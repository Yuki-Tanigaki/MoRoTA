from __future__ import annotations

from typing import Mapping, Optional

from morota.opt.robot_conf.representation import Individual


class ConfigurationEvaluator:
    def __init__(
        self,
        cfg,
        default_p_fail: float = 0.05,
        p_fail_by_type: Optional[Mapping[str, float]] = None,
    ) -> None:
        self.cfg = cfg
        self.default_p_fail = float(default_p_fail)
        self.p_fail_by_type = dict(p_fail_by_type) if p_fail_by_type is not None else None
        self.worst_objectives = (float("inf"), float("inf"))

        # model は外から注入される想定（evaluator.model = model）
        self.model = None  # type: ignore[assignment]

    def __call__(self, indiv: Individual) -> list[float]:
        cfg = self.cfg
        model = self.model
        if model is None:
            raise ValueError("ConfigurationEvaluator.model is not set. Do `evaluator.model = model`.")

        # --- constraints ---
        # violation = self._remove_constraint_violation(indiv)
        # if violation > 0:
        #     return [violation, violation]

        if self._violates_depot_capacity(indiv):
            return [self.worst_objectives[0], self.worst_objectives[1]]
        
        if self._violates_all_none(indiv):
            return [self.worst_objectives[0], self.worst_objectives[1]]

        # --- objectives ---
        total_nominal = 0.0

        for i, rt in enumerate(indiv.worker_types):
            if rt is None:
                continue

            spec = cfg.robot_types.get(rt)
            if spec is None:
                continue

            total_nominal += float(spec.speed) + float(spec.throughput)

        # total_potential = self._fatigue_based_potential_global()
        # total_potential = self._fatigue_based_potential_global_surplus(indiv)
        reserve_variation = self._reserve_variation_min_remain(indiv)

        return [-total_nominal, -reserve_variation]


    def _compute_need_total(self, indiv: Individual) -> Optional[dict[str, int]]:
        cfg = self.cfg
        model = self.model

        need_total: dict[str, int] = {}

        for i, desired in enumerate(indiv.worker_types):
            if desired is None:
                continue

            spec = cfg.robot_types.get(desired)
            if spec is None:
                raise ValueError(f"Unknown robot_type '{desired}' in individual.")

            w = model.workers.get(i)
            alive = (w is not None and getattr(w, "robot_type", None) is not None)

            if alive:
                have: dict[str, int] = {}
                for m in w.modules:
                    have[m.type] = have.get(m.type, 0) + 1

                for t, req in spec.required_modules.items():
                    deficit = int(req) - int(have.get(t, 0))
                    if deficit > 0:
                        need_total[t] = need_total.get(t, 0) + deficit
            else:
                for t, req in spec.required_modules.items():
                    need_total[t] = need_total.get(t, 0) + int(req)

        return need_total

    def _reserve_variation_min_remain(self, indiv: Individual) -> float:
        cfg = self.cfg
        model = self.model

        stock = model.depot.snapshot()
        need_total = self._compute_need_total(indiv)
        if need_total is None:
            raise ValueError("Failed to compute need_total for reserve variation.")

        # 在庫残数をタイプごとに計算
        # cfg.modules が ["Body","Limb","Wheel"] みたいなリスト想定
        module_types = list(stock.keys())

        min_remain = float("inf")
        for t in module_types:
            remain = int(stock.get(t, 0)) - int(need_total.get(t, 0))
            # capacity constraint を先に通してるなら remain>=0 のはずだが念のため
            if remain < 0:
                remain = 0
            if remain < min_remain:
                min_remain = remain

        if min_remain == float("inf"):
            raise ValueError("No module types found for reserve variation calculation.")

        return float(min_remain)

    # =========================================================
    # Constraint 1:
    #   i番目のワーカーが alive なのに indiv[i] が None (remove要求) → 最悪
    #   alive = (worker exists) and (worker.robot_type is not None)
    # =========================================================
    def _remove_constraint_violation(self, indiv: Individual) -> int:
        """
        remove 指示を出してはいけない alive worker の数を返す
        （0 なら制約満足）
        """
        model = self.model
        violation = 0

        for i, desired in enumerate(indiv.worker_types):
            if desired is not None:
                continue

            w = model.workers.get(i)
            if w is None:
                continue

            # 「robot_type None は死んでいる扱い」
            if getattr(w, "robot_type", None) is None:
                continue

            # alive worker に対して remove 指示 → 制約違反
            violation += 1

        return violation

    # =========================================================
    # Constraint 2:
    #   追加で必要なモジュール数が depot 在庫を超えるなら最悪
    #
    # ここでは planner の差分更新ルールに合わせて
    #   - alive worker & desired!=None: 差分分だけ追加
    #   - dead/不在 & desired!=None: required_modules 全量が追加
    #   - desired is None: 追加0（ただし alive&None は constraint1 で弾かれる）
    #
    # depot 在庫は snapshot() を使う
    # =========================================================
    def _violates_depot_capacity(self, indiv: Individual) -> bool:
        cfg = self.cfg
        model = self.model

        stock = model.depot.snapshot()  # type -> count

        need_total: dict[str, int] = {}

        for i, desired in enumerate(indiv.worker_types):
            if desired is None:
                continue

            spec = cfg.robot_types.get(desired)
            if spec is None:
                raise ValueError(f"Unknown robot_type '{desired}' in individual.")

            w = model.workers.get(i)

            alive = False
            if w is not None and getattr(w, "robot_type", None) is not None:
                alive = True

            if alive:
                # --- 不足分だけ積む ---
                have: dict[str, int] = {}
                for m in w.modules:
                    have[m.type] = have.get(m.type, 0) + 1

                for t, req in spec.required_modules.items():
                    req_i = int(req)
                    have_i = int(have.get(t, 0))
                    deficit = req_i - have_i
                    if deficit > 0:
                        need_total[t] = need_total.get(t, 0) + deficit
            else:
                # --- 新規作成（全量必要）---
                for t, req in spec.required_modules.items():
                    need_total[t] = need_total.get(t, 0) + int(req)

        # capacity check
        for t, need in need_total.items():
            if int(stock.get(t, 0)) < int(need):
                return True

        return False

    # =========================================================
    # Constraint 3:
    #   全員 remove 指示は不可 → 最悪
    # =========================================================
    def _violates_all_none(self, indiv: Individual) -> bool:
        # 1体も構成しない解は無効
        return all(rt is None for rt in indiv.worker_types)