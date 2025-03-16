import os
import sqlite3
import pandas as pd
import dotenv
import logging
import requests
import html
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile
from aiogram.enums import ParseMode
from aiogram.types import Message
from aiogram.utils.markdown import hbold
from aiogram import Router


dotenv.load_dotenv()

logging.basicConfig(level=logging.INFO)

TELEGRAM_BOT_API = os.getenv('TELEGRAM_BOT_API')
bot = Bot(token=TELEGRAM_BOT_API)
dp = Dispatcher()
router = Router()

upload_button = KeyboardButton(text="Загрузить файл")
keyboard = ReplyKeyboardMarkup(keyboard=[[upload_button]], resize_keyboard=True)

def connect_db():
    return sqlite3.connect('items_info.db')

def create_table():
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS products (
                        title TEXT,
                        url TEXT,
                        xpath TEXT
                    )''')
    conn.commit()
    conn.close()

@router.message(Command("start"))
async def start_command(message: Message):
    await message.answer(
        f"Привет,  {(message.from_user.first_name)}!\n"
        "Отправь файл Excel с данными, и я обработаю его. "
        "Нажми кнопку ниже, чтобы загрузить файл.", 
        reply_markup=keyboard
    )

@router.message(F.text == "Загрузить файл")
async def upload_file_request(message: Message):
    await message.answer("Пришли мне Excel-файл с данными о зюзюбликах 📂")

@router.message(F.document)
async def handle_file(message: Message, bot: Bot):
    document = message.document
    file_path = f"{document.file_name}"

    # Скачиваем файл
    file = await bot.get_file(document.file_id)
    await bot.download_file(file.file_path, file_path)

    try:
        df = pd.read_excel(file_path)
        if not {"title", "url", "xpath"}.issubset(df.columns):
            await message.answer("Ошибка! Файл должен содержать колонки: title, url, xpath")
            return

        conn = connect_db()
        cursor = conn.cursor()
        for _, row in df.iterrows():
            cursor.execute("INSERT INTO products (title, url, xpath) VALUES (?, ?, ?)", 
                           (row["title"], row["url"], row["xpath"]))
        conn.commit()
        conn.close()

        response_text = f"{hbold('Данные из файла:')}\n\n"
        for _, row in df.iterrows():
            response_text += f"🔹 <b>{row['title']}</b>\n🌍 {row['url']}\n📌 XPath: {row['xpath']}\n\n"

        await message.answer(response_text, parse_mode=ParseMode.HTML)

    except Exception as e:
        await message.answer(f"Ошибка обработки файла: {e}")

def main():
    create_table()
    dp.include_router(router)
    dp.run_polling(bot)

if __name__ == "__main__":
    main()