# fusion-backend
│
├── app/
│   ├── main.py                         # Starts FastAPI
│   ├── config.py                       # Environment variables/settings
│   ├── database.py                     # Neon PostgreSQL connection
│   │
│   ├── models/                         # Database tables
│   │   ├── location.py                 # Dataset/location information
│   │   ├── event.py                    # Flood events
│   │   ├── simulation.py               # Simulation records
│   │   ├── risk_assessment.py          # Calculated risk results
│   │   ├── ml_prediction.py            # ML prediction results
│   │   ├── pml.py                      # PML records
│   │   ├── tvl.py                      # TVL records
│   │   ├── alert.py                    # Alerts
│   │   └── early_action.py             # Recommended actions
│   │
│   ├── schemas/                        # API request/response formats
│   │   ├── location.py
│   │   ├── event.py
│   │   ├── simulation.py
│   │   ├── risk.py
│   │   ├── ml_prediction.py
│   │   ├── pml.py
│   │   ├── tvl.py
│   │   ├── alert.py
│   │   └── llm.py
│   │
│   ├── routes/                         # API endpoints only
│   │   ├── locations.py                # Location endpoints
│   │   ├── events.py                   # Event endpoints
│   │   ├── simulations.py              # Simulation endpoints
│   │   ├── risk.py                     # Risk endpoints
│   │   ├── ml.py                       # ML prediction endpoints
│   │   ├── pml.py                      # PML endpoints
│   │   ├── tvl.py                      # TVL endpoints
│   │   ├── alerts.py                   # Alert endpoints
│   │   └── ai.py                       # LLM endpoints
│   │
│   ├── services/                       # Actual application logic
│   │   │
│   │   ├── risk/                       # Core catastrophe calculations
│   │   │   ├── hazard.py               # Hazard calculations
│   │   │   ├── flood_depth.py          # Flood depth
│   │   │   ├── damage.py               # Damage/loss
│   │   │   ├── risk.py                 # Risk calculation
│   │   │   ├── pml.py                  # PML calculation
│   │   │   └── tvl.py                  # TVL calculation
│   │   │
│   │   ├── ml/                         # Machine learning
│   │   │   ├── predictor.py            # Loads model + makes predictions
│   │   │   ├── preprocessing.py         # Prepares input data
│   │   │   └── model_loader.py          # Loads trained Random Forest
│   │   │
│   │   ├── simulation/                 # Event simulation
│   │   │   ├── simulator.py            # Controls simulation
│   │   │   ├── scenario_generator.py   # Creates scenario values
│   │   │   └── scenario_runner.py      # Runs scenario
│   │   │
│   │   ├── alerts/                     # Early warning
│   │   │   ├── alert_engine.py         # Decides whether to alert
│   │   │   └── alert_rules.py          # Alert thresholds/rules
│   │   │
│   │   ├── notifications/              # External notifications
│   │   │   └── brevo.py                # Sends email through Brevo
│   │   │
│   │   └── llm/                        # AI explanation
│   │       ├── client.py               # Connects to LLM
│   │       ├── result_explainer.py     # Explains results
│   │       ├── scenario_generator.py   # Suggests scenarios
│   │       └── action_recommender.py   # Recommends actions
│   │
│   └── utils/
│       ├── enums.py                    # Fixed values/statuses
│       └── helpers.py                  # Small reusable functions
│
├── ml/
│   ├── train.py                        # Train Random Forest
│   ├── evaluate.py                     # Evaluate model
│   └── artifacts/
│       └── model.joblib                # Saved trained model
│
├── notebooks/
│   ├── 01_dataset_exploration.ipynb
│   ├── 02_hazard_calculation.ipynb
│   ├── 03_flood_depth_calculation.ipynb
│   ├── 04_damage_calculation.ipynb
│   ├── 05_risk_calculation.ipynb
│   ├── 06_pml_calculation.ipynb
│   ├── 07_tvl_calculation.ipynb
│   ├── 08_ml_model.ipynb
│   └── 09_model_validation.ipynb
│
├── tests/
│   ├── test_hazard.py
│   ├── test_flood_depth.py
│   ├── test_damage.py
│   ├── test_risk.py
│   ├── test_pml.py
│   ├── test_tvl.py
│   ├── test_ml.py
│   ├── test_simulation.py
│   └── test_alerts.py
│
├── alembic/                            # Database migrations
├── data/
│   └── README.md                       # Explains dataset
│
├── .env                                # Secret keys (never commit)
├
├── .gitignore
├── requirements.txt
└── README.md

## Flood hotspots

Hotspots are stored as named areas with latitude and longitude. Apply the
database migrations with `alembic upgrade head`, then import the bundled
`data/nairobi_hotspots_geocoded.csv` using `python scripts/import_hotspots.py`.
The importer updates coordinates when a hotspot name already exists.

The API is available under `/api/v1/hotspots`:

- `GET /api/v1/hotspots` lists hotspots (`limit` and `offset` are supported).
- `POST /api/v1/hotspots/bulk` accepts a JSON array of `{ "name", "lat", "lon" }`
  and creates or updates entries by name.

Example upload body:

```json
[
  {"name": "Kiambiu", "lat": -1.2822758, "lon": 36.8634101},
  {"name": "Dandora", "lat": -1.2449083, "lon": 36.9060802}
]
```

## Portfolio exposure ETL

Apply all database migrations with `alembic upgrade head`. Set `OPENAI_API_KEY`
in the backend environment for PDF and DOCX extraction. CSV files are parsed
directly. The API accepts `.csv`, text-based `.pdf`, and `.docx` uploads up to
`PORTFOLIO_UPLOAD_MAX_MB` (100 MB by default). Scanned PDFs need OCR and are
reported as a processing error when no text can be extracted.

Before approval, extracted and predicted rows are held in temporary review
storage keyed by portfolio ID. The portfolio-named final table is created and
populated only after the user approves the preview. Each approved portfolio
gets a separate physical table named from the sanitized portfolio name plus a
unique suffix. The response includes a one-time `access_token`; keep it
securely and send it as `X-Portfolio-Token` on every subsequent request. The
server stores only its hash.

1. `POST /api/v1/portfolios` with multipart form fields `name` and `file`.
2. Poll `GET /api/v1/portfolios/{id}/status` until extraction finishes, sending
   `X-Portfolio-Token: <access_token>`.
3. Inspect and edit rows through `GET` and `PATCH /api/v1/portfolios/{id}/preview`,
   sending the same token header.
4. `POST /api/v1/portfolios/{id}/predict` runs the existing six-output
   `random_forest_model/hazard_random_forest.joblib` pipeline.
5. `POST /api/v1/portfolios/{id}/confirm` queues the final table write. Poll
   status until it is `confirmed`, then download
   `GET /api/v1/portfolios/{id}/export.csv`, sending the same token header.
6. Optionally call `POST /api/v1/portfolios/{id}/email` with
   `{ "email": "recipient@example.com" }` and the token header to send the
   approved CSV using Brevo. Configure `BREVO_API_KEY` and
   `BREVO_SENDER_EMAIL`; attachments above `PORTFOLIO_EMAIL_MAX_MB` are rejected.

CSV parsing and database writes run in bounded batches. Incomplete, invalid,
empty, and duplicate exposure rows are dropped and counted in the portfolio
status. The trained model requires `lat`, `lon`, `housing_class`,
`floor_area_m2`, `cost_per_m2_kes`, and `tiv_kes`; those values must be present
before a record can be predicted.

## Authentication

Set `JWT_SECRET` in `.env` to a long random secret and optionally set
`JWT_ACCESS_TOKEN_MINUTES` (defaults to 60). Apply the users migration with
`alembic upgrade head`.

- `POST /api/v1/auth/signup` accepts `{ "email", "password" }` and creates an
  account with an Argon2 password hash.
- `POST /api/v1/auth/signin` accepts the same fields and returns a signed JWT
  access token.
- `GET /api/v1/auth/me` validates `Authorization: Bearer <token>` and returns
  the current account.

Passwords are never stored in plaintext. The token is signed, not encrypted;
do not place secrets in its claims. Existing portfolio routes continue to use
their portfolio access token until portfolios are linked to user accounts.
