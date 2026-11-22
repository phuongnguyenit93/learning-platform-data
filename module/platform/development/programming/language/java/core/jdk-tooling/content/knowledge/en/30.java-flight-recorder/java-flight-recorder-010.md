# JFR Overhead and Cost

## 1. What is JFR Cost?

Java Flight Recorder (JFR) collects events in the JVM and application over time. Event recording helps investigate CPU, garbage collection (GC), allocation, thread, lock, I/O, and many other runtime issues without needing an external profiler.

**JFR cost** is the resource usage and operational impact incurred when recording, storing, transferring, and analyzing data. At least five areas should be considered:

1. **CPU:** the JVM emits events, samples stacks, and writes data.
2. **Latency:** certain types of data or additional operations can introduce pauses.
3. **Memory:** JFR uses buffers inside the JVM and may retain data in a repository.
4. **Disk I/O and capacity:** recordings write chunks, maintain the repository, and produce `.jfr` files.
5. **Operations:** teams must manage retention, protect sensitive data, and analyze recordings.

Cost varies depending on the workload, thread count, event frequency, configuration, recording duration, and the types of data collected. There is no single fixed overhead percentage that applies to every application.

## 2. How Much Overhead Does JFR Have?

JFR is designed to collect data with low overhead, though not zero.

Oracle provides reference guidelines for Java SE 24:

- The **default.jfc** configuration for continuous recording typically has under 1% overhead.
- Standard continuous recording with default settings usually produces no measurable performance impact.
- A fixed-duration profiling recording with default settings has under 2% overhead in most applications.
- The **profile.jfc** configuration collects more events and has a higher performance impact than **default.jfc**.

These are Oracle's reference results and guidelines, not an SLA guarantee. A latency-sensitive workload, one that emits a very high volume of events, or one that enables additional stack traces may experience noticeably different costs.

In JDK 24, **jcmd <PID> help JFR.start** also warns that the impact of **JFR.start** depends on settings and can range from low to high. If default event settings are modified, overhead can exceed 1%.

Therefore, start with **default.jfc**, measure on a representative workload, and enable additional data only when required by the investigation question.

Documentation: [Oracle Java SE 24 — Flight Recorder Configurations](https://docs.oracle.com/en/java/javase/24/jfapi/flight-recorder-configurations.html) and [Flight Recorder Overhead](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshoot-performance-issues-using-jfr.html).

## 3. Comparing default.jfc and profile.jfc

The JDK provides two built-in configurations in the **JAVA_HOME/lib/jfr** directory:

| Configuration | Purpose | Relative Cost |
|---|---|---|
| default.jfc | Continuous monitoring, collecting useful data with low overhead | Low |
| profile.jfc | More detailed profiling over a limited time window | Higher |

**default.jfc** is suitable to keep always enabled on services that need the ability to investigate rare incidents. It balances data volume and performance.

**profile.jfc** generally enables more events or samples more frequently. Use it when you need to find hot methods, allocations, compiler activity, lock contention, or bottlenecks that default data does not capture.

Do not leave a profile recording running indefinitely just to collect more data. Record for a window long enough to reproduce the issue, then stop and analyze.

If customization is needed, copy an existing `.jfc` file and edit the copy. Do not edit **default.jfc** or **profile.jfc** directly inside the JDK installation directory, as those changes are hard to track and may be lost on upgrade.

## 4. CPU Cost

CPU is spent emitting events, sampling threads, capturing stack traces, and processing buffers.

Factors that increase CPU usage:

- Enabling more events.
- Increasing sampling frequency.
- Enabling stack traces for many event types.
- Lowering event thresholds to record very short operations.
- Recording detailed allocations or denser method profiling.
- Running multiple recordings or multiple JVMs concurrently.

In the built-in configurations, many Java Application duration events are only recorded when the duration exceeds a threshold, commonly 20 ms. This threshold helps limit event volume. Lowering it to 1 ms can produce significantly more events, increasing CPU usage, file size, and analysis effort.

Example of starting a recording with a lower event threshold:

§§§bash
jcmd <PID> JFR.start name=short-profile settings=profile duration=5m jdk.JavaMonitorEnter#threshold=1ms
§§§

Only lower thresholds for events relevant to the question being investigated. Do not lower all thresholds across the board in production.

## 5. Latency and GC Pause Cost

Some data collection can increase pauses or alter response times.

**Heap Statistics** is an important example. This feature is disabled by default because collecting it can trigger an old garbage collection at the start and end of the recording. Those two GCs can add pauses to the application.

If the goal is measuring latency or throughput, do not enable Heap Statistics by default. Only enable it when investigating a memory leak or determining the application's live set, and when the pause cost is acceptable.

The **path-to-gc-roots** option traces reference paths to objects from GC roots, which is useful when investigating memory leaks. However, collecting this data is expensive and can pause the application briefly. Enable it only when there is a specific suspicion of a leak.

Example of dumping a recording and requesting GC root paths:

§§§bash
jcmd <PID> JFR.dump name=memory-investigation path-to-gc-roots=true filename=memory-investigation.jfr
§§§

Do not use this option as a default continuous configuration. When evaluating latency, compare p95/p99 and GC pauses with the feature disabled vs. enabled in a test environment.

## 6. JVM Memory Cost

JFR uses buffers to collect events before writing data out as chunks. Memory usage depends on configuration, thread count, event rate, and how long data is retained in buffers.

Common configuration values in JDK 24:

| Parameter | Default Value | Role |
|---|---:|---|
| memorysize | 10 MB | Total memory JFR reserves for buffers |
| maxchunksize | 12 MB | Maximum size of a single chunk |
| stackdepth | 64 | Stack trace depth |
| thread_buffer_size | 8 KB | Thread-local buffer per thread |

These values describe JFR configuration, not the total absolute memory footprint of the entire JVM. Actual total footprint also depends on thread count, active recordings, and runtime activity.

Key notes:

- Increasing **stackdepth** beyond the default of 64 can degrade performance.
- Changing **thread_buffer_size** can degrade performance and is not recommended without clear measurement-backed justification.
- Parameters such as **memorysize**, **maxchunksize**, and **stackdepth** cannot be changed after JFR has been initialized.
- Do not increase buffer sizes just to try to capture every single event. Check data loss, event volume, and investigation goals first.

You can inspect the JVM's JFR configuration:

§§§bash
jcmd <PID> JFR.configure
§§§

Read the output before deciding to change startup options. Refer to the syntax and limits in the documentation for the exact JDK version in use.

## 7. Disk I/O and Repository Cost

When a recording writes to disk, JFR stores data in chunks inside a disk repository. The repository holds temporary data while the recording is running; `.jfr` files are created when dumping or stopping the recording as configured.

On Windows, the default repository resides in the temporary directory specified by the `TMP` environment variable. On Linux, the default temporary directory is typically `/tmp`.

Without time or size limits, a recording can accumulate more and more data. Therefore, continuous recordings in production should have a clear retention policy.

Two primary limits:

- **maxage:** maximum duration to retain data in the repository.
- **maxsize:** maximum disk space to retain.

Both take effect only when **disk=true**. When either limit is reached, the oldest chunk data is discarded to make room for new data. If both are set, the recording obeys both time and size limits; whichever limit is reached first determines how much data is kept.

A value of **0** means unlimited. Do not use **maxage=0** and **maxsize=0** for continuous recordings on machines with finite disk space unless an external management mechanism is in place.

Example of configuring a continuous recording retaining at most six hours or two gigabytes of data:

§§§bash
jcmd <PID> JFR.start name=continuous settings=default disk=true maxage=6h maxsize=2G
§§§

If the repository uses a temporary directory with limited space, choose a repository path on a monitored volume with sufficient capacity. Ensure the account running the JVM has write permissions and that cleanup jobs do not delete repository files currently in use by the JVM.

## 8. Estimating Recording Size

JFR file size depends on event rate and configuration, so it should not be predicted from recording duration alone.

An initial estimate can be made from a trial recording:

§§§text
Estimated size
  = Average size per hour
    × Retention hours
    × Number of JVMs
    × Safety factor
§§§

Illustrative example:

- One JVM generates an average of 40 MB of data per hour.
- Desired retention is 6 hours.
- There are 20 JVMs.
- Safety factor chosen is 1.5.

§§§text
40 MB × 6 × 20 × 1.5 = 7,200 MB
§§§

Under these assumptions, roughly 7.2 GB of repository space is needed across all 20 JVMs. This is only an illustrative calculation; use your application's actual file growth rate for capacity budgeting.

When sizing production, also account for:

- Size of `.jfr` files dumped outside the repository.
- Number of concurrent recordings per JVM.
- Temporary files during upload or analysis.
- Retention period for copies kept for incident postmortems.
- Headroom for traffic spikes or sudden increases in event rate.

Monitor repository size over time rather than checking it only once right after enabling JFR.

## 9. Time and Size Limits When Recording

**JFR.start** supports **duration**, **maxage**, **maxsize**, **disk**, **filename**, and **settings**.

Example of a ten-minute time-bounded profiling recording:

§§§bash
jcmd <PID> JFR.start name=profile settings=profile duration=10m disk=true maxage=15m maxsize=512M filename=/var/log/jfr/short-profile.jfr
§§§

The recording stops automatically when the duration elapses. Retention size and age limit how much data is kept on disk during the recording.

Check running recordings:

§§§bash
jcmd <PID> JFR.check
§§§

Dump data from a continuous recording to a file:

§§§bash
jcmd <PID> JFR.dump name=continuous filename=/var/log/jfr/continuous-snapshot.jfr
§§§

You can dump a relative time range, such as data from the last hour:

§§§bash
jcmd <PID> JFR.dump name=continuous begin=-1h filename=/var/log/jfr/last-hour.jfr
§§§

**JFR.dump** writes data to a file while the recording continues running. When recording is no longer needed, stop it:

§§§bash
jcmd <PID> JFR.stop name=continuous
§§§

To record from application startup, use the startup option:

§§§bash
java -XX:StartFlightRecording:settings=default,disk=true,maxage=6h,maxsize=2G -jar app.jar
§§§

The examples use Linux paths; on Windows, substitute an appropriate path and ensure the service account has write permissions.

## 10. Choosing Event Settings to Control Cost

Each event can have settings such as:

| Setting | Role | Impact When Increasing Collection |
|---|---|---|
| enabled | Enable/disable the event | More events when enabling additional types |
| threshold | Minimum duration to record a duration event | Lowering threshold increases event count |
| period | Emission interval for periodic events | Shorter period produces more samples |
| stackTrace | Record stack trace for the event | Adds CPU and data volume cost |

Enable only the events you need. For example:

- Investigating lock contention: look at **jdk.JavaMonitorEnter** and **jdk.JavaMonitorWait**.
- Investigating I/O: look at **jdk.FileRead**, **jdk.FileWrite**, **jdk.SocketRead**, and **jdk.SocketWrite**.
- Investigating CPU: look at **jdk.ExecutionSample**, **jdk.CPULoad**, and **jdk.ThreadCPULoad**.
- Investigating GC: look at **jdk.GarbageCollection**, **jdk.GCPhasePause**, and related GC events.
- Investigating allocation: choose appropriate allocation profiling and expect larger files.

If customization is needed, create a copy of an existing configuration and adjust it using JDK Mission Control or **jfr configure**. Do not enable every event at high detail just to have complete data; such a configuration can generate massive data volume and sharply increase overhead.

Documentation: [Flight Recorder Event Configuration](https://docs.oracle.com/en/java/javase/24/jfapi/configuration.html).

## 11. Measuring JFR Overhead Fairly

Overhead cannot be evaluated by intuition or a single run. Compare on the same workload.

Recommended procedure:

1. Prepare a staging or benchmark environment close to production.
2. Fix the JDK vendor/version, OS, heap, GC, CPU quota, and application configuration.
3. Run the workload without JFR enabled to establish a baseline.
4. Re-run the same workload with **default.jfc**.
5. Re-run with **profile.jfc** for a bounded duration.
6. Repeat runs enough times to reduce noise.
7. Compare throughput, p50/p95/p99 latency, CPU, allocation rate, GC pauses, RSS, and disk writes.
8. Verify the recording contains the required events and check for **jdk.DataLoss**.
9. Record the configuration, measurement window, and load conditions so the test is reproducible.

Sample comparison table:

| Metric | No JFR | Default | Profile |
|---|---:|---:|---:|
| Throughput (req/s) | 10,000 | 9,980 | 9,850 |
| p99 latency (ms) | 80 | 81 | 86 |
| CPU (%) | 65 | 65.5 | 68 |
| GC pause (ms/min) | 120 | 121 | 126 |
| Disk write (MB/hr) | 0 | 35 | 180 |

The numbers above are illustrative only for presentation. Do not treat them as standard thresholds or expected results for a real system.

Reference formulas:

§§§text
CPU overhead (%) =
  (CPU_with_JFR - CPU_baseline) / CPU_baseline × 100

Latency change (%) =
  (p99_with_JFR - p99_baseline) / p99_baseline × 100
§§§

When the baseline is 0 or very small, percentages may not be meaningful; compare absolute values instead. If the workload fluctuates, use multiple runs and analyze distributions rather than relying on a single average.

## 12. Reading Recordings to Control Cost

Once you have a `.jfr` file, use the **jfr** command to view a summary:

§§§bash
jfr summary recording.jfr
§§§

Print a specific group of events:

§§§bash
jfr print --events jdk.ExecutionSample,jdk.CPULoad recording.jfr
§§§

Check for data loss events:

§§§bash
jfr print --events jdk.DataLoss recording.jfr
§§§

Open the file in JDK Mission Control (JMC) to inspect the timeline, event counts, hot methods, allocations, GC, and thread activity.

If the file is unusually large:

- Check which events consume the most bytes or have excessive counts.
- Verify whether thresholds and periods are lower than necessary.
- Check whether stack traces are enabled on too many events.
- Compare **default** against **profile**.
- Narrow the event scope and recording duration.
- Use **maxage**/**maxsize** to keep the repository within limits.

Do not remove events just to shrink the file if those events are required evidence for the investigation question. Balance file size with diagnostic power.

## 13. Tips for Reducing Cost in Production

- Start with **default.jfc** for continuous recording.
- Bound retention with **maxage** and **maxsize**.
- Place the repository path on a monitored volume with sufficient capacity.
- Use **profile.jfc** for short windows when deeper data is needed.
- Enable Heap Statistics only when investigating memory leaks or live set size.
- Enable **path-to-gc-roots** only when object reference tracing is truly needed.
- Keep the default stack depth unless there is evidence that deeper stacks are required.
- Do not increase **thread_buffer_size** without measured benefit.
- Lower event thresholds only for specific event types.
- Avoid running multiple profiling recordings on the same JVM unnecessarily.
- Stop temporary recordings once the investigation is complete.
- Re-measure overhead after every configuration change.

For latency-sensitive applications, also evaluate GC pause times and p99 latency rather than looking only at average CPU.

## 14. Java 17+ Example: Creating a Bounded Recording with the JFR API

The JFR API allows an application to create recordings programmatically and set retention limits. The example below uses the **default** configuration, enables writing to disk, and caps repository data at a maximum of five minutes or 64 MB.

Create **JfrCostDemo.java**:

§§§java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Configuration;
import jdk.jfr.Recording;

public class JfrCostDemo {
    public static void main(String[] args) throws Exception {
        Path output = Path.of("jfr-cost-demo.jfr");

        try (Recording recording = new Recording(
                Configuration.getConfiguration("default"))) {
            recording.setName("jfr-cost-demo");
            recording.setToDisk(true);
            recording.setMaxAge(Duration.ofMinutes(5));
            recording.setMaxSize(64L * 1024 * 1024);
            recording.start();

            long deadline = System.nanoTime()
                    + Duration.ofSeconds(2).toNanos();
            long checksum = 0;

            while (System.nanoTime() < deadline) {
                checksum += System.nanoTime() & 0xff;
            }

            recording.stop();
            recording.dump(output);

            if (checksum == Long.MIN_VALUE) {
                throw new AssertionError("unreachable");
            }
        }

        System.out.println(
            "Recording created: " + Files.exists(output));
    }
}
§§§

Compile and run:

§§§bash
javac JfrCostDemo.java
java JfrCostDemo
§§§

Exact stdout:

§§§text
Recording created: true
§§§

The file **jfr-cost-demo.jfr** is created in the current directory. View its summary:

§§§bash
jfr summary jfr-cost-demo.jfr
§§§

File size and event counts vary by JDK, machine, and runtime conditions. This example demonstrates how to bound a recording and create a file; the loop is not a JFR overhead benchmark. To measure overhead, run a realistic application workload across baseline/default/profile runs as described in the previous section.

## 15. Common Issues Related to JFR Cost

| Symptom | Possible Cause | Resolution |
|---|---|---|
| CPU increases after enabling JFR | Using **profile.jfc**, too many events, or dense sampling | Switch back to **default**, reduce events, and re-measure |
| p99 latency increases | Heap Statistics enabled or pause-inducing events collected | Disable heap stats; use only when investigating memory leaks |
| Disk fills up | Unbounded recording or rising event rate | Set **maxage**, **maxsize**, and monitor the repository |
| `.jfr` file unusually large | Threshold too low, excessive stack traces, or long profiling | Inspect with **jfr summary**, reduce events and duration |
| Expected events missing | Event disabled or threshold too high | Check `.jfc` and enable the required events |
| **jdk.DataLoss** present | Event rate exceeds buffer/consumer capacity under current load | Check load, buffers, event volume, and recording settings |
| **JFR.start** reports invalid maxsize | `maxsize` is smaller than `maxchunksize` | Set `maxsize` to at least the configured `maxchunksize` |
| Repository uses too much space | `maxage`/`maxsize` unset or disk usage differs from expectations | Check **JFR.check**, **JFR.configure**, and retention settings |
| Dump causes pauses | **path-to-gc-roots** enabled or workload is heavily loaded | Collect GC roots only when there is a clear memory leak target |
| File not created on JVM exit | `dumponexit` not enabled or process forcibly killed | Configure **dumponexit=true** or dump proactively before shutdown |

## 16. Securing Recordings and Operational Cost

A JFR file may contain thread names, class names, method names, command lines, system properties, environment variables, file paths, hostnames, and connection details depending on which events are enabled.

Therefore:

- Store files in directories with restricted access permissions.
- Do not attach recordings to public tickets or send them over unapproved channels.
- Inspect for sensitive data before sharing with vendors or third parties.
- Delete or archive files according to your organization's retention policy.
- Record the PID, vendor, JDK version, `.jfc` configuration, start/end timestamps, and workload.
- Factor file transfer, copy storage, and analysis time into incident planning.

A useful recording must answer the investigation question. Recording more data does not automatically produce a better diagnosis; it also increases storage, complexity, and data exposure risk.

## 17. Summary

JFR can be kept enabled continuously with low overhead when configured appropriately, though actual cost still depends on the application and event settings.

Key principles to remember:

- Use **default.jfc** for continuous recording and measure overhead on realistic workloads.
- Use **profile.jfc** for bounded time windows when deeper data is needed.
- Do not enable Heap Statistics or **path-to-gc-roots** indiscriminately, as they can trigger GC pauses or additional pauses.
- Bound disk retention with **maxage** and **maxsize**.
- Keep default stack depth and thread buffer sizes unless measurements justify changing them.
- Check event counts, file size, and **jdk.DataLoss**.
- Compare baseline, default, and profile using throughput, p99 latency, CPU, GC pauses, and disk I/O.
- Protect recordings as operational data that may contain sensitive information.

**Official references:**

- [Oracle Java SE 24 — Flight Recorder Configurations](https://docs.oracle.com/en/java/javase/24/jfapi/flight-recorder-configurations.html)
- [Oracle Java SE 24 — Flight Recorder Overhead](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [Oracle Java SE 24 — The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [Oracle Java SE 24 — The jfr Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jfr.html)
- [Oracle Java SE 24 — Recording API](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/jdk/jfr/Recording.html)
- [Oracle Java SE 24 — Flight Recorder Event Configuration](https://docs.oracle.com/en/java/javase/24/jfapi/configuration.html)
- [Oracle Java SE 24 — The java Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html)
