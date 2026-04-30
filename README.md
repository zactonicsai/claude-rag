# Claude RAG Chat

A self-contained RAG (retrieval-augmented generation) chat app:

* **FastAPI** backend that talks to **Anthropic's Claude API** and **ChromaDB**.
* **LocalStack S3** for staging uploaded files before they're processed.
* **Temporal** + three Python workers — `doc-worker` (PDF/DOCX/HTML/CSV/JSON/text),
  `ocr-worker` (Tesseract for images), `ingest-worker` (chunking + ChromaDB writes,
  also hosts the workflow).
* Static **HTML / Tailwind / vanilla JS** frontend served by nginx.
* SQLite registry (mounted on a shared volume) for file metadata and extracted text.

The whole thing runs with `docker compose up`.

```
              ┌───────── browser ─────────┐
              │  (nginx / index.html)     │
              └────────────┬──────────────┘
                           │  /api/*
                           ▼
              ┌────────── FastAPI ────────┐
   upload ──► │  /api/files (S3 + Temporal start) │
   chat   ──► │  /api/chat  (Chroma + Claude)     │
              └────┬─────────┬───────────┬────────┘
                   │ S3      │ Chroma    │ Temporal
                   ▼         ▼           ▼
            LocalStack    ChromaDB    Temporal Server
                                          │
              ┌───────────────────────────┴───────────────┐
              ▼                          ▼                ▼
        doc-worker                  ocr-worker       ingest-worker
      (pypdf/docx/bs4)         (tesseract+pillow)   (chunk + embed,
                                                     hosts workflow)
```

---

## Quick start

```bash
cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY=sk-ant-...

docker compose build
docker compose up
```

Then open:

| URL                              | Purpose                              |
|----------------------------------|--------------------------------------|
| http://localhost:8080            | Chat UI                              |
| http://localhost:8000/docs       | FastAPI Swagger docs                 |
| http://localhost:8088            | Temporal Web UI (workflows view)     |
| http://localhost:4566            | LocalStack S3 endpoint               |
| http://localhost:8001            | ChromaDB API                         |

### Recovering from a broken first boot

If a previous `docker compose up` failed with the temporal "dynamic config
… no such file or directory" error, the dead container and Postgres state
need to be cleared so the rebuild takes effect:

```bash
docker compose down -v          # stop and remove volumes
docker compose build temporal   # rebuild the temporal image with the baked-in config
docker compose up
```

To verify the file actually made it into the running image:

```bash
docker compose exec temporal ls -l /etc/temporal/config/dynamicconfig/
# expect: development-sql.yaml
```

### Windows-specific notes

* **Use the `build:` form, not `image:`.** The `temporal` service in
  `docker-compose.yml` must be `build: ./temporal` (it bakes the dynamic-config
  file into a custom image). If you copy a snippet from elsewhere and end up
  with `image: temporalio/auto-setup:1.25.2` directly + no volume mount, the
  upstream image has nothing at the configured `DYNAMIC_CONFIG_FILE_PATH` and
  startup fails immediately.
* **Line endings.** The repo ships a `.gitattributes` that forces LF on all
  YAML / shell / Dockerfile content, and `temporal/Dockerfile` runs the YAML
  through `tr -d '\r'` during the COPY step, so even if your extractor or Git
  config converted to CRLF, the file inside the container is correct.
* **WSL2 file sharing.** Make sure your project lives somewhere Docker
  Desktop is allowed to read (Settings → Resources → File Sharing). Putting
  the repo under `\\wsl$\...` or directly inside the WSL filesystem usually
  works best; deeply-nested paths under `OneDrive` sometimes don't.
* **PowerShell quoting.** All commands in this README assume bash semantics.
  If you're in PowerShell, use straight quotes (`"`), not smart quotes.

---

## Using it

1. Upload one or more files via the sidebar. Supported out of the box:
   * Text-ish: `.txt .md .log .py .js .ts .yaml .yml .csv .json .html`
   * Office: `.docx`, `.pdf` (text-based)
   * Images (OCR via Tesseract): `.png .jpg .jpeg .tiff .bmp .gif .webp`
2. Files cycle through statuses you can watch in the table:
   `pending → converting | ocr → chunking → ready` (or `error`).
3. Click **view** on a row to see the extracted text.
4. Tick the checkboxes next to whichever files you want as context. Leaving them
   unchecked searches the whole library.
5. Toggle **Use ChromaDB only (skip Claude)** to do retrieval-only with no
   Claude API call (cost: $0).
6. Each Claude reply shows the per-request token & cost breakdown; the sidebar
   tracks a running session total.

---

## Configuration (`.env`)

```ini
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-sonnet-4-5

# USD per 1M tokens — match these to whatever model you select
CLAUDE_PRICE_INPUT_PER_MTOK=3.00
CLAUDE_PRICE_OUTPUT_PER_MTOK=15.00

CHUNK_SIZE=1200
CHUNK_OVERLAP=150
TOP_K=6
MAX_OUTPUT_TOKENS=1024
```

---

## Project layout

```
claude-rag/
├── docker-compose.yml          ← orchestrates 10 services
├── .env.example
├── pytest.ini, conftest.py
├── localstack/init-aws.sh
│
├── backend/                    FastAPI service
│   ├── Dockerfile, requirements.txt
│   └── app/
│       ├── main.py             entry + CORS
│       ├── config.py           pydantic-settings
│       ├── models.py           request/response schemas
│       ├── db.py               SQLite file registry
│       ├── s3_client.py        LocalStack-aware boto3 wrapper
│       ├── chroma_client.py    retrieval helpers
│       ├── claude_client.py    SDK wrapper + cost math
│       ├── utils/chunking.py
│       └── routes/{files,chat,health}.py
│   └── tests/                  unit + route tests (mocked deps)
│
├── workers/                    Temporal workers (Python)
│   ├── shared/
│   │   ├── activities.py       fetch / detect / convert / ocr / chunk+embed / mark
│   │   ├── workflows.py        FileProcessingWorkflow
│   │   ├── converters.py       per-format → text dispatchers
│   │   ├── chunking.py, db.py, config.py
│   ├── doc_worker.py           queue: doc-conversion
│   ├── ocr_worker.py           queue: ocr-processing
│   ├── ingest_worker.py        queues: file-processing (workflow) + chroma-ingestion
│   └── Dockerfile.{doc,ocr,ingest}, requirements.{doc,ocr,ingest}.txt
│   └── tests/
│
└── frontend/
    ├── index.html, app.js, styles.css
    └── nginx.conf              proxies /api/ → backend:8000
```

---

## Workflow internals

`FileProcessingWorkflow` (in `workers/shared/workflows.py`) is started by the
backend as soon as the upload hits S3:

1. `fetch_from_s3` — pulls the bytes back out (ingest queue).
2. `detect_kind` — image vs document (ingest queue).
3. Either `ocr_image` (ocr queue) or `convert_doc` (doc queue) → extracted text.
4. `chunk_and_embed` — sentence-aware overlapping windows → ChromaDB
   (ingest queue). Idempotent: deletes any prior chunks for this file before
   writing.
5. `mark_status` — flips the SQLite row to `ready` (or `error` on failure).

Each step's task queue is selected so only the worker with the right
dependencies installed (tesseract, pypdf, etc.) sees the work. Activities are
sync Python and run on a per-worker `ThreadPoolExecutor`.

---

## Chat internals

`POST /api/chat` does:

1. `chroma.query()` against the configured collection, filtered by
   `metadata.file_id ∈ selected_file_ids` (or unfiltered if no selection).
2. If `chroma_only=True`: format and return the chunks; no Claude call;
   cost reported as $0.
3. Otherwise: build a system prompt that asks Claude to answer using the
   context and cite filenames inline; return Claude's text plus the chunks
   used and a `CostBreakdown` (input tokens, output tokens, USD).

---

## Tests

```bash
pip install -r backend/requirements.txt \
    -r workers/requirements.doc.txt \
    -r workers/requirements.ocr.txt \
    -r workers/requirements.ingest.txt
pytest
```

The suite (52 tests) covers chunking, the SQLite registry, the cost math,
the route handlers (with S3 / Chroma / Temporal / Claude all mocked), the
converter dispatcher, and every Temporal activity (mocking `boto3`,
`chromadb.HttpClient`, `PIL.Image.open`, and `pytesseract.image_to_string`).
None of the tests require any of the backing services to be running — `pytest`
from a clean checkout passes.

---

## Things to know / extend

* **Temporal needs the dynamic-config setup file.** `auto-setup` reads
  `DYNAMIC_CONFIG_FILE_PATH` and the server fails to start if that file isn't
  present, with errors like *"unable to validate dynamic config: stat
  config/dynamicconfig/development-sql.yaml: no such file or directory"*.
  The repo handles this by **baking the file into a custom image**
  (`temporal/Dockerfile`, which extends `temporalio/auto-setup:1.25.2` and
  copies `temporal/dynamicconfig/development-sql.yaml` to its absolute path
  inside the image). Compose builds this image as `rag-temporal-with-dynamicconfig`.
  Bind mounts were the original approach but they silently no-op on Docker
  Desktop / WSL2 setups when the host path isn't where compose thinks it is —
  bake-in is bulletproof.
  The compose healthcheck waits for `tctl namespace describe default` to
  succeed before the backend and workers are allowed to connect, so workers
  don't race the namespace-creation step on first boot.

* The default Chroma embedding function is the bundled SentenceTransformer
  (`all-MiniLM-L6-v2`). The first chunk-and-embed call after `compose up`
  downloads the model — a few hundred MB, takes a minute. Subsequent runs
  are fast.
* Pricing in `.env` is per 1M tokens. Update both numbers when you change
  `CLAUDE_MODEL` so the displayed cost matches.
* Scanned (image-only) PDFs aren't OCR'd — the doc worker uses pypdf which
  only extracts an embedded text layer. If you need OCR on PDFs, route them
  to the OCR worker (rasterize first with `pdf2image` and feed to Tesseract).
* The SQLite file is mounted on the shared `backend-data` volume so all
  workers can update statuses; for production you'd swap this for Postgres.
