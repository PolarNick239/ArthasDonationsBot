import os
import json
import logging

logger = logging.getLogger("File storage")


class FileStorage:
    def __init__(self, filename, *, dirpath="."):
        self.value = None
        self.dirpath = dirpath
        self.filepath = os.path.join(dirpath, filename)
        self.filepath_tmp = self.filepath + ".tmp"

    def save(self):
        if self.value is None:
            try:
                os.remove(self.filepath)
                logger.info("State deleted! ({})".format(self.filepath))
            except FileNotFoundError:
                logger.warning("No state already! ({})".format(self.filepath))
        else:
            os.makedirs(self.dirpath, exist_ok=True)

            with open(self.filepath_tmp, 'w') as state_file_tmp:
                if isinstance(self.value, str):
                    value_for_json = self.value
                elif isinstance(self.value, dict):
                    value_for_json = self.value
                elif hasattr(self.value, '_asdict'):
                    value_for_json = self.value._asdict()
                else:
                    raise AssertionError("Unsupported type in FileStorage! (value={})".format(self.value))
                json.dump(value_for_json, state_file_tmp)
                state_file_tmp.flush()
                os.fsync(state_file_tmp.fileno())
                state_file_tmp.close()

                os.rename(self.filepath_tmp, self.filepath)
            logger.info("State saved! ({})".format(self.filepath))

    def load(self, constructor=None):
        try:
            with open(self.filepath, mode='r') as state_file:
                data = json.load(state_file)
                if constructor is not None:
                    self.value = constructor(**data)
                else:
                    self.value = data
            logger.info("State loaded! ({})".format(self.filepath))
        except FileNotFoundError:
            logger.info("No state found, initialized with None! ({})".format(self.filepath))
            self.value = None
