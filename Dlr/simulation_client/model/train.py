import logging
import math
import uuid
from typing import Dict, List, Tuple

from typing_extensions import Self

from simulation_client.communication.instant_communication import InstantCommunication
from simulation_client.communication.train_command_comm import CommunicationSimulation
from simulation_client.model.sensor import Sensor
from simulation_client.model.train_properties import extract_properties
from simulation_client.openrails_interface.open_rails_server_interface import OpenRailsServer
from routecreation.openrails_data import DEFAULT_START_TILE, TILE_SIZE

SPEED = float


class Train:
    current_train_number = 0

    def __init__(self, server: OpenRailsServer, consist: str, route: str = None, name: str = None,
                 path_number: int = None, is_ego: bool = False,
                 communication_sim: CommunicationSimulation = None, start_tile: Tuple[int, int] = DEFAULT_START_TILE):
        self.properties = extract_properties(consist)
        self.id = uuid.uuid4()
        self.is_ego = is_ego
        self.name = name
        if not is_ego:
            self.current_train_number += 1
            self.number = self.current_train_number
        else:
            self.number = 0
        self.server = server
        self.consist = consist
        self.route = route
        self.path_number = path_number
        self.sensors: Dict[str, Sensor] = dict()
        self.logger = logging.getLogger(f"Train{' ' + name if name else ''}:{self.id}")
        server.register_train(self)
        self.commands: Dict[str, float] = dict()
        self.location: Tuple[float, float, float] = (0.0, 0.0, 0.0)
        self.velocity_current_mps = 0.0
        self.velocity_x = 0.0
        self.velocity_y = 0.0
        self.wheelslip = 0
        self.velocity_current_mps = 0.0
        self.rotation = 0.0
        self.acceleration = 0.0
        self.distance_travelled = 0.0
        self.trackNodeOffset: float = 0.0
        self.trackNodeIndex: int = 0
        self.moves_backwards_on_track = False
        self.frontTrackNodeOffset: float = 0.0
        self.frontTrackNodeIndex: int = 0
        self.front_moves_backwards_on_track = False
        if not communication_sim:
            self.communication_sim = InstantCommunication()
        else:
            self.communication_sim = communication_sim

        self.start_tile_x, self.start_tile_z = start_tile

    def set(self,
            direction=None,
            train_brake=None) -> Self:
        self._set_value("DIRECTION", direction)
        # The simulation does not always accept 0.0 as input, therefore it needs a value slightly above 0.0.
        # This is mapped to 0.0 in the simulation.
        self._set_value("TRAIN_BRAKE", 0.0001 if train_brake < 0.0001 else train_brake)

        return self

    def set_diesel(self, throttle=None) -> Self:
        self._set_value("THROTTLE", throttle)
        # The simulation does not always accept 0.0 as input, therefore it needs a value slightly above 0.0.
        # This is mapped to 0.0 in the simulation.
        self._set_value("THROTTLE", 0.0 if throttle < 0.0001 else throttle)

        return self

    def set_steam(self, regulator=None):
        self._set_value("REGULATOR", regulator)

    def create_json_command(self) -> List[Dict[str, float]]:
        body: List[Dict[str, float]] = list()
        commands = self.communication_sim.get_current_commands()
        for key, value in commands.items():
            body.append({"LocomotiveName": self.name, "TypeName": key, "Value": value})

        return body

    def _set_value(self, key: str, value: float):
        if value is not None:
            self.communication_sim.set_value(key, value)

    def _get_value(self, key: str):
        commands = self.communication_sim.get_current_commands()
        if key in commands.keys():
            return commands[key]
        else:
            return None

    def __str__(self):
        return f"CabCommands:\n{self.commands}"

    def add_sensor(self, name: str, sensor: Sensor):
        self.sensors[name] = sensor
        sensor.train = self
        sensor.name = self.name + "__" + name
        sensor.server = self.server

    def update_state(self, state):
        for sensor in self.sensors.values():
            sensor.update(state)

        train_name = self.name if not self.is_ego else "PLAYER"
        own_train_state = state["trains"][train_name]

        # TODO IS THIS THE CORRECT ORDER?
        self.location = self._parse_location(own_train_state["location"])
        self.velocity_current_mps = own_train_state["locomotiveState"]["v"]
        self.acceleration = own_train_state["locomotiveState"]["a"]
        self.distance_travelled = own_train_state["locomotiveState"]["distance"]
        self.wheelslip = own_train_state["locomotiveState"]["wheelslip"]
        self.trackNodeIndex = own_train_state['rearTrackLocation']['trackNodeIndex']
        self.trackNodeOffset = own_train_state['rearTrackLocation']['trackNodeOffset']
        self.moves_backwards_on_track = own_train_state['rearTrackLocation']['movementDirection'] == 'Backward'
        self.frontTrackNodeIndex = own_train_state['trackLocation']['trackNodeIndex']
        self.frontTrackNodeOffset = own_train_state['trackLocation']['trackNodeOffset']
        self.front_moves_backwards_on_track = own_train_state['trackLocation']['movementDirection'] == 'Backward'
        self.rotation = own_train_state['rotation']

        self.velocity_x = self.velocity_current_mps * math.cos(self.rotation)
        self.velocity_y = self.velocity_current_mps * math.sin(self.rotation)

    def _parse_location(self, location):
        offset_x = (location['tileX'] - self.start_tile_x) * TILE_SIZE
        offset_z = (location['tileZ'] - self.start_tile_z) * TILE_SIZE
        return location['x'] + offset_x, location['z'] + offset_z, location['y']

