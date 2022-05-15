import logging
import pathlib
import time
from collections import namedtuple

import cv2
import numpy as np
from wrapt import synchronized

from arthas.utils.donates_detector import extract_donate_robust
from arthas.utils.file_storage import FileStorage
from arthas.utils.stream_video import StreamVideoSnapshots
from arthas.utils.telegram_chat_bot import TelegramChatBot
from arthas.utils.youtube_api import YoutubeAPI
from arthas.utils.youtube_stream_monitor import YoutubeStreamerMonitor


logger = logging.getLogger("Arthas bot")


ClipInfo = namedtuple('ClipInfo',
                      'clip_url clip_id video_id offset duration username message telegram_message_id')


class ArthasBot:
    def __init__(
        self,
        google_api_key: str,
        channel_name: str,
        telegram_token: str,
        telegram_channel: str,
    ):
        self.channel_name = channel_name

        self.telegram_bot = TelegramChatBot(telegram_channel, telegram_token)

        self.api = YoutubeAPI(google_api_key)
        self.video_tracker = StreamVideoSnapshots(f'https://www.youtube.com/channel/{channel_name}')
        self.stream_monitor = YoutubeStreamerMonitor(channel_name, self.api)

        self.waiting_for_screenshot = False

        self.clips_ids_by_video_id: FileStorage[dict[str, str]] = FileStorage("clips.json", dirpath="state/clips")
        self.clips = {}

        self.clips_ids_by_video_id.load()
        if self.clips_ids_by_video_id.value is None:
            self.clips_ids_by_video_id.value = {}
        else:
            logger.info("Loading clips...")
            deleted_number = 0
            for video_id, clips_ids in self.clips_ids_by_video_id.value.items():
                for clip_id in clips_ids:
                    self.clips[clip_id] = self.create_clip_storage(video_id, clip_id)
                    self.clips[clip_id].load(ClipInfo)
                    if self.clips[clip_id].value is None:
                        deleted_number += 1
            logger.info("{} clips loaded! ({} deleted)".format(len(self.clips), deleted_number))

        self.stream_monitor.add_new_post_callback(self.on_new_post)
        self.stream_monitor.add_channel_status_callback(self.on_channel_status_changed)
        self.stream_monitor.add_start_callback(self.on_stream_started)
        self.stream_monitor.add_game_changed_callback(self.on_game_changed)
        self.stream_monitor.add_title_changed_callback(self.on_title_changed)
        self.stream_monitor.add_stop_callback(self.on_stream_stopped)

    def run(self) -> None:
        logger.info("Starting telegram bot...")
        self.telegram_bot.start()

        if self.stream_monitor.streamer_state.value is not None:
            self.start_donates_detection()

        logger.info("Starting stream monitor...")
        monitor_thread = self.stream_monitor.start()

        # Waiting for interruption (Ctrl+C)
        self.telegram_bot.join()

        self.stop_donates_detection()

        if monitor_thread is not None:
            logger.info("Stopping stream monitor...")
            self.stream_monitor.stop()
            monitor_thread.join()

        logger.info("Stopping telegram bot...")
        self.telegram_bot.stop()

    @synchronized
    def on_stream_started(self, stream_id: str, title: str, game_name: str) -> None:
        self.telegram_bot.send_message(
            f'Величайший подрубил!\n{game_name}\n{title}\nhttps://www.youtube.com/watch?v={stream_id}'
        )
        self.waiting_for_screenshot = True

        self.start_donates_detection()

    @synchronized
    def on_game_changed(self, game_name: str) -> None:
        self.telegram_bot.send_message("Игра: {}".format(game_name))
        self.waiting_for_screenshot = True

    @synchronized
    def on_title_changed(self, title: str) -> None:
        self.telegram_bot.send_message("Название стрима: {}".format(title))

    @synchronized
    def on_stream_stopped(self) -> None:
        self.telegram_bot.send_message("Папич отрубил :(((9(9((9(((((99(9")

        self.stop_donates_detection()

    @synchronized
    def on_channel_status_changed(self, status: str) -> None:
        self.telegram_bot.send_message("Статус канала: {}".format(status))

    @synchronized
    def on_new_post(self, body: str) -> None:
        self.telegram_bot.send_message(body)

    def start_donates_detection(self) -> None:
        logger.info("Starting video streaming for {}...".format(self.channel_name))

        self.video_frame_index_cur = 0
        self.video_frame_index_prev_processed = 0
        self.video_frame_index_prev_donate = 0
        self.video_key_imgs: list[np.ndarray] = []

        self.video_tracker.add_image_callback(self.on_video_screen)
        self.video_tracker.start()

    def stop_donates_detection(self) -> None:
        logging.info("Stopping video streaming...")

        self.video_tracker.image_callbacks = []
        if not self.video_tracker.stopped:
            logger.info("Stopping stream video...")
            self.video_tracker.stop()

    @synchronized
    def on_video_screen(self, img: np.ndarray) -> None:
        if self.waiting_for_screenshot:
            self.waiting_for_screenshot = False
            current_time = time.time()

            logger.info("Saving and sending screenshot {}!".format(current_time))

            screenshots_path = "screenshots"
            pathlib.Path(screenshots_path).mkdir(exist_ok=True)
            donate_path = screenshots_path + "/{}.png".format(current_time)

            cv2.imwrite(donate_path, img)
            with open(donate_path, 'rb') as photo_file:
                self.telegram_bot.send_photo(photo_file)

        self.video_frame_index_cur += 1
        frames_passed = self.video_frame_index_cur - self.video_frame_index_prev_processed

        if frames_passed < 1:
            return

        cur_time = int(round(time.time() * 1000))
        self.video_frame_index_prev_processed = self.video_frame_index_cur

        self.video_key_imgs.append(img)
        if len(self.video_key_imgs) != 4:
            return
        self.video_key_imgs = self.video_key_imgs[1:]

        donate_img = extract_donate_robust(self.video_key_imgs[0], self.video_key_imgs[1], self.video_key_imgs[2])
        if donate_img is not None:
            donate_id = "{}_{}".format(cur_time, self.video_frame_index_cur)

            logging.info("Donate detected! id={}".format(donate_id))

            # for testing puproses
            donate_path = "donates_triplets/{}".format(donate_id)
            pathlib.Path(donate_path).mkdir(parents=True, exist_ok=True)
            for i in range(3):
                cv2.imwrite(donate_path + "/{}_{}.png".format(donate_id, i), self.video_key_imgs[i])

            if self.video_frame_index_cur - self.video_frame_index_prev_donate < 13:
                logging.warning("Donate skipped because of donate timeout! (donate_id={})".format(donate_id))
            else:
                self.video_frame_index_prev_donate = self.video_frame_index_cur
                self.on_donate(donate_img, donate_id)

    def on_donate(self, donate_img: np.ndarray, donate_id: str) -> None:
        donates_path = "donates"
        pathlib.Path(donates_path).mkdir(exist_ok=True)
        donate_path = donates_path + "/{}.png".format(donate_id)

        cv2.imwrite(donate_path, donate_img)
        with open(donate_path, 'rb') as photo_file:
            self.telegram_bot.send_photo(photo_file)

    def create_clip_storage(self, video_id: str, clip_id: str) -> FileStorage[ClipInfo]:
        return FileStorage("clip_{}.json".format(clip_id), dirpath="state/clips/{}".format(video_id))
