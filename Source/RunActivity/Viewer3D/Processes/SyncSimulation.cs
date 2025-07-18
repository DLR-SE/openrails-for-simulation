using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace Orts.Viewer3D.Processes
{
    class SyncSimulation
    {
        public static bool isSyncSimulation = false;
        public static SemaphoreSlim inputSemaphore = new SemaphoreSlim(1, 1);
        public static SemaphoreSlim simulationSemaphore = new SemaphoreSlim(0, 1);
        public static SemaphoreSlim outputSemaphore = new SemaphoreSlim(0, 1);
        public static TimeSpan simStepSeconds = TimeSpan.FromMilliseconds(200);
        public static bool pauseAtGameStart = false;
    }
}
