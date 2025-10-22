from datetime import timedelta
from typing import Any

from src.config import (
    DITM_MODEL_API_URL,
)
from src.infrastructure._auth.http.authenticated_session import (
    _BearerAuthenticatedSession,
)
from src.models.predicted_load import PredictedGridAssetLoad
import pandas as pd


class _DitmPredictionPayload:
    def __init__(
        self, columns: list[str], index: list[int], data: list[Any], params: dict
    ) -> None:
        """Create a DITM predictions payload

        Args:
            columns (list[str]): The columns to perform inference on
            index (list[str]): The indexes
            data (list[Any]): The data
            params (dict): The parameters

        Returns:
            DitmPredictionPayload: The payload
        """
        self.columns = columns
        self.index = index
        self.data = data
        self.params = params

    def as_json(self) -> dict:
        data = {
            "input_data": {
                "columns": self.columns,
                "index": self.index,
                "data": self.data,
            },
            "params": self.params,
        }

        return data


def get_predictions_for_features(
    features: pd.DataFrame,
) -> list[PredictedGridAssetLoad]:
    """Get transformer load predictions between the start date (exclusive) and end date (inclusive).

    Args:
        features (pd.DataFrame): The features to make prediction(s) for.

    Returns:
        list[TransformerLoad]: The list of transformer load predictions
    """
    copied_features = features.copy()
    altered_features = copied_features.reset_index(drop=True).drop(columns=["datetime"])
    altered_features.fillna(0, inplace=True)

    session = _BearerAuthenticatedSession(scopes=["https://ml.azure.com/.default"])
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    payload = _DitmPredictionPayload(
        columns=[
            "year",
            "month",
            "day",
            "hour",
            "minute",
            "dayofyear",
            "dayofweek",
            "weekofyear",
            "is_weekend",
            "is_holiday",
            "lag_1_days",
            "lag_2_days",
            "lag_3_days",
            "lag_4_days",
            "lag_5_days",
            "lag_6_days",
            "lag_7_days",
            "lag_1_year",
            "temperature",
            "irradiation_duration",
            "irradiation",
            "cloud_coverage",
            "rain",
            "humidity",
            "snow",
            "scaled_profile",
        ],
        index=list(range(len(altered_features))),
        data=altered_features.values.tolist(),
        params={},
    )

    response = session.post(
        url=DITM_MODEL_API_URL, headers=headers, json=payload.as_json()
    )

    predictions = [float(x) for x in response.json()]

    if len(predictions) != len(features):
        raise ValueError("Features dataframe and predictions list did not match")

    loads: list[PredictedGridAssetLoad] = []

    for index, pred in enumerate(predictions):
        matching_df_row = features.iloc[index]
        datetime_of_load = matching_df_row["datetime"][0]
        converted = pd.to_datetime(datetime_of_load, utc=True).to_pydatetime()

        loads.append(
            PredictedGridAssetLoad(
                time=converted, duration=timedelta(minutes=15), load=pred
            )
        )

    return loads
