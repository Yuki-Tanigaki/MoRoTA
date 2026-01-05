# MOROTA
Modular Robot Task Allocator

# Installation 
Ubuntuでの実行を想定
## Step 0 — Install **uv** and **ffmpeg**
```bash 
sudo apt update
sudo apt install ffmpeg
``` 

```bash 
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
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


uv run python scripts/analysis/estimate_contrib.py configs/robot_setup_norm.yml
uv run python scripts/analysis/gen_perf.py robots.yml --s0 0.2 --sB 0.4 --sL 0.15 --sW 0.55 --t0 0.0 --tB 1.2 --tL 0.7  --tW 0.2 --out robots_with_perf.yml

uv run python scripts/test_config_loader.py configs/toy_scenario.yml

uv run python scripts/run.py --scenario configs/toy_scenario.yml --seed 0000 --log-file
uv run solara run scripts/viz.py
uv run python scripts/gen_configs.py


