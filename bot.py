import os
import io
import csv
import json
import pandas as pd
from thefuzz import process

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

# إعدادات المسارات
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PRICES_PATH = os.path.join(BASE_DIR, "prices.xlsx")
URLS_PATH = os.path.join(BASE_DIR, "phones_urls.json")
USERS_FILE = os.path.join(BASE_DIR, "users.json")
TOKEN = os.getenv("TOKEN")
CHANNEL_USERNAME = "@mitech808"
ADMIN_IDS = [193646746]

# تحميل المستخدمين
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

# تحميل الأسعار
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

# تحميل روابط المواصفات
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

# مطابقة الرابط
def fuzzy_get_url(name):
    if name in phone_urls:
        return phone_urls[name]
    matches = process.extract(name, phone_urls.keys(), limit=1)
    if matches and matches[0][1] >= 80:
        return phone_urls[matches[0][0]]
    return "https://t.me/mitech808"

# رسائل ثابتة
WELCOME_MSG = (
    "👋 مرحبًا بك في بوت أسعار الموبايلات!\n\n"
    "لإضافة متجرك للبوت، يرجى مراسلتنا عبر رقم الواتساب التالي:\n"
    "07828816508\n\n"
    "اختر طريقة البحث المناسبة لك من الأزرار أدناه:"
)
BACK_TO_MENU = "back_to_menu"

# قائمة رئيسية
def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔤 البحث عن طريق الاسم", callback_data="search_by_name")],
        [InlineKeyboardButton("🏷️ البحث عن طريق الماركة", callback_data="search_by_brand")],
        [InlineKeyboardButton("🏬 البحث عن طريق المتجر", callback_data="search_by_store")],
        [InlineKeyboardButton("💰 البحث عن طريق السعر", callback_data="search_by_price")]
    ])

def back_to_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع إلى القائمة الرئيسية", callback_data=BACK_TO_MENU)]
    ])

# التحقق من الاشتراك
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

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await check_user_subscription(user_id, context):
        return await send_subscription_required(update)
    store_user(update.effective_user)
    await update.message.reply_text(WELCOME_MSG, reply_markup=main_menu_keyboard())

# قائمة الماركات
def get_brands():
    return sorted(set(name.split()[0].strip() for name in price_data.keys()))

async def show_brands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    brands = get_brands()
    buttons = [[InlineKeyboardButton(b, callback_data=f"brand_{b}_0")] for b in brands[:30]]
    buttons.append([InlineKeyboardButton("🔙 رجوع إلى القائمة الرئيسية", callback_data=BACK_TO_MENU)])
    await query.edit_message_text("🏷️ اختر الماركة:", reply_markup=InlineKeyboardMarkup(buttons))

# قائمة المتاجر
def get_stores():
    return sorted(set(spec['store'] for specs in price_data.values() for spec in specs))

async def show_stores(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    stores = get_stores()
    buttons = [[InlineKeyboardButton(s, callback_data=f"store_{s}")] for s in stores[:30]]
    buttons.append([InlineKeyboardButton("🔙 رجوع إلى القائمة الرئيسية", callback_data=BACK_TO_MENU)])
    await query.edit_message_text("🏬 اختر المتجر:", reply_markup=InlineKeyboardMarkup(buttons))

# التعامل مع الماركة أو المتجر
async def brand_store_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("brand_"):
        parts = data.split("_")
        brand = "_".join(parts[1:-1])
        page = int(parts[-1])
        results = [name for name in price_data.keys() if name.lower().startswith(brand.lower())]

        if not results:
            await query.edit_message_text(f"❌ لا توجد أجهزة للماركة: {brand}", reply_markup=back_to_menu_keyboard())
            return

        per_page = 10
        start = page * per_page
        end = start + per_page
        page_results = results[start:end]
        buttons = [[InlineKeyboardButton(f"📱 {name}", callback_data=f"device_{name}")] for name in page_results]

        if end < len(results):
            buttons.append([InlineKeyboardButton("المزيد ➕", callback_data=f"brand_{brand}_{page+1}")])

        buttons.append([InlineKeyboardButton("🔙 رجوع إلى القائمة الرئيسية", callback_data=BACK_TO_MENU)])

        await query.edit_message_text(f"🏷️ أجهزة الماركة: {brand} (صفحة {page + 1})", reply_markup=InlineKeyboardMarkup(buttons))

    elif data.startswith("store_"):
        store = data.replace("store_", "")
        context.user_data['search_mode'] = "store_name"
        context.user_data['selected_store'] = store
        await query.edit_message_text(
            f"🏬 تم اختيار المتجر: {store}\n\n🔤 الآن أرسل اسم الجهاز للبحث ضمن هذا المتجر:",
            reply_markup=back_to_menu_keyboard()
        )

# القائمة الرئيسية
async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == BACK_TO_MENU:
        await query.edit_message_text(WELCOME_MSG, reply_markup=main_menu_keyboard())
    elif data == "search_by_brand":
        await show_brands(update, context)
    elif data == "search_by_store":
        await show_stores(update, context)
    else:
        context.user_data['search_mode'] = data.replace("search_by_", "")
        context.user_data['search_results'] = []
        await query.edit_message_text("✏️ الآن أرسل نص البحث:", reply_markup=back_to_menu_keyboard())

# زر "➕ المزيد"
async def show_more_results_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['search_page'] += 1
    await show_search_results(query, context)

# عرض نتائج البحث المجزأة
async def show_search_results(update_or_query, context):
    results = context.user_data.get('search_results', [])
    page = context.user_data.get('search_page', 0)
    per_page = 10

    start = page * per_page
    end = start + per_page
    page_results = results[start:end]

    if not page_results:
        await update_or_query.message.reply_text("❌ لا توجد نتائج إضافية.", reply_markup=back_to_menu_keyboard())
        return

    buttons = [[InlineKeyboardButton(f"📱 {name}", callback_data=f"device_{name}")] for name in page_results]

    if end < len(results):
        buttons.append([InlineKeyboardButton("➕ المزيد", callback_data="more_results")])

    buttons.append([InlineKeyboardButton("🔙 رجوع إلى القائمة الرئيسية", callback_data=BACK_TO_MENU)])
    keyboard = InlineKeyboardMarkup(buttons)

    msg = f"🔍 عرض {min(end, len(results))} من أصل {len(results)} نتيجة:"
    if isinstance(update_or_query, Update):
        await update_or_query.message.reply_text(msg, reply_markup=keyboard)
    else:
        await update_or_query.edit_message_text(msg, reply_markup=keyboard)

# البحث
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

    if mode == "name":
        matches = process.extract(text, price_data.keys(), limit=50)
        results = [name for name, score in matches if score >= 70]
    elif mode == "store_name":
        store = context.user_data.get("selected_store")
        results = [name for name in price_data if text.lower() in name.lower()
                   and any(spec['store'] == store for spec in price_data[name])]
    elif mode == "price":
        try:
            val = int(text)
            min_price = int(val * 0.9)
            max_price = int(val * 1.1)
            for name, specs in price_data.items():
                for spec in specs:
                    try:
                        price = int(str(spec['price']).replace(',', '').replace('٬', ''))
                        if min_price <= price <= max_price:
                            results.append(name)
                            break
                    except:
                        continue
        except:
            await update.message.reply_text("⚠️ يرجى إدخال رقم صالح.", reply_markup=back_to_menu_keyboard())
            return

    results = list(dict.fromkeys(results))
    context.user_data['search_results'] = results
    context.user_data['search_page'] = 0

    if not results:
        await update.message.reply_text("❌ لم يتم العثور على نتائج.", reply_markup=back_to_menu_keyboard())
    else:
        await show_search_results(update, context)

# عرض تفاصيل جهاز
async def device_option_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    name = query.data.replace("device_", "")
    if name not in price_data:
        await query.edit_message_text("❌ الجهاز غير موجود.", reply_markup=back_to_menu_keyboard())
        return
    msg = ""
    for spec in price_data[name]:
        msg += f"📱 {name}\n💰 السعر: {spec['price']}\n🏬 المتجر: {spec['store']}\n📍 العنوان: {spec['location']}\n\n"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📎 المواصفات", url=fuzzy_get_url(name))],
        [InlineKeyboardButton("🔙 رجوع إلى القائمة الرئيسية", callback_data=BACK_TO_MENU)]
    ])
    await query.edit_message_text(msg, reply_markup=keyboard)

# التحقق من الاشتراك من زر
async def check_subscription_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if await check_user_subscription(query.from_user.id, context):
        await query.edit_message_text("✅ تم التحقق! يمكنك الآن استخدام البوت.\n\n" + WELCOME_MSG, reply_markup=main_menu_keyboard())
    else:
        await query.answer("❌ لم يتم التحقق من اشتراكك.", show_alert=True)

# /stats
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ هذا الأمر للمشرف فقط.")
        return
    users = load_users()
    count = len(users)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬇️ تصدير المستخدمين CSV", callback_data="export_users_csv")]
    ])
    await update.message.reply_text(f"👥 عدد المستخدمين: {count}", reply_markup=keyboard)

# تصدير CSV
async def export_users_csv_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id not in ADMIN_IDS:
        return
    users = load_users()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "name", "username"])
    for u in users.values():
        writer.writerow([u.get("id", ""), u.get("name", ""), u.get("username", "")])
    bio = io.BytesIO(output.getvalue().encode("utf-8"))
    bio.name = "users.csv"
    await query.message.reply_document(document=InputFile(bio, filename="users.csv"))

# main
def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CallbackQueryHandler(main_menu_callback, pattern="^(search_by_|back_to_menu)$"))
    application.add_handler(CallbackQueryHandler(brand_store_selected_callback, pattern="^(brand_|store_).*"))
    application.add_handler(CallbackQueryHandler(device_option_callback, pattern="^device_.*$"))
    application.add_handler(CallbackQueryHandler(check_subscription_button, pattern="^check_subscription$"))
    application.add_handler(CallbackQueryHandler(export_users_csv_callback, pattern="^export_users_csv$"))
    application.add_handler(CallbackQueryHandler(show_more_results_callback, pattern="^more_results$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search_text))
    print("🤖 البوت يعمل الآن...")
    application.run_polling()

if __name__ == "__main__":
    main()
