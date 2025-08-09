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

TOKEN = os.getenv("TOKEN")  # ضبط متغير البيئة TOKEN قبل التشغيل
CHANNEL_USERNAME = "@mitech808"
ADMIN_IDS = [193646746]

# ======= تحقق وجود الملفات =======
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

# إعادة تسمية الأعمدة لتسهيل الاستخدام
df.rename(columns={
    'الاسم (name)': 'name',
    'الرام والذاكره': 'ram_memory',
    'السعر (price)': 'price',
    'الماركه ( Brand )': 'brand',
    'المتجر': 'store',
    'العنوان': 'address'
}, inplace=True)

# تحويل السعر لرقم float بعد إزالة الفواصل
df['price'] = df['price'].astype(str).str.replace(',', '').astype(float)

# تحميل روابط المواصفات
with open(URLS_PATH, encoding='utf-8') as f:
    phones_urls_data = json.load(f)

url_map = {}
url_names = []
for brand_group in phones_urls_data.values():
    for device in brand_group:
        name_lower = device['name'].lower()
        url_names.append(name_lower)
        url_map[name_lower] = device['url']

# ======= حالات الحوار =======
CHOOSING, TYPING_NAME, SELECTING_STORE, TYPING_PRICE = range(4)

search_keyboard = [
    ["بحث بالاسم"],
    ["بحث بالمتجر"],
    ["بحث بالسعر"]
]
search_markup = ReplyKeyboardMarkup(search_keyboard, one_time_keyboard=True, resize_keyboard=True)

# دالة لجلب قائمة المتاجر بدون تكرار
def get_unique_stores():
    return sorted(df['store'].dropna().unique().tolist())

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
        # عرض قائمة المتاجر كأزرار تفاعلية
        stores = get_unique_stores()
        keyboard = [[InlineKeyboardButton(store, callback_data=f"store_select::{store}")] for store in stores]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text("اختر المتجر من القائمة:", reply_markup=reply_markup)
        return SELECTING_STORE

    elif text == "بحث بالسعر":
        await update.message.reply_text("أرسل السعر المطلوب (رقم فقط):", reply_markup=ReplyKeyboardRemove())
        return TYPING_PRICE

    else:
        await update.message.reply_text("الرجاء اختيار أحد الخيارات.")
        return CHOOSING

# بناء رسائل نتائج البحث مع زر المواصفات (رابط أو زر تفاعلي)
async def build_response_with_buttons(results):
    responses = []
    for _, row in results.iterrows():
        device_name = row['name']
        device_name_lower = device_name.lower()

        # تطابق اسم الجهاز مع أسماء الروابط
        match = process.extractOne(device_name_lower, url_names)
        url = None
        if match and match[1] >= 90:
            matched_name = match[0]
            url = url_map.get(matched_name)

        text = (
            f"📱 الاسم: {device_name}\n"
            f"💾 الرام والذاكرة: {row['ram_memory']}\n"
            f"💰 السعر: {row['price']:,} د.ع\n"
            f"🏷️ الماركة: {row['brand']}\n"
            f"🏪 المتجر: {row['store']}\n"
            f"📍 العنوان: {row['address']}\n"
        )

        if url:
            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton("📄 عرض المواصفات", url=url)]]
            )
        else:
            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton("📄 عرض المواصفات", callback_data=f"no_specs::{device_name}")]]
            )

        responses.append((text, keyboard))
    return responses

async def send_results(update: Update, context: ContextTypes.DEFAULT_TYPE, results):
    if results.empty:
        await update.message.reply_text("لم أجد نتائج مطابقة، حاول مرة أخرى.")
        return CHOOSING

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
    good_matches = [match for match in matches if match[1] >= 85]

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

async def store_selection_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    prefix, store_name = data.split("::", 1)

    results = df[df['store'].str.lower() == store_name.lower()]
    if results.empty:
        await query.edit_message_text("لم أجد نتائج لهذا المتجر.")
    else:
        await query.edit_message_text(f"نتائج البحث لمتجر: {store_name}")

        responses = await build_response_with_buttons(results)
        for text, keyboard in responses:
            await query.message.reply_text(text, reply_markup=keyboard)

    await query.message.reply_text("هل تريد البحث بطريقة أخرى؟ اختر خيارًا:", reply_markup=search_markup)
    return CHOOSING

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

async def no_specs_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("عذراً، لم تتوفر مواصفات لهذا الجهاز.")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("تم إلغاء البحث. لإعادة البدء أرسل /start", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


if __name__ == '__main__':
    application = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            CHOOSING: [
                MessageHandler(filters.TEXT & (~filters.COMMAND), choosing),
                CallbackQueryHandler(name_selection_handler, pattern=r"^name_select::"),
                CallbackQueryHandler(store_selection_handler, pattern=r"^store_select::"),
                CallbackQueryHandler(no_specs_handler, pattern=r"^no_specs::"),
            ],
            TYPING_NAME: [MessageHandler(filters.TEXT & (~filters.COMMAND), search_by_name)],
            SELECTING_STORE: [],
            TYPING_PRICE: [MessageHandler(filters.TEXT & (~filters.COMMAND), search_by_price)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(conv_handler)

    application.run_polling()
