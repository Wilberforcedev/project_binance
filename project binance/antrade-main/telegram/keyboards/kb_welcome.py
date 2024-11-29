from aiogram.types import (
    ReplyKeyboardMarkup, 
    KeyboardButton,
)

# Главное меню
main_kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
main_description = KeyboardButton('О проекте')
main_help = KeyboardButton('Помощь')
main_balance = KeyboardButton('Баланс')
main_algorithms = KeyboardButton('Алгоритмы')
main_kb.row(main_description, main_help).row(main_balance, main_algorithms)
