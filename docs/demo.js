/* MailDeck デモモード (GitHub Pages 用)
 * バックエンドの代わりに、架空のサンプルデータで /api/* を再現する。
 * 実アプリはローカルで Mail.app と連携して動く — README 参照。 */
"use strict";

(function () {
  const now = new Date();
  const d = (daysAgo, h, m) => {
    const t = new Date(now);
    t.setDate(t.getDate() - daysAgo);
    t.setHours(h, m, 0, 0);
    return t.toISOString().slice(0, 19);
  };

  // ---- 架空のサンプルメール ----
  let messages = [
    { key: "d1", account: "tsdesign.ltd@gmail.com", senderName: "田中 太郎", senderAddr: "taro.tanaka@example.co.jp", subject: "打ち合わせ日程の件", date: d(0, 9, 24), read: false, cls: "ok", reasons: [] },
    { key: "d2", account: "tsdesign.ltd@gmail.com", senderName: "田中 太郎", senderAddr: "taro.tanaka@example.co.jp", subject: "Re: 見積書のご確認", date: d(1, 15, 2), read: true, cls: "ok", reasons: [] },
    { key: "d3", account: "tsdesign.ltd@gmail.com", senderName: "田中 太郎", senderAddr: "taro.tanaka@example.co.jp", subject: "資料ありがとうございました", date: d(3, 11, 40), read: true, cls: "ok", reasons: [] },
    { key: "d4", account: "tsdesign.ltd@gmail.com", senderName: "佐藤 花子", senderAddr: "hanako@design-studio.example.jp", subject: "ロゴ案の修正版を送ります", date: d(0, 8, 5), read: false, cls: "ok", reasons: [] },
    { key: "d5", account: "tsdesign.ltd@gmail.com", senderName: "佐藤 花子", senderAddr: "hanako@design-studio.example.jp", subject: "納品データの形式について", date: d(2, 17, 30), read: true, cls: "ok", reasons: [] },
    { key: "d6", account: "tsdesign.ltd@gmail.com", senderName: "山本印刷", senderAddr: "order@yamamoto-print.example.jp", subject: "【受注確認】パンフレット 1,000部", date: d(1, 10, 12), read: true, cls: "ok", reasons: [] },
    { key: "d7", account: "monoralbikes@gmail.com", senderName: "鈴木 一郎", senderAddr: "ichiro.suzuki@example.com", subject: "週末のライドの件", date: d(4, 20, 45), read: true, cls: "ok", reasons: [] },
    { key: "d8", account: "monoralbikes@gmail.com", senderName: "Example ストア", senderAddr: "newsletter@store.example.com", subject: "夏のセールが始まりました", date: d(2, 7, 0), read: false, cls: "ok", reasons: [] },
    { key: "s1", account: "tsdesign.ltd@gmail.com", senderName: "Amazon サポート", senderAddr: "x93k2a1@secure-verify.top", subject: "【重要】アカウントが停止されました。本人確認が必要です", date: d(0, 3, 12), read: false, cls: "spam",
      reasons: ["「amazon」を名乗るが正規ドメインではない (secure-verify.top)", "アカウント停止を装うフィッシング", "迷惑メールに多いドメイン (secure-verify.top)"] },
    { key: "s2", account: "monoralbikes@gmail.com", senderName: "宝くじ事務局", senderAddr: "prize8821k@lucky-winner.xyz", subject: "おめでとうございます!1億円当選のお知らせ!!!", date: d(1, 4, 55), read: false, cls: "spam",
      reasons: ["当選・懸賞系の件名", "迷惑メールに多いドメイン (lucky-winner.xyz)", "記号の多い件名"] },
    { key: "g1", account: "monoralbikes@gmail.com", senderName: "CAMP GEAR SHOP", senderAddr: "info@campgear.shop", subject: "フォトコンテスト結果発表!", date: d(3, 12, 0), read: true, cls: "grey",
      reasons: ["迷惑メールに多いドメイン (campgear.shop)"] },
    { key: "g2", account: "tsdesign.ltd@gmail.com", senderName: "投資セミナー事務局", senderAddr: "seminar@invest-info.example.net", subject: "無料オンラインセミナーのご案内", date: d(5, 9, 30), read: true, cls: "grey",
      reasons: ["「無料」を強調する件名"] },
  ];

  const bodies = {
    d1: "田中です。お世話になっております。\n\n来週の打ち合わせですが、火曜 14:00 か水曜 10:00 はいかがでしょうか。\nご都合をお知らせください。\n\n--\n田中 太郎",
    d4: "佐藤です。\n\nロゴ案、いただいたフィードバックを反映した修正版を添付します。\nB案の色味を少し落ち着かせました。ご確認ください。",
    d7: "今週末、いつものコースでライドどうですか?\n天気は良さそうです。",
  };

  let settings = {
    trustedSenders: [], trustedDomains: [], blockedSenders: [], blockedDomains: [],
    favorites: ["taro.tanaka@example.co.jp"], dismissedFavorites: [],
    autoFavorite: true, perAccountLimit: 100,
  };
  const autoFavs = ["hanako@design-studio.example.jp"];

  function overview() {
    const judged = messages.map((m) => {
      let cls = m.cls;
      if (settings.blockedSenders.includes(m.senderAddr)) cls = "spam";
      if (settings.trustedSenders.includes(m.senderAddr) || settings.favorites.includes(m.senderAddr)) cls = "ok";
      return { ...m, source: "demo", spamClass: cls, spamScore: cls === "spam" ? 12 : cls === "grey" ? 5 : 0, spamReasons: m.reasons };
    }).sort((a, b) => (b.date || "").localeCompare(a.date || ""));

    const threads = {};
    for (const m of judged) {
      if (m.spamClass === "spam") continue;
      const t = threads[m.senderAddr] || (threads[m.senderAddr] = {
        addr: m.senderAddr, name: m.senderName, unread: 0, count: 0, latest: "", latestSubject: "", messages: [],
      });
      t.count++;
      if (!m.read) t.unread++;
      if ((m.date || "") > t.latest) { t.latest = m.date; t.latestSubject = m.subject; t.name = m.senderName; }
      t.messages.push(m);
    }
    const threadList = Object.values(threads).sort((a, b) => b.latest.localeCompare(a.latest));

    const favorites = [];
    for (const addr of settings.favorites) {
      const t = threads[addr];
      favorites.push({ addr, name: t ? t.name : addr, unread: t ? t.unread : 0, auto: false, latest: t ? t.latest : "" });
    }
    if (settings.autoFavorite) {
      for (const addr of autoFavs) {
        if (settings.favorites.includes(addr) || settings.dismissedFavorites.includes(addr)) continue;
        const t = threads[addr];
        if (t) favorites.push({ addr, name: t.name, unread: t.unread, auto: true, latest: t.latest });
      }
    }

    return {
      threads: threadList, favorites,
      spam: judged.filter((m) => m.spamClass === "spam"),
      grey: judged.filter((m) => m.spamClass === "grey"),
      totalMessages: judged.length, settings,
      accounts: [...new Set(messages.map((m) => m.account))].sort(),
      sync: { running: false, mode: "demo", progress: "", lastSync: d(0, 8, 0), error: null },
      fastMode: false, aiAvailable: false, spamMailbox: "各アカウントの迷惑メールフォルダ",
    };
  }

  // ---- fetch を差し替え ----
  const realFetch = window.fetch.bind(window);
  window.fetch = async function (url, opts) {
    const u = String(url);
    const isApi = u.startsWith("/api/") || u.includes("/api/");
    if (!isApi) return realFetch(url, opts);
    const path = u.slice(u.indexOf("/api/"));
    const body = opts && opts.body ? JSON.parse(opts.body) : {};
    const json = (obj) => new Response(JSON.stringify(obj), { headers: { "Content-Type": "application/json" } });
    await new Promise((r) => setTimeout(r, 120)); // それっぽい待ち時間

    if (path.startsWith("/api/overview")) return json(overview());
    if (path.startsWith("/api/sync/status")) return json(overview().sync);
    if (path.startsWith("/api/sync")) return json({ started: false, status: overview().sync });
    if (path.startsWith("/api/message")) {
      const key = new URLSearchParams(path.split("?")[1] || "").get("key");
      return json({ key, content: bodies[key] || "(デモ用のサンプル本文です)\n\nローカルで実行すると、Mail.app から実際の本文を取得します。" });
    }
    if (path.startsWith("/api/spam/move")) {
      const keys = body.keys || [];
      messages = messages.filter((m) => !keys.includes(m.key));
      for (const a of body.senders || []) {
        if (!settings.blockedSenders.includes(a)) settings.blockedSenders.push(a);
      }
      return json({ moved: keys.length, failed: 0, skipped: 0 });
    }
    if (path.startsWith("/api/spam/trust")) {
      const a = body.sender;
      if (a && !settings.trustedSenders.includes(a)) settings.trustedSenders.push(a);
      settings.blockedSenders = settings.blockedSenders.filter((x) => x !== a);
      return json({ ok: true });
    }
    if (path.startsWith("/api/spam/block")) {
      const a = body.sender;
      if (a && !settings.blockedSenders.includes(a)) settings.blockedSenders.push(a);
      const n = messages.filter((m) => m.senderAddr === a).length;
      messages = messages.filter((m) => m.senderAddr !== a);
      return json({ ok: true, moved: n, failed: 0, skipped: 0 });
    }
    if (path.startsWith("/api/spam/ai")) return json({ available: false });
    if (path.startsWith("/api/favorites")) {
      const a = body.sender;
      if (body.action === "pin") {
        if (!settings.favorites.includes(a)) settings.favorites.push(a);
        settings.dismissedFavorites = settings.dismissedFavorites.filter((x) => x !== a);
      } else if (body.action === "unpin") {
        settings.favorites = settings.favorites.filter((x) => x !== a);
      } else if (body.action === "dismiss") {
        if (!settings.dismissedFavorites.includes(a)) settings.dismissedFavorites.push(a);
        settings.favorites = settings.favorites.filter((x) => x !== a);
      }
      return json({ ok: true });
    }
    if (path.startsWith("/api/settings")) {
      Object.assign(settings, body);
      return json({ ok: true, settings });
    }
    if (path.startsWith("/api/accounts")) return json({ accounts: [] });
    return json({ error: "not found" }, 404);
  };

  // ---- デモバナー ----
  document.addEventListener("DOMContentLoaded", () => {
    const bar = document.createElement("div");
    bar.style.cssText = "background:#fff3cd;color:#664d03;padding:8px 16px;font-size:12.5px;text-align:center;border-bottom:1px solid #ffe69c;";
    bar.innerHTML = "🧪 これは<b>サンプルデータによるデモ</b>です。実際のメール整理は、リポジトリを clone してローカルで <code>python3 server.py</code> を実行してください(macOS + Mail.app が必要)。";
    document.body.prepend(bar);
    const sync = document.getElementById("syncBtn");
    if (sync) sync.title = "デモモードでは同期は動作しません";
  });
})();
