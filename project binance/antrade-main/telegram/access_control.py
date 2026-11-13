from aiogram.dispatcher.handler import CancelHandler
from aiogram.dispatcher.middlewares import BaseMiddleware


class OwnerOnlyMiddleware(BaseMiddleware):
    """Reject Telegram updates not sent by the configured bot owner."""

    def __init__(self, owner_user_id: int):
        super().__init__()
        self.owner_user_id = owner_user_id

    async def on_pre_process_message(self, message, data):
        sender = getattr(message, "from_user", None)
        if sender is None or sender.id != self.owner_user_id:
            raise CancelHandler()

    async def on_pre_process_callback_query(self, callback_query, data):
        sender = getattr(callback_query, "from_user", None)
        if sender is None or sender.id != self.owner_user_id:
            raise CancelHandler()
