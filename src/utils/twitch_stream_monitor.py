import time
import logging
import requests
import threading
import dateutil.parser
from collections import namedtuple

from utils.file_storage import FileStorage

logger = logging.getLogger("Stream monitor")

StreamerState = namedtuple('StreamerState',
                           'user_id title game_id')

LastPostState = namedtuple('LastPostState',
                           'id created_at body')

ChannelState = namedtuple('ChannelState',
                          'status')


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

        self.last_post_state = FileStorage("last_post.json", dirpath="state")
        self.last_post_state.load(LastPostState)

        self.new_post_callbacks = []

        self.channel_status_callbacks = []

        self.channel_state = FileStorage("channel_state.json", dirpath="state")
        self.channel_state.load(ChannelState)

        self.previous_query_time = 0
        self.query_timeout = 1.0
        self.monitor_timeout = 10.0

        self.cache_get_user_id = {}
        self.cache_get_game = {}

        ad_kw_prefixes = ["http://", "https://", "goo.gl"]
        self.ad_separators = [" " + kw for kw in ad_kw_prefixes] +\
                             [" [" + kw for kw in ad_kw_prefixes]

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

        iteration = 0

        while not self.stopped:
            iteration += 1
            try:
                if iteration % 10 == 1:
                    last_post = self.get_last_post(self.user_id)
                    if last_post is not None:
                        new_last_post = LastPostState(**last_post)

                        # RFC 3339 format
                        # '2017-12-06T14:28:26.084868Z'
                        new_created_date = dateutil.parser.parse(new_last_post.created_at)
                        if self.last_post_state.value is None\
                                or new_created_date > dateutil.parser.parse(self.last_post_state.value.created_at):
                            self.notify_new_post(new_last_post)

                            self.last_post_state.value = new_last_post
                            self.last_post_state.save()

                changed = False
                current_state = self.get_user_stream(self.user_id)

                if current_state is None:
                    if self.streamer_state.value is not None:
                        changed = True
                        self.notify_stream_stopped()

                    current_channel = self.get_channel(self.user_id)
                    channel_status = ChannelState(status=current_channel['status'])
                    if self.channel_state.value is None or channel_status.status != self.channel_state.value.status:
                        self.notify_channel_status_changed(channel_status.status)

                        self.channel_state.value = channel_status
                        self.channel_state.save()
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

    def notify_new_post(self, post):
        logger.info("New post! id={} create_at={} body={}".format(post.id, post.created_at, post.body))
        for callback in self.new_post_callbacks:
            callback(post.body)

    def add_new_post_callback(self, callback):
        self.new_post_callbacks.append(callback)

    def notify_channel_status_changed(self, status):
        logger.info("Channel status changed! status={}".format(status))
        for callback in self.channel_status_callbacks:
            callback(status)

    def add_channel_status_callback(self, callback):
        self.channel_status_callbacks.append(callback)

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

    def get_user_id(self, username):
        # https://dev.twitch.tv/docs/api/reference#get-users
        if username in self.cache_get_user_id:
            user_data = self.cache_get_user_id[username]
        else:
            logger.debug("Searching for user with login={}...".format(username))
            user_data = self.query('users', login=username)
            self.cache_get_user_id[username] = user_data

        if not user_data:
            raise KeyError("No user with login={} found!".format(username))

        logger.info("User with login={} has id={}.".format(username, user_data['id']))
        return user_data['id']

    def get_game_info(self, game_id):
        # https://dev.twitch.tv/docs/api/reference#get-games
        if game_id in self.cache_get_game:
            game_data = self.cache_get_game[game_id]
        else:
            game_data = self.query('games', id=game_id)
            self.cache_get_game[game_id] = game_data

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

        for ad_separator in self.ad_separators:
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

    def get_channel(self, channel_id):
        # https://dev.twitch.tv/docs/v5/reference/channels#get-channel-by-id
        channel_data = self.query_v5('channels', entity_id=channel_id)

        status = channel_data['status']

        for ad_separator in self.ad_separators:
            if ad_separator in status:
                status = status[:status.index(ad_separator)]

        return {'status': status}

    def get_last_post(self, channel_id):
        # https://dev.twitch.tv/docs/v5/reference/channel-feed#get-feed-post
        posts_data = self.query_v5("feed", "{}/posts".format(channel_id), limit=1)

        if 'posts' not in posts_data or len(posts_data['posts']) != 1:
            return None

        last_post = posts_data['posts'][0]

        return {'id': last_post['id'],
                'created_at': last_post['created_at'],
                'body': last_post['body']}

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
            elif method not in ['channels']:
                raise Exception("url={} ".format(url) + data['error'])

        return data


if __name__ == '__main__':
    import config

    logging.basicConfig(level=logging.DEBUG, format=config.logger_format)

    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    monitor = TwitchStreamerMonitor(config.client_id, "arthas")

    try:
        monitor_thread = monitor.start()
        monitor_thread.join()
    except KeyboardInterrupt:
        monitor.stop()
