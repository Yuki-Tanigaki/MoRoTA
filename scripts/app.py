# ロボット生成・配置
for _ in range(n_robots):
    pos = (self.random.uniform(0, width), self.random.uniform(0, height))
    r = RobotAgent(self, pos=pos)
    self.space.place_agent(r, pos)
    self.robots.append(r)

# タスク生成・配置
for _ in range(n_tasks):
    pos  = (self.random.uniform(0.2*width, 0.8*width),
            self.random.uniform(0.2*height, 0.8*height))
    dest = (self.random.uniform(0.2*width, 0.8*width),
            self.random.uniform(0.2*height, 0.8*height))
    req = self.random.uniform(*task_required_capacity)
    t = TaskAgent(self, pos=pos, dest=dest, required_capacity=req, base_speed=0.10)
    self.space.place_agent(t, pos)
    self.tasks.add(t)