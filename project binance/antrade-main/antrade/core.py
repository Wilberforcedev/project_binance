import pandas as pd
import json
from binance.helpers import round_step_size
from antrade.utils import round_float
from antrade.config_binance import CLIENT
from antrade.utils import send_message


class BinanceAPI:
    """ Базовый класс, источник передачи данных через API Binance
    """

    def __init__(self, symbol, interval, qnty):
        """ Конструктор класса BinanceAPI
            symbol (str): Наименование тикера
            interval (str): Временной интервал
            qnty (float): Размер ордера
            open_position (bool): Состояние, в котором находится алгоритм:
                                если нет открытой позиции, значение атрибута - False,
                                если ордер открыт - True
        """
        self.symbol = symbol
        self.interval = interval
        self.qnty = qnty
        self.open_position = False

    
    def get_data(self):
        """ Получение данных 
        """
        df = pd.DataFrame(CLIENT.get_historical_klines(symbol=self.symbol, interval=self.interval, limit=70))
        df = df.iloc[:,:5]
        df.columns = ['Time', 'Open', 'High', 'Low', 'Close']
        df = df.set_index('Time')
        df.index = pd.to_datetime(df.index, unit='ms')
        df = df.astype(float)
        return df
    

    def get_last_price(self) -> float:
        """ Вывод цены закрытия последней свечи 
        """
        df = self.get_data()
        return df.Close.iloc[-1]


    def calculate_quantity(self) -> float:
        """ Расчет объема ордера 
        """
        symbol_info = CLIENT.get_symbol_info(self.symbol)
        step_size = symbol_info.get('filters')[1]['stepSize']
        order_volume = self.qnty / self.get_last_price()
        order_volume = round_step_size(order_volume, step_size)
        return order_volume


    def place_order(self, order_side: str):
        """ Размещение ордеров

            order_side (str): Направление ордера, передаваемое при вызове функции в алгоритме.
        """

        if order_side == 'BUY':
            order = CLIENT.create_order(
                symbol=self.symbol, 
                side='BUY', 
                type='MARKET', 
                quantity=self.calculate_quantity(),
            )
            self.open_position = True
            self.buy_price = round(
                float(order.get('fills')[0]['price']), 
                round_float(num=self.get_last_price())
            )
            message = f'{self.symbol} \n Buy \n {self.buy_price}'
            send_message(message)
            print(message)
            print(json.dumps(order, indent=4, sort_keys=True))

        elif order_side == 'SELL':
            order = CLIENT.create_order(
                symbol=self.symbol, 
                side='SELL', 
                type='MARKET', 
                quantity=self.calculate_quantity(),
            )
            self.open_position = False
            self.sell_price = round(
                float(order.get('fills')[0]['price']), 
                round_float(num=self.get_last_price())
            )
            result = round(((self.sell_price - self.buy_price) * self.calculate_quantity()), 2)
            message = f'{self.symbol} \n Sell \n {self.sell_price} \n Результат: {result} USDT'
            send_message(message)
            print(message)
            print(json.dumps(order, indent=4, sort_keys=True))
