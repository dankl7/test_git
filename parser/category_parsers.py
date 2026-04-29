import re
from typing import List, Dict, Optional
from .base_parser import BaseParser


class SmartphoneParser(BaseParser):
    """Парсер для смартфонов (Apple, Samsung, Google, etc.)"""
    
    def parse_block(self, header: str, lines: List[str]) -> List[Dict]:
        products = []
        header_lower = header.lower()
        
        # Определяем бренд из заголовка
        brand = self._detect_brand(header_lower)
        
        for line in lines:
            if self._is_skip_line(line):
                continue
            
            product = self._parse_line(line, brand)
            if product:
                products.append(product)
        
        return products
    
    def _detect_brand(self, text: str) -> str:
        if 'samsung' in text or 'galaxy' in text:
            return 'Samsung'
        elif 'iphone' in text or 'apple' in text:
            return 'Apple'
        elif 'pixel' in text:
            return 'Google'
        elif 'poco' in text:
            return 'Poco'
        elif 'xiaomi' in text:
            return 'Xiaomi'
        elif 'honor' in text:
            return 'Honor'
        elif 'huawei' in text:
            return 'Huawei'
        return 'Unknown'
    
    def _parse_line(self, line: str, brand: str) -> Optional[Dict]:
        flag = self.extract_flag(line)
        price = self.extract_price(line)
        
        if not price or not flag:
            return None
        
        model = self._extract_model(line, brand)
        if not model:
            return None
        
        storage = self._extract_storage(line)
        color = self._extract_color(line)
        sim_type = self.get_sim_type(flag, 'smartphones')
        
        # Приоритет /DS для Samsung
        if brand == 'Samsung':
            if '/ds' in line.lower():
                sim_type = '2sim'
            elif flag == '🇨🇳':  # Китай
                sim_type = '2sim'
        
        attributes = {}
        if storage:
            attributes['storage'] = storage
        if color:
            attributes['color'] = color.title()
        if sim_type:
            attributes['sim_type'] = sim_type
        
        return {
            'brand': brand,
            'model': model,
            'price': price,
            'attributes': attributes
        }
    
    def _extract_model(self, line: str, brand: str) -> Optional[str]:
        line_lower = line.lower()
        
        if brand == 'Apple':
            # iPhone 17 Pro Max 256GB
            m = re.search(r'(iphone\s*(17|16|15|14|13)\s*(pro\s*max|pro|max|plus|e|air)?)', line_lower)
            if m:
                model = m.group(1).strip().title()
                return model.replace('Iphone', 'iPhone')
        
        elif brand == 'Samsung':
            # S25 Ultra, S24+, A56, Z Fold 6, Z Flip 5
            if re.search(r's2\d', line_lower):
                m = re.search(r'(s2\d\s*ultra|s2\d\+|s2\d)', line_lower)
                if m:
                    model = m.group(1).strip().upper()
                    return model.replace('S2', 'S2').replace('ULTRA', 'Ultra').replace('+', ' Plus')
            
            if re.search(r'a\d{2}', line_lower):
                m = re.search(r'(a\d{2})', line_lower)
                if m:
                    return f"Galaxy {m.group(1).upper()}"
            
            if 'z fold' in line_lower:
                m = re.search(r'z fold\s*\d', line_lower)
                if m:
                    return f"Z Fold {m.group(0).split()[-1]}"
            
            if 'z flip' in line_lower:
                m = re.search(r'z flip\s*\d', line_lower)
                if m:
                    return f"Z Flip {m.group(0).split()[-1]}"
        
        elif brand == 'Google':
            m = re.search(r'(pixel\s*\d\s*pro?)', line_lower)
            if m:
                return m.group(1).strip().title()
        
        elif brand == 'Poco':
            m = re.search(r'(poco\s*[a-z]?\s*\d+[a-z]?)', line_lower)
            if m:
                return m.group(1).strip().title()
        
        elif brand == 'Xiaomi':
            m = re.search(r'(redmi\s*note\s*\d+[a-z]?\s*pro?)', line_lower)
            if m:
                return m.group(1).strip().title()
        
        elif brand == 'Honor':
            m = re.search(r'(honor\s*[a-z]?\s*\d+[a-z]?)', line_lower)
            if m:
                return m.group(1).strip().title()
        
        return None
    
    def _extract_storage(self, line: str) -> Optional[str]:
        m = re.search(r'(\d{2,3})\s*gb', line, re.IGNORECASE)
        if m:
            return f"{m.group(1)}GB"
        m = re.search(r'(\d)\s*tb', line, re.IGNORECASE)
        if m:
            return f"{m.group(1)}TB"
        return None
    
    def _extract_color(self, line: str) -> Optional[str]:
        colors = [
            'black', 'white', 'blue', 'green', 'pink', 'red', 'yellow',
            'purple', 'gray', 'gold', 'silver', 'natural', 'titanium',
            'starlight', 'midnight', 'desert', 'cosmic', 'navy', 'olive',
            'lavender', 'phantom', 'graphite', 'cream', 'sky', 'mint'
        ]
        line_lower = line.lower()
        for c in colors:
            if c in line_lower:
                return c
        return None


class LaptopParser(BaseParser):
    """Парсер для ноутбуков (MacBook)"""
    
    def parse_block(self, header: str, lines: List[str]) -> List[Dict]:
        products = []
        
        for line in lines:
            if self._is_skip_line(line):
                continue
            
            flag = self.extract_flag(line)
            price = self.extract_price(line)
            
            if not price:
                continue
            
            model_data = self._parse_macbook(line)
            if not model_data:
                continue
            
            product = {
                'brand': 'Apple',
                'model': model_data['model'],
                'price': price,
                'attributes': {
                    'storage': model_data.get('storage'),
                    'color': model_data.get('color'),
                    'chip': model_data.get('chip'),
                    'ram': model_data.get('ram')
                }
            }
            
            # Очистка None значений
            product['attributes'] = {k: v for k, v in product['attributes'].items() if v}
            products.append(product)
        
        return products
    
    def _parse_macbook(self, line: str) -> Optional[Dict]:
        line_lower = line.lower()
        
        # MacBook Air/Pro/Neo 13/15 M1/M2/M3/M4
        m = re.search(r'macbook\s*(air|pro|neo)\s*(\d{0,2})?\s*\(?(m\d{1,2})\)?', line_lower)
        if m:
            type_map = {'air': 'Air', 'pro': 'Pro', 'neo': 'Neo'}
            mb_type = type_map.get(m.group(1), '')
            size = m.group(2) if m.group(2) else ""
            chip = m.group(3).upper()
            
            model_name = f"MacBook {mb_type}"
            if size:
                model_name += f" {size}"
            model_name += f" {chip}"
            
            storage = self._extract_storage(line)
            color = self._extract_color(line)
            
            return {
                'model': model_name.strip(),
                'storage': storage,
                'color': color.title() if color else None,
                'chip': chip.upper(),
                'ram': None  # Сложно определить без контекста
            }
        
        return None
    
    def _extract_storage(self, line: str) -> Optional[str]:
        m = re.search(r'(\d{2,3})\s*gb', line, re.IGNORECASE)
        if m:
            return f"{m.group(1)}GB"
        m = re.search(r'(\d)\s*tb', line, re.IGNORECASE)
        if m:
            return f"{m.group(1)}TB"
        return None
    
    def _extract_color(self, line: str) -> Optional[str]:
        colors = ['black', 'white', 'blue', 'pink', 'green', 'gray', 'gold', 
                  'silver', 'natural', 'starlight', 'midnight', 'desert', 'cosmic']
        line_lower = line.lower()
        for c in colors:
            if c in line_lower:
                return c
        return None


class TabletParser(BaseParser):
    """Парсер для планшетов (iPad)"""
    
    def parse_block(self, header: str, lines: List[str]) -> List[Dict]:
        products = []
        
        for line in lines:
            if self._is_skip_line(line):
                continue
            
            flag = self.extract_flag(line)
            price = self.extract_price(line)
            
            if not price or not flag:
                continue
            
            model = self._parse_ipad(line)
            if model:
                products.append({
                    'brand': 'Apple',
                    'model': model,
                    'price': price,
                    'attributes': {}
                })
        
        return products
    
    def _parse_ipad(self, line: str) -> Optional[str]:
        line_lower = line.lower()
        
        # iPad Air M2, iPad Pro 11, iPad 10
        m = re.search(r'ipad\s*(air|pro|mini)?\s*(\d{0,2})?\s*(m\d{1,2})?', line_lower)
        if m:
            suffix = m.group(1).capitalize() if m.group(1) else ""
            ver = m.group(2) if m.group(2) else ""
            chip = m.group(3).upper() if m.group(3) else ""
            
            res = "iPad"
            if suffix:
                res += f" {suffix}"
            if ver:
                res += f" {ver}"
            if chip:
                res += f" {chip}"
            return res
        
        return None


class ConsoleParser(BaseParser):
    """Парсер для консолей (PS5, Xbox)"""
    
    def parse_block(self, header: str, lines: List[str]) -> List[Dict]:
        products = []
        
        for line in lines:
            if self._is_skip_line(line):
                continue
            
            price = self.extract_price(line)
            if not price:
                continue
            
            model = self._parse_console(line)
            if model:
                brand = 'Sony' if 'ps' in line.lower() else 'Microsoft'
                products.append({
                    'brand': brand,
                    'model': model,
                    'price': price,
                    'attributes': {}
                })
        
        return products
    
    def _parse_console(self, line: str) -> Optional[str]:
        line_lower = line.lower()
        
        if 'ps5' in line_lower:
            if 'pro' in line_lower:
                return "PS5 Pro"
            if 'slim' in line_lower:
                return "PS5 Slim"
            if 'digital' in line_lower:
                return "PS5 Digital Edition"
            return "PS5"
        
        if 'xbox' in line_lower:
            if 'series x' in line_lower:
                return "Xbox Series X"
            if 'series s' in line_lower:
                return "Xbox Series S"
        
        return None


class AccessoryParser(BaseParser):
    """Парсер для аксессуаров (AirPods, Watch, Dyson)"""
    
    def parse_block(self, header: str, lines: List[str]) -> List[Dict]:
        products = []
        header_lower = header.lower()
        
        brand = self._detect_brand(header_lower)
        
        for line in lines:
            if self._is_skip_line(line):
                continue
            
            flag = self.extract_flag(line)
            price = self.extract_price(line)
            
            if not price or not flag:
                continue
            
            model = self._parse_item(line, brand)
            if model:
                attrs = {}
                if brand == 'Dyson':
                    color = self._extract_color(line)
                    if color:
                        attrs['color'] = color.title()
                
                products.append({
                    'brand': brand,
                    'model': model,
                    'price': price,
                    'attributes': attrs
                })
        
        return products
    
    def _detect_brand(self, header: str) -> str:
        if 'dyson' in header:
            return 'Dyson'
        elif 'airpods' in header or 'watch' in header or 'apple' in header:
            return 'Apple'
        return 'Unknown'
    
    def _parse_item(self, line: str, brand: str) -> Optional[str]:
        line_lower = line.lower()
        
        if brand == 'Dyson':
            m = re.search(r'(hs|hd|v)\s*(\d{2,3})', line_lower)
            if m:
                return f"Dyson {m.group(1).upper()}{m.group(2)}"
        
        elif brand == 'Apple':
            if 'airpods' in line_lower:
                if 'max' in line_lower:
                    return "AirPods Max"
                if 'pro 2' in line_lower:
                    return "AirPods Pro 2"
                if 'pro' in line_lower:
                    return "AirPods Pro"
                return "AirPods"
            
            if 'watch' in line_lower:
                if 'ultra' in line_lower:
                    m = re.search(r'ultra\s*(\d)?', line_lower)
                    return f"Apple Watch Ultra {m.group(1) if m else '2'}"
                if 'se' in line_lower:
                    m = re.search(r'se\s*(\d)?', line_lower)
                    return f"Apple Watch SE {m.group(1) if m else '2'}"
                if re.search(r's\d{2}', line_lower):
                    m = re.search(r's(\d{2})', line_lower)
                    return f"Apple Watch S{m.group(1)}"
        
        return None
    
    def _extract_color(self, line: str) -> Optional[str]:
        colors = ['black', 'white', 'blue', 'pink', 'green', 'red', 'yellow',
                  'purple', 'gray', 'gold', 'silver', 'nickel', 'copper']
        line_lower = line.lower()
        for c in colors:
            if c in line_lower:
                return c
        return None
