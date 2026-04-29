"""Products API endpoints"""
import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

from common.database import get_db
from common.models import SearchCriteria
from storage.repository import ProductRepository, CategoryRepository

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["products"])


class ProductCreate(BaseModel):
    category_id: str
    brand: str
    model: str
    price: float
    source_channel: str
    message_link: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    attributes: Dict[str, Any] = Field(default_factory=dict)
    raw_message_id: Optional[str] = None


class ProductResponse(BaseModel):
    id: str
    category_id: str
    brand: str
    model: str
    price: float
    source_channel: str
    message_link: str
    timestamp: datetime
    attributes: Dict[str, Any]


@router.get("/products/{product_id}", response_model=ProductResponse)
async def get_product(product_id: str, db: Session = Depends(get_db)):
    """Get product by ID"""
    repo = ProductRepository(db)
    product = await repo.get(product_id)

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    return ProductResponse(
        id=product.id,
        category_id=product.category_id,
        brand=product.brand,
        model=product.model,
        price=product.price,
        source_channel=product.source_channel,
        message_link=product.message_link,
        timestamp=product.timestamp,
        attributes=product.attributes or {}
    )


@router.post("/products/search")
async def search_products(
    category_id: Optional[str] = None,
    brand: Optional[str] = None,
    model: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """Search products by criteria"""
    repo = ProductRepository(db)

    criteria = SearchCriteria(
        category_id=category_id,
        brand=brand,
        model=model,
        min_price=min_price,
        max_price=max_price,
        limit=limit,
        offset=offset
    )

    products = await repo.search(criteria)

    return {
        "count": len(products),
        "offset": offset,
        "limit": limit,
        "products": [
            ProductResponse(
                id=p.id,
                category_id=p.category_id,
                brand=p.brand,
                model=p.model,
                price=p.price,
                source_channel=p.source_channel,
                message_link=p.message_link,
                timestamp=p.timestamp,
                attributes=p.attributes or {}
            ) for p in products
        ]
    }


@router.get("/categories")
async def get_categories(db: Session = Depends(get_db)):
    """Get all active categories"""
    repo = CategoryRepository(db)
    categories = await repo.get_all()

    return [
        {
            "id": c.id,
            "name": c.name,
            "parent_id": c.parent_id,
            "attributes": c.attributes or [],
            "keywords": c.keywords or [],
            "is_active": c.is_active
        }
        for c in categories
    ]
