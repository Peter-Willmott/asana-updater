import json
import boto3
import os

JOBS_SECRET = json.loads(
    boto3.client("secretsmanager").get_secret_value(
        SecretId=os.getenv("JOBS_SECRET_ARN")
    )["SecretString"]
)
