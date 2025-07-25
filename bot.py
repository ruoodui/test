import os
import pandas as pd
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes
)
from thefuzz import process
from datetime import datetime
import csv
import logging

# ================== إعدادات ==================
TOKEN = os.getenv("TOKEN")
CHANNEL_USERNAME = "@mitech808"  # قناة تيليجرام
INSTAGRAM_URL = "https://www.instagram.com/mitech808"  # رابط إنستغرام
DATA_FILE = "prices.xlsx"
USERS_FILE = "users.csv"
ADMIN_IDS = [193646746]  # استبدل بمعرفات المشرفين

# ================== إعدادات السجل ==================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== التحقق من الاشتراك ==================
async def check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        member = await context.bot.get_chat_member(CHANNEL_USERNAME, user_id)
        if member.status in ["member", "creator", "administrator"]:
            return True
    except:
        pass

    keyboard = [
        [InlineKeyboardButton("🔗 قناة تيليجرام", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
        [InlineKeyboardButton("📸 إنستغرام", url=INSTAGRAM_URL)],
        [InlineKeyboardButton("✅ تم الاشتراك", callback_data="check_sub")]
    ]
    await update.message.reply_text("🔒 يجب الاشتراك في القنوات أولاً لاستخدام البوت:",
                                    reply_markup=InlineKeyboardMarkup(keyboard))
    return False

# ================== حفظ المستخدم ==================
def save_user(user):
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["id", "username", "first_name", "date"])

    users = pd.read_csv(USERS_FILE)
    if user.id not in users['id'].values:
        with open(USERS_FILE, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                user.id,
                user.username,
                user.first_name,
                datetime.now().strftime("%Y-%m-%d %H:%M")
            ])

# ================== /start ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_subscription(update, context):
        return

    save_user(update.effective_user)

    keyboard = [
        [
            InlineKeyboardButton("📱 حسب الجهاز", callback_data="search_name"),
            InlineKeyboardButton("🏷️ حسب الماركة", callback_data="search_brand")
        ],
        [
            InlineKeyboardButton("🏪 حسب المتجر", callback_data="search_store"),
            InlineKeyboardButton("💰 حسب السعر", callback_data="search_price")
        ]
    ]
    await update.message.reply_text("🔍 اختر نوع البحث:", reply_markup=InlineKeyboardMarkup(keyboard))

# ================== البحث ==================
def load_data():
    return pd.read_excel(DATA_FILE)

def filter_data(df, column, keyword):
    return df[df[column].str.contains(keyword, case=False, na=False)]

def filter_price_range(df, target_price):
    min_price = target_price * 0.9
    max_price = target_price * 1.1
    df['السعر (price)'] = pd.to_numeric(df['السعر (price)'], errors='coerce')
    return df[(df['السعر (price)'] >= min_price) & (df['السعر (price)'] <= max_price)]

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['mode'] = query.data
    await query.message.reply_text("✏️ أرسل الكلمة المفتاحية الآن:")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_subscription(update, context):
        return

    save_user(update.effective_user)

    mode = context.user_data.get('mode')
    if not mode:
        await start(update, context)
        return

    df = load_data()
    results = pd.DataFrame()
    text = update.message.text.strip()

    if mode == "search_name":
        results = filter_data(df, 'الاسم (name)', text)
    elif mode == "search_brand":
        results = filter_data(df, 'الماركه ( Brand )', text)
    elif mode == "search_store":
        results = filter_data(df, 'المتجر', text)
    elif mode == "search_price":
        try:
            price = int(text.replace(",", ""))
            results = filter_price_range(df, price)
        except:
            await update.message.reply_text("❌ يرجى إرسال رقم صحيح.")
            return

    if results.empty:
        await update.message.reply_text("❌ لا توجد نتائج.")
    else:
        for _, row in results.iterrows():
            msg = f"📱 <b>{row['الاسم (name)']}</b>\n💰 السعر: {row['السعر (price)']}\n🏷️ الماركة: {row['الماركه ( Brand )']}\n🏪 المتجر: {row['المتجر']}\n📍 العنوان: {row['العنوان']}"
            await update.message.reply_text(msg, parse_mode='HTML')

    keyboard = [[InlineKeyboardButton("🔙 رجوع لقائمة البحث", callback_data="back")]]
    await update.message.reply_text("اختر نوع البحث:", reply_markup=InlineKeyboardMarkup(keyboard))

# ================== /stats للأدمن فقط ==================
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ هذا الأمر مخصص للمشرف فقط.")
        return

    if not os.path.exists(USERS_FILE):
        await update.message.reply_text("لا يوجد مستخدمون بعد.")
        return

    df = pd.read_csv(USERS_FILE)
    count = df.shape[0]
    keyboard = [[InlineKeyboardButton("📥 تحميل المستخدمين CSV", callback_data="download_users")]]
    await update.message.reply_text(f"👥 عدد المستخدمين: {count}", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "back":
        await start(update, context)
    elif query.data == "download_users":
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, "rb") as f:
                await query.message.reply_document(document=InputFile(f, filename="users.csv"))
    elif query.data == "check_sub":
        if await check_subscription(update, context):
            await start(update, context)

# ================== التشغيل ==================
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.run_polling()

if __name__ == '__main__':
    main()
