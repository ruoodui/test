import os
import json
import pandas as pd
from thefuzz import process

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardRemove
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

# إعادة تسمية الأعمدة لتسهيل الاستخدام في الكود
df.rename(columns={
    'الاسم (name)': 'name',
    'الرام والذاكره': 'ram_memory',
    'السعر (price)': 'price',
    'الماركه ( Brand )': 'brand',
    'المتجر': 'store',
    'العنوان': 'address'
}, inplace=True)

# تحويل عمود السعر إلى float مع إزالة الفواصل
df['price'] = df['price'].astype(str).str.replace(',', '').astype(float)

with open(URLS_PATH, encoding='utf-8') as f:
    phones_urls_data = json.load(f)

url_map = {}
for brand_group in phones_urls_data.values():
    for device in brand_group:
        url_map[device['name'].lower()] = device['url']

# ======= حالات الحوار =======
CHOOSING, TYPING_NAME, TYPING_STORE, TYPING_PRICE, TYPING_NAME_IN_STORE = range(5)

# ======= أزرار وقوائم =======
def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("بحث بالاسم", callback_data="search_name")],
        [InlineKeyboardButton("بحث بالمتجر", callback_data="search_store")],
        [InlineKeyboardButton("بحث بالسعر", callback_data="search_price")]
    ])

def back_to_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="back_to_menu")]
    ])

def stores_keyboard():
    stores = sorted(df['store'].unique())
    keyboard = [[InlineKeyboardButton(store, callback_data=f"store_select::{store}")] for store in stores]
    keyboard.append([InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(keyboard)

# ======= دوال التعامل مع البوت =======

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    store_user(update.effective_user)
    if update.message:
        await update.message.reply_text(
            "أهلاً! كيف تريد البحث عن الهواتف؟ اختر خيارًا:",
            reply_markup=main_menu_keyboard()
        )
    elif update.callback_query:
        await update.callback_query.edit_message_text(
            "أهلاً! كيف تريد البحث عن الهواتف؟ اختر خيارًا:",
            reply_markup=main_menu_keyboard()
        )
    return CHOOSING

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "search_name":
        await query.edit_message_text("أرسل اسم الهاتف أو جزء منه:", reply_markup=back_to_menu_keyboard())
        # مسح متجر مختار إن وجد
        context.user_data.pop('selected_store', None)
        return TYPING_NAME

    elif data == "search_store":
        await query.edit_message_text("اختر المتجر للبحث فيه:", reply_markup=stores_keyboard())
        return CHOOSING

    elif data.startswith("store_select::"):
        selected_store = data.split("::", 1)[1]
        context.user_data['selected_store'] = selected_store
        await query.edit_message_text(
            f"أنت الآن تبحث في متجر: {selected_store}\n"
            "أرسل اسم الهاتف أو جزء منه للبحث:",
            reply_markup=back_to_menu_keyboard()
        )
        return TYPING_NAME_IN_STORE

    elif data == "search_price":
        await query.edit_message_text("أرسل السعر المطلوب (رقم فقط):", reply_markup=back_to_menu_keyboard())
        # مسح متجر مختار إن وجد
        context.user_data.pop('selected_store', None)
        return TYPING_PRICE

    elif data == "back_to_menu":
        context.user_data.pop('selected_store', None)
        await query.edit_message_text("اختر طريقة البحث:", reply_markup=main_menu_keyboard())
        return CHOOSING

    elif data.startswith("name_select::"):
        selected_name = data.split("::", 1)[1]
        selected_store = context.user_data.get('selected_store')

        if selected_store:
            results = df[(df['name'] == selected_name) & (df['store'] == selected_store)]
        else:
            results = df[df['name'] == selected_name]

        if results.empty:
            await query.edit_message_text("لم أتمكن من إيجاد معلومات عن هذا الجهاز.", reply_markup=back_to_menu_keyboard())
        else:
            responses = await build_response_with_buttons(results)
            for text, keyboard in responses:
                await query.edit_message_text(text, reply_markup=keyboard)

        await query.message.reply_text("هل تريد البحث بطريقة أخرى؟ اختر خيارًا:", reply_markup=main_menu_keyboard())
        context.user_data.pop('selected_store', None)
        return CHOOSING

    return CHOOSING

async def build_response_with_buttons(results):
    responses = []
    for _, row in results.iterrows():
        name_lower = row['name'].lower()
        url = url_map.get(name_lower)

        text = (
            f"📱 الاسم: {row['name']}\n"
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
            keyboard = None

        responses.append((text, keyboard))
    return responses

async def send_results(update: Update, context: ContextTypes.DEFAULT_TYPE, results):
    if results.empty:
        await update.message.reply_text("لم أجد نتائج مطابقة، حاول مرة أخرى.", reply_markup=main_menu_keyboard())
        return

    responses = await build_response_with_buttons(results)
    for text, keyboard in responses:
        if keyboard:
            await update.message.reply_text(text, reply_markup=keyboard)
        else:
            await update.message.reply_text(text)

    await update.message.reply_text("هل تريد البحث بطريقة أخرى؟ اختر خيارًا:", reply_markup=main_menu_keyboard())
    return CHOOSING

async def search_by_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.message.text.lower()
    names_list = df['name'].tolist()

    matches = process.extract(query_text, names_list, limit=10)
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

async def search_by_name_in_store(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.message.text.lower()
    selected_store = context.user_data.get('selected_store')

    if not selected_store:
        await update.message.reply_text("حدث خطأ: المتجر غير محدد. الرجاء البدء من جديد.", reply_markup=main_menu_keyboard())
        return CHOOSING

    names_list = df[df['store'] == selected_store]['name'].tolist()
    matches = process.extract(query_text, names_list, limit=10)
    good_matches = [match for match in matches if match[1] >= 85]

    if good_matches:
        matched_names = [match[0] for match in good_matches]
        results = df[(df['name'].isin(matched_names)) & (df['store'] == selected_store)]
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

async def search_by_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price_query = float(update.message.text.replace(',', '').strip())
    except ValueError:
        await update.message.reply_text("الرجاء إرسال رقم صالح للسعر.", reply_markup=back_to_menu_keyboard())
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
            CHOOSING: [CallbackQueryHandler(button_handler)],
            TYPING_NAME: [MessageHandler(filters.TEXT & (~filters.COMMAND), search_by_name)],
            TYPING_NAME_IN_STORE: [MessageHandler(filters.TEXT & (~filters.COMMAND), search_by_name_in_store)],
            TYPING_PRICE: [MessageHandler(filters.TEXT & (~filters.COMMAND), search_by_price)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(conv_handler)

    application.run_polling()
