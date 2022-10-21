import os

from constructs import Construct
from aws_cdk import App, Stack    

from aws_cdk import (
    aws_sam as sam,
    aws_lambda as _lambda,
    aws_apigateway as apigw
)

_POWERTOOLS_BASE_NAME = 'AWSLambdaPowertools'
# Find latest from github.com/awslabs/aws-lambda-powertools-python/releases
_POWERTOOLS_VER = '1.30.0'
_POWERTOOLS_ARN = 'arn:aws:serverlessrepo:eu-west-1:057560766410:applications/aws-lambda-powertools-python-layer'
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_SRC_CODE = os.path.join(_BASE_DIR, '../../src/slack_commands/')


class SlackWhisperStack(Stack):

     def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:

        application_name = kwargs.pop('application_name', 'slack-whisper-command')

        super(SlackWhisperStack, self).__init__(scope, construct_id, **kwargs)

        # Launches SAR App as CloudFormation nested stack and return Lambda Layer
        powertools_app = sam.CfnApplication(self,
            f'{_POWERTOOLS_BASE_NAME}SlackWhisperApplication',
            location={
                'applicationId': _POWERTOOLS_ARN,
                'semanticVersion': _POWERTOOLS_VER
            },
        )

        powertools_layer_arn = powertools_app.get_att("Outputs.LayerVersionArn").to_string()

        powertools_layer_version = _lambda.LayerVersion.from_layer_version_arn(self, f'{_POWERTOOLS_BASE_NAME}', powertools_layer_arn)

        slack_commands_lambdas = _lambda.Function(self,
            application_name,
            runtime=_lambda.Runtime.PYTHON_3_8,
            function_name=application_name,
            code=_lambda.Code.from_asset(_SRC_CODE),
            handler='handler.handler',
            layers=[powertools_layer_version]
        )

        apigw.LambdaRestApi(
            self,
            'Endpoint',
            handler=slack_commands_lambdas,
        )