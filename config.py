import os

BRAND = "FluxVPN"
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "6049379160"))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "zrdws").lstrip("@")
CRYPTO_BOT_TOKEN = os.getenv("CRYPTO_BOT_TOKEN", "")
PUBLIC_URL = (os.getenv("PUBLIC_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").rstrip("/")
PORT = int(os.getenv("PORT", "10000"))
REF_DAYS = 5
REF_PERCENT = 10
PLAN_PRICES = {7: 50, 30: 200, 90: 400, 365: 800}
CUSTOM_MIN_DAYS = 3
CUSTOM_MAX_DAYS = 730
TRIAL_DEVICE_LIMIT = 2
PREMIUM_DEVICE_LIMIT = 4
TOPUP_AMOUNTS = (100, 200, 500, 1000)

def validate():
    missing=[]
    if not BOT_TOKEN: missing.append("BOT_TOKEN")
    if not DATABASE_URL: missing.append("DATABASE_URL")
    if missing: raise RuntimeError("Missing environment: " + ", ".join(missing))
