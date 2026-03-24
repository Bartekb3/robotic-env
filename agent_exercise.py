import json
from os import system
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

class BaseHTTPTool(BaseTool):
    """Base class for tools that communicate with an HTTP robot API."""

    connector: HTTPConnector
    base_url: str

    name: str = ""
    description: str = ""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _get(self, path: str, timeout_sec: float = 10.0) -> dict | str:
        ... #todo: implement

    def _post(
        self, path: str, body: dict | None = None, timeout_sec: float = 10.0
    ) -> dict | str:
        ... #todo: implement

BASE_URL = "http://localhost:8000"

class GetObjectsTool(BaseHTTPTool):
    ... 


class GoToPositionTool(BaseHTTPTool):
    ...

class RotateTool(BaseHTTPTool):
    ...


class GrabTool(BaseHTTPTool):
    ...

class ReleaseTool(BaseHTTPTool):
    ...


class GetCameraTool(BaseHTTPTool):
    ...


def _build_tools(connector: HTTPConnector, base_url: str) -> List[BaseTool]:
    kwargs = dict(connector=connector, base_url=base_url)
    return [] # TODO: implement!

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
        system_prompt: str,
    ):
        tools = _build_tools(connector, base_url)
        llm = get_llm_model("complex_model", config_path="./config.toml")
        print(llm)
        super().__init__(
            target_connectors={},
            llm=llm,
            tools=tools,
            system_prompt=system_prompt,
        )

def run(system_prompt:str ,task: str) -> None:
    connector = HTTPConnector(host="localhost", port=9999, mode=HTTPConnectorMode.client)
    agent = RobotControllerAgent(system_prompt=system_prompt, connector=connector, base_url=BASE_URL)

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
    SYSTEM_PROMPT = (
        "You are a robot controller agent. Use the available tools to interact "
        "with the robot and complete the given task. Always check the current "
        "state before taking actions when it helps you plan."
    )
    task = (
        " ".join(sys.argv[1:])
        if len(sys.argv) > 1
        else "Describe what you see using your camera. Then go forward."
    )

    run(SYSTEM_PROMPT, task)
