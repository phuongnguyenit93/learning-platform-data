# Recording Profiles in Java Flight Recorder

## 1. What is a recording profile?

Java Flight Recorder (JFR) is a runtime event collection framework built into the JDK. JFR records timestamped events about the JVM and the application, such as CPU sampling, method execution, allocation, garbage collection, lock contention, threads, I/O, and class loading.

A **recording profile** is a set of event configuration settings used when creating a JFR recording. The configuration determines:

- Which events are enabled or disabled.
- The duration threshold an event must exceed to be recorded.
- The sampling period for periodic events.
- Whether stack traces are attached to events.
- The level of detail in the collected data.

In the JDK, configurations are stored as `.jfc` (JFR configuration) files. The resulting recording file has the `.jfr` extension. The two files serve different roles: `.jfc` determines what data to collect; `.jfr` contains the recorded data for analysis.

Recording profiles are useful for targeted investigations, such as finding CPU-intensive methods, object allocation sites, lock contention, or GC activity within a specific time window.

## 2. Two built-in configurations: default.jfc and profile.jfc

The JDK provides two main configurations in the directory:

~~~text
<JAVA_HOME>/lib/jfr/
    default.jfc
    profile.jfc
~~~

`default.jfc` is the default configuration when starting a JFR recording without specifying settings. It collects a balanced dataset with low overhead and is suitable for continuous recording.

`profile.jfc` enables more profiling data, such as method execution sampling, allocation profiling, and more detailed runtime events. This configuration is useful when looking for bottlenecks over a short period; in return, the recording file may be larger and have a higher performance impact.

| Criterion | `default.jfc` | `profile.jfc` |
|---|---|---|
| Purpose | Continuous monitoring and initial investigation | Targeted profiling |
| Data level | Balanced set of events | More events and finer detail |
| Overhead | Low; JDK description typically under 1% | Higher; JDK 24 description typically around 2% |
| Allocation/method profiling | Lighter configuration | More detailed |
| Suitable duration | Can run continuously | Should run for short intervals |
| Use case | Capturing recent history for later analysis | Finding CPU hotspots, allocation, or lock bottlenecks |

These overhead figures are reference descriptions for the JDK configurations, not guarantees for every application. CPU load, thread count, enabled events, stack traces, garbage collector, and hardware all affect actual cost.

**Quick selection rule:** start with `default` for long-term observation. Once you have a hypothesis that needs deeper investigation, run `profile` for a short duration, reproduce the workload, and then stop the recording.

## 3. Understanding event settings inside a profile

Each JFR event can have the following main settings:

| Setting | Meaning |
|---|---|
| `enabled` | Whether to record the event |
| `threshold` | Only record duration events when the duration reaches this threshold |
| `period` | Emission interval for periodic events |
| `stackTrace` | Whether to attach a stack trace to the event |

Example:

~~~xml
<event name="jdk.JavaMonitorEnter">
  <setting name="enabled">true</setting>
  <setting name="stackTrace">true</setting>
  <setting name="threshold">10 ms</setting>
</event>
~~~

This configuration records an event when a thread waits to acquire a Java monitor for longer than 10 ms, and captures the stack trace to identify where in the code contention occurs.

Commonly encountered event types in profiles:

- `jdk.ExecutionSample`: samples stacks of executing threads for CPU/method analysis.
- `jdk.ObjectAllocationSample`: samples object allocations and their allocation stack traces.
- `jdk.JavaMonitorEnter`: records time spent waiting to enter a monitor.
- `jdk.ThreadPark` and `jdk.ThreadSleep`: observes thread parking or sleeping.
- `jdk.GarbageCollection` and GC phase events: analyzes GC cycles and pauses.
- `jdk.Compilation`: tracks JIT compilation activity.
- `jdk.SocketRead`, `jdk.SocketWrite`, `jdk.FileRead`, `jdk.FileWrite`: identifies slow I/O when enabled and exceeding the threshold.

A lower `threshold` records more events, helping reveal shorter waits, but also increases data volume and overhead. `stackTrace=true` makes events much more useful for tracing back to code, at the cost of extra collection and storage overhead.

## 4. Viewing preset profile options

Use the JDK tool to view the options supported by your installed version:

~~~bash
jfr help configure
~~~

On the tested JDK 24.0.2, `jfr configure` provides the following high-level options:

| Option | Common values | Impact |
|---|---|---|
| `gc` | `off`, `normal`, `detailed`, `high`, `all` | Increases GC detail |
| `allocation-profiling` | `off`, `low`, `medium`, `high`, `maximum` | Adjusts allocation collection level |
| `compiler` | `off`, `normal`, `detailed`, `all` | Adjusts compiler data |
| `method-profiling` | `off`, `normal`, `high`, `max` | Adjusts method profiling |
| `thread-dump` | `off`, `once`, `60s`, `10s`, `1s` | Enables periodic thread dumps |
| `exceptions` | `off`, `errors`, `all` | Adjusts exception data |
| `memory-leaks` | `off`, `types`, `stack-traces`, `gc-roots` | Increases data for leak investigation |
| `locking-threshold` | Timespan such as `10ms` | Lock event threshold |
| `file-threshold` | Timespan such as `10ms` | File I/O threshold |
| `socket-threshold` | Timespan such as `10ms` | Socket I/O threshold |
| `class-loading` | `true`, `false` | Enables/disables class loading data |

The JDK 24 `profile` preset sets `gc=detailed`, `allocation-profiling=medium`, `compiler=detailed`, `method-profiling=high`, `memory-leaks=stack-traces`, and lower lock/file/socket thresholds than `default`. Preset values can vary across JDK versions; check `jfr help configure` in your actual environment before relying on them.

Avoid enabling `gc=all` or every event just to get "as much data as possible." Some modes can generate a high volume of events, inflate file size, or alter application behavior. Choose events based on the hypothesis you want to test.

## 5. Starting a recording with a profile using jcmd

You can start a recording on a running application without modifying source code or restarting the JVM.

Find the PID:

~~~bash
jps -l
~~~

Check the syntax supported by the target JVM:

~~~bash
jcmd <pid> help JFR.start
~~~

Start a recording using `profile.jfc` that automatically stops after 60 seconds and writes to a file:

~~~bash
jcmd <pid> JFR.start name=profile settings=profile duration=60s filename=profile.jfr
~~~

Where:

- `name=profile` assigns a recording name for checking or stopping.
- `settings=profile` selects the `profile.jfc` configuration file in the JDK directory.
- `duration=60s` limits collection to 60 seconds.
- `filename=profile.jfr` specifies the output file.

If `settings` is omitted, JFR uses `default.jfc`. If `duration` is omitted, the recording continues until explicitly stopped or until the JVM exits according to the storage configuration.

Check running recordings:

~~~bash
jcmd <pid> JFR.check
~~~

Display event settings as well:

~~~bash
jcmd <pid> JFR.check name=profile verbose=true
~~~

While a recording is running, you can dump a snapshot to a file without stopping it:

~~~bash
jcmd <pid> JFR.dump name=profile filename=profile-snapshot.jfr
~~~

Manually stop the recording and write the file:

~~~bash
jcmd <pid> JFR.stop name=profile filename=profile.jfr
~~~

If `duration` was set, JFR automatically stops and writes the file when the time expires. There is no need to run `JFR.stop` again after the recording has already ended.

## 6. Starting a profile at JVM startup

If you need to collect data from the very first seconds, you can configure the recording in the `java` command:

~~~bash
java \
  -XX:StartFlightRecording:filename=profile.jfr,settings=profile,duration=60s \
  -jar application.jar
~~~

The parameters have the same meaning as in `JFR.start`:

- `filename`: path to the recording file.
- `settings=profile`: uses the profile preset.
- `duration=60s`: automatically stops after 60 seconds.

If you want to write the file on JVM shutdown, you can use:

~~~bash
java \
  -XX:StartFlightRecording:filename=profile.jfr,settings=profile,dumponexit=true \
  -jar application.jar
~~~

When `duration` is not set, the recording can continue until the JVM stops. For long-running applications, consider a continuous recording using `default` and limit data with `maxage` or `maxsize`.

## 7. Creating a custom recording profile with jfr configure

The two built-in presets are usually sufficient. When you need to collect data for a specific hypothesis, create a custom `.jfc` file based on an existing preset.

For example, create a custom profile from `profile.jfc`, set allocation/method detail, and lower the lock threshold to 5 ms:

~~~bash
jfr configure \
  --input "$JAVA_HOME/lib/jfr/profile.jfc" \
  --output custom-profile.jfc \
  allocation-profiling=medium \
  method-profiling=high \
  jdk.JavaMonitorEnter#threshold=5ms
~~~

This command creates `custom-profile.jfc` in the current directory. The new file keeps the original profile's settings and applies the specified overrides.

Use the custom file when starting a recording:

~~~bash
jcmd <pid> JFR.start \
  name=custom \
  settings=/path/to/custom-profile.jfc \
  duration=60s \
  filename=custom-profile.jfr
~~~

On Windows PowerShell, you can pass the full path to the `.jfc` file; if the path contains spaces, wrap the `settings=...` argument in double quotes.

You can also override a single event without creating a new `.jfc` file:

~~~bash
jcmd <pid> JFR.start \
  name=lock-profile \
  settings=profile \
  jdk.JavaMonitorEnter#threshold=5ms \
  duration=60s \
  filename=lock-profile.jfr
~~~

You can also add event settings using the `+EventName#setting=value` syntax as documented by `jfr configure` and `jcmd JFR.start`. Custom events must be defined in the application or a library; configuration only controls how events are recorded and does not automatically add instrumentation to source code.

**Do not modify `default.jfc` or `profile.jfc` directly in the JDK.** Create a separate custom file or use JDK Mission Control's Template Manager to copy and edit templates. This keeps the original configurations reusable and prevents JDK upgrades from overwriting your customizations.

## 8. Creating a minimal profile or combining multiple settings

If you want to start from an empty configuration, `jfr configure` supports `--input none`. For example:

~~~bash
jfr configure \
  --input none \
  --output minimal.jfc \
  +jdk.ExecutionSample#enabled=true \
  +jdk.ExecutionSample#period=20ms
~~~

This enables only the specified events, which is suitable when you know exactly what data you need to collect. An empty configuration is not equivalent to a standard profile; if required events are missing, the recording may not answer your investigation question.

You can combine multiple configuration files:

~~~bash
jfr configure \
  --input "$JAVA_HOME/lib/jfr/default.jfc,team.jfc" \
  --output combined.jfc
~~~

When multiple configurations set the same setting, they are combined in input order and settings are overridden according to the tool's rules. Inspect `--verbose` output and verify the resulting file before using it in production.

## 9. Recording profiles vs. recording duration

Profile configuration and recording mode answer two different questions:

- **Profile/settings** determine which events and what level of detail are recorded.
- **Duration/recording mode** determines how long the recording runs and how data is stored.

### Time-fixed profiling recording

This is a recording with a fixed duration, such as 30 or 60 seconds. It typically uses `profile.jfc` or a custom profile to capture rich events while reproducing an issue.

~~~bash
jcmd <pid> JFR.start name=incident settings=profile duration=60s filename=incident.jfr
~~~

When the duration expires, JFR stops the recording and writes the file. This is suitable for finding CPU hotspots, allocation pressure, lock contention, or slow I/O in a reproducible scenario.

### Continuous recording

Continuous recording typically uses `default.jfc` for low-overhead background collection. You can bound the data stored on disk:

~~~bash
jcmd <pid> JFR.start \
  name=continuous \
  settings=default \
  disk=true \
  maxage=1h \
  maxsize=250M \
  dumponexit=true
~~~

`maxage` limits the age of retained data and `maxsize` limits total size. These parameters apply when the recording writes to disk. When you need to save a snapshot for investigation:

~~~bash
jcmd <pid> JFR.dump name=continuous filename=recent.jfr
~~~

Continuous recording retains the most recent data for post-incident analysis. If you need more detail, you can run a short `profile` recording alongside the background recording, but evaluate the combined overhead and disk usage first.

## 10. Analyzing recording files

Once you have a `.jfr` file, use command-line tools for quick inspection.

View a recording overview:

~~~bash
jfr summary profile.jfr
~~~

Inspect lock contention events and stack traces:

~~~bash
jfr print --events jdk.JavaMonitorEnter profile.jfr
~~~

Inspect allocation samples:

~~~bash
jfr print --events jdk.ObjectAllocationSample profile.jfr
~~~

Inspect execution samples:

~~~bash
jfr print --events jdk.ExecutionSample profile.jfr
~~~

You can filter multiple events with a comma-separated list:

~~~bash
jfr print --events jdk.ExecutionSample,jdk.ObjectAllocationSample,jdk.JavaMonitorEnter profile.jfr
~~~

For large recordings, run `jfr summary` first to see which events are present and their counts. Then filter only the needed events instead of printing the entire file to the terminal.

### Analyzing with JDK Mission Control

JDK Mission Control (JMC) provides a GUI for analyzing recordings:

1. Open the `.jfr` file in JMC.
2. Check Automated Analysis Results for notable warnings.
3. Use Threads and Locks to find blocked, parked, or monitor-waiting threads.
4. Use Method Profiling to identify time-consuming methods.
5. Use Memory/Allocation to find classes and stack traces allocating many objects.
6. Use Garbage Collections to inspect pauses, heap usage, and collector activity.
7. Use I/O to inspect long-duration socket/file operations.
8. Open detailed events and check timestamps, threads, durations, stack traces, and context.

A single event is rarely enough to conclude root cause. Correlate timestamps with request latency, logs, metrics, and actual workload before changing code or configuration.

## 11. Complete Java 17 example: generating allocation and lock contention

Create `src/demo/RecordingProfileDemo.java`:

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;

/** Generates allocation and monitor-contention activity for JFR practice. */
public final class RecordingProfileDemo {
    private static final Object LOCK = new Object();
    private static final List<byte[]> RETAINED = new ArrayList<>();
    private static volatile long sink;

    private static void work() {
        while (!Thread.currentThread().isInterrupted()) {
            byte[] temporary = new byte[1024];
            sink += temporary.length;

            synchronized (LOCK) {
                try {
                    Thread.sleep(20);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        for (int i = 0; i < 8; i++) {
            RETAINED.add(new byte[256 * 1024]);
        }

        Thread first = new Thread(RecordingProfileDemo::work, "worker-1");
        Thread second = new Thread(RecordingProfileDemo::work, "worker-2");
        first.start();
        second.start();

        System.out.println("READY retainedKiB=" + RETAINED.size() * 256);
        Thread.sleep(120_000);
    }
}
~~~

Compile with JDK 17 or later:

~~~bash
javac --release 17 -d out src/demo/RecordingProfileDemo.java
~~~

Open Terminal 1 and run:

~~~bash
java -Xms32m -Xmx128m -cp out demo.RecordingProfileDemo
~~~

Exact stdout:

~~~text
READY retainedKiB=2048
~~~

Keep the JVM running. Open Terminal 2 and find the PID:

~~~bash
jps -l
~~~

Start a 5-second profile recording:

~~~bash
jcmd <pid> JFR.start name=profile settings=profile duration=5s filename=profile.jfr
~~~

Once the recording finishes, view the event summary:

~~~bash
jfr summary profile.jfr
~~~

Inspect lock contention:

~~~bash
jfr print --events jdk.JavaMonitorEnter profile.jfr
~~~

In a test run on Azul JDK 24.0.2, the 5-second recording captured 63 `jdk.JavaMonitorEnter` events. The output showed `worker-1` and `worker-2` taking turns holding the monitor, with sample wait durations around 20–80 ms and stack traces pointing to `RecordingProfileDemo.work()`. Event counts and durations vary depending on CPU, scheduling, and machine load.

When finished, return to Terminal 1 and press Ctrl+C to stop the application.

## 12. Reading a profile to find bottlenecks

Common indicators:

| Recording data | Investigation direction |
|---|---|
| `jdk.ExecutionSample` appearing frequently on the same stack | Inspect CPU-heavy methods and call paths |
| Many `jdk.ObjectAllocationSample` events on one class/stack | Check hot allocations, temporary objects, and unnecessary copies |
| Long `jdk.JavaMonitorEnter` durations | Identify lock owners, waiting threads, and `synchronized` blocks |
| Long `jdk.SocketRead`/`jdk.SocketWrite` durations | Check network latency, downstream services, and timeouts |
| Long `jdk.FileRead`/`jdk.FileWrite` durations | Check storage, file sizes, and synchronous I/O |
| Long or frequent GC pauses | Check allocation rate, heap pressure, and garbage collector |
| Elevated `jdk.Compilation` during warm-up | Check warm-up timing and its impact on latency |

A profile only records events that are enabled and exceed their threshold. The absence of an event in the file does not prove the phenomenon did not occur; the event might be disabled, the threshold too high, sampling might have missed it, or the recording window may not cover the incident.

When comparing before and after a change, keep the workload, recording duration, and settings identical. Changing profiles between measurements can skew conclusions due to differences in collected data.

## 13. Using path-to-gc-roots when suspecting a memory leak

JFR provides an option to collect reference paths from GC roots:

~~~bash
jcmd <pid> JFR.start \
  name=leak-investigation \
  settings=profile \
  path-to-gc-roots=true \
  duration=60s \
  filename=leak-investigation.jfr
~~~

This data is useful for finding why objects remain reachable and where potential leak candidates were allocated. With `settings=profile`, JFR can also record the allocation stack trace for tracked objects.

Collecting path-to-GC-roots data is expensive and can cause JVM pauses during processing. Enable it only when you already suspect a memory leak and accept the diagnostic cost. For routine checks, use a standard profile first.

## 14. Common errors and troubleshooting

### settings=profile not found

Check whether the running JVM has `JAVA_HOME/lib/jfr/profile.jfc`. Run `jfr help configure` and `jcmd <pid> help JFR.start` to verify the exact version's options.

### Custom .jfc is not loaded

Use the full path in `settings=/path/to/custom.jfc`. Verify that the file exists, is valid XML, and is readable by the user running the JVM.

### Recording has very few events

Verify that the events have `enabled=true`, the threshold is not too high, the period is not too long, and the workload reproduces the target behavior. Run `jcmd <pid> JFR.check name=profile verbose=true` to inspect the active settings.

### Recording file is too large

Shorten the duration, use `default` if appropriate, raise thresholds for duration events, reduce sampling frequency, or enable only the needed event groups. Bound continuous recordings with `maxage` and `maxsize`.

### Overhead increases after enabling profile

`profile` collects more data than `default`. Shorten the duration, dial back allocation/method profiling, raise thresholds, or switch back to `default` once diagnosis is complete.

### No lock contention observed

Verify whether threads are actually waiting on a monitor, whether `jdk.JavaMonitorEnter` is enabled, and whether the threshold is appropriate. `Thread.sleep` or `Thread.park` does not equate to monitor contention.

### jfr print shows no events

Run `jfr summary` to confirm whether the event is present in the file. If not, recheck settings, thresholds, recording timing, and workload.

### jfr configure reports an invalid option

Supported options depend on the JDK version. Run `jfr help configure` and use the exact supported option names and values. Do not copy presets from a newer JDK to an older JDK without checking.

## 15. Security and operations

JFR recordings can contain stack traces, class/method names, file paths, JVM info, system properties, environment variables, and application-defined events. Some events may expose operational data or sensitive information.

Before sharing a `.jfr` file:

- Review the event settings and recording contents.
- Restrict file read permissions and retention time.
- Use file transfer channels approved by your organization.
- Do not upload recordings to public services without inspecting the data first.
- Keep record of the JDK version, PID, timestamp, settings, and workload so results remain comparable.

When running `profile` in production, choose an appropriate load window, bound the duration, and check CPU, disk, and memory headroom before starting. Whenever possible, reproduce the issue in staging before increasing collection levels.

## 16. Checklist for choosing and using recording profiles

- [ ] Understand that `.jfc` is the configuration and `.jfr` is the recording data file.
- [ ] Use `default` for continuous recording or background observation.
- [ ] Use `profile` for time-bounded profiling.
- [ ] Check presets and event settings with `jfr help configure`.
- [ ] Check syntax on the target JVM with `jcmd <pid> help JFR.start`.
- [ ] Select events based on the hypothesis being tested.
- [ ] Tune `enabled`, `threshold`, `period`, and `stackTrace` as needed.
- [ ] Create custom `.jfc` files using `jfr configure` or JMC Template Manager.
- [ ] Never edit `default.jfc` or `profile.jfc` directly.
- [ ] Set `duration` for profiling recordings.
- [ ] Use `JFR.check`, `JFR.dump`, and `JFR.stop` to manage running recordings.
- [ ] Use `jfr summary`, `jfr print`, or JMC for analysis.
- [ ] Enable `path-to-gc-roots` only when suspecting a memory leak.
- [ ] Protect `.jfr` files as operational data that may contain sensitive information.

## 17. References

- [Oracle JDK 24 — Flight Recorder Configurations](https://docs.oracle.com/en/java/javase/24/jfapi/flight-recorder-configurations.html): roles of `default.jfc` and `profile.jfc`, file locations, and creating custom configurations.
- [Oracle JDK 24 — The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html): syntax for `JFR.start`, `JFR.check`, `JFR.dump`, `JFR.stop`, `settings`, `duration`, and `path-to-gc-roots`.
- [Oracle JDK 24 — The java Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html): `-XX:StartFlightRecording` option, profile settings, and startup recordings.
- [Oracle JDK 24 — Configure Events and Flight Recorder](https://docs.oracle.com/en/java/javase/24/jfapi/configuration.html): `enabled`, `threshold`, `period`, and `stackTrace` event settings.
- [JDK Mission Control 9 — Using JDK Flight Recorder](https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/using-jdk-flight-recorder.html): time-fixed/continuous recordings, template selection, and analysis with JMC.

Recording profiles let you tailor JFR data volume to your diagnostic question. Choose `default` for background monitoring, use `profile` for short windows when you need more events and stack traces, and refine a custom `.jfc` once you know the exact data you need to collect.
