import os

from datetime import datetime

from constructs import Construct
from aws_cdk import App, Stack, RemovalPolicy

from aws_cdk import (
    aws_sam as sam,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
    aws_dynamodb as dynamodb,
    aws_kms as kms,
    aws_iam as iam,
    Duration
)

_POWERTOOLS_BASE_NAME = 'AWSLambdaPowertools'
_POWERTOOLS_VER = '1.30.0'
_POWERTOOLS_ARN = 'arn:aws:serverlessrepo:eu-west-1:057560766410:applications/aws-lambda-powertools-python-layer'
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_SRC_CODE = os.path.join(_BASE_DIR, '../../src/slack_commands/')
_SRC_CODE_SECRET_REVEAL = os.path.join(_BASE_DIR, '../../src/secret_reveal/')
_SRC_LAYER_CODE = os.path.join(_BASE_DIR, '../../src/layer/')
_SRC_CUSTOM_LAYER_CODE = os.path.join(_BASE_DIR, '../../src/custom_layer/')
_TABLE_NAME = os.environ.get('TABLE_NAME', 'slack_whisper_table')


class SlackWhisperStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:

        application_name = kwargs.pop('application_name', 'slack-whisper-command')
        slack_secret = kwargs.pop('slack_signing_secret') # TODO: get slack token from config
        global_table_regions = kwargs.pop('global_table_regions', None)
        api_gw_stage = kwargs.pop('apigw_stage', 'v1')
        slack_bot_token = kwargs.pop('slack_bot_token')
        slack_bot_user_token = kwargs.pop('slack_bot_user_token')
        total_minutes_to_expire_secret = kwargs.pop('total_minutes_to_expire_secrets', 40)

        self._encryption_key = kwargs.pop('encryption_key', None)

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

        local_layer = _lambda.LayerVersion(self, "MyLayer",
            removal_policy=RemovalPolicy.RETAIN,
            code=_lambda.Code.from_asset(_SRC_LAYER_CODE),
            compatible_architectures=[_lambda.Architecture.X86_64, _lambda.Architecture.ARM_64],
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_8]
        )

        custom_layer = _lambda.LayerVersion(
            self,
            "MyCustomLayer",
            removal_policy=RemovalPolicy.RETAIN,
            code=_lambda.Code.from_asset(_SRC_CUSTOM_LAYER_CODE),
            compatible_architectures=[_lambda.Architecture.X86_64, _lambda.Architecture.ARM_64],
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_8]
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
            time_to_live_attribute="ttl",
            billing_mode=dynamodb.BillingMode.PROVISIONED,
            **_ddb_kwargs
        )

        # API GATEWAY FOR BOT COMMANDS
        slack_bot_command_api = apigw.RestApi(
            self,
            'SlackCommandsEndpoint',
            description='Api endpoint for slack command handler',
            rest_api_name='slack_commands_api',
            deploy_options=apigw.StageOptions(
                stage_name=api_gw_stage
            )
        )

        # SECRET REVEAL HANDLER LAMBDA
        secret_reveal_lambda = _lambda.Function(self,
            f'{application_name}-secret-reveal',
            current_version_options=_lambda.VersionOptions(
                removal_policy=RemovalPolicy.RETAIN,  # retain old versions
                retry_attempts=2
            ),
            description=f'Lambda generated at: {datetime.now()}',
            runtime=_lambda.Runtime.PYTHON_3_8,
            function_name=f'{application_name}-secret-reveal-function',
            code=_lambda.Code.from_asset(_SRC_CODE_SECRET_REVEAL),
            handler='handler.handler',
            layers=[powertools_layer_version, local_layer, custom_layer],
            timeout=Duration.minutes(2),
            environment={
                "DDB_TABLE": _TABLE_NAME,
                "SLACK_SIGNING_SECRET": slack_secret,
                'BOT_TOKEN': slack_bot_token,
                'BOT_USER_TOKEN': slack_bot_user_token,
                'KMS_ID': self.encryption_key.key_id
            }
        )

        secret_reveal_lambda.add_alias("live")

        secret_reveal_lambda.role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            resources=[
                f'arn:aws:ssm:{self.region}:{self.account}:parameter/*',
                self.encryption_key.key_arn
            ],
            actions=[
                "ssm:*",
                "kms:*"
            ],
        ))

        global_table.grant_read_write_data(secret_reveal_lambda)

        # SLACK COMMAND HANDLER LAMBDA
        slack_commands_lambda = _lambda.Function(self,
            application_name,
            current_version_options=_lambda.VersionOptions(
                removal_policy=RemovalPolicy.RETAIN,  # retain old versions
                retry_attempts=2
            ),
            description=f'Lambda generated at: {datetime.now()}',
            runtime=_lambda.Runtime.PYTHON_3_8,
            function_name=f'{application_name}-function',
            code=_lambda.Code.from_asset(_SRC_CODE),
            handler='handler.handler',
            layers=[powertools_layer_version, local_layer, custom_layer],
            timeout=Duration.minutes(2),
            environment={
                "DDB_TABLE": _TABLE_NAME,
                "SLACK_SIGNING_SECRET": slack_secret,
                'BOT_TOKEN': slack_bot_token,
                'BOT_USER_TOKEN': slack_bot_user_token,
                'TOTAL_MINUTES_TO_EXPIRE': str(total_minutes_to_expire_secret),
                'KMS_ID': self.encryption_key.key_id,
                'SECRET_INTERNAL_ALB_URL': f'https://{slack_bot_command_api.rest_api_id}.execute-api.{self.region}.amazonaws.com/{api_gw_stage}'
            }
        )

        slack_commands_lambda.add_alias("live")

        global_table.grant_read_write_data(slack_commands_lambda)

        slack_commands_lambda.role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            resources=[
                f'arn:aws:ssm:{self.region}:{self.account}:parameter/*',
                self.encryption_key.key_arn
            ],
            actions=[
                "ssm:*",
                "kms:*"
            ],
        ))

        integration = apigw.LambdaIntegration(
            slack_commands_lambda,
            request_parameters={
                "integration.request.header.x-slack-signature": "method.request.header.x-slack-signature",
                "integration.request.header.x-slack-request-timestamp": "method.request.header.x-slack-request-timestamp"
            }
        )
        version_api = slack_bot_command_api.root.add_resource('secret')

        version_api.add_method(
            "POST",
            integration,
            request_validator_options=apigw.RequestValidatorOptions(
                request_validator_name='test-validator-2',
                validate_request_body=True,
                validate_request_parameters=True
            ),
            request_parameters={
                "method.request.header.x-slack-signature": True,
                "method.request.header.x-slack-request-timestamp": True
            }
        )


        # TODO: TMP get secrets on apigw
        integration_secret_reveal = apigw.LambdaIntegration(
            secret_reveal_lambda,
            request_parameters={
                "integration.request.path.secret_id": "method.request.path.secret_id"
            }
        )
        version_api_reveal = version_api.add_resource('{secret_id}')

        version_api_reveal.add_method(
            "GET",
            integration_secret_reveal,
            request_validator=apigw.RequestValidator(
                self,
                'NewValidatorBugWorkAround',
                rest_api=slack_bot_command_api,
                request_validator_name="test-validator-3",
                validate_request_body=True,
                validate_request_parameters=True
            ),
            request_parameters={
                "method.request.path.secret_id": True
            }
        )


        slack_bot_command_api.add_gateway_response(
            'badParametersResponse',
            type=apigw.ResponseType.BAD_REQUEST_PARAMETERS,
            status_code='400',
            templates={
                "application/json": '{ "message": "Invalid parameters", "statusCode": "400", "type": "$context.error.responseType" }'
            }
        )

        deployment = apigw.Deployment(
            self,
            "Deployment",
            api=slack_bot_command_api
        )

    @property
    def encryption_key(self):
        if not self._encryption_key:

            # KMS KEY TO ENCRYPT TEXT ON SSM
            self._encryption_key = kms.Key(
                self,
                "Key",
                enable_key_rotation=True
            )

        return self._encryption_key
