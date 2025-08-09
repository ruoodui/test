import os
import io
import csv
import json
import pandas as pd
from thefuzz import process
import asyncio

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    InputFile
)
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

# تحقق من وجود الملفات
if not os.path.exists(PRICES_PATH):
    print(f"❌ ملف الأسعار غير موجود: {PRICES_PATH}")
if not os.path.exists(URLS_PATH):
    print(f"❌ ملف الروابط غير موجود: {URLS_PATH}")

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
    if not os.path.exists(path):
        return {}
    df = pd.read_excel(path)
    df = df.dropna(subset=["الاسم (name)", "السعر (price)"])
    phone_map = {}
    for _, row in df.iterrows():
        name = str(row["الاسم (name)"]).strip()
        phone_map.setdefault(name, []).append({
            "ram_memory": str(row.get("الرام والذاكره", "—")).strip(),
            "price": str(row.get("السعر (price)", "")).strip(),
            "store": str(row.get("المتجر", "—")).strip(),
            "location": str(row.get("العنوان", "—")).strip(),
        })
    return phone_map

# ======= تحميل روابط المواصفات =======
def load_phone_urls(filepath=URLS_PATH):
    if not os.path.exists(filepath):
        return {}
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

# ======= الرسائل الثابتة =======
WELCOME_MSG = (
    "👋 مرحبًا بك في بوت أسعار الموبايلات!\n\n"
    "لإضافة متجرك للبوت، يرجى مراسلتنا عبر رقم الواتساب التالي:\n"
    "07828816508\n\n"
    "اختر طريقة البحث المناسبة لك من الأزرار أدناه:"
)

BACK_TO_MENU = "back_to_menu"

# ======= أزرار القائمة الرئيسية =======
def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("🔤 البحث عن طريق الاسم", callback_data="search_by_name")],
        [InlineKeyboardButton("🏬 البحث عن طريق المتجر", callback_data="search_by_store")],
        [InlineKeyboardButton("💰 البحث عن طريق السعر", callback_data="search_by_price")],
    ]
    return InlineKeyboardMarkup(keyboard)

def back_to_menu_keyboard():
    keyboard = [[InlineKeyboardButton("🔙 رجوع إلى القائمة الرئيسية", callback_data=BACK_TO_MENU)]]
    return InlineKeyboardMarkup(keyboard)

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

# ======= /start =======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await check_user_subscription(user_id, context):
        return await send_subscription_required(update)
    store_user(update.effective_user)
    await update.message.reply_text(WELCOME_MSG, reply_markup=main_menu_keyboard())

# ======= البحث =======
async def handle_search_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'search_mode' not in context.user_data:
        await update.message.reply_text("⚠️ يرجى اختيار طريقة البحث أولاً من القائمة.", reply_markup=main_menu_keyboard())
        return

    mode = context.user_data['search_mode']
    text = update.message.text.strip()
    results = []

    if mode == "name":
        matches = process.extract(text, price_data.keys(), limit=10)
        results = [name for name, score in matches if score >= 95]

    elif mode == "store":
        all_stores = {entry["store"] for devices in price_data.values() for entry in devices}
        matches = process.extract(text, all_stores, limit=10)
        matched_stores = [store for store, score in matches if score >= 95]
        for store in matched_stores:
            for name, devices in price_data.items():
                if any(store == d["store"] for d in devices):
                    results.append(name)

    elif mode == "price":
        try:
            target_price = int(text)
            for name, devices in price_data.items():
                for device in devices:
                    try:
                        price = int(device["price"])
                        if abs(price - target_price) <= target_price * 0.1:
                            results.append(name)
                            break
                    except ValueError:
                        continue
        except ValueError:
            await update.message.reply_text("⚠️ يرجى إدخال سعر صالح.")
            return

    results = list(dict.fromkeys(results))  # إزالة التكرار

    if not results:
        await update.message.reply_text("❌ لم أجد نتائج مطابقة.", reply_markup=back_to_menu_keyboard())
        return

    buttons = [[InlineKeyboardButton(f"📱 {name}", callback_data=f"device_{name}")] for name in results[:10]]
    buttons.append([InlineKeyboardButton("🔙 رجوع إلى القائمة الرئيسية", callback_data=BACK_TO_MENU)])
    await update.message.reply_text(f"🔍 نتائج البحث عن '{text}':", reply_markup=InlineKeyboardMarkup(buttons))

# ======= التشغيل =======
def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search_text))
    print("🤖 البوت يعمل الآن...")
    application.run_polling()

if __name__ == "__main__":
    main()
