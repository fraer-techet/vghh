# -*- coding: utf-8 -*-
import html as html_lib
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
TRIAL_DEVICE_LIMIT = 2
PREMIUM_DEVICE_LIMIT = 4

def env(name, default=""):
    return os.environ.get(name, default)

BOT_TOKEN = env("BOT_TOKEN")
DATABASE_URL = env("DATABASE_URL")
ADMIN_ID = int(env("ADMIN_ID", "6049379160") or "6049379160")
ADMIN_USERNAME = (env("ADMIN_USERNAME", "zrdws") or "zrdws").lstrip("@")
PREMIUM_DAYS = int(env("PREMIUM_DAYS", "30") or "30")
PREMIUM_STARS = int(env("PREMIUM_STARS", "150") or "150")
PREMIUM_PLANS = [
    {"days": 7, "key": "7", "price": 50},
    {"days": 30, "key": "30", "price": 200},
    {"days": 90, "key": "90", "price": 400},
    {"days": 365, "key": "365", "price": 800},
]
PLAN_PRICE = {7: 50, 30: 200, 90: 400, 365: 800}
PLAN_PRICE = {7: 50, 30: 200, 90: 400, 365: 800}

def plan_price(days):
    return int(PLAN_PRICE.get(int(days), 0))
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
PENDING = {}
USER_SELECT = (
    "select telegram_id, status, trial_used, subscription_expires, sub_token, "
    "referral_code, referred_by, referral_count, username, full_name, lang from users"
)

TEXTS = {
    "ru": {
        "choose_lang": "Выбери язык / Choose language",
        "welcome": "<b>{brand}</b>\nЧистый доступ. Без лишнего.",
        "welcome_ref": "Тебя пригласили в <b>{brand}</b>.\nДобро пожаловать.",
        "status_title": "<b>{brand}</b>",
        "plan": "План · <b>{plan}</b>",
        "days": "Осталось · <b>{days} дн.</b>",
        "inactive": "Статус · <b>неактивна</b>",
        "refs": "Рефералы · <b>{n}</b>  ·  +{bonus} дн. за друга",
        "trial_avail": "Доступен пробный период 7 дней.",
        "need_premium": "Нужен Premium для доступа.",
        "btn_trial": "Триал 7 дней",
        "btn_buy": "Купить Premium",
        "buy_title": "<b>Premium</b>\nВыбери тариф. Оплата админу @zrdws.",
        "buy_plan_7": "7 дней — 50₽",
        "buy_plan_30": "30 дней — 200₽",
        "buy_plan_90": "90 дней — 400₽",
        "buy_plan_365": "1 год — 800₽",
        "buy_order": "Заявка: <b>{days} дн.</b> / <b>{price}₽</b>\n\n1) Напиши админу\n2) Отправь заказ\n3) После оплаты нажмёт «Заказ оплачен»\n\n<code>{order}</code>",
        "btn_write_admin": "Написать админу",
        "btn_choose_plan": "Другой срок",
        "admin_new_order": "🛒 <b>Новый заказ</b>\nОт: <code>{uid}</code> {name}\nПлан: <b>{days} дн.</b> / <b>{price}₽</b>",
        "btn_order_paid": "✅ Заказ оплачен",
        "order_paid_ok": "✅ Заказ подтверждён.\nЮзеру <code>{uid}</code> выдано <b>{days} дн.</b> Premium.",
        "order_paid_user": "✅ Оплата подтверждена.\nТебе начислено <b>{days} дн.</b> Premium.",
        "order_paid_done": "Уже обработан",
        "order_bad": "Некорректный заказ",
        "btn_status": "Статус",
        "btn_ref": "Рефералка",
        "btn_servers": "Серверы",
        "btn_cab": "Кабинет",
        "btn_copy_key": "Скопировать ключ",
        "btn_copy_ref": "Скопировать реф",
        "btn_admin": "Админ",
        "btn_back": "Назад",
        "trial_ok": "Триал активирован на 7 дней.",
        "trial_used": "Триал уже использован",
        "already": "Подписка уже активна",
        "need_sub": "Нужна активная подписка",
        "servers_title": "<b>Серверы</b>",
        "servers_empty": "Пока нет серверов.",
        "servers_note": "Ключ подписки — кнопкой ниже.",
        "ref_title": "<b>Рефералка</b>",
        "ref_body": "+{bonus} дней за каждого друга.\nПриглашено: <b>{n}</b>",
        "ref_bonus_inviter": "Реферальный бонус: +{bonus} дн. ({brand})",
        "pay_ok": "Premium активирован.",
        "admin_title": "🛠 <b>Админка {brand}</b>",
        "admin_stats": "👥 Юзеров: <b>{total}</b>\n🟢 Активных: <b>{active}</b>\n💎 Premium: <b>{premium}</b>\n✨ Trial: <b>{trial}</b>\n🎁 Рефов: <b>{refs}</b>\n🛰 Серверов: <b>{servers}</b>\n📱 Устройств: <b>{devices}</b>",
        "adm_stats": "📈 Статистика",
        "adm_users": "👥 Пользователи",
        "adm_servers": "🛰 Серверы",
        "adm_active": "🟢 Активные",
        "adm_broadcast": "📣 Рассылка",
        "adm_grant_self": "👑 Себе Premium",
        "adm_grant_user": "➕ Юзеру дни",
        "adm_trial": "🧪 Выдать триал",
        "adm_revoke": "⛔ Снять доступ",
        "adm_add_srv": "➕ Сервер",
        "adm_del_srv": "🗑 Удалить сервер",
        "adm_find": "🔎 Найти юзера",
        "adm_reset_devices": "📱 Сброс устройств",
        "adm_prices": "💰 Тарифы",
        "adm_orders_help": "ℹ️ Как выдавать",
        "adm_search": "🔎 Поиск",
        "prices_text": "<b>Тарифы FluxVPN</b>\n\n• 7 дней — <b>50₽</b>\n• 30 дней — <b>200₽</b>\n• 90 дней — <b>400₽</b>\n• 1 год — <b>800₽</b>",
        "orders_help": "Юзер жмёт Купить → тариф → пишет тебе.\nПосле оплаты жми <b>Заказ оплачен</b> в уведомлении.",
        "device_reset_ok": "✅ Устройства пользователя заблокированы. После обновления подписки в VPN конфиги пропадут.",
        "ask_reset_devices": "Отправь Telegram ID для сброса устройств.",
        "ask_user_id": "Отправь Telegram ID пользователя числом.",
        "ask_broadcast": "Отправь текст рассылки одним сообщением.",
        "ask_server_name": "Отправь название сервера (можно с флагом).\nПример: 🇩🇪 Germany",
        "ask_server_cfg": "Отправь raw-конфиг (vless/ss строку).",
        "choose_days": "Сколько дней выдать?",
        "days_7": "7 дней",
        "days_30": "30 дней",
        "days_90": "90 дней",
        "days_365": "365 дней",
        "days_9999": "∞ Навсегда",
        "granted": "✅ Выдано {days} дн. пользователю <code>{id}</code>",
        "granted_self": "✅ Тебе начислено {days} дн. Premium",
        "revoked": "⛔ Доступ снят у <code>{id}</code>",
        "trial_given": "✅ Триал выдан <code>{id}</code>",
        "not_found": "Не найден",
        "broadcast_done": "Рассылка: OK {ok} / fail {fail}",
        "server_added": "✅ Сервер #{id} — {name}",
        "server_deleted": "🗑 Удалён",
        "cancel": "❌ Отмена",
        "cancelled": "Отменено.",
        "users_title": "👥 <b>Последние пользователи</b>",
        "active_title": "🟢 <b>Активные</b>",
        "none_active": "Активных нет.",
        "pick_server_del": "Выбери сервер для удаления:",
        "no_servers": "Серверов нет.",
        "lang_set": "Язык сохранён: Русский",
    },
    "en": {
        "choose_lang": "Choose language / Выбери язык",
        "welcome": "<b>{brand}</b>\nClean access. Nothing extra.",
        "welcome_ref": "You were invited to <b>{brand}</b>.\nWelcome.",
        "status_title": "<b>{brand}</b>",
        "plan": "Plan · <b>{plan}</b>",
        "days": "Left · <b>{days} d</b>",
        "inactive": "Status · <b>inactive</b>",
        "refs": "Referrals · <b>{n}</b>  ·  +{bonus}d each",
        "trial_avail": "7-day trial available.",
        "need_premium": "Premium required.",
        "btn_trial": "Trial 7 days",
        "btn_buy": "Buy Premium",
        "buy_title": "<b>Premium</b>\nChoose a plan. Pay via admin @zrdws.",
        "buy_plan_7": "7 days — 50₽",
        "buy_plan_30": "30 days — 200₽",
        "buy_plan_90": "90 days — 400₽",
        "buy_plan_365": "1 year — 800₽",
        "buy_order": "Order: <b>{days}d</b> / <b>{price}₽</b>\n\n1) Message admin\n2) Send this order\n3) Admin confirms payment\n\n<code>{order}</code>",
        "btn_write_admin": "Write admin",
        "btn_choose_plan": "Other plan",
        "admin_new_order": "🛒 <b>New order</b>\nFrom: <code>{uid}</code> {name}\nPlan: <b>{days}d</b> / <b>{price}₽</b>",
        "btn_order_paid": "✅ Order paid",
        "order_paid_ok": "✅ Order confirmed.\nUser <code>{uid}</code> got <b>{days}d</b> Premium.",
        "order_paid_user": "✅ Payment confirmed.\nYou received <b>{days}d</b> Premium.",
        "order_paid_done": "Already processed",
        "order_bad": "Invalid order",
        "btn_status": "Status",
        "btn_ref": "Referral",
        "btn_servers": "Servers",
        "btn_cab": "Cabinet",
        "btn_copy_key": "Copy key",
        "btn_copy_ref": "Copy referral",
        "btn_admin": "Admin",
        "btn_back": "Back",
        "trial_ok": "Trial activated for 7 days.",
        "trial_used": "Trial already used",
        "already": "Already active",
        "need_sub": "Active subscription required",
        "servers_title": "<b>Servers</b>",
        "servers_empty": "No servers yet.",
        "servers_note": "Use the key button below.",
        "ref_title": "<b>Referral</b>",
        "ref_body": "+{bonus} days per friend.\nInvited: <b>{n}</b>",
        "ref_bonus_inviter": "Referral bonus: +{bonus}d ({brand})",
        "pay_ok": "Premium activated.",
        "admin_title": "🛠 <b>{brand} Admin</b>",
        "admin_stats": "👥 Users: <b>{total}</b>\n🟢 Active: <b>{active}</b>\n💎 Premium: <b>{premium}</b>\n✨ Trial: <b>{trial}</b>\n🎁 Refs: <b>{refs}</b>\n🛰 Servers: <b>{servers}</b>\n📱 Devices: <b>{devices}</b>",
        "adm_stats": "📈 Stats",
        "adm_users": "👥 Users",
        "adm_servers": "🛰 Servers",
        "adm_active": "🟢 Active",
        "adm_broadcast": "📣 Broadcast",
        "adm_grant_self": "👑 Premium to me",
        "adm_grant_user": "➕ Days to user",
        "adm_trial": "🧪 Give trial",
        "adm_revoke": "⛔ Revoke",
        "adm_add_srv": "➕ Server",
        "adm_del_srv": "🗑 Delete server",
        "adm_find": "🔎 Find user",
        "adm_reset_devices": "📱 Reset devices",
        "adm_prices": "💰 Prices",
        "adm_orders_help": "ℹ️ How to grant",
        "adm_search": "🔎 Search",
        "prices_text": "<b>FluxVPN prices</b>\n\n• 7 days — <b>50₽</b>\n• 30 days — <b>200₽</b>\n• 90 days — <b>400₽</b>\n• 1 year — <b>800₽</b>",
        "orders_help": "User buys a plan and DMs you. After payment tap <b>Order paid</b>.",
        "device_reset_ok": "✅ User devices blocked. After sub refresh VPN configs disappear.",
        "ask_reset_devices": "Send Telegram ID to reset devices.",
        "ask_user_id": "Send user Telegram ID as a number.",
        "ask_broadcast": "Send broadcast text in one message.",
        "ask_server_name": "Send server name (flag allowed).\nExample: 🇩🇪 Germany",
        "ask_server_cfg": "Send raw config (vless/ss line).",
        "choose_days": "How many days?",
        "days_7": "7 days",
        "days_30": "30 days",
        "days_90": "90 days",
        "days_365": "365 days",
        "days_9999": "∞ Forever",
        "granted": "✅ Granted {days}d to <code>{id}</code>",
        "granted_self": "✅ Added {days}d Premium to you",
        "revoked": "⛔ Revoked <code>{id}</code>",
        "trial_given": "✅ Trial given to <code>{id}</code>",
        "not_found": "Not found",
        "broadcast_done": "Broadcast: OK {ok} / fail {fail}",
        "server_added": "✅ Server #{id} — {name}",
        "server_deleted": "🗑 Deleted",
        "cancel": "❌ Cancel",
        "cancelled": "Cancelled.",
        "users_title": "👥 <b>Latest users</b>",
        "active_title": "🟢 <b>Active</b>",
        "none_active": "No active subs.",
        "pick_server_del": "Pick server to delete:",
        "no_servers": "No servers.",
        "lang_set": "Language saved: English",
    },
}


def t(lang, key, **kw):
    lang = lang if lang in TEXTS else "ru"
    s = TEXTS[lang].get(key) or TEXTS["ru"].get(key) or key
    if kw:
        try:
            return s.format(**kw)
        except Exception:
            return s
    return s

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
            ("lang", "add column lang text"),
        ]:
            if col not in cols:
                conn.run("alter table users " + ddl)
        conn.run(
            "update users set referral_code = md5(random()::text || clock_timestamp()::text) "
            "where referral_code is null or referral_code = \'\'"
        )
        try:
            conn.run("create unique index if not exists idx_users_referral_code on users(referral_code)")
        except Exception:
            pass
        conn.run(
            "create table if not exists devices ("
            "id bigserial primary key, "
            "telegram_id bigint not null, "
            "device_hash text not null, "
            "device_name text not null default 'Device', "
            "user_agent text, "
            "last_ip text, "
            "created_at timestamptz not null default now(), "
            "last_seen timestamptz not null default now(), "
            "unique(telegram_id, device_hash))"
        )
        try:
            conn.run("create index if not exists idx_devices_tg on devices(telegram_id)")
        except Exception:
            pass
        dcols = {
            r[0]
            for r in conn.run(
                "select column_name from information_schema.columns where table_name='devices'"
            )
        }
        if dcols and "blocked" not in dcols:
            try:
                conn.run("alter table devices add column blocked boolean not null default false")
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

def fmt_until(expires):
    if expires is None:
        return "—"
    if getattr(expires, "tzinfo", None) is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return expires.strftime("%Y-%m-%d %H:%M:%S UTC")

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
        "lang": r[10] if len(r) > 10 else None,
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
    return "•"

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

def plan_label(user, lang="ru"):
    if is_active(user["status"], user["subscription_expires"]):
        return "Trial" if user["status"] == "trial" else "Premium"
    return "Free"

def lang_of(user):
    lg = (user or {}).get("lang")
    return lg if lg in ("ru", "en") else "ru"

def status_text(user):
    lang = lang_of(user)
    active = is_active(user["status"], user["subscription_expires"])
    lines = [
        t(lang, "status_title", brand=BRAND),
        "",
        html_lib.escape(display_name(user)),
        t(lang, "plan", plan=plan_label(user, lang)),
    ]
    if active:
        lines.append(t(lang, "days", days=days_left(user["subscription_expires"])))
    else:
        lines.append(t(lang, "inactive"))
    lines.append(t(lang, "refs", n=user.get("referral_count") or 0, bonus=REF_BONUS_DAYS))
    if not active and not user["trial_used"]:
        lines.extend(["", t(lang, "trial_avail")])
    elif not active:
        lines.extend(["", t(lang, "need_premium")])
    return chr(10).join(lines)

def kb_lang():
    return {
        "inline_keyboard": [
            [
                {"text": "🇷🇺 Русский", "callback_data": "lang_ru"},
                {"text": "🇬🇧 English", "callback_data": "lang_en"},
            ]
        ]
    }

def kb_main(user):
    lang = lang_of(user)
    rows = []
    active = is_active(user["status"], user["subscription_expires"])
    link = sub_link(user)
    rlink = ref_link(user)

    if (not user["trial_used"]) and (not active):
        rows.append([{"text": t(lang, "btn_trial"), "callback_data": "trial"}])
    rows.append([{"text": t(lang, "btn_buy"), "callback_data": "buy"}])

    row2 = [{"text": t(lang, "btn_status"), "callback_data": "mysub"}]
    if active:
        row2.append({"text": t(lang, "btn_servers"), "callback_data": "servers"})
    rows.append(row2)

    actions = []
    if link and active:
        actions.append({"text": t(lang, "btn_copy_key"), "copy_text": {"text": link}})
        actions.append({"text": t(lang, "btn_cab"), "url": link})
    if actions:
        rows.append(actions)

    ref_row = [{"text": t(lang, "btn_ref"), "callback_data": "referral"}]
    if rlink:
        ref_row.append({"text": t(lang, "btn_copy_ref"), "copy_text": {"text": rlink}})
    rows.append(ref_row)

    rows.append([{"text": "EN / RU", "callback_data": "lang_menu"}])
    if user["telegram_id"] == ADMIN_ID:
        rows.append([{"text": t(lang, "btn_admin"), "callback_data": "admin"}])
    return {"inline_keyboard": rows}

def kb_ref(user):
    lang = lang_of(user)
    rlink = ref_link(user)
    rows = []
    if rlink:
        rows.append([{"text": t(lang, "btn_copy_ref"), "copy_text": {"text": rlink}}])
    rows.append([{"text": t(lang, "btn_back"), "callback_data": "mysub"}])
    return {"inline_keyboard": rows}

def kb_servers(user):
    lang = lang_of(user)
    link = sub_link(user)
    rows = []
    if link:
        rows.append([
            {"text": t(lang, "btn_copy_key"), "copy_text": {"text": link}},
            {"text": t(lang, "btn_cab"), "url": link},
        ])
    rows.append([{"text": t(lang, "btn_back"), "callback_data": "mysub"}])
    return {"inline_keyboard": rows}

def kb_buy_plans(lang):
    return {
        "inline_keyboard": [
            [
                {"text": t(lang, "buy_plan_7"), "callback_data": "buy_7"},
                {"text": t(lang, "buy_plan_30"), "callback_data": "buy_30"},
            ],
            [
                {"text": t(lang, "buy_plan_90"), "callback_data": "buy_90"},
                {"text": t(lang, "buy_plan_365"), "callback_data": "buy_365"},
            ],
            [{"text": t(lang, "btn_back"), "callback_data": "mysub"}],
        ]
    }


def admin_dm_link(order_text=""):
    base = "https://t.me/" + ADMIN_USERNAME
    if order_text:
        return base + "?text=" + urllib.parse.quote(order_text)
    return base




def make_order_text(user, days):
    uname = display_name(user)
    price = plan_price(days)
    parts = [
        "FluxVPN order",
        "ID: " + str(user["telegram_id"]),
        "User: " + uname,
        "Plan: " + str(days) + " days Premium",
        "Price: " + str(price) + " RUB",
    ]
    return chr(10).join(parts)


def kb_admin_order(uid, days):
    return {
        "inline_keyboard": [
            [{
                "text": t("ru", "btn_order_paid"),
                "callback_data": "paid_" + str(int(uid)) + "_" + str(int(days)),
            }],
        ]
    }


def kb_buy_order(lang, order_text):
    return {
        "inline_keyboard": [
            [{"text": t(lang, "btn_write_admin"), "url": admin_dm_link(order_text)}],
            [{"text": t(lang, "btn_choose_plan"), "callback_data": "buy"}],
            [{"text": t(lang, "btn_back"), "callback_data": "mysub"}],
        ]
    }


def kb_cancel(lang):
    return {"inline_keyboard": [[{"text": t(lang, "cancel"), "callback_data": "adm_cancel"}]]}

def kb_admin(lang):
    return {
        "inline_keyboard": [
            [
                {"text": t(lang, "adm_stats"), "callback_data": "adm_stats"},
                {"text": t(lang, "adm_active"), "callback_data": "adm_active"},
            ],
            [
                {"text": t(lang, "adm_users"), "callback_data": "adm_users"},
                {"text": t(lang, "adm_find"), "callback_data": "adm_find"},
            ],
            [
                {"text": t(lang, "adm_grant_self"), "callback_data": "adm_grant_self"},
                {"text": t(lang, "adm_grant_user"), "callback_data": "adm_grant_user"},
            ],
            [
                {"text": t(lang, "adm_trial"), "callback_data": "adm_trial"},
                {"text": t(lang, "adm_revoke"), "callback_data": "adm_revoke"},
            ],
            [
                {"text": t(lang, "adm_reset_devices"), "callback_data": "adm_reset_devices"},
                {"text": t(lang, "adm_servers"), "callback_data": "adm_servers"},
            ],
            [
                {"text": t(lang, "adm_add_srv"), "callback_data": "adm_add_srv"},
                {"text": t(lang, "adm_del_srv"), "callback_data": "adm_del_srv"},
            ],
            [
                {"text": t(lang, "adm_broadcast"), "callback_data": "adm_broadcast"},
                {"text": t(lang, "adm_prices"), "callback_data": "adm_prices"},
            ],
            [
                {"text": t(lang, "adm_orders_help"), "callback_data": "adm_orders_help"},
            ],
            [{"text": t(lang, "btn_back"), "callback_data": "mysub"}],
        ]
    }


def kb_days(prefix, lang):
    return {
        "inline_keyboard": [
            [
                {"text": t(lang, "days_7"), "callback_data": prefix + "_7"},
                {"text": t(lang, "days_30"), "callback_data": prefix + "_30"},
            ],
            [
                {"text": t(lang, "days_90"), "callback_data": prefix + "_90"},
                {"text": t(lang, "days_365"), "callback_data": prefix + "_365"},
            ],
            [{"text": t(lang, "days_9999"), "callback_data": prefix + "_9999"}],
            [{"text": t(lang, "cancel"), "callback_data": "adm_cancel"}],
        ]
    }


def send(chat_id, text, markup=None):
    p = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
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

def ensure_user(conn, tg_id, username=None, full_name=None, ref_code=None, lang=None):
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
        "insert into users (telegram_id, status, trial_used, sub_token, referral_code, referred_by, referral_count, username, full_name, lang) "
        "values (:id, 'free', false, :st, :rc, :rb, 0, :u, :f, :lg)",
        id=tg_id,
        st=sub_token,
        rc=referral_code,
        rb=referred_by,
        u=username,
        f=full_name,
        lg=lang,
    )
    user = get_user(conn, tg_id)
    if referred_by:
        apply_referral_bonus(conn, referred_by, tg_id)
        user = get_user(conn, tg_id)
    return user

def set_lang(conn, tg_id, lang):
    conn.run("update users set lang=:l where telegram_id=:id", l=lang, id=tg_id)
    return get_user(conn, tg_id)

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
    expires = base + timedelta(days=int(days))
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
            t(
                lang_of(inviter),
                "ref_bonus_inviter",
                bonus=REF_BONUS_DAYS,
                brand=BRAND,
            ),
        )
    except Exception:
        pass

def get_servers(conn):
    ensure_schema(conn)
    return conn.run("select id, raw_config, custom_name from server_pool order by id")

def servers_list_text(conn, lang):
    rows = get_servers(conn)
    if not rows:
        return t(lang, "servers_empty")
    lines = [t(lang, "servers_title", brand=BRAND), ""]
    for r in rows:
        lines.append(extract_flag(r[2]) + " <b>" + html_lib.escape(str(r[2])) + "</b>")
    lines.extend(["", t(lang, "servers_note")])
    return "\n".join(lines)

def admin_stats_text(conn, lang):
    ensure_schema(conn)
    total = conn.run("select count(*) from users")[0][0]
    servers = conn.run("select count(*) from server_pool")[0][0]
    try:
        devices = conn.run("select count(*) from devices where coalesce(blocked,false)=false")[0][0]
    except Exception:
        devices = 0
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
        t(lang, "admin_title", brand=BRAND)
        + "\n\n"
        + t(
            lang,
            "admin_stats",
            total=total,
            active=active,
            premium=premium,
            trial=trial,
            refs=refs,
            servers=servers,
            devices=devices,
        )
    )

def admin_users_text(conn, lang, limit=12):
    rows = conn.run(USER_SELECT + " order by id desc limit :n", n=limit)
    lines = [t(lang, "users_title"), ""]
    if not rows:
        lines.append(t(lang, "not_found"))
        return "\n".join(lines)
    for r in rows:
        u = user_row(r)
        left = (
            days_left(u["subscription_expires"])
            if is_active(u["status"], u["subscription_expires"])
            else 0
        )
        lines.append(
            "• <code>"
            + str(u["telegram_id"])
            + "</code> "
            + html_lib.escape(display_name(u))
            + " — <b>"
            + plan_label(u, lang)
            + "</b>"
            + (" · " + str(left) + "d" if left else "")
        )
    return "\n".join(lines)

def admin_active_text(conn, lang):
    rows = conn.run(USER_SELECT + " order by subscription_expires desc nulls last limit 40")
    lines = [t(lang, "active_title"), ""]
    n = 0
    for r in rows:
        u = user_row(r)
        if not is_active(u["status"], u["subscription_expires"]):
            continue
        n += 1
        lines.append(
            "• <code>"
            + str(u["telegram_id"])
            + "</code> "
            + html_lib.escape(display_name(u))
            + " — "
            + plan_label(u, lang)
            + " · "
            + str(days_left(u["subscription_expires"]))
            + "d"
        )
    if n == 0:
        lines.append(t(lang, "none_active"))
    return "\n".join(lines)

def admin_servers_text(conn, lang):
    rows = get_servers(conn)
    lines = [t(lang, "servers_title", brand=BRAND), ""]
    if not rows:
        lines.append(t(lang, "no_servers"))
    else:
        for r in rows:
            lines.append(
                extract_flag(r[2])
                + " <b>#"
                + str(r[0])
                + "</b> — "
                + html_lib.escape(str(r[2]))
            )
    return "\n".join(lines)

def kb_delete_servers(conn, lang):
    rows = get_servers(conn)
    if not rows:
        return None, t(lang, "no_servers")
    ik = []
    for r in rows:
        ik.append(
            [
                {
                    "text": extract_flag(r[2]) + " #" + str(r[0]) + " " + str(r[2])[:28],
                    "callback_data": "adel_" + str(r[0]),
                }
            ]
        )
    ik.append([{"text": t(lang, "cancel"), "callback_data": "adm_cancel"}])
    return {"inline_keyboard": ik}, t(lang, "pick_server_del")

def clear_pending(tg_id):
    PENDING.pop(tg_id, None)

def handle_start(conn, msg, ref_code=None):
    tg_id = msg["from"]["id"]
    chat = msg["chat"]["id"]
    username, full_name = from_user_meta(msg.get("from") or {})
    existing = get_user(conn, tg_id)
    is_new = existing is None
    user = ensure_user(
        conn, tg_id, username=username, full_name=full_name, ref_code=ref_code if is_new else None
    )
    if not user.get("lang"):
        PENDING[tg_id] = {"action": "choose_lang", "ref_new": bool(is_new and ref_code)}
        send(chat, TEXTS["ru"]["choose_lang"], kb_lang())
        return
    lang = lang_of(user)
    if is_new and ref_code:
        text = t(lang, "welcome_ref", brand=BRAND) + "\n\n" + status_text(user)
    else:
        text = t(lang, "welcome", brand=BRAND) + "\n\n" + status_text(user)
    send(chat, text, kb_main(user))

def from_user_meta(u):
    username = u.get("username")
    full_name = ((u.get("first_name") or "") + " " + (u.get("last_name") or "")).strip() or None
    return username, full_name

def open_admin(conn, chat, mid, lang):
    edit(chat, mid, admin_stats_text(conn, lang), kb_admin(lang))

def handle_cb(conn, cq):
    data = cq.get("data") or ""
    tg_id = cq["from"]["id"]
    chat = cq["message"]["chat"]["id"]
    mid = cq["message"]["message_id"]
    username, full_name = from_user_meta(cq.get("from") or {})
    user = ensure_user(conn, tg_id, username=username, full_name=full_name)
    lang = lang_of(user)

    if data in ("lang_ru", "lang_en"):
        lg = "ru" if data.endswith("ru") else "en"
        user = set_lang(conn, tg_id, lg)
        lang = lg
        pend = PENDING.pop(tg_id, None) or {}
        prefix = t(lang, "welcome_ref", brand=BRAND) if pend.get("ref_new") else t(lang, "welcome", brand=BRAND)
        edit(chat, mid, t(lang, "lang_set") + "\n\n" + prefix + "\n\n" + status_text(user), kb_main(user))
        ans(cq["id"])
        return

    if data == "lang_menu":
        edit(chat, mid, TEXTS["ru"]["choose_lang"], kb_lang())
        ans(cq["id"])
        return

    if data == "mysub":
        clear_pending(tg_id)
        edit(chat, mid, status_text(user), kb_main(user))
        ans(cq["id"])
        return

    if data == "referral":
        text = (
            t(lang, "ref_title")
            + chr(10) + chr(10)
            + t(lang, "ref_body", bonus=REF_BONUS_DAYS, n=user.get("referral_count") or 0)
        )
        edit(chat, mid, text, kb_ref(user))
        ans(cq["id"])
        return

    if data == "trial":
        if is_active(user["status"], user["subscription_expires"]):
            ans(cq["id"], t(lang, "already"), True)
            return
        if user["trial_used"]:
            ans(cq["id"], t(lang, "trial_used"), True)
            return
        exp = utcnow() + timedelta(days=7)
        conn.run(
            "update users set status='trial', trial_used=true, subscription_expires=:e where telegram_id=:id",
            e=exp,
            id=tg_id,
        )
        user = get_user(conn, tg_id)
        edit(chat, mid, t(lang, "trial_ok") + "\n\n" + status_text(user), kb_main(user))
        ans(cq["id"], "OK")
        return

    if data == "buy":
        edit(chat, mid, t(lang, "buy_title"), kb_buy_plans(lang))
        ans(cq["id"])
        return

    if data.startswith("buy_") and data[4:].isdigit():
        days = int(data.split("_", 1)[1])
        if days not in (7, 30, 90, 365):
            ans(cq["id"])
            return
        order = make_order_text(user, days)
        text = t(lang, "buy_order", days=days, price=plan_price(days), order=html_lib.escape(order))
        edit(chat, mid, text, kb_buy_order(lang, order))
        # notify admin in background-ish
        try:
            uname = html_lib.escape(display_name(user))
            send(
                ADMIN_ID,
                t(
                    "ru",
                    "admin_new_order",
                    uid=tg_id,
                    name=uname,
                    days=days, price=plan_price(days),
                ),
                kb_admin_order(tg_id, days),
            )
        except Exception:
            pass
        ans(cq["id"])
        return

    if data == "servers":
        if not is_active(user["status"], user["subscription_expires"]):
            ans(cq["id"], t(lang, "need_sub"), True)
            return
        edit(chat, mid, servers_list_text(conn, lang), kb_servers(user))
        ans(cq["id"])
        return

    if data == "admin":
        if tg_id != ADMIN_ID:
            ans(cq["id"])
            return
        clear_pending(tg_id)
        open_admin(conn, chat, mid, lang)
        ans(cq["id"])
        return

    if tg_id != ADMIN_ID:
        ans(cq["id"])
        return


    if data.startswith("paid_"):
        if tg_id != ADMIN_ID:
            ans(cq["id"])
            return
        parts = data.split("_")
        # paid_<uid>_<days>
        if len(parts) != 3 or (not parts[1].isdigit()) or (not parts[2].isdigit()):
            ans(cq["id"], t(lang, "order_bad"), True)
            return
        uid = int(parts[1])
        days = int(parts[2])
        if days not in (7, 30, 90, 365, 9999):
            # allow common grant lengths too
            if days <= 0 or days > 4000:
                ans(cq["id"], t(lang, "order_bad"), True)
                return
        ensure_user(conn, uid)
        target = extend_subscription(conn, uid, days, status="premium")
        # update admin message
        edit(
            chat,
            mid,
            t(lang, "order_paid_ok", uid=uid, days=days),
            {"inline_keyboard": []},
        )
        try:
            tlang = lang_of(target or {})
            send(
                uid,
                t(tlang, "order_paid_user", days=days) + chr(10) + chr(10) + status_text(target),
                kb_main(target),
            )
        except Exception:
            pass
        ans(cq["id"], "OK")
        return

    if data == "adm_cancel":
        clear_pending(tg_id)
        open_admin(conn, chat, mid, lang)
        ans(cq["id"], t(lang, "cancelled"))
        return

    if data == "adm_stats":
        open_admin(conn, chat, mid, lang)
        ans(cq["id"])
        return
    if data == "adm_users":
        edit(chat, mid, admin_users_text(conn, lang), kb_admin(lang))
        ans(cq["id"])
        return
    if data == "adm_servers":
        edit(chat, mid, admin_servers_text(conn, lang), kb_admin(lang))
        ans(cq["id"])
        return
    if data == "adm_active":
        edit(chat, mid, admin_active_text(conn, lang), kb_admin(lang))
        ans(cq["id"])
        return

    if data == "adm_grant_self":
        edit(chat, mid, t(lang, "choose_days"), kb_days("gself", lang))
        ans(cq["id"])
        return

    if data.startswith("gself_"):
        days = int(data.split("_", 1)[1])
        extend_subscription(conn, tg_id, days, status="premium")
        user = get_user(conn, tg_id)
        edit(
            chat,
            mid,
            t(lang, "granted_self", days=days) + "\n\n" + status_text(user),
            kb_admin(lang),
        )
        ans(cq["id"], "OK")
        return

    if data == "adm_grant_user":
        PENDING[tg_id] = {"action": "grant_user_id"}
        edit(chat, mid, t(lang, "ask_user_id"), kb_cancel(lang))
        ans(cq["id"])
        return

    if data.startswith("guser_"):
        # guser_<id>_<days>
        parts = data.split("_")
        if len(parts) == 3 and parts[1].isdigit():
            uid = int(parts[1])
            days = int(parts[2])
            ensure_user(conn, uid)
            extend_subscription(conn, uid, days, status="premium")
            edit(chat, mid, t(lang, "granted", days=days, id=uid), kb_admin(lang))
            try:
                send(uid, t(lang_of(get_user(conn, uid) or user), "granted_self", days=days))
            except Exception:
                pass
            ans(cq["id"], "OK")
            return

    if data == "adm_trial":
        PENDING[tg_id] = {"action": "trial_user_id"}
        edit(chat, mid, t(lang, "ask_user_id"), kb_cancel(lang))
        ans(cq["id"])
        return

    if data == "adm_revoke":
        PENDING[tg_id] = {"action": "revoke_user_id"}
        edit(chat, mid, t(lang, "ask_user_id"), kb_cancel(lang))
        ans(cq["id"])
        return

    if data == "adm_find":
        PENDING[tg_id] = {"action": "find_user_id"}
        edit(chat, mid, t(lang, "ask_user_id"), kb_cancel(lang))
        ans(cq["id"])
        return


    if data == "adm_prices":
        edit(chat, mid, t(lang, "prices_text"), kb_admin(lang))
        ans(cq["id"])
        return

    if data == "adm_orders_help":
        edit(chat, mid, t(lang, "orders_help"), kb_admin(lang))
        ans(cq["id"])
        return

    if data == "adm_reset_devices":
        PENDING[tg_id] = {"action": "reset_devices_id"}
        edit(chat, mid, t(lang, "ask_reset_devices"), kb_cancel(lang))
        ans(cq["id"])
        return

    if data == "adm_broadcast":
        PENDING[tg_id] = {"action": "broadcast"}
        edit(chat, mid, t(lang, "ask_broadcast"), kb_cancel(lang))
        ans(cq["id"])
        return

    if data == "adm_add_srv":
        PENDING[tg_id] = {"action": "add_srv_name"}
        edit(chat, mid, t(lang, "ask_server_name"), kb_cancel(lang))
        ans(cq["id"])
        return

    if data == "adm_del_srv":
        markup, text = kb_delete_servers(conn, lang)
        if not markup:
            edit(chat, mid, text, kb_admin(lang))
        else:
            edit(chat, mid, text, markup)
        ans(cq["id"])
        return

    if data.startswith("adel_"):
        sid = data.split("_", 1)[1]
        if sid.isdigit():
            conn.run("delete from server_pool where id=:id", id=int(sid))
            edit(chat, mid, t(lang, "server_deleted"), kb_admin(lang))
            ans(cq["id"], "OK")
            return

    ans(cq["id"])

def handle_admin_text(conn, msg):
    tg_id = msg["from"]["id"]
    chat = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()
    user = get_user(conn, tg_id) or ensure_user(conn, tg_id)
    lang = lang_of(user)
    pend = PENDING.get(tg_id) or {}
    action = pend.get("action")
    if not action:
        return False

    if action == "grant_user_id":
        if not text.isdigit():
            send(chat, t(lang, "ask_user_id"), kb_cancel(lang))
            return True
        uid = int(text)
        PENDING[tg_id] = {"action": "grant_user_days", "uid": uid}
        send(chat, t(lang, "choose_days"), kb_days("guser_" + str(uid), lang))
        return True

    if action == "trial_user_id":
        if not text.isdigit():
            send(chat, t(lang, "ask_user_id"), kb_cancel(lang))
            return True
        uid = int(text)
        ensure_user(conn, uid)
        exp = utcnow() + timedelta(days=7)
        conn.run(
            "update users set status='trial', trial_used=true, subscription_expires=:e where telegram_id=:id",
            e=exp,
            id=uid,
        )
        clear_pending(tg_id)
        send(chat, t(lang, "trial_given", id=uid), kb_admin(lang))
        return True

    if action == "revoke_user_id":
        if not text.isdigit():
            send(chat, t(lang, "ask_user_id"), kb_cancel(lang))
            return True
        uid = int(text)
        conn.run(
            "update users set status='free', subscription_expires=null where telegram_id=:id",
            id=uid,
        )
        clear_pending(tg_id)
        send(chat, t(lang, "revoked", id=uid), kb_admin(lang))
        return True

    if action == "find_user_id":
        if not text.isdigit():
            send(chat, t(lang, "ask_user_id"), kb_cancel(lang))
            return True
        u = get_user(conn, int(text))
        clear_pending(tg_id)
        send(chat, status_text(u) if u else t(lang, "not_found"), kb_admin(lang))
        return True

    if action == "broadcast":
        ids = [r[0] for r in conn.run("select telegram_id from users")]
        ok = fail = 0
        for i in ids:
            try:
                send(i, "📢 <b>" + BRAND + "</b>\n\n" + html_lib.escape(text))
                ok += 1
                time.sleep(0.04)
            except Exception:
                fail += 1
        clear_pending(tg_id)
        send(chat, t(lang, "broadcast_done", ok=ok, fail=fail), kb_admin(lang))
        return True

    if action == "add_srv_name":
        PENDING[tg_id] = {"action": "add_srv_cfg", "name": text}
        send(chat, t(lang, "ask_server_cfg"), kb_cancel(lang))
        return True

    if action == "add_srv_cfg":
        name = pend.get("name") or "Server"
        r = conn.run(
            "insert into server_pool (raw_config, custom_name) values (:c, :n) returning id, custom_name",
            c=text,
            n=name,
        )
        clear_pending(tg_id)
        send(
            chat,
            t(lang, "server_added", id=r[0][0], name=html_lib.escape(r[0][1])),
            kb_admin(lang),
        )
        return True

    return False

def handle_cmd(conn, msg):
    text = (msg.get("text") or "").strip()
    tg_id = msg["from"]["id"]
    if tg_id == ADMIN_ID and tg_id in PENDING:
        if handle_admin_text(conn, msg):
            return
    if not text.startswith("/"):
        if tg_id == ADMIN_ID and handle_admin_text(conn, msg):
            return
        return
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
        if not user.get("lang"):
            send(chat, TEXTS["ru"]["choose_lang"], kb_lang())
            return
        send(chat, status_text(user), kb_main(user))
        return
    if tg_id == ADMIN_ID and cmd == "/admin":
        user = get_user(conn, tg_id) or ensure_user(conn, tg_id)
        send(chat, admin_stats_text(conn, lang_of(user)), kb_admin(lang_of(user)))

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
    lang = lang_of(user)
    send(chat, t(lang, "pay_ok") + "\n\n" + status_text(user), kb_main(user))

def process(conn, upd):
    if "callback_query" in upd:
        handle_cb(conn, upd["callback_query"])
        return
    msg = upd.get("message") or upd.get("edited_message")
    if not msg:
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



def device_limit_for(user):
    if not is_active(user["status"], user["subscription_expires"]):
        return 0
    if user["status"] == "trial":
        return TRIAL_DEVICE_LIMIT
    if user["status"] == "premium":
        return PREMIUM_DEVICE_LIMIT
    return 0


def client_ip(handler):
    xff = handler.headers.get("X-Forwarded-For") or handler.headers.get("x-forwarded-for") or ""
    if xff:
        return xff.split(",")[0].strip()[:64]
    try:
        return (handler.client_address[0] or "")[:64]
    except Exception:
        return ""


def device_hash_from(ua, ip):
    import hashlib
    raw = (ua or "unknown") + "|" + (ip or "")
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:32]


def device_name_from(ua):
    s = (ua or "").strip()
    if not s:
        return "Unknown device"
    low = s.lower()
    if "hiddify" in low:
        return "Hiddify"
    if "happ" in low:
        return "Happ"
    if "v2rayng" in low or "v2ray" in low:
        return "v2rayNG"
    if "clash" in low:
        return "Clash"
    if "streisand" in low:
        return "Streisand"
    if "shadowrocket" in low:
        return "Shadowrocket"
    if "nekobox" in low:
        return "NekoBox"
    if "sing-box" in low or "sfa" in low:
        return "sing-box"
    if "okhttp" in low:
        return "Android client"
    if "cfnetwork" in low or "darwin" in low:
        return "iOS client"
    # short clean label
    name = s.split("/")[0].split(" ")[0]
    return (name or "Device")[:40]



def list_devices(conn, telegram_id):
    return conn.run(
        "select id, device_name, user_agent, last_ip, created_at, last_seen, device_hash "
        "from devices where telegram_id=:tg and coalesce(blocked,false)=false order by last_seen desc",
        tg=telegram_id,
    )


def count_devices(conn, telegram_id):
    return int(
        conn.run(
            "select count(*) from devices where telegram_id=:tg and coalesce(blocked,false)=false",
            tg=telegram_id,
        )[0][0]
    )


def touch_device(conn, user, ua, ip):
    limit = device_limit_for(user)
    tg = user["telegram_id"]
    dhash = device_hash_from(ua, ip)
    name = device_name_from(ua)
    existing = conn.run(
        "select id, coalesce(blocked,false) from devices where telegram_id=:tg and device_hash=:h limit 1",
        tg=tg,
        h=dhash,
    )
    if existing:
        if bool(existing[0][1]):
            return False, count_devices(conn, tg), limit, "blocked"
        conn.run(
            "update devices set last_seen=now(), user_agent=:ua, last_ip=:ip, device_name=:n where id=:id",
            ua=(ua or "")[:300],
            ip=ip or "",
            n=name,
            id=existing[0][0],
        )
        return True, count_devices(conn, tg), limit, "ok"

    cnt = count_devices(conn, tg)
    if cnt >= limit:
        return False, cnt, limit, "limit"

    try:
        conn.run(
            "insert into devices (telegram_id, device_hash, device_name, user_agent, last_ip, blocked) "
            "values (:tg, :h, :n, :ua, :ip, false)",
            tg=tg, h=dhash, n=name, ua=(ua or "")[:300], ip=ip or "",
        )
    except Exception:
        conn.run(
            "insert into devices (telegram_id, device_hash, device_name, user_agent, last_ip) "
            "values (:tg, :h, :n, :ua, :ip)",
            tg=tg, h=dhash, n=name, ua=(ua or "")[:300], ip=ip or "",
        )
    return True, count_devices(conn, tg), limit, "ok"


def delete_device(conn, telegram_id, device_id):
    try:
        rows = conn.run(
            "update devices set blocked=true, last_seen=now() where id=:id and telegram_id=:tg returning id",
            id=int(device_id), tg=telegram_id,
        )
        if rows:
            return True
    except Exception:
        pass
    rows = conn.run(
        "delete from devices where id=:id and telegram_id=:tg returning id",
        id=int(device_id), tg=telegram_id,
    )
    return bool(rows)


def reset_user_devices(conn, telegram_id):
    try:
        conn.run(
            "update devices set blocked=true where telegram_id=:tg and coalesce(blocked,false)=false",
            tg=int(telegram_id),
        )
    except Exception:
        conn.run("delete from devices where telegram_id=:tg", tg=int(telegram_id))


def limit_sub_body(lang="ru"):
    title = "FluxVPN | Device limit" if lang == "en" else "FluxVPN | Лимит устройств"
    remark = urllib.parse.quote(title, safe="")
    return (
        "vless://00000000-0000-0000-0000-000000000000@127.0.0.1:1"
        "?encryption=none&security=none&type=tcp#" + remark + chr(10)
    )


def blocked_sub_body(lang="ru"):
    title = "FluxVPN | Device removed" if lang == "en" else "FluxVPN | Устройство удалено"
    remark = urllib.parse.quote(title, safe="")
    return (
        "vless://00000000-0000-0000-0000-000000000000@127.0.0.1:1"
        "?encryption=none&security=none&type=tcp#" + remark + chr(10)
    )


def render_denied():
    return (
        "<!DOCTYPE html><html lang=ru><head><meta charset=utf-8>"
        "<meta name=viewport content=\"width=device-width,initial-scale=1\">"
        "<meta name=robots content=noindex,nofollow>"
        "<title>FluxVPN</title><style>"
        "*{box-sizing:border-box}html,body{height:100%}"
        "body{margin:0;display:grid;place-items:center;background:#090909;color:#f2f2f2;"
        "font-family:Inter,SF Pro Text,-apple-system,system-ui,sans-serif}"
        ".box{width:min(420px,90vw);text-align:center;padding:36px 28px;border:1px solid #1f1f1f;"
        "border-radius:24px;background:linear-gradient(180deg,#121212,#0c0c0c)}"
        ".mark{width:42px;height:42px;border-radius:14px;margin:0 auto 18px;display:grid;place-items:center;"
        "background:#171717;border:1px solid #2a2a2a;font-weight:800;letter-spacing:.04em;font-size:12px}"
        "h1{margin:0 0 10px;font-size:22px;font-weight:650;letter-spacing:-.02em}"
        "p{margin:0;color:#8f8f8f;font-size:14px;line-height:1.6}"
        "</style></head><body><div class=box>"
        "<div class=mark>FX</div><h1>Нет доступа</h1>"
        "<p>Подписка неактивна. Открой бота FluxVPN и продли доступ.</p>"
        "</div></body></html>"
    )


def render_cabinet(user, servers, devices=None, device_limit=0):
    if devices is None:
        devices = []
    active = is_active(user["status"], user["subscription_expires"])
    left = days_left(user["subscription_expires"]) if active else 0
    until = fmt_until(user["subscription_expires"]) if active else "—"
    link = sub_link(user) or ""
    status_txt = "Active" if active else "Inactive"
    token = html_lib.escape(user.get("sub_token") or "")
    dev_count = len(devices)

    rows = []
    for s in servers:
        flag = extract_flag(s[2])
        title = html_lib.escape(str(s[2]))
        rows.append(
            "<div class=node>"
            "<div class=nleft><div class=dot></div>"
            "<div class=flag>" + flag + "</div>"
            "<div class=nmeta><div class=nname>" + title + "</div></div></div>"
            "<div class=badge>Online</div></div>"
        )
    servers_html = "".join(rows) if rows else "<div class=empty>Пока нет локаций</div>"

    dev_rows = []
    for d in devices:
        did = str(d[0])
        dname = html_lib.escape(str(d[1] or "Device"))
        seen = d[5]
        try:
            seen_s = seen.strftime("%Y-%m-%d %H:%M") if hasattr(seen, "strftime") else str(seen)[:16]
        except Exception:
            seen_s = "—"
        del_url = "/sub/" + token + "/device/" + did + "/delete"
        dev_rows.append(
            "<div class=node>"
            "<div class=nleft><div class=dot></div>"
            "<div class=nmeta><div class=nname>" + dname + "</div>"
            "<div class=nsub>" + html_lib.escape(seen_s) + "</div></div></div>"
            "<a class=xbtn href=\"" + del_url + "\">Удалить</a></div>"
        )
    devices_html = "".join(dev_rows) if dev_rows else "<div class=empty>Нет привязанных устройств</div>"

    happ = "happ://add/" + urllib.parse.quote(link, safe="") if link else "#"
    link_js = json.dumps(link)
    happ_js = json.dumps(happ)
    css = (
        "*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}"
        "html,body{margin:0;min-height:100%;background:#090909;color:#f3f3f3;"
        "font-family:Inter,SF Pro Text,-apple-system,BlinkMacSystemFont,system-ui,sans-serif}"
        "body{background:radial-gradient(900px 420px at 50% -10%,rgba(255,255,255,.06),transparent 60%),#090909}"
        ".wrap{width:min(680px,100%);margin:0 auto;padding:28px 18px 56px}"
        ".nav{display:flex;align-items:center;justify-content:space-between;margin-bottom:22px}"
        ".brand{display:flex;align-items:center;gap:10px}"
        ".logo{width:34px;height:34px;border-radius:11px;display:grid;place-items:center;"
        "background:#141414;border:1px solid #242424;font-size:11px;font-weight:800;letter-spacing:.06em}"
        ".brand b{font-size:14px;font-weight:700;letter-spacing:.08em;text-transform:uppercase}"
        ".chip{font-size:12px;color:#cfcfcf;border:1px solid #2a2a2a;background:#121212;border-radius:999px;padding:7px 11px}"
        ".hero{padding:22px;border-radius:22px;border:1px solid #1e1e1e;background:linear-gradient(180deg,#121212,#0d0d0d);margin-bottom:14px}"
        ".hero h1{margin:0 0 6px;font-size:28px;line-height:1.1;letter-spacing:-.03em;font-weight:680}"
        ".hero p{margin:0;color:#8d8d8d;font-size:13px;line-height:1.5}"
        ".stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:18px}"
        ".stat{padding:14px;border-radius:16px;background:#0c0c0c;border:1px solid #1c1c1c}"
        ".stat span{display:block;color:#8a8a8a;font-size:11px;margin-bottom:6px}"
        ".stat b{display:block;font-size:18px;font-weight:700;letter-spacing:-.02em}"
        ".tabs{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 12px}"
        ".tab{border:1px solid #2a2a2a;background:#101010;color:#e8e8e8;padding:10px 14px;border-radius:999px;cursor:pointer;font-weight:600;font-size:13px}"
        ".tab.on{background:#f2f2f2;color:#0a0a0a;border-color:#f2f2f2}"
        ".panel{display:none}.panel.on{display:block}"
        ".card{padding:16px;border-radius:20px;border:1px solid #1e1e1e;background:#0f0f0f;margin-bottom:12px}"
        ".head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:12px}"
        ".head h2{margin:0;font-size:14px;font-weight:650;color:#ececec}"
        ".muted{color:#7d7d7d;font-size:12px}"
        ".actions{display:grid;grid-template-columns:1.2fr 1fr 1fr;gap:8px}"
        ".btn{appearance:none;border:0;cursor:pointer;border-radius:13px;padding:12px 10px;font-weight:650;font-size:13px;"
        "text-decoration:none;display:flex;align-items:center;justify-content:center;color:#0a0a0a;background:#f2f2f2}"
        ".btn.ghost{background:transparent;color:#f0f0f0;border:1px solid #2a2a2a}"
        ".toast{display:none;margin-top:10px;color:#bdbdbd;font-size:12px;text-align:center}.toast.show{display:block}"
        ".node{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 2px;border-bottom:1px solid #171717}"
        ".node:last-child{border-bottom:0}"
        ".nleft{display:flex;align-items:center;gap:10px;min-width:0}"
        ".dot{width:7px;height:7px;border-radius:50%;background:#f5f5f5;box-shadow:0 0 0 4px rgba(255,255,255,.06);flex:0 0 auto}"
        ".flag{width:32px;height:32px;border-radius:10px;display:grid;place-items:center;background:#141414;border:1px solid #222;font-size:15px}"
        ".nname{font-size:14px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:46vw}"
        ".nsub{color:#7a7a7a;font-size:11px;margin-top:2px}"
        ".badge{font-size:11px;color:#bdbdbd;border:1px solid #262626;border-radius:999px;padding:5px 9px}"
        ".xbtn{font-size:12px;color:#111;background:#efefef;text-decoration:none;border-radius:999px;padding:7px 10px;font-weight:650}"
        ".empty{color:#7a7a7a;font-size:13px;padding:8px 0}"
        ".note{color:#8a8a8a;font-size:12px;line-height:1.5;margin:0 0 12px}"
        ".foot{margin-top:18px;text-align:center;color:#5f5f5f;font-size:11px;letter-spacing:.08em;text-transform:uppercase}"
        "@media(max-width:560px){.stats{grid-template-columns:1fr 1fr}.actions{grid-template-columns:1fr}.hero h1{font-size:24px}}"
    )
    js = (
        "const SUB=" + link_js + ";const HAPP=" + happ_js + ";"
        "const toast=document.getElementById('toast');"
        "function flash(m){toast.textContent=m;toast.classList.add('show');clearTimeout(window.__t);window.__t=setTimeout(()=>toast.classList.remove('show'),1600)}"
        "async function copySub(){try{await navigator.clipboard.writeText(SUB);flash('Скопировано')}catch(e){flash('Ошибка')}}"
        "function openHapp(){if(HAPP&&HAPP!=='#')location.href=HAPP;else flash('Недоступно')}"
        "document.querySelectorAll('.tab').forEach(btn=>btn.onclick=()=>{document.querySelectorAll('.tab').forEach(b=>b.classList.remove('on'));"
        "document.querySelectorAll('.panel').forEach(p=>p.classList.remove('on'));btn.classList.add('on');"
        "document.getElementById(btn.dataset.tab).classList.add('on')});"
    )
    return (
        "<!DOCTYPE html><html lang=ru><head><meta charset=utf-8>"
        "<meta name=viewport content=\"width=device-width,initial-scale=1,viewport-fit=cover\">"
        "<meta name=robots content=noindex,nofollow,noarchive><meta name=referrer content=no-referrer>"
        "<title>FluxVPN</title><style>" + css + "</style></head><body><div class=wrap>"
        "<div class=nav><div class=brand><div class=logo>FX</div><b>FluxVPN</b></div>"
        "<div class=chip>" + status_txt + "</div></div>"
        "<section class=hero><h1>Кабинет</h1>"
        "<p>Статус, локации и устройства. Ключ подписки не показывается — только копирование.</p>"
        "<div class=stats>"
        "<div class=stat><span>Осталось</span><b>" + str(left) + " дн</b></div>"
        "<div class=stat><span>До</span><b style=\"font-size:12px\">" + html_lib.escape(until) + "</b></div>"
        "<div class=stat><span>Локации</span><b>" + str(len(servers)) + "</b></div>"
        "<div class=stat><span>Устройства</span><b>" + str(dev_count) + "/" + str(int(device_limit or 0)) + "</b></div>"
        "</div></section>"
        "<div class=tabs>"
        "<button class=\"tab on\" type=button data-tab=p-home>Обзор</button>"
        "<button class=tab type=button data-tab=p-loc>Локации</button>"
        "<button class=tab type=button data-tab=p-dev>Устройства</button>"
        "</div>"
        "<section id=p-home class=\"panel on\">"
        "<div class=card><div class=head><h2>Подключение</h2><span class=muted>private</span></div>"
        "<div class=actions>"
        "<button class=btn id=copyBtn type=button>Скопировать ключ</button>"
        "<button class=\"btn ghost\" id=happBtn type=button>Happ</button>"
        "<button class=\"btn ghost\" type=button onclick=\"history.replaceState({},'', '/');flash('OK')\">Скрыть</button>"
        "</div><div class=toast id=toast></div></div></section>"
        "<section id=p-loc class=panel><div class=card><div class=head><h2>Локации</h2>"
        "<span class=muted>" + str(len(servers)) + "</span></div>" + servers_html + "</div></section>"
        "<section id=p-dev class=panel><div class=card><div class=head><h2>Устройства</h2>"
        "<span class=muted>" + str(dev_count) + " / " + str(int(device_limit or 0)) + "</span></div>"
        "<p class=note>Trial — 2, Premium — 4. Удаление блокирует устройство: обнови подписку в VPN-клиенте — конфиги пропадут.</p>"
        + devices_html + "</div></section>"
        "<div class=foot>FluxVPN</div></div><script>" + js
        + "document.getElementById('copyBtn').onclick=copySub;"
        + "document.getElementById('happBtn').onclick=openHapp;"
        + "</script></body></html>"
    )


def re_fullmatch_token(token):
    import re as _re
    return bool(_re.fullmatch(r"[A-Za-z0-9_-]+", token or ""))


def b64url(s):
    import base64
    raw = base64.b64encode(str(s).encode("utf-8")).decode("ascii")
    return raw.rstrip("=")


def expired_sub_body(lang="ru"):
    if lang == "en":
        title = "FluxVPN | Subscription expired"
    else:
        title = "FluxVPN | Подписка истекла"
    remark = urllib.parse.quote(title, safe="")
    line = (
        "vless://00000000-0000-0000-0000-000000000000@127.0.0.1:1"
        + "?encryption=none&security=none&type=tcp#"
        + remark
    )
    return line + chr(10)



def sub_headers(expire_ts=0, upload=0, download=0, total=0):
    title_b64 = b64url(BRAND)
    info = (
        "upload=" + str(int(upload))
        + "; download=" + str(int(download))
        + "; total=" + str(int(total))
        + "; expire=" + str(int(expire_ts or 0))
    )
    return {
        "Content-Type": "text/plain; charset=utf-8",
        "Cache-Control": "no-store",
        "Profile-Update-Interval": "1",
        "profile-update-interval": "1",
        "Profile-Title": "base64:" + title_b64,
        "profile-title": "base64:" + title_b64,
        "Content-Disposition": 'attachment; filename="FluxVPN"',
        "subscription-userinfo": info,
        "Subscription-Userinfo": info,
    }


def send_sub_response(handler, body, expire_ts=0):
    data = body.encode("utf-8") if isinstance(body, str) else body
    handler.send_response(200)
    for k, v in sub_headers(expire_ts=expire_ts).items():
        handler.send_header(k, v)
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


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
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            if path in ("/", "/health", "/favicon.ico"):
                self._send(200, "text/plain; charset=utf-8", "FluxVPN ok")
                return

            # /sub/{token}/device/{id}/delete
            parts = [x for x in path.split("/") if x]
            if len(parts) >= 1 and parts[0] == "sub":
                if len(parts) == 4 and parts[2] == "device" and parts[3].isdigit() is False and False:
                    pass
                # delete device: sub/<token>/device/<id>/delete
                if len(parts) == 5 and parts[2] == "device" and parts[4] == "delete" and parts[3].isdigit():
                    token = parts[1]
                    dev_id = parts[3]
                    if (not re_fullmatch_token(token)) or len(token) < 16:
                        self._send(400, "text/plain; charset=utf-8", "bad token")
                        return
                    conn = db()
                    try:
                        ensure_schema(conn)
                        rows = conn.run(USER_SELECT + " where sub_token=:t limit 1", t=token)
                        user = user_row(rows[0]) if rows else None
                        if not user or not is_active(user["status"], user["subscription_expires"]):
                            self._send(403, "text/html; charset=utf-8", render_denied())
                            return
                        delete_device(conn, user["telegram_id"], dev_id)
                        # redirect back to cabinet
                        self.send_response(302)
                        self.send_header("Location", "/sub/" + token + "#devices")
                        self.send_header("Cache-Control", "no-store")
                        self.end_headers()
                        return
                    finally:
                        conn.close()

                if len(parts) >= 2:
                    token = parts[1]
                    if (not token) or (len(token) < 16) or (len(token) > 128) or (not re_fullmatch_token(token)):
                        self._send(400, "text/plain; charset=utf-8", "bad token")
                        return
                    conn = db()
                    try:
                        ensure_schema(conn)
                        rows = conn.run(USER_SELECT + " where sub_token=:t limit 1", t=token)
                        user = user_row(rows[0]) if rows else None
                        ua = self.headers.get("User-Agent") or ""
                        browser = is_browser(ua)
                        ip = client_ip(self)

                        if not user:
                            if browser:
                                self._send(403, "text/html; charset=utf-8", render_denied())
                            else:
                                send_sub_response(self, expired_sub_body("ru"), expire_ts=0)
                            return

                        lang = lang_of(user)
                        active = is_active(user["status"], user["subscription_expires"])
                        exp_ts = 0
                        if user.get("subscription_expires") is not None:
                            exp = user["subscription_expires"]
                            if getattr(exp, "tzinfo", None) is None:
                                exp = exp.replace(tzinfo=timezone.utc)
                            exp_ts = int(exp.timestamp())

                        if browser:
                            if not active:
                                self._send(200, "text/html; charset=utf-8", render_denied())
                            else:
                                servers = get_servers(conn)
                                devices = list_devices(conn, user["telegram_id"])
                                limit = device_limit_for(user)
                                self._send(
                                    200,
                                    "text/html; charset=utf-8",
                                    render_cabinet(user, servers, devices=devices, device_limit=limit),
                                )
                            return

                        # VPN clients
                        if not active:
                            send_sub_response(self, expired_sub_body(lang), expire_ts=exp_ts)
                            return

                        allowed, cnt, limit, reason = touch_device(conn, user, ua, ip)
                        if not allowed:
                            body = blocked_sub_body(lang) if reason == "blocked" else limit_sub_body(lang)
                            send_sub_response(self, body, expire_ts=exp_ts)
                            return

                        servers = get_servers(conn)
                        lines = [brand_config(s[1], s[2]) for s in servers if brand_config(s[1], s[2])]
                        body = chr(10).join(lines)
                        if body:
                            body = body + chr(10)
                        send_sub_response(self, body, expire_ts=exp_ts)
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
                    "allowed_updates": ["message", "callback_query"],
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
