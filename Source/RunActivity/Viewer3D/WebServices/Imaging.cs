using System.Drawing;
using System.IO;
using System.Windows.Forms;
using System.Drawing.Imaging;
using Microsoft.Xna.Framework.Graphics;

namespace Orts.Viewer3D.WebServices
{
    class Imaging
    {
        public static Bitmap CaptureScreen(Viewer Viewer, int width, int height)
        {
            // Create a bitmap to hold the screenshot
            var screenshot = new Bitmap(Screen.PrimaryScreen.Bounds.Width, Screen.PrimaryScreen.Bounds.Height);

            // Create a graphics object from the bitmap
            using (var graphics = Graphics.FromImage(screenshot))
            {
                // Capture the screen into the bitmap
                graphics.CopyFromScreen(Point.Empty, Point.Empty, Screen.PrimaryScreen.Bounds.Size);
            }

            var resizedScreenshot = new Bitmap(width, height);

            // Create a graphics object from the reduced-resolution bitmap
            using (var graphics = Graphics.FromImage(resizedScreenshot))
            {
                // Resize the original screenshot to fit the reduced-resolution bitmap
                graphics.DrawImage(screenshot, new Rectangle(0, 0, width, height));
            }

            // Dispose of the original Bitmap object
            screenshot.Dispose();

            return resizedScreenshot;
        }

        public static byte[] CaptureScreenXNA(Viewer Viewer)
        {

            int w = Viewer.GraphicsDevice.PresentationParameters.BackBufferWidth;
            int h = Viewer.GraphicsDevice.PresentationParameters.BackBufferHeight;

            //pull the picture from the buffer 
            int[] backBuffer = new int[w * h];
            Viewer.GraphicsDevice.GetBackBufferData(backBuffer);

            //copy into a texture 
            Texture2D texture = new Texture2D(Viewer.GraphicsDevice, w, h, false, Viewer.GraphicsDevice.PresentationParameters.BackBufferFormat);
            texture.SetData(backBuffer);

            //save to disk 
            using (var memoryStream = new MemoryStream())
            {
                // Save the bitmap to the memory stream using PNG compression
                texture.SaveAsJpeg(memoryStream, w, h);


                // Return the compressed data
                texture.Dispose();
                return memoryStream.ToArray();
            }
        }

        public static byte[] GetSerializedJpeg(Bitmap bitmap)
        {
            using (var memoryStream = new MemoryStream())
            {
                // Save the bitmap to the memory stream using PNG compression
                bitmap.Save(memoryStream, ImageFormat.Jpeg);

                // Return the compressed data
                return memoryStream.ToArray();
            }
        }

    }
}
