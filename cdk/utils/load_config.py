import os
import json

from typing import Optional


__all__ = [ 'Config' ]


_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_config_json(config_file: Optional[str] = f'{_BASE_DIR}/../../config.json') -> dict:
    with open(config_file, 'rb') as json_file:
        return json.load(json_file)


Config = load_config_json()
