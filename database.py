from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean, ForeignKey
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()

class Master(Base):
    __tablename__ = 'masters'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True)
    username = Column(String)

class Client(Base):
    __tablename__ = 'clients'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    notes = Column(String) 

class Appointment(Base):
    __tablename__ = 'appointments'
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey('clients.id'), nullable=True)
    service = Column(String)
    price = Column(Float, default=0.0)
    is_day_off = Column(Boolean, default=False)
    appointment_date = Column(DateTime)
    telegram_id = Column(String) # Чтобы фильтровать данные конкретного мастера
    
    client = relationship("Client")
