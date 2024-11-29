import time
from antrade.core import BinanceAPI

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
    """ Стратегия, реализующая логику пересечения быстрой и медленной скользящих средних 
    
        BUY: FastSMA пересекает снизу вверх SlowSMA
        SELL: FastSMA пересекает сверху вниз SlowSMA

        online == False - остановка алгоритма
        closed == True - продажа по рынку вручную через интерфейс
    """

    def main(self):
        global online, closed
        print('SMA Start')

        df = self.get_data()
        df['FastSMA'] = df.Close.rolling(window=6).mean()
        df['SlowSMA'] = df.Close.rolling(window=100).mean()

        trend_bull = (df.FastSMA.iloc[-1] > df.SlowSMA.iloc[-1]) \
            and (df.FastSMA.iloc[-2] < df.SlowSMA.iloc[-2])

        trend_bear = (df.FastSMA.iloc[-1] < df.SlowSMA.iloc[-1]) \
            and (df.FastSMA.iloc[-2] > df.SlowSMA.iloc[-2])

        while online:
            if not self.open_position:
                if trend_bull:
                    self.place_order('BUY')
                    break
                else:
                    print(f'{self.symbol} {df.Close.iloc[-1]} Ожидание')
                    time.sleep(60)

        if self.open_position:
            while online:
                if trend_bear or closed:
                    self.place_order('SELL')
                    break
                else:
                    print(f'Открыта позиция {self.symbol} {df.Close.iloc[-1]}')
                    time.sleep(60)


class WoodieCCI(BinanceAPI):
    """ Стратегия, описывающая трендовые паттерны WoodieCCI 
    
        Логика стратегии основывается на индикаторе CCI двух периодов: 6 и 14

        Зона покупки начинается с того момента, когда пять и более значений CCI_14 больше 0.
        BUY: CCI_6 (как отдельно CCI_6, так и вместе с CCI_14, если отрицательных значений меньше пяти) 
            пересекает значение 0 снизу вверх
        SELL: CCI_6 опускается ниже 0

        online == False - остановка алгоритма
        closed == True - продажа по рынку вручную через интерфейс
    """

    def get_cci_values(self, period: int) -> float:
        """ Расчет индикатора CCI 
        
            period (int): Период индикатора, на основании которого производится расчет значений
            return (float): Значение индикатора
        """
        df = self.get_data()
        typical_price = (df['High'] + df['Low'] + df['Close']) / 3
        rolling_mean = typical_price.rolling(window=period).mean()
        rolling_std = typical_price.rolling(window=period).std()
        indicator = round((typical_price - rolling_mean) / (0.015 * rolling_std), 2)
        return indicator

    
    def main(self):
        global online, closed
        print('Start')

        df = self.get_data()
        df['CCI_14'] = self.get_cci_values(14)
        df['CCI_6'] = self.get_cci_values(6)

        # Сигналы на покупку
        green_zone = all(cci > 0 for cci in df['CCI_14'][-5:]) or \
            (sum(1 for cci in df['CCI_14'][-5:] if cci < 0) < 5)
        green_zlr = green_zone and (
            (df.CCI_6.iloc[-2] < 0) and \
            (df.CCI_6.iloc[-1] > 0) and \
            (df.CCI_14.iloc[-1] > 0)
        )
        zero_line = df.CCI_6.iloc[-1] < 0
    
        while online:
            if not self.open_position:
                if green_zlr:
                    self.place_order('BUY')
                    break
                else:
                    print(f'{self.symbol} {df.Close.iloc[-1]} Ожидание')
                    time.sleep(60)
        if self.open_position:
            while online:
                if zero_line or closed:
                    self.place_order('SELL')
                    break
                else:
                    print(f'Открыта позиция {self.symbol} {df.Close.iloc[-1]}')
                    time.sleep(60)
                    