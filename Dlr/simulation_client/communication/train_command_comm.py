import simpy


class CommunicationSimulation:
    def __init__(self):
        pass

    def update_value(self, value):
        raise NotImplementedError("Must be implemented by subclasses")

    def set_value(self, key, value):
        raise NotImplementedError("Must be implemented by subclasses")

    def get_current_commands(self):
        raise NotImplementedError("Must be implemented by subclasses")

    def run(self, simpy_env: simpy.Environment, step_size_ms: int):
        raise NotImplementedError("Must be implemented by subclasses")

    def step(self):
        raise NotImplementedError("Muste be implemented by subclasses")
