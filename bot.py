import os
import io
import csv
import json
import re
import pandas as pd
from thefuzz import process, fuzz

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardRemove, InputFile
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

# ======= الرسائل الثابتة =======
WELCOME_MSG = (
    "👋 مرحبًا بك في بوت أسعار الموبايلات!\n\n"
    "لإضافة متجرك للبوت، يرجى مراسلتنا عبر رقم الواتساب التالي:\n"
    "07828816508\n\n"
    "اختر طريقة البحث المناسبة لك من الأزرار أدناه:"
)

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

# ======= التحقق من وجود الملفات =======
if not os.path.exists(PRICES_PATH):
    raise FileNotFoundError(f"❌ ملف الأسعار غير موجود: {PRICES_PATH}")
if not os.path.exists(URLS_PATH):
    raise FileNotFoundError(f"❌ ملف الروابط غير موجود: {URLS_PATH}")

# ======= تنظيف وتحويل الأسعار =======
def clean_price(value):
    cleaned = re.sub(r'[^0-9.]', '', str(value))
    try:
        return float(cleaned)
    except:
        return None

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

df['price'] = df['price'].apply(clean_price)
df = df.dropna(subset=['price'])
df['name'] = df['name'].astype(str).str.strip()

with open(URLS_PATH, encoding='utf-8') as f:
    phones_urls_data = json.load(f)

def clean_name(name):
    return ''.join(ch for ch in name.lower().strip() if ch.isalnum() or ch.isspace())

url_map = {}
for brand_group in phones_urls_data.values():
    for device in brand_group:
        url_map[clean_name(device['name'])] = device['url']

def get_device_url(name):
    cleaned = clean_name(name)
    best_match = process.extractOne(cleaned, url_map.keys(), scorer=fuzz.partial_ratio)
    if best_match and best_match[1] >= 70:
        return url_map[best_match[0]]
    simplified = cleaned.split('(')[0].strip()
    best_match = process.extractOne(simplified, url_map.keys(), scorer=fuzz.partial_ratio)
    if best_match and best_match[1] >= 70:
        return url_map[best_match[0]]
    return None

# ======= حالات الحوار =======
CHOOSING, TYPING_NAME, SELECTING_STORE, TYPING_PRICE, SELECTING_SUGGESTION = range(5)

search_keyboard = [
    [
        InlineKeyboardButton("🔍 بحث بالاسم", callback_data="search_name"),
        InlineKeyboardButton("🏪 بحث بالمتجر", callback_data="search_store"),
        InlineKeyboardButton("💰 بحث بالسعر", callback_data="search_price"),
    ]
]
search_markup = InlineKeyboardMarkup(search_keyboard)

def get_unique_stores():
    return sorted(df['store'].dropna().unique().tolist())

# ======= دوال البوت =======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await check_user_subscription(user_id, context):
        await send_subscription_required(update)
        return ConversationHandler.END

    store_user(update.effective_user)
    await update.message.reply_text(WELCOME_MSG, reply_markup=search_markup)
    return CHOOSING

async def subscription_check_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if await check_user_subscription(user_id, context):
        await query.edit_message_text("✅ شكراً لانضمامك! يمكنك الآن استخدام البوت عبر /start")
    else:
        await query.edit_message_text("❌ لم يتم العثور على اشتراكك. يرجى الانضمام أولاً.")

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
        await query.edit_message_text("👋 كيف تريد البحث عن الهواتف؟", reply_markup=search_markup)
        return CHOOSING

async def store_selection_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, selected_store = query.data.split("::", 1)
    context.user_data['selected_store'] = selected_store
    await query.edit_message_text(f"🔍 البحث داخل المتجر: {selected_store}\n\nأرسل اسم الهاتف أو جزء منه:")
    return TYPING_NAME

async def search_by_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.message.text.strip()
    selected_store = context.user_data.get('selected_store')
    filtered_df = df[df['store'].str.lower() == selected_store.lower()] if selected_store else df
    names_list = filtered_df['name'].tolist()

    matched_names = [name for name, score in [(n, fuzz.token_sort_ratio(query_text.lower(), n.lower())) for n in names_list] if score >= 90]

    if matched_names:
        results = filtered_df[filtered_df['name'].isin(matched_names)]
        return await send_results(update, context, results)

    suggestions = [name for name, score in [(n, fuzz.token_sort_ratio(query_text.lower(), n.lower())) for n in names_list] if 60 <= score < 90]
    suggestions = sorted(suggestions, key=lambda n: fuzz.token_sort_ratio(query_text.lower(), n.lower()), reverse=True)[:10]

    if suggestions:
        context.user_data['suggestions'] = suggestions
        text = "❌ لم أجد تطابقًا دقيقًا، هل تقصد أحد هذه الأجهزة؟\n"
        for i, name in enumerate(suggestions, start=1):
            text += f"{i}. {name}\n"
        text += "\nأرسل رقم الجهاز من القائمة أعلاه لاختيار الجهاز المطلوب، أو أرسل اسم آخر للبحث."
        await update.message.reply_text(text)
        return SELECTING_SUGGESTION

    else:
        await update.message.reply_text("❌ لم أتمكن من العثور على أي جهاز مشابه للاسم المدخل.")
        await update.message.reply_text("اختر طريقة أخرى للبحث:", reply_markup=search_markup)
        return CHOOSING

async def suggestion_choice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    suggestions = context.user_data.get('suggestions', [])

    if user_input.isdigit():
        idx = int(user_input) - 1
        if 0 <= idx < len(suggestions):
            selected_name = suggestions[idx]
            selected_store = context.user_data.get('selected_store')
            filtered_df = df[df['store'].str.lower() == selected_store.lower()] if selected_store else df
            results = filtered_df[filtered_df['name'] == selected_name]

            if results.empty:
                await update.message.reply_text("❌ لم أتمكن من إيجاد معلومات عن هذا الجهاز.")
            else:
                for _, row in results.iterrows():
                    url = get_device_url(row['name'])
                    buttons = []
                    if url:
                        buttons.append([InlineKeyboardButton("📄 عرض المواصفات", url=url)])
                    text = (
                        f"📱 الاسم: {row['name']}\n"
                        f"💾 الرام والذاكرة: {row['ram_memory']}\n"
                        f"💰 السعر: {row['price']:,} د.ع\n"
                        f"🏷️ الماركة: {row['brand']}\n"
                        f"🏪 المتجر: {row['store']}\n"
                        f"📍 العنوان: {row['address']}\n"
                    )
                    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
            context.user_data.pop('suggestions', None)
            return CHOOSING
        else:
            await update.message.reply_text("❌ الرقم غير صالح. الرجاء اختيار رقم من القائمة.")
            return SELECTING_SUGGESTION
    else:
        context.user_data.pop('suggestions', None)
        return await search_by_name(update, context)

async def name_selection_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            url = get_device_url(row['name'])
            buttons = []
            if url:
                buttons.append([InlineKeyboardButton("📄 عرض المواصفات", url=url)])
            text = (
                f"📱 الاسم: {row['name']}\n"
                f"💾 الرام والذاكرة: {row['ram_memory']}\n"
                f"💰 السعر: {row['price']:,} د.ع\n"
                f"🏷️ الماركة: {row['brand']}\n"
                f"🏪 المتجر: {row['store']}\n"
                f"📍 العنوان: {row['address']}\n"
            )
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))

    context.user_data.pop('selected_store', None)
    return CHOOSING

async def send_results(update: Update, context: ContextTypes.DEFAULT_TYPE, results):
    if results.empty:
        await update.message.reply_text("❌ لم أجد نتائج مطابقة، حاول مرة أخرى.")
        return CHOOSING

    for _, row in results.iterrows():
        url = get_device_url(row['name'])
        buttons = []
        if url:
            buttons.append([InlineKeyboardButton("📄 عرض المواصفات", url=url)])
        text = (
            f"📱 الاسم: {row['name']}\n"
            f"💾 الرام والذاكرة: {row['ram_memory']}\n"
            f"💰 السعر: {row['price']:,} د.ع\n"
            f"🏷️ الماركة: {row['brand']}\n"
            f"🏪 المتجر: {row['store']}\n"
            f"📍 العنوان: {row['address']}\n"
        )
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

    # زر بحث جديد
    new_search_button = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 بحث جديد", callback_data="new_search")]
    ])
    await update.message.reply_text("اختر طريقة أخرى للبحث:", reply_markup=new_search_button)

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

# ======= دالة تصدير المستخدمين CSV =======
async def export_users_csv_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❌ هذا الأمر مخصص للمشرف فقط.", show_alert=True)
        return

    users = load_users()
    if not users:
        await query.message.reply_text("❌ لا يوجد مستخدمون مسجلون حالياً.")
        return

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "name", "username"])
    for user in users.values():
        writer.writerow([user.get("id", ""), user.get("name", ""), user.get("username", "")])

    output.seek(0)
    bio = io.BytesIO(output.getvalue().encode("utf-8"))
    bio.name = "users.csv"

    await query.message.reply_document(document=InputFile(bio, filename="users.csv"))

# ======= أمر إحصائيات المشرف =======
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ هذا الأمر مخصص للمشرف فقط.")
        return

    users = load_users()
    user_count = len(users)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬇️ تصدير المستخدمين CSV", callback_data="export_users_csv")]
    ])

    await update.message.reply_text(f"👥 عدد مستخدمي البوت: {user_count}", reply_markup=keyboard)

# ======= تشغيل التطبيق =======
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING: [
                CallbackQueryHandler(search_choice_handler, per_message=True),
                CallbackQueryHandler(subscription_check_callback, pattern="^check_subscription$", per_message=True),
                CallbackQueryHandler(export_users_csv_callback, pattern="^export_users_csv$", per_message=True),
                CallbackQueryHandler(search_choice_handler, pattern="^new_search$", per_message=True),
                CallbackQueryHandler(store_selection_handler, pattern="^store_select::", per_message=True),
            ],
            TYPING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_by_name)],
            SELECTING_SUGGESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, suggestion_choice_handler)],
            SELECTING_STORE: [CallbackQueryHandler(store_selection_handler, pattern="^store_select::", per_message=True)],
            TYPING_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_by_price)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("stats", stats_command))

    print("✅ البوت يعمل الآن...")
    app.run_polling()

if __name__ == "__main__":
    main()
