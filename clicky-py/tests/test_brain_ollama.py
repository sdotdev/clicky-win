"""Tests for the Ollama SSE parser and Anthropic→OpenAI message converter."""

from clicky.clients.brain_ollama import (
    _anthropic_to_openai_content,
    _to_openai_messages,
    parse_openai_sse_stream,
)


# ---------------------------------------------------------------------------
# parse_openai_sse_stream
# ---------------------------------------------------------------------------

def test_parse_single_delta() -> None:
    raw = b'data: {"choices": [{"delta": {"content": "Hello"}}]}\n'
    assert list(parse_openai_sse_stream(raw)) == ["Hello"]


def test_parse_multiple_deltas() -> None:
    raw = (
        b'data: {"choices": [{"delta": {"content": "Hi"}}]}\n'
        b'data: {"choices": [{"delta": {"content": " there"}}]}\n'
    )
    assert list(parse_openai_sse_stream(raw)) == ["Hi", " there"]


def test_parse_done_sentinel_ignored() -> None:
    raw = b"data: [DONE]\n"
    assert list(parse_openai_sse_stream(raw)) == []


def test_parse_empty_delta_skipped() -> None:
    raw = b'data: {"choices": [{"delta": {}}]}\n'
    assert list(parse_openai_sse_stream(raw)) == []


def test_parse_empty_bytes() -> None:
    assert list(parse_openai_sse_stream(b"")) == []


def test_parse_non_data_lines_ignored() -> None:
    raw = b'id: 1\ndata: {"choices": [{"delta": {"content": "hi"}}]}\n'
    assert list(parse_openai_sse_stream(raw)) == ["hi"]


# ---------------------------------------------------------------------------
# _anthropic_to_openai_content
# ---------------------------------------------------------------------------

def test_text_block_passthrough() -> None:
    blocks = [{"type": "text", "text": "hello"}]
    result = _anthropic_to_openai_content(blocks)
    assert result == blocks


def test_image_block_converted() -> None:
    blocks = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": "abc123",
            },
        }
    ]
    result = _anthropic_to_openai_content(blocks)
    assert result == [
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,abc123"}}
    ]


def test_mixed_blocks_converted() -> None:
    blocks = [
        {"type": "text", "text": "Monitor 1:"},
        {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": "xyz"},
        },
        {"type": "text", "text": "What is this?"},
    ]
    result = _anthropic_to_openai_content(blocks)
    assert result[0] == {"type": "text", "text": "Monitor 1:"}
    assert result[1]["type"] == "image_url"
    assert result[2] == {"type": "text", "text": "What is this?"}


# ---------------------------------------------------------------------------
# _to_openai_messages
# ---------------------------------------------------------------------------

def test_system_prepended() -> None:
    messages = [{"role": "user", "content": "hi"}]
    result = _to_openai_messages(messages, system="You are helpful.")
    assert result[0] == {"role": "system", "content": "You are helpful."}
    assert result[1] == {"role": "user", "content": "hi"}


def test_list_content_converted() -> None:
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "label"},
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": "AAA"},
                },
            ],
        }
    ]
    result = _to_openai_messages(messages, system="sys")
    user_msg = result[1]
    assert user_msg["role"] == "user"
    assert user_msg["content"][0] == {"type": "text", "text": "label"}
    assert user_msg["content"][1]["type"] == "image_url"
