import os
import json
import requests
from datetime import datetime, timedelta

from wrapper import wrapper, _LOGGER
from dynamodb import DDB
from ssm import ssm

from typing import Optional

from jinja2 import Environment, FileSystemLoader

from config import TOTAL_MINUTES_TO_EXPIRE

from aws_lambda_powertools.utilities.typing import LambdaContext


_SLACK_BOT_USER_TOKEN = os.environ.get("BOT_USER_TOKEN")
_SLACK_BOT_TOKEN = os.environ.get("BOT_TOKEN")
_SLACKP_API_BASE_URL = 'https://slack.com/api'
_BASE_PATH_TEMPLATE = os.path.dirname(os.path.abspath(__file__))
_BASE_JINJA_PATH_ENV_ENV = Environment(loader=FileSystemLoader(_BASE_PATH_TEMPLATE))
_JINJA_TEMPLATE = _BASE_JINJA_PATH_ENV_ENV.get_template("./index.html")
_JINJA_NOT_FOUND_TEMPLATE = _BASE_JINJA_PATH_ENV_ENV.get_template("./not_found.html")


def __make_api_call(method: str, action: Optional[str] = None, qs: Optional[str] = None,
                    use_bot_token: Optional[bool] = False,
                    auth: Optional[bool] = True,
                    url: Optional[str] = None,
                    **kwargs) -> dict:

    _requester = getattr(requests, method)

    _headers = kwargs.get('headers', {})

    if auth:
        if use_bot_token:
            token = _SLACK_BOT_TOKEN
        else:
            token = _SLACK_BOT_USER_TOKEN

        _headers.update({
            "Authorization": f"Bearer {token}"
        })

    if kwargs.get('json'):
        _headers.update({
            "Content-Type": "application/json;charset=UTF-8",
        })

    if not url:
        url = f'{_SLACKP_API_BASE_URL}/{action}'

        if qs:
            url = f'{url}?{qs}'

    response = _requester(url, headers=_headers, **kwargs)

    try:
        response = response.json()
    except Exception as e:
        response = response.text

    return response


@wrapper(check_slack_sig=False)
def handler(event: dict, context: LambdaContext) -> str:
    _LOGGER.debug(event)
    _LOGGER.debug(context)
    
    item = DDB.get_secret(_id=event['pathParameters']['secret_id'])

    if item.get('Item'):

        item = item['Item']


        message_ts = __make_api_call(
            method='get',
            action='conversations.history',
            qs=f'channel={item["channel"]}&inclusive=true&oldest={item["reply_message_ts"]}'
        )

        ts = None

        if len(message_ts['messages']) > 0:

            for message in message_ts['messages']:

                try:
                    url_id = message.get('attachments')[1]['actions'][0]['url']
                except Exception as e:
                    pass
                else:
                    if item['id'] in url_id:
                        ts = message['ts']
                        break

            if ts:
                dialog_form = {
                    "link_names": True,
                    "channel": item['channel'],
                    "replace_original": "true",
                    'response_type': 'in_channel',
                    'replace_original': 'true',
                    'delete_original': 'true',
                    'ts': ts,
                    "attachments": [
                        {
                            "title": "This secret was revealed, therefore deleted!",
                            "text": f":white_check_mark: *This secret has been opened and deleted! {datetime.now()}",
                        }
                    ]
                }
                dl = __make_api_call(
                    method='post',
                    action='chat.delete',
                    json={
                        'channel': item['channel'],
                        'ts': ts
                    }
                )

                resp = __make_api_call(
                    method='post',
                    auth=False,
                    url=item['response_url'],
                    json=dialog_form
                )

                total_minutes = (datetime.fromtimestamp(int(item['ttl'])) - datetime.now()) // timedelta(minutes=1)

                secret = ssm.get_secret(_id=item['id'])

                if total_minutes <= 0 and secret:
                    total_minutes = TOTAL_MINUTES_TO_EXPIRE

                context = {
                    'minutes_to_add': total_minutes,
                    'user': item['user_name'],
                    'secret': secret
                }
                response = _JINJA_TEMPLATE.render(**context)

                if DDB.delete_secret(item['id']) and ssm.delete_secret(_id=item['id']):
                    print('RETURNED')
                    return {
                        'statusCode': 200,
                        'body': response,
                        'headers': {
                            'Content-Type': 'text/html'
                        }
                    }

    return {
        'statusCode': 200,
        'body': _JINJA_NOT_FOUND_TEMPLATE.render(),
        'headers': {
            'Content-Type': 'text/html'
        }
    }
