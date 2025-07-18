# Depth and Semantic Sensor Emulation

The goal is to provide, beneath RGB camera data, also depth and semantic information. The goal is to enable generation of point clouds and labeled data, based on ground truth. 

## Approach Overview

The heart of the approach is a replacement of the SceneryShader by a custom shader called DepthSensorShader. This custom shader uses color output to store, instead of RGB color values, 
semantical and depth information in the output buffer. The depth and semantical output can be produced by rendering to a texture buffer (instead of screen) using the special shader. 
We choose a 32bit float color format for that buffer, because it has the highes accuracy. We use the color components as follows

* red channel: Object type and object ID (encoded as TypeID / 8 + ObjectID / 2^16)
* green channel: Distance (scaled)
* Intensity estimation (e.g., of a received LiDAR signal)

Note, that all components must be scaled to the range [0, 1]. We assume that the graphics card provides an accuracy of at least 16 bits. 

## Implementation of the Shader

The shader code can be found in DepthSensorShader.fx. Note that it's not possible to merge both shaders into one, because it would exceed the graphic cards capacity (number of instruction slots). 

The shader shares a common interface with the SceneryShader. In particular, it provides the same set of effects, so it can be used as a drop-in replacement in many places.  However, some of the original effect parameters are not needed. The DepthSensorShader uses the following additional parameters:

* ObjectClassifier: Semantical information, written to red color component without modification
* MaxDistance: Range of the depth information; used for scaling the depth information (green color component) and far pane clipping
* BaseIntensity: Scaling factor for intensity estimation (blue color component). Must be in the range [0, 1]
* TrackClipping: Boolean flag to enable special clipping of track textures

The vertex shaders are identical to the SceneryShader vertex shaders. The pixel shader works the same for all declared techniques, except that some don't use clipping.  

* First, alpha clipping is performed in order to avoid transparent texture parts to occure as artifacts. 
Track elements are much wider than the actual gauge. Therefore, if TrackClipping = true, we also clip every thing that is not light gray (precisely: has a color component < 0.7). 
* The depth value is the length of the camera-relative position vector. Everything with a distance > MaxDistance is clipped. 
* The intensity estimation is calculated as the dot product of the (normalized) normal vector and the normalized relative position vector, multiplied with the BaseIntensity. 
* The pixel shader produces an RGBA output value (ObjectClassification, Distance / MaxDistance, Intensity, 1.0)

Note that any output values need to be in the range [0, 1]. We set the alpha channel to 1.0 so we can be sure that the output is not distroyed by alpha blending. 

## Implementation of Shader Use

The DepthSensor itself is modeled in the `DepthSensor` class in `Viewer.cs` (we shall think about a better place in future). It defines a camera projection matrix, maximum range, and data buffers. 
Note that currently the DepthSensor field of view must be covered by the current camera's field of view, because the latter is used for object culling. This may be changed in future. 
Furthermore, the DepthSensor shares the current camera's view point (that may also change). 

Currently, we create one instance of the DepthSensor that is attached to the `Viewer` instance. 

### Modifications in the Rendering Loop

First of all, we introduce a Boolean flag in the material manager that shows whether the special shader is active. This flag can be accessed by `Viewer.MaterialManager.DepthSensorActive`. 
Furthermore, we introduce a corresponding shader class `DepthSensorShader` and a common superclass `AbstractSceneryShader` for both `DepthSensorShader` and `SceneryShader` that declares common effect parameters of both shaders. 

There are also modifications in the rest of the code necessary, especially in the different `Material` subclasses that use the `SceneryShader`. 

In the `RenderFrame.Draw(...)` method, a second pass rendering pass is introduced that sets `Viewer.MaterialManager.DepthSensorActive` temporarily to `true` and then renders to the depth sensor buffer. In this second rendering pass care is taken to not render the cab, sky, labels, and light effects. 

### Implementation of Semantical Labeling

Semantical information about the current object is passed to the DepthSensorShader via the `ObjectClassifier` effect parameter. The object type and ID information is stored in the `RenderPrimitive` objects that make up the scene. 
To avoid passing the information down through a large chain of method calls, we introduce a `NextObject(ObjectClassification)` method in the `RenderFrame` class. This is called every time when construction of a new object is started. 
We have to patch the toplevel `PrepareFrame` methods for that. 

## Transmission via HTTP

The raw sensor data is transmitted to the simulation client via the HTTP interface. Transmiting ground truth data allows maximum flexibility on client-side. It can be used for emulation of a variety of sensors, for example a LiDAR sensor. Due to parallel data processing techniques provided by the numpy Python library, efficient implementations are possible. Although a sensor (e.g. LiDAR) emulation directly in the shader would be more efficient, the cost in data transmission and processing large point clouds in the client will probably outweigh the performance gain. 

In the response to the CABCONTROLS POST request, metadata about the raw depth data is transmitted. This includes the size of the image (height, width), the horizontal (h_scale) and vertical (v_scale) field of view ratios from the projection matrix, and the depth range (max_distance). 

To avoid a costly encoding of the raw data to JSON, the raw data is not part of the POST response, but can be received via a sepatrate GET request. The data is transferred line-wise as a sequence of unsigned 16bit numbers. So, each point is a sequence of three 16bit values being (in order)

* The object class (in the most significant 3 bits) and the object ID (remaining bits)
* The distance to the sensor, scaled to the range $[0, 2^{16}-1]$ 
* The raw intensity, scaled to the range $[0, 2^{16}-1]$. 

The byte ordering is LSB. 

## Debugging

For debugging, the shader has a DEBUG macro. It can be used to only render depth or semantic information. Instead of using the color channels independently, either depth or semantic information is output as an RGB value using a heatmap color coding. When initializing `Viewer.MaterialManager.DepthSensorActive` with `true` (instead of `false`, the default), the DepthSensorShader output is rendered to screen. 

Note that the shaders are not automatically compiled. The project needs to be re-build manually when changing shader code. 

## Current Limitations

* Object culling is based on the current camera, so we can create depth and semantical information only from the same point of view; the sensor field of view cannot exceed the camera field of view.
* The sensor uses a perspective projection, so the depth/semantical value at horizontal/vertical angle `alpha` has x/y position `a * tan(alpha) + b`, where a and b depend on image size and field of view angle. The field of view is limited; especially, it is always less than 180°. 
* The semantical information about object classes that is avaliable is limited. So far, we can only distinguish between trains, dynamic tracks, signals, terrain, moving objects, and static scenery objects. 
* Passing the sensor data to the client is a true bottleneck. 

 # Implementation of the LiDAR emulation

The Python client contains a LiDAR emulation based on the transmitted raw data. 

It is assumed that, in each frame, the LiDAR creates a point cloud from a series of laser shots (all occuring in the same simulation frame). For each shot, $\alpha$ is the yaw-angle of the laser, and $\beta$ the pitch angle. The shots are equaly spaced with respect to both the yaw and the pitch angle, and created for the full field of view. 

## Examining Raw Data

The rendering pipeline uses a perspective transformation matrix of the form

$$ P = \begin{bmatrix} 
a & 0 & 0 & 0 \\
0 & b & 0 & 0 \\
0 & 0 & -c & -1 \\
0 & 0 & -c & 0 
\end{bmatrix} $$

A point $p = (x, y, z)$ in view coordinates ($x$ pointing right, $y$ right, and $z$ towards the viewer) is transformed to screen coordinates $(x', y', z')$ by calculating 
$$ [x''~y''~z''~w] = [x~y~z~1]\cdot P $$
and defining 
$$ x' = x''/w, y' = y''/w, z' = z''/w $$
The $z'$ coordinate goes into the depth buffer and is ignored for our calculation. 
A point hit by a laser at distance $d$ has a position 
$$ \mathbf{p} = d\mathbf{f} $$ 
with
$$ \mathbf{f} = [\sin\alpha\cos\beta\quad\sin\beta\quad-\cos\alpha\cos\beta] $$
By the projection matrix above, it is $w = -z$. This eliminates the distance $d$ from the screen coordinate which only depends now on $\alpha$ and $\beta$:
$$ x' = a\tan\alpha $$ 
$$ y'=\frac{b\tan\beta}{\cos\alpha} $$ 

The $(x', y')$ is uniformly mapped to column and line indexes of the render target buffer that is a raster image with height $h$ and width $w$. Thereby, $(-1-1)$ is mapped to the bottom left, and $(1,1)$ to the top right corner. So, the column is 
$$ s = \frac{1+x'}{2}w $$
and the row is 
$$ t = \frac{1-y'}{2}h $$
each rounded to the closest integer. Points outside the image bounds are dropped. The image is indexed row-wise, so the index of the point in the raw data stream is $s + tw$. At this index we find the object type and ID, distance $d$ (after scaling back to the sensor range), and the base intensity $I_0$.

## Intensity and Dropoff

We adopt the intensity estimation and randomized intensity-based dropoff that is also implemented in the CARLA LiDAR sensor model. 

### Intensity

The intensity reduces exponentially with the distance from the sensor, based on the atmosphere attenuation rate $a$, which is implemented as a sensor parameter. The effective intensity of a point with distance $d$ is then
$$ I = I_0 \cdot e^{-a\cdot d} $$
where $I_0$ is the base intensity reported by the simulation server in that point. Note that, in contrast to CARLA, we take reflectance into account. As described in one of the sections above, the base intensity is  
$$ I_0 = I_M \frac{|\mathbf{n}\cdot\mathbf{p}^T|}{|\mathbf{n}|\cdot|\mathbf{p}|} $$
where $I_M$ is a material-dependent reflectance factor (that is currently always $1$), $\mathbf{n}$ the normal vector of the hidden surface with respect to the viewer, and $\mathbf{p}$ the relative position.  

### Dropoff

Points are dropped with a probability $P$ that depends on the intensity $I$ and the following sensor parameters:

* a base dropoff probability $P_0$
* a probability $P_{I=0}$ that a point with intensity $I=0$ is dropped
* an intensity limit $I_{P=0}$ above that no intensity-based dropoff occurs. 

If $I \geq I_{P=0}$, then no intensity-based dropoff occurs and the point is dropped with a probability $P=P_0$. The same holds if $P_{I=0} = 0$ or $I_{P=0} \leq 0$ which deactivates intensity-based dropoff. 
Otherwise, the probability for intensity-based dropoff is 
$$ P_I = \left(1-\frac{I}{I_{P=0}}\right)P_{I=0} $$ 
and the overall probability that the point is dropped is 
$$ P = P_0 + P_I - P_0P_I $$

