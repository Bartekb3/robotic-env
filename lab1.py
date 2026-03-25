"""
Robot controller agent using the RAI framework with HTTPConnector.

Usage:
    python environment_test.py "Pick up the red object and move it to position (5, 5)"
    python environment_test.py  # defaults to a state-check task
"""

import json
import sys
from typing import Dict, List, Literal, Optional, Tuple, Type

from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from rai.agents.langchain.react_agent import ReActAgent
from rai.communication.hri_connector import HRIMessage
from rai.communication.http.api import HTTPConnectorMode
from rai.communication.http.connectors import HTTPConnector
from rai.communication.http.messages import HTTPMessage
from rai.initialization import get_llm_model
from rai.messages import MultimodalArtifact

BASE_URL = "http://localhost:8000"


# ---------------------------------------------------------------------------
# BaseHTTPTool – analogous to BaseROS2Tool, but for HTTPConnector
# ---------------------------------------------------------------------------


class BaseHTTPTool(BaseTool):
    """Base class for tools that communicate with an HTTP robot API."""

    connector: HTTPConnector
    base_url: str

    name: str = ""
    description: str = ""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _get(self, path: str, timeout_sec: float = 10.0) -> dict | str:
        msg = HTTPMessage(method="GET", payload=None)
        resp = self.connector.service_call(
            msg, f"{self.base_url}{path}", timeout_sec=timeout_sec
        )
        try:
            return json.loads(resp.payload)
        except Exception:
            return resp.payload

    def _post(
        self, path: str, body: dict | None = None, timeout_sec: float = 10.0
    ) -> dict | str:
        msg = HTTPMessage(method="POST", payload=body)
        resp = self.connector.service_call(
            msg, f"{self.base_url}{path}", timeout_sec=timeout_sec
        )
        try:
            return json.loads(resp.payload)
        except Exception:
            return resp.payload


# ---------------------------------------------------------------------------
# Tool input schemas
# ---------------------------------------------------------------------------


class _NoArgs(BaseModel):
    pass


class _GoToPositionInput(BaseModel):
    x: float = Field(..., description="Target X coordinate")
    y: float = Field(..., description="Target Y coordinate")


class _RotateInput(BaseModel):
    angle: float = Field(
        ..., description="Absolute heading in degrees (0=north, clockwise)"
    )


# ---------------------------------------------------------------------------
# Concrete tools
# ---------------------------------------------------------------------------


class GetStateTool(BaseHTTPTool):
    name: str = "get_state"
    description: str = (
        "Get full world snapshot: robot position/heading, all objects, and world metadata."
    )
    args_schema: Type[_NoArgs] = _NoArgs

    def _run(self) -> str:
        return json.dumps(self._get("/state"))


class GetObjectsTool(BaseHTTPTool):
    name: str = "get_objects"
    description: str = "Get all non-robot objects currently in the world."
    args_schema: Type[_NoArgs] = _NoArgs

    def _run(self) -> str:
        return json.dumps(self._get("/objects"))


class GoToPositionTool(BaseHTTPTool):
    name: str = "go_to_position"
    description: str = (
        "Move the robot to (x, y). Movement happens over time; call returns immediately."
    )
    args_schema: Type[_GoToPositionInput] = _GoToPositionInput

    def _run(self, x: float, y: float) -> str:
        return json.dumps(self._post("/go_to_position", {"x": x, "y": y}))


class RotateTool(BaseHTTPTool):
    name: str = "rotate"
    description: str = "Rotate the robot to an absolute heading. 0=north, clockwise."
    args_schema: Type[_RotateInput] = _RotateInput

    def _run(self, angle: float) -> str:
        return json.dumps(self._post("/rotate", {"angle": angle}))


class GrabTool(BaseHTTPTool):
    name: str = "grab"
    description: str = "Pick up the nearest grabbable object within grab_range."
    args_schema: Type[_NoArgs] = _NoArgs

    def _run(self) -> str:
        return json.dumps(self._post("/grab"))


class ReleaseTool(BaseHTTPTool):
    name: str = "release"
    description: str = "Drop the currently held object in front of the robot."
    args_schema: Type[_NoArgs] = _NoArgs

    def _run(self) -> str:
        return json.dumps(self._post("/release"))


class ResetTool(BaseHTTPTool):
    name: str = "reset"
    description: str = "Restore the world to its initial state from config.json."
    args_schema: Type[_NoArgs] = _NoArgs

    def _run(self) -> str:
        return json.dumps(self._post("/reset"))


class GetCameraTool(BaseHTTPTool):
    name: str = "get_camera"
    description: str = (
        "Capture a PNG frame from the robot's POV camera. Returns the image for visual inspection."
    )
    args_schema: Type[_NoArgs] = _NoArgs
    response_format: Literal["content", "content_and_artifact"] = "content_and_artifact"

    def _run(self) -> Tuple[str, MultimodalArtifact]:
        result = self._get("/camera")
        if isinstance(result, dict) and "image" in result:
            return "Camera image from robot POV:", MultimodalArtifact(
                images=[result["image"]], audios=[]
            )
        return json.dumps(result), MultimodalArtifact(images=[], audios=[])


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are a robot controller agent. Use the available tools to interact "
    "with the robot and complete the given task. Always check the current "
    "state before taking actions when it helps you plan."
)


def _build_tools(connector: HTTPConnector, base_url: str) -> List[BaseTool]:
    kwargs = dict(connector=connector, base_url=base_url)
    return [
            # GetStateTool(**kwargs),
        GetObjectsTool(**kwargs),
        GoToPositionTool(**kwargs),
        RotateTool(**kwargs),
        GrabTool(**kwargs),
        ReleaseTool(**kwargs),
        ResetTool(**kwargs),
        GetCameraTool(**kwargs),
    ]


class RobotControllerAgent(ReActAgent):
    """ReActAgent pre-configured for HTTP robot control.

    Parameters
    ----------
    connector:
        An HTTPConnector in client mode pointed at the robot API.
    base_url:
        Base URL of the robot HTTP API (e.g. ``"http://localhost:8080"``).
    llm:
        LangChain chat model to use. Defaults to ``get_llm_model("complex_model")``.
    """

    def __init__(
        self,
        connector: HTTPConnector,
        base_url: str,
    ):
        tools = _build_tools(connector, base_url)
        llm = get_llm_model("complex_model", config_path="./config.toml")
        print(llm)
        super().__init__(
            target_connectors={},
            llm=llm,
            tools=tools,
            system_prompt=SYSTEM_PROMPT,
        )


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------


def run(task: str) -> None:
    connector = HTTPConnector(host="localhost", port=9999, mode=HTTPConnectorMode.client)
    agent = RobotControllerAgent(connector=connector, base_url=BASE_URL)

    print(f"\nTask: {task}\n{'=' * 60}")

    agent.run()
    agent(HRIMessage(text=task, message_author="human"))
    agent.wait()
    agent.stop()

    # Print the last AI response from accumulated state
    for msg in reversed(agent.state["messages"]):
        if isinstance(msg, AIMessage) and msg.content:
            content = msg.content
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        print(f"\nAgent: {block['text']}")
            else:
                print(f"\nAgent: {content}")
            break

    connector.shutdown()


if __name__ == "__main__":
    task = (
        " ".join(sys.argv[1:])
        if len(sys.argv) > 1
        else "Describe what you see using your camera. Then go forward."
    )
    run(task)

