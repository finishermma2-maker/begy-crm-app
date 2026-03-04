# ПЕРЕД ЗАПУСКОМ ОБНОВИТЕ PIP И ПРИНУДИТЕЛЬНО ОБНОВИТЕ БИБЛИОТЕКИ:
# 1. python -m pip install --upgrade pip
# 2. python -m pip install --upgrade aiogram aiohttp fastapi uvicorn sqlalchemy pydantic --only-binary :all:

import asyncio
from datetime import datetime, date
from contextlib import asynccontextmanager
from typing import Optional, List

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base, Master, Client, Appointment

# === КОНФИГУРАЦИЯ ===
TOKEN = "8624226286:AAECzu8_BTLj2IcZbP8isJDwH8koF9P9Vt0"
APP_URL = "https://finishermma2-maker.github.io/my-bot-app/"

# === БАЗА ДАННЫХ (SQLite) ===

engine = create_engine('sqlite:///hairdresser_crm.db')
Session = sessionmaker(bind=engine)
Base.metadata.create_all(engine)

# === ТЕЛЕГРАМ БОТ ===
bot = Bot(token=TOKEN)
dp = Dispatcher()

def get_main_keyboard():
    kb = [[KeyboardButton(text="📱 Открыть CRM", web_app=WebAppInfo(url=APP_URL))]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
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
    service: Optional[str] = "-"
    price: Optional[float] = 0.0
    notes: Optional[str] = ""
    telegram_id: Optional[str] = "unknown"
    isDayOff: Optional[bool] = False

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Бот запущен и сервер API активен...")
    polling_task = asyncio.create_task(dp.start_polling(bot))
    yield
    polling_task.cancel()
    await bot.session.close()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- НОВЫЙ ЭНДПОИНТ: ЗАГРУЗКА ВСЕХ ДАННЫХ ---
@app.get("/api/sync/{tg_id}")
async def sync_data(tg_id: str):
    db_session = Session()
    try:
        # Получаем все записи мастера, сортируем по дате
        apps = db_session.query(Appointment).filter_by(telegram_id=tg_id).order_by(Appointment.appointment_date).all()
        
        result = {}
        for a in apps:
            d_str = a.appointment_date.strftime("%Y-%m-%d")
            t_str = a.appointment_date.strftime("%H:%M") if not a.is_day_off else "-"
            
            if d_str not in result:
                result[d_str] = []
            
            # Ищем заметку клиента, если это не выходной
            client_notes = a.client.notes if a.client else (a.service if a.is_day_off else "")
            client_name = a.client.name if a.client else "Выходной"

            result[d_str].append({
                "id": a.id, # Добавляем ID для возможности удаления
                "date": d_str,
                "time": t_str,
                "name": client_name,
                "service": a.service,
                "price": a.price,
                "notes": client_notes,
                "isDayOff": a.is_day_off
            })
        return result
    except Exception as e:
        print(f"Ошибка синхронизации: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db_session.close()

# --- НОВЫЙ ЭНДПОИНТ: УДАЛЕНИЕ ЗАПИСИ ---
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
                client = Client(name=payload.name, notes=payload.notes)
                db_session.add(client)
                db_session.commit()
            else:
                client.notes = payload.notes
            
            new_appt = Appointment(
                client_id=client.id, 
                service=payload.service, 
                price=payload.price, 
                is_day_off=False, 
                appointment_date=appt_dt,
                telegram_id=payload.telegram_id
            )
            db_session.add(new_appt)
            msg_text = (f"✅ <b>Новая запись!</b>\n\n👤 {payload.name}\n"
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

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)