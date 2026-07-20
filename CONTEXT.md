# MailDeck 開発コンテキスト（引き継ぎ用）

このファイルは、別のPCで（Claude Code などを使って）このプロジェクトの開発を
続けるための引き継ぎメモです。`git clone` 後にまずこれを読んでください。

- **リポジトリ**: https://github.com/tsdesignltd/mail （public）
- **デモ (GitHub Pages)**: https://tsdesignltd.github.io/mail/
- **最終更新セッション**: 2026-07-20

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
| `list_accounts.applescript` | 有効アカウントとINBOX件数一覧 |
| `fetch_chunk.applescript` | INBOXの start〜end 番目を50通ずつ取得（巨大MB対策） |
| `get_content.applescript` | 1通の本文取得（`whose id is` で検索） |
| `move_to_junk.applescript` | 各アカウント自身の迷惑フォルダへ移動（現行の仕訳先） |
| `move_messages.applescript` / `move_by_msgid.applescript` | 旧: ローカルMBへ移動（現在は未使用だが残置） |

> **AppleScript の落とし穴（重要）**: `ref`, `kind`, `id` は予約語。変数名に使うと
> `-2740`/`-10006` エラー。`refVal`, `refKind` 等に回避済み。
> `message id <変数> of mb` も構文衝突するので `messages of mb whose id is <変数>` を使う。

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

---

## 4. 現在の状態・既知の課題

### アカウント設定（data/settings.json、※このPC固有・gitignore対象）
- **除外中**: `sunadx@gmail.com`
- **同期対象**: monoralbikes / monoraloutdoor / outdesign.inc / sunadx@me.com /
  sunami26015@venus.joshibi.jp / tsdesign.ltd / **tsdx@mac.com**

### 未解決・注意点
- ⚠️ **tsdx@mac.com は受信6.6万通と巨大**。AppleScriptの分割取得だと1ヶ月分フルで
  1時間近くかかる（50通≒10分）。最後のセッションで同期を開始したが完走は未確認。
- ⚠️ **高速モード（フルディスクアクセス）が本命の解決策**。許可すれば全アカウント
  数秒。「システム設定→プライバシーとセキュリティ→フルディスクアクセス」でターミナル
  （or Claude）をON。**まだ許可されていない**ため未検証。許可後は `mail_store.py` の
  `sync_sqlite` を実データでテストすること。
- **Claude CLI 未インストール**のため、グレーゾーンのAI判定ボタンは非表示。
- **GitHub のPAT に workflow スコープが無い**ため、`.github/workflows/*` は push 不可。
  Pages は Settings→Pages で main /docs を手動選択する方式（CONTEXT作成時点で有効化済みか要確認）。

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

Claude Code で続ける場合は、この `CONTEXT.md` と `README.md` を読ませればフルに
文脈を復元できる。設定（除外アカウント等）は data/ が無い状態から始まるので、
設定画面で sunadx@gmail.com を再度除外するなど、各PCで初回設定が必要。

---

## 6. 次にやると良い候補（TODO）
- [ ] フルディスクアクセス許可後、高速モード(sync_sqlite)を実データで検証
- [ ] tsdx@mac.com の1ヶ月分同期の完走確認（or 高速モードで代替）
- [ ] 迷惑判定ルール(rules.py)の精度チューニング（誤検知の確認）
- [ ] 複数PCで設定/学習を共有したい場合の方式検討（非公開リポジトリ化 or Dropbox経由でdata/共有）
- [ ] 本文取得の高速モード対応（現状 sqlite モードでは本文は Mail.app で開く案内のみ）
