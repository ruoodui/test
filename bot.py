import os
import pandas as pd
from thefuzz import process
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

# ======= إعدادات =======
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PRICES_PATH = os.path.join(BASE_DIR, "prices.xlsx")

# ======= تحميل البيانات =======
df = pd.read_excel(PRICES_PATH)
df.fillna("", inplace=True)
price_data = {
    row["name"]: {
        "price": row["price"],
        "store": row["المتجر"],
        "address": row["العنوان"]
    }
    for _, row in df.iterrows()
}

# ======= البحث الغامض =======
def fuzzy_search(query):
    names = list(price_data.keys())
    results = process.extract(query, names, limit=10)
    return [name for name, score in results if score >= 60]

# ======= إرسال معلومات الجهاز =======
async def send_device_info(update: Update, context: ContextTypes.DEFAULT_TYPE, name: str):
    info = price_data.get(name)
    if not info:
        await update.message.reply_text("❌ لم يتم العثور على معلومات للجهاز.")
        return

    text = f"📱 *{name}*\n💰 السعر: {info['price']}\n🏬 المتجر: {info['store']}\n📍 العنوان: {info['address']}"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📎 المواصفات", url=fuzzy_get_url(name))],
        [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="back_to_home")]
    ])
    await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")

# ======= توليد رابط المواصفات (مؤقتًا وهمي) =======
def fuzzy_get_url(name):
    return "https://www.gsmarena.com"

# ======= التعامل مع الرسائل =======
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text
    matches = fuzzy_search(query)

    if not matches:
        await update.message.reply_text("❌ لم يتم العثور على نتائج.")
        return

    if len(matches) == 1:
        await send_device_info(update, context, matches[0])
        return

    buttons = [
        [InlineKeyboardButton(name, callback_data=f"device_{name}")]
        for name in matches
    ]
    keyboard = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("🔍 اختر الجهاز الذي تقصده:", reply_markup=keyboard)

# ======= عند الضغط على أحد نتائج البحث =======
async def device_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    device_name = query.data.replace("device_", "")

    info = price_data.get(device_name)
    if not info:
        await query.edit_message_text("❌ لم يتم العثور على معلومات للجهاز.")
        return

    text = f"📱 *{device_name}*\n💰 السعر: {info['price']}\n🏬 المتجر: {info['store']}\n📍 العنوان: {info['address']}"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📎 المواصفات", url=fuzzy_get_url(device_name))],
        [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="back_to_home")]
    ])
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

# ======= عرض الماركات =======
async def show_brands_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    all_brands = sorted(set(name.split()[0] for name in price_data.keys()))
    buttons = [
        [InlineKeyboardButton(brand, callback_data=f"device_{brand}")]
        for brand in all_brands
    ]

    keyboard = InlineKeyboardMarkup(buttons)
    await query.edit_message_text(
        "🏷️ *الماركات المتوفرة:* اختر ماركة لعرض الأجهزة:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

# ======= العودة إلى القائمة الرئيسية =======
async def back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 بحث جديد", switch_inline_query_current_chat="")],
        [InlineKeyboardButton("🏷️ عرض الماركات", callback_data="show_brands")],
        [InlineKeyboardButton("⚖️ مقارنة جهازين", callback_data="start_compare")],
        [InlineKeyboardButton("📢 الاشتراك في القناة", url="https://t.me/mitech808")]
    ])
    await query.edit_message_text(
        "🏠 *القائمة الرئيسية*\n\nاختر أحد الخيارات:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

# ======= مقارنة جهازين (مؤقتًا) =======
async def compare_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📊 سيتم تفعيل ميزة مقارنة جهازين قريبًا.")

# ======= التشغيل =======
def main():
    import dotenv
    dotenv.load_dotenv()
    app = Application.builder().token(os.getenv("TOKEN")).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(device_callback, pattern="^device_"))
    app.add_handler(CallbackQueryHandler(back_to_main_menu, pattern="^back_to_home$"))
    app.add_handler(CallbackQueryHandler(show_brands_callback, pattern="^show_brands$"))
    app.add_handler(CallbackQueryHandler(compare_start, pattern="^start_compare$"))

    app.run_polling()

if __name__ == "__main__":
    main()
