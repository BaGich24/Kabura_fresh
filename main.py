import asyncio
import time
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramNetworkError
from app.config import BOT_TOKEN
from app.database import Database
from app.handlers import router
from app.admin_handlers import admin
from app.middlewares import DBSessionMiddleware

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    db = Database()
    
    max_retries = 5
    retry_delay = 5
    
    try:
        await db.init()
        dp.include_router(router)
        dp.include_router(admin)
        dp["db"] = db
        dp.message.middleware(DBSessionMiddleware(db.async_session))
        dp.callback_query.middleware(DBSessionMiddleware(db.async_session))

        for attempt in range(max_retries):
            try:
                print(f"Попытка подключиться к Telegram (попытка {attempt + 1}/{max_retries})...")
                await dp.start_polling(bot)
                break
            except TelegramNetworkError as e:
                print(f"Ошибка подключения: {e}")
                if attempt < max_retries - 1:
                    print(f"Переподключение через {retry_delay} секунд...")
                    await asyncio.sleep(retry_delay)
                else:
                    print(f"Не удалось подключиться после {max_retries} попыток.")
                    raise
        
    except Exception:
        import traceback
        traceback.print_exc()
        raise
    finally:
        await db.close()
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("\n✋ Бот остановлен.")
    except Exception:
        import traceback
        traceback.print_exc()