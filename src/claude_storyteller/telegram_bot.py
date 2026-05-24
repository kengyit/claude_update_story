from __future__ import annotations

import asyncio
import logging

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import RetryAfter, TelegramError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

log = logging.getLogger(__name__)


class TelegramSender:
    def __init__(self, token: str, chat_id: str) -> None:
        self._bot = Bot(token=token)
        self._chat_id = chat_id

    @retry(
        retry=retry_if_exception_type(TelegramError),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        reraise=True,
    )
    async def _send_async(self, text: str) -> int:
        try:
            msg = await self._bot.send_message(
                chat_id=self._chat_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True,
            )
            return msg.message_id
        except RetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 1)
            raise

    def send(self, text: str) -> int:
        return asyncio.run(self._send_async(text))
