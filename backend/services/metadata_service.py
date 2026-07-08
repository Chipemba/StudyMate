from sqlmodel import SQLModel, Session, create_engine, select
from backend.schemas import LearningSession, DocumentRecord

DATABASE_URL = "sqlite:///db/studystore.db"
engine = create_engine(DATABASE_URL, echo=False)


def init_db():
    SQLModel.metadata.create_all(engine)
    
def create_learning_session(title: str, description:str, collection_name: str):
    with Session(engine) as session:
        item = LearningSession(title=title, description=description, collection_name=collection_name)
        session.add(item)
        session.commit()
        session.refresh(item)
        return item
    
def list_learning_sessions():
    with Session(engine) as session:
        return session.exec(select(LearningSession).order_by(LearningSession.created_at.desc())).all()
    
def add_document_record(session_id: int, filename: str, source_type: str, source_url: str | None, chunk_count: int):
    with Session(engine) as session:
        item = DocumentRecord( 
            session_id=session_id,
            filename=filename,
            source_type=source_type,
            source_url=source_url,
            chunk_count=chunk_count, 
            )
        session.add(item)
        session.commit()
        session.refresh(item)
        return item