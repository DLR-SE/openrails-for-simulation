from simulation_client.openrails_interface.open_rails_server_interface import OpenRailsServer

from routecreation.geometry import Vector, Pose
from routecreation.openrails_data import OR_TILE, OR_W_FILE_INDEX, pos2world
from routecreation.railgraphs import SceneryObject


class DynamicObject:
    """
    A wrapper for a scenery object that allows to move the object and change its orientation during simulation.
    """

    def __init__(self, server: OpenRailsServer, obj: SceneryObject):
        """
        Initialize this wrapper

        :param server: the server instance to register this object to
        :param obj: the scenery object to wrap
        """
        self.server = server
        self.obj = obj
        self._commands: list[(str, dict)] = []
        server.register_dynamic_object(self)

    def set(self, pos: Vector = None, z: float = None, pitch: float = None, yaw: float = None, roll: float = None, relative=True):
        """
        Change the position of a SceneryObject. The SceneryObject must be animated (otherwise OpenRails may merge it
        with another shape and it cannot be modified anymore). Missing parameters will remain unchanged.
        The new position and rotation in all three dimensions is stored in the object additional attributes;
        the `pose` attribute is updated.

        :param pos: new position of the object
        :param z: new z position (above ground)
        :param pitch: new pitch angle
        :param yaw: new yaw angle (goes to/defaults to pose direction)
        :param roll: new roll angle
        :param relative: if `True`, the new position is relative to the owner

        :return: None
        """
        obj = self.obj
        if not obj.attrs.get('animated', False):
            raise Exception("Only animated objects can be modified")

        if pos or (yaw is not None):
            pose = obj.pose if relative else obj.global_pose

            if yaw is None:
                yaw = pose.direction
            if pos is None:
                pos = pose.pos
            pose = Pose(pos, yaw)
            if relative:
                obj.pose = pose
                pose = obj.global_pose
            else:
                obj.global_pose = pose
        else:
            pose = obj.global_pose
            yaw = pose.direction
        if z is not None:
            obj.attrs['z'] = z
        else:
            z = obj.attrs.get('z', 0.0)
        if pitch is not None:
            obj.attrs['pitch'] = pitch
        else:
            pitch = obj.attrs.get('pitch', 0.0)
        if roll is not None:
            obj.attrs['roll'] = roll
        else:
            roll = obj.attrs.get('roll', 0.0)

        tile = obj.attrs[OR_TILE]
        uid = obj.attrs[OR_W_FILE_INDEX]
        _, _, x, y, z = pos2world(pose.pos, z, tile, obj.graph.attrs[OR_TILE])
        self._add_world_command('ChangeObjectPosition',
                                {'UID': uid, 'TileX': tile[0], 'TileZ': tile[1],
                                 'x': x, 'y': y, 'z': z, 'yaw': yaw, 'pitch': pitch, 'roll': roll})

    def _add_world_command(self, command: str, params: dict):
        """
        Add a world command to the prepared list of commands for the next step.
        The new command is merged into the list; any existing command with the same command name is removed.

        :param command: the command name
        :param params: the command parameters
        """
        self._commands = [cmd for cmd in self._commands if cmd['Command'] != command] + [{'Command': command, **params}]

    def get_and_clear_world_commands(self):
        """
        Return the list of world commands and clear it.

        :return: A copy of the list of commands
        """
        cmds = list(self._commands)
        self._commands.clear()
        return cmds

    @property
    def x(self):
        """the global x position"""
        return self.obj.global_pose.pos.x

    @property
    def y(self):
        """the global y position"""
        return self.obj.global_pose.pos.y

    @property
    def z(self):
        """the global z position"""
        return self.obj.attrs.get('z', 0.0)

    @property
    def pitch(self):
        """the global pitch angle"""
        return self.obj.attrs.get('pitch', 0.0)

    @property
    def yaw(self):
        """the global yaw angle"""
        return self.obj.global_pose.direction

    @property
    def roll(self):
        """the global roll angle"""
        return self.obj.attrs.get('roll', 0.0)

    @x.setter
    def x(self, x):
        """setter for the global x position"""
        pos = self.obj.global_pose.pos.copy()
        pos.x = x
        self.set(pos=pos, relative=False)

    @y.setter
    def y(self, y):
        """setter for the global y position"""
        pos = self.obj.global_pose.pos.copy()
        pos.y = y
        self.set(pos=pos, relative=False)

    @z.setter
    def z(self, z):
        """setter for the global z position"""
        self.set(z=z, relative=False)

    @pitch.setter
    def pitch(self, pitch):
        """setter for the global pitch angle"""
        self.set(pitch=pitch, relative=False)

    @yaw.setter
    def yaw(self, yaw):
        """setter for the global yaw angle"""
        self.set(yaw=yaw, relative=False)

    @roll.setter
    def roll(self, roll):
        """setter for the global roll angle"""
        self.set(roll=roll, relative=False)

