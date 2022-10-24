#!/usr/bin/env python3

import aws_cdk as cdk

from cdk.cdk_stack import SlackWhisperStack

# TODO: It will be future an argument
kwargs = {
	'description': 'Slack whisper stack'
}

app = cdk.App()
SlackWhisperStack(app, "slack-whisper-infra", **kwargs)

app.synth()
