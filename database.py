import secrets
import urllib.parse
from datetime import datetime, timedelta, timezone
import pg8000.native
from config import DATABASE_URL, REF_DAYS, REF_PERCENT

USER_COLUMNS="""telegram_id,status,trial_used,subscription_expires,sub_token,referral_code,referred_by,coalesce(referral_count,0),username,full_name,coalesce(lang,'ru'),coalesce(balance,0),coalesce(banned,false),ban_reason,coalesce(promo_percent,0),coalesce(referral_earned,0),coalesce(notify_2d,false),coalesce(notify_1d,false),coalesce(notify_1h,false),coalesce(notify_exp,false)"""
SCHEMA_READY=False

def connect():
    parsed=urllib.parse.urlparse(DATABASE_URL)
    return pg8000.native.Connection(user=urllib.parse.unquote(parsed.username or ""),password=urllib.parse.unquote(parsed.password or ""),host=parsed.hostname,port=parsed.port or 5432,database=(parsed.path or "/neondb").lstrip("/"),ssl_context=True)

def migrate(db):
    global SCHEMA_READY
    if SCHEMA_READY:return
    db.run("create table if not exists users(telegram_id bigint primary key,status text not null default 'free',trial_used boolean not null default false,subscription_expires timestamptz,sub_token text not null unique,created_at timestamptz not null default now())")
    columns={row[0] for row in db.run("select column_name from information_schema.columns where table_name='users'")}
    additions={"referral_code":"text","referred_by":"bigint","referral_count":"integer not null default 0","username":"text","full_name":"text","lang":"text not null default 'ru'","balance":"double precision not null default 0","banned":"boolean not null default false","ban_reason":"text","promo_percent":"double precision not null default 0","referral_earned":"double precision not null default 0","notify_2d":"boolean not null default false","notify_1d":"boolean not null default false","notify_1h":"boolean not null default false","notify_exp":"boolean not null default false"}
    for name,definition in additions.items():
        if name not in columns: db.run(f'alter table users add column "{name}" {definition}')
    db.run("update users set referral_code=substr(md5(random()::text||clock_timestamp()::text),1,10) where referral_code is null")
    try: db.run("create unique index if not exists users_referral_code_uq on users(referral_code)")
    except Exception: pass
    db.run("create table if not exists servers(id bigserial primary key,name text not null,config text not null,enabled boolean not null default true,created_at timestamptz not null default now())")
    legacy=db.run("select to_regclass('public.server_pool')")
    if legacy and legacy[0][0] and int(db.run("select count(*) from servers")[0][0])==0:
        try:
            db.run("insert into servers(name,config) select coalesce(custom_name,'Server'),raw_config from server_pool where raw_config is not null")
        except Exception:
            pass
    db.run("create table if not exists devices(id bigserial primary key,telegram_id bigint not null,device_hash text not null,device_name text not null,user_agent text,last_ip text,blocked boolean not null default false,created_at timestamptz not null default now(),last_seen timestamptz not null default now(),unique(telegram_id,device_hash))")
    db.run("create table if not exists promo_codes(code text primary key,kind text not null,value double precision not null,max_uses integer not null default 100,used_count integer not null default 0,active boolean not null default true,created_at timestamptz not null default now())")
    db.run("create table if not exists promo_redemptions(code text not null,telegram_id bigint not null,created_at timestamptz not null default now(),primary key(code,telegram_id))")
    db.run("create table if not exists tickets(id bigserial primary key,telegram_id bigint not null,status text not null default 'open',subject text not null,created_at timestamptz not null default now(),updated_at timestamptz not null default now())")
    db.run("create table if not exists ticket_messages(id bigserial primary key,ticket_id bigint not null,sender text not null,body text not null,created_at timestamptz not null default now())")
    db.run("create table if not exists payments(id bigserial primary key,telegram_id bigint not null,kind text not null,amount double precision not null,days integer not null default 0,method text not null,external_id text,created_at timestamptz not null default now())")
    db.run("create table if not exists fulfilled_payments(external_id text primary key,created_at timestamptz not null default now())")
    SCHEMA_READY=True

def row_to_user(row):
    return dict(zip(["telegram_id","status","trial_used","subscription_expires","sub_token","referral_code","referred_by","referral_count","username","full_name","lang","balance","banned","ban_reason","promo_percent","referral_earned","notify_2d","notify_1d","notify_1h","notify_exp"],row))
def get_user(db,user_id):
    rows=db.run(f"select {USER_COLUMNS} from users where telegram_id=:id",id=int(user_id));return row_to_user(rows[0]) if rows else None
def ensure_user(db,user_id,username=None,full_name=None,referral_code=None):
    migrate(db);user=get_user(db,user_id)
    if user:
        db.run("update users set username=coalesce(:username,username),full_name=coalesce(:full_name,full_name) where telegram_id=:id",username=username,full_name=full_name,id=int(user_id));return get_user(db,user_id)
    inviter=None
    if referral_code:
        rows=db.run("select telegram_id from users where referral_code=:code",code=referral_code)
        if rows and int(rows[0][0])!=int(user_id):inviter=int(rows[0][0])
    db.run("insert into users(telegram_id,sub_token,referral_code,referred_by,username,full_name) values(:id,:token,:code,:inviter,:username,:full_name)",id=int(user_id),token=secrets.token_hex(20),code=secrets.token_hex(5),inviter=inviter,username=username,full_name=full_name)
    if inviter:
        db.run("update users set referral_count=referral_count+1 where telegram_id=:id",id=inviter);extend_subscription(db,inviter,REF_DAYS)
    return get_user(db,user_id)
def is_active(user):
    expires=user.get("subscription_expires")
    if user.get("status") not in ("trial","premium") or not expires:return False
    if expires.tzinfo is None:expires=expires.replace(tzinfo=timezone.utc)
    return expires>datetime.now(timezone.utc)
def days_left(user):
    if not is_active(user):return 0
    seconds=(user["subscription_expires"]-datetime.now(timezone.utc)).total_seconds();return max(1,int((seconds+86399)//86400))
def extend_subscription(db,user_id,days,status="premium"):
    user=get_user(db,user_id) or ensure_user(db,user_id);now=datetime.now(timezone.utc);base=now
    if is_active(user) and user["subscription_expires"]>now:base=user["subscription_expires"]
    db.run("update users set status=:status,subscription_expires=:expires,notify_2d=false,notify_1d=false,notify_1h=false,notify_exp=false where telegram_id=:id",status=status,expires=base+timedelta(days=int(days)),id=int(user_id));return get_user(db,user_id)
def add_balance(db,user_id,amount):
    db.run("update users set balance=balance+:amount where telegram_id=:id",amount=float(amount),id=int(user_id));return get_user(db,user_id)
def charge_balance(db,user_id,amount):
    rows=db.run("update users set balance=balance-:amount,promo_percent=0 where telegram_id=:id and balance>=:amount returning telegram_id",amount=float(amount),id=int(user_id));return bool(rows)
def record_payment(db,user_id,kind,amount,days,method,external_id=None):
    db.run("insert into payments(telegram_id,kind,amount,days,method,external_id) values(:id,:kind,:amount,:days,:method,:external)",id=int(user_id),kind=kind,amount=float(amount),days=int(days),method=method,external=external_id)
    if kind=="premium":
        user=get_user(db,user_id)
        if user and user.get("referred_by"):
            bonus=round(float(amount)*REF_PERCENT/100,2);db.run("update users set balance=balance+:bonus,referral_earned=referral_earned+:bonus where telegram_id=:id",bonus=bonus,id=int(user["referred_by"]))
def payment_once(db,external_id):
    rows=db.run("insert into fulfilled_payments(external_id) values(:id) on conflict do nothing returning external_id",id=str(external_id));return bool(rows)
