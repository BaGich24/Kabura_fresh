from typing import Union
from aiogram import F, Bot, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command
from sqlalchemy import delete, func, select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from .database import User, Order, CartItem, Product
from .config import ADMIN_IDS
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ContentType

admin = Router()
async def is_admin(user_id: int):
    return user_id in ADMIN_IDS

class BroadcastStates(StatesGroup):
    waiting_for_content = State()
    waiting_for_confirmation = State()

class SearchOrder(StatesGroup):
    waiting_for_search_term = State()
    waiting_for_user_selection = State()


class AddPhotoStates(StatesGroup):
    waiting_for_product_name = State()
    waiting_for_photo_url = State()

@admin.message(Command("admin"))
async def admin_panel(message: Message):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещен")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🔍 Найти заказ", callback_data="admin_find_order")],
        [InlineKeyboardButton(text="📦 Все заказы", callback_data="admin_all_orders")],
        [InlineKeyboardButton(text="📷 Добавить фото товару", callback_data="admin_add_photo")]
    ])
    
    await message.answer("Админ-панель:", reply_markup=keyboard)

@admin.callback_query(F.data == "admin_add_photo")
async def admin_add_photo(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return

    await callback.message.edit_text(
        "📷 Введите название товара, которому хотите добавить фото:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
        ])
    )
    await state.set_state(AddPhotoStates.waiting_for_product_name)
    await callback.answer()

@admin.message(AddPhotoStates.waiting_for_product_name, F.text)
async def process_product_name_for_photo(message: Message, state: FSMContext, session: AsyncSession):
    product_name = message.text.strip()
    # Используем % для поиска по частичному совпадению (работает с кириллицей)
    result = await session.execute(
        select(Product).where(Product.name.ilike(f"%{product_name}%"))
    )
    products = result.scalars().all()
    
    # Если нашли несколько, ищем точное совпадение
    product = None
    if len(products) == 1:
        product = products[0]
    elif len(products) > 1:
        # Ищем точное совпадение среди результатов
        for p in products:
            if p.name.lower() == product_name.lower():
                product = p
                break
        # Если точного нет, берём первый
        if not product:
            product = products[0]

    if not product:
        await message.answer(
            f"❌ Товар '{product_name}' не найден.\n\nПопробуйте ещё раз (введите точное название из каталога):",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_add_photo")]
            ])
        )
        return

    await state.update_data(product_id=product.id)
    await message.answer(
        f"✅ Найден товар: {product.name}\n"
        "Теперь отправьте фото товара (в виде файла) или ссылку на изображение.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить", callback_data="admin_back")]
        ])
    )
    await state.set_state(AddPhotoStates.waiting_for_photo_url)

@admin.message(AddPhotoStates.waiting_for_photo_url, F.content_type.in_({ContentType.PHOTO, ContentType.TEXT}))
async def process_product_photo(message: Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    product_id = data.get('product_id')
    
    if not product_id:
        await state.clear()
        await message.answer(
            "❌ Ошибка: товар не выбран. Начните заново.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📷 Добавить фото", callback_data="admin_add_photo")]
            ])
        )
        return
    
    product = await session.get(Product, product_id)

    if not product:
        await message.answer(
            "❌ Товар удален или не существует. Начните заново.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_add_photo")]
            ])
        )
        await state.clear()
        return

    if message.content_type == ContentType.PHOTO:
        image_value = message.photo[-1].file_id
    else:
        image_value = message.text.strip()
        if not image_value:
            await message.answer(
                "❌ Пожалуйста, отправьте фото товара или ссылку на изображение.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_add_photo")]
                ])
            )
            return

    product.image_url = image_value
    await session.commit()
    await state.clear()

    try:
        await message.answer_photo(
            photo=image_value,
            caption=f"✅ Фото для товара '{product.name}' успешно сохранено!"
        )
    except Exception:
        await message.answer(f"✅ Фото для товара '{product.name}' успешно сохранено!")

    await message.answer(
        "✨ Изображение теперь видно в каталоге. Вы можете вернуться в админ-панель.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin_back")]
        ])
    )

@admin.callback_query(F.data == "cancel_add_photo")
async def cancel_add_photo(callback: CallbackQuery, state: FSMContext):
    """Отмена добавления фото и возврат в админ-панель"""
    await state.clear()
    await callback.answer("❌ Добавление фото отменено", show_alert=False)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🔍 Найти заказ", callback_data="admin_find_order")],
        [InlineKeyboardButton(text="📦 Все заказы", callback_data="admin_all_orders")],
        [InlineKeyboardButton(text="📷 Добавить фото товару", callback_data="admin_add_photo")]
    ])
    
    await callback.message.edit_text("Админ-панель:", reply_markup=keyboard)

@admin.callback_query(F.data == "admin_broadcast")
async def broadcast_menu(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    user_count = await session.scalar(select(func.count(User.id)))
    
    await callback.message.edit_text(
        f"📢 Рассылка\n\nВсего пользователей: {user_count}\n\n"
        "Отправьте сообщение для рассылки (текст, фото, видео или документ с подписью или без):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
        ])
    )
    await state.set_state(BroadcastStates.waiting_for_content)
    await callback.answer()

@admin.message(BroadcastStates.waiting_for_content, F.content_type.in_({
    ContentType.TEXT, 
    ContentType.PHOTO, 
    ContentType.VIDEO, 
    ContentType.DOCUMENT
}))
async def process_broadcast_content(message: Message, state: FSMContext, bot: Bot):
    content_type = message.content_type
    content_data = {
        'type': content_type,
        'caption': message.caption if hasattr(message, 'caption') else None
    }
    
    if content_type == ContentType.TEXT:
        content_data['text'] = message.text
    else:
        if content_type == ContentType.PHOTO:
            content_data['file_id'] = message.photo[-1].file_id
        elif content_type == ContentType.VIDEO:
            content_data['file_id'] = message.video.file_id
        elif content_type == ContentType.DOCUMENT:
            content_data['file_id'] = message.document.file_id
    
    await state.update_data(content_data=content_data)
    
    # Формируем текст для предпросмотра
    preview_text = "📢 Предпросмотр рассылки:\n\n"
    if content_type != ContentType.TEXT:
        preview_text += f"Тип: {content_type}\n"
    if 'text' in content_data or content_data['caption']:
        preview_text += f"Текст: {content_data.get('text') or content_data.get('caption')}\n"
    
    preview_text += "\nПодтвердите рассылку:"
    
    await message.answer(
        preview_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Начать рассылку", callback_data="confirm_broadcast")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_broadcast")]
        ])
    )
    await state.set_state(BroadcastStates.waiting_for_confirmation)

@admin.callback_query(BroadcastStates.waiting_for_confirmation, F.data == "confirm_broadcast")
async def start_broadcast(callback: CallbackQuery, state: FSMContext, bot: Bot, session: AsyncSession):
    data = await state.get_data()
    content_data = data['content_data']
    
    users = await session.scalars(select(User.telegram_id))
    user_ids = users.all()
    
    success = 0
    failed = 0
    
    await callback.message.edit_text("⏳ Начата рассылка...")
    
    for user_id in user_ids:
        try:
            if content_data['type'] == ContentType.TEXT:
                await bot.send_message(
                    chat_id=user_id,
                    text=content_data['text']
                )
            else:
                method = {
                    ContentType.PHOTO: bot.send_photo,
                    ContentType.VIDEO: bot.send_video,
                    ContentType.DOCUMENT: bot.send_document
                }[content_data['type']]
                
                await method(
                    chat_id=user_id,
                    **{content_data['type']: content_data['file_id']},
                    caption=content_data['caption']
                )
            success += 1
        except Exception as e:
            failed += 1
            continue
    
    await callback.message.answer(
        f"✅ Рассылка завершена\n\n"
        f"Успешно: {success}\n"
        f"Не удалось: {failed}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 В меню", callback_data="admin_back")]
        ])
    )
    await state.clear()

@admin.callback_query(BroadcastStates.waiting_for_confirmation, F.data == "cancel_broadcast")
async def cancel_broadcast(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ Рассылка отменена")
    await state.clear()
    await callback.answer()

@admin.callback_query(F.data == "admin_find_order")
async def find_order_menu(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return

    await callback.message.edit_text(
        "🔍 Введите ID заказа или username/имя/телефон пользователя:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
        ])
    )
    await state.set_state(SearchOrder.waiting_for_search_term)
    await callback.answer()

async def show_order_details(message: Union[Message, CallbackQuery], order: Order, session: AsyncSession):
    """Показывает детали заказа с возможностью завершения"""
    if isinstance(message, CallbackQuery):
        callback = message
        try:
            # Пытаемся редактировать существующее сообщение
            await callback.message.edit_text(
                await format_order_text(order, session),
                reply_markup=await format_order_keyboard(order)
            )
            await callback.answer()
            return
        except TelegramBadRequest:
            # Если не получилось редактировать - отправляем новое сообщение
            message = callback.message
            await message.answer(
                await format_order_text(order, session),
                reply_markup=await format_order_keyboard(order)
            )
            return
    else:
        # Для новых сообщений просто отправляем
        await message.answer(
            await format_order_text(order, session),
            reply_markup=await format_order_keyboard(order)
        )

async def format_order_text(order: Order, session: AsyncSession) -> str:
    """Форматирует текст сообщения с информацией о заказе"""
    user = await session.get(User, order.user_id) if order.user_id else None
    
    user_info = "Неизвестный пользователь"
    if user:
        user_info = f"{user.first_name or ''} {user.last_name or ''}".strip()
        if user.username:
            user_info += f" (@{user.username})"
    
    return (
        f"📦 Заказ #{order.id}\n"
        f"👤 Пользователь: {order.customer_name}\n"
        f"📞 Телефон: {order.customer_phone or 'не указан'}\n"
        f"💰 Сумма: {order.amount} ₽\n"
        f"🔄 Статус: {order.status}\n"
        f"📅 Дата: {order.created_at.strftime('%d.%m.%Y %H:%M')}\n"
    )

async def format_order_keyboard(order: Order) -> InlineKeyboardMarkup:
    """Форматирует клавиатуру для сообщения с заказом"""
    keyboard_buttons = []
    if order.status != "completed":
        keyboard_buttons.append(
            [InlineKeyboardButton(text="✅ Завершить заказ", callback_data=f"admin_complete_{order.id}")]
        )
    keyboard_buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    

@admin.message(SearchOrder.waiting_for_search_term, F.text)
async def process_search_term(message: Message, state: FSMContext, session: AsyncSession):
    search_term = message.text.strip()
    
    # Если ввели только цифры - ищем как ID заказа
    if search_term.isdigit():
        order_id = int(search_term)
        order = await session.get(Order, order_id)
        
        if order:
            await show_order_details(message, order, session)
            await state.clear()
            return
        else:
            await message.answer("❌ Заказ с таким ID не найден", show_alert=True)
            return

    # Остальная логика поиска по пользователям (как было)
    users = await session.execute(
        select(User)
        .where(
            or_(
                User.username.ilike(f"%{search_term}%"),
                User.first_name.ilike(f"%{search_term}%"),
                User.last_name.ilike(f"%{search_term}%")
            )
        )
    )
    users = users.scalars().all()

    if not users:
        orders_with_phone = await session.execute(
            select(Order)
            .where(Order.customer_phone.ilike(f"%{search_term}%"))
            .order_by(Order.created_at.desc())
        )
        orders_with_phone = orders_with_phone.scalars().all()
        
        if orders_with_phone:
            user_ids = {order.user_id for order in orders_with_phone}
            users = await session.execute(
                select(User).where(User.telegram_id.in_(user_ids))
            )
            users = users.scalars().all()

    if not users:
        await message.answer("❌ Пользователи не найдены", show_alert=True)
        await state.clear()
        return

    if len(users) == 1:
        await show_user_orders(message, users[0], session)
        await state.clear()
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{u.first_name or ''} {u.last_name or ''} (@{u.username})" if u.username else f"{u.first_name or ''} {u.last_name or ''}",
            callback_data=f"admin_user_{u.telegram_id}"
        )] for u in users
    ] + [[InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]])

    await message.answer("👥 Найдено несколько пользователей:", reply_markup=keyboard)
    await state.set_state(SearchOrder.waiting_for_user_selection)

@admin.callback_query(SearchOrder.waiting_for_user_selection, F.data.startswith("admin_user_"))
async def process_user_selection(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    telegram_id = int(callback.data.split("_")[-1])
    
    user = await session.execute(
        select(User)
        .where(User.telegram_id == telegram_id)
    )
    user = user.scalar_one_or_none()

    if not user:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        await state.clear()
        return

    await show_user_orders(callback, user, session)
    await state.clear()
    await callback.answer()

@admin.callback_query(F.data == "admin_all_orders")
async def all_orders_menu(callback: CallbackQuery, session: AsyncSession):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    # Получаем уникальные user_id из заказов
    distinct_user_ids = await session.execute(
        select(Order.user_id).distinct()
    )
    user_ids = [row[0] for row in distinct_user_ids.all()]
    
    if not user_ids:
        await callback.answer("❌ Нет заказов в базе", show_alert=True)
        return
    
    # Получаем пользователей по их telegram_id (user_id в заказах)
    users = await session.execute(
        select(User)
        .where(User.telegram_id.in_(user_ids))
        .order_by(User.telegram_id)
    )
    users = users.scalars().all()
    
    if not users:
        await callback.answer("❌ Пользователи не найдены", show_alert=True)
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{u.first_name} {u.last_name or ''} (@{u.username})" if u.username else f"{u.first_name} {u.last_name or ''}",
            callback_data=f"admin_user_orders_{u.telegram_id}"  # Используем telegram_id вместо id
        )] for u in users
    ] + [[InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]])
    
    await callback.message.edit_text(
        "📦 Все пользователи с заказами:",
        reply_markup=keyboard
    )
    await callback.answer()

@admin.callback_query(F.data.startswith("admin_user_orders_"))
async def show_user_orders(callback: CallbackQuery, session: AsyncSession):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    telegram_id = int(callback.data.split("_")[-1])
    
    # Находим пользователя по telegram_id
    user = await session.execute(
        select(User)
        .where(User.telegram_id == telegram_id)
    )
    user = user.scalar_one_or_none()
    
    if not user:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return
    
    orders = await session.execute(
        select(Order)
        .where(Order.user_id == telegram_id)  # Используем telegram_id как user_id
        .order_by(Order.created_at.desc())
    )
    orders = orders.scalars().all()
    
    if not orders:
        await callback.answer("❌ У пользователя нет заказов", show_alert=True)
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"#{o.id} | {o.amount} ₽ | {o.status} | {o.created_at.strftime('%d.%m')}",
            callback_data=f"admin_order_{o.id}"
        )] for o in orders
    ] + [
        [InlineKeyboardButton(text="🛒 Показать корзину", callback_data=f"admin_user_cart_{telegram_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_all_orders")]
    ])
    
    user_info = f"{user.first_name or ''} {user.last_name or ''}"
    if user.username:
        user_info += f" (@{user.username})"
    
    await callback.message.edit_text(
        f"📦 Заказы пользователя {user_info}:",
        reply_markup=keyboard
    )
    await callback.answer()
    
@admin.callback_query(F.data.startswith("admin_order_"))
async def order_details(callback: CallbackQuery, session: AsyncSession):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    order_id = int(callback.data.split("_")[-1])
    order = await session.get(Order, order_id)
    
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    
    # Ищем пользователя по telegram_id (который сохранен в order.user_id)
    user = await session.execute(
        select(User)
        .where(User.telegram_id == order.user_id)
    )
    user = user.scalar_one_or_none()
    
    # Формируем информацию о пользователе, даже если его нет в базе
    user_info = "Неизвестный пользователь"
    if user:
        user_info = f"{user.first_name or ''} {user.last_name or ''}"
        if user.username:
            user_info += f" (@{user.username})"
    
    cart_items = await session.execute(
        select(CartItem)
        .where(CartItem.order_id == order_id)
    )
    cart_items = cart_items.scalars().all()
    
    items_text = "\n".join(
        f"• {item.product_name} - {item.quantity} шт. x {item.price} ₽"
        for item in cart_items
    )
    
    text = (
        f"📦 Заказ #{order.id}\n\n"
        f"👤 Пользователь: {user_info}\n"
        f"📞 Телефон: {order.customer_phone}\n"
        f"📍 Адрес: {order.delivery_address}\n"
        f"⏰ Время доставки: {order.delivery_time}\n"
        f"💰 Сумма: {order.amount} ₽\n"
        f"📅 Дата: {order.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        f"🛒 Статус: {order.status}\n\n"
        f"🛍️ Состав заказа:\n{items_text}"
    )
    
    keyboard_buttons = []
    if order.status != "completed":
        keyboard_buttons.append(
            [InlineKeyboardButton(text="✅ Завершить заказ", callback_data=f"admin_complete_{order.id}")]
        )
    
    keyboard_buttons.append(
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"admin_user_orders_{order.user_id}")]
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    )
    await callback.answer()
    
@admin.callback_query(F.data.startswith("admin_complete_"))
async def complete_order(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    order_id = int(callback.data.split("_")[-1])
    
    try:
        async with session.begin():
            order = await session.get(Order, order_id)
            
            if not order:
                await callback.answer("❌ Заказ не найден", show_alert=True)
                return
            
            if order.status == "completed":
                await callback.answer("ℹ️ Заказ уже завершен", show_alert=True)
                return
            
            # Удаляем связанные элементы корзины
            await session.execute(
                delete(CartItem)
                .where(CartItem.order_id == order_id)
            )
            await session.delete(order)
        
        # 1. Сначала отвечаем на callback
        await callback.answer("✅ Заказ успешно завершен и удален!", show_alert=True)
        
        # 2. Затем редактируем оригинальное сообщение
        await callback.message.edit_text(
            text="✅ Заказ успешно завершен и удален!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin_back")]
            ])
        )
        
    except Exception as e:
        await session.rollback()
        print(f"Ошибка при удалении заказа: {e}")
        await callback.answer("❌ Ошибка при удалении заказа", show_alert=True)

@admin.callback_query(F.data.startswith("admin_user_cart_"))
async def show_user_cart(callback: CallbackQuery, session: AsyncSession):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    telegram_id = int(callback.data.split("_")[-1])
    
    # Ищем пользователя по telegram_id
    user = await session.execute(
        select(User)
        .where(User.telegram_id == telegram_id)
    )
    user = user.scalar_one_or_none()
    
    # Получаем текущую корзину пользователя (где order_id is NULL)
    cart_items = await session.execute(
        select(CartItem)
        .where(
            (CartItem.user_id == telegram_id) &  # Используем telegram_id как user_id
            (CartItem.order_id.is_(None))
        )
    )
    cart_items = cart_items.scalars().all()
    
    if not cart_items:
        await callback.answer("🛒 Корзина пуста", show_alert=True)
        return
    
    items_text = "\n".join(
        f"• {item.product_name} - {item.quantity} шт. x {item.price} ₽"
        for item in cart_items
    )
    
    total = sum(item.price * item.quantity for item in cart_items)
    
    user_info = "Пользователь" if not user else f"{user.first_name or ''} {user.last_name or ''}"
    
    text = (
        f"🛒 Текущая корзина {user_info}:\n\n"
        f"{items_text}\n\n"
        f"💳 Итого: {total} ₽"
    )
    
    await callback.message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data=f"admin_user_orders_{telegram_id}")]
        ])
    )
    await callback.answer()

@admin.callback_query(F.data == "admin_back")
async def back_to_admin(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🔍 Найти заказ", callback_data="admin_find_order")],
        [InlineKeyboardButton(text="📦 Все заказы", callback_data="admin_all_orders")],
        [InlineKeyboardButton(text="📷 Добавить фото товару", callback_data="admin_add_photo")]
    ])
    
    await callback.message.edit_text("Админ-панель:", reply_markup=keyboard)
    await callback.answer()