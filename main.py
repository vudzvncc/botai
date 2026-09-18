import os
import time
import threading
import discord
import requests
from discord.ext import commands
from google import genai
from dotenv import load_dotenv
from flask import Flask

# ---------------------------------------------------------
# 1. Khởi tạo Web Server với Flask (để giữ bot chạy 24/7)
# ---------------------------------------------------------
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot Discord Gemini đang hoạt động!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# ---------------------------------------------------------
# 2. Cấu hình Bot Discord & Gemini AI
# ---------------------------------------------------------
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

ai_client = genai.Client(api_key=GEMINI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

chat_sessions = {}   # { channel_id: chat_session }
channel_models = {}  # { channel_id: "model_name" }

DEFAULT_MODEL = "gemini-2.5-flash"

# LỜI DẶN HỆ THỐNG: Bắt buộc Bot luôn trả lời bằng tiếng Việt
SYSTEM_INSTRUCTION = "Bạn là một trợ lý AI thông minh trên Discord. Luôn luôn trả lời hoàn toàn bằng tiếng Việt tự nhiên, lịch sự và dễ hiểu, ngoại trừ khi người dùng yêu cầu dịch sang ngôn ngữ khác hoặc viết mã code."

@bot.event
async def on_ready():
    print(f"Bot đã đăng nhập thành công với tên: {bot.user}")

# ---------------------------------------------------------
# 3. Các Lệnh Điều Khiển (Bot Commands)
# ---------------------------------------------------------

@bot.command(name="model")
async def change_or_show_model(ctx, new_model: str = None):
    """Xem hoặc thay đổi mô hình Gemini cho kênh hiện tại."""
    channel_id = ctx.channel.id

    if new_model is None:
        current_model = channel_models.get(channel_id, DEFAULT_MODEL)
        await ctx.reply(f"🤖 Mô hình Gemini hiện tại của kênh này là: `{current_model}`")
        return

    channel_models[channel_id] = new_model
    if channel_id in chat_sessions:
        del chat_sessions[channel_id]

    await ctx.reply(
        f"✅ Đã chuyển mô hình Gemini sang: `{new_model}`!\n"
        f"🧹 Lịch sử trò chuyện của kênh này đã được làm mới."
    )

@bot.command(name="clear")
async def clear_history(ctx):
    """Xóa lịch sử trò chuyện của kênh hiện tại."""
    session_id = ctx.channel.id
    if session_id in chat_sessions:
        del chat_sessions[session_id]
        await ctx.reply("🧹 Đã xóa lịch sử trò chuyện của kênh này!")
    else:
        await ctx.reply("Kênh này chưa có lịch sử trò chuyện nào.")

@bot.command(name="dog")
async def get_random_dog(ctx):
    """Lấy ảnh chó ngẫu nhiên."""
    try:
        response = requests.get("https://dog.ceo/api/breeds/image/random")
        data = response.json()
        if data.get("status") == "success":
            await ctx.reply(data["message"])
        else:
            await ctx.reply("Không thể lấy ảnh chó vào lúc này.")
    except Exception as e:
        await ctx.reply(f"Lỗi khi gọi API: {e}")

@bot.command(name="crypto")
async def get_crypto_price(ctx, coin: str = "bitcoin"):
    """Tra cứu giá coin từ CoinGecko API."""
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin.lower()}&vs_currencies=usd"
        response = requests.get(url)
        data = response.json()
        
        if coin.lower() in data:
            price = data[coin.lower()]["usd"]
            await ctx.reply(f"💰 Giá **{coin.capitalize()}** hiện tại: **${price:,} USD**")
        else:
            await ctx.reply(f"Không tìm thấy thông tin cho coin: `{coin}`")
    except Exception as e:
        await ctx.reply(f"Lỗi khi lấy giá crypto: {e}")

# ---------------------------------------------------------
# 4. Xử Lý Trò Chuyện (AI Chat)
# ---------------------------------------------------------

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    await bot.process_commands(message)

    if message.content.startswith(bot.command_prefix):
        return

    is_mentioned = bot.user in message.mentions
    is_private = isinstance(message.channel, discord.DMChannel)

    if is_mentioned or is_private:
        user_input = message.content.replace(f"<@{bot.user.id}>", "").strip()

        if not user_input:
            await message.channel.send("Bạn cần hỏi gì tôi thế?")
            return

        session_id = message.channel.id
        selected_model = channel_models.get(session_id, DEFAULT_MODEL)

        # CÁCH 1 NẰM Ở ĐÂY: Tạo phiên chat với cấu hình system_instruction
        if session_id not in chat_sessions:
            chat_sessions[session_id] = ai_client.chats.create(
                model=selected_model,
                config={
                    "system_instruction": SYSTEM_INSTRUCTION
                }
            )

        chat = chat_sessions[session_id]

        async with message.channel.typing():
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = chat.send_message(user_input)
                    reply_text = response.text

                    if len(reply_text) <= 2000:
                        await message.reply(reply_text)
                    else:
                        for i in range(0, len(reply_text), 1900):
                            await message.channel.send(reply_text[i:i + 1900])
                    break

                except Exception as e:
                    error_str = str(e)
                    if "503" in error_str and attempt < max_retries - 1:
                        time.sleep(2)
                        continue
                    elif "503" in error_str:
                        await message.reply("⚠️ Máy chủ Gemini hiện đang quá tải. Bạn vui lòng thử lại sau vài giây hoặc dùng lệnh `!model` để đổi mô hình khác nhé!")
                        break
                    else:
                        await message.reply(f"❌ Đã xảy ra lỗi khi xử lý câu hỏi: {e}")
                        break

# ---------------------------------------------------------
# 5. Khởi Chạy
# ---------------------------------------------------------
if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    bot.run(DISCORD_TOKEN)
