import io
import json
from unittest.mock import MagicMock


def fake_invoke(results):
    """Return a fake lambda.invoke that answers with a preset result per function name."""

    def invoke(FunctionName):
        result = results[FunctionName]
        response = {"Payload": io.BytesIO(json.dumps(result).encode())}
        if "errorMessage" in result:
            response["FunctionError"] = "Unhandled"
        return response

    return invoke


def make_scan_app(lambda_module, results):
    app = lambda_module("scan")
    app.CHECK_FUNCTIONS = list(results)
    app.lambda_client = MagicMock()
    app.lambda_client.invoke.side_effect = fake_invoke(results)
    app.table = MagicMock()
    app.sns = MagicMock()
    return app


def test_scan_all_pass_saves_and_emails(lambda_module):
    app = make_scan_app(
        lambda_module,
        {
            "fn-a": {"check": "root_mfa", "status": "PASS", "details": "ok"},
            "fn-b": {"check": "cloudtrail", "status": "PASS", "details": "ok"},
        },
    )
    response = app.lambda_handler({}, None)
    body = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert body["overall"] == "PASS"
    app.table.put_item.assert_called_once()
    app.sns.publish.assert_called_once()
    assert "2/2 passed" in app.sns.publish.call_args.kwargs["Subject"]


def test_scan_one_failure_makes_overall_fail_and_adds_fix(lambda_module):
    app = make_scan_app(
        lambda_module,
        {
            "fn-a": {"check": "root_mfa", "status": "FAIL", "details": "no MFA"},
            "fn-b": {"check": "cloudtrail", "status": "PASS", "details": "ok"},
        },
    )
    body = json.loads(app.lambda_handler({}, None)["body"])
    message = app.sns.publish.call_args.kwargs["Message"]

    assert body["overall"] == "FAIL"
    assert "❌ Root user MFA: FAIL" in message
    assert "How to fix: Sign in as root" in message


def test_scan_crashed_check_is_reported_as_error_not_lost(lambda_module):
    app = make_scan_app(
        lambda_module,
        {
            "fn-ok": {"check": "root_mfa", "status": "PASS", "details": "ok"},
            "fn-broken": {"errorMessage": "AccessDenied"},
        },
    )
    body = json.loads(app.lambda_handler({}, None)["body"])

    assert body["overall"] == "FAIL"
    assert body["checks"]["fn-broken"]["status"] == "ERROR"
    app.table.put_item.assert_called_once()


def test_report_lists_buckets_and_keys(lambda_module):
    app = lambda_module("scan")
    subject, message = app.build_report(
        {
            "scanned_at": "2026-11-16T19:00:00+00:00",
            "checks": {
                "public_s3": {
                    "check": "public_s3",
                    "status": "FAIL",
                    "details": "1 bucket(s) not fully blocked from public access.",
                    "exposed_buckets": [{"bucket": "my-bucket", "missing_settings": ["BlockPublicAcls"]}],
                },
                "access_keys": {
                    "check": "access_keys",
                    "status": "FAIL",
                    "details": "1 active access key(s) older than 90 days.",
                    "old_keys": [{"user": "bot", "key_id": "1234", "age_days": 120}],
                },
            },
        }
    )
    assert subject == "AWS Security Checkup: 0/2 passed"
    assert "my-bucket (off: BlockPublicAcls)" in message
    assert "bot: key ending 1234 is 120 days old" in message


def test_get_results_returns_latest_or_404(lambda_module):
    app = lambda_module("get_results")
    app.table = MagicMock()

    app.table.query.return_value = {"Items": []}
    assert app.lambda_handler({}, None)["statusCode"] == 404

    app.table.query.return_value = {"Items": [{"pk": "SCAN", "overall": "PASS"}]}
    response = app.lambda_handler({}, None)
    assert response["statusCode"] == 200
    assert json.loads(response["body"])["overall"] == "PASS"
