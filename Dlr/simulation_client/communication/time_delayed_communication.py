from typing import Dict

import simpy

from simulation_client.communication.train_command_comm import CommunicationSimulation


class TimeDelayedCommunication(CommunicationSimulation):
    def __init__(self, delay=1000):
        super().__init__()

        # fill with empty commands for initial delay
        self.current_commands = dict()

        self.receiving_commands: Dict[str, float] = dict()
        self.delay = delay

    def run(self, simpy_env: simpy.Environment, step_size_ms: int):
        while True:
            simpy_env.process(self.step(simpy_env))
            yield simpy_env.timeout(step_size_ms)

    def set_value(self, key, value):
        self.receiving_commands[key] = value

    def get_current_commands(self):
        return self.current_commands

    def step(self, simpy_env):
        command_to_send = self.receiving_commands.copy()
        self.receiving_commands = dict()
        yield simpy_env.timeout(self.delay)
        self.current_commands = command_to_send
