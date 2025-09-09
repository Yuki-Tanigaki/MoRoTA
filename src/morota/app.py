import solara as sl
from mesa.visualization import SolaraViz, SpaceRenderer, make_plot_component
from mesa.visualization.components import AgentPortrayalStyle, PropertyLayerStyle
from model_foodworld import FoodWorld, Walker, Food

# --- エージェントの見た目（portrayal） ---
def agent_portrayal(agent):
    if isinstance(agent, Walker):
        # エネルギーでサイズ変化（視覚的な手がかり）
        size = max(20, min(80, 20 + 8 * agent.energy))
        return AgentPortrayalStyle(marker="o", size=size)  # 色はデフォルト
    if isinstance(agent, Food):
        return AgentPortrayalStyle(marker="s", size=40)   # 四角で描画
    return AgentPortrayalStyle()

# --- UI から触れるモデルパラメータ ---
model_params = {
    "width": 20,
    "height": 20,
    "n_walkers": {"type": "SliderInt", "value": 10, "label": "Walkers", "min": 1, "max": 80, "step": 1},
    "n_food": {"type": "SliderInt", "value": 40, "label": "Food", "min": 0, "max": 300, "step": 5},
    "food_energy": {"type": "SliderInt", "value": 3, "label": "Food Energy", "min": 1, "max": 10, "step": 1},
    "food_spawn": {"type": "SliderInt", "value": 0, "label": "Food spawn/step", "min": 0, "max": 5, "step": 1},
    "seed": {"type": "SliderInt", "value": 0, "label": "Seed", "min": 0, "max": 99999, "step": 1},
}

# --- 初期モデル & レンダラ（matplotlib / altair どちらでも可） ---
initial_model = FoodWorld(**{k: (v["value"] if isinstance(v, dict) else v) for k, v in model_params.items()})
renderer = SpaceRenderer(model=initial_model, backend="matplotlib").render(
    agent_portrayal=agent_portrayal
)

# --- 時系列プロット（DataCollector のキー名で指定） ---
WalkersPlot = make_plot_component("Walkers", page=1)
FoodPlot    = make_plot_component("Food", page=1)
EnergyPlot  = make_plot_component("MeanEnergy", page=1)

# --- Solara ページ（ブラウザUI） ---
page = SolaraViz(
    initial_model,
    renderer,
    components=[WalkersPlot, FoodPlot, EnergyPlot],  # ページ1に折れ線グラフ
    model_params=model_params,
    name="Mesa 3 Demo: Walker & Food",
)

# Jupyter の場合は `page` を最後に評価するだけでOK／
# スクリプトとしては `solara run app.py` でブラウザが開く
