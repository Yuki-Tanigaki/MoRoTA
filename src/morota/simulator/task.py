import mesa

class TaskAgent(mesa.Agent):
    def __init__(self, model: "World", pos: Vec, dest: Vec,
                 required_capacity: float, base_speed: float = 0.10):
        super().__init__(model)             # ★ Agent.__init__ で自動登録されます
        self.pos: Vec = pos
        self.dest: Vec = dest
        self.required_capacity = required_capacity
        self.base_speed = base_speed
        self.attached: Set["Robot"] = set()
        self.completed = False

    def total_capacity(self) -> float:
        return sum(r.capacity for r in self.attached)

    def step(self) -> None:
        if self.completed:
            return
        cap = self.total_capacity()
        if cap < self.required_capacity:
            return
        # 目的地へ前進（cap に比例して速くなる）
        d = v_sub(self.dest, self.pos)
        L = v_len(d)
        if L == 0:
            return self._finish()
        v = self.base_speed * clamp(cap / self.required_capacity, 0.0, 1.5)
        step = min(v, L)
        new_pos = v_add(self.pos, v_scale(v_norm(d), step))
        # トーラス補正して移動
        new_pos = self.model.space.torus_adj(new_pos)
        self.model.space.move_agent(self, new_pos)
        self.pos = new_pos
        if v_len(v_sub(self.dest, self.pos)) < 1e-6:
            self.model.space.move_agent(self, self.dest)
            self.pos = self.dest
            self._finish()

    def _finish(self):
        for r in list(self.attached):
            r.attached_task = None
            r.state = "idle"
        self.attached.clear()
        self.completed = True
        self.model.tasks.discard(self)
        # 空間とモデルから除去
        self.model.space.remove_agent(self)
        self.remove()