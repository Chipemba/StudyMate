import os
import re
import requests
import streamlit as st
from dotenv import load_dotenv


# =========================================================
# Environment setup
# =========================================================
# Streamlit should NOT load or use OPENAI_API_KEY directly.
# The OpenAI key belongs only in the FastAPI backend.
#
# Streamlit only needs to know where the backend API is.
load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")


# =========================================================
# Page configuration
# =========================================================
st.set_page_config(
    page_title="StudyMate",
    page_icon="📚",
    layout="wide",
)

st.title("📚 StudyMate Studying Platform")
st.caption(
    "Turn PDFs into FAQs, notes, quizzes, flashcards, glossary terms, "
    "and source-grounded AI study material."
)


# =========================================================
# Session state initialization
# =========================================================
if "sessions" not in st.session_state:
    # Stores all uploaded and successfully ingested study sessions.
    #
    # Example:
    # {
    #   "Python Basics": {
    #       "collection_name": "python-basics",
    #       "file_name": "python-basics.pdf",
    #       "messages": [],
    #       "study_assets": {
    #           "faq": "...",
    #           "quiz": "..."
    #       }
    #   }
    # }
    st.session_state.sessions = {}

if "active_session" not in st.session_state:
    # None means no uploaded document session is active.
    # When this is None, the app runs in generic tutor mode.
    st.session_state.active_session = None

if "general_messages" not in st.session_state:
    # Chat history for the generic tutor.
    # This is used before the user uploads and ingests a PDF.
    st.session_state.general_messages = []

if "backend_status" not in st.session_state:
    # Stores whether the backend health check passed.
    st.session_state.backend_status = None


# =========================================================
# Helper functions
# =========================================================
def make_collection_name(filename: str) -> str:
    """
    Converts an uploaded file name into a clean Chroma collection name.

    The collection name is the backend identifier for a study session.
    It connects the uploaded PDF to:
    - document ingestion
    - vector database storage
    - document-grounded tutor questions
    - generated study modes

    Example:
        "Python Basics Intro.pdf" -> "python-basics-intro"
    """

    name_without_extension = os.path.splitext(filename)[0]
    clean_name = name_without_extension.lower()
    clean_name = re.sub(r"[^a-z0-9]+", "-", clean_name)
    clean_name = clean_name.strip("-")

    return clean_name or "uploaded-document"


def make_session_name(filename: str) -> str:
    """
    Creates a readable session name from the uploaded file name.
    This is what the user sees in the left-side session panel.
    Example:
        "python_basics_intro.pdf" -> "Python Basics Intro"
    """

    name_without_extension = os.path.splitext(filename)[0]
    readable_name = name_without_extension.replace("_", " ").replace("-", " ")
    readable_name = re.sub(r"\s+", " ", readable_name).strip()

    return readable_name.title() or "Uploaded Document"


def get_current_session():
    """
    Returns the active study session dictionary.

    If no session has been created or selected, returns None.
    """

    active_session_name = st.session_state.active_session

    if active_session_name is None:
        return None

    return st.session_state.sessions.get(active_session_name)


def check_backend_health():
    """
    Calls the FastAPI health endpoint to confirm the backend is running.

    This helps the user quickly understand whether failures are caused by
    the frontend or the backend not being started.
    """

    try:
        response = requests.get(
            f"{API_BASE_URL}/api/health",
            timeout=5,
        )

        if response.status_code == 200:
            return True, response.json()

        return False, {"error": response.text}

    except requests.exceptions.RequestException as error:
        return False, {"error": str(error)}


def call_basic_tutor(question: str):
    """
    Calls the backend generic tutor endpoint.

    This endpoint does not use a PDF, vector database, or collection_name.
    It is available before any study session exists.
    """

    response = requests.post(
        f"{API_BASE_URL}/api/query/basic",
        json={"question": question},
        timeout=90,
    )

    response.raise_for_status()
    return response.json()


def call_document_tutor(collection_name: str, question: str):
    """
    Calls the backend document-grounded tutor endpoint.

    This is used only after a PDF has been successfully ingested.
    The collection_name tells the backend which uploaded session to query.
    """

    response = requests.post(
        f"{API_BASE_URL}/api/query",
        json={
            "collection_name": collection_name,
            "question": question,
        },
        timeout=90,
    )

    response.raise_for_status()
    return response.json()


def call_generate_mode(collection_name: str, mode: str):
    """
    Calls the backend study mode generator.

    The same dynamic endpoint handles all modes:
        /api/generate/faq
        /api/generate/notes
        /api/generate/quiz
        /api/generate/flashcards
        /api/generate/glossary

    The backend uses collection_name to generate assets for the active session.
    """

    response = requests.post(
        f"{API_BASE_URL}/api/generate/{mode}",
        data={"collection_name": collection_name},
        timeout=180,
    )

    response.raise_for_status()
    return response.json()


def ingest_pdf(uploaded_file, collection_name: str):
    """
    Sends an uploaded PDF to the FastAPI backend for ingestion.

    Backend responsibility:
    - receive PDF
    - load PDF
    - split into chunks
    - create OpenAI embeddings
    - store chunks in ChromaDB
    - return the collection_name and metadata

    Streamlit responsibility:
    - upload file
    - create session only if ingestion succeeds
    """

    files = {
        "file": (
            uploaded_file.name,
            uploaded_file.getvalue(),
            "application/pdf",
        )
    }

    data = {
        "collection_name": collection_name,
    }

    response = requests.post(
        f"{API_BASE_URL}/api/ingest/pdf",
        data=data,
        files=files,
        timeout=180,
    )

    response.raise_for_status()
    return response.json()


def add_message(message_list: list, role: str, content: str):
    """
    Adds a chat message to either:
    - the generic tutor chat history, or
    - the current session's document-grounded chat history.
    """

    message_list.append(
        {
            "role": role,
            "content": content,
        }
    )


def format_document_answer(data: dict) -> str:
    """
    Formats a document-grounded answer for chat history.

    The backend may return:
    - answer
    - source_excerpt
    - reasoning

    This combines those fields into one markdown message so the full
    response appears in the session history after rerun.
    """

    answer = data.get("answer", "No answer returned.")

    source_excerpt = data.get("source_excerpt")
    reasoning = data.get("reasoning")

    formatted_answer = answer

    if source_excerpt:
        formatted_answer += f"\n\n### Source excerpt\n{source_excerpt}"

    if reasoning:
        formatted_answer += f"\n\n### Reasoning\n{reasoning}"

    return formatted_answer


def render_chat_history(messages: list):
    """
    Displays all chat messages in the selected chat history list.

    This function is reused by:
    - generic tutor mode
    - session-based document tutor mode
    """

    for message in messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])


# =========================================================
# Top metrics
# =========================================================
metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)

metric_col1.metric("Content Types", "PDF")
metric_col2.metric("Study Modes", "5")
metric_col3.metric("API Backend", "FastAPI")
metric_col4.metric("AI Provider", "OpenAI")


# =========================================================
# Sidebar: session panel
# =========================================================
with st.sidebar:
    st.title("📌 Study Sessions")

    st.caption("Sessions are created only after a PDF is successfully ingested.")

    # Backend status check
    if st.button("Check Backend", use_container_width=True):
        is_healthy, health_data = check_backend_health()
        st.session_state.backend_status = {
            "is_healthy": is_healthy,
            "data": health_data,
        }

    if st.session_state.backend_status:
        if st.session_state.backend_status["is_healthy"]:
            st.success("Backend connected.")
            with st.expander("Backend details"):
                st.json(st.session_state.backend_status["data"])
        else:
            st.error("Backend unavailable.")
            # with st.expander("Error details"):
            #     st.json(st.session_state.backend_status["data"])

    st.divider()

    # Session list
    if not st.session_state.sessions:
        st.info("No sessions yet.")
        st.write("Upload and ingest a PDF to create your first study session.")
    else:
        st.write("Select a session:")

        for session_name in st.session_state.sessions.keys():
            is_active = session_name == st.session_state.active_session
            button_label = f"✅ {session_name}" if is_active else session_name

            if st.button(button_label, use_container_width=True):
                st.session_state.active_session = session_name
                st.rerun()

    st.divider()

    # Current mode indicator
    if st.session_state.active_session:
        st.success(f"Active: {st.session_state.active_session}")
    else:
        st.warning("Generic tutor mode")

    # Option to return to generic mode
    if st.button("Use Generic Tutor", use_container_width=True):
        st.session_state.active_session = None
        st.rerun()


# =========================================================
# Main tabs
# =========================================================
upload_tab, tutor_tab, modes_tab, about_tab = st.tabs(
    [
        "Upload",
        "AI Tutor",
        "Study Modes",
        "About",
    ]
)


# =========================================================
# Upload tab
# =========================================================
with upload_tab:
    st.subheader("Upload PDF and Create Study Session")

    st.write(
        "When you upload and ingest a PDF, StudyMate creates a new session. "
        "All tutor answers and study modes will then use that active session."
    )

    uploaded_file = st.file_uploader(
        "Choose a PDF file",
        type=["pdf"],
        help="Upload a short PDF first when testing so ingestion runs quickly.",
    )

    if uploaded_file is None:
        st.info("No file selected yet.")
    else:
        proposed_session_name = make_session_name(uploaded_file.name)
        proposed_collection_name = make_collection_name(uploaded_file.name)

        preview_col1, preview_col2 = st.columns(2)

        with preview_col1:
            st.markdown("### Session Preview")
            st.write(f"**Session name:** {proposed_session_name}")
            st.write(f"**File name:** {uploaded_file.name}")

        with preview_col2:
            st.markdown("### Backend Identifier")
            st.code(proposed_collection_name, language="text")
            st.caption(
                "This collection_name is sent to the backend and used by ChromaDB."
            )

        if st.button("Ingest PDF and Start Session", type="primary"):
            with st.spinner("Ingesting PDF and creating session..."):
                try:
                    result = ingest_pdf(
                        uploaded_file=uploaded_file,
                        collection_name=proposed_collection_name,
                    )

                    # Prefer backend-returned values if available.
                    backend_session_name = result.get(
                        "session_name",
                        proposed_session_name,
                    )

                    backend_collection_name = result.get(
                        "collection_name",
                        proposed_collection_name,
                    )

                    # Create or overwrite the session after successful ingestion.
                    st.session_state.sessions[backend_session_name] = {
                        "collection_name": backend_collection_name,
                        "file_name": uploaded_file.name,
                        "messages": [],
                        "study_assets": {},
                    }

                    # Make the newly created session active immediately.
                    st.session_state.active_session = backend_session_name

                    st.success(
                        f"Session created successfully: {backend_session_name}"
                    )

                    st.json(result)

                    st.info(
                        "Go to the AI Tutor or Study Modes tab to use this session."
                    )

                except requests.exceptions.RequestException as error:
                    st.error("PDF ingestion failed.")
                    st.write(
                        "Check that the FastAPI backend is running and that "
                        "OPENAI_API_KEY is correctly set in the backend environment."
                    )
                    st.code(str(error))


# =========================================================
# AI Tutor tab
# =========================================================
with tutor_tab:
    current_session = get_current_session()

    if current_session:
        st.subheader(f"AI Tutor — {st.session_state.active_session}")
        st.caption(
            "Document-grounded mode is active. Answers use the uploaded PDF session."
        )
        active_messages = current_session["messages"]
    else:
        st.subheader("AI Tutor — Generic Mode")
        st.caption(
            "No PDF session is active. The tutor can answer general questions, "
            "but it will not use uploaded course material."
        )
        active_messages = st.session_state.general_messages

    # Chat history appears above the input.
    with st.container(height=570):
        render_chat_history(active_messages)

    # st.chat_input stays visually below the history.
    question = st.chat_input("Ask a question...")

    if question:
        # Save user question first.
        add_message(active_messages, "user", question)

        try:
            with st.spinner("Generating answer..."):
                if current_session:
                    data = call_document_tutor(
                        collection_name=current_session["collection_name"],
                        question=question,
                    )

                    answer = format_document_answer(data)

                else:
                    data = call_basic_tutor(question=question)
                    answer = data.get("answer", "No answer returned.")

        except requests.exceptions.RequestException as error:
            answer = (
                "The tutor could not connect to the backend API.\n\n"
                "Make sure the FastAPI backend is running and your `.env` file "
                "contains the required backend settings.\n\n"
                f"Error: `{error}`"
            )

        # Save assistant answer to the same history list.
        add_message(active_messages, "assistant", answer)

        # Rerun so question and answer appear immediately in history.
        st.rerun()


# =========================================================
# Study Modes tab
# =========================================================
with modes_tab:
    current_session = get_current_session()
    session_ready = current_session is not None

    st.subheader("Generate Study Assets")

    if not session_ready:
        st.warning(
            "Study modes are disabled until a PDF has been successfully ingested."
        )
        st.write(
            "You can still use the AI Tutor in generic mode, upload a PDF, "
            "or read the About section."
        )
    else:
        st.success(f"Study modes active for: {st.session_state.active_session}")
        st.caption(f"Collection: `{current_session['collection_name']}`")

    mode = st.selectbox(
        "Choose a study mode",
        ["faq", "notes", "quiz", "flashcards", "glossary"],
        disabled=not session_ready,
    )

    generate_clicked = st.button(
        "Generate Study Asset",
        disabled=not session_ready,
        type="primary",
    )

    if generate_clicked and session_ready:
        with st.spinner(f"Generating {mode} for this session..."):
            try:
                data = call_generate_mode(
                    collection_name=current_session["collection_name"],
                    mode=mode,
                )

                title = data.get("title", mode.title())
                content_markdown = data.get("content_markdown", "")
                source_basis = data.get("source_basis", "")

                # Store generated content in the active session.
                current_session["study_assets"][mode] = {
                    "title": title,
                    "content_markdown": content_markdown,
                    "source_basis": source_basis,
                }

                st.success(f"{mode.title()} generated successfully.")

            except requests.exceptions.RequestException as error:
                st.error("Study asset generation failed.")
                st.write(
                    "Check that the backend is running and that OpenAI access "
                    "is configured correctly."
                )
                st.code(str(error))

    # Display saved study assets for the active session.
    if session_ready and current_session["study_assets"]:
        st.divider()
        st.subheader("Generated Assets for This Session")

        for asset_mode, asset_data in current_session["study_assets"].items():
            with st.expander(asset_data.get("title", asset_mode.title()), expanded=True):
                st.markdown(asset_data.get("content_markdown", ""))

                source_basis = asset_data.get("source_basis")
                if source_basis:
                    st.caption(source_basis)


# =========================================================
# About tab
# =========================================================
with about_tab:
    st.markdown(
        """
        ## About StudyMate

        StudyMate is a portfolio project designed to demonstrate a realistic
        AI-powered learning platform.

        ### Core idea

        The app is built around **study sessions**.

        When the app first starts:

        - no sessions exist
        - no PDF has been uploaded
        - the AI Tutor works only in generic mode
        - study modes are disabled

        After a PDF is uploaded and successfully ingested:

        - a new study session is created
        - the session is named after the uploaded file
        - the backend creates a ChromaDB collection for that PDF
        - the tutor switches into document-grounded mode
        - FAQ, notes, quiz, flashcards, and glossary tools unlock

        ### Architecture

        ```text
        Streamlit frontend
            ↓
        FastAPI backend
            ↓
        OpenAI chat model + OpenAI embeddings
            ↓
        ChromaDB vector database
        ```

        ### Important security note

        The Streamlit frontend does **not** use the OpenAI API key directly.

        The OpenAI key is stored in the backend `.env` file and used only by
        the FastAPI backend. Streamlit communicates with the backend through
        `API_BASE_URL`.

        ### Portfolio skills demonstrated

        - Python
        - Streamlit
        - FastAPI
        - REST APIs
        - OpenAI API integration
        - Retrieval-Augmented Generation
        - ChromaDB vector storage
        - Environment variables
        - Session-based app design
        - Docker-ready architecture
        - Technical writing and developer education
        """
    )