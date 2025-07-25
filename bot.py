import os
import io
import csv
import json
import pandas as pd
from thefuzz import process

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
        phone_map.setdefault(name, []).append({
            "price": str(row.get("السعر (price)", "")).strip(),
            "store": str(row.get("المتجر", "—")).strip(),
            "location": str(row.get("العنوان", "—")).strip(),
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
    "👋 مرحبًا بك في بوت أسعار الموبايلات!

"
    "📱 أرسل اسم الجهاز (مثال: Galaxy S25 Ultra)
"
    "💰 أو أرسل السعر (مثال: 1300000) للبحث عن أجهزة في هذا النطاق.
"
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
        "🔒 يرجى الانضمام إلى قناتنا على تليغرام من أجل استخدام البوت 😍✅

"
        f"📢 قناة التليغرام: {CHANNEL_USERNAME}
"
        "📸 أيضًا يجب متابعة حساب الإنستغرام:
"
        "https://www.instagram.com/mitech808

"
        "✅ بعد الاشتراك، اضغط على /start للبدء الآن.",
        reply_markup=keyboard
    )

# ======= مقارنة =======
COMPARE_FIRST, COMPARE_SECOND = range(2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await check_user_subscription(user_id, context):
        return await send_subscription_required(update)
    store_user(update.effective_user)
    await update.message.reply_text(WELCOME_MSG)

async def compare_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_user_subscription(update.effective_user.id, context):
        return await send_subscription_required(update)
    await update.message.reply_text("📱 أرسل اسم الجهاز الأول للمقارنة:")
    return COMPARE_FIRST

async def compare_first(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['compare_first'] = update.message.text.strip()
    await update.message.reply_text("📱 الآن أرسل اسم الجهاز الثاني للمقارنة:")
    return COMPARE_SECOND

async def compare_second(update: Update, context: ContextTypes.DEFAULT_TYPE):
    first_name = context.user_data.get('compare_first')
    second_name = update.message.text.strip()

    def best_match(name):
        matches = process.extract(name, price_data.keys(), limit=1)
        if matches and matches[0][1] >= 95:
            return matches[0][0]
        return None

    first = best_match(first_name)
    second = best_match(second_name)

    if not first or not second:
        await update.message.reply_text("❌ لم أتمكن من العثور على أحد الأجهزة. حاول كتابة الأسماء بشكل أدق.")
        return ConversationHandler.END

    msg = f"⚖️ مقارنة بين:

"

    msg += f"📱 {first}:
"
    for spec in price_data[first]:
        msg += (
            f"💰 السعر: {spec['price']}
"
            f"🏬 المتجر: {spec['store']}
"
            f"📍 العنوان: {spec['location']}
"
            f"🔗 {fuzzy_get_url(first)}

"
        )

    msg += f"📱 {second}:
"
    for spec in price_data[second]:
        msg += (
            f"💰 السعر: {spec['price']}
"
            f"🏬 المتجر: {spec['store']}
"
            f"📍 العنوان: {spec['location']}
"
            f"🔗 {fuzzy_get_url(second)}

"
        )

    await update.message.reply_text(msg)
    return ConversationHandler.END

async def compare_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ تم إلغاء عملية المقارنة.")
    return ConversationHandler.END

# ======= زر الرجوع للقائمة =======
async def start_over_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(WELCOME_MSG)

# ======= عرض تفاصيل الجهاز عند اختيار زر =======
async def device_option_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    device_name = query.data.replace("device_", "")

    if device_name not in price_data:
        await query.edit_message_text("❌ حدث خطأ: الجهاز غير موجود.")
        return

    msg = ""
    for spec in price_data[device_name]:
        msg += (
            f"📱 {device_name}
"
            f"💰 السعر: {spec['price']}
"
            f"🏬 المتجر: {spec['store']}
"
            f"📍 العنوان: {spec['location']}

"
        )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📎 المواصفات", url=fuzzy_get_url(device_name))],
        [InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="start_over")]
    ])
    await query.edit_message_text(msg, reply_markup=keyboard)

# ======= الرسائل العامة =======
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
                        msg = (
                            f"📱 {name}
"
                            f"💰 السعر: {spec['price']}
"
                            f"🏬 المتجر: {spec['store']}
"
                            f"📍 العنوان: {spec['location']}"
                        )
                        keyboard = InlineKeyboardMarkup([
                            [InlineKeyboardButton("📎 المواصفات", url=fuzzy_get_url(name))],
                            [InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="start_over")]
                        ])
                        await update.message.reply_text(msg, reply_markup=keyboard)
                        break
                except ValueError:
                    continue
        return

    matches = process.extract(text, price_data.keys(), limit=5)
    good_matches = [m for m in matches if m[1] >= 95]

    if good_matches:
        for name, _ in good_matches:
            for spec in price_data[name]:
                msg = (
                    f"📱 {name}
"
                    f"💰 السعر: {spec['price']}
"
                    f"🏬 المتجر: {spec['store']}
"
                    f"📍 العنوان: {spec['location']}"
                )
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📎 المواصفات", url=fuzzy_get_url(name))],
                    [InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="start_over")]
                ])
                await update.message.reply_text(msg, reply_markup=keyboard)
        return

    suggestions = [m[0] for m in matches if m[1] >= 70]
    if suggestions:
        buttons = [
            [InlineKeyboardButton(f"🔹 {name}", callback_data=f"device_{name}")]
            for name in suggestions
        ]
        buttons.append([InlineKeyboardButton("🔍 بحث جديد", callback_data="start_over")])
        keyboard = InlineKeyboardMarkup(buttons)
        await update.message.reply_text(
            "❌ لم أجد جهازًا مطابقًا بدقة.

"
            "هل تريد اختيار أحد هذه الأجهزة لعرض تفاصيله؟",
            reply_markup=keyboard
        )
    else:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔍 بحث جديد", callback_data="start_over")]
        ])
        await update.message.reply_text("❌ لم أجد جهازًا مشابهًا. حاول كتابة الاسم بشكل أدق.", reply_markup=keyboard)

# باقي الأوامر (check_subscription_button، /stats) تُترك كما هي...
# أضف باقي الأوامر كما هي من سكربتك إن أردت، أو أرسل لي لأكملها.

def main():
    app = Application.builder().token(TOKEN).build()

    compare_conv = ConversationHandler(
        entry_points=[CommandHandler("compare", compare_start)],
        states={
            COMPARE_FIRST: [MessageHandler(filters.TEXT & ~filters.COMMAND, compare_first)],
            COMPARE_SECOND: [MessageHandler(filters.TEXT & ~filters.COMMAND, compare_second)],
        },
        fallbacks=[CommandHandler("cancel", compare_cancel)],
        allow_reentry=True
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(start_over_callback, pattern="^start_over$"))
    app.add_handler(CallbackQueryHandler(device_option_callback, pattern="^device_"))
    app.add_handler(compare_conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ البوت يعمل الآن...")
    app.run_polling()

if __name__ == "__main__":
    main()
