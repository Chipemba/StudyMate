from fastapi import FastAPI, UploadFile, File, Form
from pathlib import Path
from pydantic import BaseModel

from backend.schemas import QueryRequest, QueryResponse
from backend.services.metadata_service import init_db, create_learning_session, list_learning_sessions

from backend.services.rag_service import (
    clean_collection_name,
    load_pdf_from_upload,
    create_vectorstore,
    query_collection,
    query_basic as query_basic_service,
)

from backend.services.generation_service import generate_study_asset, StudyMode

app = FastAPI(title="StudyMate API", version="1.0.0")

@app.on_event("startup")
def startup():
    Path("data/uploads").mkdir(parents=True, exist_ok=True)
    Path("db").mkdir(parents=True, exist_ok=True)
    init_db()
    
@app.get("/api/health")
def health():
    return {"status": "ok", 
            "service": "studymate"
            }

@app.post("/api/sessions")
def create_session(title: str = Form(...), description: str = Form("")):
    collection_name = clean_collection_name(title)
    return create_learning_session(title, description, collection_name)

@app.get("/api/sessions")
def get_sessions():
    return list_learning_sessions()

@app.post("/api/ingest/pdf")
async def ingest_pdf(
    file: UploadFile = File(...),
    collection_name: str = Form(...),
):
    safe_collection_name = clean_collection_name(collection_name or file.filename)

    documents = await load_pdf_from_upload(file)

    result = create_vectorstore(
        documents=documents,
        collection_name=safe_collection_name,
    )

    session_name = (
        file.filename
        .replace(".pdf", "")
        .replace("-", " ")
        .replace("_", " ")
        .title()
    )

    return {
        "message": "PDF ingested successfully.",
        "session_name": session_name,
        "collection_name": result["collection_name"],
        "chunk_count": result["chunk_count"],
        "provider": "openai",
    }

@app.post("/api/query", response_model=QueryResponse)
def query(req: QueryRequest):
    result = query_collection(
        collection_name=req.collection_name,
        question=req.question,
    )

    return QueryResponse(**result)


class BasicQueryRequest(BaseModel):
    question: str

@app.post("/api/query/basic")
def query_without_document(request: BasicQueryRequest):
    return query_basic_service(request.question)


@app.post("/api/generate/{mode}")
def generate_mode(mode: StudyMode, collection_name: str = Form(...)):
    return generate_study_asset(
        collection_name=collection_name,
        mode=mode.value,
    )