def count_failed_logins(events):
    failed_count = 0
    ip_counts = {}
    user_counts = {}
    hourly_counts = {}
    failed_records = []

    for event in events:
        username = event["username"]
        ip = event["ip"]
        hour = event["hour"]
        success = event["success"]
        password = event["password"]

        if not success:
            failed_count += 1
            failed_records.append({
                "username": username,
                "ip": ip,
                "password": password
            })

        if ip not in ip_counts:
            ip_counts[ip] = 0
        ip_counts[ip] += 1

        if username not in user_counts:
            user_counts[username] = 0
        user_counts[username] += 1

        if hour not in hourly_counts:
            hourly_counts[hour] = 0
        hourly_counts[hour] += 1

    return failed_count
