import os
import pandas as pd
import json
from thefuzz import process

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes
)

# ======= إعدادات =======
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # ✅ مسار ديناميكي
PRICES_PATH = os.path.join(BASE_DIR, "prices.xlsx")
URLS_PATH = os.path.join(BASE_DIR, "phones_urls.json")
USERS_FILE = os.path.join(BASE_DIR, "users.json")
TOKEN = os.getenv("TOKEN")
CHANNEL_USERNAME = "@mitech808"
ADMIN_IDS = [193646746]  # <-- استبدل بمعرف المشرف الخاص بك

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
    df = df.dropna(subset=["الاسم (name)", "السعر (price)"])  # حذف الروم حسب طلبك
    phone_map = {}
    for _, row in df.iterrows():
        name = str(row["الاسم (name)"]).strip()
        price = str(row["السعر (price)"]).strip()
        phone_map.setdefault(name, []).append({"price": price})
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

# ======= البيانات =======
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
    "👋 مرحبًا بك في بوت أسعار الموبايلات!\n\n"
    "📱 أرسل اسم الجهاز (مثال: Galaxy S25 Ultra)\n"
    "💰 أو أرسل السعر (مثال: 1300000) للبحث عن أجهزة في هذا النطاق.\n"
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
        "🔒 يرجى الانضمام إلى قناتنا على تليغرام من أجل استخدام البوت 😍✅\n\n"
        f"📢 قناة التليغرام: {CHANNEL_USERNAME}\n"
        "📸 أيضًا يجب متابعة حساب الإنستغرام:\n"
        "https://www.instagram.com/mitech808\n\n"
        "✅ بعد الاشتراك، اضغط على /start للبدء الآن.",
        reply_markup=keyboard
    )

# ======= دالة start (هام جداً) =======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await check_user_subscription(user_id, context):
        return await send_subscription_required(update)

    store_user(update.effective_user)  # حفظ المستخدم
    await update.message.reply_text(WELCOME_MSG)

# ======= مقارنة =======
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

    first = best_match(first_name)
    second = best_match(second_name)

    if not first or not second:
        await update.message.reply_text("❌ لم أتمكن من العثور على أحد الأجهزة. حاول كتابة الأسماء بشكل أدق.")
        return ConversationHandler.END

    msg = f"⚖️ مقارنة بين:\n\n"
    msg += f"📱 {first}:\n"
    for spec in price_data[first]:
        msg += f"💰 {spec['price']}\n🔗 {fuzzy_get_url(first)}\n"
    msg += f"\n📱 {second}:\n"
    for spec in price_data[second]:
        msg += f"💰 {spec['price']}\n🔗 {fuzzy_get_url(second)}\n"
    await update.message.reply_text(msg)
    return ConversationHandler.END

async def compare_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ تم إلغاء عملية المقارنة.")
    return ConversationHandler.END

# ======= الرسائل العامة =======
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await check_user_subscription(user_id, context):
        return await send_subscription_required(update)

    store_user(update.effective_user)  # حفظ المستخدم

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
                        msg = f"📱 {name}\n💰 {spec['price']}"
                        keyboard = InlineKeyboardMarkup([
                            [InlineKeyboardButton("📎 المواصفات", url=fuzzy_get_url(name))]
                        ])
                        await update.message.reply_text(msg, reply_markup=keyboard)
                except:
                    continue
        return

    matches = process.extract(text, price_data.keys(), limit=5)
    good_matches = [m for m in matches if m[1] >= 95]

    if not good_matches:
        suggestions = [m[0] for m in matches if m[1] >= 70]
        if suggestions:
            buttons = [[InlineKeyboardButton(s, callback_data=f"spec_{s}")] for s in suggestions]
            await update.message.reply_text(
                "❌ لم أجد جهازًا مطابقًا بدقة.\n\nهل تقصد أحد هذه الأجهزة؟",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        else:
            await update.message.reply_text("❌ لم أجد جهازًا مشابهًا. حاول كتابة الاسم بشكل أدق.")
        return

    for name, _ in good_matches:
        for spec in price_data[name]:
            msg = f"📱 {name}\n💰 {spec['price']}"
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📎 المواصفات", url=fuzzy_get_url(name))]
            ])
            await update.message.reply_text(msg, reply_markup=keyboard)

async def check_subscription_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if await check_user_subscription(query.from_user.id, context):
        await query.edit_message_text("✅ تم التحقق! يمكنك الآن استخدام البوت.\n\n" + WELCOME_MSG)
    else:
        await query.answer("❌ لم يتم العثور على اشتراكك بعد. تأكد من الاشتراك ثم أعد المحاولة.", show_alert=True)

# ======= أمر المشرف /stats =======
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ هذا الأمر مخصص للمشرف فقط.")
        return

    users = load_users()
    if not users:
        await update.message.reply_text("❌ لا يوجد مستخدمون مسجلون بعد.")
        return

    msg = f"👥 عدد مستخدمي البوت: {len(users)}"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 تصدير قائمة المستخدمين CSV", callback_data="export_users_csv")]
    ])
    await update.message.reply_text(msg, reply_markup=keyboard)

# ======= تعامل مع زر تصدير CSV للمشرف =======
async def export_users_csv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id not in ADMIN_IDS:
        await query.edit_message_text("❌ هذا الأمر مخصص للمشرف فقط.")
        return

    users = load_users()
    if not users:
        await query.edit_message_text("❌ لا يوجد مستخدمون مسجلون بعد.")
        return

    import io
    import csv

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "name", "username"])
    for user in users.values():
        writer.writerow([user["id"], user["name"], user["username"] or "—"])
    output.seek(0)

    await context.bot.send_document(
        chat_id=user_id,
        document=output.getvalue().encode("utf-8"),
        filename="users.csv",
        caption="📋 قائمة المستخدمين"
    )
    await query.edit_message_text("✅ تم إرسال ملف المستخدمين إليك.")

# ======= التعامل مع الأزرار =======
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("spec_"):
        phone_name = data[5:]
        if phone_name in price_data:
            msg = f"📱 {phone_name}:\n"
            for spec in price_data[phone_name]:
                msg += f"💰 {spec['price']}\n🔗 {fuzzy_get_url(phone_name)}\n"
            await query.edit_message_text(msg)
        else:
            await query.edit_message_text("❌ لم أتمكن من العثور على هذا الجهاز.")

    elif data == "check_subscription":
        if await check_user_subscription(query.from_user.id, context):
            await query.edit_message_text("✅ تم التحقق! يمكنك الآن استخدام البوت.\n\n" + WELCOME_MSG)
        else:
            await query.answer("❌ لم يتم العثور على اشتراكك بعد. تأكد من الاشتراك ثم أعد المحاولة.", show_alert=True)

    elif data == "export_users_csv":
        await export_users_csv(update, context)

# ======= تشغيل البوت =======
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
    app.add_handler(CommandHandler("stats", stats_command))  # أمر المشرف
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(compare_conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ البوت يعمل الآن...")
    app.run_polling()

if __name__ == "__main__":
    main()
