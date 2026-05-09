"""Data Normalizer Service - Standardizes product data before DB insertion"""
import re
from typing import Dict, List, Optional
from common.models import ParsedProduct

NO_SIM_CATEGORIES = {'accessories', 'tablets', 'laptops', 'computers', 'consoles'}
NO_SIM_BRANDS = {'dyson', 'sony'}
VALID_SIM_TYPES = {'esim', 'sim+esim', '2sim', 'dual-sim'}
STORAGE_RE = re.compile(r'(\d+)\s*(gb|tb|mb)', re.IGNORECASE)
COLOR_MAP = {
    'spacegray': 'space gray', 'spaceblack': 'space black', 'rosegold': 'rose gold',
    'skyblue': 'sky blue', 'midnightgreen': 'midnight green', 'olivegreen': 'olive',
    'graphitegray': 'graphite', 'lavander': 'lavender', 'mistblue': 'mist blue',
    'jetblack': 'jet black'
}


class NormalizerService:
    @staticmethod
    def normalize_product(product: ParsedProduct) -> ParsedProduct:
        """Normalize product attributes"""
        clean_attrs = {}
        for key, value in product.attributes.items():
            if key == 'sim_type':
                if product.category_id not in NO_SIM_CATEGORIES and product.brand not in NO_SIM_BRANDS:
                    if value in VALID_SIM_TYPES:
                        clean_attrs['sim_type'] = value
            elif key == 'storage':
                normalized = NormalizerService.normalize_storage(value)
                if normalized:
                    clean_attrs['storage'] = normalized
            elif key == 'color':
                normalized = NormalizerService._normalize_color(value)
                if normalized:
                    clean_attrs['color'] = normalized
            else:
                clean_attrs[key] = value
        
        product.attributes = clean_attrs
        product.model = NormalizerService._normalize_model(product.model, product.brand, product.category_id)
        return product
    
    @staticmethod
    def normalize_storage(storage: str) -> Optional[str]:
        """Normalize storage to standard format (e.g., '256GB', '1TB')"""
        if not storage:
            return None
        storage_upper = storage.upper().strip()
        if re.match(r'^\d+(GB|TB)$', storage_upper):
            return storage_upper
        match = STORAGE_RE.search(storage_upper)
        if match:
            value, unit = match.group(1), match.group(2).upper()
            if unit in {'GB', 'TB'}:
                return f"{value}{unit}"
        if storage.isdigit():
            return f"{storage}GB"
        return None
    
    @staticmethod
    def _normalize_color(color: str) -> Optional[str]:
        """Normalize color name"""
        if not color:
            return None
        color_lower = color.lower().strip()
        normalized = COLOR_MAP.get(color_lower, color)
        return normalized.title()
    
    @staticmethod
    def _normalize_model(model: str, brand: str, category_id: str) -> str:
        """Normalize model name"""
        if not model:
            return "Unknown"
        model = re.sub(r'\s*None\s*', ' ', model).strip()
        model = re.sub(r'\s+', ' ', model).strip()
        model = re.sub(r'[\s\-]+$', '', model)
        
        if brand.lower() == 'apple':
            model = re.sub(r'\biphone\b', 'iPhone', model, flags=re.IGNORECASE)
            model = re.sub(r'\bipad\b', 'iPad', model, flags=re.IGNORECASE)
            model = re.sub(r'\bmacbook\b', 'MacBook', model, flags=re.IGNORECASE)
            model = re.sub(r'\bairpods\b', 'AirPods', model, flags=re.IGNORECASE)
            model = re.sub(r'\bwatch\b', 'Watch', model, flags=re.IGNORECASE)
        elif brand.lower() == 'samsung':
            model = re.sub(r'\bs\d+\s*ultra\b', lambda m: m.group(0).upper().replace('ULTRA', 'Ultra'), model, flags=re.IGNORECASE)
            model = re.sub(r'\bs\d+\+\b', lambda m: m.group(0).upper(), model, flags=re.IGNORECASE)
        
        return model if model else "Unknown"
    
    @staticmethod
    def normalize_batch(products: List[ParsedProduct]) -> List[ParsedProduct]:
        """Normalize batch of products"""
        return [NormalizerService.normalize_product(p) for p in products]
    
    @staticmethod
    def validate_product(product: ParsedProduct) -> tuple:
        """Validate product data"""
        errors = []
        if not product.brand or not product.brand.strip():
            errors.append("Brand is required")
        if not product.model or not product.model.strip() or product.model == "Unknown":
            errors.append("Model is required")
        if not product.category_id or not product.category_id.strip():
            errors.append("Category is required")
        if not product.price or product.price <= 0:
            errors.append("Valid price is required")
        if product.category_id not in {'smartphones', 'tablets', 'laptops', 'computers', 'accessories', 'consoles'}:
            errors.append(f"Invalid category: {product.category_id}")
        if 'sim_type' in product.attributes and product.category_id in NO_SIM_CATEGORIES:
            errors.append(f"SIM type not valid for category: {product.category_id}")
        return len(errors) == 0, errors
