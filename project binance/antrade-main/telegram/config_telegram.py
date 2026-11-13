from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage
import environs

from telegram.access_control import OwnerOnlyMiddleware

env = environs.Env()
env.read_env('.env')

# Telegram API
TELETOKEN = env('TELETOKEN')
CHAT_ID = env('CHAT_ID')

# In a private chat, Telegram's chat ID is normally the owner's user ID.
# For group chats or custom routing, set TELEGRAM_ALLOWED_USER_ID explicitly.
try:
    default_owner_user_id = int(CHAT_ID) if int(CHAT_ID) > 0 else None
except ValueError:
    default_owner_user_id = None

TELEGRAM_ALLOWED_USER_ID = env.int(
    'TELEGRAM_ALLOWED_USER_ID',
    default=default_owner_user_id,
)
if TELEGRAM_ALLOWED_USER_ID is None:
    raise RuntimeError(
        'Set TELEGRAM_ALLOWED_USER_ID to the numeric Telegram user ID allowed to control the bot'
    )

bot = Bot(TELETOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())
dp.middleware.setup(OwnerOnlyMiddleware(TELEGRAM_ALLOWED_USER_ID))
