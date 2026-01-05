# uv run python scripts/scenario_maker/generate_tasks.py --n 49 --width 100 --height 100 --out configs/datasets/tasks_sobol.csv --seed 0 --method sobol
# uv run python scripts/scenario_maker/generate_tasks.py --n 49 --width 100 --height 100 --out configs/datasets/tasks_lattice.csv --seed 0 --method lattice
# uv run python scripts/scenario_maker/generate_tasks.py --n 49 --width 100 --height 100 --out configs/datasets/tasks_circle.csv --seed 0 --method circle
# uv run python scripts/analysis/plot_tasks.py --width 100 --height 100 --file configs/datasets/tasks_sobol.csv --out figures/tasks_sobol.pdf --title "Sobol"
# uv run python scripts/analysis/plot_tasks.py --width 100 --height 100 --file configs/datasets/tasks_lattice.csv --out figures/tasks_lattice.pdf --title "Lattice"
# uv run python scripts/analysis/plot_tasks.py --width 100 --height 100 --file configs/datasets/tasks_circle.csv --out figures/tasks_circle.pdf --title "Circle"

uv run python scripts/scenario_maker/generate_modules.py --n 100 --width 100 --height 100 --out configs/modules_100_244.csv --seed 0 --type Body Limb Wheel --ratio 2 4 4
uv run python scripts/scenario_maker/generate_modules.py --n 200 --width 100 --height 100 --out configs/modules_200_244.csv --seed 0 --type Body Limb Wheel --ratio 2 4 4
uv run python scripts/scenario_maker/generate_modules.py --n 100 --width 100 --height 100 --out configs/modules_100_154.csv --seed 0 --type Body Limb Wheel --ratio 1 5 4
uv run python scripts/scenario_maker/generate_modules.py --n 200 --width 100 --height 100 --out configs/modules_200_154.csv --seed 0 --type Body Limb Wheel --ratio 1 5 4