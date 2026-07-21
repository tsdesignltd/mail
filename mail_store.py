# -*- coding: utf-8 -*-
"""メールデータ取得層。

高速モード: ~/Library/Mail/V*/MailData/Envelope Index (SQLite) を直接読む。
            フルディスクアクセスが許可されている場合のみ使える。
フォールバック: AppleScript で各アカウントの直近メールを取得(遅い)。
"""
import glob
import json
import os
import re
import sqlite3
import subprocess
import threading
import time
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
DATA_DIR = os.path.join(BASE_DIR, "data")
CACHE_PATH = os.path.join(DATA_DIR, "cache.json")

FIELD_SEP = "␞"  # ␞
REC_SEP = "␟"    # ␟

# Apple epoch ではなく unix epoch が使われている列もあるため両対応で変換する
APPLE_EPOCH_OFFSET = 978307200  # 2001-01-01

# 「やり取りのあった相手」として扱う期間 (日)
CUTOFF_DAYS = 31


def run_osascript(script_name, args, timeout=600):
    path = os.path.join(SCRIPTS_DIR, script_name)
    cmd = ["osascript", path] + [str(a) for a in args]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError("osascript error: %s" % proc.stderr.strip())
    return proc.stdout.rstrip("\n")


def parse_sender(raw):
    """'名前 <addr@example.com>' → (名前, アドレス)"""
    raw = (raw or "").strip()
    m = re.match(r'^"?(.*?)"?\s*<([^<>]+@[^<>]+)>$', raw)
    if m:
        name = m.group(1).strip() or m.group(2)
        return name, m.group(2).lower().strip()
    if "@" in raw:
        return raw, raw.lower()
    return raw or "(不明)", raw.lower() or "(不明)"


class SyncStatus(object):
    def __init__(self):
        self.lock = threading.Lock()
        self.running = False
        self.mode = None          # "sqlite" | "applescript"
        self.progress = ""        # 進行状況の説明文
        self.done_accounts = 0
        self.total_accounts = 0
        self.last_sync = None
        self.error = None
        self.account_errors = {}  # アカウント名 -> 直近同期のエラー内容

    def snapshot(self):
        with self.lock:
            return {
                "running": self.running,
                "mode": self.mode,
                "progress": self.progress,
                "doneAccounts": self.done_accounts,
                "totalAccounts": self.total_accounts,
                "lastSync": self.last_sync,
                "error": self.error,
                "accountErrors": dict(self.account_errors),
            }


MOVED_PATH = os.path.join(DATA_DIR, "moved.json")


class MailStore(object):
    def __init__(self):
        self.lock = threading.Lock()
        self.messages = {}   # key -> dict
        self.replied_to = {} # address -> 返信した回数 (sqliteモードのみ)
        self.status = SyncStatus()
        # 迷惑フォルダへ移動したメールの記録。受信トレイに戻ってきたら
        # 「ユーザーが迷惑メールではないと指定した」とみなす。
        # {"id:<acct>:<msgid>" or "mid:<rfcId>": senderAddr}
        self.moved_records = {}
        self.restored = set()  # 迷惑ではないと指定された差出人 (未処理分)
        self.sender_lock = threading.Lock()
        self.sender_syncing = False  # 差出人個別同期の実行中フラグ
        self._load_cache()
        self._load_moved()

    def _load_moved(self):
        if os.path.exists(MOVED_PATH):
            try:
                with open(MOVED_PATH, "r", encoding="utf-8") as f:
                    self.moved_records = json.load(f)
            except Exception:
                self.moved_records = {}

    def _save_moved(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = MOVED_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.moved_records, f, ensure_ascii=False)
        os.replace(tmp, MOVED_PATH)

    def _check_restored(self, msg):
        """受信トレイで見つかったメールが「迷惑フォルダへ移動した記録」と一致したら、
        ユーザーが Mail.app で迷惑メールではないと指定した(戻した)と判断する。"""
        keys = []
        if msg.get("id") is not None:
            keys.append("id:%s:%s" % (msg.get("account"), msg["id"]))
        if msg.get("rfcId"):
            keys.append("mid:%s" % msg["rfcId"])
        hit = False
        for k in keys:
            if k in self.moved_records:
                self.restored.add(self.moved_records.pop(k))
                hit = True
        if hit:
            self._save_moved()

    def consume_restored(self):
        """未処理の「迷惑ではない」差出人を取り出す (呼び出し側で信頼リストへ)。"""
        with self.lock:
            r = list(self.restored)
            self.restored.clear()
        return r

    # ---------- キャッシュ ----------
    def _load_cache(self):
        if os.path.exists(CACHE_PATH):
            try:
                with open(CACHE_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.messages = data.get("messages", {})
                self.replied_to = data.get("repliedTo", {})
                self.status.last_sync = data.get("lastSync")
            except Exception:
                self.messages = {}

    def _save_cache(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = CACHE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({
                "messages": self.messages,
                "repliedTo": self.replied_to,
                "lastSync": self.status.last_sync,
            }, f, ensure_ascii=False)
        os.replace(tmp, CACHE_PATH)

    # ---------- Envelope Index (高速モード) ----------
    def envelope_index_path(self):
        for p in sorted(glob.glob(os.path.expanduser("~/Library/Mail/V*/MailData/Envelope Index")), reverse=True):
            return p
        return None

    def sqlite_available(self):
        p = self.envelope_index_path()
        if not p:
            return False
        try:
            with open(p, "rb") as f:
                f.read(16)
            return True
        except (PermissionError, OSError):
            return False

    def _convert_date(self, v):
        if v is None:
            return None
        try:
            v = float(v)
        except (TypeError, ValueError):
            return None
        # Apple epoch (2001年基準) なら unix に変換
        if v < 1000000000:
            v += APPLE_EPOCH_OFFSET
        return datetime.fromtimestamp(v).strftime("%Y-%m-%dT%H:%M:%S")

    def sync_sqlite(self, limit=3000, excluded=None):
        """Envelope Index から直近 limit 件 + 送信履歴を読む。"""
        excluded = set(excluded or [])
        st = self.status
        with st.lock:
            st.running = True
            st.mode = "sqlite"
            st.progress = "ローカルDBを読み込み中..."
            st.error = None
        try:
            src = self.envelope_index_path()
            # Mail が書き込み中でも安全に読むため読み取り専用 URI で開く
            con = sqlite3.connect("file:%s?mode=ro" % src.replace("?", "%3f"), uri=True, timeout=10)
            con.row_factory = sqlite3.Row
            cur = con.cursor()

            cols = {r[1] for r in cur.execute("PRAGMA table_info(messages)")}
            tables = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}

            # スキーマはOSバージョンで変わるため、存在確認しながら組み立てる
            subject_join = "subjects" in tables and "subject" in cols
            sender_join = "addresses" in tables and "sender" in cols
            mailbox_join = "mailboxes" in tables and "mailbox" in cols
            q = ["SELECT m.ROWID AS rowid_", ]
            q.append(", m.read AS read_" if "read" in cols else ", 1 AS read_")
            q.append(", m.flagged AS flagged" if "flagged" in cols else ", 0 AS flagged")
            date_col = "date_received" if "date_received" in cols else ("date_sent" if "date_sent" in cols else None)
            q.append(", m.%s AS date_" % date_col if date_col else ", NULL AS date_")
            q.append(", s.subject AS subject" if subject_join else ", '' AS subject")
            if sender_join:
                q.append(", a.address AS sender_addr, a.comment AS sender_name")
            else:
                q.append(", '' AS sender_addr, '' AS sender_name")
            q.append(", mb.url AS mailbox_url" if mailbox_join else ", '' AS mailbox_url")
            q.append(", m.message_id AS rfc_id" if "message_id" in cols else ", NULL AS rfc_id")
            q.append(" FROM messages m")
            if subject_join:
                q.append(" LEFT JOIN subjects s ON s.ROWID = m.subject")
            if sender_join:
                q.append(" LEFT JOIN addresses a ON a.ROWID = m.sender")
            if mailbox_join:
                q.append(" LEFT JOIN mailboxes mb ON mb.ROWID = m.mailbox")
            if "deleted" in cols:
                q.append(" WHERE m.deleted = 0")
            if date_col:
                q.append(" ORDER BY m.%s DESC" % date_col)
            q.append(" LIMIT %d" % limit)

            rows = cur.execute("".join(q)).fetchall()
            with st.lock:
                st.progress = "メッセージ %d 件を解析中..." % len(rows)

            cutoff_iso = (datetime.now() - timedelta(days=CUTOFF_DAYS)).strftime("%Y-%m-%dT%H:%M:%S")
            new_messages = {}
            for r in rows:
                url = r["mailbox_url"] or ""
                # 受信トレイ系のみ対象(送信済み・ゴミ箱・迷惑は除外)
                if url and not self._is_inbox_url(url):
                    continue
                d = self._convert_date(r["date_"])
                if d and d < cutoff_iso:
                    continue
                if self._account_from_url(url) in excluded:
                    continue
                addr = (r["sender_addr"] or "").lower()
                name = r["sender_name"] or addr or "(不明)"
                key = "sq:%s" % r["rowid_"]
                if isinstance(r["rfc_id"], str):
                    self._check_restored({"rfcId": r["rfc_id"]})
                new_messages[key] = {
                    "key": key,
                    "source": "sqlite",
                    "rowid": r["rowid_"],
                    "account": self._account_from_url(url),
                    "mailbox": "INBOX",
                    "id": None,
                    "date": self._convert_date(r["date_"]),
                    "read": bool(r["read_"]),
                    "flagged": bool(r["flagged"]),
                    "senderName": name,
                    "senderAddr": addr or "(不明)",
                    "subject": r["subject"] or "(件名なし)",
                    "rfcId": r["rfc_id"] if isinstance(r["rfc_id"], str) else None,
                }

            # 送信履歴: recipients テーブルから「自分が送った相手」を数える
            replied = {}
            if "recipients" in tables:
                try:
                    rec_cols = {c[1] for c in cur.execute("PRAGMA table_info(recipients)")}
                    addr_ref = "address" if "address" in rec_cols else None
                    msg_ref = "message" if "message" in rec_cols else ("message_id" if "message_id" in rec_cols else None)
                    if addr_ref and msg_ref and mailbox_join:
                        rows2 = cur.execute(
                            "SELECT a.address AS addr, COUNT(*) AS cnt FROM recipients r "
                            "JOIN addresses a ON a.ROWID = r.%s "
                            "JOIN messages m ON m.ROWID = r.%s "
                            "JOIN mailboxes mb ON mb.ROWID = m.mailbox "
                            "WHERE mb.url LIKE '%%Sent%%' OR mb.url LIKE '%%送信%%' "
                            "GROUP BY a.address ORDER BY cnt DESC LIMIT 500" % (addr_ref, msg_ref)
                        ).fetchall()
                        for r2 in rows2:
                            if r2["addr"]:
                                replied[r2["addr"].lower()] = r2["cnt"]
                except Exception:
                    pass
            con.close()

            with self.lock:
                self.messages = new_messages
                if replied:
                    self.replied_to = replied
            with st.lock:
                st.last_sync = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                st.progress = "完了 (%d 件)" % len(new_messages)
            self._save_cache()
        except Exception as e:
            with st.lock:
                st.error = str(e)
        finally:
            with st.lock:
                st.running = False

    def _is_inbox_url(self, url):
        u = url.lower()
        if "inbox" in u or u.endswith("/受信"):
            return True
        for bad in ("sent", "trash", "junk", "draft", "deleted", "spam", "送信", "ゴミ", "迷惑", "下書き", "アーカイブ", "all%20mail", "allmail"):
            if bad in u:
                return False
        return False

    def _account_from_url(self, url):
        # imap://user%40example.com@imap.example.com/INBOX → user@example.com
        m = re.match(r'^[a-z]+://([^@/]+)@', url)
        if m:
            try:
                from urllib.parse import unquote
                return unquote(m.group(1))
            except Exception:
                return m.group(1)
        return "local"

    # ---------- AppleScript (フォールバック) ----------
    def _list_accounts(self):
        """有効アカウントと受信/送信メールボックス名・件数を取得する。
        list_accounts.applescript の出力: 名前␞受信MB␞受信件数␞送信MB␞送信件数
        (旧形式 名前␞MB␞件数 も許容)。副作用で accounts.json を更新する。"""
        raw = run_osascript("list_accounts.applescript", [], timeout=900)
        accounts = []
        for rec in raw.split(REC_SEP):
            if not rec.strip():
                continue
            parts = rec.split(FIELD_SEP)
            if len(parts) >= 3:
                acct = {"name": parts[0], "mailbox": parts[1], "count": int(parts[2]),
                        "sentMailbox": "", "sentCount": 0}
                if len(parts) >= 5:
                    acct["sentMailbox"] = parts[3]
                    try:
                        acct["sentCount"] = int(parts[4])
                    except ValueError:
                        acct["sentCount"] = 0
                accounts.append(acct)
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(os.path.join(DATA_DIR, "accounts.json"), "w", encoding="utf-8") as f:
            json.dump({a["name"]: a["name"] for a in accounts}, f, ensure_ascii=False)
        return accounts

    def sync_sender(self, addr, excluded=None):
        """指定アドレスとの受信+送信の全履歴を、全(非除外)アカウントから取得する。
        差出人個別ページの「同期」ボタン用。期間の上限なし(その相手の分だけ)。"""
        addr = (addr or "").lower().strip()
        if not addr:
            return {"received": 0, "sent": 0, "error": "アドレスが空です"}
        excluded = set(excluded or [])
        with self.sender_lock:
            if self.sender_syncing:
                return {"busy": True}
            self.sender_syncing = True
        r_count = s_count = 0
        try:
            accounts = self._list_accounts()
            for acct in accounts:
                if acct["name"] in excluded:
                    continue
                try:
                    raw = run_osascript(
                        "fetch_sender.applescript",
                        [acct["name"], acct["mailbox"], acct.get("sentMailbox", ""), addr],
                        timeout=600)
                except Exception:
                    continue  # 1アカウント失敗は無視して続行
                for rec in raw.split(REC_SEP):
                    if not rec.strip():
                        continue
                    parts = rec.split(FIELD_SEP)
                    if len(parts) < 6:
                        continue
                    typ = parts[0]
                    if typ == "R":
                        msg_id, date_s, read_s, sender_raw = parts[1], parts[2], parts[3], parts[4]
                        subject = FIELD_SEP.join(parts[5:])
                        name, saddr = parse_sender(sender_raw)
                        key = "as:%s:%s" % (acct["name"], msg_id)
                        try:
                            self._check_restored({"id": int(msg_id), "account": acct["name"]})
                        except ValueError:
                            pass
                        with self.lock:
                            self.messages[key] = {
                                "key": key, "source": "applescript", "rowid": None,
                                "account": acct["name"], "mailbox": acct["mailbox"],
                                "id": int(msg_id), "date": date_s, "read": read_s == "true",
                                "flagged": False, "senderName": name, "senderAddr": saddr,
                                "subject": subject or "(件名なし)",
                            }
                        r_count += 1
                    elif typ == "S":
                        msg_id, date_s, to_addr, to_name = parts[1], parts[2], parts[3], parts[4]
                        subject = FIELD_SEP.join(parts[5:])
                        to_addr = (to_addr or "").lower().strip()
                        if not to_addr:
                            continue
                        key = "sent:%s:%s" % (acct["name"], msg_id)
                        with self.lock:
                            self.messages[key] = {
                                "key": key, "source": "applescript", "rowid": None,
                                "account": acct["name"], "mailbox": acct.get("sentMailbox", ""),
                                "id": int(msg_id), "date": date_s, "read": True,
                                "flagged": False, "fromMe": True,
                                "toAddr": to_addr, "toName": to_name or to_addr,
                                "senderName": "自分", "senderAddr": acct["name"],
                                "subject": subject or "(件名なし)",
                            }
                        s_count += 1
            self._save_cache()
        finally:
            with self.sender_lock:
                self.sender_syncing = False
        return {"received": r_count, "sent": s_count}

    def sync_applescript(self, per_account_limit=100, excluded=None):
        excluded = set(excluded or [])
        st = self.status
        with st.lock:
            st.running = True
            st.mode = "applescript"
            st.progress = "アカウント一覧を取得中..."
            st.error = None
            st.done_accounts = 0
        try:
            accounts = self._list_accounts()
            accounts = [a for a in accounts if a["name"] not in excluded]
            with st.lock:
                st.total_accounts = len(accounts)

            with st.lock:
                st.account_errors = {}
            for acct in accounts:
                try:
                    if acct["count"] > 0:
                        self._fetch_account_chunked(acct, per_account_limit)
                    # 送信済みも取得して「自分の返信」をタイムラインに混ぜる
                    if acct.get("sentMailbox") and acct.get("sentCount", 0) > 0:
                        self._fetch_sent_chunked(acct, per_account_limit)
                except Exception as e:
                    with st.lock:
                        st.account_errors[acct["name"]] = str(e)
                finally:
                    with st.lock:
                        st.done_accounts += 1

            with st.lock:
                st.last_sync = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                st.progress = "完了"
            self._save_cache()
        except Exception as e:
            with st.lock:
                st.error = str(e)
        finally:
            with st.lock:
                st.running = False

    CHUNK_SIZE = 50

    def _fetch_account_chunked(self, acct, cap):
        """過去 CUTOFF_DAYS 日分を 50通ずつ分割取得する。
        巨大メールボックスでの一括取得は Mail の接続が切れる(-609)ため。
        チャンク失敗は1回リトライし、2回失敗したら途中まで保存して打ち切る。"""
        st = self.status
        cutoff_iso = (datetime.now() - timedelta(days=CUTOFF_DAYS)).strftime("%Y-%m-%dT%H:%M:%S")
        start = 1
        fetched = 0
        while fetched < cap:
            end = min(start + self.CHUNK_SIZE - 1, start + cap - fetched - 1)
            with st.lock:
                st.progress = "%s から取得中... (%d件目〜)" % (acct["name"], start)
            raw = None
            for attempt in (1, 2):
                try:
                    raw = run_osascript("fetch_chunk.applescript",
                                        [acct["name"], acct["mailbox"], start, end],
                                        timeout=600)
                    break
                except Exception as e:
                    if attempt == 2:
                        with st.lock:
                            st.account_errors[acct["name"]] = \
                                "%d件目以降の取得に失敗: %s" % (start, e)
                        return
                    time.sleep(3)
            if not raw.strip():
                return  # メールボックスの末尾に到達
            records = [r for r in raw.split(REC_SEP) if r.strip()]
            self._merge_applescript(acct, raw)
            self._save_cache()
            fetched += len(records)
            # このチャンクの最古が期間外なら打ち切り (1が最新の前提)
            oldest = records[-1].split(FIELD_SEP)
            if len(oldest) >= 2 and oldest[1] < cutoff_iso:
                return
            if len(records) < (end - start + 1):
                return  # 末尾に到達
            start = end + 1

    def _merge_applescript(self, acct, raw):
        for rec in raw.split(REC_SEP):
            if not rec.strip():
                continue
            parts = rec.split(FIELD_SEP)
            if len(parts) < 5:
                continue
            msg_id, date_s, read_s, sender_raw, subject = parts[0], parts[1], parts[2], parts[3], FIELD_SEP.join(parts[4:])
            name, addr = parse_sender(sender_raw)
            key = "as:%s:%s" % (acct["name"], msg_id)
            self._check_restored({"id": int(msg_id), "account": acct["name"]})
            with self.lock:
                self.messages[key] = {
                    "key": key,
                    "source": "applescript",
                    "rowid": None,
                    "account": acct["name"],
                    "mailbox": acct["mailbox"],
                    "id": int(msg_id),
                    "date": date_s,
                    "read": read_s == "true",
                    "flagged": False,
                    "senderName": name,
                    "senderAddr": addr,
                    "subject": subject or "(件名なし)",
                }

    SENT_CHUNK_SIZE = 25  # 送信は1通ずつ宛先を読むため受信より小さめ

    def _fetch_sent_chunked(self, acct, cap):
        """送信済みメールボックスを過去 CUTOFF_DAYS 日分・分割取得する。
        1通ずつ宛先(受取人)を読むため受信より遅い。上限 cap で打ち切る。"""
        st = self.status
        cutoff_iso = (datetime.now() - timedelta(days=CUTOFF_DAYS)).strftime("%Y-%m-%dT%H:%M:%S")
        start = 1
        fetched = 0
        while fetched < cap:
            end = min(start + self.SENT_CHUNK_SIZE - 1, start + cap - fetched - 1)
            with st.lock:
                st.progress = "%s の送信履歴を取得中... (%d件目〜)" % (acct["name"], start)
            raw = None
            for attempt in (1, 2):
                try:
                    raw = run_osascript("fetch_sent_chunk.applescript",
                                        [acct["name"], acct["sentMailbox"], start, end],
                                        timeout=600)
                    break
                except Exception:
                    if attempt == 2:
                        return  # 送信履歴の取得失敗は致命的でないので黙って諦める
                    time.sleep(3)
            if not raw.strip():
                return
            records = [r for r in raw.split(REC_SEP) if r.strip()]
            self._merge_sent_applescript(acct, raw)
            self._save_cache()
            fetched += len(records)
            oldest = records[-1].split(FIELD_SEP)
            if len(oldest) >= 2 and oldest[1] < cutoff_iso:
                return
            if len(records) < (end - start + 1):
                return
            start = end + 1

    def _merge_sent_applescript(self, acct, raw):
        for rec in raw.split(REC_SEP):
            if not rec.strip():
                continue
            parts = rec.split(FIELD_SEP)
            if len(parts) < 5:
                continue
            msg_id, date_s, to_addr, to_name, subject = (
                parts[0], parts[1], parts[2], parts[3], FIELD_SEP.join(parts[4:]))
            to_addr = (to_addr or "").lower().strip()
            if not to_addr:
                continue
            key = "sent:%s:%s" % (acct["name"], msg_id)
            with self.lock:
                self.messages[key] = {
                    "key": key,
                    "source": "applescript",
                    "rowid": None,
                    "account": acct["name"],
                    "mailbox": acct["sentMailbox"],
                    "id": int(msg_id),
                    "date": date_s,
                    "read": True,
                    "flagged": False,
                    "fromMe": True,
                    "toAddr": to_addr,
                    "toName": to_name or to_addr,
                    "senderName": "自分",
                    "senderAddr": acct["name"],
                    "subject": subject or "(件名なし)",
                }

    # ---------- 共通操作 ----------
    def sync(self, per_account_limit=100, excluded=None):
        if self.status.running:
            return False
        excluded = set(excluded or [])
        if self.sqlite_available():
            t = threading.Thread(target=self.sync_sqlite,
                                 kwargs={"excluded": excluded}, daemon=True)
        else:
            t = threading.Thread(target=self.sync_applescript,
                                 args=(per_account_limit, excluded), daemon=True)
        t.start()
        return True

    def all_messages(self):
        with self.lock:
            return list(self.messages.values())

    def get_content(self, key):
        with self.lock:
            msg = self.messages.get(key)
        if not msg:
            return None
        if msg["source"] == "applescript" and msg.get("id"):
            return run_osascript("get_content.applescript",
                                 [msg["account"], msg["mailbox"], msg["id"]], timeout=300)
        return None  # sqliteモードは本文をDBに持たないため v1 では未対応

    def load_account_map(self):
        """メールアドレス → Mail.app アカウント名の対応表 (data/accounts.json)。"""
        p = os.path.join(DATA_DIR, "accounts.json")
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def move_messages(self, keys, target_mailbox):
        """AppleScript でローカルメールボックスへ移動する。
        AppleScript 由来 → numeric id で高速移動。
        sqlite 由来   → RFC Message-ID の whose 検索で移動(やや遅い)。"""
        by_id_args = [target_mailbox]
        by_rfc_args = [target_mailbox]
        movable_id, movable_rfc = [], []
        acct_map = self.load_account_map()
        with self.lock:
            for k in keys:
                m = self.messages.get(k)
                if not m:
                    continue
                if m.get("id") is not None:
                    by_id_args += [m["account"], m["mailbox"], m["id"]]
                    movable_id.append(k)
                elif m.get("rfcId"):
                    acct_name = acct_map.get(m.get("account", ""), m.get("account", ""))
                    by_rfc_args += [acct_name, m["rfcId"]]
                    movable_rfc.append(k)
        moved = failed = 0
        if movable_id:
            out = run_osascript("move_messages.applescript", by_id_args, timeout=900)
            a, b = [int(x) for x in out.split(",")]
            moved += a
            failed += b
        if movable_rfc:
            out = run_osascript("move_by_msgid.applescript", by_rfc_args, timeout=900)
            a, b = [int(x) for x in out.split(",")]
            moved += a
            failed += b
        if moved:
            with self.lock:
                for k in movable_id + movable_rfc:
                    self.messages.pop(k, None)
            self._save_cache()
        skipped = len(keys) - len(movable_id) - len(movable_rfc)
        return {"moved": moved, "failed": failed, "skipped": skipped}

    def move_to_junk(self, keys):
        """指定メッセージを各アカウント自身の迷惑メールフォルダへ移動する。
        成功したメールは記録し、後で受信トレイに戻されたら「迷惑ではない」と判断する。"""
        args = []
        movable = []  # (key, 記録キー, senderAddr)
        acct_map = self.load_account_map()
        with self.lock:
            for k in keys:
                m = self.messages.get(k)
                if not m:
                    continue
                if m.get("id") is not None:
                    args += [m["account"], m["mailbox"], "id", m["id"]]
                    movable.append((k, "id:%s:%s" % (m["account"], m["id"]), m.get("senderAddr", "")))
                elif m.get("rfcId"):
                    acct_name = acct_map.get(m.get("account", ""), m.get("account", ""))
                    args += [acct_name, "INBOX", "mid", m["rfcId"]]
                    movable.append((k, "mid:%s" % m["rfcId"], m.get("senderAddr", "")))
        if not movable:
            return {"moved": 0, "failed": 0, "skipped": len(keys)}
        out = run_osascript("move_to_junk.applescript", args, timeout=900)
        statuses = out.split(",")
        moved = failed = 0
        with self.lock:
            for (k, rec_key, addr), st_ in zip(movable, statuses):
                if st_ == "1":
                    moved += 1
                    self.messages.pop(k, None)
                    if addr:
                        self.moved_records[rec_key] = addr
                else:
                    failed += 1
        if moved:
            self._save_cache()
            self._save_moved()
        return {"moved": moved, "failed": failed, "skipped": len(keys) - len(movable)}

    def keys_by_sender(self, addr):
        addr = (addr or "").lower()
        with self.lock:
            return [k for k, m in self.messages.items() if m.get("senderAddr") == addr]
