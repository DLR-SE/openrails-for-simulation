from enum import Enum
from typing import List, Dict

from routecreation.railgraphs import Graph, Path
from simulation_client.openrails_interface.open_rails_server_interface import OpenRailsServer


class SwitchState(Enum):
    """direction of the switch when driving over it from its root"""

    LEFT = 0
    RIGHT = 1


class SwitchSetting:
    def __init__(self, server: OpenRailsServer, train_paths: Dict[str, Path]):
        self.switches_per_path = self._get_switches_per_path(train_paths)
        self.switch_commands = {}
        server.switch_setting = self

    def set_switch(self, train_name: str, n: int, state: SwitchState):
        """
        Set the n-th switch on the path of the train with train_name to state.

        :param train_name: The name of the train on whose path which the switch is located
        :param n: The index of the switch when counting switches from the start of the path
        :param state: The target state of the switch
        :return: None
        """
        switch_tdb_index = self.switches_per_path[train_name][n]
        self.switch_commands[switch_tdb_index] = state.value

    def _get_switches_per_path(self, train_paths: Dict[str, Path]) -> Dict[str, List[int]]:
        result = {}
        for train_name, path in train_paths.items():
            result[train_name] = [end.node().attrs["or_tdb_index"] for end in path if len(end.node().ends()) > 2]
        return result
