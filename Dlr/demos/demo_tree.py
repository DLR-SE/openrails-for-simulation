import datetime
import logging
import os
from typing import Tuple, Callable, List
import sys
import simpy
import math
from numpy import arange
from config.constants import OR_CONTENT_BASE
from simulation_client.openrails_interface.environment import Season, Environment, Weather
from simulation_client.openrails_interface.open_rails_server_interface import OpenRailsServer
from simulation_client.model.train import Train
from routecreation.railgraphs import Graph, Node, Path, SceneryObject
from routecreation.geometry import Vector, Pose
from routecreation.openrails_data import ORWriter
from simulation_client.model.dynamic_objects import DynamicObject


def set_scene(output_path: str, create_route: bool = False) -> Tuple[Graph, List[SceneryObject]]:
    """
    This function creates a new route which can then be used by Open Rails. Additionally, a simple tree is defined.

    :param output_path: The path to the output directory of the new route
    :param create_route: If False, the route will not be created (Only use False, if you run the same script multiple
                         times)
    :returns: the Graph object as well as a list of static scenery objects (in this demo: one tree)
    """
    graph = Graph()
    start = Node(pose=Pose(Vector(x=-1000.0, y=0.0)), graph=graph)
    end = start.add_edge(length=2000.0)
    edge = end.edge
    tree = SceneryObject(pose=Pose(Vector(x=400.0, y=4.0), direction=90.0),
                         relative_to=edge,
                         shapefile='tree.s',
                         animated=True)

    if create_route:
        writer = ORWriter(directory=output_path, graph=graph)
        writer.write_all()
        writer.write_path_file(filename='0',
                               name='main',
                               start_name='start',
                               end_name='end',
                               points=Path([end.other_end()]))
        writer.write_path_file(filename='1',
                               name='revers',
                               start_name='end',
                               end_name='start',
                               points=Path([end]))

    return graph, [tree]


def setup() -> Tuple[Train, OpenRailsServer, simpy.Environment, List[DynamicObject]]:
    """
    This function is used to set up the simulation environment.
    :returns: Tuple including the ego train instance, an OpenRailsServer instance, a simpy simulation environment and
              a list of dynamic objects (in this demo: one tree)
    """
    # enable simple logging with different levels (NOTSET, DEBUG, INFO, WARN/WARNING, FATAL/ERROR)
    logging.basicConfig(level=logging.WARN,
                        stream=sys.stdout,
                        format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s')

    # initialize assets and open rails environment
    # for setting OR_CONTENT_BASE-environment see the documentation
    content_base_path = os.getenv(OR_CONTENT_BASE)
    route = os.path.join(content_base_path, r"Demo Model 1\ROUTES\demo_route")

    # initialize the scene (route + tree)
    route_graph, scene_objects = set_scene(output_path=route,
                                           create_route=True)

    # initialize Open Rails server
    or_environment = Environment(route=route,
                                 time=datetime.time(hour=12),
                                 season=Season.AUTUMN,
                                 weather=Weather.RAIN)
    server = OpenRailsServer(environment=or_environment,
                             connect_to_existing=False,
                             step_size_ms=250,
                             show_server_logs=False)

    # convert scene object (tree) into dynamic object
    dynamic_tree = DynamicObject(server=server, obj=scene_objects[0])

    # define the consist file path in order to load the train model
    consist = os.path.join(content_base_path, r"Demo Model 1\TRAINS\CONSISTS\MT_MT_Class 27 102 & 6 mk2 PP.CON")

    # initialize ego train
    ego_train = Train(server=server,
                      consist=consist,
                      route=route,
                      path_number=0, # corresponds to path number defined in `set_scene`
                      is_ego=True,
                      name="EGO_TRAIN")

    # set initial values for train throttle and brakes
    ego_train.set(train_brake=0.0, direction=1.0)
    ego_train.set_diesel(throttle=0.1)

    server.setup()

    return ego_train, server, simpy.Environment(), [dynamic_tree]


def run(train: Train,
        server: OpenRailsServer,
        simulation_environment: simpy.Environment,
        stop_function: Callable,
        **kwargs) -> None:
    """
    Defines the processes and control logic of the simulation run.
    :param train: Ego train instance which can be influenced by the developer.
    :param server: OpenRailsServer instance which hosts the simulation and the python client communicates to.
    :param simulation_environment: Simpy simulation environment for setting up the simulation processes
    :param stop_function: A function which contains the control logic. The simulation will stop whenever this function
    finishes.
    returns: Nothing
    """
    # start the simulation environment
    simulation_environment.process(server.run(simulation_environment))
    # start the train controller logic
    simulation_environment.run(until=simulation_environment.process(stop_function(train,
                                                                                  server,
                                                                                  simulation_environment,
                                                                                  **kwargs)))


def stop(train: Train,
         server: OpenRailsServer,
         simulation_environment: simpy.Environment,
         tree: DynamicObject):
    """
    Custom stop function which defines the logic for the tree falling onto the track and stopping the train accordingly.
    This method terminates after the ego train travelling a fixed distance.

    :param train: Ego train instance which can be influenced by the developer.
    :param server: OpenRailsServer instance which hosts the simulation and the python client communicates to.
    :param simulation_environment: Simpy simulation environment for setting up the simulation processes
    :param tree: dynamic object which falls onto the track
    """
    # falling tree trajectory
    falling_tree_trajectory = [2.0 * math.sin(x) for x in arange(0, math.pi, 0.01)]
    i: int = 0
    while True:
        if tree.roll <= 1.5 and train.distance_travelled > 100:
            tree.roll = falling_tree_trajectory[i]
            i = (i + 1) % len(falling_tree_trajectory)
        if train.distance_travelled > 200:
            if train.velocity_y < 0.0001:
                yield simulation_environment.event().succeed()
                break
            else:
                train.set(train_brake=0.3)
            train.set_diesel(throttle=0.0)
        yield simulation_environment.timeout(server.step_size_ms)


def main():
    ego_train, server, simulation_environment, scene_objects = setup()
    run(train=ego_train,
        server=server,
        simulation_environment=simulation_environment,
        stop_function=stop,
        tree=scene_objects[0])


if __name__ == "__main__":
    main()
