"""Durable order and position state for recovery after a process restart."""

import os
import sqlite3
from pathlib import Path


class TradingStore:
    def __init__(self, database_path: str | None = None):
        self.database_path = database_path or os.environ.get(
            'ANTRADE_DB_PATH', 'data/antrade.sqlite3'
        )
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA busy_timeout = 30000')
        return connection

    def _initialize(self):
        with self._connect() as connection:
            connection.execute('PRAGMA journal_mode = WAL')
            connection.execute(
                '''CREATE TABLE IF NOT EXISTS positions (
                    symbol TEXT PRIMARY KEY,
                    quantity TEXT NOT NULL,
                    average_price TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )'''
            )
            connection.execute(
                '''CREATE TABLE IF NOT EXISTS orders (
                    client_order_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    requested_quantity TEXT NOT NULL,
                    status TEXT NOT NULL,
                    exchange_order_id TEXT,
                    executed_quantity TEXT NOT NULL DEFAULT '0',
                    quote_quantity TEXT NOT NULL DEFAULT '0',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )'''
            )
            # A process restart or simultaneous bot workers must not allow a
            # second order for the same symbol while an earlier order is open.
            connection.execute(
                '''CREATE UNIQUE INDEX IF NOT EXISTS one_unresolved_order_per_symbol
                   ON orders(symbol)
                   WHERE status IN ('PENDING', 'UNKNOWN', 'NEW', 'PARTIALLY_FILLED')'''
            )

    def get_position(self, symbol: str):
        with self._connect() as connection:
            row = connection.execute(
                'SELECT quantity, average_price FROM positions WHERE symbol = ?',
                (symbol,),
            ).fetchone()
        if row is None:
            return None
        return {
            'quantity': float(row['quantity']),
            'average_price': float(row['average_price']),
        }

    def save_position(self, symbol: str, quantity: float, average_price: float):
        with self._connect() as connection:
            if quantity <= 0:
                connection.execute('DELETE FROM positions WHERE symbol = ?', (symbol,))
                return
            connection.execute(
                '''INSERT INTO positions(symbol, quantity, average_price, updated_at)
                   VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(symbol) DO UPDATE SET
                     quantity = excluded.quantity,
                     average_price = excluded.average_price,
                     updated_at = CURRENT_TIMESTAMP''',
                (symbol, str(quantity), str(average_price)),
            )

    def begin_order(
        self,
        client_order_id: str,
        symbol: str,
        side: str,
        requested_quantity: float,
    ):
        with self._connect() as connection:
            connection.execute(
                '''INSERT INTO orders(
                     client_order_id, symbol, side, requested_quantity, status
                   ) VALUES (?, ?, ?, ?, 'PENDING')''',
                (client_order_id, symbol, side, str(requested_quantity)),
            )

    def complete_order_and_position(
        self,
        client_order_id: str,
        order: dict,
        symbol: str,
        quantity: float,
        average_price: float,
    ):
        status = order.get('status', 'UNKNOWN')
        if status in ('NEW', 'PARTIALLY_FILLED', 'UNKNOWN'):
            status = 'UNKNOWN'
        with self._connect() as connection:
            connection.execute(
                '''UPDATE orders SET status = ?, exchange_order_id = ?,
                   executed_quantity = ?, quote_quantity = ?,
                   updated_at = CURRENT_TIMESTAMP WHERE client_order_id = ?''',
                (
                    status,
                    str(order.get('orderId', '')) or None,
                    str(order.get('executedQty', '0')),
                    str(order.get('cummulativeQuoteQty', '0')),
                    client_order_id,
                ),
            )
            if quantity <= 0:
                connection.execute('DELETE FROM positions WHERE symbol = ?', (symbol,))
            else:
                connection.execute(
                    '''INSERT INTO positions(symbol, quantity, average_price, updated_at)
                       VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                       ON CONFLICT(symbol) DO UPDATE SET
                         quantity = excluded.quantity,
                         average_price = excluded.average_price,
                         updated_at = CURRENT_TIMESTAMP''',
                    (symbol, str(quantity), str(average_price)),
                )

    def mark_order_unknown(self, client_order_id: str):
        with self._connect() as connection:
            connection.execute(
                '''UPDATE orders SET status = 'UNKNOWN',
                   updated_at = CURRENT_TIMESTAMP WHERE client_order_id = ?''',
                (client_order_id,),
            )

    def get_unresolved_order(self, symbol: str):
        with self._connect() as connection:
            row = connection.execute(
                '''SELECT client_order_id, side, status, requested_quantity FROM orders
                   WHERE symbol = ? AND status IN ('PENDING', 'UNKNOWN', 'NEW', 'PARTIALLY_FILLED')
                   ORDER BY updated_at DESC LIMIT 1''',
                (symbol,),
            ).fetchone()
        return dict(row) if row else None


STORE = TradingStore()
