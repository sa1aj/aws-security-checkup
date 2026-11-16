import json
import os
from datetime import datetime, timezone

import boto3

lambda_client = boto3.client("lambda")
table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])

CHECK_FUNCTIONS = [
    os.environ["ROOT_MFA_FUNCTION"],
    os.environ["PUBLIC_S3_FUNCTION"],
]


def run_check(function_name):
    response = lambda_client.invoke(FunctionName=function_name)
    payload = json.loads(response["Payload"].read())
    if "FunctionError" in response:
        return {
            "check": function_name,
            "status": "ERROR",
            "details": payload.get("errorMessage", "Check failed to run."),
        }
    return payload


def lambda_handler(event, context):
    scanned_at = datetime.now(timezone.utc).isoformat()
    results = [run_check(name) for name in CHECK_FUNCTIONS]

    item = {
        "pk": "SCAN",
        "scanned_at": scanned_at,
        "overall": "PASS" if all(r["status"] == "PASS" for r in results) else "FAIL",
        "checks": {r["check"]: r for r in results},
    }
    table.put_item(Item=item)

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(item),
    }
