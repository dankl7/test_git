import json
import structlog
from datetime import datetime
from typing import Optional, Dict, Any
from common.models import RawMessage, ParsedProduct
from common.config import settings

logger = structlog.get_logger(__name__)


class LLMParser:
    """LLM-based parser for complex product extraction (FR-2.5)"""

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4"):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model = model
        self._client = None
        self._initialized = False

    async def _ensure_initialized(self):
        """Lazy initialization of LLM client"""
        if self._initialized or not self.api_key:
            return

        try:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=self.api_key)
            logger.info("✅ LLM client initialized")
        except ImportError:
            logger.warning("⚠️ OpenAI not installed, LLM parsing disabled")
        except Exception as e:
            logger.error(f"❌ Failed to initialize LLM client: {e}")
        finally:
            self._initialized = True

    async def parse(self, raw_message: RawMessage) -> Optional[ParsedProduct]:
        """Parse product using LLM"""
        if not self._initialized:
            await self._ensure_initialized()

        if not self._client:
            return None

        try:
            prompt = self._build_prompt(raw_message.text)
            response = await self._call_llm(prompt)
            if response:
                return self._parse_llm_response(response, raw_message)
        except Exception as e:
            logger.error(f"❌ LLM parsing failed: {e}")
        return None

    def _build_prompt(self, text: str) -> str:
        """Build LLM prompt for product extraction"""
        return f"""Extract product information from this message. Return JSON with:
- category_id: one of [smartphones, laptops, accessories]
- brand: brand name
- model: model name
- price: numeric price in rubles
- attributes: dict with storage, color, ram, etc.
Message: {text}
Return only valid JSON."""

    async def _call_llm(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Call LLM API"""
        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=500
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"❌ LLM API call failed: {e}")
            return None

    def _parse_llm_response(self, response: Dict[str, Any], raw_message: RawMessage) -> Optional[ParsedProduct]:
        """Map LLM response to ParsedProduct"""
        try:
            return ParsedProduct(
                id=f"prod_{raw_message.id}_{datetime.utcnow().timestamp()}",
                category_id=response.get('category_id', 'unknown'),
                brand=response.get('brand', 'Unknown'),
                model=response.get('model', 'Unknown'),
                price=float(response.get('price', 0)),
                source_channel=raw_message.channel_id,
                message_link=raw_message.message_link,
                timestamp=raw_message.timestamp,
                attributes=response.get('attributes', {}),
                raw_message_id=raw_message.id
            )
        except Exception as e:
            logger.error(f"❌ Failed to parse LLM response: {e}")
            return None
