import json
import urllib.error
import urllib.request
from config import BOT_TOKEN

BASE = "https://api.telegram.org/bot" + BOT_TOKEN

def call(method, payload=None, timeout=60):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(BASE + "/" + method, data=data, headers=headers, method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Telegram {method}: HTTP {error.code}: {detail}")
    if not result.get("ok"):
        raise RuntimeError(f"Telegram {method}: {result}")
    return result["result"]

def send(chat_id, message, keyboard=None):
    payload={"chat_id":chat_id,"text":message,"parse_mode":"HTML","disable_web_page_preview":True}
    if keyboard is not None: payload["reply_markup"]=keyboard
    return call("sendMessage", payload)

def edit(chat_id, message_id, message, keyboard=None):
    payload={"chat_id":chat_id,"message_id":message_id,"text":message,"parse_mode":"HTML","disable_web_page_preview":True}
    if keyboard is not None: payload["reply_markup"]=keyboard
    try: return call("editMessageText", payload)
    except RuntimeError as error:
        if "message is not modified" in str(error): return None
        raise

def answer(query_id, message=None, alert=False):
    payload={"callback_query_id":query_id,"show_alert":alert}
    if message: payload["text"]=message[:200]
    return call("answerCallbackQuery",payload)
