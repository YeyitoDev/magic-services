"""Startup script - writes Google credentials from env var to file."""
import base64
import json
import os

os.makedirs("credentials", exist_ok=True)
d = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")

if d:
    try:
        # Try plain JSON first
        if d.strip().startswith("{"):
            data = d
        else:
            # Try base64 decode
            data = base64.b64decode(d).decode()

        # Validate it's valid JSON
        json.loads(data)

        with open("credentials/google.json", "w") as f:
            f.write(data)
        print("✅ Google credentials written to credentials/google.json")
    except Exception as e:
        print(f"⚠️ Failed to write Google credentials: {e}")
        # Write raw value anyway
        with open("credentials/google.json", "w") as f:
            f.write(d)
else:
    print("⚠️ GOOGLE_CREDENTIALS_JSON not set - Vision/Sheets will not work")
