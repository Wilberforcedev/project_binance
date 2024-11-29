from aiogram import executor
from telegram.config_telegram import dp
from telegram.handlers import trading, welcome


async def on_startup(_):
    print('Antrade Online')


welcome.register_handlers_welcome(dp)
trading.register_handlers_trading(dp)

executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
