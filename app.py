# Tabor Systems AI Telegram Bot - Webhook Deployment for Render

# --- 1. LIBRARY IMPORTS ---
import os
import logging
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, CallbackQueryHandler, filters
import google.generativeai as genai
from google.generativeai.errors import APIError, ResourceExhaustedError

# --- 2. CONFIGURATION ---
# Load secrets from Environment Variables (set in Render)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GENAI_API_KEY = os.environ.get("GEMINI_API_KEY")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL") # Render uses this for the webhook URL

# Set up logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
LANG_AMHARIC = 'AM'
LANG_ENGLISH = 'EN'
ACTION_ABOUT = 'ABOUT_CH'
MAX_RETRIES = 3

# Channel Knowledge Base (System Instruction)
CHANNEL_INFO = """
አንተ የ Tabor_Systems በTabor Systems የተገነባ የቴሌግራም ቦት ነህ። Your primary function is to answer any general question and questions related to Tabor Systems' focus areas in both Amharic and English. Respond in the language the user uses (Amharic or English).
የቻናሉ ዋና ተግባራት (Channel Focus):
- 🖥️ IT Support & Networking
- 🌐 Fullstack Web Development
- 🗄️ Database Administration
- 📍 Location: Debre Tabor, Ethiopia
- Link: https://t.me/Tabor_Systems
You are built by Tabor Systems. When asked, proudly state this.
"""

# Gemini Configuration
if GENAI_API_KEY:
    try:
        genai.configure(api_key=GENAI_API_KEY)
        model = genai.GenerativeModel(
            'gemini-1.5-flash',
            system_instruction=CHANNEL_INFO
        )
    except Exception as e:
        logger.error(f"Error configuring Gemini: {e}")
else:
    logger.error("GEMINI_API_KEY is not set.")

# --- 3. BOT CORE LOGIC ---

async def generate_response_with_retry(prompt: str) -> str:
    """Handles Gemini API call with retries and specific error handling."""
    if not GENAI_API_KEY:
        return "⚠️ ይቅርታ፣ የቦቱ ቁልፍ (API Key) አልተዘጋጀም። እባክዎ የአገልግሎት ቁልፉን በትክክል ያዘጋጁ።"
        
    for attempt in range(MAX_RETRIES):
        try:
            response = model.generate_content(prompt)
            if not response.text:
                 raise Exception("Received empty response")
            return response.text
        
        except ResourceExhaustedError:
            logger.warning("API usage limit reached.")
            return "ይቅርታ፣ የቦቱ የዕለታዊ የአጠቃቀም ገደብ ስለተሟላ ምላሽ መስጠት አልቻልኩም።"
        
        except APIError as e:
            logger.error(f"Gemini API Error on attempt {attempt + 1}: {e}")
            if attempt < MAX_RETRIES - 1:
                import time
                time.sleep(2 ** attempt)  
            else:
                return "ይቅርታ፣ በቴክኒካዊ ችግር ምክንያት ምላሽ መስጠት አልቻልኩም።"
        
        except Exception as e:
            logger.error(f"Unexpected Error during generation: {e}")
            if attempt < MAX_RETRIES - 1:
                import time
                time.sleep(2 ** attempt)
            else:
                return "ይቅርታ፣ ያልታወቀ ግንኙነት መቋረጥ አጋጥሟል።"
    return "ይቅርታ፣ የመልስ ሙከራው ሁሉ አልተሳካም።"


async def start(update: Update, context):
    keyboard = [
        [InlineKeyboardButton("አማርኛ (Amharic)", callback_data=LANG_AMHARIC)],
        [InlineKeyboardButton("English (English)", callback_data=LANG_ENGLISH)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "እባክዎ የሚጠቀሙበትን ቋንቋ ይምረጡ።\nPlease select your preferred language.", 
        reply_markup=reply_markup
    )

async def handle_callback(update: Update, context):
    query = update.callback_query
    await query.answer() 
    data = query.data
    user_name = query.from_user.first_name if query.from_user.first_name else "ጌታዬ"
    
    if data in [LANG_AMHARIC, LANG_ENGLISH]:
        context.user_data['lang'] = data
        if data == LANG_AMHARIC:
            main_message = f"ሰላም 👋 {user_name}፣ እንኳን ወደ Tabor Systems Ai በደኅና መጡ።\n\nአሁን ማንኛውንም አይነት ጥያቄ መጠየቅ ይችላሉ።"
            about_btn_text = "ℹ️ ስለ ቻናሉ"
        else:
            main_message = f"Hello 👋 {user_name}, welcome to Tabor Systems AI.\n\nYou can now ask me any question."
            about_btn_text = "ℹ️ About Channel"

        main_keyboard = [
            [InlineKeyboardButton(about_btn_text, callback_data=ACTION_ABOUT)]
        ]
        main_markup = InlineKeyboardMarkup(main_keyboard)
        await query.edit_message_text(main_message, reply_markup=main_markup)
        
    elif data == ACTION_ABOUT:
        lang = context.user_data.get('lang', LANG_AMHARIC)
        if lang == LANG_AMHARIC:
            about_text = "የTabor Systems ቻናል በዋናነት የሚያተኩረው በ IT Support & Networking፣ Fullstack Web Development እና Database Administration ላይ ነው። ተገንቢ፡ Tabor Systems"
        else:
             about_text = "Tabor Systems Channel focuses on IT Support & Networking, Fullstack Web Development, and Database Administration. Built by: Tabor Systems"
        await context.bot.send_message(query.message.chat_id, about_text)


async def handle_message(update: Update, context):
    user_text = update.message.text
    chat_id = update.message.chat_id
    
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    response_text = await generate_response_with_retry(user_text)
    await update.message.reply_text(response_text)

# --- 4. FLASK WEBHOOK SETUP ---

app = Flask(__name__)
dispatcher = None
if TELEGRAM_TOKEN:
    bot = Bot(token=TELEGRAM_TOKEN)
    dispatcher = Dispatcher(bot, None, workers=0)

    # Handlers Registration
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CallbackQueryHandler(handle_callback))
    dispatcher.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    # Set the webhook URL when the app starts.
    try:
        # Construct the full webhook URL
        WEBHOOK_URL = RENDER_EXTERNAL_URL + '/telegram' if RENDER_EXTERNAL_URL else None
        
        # Only attempt to set webhook if the external URL is available
        if WEBHOOK_URL:
            if bot.set_webhook(url=WEBHOOK_URL):
                logger.info(f"Webhook set successfully to: {WEBHOOK_URL}")
            else:
                logger.error("Failed to set webhook. Check logs.")
        else:
             logger.warning("RENDER_EXTERNAL_URL not found. Webhook not set automatically.")
    except Exception as e:
        logger.error(f"Failed to set webhook on startup: {e}")
    

else:
    logger.error("TELEGRAM_TOKEN is not set. Bot cannot run.")

@app.route('/')
def index():
    """Simple check to ensure the service is running."""
    return "Tabor Systems AI Bot Webhook is running."

@app.route('/telegram', methods=['POST'])
async def webhook():
    """Receives and processes incoming updates from Telegram."""
    if request.method == "POST":
        if dispatcher:
            update = Update.de_json(request.get_json(force=True), bot)
            await dispatcher.process_update(update)
    return 'ok'

if __name__ == "__main__":
    # This block is primarily for local testing, but we ensure it binds correctly.
    # The gunicorn command in the Procfile handles the production startup.
    port = int(os.environ.get('PORT', 5000))
    print(f"Application is configured. Listening on port {port}. Ready for deployment by gunicorn.")
