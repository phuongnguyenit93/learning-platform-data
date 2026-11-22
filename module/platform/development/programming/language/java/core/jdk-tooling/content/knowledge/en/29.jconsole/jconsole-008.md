# How to Read VM Summary in JConsole

VM Summary is the overview screen of Java Virtual Machine (JVM) information in JConsole. It consolidates metrics for uptime, CPU, JIT compilation, threads, class loading, heap, garbage collection, operating system, and launch configuration in one place. When an application slows down, consumes increasing memory, creates too many threads, or runs in an unexpected environment, this screen helps you identify which resource group to investigate next.

This article uses JDK 17 or later. The focus is on the meaning of each field in VM Summary, how to read metrics over time, distinguishing cumulative counters from current values, how to connect JConsole to local/remote JVMs, and how to cross-reference with MXBeans or command-line tools.

## 1. What Are JConsole and VM Summary?

JConsole is a graphical user interface tool that uses Java Management Extensions (JMX) to monitor and manage a JVM. The JVM provides instrumentation and platform MXBeans; JConsole reads that data through the management agent.

After connecting to a Java process, the JConsole interface typically has the following tabs:

| Tab | Purpose |
|---|---|
| Overview | Quickly view charts for CPU, memory, threads, and class loading |
| Memory | Monitor heap, non-heap, memory pools, and GC |
| Threads | View live threads, states, stack traces, and deadlocks |
| Classes | Monitor currently loaded classes, total loaded, and unloaded classes |
| VM Summary | View consolidated information on JVM, threads, classes, memory, GC, OS, and launch arguments |
| MBeans | Read attributes, invoke operations, and manage registered MBeans |

Tab names or layouts may vary slightly depending on the JDK version and platform. In JDK 17 documentation, this overview screen is called **VM Summary**.

VM Summary answers initial diagnostic questions such as:

- How long has the JVM been running?
- How much CPU time has the process consumed?
- How much time has the JIT compiler spent compiling?
- How many threads and classes are currently active?
- How much heap is used, committed, and what is the maximum it can grow to?
- How many times have the garbage collectors run and how much time did they take?
- Which operating system is the JVM running on, and with what arguments/classpath was it launched?

VM Summary is the starting point to guide diagnosis. When you spot an anomaly, switch to the specialized tab or appropriate tool to verify the root cause.

## 2. Launching JConsole

The `jconsole` executable is located in the JDK's `bin` directory.

If the JDK is already in your PATH:

~~~powershell
jconsole
~~~

You can launch JConsole and connect directly to a PID:

~~~powershell
jconsole 8120
~~~

PID `8120` is just an example. Find the PID using:

~~~powershell
jps -l
~~~

Or use Task Manager on Windows, or `ps` on Linux/macOS.

When running `jconsole` without a PID, the New Connection dialog lets you select a local process or enter remote connection details. Select the right application and click Connect. After connecting, open the **VM Summary** tab.

### 2.1. Local Connection Requirements

For JVMs that support the Attach API, modern JDKs can automatically start the management agent when JConsole attaches; you usually do not need to add `-Dcom.sun.management.jmxremote` for local monitoring.

Common requirements:

- JConsole and the application are running on the same machine.
- JConsole and the target JVM are running under the same OS user account.
- The target JVM supports attach and is not blocked by security configuration.
- The selected PID is the PID of the JVM to monitor.
- On Windows, the default temporary directory must reside on a filesystem that supports appropriate file/directory permissions, such as NTFS.

If the process does not appear or you cannot connect, check the PID, user, JDK, and container environment before changing JVM configuration.

### 2.2. Remote Connection

To monitor a JVM on another machine, the target JVM must have the JMX remote agent enabled. JConsole can be launched with the syntax:

~~~powershell
jconsole app-server.example.com:9010
~~~

Or enter the hostname and port in the New Connection dialog. If the agent requires authentication, provide the username/password configured by the administrator.

Remote JMX has permissions to read runtime information and may allow invoking operations or modifying MBean attributes. Therefore:

- Enable authentication and TLS according to the JDK guide.
- Restrict the port using firewalls and network policies.
- Grant accounts only the necessary permissions; use read-only access when only monitoring.
- Protect password/access files with restricted file permissions.
- Do not expose unauthenticated JMX to the Internet or untrusted networks.
- Do not place real credentials in shell history, scripts, or logs.

Oracle fully documents JMX remote properties, password/access files, and TLS in the Java SE 17 Monitoring and Management Guide. Do not disable authentication or SSL as a workaround for connection issues in production.

## 3. Structure of Information Groups in VM Summary

Fields are typically grouped as follows:

1. **Summary:** JVM identification, uptime, process CPU time, and JIT compile time.
2. **Threads:** live thread count, peak, daemon, and total threads started.
3. **Classes:** current classes loaded, total classes loaded, and classes unloaded.
4. **Memory:** current heap, maximum heap, committed memory, objects pending finalization, and GC statistics.
5. **Operating System:** operating system, architecture, processors, and certain RAM/virtual memory/swap metrics depending on the platform.
6. **Other Information:** VM arguments, class path, library path, and boot class path information if provided by the runtime.

Some fields may be absent or show as unavailable depending on the JVM, operating system, garbage collector, and JDK vendor. Do not assume every JVM will display the exact same list.

## 4. Summary: Uptime, CPU Time, and JIT Compile Time

### 4.1. Uptime

`Uptime` is the total time the JVM has been running since startup.

For example, if uptime shows `02:15:30`, the JVM has been running for approximately 2 hours, 15 minutes, and 30 seconds. This is not the time a user has had the application open, nor is it necessarily equal to the server's uptime.

Uptime is useful to:

- Determine whether the application recently restarted or has been running for a long time.
- Place cumulative counters into the proper time window.
- Compare two metric snapshots.
- Recognize when a restart has reset runtime counters.

If a counter such as total threads started or total classes loaded increases, evaluate it alongside uptime. A large value on a JVM running for many days may be normal; the rate of growth is what matters.

### 4.2. Process CPU Time

`Process CPU Time` is the total CPU time the JVM process has used since startup. This is cumulative CPU time, not an instantaneous CPU percentage.

For example, after one wall-clock minute, an increase of 20 seconds in process CPU time indicates the process used a total of about 20 seconds of CPU during that interval. On multi-core machines, CPU time can increase faster than wall-clock time because multiple threads can run in parallel.

To observe trends, record two samples:

| Sample | Uptime | Process CPU Time |
|---|---:|---:|
| A | 10 minutes | 45 seconds |
| B | 11 minutes | 78 seconds |

In the one minute between the two samples, CPU time increased by 33 seconds. This is the cumulative CPU consumption of the entire process during that interval. Cross-check against core count, system load, and OS metrics before concluding high CPU usage.

If Process CPU Time is unavailable or unsupported, use OS tools, JFR, or an APM for alternative metrics.

### 4.3. Total Compile Time

`Total Compile Time` is the total time the JVM has spent on JIT compilation since startup. The JIT compiler compiles certain bytecode methods into native machine code when the runtime determines they provide a performance benefit.

Keep in mind the distinction:

- This is cumulative time spent on compilation activity.
- It is not the time the application spent processing requests.
- It is not the CPU time of the entire process.
- It does not indicate which specific method is slow.
- It does not mean every method has been compiled.

During startup or warm-up, compile time may rise rapidly as the JVM compiles hot methods. Once the application stabilizes, the rate of increase may drop. If you need detailed compilation data, use the MBeans tab / Compilation MXBean, JFR, or a profiling tool.

## 5. Threads: Reading Thread Counts and Trends

VM Summary displays four main thread metrics.

| Field | Meaning |
|---|---|
| Live threads | Number of daemon and non-daemon threads currently alive |
| Peak | Highest number of live threads since the JVM started |
| Daemon threads | Number of daemon threads currently alive |
| Total threads started | Total number of threads started since the JVM started, including terminated threads |

### 5.1. Live threads

Live threads is the number of threads existing at the time of the refresh. This number can fluctuate as requests arrive, workers are created, tasks complete, or thread pools expand/shrink.

A large value is not automatically a bug. A web server may have many worker threads to serve concurrent requests. Compare against your baseline and thread pool configuration.

### 5.2. Peak

Peak is the highest live thread count observed since the JVM started. It helps you see how high the thread count has ever spiked, even if the current thread count has dropped.

Peak always retains the highest observed value. If live threads drop while peak remains high, it does not mean the old threads are still alive.

### 5.3. Daemon threads

Daemon threads are background threads that the JVM does not wait on to keep the process alive when no non-daemon threads remain. Some runtime threads, schedulers, and background workers may be daemon threads.

Daemon count should be viewed alongside Live threads. If daemon threads grow continuously, look for executors or components creating background threads with uncontrolled lifecycles.

### 5.4. Total threads started

This is a cumulative counter that includes terminated threads. If Total threads started rises rapidly while Live threads stays nearly flat, the application may be creating and destroying many threads continuously.

This can be a sign of thread churn—for example, code creating a new thread per request instead of reusing an executor. If both Live threads and Peak grow over time, investigate a potential thread leak or unbounded pool.

When an anomaly is detected, open the Threads tab to inspect names, states, and stack traces. Use the Detect Deadlock button if you need to check for deadlocks; for deeper analysis, capture a thread dump with `jcmd PID Thread.print -l`.

## 6. Classes: Distinguishing Current Counts from Cumulative Counters

VM Summary displays:

| Field | Meaning |
|---|---|
| Current classes loaded | Number of classes currently loaded in the JVM |
| Total classes loaded | Total number of classes loaded since the JVM started, including classes later unloaded |
| Total classes unloaded | Total number of classes unloaded since the JVM started |

Example:

~~~text
Current classes loaded: 8,400
Total classes loaded: 9,100
Total classes unloaded: 700
~~~

In this example, the JVM has loaded 9,100 classes in total; 700 classes have been unloaded, leaving 8,400 classes currently loaded. These are illustrative counters, not fixed output.

How to read trends:

- Total loaded increasing during startup/warm-up is normal.
- Current loaded stabilizing after warm-up is usually a sign that class loading has settled.
- Total loaded rising continuously while current loaded trends upward may indicate dynamic class loading.
- Total unloaded increasing shows the JVM has unloaded classes; it does not automatically mean a memory leak has been completely resolved.

If you suspect a class loader leak, combine the Classes tab with Metaspace metrics, `jcmd PID VM.classloader_stats`, and a heap dump. Do not conclude a leak solely from an increasing total class count.

## 7. Memory: Heap, Committed, and Maximum

VM Summary displays key memory fields. It is important to understand the difference between used memory, committed memory, and the maximum limit.

| Field | Meaning |
|---|---|
| Current heap size | Amount of heap currently in use as displayed by VM Summary |
| Committed memory | Amount of heap committed by the JVM and guaranteed available for use |
| Maximum heap size | Maximum heap limit the JVM can use, if determined by the runtime |
| Objects pending for finalization | Number of objects awaiting finalization |

These values are usually shown in KB or human-readable units like MB. Check the unit on the UI before converting.

### 7.1. How Do Used, Committed, and Max Differ?

- **Used:** the portion of memory currently in use. Heap used may include objects not yet reclaimed by GC at the time of sampling.
- **Committed:** the portion of memory the JVM has committed and guaranteed available for the JVM to use. Committed is typically greater than or equal to used.
- **Max:** the maximum amount the memory-managed area can reach. Depending on the runtime, this value may be undefined or may change.

Example:

~~~text
Current heap size: 420 MB
Committed memory: 768 MB
Maximum heap size: 2048 MB
~~~

This example shows roughly 420 MB of heap in use, 768 MB committed, and the heap can grow up to around 2 GB if the JVM and environment allow. It does not mean the process is using only 420 MB of RAM in total; the JVM also uses non-heap and native memory.

Do not conclude a memory leak from a single high used sample. Observe across multiple GC cycles under the same workload. If heap used after GC keeps rising across multiple cycles, inspect object retention with a heap dump/profiler.

### 7.2. Objects pending for finalization

This field counts objects awaiting finalization. Finalization is a legacy mechanism with overhead and has been deprecated in modern Java. Do not use this field as a general measure of all objects awaiting GC or the entire application backlog.

If pending finalization increases, review code using `finalize()` and prefer explicit resource management mechanisms such as try-with-resources, `AutoCloseable`, or an appropriate cleaner.

## 8. Garbage Collector: Collection Count and GC Time

VM Summary can list each garbage collector with the following information:

- Collector name.
- Number of collections performed.
- Total time spent on collections.

Illustrative example:

~~~text
Garbage collector:
  Name = G1 Young Generation
  Collections = 120
  Total time spent = 2.40 seconds

Garbage collector:
  Name = G1 Old Generation
  Collections = 3
  Total time spent = 1.15 seconds
~~~

Collector names and young/old splits depend on the JVM and the selected GC. Some collectors may expose multiple MXBeans; exact metrics vary by JDK and configuration.

### 8.1. Collections

Collections is a cumulative counter of how many times the collector has run since JVM startup. Compare the delta between two readings rather than looking only at the total.

If young collections increase rapidly, the application may be allocating many short-lived objects. If old/full collections occur frequently, check heap pressure, long-lived objects, and GC configuration.

### 8.2. Total time spent

This is the cumulative time the collector reports having spent on GC. Compare the delta over a time window against the length of the observation window to assess impact.

For example, an increase of 0.8 seconds in GC time over one minute shows the collector spent 0.8 seconds total on GC activity during that window. Cross-reference with actual pause times, throughput, latency, and GC logs; total collector time does not replace per-pause analysis.

### 8.3. When to Open the Memory Tab?

Switch to the Memory tab when you need to:

- View heap/non-heap over time.
- Select a specific memory pool.
- Monitor Eden, Survivor, Old/tenured, or Metaspace depending on the GC/JVM.
- Compare used, committed, and max.
- Cross-reference GC time and collection counts.
- Check memory trends before and after collections.

The Perform GC button can request the JVM to run garbage collection. This operation affects the running process and should not be clicked casually in production just to "see if memory drops".

## 9. Operating System: Reading Host Information

The Operating System section can display:

| Field | Meaning |
|---|---|
| Operating System | Operating system name and version |
| Architecture | System architecture |
| Number of processors | Number of processors reported by the runtime |
| Total physical memory | Total physical RAM |
| Free physical memory | Free physical RAM |
| Committed virtual memory | Amount of virtual memory guaranteed to be available to the process |
| Total swap space | Total swap space, if supported |
| Free swap space | Free swap space, if supported |

Specific fields depend on the OS, JDK vendor, and version. Some information comes from extensions of `OperatingSystemMXBean`, which not all platforms support.

### 9.1. Distinguishing JVM Memory from OS Memory

Heap committed is memory the JVM committed for the heap. Committed virtual memory is a process/OS-level metric. These two metrics do not cover the same scope.

A Java process also uses:

- Metaspace and compressed class space.
- JIT code cache.
- Thread stacks.
- Direct byte buffers.
- Native libraries and JNI allocations.
- Other native/internal JVM regions.

Therefore, a 2 GB max heap does not mean the process can use at most 2 GB of RAM.

In containers, OS metrics may reflect the host or values adjusted by a container-aware JVM, depending on the JDK and platform. Cross-check with cgroup/container metrics or platform operational tools instead of assuming values in JConsole are always container limits.

## 10. Other Information: VM Arguments and Paths

The bottom of VM Summary provides launch information and class/native library search paths.

| Field | Meaning |
|---|---|
| VM arguments | Arguments passed to the JVM at launch, excluding arguments passed to `main(String[] args)` |
| Class path | Classpath used by the system class loader to locate classes |
| Library path | List of paths searched when loading native libraries |
| Boot class path | Path used by the bootstrap class loader when provided by the runtime |

Example VM arguments:

~~~text
-Xms512m
-Xmx2g
-XX:+UseG1GC
-Dapp.profile=production
~~~

These arguments help verify which heap size, GC, and profile the JVM is actually running with. If the configuration in your deployment script differs from what appears in VM Summary, investigate the service wrapper, container entrypoint, or deployment setup.

### 10.1. VM Arguments Are Not Application Arguments

These two types of arguments are different:

~~~powershell
java -Xmx2g -Dapp.profile=prod -jar app.jar --mode=batch
~~~

- `-Xmx2g` and `-Dapp.profile=prod` are JVM arguments.
- `--mode=batch` is an application argument passed to `main(String[] args)` or the command-line handling framework.

VM Summary displays VM arguments; it is not a screen listing all business/application arguments.

### 10.2. Be Careful with Sensitive Information

VM arguments may contain passwords/tokens if an application was misconfigured by passing secrets on the command line or via `-D`. Class path and library path can also reveal directory structures, service names, and internal artifacts.

Before sharing screenshots or output:

- Redact credentials and tokens if present.
- Redact hostnames, usernames, and internal paths when required by policy.
- Do not paste full VM arguments into public tickets.
- Extract only the fields needed for diagnosis.

## 11. Reading VM Summary by Real-World Scenario

### 11.1. Application Just Started

Signs you may see:

- Low uptime.
- Process CPU Time and Total Compile Time increasing as the JVM warms up.
- Total threads started increasing while the framework creates workers.
- Total classes loaded increasing rapidly.
- Heap used/committed fluctuating as the application initializes.

This can be normal behavior. Capture a baseline after the application finishes warming up for future comparisons.

### 11.2. High CPU Usage

Check Process CPU Time at two points in time. If the delta increases rapidly relative to wall-clock time, the process is consuming more CPU.

Next:

1. Check Overview to see the CPU trend.
2. Open Threads and look for threads with relevant stacks.
3. Take multiple thread dumps to see if RUNNABLE threads repeatedly show the same stack.
4. Use JFR or a profiler to locate hot methods.

Process CPU Time is only a process-wide total; VM Summary does not identify the specific thread or method causing the load.

### 11.3. Growing Thread Count

Compare Live threads, Peak, and Total threads started:

- Live rising and not dropping after load subsides: check for a thread leak or unbounded executor.
- Total started rising rapidly while Live stays stable: short-lived threads may be created too frequently.
- High Peak but low current Live: the application may have experienced a heavy load spike that has since subsided.

Open Threads to inspect thread names and stacks; group threads by prefix to identify the component creating them.

### 11.4. Rising Heap Used

Monitor Current heap size, Committed, and Maximum. If used rises while a workload runs, that may be normal. If used after GC does not drop and increases across multiple cycles, investigate object retention.

Switch to the Memory tab to inspect heap pools and GC. If you need to find which objects are retaining memory, take a heap dump using an appropriate procedure and analyze it with a heap analyzer.

### 11.5. Continuously Increasing Class Count

If Total classes loaded increases, check Current classes loaded and Total classes unloaded:

- Current stable, total rising: new classes are being loaded and some older classes may have been unloaded.
- Current rising steadily, unloaded not rising: possible dynamic class loading or old class loaders being retained.
- Total unloaded rising: the JVM has unloaded classes; still check Metaspace if a memory leak is suspected.

Use the Classes tab, `jstat -class`, and `jcmd PID VM.classloader_stats` for deeper investigation.

### 11.6. Increasing GC Time

Compare collection counts and total GC time across intervals. If GC time rises rapidly alongside heap pressure and latency, analyze GC logs/JFR and allocation workload. Do not change GC flags based solely on a single VM Summary snapshot.

## 12. Mapping VM Summary to the Java Management API

VM Summary displays data retrieved from platform MXBeans and runtime/OS information. Applications can also read many of these metrics using `ManagementFactory`.

| Section in VM Summary | Common API/MXBean |
|---|---|
| Uptime, VM arguments, class path | `RuntimeMXBean` |
| Process CPU and OS info | `OperatingSystemMXBean` or vendor extension |
| Thread count, peak, daemon, total started | `ThreadMXBean` |
| Current/total/unloaded classes | `ClassLoadingMXBean` |
| Heap usage and pending finalization | `MemoryMXBean` |
| GC count and collection time | `GarbageCollectorMXBean` |
| Total compile time | `CompilationMXBean` |

Example of reading some values in Java:

~~~java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.CompilationMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.RuntimeMXBean;
import java.lang.management.ThreadMXBean;

public class VmSummaryMetrics {
    public static void main(String[] args) {
        RuntimeMXBean runtime = ManagementFactory.getRuntimeMXBean();
        ThreadMXBean threads = ManagementFactory.getThreadMXBean();
        ClassLoadingMXBean classes =
                ManagementFactory.getClassLoadingMXBean();
        CompilationMXBean compilation =
                ManagementFactory.getCompilationMXBean();

        System.out.println("Uptime ms: " + runtime.getUptime());
        System.out.println("Live threads: " + threads.getThreadCount());
        System.out.println("Peak threads: " + threads.getPeakThreadCount());
        System.out.println("Daemon threads: " + threads.getDaemonThreadCount());
        System.out.println("Total started threads: "
                + threads.getTotalStartedThreadCount());
        System.out.println("Current loaded classes: "
                + classes.getLoadedClassCount());
        System.out.println("Total loaded classes: "
                + classes.getTotalLoadedClassCount());
        System.out.println("Total unloaded classes: "
                + classes.getUnloadedClassCount());

        if (compilation != null && compilation.isCompilationTimeMonitoringSupported()) {
            System.out.println("Total compile time ms: "
                    + compilation.getTotalCompilationTime());
        } else {
            System.out.println("Compilation time monitoring is unavailable.");
        }
    }
}
~~~

Compile and run:

~~~powershell
javac VmSummaryMetrics.java
java VmSummaryMetrics
~~~

Thread, class, and uptime numbers vary at runtime, so stdout has no fixed output. The program prints metrics with the same meaning as part of VM Summary; process CPU time and some OS fields may require vendor-specific extension APIs.

## 13. How Does VM Summary Differ from Other Tabs?

VM Summary provides the big picture. Other tabs provide more detailed data:

| When you need to... | Open tab |
|---|---|
| View CPU, heap, threads, and classes trends together | Overview |
| View memory pools, heap/non-heap, and GC | Memory |
| View thread names, states, stack traces, and deadlocks | Threads |
| View current, total loaded, and unloaded class counts | Classes |
| View uptime, CPU time, compile time, thread/class/memory/OS, and VM args | VM Summary |
| View platform MXBeans, application MBeans, attributes, and operations | MBeans |

For example, VM Summary reports an unusual increase in Live threads. The Threads tab helps identify which threads are alive and their stack traces. VM Summary reports rising heap; the Memory tab shows which pool is growing. VM Summary reports rising total classes; the Classes tab shows current/total/unloaded over time.

## 14. Saving Charts and Comparing Over Time

JConsole allows saving chart data to CSV:

1. Open the tab containing the chart to save, such as Overview, Memory, Threads, or Classes.
2. Right-click on the chart.
3. Select **Save data as...**.
4. Choose the path and CSV filename.
5. Open the CSV in a spreadsheet or analysis tool.

The CSV typically contains a timestamp column and the measured values. When importing into a spreadsheet, check the timestamp format and column units before re-plotting.

VM Summary contains many cumulative counters; to analyze trends, record periodic snapshots or export charts from specialized tabs. Compare deltas over a time interval rather than comparing only total values since JVM startup.

## 15. Common Issues When Using VM Summary

| Symptom | Common Cause | Resolution |
|---|---|---|
| `jconsole is not recognized` | JDK `bin` is not in PATH | Use the full path to `jconsole` or update PATH |
| Local process not visible | Different user, PID namespace/container, or process does not support attach | Run under the same user and in the right environment; verify PID with `jps -l` |
| Process grayed out / cannot Connect | Management agent disabled and JVM does not support dynamic attach | Check runtime, Attach API, and agent configuration |
| Local connection fails on Windows | Temporary directory does not support required ACLs | Use a filesystem supporting permissions such as NTFS and check directory permissions |
| Remote connection refused | Wrong host/port, firewall, or JMX agent not enabled | Check agent, port, RMI, and network policy |
| Remote connection authentication rejected | Incorrect username/password or access file | Verify credentials and read-only/read-write permissions |
| Some metrics unavailable | JVM/OS does not support the corresponding MXBean or extension | Consult vendor documentation and OS tools |
| High heap used without knowing which objects retain it | VM Summary only shows aggregate data | Use the Memory tab, heap dump, and heap analyzer |
| Rising CPU time without knowing which thread causes load | Process CPU time is a JVM-wide total | Use Threads, thread dumps, JFR, or a profiler |
| Total threads rising while live stays stable | Threads are created and terminated frequently | Check for thread churn and executor usage |

## 16. Limitations and Operational Notes

- VM Summary is a snapshot of metrics at the time the UI refreshes; it does not replace long-term monitoring history.
- Counters such as uptime, total threads started, total classes loaded, GC count, and GC time are typically cumulative from JVM startup.
- Peak threads is a high-water mark, not the number of currently live threads.
- Process CPU time is cumulative CPU time, not CPU percentage.
- Total compile time is cumulative JIT time, not request latency.
- Heap committed and process committed virtual memory belong to different scopes.
- OS fields are platform-dependent and may not accurately reflect container quotas if the runtime does not expose container-aware values.
- Local JConsole consumes resources; Oracle does not recommend running local JConsole in production because it can impact the monitored process. Place monitoring tools on a separate machine when appropriate.
- The MBeans tab can modify writable attributes or invoke operations; verify the impact before executing.
- VM arguments and classpath may contain sensitive information; redact before sharing.

For production, use a monitoring system/JMX exporter/APM/JFR for historical storage and alerting. JConsole is suited for live inspection, learning, and interactive diagnosis.

## 17. Checklist for Reading VM Summary

- [ ] Identified the correct JVM/PID and confirmed connection to the right application.
- [ ] Recorded VM name, vendor, version, and uptime.
- [ ] Understood Process CPU Time is cumulative CPU time.
- [ ] Understood Total Compile Time is cumulative JIT compile time.
- [ ] Distinguished Live, Peak, Daemon, and Total threads started.
- [ ] Distinguished Current classes loaded from Total classes loaded and Total classes unloaded.
- [ ] Distinguished heap used/current, committed, and maximum.
- [ ] Read collection counts and total GC time per collector.
- [ ] Distinguished heap metrics from OS/process-level memory metrics.
- [ ] Checked VM arguments, class path, and library path when needed.
- [ ] Cross-referenced anomalous metrics using specialized tabs or JMX/CLI.
- [ ] Reviewed permissions and security when using remote JMX.
- [ ] Redacted credentials, hostnames, and sensitive paths before sharing.

VM Summary is the overview screen for quickly reading JVM health: uptime, CPU/JIT, threads, classes, heap/GC, operating system, and launch configuration. Distinguish current values from cumulative counters, compare deltas across snapshots, and switch to specialized tabs when you need to find the root cause. When monitoring production, secure remote JMX, restrict access, and use a monitoring system with history to confirm trends.

## References

- Oracle, Java SE 17 Monitoring and Management Guide — Using JConsole: https://docs.oracle.com/en/java/javase/17/management/using-jconsole.html
- Oracle, Java SE 17 Monitoring and Management Guide — Monitoring and Management Using JMX: https://docs.oracle.com/en/java/javase/17/management/monitoring-and-management-using-jmx-technology.html
- Oracle, Java SE 17 API — RuntimeMXBean: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/RuntimeMXBean.html
- Oracle, Java SE 17 API — ThreadMXBean: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html
- Oracle, Java SE 17 API — ClassLoadingMXBean: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html
- Oracle, Java SE 17 API — MemoryMXBean: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html
