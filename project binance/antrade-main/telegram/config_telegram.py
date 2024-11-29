from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage
import environs

env = environs.Env()
env.read_env('.env')

# Telegram API
TELETOKEN = env('TELETOKEN')
CHAT_ID = env('CHAT_ID')
bot = Bot(TELETOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())
