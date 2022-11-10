import os
import boto3
import time

from config import TOTAL_MINUTES_TO_EXPIRE

from typing import Optional, Callable


__all__ = [ 'SlackWhisperSecret', 'DDB' ]


_DDB = boto3.resource('dynamodb')

_TABLE = _DDB.Table(
    os.environ.get('DDB_TABLE', 'slack_whisper_table')
)


class SlackWhisperSecret:
    def __init__(self, table_resource: Optional[Callable] = _TABLE) -> None:
        self.table = table_resource

    def delete_secret(self, _id: str) -> bool:
        try:
            self.table.delete_item(
                Key={
                    'id': _id
                }
            )
        except Exception as e:
            print(f'Exception as :{str(e)}')
            return False

        return True

    def add_secret(self, _id: str, message_ts: str,
                   channel: str, user_name: str,
                   response_url: str, **kwargs) -> bool:
        """
        Adds a new secret to the table.

        :param message_ts: The original message to delete.
        :param channel: The channel the message were sent to.
        :param user_name: The user that created the secret.
        :param kwargs: Extra arguments to save on the table.
        """
        print(TOTAL_MINUTES_TO_EXPIRE)
        print(time.time())

        return self.table.put_item(
            Item={
                'id': _id,
                'message_ts': message_ts,
                'channel': channel,
                'user_name': user_name,
                'response_url': response_url,
                'ttl': int(time.time() + int(TOTAL_MINUTES_TO_EXPIRE)),
                **kwargs
            }
        )

    def get_secret(self, _id: str) -> dict:
        return self.table.get_item(Key={'id': _id})


DDB = SlackWhisperSecret()