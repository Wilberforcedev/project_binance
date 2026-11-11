import math
import threading

from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from aiogram.types import ReplyKeyboardRemove
from aiogram.dispatcher.filters.state import StatesGroup, State

from antrade.algorithms import bot_closed, bot_off, bot_on, ManualTrading, SMA, WoodieCCI
from antrade.utils import symbol_list, get_balance_ticker
from telegram.config_telegram import bot, CHAT_ID
from telegram.templates import (
    STATE_ALGO, STATE_SYMBOL, STATE_INTERVAL, STATE_QNTY, STATE_QNTY_MAX_VALUE_ERROR,
    STATE_QNTY_MIN_VALUE_ERROR, STATE_QNTY_TYPE_ERROR, STATE_VALID_ERROR,
    ORDER_EXCEPTION, CLOSE_EXCEPTION
)
from telegram.keyboards.kb_trading import algorithm_kb, symbol_kb, interval_kb, start_kb, stop_kb
from telegram.keyboards.kb_welcome import main_kb


class TradeStateGroup(StatesGroup):
    """Состояния настройки алгоритма и торговой сессии."""
    algorithm = State()
    symbol = State()
    interval = State()
    qnty = State()
    start = State()
    stop = State()


async def get_algorithms(message: types.Message):
    """Открыть меню выбора алгоритма."""
    await TradeStateGroup.algorithm.set()
    await bot.send_message(
        chat_id=CHAT_ID,
        text=STATE_ALGO,
        parse_mode="HTML",
        reply_markup=algorithm_kb
    )
    await message.delete()


async def cancel_handler(message: types.Message, state: FSMContext):
    """Отменить настройку."""
    current_state = await state.get_state()
    if current_state is None:
        return
    await state.finish()
    await bot.send_message(chat_id=CHAT_ID, text='Отменено')


async def algorithm_callback(callback: types.CallbackQuery, state: FSMContext):
    async with state.proxy() as data:
        if callback.data in ['Test', 'SMA', 'WoodieCCI']:
            data['algorithm'] = callback.data
            await TradeStateGroup.next()
            await bot.send_message(
                chat_id=CHAT_ID,
                text=STATE_SYMBOL,
                parse_mode="HTML",
                reply_markup=symbol_kb
            )
        else:
            await state.finish()
            await bot.send_message(
                chat_id=CHAT_ID,
                text=STATE_VALID_ERROR,
                parse_mode="HTML",
                reply_markup=main_kb
            )


async def symbol_callback(callback: types.CallbackQuery, state: FSMContext):
    async with state.proxy() as data:
        if callback.data in symbol_list:
            data['symbol'] = callback.data
            await TradeStateGroup.next()
            await bot.send_message(
                chat_id=CHAT_ID,
                text=STATE_INTERVAL,
                parse_mode="HTML",
                reply_markup=interval_kb
            )
        else:
            await state.finish()
            await bot.send_message(
                chat_id=CHAT_ID,
                text=STATE_VALID_ERROR,
                parse_mode="HTML",
                reply_markup=main_kb
            )


async def interval_callback(callback: types.CallbackQuery, state: FSMContext):
    async with state.proxy() as data:
        if callback.data in ['1m', '5m', '15m', '30m', '1h', '4h', '1d']:
            data['interval'] = callback.data
            await TradeStateGroup.next()
            await bot.send_message(
                chat_id=CHAT_ID,
                text=STATE_QNTY,
                parse_mode="HTML",
                reply_markup=ReplyKeyboardRemove()
            )
        else:
            await state.finish()
            await bot.send_message(
                chat_id=CHAT_ID,
                text=STATE_VALID_ERROR,
                parse_mode="HTML",
                reply_markup=main_kb
            )


async def qnty_message(message: types.Message, state: FSMContext):
    """Validate the USDT budget; keep the user in this state when input is invalid."""
    async with state.proxy() as data:
        try:
            quantity_float = float(message.text)
        except (TypeError, ValueError):
            await bot.send_message(
                chat_id=CHAT_ID,
                text=STATE_QNTY_TYPE_ERROR,
                parse_mode="HTML"
            )
            return

        if not math.isfinite(quantity_float):
            await bot.send_message(
                chat_id=CHAT_ID,
                text=STATE_QNTY_TYPE_ERROR,
                parse_mode="HTML"
            )
            return

        if quantity_float < 15:
            await bot.send_message(
                chat_id=CHAT_ID,
                text=STATE_QNTY_MIN_VALUE_ERROR,
                parse_mode="HTML"
            )
            return

        balance = get_balance_ticker('USDT')
        if quantity_float >= balance:
            await bot.send_message(
                chat_id=CHAT_ID,
                text=STATE_QNTY_MAX_VALUE_ERROR,
                parse_mode="HTML"
            )
            return

        data['qnty'] = quantity_float
        await TradeStateGroup.next()
        STATE_RESULT = (
            f"Алгоритм: {data['algorithm']} \n"
            f"Тикер: {data['symbol']} \n"
            f"Таймфрейм: {data['interval']} \n"
            f"Объем USDT: {data['qnty']}"
        )
        await bot.send_message(
            chat_id=CHAT_ID,
            text=STATE_RESULT,
            reply_markup=start_kb
        )


async def start_callback(callback: types.CallbackQuery, state: FSMContext):
    async with state.proxy() as data:
        try:
            data['start'] = callback.data
            algorithm = data['algorithm']
            if data['start'] == 'start':
                if algorithm == 'Test':
                    state_data = ManualTrading(data['symbol'], data['interval'], data['qnty'])
                elif algorithm == 'SMA':
                    state_data = SMA(data['symbol'], data['interval'], data['qnty'])
                elif algorithm == 'WoodieCCI':
                    state_data = WoodieCCI(data['symbol'], data['interval'], data['qnty'])
                else:
                    raise ValueError(f'Unsupported algorithm: {algorithm}')

                bot_on()

                def work():
                    state_data.main()

                thread_work = threading.Thread(target=work, daemon=True)
                thread_work.start()

                await TradeStateGroup.next()
                STATE_START = f'{algorithm} начал свою работу'
                await callback.answer(STATE_START)
                await bot.send_message(
                    chat_id=CHAT_ID,
                    text=STATE_START,
                )
        except Exception:
            await state.finish()
            print('Ошибка старта')
            await bot.send_message(
                chat_id=CHAT_ID,
                text=ORDER_EXCEPTION,
                parse_mode="HTML",
                reply_markup=main_kb
            )


async def manage_message(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        algorithm = data.get('algorithm')
        if message.text == 'Продать' and algorithm:
            try:
                bot_closed()
                await TradeStateGroup.last()
                STATE_CLOSED = f'Совершена ручная продажа по {algorithm}'
                await bot.send_message(
                    chat_id=CHAT_ID,
                    text=STATE_CLOSED
                )
                await message.delete()
            except Exception:
                await bot.send_message(
                    chat_id=CHAT_ID,
                    text=CLOSE_EXCEPTION,
                    parse_mode="HTML"
                )
                await message.delete()
        if message.text == 'Стоп' and algorithm:
            STATE_STOP_MESSAGE = f'\U0001F6D1 Вы действительно хотите остановить {algorithm}?'
            await bot.send_message(
                chat_id=CHAT_ID,
                text=STATE_STOP_MESSAGE,
                reply_markup=stop_kb
            )
            await message.delete()


async def stop_callback(callback: types.CallbackQuery, state: FSMContext):
    async with state.proxy() as data:
        data['stop'] = callback.data
        algorithm = data.get('algorithm')
        if data['stop'] == 'continue':
            STATE_CONTINUE = f'{algorithm} продолжает работу'
            await bot.send_message(
                chat_id=CHAT_ID,
                text=STATE_CONTINUE,
            )
        elif data['stop'] == 'stop':
            bot_off()
            STATE_STOP = f'{algorithm} закончил свою работу'
            await bot.send_message(
                chat_id=CHAT_ID,
                text=STATE_STOP,
                reply_markup=main_kb
            )
            await state.finish()


def register_handlers_trading(dp: Dispatcher):
    dp.register_message_handler(get_algorithms, text='Алгоритмы', state=None)
    dp.register_message_handler(cancel_handler, state="*", text='Отмена')
    dp.register_message_handler(cancel_handler, Text(equals='Отмена', ignore_case=True), state="*")
    dp.register_callback_query_handler(algorithm_callback, state=TradeStateGroup.algorithm)
    dp.register_callback_query_handler(symbol_callback, state=TradeStateGroup.symbol)
    dp.register_callback_query_handler(interval_callback, state=TradeStateGroup.interval)
    dp.register_message_handler(qnty_message, state=TradeStateGroup.qnty)
    dp.register_callback_query_handler(start_callback, state=TradeStateGroup.start)
    dp.register_message_handler(manage_message, state="*")
    dp.register_callback_query_handler(stop_callback, state=TradeStateGroup.stop)
