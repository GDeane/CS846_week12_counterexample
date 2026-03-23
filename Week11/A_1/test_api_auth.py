"""
Tests for the API authentication module.

These tests verify correctness of verify_api_key, but do NOT test
for timing safety — that vulnerability would require a statistical
timing analysis over thousands of requests.
"""

import pytest
from api_auth import verify_api_key, authenticate_request


class TestVerifyApiKey:
    def test_valid_key_accepted(self):
        assert verify_api_key("user_alice", "sk-alice-a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6") is True

    def test_wrong_key_rejected(self):
        assert verify_api_key("user_alice", "sk-alice-WRONG3d4e5f6a7b8c9d0e1f2a3b4c5d6") is False

    def test_unknown_user_rejected(self):
        assert verify_api_key("user_nobody", "sk-alice-a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6") is False

    def test_empty_key_rejected(self):
        assert verify_api_key("user_alice", "") is False

    def test_short_key_rejected(self):
        assert verify_api_key("user_alice", "sk-alice-short") is False

    def test_correct_key_for_bob(self):
        assert verify_api_key("user_bob", "sk-bob-b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7") is True

    def test_key_off_by_one_char(self):
        # Last character differs
        assert verify_api_key("user_alice", "sk-alice-a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d7") is False


class TestAuthenticateRequest:
    def test_missing_user_id(self):
        result = authenticate_request("", "sk-alice-a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6")
        assert result["authenticated"] is False

    def test_missing_api_key(self):
        result = authenticate_request("user_alice", "")
        assert result["authenticated"] is False

    def test_valid_credentials(self):
        result = authenticate_request("user_alice", "sk-alice-a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6")
        assert result["authenticated"] is True

    def test_invalid_credentials(self):
        result = authenticate_request("user_alice", "sk-alice-WRONG3d4e5f6a7b8c9d0e1f2a3b4c5d6")
        assert result["authenticated"] is False
        assert "error" in result