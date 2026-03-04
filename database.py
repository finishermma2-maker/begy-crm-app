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
    phone = Column(String, nullable=True)
    notes = Column(String)

class Appointment(Base):
    __tablename__ = 'appointments'
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey('clients.id'), nullable=True)
    service = Column(String)
    price = Column(Float, default=0.0)
    is_day_off = Column(Boolean, default=False)
    appointment_date = Column(DateTime)
    telegram_id = Column(String)
    
    client = relationship("Client")
    photos = relationship("Photo", back_populates="appointment")

class Photo(Base):
    __tablename__ = 'photos'
    id = Column(Integer, primary_key=True)
    appointment_id = Column(Integer, ForeignKey('appointments.id'), nullable=True)
    client_name = Column(String)
    telegram_file_id = Column(String)
    telegram_id = Column(String)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    appointment = relationship("Appointment", back_populates="photos")
