
import html
import json
import os
import secrets
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pg8000.native

BRAND = "FluxVPN"
REF_BONUS_DAYS = 5

def env(name, default=""):
    return os.environ.get(name, default)

BOT_TOKEN = env("BOT_TOKEN")
DATABASE_URL = env("DATABASE_URL")
ADMIN_ID = int(env("ADMIN_ID", "6049379160") or "6049379160")
PREMIUM_DAYS = int(env("PREMIUM_DAYS", "30") or "30")
PREMIUM_STARS = int(env("PREMIUM_STARS", "150") or "150")
PORT = int(env("PORT", "10000") or "10000")
PUBLIC_URL = (env("PUBLIC_URL") or env("RENDER_EXTERNAL_URL") or "").rstrip("/")

if not BOT_TOKEN:
    print("FATAL: BOT_TOKEN missing", flush=True)
    sys.exit(1)
if not DATABASE_URL:
    print("FATAL: DATABASE_URL missing", flush=True)
    sys.exit(1)

API = "ht" + "tps://api.telegram.org/bot" + BOT_TOKEN
print("boot", BRAND, "PORT=", PORT, flush=True)

_schema_lock = threading.Lock()
_schema_ready = False
USER_SELECT = (
    "select telegram_id, status, trial_used, subscription_expires, sub_token, "
    "referral_code, referred_by, referral_count, username, full_name from users"
)

def utcnow():
    return datetime.now(timezone.utc)

def db():
    u = urllib.parse.urlparse(DATABASE_URL)
    return pg8000.native.Connection(
        user=urllib.parse.unquote(u.username or ""),
        password=urllib.parse.unquote(u.password or ""),
        host=u.hostname or "localhost",
        port=u.port or 5432,
        database=(u.path or "/neondb").lstrip("/") or "neondb",
        ssl_context=True,
    )

def ensure_schema(conn):
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        try:
            conn.run("create extension if not exists pgcrypto")
        except Exception:
            pass
        conn.run(
            "create table if not exists server_pool ("
            "id bigserial primary key, raw_config text not null, custom_name text not null, "
            "created_at timestamptz not null default now())"
        )
        conn.run(
            "create table if not exists users ("
            "id bigserial primary key, telegram_id bigint not null unique, "
            "status text not null default 'free', trial_used boolean not null default false, "
            "subscription_expires timestamptz, sub_token text not null unique, "
            "created_at timestamptz not null default now())"
        )
        cols = {
            r[0]
            for r in conn.run(
                "select column_name from information_schema.columns where table_name='users'"
            )
        }
        for col, ddl in [
            ("referral_code", "add column referral_code text"),
            ("referred_by", "add column referred_by bigint"),
            ("referral_count", "add column referral_count integer not null default 0"),
            ("username", "add column username text"),
            ("full_name", "add column full_name text"),
        ]:
            if col not in cols:
                conn.run("alter table users " + ddl)
        conn.run(
            "update users set referral_code = md5(random()::text || clock_timestamp()::text) "
            "where referral_code is null or referral_code = ''"
        )
        try:
            conn.run("create unique index if not exists idx_users_referral_code on users(referral_code)")
        except Exception:
            pass
        _schema_ready = True

def api(method, payload=None, timeout=60):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        API + "/" + method, data=data, headers=headers, method="POST" if data else "GET"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(method + " " + str(e.code) + " " + err)
    if not body.get("ok"):
        raise RuntimeError(method + " " + str(body))
    return body["result"]

def is_active(status, expires):
    if status not in ("trial", "premium") or expires is None:
        return False
    if getattr(expires, "tzinfo", None) is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return expires > utcnow()

def days_left(expires):
    if expires is None:
        return 0
    if getattr(expires, "tzinfo", None) is None:
        expires = expires.replace(tzinfo=timezone.utc)
    sec = (expires - utcnow()).total_seconds()
    if sec <= 0:
        return 0
    return max(1, int((sec + 86399) // 86400))

def user_row(r):
    return {
        "telegram_id": r[0],
        "status": r[1],
        "trial_used": bool(r[2]),
        "subscription_expires": r[3],
        "sub_token": r[4],
        "referral_code": r[5] if len(r) > 5 else None,
        "referred_by": r[6] if len(r) > 6 else None,
        "referral_count": int(r[7] or 0) if len(r) > 7 else 0,
        "username": r[8] if len(r) > 8 else None,
        "full_name": r[9] if len(r) > 9 else None,
    }

def gen_codes():
    return secrets.token_hex(16), secrets.token_hex(4)

def display_name(u):
    if u.get("full_name"):
        return u["full_name"]
    if u.get("username"):
        return "@" + u["username"]
    return str(u["telegram_id"])

def extract_flag(name):
    text = str(name or "")
    for ch in text:
        o = ord(ch)
        if 0x1F1E6 <= o <= 0x1F1FF:
            return ch
    return "\U0001F310"

def brand_config(raw, name):
    cfg = (raw or "").strip()
    nm = (name or "Server").strip()
    if not cfg:
        return ""
    i = cfg.rfind("#")
    base = cfg[:i] if i >= 0 else cfg
    return base + "#" + nm

def sub_link(user):
    if not PUBLIC_URL:
        return ""
    return PUBLIC_URL + "/sub/" + user["sub_token"]

def ref_link(user):
    me = env("BOT_USERNAME", "").lstrip("@")
    code = user.get("referral_code") or ""
    if me:
        return "https://t.me/" + me + "?start=ref_" + code
    return "ref_" + code

def plan_label(user):
    if is_active(user["status"], user["subscription_expires"]):
        return "Trial" if user["status"] == "trial" else "Premium"
    return "Free"

def status_text(user):
    link = sub_link(user)
    active = is_active(user["status"], user["subscription_expires"])
    lines = [
        "\u26A1 <b>" + BRAND + "</b>",
        "",
        "\U0001F464 " + html.escape(display_name(user)),
        "\U0001F4E6 Plan: <b>" + plan_label(user) + "</b>",
    ]
    if active:
        lines.append("\u23F3 Days left: <b>" + str(days_left(user["subscription_expires"])) + "</b>")
    else:
        lines.append("\u23F3 Subscription inactive")
    lines.append(
        "\U0001F381 Referrals: <b>"
        + str(user.get("referral_count") or 0)
        + "</b> (+"
        + str(REF_BONUS_DAYS)
        + " days each)"
    )
    if link:
        lines.extend(["", "\U0001F517 Subscription:", "<code>" + html.escape(link) + "</code>"])
    lines.extend(["", "\U0001F91D Ref link:", "<code>" + html.escape(ref_link(user)) + "</code>"])
    if not active and not user["trial_used"]:
        lines.extend(["", "\u2728 Free 7-day trial available."])
    elif not active:
        lines.extend(["", "\U0001F48E Buy Premium to restore access."])
    return "\n".join(lines)

def kb_main(user):
    rows = []
    active = is_active(user["status"], user["subscription_expires"])
    if (not user["trial_used"]) and (not active):
        rows.append([{"text": "\u2728 Trial 7 days", "callback_data": "trial"}])
    rows.append([{"text": "\U0001F48E Buy Premium", "callback_data": "buy"}])
    rows.append(
        [
            {"text": "\U0001F4CA Status", "callback_data": "mysub"},
            {"text": "\U0001F381 Referral", "callback_data": "referral"},
        ]
    )
    if active:
        rows.append([{"text": "\U0001F6F0 Servers", "callback_data": "servers"}])
    link = sub_link(user)
    if link:
        rows.append([{"text": "\U0001F5A5 Cabinet", "url": link}])
    if user["telegram_id"] == ADMIN_ID:
        rows.append([{"text": "\U0001F6E0 Admin", "callback_data": "admin"}])
    return {"inline_keyboard": rows}

def kb_admin():
    return {
        "inline_keyboard": [
            [
                {"text": "\U0001F4C8 Stats", "callback_data": "adm_stats"},
                {"text": "\U0001F465 Users", "callback_data": "adm_users"},
            ],
            [
                {"text": "\U0001F6F0 Servers", "callback_data": "adm_servers"},
                {"text": "\U0001F7E2 Active", "callback_data": "adm_active"},
            ],
            [
                {"text": "\U0001F4E3 Broadcast", "callback_data": "adm_broadcast"},
                {"text": "+ Days", "callback_data": "adm_grant_help"},
            ],
            [
                {"text": "Trial", "callback_data": "adm_trial_help"},
                {"text": "Revoke", "callback_data": "adm_revoke_help"},
            ],
            [{"text": "Back", "callback_data": "mysub"}],
        ]
    }

def send(chat_id, text, markup=None):
    p = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    if markup is not None:
        p["reply_markup"] = markup
    return api("sendMessage", p)

def edit(chat_id, mid, text, markup=None):
    p = {
        "chat_id": chat_id,
        "message_id": mid,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if markup is not None:
        p["reply_markup"] = markup
    try:
        return api("editMessageText", p)
    except Exception:
        return None

def ans(cq_id, text=None, alert=False):
    p = {"callback_query_id": cq_id, "show_alert": alert}
    if text:
        p["text"] = text
    return api("answerCallbackQuery", p)

def get_user(conn, tg_id):
    rows = conn.run(USER_SELECT + " where telegram_id = :id", id=tg_id)
    return user_row(rows[0]) if rows else None

def ensure_user(conn, tg_id, username=None, full_name=None, ref_code=None):
    ensure_schema(conn)
    existing = get_user(conn, tg_id)
    if existing:
        if username is not None or full_name is not None:
            conn.run(
                "update users set username=coalesce(:u, username), full_name=coalesce(:f, full_name) where telegram_id=:id",
                u=username,
                f=full_name,
                id=tg_id,
            )
            existing = get_user(conn, tg_id)
        return existing
    sub_token, referral_code = gen_codes()
    referred_by = None
    if ref_code:
        rows = conn.run(USER_SELECT + " where referral_code = :c limit 1", c=ref_code)
        if rows and rows[0][0] != tg_id:
            referred_by = rows[0][0]
    conn.run(
        "insert into users (telegram_id, status, trial_used, sub_token, referral_code, referred_by, referral_count, username, full_name) "
        "values (:id, 'free', false, :st, :rc, :rb, 0, :u, :f)",
        id=tg_id,
        st=sub_token,
        rc=referral_code,
        rb=referred_by,
        u=username,
        f=full_name,
    )
    user = get_user(conn, tg_id)
    if referred_by:
        apply_referral_bonus(conn, referred_by, tg_id)
        user = get_user(conn, tg_id)
    return user

def extend_subscription(conn, tg_id, days, status="premium"):
    user = get_user(conn, tg_id) or ensure_user(conn, tg_id)
    now = utcnow()
    base = now
    if is_active(user["status"], user["subscription_expires"]):
        exp = user["subscription_expires"]
        if getattr(exp, "tzinfo", None) is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp > now:
            base = exp
    expires = base + timedelta(days=days)
    conn.run(
        "update users set status=:s, subscription_expires=:e where telegram_id=:id",
        s=status,
        e=expires,
        id=tg_id,
    )
    return get_user(conn, tg_id)

def apply_referral_bonus(conn, inviter_id, newbie_id):
    inviter = get_user(conn, inviter_id)
    newbie = get_user(conn, newbie_id)
    if not inviter or not newbie:
        return
    if newbie.get("referred_by") not in (None, inviter_id):
        return
    conn.run(
        "update users set referral_count = coalesce(referral_count,0) + 1 where telegram_id=:id",
        id=inviter_id,
    )
    keep_trial = inviter["status"] == "trial" and is_active(
        inviter["status"], inviter["subscription_expires"]
    )
    extend_subscription(
        conn, inviter_id, REF_BONUS_DAYS, status=("trial" if keep_trial else "premium")
    )
    try:
        send(
            inviter_id,
            "\U0001F389 <b>Referral bonus!</b>\n+"
            + str(REF_BONUS_DAYS)
            + " days on "
            + BRAND
            + ".",
        )
    except Exception:
        pass

def get_servers(conn):
    ensure_schema(conn)
    return conn.run("select id, raw_config, custom_name from server_pool order by id")

def servers_list_text(conn):
    rows = get_servers(conn)
    if not rows:
        return "No servers yet."
    lines = ["\U0001F6F0 <b>" + BRAND + " servers</b>", ""]
    for r in rows:
        lines.append(extract_flag(r[2]) + " <b>" + html.escape(str(r[2])) + "</b>")
    lines.extend(["", "Configs are delivered only via subscription URL in the client."])
    return "\n".join(lines)

def admin_stats_text(conn):
    ensure_schema(conn)
    total = conn.run("select count(*) from users")[0][0]
    trial_used = conn.run("select count(*) from users where trial_used = true")[0][0]
    servers = conn.run("select count(*) from server_pool")[0][0]
    refs = conn.run("select coalesce(sum(referral_count),0) from users")[0][0]
    active = premium = trial = 0
    for r in conn.run(USER_SELECT):
        u = user_row(r)
        if is_active(u["status"], u["subscription_expires"]):
            active += 1
            if u["status"] == "premium":
                premium += 1
            elif u["status"] == "trial":
                trial += 1
    return (
        "\U0001F6E0 <b>" + BRAND + " Admin</b>\n\n"
        "Users: <b>" + str(total) + "</b>\n"
        "Active: <b>" + str(active) + "</b>\n"
        "Premium: <b>" + str(premium) + "</b>\n"
        "Trial live: <b>" + str(trial) + "</b>\n"
        "Trial used: <b>" + str(trial_used) + "</b>\n"
        "Referrals: <b>" + str(refs) + "</b>\n"
        "Servers: <b>" + str(servers) + "</b>"
    )

def admin_users_text(conn, limit=15):
    rows = conn.run(USER_SELECT + " order by id desc limit :n", n=limit)
    if not rows:
        return "No users."
    lines = ["\U0001F465 <b>Latest users</b>", ""]
    for r in rows:
        u = user_row(r)
        left = (
            days_left(u["subscription_expires"])
            if is_active(u["status"], u["subscription_expires"])
            else 0
        )
        lines.append(
            "\u2022 <code>"
            + str(u["telegram_id"])
            + "</code> "
            + html.escape(display_name(u))
            + " - <b>"
            + plan_label(u)
            + "</b>"
            + (" / " + str(left) + "d" if left else "")
            + " / ref "
            + str(u.get("referral_count") or 0)
        )
    lines.extend(["", "/grant ID DAYS", "/trial ID", "/revoke ID", "/find ID"])
    return "\n".join(lines)

def admin_active_text(conn):
    rows = conn.run(USER_SELECT + " order by subscription_expires desc nulls last limit 50")
    lines = ["\U0001F7E2 <b>Active</b>", ""]
    n = 0
    for r in rows:
        u = user_row(r)
        if not is_active(u["status"], u["subscription_expires"]):
            continue
        n += 1
        lines.append(
            "\u2022 <code>"
            + str(u["telegram_id"])
            + "</code> "
            + html.escape(display_name(u))
            + " - "
            + plan_label(u)
            + " / "
            + str(days_left(u["subscription_expires"]))
            + "d"
        )
    if n == 0:
        lines.append("None active.")
    return "\n".join(lines)

def admin_servers_text(conn):
    rows = get_servers(conn)
    lines = ["\U0001F6F0 <b>Server pool</b>", ""]
    if not rows:
        lines.append("Empty.")
    else:
        for r in rows:
            lines.append(
                extract_flag(r[2])
                + " <b>#"
                + str(r[0])
                + "</b> - "
                + html.escape(str(r[2]))
            )
    lines.extend(
        [
            "",
            "/add_server NAME|||config",
            "/delete_server ID",
            "/edit_name ID|||NAME",
        ]
    )
    return "\n".join(lines)

def from_user_meta(u):
    username = u.get("username")
    full_name = ((u.get("first_name") or "") + " " + (u.get("last_name") or "")).strip() or None
    return username, full_name

def handle_start(conn, msg, ref_code=None):
    tg_id = msg["from"]["id"]
    chat = msg["chat"]["id"]
    username, full_name = from_user_meta(msg.get("from") or {})
    user = ensure_user(conn, tg_id, username=username, full_name=full_name, ref_code=ref_code)
    text = (
        "\U0001F680 Welcome to <b>"
        + BRAND
        + "</b>\nPremium VPN with cabinet and referrals.\n\n"
        + status_text(user)
    )
    send(chat, text, kb_main(user))

def handle_cb(conn, cq):
    data = cq.get("data") or ""
    tg_id = cq["from"]["id"]
    chat = cq["message"]["chat"]["id"]
    mid = cq["message"]["message_id"]
    username, full_name = from_user_meta(cq.get("from") or {})
    user = ensure_user(conn, tg_id, username=username, full_name=full_name)

    if data == "mysub":
        edit(chat, mid, status_text(user), kb_main(user))
        ans(cq["id"])
        return
    if data == "referral":
        t = (
            "\U0001F381 <b>"
            + BRAND
            + " referral</b>\n\n+"
            + str(REF_BONUS_DAYS)
            + " days for each friend.\nInvited: <b>"
            + str(user.get("referral_count") or 0)
            + "</b>\n\n<code>"
            + html.escape(ref_link(user))
            + "</code>"
        )
        edit(chat, mid, t, kb_main(user))
        ans(cq["id"])
        return
    if data == "trial":
        if is_active(user["status"], user["subscription_expires"]):
            ans(cq["id"], "Already active", True)
            return
        if user["trial_used"]:
            ans(cq["id"], "Trial already used", True)
            return
        exp = utcnow() + timedelta(days=7)
        conn.run(
            "update users set status='trial', trial_used=true, subscription_expires=:e where telegram_id=:id",
            e=exp,
            id=tg_id,
        )
        user = get_user(conn, tg_id)
        edit(chat, mid, "\u2705 Trial 7 days on!\n\n" + status_text(user), kb_main(user))
        ans(cq["id"], "OK")
        return
    if data == "buy":
        api(
            "sendInvoice",
            {
                "chat_id": tg_id,
                "title": BRAND + " Premium " + str(PREMIUM_DAYS) + " days",
                "description": BRAND + " access",
                "payload": "premium:" + str(PREMIUM_DAYS),
                "currency": "XTR",
                "prices": [{"label": BRAND + " Premium", "amount": PREMIUM_STARS}],
                "provider_token": "",
            },
        )
        ans(cq["id"])
        return
    if data == "servers":
        if not is_active(user["status"], user["subscription_expires"]):
            ans(cq["id"], "Need active sub", True)
            return
        edit(chat, mid, servers_list_text(conn), kb_main(user))
        ans(cq["id"])
        return
    if data == "admin":
        if tg_id != ADMIN_ID:
            ans(cq["id"])
            return
        edit(chat, mid, admin_stats_text(conn), kb_admin())
        ans(cq["id"])
        return
    if data.startswith("adm_") and tg_id == ADMIN_ID:
        if data == "adm_stats":
            edit(chat, mid, admin_stats_text(conn), kb_admin())
        elif data == "adm_users":
            edit(chat, mid, admin_users_text(conn), kb_admin())
        elif data == "adm_servers":
            edit(chat, mid, admin_servers_text(conn), kb_admin())
        elif data == "adm_active":
            edit(chat, mid, admin_active_text(conn), kb_admin())
        elif data == "adm_broadcast":
            edit(chat, mid, "\U0001F4E3 <code>/broadcast TEXT</code>", kb_admin())
        elif data == "adm_grant_help":
            edit(chat, mid, "+ days\n<code>/grant ID DAYS</code>", kb_admin())
        elif data == "adm_trial_help":
            edit(chat, mid, "Trial\n<code>/trial ID</code>", kb_admin())
        elif data == "adm_revoke_help":
            edit(chat, mid, "Revoke\n<code>/revoke ID</code>", kb_admin())
        ans(cq["id"])
        return
    ans(cq["id"])

def handle_cmd(conn, msg):
    text = (msg.get("text") or "").strip()
    if not text.startswith("/"):
        return
    tg_id = msg["from"]["id"]
    chat = msg["chat"]["id"]
    parts = text.split(maxsplit=1)
    cmd = parts[0].split("@")[0].lower()
    args = parts[1].strip() if len(parts) > 1 else ""
    if cmd == "/start":
        ref = args[4:].strip() if args.startswith("ref_") else None
        handle_start(conn, msg, ref_code=ref)
        return
    if cmd == "/menu":
        username, full_name = from_user_meta(msg.get("from") or {})
        user = ensure_user(conn, tg_id, username=username, full_name=full_name)
        send(chat, status_text(user), kb_main(user))
        return
    if tg_id != ADMIN_ID:
        return
    if cmd == "/admin":
        send(chat, admin_stats_text(conn), kb_admin())
        return
    if cmd == "/add_server":
        if "|||" not in args:
            send(chat, "/add_server NAME|||config")
            return
        name, cfg = args.split("|||", 1)
        name, cfg = name.strip(), cfg.strip()
        if not name or not cfg:
            send(chat, "empty")
            return
        r = conn.run(
            "insert into server_pool (raw_config, custom_name) values (:c, :n) returning id, custom_name",
            c=cfg,
            n=name,
        )
        send(chat, "\u2705 #" + str(r[0][0]) + " " + html.escape(r[0][1]), kb_admin())
        return
    if cmd == "/delete_server":
        if not args.isdigit():
            send(chat, admin_servers_text(conn), kb_admin())
            return
        r = conn.run("delete from server_pool where id=:id returning id", id=int(args))
        send(chat, "deleted" if r else "no", kb_admin())
        return
    if cmd == "/edit_name":
        if "|||" not in args:
            send(chat, "/edit_name ID|||NAME")
            return
        left, name = args.split("|||", 1)
        if not left.strip().isdigit() or not name.strip():
            send(chat, "bad")
            return
        r = conn.run(
            "update server_pool set custom_name=:n where id=:id returning id",
            n=name.strip(),
            id=int(left.strip()),
        )
        send(chat, "ok" if r else "no", kb_admin())
        return
    if cmd == "/grant":
        b = args.split()
        if len(b) < 2 or not b[0].isdigit() or not b[1].isdigit():
            send(chat, "/grant ID DAYS")
            return
        u = extend_subscription(conn, int(b[0]), int(b[1]), status="premium")
        send(chat, "\u2705\n<code>" + html.escape(sub_link(u)) + "</code>", kb_admin())
        try:
            send(int(b[0]), "\U0001F48E Premium +" + b[1] + "d " + BRAND)
        except Exception:
            pass
        return
    if cmd == "/trial":
        if not args.isdigit():
            send(chat, "/trial ID")
            return
        tid = int(args)
        ensure_user(conn, tid)
        exp = utcnow() + timedelta(days=7)
        conn.run(
            "update users set status='trial', trial_used=true, subscription_expires=:e where telegram_id=:id",
            e=exp,
            id=tid,
        )
        send(chat, "trial ok", kb_admin())
        return
    if cmd == "/revoke":
        if not args.isdigit():
            send(chat, "/revoke ID")
            return
        conn.run(
            "update users set status='free', subscription_expires=null where telegram_id=:id",
            id=int(args),
        )
        send(chat, "revoked", kb_admin())
        return
    if cmd == "/find":
        if not args.isdigit():
            send(chat, "/find ID")
            return
        u = get_user(conn, int(args))
        send(chat, status_text(u) if u else "no", kb_admin())
        return
    if cmd == "/broadcast":
        if not args:
            send(chat, "/broadcast TEXT")
            return
        ids = [r[0] for r in conn.run("select telegram_id from users")]
        ok = fail = 0
        for i in ids:
            try:
                send(i, "\U0001F4E2 <b>" + BRAND + "</b>\n\n" + html.escape(args))
                ok += 1
                time.sleep(0.05)
            except Exception:
                fail += 1
        send(chat, "OK " + str(ok) + " / fail " + str(fail), kb_admin())

def handle_pay(conn, msg):
    tg_id = msg["from"]["id"]
    chat = msg["chat"]["id"]
    payload = (msg.get("successful_payment") or {}).get("invoice_payload") or ""
    days = PREMIUM_DAYS
    if payload.startswith("premium:"):
        try:
            days = int(payload.split(":", 1)[1])
        except Exception:
            days = PREMIUM_DAYS
    user = extend_subscription(conn, tg_id, days, status="premium")
    send(chat, "\u2705 Premium on!\n\n" + status_text(user), kb_main(user))

def process(conn, upd):
    if "pre_checkout_query" in upd:
        api(
            "answerPreCheckoutQuery",
            {"pre_checkout_query_id": upd["pre_checkout_query"]["id"], "ok": True},
        )
        return
    if "callback_query" in upd:
        handle_cb(conn, upd["callback_query"])
        return
    msg = upd.get("message") or upd.get("edited_message")
    if not msg:
        return
    if msg.get("successful_payment"):
        handle_pay(conn, msg)
        return
    if msg.get("text"):
        handle_cmd(conn, msg)

def is_browser(ua):
    s = (ua or "").lower()
    if not s:
        return False
    for m in (
        "v2ray",
        "clash",
        "hiddify",
        "streisand",
        "shadowrocket",
        "nekobox",
        "sing-box",
        "happ",
        "okhttp",
    ):
        if m in s:
            return False
    return ("mozilla" in s) or ("chrome" in s) or ("safari" in s) or ("firefox" in s)

def render_denied():
    return (
        "<!DOCTYPE html><html lang=ru><head><meta charset=utf-8>"
        "<meta name=viewport content=\"width=device-width,initial-scale=1\">"
        "<title>FluxVPN</title><style>"
        "body{margin:0;min-height:100vh;display:grid;place-items:center;font-family:Inter,system-ui,sans-serif;"
        "color:#f8fafc;background:radial-gradient(900px 500px at 10% -10%,#7c3aed66,transparent),#07060f}"
        ".card{width:min(520px,92vw);padding:32px;border-radius:28px;background:#12101ccc;border:1px solid #ffffff14}"
        "h1{margin:0 0 10px;background:linear-gradient(90deg,#67e8f9,#a78bfa);-webkit-background-clip:text;color:transparent}"
        "p{margin:0;color:#94a3b8;line-height:1.6}</style></head>"
        "<body><div class=card><h1>FluxVPN</h1>"
        "<p>Access denied. Activate Trial or Premium in the bot.</p></div></body></html>"
    )

def render_cabinet(user, servers):
    active = is_active(user["status"], user["subscription_expires"])
    left = days_left(user["subscription_expires"]) if active else 0
    plan = html.escape(plan_label(user))
    link = html.escape(sub_link(user) or "")
    ref = html.escape(ref_link(user))
    name = html.escape(display_name(user))
    cards = []
    for s in servers:
        flag = extract_flag(s[2])
        title = html.escape(str(s[2]))
        cards.append(
            "<div class=server><div class=flag>"
            + flag
            + "</div><div class=meta><div class=sname>"
            + title
            + "</div><div class=stag>Node #"
            + str(s[0])
            + "</div></div><div class=pill>Online</div></div>"
        )
    servers_html = "".join(cards) if cards else "<div class=empty>Servers coming soon</div>"
    st = "Active" if active else "Inactive"
    refs = str(int(user.get("referral_count") or 0))
    nserv = str(len(servers))
    bonus = str(REF_BONUS_DAYS)
    css = (
        "*{box-sizing:border-box}body{margin:0;font-family:Inter,system-ui,sans-serif;color:#f8fafc;"
        "background:radial-gradient(1000px 500px at 0% -10%,#22d3ee33,transparent 60%),"
        "radial-gradient(900px 500px at 100% 0%,#a78bfa44,transparent 55%),#07060f}"
        ".wrap{width:min(1100px,94vw);margin:0 auto;padding:28px 0 60px}"
        ".top{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;padding:22px;border-radius:28px;"
        "border:1px solid rgba(255,255,255,.08);background:linear-gradient(135deg,rgba(34,211,238,.12),rgba(167,139,250,.14));"
        "box-shadow:0 24px 80px #0007}"
        ".brand{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#e2e8f0aa}"
        "h1{margin:8px 0 6px;font-size:clamp(28px,5vw,40px);background:linear-gradient(90deg,#fff,#a5f3fc,#ddd6fe);"
        "-webkit-background-clip:text;color:transparent}"
        ".sub{margin:0;color:#94a3b8;max-width:60ch;line-height:1.55}"
        ".badge{display:inline-flex;gap:8px;align-items:center;padding:8px 12px;border-radius:999px;background:#0006;"
        "border:1px solid rgba(255,255,255,.08);font-size:12px}"
        ".dot{width:8px;height:8px;border-radius:50%;background:#34d399;box-shadow:0 0 16px #34d399}"
        ".stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-top:16px}"
        ".stat{padding:16px;border-radius:20px;background:rgba(8,7,16,.72);border:1px solid rgba(255,255,255,.08)}"
        ".stat span{display:block;color:#94a3b8;font-size:12px}.stat b{display:block;margin-top:6px;font-size:22px}"
        ".tabs{display:flex;gap:8px;flex-wrap:wrap;margin:22px 0 14px}"
        ".tab{border:1px solid rgba(255,255,255,.08);background:#0d0b16cc;color:#e2e8f0;padding:10px 14px;"
        "border-radius:999px;cursor:pointer;font-weight:600}"
        ".tab.active{background:linear-gradient(90deg,#0891b2,#7c3aed);border-color:transparent}"
        ".panel{display:none;padding:18px;border-radius:24px;background:#0c0b14f2;border:1px solid rgba(255,255,255,.08)}"
        ".panel.active{display:block}"
        ".server{display:flex;align-items:center;gap:12px;padding:14px;border-radius:18px;background:#0a0912;"
        "border:1px solid rgba(255,255,255,.08);margin-bottom:10px}"
        ".flag{width:46px;height:46px;border-radius:16px;display:grid;place-items:center;font-size:24px;"
        "background:linear-gradient(135deg,#22d3ee33,#a78bfa33)}"
        ".sname{font-weight:700}.stag{color:#94a3b8;font-size:12px;margin-top:2px}"
        ".pill{margin-left:auto;font-size:11px;padding:6px 10px;border-radius:999px;background:#063;color:#bbf7d0}"
        ".box{padding:14px;border-radius:16px;background:#0006;border:1px solid rgba(255,255,255,.08);word-break:break-all;"
        "font-family:ui-monospace,Menlo,monospace;font-size:12px;color:#cbd5e1}"
        ".btn{display:inline-flex;margin-top:12px;padding:12px 16px;border-radius:14px;"
        "background:linear-gradient(90deg,#06b6d4,#8b5cf6);color:#fff;border:0;cursor:pointer;font-weight:700}"
        ".note{color:#94a3b8;font-size:13px;line-height:1.6;margin-top:12px}.empty{color:#94a3b8;padding:20px 8px}"
        "@media(max-width:800px){.stats{grid-template-columns:1fr 1fr}}"
        "@media(max-width:520px){.stats{grid-template-columns:1fr}}"
    )
    js = (
        "const tabs=[...document.querySelectorAll('.tab')];"
        "const panels=[...document.querySelectorAll('.panel')];"
        "tabs.forEach(t=>t.addEventListener('click',()=>{tabs.forEach(x=>x.classList.remove('active'));"
        "panels.forEach(x=>x.classList.remove('active'));t.classList.add('active');"
        "document.getElementById(t.dataset.tab).classList.add('active');}));"
    )
    return (
        "<!DOCTYPE html><html lang=ru><head><meta charset=utf-8>"
        "<meta name=viewport content=\"width=device-width,initial-scale=1\">"
        "<title>FluxVPN Cabinet</title><style>"
        + css
        + "</style></head><body><div class=wrap>"
        "<div class=top><div><div class=brand>FLUXVPN PRIVATE ACCESS</div>"
        "<h1>Cabinet</h1>"
        "<p class=sub>Hi, "
        + name
        + ". Manage plan and locations. Raw vless/ss strings are hidden here.</p></div>"
        "<div class=badge><span class=dot></span> "
        + st
        + "</div></div>"
        "<div class=stats>"
        "<div class=stat><span>Plan</span><b>"
        + plan
        + "</b></div>"
        "<div class=stat><span>Days</span><b>"
        + str(left)
        + "</b></div>"
        "<div class=stat><span>Servers</span><b>"
        + nserv
        + "</b></div>"
        "<div class=stat><span>Referrals</span><b>"
        + refs
        + "</b></div></div>"
        "<div class=tabs>"
        "<button class=\"tab active\" data-tab=overview>Overview</button>"
        "<button class=tab data-tab=servers>Servers</button>"
        "<button class=tab data-tab=sub>Subscription</button>"
        "<button class=tab data-tab=ref>Referral</button></div>"
        "<div id=overview class=\"panel active\"><h3>How to connect</h3>"
        "<p class=note>1. Copy subscription URL.<br>2. Paste into Happ / Hiddify / v2rayNG.<br>"
        "3. Refresh subscription.<br><br>Cabinet shows locations only, not raw configs.</p></div>"
        "<div id=servers class=panel><h3>Locations</h3>"
        + servers_html
        + "</div>"
        "<div id=sub class=panel><h3>Subscription URL</h3><div class=box id=suburl>"
        + link
        + "</div>"
        "<button class=btn onclick=\"navigator.clipboard.writeText(document.getElementById('suburl').innerText)\">Copy</button>"
        "<p class=note>Browser = cabinet. VPN client = config list.</p></div>"
        "<div id=ref class=panel><h3>Referral</h3>"
        "<p class=note>Each friend = +"
        + bonus
        + " days.</p>"
        "<div class=box id=refurl>"
        + ref
        + "</div>"
        "<button class=btn onclick=\"navigator.clipboard.writeText(document.getElementById('refurl').innerText)\">Copy ref</button></div>"
        "</div><script>"
        + js
        + "</script></body></html>"
    )

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print("http", self.address_string(), fmt % args, flush=True)

    def _send(self, code, ctype, body):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        try:
            path = urllib.parse.urlparse(self.path).path
            if path in ("/", "/health", "/favicon.ico"):
                self._send(200, "text/plain; charset=utf-8", "FluxVPN ok")
                return
            if path.startswith("/sub/"):
                token = path.split("/sub/", 1)[1].strip("/")
                if not token:
                    self._send(400, "text/plain; charset=utf-8", "missing token")
                    return
                conn = db()
                try:
                    ensure_schema(conn)
                    rows = conn.run(USER_SELECT + " where sub_token=:t limit 1", t=token)
                    user = user_row(rows[0]) if rows else None
                    if (not user) or (not is_active(user["status"], user["subscription_expires"])):
                        if is_browser(self.headers.get("User-Agent")):
                            self._send(403, "text/html; charset=utf-8", render_denied())
                        else:
                            self._send(403, "text/plain; charset=utf-8", "subscription inactive")
                        return
                    servers = get_servers(conn)
                    if is_browser(self.headers.get("User-Agent")):
                        self._send(200, "text/html; charset=utf-8", render_cabinet(user, servers))
                        return
                    lines = [brand_config(s[1], s[2]) for s in servers if brand_config(s[1], s[2])]
                    body = "\n".join(lines) + ("\n" if lines else "")
                    exp = user["subscription_expires"]
                    if getattr(exp, "tzinfo", None) is None:
                        exp = exp.replace(tzinfo=timezone.utc)
                    data = body.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Profile-Update-Interval", "12")
                    self.send_header("Subscription-Userinfo", "expire=" + str(int(exp.timestamp())))
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                finally:
                    conn.close()
                return
            self._send(404, "text/plain; charset=utf-8", "not found")
        except Exception:
            print("http error", traceback.format_exc(), flush=True)
            self._send(500, "text/plain; charset=utf-8", "server error")

def start_http():
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print("HTTP listening 0.0.0.0:" + str(PORT), flush=True)

def resolve_bot_username():
    try:
        me = api("getMe")
        uname = me.get("username") or ""
        if uname:
            os.environ["BOT_USERNAME"] = uname
            print("bot @" + uname, flush=True)
    except Exception as e:
        print("getMe", e, flush=True)

def main():
    print("starting " + BRAND, flush=True)
    start_http()
    time.sleep(0.2)
    resolve_bot_username()
    try:
        c = db()
        try:
            ensure_schema(c)
            print("schema ok", flush=True)
        finally:
            c.close()
    except Exception:
        print("schema init", traceback.format_exc(), flush=True)
    try:
        api("deleteWebhook", {"drop_pending_updates": False})
        print("webhook cleared", flush=True)
    except Exception as e:
        print("deleteWebhook", e, flush=True)
    offset = 0
    while True:
        try:
            updates = api(
                "getUpdates",
                {
                    "timeout": 50,
                    "offset": offset,
                    "allowed_updates": ["message", "callback_query", "pre_checkout_query"],
                },
                timeout=60,
            )
            conn = db()
            try:
                ensure_schema(conn)
                for u in updates:
                    offset = u["update_id"] + 1
                    try:
                        process(conn, u)
                    except Exception:
                        print("upd", traceback.format_exc(), flush=True)
            finally:
                conn.close()
        except Exception:
            print("loop", traceback.format_exc(), flush=True)
            time.sleep(3)

if __name__ == "__main__":
    main()
