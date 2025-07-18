import contextlib
import importlib.resources
import logging
import math
import os.path
import shutil
from typing import Tuple, Dict, Any, List

from .geometry import Vector, Pose, angle_between
from .railgraphs import Graph, EdgeSegment, Node, Edge, End, SceneryObject, SIGNAL_TYPE, Path
import routecreation.railgraphs as rg

UNDEFINED = 4294967295

GROUND_LEVEL = 1.0

DYNTRACK_Z_OFFSET = -0.2

DEFAULT_START_TILE = (-5354, 14849)

TILE_SIZE = 2048.0

OR_TILE = 'or_tile'

OR_SECTION_INDEX = 'or_section_index'

OR_TR_ITEM_ID = 'or_tr_item_id'

OR_TDB_INDEX = 'or_tdb_index'

OR_W_FILE_INDEX = 'or_w_file_index'

'''
Classes for writing OpenRails files
'''


class STFOutput:
    def __init__(self, f, signature_char):
        self._path = f
        self._signature = signature_char
        if len(signature_char) == 1:
            self._signature += '0'
        self._file = None
        self._parentheses = 0

    def __enter__(self):
        self._file = open(self._path, 'w', encoding='UTF-16')
        self.write(f'SIMISA@@@@@@@@@@JINX0{self._signature}t______\n\n')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        if self._file:
            self.close_parentheses()
            self._file.close()

    def write(self, content: str):
        lines = content.splitlines()
        indented_lines = ''
        for line in lines:
            line = line.lstrip()
            indent = self._parentheses
            if line.startswith(')'):
                indent -= 1
            assert indent >= 0, "unbalanced input"
            indented_lines += '\t' * indent + line + '\n'
            self._parentheses += line.count('(') - line.count(')')
        self._file.write(indented_lines)

    def close_parentheses(self):
        while self._parentheses > 0:
            self.write(')')

    def __add__(self, other):
        self.write(other)
        return self


class _Indexer:
    """
    Helper for assigning indices to objects. Indices for objects can be derived with [].

    Objects of this class are iterable; the iterator returns pairs (object, index)
    """

    def __init__(self, key: str, first_index=1):
        self.key = key
        self.next_index = first_index
        self.indices: Dict[Any, int] = {}

    def __getitem__(self, item):
        return self.get_or_add(item)

    def get_or_add(self, item) -> int:
        if item in self.indices:
            return self.indices[item]
        else:
            idx = self.next_index
            self.next_index += 1
            self.indices[item] = idx
            item.attrs[self.key] = idx
            return idx

    def __len__(self):
        return len(self.indices)

    def register(self, *items):
        for item in items:
            self.get_or_add(item)

    def __iter__(self):
        return iter(self.indices.items())

    def __contains__(self, item):
        return item in self.indices


_EMPTY_TILE = _Indexer(OR_W_FILE_INDEX)


def displayable(obj):
    shapefile = obj.attrs.get("shapefile", None)
    if obj.render and not shapefile:
        logging.warning("Adding an object without a shapefile to the OpenRails files, this may fail")
    return obj.render and shapefile


def pos2tile(pos: Vector, start_tile=DEFAULT_START_TILE):
    """
    Get the tile for a 2D position
    :param pos: the position
    :param start_tile: the start tile that position (0,0) maps to
    :return: tuple (tile X, tile Z)
    """
    x0, z0 = start_tile
    return round(pos.x / TILE_SIZE) + x0, round(pos.y / TILE_SIZE) + z0


def pos2world(pos: Vector, z=0.0, tile: Tuple[int, int] = None, start_tile=DEFAULT_START_TILE):
    """
    Convert 2D coordinates to world coordinates

    :param tile: the tile to use; derive from position if None
    :param pos: 2D coordinate to convert
    :param z: Z value (height) of world coordinate
    :param start_tile: the start tile that position (0,0) maps to
    :return: tuple (tile X, tile Z, X, Y, Z)
    """
    y = z + GROUND_LEVEL
    tile_x, tile_z = tile or pos2tile(pos, start_tile)
    x = pos.x - (tile_x - start_tile[0]) * TILE_SIZE
    z = pos.y - (tile_z - start_tile[1]) * TILE_SIZE
    return tile_x, tile_z, x, y, z


class _TileManager(Dict[Tuple[int, int], _Indexer]):
    """
    Managing tiles. The main task is

    - converting between 2D coordinates and world coordinates (tile + position)
    - assigning objects to tiles (*.w files), and an index in the *.w file
    """

    def __init__(self, tile_x: int, tile_z: int):
        """

        :param tile_x: initial tile X
        :param tile_z: initial tile Z
        """
        super().__init__()
        self.tile_x = tile_x
        self.tile_z = tile_z

    def register(self, item, pos: Vector):
        tile = self.pos2tile(pos)
        # we add also surrounding tiles, so we won't cross world boundaries
        for i in [-1, 0, 1]:
            for j in [-1, 0, 1]:
                surrounding_tile = (tile[0] + i, tile[1] + j)
                if surrounding_tile not in self:
                    self[surrounding_tile] = _Indexer(OR_W_FILE_INDEX)
        self[tile].register(item)
        item.attrs[OR_TILE] = tile

    def pos2tile(self, pos: Vector):
        """
        Get the tile for a 2D position
        :param pos: the position
        :return: tuple (tile X, tile Z)
        """
        return pos2tile(pos, (self.tile_x, self.tile_z))

    def pos2world(self, pos: Vector, z=0.0, tile: Tuple[int, int] = None):
        """
        Convert 2D coordinates to world coordinates

        :param tile: the tile to use; derive from position if None
        :param pos: 2D coordinate to convert
        :param z: Z value (height) of world coordinate
        :return: tuple (tile X, tile Z, X, Y, Z)
        """
        return pos2world(pos, z, tile, (self.tile_x, self.tile_z))

    def tiles(self):
        """

        :return: all the tiles as tuples (X, Z)
        """
        return self.keys()

    def by_tile(self, tile_x, tile_z):
        """
        Get an indexer for a tile. The returned indexer must be used for reading only!

        :param tile_x: tile X
        :param tile_z: tile Z
        :return: The indexer for tile (X, Z)
        """
        tile = (tile_x, tile_z)
        return self.get(tile, _EMPTY_TILE)

    def tile_and_index(self, item) -> Tuple[int, int, int]:
        """
        Look up the tile and index of an object

        :param item: object to look up
        :return: tuple (tile X, tile Z, index) for the object
        """
        for tile, indexer in self.items():
            if item in indexer:
                return tile[0], tile[1], indexer[item]


def _write_ts(f, curved, section=UNDEFINED, a=0.0, b=0.0):
    f.write(f'      TrackSection (\n'
            f'        SectionCurve ( {curved} ) {section} {a:g} {b:g} \n'
            f'      )\n')


class ORWriter:
    """
    Class for writing OpenRails files
    """

    def __init__(self, directory, graph: Graph, tile_x=DEFAULT_START_TILE[0], tile_z=DEFAULT_START_TILE[1],
                 template_folder: str = None):
        self.directory = directory
        self.base_name = os.path.basename(directory)
        self._world_indices = _TileManager(tile_x, tile_z)
        self._tdb_indices = _Indexer(OR_TDB_INDEX)
        self._tr_item_ids = _Indexer(OR_TR_ITEM_ID, 0)
        self._section_indices = _Indexer(OR_SECTION_INDEX, 40000)
        self.graph = graph
        graph.attrs[OR_TILE] = (tile_x, tile_z)
        self._init_indices()
        self.template_folder = template_folder

    def _init_indices(self):
        for edge in self.graph.edges:
            # tile_x, tile_z, _, _, _ = self._world_indices.pos2world(edge.start().pos)
            # if tile_x != self._world_indices.tile_x or tile_z != self._world_indices.tile_z:
            #     continue
            for segment in edge.segments:
                self._world_indices.register(segment, segment.start.pos)
            self._section_indices.register(*edge.segments)
            self._tdb_indices.register(edge)
            for obj in edge.scenery_objects:
                if not displayable(obj):
                    continue
                if obj.object_type == SIGNAL_TYPE:
                    self._tr_item_ids.register(obj)
                self._world_indices.register(obj, obj.global_pose.pos)

        self._tdb_indices.register(*self.graph.nodes)
        for obj in self.graph.scenery_objects:
            if not displayable(obj):
                continue
            assert obj.object_type != SIGNAL_TYPE, "signals must be owned by edges"
            self._world_indices.register(obj, obj.global_pose.pos)

    def ensure_directory_exists(self, directory):
        directory = os.path.join(self.directory, directory)
        if not os.path.exists(directory):
            os.mkdir(directory)

    def get_w_file_name(self, tile_x, tile_z):
        return os.path.join(self.directory, 'world', f'w{tile_x:+07}{tile_z:+07}.w')

    def write_world_files(self):
        self.ensure_directory_exists('world')
        self.ensure_directory_exists('tiles')
        with self.template() as template:
            for tile, objects in self._world_indices.items():
                with STFOutput(self.get_w_file_name(*tile), 'w') as f:
                    f.write('Tr_Worldfile (')
                    for obj, uid in objects:
                        if isinstance(obj, EdgeSegment):
                            self._write_dyntrack(f, obj, uid)
                        elif isinstance(obj, SceneryObject) and obj.render:
                            if obj.object_type == SIGNAL_TYPE:
                                self._write_signal_w(f, obj, uid)
                            else:
                                self._write_static_object(f, obj, uid)
                    f.write(')\n')
                tile_t, tile_raw = self._tile_file_names(*tile)
                shutil.copy(os.path.join(template, 'tiles', 'template.t'), tile_t)
                shutil.copy(os.path.join(template, 'tiles', 'template_y.raw'), tile_raw)

    def _write_dyntrack(self, f, obj, uid):
        f.write(f'Dyntrack (\n')
        section_idx = self._get_section_index(obj)
        f.write(f'UiD ( {uid} )\n')
        f.write('TrackSections (\n')
        if obj.straight():
            _write_ts(f, 0, section_idx, obj.length)
            _write_ts(f, 1)
        else:
            _write_ts(f, 0)
            _write_ts(f, 1, section_idx, obj.length / obj.radius, abs(obj.radius))
        _write_ts(f, 0)
        _write_ts(f, 1)
        _write_ts(f, 0)
        f.write(f'    )\n'
                f'    SectionIdx ( {self._section_indices[obj]} )\n'
                f'    Elevation ( 0 )\n'
                f'    CollideFlags ( 39 )\n'
                f'    StaticFlags ( 00100000 )\n'
                f'{self._position_and_qdirection(obj.start, DYNTRACK_Z_OFFSET, facing="y")}\n'
                '    VDbId ( 4294967295 )\n'
                '  )\n')

    def _write_static_object(self, f, obj: SceneryObject, uid):
        static_flags = 0x00010000
        if obj.attrs.get('animated', False):
            static_flags |= 0x00080000
        static_flags |= (int(obj.attrs.get('classification', 0)) & 7) << 24
        f.write(f'Static (\n'
                f'UiD ( {uid} )\n'
                f'FileName ( {obj.attrs.get("shapefile", str(obj.name or obj.object_type) + ".s")} )\n'
                f'StaticFlags ( {static_flags:8x} )\n'
                f'{self._position_and_qdirection(obj.global_pose, obj.attrs.get("z", 0.0))}\n'
                f'VDbId ( {UNDEFINED} )\n'
                ' )\n')

    def _write_signal_w(self, f, obj: SceneryObject, uid):
        static_flags = 0x00010000
        if obj.attrs.get('animated', False):
            static_flags |= 0x00080000
        f.write(f'Signal (\n'
                f'    UiD ( {uid} )\n'
                f'    FileName ( {obj.attrs.get("shapefile", "Signal.s")} )\n'
                f'    StaticFlags ( {static_flags:8x} )\n'
                f'    {self._position_and_qdirection(obj.global_pose, facing="-y")}\n'
                f'    VDbId ( {UNDEFINED} )\n'
                f'    SignalSubObj ( 00000001 )\n'
                f'    SignalUnits ( 1 \n'
                f'        SignalUnit ( 0\n'
                f'            TrItemId ( 0 {self._tr_item_ids[obj]} )\n'
                f'        )\n'
                f'    )\n'
                f')\n')
        rg.DBG_TRAVEL = False

    def _position_and_qdirection(self, pose: Pose, z=0.0, facing='x'):
        if facing == 'x':
            offset = 0.0
        elif facing == 'y':
            offset = 0.25 * math.pi
        elif facing == '-x':
            offset = 0.5 * math.pi
        elif facing == '-y':
            offset = 0.75 * math.pi
        else:
            raise ValueError("facing is none of 'x', 'y', '-x', '-y'")

        _, _, x, y, z = self._world_indices.pos2world(pose.pos, z)
        return (
            f'    Position ( {x:g} {y:g} {z:g} )\n'
            f'    QDirection ( 0 {math.sin(pose.direction / 2.0 - offset):g} '
            f'0 {math.cos(pose.direction / 2.0 - offset):g} )'
        )

    def write_tsection_file(self):
        with STFOutput(os.path.join(self.directory, 'tsection.dat'), 'T') as f:
            # TSRE counts non-existent sections also
            f.write(f'TrackSections ( {2 * len(self._section_indices)}\n')
            for obj, idx in self._section_indices:
                idx -= 20000
                if obj.straight():
                    _write_ts(f, 0, 2 * idx, obj.length, 0.0)
                else:
                    angle = abs(obj.length / obj.radius)
                    radius = abs(obj.radius)
                    _write_ts(f, 1, 2 * idx, -angle, radius)
                    _write_ts(f, 1, 2 * idx + 1, angle, radius)

            f.write(f')\nSectionIdx ( {len(self._section_indices)}\n')
            for obj, idx in self._section_indices:
                f.write(f'TrackPath ( {idx} 1 {self._get_section_index(obj)} )\n')
            f.write(')')

    def write_tdb(self):
        def _uid(item, pose, reserved='1'):
            w_tile_x, w_tile_z, world = self._world_indices.tile_and_index(item)
            tile_x, tile_z, x, y, z = self._world_indices.pos2world(pose.pos)
            return (f'{w_tile_x} {w_tile_z} {world} {reserved} '
                    f'{tile_x} {tile_z} {x:g} {y:g} {z:g} '
                    f'0 {(-pose.direction - 0.5 * math.pi) % (2 * math.pi) - math.pi:g} 0')

        with STFOutput(os.path.join(self.directory, self.base_name + '.tdb'), 'T') as f:
            f.write(f'TrackDB (\n Serial ( 0 ) \n TrackNodes ( {len(self._tdb_indices)}')
            for obj, idx in self._tdb_indices:
                f.write(f'TrackNode ( {idx}')
                if isinstance(obj, Node):
                    if not (obj.degree() == 1 or obj.degree() > 2):
                        raise Exception(
                            f'Node with bad degree {obj.degree()} found, which is not supported by OpenRails')
                    end = obj.ends()[-1]
                    primary_segment = end.segment()
                    if obj.degree() == 1:
                        f.write(f'TrEndNode ( 0 )')
                    else:
                        f.write(f'TrJunctionNode ( 0 {self._section_indices[primary_segment]} 0)')
                    f.write(f'UiD ( {_uid(primary_segment, end.pose())} )')
                    f.write(f'TrPins ( 1 {len(obj.ends()) - 1}')
                    for end in obj.ends():
                        assert end.edge in self._tdb_indices
                        f.write(f'TrPin ( {self._tdb_indices[end.edge]} {end.side.value} )')
                    f.write(')\n)')
                elif isinstance(obj, Edge):
                    f.write('TrVectorNode (')
                    f.write(f'TrVectorSections ( {len(obj.segments)}')
                    for segment in obj.segments:
                        f.write(f'{self._get_section_index(segment)} {self._section_indices[segment]} '
                                f'{_uid(segment, segment.start, "0 1 00")}')
                    f.write(')')
                    tr_items = [sig for sig in obj.scenery_objects if sig.object_type == SIGNAL_TYPE and sig.render]
                    if tr_items:
                        f.write(f'TrItemRefs ( {len(tr_items)}')
                        for item in tr_items:
                            f.write(f'TrItemRef ( {self._tr_item_ids[item]} )')
                        f.write(')')
                    f.write(')')
                    f.write('TrPins ( 1 1')
                    for end in (obj.source_end, obj.target_end):
                        assert end.node() in self._tdb_indices, end.node()
                        f.write(f'TrPin ( {self._tdb_indices[end.node()]} {1 if end == end.node().ends()[0] else 0} )')
                    f.write(')\n)')
            f.write(')')
            if len(self._tr_item_ids) > 0:
                f.write(f'TrItemTable ( {len(self._tr_item_ids)}')
                for item, idx in self._tr_item_ids:
                    assert isinstance(item.relative_to, Edge)
                    s = item.pose.pos.x
                    ref_pose = item.relative_to.travel(s)
                    tile_x, tile_z, x, y, z = self._world_indices.pos2world(ref_pose.pos)
                    if item.object_type == SIGNAL_TYPE:
                        sig_type = item.attrs.get('signal_type', 'Ks')
                        sig_dir = 1 if abs(
                            angle_between(ref_pose.direction, item.global_pose.direction)) <= 0.5 * math.pi else 0
                        f.write('SignalItem (\n'
                                f'TrItemId ( {idx} )\n'
                                f'TrItemSData ( {s} 00000002 )\n'
                                f'TrItemRData ( {x} {y} {z} {tile_x} {tile_z})\n'
                                f'TrSignalType ( 00000000 {sig_dir} 1.8310872 {sig_type} )\n)')

    def _get_section_index(self, segment: EdgeSegment):
        """

        :param segment:
        :return: the path section index for an edge segment
        """
        idx = self._section_indices[segment]
        # TSRE assigns even indices to straight and left turn segments, and odd indices to right turns
        if segment.radius <= 0.0:
            return 2 * idx - 40000
        else:
            return 2 * idx - 40000 + 1

    def write_path_file(self, filename: str, name: str, start_name: str, end_name: str, points: List[End]):
        locations = []
        started = False
        offset = points.start_offset if isinstance(points, Path) else 0.0
        for end in points:
            if not started and offset > end.edge.length():
                offset -= end.edge.length()
                continue
            locations.append((end.travel(offset).pos, '2 0' if started else '1 1', '00000000'))
            # check if the edge to the next node is unique. Otherwise, insert an intermediate point
            for other in end.node().ends():
                if other != end and other.other_end().node() == end.other_end().node():
                    locations.append((end.travel(end.edge.length() / 2.0).pos, '1 1', '00000004'))
                    break
            started = True
            offset = 0.0
        locations.append((points[-1].other_end().pose().pos, '1 1', '00000000'))
        locations = list(enumerate(locations))
        locations.sort(key=lambda _x: _x[1][1], reverse=True)
        perm = {idx: pdp for pdp, (idx, _) in enumerate(locations)}
        self.ensure_directory_exists('paths')
        with STFOutput(os.path.join(self.directory, 'paths', filename + '.pat'), 'P') as f:
            f.write('Serial ( 1 )')
            f.write('TrackPDPs (')
            for _, (loc, flags, _) in locations:
                tile_x, tile_z, x, y, z = self._world_indices.pos2world(loc)
                f.write(f'TrackPDP ( {tile_x} {tile_z} {x} {y} {z} {flags} )')
            f.write(')')
            f.write(f'''TrackPath (
                        TrPathName ( "{filename}" )
                        Name ( "{name}" )
                        TrPathStart ( "{start_name}" )
                        TrPathEnd ( "{end_name}" )
                        TrPathNodes ( {len(locations)}''')
            for idx in range(len(locations)):
                pdp = perm[idx]
                flags = locations[pdp][1][2]
                nxt = (idx + 1) if idx + 1 < len(locations) else UNDEFINED
                f.write(f'TrPathNode ( {flags} {nxt} {UNDEFINED} {pdp} )')
            f.write(')\n)')

    def write_track_file(self):
        with STFOutput(os.path.join(self.directory, self.base_name + '.trk'), 'r1') as f:
            f.write(f'''
                Tr_RouteFile (
                    RouteID ( {self.base_name} )
                    Name ( {self.base_name} )
                    Description ( "" )
                    Graphic ( graphic.ace )
                    LoadingScreen ( load.ace )
                    FileName ( {self.base_name} )
                    Electrified ( 00000000 )
                    Mountains ( 00000000 )
                    OverheadWireHeight ( 0 )
                    PassengerRuleSet ( 0 )
                    FreightRuleSet ( 0 )
                    SignalSet ( 0 )
                    GantrySet ( 0 )
                    TrackGauge ( 0 )
                    Era ( 0 )
                    SpeedLimit ( 44.444443 )
                    Environment (
                        SpringClear ( sun.env )
                        SpringRain ( rain.env )
                        SpringSnow ( snow.env )
                        SummerClear ( sun.env )
                        SummerRain ( rain.env )
                        SummerSnow ( snow.env )
                        AutumnClear ( sun.env )
                        AutumnRain ( rain.env )
                        AutumnSnow ( snow.env )
                        WinterClear ( sun.env )
                        WinterRain ( rain.env )
                        WinterSnow ( snow.env )
                    )
                    TerrainErrorScale ( 1 )
                    RouteStart ( {self._world_indices.tile_x} {self._world_indices.tile_z} 0 0 )
                    MilepostUnitsKilometers ( )
                    DefaultCrossingSMS ( crossing.sms )
                    DefaultSignalSMS ( signal.sms )
                    DefaultWaterTowerSMS ( wtower.sms )
                    DefaultCoalTowerSMS ( ctower.sms )
                    DefaultDieselTowerSMS ( dtower.sms )
                    TempRestrictedSpeed ( 0 )
                    ORTSUserPreferenceForestClearDistance ( 0 )
                    )
                    ''')

    def copy_route_template(self, overwrite=False):
        def copy_function(src, dst):
            directory, filename = os.path.split(dst)
            basename, ext = os.path.splitext(filename)
            if ext in ['.w', '.tdb', '.trk']:
                return
            if ext in ['.rdb']:
                dst = os.path.join(directory, self.base_name + ext)

            shutil.copy(src, dst)

        if not os.path.exists(self.directory):
            with self.template() as template:
                shutil.copytree(template, self.directory, copy_function=copy_function)

        if overwrite:
            with self.template() as template:
                shutil.rmtree(self.directory)
                shutil.copytree(template, self.directory, copy_function=copy_function)

    def _tile_file_names(self, tile_x: int, tile_z: int):
        x = tile_x + (1 << 14)
        z = tile_z + (1 << 14)
        x = x ^ z
        x = ~x
        z = ~z
        tile_idx = 0
        for i in range(15):
            tile_idx |= ((x & (1 << i)) | ((z & (1 << i)) << 1)) << i
        tile_idx <<= 2
        basename = os.path.join(self.directory, 'tiles', f'-{tile_idx:08x}')
        return basename + '.t', basename + '_y.raw'

    def write_all(self, overwrite=False):
        self.copy_route_template(overwrite=overwrite)
        self.write_track_file()
        self.write_tsection_file()
        self.write_world_files()
        self.write_tdb()

    def pos2world(self, pos: Vector, z=0.0, tile: Tuple[int, int] = None):
        return self._world_indices.pos2world(pos, z, tile)

    def get_world_tile_and_index(self, obj: object):
        return self._world_indices.tile_and_index(obj)

    def template(self):
        if self.template_folder is None:
            return importlib.resources.as_file(importlib.resources.files().joinpath('template'))
        else:
            return contextlib.nullcontext(self.template_folder)
