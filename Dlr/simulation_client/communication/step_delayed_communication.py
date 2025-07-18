from queue import Queue
from typing import Dict

import simpy

from simulation_client.communication.train_command_comm import CommunicationSimulation


class StepDelayedCommunication(CommunicationSimulation):
    def __init__(self, steps=5):
        super().__init__()
        self.command_q = Queue(steps)

        # fill with empty commands for initial delay
        for step in range(steps):
            self.command_q.put(dict())

        self.receiving_commands: Dict[str, float] = dict()

    def set_value(self, key, value):
        self.receiving_commands[key] = value

    def get_current_commands(self):
        return self.command_q.get()

    def run(self, simpy_env: simpy.Environment, step_size_ms: int):
        while True:
            self.command_q.put(self.receiving_commands.copy())
            self.receiving_commands = dict()
            yield simpy_env.timeout(step_size_ms)
