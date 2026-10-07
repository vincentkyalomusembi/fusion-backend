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