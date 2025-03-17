import os
import uuid
import sqlite3
import logging
import re
import pandas as pd
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, Router
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

load_dotenv()
router = Router()

TELEGRAM_BOT_API = os.getenv("TELEGRAM_BOT_API")
DATABASE_PATH = os.getenv("PATH_TO_DB")
UPLOAD_FOLDER = os.getenv("PATH_TO_UPLOADS")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TELEGRAM_BOT_API)
dp = Dispatcher()

def connect_db():
    return sqlite3.connect(DATABASE_PATH)

def create_table():
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            url TEXT,
            xpath TEXT
        )
    ''')
    conn.commit()
    conn.close()

create_table()

@router.message(Command("start"))
async def start_handler(message: types.Message):
    """Приветствие + кнопка загрузки файла"""
    greeting_message = (
        "👋 <b>Привет! Я бот для парсинга цен с сайтов.</b>\n\n"
        "📄 <b>Как я работаю?</b>\n"
        "Вы отправляете <u>Excel-файл</u> с товарами, а я собираю цены с сайтов.\n\n"
        "✅ <b>Какой нужен файл?</b>\n"
        "Файл должен содержать 3 колонки:\n"
        "🔹 <b>title</b> — название товара\n"
        "🔹 <b>url</b> — ссылка на товар\n"
        "🔹 <b>xpath</b> — путь к цене\n\n"
        "📩 <b>Отправьте файл, и я его обработаю!</b>"
    )
    
    # Создаём постоянно видимую кнопку
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📤 Загрузить файл")]],
        resize_keyboard=True
    )
    
    await message.answer(greeting_message, parse_mode="HTML", reply_markup=keyboard)

@router.message(lambda message: message.text == "📤 Загрузить файл")
async def request_file(message: types.Message):
    """Сообщение с просьбой отправить файл"""
    await message.answer("📁 <b>Прикрепите Excel-файл с данными.</b>", parse_mode="HTML")

@router.message(lambda message: message.document)
async def handle_file(message: types.Message):
    """Обработка загруженного файла"""
    file_id = message.document.file_id
    file_info = await bot.get_file(file_id)
    file_path = file_info.file_path
    unique_filename = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}.xlsx")

    await bot.download_file(file_path, unique_filename)

    try:
        df = pd.read_excel(unique_filename)

        # Проверяем наличие нужных колонок
        if not all(col in df.columns for col in ["title", "url", "xpath"]):
            os.remove(unique_filename)  # Удаляем невалидный файл
            await message.answer(
                "❌ <b>Ошибка!</b> В файле должны быть колонки:\n"
                "🔹 title (название товара)\n"
                "🔹 url (ссылка на товар)\n"
                "🔹 xpath (путь к цене)\n\n"
                "📄 Проверьте файл и загрузите снова.", 
                parse_mode="HTML"
            )
            return  # Прекращаем выполнение кода

        # Если файл валидный, продолжаем обработку
        prices = []
        for _, row in df.iterrows():
            price = fetch_price(row["url"], row["xpath"])
            prices.append(price)

        # Округляем среднюю цену до двух знаков
        avg_price = round(sum(prices) / len(prices), 2) if prices else 0.0

        # Добавляем колонку с ценами
        df["extracted_price"] = prices

        # Форматируем вывод
        df_text = ""
        for _, row in df.iterrows():
            df_text += f"📌 <b>{row['title']}</b>\n"
            df_text += f"🔗 <a href='{row['url']}'>Ссылка на товар</a>\n"
            df_text += f"💰 Цена: <b>{row['extracted_price']} ₽</b>\n\n"

        # Сохраняем данные в БД
        conn = connect_db()
        cursor = conn.cursor()
        for _, row in df.iterrows():
            cursor.execute("INSERT INTO items (title, url, xpath) VALUES (?, ?, ?)", (row["title"], row["url"], row["xpath"]))
        conn.commit()
        conn.close()

        # Формируем красивое сообщение
        response_text = (
            f"✅ <b>Файл обработан!</b>\n"
            f"📊 <i>Средняя цена: {avg_price} ₽</i>\n\n"
            f"{df_text}"
        )

        await message.answer(response_text, parse_mode="HTML")

    except Exception:
        os.remove(unique_filename)  # Удаляем файл, если произошла ошибка
        await message.answer("❌ <b>Ошибка обработки файла!</b> Проверьте формат и попробуйте снова.", parse_mode="HTML")

def fetch_price(url, xpath):
    """Функция парсинга цены"""
    options = Options()
    options.add_argument("--headless")
    service = Service("/opt/homebrew/bin/chromedriver")
    driver = webdriver.Chrome(service=service, options=options)
    driver.get(url)
    
    try:
        element = driver.find_element(By.XPATH, xpath)
        price_text = element.text

        # Извлекаем только число (с запятой или точкой)
        price_match = re.search(r'\d+[\.,]?\d*', price_text.replace(' ', ''))
        price = float(price_match.group()) if price_match else 0.0
    except Exception:
        price = 0.0
    finally:
        driver.quit()
    return price

dp.include_router(router)

dp.run_polling(bot)
