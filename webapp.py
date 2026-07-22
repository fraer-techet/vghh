import hashlib
import html
import json
import threading
import urllib.parse
from datetime import timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import database
from config import BRAND, PORT, PREMIUM_DEVICE_LIMIT, TRIAL_DEVICE_LIMIT
from services import branded_config, get_servers, subscription_url


def browser_agent(agent):
    value=(agent or "").lower()
    clients=("happ","hiddify","v2ray","clash","sing-box","nekobox","shadowrocket","streisand","okhttp")
    return not any(item in value for item in clients) and any(item in value for item in ("mozilla","chrome","safari","firefox","edge"))
def device_hash(agent,ip):return hashlib.sha256(((agent or "")+"|"+(ip or "")).encode()).hexdigest()[:32]
def device_name(agent):
    value=(agent or "").lower()
    for marker,name in (("happ","Happ"),("hiddify","Hiddify"),("v2ray","v2rayNG"),("clash","Clash"),("shadowrocket","Shadowrocket"),("streisand","Streisand"),("nekobox","NekoBox"),("sing-box","sing-box")):
        if marker in value:return name
    return ((agent or "Device").split("/")[0].split(" ")[0] or "Device")[:40]
def device_limit(user):return TRIAL_DEVICE_LIMIT if user["status"]=="trial" else PREMIUM_DEVICE_LIMIT
def register_device(db,user,agent,ip):
    fingerprint=device_hash(agent,ip);rows=db.run("select id,blocked from devices where telegram_id=:user and device_hash=:fingerprint",user=user["telegram_id"],fingerprint=fingerprint)
    if rows:
        if rows[0][1]:return False,"removed"
        db.run("update devices set last_seen=now(),user_agent=:agent,last_ip=:ip,device_name=:name where id=:id",agent=agent[:300],ip=ip,name=device_name(agent),id=rows[0][0]);return True,"ok"
    count=int(db.run("select count(*) from devices where telegram_id=:user and blocked=false",user=user["telegram_id"])[0][0])
    if count>=device_limit(user):return False,"limit"
    db.run("insert into devices(telegram_id,device_hash,device_name,user_agent,last_ip) values(:user,:fingerprint,:name,:agent,:ip)",user=user["telegram_id"],fingerprint=fingerprint,name=device_name(agent),agent=agent[:300],ip=ip);return True,"ok"
def dummy(name):return "vless://00000000-0000-0000-0000-000000000000@127.0.0.1:1?encryption=none&security=none&type=tcp#"+urllib.parse.quote(name,safe="")+"\n"
def expiry(user):
    value=user.get("subscription_expires")
    if not value:return 0
    if value.tzinfo is None:value=value.replace(tzinfo=timezone.utc)
    return int(value.timestamp())
def subscription(handler,body,user=None):
    data=body.encode();expiration=expiry(user) if user else 0
    handler.send_response(200)
    headers={"Content-Type":"text/plain; charset=utf-8","Cache-Control":"no-store","Profile-Title":"base64:Rmx1eFZQTg","Profile-Update-Interval":"1","Subscription-Userinfo":f"upload=0; download=0; total=0; expire={expiration}","Content-Length":str(len(data))}
    for key,value in headers.items():handler.send_header(key,value)
    handler.end_headers();handler.wfile.write(data)
def denied():return """<!doctype html><html lang=ru><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>FluxVPN</title><style>body{margin:0;background:#080808;color:#eee;font-family:system-ui;min-height:100vh;display:grid;place-items:center}.c{padding:32px;border:1px solid #242424;border-radius:24px;background:#101010;text-align:center;max-width:360px}p{color:#888}</style><div class=c><h2>FluxVPN</h2><p>Подписка неактивна. Открой бота и продли доступ.</p></div>"""
def cabinet(user,servers,devices):
    link=subscription_url(user);limit=device_limit(user);token=html.escape(user["sub_token"]);days=database.days_left(user)
    server_rows="".join(f"<div class=row><span>● &nbsp;{html.escape(row[1])}</span><b>online</b></div>" for row in servers) or "<div class=empty>Нет серверов</div>"
    device_rows="".join(f"<div class=row><span>{html.escape(row[1])}</span><a href='/sub/{token}/device/{row[0]}/delete'>Удалить</a></div>" for row in devices) or "<div class=empty>Нет устройств</div>"
    return f"""<!doctype html><html lang=ru><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><meta name=robots content=noindex,nofollow><title>FluxVPN</title><style>*{{box-sizing:border-box}}body{{margin:0;background:#080808;color:#f5f5f5;font:14px system-ui}}.wrap{{max-width:680px;margin:auto;padding:24px 16px 60px}}header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px}}.logo{{font-weight:900;letter-spacing:.12em}}.badge,.tab{{border:1px solid #292929;border-radius:999px;padding:8px 12px;background:#111;color:#eee}}.hero,.card{{border:1px solid #202020;background:linear-gradient(180deg,#121212,#0c0c0c);border-radius:22px;padding:20px;margin-bottom:12px}}h1{{margin:0 0 8px;font-size:28px}}p,.empty{{color:#888}}.stats{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:16px}}.stat{{background:#090909;border:1px solid #1c1c1c;border-radius:14px;padding:12px}}.stat small{{color:#777;display:block}}.tabs{{display:flex;gap:8px;margin:12px 0}}.tab.active{{background:#eee;color:#111}}section{{display:none}}section.active{{display:block}}.row{{display:flex;justify-content:space-between;padding:13px 0;border-bottom:1px solid #1b1b1b}}.row:last-child{{border:0}}.row b{{font-size:11px}}a{{color:#111;background:#eee;border-radius:999px;padding:6px 10px;text-decoration:none;font-weight:700}}button.action{{width:100%;border:0;border-radius:14px;padding:14px;font-weight:800}}#toast{{text-align:center;color:#888;padding:8px}}@media(max-width:500px){{.stats{{grid-template-columns:1fr}}}}</style><div class=wrap><header><div class=logo>FLUXVPN</div><div class=badge>ACTIVE</div></header><div class=hero><h1>Личный кабинет</h1><p>Ключ скрыт. Управляй подключениями без открытых конфигов.</p><div class=stats><div class=stat><small>Осталось</small><b>{days} дней</b></div><div class=stat><small>Серверов</small><b>{len(servers)}</b></div><div class=stat><small>Устройств</small><b>{len(devices)}/{limit}</b></div></div></div><div class=tabs><button class='tab active' data-id=connect>Подключение</button><button class=tab data-id=locations>Локации</button><button class=tab data-id=devices>Устройства</button></div><section id=connect class='card active'><button class=action id=copy>Скопировать ключ</button><div id=toast></div></section><section id=locations class=card>{server_rows}</section><section id=devices class=card><p>После удаления обнови подписку в VPN-клиенте.</p>{device_rows}</section></div><script>const link={json.dumps(link)};document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{{document.querySelectorAll('.tab,section').forEach(x=>x.classList.remove('active'));b.classList.add('active');document.getElementById(b.dataset.id).classList.add('active')}});document.getElementById('copy').onclick=async()=>{{try{{await navigator.clipboard.writeText(link);document.getElementById('toast').textContent='Скопировано'}}catch(e){{document.getElementById('toast').textContent='Не удалось скопировать'}}}}</script>"""

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send_body(self,code,content_type,body):
        data=body.encode() if isinstance(body,str) else body;self.send_response(code);self.send_header("Content-Type",content_type);self.send_header("Cache-Control","no-store");self.send_header("Content-Length",str(len(data)));self.end_headers();self.wfile.write(data)
    def do_GET(self):
        connection=None
        try:
            path=urllib.parse.urlparse(self.path).path;parts=[item for item in path.split("/") if item]
            if path in ("/","/health"):self.send_body(200,"text/plain; charset=utf-8","FluxVPN healthy");return
            if len(parts)<2 or parts[0]!="sub":self.send_body(404,"text/plain","not found");return
            token=parts[1];connection=database.connect();database.migrate(connection);rows=connection.run(f"select {database.USER_COLUMNS} from users where sub_token=:token",token=token)
            if not rows:self.send_body(403,"text/html; charset=utf-8",denied());return
            user=database.row_to_user(rows[0])
            if len(parts)==5 and parts[2]=="device" and parts[4]=="delete" and parts[3].isdigit():
                connection.run("update devices set blocked=true where id=:id and telegram_id=:user",id=int(parts[3]),user=user["telegram_id"]);self.send_response(302);self.send_header("Location",f"/sub/{token}");self.end_headers();return
            agent=self.headers.get("User-Agent") or "";browser=browser_agent(agent);active=database.is_active(user) and not user.get("banned")
            if browser:
                if not active:self.send_body(200,"text/html; charset=utf-8",denied());return
                servers=get_servers(connection);devices=connection.run("select id,device_name from devices where telegram_id=:user and blocked=false order by last_seen desc",user=user["telegram_id"]);self.send_body(200,"text/html; charset=utf-8",cabinet(user,servers,devices));return
            if not active:subscription(self,dummy("FluxVPN | Подписка истекла"),user);return
            forwarded=self.headers.get("X-Forwarded-For") or "";ip=(forwarded.split(",")[0].strip() if forwarded else self.client_address[0])[:64];allowed,reason=register_device(connection,user,agent,ip)
            if not allowed:subscription(self,dummy("FluxVPN | Устройство удалено" if reason=="removed" else "FluxVPN | Лимит устройств"),user);return
            lines=[branded_config(row[2],row[1]) for row in get_servers(connection)];subscription(self,"\n".join(item for item in lines if item)+("\n" if lines else ""),user)
        except Exception as error:
            print("HTTP",repr(error),flush=True)
            try:self.send_body(500,"text/plain","server error")
            except Exception:pass
        finally:
            if connection:
                try:connection.close()
                except Exception:pass

def start():
    server=ThreadingHTTPServer(("0.0.0.0",PORT),Handler);threading.Thread(target=server.serve_forever,daemon=True).start();return server
