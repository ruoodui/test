import os
import json
import pandas as pd
from thefuzz import process, fuzz

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

TOKEN = os.getenv("TOKEN")  # تأكد من ضبط متغير البيئة TOKEN قبل التشغيل
CHANNEL_USERNAME = "@mitech808"
ADMIN_IDS = [193646746]

# ======= التحقق من وجود الملفات =======
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

df.rename(columns={
    'الاسم (name)': 'name',
    'الرام والذاكره': 'ram_memory',
    'السعر (price)': 'price',
    'الماركه ( Brand )': 'brand',
    'المتجر': 'store',
    'العنوان': 'address'
}, inplace=True)

df['price'] = df['price'].astype(str).str.replace(',', '').astype(float)

with open(URLS_PATH, encoding='utf-8') as f:
    phones_urls_data = json.load(f)

url_map = {}
for brand_group in phones_urls_data.values():
    for device in brand_group:
        url_map[device['name'].lower()] = device['url']

# ======= حالات الحوار =======
CHOOSING, TYPING_NAME, SELECTING_STORE, TYPING_PRICE = range(4)

search_keyboard = [
    [
        InlineKeyboardButton("🔍 بحث بالاسم", callback_data="search_name"),
        InlineKeyboardButton("🏪 بحث بالمتجر", callback_data="search_store"),
        InlineKeyboardButton("💰 بحث بالسعر", callback_data="search_price"),
    ]
]
search_markup = InlineKeyboardMarkup(search_keyboard)

# ======= دوال مساعدة =======
def get_unique_stores():
    return sorted(df['store'].dropna().unique().tolist())

def build_product_buttons(matches, df):
    keyboard = []
    for i in range(0, len(matches), 2):
        row = []
        for j in range(2):
            if i + j < len(matches):
                name = matches[i + j][0]
                price = df[df['name'] == name]['price'].values[0]
                button_text = f"📱 {name}\n💰 {price} د.ع"
                row.append(InlineKeyboardButton(button_text, callback_data=f"name_select::{name}"))
        keyboard.append(row)
    keyboard.append([
        InlineKeyboardButton("📋 عرض الكل", callback_data="show_all"),
        InlineKeyboardButton("🔍 بحث جديد", callback_data="new_search")
    ])
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="go_back")])
    return InlineKeyboardMarkup(keyboard)

# ======= دوال البوت =======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    store_user(update.effective_user)
    await update.message.reply_text(
        "👋 أهلاً بك! كيف تريد البحث عن الهواتف؟ اختر خيارًا:",
        reply_markup=search_markup
    )
    return CHOOSING

async def search_choice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice = query.data

    if choice == "search_name":
        await query.edit_message_text("📝 أرسل اسم الهاتف أو جزء منه:")
        return TYPING_NAME

    elif choice == "search_store":
        stores = get_unique_stores()
        keyboard = [[InlineKeyboardButton(store, callback_data=f"store_select::{store}")] for store in stores]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("🏪 اختر المتجر من القائمة:", reply_markup=reply_markup)
        return SELECTING_STORE

    elif choice == "search_price":
        await query.edit_message_text("💰 أرسل السعر المطلوب (رقم فقط):")
        return TYPING_PRICE

    elif choice == "new_search":
        await query.edit_message_text(
            "👋 كيف تريد البحث عن الهواتف؟ اختر خيارًا:",
            reply_markup=search_markup
        )
        return CHOOSING

    elif choice == "go_back":
        await query.edit_message_text(
            "👋 كيف تريد البحث عن الهواتف؟ اختر خيارًا:",
            reply_markup=search_markup
        )
        return CHOOSING

async def store_selection_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, selected_store = query.data.split("::", 1)
    context.user_data['selected_store'] = selected_store
    await query.edit_message_text(f"🔍 البحث داخل المتجر: {selected_store}\n\nأرسل اسم الهاتف أو جزء منه:")
    return TYPING_NAME

async def search_by_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.message.text.lower().strip()
    selected_store = context.user_data.get('selected_store')
    filtered_df = df[df['store'].str.lower() == selected_store.lower()] if selected_store else df
    names_list = filtered_df['name'].tolist()

    matches = [(name, fuzz.token_sort_ratio(query_text, name.lower())) for name in names_list]

    good_matches = [match for match in matches if match[1] >= 95]

    if good_matches:
        matched_names = [match[0] for match in good_matches]
        results = filtered_df[filtered_df['name'].isin(matched_names)]
        return await send_results(update, context, results)

    # عرض اقتراحات بنسبة تشابه >= 70%
    suggestions = [match for match in matches if match[1] >= 70]
    suggestions = sorted(suggestions, key=lambda x: x[1], reverse=True)[:6]

    if suggestions:
        keyboard = []
        for name, score in suggestions:
            button_text = f"📱 {name} ({score}%)"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"name_select::{name}")])
        keyboard.append([InlineKeyboardButton("🔍 بحث جديد", callback_data="new_search")])
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="go_back")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "❌ لم أجد تطابقًا دقيقًا، هل تقصد أحد هذه الأجهزة؟ اختر من القائمة:",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text("❌ لم أتمكن من العثور على أي جهاز مشابه للاسم المدخل.")

    return CHOOSING

async def name_selection_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("name_selection_handler triggered")  # للتتبع
    query = update.callback_query
    await query.answer()
    _, selected_name = query.data.split("::", 1)
    selected_store = context.user_data.get('selected_store')
    filtered_df = df[df['store'].str.lower() == selected_store.lower()] if selected_store else df
    results = filtered_df[filtered_df['name'] == selected_name]

    if results.empty:
        await query.edit_message_text("❌ لم أتمكن من إيجاد معلومات عن هذا الجهاز.")
    else:
        for _, row in results.iterrows():
            name_lower = row['name'].lower()
            best_match = process.extractOne(name_lower, url_map.keys(), scorer=fuzz.token_sort_ratio)
            url = url_map[best_match[0]] if best_match and best_match[1] >= 90 else None

            text = (
                f"📱 الاسم: {row['name']}\n"
                f"💾 الرام والذاكرة: {row['ram_memory']}\n"
                f"💰 السعر: {row['price']:,} د.ع\n"
                f"🏷️ الماركة: {row['brand']}\n"
                f"🏪 المتجر: {row['store']}\n"
                f"📍 العنوان: {row['address']}\n"
            )
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("📄 عرض المواصفات", url=url)]]) if url else None
            await query.edit_message_text(text, reply_markup=keyboard)

    context.user_data.pop('selected_store', None)
    await query.message.reply_text("هل تريد البحث بطريقة أخرى؟ اختر خيارًا:", reply_markup=search_markup)
    return CHOOSING

async def send_results(update: Update, context: ContextTypes.DEFAULT_TYPE, results):
    if results.empty:
        await update.message.reply_text("❌ لم أجد نتائج مطابقة، حاول مرة أخرى.")
        return CHOOSING

    for _, row in results.iterrows():
        name_lower = row['name'].lower()
        best_match = process.extractOne(name_lower, url_map.keys(), scorer=fuzz.token_sort_ratio)
        url = url_map[best_match[0]] if best_match and best_match[1] >= 90 else None

        text = (
            f"📱 الاسم: {row['name']}\n"
            f"💾 الرام والذاكرة: {row['ram_memory']}\n"
            f"💰 السعر: {row['price']:,} د.ع\n"
            f"🏷️ الماركة: {row['brand']}\n"
            f"🏪 المتجر: {row['store']}\n"
            f"📍 العنوان: {row['address']}\n"
        )
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("📄 عرض المواصفات", url=url)]]) if url else None
        await update.message.reply_text(text, reply_markup=keyboard)

    await update.message.reply_text("هل تريد البحث بطريقة أخرى؟ اختر خيارًا:", reply_markup=search_markup)
    return CHOOSING

async def search_by_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price_query = float(update.message.text.replace(',', '').strip())
    except ValueError:
        await update.message.reply_text("❌ الرجاء إرسال رقم صالح للسعر.")
        return TYPING_PRICE

    margin = 0.10
    lower_bound = price_query * (1 - margin)
    upper_bound = price_query * (1 + margin)
    selected_store = context.user_data.get('selected_store')
    filtered_df = df[df['store'].str.lower() == selected_store.lower()] if selected_store else df
    results = filtered_df[(filtered_df['price'] >= lower_bound) & (filtered_df['price'] <= upper_bound)]
    return await send_results(update, context, results)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ تم إلغاء العملية. يمكنك البدء من جديد باستخدام /start", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# ======= تشغيل التطبيق =======
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING: [CallbackQueryHandler(search_choice_handler)],
            TYPING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_by_name)],
            SELECTING_STORE: [CallbackQueryHandler(store_selection_handler, pattern="^store_select::")],
            TYPING_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_by_price)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )

    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(name_selection_handler, pattern="^name_select::"))

    print("✅ البوت يعمل الآن...")
    app.run_polling()

if __name__ == "__main__":
    main()
