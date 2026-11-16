import boto3
from botocore.exceptions import ClientError

cloudtrail = boto3.client("cloudtrail")


def is_logging(trail):
    regional_client = boto3.client("cloudtrail", region_name=trail["HomeRegion"])
    try:
        status = regional_client.get_trail_status(Name=trail["TrailARN"])
        return status.get("IsLogging", False)
    except ClientError:
        return False


def lambda_handler(event, context):
    trails = cloudtrail.describe_trails(includeShadowTrails=True)["trailList"]
    multi_region = [t for t in trails if t.get("IsMultiRegionTrail")]
    active = [t["Name"] for t in multi_region if is_logging(t)]

    if active:
        return {
            "check": "cloudtrail",
            "status": "PASS",
            "details": f"Multi-region CloudTrail is logging: {', '.join(active)}.",
        }

    return {
        "check": "cloudtrail",
        "status": "FAIL",
        "details": "No multi-region CloudTrail trail is logging. "
        "API activity in this account is not being recorded.",
    }
