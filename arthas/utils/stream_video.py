import os
import tempfile
from io import TextIOWrapper
from typing import Callable, Optional

import time
import fcntl
import signal
import pathlib
import logging
import threading
import subprocess

import numpy as np

logger = logging.getLogger("Stream snapshots")


ImageCallback = Callable[[np.ndarray], None]


class StreamVideoSnapshots:
    STREAM_URL = 'https://www.youtube.com/watch?v={video_id}'

    def __init__(self) -> None:
        with tempfile.NamedTemporaryFile(delete=True) as f:
            self.fifo_filename = f.name
        self.logs_dir = pathlib.Path("stream_video_logs")

        self.streamlink_process: Optional[subprocess.Popen[bytes]] = None
        self.ffmpeg_process: Optional[subprocess.Popen[bytes]] = None

        self.streamlink_process_log: Optional[TextIOWrapper] = None
        self.ffmpeg_process_log: Optional[TextIOWrapper] = None

        self.thread: Optional[threading.Thread] = None
        self.stopped = True
        self.lock = threading.RLock()

        self.image_callbacks: list[ImageCallback] = []

    def start(self, video_id: str) -> None:
        self.lock.acquire()
        try:
            self.stop()

            try:
                os.remove(self.fifo_filename)
            except FileNotFoundError:
                pass
            os.mkfifo(self.fifo_filename)

            self.logs_dir.mkdir(exist_ok=True)
            timestamp = int(time.time())

            streamlink_command = [
                "streamlink", self.STREAM_URL.format(video_id=video_id),
                "--default-stream", "1080p,1080p60",
                "--loglevel", "debug",
                "-o", self.fifo_filename
            ]
            logger.info("streamlink launched: {}".format(" ".join(streamlink_command)))

            self.streamlink_process_log = (self.logs_dir / "{}_streamlink".format(timestamp)).open("a")
            self.streamlink_process = subprocess.Popen(
                streamlink_command, stdout=self.streamlink_process_log, stderr=self.streamlink_process_log
            )

            ffmpeg_command = ["ffmpeg",
                              '-i', self.fifo_filename,  # named pipe
                              '-pix_fmt', 'bgr24',  # opencv requires bgr24 pixel format.
                              "-r", "1",
                              '-vcodec', 'rawvideo',
                              '-an', '-sn',  # we want to disable audio processing (there is no audio)
                              '-loglevel', 'debug',
                              '-f', 'image2pipe', '-']
            logger.info("ffmpeg launched:     {}".format(" ".join(ffmpeg_command)))

            self.ffmpeg_process_log = (self.logs_dir / "{}_ffmpeg".format(timestamp)).open("a")
            self.ffmpeg_process = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, stderr=self.ffmpeg_process_log)

            logger.info("Video start timestamp: {}".format(timestamp))

            self.stopped = False

            self.thread = threading.Thread(target=lambda: self.run_loop(video_id), name="Stream snapshots")
            self.thread.start()
        finally:
            self.lock.release()

    def run_loop(self, video_id: str) -> None:
        failed = False
        restart = False
        raw_image = b""

        assert self.ffmpeg_process is not None
        assert self.ffmpeg_process.stdout is not None
        flag = fcntl.fcntl(self.ffmpeg_process.stdout, fcntl.F_GETFL)
        fcntl.fcntl(self.ffmpeg_process.stdout.fileno(), fcntl.F_SETFL, flag | os.O_NONBLOCK)

        previous_img_time = time.time()

        while not self.stopped and not failed and not restart:
            try:
                img = None

                self.lock.acquire()
                try:
                    if self.stopped:
                        break
                    new_data = self.ffmpeg_process.stdout.read(1920 * 1080 * 3 - len(raw_image))
                    if new_data is not None and len(new_data) > 0:
                        raw_image += new_data
                        if len(raw_image) == 1080 * 1920 * 3:
                            img = np.frombuffer(raw_image, dtype=np.uint8)
                            raw_image = b''
                            img = img.reshape((1080, 1920, 3))
                    else:
                        time.sleep(0.001)
                finally:
                    self.lock.release()

                current_time = time.time()

                if img is not None:
                    self.on_image(img)
                    previous_img_time = current_time

                if current_time - previous_img_time > 60:
                    logger.error("No image for a minute!")
                    restart = True
            except Exception as e:
                logger.error(e)

        if restart:
            self.start(video_id)
        elif failed:
            self.failed()

    def failed(self) -> None:
        self.stop()

    def on_image(self, img: np.ndarray) -> None:
        for callback in self.image_callbacks:
            callback(img)

    def add_image_callback(self, callback: ImageCallback) -> None:
        self.image_callbacks.append(callback)

    def stop(self) -> None:
        self.lock.acquire()
        try:
            self.stopped = True
            if self.streamlink_process is not None:
                logger.info("Stopping streamlink process...")
                try:
                    os.kill(self.streamlink_process.pid, signal.SIGTERM)
                except ProcessLookupError as e:
                    logger.error("Error while terminating streamlink: {}".format(e))
                self.streamlink_process = None
                assert self.streamlink_process_log is not None
                self.streamlink_process_log.close()
                self.streamlink_process_log = None
            if self.ffmpeg_process is not None:
                logger.info("Stopping ffmpeg process...")
                try:
                    os.kill(self.ffmpeg_process.pid, signal.SIGTERM)
                except ProcessLookupError as e:
                    logger.error("Error while terminating ffmpeg: {}".format(e))
                self.ffmpeg_process = None
                assert self.ffmpeg_process_log is not None
                self.ffmpeg_process_log.close()
                self.ffmpeg_process_log = None
            logger.info("Video stream stopped!")
        finally:
            self.lock.release()
