import logging
from pathlib import Path

import yaml
import click

from arthas.utils.arthas_bot import ArthasBot
import arthas.config


@click.command()
@click.option('-c', '--config-path', default=None, type=Path)
def main(config_path: Path) -> None:
    if config_path is not None:
        with open(config_path) as f:
            config = yaml.safe_load(f)
    else:
        config = {}

    logging.basicConfig(level=logging.DEBUG, format=arthas.config.logger_format, filename='bot.log', filemode='a')

    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)

    google_api_key = config.get('google_api_key', arthas.config.google_api_key)
    youtube_channel_id = config.get('youtube_channel_id', arthas.config.youtube_channel_id)
    telegram_token = config.get('telegram_token', arthas.config.telegram_token)
    telegram_chat_channel = config.get('telegram_chat_channel', arthas.config.telegram_chat_channel)

    arthas_bot = ArthasBot(
        google_api_key=google_api_key,
        channel_name=youtube_channel_id,
        telegram_token=telegram_token,
        telegram_channel=telegram_chat_channel,
    )
    arthas_bot.run()


if __name__ == '__main__':
    main()
