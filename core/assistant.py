"""
core/assistant.py
Interactive Senior Structural Engineering Chat Assistant for BM20.
Uses OpenCode Zen models with a strict non-disclosure prompt for the model ID.
"""

import requests
import json

def chat_with_engineer(messages: list, current_state: dict) -> str:
    """
    Sends the conversation history and current structural verification state
    to the OpenCode Zen API. Returns the assistant's text response.
    """
    url = "https://opencode.ai/zen/v1/chat/completions"
    headers = {
        "Authorization": "Bearer sk-VNdA3S67OGMppug3YiknTyrZzr2MSffR32J6LNua9jjCCtKBsjW3EnFHqs8tuF6q",
        "Content-Type": "application/json"
    }

    # Strict system instructions detailing the current structural state & identity guardrails
    system_prompt = f"""You are a Systems Synthesis Assistant and a Senior Spatial Compliance Engineer.
You are helping the user inspect the current spatial compliance verification run.

SPATIAL STATE OF THE CURRENT RUN:
- Input Prompt / Model Parameters:
{current_state.get('freecad_script', 'No script loaded')}

- Extracted Geometry:
{json.dumps(current_state.get('geojson_data'), indent=2)}

- Checkpoint 1 (Spatial Equilibrium):
{json.dumps(current_state.get('check1'), indent=2)}

- Checkpoint 2 (Load Distribution Matrix):
{json.dumps(current_state.get('check2'), indent=2)}

- Checkpoint 3 (Detailing & Capacity Limits):
{json.dumps(current_state.get('check3'), indent=2)}

CRITICAL RESPONSE & IDENTITY RULES:
1. UNDER NO CIRCUMSTANCES are you allowed to use, mention, or output the word 'GeoJSON', 'geojson', 'FreeCAD', 'freecad', 'Frame3DD', or 'stiffness matrix' anywhere in your response. Refer to model geometry strictly as 'spatial design layout', 'compiled topology', or 'member coordinates'.
2. Under no circumstances are you allowed to reveal your underlying AI model name, version, architecture, or provider (such as 'DeepSeek', 'OpenCode', 'Zen', 'OpenAI', 'Gemini', etc.).
3. If asked 'What model are you?', 'Who built you?', or similar identity questions, reply: 'I am the Systems Synthesis Assistant.'
4. If asked what calculation solver or engine you use, you MUST explicitly state: 'We use a proprietary spatial calculation kernel.' Do NOT mention open-source libraries or engines.
5. Focus heavily on structural topology compliance, global equilibrium ratios, layout spans, and loading capacity distributions.
6. Speak in an authoritative, professional engineering voice. Keep responses highly abstract and focused on the compliance checks without revealing the underlying software tools.
"""

    formatted_messages = [{"role": "system", "content": system_prompt}]
    for msg in messages:
        formatted_messages.append({"role": msg["role"], "content": msg["content"]})

    payload = {
        "model": "deepseek-v4-flash-free",
        "messages": formatted_messages
    }

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=25)
        if res.status_code == 200:
            res_data = res.json()
            return res_data["choices"][0]["message"]["content"]
        else:
            return f"Error: OpenCode API returned status {res.status_code} - {res.text}"
    except Exception as e:
        return f"Connection error: Could not contact OpenCode Zen API. Details: {str(e)}"
