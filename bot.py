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
    # إعادة ترتيب DataFrame واحتفاظ بالفهرس للرجوع إليه
    df = df.reset_index(drop=False)  # index يحفظ رقم الصف في العمود 'index'
    return df

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

df_prices = load_excel_prices()
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
WELCOME_MSG = (
    "👋 مرحبًا بك في بوت أسعار الموبايلات!\n\n"
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

# ======= /start مع عرض القائمة =======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await check_user_subscription(user_id, context):
        return await send_subscription_required(update)
    store_user(update.effective_user)
    await update.message.reply_text(WELCOME_MSG, reply_markup=main_menu_keyboard())

# ======= عرض قائمة الماركات مع دعم زر المزيد =======
def get_brands():
    brands = set()
    for name in df_prices["الاسم (name)"]:
        brand = str(name).split()[0].strip()
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
    for store in df_prices["المتجر"]:
        stores.add(store)
    return sorted(stores)

async def show_stores(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    stores = get_stores()
    buttons = [[InlineKeyboardButton(s, callback_data=f"store_{s}")] for s in stores[:30]]
    buttons.append([InlineKeyboardButton("🔙 رجوع إلى القائمة الرئيسية", callback_data=BACK_TO_MENU)])
    await query.edit_message_text("🏬 اختر المتجر:", reply_markup=InlineKeyboardMarkup(buttons))

# ======= التعامل مع اختيار الماركة مع صفحات النتائج =======
async def brand_store_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("brand_"):
        # صيغة callback_data: brand_اسم_الماركة_رقم_الصفحة
        parts = data.split("_")
        brand = "_".join(parts[1:-1])
        page = int(parts[-1])

        # جلب الأجهزة التي تبدأ بالماركة
        all_names = df_prices["الاسم (name)"].tolist()
        results = [name for name in all_names if name.lower().startswith(brand.lower())]
        if not results:
            await query.edit_message_text(f"❌ لا توجد أجهزة للماركة: {brand}", reply_markup=back_to_menu_keyboard())
            return

        per_page = 10
        start = page * per_page
        end = start + per_page
        page_results = results[start:end]

        buttons = []
        for name in page_results:
            # البحث عن الفهرس في df_prices
            idx = df_prices[df_prices["الاسم (name)"] == name].index[0]
            buttons.append([InlineKeyboardButton(f"📱 {name}", callback_data=f"device_{idx}")])

        if end < len(results):
            buttons.append([InlineKeyboardButton("المزيد ➕", callback_data=f"brand_{brand}_{page+1}")])

        buttons.append([InlineKeyboardButton("🔙 رجوع إلى القائمة الرئيسية", callback_data=BACK_TO_MENU)])

        await query.edit_message_text(
            f"🏷️ أجهزة الماركة: {brand} (صفحة {page + 1})",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    elif data.startswith("store_"):
        store = data.replace("store_", "")
        context.user_data['search_mode'] = "store_name"
        context.user_data['selected_store'] = store
        await query.edit_message_text(
            f"🏬 تم اختيار المتجر: {store}\n\n"
            "🔤 الآن أرسل اسم الجهاز للبحث ضمن هذا المتجر:",
            reply_markup=back_to_menu_keyboard()
        )

# ======= التعامل مع أزرار القائمة الرئيسية =======
async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == BACK_TO_MENU:
        await query.edit_message_text(WELCOME_MSG, reply_markup=main_menu_keyboard())
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
        matches = process.extract(text, df_prices["الاسم (name)"].tolist(), limit=10)
        for name, score in matches:
            if score >= 70:
                results.append(name)

    elif mode == "store_name":
        store = context.user_data.get('selected_store')
        if not store:
            await update.message.reply_text("⚠️ حدث خطأ داخلي، المتجر غير محدد. الرجاء إعادة المحاولة.", reply_markup=back_to_menu_keyboard())
            return

        for idx, row in df_prices.iterrows():
            if text.lower() in str(row["الاسم (name)"]).lower() and row["المتجر"] == store:
                results.append(row["الاسم (name)"])

    elif mode == "price":
        try:
            target = int(text)
            margin = 0.10
            min_price = int(target * (1 - margin))
            max_price = int(target * (1 + margin))
            for idx, row in df_prices.iterrows():
                try:
                    price = int(str(row["السعر (price)"]).replace(',', '').replace('٬', ''))
                    if min_price <= price <= max_price:
                        results.append(row["الاسم (name)"])
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

    if mode == "price":
        count = 0
        for name in results[:10]:
            specs_rows = df_prices[df_prices["الاسم (name)"] == name]
            for _, spec in specs_rows.iterrows():
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📎 المواصفات", url=fuzzy_get_url(name))]
                ])
                msg = (
                    f"📱 {name}\n"
                    f"💰 السعر: {spec['السعر (price)']}\n"
                    f"🏬 المتجر: {spec['المتجر']}\n"
                    f"📍 العنوان: {spec['العنوان']}\n"
                )
                await update.message.reply_text(msg, reply_markup=keyboard)
                count += 1
                if count >= 10:
                    break
            if count >= 10:
                break
        await update.message.reply_text("🔙 يمكنك العودة للقائمة الرئيسية.", reply_markup=back_to_menu_keyboard())
    else:
        buttons = []
        for name in results[:10]:
            idx = df_prices[df_prices["الاسم (name)"] == name].index[0]
            buttons.append([InlineKeyboardButton(f"📱 {name}", callback_data=f"device_{idx}")])
        buttons.append([InlineKeyboardButton("🔙 رجوع إلى القائمة الرئيسية", callback_data=BACK_TO_MENU)])

        keyboard = InlineKeyboardMarkup(buttons)
        await update.message.reply_text(f"🔍 نتائج البحث عن '{text}':", reply_markup=keyboard)

# ======= عرض تفاصيل الجهاز =======
async def device_option_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if not data.startswith("device_"):
        await query.edit_message_text("❌ خطأ: بيانات الزر غير صالحة.", reply_markup=back_to_menu_keyboard())
        return

    try:
        idx = int(data.replace("device_", ""))
    except ValueError:
        await query.edit_message_text("❌ خطأ في رقم الجهاز.", reply_markup=back_to_menu_keyboard())
        return

    if idx not in df_prices.index:
        await query.edit_message_text("❌ الجهاز غير موجود.", reply_markup=back_to_menu_keyboard())
        return

    row = df_prices.loc[idx]
    msg = (
        f"📱 {row['الاسم (name)']}\n"
        f"💰 السعر: {row['السعر (price)']}\n"
        f"🏬 المتجر: {row['المتجر']}\n"
        f"📍 العنوان: {row['العنوان']}\n"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📎 المواصفات", url=fuzzy_get_url(row['الاسم (name)']))],
        [InlineKeyboardButton("🔙 رجوع إلى القائمة الرئيسية", callback_data=BACK_TO_MENU)]
    ])
    await query.edit_message_text(msg, reply_markup=keyboard)

# ======= باقي الوظائف كما في السكربت الأصلي (التحقق، إحصائيات، ...) =======
# ...

# ======= نقاط الدخول =======
def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stats", stats_command))

    application.add_handler(CallbackQueryHandler(main_menu_callback, pattern="^(search_by_name|search_by_brand|search_by_store|search_by_price|back_to_menu)$"))
    application.add_handler(CallbackQueryHandler(brand_store_selected_callback, pattern="^(brand_|store_).*"))
    application.add_handler(CallbackQueryHandler(device_option_callback, pattern="^device_.*$"))
    application.add_handler(CallbackQueryHandler(check_subscription_button, pattern="^check_subscription$"))
    application.add_handler(CallbackQueryHandler(export_users_csv_callback, pattern="^export_users_csv$"))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search_text))

    print("🤖 بوت أسعار الهواتف يعمل الآن ...")
    application.run_polling()

if __name__ == "__main__":
    main()
