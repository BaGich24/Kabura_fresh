# Kabura Fresh Bot

Телеграм-бот для магазина свежих продуктов Kabura Fresh.

## Функциональность

- 📋 Каталог товаров с категориями
- 🛒 Корзина покупок
- 💳 Оформление заказов
- � Управление товарами и ценами через базу данных
- 👨‍💼 Админ-панель для управления товарами и заказами

## Установка

1. Клонируйте репозиторий:
```bash
git clone https://github.com/your-username/kabura-fresh.git
cd kabura-fresh
```

2. Создайте виртуальное окружение и активируйте его:
```bash
python -m venv venv
source venv/bin/activate  # для Linux/Mac
venv\Scripts\activate     # для Windows
```

3. Установите зависимости:
```bash
pip install -r requirements.txt
```

4. Создайте файл `.env` в корневой директории проекта со следующими переменными:
```env
BOT_TOKEN=your_bot_token
ADMIN_IDS=your_admin_id
NOTIFICATION_CHAT_ID=your_notification_chat_id
```

## Запуск

1. Активируйте виртуальное окружение (если еще не активировано):
```bash
source venv/bin/activate  # для Linux/Mac
venv\Scripts\activate     # для Windows
```

2. Запустите бота:
```bash
python main.py
```

## Структура проекта

- `main.py` - основной файл бота
- `handlers.py` - обработчики команд и callback-запросов
- `keyboards.py` - клавиатуры для бота
- `database.py` - работа с базой данных
- `config.py` - конфигурация бота

## Команды бота

- `/start` - начать работу с ботом
- `/admin` - доступ к админ-панели (только для администраторов)
- `/prices` - просмотр текущих цен из базы данных
- `/update_price` - обновление цен товара в базе данных (только для администраторов)

## Лицензия

MIT 