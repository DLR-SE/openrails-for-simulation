from http import HTTPStatus
from typing import Any

import numpy as np
from immutabledict import immutabledict

from simulation_client.model.sensor import Sensor
from simulation_client.openrails_interface.open_rails_server_interface import OpenRailsServer


class AbstractCameraSensor(Sensor):
    def __init__(self, sensor_type: str, width=800, height=600, fov=45.0):
        super().__init__()
        self.sensor_type = sensor_type
        self.width = width
        self.height = height
        self.fov = fov
        self.output_data = np.empty(3)

    def process(self, state: immutabledict[str, Any]) -> dict[str, object]:
        response = self.server.get_with_cache('CAMERASENSOR/' + self.name)
        if response.status_code == HTTPStatus.OK:
            return self.decode(response.content, state['CameraSensors'][self.name])
        else:
            return {}

    def decode(self, raw_data, state: dict[str, Any]) -> dict[str, object]:
        raise NotImplementedError

    def update(self, state: immutabledict[str, Any]):
        self.output_data = self.process(state)

    def output(self):
        return self.output_data

    def get_configuration_data(self):
        return {'sensorName': self.name,
                'sensorType': self.sensor_type,
                'trainName': 'PLAYER' if self.train.is_ego else self.train.name,
                'height': self.height,
                'width': self.width,
                'fov': self.fov}

class RGBCameraSensor(AbstractCameraSensor):

    def __init__(self, width=800, height=600, fov=45.0):
        super().__init__('rgb', width, height, fov)

    def decode(self, raw_data, state: dict[str, Any]):
        return {'size': (state['width'], state['height']), 'data': raw_data}


