# Lumi.AI (SDT2143 Mini AI Hackathon, theme: AI in Education)

Upload a long chapter PDF and get a 1-page summary, a mind map and flashcards.

| Step | Tool |
|---|---|
| Extract text | PyPDF2 |
| Summary | Hugging Face `facebook/bart-large-cnn` (chunk, then summarise the summaries) |
| Mind map + flashcards | Gemini (`gemini-2.5-flash`), JSON output |
| UI | Streamlit (mind map drawn with Graphviz) |

## Run

```bash
pip install -r requirements.txt
export GEMINI_API_KEY=your_key   # or paste it in the sidebar
streamlit run app.py
```

The first run downloads BART (~1.6 GB). Get a free key at https://aistudio.google.com/apikey.

## Limits
- Scanned PDFs have no text layer and need OCR first.
- BART may paraphrase badly on equations and tables.
- Check flashcards against the source before relying on them.

## Colab prototype
Copy the functions from `app.py` (everything above `# ---------- UI`) into notebook cells, replace `st.cache_resource` with nothing, and call them on a PDF path. Use `streamlit` + `localtunnel` or deploy on Streamlit Community Cloud for the demo link.
