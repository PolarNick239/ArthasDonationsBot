import logging

import click

from arthas.utils.arthas_bot import ArthasBot
from arthas import config


@click.command()
@click.option('--google-api-key', default=config.google_api_key, type=str)
@click.option('--youtube-channel-id', default=config.youtube_channel_id, type=str)
@click.option('--telegram-token', default=config.telegram_token, type=str)
@click.option('--telegram-chat-channel', default=config.telegram_chat_channel, type=str)
def main(google_api_key: str, youtube_channel_id: str, telegram_token: str, telegram_chat_channel: str) -> None:
    logging.basicConfig(level=logging.DEBUG, format=config.logger_format, filename='bot.log', filemode='a')

    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)

    arthas_bot = ArthasBot(
        google_api_key=google_api_key,
        channel_name=youtube_channel_id,
        telegram_token=telegram_token,
        telegram_channel=telegram_chat_channel,
    )
    arthas_bot.run()


if __name__ == '__main__':
    main()
