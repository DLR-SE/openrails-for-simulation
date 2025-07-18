import math
from typing import Union

"""
Helpers for geometry in the 2D plane
"""


class Vector:
    """
    A 2D vector
    """
    def __init__(self, x=0.0, y=0.0):
        self.x = x
        self.y = y

    def __hash__(self):
        return hash(self.x + self.y)

    def __eq__(self, other):
        return isinstance(other, Vector) and self.x == other.x and self.y == other.y

    def __str__(self):
        return f'({self.x}, {self.y})'

    def __repr__(self):
        return f'({self.x}, {self.y})'

    def __sub__(self, other):
        return Vector(self.x - other.x, self.y - other.y)

    def __add__(self, other):
        return Vector(self.x + other.x, self.y + other.y)

    def __mul__(self, other):
        """
        Dot product or scale
        :param other:
        :return:
        """
        if isinstance(other, Vector):
            return self.x * other.x + self.y * other.y
        else:
            return Vector(self.x * other, self.y * other)

    def __rmul__(self, other):
        """
        Dot product or scale
        :param other:
        :return:
        """
        return self.__mul__(other)

    def __truediv__(self, other):
        """
        Inverse scale

        :param other:
        :return:
        """
        return Vector(self.x / other, self.y / other)

    def __abs__(self):
        """
        Vector length
        :return:
        """
        return math.sqrt(self.x**2 + self.y**2)

    def alpha(self):
        """
        Direction of the vector, counter-clockwise from X axis in radians
        :return:
        """
        return math.atan2(self.y, self.x)

    def ortho(self):
        """
        Orthogonal vector, i.e. (-Y, X)
        :return: the orthogonal vector
        """
        return Vector(-self.y, self.x)

    def norm(self):
        """
        Normalized vector, i.e. same direction but length 1.0
        :return: the normalized vector
        """
        length = abs(self)
        return Vector(self.x / length, self.y / length)

    def __neg__(self):
        return Vector(-self.x, -self.y)

    def __matmul__(self, other):
        """
        Up-vector of vector cross product
        :param other: other vector
        :return: Z component of cross product
        """
        return self.x * other.y - self.y * other.x

    def copy(self):
        return Vector(self.x, self.y)




def polar(alpha, length=1.0):
    """
    Create a vector with certain direction and length
    :param alpha: direction
    :param length: length
    :return:
    """
    return Vector(math.cos(alpha) * length, math.sin(alpha) * length)


class Pose:
    """
    A pose combines a position with a direction
    """
    def __init__(self, pos: Vector, direction=0.0):
        self.pos = pos
        self.direction = direction % (2*math.pi)

    def reverse(self):
        """
        Same position, but reverse direction (i.e., turn by 180°)
        :return: the reverse position
        """
        return Pose(self.pos, self.direction + math.pi)

    def copy(self):
        return Pose(self.pos.copy(), self.direction)

    def __copy__(self):
        return self.copy()

    def to_global(self, other: Union['Pose', Vector]):
        """
        Translate a point (or pose) from the local coordinate system spanned by this pose
        to the global coordinate system
        """
        if isinstance(other, Pose):
            p = other.pos
        else:
            p = other
        vx = polar(self.direction)
        vy = vx.ortho()
        p = self.pos + p.x * vx + p.y * vy
        if isinstance(other, Pose):
            return Pose(p, self.direction + other.direction)
        else:
            return p

    def to_local(self, other: Union['Pose', Vector]):
        """
        Translate a point (or pose) from the global coordinate system
        to the local coordinate system spanned by this pose
        """
        if isinstance(other, Pose):
            p = other.pos
        else:
            p = other
        vx = polar(self.direction)
        vy = vx.ortho()
        p = p - self.pos
        p = Vector(p * vx, p * vy)
        if isinstance(other, Pose):
            return Pose(p, other.direction - self.direction)
        else:
            return p

    def __str__(self):
        return f'({self.pos}, {self.direction})'

    def __repr__(self):
        return f'({self.pos}, {self.direction})'


def angle_between(alpha, beta):
    """
    Utility for the angle between two directions (angle difference beta - alpha), in the range [-pi, pi]
    :param alpha:
    :param beta:
    :return:
    """
    if isinstance(alpha, Pose):
        alpha = alpha.direction
    elif isinstance(alpha, Vector):
        alpha = alpha.alpha()
    if isinstance(beta, Pose):
        beta = beta.direction
    elif isinstance(beta, Vector):
        beta = beta.alpha()
    return (beta - alpha + math.pi) % (2*math.pi) - math.pi


def biarc_interpolation(p1: Vector, t1: Vector, p2: Vector, t2: Vector):
    """
    bi-arc interpolation between two points. Produces

    - r1: radius of first arc
    - theta1: angle of first arc (measured counter-clockwise from p1)
    - r2: radius of second arc
    - theta2: angle of second arc (measured counter-clockwise from p2)

    See https://www.ryanjuckett.com/biarc-interpolation/

    :param p1: first (start) point
    :param t1: tangent in first point (facing along the bi-arc)
    :param p2: second (end) point
    :param t2: tangent in second point (facing away from the bi-arc)
    :return: tuple (r1, theta1, r2, theta2)
    """
    v = p2 - p1
    t = t1 + t2
    vt = v * t
    denominator = 2 * (1 - t1 * t2)
    if denominator == 0.0:
        print('parallel')
        if vt == 0.0:
            c1 = p1 + 0.25*v
            c2 = p1 + 0.75*v
            theta1, theta2 = (math.pi, -math.pi) if v @ t2 < 0 else (-math.pi, math.pi)
            return c1, theta1, c2, theta2
        d = 0.5 * (v * v) / vt
    else:
        d = (-vt + math.sqrt(vt ** 2 + 2 * (1 - t1 * t2) * (v * v))) / denominator

    pm = 0.5 * (p1 + p2 + d * (t1 - t2))

    def calculate_arc(p, t_):
        n = t_.ortho()
        s = ((pm - p) * (pm - p)) / (2 * (n * (pm - p)))
        c = p + s*n
        r = abs(s)
        op = (p - c) / r
        om = (pm - c) / r

        theta = math.acos(op * om)
        if d <= 0:
            theta -= 2*math.pi
        if op @ om <= 0:
            theta = -theta
        return r, theta

    r1, theta1 = calculate_arc(p1, t1)
    r2, theta2 = calculate_arc(p2, t2)
    return r1, theta1, r2, theta2



