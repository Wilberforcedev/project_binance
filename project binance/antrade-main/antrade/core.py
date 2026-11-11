import json
import uuid
from decimal import Decimal

import pandas as pd

from antrade.config_binance import CLIENT
from antrade.storage import STORE
from antrade.utils import send_message


class BinanceAPI:
    """Базовый класс для передачи данных через API Binance."""

    def __init__(self, symbol, interval, qnty):
        self.symbol = symbol
        self.interval = interval
        self.qnty = qnty
        position = STORE.get_position(symbol)
        self.open_position = position is not None
        self.position_qty = position['quantity'] if position else 0.0
        self.buy_price = position['average_price'] if position else 0.0

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
        """Get the latest spot price used for order preflight sizing."""
        ticker = CLIENT.get_symbol_ticker(symbol=self.symbol)
        return float(ticker['price'])

    def _symbol_info(self):
        info = CLIENT.get_symbol_info(self.symbol)
        if not info:
            raise ValueError(f'Unknown Binance symbol: {self.symbol}')
        return info

    @staticmethod
    def _quantity_filters(symbol_info):
        filters = {
            item.get('filterType'): item
            for item in symbol_info.get('filters', [])
        }
        lot_size = filters.get('LOT_SIZE')
        market_lot_size = filters.get('MARKET_LOT_SIZE')
        active_market_filter = market_lot_size and Decimal(
            str(market_lot_size.get('stepSize', '0'))
        ) > 0
        active_lot_filter = lot_size and Decimal(
            str(lot_size.get('stepSize', '0'))
        ) > 0
        if not active_market_filter and not active_lot_filter:
            raise ValueError('Binance symbol has no active market quantity filter')
        active = [
            item for item, enabled in (
                (lot_size, active_lot_filter),
                (market_lot_size, active_market_filter),
            ) if enabled
        ]
        return active

    @staticmethod
    def _round_market_quantity(quantity: float, symbol_info) -> float:
        active_filters = BinanceAPI._quantity_filters(symbol_info)
        # Round down on the coarser step, then verify every active filter.
        step_size = max(Decimal(str(item['stepSize'])) for item in active_filters)
        amount = Decimal(str(quantity))
        rounded = amount - (amount % step_size)
        if rounded <= 0:
            raise ValueError('Calculated order quantity is below Binance minimum')
        for item in active_filters:
            minimum = Decimal(str(item.get('minQty', '0')))
            maximum = Decimal(str(item.get('maxQty', '0')))
            item_step = Decimal(str(item.get('stepSize', '0')))
            if minimum > 0 and rounded < minimum:
                raise ValueError('Order quantity is below Binance market minimum')
            if maximum > 0 and rounded > maximum:
                raise ValueError('Order quantity exceeds Binance market maximum')
            if item_step > 0 and rounded % item_step != 0:
                raise ValueError('Order quantity does not satisfy Binance step size')
        return float(rounded)

    @staticmethod
    def _validate_market_notional(symbol_info, quantity: float, price: float):
        notional = Decimal(str(quantity)) * Decimal(str(price))
        for item in symbol_info.get('filters', []):
            filter_type = item.get('filterType')
            if filter_type == 'MIN_NOTIONAL' and item.get('applyToMarket'):
                minimum = Decimal(str(item.get('minNotional', '0')))
                if minimum and notional < minimum:
                    raise ValueError('Order value is below Binance MIN_NOTIONAL')
            elif filter_type == 'NOTIONAL':
                minimum = Decimal(str(item.get('minNotional', '0')))
                maximum = Decimal(str(item.get('maxNotional', '0')))
                if item.get('applyMinToMarket') and minimum and notional < minimum:
                    raise ValueError('Order value is below Binance NOTIONAL minimum')
                if item.get('applyMaxToMarket') and maximum and notional > maximum:
                    raise ValueError('Order value exceeds Binance NOTIONAL maximum')

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

    @staticmethod
    def _order_is_terminal(order) -> bool:
        return order.get('status') in {
            'FILLED', 'CANCELED', 'REJECTED', 'EXPIRED', 'EXPIRED_IN_MATCH'
        }

    def calculate_quantity(self) -> float:
        """Size a market BUY and preflight Binance's active quantity/notional rules."""
        symbol_info = self._symbol_info()
        price = self.get_last_price()
        order_volume = self._round_market_quantity(self.qnty / price, symbol_info)
        self._validate_market_notional(symbol_info, order_volume, price)
        return order_volume

    def _create_market_order(self, side: str, quantity: float):
        unresolved = STORE.get_unresolved_order(self.symbol)
        if unresolved:
            raise RuntimeError(
                f"Unresolved Binance order {unresolved['client_order_id']} "
                f"({unresolved['status']}); reconcile it before trading again"
            )

        client_order_id = uuid.uuid4().hex
        STORE.begin_order(client_order_id, self.symbol, side, quantity)
        try:
            order = CLIENT.create_order(
                symbol=self.symbol,
                side=side,
                type='MARKET',
                quantity=quantity,
                newClientOrderId=client_order_id,
                newOrderRespType='FULL',
            )
        except Exception:
            # A timeout can mean the exchange accepted the order. Query by the
            # idempotency key before deciding the outcome; never blindly retry.
            try:
                order = CLIENT.get_order(
                    symbol=self.symbol,
                    origClientOrderId=client_order_id,
                )
                order['fills'] = CLIENT.get_my_trades(
                    symbol=self.symbol,
                    orderId=order['orderId'],
                )
            except Exception as reconciliation_error:
                STORE.mark_order_unknown(client_order_id)
                raise RuntimeError(
                    f'Binance order outcome is unknown; order {client_order_id} '
                    'is recorded and trading is paused for this symbol'
                ) from reconciliation_error

        return order, client_order_id

    def _recover_pending_order(self) -> bool:
        pending = STORE.get_unresolved_order(self.symbol)
        if not pending:
            return False

        client_order_id = pending['client_order_id']
        try:
            order = CLIENT.get_order(
                symbol=self.symbol,
                origClientOrderId=client_order_id,
            )
            order['fills'] = CLIENT.get_my_trades(
                symbol=self.symbol,
                orderId=order['orderId'],
            )
        except Exception as error:
            STORE.mark_order_unknown(client_order_id)
            raise RuntimeError(
                f'Cannot reconcile Binance order {client_order_id}; '
                'trading remains paused for this symbol'
            ) from error

        status = order.get('status', 'UNKNOWN')
        if not self._order_is_terminal(order):
            STORE.mark_order_unknown(client_order_id)
            raise RuntimeError(
                f'Binance order {client_order_id} is still {status}; '
                'trading remains paused for this symbol'
            )

        symbol_info = self._symbol_info()
        base_asset = symbol_info['baseAsset']
        executed_qty = Decimal(str(order.get('executedQty', '0')))
        current_position = STORE.get_position(self.symbol)
        current_qty = Decimal(str(current_position['quantity'])) if current_position else Decimal('0')
        average_price = current_position['average_price'] if current_position else 0.0

        if pending['side'] == 'BUY' and executed_qty > 0:
            current_qty += executed_qty - self._base_commission(order, base_asset)
            average_price = self._average_fill_price(order)
        elif pending['side'] == 'SELL' and executed_qty > 0:
            consumed_qty = executed_qty + self._base_commission(order, base_asset)
            current_qty = max(Decimal('0'), current_qty - consumed_qty)

        self.position_qty = float(current_qty)
        self.buy_price = average_price
        self.open_position = self.position_qty > 0
        STORE.complete_order_and_position(
            client_order_id,
            order,
            self.symbol,
            self.position_qty,
            self.buy_price,
        )
        return True

    def place_order(self, order_side: str):
        """Place a market order and track the quantity actually filled."""
        # Recover an order whose response or local state write was interrupted.
        # Skip this signal cycle after reconciliation; never issue a second order.
        if self._recover_pending_order():
            return

        symbol_info = self._symbol_info()
        base_asset = symbol_info['baseAsset']

        if order_side == 'BUY':
            if self.open_position:
                raise RuntimeError(f'An open {self.symbol} position already exists')
            quantity = self.calculate_quantity()
            order, client_order_id = self._create_market_order('BUY', quantity)
            if not self._order_is_terminal(order):
                STORE.mark_order_unknown(client_order_id)
                raise RuntimeError(
                    f'Binance BUY order {client_order_id} is still '
                    f"{order.get('status', 'UNKNOWN')}; trading is paused for this symbol"
                )
            executed_qty = Decimal(str(order.get('executedQty', '0')))
            acquired_qty = executed_qty - self._base_commission(order, base_asset)
            self.position_qty = float(acquired_qty)
            if self.position_qty <= 0:
                raise RuntimeError('BUY order filled no sellable base-asset quantity')

            self.buy_price = self._average_fill_price(order)
            self.open_position = True
            STORE.complete_order_and_position(
                client_order_id,
                order,
                self.symbol,
                self.position_qty,
                self.buy_price,
            )
            message = f'{self.symbol} \n Buy \n {self.buy_price}'
            send_message(message)
            print(message)
            print(json.dumps(order, indent=4, sort_keys=True))

        elif order_side == 'SELL':
            if not self.open_position:
                raise RuntimeError(f'No stored {self.symbol} position is available to sell')
            quantity = self._round_market_quantity(self.position_qty, symbol_info)
            if quantity <= 0:
                raise ValueError('There is no sellable position quantity')

            order, client_order_id = self._create_market_order('SELL', quantity)
            if not self._order_is_terminal(order):
                STORE.mark_order_unknown(client_order_id)
                raise RuntimeError(
                    f'Binance SELL order {client_order_id} is still '
                    f"{order.get('status', 'UNKNOWN')}; trading is paused for this symbol"
                )
            executed_qty = Decimal(str(order.get('executedQty', '0')))
            if executed_qty <= 0:
                raise RuntimeError('SELL order filled no quantity')

            consumed_qty = executed_qty + self._base_commission(order, base_asset)
            remaining_qty = max(
                Decimal('0'),
                Decimal(str(self.position_qty)) - consumed_qty,
            )
            self.position_qty = float(remaining_qty)
            self.open_position = self.position_qty > 0

            sell_price = self._average_fill_price(order)
            STORE.complete_order_and_position(
                client_order_id,
                order,
                self.symbol,
                self.position_qty,
                self.buy_price,
            )
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
