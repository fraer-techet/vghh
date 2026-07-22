import html
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import database
from config import ADMIN_ID, ADMIN_USERNAME, CUSTOM_MAX_DAYS, CUSTOM_MIN_DAYS, REF_DAYS, REF_PERCENT, TOPUP_AMOUNTS
from services import calculate_price, create_invoice, discounted_price, display_name, get_invoice, get_servers, manual_admin_url, manual_order, plan_name, referral_url, revenue_stats, server_flag, stats, subscription_url, until_text
from telegram import answer, edit, send
from texts import text
from ui import admin_keyboard, admin_order_keyboard, back_keyboard, balance_keyboard, button, cancel_keyboard, checkout_keyboard, crypto_keyboard, days_keyboard, home_keyboard, keyboard, language_keyboard, plans_keyboard, referral_keyboard, servers_keyboard, ticket_keyboard, topup_admin_keyboard, topup_keyboard, topup_methods_keyboard

PENDING={}
BOT_USERNAME=""

def set_bot_username(username):
    global BOT_USERNAME;BOT_USERNAME=(username or "").lstrip("@")
def user_meta(source):
    username=source.get("username");full_name=((source.get("first_name") or "")+" "+(source.get("last_name") or "")).strip() or None
    return username,full_name
def language(user):return user.get("lang") if user.get("lang") in ("ru","en") else "ru"
def is_admin(user_id):return int(user_id)==int(ADMIN_ID)
def clear_pending(user_id):PENDING.pop(int(user_id),None)
def require_admin(query_id,user_id):
    if is_admin(user_id):return True
    answer(query_id,"Admin only",True);return False

def home_message(user):
    lang=language(user);active=database.is_active(user)
    subscription=text(lang,"sub_active",plan=plan_name(user),days=database.days_left(user),until=until_text(user)) if active else text(lang,"sub_inactive")
    return text(lang,"home",name=html.escape(display_name(user)),subscription=subscription,balance=float(user.get("balance") or 0),referrals=int(user.get("referral_count") or 0),earned=float(user.get("referral_earned") or 0))
def show_home(db,chat_id,message_id,user):
    active=database.is_active(user);edit(chat_id,message_id,home_message(user),home_keyboard(user,active,subscription_url(user),referral_url(user,BOT_USERNAME)))
def send_home(db,chat_id,user,prefix=""):
    active=database.is_active(user);send(chat_id,(prefix+"\n\n" if prefix else "")+home_message(user),home_keyboard(user,active,subscription_url(user),referral_url(user,BOT_USERNAME)))
def admin_message(db,lang):return text(lang,"admin",**stats(db))
def show_admin(db,chat_id,message_id,lang):edit(chat_id,message_id,admin_message(db,lang),admin_keyboard(lang))
def send_admin(db,chat_id,lang):send(chat_id,admin_message(db,lang),admin_keyboard(lang))

def start(db,message,argument=""):
    user_id=message["from"]["id"];chat_id=message["chat"]["id"];username,full_name=user_meta(message["from"])
    referral=argument[4:] if argument.startswith("ref_") else None
    user=database.ensure_user(db,user_id,username,full_name,referral)
    if user.get("banned") and not is_admin(user_id):send(chat_id,text(language(user),"banned",reason=html.escape(user.get("ban_reason") or "—")));return
    if not user.get("lang"):
        send(chat_id,text("ru","language"),language_keyboard());return
    send_home(db,chat_id,user)

def callback(db,query):
    data=query.get("data") or "";user_id=query["from"]["id"];chat_id=query["message"]["chat"]["id"];message_id=query["message"]["message_id"]
    username,full_name=user_meta(query["from"]);user=database.ensure_user(db,user_id,username,full_name);lang=language(user)
    def ack(message=None,alert=False):answer(query["id"],message,alert)
    if user.get("banned") and not is_admin(user_id) and not data.startswith("lang:"):
        ack(text(lang,"banned",reason=user.get("ban_reason") or "—"),True);return

    # Navigation and language are resolved first, before every permission gate.
    if data=="home":clear_pending(user_id);show_home(db,chat_id,message_id,user);ack();return
    if data=="language":edit(chat_id,message_id,text(lang,"language"),language_keyboard());ack();return
    if data.startswith("lang:"):
        selected=data.split(":",1)[1]
        if selected not in ("ru","en"):ack();return
        db.run("update users set lang=:lang where telegram_id=:id",lang=selected,id=user_id);user=database.get_user(db,user_id)
        edit(chat_id,message_id,text(selected,"language_saved")+"\n\n"+home_message(user),home_keyboard(user,database.is_active(user),subscription_url(user),referral_url(user,BOT_USERNAME)));ack();return

    # The admin entrance is intentionally exact and precedes all other admin routing.
    if data=="admin:home":
        if not require_admin(query["id"],user_id):return
        clear_pending(user_id);show_admin(db,chat_id,message_id,lang);ack();return

    if data=="trial":
        if database.is_active(user):ack(text(lang,"already_active"),True);return
        if user["trial_used"]:ack(text(lang,"trial_used"),True);return
        expires=datetime.now(timezone.utc)+timedelta(days=7)
        db.run("update users set status='trial',trial_used=true,subscription_expires=:expires,notify_2d=false,notify_1d=false,notify_1h=false,notify_exp=false where telegram_id=:id",expires=expires,id=user_id)
        user=database.get_user(db,user_id);edit(chat_id,message_id,text(lang,"trial_ok")+"\n\n"+home_message(user),home_keyboard(user,True,subscription_url(user),referral_url(user,BOT_USERNAME)));ack("OK");return
    if data=="buy":edit(chat_id,message_id,text(lang,"buy"),plans_keyboard(lang));ack();return
    if data=="buy:custom":PENDING[user_id]={"action":"custom_days"};edit(chat_id,message_id,text(lang,"custom_days",minimum=CUSTOM_MIN_DAYS,maximum=CUSTOM_MAX_DAYS),cancel_keyboard(lang));ack();return
    if data.startswith("buy:"):
        raw=data.split(":",1)[1]
        if not raw.isdigit():ack();return
        days=int(raw)
        try:price,base,discount=discounted_price(user,days)
        except ValueError:ack("Invalid days",True);return
        discount_label=(f"\nСкидка: <b>−{discount:.0f}%</b>" if discount else "")
        edit(chat_id,message_id,text(lang,"checkout",days=days,price=price,discount=discount_label),checkout_keyboard(lang,days));ack();return
    if data.startswith("pay:balance:"):
        days=int(data.rsplit(":",1)[1]);price,_,_=discounted_price(user,days)
        if float(user.get("balance") or 0)<price:ack(text(lang,"balance_low",price=price,balance=float(user.get("balance") or 0)),True);return
        if not database.charge_balance(db,user_id,price):ack(text(lang,"balance_low",price=price,balance=float(user.get("balance") or 0)),True);return
        user=database.extend_subscription(db,user_id,days);database.record_payment(db,user_id,"premium",price,days,"balance")
        edit(chat_id,message_id,text(lang,"balance_paid",price=price,days=days)+"\n\n"+home_message(user),home_keyboard(user,True,subscription_url(user),referral_url(user,BOT_USERNAME)));ack("OK");return
    if data.startswith("pay:admin:"):
        days=int(data.rsplit(":",1)[1]);price,_,_=discounted_price(user,days);order=manual_order(user,days,price)
        edit(chat_id,message_id,text(lang,"manual_order",days=days,price=price,order=html.escape(order)),keyboard([button("👤 @"+ADMIN_USERNAME,url=manual_admin_url(order))],[button("⬅️","buy")]))
        try:send(ADMIN_ID,text("ru","admin_order",user_id=user_id,name=html.escape(display_name(user)),days=days,price=price),admin_order_keyboard(user_id,days,price))
        except Exception:pass
        ack();return
    if data.startswith("pay:crypto:"):
        days=int(data.rsplit(":",1)[1]);price,_,_=discounted_price(user,days)
        try:
            invoice=create_invoice(price,f"FluxVPN Premium {days} days",f"premium:{user_id}:{days}:{price}");invoice_id=invoice.get("invoice_id") or invoice.get("id");url=invoice.get("bot_invoice_url") or invoice.get("pay_url") or invoice.get("mini_app_invoice_url")
            if not invoice_id or not url:raise RuntimeError("bad invoice")
            edit(chat_id,message_id,text(lang,"crypto_invoice",amount=price),crypto_keyboard(lang,url,invoice_id,"premium"))
        except Exception as error:
            print("crypto create",error,flush=True);edit(chat_id,message_id,text(lang,"crypto_error"),checkout_keyboard(lang,days))
        ack();return
    if data.startswith("crypto:check:"):
        parts=data.split(":")
        if len(parts)!=4:ack();return
        kind,invoice_id=parts[2],parts[3]
        try:invoice=get_invoice(invoice_id)
        except Exception as error:print("crypto check",error,flush=True);ack(text(lang,"crypto_wait"),True);return
        if not invoice or invoice.get("status")!="paid":ack(text(lang,"crypto_wait"),True);return
        external="crypto:"+str(invoice_id)
        if not database.payment_once(db,external):ack("Already processed",True);return
        payload=str(invoice.get("payload") or "");tokens=payload.split(":")
        if kind=="premium" and len(tokens)==4 and tokens[0]=="premium":
            target,days,price=int(tokens[1]),int(tokens[2]),float(tokens[3])
            if target!=user_id and not is_admin(user_id):ack();return
            target_user=database.extend_subscription(db,target,days);db.run("update users set promo_percent=0 where telegram_id=:id",id=target);database.record_payment(db,target,"premium",price,days,"crypto",external)
            edit(chat_id,message_id,text(lang,"crypto_paid",days=days)+"\n\n"+home_message(target_user),home_keyboard(target_user,True,subscription_url(target_user),referral_url(target_user,BOT_USERNAME)));ack("OK");return
        if kind=="topup" and len(tokens)==3 and tokens[0]=="topup":
            target,amount=int(tokens[1]),float(tokens[2])
            if target!=user_id and not is_admin(user_id):ack();return
            target_user=database.add_balance(db,target,amount);database.record_payment(db,target,"topup",amount,0,"crypto",external)
            edit(chat_id,message_id,text(lang,"topup_paid",amount=amount)+"\n\n"+home_message(target_user),home_keyboard(target_user,database.is_active(target_user),subscription_url(target_user),referral_url(target_user,BOT_USERNAME)));ack("OK");return
        ack();return

    if data=="balance":edit(chat_id,message_id,text(lang,"balance",balance=float(user.get("balance") or 0)),balance_keyboard(lang));ack();return
    if data=="topup":edit(chat_id,message_id,text(lang,"topup"),topup_keyboard(lang));ack();return
    if data.startswith("topup:crypto:"):
        amount=int(data.rsplit(":",1)[1])
        try:
            invoice=create_invoice(amount,f"FluxVPN balance top-up {amount} RUB",f"topup:{user_id}:{amount}");invoice_id=invoice.get("invoice_id") or invoice.get("id");url=invoice.get("bot_invoice_url") or invoice.get("pay_url") or invoice.get("mini_app_invoice_url")
            if not invoice_id or not url:raise RuntimeError("bad invoice")
            edit(chat_id,message_id,text(lang,"topup_invoice",amount=amount),crypto_keyboard(lang,url,invoice_id,"topup"))
        except Exception as error:print("topup crypto",error,flush=True);edit(chat_id,message_id,text(lang,"crypto_error"),topup_keyboard(lang))
        ack();return
    if data.startswith("topup:") and data.split(":",1)[1].isdigit():
        amount=int(data.split(":",1)[1])
        if amount not in TOPUP_AMOUNTS:ack();return
        order=f"FluxVPN top-up\nID: {user_id}\nUser: {display_name(user)}\nAmount: {amount} RUB";url=manual_admin_url(order)
        edit(chat_id,message_id,text(lang,"topup_invoice",amount=amount),topup_methods_keyboard(amount,url))
        try:send(ADMIN_ID,f"💳 <b>Пополнение</b>\n<code>{user_id}</code> · {html.escape(display_name(user))}\n<b>{amount} ₽</b>",topup_admin_keyboard(user_id,amount))
        except Exception:pass
        ack();return
    if data=="promo":PENDING[user_id]={"action":"promo"};edit(chat_id,message_id,text(lang,"promo_prompt"),cancel_keyboard(lang));ack();return
    if data=="support":PENDING[user_id]={"action":"support"};edit(chat_id,message_id,text(lang,"support_prompt"),cancel_keyboard(lang));ack();return
    if data=="referral":edit(chat_id,message_id,text(lang,"referral",days=REF_DAYS,percent=REF_PERCENT,count=int(user.get("referral_count") or 0),earned=float(user.get("referral_earned") or 0)),referral_keyboard(lang,referral_url(user,BOT_USERNAME)));ack();return
    if data=="servers":
        if not database.is_active(user):ack(text(lang,"active_required"),True);return
        rows=get_servers(db);listing="\n".join(server_flag(row[1])+" <b>"+html.escape(row[1])+"</b>" for row in rows) or text(lang,"no_servers")
        edit(chat_id,message_id,text(lang,"servers",servers=listing),servers_keyboard(lang,subscription_url(user)));ack();return

    # Every callback below this point is administrative and cannot shadow admin:home.
    if data.startswith(("admin:","admin-grant:","order:","topup:paid:","topup:reject:","ticket:")) and not require_admin(query["id"],user_id):return
    if data=="admin:revenue":edit(chat_id,message_id,text(lang,"revenue",**revenue_stats(db)),admin_keyboard(lang));ack();return
    if data in ("admin:users","admin:active"):
        rows=db.run(f"select {database.USER_COLUMNS} from users order by created_at desc limit 30") if data=="admin:users" else db.run(f"select {database.USER_COLUMNS} from users where subscription_expires>now() order by subscription_expires limit 40")
        rendered=[]
        for row in rows:
            item=database.row_to_user(row);rendered.append(f"<code>{item['telegram_id']}</code> · {html.escape(display_name(item))} · {plan_name(item)}")
        key="users" if data=="admin:users" else "active_users";edit(chat_id,message_id,text(lang,key,rows="\n".join(rendered) or "—"),admin_keyboard(lang));ack();return
    if data in ("admin:find","admin:grant","admin:trial","admin:revoke","admin:ban","admin:unban","admin:devices"):
        PENDING[user_id]={"action":data.split(":",1)[1]};edit(chat_id,message_id,text(lang,"admin_user_id"),cancel_keyboard(lang,"admin:home"));ack();return
    if data=="admin:balance":PENDING[user_id]={"action":"admin_balance"};edit(chat_id,message_id,text(lang,"admin_balance"),cancel_keyboard(lang,"admin:home"));ack();return
    if data=="admin:promo":PENDING[user_id]={"action":"admin_promo"};edit(chat_id,message_id,text(lang,"admin_promo"),cancel_keyboard(lang,"admin:home"));ack();return
    if data=="admin:broadcast":PENDING[user_id]={"action":"broadcast"};edit(chat_id,message_id,text(lang,"admin_broadcast"),cancel_keyboard(lang,"admin:home"));ack();return
    if data=="admin:server_add":PENDING[user_id]={"action":"server_name"};edit(chat_id,message_id,text(lang,"admin_server_name"),cancel_keyboard(lang,"admin:home"));ack();return
    if data=="admin:servers":
        rows=get_servers(db);rendered="\n".join(f"#{row[0]} · {html.escape(row[1])}" for row in rows) or "—";edit(chat_id,message_id,"<b>Servers</b>\n\n"+rendered,admin_keyboard(lang));ack();return
    if data=="admin:server_delete":
        rows=get_servers(db);buttons=[[button(f"#{row[0]} · {row[1]}",f"admin:server_delete:{row[0]}")] for row in rows];buttons.append([button("❌","admin:home")]);edit(chat_id,message_id,"Delete server:",keyboard(*buttons));ack();return
    if data.startswith("admin:server_delete:"):
        server_id=int(data.rsplit(":",1)[1]);db.run("delete from servers where id=:id",id=server_id);edit(chat_id,message_id,text(lang,"admin_server_deleted"),admin_keyboard(lang));ack("OK");return
    if data=="admin:tickets":
        rows=db.run("select id,telegram_id,subject from tickets where status='open' order by updated_at desc limit 20")
        rendered="\n".join(f"#{row[0]} · <code>{row[1]}</code> · {html.escape(row[2][:35])}" for row in rows) or "—";buttons=[[button(f"#{row[0]} reply",f"ticket:reply:{row[0]}")] for row in rows];buttons.append([button("⬅️","admin:home")]);edit(chat_id,message_id,"<b>Tickets</b>\n\n"+rendered,keyboard(*buttons));ack();return
    if data.startswith("ticket:reply:"):
        ticket_id=int(data.rsplit(":",1)[1]);PENDING[user_id]={"action":"ticket_reply","ticket_id":ticket_id};edit(chat_id,message_id,text(lang,"ticket_reply_prompt",ticket_id=ticket_id),cancel_keyboard(lang,"admin:home"));ack();return
    if data.startswith("ticket:close:"):
        ticket_id=int(data.rsplit(":",1)[1]);db.run("update tickets set status='closed',updated_at=now() where id=:id",id=ticket_id);edit(chat_id,message_id,text(lang,"ticket_closed",ticket_id=ticket_id),admin_keyboard(lang));ack("OK");return
    if data.startswith("admin-grant:"):
        _,target,days=data.split(":");target=int(target);days=int(days);database.extend_subscription(db,target,days);edit(chat_id,message_id,text(lang,"admin_granted",days=days,user_id=target),admin_keyboard(lang));ack("OK");return
    if data.startswith("order:paid:"):
        parts=data.split(":");target=int(parts[2]);days=int(parts[3]);price=float(parts[4]) if len(parts)>4 else calculate_price(days);database.extend_subscription(db,target,days);db.run("update users set promo_percent=0 where telegram_id=:id",id=target);database.record_payment(db,target,"premium",price,days,"admin")
        edit(chat_id,message_id,text(lang,"order_paid_admin",user_id=target,days=days,price=price),keyboard())
        try:target_user=database.get_user(db,target);send(target,text(language(target_user),"order_paid_user",days=days),home_keyboard(target_user,True,subscription_url(target_user),referral_url(target_user,BOT_USERNAME)))
        except Exception:pass
        ack("OK");return
    if data.startswith("order:reject:"):
        _,_,target,days=data.split(":");target=int(target);days=int(days);edit(chat_id,message_id,text(lang,"order_rejected_admin",user_id=target),keyboard())
        try:target_user=database.get_user(db,target);send(target,text(language(target_user),"order_rejected_user",days=days))
        except Exception:pass
        ack("OK");return
    if data.startswith("topup:paid:"):
        _,_,target,amount=data.split(":");target=int(target);amount=float(amount);target_user=database.add_balance(db,target,amount);database.record_payment(db,target,"topup",amount,0,"admin");edit(chat_id,message_id,f"✅ <code>{target}</code> +{amount:.0f} ₽",keyboard())
        try:send(target,text(language(target_user),"topup_paid",amount=amount))
        except Exception:pass
        ack("OK");return
    if data.startswith("topup:reject:"):
        _,_,target,amount=data.split(":");edit(chat_id,message_id,f"❌ Top-up rejected · <code>{target}</code>",keyboard());ack("OK");return
    ack()

def message(db,event):
    user_id=event["from"]["id"];chat_id=event["chat"]["id"];body=(event.get("text") or "").strip();username,full_name=user_meta(event["from"]);user=database.ensure_user(db,user_id,username,full_name);lang=language(user)
    if body.startswith("/"):
        command=body.split()[0].split("@")[0].lower();argument=body[len(body.split()[0]):].strip()
        if command=="/start":clear_pending(user_id);start(db,event,argument);return
        if command in ("/menu","/home"):clear_pending(user_id);send_home(db,chat_id,user);return
        if command=="/admin":
            if not is_admin(user_id):send(chat_id,"Admin only");return
            clear_pending(user_id);send_admin(db,chat_id,lang);return
    if user.get("banned") and not is_admin(user_id):send(chat_id,text(lang,"banned",reason=html.escape(user.get("ban_reason") or "—")));return
    pending=PENDING.get(user_id)
    if not pending:return
    action=pending["action"]
    if action=="custom_days":
        if not body.isdigit() or not CUSTOM_MIN_DAYS<=int(body)<=CUSTOM_MAX_DAYS:send(chat_id,text(lang,"custom_days_error",minimum=CUSTOM_MIN_DAYS,maximum=CUSTOM_MAX_DAYS),cancel_keyboard(lang));return
        days=int(body);clear_pending(user_id);price,_,discount=discounted_price(user,days);discount_label=f"\nСкидка: <b>−{discount:.0f}%</b>" if discount else "";send(chat_id,text(lang,"checkout",days=days,price=price,discount=discount_label),checkout_keyboard(lang,days));return
    if action=="promo":
        clear_pending(user_id);code=body.upper();rows=db.run("select kind,value,max_uses,used_count,active from promo_codes where code=:code",code=code)
        if not rows or not rows[0][4] or int(rows[0][3])>=int(rows[0][2]):send(chat_id,text(lang,"promo_invalid"),home_keyboard(user,database.is_active(user),subscription_url(user),referral_url(user,BOT_USERNAME)));return
        if db.run("select 1 from promo_redemptions where code=:code and telegram_id=:id",code=code,id=user_id):send(chat_id,text(lang,"promo_used"),home_keyboard(user,database.is_active(user),subscription_url(user),referral_url(user,BOT_USERNAME)));return
        kind,value=rows[0][0],float(rows[0][1])
        if kind=="days":user=database.extend_subscription(db,user_id,int(value));result=text(lang,"promo_days",value=int(value))
        elif kind=="balance":user=database.add_balance(db,user_id,value);result=text(lang,"promo_balance",value=value)
        elif kind=="percent":db.run("update users set promo_percent=:value where telegram_id=:id",value=value,id=user_id);user=database.get_user(db,user_id);result=text(lang,"promo_percent",value=value)
        else:send(chat_id,text(lang,"promo_invalid"));return
        db.run("insert into promo_redemptions(code,telegram_id) values(:code,:id)",code=code,id=user_id);db.run("update promo_codes set used_count=used_count+1 where code=:code",code=code);send(chat_id,result+"\n\n"+home_message(user),home_keyboard(user,database.is_active(user),subscription_url(user),referral_url(user,BOT_USERNAME)));return
    if action=="support":
        clear_pending(user_id);ticket_id=int(db.run("insert into tickets(telegram_id,subject) values(:id,:subject) returning id",id=user_id,subject=body[:80])[0][0]);db.run("insert into ticket_messages(ticket_id,sender,body) values(:ticket,'user',:body)",ticket=ticket_id,body=body);send(chat_id,text(lang,"support_created",ticket_id=ticket_id),home_keyboard(user,database.is_active(user),subscription_url(user),referral_url(user,BOT_USERNAME)))
        try:send(ADMIN_ID,text("ru","support_admin",ticket_id=ticket_id,user_id=user_id,name=html.escape(display_name(user)),body=html.escape(body)),ticket_keyboard(ticket_id))
        except Exception:pass
        return
    if not is_admin(user_id):return
    if action in ("find","grant","trial","revoke","ban","unban","devices"):
        if not body.isdigit():send(chat_id,text(lang,"admin_user_id"),cancel_keyboard(lang,"admin:home"));return
        target=int(body);database.ensure_user(db,target)
        if action=="find":clear_pending(user_id);target_user=database.get_user(db,target);send(chat_id,home_message(target_user),admin_keyboard(lang));return
        if action=="grant":PENDING[user_id]={"action":"noop"};send(chat_id,text(lang,"admin_days"),days_keyboard(f"admin-grant:{target}",lang));return
        if action=="trial":clear_pending(user_id);expires=datetime.now(timezone.utc)+timedelta(days=7);db.run("update users set status='trial',trial_used=true,subscription_expires=:expires where telegram_id=:id",expires=expires,id=target);send(chat_id,text(lang,"admin_trial",user_id=target),admin_keyboard(lang));return
        if action=="revoke":clear_pending(user_id);db.run("update users set status='free',subscription_expires=null where telegram_id=:id",id=target);send(chat_id,text(lang,"admin_revoked",user_id=target),admin_keyboard(lang));return
        if action=="ban":PENDING[user_id]={"action":"ban_reason","target":target};send(chat_id,text(lang,"admin_ban_reason"),cancel_keyboard(lang,"admin:home"));return
        if action=="unban":clear_pending(user_id);db.run("update users set banned=false,ban_reason=null where telegram_id=:id",id=target);send(chat_id,text(lang,"admin_unbanned",user_id=target),admin_keyboard(lang));return
        if action=="devices":clear_pending(user_id);db.run("update devices set blocked=true where telegram_id=:id",id=target);send(chat_id,text(lang,"admin_devices_reset",user_id=target),admin_keyboard(lang));return
    if action=="ban_reason":target=int(pending["target"]);clear_pending(user_id);db.run("update users set banned=true,ban_reason=:reason where telegram_id=:id",reason=body,id=target);send(chat_id,text(lang,"admin_banned",user_id=target),admin_keyboard(lang));return
    if action=="admin_balance":
        parts=body.split()
        if len(parts)!=2 or not parts[0].isdigit():send(chat_id,text(lang,"admin_balance"),cancel_keyboard(lang,"admin:home"));return
        try:amount=float(parts[1].replace(",","."))
        except ValueError:send(chat_id,text(lang,"admin_balance"),cancel_keyboard(lang,"admin:home"));return
        target=int(parts[0]);database.ensure_user(db,target);database.add_balance(db,target,amount);clear_pending(user_id);send(chat_id,text(lang,"admin_balance_ok",user_id=target,amount=amount),admin_keyboard(lang));return
    if action=="admin_promo":
        parts=body.split()
        if len(parts)<3 or parts[1] not in ("days","balance","percent"):send(chat_id,text(lang,"admin_promo"),cancel_keyboard(lang,"admin:home"));return
        try:value=float(parts[2].replace(",","."));maximum=int(parts[3]) if len(parts)>3 else 100
        except ValueError:send(chat_id,text(lang,"admin_promo"),cancel_keyboard(lang,"admin:home"));return
        code=parts[0].upper();db.run("insert into promo_codes(code,kind,value,max_uses) values(:code,:kind,:value,:maximum) on conflict(code) do update set kind=:kind,value=:value,max_uses=:maximum,active=true",code=code,kind=parts[1],value=value,maximum=maximum);clear_pending(user_id);send(chat_id,text(lang,"admin_promo_ok",code=code),admin_keyboard(lang));return
    if action=="broadcast":
        clear_pending(user_id);ok=failed=0
        for row in db.run("select telegram_id from users"):
            try:send(row[0],"📣 <b>FluxVPN</b>\n\n"+html.escape(body));ok+=1;time.sleep(.03)
            except Exception:failed+=1
        send(chat_id,text(lang,"admin_broadcast_ok",ok=ok,failed=failed),admin_keyboard(lang));return
    if action=="server_name":PENDING[user_id]={"action":"server_config","name":body};send(chat_id,text(lang,"admin_server_config"),cancel_keyboard(lang,"admin:home"));return
    if action=="server_config":server_id=int(db.run("insert into servers(name,config) values(:name,:config) returning id",name=pending["name"],config=body)[0][0]);clear_pending(user_id);send(chat_id,text(lang,"admin_server_added",server_id=server_id),admin_keyboard(lang));return
    if action=="ticket_reply":
        ticket_id=int(pending["ticket_id"]);clear_pending(user_id);rows=db.run("select telegram_id from tickets where id=:id",id=ticket_id)
        if not rows:send(chat_id,text(lang,"not_found"),admin_keyboard(lang));return
        target=int(rows[0][0]);db.run("insert into ticket_messages(ticket_id,sender,body) values(:ticket,'admin',:body)",ticket=ticket_id,body=body);db.run("update tickets set updated_at=now() where id=:id",id=ticket_id);send(chat_id,"✅ Reply sent",admin_keyboard(lang))
        try:target_user=database.get_user(db,target);send(target,text(language(target_user),"support_reply",ticket_id=ticket_id,body=html.escape(body)))
        except Exception:pass

def process(db,update):
    if update.get("callback_query"):callback(db,update["callback_query"]);return
    event=update.get("message") or update.get("edited_message")
    if event and event.get("text") is not None:message(db,event)
