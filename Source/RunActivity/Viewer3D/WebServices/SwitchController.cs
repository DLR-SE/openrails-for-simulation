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

using System;
using System.Collections.Generic;
using System.Drawing.Printing;
using Orts.Formats.Msts;
using Orts.MultiPlayer;
using Orts.Simulation;
using Orts.Simulation.Physics;
using Orts.Simulation.Signalling;
using Orts.Viewer3D.Popups;
using Swan;

namespace Orts.Viewer3D.WebServices
{
    class SwitchController
    {
        Simulator Simulator;

        public IDictionary<uint, TrJunctionNode> Switches { get; private set; }

        public SwitchController(Simulator simulator)
        {
            this.Simulator = simulator;
            this.Switches = FindSwitches();
        }

        public void UpdateSwitches(IDictionary<uint, int> switchStates)
        {

            foreach (KeyValuePair<uint, int> t in switchStates)
            {
                try
                {
                    var switchNode = Switches[t.Key].TN;
                    var switchState = t.Value;
                    SetSwitch(switchNode, switchState);
                    Console.WriteLine("Swtich with index {0} set", t.Key);
                }
                catch (KeyNotFoundException ex)
                {
                    Console.WriteLine("Could not find switch with index {0}", t.Key);
                }
            }
        }

      
        private void SetSwitch(TrackNode switchNode, int desiredState)
        {
            TrackCircuitSection switchSection = Simulator.Signals.TrackCircuitList[switchNode.TCCrossReference[0].Index];
            Simulator.Signals.trackDB.TrackNodes[switchSection.OriginalIndex].TrJunctionNode.SelectedRoute = switchSection.JunctionSetManual = desiredState;
            switchSection.JunctionLastRoute = switchSection.JunctionSetManual;

            // update linked signals
            if (switchSection.LinkedSignals != null)
            {
                foreach (int thisSignalIndex in switchSection.LinkedSignals)
                {
                    SignalObject thisSignal = Simulator.Signals.SignalObjects[thisSignalIndex];
                    thisSignal.Update();
                }
            }
        }

        private IDictionary<uint, TrJunctionNode> FindSwitches()
        {
            var switches = new Dictionary<uint, TrJunctionNode>();
            foreach (TrackNode t in Simulator.TDB.TrackDB.TrackNodes)
            {
                if (t != null && t.TrJunctionNode != null)
                {
                    switches.Add(t.Index, t.TrJunctionNode);
                }
            }
            Console.WriteLine("Switches:");
            foreach (var t in switches)
            {
                Console.WriteLine(t.ToString());
            }
            return switches;
        }

        private bool SwitchOccupiedByPlayerTrain(TrJunctionNode junctionNode)
        {
            if (Simulator.PlayerLocomotive == null) return false;
            Train train = Simulator.PlayerLocomotive.Train;
            if (train == null) return false;
            if (train.FrontTDBTraveller.TrackNodeIndex == train.RearTDBTraveller.TrackNodeIndex)
                return false;
            Traveller traveller = new Traveller(train.RearTDBTraveller);
            while (traveller.NextSection())
            {
                if (traveller.TrackNodeIndex == train.FrontTDBTraveller.TrackNodeIndex)
                    break;
                if (traveller.TN.TrJunctionNode == junctionNode)
                    return true;
            }
            return false;
        }
    }
}
