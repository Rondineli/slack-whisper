import os

from constructs import Construct
from aws_cdk import App, Stack, RemovalPolicy

from aws_cdk import (
    aws_sam as sam,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
    aws_dynamodb as dynamodb
)

_POWERTOOLS_BASE_NAME = 'AWSLambdaPowertools'
_POWERTOOLS_VER = '1.30.0'
_POWERTOOLS_ARN = 'arn:aws:serverlessrepo:eu-west-1:057560766410:applications/aws-lambda-powertools-python-layer'
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_SRC_CODE = os.path.join(_BASE_DIR, '../../src/slack_commands/')
_TABLE_NAME = os.environ.get('TABLE_NAME', 'slack_whisper_table')


class SlackWhisperStack(Stack):

     def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:

        application_name = kwargs.pop('application_name', 'slack-whisper-command')
        global_table_regions = kwargs.pop('global_table_regions', None)

        super(SlackWhisperStack, self).__init__(scope, construct_id, **kwargs)

        # Launches SAR App as CloudFormation nested stack and return Lambda Layer
        powertools_app = sam.CfnApplication(
            self,
            f'{_POWERTOOLS_BASE_NAME}SlackWhisperApplication',
            location={
                'applicationId': _POWERTOOLS_ARN,
                'semanticVersion': _POWERTOOLS_VER
            },
        )

        powertools_layer_arn = powertools_app.get_att("Outputs.LayerVersionArn").to_string()

        powertools_layer_version = _lambda.LayerVersion.from_layer_version_arn(
            self,
            f'{_POWERTOOLS_BASE_NAME}',
            powertools_layer_arn
        )

        _ddb_kwargs = {}

        if global_table_regions:
            _ddb_kwargs['replication_regions'] = global_table_regions

        global_table = dynamodb.Table(
            self,
            _TABLE_NAME,
            partition_key=dynamodb.Attribute(
                name="id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PROVISIONED,
            **_ddb_kwargs
        )

        slack_commands_lambda = _lambda.Function(self,
            application_name,
            current_version_options=_lambda.VersionOptions(
                removal_policy=RemovalPolicy.RETAIN,  # retain old versions
                retry_attempts=2
            ),
            runtime=_lambda.Runtime.PYTHON_3_8,
            function_name=application_name,
            code=_lambda.Code.from_asset(_SRC_CODE),
            handler='handler.handler',
            layers=[powertools_layer_version],
            environment={
                "DDB_TABLE": _TABLE_NAME
            }
        )

        slack_commands_lambda.add_alias("live")

        apigw.LambdaRestApi(
            self,
            'SlackCommandsEndpoint',
            description='Api endpoint for slack command handler',
            rest_api_name='slack_commands_api',
            handler=slack_commands_lambda,
        )