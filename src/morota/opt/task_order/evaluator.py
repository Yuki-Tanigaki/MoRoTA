from __future__ import annotations

from dataclasses import replace
import math
from typing import TYPE_CHECKING, Dict, Mapping, Optional, Tuple

from morota.opt.task_order.representation import Individual
from morota.sim.module import Module

if TYPE_CHECKING:
    from morota.sim.model import ScenarioModel
    from morota.sim.agent.worker_agent import WorkerAgent

Pos = Tuple[float, float]


def dist(a: Pos, b: Pos) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


class ExpectedMakespanEvaluator:
    """
    Individual が表す「Route & RepairFlags」からメイクスパンの期待値を評価する Evaluator。

    - 故障は考慮しない（ただし疲労による性能期待値は更新する）
    - routes/repairs は dict keyed by worker_id を想定
    """

    def __init__(self, model: ScenarioModel):
        self.model = model

    def __call__(self, indiv: Individual) -> list[float]:
        makespan = 0.0

        for wid in indiv.worker_ids:
            worker = self.model.workers.get(wid)
            if worker is None:
                # 個体が参照してる worker がモデルにいない => 実行不能
                return [float("inf")]

            t_i = self._estimate_worker_time(worker, indiv)
            makespan = max(makespan, t_i)

        return [makespan]


    def _estimate_worker_time(self, worker: WorkerAgent, indiv: Individual) -> float:
        cfg = self.model.cfg
        wid = worker.worker_id

        route = list(indiv.routes.get(wid, []))
        flags = indiv.repairs.get(wid)

        if flags is None:
            flags = [False] * indiv.L_max
        elif len(flags) != indiv.L_max:
            # ここは ValueError でもOK（GA側のバグ検出用）
            raise ValueError(f"repairs[{wid}] length {len(flags)} != L_max={indiv.L_max}")

        # Evaluator内で modules を壊さない（Hのみ進める）
        modules: list[Module] = [replace(m) for m in worker.modules]

        cur = worker.pos
        depot_pos = self.model.depot.pos

        total = 0.0

        for i, task_id in enumerate(route):
            task = self.model.tasks.get(task_id)
            # すでに完了しているタスクは無視
            if task is None or task.status == "done":
                continue

            # ==================================================
            # reconstruction BEFORE task i
            # ==================================================
            if i < len(flags) and bool(flags[i]):
                exp_speed, exp_throughput = self._expected_performance(modules)
                go_d = dist(cur, depot_pos)
                if exp_speed <= 0.0 and go_d > 1e-6:
                    return float("inf")

                go_time = 0.0 if go_d < 1e-6 else go_d / exp_speed
                total += go_time
                self._advance_fatigue(modules, action="move", time=go_time)
                cur = depot_pos

                recon_t = float(cfg.sim.reconstruct_duration)
                total += recon_t

                # 再構成で不足モジュールを補充（H=0）
                if worker.declared_type is not None:
                    modules = self._apply_reconstruction(modules, declared_type=worker.declared_type)

            # ==================================================
            # (A) move to task
            # ==================================================
            exp_speed, exp_throughput = self._expected_performance(modules)
            if exp_speed <= 0.0 or exp_throughput <= 0.0:
                return float("inf")

            move_d = dist(cur, task.pos)
            move_time = move_d / exp_speed
            total += move_time
            self._advance_fatigue(modules, action="move", time=move_time)
            cur = task.pos

            # ==================================================
            # (B) do work
            # ==================================================
            exp_speed, exp_throughput = self._expected_performance(modules)
            if exp_speed <= 0.0 or exp_throughput <= 0.0:
                return float("inf")

            workload = task.remaining_work
            work_time = workload / exp_throughput
            total += work_time
            self._advance_fatigue(modules, action="work", time=work_time)

        return total

    # ==========================================================
    # fatigue / expected performance
    # ==========================================================
    def _advance_fatigue(self, modules: list[Module], action: str, time: float) -> None:
        if time <= 0.0:
            return
        rates = self.model.failure_model.fatigue(action)  # module_type -> rate
        for m in modules:
            rate = float(rates.get(m.type, 0.0))
            m.H += rate * time

    def _expected_performance(self, modules: list[Module]) -> tuple[float, float]:
        cfg = self.model.cfg
        fm = self.model.failure_model

        dist_by_type: dict[str, list[float]] = {}
        for t in cfg.robot_modules:
            ms = [m for m in modules if m.type == t]
            ps = []
            for m in ms:
                p_fail = float(fm.failure_prob(m.H))
                p_surv = max(0.0, min(1.0, 1.0 - p_fail))
                ps.append(p_surv)
            dist_by_type[t] = self._poisson_binomial_count_pmf(ps)

        joint = [({}, 1.0)]
        for t, pmf in dist_by_type.items():
            new_joint = []
            for counts, p0 in joint:
                for k, pk in enumerate(pmf):
                    if pk <= 0.0:
                        continue
                    cc = dict(counts)
                    cc[t] = k
                    new_joint.append((cc, p0 * pk))
            joint = new_joint

        sorted_types = sorted(cfg.robot_types.keys(), key=lambda n: cfg.type_priority.get(n, 10**9))

        prob_type: dict[Optional[str], float] = {None: 0.0}
        for r in sorted_types:
            prob_type.setdefault(r, 0.0)

        for counts, p in joint:
            rtype = self._infer_type_from_counts(counts, sorted_types)
            prob_type[rtype] = prob_type.get(rtype, 0.0) + p

        exp_speed = 0.0
        exp_throughput = 0.0
        for rtype, pr in prob_type.items():
            if not pr or rtype is None:
                continue
            spec = cfg.robot_types[rtype]
            exp_speed += pr * float(spec.speed)
            exp_throughput += pr * float(spec.throughput)

        return exp_speed, exp_throughput

    def _infer_type_from_counts(self, counts: Mapping[str, int], sorted_types: list[str]) -> Optional[str]:
        cfg = self.model.cfg
        for rtype in sorted_types:
            req = cfg.robot_types[rtype].required_modules
            ok = True
            for mod_type, need in req.items():
                if counts.get(mod_type, 0) < int(need):
                    ok = False
                    break
            if ok:
                return rtype
        return None

    def _poisson_binomial_count_pmf(self, ps: list[float]) -> list[float]:
        dp = [1.0]
        for p in ps:
            p = max(0.0, min(1.0, float(p)))
            nxt = [0.0] * (len(dp) + 1)
            for k, v in enumerate(dp):
                nxt[k] += v * (1.0 - p)
                nxt[k + 1] += v * p
            dp = nxt
        return dp

    def _apply_reconstruction(self, modules: list[Module], declared_type: str) -> list[Module]:
        cfg = self.model.cfg
        spec = cfg.robot_types.get(declared_type)
        if spec is None:
            return modules

        out: list[Module] = []
        counts: Dict[str, int] = {}

        for m in modules:
            # H / h の揺れ吸収
            if hasattr(m, "H"):
                m2 = replace(m, H=0.0)
            else:
                m2 = replace(m, h=0.0)

            out.append(m2)
            counts[m2.type] = counts.get(m2.type, 0) + 1

        for t, need in spec.required_modules.items():
            have = counts.get(t, 0)
            add = int(need) - int(have)
            if add <= 0:
                continue
            for _ in range(add):
                out.append(
                    Module(
                        id=-1,
                        type=t,
                        x=0.0,
                        y=0.0,
                        H=0.0,
                    )
                )

        return out
