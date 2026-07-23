# MailDeck 開発コンテキスト（引き継ぎ用）

このファイルは、別のPCで（Claude Code などを使って）このプロジェクトの開発を
続けるための引き継ぎメモです。`git clone` 後にまずこれを読んでください。

- **リポジトリ**: https://github.com/tsdesignltd/mail （public）
- **デモ (GitHub Pages)**: https://tsdesignltd.github.io/mail/
- **最終更新セッション**: 2026-07-23

---

## 1. これは何か

macOS の「メール」(Mail.app) と連携する**ローカルWebアプリ**。追加インストール
不要（macOS標準の Python 3 だけで動く）。`python3 server.py` → http://localhost:8765。

### 当初の要望（ユーザーの最初の指示）
1. 迷惑メールの判断・リストアップ・別メールボックスへ仕訳
2. 重要な連絡を差出人ごとに分けて見る
3. FBメッセンジャーのように差出人ごとにメールを分けて見るUI
4. 重要な差出人を自動判断して「よく使う相手」に追加

### 確定した方針
- UI形態: **ローカルWebアプリ**（ブラウザで開く。裏でPythonがAppleScript経由でMail操作）
- 迷惑判定: **ハイブリッド**（ルールベース＋グレーゾーンのみ任意でAI判定）

---

## 2. アーキテクチャ

```
ブラウザUI (public/)
   ↕ HTTP (localhost:8765)
server.py — API・迷惑判定(rules.py)・重要度スコアリング・設定管理
   ↕
mail_store.py — 高速モード: ~/Library/Mail の Envelope Index (SQLite, 読み取り専用)
             — フォールバック: AppleScript (scripts/*.applescript)
   ↕
Mail.app（仕訳・本文取得・移動は常に AppleScript 経由）
```

### 主要ファイル
| ファイル | 役割 |
|---|---|
| `server.py` | HTTPサーバー・API・overview構築・設定(data/settings.json) |
| `mail_store.py` | メール取得層。高速/AppleScript両モード、移動・迷惑解除検知 |
| `rules.py` | 迷惑判定ルール、重要差出人スコアリング、自動お気に入り判定 |
| `public/index.html, app.js, style.css` | フロントUI（サムネイルタイル型ダッシュボード） |
| `scripts/*.applescript` | Mail.app 操作（下記） |
| `docs/` | GitHub Pages 用デモ。`demo.js` が `/api/*` をサンプルデータでモック |
| `start.command` | ダブルクリック起動スクリプト |

### AppleScript スクリプト
| スクリプト | 用途 |
|---|---|
| `list_accounts.applescript` | 有効アカウントの受信MB/送信MB名と件数一覧（送信MBは走査で解決） |
| `fetch_chunk.applescript` | INBOXの start〜end 番目を50通ずつ取得（巨大MB対策・差分同期にも使用） |
| `fetch_sender.applescript` | **指定アドレスとの受信+送信の全履歴を1アカウント分取得**（差出人個別同期用）。id・RFC Message-ID も返す |
| `get_content.applescript` | 1通の本文取得。**RFC Message-ID優先**・番号IDはフォールバック。取得した1通を Mail.app でも既読化 |
| `open_message.applescript` | 1通を Mail.app で別ウインドウ表示（RFC id 優先） |
| `mark_sender_read.applescript` | 指定差出人の受信メールを Mail.app で既読化（`whose sender contains`＋1通ずつ set） |
| `move_to_junk.applescript` | 各アカウント自身の迷惑フォルダへ移動（現行の仕訳先） |
| `move_messages.applescript` / `move_by_msgid.applescript` | 旧: ローカルMBへ移動（現在は未使用だが残置） |

> **AppleScript の落とし穴（重要・実測で踏んだもの）**:
> - `ref`, `kind`, `id`, **`inbox`** は予約語。変数名に使うと `-2740`/`-10006`。`inMb` 等に回避。
> - `message id <変数> of mb` は構文衝突 → `messages of mb whose id is <変数>` を使う。RFC Message-ID での照合は `whose message id is <変数>`。
> - **Gmail の [Gmail] 配下（送信済みメール/Sent Mail 等）は `mailbox "名前" of account` で直接参照できない(-1728)**。`every mailbox of acct` を走査して名前一致のオブジェクトを得る（list_accounts / fetch_sender / get_content / open_message で対応済み）。
> - **Gmail の `whose ...` 結果は [Gmail]/All Mail 参照になり一括プロパティ取得(`id of {list}`)が -1728 で失敗**。該当会話は1通ずつ取得する。
> - **番号ID(整数 id)は Mail の再インデックス等で振り替わりうる**。本文取得・表示は安定・一意な RFC Message-ID を優先（`rfcId`）。
> - **`whose read status is false` は Gmail の巨大INBOXで120秒でもタイムアウト**。一括既読はMail.appを触らずキャッシュ上のみで行う（後述）。

---

## 3. 実装済み機能（このセッションで作った順）

1. **基本機能**: 迷惑判定・差出人別スレッド・自動お気に入り・信頼/ブロックリスト学習
2. **GitHub保存 + Pages デモ**: `docs/` にサンプルデータ版。`data/` は .gitignore で除外
3. **他PC対応**: `start.command`、README を汎用手順に
4. **UI刷新（サムネイルタイル型ダッシュボード）** ← スケッチ指定:
   - 上部: よく使う相手を大タイルでグリッド表示（最大20件・新着順・未読バッジ右上・✕ボタン右下）
   - 下部: 全員リストを**3カラム**表示、ブラウザ下端まで拡大、名前/アドレス/受信日時でソート可
   - 右上: メールアカウント切替ドロップダウン
   - タイル/行クリックで会話をオーバーレイ表示、「← 一覧に戻る」or **ロゴクリック**で戻る
5. **仕訳先を各アカウントの迷惑メールフォルダに統一**: 迷惑候補タブの仕訳もブロックも
   `move_to_junk.applescript`（迷惑フォルダ名を候補から自動解決: 迷惑メール/Junk等）
6. **過去1ヶ月ベースの同期 + 分割取得**:
   - 「最新N件」でなく**過去31日分を全部**取得（`CUTOFF_DAYS=31` in mail_store.py）
   - 巨大MB（tsdx@mac.com=6.6万通）で接続切断(-609/-1712)するため**50通ずつ分割取得**
     （`_fetch_account_chunked`、AppleEventタイムアウト延長、チャンク毎保存・リトライ）
   - アカウント別取得エラーを記録し画面右上に表示
7. **「迷惑メールではない」の学習**: MailDeckが迷惑フォルダへ移動したメールを
   `data/moved.json` に記録。ユーザーがMail.appで受信トレイに戻すと、次回同期で検知して
   その差出人を**ブロック解除＋信頼リストへ自動移行**（`_check_restored`/`consume_restored`/
   `apply_restored_senders`）
8. **同期対象アカウントのON/OFF**: 設定画面にチェックボックス（`excludedAccounts`）

### 2026-07-23 セッションで追加（会話タイムライン・個別同期・高速化）
9. **送受信タイムライン**: 会話画面で相手の受信メールは左（グレー）、**自分の返信は右（青「自分の返信」）**。迷惑判定・重要度スコア・お気に入り学習は**受信のみ**（挙動不変）、送信は表示のためスレッドに合流。
10. **全体同期は受信のみ**: `sync_applescript` は INBOX（左側）だけ取得。**送信（右側）は差出人個別同期でのみ取得**（巨大な送信MBを毎回スキャンしない）。
11. **差出人個別の同期**（`fetch_sender.applescript` / `sync_sender` / `POST /api/sync/sender`）: 会話の「🔄 この相手を同期」ボタン＋**会話を開いた時に自動同期**（セッション中は相手ごと1回）。**全アカウント横断でその相手の受信+送信の全履歴**を取得。巨大アカウントからも相手の分だけ取れる。全体同期中はスキップ。
12. **メールで開く**（`open_message.applescript` / `POST /api/message/open`）: 各バブル・迷惑候補の各メールの**件名末尾に封筒アイコン ✉️**。クリックで Mail.app に別ウインドウ表示。バブル本体のクリック（本文開閉）とは stopPropagation で分離。
13. **RFC Message-ID 照合**: 本文取得・メール表示を番号IDでなく安定・一意な RFC Message-ID 優先に（番号ID振り替わりによる取り違え防止。`rfcId`）。
14. **差分（増分）同期**: 右上「同期」は前回以降の**新着だけ**取得（新しい順に取得し既知メールに当たったら停止）。初回のみフル。設定に「全体を再取得」ボタン（`POST /api/sync {full:true}`）。`store.version` でキャッシュ変更を追跡。高速モード(sqlite)は使わない方針に。
15. **自動同期（1時間ごと）**: `autoSync` 設定（既定OFF）。**ブラウザ側タイマー**で MailDeck を開いている間1時間毎に差分同期し画面も更新。**設定画面のチェックボックス**と**メニューバーのON/OFFトグル**の両方から切替（連動）。
16. **パフォーマンス最適化**: `build_overview` を**メモ化**（`(store.version, SETTINGS_VERSION)` をキー。実測 37ms→9ms/2988件）。フロントはクリックを**イベント委譲**に（描画毎の約950リスナー付け直しを廃止）。検索を150msデバウンス。
17. **差出人ごとの既読**（`mark_read` / `mark_sender_read_async` / `POST /api/read/all {sender}`）:
    - ボタンは2ヶ所 —「すべての差出人」一覧の各行（未読行のみ・ホバー表示）の「✓ 既読」と、**会話ヘッダーの差出人名の隣**の「✓ すべて既読」（`#threadReadBtn`、未読時のみ表示）。
    - **キャッシュ（表示）は即座に既読**（`mark_read`）→バッジが消える。フロントは全再描画せず局所更新。
    - **差出人指定時は Mail.app 側もバックグラウンドで既読化**（`mark_sender_read.applescript` = 各アカウントの受信MBで `whose sender contains addr` → 1通ずつ `set read status`。バルク set は All Mail 参照で失敗するため）。件数が多いと数十秒かかるので非同期。
    - `account`指定/全体（sender無し）は**キャッシュのみ**（全差出人を Mail.app 既読化すると whose が遅く非現実的なため）。
18. **本文を開いたら Mail.app でも既読に**: 会話でバブルの本文を開く（`get_content`）と、その1通を **Mail.app 側でも既読**にする（`set read status ... to true`）＋キャッシュも既読。1通だけなので高速。フロントは全再描画せずそのバブルの未読表示だけ局所的に消す（`markBubbleReadLocal`）。

---

## 4. 現在の状態・既知の課題

### アカウント設定（data/settings.json、※このPC固有・gitignore対象）
- **除外中**: `sunadx@gmail.com`
- **同期対象**: monoralbikes / monoraloutdoor / outdesign.inc / sunadx@me.com /
  sunami26015@venus.joshibi.jp / tsdesign.ltd / **tsdx@mac.com**

### 未解決・注意点
- ✅ **差分同期で常用時の遅さは大幅緩和**（2回目以降は新着のみ）。初回のフル取得は
  依然かかる（tsdx@mac.com は巨大なので初回は数十分想定）。
- ⚠️ **tsdx@mac.com は受信6.6万通と巨大**。初回フル取得や、その相手を含む個別同期は
  時間がかかる。差分同期でも1チャンクは必要。
- ⚠️ **高速モード(sqlite)は現在使わない方針**（`sync()` は常に AppleScript 差分同期）。
  理由: sqlite モードは本文取得・送信・「メールで開く」非対応で、受信も二重表示に
  なりうる（未検証）。将来やるなら sync_sqlite に送信取り込み＋重複排除が必要。
- ⚠️ **一括既読(すべて/差出人ごと)は Mail.app を触らない**（`whose read status is false`
  が Gmail で120秒超のため）。**本文を開いた1通だけ** Mail.app にも既読反映される。
- **AI判定**: `claude` CLI があれば「グレーゾーンをAI判定」ボタンが出る（`aiAvailable`）。
  無ければ非表示。
- **GitHub のPAT に workflow スコープが無い**ため、`.github/workflows/*` は push 不可。
  Pages は Settings→Pages で main /docs を手動選択する方式。
  ※ `docs/`（Pagesデモ）は本セッションの新機能に未追従。実挙動はローカル実行で確認。

### データの扱い（プライバシー）
- `data/`（settings.json / cache.json / moved.json / accounts.json）は **.gitignore 済み**。
  実メール・学習リストは**PCごとに独立**。GitHubには一切上がらない。
- 別PCで続きをやる場合、**メール取得は各PCで同期し直す**（キャッシュは共有されない）。

---

## 5. 別PCで開発を再開する手順

```sh
git clone https://github.com/tsdesignltd/mail.git
cd mail
python3 server.py    # → http://localhost:8765、右上「同期」を押す
```
または `start.command` をダブルクリック。初回は Mail 操作の許可ダイアログでOK。

- 初回の「同期」は時間がかかる（過去1ヶ月分をフル取得）。**2回目以降は差分同期**で速い。
- **会話を開くと自動でその相手を個別同期**し、送信（右側）・本文・「メールで開く」が使える。
- 自動同期（1時間毎）は既定OFF。メニューバー or 設定でON/OFF。
- 設定（除外アカウント等）は data/ が無い状態から始まるので、各PCで初回設定が必要。

Claude Code で続ける場合は、この `CONTEXT.md` と `README.md` を読ませればフルに
文脈を復元できる。

---

## 6. 次にやると良い候補（TODO）
- [ ] 迷惑判定ルール(rules.py)の精度チューニング（誤検知の確認）
- [ ] `docs/`（Pagesデモ）を本セッションの新機能（タイムライン・個別同期・既読等）に追従
- [ ] 一括既読も Mail.app に反映したい場合の高速な方法検討（現状 whose が遅く未対応）
- [ ] 手動でMail側へ移動/削除したメールのキャッシュ反映（差分同期は削除を検出しない。
      現状「全体を再取得」で解消）
- [ ] 複数PCで設定/学習を共有したい場合の方式検討（非公開リポジトリ化 or Dropbox経由でdata/共有）
- [ ] （任意）高速モード(sqlite)を使うなら: 送信取り込み＋sq/asキー重複排除＋本文対応

## 7. 主なAPI（server.py）
| メソッド/パス | 用途 |
|---|---|
| `GET /api/overview` | ダッシュボード一式（メモ化済み） |
| `POST /api/sync {full?}` | 差分同期（full=trueで全取得） |
| `POST /api/sync/sender {addr}` | 差出人個別の送受信同期 |
| `GET /api/message?key=` | 本文取得（＝Mail.appでも既読化） |
| `POST /api/message/open {key}` | Mail.appで開く |
| `POST /api/read/all {sender?,account?}` | 既読化（MailDeck表示のみ） |
| `POST /api/spam/move|trust|block|ai` | 迷惑仕訳・学習・AI判定 |
| `POST /api/favorites {sender,action}` | よく使う相手 pin/unpin/dismiss |
| `POST /api/settings {...}` | 設定更新（autoSync/excludedAccounts/perAccountLimit 等） |
