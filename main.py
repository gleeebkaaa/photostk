import os
import logging
import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from config import BOT_TOKEN, ALLOWED_USERS, APARTMENTS, PHOTOS_DIR

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Создаем папку для фото
os.makedirs(PHOTOS_DIR, exist_ok=True)

# FSM для выбора квартиры
class UserStates(StatesGroup):
    waiting_for_apartment = State()
    waiting_for_download_date = State()
    waiting_for_download_apartment = State()

# Клавиатура с квартирами
def get_apartment_keyboard(apartments):
    rows = []
    for i in range(0, len(apartments), 5):
        rows.append([KeyboardButton(text=apt) for apt in apartments[i:i+5]])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, one_time_keyboard=True)

# Команда /start
@dp.message(F.text == "/start")
async def start(message: types.Message):
    logger.info(f"Пользователь {message.from_user.username} отправил /start")
    if not message.from_user.username or message.from_user.username not in ALLOWED_USERS:
        await message.answer("Вы не авторизованы.")
        return
    await message.answer("Добро пожаловать! Отправьте фото для сохранения.")

# Обработка фото (одиночное)
@dp.message(F.photo)
async def handle_single_photo(message: types.Message, state: FSMContext):
    logger.info(f"Получено фото от {message.from_user.username}")
    if not message.from_user.username or message.from_user.username not in ALLOWED_USERS:
        return

    data = await state.get_data()
    current_apartment = data.get("current_apartment")

    if current_apartment:
        logger.info(f"Фото добавляется в квартиру {current_apartment}")
        await save_photos_batch(message, state, current_apartment, [message.photo[-1].file_id])
        return

    logger.info("Обнаружено одиночное фото")
    await state.update_data(file_id=message.photo[-1].file_id)
    keyboard = get_apartment_keyboard(APARTMENTS)
    await message.answer("Выберите номер квартиры:", reply_markup=keyboard)
    await state.set_state(UserStates.waiting_for_apartment)

# Обработчик выбора квартиры
@dp.message(UserStates.waiting_for_apartment)
async def process_apartment(message: types.Message, state: FSMContext):
    logger.info(f"Пользователь выбрал квартиру: {message.text}")
    apartment = message.text.strip()
    if apartment not in APARTMENTS:
        logger.warning(f"Недопустимый номер квартиры: {apartment}")
        await message.answer("Пожалуйста, выберите номер из списка.")
        return

    data = await state.get_data()
    file_id = data.get("file_id")

    if not file_id:
        logger.warning("Нет file_id для сохранения")
        await message.answer("Ошибка: нет фото для сохранения.")
        await state.clear()
        return

    await save_photos_batch(message, state, apartment, [file_id])
    await message.answer(f"Фото сохранено в квартиру {apartment}.", reply_markup=types.ReplyKeyboardRemove())
    await state.update_data(current_apartment=apartment)
    await state.clear()

# Сохранение фото
async def save_photos_batch(message, state, apartment, file_ids):
    logger.info(f"Сохраняю {len(file_ids)} фото в квартиру {apartment}")
    current_date = datetime.now().strftime("%y-%m-%d")
    date_folder = os.path.join(PHOTOS_DIR, current_date)
    os.makedirs(date_folder, exist_ok=True)

    apartment_folder = os.path.join(date_folder, apartment)
    os.makedirs(apartment_folder, exist_ok=True)

    for idx, file_id in enumerate(file_ids):
        logger.debug(f"Сохраняю фото {idx+1}/{len(file_ids)}. File ID: {file_id}")
        try:
            file = await bot.get_file(file_id)
            file_path = os.path.join(apartment_folder, f"{file_id}.jpg")
            await bot.download_file(file.file_path, file_path)
        except Exception as e:
            logger.error(f"Ошибка при сохранении фото {file_id}: {e}", exc_info=True)
            await message.answer(f"Ошибка при сохранении фото: {e}")

# Команда /list
@dp.message(F.text == "/list")
async def list_photos(message: types.Message):
    if not message.from_user.username or message.from_user.username not in ALLOWED_USERS:
        return

    result = "📁 Структура сохраненных фото:\n"
    for date_folder in sorted(os.listdir(PHOTOS_DIR)):
        date_path = os.path.join(PHOTOS_DIR, date_folder)
        if os.path.isdir(date_path):
            result += f"\n📅 {date_folder}:\n"
            for apt in sorted(os.listdir(date_path)):
                apt_path = os.path.join(date_path, apt)
                if os.path.isdir(apt_path):
                    count = len(os.listdir(apt_path))
                    result += f"  🏠 {apt} ({count} фото)\n"
    await message.answer(result or "Нет данных.")

# Команда /download
@dp.message(F.text == "/download")
async def download_photos(message: types.Message, state: FSMContext):
    if not message.from_user.username or message.from_user.username not in ALLOWED_USERS:
        return

    if not os.path.exists(PHOTOS_DIR):
        await message.answer("Нет сохраненных фото.")
        return

    dates = sorted(os.listdir(PHOTOS_DIR))
    if not dates:
        await message.answer("Нет доступных дат.")
        return

    keyboard = InlineKeyboardBuilder()
    for date in dates:
        keyboard.add(InlineKeyboardButton(text=date, callback_data=f"date_{date}"))
    keyboard.adjust(2)
    await message.answer("Выберите дату:", reply_markup=keyboard.as_markup())
    await state.set_state(UserStates.waiting_for_download_date)

# Callback выбора даты
@dp.callback_query(UserStates.waiting_for_download_date)
async def choose_apartment(callback: types.CallbackQuery, state: FSMContext):
    date = callback.data.split("_")[1]
    await state.update_data(selected_date=date)

    date_path = os.path.join(PHOTOS_DIR, date)
    apartments = sorted(os.listdir(date_path))
    if not apartments:
        await callback.message.edit_text("Нет квартир за эту дату.")
        return

    keyboard = InlineKeyboardBuilder()
    for apt in apartments:
        keyboard.add(InlineKeyboardButton(text=apt, callback_data=f"apt_{apt}"))
    keyboard.adjust(2)
    await callback.message.edit_text("Выберите квартиру:", reply_markup=keyboard.as_markup())
    await state.set_state(UserStates.waiting_for_download_apartment)

# Callback выбора квартиры
@dp.callback_query(UserStates.waiting_for_download_apartment)
async def send_photos(callback: types.CallbackQuery, state: FSMContext):
    apartment = callback.data.split("_")[1]
    data = await state.get_data()
    date = data.get("selected_date")

    if not date:
        await callback.message.answer("Ошибка: дата не выбрана.")
        return

    apt_path = os.path.join(PHOTOS_DIR, date, apartment)
    if not os.path.exists(apt_path):
        await callback.message.answer("Квартира не найдена.")
        return

    archive_path = f"{apt_path}.zip"
    shutil.make_archive(apt_path, 'zip', apt_path)
    await callback.message.answer_document(types.FSInputFile(archive_path))
    os.remove(archive_path)
    await state.clear()

# Запуск бота
if __name__ == "__main__":
    import asyncio
    logger.info("Запуск бота...")
    asyncio.run(dp.start_polling(bot))
