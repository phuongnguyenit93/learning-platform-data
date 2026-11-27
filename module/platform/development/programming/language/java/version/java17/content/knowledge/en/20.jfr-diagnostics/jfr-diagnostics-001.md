# Reproducing Incidents and Collecting JDK, OS, and Load Information in Java 17

When a Java application fails only on a specific machine, only under high load, or only after running for several hours, error logs are usually not enough to find the root cause. To diagnose with solid evidence, you need to **reproduce the incident using a repeatable scenario** and collect data from the exact process experiencing the problem: the actual JDK build, JVM options, operating system, resource limits, load characteristics, and Java Flight Recorder (JFR) recordings.

General workflow:

1. Describe the symptoms and record the reproduction conditions.
2. Identify the exact PID and JDK used by the process.
3. Collect OS, CPU, memory, container, and application load information.
4. Record a timeline with unified timestamps.
5. Collect JFR recordings, thread dumps, GC logs, or other appropriate supplementary data.
6. Package the evidence bundle so it can be analyzed and compared against subsequent reproductions.

This lesson uses built-in JDK 17 tools such as `java`, `jcmd`, `jfr`, and JFR. Operating system commands are split between Linux and Windows. The goal is to produce a complete set of information so others can understand the environment, load, and timing of the incident without guessing.

## 1. What Does Reproducing an Incident Mean?

Reproducing an incident means re-running the application under conditions close enough for the error to appear in an observable and recordable way. A report like “the server is sometimes slow” is not a reproduction scenario. It must be turned into measurable conditions.

For example, instead of simply writing:

```text
The application occasionally responds slowly.
```

Describe it specifically:

```text
- Application: billing-service, build 2.8.4.
- Runtime: Eclipse Temurin JDK 17.0.x, Linux x86_64.
- Incident: p99 latency increased from ~180 ms to over 4 s.
- Conditions: 350 requests/second, ~220 concurrent requests.
- Timing: after 12–18 minutes of continuous load.
- Impact: invoice read requests slow down; database timeouts increase.
- How to re-run: same test dataset, same pool configuration, same load profile for 20 minutes.
- Accompanying signs: high process CPU, increased thread count, GC pauses near the time latency spikes.
```

This description helps others recreate the load and know whether to observe CPU, threads, GC, or the database.

### 1.1. Distinguishing Symptoms, Causes, and Triggers

| Concept | Example |
|---|---|
| Symptom | Slow request responses, process exit, `OutOfMemoryError` |
| Trigger | Increased load, large payload, cold cache, a specific node |
| Hypothesized cause | Thread pool exhaustion, lock contention, GC pressure, slow I/O |
| Evidence to collect | JFR, thread dump, GC log, OS metrics, request rate |
| Reproduction result | Incident reoccurs under the same conditions, or disappears after a controlled change |

Do not record a hypothesis as a conclusion without evidence. High CPU can be the cause of latency, but it can also be the consequence of a retry storm or an unusual workload.

### 1.2. Clearly Stating Expected and Actual Behavior

Each scenario should have two parts:

- **Expected:** what the system is expected to do, and within what limits.
- **Actual:** what happened, at what time, on which node, and to what extent.

Example:

```text
Expected:
  p95 latency < 500 ms at a load of 300 requests/second.

Actual:
  p95 = 2.1 s, p99 = 6.8 s from 10:42:15Z to 10:45:30Z.
  Node app-03 had an average process CPU of 92%.
  Request timeouts increased from 0.1% to 8%.
```

Use the same units of measurement, the same time window, and the same percentile definitions across comparisons.

## 2. Creating a Repeatable Reproduction Scenario

A good scenario controls the variables that affect the outcome. You do not necessarily have to recreate all of production right away; start with the smallest case that still makes the error appear.

### 2.1. Recording Inputs and Initial State

Collect:

- The payload or input dataset that triggered the error.
- Record count, payload size, and data distribution.
- Application configuration, thread pools, connection pools, caches, and timeouts.
- Cache state: cold or warm.
- State of the database, queues, and dependent services.
- Random seed if the program or test uses randomness.
- Timestamp, timezone, and locale if logic depends on calendar/time.
- Number of runs before the error appears and elapsed time from startup to failure.

If the data contains personal information, tokens, or secrets, create an anonymized dataset that still preserves the necessary size and distribution characteristics. Do not copy raw production data into shared environments solely for reproduction.

### 2.2. Holding Variables Constant When Comparing

When testing a change, change only one relevant factor per run:

- Same build, change worker count.
- Same load, change heap limit.
- Same JVM configuration, change JDK patch version.
- Same data, change cache configuration.

If you change the JDK, heap, thread pool, and database simultaneously, a better or worse result will not tell you which change made the difference.

### 2.3. Distinguishing Deterministic vs. Intermittent Failures

- **Deterministic errors:** appear after the exact same input or sequence of operations. Reduce the scenario to a small test, capturing the stack trace and minimal input.
- **Load-dependent errors:** only appear when concurrency, throughput, or queue depth is high enough. Use a load generator and record the load profile.
- **Time-dependent errors:** appear after running for a period of time, after a batch cycle, when a cache fills up, or when a token expires. Record uptime and accumulated state.
- **Environment-specific errors:** only occur on a specific OS, container, filesystem, CPU architecture, or JDK build. Compare actual environments rather than just comparing source code.

### 2.4. Describing the Load Profile

A load profile is not just “send 500 requests.” Record:

| Attribute | Example |
|---|---|
| Warm-up | 2 minutes at 50 requests/second |
| Steady load | 10 minutes at 250 requests/second |
| Burst | Increase to 500 requests/second for 60 seconds |
| Concurrency | 100, 200, or 400 concurrent requests |
| Payload | Median 4 KB, p95 80 KB |
| Operation mix | 70% read, 20% update, 10% report |
| Think time | 100 ms between operations per virtual user |
| Measurements | Throughput, p50/p95/p99 latency, error rate, queue depth |

Use the same load profile for both the baseline run and the incident run. If the load generator itself becomes a bottleneck, the measurements no longer reflect the Java application alone.

## 3. Identifying the Exact Java Process

Before collecting information, you must identify the **PID of the exact process running the application**. A single machine may host multiple JDKs, multiple Java services, and multiple processes across containers.

### 3.1. Finding the Process with jcmd

In the JDK's `bin` directory:

```bash
jcmd -l
```

This command lists the Java processes that the attach tool can detect, typically showing the PID and the main class or JAR name.

Example:

```text
18420 com.example.billing.Main
20731 org.apache.catalina.startup.Bootstrap
```

Select the PID of the service to diagnose. Do not confuse it with the PID of a load generator, an agent, or another service.

If `jcmd -l` does not show the process, it may be running under a different user, inside a different container/PID namespace, with the attach mechanism disabled, due to insufficient permissions, or the process may have already exited.

### 3.2. Checking the PID on Linux

```bash
ps -ef | grep '[j]ava'
ps -p 18420 -o pid,ppid,user,etime,%cpu,%mem,rss,vsz,args
```

`ps` shows the user, elapsed runtime, CPU, memory, and command line. The command line may contain passwords or tokens passed as arguments; redact sensitive data before sharing.

### 3.3. Checking the PID on Windows PowerShell

```powershell
$javaPid = 18420

Get-CimInstance Win32_Process -Filter "ProcessId = $javaPid" |
    Select-Object ProcessId, ParentProcessId, ExecutablePath, CommandLine

Get-Process -Id $javaPid |
    Select-Object Id, ProcessName, CPU, WorkingSet64, VirtualMemorySize64,
                  Threads, Handles, StartTime
```

`WorkingSet64` is the physical memory used by the process from Windows' perspective; `VirtualMemorySize64` is the virtual address space. They are not equivalent to used heap inside the JVM.

## 4. Collecting the Exact JDK Version of the Process

Running `java -version` in a terminal only reports the Java launcher found via `PATH`. It may differ from the JDK running the service, especially when the service is started by systemd, a Windows Service, a container, or a custom script.

### 4.1. Checking the Launcher in the Current Environment

Linux/macOS:

```bash
command -v java
command -v jcmd
command -v jfr
java -version
javac -version
```

Windows PowerShell:

```powershell
Get-Command java, javac, jcmd, jfr -ErrorAction SilentlyContinue |
    Select-Object Name, Source

java -version
javac -version
```

Record the executable paths as well. Two machines both reporting “Java 17” may still differ in vendor, patch release, build, or JVM options.

### 4.2. Checking the Version from the Running Process

Using the identified PID:

```bash
jcmd 18420 VM.version
jcmd 18420 VM.command_line
jcmd 18420 VM.flags
```

Meaning:

- `VM.version`: the actual VM version.
- `VM.command_line`: the launch command and JVM/application arguments received by the VM.
- `VM.flags`: the active VM flags, including many default flags and explicitly set flags.

This data is far more reliable than simply asking the shell which Java it uses.

### 4.3. Collecting JVM System Properties

```bash
jcmd 18420 VM.system_properties
```

Useful properties for identifying the environment include:

- `java.version`, `java.runtime.version`.
- `java.vendor`, `java.vm.name`, `java.vm.version`.
- `java.home`, `java.class.path`.
- `os.name`, `os.version`, `os.arch`.
- `user.timezone`, `file.encoding`.
- `user.dir`.

However, `VM.system_properties` may contain custom application properties, including internal URLs, file paths, usernames, or secrets. Do not share the raw output without reviewing and redacting sensitive values.

### 4.4. Collecting Information from Inside the Application

If you can add a diagnostic endpoint or startup log, you can record selected details:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.RuntimeMXBean;

public final class RuntimeInfo {
    public static void print() {
        RuntimeMXBean runtime =
                ManagementFactory.getRuntimeMXBean();

        System.out.println("java.version="
                + System.getProperty("java.version"));
        System.out.println("java.runtime.version="
                + System.getProperty("java.runtime.version"));
        System.out.println("java.vendor="
                + System.getProperty("java.vendor"));
        System.out.println("java.vm.name="
                + System.getProperty("java.vm.name"));
        System.out.println("java.vm.version="
                + System.getProperty("java.vm.version"));

        System.out.println("os.name="
                + System.getProperty("os.name"));
        System.out.println("os.version="
                + System.getProperty("os.version"));
        System.out.println("os.arch="
                + System.getProperty("os.arch"));

        System.out.println("processors="
                + Runtime.getRuntime().availableProcessors());
        System.out.println("jvm.startTime="
                + runtime.getStartTime());
        System.out.println("jvm.uptimeMillis="
                + runtime.getUptime());
        System.out.println("jvm.inputArguments="
                + runtime.getInputArguments());
    }
}
```

`RuntimeMXBean.getInputArguments()` is useful for recording JVM arguments, though it may contain sensitive values. For public endpoints, only return allow-listed properties and do not expose the full command line.

### 4.5. Do Not Confuse JDK Version with Source/Target Version

An application may be compiled with `--release 17` yet run on a different JDK 17 patch or a different runtime if the deployment configuration allows it. When reporting an incident, record separately:

- The JDK/compiler used to build.
- The actual runtime JDK of the process.
- Application version/build commit.
- Relevant JVM flags and module/class path.

## 5. Collecting Operating System Information

The JDK, JVM, and OS all influence how the application uses CPU, memory, threads, file descriptors, network, and filesystem. Simply noting “Linux” or “Windows” is not enough.

### 5.1. Linux: Basic System Information

```bash
date -u +"%Y-%m-%dT%H:%M:%SZ"
uname -a
cat /etc/os-release
lscpu
free -h
uptime
df -h
```

| Command | Information |
|---|---|
| `date -u` | UTC time for timeline synchronization |
| `uname -a` | Kernel, hostname, architecture |
| `/etc/os-release` | Distribution and version |
| `lscpu` | CPU model, cores, threads, architecture |
| `free -h` | Total, used, available memory, swap |
| `uptime` | Uptime and load average |
| `df -h` | Filesystem capacity and mount points |

If `lscpu` is unavailable, you can use `cat /proc/cpuinfo`; the output is longer and requires appropriate filtering.

### 5.2. Linux: Observing Load Over a Time Interval

```bash
vmstat 1 10
pidstat -p 18420 1 10
iostat -xz 1 10
```

- `vmstat` provides system-level CPU, run queue, memory, swap, and I/O statistics.
- `pidstat` provides periodic CPU and process-level statistics.
- `iostat` shows storage device activity, latency, and utilization.

`pidstat` and `iostat` usually belong to the `sysstat` package. If they are not installed in the environment, explicitly note that the tools are missing rather than silently omitting the data.

To view per-thread statistics:

```bash
pidstat -t -p 18420 1 10
```

### 5.3. Linux: Process Limits

```bash
cat /proc/18420/status
cat /proc/18420/limits
ls /proc/18420/fd | wc -l
```

`/proc/<pid>/status` provides process details such as thread count, state, memory, and counters. `/proc/<pid>/limits` displays resource limits such as open files and process count. The number of open file descriptors can hint at socket or file handle leaks; this is only a snapshot at the time of collection.

### 5.4. Windows: Basic System Information

In PowerShell:

```powershell
Get-Date -Format o
Get-TimeZone

Get-ComputerInfo |
    Select-Object WindowsProductName, WindowsVersion,
                  OsBuildNumber, OsArchitecture, CsSystemType

Get-CimInstance Win32_Processor |
    Select-Object Name, NumberOfCores, NumberOfLogicalProcessors

Get-CimInstance Win32_OperatingSystem |
    Select-Object Caption, Version, BuildNumber,
                  TotalVisibleMemorySize, FreePhysicalMemory
```

These commands capture the time, timezone, Windows version/build, architecture, CPU, and system memory.

### 5.5. Windows: Observing Load and Process

```powershell
$javaPid = 18420

Get-Process -Id $javaPid |
    Select-Object Id, ProcessName, CPU, WorkingSet64,
                  VirtualMemorySize64, Threads, Handles, StartTime

Get-Counter -Counter @(
    '\Processor(_Total)\% Processor Time',
    '\Memory\Available MBytes'
) -SampleInterval 1 -MaxSamples 10
```

`Get-Process` provides a process snapshot. `Get-Counter` samples performance counters over time. Counter names may differ on localized Windows installations; if a counter does not exist, record the appropriate name on that machine.

### 5.6. Operating System and CPU Architecture

Be sure to record CPU architecture and logical processor count, kernel/OS build, physical memory, swap/page file, relevant filesystems and mounts, process limits and permissions of the user running Java, and virtualization or container environments if present.

Do not assume two machines with “the same 8 cores” have identical performance. Different CPU models, quotas, clock behaviors, virtualization, and workloads can produce very different results.

## 6. Collecting Container Limits and Actual Resources

In containers, the CPU and memory visible to the JVM may be restricted by cgroups or the runtime. Host hardware specifications are not necessarily the resources allocated to the container.

### 6.1. Docker and Kubernetes

If you have Docker access:

```bash
docker stats --no-stream <container>
docker inspect <container>
```

`docker stats` gives a snapshot of CPU, memory, network, and block I/O. `docker inspect` may contain sensitive configuration; filter the output before sharing.

For Kubernetes:

```bash
kubectl top pod -n <namespace>
kubectl describe pod <pod-name> -n <namespace>
```

`kubectl top` depends on the Metrics Server. `describe` provides requests/limits, restart status, events, and node placement. Do not include tokens or kubeconfig in the evidence bundle.

### 6.2. Cgroup v2 on Linux

On many modern Linux systems, cgroup v2 uses files such as:

```bash
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpu.stat
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.events
```

General meaning:

- `cpu.max`: the cgroup's CPU quota and period.
- `cpu.stat`: CPU time and throttling statistics.
- `memory.max`: memory limit.
- `memory.current`: memory currently in use.
- `memory.events`: counts of cgroup events such as high/max/oom.

The actual cgroup path may differ if the process is inside a child cgroup or the system uses a different layout. Read `/proc/<pid>/cgroup` to determine the process's cgroup location.

### 6.3. Cgroup v1 and Container Limits

Cgroup v1 separates controllers into distinct hierarchies. Paths typically reside under `/sys/fs/cgroup/cpu`, `/sys/fs/cgroup/memory`, or custom mounts depending on configuration. Do not apply v2 filenames like `cpu.max` to v1.

Record the cgroup version and exact paths. Do not compare host CPU count with container quota as if they were the same quantity.

JVM 17 can detect container resource limits on supported platforms, but runtime configuration, cgroups, and deployment environments still need to be verified. A process may see fewer CPUs than the host, experience throttling even while the host has idle CPU, or be killed by the OOM killer due to container limits.

When investigating memory pressure, record both JVM heap and container memory. Free heap space does not guarantee the container has enough memory left for metaspace, code cache, thread stacks, direct buffers, and native allocations.

## 7. Collecting Application Load Information

OS metrics tell you how busy the machine is; application metrics tell you what users and workloads are requesting. Both are needed to distinguish legitimate load from a bottleneck.

### 7.1. Throughput, Concurrency, and Latency

Record at least requests/operations per second, concurrent request count, p50/p95/p99 latency, error/timeout rate, retry count, request/response sizes, and the breakdown by endpoint or task type.

Do not rely solely on average latency. The average can remain low even when a small percentage of requests hang for several seconds; p95/p99 usually exposes tail latency.

### 7.2. Queues and Pools

| Component | Metrics to Collect |
|---|---|
| Executor | Active threads, pool size, queue size, rejected tasks |
| HTTP server | Active requests, connection count, pending requests |
| Database pool | Active/idle connections, waiters, acquisition timeout |
| Message broker | Consumer lag, queue depth, redelivery, processing rate |
| Cache | Hit/miss ratio, eviction, load latency |
| Scheduler | Task duration, lateness, pending task count |

A full thread pool can drive up latency even when CPU is low, because threads are waiting on the database, network, locks, or queues.

### 7.3. JVM CPU and Memory

Collect process CPU and system CPU, heap used/committed/max, GC count and pause time, allocation rate if available, thread count and thread states, metaspace/direct buffer/native memory when relevant, and class loading/unloading if there are signs of metaspace growth.

`Runtime.getRuntime().availableProcessors()` reports the number of processors detected by the JVM; it is not a measure of CPU utilization. Compare it against container quotas and OS metrics to understand actual limits.

### 7.4. Specifying Measurement Windows and Metric Sources

A metric like “CPU = 90%” is insufficient without knowing whether it is process or host CPU, over what duration it was measured, whether it is an average or peak, how many cores are allocated, and whether CPU throttling occurred. Attach a UTC timestamp and interval to every metric file. Use the same interval in baseline and reproduction runs for comparison.

## 8. Using jcmd to Collect JVM State

`jcmd` is a diagnostic tool bundled with the JDK. It sends diagnostic commands to a running JVM. Use JDK tools from the same environment and with permissions matching the target process.

### 8.1. Confirming Version and Launch Command

```bash
jcmd 18420 VM.version
jcmd 18420 VM.command_line
jcmd 18420 VM.flags
jcmd 18420 VM.system_properties
```

`VM.system_properties` may expose secrets. Store only a reviewed, redacted version in shared bundles.

### 8.2. Capturing Thread Dumps

```bash
jcmd 18420 Thread.print -l
```

A thread dump shows stack traces and thread states at a single point in time. It is useful when many threads are `BLOCKED` on the same monitor, a thread pool has no idle workers left, many threads are `WAITING`/`PARKED`, there are signs of a deadlock, or threads are stuck in I/O or external service calls.

A single thread dump is a snapshot, not a timeline. For intermittent issues, capture several snapshots spaced closely apart and compare stacks/states; JFR supplements this with time-series data.

### 8.3. Viewing Heap Summary

```bash
jcmd 18420 GC.heap_info
```

This command provides a high-level overview of the heap at the time of sampling. It does not replace a heap profiler and does not fully identify which objects are retaining memory.

`GC.class_histogram` can be useful when you need to see which object types occupy the most heap, but it can take time or cause impact because it inspects the heap at a safepoint. Only use it with good reason after weighing the impact on a system serving live traffic.

Do not automatically take a heap dump in every incident. Heap dumps can be huge, generate significant I/O, and contain sensitive application data.

### 8.4. Native Memory Tracking

If the JVM was launched with Native Memory Tracking enabled, you can capture a summary:

```bash
jcmd 18420 VM.native_memory summary
```

NMT must be enabled at startup, for example:

```bash
-XX:NativeMemoryTracking=summary
```

Full NMT cannot be enabled retroactively on a running process that was not started with this option. NMT has overhead; only enable it when investigating native memory and plan to measure its impact.

## 9. Java Flight Recorder in JDK 17

**Java Flight Recorder (JFR)** is the JVM's performance and runtime event recording system. It captures timestamped events such as CPU sampling, GC, thread scheduling, lock contention, allocation sampling, and I/O.

JFR is built into JDK 17 and can be used for production diagnostics with appropriate configuration. Legacy commercial unlock flags are not needed to use JFR in Java 17.

JFR has two main concepts: a **Recording** is a collection of events recorded over a period of time; an **Event** is an occurrence with a timestamp, data fields, and sometimes a stack trace.

JFR helps answer which threads/code paths are consuming CPU, when GC happens, where threads are parking or waiting on monitors, whether allocation pressure is spiking abnormally, and whether file/socket I/O has unusual latency.

### 9.1. How JFR Differs from Application Logs

| Application Logs | JFR |
|---|---|
| Records business events explicitly logged by the application | Records JVM and runtime events |
| Often includes request IDs and business context if added by the app | Includes timestamps, threads, stacks, and runtime metrics depending on the event |
| Useful for knowing what action a user performed | Useful for knowing what the JVM was doing during the same period |
| Can be missing if the code didn't log it | Does not inherently understand the business meaning of a request |

The two data sources complement each other. Keep request IDs/correlation IDs in application logs and record UTC timestamps to correlate with JFR.

### 9.2. default and profile Settings

JFR provides standard recording configurations:

- `default`: lower-overhead configuration suitable for longer recordings or continuous observation.
- `profile`: captures more detail, useful for short-duration investigations; may introduce higher overhead and larger output files.

Do not default to running `profile` forever on every process. Choose settings based on the questions you need to answer, the recording duration, and your overhead budget.

## 10. Starting JFR from a Running JVM with jcmd

This is convenient when an incident is already occurring or you need to enable recording on a live process.

### 10.1. Checking Existing Recordings

```bash
jcmd 18420 JFR.check
```

This command displays active recordings and their status.

### 10.2. Starting a Short Recording

```bash
jcmd 18420 JFR.start name=incident settings=profile duration=10m filename=/var/tmp/incident.jfr
```

| Parameter | Meaning |
|---|---|
| `name=incident` | Recording name for referencing via jcmd |
| `settings=profile` | Use JFR's profile configuration |
| `duration=10m` | Automatically stop the recording after 10 minutes |
| `filename=...` | Output file path written when the recording ends |

The path must be writable by the user running the JVM. On Windows, use an appropriate path, such as `C:/temp/incident.jfr`.

### 10.3. Verifying the Recording Started

```bash
jcmd 18420 JFR.check
```

If the recording does not appear, check the message returned by `jcmd`, attach permissions, disk space, and the file path.

### 10.4. Dumping Before the Recording Auto-Stops

If a recording is still running and you want a snapshot at the moment of an incident:

```bash
jcmd 18420 JFR.dump name=incident filename=/var/tmp/incident-now.jfr
```

Dumping creates a recording file at the time of the call; the original recording can continue running.

Once enough data has been collected, stop the recording:

```bash
jcmd 18420 JFR.stop name=incident
```

If a recording is configured to stop after a `duration`, you do not have to wait for it to expire if you already have sufficient data; stopping intentionally reduces collection time and file size.

### 10.5. Long-Running Recording with Rolling Data

For processes requiring longer observation, use a disk recording with age and size limits:

```bash
jcmd 18420 JFR.start name=continuous settings=default disk=true maxage=2h maxsize=512m dumponexit=true
```

When an incident occurs:

```bash
jcmd 18420 JFR.dump name=continuous filename=/var/tmp/incident-window.jfr
```

The continuous recording keeps running after the dump. When no longer needed:

```bash
jcmd 18420 JFR.stop name=continuous
```

`maxage` and `maxsize` cap the age and size of retained recording data, preventing unbounded file growth. Choose limits appropriate for your event generation rate and available disk space.

## 11. Starting JFR at JVM Startup

If the incident occurs during startup or before an operator can attach, configure the recording via JVM arguments.

```bash
java \
  -XX:StartFlightRecording=name=startup,settings=profile,duration=10m,filename=/var/tmp/startup.jfr \
  -jar application.jar
```

JFR starts from the VM startup phase according to the configuration. This works well for early failures, startup latency, class loading issues, or race conditions that only happen during initialization.

You can use `default` settings to reduce detail and overhead:

```bash
java -XX:StartFlightRecording=name=baseline,settings=default,dumponexit=true \
     -jar application.jar
```

With `dumponexit=true`, the recording is dumped when the JVM exits normally. Do not rely on it as a guarantee that the file will be created if the process is forcibly killed or the machine loses power.

### 11.1. Choosing a Recording Method by Incident Type

| Incident | Appropriate Recording Method |
|---|---|
| Error occurs right at startup | `-XX:StartFlightRecording` |
| Error already occurring on a running process | `jcmd JFR.start` |
| Rare error, need to retain a recent window | Continuous disk recording with `maxage`/`maxsize` |
| Only need to investigate for 5–10 minutes | Short recording with `settings=profile` |
| Need low-detail baseline over a long period | `settings=default` |

### 11.2. Do Not Restart Before Collecting Evidence Unless Necessary

Restarting can wipe out thread state at the time of a hang, heap state, active recordings, queue/connection state, and the context leading up to the failure.

If the process is safe to observe, capture the necessary snapshots before restarting. If the system is causing severe impact or risking data integrity, prioritize your organization's approved operational and recovery procedures.

## 12. Reading and Analyzing JFR Files

Once you have a `.jfr` file, the JDK provides the `jfr` tool to view summaries and print events.

### 12.1. Viewing the Recording Summary

```bash
jfr summary /var/tmp/incident.jfr
```

The summary displays start/end times, total duration, and event counts by type. Use `summary` to verify the file contains data and to see what time span the recording covers.

### 12.2. Printing CPU and GC Events

```bash
jfr print --events jdk.CPULoad,jdk.ThreadCPULoad,jdk.ExecutionSample,jdk.GarbageCollection,jdk.GCHeapSummary /var/tmp/incident.jfr
```

These events help identify CPU load, sampled stacks, GC times, and heap summaries around GC. Whether specific events are present depends on settings and runtime. If an event is missing, check the recording configuration rather than concluding the event never occurred.

### 12.3. Viewing Execution Sample Stacks

```bash
jfr print --events jdk.ExecutionSample --stack-depth 64 /var/tmp/incident.jfr
```

Execution samples are sampled data, not a trace of every method call. A method appearing frequently in samples may be consuming CPU, but you need to read the stack context and correlate with load before drawing conclusions.

### 12.4. Viewing Locks, Threads, and I/O

```bash
jfr print --events jdk.JavaMonitorEnter,jdk.ThreadPark,jdk.SocketRead,jdk.SocketWrite,jdk.FileRead,jdk.FileWrite /var/tmp/incident.jfr
```

These events are helpful when the application has low CPU usage yet remains slow:

- `jdk.JavaMonitorEnter`: wait time for monitor contention.
- `jdk.ThreadPark`: thread parking, often related to locks, synchronizers, or executors.
- `jdk.SocketRead`/`jdk.SocketWrite`: socket operations.
- `jdk.FileRead`/`jdk.FileWrite`: file I/O operations.

Not every read/write is recorded in every configuration. Events have their own thresholds and settings; check the recording configuration if expected data does not appear.

### 12.5. Viewing Allocation Samples

```bash
jfr print --events jdk.ObjectAllocationSample /var/tmp/incident.jfr
```

Allocation samples can highlight code paths creating many objects. This is sampled data, not an exact list of every allocation. Use it to guide investigation and cross-check against heap/GC metrics.

### 12.6. Using Java Mission Control

Java Mission Control (JMC) can open JFR files and present data across views such as JVM overview, threads, memory, garbage collections, locks, and I/O. It is a visual analysis tool; the underlying artifact remains the JFR recording.

When sharing results, keep the original recording file and record the JDK/JMC version used for analysis. If recipients do not have JMC, `jfr summary` and `jfr print` still allow extracting text-based details.

## 13. Collecting GC Logs and Combining with JFR

JFR records many GC events, but GC logs remain valuable when you need a detailed log stream that easily integrates into centralized logging systems.

Java 17 uses Unified Logging:

```bash
-Xlog:gc*,safepoint:file=/var/log/app/gc.log:time,uptime,level,tags:filecount=5,filesize=20m
```

Meaning:

- `gc*`: tag group related to garbage collection.
- `safepoint`: safepoint information.
- `time,uptime,level,tags`: decorators written to each log line.
- `filecount=5`: retain up to 5 rotated files.
- `filesize=20m`: target size per file before rotation.

Add this argument to the process's JVM options. Confirm the log directory exists and the JVM user has write permissions.

### 13.1. Reading GC Logs Alongside the Timeline

Correlate the moment latency increases with GC pause start/end times, heap occupancy before/after GC, GC frequency, safepoint duration, and allocation rate.

A long GC pause coinciding with a latency spike is notable evidence, but you must examine the entire sequence and load. Not every latency spike is caused by GC.

### 13.2. Heap and Native Memory Are Separate Scopes

The heap is only part of a process's memory. Total memory can also include metaspace, code cache, thread stacks, direct buffers, JNI/native allocations, JIT/compiler memory, and memory-mapped files.

If a container hits OOM while heap usage has not reached `-Xmx`, inspect OS/cgroup memory and native memory instead of simply increasing the heap.

## 14. Choosing Evidence by Symptom

Not every incident requires every type of recording. Start from the symptom and select the relevant data.

| Symptom | Priority Data | Questions to Answer |
|---|---|---|
| High process CPU | JFR execution samples, thread CPU, OS per-process CPU | Which thread/code path is consuming CPU? |
| Low CPU but high latency | Thread dumps, ThreadPark, JavaMonitorEnter, socket/file I/O | Are threads waiting on locks, network, or disk? |
| Latency increasing over time | JFR, GC logs, heap/queue metrics | Is there GC pressure, queue buildup, or a memory leak? |
| Heap OOM | JFR allocations, heap metrics, heap dump if needed | Which objects are growing and what holds references to them? |
| Container OOM kill | Cgroup memory events, container stats, heap/native metrics | Where did total process memory exceed the limit? |
| Increasing thread count | JFR thread events, thread dumps, pool metrics | Where are threads created and why aren't they terminating? |
| Slow startup | Startup JFR, class loading, application startup logs | Is time spent in class loading, I/O, or initialization? |
| Database timeouts | Application metrics, pool wait, socket events, thread dumps | Waiting on connections, queries, or the network? |
| Slow file I/O | JFR file events, iostat, filesystem metrics | Is the latency in the JVM, filesystem, or storage device? |

A heap dump may be necessary when investigating retained objects or leaks, but it is typically large and carries operational impact. Only generate one when you have a plan for storage, analysis, and data protection.

## 15. Creating a Unified Timeline

To correlate JFR, application logs, GC logs, and OS metrics, timestamps must be comparable.

### 15.1. Using UTC for Incident Timestamps

Record times in ISO-8601 UTC format:

```text
2026-11-15T10:42:15.123Z
```

If application logs use local time, note the timezone/offset and verify that host clocks are synchronized. Do not compare two local timestamps from different machines while ignoring timezone or clock skew.

### 15.2. Recording Markers at the Start and End of a Scenario

```text
10:30:00Z - service restarted
10:32:00Z - warm-up begins
10:34:00Z - steady load begins (250 req/s)
10:42:15Z - p99 latency exceeds threshold
10:42:20Z - JFR dump requested
10:43:00Z - thread dump captured
10:45:00Z - load stopped
10:46:00Z - JFR recording stopped
```

Markers help analysts locate the exact window inside a recording. If possible, log a shared incident ID/correlation ID in both application logs and monitoring systems.

### 15.3. Recording Snapshot Capture Times

Example on Linux:

```bash
date -u +"%Y-%m-%dT%H:%M:%SZ"
jcmd 18420 Thread.print -l > thread-18420.txt
date -u +"%Y-%m-%dT%H:%M:%SZ"
```

On PowerShell:

```powershell
Get-Date -Format o
jcmd 18420 Thread.print -l | Out-File -Encoding utf8 thread-18420.txt
Get-Date -Format o
```

Record the command, PID, host/container, and executing user. A thread dump without a timestamp and PID is very hard to align with JFR.

## 16. Packaging the Evidence Bundle

A structured bundle allows others to analyze the incident without repeatedly asking for missing details.

Example:

```text
incident-2026-11-15/
├── README.md
├── reproduction/
│   ├── scenario.md
│   ├── input-sample-redacted.json
│   └── load-profile.csv
├── jdk/
│   ├── java-version.txt
│   ├── vm-version.txt
│   ├── vm-command-line-redacted.txt
│   └── vm-flags.txt
├── os/
│   ├── os-release.txt
│   ├── cpu-memory.txt
│   ├── process-snapshot.txt
│   └── cgroup-limits.txt
├── application/
│   ├── application.log
│   └── metrics.csv
├── jfr/
│   ├── incident.jfr
│   └── jfr-summary.txt
├── gc/
│   └── gc.log
└── threads/
    ├── thread-before.txt
    └── thread-during.txt
```

Not every incident needs every single file. Keep only relevant evidence and explicitly note which files could not be collected.

### 16.1. Evidence Bundle README

You can use this template:

```text
Incident ID:
Service / version / commit:
Host / container / pod:
PID:
JDK vendor / runtime version:
OS / kernel / architecture:
JVM flags:
Heap settings:
Container CPU / memory limits:
Start time (UTC):
Incident window (UTC):
Reproduction steps:
Load profile:
Expected behavior:
Actual behavior:
Error rate / p95 / p99:
Files collected:
Known limitations:
Sensitive fields redacted:
```

The README serves as an index and context for the raw data. Never embed tokens, passwords, or secrets in the README.

### 16.2. Checking File Size and Checksum

Linux:

```bash
ls -lh incident.jfr
sha256sum incident.jfr
```

Windows PowerShell:

```powershell
Get-Item .\incident.jfr |
    Select-Object Name, Length, LastWriteTimeUtc

Get-FileHash .\incident.jfr -Algorithm SHA256
```

A checksum verifies file integrity when transferring across storage systems; it does not encrypt or secure the file's contents.

## 17. Common Issues When Collecting JFR and Diagnostics

### 17.1. jcmd Fails to Attach

Possible causes: running under a different user, PID is outside the namespace visible to the command, process has already exited, attach mechanism is disabled, or tools are from an incompatible environment.

How to resolve:

1. Verify the PID and user.
2. Run `jcmd -l` on the same host/container.
3. Use JDK tools matching the process's runtime.
4. If attach is not feasible, consider a startup recording via JVM options on the next restart.

Do not attempt to enable the attach mechanism by making ad-hoc changes on a running production instance.

### 17.2. JFR File Not Found

Check whether the path is absolute or relative, write permissions of the JVM user, disk space, recording status, and output messages from `JFR.dump`/`JFR.stop`. Use absolute paths to avoid confusing the process's working directory with your current terminal directory.

### 17.3. JFR File Exists but Lacks Expected Events

The recording may use settings that do not enable the desired events, or the events may have thresholds. Check the recording configuration, use `profile` settings during a controlled window, or create a custom JFR configuration.

Do not conclude “there is no lock contention” merely because no lock events appear in a recording where the appropriate events were not enabled.

### 17.4. Recording Increases Overhead

If a recording runs too long, uses overly detailed settings, or captures stack traces at high frequency, it can increase CPU, I/O, and storage usage.

Ways to reduce impact:

- Use `default` for long-term observation.
- Use `profile` for short investigation windows.
- Cap `duration`, `maxage`, and `maxsize`.
- Enable detailed events only when required by the diagnostic question.
- Monitor CPU and disk while recording.

There is no single overhead number valid for every application; it depends on events, load, and hardware. Measure in a production-like environment if you need to assess impact.

### 17.5. JFR or Logs Contain Sensitive Data

Recordings and diagnostic outputs may contain stack traces, internal class names, file paths, hostnames, endpoints, socket/I/O details, thread names, and application-defined properties or command-line arguments.

Restrict access permissions, store securely, set retention limits, and redact before sharing externally. Never upload production JFR files to public locations.

## 18. Example Workflow: Investigating Increasing Latency Under Load

Suppose a Java 17 service exhibits increasing latency after several minutes of sustained load.

### Step 1 — Record the Baseline

```text
JDK: vendor + runtime version + VM version
OS: distribution/build + kernel + architecture
CPU: model + logical processors
Memory: host/container limit
JVM: command line + flags + Xms/Xmx
Application: build + config + dependency versions
Load: request rate + concurrency + payload distribution
Metrics: p50/p95/p99 + error rate + queue depth
```

### Step 2 — Run with a Fixed Load Profile

```text
Warm-up: 2 minutes, 50 req/s
Steady: 15 minutes, 250 req/s
Burst: 1 minute, 400 req/s
Payload: same anonymized dataset
```

### Step 3 — Mark the Timestamp When Latency Crosses Threshold

Record the incident marker in UTC along with request rate, concurrency, p95/p99, and error rate.

### Step 4 — Capture JFR

If no recording is active:

```bash
jcmd 18420 JFR.start name=latency-incident settings=profile duration=10m filename=/var/tmp/latency-incident.jfr
```

If a continuous recording is already running, dump the current window:

```bash
jcmd 18420 JFR.dump name=continuous filename=/var/tmp/latency-window.jfr
```

### Step 5 — Capture Thread Dump and JVM Snapshot

```bash
jcmd 18420 Thread.print -l > /var/tmp/threads-1.txt
jcmd 18420 GC.heap_info > /var/tmp/heap-info.txt
jcmd 18420 VM.flags > /var/tmp/vm-flags.txt
```

If latency continues to climb, take another thread dump a few seconds later to compare whether threads are waiting at the exact same location.

### Step 6 — Capture OS and Container Load

Linux:

```bash
date -u +"%Y-%m-%dT%H:%M:%SZ"
uptime
vmstat 1 10
pidstat -p 18420 1 10
free -h
```

Container: record CPU/memory quotas, throttling, and memory events according to your cgroup/runtime.

### Step 7 — Analyze JFR

```bash
jfr summary /var/tmp/latency-incident.jfr

jfr print --events jdk.ExecutionSample,jdk.CPULoad,jdk.GarbageCollection,jdk.GCHeapSummary /var/tmp/latency-incident.jfr

jfr print --events jdk.JavaMonitorEnter,jdk.ThreadPark,jdk.SocketRead,jdk.SocketWrite /var/tmp/latency-incident.jfr
```

Correlate timestamps with application metrics:

- Are execution samples concentrated in a CPU-bound code path?
- Are threads mostly parking or waiting on monitors?
- Are socket read/write durations increasing?
- Do GC pauses align with latency spikes?
- Did queue depth rise before latency increased?

### Step 8 — Form a Hypothesis and Reproduce Under Control

If JFR shows many threads waiting on the same monitor lock:

1. Identify the lock owner and stack trace.
2. Inspect thread dumps at the same timestamp.
3. Construct a similar concurrency scenario.
4. Change one factor, such as the critical section or worker count.
5. Compare before/after latency and JFR recordings.

Do not modify code based on a single isolated event. Look for evidence linking load, thread states, stacks, and symptoms.

## 19. Quick Collection Command Templates

The following commands serve as a starting point for an incident. Substitute PID, paths, and durations for your environment.

### 19.1. Linux: JDK and JVM

```bash
PID=18420

date -u +"%Y-%m-%dT%H:%M:%SZ"
jcmd -l
jcmd "$PID" VM.version
jcmd "$PID" VM.command_line
jcmd "$PID" VM.flags
jcmd "$PID" VM.system_properties
```

Review `VM.system_properties` and command-line output to remove secrets before sharing.

### 19.2. Linux: OS and Load

```bash
date -u +"%Y-%m-%dT%H:%M:%SZ"
uname -a
cat /etc/os-release
lscpu
free -h
uptime
vmstat 1 10
pidstat -p 18420 1 10
df -h
cat /proc/18420/status
cat /proc/18420/limits
```

If disk I/O data is needed and the tool is available:

```bash
iostat -xz 1 10
```

### 19.3. Linux: JFR and Thread Dump

```bash
jcmd 18420 JFR.check
jcmd 18420 JFR.start name=incident settings=profile duration=10m filename=/var/tmp/incident.jfr
jcmd 18420 Thread.print -l > /var/tmp/thread-dump.txt
```

After the recording finishes:

```bash
jfr summary /var/tmp/incident.jfr
```

### 19.4. Windows PowerShell: JDK and OS

```powershell
$javaPid = 18420

Get-Date -Format o
Get-Command java, jcmd, jfr | Select-Object Name, Source
java -version

jcmd $javaPid VM.version
jcmd $javaPid VM.command_line
jcmd $javaPid VM.flags

Get-ComputerInfo |
    Select-Object WindowsProductName, WindowsVersion,
                  OsBuildNumber, OsArchitecture

Get-Process -Id $javaPid |
    Select-Object Id, ProcessName, CPU, WorkingSet64, Threads, Handles, StartTime
```

`VM.command_line` and certain properties may contain secrets. Review the output before sending.

### 19.5. Windows PowerShell: JFR and Thread Dump

```powershell
$javaPid = 18420

jcmd $javaPid JFR.check
jcmd $javaPid JFR.start name=incident settings=profile duration=10m filename=C:/temp/incident.jfr
jcmd $javaPid Thread.print -l |
    Out-File -Encoding utf8 C:/temp/thread-dump.txt

jfr summary C:/temp/incident.jfr
```

Ensure `C:/temp` exists and the user running the JVM has write permission. If the process runs under a service account, the service account's filesystem permissions are what matter.

## 20. What Not to Do When Reproducing and Collecting Data

- Do not change multiple configuration variables in the same run and then claim a root cause.
- Do not record only the shell's `java -version` while ignoring the actual JDK of the process.
- Do not use a single CPU or heap snapshot to draw conclusions about a long time window.
- Do not look only at average latency when the problem is in p95/p99.
- Do not assume the host CPU count equals the CPUs allowed for the JVM or container.
- Do not run `readAllBytes` or large heap dumps on a stressed process without evaluating the impact.
- Do not leave detailed JFR events enabled indefinitely without knowing their overhead and storage footprint.
- Do not restart a process before capturing necessary snapshots if observation is still safe.
- Do not send raw command lines, system properties, logs, heap dumps, or JFR files externally without reviewing for sensitive data.
- Do not treat JFR as the sole piece of evidence; combine it with application logs, metrics, and OS data.

## 21. Key Takeaways

- Reproducing an incident requires clearly defined **inputs, conditions, load, expected behavior, and actual behavior**.
- Identify the exact PID and runtime of the process; `java -version` in a shell may not be the JDK running the service.
- Collect JDK vendor/build, VM version, command line, flags, and selective system properties.
- Record OS/kernel, CPU, memory, process limits, filesystem, and container quotas.
- Measure load using throughput, concurrency, p50/p95/p99, error rate, queue depth, and pool metrics.
- Use `jcmd` to gather VM info, thread dumps, heap summaries, and control JFR.
- JFR can be started via `jcmd JFR.start` or at startup with `-XX:StartFlightRecording`.
- Use `default` for lower-detail recordings and `profile` for short investigation windows needing more events.
- JFR and GC logs do not replace application logs; synchronize timelines in UTC for correlation.
- JFR, thread dumps, command lines, and system properties can contain sensitive data; control access and redact before sharing.

## Official Java 17 References

- [Java SE 17 — `jcmd` tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html).
- [Java SE 17 — `jfr` tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html).
- [Java SE 17 — `java` launcher and VM options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html).
- [Oracle Java 17 — JDK Flight Recorder](https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder-api-programmers-guide.pdf).
- [Oracle Java 17 — Troubleshoot Performance Issues Using JFR](https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-performance-issues-using-jfr.html).
- [JEP 328 — Flight Recorder](https://openjdk.org/jeps/328).
- [JEP 331 — Low-Overhead Heap Profiling](https://openjdk.org/jeps/331).
