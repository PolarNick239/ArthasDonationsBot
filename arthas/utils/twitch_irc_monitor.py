import socket
import logging
import threading

from abc import ABC
from typing import Optional, Callable

logger = logging.getLogger("IRC monitor")


OnMessageCallback = Callable[[str, str], None]


class ChatMonitor(ABC):
    def start(self) -> threading.Thread:
        pass

    def stop(self) -> None:
        pass

    def add_message_callback(self, callback: OnMessageCallback) -> None:
        pass


# See https://dev.twitch.tv/docs/irc
class IRCTwitchMonitor(ChatMonitor):
    def __init__(self, nickname: str, oauth_key: str, channel: str, host: str, port: int = 6667):
        self.nickname = nickname
        self.oauth_key = oauth_key
        self.channel = channel
        self.host = host
        self.port = port

        self.socket: Optional[socket.socket] = None
        self.stopped = False

        self.buffer = b''
        self.lines: list[str] = []

        self.messages_callbacks: list[OnMessageCallback] = []

        self.connect()

    def connect(self) -> None:
        self.socket = socket.socket()
        logger.info("Connecting socket...")
        self.socket.connect((self.host, self.port))
        logger.info("Socket connected!")

        logger.info("Authorizing...")
        self.send("PASS " + self.oauth_key)
        self.send("NICK " + self.nickname)
        self.send("JOIN #" + self.channel)

        while True:
            line = self.next_line()

            logger.debug(line)

            if "End of /NAMES list" in line:
                break

        logger.info("Authorized!")

    def next_line(self) -> str:
        while len(self.lines) == 0:
            assert self.socket, 'Socket is not initialized. Probably `connect()` method was not called'
            self.buffer = self.buffer + self.socket.recv(1024)
            if len(self.buffer) == 0:
                logger.error("Empty buffer!")
                raise ConnectionAbortedError("Empty buffer!")
            lines_bytes = self.buffer.split("\r\n".encode("utf-8"))
            self.buffer = lines_bytes.pop()

            self.lines = [line_bytes.decode("utf-8") for line_bytes in lines_bytes]

        return self.lines.pop(0)

    def start(self) -> threading.Thread:
        thread = threading.Thread(target=self.run_loop, name="IRC monitor")
        thread.start()
        return thread

    def stop(self) -> None:
        self.stopped = True

    def run_loop(self) -> None:
        while not self.stopped:
            line = self.next_line()

            if line == "PING :tmi.twitch.tv":
                self.send("PONG :tmi.twitch.tv")
                continue

            user_message = self.parse_message(line)
            if user_message is not None:
                username, message = user_message

                for callback in self.messages_callbacks:
                    callback(username, message)
                continue

            logger.warning("Unexpected message: {}".format(line))

    def add_message_callback(self, callback: OnMessageCallback) -> None:
        self.messages_callbacks.append(callback)

    def parse_message(self, line: str) -> Optional[tuple[str, str]]:
        # Expected format:
        # :<user>!<user>@<user>.tmi.twitch.tv
        parts = line.split('.tmi.twitch.tv PRIVMSG #{} :'.format(self.channel), 1)
        if len(parts) != 2:
            return None
        raw_username, message = parts

        username = self.parse_username(raw_username)
        if not username:
            return None

        return username, message

    def parse_username(self, username_part: str) -> Optional[str]:
        # Username part format:
        # :<user>!<user>@<user>
        if not username_part.startswith(":"):
            return None
        username_part = username_part[1:]

        parts1_23 = username_part.split("!")
        if len(parts1_23) != 2:
            return None

        parts23 = parts1_23[1].split("@")
        if len(parts23) != 2:
            return None

        if parts1_23[0] != parts23[0] or parts23[0] != parts23[1]:
            return None

        return parts1_23[0]

    def send(self, content: str) -> None:
        assert self.socket, 'Socket is not initialized. Probably `connect()` method was not called'
        self.socket.send((content + "\r\n").encode("utf-8"))

    def send_message(self, message: str) -> None:
        self.send("PRIVMSG #" + self.channel + " :" + message)


# if __name__ == '__main__':
#     import config
#
#     logging.basicConfig(level=logging.DEBUG, format=config.logger_format)
#
#     monitor = IRCTwitchMonitor(config.nickname, config.oauth_key, config.channel, config.host)
#     monitor.add_message_callback(lambda username, message: logger.debug("[{}] {}".format(username, message)))
#
#     try:
#         thread = monitor.start()
#         thread.join()
#     except KeyboardInterrupt:
#         monitor.stop()
