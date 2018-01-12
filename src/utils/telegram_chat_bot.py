import time
import logging
from telegram.ext import Updater

logger = logging.getLogger("Telegram bot")


class TelegramChatBot:
    def __init__(self, channel, token):
        self.channel = channel

        self.updater = Updater(token)
        self.bot = self.updater.bot

        dispatcher = self.updater.dispatcher
        dispatcher.add_error_handler(self.error_handler)

        self.previous_query_time = 0
        self.query_timeout = 1.0

    def send_message(self, text):
        logger.info("Sending message with text: {}".format(text))

        self.ensure_timeout()
        return self.bot.send_message(chat_id="@{}".format(self.channel), text=text, disable_web_page_preview=True)

    def edit_message(self, message_id, text):
        logger.info("Editing message with id={}, new text: {}".format(message_id, text))

        self.ensure_timeout()
        return self.bot.edit_message_text(chat_id="@{}".format(self.channel), text=text, message_id=message_id)

    def send_photo(self, photo_file):
        return self.bot.send_photo("@{}".format(self.channel), photo=photo_file)

    def ensure_timeout(self):
        current_time = time.time()
        passed = current_time - self.previous_query_time

        if passed < self.query_timeout:
            # logger.debug("Faced timeout!")
            time.sleep(1.1 * self.query_timeout - passed)

        self.previous_query_time = current_time

    def start(self):
        self.updater.start_polling(read_latency=10)

    def stop(self):
        self.updater.stop()

    def join(self):
        self.updater.idle()

    @staticmethod
    def error_handler(bot, update, error):
        logger.error('Update "%s" caused error "%s"', update, error)
