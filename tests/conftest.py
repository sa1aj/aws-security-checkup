import importlib.util
import os
from pathlib import Path

import pytest

# Fake settings so the Lambda modules can be imported without a real AWS account.
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
for name in [
    "TABLE_NAME",
    "REPORT_TOPIC_ARN",
    "ROOT_MFA_FUNCTION",
    "PUBLIC_S3_FUNCTION",
    "CLOUDTRAIL_FUNCTION",
    "ACCESS_KEYS_FUNCTION",
]:
    os.environ.setdefault(name, f"test-{name.lower()}")

SRC = Path(__file__).resolve().parent.parent / "src"


def load_lambda(folder):
    """Import src/<folder>/app.py under a unique name (every Lambda file is called app.py)."""
    spec = importlib.util.spec_from_file_location(f"{folder}_app", SRC / folder / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def lambda_module():
    return load_lambda
