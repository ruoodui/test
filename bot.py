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
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PRICES_PATH = os.path.join(BASE_DIR, "prices.xlsx")
URLS_PATH = os.path.join(BASE_DIR, "urls.json")
USERS_PATH = os.path.join(BASE_DIR, "users.csv")

# ========== الترحيب ==========
WELCOME_MSG = """📱 أهلاً بك في بوت أسعار الهواتف

🔍 أرسل اسم الجهاز للبحث عن سعره.
📊 أو أرسل اسمين للمقارنة بين جهازين.
💡 مثال: iPhone 13 Pro Max
💡 مثال للمقارنة: S23 Ultra vs iPhone 15 Pro Max
"""

# ========== تحميل البيانات ==========
def load_prices():
    df = pd.read_excel(PRICES_PATH)
    df.fillna("", inplace=True)
    return df

def load_urls():
    if os.path.exists(URLS_PATH):
        with open(URLS_PATH, "r") as f:
            return json.load(f)
    return {}

# ========== حفظ المستخدمين ==========
def save_user(user_id):
    if not os.path.exists(USERS_PATH):
        with open(USERS_PATH, "w") as f:
            f.write("user_id\n")
    with open(USERS_PATH, "r") as f:
        existing = f.read().splitlines()
    if str(user_id) not in existing:
        with open(USERS_PATH, "a") as f:
            f.write(f"{user_id}\n")

def get_user_count():
    if os.path.exists(USERS_PATH):
        with open(USERS_PATH, "r") as f:
            return len(f.read().splitlines()) - 1
    return 0

# ========== استرجاع الرابط ==========
def fuzzy_get_url(name):
    urls = load_urls()
    best_match, score = process.extractOne(name, urls.keys())
    if score >= 60:
        return urls[best_match]
    return "https://www.gsmarena.com/"

# ========== بدء ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update.effective_user.id)
    await update.message.reply_text(WELCOME_MSG)

# ========== إحصائيات ==========
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    count = get_user_count()
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 تصدير المستخدمين", callback_data="export_users")]
    ])
    await update.message.reply_text(f"👥 عدد المستخدمين: {count}", reply_markup=keyboard)

async def export_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    if os.path.exists(USERS_PATH):
        await update.callback_query.message.reply_document(document=USERS_PATH)

# ========== اقتراح المطابقات ==========
async def suggest_devices(update: Update, context: ContextTypes.DEFAULT_TYPE, query, all_devices):
    matches = process.extract(query, all_devices, limit=5)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(match[0], callback_data=f"search::{match[0]}")]
        for match in matches if match[1] >= 60
    ])
    await update.message.reply_text("🔎 هل تقصد أحد هذه الأجهزة؟", reply_markup=keyboard)

# ========== زر الرجوع للقائمة ==========
async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(WELCOME_MSG)

# ========== دالة البحث ==========
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    df = load_prices()
    all_devices = df['name'].unique().tolist()

    # مقارنة بين جهازين
    if " vs " in text.lower():
        first, second = text.lower().split(" vs ")
        first_match = process.extractOne(first.strip(), all_devices)
        second_match = process.extractOne(second.strip(), all_devices)
        if first_match[1] >= 60 and second_match[1] >= 60:
            await compare_second(update, context, first_match[0], second_match[0])
        else:
            await suggest_devices(update, context, text, all_devices)
        return

    # بحث عن جهاز واحد
    good_matches = process.extract(text, all_devices, limit=1)
    if not good_matches or good_matches[0][1] < 60:
        await suggest_devices(update, context, text, all_devices)
        return

    price_data = {}
    for _, row in df.iterrows():
        name = row['name']
        if name not in price_data:
            price_data[name] = []
        price_data[name].append({
            'price': row['price'],
            'store': row['المتجر'],
            'address': row['العنوان'],
            'brand': row[' Brand ']
        })

    for name, _ in good_matches:
        for spec in price_data[name]:
            msg = (
                f"📱 {name}\n"
                f"💰 السعر: {spec['price']}\n"
                f"🏬 المتجر: {spec['store']}\n"
                f"📍 العنوان: {spec['address']}\n"
                f"🏷️ الماركة: {spec['brand']}"
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📎 رابط المواصفات", url=fuzzy_get_url(name))],
                [InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="back_to_menu")]
            ])
            await update.message.reply_text(msg, reply_markup=keyboard)

# ========== مقارنة جهازين ==========
async def compare_second(update: Update, context: ContextTypes.DEFAULT_TYPE, first, second):
    df = load_prices()
    first_info = df[df['name'] == first].iloc[0]
    second_info = df[df['name'] == second].iloc[0]

    msg = f"📊 مقارنة بين:\n\n"
    msg += f"🔹 {first}\n💰 {first_info['price']} - {first_info['المتجر']}\n\n"
    msg += f"🔸 {second}\n💰 {second_info['price']} - {second_info['المتجر']}"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📎 مواصفات {first}", url=fuzzy_get_url(first))],
        [InlineKeyboardButton(f"📎 مواصفات {second}", url=fuzzy_get_url(second))],
        [InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="back_to_menu")]
    ])
    await update.message.reply_text(msg, reply_markup=keyboard)

# ========== زر مقترح ==========
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("search::"):
        device_name = query.data.split("::")[1]
        update.message = query.message  # لتحاكي الرسالة الأصلية
        update.message.text = device_name
        await handle_message(update, context)

# ========== إعداد البوت ==========
def main():
    app = Application.builder().token("YOUR_BOT_TOKEN_HERE").build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CallbackQueryHandler(export_users, pattern="^export_users$"))
    app.add_handler(CallbackQueryHandler(back_to_menu, pattern="^back_to_menu$"))
    app.add_handler(CallbackQueryHandler(handle_callback_query, pattern="^search::"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()

if __name__ == '__main__':
    main()
