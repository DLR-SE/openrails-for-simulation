import atexit
import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
from http import HTTPStatus
from time import sleep
from typing import Any, Dict

import requests
import simpy
from requests import Response

from config.constants import OR_EXEC_DIR, CONTROL_ENDPOINT, READY_ENDPOINT
from config.log_config import get_server_connector_log, get_openrails_log
from simulation_client.model.sensor import Sensor
from simulation_client.openrails_interface.environment import Environment


def _get_json_config(other_trains):
    config = list()
    for train in other_trains:
        config.append({
            "trainNumber": train.number,
            "trainName": train.name,
            "trainConfig": train.consist,
            "trainPath": train.path_number
        })

    with tempfile.NamedTemporaryFile(mode='w+', delete=False) as temp_file:
        json.dump(config, temp_file, indent=4)
        return os.path.abspath(temp_file.name)


def _get_sensor_config(sensors):
    config = []
    for sensor in sensors:
        conf = sensor.get_configuration_data()
        if conf is not None:
            config.append(conf)

    with tempfile.NamedTemporaryFile(mode='w+', delete=False) as temp_file:
        json.dump(config, temp_file, indent=4)
        return os.path.abspath(temp_file.name)


class OpenRailsServer:

    def __init__(self,
                 environment: Environment,
                 connect_to_existing=False,
                 step_size_ms: int = 250,  # numbers higher than 500 make the simulation unstable
                 openrails_dir: str = os.getenv(OR_EXEC_DIR),
                 openrails_exe: str = "RunActivity.exe",
                 host="http://localhost",
                 port=2150,
                 api_path="API",
                 show_server_logs=True,
                 sync=True):
        if step_size_ms > 500:
            logging.error(f"Step sizes > 500ms currently not supported, you set step size to {step_size_ms} ms.")
            sys.exit(-1)
        self.host = host
        self.port = port
        self.api_path = api_path
        self.environment = environment
        self.step_size_ms = step_size_ms
        self.openrails_exe: str = os.path.join(openrails_dir, openrails_exe)
        self.logger = get_server_connector_log()
        self.post_thread = None
        self.sensors: Dict[str, Sensor] = dict()
        self.or_log_thread = None
        self.show_server_logs = show_server_logs
        self.trains = dict()
        self.dynamic_objects = []
        self.connect_to_existing = connect_to_existing
        self._cached_get_responses = {}
        self.sync = sync
        self.taken_steps = 0
        self.ego_train = None
        self.switch_setting = None

        self._world_commands = []
        self.ready = False

    def setup(self):
        if not self.connect_to_existing:
            self.openrails_process = self._start_openrails()
            atexit.register(self.stop)

    def run(self, simpy_env: simpy.Environment):
        while True:
            self.step()
            yield simpy_env.timeout(self.step_size_ms)

    def register_train(self, train):
        self.trains[train.name] = train

    def unregister_train(self, train):
        self.trains.pop(train.name)

    def add_sensor(self, name: str, sensor: Sensor):
        sensor.name = name
        sensor.server = self
        self.sensors[name] = sensor

    def register_dynamic_object(self, dynamic_object):
        self.dynamic_objects.append(dynamic_object)

    def unregister_dynamic_object(self, dynamic_object):
        self.dynamic_objects.remove(dynamic_object)

    def step(self):
        self._cached_get_responses.clear()

        all_commands = []
        for train in self.trains.values():
            if train.is_ego:
                # OpenRails needs the Ego Train to be called "PLAYER", therefore the name is replaced in the command
                #  but not in the Train object itself to ensure consistency within the framework
                command = train.create_json_command()
                for entry in command:
                    entry["LocomotiveName"] = "PLAYER"
                all_commands.extend(command)
            else:
                all_commands.extend(train.create_json_command())
        for dynamic_object in self.dynamic_objects:
            self._world_commands.extend(dynamic_object.get_and_clear_world_commands())
        body = {
            'Controls': all_commands,
            'Commands': self._world_commands,
            'SwitchCommands': self.switch_setting.switch_commands if self.switch_setting else {}
        }
        while not self._server_ready():
            sleep(0.5)
        response = self.post(body, CONTROL_ENDPOINT)
        self.logger.info(f"sent command: {body}")

        if response.status_code == HTTPStatus.OK:
            self.taken_steps += 1
            self._world_commands.clear()

            state = response.json()
            try:
                for sensor in self.sensors.values():
                    sensor.update(state)
                self.update_train_state(state)
            except KeyError as e:
                logging.error("Server response does not meet client expectations. "
                              "Recompiling the server may fix the issue if this is caused by inconsistent API states.")
                raise e

        else:
            self.logger.error(
                f"Server did not accept command. Request was: {body}, Server response was: {response}"
            )

    def post(self, body: Any, endpoint: str, max_retries=3) -> Response:
        number_of_retries = 0
        while number_of_retries <= max_retries:
            try:
                response = requests.post(self.build_url(endpoint), json=body, timeout=30)
                return response
            except TimeoutError:
                self.logger.warning(f"try {number_of_retries} timed out")
                number_of_retries += 1
            except KeyboardInterrupt:
                self.logger.info("server connection terminated")
                sys.exit(0)

        raise TimeoutError

    def get(self, endpoint: str, max_retries=3) -> Response:
        number_of_retries = 0
        while number_of_retries <= max_retries:
            try:
                response = requests.get(self.build_url(endpoint), timeout=15)
                return response
            except TimeoutError:
                print(f"try {number_of_retries} timed out")
                number_of_retries += 1

        raise TimeoutError

    def get_with_cache(self, endpoint: str, *args, **kwargs) -> Response:
        if endpoint in self._cached_get_responses:
            response = self._cached_get_responses[endpoint]
            if isinstance(response, TimeoutError):
                raise TimeoutError from response
        else:
            try:
                response = self.get(endpoint, *args, **kwargs)
                self._cached_get_responses[endpoint] = response
            except TimeoutError as e:
                self._cached_get_responses[endpoint] = e
                raise TimeoutError from e
        return response

    def is_ready(self) -> bool:
        try:
            ready = requests.get(self.build_url(READY_ENDPOINT)).status_code == HTTPStatus.OK
            if ready:
                self.logger.info("ready")
                return True
            else:
                self.logger.info("waiting for server")
        except Exception:
            self.logger.warning("server not yet reachable")
        return False

    def build_url(self, endpoint: str) -> str:
        return f"{self.host}:{self.port}/{self.api_path}/{endpoint}"

    def _start_openrails(self):
        other_trains = list()

        for train in self.trains.values():
            if train.is_ego:
                self.ego_train = train
            else:
                other_trains.append(train)

        assert self.ego_train is not None
        ego_route = (self.environment.route + r'\PATHS\{path_number}.pat').format(
            path_number=self.ego_train.path_number)

        other_trains_config = _get_json_config(other_trains)
        sensors_config = _get_sensor_config(list(self.sensors.values()) +
                                            sum((list(train.sensors.values()) for train in self.trains.values()), []))

        if self.sync:
            command = self.get_synced_command(ego_route, self.ego_train, other_trains_config, sensors_config)
        else:
            command = self.get_async_command(ego_route, self.ego_train)
        self.logger.info(f"starting server: {command}")

        openrails = subprocess.Popen(command, stdout=subprocess.PIPE if self.show_server_logs else None)

        # display server logs
        if self.show_server_logs:
            self.or_log_thread = threading.Thread(target=self._print_logs, args=[openrails])
            self.or_log_thread.start()

        while not self._server_ready():
            time.sleep(1)

        return openrails

    def get_synced_command(self, ego_route, ego_train, other_trains_config, sensors_config):
        return (f'{self.openrails_exe} -start -syncsimulation '
                f'"{ego_route}" '
                f'"{ego_train.consist}" '
                f'{self.environment.time.strftime("%H:%M")} '
                f'{self.environment.season.value} '
                f'{self.environment.weather.value} '
                f'{self.step_size_ms} '
                f'{other_trains_config} '
                f'{sensors_config} '
                f'port={self.port}')

    def get_async_command(self, ego_route, ego_train):
        return (f'{self.openrails_exe} -start -explore '
                f'"{ego_route}" '
                f'"{ego_train.consist}" '
                f'{self.environment.time.strftime("%H:%M")} '
                f'{self.environment.season.value} '
                f'{self.environment.weather.value} '
                f'port={self.port}')

    def _server_ready(self):
        if self.ready:
            return True

        # Only ask the server if it has not yet reported ready
        self.ready = self.is_ready()
        return self.ready

    def _print_logs(self, process):
        # Configure the logger to print in different color for better decidability
        openrails_log = get_openrails_log()

        while process.poll() is None:
            raw_line = process.stdout.readline().rstrip()
            try:
                line = raw_line.decode(str(sys.stdout.encoding))  # This blocks until it receives a newline.
                line.rstrip()
            except UnicodeDecodeError:  # OpenRails stdout seems to be off the encoding sometimes
                line = raw_line
            openrails_log.info(line)
        # When the subprocess terminates there might be unconsumed output
        # that still needs to be processed.
        openrails_log.info(process.stdout.read())

    def stop(self):
        if self.or_log_thread:
            self.or_log_thread.join()
        if self.openrails_process.poll() is None:  # Check if the process is still running
            self.logger.info("Stopping server...")
            self.openrails_process.kill()
            self.openrails_process.wait()

    def __del__(self):
        self.stop()

    def update_train_state(self, result):
        for name, train in self.trains.items():
            train.update_state(result)
