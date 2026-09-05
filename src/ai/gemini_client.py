"""
RetailIQ Gemini Client
Integrates Google Gemini (gemini-2.5-flash / gemini-3.7-flash and gemini-embedding-001)
via the official google-genai SDK with automatic deterministic fallback.
"""

import os
import json
from typing import Dict, Any, List, Optional
from src.config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_EMBEDDING_MODEL
from src.utils.logging_config import logger
from src.ai.prompts import SYSTEM_INSTRUCTION, INTENT_EXTRACTION_PROMPT, GROUNDED_SYNTHESIS_PROMPT
from src.ai.intent_router import parse_deterministic_intent
from src.utils.validation import validate_intent_payload

_client = None

def get_gemini_client():
    """Initializes and returns the official google-genai Client if API key is present."""
    global _client
    if _client is not None:
        return _client
    
    api_key = os.getenv("GEMINI_API_KEY", GEMINI_API_KEY).strip()
    if not api_key:
        return None

    try:
        from google import genai
        _client = genai.Client(api_key=api_key)
        logger.info("Initialized Google Gemini client successfully.")
        return _client
    except Exception as e:
        logger.warning(f"Failed to initialize google-genai client: {e}")
        return None

def extract_intent_with_gemini(query: str) -> Dict[str, Any]:
    """
    Extracts intent and entities from user query using Gemini.
    Gracefully falls back to deterministic rule parser if Gemini is unavailable.
    """
    client = get_gemini_client()
    if not client:
        logger.info("GEMINI_API_KEY not configured. Using deterministic intent parser.")
        return parse_deterministic_intent(query)

    try:
        prompt = INTENT_EXTRACTION_PROMPT.format(query=query)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={
                "system_instruction": SYSTEM_INSTRUCTION,
                "response_mime_type": "application/json",
                "temperature": 0.0
            }
        )
        if response and response.text:
            parsed = json.loads(response.text)
            validated = validate_intent_payload(parsed)
            # Retain entities extracted
            if "entities" in parsed and isinstance(parsed["entities"], dict):
                # Augment with store_id if store name matches
                st_name = str(parsed["entities"].get("store") or "").lower()
                from src.ai.intent_router import STORE_MAP
                for s_key, s_val in STORE_MAP.items():
                    if s_key in st_name:
                        validated["entities"]["store_id"] = s_val
                        break
                validated["entities"]["product"] = parsed["entities"].get("product")
            return validated
    except Exception as e:
        logger.warning(f"Gemini intent extraction failed ({e}). Falling back to deterministic parser.")

    return parse_deterministic_intent(query)

def generate_grounded_explanation(
    query: str,
    intent: str,
    evidence_context: str,
    data_context: str
) -> Optional[str]:
    """
    Synthesizes a natural, grounded explanation using Gemini 2.5/3.7 Flash.
    Strictly constrained by the verified calculations and evidence.
    Returns None if Gemini is offline (triggering template formatting).
    """
    client = get_gemini_client()
    if not client:
        return None

    try:
        prompt = GROUNDED_SYNTHESIS_PROMPT.format(
            query=query,
            intent=intent,
            evidence_context=evidence_context,
            data_context=data_context
        )
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={
                "system_instruction": SYSTEM_INSTRUCTION,
                "temperature": 0.2
            }
        )
        if response and response.text:
            return response.text.strip()
    except Exception as e:
        logger.warning(f"Gemini narrative generation failed ({e}). Using deterministic template.")
        return None

def generate_embedding(text: str) -> Optional[List[float]]:
    """Generates embedding using gemini-embedding-001 if API key is available."""
    client = get_gemini_client()
    if not client:
        return None

    try:
        response = client.models.embed_content(
            model=GEMINI_EMBEDDING_MODEL,
            contents=text
        )
        if response and response.embedding:
            return response.embedding.values
    except Exception as e:
        logger.warning(f"Gemini embedding failed: {e}")
        return None
