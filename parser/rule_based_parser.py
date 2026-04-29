import re
import yaml
import structlog
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from common.models import RawMessage, ParsedProduct
from common.config import settings

logger = structlog.get_logger(__name__)


class RuleBasedParser:
    """
    Rule-based parser using YAML configuration (FR-2.2, FR-2.3, FR-2.4)
    Extracts category, brand, model, price, and attributes from message text.
    Supports grouped messages where header line defines category and following lines are products.
    """

    def __init__(self, config_dir: str = "config/parsing_rules"):
        self.config_dir = Path(config_dir)
        self.categories: Dict[str, Any] = {}
        self._load_all_rules()
    
    def _load_all_rules(self):
        """Load all parsing rules from config directory"""
        self.categories = {}
        for config_file in self.config_dir.glob("*.yaml"):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    category_config = config.get('category', {})
                    category_id = category_config.get('id')
                    if category_id:
                        self.categories[category_id] = category_config
                        logger.info(f"Loaded rules for category: {category_id}")
            except Exception as e:
                logger.error(f"Failed to load {config_file}", error=str(e))
    
    async def parse(self, raw_message: RawMessage) -> Optional[ParsedProduct]:
        """Parse raw message - универсальный парсер для всех форматов"""
        text_lower = raw_message.text.lower()

        # Skip ASIS/used/refurbished - ПРОВЕРЯЕМ ВСЕ СЛОВОСОЧЕТАНИЯ
        skip_keywords = [
            'asis', 'active', 'с коробки', 'без коробки', 'non active', 
            'обменки', 'б/у', 'refurbished', 'запак', 'активирован',
            'с комплектом', 'с кейсом', '0-15 циклов', 'гарантия на обменки'
        ]
        
        # Проверяем КАЖДУЮ строку на ASIS
        for line in raw_message.text.split('\n'):
            line_lower = line.lower()
            # Если строка содержит ASIS/обменки - пропускаем ВСЕ сообщение
            if any(kw in line_lower for kw in ['обменки', ' без коробки', 'с коробки', 'активирован']):
                logger.debug(f"⚠️ Skipping ASIS/used message: {raw_message.id}")
                return None

        lines = raw_message.text.split('\n')
        products = []
        current_category = None
        current_brand = None

        for line in lines:
            line_stripped = line.strip()
            if not line_stripped or len(line_stripped) < 3:
                continue

            line_lower = line_stripped.lower()

            # Skip metadata lines
            if any(x in line_lower for x in [
                'оформление заказа', 'менеджер', 'условия', 'отзывы', 
                'отправки', 'faq', 'http', 't.me/', '@', 'гарантия',
                'в зависимости от страны'
            ]):
                continue

            # Skip ASIS lines (повторная проверка)
            if any(kw in line_lower for kw in skip_keywords):
                continue

            # Check for category header (e.g., "iPhone 17:", "IPhone 17:")
            header_match = re.search(
                r'^(iphone\s*(17e|17\s*air|17\s*pro\s*max|17\s*pro|17|16e|16\s*pro\s*max|16\s*pro|16|15|14|13)|samsung|s2[4-6]|galaxy\s*s2[4-6]|galaxy\s*a[0-9]+|galaxy\s*z\s*fold|galaxy\s*z\s*flip|dyson|airpods|apple\s*watch|ipad|macbook)\s*:?', 
                line_lower
            )

            if header_match:
                category_id = self._detect_category(line_stripped)
                if category_id:
                    current_category = category_id
                    brand = self._extract_brand(line_stripped, self.categories.get(category_id, {}))
                    if brand:
                        current_brand = brand
                continue

            # Detect category from line content
            category_id = self._detect_category(line_stripped)

            if not category_id and current_category:
                category_id = current_category

            if not category_id:
                continue

            category_config = self.categories[category_id]
            brand = self._extract_brand(line_stripped, category_config)

            # Use current_brand from header
            if not brand and current_brand:
                brand = current_brand

            # Auto-detect brand from patterns - РАСШИРЕННЫЕ ПРАВИЛА
            if not brand:
                if category_id == 'smartphones':
                    # iPhone patterns - ЛЮБОЙ ФОРМАТ
                    iphone_patterns = [
                        r'\b(17e|17\s*air|17\s*pro\s*max|17\s*pro|17\s*plus|17|16e|16\s*pro\s*max|16\s*pro|16\s*plus|16|15\s*pro\s*max|15\s*pro|15\s*plus|15|14|13)\s+(\d{2,3}\s*gb)',
                        r'\b(sim\+esim|esim)\s+(17e|17\s*air|17\s*pro\s*max|17\s*pro|17|16e|16\s*pro\s*max|16\s*pro|16)\s+(\d{2,3}\s*gb)',
                        r'\b(17e|17|16e|16|15|14|13)\s+(\d{2,3}\s*gb)\s+(white|black|blue|pink|green|yellow|purple|red|lavender|sage)',
                    ]
                    for pattern in iphone_patterns:
                        if re.search(pattern, line_lower):
                            brand = 'Apple'
                            break
                    
                    # Samsung patterns
                    samsung_patterns = [
                        r'\b(s2[6-9]|s2[4-6]\s*ultra|s2[4-6]\+|s2[4-6]|a56|a36|a26|a17|a07)',
                        r'\b(z\s*fold|z\s*flip)\s*\d',
                    ]
                    for pattern in samsung_patterns:
                        if re.search(pattern, line_lower):
                            brand = 'Samsung'
                            break

                    # Fallback для iPhone - если есть флаг + GB + color
                    if not brand:
                        if re.search(r'🇪🇺|🇮🇳|🇯🇵|🇺🇸|🇨🇳|🇦🇪|🇭🇰|🇸🇬|🇰🇷', line_stripped):
                            if re.search(r'\d{2,3}\s*gb', line_lower):
                                if re.search(r'\b(white|black|blue|pink|green|yellow|purple|red|lavender|sage|starlight|midnight|natural|desert|cosmic|orange|silver|gold|ultramarine|teal)\b', line_lower):
                                    brand = 'Apple'

            if not brand:
                continue

            model = self._extract_model(line_stripped, brand)
            if not model:
                continue

            # Нормализуем бренд
            brand_clean = brand.split()[0].capitalize() if brand else 'Unknown'
            
            # _extract_model уже возвращает полное название (например, "Sony PS5 Slim")
            # Поэтому просто используем model как есть
            full_model = model.strip()
            
            price = self._extract_price(line_stripped, category_config)
            if not price:
                continue

            attributes = self._extract_attributes(line_stripped, category_config)

            # Уникальный ID для КАЖДОЙ строки продукта (даже из одного сообщения)
            line_hash = hash(line_stripped) & 0xffffffff
            product_id = f"prod_{raw_message.id}_{line_hash}_{int(datetime.utcnow().timestamp())}"
            
            # Уникальный message_link для каждой строки (добавляем hash)
            unique_message_link = f"{raw_message.message_link}?line={line_hash}"

            product = ParsedProduct(
                id=product_id,
                category_id=category_id,
                brand=brand_clean,
                model=full_model,
                price=price,
                source_channel=raw_message.channel_id,
                message_link=unique_message_link,
                timestamp=raw_message.timestamp,
                attributes=attributes,
                raw_message_id=raw_message.id
            )

            products.append(product)

        if products:
            logger.info(f"✅ Found {len(products)} products in message", count=len(products))
            return products[0]

        return None

        lines = raw_message.text.split('\n')
        products = []
        current_category = None
        current_brand = None

        for line in lines:
            line_stripped = line.strip()
            if not line_stripped or len(line_stripped) < 3:
                continue

            line_lower = line_stripped.lower()

            # Skip metadata lines
            if any(x in line_lower for x in ['оформление заказа', 'менеджер', 'условия', 'отзывы', 'отправки', 'faq', 'http', 't.me/', '@', 'меню', 'подборка', 'навигация']):
                continue

            # Skip ASIS lines
            if any(keyword in line_lower for keyword in skip_keywords):
                continue

            # Check for category header (e.g., "iPhone 17:", "Samsung S26:")
            header_match = re.search(r'^(iphone\s*(17e|17\s*air|17\s*pro\s*max|17\s*pro|17|16e|16\s*pro\s*max|16\s*pro|16|15|14|13)|samsung|s2[4-6]|galaxy\s*s2[4-6]|galaxy\s*a[0-9]+|galaxy\s*z\s*fold|galaxy\s*z\s*flip|dyson|airpods|apple\s*watch|ipad|macbook)\s*:?', line_lower)

            if header_match:
                category_id = self._detect_category(line_stripped)
                if category_id:
                    current_category = category_id
                    brand = self._extract_brand(line_stripped, self.categories.get(category_id, {}))
                    if brand:
                        current_brand = brand
                continue

            # Detect category from line content
            category_id = self._detect_category(line_stripped)

            if not category_id and current_category:
                category_id = current_category

            if not category_id:
                continue

            category_config = self.categories.get(category_id, {})
            brand = self._extract_brand(line_stripped, category_config)

            # Use current_brand from header
            if not brand and current_brand:
                brand = current_brand

            # Auto-detect brand from patterns
            if not brand:
                if category_id == 'smartphones':
                    # iPhone patterns
                    if re.search(r'\b(17e|17\s*air|17\s*pro\s*max|17\s*pro|17\s*plus|17|16e|16\s*pro\s*max|16\s*pro|16\s*plus|16|15\s*pro\s*max|15\s*pro|15\s*plus|15|14|13)\s*(\d{2,3}\s*gb)?', line_lower):
                        brand = 'Apple'
                    # Samsung patterns
                    elif re.search(r'\b(s2[6-9]|s2[4-6]\s*ultra|s2[4-6]|a56|a36|a26|a17|a07|z\s*fold|z\s*flip)', line_lower):
                        brand = 'Samsung'

                if not brand:
                    continue

            model = self._extract_model(line_stripped, brand)
            if not model or model == brand:
                continue

            price = self._extract_price(line_stripped, category_config)
            if not price:
                continue

            attributes = self._extract_attributes(line_stripped, category_config)

            product = ParsedProduct(
                id=f"prod_{raw_message.id}_{datetime.utcnow().timestamp()}_{hash(line_stripped)}",
                category_id=category_id,
                brand=brand.capitalize(),
                model=model.strip(),
                price=price,
                source_channel=raw_message.channel_id,
                message_link=raw_message.message_link,
                timestamp=raw_message.timestamp,
                attributes=attributes,
                raw_message_id=raw_message.id
            )

            products.append(product)

        # Return first product if multiple found
        if products:
            logger.info(f"✅ Found {len(products)} products in message", count=len(products))
            return products[0]

        return None

        lines = raw_message.text.split('\n')
        products = []
        current_category = None
        current_brand = None
        header_detected = False

        for line in lines:
            line_stripped = line.strip()
            if not line_stripped or len(line_stripped) < 3:
                continue
            
            line_lower = line_stripped.lower()
            
            # Skip metadata lines
            if any(x in line_lower for x in ['оформление заказа', 'менеджер', 'условия', 'отзывы', 'отправки', 'faq', 'http', 't.me/', '@']):
                continue
            
            # Skip ASIS lines
            if any(keyword in line_lower for keyword in skip_keywords):
                continue

            # Check for category header (e.g., "iPhone 17:", "Samsung S26:", "iPhone 16e")
            header_match = re.search(r'^(iphone\s*(17e|17\s*air|17\s*pro\s*max|17\s*pro|17|16e|16\s*pro\s*max|16\s*pro|16|15|14|13)|samsung|s2[4-6]|galaxy\s*s2[4-6]|galaxy\s*a[0-9]+|galaxy\s*z\s*fold|galaxy\s*z\s*flip|dyson|airpods|apple\s*watch|ipad|macbook)\s*:?', line_lower)
            
            if header_match:
                header_detected = True
                category_id = self._detect_category(line_stripped)
                if category_id:
                    current_category = category_id
                    brand = self._extract_brand(line_stripped, self.categories.get(category_id, {}))
                    if brand:
                        current_brand = brand
                continue

            # Detect category from line content
            category_id = self._detect_category(line_stripped)
            
            if not category_id and current_category:
                category_id = current_category
            
            if not category_id:
                continue

            category_config = self.categories[category_id]
            brand = self._extract_brand(line_stripped, category_config)
            
            # Use current_brand from header
            if not brand and current_brand:
                brand = current_brand
            
            # Auto-detect brand from patterns
            if not brand:
                if category_id == 'smartphones':
                    # iPhone patterns (including new format "17 256GB")
                    if re.search(r'\b(17e|17\s*air|17\s*pro\s*max|17\s*pro|17\s*plus|17|16e|16\s*pro\s*max|16\s*pro|16\s*plus|16|15\s*pro\s*max|15\s*pro|15\s*plus|15|14|13)\s*(\d{2,3}\s*gb)', line_lower):
                        brand = 'Apple'
                    # Samsung patterns
                    elif re.search(r'\b(s2[6-9]|s2[4-6]\s*ultra|s2[4-6]|a56|a36|a26|a17|a07|z\s*fold|z\s*flip)', line_lower):
                        brand = 'Samsung'
                    # Fallback to Apple for any iPhone-like pattern
                    elif re.search(r'\b\d{2,3}\s*gb', line_lower) and re.search(r'\b(white|black|blue|pink|green|yellow|purple|red|lavender|sage|starlight|midnight|natural|desert|cosmic|orange|silver|gold)', line_lower):
                        brand = 'Apple'
            
            if not brand:
                continue

            model = self._extract_model(line_stripped, brand)
            if not model or model == brand:
                continue

            price = self._extract_price(line_stripped, category_config)
            if not price:
                continue

            attributes = self._extract_attributes(line_stripped, category_config)

            product = ParsedProduct(
                id=f"prod_{raw_message.id}_{datetime.utcnow().timestamp()}_{hash(line_stripped)}",
                category_id=category_id,
                brand=brand.capitalize(),
                model=model.strip(),
                price=price,
                source_channel=raw_message.channel_id,
                message_link=raw_message.message_link,
                timestamp=raw_message.timestamp,
                attributes=attributes,
                raw_message_id=raw_message.id
            )

            products.append(product)

        if products:
            logger.info(f"✅ Found {len(products)} products in message", count=len(products))
            return products[0]

        return None
    
    def _detect_category(self, text: str) -> Optional[str]:
        """Detect category - универсальное определение"""
        text_lower = text.lower()

        # === SMARTPHONES ===
        # iPhone - ЛЮБОЙ ФОРМАТ: "17 256GB", "iPhone 17", "Sim+eSim 17"
        iphone_patterns = [
            r'\b(17e|17\s*air|17\s*pro\s*max|17\s*pro|17\s*plus|17|16e|16\s*pro\s*max|16\s*pro|16\s*plus|16|15\s*pro\s*max|15\s*pro|15\s*plus|15|14\s*plus|14|13)\s*(\d{2,3}\s*gb)',
            r'\b(sim\+esim|esim)\s+(17e|17|16e|16|15|14|13)',
            r'\biphone\s*(17e|17|16e|16|15|14|13)',
        ]
        for pattern in iphone_patterns:
            if re.search(pattern, text_lower):
                return 'smartphones'

        # Samsung - S26, S25, A56, etc.
        samsung_patterns = [
            r'\b(s2[6-9]|s2[4-6]\s*ultra|s2[4-6]\s*\+|s2[4-6]|a56|a36|a26|a17|a07)\b',
            r'\b(z\s*fold|z\s*flip)\s*\d',
        ]
        for pattern in samsung_patterns:
            if re.search(pattern, text_lower):
                return 'smartphones'

        # === LAPTOPS ===
        if re.search(r'\b(macbook|mac\s*book|neo)\s*(air|pro)?', text_lower):
            return 'laptops'

        # === TABLETS ===
        if re.search(r'\b(ipad|tablet)\s*(air|pro|mini)?', text_lower):
            return 'tablets'

        # === ACCESSORIES ===
        if re.search(r'\b(airpods|airpods\s*pro|airpods\s*max|apple\s*watch|watch\s*se|watch\s*ultra)', text_lower):
            return 'accessories'

        # === DYSON ===
        if re.search(r'\b(dyson|hs\d{2}|hd\d{2}|v\d{2}|airwrap|supersonic)', text_lower):
            return 'accessories'

        # === CONSOLES ===
        if re.search(r'\b(ps5|playstation|xbox|nintendo|steam\s*deck|oculus|quest)', text_lower):
            return 'consoles'

        # Fallback to keyword matching
        for category_id, config in self.categories.items():
            keywords = config.get('keywords', [])
            for keyword in keywords:
                if keyword.lower() in text_lower:
                    return category_id
        return None
    
    def _extract_brand(self, text: str, category_config: Dict) -> Optional[str]:
        """Extract brand from text using brand patterns"""
        brand_patterns = category_config.get('brand_patterns', {})
        text_lower = text.lower()

        for brand, patterns in brand_patterns.items():
            for pattern in patterns:
                if pattern.lower() in text_lower:
                    return brand

        return None
    
    def _extract_model(self, text: str, brand: str) -> Optional[str]:
        """Extract model - универсальный парсер для всех форматов"""
        text_lower = text.lower()
        brand_lower = brand.lower()

        # iPhone - все форматы: "iPhone 17", "17 256GB", "Sim+eSim 17 256GB"
        if brand_lower == 'apple':
            # Format 1: "17 256GB White" (Top re:sale)
            match = re.search(
                r'\b((17e|17\s*air|17\s*pro\s*max|17\s*pro|17\s*plus|17|16e|16\s*pro\s*max|16\s*pro|16\s*plus|16|15\s*pro\s*max|15\s*pro|15\s*plus|15|14\s*plus|14|13)\s+(\d{2,3}\s*gb)\s+(white|black|blue|pink|green|yellow|purple|red|lavender|sage|teal|ultramarine|starlight|midnight|natural|desert|cosmic|orange|silver|gold)?)',
                text,
                re.IGNORECASE
            )
            if match:
                return match.group(1).strip()

            # Format 2: "Sim+eSim 17 256GB White"
            match = re.search(
                r'(sim\+esim|esim)\s+((17e|17\s*air|17\s*pro\s*max|17\s*pro|17|16e|16\s*pro\s*max|16\s*pro|16)\s+(\d{2,3}\s*gb)\s+(white|black|blue|pink|green|yellow|purple|red|lavender|sage|teal|ultramarine|starlight|midnight|natural|desert|cosmic|orange|silver|gold)?)',
                text,
                re.IGNORECASE
            )
            if match:
                return match.group(2).strip()

            # Format 3: Full "iPhone 17 Pro Max 256GB Blue"
            match = re.search(
                r'(iphone\s*(17e|17\s*air|17\s*pro\s*max|17\s*pro|17\s*plus|17|16e|16\s*pro\s*max|16\s*pro|16\s*plus|16|15\s*pro\s*max|15\s*pro|15\s*plus|15|14\s*plus|14|13)\s*(\d{1,3}\s*gb)?\s*(black|white|blue|pink|green|yellow|purple|red|lavender|sage|teal|ultramarine|starlight|midnight|rose|desert|natural|orange|cosmic|silver|gold)?)',
                text,
                re.IGNORECASE
            )
            if match:
                return match.group(1).strip()
            
            # Pattern 2: Standalone "17 256GB White" or "17e 256GB"
            match = re.search(
                r'\b((?:17e|17\s*air|17\s*pro\s*max|17\s*pro|17\s*plus|17|16e|16\s*pro\s*max|16\s*pro|16\s*plus|16|15\s*pro\s*max|15\s*pro|15\s*plus|15|14|13)\s+(\d{2,3}\s*gb)\s+(black|white|blue|pink|green|yellow|purple|red|lavender|sage|teal|ultramarine|starlight|midnight|rose|desert|natural|orange|silver|gold)?)',
                text,
                re.IGNORECASE
            )
            if match:
                return match.group(1).strip()
            
            # Pattern 3: Just "17 256GB" without color
            match = re.search(
                r'\b((?:17e|17\s*air|17\s*pro\s*max|17\s*pro|17|16e|16\s*pro\s*max|16\s*pro|16|15|14|13)\s+\d{2,3}\s*gb)',
                text,
                re.IGNORECASE
            )
            if match:
                return match.group(1).strip()
            
            # Alternative: Just model number like "17 256GB"
            match = re.search(
                r'\b((?:17e|17\s*air|17\s*pro\s*max|17\s*pro|17|16e|16\s*pro\s*max|16\s*pro|16|15\s*pro\s*max|15\s*pro|15|14\s*pro\s*max|14\s*pro|14|13)\s*(\d{1,3}\s*gb)?\s*(black|white|blue|pink|green|yellow|purple|red|lavender|sage|teal|ultramarine|starlight|midnight|rose|desert|natural|orange)?)',
                text,
                re.IGNORECASE
            )
            if match:
                return match.group(1).strip()

        # Samsung Galaxy models - improved for S26, S25, etc.
        if 'samsung' in text_lower or 'galaxy' in text_lower or re.search(r'\bs\d{2,3}', text_lower) or brand_lower == 'samsung':
            # Match S26 Ultra, S25+, Z Fold, etc.
            match = re.search(
                r'(s26\s*ultra|s26\s*\+|s26|s25\s*ultra|s25\s*\+|s25|s24\s*ultra|s24\s*\+|s24|z\s*fold\s*\d|z\s*flip\s*\d|a56|a36|a26|a17|a07)\s*(\d{1,2}/\d{2,3}\s*gb)?\s*(black|white|blue|pink|green|yellow|purple|red|gray|graphite|mint|navy|silver|gold|violet|lavender|onyx|marble|teal|indigo|sand|blue\s*black)?',
                text,
                re.IGNORECASE
            )
            if match:
                return match.group(1).strip()

        # MacBook models
        if 'macbook' in text_lower:
            match = re.search(
                r'(macbook\s*(?:pro|air|neo)?\s*(?:\d{2})?\s*(?:inch)?\s*(m[1-7]\s*(?:pro|max|ultra)?)?\s*(\d{2})?\s*(gb|tb)?\s*(black|white|blue|pink|green|yellow|purple|red|lavender|sage|teal|ultramarine|starlight|midnight|rose|desert|natural|space\s*gray|space\s*black|silver|gold|sky\s*blue|indigo|citrus)?)',
                text,
                re.IGNORECASE
            )
            if match:
                return match.group(0).strip()

        # iPad models
        if 'ipad' in text_lower:
            match = re.search(
                r'(ipad\s*(?:air|pro|mini)?\s*(\d{2})?\s*(m[1-7])?\s*(\d{2,3}\s*gb)?\s*(wi-fi|lte|5g)?\s*(black|white|blue|pink|green|yellow|purple|red|starlight|space\s*gray|silver|gold)?)',
                text,
                re.IGNORECASE
            )
            if match:
                return match.group(1).strip()

        # Apple Watch
        if 'watch' in text_lower and ('apple' in text_lower or 'se' in text_lower or 'ultra' in text_lower):
            match = re.search(
                r'(apple\s*watch\s*(?:se\d?|s\d{2}|ultra\s*\d?)\s*(\d{2})?mm?\s*(black|white|blue|pink|green|yellow|purple|red|starlight|space\s*gray|silver|gold|rose\s*gold|milanese|sport\s*band|sport\s*loop)?)',
                text,
                re.IGNORECASE
            )
            if match:
                return match.group(1).strip()

        # AirPods
        if 'airpods' in text_lower:
            match = re.search(
                r'(airpods\s*(?:pro\s*\d?|max|m\d?)?\s*(black|white|blue|pink|green|yellow|purple|red|starlight|space\s*gray|silver|gold|rose|orange)?)',
                text,
                re.IGNORECASE
            )
            if match:
                return match.group(1).strip()

        # Dyson
        if 'dyson' in text_lower or re.search(r'\b(hs|hd|v)\d{2}\b', text_lower):
            match = re.search(
                r'(dyson\s*(?:hs|hd|v)?\d{2,3}\s*(?:airwrap|supersonic|detect|absolute|submarine|pro)?\s*(?:black|white|blue|pink|green|yellow|purple|red|nickel|copper|gold|ceramic|strawberry|prussian|vinca|amber|jasper|kanzan|iron)?\s*(?:fuchsia|topaz|pop|silk|velvet|plum|orange)?)',
                text,
                re.IGNORECASE
            )
            if match:
                return match.group(1).strip()

        # PS5
        if 'ps5' in text_lower or 'playstation' in text_lower:
            match = re.search(
                r'(ps5\s*(?:pro|slim|digital|disk)?\s*(\d{1,2}tb|\d{3}gb)?\s*(black|white|blue|pink|purple|red|camo)?)',
                text,
                re.IGNORECASE
            )
            if match:
                return match.group(1).strip()

        # Generic fallback - extract model after brand
        words = text.split()
        start_idx = 0
        for i, word in enumerate(words):
            if brand_lower in word.lower():
                start_idx = i
                break

        model_parts = []
        for word in words[start_idx:start_idx+10]:
            # Stop at price indicators or metadata
            if any(x in word.lower() for x in ['₽', 'руб', 'rub', 'price', 'цена', 'менеджер', 'оформление', 'заказа', 'условия', 'отзывы', 'отправки', 'http', 't.me']):
                break
            # Keep alphanumeric model parts
            if re.match(r'^[\w\d\-\+\./]+$', word):
                model_parts.append(word)
            else:
                break

        return ' '.join(model_parts).strip() if model_parts else brand
    
    def _extract_price(self, text: str, category_config: Dict) -> Optional[float]:
        """Extract price - универсальный парсер цен для всех форматов"""
        text_clean = text.replace(' ', '')
        
        # Format 1: "63000₽", "63000руб", "63000RUB"
        match = re.search(r'(\d+)\s*(₽|руб|rub)', text_clean, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass

        # Format 2: "— 63000", "- 63000" (после тире)
        match = re.search(r'[-—]\s*(\d{3,})', text.replace(' ', ''))
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass

        # Format 3: Европейский формат "63.000" 
        match = re.search(r'(\d+)\.(\d{3})\b', text)
        if match:
            try:
                return float(f"{match.group(1)}{match.group(2)}")
            except ValueError:
                pass

        return None
    
    def _extract_attributes(self, text: str, category_config: Dict) -> Dict[str, Any]:
        """Extract attributes from text including flags, region, SIM type"""
        attributes = {}

        # Флаги стран
        flags_esim_only = category_config.get('flags_esim_only', [])
        flags_esim_physical = category_config.get('flags_esim_physical', [])
        flags_physical_only = category_config.get('flags_physical_only', [])

        # Определяем флаг
        flag = None
        flag_match = re.search(r'(🇧🇭|🇨🇦|🇬🇺|🇯🇵|🇰🇼|🇲🇽|🇴🇲|🇶🇦|🇸🇦|🇦🇪|🇺🇸|🇻🇮|🇪🇺|🇮🇳|🇻🇳|🇦🇺|🇳🇿|🇰🇷|🇸🇬|🇭🇰|🇨🇳|🇷🇺|🇰🇿|🇮🇩|🇹🇭|🇵🇭|🇲🇾|🇵🇦|🇨🇱|🇿🇦|🇬🇧)', text)
        if flag_match:
            flag = flag_match.group(1)
            attributes['flag'] = flag

            # Определяем тип SIM по флагу
            if flag in flags_esim_only:
                attributes['sim_type'] = 'eSIM only'
            elif flag in flags_esim_physical:
                attributes['sim_type'] = 'eSIM + physical SIM'
            elif flag in flags_physical_only:
                attributes['sim_type'] = '2 physical SIM'
            else:
                # По умолчанию для iPhone 17 Air - только eSIM
                if 'iphone 17 air' in text.lower():
                    attributes['sim_type'] = 'eSIM only'
                else:
                    attributes['sim_type'] = 'unknown'

        # Определяем SIM тип из явного упоминания Sim+eSim или eSim
        if 'sim_type' not in attributes:
            if 'sim+esim' in text.lower() or 'sim + esim' in text.lower():
                attributes['sim_type'] = 'eSIM + physical SIM'
            elif 'esim' in text.lower() and 'sim' not in text.lower().replace('esim', ''):
                attributes['sim_type'] = 'eSIM only'
            elif '2sim' in text.lower() or 'dual sim' in text.lower():
                attributes['sim_type'] = '2 physical SIM'
            elif flag:
                # Если флаг есть, но не в списках - ставим unknown
                if 'sim_type' not in attributes:
                    attributes['sim_type'] = 'unknown'
            else:
                # По умолчанию для iPhone 17 Air - только eSIM
                if 'iphone 17 air' in text.lower():
                    attributes['sim_type'] = 'eSIM only'
                else:
                    attributes['sim_type'] = 'unknown'
        else:
            # Флаг не найден - определяем SIM из текста
            if 'iphone 17 air' in text.lower():
                attributes['sim_type'] = 'eSIM only'
            else:
                attributes['sim_type'] = 'unknown'

        # Определяем SIM тип из явного упоминания Sim+eSim или eSim
        if 'sim+esim' in text.lower() or 'sim + esim' in text.lower():
            attributes['sim_type'] = 'eSIM + physical SIM'
        elif 'esim' in text.lower() and 'sim' not in text.lower().replace('esim', ''):
            attributes['sim_type'] = 'eSIM only'
        elif '2sim' in text.lower() or 'dual sim' in text.lower():
            attributes['sim_type'] = '2 physical SIM'

        # Extract storage from text (e.g., "4/128", "8/256", "128GB", "256GB")
        storage_match = re.search(r'(\d+)/(\d+)\s*gb|\b(\d{3,4})\s*gb\b', text, re.IGNORECASE)
        if storage_match:
            if storage_match.group(1) and storage_match.group(2):
                attributes['ram'] = f"{storage_match.group(1)}GB"
                attributes['storage'] = f"{storage_match.group(2)}GB"
            elif storage_match.group(3):
                attributes['storage'] = f"{storage_match.group(3)}GB"

        return attributes
