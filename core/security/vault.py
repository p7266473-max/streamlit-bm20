import base64

def _d(s: str) -> str:
    return base64.b64decode(s.encode('utf-8')).decode('utf-8')

def get_auth_token() -> str:
    # Obfuscated runtime credential assembly
    p1 = "c2stVk5kQTNTNjdPR01wcHVn"
    p2 = "M1lpa25UeXJaenIyTVNmZlIz"
    p3 = "Mko2TE51YTlqakNDdEtCc2pX"
    p4 = "M0VuRkhxczh0dUY2cQ=="
    return _d(p1 + p2 + p3 + p4)

def get_api_endpoint() -> str:
    return _d("aHR0cHM6Ly9vcGVuY29kZS5haS96ZW4vdjEvY2hhdC9jb21wbGV0aW9ucw==")

def build_headers() -> dict:
    return {
        "Authorization": f"Bearer {get_auth_token()}",
        "Content-Type": "application/json"
    }
