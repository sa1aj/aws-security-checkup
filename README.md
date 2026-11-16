# AWS Security Checkup

A read-only serverless security checkup for your AWS account. It runs every day and
**emails you a PASS/FAIL report with how-to-fix steps**. You don't need a terminal to use it.

```
AWS Security Checkup: 2/3 checks passed
Scanned at 2026-11-16T18:59:45+00:00

✅ Root user MFA: PASS
   Root user has MFA enabled.

❌ S3 public access: FAIL
   1 bucket(s) not fully blocked from public access.
   - my-old-bucket (off: BlockPublicAcls, IgnorePublicAcls, BlockPublicPolicy, RestrictPublicBuckets)
   How to fix: S3 console > Block Public Access settings for this account > turn all four on (check nothing needs to be public first).

✅ CloudTrail logging: PASS
   Multi-region CloudTrail is logging: main-trail.
```

| Check | What it verifies | Pass condition |
|-------|------------------|----------------|
| `root_mfa` | The account root user has MFA enabled | `AccountMFAEnabled == 1` from `iam:GetAccountSummary` |
| `public_s3` | Every S3 bucket is fully blocked from public access | All four Block Public Access settings are on, at the account level or the bucket level |
| `cloudtrail` | API activity is being recorded | At least one multi-region CloudTrail trail is logging |

## Install in your account (no terminal)

**[👉 Install from the AWS Serverless Application Repository](https://console.aws.amazon.com/lambda/home?region=us-east-1#/create/app?applicationId=arn:aws:serverlessrepo:us-east-1:690998797525:applications/aws-security-checkup)**
([public app page](https://serverlessrepo.aws.amazon.com/applications/us-east-1/690998797525/aws-security-checkup))

1. Open the app in the **AWS Serverless Application Repository** (link above) while signed in to your AWS console.
2. Enter your email in **NotificationEmail**.
3. Tick **"I acknowledge that this app creates custom IAM roles"** and click **Deploy**.
4. Click the link in the **"AWS Notification - Subscription Confirmation"** email from AWS.

You'll get a report every day. The checkup only scans the account you install it in.
Nobody else, including the author, gets access to your account or your results.
To uninstall, delete the `serverlessrepo-aws-security-checkup` stack in the CloudFormation console.

## Architecture

```
  EventBridge schedule ─┐
     (daily)            │      ┌──────────────────┐
                        ├────► │  ScanFunction    │──invoke──► CheckRootMfaFunction ───► IAM (read)
  POST /scan ───────────┘      │  (orchestrator)  │──invoke──► CheckPublicS3Function ──► S3 (read)
  (IAM-authorized)             │                  │──invoke──► CheckCloudTrailFunction ► CloudTrail (read)
                               │                  │──PutItem─► ResultsTable (DynamoDB)
                               └──────────────────┘──Publish─► ReportTopic (SNS) ──► your email

  GET /results ──► GetResultsFunction ──Query──► ResultsTable (DynamoDB)
  (IAM-authorized)
```

- **EventBridge schedule** triggers a scan once a day (configurable with `ScanSchedule`).
- **ScanFunction** invokes each check Lambda, combines the results with a UTC timestamp and an overall PASS/FAIL, writes one item to DynamoDB, then publishes a readable report to SNS.
- **Check Lambdas** only read account configuration. They have no write permissions of any kind.
- **ReportTopic (SNS)** emails the report to the address you entered, after you confirm the subscription.
- **API Gateway HTTP API** exposes `POST /scan` and `GET /results` for on-demand use. It accepts only IAM-signed requests and is throttled to 1 request/second (burst 5).
- **ResultsTable** is an on-demand (pay-per-request) DynamoDB table holding scan history (`pk = "SCAN"`, sort key `scanned_at`).

### Least-privilege IAM

Each function has its own role. Apart from CloudWatch Logs, which every Lambda needs for logging, these are the only permissions:

| Function | Allowed actions | Resource |
|----------|-----------------|----------|
| CheckRootMfaFunction | `iam:GetAccountSummary` | `*` (action does not support resource scoping) |
| CheckPublicS3Function | `s3:ListAllMyBuckets`, `s3:GetAccountPublicAccessBlock` | `*` (no resource scoping available) |
| | `s3:GetBucketPublicAccessBlock` | `arn:aws:s3:::*` |
| CheckCloudTrailFunction | `cloudtrail:DescribeTrails` | `*` (no resource scoping available) |
| | `cloudtrail:GetTrailStatus` | trails only (`arn:aws:cloudtrail:*:*:trail/*`) |
| ScanFunction | `lambda:InvokeFunction` | the three check functions only |
| | `dynamodb:PutItem` | the results table only |
| | `sns:Publish` | the report topic only |
| GetResultsFunction | `dynamodb:Query` | the results table only |

Nothing in this stack can modify IAM, S3, CloudTrail or any other account configuration.
The only writes are to the stack's own results table and report topic.

## Deploy from source (developers)

Requires the [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html) and Python 3.13.

```bash
git clone https://github.com/sa1aj/aws-security-checkup
cd aws-security-checkup
sam build
sam deploy --profile <your-profile> --parameter-overrides NotificationEmail=you@example.com
```

`sam deploy` shows a changeset (including the IAM roles listed above) and asks you to
confirm before anything is created.

### On-demand API

The API URL is in the stack outputs as `ApiUrl`. Unsigned requests get `403 Forbidden`,
so your results are not public. Sign requests with [awscurl](https://github.com/okigan/awscurl):

```bash
python3 -m venv .venv && .venv/bin/pip install awscurl
API=https://<api-id>.execute-api.us-east-1.amazonaws.com
eval "$(aws configure export-credentials --profile <your-profile> --format env)"

.venv/bin/awscurl --service execute-api --region us-east-1 -X POST $API/scan   # run now (also emails the report)
.venv/bin/awscurl --service execute-api --region us-east-1 $API/results        # latest stored results
```

### Clean up

```bash
sam delete --profile <your-profile>
```

## License

MIT
