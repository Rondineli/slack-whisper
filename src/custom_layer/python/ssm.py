import boto3
import os

from datetime import datetime

from typing import Optional, Callable


_SSM = boto3.client('ssm')

_BASE_SECRETS_NAME = os.environ.get('BASE_SECRETS_NAME', '/prod/slack_whisper')



class ISSM:
    def __init__(self, ssm_client: Optional[Callable] = _SSM,
                 base_name_secret: Optional[Callable] = _BASE_SECRETS_NAME) -> None:

        self.client = ssm_client
        self.base_name_secret = base_name_secret

    def create_secret(self, _id: str, secret: str, user: str) -> bool:
        _created = True

        created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        secret = self.client.put_parameter(
            Name=f'{self.base_name_secret}/{_id}',
            Description=f'Secreted created by {user} at {created_at}',
            KeyId=os.environ.get('KMS_ID'),
            Type='SecureString',
            Value=secret
        )

        return True

    def delete_secret(self, _id: str) -> bool:
        _response = False

        try:
            self.client.delete_parameter(
                Name=f'{self.base_name_secret}/{_id}'
            )
            _response = True
        except Exception as e:
            _response = False

        return _response

    def get_secret(self, _id: str) -> str:
        _secret = None

        try:

            _secret = self.client.get_parameter(
                Name=f'{self.base_name_secret}/{_id}',
                WithDecryption=True
            ).get("Parameter").get("Value")

        except Exception as e:
            print(e)

        return _secret

ssm = ISSM()
