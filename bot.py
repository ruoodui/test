# سكربت بوت أسعار الموبايلات - كامل ومعدل 100%
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
    filters, ContextTypes
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
    df = df.dropna(subset=["الاسم (name)", "السعر (price)", "الماركه ( Brand )"])
    phone_map = {}
    brand_set = set()
    for _, row in df.iterrows():
        name = str(row["الاسم (name)"]).strip()
        brand = str(row["الماركه ( Brand )"]).strip()
        brand_set.add(brand)
        phone_map.setdefault(name, []).append({
            "price": str(row.get("السعر (price)", "")).strip(),
            "store": str(row.get("المتجر", "—")).strip(),
            "location": str(row.get("العنوان", "—")).strip(),
            "brand": brand
        })
    return phone_map, sorted(brand_set)

price_data, brand_list = load_excel_prices()

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

phone_urls = load_phone_urls()

def fuzzy_get_url(name):
    if name in phone_urls:
        return phone_urls[name]
    matches = process.extract(name, phone_urls.keys(), limit=1)
    if matches and matches[0][1] >= 80:
        return phone_urls[matches[0][0]]
    return "https://t.me/mitech808"

WELCOME_MSG = (
    "👋 مرحبًا بك في بوت أسعار الموبايلات!\n\n"
    "لإضافة متجرك للبوت، يرجى مراسلتنا عبر رقم الواتساب التالي:\n"
    "07828816508\n\n"
    "اختر طريقة البحث المناسبة لك من الأزرار أدناه:"
)
BACK_TO_MENU = "back_to_menu"

def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("🔤 البحث عن طريق الاسم", callback_data="search_by_name")],
        [InlineKeyboardButton("🏷️ البحث عن طريق الماركة", callback_data="search_by_brand")],
        [InlineKeyboardButton("🏬 البحث عن طريق المتجر", callback_data="search_by_store")],
        [InlineKeyboardButton("💰 البحث عن طريق السعر", callback_data="search_by_price")],
    ]
    return InlineKeyboardMarkup(keyboard)

def back_to_menu_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع إلى القائمة الرئيسية", callback_data=BACK_TO_MENU)]])

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await check_user_subscription(user_id, context):
        return await send_subscription_required(update)
    store_user(update.effective_user)
    await update.message.reply_text(WELCOME_MSG, reply_markup=main_menu_keyboard())

def get_brands():
    return brand_list

async def show_brands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    buttons = [[InlineKeyboardButton(b, callback_data=f"brand_{b}_0")] for b in brand_list[:30]]
    buttons.append([InlineKeyboardButton("🔙 رجوع إلى القائمة الرئيسية", callback_data=BACK_TO_MENU)])
    await query.edit_message_text("🏷️ اختر الماركة:", reply_markup=InlineKeyboardMarkup(buttons))

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

async def brand_store_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("brand_"):
        parts = data.split("_")
        brand = "_".join(parts[1:-1])
        page = int(parts[-1])

        results = [name for name, specs in price_data.items() if any(spec.get("brand", "").lower() == brand.lower() for spec in specs)]
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
        context.user_data['search_page'] = 0

async def send_search_results_page(update, context, results, page=0, mode="name"):
    per_page = 10
    start = page * per_page
    end = start + per_page
    page_results = results[start:end]

    buttons = [[InlineKeyboardButton(f"📱 {name}", callback_data=f"device_{name}")] for name in page_results]

    if end < len(results):
        buttons.append([InlineKeyboardButton("المزيد ➕", callback_data="search_more")])

    buttons.append([InlineKeyboardButton("🔙 رجوع إلى القائمة الرئيسية", callback_data=BACK_TO_MENU)])

    if update.callback_query:
        await update.callback_query.edit_message_text(
            f"🔍 نتائج البحث (صفحة {page + 1}):",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    else:
        await update.message.reply_text(
            f"🔍 نتائج البحث (صفحة {page + 1}):",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

async def search_more_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if 'search_results' not in context.user_data or not context.user_data['search_results']:
        await query.edit_message_text("⚠️ لا توجد نتائج للعرض.")
        return
    context.user_data['search_page'] += 1
    await send_search_results_page(update, context, context.user_data['search_results'], context.user_data['search_page'])

# ======= دالة عرض المواصفات عند الضغط على زر المقارنة أو عرض التفاصيل =======
async def device_option_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("specs_"):
        name = data.split("_", 1)[1]
        url = fuzzy_get_url(name)
        await query.message.reply_text(f"📎 رابط المواصفات:\n{url}", disable_web_page_preview=True)

    elif data == "back_to_menu":
        await start(update, context)

# ======= تشغيل البوت =======
def main():
    app = Application.builder().token("YOUR_BOT_TOKEN_HERE").build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback, pattern="^(search_by|select_brand|select_store|back_to_menu|compare_).+"))
    app.add_handler(CallbackQueryHandler(device_option_callback, pattern="^(specs_|back_to_menu)"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search_text))

    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()

