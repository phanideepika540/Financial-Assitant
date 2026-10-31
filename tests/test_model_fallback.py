from types import SimpleNamespace

from langchain_core.runnables import RunnableLambda

from src.web_app import api


def test_gemini_is_fallback_for_chat_model_when_key_is_configured(monkeypatch):
    settings = SimpleNamespace(model="gpt-4o-mini", temperature=0.2)
    observed = {}

    def fail_openai(_):
        raise RuntimeError("OpenAI unavailable")

    primary = RunnableLambda(fail_openai)

    def create_openai(**kwargs):
        observed["openai"] = kwargs
        return primary

    def create_gemini(**kwargs):
        observed["gemini"] = kwargs
        return RunnableLambda(lambda _: "Gemini response")

    import langchain_openai
    import langchain_google_genai

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", create_openai)
    monkeypatch.setattr(langchain_google_genai, "ChatGoogleGenerativeAI", create_gemini)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test-model")

    chat_model = api._build_chat_model(settings)

    assert chat_model.invoke("test question") == "Gemini response"
    assert observed["openai"]["model"] == "gpt-4o-mini"
    assert observed["gemini"]["model"] == "gemini-test-model"
    assert observed["gemini"]["api_key"] == "test-key"


def test_chat_model_keeps_openai_only_without_gemini_key(monkeypatch):
    settings = SimpleNamespace(model="gpt-4o-mini", temperature=0.2)
    primary = RunnableLambda(lambda _: "OpenAI response")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    import langchain_openai

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", lambda **_: primary)

    chat_model = api._build_chat_model(settings)

    assert chat_model is primary
    assert chat_model.invoke("test question") == "OpenAI response"
