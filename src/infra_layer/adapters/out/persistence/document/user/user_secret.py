"""
UserSecret document — per-user credentials for server-side deployment.

Stores each user's:
  - api_key       : plaintext API key used for Bearer authentication (TEE environment assumed)
  - zerog_stream_id      : 0G KV stream ID (unique per user)
  - zerog_encryption_key : AES-256 key (hex-encoded, unique per user)
  - zerog_wallet_key     : EVM wallet private key (submitted by user at registration)
"""

from datetime import datetime
from typing import Optional

from pymongo import IndexModel, ASCENDING
from pydantic import Field

from core.oxm.mongo.document_base import DocumentBase


class UserSecret(DocumentBase):
    """Per-user secret document for server-side multi-user deployment."""

    user_id: str = Field(..., description="Unique user identifier (chosen by user)")
    api_key: str = Field(..., description="API key for Bearer authentication")
    zerog_stream_id: str = Field(..., description="0G KV stream ID (per-user)")
    zerog_encryption_key: str = Field(
        ..., description="AES-256 encryption key, hex-encoded (per-user)"
    )
    zerog_wallet_key: str = Field(
        ..., description="EVM wallet private key (submitted by user at registration)"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "user_secrets"
        indexes = [
            IndexModel([("user_id", ASCENDING)], unique=True),
        ]


__all__ = ["UserSecret"]
