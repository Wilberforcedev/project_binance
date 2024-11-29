from binance.client import Client
import environs

env = environs.Env()
env.read_env('.env')

# Binance API Spot
CLIENT = Client(env('API_KEY'), env('SECRET_KEY'), {'verify': True, 'timeout': 20})
