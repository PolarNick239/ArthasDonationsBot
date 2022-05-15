import time
import logging
from dataclasses import dataclass
from enum import unique, Enum, auto
from typing import Optional

import threading

from arthas.utils.file_storage import FileStorage
from arthas.utils.streamer_monitor import StartedCallback, TitleChangedCallback, GameChangedCallback, StoppedCallback, \
    NewPostCallback, StatusChangedCallback
from arthas.utils.twitch_stream_monitor import LastPostState
from arthas.utils.youtube_api import YoutubeAPI, VideoStatus

logger = logging.getLogger("Stream monitor")


@unique
class StreamStatus(Enum):
    Running = auto()
    NotRunning = auto()


@dataclass
class StreamerState:
    user_id: str
    playlist_id: str
    title: str
    video_id: Optional[str]

    def is_stream_running(self) -> bool:
        return self.video_id is not None


class YoutubeStreamerMonitor:
    def __init__(self, username: str, api: YoutubeAPI):
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

        self.monitor_timeout = 120.0

        ad_kw_prefixes = ["http://", "https://", "goo.gl"]
        self.ad_separators = [" " + kw for kw in ad_kw_prefixes] + [" [" + kw for kw in ad_kw_prefixes]


    def start(self) -> threading.Thread:
        thread = threading.Thread(target=self.run_loop, name="Stream monitor")
        thread.start()
        return thread

    def stop(self) -> None:
        self.stopped = True

    def check_if_stream_continues(self) -> None:
        assert self.streamer_state.value is not None
        assert self.streamer_state.value.video_id is not None

        video_status = self.api.get_video_info(self.streamer_state.value.video_id)

        assert \
            video_status.status not in [VideoStatus.NotStream, VideoStatus.Scheduled], \
            f'Incorrect status "{video_status.status}" for already running stream'

        if video_status.status == VideoStatus.Ended:
            self.streamer_state.value.video_id = None
            self.streamer_state.save()
            self.notify_stream_stopped()
        elif video_status.title != self.streamer_state.value.title:
            self.streamer_state.value.title = video_status.title
            self.streamer_state.save()
            self.notify_title_changed(video_status.title)

    def check_if_stream_started(self) -> None:
        assert self.streamer_state.value is not None
        assert self.streamer_state.value.video_id is None

        video_ids = self.api.get_video_ids(self.streamer_state.value.playlist_id)
        video_statuses = self.api.get_video_infos(video_ids)

        for video_status in video_statuses:
            if video_status.status == VideoStatus.Started:
                self.streamer_state.value.video_id = video_status.id
                self.streamer_state.value.title = video_status.title
                self.notify_stream_started(video_status.title, '', video_status.id)
                return

    def run_loop(self) -> None:
        user = self.api.get_user(self.username)

        self.streamer_state.value = StreamerState(
            user.id, user.video_playlist_id, '', None
        )

        assert self.streamer_state.value is not None

        while not self.stopped:
            try:
                if self.streamer_state.value.video_id is not None:
                    self.check_if_stream_continues()
                else:
                    self.check_if_stream_started()
            except Exception as e:
                logger.error(e)
                raise e
            finally:
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

