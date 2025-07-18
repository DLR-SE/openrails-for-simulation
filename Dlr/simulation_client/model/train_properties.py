from pathlib import Path


class TrainProperties:
    def __init__(self, mass, bounding_box):
        self.mass = mass
        self.bounding_box = bounding_box


def extract_properties(consist) -> TrainProperties:
    engine_path, shape_path = _get_engine_paths(consist)

    with open(engine_path, "r", encoding="utf-16le") as file:
        engine_description = file.read().strip().replace(" ", "")
    mass = float(_get_value(engine_description, "Mass").removesuffix("t")) * 1000

    with open(shape_path, "r", encoding="utf-16le") as file:
        shape_description = file.read().strip()
    bounding_box_values = tuple(_get_value(shape_description, "ESD_Bounding_Box").split(" "))

    bounding_box = _get_bounding_box(bounding_box_values)

    return TrainProperties(mass, bounding_box)


def _get_engine_paths(consist):
    with open(consist, "r", encoding="utf-16le") as file:
        data = file.read()

    # Find the first occurrence of "Engine ("
    engine_pos = data.find("Engine (")

    if engine_pos == -1:
        raise SyntaxError("The CON file does not specify an engine")

    # Find the first occurrence of "EngineData (" after "Engine ("
    enginedata_magic = "EngineData ("
    enginedata_pos = data.find(enginedata_magic, engine_pos)

    if enginedata_pos == -1:
        raise SyntaxError(f"The CON file specifies an engine but no {enginedata_magic}")

    # find the closing parenthesis after EngineData
    closing_pos = data.find(")", enginedata_pos)

    if closing_pos == -1:
        raise SyntaxError("No closing parentheses found for engine data")

    starting_pos = enginedata_pos + len(enginedata_magic)
    engine_files = data[starting_pos:closing_pos].strip().removesuffix(".eng").split(" ")
    engine_dir = engine_files[1].lower()
    engine_file = f"{engine_files[0]}.eng"
    shape_file = f"{engine_files[0]}.sd"
    engine_path = Path(consist).parent.parent / "trainset" / engine_dir / f"{engine_file}"
    shape_path = Path(consist).parent.parent / "trainset" / engine_dir / f"{shape_file}"

    return engine_path, shape_path


def _get_value(engine_description, param):
    search_string = f"{param}("
    param_pos = engine_description.find(search_string)

    if param_pos == -1:  # try again with one more whitespace
        search_string = f"{param} ("
        param_pos = engine_description.find(search_string)

    if param_pos == -1:
        raise SyntaxError(f"The ENG file does not specify parameter {param}")

    closing_pos = engine_description.find(")", param_pos)
    if closing_pos == -1:
        raise SyntaxError(f"No closing parentheses found for param {param}")

    starting_pos = param_pos + len(search_string)
    result = engine_description[starting_pos:closing_pos]
    return result.strip()


def _get_bounding_box(bounding_box_values):
    # OpenRails Coordinates are (with, height, length) -> in python we use (length, width, height)
    bbox_first = float(bounding_box_values[2]), float(bounding_box_values[0]), float(bounding_box_values[1])
    bbox_second = float(bounding_box_values[5]), float(bounding_box_values[3]), float(bounding_box_values[4])
    bounding_box = [bbox_first, bbox_second]
    return bounding_box


if __name__ == "__main__":
    properties = extract_properties(
        r"C:\Users\IT-USER\PycharmProjects\openrails-content\Demo Model 1\TRAINS\CONSISTS\MT_MT_Class 27 102 & 6 mk2 PP.CON")

    print(properties.mass, properties.bounding_box)
