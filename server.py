# -*- coding: utf-8 -*-
"""MailDeck サーバー。

macOS 標準の Python 3 だけで動く (追加インストール不要)。
起動:  python3 server.py  →  http://localhost:8765
"""
import json
import os
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import rules
from mail_store import MailStore, run_osascript, FIELD_SEP, REC_SEP, DATA_DIR, CUTOFF_DAYS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(BASE_DIR, "public")
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
PORT = 8765

SPAM_MAILBOX = "MailDeck迷惑候補"

DEFAULT_SETTINGS = {
    "trustedSenders": [],
    "trustedDomains": [],
    "blockedSenders": [],
    "blockedDomains": [],
    "favorites": [],            # 手動追加した「よく使う相手」
    "dismissedFavorites": [],   # 自動追加を拒否した相手
    "autoFavorite": True,
    "perAccountLimit": 300,  # 1アカウントの最大取得件数 (過去1ヶ月分の安全上限)
    "excludedAccounts": [],  # 同期対象から外すアカウント
}

store = MailStore()
settings_lock = threading.Lock()


def load_settings():
    with settings_lock:
        if os.path.exists(SETTINGS_PATH):
            try:
                with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                    s = json.load(f)
                merged = dict(DEFAULT_SETTINGS)
                merged.update(s)
                return merged
            except Exception:
                pass
        return dict(DEFAULT_SETTINGS)


def save_settings(s):
    with settings_lock:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = SETTINGS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
        os.replace(tmp, SETTINGS_PATH)


def claude_cli():
    return shutil.which("claude")


def apply_restored_senders(settings):
    """Mail.app で「迷惑メールではない」と指定(受信トレイへ戻)された差出人を
    ブロックリストから外し、信頼リストへ移す。"""
    restored = store.consume_restored()
    if not restored:
        return settings
    changed = False
    for addr in restored:
        if addr in settings["blockedSenders"]:
            settings["blockedSenders"].remove(addr)
            changed = True
        if addr not in settings["trustedSenders"]:
            settings["trustedSenders"].append(addr)
            changed = True
    if changed:
        save_settings(settings)
    return settings


def build_overview():
    """UI 用のまとめ: 差出人別スレッド・迷惑候補・よく使う相手。"""
    settings = apply_restored_senders(load_settings())
    excluded = set(settings.get("excludedAccounts", []))
    messages = [m for m in store.all_messages()
                if m.get("account") not in excluded]
    # 受信(相手から)と送信(自分から)を分ける。迷惑判定・統計は受信のみで行う。
    received = [m for m in messages if not m.get("fromMe")]
    sent = [m for m in messages if m.get("fromMe")]
    sender_stats = rules.build_sender_stats(received, store.replied_to)

    judged = []
    for m in received:
        score, reasons = rules.judge_message(m, settings, sender_stats)
        cls = rules.classify(score)
        mm = dict(m)
        mm["spamScore"] = score
        mm["spamClass"] = cls
        mm["spamReasons"] = reasons
        # 会話相手 = 差出人。フロントのスレッド分けと左右振り分けに使う。
        mm["partyAddr"] = m["senderAddr"]
        mm["partyName"] = m["senderName"]
        mm["fromMe"] = False
        judged.append(mm)
    judged.sort(key=lambda x: x.get("date") or "", reverse=True)

    # 差出人別スレッド(迷惑判定されたものは除く)
    threads = {}
    for m in judged:
        if m["spamClass"] == "spam":
            continue
        addr = m["senderAddr"]
        t = threads.setdefault(addr, {
            "addr": addr, "name": m["senderName"],
            "unread": 0, "count": 0, "latest": "", "latestSubject": "",
            "messages": [],
        })
        t["count"] += 1
        if not m.get("read"):
            t["unread"] += 1
        if (m.get("date") or "") > t["latest"]:
            t["latest"] = m.get("date") or ""
            t["latestSubject"] = m.get("subject") or ""
            t["name"] = m["senderName"]
        t["messages"].append(m)

    # 送信済みメールを「相手(宛先)」ごとの既存スレッドに混ぜる。
    # 会話のある相手にだけ足す(送信のみの相手で新規スレッドは作らない)。
    for m in sent:
        t = threads.get(m.get("toAddr"))
        if not t:
            continue
        mm = dict(m)
        mm["spamScore"] = 0
        mm["spamClass"] = "ok"
        mm["spamReasons"] = []
        mm["partyAddr"] = m["toAddr"]
        mm["partyName"] = t["name"]
        mm["fromMe"] = True
        t["count"] += 1
        if (m.get("date") or "") > t["latest"]:
            t["latest"] = m.get("date") or ""
            t["latestSubject"] = m.get("subject") or ""
        t["messages"].append(mm)
    thread_list = sorted(threads.values(), key=lambda t: t["latest"], reverse=True)

    # よく使う相手 (手動 + 自動)
    auto = rules.auto_favorites(sender_stats, settings) if settings.get("autoFavorite") else []
    fav_addrs = list(settings.get("favorites", []))
    favorites = []
    seen = set()
    for addr in fav_addrs:
        st = sender_stats.get(addr, {"addr": addr, "name": addr})
        favorites.append({"addr": addr, "name": st.get("name", addr),
                          "unread": st.get("unread", 0), "auto": False,
                          "latest": st.get("latest", "")})
        seen.add(addr)
    for a in auto:
        if a["addr"] in seen:
            continue
        st = sender_stats.get(a["addr"], {})
        favorites.append({"addr": a["addr"], "name": st.get("name", a["addr"]),
                          "unread": st.get("unread", 0), "auto": True,
                          "latest": st.get("latest", ""), "score": a["score"]})

    spam = [m for m in judged if m["spamClass"] == "spam"]
    grey = [m for m in judged if m["spamClass"] == "grey"]

    accounts = sorted({m.get("account") for m in judged if m.get("account")})
    # 設定画面用: Mail.app に存在する全アカウント (未同期・除外中も含む)
    all_accounts = sorted(set(store.load_account_map().keys()) | set(accounts) | excluded)

    return {
        "threads": thread_list,
        "favorites": favorites,
        "spam": spam,
        "grey": grey,
        "accounts": accounts,
        "allAccounts": all_accounts,
        "totalMessages": len(judged),
        "settings": settings,
        "sync": store.status.snapshot(),
        "fastMode": store.sqlite_available(),
        "aiAvailable": claude_cli() is not None,
        "spamMailbox": "各アカウントの迷惑メールフォルダ",
        "cutoffDays": CUTOFF_DAYS,
    }


def refresh_account_map():
    """AppleScript でアカウント一覧を取り、address→アカウント名対応を保存。"""
    raw = run_osascript("list_accounts.applescript", [], timeout=900)
    mapping = {}
    for rec in raw.split(REC_SEP):
        if not rec.strip():
            continue
        parts = rec.split(FIELD_SEP)
        if len(parts) == 3:
            mapping[parts[0]] = parts[0]
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, "accounts.json"), "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False)
    return mapping


def ai_judge(keys):
    """グレーゾーンのメールを Claude CLI で判定する (CLI がある場合のみ)。"""
    cli = claude_cli()
    if not cli:
        return {"available": False}
    messages = {m["key"]: m for m in store.all_messages()}
    items = []
    for k in keys:
        m = messages.get(k)
        if m:
            items.append({"key": k, "sender": m["senderName"],
                          "addr": m["senderAddr"], "subject": m["subject"]})
    if not items:
        return {"available": True, "verdicts": {}}
    prompt = (
        "次のメール一覧について、それぞれ迷惑メール(スパム・フィッシング・過剰な宣伝)かどうか判定してください。\n"
        "出力は JSON のみ: {\"verdicts\": {\"<key>\": \"spam\" | \"ok\"}}\n\n"
        + json.dumps(items, ensure_ascii=False)
    )
    proc = subprocess.run([cli, "-p", prompt, "--output-format", "text"],
                          capture_output=True, text=True, timeout=300)
    try:
        txt = proc.stdout.strip()
        start = txt.find("{")
        end = txt.rfind("}")
        data = json.loads(txt[start:end + 1])
        return {"available": True, "verdicts": data.get("verdicts", {})}
    except Exception as e:
        return {"available": True, "error": "AI応答を解釈できませんでした: %s" % e}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass  # 静かに

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, rel):
        path = os.path.normpath(os.path.join(PUBLIC_DIR, rel.lstrip("/")))
        if not path.startswith(PUBLIC_DIR) or not os.path.isfile(path):
            self.send_error(404)
            return
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".svg": "image/svg+xml",
        }.get(os.path.splitext(path)[1], "application/octet-stream")
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        return {}

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/" or u.path == "/index.html":
            return self._file("index.html")
        if u.path.startswith("/api/"):
            return self.api_get(u)
        return self._file(u.path)

    def do_POST(self):
        u = urlparse(self.path)
        try:
            body = self._read_body()
        except Exception:
            return self._json({"error": "invalid json"}, 400)
        try:
            return self.api_post(u, body)
        except Exception as e:
            return self._json({"error": str(e)}, 500)

    def api_get(self, u):
        if u.path == "/api/overview":
            return self._json(build_overview())
        if u.path == "/api/sync/status":
            return self._json(store.status.snapshot())
        if u.path == "/api/message":
            qs = parse_qs(u.query)
            key = (qs.get("key") or [""])[0]
            try:
                content = store.get_content(key)
            except Exception as e:
                return self._json({"error": str(e)}, 500)
            return self._json({"key": key, "content": content})
        return self._json({"error": "not found"}, 404)

    def api_post(self, u, body):
        settings = load_settings()

        if u.path == "/api/sync":
            started = store.sync(per_account_limit=int(settings.get("perAccountLimit", 300)),
                                 excluded=settings.get("excludedAccounts", []))
            return self._json({"started": started, "status": store.status.snapshot()})

        if u.path == "/api/sync/sender":
            addr = (body.get("addr") or "").strip()
            if not addr:
                return self._json({"error": "addr required"}, 400)
            if store.status.running:
                return self._json({"busy": True, "reason": "full-sync"})
            try:
                result = store.sync_sender(addr, excluded=settings.get("excludedAccounts", []))
            except Exception as e:
                return self._json({"error": str(e)}, 500)
            return self._json(result)

        if u.path == "/api/spam/move":
            keys = body.get("keys", [])
            result = store.move_to_junk(keys)
            # 仕訳した差出人はブロックリストに学習させる
            if body.get("block", True):
                addrs = set(body.get("senders", []))
                for a in addrs:
                    if a and a not in settings["blockedSenders"]:
                        settings["blockedSenders"].append(a)
                save_settings(settings)
            return self._json(result)

        if u.path == "/api/spam/trust":
            addr = body.get("sender", "")
            if addr:
                if addr not in settings["trustedSenders"]:
                    settings["trustedSenders"].append(addr)
                for lst in ("blockedSenders",):
                    if addr in settings[lst]:
                        settings[lst].remove(addr)
                save_settings(settings)
            return self._json({"ok": True})

        if u.path == "/api/spam/block":
            addr = body.get("sender", "")
            if not addr:
                return self._json({"error": "sender required"}, 400)
            if addr not in settings["blockedSenders"]:
                settings["blockedSenders"].append(addr)
                save_settings(settings)
            # その差出人の受信済みメールを、各アカウントの迷惑メールフォルダへ移動
            keys = store.keys_by_sender(addr)
            result = {"moved": 0, "failed": 0, "skipped": 0}
            if keys:
                try:
                    result = store.move_to_junk(keys)
                except Exception as e:
                    result = {"moved": 0, "failed": len(keys), "skipped": 0, "error": str(e)}
            result["ok"] = True
            return self._json(result)

        if u.path == "/api/spam/ai":
            return self._json(ai_judge(body.get("keys", [])))

        if u.path == "/api/favorites":
            addr = body.get("sender", "")
            action = body.get("action", "")
            if not addr:
                return self._json({"error": "sender required"}, 400)
            if action == "pin":
                if addr not in settings["favorites"]:
                    settings["favorites"].append(addr)
                if addr in settings["dismissedFavorites"]:
                    settings["dismissedFavorites"].remove(addr)
            elif action == "unpin":
                if addr in settings["favorites"]:
                    settings["favorites"].remove(addr)
            elif action == "dismiss":
                if addr not in settings["dismissedFavorites"]:
                    settings["dismissedFavorites"].append(addr)
                if addr in settings["favorites"]:
                    settings["favorites"].remove(addr)
            save_settings(settings)
            return self._json({"ok": True})

        if u.path == "/api/settings":
            for k in DEFAULT_SETTINGS:
                if k in body:
                    settings[k] = body[k]
            save_settings(settings)
            return self._json({"ok": True, "settings": settings})

        if u.path == "/api/accounts/refresh":
            mapping = refresh_account_map()
            return self._json({"accounts": list(mapping.keys())})

        return self._json({"error": "not found"}, 404)


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("MailDeck: http://localhost:%d  (fastMode=%s)" % (PORT, store.sqlite_available()))
    server.serve_forever()


if __name__ == "__main__":
    main()
