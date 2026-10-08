from vulnerability import damage_ratio

damage_value = damage_ratio("concrete_rcc", 0.23)
damage_percent = damage_value * 100

print(f"{damage_percent:.2f}") #output 16.06

import joblib
import pandas as pd

model = joblib.load("../random_forest_model/hazard_random_forest.joblib")

X_new = pd.DataFrame(
    [
        {
            "lat": -1.257597,
            "lon": 36.896201,
            "housing_class": "permanent_masonry",
            "floor_area_m2": 40,
            "cost_per_m2_kes": 25000,
            "tiv_kes": 1000000,
        }
    ]
)

prediction = model.predict(X_new)
print(prediction) #output [[0.22435766 0.16783469 0.12718236 0.08520667 0.05449901 0.516     ]]