from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field
from pydantic import BaseModel

class LearningSession(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    description: str = ""
    collection_name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    
class DocumentRecord(SQLModel, table=True): 
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int 
    filename: str
    source_type: str
    source_url: str | None = None
    chunk_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    

class QueryRequest(BaseModel):
    collection_name: str
    question: str
    
class QueryResponse(BaseModel):
    answer: str
    source_excerpt: str
    reasoning: str