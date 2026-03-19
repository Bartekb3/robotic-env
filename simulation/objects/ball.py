from .base import SimObject


class Ball(SimObject):
    """A grabbable ball that can be picked up and carried by the robot."""

    is_grabbable = True

    def __init__(
        self,
        id: str,
        x: float,
        y: float,
        radius: float = 0.3,
        color: str = "#F44336",
    ):
        super().__init__(id, x, y)
        self.radius = radius
        self.color = color
        self.grabbed = False

    @property
    def type(self) -> str:
        return "ball"

    def get_aabb(self):
        return (
            self.x - self.radius,
            self.y - self.radius,
            self.x + self.radius,
            self.y + self.radius,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "x": self.x,
            "y": self.y,
            "radius": self.radius,
            "color": self.color,
            "grabbed": self.grabbed,
        }
