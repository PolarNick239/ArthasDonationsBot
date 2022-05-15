import threading
from typing import Callable, Protocol


NewPostCallback = Callable[[str], None]
StatusChangedCallback = Callable[[str], None]
StartedCallback = Callable[[str, str, str], None]
TitleChangedCallback = Callable[[str], None]
GameChangedCallback = Callable[[str], None]
StoppedCallback = Callable[[], None]


class StreamerMonitor(Protocol):
    username: str

    def start(self) -> threading.Thread: ...

    def stop(self) -> None: ...

    def add_new_post_callback(self, callback: NewPostCallback) -> None: ...

    def add_channel_status_callback(self, callback: StatusChangedCallback) -> None: ...

    def add_start_callback(self, callback: StartedCallback) -> None: ...

    def add_game_changed_callback(self, callback: TitleChangedCallback) -> None: ...

    def add_title_changed_callback(self, callback: GameChangedCallback) -> None: ...

    def add_stop_callback(self, callback: StoppedCallback) -> None: ...


