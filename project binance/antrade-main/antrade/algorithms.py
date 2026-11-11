import time
from antrade.core import BinanceAPI

online = True
closed = False


def bot_on():
    global online, closed
    online = True
    closed = False


def bot_off():
    global online
    online = False


def bot_closed():
    global closed
    closed = True


class ManualTrading(BinanceAPI):

    def main(self):
        global online, closed
        print('Manual Start')
        while online:
            if not self.open_position:
                self.place_order('BUY')
                break
        if self.open_position:
            while online:
                if closed:
                    self.place_order('SELL')
                    closed = False
                    break


class SMA(BinanceAPI):
    """Стратегия пересечения быстрой и медленной скользящих средних."""

    def main(self):
        global online, closed
        print('SMA Start')

        while online:
            # 101 candles are needed to compare two consecutive 100-period SMA values.
            df = self.get_data(limit=101)
            if len(df) < 101:
                print(f'{self.symbol}: недостаточно данных для SMA')
                time.sleep(60)
                continue

            df['FastSMA'] = df.Close.rolling(window=6).mean()
            df['SlowSMA'] = df.Close.rolling(window=100).mean()

            trend_bull = (
                df.FastSMA.iloc[-1] > df.SlowSMA.iloc[-1]
                and df.FastSMA.iloc[-2] < df.SlowSMA.iloc[-2]
            )
            trend_bear = (
                df.FastSMA.iloc[-1] < df.SlowSMA.iloc[-1]
                and df.FastSMA.iloc[-2] > df.SlowSMA.iloc[-2]
            )

            if not self.open_position:
                if trend_bull:
                    self.place_order('BUY')
                else:
                    print(f'{self.symbol} {df.Close.iloc[-1]} Ожидание')
            elif trend_bear or closed:
                self.place_order('SELL')
                closed = False
            else:
                print(f'Открыта позиция {self.symbol} {df.Close.iloc[-1]}')

            time.sleep(60)


class WoodieCCI(BinanceAPI):
    """Стратегия WoodieCCI на индикаторах CCI с периодами 6 и 14."""

    def get_cci_values(self, period: int, df=None):
        """Расчет индикатора CCI для уже загруженных свечей."""
        if df is None:
            df = self.get_data()
        typical_price = (df['High'] + df['Low'] + df['Close']) / 3
        rolling_mean = typical_price.rolling(window=period).mean()
        rolling_std = typical_price.rolling(window=period).std()
        return round((typical_price - rolling_mean) / (0.015 * rolling_std), 2)

    def main(self):
        global online, closed
        print('WoodieCCI Start')

        while online:
            df = self.get_data(limit=70)
            df['CCI_14'] = self.get_cci_values(14, df)
            df['CCI_6'] = self.get_cci_values(6, df)

            recent_cci14 = df['CCI_14'].iloc[-5:]
            green_zone = all(cci > 0 for cci in recent_cci14) or (
                sum(1 for cci in recent_cci14 if cci < 0) < 5
            )
            green_zlr = green_zone and (
                df.CCI_6.iloc[-2] < 0
                and df.CCI_6.iloc[-1] > 0
                and df.CCI_14.iloc[-1] > 0
            )
            zero_line = df.CCI_6.iloc[-1] < 0

            if not self.open_position:
                if green_zlr:
                    self.place_order('BUY')
                else:
                    print(f'{self.symbol} {df.Close.iloc[-1]} Ожидание')
            elif zero_line or closed:
                self.place_order('SELL')
                closed = False
            else:
                print(f'Открыта позиция {self.symbol} {df.Close.iloc[-1]}')

            time.sleep(60)
