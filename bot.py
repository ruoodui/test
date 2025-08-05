import os
import json
import pandas as pd
from thefuzz import process

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

# ======= إعدادات =======
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PRICES_PATH = os.path.join(BASE_DIR, "prices.xlsx")
URLS_PATH = os.path.join(BASE_DIR, "phones_urls.json")
USERS_FILE = os.path.join(BASE_DIR, "users.json")
TOKEN = os.getenv("TOKEN")  # أو استبدلها بسلسلة التوكن مباشرة
CHANNEL_USERNAME = "@mitech808"
ADMIN_IDS = [193646746]

# ======= الرسائل الثابتة =======
WELCOME_MSG = (
    "👋 مرحبًا بك في بوت أسعار الموبايلات!\n\n"
    "لإضافة متجرك للبوت، يرجى مراسلتنا عبر رقم الواتساب التالي:\n"
    "07828816508\n\n"
    "اختر طريقة البحث المناسبة لك من الأزرار أدناه:"
)

BACK_TO_MENU = "back_to_menu"

# ======= تحميل البيانات =======
df = pd.read_excel(PRICES_PATH)
df.columns = [col.strip() for col in df.columns]

with open(URLS_PATH, "r", encoding="utf-8") as f:
    raw_specs = json.load(f)

phone_specs = {}
for category in raw_specs.values():
    for item in category:
        phone_specs[item["name"].strip()] = item["url"]

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
    subscribed = await check_user_subscription(user_id, context)
    if not subscribed:
        await send_subscription_required(update)
        return

    store_user(update.effective_user)
    context.user_data.clear()
    keyboard = [
        [InlineKeyboardButton("🔍 البحث بالاسم", callback_data='search_name')],
        [InlineKeyboardButton("🏬 البحث بالمتجر", callback_data='search_store')],
        [InlineKeyboardButton("💰 البحث بالسعر", callback_data='search_price')]
    ]
    await update.message.reply_text(
        WELCOME_MSG,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ======= قائمة المتاجر =======
async def list_stores(update: Update, context: ContextTypes.DEFAULT_TYPE):
    unique_stores = df["المتجر"].dropna().unique()
    keyboard = [[InlineKeyboardButton(store, callback_data=f'store:{store}')] for store in unique_stores]
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=BACK_TO_MENU)])
    await update.callback_query.message.edit_text("اختر المتجر:", reply_markup=InlineKeyboardMarkup(keyboard))

# ======= استجابة الأزرار =======
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == 'search_name':
        await query.message.edit_text("أرسل اسم الجهاز:")
        context.user_data['mode'] = 'name'

    elif data == 'search_store':
        await list_stores(update, context)

    elif data == 'search_price':
        await query.message.edit_text("أرسل السعر المطلوب (بالأرقام فقط):")
        context.user_data['mode'] = 'price'

    elif data.startswith("store:"):
        store = data.split(":", 1)[1]
        results = df[df["المتجر"] == store]
        await show_results(query.message, results)

    elif data == BACK_TO_MENU:
        await start(update, context)

    elif data.startswith("specs:"):
        index = int(data.split(":")[1])
        row = df.iloc[index]
        name = row["الاسم (name)"].strip()

        url = phone_specs.get(name)
        if url:
            text = f"""📱 <b>{name}</b>\n📎 <a href="{url}">اضغط هنا لعرض المواصفات الكاملة</a>"""
        else:
            search_url = f"https://www.google.com/search?q={name.replace(' ', '+')}+site:gsmarena.com"
            text = f"""📱 <b>{name}</b>\n⚠️ لم يتم العثور على رابط المواصفات.\n📎 <a href="{search_url}">ابحث في Google عن المواصفات</a>"""

        await query.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)

    elif data == "check_subscription":
        user_id = query.from_user.id
        subscribed = await check_user_subscription(user_id, context)
        if subscribed:
            await query.message.edit_text("✅ تم التأكد من اشتراكك، يمكنك الآن استخدام البوت.\n\nاضغط /start للبدء.")
        else:
            await query.answer("❌ أنت غير مشترك بعد، يرجى الاشتراك أولاً.", show_alert=True)

# ======= معالجة الرسائل =======
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    subscribed = await check_user_subscription(user_id, context)
    if not subscribed:
        await send_subscription_required(update)
        return

    mode = context.user_data.get('mode')
    if not mode:
        await update.message.reply_text("يرجى اختيار طريقة البحث أولاً /start")
        return

    text = update.message.text.strip()

    if mode == 'name':
        names = df["الاسم (name)"].dropna().tolist()
        match, score = process.extractOne(text, names)
        results = df[df["الاسم (name)"] == match] if score > 60 else pd.DataFrame()
        await show_results(update.message, results)

    elif mode == 'price':
        try:
            price = float(text.replace(',', '').replace('٫', '').replace(' ', ''))
            min_price = price * 0.9
            max_price = price * 1.1
            results = df[df["السعر (price)"].between(min_price, max_price)]
            await show_results(update.message, results)
        except ValueError:
            await update.message.reply_text("❌ السعر غير صالح. أرسل رقماً فقط.")

# ======= عرض النتائج =======
async def show_results(msg, results):
    if results.empty:
        await msg.reply_text("❌ لم يتم العثور على نتائج.")
        return

    for idx, row in results.iterrows():
        name = row["الاسم (name)"]
        price = row["السعر (price)"]
        brand = row.get("ماركه ( Brand )", "")
        store = row["المتجر"]
        address = row["العنوان"]

        text = f"""📱 <b>{name}</b>
💰 السعر: {price:,.0f}
🏷️ الماركة: {brand}
🏬 المتجر: {store}
📍 العنوان: {address}"""

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔎 عرض المواصفات", callback_data=f"specs:{idx}")]
        ])

        await msg.reply_text(text, parse_mode="HTML", reply_markup=keyboard)

# ======= تشغيل البوت =======
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    print("✅ Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
