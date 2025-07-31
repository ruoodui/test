import os
import io
import csv
import json
import re
import pandas as pd
from thefuzz import process

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    InputFile
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes
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
    df = df.dropna(subset=["الاسم (name)", "السعر (price)", "الماركه ( Brand )"])
    phone_map = {}
    brand_set = set()
    for _, row in df.iterrows():
        name = str(row["الاسم (name)"]).strip()
        brand = str(row["الماركه ( Brand )"]).strip()
        brand_set.add(brand)
        phone_map.setdefault(name, []).append({
            "price": str(row.get("السعر (price)", "")).strip(),
            "store": str(row.get("المتجر", "—")).strip(),
            "location": str(row.get("العنوان", "—")).strip(),
            "brand": brand
        })
    return phone_map, sorted(brand_set)

price_data, brand_list = load_excel_prices()

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

phone_urls = load_phone_urls()

def fuzzy_get_url(name):
    if name in phone_urls:
        return phone_urls[name]
    matches = process.extract(name, phone_urls.keys(), limit=1)
    if matches and matches[0][1] >= 80:
        return phone_urls[matches[0][0]]
    return "https://t.me/mitech808"

# ======= الرسائل =======
WELCOME_MSG = (
    "👋 مرحبًا بك في بوت أسعار الموبايلات!\n\n"
    "لإضافة متجرك للبوت، يرجى مراسلتنا عبر رقم الواتساب التالي:\n"
    "07828816508\n\n"
    "اختر طريقة البحث المناسبة لك من الأزرار أدناه:"
)

BACK_TO_MENU = "back_to_menu"

def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("🔤 البحث عن طريق الاسم", callback_data="search_by_name")],
        [InlineKeyboardButton("🏷️ البحث عن طريق الماركة", callback_data="search_by_brand")],
        [InlineKeyboardButton("🏬 البحث عن طريق المتجر", callback_data="search_by_store")],
        [InlineKeyboardButton("💰 البحث عن طريق السعر", callback_data="search_by_price")],
    ]
    return InlineKeyboardMarkup(keyboard)

def back_to_menu_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع إلى القائمة الرئيسية", callback_data=BACK_TO_MENU)]])

# ======= التحقق من الاشتراك =======
async def check_user_subscription(user_id, context):
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in ["member", "creator", "administrator"]
    except:
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

# ======= نتائج البحث بالسعر (محدث) =======
async def handle_search_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await check_user_subscription(user_id, context):
        return await send_subscription_required(update)
    store_user(update.effective_user)

    if 'search_mode' not in context.user_data:
        await update.message.reply_text("⚠️ يرجى اختيار طريقة البحث أولاً من القائمة.", reply_markup=main_menu_keyboard())
        return

    mode = context.user_data['search_mode']
    text = update.message.text.strip()
    results = []

    if mode == "price":
        try:
            target = int(''.join(filter(str.isdigit, text)))
            margin = 0.10
            min_price = int(target * (1 - margin))
            max_price = int(target * (1 + margin))
            for name, specs in price_data.items():
                for spec in specs:
                    raw_price = str(spec.get('price', '')).strip()
                    clean_price = re.sub(r"[^\d]", "", raw_price)
                    if not clean_price.isdigit():
                        continue
                    price = int(clean_price)
                    if min_price <= price <= max_price:
                        results.append(name)
                        break
        except ValueError:
            await update.message.reply_text("⚠️ يرجى إدخال رقم صالح للبحث بالسعر.", reply_markup=back_to_menu_keyboard())
            return

    # باقي أوضاع البحث مثل "name", "store_name" تضاف هنا كما كانت

    results = list(dict.fromkeys(results))

    if not results:
        await update.message.reply_text("❌ لم أجد نتائج مطابقة.\n🔙 يمكنك العودة للقائمة الرئيسية.", reply_markup=back_to_menu_keyboard())
        return

    count = 0
    for name in results[:10]:
        for spec in price_data[name]:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📎 المواصفات", url=fuzzy_get_url(name))]
            ])
            msg = (
                f"📱 {name}\n"
                f"💰 السعر: {spec['price']}\n"
                f"🏬 المتجر: {spec['store']}\n"
                f"📍 العنوان: {spec['location']}\n"
            )
            await update.message.reply_text(msg, reply_markup=keyboard)
            count += 1
            if count >= 10:
                break
        if count >= 10:
            break

    await update.message.reply_text("🔙 يمكنك العودة للقائمة الرئيسية.", reply_markup=back_to_menu_keyboard())

# ======= تسجيل المعالجات =======
def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search_text))
    print("Bot started...")
    application.run_polling()

if __name__ == "__main__":
    main()
