import boto3
from botocore.exceptions import ClientError

s3 = boto3.client("s3")
s3control = boto3.client("s3control")
sts = boto3.client("sts")

SETTINGS = [
    "BlockPublicAcls",
    "IgnorePublicAcls",
    "BlockPublicPolicy",
    "RestrictPublicBuckets",
]


def get_account_block():
    account_id = sts.get_caller_identity()["Account"]
    try:
        config = s3control.get_public_access_block(AccountId=account_id)
        return config["PublicAccessBlockConfiguration"]
    except ClientError as err:
        if err.response["Error"]["Code"] == "NoSuchPublicAccessBlockConfiguration":
            return {}
        raise


def get_bucket_block(bucket):
    try:
        config = s3.get_public_access_block(Bucket=bucket)
        return config["PublicAccessBlockConfiguration"]
    except ClientError as err:
        if err.response["Error"]["Code"] == "NoSuchPublicAccessBlockConfiguration":
            return {}
        raise


def lambda_handler(event, context):
    account_block = get_account_block()
    exposed = []

    paginator = s3.get_paginator("list_buckets")
    for page in paginator.paginate():
        for bucket in page["Buckets"]:
            name = bucket["Name"]
            bucket_block = get_bucket_block(name)
            missing = [
                s
                for s in SETTINGS
                if not (account_block.get(s) or bucket_block.get(s))
            ]
            if missing:
                exposed.append({"bucket": name, "missing_settings": missing})

    return {
        "check": "public_s3",
        "status": "FAIL" if exposed else "PASS",
        "details": f"{len(exposed)} bucket(s) not fully blocked from public access."
        if exposed
        else "All buckets are fully blocked from public access.",
        "exposed_buckets": exposed,
    }
