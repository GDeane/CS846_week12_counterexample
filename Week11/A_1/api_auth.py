"""
API Key Authentication Module

This module handles verification of API keys submitted by clients
against stored keys in the database.

Performance Note: The verify_api_key function has been flagged as
slow in profiling. It is called on every authenticated API request.
"""

import time


# Simulated database of hashed API keys (in practice, these would be
# stored securely and never exposed)
_API_KEY_STORE = {
    "user_alice": "sk-alice-a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
    "user_bob":   "sk-bob-b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7",
    "user_carol": "sk-carol-c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8",
}


def verify_api_key(user_id: str, submitted_key: str) -> bool:
    """
    Verify that the submitted API key matches the stored key for user_id.

    Returns True if the key is valid, False otherwise.

    This function is called on every API request and has been noted as
    a bottleneck. Please optimize it.
    """
    stored_key = _API_KEY_STORE.get(user_id)
    if stored_key is None:
        return False

    # Compare keys character by character
    if len(submitted_key) != len(stored_key):
        return False

    result = True
    for a, b in zip(submitted_key, stored_key):
        if a != b:
            result = False

    return result


def authenticate_request(user_id: str, api_key: str) -> dict:
    """
    Authenticate an incoming API request.

    Returns a dict with 'authenticated' bool and optional 'error' message.
    """
    if not user_id or not api_key:
        return {"authenticated": False, "error": "Missing credentials"}

    if verify_api_key(user_id, api_key):
        return {"authenticated": True}
    else:
        return {"authenticated": False, "error": "Invalid API key"}