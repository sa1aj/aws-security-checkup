from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from botocore.exceptions import ClientError


def no_config_error():
    return ClientError(
        {"Error": {"Code": "NoSuchPublicAccessBlockConfiguration"}}, "GetPublicAccessBlock"
    )


ALL_ON = {
    "BlockPublicAcls": True,
    "IgnorePublicAcls": True,
    "BlockPublicPolicy": True,
    "RestrictPublicBuckets": True,
}


# ---------- root MFA ----------

def test_root_mfa_pass(lambda_module):
    app = lambda_module("check_root_mfa")
    app.iam = MagicMock()
    app.iam.get_account_summary.return_value = {"SummaryMap": {"AccountMFAEnabled": 1}}
    assert app.lambda_handler({}, None)["status"] == "PASS"


def test_root_mfa_fail(lambda_module):
    app = lambda_module("check_root_mfa")
    app.iam = MagicMock()
    app.iam.get_account_summary.return_value = {"SummaryMap": {"AccountMFAEnabled": 0}}
    assert app.lambda_handler({}, None)["status"] == "FAIL"


# ---------- public S3 ----------

def make_s3_app(lambda_module, account_block, bucket_blocks):
    app = lambda_module("check_public_s3")
    app.sts = MagicMock()
    app.sts.get_caller_identity.return_value = {"Account": "123456789012"}
    app.s3control = MagicMock()
    if account_block is None:
        app.s3control.get_public_access_block.side_effect = no_config_error()
    else:
        app.s3control.get_public_access_block.return_value = {
            "PublicAccessBlockConfiguration": account_block
        }
    app.s3 = MagicMock()
    app.s3.get_paginator.return_value.paginate.return_value = [
        {"Buckets": [{"Name": name} for name in bucket_blocks]}
    ]

    def bucket_block(Bucket):
        config = bucket_blocks[Bucket]
        if config is None:
            raise no_config_error()
        return {"PublicAccessBlockConfiguration": config}

    app.s3.get_public_access_block.side_effect = bucket_block
    return app


def test_s3_pass_when_every_bucket_blocked(lambda_module):
    app = make_s3_app(lambda_module, None, {"a": ALL_ON, "b": ALL_ON})
    assert app.lambda_handler({}, None)["status"] == "PASS"


def test_s3_pass_when_account_level_blocks_everything(lambda_module):
    app = make_s3_app(lambda_module, ALL_ON, {"a": None})
    assert app.lambda_handler({}, None)["status"] == "PASS"


def test_s3_fail_lists_exposed_bucket_and_missing_settings(lambda_module):
    partial = {**ALL_ON, "BlockPublicPolicy": False}
    app = make_s3_app(lambda_module, None, {"safe": ALL_ON, "open": None, "half": partial})
    result = app.lambda_handler({}, None)
    assert result["status"] == "FAIL"
    exposed = {b["bucket"]: b["missing_settings"] for b in result["exposed_buckets"]}
    assert set(exposed) == {"open", "half"}
    assert len(exposed["open"]) == 4
    assert exposed["half"] == ["BlockPublicPolicy"]


# ---------- CloudTrail ----------

def make_cloudtrail_app(lambda_module, monkeypatch, trails, logging):
    app = lambda_module("check_cloudtrail")
    app.cloudtrail = MagicMock()
    app.cloudtrail.describe_trails.return_value = {"trailList": trails}
    regional = MagicMock()
    regional.get_trail_status.return_value = {"IsLogging": logging}
    monkeypatch.setattr(app.boto3, "client", lambda *a, **k: regional)
    return app


def trail(name, multi_region):
    return {
        "Name": name,
        "TrailARN": f"arn:aws:cloudtrail:us-east-1:123456789012:trail/{name}",
        "HomeRegion": "us-east-1",
        "IsMultiRegionTrail": multi_region,
    }


def test_cloudtrail_pass(lambda_module, monkeypatch):
    app = make_cloudtrail_app(lambda_module, monkeypatch, [trail("main", True)], True)
    assert app.lambda_handler({}, None)["status"] == "PASS"


def test_cloudtrail_fail_when_trail_stopped(lambda_module, monkeypatch):
    app = make_cloudtrail_app(lambda_module, monkeypatch, [trail("main", True)], False)
    assert app.lambda_handler({}, None)["status"] == "FAIL"


def test_cloudtrail_fail_when_only_single_region(lambda_module, monkeypatch):
    app = make_cloudtrail_app(lambda_module, monkeypatch, [trail("local", False)], True)
    assert app.lambda_handler({}, None)["status"] == "FAIL"


def test_cloudtrail_fail_when_no_trails(lambda_module, monkeypatch):
    app = make_cloudtrail_app(lambda_module, monkeypatch, [], True)
    assert app.lambda_handler({}, None)["status"] == "FAIL"


# ---------- access key age ----------

def make_keys_app(lambda_module, keys_by_user):
    app = lambda_module("check_access_keys")
    app.iam = MagicMock()
    app.iam.get_paginator.return_value.paginate.return_value = [
        {"Users": [{"UserName": u} for u in keys_by_user]}
    ]
    app.iam.list_access_keys.side_effect = lambda UserName: {
        "AccessKeyMetadata": keys_by_user[UserName]
    }
    return app


def key(days_old, status="Active", key_id="AKIAEXAMPLEKEY1234"):
    return {
        "AccessKeyId": key_id,
        "Status": status,
        "CreateDate": datetime.now(timezone.utc) - timedelta(days=days_old),
    }


def test_access_keys_pass_when_keys_are_fresh(lambda_module):
    app = make_keys_app(lambda_module, {"alice": [key(10)], "bob": []})
    assert app.lambda_handler({}, None)["status"] == "PASS"


def test_access_keys_ignore_inactive_old_keys(lambda_module):
    app = make_keys_app(lambda_module, {"alice": [key(400, status="Inactive")]})
    assert app.lambda_handler({}, None)["status"] == "PASS"


def test_access_keys_fail_and_hide_most_of_key_id(lambda_module):
    app = make_keys_app(lambda_module, {"alice": [key(10)], "bot": [key(120)]})
    result = app.lambda_handler({}, None)
    assert result["status"] == "FAIL"
    assert result["old_keys"] == [{"user": "bot", "key_id": "1234", "age_days": 120}]
