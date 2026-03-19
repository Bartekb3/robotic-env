from .base import SimObject


class Wall(SimObject):
    """An immovable rectangular obstacle."""

    def __init__(
        self,
        id: str,
        x: float,
        y: float,
        width: float,
        height: float,
        color: str = "#795548",
    ):
        super().__init__(id, x, y)
        self.width = width
        self.height = height
        self.color = color

    @property
    def type(self) -> str:
        return "wall"

    def get_aabb(self):
        hw, hh = self.width / 2, self.height / 2
        return (self.x - hw, self.y - hh, self.x + hw, self.y + hh)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "color": self.color,
        }
