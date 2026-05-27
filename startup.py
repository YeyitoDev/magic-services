"""Startup script - writes Google credentials from env var to file."""
import os, base64

os.makedirs("credentials", exist_ok=True)
d = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")

if d:
    try:
        if d[0] != "{":
            d = base64.b64decode(d).decode()
        with open("credentials/google.json", "w") as f:
            f.write(d)
        print("✅ Google credentials written")
    except Exception as e:
        print(f"⚠️ Could not write Google credentials: {e}")
else:
    print("⚠️ GOOGLE_CREDENTIALS_JSON not set")
