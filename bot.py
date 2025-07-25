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
CHANNEL_USERNAME = "@mitech808"  # قناة تيليجرام
INSTAGRAM_URL = "https://www.instagram.com/mitech808"  # رابط إنستغرام
DATA_FILE = "prices.xlsx"
USERS_FILE = "users.csv"
ADMIN_IDS = [193646746]

SEARCH_MENU, SEARCH_BY_NAME, SEARCH_BY_BRAND, SEARCH_BY_STORE, SEARCH_BY_PRICE = range(5)


def check_user(user_id):
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["user_id"])
    with open(USERS_FILE, mode='r', newline='') as file:
        reader = csv.reader(file)
        if any(row[0] == str(user_id) for row in reader):
            return
    with open(USERS_FILE, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([user_id])


async def check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_member = await context.bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user.id)
    if chat_member.status in ['left', 'kicked']:
        keyboard = [
            [InlineKeyboardButton("🔗 قناة تيليجرام", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
            [InlineKeyboardButton("📸 إنستغرام", url=INSTAGRAM_URL)],
            [InlineKeyboardButton("✅ تم الاشتراك", callback_data="check_again")]
        ]
        await update.message.reply_text("🔒 يجب الاشتراك في القنوات للاستمرار:", reply_markup=InlineKeyboardMarkup(keyboard))
        return False
    return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_subscription(update, context):
        return
    check_user(update.effective_user.id)
    keyboard = [
        [InlineKeyboardButton("📱 حسب اسم الجهاز", callback_data="search_name")],
        [InlineKeyboardButton("🏷️ حسب الماركة", callback_data="search_brand")],
        [InlineKeyboardButton("🏪 حسب المتجر", callback_data="search_store")],
        [InlineKeyboardButton("💰 حسب السعر", callback_data="search_price")]
    ]
    await update.message.reply_text("اختر طريقة البحث:", reply_markup=InlineKeyboardMarkup(keyboard))
    return SEARCH_MENU


async def handle_search_option(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice = query.data

    if choice == "check_again":
        return await start(update, context)

    context.user_data["search_type"] = choice
    prompt = {
        "search_name": "أرسل اسم الجهاز للبحث عنه:",
        "search_brand": "أرسل اسم الماركة:",
        "search_store": "أرسل اسم المتجر:",
        "search_price": "أرسل السعر (مثال: 500000):"
    }
    await query.edit_message_text(prompt[choice])
    return {
        "search_name": SEARCH_BY_NAME,
        "search_brand": SEARCH_BY_BRAND,
        "search_store": SEARCH_BY_STORE,
        "search_price": SEARCH_BY_PRICE
    }[choice]


def load_data():
    return pd.read_excel(DATA_FILE)


def filter_data(df, column, keyword):
    return df[df[column].astype(str).str.contains(keyword, case=False, na=False)]


def filter_price_range(df, price):
    min_price = price * 0.9
    max_price = price * 1.1
    return df[(df["السعر (price)"] >= min_price) & (df["السعر (price)"] <= max_price)]


async def search_results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    search_type = context.user_data.get("search_type")
    df = load_data()

    if search_type == "search_price":
        try:
            price = float(user_input.replace(",", ""))
            results = filter_price_range(df, price)
        except:
            await update.message.reply_text("❌ الرجاء إرسال رقم صالح.")
            return
    elif search_type == "search_brand":
        results = filter_data(df, "الماركه ( Brand )", user_input)
    elif search_type == "search_store":
        results = filter_data(df, "المتجر", user_input)
    else:
        matches = process.extract(user_input, df["الاسم (name)"], limit=5)
        keyboard = [[InlineKeyboardButton(m[0], callback_data=f"select|{m[0]}")] for m in matches]
        await update.message.reply_text("هل تقصد:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if results.empty:
        await update.message.reply_text("❌ لا توجد نتائج.")
    else:
        for _, row in results.iterrows():
            await update.message.reply_text(
                f"📱 الاسم: {row['الاسم (name)']}\n"
                f"💵 السعر: {row['السعر (price)']:,}\n"
                f"🏷️ الماركة: {row['الماركه ( Brand )']}\n"
                f"🏪 المتجر: {row['المتجر']}\n"
                f"📍 العنوان: {row['العنوان']}"
            )

    keyboard = [[InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="back_to_menu")]]
    await update.message.reply_text("اختر:", reply_markup=InlineKeyboardMarkup(keyboard))
    return SEARCH_MENU


async def handle_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, name = query.data.split("|")
    df = load_data()
    row = df[df["الاسم (name)"] == name].iloc[0]
    await query.message.reply_text(
        f"📱 الاسم: {row['الاسم (name)']}\n"
        f"💵 السعر: {row['السعر (price)']:,}\n"
        f"🏷️ الماركة: {row['الماركه ( Brand )']}\n"
        f"🏪 المتجر: {row['المتجر']}\n"
        f"📍 العنوان: {row['العنوان']}"
    )
    keyboard = [[InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="back_to_menu")]]
    await query.message.reply_text("اختر:", reply_markup=InlineKeyboardMarkup(keyboard))
    return SEARCH_MENU


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ هذا الأمر مخصص للمشرف فقط.")
        return
    if not os.path.exists(USERS_FILE):
        count = 0
    else:
        with open(USERS_FILE) as f:
            count = sum(1 for line in f) - 1
    keyboard = [[InlineKeyboardButton("📥 تحميل ملف المستخدمين", callback_data="export_users")]]
    await update.message.reply_text(f"📊 عدد المستخدمين: {count}", reply_markup=InlineKeyboardMarkup(keyboard))


async def export_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "rb") as f:
            await query.message.reply_document(InputFile(f, filename="users.csv"))
    else:
        await query.message.reply_text("❌ لا يوجد ملف مستخدمين.")


def main():
    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SEARCH_MENU: [CallbackQueryHandler(handle_search_option)],
            SEARCH_BY_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_results)],
            SEARCH_BY_BRAND: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_results)],
            SEARCH_BY_STORE: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_results)],
            SEARCH_BY_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_results)],
        },
        fallbacks=[CallbackQueryHandler(start, pattern="back_to_menu")],
    )

    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(handle_selection, pattern="^select\|"))
    app.add_handler(CallbackQueryHandler(export_users, pattern="export_users"))
    app.add_handler(CommandHandler("stats", stats))
    app.run_polling()


if __name__ == "__main__":
    main()
