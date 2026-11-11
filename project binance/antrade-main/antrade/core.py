import json
from decimal import Decimal

import pandas as pd
from binance.helpers import round_step_size

from antrade.config_binance import CLIENT
from antrade.utils import round_float, send_message


class BinanceAPI:
    """Базовый класс для передачи данных через API Binance."""

    def __init__(self, symbol, interval, qnty):
        self.symbol = symbol
        self.interval = interval
        self.qnty = qnty
        self.open_position = False
        self.position_qty = 0.0
        self.buy_price = 0.0

    def get_data(self, limit: int = 70):
        """Получить последние свечи."""
        candles = CLIENT.get_historical_klines(
            symbol=self.symbol,
            interval=self.interval,
            limit=limit,
        )
        df = pd.DataFrame(candles)
        df = df.iloc[:, :5]
        df.columns = ['Time', 'Open', 'High', 'Low', 'Close']
        df = df.set_index('Time')
        df.index = pd.to_datetime(df.index, unit='ms')
        return df.astype(float)

    def get_last_price(self) -> float:
        """Получить цену закрытия последней свечи."""
        df = self.get_data()
        if df.empty:
            raise ValueError(f'Binance returned no candles for {self.symbol}')
        return float(df.Close.iloc[-1])

    def _symbol_info(self):
        info = CLIENT.get_symbol_info(self.symbol)
        if not info:
            raise ValueError(f'Unknown Binance symbol: {self.symbol}')
        return info

    @staticmethod
    def _lot_size_filter(symbol_info):
        lot_size = next(
            (
                item for item in symbol_info.get('filters', [])
                if item.get('filterType') == 'LOT_SIZE'
            ),
            None,
        )
        if lot_size is None:
            raise ValueError('Binance symbol has no LOT_SIZE filter')
        return lot_size

    @staticmethod
    def _base_commission(order, base_asset):
        return sum(
            (
                Decimal(str(fill.get('commission', '0')))
                for fill in (order.get('fills') or [])
                if fill.get('commissionAsset') == base_asset
            ),
            Decimal('0'),
        )

    @staticmethod
    def _average_fill_price(order):
        executed_qty = Decimal(str(order.get('executedQty', '0')))
        if executed_qty <= 0:
            raise RuntimeError('Binance order has no executed quantity')

        quote_qty = Decimal(str(order.get('cummulativeQuoteQty', '0')))
        if quote_qty <= 0:
            fills = order.get('fills') or []
            quote_qty = sum(
                (
                    Decimal(str(fill.get('qty', '0')))
                    * Decimal(str(fill.get('price', '0')))
                    for fill in fills
                ),
                Decimal('0'),
            )
        if quote_qty <= 0:
            raise RuntimeError('Binance order has no executed quote value')
        return float(quote_qty / executed_qty)

    def calculate_quantity(self) -> float:
        """Calculate the BUY quantity and round using Binance's LOT_SIZE filter."""
        symbol_info = self._symbol_info()
        lot_size = self._lot_size_filter(symbol_info)
        order_volume = self.qnty / self.get_last_price()
        order_volume = round_step_size(order_volume, lot_size['stepSize'])
        if order_volume <= 0:
            raise ValueError('Calculated order quantity is below Binance LOT_SIZE')
        return order_volume

    def place_order(self, order_side: str):
        """Place a market order and track the quantity actually filled."""
        symbol_info = self._symbol_info()
        lot_size = self._lot_size_filter(symbol_info)
        step_size = lot_size['stepSize']
        base_asset = symbol_info['baseAsset']

        if order_side == 'BUY':
            order = CLIENT.create_order(
                symbol=self.symbol,
                side='BUY',
                type='MARKET',
                quantity=self.calculate_quantity(),
                newOrderRespType='FULL',
            )
            executed_qty = Decimal(str(order.get('executedQty', '0')))
            acquired_qty = executed_qty - self._base_commission(order, base_asset)
            self.position_qty = round_step_size(
                float(acquired_qty),
                step_size,
            )
            if self.position_qty <= 0:
                raise RuntimeError('BUY order filled no sellable base-asset quantity')

            self.buy_price = self._average_fill_price(order)
            self.open_position = True
            message = f'{self.symbol} \n Buy \n {self.buy_price}'
            send_message(message)
            print(message)
            print(json.dumps(order, indent=4, sort_keys=True))

        elif order_side == 'SELL':
            quantity = round_step_size(self.position_qty, step_size)
            if quantity <= 0:
                raise ValueError('There is no sellable position quantity')

            order = CLIENT.create_order(
                symbol=self.symbol,
                side='SELL',
                type='MARKET',
                quantity=quantity,
                newOrderRespType='FULL',
            )
            executed_qty = Decimal(str(order.get('executedQty', '0')))
            if executed_qty <= 0:
                raise RuntimeError('SELL order filled no quantity')

            consumed_qty = executed_qty + self._base_commission(order, base_asset)
            remaining_qty = max(
                Decimal('0'),
                Decimal(str(self.position_qty)) - consumed_qty,
            )
            self.position_qty = round_step_size(float(remaining_qty), step_size)
            self.open_position = self.position_qty > 0

            sell_price = self._average_fill_price(order)
            result = round(
                (sell_price - self.buy_price) * float(executed_qty),
                2,
            )
            message = (
                f'{self.symbol} \n Sell \n {sell_price}'
                f' \n Gross result before fees: {result} USDT'
            )
            send_message(message)
            print(message)
            print(json.dumps(order, indent=4, sort_keys=True))
