import os
import asyncpg
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import asyncio

# .env faylidan o'zgaruvchilarni yuklash
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("APP_URL")  # Netlify frontend URL
DATABASE_URL = os.getenv("DATABASE_URL")  # Neon.tech PostgreSQL URL

# Telegram Bot va Dispatcher sozlanadi
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# FastAPI ilovasi (REST API uchun)
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ma'lumotlar bazasiga ulanish havzasi (pool)
async def init_db_pool():
    return await asyncpg.create_pool(DATABASE_URL)

# Bot start komandasi
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    # Foydalanuvchini bazaga qo'shish (agar yangi bo'lsa)
    pool = app.state.db_pool
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (telegram_id, username, full_name) 
            VALUES ($1, $2, $3)
            ON CONFLICT (telegram_id) DO NOTHING
        """, message.from_user.id, message.from_user.username, message.from_user.full_name)
    
    # Mini App tugmasi bilan javob
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="Mini Appni ochish", web_app=types.WebAppInfo(url=APP_URL))]
        ]
    )
    await message.answer(
        "Assalomu alaykum! Reklama Marketplace botiga xush kelibsiz",
        reply_markup=keyboard
    )

# REST API endpoint: barcha reklamalarni olish
@app.get("/api/ads")
async def get_ads():
    pool = app.state.db_pool
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, title, description, price FROM ads")
        return [dict(row) for row in rows]

# REST API endpoint: yangi buyurtma yaratish
@app.post("/api/orders")
async def create_order(order: dict):
    pool = app.state.db_pool
    async with pool.acquire() as conn:
        order_id = await conn.fetchval("""
            INSERT INTO orders (advertiser_id, business_id, amount, status)
            VALUES ($1, $2, $3, 'pending') RETURNING id
        """, order['advertiser_id'], order['business_id'], order['amount'])
        return {"id": order_id, "status": "created"}

# Asosiy ishga tushirish funksiyasi
async def main():
    # Ma'lumotlar bazasini ishga tushurish
    pool = await init_db_pool()
    app.state.db_pool = pool
    
    # Jadvallarni yaratish (agar mavjud bo'lmasa)
    # backend.py dagi jadvallar qismini BUNGA ALMASHTIRING:

async with pool.acquire() as conn:
    # 1. Avval users jadvalini yaratamiz (PRIMARY KEY bilan)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE NOT NULL,  -- UNIQUE va NOT NULL muhim!
            username TEXT,
            full_name TEXT,
            role TEXT DEFAULT 'user',
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
    
    # 2. Keyin ads jadvalini (to'g'ri FOREIGN KEY bilan)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS ads (
            id SERIAL PRIMARY KEY,
            title TEXT,
            description TEXT,
            price DECIMAL,
            owner_telegram_id BIGINT REFERENCES users(telegram_id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
    
    # 3. Orders jadvali
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            advertiser_telegram_id BIGINT REFERENCES users(telegram_id) ON DELETE CASCADE,
            business_telegram_id BIGINT REFERENCES users(telegram_id) ON DELETE CASCADE,
            amount DECIMAL,
            status TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """) 
    # Botni polling rejimida ishga tushurish (webhook emas, chunki Render free da webhook muammo)
    asyncio.create_task(dp.start_polling(bot))
    
    # FastAPI ni ishga tushurish
    config = uvicorn.Config(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":

    asyncio.run(main())
