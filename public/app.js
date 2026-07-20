/* MailDeck フロントエンド — サムネイルタイル型ダッシュボード */
"use strict";

let state = {
  overview: null,
  account: "all",     // アカウント切替 ("all" or アカウント名)
  activeSender: null,
  sortKey: "latest",  // 全員リストの並び: latest | name | addr
  sortDir: -1,        // -1: 降順, 1: 昇順
  tab: "inbox",
  syncTimer: null,
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

/* ---------- utilities ---------- */
function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
function avatarColor(addr) {
  let h = 0;
  for (let i = 0; i < addr.length; i++) h = (h * 31 + addr.charCodeAt(i)) >>> 0;
  return `hsl(${h % 360}, 55%, 45%)`;
}
function initials(name) {
  const t = (name || "?").trim();
  return t ? t[0].toUpperCase() : "?";
}
function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d)) return "";
  const now = new Date();
  if (d.toDateString() === now.toDateString())
    return d.toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit" });
  if (d.getFullYear() === now.getFullYear()) return `${d.getMonth() + 1}/${d.getDate()}`;
  return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()}`;
}
function fmtDay(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return "";
  return d.toLocaleDateString("ja-JP", { year: "numeric", month: "long", day: "numeric", weekday: "short" });
}
let toastEl = null;
function toast(msg) {
  if (!toastEl) {
    toastEl = document.createElement("div");
    toastEl.className = "toast";
    document.body.appendChild(toastEl);
  }
  toastEl.textContent = msg;
  toastEl.classList.add("show");
  setTimeout(() => toastEl.classList.remove("show"), 2600);
}
async function api(path, opts) {
  const res = await fetch(path, opts);
  return res.json();
}
async function post(path, body) {
  return api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
}

/* ---------- tabs ---------- */
$$(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    state.tab = btn.dataset.tab;
    $$(".tab").forEach((b) => b.classList.toggle("active", b === btn));
    ["inbox", "spam", "settings"].forEach((t) => {
      $("#view-" + t).classList.toggle("hidden", t !== state.tab);
    });
  });
});

/* ---------- アカウントフィルタとグルーピング ---------- */
function filteredMessages() {
  const ov = state.overview;
  if (!ov) return [];
  const msgs = [];
  for (const t of ov.threads) {
    for (const m of t.messages) {
      if (state.account === "all" || m.account === state.account) msgs.push(m);
    }
  }
  return msgs;
}

function buildThreads(msgs) {
  const threads = {};
  for (const m of msgs) {
    const t = threads[m.senderAddr] || (threads[m.senderAddr] = {
      addr: m.senderAddr, name: m.senderName,
      unread: 0, count: 0, latest: "", latestSubject: "", messages: [],
    });
    t.count++;
    if (!m.read) t.unread++;
    if ((m.date || "") > t.latest) {
      t.latest = m.date || "";
      t.latestSubject = m.subject || "";
      t.name = m.senderName;
    }
    t.messages.push(m);
  }
  return threads;
}

/* ---------- data load ---------- */
async function loadOverview() {
  const ov = await api("/api/overview");
  state.overview = ov;
  renderAccountSelect();
  renderDash();
  renderSpam();
  renderSettings();
  renderSyncStatus(ov.sync);
  if (state.activeSender && !$("#threadOverlay").classList.contains("hidden")) {
    renderThread(state.activeSender);
  }
}

function renderAccountSelect() {
  const ov = state.overview;
  const sel = $("#accountSelect");
  const accounts = ov.accounts || [];
  const cur = state.account;
  sel.innerHTML = `<option value="all">すべてのアカウント</option>` +
    accounts.map((a) => `<option value="${esc(a)}" ${a === cur ? "selected" : ""}>${esc(a)}</option>`).join("");
  sel.value = accounts.includes(cur) ? cur : "all";
}
$("#accountSelect").addEventListener("change", (e) => {
  state.account = e.target.value;
  renderDash();
});

function renderSyncStatus(sync) {
  const el = $("#syncStatus");
  const btn = $("#syncBtn");
  if (sync.running) {
    el.textContent = "同期中: " + (sync.progress || "...");
    btn.disabled = true;
    if (!state.syncTimer) {
      state.syncTimer = setInterval(async () => {
        const s = await api("/api/sync/status");
        renderSyncStatus(s);
        if (!s.running) {
          clearInterval(state.syncTimer);
          state.syncTimer = null;
          loadOverview();
        }
      }, 3000);
    }
  } else {
    btn.disabled = false;
    if (sync.error) el.textContent = "エラー: " + sync.error;
    else if (sync.lastSync) el.textContent = "最終同期: " + fmtDate(sync.lastSync) + (sync.mode === "sqlite" ? " (高速)" : "");
    else el.textContent = "未同期 — 「同期」を押してください";
  }
}

$("#syncBtn").addEventListener("click", async () => {
  const r = await post("/api/sync");
  if (r.started) toast("同期を開始しました");
  renderSyncStatus(r.status);
});

/* ---------- ダッシュボード (タイル + 全員リスト) ---------- */
function renderDash() {
  const ov = state.overview;
  if (!ov) return;
  const q = ($("#senderSearch").value || "").toLowerCase();
  const match = (t) => !q || t.name.toLowerCase().includes(q) || t.addr.toLowerCase().includes(q);

  const threads = buildThreads(filteredMessages());

  // --- よく使う相手のタイル (最大20件・新着順) ---
  const favMeta = {};
  for (const f of ov.favorites) favMeta[f.addr] = f;
  let tiles = Object.keys(favMeta)
    .map((addr) => {
      const t = threads[addr];
      return {
        addr,
        name: t ? t.name : favMeta[addr].name,
        unread: t ? t.unread : 0,
        latest: t ? t.latest : "",
        auto: favMeta[addr].auto,
        present: !!t,
      };
    })
    .filter((x) => state.account === "all" || x.present)
    .filter(match)
    .sort((a, b) => (b.latest || "").localeCompare(a.latest || ""))
    .slice(0, 20);

  $("#favTiles").innerHTML = tiles.length
    ? tiles.map(tileHtml).join("")
    : `<div class="tile-empty">まだ「よく使う相手」がありません。<br>下の一覧から相手を開いて「★ よく使う相手に追加」を押すか、やり取りを重ねると自動で追加されます。</div>`;

  // --- 全員リスト (ソート可能) ---
  let rows = Object.values(threads).filter(match);
  const dir = state.sortDir;
  rows.sort((a, b) => {
    if (state.sortKey === "name") return a.name.localeCompare(b.name, "ja") * dir;
    if (state.sortKey === "addr") return a.addr.localeCompare(b.addr) * dir;
    return (a.latest || "").localeCompare(b.latest || "") * dir;
  });
  $("#allList").innerHTML = rows.map(rowHtml).join("") ||
    `<div class="tile-empty">表示できる差出人がいません</div>`;

  $$(".sort-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.sort === state.sortKey);
    const arrow = b.dataset.sort === state.sortKey ? (state.sortDir < 0 ? " ▼" : " ▲") : "";
    b.textContent = { latest: "受信日時", name: "名前", addr: "メールアドレス" }[b.dataset.sort] + arrow;
  });

  // クリックで会話を開く
  $$("#favTiles .tile, #allList .all-row").forEach((el) => {
    el.addEventListener("click", () => openThread(el.dataset.addr));
  });

  const spamTotal = ov.spam.length + ov.grey.length;
  const badge = $("#spamBadge");
  badge.classList.toggle("hidden", spamTotal === 0);
  badge.textContent = spamTotal;
}

function tileHtml(t) {
  const unread = t.unread ? `<span class="unread-dot">${t.unread}</span>` : "";
  const auto = t.auto ? `<span class="auto-mark">自動</span>` : "";
  return `
  <div class="tile" data-addr="${esc(t.addr)}">
    ${unread}
    <div class="avatar" style="background:${avatarColor(t.addr)}">${esc(initials(t.name))}</div>
    <div class="tile-name">${esc(t.name)} ${auto}</div>
    <div class="tile-sub">${esc(t.addr)}</div>
    <div class="tile-date">${fmtDate(t.latest)}</div>
  </div>`;
}

function rowHtml(t) {
  const unread = t.unread ? `<span class="unread-dot">${t.unread}</span>` : "<span></span>";
  return `
  <div class="all-row" data-addr="${esc(t.addr)}">
    ${unread}
    <div class="avatar" style="background:${avatarColor(t.addr)}">${esc(initials(t.name))}</div>
    <div class="r-name">${esc(t.name)}</div>
    <div class="r-addr">${esc(t.addr)}</div>
    <div class="r-date">${fmtDate(t.latest)}</div>
  </div>`;
}

$("#senderSearch").addEventListener("input", renderDash);
$$(".sort-btn").forEach((b) =>
  b.addEventListener("click", () => {
    if (state.sortKey === b.dataset.sort) {
      state.sortDir *= -1;
    } else {
      state.sortKey = b.dataset.sort;
      state.sortDir = b.dataset.sort === "latest" ? -1 : 1;
    }
    renderDash();
  }));

/* ---------- メッセンジャー画面 (オーバーレイ) ---------- */
function openThread(addr) {
  state.activeSender = addr;
  $("#threadOverlay").classList.remove("hidden");
  renderThread(addr);
}
function backToList() {
  $("#threadOverlay").classList.add("hidden");
  state.activeSender = null;
  // 受信タブに戻す
  state.tab = "inbox";
  $$(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === "inbox"));
  ["inbox", "spam", "settings"].forEach((t) => {
    $("#view-" + t).classList.toggle("hidden", t !== "inbox");
  });
  renderDash();
}
$("#backBtn").addEventListener("click", backToList);
$(".logo").addEventListener("click", backToList);

function renderThread(addr) {
  const ov = state.overview;
  if (!ov) return;
  const threads = buildThreads(filteredMessages());
  const t = threads[addr];
  $("#threadName").textContent = t ? t.name : addr;
  $("#threadAddr").textContent = addr;

  const favSet = new Set(ov.settings.favorites || []);
  const pinned = favSet.has(addr);
  $("#pinBtn").textContent = pinned ? "★ よく使う相手から外す" : "★ よく使う相手に追加";
  $("#pinBtn").dataset.action = pinned ? "unpin" : "pin";

  if (!t) {
    $("#bubbles").innerHTML = `<div class="empty-state"><p>この差出人からの最近のメールはありません</p></div>`;
    return;
  }
  const msgs = [...t.messages].sort((a, b) => (a.date || "").localeCompare(b.date || ""));
  let html = "";
  let lastDay = "";
  for (const m of msgs) {
    const day = (m.date || "").slice(0, 10);
    if (day && day !== lastDay) {
      html += `<div class="day-sep">${esc(fmtDay(m.date))}</div>`;
      lastDay = day;
    }
    const time = m.date ? new Date(m.date).toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit" }) : "";
    const acct = state.account === "all" && m.account ? ` ・ ${esc(m.account)}` : "";
    html += `
    <div class="bubble ${m.read ? "" : "unread"}" data-key="${esc(m.key)}" data-source="${esc(m.source)}">
      <div class="b-subject">${esc(m.subject)}</div>
      <div class="b-time">${time}${m.read ? "" : " ・未読"}${acct}</div>
      <div class="b-content"></div>
    </div>`;
  }
  $("#bubbles").innerHTML = html;
  $("#bubbles").scrollTop = $("#bubbles").scrollHeight;
  $$("#bubbles .bubble").forEach((el) => {
    el.addEventListener("click", () => toggleBubbleContent(el));
  });
}

async function toggleBubbleContent(el) {
  const slot = el.querySelector(".b-content");
  if (slot.dataset.loaded) {
    slot.innerHTML = slot.innerHTML ? "" : slot.dataset.html || "";
    return;
  }
  if (el.dataset.source === "sqlite") {
    slot.innerHTML = `<div class="b-loading">本文表示は Mail.app で開いてください(高速モードでは一覧のみ)</div>`;
    slot.dataset.loaded = "1";
    return;
  }
  slot.innerHTML = `<div class="b-loading">本文を読み込み中...</div>`;
  const r = await api("/api/message?key=" + encodeURIComponent(el.dataset.key));
  const body = r.content ? esc(r.content.trim().slice(0, 8000)) : "(本文を取得できませんでした)";
  const html = `<div class="b-body">${body}</div>`;
  slot.innerHTML = html;
  slot.dataset.html = html;
  slot.dataset.loaded = "1";
}

$("#pinBtn").addEventListener("click", async () => {
  if (!state.activeSender) return;
  await post("/api/favorites", { sender: state.activeSender, action: $("#pinBtn").dataset.action });
  toast($("#pinBtn").dataset.action === "pin" ? "よく使う相手に追加しました" : "よく使う相手から外しました");
  loadOverview();
});

$("#blockBtn").addEventListener("click", async () => {
  if (!state.activeSender) return;
  $("#blockBtn").disabled = true;
  try {
    const r = await post("/api/spam/block", { sender: state.activeSender });
    let msg = "ブロックしました。";
    if (r.moved) msg += `受信済みの ${r.moved} 件を迷惑メールフォルダへ移動しました。`;
    if (r.failed) msg += `(${r.failed} 件は移動できませんでした)`;
    toast(msg);
  } finally {
    $("#blockBtn").disabled = false;
  }
  $("#threadOverlay").classList.add("hidden");
  loadOverview();
});

/* ---------- spam view ---------- */
function mailItemHtml(m, cls, checked) {
  const reasons = (m.spamReasons || [])
    .map((r) => `<span class="reason-chip">${esc(r)}</span>`).join("");
  const actions = cls === "grey"
    ? `<div class="mail-actions">
         <button class="btn small danger act-spam" data-key="${esc(m.key)}" data-addr="${esc(m.senderAddr)}">迷惑</button>
         <button class="btn small act-ok" data-addr="${esc(m.senderAddr)}">問題なし</button>
         <span class="ai-verdict" data-ai="${esc(m.key)}"></span>
       </div>`
    : "";
  return `
  <div class="mail-item ${cls}">
    <input type="checkbox" class="spam-check" data-key="${esc(m.key)}" data-addr="${esc(m.senderAddr)}" ${checked ? "checked" : ""}>
    <div class="mail-main">
      <div class="mail-subject">${esc(m.subject)}</div>
      <div class="mail-from">${esc(m.senderName)} &lt;${esc(m.senderAddr)}&gt; ・ ${fmtDate(m.date)} ・ スコア ${m.spamScore}</div>
      <div class="mail-reasons">${reasons}</div>
    </div>
    ${actions}
  </div>`;
}

function renderSpam() {
  const ov = state.overview;
  if (!ov) return;
  $(".mbname").textContent = ov.spamMailbox;
  $("#spamCount").textContent = `${ov.spam.length} 件`;
  $("#greyCount").textContent = `${ov.grey.length} 件`;
  $("#spamItems").innerHTML = ov.spam.length
    ? ov.spam.map((m) => mailItemHtml(m, "spam", true)).join("")
    : `<p class="hint">高確度の迷惑メールはありません 🎉</p>`;
  $("#greyItems").innerHTML = ov.grey.length
    ? ov.grey.map((m) => mailItemHtml(m, "grey", false)).join("")
    : `<p class="hint">グレーゾーンのメールはありません</p>`;
  $("#aiJudgeBtn").classList.toggle("hidden", !(ov.aiAvailable && ov.grey.length));

  $$("#greyItems .act-spam").forEach((b) =>
    b.addEventListener("click", async () => {
      const r = await post("/api/spam/move", { keys: [b.dataset.key], senders: [b.dataset.addr], block: true });
      toast(moveResultText(r));
      loadOverview();
    }));
  $$("#greyItems .act-ok").forEach((b) =>
    b.addEventListener("click", async () => {
      await post("/api/spam/trust", { sender: b.dataset.addr });
      toast("信頼リストに追加しました");
      loadOverview();
    }));
}

function moveResultText(r) {
  let msg = `${r.moved} 件を仕訳しました`;
  if (r.failed) msg += ` (${r.failed} 件失敗)`;
  if (r.skipped) msg += ` (${r.skipped} 件は移動対象外)`;
  return msg;
}

$("#checkAllSpam").addEventListener("change", (e) => {
  $$("#spamItems .spam-check").forEach((c) => (c.checked = e.target.checked));
});

$("#moveSpamBtn").addEventListener("click", async () => {
  const checks = $$(".spam-check").filter((c) => c.checked);
  if (!checks.length) return toast("仕訳するメールを選択してください");
  const keys = checks.map((c) => c.dataset.key);
  const senders = [...new Set(checks.map((c) => c.dataset.addr))];
  $("#moveSpamBtn").disabled = true;
  try {
    const r = await post("/api/spam/move", { keys, senders, block: true });
    toast(moveResultText(r));
  } finally {
    $("#moveSpamBtn").disabled = false;
  }
  loadOverview();
});

$("#aiJudgeBtn").addEventListener("click", async () => {
  const keys = (state.overview.grey || []).map((m) => m.key);
  $("#aiJudgeBtn").disabled = true;
  toast("AI判定中...");
  try {
    const r = await post("/api/spam/ai", { keys });
    if (!r.available) return toast("Claude CLI が見つかりません");
    if (r.error) return toast(r.error);
    let n = 0;
    for (const [key, v] of Object.entries(r.verdicts || {})) {
      const el = document.querySelector(`[data-ai="${CSS.escape(key)}"]`);
      if (el) {
        el.textContent = v === "spam" ? "AI: 迷惑" : "AI: 問題なし";
        el.className = "ai-verdict " + (v === "spam" ? "spam" : "ok");
        n++;
      }
    }
    toast(`AI判定が完了しました (${n} 件)`);
  } finally {
    $("#aiJudgeBtn").disabled = false;
  }
});

/* ---------- settings ---------- */
function chipHtml(addr, listName) {
  return `<span class="chip">${esc(addr)}<button data-list="${listName}" data-addr="${esc(addr)}" title="削除">✕</button></span>`;
}
function renderSettings() {
  const ov = state.overview;
  if (!ov) return;
  const s = ov.settings;
  $("#autoFavToggle").checked = !!s.autoFavorite;
  $("#limitSelect").value = String(s.perAccountLimit || 100);
  $("#modeInfo").textContent = ov.fastMode
    ? "高速モード: Mail のローカルデータベースを直接読んでいます。"
    : "AppleScriptモード: Mail.app 経由で取得しています。高速化するには README の手順でフルディスクアクセスを許可してください。";
  $("#trustCount").textContent = `${(s.trustedSenders || []).length} 件`;
  $("#blockCount").textContent = `${(s.blockedSenders || []).length} 件`;
  $("#trustList").innerHTML = (s.trustedSenders || []).map((a) => chipHtml(a, "trustedSenders")).join("") || `<span class="hint">まだありません</span>`;
  $("#blockList").innerHTML = (s.blockedSenders || []).map((a) => chipHtml(a, "blockedSenders")).join("") || `<span class="hint">まだありません</span>`;

  $$(".chip button").forEach((b) =>
    b.addEventListener("click", async () => {
      const list = b.dataset.list;
      const arr = (state.overview.settings[list] || []).filter((x) => x !== b.dataset.addr);
      await post("/api/settings", { [list]: arr });
      loadOverview();
    }));
}
$("#autoFavToggle").addEventListener("change", async (e) => {
  await post("/api/settings", { autoFavorite: e.target.checked });
  loadOverview();
});
$("#limitSelect").addEventListener("change", async (e) => {
  await post("/api/settings", { perAccountLimit: parseInt(e.target.value, 10) });
});

/* ---------- boot ---------- */
loadOverview().then(() => {
  const ov = state.overview;
  if (ov && ov.totalMessages === 0 && !ov.sync.running) {
    post("/api/sync").then(() => loadOverview());
  }
});
