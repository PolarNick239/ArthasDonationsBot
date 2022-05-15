import time
import logging
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

import threading

from arthas.utils.file_storage import FileStorage
from arthas.utils.streamer_monitor import StartedCallback, TitleChangedCallback, GameChangedCallback, StoppedCallback, \
    NewPostCallback, StatusChangedCallback
from arthas.utils.twitch_api import API

logger = logging.getLogger("Stream monitor")


@dataclass
class StreamerState:
    user_id: str
    title: str
    game_id: str


@dataclass
class LastPostState:
    id: str
    created_at: str
    body: str


@dataclass
class ChannelState:
    status: str


class StreamerMonitor:
    def __init__(self, username: str, api: API):
        self.api = api

        self.username = username
        self.user_id: Optional[str] = None

        self.stopped = False

        self.start_callbacks: list[StartedCallback] = []
        self.title_changed_callbacks: list[TitleChangedCallback] = []
        self.game_changed_callbacks: list[GameChangedCallback] = []
        self.stop_callbacks: list[StoppedCallback] = []
        self.new_post_callbacks: list[NewPostCallback] = []
        self.channel_status_callbacks: list[StatusChangedCallback] = []

        self.streamer_state: FileStorage[StreamerState] = FileStorage("streamer_state.json", dirpath="state")
        self.streamer_state.load(StreamerState)

        self.last_post_state: FileStorage[LastPostState] = FileStorage("last_post.json", dirpath="state")
        self.last_post_state.load(LastPostState)

        self.channel_state: FileStorage[ChannelState] = FileStorage("channel_state.json", dirpath="state")
        self.channel_state.load(ChannelState)

        self.monitor_timeout = 20.0

        ad_kw_prefixes = ["http://", "https://", "goo.gl"]
        self.ad_separators = [" " + kw for kw in ad_kw_prefixes] + [" [" + kw for kw in ad_kw_prefixes]

    def start(self) -> threading.Thread:
        thread = threading.Thread(target=self.run_loop, name="Stream monitor")
        thread.start()
        return thread

    def stop(self) -> None:
        self.stopped = True

    def run_loop(self) -> None:
        self.user_id = self.api.get_user_id(self.username)
        # self.ensure_timeout(query_following=False)  # TODO: idk

        if self.streamer_state.value is not None:
            if self.streamer_state.value.user_id != self.user_id:
                logger.warning(
                    "User_id saved in state mismatched with current user_id! {} != {} (current user name: {})"
                    .format(self.streamer_state.value.user_id, self.user_id, self.username))
                logger.info("Stated initialized with None!")
                self.streamer_state.value = None

        while not self.stopped:
            changed = False
            try:
                changed = False
                raw_current_state = self.api.get_user_stream(self.user_id)

                if raw_current_state is None:
                    if self.streamer_state.value is not None:
                        changed = True
                        self.notify_stream_stopped()
                    current_state = None
                    continue

                stream_id = raw_current_state["stream_id"]
                current_state = StreamerState(
                    user_id=self.user_id,
                    title=self.remove_ad(raw_current_state["title"]),
                    game_id=raw_current_state["game_id"]
                )

                if self.streamer_state.value is None:
                    changed = True
                    # game_name = self.api.get_game_info(current_state.game_id)['name']
                    game_name = ''  # TODO: idk, wheather there is such an API for youtube
                    self.notify_stream_started(current_state.title, game_name, stream_id)
                    continue

                if current_state.title != self.streamer_state.value.title:
                    changed = True
                    self.notify_title_changed(current_state.title)

                if current_state.game_id != self.streamer_state.value.game_id:
                    changed = True
                    # game_name = self.api.get_game_info(current_state.game_id)['name']
                    game_name = ''  # TODO: idk, wheather there is such an API for youtube
                    self.notify_game_changed(game_name)
            except Exception as e:
                logger.error(e)
                raise e
            finally:
                if changed:
                    self.streamer_state.value = current_state
                    self.streamer_state.save()

                time.sleep(self.monitor_timeout)

    def remove_ad(self, status: str) -> str:
        for ad_separator in self.ad_separators:
            if ad_separator in status:
                status = status[:status.index(ad_separator)]
        return status

    def notify_new_post(self, post: LastPostState) -> None:
        logger.info("New post! id={} create_at={} body={}".format(post.id, post.created_at, post.body))
        for callback in self.new_post_callbacks:
            callback(post.body)

    def add_new_post_callback(self, callback: NewPostCallback) -> None:
        self.new_post_callbacks.append(callback)

    def notify_channel_status_changed(self, status: str) -> None:
        logger.info("Channel status changed! status={}".format(status))
        for callback in self.channel_status_callbacks:
            callback(status)

    def add_channel_status_callback(self, callback: StatusChangedCallback) -> None:
        self.channel_status_callbacks.append(callback)

    def notify_stream_started(self, title: str, game_name: str, stream_id: str) -> None:
        logger.info("Stream started! stream_id={} game={} title={}".format(stream_id, title, game_name))
        for callback in self.start_callbacks:
            callback(stream_id, title, game_name)

    def notify_title_changed(self, title: str) -> None:
        logger.info("Title changed! title={}".format(title))
        for callback in self.title_changed_callbacks:
            callback(title)

    def notify_game_changed(self, game_name: str) -> None:
        logger.info("Game changed! game={}".format(game_name))
        for callback in self.game_changed_callbacks:
            callback(game_name)

    def notify_stream_stopped(self) -> None:
        logger.info("Stream stopped!")
        for callback in self.stop_callbacks:
            callback()

    def add_start_callback(self, callback: StartedCallback) -> None:
        self.start_callbacks.append(callback)

    def add_title_changed_callback(self, callback: TitleChangedCallback) -> None:
        self.title_changed_callbacks.append(callback)

    def add_game_changed_callback(self, callback: GameChangedCallback) -> None:
        self.game_changed_callbacks.append(callback)

    def add_stop_callback(self, callback: StoppedCallback) -> None:
        self.stop_callbacks.append(callback)


# if __name__ == '__main__':
#     import config
#
#     logging.basicConfig(level=logging.DEBUG, format=config.logger_format)
#
#     logging.getLogger("requests").setLevel(logging.WARNING)
#     logging.getLogger("urllib3").setLevel(logging.WARNING)
#
#     monitor = TwitchStreamerMonitor(config.client_id, "arthas")
#
#     try:
#         monitor_thread = monitor.start()
#         monitor_thread.join()
#     except KeyboardInterrupt:
#         monitor.stop()
