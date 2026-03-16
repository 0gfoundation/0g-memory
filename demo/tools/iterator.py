#!/usr/bin/env python3

import os
import sys
import time

from zg_storage import configure_logging
from zg_storage.kv import KvClient

configure_logging(
    "info,zg_storage=info,web3=warning,urllib3=warning,httpx=warning,httpcore=warning"
)

KV_URL = "http://127.0.0.1:6789"

# Read STREAM_ID from .0g_secrets at the project root (two levels up from demo/tools/)
_secrets_path = os.path.join(os.path.dirname(__file__), "..", "..", ".0g_secrets")
_secrets_path = os.path.abspath(_secrets_path)
STREAM_ID = None
with open(_secrets_path) as _f:
    for _line in _f:
        _line = _line.strip()
        if _line.startswith("ZEROG_STREAM_ID="):
            STREAM_ID = _line.split("=", 1)[1]
            break
if not STREAM_ID:
    raise RuntimeError(f"ZEROG_STREAM_ID not found in {_secrets_path}")

kv_client = KvClient(KV_URL)
iter = kv_client.new_iterator(STREAM_ID)

print("begin to end:")
count = 0
iter.seek_to_first()
while iter.valid():
    count += 1
    print(f"{count},  {iter.key}")
    if count % 10 == 0:
        print(f"{iter.key}: {iter.data}")
    iter.next()

"""
print("end to begin:")
iter.seek_to_last()
while iter.valid():
    print(f"{iter.key}: {iter.data}")
    iter.prev()
    time.sleep(1)
"""

"""
key0 = b"TESTKEY"
key1 = b"TESTKEY2"

print(f"seek before {key1}")
iter.seek_before(key1)
if iter.valid():
    print(f"{iter.key}: {iter.data}")

print(f"seek after {key0}")
iter.seek_after(key0)
if iter.valid():
    print(f"{iter.key}: {iter.data}")
"""
