import logging

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

CHUNK_SIZE = 4000

SYSTEM_PROMPT = """Отвечай ТОЛЬКО на русском языке.

Ты — профессиональный секретарь. По транскрипту совещания составь структурированный протокол на русском языке.

Протокол должен содержать строго следующие разделы:

## 1. Дата и участники
Укажи дату совещания и список участников (если упомянуты в транскрипте, иначе напиши «не указано»).

## 2. Повестка дня
Перечисли основные темы, которые обсуждались.

## 3. Ключевые обсуждения
Краткое резюме по каждой теме повестки.

## 4. Принятые решения
Пронумерованный список всех принятых решений.

## 5. Ответственные и сроки
Таблица в формате Markdown:
| Задача | Ответственный | Срок |
|--------|--------------|------|

## 6. Следующие шаги
Перечисли конкретные действия, которые необходимо предпринять после совещания.

Будь точен и конкретен. Не добавляй информацию, которой нет в транскрипте."""

CHUNK_SUMMARY_PROMPT = """Отвечай ТОЛЬКО на русском языке.

Ты — помощник секретаря. Перед тобой фрагмент транскрипта совещания.
Извлеки из него краткое резюме: участники (если упомянуты), темы, решения, поручения и сроки.
Пиши только то, что есть в тексте. Ответ на русском языке, не более 600 слов."""

COMBINE_PROMPT = """Отвечай ТОЛЬКО на русском языке.

Ниже приведены частичные резюме отдельных фрагментов одного совещания.
Объедини их и составь итоговый протокол согласно инструкции."""


def _split_transcript(transcript: str, chunk_size: int = CHUNK_SIZE) -> list[str]:
    """Split transcript into chunks at word boundaries."""
    if len(transcript) <= chunk_size:
        return [transcript]

    chunks: list[str] = []
    start = 0
    while start < len(transcript):
        end = start + chunk_size
        if end >= len(transcript):
            chunks.append(transcript[start:])
            break
        # Walk back to the nearest space to avoid splitting mid-word
        boundary = transcript.rfind(" ", start, end)
        if boundary <= start:
            boundary = end  # No space found; hard-cut
        chunks.append(transcript[start:boundary])
        start = boundary + 1
    return chunks


def _chat(client: anthropic.Anthropic, system: str, user: str) -> str:
    message = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return message.content[0].text


def generate_protocol(transcript: str) -> str:
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    logger.info(
        "Generating protocol via Anthropic/%s, transcript length: %d chars",
        settings.anthropic_model,
        len(transcript),
    )

    chunks = _split_transcript(transcript)

    if len(chunks) == 1:
        protocol_text = _chat(
            client,
            SYSTEM_PROMPT,
            f"Транскрипт совещания:\n\n{transcript}",
        )
    else:
        logger.info("Transcript split into %d chunks of ~%d chars each", len(chunks), CHUNK_SIZE)
        partial_summaries: list[str] = []
        for i, chunk in enumerate(chunks, 1):
            logger.info("Summarising chunk %d/%d (%d chars)...", i, len(chunks), len(chunk))
            summary = _chat(
                client,
                CHUNK_SUMMARY_PROMPT,
                f"Фрагмент {i}/{len(chunks)} транскрипта:\n\n{chunk}",
            )
            partial_summaries.append(f"### Фрагмент {i}\n{summary}")

        combined = "\n\n".join(partial_summaries)
        logger.info("Combining %d partial summaries into final protocol...", len(partial_summaries))
        protocol_text = _chat(
            client,
            SYSTEM_PROMPT,
            f"{COMBINE_PROMPT}\n\n{combined}",
        )

    logger.info("Protocol generated: %d characters", len(protocol_text))
    return protocol_text
