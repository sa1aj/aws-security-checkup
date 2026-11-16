# AWS Security Checkup

A minimal serverless security checkup for an AWS account, built with AWS SAM.
It runs two read-only checks and stores the results in DynamoDB:

| Check | What it verifies | Pass condition |
|-------|------------------|----------------|
| `root_mfa` | The account root user has MFA enabled | `AccountMFAEnabled == 1` from `iam:GetAccountSummary` |
| `public_s3` | Every S3 bucket is fully blocked from public access | All four Block Public Access settings are on, at the account level or the bucket level |

## Architecture

```
                 ┌──────────────────────────┐
  POST /scan ──► │  ScanFunction            │──invoke──► CheckRootMfaFunction ──► IAM (read)
                 │  (orchestrator)          │──invoke──► CheckPublicS3Function ─► S3 (read)
                 │                          │──PutItem─► ResultsTable (DynamoDB)
                 └──────────────────────────┘
  GET /results ─► GetResultsFunction ──Query──► ResultsTable (DynamoDB)

  (both routes served by one API Gateway HTTP API)
```

- **API Gateway HTTP API** exposes `POST /scan` and `GET /results`, throttled to 1 request/second (burst 5).
- **ScanFunction** invokes each check Lambda synchronously, combines the results with a UTC timestamp and an overall PASS/FAIL, and writes one item to DynamoDB.
- **Check Lambdas** only read account configuration. They have no write permissions of any kind.
- **GetResultsFunction** queries the newest scan (`pk = "SCAN"`, sorted by `scanned_at` descending, limit 1).
- **ResultsTable** is an on-demand (pay-per-request) DynamoDB table. Partition key `pk`, sort key `scanned_at`.

### Least-privilege IAM

Each function has its own role. Apart from CloudWatch Logs, which every Lambda needs for logging, these are the only permissions:

| Function | Allowed actions | Resource |
|----------|-----------------|----------|
| CheckRootMfaFunction | `iam:GetAccountSummary` | `*` (action does not support resource scoping) |
| CheckPublicS3Function | `s3:ListAllMyBuckets`, `s3:GetAccountPublicAccessBlock` | `*` (no resource scoping available) |
| | `s3:GetBucketPublicAccessBlock` | `arn:aws:s3:::*` |
| ScanFunction | `lambda:InvokeFunction` | the two check functions only |
| | `dynamodb:PutItem` | the results table only |
| GetResultsFunction | `dynamodb:Query` | the results table only |

Nothing in this stack can modify IAM, S3, or any other account configuration. The only write is the scan Lambda's `PutItem` to its own results table.

## Deploy

Requires the [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html) and Python 3.13.

```bash
sam build
sam deploy            # uses samconfig.toml; edit the profile/region there
```

## Use

```bash
API=https://<api-id>.execute-api.us-east-1.amazonaws.com

curl -X POST $API/scan     # run the checks and store the results
curl $API/results          # fetch the latest stored results
```

Example response:

```json
{
  "pk": "SCAN",
  "scanned_at": "2026-11-16T18:05:00.123456+00:00",
  "overall": "FAIL",
  "checks": {
    "root_mfa": {"check": "root_mfa", "status": "PASS", "details": "Root user has MFA enabled."},
    "public_s3": {"check": "public_s3", "status": "FAIL", "details": "1 bucket(s) not fully blocked from public access.",
                  "exposed_buckets": [{"bucket": "my-site", "missing_settings": ["BlockPublicPolicy", "RestrictPublicBuckets"]}]}
  }
}
```

## Clean up

```bash
sam delete
```
