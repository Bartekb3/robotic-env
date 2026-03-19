# Robotic Agent Environment

Developed for purposes of Agents and Multi-Agent Systems course at Warsaw University of Technology 2026.

## Requirements

Python 3.12.12

For the local setup a GPU with 8+GB VRAM is reccomended.

## Installation

```
pip install -r requirements.txt
```

## Running

First run the simulation and server in one terminal:

```
uvicorn main:app
```

Then in the second terminal run:
```
python agent_exercise.py
```

To run the agent.
