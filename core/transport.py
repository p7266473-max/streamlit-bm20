import importlib.resources  # noqa: F401  (py3.14 shim for smolagents)

from smolagents import OpenAIServerModel


def model(values, key, max_tokens):
    return OpenAIServerModel(
        model_id=values[key],
        api_base=values["K1"],
        api_key=values["K2"],
        max_tokens=max_tokens,
    )
