from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api_types import SearchResponse, SearchResult
from app.db import TENANT_DB
from app.embeddings import Embedder, get_embedder
from app.search import vector_search

router = APIRouter(prefix="/search", tags=["search"])

MAX_K = 50


@router.get("", response_model=SearchResponse)
def search(
    q: str = Query(min_length=1, max_length=1000, description="The question, in plain words"),
    k: int = Query(5, ge=1, le=MAX_K, description="How many records to return"),
    embedder: Embedder = Depends(get_embedder),
    db: Session = TENANT_DB,
) -> SearchResponse:
    hits = vector_search(db, embedder, q, k)
    return SearchResponse(results=[SearchResult.model_validate(hit) for hit in hits])
