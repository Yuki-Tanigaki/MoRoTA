# MOROTA
Modular Robot Task Allocator

# Installation 
Ubuntuでの実行を想定
## Step 0 — Install **uv** and **ffmpeg**
```bash 
sudo apt update
sudo apt install uv 
sudo apt install ffmpeg
``` 

```bash 
uv --version 
```
```uv 0.9.5```のような表示が出ることを確認

## Step 1 — Clone project 
```bash 
git 
cd MOROTA
```
## Step 2 — Create virtual environment & install dependencies
```bash 
uv venv source.venv/bin/activate  
uv sync 
```


uv run python scripts/scenario_maker/generate_tasks.py --n 50 --width 100 --height 100 --out configs/tasks_sobol.csv --seed 0 --method sobol
uv run python scripts/scenario_maker/generate_tasks.py --n 50 --width 100 --height 100 --out configs/tasks_lattice.csv --seed 0 --method lattice
uv run python scripts/scenario_maker/generate_tasks.py --n 50 --width 100 --height 100 --out configs/tasks_circle.csv --seed 0 --method circle
uv run python scripts/analysis/plot_tasks.py --width 100 --height 100 --file configs/tasks_sobol.csv --out figures/tasks_sobol.pdf
uv run python scripts/analysis/plot_tasks.py --width 100 --height 100 --file configs/tasks_lattice.csv --out figures/tasks_lattice.pdf
uv run python scripts/analysis/plot_tasks.py --width 100 --height 100 --file configs/tasks_circle.csv --out figures/tasks_circle.pdf

uv run python scripts/scenario_maker/generate_modules.py --n 100 --width 100 --height 100 --out configs/modules_100_244.csv --seed 0 --type Body Limb Wheel --ratio 2 4 4
uv run python scripts/scenario_maker/generate_modules.py --n 200 --width 100 --height 100 --out configs/modules_200_244.csv --seed 0 --type Body Limb Wheel --ratio 2 4 4
uv run python scripts/scenario_maker/generate_modules.py --n 100 --width 100 --height 100 --out configs/modules_100_253.csv --seed 0 --type Body Limb Wheel --ratio 2 5 3
uv run python scripts/scenario_maker/generate_modules.py --n 200 --width 100 --height 100 --out configs/modules_200_253.csv --seed 0 --type Body Limb Wheel --ratio 2 5 3
uv run python scripts/scenario_maker/generate_modules.py --n 100 --width 100 --height 100 --out configs/modules_100_235.csv --seed 0 --type Body Limb Wheel --ratio 2 3 5
uv run python scripts/scenario_maker/generate_modules.py --n 200 --width 100 --height 100 --out configs/modules_200_235.csv --seed 0 --type Body Limb Wheel --ratio 2 3 5

uv run python scripts/analysis/estimate_contrib.py configs/robot_setup_norm.yaml
uv run python scripts/analysis/gen_perf.py robots.yaml --s0 0.2 --sB 0.4 --sL 0.15 --sW 0.55 --t0 0.0 --tB 1.2 --tL 0.7  --tW 0.2 --out robots_with_perf.yaml

uv run python scripts/test_config_loader.py configs/toy_scenario.yaml





