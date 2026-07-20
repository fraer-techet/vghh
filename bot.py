import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pg8000.native

BOT_TOKEN = os.environ["BOT_TOKEN"]
DATABASE_URL = os.environ["DATABASE_URL"]
ADMIN_ID = int(os.environ.get("ADMIN_ID", "6049379160"))
PREMIUM_DAYS = int(os.environ.get("PREMIUM_DAYS", "30"))
PREMIUM_STARS = int(os.environ.get("PREMIUM_STARS", "150"))
PORT = int(os.environ.get("PORT", "10000"))
PUBLIC_URL = (os.environ.get("PUBLIC_URL") or os.environ.get("RENDER_EXTERNAL_URL") or "").rstrip("/")
API = "ht" + "tps://api.telegram.org/bot" + BOT_TOKEN


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


def api(method, payload=None, timeout=60):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API + "/" + method, data=data, headers=headers, method="POST" if data else "GET")
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
    }


def ensure_user(conn, tg_id):
    rows = conn.run(
        "select telegram_id, status, trial_used, subscription_expires, sub_token from users where telegram_id = :id",
        id=tg_id,
    )
    if rows:
        return user_row(rows[0])
    rows = conn.run(
        "insert into users (telegram_id, status, trial_used) values (:id, 'free', false) returning telegram_id, status, trial_used, subscription_expires, sub_token",
        id=tg_id,
    )
    return user_row(rows[0])


def sub_link(user):
    base = PUBLIC_URL
    if not base:
        return "(ссылка появится после деплоя, задай PUBLIC_URL)"
    return base + "/sub/" + user["sub_token"]


def status_text(user):
    link = sub_link(user)
    if is_active(user["status"], user["subscription_expires"]):
        kind = "Trial" if user["status"] == "trial" else "Premium"
        return (
            "Статус: <b>" + kind + "</b>\n"
            "Дней осталось: <b>" + str(days_left(user["subscription_expires"])) + "</b>\n"
            "Ссылка подписки:\n<code>" + link + "</code>\n\n"
            "Вставь её в Hiddify / v2rayNG как subscription URL."
        )
    trial = "Триал доступен." if not user["trial_used"] else "Триал уже использован."
    return "Статус: <b>нет подписки</b>\n" + trial + "\nСсылка:\n<code>" + link + "</code>"


def kb_main(user):
    rows = []
    active = is_active(user["status"], user["subscription_expires"])
    if (not user["trial_used"]) and (not active):
        rows.append([{"text": "Активировать триал 7 дней", "callback_data": "trial"}])
    rows.append([{"text": "Купить Premium", "callback_data": "buy"}])
    if active:
        rows.append([{"text": "Моя подписка", "callback_data": "mysub"}])
        rows.append([{"text": "Показать серверы", "callback_data": "servers"}])
    if PUBLIC_URL:
        rows.append([{"text": "Личный кабинет", "url": sub_link(user)}])
    return {"inline_keyboard": rows}


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


def brand(raw, name):
    cfg = (raw or "").strip()
    nm = (name or "Server").strip()
    if not cfg:
        return ""
    i = cfg.rfind("#")
    base = cfg[:i] if i >= 0 else cfg
    return base + "#" + nm


def get_servers(conn):
    return conn.run("select id, raw_config, custom_name from server_pool order by id")


def servers_text(conn):
    rows = get_servers(conn)
    if not rows:
        return "Пул серверов пуст."
    lines = []
    for r in rows:
        lines.append(brand(r[1], r[2]))
    return "\n".join(lines)


def activate_premium(conn, tg_id, days):
    user = ensure_user(conn, tg_id)
    now = utcnow()
    base = now
    if is_active(user["status"], user["subscription_expires"]):
        exp = user["subscription_expires"]
        if getattr(exp, "tzinfo", None) is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp > now:
            base = exp
    expires = base + timedelta(days=days)
    rows = conn.run(
        "update users set status='premium', subscription_expires=:e where telegram_id=:id returning telegram_id, status, trial_used, subscription_expires, sub_token",
        e=expires,
        id=tg_id,
    )
    return user_row(rows[0])


def handle_start(conn, msg):
    tg_id = msg["from"]["id"]
    chat = msg["chat"]["id"]
    user = ensure_user(conn, tg_id)
    text = "VPN бот готов.\n\n" + status_text(user)
    if tg_id == ADMIN_ID:
        text += "\n\nАдмин: /add_server /delete_server /edit_name /grant /admin"
    send(chat, text, kb_main(user))


def handle_cb(conn, cq):
    data = cq.get("data") or ""
    tg_id = cq["from"]["id"]
    chat = cq["message"]["chat"]["id"]
    mid = cq["message"]["message_id"]
    user = ensure_user(conn, tg_id)

    if data in ("mysub",):
        edit(chat, mid, status_text(user), kb_main(user))
        ans(cq["id"])
        return

    if data == "trial":
        if is_active(user["status"], user["subscription_expires"]):
            ans(cq["id"], "Уже активно", True)
            return
        if user["trial_used"]:
            ans(cq["id"], "Триал уже был", True)
            return
        exp = utcnow() + timedelta(days=7)
        rows = conn.run(
            "update users set status='trial', trial_used=true, subscription_expires=:e where telegram_id=:id returning telegram_id, status, trial_used, subscription_expires, sub_token",
            e=exp,
            id=tg_id,
        )
        user = user_row(rows[0])
        edit(chat, mid, "Триал 7 дней включён.\n\n" + status_text(user), kb_main(user))
        ans(cq["id"], "Ок")
        return

    if data == "buy":
        api(
            "sendInvoice",
            {
                "chat_id": tg_id,
                "title": "Premium " + str(PREMIUM_DAYS) + " days",
                "description": "VPN Premium",
                "payload": "premium:" + str(PREMIUM_DAYS),
                "currency": "XTR",
                "prices": [{"label": "Premium", "amount": PREMIUM_STARS}],
                "provider_token": "",
            },
        )
        ans(cq["id"])
        return

    if data == "servers":
        if not is_active(user["status"], user["subscription_expires"]):
            ans(cq["id"], "Нет подписки", True)
            return
        txt = servers_text(conn)
        send(chat, "<code>" + txt.replace("&", "&amp;").replace("<", "&lt;") + "</code>")
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
        handle_start(conn, msg)
        return

    if tg_id != ADMIN_ID:
        return

    if cmd == "/admin":
        rows = get_servers(conn)
        t = "Серверов: " + str(len(rows))
        send(chat, t)
        return

    if cmd == "/add_server":
        if "|||" not in args:
            send(chat, "/add_server ИМЯ|||конфиг")
            return
        name, cfg = args.split("|||", 1)
        name, cfg = name.strip(), cfg.strip()
        if not name or not cfg:
            send(chat, "Пусто")
            return
        r = conn.run(
            "insert into server_pool (raw_config, custom_name) values (:c, :n) returning id, custom_name",
            c=cfg,
            n=name,
        )
        send(chat, "Добавлен #" + str(r[0][0]) + " " + r[0][1])
        return

    if cmd == "/delete_server":
        if not args.isdigit():
            rows = get_servers(conn)
            send(chat, "/delete_server ID\n" + "\n".join("#" + str(r[0]) + " " + r[2] for r in rows))
            return
        r = conn.run("delete from server_pool where id=:id returning id", id=int(args))
        send(chat, "Удалён" if r else "Нет")
        return

    if cmd == "/edit_name":
        if "|||" not in args:
            send(chat, "/edit_name ID|||Имя")
            return
        left, name = args.split("|||", 1)
        if not left.strip().isdigit():
            send(chat, "ID?")
            return
        r = conn.run(
            "update server_pool set custom_name=:n where id=:id returning id",
            n=name.strip(),
            id=int(left.strip()),
        )
        send(chat, "Ок" if r else "Нет")
        return

    if cmd == "/grant":
        b = args.split()
        if len(b) < 2 or (not b[0].isdigit()) or (not b[1].isdigit()):
            send(chat, "/grant TELEGRAM_ID DAYS")
            return
        u = activate_premium(conn, int(b[0]), int(b[1]))
        send(chat, "Premium ok\n<code>" + sub_link(u) + "</code>")


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
    user = activate_premium(conn, tg_id, days)
    send(chat, "Оплата ок.\n\n" + status_text(user), kb_main(user))


def process(conn, upd):
    if "pre_checkout_query" in upd:
        api("answerPreCheckoutQuery", {"pre_checkout_query_id": upd["pre_checkout_query"]["id"], "ok": True})
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
    for m in ("v2ray", "clash", "hiddify", "streisand", "shadowrocket", "nekobox", "sing-box"):
        if m in s:
            return False
    return ("mozilla" in s) or ("chrome" in s) or ("safari" in s)


def html_denied():
    return "<!doctype html><meta charset=utf-8><body style='background:#111;color:#eee;font-family:sans-serif;display:grid;place-items:center;height:100vh'><div><h1>Доступ закрыт</h1><p>Активируй триал или Premium в боте.</p></div>"


def html_cab(user, servers):
    left = days_left(user["subscription_expires"])
    kind = "Trial" if user["status"] == "trial" else "Premium"
    cards = ""
    for s in servers:
        name = s[2]
        cfg = brand(s[1], s[2])
        cards += (
            "<div style='background:#1a1328;border:1px solid #333;border-radius:16px;padding:14px;margin:10px 0'>"
            "<b>" + name + "</b><pre style='white-space:pre-wrap;word-break:break-all;font-size:11px'>"
            + cfg.replace("&", "&amp;").replace("<", "&lt;")
            + "</pre></div>"
        )
    if not cards:
        cards = "<p>Серверов пока нет</p>"
    return (
        "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
        "<body style='margin:0;background:radial-gradient(circle at top,#4c1d95,#0a0a0f);color:#f8fafc;font-family:sans-serif'>"
        "<div style='max-width:900px;margin:0 auto;padding:28px 16px'>"
        "<h1 style='background:linear-gradient(90deg,#e879f9,#a78bfa);-webkit-background-clip:text;color:transparent'>Личный кабинет</h1>"
        "<p>План: <b>" + kind + "</b> · Дней: <b>" + str(left) + "</b> · Нод: <b>" + str(len(servers)) + "</b></p>"
        + cards
        + "</div>"
    )


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        return

    def _send(self, code, ctype, body):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/health"):
            self._send(200, "text/plain; charset=utf-8", "ok")
            return
        if path.startswith("/sub/"):
            token = path.split("/sub/", 1)[1].strip("/")
            if not token:
                self._send(400, "text/plain; charset=utf-8", "missing token")
                return
            conn = db()
            try:
                rows = conn.run(
                    "select telegram_id, status, trial_used, subscription_expires, sub_token from users where sub_token=:t limit 1",
                    t=token,
                )
                if not rows:
                    user = None
                else:
                    user = user_row(rows[0])
                if (not user) or (not is_active(user["status"], user["subscription_expires"])):
                    if is_browser(self.headers.get("User-Agent")):
                        self._send(403, "text/html; charset=utf-8", html_denied())
                    else:
                        self._send(403, "text/plain; charset=utf-8", "subscription inactive")
                    return
                servers = get_servers(conn)
                if is_browser(self.headers.get("User-Agent")):
                    self._send(200, "text/html; charset=utf-8", html_cab(user, servers))
                    return
                lines = [brand(s[1], s[2]) for s in servers if brand(s[1], s[2])]
                body = "\n".join(lines) + ("\n" if lines else "")
                self._send(200, "text/plain; charset=utf-8", body)
            finally:
                conn.close()
            return
        self._send(404, "text/plain; charset=utf-8", "not found")


def start_http():
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print("http on", PORT, flush=True)


def main():
    print("starting bot", flush=True)
    start_http()
    try:
        api("deleteWebhook", {"drop_pending_updates": False})
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
                for u in updates:
                    offset = u["update_id"] + 1
                    try:
                        process(conn, u)
                    except Exception as e:
                        print("upd", e, flush=True)
            finally:
                conn.close()
        except Exception as e:
            print("loop", e, flush=True)
            time.sleep(3)


if __name__ == "__main__":
    main()
