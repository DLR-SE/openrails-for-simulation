// COPYRIGHT 2020 by the Open Rails project.
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
//
// ===========================================================================================
//      Open Rails Web Server
//      Based on an idea by Dan Reynolds (HighAspect) - 2017-12-21
// ===========================================================================================

using EmbedIO;
using EmbedIO.Routing;
using EmbedIO.WebApi;
using Microsoft.Xna.Framework;
using Newtonsoft.Json;
using Newtonsoft.Json.Serialization;
using Orts.Common;
using Orts.Formats.Msts;
using Orts.Simulation.Physics;
using Orts.Simulation.RollingStocks;
using Orts.Viewer3D.Processes;
using Orts.Viewer3D.RollingStock;
using ORTS.Common;
using ORTS.Settings;
using System;
using System.Collections.Generic;
using System.Drawing.Printing;
using System.Linq;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using static Orts.Common.InfoApiMap;

namespace Orts.Viewer3D.WebServices
{
    /// <summary>
    /// A static class that contains server creation and helper methods for the
    /// Open Rails web server.
    /// </summary>
    public static class WebServer
    {
        /// <summary>
        /// Create a web server with a single listening address.
        /// </summary>
        /// <param name="url">The URL prefix to listen on.</param>
        /// <param name="path">The root directory to serve static files from.</param>
        /// <returns>The EmbedIO web server instance.</returns>
        public static EmbedIO.WebServer CreateWebServer(string url, string path) => CreateWebServer(new string[] { url }, path);

        /// <summary>
        /// Create a web server with multiple listening addresses.
        /// </summary>
        /// <param name="urls">A list of URL prefixes to listen on.</param>
        /// <param name="path">The root directory to serve static files from.</param>
        /// <returns>The EmbedIO web server instance.</returns>
        public static EmbedIO.WebServer CreateWebServer(IEnumerable<string> urls, string path)
        {
            // Viewer is not yet initialized in the GameState object - wait until it is 
            // When in synchronized mode, do not wait because the Viewer will be ready when needed
            if (!SyncSimulation.isSyncSimulation)
            {
                while (Program.Viewer == null)
                {
                    System.Diagnostics.Debug.WriteLine("waiting for viewer");
                    Thread.Sleep(1000);
                }
            }

            return new EmbedIO.WebServer(o => o
                    .WithUrlPrefixes(urls))
                .WithWebApi("/API", SerializationCallback, m => m
                    .WithController(() => new ORTSApiController(Program.Viewer)))
                .WithStaticFolder("/", path, true);
        }

        /// <remarks>
        /// The Swan serializer used by EmbedIO does not serialize custom classes,
        /// so this callback replaces it with the Newtonsoft serializer.
        /// </remarks>
        private static async Task SerializationCallback(IHttpContext context, object data)
        {
            if (data is byte[])
            {
                using (var stream = context.OpenResponseStream(true, false))
                {
                    await stream.WriteAsync((byte[])data, 0, ((byte[])data).Length); // ((byte[])data).Length);
                }
            }
            else
            {
                using (var text = context.OpenResponseText(new UTF8Encoding(false)))
                {
                await text.WriteAsync(JsonConvert.SerializeObject(data, new JsonSerializerSettings()
                {
                    Formatting = Formatting.Indented,
                    ContractResolver = new XnaFriendlyResolver()
                }));
            }
        }
        }
        
        public static async Task<T> DeserializationCallback<T>(IHttpContext context)
        {
            using (var text = context.OpenRequestText())
            {
                return JsonConvert.DeserializeObject<T>(await text.ReadToEndAsync());
            }
        }

        /// <summary>
        /// This contract resolver fixes JSON serialization for certain XNA classes.
        /// </summary>
        /// <remarks>
        /// Many thanks to <a href="https://stackoverflow.com/a/44238343">Elliott Darfink of Stack Overflow</a>.
        /// </remarks>
        private class XnaFriendlyResolver : DefaultContractResolver
        {
            protected override JsonContract CreateContract(Type objectType)
            {
                if (objectType == typeof(Rectangle) || objectType == typeof(Point))
                    return CreateObjectContract(objectType);
                return base.CreateContract(objectType);
            }
        }
    }

    /// <summary>
    /// An API controller that serves Open Rails data from an attached Viewer.
    /// </summary>
    internal class ORTSApiController : WebApiController
    {
        /// <summary>
        /// The Viewer to serve train data from.
        /// </summary>
        private readonly Viewer Viewer;
        protected WorldLocation cameraLocation = new WorldLocation();
        private OutputGenerator OutputGenerator;
        private SwitchController SwitchController;

        public ORTSApiController(Viewer viewer)
        {
            Viewer = viewer;
            OutputGenerator = new OutputGenerator(Viewer);
            SwitchController = new SwitchController(Viewer.Simulator);
        }

        #region /API/READY
        [Route(HttpVerbs.Get, "/READY")]
        public void ReadyEndpoint()
        {
            System.Diagnostics.Debug.WriteLine("ready endpoint: " + (Program.Viewer != null));
            if (Program.Viewer != null)
            {
                HttpContext.Response.StatusCode = 200;
            }
            else
            {
                HttpContext.Response.StatusCode = 425;
            }
            
            HttpContext.SendDataAsync("");

        }
        #endregion

        #region /API/APISAMPLE
        public struct Embedded
        {
            public string Str;
            public int Numb;
        }
        public struct ApiSampleData
        {
            public int intData;
            public string strData;
            public DateTime dateData;
            public Embedded embedded;
            public string[] strArrayData;
        }

        // Call from JavaScript is case-sensitive, with /API prefix, e.g:
        //   hr.open("GET", "/API/APISAMPLE", true);
        [Route(HttpVerbs.Get, "/APISAMPLE")]
        public ApiSampleData ApiSample() => new ApiSampleData()
        {
            intData = 576,
            strData = "Sample String",
            dateData = new DateTime(2018, 1, 1),
            embedded = new Embedded()
            {
                Str = "Embedded String",
                Numb = 123
            },
            strArrayData = new string[5]
            {
                "First member",
                "Second member",
                "Third member",
                "Fourth member",
                "Fifth member"
            }
        };
        #endregion


        #region /API/HUD
        public struct HudApiTable
        {
            public int nRows;
            public int nCols;
            public string[] values;
        }

        public struct HudApiArray
        {
            public int nTables;
            public HudApiTable commonTable;
            public HudApiTable extraTable;
        }

        [Route(HttpVerbs.Get, "/HUD/{pageNo}")]
        // Example URL where pageNo = 3:
        //   "http://localhost:2150/API/HUD/3" returns data in JSON
        // Call from JavaScript is case-sensitive, with /API prefix, e.g:
        //   hr.open("GET", "/API/HUD" + pageNo, true);
        // The name of this method is not significant.
        public HudApiArray ApiHUD(int pageNo)
        {
            var hudApiArray = new HudApiArray()
            {
                nTables = 1,
                commonTable = ApiHUD_ProcessTable(0)
            };

            if (pageNo > 0)
            {
                hudApiArray.nTables = 2;
                hudApiArray.extraTable = ApiHUD_ProcessTable(pageNo);
            }
            return hudApiArray;
        }

        private HudApiTable ApiHUD_ProcessTable(int pageNo)
        {
            Popups.HUDWindow.TableData hudTable = Viewer.HUDWindow.PrepareTable(pageNo);
            int nRows = hudTable.Cells.GetLength(0);
            int nCols = hudTable.Cells.GetLength(1);
            IEnumerable<string> GetValues()
            {
                foreach (int r in Enumerable.Range(0, nRows))
                    foreach (int c in Enumerable.Range(0, nCols))
                        yield return hudTable.Cells[r, c];
            }
            return new HudApiTable()
            {
                nRows = nRows,
                nCols = nCols,
                values = GetValues().ToArray()
            };
        }
        #endregion


        #region /API/TRACKMONITORDISPLAY
        [Route(HttpVerbs.Get, "/TRACKMONITORDISPLAY")]
        public IEnumerable<TrackMonitorDisplay.ListLabel> TrackMonitorDisplayList() => Viewer.TrackMonitorDisplayList();
        #endregion


        #region /API/TRAININFO
        [Route(HttpVerbs.Get, "/TRAININFO")]
        public TrainInfo TrainInfo() => Viewer.GetWebTrainInfo();
        #endregion


        #region /API/TRAINDRIVINGDISPLAY
        [Route(HttpVerbs.Get, "/TRAINDRIVINGDISPLAY")]
        public IEnumerable<TrainDrivingDisplay.ListLabel> TrainDrivingDisplay([QueryField] bool normalText) => Viewer.TrainDrivingDisplayList(normalText);
        #endregion

        #region /API/TRAINDPUDISPLAY
        [Route(HttpVerbs.Get, "/TRAINDPUDISPLAY")]
        public IEnumerable<TrainDpuDisplay.ListLabel> TrainDpuDisplay([QueryField] bool normalText) => Viewer.TrainDpuDisplayList(normalText);
        #endregion

        #region /API/CABCONTROLS
        // Note: to see the JSON, use "localhost:2150/API/CABCONTROLS" - Beware: case matters
        // Note: to run the webpage, use "localhost:2150/CabControls/index.html" - case doesn't matter
        // or use "localhost:2150/CabControls/"
        // Do not use "localhost:2150/CabControls/"
        // as that will return the webpage, but the path will be "/" not "/CabControls/ and the appropriate scripts will not be loaded.

        [Route(HttpVerbs.Get, "/CABCONTROLS")]
        public IEnumerable<ControlValue> CabControls() => ((MSTSLocomotiveViewer)Viewer.PlayerLocomotiveViewer).GetWebControlValueList();
        #endregion

        #region /API/CABCONTROLS
        // SetCabControls() expects a request passing an array of ControlValuePost objects using JSON.
        // For example:
        // [{ "TypeName": "THROTTLE"    // A CABViewControlTypes name - must be uppercase.
        //  , "ControlIndex": 1         // Index of control type in CVF (optional for most controls)
        //  , "Value": 0.50             // A floating-point value
        //  }
        // ]

        [Route(HttpVerbs.Post, "/CABCONTROLS")]
        public async Task<Dictionary<string, object>> SetCabControls()
        {
            if (SyncSimulation.isSyncSimulation)
            {
            await SyncSimulation.inputSemaphore.WaitAsync();
            }

            var data = await HttpContext.GetRequestDataAsync<CabControlsPost>(WebServer.DeserializationCallback<CabControlsPost>);
            Console.WriteLine("Data Received:");
            Console.WriteLine(data.ToString());
            //TODO the Input given through this WebDeviceState is handled by the MSTSLocomotiveViewer:236 HandleUserInput(), which is usually attached to the player locomotive 
            // (and therefore only executes commands for that locomotive). 
            // Either add code to the MSTSLocomotiveViewer so it also sets the values for other trains (messy) 
            // Or provide a more uncoupled structure that separates input and viewer. 

            var dev = UserInput.WebDeviceState;
            foreach (var control in data.Controls)
            {
                MSTSLocomotive locomotive = null;

                if (control.LocomotiveName != null) {
                    locomotive = Viewer.Simulator.NameDictionary[control.LocomotiveName].LeadLocomotive as MSTSLocomotive;
                }
                var locoName = locomotive.Train.Name;

                var key = (new CabViewControlType(control.TypeName), control.ControlIndex, locoName);


                if (!dev.CabControls.TryGetValue(key, out var state))
                {
                    state = new ExternalDeviceCabControl();
                    state.Locomotive = locomotive;
                    var controls = new Dictionary<(CabViewControlType, int, string), ExternalDeviceCabControl>(dev.CabControls);
                    controls[key] = state;
                    dev.CabControls = controls;
                }
                state.Value = (float)control.Value;
            }
            var commands = new List<WorldCommand>();
            foreach (var command in data.Commands)
            {
                commands.Add(WorldCommand.Constructors[command["Command"] as string](command));
            }
            dev.WorldCommands = commands;

            SwitchController.UpdateSwitches(data.SwitchCommands);

            if (SyncSimulation.isSyncSimulation)
            {
                SyncSimulation.simulationSemaphore.Release();
                await SyncSimulation.outputSemaphore.WaitAsync();
            }


            //TODO build output data structure to return
            //await HttpContext.SendDataAsync(((MSTSLocomotiveViewer)Viewer.PlayerLocomotiveViewer).GetWebControlValueList());
            var output = OutputGenerator.CreateOutput();

            if (SyncSimulation.isSyncSimulation)
            {
                SyncSimulation.inputSemaphore.Release();
            }
            return output;
        }
        #endregion

        #region /API/CAMERASENSOR
        // SetCabControls() expects a request passing an array of ControlValuePost objects using JSON.
        // For example:
        // [{ "TypeName": "THROTTLE"    // A CABViewControlTypes name - must be uppercase.
        //  , "ControlIndex": 1         // Index of control type in CVF (optional for most controls)
        //  , "Value": 0.50             // A floating-point value
        //  }
        // ]

        [Route(HttpVerbs.Get, "/CAMERASENSOR/{name}")]
        public byte[] GetCameraSensorData(string name)
        {
            foreach (var sensor in Viewer.CameraSensors)
            {
                if (sensor.Name.Equals(name)) {
                    return sensor.EncodedRawData;
                }
            }
            throw HttpException.NotFound($"No camera sensor named {name} found");

        }
        #endregion

        #region /API/TIME
        [Route(HttpVerbs.Get, "/TIME")]
        public double Time() => Viewer.Simulator.ClockTime;
        #endregion

        #region /API/MAP/INIT
        [Route(HttpVerbs.Get, "/MAP/INIT")]
        public InfoApiMap InfoApiMap() => GetApiMapInfo(Viewer);
        #endregion

        public static InfoApiMap GetApiMapInfo(Viewer viewer)
        {
            InfoApiMap infoApiMap = new InfoApiMap(
                viewer.PlayerLocomotive.PowerSupply.GetType().Name);

            viewer.Simulator.TDB.TrackDB.AddTrNodesToPointsOnApiMap(infoApiMap);

            viewer.Simulator.TDB.TrackDB.AddTrItemsToPointsOnApiMap(infoApiMap);

            return infoApiMap;
        }

        #region /API/MAP
        [Route(HttpVerbs.Get, "/MAP")]
        public LatLonDirection LatLonDirection() => Viewer.Simulator.PlayerLocomotive.GetLatLonDirection();
        #endregion
    }

    struct CabControlsPost
    {
        public IEnumerable<ControlValuePost> Controls;
        public IEnumerable<IDictionary<string, object>> Commands;
        public IDictionary<uint, int> SwitchCommands;
    }
}
