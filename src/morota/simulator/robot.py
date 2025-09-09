import mesa

class RobotAgent(mesa.Agent):
    def __init__(self, model: "World", pos: Vec,
                 capacity: float = 1.0, speed: float = 0.30,
                 attach_radius: float = 0.8, sense_range: float = 6.0):
        super().__init__(model)
        self.pos: Vec = pos
        self.capacity = capacity
        self.speed = speed
        self.attach_radius = attach_radius
        self.sense_range = sense_range
        self.state = "idle"            # idle -> to_task -> attached
        self.target_task: Optional[Task] = None
        self.attached_task: Optional[Task] = None

    def _move_towards(self, target: Vec):
        d = v_sub(target, self.pos)
        L = v_len(d)
        if L == 0: return
        step = min(self.speed, L)
        new_pos = v_add(self.pos, v_scale(v_norm(d), step))
        new_pos = self.model.space.torus_adj(new_pos)
        self.model.space.move_agent(self, new_pos)
        self.pos = new_pos

    def step(self) -> None:
        m: World = self.model
        # 付着中はタスクに追従
        if self.attached_task is not None:
            t = self.attached_task
            if t.completed:
                self.attached_task = None
                self.state = "idle"
                return
            if v_len(v_sub(t.pos, self.pos)) > self.attach_radius * 0.7:
                self._move_towards(t.pos)
            return

        # 目標が無効ならリセット
        if self.target_task is not None and (self.target_task.completed or self.target_task not in m.tasks):
            self.target_task = None
            self.state = "idle"

        # タスク探索：sense_range 内の近傍から Task を抽出
        if self.target_task is None:
            neighbors = m.space.get_neighbors(self.pos, radius=self.sense_range, include_center=False)
            candidates = [a for a in neighbors if isinstance(a, Task) and not a.completed]
            if not candidates:
                # 見つからなければ全タスクから最近傍
                candidates = [t for t in m.tasks if not t.completed]
            if candidates:
                self.target_task = min(candidates, key=lambda t: m.space.get_distance(self.pos, t.pos))
                self.state = "to_task"

        # 取り付き or 接近
        if self.target_task is not None:
            t = self.target_task
            if m.space.get_distance(self.pos, t.pos) <= self.attach_radius:
                self.target_task = None
                self.attached_task = t
                self.state = "attached"
                t.attached.add(self)
            else:
                self._move_towards(t.pos)