using System.Collections.Generic;
using Microsoft.Xna.Framework;
using System.IO;
using Microsoft.Xna.Framework.Graphics;
using ORTS.Common;
using static Orts.Viewer3D.WebServices.Imaging;
using ORTS.Scripting.Api;

namespace Orts.Viewer3D.WebServices
{
    class OutputGenerator
    {
        private Viewer Viewer;
        
        public OutputGenerator(Viewer viewer)
        {
            Viewer = viewer;
        }

        public Dictionary<string, object> CreateOutput()
        {
            var trainDict = new Dictionary<string, object>();
            var trains = Viewer.Simulator.Trains;
            foreach (var train in trains) {

                trainDict[train.Name] = new Dictionary<string, object>() 
                {
                    {"location", GetLocationCoordinates(train)},
                    {"trackLocation",  GetTrackLocation(train)},
                    {"rearTrackLocation", GetRearTrackLocation(train) },
                    {"rotation", train.FrontTDBTraveller.Rotation.Y},
                    {"locomotiveState",  GetLocomotiveState(train)},
                    {"trainLength", GetTrainLength(train) },
                    {"carPositions", GetFrontRearWorldPos(train) },
                };
            }

            return new Dictionary<string, object>()
            {
                {"trains", trainDict},
                {"CameraSensors",  GetCameraSensorConfigs()}
            };

        }


        /// <summary>
        /// Get the WorldPosition of Front and Rear
        /// </summary>
        /// <returns></returns>
        private Dictionary<string, object> GetFrontRearWorldPos(Simulation.Physics.Train train)
        {
            var FrontPos = train.FirstCar.WorldPosition;
            var RearPos = train.LastCar.WorldPosition;
            return new Dictionary<string, object>()
            {
                {"Front", WorldPosition2Dict(FrontPos)},
                {"Rear", WorldPosition2Dict(RearPos)}
            };
        }
        /// <summary>
        /// Get the length of the locomotive
        /// </summary>
        /// <returns></returns>
        private Dictionary<string, object> GetTrainLength(Simulation.Physics.Train train)
        {
            var length = train.Length;
            return new Dictionary<string, object>()
            {
                {"length", length}
            };
        }

        /// <summary>
        /// Get the state of the locomotive kinematics
        /// </summary>
        /// <returns></returns>
        private Dictionary<string, object> GetLocomotiveState(Simulation.Physics.Train train)
        {
            var locomotive = train.FindLeadLocomotive();
            return new Dictionary<string, object>()
            {
                {"v", locomotive.SpeedMpS},
                {"a", locomotive.AccelerationMpSS},
                {"distance", locomotive.DistanceM},
                {"wheelslip", locomotive.WheelSlip},
                {"wheelskid", locomotive.WheelSkid}
            };
        }


        /// <summary>
        /// get track location of the rear of the train
        /// </summary>
        /// <returns></returns>
        private Dictionary<string, object> GetRearTrackLocation(Simulation.Physics.Train train)
        {
            var traveller = train.RearTDBTraveller;
            return GetTravellerTrackLocation(traveller);
        }

        /// <summary>
        /// get track location of the front of the train
        /// </summary>
        /// <returns></returns>
        private Dictionary<string, object> GetTrackLocation(Simulation.Physics.Train train)
        {
            var traveller = train.FrontTDBTraveller;
            return GetTravellerTrackLocation(traveller);
        }

        /// <summary>
        /// get track location and movement direction of a traveller (i.e., front or rear of a train)
        /// </summary>
        /// <returns></returns>
        private Dictionary<string, object> GetTravellerTrackLocation(Simulation.Traveller
            traveller)
        {
            return new Dictionary<string, object>()
            {
                {"trackNodeIndex", traveller.TrackNodeIndex},
                {"trackNodeLength", traveller.TrackNodeLength},
                {"trackNodeOffset", traveller.TrackNodeOffset},
                {"trackVectorSectionIndex", traveller.TrackVectorSectionIndex},
                {"movementDirection", traveller.Direction.ToString()},
            };
        }

        /// <summary>
        /// Return the current position relative to the center of the center of the tile the train started in. 
        /// This avoids big numbers in the output because the first tile coordinates are likely far away from (0, 0). 
        /// </summary>
        /// <returns></returns>
        private Dictionary<string, object> GetLocationCoordinates(Simulation.Physics.Train train)
        {
            var locomotive = train.FindLeadLocomotive();
            return WorldPosition2Dict(locomotive.WorldPosition);
            
        }

        private Dictionary<string,object> WorldPosition2Dict(WorldPosition worldPosition)
        {
            return new Dictionary<string, object>()
            {
                {"tileX", worldPosition.TileX},
                {"tileZ", worldPosition.TileZ},
                {"x",  worldPosition.Location.X},
                {"y", worldPosition.Location.Y},
                {"z", worldPosition.Location.Z},
            };
        }

        private Dictionary<string, Dictionary<string, object>> GetCameraSensorConfigs()
        {
            var configs = new Dictionary<string, Dictionary<string, object>>();
            foreach (var sensor in Viewer.CameraSensors)
            {
                configs[sensor.Name] = new Dictionary<string, object>()
                {
                    {"height", sensor.ImageHeight},
                    {"width", sensor.ImageWidth},
                    {"h_scale", sensor.Camera.XnaProjection.M11},
                    {"v_scale", sensor.Camera.XnaProjection.M22},
                };
                if (sensor is DepthSensor)
                {
                    configs[sensor.Name]["max_distance"] = ((DepthSensor)sensor).MaxDistance;
                }
            }
            return configs;
        }
        

    }
}
