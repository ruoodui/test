import os
import pandas as pd
import json
from thefuzz import process

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes
)

# ======= إعدادات =======
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PRICES_PATH = os.path.join(BASE_DIR, "prices.xlsx")
URLS_PATH = os.path.join(BASE_DIR, "phones_urls.json")
USERS_FILE = os.path.join(BASE_DIR, "users.json")
TOKEN = os.getenv("TOKEN")
CHANNEL_USERNAME = "@mitech808"
ADMIN_IDS = [193646746]

# ======= دوال إدارة المستخدمين =======
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)

def store_user(user):
    users = load_users()
    user_id = str(user.id)
    if user_id not in users:
        users[user_id] = {
            "name": user.full_name,
            "username": user.username,
            "id": user.id
        }
        save_users(users)

# ======= تحميل بيانات الأسعار =======
def load_excel_prices(path=PRICES_PATH):
    df = pd.read_excel(path)
    df = df.dropna(subset=["الاسم (name)", "السعر (price)"])
    phone_map = {}
    for _, row in df.iterrows():
        name = str(row["الاسم (name)"]).strip()
        price = str(row["السعر (price)"]).strip()
        brand = str(row.get("الماركه ( Brand )", "")).strip()
        store = str(row.get("المتجر", "")).strip()
        address = str(row.get("العنوان", "")).strip()
        phone_map.setdefault(name, []).append({
            "price": price,
            "brand": brand,
            "store": store,
            "address": address
        })
    return phone_map

# ======= تحميل روابط المواصفات =======
def load_phone_urls(filepath=URLS_PATH):
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)
    url_map = {}
    for brand_devices in data.values():
        for phone in brand_devices:
            name = phone.get("name")
            url = phone.get("url", "🔗 غير متوفر")
            if name:
                url_map[name.strip()] = url
    return url_map

# ======= البيانات =======
price_data = load_excel_prices()
phone_urls = load_phone_urls()

# ======= مطابقة غامضة للروابط =======
def fuzzy_get_url(name):
    if name in phone_urls:
        return phone_urls[name]
    matches = process.extract(name, phone_urls.keys(), limit=1)
    if matches and matches[0][1] >= 80:
        return phone_urls[matches[0][0]]
    return "https://t.me/mitech808"

# ======= رسالة ترحيب =======
WELCOME_MSG = (
    "👋 مرحبًا بك في بوت أسعار الموبايلات!\n\n"
    "📱 أرسل اسم الجهاز (مثال: Galaxy S25 Ultra)\n"
    "💰 أو أرسل السعر (مثال: 1300000) للبحث عن أجهزة في هذا النطاق.\n"
    "🔄 استخدم الأمر /compare لمقارنة جهازين."
)

# ======= التحقق من الاشتراك =======
async def check_user_subscription(user_id, context):
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in ["member", "creator", "administrator"]
    except Exception as e:
        print("⚠️ Subscription check failed:", e)
        return False

async def send_subscription_required(update: Update):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 انضم إلى قناتنا", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
        [InlineKeyboardButton("📸 تابعنا على إنستغرام", url="https://www.instagram.com/mitech808")],
        [InlineKeyboardButton("🔄 تحقق من الاشتراك", callback_data="check_subscription")]
    ])
    await update.message.reply_text(
        "🔒 يرجى الانضمام إلى قناتنا على تليغرام من أجل استخدام البوت 😍✅\n\n"
        f"📢 قناة التليغرام: {CHANNEL_USERNAME}\n"
        "📸 أيضًا يجب متابعة حساب الإنستغرام:\n"
        "https://www.instagram.com/mitech808\n\n"
        "✅ بعد الاشتراك، اضغط على /start للبدء الآن.",
        reply_markup=keyboard
    )

# ======= دالة البداية =======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await check_user_subscription(user_id, context):
        return await send_subscription_required(update)

    store_user(update.effective_user)
    await update.message.reply_text(WELCOME_MSG)

# ======= التعامل مع الضغط على زر المواصفات =======
async def show_specs_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    phone_name = query.data.replace("show_specs_", "", 1)
    specs_list = price_data.get(phone_name)

    if not specs_list:
        await query.edit_message_text("❌ لم أتمكن من العثور على مواصفات لهذا الجهاز.")
        return

    msg = f"📱 مواصفات {phone_name}:\n\n"
    for spec in specs_list:
        msg += f"💰 السعر: {spec['price']}\n"
        if spec['brand']:
            msg += f"🏷️ الماركة: {spec['brand']}\n"
        if spec['store']:
            msg += f"🏪 المتجر: {spec['store']}\n"
        if spec['address']:
            msg += f"📍 العنوان: {spec['address']}\n"
        msg += f"🔗 رابط المواصفات: {fuzzy_get_url(phone_name)}\n"
        msg += "----------------------\n"

    await query.edit_message_text(msg)

# ======= التعامل مع الرسائل العامة =======
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await check_user_subscription(user_id, context):
        return await send_subscription_required(update)

    store_user(update.effective_user)

    text = update.message.text.strip()

    if text.isdigit():
        target = int(text)
        margin = 0.10
        min_price = int(target * (1 - margin))
        max_price = int(target * (1 + margin))

        for name, specs in price_data.items():
            for spec in specs:
                try:
                    price = int(str(spec['price']).replace(',', '').replace('٬', ''))
                    if min_price <= price <= max_price:
                        msg = f"📱 {name}\n💰 {spec['price']}"
                        keyboard = InlineKeyboardMarkup([
                            [InlineKeyboardButton("📎 المواصفات", callback_data=f"show_specs_{name}")]
                        ])
                        await update.message.reply_text(msg, reply_markup=keyboard)
                except:
                    continue
        return

    matches = process.extract(text, price_data.keys(), limit=5)
    good_matches = [m for m in matches if m[1] >= 95]

    if not good_matches:
        suggestions = [m[0] for m in matches if m[1] >= 70]
