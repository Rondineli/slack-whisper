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
_SRC_CODE_AUTH = os.path.join(_BASE_DIR, '../../src/authorizer/')
_TABLE_NAME = os.environ.get('TABLE_NAME', 'slack_whisper_table')


class SlackWhisperStack(Stack):

     def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:

        application_name = kwargs.pop('application_name', 'slack-whisper-command')
        global_table_regions = kwargs.pop('global_table_regions', None)
        api_gw_stage = kwargs.pop('apigw_stage', 'v1')

        super(SlackWhisperStack, self).__init__(scope, construct_id, **kwargs)

        # POWER TOOLS SAR
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

        # DYNAMODB TABLE
        _ddb_kwargs = {}

        if global_table_regions:
            _ddb_kwargs['replication_regions'] = global_table_regions

        global_table = dynamodb.Table(
            self,
            _TABLE_NAME,
            table_name=_TABLE_NAME,
            partition_key=dynamodb.Attribute(
                name="id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PROVISIONED,
            **_ddb_kwargs
        )

        # SLACK COMMAND HANDLER LAMBDA
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

        # LAMBDA authorizer
        slack_integration_auth_handler = _lambda.Function(self,
            f"{application_name}-authorizer",
            current_version_options=_lambda.VersionOptions(
                removal_policy=RemovalPolicy.RETAIN,  # retain old versions
                retry_attempts=2
            ),
            runtime=_lambda.Runtime.PYTHON_3_8,
            function_name=f"{application_name}-authorizer",
            code=_lambda.Code.from_asset(_SRC_CODE_AUTH),
            handler='main.handler',
            layers=[powertools_layer_version],
            environment={
                "STAGE": api_gw_stage #, "APIGW_REST_API_ID": slack_bot_command_api.rest_api_id
            }
        )

        authorizer = apigw.RequestAuthorizer(
            self,
            "SlackIntegrationAuthorizer",
            handler=slack_integration_auth_handler,
            identity_sources=[
                apigw.IdentitySource.header("X-Slack-Signature"),
                apigw.IdentitySource.header("X-Slack-Request-Timestamp"),
            ]
        )

        # API GATEWAY FOR BOT COMMANDS
        slack_bot_command_api = apigw.LambdaRestApi(
            self,
            'SlackCommandsEndpoint',
            description='Api endpoint for slack command handler',
            rest_api_name='slack_commands_api',
            handler=slack_commands_lambda,
            default_method_options={
                "authorizer": authorizer,
                "authorization_type": apigw.AuthorizationType.CUSTOM
            },
            deploy=False

        )

        deployment = apigw.Deployment(
            self,
            "Deployment",
            api=slack_bot_command_api
        )

        apigw.Stage(
            self,
            api_gw_stage,
            deployment=deployment
        )
