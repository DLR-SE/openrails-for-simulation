// COPYRIGHT 2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017 by the Open Rails project.
//
// This file is part of Open Rails.
//
// Open Rails is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// Open Rails is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with Open Rails.  If not, see <http://www.gnu.org/licenses/>.

// This file is the responsibility of the 3D & Environment Team.

using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Orts.Viewer3D;
using ORTS.Common;

/// <summary>
/// Data from a sensor that is used by a <see cref="RenderFrame"/> instance for rendering. 
/// We have to store this separately because the sensor sate may be modified in parallel on the Update thread 
/// </summary>
public class CameraSensorRenderFrameData
{
    public Vector3 CameraLocation;
    public Matrix XNACameraView;
    public Matrix XNACameraProjection;

    public RenderTarget2D RenderTarget;
}
public abstract class CameraSensor
{
    /// <summary>
    /// Buffer for image data to be exposed via the web interface
    /// </summary>
    public byte[] EncodedRawData { get; internal set; }
    public int ImageWidth;
    public int ImageHeight;
    
    internal SurfaceFormat SurfaceFormat;

    public Camera Camera { get; internal set; }

    /// <summary>
    /// The sensor that is currently rendered. We use a static variable, so it is accessible from everywhere with minimal code modifications
    /// </summary>
    public static CameraSensor CurrentSensor;

    /// <summary>
    /// The groups of render primitives that shall be rendered for this sensor. 
    /// </summary>
    public uint RenderPrimitiveGroups;
    public readonly string Name;

    /// <summary>
    /// 
    /// </summary>
    /// <param name="name">Name of the sensor</param>
    /// <param name="imageWidth">Width of the camra image. Shall be a multiple of 32, otherwise performance drops rapidly</param>
    /// <param name="imageHeight">Height of the camera image</param>
    /// <param name="camera">The camera to record from</param>
    /// <param name="surfaceFormat">The surface format to use</param>
    public CameraSensor(string name, int imageWidth, int imageHeight, Camera camera, SurfaceFormat surfaceFormat)
    {
        ImageWidth = imageWidth;
        ImageHeight = imageHeight;
        SurfaceFormat = surfaceFormat;
        Camera = camera;
        RenderPrimitiveGroups = (1 << (int)RenderPrimitiveSequence.WorldOpaque) |
            (1 << (int)RenderPrimitiveSequence.WorldBlended);
        Name = name;
    }

    /// <summary>
    /// Update the camera. May be overridden to update also other sensor status
    /// </summary>
    /// <param name="elapsedTime"></param>
    public virtual void Update(ElapsedTime elapsedTime)
    {
        Camera.Update(elapsedTime);
    }

    public virtual void Initialize()
    {
        Camera.Activate(false, (float)ImageWidth / (float)ImageHeight);
    }

    /// <summary>
    /// Called by the updater to prepare the next frame for rendering
    /// </summary>
    /// <param name="frame">The render frame to be filled</param>
    /// <param name="elapsedTime">The time elapsed since last rendering call</param>
    public virtual void PrepareFrame(RenderFrame frame, ElapsedTime elapsedTime)
    {
        Camera.PrepareFrame(frame, elapsedTime, false);
        if (!frame.SensorData.ContainsKey(this)) 
        {
            frame.SensorData[this] = new CameraSensorRenderFrameData();
        }
        frame.SensorData[this].CameraLocation = Camera.Location;
        frame.SensorData[this].XNACameraView = Camera.XnaView;
        frame.SensorData[this].XNACameraProjection = Camera.XnaProjection;
    }
    /// <summary>
    /// Transfer the data from the render frame to the internal buffer, so it can be picked up later by the web interface
    /// </summary>
    /// <param name="frame"></param>
    public void StoreData(RenderFrame frame)
    {
        if (!frame.SensorData.ContainsKey(this))
        {
            return;
        }
        var renderTarget = frame.SensorData[this].RenderTarget;
        if (renderTarget != null)
        {
            StoreData(renderTarget);
        }
    }

    /// <summary>
    /// Extract the data from the GPU and store it into the <see cref="EncodedRawData"/> buffer
    /// </summary>
    /// <param name="renderTarget">this holds the data</param>
    protected abstract void StoreData(RenderTarget2D renderTarget);

    public RenderTarget2D CreateRenderTarget(GraphicsDevice graphicsDevice)
    {
        return new RenderTarget2D(
            graphicsDevice,
            ImageWidth,
            ImageHeight,
            false,
            SurfaceFormat,
            graphicsDevice.PresentationParameters.DepthStencilFormat,
            1,
            RenderTargetUsage.PreserveContents
        );
    }

    public static void ConfigureShader(AbstractSceneryShader shader, RenderItem renderItem, SceneryMaterialOptions options = SceneryMaterialOptions.None)
    {
        if (CurrentSensor != null && shader is DepthSensorShader)
        {
            CurrentSensor.DoConfigureShader(shader as DepthSensorShader, renderItem, options);
        }
    }

    public virtual void DoConfigureShader(DepthSensorShader shader, RenderItem item, SceneryMaterialOptions options)
    {
        
    }

}
/// <summary>
/// A camera-based sensor that renders depth and object ID/class information
/// </summary>
public class DepthSensor: CameraSensor
{
    
    public float MaxDistance;

    float[] RawImageData;

    
    public DepthSensor(string name, Camera camera, int imgHeight = 600, int imgWidth = 800, float maxDistance = 400.0f)
        : base(name, imgHeight, imgWidth, camera, SurfaceFormat.Vector4)
    {
        MaxDistance = maxDistance;  

        EncodedRawData = new byte[6 * ImageWidth * ImageHeight];
        RawImageData = new float[4 * ImageWidth * ImageHeight];
    }


    protected override void StoreData(RenderTarget2D renderTarget)
    {
        renderTarget.GetData(RawImageData);
        for (int i = 0; i < ImageWidth * ImageHeight; i++)
        {
            var bits = (int)(RawImageData[4 * i] * (1 << 16));
            EncodedRawData[6 * i + 0] = (byte)(bits & 0xFF);
            EncodedRawData[6 * i + 1] = (byte)((bits >> 8) & 0xFF);
            bits = (int)(RawImageData[4 * i + 1] * ((1 << 16) - 1));
            EncodedRawData[6 * i + 2] = (byte)(bits & 0xFF);
            EncodedRawData[6 * i + 3] = (byte)((bits >> 8) & 0xFF);
            bits = (int)(RawImageData[4 * i + 2] * ((1 << 16) - 1));
            EncodedRawData[6 * i + 4] = (byte)(bits & 0xFF);
            EncodedRawData[6 * i + 5] = (byte)((bits >> 8) & 0xFF);
        }
    }

    public override void DoConfigureShader(DepthSensorShader shader, RenderItem item, SceneryMaterialOptions options)
    {
        if (shader != null)
        {
            shader.BaseIntensity = 1.0f;
            float factor = 1.0f / (1 << 16);
            int bits = (int)item.ObjectClassifier << 13 | item.ObjectIndex & 0x1FFF;
            shader.ObjectClassifier = bits * factor;
            shader.TrackClipping =
                item.ObjectClassifier == ObjectClass.Track && (options & SceneryMaterialOptions.AlphaBlendingBlend) != 0;
        }
    }

}

/// <summary>
/// A camera sensor that provides RGB image data
/// </summary>
public class RGBCameraSensor: CameraSensor
{
    byte[] RawImageData;

    public RGBCameraSensor(string name, Camera camera, int imgHeight = 600, int imgWidth = 800)
        : base(name, imgWidth, imgHeight, camera, SurfaceFormat.Color)
    {
        
        EncodedRawData = new byte[3 * ImageWidth * ImageHeight];
        RawImageData = new byte[4 * ImageWidth * ImageHeight];
    }

    protected override void StoreData(RenderTarget2D renderTarget)
    {
        renderTarget.GetData(RawImageData);
        for (int i = 0; i < ImageWidth * ImageHeight; i++)
        {
            EncodedRawData[3 * i] = RawImageData[4 * i];
            EncodedRawData[3 * i + 1] = RawImageData[4 * i + 1];
            EncodedRawData[3 * i + 2] = RawImageData[4 * i + 2];
        }
    }
}
