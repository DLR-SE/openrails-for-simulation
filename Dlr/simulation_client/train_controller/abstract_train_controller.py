import simpy


class AbstractTrainController:
    """
    Base class for a train train_controller.
    """

    def __init__(self, train):
        """
        Initializes the train train_controller with a reference to a train object.

        Args:
        - train (Train): The train object that this train_controller will manage.
        """
        self.train = train
        self.name = 'abstract_train_controller'

    def run(self, simpy_env: simpy.Environment, step_size_ms: int):
        while True:
            self.update()
            yield simpy_env.timeout(step_size_ms)

    def update(self):
        """
        Controls the train
        Subclasses should override this method to implement specific control strategies.

        Args:
        - state (dict): The current state of the train, e.g. {'velocity_current_mps': 10.}.
        """
        raise NotImplementedError("Subclasses must implement this method")

    def get_name(self):
        return self.name
