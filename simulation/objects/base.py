from abc import ABC, abstractmethod
from typing import Tuple


class SimObject(ABC):
    """
    Abstract base class for all objects in the simulation.

    Subclass this to add new environment objects.  The only requirements are:
      - a unique `id` and a 2-D position `(x, y)`
      - a string `type` property used by the renderer
      - an AABB for lightweight collision detection
      - a `to_dict()` serialiser for the state broadcast
    """

    def __init__(self, id: str, x: float, y: float):
        self.id = id
        self.x = x
        self.y = y

    # ------------------------------------------------------------------ #
    #  Abstract interface                                                  #
    # ------------------------------------------------------------------ #

    @property
    @abstractmethod
    def type(self) -> str:
        """Short type identifier, e.g. 'wall', 'ball'."""

    @abstractmethod
    def get_aabb(self) -> Tuple[float, float, float, float]:
        """Return axis-aligned bounding box: (min_x, min_y, max_x, max_y)."""

    @abstractmethod
    def to_dict(self) -> dict:
        """Serialise full object state to a plain dictionary."""

    # ------------------------------------------------------------------ #
    #  Shared helpers                                                      #
    # ------------------------------------------------------------------ #

    def overlaps(self, other: "SimObject") -> bool:
        """AABB overlap test against another SimObject."""
        ax1, ay1, ax2, ay2 = self.get_aabb()
        bx1, by1, bx2, by2 = other.get_aabb()
        return ax1 < bx2 and ax2 > bx1 and ay1 < by2 and ay2 > by1
