import os
import discord
from discord.ext import commands
from google import genai
from dotenv import load_dotenv

# Tải cấu hình từ file .env
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Khởi tạo Gemini Client
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# Khởi tạo Discord Bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Bộ nhớ lưu trữ phiên chat và cấu hình cho từng kênh
chat_sessions = {}  # { channel_id: chat_session }
channel_models = {}  # { channel_id: "model_name" }

# Mô hình Gemini mặc định
DEFAULT_MODEL = "gemini-2.5-flash"

@bot.event
async def on_ready():
    print(f"Bot đã đăng nhập thành công với tên: {bot.user}")

@bot.command(name="model")
async def change_or_show_model(ctx, new_model: str = None):
    """
    Xem hoặc thay đổi mô hình Gemini cho kênh hiện tại.
    Cú pháp:
      !model -> Xem model hiện tại
      !model gemini-2.5-pro -> Đổi sang model mới
    """
    channel_id = ctx.channel.id

    # Nếu người dùng không truyền tên model mới -> Hiển thị model hiện tại
    if new_model is None:
        current_model = channel_models.get(channel_id, DEFAULT_MODEL)
        await ctx.reply(f"🤖 Mô hình Gemini hiện tại của kênh này là: `{current_model}`")
        return

    # Nếu người dùng truyền tên model mới -> Cập nhật và xóa phiên chat cũ
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
    # Tránh bot tự trả lời chính nó
    if message.author == bot.user:
        return

    # Lắng nghe các lệnh có tiền tố (!) trước
    await bot.process_commands(message)

    # Kiểm tra xem bot có được tag tên hoặc người dùng nhắn qua DM không
    is_mentioned = bot.user in message.mentions
    is_private = isinstance(message.channel, discord.DMChannel)

    # Nếu tin nhắn là một lệnh (bắt đầu bằng !), bỏ qua không xử lý chat AI
    if message.content.startswith(bot.command_prefix):
        return

    if is_mentioned or is_private:
        # Lấy nội dung tin nhắn và xóa phần tag bot (@Bot)
        user_input = message.content.replace(f"<@{bot.user.id}>", "").strip()

        if not user_input:
            await message.channel.send("Bạn cần hỏi gì tôi thế?")
            return

        session_id = message.channel.id
        selected_model = channel_models.get(session_id, DEFAULT_MODEL)

        # Khởi tạo phiên trò chuyện mới nếu chưa có
        if session_id not in chat_sessions:
            chat_sessions[session_id] = ai_client.chats.create(model=selected_model)

        chat = chat_sessions[session_id]

        async with message.channel.typing():
            try:
                # Gửi câu hỏi tới Gemini
                response = chat.send_message(user_input)
                reply_text = response.text

                # Discord giới hạn 2000 ký tự mỗi tin nhắn
                if len(reply_text) <= 2000:
                    await message.reply(reply_text)
                else:
                    # Chia nhỏ tin nhắn nếu dài hơn 2000 ký tự
                    for i in range(0, len(reply_text), 1900):
                        await message.channel.send(reply_text[i:i + 1900])

            except Exception as e:
                await message.reply(f"❌ Đã xảy ra lỗi khi xử lý câu hỏi: {e}")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
