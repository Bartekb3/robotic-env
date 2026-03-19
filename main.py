"""
Robotic Environment — FastAPI server
=====================================
Serves the Three.js viewer and exposes the robot control HTTP API.

Run with:
    uvicorn main:app --reload

API summary
-----------
GET  /state             — full simulation snapshot
GET  /objects           — list of all non-robot objects
POST /go_to_position    — move robot toward {x, y}
POST /rotate            — rotate robot to absolute heading {angle} (degrees)
POST /grab              — pick up nearest grabbable object in range
POST /release           — drop currently held object
POST /reset             — restore world to config.json initial state
GET  /camera            — render one frame from the robot's on-board camera
                          (requires a connected browser tab)
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from simulation.world import World

# --------------------------------------------------------------------------- #
#  Global state                                                                #
# --------------------------------------------------------------------------- #

world = World("config.json")
_clients: list[WebSocket] = []
_camera_future: Optional[asyncio.Future] = None

# --------------------------------------------------------------------------- #
#  Background simulation loop                                                  #
# --------------------------------------------------------------------------- #

TICK_DT = 0.05  # seconds  →  20 Hz


async def _simulation_loop():
    while True:
        world.tick(TICK_DT)
        await _broadcast({"type": "state", "data": world.get_state()})
        await asyncio.sleep(TICK_DT)


async def _broadcast(message: dict):
    dead = []
    for ws in _clients:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in _clients:
            _clients.remove(ws)


# --------------------------------------------------------------------------- #
#  App lifecycle                                                               #
# --------------------------------------------------------------------------- #

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_simulation_loop())
    yield
    task.cancel()


app = FastAPI(title="Robotic Environment", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------------------------------- #
#  WebSocket                                                                   #
# --------------------------------------------------------------------------- #

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    global _camera_future
    await websocket.accept()
    _clients.append(websocket)
    # Push current state immediately so the viewer initialises without waiting
    await websocket.send_json({"type": "state", "data": world.get_state()})
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "camera_frame":
                if _camera_future and not _camera_future.done():
                    _camera_future.set_result(data["data"])
    except WebSocketDisconnect:
        if websocket in _clients:
            _clients.remove(websocket)

# --------------------------------------------------------------------------- #
#  Request models                                                              #
# --------------------------------------------------------------------------- #

class PositionBody(BaseModel):
    x: float
    y: float

class RotateBody(BaseModel):
    angle: float  # degrees, 0 = north (+Y), clockwise

# --------------------------------------------------------------------------- #
#  REST endpoints                                                              #
# --------------------------------------------------------------------------- #

@app.get("/state", summary="Full simulation snapshot")
async def get_state():
    """Returns robot pose, all object states, and world metadata."""
    return world.get_state()


@app.get("/objects", summary="List all non-robot objects")
async def get_objects():
    """Returns current state of every object in the world."""
    return world.get_objects()


@app.post("/go_to_position", summary="Move robot to a position")
async def go_to_position(body: PositionBody):
    """
    Begin moving the robot toward (x, y).  Returns immediately.
    The robot faces the target direction and moves at its configured speed.
    Poll `/state` or subscribe via WebSocket to know when it arrives
    (is_moving will be false).
    """
    world.robot.set_target(body.x, body.y)
    return {"status": "ok", "target": {"x": body.x, "y": body.y}}


@app.post("/rotate", summary="Rotate robot to an absolute heading")
async def rotate(body: RotateBody):
    """
    Begin rotating to the given absolute heading in degrees.
    0 = north (+Y), 90 = east (+X), increases clockwise.
    Returns immediately; poll `is_rotating` in /state to detect completion.
    """
    world.robot.set_rotation_target(body.angle)
    return {"status": "ok", "target_angle": body.angle}


@app.post("/grab", summary="Grab nearest grabbable object")
async def grab():
    """
    Attempt to pick up the closest grabbable object within grab_range.
    The object will follow the robot until released.
    """
    return world.grab()


@app.post("/release", summary="Release currently held object")
async def release():
    """
    Drop the currently held object slightly in front of the robot.
    """
    return world.release()


@app.post("/reset", summary="Reset world to initial config state")
async def reset():
    """Restores all positions and states from config.json."""
    world.reset()
    await _broadcast({"type": "state", "data": world.get_state()})
    return {"status": "ok"}


@app.get("/camera", summary="Render one frame from the robot's camera")
async def get_camera():
    """
    Requests a single rendered frame from the robot's on-board perspective
    camera.  The browser renders the scene from the robot's POV and returns
    the image as a base64-encoded PNG string.

    Requires at least one browser tab connected via WebSocket.
    Times out after 5 seconds if no frame is received.

    Response: { "image": "<base64 PNG>" }
    """
    global _camera_future

    if not _clients:
        return JSONResponse(
            status_code=503,
            content={"error": "No viewer connected — open the browser tab first"},
        )

    # Cancel any stale pending request
    if _camera_future and not _camera_future.done():
        _camera_future.cancel()

    _camera_future = asyncio.get_running_loop().create_future()
    await _broadcast({"type": "camera_request"})

    try:
        image_data = await asyncio.wait_for(_camera_future, timeout=5.0)
        return {"image": image_data}
    except asyncio.TimeoutError:
        return JSONResponse(status_code=504, content={"error": "Camera render timed out"})


# --------------------------------------------------------------------------- #
#  Static files  (must be last — catches everything not matched above)        #
# --------------------------------------------------------------------------- #

app.mount("/", StaticFiles(directory="static", html=True), name="static")
