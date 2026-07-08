from enum import Enum
from pydantic import BaseModel, Field
from backend.services.rag_service import load_vectorstore, format_docs, get_chat_model


class StudyMode(str, Enum):
    faq = "faq"
    notes = "notes"
    quiz = "quiz"
    flashcards = "flashcards"
    glossary = "glossary"
    
class GeneratedStudyAsset(BaseModel):
    mode: str
    title: str
    content_markdown: str
    source_basis: str = Field(description="Short explanation of what retrieved material shaped the output")
    

def get_mode_prompt(mode: StudyMode) -> str:
    instructions = { 
        StudyMode.faq: "Create 10 practical learner FAQs with answers.",
        StudyMode.notes: "Create hierarchical Markdown study notes with headings and bullets.",
        StudyMode.quiz: "Create 10 quiz questions with answers and explanations.",
        StudyMode.flashcards: "Create 5 flashcards in Q/A format.",
        StudyMode.glossary: "Create a glossary of important terms with concise definitions.", 
        }
    return f"""
    You are StudyMate. Use only the retrieved context.
    Task: {instructions[mode]}
    
    Context:{{context}}
    
    Return a title, content_markdown and source_basis.
    """


MODE_PROMPTS = {
    "faq": """
    Create 6 frequently asked questions and answers from the retrieved course content.
    Keep answers concise but useful.
    """,

    "notes": """
    Create organized study notes from the retrieved course content.
    Use headings, bullets, and short explanations.
    """,

    "quiz": """
    Create 8 quiz questions from the retrieved course content.
    Include answers after each question.
    Mix multiple choice and short answer questions.
    """,

    "flashcards": """
    Create 10 flashcards from the retrieved course content.
    Format each as:
    Front:
    Back:
    """,

    "glossary": """
    Create a glossary of key terms from the retrieved course content.
    Format each term with a plain-language definition.
    """,
}


def mock_study_asset(mode: str):
    """
    Fallback response used when OpenAI is unavailable or the API key is missing.
    This keeps the portfolio demo from crashing.
    """

    return {
        "mode": mode,
        "title": f"Demo {mode.title()} Output",
        "content_markdown": (
            f"## Demo {mode.title()} Output\n\n"
            "This is mock content shown because the OpenAI service is unavailable.\n\n"
            "The backend route is working, but the real model call failed."
        ),
        "source_basis": "Mock fallback for demo stability.",
    }


def generate_study_asset(collection_name: str, mode: str):
    """
    Generates a study asset for the active session.

    This function:
    1. Loads the session's Chroma collection.
    2. Retrieves representative document chunks.
    3. Sends those chunks to ChatOpenAI.
    4. Returns markdown for Streamlit to display.
    """

    if mode not in MODE_PROMPTS:
        raise ValueError(f"Unsupported mode: {mode}")

    try:
        vectorstore = load_vectorstore(collection_name)
        retriever = vectorstore.as_retriever(search_kwargs={"k": 6})

        docs = retriever.invoke(
            "important concepts definitions examples summary"
        )

        context = format_docs(docs)

        prompt = f"""
        You are StudyMate, an AI study material generator.

        Use only this retrieved content:
        {context}

        Task:
        {MODE_PROMPTS[mode]}

        Return clean markdown.
        """

        llm = get_chat_model()
        response = llm.invoke(prompt)

        return {
            "mode": mode,
            "title": f"Generated {mode.title()}",
            "content_markdown": response.content,
            "source_basis": f"Generated from Chroma collection: {collection_name}",
        }

    except Exception as e:
        print(f"Study asset generation failed for mode={mode}: {e}")
        return mock_study_asset(mode)