from typing import Dict

from simulation_client.communication.train_command_comm import CommunicationSimulation


class InstantCommunication(CommunicationSimulation):
    def __init__(self):
        super().__init__()
        self.commands: Dict[str, float] = dict()

    def set_value(self, key, value):
        self.commands[key] = value

    def get_current_commands(self):
        return self.commands

    def step(self):
        pass

    # TODO rework to work with simpy when a plotting solution is implemented