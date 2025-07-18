import datetime
import logging
import os
from typing import Tuple, Callable
import sys
import simpy
from config.constants import OR_CONTENT_BASE
from simulation_client.openrails_interface.environment import Season, Environment, Weather
from simulation_client.openrails_interface.open_rails_server_interface import OpenRailsServer
from simulation_client.model.train import Train
from routecreation.railgraphs import Graph, Node, find_shortest_path
from routecreation.geometry import Vector, Pose
from routecreation.openrails_data import ORWriter


def create_route(output_path: str) -> None:
    """
    This function creates a new route which can then be used by Open Rails.

    :param output_path: The path to the output directory of the new route
    :returns: Nothing
    """
    # initialize a graph
    graph = Graph()
    # simple straight route
    start = Node(pose=Pose(Vector(x=1000.0, y=0.0)), graph=graph)
    end = start.add_edge(length=1200.0)

    # initialize the Open Rails writer
    writer = ORWriter(directory=output_path, graph=graph)
    writer.write_all()
    # define custom paths through the graph which can be used to initialize a train
    writer.write_path_file(filename='0',
                           name='main',
                           start_name='start',
                           end_name='end',
                           points=find_shortest_path(start, end))
    writer.write_path_file(filename='1',
                           name='reverse',
                           start_name='end',
                           end_name='start',
                           points=find_shortest_path(end, start))


def setup() -> Tuple[Train, OpenRailsServer, simpy.Environment]:
    """
    This function is used to set up the simulation environment.
    :returns: Tuple of the ego train instance, an OpenRailsServer instance and a simpy simulation environment
    """
    # enable simple logging with different levels (NOTSET, DEBUG, INFO, WARN/WARNING, FATAL/ERROR)
    logging.basicConfig(level=logging.INFO,
                        stream=sys.stdout,
                        format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s')

    # initialize assets and open rails environment
    # for setting OR_CONTENT_BASE-environment see the documentation
    content_base_path = os.getenv(OR_CONTENT_BASE)
    route = os.path.join(content_base_path, r"Demo Model 1\ROUTES\demo_route")

    # initialize the route
    create_route(output_path=route)

    # initialize Open Rails server
    or_environment = Environment(route=route,
                                 time=datetime.time(hour=12),
                                 season=Season.SPRING,
                                 weather=Weather.CLEAR)
    server = OpenRailsServer(environment=or_environment,
                             connect_to_existing=False,
                             step_size_ms=250,
                             show_server_logs=False)

    # define the consist file path in order to load the ego train model
    consist = os.path.join(content_base_path, r"Demo Model 1\TRAINS\CONSISTS\MT_MT_Class 27 102 & 6 mk2 PP.CON")

    # initialize ego train
    ego_train = Train(server=server,
                      consist=consist,
                      route=route,
                      path_number=0, # corresponds to path number defined in `create_route`
                      is_ego=True,
                      name="EGO_TRAIN")
    # set initial values for train throttle and brakes
    ego_train.set(train_brake=0.0, direction=1.0)
    ego_train.set_diesel(throttle=1.0)

    server.setup()

    return ego_train, server, simpy.Environment()


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
         max_distance: int = 300):
    """
    Custom stop function which terminates after the ego train passes a certain distance

    :param train: Ego train instance which can be influenced by the developer.
    :param server: OpenRailsServer instance which hosts the simulation and the python client communicates to.
    :param simulation_environment: Simpy simulation environment for setting up the simulation processes
    :param max_distance: Train distance threshold after which the simulation is being stopped.
    """
    while True:
        print(f"ego train distance travelled: {train.distance_travelled}")
        # if the train crosses the distance threshold, the entire simulation stops
        if train.distance_travelled > max_distance:
            yield simulation_environment.event().succeed()
            break
        else:
            yield simulation_environment.timeout(server.step_size_ms)


def main():
    ego_train, server, simulation_environment = setup()
    run(train=ego_train,
        server=server,
        simulation_environment=simulation_environment,
        stop_function=stop,
        max_distance=1000)


if __name__ == "__main__":
    main()
