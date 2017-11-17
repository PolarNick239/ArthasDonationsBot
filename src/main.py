import cv2
import time
import logging
import pathlib
from wrapt import synchronized
from collections import namedtuple

from utils.file_storage import FileStorage
from utils.donates_detector import extract_donate_robust
from utils.telegram_chat_bot import TelegramChatBot
from utils.twitch_irc_monitor import IRCTwitchMonitor
from utils.twitch_stream_monitor import TwitchStreamerMonitor
from utils.twitch_stream_video import StreamVideoSnapshots

logger = logging.getLogger("Arthas bot")

ClipInfo = namedtuple('ClipInfo',
                      'clip_url clip_id video_id offset duration username message telegram_message_id')


class ArthasBot:
    def __init__(self, twitch_irc_botname, twitch_irc_bot_oauth_key, twitch_irc_host,
                 twitch_token, twitch_channel,
                 telegram_token, telegram_channel):
        self.twitch_channel = twitch_channel

        self.telegram_bot = TelegramChatBot(telegram_channel, telegram_token)
        self.twitch_video = StreamVideoSnapshots()
        self.twitch_monitor = TwitchStreamerMonitor(twitch_token, twitch_channel)
        self.twitch_chat_monitor = IRCTwitchMonitor(twitch_irc_botname, twitch_irc_bot_oauth_key, twitch_channel,
                                                    twitch_irc_host)

        self.clips_ids_by_video_id = FileStorage("clips.json", dirpath="state/clips")
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

        self.twitch_monitor.add_channel_status_callback(self.on_channel_status_changed)

        self.twitch_monitor.add_start_callback(self.on_stream_started)
        self.twitch_monitor.add_game_changed_callback(self.on_game_changed)
        self.twitch_monitor.add_title_changed_callback(self.on_title_changed)
        self.twitch_monitor.add_stop_callback(self.on_stream_stopped)

        self.twitch_chat_monitor.add_message_callback(self.on_chat_message)

    def run(self):
        logger.info("Starting telegram bot...")
        self.telegram_bot.start()

        if self.twitch_monitor.streamer_state.value is not None:
            self.start_donates_detection()

        logger.info("Starting twitch monitor...")
        twitch_monitor_thread = self.twitch_monitor.start()

        logger.info("Starting twitch chat monitor...")
        chat_monitor_thread = self.twitch_chat_monitor.start()

        # Waiting for interruption (Ctrl+C)
        self.telegram_bot.join()

        self.stop_donates_detection()

        if chat_monitor_thread is not None:
            logger.info("Stopping twitch chat monitor...")
            self.twitch_chat_monitor.stop()
            chat_monitor_thread.join()

        if twitch_monitor_thread is not None:
            logger.info("Stopping twitch monitor...")
            self.twitch_monitor.stop()
            twitch_monitor_thread.join()

        logger.info("Stopping telegram bot...")
        self.telegram_bot.stop()

    @synchronized
    def on_stream_started(self, stream_id, title, game_name):
        self.telegram_bot.send_message("Величайший подрубил!\n{}\n{}".format(game_name, title))

        self.start_donates_detection()

    @synchronized
    def on_game_changed(self, game_name):
        self.telegram_bot.send_message("Игра: {}".format(game_name))

    @synchronized
    def on_title_changed(self, title):
        self.telegram_bot.send_message("Название стрима: {}".format(title))

    @synchronized
    def on_stream_stopped(self):
        self.telegram_bot.send_message("Папич отрубил :(((9(9((9(((((99(9")

        self.stop_donates_detection()

    @synchronized
    def on_channel_status_changed(self, status):
        self.telegram_bot.send_message("Статус канала: {}".format(status))

    def start_donates_detection(self):
        logger.info("Starting video streaming for {}...".format(self.twitch_channel))

        self.video_frame_index_cur = 0
        self.video_frame_index_prev_processed = 0
        self.video_frame_index_prev_donate = 0
        self.video_key_imgs = []

        self.twitch_video.add_image_callback(self.on_video_screen)
        self.twitch_video.start(self.twitch_channel)

    def stop_donates_detection(self):
        logging.info("Stopping video streaming...")

        self.twitch_video.image_callbacks = []
        if not self.twitch_video.stopped:
            logger.info("Stopping twitch video...")
            self.twitch_video.stop()

    @synchronized
    def on_video_screen(self, img):
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

    def on_donate(self, donate_img, donate_id):
        donates_path = "donates"
        pathlib.Path(donates_path).mkdir(exist_ok=True)
        donate_path = donates_path + "/{}.png".format(donate_id)

        cv2.imwrite(donate_path, donate_img)
        with open(donate_path, 'rb') as photo_file:
            self.telegram_bot.send_photo(photo_file)

    def create_clip_storage(self, video_id, clip_id):
        return FileStorage("clip_{}.json".format(clip_id), dirpath="state/clips/{}".format(video_id))

    @synchronized
    def on_chat_message(self, username, message):
        if "https://clips.twitch.tv/" not in message:
            return

        clip_url = message[message.index("https://clips.twitch.tv/"):].split(" ")[0]
        clip_id = clip_url.split('/')[-1]
        if clip_id in self.clips:
            return

        logger.info("Clip url={}, clip_id={}, username={}, message={}".format(clip_url, clip_id, username, message))

        try:
            new_clip = self.twitch_monitor.get_clip(clip_id)
            assert new_clip['clip_id'] == clip_id
        except Exception as e:
            logger.error(e)
            return

        new_clip = ClipInfo(clip_url=clip_url, clip_id=clip_id, video_id=new_clip['video_id'], offset=new_clip['offset'],
                            duration=new_clip['duration'], username=username, message=message, telegram_message_id=None)
        if new_clip.video_id not in self.clips_ids_by_video_id.value:
            self.clips_ids_by_video_id.value[new_clip.video_id] = []

        intersected_clip = None
        consumed_clip = None
        for old_clip_id in self.clips_ids_by_video_id.value[new_clip.video_id]:
            old_clip = self.clips[old_clip_id].value
            if old_clip is None:
                continue

            old_from = old_clip.offset
            old_to = old_clip.offset + old_clip.duration
            new_from = new_clip.offset
            new_to = new_clip.offset + new_clip.duration

            # if (new_from <= old_from and old_to < new_to) or (new_from < old_from and old_to <= new_to):
            #     consumed_clip = old_clip
            #     break
            #
            # no_intersection = (old_from >= new_to or old_to <= new_from)
            # if not no_intersection:
            #     intersected_clip = old_clip

        message_text = "{}: {}".format(username, clip_url)

        clip_storage = self.create_clip_storage(new_clip.video_id, clip_id)

        if consumed_clip is not None:
            logger.info("Clip consumed: old={}, new={}!".format(consumed_clip, new_clip))
            #telegram_message = self.telegram_bot.edit_message(consumed_clip.telegram_message_id, message_text)
            #logger.info("Clip {} replaced clip {} in telegram message with id={}!".format(clip_id, consumed_clip.clip_id, -1))

            clip_storage.value = ClipInfo(clip_url=clip_url, clip_id=clip_id,
                                          video_id=new_clip.video_id,
                                          offset=new_clip.offset,
                                          duration=new_clip.duration,
                                          username=username, message=message,
                                          telegram_message_id=-1)
            clip_storage.save()
        elif intersected_clip is not None:
            logger.info("Clip ignored because of intersection: old={}, new={}!".format(intersected_clip, new_clip))
        else:
            logger.info("Clip detected {}!".format(new_clip))
            #telegram_message = self.telegram_bot.send_message(message_text)
            #logger.info("Clip {} sent in telegram message with id={}!".format(clip_id, telegram_message.message_id))

            clip_storage.value = ClipInfo(clip_url=clip_url, clip_id=clip_id,
                                          video_id=new_clip.video_id,
                                          offset=new_clip.offset,
                                          duration=new_clip.duration,
                                          username=username, message=message,
                                          telegram_message_id=-1)
            clip_storage.save()

        self.clips_ids_by_video_id.value[new_clip.video_id].append(clip_id)
        self.clips_ids_by_video_id.save()

        if consumed_clip is not None:
            consumed_storage = self.create_clip_storage(consumed_clip.video_id, consumed_clip.clip_id)
            consumed_storage.value = None
            consumed_storage.save()


if __name__ == '__main__':
    import config

    logging.basicConfig(level=logging.DEBUG, format=config.logger_format, filename='twitchbot.log', filemode='a')

    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)

    arthas_bot = ArthasBot(twitch_irc_botname=config.nickname,
                           twitch_irc_bot_oauth_key=config.oauth_key,
                           twitch_irc_host=config.host,
                           twitch_token=config.client_id,
                           twitch_channel=config.channel,
                           telegram_token=config.telegram_token,
                           telegram_channel=config.telegram_chat_channel)

    arthas_bot.run()
