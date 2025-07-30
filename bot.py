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
INSTAGRAM_USERNAME = "mitech808"
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

# ======= الرسائل الثابتة =======
def welcome_message(user):
    return (
        f"👋 مرحبًا بك في بوت أسعار الموبايلات!\n\n"
        f"📱 معرفك في التيليجرام: {user.username or 'غير متوفر'}\n"
        f"🆔 رقم التعريف الخاص بك: {user.id}\n"
        f"📸 تابعنا على إنستغرام: https://www.instagram.com/{INSTAGRAM_USERNAME}\n"
        f"📢 قناة التليغرام: {CHANNEL_USERNAME}\n\n"
        "لإضافة متجرك للبوت، يرجى مراسلتنا عبر رقم الواتساب التالي:\n"
        "07828816508\n\n"
        "اختر طريقة البحث المناسبة لك من الأزرار أدناه:"
    )

BACK_TO_MENU = "back_to_menu"

# ======= أزرار القائمة الرئيسية =======
def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("🔤 البحث عن طريق الاسم", callback_data="search_by_name")],
        [InlineKeyboardButton("🏷️ البحث عن طريق الماركة", callback_data="search_by_brand")],
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
        [InlineKeyboardButton("📸 تابعنا على إنستغرام", url=f"https://www.instagram.com/{INSTAGRAM_USERNAME}")],
        [InlineKeyboardButton("🔄 تحقق من الاشتراك", callback_data="check_subscription")]
    ])
    await update.message.reply_text(
        "🔒 يرجى الانضمام إلى قناتنا على تليغرام من أجل استخدام البوت 😍✅\n\n"
        f"📢 قناة التليغرام: {CHANNEL_USERNAME}\n"
        f"📸 أيضًا يجب متابعة حساب الإنستغرام:\n"
        f"https://www.instagram.com/{INSTAGRAM_USERNAME}\n\n"
        "✅ بعد الاشتراك، اضغط على /start للبدء الآن.",
        reply_markup=keyboard
    )

# ======= /start مع عرض القائمة والبيانات الشخصية =======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not await check_user_subscription(user.id, context):
        return await send_subscription_required(update)
    store_user(user)
    await update.message.reply_text(welcome_message(user), reply_markup=main_menu_keyboard())

# ======= عرض قائمة الماركات مع دعم زر المزيد =======
def get_brands():
    brands = set()
    for name in price_data.keys():
        brand = name.split()[0].strip()
        brands.add(brand)
    return sorted(brands)

async def show_brands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    brands = get_brands()
    buttons = [[InlineKeyboardButton(b, callback_data=f"brand_{b}_0")] for b in brands[:30]]
    buttons.append([InlineKeyboardButton("🔙 رجوع إلى القائمة الرئيسية", callback_data=BACK_TO_MENU)])
    await query.edit_message_text("🏷️ اختر الماركة:", reply_markup=InlineKeyboardMarkup(buttons))

# ======= عرض قائمة المتاجر كأزرار =======
def get_stores():
    stores = set()
    for specs_list in price_data.values():
        for spec in specs_list:
            stores.add(spec['store'])
    return sorted(stores)

async def show_stores(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    stores = get_stores()
    buttons = [[InlineKeyboardButton(s, callback_data=f"store_{s}")] for s in stores[:30]]
    buttons.append([InlineKeyboardButton("🔙 رجوع إلى القائمة الرئيسية", callback_data=BACK_TO_MENU)])
    await query.edit_message_text("🏬 اختر المتجر:", reply_markup=InlineKeyboardMarkup(buttons))

# ======= عرض نتائج البحث مع زر إظهار المزيد (تصفح بالصفحات) =======
async def show_results_paginated(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    results = context.user_data.get("search_results", [])
    items_per_page = 5
    start = page * items_per_page
    end = start + items_per_page
    current_page_results = results[start:end]

    if not current_page_results:
        # لا توجد نتائج في الصفحة المطلوبة
        if update.callback_query:
            await update.callback_query.edit_message_text("❌ لا توجد نتائج إضافية.", reply_markup=back_to_menu_keyboard())
        else:
            await update.message.reply_text("❌ لا توجد نتائج إضافية.", reply_markup=back_to_menu_keyboard())
        return

    keyboard = []
    text = ""
    for name in current_page_results:
        # عرض كل اسم مع زر اختيار التفاصيل
        keyboard.append([InlineKeyboardButton(f"📱 {name}", callback_data=f"device_{name}")])
        text += f"📱 {name}\n"

    # زر إظهار المزيد إذا لم نصل لنهاية النتائج
    if end < len(results):
        keyboard.append([InlineKeyboardButton("📥 إظهار المزيد", callback_data=f"more_{page + 1}")])

    keyboard.append([InlineKeyboardButton("🔙 رجوع إلى القائمة الرئيسية", callback_data=BACK_TO_MENU)])

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ======= التعامل مع اختيار الماركة والمتجر =======
async def brand_store_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("brand_"):
        parts = data.split("_")
        brand = "_".join(parts[1:-1])
        page = int(parts[-1])

        # جلب الأجهزة التي تبدأ بالماركة
        results = [name for name in price_data.keys() if name.lower().startswith(brand.lower())]
        if not results:
            await query.edit_message_text(f"❌ لا توجد أجهزة للماركة: {brand}", reply_markup=back_to_menu_keyboard())
            return

        context.user_data['search_results'] = results
        await show_results_paginated(update, context, page)

    elif data.startswith("store_"):
        store = data.replace("store_", "")
        context.user_data['search_mode'] = "store_name"
        context.user_data['selected_store'] = store
        await query.edit_message_text(
            f"🏬 تم اختيار المتجر: {store}\n\n"
            "🔤 الآن أرسل اسم الجهاز للبحث ضمن هذا المتجر:",
            reply_markup=back_to_menu_keyboard()
        )

    elif data.startswith("more_"):
        page = int(data.split("_")[1])
        await show_results_paginated(update, context, page)

# ======= التعامل مع أزرار القائمة الرئيسية =======
async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == BACK_TO_MENU:
        await query.edit_message_text(welcome_message(update.effective_user), reply_markup=main_menu_keyboard())
        return

    if data == "search_by_brand":
        return await show_brands(update, context)
    elif data == "search_by_store":
        return await show_stores(update, context)
    else:
        await query.edit_message_text(f"✏️ الآن أرسل نص البحث لـ {data.replace('search_by_', '').replace('_', ' ')}:")
        context.user_data['search_mode'] = data.replace("search_by_", "")
        context.user_data['search_results'] = []

# ======= البحث بناءً على الوضع المختار =======
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
        for name, score in matches:
            if score >= 70:
                results.append(name)

    elif mode == "store_name":
        store = context.user_data.get('selected_store')
        if not store:
            await update.message.reply_text("⚠️ حدث خطأ داخلي، المتجر غير محدد. الرجاء إعادة المحاولة.", reply_markup=back_to_menu_keyboard())
            return

        for name in price_data.keys():
            if text.lower() in name.lower():
                specs = price_data.get(name, [])
                for spec in specs:
                    if spec['store'] == store:
                        results.append(name)
                        break

    elif mode == "price":
        try:
            target = int(text)
            margin = 0.10
            min_price = int(target * (1 - margin))
            max_price = int(target * (1 + margin))
            for name, specs in price_data.items():
                for spec in specs:
                    try:
                        price = int(str(spec['price']).replace(',', '').replace('٬', ''))
                        if min_price <= price <= max_price:
                            results.append(name)
                            break
                    except ValueError:
                        continue
        except ValueError:
            await update.message.reply_text("⚠️ يرجى إدخال رقم صالح للبحث بالسعر.", reply_markup=back_to_menu_keyboard())
            return

    else:
        await update.message.reply_text("⚠️ وضع البحث غير معروف أو غير مدعوم في البحث النصي حالياً.", reply_markup=back_to_menu_keyboard())
        return

    results = list(dict.fromkeys(results))

    if not results:
        await update.message.reply_text("❌ لم أجد نتائج مطابقة.\n🔙 يمكنك العودة للقائمة الرئيسية.", reply_markup=back_to_menu_keyboard())
        return

    # خزّن النتائج في user_data للعرض مع زر إظهار المزيد
    context.user_data['search_results'] = results
    await show_results_paginated(update, context, page=0)

# ======= عرض تفاصيل الجهاز =======
async def device_option_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    device_name = query.data.replace("device_", "")

    if device_name not in price_data:
        await query.edit_message_text("❌ حدث خطأ: الجهاز غير موجود.", reply_markup=back_to_menu_keyboard())
        return

    msg = ""
    for spec in price_data[device_name]:
        msg += (
            f"📱 {device_name}\n"
            f"💰 السعر: {spec['price']}\n"
            f"🏬 المتجر: {spec['store']}\n"
            f"📍 العنوان: {spec['location']}\n\n"
        )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📎 المواصفات", url=fuzzy_get_url(device_name))],
        [InlineKeyboardButton("🔙 رجوع إلى القائمة الرئيسية", callback_data=BACK_TO_MENU)]
    ])
    await query.edit_message_text(msg, reply_markup=keyboard)

# ======= باقي الوظائف =======
async def check_subscription_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if await check_user_subscription(query.from_user.id, context):
        await query.edit_message_text("✅ تم التحقق! يمكنك الآن استخدام البوت.\n\n" + welcome_message(query.from_user), reply_markup=main_menu_keyboard())
    else:
        await query.answer("❌ لم يتم العثور على اشتراكك بعد. تأكد من الاشتراك ثم أعد المحاولة.", show_alert=True)

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

    await update.message.reply_text(
        f"👥 عدد مستخدمي البوت: {user_count}",
        reply_markup=keyboard
    )

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

COMPARE_FIRST, COMPARE_SECOND = range(2)

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

    first_match = best_match(first_name)
    second_match = best_match(second_name)

    if not first_match or not second_match:
        await update.message.reply_text("❌ لم أتمكن من العثور على أحد الجهازين. حاول مجددًا.")
        return ConversationHandler.END

    msg = f"🔍 مقارنة بين:\n\n📱 {first_match}\n📱 {second_match}\n\n"

    for key in ['price', 'store', 'location']:
        first_val = price_data.get(first_match, [{}])[0].get(key, "غير متوفر")
        second_val = price_data.get(second_match, [{}])[0].get(key, "غير متوفر")
        msg += f"{key.capitalize()}: {first_val} | {second_val}\n"

    await update.message.reply_text(msg)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ تم إلغاء العملية.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END

# ======= نقطة الدخول =======
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CallbackQueryHandler(main_menu_callback))
    app.add_handler(CallbackQueryHandler(brand_store_selected_callback))
    app.add_handler(CallbackQueryHandler(device_option_callback, pattern=r"device_"))
    app.add_handler(CallbackQueryHandler(export_users_csv_callback, pattern=r"export_users_csv"))
    app.add_handler(CallbackQueryHandler(check_subscription_button, pattern=r"check_subscription"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search_text))

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('compare', compare_start)],
        states={
            COMPARE_FIRST: [MessageHandler(filters.TEXT & ~filters.COMMAND, compare_first)],
            COMPARE_SECOND: [MessageHandler(filters.TEXT & ~filters.COMMAND, compare_second)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    app.add_handler(conv_handler)

    print("🤖 البوت يعمل الآن ...")
    app.run_polling()

if __name__ == "__main__":
    main()
