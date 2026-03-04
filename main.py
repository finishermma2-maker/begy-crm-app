# ПЕРЕД ЗАПУСКОМ ОБНОВИТЕ PIP И ПРИНУДИТЕЛЬНО ОБНОВИТЕ БИБЛИОТЕКИ:
# 1. python -m pip install --upgrade pip
# 2. python -m pip install --upgrade aiogram aiohttp fastapi uvicorn sqlalchemy pydantic --only-binary :all:

import asyncio
import base64
import io
from datetime import datetime, date
from contextlib import asynccontextmanager
from typing import Optional, List

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, BufferedInputFile

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from database import Base, Master, Client, Appointment, Photo

# === КОНФИГУРАЦИЯ ===
TOKEN = "8624226286:AAECzu8_BTLj2IcZbP8isJDwH8koF9P9Vt0"
APP_URL = "https://begy-crm-bot.onrender.com"

# Telegram chat для хранения фото (ID чата куда бот будет слать фото)
# Используем чат самого мастера — фото будут приходить ему в личку
PHOTO_STORAGE_CHAT = None  # Будет установлен при первом /start

# === БАЗА ДАННЫХ (SQLite) ===

engine = create_engine('sqlite:///hairdresser_crm.db')
Session = sessionmaker(bind=engine)
Base.metadata.create_all(engine)

try:
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE clients ADD COLUMN client_tg VARCHAR;"))
except Exception:
    pass

# === ТЕЛЕГРАМ БОТ ===
bot = Bot(token=TOKEN)
dp = Dispatcher()

def get_main_keyboard():
    # Отправляем Inline кнопку, так как она надежнее отображается на телефонах в новых чатах
    kb = [[InlineKeyboardButton(text="📱 Открыть CRM", web_app=WebAppInfo(url=APP_URL))]]
    return InlineKeyboardMarkup(inline_keyboard=kb)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    global PHOTO_STORAGE_CHAT
    PHOTO_STORAGE_CHAT = message.chat.id
    
    db_session = Session()
    try:
        master = db_session.query(Master).filter_by(telegram_id=str(message.from_user.id)).first()
        if not master:
            new_master = Master(telegram_id=str(message.from_user.id), username=message.from_user.username)
            db_session.add(new_master)
            db_session.commit()
    finally:
        db_session.close()
    await message.answer("Добро пожаловать в BEGY CRM! ✂️\nВсе ваши записи и доходы теперь под контролем.", reply_markup=get_main_keyboard())

# === API СЕРВЕР (FastAPI) ===
class AppointmentPayload(BaseModel):
    date: str
    time: Optional[str] = "-"
    name: Optional[str] = "Выходной"
    phone: Optional[str] = ""
    client_tg: Optional[str] = ""
    service: Optional[str] = "-"
    price: Optional[float] = 0.0
    notes: Optional[str] = ""
    telegram_id: Optional[str] = "unknown"
    isDayOff: Optional[bool] = False

class PhotoPayload(BaseModel):
    image_base64: str
    client_name: str
    telegram_id: str
    description: Optional[str] = ""

async def start_bot():
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except Exception as e:
        print(f"Ошибка polling: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Бот запущен и сервер API активен...")
    polling_task = asyncio.create_task(start_bot())
    yield
    polling_task.cancel()
    await bot.session.close()

app = FastAPI(lifespan=lifespan)

# --- ОТДАЧА ФРОНТЕНДА ---
@app.get("/")
async def serve_index():
    return FileResponse("index.html")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ЗАГРУЗКА ВСЕХ ДАННЫХ ---
@app.get("/api/sync/{tg_id}")
async def sync_data(tg_id: str):
    db_session = Session()
    try:
        apps = db_session.query(Appointment).filter_by(telegram_id=tg_id).order_by(Appointment.appointment_date).all()
        
        result = {}
        for a in apps:
            d_str = a.appointment_date.strftime("%Y-%m-%d")
            t_str = a.appointment_date.strftime("%H:%M") if not a.is_day_off else "-"
            
            if d_str not in result:
                result[d_str] = []
            
            client_name = a.client.name if a.client else "Выходной"
            client_phone = a.client.phone if a.client else ""
            client_tg_val = a.client.client_tg if a.client and hasattr(a.client, 'client_tg') else ""

            result[d_str].append({
                "id": a.id,
                "date": d_str,
                "time": t_str,
                "name": client_name,
                "phone": client_phone,
                "client_tg": client_tg_val,
                "service": a.service,
                "price": a.price,
                "notes": "",
                "isDayOff": a.is_day_off
            })
        return result
    except Exception as e:
        print(f"Ошибка синхронизации: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db_session.close()

# --- УДАЛЕНИЕ ЗАПИСИ ---
@app.delete("/api/appointments/{app_id}")
async def delete_appointment(app_id: int):
    db_session = Session()
    try:
        app_to_del = db_session.query(Appointment).get(app_id)
        if app_to_del:
            db_session.delete(app_to_del)
            db_session.commit()
            return {"status": "deleted"}
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        db_session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db_session.close()

# --- СОЗДАНИЕ ЗАПИСИ ---
@app.post("/api/appointments")
async def create_appointment(payload: AppointmentPayload):
    db_session = Session()
    try:
        if payload.isDayOff:
            appt_dt = datetime.strptime(payload.date, "%Y-%m-%d")
            new_appt = Appointment(
                service="ВЫХОДНОЙ", 
                price=0.0, 
                is_day_off=True, 
                appointment_date=appt_dt,
                telegram_id=payload.telegram_id
            )
            db_session.add(new_appt)
            msg_text = f"🏖 <b>Выходной установлен!</b>\n📅 {payload.date}\n📝 {payload.notes}"
        else:
            appt_dt = datetime.strptime(f"{payload.date} {payload.time}", "%Y-%m-%d %H:%M")
            client = db_session.query(Client).filter_by(name=payload.name).first()
            if not client:
                client = Client(name=payload.name, phone=payload.phone, notes=payload.notes)
                if hasattr(client, 'client_tg'):
                    client.client_tg = payload.client_tg
                db_session.add(client)
                db_session.commit()
            else:
                if payload.phone:
                    client.phone = payload.phone
                if payload.client_tg and hasattr(client, 'client_tg'):
                    client.client_tg = payload.client_tg
            
            new_appt = Appointment(
                client_id=client.id, 
                service=payload.service, 
                price=payload.price, 
                is_day_off=False, 
                appointment_date=appt_dt,
                telegram_id=payload.telegram_id
            )
            db_session.add(new_appt)
            phone_str = f"\n📞 {payload.phone}" if payload.phone else ""
            tg_str = f" / ✈️ {payload.client_tg}" if hasattr(payload, 'client_tg') and payload.client_tg else ""
            msg_text = (f"✅ <b>Новая запись!</b>\n\n👤 {payload.name}{phone_str}{tg_str}\n"
                        f"⏰ {payload.time}\n💇‍♀️ {payload.service}\n💰 {payload.price} ₽")

        db_session.commit()
        if payload.telegram_id and payload.telegram_id != "unknown":
            await bot.send_message(chat_id=payload.telegram_id, text=msg_text, parse_mode="HTML")
        return {"status": "success"}
    except Exception as e:
        db_session.rollback()
        print(f"Ошибка сохранения: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db_session.close()

# --- ЗАГРУЗКА ФОТО (через Telegram как хранилище) ---
@app.post("/api/photos")
async def upload_photo(payload: PhotoPayload):
    try:
        # Декодируем base64 в байты
        image_data = base64.b64decode(payload.image_base64.split(",")[-1])
        
        # Отправляем фото в Telegram (боту самому себе или мастеру)
        chat_id = int(payload.telegram_id) if payload.telegram_id != "unknown" else PHOTO_STORAGE_CHAT
        if not chat_id:
            raise HTTPException(status_code=400, detail="No chat ID available")
        
        photo_file = BufferedInputFile(image_data, filename="photo.jpg")
        caption = f"📸 {payload.client_name}"
        if payload.description:
            caption += f"\n{payload.description}"
        
        result = await bot.send_photo(
            chat_id=chat_id,
            photo=photo_file,
            caption=caption
        )
        
        # Сохраняем file_id в базу
        file_id = result.photo[-1].file_id  # Берём самое большое разрешение
        
        db_session = Session()
        try:
            new_photo = Photo(
                client_name=payload.client_name,
                telegram_file_id=file_id,
                telegram_id=payload.telegram_id,
                description=payload.description
            )
            db_session.add(new_photo)
            db_session.commit()
            return {"status": "success", "file_id": file_id}
        finally:
            db_session.close()
            
    except Exception as e:
        print(f"Ошибка загрузки фото: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- ПОЛУЧИТЬ ФОТО КЛИЕНТА ---
@app.get("/api/photos/{client_name}")
async def get_client_photos(client_name: str, telegram_id: str = "unknown"):
    db_session = Session()
    try:
        photos = db_session.query(Photo).filter_by(
            client_name=client_name, 
            telegram_id=telegram_id
        ).order_by(Photo.created_at.desc()).all()
        
        result = []
        for p in photos:
            # Получаем URL фото через Telegram API
            try:
                file = await bot.get_file(p.telegram_file_id)
                file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file.file_path}"
                result.append({
                    "id": p.id,
                    "url": file_url,
                    "description": p.description or "",
                    "date": p.created_at.strftime("%d.%m.%Y") if p.created_at else ""
                })
            except Exception:
                continue
        
        return result
    except Exception as e:
        print(f"Ошибка получения фото: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db_session.close()

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
