import os
import pandas as pd
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes
)
from thefuzz import process
import csv

load_dotenv()

# === إعداد المتغيرات ===
TOKEN = os.getenv("TOKEN")
CHANNEL_USERNAME = "@mitech808"
INSTAGRAM_URL = "https://www.instagram.com/mitech808"
DATA_FILE = "prices.xlsx"
USERS_FILE = "users.csv"
ADMIN_IDS = [193646746]

SEARCH, = range(1)

# === التحقق من الاشتراك في القناة ===
async def check_subscription(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ("member", "creator", "administrator")
    except:
        return False

# === حفظ المستخدم ===
def save_user(user):
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, "w", newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["id", "first_name", "username"])
    with open(USERS_FILE, "a", newline='') as f:
        writer = csv.writer(f)
        writer.writerow([user.id, user.first_name, user.username])

# === أمر /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not await check_subscription(user.id, context):
        keyboard = [
            [InlineKeyboardButton("✅ تم الاشتراك", callback_data="check_sub")],
            [InlineKeyboardButton("📢 قناة تيليجرام", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
            [InlineKeyboardButton("📸 تابعنا على إنستغرام", url=INSTAGRAM_URL)]
        ]
        await update.message.reply_text("👋 يجب الاشتراك في القناة أولًا لاستخدام البوت:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    save_user(user)
    keyboard = [
        [InlineKeyboardButton("📱 حسب اسم الجهاز", callback_data="search_device")],
        [InlineKeyboardButton("🏷️ حسب الماركة", callback_data="search_brand")],
        [InlineKeyboardButton("🏪 حسب المتجر", callback_data="search_store")],
        [InlineKeyboardButton("💰 حسب السعر", callback_data="search_price")]
    ]
    await update.message.reply_text("أهلاً بك 👋\nاختر طريقة البحث:", reply_markup=InlineKeyboardMarkup(keyboard))

# === زر تحقق من الاشتراك ===
async def handle_check_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if await check_subscription(query.from_user.id, context):
        save_user(query.from_user)
        await start(update, context)
    else:
        await query.edit_message_text("❌ لم يتم التحقق من الاشتراك بعد. الرجاء الاشتراك أولًا.")

# === أمر /stats للأدمن فقط ===
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ هذا الأمر مخصص للمشرف فقط.")
        return
    if not os.path.exists(USERS_FILE):
        await update.message.reply_text("⚠️ لا يوجد مستخدمون بعد.")
        return

    with open(USERS_FILE, "r") as f:
        user_count = sum(1 for _ in f) - 1
    keyboard = [[InlineKeyboardButton("⬇️ تحميل ملف المستخدمين", callback_data="download_users")]]
    await update.message.reply_text(f"عدد المستخدمين: {user_count}", reply_markup=InlineKeyboardMarkup(keyboard))

# === زر تحميل ملف المستخدمين CSV ===
async def handle_download_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id not in ADMIN_IDS:
        await query.answer("❌ هذا الأمر للمشرف فقط", show_alert=True)
        return
    await query.answer()
    await context.bot.send_document(chat_id=query.message.chat_id, document=InputFile(USERS_FILE), filename="users.csv")

# === عرض النتائج ===
def filter_data(df, column, value):
    return df[df[column].str.contains(value, case=False, na=False)]

def filter_by_price(df, price):
    try:
        price = int(price)
        margin = price * 0.10
        return df[df["السعر (price)"].apply(pd.to_numeric, errors='coerce').between(price - margin, price + margin)]
    except:
        return pd.DataFrame()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_subscription(update.effective_user.id, context):
        await start(update, context)
        return

    query = update.message.text.strip()
    df = pd.read_excel(DATA_FILE)

    search_type = context.user_data.get("search_type")

    if search_type == "device":
        results = process.extract(query, df["الاسم (name)"], limit=10)
        buttons = [
            [InlineKeyboardButton(name, callback_data=f"result:{name}")]
            for name, score in results if score > 60
        ]
        if buttons:
            await update.message.reply_text("🔍 اختر الجهاز من القائمة:", reply_markup=InlineKeyboardMarkup(buttons))
        else:
            await update.message.reply_text("❌ لم يتم العثور على نتائج.")
        return

    elif search_type == "brand":
        result_df = filter_data(df, "الماركه ( Brand )", query)
    elif search_type == "store":
        result_df = filter_data(df, "المتجر", query)
    elif search_type == "price":
        result_df = filter_by_price(df, query)
    else:
        await update.message.reply_text("❌ لم يتم تحديد نوع البحث.")
        return

    if result_df.empty:
        await update.message.reply_text("❌ لم يتم العثور على نتائج.")
    else:
        text = "\n\n".join([
            f"📱 {row['الاسم (name)']}\n💰 السعر: {row['السعر (price)']}\n🏪 المتجر: {row['المتجر']}\n📍 العنوان: {row['العنوان']}"
            for _, row in result_df.iterrows()
        ])
        keyboard = [[InlineKeyboardButton("🔙 رجوع لقائمة البحث", callback_data="back_to_search")]]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_result_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    name = query.data.split("result:")[1]
    df = pd.read_excel(DATA_FILE)
    result_df = df[df["الاسم (name)"] == name]
    if result_df.empty:
        await query.edit_message_text("❌ لم يتم العثور على تفاصيل.")
        return
    row = result_df.iloc[0]
    text = f"📱 {row['الاسم (name)']}\n💰 السعر: {row['السعر (price)']}\n🏪 المتجر: {row['المتجر']}\n📍 العنوان: {row['العنوان']}"
    keyboard = [[InlineKeyboardButton("🔙 رجوع لقائمة البحث", callback_data="back_to_search")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def set_search_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    mapping = {
        "search_device": "اسم الجهاز",
        "search_brand": "الماركة",
        "search_store": "المتجر",
        "search_price": "السعر"
    }
    context.user_data["search_type"] = query.data.split("_")[-1]
    await query.edit_message_text(f"🔍 أرسل {mapping.get(query.data)} للبحث:")

async def back_to_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

# === Main ===
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CallbackQueryHandler(handle_check_sub, pattern="check_sub"))
    app.add_handler(CallbackQueryHandler(handle_download_users, pattern="download_users"))
    app.add_handler(CallbackQueryHandler(handle_result_selection, pattern="result:"))
    app.add_handler(CallbackQueryHandler(set_search_type, pattern="search_"))
    app.add_handler(CallbackQueryHandler(back_to_search, pattern="back_to_search"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()

if __name__ == "__main__":
    main()
