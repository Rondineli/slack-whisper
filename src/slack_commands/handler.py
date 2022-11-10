import os
import json
import requests
import uuid
import urllib

from urllib.parse import parse_qs, unquote
from datetime import datetime

from wrapper import wrapper, _LOGGER
from dynamodb import DDB
from ssm import ssm

from aws_lambda_powertools.utilities.typing import LambdaContext


_SECRET_INTERNAL_ALB_URL = os.environ.get('SECRET_INTERNAL_ALB_URL', 'https://www.google.com')



def send_secret_link(**payload) -> dict:
    if payload.get('secret'):
        secret = payload['secret']
    else:
        secret_key = list(payload["state"]["values"].keys())[0]
        secret = payload["state"]["values"][secret_key]["secret"]["value"]

    secret_id = str(uuid.uuid4())

    _ddb_secret_args = {
        '_id': secret_id,
        'channel': payload['channel'],
        'user_name': payload['user']['username'],
        'response_url': payload['response_url']
    }

    dialog_form = {}

    if payload.get('container'):
        _ddb_secret_args.update({'message_ts': payload["container"]["message_ts"]})

        dialog_form.update({
            'ts': payload['container']['message_ts']
        })
    
    #if payload.get('actions'):
    #    dialog_form['ts'] = payload['actions'][0]['action_ts']

    ssm.create_secret(secret_id, secret, payload['user']['username'])

    dialog_form.update({
        'link_names': True,
        'channel': payload['channel'],
        'response_type': 'in_channel',
        'replace_original': 'true',
        'delete_original': 'true',
        "attachments": [
            {
                'title': 'New secret shared!',
                'text': f':wave: <@{payload["user"]["username"]}> Has shared a secret with you!',
            },
            {
                'fallback': 'Reveal the secret?',
                'title': 'Reveal secret!',
                'callback_id': 'shared_secret',
                'color': '#3AA3E3',
                'attachment_type': 'default',
                'actions': [
                    {
                      'type': 'button',
                      'text': 'Go to secret reveal :lock:',
                      'url': f'{_SECRET_INTERNAL_ALB_URL}/secret/{secret_id}'
                    }
                ]
            }
        ]
    })




    resp = requests.post(
        payload['response_url'],
        json=dialog_form
    )

    print(dialog_form)

    if 'ok' in resp.text: # this is ugly, but sometimes slack api returns a {"ok" true}
        ts = datetime.strptime(
            resp.headers['date'],
            '%a, %d %b %Y %X %Z'
        ).strftime("%s")

        _ddb_secret_args.update({
            'reply_message_ts': ts
        })
        try:
            DDB.add_secret(**_ddb_secret_args)
        except Exception as e:
            print(f'Exception here: {str(e)}')
            raise GeneralError('Exception test here')

        return {
            'statusCode': 200
        }

    return {
            'statusCode': 500,
            'body': 'Error to process this request'
        }


@wrapper()
def handler(event: dict, context: LambdaContext) -> str:
    _LOGGER.debug(event)
    _LOGGER.debug(context)

    body = parse_qs(event['body'])

    # If it is a response from our form sent when the comma
    if body.get('payload'):
        payload = json.loads(body['payload'][0])
        channel = payload['channel']['id']

        payload.update({
            'channel': channel
        })

        return send_secret_link(**payload)

    response_url = body.get('response_url')[0]
    trigger_id = body['trigger_id'][0]
    text = None

    channel = body['channel_id'][0]

    if body.get('text'):
        text = body['text'][0]

        payload = {
            'secret': text,
            'channel': channel,
            'user': {
                'username': body['user_name'][0]
            },
            'container': {
              'message_ts': body['trigger_id'][0]  
            },
            'response_url': response_url
        }

        return send_secret_link(**payload)

    dialog_form  = {
        "title": {
            "type": "plain_text",
            "text": "Share your secret!"
        },
        "submit": {
            "type": "plain_text",
            "text": "Submit"
        },
        "blocks": [
            {
                "type": "input",
                "element": {
                    "type": "plain_text_input",
                    "action_id": "secret",
                    "placeholder": {
                        "type": "plain_text",
                        "text":  "Tell me your secret!"
                    }
                },
                "label": {
                    "type": "plain_text",
                    "text": f":wave: Hey <@{body['user_name'][0]}>!\n\nTell me your secret, dont worry it is very secure!",
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "action_id": "save",
                        "text": {
                            "type": "plain_text",
                            "text": "Share!"
                        }
                    }
                ]
            }
        ],
        "type": "modal"
    }

    return {
        'statusCode': 200,
        'body': json.dumps(dialog_form)
    }
