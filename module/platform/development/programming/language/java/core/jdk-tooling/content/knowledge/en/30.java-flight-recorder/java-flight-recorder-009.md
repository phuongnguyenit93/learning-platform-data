# Operating Java Flight Recorder (JFR) in Production

Java Flight Recorder (JFR) is an event recording system built into the JVM. It collects runtime data over time, such as CPU sampling, allocations, garbage collection, lock contention, I/O, exceptions, class loading, threads, and safepoints. Recording files use the `.jfr` format and can be analyzed with Java Mission Control (JMC), the `jfr` command-line tool, or compatible tools.

JFR is well suited for production because the `default.jfc` configuration is designed to collect data with low overhead and can run continuously. The `profile.jfc` configuration collects more detail, but generates more data and has a higher performance impact; it should be used for short periods when deep investigation is needed.

The two tools serve different roles:

- `jcmd <PID> JFR.*`: controls recordings on a running JVM.
- `jfr ...`: inspects, filters, configures, or processes `.jfr` files.

This article uses Zulu/OpenJDK 24.0.2 to verify syntax, options, and an actual recording. Commands should still be verified against the target JDK's help output because events and options can change between versions.

## 1. When Should You Use JFR in Production?

JFR helps answer questions about JVM behavior during a specific time window.

| Symptom | Useful JFR Data |
|---|---|
| High CPU usage | Execution samples, hot methods, compiler, and thread CPU |
| Increased GC pauses or allocations | Garbage collection, heap summary, allocation samples |
| Slow requests or lock contention | Java monitor enter/wait, thread park, stack traces |
| Slow I/O | Socket read/write, file read/write, and event durations |
| Increased exceptions | Exception/error events and stack traces if enabled |
| Abnormal thread growth | Thread start/end, thread count, and thread dump events |
| Abnormal class loading | Class load/unload, class loader statistics |
| Virtual thread pinning | Virtual thread pinned events and stack traces |
| Suspected memory leak | Old object samples and path to GC roots when needed |

JFR records events inside the JVM, not a complete distributed trace. If a request is slow across multiple services, databases, or message brokers, correlate JFR with trace IDs, application logs, database metrics, and telemetry from the related services.

## 2. Recording Models: Continuous and Investigation Sessions

There are two common usage patterns.

### 2.1. Continuous Recording

Run `default` settings over a long period, bounding the data with `maxage` and `maxsize`. The JVM keeps the recording in a disk repository and evicts older data when the retention limits are exceeded.

Example:

~~~text
jcmd <PID> JFR.start name=continuous settings=default disk=true maxage=6h maxsize=1G dumponexit=true
~~~

- `name=continuous`: recording name used to reference it in subsequent commands.
- `settings=default`: low-overhead configuration suitable for continuous recording.
- `disk=true`: writes data to the disk repository while the recording is running.
- `maxage=6h`: retains data only up to the specified maximum age.
- `maxsize=1G`: limits the recording data size on disk.
- `dumponexit=true`: writes the recording to a file on normal JVM shutdown.

Continuous recording preserves data from before an alert fires. When an incident occurs, you can dump a recent time window without waiting for the issue to reproduce.

`maxage` and `maxsize` only apply when the recording writes to disk. Check the capacity of the repository and dump destination; do not set retention larger than the actual volume capacity.

### 2.2. Short Recording for Incidents

When more detail is needed, use `profile` for a limited duration:

~~~text
jcmd <PID> JFR.start name=incident settings=profile duration=5m filename=incident.jfr
~~~

`profile.jfc` typically enables more events, increases sampling rates, or lowers thresholds compared to `default.jfc`. It is useful for identifying hot methods, allocation sites, lock waits, or slow I/O. Limit both duration and size, then return to a lighter configuration.

Avoid running multiple overlapping profile recordings unless you understand the event set and overhead of each one. `JFR.start` has a Medium impact; actual overhead depends on the configuration and workload.

## 3. Choosing `default.jfc` vs. `profile.jfc`

The JDK provides two standard configurations in `JAVA_HOME/lib/jfr`.

| Configuration Group | `default.jfc` | `profile.jfc` |
|---|---|---|
| Goal | Continuous observation, low overhead | Short investigation, more detail |
| GC | `normal` | `detailed` |
| Allocation profiling | `low` | `medium` |
| Compiler | `normal` | `detailed` |
| Method profiling | `normal` | `high` |
| Memory leak | `types` | `stack-traces` |
| Locking threshold | `20ms` | `10ms` |
| File/socket threshold | `20ms` | `10ms` |
| Exceptions | `errors` | `errors` |

The values above were verified from `jcmd <PID> help JFR.start` on JDK 24.0.2. They are the defaults for the tested version; other JDK releases may differ.

Selection guidelines:

- Start with `default` when you need continuous recording.
- Use `profile` for a short window when you need stack traces and finer-grained data.
- Lower event thresholds only when your diagnostic question requires shorter-duration events.
- Enable stack traces for targeted events; stack traces increase file size and collection cost.
- Do not enable all events at high frequency just because you can.

## 4. Starting JFR with the Application

You can configure a recording right when the JVM starts:

~~~text
java -XX:StartFlightRecording=name=continuous,settings=default,disk=true,maxage=6h,maxsize=1g,dumponexit=true -jar application.jar
~~~

The JVM starts the recording with the specified configuration. This is useful when you want to ensure JFR is active from service startup.

You can set `filename` to specify where the file is written when the recording is dumped or stopped:

~~~text
java -XX:StartFlightRecording=name=continuous,settings=default,disk=true,maxage=6h,maxsize=1g,dumponexit=true,filename=/var/log/myapp/jfr/continuous-%p-%t.jfr -jar application.jar
~~~

In the filename pattern:

- `%p` is replaced by the PID.
- `%t` is replaced by a timestamp in `yyyy_MM_dd_HH_mm_ss` format.

The target directory must exist, and the user running the JVM must have write permission. On Windows, use an environment-appropriate path such as `D:\logs\myapp\jfr`.

Verify startup option syntax on the exact JDK using the `java` documentation and test it in staging before adding it to deployment manifests.

## 5. Controlling Recordings on a Running JVM with `jcmd`

First, find the PID:

~~~text
jcmd -l
~~~

Then check the JFR commands supported by the JVM:

~~~text
jcmd <PID> help JFR.start
jcmd <PID> help JFR.check
jcmd <PID> help JFR.dump
jcmd <PID> help JFR.stop
jcmd <PID> help JFR.configure
~~~

### 5.1. Starting a Recording

~~~text
jcmd <PID> JFR.start name=incident settings=default
~~~

The recording can be configured further:

~~~text
jcmd <PID> JFR.start name=incident delay=10s duration=5m settings=profile filename=incident.jfr
~~~

- `delay`: wait time before starting.
- `duration`: recording duration; `0s` means unlimited.
- `settings`: profile name or path to a `.jfc` file.
- `filename`: file written when the recording stops or completes.

If no name is specified, the JVM generates one automatically. Record the name or ID returned by the command for use with `JFR.check`, `JFR.dump`, and `JFR.stop`.

### 5.2. Checking Recordings

~~~text
jcmd <PID> JFR.check
jcmd <PID> JFR.check name=incident verbose=true
~~~

`JFR.check` shows which recordings are running. `verbose=true` prints event settings; the output can be long because it includes many events. When verifying a custom event or threshold, filter the output in your terminal after the command finishes.

### 5.3. Dumping Data Without Stopping the Recording

~~~text
jcmd <PID> JFR.dump name=continuous filename=incident-snapshot.jfr
~~~

Dumping creates a `.jfr` file from the active recording. The recording continues running, so you can capture a snapshot during an ongoing incident and keep observing.

You can also extract a specific time range:

~~~text
jcmd <PID> JFR.dump name=continuous filename=last-window.jfr begin=-15m end=-5m
~~~

`begin` and `end` accept local times, ISO timestamps, or relative times such as `-15m`, `-30s`, and `-2h`. The example above captures data from 15 minutes ago to 5 minutes ago relative to the dump time.

### 5.4. Stopping a Recording

~~~text
jcmd <PID> JFR.stop name=incident filename=incident-final.jfr
~~~

When stopping, specify `filename` if you want to save the data to a file. According to the JDK 24.0.2 help output, if no path is provided, the recording data is discarded on stop.

If you dumped a snapshot earlier, that snapshot file remains independent of the running recording.

## 6. Managing Disk Space, Repository, and Retention

JFR uses a repository to store data chunks before assembling a complete recording file. By default, the repository is located in the operating system's temporary directory.

Key recording parameters:

| Option | Meaning |
|---|---|
| `disk=true` | Write the recording to the disk repository |
| `maxage=1h` | Maximum age of retained data |
| `maxsize=512M` | Maximum size of retained data |
| `dumponexit=true` | Dump on JVM shutdown |
| `filename=...` | Recording file path on dump/stop |

`maxsize` must be at least as large as the `maxchunksize` configured for JFR. On JDK 24.0.2, the default `maxchunksize` is 12 MB; for example, `maxsize=32M` is valid.

### 6.1. Configuring the JFR Repository and Memory

View the current configuration:

~~~text
jcmd <PID> JFR.configure
~~~

Notable options:

- `repositorypath`: directory for the temporary repository.
- `dumppath`: directory where recordings are written on fatal JVM errors.
- `memorysize`: total JFR buffer memory.
- `maxchunksize`: maximum chunk size.
- `stackdepth`: stack trace depth.
- `thread_buffer_size`: per-thread local buffer size.
- `preserve-repository`: retain the repository after the JVM exits.

Example:

~~~text
jcmd <PID> JFR.configure repositorypath=/var/lib/myapp/jfr-repository dumppath=/var/lib/myapp/jfr-crash preserve-repository=true
~~~

Some parameters such as `memorysize`, `maxchunksize`, `stackdepth`, and `thread_buffer_size` cannot be changed after JFR has been initialized. If you need to customize them, configure them early in the JVM lifecycle and check the help output for your exact JDK version.

`preserve-repository=true` can help with post-crash investigation, but leftover chunks consume disk space. Put a process in place to collect, inspect, and clean up the repository once the investigation is complete.

## 7. Customizing Events and Thresholds

JFR events have common settings:

- `enabled`: enables or disables the event.
- `threshold`: records only events whose duration meets the threshold.
- `period`: interval for periodic events.
- `stackTrace`: whether to capture stack traces.
- `throttle`: rate-limits certain event types.

Event setting syntax:

~~~text
<event-name>#<setting-name>=<value>
~~~

Example capturing monitor contention of 5 ms or longer:

~~~text
jcmd <PID> JFR.start name=locks settings=default jdk.JavaMonitorEnter#threshold=5ms
~~~

You can create a reusable `.jfc` file:

~~~text
jfr configure gc=high method-profiling=high jdk.JavaMonitorEnter#threshold=5ms --output production.jfc
~~~

Start a recording using that file:

~~~text
jcmd <PID> JFR.start name=custom-profile settings=C:\diagnostics\production.jfc
~~~

`jfr configure` also lets you add new event settings using the `+` prefix, for example:

~~~text
jfr configure +com.example.OrderEvent#enabled=true +com.example.OrderEvent#stackTrace=true --output app-events.jfc
~~~

Do not lower thresholds arbitrarily. Lower thresholds record more events, which can produce larger files and higher collection overhead. Choose events based on the hypothesis you want to test.

## 8. Creating Custom JFR Events for Your Application

Applications can define custom events to record business operations. Custom events help correlate the execution time of an operation with JVM events such as allocations, GC, locks, and CPU samples.

Example file `JfrProdDemo.java`:

~~~java
import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;

@Name("com.example.OrderEvent")
@Label("Order Operation")
@Category({"Application", "Orders"})
class OrderEvent extends Event {
    @Label("Operation")
    String operation;

    @Label("Order ID")
    long orderId;
}

public final class JfrProdDemo {
    private JfrProdDemo() {
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println("JFR_DEMO_READY");
        long orderId = 0;

        while (true) {
            OrderEvent event = new OrderEvent();
            event.begin();
            event.operation = "reserve";
            event.orderId = ++orderId;

            byte[] payload = new byte[16 * 1024];
            payload[0] = 1;

            event.commit();
            Thread.sleep(100);
        }
    }
}
~~~

`OrderEvent` is a duration event because the code calls `begin()` and `commit()`. JFR records the start time, duration, business fields, event thread, and stack trace if enabled by the settings.

Compile:

~~~text
javac --release 17 JfrProdDemo.java
~~~

Run:

~~~text
java JfrProdDemo
~~~

Stdout:

~~~text
JFR_DEMO_READY
~~~

Open a second terminal, find the PID with `jcmd -l`, then start the recording and enable the custom event:

~~~text
jcmd <PID> JFR.start name=prod-lab settings=default disk=true maxage=5m maxsize=32M +com.example.OrderEvent#enabled=true +com.example.OrderEvent#stackTrace=true
~~~

Custom events only appear in the recording if the event is enabled. You can verify this with:

~~~text
jcmd <PID> JFR.check name=prod-lab verbose=true
~~~

In production code, include only fields needed for analysis. Avoid recording passwords, tokens, personal data, or request bodies. If creating events on a high-frequency code path, consider checking `event.isEnabled()` and `event.shouldCommit()` before computing expensive payloads.

## 9. Analyzing `.jfr` Files with the Command-Line Tool

After dumping the file:

~~~text
jfr summary prod-lab.jfr
~~~

`summary` displays the JFR version, duration, chunk count, event count, and size by event type. Use it to verify that the file covers the expected time range and that the events you need were recorded.

Print a specific event:

~~~text
jfr print --events com.example.OrderEvent prod-lab.jfr
~~~

Filter CPU and GC events:

~~~text
jfr print --events jdk.ExecutionSample,jdk.GarbageCollection prod-lab.jfr
~~~

Limit stack trace depth:

~~~text
jfr print --events jdk.JavaMonitorEnter --stack-depth 32 prod-lab.jfr
~~~

Export as JSON:

~~~text
jfr print --json --events jdk.CPULoad,jdk.GarbageCollection prod-lab.jfr
~~~

Other useful commands:

~~~text
jfr metadata prod-lab.jfr
jfr view hot-methods prod-lab.jfr
jfr view allocation-by-class prod-lab.jfr
jfr view gc-pauses prod-lab.jfr
~~~

`jfr metadata` displays event metadata and field layouts. `jfr view` generates built-in analysis tables such as hot methods, allocations by class, GC pauses, or lock contention.

You can filter by category:

~~~text
jfr print --categories "GC,JVM,Java*" prod-lab.jfr
~~~

For large files, avoid printing every event to the terminal. Start with `summary` and `view`, then print only the relevant event types and time range.

## 10. Interpreting Common Events

| Event | Meaning During Investigation |
|---|---|
| `jdk.ExecutionSample` | Stack samples for finding CPU-intensive methods |
| `jdk.ObjectAllocationSample` | Allocation samples for identifying notable allocating classes/sites |
| `jdk.GarbageCollection` | GC events and durations |
| `jdk.GCHeapSummary` | Heap usage around GC events |
| `jdk.JavaMonitorEnter` | Time spent waiting on a monitor |
| `jdk.JavaMonitorWait` | Thread waiting on a monitor |
| `jdk.ThreadPark` | Thread parking, often related to synchronizers or executors |
| `jdk.SocketRead` / `jdk.SocketWrite` | Socket I/O duration |
| `jdk.FileRead` / `jdk.FileWrite` | File I/O duration |
| `jdk.JavaExceptionThrow` | Exceptions thrown when the event is enabled |
| `jdk.ClassLoad` | Class loading |
| `jdk.SafepointBegin` | Safepoints and VM stop-the-world synchronization pauses |
| `jdk.VirtualThreadPinned` | Virtual thread pinned in a native or monitor context as defined by the event |

Allocation samples are sampled data, not a complete list of every object allocation. Do not sum sample event values and treat them as total bytes allocated. Use allocation profiling and related events to spot trends, then cross-check with heap/GC metrics.

For lock contention, inspect event duration, thread, stack trace, and code location. A long monitor wait event can be caused by a busy lock owner, I/O inside a `synchronized` block, or an overly broad critical section.

## 11. Analyzing Recordings with Java Mission Control

Java Mission Control (JMC) is a GUI tool for opening `.jfr` files and analyzing them across specialized pages.

Common workflow:

1. Collect the `.jfr` file from the JVM.
2. Open the file in JMC.
3. Check the Overview and recording duration.
4. Review Automated Analysis to spot prominent issues.
5. Open the JVM Internals, Threads, Memory, Garbage Collections, I/O, and Lock Instances pages based on the symptoms.
6. Use the event timeline to correlate CPU, allocation, GC, locks, and I/O.
7. Inspect stack traces and trace back to the source code.
8. Document the hypothesis, event evidence, timestamps, and the change to verify.

JMC is an analysis tool; it does not fix the root cause in the application. When comparing two recordings, keep the workload, JDK version, collector, heap sizing, and recording duration comparable.

## 12. Capturing Data Around an Incident

With a continuous recording already running, when an alert fires you can check the recording:

~~~text
jcmd <PID> JFR.check
~~~

Dump the 10 minutes immediately before the incident:

~~~text
jcmd <PID> JFR.dump name=continuous filename=incident-before.jfr begin=-10m
~~~

If you need a specific window prior to the current time:

~~~text
jcmd <PID> JFR.dump name=continuous filename=incident-window.jfr begin=-20m end=-5m
~~~

If more detail is needed, start a short profile recording:

~~~text
jcmd <PID> JFR.start name=incident-profile settings=profile duration=3m filename=incident-profile.jfr
~~~

After the investigation, stop any recording that is no longer needed:

~~~text
jcmd <PID> JFR.stop name=continuous filename=continuous-final.jfr
~~~

Only stop the continuous recording once you have saved the needed snapshots and have a plan to restart it. If you only need to extract a portion of the data, use `JFR.dump` so the recording keeps running.

## 13. Collecting Path to GC Roots for Suspected Memory Leaks

JFR can collect paths from objects to GC roots to investigate why objects remain reachable.

Example:

~~~text
jcmd <PID> JFR.dump name=continuous filename=memory-leak.jfr path-to-gc-roots=true
~~~

Or enable `path-to-gc-roots=true` when starting the recording per the JVM help output.

This operation can be expensive and pause the application briefly. Only enable it when you have a memory leak hypothesis and have assessed the impact. Do not leave it enabled continuously for all production recordings.

Combine Old Object Samples, allocation stack traces, heap dumps, and dominator/retained-size analysis to identify which objects are retaining memory. JFR path to GC roots provides supplemental evidence; it does not replace all forms of heap analysis.

## 14. Protecting Recording Files and Sensitive Data

A `.jfr` file can contain much more information than a typical log file:

- Initial environment variables and system properties.
- JVM arguments, classpath, process name, and system information.
- Thread names, stack traces, internal classes, and method names.
- File paths, socket endpoints, hostnames, or URLs.
- Field values recorded in application custom events.
- Information about load and business behavior at the time of capture.

Treat `.jfr` files as sensitive operational data:

1. Write to a volume with restricted access.
2. Encrypt at rest and in transit according to organizational policy.
3. Do not attach raw recordings directly to public tickets or chat channels.
4. Define a retention period and delete files once the investigation ends.
5. Redact or scrub sensitive events before sharing.
6. Avoid putting tokens, passwords, request bodies, or personal data in custom events.

You can remove certain sensitive events before sharing a file:

~~~text
jfr scrub --exclude-events InitialEnvironmentVariable,InitialSystemProperty,InitialSecurityProperty original.jfr sanitized.jfr
~~~

You can filter by event, category, or thread:

~~~text
jfr scrub --include-categories "GC,JVM" original.jfr gc-only.jfr
jfr scrub --exclude-threads "health-check*" original.jfr filtered.jfr
~~~

Scrubbing only removes the selected events. It does not automatically detect secrets inside stack traces, URLs, custom fields, or other events. Inspect the output file before sharing.

## 15. Recovering and Processing Recording Files

Useful commands when managing recording files:

~~~text
jfr assemble C:\jfr-repository recovered.jfr
~~~

`jfr assemble` merges remaining chunks in a disk repository into a `.jfr` file, which is useful when recovering repository data after an incident.

Split a large file into smaller parts:

~~~text
jfr disassemble --output C:\jfr-parts --max-size 100M large-recording.jfr
~~~

Chunk files can be analyzed individually or transferred through storage systems. When reassembling, preserve chunk ordering and metadata.

Before deleting a repository, confirm the recording was dumped and that the file opens cleanly with `jfr summary`.

## 16. Overhead and Safe Operating Principles

JFR is designed for production diagnostics, but no recording is completely free.

Impact depends on:

- Settings profile and number of enabled events.
- Sampling frequency and event thresholds.
- Whether stack traces are collected.
- Thread count and event emission rate.
- Recording duration and disk write throughput.
- Buffer sizes and repository configuration.
- Whether path to GC roots is requested.

Impact levels reported in JDK 24.0.2 help output:

| Command | Impact Reported by JVM |
|---|---|
| `JFR.start` | Medium, ranging from low to high depending on settings |
| `JFR.check` | Low |
| `JFR.dump` | Low |
| `JFR.stop` | Low |
| `JFR.configure` | Low |
| `JFR.view` | Medium |

To minimize impact:

- Use `default` for continuous recordings.
- Use `profile` for short windows.
- Set `maxage` and `maxsize` according to your disk budget.
- Enable stack traces and detailed events only when targeted.
- Do not set very low thresholds on high-frequency events without testing.
- Do not enable path to GC roots unless investigating a memory leak.
- Avoid running multiple overlapping profile recordings.
- Monitor disk usage and verify dump files after creation.
- Measure overhead in staging under a production-like workload.

JDK 24.0.2 help also notes that modifying default event settings can push overhead above 1%. Do not rely on a single fixed overhead number as a guarantee for every application.

## 17. Troubleshooting

### JVM Does Not Support JFR Commands

**Cause:** runtime is too old, JFR is not included, recording is disabled, or the target JVM does not support the requested command.

**Resolution:** check `jcmd <PID> help`, `jcmd <PID> help JFR.start`, and the JDK vendor/version. Do not assume every runtime has the same event set.

### `JFR.start` Reports Recording Already Exists or Duplicate Name

**Cause:** a recording with the same name is already running or a previous recording has not stopped.

**Resolution:** run `JFR.check`, use a different name, or stop the old recording after saving any needed data.

### `JFR.dump` Cannot Find the Recording

**Cause:** wrong name/ID or the recording has already stopped.

**Resolution:** check `JFR.check`, confirm the exact name/ID, and run `JFR.dump name=<recording-name>`.

### `.jfr` File Not Found

**Cause:** the JVM wrote the file to a different working directory, `filename` was a relative path, write permissions were insufficient, or `stop` was called without specifying `filename`.

**Resolution:** use an absolute path, verify permissions, and use `JFR.dump filename=...` to save snapshots explicitly.

### Recording File Is Too Large

**Cause:** `profile` is enabled, thresholds are too low, too many stack traces are captured, or the recording runs unbounded.

**Resolution:** check `JFR.check verbose=true`, reduce the event set, raise thresholds, set `maxage`/`maxsize`, and capture detailed data only for short windows.

### Expected Events Are Missing

**Cause:** the event is not enabled, the threshold is too high, the recording started after the event occurred, or the JVM does not support that event.

**Resolution:** inspect event metadata with `jfr metadata`, check settings with `JFR.check verbose=true`, enable the event, and adjust the threshold before the next capture.

### Custom Event Does Not Appear

**Cause:** the `@Name` does not match the setting, the event is not enabled, or the code does not call `commit()`.

**Resolution:** confirm the full event name, enable `+com.example.OrderEvent#enabled=true`, check `event.isEnabled()`, and ensure `commit()` is called.

### Recording Missing Tail Data After a JVM Crash

**Cause:** the JVM did not shut down normally to trigger `dumponexit`, or the disk repository was not preserved.

**Resolution:** configure `dumppath`/`preserve-repository` appropriately, inspect the repository after a crash, and use `jfr assemble` when valid chunks exist. Do not assume all buffered data can be recovered.

### Recording Causes Performance Degradation

**Cause:** settings are too detailed, event thresholds are too low, stack traces are too deep, or high-frequency events are enabled.

**Resolution:** switch back to `default`, limit duration, reduce the event set, raise thresholds, and re-test under a similar workload.

### Cannot Attach with `jcmd`

**Cause:** wrong PID, different user, attach mechanism disabled, mismatched container/PID namespace, or the process has exited.

**Resolution:** verify the PID on the right host/container, run as an authorized user, and check for `-XX:+DisableAttachMechanism`. If attach is unavailable, rely on startup recordings, GC logs, or preconfigured telemetry.

## 18. Production JFR Runbook

A practical operational workflow:

1. Enable a continuous recording with `settings=default`, `disk=true`, and appropriate `maxage` and `maxsize`.
2. Verify the recording with `jcmd <PID> JFR.check`.
3. Monitor the disk repository and retention limits.
4. When an alert fires, record the timestamp, PID, JDK version, workload, and symptoms.
5. Dump the time window before and around the incident using `JFR.dump begin=... end=...`.
6. If more detail is needed, run `profile` for a short, bounded duration.
7. Stop the incident recording and save the `.jfr` file.
8. Run `jfr summary` to verify duration and event counts.
9. Open in JMC or use `jfr view`/`jfr print` to analyze.
10. Correlate events with application logs, distributed traces, and metrics.
11. Document hypotheses, evidence, root cause, and changes to verify.
12. Scrub sensitive data before sharing and delete files per your retention policy.

Each recording should have a name describing the service, incident, or investigation goal. Record start/end times and the settings used so others can interpret the results.

## 19. Checklist Before Enabling JFR in Production

- [ ] Verified JDK vendor/version and supported JFR commands.
- [ ] Identified the observation goal: CPU, GC, allocation, locks, I/O, or threads.
- [ ] Selected `default` for continuous recording or `profile` for short incidents.
- [ ] Set a clear recording name.
- [ ] Bounded `maxage`, `maxsize`, and the disk repository.
- [ ] Configured `repositorypath`, `dumppath`, and write permissions if needed.
- [ ] Verified `dumponexit` and `filename` against how the service shuts down.
- [ ] Checked event thresholds, stack traces, and event enablement.
- [ ] Measured overhead in staging with a similar workload.
- [ ] Established procedures for `JFR.check`, `JFR.dump`, and `JFR.stop`.
- [ ] Confirmed how to read `.jfr` files with `jfr summary`, `jfr view`, `jfr print`, or JMC.
- [ ] Protected recording files as sensitive operational data.
- [ ] Ensured custom events do not record secrets, credentials, or personal data.
- [ ] Established retention, scrubbing, and cleanup policies.
- [ ] Verified dump files open cleanly before closing an incident.

## 20. References

- Oracle JDK 24 — Flight Recorder: https://docs.oracle.com/en/java/javase/24/jfapi/flight-recorder.html
- Oracle JDK 24 — JFR Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jfr.html
- Oracle JDK 24 — `jcmd` Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html
- Oracle JDK 24 — JFR Event Settings: https://docs.oracle.com/en/java/javase/24/jfapi/event-settings.html
- Oracle JDK 24 — Custom Events: https://docs.oracle.com/en/java/javase/24/jfapi/custom-events.html
- Oracle Java Mission Control: https://www.oracle.com/java/technologies/jdk-mission-control.html

JFR in production should be operated in two layers: a lightweight continuous recording to retain pre-incident data, and a short profile recording for deep investigation. `jcmd` controls the running JVM; `jfr` and JMC analyze the collected files. Bounding retention, selecting events by hypothesis, protecting files, and recording capture timestamps turn recordings into actionable evidence for performance investigations.