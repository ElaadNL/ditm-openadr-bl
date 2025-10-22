"""Module containing models representing predicted load on a grid asset."""

from datetime import datetime, timedelta


class PredictedGridAssetLoad:
    """Represents the load on a grid asset at a specific time."""

    def __init__(
        self, time: datetime, load: float, duration: timedelta = timedelta(minutes=15)
    ) -> None:
        """Initializes a predicted grid asset load object.

        Args:
            time (datetime): The time of the prediction.
            load (float): The load on the grid asset.
            duration (timedelta): The duration of the prediction. Defaults to 15 minutes.
        """
        self.time = time
        self.duration = duration
        self.load = load

    def __eq__(self, other) -> bool:
        """Implement value based equality instead of reference based.

        Args:
            other: The value to compare
        """
        if isinstance(other, PredictedGridAssetLoad):
            return (
                self.time == other.time
                and self.load == other.load
                and self.duration == other.duration
            )

        return False

    def flex_capacity_required(self, max_capacity: float) -> float | None:
        """Returns the flex capacity needed for this predicted grid asset load period.

        The required flex capacity is the difference between the predicted load and the
        maximum capacity provided to this function. If the predicted load is less than the
        maximum capacity, no flex capacity is needed and None is returned.

        If the predicted load is greater than the maximum capacity, the required flex
        capacity is returned in kW.

        Args:
            load (PredictedGridAssetLoad): The predicted grid asset load at a given time.
            max_capacity (float): The (virtual) max capacity of the grid asset.

        Returns:
            float: The amount of kw of flex which is needed for this grid asset load period.
        """
        min_guaranteed_capacity = 4
        max_capacity_of_pod = (
            22  # TODO: configure based on input from actual battery when available.
        )
        max_excess = 50

        excess_load = self.load - max_capacity
        if excess_load <= 0:
            return 0  # not exceeding capacity

        # Linear scaling from min_value to max_value
        scaled = min_guaranteed_capacity + (
            max_capacity_of_pod - min_guaranteed_capacity
        ) * (excess_load / max_excess)

        # Cap to max_value
        return min(max_capacity_of_pod, scaled)
