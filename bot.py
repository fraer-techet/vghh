# -*- coding: utf-8 -*-
import hashlib
import html as H
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
REF_PERCENT = 10
TRIAL_DEVICE_LIMIT = 2
PREMIUM_DEVICE_LIMIT = 4
CUSTOM_DAY_MIN = 3
CUSTOM_DAY_MAX = 730
TOPUP_PACKS = [100, 200, 500, 1000]
PLAN_PRICE = {7: 50, 30: 200, 90: 400, 365: 800}

def env(k, d=""):
    return os.environ.get(k, d)

BOT_TOKEN = env("BOT_TOKEN")
DATABASE_URL = env("DATABASE_URL")
ADMIN_ID = int(env("ADMIN_ID", "6049379160") or "6049379160")
ADMIN_USERNAME = (env("ADMIN_USERNAME", "zrdws") or "zrdws").lstrip("@")
CRYPTO_BOT_TOKEN = env("CRYPTO_BOT_TOKEN", "599850:AA21TXJWkZO0aZT8DZFbB6NIwdj6jtKZ3YB")
PORT = int(env("PORT", "10000") or "10000")
PUBLIC_URL = (env("PUBLIC_URL") or env("RENDER_EXTERNAL_URL") or "").rstrip("/")

if not BOT_TOKEN or not DATABASE_URL:
    print("FATAL missing BOT_TOKEN/DATABASE_URL", flush=True)
    sys.exit(1)

API = "ht" + "tps://api.telegram.org/bot" + BOT_TOKEN
PENDING = {}
_schema_ok = False
_schema_lock = threading.Lock()

T = {
"ru": {
"lang_pick": "Выбери язык интерфейса",
"home": "<b>{b}</b>\n──────────────\nПривет, <b>{n}</b>\n\nСтатус · <b>{plan}</b>\n{extra}\nБаланс · <b>{bal:.0f}₽</b>\nРефералы · <b>{refs}</b> (+{rd}д / {rp}%)",
"plan_active": "Осталось · <b>{d} дн.</b>\nДо · <code>{until}</code>",
"plan_off": "Подписка · <b>неактивна</b>",
"btn_home": "🏠 Меню",
"btn_trial": "✨ Триал",
"btn_buy": "💎 Premium",
"btn_key": "🔑 Ключ",
"btn_cab": "🖥 Кабинет",
"btn_srv": "🛰 Серверы",
"btn_ref": "🎁 Рефералка",
"btn_bal": "💰 Баланс",
"btn_promo": "🏷 Промо",
"btn_help": "💬 Поддержка",
"btn_lang": "🌐 Язык",
"btn_adm": "🛠 Админ",
"btn_back": "⬅️ Назад",
"btn_cancel": "❌ Отмена",
"trial_ok": "✅ Триал на 7 дней включён.",
"trial_used": "Триал уже был использован.",
"already": "Подписка уже активна.",
"need": "Нужна активная подписка.",
"buy_title": "<b>Premium</b>\n\nВыбери срок. Цена сразу видна.",
"p7": "7д · 50₽",
"p30": "30д · 200₽",
"p90": "90д · 400₽",
"p365": "Год · 800₽",
"pcust": "✏️ Свои дни",
"pay_title": "<b>{days} дн.</b> Premium\nК оплате · <b>{price}₽</b>\n\nСпособ оплаты:",
"pay_crypto": "🪙 CryptoBot",
"pay_bal": "💰 С баланса",
"pay_adm": "👤 Админу",
"cust_ask": "Сколько дней?\nОт <b>{a}</b> до <b>{z}</b>.\nПример: <code>45</code>",
"cust_bad": "Число от {a} до {z}.",
"order_box": "Заказ FluxVPN\nID: {uid}\nUser: {name}\nPlan: {days}d\nPrice: {price} RUB",
"order_user": "Заявка · <b>{days}д / {price}₽</b>\n\n1) Напиши админу\n2) Отправь заказ\n3) Жди подтверждения\n\n<code>{order}</code>",
"write_adm": "Написать @{a}",
"new_order": "🛒 <b>Заказ</b>\n<code>{uid}</code> {name}\n<b>{days}д</b> · <b>{price}₽</b>",
"paid": "✅ Заказ оплачен",
"reject": "❌ Отклонить",
"paid_ok": "✅ Выдано <code>{uid}</code> · {days}д",
"paid_user": "✅ Оплата ок. Premium <b>{days}д</b>.",
"rej_ok": "❌ Заказ отклонён · <code>{uid}</code>",
"rej_user": "❌ Заявка ({days}д) отклонена. Напиши в поддержку, если ошибка.",
"bal_title": "<b>Баланс</b>\nСейчас · <b>{bal:.0f}₽</b>",
"bal_low": "Мало средств: нужно {price}₽, есть {bal:.0f}₽",
"bal_ok": "✅ Списано {price}₽ · Premium {days}д",
"top_title": "<b>Пополнение</b>\nВыбери сумму",
"top_order": "Пополнение · <b>{amount}₽</b>\n\n<code>{order}</code>",
"top_new": "💳 <b>Пополнение</b>\n<code>{uid}</code> {name}\n<b>{amount}₽</b>",
"top_paid": "✅ Баланс пополнен",
"top_ok_a": "✅ <code>{uid}</code> +{amount}₽",
"top_ok_u": "✅ Баланс +{amount}₽ · итого <b>{bal:.0f}₽</b>",
"crypto_mk": "Счёт CryptoBot · <b>{price}₽</b>",
"crypto_top": "Счёт пополнения · <b>{amount}₽</b>",
"crypto_open": "Оплатить",
"crypto_chk": "Проверить оплату",
"crypto_wait": "Ещё не оплачено. Подожди и проверь снова.",
"crypto_ok": "✅ Оплата получена · Premium {days}д",
"crypto_top_ok": "✅ Оплата получена · +{amount}₽",
"crypto_err": "Счёт не создался. Попробуй позже или админу.",
"ref_title": "<b>Рефералка</b>\n+{d} дней и <b>{p}%</b> с покупок друга.\nПриглашено · <b>{n}</b>\nЗаработано · <b>{earn:.0f}₽</b>",
"copy_ref": "Скопировать реф",
"copy_key": "Скопировать ключ",
"srv_title": "<b>Серверы</b>",
"srv_empty": "Пока пусто.",
"srv_note": "Ключ — кнопкой ниже. Конфиги подтянет клиент.",
"promo_ask": "Отправь промокод",
"promo_bad": "Промокод недействителен",
"promo_used": "Уже использован",
"promo_days": "✅ Промо: +{v}д",
"promo_bal": "✅ Промо: +{v:.0f}₽",
"promo_pct": "✅ Промо: скидка {v:.0f}% на след. покупку с баланса",
"help_ask": "Опиши проблему одним сообщением",
"help_ok": "✅ Тикет #{id} создан",
"help_adm": "🎫 <b>Тикет #{id}</b>\n<code>{uid}</code> {name}\n\n{body}",
"help_reply": "💬 <b>Поддержка #{id}</b>\n\n{body}",
"t_reply": "Ответить",
"t_close": "Закрыть",
"t_ask": "Ответ для тикета #{id}",
"t_closed": "Тикет #{id} закрыт",
"ban_msg": "🚫 Доступ ограничен\n{reason}",
"n2": "⏰ <b>{b}</b>\nПодписка кончается через <b>2 дня</b>.\nПродли сейчас — без обрывов. 💪",
"n1": "⏰ <b>{b}</b>\nОстался <b>1 день</b>.\nПродли заранее. 🔥",
"nh": "⏰ <b>{b}</b>\nДо конца ~<b>час</b>.\nПродли, чтобы остаться online. ⚡",
"nx": "❌ <b>{b}</b>\nПодписка закончилась.\nПродли — и доступ сразу вернётся. 🚀",
"lang_ok": "Язык: Русский",
"welcome_ref": "Тебя пригласили в <b>{b}</b>. Добро пожаловать.",
"adm_title": "🛠 <b>Админ {b}</b>\n\n👥 {u} · 🟢 {a} · 💎 {p}\n✨ {t} · 🎁 {r} · 🛰 {s}\n💰 выручка {rev:.0f}₽ · 💳 баланс-сумма {sumbal:.0f}₽\n📱 устройств {dev} · 🎫 тикетов {tk}",
"a_stats": "📊 Стата",
"a_users": "👥 Юзеры",
"a_active": "🟢 Актив",
"a_find": "🔎 Найти",
"a_me": "👑 Себе",
"a_grant": "➕ Юзеру",
"a_trial": "✨ Триал",
"a_rev": "⛔ Снять",
"a_ban": "🚫 Бан",
"a_unban": "✅ Разбан",
"a_bal": "💰 +баланс",
"a_dev": "📱 Сброс уст.",
"a_promo": "🏷 Промо",
"a_tick": "🎫 Тикеты",
"a_srv": "🛰 Серверы",
"a_add": "➕ Сервер",
"a_del": "🗑 Удалить",
"a_bc": "📣 Рассылка",
"a_price": "💵 Тарифы",
"a_revstats": "📈 Выручка",
"prices": "<b>Тарифы</b>\n7д — 50₽\n30д — 200₽\n90д — 400₽\nГод — 800₽\nСвои дни — автоцена",
"ask_id": "Telegram ID числом",
"ask_bc": "Текст рассылки",
"ask_sn": "Имя сервера\n🇩🇪 Germany",
"ask_sc": "VLESS/SS строка",
"ask_banr": "Причина бана",
"ask_bal": "ID СУММА\n123 200",
"ask_promo": "CODE days N\nCODE balance N\nCODE percent N\nFLUX10 percent 10",
"d7": "7д", "d30": "30д", "d90": "90д", "d365": "365д", "dinf": "∞",
"ok": "Готово",
"no": "Не найдено",
"bc_ok": "Рассылка OK {o} / fail {f}",
"srv_add": "✅ #{i} {n}",
"srv_del": "Удалён",
"ban_ok": "Бан <code>{i}</code>",
"unban_ok": "Разбан <code>{i}</code>",
"bal_add": "+{a}₽ юзеру <code>{i}</code> (итого {b:.0f}₽)",
"promo_mk": "Промо <code>{c}</code>",
"dev_reset": "Устройства сброшены <code>{i}</code>",
"grant_ok": "+{d}д · <code>{i}</code>",
"rev_ok": "Снято · <code>{i}</code>",
"trial_g": "Триал · <code>{i}</code>",
"rev_title": "<b>Выручка</b>\nВсего · <b>{all:.0f}₽</b>\nСегодня · <b>{td:.0f}₽</b>\n7 дней · <b>{w:.0f}₽</b>\n30 дней · <b>{m:.0f}₽</b>\nПлатежей · <b>{n}</b>",
},
"en": {
"lang_pick": "Choose language",
"home": "<b>{b}</b>\n──────────────\nHi, <b>{n}</b>\n\nStatus · <b>{plan}</b>\n{extra}\nBalance · <b>{bal:.0f}₽</b>\nReferrals · <b>{refs}</b> (+{rd}d / {rp}%)",
"plan_active": "Left · <b>{d}d</b>\nUntil · <code>{until}</code>",
"plan_off": "Sub · <b>inactive</b>",
"btn_home": "🏠 Menu",
"btn_trial": "✨ Trial",
"btn_buy": "💎 Premium",
"btn_key": "🔑 Key",
"btn_cab": "🖥 Cabinet",
"btn_srv": "🛰 Servers",
"btn_ref": "🎁 Referral",
"btn_bal": "💰 Balance",
"btn_promo": "🏷 Promo",
"btn_help": "💬 Support",
"btn_lang": "🌐 Lang",
"btn_adm": "🛠 Admin",
"btn_back": "⬅️ Back",
"btn_cancel": "❌ Cancel",
"trial_ok": "✅ 7-day trial on.",
"trial_used": "Trial already used.",
"already": "Already active.",
"need": "Active sub required.",
"buy_title": "<b>Premium</b>\n\nPick a plan.",
"p7": "7d · 50₽",
"p30": "30d · 200₽",
"p90": "90d · 400₽",
"p365": "Year · 800₽",
"pcust": "✏️ Custom days",
"pay_title": "<b>{days}d</b> Premium\nTotal · <b>{price}₽</b>\n\nPay with:",
"pay_crypto": "🪙 CryptoBot",
"pay_bal": "💰 Balance",
"pay_adm": "👤 Admin",
"cust_ask": "How many days?\n<b>{a}</b>–<b>{z}</b>\ne.g. <code>45</code>",
"cust_bad": "Number {a}–{z}.",
"order_box": "FluxVPN order\nID: {uid}\nUser: {name}\nPlan: {days}d\nPrice: {price} RUB",
"order_user": "Order · <b>{days}d / {price}₽</b>\n\n1) Message admin\n2) Send order\n3) Wait confirm\n\n<code>{order}</code>",
"write_adm": "Message @{a}",
"new_order": "🛒 <b>Order</b>\n<code>{uid}</code> {name}\n<b>{days}d</b> · <b>{price}₽</b>",
"paid": "✅ Order paid",
"reject": "❌ Reject",
"paid_ok": "✅ Granted <code>{uid}</code> · {days}d",
"paid_user": "✅ Paid. Premium <b>{days}d</b>.",
"rej_ok": "❌ Rejected · <code>{uid}</code>",
"rej_user": "❌ Request ({days}d) rejected.",
"bal_title": "<b>Balance</b>\nNow · <b>{bal:.0f}₽</b>",
"bal_low": "Need {price}₽, have {bal:.0f}₽",
"bal_ok": "✅ Charged {price}₽ · Premium {days}d",
"top_title": "<b>Top up</b>",
"top_order": "Top-up · <b>{amount}₽</b>\n\n<code>{order}</code>",
"top_new": "💳 <b>Top-up</b>\n<code>{uid}</code> {name}\n<b>{amount}₽</b>",
"top_paid": "✅ Topped up",
"top_ok_a": "✅ <code>{uid}</code> +{amount}₽",
"top_ok_u": "✅ +{amount}₽ · now <b>{bal:.0f}₽</b>",
"crypto_mk": "CryptoBot · <b>{price}₽</b>",
"crypto_top": "Top-up invoice · <b>{amount}₽</b>",
"crypto_open": "Pay",
"crypto_chk": "Check payment",
"crypto_wait": "Not paid yet.",
"crypto_ok": "✅ Paid · Premium {days}d",
"crypto_top_ok": "✅ Paid · +{amount}₽",
"crypto_err": "Invoice failed.",
"ref_title": "<b>Referral</b>\n+{d}d and <b>{p}%</b> of friend purchases.\nInvited · <b>{n}</b>\nEarned · <b>{earn:.0f}₽</b>",
"copy_ref": "Copy ref",
"copy_key": "Copy key",
"srv_title": "<b>Servers</b>",
"srv_empty": "Empty.",
"srv_note": "Use key button. Client pulls configs.",
"promo_ask": "Send promo code",
"promo_bad": "Invalid promo",
"promo_used": "Already used",
"promo_days": "✅ +{v}d",
"promo_bal": "✅ +{v:.0f}₽",
"promo_pct": "✅ {v:.0f}% off next balance buy",
"help_ask": "Describe issue in one message",
"help_ok": "✅ Ticket #{id}",
"help_adm": "🎫 <b>Ticket #{id}</b>\n<code>{uid}</code> {name}\n\n{body}",
"help_reply": "💬 <b>Support #{id}</b>\n\n{body}",
"t_reply": "Reply",
"t_close": "Close",
"t_ask": "Reply for #{id}",
"t_closed": "Ticket #{id} closed",
"ban_msg": "🚫 Restricted\n{reason}",
"n2": "⏰ <b>{b}</b>\nEnds in <b>2 days</b>. Renew 💪",
"n1": "⏰ <b>{b}</b>\n<b>1 day</b> left. Renew 🔥",
"nh": "⏰ <b>{b}</b>\n~<b>1 hour</b> left. Renew ⚡",
"nx": "❌ <b>{b}</b>\nExpired. Renew to restore 🚀",
"lang_ok": "Language: English",
"welcome_ref": "Invited to <b>{b}</b>. Welcome.",
"adm_title": "🛠 <b>Admin {b}</b>\n\n👥 {u} · 🟢 {a} · 💎 {p}\n✨ {t} · 🎁 {r} · 🛰 {s}\n💰 revenue {rev:.0f}₽ · 💳 balances {sumbal:.0f}₽\n📱 devices {dev} · 🎫 tickets {tk}",
"a_stats": "📊 Stats",
"a_users": "👥 Users",
"a_active": "🟢 Active",
"a_find": "🔎 Find",
"a_me": "👑 Me",
"a_grant": "➕ User",
"a_trial": "✨ Trial",
"a_rev": "⛔ Revoke",
"a_ban": "🚫 Ban",
"a_unban": "✅ Unban",
"a_bal": "💰 +bal",
"a_dev": "📱 Reset dev",
"a_promo": "🏷 Promo",
"a_tick": "🎫 Tickets",
"a_srv": "🛰 Servers",
"a_add": "➕ Server",
"a_del": "🗑 Delete",
"a_bc": "📣 Broadcast",
"a_price": "💵 Prices",
"a_revstats": "📈 Revenue",
"prices": "<b>Prices</b>\n7d 50₽ · 30d 200₽\n90d 400₽ · year 800₽",
"ask_id": "Telegram ID",
"ask_bc": "Broadcast text",
"ask_sn": "Server name",
"ask_sc": "VLESS/SS line",
"ask_banr": "Ban reason",
"ask_bal": "ID AMOUNT",
"ask_promo": "CODE days N | balance N | percent N",
"d7": "7d", "d30": "30d", "d90": "90d", "d365": "365d", "dinf": "∞",
"ok": "OK",
"no": "Not found",
"bc_ok": "BC OK {o} / fail {f}",
"srv_add": "✅ #{i} {n}",
"srv_del": "Deleted",
"ban_ok": "Banned <code>{i}</code>",
"unban_ok": "Unbanned <code>{i}</code>",
"bal_add": "+{a}₽ to <code>{i}</code> ({b:.0f}₽)",
"promo_mk": "Promo <code>{c}</code>",
"dev_reset": "Devices reset <code>{i}</code>",
"grant_ok": "+{d}d · <code>{i}</code>",
"rev_ok": "Revoked · <code>{i}</code>",
"trial_g": "Trial · <code>{i}</code>",
"rev_title": "<b>Revenue</b>\nAll · <b>{all:.0f}₽</b>\nToday · <b>{td:.0f}₽</b>\n7d · <b>{w:.0f}₽</b>\n30d · <b>{m:.0f}₽</b>\nPayments · <b>{n}</b>",
},
}

def tr(lang, key, **kw):
    lang = lang if lang in T else "ru"
    s = T.get(lang, T["ru"]).get(key) or T["ru"].get(key) or key
    try:
        return s.format(**kw) if kw else s
    except Exception:
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
    global _schema_ok
    if _schema_ok:
        return
    with _schema_lock:
        if _schema_ok:
            return
        try:
            conn.run("create extension if not exists pgcrypto")
        except Exception:
            pass
        conn.run("create table if not exists server_pool (id bigserial primary key, raw_config text not null, custom_name text not null, created_at timestamptz not null default now())")
        conn.run("create table if not exists users (id bigserial primary key, telegram_id bigint not null unique, status text not null default 'free', trial_used boolean not null default false, subscription_expires timestamptz, sub_token text not null unique, created_at timestamptz not null default now())")
        cols = {r[0] for r in conn.run("select column_name from information_schema.columns where table_name='users'")}
        alters = [
            ("referral_code", "add column referral_code text"),
            ("referred_by", "add column referred_by bigint"),
            ("referral_count", "add column referral_count int not null default 0"),
            ("referral_earned", "add column referral_earned double precision not null default 0"),
            ("username", "add column username text"),
            ("full_name", "add column full_name text"),
            ("lang", "add column lang text"),
            ("balance", "add column balance double precision not null default 0"),
            ("banned", "add column banned boolean not null default false"),
            ("ban_reason", "add column ban_reason text"),
            ("promo_percent", "add column promo_percent double precision not null default 0"),
            ("notify_2d", "add column notify_2d boolean not null default false"),
            ("notify_1d", "add column notify_1d boolean not null default false"),
            ("notify_1h", "add column notify_1h boolean not null default false"),
            ("notify_exp", "add column notify_exp boolean not null default false"),
        ]
        for c, ddl in alters:
            if c not in cols:
                try: conn.run("alter table users " + ddl)
                except Exception: pass
        conn.run("update users set referral_code = md5(random()::text || clock_timestamp()::text) where referral_code is null or referral_code=''")
        try: conn.run("create unique index if not exists idx_users_ref on users(referral_code)")
        except Exception: pass
        conn.run("create table if not exists devices (id bigserial primary key, telegram_id bigint not null, device_hash text not null, device_name text not null default 'Device', user_agent text, last_ip text, created_at timestamptz not null default now(), last_seen timestamptz not null default now(), blocked boolean not null default false, unique(telegram_id, device_hash))")
        dcols = {r[0] for r in conn.run("select column_name from information_schema.columns where table_name='devices'")}
        if dcols and "blocked" not in dcols:
            try: conn.run("alter table devices add column blocked boolean not null default false")
            except Exception: pass
        conn.run("create table if not exists promo_codes (code text primary key, kind text not null, value double precision not null, max_uses int not null default 100, used_count int not null default 0, active boolean not null default true, created_at timestamptz not null default now())")
        conn.run("create table if not exists promo_redemptions (id bigserial primary key, code text not null, telegram_id bigint not null, created_at timestamptz not null default now(), unique(code, telegram_id))")
        conn.run("create table if not exists tickets (id bigserial primary key, telegram_id bigint not null, status text not null default 'open', subject text not null default '', created_at timestamptz not null default now(), updated_at timestamptz not null default now())")
        conn.run("create table if not exists ticket_messages (id bigserial primary key, ticket_id bigint not null, sender text not null, body text not null, created_at timestamptz not null default now())")
        conn.run("create table if not exists payments (id bigserial primary key, telegram_id bigint not null, kind text not null, amount double precision not null, days int not null default 0, method text not null default '', meta text, created_at timestamptz not null default now())")
        _schema_ok = True

USQL = (
    "select telegram_id, status, trial_used, subscription_expires, sub_token, referral_code, referred_by, "
    "coalesce(referral_count,0), username, full_name, lang, coalesce(balance,0), coalesce(banned,false), ban_reason, "
    "coalesce(promo_percent,0), coalesce(referral_earned,0), coalesce(notify_2d,false), coalesce(notify_1d,false), "
    "coalesce(notify_1h,false), coalesce(notify_exp,false) from users"
)

def urow(r):
    return {
        "telegram_id": r[0], "status": r[1], "trial_used": bool(r[2]), "subscription_expires": r[3],
        "sub_token": r[4], "referral_code": r[5], "referred_by": r[6], "referral_count": int(r[7] or 0),
        "username": r[8], "full_name": r[9], "lang": r[10], "balance": float(r[11] or 0),
        "banned": bool(r[12]), "ban_reason": r[13], "promo_percent": float(r[14] or 0),
        "referral_earned": float(r[15] or 0),
        "notify_2d": bool(r[16]), "notify_1d": bool(r[17]), "notify_1h": bool(r[18]), "notify_exp": bool(r[19]),
    }

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
        raise RuntimeError(str(body))
    return body["result"]

def send(chat, text, kb=None):
    p = {"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    if kb is not None:
        p["reply_markup"] = kb
    return api("sendMessage", p)

def edit(chat, mid, text, kb=None):
    p = {"chat_id": chat, "message_id": mid, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    if kb is not None:
        p["reply_markup"] = kb
    try:
        return api("editMessageText", p)
    except Exception:
        return None

def ans(qid, text=None, alert=False):
    p = {"callback_query_id": qid, "show_alert": alert}
    if text:
        p["text"] = text[:200]
    return api("answerCallbackQuery", p)

def is_active(st, exp):
    if st not in ("trial", "premium") or exp is None:
        return False
    if getattr(exp, "tzinfo", None) is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return exp > utcnow()

def days_left(exp):
    if exp is None:
        return 0
    if getattr(exp, "tzinfo", None) is None:
        exp = exp.replace(tzinfo=timezone.utc)
    s = (exp - utcnow()).total_seconds()
    return 0 if s <= 0 else max(1, int((s + 86399) // 86400))

def fmt_until(exp):
    if exp is None:
        return "—"
    if getattr(exp, "tzinfo", None) is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return exp.strftime("%Y-%m-%d %H:%M UTC")

def lang_of(u):
    lg = (u or {}).get("lang")
    return lg if lg in ("ru", "en") else "ru"

def dname(u):
    if u.get("full_name"): return u["full_name"]
    if u.get("username"): return "@" + u["username"]
    return str(u["telegram_id"])

def plan_label(u):
    if is_active(u["status"], u["subscription_expires"]):
        return "Trial" if u["status"] == "trial" else "Premium"
    return "Free"

def sub_link(u):
    if not PUBLIC_URL: return ""
    return PUBLIC_URL + "/sub/" + u["sub_token"]

def ref_link(u):
    me = env("BOT_USERNAME", "").lstrip("@")
    code = u.get("referral_code") or ""
    return ("https://t.me/" + me + "?start=ref_" + code) if me else ("ref_" + code)

def calc_price(days):
    d = int(days)
    if d in PLAN_PRICE:
        return int(PLAN_PRICE[d])
    if d <= 0: return 0
    if d <= 7: return max(30, int(round(d * 50 / 7)))
    if d <= 30: return int(round(50 + (d - 7) * 150 / 23))
    if d <= 90: return int(round(200 + (d - 30) * 200 / 60))
    if d <= 365: return int(round(400 + (d - 90) * 400 / 275))
    return int(round(800 + (d - 365) * 2))

def price_with_promo(user, days):
    base = calc_price(days)
    pct = float(user.get("promo_percent") or 0)
    if pct > 0:
        return max(1, int(round(base * (100 - pct) / 100.0))), base, pct
    return base, base, 0

def get_user(conn, tg):
    rows = conn.run(USQL + " where telegram_id=:id", id=tg)
    return urow(rows[0]) if rows else None

def ensure_user(conn, tg, username=None, full_name=None, ref_code=None, lang=None):
    ensure_schema(conn)
    u = get_user(conn, tg)
    if u:
        if username is not None or full_name is not None:
            conn.run("update users set username=coalesce(:u,username), full_name=coalesce(:f,full_name) where telegram_id=:id", u=username, f=full_name, id=tg)
            u = get_user(conn, tg)
        return u
    st, rc = secrets.token_hex(16), secrets.token_hex(4)
    ref_by = None
    if ref_code:
        rows = conn.run(USQL + " where referral_code=:c limit 1", c=ref_code)
        if rows and rows[0][0] != tg:
            ref_by = rows[0][0]
    conn.run(
        "insert into users (telegram_id,status,trial_used,sub_token,referral_code,referred_by,referral_count,username,full_name,lang) "
        "values (:id,'free',false,:st,:rc,:rb,0,:u,:f,:lg)",
        id=tg, st=st, rc=rc, rb=ref_by, u=username, f=full_name, lg=lang,
    )
    u = get_user(conn, tg)
    if ref_by:
        apply_ref_join(conn, ref_by, tg)
        u = get_user(conn, tg)
    return u

def set_lang(conn, tg, lang):
    conn.run("update users set lang=:l where telegram_id=:id", l=lang, id=tg)
    return get_user(conn, tg)

def extend_sub(conn, tg, days, status="premium"):
    u = get_user(conn, tg) or ensure_user(conn, tg)
    now = utcnow()
    base = now
    if is_active(u["status"], u["subscription_expires"]):
        exp = u["subscription_expires"]
        if getattr(exp, "tzinfo", None) is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp > now:
            base = exp
    exp = base + timedelta(days=int(days))
    conn.run(
        "update users set status=:s, subscription_expires=:e, notify_2d=false, notify_1d=false, notify_1h=false, notify_exp=false where telegram_id=:id",
        s=status, e=exp, id=tg,
    )
    return get_user(conn, tg)

def apply_ref_join(conn, inviter, newbie):
    inv = get_user(conn, inviter)
    nb = get_user(conn, newbie)
    if not inv or not nb: return
    if nb.get("referred_by") not in (None, inviter): return
    conn.run("update users set referral_count=coalesce(referral_count,0)+1 where telegram_id=:id", id=inviter)
    keep = inv["status"] == "trial" and is_active(inv["status"], inv["subscription_expires"])
    extend_sub(conn, inviter, REF_BONUS_DAYS, status=("trial" if keep else "premium"))
    try:
        send(inviter, tr(lang_of(inv), "promo_days", v=REF_BONUS_DAYS).replace("Промо", "Реф").replace("Promo", "Ref"))
    except Exception:
        pass

def record_payment(conn, tg, kind, amount, days=0, method="", meta=""):
    conn.run(
        "insert into payments (telegram_id, kind, amount, days, method, meta) values (:t,:k,:a,:d,:m,:x)",
        t=int(tg), k=kind, a=float(amount), d=int(days), m=method or "", x=meta or "",
    )
    # referral percent on premium purchases
    if kind == "premium" and amount > 0:
        u = get_user(conn, tg)
        if u and u.get("referred_by"):
            bonus = round(float(amount) * REF_PERCENT / 100.0, 2)
            if bonus > 0:
                conn.run(
                    "update users set balance=coalesce(balance,0)+:b, referral_earned=coalesce(referral_earned,0)+:b where telegram_id=:id",
                    b=bonus, id=int(u["referred_by"]),
                )
                try:
                    inv = get_user(conn, int(u["referred_by"]))
                    send(int(u["referred_by"]), "🎁 Реф-бонус с покупки: +" + str(bonus) + "₽ на баланс")
                except Exception:
                    pass

def add_balance(conn, tg, amount):
    conn.run("update users set balance=coalesce(balance,0)+:a where telegram_id=:id", a=float(amount), id=int(tg))
    return get_user(conn, int(tg))

def charge_balance(conn, tg, amount):
    u = get_user(conn, tg)
    if float(u.get("balance") or 0) < float(amount):
        return None
    conn.run("update users set balance=coalesce(balance,0)-:a where telegram_id=:id", a=float(amount), id=int(tg))
    # consume promo percent after successful balance purchase
    conn.run("update users set promo_percent=0 where telegram_id=:id", id=int(tg))
    return get_user(conn, int(tg))

def set_ban(conn, tg, banned, reason=""):
    conn.run("update users set banned=:b, ban_reason=:r where telegram_id=:id", b=bool(banned), r=reason or None, id=int(tg))
    return get_user(conn, int(tg))

def clear_pend(tg):
    PENDING.pop(tg, None)

def meta(uobj):
    return uobj.get("username"), (((uobj.get("first_name") or "") + " " + (uobj.get("last_name") or "")).strip() or None)

def home_text(u):
    lg = lang_of(u)
    active = is_active(u["status"], u["subscription_expires"])
    extra = tr(lg, "plan_active", d=days_left(u["subscription_expires"]), until=fmt_until(u["subscription_expires"])) if active else tr(lg, "plan_off")
    return tr(lg, "home", b=BRAND, n=H.escape(dname(u)), plan=plan_label(u), extra=extra,
              bal=float(u.get("balance") or 0), refs=int(u.get("referral_count") or 0), rd=REF_BONUS_DAYS, rp=REF_PERCENT)

def ik(*rows):
    return {"inline_keyboard": list(rows)}

def btn(text, cb=None, url=None, copy=None):
    b = {"text": text}
    if cb: b["callback_data"] = cb
    if url: b["url"] = url
    if copy is not None: b["copy_text"] = {"text": copy}
    return b

def kb_lang():
    return ik([btn("🇷🇺 Русский", "lang_ru"), btn("🇬🇧 English", "lang_en")])

def kb_home(u):
    lg = lang_of(u)
    active = is_active(u["status"], u["subscription_expires"])
    link = sub_link(u)
    rows = []
    if (not u["trial_used"]) and (not active):
        rows.append([btn(tr(lg, "btn_trial"), "trial")])
    rows.append([btn(tr(lg, "btn_buy"), "buy")])
    row = []
    if active and link:
        row.append(btn(tr(lg, "btn_key"), copy=link))
        row.append(btn(tr(lg, "btn_cab"), url=link))
    if row:
        rows.append(row)
    if active:
        rows.append([btn(tr(lg, "btn_srv"), "srv")])
    rows.append([btn(tr(lg, "btn_ref"), "ref"), btn(tr(lg, "btn_bal"), "bal")])
    rows.append([btn(tr(lg, "btn_promo"), "promo"), btn(tr(lg, "btn_help"), "help")])
    rows.append([btn(tr(lg, "btn_lang"), "lang")])
    if u["telegram_id"] == ADMIN_ID:
        rows.append([btn(tr(lg, "btn_adm"), "adm")])
    return ik(*rows)

def kb_back(lg, cb="home"):
    return ik([btn(tr(lg, "btn_back"), cb)])

def kb_cancel(lg):
    return ik([btn(tr(lg, "btn_cancel"), "home")])

def kb_buy(lg):
    return ik(
        [btn(tr(lg, "p7"), "buy_7"), btn(tr(lg, "p30"), "buy_30")],
        [btn(tr(lg, "p90"), "buy_90"), btn(tr(lg, "p365"), "buy_365")],
        [btn(tr(lg, "pcust"), "buy_custom")],
        [btn(tr(lg, "btn_back"), "home")],
    )

def kb_pay(lg, days):
    return ik(
        [btn(tr(lg, "pay_crypto"), "pcrypto_" + str(days))],
        [btn(tr(lg, "pay_bal"), "pbal_" + str(days))],
        [btn(tr(lg, "pay_adm"), "padm_" + str(days))],
        [btn(tr(lg, "btn_back"), "buy")],
    )

def kb_adm_order(uid, days):
    return ik(
        [btn(tr("ru", "paid"), "paid_" + str(uid) + "_" + str(days))],
        [btn(tr("ru", "reject"), "rej_" + str(uid) + "_" + str(days))],
    )

def kb_adm_top(uid, amount):
    return ik(
        [btn(tr("ru", "top_paid"), "topok_" + str(uid) + "_" + str(amount))],
        [btn(tr("ru", "reject"), "toprej_" + str(uid) + "_" + str(amount))],
    )

def kb_crypto(lg, url, inv, kind):
    return ik(
        [btn(tr(lg, "crypto_open"), url=url)],
        [btn(tr(lg, "crypto_chk"), "cchk_" + kind + "_" + str(inv))],
        [btn(tr(lg, "btn_back"), "home")],
    )

def kb_top(lg):
    rows, row = [], []
    for a in TOPUP_PACKS:
        row.append(btn(str(a) + "₽", "top_" + str(a)))
        if len(row) == 2:
            rows.append(row); row = []
    if row: rows.append(row)
    rows.append([btn(tr(lg, "btn_back"), "bal")])
    return ik(*rows)

def kb_bal(lg):
    return ik([btn(tr(lg, "btn_buy"), "buy")], [btn("➕ " + tr(lg, "top_title").replace("<b>" ,"").replace("</b>",""), "topup")], [btn(tr(lg, "btn_back"), "home")])

def kb_admin(lg):
    return ik(
        [btn(tr(lg, "a_stats"), "adm"), btn(tr(lg, "a_revstats"), "arev")],
        [btn(tr(lg, "a_users"), "ausers"), btn(tr(lg, "a_active"), "aact")],
        [btn(tr(lg, "a_find"), "afind"), btn(tr(lg, "a_me"), "ame")],
        [btn(tr(lg, "a_grant"), "agrant"), btn(tr(lg, "a_trial"), "atrial")],
        [btn(tr(lg, "a_rev"), "arevoke"), btn(tr(lg, "a_bal"), "abal")],
        [btn(tr(lg, "a_ban"), "aban"), btn(tr(lg, "a_unban"), "aunban")],
        [btn(tr(lg, "a_dev"), "adev"), btn(tr(lg, "a_promo"), "apromo")],
        [btn(tr(lg, "a_tick"), "atick"), btn(tr(lg, "a_bc"), "abc")],
        [btn(tr(lg, "a_srv"), "asrv"), btn(tr(lg, "a_add"), "aadd")],
        [btn(tr(lg, "a_del"), "adel"), btn(tr(lg, "a_price"), "aprice")],
        [btn(tr(lg, "btn_back"), "home")],
    )

def kb_days(prefix, lg):
    return ik(
        [btn(tr(lg, "d7"), prefix + "_7"), btn(tr(lg, "d30"), prefix + "_30")],
        [btn(tr(lg, "d90"), prefix + "_90"), btn(tr(lg, "d365"), prefix + "_365")],
        [btn(tr(lg, "dinf"), prefix + "_9999")],
        [btn(tr(lg, "btn_cancel"), "adm")],
    )

def kb_ticket(tid):
    return ik([btn(tr("ru", "t_reply"), "trep_" + str(tid)), btn(tr("ru", "t_close"), "tclose_" + str(tid))])

def get_servers(conn):
    return conn.run("select id, raw_config, custom_name from server_pool order by id")

def flag(name):
    for ch in str(name or ""):
        o = ord(ch)
        if 0x1F1E6 <= o <= 0x1F1FF:
            return ch
    return "•"

def brand_cfg(raw, name):
    cfg = (raw or "").strip()
    nm = (name or "Server").strip()
    if not cfg: return ""
    i = cfg.rfind("#")
    return (cfg[:i] if i >= 0 else cfg) + "#" + nm

def servers_text(conn, lg):
    rows = get_servers(conn)
    if not rows: return tr(lg, "srv_empty")
    lines = [tr(lg, "srv_title"), ""]
    for r in rows:
        lines.append(flag(r[2]) + " <b>" + H.escape(str(r[2])) + "</b>")
    lines += ["", tr(lg, "srv_note")]
    return chr(10).join(lines)

def admin_title(conn, lg):
    ensure_schema(conn)
    total = conn.run("select count(*) from users")[0][0]
    servers = conn.run("select count(*) from server_pool")[0][0]
    refs = conn.run("select coalesce(sum(referral_count),0) from users")[0][0]
    sumbal = float(conn.run("select coalesce(sum(balance),0) from users")[0][0] or 0)
    try: dev = conn.run("select count(*) from devices where coalesce(blocked,false)=false")[0][0]
    except Exception: dev = 0
    try: tk = conn.run("select count(*) from tickets where status='open'")[0][0]
    except Exception: tk = 0
    try:
        rev = float(conn.run("select coalesce(sum(amount),0) from payments where kind in ('premium','topup')")[0][0] or 0)
    except Exception:
        rev = 0
    active = premium = trial = 0
    for r in conn.run(USQL):
        u = urow(r)
        if is_active(u["status"], u["subscription_expires"]):
            active += 1
            if u["status"] == "premium": premium += 1
            elif u["status"] == "trial": trial += 1
    return tr(lg, "adm_title", b=BRAND, u=total, a=active, p=premium, t=trial, r=refs, s=servers, rev=rev, sumbal=sumbal, dev=dev, tk=tk)

def revenue_text(conn, lg):
    def sum_since(days=None):
        if days is None:
            return float(conn.run("select coalesce(sum(amount),0) from payments where kind in ('premium','topup')")[0][0] or 0)
        return float(conn.run(
            "select coalesce(sum(amount),0) from payments where kind in ('premium','topup') and created_at >= now() - (:d || ' days')::interval",
            d=str(int(days)),
        )[0][0] or 0)
    try:
        n = int(conn.run("select count(*) from payments where kind in ('premium','topup')")[0][0] or 0)
        return tr(lg, "rev_title", all=sum_since(), td=sum_since(1), w=sum_since(7), m=sum_since(30), n=n)
    except Exception:
        return tr(lg, "rev_title", all=0, td=0, w=0, m=0, n=0)

def crypto_api(method, payload=None):
    url = "https://pay.crypt.bot/api/" + method
    headers = {"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if not body.get("ok"):
        raise RuntimeError(str(body))
    return body.get("result")

def crypto_invoice(amount, desc, payload):
    return crypto_api("createInvoice", {
        "currency_type": "fiat", "fiat": "RUB", "amount": str(int(amount)),
        "description": desc[:1024], "payload": str(payload)[:4096],
        "expires_in": 3600, "allow_comments": False, "allow_anonymous": True,
    })

def crypto_get(inv_id):
    res = crypto_api("getInvoices", {"invoice_ids": str(inv_id)})
    if isinstance(res, dict) and "items" in res:
        items = res.get("items") or []
        return items[0] if items else None
    if isinstance(res, list):
        return res[0] if res else None
    return res

def adm_link(text=""):
    base = "https://t.me/" + ADMIN_USERNAME
    return base + ("?text=" + urllib.parse.quote(text) if text else "")

def order_text(u, days, price):
    return tr("en", "order_box", uid=u["telegram_id"], name=dname(u), days=days, price=price).replace("FluxVPN order", "FluxVPN order")

# ---------------- callbacks / messages ----------------

def show_home(conn, chat, mid, u, edit_mode=True):
    text = home_text(u)
    kb = kb_home(u)
    if edit_mode and mid:
        edit(chat, mid, text, kb)
    else:
        send(chat, text, kb)

def handle_start(conn, msg, ref=None):
    tg = msg["from"]["id"]; chat = msg["chat"]["id"]
    un, fn = meta(msg.get("from") or {})
    exists = get_user(conn, tg)
    is_new = exists is None
    u = ensure_user(conn, tg, username=un, full_name=fn, ref_code=ref if is_new else None)
    if u.get("banned") and tg != ADMIN_ID:
        send(chat, tr(lang_of(u), "ban_msg", reason=H.escape(u.get("ban_reason") or "—")))
        return
    if not u.get("lang"):
        PENDING[tg] = {"a": "lang", "refnew": bool(is_new and ref)}
        send(chat, tr("ru", "lang_pick"), kb_lang())
        return
    lg = lang_of(u)
    prefix = (tr(lg, "welcome_ref", b=BRAND) + "\n\n") if (is_new and ref) else ""
    send(chat, prefix + home_text(u), kb_home(u))

def handle_cb(conn, cq):
    data = cq.get("data") or ""
    tg = cq["from"]["id"]
    chat = cq["message"]["chat"]["id"]
    mid = cq["message"]["message_id"]
    un, fn = meta(cq.get("from") or {})
    u = ensure_user(conn, tg, username=un, full_name=fn)
    lg = lang_of(u)

    def ok(txt=None, alert=False):
        ans(cq["id"], txt, alert)

    if u.get("banned") and tg != ADMIN_ID and not data.startswith("lang_"):
        ok(tr(lg, "ban_msg", reason=u.get("ban_reason") or "—"), True)
        return

    # language
    if data in ("lang_ru", "lang_en"):
        lg = "ru" if data.endswith("ru") else "en"
        u = set_lang(conn, tg, lg)
        pend = PENDING.pop(tg, None) or {}
        pre = (tr(lg, "welcome_ref", b=BRAND) + "\n\n") if pend.get("refnew") else ""
        edit(chat, mid, tr(lg, "lang_ok") + "\n\n" + pre + home_text(u), kb_home(u))
        ok(); return
    if data == "lang":
        edit(chat, mid, tr(lg, "lang_pick"), kb_lang()); ok(); return

    if data == "home":
        clear_pend = PENDING.pop(tg, None)
        edit(chat, mid, home_text(u), kb_home(u)); ok(); return

    if data == "trial":
        if is_active(u["status"], u["subscription_expires"]):
            ok(tr(lg, "already"), True); return
        if u["trial_used"]:
            ok(tr(lg, "trial_used"), True); return
        exp = utcnow() + timedelta(days=7)
        conn.run("update users set status='trial', trial_used=true, subscription_expires=:e, notify_2d=false, notify_1d=false, notify_1h=false, notify_exp=false where telegram_id=:id", e=exp, id=tg)
        u = get_user(conn, tg)
        edit(chat, mid, tr(lg, "trial_ok") + "\n\n" + home_text(u), kb_home(u)); ok("OK"); return

    if data == "buy":
        edit(chat, mid, tr(lg, "buy_title"), kb_buy(lg)); ok(); return

    if data == "buy_custom":
        PENDING[tg] = {"a": "custom_days"}
        edit(chat, mid, tr(lg, "cust_ask", a=CUSTOM_DAY_MIN, z=CUSTOM_DAY_MAX), kb_cancel(lg)); ok(); return

    if data.startswith("buy_") and data[4:].isdigit():
        days = int(data[4:])
        if days not in PLAN_PRICE:
            ok(); return
        price = calc_price(days)
        # apply visual promo note
        p2, base, pct = price_with_promo(u, days)
        msg = tr(lg, "pay_title", days=days, price=p2)
        if pct: msg += "\n🏷 −" + str(int(pct)) + "%"
        edit(chat, mid, msg, kb_pay(lg, days)); ok(); return

    if data.startswith("pbal_"):
        days = int(data.split("_")[1])
        price, base, pct = price_with_promo(u, days)
        if float(u.get("balance") or 0) < price:
            ok(tr(lg, "bal_low", price=price, bal=float(u.get("balance") or 0)), True); return
        u2 = charge_balance(conn, tg, price)
        if not u2:
            ok(tr(lg, "bal_low", price=price, bal=float(u.get("balance") or 0)), True); return
        u2 = extend_sub(conn, tg, days, "premium")
        record_payment(conn, tg, "premium", price, days, "balance")
        edit(chat, mid, tr(lg, "bal_ok", price=price, days=days) + "\n\n" + home_text(u2), kb_home(u2)); ok("OK"); return

    if data.startswith("padm_"):
        days = int(data.split("_")[1])
        price = calc_price(days)
        ot = "FluxVPN order\nID: " + str(tg) + "\nUser: " + dname(u) + "\nPlan: " + str(days) + " days\nPrice: " + str(price) + " RUB"
        edit(chat, mid, tr(lg, "order_user", days=days, price=price, order=H.escape(ot)), ik(
            [btn(tr(lg, "write_adm", a=ADMIN_USERNAME), url=adm_link(ot))],
            [btn(tr(lg, "btn_back"), "buy")],
        ))
        try:
            send(ADMIN_ID, tr("ru", "new_order", uid=tg, name=H.escape(dname(u)), days=days, price=price), kb_adm_order(tg, days))
        except Exception:
            pass
        ok(); return

    if data.startswith("pcrypto_"):
        days = int(data.split("_")[1])
        price = calc_price(days)
        try:
            inv = crypto_invoice(price, BRAND + " Premium " + str(days) + "d", "prem:" + str(tg) + ":" + str(days) + ":" + str(price))
            iid = inv.get("invoice_id") or inv.get("id")
            url = inv.get("pay_url") or inv.get("bot_invoice_url") or inv.get("mini_app_invoice_url")
            if not iid or not url: raise RuntimeError(str(inv))
            edit(chat, mid, tr(lg, "crypto_mk", price=price), kb_crypto(lg, url, iid, "p"))
        except Exception as e:
            print("crypto", e, flush=True)
            edit(chat, mid, tr(lg, "crypto_err"), kb_buy(lg))
        ok(); return

    if data.startswith("cchk_"):
        parts = data.split("_")
        if len(parts) < 3:
            ok(); return
        kind, iid = parts[1], parts[2]
        try:
            inv = crypto_get(iid)
        except Exception as e:
            print("cchk", e, flush=True)
            ok(tr(lg, "crypto_wait"), True); return
        if (inv or {}).get("status") != "paid":
            ok(tr(lg, "crypto_wait"), True); return
        payload = str((inv or {}).get("payload") or "")
        if kind == "p" and payload.startswith("prem:"):
            _, uid_s, days_s, price_s = (payload.split(":") + ["0", "0", "0"])[:4]
            uid, days, price = int(uid_s), int(days_s), float(price_s or calc_price(days_s))
            if uid != tg and tg != ADMIN_ID:
                ok(); return
            u2 = extend_sub(conn, uid, days, "premium")
            record_payment(conn, uid, "premium", price, days, "crypto", str(iid))
            edit(chat, mid, tr(lg, "crypto_ok", days=days) + "\n\n" + home_text(u2), kb_home(u2)); ok("OK"); return
        if kind == "t" and payload.startswith("top:"):
            _, uid_s, amt_s = (payload.split(":") + ["0", "0"])[:3]
            uid, amount = int(uid_s), int(float(amt_s))
            if uid != tg and tg != ADMIN_ID:
                ok(); return
            u2 = add_balance(conn, uid, amount)
            record_payment(conn, uid, "topup", amount, 0, "crypto", str(iid))
            edit(chat, mid, tr(lg, "crypto_top_ok", amount=amount) + "\n" + tr(lg, "bal_title", bal=float(u2.get("balance") or 0)), kb_home(u2)); ok("OK"); return
        ok(tr(lg, "crypto_wait"), True); return

    if data == "bal":
        edit(chat, mid, tr(lg, "bal_title", bal=float(u.get("balance") or 0)), ik([btn(tr(lg, "btn_buy"), "buy")], [btn("➕", "topup")], [btn(tr(lg, "btn_back"), "home")])); ok(); return
    if data == "topup":
        edit(chat, mid, tr(lg, "top_title"), kb_top(lg)); ok(); return
    if data.startswith("top_") and data[4:].isdigit():
        amount = int(data[4:])
        if amount not in TOPUP_PACKS:
            ok(); return
        ot = "FluxVPN topup\nID: " + str(tg) + "\nUser: " + dname(u) + "\nAmount: " + str(amount) + " RUB"
        edit(chat, mid, tr(lg, "top_order", amount=amount, order=H.escape(ot)), ik(
            [btn(tr(lg, "pay_crypto"), "tcrypto_" + str(amount))],
            [btn(tr(lg, "write_adm", a=ADMIN_USERNAME), url=adm_link(ot))],
            [btn(tr(lg, "btn_back"), "bal")],
        ))
        try:
            send(ADMIN_ID, tr("ru", "top_new", uid=tg, name=H.escape(dname(u)), amount=amount), kb_adm_top(tg, amount))
        except Exception:
            pass
        ok(); return
    if data.startswith("tcrypto_") and data[8:].isdigit():
        amount = int(data[8:])
        try:
            inv = crypto_invoice(amount, BRAND + " topup " + str(amount), "top:" + str(tg) + ":" + str(amount))
            iid = inv.get("invoice_id") or inv.get("id")
            url = inv.get("pay_url") or inv.get("bot_invoice_url") or inv.get("mini_app_invoice_url")
            edit(chat, mid, tr(lg, "crypto_top", amount=amount), kb_crypto(lg, url, iid, "t"))
        except Exception as e:
            print("tcrypto", e, flush=True)
            edit(chat, mid, tr(lg, "crypto_err"), kb_top(lg))
        ok(); return

    if data == "ref":
        edit(chat, mid, tr(lg, "ref_title", d=REF_BONUS_DAYS, p=REF_PERCENT, n=int(u.get("referral_count") or 0), earn=float(u.get("referral_earned") or 0)),
             ik([btn(tr(lg, "copy_ref"), copy=ref_link(u))], [btn(tr(lg, "btn_back"), "home")])); ok(); return

    if data == "srv":
        if not is_active(u["status"], u["subscription_expires"]):
            ok(tr(lg, "need"), True); return
        link = sub_link(u)
        rows = [[btn(tr(lg, "copy_key"), copy=link), btn(tr(lg, "btn_cab"), url=link)]] if link else []
        rows.append([btn(tr(lg, "btn_back"), "home")])
        edit(chat, mid, servers_text(conn, lg), ik(*rows)); ok(); return

    if data == "promo":
        PENDING[tg] = {"a": "promo"}
        edit(chat, mid, tr(lg, "promo_ask"), kb_cancel(lg)); ok(); return
    if data == "help":
        PENDING[tg] = {"a": "help"}
        edit(chat, mid, tr(lg, "help_ask"), kb_cancel(lg)); ok(); return

    # admin callbacks
    if data == "adm":
        if tg != ADMIN_ID: ok(); return
        clear_pend(tg)
        edit(chat, mid, admin_title(conn, lg), kb_admin(lg)); ok(); return
    if tg != ADMIN_ID and data.startswith(("a", "paid_", "rej_", "topok_", "toprej_", "trep_", "tclose_")):
        # allow only non-admin-safe already handled
        if data.startswith(("paid_", "rej_", "topok_", "toprej_", "trep_", "tclose_")) or data.startswith("a"):
            ok(); return

    if tg == ADMIN_ID:
        if data == "arev":
            edit(chat, mid, revenue_text(conn, lg), kb_admin(lg)); ok(); return
        if data == "ausers":
            rows = conn.run(USQL + " order by telegram_id desc limit 12")
            lines = ["👥"]
            for r in rows:
                x = urow(r)
                lines.append("<code>" + str(x["telegram_id"]) + "</code> " + H.escape(dname(x)) + " · " + plan_label(x))
            edit(chat, mid, chr(10).join(lines), kb_admin(lg)); ok(); return
        if data == "aact":
            lines = ["🟢"]
            for r in conn.run(USQL + " order by subscription_expires desc nulls last limit 40"):
                x = urow(r)
                if is_active(x["status"], x["subscription_expires"]):
                    lines.append("<code>" + str(x["telegram_id"]) + "</code> " + plan_label(x) + " · " + str(days_left(x["subscription_expires"])) + "d")
            if len(lines) == 1: lines.append("—")
            edit(chat, mid, chr(10).join(lines), kb_admin(lg)); ok(); return
        if data == "aprice":
            edit(chat, mid, tr(lg, "prices"), kb_admin(lg)); ok(); return
        if data == "asrv":
            rows = get_servers(conn)
            lines = ["🛰"] + ([flag(r[2]) + " <b>#" + str(r[0]) + "</b> " + H.escape(str(r[2])) for r in rows] or ["—"])
            edit(chat, mid, chr(10).join(lines), kb_admin(lg)); ok(); return
        if data == "ame":
            edit(chat, mid, tr(lg, "ask_id") if False else tr(lg, "d7"), kb_days("gself", lg))
            edit(chat, mid, "Себе Premium — выбери срок:", kb_days("gself", lg)); ok(); return
        if data.startswith("gself_"):
            d = int(data.split("_")[1])
            u2 = extend_sub(conn, tg, d, "premium")
            edit(chat, mid, tr(lg, "grant_ok", d=d, i=tg) + "\n\n" + home_text(u2), kb_admin(lg)); ok("OK"); return
        if data == "agrant":
            PENDING[tg] = {"a": "grant_id"}; edit(chat, mid, tr(lg, "ask_id"), kb_cancel(lg)); ok(); return
        if data.startswith("guser_"):
            parts = data.split("_")
            if len(parts) == 3:
                uid, d = int(parts[1]), int(parts[2])
                ensure_user(conn, uid); extend_sub(conn, uid, d, "premium")
                edit(chat, mid, tr(lg, "grant_ok", d=d, i=uid), kb_admin(lg))
                try: send(uid, tr("ru", "paid_user", days=d))
                except Exception: pass
                ok("OK"); return
        if data == "atrial":
            PENDING[tg] = {"a": "trial_id"}; edit(chat, mid, tr(lg, "ask_id"), kb_cancel(lg)); ok(); return
        if data == "arevoke":
            PENDING[tg] = {"a": "rev_id"}; edit(chat, mid, tr(lg, "ask_id"), kb_cancel(lg)); ok(); return
        if data == "afind":
            PENDING[tg] = {"a": "find_id"}; edit(chat, mid, tr(lg, "ask_id"), kb_cancel(lg)); ok(); return
        if data == "aban":
            PENDING[tg] = {"a": "ban_id"}; edit(chat, mid, tr(lg, "ask_id"), kb_cancel(lg)); ok(); return
        if data == "aunban":
            PENDING[tg] = {"a": "unban_id"}; edit(chat, mid, tr(lg, "ask_id"), kb_cancel(lg)); ok(); return
        if data == "abal":
            PENDING[tg] = {"a": "add_bal"}; edit(chat, mid, tr(lg, "ask_bal"), kb_cancel(lg)); ok(); return
        if data == "adev":
            PENDING[tg] = {"a": "dev_id"}; edit(chat, mid, tr(lg, "ask_id"), kb_cancel(lg)); ok(); return
        if data == "apromo":
            PENDING[tg] = {"a": "promo_mk"}; edit(chat, mid, tr(lg, "ask_promo"), kb_cancel(lg)); ok(); return
        if data == "abc":
            PENDING[tg] = {"a": "bc"}; edit(chat, mid, tr(lg, "ask_bc"), kb_cancel(lg)); ok(); return
        if data == "aadd":
            PENDING[tg] = {"a": "sn"}; edit(chat, mid, tr(lg, "ask_sn"), kb_cancel(lg)); ok(); return
        if data == "adel":
            rows = get_servers(conn)
            if not rows:
                edit(chat, mid, tr(lg, "no"), kb_admin(lg)); ok(); return
            ikb = [[btn(flag(r[2]) + " #" + str(r[0]) + " " + str(r[2])[:20], "dels_" + str(r[0]))] for r in rows]
            ikb.append([btn(tr(lg, "btn_cancel"), "adm")])
            edit(chat, mid, "Удалить сервер:", {"inline_keyboard": ikb}); ok(); return
        if data.startswith("dels_") and data[5:].isdigit():
            conn.run("delete from server_pool where id=:i", i=int(data[5:]))
            edit(chat, mid, tr(lg, "srv_del"), kb_admin(lg)); ok("OK"); return
        if data == "atick":
            rows = conn.run("select id, telegram_id, subject from tickets where status='open' order by updated_at desc limit 15")
            if not rows:
                edit(chat, mid, "Нет тикетов", kb_admin(lg)); ok(); return
            lines = ["🎫"]
            ikb = []
            for r in rows:
                lines.append("#" + str(r[0]) + " <code>" + str(r[1]) + "</code> " + H.escape(str(r[2] or "")[:40]))
                ikb.append([btn("#" + str(r[0]), "trep_" + str(r[0]))])
            ikb.append([btn(tr(lg, "btn_back"), "adm")])
            edit(chat, mid, chr(10).join(lines), {"inline_keyboard": ikb}); ok(); return
        if data.startswith("trep_"):
            tid = int(data.split("_")[1]); PENDING[tg] = {"a": "trep", "tid": tid}
            edit(chat, mid, tr(lg, "t_ask", id=tid), kb_cancel(lg)); ok(); return
        if data.startswith("tclose_"):
            tid = int(data.split("_")[1])
            conn.run("update tickets set status='closed', updated_at=now() where id=:i", i=tid)
            edit(chat, mid, tr(lg, "t_closed", id=tid), kb_admin(lg)); ok("OK"); return
        if data.startswith("paid_"):
            _, uid_s, d_s = data.split("_", 2)
            uid, days = int(uid_s), int(d_s)
            ensure_user(conn, uid); extend_sub(conn, uid, days, "premium")
            price = calc_price(days) if False else calc_price(days)
            record_payment(conn, uid, "premium", calc_price(days), days, "admin")
            edit(chat, mid, tr(lg, "paid_ok", uid=uid, days=days), {"inline_keyboard": []})
            try:
                uu = get_user(conn, uid)
                send(uid, tr(lang_of(uu), "paid_user", days=days) + "\n\n" + home_text(uu), kb_home(uu))
            except Exception: pass
            ok("OK"); return
        if data.startswith("rej_"):
            _, uid_s, d_s = data.split("_", 2)
            uid, days = int(uid_s), int(d_s)
            edit(chat, mid, tr(lg, "rej_ok", uid=uid), {"inline_keyboard": []})
            try: send(uid, tr("ru", "rej_user", days=days))
            except Exception: pass
            ok("OK"); return
        if data.startswith("topok_"):
            _, uid_s, a_s = data.split("_", 2)
            uid, amount = int(uid_s), int(a_s)
            uu = add_balance(conn, uid, amount)
            record_payment(conn, uid, "topup", amount, 0, "admin")
            edit(chat, mid, tr(lg, "top_ok_a", uid=uid, amount=amount), {"inline_keyboard": []})
            try: send(uid, tr(lang_of(uu), "top_ok_u", amount=amount, bal=float(uu.get("balance") or 0)), kb_home(uu))
            except Exception: pass
            ok("OK"); return
        if data.startswith("toprej_"):
            _, uid_s, a_s = data.split("_", 2)
            edit(chat, mid, tr(lg, "rej_ok", uid=int(uid_s)), {"inline_keyboard": []})
            try: send(int(uid_s), tr("ru", "rej_user", days=0))
            except Exception: pass
            ok("OK"); return

    ok()

def handle_text(conn, msg):
    tg = msg["from"]["id"]
    chat = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()
    un, fn = meta(msg.get("from") or {})
    u = ensure_user(conn, tg, username=un, full_name=fn)
    lg = lang_of(u)
    if u.get("banned") and tg != ADMIN_ID:
        send(chat, tr(lg, "ban_msg", reason=H.escape(u.get("ban_reason") or "—")))
        return

    pend = PENDING.get(tg) or {}
    a = pend.get("a")

    # commands
    if text.startswith("/"):
        cmd = text.split()[0].split("@")[0].lower()
        arg = text[len(text.split()[0]):].strip()
        if cmd == "/start":
            ref = arg[4:].strip() if arg.startswith("ref_") else None
            clear_pend(tg)
            handle_start(conn, msg, ref)
            return
        if cmd in ("/menu", "/home"):
            clear_pend(tg)
            if not u.get("lang"):
                send(chat, tr("ru", "lang_pick"), kb_lang()); return
            send(chat, home_text(u), kb_home(u)); return
        if cmd == "/admin" and tg == ADMIN_ID:
            clear_pend(tg)
            send(chat, admin_title(conn, lg), kb_admin(lg)); return

    if not a:
        # ignore plain text
        return

    # pending flows
    if a == "custom_days":
        if (not text.isdigit()) or not (CUSTOM_DAY_MIN <= int(text) <= CUSTOM_DAY_MAX):
            send(chat, tr(lg, "cust_bad", a=CUSTOM_DAY_MIN, z=CUSTOM_DAY_MAX), kb_cancel(lg)); return
        days = int(text); clear_pend(tg)
        price = calc_price(days)
        send(chat, tr(lg, "pay_title", days=days, price=price), kb_pay(lg, days)); return

    if a == "promo":
        code = text.strip().upper(); clear_pend(tg)
        row = conn.run("select code, kind, value, max_uses, used_count, active from promo_codes where code=:c", c=code)
        if not row or not row[0][5] or int(row[0][4]) >= int(row[0][3]):
            send(chat, tr(lg, "promo_bad"), kb_home(u)); return
        if conn.run("select 1 from promo_redemptions where code=:c and telegram_id=:i", c=code, i=tg):
            send(chat, tr(lg, "promo_used"), kb_home(u)); return
        kind, val = row[0][1], float(row[0][2])
        if kind == "days":
            u = extend_sub(conn, tg, int(val), "premium"); msg = tr(lg, "promo_days", v=int(val))
        elif kind == "balance":
            u = add_balance(conn, tg, val); msg = tr(lg, "promo_bal", v=val)
        elif kind == "percent":
            conn.run("update users set promo_percent=:p where telegram_id=:i", p=val, i=tg)
            u = get_user(conn, tg); msg = tr(lg, "promo_pct", v=val)
        else:
            send(chat, tr(lg, "promo_bad"), kb_home(u)); return
        conn.run("insert into promo_redemptions(code, telegram_id) values(:c,:i)", c=code, i=tg)
        conn.run("update promo_codes set used_count=used_count+1 where code=:c", c=code)
        send(chat, msg + "\n\n" + home_text(u), kb_home(u)); return

    if a == "help":
        clear_pend(tg)
        rows = conn.run("insert into tickets(telegram_id,status,subject) values(:i,'open',:s) returning id", i=tg, s=text[:80])
        tid = int(rows[0][0])
        conn.run("insert into ticket_messages(ticket_id,sender,body) values(:t,'user',:b)", t=tid, b=text)
        send(chat, tr(lg, "help_ok", id=tid), kb_home(u))
        try:
            send(ADMIN_ID, tr("ru", "help_adm", id=tid, uid=tg, name=H.escape(dname(u)), body=H.escape(text)), kb_ticket(tid))
        except Exception:
            pass
        return

    # admin pendings
    if tg != ADMIN_ID:
        return

    if a == "grant_id":
        if not text.isdigit():
            send(chat, tr(lg, "ask_id"), kb_cancel(lg)); return
        PENDING[tg] = {"a": "grant_days", "uid": int(text)}
        send(chat, "Срок:", kb_days("guser_" + text, lg)); return
    if a == "trial_id":
        if not text.isdigit():
            send(chat, tr(lg, "ask_id"), kb_cancel(lg)); return
        uid = int(text); ensure_user(conn, uid)
        exp = utcnow() + timedelta(days=7)
        conn.run("update users set status='trial', trial_used=true, subscription_expires=:e, notify_2d=false, notify_1d=false, notify_1h=false, notify_exp=false where telegram_id=:i", e=exp, i=uid)
        clear_pend(tg); send(chat, tr(lg, "trial_g", i=uid), kb_admin(lg)); return
    if a == "rev_id":
        if not text.isdigit():
            send(chat, tr(lg, "ask_id"), kb_cancel(lg)); return
        conn.run("update users set status='free', subscription_expires=null where telegram_id=:i", i=int(text))
        clear_pend(tg); send(chat, tr(lg, "rev_ok", i=int(text)), kb_admin(lg)); return
    if a == "find_id":
        if not text.isdigit():
            send(chat, tr(lg, "ask_id"), kb_cancel(lg)); return
        uu = get_user(conn, int(text)); clear_pend(tg)
        send(chat, home_text(uu) if uu else tr(lg, "no"), kb_admin(lg)); return
    if a == "ban_id":
        if not text.isdigit():
            send(chat, tr(lg, "ask_id"), kb_cancel(lg)); return
        PENDING[tg] = {"a": "ban_reason", "uid": int(text)}
        send(chat, tr(lg, "ask_banr"), kb_cancel(lg)); return
    if a == "ban_reason":
        uid = int(pend.get("uid") or 0); clear_pend(tg)
        set_ban(conn, uid, True, text)
        send(chat, tr(lg, "ban_ok", i=uid), kb_admin(lg))
        try: send(uid, tr("ru", "ban_msg", reason=H.escape(text)))
        except Exception: pass
        return
    if a == "unban_id":
        if not text.isdigit():
            send(chat, tr(lg, "ask_id"), kb_cancel(lg)); return
        clear_pend(tg); set_ban(conn, int(text), False, "")
        send(chat, tr(lg, "unban_ok", i=int(text)), kb_admin(lg)); return
    if a == "add_bal":
        parts = text.split()
        if len(parts) < 2 or not parts[0].isdigit():
            send(chat, tr(lg, "ask_bal"), kb_cancel(lg)); return
        try: amount = float(parts[1].replace(",", "."))
        except Exception:
            send(chat, tr(lg, "ask_bal"), kb_cancel(lg)); return
        uid = int(parts[0]); clear_pend(tg)
        uu = add_balance(conn, uid, amount)
        send(chat, tr(lg, "bal_add", a=amount, i=uid, b=float(uu.get("balance") or 0)), kb_admin(lg))
        try: send(uid, tr(lang_of(uu), "top_ok_u", amount=amount, bal=float(uu.get("balance") or 0)))
        except Exception: pass
        return
    if a == "dev_id":
        if not text.isdigit():
            send(chat, tr(lg, "ask_id"), kb_cancel(lg)); return
        uid = int(text); clear_pend(tg)
        try: conn.run("update devices set blocked=true where telegram_id=:i", i=uid)
        except Exception: conn.run("delete from devices where telegram_id=:i", i=uid)
        send(chat, tr(lg, "dev_reset", i=uid), kb_admin(lg)); return
    if a == "promo_mk":
        parts = text.split(); clear_pend(tg)
        if len(parts) < 3:
            send(chat, tr(lg, "ask_promo"), kb_admin(lg)); return
        code, kind = parts[0].upper(), parts[1].lower()
        try: val = float(parts[2].replace(",", "."))
        except Exception:
            send(chat, tr(lg, "ask_promo"), kb_admin(lg)); return
        if kind not in ("days", "balance", "percent"):
            send(chat, tr(lg, "ask_promo"), kb_admin(lg)); return
        mx = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 100
        conn.run("insert into promo_codes(code,kind,value,max_uses,used_count,active) values(:c,:k,:v,:m,0,true) on conflict(code) do update set kind=:k,value=:v,max_uses=:m,active=true", c=code, k=kind, v=val, m=mx)
        send(chat, tr(lg, "promo_mk", c=code), kb_admin(lg)); return
    if a == "bc":
        ids = [r[0] for r in conn.run("select telegram_id from users")]; o = f = 0; clear_pend(tg)
        for i in ids:
            try: send(i, "📢 <b>" + BRAND + "</b>\n\n" + H.escape(text)); o += 1; time.sleep(0.03)
            except Exception: f += 1
        send(chat, tr(lg, "bc_ok", o=o, f=f), kb_admin(lg)); return
    if a == "sn":
        PENDING[tg] = {"a": "sc", "name": text}; send(chat, tr(lg, "ask_sc"), kb_cancel(lg)); return
    if a == "sc":
        name = pend.get("name") or "Server"
        r = conn.run("insert into server_pool(raw_config, custom_name) values(:c,:n) returning id, custom_name", c=text, n=name)
        clear_pend(tg); send(chat, tr(lg, "srv_add", i=r[0][0], n=H.escape(r[0][1])), kb_admin(lg)); return
    if a == "trep":
        tid = int(pend.get("tid") or 0); clear_pend(tg)
        rows = conn.run("select telegram_id from tickets where id=:i", i=tid)
        if not rows:
            send(chat, tr(lg, "no"), kb_admin(lg)); return
        uid = int(rows[0][0])
        conn.run("insert into ticket_messages(ticket_id,sender,body) values(:t,'admin',:b)", t=tid, b=text)
        conn.run("update tickets set updated_at=now() where id=:i", i=tid)
        send(chat, "OK", kb_admin(lg))
        try: send(uid, tr(lang_of(get_user(conn, uid) or {}), "help_reply", id=tid, body=H.escape(text)))
        except Exception: pass
        return

def process(conn, upd):
    if "callback_query" in upd:
        handle_cb(conn, upd["callback_query"]); return
    msg = upd.get("message") or upd.get("edited_message")
    if not msg: return
    if msg.get("text") is not None:
        handle_text(conn, msg)

# ---------------- HTTP cabinet / sub ----------------

def is_browser(ua):
    s = (ua or "").lower()
    if not s: return False
    for m in ("v2ray", "clash", "hiddify", "streisand", "shadowrocket", "nekobox", "sing-box", "happ", "okhttp"):
        if m in s: return False
    return any(x in s for x in ("mozilla", "chrome", "safari", "firefox", "edge"))

def client_ip(h):
    xff = h.headers.get("X-Forwarded-For") or ""
    if xff: return xff.split(",")[0].strip()[:64]
    try: return (h.client_address[0] or "")[:64]
    except Exception: return ""

def dev_hash(ua, ip):
    return hashlib.sha256(((ua or "?") + "|" + (ip or "")).encode("utf-8", "ignore")).hexdigest()[:32]

def dev_name(ua):
    s = (ua or "").lower()
    for k, n in [("hiddify", "Hiddify"), ("happ", "Happ"), ("v2ray", "v2rayNG"), ("clash", "Clash"), ("streisand", "Streisand"), ("shadowrocket", "Shadowrocket"), ("nekobox", "NekoBox"), ("sing-box", "sing-box"), ("okhttp", "Android")]:
        if k in s: return n
    return ((ua or "Device").split("/")[0].split(" ")[0] or "Device")[:40]

def device_limit(u):
    if not is_active(u["status"], u["subscription_expires"]): return 0
    return TRIAL_DEVICE_LIMIT if u["status"] == "trial" else PREMIUM_DEVICE_LIMIT

def touch_dev(conn, u, ua, ip):
    lim = device_limit(u); tg = u["telegram_id"]; h = dev_hash(ua, ip); name = dev_name(ua)
    ex = conn.run("select id, coalesce(blocked,false) from devices where telegram_id=:t and device_hash=:h", t=tg, h=h)
    if ex:
        if bool(ex[0][1]):
            return False, "blocked"
        conn.run("update devices set last_seen=now(), user_agent=:ua, last_ip=:ip, device_name=:n where id=:i", ua=(ua or "")[:300], ip=ip or "", n=name, i=ex[0][0])
        return True, "ok"
    cnt = int(conn.run("select count(*) from devices where telegram_id=:t and coalesce(blocked,false)=false", t=tg)[0][0])
    if cnt >= lim:
        return False, "limit"
    try:
        conn.run("insert into devices(telegram_id,device_hash,device_name,user_agent,last_ip,blocked) values(:t,:h,:n,:ua,:ip,false)", t=tg, h=h, n=name, ua=(ua or "")[:300], ip=ip or "")
    except Exception:
        conn.run("insert into devices(telegram_id,device_hash,device_name,user_agent,last_ip) values(:t,:h,:n,:ua,:ip)", t=tg, h=h, n=name, ua=(ua or "")[:300], ip=ip or "")
    return True, "ok"

def list_dev(conn, tg):
    return conn.run("select id, device_name, last_seen from devices where telegram_id=:t and coalesce(blocked,false)=false order by last_seen desc", t=tg)

def block_dev(conn, tg, did):
    try:
        r = conn.run("update devices set blocked=true where id=:i and telegram_id=:t returning id", i=int(did), t=tg)
        return bool(r)
    except Exception:
        r = conn.run("delete from devices where id=:i and telegram_id=:t returning id", i=int(did), t=tg)
        return bool(r)

def dummy(title):
    return "vless://00000000-0000-0000-0000-000000000000@127.0.0.1:1?encryption=none&security=none&type=tcp#" + urllib.parse.quote(title, safe="") + "\n"

def b64(s):
    import base64
    return base64.b64encode(str(s).encode()).decode().rstrip("=")

def send_sub(handler, body, exp_ts=0):
    data = body.encode("utf-8") if isinstance(body, str) else body
    info = "upload=0; download=0; total=0; expire=" + str(int(exp_ts or 0))
    handler.send_response(200)
    for k, v in {
        "Content-Type": "text/plain; charset=utf-8",
        "Cache-Control": "no-store",
        "Profile-Update-Interval": "1",
        "profile-update-interval": "1",
        "Profile-Title": "base64:" + b64(BRAND),
        "profile-title": "base64:" + b64(BRAND),
        "Content-Disposition": 'attachment; filename="FluxVPN"',
        "subscription-userinfo": info,
        "Subscription-Userinfo": info,
        "Content-Length": str(len(data)),
    }.items():
        handler.send_header(k, v)
    handler.end_headers(); handler.wfile.write(data)

def render_denied():
    return """<!doctype html><html lang=ru><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><meta name=robots content=noindex><title>FluxVPN</title>
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#090909;color:#eee;font-family:Inter,system-ui,sans-serif}
.card{width:min(400px,90vw);padding:32px;border:1px solid #222;border-radius:20px;background:#111;text-align:center}
h1{margin:0 0 8px;font-size:22px}p{margin:0;color:#888;line-height:1.5}</style>
<div class=card><h1>FluxVPN</h1><p>Нет доступа. Открой бота и продли подписку.</p></div>"""

def render_cab(u, servers, devices, limit):
    active = is_active(u["status"], u["subscription_expires"])
    left = days_left(u["subscription_expires"]) if active else 0
    until = fmt_until(u["subscription_expires"]) if active else "—"
    link = sub_link(u) or ""
    token = H.escape(u.get("sub_token") or "")
    srows = "".join(
        "<div class=row><div class=l><i></i><b>"+flag(s[2])+"</b><span>"+H.escape(str(s[2]))+"</span></div><em>online</em></div>"
        for s in servers
    ) or "<div class=empty>Нет локаций</div>"
    drows = "".join(
        "<div class=row><div class=l><i></i><span>"+H.escape(str(d[1] or "Device"))+"</span></div>"
        "<a class=x href=\"/sub/"+token+"/device/"+str(d[0])+"/delete\">удалить</a></div>"
        for d in devices
    ) or "<div class=empty>Нет устройств</div>"
    happ = "happ://add/" + urllib.parse.quote(link, safe="") if link else "#"
    return f"""<!doctype html><html lang=ru><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><meta name=robots content=noindex,nofollow><meta name=referrer content=no-referrer><title>FluxVPN</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;font-family:Inter,SF Pro Text,system-ui,sans-serif;background:#0a0a0a;color:#f2f2f2}}
.w{{max-width:680px;margin:0 auto;padding:28px 16px 60px}}
.nav{{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}}
.brand{{display:flex;gap:10px;align-items:center;font-weight:800;letter-spacing:.08em}}
.logo{{width:34px;height:34px;border-radius:10px;display:grid;place-items:center;background:#151515;border:1px solid #2a2a2a;font-size:11px}}
.chip{{border:1px solid #2a2a2a;border-radius:999px;padding:6px 10px;font-size:12px;color:#ccc}}
.hero{{padding:22px;border:1px solid #1e1e1e;border-radius:22px;background:linear-gradient(180deg,#121212,#0d0d0d);margin-bottom:14px}}
h1{{margin:0 0 6px;font-size:28px;letter-spacing:-.03em}}p{{margin:0;color:#8a8a8a;font-size:13px;line-height:1.5}}
.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:16px}}
.stat{{background:#0c0c0c;border:1px solid #1c1c1c;border-radius:14px;padding:12px}}
.stat span{{display:block;color:#777;font-size:11px;margin-bottom:4px}}.stat b{{font-size:16px}}
.tabs{{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 12px}}
.tab{{background:#111;border:1px solid #2a2a2a;color:#eee;border-radius:999px;padding:9px 12px;cursor:pointer;font-weight:600}}
.tab.on{{background:#f2f2f2;color:#111;border-color:#f2f2f2}}
.panel{{display:none}}.panel.on{{display:block}}
.card{{background:#0f0f0f;border:1px solid #1e1e1e;border-radius:18px;padding:14px;margin-bottom:10px}}
.head{{display:flex;justify-content:space-between;margin-bottom:10px;font-weight:700}}
.muted{{color:#777;font-size:12px;font-weight:500}}
.actions{{display:grid;grid-template-columns:1.3fr 1fr 1fr;gap:8px}}
.btn{{border:0;border-radius:12px;padding:12px;font-weight:700;cursor:pointer;background:#f2f2f2;color:#111}}
.btn.g{{background:transparent;color:#f2f2f2;border:1px solid #2a2a2a}}
.row{{display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid #171717}}
.row:last-child{{border-bottom:0}}.l{{display:flex;gap:8px;align-items:center}}
.l i{{width:7px;height:7px;border-radius:50%;background:#fff;display:inline-block}}
.x{{color:#111;background:#eee;text-decoration:none;border-radius:999px;padding:6px 10px;font-size:12px;font-weight:700}}
.empty{{color:#777;padding:8px 0}}.toast{{display:none;text-align:center;color:#aaa;margin-top:8px;font-size:12px}}.toast.on{{display:block}}
.note{{color:#777;font-size:12px;line-height:1.45;margin:0 0 10px}}
@media(max-width:560px){{.stats{{grid-template-columns:1fr 1fr}}.actions{{grid-template-columns:1fr}}}}
</style>
<div class=w>
<div class=nav><div class=brand><div class=logo>FX</div>FLUXVPN</div><div class=chip>{"Active" if active else "Inactive"}</div></div>
<div class=hero><h1>Кабинет</h1><p>Статус, локации и устройства. Ключ скрыт — только копирование.</p>
<div class=stats>
<div class=stat><span>Осталось</span><b>{left} дн</b></div>
<div class=stat><span>До</span><b style="font-size:12px">{H.escape(until)}</b></div>
<div class=stat><span>Локации</span><b>{len(servers)}</b></div>
<div class=stat><span>Устройства</span><b>{len(devices)}/{limit}</b></div>
</div></div>
<div class=tabs>
<button class="tab on" data-t=p1 type=button>Обзор</button>
<button class=tab data-t=p2 type=button>Локации</button>
<button class=tab data-t=p3 type=button>Устройства</button>
</div>
<section class="panel on" id=p1><div class=card><div class=head>Подключение <span class=muted>private</span></div>
<div class=actions>
<button class=btn id=c type=button>Скопировать ключ</button>
<button class="btn g" id=h type=button>Happ</button>
<button class="btn g" type=button onclick="history.replaceState({{}},'', '/');flash('OK')">Скрыть</button>
</div><div class=toast id=t></div></div></section>
<section class=panel id=p2><div class=card><div class=head>Локации <span class=muted>{len(servers)}</span></div>{srows}</div></section>
<section class=panel id=p3><div class=card><div class=head>Устройства <span class=muted>{len(devices)}/{limit}</span></div>
<p class=note>Trial — 2, Premium — 4. Удаление блокирует устройство: обнови подписку в VPN-клиенте.</p>{drows}</div></section>
</div>
<script>
const SUB={json.dumps(link)}; const HAPP={json.dumps(happ)};
const t=document.getElementById('t');
function flash(m){{t.textContent=m;t.classList.add('on');clearTimeout(window.__x);window.__x=setTimeout(()=>t.classList.remove('on'),1500)}}
async function copy(){{try{{await navigator.clipboard.writeText(SUB);flash('Скопировано')}}catch(e){{flash('Ошибка')}}}}
document.getElementById('c').onclick=copy;
document.getElementById('h').onclick=()=>{{if(HAPP&&HAPP!=='#') location.href=HAPP; else flash('Нет')}};
document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{{
document.querySelectorAll('.tab').forEach(x=>x.classList.remove('on'));
document.querySelectorAll('.panel').forEach(x=>x.classList.remove('on'));
b.classList.add('on'); document.getElementById(b.dataset.t).classList.add('on');
}});
</script>"""

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, ctype, body):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers(); self.wfile.write(data)

    def do_GET(self):
        try:
            path = urllib.parse.urlparse(self.path).path
            parts = [x for x in path.split("/") if x]
            if path in ("/", "/health", "/favicon.ico"):
                self._send(200, "text/plain; charset=utf-8", "FluxVPN ok"); return
            if not parts or parts[0] != "sub":
                self._send(404, "text/plain; charset=utf-8", "not found"); return

            # delete device
            if len(parts) == 5 and parts[2] == "device" and parts[4] == "delete" and parts[3].isdigit():
                token = parts[1]
                conn = db()
                try:
                    ensure_schema(conn)
                    rows = conn.run(USQL + " where sub_token=:t", t=token)
                    if not rows:
                        self._send(403, "text/html; charset=utf-8", render_denied()); return
                    u = urow(rows[0])
                    if not is_active(u["status"], u["subscription_expires"]):
                        self._send(403, "text/html; charset=utf-8", render_denied()); return
                    block_dev(conn, u["telegram_id"], parts[3])
                    self.send_response(302)
                    self.send_header("Location", "/sub/" + token)
                    self.end_headers(); return
                finally:
                    conn.close()

            if len(parts) < 2:
                self._send(400, "text/plain; charset=utf-8", "bad token"); return
            token = parts[1]
            if len(token) < 16 or len(token) > 128 or not all(c.isalnum() or c in "-_" for c in token):
                self._send(400, "text/plain; charset=utf-8", "bad token"); return

            conn = db()
            try:
                ensure_schema(conn)
                rows = conn.run(USQL + " where sub_token=:t", t=token)
                ua = self.headers.get("User-Agent") or ""
                browser = is_browser(ua)
                ip = client_ip(self)
                if not rows:
                    if browser: self._send(403, "text/html; charset=utf-8", render_denied())
                    else: send_sub(self, dummy("FluxVPN | No access"), 0)
                    return
                u = urow(rows[0])
                lg = lang_of(u)
                exp_ts = 0
                if u.get("subscription_expires") is not None:
                    exp = u["subscription_expires"]
                    if getattr(exp, "tzinfo", None) is None: exp = exp.replace(tzinfo=timezone.utc)
                    exp_ts = int(exp.timestamp())
                active = is_active(u["status"], u["subscription_expires"]) and not u.get("banned")

                if browser:
                    if not active:
                        self._send(200, "text/html; charset=utf-8", render_denied()); return
                    servers = get_servers(conn)
                    devices = list_dev(conn, u["telegram_id"])
                    self._send(200, "text/html; charset=utf-8", render_cab(u, servers, devices, device_limit(u))); return

                if not active:
                    send_sub(self, dummy("FluxVPN | Подписка истекла" if lg == "ru" else "FluxVPN | Subscription expired"), exp_ts); return
                ok, reason = touch_dev(conn, u, ua, ip)
                if not ok:
                    title = "FluxVPN | Устройство удалено" if reason == "blocked" else "FluxVPN | Лимит устройств"
                    if lg == "en":
                        title = "FluxVPN | Device removed" if reason == "blocked" else "FluxVPN | Device limit"
                    send_sub(self, dummy(title), exp_ts); return
                servers = get_servers(conn)
                lines = [brand_cfg(s[1], s[2]) for s in servers if brand_cfg(s[1], s[2])]
                body = "\n".join(lines) + ("\n" if lines else "")
                send_sub(self, body, exp_ts)
            finally:
                conn.close()
        except Exception:
            print("http", traceback.format_exc(), flush=True)
            try: self._send(500, "text/plain; charset=utf-8", "server error")
            except Exception: pass

def notification_loop():
    while True:
        try:
            conn = db()
            try:
                ensure_schema(conn)
                now = utcnow()
                for r in conn.run(USQL):
                    u = urow(r)
                    if u.get("banned"): continue
                    exp = u.get("subscription_expires")
                    if not exp: continue
                    if getattr(exp, "tzinfo", None) is None: exp = exp.replace(tzinfo=timezone.utc)
                    left = (exp - now).total_seconds()
                    lg = lang_of(u); tid = u["telegram_id"]
                    def mark(col):
                        conn.run("update users set " + col + "=true where telegram_id=:i", i=tid)
                    try:
                        if left <= 0 and not u.get("notify_exp"):
                            send(tid, tr(lg, "nx", b=BRAND)); mark("notify_exp")
                        elif 0 < left <= 3600 and not u.get("notify_1h"):
                            send(tid, tr(lg, "nh", b=BRAND)); mark("notify_1h")
                        elif left <= 86400 and not u.get("notify_1d"):
                            send(tid, tr(lg, "n1", b=BRAND)); mark("notify_1d")
                        elif left <= 2*86400 and not u.get("notify_2d"):
                            send(tid, tr(lg, "n2", b=BRAND)); mark("notify_2d")
                    except Exception:
                        pass
            finally:
                conn.close()
        except Exception as e:
            print("notify", e, flush=True)
        time.sleep(60)

def start_http():
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print("HTTP", PORT, flush=True)

def main():
    print("start", BRAND, flush=True)
    start_http()
    threading.Thread(target=notification_loop, daemon=True).start()
    try:
        me = api("getMe")
        if me.get("username"):
            os.environ["BOT_USERNAME"] = me["username"]
            print("@"+me["username"], flush=True)
    except Exception as e:
        print("getMe", e, flush=True)
    try:
        c = db(); ensure_schema(c); c.close(); print("schema ok", flush=True)
    except Exception:
        print(traceback.format_exc(), flush=True)
    try: api("deleteWebhook", {"drop_pending_updates": False})
    except Exception as e: print("wh", e, flush=True)
    off = 0
    while True:
        try:
            ups = api("getUpdates", {"timeout": 50, "offset": off, "allowed_updates": ["message", "callback_query"]}, timeout=60)
            conn = db()
            try:
                ensure_schema(conn)
                for u in ups:
                    off = u["update_id"] + 1
                    try: process(conn, u)
                    except Exception: print("upd", traceback.format_exc(), flush=True)
            finally:
                conn.close()
        except Exception:
            print("loop", traceback.format_exc(), flush=True)
            time.sleep(3)

def process(conn, upd):
    if "callback_query" in upd:
        handle_cb(conn, upd["callback_query"]); return
    msg = upd.get("message") or upd.get("edited_message")
    if msg and msg.get("text") is not None:
        handle_text(conn, msg)

if __name__ == "__main__":
    main()
