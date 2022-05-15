import logging
from http import HTTPStatus
from typing import Optional, Any, Protocol

import requests

from arthas.utils.timeout_watcher import TimeoutWatcher

logger = logging.getLogger("API")


class API(Protocol):
    def get_user_id(self, username: str) -> str: ...

    def get_user_stream(self, user_id: str) -> Optional[dict[str, str]]: ...

    # def get_game_info(self, game_id: str) -> dict[str, str]: ...

    # def get_clip(self, clipname: str) -> dict[str, str]: ...

    # def get_channel(self, channel_id: str) -> dict[str, str]: ...

    # def get_last_post(self, channel_id: str) -> Optional[dict[str, str]]: ...


class TwitchAPI:
    API_URL = "https://api.twitch.tv/helix"
    API_URL_V5 = "https://api.twitch.tv/kraken"

    def __init__(self, client_id: str, oauth_key: str):
        self.client_id = client_id
        self.oauth_key = oauth_key

        self.timeout = TimeoutWatcher()

        self.cache_get_user_id: dict[str, dict[str, str]] = {}
        self.cache_get_game: dict[str, dict[str, str]] = {}

    def get_user_id(self, username: str) -> str:
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

    def get_game_info(self, game_id: str) -> dict[str, str]:
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

    def get_user_stream(self, user_id: str) -> Optional[dict[str, str]]:
        # https://dev.twitch.tv/docs/api/reference#get-streams
        stream_data = self.query('streams', user_id=user_id)

        if not stream_data:
            return None

        return {
            'stream_id': stream_data['id'],
            'title': stream_data['title'],
            'viewer_count': stream_data['viewer_count'],
            'game_id': stream_data['game_id'],
        }

    def get_clip(self, clipname: str) -> dict[str, str]:
        # https://dev.twitch.tv/docs/v5/reference/clips
        clip_data = self.query_v5('clips', entity_id=clipname)

        # video_id = 239#clip_data['vod']['id']
        # offset = 239#clip_data['vod']['offset']
        duration = clip_data['duration']

        return {'clip_id': clip_data['slug'],
                # 'video_id': video_id,
                # 'offset': offset,
                'duration': duration}

    def get_channel(self, channel_id: str) -> dict[str, str]:
        # https://dev.twitch.tv/docs/v5/reference/channels#get-channel-by-id
        channel_data = self.query_v5('channels', entity_id=channel_id)

        status = channel_data['status']

        return {'status': status}

    def get_last_post(self, channel_id: str) -> Optional[dict[str, str]]:
        # https://dev.twitch.tv/docs/v5/reference/channel-feed#get-feed-post
        posts_data = self.query_v5("feed", "{}/posts".format(channel_id), limit=1)

        if 'posts' not in posts_data or len(posts_data['posts']) != 1:
            return None

        last_post = posts_data['posts'][0]

        return {'id': last_post['id'],
                'created_at': last_post['created_at'],
                'body': last_post['body']}

    def query(self, method: str, single_data: bool = True, **values: str) -> Any:
        url = self.API_URL + '/' + method

        if len(values) > 0:
            url += "?" + ",".join(["{}={}".format(key, value) for key, value in values.items()])

        web = requests.Session()
        web.headers.update({'Client-ID': self.client_id, 'Authorization': f'Bearer {self.oauth_key[6:]}'})
        self.timeout.ensure_timeout()
        data = web.get(url).json()

        if not single_data:
            return data
        else:
            if 'status' in data and data['status'] == HTTPStatus.TOO_MANY_REQUESTS:
                logger.error(data)
                raise RuntimeError(data['error'])

            if 'data' not in data:
                return None

            data = data['data']
            if len(data) == 0:
                return None
            assert len(data) == 1
            return data[0]

    def query_v5(self, method: str, entity_id: Optional[str] = None, **values: Any) -> Any:
        url = self.API_URL_V5 + '/' + method

        if entity_id is not None:
            url += "/{}".format(entity_id)

        if len(values) > 0:
            url += "?" + "&".join(["{}={}".format(key, value) for key, value in values.items()])

        web = requests.Session()
        web.headers.update({'Client-ID': self.client_id,
                            'Accept': "application/vnd.twitchtv.v5+json"})
        self.timeout.ensure_timeout()
        data = web.get(url).json()

        if 'status' in data:
            if data['status'] == HTTPStatus.TOO_MANY_REQUESTS:
                logger.error(data)
                raise RuntimeError("url={} ".format(url) + data['error'])
            elif data['status'] == HTTPStatus.NOT_FOUND:
                logger.error(data)
                raise KeyError("url={} ".format(url) + data['error'])
            elif method not in ['channels']:
                raise Exception("url={} ".format(url) + data['error'])

        return data
