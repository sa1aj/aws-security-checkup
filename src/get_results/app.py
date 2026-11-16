import json
import os

import boto3
from boto3.dynamodb.conditions import Key

table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])


def lambda_handler(event, context):
    response = table.query(
        KeyConditionExpression=Key("pk").eq("SCAN"),
        ScanIndexForward=False,
        Limit=1,
    )
    items = response["Items"]

    if not items:
        return {
            "statusCode": 404,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"message": "No scans yet. POST /scan first."}),
        }

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(items[0], default=str),
    }
