# Candidate Intelligence System (CIS)

Production-grade AI-powered Resume Screening System. Hiring reframed as an
**information retrieval and ranking problem** — not classification.

## Architecture

Five-layer cascade pipeline:

```
Retrieval (BGE/E5 + FAISS) → Reranking (Cross-Encoder) → Intelligence (Skill Graph + Evidence + Career + Behavior) → Fusion (XGBoost LTR) → Explanation (SHAP + NL)
```

## Key Features

- **Semantic Retrieval**: Hybrid BM25 + dense FAISS search
- **Multi-dimensional Scoring**: Semantic Fit, Evidence Strength, Career Consistency, Behavior Score
- **Learning-to-Rank**: XGBoost/LightGBM with 255 engineered features
- **Explainability**: SHAP-based per-candidate explanations with natural language summaries
- **Fairness Audit**: Demographic parity, equal opportunity, and proxy feature detection
- **CPU-Only**: No GPU required; 16GB RAM ceiling; 5-minute inference budget

## Quick Start

### Prerequisites

- Python 3.11+
- Tesseract OCR (`brew install tesseract` on macOS)

### Setup

```bash
cd candidate_ai
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm

# Copy and configure environment
cp .env.example .env

# Run database migrations
alembic upgrade head

# Start the API server
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

### Docker

```bash
cd docker
docker-compose up --build
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/token` | Login, get JWT token |
| POST | `/api/v1/jobs` | Upload job description |
| GET | `/api/v1/jobs/{jd_id}` | Get parsed JD |
| POST | `/api/v1/candidates/upload` | Upload single resume |
| POST | `/api/v1/candidates/bulk-upload` | Bulk upload resumes |
| GET | `/api/v1/candidates/{candidate_id}` | Get candidate details |
| POST | `/api/v1/search/rank` | Rank candidates for a JD |
| GET | `/api/v1/search/rank/{jd_id}/{candidate_id}/explain` | Get SHAP explanation |
| GET | `/api/v1/fairness/report/{jd_id}` | Fairness audit report |
| GET | `/api/v1/health` | Health check |

## Project Structure

```
candidate_ai/
├── configs/          # YAML/JSON configuration
├── data/             # Raw resumes, processed data, embeddings
├── models/           # Trained model artifacts
├── src/
│   ├── parser/       # PDF/DOCX/OCR resume parsing
│   ├── jd/           # Job description intelligence
│   ├── resume/       # Resume intelligence
│   ├── retrieval/    # FAISS + BM25 retrieval
│   ├── graph/        # Skill graph & ontology
│   ├── evidence/     # Evidence linking & authenticity
│   ├── career/       # Career trajectory analysis
│   ├── behavior/     # Behavioral signal extraction
│   ├── features/     # Feature engineering & store
│   ├── ranking/      # Learning-to-Rank models
│   ├── explainability/ # SHAP + NL explanations
│   ├── fairness/     # Bias audit & calibration
│   ├── api/          # FastAPI backend
│   └── utils/        # Shared utilities
├── training/         # Model training scripts
├── inference/        # Inference pipeline
├── scripts/          # Offline indexing scripts
├── tests/            # Unit, integration, benchmark tests
└── docker/           # Deployment files
```

## Constraints

- **CPU-only** inference (no GPU required)
- **16 GB RAM** ceiling
- **5-minute** end-to-end inference budget
- **No external APIs** at inference time
- All embeddings and features **pre-computed offline**

## License

Proprietary. All rights reserved.
