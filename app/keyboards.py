from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove
)
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import List

from sqlalchemy import func, select

from app.database import CartItem, Product
from .config import DELIVERY_INTERVALS
import time


current_quantities = {}
PRODUCTS_PER_PAGE = 10

def get_main_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="📋 Каталог", callback_data="catalog"),
        InlineKeyboardButton(text='🛒 Корзина', callback_data='view_cart'),
        InlineKeyboardButton(text='📦 Мой заказы',callback_data='my_orders'),
        InlineKeyboardButton(text="📞 Контакты", callback_data="contacts"),
        InlineKeyboardButton(text="ℹ️ О сервисе", callback_data="about")
    )
    builder.adjust(1,1,1,2)  
    return builder.as_markup()


def get_catalog_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора категорий"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🍎 Фрукты", callback_data="category_fruits"),
        InlineKeyboardButton(text="🥕 Овощи", callback_data="category_vegetables")
    )
    builder.row(
        InlineKeyboardButton(text="🧃 Напитки", callback_data="category_drinks"),
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")
    )
    return builder.as_markup()

async def get_products_keyboard(category: str, session: AsyncSession, page: int = 0) -> InlineKeyboardMarkup:
    items_per_page = 5
    builder = InlineKeyboardBuilder()
    
    products = await session.execute(
        select(Product)
        .where(Product.category == category)
        .order_by(Product.name)
        .offset(page * items_per_page)
        .limit(items_per_page)
    )
    products = products.scalars().all()
    
    for product in products:
        builder.row(
            InlineKeyboardButton(
                text=f"{product.name} | {product.retail_price}₽ ",
                callback_data=f"product_{product.id}"
            )
        )
    
    total = await session.scalar(
        select(func.count()).where(Product.category == category)
    )
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=f"prev_{category}_{page-1}"  # Формируем callback_data
            )
        )
    
    nav_buttons.append(
        InlineKeyboardButton(text="◀️ в категории", callback_data="back_to_categories")
    )
    
    if (page + 1) * items_per_page < total:
        nav_buttons.append(
            InlineKeyboardButton(
                text="Вперёд ➡️",
                callback_data=f"next_{category}_{page+1}"  # Формируем callback_data
            )
        )
    
    if nav_buttons:
        builder.row(*nav_buttons)
    
    return builder.as_markup()

async def get_product_detail_keyboard(product_id: int, user_id: int, session: AsyncSession, category: str) -> InlineKeyboardMarkup:
    """Клавиатура для детального просмотра товара"""
    builder = InlineKeyboardBuilder()
    
    # Проверяем, есть ли товар в корзине
    in_cart = await session.execute(
        select(CartItem)
        .where(
            (CartItem.user_id == user_id) & 
            (CartItem.product_id == product_id)
        )
    )
    in_cart = in_cart.scalar_one_or_none()
    
    cart_button_text = "🛒 В корзине" if in_cart else "🛒 Добавить в корзину"
    
    builder.row(
        InlineKeyboardButton(text=cart_button_text, callback_data=f"add_to_cart_{product_id}"),
        InlineKeyboardButton(text="📦 Корзина", callback_data="view_cart"),
        InlineKeyboardButton(text="◀️ Назад", callback_data=f"back_to_products_{category}")
    )
    builder.adjust(2,1)
    return builder.as_markup()


def get_cart_keyboard(cart_items: list) -> InlineKeyboardMarkup:
    """Клавиатура корзины с реальными ID товаров"""
    builder = InlineKeyboardBuilder()
    
    # Добавляем товары в корзине
    for cart_item, product in cart_items:
        builder.row(
            InlineKeyboardButton(
                text=f"❌ Удалить {product.name} ({cart_item.quantity} кг)",
                callback_data=f"remove_from_cart_{product.id}"
            )
        )
    
    # Кнопки управления корзиной
    builder.row(
        InlineKeyboardButton(text="💳 Оформить заказ", callback_data="checkout"),
        InlineKeyboardButton(text="🗑 Очистить корзину", callback_data="clear_cart")
    )
    
    builder.row(
        InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_main")
    )
    
    return builder.as_markup()

def get_phone_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура для ввода телефона"""
    buttons = [
        [KeyboardButton(text="📱 Отправить номер телефона", request_contact=True)]
    ]
    keyboard = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, one_time_keyboard=True)
    return keyboard

def get_location_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура для отправки локации"""
    buttons = [
        [KeyboardButton(text="📍 Отправить адрес", request_location=True)],
        [KeyboardButton(text="✍️ Ввести адрес вручную")]
    ]
    keyboard = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, one_time_keyboard=True)
    return keyboard


def get_back_to_start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
        ]
    )

def get_contact_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📞 Позвонить", url="https://t.me/share/url?url=tel:+1234567890")],
            [InlineKeyboardButton(text="💬 Написать в Telegram", url="https://t.me/support")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]
        ]
    )

def get_about_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Условия доставки", callback_data="delivery_info")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]
        ]
        
    
    )