import os
import cv2
import signal
import logging
import threading
import subprocess
import numpy as np

logger = logging.getLogger("Stream snapshots")


class StreamVideoSnapshots:
    def __init__(self):
        self.fifo_filename = "/tmp/stream"
        self.streamlink_process = None
        self.ffmpeg_process = None

        self.thread = None
        self.stopped = True
        self.lock = threading.Lock()

        self.image_callbacks = []

    def start(self, channel):
        self.stop()

        try:
            os.remove(self.fifo_filename)
        except FileNotFoundError:
            pass
        os.mkfifo(self.fifo_filename)

        streamlink_command = ["streamlink", "twitch.tv/{}".format(channel), "--default-stream", "1080p,1080p60", "--loglevel", "warning",
                              "-o", self.fifo_filename]
        logger.info("streamlink launched: {}".format(" ".join(streamlink_command)))
        self.streamlink_process = subprocess.Popen(streamlink_command, stderr=subprocess.DEVNULL, preexec_fn=os.setsid)

        ffmpeg_command = ["ffmpeg",
                          '-i', self.fifo_filename,  # named pipe
                          '-pix_fmt', 'bgr24',  # opencv requires bgr24 pixel format.
                          "-r", "1",
                          '-vcodec', 'rawvideo',
                          '-an', '-sn',  # we want to disable audio processing (there is no audio)
                          '-f', 'image2pipe', '-']
        logger.info("ffmpeg launched:     {}".format(" ".join(ffmpeg_command)))
        self.ffmpeg_process = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, bufsize=10 ** 8, preexec_fn=os.setsid)

        self.stopped = False

        self.thread = threading.Thread(target=self.run_loop, name="Stream snapshots")
        self.thread.start()

    def run_loop(self):
        failed = False
        while not self.stopped and not failed:
            img = None

            self.lock.acquire()
            try:
                if self.stopped:
                    break
                raw_image = self.ffmpeg_process.stdout.read(1920 * 1080 * 3)
                img = np.fromstring(raw_image, dtype='uint8')
                if len(img) != 1080 * 1920 * 3:
                    logger.error("Img bytes number = {}, while expected = {}!".format(len(img), 1080 * 1920 * 3))
                    failed = True
                    break

                img = img.reshape((1080, 1920, 3))

                self.ffmpeg_process.stdout.flush()
            finally:
                self.lock.release()

            if img is not None:
                self.on_image(img)

        if failed:
            self.failed()

    def failed(self):
        self.stop()

    def on_image(self, img):
        for callback in self.image_callbacks:
            callback(img)

    def add_image_callback(self, callback):
        self.image_callbacks.append(callback)

    def stop(self):
        self.lock.acquire()
        try:
            self.stopped = True
            if self.ffmpeg_process is not None:
                logger.info("Stopping ffmpeg process...")
                os.killpg(os.getpgid(self.ffmpeg_process.pid), signal.SIGTERM)
                self.ffmpeg_process = None
            if self.streamlink_process is not None:
                logger.info("Stopping streamlink process...")
                os.killpg(os.getpgid(self.streamlink_process.pid), signal.SIGTERM)
                self.streamlink_process = None
            logger.info("Video stream stopped!")
        finally:
            self.lock.release()


if __name__ == '__main__':
    import config

    logging.basicConfig(level=logging.DEBUG, format=config.logger_format)

    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    channel = config.channel

    video = StreamVideoSnapshots()


    def on_image(img):
        cv2.imshow("Video", img)
        key = cv2.waitKey(1)
        if key != -1:
            if key == 32:
                cv2.waitKey()
            if key == 115:  # S
                video.stop()
                print("Stopped... Press one more button to start again!")
                cv2.waitKey()
                video.start(channel)
                print("Started!...")
            else:
                print(key)


    video.add_image_callback(on_image)
    video.start(channel)
