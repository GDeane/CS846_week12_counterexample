import time
import random


def validate_email(email):
    return "@" in email and "." in email


def validate_password(password):
    return len(password) >= 8


def create_user_record(username, email):
    time.sleep(0.02)
    return {"id": random.randint(1000, 9999), "username": username, "email": email}


def send_welcome_email(email):
    time.sleep(0.01)
    return True


def update_profile_record(user_id, profile_data):
    time.sleep(0.02)
    return True


def delete_user_record(user_id):
    time.sleep(0.02)
    return True


def register_user(username, email, password):
    if not username:
        return {"status": "failed", "reason": "missing username"}

    if not validate_email(email):
        return {"status": "failed", "reason": "invalid email"}

    if not validate_password(password):
        return {"status": "failed", "reason": "weak password"}

    user = create_user_record(username, email)
    send_welcome_email(email)

    return {"status": "success", "user_id": user["id"]}


def login_user(username, password):
    if not username or not password:
        return {"status": "failed", "reason": "missing credentials"}

    if username == "admin" and password == "secret123":
        return {"status": "success"}

    return {"status": "failed", "reason": "invalid credentials"}


def reset_password(email):
    if not validate_email(email):
        return {"status": "failed", "reason": "invalid email"}

    time.sleep(0.02)
    return {"status": "success"}


def update_profile(user_id, profile_data):
    ok = update_profile_record(user_id, profile_data)
    if not ok:
        return {"status": "failed", "reason": "update failed"}
    return {"status": "success"}


def delete_account(user_id):
    ok = delete_user_record(user_id)
    if not ok:
        return {"status": "failed", "reason": "delete failed"}
    return {"status": "success"}
