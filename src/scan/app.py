import json
import os
from datetime import datetime, timezone

import boto3

lambda_client = boto3.client("lambda")
sns = boto3.client("sns")
table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])

CHECK_FUNCTIONS = [
    os.environ["ROOT_MFA_FUNCTION"],
    os.environ["PUBLIC_S3_FUNCTION"],
    os.environ["CLOUDTRAIL_FUNCTION"],
    os.environ["ACCESS_KEYS_FUNCTION"],
]

TITLES = {
    "root_mfa": "Root user MFA",
    "public_s3": "S3 public access",
    "cloudtrail": "CloudTrail logging",
    "access_keys": "Access key age",
}

FIXES = {
    "root_mfa": "Sign in as root > Security credentials > Assign MFA device.",
    "public_s3": "S3 console > Block Public Access settings for this account > turn all four on "
    "(check nothing needs to be public first).",
    "cloudtrail": "CloudTrail console > Create trail > apply to all regions.",
    "access_keys": "IAM console > Users > Security credentials > create a new key, "
    "switch your apps to it, then deactivate and delete the old one.",
}

ICONS = {"PASS": "✅", "FAIL": "❌", "ERROR": "⚠️"}


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


def build_report(item):
    checks = item["checks"].values()
    passed = sum(1 for c in checks if c["status"] == "PASS")
    lines = [
        f"AWS Security Checkup: {passed}/{len(checks)} checks passed",
        f"Scanned at {item['scanned_at']}",
        "",
    ]
    for c in checks:
        name = c["check"]
        lines.append(f"{ICONS.get(c['status'], '?')} {TITLES.get(name, name)}: {c['status']}")
        lines.append(f"   {c['details']}")
        for b in c.get("exposed_buckets", []):
            lines.append(f"   - {b['bucket']} (off: {', '.join(b['missing_settings'])})")
        for k in c.get("old_keys", []):
            lines.append(f"   - {k['user']}: key ending {k['key_id']} is {k['age_days']} days old")
        if c["status"] != "PASS" and name in FIXES:
            lines.append(f"   How to fix: {FIXES[name]}")
        lines.append("")
    subject = f"AWS Security Checkup: {passed}/{len(checks)} passed"
    return subject, "\n".join(lines)


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

    subject, message = build_report(item)
    sns.publish(TopicArn=os.environ["REPORT_TOPIC_ARN"], Subject=subject, Message=message)

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(item),
    }
