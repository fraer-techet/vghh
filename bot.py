import os
import threading
import time
import traceback
from datetime import datetime, timezone

import database
import handlers
from config import ADMIN_ID, BRAND, validate
from telegram import call, send
import webapp


def report_error(label,error):
    detail=f"⚠️ <b>{BRAND} error</b>\n<code>{label}: {str(error)[:1200]}</code>"
    print(label,traceback.format_exc(),flush=True)
    try:send(ADMIN_ID,detail)
    except Exception:pass

def notification_loop():
    while True:
        connection=None
        try:
            connection=database.connect();database.migrate(connection);now=datetime.now(timezone.utc)
            for row in connection.run(f"select {database.USER_COLUMNS} from users where subscription_expires is not null and banned=false"):
                user=database.row_to_user(row);expires=user["subscription_expires"]
                if expires.tzinfo is None:expires=expires.replace(tzinfo=timezone.utc)
                left=(expires-now).total_seconds();language=user["lang"] if user["lang"] in ("ru","en") else "ru";column=key=None
                if left<=0 and not user["notify_exp"]:column,key="notify_exp","notify_expired"
                elif 0<left<=3600 and not user["notify_1h"]:column,key="notify_1h","notify_1h"
                elif 3600<left<=86400 and not user["notify_1d"]:column,key="notify_1d","notify_1d"
                elif 86400<left<=172800 and not user["notify_2d"]:column,key="notify_2d","notify_2d"
                if column:
                    from texts import text
                    try:send(user["telegram_id"],text(language,key));connection.run(f"update users set {column}=true where telegram_id=:id",id=user["telegram_id"])
                    except Exception:pass
        except Exception as error:report_error("notification_loop",error)
        finally:
            if connection:
                try:connection.close()
                except Exception:pass
        time.sleep(60)
def main():
    validate();webapp.start();threading.Thread(target=notification_loop,daemon=True).start()
    try:
        me=call("getMe");handlers.set_bot_username(me.get("username") or "")
    except Exception as error:report_error("getMe",error)
    connection=database.connect()
    try:database.migrate(connection)
    finally:connection.close()
    try:call("deleteWebhook",{"drop_pending_updates":False})
    except Exception as error:report_error("deleteWebhook",error)
    offset=0
    print(BRAND,"started",flush=True)
    while True:
        try:
            updates=call("getUpdates",{"timeout":50,"offset":offset,"allowed_updates":["message","callback_query"]},timeout=60)
            connection=database.connect()
            try:
                database.migrate(connection)
                for update in updates:
                    offset=update["update_id"]+1
                    try:handlers.process(connection,update)
                    except Exception as error:report_error("update "+str(update.get("update_id")),error)
            finally:connection.close()
        except Exception as error:
            report_error("polling",error);time.sleep(3)
if __name__=="__main__":main()
