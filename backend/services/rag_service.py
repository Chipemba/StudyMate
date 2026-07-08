import os
import re
import tempfile
import uuid

from fastapi import UploadFile
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_chroma import Chroma
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough

from backend.settings import settings, require_openai_key

from pydantic import BaseModel

RAG_PROMPT = """
You are StudyMate, an AI tutor for document based studying.

Use only the retrieved context to answer the student's question.
If the answer is not in the context, say:
"I do not know based on the uploaded document."

Do not invent or come up with facts.

Context:
{context}

Question:
{question}

Return:
1. A clear answer
2. A short source excerpt
3. Brief reasoning
"""


def clean_collection_name(name: str) -> str:
    """
    Converts a file name into a safe
    Chroma collection name.

    Example:
        "Python Basics.pdf" -> "python-basics"

    This name connects:
    - the uploaded PDF session
    - the Chroma vector collection
    - the tutor query endpoint
    - the study mode generator endpoint
    """

    name = os.path.splitext(name)[0]
    name = name.lower()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    name = name.strip("-")
    return name or "uploaded-document"


def get_embedding_function():
    """
    Creates the OpenAI embedding function used by ChromaDB.
    The API key is loaded from .env through backend/settings.py.
    """

    api_key = require_openai_key()

    return OpenAIEmbeddings(
        model=settings.OPENAI_EMBEDDING_MODEL,
        api_key=api_key,
    )


def get_chat_model():
    """
    Creates the OpenAI chat model used for:
    - document-grounded tutor mode
    - FAQ generation
    - notes generation
    - quiz generation
    - flashcard generation
    - glossary generation
    """

    api_key = require_openai_key()

    return ChatOpenAI(
        model=settings.OPENAI_CHAT_MODEL,
        api_key=api_key,
        temperature=0.2,
    )


async def load_pdf_from_upload(file: UploadFile):
    """
    Saves an uploaded PDF temporarily and loads it into LangChain documents.
    
    FastAPI UploadFile cannot be passed directly into PyPDFLoader because
    PyPDFLoader expects a file path. So this function writes the upload to
    a temporary file, loads it, then deletes the temp file.
    """

    temp_path = None

    try:
        contents = await file.read()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file.write(contents)
            temp_path = temp_file.name

        loader = PyPDFLoader(temp_path)
        documents = loader.load()

        return documents

    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def split_documents(documents):
    """
    Splits loaded PDF pages into smaller chunks.

    Chunks are needed because embedding models and LLM prompts work better
    when documents are broken into searchable sections.
    """

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len,
        separators=["\n\n", "\n", " "],
    )

    return splitter.split_documents(documents)


def create_vectorstore(documents, collection_name: str):
    """
    Creates and persists a Chroma vector database collection.

    This is called after a PDF is successfully uploaded.
    The collection_name becomes the backend identity of that study session.
    """

    chunks = split_documents(documents)
    embeddings = get_embedding_function()

    ids = [
        str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk.page_content))
        for chunk in chunks
    ]

    unique_ids = set()
    unique_chunks = []
    unique_chunk_ids = []

    for chunk, chunk_id in zip(chunks, ids):
        if chunk_id not in unique_ids:
            unique_ids.add(chunk_id)
            unique_chunks.append(chunk)
            unique_chunk_ids.append(chunk_id)

    vectorstore = Chroma.from_documents(
        documents=unique_chunks,
        embedding=embeddings,
        collection_name=collection_name,
        ids=unique_chunk_ids,
        persist_directory=settings.CHROMA_DB_DIR,
    )

    return {
        "collection_name": collection_name,
        "chunk_count": len(unique_chunks),
    }


def load_vectorstore(collection_name: str):
    """
    Loads an existing Chroma collection for a session.

    This is used by:
    - /api/query
    - /api/generate/{mode}
    """

    embeddings = get_embedding_function()

    return Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory=settings.CHROMA_DB_DIR,
    )


def format_docs(docs):
    """
    Converts retrieved LangChain Document objects into plain text for the prompt.
    """

    return "\n\n".join(doc.page_content for doc in docs)


def query_collection(collection_name: str, question: str):
    """
    Answers a user question using the uploaded document session.

    Flow:
        collection_name
        -> load Chroma collection
        -> retrieve relevant chunks
        -> send chunks + question to ChatOpenAI
        -> return answer, source excerpt, and reasoning
    """

    vectorstore = load_vectorstore(collection_name)
    retriever = vectorstore.as_retriever(search_type="similarity", search_kwargs={"k": 4})

    prompt = ChatPromptTemplate.from_template(RAG_PROMPT)
    llm = get_chat_model()

    rag_chain = (
        {
            "context": retriever | format_docs,
            "question": RunnablePassthrough(),
        }
        | prompt
        | llm
    )

    response = rag_chain.invoke(question)

    # Also retrieve one source excerpt for display.
    source_docs = retriever.invoke(question)
    source_excerpt = source_docs[0].page_content[:800] if source_docs else ""

    return {
        "answer": response.content,
        "source_excerpt": source_excerpt,
        "reasoning": "The answer was generated from the most relevant retrieved chunks in the active session collection.",
    }


def query_basic(question: str):
    """
    Generic tutor mode.

    This is used before any PDF has been uploaded.
    It does not use ChromaDB or document retrieval.
    """

    llm = get_chat_model()

    prompt = f"""
    You are StudyMate, a helpful AI tutor.

    The student has not uploaded a document yet, so answer using general
    educational knowledge. Be clear, beginner-friendly, and structured.

    Question:
    {question}
    """

    response = llm.invoke(prompt)

    return {
        "answer": response.content,
        "mode": "basic",
        "source_excerpt": None,
        "reasoning": "Generic tutor response generated without document context.",
    }