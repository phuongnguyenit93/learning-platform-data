# Measuring Startup, Memory, and Class Loading

The performance of a Java application is not only the time taken to handle a request. For modular applications—especially command-line tools, small services, or runtime images built with `jlink`—you should observe at least three dimensions: **startup latency**, **memory footprint**, and **class loading**.

These three dimensions are related but not interchangeable. Startup time measures how long a process takes from launch to a defined readiness milestone. Memory must distinguish heap from total process memory. Class-loading logs show which classes are loaded, from where, and when; they help explain startup and footprint, though class count alone is not a complete performance metric.

This lesson uses JDK 21 and built-in JDK tools such as `time`, `Measure-Command`, `jcmd`, `jstat`, Java Flight Recorder (JFR), and Unified Logging.

## 1. Define Exactly What to Measure

Before running benchmarks, define the measurement milestone:

- **Process startup**: from when the operating system creates the Java process until the process exits or writes its first output.
- **Application ready**: the point when the application is genuinely ready to accept work, such as an HTTP health endpoint reporting ready or the application logging `READY`.
- **First operation**: time until the first operation completes. This milestone may include post-startup lazy initialization.
- **Steady-state latency/throughput**: performance after the JVM has warmed up and the JIT compiler and caches have stabilized.

Do not use process exit time as a proxy for ready time if the application continues running in the background. For a server, measure until the readiness signal; for a CLI, you can measure until the command finishes if that is the user experience to optimize.

A measurement result should be recorded along with:

- JDK vendor and version.
- OS, CPU architecture, and core count.
- JVM configuration such as `-Xms`, `-Xmx`, GC, and key system properties.
- Classpath/module path or runtime image being used.
- Root modules and resolved modules.
- Number of runs, how median/p95 are calculated, and cold/warm conditions.
- Start/end milestones used.

## 2. Measuring Startup of a Java Process

### Measuring Time with time on Linux/macOS

For a modular application:

~~~bash
/usr/bin/time -f "elapsed=%e sec max_rss=%M KB"   java --module-path mods        --module com.acme.app/com.acme.app.Main
~~~

- `elapsed` is the wall-clock time from running the command until the process exits.
- `max_rss` is the maximum resident set size recorded by the OS, in KB on common GNU time systems.

If the application is a long-running server, the command above only prints results after the process exits. In that case, use an external measurement tool to record start and readiness times, or have the application emit a timestamped `READY` milestone.

### Measuring with PowerShell on Windows

For a CLI that exits after running:

~~~powershell
Measure-Command {
    java --module-path mods --module com.acme.app/com.acme.app.Main
}
~~~

The returned object contains `TotalMilliseconds` and time components. For a long-running server, `Measure-Command` waits for the process to exit; measure readiness with a separate script or health check instead of waiting for the server to stop.

### Running Multiple Iterations

A single run is not enough to draw conclusions. Timings can vary due to:

- OS file cache and disk cache.
- CPU frequency scaling, background load, and scheduling.
- JIT compilation or caches created by the application itself.
- DNS, database, network, or dependencies outside the JVM.
- Antivirus or filesystem scans on certain systems.

Run multiple times under equivalent conditions, record each result, and report the median along with p95 if there are enough samples. Distinguish:

- **Cold process**: each run spawns a new JVM process.
- **Warm environment**: new JVM, yet OS/file caches have been warmed by previous runs.
- **Warm JVM**: the same process has already processed substantial work. This is a different state from the startup of a fresh process.

If the goal is application startup after deploy/restart, measure cold processes following a realistic workflow. If the goal is request latency after the service stabilizes, benchmark steady state separately.

### Do Not Confuse Startup with Module Resolution

You can add:

~~~bash
java --show-module-resolution   --module-path mods   --module com.acme.app/com.acme.app.Main
~~~

This option shows root and dependency modules being resolved. It is useful for checking whether the graph pulls in unnecessary modules, but it is not a detailed startup timer. To analyze initialization time, class loading, GC, and JIT, use logs/JFR.

## 3. Measuring Memory: Heap and Process Memory

A Java application uses multiple memory regions. You cannot determine total memory from the heap alone.

### Heap Memory

The heap is the JVM memory region used for Java objects. Two common options are:

- `-Xms`: initial heap size.
- `-Xmx`: maximum heap limit.

Example:

~~~bash
java -Xms256m -Xmx1g   --module-path mods   --module com.acme.app/com.acme.app.Main
~~~

`-Xmx1g` does not mean the process always uses 1 GB of RAM. It is the maximum heap limit. Committed heap and used heap vary with allocation, GC, and JVM configuration.

### Process Memory / RSS

Process memory can include:

- Committed heap.
- Metaspace storing class metadata.
- Code cache holding machine code generated by the JIT compiler.
- Thread stacks of threads.
- Direct byte buffers and native allocations.
- Native libraries, memory mappings, and internal JVM structures.

Therefore, RSS can be significantly larger than heap used. Conversely, a large heap max does not mean all of that capacity has been physically allocated.

| Metric | Meaning | Suggested Tool |
|---|---|---|
| Heap used | Objects currently occupying the heap | `jcmd GC.heap_info`, GC logs |
| Heap committed | Heap committed by the JVM | `jcmd GC.heap_info` |
| Heap max | Heap limit | `-Xmx`, `Runtime.maxMemory()` |
| Process RSS | Total process resident memory | `/usr/bin/time -v`, OS process monitor |
| Native memory categories | Native memory groups tracked by the JVM | Native Memory Tracking |
| Metaspace | Class metadata | `jcmd GC.heap_info`, NMT |
| Class count | Number of loaded classes | Class-loading logs, `jcmd` |

## 4. Inspecting Heap with jcmd and jstat

To inspect a running JVM, find the process PID:

~~~bash
jcmd -l
~~~

Then view heap info:

~~~bash
jcmd <pid> GC.heap_info
~~~

The output shows the JVM's heap information at the sampling moment. This is a snapshot, not the peak usage across the application's entire lifetime.

You can sample GC metrics periodically with `jstat`:

~~~bash
jstat -gc <pid> 1000
~~~

The `1000` argument requests sampling every 1000 ms. The columns display capacities/usage of heap regions and GC counters depending on the JVM. Use `jstat -options` or JDK documentation to see other modes.

Useful commands:

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> GC.heap_info
jcmd <pid> VM.classloader_stats
~~~

- `VM.version`: running JVM version.
- `VM.command_line`: command line and JVM options.
- `GC.heap_info`: heap information.
- `VM.classloader_stats`: class loader statistics.

`jcmd` commands typically need to run under the same user and environment with permission to attach to the target JVM. Some container environments or security configurations may restrict attach.

## 5. Native Memory Tracking

The heap does not include all native memory. The JVM has Native Memory Tracking (NMT) to monitor certain native allocation categories managed by the JVM.

Enable NMT at launch:

~~~bash
java -XX:NativeMemoryTracking=summary   --module-path mods   --module com.acme.app/com.acme.app.Main
~~~

You can choose `detail` for more granular information, though overhead and data volume increase. NMT must be enabled at JVM startup; it cannot be enabled retroactively on an already running process.

Retrieve the report:

~~~bash
jcmd <pid> VM.native_memory summary
~~~

You can view differences between two points using a baseline:

~~~bash
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary.diff
~~~

Baseline/diff helps observe how native memory changes over time. NMT does not measure every native allocation outside the JVM and does not replace OS RSS. Use NMT together with a process monitor for a more complete view.

## 6. Measuring Class Loading with Unified Logging

Java provides Unified Logging to record class loading and unloading events.

Log class loading to console:

~~~bash
java -Xlog:class+load=info   --module-path mods   --module com.acme.app/com.acme.app.Main
~~~

Log to a file with timestamp and uptime:

~~~bash
java -Xlog:class+load=info:file=class-load.log:time,uptime,level,tags   --module-path mods   --module com.acme.app/com.acme.app.Main
~~~

Each event shows the loaded class and its corresponding source, depending on the class type and JVM. You can use the log to answer:

- Which classes are loaded during startup?
- Which module/JAR or runtime image do classes come from?
- Does a library pull in many unnecessary classes?
- Are any classes loaded from an unexpected location?

You can log both load and unload:

~~~bash
java -Xlog:class+load=info,class+unload=info   --module-path mods   --module com.acme.app/com.acme.app.Main
~~~

Class unloading occurs when a class loader and its associated classes become eligible for collection; not every class is unloaded during an application's lifetime. Classes in platform loaders or long-lived loaders typically remain until the JVM exits.

### Counting Class Loading Log Lines

On Linux/macOS, once you have the log file:

~~~bash
grep -c "class,load" class-load.log
~~~

On PowerShell:

~~~powershell
(Select-String -Path class-load.log -Pattern "class,load").Count
~~~

The number of log lines is the number of events recorded under the logging configuration, not the number of classes currently alive at the time of measurement. A class can be loaded and later unloaded; different class loaders can also load the same class name in special cases. Therefore, combine counts with class sources and classloader stats.

## 7. Using Java Flight Recorder to Inspect Startup and Class Loading

Java Flight Recorder (JFR) collects JVM events into a recording, which can be analyzed with Java Mission Control (JMC) or the `jfr` tool.

Start a recording from JVM launch:

~~~bash
java   -XX:StartFlightRecording=filename=startup.jfr,settings=profile,dumponexit=true   --module-path mods   --module com.acme.app/com.acme.app.Main
~~~

For a long-running server, you can attach and start a recording with `jcmd`:

~~~bash
jcmd <pid> JFR.start name=StartupProfile settings=profile filename=startup.jfr
~~~

Once enough data is collected:

~~~bash
jcmd <pid> JFR.stop name=StartupProfile
~~~

Print selected events as text:

~~~bash
jfr summary startup.jfr
jfr print --events jdk.ClassLoad startup.jfr
~~~

Event names and fields depend on the JDK recording configuration. In JMC, you can view the timeline, class loading, allocations, GC, thread activity, and startup-related events.

JFR is suited for identifying time-consuming or allocation-heavy activities. A `profile` recording carries some overhead; use a consistent configuration and avoid directly comparing a profiled run against an uninstrumented baseline run without noting it.

## 8. Measuring Class Loading Does Not Equal Measuring Startup

The number of loaded classes is only one part of startup. Startup time also depends on:

- Bytecode verification and linking.
- Class initialization (static initializers).
- Reflection, service discovery, and dependency injection.
- JIT compilation.
- Reading JAR/module image files and filesystem cache.
- Connecting to networks, databases, or secret/config providers.
- Framework-specific initialization work.

An application with fewer classes can still start more slowly if static initializers perform I/O or wait on the network. Conversely, many classes can be loaded quickly if most are metadata and small code.

Use class-loading logs to determine which classes are loaded and when; use JFR to find time-consuming activities; use readiness timestamps to measure the final startup outcome.

## 9. Measuring Runtime Images and Module Graphs Separately

If comparing a runtime image created with `jlink` against a full JDK, keep measurement conditions identical:

- Same application and same bytecode version.
- Same OS, CPU, JDK release, and JVM flags.
- Same root modules and service-binding policy.
- Same input data and environment configuration.
- Same readiness definition and warm/cold procedure.

You can inspect the module graph at launch:

~~~bash
runtime/bin/java --show-module-resolution   --module com.acme.app/com.acme.app.Main
~~~

To view the list of modules in the runtime image:

~~~bash
runtime/bin/java --list-modules
~~~

A smaller runtime image does not guarantee faster startup or lower RSS. Image size on disk, number of resolved modules, number of loaded classes, and process memory are different quantities. Measure each metric rather than inferring from the runtime directory size.

## 10. A Repeatable, Comparable Measurement Workflow

A practical workflow:

1. Lock down JDK, OS, CPU, JVM flags, module path, and application version.
2. Define the startup milestone, such as a `READY` log line or CLI exit time.
3. Run multiple times with fresh JVM processes; record the time of each run.
4. Record OS process RSS and take a heap snapshot with `jcmd`.
5. Run one pass with `-Xlog:class+load=info` to collect class-loading logs.
6. Run one JFR pass to identify time-consuming or allocation-heavy work.
7. If native memory analysis is needed, run with NMT enabled from the start.
8. Compare median/p95 and clearly note instrumented runs.
9. Change one factor at a time, such as root set, module path, runtime image, or JVM flags.
10. Repeat enough times under identical conditions and archive logs alongside environment metadata.

Do not add heap used, RSS, and NMT into a single total memory figure. These metrics have different measurement scopes and can overlap. Present them separately.

## 11. Tool Selection Table

| Question | Tool |
|---|---|
| How long does the CLI process take to run? | `/usr/bin/time`, PowerShell `Measure-Command` |
| How long until the server is ready? | Readiness timestamp/health check and external timer |
| How much heap is in use? | `jcmd GC.heap_info`, `jstat -gc` |
| What is the total process memory/RSS? | OS process monitor, `/usr/bin/time -v` |
| How is JVM native memory broken down by category? | `-XX:NativeMemoryTracking=summary`, `jcmd VM.native_memory` |
| Which classes are loaded and from where? | `-Xlog:class+load=info` |
| How many classes does each class loader hold? | `jcmd VM.classloader_stats` |
| What is consuming time or allocations? | JFR and JMC |
| Which modules are resolved? | `--show-module-resolution` |
| Which modules are inside the runtime image? | `--list-modules` |

## 12. Common Measurement Mistakes

**Using `-Xmx` as actual memory usage.** `-Xmx` is the heap limit, not RSS or heap used. Take snapshots with `jcmd GC.heap_info` and measure RSS from the OS.

**Measuring a server by when the launch command returns.** A server does not exit, so the timer waits forever. Measure until the readiness signal or health endpoint.

**Comparing a cold run with a warm run.** OS cache and JIT can significantly change results. Record the run type and repeat multiple times.

**Enabling all logs during the primary benchmark run.** Class-loading logs, GC logs, JFR, and NMT add overhead. Use a minimally instrumented baseline and separate diagnostic runs.

**Treating class count as performance.** Class count does not reveal whether class initialization blocks on I/O. Use JFR and timestamps to find what actually consumes time.

**Concluding the process monitor is wrong because NMT is lower than RSS.** NMT only tracks JVM-supported native allocation categories; RSS can also include memory mappings, native allocations outside NMT's scope, and other regions.

**Unable to find PID with jcmd.** Check user, container namespace, attach permissions, and whether the JVM enables the appropriate attach mechanism.

## 13. Practice Exercises

1. Run a modular CLI application with `/usr/bin/time` or `Measure-Command`; record wall-clock time.
2. Re-run at least five times with fresh JVM processes, record each result, and compute the median.
3. Launch a service and measure from process start to the readiness endpoint.
4. Add `-Xms256m -Xmx1g`; observe the heap with `jcmd GC.heap_info` and compare with RSS.
5. Enable `-XX:NativeMemoryTracking=summary`, take a baseline, and check `summary.diff` after a period of activity.
6. Enable `-Xlog:class+load=info`, count class load events, and inspect the sources of key classes.
7. Create a JFR recording from startup; use `jfr summary` and JMC to find time-consuming events.
8. Compare a full JDK and a `jlink` runtime image under identical conditions; separately record startup, heap, RSS, class count, and the module graph.

To evaluate a modular Java application, measure the right quantities at the right milestones. Startup needs readiness or process timing; memory requires separating heap, native memory, and RSS; class loading needs logs or JFR to understand which classes are loaded and their impact. Combining these sources with module resolution lets you pinpoint which modules or dependencies affect startup and footprint rather than guessing solely from module count or runtime image size.
