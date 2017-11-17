import socket
import logging
import threading

logger = logging.getLogger("IRC monitor")


# See https://dev.twitch.tv/docs/irc
class IRCTwitchMonitor:
    def __init__(self, nickname, oauth_key, channel, host, port=6667):
        self.nickname = nickname
        self.oauth_key = oauth_key
        self.channel = channel
        self.host = host
        self.port = port

        self.socket = None
        self.stopped = False

        self.buffer = b""
        self.lines = []

        self.messages_callbacks = []

        self.connect()

    def connect(self):
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

    def next_line(self):
        while len(self.lines) == 0:
            self.buffer = self.buffer + self.socket.recv(1024)
            if len(self.buffer) == 0:
                logger.error("Empty buffer!")
                raise ConnectionAbortedError("Empty buffer!")
            lines_bytes = self.buffer.split("\r\n".encode("utf-8"))
            self.buffer = lines_bytes.pop()

            self.lines = [line_bytes.decode("utf-8") for line_bytes in lines_bytes]

        return self.lines.pop(0)

    def start(self):
        thread = threading.Thread(target=self.run_loop, name="IRC monitor")
        thread.start()
        return thread

    def stop(self):
        self.stopped = True

    def run_loop(self):
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

    def add_message_callback(self, callback):
        self.messages_callbacks.append(callback)

    def parse_message(self, line):
        # Expected format:
        # :<user>!<user>@<user>.tmi.twitch.tv
        parts = line.split('.tmi.twitch.tv PRIVMSG #{} :'.format(self.channel), 1)
        if len(parts) != 2:
            return None
        username, message = parts

        username = self.parse_username(username)
        if not username:
            return None

        return username, message

    def parse_username(self, username_part):
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

    def send(self, str):
        self.socket.send((str + "\r\n").encode("utf-8"))

    def send_message(self, message):
        self.send("PRIVMSG #" + self.channel + " :" + message)


if __name__ == '__main__':
    import config

    logging.basicConfig(level=logging.DEBUG, format=config.logger_format)

    monitor = IRCTwitchMonitor(config.nickname, config.oauth_key, config.channel, config.host)
    monitor.add_message_callback(lambda username, message: logger.debug("[{}] {}".format(username, message)))

    try:
        thread = monitor.start()
        thread.join()
    except KeyboardInterrupt:
        monitor.stop()
