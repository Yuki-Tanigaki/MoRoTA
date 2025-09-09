# ModularRobotTaskAllocator

## Basic Concepts
A task allocation system for modular robots

## Installation

This project uses [Poetry](https://python-poetry.org/) for dependency and environment management.

### 1. Install Poetry (if not already installed)

```bash
pip install poetry
```

### 2. Clone the Repository

```bash
git clone git@github.com:Yuki-Tanigaki/MoRoTA.git
cd MoRoTA
```

### 3. Install Dependencies
```bash
poetry install
```

### 4. Activate the Virtual Environment
```bash
poetry env activate
```

### (optional) Use Poetry’s virtual environment in VS Code
1) Get the Poetry venv path
```bash
poetry env info --path
```

2) Tell VS Code to use that interpreter
Create .vscode/settings.json and paste the path you copied:
```json
{
  "python.defaultInterpreterPath": "/absolute/path/from/poetry/env/bin/python"
}
```  
Choose the interpreter inside the Poetry environment you copied above:  
macOS/Linux: <…>/bin/python  
Windows: <…>\Scripts\python.exe  

## How to Use
### Install


### Run Tests
```
poetry run pytest -s
```

### Run mypy
```
poetry run mypy modutask/core/
```

### Run Robot-Configuration
```python
poetry run python optimize_configuration.py --property_file configs/optimize_configuration_sample/property.yaml
```

### Run Task-allocation
```python
poetry run python modutask/task_allocation.py --property_file configs/task_allocation_sample/property.yaml
```


### Run Simulation
```python
poetry run python simulation_launcher.py --property_file configs/simulation_sample/property.yaml
```