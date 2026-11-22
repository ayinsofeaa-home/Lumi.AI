# 💡 Lumi.AI: AI Revision Buddy

**SDT2143 Artificial Intelligence in Modern Computing · Mini AI Hackathon**
**Theme:** AI in Education

🔗 **Live app:** https://YOUR-APP-NAME.streamlit.app

Lumi.AI turns a long chapter into a quick revision pack. Upload your notes and get a one-page summary, the key sentences from the original text, and flashcards to test yourself, in seconds.

---

## 🎯 Problem
Before exams, students have to revise from long chapters and lecture slides, often 30 to 50 pages per topic. Reading everything again takes too long, and it is hard to tell which parts matter most.

## ✓ Objectives
1. Turn a long chapter into a one-page summary in under one minute.
2. Pick out the most important original sentences so students can check the AI summary.
3. Generate flashcards automatically for active recall practice.
4. Support English and Bahasa Melayu for Malaysian students.

---

## · Features
| Feature | Description |
|---|---|
| 📄 Multiple file types | PDF, PowerPoint (.pptx), Word (.docx) and text (.txt) |
| 📝 Summary | A one-page revision summary with bullet points |
| 📌 Key sentences | The 8 most important sentences from the original file, translated into the chosen language, with the original wording shown underneath |
| 🃏 Flashcards | Click-to-reveal question and answer cards, downloadable as CSV for Anki or Quizlet |
| 🌏 Language | English or Bahasa Melayu |
| 🎚️ Difficulty | Easy (facts), Medium (understanding) or Exam-style (explain and apply) |
| 🕘 History | Reopen earlier study packs during the same session |

---

## 🤖 AI tools used and why
| Tool | Role | Why we chose it |
|---|---|---|
| **Google Gemini** (Flash-Lite) | Writes the summary and flashcards and translates the key sentences, all in one request | Fast, free tier, follows instructions well and can return structured JSON |
| **Hugging Face `all-MiniLM-L6-v2`** | Finds the key sentences in the original text | A small pre-trained model (about 90 MB) that runs inside the app in seconds, with no API cost |
| **PyPDF2, python-pptx, python-docx** | Read text from the uploaded file | Standard Python libraries for each file type |
| **Streamlit** | Web interface | Turns Python code into a web app quickly, with free hosting |
| **Google Colab** | Prototyping and testing each step | Free cloud notebook for testing the AI tools before building the app |

### How the key sentences are picked
1. The text is split into sentences.
2. MiniLM turns each sentence into a vector, a list of numbers that represents its meaning.
3. The average of all the vectors represents the main idea of the chapter.
4. The sentences closest to that average are the most central ones, so they are chosen.

---

## 🔄 How it works
