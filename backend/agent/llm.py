"""Multi-provider LLM Factory for SysAdmin AI Agent."""

import os
from typing import Any, Dict, Optional
from langchain_core.language_models.chat_models import BaseChatModel

from backend.config import settings


def get_chat_model(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    temperature: Optional[float] = None,
) -> BaseChatModel:
    """Instantiates and returns a ChatModel for any supported provider."""
    resolved_provider = (provider or settings.LLM_PROVIDER).strip().lower()
    resolved_model = model or settings.LLM_MODEL
    resolved_temp = temperature if temperature is not None else settings.LLM_TEMPERATURE
    resolved_key = api_key or settings.get_api_key()
    resolved_base_url = base_url or settings.LLM_BASE_URL

    if resolved_provider in ("openai", "openai-compatible", "groq", "deepseek", "vllm", "openrouter"):
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=resolved_model,
            api_key=resolved_key or "sk-dummy-key-for-local",
            base_url=resolved_base_url,
            temperature=resolved_temp,
        )

    elif resolved_provider in ("anthropic", "claude"):
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=resolved_model,
            api_key=resolved_key,
            temperature=resolved_temp,
        )

    elif resolved_provider in ("google", "gemini"):
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=resolved_model,
            google_api_key=resolved_key or settings.GOOGLE_API_KEY or settings.GEMINI_API_KEY,
            temperature=resolved_temp,
        )

    elif resolved_provider == "ollama":
        try:
            from langchain_ollama import ChatOllama
        except ImportError:
            from langchain_community.chat_models import ChatOllama
        url = resolved_base_url or "http://localhost:11434"
        return ChatOllama(
            model=resolved_model,
            base_url=url,
            temperature=resolved_temp,
        )

    else:
        raise ValueError(
            f"Unsupported LLM provider: '{resolved_provider}'. "
            f"Supported providers: openai, anthropic, google, ollama, openai-compatible"
        )


def probe_model_connection(chat_model: BaseChatModel) -> Dict[str, Any]:
    """Tests the model connection and basic invocation."""
    try:
        from langchain_core.messages import HumanMessage
        response = chat_model.invoke([HumanMessage(content="Respond with 'PONG' only.")])
        text = response.content.strip()
        return {
            "success": True,
            "provider": getattr(chat_model, "_llm_type", "unknown"),
            "model": getattr(chat_model, "model_name", getattr(chat_model, "model", "unknown")),
            "response": text,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
