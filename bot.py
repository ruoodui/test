import os
import json
import pandas as pd
from thefuzz import process

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)

# ======= إعدادات =======
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PRICES_PATH = os.path.join(BASE_DIR, "prices.xlsx")
URLS_PATH = os.path.join(BASE_DIR, "phones_urls.json")
USERS_FILE = os.path.join(BASE_DIR, "users.json")

TOKEN = os.getenv("TOKEN")  # يجب ضبط متغير البيئة TOKEN قبل التشغيل
CHANNEL_USERNAME = "@mitech808"
ADMIN_IDS = [193646746]

# ======= التحقق من وجود الملفات (رفع استثناء عند الفقدان) =======
if not os.path.exists(PRICES_PATH):
    raise FileNotFoundError(f"❌ ملف الأسعار غير موجود: {PRICES_PATH}")
if not os.path.exists(URLS_PATH):
    raise FileNotFoundError(f"❌ ملف الروابط غير موجود: {URLS_PATH}")

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

# ======= تحميل البيانات =======
df = pd.read_excel(PRICES_PATH)

with open(URLS_PATH, encoding='utf-8') as f:
    phones_urls_data = json.load(f)

url_map = {}
for brand_group in phones_urls_data.values():
    for device in brand_group:
        url_map[device['name'].lower()] = device['url']

# ======= حالات الحوار =======
CHOOSING, TYPING_NAME, TYPING_STORE, TYPING_PRICE = range(4)

search_keyboard = [
    ["بحث بالاسم"],
    ["بحث بالمتجر"],
    ["بحث بالسعر"]
]
search_markup = ReplyKeyboardMarkup(search_keyboard, one_time_keyboard=True, resize_keyboard=True)

# ======= دوال التعامل مع البوت =======

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    store_user(update.effective_user)
    await update.message.reply_text(
        "أهلاً! كيف تريد البحث عن الهواتف؟ اختر خيارًا:",
        reply_markup=search_markup
    )
    return CHOOSING

async def choosing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "بحث بالاسم":
        await update.message.reply_text("أرسل اسم الهاتف أو جزء منه:", reply_markup=ReplyKeyboardRemove())
        return TYPING_NAME

    elif text == "بحث بالمتجر":
        await update.message.reply_text("أرسل اسم المتجر:", reply_markup=ReplyKeyboardRemove())
        return TYPING_STORE

    elif text == "بحث بالسعر":
        await update.message.reply_text("أرسل السعر المطلوب (رقم فقط):", reply_markup=ReplyKeyboardRemove())
        return TYPING_PRICE

    else:
        await update.message.reply_text("الرجاء اختيار أحد الخيارات.")
        return CHOOSING

async def build_response_with_buttons(results):
    responses = []
    for _, row in results.iterrows():
        name_lower = row['name'].lower()
        url = url_map.get(name_lower)

        text = (
            f"📱 الاسم: {row['name']}\n"
            f"💾 الرام والذاكرة: {row['الرام والذاكره']}\n"
            f"💰 السعر: {row['price']:,} د.ع\n"
            f"🏷️ الماركة: {row['Brand']}\n"
            f"🏪 المتجر: {row['المتجر']}\n"
            f"📍 العنوان: {row['العنوان']}\n"
        )

        if url:
            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton("📄 عرض المواصفات", url=url)]]
            )
        else:
            keyboard = None

        responses.append((text, keyboard))
    return responses

async def send_results(update: Update, context: ContextTypes.DEFAULT_TYPE, results):
    if results.empty:
        await update.message.reply_text("لم أجد نتائج مطابقة، حاول مرة أخرى.")
        return

    responses = await build_response_with_buttons(results)
    for text, keyboard in responses:
        if keyboard:
            await update.message.reply_text(text, reply_markup=keyboard)
        else:
            await update.message.reply_text(text)

    await update.message.reply_text("هل تريد البحث بطريقة أخرى؟ اختر خيارًا:", reply_markup=search_markup)
    return CHOOSING

async def search_by_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.lower()
    names_list = df['name'].tolist()

    matches = process.extract(query, names_list, limit=10)
    good_matches = [match for match in matches if match[1] >= 95]

    if good_matches:
        matched_names = [match[0] for match in good_matches]
        results = df[df['name'].isin(matched_names)]
        return await send_results(update, context, results)

    else:
        top_matches = [match[0] for match in matches[:5]]
        keyboard = [[InlineKeyboardButton(name, callback_data=f"name_select::{name}")] for name in top_matches]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "لم أجد تطابقًا دقيقًا، هل تقصد أحد هذه الهواتف؟ اختر من القائمة:",
            reply_markup=reply_markup
        )
        return CHOOSING

async def name_selection_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    prefix, selected_name = data.split("::", 1)

    results = df[df['name'] == selected_name]
    if results.empty:
        await query.edit_message_text("لم أتمكن من إيجاد معلومات عن هذا الجهاز.")
    else:
        responses = await build_response_with_buttons(results)
        for text, keyboard in responses:
            await query.edit_message_text(text, reply_markup=keyboard)

    await query.message.reply_text("هل تريد البحث بطريقة أخرى؟ اختر خيارًا:", reply_markup=search_markup)
    return CHOOSING

async def search_by_store(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.lower()
    results = df[df['المتجر'].str.lower().str.contains(query)]
    return await send_results(update, context, results)

async def search_by_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price_query = float(update.message.text.replace(',', '').strip())
    except ValueError:
        await update.message.reply_text("الرجاء إرسال رقم صالح للسعر.")
        return TYPING_PRICE

    margin = 0.10
    lower_bound = price_query * (1 - margin)
    upper_bound = price_query * (1 + margin)

    results = df[(df['price'] >= lower_bound) & (df['price'] <= upper_bound)]
    return await send_results(update, context, results)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("تم إلغاء البحث. لإعادة البدء أرسل /start", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


if __name__ == '__main__':
    application = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            CHOOSING: [MessageHandler(filters.TEXT & (~filters.COMMAND), choosing)],
            TYPING_NAME: [MessageHandler(filters.TEXT & (~filters.COMMAND), search_by_name)],
            TYPING_STORE: [MessageHandler(filters.TEXT & (~filters.COMMAND), search_by_store)],
            TYPING_PRICE: [MessageHandler(filters.TEXT & (~filters.COMMAND), search_by_price)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(name_selection_handler, pattern=r"^name_select::"))

    application.run_polling()
