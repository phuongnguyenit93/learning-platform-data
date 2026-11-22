# Recording Duration in Java Flight Recorder

## Objectives

After this lesson, you will be able to choose an appropriate duration for a Java Flight Recorder (JFR) recording; distinguish between time-fixed and continuous recordings; use `duration`, `delay`, `maxage`, and `maxsize` for their intended purposes; start, check, dump, and stop recordings with `jcmd`; configure recordings at JVM startup; manage recordings with JDK Mission Control (JMC); control duration via the JFR Recording API; analyze `.jfr` files; and balance detail level, overhead, storage capacity, and the incident window under investigation.

## 1. What Is Recording Duration?

Java Flight Recorder (JFR) is a framework for collecting events from the JVM, JDK, operating system, and Java applications. A recording stores timestamped events so you can analyze process behavior after an incident occurs.

**Recording duration** is the length of time JFR continues collecting events after a recording starts. For example, a recording with a 10-minute duration automatically ends approximately 10 minutes after its actual start time.

Duration affects:

- The time span of the application being observed.
- The likelihood of capturing issues that only appear periodically or under load spikes.
- The volume of events and the recording file size.
- How long JFR continues running and the cumulative overhead.
- The ability to retain data before, during, and after an incident.

A recording that is too short may miss rare occurrences. A recording that is too long with a verbose event profile can produce large files and add unnecessary overhead. Choose the duration based on your investigation question and how frequently the issue occurs.

JFR supports two primary usage modes:

- **Time-fixed recording:** records for a defined period and then stops automatically. Suitable for targeted profiling, verifying a deployment, running a load test, or capturing a known reproduction window.
- **Continuous recording:** runs continuously, retaining a rolling window of the most recent data bounded by time or size limits. When an investigation is needed, operators dump the relevant data to a file.

## 2. Distinguishing duration, delay, maxage, and maxsize

These four parameters relate to time or storage, but they control different aspects.

| Parameter | Controls | Example |
|---|---|---|
| duration | How long the recording runs before stopping automatically | 10m |
| delay | How long to wait after the start request before recording begins | 30s |
| maxage | Retains data on disk only for the most recent time window | 2h |
| maxsize | Limits the amount of data retained on disk | 512M |

### duration — recording run time

`duration` defines the recording lifecycle. When the duration expires, the recording stops automatically. With `jcmd` in JDK 26, values use `s`, `m`, or `h` units; `0s` means unlimited duration.

~~~bash
jcmd <PID> JFR.start name=checkout-profile settings=profile duration=10m filename=checkout-profile.jfr
~~~

The recording starts immediately and stops automatically after 10 minutes. The file is written to `checkout-profile.jfr` when the recording ends.

### delay — postponing the start time

`delay` specifies the wait period before JFR begins recording events. It is useful when you want the application to warm up and stabilize before profiling, or when you want the recording to start close to a load test.

~~~bash
jcmd <PID> JFR.start name=after-warmup settings=profile delay=2m duration=8m filename=after-warmup.jfr
~~~

JFR waits 2 minutes, then records for 8 minutes. The end time is approximately 10 minutes after issuing the command, plus command-processing time and scheduling variance.

### maxage — limiting the age of retained data

`maxage` limits how long data is kept in the disk repository. When data becomes older than this limit, the JVM discards old chunks.

~~~bash
jcmd <PID> JFR.start name=rolling settings=default disk=true maxage=2h
~~~

The recording can continue running longer than two hours, but the repository only retains data within roughly the most recent two-hour window.

### maxsize — limiting the size of retained data

`maxsize` limits the disk space used by the recording. When the limit is exceeded, JFR discards old chunks to make room for new data.

~~~bash
jcmd <PID> JFR.start name=rolling settings=default disk=true maxsize=512M
~~~

If events are generated rapidly, the actual retained time window may be shorter than expected because the size limit is reached before `maxage`.

### duration does not replace maxage/maxsize

- `duration` limits the total lifetime of the recording.
- `maxage` and `maxsize` limit how much historical data is kept in the repository while a recording is running on disk.

A recording with a 30-minute `duration` but a 5-minute `maxage` may only contain data from the final 5 minutes when it finishes. Similarly, `maxsize` can cause old chunks to be evicted before `duration` expires.

If you want to capture an entire 15-minute profiling run, ensure `maxage`/`maxsize` are large enough or avoid setting unnecessary repository limits. If you want to keep a recent window for unexpected incidents, use a continuous recording with finite `maxage`/`maxsize`.

## 3. Time-Fixed vs. Continuous Recordings

| Criterion | Time-fixed | Continuous |
|---|---|---|
| Lifecycle | Stops automatically after `duration` | Continues until stopped or JVM exits |
| Retained data | Entire window within repository limits | Most recent window per `maxage`/`maxsize` |
| File retrieval | File is written when recording stops | Dumped on demand while recording continues |
| Purpose | Profiling a known scenario | Investigating rare or unpredictable incidents |
| Common template | `profile` or `default` depending on goal | `default` or `Continuous` |

### When to use a time-fixed recording

Choose time-fixed when you can reproduce an issue within a known time window; want to measure performance before and after a change; run a benchmark or load test with a fixed duration; or want to strictly bound profiling time in production.

~~~bash
jcmd <PID> JFR.start name=api-profile settings=profile duration=5m filename=api-profile-%p-%t.jfr
~~~

### When to use a continuous recording

Choose continuous when incidents occur randomly, you do not know when latency/GC anomalies will happen, or you need to retain data leading up to an alert trigger.

~~~bash
jcmd <PID> JFR.start name=production-ring settings=default disk=true maxage=6h maxsize=512M dumponexit=true
~~~

In this configuration, `duration` defaults to `0s`, meaning the recording does not stop automatically based on time. When analysis is needed, dump a snapshot to a separate file.

## 4. Choose a Template Before Deciding on Duration

Duration only specifies how long the recording runs. The template and event settings determine what kind of data is collected during that time.

| Template | Data | Overhead |
|---|---|---|
| default.jfc | Baseline event set useful for continuous monitoring | Low |
| profile.jfc | More detailed events, useful for profiling | Higher than default |

### default

`default` is suited for continuous recordings or long-running background observation. This template is designed for low overhead. A continuous recording using `default` does not collect heap statistics or allocation profiling by default.

### profile

`profile` collects more data to identify hot methods, allocations, contention, and bottlenecks. Because more events are enabled, this template can incur higher overhead and larger file sizes. Use it for short periods when higher detail is needed.

### Adjusting event settings

Event settings control which events are recorded, whether stack traces are captured, sampling periods, and thresholds for duration events.

Lower thresholds reveal more events but can increase overhead and recording size. Inspect configurations with the `jfr` tool and check event-specific documentation before making changes. Do not enable all events at maximum detail simply because a recording is time-bounded.

## 5. Recording Duration vs. Event Duration

JFR has two time-related concepts that are completely distinct:

- **Recording duration:** the total time JFR collects data, such as 10 minutes.
- **Event duration/threshold:** the duration of an application operation, or the minimum threshold for an event to be recorded, such as a lock wait lasting 20 ms.

For example, a 10-minute recording might capture hundreds of `JavaMonitorEnter` events. Each event has its own duration indicating how long a thread waited on the monitor.

If the threshold is 20 ms, shorter waits may not be recorded under that event configuration. The recording still runs for the full 10 minutes; the threshold does not stop the recording after 20 ms.

JFR also has periodic events, which are recorded on a sampling interval. Periodic events have their own `period`, not a recording duration.

When an expected event is missing from a file, check whether the event is enabled, whether the threshold is too high, and whether the period is appropriate. Do not conclude that the recording duration was too short if the real issue lies in the event settings.

## 6. Starting a Timed Recording with jcmd

`jcmd` is the standard way to control JFR on a running JVM.

### Identify the PID

~~~bash
jcmd -l
~~~

Select the correct PID for the application. `jcmd` must run on the same machine as the JVM and under the same effective user/group that launched the JVM.

### Start a 10-minute recording

~~~bash
jcmd <PID> JFR.start name=incident-10m settings=profile duration=10m filename=incident-10m-%p-%t.jfr
~~~

- `name`: identifier for the recording in subsequent JFR commands.
- `settings`: template or event configuration file.
- `duration`: collection time before stopping automatically.
- `filename`: file path written when the recording stops.
- `%p`: replaced by the JVM's PID.
- `%t`: replaced by the current timestamp.

If `name` is omitted, the JVM generates a name and prints it in the command output. Note the returned name to use with `JFR.check`, `JFR.dump`, and `JFR.stop`.

### Check the recording

~~~bash
jcmd <PID> JFR.check
jcmd <PID> JFR.check name=incident-10m verbose=true
~~~

Verify that the recording is running, along with its start time, settings, and state. Do not rely solely on the start command returning success; verify that the recording with the expected name is active.

### Wait for the recording to finish automatically

When `duration` expires, JFR stops the recording automatically. If `filename` was configured, the data is written to that file when the recording ends.

Verify that the file exists, has a reasonable size, and can be read by the `jfr` tool or JMC.

### Stop early before duration expires

~~~bash
jcmd <PID> JFR.stop name=incident-10m filename=incident-10m-early-stop.jfr
~~~

When stopping manually, pass `filename` to save the data. Per JDK 26 syntax, if `JFR.stop` is called without a file path, the recording data is discarded. Use a distinct filename to avoid overwriting an earlier recording.

## 7. Dumping a Snapshot Without Stopping the Recording

For continuous recordings, you do not need to stop the recording to retrieve diagnostic data.

~~~bash
jcmd <PID> JFR.dump name=production-ring filename=incident-snapshot.jfr
~~~

`JFR.dump` writes the currently available data to a file while the recording continues running. You can keep monitoring and dump again if another incident occurs.

### Capturing only a specific time window

`JFR.dump` supports `begin` and `end` to select a data range. You can use timestamps or relative durations from the current time.

~~~bash
jcmd <PID> JFR.dump name=production-ring begin=-15m filename=last-15-minutes.jfr
~~~

Example using explicit timestamps:

~~~bash
jcmd <PID> JFR.dump name=production-ring begin=2026-11-10T09:00:00 end=2026-11-10T09:15:00 filename=morning-window.jfr
~~~

Timestamps must be in a format parseable by `LocalTime`, `LocalDateTime`, or `Instant`. `begin` and `end` reference timestamps inside the recording.

Dumping a shorter range does not alter the duration or state of the underlying recording. It only selects which data is written to the snapshot file.

### How does dump differ from stop?

| Command | Result | Underlying recording |
|---|---|---|
| JFR.dump | Writes a snapshot to a file | Continues running |
| JFR.stop | Ends the recording and saves to file if `filename` is given | Stopped |
| duration expires | Recording stops automatically | Stopped automatically |

If you are investigating an incident and want to keep background collection running, use `JFR.dump`. If you are finished and want to end the recording, use `JFR.stop`.

## 8. Using Continuous Recordings with Time and Size Limits

Continuous recordings are useful when you cannot predict when an incident will occur.

~~~bash
jcmd <PID> JFR.start name=rolling-default settings=default disk=true maxage=6h maxsize=512M dumponexit=true
~~~

Meaning:

- `duration` defaults to `0s`, so the recording runs continuously.
- `disk=true` writes data to the disk repository.
- `maxage=6h` retains data for at most a 6-hour window.
- `maxsize=512M` caps repository disk usage.
- `dumponexit=true` requests a dump when the JVM shuts down.

JFR discards old chunks when `maxage` or `maxsize` is exceeded. Therefore, the actual retained window may be shorter than six hours if the recording generates events quickly and hits the size limit first.

### Capturing data when an alert fires

~~~bash
jcmd <PID> JFR.check name=rolling-default
jcmd <PID> JFR.dump name=rolling-default begin=-20m filename=incident-last-20m.jfr
~~~

The dump command extracts the most recent 20 minutes still retained in the repository. The recording keeps running to capture subsequent incidents.

If you need more data after the alert, wait an appropriate interval and dump again with a different filename.

### Stopping a continuous recording

~~~bash
jcmd <PID> JFR.stop name=rolling-default filename=rolling-final.jfr
~~~

Provide `filename` to save the final data. If the recording was configured with `dumponexit`, the JVM can also dump on shutdown according to that setting.

### Choosing maxage and maxsize

Base your choices on actual event rates and disk capacity:

- Longer `maxage` retains more history.
- Larger `maxsize` preserves a longer window under high event rates.
- `profile` typically generates data faster than `default`.
- A `maxsize` that is too small can cause data to be evicted before an incident is detected.
- Excessive `maxage`/`maxsize` can consume significant disk space.

Monitor recording sizes and filesystem usage in a staging environment before applying limits in production.

## 9. Starting a Recording at JVM Startup

You can configure JFR using the `-XX:StartFlightRecording` option on the `java` launcher. This is useful when you need to capture startup behavior or want the recording active before the application receives traffic.

~~~bash
java -XX:StartFlightRecording.delay=20s,duration=60s,name=startup-profile,filename=startup-profile.jfr,settings=profile -jar app.jar
~~~

Where:

- `delay=20s`: waits 20 seconds after application launch.
- `duration=60s`: records for 60 seconds after the delay ends.
- `name`: recording name.
- `filename`: output file.
- `settings=profile`: uses the `profile` template.

Recording begins roughly 20 seconds after process creation and stops roughly 80 seconds after launch. If the JVM does not run long enough for `duration` to complete, the recording may end due to JVM shutdown; consider `dumponexit` when you need data saved on shutdown.

### Continuous recording from startup

~~~bash
java -XX:StartFlightRecording=settings=default,disk=true,maxage=6h,maxsize=512M,dumponexit=true -jar app.jar
~~~

This configuration creates a continuous recording with bounded retention. You can later use `jcmd JFR.dump` to extract a time window when needed.

Do not add `profile` to every production JVM by default. Choose settings based on your goals, verify overhead, and ensure adequate repository space.

## 10. Managing Recording Duration with JDK Mission Control

JDK Mission Control (JMC) provides a GUI for starting and managing recordings.

Basic workflow:

1. Open JMC and locate the JVM in the JVM Browser.
2. Select the target JVM.
3. Open Start Flight Recording.
4. Choose Time fixed recording or Continuous recording.
5. Select a template such as Continuous/`default` or Profiling/`profile`.
6. For time-fixed, enter the duration and destination file.
7. For continuous, set maximum age or maximum size.
8. Review event settings and thresholds if needed.
9. Start the recording.
10. When needed, dump a snapshot, stop, or close the recording depending on your goal.

JMC lets you manage running recordings: dump everything, dump the most recent portion, edit settings, stop, or close. Stopping a profiling recording creates the recording file; closing a recording may discard data if it has not been dumped.

### Choosing time-fixed in JMC

Use this when you have a known profiling window, such as selecting a 5-minute profile during a load test.

### Choosing continuous in JMC

Use this for background monitoring. Set maximum age/size to bound historical data and dump when an incident occurs.

UI labels may vary across JMC versions. Verify field names and behavior in the JMC version you are using.

## 11. Using the JFR Recording API to Set Duration in Java

The JDK provides the `jdk.jfr` API. The `Recording` class can configure name, template, duration, max age, max size, and destination file.

| Method | Purpose |
|---|---|
| setDuration(Duration) | Sets how long the recording runs before stopping automatically |
| setMaxAge(Duration) | Limits the age of data retained in the disk repository |
| setMaxSize(long) | Limits the size of data retained in the repository |
| setDestination(Path) | Sets the destination file written when the recording stops |
| setToDisk(boolean) | Controls whether the recording continuously writes to the disk repository |
| scheduleStart(Duration) | Schedules the recording to start after a delay |
| start() | Starts the recording |
| stop() | Stops the recording |
| dump(Path) | Writes recording data to a file |
| close() | Releases resources associated with the recording |

Setting `duration` and `destination` before calling `start()` is a straightforward way to create a time-fixed recording with automatic file output.

### Java 17+ example: recording that stops automatically after 5 seconds

Create `DurationRecordingDemo.java`:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Configuration;
import jdk.jfr.Recording;

public class DurationRecordingDemo {
    public static void main(String[] args) throws Exception {
        Path output = Path.of("duration-demo.jfr");

        try (Recording recording =
                     new Recording(Configuration.getConfiguration("default"))) {
            recording.setName("duration-demo");
            recording.setToDisk(true);
            recording.setDuration(Duration.ofSeconds(5));
            recording.setDestination(output);

            recording.start();
            System.out.println("recording-started");

            Thread.sleep(7_000);

            System.out.println(
                    "recording-file-exists=" + Files.exists(output));
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 DurationRecordingDemo.java
java DurationRecordingDemo
~~~

Exact output:

~~~text
recording-started
recording-file-exists=true
~~~

Explanation:

- `Configuration.getConfiguration("default")` selects the `default` template.
- `setDuration` configures the recording to stop automatically after 5 seconds.
- `setDestination` sets the file written when the recording stops.
- `setToDisk(true)` enables writing recording data to the disk repository.
- `Thread.sleep` for 7 seconds waits longer than `duration`, giving the recording enough time to finish and write the file.
- `try-with-resources` closes the `Recording` when the block exits.

The file `duration-demo.jfr` is created in the working directory. Its size and contained events depend on the JDK, environment, and process activity.

### Continuous recording example via the API

If you want a recording that does not stop automatically, omit `setDuration` or do not set a duration. You can bound the data retained in the repository:

~~~java
Recording recording =
        new Recording(Configuration.getConfiguration("default"));

recording.setName("continuous-demo");
recording.setToDisk(true);
recording.setMaxAge(Duration.ofHours(2));
recording.setMaxSize(256L * 1024 * 1024);
recording.start();
~~~

This snippet only illustrates configuration and startup; the application must manage the recording lifecycle, dump data when needed, and call `stop`/`close` when done.

## 12. Choosing Duration Based on Investigation Goals

There is no single duration that fits every application. Start from how often the issue occurs and how much data is needed for analysis.

| Goal | Selection approach |
|---|---|
| Inspect a reproducible slow operation | Short recording bracketing the operation |
| Fixed-duration load test | Record from before the test starts until after it finishes |
| Compare before/after deployment | Two recordings with equivalent duration and workload |
| Investigate rare GC pauses | Recording longer than the occurrence interval, or continuous |
| Investigate sudden latency spikes | Continuous with `maxage`/`maxsize`, then dump on alert |
| Inspect startup | Start at launch or use a short delay |
| Investigate a memory leak | Recording long enough to show allocation/live-set trends; may need multiple snapshots |

### Scenario 1: issue occurs every minute

If a scheduled task runs every minute, a 10-second recording may miss it entirely. Choose at least a few cycles to have data for comparison.

### Scenario 2: error appears after several hours

If an issue typically surfaces after 3 hours, a 10-minute time-fixed recording started right after deployment will not be enough. Use a continuous recording with a sufficiently long `maxage`, or schedule a recording near the expected time.

### Scenario 3: precise latency measurement

Choose a short window that cleanly brackets the target operation, and use an appropriate template and event settings. Do not extend a `profile` recording unnecessarily, as it collects out-of-scope data and may add overhead.

### Scenario 4: comparing two versions

Keep duration, template, event thresholds, workload, and warm-up time comparable. If one recording uses `default` for 5 minutes and the other uses `profile` for 30 minutes, differences may stem from collection settings rather than application changes.

## 13. Estimating File Size and Managing Disk Space

JFR file size depends on duration, template, event settings, event rate, thread count, stack traces, thresholds/periods, profiling detail, and disk repository configuration.

You cannot derive exact file size from duration alone. Two 10-minute recordings can differ in size by several multiples.

### Measure empirically

Run a test recording in a production-like environment:

~~~bash
jcmd <PID> JFR.start name=size-test settings=profile duration=5m filename=size-test.jfr
~~~

After the recording finishes, check the file size using OS tools.

Linux:

~~~bash
ls -lh size-test.jfr
~~~

Windows PowerShell:

~~~powershell
Get-Item size-test.jfr | Select-Object Name, Length, LastWriteTime
~~~

From the test result, estimate storage based on actual event rates, while leaving headroom because traffic and event volume can fluctuate.

### Disk repository and output file

JFR may write chunks to a temporary repository while a recording runs. When dumped or stopped, data is written to your chosen output file.

- The repository holds temporary data while the recording is active.
- The destination/output file is the artifact for analysis or archival.
- `maxage`/`maxsize` bound the data kept in the repository when recording to disk.
- Output files must be protected and managed under their own retention policy.

Do not delete the repository or temporary files while the JVM is using them. Use JFR commands to manage recordings and let the JVM handle old chunk eviction.

## 14. Analyzing a Recording File After Completion

Once you have a `.jfr` file, you can use JMC or the JDK `jfr` tool.

### View summary

~~~bash
jfr summary duration-demo.jfr
~~~

`summary` shows metadata, recording time span, event counts, and overall size.

### Print specific events

~~~bash
jfr print --events jdk.GCPhasePause duration-demo.jfr
~~~

You can filter for events relevant to your goal, such as GC pauses, execution samples, monitor waits, socket read/write, or allocation events if enabled by the template.

### Open in JMC

Open the `.jfr` file in JMC to analyze recording duration and timeline, CPU usage and method samples, garbage collection and pause times, thread states, monitor contention and lock waits, file/socket I/O, allocation and memory behavior if collected by event settings, and custom application events.

JFR only stores events that are enabled and meet their threshold/period. The absence of an event in the file does not prove that the activity did not occur.

## 15. Performance Impact and Limitations When Choosing Duration

JFR is designed to collect runtime data with low overhead, but actual overhead depends on event settings.

1. Start with `default` when you need continuous recording.
2. Use `profile` for short windows when more detailed data is required.
3. Choose a duration long enough to cover the scenario, and no longer than necessary when using `profile`.
4. Use `maxage`/`maxsize` for continuous recordings to prevent unbounded repository growth.
5. Check disk space, quotas, and retention policies.
6. Limit stack traces or expensive events when they are not needed.
7. Do not lower event thresholds aggressively in production without measuring overhead first.
8. Record settings, duration, JDK version, and workload for comparison.

Some event settings can cause the JVM to gather extra information or perform additional work. For example, enabling heap statistics can trigger old GCs at the start and end of a test run, increasing pause times. If you are measuring pause-sensitive latency, do not enable heap statistics unless required by the investigation.

A longer duration does not make an individual event more expensive, but it extends the collection period and increases the total data that may be written. Event settings and event rates largely determine overhead and file size.

## 16. Common Errors and Troubleshooting

### Recording stops earlier than expected

**Symptom:** the recording ends before the expected time.

**Cause:** `duration` was set too short, the recording was stopped via `JFR.stop`, the JVM shut down, or the managing application closed the recording.

**Resolution:** check `JFR.check`, the start command, shutdown timing, and where the `Recording` API lifecycle is managed. Distinguish between recording `duration` and `delay` before starting.

### Recording runs indefinitely without stopping

**Symptom:** waited past the expected duration, but the recording is still active.

**Cause:** `duration` was not set, `duration=0s`, or the command targeted the wrong JVM or recording.

**Resolution:** verify the correct PID and `name` with `JFR.check`; set a positive `duration` or stop with `JFR.stop` and a `filename`.

### Recording finished but no file exists

**Symptom:** the recording stopped, but no `.jfr` file is found.

**Cause:** wrong `filename`, missing directory, insufficient write permissions, full disk, or `JFR.stop` was called without `filename`.

**Resolution:** check destination path, permissions, and disk space; pass `filename` explicitly to `JFR.start` or `JFR.stop`; check logs and generated files.

### Continuous recording only contains recent data

**Symptom:** the dumped file lacks data from when the recording started.

**Cause:** `maxage` or `maxsize` evicted older chunks from the repository.

**Resolution:** increase retention if a longer window is needed; monitor event rates and dump before data is evicted.

### Recording file is too large

**Symptom:** the file grows rapidly or consumes excessive disk space.

**Cause:** `profile` settings, high event rate, many stack traces, threshold too low, or duration too long.

**Resolution:** use `default` for background monitoring; shorten `profile` runs; raise thresholds appropriately; cap `maxage`/`maxsize`; measure file sizes in staging first.

### Recording duration was long enough, but expected events are missing

**Symptom:** the file covers the right time span but lacks the events needed for analysis.

**Cause:** events were not enabled, threshold is too high, sampling period is too sparse, or the template does not collect that event type.

**Resolution:** inspect event settings in JMC/JFR; choose an appropriate template; verify event names and thresholds; increase detail only after understanding the overhead.

### Dumping a snapshot does not stop the recording

**Symptom:** after `JFR.dump`, `JFR.check` still shows the recording running.

**Cause:** this is the expected behavior of `JFR.dump`.

**Resolution:** continue collecting if needed; use `JFR.stop` when you want to end the recording.

### maxage/maxsize has no effect

**Symptom:** data is not bounded as expected.

**Cause:** `disk=false` or invalid parameter; `maxsize` is smaller than the configured `maxchunksize`.

**Resolution:** confirm `disk=true`; check `JFR.configure`; choose `maxsize` not smaller than `maxchunksize`; use valid units.

### Recording API does not create a file automatically

**Symptom:** the Java program finishes, but the destination file does not appear.

**Cause:** `start` was not called, destination was not set, duration had not elapsed, the recording was closed before data was written, or the path is not writable.

**Resolution:** call `setDestination` before `start`; call `setDuration` before `start`; wait past `duration`; check for `IOException` and write permissions; if not using `destination`, call `stop` and then `dump(Path)`.

## 17. Recommended Operational Workflows

### Targeted profiling

1. Identify the operation or workload to measure.
2. Choose `profile` or appropriate event settings.
3. Set `duration` to cover the entire workload.
4. Specify a unique `filename` and a directory with sufficient space.
5. Start the recording.
6. Verify with `JFR.check`.
7. Wait for automatic stop or stop early with `filename`.
8. Verify the file and open it in JMC.
9. Record settings, duration, JDK version, and workload.

### Continuous production monitoring

1. Choose the `default`/`Continuous` template.
2. Start the recording at startup or attach with `jcmd`.
3. Set finite `maxage` and `maxsize`.
4. Enable `dumponexit` if you need to preserve the recording on JVM shutdown.
5. Monitor recording status and repository disk usage.
6. When an alert fires, dump the most recent data window.
7. Keep the recording running if ongoing monitoring is needed.
8. Stop the recording when collection is no longer needed.
9. Analyze the file and store it according to your retention policy.

### Comparing before and after a change

1. Use the same template and event settings.
2. Use equivalent durations.
3. Keep workload, warm-up, and environment consistent.
4. Save each run to a separate file named with version and timestamp.
5. Compare the same event groups in JMC.
6. Distinguish real application changes from differences caused by recording configuration.

## 18. Recording Duration Checklist

### Before starting

- [ ] Define the goal: fixed profiling or continuous monitoring.
- [ ] Choose the `default` or `profile` template.
- [ ] Choose a `duration` long enough to cover the scenario if time-fixed.
- [ ] Choose `delay` if you want to postpone the start time.
- [ ] Choose `maxage`/`maxsize` if running a continuous recording.
- [ ] Verify `disk=true` when using `maxage`/`maxsize`.
- [ ] Specify `filename` and output directory.
- [ ] Check disk space, quotas, and write permissions.
- [ ] Review event settings, thresholds, and periods.

### During the recording

- [ ] Confirm the correct JVM PID and recording name.
- [ ] Use `JFR.check` to verify status.
- [ ] Monitor repository disk usage.
- [ ] Dump a snapshot with `JFR.dump` if needed while keeping the recording active.
- [ ] Do not confuse recording `duration` with event thresholds.
- [ ] Do not stop the recording before saving needed data.

### After the recording

- [ ] Confirm the recording has stopped or is still running as intended.
- [ ] Verify that the `.jfr` file exists and has a reasonable size.
- [ ] Use `jfr summary` or JMC to inspect the file.
- [ ] Record the actual duration, template, and event settings.
- [ ] Correlate recording timestamps with the incident timeline.
- [ ] Protect the file and apply your retention policy.
- [ ] Compare recordings under equivalent workload conditions.

## 19. Official References

- [The jcmd Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html) — `JFR.start`, `duration`, `delay`, `maxage`, `maxsize`, `JFR.check`, `JFR.dump`, and `JFR.stop`.
- [The java Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html) — `-XX:StartFlightRecording`, `duration`, `delay`, `filename`, `maxage`, `maxsize`, and `dumponexit`.
- [Recording — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/Recording.html) — `setDuration`, `setMaxAge`, `setMaxSize`, `setDestination`, `scheduleStart`, `start`, `stop`, and `dump`.
- [Flight Recorder — JDK Mission Control User Guide](https://docs.oracle.com/en/java/java-components/jdk-mission-control/8/user-guide/using-jdk-flight-recorder.html) — time-fixed/continuous recordings, templates, duration, and managing recordings in JMC.
- [Diagnostic Tools — Java SE 26 Troubleshooting Guide](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html) — ways to create a Flight Recording from JMC, startup flags, and diagnostic commands.
- [Troubleshoot Performance Issues Using Flight Recorder — Java SE 26](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshoot-performance-issues-using-jfr.html) — events, thresholds, overhead, and using recordings to find bottlenecks.

Recording duration determines how long JFR collects data; `maxage` and `maxsize` determine which historical data is retained; event settings determine the event types and level of detail. Choose these three factors together to capture the right incident window, preserve sufficient evidence, and control overhead and storage usage.