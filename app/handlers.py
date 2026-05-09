from datetime import datetime
import re
from typing import Dict,List
from aiogram import Bot, Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums import ParseMode
from aiogram.types import FSInputFile,InputMediaPhoto
from aiogram.exceptions import TelegramBadRequest
from pathlib import Path
from sqlalchemy import and_, case, delete, func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.types import Message, CallbackQuery, Contact, Location



from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButton,
    )
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.database import CartItem, Database, Order, OrderItem, Product
from app.keyboards import (
    get_about_keyboard,
    get_contact_keyboard,
    get_main_keyboard,
    get_catalog_keyboard,
    get_products_keyboard,
    get_product_detail_keyboard,
    get_cart_keyboard,
    get_phone_keyboard,
    get_location_keyboard
)
from app.payment import PaymentSystem
from .config import ADMIN_IDS, PAYMENT_TOKEN, ITEMS_PER_PAGE

# Создаем роутер
router = Router()

payment_system = PaymentSystem(
    shop_id="1103478",
        secret_key="live_rn2lnHbd5Sh6JnMgynZ3NeZkvPYtQvL_mcnSYhARJFo"
)


# Состояния FSM для оформления заказа
class OrderStates(StatesGroup):
    WAITING_NAME = State()
    WAITING_PHONE = State()
    WAITING_ADDRESS = State()
    WAITING_DELIVERY_TIME = State()


current_quantities: Dict[int, Dict[int, int]] = {}
PRODUCTS_PER_PAGE = 10

# Команда /start
@router.message(Command("start"))
async def cmd_start(message: Message, db: Database):
    """Обработчик команды /start с отправкой фото"""
    try:
        user_id = message.from_user.id
        username = message.from_user.username or ""
        first_name = message.from_user.first_name or "Пользователь"
        last_name = message.from_user.last_name or ""
        
        user = await db.get_user(user_id)
        if not user:
            user = await db.create_user(user_id, username, first_name, last_name)

        welcome_text = (
            f"👋 Привет, {first_name}!\n\n"
            "Добро пожаловать в наш магазин свежих продуктов.\n"
            "У нас всегда самые свежие фрукты и овощи!\n"
            "Выберите действие в меню ниже:"
        )

        try:

            photo = FSInputFile("app/img/fresh.jpg")  
            await message.answer_photo(
                photo=photo,
                caption=welcome_text,
                reply_markup=get_main_keyboard(),
                parse_mode=ParseMode.HTML
            )
        except FileNotFoundError:
            raise FileNotFoundError
            
    except FileNotFoundError:
        await message.answer(
            "👋 Добро пожаловать в наш магазин свежих продуктов!\n"
            "Выберите действие в меню ниже:",
            reply_markup=get_main_keyboard(),
            parse_mode=ParseMode.HTML
        )
        
    except Exception as e:
        await message.answer(
            "Произошла ошибка при запуске бота. Пожалуйста, попробуйте позже."
        )



@router.message(Command("prices"))
async def cmd_prices(message: Message, session: AsyncSession):
    """Показать цены товаров из базы данных"""
    try:
        result = await session.execute(
            select(Product).where(Product.is_available == True).order_by(Product.category, Product.name)
        )
        products = result.scalars().all()

        if not products:
            await message.answer("❌ Пока нет доступных товаров.")
            return

        prices_text = "<b>📊 ТЕКУЩИЕ ЦЕНЫ</b>\n\n"
        for product in products:
            wholesale_price = product.wholesale_price if product.wholesale_price is not None else '—'
            prices_text += (
                f"• <b>{product.name}</b>: розница {product.retail_price} ₽, "
                f"опт {wholesale_price} ₽\n"
            )

        await message.answer(prices_text, parse_mode=ParseMode.HTML)
    except Exception:
        await message.answer(
            "Произошла ошибка при получении цен. Пожалуйста, попробуйте позже.",
            parse_mode=ParseMode.HTML
        )

# Команда /update_price
@router.message(Command("update_price"))
async def cmd_update_price(message: Message, session: AsyncSession):
    """Обновление цен товара в базе данных"""
    try:
        user_id = message.from_user.id
        if user_id not in ADMIN_IDS:
            await message.answer("⛔️ У вас нет прав для обновления цен.")
            return

        try:
            parts = message.text.split()
            if len(parts) != 4:
                raise ValueError("Неверное количество параметров")
            _, product_name, retail_price, wholesale_price = parts
            retail_price = float(retail_price)
            wholesale_price = float(wholesale_price)
        except ValueError:
            await message.answer(
                "❌ Неверный формат команды.\n"
                "Используйте: /update_price <название> <розничная_цена> <оптовая_цена>"
            )
            return

        result = await session.execute(
            select(Product).where(func.lower(Product.name) == product_name.lower())
        )
        product = result.scalars().first()

        if not product:
            await message.answer(f"❌ Товар '{product_name}' не найден в базе.")
            return

        product.retail_price = retail_price
        product.wholesale_price = wholesale_price
        await session.commit()

        await message.answer(f"✅ Цены для товара '{product_name}' успешно обновлены.")
    except Exception:
        await message.answer(
            "Произошла ошибка при обновлении цен. Пожалуйста, попробуйте позже."
        )
@router.callback_query(F.data == "contacts")
async def process_contacts(callback: CallbackQuery):
    """Обработчик кнопки контактов"""
    try:
        await callback.message.edit_text(
            "📞 Наши контакты:\n\n"
            "Телефон: +7 (985) 575-09-08\n"
            "Telegram: @kabura_support\n"
            "Email: kabura.support@mail.ru",
            reply_markup=get_contact_keyboard()
        )
    except TelegramBadRequest:
        # Если сообщение было с фото, сначала удаляем его
        try:
            await callback.message.delete()
        except Exception as e:
            pass
        
        await callback.message.answer(
            "📞 Наши контакты:\n\n"
            "Телефон: +7 (985) 575-09-08\n"
            "Telegram: @kabura_support\n"
            "Email: kabura.support@mail.ru",
            reply_markup=get_contact_keyboard()
        )
    finally:
        await callback.answer()

@router.callback_query(F.data == "about")
async def process_about(callback: CallbackQuery):
    """Обработчик кнопки о сервисе"""
    try:
        await callback.message.edit_text(
            "ℹ️ О нашем сервисе:\n\n"
            "Мы предлагаем свежие продукты с доставкой.\n"
            "Работаем ежедневно с 8:00 до 20:00.\n"
            "Минимальный заказ: 1 кг.\n"
            "Фрукты,Овощи --- Цена розничная за 1 кг , цена оптовая за ящик в ящике 5,5 кг\n"
            "Кола, спрайт, фанта --- Цена розничная за 1 шт, цена оптовая за упаковку(12шт)\n"
            "Доставка: бесплатно от 3000₽.",
            reply_markup=get_about_keyboard()
        )
    except TelegramBadRequest:
        try:
            await callback.message.delete()
        except Exception as e:
            pass
        
        await callback.message.answer(
            "ℹ️ О нашем сервисе:\n\n"
            "Мы предлагаем свежие продукты с доставкой.\n"
            "Работаем ежедневно с 8:00 до 20:00.\n"
            "Минимальный заказ: 1 кг.\n"
            "Доставка: бесплатно от 3000₽.",
            reply_markup=get_about_keyboard()
        )
    finally:
        await callback.answer()

@router.callback_query(F.data == "catalog")
async def process_catalog(callback: CallbackQuery):
    """Обработчик каталога"""
    try:
        await callback.message.delete()
    except Exception as e:
        pass
    
    try:
        await callback.message.answer(
            "📋 Выберите категорию товаров:",
            reply_markup=get_catalog_keyboard()
        )
    except Exception as e:
        await callback.answer("Произошла ошибка, попробуйте позже")
    else:
        await callback.answer()

@router.callback_query(F.data == "back_to_main")
async def process_back_to_main(callback: CallbackQuery):
    """Обработчик возврата в главное меню"""
    try:
        photo_path = Path("app/img/fresh.jpg")
        if photo_path.exists():
            photo = FSInputFile(photo_path)
            try:
                await callback.message.edit_media(
                    InputMediaPhoto(media=photo, caption="🏠 Главное меню"),
                    reply_markup=get_main_keyboard()
                )
                await callback.answer()
                return
            except TelegramBadRequest:
                pass
        
        # Если редактирование не удалось, отправляем новое сообщение
        try:
            await callback.message.delete()
        except:
            pass
        
        if photo_path.exists():
            try:
                photo = FSInputFile(photo_path)
                await callback.message.answer_photo(
                    photo=photo,
                    caption="🏠 Главное меню",
                    reply_markup=get_main_keyboard(),
                    parse_mode=ParseMode.HTML
                )
                await callback.answer()
                return
            except Exception as e:
                pass
        
        # Финальный вариант - просто текстовое сообщение
        await callback.message.answer(
            "🏠 Главное меню",
            reply_markup=get_main_keyboard(),
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        await callback.message.answer(
            "Произошла ошибка, попробуйте еще раз",
            reply_markup=get_main_keyboard()
        )
    finally:
        await callback.answer()

@router.callback_query(F.data == "back_to_products")
async def process_back_to_products(callback: CallbackQuery):
    """Обработчик возврата к списку товаров"""
    try:
        await callback.message.edit_text(
            "📋 Выберите категорию товаров:",
            reply_markup=get_catalog_keyboard()
        )
    except TelegramBadRequest:
        try:
            await callback.message.delete()
        except Exception as e:
            pass
        
        await callback.message.answer(
            "📋 Выберите категорию товаров:",
            reply_markup=get_catalog_keyboard()
        )
    finally:
        await callback.answer()

@router.callback_query(F.data == "back_to_cart")
async def process_back_to_cart(callback: CallbackQuery, db: Database):
    """Обработчик возврата в корзину"""
    try:
        user_id = callback.from_user.id
        cart = await db.get_cart(user_id)
        
        if not cart:
            try:
                await callback.message.edit_text(
                    "🛒 Ваша корзина пуста!",
                    reply_markup=get_catalog_keyboard()
                )
            except TelegramBadRequest:
                await callback.message.delete()
                await callback.message.answer(
                    "🛒 Ваша корзина пуста!",
                    reply_markup=get_catalog_keyboard()
                )
            return
        
        try:
            await callback.message.edit_text(
                "🛒 Ваша корзина:",
                reply_markup=get_cart_keyboard(cart)
            )
        except TelegramBadRequest:
            await callback.message.delete()
            await callback.message.answer(
                "🛒 Ваша корзина:",
                reply_markup=get_cart_keyboard(cart)
            )
    except Exception as e:
        await callback.answer("Произошла ошибка")
    finally:
        await callback.answer()

@router.callback_query(F.data.startswith("prev_"))
async def prev_page(callback: CallbackQuery, session: AsyncSession):
    try:
        # Разбираем callback_data, учитывая что в названии категории могут быть подчеркивания
        parts = callback.data.split("_")
        page = int(parts[-1])  # Последний элемент - номер страницы
        category = "_".join(parts[1:-1])  # Все между prev_ и номером страницы - категория
        
        keyboard = await get_products_keyboard(category, session, page)
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    except Exception as e:
        await callback.answer("⚠️ Ошибка при загрузке страницы", show_alert=True)
    finally:
        await callback.answer()

@router.callback_query(F.data.startswith("next_"))
async def next_page(callback: CallbackQuery, session: AsyncSession):
    try:
        parts = callback.data.split("_")
        page = int(parts[-1])
        category = "_".join(parts[1:-1])
        
        keyboard = await get_products_keyboard(category, session, page)
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    except Exception as e:
        await callback.answer("⚠️ Ошибка при загрузке страницы", show_alert=True)
    finally:
        await callback.answer()


@router.callback_query(F.data.startswith("category_"))
async def show_category_products(
    callback: CallbackQuery, 
    session: AsyncSession
):
    category = callback.data.split("_")[1]  # fruits, vegetables, drinks, other
    await callback.message.edit_text(
        text=f"Товары в категории: {category}",
        reply_markup=await get_products_keyboard(category, session)
    )
    await callback.answer()

@router.callback_query(F.data.startswith("product_"))
async def show_product_detail(
    callback: CallbackQuery, 
    session: AsyncSession,
    bot: Bot
):
    product_id = int(callback.data.split("_")[1])
    product = await session.get(Product, product_id)    
    if not product:
        await callback.answer("Товар не найден")
        return
    
    text = (
        f"<b>{product.name}</b>\n\n"
        f"<b>Цена за 1 кг:</b> {product.retail_price}₽\n"
        f"<b>Цена за ящик:</b> {product.wholesale_price}₽\n"
        f"<b>Наличие:</b> {'✅ В наличии' if product.is_available else '❌ Нет в наличии'}\n"
        f"<b>Описание:</b> {product.description or 'Нет описания'}\n"
    )
    
    keyboard = await get_product_detail_keyboard(
        product_id=product_id,
        user_id=callback.from_user.id,
        session=session
    )
    
    # Если у товара есть фото, отправляем его с подписью
    if product.image_url:
        try:
            # Пытаемся отредактировать сообщение, добавив фото
            try:
                await callback.message.edit_media(
                    InputMediaPhoto(
                        media=product.image_url,
                        caption=text,
                        parse_mode='HTML'
                    ),
                    reply_markup=keyboard
                )
            except (TelegramBadRequest, AttributeError):
                # Если не получилось отредактировать, удаляем старое и отправляем новое
                try:
                    await callback.message.delete()
                except:
                    pass
                await bot.send_photo(
                    chat_id=callback.from_user.id,
                    photo=product.image_url,
                    caption=text,
                    reply_markup=keyboard,
                    parse_mode='HTML'
                )
        except Exception as e:
            # Если не удалось отправить фото (неверный URL и т.д.), отправляем текст
            try:
                await callback.message.delete()
            except:
                pass
            await bot.send_message(
                chat_id=callback.from_user.id,
                text=text,
                reply_markup=keyboard,
                parse_mode='HTML'
            )
    else:
        # Если фото нет, отправляем только текст
        try:
            await callback.message.edit_text(
                text=text,
                reply_markup=keyboard,
                parse_mode='HTML'
            )
        except TelegramBadRequest:
            # Если не получилось отредактировать, удаляем и отправляем новое
            try:
                await callback.message.delete()
            except:
                pass
            await bot.send_message(
                chat_id=callback.from_user.id,
                text=text,
                reply_markup=keyboard,
                parse_mode='HTML'
            )
    
    await callback.answer()


@router.callback_query(F.data.startswith("add_to_cart_"))
async def add_to_cart(callback: CallbackQuery, session: AsyncSession):
    try:
        product_id = int(callback.data.split("_")[-1])
        user_id = callback.from_user.id
        
        # First get the product to ensure it exists and get its details
        product = await session.get(Product, product_id)
        if not product:
            await callback.answer("⚠️ Товар не найден", show_alert=True)
            return
            
        # Проверяем, есть ли уже такой товар в корзине
        existing_item = await session.execute(
            select(CartItem).where(
                (CartItem.user_id == user_id) & 
                (CartItem.product_id == product_id)
            )
        )
        existing_item = existing_item.scalar_one_or_none()
        
        if existing_item:
            existing_item.quantity += 1
            alert_text = "Количество увеличено!"
        else:
            new_item = CartItem(
                user_id=user_id,
                product_id=product_id,
                product_name=product.name,  # Добавляем название товара
                price=product.wholesale_price,  # Добавляем цену
                quantity=1
            )
            session.add(new_item)
            alert_text = "Товар добавлен в корзину!"
        
        await session.commit()
        await callback.answer(alert_text, show_alert=True)
        
        # Обновляем кнопку в сообщении
        product_message = callback.message
        reply_markup = await get_product_detail_keyboard(
            product_id=product_id,
            user_id=user_id,
            session=session
        )
        await product_message.edit_reply_markup(reply_markup=reply_markup)
        
    except Exception as e:
        await callback.answer("⚠️ Ошибка при добавлении в корзину", show_alert=True)
        await session.rollback()

@router.callback_query(F.data == "view_cart")
async def view_cart(callback: CallbackQuery, session: AsyncSession):
    try:
        user_id = callback.from_user.id
        
        # Проверяем количество товаров в корзине
        cart_count = await session.scalar(
            select(func.count(CartItem.id))
            .where(CartItem.user_id == user_id)
        )
        
        if not cart_count:
            await callback.answer("🛒 Ваша корзина пуста", show_alert=True)
            return
        
        await callback.answer("Открываю корзину...")
        await show_cart_page(callback.message, session, user_id, 0)
        
    except Exception as e:
        await callback.answer("⚠️ Ошибка при открытии корзины", show_alert=True)

async def show_cart_page(message: Message, session: AsyncSession, user_id: int, page: int = 0, items_per_page: int = 5):
    try:
        # Получаем товары с пагинацией
        cart_items = await session.execute(
            select(CartItem, Product)
            .join(Product, CartItem.product_id == Product.id)
            .where(CartItem.user_id == user_id)
            .offset(page * items_per_page)
            .limit(items_per_page)
        )
        cart_items = cart_items.all()
        
        if not cart_items:
            await message.answer("🛒 Ваша корзина пуста")
            return
        
        # Формируем сообщение с корзиной
        total = 0
        cart_text = "🛒 <b>Ваша корзина</b>\n\n"
        cart_text += "━━━━━━━━━━━━━━━━━━━━\n"
        
        for item, product in cart_items:
            # Используем только оптовую цену
            price = product.wholesale_price
            price_type = "опт"
            
            item_total = price * item.quantity
            total += item_total
            
            cart_text += (
                f"<b>▫️ {product.name}</b>\n"
                f"<i>Цена ({price_type}):</i> {price} ₽ × {item.quantity} = <b>{item_total} ₽</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
            )
        
        cart_text += f"\n<b>💳 Итого к оплате: {total} ₽</b>"

        builder = InlineKeyboardBuilder()

        for item, product in cart_items:
            try:

                unit = ''.join([c for c in str(getattr(product, 'amount', '')) if c.isalpha()]).strip()
                btn_text = f"✏️ {product.name[:15]} ({item.quantity} {unit})"
            except:
                btn_text = f"✏️ {product.name[:15]} ({item.quantity}) {unit}"
            
            builder.row(
                InlineKeyboardButton(
                    text=btn_text,
                    callback_data=f"edit_cart_{item.id}"
                )
            )

        total_items = await session.scalar(
            select(func.count(CartItem.id))
            .where(CartItem.user_id == user_id)
        )
        
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"cart_prev_{page-1}"))
        
        if (page + 1) * items_per_page < total_items:
            nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"cart_next_{page+1}"))
        
        if nav_buttons:
            builder.row(*nav_buttons)
        
        # Основные кнопки
        builder.row(
            InlineKeyboardButton(text="🗑 Очистить", callback_data="clear_cart"),
            InlineKeyboardButton(text="💳 Оформить", callback_data="checkout")
        )
        builder.row(
            InlineKeyboardButton(text="⬅️ В каталог", callback_data="back_to_categories")
        )
        try:
            await message.delete()
        except:
            pass
        
        await message.answer(
            text=cart_text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        return total
        
    except Exception as e:
        await message.answer("⚠️ Произошла ошибка при загрузке корзины")

        
@router.callback_query(F.data == "back_to_categories")
async def process_back_to_categories(callback_query: CallbackQuery, session: AsyncSession):
    await callback_query.answer()
    await callback_query.message.edit_text(
        text="📋 Выберите категорию товаров:",
        reply_markup=get_catalog_keyboard()
    )


@router.callback_query(F.data.startswith("cart_page_"))
async def change_cart_page(callback: CallbackQuery, session: AsyncSession):
    try:
        page = int(callback.data.split("_")[-1])
        await callback.answer()
        await show_cart_page(callback.message, session, callback.from_user.id, page)
    except Exception as e:
        await callback.answer("⚠️ Ошибка при переключении страницы", show_alert=True)

@router.callback_query(F.data.startswith("edit_cart_"))
async def edit_cart_item(callback: CallbackQuery, session: AsyncSession):
    try:
        cart_item_id = int(callback.data.split("_")[-1])

        result = await session.execute(
            select(CartItem, Product)
            .join(Product, CartItem.product_id == Product.id)
            .where(CartItem.id == cart_item_id)
        )
        cart_item, product = result.first()

        text = (
            f"<b>✏️ Редактирование товара</b>\n\n"
            f"<b>Название:</b> {product.name}\n"
            f"<b>Цена:</b> {product.wholesale_price} ₽\n"
            f"<b>Количество:</b> {cart_item.quantity}\n\n"
            f"<i>Измените количество:</i>"
        )
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="➖ Уменьшить", callback_data=f"decrease_{cart_item.id}"),
            InlineKeyboardButton(text="➕ Увеличить", callback_data=f"increase_{cart_item.id}"),
        )
        builder.row(
            InlineKeyboardButton(text="❌ Удалить", callback_data=f"remove_{cart_item.id}"),
            InlineKeyboardButton(text="◀️ В корзину", callback_data="view_cart")
        )
        
        await callback.message.edit_text(
            text=text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        await callback.answer()
        
    except Exception as e:
        await callback.answer("⚠️ Ошибка при редактировании", show_alert=True)

@router.callback_query(F.data.startswith("increase_"))
async def increase_quantity(callback: CallbackQuery, session: AsyncSession):
    try:
        cart_item_id = int(callback.data.split("_")[-1])
        cart_item = await session.get(CartItem, cart_item_id)
        cart_item.quantity += 1
        await session.commit()
        await callback.answer("Количество увеличено!", show_alert=True)
        await edit_cart_item(callback, session)
    except Exception as e:
        await callback.answer("⚠️ Ошибка при увеличении", show_alert=True)

@router.callback_query(F.data.startswith("decrease_"))
async def decrease_quantity(callback: CallbackQuery, session: AsyncSession):
    try:
        cart_item_id = int(callback.data.split("_")[-1])
        cart_item = await session.get(CartItem, cart_item_id)
        
        if cart_item.quantity > 1:
            cart_item.quantity -= 1
            await session.commit()
            await callback.answer("Количество уменьшено!", show_alert=True)
            await edit_cart_item(callback, session)
        else:
            await callback.answer("Минимальное количество - 1", show_alert=True)
    except Exception as e:
        await callback.answer("⚠️ Ошибка при уменьшении", show_alert=True)

@router.callback_query(F.data.startswith("remove_"))
async def remove_item(callback: CallbackQuery, session: AsyncSession):
    try:
        cart_item_id = int(callback.data.split("_")[-1])
        cart_item = await session.get(CartItem, cart_item_id)
        await session.delete(cart_item)
        await session.commit()
        
        # Сначала показываем алерт
        await callback.answer("Товар удалён из корзины", show_alert=True)
        
        # Затем обновляем сообщение
        try:
            await callback.message.edit_text(
                text="📋 Выберите категорию товаров:",
                reply_markup=get_catalog_keyboard()
            )
        except:
            await callback.message.delete()
            await callback.message.answer(
                text="📋 Выберите категорию товаров:",
                reply_markup=get_catalog_keyboard()
            )
            
    except Exception as e:
        await callback.answer("⚠️ Ошибка при удалении", show_alert=True)

@router.callback_query(F.data == "clear_cart")
async def clear_cart(callback: CallbackQuery, session: AsyncSession):
    try:
        user_id = callback.from_user.id
        await session.execute(
            delete(CartItem).where(CartItem.user_id == user_id)
        )
        await session.commit()
        await callback.answer("Корзина очищена", show_alert=True)

        await callback.message.delete()
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="⬅️ Назад ", callback_data="back_to_categories")

        )
        await callback.message.answer("🛒 Ваша корзина теперь пуста",reply_markup=builder.as_markup())
    except Exception as e:
        await callback.answer("⚠️ Ошибка при очистке корзины", show_alert=True)



@router.callback_query(F.data == "checkout")
async def start_checkout(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    try:
        # Получаем сумму корзины только по оптовым ценам
        total = await session.scalar(
            select(func.sum(
                Product.wholesale_price * CartItem.quantity
            ))
            .join(CartItem, Product.id == CartItem.product_id)
            .where(CartItem.user_id == callback.from_user.id)
        )
        
        if not total:
            await callback.answer("Ваша корзина пуста", show_alert=True)
            return
            
        await state.update_data(total=total)
        
        builder = InlineKeyboardBuilder()
        builder.add(InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_order"))
        
        await callback.message.answer(
            "Введите ваше имя:",
            reply_markup=builder.as_markup()
        )
        await state.set_state(OrderStates.WAITING_NAME)
        await callback.answer()
        
    except Exception as e:
        await callback.answer("⚠️ Ошибка при оформлении заказа", show_alert=True)

@router.message(OrderStates.WAITING_NAME)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📱 Отправить контакт", callback_data="send_contact"),
        InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_order"),
        width=1  # Каждая кнопка в своем ряду
    )
    
    await message.answer(
        "Теперь укажите ваш телефон:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(OrderStates.WAITING_PHONE)

@router.callback_query(F.data == "send_contact", OrderStates.WAITING_PHONE)
async def request_contact(callback: CallbackQuery, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_order"))
    
    await callback.message.answer(
        "Пожалуйста, поделитесь контактом:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📱 Отправить контакт", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )
    await callback.answer()

@router.message(OrderStates.WAITING_PHONE, F.contact)
async def process_contact(message: Message, state: FSMContext):
    phone = message.contact.phone_number
    if not phone:
        await message.answer("Не удалось получить номер телефона из контакта")
        return
        
    await state.update_data(phone=phone)
    
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_order"))
    
    await message.answer(
        "Теперь укажите адрес доставки текстом:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(OrderStates.WAITING_ADDRESS)

@router.message(OrderStates.WAITING_PHONE, F.text)
async def process_phone_text(message: Message, state: FSMContext):
    phone = message.text.strip()
    if not re.match(r'^\+?[\d\s\-\(\)]{7,}$', phone):
        await message.answer("Пожалуйста, введите корректный номер телефона")
        return
        
    await state.update_data(phone=phone)
    
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_order"))
    
    await message.answer(
        "Теперь укажите адрес доставки текстом:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(OrderStates.WAITING_ADDRESS)

async def safe_answer_callback(callback: CallbackQuery, text: str = None, show_alert: bool = False):
    """Safely answer callback query with timeout handling"""
    try:
        await callback.answer(text, show_alert=show_alert)
        return True
    except TelegramBadRequest as e:
        if "query is too old" in str(e):
            return False
        raise

@router.message(OrderStates.WAITING_ADDRESS, F.text)
async def process_address(message: Message, state: FSMContext):
    address = message.text.strip()
    if not address:
        await message.answer("Пожалуйста, введите адрес текстом")
        return
        
    await state.update_data(address=address)
    
    builder = InlineKeyboardBuilder()
    time_slots = [
        ("Утро (9-12)", "delivery_morning"),
        ("День (12-18)", "delivery_day"),
        ("Вечер (18-22)", "delivery_evening")
    ]
    for text, callback_data in time_slots:
        builder.row(InlineKeyboardButton(text=text, callback_data=callback_data))
    
    builder.row(InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_order"))
    
    await message.answer(
        "Выберите удобный интервал доставки:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(OrderStates.WAITING_DELIVERY_TIME)

# Добавляем функцию для преобразования callback_data в читаемый текст
def get_delivery_time_text(callback_data: str) -> str:
    time_mapping = {
        "delivery_morning": "Утро (9-12)",
        "delivery_day": "День (12-18)",
        "delivery_evening": "Вечер (18-22)"
    }
    return time_mapping.get(callback_data, callback_data)

@router.callback_query(F.data.startswith("delivery_"), OrderStates.WAITING_DELIVERY_TIME)
async def process_delivery_time(
    callback: CallbackQuery, 
    state: FSMContext, 
    session: AsyncSession
):
    """Handle delivery time selection and payment creation"""
    if not await safe_answer_callback(callback):
        return
    
    data = await state.get_data()
    user_id = callback.from_user.id
    
    try:
        # Обновляем время доставки
        delivery_time = callback.data.replace("delivery_", "")
        await state.update_data(delivery_time=delivery_time)
        
        # Создаем платеж
        payment = await payment_system.create_payment(
            amount=float(data['total']),
            user_id=user_id,
            description=f"Order #{user_id}-{int(datetime.now().timestamp())}"
        )
        
        if not payment:
            await callback.message.answer("⚠️ Ошибка платежной системы. Пожалуйста, попробуйте позже.")
            return
            
        # Сохраняем данные платежа
        await state.update_data(
            payment_id=payment['id'],
            payment_amount=payment['amount']
        )
        
        # Создаем клавиатуру для оплаты
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(
            text="💳 Оплатить сейчас", 
            url=payment['confirmation_url']
        ))
        builder.row(InlineKeyboardButton(
            text="🔄 Проверить оплату", 
            callback_data="check_payment"
        ))
        
        payment_message = await callback.message.answer(
            f"Сумма к оплате: {payment['amount']} ₽\n"
            "Ссылка действительна 30 минут.\n"
            "После оплаты нажмите 'Проверить оплату'.",
            reply_markup=builder.as_markup()
        )
        
        await state.update_data(payment_message_id=payment_message.message_id)
        
    except Exception as e:
        await callback.message.answer("⚠️ Ошибка при создании платежа. Пожалуйста, попробуйте снова.")
        
@router.callback_query(F.data == "check_payment")
async def check_payment_handler(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot
):
    data = await state.get_data()
    payment_id = data.get('payment_id')
    user_id = callback.from_user.id
    
    if not payment_id:
        await callback.answer("❌ Платеж не найден", show_alert=True)
        return
    
    try:
        # Проверяем статус платежа
        is_paid = await payment_system.verify_payment_success(payment_id)
        
        if is_paid:
            # Получаем все данные из состояния
            state_data = await state.get_data()
            
            # Получаем товары из корзины
            cart_items = await session.execute(
                select(CartItem)
                .where(CartItem.user_id == user_id)
                .options(selectinload(CartItem.product))
            )
            cart_items = cart_items.scalars().all()
            
            if not cart_items:
                await callback.answer("❌ Корзина пуста", show_alert=True)
                return
            
            # Создаем заказ
            order = Order(
                user_id=user_id,
                payment_id=payment_id,
                status="paid",
                amount=state_data['total'],
                customer_name=state_data.get('name', 'Не указано'),
                customer_phone=state_data.get('phone', 'Не указан'),
                delivery_address=state_data.get('address', 'Не указан'),
                delivery_time=state_data.get('delivery_time', 'Не указано')
            )
            
            session.add(order)
            await session.flush()  # Получаем ID заказа
            
            # Создаем элементы заказа
            for item in cart_items:
                order_item = OrderItem(
                    order_id=order.id,
                    product_id=item.product_id,
                    product_name=item.product.name if item.product else f"Товар {item.product_id}",
                    quantity=item.quantity,
                    price=item.price
                )
                session.add(order_item)
            
            # Очищаем корзину
            await session.execute(
                delete(CartItem).where(CartItem.user_id == user_id))
            
            await session.commit()
            
            # Отправляем подтверждение пользователю
            await callback.answer(f"✅ Заказ #{order.id} успешно оформлен!", show_alert=True)
            
            # Отправляем уведомление администратору
            await send_admin_notification(bot, order, cart_items)
            
            # Очищаем состояние
            await state.clear()
            
        else:
            await callback.answer("❌ Оплата не прошла или еще обрабатывается", show_alert=True)
            
    except Exception as e:
        await session.rollback()
        await callback.answer("⚠️ Ошибка при обработке заказа", show_alert=True)

async def send_admin_notification(bot: Bot, order: Order, cart_items: list):
    """Send order notification to admin"""
    try:
        items_text = "\n".join(
            f"- {item.product_name}: {item.quantity} x {item.price} ₽ = {item.quantity * item.price} ₽"
            for item in cart_items
        )
        
        # Преобразуем время доставки в читаемый формат
        delivery_time_text = get_delivery_time_text(order.delivery_time)
        
        admin_text = (
            "📦 <b>НОВЫЙ ОПЛАЧЕННЫЙ ЗАКАЗ!</b>\n\n"
            f"🆔 Номер: #{order.id}\n"
            f"👤 Клиент: {order.customer_name}\n"
            f"📞 Телефон: {order.customer_phone}\n"
            f"📍 Адрес: {order.delivery_address}\n"
            f"⏰ Время доставки: {delivery_time_text}\n"
            f"💵 Сумма: {order.amount} ₽\n\n"
            f"🛒 <b>Состав заказа:</b>\n{items_text}"
        )
        
        for admin in ADMIN_IDS:
            try:
                await bot.send_message(
                    chat_id=admin,
                    text=admin_text,
                    parse_mode="HTML"
                )
            except Exception:
                continue
    except Exception as e:
        pass

@router.callback_query(F.data == "cancel_order")
async def cancel_order(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer(
        "❌ Оформление заказа отменено",
        reply_markup=ReplyKeyboardRemove()
    )
    await callback.answer()
    
@router.callback_query(F.data == 'my_orders')
async def show_user_orders(callback: CallbackQuery, session: AsyncSession):
    try:
        # Получаем заказы пользователя
        orders = await session.execute(
            select(Order)
            .where(Order.user_id == callback.from_user.id)
            .order_by(Order.created_at.desc())
        )
        orders = orders.scalars().all()
        
        if not orders:
            await callback.answer("📭 У вас пока нет заказов", show_alert=True)
            return
        
        # Формируем сообщение с заказами
        builder = InlineKeyboardBuilder()
        for order in orders:
            builder.row(
                InlineKeyboardButton(
                    text=f"🛒 Заказ №{order.id} | {order.amount} ₽ | {order.status}",
                    callback_data=f"order_detail_{order.id}"
                )
            )
        builder.row(
            InlineKeyboardButton(text="🔙 На главную", callback_data="back_to_main")
        )
        
        # Универсальный способ обновления сообщения
        try:
            # Пытаемся отредактировать
            await callback.message.edit_text(
                "📦 <b>Ваши заказы:</b>",
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
        except TelegramBadRequest as e:
            if "no text in the message to edit" in str(e):
                # Если нельзя редактировать - удаляем старое и отправляем новое
                await callback.message.delete()
                await callback.message.answer(
                    "📦 <b>Ваши заказы:</b>",
                    reply_markup=builder.as_markup(),
                    parse_mode="HTML"
                )
            else:
                raise
        
        await callback.answer()
        
    except Exception as e:
        await callback.answer("⚠️ Не удалось загрузить заказы", show_alert=True)

@router.callback_query(F.data.startswith("order_detail_"))
async def show_order_details(callback: CallbackQuery, session: AsyncSession):
    try:
        # Извлекаем ID заказа из callback_data
        order_id = int(callback.data.split("_")[-1])
        
        # Получаем заказ из БД
        order = await session.scalar(
            select(Order)
            .where(Order.id == order_id)
            .where(Order.user_id == callback.from_user.id)
        )
        
        if not order:
            await callback.answer("Заказ не найден", show_alert=True)
            return
        
        # Получаем товары из этого заказа
        items_result = await session.execute(
            select(CartItem, Product)
            .join(Product, CartItem.product_id == Product.id)
            .where(CartItem.order_id == order_id)
        )
        items = items_result.scalars().all()
        
        # Формируем текст сообщения
        message_text = (
            "📋 <b>Детали заказа</b>\n\n"
            f"🆔 <b>Номер заказа:</b> {order.id}\n"
            f"📅 <b>Дата оформления:</b> {order.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            f"👤 <b>Имя:</b> {order.customer_name}\n"
            f"📞 <b>Телефон:</b> {order.customer_phone}\n"
            f"📍 <b>Адрес доставки:</b> {order.delivery_address}\n"
            f"⏰ <b>Время доставки:</b> {order.delivery_time}\n"
            f"🛒 <b>Статус:</b> {order.status}\n\n"
            "📦 <b>Состав заказа:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
        )
        
        # Добавляем товары
        for item in items:
            product = await session.get(Product, item.product_id)
            if not product:
                continue
                
            # Определяем цену (розничная или оптовая)
            price = product.wholesale_price  # По умолчанию розничная цена
            price_type = "опт"
            
            message_text += (
                f"🍅 <b>{product.name}</b>\n"
                f"├ Цена ({price_type}): {price} ₽/кг\n"
                f"├ Количество: {item.quantity} кг\n"
                f"└ Сумма: {price * item.quantity} ₽\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
            )
        
        message_text += f"\n💰 <b>Итого к оплате:</b> {order.amount} ₽"
        
        # Создаем кнопки
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="🔙 К списку заказов", callback_data="my_orders"),
            width=1
        )
        
        # Отправляем сообщение
        await callback.message.edit_text(
            message_text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        
    except Exception as e:
        await callback.answer("⚠️ Ошибка при загрузке деталей заказа", show_alert=True)