from dataclasses import dataclass
from enum import Enum, auto, unique
from typing import Any

import requests
import xmltodict

from arthas.utils.timeout_watcher import TimeoutWatcher


@dataclass
class YoutubeUser:
    id: str
    video_playlist_id: str


@unique
class VideoStatus(Enum):
    NotStream = auto()
    Scheduled = auto()
    Started = auto()
    Ended = auto()


@dataclass
class VideoInfo:
    id: str
    title: str
    status: VideoStatus


class YoutubeAPI:
    API_URL = "https://www.googleapis.com/youtube/v3"
    FEED_URL = 'https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}'
    MAX_RESULTS = 10

    def __init__(self, client_key: str):
        self.client_key = client_key
        self.timeout = TimeoutWatcher()

    def get_user(self, username: str) -> YoutubeUser:
        found_result = self.query('channels', part='id,contentDetails', forUsername=username)
        if found_result is None:
            # Assume that channel does not have a separate username thus username is the same as channel_id
            found_result = self.query('channels', part='id,contentDetails', id=username)

        return YoutubeUser(
            id=found_result['id'],
            video_playlist_id=found_result['contentDetails']['relatedPlaylists']['uploads']
        )

    def get_last_video_id(self, playlist_id: str) -> str:
        return self.get_video_ids(playlist_id)[0]

    def get_video_ids(self, playlist_id: str) -> list[str]:
        found_result = self.query(
            'playlistItems',
            part='id,snippet,contentDetails',
            playlistId=playlist_id,
            maxResults=self.MAX_RESULTS,
            single_data=False,
        )
        return [item['contentDetails']['videoId'] for item in found_result]

    def get_video_id_from_feed(self, channel_id: str) -> str:
        with requests.Session() as web:
            response = web.get(self.FEED_URL.format(channel_id=channel_id))
            data = xmltodict.parse(response.text)
            video_id = data['feed']['entry'][0]['yt:videoId']
            assert isinstance(video_id, str)
            return video_id

    def get_video_info(self, video_id: str) -> VideoInfo:
        return self.get_video_infos([video_id])[0]

    def get_video_infos(self, video_ids: list[str]) -> list[VideoInfo]:
        found_results = self.query(
            'videos', part='snippet,liveStreamingDetails', id=','.join(video_ids), single_data=False
        )

        video_infos = []

        for item in found_results:
            if 'liveStreamingDetails' not in item:
                status = VideoStatus.NotStream
            else:
                stream_details = item['liveStreamingDetails']
                if 'actualEndTime' in stream_details:
                    status = VideoStatus.Ended
                elif 'actualStartTime' in stream_details:
                    status = VideoStatus.Started
                elif 'scheduledStartTime' in stream_details:
                    status = VideoStatus.Scheduled
                else:
                    status = VideoStatus.Scheduled
                    # assert False, 'The invariant is violated: bad format of "liveStreamingDetails"'

            video_infos.append(VideoInfo(id=item['id'], title=item['snippet']['title'], status=status))

        return video_infos


    def query(self, method: str, single_data: bool = True, **kwargs: Any) -> Any:
        url = f'{self.API_URL}/{method}'

        kwargs['key'] = self.client_key
        if len(kwargs) > 0:
            url += "?" + "&".join(["{}={}".format(key, value) for key, value in kwargs.items()])

        with requests.Session() as web:
            self.timeout.ensure_timeout()
            data = web.get(url).json()

            items = data.get('items', None)

            if items is None:
                return None

            if single_data:
                return items[0] if len(items) else None
            else:
                return items
