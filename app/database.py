import asyncio
from typing import Dict, List, Optional
from sqlalchemy import BigInteger, Column, Index, Integer, Numeric, String, Float, DateTime, ForeignKey, Boolean, select, func, update
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import relationship, sessionmaker
try:
    from sqlalchemy.ext.asyncio import async_sessionmaker
except ImportError:
    async_sessionmaker = sessionmaker
from datetime import datetime

from .config import DATABASE_URL

# Создание базового класса для моделей
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    username = Column(String)
    first_name = Column(String)
    last_name = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class Product(Base):
    __tablename__ = 'products'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String)
    category = Column(String, nullable=False)
    retail_price = Column(Float, nullable=False)
    wholesale_price = Column(Float)
    amount = Column(String) 
    image_url = Column(String)
    is_available = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)




class CartItem(Base):
    __tablename__ = 'cart_items'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"))
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False)
    product_name = Column(String(100)) 
    price = Column(Float, nullable=False) 
    quantity = Column(Integer, nullable=False, default=1)
    

    product = relationship("Product", lazy="joined")  

    def __repr__(self):
        return f"<CartItem(user_id={self.user_id}, product={self.product_name}, quantity={self.quantity})>"

class OrderItem(Base):
    __tablename__ = 'order_items'
    
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('orders.id'))
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False)
    product_name = Column(String(100)) 
    price = Column(Float, nullable=False) 
    quantity = Column(Integer, nullable=False, default=1)

class Order(Base):
    __tablename__ = 'orders'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    payment_id = Column(String)  # Telegram user_id обычно bigint
    amount = Column(Numeric(10, 2), nullable=False)  # Лучше для денег, чем Float
    customer_name = Column(String(100), nullable=False)  # Ограничение длины
    customer_phone = Column(String(20), nullable=False)  # + и цифры занимают место
    delivery_address = Column(String(200), nullable=False)
    delivery_time = Column(String(20))  # "morning", "afternoon" etc.
    status = Column(String(20), default='new', nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Добавьте индексы для часто запрашиваемых полей
    __table_args__ = (
        Index('ix_orders_user_id', 'user_id'),
        Index('ix_orders_status', 'status'),
    )
    
class Database:
    def __init__(self):
        # Убедимся, что URL правильный
        async_db_url = DATABASE_URL
        if async_db_url.startswith('sqlite:///'):
            async_db_url = async_db_url.replace('sqlite:///', 'sqlite+aiosqlite:///')
        
        # Для SQLite нужно добавить check_same_thread=False для асинхронной работы
        self.engine = create_async_engine(
            async_db_url,
            connect_args={"check_same_thread": False} if "sqlite" in async_db_url else {}
        )
        self.async_session = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
    async def init(self):
        """Инициализация базы данных"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    
    async def close(self):
        """Закрытие соединения с базой данных"""
        await self.engine.dispose()
    
    async def get_user(self, telegram_id: int):
        """Получение пользователя по telegram_id"""
        async with self.async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            return result.scalar_one_or_none()
    
    async def create_user(self, telegram_id: int, username: str = None, 
                         first_name: str = None, last_name: str = None):
        """Создание нового пользователя"""
        async with self.async_session() as session:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name
            )
            session.add(user)
            await session.commit()
            return user



    