import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message
from dotenv import load_dotenv

from database import get_db_pool
from llm_service import generate_sql

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Инициализация
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Пул соединений с БД (будет создан при старте)
db_pool = None

async def on_startup():
    global db_pool
    db_pool = await get_db_pool()
    logger.info("Database pool created")

async def on_shutdown():
    if db_pool:
        await db_pool.close()
        logger.info("Database pool closed")

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("Привет! Я бот аналитики. Спроси меня что-нибудь о видео, например: 'Сколько видео вышло в ноябре?'")

@dp.message(F.text)
async def handle_text(message: Message):
    user_query = message.text
    
    # 1) Отправляем запрос в LLM, чтобы получить SQL
    sql_query = await generate_sql(user_query)
    
    if not sql_query:
        await message.answer("0") # или сообщение об ошибке, но по ТЗ в ответе от бота ожидается число.
        return

    logger.info(f"User: {user_query} -> SQL: {sql_query}")

    # 2) Выполняем SQL
    try:
        async with db_pool.acquire() as conn:
            # fetchval возвращает первое значение первой строки
            result = await conn.fetchval(sql_query)
            
            # обработка NULL (если сумма пустая)
            if result is None:
                result = 0
            
            # форматируем, если нужно, но по ТЗ от бота надо вернуть "одно число"
            await message.answer(str(result))
            
    except Exception as e:
        logger.error(f"SQL Execution error: {e}")
        await message.answer("0") # в случае ошибки SQL (например, модель сгаллюцинировала синтаксис)

async def main():
    await on_startup()
    try:
        await dp.start_polling(bot)
    finally:
        await on_shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")