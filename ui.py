from config import ADMIN_ID, ADMIN_USERNAME, PLAN_PRICES, TOPUP_AMOUNTS
from texts import text

def keyboard(*rows): return {"inline_keyboard":list(rows)}
def button(label, callback=None, url=None, copy=None):
    item={"text":label}
    if callback: item["callback_data"]=callback
    elif url: item["url"]=url
    elif copy is not None: item["copy_text"]={"text":copy}
    else: raise ValueError("button action required")
    return item

def language_keyboard(): return keyboard([button("🇷🇺 Русский","lang:ru"),button("🇬🇧 English","lang:en")])
def cancel_keyboard(lang, destination="home"): return keyboard([button("❌ " + text(lang,"cancelled"),destination)])
def back_keyboard(lang, destination="home"): return keyboard([button("⬅️",destination)])

def home_keyboard(user, active, subscription_url, referral_url):
    lang=user["lang"]
    rows=[]
    if not active and not user["trial_used"]: rows.append([button("✨ Trial","trial")])
    rows.append([button("💎 Premium","buy")])
    if active and subscription_url:
        rows.append([button("🔑 Key",copy=subscription_url),button("🖥 Cabinet",url=subscription_url)])
        rows.append([button("🛰 Servers","servers")])
    rows.append([button("🎁 Referral","referral"),button("💰 Balance","balance")])
    rows.append([button("🏷 Promo","promo"),button("💬 Support","support")])
    rows.append([button("🌐 Language","language")])
    if int(user["telegram_id"]) == int(ADMIN_ID):
        rows.append([button("🛠 ADMIN PANEL","admin:home")])
    return keyboard(*rows)

def plans_keyboard(lang):
    return keyboard(
        [button("7 days · 50₽","buy:7"),button("30 days · 200₽","buy:30")],
        [button("90 days · 400₽","buy:90"),button("1 year · 800₽","buy:365")],
        [button("✏️ Custom days","buy:custom")],
        [button("⬅️","home")],
    )
def checkout_keyboard(lang,days):
    return keyboard(
        [button("🪙 CryptoBot",f"pay:crypto:{days}")],
        [button("💰 Balance",f"pay:balance:{days}")],
        [button("👤 @"+ADMIN_USERNAME,f"pay:admin:{days}")],
        [button("⬅️","buy")],
    )
def admin_order_keyboard(user_id,days,price):
    return keyboard([button("✅ Заказ оплачен",f"order:paid:{user_id}:{days}:{price}")],[button("❌ Отклонить",f"order:reject:{user_id}:{days}")])
def balance_keyboard(lang): return keyboard([button("➕ Top up","topup")],[button("💎 Premium","buy")],[button("⬅️","home")])
def topup_keyboard(lang):
    rows=[]
    for index in range(0,len(TOPUP_AMOUNTS),2): rows.append([button(f"{amount}₽",f"topup:{amount}") for amount in TOPUP_AMOUNTS[index:index+2]])
    rows.append([button("⬅️","balance")]); return keyboard(*rows)
def topup_methods_keyboard(amount, manual_url): return keyboard([button("🪙 CryptoBot",f"topup:crypto:{amount}")],[button("👤 Admin",url=manual_url)],[button("⬅️","balance")])
def topup_admin_keyboard(user_id,amount): return keyboard([button("✅ Баланс пополнен",f"topup:paid:{user_id}:{amount}")],[button("❌ Отклонить",f"topup:reject:{user_id}:{amount}")])
def crypto_keyboard(lang,pay_url,invoice_id,kind): return keyboard([button("💳 Pay",url=pay_url)],[button("🔄 Check",f"crypto:check:{kind}:{invoice_id}")],[button("⬅️","home")])
def referral_keyboard(lang,referral_url): return keyboard([button("📋 Copy",copy=referral_url)],[button("⬅️","home")])
def servers_keyboard(lang,subscription_url): return keyboard([button("🔑 Copy key",copy=subscription_url),button("🖥 Cabinet",url=subscription_url)],[button("⬅️","home")])
def ticket_keyboard(ticket_id): return keyboard([button("↩️ Ответить",f"ticket:reply:{ticket_id}"),button("✅ Закрыть",f"ticket:close:{ticket_id}")])

def admin_keyboard(lang):
    return keyboard(
        [button("📊 Dashboard","admin:home"),button("📈 Revenue","admin:revenue")],
        [button("👥 Users","admin:users"),button("🟢 Active","admin:active")],
        [button("🔎 Find","admin:find"),button("➕ Grant","admin:grant")],
        [button("✨ Trial","admin:trial"),button("⛔ Revoke","admin:revoke")],
        [button("🚫 Ban","admin:ban"),button("✅ Unban","admin:unban")],
        [button("💰 Add balance","admin:balance"),button("📱 Reset devices","admin:devices")],
        [button("🏷 Promos","admin:promo"),button("🎫 Tickets","admin:tickets")],
        [button("🛰 Servers","admin:servers"),button("➕ Server","admin:server_add")],
        [button("🗑 Delete server","admin:server_delete"),button("📣 Broadcast","admin:broadcast")],
        [button("⬅️ User menu","home")],
    )
def days_keyboard(prefix,lang):
    return keyboard([button("7",f"{prefix}:7"),button("30",f"{prefix}:30")],[button("90",f"{prefix}:90"),button("365",f"{prefix}:365")],[button("∞",f"{prefix}:9999")],[button("❌","admin:home")])
