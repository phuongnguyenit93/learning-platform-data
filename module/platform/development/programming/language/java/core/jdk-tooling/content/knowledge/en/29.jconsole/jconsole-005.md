# Memory Tab in JConsole

The **Memory tab** in **JConsole** is the interface for monitoring memory usage of a running Java Virtual Machine (JVM). This tab displays charts for heap, non-heap, and individual memory pools over time, while also providing Used, Committed, and Max metrics along with garbage collection (GC) statistics.

The Memory tab is useful when you need to observe heap growth or shrinkage, check which memory region is consuming the most resources, track GC impact, and detect trends that may indicate a memory leak. It is a runtime observation tool based on Java Management Extensions (JMX), not a tool for analyzing total OS RAM or automatically finding the root cause of a leak.

## 1. JConsole and the Memory Tab

JConsole is a GUI tool bundled with the JDK that uses JMX to read management information from the JVM. After connecting to a Java application, the interface typically includes the following tabs:

- **Overview:** summary of CPU, memory, threads, and class loading.
- **Memory:** heap/non-heap charts, memory pools, and GC.
- **Threads:** thread count, states, and stack traces.
- **Classes:** class loading statistics.
- **VM:** runtime information and startup arguments.
- **MBeans:** access to registered MXBeans and MBeans.

The Memory tab focuses on memory usage. Charts update over time so you can observe changing trends as the application allocates objects, frees objects, runs GC, or loads classes.

JConsole reads data from platform MXBeans, especially:

- `MemoryMXBean`: heap/non-heap usage and the operation to request GC.
- `MemoryPoolMXBean`: per-pool usage and threshold information.
- `GarbageCollectorMXBean`: collection count and total GC time.
- `ClassLoadingMXBean`: number of loaded classes, if you need to correlate with metaspace.

## 2. Launching JConsole and Connecting to a Local JVM

`jconsole` is located in the JDK `bin` directory. Open a terminal:

```bash
jconsole
```

JConsole displays a dialog listing local Java processes observable by the current user account. Select the application to inspect and click **Connect**.

If you already know the PID, you can connect directly:

```bash
jps -l
jconsole 18420
```

In this example, `18420` is a sample PID; replace it with the actual PID.

On Windows, you can find the PID in Task Manager or use `jps -l`. On Linux/macOS, you can use `ps` or `jps -l`.

For local attach to work:

- JConsole and the target JVM must usually run under the same OS user.
- The JVM must support the Attach API and not be restricted by environment/security policies.
- In containers, PID namespaces and users may differ from the host; sometimes you need to run JConsole inside the same container or namespace.
- Some JVMs cannot be attached to if the Attach Mechanism was disabled at startup.

When connecting locally, JConsole can dynamically enable the management agent on an attachable JVM that did not have the agent enabled at startup. Processes that do not support attach appear grayed out or cannot be selected.

## 3. Connecting JConsole to a Remote JVM

To monitor an application on another machine, JConsole connects through the JMX agent.

Syntax:

```bash
jconsole hostname:port
```

Where:

- `hostname` is the machine running the JVM.
- `port` is the JMX agent port configured on the target JVM.

In the Remote Process dialog, enter the hostname, port, and authentication credentials if required by the JMX agent.

Remote JMX must be configured on the application/JVM side. In production:

- Enable authentication and TLS according to system policy.
- Restrict network sources allowed to access the JMX port.
- Do not expose unauthenticated JMX to the Internet or untrusted networks.
- Do not use default passwords or store passwords in scripts/repositories.
- Prefer VPNs, bastions, or secure tunnels if required by the architecture.

Local monitoring is convenient for development, but JConsole consumes resources on the same machine running the application. For production, remote monitoring helps offload the monitoring UI from the observed machine.

## 4. Main Components of the Memory Tab

The Memory tab typically has the following areas:

1. **Chart:** memory usage chart over time.
2. **Chart selector:** choose Heap Memory Usage, Non-Heap Memory Usage, or a specific memory pool.
3. **Time Range:** select the time window displayed on the chart.
4. **Details:** displays Used, Committed, Max, and GC time values.
5. **Heap/Non-Heap bars:** bars showing the relative usage of heap and non-heap.
6. **Perform GC:** requests the JVM to perform garbage collection.

Memory pool names and display details may vary depending on the JDK vendor, JVM version, garbage collector, and runtime configuration. Do not assume every machine has the exact same list of pools.

## 5. Heap Memory Usage

**Heap memory** is the runtime area where the JVM allocates memory for objects and arrays. The garbage collector reclaims memory from objects that are no longer reachable.

In the Memory tab, select the **Heap Memory Usage** chart to observe total heap usage over time.

A typical chart has a sawtooth pattern:

- As the application creates objects, Used gradually increases.
- When GC reclaims unreachable objects, Used drops.
- Committed may increase when the JVM needs more memory to satisfy allocations.
- Committed may also decrease when the JVM returns part of the memory to the OS.
- Max indicates the heap limit the JVM can use, if a limit is defined.

This chart helps answer:

- Does the heap grow continuously under a steady workload?
- After GC, does Used drop significantly?
- Does the heap frequently approach Max?
- Does Committed grow over time?
- Do memory spikes coincide with high load or batch jobs?

Do not conclude there is a memory leak from a single chart peak. Observe multiple GC cycles and compare post-GC Used levels under comparable workloads.

## 6. Non-Heap Memory Usage

**Non-heap memory** holds data for class structures and internal JVM operations. It may include:

- Class and method metadata.
- Runtime constant pool and class information.
- Metaspace and Compressed Class Space on modern HotSpot.
- Code Cache for native machine code generated by the JIT compiler.
- Other non-heap regions depending on the JVM implementation.

Select **Non-Heap Memory Usage** to observe usage of this memory area.

Non-heap growth may be related to:

- Loading additional classes or dynamic proxies.
- Frameworks creating many classloaders.
- Old classloaders not being released after redeploy.
- The JIT compiler generating more native code.
- Applications or libraries using increasing amounts of metadata.

Do not equate non-heap with the entire native memory of the process. Thread stacks, direct buffers, native libraries, and certain off-heap allocations can increase RSS without fully appearing in the Memory tab's heap/non-heap charts. If process memory grows while heap remains stable, inspect Native Memory Tracking (NMT), direct buffer metrics, and OS tools.

**Historical note:** older JDK documentation may mention Permanent Generation (PermGen). Starting in Java 8, HotSpot removed PermGen and moved class metadata to Metaspace. When learning or operating Java 17+, do not refer to PermGen as an active memory pool name.

## 7. Memory Pools and Per-Pool Charts

A **memory pool** is a memory region managed by the JVM. A JVM can have multiple pools belonging to heap or non-heap; the number and names of pools depend on the garbage collector and implementation.

On HotSpot using G1 in Java 17+, common pools include:

| Group | Example Pool Name | Role |
| --- | --- | --- |
| Heap | G1 Eden Space | Initial allocation region for most new objects |
| Heap | G1 Survivor Space | Region holding objects that survived young GC cycles |
| Heap | G1 Old Gen | Region holding promoted or long-lived objects |
| Non-heap | Metaspace | Class metadata |
| Non-heap | Compressed Class Space | Compressed class pointer metadata when the JVM uses this mechanism |
| Non-heap | CodeHeap 'profiled nmethods' | Part of code cache for JIT-compiled profiled code |
| Non-heap | CodeHeap 'non-profiled nmethods' | Part of code cache for non-profiled JIT code |
| Non-heap | CodeHeap 'non-nmethods' | Runtime/compiler code not belonging to regular nmethods |

Pool names and counts may differ if using Serial GC, Parallel GC, ZGC, Shenandoah, or another JVM vendor.

In the Chart selector, choose a specific pool to view its curve. This helps pinpoint which part of heap or non-heap is growing.

For example:

- Eden rising rapidly and dropping after young GC can be normal allocation activity.
- Old Gen rising across multiple cycles without dropping significantly may warrant investigating object retention.
- Metaspace growing continuously may relate to class loading or classloader lifecycle.
- Code Cache growing during application warm-up and JIT compilation can be normal.

Do not apply one collector's pool names to another collector. Check the actual list in the Memory tab or MBeans.

## 8. Reading Used, Committed, and Max

The Details area displays key metrics.

| Metric | Meaning |
| --- | --- |
| **Used** | Amount of memory currently reported by the JVM as used at the sampling time |
| **Committed** | Amount of memory the JVM has committed and guaranteed available for use |
| **Max** | Maximum limit the memory area can use, if defined |
| **GC time** | Total garbage collection time and collection count per collector |

### Used

Used includes memory occupied by reachable objects as well as unreachable objects not yet reclaimed by GC. Therefore, Used may not drop immediately when the application drops references to objects.

### Committed

Committed is the amount of memory the JVM has committed for use. It is typically greater than or equal to Used. Committed can change based on runtime demand and collector policy.

### Max

Max is the upper limit of the memory region. The value may vary or be undefined; in the API, an undefined value may be represented as `-1`.

Even when Used has not reached Max, allocations can still fail if the JVM cannot increase Committed due to insufficient system resources or container limits.

### GC time

GC time is the cumulative time spent on garbage collection and the number of collections. There may be multiple lines, each corresponding to a collector / garbage collector bean.

This is a cumulative metric since JVM startup or since counters were reset by the implementation; it is not the pause time of only the most recent GC.

## 9. Heap and Non-Heap Bars

In the bottom-right corner, the Memory tab displays Heap and Non-Heap bars representing relative usage against each region's limit/manageable capacity.

A bar can turn red when memory usage exceeds a configured usage threshold. Thresholds are only supported on certain memory pools; check support before setting them.

In JMX, threshold information is exposed on `MemoryPoolMXBean`:

- `isUsageThresholdSupported()` indicates whether the pool supports a usage threshold.
- `getUsageThreshold()` reads the current threshold.
- `setUsageThreshold(long)` sets the threshold if supported and the caller has appropriate permissions.
- `isUsageThresholdExceeded()` indicates whether the threshold is exceeded at the time of inspection.

Do not treat red bars as conclusive proof of a memory leak. It is a threshold-exceeded signal for operators to investigate further.

## 10. Chart Selector and Time Range

The **Chart selector** lets you choose what data to monitor:

- Heap Memory Usage.
- Non-Heap Memory Usage.
- A specific memory pool provided by the JVM.

**Time Range** lets you choose the time span retained by the chart. Choose a short range to inspect a single allocation/GC event in detail; choose a long range to observe trends over many minutes or longer.

How to use them:

1. Select Heap Memory Usage to observe total heap.
2. Select Non-Heap Memory Usage to monitor metadata and code cache.
3. Select individual pools to isolate the growing area.
4. Change Time Range to compare short-term fluctuations and long-term trends.
5. Correlate increases/decreases with logs, metrics, request rate, and GC activity.

Do not look only at the aggregate line. If heap grows, select Old Gen or Eden to find which pool contributes more. If non-heap grows, check Metaspace and Code Cache.

## 11. Perform GC: When Should You Use It?

The **Perform GC** button requests the JVM to perform garbage collection. It is equivalent to requesting GC via the management interface; actual behavior depends on the collector and JVM configuration.

It can be used during a controlled investigation to observe Used before and after GC:

1. Record the current Used and Committed values.
2. Click Perform GC once.
3. Observe Used after GC completes.
4. Compare with previous natural GC cycles.
5. Note the timestamp of the action to correlate with logs and metrics.

If Used drops sharply, many objects were unreachable and have been reclaimed. If Used remains high, many objects may still be reachable or the collector may not have reclaimed as expected.

**Do not click Perform GC repeatedly.** Explicit GC requests can cause pauses and alter runtime behavior. Some configurations may ignore explicit GC. A drop in Used after GC does not prove the application has no leak; Used not dropping also does not by itself prove a leak.

In production, prefer observing natural GC cycles first. Only use Perform GC when you have a specific diagnostic question and have weighed the impact.

## 12. Identifying Trends That May Indicate a Memory Leak

Memory leaks in Java typically occur when objects are no longer needed but remain reachable through a reference—such as a static collection, an unbounded cache, an unregistered listener, or a `ThreadLocal` retaining data longer than intended.

Signs that warrant investigation:

- Post-GC Used trends upward over time under comparable workloads.
- Old Gen grows across multiple cycles and does not return to the previous baseline.
- Committed keeps increasing to satisfy allocations.
- GC frequency or total GC time increases.
- The application approaches Max or encounters `OutOfMemoryError`.
- The number of retained objects in certain classes increases over time.

Observation workflow:

1. Choose a time window with a relatively steady workload.
2. Monitor Heap Memory Usage across multiple GC cycles.
3. Switch to Old Gen and check post-collection Used levels.
4. Record GC time/count.
5. Repeat after an interval and compare against the baseline.
6. If the trend is suspicious, capture a class histogram or heap dump for deep analysis.

JConsole charts only help detect symptoms. To find the root cause, analyze a heap dump with Eclipse Memory Analyzer (MAT), inspecting the dominator tree, retained size, and path to GC roots. JFR is also useful when you need to examine allocations and GC over time.

## 13. Exporting Chart Data to CSV

JConsole lets you export chart data:

1. Right-click the chart you want to save.
2. Select **Save data as...**.
3. Choose the path and CSV filename.
4. Open the CSV in a spreadsheet or data analysis tool.

The CSV typically contains a timestamp column and one or more value columns. You can use this data to:

- Plot custom charts.
- Compare heap usage across runs.
- Calculate baselines and growth rates over time.
- Align with deployment times, batch jobs, or incidents.
- Share filtered numbers instead of sending full screenshots.

When importing CSV into a spreadsheet, check the timestamp column format so time values are parsed accurately.

## 14. Viewing Memory Metrics via MBeans

The Memory tab uses platform MXBeans. If you need more detailed information, open the **MBeans** tab.

Common nodes:

- `java.lang / Memory`: HeapMemoryUsage, NonHeapMemoryUsage, ObjectPendingFinalizationCount, and the GC operation.
- `java.lang / MemoryPool`: Usage, PeakUsage, CollectionUsage, and thresholds for each pool.
- `java.lang / GarbageCollector`: CollectionCount and CollectionTime.
- `java.lang / OperatingSystem`: OS and process information depending on JDK/vendor.

You can double-click a supported numeric value to view a chart of that attribute. Writable attributes can be modified from the MBeans tab if the MBean permits it; only change them when you clearly understand the impact.

Java example reading heap and each memory pool:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryUsage;

public class MemoryMetrics {
    public static void main(String[] args) {
        MemoryUsage heap =
            ManagementFactory.getMemoryMXBean().getHeapMemoryUsage();

        System.out.printf(
            "Heap used=%d committed=%d max=%d%n",
            heap.getUsed(),
            heap.getCommitted(),
            heap.getMax()
        );

        for (MemoryPoolMXBean pool :
                ManagementFactory.getMemoryPoolMXBeans()) {
            MemoryUsage usage = pool.getUsage();

            if (usage != null) {
                System.out.printf(
                    "%s: used=%d committed=%d max=%d%n",
                    pool.getName(),
                    usage.getUsed(),
                    usage.getCommitted(),
                    usage.getMax()
                );
            }
        }
    }
}
```

Compile and run:

```bash
javac --release 17 MemoryMetrics.java
java MemoryMetrics
```

Metrics vary by execution time and JVM. This example reads the same set of MXBeans that JConsole uses to display memory information.

## 15. Java 17 Hands-On Example: Generating Memory Activity to Observe

This example creates short-lived allocations and retains a bounded list of byte arrays. The goal is to generate enough heap fluctuation to observe on the Memory tab.

File **`MemoryTabTarget.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;
import java.util.ArrayDeque;
import java.util.Deque;

public final class MemoryTabTarget {
    private static final Deque<byte[]> RETAINED = new ArrayDeque<>();
    private static volatile byte[] lastTransientAllocation;

    private MemoryTabTarget() {
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println("PID=" + ProcessHandle.current().pid());

        ManagementFactory.getMemoryPoolMXBeans().forEach(pool ->
            System.out.println(
                "pool=" + pool.getName() + " type=" + pool.getType()
            )
        );

        int round = 0;

        while (!Thread.currentThread().isInterrupted()) {
            for (int i = 0; i < 12; i++) {
                lastTransientAllocation = new byte[256 * 1024];
                lastTransientAllocation[0] = (byte) i;
            }

            RETAINED.addLast(new byte[1024 * 1024]);

            if (RETAINED.size() > 16) {
                RETAINED.removeFirst();
            }

            if (round++ % 5 == 0) {
                MemoryUsage heap =
                    ManagementFactory.getMemoryMXBean()
                        .getHeapMemoryUsage();

                System.out.printf(
                    "heap used=%d committed=%d max=%d retainedChunks=%d%n",
                    heap.getUsed(),
                    heap.getCommitted(),
                    heap.getMax(),
                    RETAINED.size()
                );
            }

            Thread.sleep(500);
        }
    }
}
```

Compile:

```bash
javac --release 17 MemoryTabTarget.java
```

Run with a bounded heap for easy observation:

```bash
java -Xms32m -Xmx128m -XX:+UseG1GC MemoryTabTarget
```

Sample output from a test run:

```text
PID=78016
pool=CodeHeap 'non-nmethods' type=Non-heap memory
pool=Metaspace type=Non-heap memory
pool=CodeHeap 'profiled nmethods' type=Non-heap memory
pool=Compressed Class Space type=Non-heap memory
pool=G1 Eden Space type=Heap memory
pool=G1 Old Gen type=Heap memory
pool=G1 Survivor Space type=Heap memory
pool=CodeHeap 'non-profiled nmethods' type=Non-heap memory
heap used=7455512 committed=35651584 max=134217728 retainedChunks=1
```

The PID and numbers are from a single test run; they will change when you run it again. Memory pool names also depend on the JDK and collector.

Open a second terminal and connect JConsole:

```bash
jconsole 78016
```

Replace `78016` with the PID printed by the program. In JConsole:

1. Select the Memory tab.
2. Select Heap Memory Usage.
3. Adjust Time Range to observe allocations and GC.
4. Select G1 Eden Space and G1 Old Gen if those pools appear.
5. Switch to Non-Heap Memory Usage to view Metaspace and Code Cache.
6. Compare Used, Committed, Max, and GC time.
7. Optionally export the chart to CSV via the right-click menu.

The program retains up to 16 1 MiB arrays in the list; each round replaces an older array with a new one. The short-lived allocations generate additional GC activity. This is a hands-on example, not a benchmark, and does not fully simulate a production workload.

Stop the program with Ctrl+C in the terminal running `MemoryTabTarget`.

## 16. Common Issues When Using the Memory Tab

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| JVM not visible in Local Process list | Different user, non-attachable process, or Attach Mechanism restricted | Check user, PID namespace, and JVM options |
| Remote connection fails | JMX agent not enabled, wrong host/port, or blocked by firewall | Verify JMX configuration and network policy |
| Expected pool not visible | Pools depend on collector/JDK/vendor | Check the actual list in the Memory tab or `MemoryPoolMXBean` |
| Heap Used rises without dropping | No GC yet, objects still reachable, or workload retaining data | Observe across multiple GC cycles and inspect Old Gen |
| Heap Used drops after Perform GC | GC reclaimed unreachable objects | Keep monitoring baseline; do not treat one GC as leak-free proof |
| Non-Heap grows continuously | Class loading, Metaspace, or Code Cache growth | Monitor specific pools and classloader statistics |
| Process RAM is high while Heap is normal | Native memory, thread stacks, direct buffers, or native libraries | Check NMT, OS metrics, and direct buffer usage |
| Pool bar turns red | Usage threshold exceeded | Check threshold and pool trend; verify threshold support |
| GC time rises rapidly | GC occurring more frequently or taking longer | Correlate allocation, heap occupancy, collector logs, and JFR |
| Unable to save chart CSV | Invalid path or insufficient write permissions | Choose a writable directory and check disk space |

## 17. Production Monitoring Notes

- JConsole is a monitoring tool, not a replacement for continuous metrics/alerting.
- Local JConsole can consume significant CPU and memory; consider remote monitoring to reduce load on the target machine.
- Do not click Perform GC repeatedly to force charts down.
- Do not conclude a memory leak from a single snapshot or a single GC.
- Use comparable workloads when comparing baselines.
- Protect JMX connection details and credentials.
- Do not open unauthenticated JMX ports to public networks.
- Store CSVs, heap dumps, and JFR recordings according to security/retention policies.
- When deep analysis is needed, combine JConsole with JFR, heap dumps, MAT, GC logs, and OS-level memory metrics.

The Memory tab helps detect trends and isolate pools. To identify the root cause of a memory leak, you need to trace object retention, GC roots, allocations, and application lifecycle.

## 18. Memory Tab Investigation Workflow

When investigating memory pressure:

1. Connect to the right JVM and record the PID/JDK version.
2. Select Heap Memory Usage and observe Used/Committed/Max.
3. Select Non-Heap Memory Usage to inspect metadata and code cache.
4. Select the specific pool that is growing.
5. Monitor multiple GC cycles and compare post-GC Used.
6. Read GC time/count to evaluate collector activity.
7. Use Perform GC only when you have a clear diagnostic goal.
8. Export chart CSVs if needed for comparison or reporting.
9. If a leak is suspected, capture a histogram/heap dump or JFR for deep analysis.
10. Correlate heap/non-heap with process memory and container limits.
11. Protect diagnostic files and JMX credentials.
12. Base conclusions on trends, not a single point in time.

## 19. Key Takeaways

- The Memory tab in JConsole monitors heap, non-heap, memory pools, and GC over time.
- Heap holds objects/arrays; non-heap holds class metadata, method data, and JIT code.
- Memory pools depend on the JDK, JVM vendor, and garbage collector.
- Used can include unreachable objects not yet reclaimed by GC.
- Committed is memory already committed; Max is the maximum limit if defined.
- GC time/count are cumulative metrics per collector.
- Chart selector and Time Range help isolate memory pools and time windows.
- Perform GC only requests GC; it can cause pauses and does not replace leak analysis.
- Pool bars can turn red when a usage threshold is exceeded.
- Right-click a chart and choose Save data as... to export CSV.
- Java 17 HotSpot uses Metaspace instead of PermGen.
- Stable heap does not mean total process memory is stable; monitor native memory and direct buffers when needed.

Knowing how to read charts, memory pools, Used/Committed/Max, and GC time helps you use the Memory tab for evidence-based JVM monitoring, spot memory pressure early, and decide when to escalate to heap dumps, JFR, or deeper analysis tools.

## References

- [Using JConsole — Java SE 24 Monitoring and Management Guide](https://docs.oracle.com/en/java/javase/24/management/using-jconsole.html)
- [MemoryMXBean — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.management/java/lang/management/MemoryMXBean.html)
- [MemoryPoolMXBean — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html)
- [GarbageCollectorMXBean — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html)
