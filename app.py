"""Lumi.AI: PDF chapter -> 1-page summary, mind map, flashcards.

Pipeline
  PyPDF2 (extract text)
  -> Hugging Face BART (facebook/bart-large-cnn) chunked, 2-stage summary
  -> Gemini (mind map + flashcards, returned as JSON)
"""
import csv
import io
import json
import os

import streamlit as st
from PyPDF2 import PdfReader

BART_MODEL = "facebook/bart-large-cnn"
GEMINI_MODEL = "gemini-3.8-flash"
CHUNK_WORDS = 500          # BART input limit is ~1024 tokens; 500 words is safe
MAX_GEMINI_CHARS = 60000   # cap text sent to Gemini


# ---------- PDF ----------
def extract_text(file) -> str:
    reader = PdfReader(file)
    pages = [(p.extract_text() or "") for p in reader.pages]
    return "\n".join(pages)


def chunk_words(text: str, size: int = CHUNK_WORDS):
    words = text.split()
    for i in range(0, len(words), size):
        yield " ".join(words[i:i + size])


# ---------- BART ----------
@st.cache_resource(show_spinner="Loading BART model (first run downloads ~1.6 GB)...")
def load_summarizer():
    from transformers import pipeline
    return pipeline("summarization", model=BART_MODEL)


def bart_summarize(text: str, max_len: int, min_len: int) -> str:
    summarizer = load_summarizer()
    n_words = len(text.split())
    max_len = min(max_len, max(30, int(n_words * 0.8)))
    min_len = min(min_len, max_len - 5)
    out = summarizer(text, max_length=max_len, min_length=min_len, do_sample=False,
                     truncation=True)
    return out[0]["summary_text"].strip()


def one_page_summary(text: str, progress) -> str:
    """Stage 1: summarise each chunk. Stage 2: summarise the joined partials."""
    chunks = list(chunk_words(text))
    partials = []
    for i, ch in enumerate(chunks):
        if len(ch.split()) < 40:
            continue
        partials.append(bart_summarize(ch, max_len=130, min_len=40))
        progress.progress((i + 1) / len(chunks), text=f"Summarising chunk {i + 1}/{len(chunks)}")
    joined = " ".join(partials)
    # Keep reducing until the text fits roughly one page (~350 words).
    while len(joined.split()) > 350 and len(partials) > 1:
        partials = [bart_summarize(c, 130, 40) for c in chunk_words(joined)
                    if len(c.split()) >= 40] or partials[:1]
        joined = " ".join(partials)
    return joined


# ---------- Gemini ----------
def gemini_json(api_key: str, prompt: str):
    import time
    from google import genai
    from google.genai import errors, types
    client = genai.Client(api_key=api_key)
    for attempt in range(4):
        try:
            resp = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
            return json.loads(resp.text)
        except errors.APIError as e:
            # 429 = rate limit, 500/503 = server busy: wait and retry
            if e.code in (429, 500, 503) and attempt < 3:
                time.sleep(2 ** (attempt + 1))  # wait 2s, 4s, then 8s
                continue
            raise



def make_flashcards(api_key: str, text: str, n: int):
    prompt = (
        f"You are a study coach. From the study material below, write {n} flashcards "
        "for exam revision. Each must test one idea, with a short question and a "
        "concise answer (max 2 sentences). Use only facts from the material. "
        'Return JSON: [{"question": "...", "answer": "..."}].\n\n'
        f"MATERIAL:\n{text[:MAX_GEMINI_CHARS]}"
    )
    return gemini_json(api_key, prompt)


def make_mindmap(api_key: str, text: str):
    prompt = (
        "Extract a mind map of the key concepts from the study material below. "
        "Use one central topic, 4-7 main branches, and 2-4 sub-points per branch. "
        "Labels must be 1-5 words. "
        'Return JSON: {"topic": "...", "branches": [{"name": "...", "children": ["..."]}]}.\n\n'
        f"MATERIAL:\n{text[:MAX_GEMINI_CHARS]}"
    )
    return gemini_json(api_key, prompt)


def mindmap_to_dot(mm: dict) -> str:
    def esc(s):
        return str(s).replace('"', "'")
    lines = ["digraph G {", "rankdir=LR;",
             'node [shape=box, style="rounded,filled", fontname="Helvetica"];',
             f'root [label="{esc(mm["topic"])}", fillcolor="#ffd966", fontsize=16];']
    for i, b in enumerate(mm.get("branches", [])):
        lines.append(f'b{i} [label="{esc(b["name"])}", fillcolor="#9fc5e8"];')
        lines.append(f"root -> b{i};")
        for j, c in enumerate(b.get("children", [])):
            lines.append(f'c{i}_{j} [label="{esc(c)}", fillcolor="#d9ead3"];')
            lines.append(f"b{i} -> c{i}_{j};")
    lines.append("}")
    return "\n".join(lines)


def cards_to_csv(cards) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Question", "Answer"])  # Anki/Quizlet-friendly
    for c in cards:
        w.writerow([c["question"], c["answer"]])
    return buf.getvalue()


# ---------- UI ----------
st.set_page_config(page_title="Lumi.AI", page_icon="💡", layout="wide")
st.title("💡 Lumi.AI")
st.caption("Upload a chapter PDF. Get a 1-page summary, a mind map and flashcards.")

with st.sidebar:
    st.header("Settings")
    api_key = st.text_input("Gemini API key", type="password",
                            value=os.getenv("GEMINI_API_KEY", ""),
                            help="Free key at https://aistudio.google.com/apikey")
    n_cards = st.slider("Number of flashcards", 5, 30, 12)
    max_pages = st.number_input("Max pages to read", 1, 200, 60)

uploaded = st.file_uploader("Chapter PDF", type="pdf")

if uploaded and st.button("Generate study pack", type="primary"):
    if not api_key:
        st.error("Enter a Gemini API key in the sidebar.")
        st.stop()

    with st.spinner("Reading PDF..."):
        reader = PdfReader(uploaded)
        total = len(reader.pages)
        text = "\n".join((p.extract_text() or "") for p in reader.pages[:max_pages])
    if len(text.split()) < 100:
        st.error("Almost no text found. The PDF may be scanned images (needs OCR).")
        st.stop()
    st.info(f"Read {min(total, max_pages)} of {total} pages, {len(text.split()):,} words.")

    try:
        bar = st.progress(0.0, text="Starting summary...")
        summary = one_page_summary(text, bar)
        bar.empty()
        with st.spinner("Gemini is building the mind map and flashcards..."):
            # Use the BART summary + raw text excerpt so Gemini stays grounded.
            mindmap = make_mindmap(api_key, text)
            cards = make_flashcards(api_key, text, n_cards)
        st.session_state["pack"] = {"summary": summary, "mindmap": mindmap, "cards": cards}
    except Exception as e:  # noqa: BLE001 - show any API/model error to the user
        st.error(f"Failed: {e}")

pack = st.session_state.get("pack")
if pack:
    tab1, tab2, tab3 = st.tabs(["📝 Summary", "🧠 Mind map", "🃏 Flashcards"])
    with tab1:
        st.write(pack["summary"])
        st.download_button("Download summary (.txt)", pack["summary"], "summary.txt")
    with tab2:
        st.graphviz_chart(mindmap_to_dot(pack["mindmap"]), use_container_width=True)
    with tab3:
        for i, c in enumerate(pack["cards"], 1):
            with st.expander(f"Q{i}. {c['question']}"):
                st.write(c["answer"])
        st.download_button("Download flashcards (.csv)", cards_to_csv(pack["cards"]),
                           "flashcards.csv", "text/csv")
