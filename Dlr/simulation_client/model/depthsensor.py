import math
from enum import IntEnum
from typing import Union, Iterable

import numpy as np

from simulation_client.model.camera_sensor import AbstractCameraSensor
from simulation_client.openrails_interface.open_rails_server_interface import OpenRailsServer

RAW_DATA_DTYPE = np.dtype('<u2')
DEFAULT_CONFIG = {'height': 600, 'width': 800, 'h_scale': 1.81066, 'v_scale': 2.414213, 'max_distance': 200.0}


class ObjectClassifiers(IntEnum):
    """
    Semantic object classifiers used by the simulator
    """

    UNKNOWN = 0
    """
    Any scenery object of unknown type
    """
    TERRAIN = 1
    """
    The terrain ground
    """
    TRACK = 2
    """
    A (dynamic) track object. Only the railroad ties are classified
    """
    TRAIN = 3
    """
    A train 
    """
    CAR = 4
    """
    A road vehicle, pedestrian, ... 
    Something that is moved by the simulator along pre-defined paths and is not a train 
    """
    SIGNAL = 5
    """
    A signal
    """
    CUSTOM1 = 6
    """
    For custom use 
    """
    CUSTOM2 = 7
    """
    For custom use
    """


class LidarSensor(AbstractCameraSensor):
    """
    Emulation of a LiDAR sensor. It is adapted from the CARLA LiDAR simulation.

    It produces a point cloud, represented as a 2D numpy array, where each row is a 5-tuple (X, Y, Z, ID_CLS, I) with

    * (X, Y, Z) being the position
    * ID_CLS being object ID and classification C, encoded as ``(C << 13) + ID``
    * I the intensity

    The coordinate system is X right, Y up, and Z away from the sensor.

    The intensity of a point is

    .. math:: I := I_0 e^{-a \cdot D}

    where :math:`I_0` is the raw intensity from the simulator, :math:`D` the distance from the point to the sensor, and
    :math:`a` the atmosphere attenuation rate.

    Dropoff is simulated based on sensor parameters

    - :math:`P_0` base dropoff rate
    - :math:`P_Z` additional dropoff rate for points with zero intensity
    - :math:`I_D` intensity above that no intensity-based dropoff occurs

    The probability that a point is dropped is then

    .. math:: P = P_0 + P_I(1-P_0)

    with intensity based dropoff

    .. math:: P_I = P_Z(1 - I / I_D)

    if :math:`I \geq I_D` and :math:`P_I = 0` otherwise

    """
    def __init__(self, h_step=0.1, v_step=0.1, dropoff_base=0.45, attenuation_rate=0.004, dropoff_intensity_limit=0.8,
                 dropoff_zero_intensity=0.4, h_fov=45.0, v_fov=45.0,
                 filter_ground_pane: Union[bool, Iterable[ObjectClassifiers]] = False, seed=None, max_distance=200.0):
        """

        :param h_step: horizontal distance of data points, in degree
        :param v_step: vertical distance of data points, in degree
        :param dropoff_base: base (random) drop-off rate
        :param attenuation_rate: athmosphere attenuation rate
        :param dropoff_intensity_limit: intensity limit above that no intensity-based dropoff occurs
        :param dropoff_zero_intensity: drop-off rate for points with zero intensity
        :param filter_ground_pane: whether to filter out the ground (True, False)
                                   or an iterable of object classifiers to filter out
        :param seed: Seed to use for drop-off (see np.random.default_rng)
        """

        super().__init__('depth')
        self.width = math.ceil((1.0 / (math.tan(0.5 * h_fov) - math.tan(0.5 * h_fov - h_step)) + 1.0) / 16.0) * 32
        self.height = math.ceil(math.tan(0.5 * v_fov) / math.tan(0.5 * h_fov) * self.width)
        self.fov = h_fov
        self.rng = np.random.default_rng(seed)
        self.dropoff_base = dropoff_base
        self.attenuation_rate = attenuation_rate
        self.dropoff_intensity_limit = dropoff_intensity_limit
        self.dropoff_zero_intensity = dropoff_zero_intensity
        self.h_step = h_step
        self.v_step = v_step
        self.configured_range = max_distance
        self._configure(DEFAULT_CONFIG)
        if filter_ground_pane is False:
            self.filtered_classifiers = ()
        elif filter_ground_pane is True:
            self.filtered_classifiers = (ObjectClassifiers.TERRAIN, ObjectClassifiers.TRACK)
        else:
            self.filtered_classifiers = filter_ground_pane

    def _decode_data(self, raw_input: bytes):

        ushorts = np.frombuffer(raw_input, dtype=RAW_DATA_DTYPE)
        id_and_class = ushorts[0::3][self.indices]
        distances = ushorts[1::3][self.indices] * self.max_distance / ((1 << 16) - 1)
        intensities = ushorts[2::3][self.indices] / float((1 << 16) - 1)
        return id_and_class, distances, intensities

    def _get_filter(self, id_and_class: np.array, distances: np.array, base_intensities: np.array):
        """
        Calculate a filter array for dropoff and intensities.
        The returned filter contains False for each dropped point, and True otherwise.

        :param id_and_class: array with object classes and IDs
        :param distances: array with distances
        :param base_intensities: array with base intensities
        :return: the filter array, the calculated intensities
        """
        mask = (id_and_class == 0)
        for cls in self.filtered_classifiers:
            mask |= (id_and_class >= (int(cls) << 13)) & (id_and_class < ((int(cls) + 1) << 13))

        masked_distances = np.ma.masked_array(distances, mask)
        masked_intensities = np.ma.masked_array(base_intensities, mask)
        intensities = masked_intensities * np.ma.exp(-masked_distances * self.attenuation_rate)
        if self.dropoff_intensity_limit > 0 and self.dropoff_zero_intensity > 0:
            p_intensity_drop = ((np.ma.minimum(intensities / self.dropoff_intensity_limit, 1.0) - 1.0) *
                                (-self.dropoff_zero_intensity))
        else:
            p_intensity_drop = 0.0
        p_drop = 1.0 - (1.0 - p_intensity_drop) * (1.0 - self.dropoff_base)
        return ~mask & np.ma.greater_equal(self.rng.random(self.n_values), p_drop), intensities

    def decode(self, raw_data: bytes, config: dict):
        if self._prev_config != config:
            self._configure(config)
        id_and_class, distances, intensities = self._decode_data(raw_data)
        _filter, intensities = self._get_filter(id_and_class, distances, intensities)
        return np.column_stack(((self.positions[_filter].T * distances[_filter]).T, id_and_class[_filter], intensities[_filter]))

    def _configure(self, config: dict):
        """
        Configure the layout of the point cloud. This pre-calculates all the data that is independent
        of the actual depth information. 

        :param config: the properties of the depth data as reported by the simulation server
        :return: None
        """
        def get_index(s, num):
            return np.clip(np.round((0.5 + 0.5*s) * num), 0, num - 1).astype(int)

        self.img_height = config['height']
        self.img_width = config['width']
        h_scale = config['h_scale']
        v_scale = config['v_scale']
        self.max_distance = float(config['max_distance'])

        # calculate field of view
        h_fov = 2 * math.degrees(math.atan(1.0 / h_scale))
        # print(f'h_fov = {h_fov}')
        v_fov = 2 * math.degrees(math.atan(1.0 / v_scale)) # / math.sqrt(1.0 + h_scale*h_scale)))
        # print(f'v_fov = {v_fov}')

        # create initial mesh grid of horizontal and vertical angles
        h = np.radians(np.arange(-0.5 * h_fov, 0.5 * h_fov, self.h_step))
        v = np.radians(np.arange(-0.5 * v_fov, 0.5 * v_fov, self.v_step))
        h_angles, v_angles = np.meshgrid(h, v)
        h_angles = h_angles.flatten()
        v_angles = v_angles.flatten()

        # calculate direction vectors
        fx = np.sin(h_angles) * np.cos(v_angles)
        fy = np.sin(v_angles)
        fz = np.cos(h_angles) * np.cos(v_angles)

        # calculate positions in the projection
        x_positions = fx / fz * h_scale
        y_positions = fy / fz * v_scale

        # filter points outside the viewport
        # x positions are automatically within the FOV, but in the corners some y values may shoot too high or too low
        in_view = (y_positions >= -1.0) & (y_positions <= 1.0)
        x_positions = x_positions[in_view]
        y_positions = y_positions[in_view]
        fx = fx[in_view]
        fy = fy[in_view]
        fz = fz[in_view]

        self.indices = get_index(x_positions, self.img_width) + get_index(-y_positions, self.img_height) * self.img_width
        """
        The indices of used points in the raw data image
        """
        # print(self.indices)
        self.positions = np.column_stack((fx, fy, fz))
        """
        The direction vectors for the points in the point cloud
        """
        self.n_values = len(self.indices)
        """
        Max. number of points in point cloud (some may be randomly dropped)
        """

        self._prev_config = config

    @staticmethod
    def object_classifications(data) -> np.ndarray:
        """
        Extract object classifications from LiDAR data

        :param data: LiDAR sensor data
        :return: the object classifications (cast to integers)
        """
        return data[:][3].astype(int) >> 13

    @staticmethod
    def object_ids(data) -> np.ndarray:
        """
        Extract object IDs from LiDAR data

        :param data: LiDAR sensor data
        :return: the object IDs (cast to integers)
        """
        return data[:][3].astype(int) & 0x1FFF

    @staticmethod
    def intensities(data) -> np.ndarray:
        """
        Extract intensities from LiDAR data

        :param data: LiDAR sensor data
        :return: the intensities
        """
        return data[:][4]

    @staticmethod
    def positions(data) -> np.ndarray:
        """
        Extract positions from LiDAR data

        :param data: LiDAR sensor data
        :return: the positions as triples (X, Y, Z)
        """
        return data[:][0:2]

    @staticmethod
    def filter_by_classification(data, cls: ObjectClassifiers, *other_cls: ObjectClassifiers) -> np.ndarray:
        """
        Filter LiDAR data by object classes

        :param data: the LiDAR data
        :param cls: Object classification to filter for
        :param other_cls: Other object classifications to filter for
        :return: the filtered data
        """
        classifications = LidarSensor.object_classifications(data)
        _filter = classifications == int(cls)
        for other in other_cls:
            _filter = _filter | (classifications == int(other))
        return data[_filter]

    def get_configuration_data(self):
        config = super().get_configuration_data()
        config['range'] = self.configured_range
        return config




