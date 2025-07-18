import datetime
from enum import Enum


class Season(Enum):
    SPRING = 0
    SUMMER = 1
    AUTUMN = 2
    WINTER = 3


class Weather(Enum):
    CLEAR = 0
    SNOW = 1
    RAIN = 2


class Environment:
    def __init__(self, route: str, time: datetime.time, season: Season, weather: Weather):
        self.route: str = route
        self.time: datetime.time = time
        self.season: Season = season
        self.weather: Weather = weather

