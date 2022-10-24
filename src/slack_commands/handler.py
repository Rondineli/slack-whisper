import json

from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext

#import boto3
#
#ddb = boto3.resource('dynamodb')
#table = ddb.Table(os.environ['HITS_TABLE_NAME'])

_LOGGER = Logger()


@_LOGGER.inject_lambda_context(log_event=True)
def handler(event: dict, context: LambdaContext) -> str:
    _LOGGER.debug(event)
    _LOGGER.debug(context)

    return {
        'statusCode': 200,
        'body': json.dumps({
            "response_type": "in_channel",
            "text": "I am alive!"
        })
    }