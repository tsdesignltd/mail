# -*- coding: utf-8 -*-
"""迷惑メール判定(ルールベース)と重要差出人スコアリング。

判定結果: score >= SPAM_THRESHOLD → 迷惑(高確度)
          GREY_THRESHOLD <= score < SPAM_THRESHOLD → グレーゾーン(要確認)
          それ未満 → 通常
"""
import math
import re
from datetime import datetime

SPAM_THRESHOLD = 8
GREY_THRESHOLD = 4

SUSPICIOUS_TLDS = (
    ".top", ".xyz", ".icu", ".click", ".work", ".loan", ".win", ".bid",
    ".vip", ".shop", ".rest", ".monster", ".buzz", ".cfd", ".sbs", ".bond",
)

SPAM_SUBJECT_PATTERNS = [
    (r"当選|おめでとうございます.{0,10}(賞|プレゼント)", "当選・懸賞系の件名"),
    (r"無料|タダで|0円", "「無料」を強調する件名"),
    (r"副業|在宅ワーク|高収入|日給|月収\d+万", "副業・高収入勧誘"),
    (r"出会い|人妻|熟女|セフレ|アダルト", "出会い系・アダルト"),
    (r"ビットコイン|仮想通貨.{0,10}(投資|儲)|バイナリー", "投資・仮想通貨勧誘"),
    (r"(料金|利用料).{0,8}(未納|滞納|請求)", "架空請求の典型パターン"),
    (r"(アカウント|カード|お支払い).{0,15}(停止|凍結|ロック|無効|確認)", "アカウント停止を装うフィッシング"),
    (r"(セキュリティ|不正).{0,10}(警告|アラート|検出)", "セキュリティ警告を装う件名"),
    (r"本人確認|認証.{0,6}(必要|期限)", "本人確認を迫る件名"),
    (r"最終(通知|警告)|緊急|至急.{0,6}(対応|確認)", "緊急性を煽る件名"),
    (r"viagra|casino|lottery|winner|prize|crypto\s*(profit|invest)", "英語スパムの典型語"),
    (r"クリック(して)?(ください|下さい).{0,10}(こちら|URL)", "クリック誘導"),
]

# ブランド詐称チェック: 表示名にこの語が含まれるのに、ドメインが正規のものでない場合に加点
BRAND_DOMAINS = {
    "amazon": ("amazon.co.jp", "amazon.com", "amazon.jp"),
    "アマゾン": ("amazon.co.jp", "amazon.com", "amazon.jp"),
    "楽天": ("rakuten.co.jp", "rakuten.com", "rakuten-card.co.jp", "rakuten-bank.co.jp"),
    "rakuten": ("rakuten.co.jp", "rakuten.com", "rakuten-card.co.jp", "rakuten-bank.co.jp"),
    "apple": ("apple.com", "email.apple.com", "insideapple.apple.com", "icloud.com"),
    "ヤマト": ("kuronekoyamato.co.jp", "yamato-transport.com", "091901.jp"),
    "佐川": ("sagawa-exp.co.jp",),
    "日本郵便": ("japanpost.jp", "post.japanpost.jp"),
    "paypay": ("paypay.ne.jp", "paypay-corp.co.jp", "paypay-card.co.jp"),
    "メルカリ": ("mercari.jp", "mercari.com"),
    "mercari": ("mercari.jp", "mercari.com"),
    "えきねっと": ("eki-net.com",),
    "etc": ("ml.etc-meisai.jp",),
    "paypal": ("paypal.com", "paypal.jp"),
    "三井住友": ("smbc.co.jp", "smbc-card.com", "vpass.ne.jp"),
    "三菱ufj": ("mufg.jp", "bk.mufg.jp"),
    "ゆうちょ": ("jp-bank.japanpost.jp",),
    "docomo": ("docomo.ne.jp", "nttdocomo.co.jp", "docomo-cs.co.jp"),
    "au": ("au.com", "kddi.com", "auone.jp"),
    "softbank": ("softbank.jp", "mb.softbank.jp"),
}


def domain_of(addr):
    if "@" in addr:
        return addr.rsplit("@", 1)[1].lower()
    return ""


def judge_message(msg, settings, sender_stats):
    """1通を判定して (score, reasons) を返す。"""
    addr = msg.get("senderAddr", "")
    name = (msg.get("senderName") or "").lower()
    subject = msg.get("subject") or ""
    dom = domain_of(addr)
    score = 0
    reasons = []

    trusted = set(settings.get("trustedSenders", []))
    blocked = set(settings.get("blockedSenders", []))
    trusted_domains = set(settings.get("trustedDomains", []))
    blocked_domains = set(settings.get("blockedDomains", []))
    favorites = set(settings.get("favorites", []))

    if addr in trusted or addr in favorites or dom in trusted_domains:
        return 0, ["信頼済みの差出人"]
    if addr in blocked:
        return 100, ["ブロック済みの差出人"]
    if dom in blocked_domains:
        return 100, ["ブロック済みのドメイン"]

    # ブランド詐称
    hay = name + " " + subject.lower()
    for brand, domains in BRAND_DOMAINS.items():
        if brand in hay:
            if dom and not any(dom == d or dom.endswith("." + d) for d in domains):
                score += 6
                reasons.append("「%s」を名乗るが正規ドメインではない (%s)" % (brand, dom or "不明"))
            break

    # 怪しいTLD
    if dom.endswith(SUSPICIOUS_TLDS):
        score += 4
        reasons.append("迷惑メールに多いドメイン (%s)" % dom)

    # 件名パターン
    pat_hits = 0
    for pat, desc in SPAM_SUBJECT_PATTERNS:
        if re.search(pat, subject, re.IGNORECASE):
            pat_hits += 1
            reasons.append(desc)
            if pat_hits >= 2:
                break
    score += min(pat_hits * 3, 6)

    # ランダムに見える差出人アドレス (数字が多い等)
    local = addr.split("@")[0] if "@" in addr else addr
    digits = sum(c.isdigit() for c in local)
    if len(local) >= 10 and digits >= len(local) * 0.4:
        score += 2
        reasons.append("機械的な差出人アドレス")

    # 過剰な記号
    if subject.count("!") + subject.count("!") >= 3 or "★" in subject or "◆" in subject:
        score += 1
        reasons.append("記号の多い件名")

    # 付き合いの長い相手は減点 (受信回数が多い・返信したことがある)
    stats = sender_stats.get(addr, {})
    if stats.get("replied", 0) > 0:
        score -= 8
        reasons.append("返信したことのある相手")
    elif stats.get("count", 0) >= 5:
        score -= 3
        reasons.append("受信回数が多い相手")

    return max(score, 0), reasons


def classify(score):
    if score >= SPAM_THRESHOLD:
        return "spam"
    if score >= GREY_THRESHOLD:
        return "grey"
    return "ok"


def build_sender_stats(messages, replied_to):
    """差出人ごとの統計 (受信数・最新日時・未読数・返信数)。"""
    stats = {}
    for m in messages:
        addr = m.get("senderAddr") or "(不明)"
        s = stats.setdefault(addr, {
            "addr": addr, "name": m.get("senderName") or addr,
            "count": 0, "unread": 0, "latest": "", "flagged": 0,
        })
        s["count"] += 1
        if not m.get("read"):
            s["unread"] += 1
        if m.get("flagged"):
            s["flagged"] += 1
        d = m.get("date") or ""
        if d > s["latest"]:
            s["latest"] = d
            s["name"] = m.get("senderName") or addr
    for addr, cnt in (replied_to or {}).items():
        if addr in stats:
            stats[addr]["replied"] = cnt
    return stats


def importance_score(stat, now=None):
    """重要差出人スコア: 受信頻度 + 返信履歴 + 直近性 + フラグ。"""
    now = now or datetime.now()
    score = 0.0
    score += min(stat.get("count", 0), 30) * 0.5
    score += min(stat.get("replied", 0), 20) * 2.0
    score += stat.get("flagged", 0) * 1.5
    latest = stat.get("latest") or ""
    try:
        d = datetime.strptime(latest[:19], "%Y-%m-%dT%H:%M:%S")
        days = max((now - d).days, 0)
        score += 6.0 * math.exp(-days / 30.0)  # 30日半減の直近性ボーナス
    except (ValueError, TypeError):
        pass
    return round(score, 2)


AUTO_FAVORITE_THRESHOLD = 8.0
AUTO_FAVORITE_MIN_COUNT = 3


def auto_favorites(sender_stats, settings):
    """自動で「よく使う相手」に追加すべき差出人を返す。"""
    dismissed = set(settings.get("dismissedFavorites", []))
    manual = set(settings.get("favorites", []))
    blocked = set(settings.get("blockedSenders", []))
    result = []
    for addr, stat in sender_stats.items():
        if addr in dismissed or addr in manual or addr in blocked or addr == "(不明)":
            continue
        # メルマガ・自動送信っぽいアドレスは自動追加しない
        local = addr.split("@")[0]
        dom = addr.split("@")[1] if "@" in addr else ""
        auto_local = (
            r"^(no-?reply|do-?not-?reply|newsletter|news|info|mail|email|notify|"
            r"notification|update|digest|promo|sale|deal|campaign|magazine|"
            r"mailmagazine|support|admin|system|auto|robot|bot|wordpress|auction|"
            r"alert|billing|account|service|contact|marketing|store|shop|offer|"
            r"member|cs|customer|order|delivery|survey|press|release)"
        )
        if re.match(auto_local, local) or "preference" in local or "unsubscribe" in local:
            continue
        if re.match(r"^(mail|mails|email|news|mg|mta|bounce|em|e|m)\d*\.", dom):
            continue
        # 返信履歴が全く無く、名前がアドレスと同じ(=個人名なし)相手も対象外
        if stat.get("replied", 0) == 0 and stat.get("name", "") == addr:
            continue
        sc = importance_score(stat)
        if sc >= AUTO_FAVORITE_THRESHOLD and stat.get("count", 0) >= AUTO_FAVORITE_MIN_COUNT:
            result.append({"addr": addr, "score": sc})
    result.sort(key=lambda x: -x["score"])
    return result[:20]
