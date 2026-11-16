import boto3

iam = boto3.client("iam")


def lambda_handler(event, context):
    summary = iam.get_account_summary()["SummaryMap"]
    mfa_enabled = summary.get("AccountMFAEnabled", 0) == 1

    return {
        "check": "root_mfa",
        "status": "PASS" if mfa_enabled else "FAIL",
        "details": "Root user has MFA enabled."
        if mfa_enabled
        else "Root user does NOT have MFA enabled.",
    }
