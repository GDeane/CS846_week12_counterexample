from login_audit import count_failed_logins

events = [
    {"username": "alice", "ip": "1.1.1.1", "hour": 10, "success": True, "password": "a1"},
    {"username": "bob", "ip": "2.2.2.2", "hour": 10, "success": False, "password": "b2"},
    {"username": "carol", "ip": "3.3.3.3", "hour": 11, "success": False, "password": "c3"},
]

print("Failed logins:", count_failed_logins(events))
