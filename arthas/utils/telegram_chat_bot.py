import time
import logging
from io import BufferedReader
from typing import Union

from telegram import Bot, Message
from telegram.ext import Updater, CallbackContext

logger = logging.getLogger("Telegram bot")


class TelegramChatBot:
    def __init__(self, channel: str, token: str):
        self.channel = channel

        self.updater = Updater(token)
        self.bot: Bot = self.updater.bot

        self.updater.dispatcher.add_error_handler(self.error_handler)

        self.previous_query_time: float = 0
        self.query_timeout: float = 1.0

    def send_message(self, text: str) -> Message:
        logger.info("Sending message with text: {}".format(text))

        self.ensure_timeout()
        return self.bot.send_message(chat_id="@{}".format(self.channel), text=text, disable_web_page_preview=True)

    def edit_message(self, message_id: str, text: str) -> Union[Message, bool]:
        logger.info("Editing message with id={}, new text: {}".format(message_id, text))

        self.ensure_timeout()
        return self.bot.edit_message_text(chat_id="@{}".format(self.channel), text=text, message_id=message_id)

    def send_photo(self, photo_file: BufferedReader) -> Message:
        return self.bot.send_photo("@{}".format(self.channel), photo=photo_file)

    def ensure_timeout(self) -> None:
        current_time = time.time()
        passed = current_time - self.previous_query_time

        if passed < self.query_timeout:
            # logger.debug("Faced timeout!")
            time.sleep(1.1 * self.query_timeout - passed)

        self.previous_query_time = current_time

    def start(self) -> None:
        self.updater.start_polling(read_latency=10)

    def stop(self) -> None:
        self.updater.stop()

    def join(self) -> None:
        self.updater.idle()

    @staticmethod
    def error_handler(update: object, context: CallbackContext) -> None:
        logger.error('Update "%s" caused error "%s"', update, context.error)
