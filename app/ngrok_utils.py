import json
import urllib.request


def get_ngrok_https_url() -> str:
    # ngrok exposes a local inspection API on port 4040. We use it so the app
    # can discover the current public tunnel URL automatically instead of making
    # you copy/paste the URL into code each time ngrok restarts.
    with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels") as response:
        data = json.loads(response.read().decode("utf-8"))

    # The API returns a list of active tunnels. We search for the HTTPS tunnel
    # because Telegram requires a public HTTPS webhook target.
    tunnels = data.get("tunnels", [])

    for tunnel in tunnels:
        public_url = tunnel.get("public_url", "")
        if public_url.startswith("https://"):
            return public_url

    # If no HTTPS tunnel exists, webhook registration cannot work, so we raise a
    # clear error instead of silently returning a bad URL.
    raise RuntimeError("No HTTPS ngrok tunnel found. Is ngrok running?")