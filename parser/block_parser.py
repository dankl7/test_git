"""
Block-based parser for Top re:sale format
Parses posts with structure:
  HEADER: line1
  line2
  line3
  
  NEXT HEADER: line1
"""
import re
import structlog
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from common.models import RawMessage, ParsedProduct

logger = structlog.get_logger(__name__)


class BlockParser:
    """Parser based on blocks (header + lines)"""
    
    # Header patterns
    HEADER_PATTERNS = {
        'smartphones': [
            (r'iphone\s*(17\s*pro\s*max|17\s*pro|17\s*air|17e|17|16\s*pro\s*max|16\s*pro|16e|16|15\s*pro\s*max|15\s*pro|15|14|13)', 'apple'),
            (r'samsung\s*(s2[0-9]\s*ultra|s2[0-9]\+|s2[0-9]|a5[0-9]|a3[0-9]|a2[0-9]|a1[0-9]|a0[0-9])', 'samsung'),
            (r's2[0-9]\s*ultra|s2[0-9]\+|s2[0-9]', 'samsung'),
            (r'z\s*fold\s*\d|z\s*flip\s*\d', 'samsung'),
            (r'xiaomi\s*\d|poco\s*\w', 'xiaomi'),
            (r'honor\s*\d|honor\s*magi', 'honor'),
            (r'huawei\s*\w|pura\s*\d', 'huawei'),
        ],
        'laptops': [
            (r'macbook\s*(air|pro|neo)?\s*(\d{2})?', 'apple'),
            (r'macbook\s*(m[1-7]\s*(pro|max|ultra)?)?', 'apple'),
        ],
        'tablets': [
            (r'ipad\s*(air|pro|mini)?\s*(\d{2})?', 'apple'),
            (r'galaxy\s*tab\s*\w', 'samsung'),
        ],
        'accessories': [
            (r'airpods\s*(\d|pro|max)?', 'apple'),
            (r'apple\s*watch\s*(se|s\d|ultra)?', 'apple'),
            (r'dyson\s*(hs|hd|v)?\d', 'dyson'),
        ],
        'consoles': [
            (r'ps5|playstation', 'sony'),
            (r'xbox', 'microsoft'),
            (r'nintendo\s*switch', 'nintendo'),
        ],
    }
    
    def __init__(self):
        self.categories = {}
    
    def parse(self, raw_message: RawMessage) -> List[ParsedProduct]:
        """Parse message into blocks and extract products"""
        products = []
        text = raw_message.text.strip()
        
        # Skip ASIS/used/refurbished messages
        if self._is_asim_message(text):
            logger.debug(f"⚠️ Skipping ASIS/used message: {raw_message.id}")
            return []
        
        # Split into blocks by headers
        blocks = self._split_into_blocks(text)
        
        for header, lines in blocks:
            if not lines:
                continue
            
            # Parse header to get category and model prefix
            category_id, brand, model_prefix = self._parse_header(header)
            
            if not category_id or not brand:
                continue
            
            # Parse each line in the block
            for line in lines:
                product = self._parse_line(line, category_id, brand, model_prefix, raw_message)
                if product:
                    products.append(product)
        
        return products
    
    def _is_asim_message(self, text: str) -> bool:
        """Check if message contains ASIS/used keywords"""
        asim_keywords = [
            'обменки', 'без коробки', 'с коробки', 'активирован', 
            'асис', 'б/у', 'refurbished', 'с комплектом', 'запак'
        ]
        text_lower = text.lower()
        return any(kw in text_lower for kw in asim_keywords)
    
    def _split_into_blocks(self, text: str) -> List[Tuple[str, List[str]]]:
        """Split text into blocks by headers"""
        blocks = []
        lines = text.split('\n')
        
        current_header = ""
        current_lines = []
        
        # Header keywords
        header_keywords = ['iphone', 'ipad', 'macbook', 'airpods', 'apple watch', 
                          'samsung', 'galaxy', 'dyson', 'ps5', 'playstation', 
                          'xbox', 'nintendo', 's26', 's25', 's24', 'a56', 'a36']
        
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue
            
            line_lower = line_stripped.lower()
            
            # Check if line is a header
            is_header = False
            for kw in header_keywords:
                if kw in line_lower and (':' in line_stripped or re.search(r'\d', line_stripped)):
                    is_header = True
                    break
            
            # Also check for date pattern at start (skip)
            if re.match(r'\d{2}/\d{2}/\d{2}', line_stripped):
                continue
            
            # Skip metadata lines
            if any(x in line_lower for x in ['оформление', 'менеджер', 'условия', 'отзывы', 'отправки', 'faq', 'http', 't.me/', '@']):
                continue
            
            if is_header:
                # Save previous block
                if current_header and current_lines:
                    blocks.append((current_header, current_lines))
                
                # Start new block
                current_header = line_stripped.rstrip(':')
                current_lines = []
            else:
                # Add line to current block
                if current_header:
                    current_lines.append(line_stripped)
        
        # Save last block
        if current_header and current_lines:
            blocks.append((current_header, current_lines))
        
        return blocks
    
    def _parse_header(self, header: str) -> Tuple[Optional[str], Optional[str], str]:
        """Parse header to extract category, brand, model prefix"""
        header_lower = header.lower()
        
        for category_id, patterns in self.HEADER_PATTERNS.items():
            for pattern, brand in patterns:
                match = re.search(pattern, header_lower)
                if match:
                    # Extract model prefix from header
                    model_prefix = match.group(0) if match.lastindex else match.group(0)
                    return category_id, brand, model_prefix
        
        return None, None, ""
    
    def _parse_line(self, line: str, category_id: str, brand: str, model_prefix: str, raw_message: RawMessage) -> Optional[ParsedProduct]:
        """Parse a single line into a product"""
        line_stripped = line.strip()
        if not line_stripped or len(line_stripped) < 5:
            return None
        
        # Extract SIM type
        sim_type = self._extract_sim_type(line_stripped)
        
        # Extract flag
        flag = self._extract_flag(line_stripped)
        
        # Extract storage, color, price
        storage = self._extract_storage(line_stripped)
        color = self._extract_color(line_stripped)
        price = self._extract_price(line_stripped)
        
        if not price:
            return None
        
        # Extract model details with proper formatting
        model = self._extract_model(line_stripped, model_prefix, category_id, brand)
        
        if not model:
            return None
        
        # Build attributes
        attributes = {}
        if storage:
            attributes['storage'] = storage
        if color:
            attributes['color'] = color
        if sim_type:
            attributes['sim_type'] = sim_type
        if flag:
            attributes['flag'] = flag
        
        # Generate unique ID
        line_hash = hash(line_stripped) & 0xffffffff
        product_id = f"prod_{raw_message.id}_{line_hash}_{int(datetime.utcnow().timestamp())}"
        unique_message_link = f"{raw_message.message_link}?line={line_hash}"
        
        return ParsedProduct(
            id=product_id,
            category_id=category_id,
            brand=brand.lower(),
            model=model,
            price=price,
            source_channel=raw_message.channel_id,
            message_link=unique_message_link,
            timestamp=raw_message.timestamp,
            attributes=attributes,
            raw_message_id=raw_message.id
        )
    
    def _extract_sim_type(self, line: str) -> str:
        """Extract SIM type from line"""
        line_lower = line.lower()
        
        if 'sim+esim' in line_lower or 'sim + esim' in line_lower:
            return 'sim+esim'
        elif 'esim' in line_lower and 'sim' not in line_lower.replace('esim', ''):
            return 'esim'
        elif '2sim' in line_lower or 'dual sim' in line_lower:
            return '2sim'
        
        return 'unknown'
    
    def _extract_flag(self, line: str) -> Optional[str]:
        """Extract flag emoji from line"""
        flag_match = re.search(r'(🇧🇭|🇨🇦|🇬🇺|🇯🇵|🇰🇼|🇲🇽|🇴🇲|🇶🇦|🇸🇦|🇦🇪|🇺🇸|🇻🇮|🇪🇺|🇮🇳|🇻🇳|🇦🇺|🇳🇿|🇰🇷|🇸🇬|🇭🇰|🇨🇳|🇷🇺|🇰🇿|🇮🇩|🇹🇭|🇵🇭|🇲🇾|🇵🇦|🇨🇱|🇿🇦|🇬🇧)', line)
        return flag_match.group(1) if flag_match else None
    
    def _extract_storage(self, line: str) -> Optional[str]:
        """Extract storage from line (e.g., 256GB, 512GB)"""
        match = re.search(r'(\d{2,3})\s*gb', line, re.IGNORECASE)
        return f"{match.group(1)}GB" if match else None
    
    def _extract_color(self, line: str) -> Optional[str]:
        """Extract color from line"""
        colors = ['black', 'white', 'blue', 'pink', 'green', 'yellow', 'purple', 'red', 
                 'lavender', 'sage', 'starlight', 'midnight', 'natural', 'desert', 
                 'cosmic', 'orange', 'silver', 'gold', 'ultramarine', 'teal', 'gray']
        
        line_lower = line.lower()
        for color in colors:
            if color in line_lower:
                return color.capitalize()
        return None
    
    def _extract_price(self, line: str) -> Optional[float]:
        """Extract price from line - handles formats: 62900₽, 62 900 ₽, — 62900"""
        # Format 1: "62900₽", "62900руб"
        match = re.search(r'(\d+)\s*(₽|руб|rub)', line, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
        
        # Format 2: "— 62900", "- 62900"
        match = re.search(r'[-—]\s*(\d{3,})', line.replace(' ', ''))
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
        
        return None
    
    def _extract_model(self, line: str, model_prefix: str, category_id: str, brand: str) -> str:
        """Extract model name with proper prefix based on category and brand"""
        line_lower = line.lower()
        
        # Extract storage and color for all models
        storage_match = re.search(r'(\d{2,3}\s*gb)', line_lower)
        storage = storage_match.group(1).upper() if storage_match else ""
        
        color_match = re.search(r'\b(black|white|blue|pink|green|yellow|purple|red|lavender|sage|starlight|midnight|natural|desert|cosmic|orange|silver|gold|ultramarine|teal|gray)\b', line_lower)
        color = color_match.group(1).upper() if color_match else ""

        # iPhone models
        if brand == 'apple' and category_id == 'smartphones':
            iphone_match = re.search(r'(17\s*pro\s*max|17\s*pro|17\s*air|17e|17|16\s*pro\s*max|16\s*pro|16e|16|15\s*pro\s*max|15\s*pro|15|14|13)\s+(\d{2,3}\s*gb)?', line_lower)
            if iphone_match:
                model_num = iphone_match.group(1).strip().upper()
                storage = iphone_match.group(2).strip().upper() if iphone_match.group(2) else storage
                return f"iPhone {model_num} {storage}".strip()
        
            # Samsung smartphones
            if brand == 'samsung' and category_id == 'smartphones':
                samsung_match = re.search(r'(s2[0-9]\s*ultra|s2[0-9]\+|s2[0-9]|a5[0-9]|a3[0-9]|a2[0-9]|a1[0-9]|a0[0-9]|z\s*fold\s*\d|z\s*flip\s*\d)\s*(\d+/\d+gb|\d{2,3}\s*gb)?', line_lower)
                if samsung_match:
                    model_num = samsung_match.group(1).strip().upper()
                    storage = samsung_match.group(2).strip().upper() if samsung_match.group(2) else storage
                    return f"Samsung {model_num} {storage}".strip()
        
        # MacBook
        if brand == 'apple' and category_id == 'laptops':
            macbook_match = re.search(r'(macbook\s*(air|pro|neo)?)\s*(\d{2})?\s*(m[1-7]\s*(pro|max|ultra)?)?\s*(\d{2})?\s*(gb|tb)?', line_lower)
            if macbook_match:
                model_type = macbook_match.group(2).strip().upper() if macbook_match.group(2) else ""
                year = macbook_match.group(3) or ""
                chip = macbook_match.group(4).strip().upper() if macbook_match.group(4) else ""
                size = macbook_match.group(5) or ""
                storage = macbook_match.group(6).strip().upper() if macbook_match.group(6) else ""
                
                if model_type:
                    return f"MacBook {model_type} {year} {chip} {size}{storage}".strip()
                else:
                    return "MacBook"
            
            # Fallback: extract "MacBook Air 13 M4 2025" pattern
            mb_match = re.search(r'(macbook\s*(air|pro|neo))\s*(\d{2})?\s*(m[1-7]\s*(pro|max|ultra)?)?\s*(\d{2})?\s*(gb|tb)?', line_lower)
            if mb_match:
                parts = [part for part in mb_match.groups() if part]
                return ' '.join(parts).strip().upper().replace('MACBOOK', 'MacBook')
        
        # iPad
        if brand == 'apple' and category_id == 'tablets':
            ipad_match = re.search(r'(ipad\s*(air|pro|mini)?)\s*(\d{2})?\s*(m[1-7])?\s*(\d{2,3}\s*gb)?\s*(wi-fi|lte|5g)?', line_lower)
            if ipad_match:
                parts = [p for p in ipad_match.groups() if p]
                return ' '.join(parts).strip().upper().replace('IPAD', 'iPad')
        
        # Apple Watch
        if brand == 'apple' and category_id == 'accessories' and 'watch' in line_lower:
            watch_match = re.search(r'(apple\s*watch\s*(se|s\d|ultra)?)', line_lower)
            if watch_match:
                return watch_match.group(1).strip().title()
        
        # AirPods
        if brand == 'apple' and category_id == 'accessories' and 'airpods' in line_lower:
            airpods_match = re.search(r'(airpods\s*(\d|pro|max)?)', line_lower)
            if airpods_match:
                return airpods_match.group(1).strip().title()
        
        # Dyson
        if brand == 'dyson':
            dyson_match = re.search(r'(dyson\s*(hs|hd|v)?\d{2,3})', line_lower)
            if dyson_match:
                return dyson_match.group(1).strip().title()
        
        # Sony PS5
        if brand == 'sony' and category_id == 'consoles':
            if 'ps5' in line_lower:
                return "PS5"
        
        # Fallback: use model_prefix with storage if available
        if storage_match:
            storage = storage_match.group(1).upper()
            return f"{model_prefix} {storage}".strip()

        return model_prefix.strip()