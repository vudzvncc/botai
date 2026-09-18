import os
import threading
import discord
from discord.ext import commands
from google import genai
from dotenv import load_dotenv
from flask import Flask
import requests

# Tải cấu hình từ file .env
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# --- KHỞI TẠO FLASK WEB SERVER (Giúp giữ bot online 24/7) ---
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot Gemini Discord đang hoạt động trực tuyến!"

def run_flask():
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()


# --- KHỞI TẠO GEMINI CLIENT & DISCORD BOT ---
ai_client = genai.Client(api_key=GEMINI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

chat_sessions = {}   # { channel_id: chat_session }
channel_models = {}  # { channel_id: "model_name" }

DEFAULT_MODEL = "gemini-2.5-flash"

@bot.event
async def on_ready():
    print(f"✅ Bot đã đăng nhập thành công với tên: {bot.user}")

# --- CÁC LỆNH SỬ DỤNG THƯ VIỆN REQUESTS ---

@bot.command(name="dog")
async def get_random_dog(ctx):
    """Lấy ảnh chó ngẫu nhiên bằng cách gọi API bên ngoài thông qua thư viện requests."""
    try:
        # Gửi yêu cầu GET tới API hình ảnh cún cưng
        res = requests.get("https://dog.ceo/api/breeds/image/random")
        if res.status_code == 200:
            data = res.json()
            image_url = data.get("message")
            await ctx.reply(image_url)
        else:
            await ctx.reply("❌ Không thể lấy dữ liệu ảnh lúc này.")
    except Exception as e:
        await ctx.reply(f"❌ Đã xảy ra lỗi khi kết nối API: {e}")

@bot.command(name="crypto")
async def get_crypto_price(ctx, symbol: str = "bitcoin"):
    """Xem giá các đồng tiền điện tử (Ví dụ: !crypto bitcoin, !crypto ethereum)."""
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={symbol.lower()}&vs_currencies=usd"
        res = requests.get(url)
        data = res.json()

        if symbol.lower() in data:
            price = data[symbol.lower()]["usd"]
            await ctx.reply(f"💰 Giá của **{symbol.upper()}** hiện tại là: `${price:,.2f} USD`")
        else:
            await ctx.reply(f"❌ Không tìm thấy thông tin giá cho mã `{symbol}`.")
    except Exception as e:
        await ctx.reply(f"❌ Đã xảy ra lỗi khi tra cứu giá: {e}")

# --- CÁC LỆNH ĐIỀU KHIỂN BOT CỦA GEMINI ---

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

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Ưu tiên xử lý các lệnh bắt đầu bằng dấu !
    await bot.process_commands(message)

    is_mentioned = bot.user in message.mentions
    is_private = isinstance(message.channel, discord.DMChannel)

    if message.content.startswith(bot.command_prefix):
        return

    if is_mentioned or is_private:
        user_input = message.content.replace(f"<@{bot.user.id}>", "").strip()

        if not user_input:
            await message.channel.send("Bạn cần hỏi gì tôi thế?")
            return

        session_id = message.channel.id
        selected_model = channel_models.get(session_id, DEFAULT_MODEL)

        if session_id not in chat_sessions:
            chat_sessions[session_id] = ai_client.chats.create(model=selected_model)

        chat = chat_sessions[session_id]

        async with message.channel.typing():
            try:
                response = chat.send_message(user_input)
                reply_text = response.text

                if len(reply_text) <= 2000:
                    await message.reply(reply_text)
                else:
                    for i in range(0, len(reply_text), 1900):
                        await message.channel.send(reply_text[i:i + 1900])

            except Exception as e:
                await message.reply(f"❌ Đã xảy ra lỗi khi xử lý câu hỏi: {e}")

if __name__ == "__main__":
    keep_alive()
    bot.run(DISCORD_TOKEN)
