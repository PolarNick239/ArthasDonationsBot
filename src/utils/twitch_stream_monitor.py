import time
import logging
import requests
import threading
from collections import namedtuple

from utils.file_storage import FileStorage

logger = logging.getLogger("Stream monitor")

StreamerState = namedtuple('StreamerState',
                           'user_id title game_id')


class TwitchStreamerMonitor:
    def __init__(self, client_id, username):
        self.client_id = client_id
        self.api_url = "https://api.twitch.tv/helix"
        self.api_url_v5 = "https://api.twitch.tv/kraken"

        self.username = username
        self.user_id = None

        self.stopped = False

        self.start_callbacks = []
        self.title_changed_callbacks = []
        self.game_changed_callbacks = []
        self.stop_callbacks = []

        self.streamer_state = FileStorage("streamer_state.json", dirpath="state")
        self.streamer_state.load(StreamerState)

        self.previous_query_time = 0
        self.query_timeout = 1.0
        self.monitor_timeout = 10.0

    def start(self):
        thread = threading.Thread(target=self.run_loop, name="Stream monitor")
        thread.start()
        return thread

    def stop(self):
        self.stopped = True

    def run_loop(self):
        self.user_id = self.get_user_id(self.username)
        self.ensure_timeout(query_following=False)

        if self.streamer_state.value is not None:
            if self.streamer_state.value.user_id != self.user_id:
                logger.warning(
                    "User_id saved in state mismatched with current user_id! {} != {} (current user name: {})"
                    .format(self.streamer_state.value.user_id, self.user_id, self.username))
                logger.info("Stated initialized with None!")
                self.streamer_state.value = None
            else:
                game_name = self.get_game_info(self.streamer_state.value.game_id)['name']
                self.ensure_timeout(query_following=False)
                logger.info("Initial state: title={}, game_name={}".format(self.streamer_state.value.title, game_name))

        while not self.stopped:
            try:
                changed = False
                current_state = self.get_user_stream(self.user_id)

                if current_state is None:
                    if self.streamer_state.value is not None:
                        changed = True
                        self.notify_stream_stopped()
                    continue

                stream_id = current_state["stream_id"]
                current_state = StreamerState(user_id=self.user_id,
                                              title=current_state["title"],
                                              game_id=current_state["game_id"])

                if self.streamer_state.value is None:
                    changed = True
                    game_name = self.get_game_info(current_state.game_id)['name']
                    self.notify_stream_started(current_state.title, game_name, stream_id)
                    continue

                if current_state.title != self.streamer_state.value.title:
                    changed = True
                    self.notify_title_changed(current_state.title)

                if current_state.game_id != self.streamer_state.value.game_id:
                    changed = True
                    game_name = self.get_game_info(current_state.game_id)['name']
                    self.notify_game_changed(game_name)
            except Exception as e:
                logger.error(e)
            finally:
                if changed:
                    self.streamer_state.value = current_state
                    self.streamer_state.save()

                time.sleep(self.monitor_timeout)

    def notify_stream_started(self, title, game_name, stream_id):
        logger.info("Stream started! stream_id={} game={} title={}".format(stream_id, title, game_name))
        for callback in self.start_callbacks:
            callback(stream_id, title, game_name)

    def notify_title_changed(self, title):
        logger.info("Title changed! title={}".format(title))
        for callback in self.title_changed_callbacks:
            callback(title)

    def notify_game_changed(self, game_name):
        logger.info("Game changed! game={}".format(game_name))
        for callback in self.game_changed_callbacks:
            callback(game_name)

    def notify_stream_stopped(self):
        logger.info("Stream stopped!")
        for callback in self.stop_callbacks:
            callback()

    def add_start_callback(self, callback):
        self.start_callbacks.append(callback)

    def add_title_changed_callback(self, callback):
        self.title_changed_callbacks.append(callback)

    def add_game_changed_callback(self, callback):
        self.game_changed_callbacks.append(callback)

    def add_stop_callback(self, callback):
        self.stop_callbacks.append(callback)

    def get_user_id(self, login):
        # https://dev.twitch.tv/docs/api/reference#get-users
        logger.debug("Searching for user with login={}...".format(login))
        user_data = self.query('users', login=login)
        if not user_data:
            raise KeyError("No user with login={} found!".format(login))

        logger.info("User with login={} has id={}.".format(login, user_data['id']))
        return user_data['id']

    def get_game_info(self, game_id):
        # https://dev.twitch.tv/docs/api/reference#get-games
        game_data = self.query('games', id=game_id)
        if not game_data:
            logger.warning("No game with id={} found!".format(game_id))
            return {"name": "Unknown"}

        return {"name": game_data['name']}

    def get_user_stream(self, user_id):
        # https://dev.twitch.tv/docs/api/reference#get-streams
        stream_data = self.query('streams', user_id=user_id)

        if not stream_data:
            return None

        title = stream_data['title']
        viewer_count = stream_data['viewer_count']
        game_id = stream_data['game_id']
        stream_id = stream_data['id']

        ad_separators = [" [http://"]
        for ad_separator in ad_separators:
            if ad_separator in title:
                title = title[:title.index(ad_separator)]

        return {'stream_id': stream_id,
                'title': title,
                'viewer_count': viewer_count,
                'game_id': game_id}

    def get_clip(self, clipname):
        # https://dev.twitch.tv/docs/v5/reference/clips
        clip_data = self.query_v5('clips', entity_id=clipname)

        video_id = 239#clip_data['vod']['id']
        offset = 239#clip_data['vod']['offset']
        duration = clip_data['duration']

        return {'clip_id': clip_data['slug'],
                'video_id': video_id,
                'offset': offset,
                'duration': duration}

    def ensure_timeout(self, *, query_following=True):
        current_time = time.time()
        passed = current_time - self.previous_query_time

        if passed < self.query_timeout:
            # if query_following:
            #     logger.debug("Faced timeout!")
            time.sleep(1.1 * self.query_timeout - passed)

        if query_following:
            self.previous_query_time = current_time

    def query(self, method, single_data=True, **values):
        url = self.api_url + '/' + method

        if len(values) > 0:
            url += "?" + ",".join(["{}={}".format(key, value) for key, value in values.items()])

        web = requests.Session()
        web.headers.update({'Client-ID': self.client_id})
        self.ensure_timeout()
        data = web.get(url).json()

        if not single_data:
            return data
        else:
            status_too_many_requests = 429
            if 'status' in data and data['status'] == status_too_many_requests:
                logger.error(data)
                raise RuntimeError(data['error'])

            if 'data' not in data:
                return None

            data = data['data']
            if len(data) == 0:
                return None
            assert len(data) == 1
            return data[0]

    def query_v5(self, method, entity_id=None, **values):
        url = self.api_url_v5 + '/' + method

        if entity_id is not None:
            url += "/{}".format(entity_id)

        if len(values) > 0:
            url += "?" + "&".join(["{}={}".format(key, value) for key, value in values.items()])

        web = requests.Session()
        web.headers.update({'Client-ID': self.client_id,
                            'Accept': "application/vnd.twitchtv.v5+json"})
        self.ensure_timeout()
        data = web.get(url).json()

        status_too_many_requests = 429
        status_not_found = 404
        if 'status' in data:
            if data['status'] == status_too_many_requests:
                logger.error(data)
                raise RuntimeError("url={} ".format(url) + data['error'])
            elif data['status'] == status_not_found:
                logger.error(data)
                raise KeyError("url={} ".format(url) + data['error'])
            else:
                raise Exception("url={} ".format(url) + data['error'])

        return data


if __name__ == '__main__':
    import config

    logging.basicConfig(level=logging.DEBUG, format=config.logger_format)

    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    monitor = TwitchStreamerMonitor(config.client_id, "arthas")
    res = monitor.get_clip("OutstandingThoughtfulHorseRaccAttack")
    x = 239

    try:
        monitor_thread = monitor.start()
        monitor_thread.join()
    except KeyboardInterrupt:
        monitor.stop()
