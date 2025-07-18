from immutabledict import immutabledict
from routecreation.railgraphs import SceneryObject


class Sensor:
    def __init__(self):
        self.world_object = None
        self.server = None
        self.name = None
        self.train = None
        pass

    def process(self, state: immutabledict[str, object]) -> dict[str, object]:
        """Gain additional sensor information by processing the simulation output state.

        :param state: The original state gained from the simulation
        :return: A dictionary containing only the newly gained sensor values.
        """
        raise NotImplementedError()

    def update(self, state: immutabledict[str, object]) -> None:
        """Update own output signal based on the current simulation state

        :param state: The state gained from the simulation
        """
        raise NotImplementedError()

    def output(self):
        """ Get current sensor output

        :return: current sensor output
        """
        raise NotImplementedError()

    def set_world_object(self, world_object: SceneryObject):
        self.world_object = world_object
    def get_configuration_data(self):
        return None