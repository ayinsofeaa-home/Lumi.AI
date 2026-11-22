"""Lumi.AI: turn a long chapter PDF into a revision summary, key sentences and flashcards.

AI tools
  - Gemini (Flash-Lite): writes the summary and flashcards in ONE request
  - Hugging Face all-MiniLM-L6-v2: picks the most important original sentences
"""
import csv
import html
import io
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import streamlit as st
from PyPDF2 import PdfReader

GEMINI_MODELS = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-flash-lite-latest"]
MINILM = "sentence-transformers/all-MiniLM-L6-v2"
MAX_CHARS = 120_000  # about 50 pages of text sent to Gemini

st.set_page_config(page_title="Lumi.AI", page_icon="💡", layout="wide")

# ---------- Styling (purple, black, yellow) ----------
st.markdown("""
<style>
.lumi-banner {
    background: linear-gradient(135deg, #5B2A86 0%, #2A1B47 55%, #0E0B16 100%);
    border: 1px solid #FFD23F55; border-radius: 18px;
    padding: 28px 32px; margin-bottom: 20px;
}
.lumi-banner h1 { color: #FFD23F; margin: 0; font-size: 2.6rem; }
.lumi-banner p  { color: #E9E3FF; margin: 6px 0 0 0; font-size: 1.05rem; }
.lumi-card {
    background: #2A1B47; border-left: 5px solid #FFD23F; border-radius: 12px;
    padding: 14px 18px; margin-bottom: 12px;
}
.lumi-card summary { cursor: pointer; font-weight: 600; color: #FFFFFF; }
.lumi-card .answer { color: #FFD23F; margin-top: 10px; }
.lumi-quote {
    background: #1A1230; border-left: 4px solid #9B6BFF; border-radius: 10px;
    padding: 10px 14px; margin-bottom: 10px; font-style: italic;
}
.stButton > button, .stDownloadButton > button {
    border-radius: 10px; font-weight: 700;
}
</style>
""", unsafe_allow_html=True)

# ---------- Read the file (PDF, PowerPoint, Word, text) ----------
def extract_text(file, max_pages: int):
    """Return (clean text, number of pages/slides read, total, unit name)."""
    name = file.name.lower()
    if name.endswith(".pdf"):
        reader = PdfReader(file)
        total = len(reader.pages)
        parts = [(p.extract_text() or "") for p in reader.pages[:max_pages]]
        unit = "pages"
    elif name.endswith(".pptx"):
        from pptx import Presentation
        slides = list(Presentation(file).slides)
        total = len(slides)
        parts = []
        for slide in slides[:max_pages]:
            for shape in slide.shapes:
                if shape.has_text_frame and shape.text_frame.text.strip():
                    # slide bullets often have no full stop, so add one
                    parts.append(shape.text_frame.text.strip().rstrip(".") + ".")
        unit = "slides"
    elif name.endswith(".docx"):
        from docx import Document
        parts = [p.text for p in Document(file).paragraphs if p.text.strip()]
        total, unit = 1, "document"
    else:  # .txt
        parts = [file.read().decode("utf-8", errors="ignore")]
        total, unit = 1, "document"
    text = " ".join(" ".join(parts).split())  # also removes line breaks
    return text, min(total, max_pages), total, unit

# ---------- Hugging Face: MiniLM key sentences ----------
@st.cache_resource(show_spinner="Loading Hugging Face model...")
def load_minilm():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MINILM)

def key_sentences(text: str, model, k: int = 8):
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text)
                 if 6 <= len(s.split()) <= 60]
    if len(sentences) <= k:
        return sentences
    vectors = model.encode(sentences, normalize_embeddings=True, batch_size=64)
    centre = vectors.mean(axis=0)            # the chapter's "main idea"
    scores = vectors @ centre                # closeness of each sentence to it
    top = sorted(np.argsort(scores)[-k:])    # best k, kept in original order
    return [sentences[i] for i in top]

# ---------- Gemini: summary + flashcards ----------
DIFFICULTY = {
    "Easy": "simple recall questions about definitions and facts",
    "Medium": "questions that check understanding of how and why things work",
    "Exam-style": "exam-style questions that ask students to explain, compare or apply concepts",
}

def build_prompt(text, language, difficulty, n_cards):
    return f"""You are a study coach for diploma students.
From the study material below, write in {language}:
1. "summary": a revision summary of at most 350 words that fits on one page, using short paragraphs and bullet points.
2. "flashcards": {n_cards} question-and-answer flashcards. Use {DIFFICULTY[difficulty]}. Each tests one idea. Answers max 2 sentences.
Use only facts from the material.
Return JSON: {{"summary": "...", "flashcards": [{{"question": "...", "answer": "..."}}]}}

MATERIAL:
{text[:MAX_CHARS]}"""

def ask_gemini(api_key, prompt):
    from google import genai
    from google.genai import errors, types
    client = genai.Client(api_key=api_key)
    for name in GEMINI_MODELS:              # main model, then backups
        for attempt in range(2):            # 2 tries per model
            try:
                resp = client.models.generate_content(
                    model=name,
                    contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json"),
                )
                return json.loads(resp.text), name
            except errors.APIError as e:
                if e.code not in (429, 500, 503):   # only retry when busy
                    raise
                time.sleep(2)
    raise RuntimeError("All Gemini models are busy right now. Please try again in a minute.")

def cards_to_csv(cards):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Question", "Answer"])  # imports into Anki / Quizlet
    for c in cards:
        writer.writerow([c["question"], c["answer"]])
    return buf.getvalue()

# ---------- Page ----------
st.markdown("""
<div class="lumi-banner">
  <h1>💡 Lumi.AI</h1>
  <p>Drop in a long chapter. Get a 1-page summary, key textbook sentences and flashcards in seconds.</p>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ Settings")
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        api_key = st.text_input("Gemini API key", type="password",
                                help="Free key at https://aistudio.google.com/apikey")
    language = st.radio("Language", ["English", "Bahasa Melayu"], horizontal=True)
    difficulty = st.select_slider("Flashcard difficulty", list(DIFFICULTY), value="Medium")
    n_cards = st.slider("Number of flashcards", 5, 25, 10)
    max_pages = st.number_input("Max pages to read", 1, 300, 60)

uploaded = st.file_uploader("📄 Upload your chapter (PDF)", type="pdf")

if uploaded and st.button("· Generate study pack", type="primary"):
    if not api_key:
        st.error("Please enter a Gemini API key in the sidebar.")
        st.stop()

    start = time.time()
    with st.spinner("Reading your PDF..."):
        text, total_pages = extract_text(uploaded, max_pages)
    if len(text.split()) < 100:
        st.error("Almost no text found. This PDF may be scanned images, which need OCR first.")
        st.stop()

    try:
        with st.spinner("Lumi is studying your chapter..."):
            minilm = load_minilm()  # load once, outside the thread
            with ThreadPoolExecutor() as pool:   # run both AI tools at the same time
                gemini_job = pool.submit(ask_gemini, api_key,
                                         build_prompt(text, language, difficulty, n_cards))
                quotes_job = pool.submit(key_sentences, text, minilm)
                result, model_used = gemini_job.result()
                quotes = quotes_job.result()
        st.session_state["pack"] = {
            "summary": result["summary"],
            "cards": result["flashcards"],
            "quotes": quotes,
            "info": f"Read {min(total_pages, max_pages)} of {total_pages} pages "
                    f"({len(text.split()):,} words) in {time.time() - start:.1f} s "
                    f"· Gemini model: {model_used}",
        }
    except Exception as e:  # show API errors on the page
        st.error(f"Something went wrong: {e}")

pack = st.session_state.get("pack")
if pack:
    st.success(pack["info"])
    tab_sum, tab_quotes, tab_cards = st.tabs(
        ["📝 Summary", "📌 Key sentences", "🃏 Flashcards"])

    with tab_sum:
        st.markdown(pack["summary"])
        st.download_button("⬇️ Download summary", pack["summary"], "lumi_summary.txt")

    with tab_quotes:
        st.caption("The most important sentences from your original PDF, picked by a "
                   "Hugging Face model. Use them to check the AI summary.")
        for q in pack["quotes"]:
            st.markdown(f'<div class="lumi-quote">“{html.escape(q)}”</div>',
                        unsafe_allow_html=True)

    with tab_cards:
        st.caption("Click a question to reveal the answer.")
        for i, c in enumerate(pack["cards"], 1):
            st.markdown(
                f'<div class="lumi-card"><details>'
                f'<summary>Q{i}. {html.escape(c["question"])}</summary>'
                f'<div class="answer">{html.escape(c["answer"])}</div>'
                f'</details></div>',
                unsafe_allow_html=True)
        st.download_button("⬇️ Download flashcards (CSV for Anki/Quizlet)",
                           cards_to_csv(pack["cards"]), "lumi_flashcards.csv", "text/csv")
