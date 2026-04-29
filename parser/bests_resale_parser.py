"""Bests re:sale optimized block parser"""
import re
from datetime import datetime
from typing import List
from common.models import RawMessage, ParsedProduct
from .base_parser import BaseBlockParser


class BestsResaleParser(BaseBlockParser):
    FLAG_REGEX = f"({'|'.join(k for k in BaseBlockParser.COUNTRY_SIM.keys())})"
    
    def parse(self, raw: RawMessage) -> List[ParsedProduct]:
        text = raw.text.strip()
        products = []
        blocks = self._split_blocks(text)
        for hdr, lines in blocks:
            for ln in lines:
                if self._skip_line(ln) or self._is_asis(ln) or self._is_refurbished(ln):
                    continue
                p = self._parse_line(ln, raw, hdr)
                if p:
                    products.append(p)
        return products
    
    def _is_asis(self, t):
        return t and ('(ASIS)' in t.upper() or '(ASIS+)' in t.upper())
    
    def _is_refurbished(self, t):
        return t and ('refurbished' in t.lower() or 'восстановлен' in t.lower())
    
    def _skip_line(self, l):
        return not l.strip() or len(l.strip()) < 5 or any(
            x in l.lower() for x in ['оформление','менеджер','условия','отзывы','отправки','faq','http','t.me/','@']
        )
    
    def _split_blocks(self, text):
        return self.split_blocks(text, self._parse_header)
    
    def _parse_header(self, line):
        ll = line.lower()
        # Skip if has price and flag - it's a product line
        if (any(x in line for x in ['₽','руб','—','–']) or re.search(r'\d\s*000', line)) and re.search(self.FLAG_REGEX, line):
            return None
        if any(k in ll for k in ['оформление','менеджер','условия','отзывы','отправки','faq','http','t.me/','@']):
            return None
        
        # Extract text after "Bests re:sale: " if present
        if 'bests re:sale:' in ll:
            match = re.search(r'bests re:sale:\s*(.+)$', ll)
            if match:
                extracted = match.group(1).strip()
                # Check if extracted text matches patterns
                patterns = [
                    r'iphone', r'ipad', r'macbook', r'apple\s*watch', r'airpods',
                    r'galaxy', r's\d{2}', r'a\d{2}', r'z\s*(fold|flip)',
                    r'poco', r'xiaomi', r'dyson', r'pixel', r'honor', r'huawei',
                    r'playstation', r'ps5', r'xbox', r'nintendo', r'oculus', r'steam deck',
                    r'яндекс\s*станция', r'аксессуары'
                ]
                for p in patterns:
                    if re.match(p, extracted):
                        return line.strip()
                return None
        return None
    
    def _parse_line(self, ln, raw, hdr):
        fl = self.extract_flag(ln, self.FLAG_REGEX)
        if not fl:
            return None
        
        sim = self.COUNTRY_SIM.get(fl, 'unknown')
        prc = self.extract_price(ln)
        if not prc:
            return None
        
        cat, br, mod = self._model(ln, hdr)
        if not mod:
            return None
        
        attr = {}
        st = self.extract_storage(ln)
        if st:
            attr['storage'] = st
        cl = self.extract_color(ln)
        if cl:
            attr['color'] = cl
        if sim and cat not in ('accessories', 'laptops', 'tablets', 'consoles') and br not in ('dyson', 'sony'):
            attr['sim_type'] = sim
        
        h = hash(ln.strip()) & 0xffffffff
        return ParsedProduct(
            id=f"best_{raw.id}_{h}",
            category_id=cat, brand=br.lower(), model=mod, price=prc,
            source_channel=raw.channel_id, message_link=f"{raw.message_link}?line={h}",
            timestamp=raw.timestamp, attributes=attr, raw_message_id=raw.id
        )
    
    def _model(self, ln, hdr):
        full = f"{hdr} {ln}".strip().lower()
        
        # iPhone
        if re.search(r'iphone\s*\d', full) or re.search(r'\d{2}\s*pro\s*max|\d{2}\s*pro\s|17\s*air|17e|16e', full):
            m = re.search(r'(17\s*pro\s*max|17\s*pro|17\s*air|17e|17|16\s*pro\s*max|16\s*pro|16e|16|15\s*pro\s*max|15\s*pro|15|14\s*plus|14|13|12|11)\s+(\d{2,3}gb)?', full)
            if m:
                md = m.group(1).strip().title()
                st = m.group(2).strip().upper() if m.group(2) else ""
                return 'smartphones', 'apple', f"iPhone {md} {st}".strip()
        
        # Samsung S
        if re.search(r'\bs\d{2}\s*ultra|\bs\d{2}\+|\bs\d{2}\s', full):
            m = re.search(r'(s2[0-9]\s*ultra|s2[0-9]\+|s2[0-9])\s+(\d+/\d+gb)?', full)
            if m:
                md = m.group(1).strip().upper().replace(' ULTRA', ' Ultra').replace('+', ' Plus')
                return 'smartphones', 'samsung', f"Samsung {md}"
        
        # Samsung A
        if re.search(r'\ba\d{2}\s', full) and ('galaxy' in full or re.search(r'\ba\d{2}\s+\d+/\d+', full)):
            m = re.search(r'(a\d{2})\s+(\d+/\d+gb)?', full)
            if m:
                return 'smartphones', 'samsung', f"Samsung {m.group(1).strip().upper()}"
        
        # Samsung Z
        if re.search(r'z\s*(fold|flip)\s*\d', full):
            m = re.search(r'z\s*(fold|flip)\s*(\d)', full)
            if m:
                return 'smartphones', 'samsung', f"Samsung Z {m.group(1).title()} {m.group(2)}"
        
        # iPad
        if 'ipad' in full:
            m = re.search(r'ipad\s*(air|pro|mini)?\s*(\d{0,2})?\s*(m\d{1,2})?\s*(\d{2,3}gb)?', full)
            if m:
                tp = m.group(1).capitalize() if m.group(1) else ""
                sz = m.group(2) or ""
                chip = m.group(3).upper() if m.group(3) else ""
                return 'tablets', 'apple', f"iPad {tp} {sz} {chip}".strip()
        
        # MacBook
        if 'macbook' in full:
            for pattern in [r'macbook\s*(air|pro|neo)\s*(\d{0,2})?\s*\(?(m\d{1,2})[^—–-]*?(\d+)/(\d+)', r'(air|pro|neo)\s*(\d{0,2})?\s*\(?(m\d{1,2})[^—–-]*?(\d+)/(\d+)']:
                m = re.search(pattern, full)
                if m:
                    tp = m.group(1).capitalize()
                    sz = m.group(2) or ""
                    chip = m.group(3).upper()
                    return 'laptops', 'apple', f"MacBook {tp} {sz} {chip} {m.group(4)}/{m.group(5)}GB"
        
        # Apple Watch
        if 'apple watch' in full or re.search(r'\b(se2|se3|s\d{2}|ultra\s*\d)\b', full):
            if 'ultra' in full:
                m = re.search(r'ultra\s*(\d)?', full)
                return 'accessories', 'apple', f"Apple Watch Ultra {m.group(1) if m else ''}".strip()
            if re.search(r'se\s*\d', full):
                m = re.search(r'se\s*(\d)', full)
                return 'accessories', 'apple', f"Apple Watch SE {m.group(1) if m.group(1) else ''}".strip()
            if re.search(r's\d{2}', full):
                m = re.search(r's(\d{2})', full)
                return 'accessories', 'apple', f"Apple Watch S{m.group(1) if m.group(1) else ''}"
            return 'accessories', 'apple', 'Apple Watch'
        
        # AirPods
        if 'airpods' in full:
            if 'max' in full: return 'accessories', 'apple', 'AirPods Max'
            if 'pro' in full:
                m = re.search(r'pro\s*(\d+)?', full)
                v = m.group(1) if m and m.group(1) else ""
                return 'accessories', 'apple', f"AirPods Pro {v}".strip() if v else 'AirPods Pro'
            m = re.search(r'airpods\s*(\d+)?', full)
            v = m.group(1) if m and m.group(1) else ""
            return 'accessories', 'apple', f"AirPods {v}".strip() if v else 'AirPods'
        
        # Dyson
        if 'dyson' in full or re.search(r'\b(hs|hd|ht|v)\d{2,3}', full):
            m = re.search(r'(hs|hd|ht|v)\s*(\d{2,3})', full)
            if m:
                return 'accessories', 'dyson', f"Dyson {m.group(1).upper()}{m.group(2)}"
            return 'accessories', 'dyson', 'Dyson'
        
        # PS5
        if 'ps5' in full:
            if 'pro' in full: return 'consoles', 'sony', 'PS5 Pro'
            if 'slim' in full:
                if 'digital' in full: return 'consoles', 'sony', 'PS5 Slim Digital Edition'
                return 'consoles', 'sony', 'PS5 Slim'
            return 'consoles', 'sony', 'PS5'
        
        # Pixel
        if 'pixel' in full:
            m = re.search(r'pixel\s*(\d{0,2})\s*(pro\s*max|pro|xl|a)?', full)
            if m:
                return 'smartphones', 'google', f"Pixel {m.group(1)}{m.group(2).replace(' ','').title() if m.group(2) else ''}".strip()
        
        # POCO/Xiaomi
        if 'poco' in full:
            m = re.search(r'poco\s*(\w*\d\w*)\s*(pro|ultra)?', full)
            if m:
                return 'smartphones', 'poco', f"Poco {m.group(1).upper()}{m.group(2).title() if m.group(2) else ''}".strip()
        if 'xiaomi' in full:
            m = re.search(r'xiaomi\s*(\w*\d\w*)\s*(pro|ultra)?', full)
            if m:
                return 'smartphones', 'xiaomi', f"Xiaomi {m.group(1).upper()}{m.group(2).title() if m.group(2) else ''}".strip()
        
        # Honor
        if 'honor' in full:
            m = re.search(r'honor\s*(\w*\d\w*)\s*(pro|lite)?', full)
            if m:
                return 'smartphones', 'honor', f"Honor {m.group(1).title()}{m.group(2).title() if m.group(2) else ''}".strip()
        
        # Huawei
        if 'huawei' in full:
            if re.search(r'huawei\s*nova', full):
                m = re.search(r'huawei\s*nova\s*(\d{0,2}i?)\s*(\d+/\d+gb)?', full)
                if m:
                    return 'smartphones', 'huawei', f"Huawei Nova {m.group(1)}".strip()
            m = re.search(r'huawei\s*(\w*\d\w*)\s*(pro|ultra|lite)?', full)
            if m:
                return 'smartphones', 'huawei', f"Huawei {m.group(1).title()}{m.group(2).title() if m.group(2) else ''}".strip()
        
        # Yandex
        if ('яндекс' in full or 'yandex' in full) and 'станция' in full:
            return 'accessories', 'yandex', 'Yandex Station'
        
        return '', '', ''
