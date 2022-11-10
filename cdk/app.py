#!/usr/bin/env python3

import aws_cdk as cdk

from cdk.cdk_stack import SlackWhisperStack

from utils.load_config import Config


STACK_ID = Config.pop('id', 'slack-whisper-infra')

app = cdk.App()
SlackWhisperStack(app, STACK_ID, **Config)

app.synth()
