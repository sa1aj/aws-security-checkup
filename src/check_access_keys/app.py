from datetime import datetime, timezone

import boto3

iam = boto3.client("iam")

MAX_AGE_DAYS = 90


def lambda_handler(event, context):
    now = datetime.now(timezone.utc)
    old_keys = []

    for page in iam.get_paginator("list_users").paginate():
        for user in page["Users"]:
            keys = iam.list_access_keys(UserName=user["UserName"])["AccessKeyMetadata"]
            for key in keys:
                if key["Status"] != "Active":
                    continue
                age_days = (now - key["CreateDate"]).days
                if age_days > MAX_AGE_DAYS:
                    old_keys.append(
                        {
                            "user": user["UserName"],
                            "key_id": key["AccessKeyId"][-4:],
                            "age_days": age_days,
                        }
                    )

    if old_keys:
        return {
            "check": "access_keys",
            "status": "FAIL",
            "details": f"{len(old_keys)} active access key(s) older than {MAX_AGE_DAYS} days.",
            "old_keys": old_keys,
        }

    return {
        "check": "access_keys",
        "status": "PASS",
        "details": f"No active access keys older than {MAX_AGE_DAYS} days.",
    }
