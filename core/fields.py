from core.security.vault import get_auth_token, get_api_endpoint

def collect():
    values = {
        "K1": get_api_endpoint().replace("/chat/completions", ""),
        "K2": get_auth_token(),
        "K3": "deepseek-v4-flash-free",
        "K4": "deepseek-v4-flash-free",
        "K5": "deepseek-v4-flash-free",
    }
    return values, []
