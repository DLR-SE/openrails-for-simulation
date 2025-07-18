import heapq
import json
import math
from abc import abstractmethod
from enum import Enum
from typing import Optional, List, Iterator, Iterable, Dict, Tuple, Union, Set, overload, Any

from routecreation.geometry import Pose, polar, angle_between, Vector, biarc_interpolation

"""
Classes for railway graphs. 

A railway graph models a rail network as a directed graph. 
Edges model tracks connecting nodes. Edges contain of sections (EdgeSection), which are either arcs or straight. 
Nodes have a position and a direction. For nodes with two connected edges, 
this is the direction in that the track passes the node. For switches, the direction pints towards the tip.  
"""

MIN_ANGLE = 0.0
MAX_RADIUS = float('Inf')

SIGNAL_TYPE = 'Signal'
SENSOR_TYPE = 'Sensor'


class RailgraphObject:

    def __init__(self, graph: 'Graph' = None):
        self.graph = graph

    @abstractmethod
    def to_global(self, other: Union['Pose', Vector]):
        """
        Translate a point (or pose) from the local coordinate system spanned by this node
        to the global coordinate system
        """
        raise NotImplementedError

    @abstractmethod
    def to_local(self, other: Union['Pose', Vector]):
        """
        Translate a point (or pose) from the local coordinate system spanned by this node
        to the global coordinate system
        """
        raise NotImplementedError

    @abstractmethod
    def get_index(self):
        """
        Return the index in the containing graph
        """
        raise NotImplementedError


class SceneryObject(RailgraphObject):
    """
    This models an object in the scenery, e.g. an obstacle, signal, crossing, ...
    """

    def __init__(self, pose: Pose, object_type: str = None, name: str = None,
                 relative_to: Union['Graph', 'Edge'] = None, render: bool = True, **attrs):
        super().__init__(relative_to.graph if isinstance(relative_to, RailgraphObject) else relative_to)
        self.pose = pose
        self.object_type = object_type
        self.name = name
        self.attrs = attrs
        self.render = render
        if isinstance(relative_to, Edge):
            self.relative_to = relative_to
            relative_to.scenery_objects.append(self)
        else:
            self.graph.scenery_objects.append(self)
            self.relative_to = None


    @property
    def global_pose(self):
        if self.relative_to:
            return self.relative_to.to_global(self.pose)
        else:
            return self.pose

    @global_pose.setter
    def global_pose(self, pose: Pose):
        if self.relative_to:
            self.pose = self.relative_to.to_local(pose)
        else:
            self.pose = pose

    def to_global(self, other: Union['Pose', Vector]):
        """
        Translate a point (or pose) from the local coordinate system spanned by this node
        to the global coordinate system
        """
        return self.global_pose.to_global(other)

    def to_local(self, other: Union['Pose', Vector]):
        """
        Translate a point (or pose) from the local coordinate system spanned by this node
        to the global coordinate system
        """
        return self.global_pose.to_local(other)

    def get_index(self):
        if self.graph and self in self.graph.scenery_objects:
            return self.graph.scenery_objects.index(self)
        else:
            # TODO handle case for signals
            return -1


class Node(RailgraphObject):
    """
    Nodes have a position and a direction. For nodes with two connected edges,
    this is the direction in that the track passes the node. For switches, the direction pints towards the tip.

    The lists of incoming and outgoing edges shall not be modified directly. They are managed by the edges itself.

    """

    def __init__(self, pose: Pose, graph: 'Graph' = None, s=0.0):
        """
        :param pose: The node pose
        :param s: The node way
        """
        super().__init__(graph)
        self.pose = pose
        self.incoming: List['Edge'] = []
        self.outgoing: List['Edge'] = []
        self.s = s
        self.attrs = {}
        if self.graph:
            self.graph.nodes.append(self)

    def directions(self):
        """

        :return: the directions of all the incident edges
        """
        return [e.end().direction for e in self.incoming] + [e.start().direction for e in self.outgoing]

    def calculate_direction(self):
        """
        Calculate and assign the direction of the node based on the directions of incident edges.

        If False is returned, the node ought to be a crossing and shall be split into several nodes.

        :return: True if a direction could be assigned, False otherwise
        """
        dirs = self.directions()
        if len(dirs) == 1:
            self.pose = Pose(self.pose.pos, dirs[0])
            return True
        elif len(dirs) == 2:
            if abs(angle_between(dirs[0], dirs[1])) <= 0.5 * math.pi:
                return False
            # direction is halfway on the curve
            # assume that the incoming edge is first, so direction shall be between d0 + pi and d1
            self.pose = Pose(self.pose.pos, dirs[1] + angle_between(dirs[1], dirs[0] + math.pi) * 0.5)
            return True
        else:
            for i in range(len(dirs)):
                # assume that the tip is in direction d_i
                # other directions d_j (j != i) have an angle > 120 deg to d_i
                if all(abs(angle_between(dirs[i], d)) > 0.66 * math.pi
                       for d in dirs[:i] + dirs[i + 1:]):
                    self.pose = Pose(self.pose.pos, dirs[i])
                    return True
        return False

    def degree(self):
        """

        :return: the degree (= number of incident edges) of the node
        """
        return len(self.incoming) + len(self.outgoing)

    def ends(self) -> List['End']:
        """
        All the ends incident to this node, with the end at the tip first

        :return: the list of ends
        """
        ends = [e.target_end for e in self.incoming] + [e.source_end for e in self.outgoing]

        # the tip is the edge in direction of this node, so move this to top
        ends.sort(key=lambda e: abs(angle_between(self.pose.direction, e.pose().direction)))
        ends[1:].sort(key=End.curvature)
        return ends

    def connected_ends(self, end):
        """
        Calculate other ends that are navigable from a given end
        :param end: The incoming end
        :return: the list of connected ends
        """
        ends = self.ends()
        assert end in ends
        if end == ends[0]:
            return ends[1:]
        else:
            return ends[:1]

    def add_edge(self, length, radius=0.0, backward=False):
        """
        Add a new edge to this node with a single segment
        :param length: length of the edge. If negative, create an incoming edge
        :param radius: radius of the (single) edge segment
        :param backward: if True, use the opposite direction from this node
        """
        edge = Edge(source=self)
        start_pose = self.pose.reverse() if (length < 0) ^ backward else self.pose
        segment = EdgeSegment(start_pose, abs(length), radius)
        edge.segments.append(segment)
        end_pose = segment.end()
        edge.set_target(Node(end_pose.reverse(), self.graph, self.s + length))
        if length >= 0:
            return edge.target_end
        else:
            edge.flip()
            return edge.source_end

    def to_global(self, other: Union['Pose', Vector]):
        """
        Translate a point (or pose) from the local coordinate system spanned by this node
        to the global coordinate system
        """
        return self.pose.to_global(other)

    def to_local(self, other: Union['Pose', Vector]):
        """
        Translate a point (or pose) from the local coordinate system spanned by this node
        to the global coordinate system
        """
        return self.pose.to_local(other)

    def get_index(self):
        if self.graph and self in self.graph.nodes:
            return self.graph.nodes.index(self)
        return -1


class EdgeEnd(Enum):
    SOURCE = 1
    TARGET = 0


class End:
    """
    Models an end of an edge
    """

    def __init__(self, edge: 'Edge', side: EdgeEnd):
        self.edge = edge
        self.side = side

    def pose(self):
        """
        :return: The pose of the edge at this end
        """
        return self.edge.start() if self.side == EdgeEnd.SOURCE else self.edge.end()

    def node(self):
        """
        :return: The node at this end
        """
        return self.edge.source() if self.side == EdgeEnd.SOURCE else self.edge.target()

    def set_node(self, node: Node):
        """
        connect this end to a new node
        """
        self.edge.set_source(node) if self.side == EdgeEnd.SOURCE else self.edge.set_target(node)

    def radius(self):
        """
        :return: Radius of the edge at this end
        """
        if self.edge.segments:
            if self.side == EdgeEnd.SOURCE:
                return self.edge.segments[0].radius
            else:
                return -self.edge.segments[-1].radius
        else:
            return 0.0

    def curvature(self):
        """
        :return: Curvature of the edge at this end
        """
        radius = self.radius()
        return radius and 1.0 / radius

    def segment(self):
        """
        :return: The edge segment at this end, if any
        """
        return ((self.edge.segments or None)
                and (self.edge.segments[0] if self.side == EdgeEnd.SOURCE else self.edge.segments[-1]))

    def other_end(self):
        """
        :return: the other end of the edge
        """
        return self.edge.target_end if self.side == EdgeEnd.SOURCE else self.edge.source_end

    def add_edge(self, length, radius=0.0, extend_edge=True):
        """
        Add a new edge incident to this end
        """
        if length == 0:
            return self
        if extend_edge and length >= 0 and self.node().degree() == 1:
            start_pose = self.pose().reverse()
            segment = EdgeSegment(start_pose, length, radius)
            end_pose = segment.end()
            if self.side == EdgeEnd.TARGET:
                self.edge.segments.append(segment)
                self.node().s += length
            else:
                segment.flip()
                self.edge.segments.insert(0, segment)
                self.node().s -= length
            self.node().pose = end_pose.copy()

            return self
        else:
            # check whether we are going to create a turnout
            if self.node().connected_ends(self):
                # we will create a turnout with the tip (= node direction) towards us
                # print('create turnout')
                self.node().pose = self.pose().copy()
                next_end = self.node().add_edge(length, radius, True)
            else:
                # we may or may not create a turnout, but if so, the tip will point away from us
                self.node().pose = self.pose().reverse()
                next_end = self.node().add_edge(length, radius, False)
            if self.side == EdgeEnd.SOURCE:
                next_end.edge.flip()
                next_end = next_end.edge.source_end
            return next_end

    def is_tip(self):
        """
        return True if this is the tip of a switch
        """
        all_ends = self.node().ends()
        return len(all_ends) >= 3 and self == all_ends[0]

    def travel(self, s):
        """Get a pose with given distance along the edge, away from the node"""
        if self.side == EdgeEnd.SOURCE:
            return self.edge.travel(s)
        else:
            return self.edge.travel(self.edge.length() - s).reverse()

    def __repr__(self):
        return f'({self.edge}, {self.side})'


class Edge(RailgraphObject):
    """
    Edges model tracks connecting nodes. Edges contain of sections (EdgeSection), which are either arcs or straight.
    """

    def __init__(self, source: Optional[Node] = None, target: Optional[Node] = None, graph: 'Graph' = None):
        """

        :param source: Source node
        :param target: Target node
        """
        super().__init__(graph or (source and source.graph) or (target and target.graph))
        self._source = source
        source and source.outgoing.append(self)
        self._target = target
        target and target.incoming.append(self)
        self.segments: List[EdgeSegment] = []
        self.source_end = End(self, EdgeEnd.SOURCE)
        self.target_end = End(self, EdgeEnd.TARGET)
        self.attrs = {}
        self.scenery_objects: List[SceneryObject] = []
        if self.graph:
            self.graph.edges.append(self)

    def flip(self):
        """
        Reverse this edge (exchange source and target). Segments are also reversed.
        :return:
        """
        self._source and self._source.outgoing.remove(self)
        self._target and self._target.incoming.remove(self)
        self._source, self._target = (self._target, self._source)
        self._target and self._target.incoming.append(self)
        self._source and self._source.outgoing.append(self)

        for segment in self.segments:
            segment.flip()
        self.segments.reverse()
        for obj in self.scenery_objects:
            if obj.relative_to == self:
                obj.pose = obj.pose.reverse()
                obj.pose.pos.x = self.length() - obj.pose.pos.x
                obj.pose.pos.y *= -1

    def source(self):
        """
        Return source node
        """
        return self._source

    def target(self):
        """
        Return target node
        """
        return self._target

    def set_source(self, source: Node):
        """
        Set a new source

        :param source: new source
        """
        if source != self._source:
            self._source and self._source.outgoing.remove(self)
            source and source.outgoing.append(self)
            self._source = source

    def set_target(self, target: Node):
        """
        Set a new target

        :param target: new target
        """
        if target != self._target:
            self._target and self._target.incoming.remove(self)
            target and target.incoming.append(self)
            self._target = target

    def start(self):
        """

        :return: the start pose (pointing towards target)
        """
        if len(self.segments) > 0:
            return self.segments[0].start
        else:
            p = self._source.pose.pos
            q = self._target.pose.pos
            return Pose(p, (q - p).alpha())

    def end(self):
        """

        :return: the end pose (pointing towards source)
        """
        if len(self.segments) > 0:
            return self.segments[-1].end()
        else:
            p = self._target.pose.pos
            q = self._source.pose.pos
            return Pose(p, (q - p).alpha())

    def create_biarcs(self):
        """
        Create EdgeSegments by bi-arc interpolation

        :return: None
        """
        start = self._source.pose
        if abs(angle_between(start.direction, self.start().direction)) > 0.5 * math.pi:
            start = start.reverse()

        end = self._target.pose
        if abs(angle_between(end.direction, self.end().direction)) <= 0.5 * math.pi:
            end = end.reverse()

        p1 = start.pos
        t1 = polar(start.direction)
        p2 = end.pos
        t2 = polar(end.direction)
        t = polar(self.start().direction)

        if abs(t1 @ t) + abs(t2 @ t) < 0.0001:
            self.segments = [EdgeSegment(self.start(), abs(end.pos - start.pos))]
        else:
            r1, theta1, r2, theta2 = biarc_interpolation(p1, t1, p2, t2)

            if abs(theta1) < MIN_ANGLE or r1 > MAX_RADIUS or abs(theta2) < MIN_ANGLE or r2 > MAX_RADIUS:
                self.segments = [EdgeSegment(self.start(), abs(end.pos - start.pos))]
            else:
                l1 = abs(theta1 * r1)
                if theta1 > 0.0:
                    r1 = -r1
                s1 = EdgeSegment(start, l1, r1)
                l2 = abs(theta2 * r2)
                if theta2 < 0.0:
                    r2 = -r2
                s2 = EdgeSegment(s1.end().reverse(), l2, r2)
                self.segments = [s1, s2]

    def length(self):
        if self.segments:
            return sum(segment.length for segment in self.segments)
        else:
            return abs(self._source.pose.pos - self._target.pose.pos)

    def to_global(self, other, offset: Optional[float] = 0.0, extend_before=True, extend_after=True):
        """
                Transform from local to global coordinates

                :param other: pose or point to transform
                :param offset: offset along path
                :param extend_before: whether to transform coordinates before path start
                :param extend_after: whether to transform coordinates after path end
                """
        if offset is None:
            offset = self._source.s
        if not self.segments:
            EdgeSegment(self.start(), self.length()).to_global(other, offset, extend_before, extend_after)
        for idx, segment in enumerate(self.segments):
            transformed = segment.to_global(other, offset,
                                            extend_before and idx == 0,
                                            extend_after and idx == len(self.segments) - 1)
            offset += segment.length
            if transformed:
                return transformed

    def to_local(self, other, offset: Optional[float] = 0.0, extend_before=True, extend_after=True):
        """
                Transform from global to local coordinates

                :param other: pose or point to transform
                :param offset: offset along path
                :param extend_before: whether to transform coordinates before path start
                :param extend_after: whether to transform coordinates after path end
                """
        if offset is None:
            offset = self._source.s
        if not self.segments:
            return EdgeSegment(self.start(), self.length()).to_local(other, offset, extend_before, extend_after)
        for idx, segment in enumerate(self.segments):
            transformed = segment.to_local(other, offset,
                                           extend_before,
                                           extend_after and idx == len(self.segments) - 1)
            offset += segment.length
            if transformed:
                return transformed

    def travel(self, s):
        if not self.segments:
            return Pose(self.start().pos + polar(self.start().direction, s), self.start().direction)
        else:
            for segment in self.segments[:-1]:
                if s <= segment.length:
                    return segment.travel(s)
                s -= segment.length
            return self.segments[-1].travel(s)

    def get_index(self):
        if self.graph and self in self.graph.edges:
            return self.graph.edges.index(self)
        return -1

    def __repr__(self):
        return (f'({self.get_index()}: {self._source and self._source.get_index()}, '
                f'{self._target and self._target.get_index()})')


class EdgeSegment:
    """
    A segment of an edge. May either be straight or an arc, depending on radius.

    - radius < 0: left curve arc
    - radius = 0: straight segment
    - radius > 0: right curve arc
    """

    def __init__(self, start: Pose, length: float, radius=0.0):
        """

        :param start: start pose of the segment
        :param length: length of the segment
        :param radius: radius of the segment
        """
        self.start = start
        """
        Start pose of the segment
        """
        self.length = length
        """
        Length of the segment
        """
        self.radius = radius
        """
        Radius of the circle this segment follows. 
        """
        self.attrs = {}

    def straight(self):
        """

        :return: True if this is a straight segment, False if it is an arc
        """
        return self.radius == 0.0

    def end(self):
        """

        :return: the end pose of the segment, pointing towards the start
        """
        return self.travel(self.length).reverse()

    def travel(self, s: float):
        if self.straight():
            return Pose(self.start.pos + polar(self.start.direction, s), self.start.direction)
        else:
            center = self.center()
            angle = s / self.radius
            beta = self.start.direction + 0.5 * math.pi - angle
            return Pose(center + polar(beta, self.radius), self.start.direction - angle)

    def flip(self):
        """
        Reverse this segment
        :return:
        """
        self.start = self.end()
        self.radius = - self.radius

    def center(self):
        """
        The center of the circle followed by this track segment
        """
        alpha = self.start.direction - 0.5 * math.pi
        return self.start.pos + polar(alpha, self.radius)

    def to_global(self, other: Union[Vector, Pose], offset=0.0, extend_before=True, extend_after=True):
        if isinstance(other, Pose):
            x = other.pos.x - offset
            y = other.pos.y
        else:
            x = other.x - offset
            y = other.y
        if x < 0 and not extend_before:
            return None
        if x > self.length and not extend_after:
            return None
        q = self.travel(x)
        vy = polar(q.direction).ortho()
        p = q.pos + vy * y
        if isinstance(other, Pose):
            return Pose(p, other.direction + q.direction)
        else:
            return p

    def to_local(self, other: Union[Vector, Pose], offset=0.0, extend_before=True, extend_after=True):
        """
                Transform from global to local coordinates

                :param other: pose or point to transform
                :param offset: offset along path
                :param extend_before: whether to transform coordinates before path start
                :param extend_after: whether to transform coordinates after path end
                """
        q = self.start
        if not self.straight():
            c = self.center()
            if isinstance(other, Pose):
                p = other.pos
            else:
                p = other
            d = abs(p - c)
            if self.radius > 0:
                y = d - self.radius
                angle = (self.start.direction + 0.5 * math.pi - (p - c).alpha()) % (2 * math.pi)
            else:
                y = -self.radius - d
                angle = ((p - c).alpha() + 0.5 * math.pi - self.start.direction) % (2 * math.pi)
            s = angle * abs(self.radius)
            if s <= self.length:
                x = offset + s
                if isinstance(other, Pose):
                    return Pose(Vector(x, y),
                                 (other.direction - self.start.direction + angle) if self.radius >= 0 else
                                 (other.direction - self.start.direction - angle))
                else:
                    return Vector(x, y)
            else:
                if angle >= math.pi + 0.5 * self.length / abs(self.radius):
                    if not extend_before:
                        return None
                else:
                    if not extend_after:
                        return None
                    q = self.travel(self.length)
                    offset += self.length

        other = q.to_local(other)
        if isinstance(other, Pose):
            x = other.pos.x
            other = Pose(Vector(x + offset, other.pos.y), other.direction)
        else:
            x = other.x
            other = Vector(x + offset, other.y)
        if x < 0 and not extend_before:
            return None
        if x > self.length and not extend_after:
            return None
        return other


class Graph:
    def __init__(self):
        self.nodes: List[Node] = []
        self.edges: List[Edge] = []
        self.scenery_objects: List[SceneryObject] = []
        self.attrs = {}

    def set_directions(self):
        """
        Set node directions based on positions. Thereby, split nodes that appear to be crossings in several nodes.
        """
        new_nodes = {}
        for node in self.nodes:
            while not node.calculate_direction():
                new_node = Node(node.pose)
                new_nodes[new_node] = node
                if node.degree() == 2:
                    # we have a sharp corner that we need to split into two ends
                    node.ends()[0].set_node(new_node)
                    # print('add end')
                else:
                    # print('split')
                    # we have a crossing
                    ends = node.ends()
                    opposite = 1
                    for i in range(2, len(ends)):
                        if abs(angle_between(ends[0].pose().direction, ends[i].pose().direction)) > \
                                abs(angle_between(ends[0].pose().direction, ends[opposite].pose().direction)):
                            opposite = i
                    # print(math.degrees(abs(angle_between(ends[0].pose().direction, ends[opposite].pose().direction))))
                    ends[0].set_node(new_node)
                    ends[opposite].set_node(new_node)
                new_node.calculate_direction()

        self.nodes.extend(new_nodes.keys())
        return new_nodes

    def remove_edge(self, edge):
        """
        Remove an edge from the graph, cleaning up references
        """
        edge.set_source(None)
        edge.set_target(None)
        self.edges.remove(edge)

    def remove_node(self, node):
        """
        Remove a node from the graph, including incident edges
        """
        for edge in node.incoming + node.outgoing:
            self.remove_edge(edge)
        self.nodes.remove(node)

    def create_segments(self):
        """
        Create segments for all edges in this graph, using bi-arc interpolation
        """
        for edge in self.edges:
            edge.create_biarcs()

    def contract_edges(self) -> Dict[Union[Node, Edge], Edge]:
        """
        Remove nodes with two incident edges by joining the two edges

        :return: a map from the removed elements to the edges they have been merged into.
        """
        removed = {}
        for node in list(self.nodes):
            if node.degree() == 2:
                edges = node.incoming + node.outgoing
                if edges[0] == edges[1]:
                    # this is a self loop and we can't do anything
                    # print('self loop')
                    continue
                if len(node.incoming) == 2:
                    node.incoming[1].flip()
                if len(node.outgoing) == 2:
                    node.outgoing[1].flip()
                assert len(node.incoming) == 1
                assert len(node.outgoing) == 1
                e1 = node.incoming[0]
                e2 = node.outgoing[0]
                e1.set_target(e2.target())
                for obj in e2.scenery_objects:
                    if obj.relative_to == e2:
                        obj.relative_to = e1
                        obj.pose.pos.x += e1.length()
                    e1.scenery_objects.append(obj)
                e2.scenery_objects.clear()
                e1.segments.extend(e2.segments)
                self.remove_edge(e2)
                removed[node] = e1
                removed[e2] = e1
                self.nodes.remove(node)
        return removed

    def remove_unconnected_nodes(self):
        """
        Remove all nodes without incident edges
        """
        size = len(self.nodes)
        self.nodes = [n for n in self.nodes if n.degree() > 0]
        # if len(self.nodes) < size:
        #    print(f'remove {len(self.nodes) - size} of {size} unconnected nodes')

    def check(self):
        """
        Check sanity of the graph structure
        """
        for edge in self.edges:
            assert edge.source()
            assert edge in edge.source().outgoing
            assert edge.target()
            assert edge in edge.target().incoming

        for node in self.nodes:
            for edge in node.incoming:
                assert node == edge.target()
            for edge in node.outgoing:
                assert node == edge.source()

    def end_nodes(self):
        """
        Return the nodes that are ends of tracks, i.e., having exactly one incident edge
        """
        return [node for node in self.nodes if node.degree() == 1]

    def make_directed(self):
        """
        Ensure that all drivable paths are directed
        """
        visited: Set[Union[Edge, Node]] = set()

        def _make_directed(end: End, forward: bool):
            s = end.node().s
            end = end.other_end()
            curr_node = end.node()
            if end.edge in visited:
                return
            visited.add(end.edge)
            if curr_node not in visited:
                visited.add(curr_node)
                curr_node.s = (s + end.edge.length()) if forward else (s - end.edge.length())

                ends = curr_node.ends()
                if end == ends[0]:
                    for e in ends[1:]:
                        _make_directed(e, forward)
                else:
                    _make_directed(ends[0], forward)
                    for e in ends[1:]:
                        if e != end:
                            _make_directed(e, not forward)
            if (end.side == EdgeEnd.TARGET) ^ forward:
                end.edge.flip()

        for node in self.end_nodes():
            if node in visited:
                continue
            visited.add(node)
            node.s = 0.0
            first_end = node.ends()[0]
            _make_directed(first_end, first_end.side == EdgeEnd.SOURCE)

    def to_json(self):

        def node_to_json(node: Node):
            return {
                'x': node.pose.pos.x,
                'y': node.pose.pos.y,
                'direction': node.pose.direction,
                's': node.s,
                'attrs': node.attrs
            }

        def edge_to_json(edge: Edge):
            return {
                'source': self.nodes.index(edge.source()),
                'target': self.nodes.index(edge.target()),
                'attrs': edge.attrs,
                'segments': [{
                    'length': seg.length,
                    'radius': seg.radius,
                    'attrs': seg.attrs
                } for seg in edge.segments],
                'scenery_objects': [obj_to_json(obj, edge) for obj in edge.scenery_objects]
            }

        def obj_to_json(obj: SceneryObject, parent=None):
            assert obj.relative_to == parent
            return {
                'x': obj.pose.pos.x,
                'y': obj.pose.pos.y,
                'direction': obj.pose.direction,
                'object_type': obj.object_type,
                'name': obj.name,
                'attrs': obj.attrs,
            }

        return json.dumps({
            'nodes': [node_to_json(node) for node in self.nodes],
            'edges': [edge_to_json(edge) for edge in self.edges],
            'scenery_objects': [obj_to_json(obj) for obj in self.scenery_objects]
        }, indent=2)

    def __repr__(self):
        return str(self.edges)


class Path(List[End]):

    def __init__(self, ends: Iterable[End]=(), start_offset=0.0, end_offset=0.0):
        super().__init__(ends)
        self.start_offset = start_offset
        self.end_offset = end_offset


    def to_global(self, other: Union[Vector, Pose], offset: Optional[float] = 0.0, extend_before=True, extend_after=True):
        """
        Transform from local to global coordinates

        :param other: pose or point to transform
        :param offset: offset along path
        :param extend_before: whether to transform coordinates before path start
        :param extend_after: whether to transform coordinates after path end
        """
        if offset is None:
            offset = self[0].node().s
        offset -= self.start_offset
        for idx, end in enumerate(self):
            flipped = False
            if end.side == EdgeEnd.TARGET:
                end.edge.flip()
                flipped = True
            try:
                transformed = end.edge.to_global(other, offset,
                                                 extend_before,
                                                 extend_after and idx == len(self) - 1)
            finally:
                if flipped:
                    end.edge.flip()
            offset += end.edge.length
            if transformed:
                return transformed

    def to_local(self, other, offset: Optional[float] = 0.0, extend_before=True, extend_after=True):
        """
                Transform from global to local coordinates

                :param other: pose or point to transform
                :param offset: offset along path
                :param extend_before: whether to transform coordinates before path start
                :param extend_after: whether to transform coordinates after path end
                """
        if offset is None:
            offset = self[0].node().s
        offset -= self.start_offset
        for idx, end in enumerate(self):
            flipped = False
            if end.side == EdgeEnd.TARGET:
                end.edge.flip()
                flipped = True
            try:
                transformed = end.edge.to_local(other, offset,
                                                extend_before,
                                                extend_after and idx == len(self) - 1)
            finally:
                if flipped:
                    end.edge.flip()
            offset += end.edge.length()
            if transformed:
                return transformed

    def length(self):
        return sum(end.edge.length() for end in self) - self.start_offset - self.end_offset

    def reverse(self) -> None:
        super().reverse()
        for idx in range(len(self)):
            self[idx] = self[idx].other_end()
        self.start_offset, self.end_offset = (self.end_offset, self.start_offset)

    def copy(self):
        return Path(self, start_offset=self.start_offset, end_offset=self.end_offset)



def find_shortest_path(start: Union[Node, End], end_node: Node):
    """
    Find the shortest path to a node.
    """
    cnt = 0
    heap = []
    predecessors = {}
    current_end: Optional[End] = None
    if isinstance(start, Node):
        start_ends = start.ends()
    else:
        start_ends = [start]
    for end in start_ends:
        heapq.heappush(heap, (end.edge.length(), cnt, end))
        predecessors[end] = None
        cnt += 1
    while heap:
        s, _, current_end = heapq.heappop(heap)
        other_end = current_end.other_end()
        if other_end.node() == end_node:
            break
        for end in other_end.node().connected_ends(other_end):
            if end not in predecessors:
                predecessors[end] = current_end
                heapq.heappush(heap, (s + end.edge.length(), cnt, end))
                cnt += 1
    pth = Path()
    while current_end:
        pth.insert(0, current_end)
        current_end = predecessors[current_end]
    return pth
