"""Top re:sale optimized block-based parser"""
import re
from datetime import datetime
from typing import List
from common.models import RawMessage, ParsedProduct
from .base_parser import BaseBlockParser


class TopResaleParser(BaseBlockParser):
    FLAG_PATTERN = BaseBlockParser.COUNTRY_SIM.keys() and '|'.join(BaseBlockParser.COUNTRY_SIM.keys())
    FLAG_REGEX = f"({'|'.join(k for k in BaseBlockParser.COUNTRY_SIM.keys())})"
    
    def parse(self, raw: RawMessage) -> List[ParsedProduct]:
        products = []
        blocks = self._split_blocks(raw.text)
        current_brand_context = None  # Контекст бренда для строк без явного бренда
        
        for hdr, lines in blocks:
            # Если заголовок содержит бренд (Samsung, Apple и т.д.), запоминаем его
            if hdr:
                hdr_lower = hdr.lower()
                if 'samsung' in hdr_lower or re.search(r'\bs\d{2}', hdr_lower) or re.search(r'\ba\d{2}', hdr_lower):
                    current_brand_context = 'samsung'
                elif 'apple' in hdr_lower or 'iphone' in hdr_lower or 'macbook' in hdr_lower or 'ipad' in hdr_lower:
                    current_brand_context = 'apple'
                elif 'dyson' in hdr_lower:
                    current_brand_context = 'dyson'
                elif 'ps5' in hdr_lower or 'sony' in hdr_lower:
                    current_brand_context = 'sony'
            
            for ln in lines:
                # Skip ASIS/refurbished lines
                if self._is_asis_line(ln):
                    continue
                p = self._parse_line(ln, raw, hdr, brand_context=current_brand_context)
                if p:
                    products.append(p)
                    # Сбрасываем контекст после успешного парсинга, чтобы не наследовался
                    # current_brand_context = None
        return products
    
    def _is_asis_line(self, line):
        """Check if individual line is ASIS/refurbished"""
        ll = line.lower()
        return any(k in ll for k in ['обменки','без коробки','с коробки','активирован','асис','б/у','refurbished','запак','asis'])
    
    def _split_blocks(self, text):
        return self.split_blocks(text, self._parse_header)
    
    def _parse_header(self, line):
        ll = line.lower()
        # Skip if has price and flag - it's a product line
        if (any(x in line for x in ['₽','руб','—','–']) or re.search(r'\d\s*000', line)) and re.search(self.FLAG_REGEX, line):
            return None
        if any(k in ll for k in ['оформление','менеджер','условия','отзывы','отправки','faq','http','t.me/','@']):
            return None
        # Header ends with colon
        if line.rstrip().endswith(':'):
            return line.strip()
        # Standard headers
        if re.match(r'(iphone|macbook|ipad|apple\s*watch|ps5|stайлеры|фены|беспроводные|проводные|прочие|моющие|airpods)\s*\S*\s*\d{0,2}', ll):
            return line.strip()
        # Samsung S series
        if re.match(r's\d{2}', ll):
            return line.strip()
        # Samsung A series (A07, A17, A36, A56, etc.)
        if re.match(r'a\d{2}', ll):
            return line.strip()
        return None
        if any(k in ll for k in ['оформление','менеджер','условия','отзывы','отправки','faq','http','t.me/','@']):
            return None
        # Header ends with colon
        if line.rstrip().endswith(':'):
            return line.strip()
        # Category headers without price
        if re.match(r'(iphone|macbook|ipad|apple\s*watch|ps5|stайлеры|фены|беспроводные|проводные|прочие|моющие|airpods)\s*\S*\s*\d{0,2}', ll) and not has_flag:
            return line.strip()
        if re.match(r's\d{2}', ll) and not has_flag:
            return line.strip()
        return None
    
    def _parse_line(self, ln, raw, hdr="", brand_context=None):
        ctx = f"{hdr} {ln}" if hdr else ln
        fl = self.extract_flag(ctx, self.FLAG_REGEX)
        if not fl:
            return None
        
        sim = self.COUNTRY_SIM.get(fl, 'unknown')
        if '/ds' in ctx.lower():
            sim = '2sim'
        
        prc = self.extract_price(ctx)
        if not prc:
            return None
        
        cat, br = self._categorize(ctx)
        
        # Если категория не найдена, но есть контекст бренда - используем его
        if not cat and brand_context:
            if brand_context == 'samsung':
                cat, br = 'smartphones', 'samsung'
            elif brand_context == 'apple':
                cat, br = 'smartphones', 'apple'
        
        if not cat:
            return None
        
        mod = self._model(ctx, cat, br)
        if not mod:
            return None
        
        attr = {}
        st = self.extract_storage(ctx)
        if st:
            attr['storage'] = st
        cl = self.extract_color(ctx)
        if cl:
            attr['color'] = cl
        if sim and cat not in ('accessories', 'laptops', 'tablets', 'consoles') and br not in ('dyson', 'sony'):
            attr['sim_type'] = sim
        
        h = hash(ln.strip()) & 0xffffffff
        return ParsedProduct(
            id=f"prod_{raw.id}_{h}_{int(datetime.utcnow().timestamp())}",
            category_id=cat, brand=br.lower(), model=mod, price=prc,
            source_channel=raw.channel_id, message_link=f"{raw.message_link}?line={h}",
            timestamp=raw.timestamp, attributes=attr, raw_message_id=raw.id
        )
    
    def _categorize(self, l):
        ll = l.lower()
        if 'dyson' in ll or re.search(r'\b(hs|hd|v)\d{2,3}', ll):
            return 'accessories', 'dyson'
        if 'ps5' in ll:
            return 'consoles', 'sony'
        if 'macbook' in ll:
            return 'laptops', 'apple'
        if 'ipad' in ll:
            return 'tablets', 'apple'
        if re.search(r'\b(s\d{2}\s*ultra|s\d{2}\+|s\d{2}|a0\d|a1\d|a2\d|a3\d|a5\d|z\s*(fold|flip)\s*\d)\b', ll):
            return 'smartphones', 'samsung'
        if 'apple watch' in ll or re.search(r'\b(se2|se3)\b', ll) or re.search(r's\d{1}\s*mm', ll) or re.search(r'watch\s+ultra\s*\d', ll) or (re.search(r'\bultra\s*\d', ll) and not re.search(r's\d{2}\s+ultra', ll)):
            return 'accessories', 'apple'
        if 'airpods' in ll:
            return 'accessories', 'apple'
        if re.search(r'iphone\s*\d+', ll) or re.search(r'\d{2}\s*pro\s*max|\d{2}\s*pro\s|17\s*air|17e|16e', ll) or re.search(r'\b(14|15|16|17)\s+\d{2,3}\s*gb', ll):
            return 'smartphones', 'apple'
        return None, ''
    
    def _model(self, l, cat, br):
        ll = l.lower()
        if br == 'dyson':
            m = re.search(r'(hs|hd|v)\s*(\d{2,3})', ll)
            return f"Dyson {m.group(1).upper()}{m.group(2)}" if m else "Dyson"
        if br == 'sony' and cat == 'consoles':
            if 'pro' in ll: return "PS5 Pro"
            if 'slim' in ll: return "PS5 Slim"
            if 'vr' in ll: return "PS5 VR2"
            return "PS5"
        if br == 'apple' and cat == 'accessories':
            if 'ultra' in ll:
                m = re.search(r'ultra\s*(\d)?', ll)
                return f"Apple Watch Ultra {m.group(1) if m else ''}".strip()
            if re.search(r'se\s*\d', ll):
                m = re.search(r'se\s*(\d)', ll)
                return f"Apple Watch SE {m.group(1) if m.group(1) else ''}".strip()
            if re.search(r's\d{2}', ll):
                m = re.search(r's(\d{2})', ll)
                return f"Apple Watch S{m.group(1) if m.group(1) else ''}"
            return "Apple Watch" if 'watch' in ll else "AirPods Max" if 'max' in ll else "AirPods Pro" if 'pro' in ll else "AirPods"
        if br == 'apple' and cat == 'smartphones':
            m = re.search(r'(17\s*pro\s*max|17\s*pro|17\s*air|17e|17|16\s*pro\s*max|16\s*pro|16e|16|15\s*pro\s*max|15\s*pro|15|14\s*plus|14|13)\s+(\d{2,3}\s*gb)?', ll)
            if m:
                md = m.group(1).strip().title()
                st = (m.group(2) or "").strip().upper()
                return f"iPhone {md} {st}".strip() if st else f"iPhone {md}"
        if br == 'samsung' and cat == 'smartphones':
            # Samsung S series
            m = re.search(r'(s2[0-9]\s*ultra|s2[0-9]\+|s2[0-9])', ll)
            if m:
                md = m.group(1).strip().upper().replace('S2', 'S2').replace(' ULTRA', ' Ultra').replace('+', ' Plus')
                return f"Samsung {md}"
            # Samsung A series (A07, A17, A36, A56, etc.)
            m = re.search(r'(a\d{2})\s+(\d+)/(\d+)', ll)  # A07 4/128
            if m:
                model_num = m.group(1).upper()
                return f"Samsung {model_num}"
            # Samsung Z Fold/Flip
            m = re.search(r'z\s*(fold|flip)\s*(\d)', ll)
            if m:
                return f"Samsung Z {m.group(1).capitalize()} {m.group(2)}"
            return "Samsung"
        if br == 'apple' and cat == 'laptops':
            m = re.search(r'macbook\s*(air|pro|neo)\s*(\d{0,2})?\s*\(?(m\d{1,2})\)?', ll)
            if m:
                tp = m.group(1).capitalize()
                sz = m.group(2) if m.group(2) else ""
                chip = m.group(3).upper()
                return f"MacBook {tp} {sz} {chip}".strip()
            return "MacBook"
        if br == 'apple' and cat == 'tablets':
            m = re.search(r'(ipad\s*(air|pro|mini)?)\s*(\d{2})?\s*(m[1-7])?\s*(\d{2,3}\s*gb)?', ll)
            if m:
                parts = [
                    "iPad",
                    m.group(2).capitalize() if m.group(2) else "",
                    m.group(3).upper() if m.group(3) else "",
                    (m.group(4) or "").strip().upper() if m.group(4) else ""
                ]
                return ' '.join(p for p in parts if p).strip()
            return "iPad"
        return "Unknown"
