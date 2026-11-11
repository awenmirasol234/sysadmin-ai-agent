"""Unit tests for the multi-provider LLM Factory."""

import pytest
from backend.agent.llm import get_chat_model
from backend.config import Settings


def test_instantiate_openai():
    model = get_chat_model(provider="openai", model="gpt-4o-mini", api_key="sk-test-key")
    assert model.__class__.__name__ == "ChatOpenAI"
    assert model.model_name == "gpt-4o-mini" or getattr(model, "model", None) == "gpt-4o-mini"


def test_instantiate_anthropic():
    model = get_chat_model(provider="anthropic", model="claude-3-5-haiku-20241022", api_key="sk-ant-test")
    assert model.__class__.__name__ == "ChatAnthropic"


def test_instantiate_google():
    model = get_chat_model(provider="google", model="gemini-2.5-flash", api_key="AIzaSyTest")
    assert model.__class__.__name__ == "ChatGoogleGenerativeAI"
    assert model.model == "gemini-2.5-flash"


def test_instantiate_ollama():
    model = get_chat_model(provider="ollama", model="llama3.1:8b", base_url="http://localhost:11434")
    assert model.__class__.__name__ == "ChatOllama"
    assert model.model == "llama3.1:8b"


def test_instantiate_openai_compatible():
    model = get_chat_model(
        provider="openai-compatible",
        model="deepseek-chat",
        api_key="sk-test",
        base_url="https://api.deepseek.com",
    )
    assert model.__class__.__name__ == "ChatOpenAI"


def test_unsupported_provider():
    with pytest.raises(ValueError) as exc_info:
        get_chat_model(provider="unknown-provider-xyz")
    assert "Unsupported LLM provider" in str(exc_info.value)


def test_provider_specific_api_key_isolation():
    cfg = Settings(
        _env_file=None,
        LLM_PROVIDER="openai",
        LLM_API_KEY="sk-primary-openai",
        ANTHROPIC_API_KEY="sk-ant-specific",
    )
    assert cfg.get_api_key() == "sk-primary-openai"
    assert cfg.get_api_key("anthropic") == "sk-ant-specific"
    assert cfg.get_api_key("google") is None
