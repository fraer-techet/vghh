import html
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from config import ADMIN_USERNAME, CRYPTO_BOT_TOKEN, CUSTOM_MAX_DAYS, CUSTOM_MIN_DAYS, PLAN_PRICES, PUBLIC_URL, REF_PERCENT
from database import add_balance, days_left, extend_subscription, get_user, is_active, record_payment


def display_name(user):
    if user.get("full_name"): return user["full_name"]
    if user.get("username"): return "@" + user["username"]
    return str(user["telegram_id"])

def subscription_url(user):
    return PUBLIC_URL + "/sub/" + user["sub_token"] if PUBLIC_URL else ""

def referral_url(user, bot_username):
    code=user.get("referral_code") or ""
    return ("https://t.me/" + bot_username + "?start=ref_" + code) if bot_username else ("ref_" + code)

def calculate_price(days):
    days=int(days)
    if days in PLAN_PRICES:return PLAN_PRICES[days]
    if days<CUSTOM_MIN_DAYS or days>CUSTOM_MAX_DAYS:raise ValueError("days out of range")
    if days<=7:return max(30,round(days*50/7))
    if days<=30:return round(50+(days-7)*150/23)
    if days<=90:return round(200+(days-30)*200/60)
    if days<=365:return round(400+(days-90)*400/275)
    return round(800+(days-365)*2)

def discounted_price(user,days):
    base=calculate_price(days);percent=float(user.get("promo_percent") or 0)
    return max(1,round(base*(100-percent)/100)),base,percent

def plan_name(user):
    if not is_active(user):return "Free"
    return "Trial" if user["status"]=="trial" else "Premium"

def until_text(user):
    expires=user.get("subscription_expires")
    if not expires:return "—"
    if expires.tzinfo is None:expires=expires.replace(tzinfo=timezone.utc)
    return expires.strftime("%d.%m.%Y %H:%M UTC")

def manual_order(user,days,price):
    return "\n".join(["FluxVPN order",f"ID: {user['telegram_id']}",f"User: {display_name(user)}",f"Plan: {days} days",f"Price: {price} RUB"])

def manual_admin_url(order):
    return "https://t.me/"+ADMIN_USERNAME+"?text="+urllib.parse.quote(order)

def crypto_call(method,payload):
    if not CRYPTO_BOT_TOKEN:raise RuntimeError("CRYPTO_BOT_TOKEN missing")
    data=json.dumps(payload).encode();headers={"Content-Type":"application/json","Crypto-Pay-API-Token":CRYPTO_BOT_TOKEN}
    request=urllib.request.Request("https://pay.crypt.bot/api/"+method,data=data,headers=headers,method="POST")
    with urllib.request.urlopen(request,timeout=30) as response:body=json.loads(response.read().decode())
    if not body.get("ok"):raise RuntimeError(str(body))
    return body["result"]
def create_invoice(amount,description,payload):
    return crypto_call("createInvoice",{"currency_type":"fiat","fiat":"RUB","amount":str(int(amount)),"description":description[:1024],"payload":payload[:4096],"expires_in":3600,"allow_comments":False,"allow_anonymous":True})
def get_invoice(invoice_id):
    result=crypto_call("getInvoices",{"invoice_ids":str(invoice_id)})
    if isinstance(result,dict):
        items=result.get("items") or []
        return items[0] if items else None
    return result[0] if isinstance(result,list) and result else None

def get_servers(db):return db.run("select id,name,config from servers where enabled=true order by id")
def branded_config(config,name):
    value=(config or "").strip()
    if not value:return ""
    cut=value.rfind("#")
    return (value[:cut] if cut>=0 else value)+"#"+str(name)
def server_flag(name):
    for char in str(name):
        if 0x1F1E6<=ord(char)<=0x1F1FF:return char
    return "•"

def stats(db):
    users=int(db.run("select count(*) from users")[0][0]);servers=int(db.run("select count(*) from servers where enabled=true")[0][0])
    tickets=int(db.run("select count(*) from tickets where status='open'")[0][0]);active=premium=trial=0
    from database import USER_COLUMNS,row_to_user
    for row in db.run(f"select {USER_COLUMNS} from users"):
        user=row_to_user(row)
        if is_active(user):
            active+=1
            premium+=user["status"]=="premium";trial+=user["status"]=="trial"
    revenue=float(db.run("select coalesce(sum(amount),0) from payments where kind in ('premium','topup')")[0][0] or 0)
    today=float(db.run("select coalesce(sum(amount),0) from payments where kind in ('premium','topup') and created_at>=date_trunc('day',now())")[0][0] or 0)
    return dict(users=users,servers=servers,tickets=tickets,active=active,premium=premium,trial=trial,revenue=revenue,today=today)
def revenue_stats(db):
    all_time=float(db.run("select coalesce(sum(amount),0) from payments where kind in ('premium','topup')")[0][0] or 0)
    today=float(db.run("select coalesce(sum(amount),0) from payments where kind in ('premium','topup') and created_at>=now()-interval '1 day'")[0][0] or 0)
    week=float(db.run("select coalesce(sum(amount),0) from payments where kind in ('premium','topup') and created_at>=now()-interval '7 days'")[0][0] or 0)
    month=float(db.run("select coalesce(sum(amount),0) from payments where kind in ('premium','topup') and created_at>=now()-interval '30 days'")[0][0] or 0)
    payments=int(db.run("select count(*) from payments where kind in ('premium','topup')")[0][0])
    return dict(all_time=all_time,today=today,week=week,month=month,payments=payments)
