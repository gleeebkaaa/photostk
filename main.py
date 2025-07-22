import os
import logging
import requests
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from config import TELEGRAM_TOKEN, GITHUB_TOKEN, REPO_OWNER, REPO_NAME, ALLOWED_USERS_FILE

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка разрешенных пользователей
def load_allowed_users():
    if not os.path.exists(ALLOWED_USERS_FILE):
        return set()
    with open(ALLOWED_USERS_FILE, 'r') as f:
        return set(line.strip().lower() for line in f if line.strip())

allowed_users = load_allowed_users()

# Загрузка файла в GitHub
def upload_to_github(file_path, file_name, date_str):
    url = f"https://api.github.com/repos/ {REPO_OWNER}/{REPO_NAME}/contents/{date_str}/{file_name}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Content-Type": "application/json"
    }
    
    with open(file_path, "rb") as f:
        content = f.read()
    
    data = {
        "message": f"Upload {file_name}",
        "content": content.hex()
    }
    
    response = requests.put(url, headers=headers, json=data)
    if response.status_code == 201:
        return f"https://github.com/ {REPO_OWNER}/{REPO_NAME}/blob/main/{date_str}/{file_name}"
    else:
        logger.error(f"GitHub API error: {response.text}")
        return None

# Обработка фото
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.username.lower() not in allowed_users:
        await update.message.reply_text("❌ У вас нет прав для загрузки фото.")
        return

    try:
        date_str = datetime.now().strftime("%Y-%m-%d")
        photo = update.message.photo[-1]  # Берем фото максимального размера
        file_id = photo.file_id
        file_name = f"{file_id}.jpg"
        
        # Скачиваем фото
        file = await context.bot.get_file(file_id)
        local_path = os.path.join("temp", file_name)
        os.makedirs("temp", exist_ok=True)
        await file.download_to_drive(local_path)
        
        # Загружаем на GitHub
        logger.info(f"Загрузка файла в GitHub: {date_str}/{file_name}")
        link = upload_to_github(local_path, file_name, date_str)
        os.remove(local_path)  # Удаляем временный файл
        
        if link:
            await update.message.reply_text(f"✅ Фото загружено: [Ссылка на GitHub]({link})")
        else:
            await update.message.reply_text("❌ Ошибка при загрузке на GitHub.")
    except Exception as e:
        logger.error(f"Ошибка обработки фото: {e}")
        await update.message.reply_text("❌ Произошла ошибка.")

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Отправьте фото для загрузки.")

# Основная функция
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    logger.info("Бот запущен...")
    app.run_polling()

if __name__ == '__main__':
    main()
