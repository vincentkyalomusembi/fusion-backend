# Run from the repo root: python -m CAT_model.test
from CAT_model.vulnerability import damage_ratio

damage_value = damage_ratio("concrete_rcc", 0.23)
damage_percent = damage_value * 100

print(f"{damage_percent:.2f}") #output 16.06

import pandas as pd

from app.services.ml.model_loader import load_model

model = load_model()

# The hazard model only takes location - housing class and TIV are used in the damage step.
X_new = pd.DataFrame([{"lat": -1.257597, "lon": 36.896201}])

prediction = model.predict(X_new)
print(prediction) # 6 values: common, occasional, moderate, severe, extreme tier scores + hazard_severity
