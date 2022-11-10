"""
LAMBDA is authorizing everything for now
"""
import os
import re
import time
import hmac
import hashlib
import json

from exceptions import UnauthorizedError, GeneralError

from urllib.parse import parse_qs

from aws_lambda_powertools import Logger
from aws_lambda_powertools.logging import correlation_paths

from aws_lambda_powertools.utilities.typing import LambdaContext
from aws_lambda_powertools.event_handler import content_types


_LOGGER = Logger()


def handle_invalid_request(event: dict, status_code: int, ex: UnauthorizedError):  # receives exception raised
    metadata = {
        "event": event
    }
    _LOGGER.error(f"Malformed request: {ex}", extra=metadata)

    return {
        'statusCode': status_code,
        'isBase64Encoded': False,
        'headers': {
            'Content-Type': content_types.TEXT_PLAIN
        },
        'body': json.dumps({'msg': 'Invalid auth headers.'})
    }


def wrapper(**kwargs) -> str:

    def wrap(f):
        @_LOGGER.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST, log_event=True)
        def new_f(event, context):
            timestamp = event['headers'].get('X-Slack-Request-Timestamp')
            sig_from_slack = event['headers'].get('X-Slack-Signature')
            request_body = event['body']
            slack_signing_secret = os.environ.get('SLACK_SIGNING_SECRET')

            if kwargs.get('check_slack_sig', True):
                if not sig_from_slack or not timestamp or not slack_signing_secret:
                    return handle_invalid_request(event, 403, UnauthorizedError('Missing slack defined headers'))

                if abs(time.time() - int(timestamp)) > 60 * 5:
                    return handle_invalid_request(event, 403, UnauthorizedError('Unknown timestamp'))

                sig_basestring = f'v0:{timestamp}:{request_body}'
                computed_hash = hmac.new(
                    key=slack_signing_secret.encode('utf-8'),
                    msg=sig_basestring.encode('utf-8'),
                    digestmod=hashlib.sha256
                ).hexdigest()

                signature_to_match = f'v0={computed_hash}'
                if not hmac.compare_digest(signature_to_match, sig_from_slack):
                    return handle_invalid_request(event, 403, UnauthorizedError('Signature does not match'))
            try:
                response = f(event, context)
                return response
            except Exception as e:
                return handle_invalid_request(event, 403, GeneralError(f'Function raised an error: {e}'))
        return new_f
    return wrap


