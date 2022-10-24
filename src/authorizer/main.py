"""
LAMBDA is authorizing everything for now
"""
import os
import re


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

    policy = GenPolicy(
        principal_id='userAgent|Slackbot 1.0 (+https://api.slack.com/robots)',
        rest_api_id=event['requestContext']['apiId'],
        resource_arn=event['methodArn']
    )

    # Deny everything
    # policy.deny_all_methods()

    if not event['headers'].get('X-Slack-Signature') or not event['headers'].get('X-Slack-Request-Timestamp'):
        return policy

    policy.allow_method("POST", "/*")

    auth_response = policy.build()
 
    context = {
        'slack_token': 'SLACK_TOKEN',
    }
 
    auth_response['context'] = context

    print(auth_response)
    
    return auth_response


class GenPolicy:

    def __init__(self, principal_id: str, rest_api_id: str, resource_arn: str) -> None:
        self.resource_arn = resource_arn
        self.principal_id = principal_id
        
        self.rest_api_id = rest_api_id
        self.stage = os.environ.get('STAGE')

        self.version = "2012-10-17"
        self.path_regex = "^[/.a-zA-Z0-9-\*]+$"
        self.allow_methods = []
        self.deny_methods = []


        if not self.rest_api_id or not self.stage:
            raise Exception('Unauthorized')

        self.__get_resources_arn()


    def __get_resources_arn(self) -> None:
        _tmp = self.resource_arn.split(':')
        _apgw_arn_tmp = _tmp[5].split('/')

        self.aws_account_id = _tmp[4]
        self.rest_api_id = _apgw_arn_tmp[0]
        self.region = _tmp[3]
        self.stage = _apgw_arn_tmp[1]


    def _add_method(self, effect: str, verb: str, resource: str, conditions: dict) -> None:
        if verb != "*" and verb not in ["GET", "POST", "OPTIONS"]:
            raise NameError(f"Invalid HTTP verb {verb}. Allowed verbs in HttpVerb class")

        resource_pattern = re.compile(self.path_regex)

        if not resource_pattern.match(resource):
            raise NameError(f"Invalid resource path: {resource}. Path should match: {self.path_regex}")

        if resource[:1] == "/":
            resource = resource[1:]

        resource_arn = (
            f"arn:aws:execute-api:{self.region}:{self.aws_account_id}:{self.rest_api_id}/{self.stage}/{verb}/{resource}"
        )

        if effect.lower() == "allow":
            self.allow_methods.append({
                'resourceArn': resource_arn,
                'conditions': conditions
            })
        elif effect.lower() == "deny":
            self.deny_methods.append({
                'resourceArn': resource_arn,
                'conditions': conditions
            })

    def _get_empty_statement(self, effect: str) -> dict:
        statement = {
            'Action': 'execute-api:Invoke',
            'Effect': f"{effect[:1].upper()}{effect[1:].lower()}",
            'Resource': []
        }

        return statement

    def _get_statement_for_effect(self, effect, methods):
        statements = []

        if len(methods) > 0:
            statement = self._get_empty_statement(effect)

            for _method in methods:
                if _method['conditions'] is None or len(_method['conditions']) == 0:
                    statement['Resource'].append(_method['resourceArn'])
                else:
                    conditional_tatement = self._get_empty_statement(effect)
                    conditional_tatement['Resource'].append(_method['resourceArn'])
                    conditional_tatement['Condition'] = _method['conditions']
                    statements.append(conditional_tatement)

            statements.append(statement)

        return statements

    def deny_all_methods(self) -> None:
        self._add_method("Deny", "*", "*", [])

    def allow_method(self, verb, resource) -> None:
        self._add_method("Allow", verb, resource, [])

    def build(self) -> dict:
        if ((self.allow_methods is None or len(self.allow_methods) == 0) and
            (self.deny_methods is None or len(self.deny_methods) == 0)):
            raise NameError("No statements defined for the policy")

        policy = {
            'principalId': self.principal_id,
            'policyDocument': {
                'Version': self.version,
                'Statement': []
            }
        }

        policy['policyDocument']['Statement'].extend(
            self._get_statement_for_effect(
                "Allow",
                self.allow_methods
            )
        )
        policy['policyDocument']['Statement'].extend(
            self._get_statement_for_effect(
                "Deny",
                self.deny_methods
            )
        )

        return policy
