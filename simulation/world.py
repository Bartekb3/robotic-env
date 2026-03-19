import copy
import json
import math
from typing import Optional

from .objects.ball import Ball
from .objects.base import SimObject
from .objects.robot import Robot
from .objects.wall import Wall

# Register object types here to make them available in JSON configs.
# Extend this dict when you add new SimObject subclasses.
OBJECT_REGISTRY: dict[str, type] = {
    "wall": Wall,
    "ball": Ball,
}


class World:
    """
    Holds the full simulation state and advances it each tick.

    Loading / reset
    ---------------
    The world is initialised from a JSON config file.  Calling `reset()`
    restores everything to the state described in that file.

    Tick
    ----
    Call `tick(dt)` at a fixed rate from an async loop.  It moves the robot,
    resolves wall collisions, clamps world bounds, and drags held objects.

    Extending
    ---------
    - Register new object types in OBJECT_REGISTRY.
    - Add them to the JSON config under "objects".
    """

    def __init__(self, config_path: str):
        self.config_path = config_path
        self._initial_config: dict = {}
        self.robot: Robot
        self.objects: dict[str, SimObject] = {}
        self.size_x = 20.0
        self.size_y = 20.0
        self.background_color = "#87CEEB"
        self._load(config_path)

    # ------------------------------------------------------------------ #
    #  Loading                                                             #
    # ------------------------------------------------------------------ #

    def _load(self, path: str):
        with open(path) as f:
            config = json.load(f)
        self._initial_config = copy.deepcopy(config)
        self._apply_config(config)

    def _apply_config(self, config: dict):
        w = config.get("world", {})
        self.size_x = float(w.get("size_x", 20.0))
        self.size_y = float(w.get("size_y", 20.0))
        self.background_color = w.get("background_color", "#87CEEB")

        r = config.get("robot", {})
        self.robot = Robot(
            id=r.get("id", "robot"),
            x=float(r.get("x", 0.0)),
            y=float(r.get("y", 0.0)),
            rotation=float(r.get("rotation", 0.0)),
            speed=float(r.get("speed", 3.0)),
            rotation_speed=float(r.get("rotation_speed", 180.0)),
            grab_range=float(r.get("grab_range", 1.5)),
            camera_fov=float(r.get("camera_fov", 60.0)),
        )

        self.objects = {}
        for obj_cfg in config.get("objects", []):
            obj = self._create_object(obj_cfg)
            if obj:
                self.objects[obj.id] = obj

    def _create_object(self, cfg: dict) -> Optional[SimObject]:
        cls = OBJECT_REGISTRY.get(cfg.get("type", ""))
        if cls is None:
            return None
        kwargs = {k: v for k, v in cfg.items() if k != "type"}
        return cls(**kwargs)

    # ------------------------------------------------------------------ #
    #  Simulation tick                                                     #
    # ------------------------------------------------------------------ #

    def tick(self, dt: float):
        old_x, old_y = self.robot.x, self.robot.y
        self.robot.tick(dt)

        # Revert robot on wall collision
        for obj in self.objects.values():
            if obj.type == "wall" and self.robot.overlaps(obj):
                self.robot.x = old_x
                self.robot.y = old_y
                self.robot._target_x = None
                self.robot._target_y = None
                break

        # Clamp to world bounds
        r = self.robot.RADIUS
        self.robot.x = max(-self.size_x / 2 + r, min(self.size_x / 2 - r, self.robot.x))
        self.robot.y = max(-self.size_y / 2 + r, min(self.size_y / 2 - r, self.robot.y))

        # Drag held object with robot
        if self.robot.held_object and self.robot.held_object in self.objects:
            held = self.objects[self.robot.held_object]
            held.x = self.robot.x
            held.y = self.robot.y

    # ------------------------------------------------------------------ #
    #  Actions                                                             #
    # ------------------------------------------------------------------ #

    def grab(self) -> dict:
        if self.robot.held_object:
            return {"status": "error", "message": "Already holding an object"}

        best: Optional[SimObject] = None
        best_dist = float("inf")

        for obj in self.objects.values():
            if not getattr(obj, "is_grabbable", False):
                continue
            if getattr(obj, "grabbed", False):
                continue
            dx, dy = obj.x - self.robot.x, obj.y - self.robot.y
            dist = math.sqrt(dx * dx + dy * dy)
            if dist <= self.robot.grab_range and dist < best_dist:
                best, best_dist = obj, dist

        if best is None:
            return {"status": "error", "message": "No grabbable object in range"}

        best.grabbed = True  # type: ignore[attr-defined]
        self.robot.held_object = best.id
        return {"status": "ok", "grabbed": best.id}

    def release(self) -> dict:
        if not self.robot.held_object:
            return {"status": "error", "message": "Not holding anything"}

        obj_id = self.robot.held_object
        self.robot.held_object = None

        if obj_id in self.objects:
            obj = self.objects[obj_id]
            obj.grabbed = False  # type: ignore[attr-defined]
            # Drop slightly in front of the robot
            rot_rad = math.radians(self.robot.rotation)
            drop_dist = self.robot.RADIUS + getattr(obj, "radius", 0.3) + 0.15
            obj.x = self.robot.x + math.sin(rot_rad) * drop_dist
            obj.y = self.robot.y + math.cos(rot_rad) * drop_dist

        return {"status": "ok", "released": obj_id}

    def reset(self):
        self._apply_config(copy.deepcopy(self._initial_config))

    # ------------------------------------------------------------------ #
    #  Serialisation                                                       #
    # ------------------------------------------------------------------ #

    def get_state(self) -> dict:
        return {
            "robot": self.robot.to_dict(),
            "objects": [obj.to_dict() for obj in self.objects.values()],
            "world": {
                "size_x": self.size_x,
                "size_y": self.size_y,
                "background_color": self.background_color,
            },
        }

    def get_objects(self) -> list:
        return [obj.to_dict() for obj in self.objects.values()]
