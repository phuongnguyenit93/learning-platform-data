# Continuous Recording with Java Flight Recorder

**Continuous recording** is the continuous event-recording mode of Java Flight Recorder (JFR), designed to retain a recent window of JVM data. When a rare incident occurs, operators can export the data from the time window immediately preceding the incident for analysis, even if no one had manually started profiling at the time.

JFR is built into the HotSpot JDK. It records timestamped events about the JVM and the application, such as CPU samples, garbage collection, thread scheduling, lock contention, class loading, and I/O. For continuous recording, the `default.jfc` configuration is typically the appropriate starting choice because it is designed for long-running recording with low overhead.

Continuous recording operates as a bounded history: older data is gradually discarded when it exceeds the configured retention time or storage size. When an investigation is needed, use `jcmd <pid> JFR.dump` to export a `.jfr` file for the time range you want to inspect. The dump command does not stop the recording; the JVM continues recording after creating the file.

## 1. What Problem Does Continuous Recording Solve?

Many production incidents are not easy to reproduce:

- Requests occasionally experience latency spikes for a few seconds.
- CPU spikes suddenly and then returns to normal.
- Threads wait on locks or I/O for a brief period.
- Garbage collection has abnormal pauses.
- A service experiences periodic spikes in allocation rate.
- The application slows down before health checks report an error.
- An incident occurs outside working hours when no one has a profiler attached.

If profiling is only started after an alert fires, the data leading up to the incident may already be lost. Continuous recording keeps a window of recent events so it can be reviewed afterward.

For example: configure retention for the last six hours. When an alert arrives at 14:00, an operator can export data from 13:30 onward and inspect threads, GC, CPU, locks, or I/O around the anomalous period.

Continuous recording is suited for post-incident investigation and tracking hard-to-reproduce issues. It does not replace metrics, application logs, distributed traces, or alerting; those sources help identify the timestamp and requests to investigate.

## 2. What Types of Data Does JFR Record?

JFR records data as timestamped events. Depending on the configuration, events can belong to the following categories:

| Event Category | Example Data | Investigation Question |
|---|---|---|
| CPU and execution | Execution samples, CPU load | Which thread or method is consuming CPU? |
| Thread and scheduling | Thread park, sleep, start/end | Is a thread running, waiting, or delayed? |
| Synchronization | Monitor enter, lock contention | Which thread is waiting on a lock and for how long? |
| Garbage collection | GC start/end, pause, heap summary | When did GC occur and how long did the pause last? |
| Memory and allocation | Allocation samples, object allocation when enabled | Which code is allocating many objects? |
| Class loading | Class load/unload | Is there an abnormal increase in classes or classloaders? |
| I/O | File read/write, socket read/write | Is latency coming from file or network I/O? |
| JVM and environment | Runtime, process, CPU, and OS data | In what environment is the JVM running? |
| Custom event | Application-defined events | How long did a business step take? |

JFR includes duration events, instant events, sample events, and custom events. The template determines which events are enabled, sampling periods, thresholds, and whether stack traces are attached.

An event not appearing in the file may be because that event is disabled, the threshold was not met, the request period is unsuitable, or the template does not collect that type of data. Do not infer that an event definitely did not occur simply because the corresponding event is absent.

## 3. How Does Continuous Recording Differ from Profiling Recording?

| Characteristic | Continuous recording | Time-fixed/profiling recording |
|---|---|---|
| Duration | Continuous, usually with no end duration set | Runs for a fixed duration |
| Goal | Keep recent history to investigate rare incidents | Collect detailed data for a profiling session |
| Common configuration | `default.jfc` or Continuous template | `profile.jfc` or Profiling template |
| Storage | Bounded by data age and/or size limits | Usually outputs a single file for the recording session |
| Overhead | Low with the default continuous configuration | Usually higher due to many detailed events |
| Data retrieval | Dump a time window when needed | File is created when the recording ends |

A continuous recording can run for many days, but it only retains the data window within the retention limits. It does not mean keeping every event infinitely since JVM startup.

A profiling recording can enable additional allocation profiling, method profiling, or events with detailed stack traces. Use it for short intervals when you already know the area to investigate.

## 4. Choosing default.jfc or profile.jfc?

The JDK provides two built-in JFR configurations in the directory:

```text
<JAVA_HOME>/lib/jfr/default.jfc
<JAVA_HOME>/lib/jfr/profile.jfc
```

**`default.jfc`**

- Designed for continuous recording.
- Collects key runtime events with low overhead.
- Suitable as a production baseline.
- Does not enable detailed heap statistics and allocation profiling like a profiling recording.

**`profile.jfc`**

- Collects more events.
- Useful when method profiling, allocation profiling, and deeper information are needed.
- Generates more data and can have a more noticeable performance impact.
- Suitable for short investigation sessions when more detail is needed.

Do not modify the `default.jfc` or `profile.jfc` files installed with the JDK. If customization is needed, create your own `.jfc` file based on an existing configuration, then use that file when starting the recording.

For long-term continuous recording, start with `default`. When detailed allocation or method data is needed, create a short profiling recording or a custom configuration with a well-defined scope.

## 5. Understanding Rolling Window, Repository, and Dump File

There are three concepts to distinguish:

1. **In-JVM buffers:** JFR writes events into in-memory buffers before flushing them into chunks.
2. **Disk repository:** When a recording uses disk, the JVM stores temporary chunks in the repository. Chunks are managed according to age and size limits.
3. **`.jfr` dump file:** A standalone file created when an operator dumps the recording for analysis, sharing, or archiving.

In continuous recording, JFR retains recent data. When buffer or retention limits are reached, the oldest data is discarded to make room for new data. This is the intended behavior of a rolling history.

The repository is where temporary chunks are stored while the recording is running. It is not necessarily the location of the final file that the investigation team opens with JDK Mission Control (JMC). When dumping, specify a new path for the `.jfr` file.

Example:

```text
/var/tmp/jfr-repository/        # Repository holding temporary chunks
/var/tmp/jfr-dumps/incident.jfr # Dump file for analysis
```

The repository and dump directory must have sufficient disk space, appropriate write permissions, and their own retention policies.

## 6. Limiting Data with maxage and maxsize

Two key parameters:

| Parameter | Meaning |
|---|---|
| `maxage` | Time limit for which data is retained, e.g., `6h` |
| `maxsize` | Size limit for recording data kept on disk, e.g., `1g` |

Both parameters only apply when `disk=true`.

Example:

```text
disk=true
maxage=6h
maxsize=1g
```

In this example, the recording keeps at most six hours of data and at most one gigabyte. If a high event rate causes the size limit to be reached before six hours, the actual data window will be shorter. If data is older than six hours, it is discarded even if the size limit has not been reached.

If `maxage` or `maxsize` is not set, data on disk can grow without bound. Therefore, a continuous recording needs explicit retention and must account for the actual event rate.

A value of `0` means no corresponding limit is set. Do not use `maxage=0` and `maxsize=0` for long-term production recordings unless another disk-management mechanism is in place.

`maxsize` must be large enough relative to the JFR chunk size limit (`maxchunksize`). If set too small, the JVM may reject the configuration.

## 7. Enabling Continuous Recording at JVM Startup

You can enable recording directly in the application launch command:

```sh
java -XX:StartFlightRecording=disk=true,maxage=6h,maxsize=1g,settings=default -XX:FlightRecorderOptions=repository=/var/tmp/jfr -jar app.jar
```

Meaning:

- `-XX:StartFlightRecording`: starts a JFR recording when the JVM starts.
- `disk=true`: writes the recording to the disk repository.
- `maxage=6h`: retains data for at most six hours.
- `maxsize=1g`: limits recording data to one gigabyte.
- `settings=default`: uses the default low-overhead configuration.
- `-XX:FlightRecorderOptions=repository=...`: selects the directory for temporary chunks.
- `-jar app.jar`: launches the application.

Omitting `duration` means the recording has no automatic end time; the default duration is `0`, meaning it runs indefinitely. You can add `dumponexit=true` if you want the JVM to dump the recording on normal shutdown.

Example:

```sh
java -XX:StartFlightRecording=disk=true,maxage=6h,maxsize=1g,settings=default,dumponexit=true -XX:FlightRecorderOptions=repository=/var/tmp/jfr -jar app.jar
```

If no filename is specified for dump-on-exit, JFR generates an automatic filename in the process working directory. Locate the file based on the output and deployment configuration.

`dumponexit` supports normal shutdown. Do not rely on it as a guarantee to save the file during power loss, a forced process kill, or a JVM crash.

## 8. Enabling Continuous Recording on a Running JVM with jcmd

You do not need to restart the application to start a recording if the JVM supports JFR and diagnostic attach.

First, find the PID:

```sh
jcmd -l
```

Example output:

```text
24680 com.example.OrderService
```

Check available commands:

```sh
jcmd 24680 help JFR.start
```

Start a continuous recording:

```sh
jcmd 24680 JFR.start name=continuous settings=default disk=true maxage=6h maxsize=1g duration=0s
```

Parameters:

- `name=continuous`: assigns a recognizable name to reference the recording later.
- `settings=default`: uses the default configuration.
- `disk=true`: writes data to the repository on disk.
- `maxage=6h`: keeps at most six hours.
- `maxsize=1g`: limits the recording data size.
- `duration=0s`: does not automatically end based on duration.

The JVM returns information about the newly created recording, typically including its ID, name, and state. Save the recording name to use with `JFR.check`, `JFR.dump`, and `JFR.stop`.

`jcmd` must run on the same machine as the target JVM and use the same effective user/group ID as the account that launched the JVM. In containers, run the tool in the same namespace and use the PID visible to that namespace. If attach is refused, check user/group, OS permissions, and the attach mechanism before concluding that JFR is unavailable.

If the command reports that JFR is unavailable, check the vendor/JDK version, target JVM, and supported diagnostic commands. Do not assume every Java implementation has the exact same set of commands.

## 9. Checking a Running Recording

Use:

```sh
jcmd 24680 JFR.check
```

This command displays information about active recordings. You can specify a name:

```sh
jcmd 24680 JFR.check name=continuous
```

To view detailed event settings:

```sh
jcmd 24680 JFR.check name=continuous verbose=true
```

Verify:

- Is the recording running?
- Are the name and ID correct?
- Is the recording using disk or memory?
- Which settings file is being used?
- Do `maxage` and `maxsize` match the desired retention?
- Which events are enabled?

`JFR.check` is a status-check command; it does not stop or modify the recording.

## 10. Dumping Data Near the Incident Time Without Stopping the Recording

When an alert arrives, export a recent time window:

```sh
jcmd 24680 JFR.dump name=continuous filename=/var/tmp/jfr-dumps/incident-last-30m.jfr begin=-30m
```

`begin=-30m` requests data from 30 minutes before the dump time. You can use `begin=-1h` to capture the last hour.

You can specify both start and end times:

```sh
jcmd 24680 JFR.dump name=continuous filename=/var/tmp/jfr-dumps/incident-window.jfr begin=2026-11-10T09:00:00 end=2026-11-10T09:30:00
```

Timestamps must be in a format parseable by `java.time`, such as local time, local date-time, or an ISO-8601 instant. Align the event timezone with the application log timezone before choosing timestamps.

Key point: **JFR.dump does not stop the recording.** After the file is created, the continuous recording keeps collecting new events and the rolling window continues to be maintained.

If no recording name is specified in `JFR.dump`, data from all active recordings may be included in the file. Specify `name` when the JVM has multiple recordings to avoid including out-of-scope data in the file.

## 11. Stopping a Recording and Saving the Final File

When the continuous recording is no longer needed, you can stop it and save the data:

```sh
jcmd 24680 JFR.stop name=continuous filename=/var/tmp/jfr-dumps/continuous-final.jfr
```

This command stops the recording named `continuous` and writes its data to the specified file.

If `JFR.stop` is called without a filename, the recording data may be discarded instead of creating a file for analysis. Therefore, only stop it once you have determined whether the data needs to be kept.

| Action | Result |
|---|---|
| `JFR.dump` | Exports a file; recording keeps running |
| `JFR.stop` with filename | Stops recording and saves the file |
| `JFR.stop` without filename | Stops recording; does not keep a dump file |

For continuous recordings intended to run long-term, prefer dumping around incident times and letting the recording continue. Only stop when intentionally ending collection.

## 12. Inspecting Data with JDK Mission Control

JDK Mission Control (JMC) is a GUI tool for viewing and analyzing `.jfr` files. JMC is not included in every standard JDK installation; it may need to be installed separately.

Basic workflow:

1. Open JMC.
2. Open the dumped `.jfr` file.
3. Review Automated Analysis Results for initial warnings.
4. Select the time range around the incident.
5. Open the Code, Memory, Threads, Locks, Garbage Collections, and I/O pages.
6. Correlate event timestamps with application logs and distributed traces.
7. Drill down into relevant stack traces or threads.

JMC can help answer:

- Which thread is consuming CPU?
- Is there prolonged lock contention?
- When did GC pauses occur?
- How did heap usage change?
- Which I/O operations have high latency?
- Which classes or allocation sites stand out?

JFR data only reflects the events that the recording collected. If allocation profiling is needed while the continuous recording is using `default.jfc`, start a short profiling recording or an appropriate custom configuration.

## 13. Analyzing Files with the jfr Command-Line Tool

The JDK provides the `jfr` tool in the `bin` directory.

View a file summary:

```sh
jfr summary /var/tmp/jfr-dumps/incident-last-30m.jfr
```

The summary command shows event counts, recording duration, and data size. It is useful for confirming the file contains events and evaluating event settings.

Print GC events:

```sh
jfr print --categories GC /var/tmp/jfr-dumps/incident-last-30m.jfr
```

Print a specific event:

```sh
jfr print --events jdk.GCHeapSummary /var/tmp/jfr-dumps/incident-last-30m.jfr
```

Print events in JSON format for further processing:

```sh
jfr print --json --events jdk.ExecutionSample /var/tmp/jfr-dumps/incident-last-30m.jfr
```

View event metadata:

```sh
jfr metadata /var/tmp/jfr-dumps/incident-last-30m.jfr
```

Avoid printing an entire large recording to the terminal unnecessarily. Filter by category or event to reduce output and focus on the investigation question.

## 14. Tuning Event Settings for Continuous Recording

The template dictates which events are collected and at what level of detail. If additional events are needed:

- Use JMC Template Manager to create a custom configuration.
- Or use the `jfr configure` tool to create a new `.jfc` file.
- Keep the custom file in a configuration directory managed by the application.
- Start the recording with `settings=/path/to/custom.jfc`.

Example of creating a new configuration based on default:

```sh
jfr configure --input default.jfc --output continuous-custom.jfc
```

Event settings can be modified using the syntax:

```text
<event-name>#<setting-name>=<value>
```

For example, some events have a threshold or period. Lowering the threshold collects shorter events and increases event volume; enabling more stack traces or additional events can enlarge files and increase overhead.

Do not edit the JDK-installed `default.jfc` or `profile.jfc` files directly. Create a copy/custom file so it is easy to review, version-control, and reuse across environments.

When changing configurations, verify the new recording with `JFR.check name=... verbose=true` and inspect `jfr summary` after a test collection period.

## 15. Default Continuous Recording Is Not an Allocation Profiler

This is an important limitation when investigating memory:

- `default.jfc` is suited for continuous recording with low overhead.
- This configuration does not collect full heap statistics and allocation profiling like a profiling recording.
- If only the default continuous recording is enabled, there may not be enough data to pinpoint which method allocates the most objects.
- When suspecting a memory leak, use a histogram, a heap dump, or a profiling recording with appropriate allocation events.

A common workflow:

1. Keep the default continuous recording for runtime history.
2. When heap or live set grows abnormally, dump the relevant time window.
3. Use JMC to inspect GC, heap, and available events.
4. If allocation sites are needed, start a short profiling recording with `profile.jfc` or custom settings.
5. If an object graph and reference chain are needed, take a heap dump following the appropriate operational procedure.

Do not raise every event to a high level of detail in continuous recording "just in case." Doing so can produce large files, increase recording overhead, and generate noisy data that is harder to analyze.

## 16. Managing the Repository and Disk Space

The repository is usually placed in the OS temporary directory if not specified. You can choose a dedicated directory at JVM startup:

```sh
java -XX:StartFlightRecording=disk=true,maxage=6h,maxsize=1g,settings=default -XX:FlightRecorderOptions=repository=/var/tmp/jfr-repository -jar app.jar
```

When choosing a repository:

- Ensure the directory exists or that the JVM can create it.
- The account running the JVM must have read/write permissions.
- Choose a filesystem with adequate capacity and performance.
- Avoid temporary directories that get cleaned up while the JVM is still running.
- Monitor total disk usage of both the repository and final dump files.
- Set restricted access permissions because events may contain internal information.

The `maxsize` limit applies to recording data retained in the repository. `.jfr` files dumped to another directory are separate artifacts and require their own retention policy. Do not assume the repository limit will automatically delete old dump files.

You can use `-XX:FlightRecorderOptions=preserve-repository=true` if you need to keep repository chunks after the JVM exits for recovery purposes. By default, the repository is usually cleaned up when the process terminates. Only enable preserve when a clear management and cleanup process is in place, as chunks can continue consuming disk space.

## 17. Recovering a Recording from the Repository After an Incident

JFR writes files in chunks. If the JVM encounters a fatal error, some completed chunks may still remain in the repository. When the repository is preserved, you can use:

```sh
jfr assemble /var/tmp/jfr-repository /var/tmp/jfr-dumps/recovered.jfr
```

`jfr assemble` merges valid chunks in chronological order into a single recording. Incomplete chunks may be excluded from the assembly process.

Recovery depends on chunks still existing and being uncorrupted. There is no guarantee that every event right before a crash was completely flushed.

If you need to keep the repository across a JVM exit/crash, configure `preserve-repository=true` and verify the actual path before deploying. After recovery, verify the file with `jfr summary` and try opening it in JMC.

## 18. Performance Impact and Safe Operation

JFR is designed to record events with low overhead, but the cost depends on event settings, workload, event rate, stack depth, and recording duration.

Recommendations:

- Use `default.jfc` for long-term continuous recording.
- Use `profile.jfc` for short periods when deeper data is needed.
- Keep `maxage` and `maxsize` within calculated capacity limits.
- Do not enable stack traces or allocation events more broadly than needed without evaluating overhead.
- Do not arbitrarily increase stack depth; values larger than the default can impact performance.
- Monitor repository and dump directory disk usage.
- Test on staging with production-like workload before rolling out broadly.
- Document the JDK version, template, event settings, and retention in the runbook.

A continuous recording can increase disk write I/O. If the disk is slow or nearly full, the impact may manifest beyond JFR itself. Monitor both free space and storage latency.

Do not use JFR as an unbounded log storage system. Keep a window long enough to catch incidents, yet bounded to avoid exhausting disk space.

## 19. Data Security in JFR Files

A `.jfr` file may contain:

- Internal class, package, and method names.
- Stack traces and code paths.
- Thread names, host, process, and runtime details.
- File names, socket endpoints, and I/O metadata.
- Information about application activity and request timing.
- Custom event fields recorded by the application, which may contain business data if not designed carefully.

Do not assume JFR files contain only anonymous metrics. Treat recordings as internal diagnostic artifacts.

When storing or sharing:

- Grant access only to people who need to analyze them.
- Do not upload files to public locations.
- Encrypt when transferring over a network or storing in shared locations.
- Delete files according to the retention policy.
- Mask or remove sensitive events before sending them externally.

You can use `jfr scrub` to strip certain events, categories, or threads from a file:

```sh
jfr scrub --exclude-categories "File I/O,Socket I/O" input.jfr sanitized.jfr
```

Re-check the scrubbed file with `jfr summary` and `jfr print`. Scrubbing can remove data needed for diagnosis; only exclude events after understanding the impact on analysis.

## 20. Java 17+ Example: Running an Application and Enabling Continuous Recording

Create `JfrContinuousDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public class JfrContinuousDemo {
    private static volatile byte[] lastPayload;

    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(() -> {
            while (!Thread.currentThread().isInterrupted()) {
                byte[] payload = new byte[16 * 1024];
                payload[0] = 1;
                lastPayload = payload;

                try {
                    Thread.sleep(100);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "jfr-demo-worker");

        worker.setDaemon(true);
        worker.start();

        System.out.println("READY");
        new CountDownLatch(1).await();
    }
}
```

Compile:

```sh
javac JfrContinuousDemo.java
```

Run:

```sh
java JfrContinuousDemo
```

Exact stdout:

```text
READY
```

The program keeps the JVM alive and generates a small allocation workload in the background. Open a second terminal and find the PID:

```sh
jcmd -l
```

Assuming the demo PID is `24680`, start a continuous recording:

```sh
jcmd 24680 JFR.start name=continuous settings=default disk=true maxage=30m maxsize=256m duration=0s
```

Check:

```sh
jcmd 24680 JFR.check name=continuous verbose=true
```

After a while, dump the last 10 minutes:

```sh
jcmd 24680 JFR.dump name=continuous filename=continuous-demo.jfr begin=-10m
```

View file summary:

```sh
jfr summary continuous-demo.jfr
```

After practicing, you can dump again to confirm the recording is still running. Stop and save the final file:

```sh
jcmd 24680 JFR.stop name=continuous filename=continuous-final.jfr
```

The PID in the example is illustrative only. Replace it with the actual PID from `jcmd -l`. After stopping the recording, return to the terminal running the program and press Ctrl+C to end the demo.

## 21. Common Errors and Troubleshooting

| Symptom | Common Cause | Resolution |
|---|---|---|
| `jcmd: command not found` | JDK not installed or `JAVA_HOME/bin` missing from PATH | Use `jcmd` from the JDK and verify PATH |
| PID not found | Wrong PID, process stopped, or different container namespace | Use `jcmd -l`, `jps -l`, or OS tools in the right namespace |
| Attach refused | Different user/group or attach disabled | Run under the same account as the JVM and check runtime settings |
| `JFR.start` does not exist | JVM does not support the command or JFR is unavailable | Run `jcmd PID help` and check JDK/vendor |
| Recording missing from `JFR.check` | Recording stopped, JVM restarted, or wrong name used | Verify name, ID, PID, and JVM status |
| No file after `JFR.dump` | Invalid path or target JVM lacks write permission | Use an absolute path writable on the target machine |
| Recording does not retain a full six hours | `maxsize` reached before `maxage` due to high event rate | Increase size limit or reduce event volume |
| Repository full | No retention set, multiple recordings, or dump files not cleaned up | Configure `maxage`/`maxsize` and clean up dump files per policy |
| JFR file small or missing expected events | Template does not enable the event or threshold not met | Check `JFR.check verbose=true`, settings, and event thresholds |
| No allocation profiling visible | Using `default.jfc` continuous template | Start a short profiling recording or custom configuration |
| Recording stopped on dump | Confused `JFR.dump` with `JFR.stop` | Use `JFR.dump` to export a file while keeping the recording running |
| JFR file cannot be opened after crash | Final chunk incomplete or repository deleted | Use a preserved repository and try `jfr assemble` |
| JFR increases disk I/O | High event rate, profile template, or overly detailed recording | Revert to default, tune event settings, and monitor storage |
| Repository not found after JVM exits | Default repository deleted when process terminates | Configure preserve repository if recovery is needed |

When encountering an error, first determine whether the recording is running or stopped. Then check the PID, attach permissions, recording name, repository path, retention, and event settings.

## 22. Continuous Recording Workflow for Production

An operational workflow you can deploy:

1. Choose a JDK with JFR and verify that `JFR.start`, `JFR.check`, `JFR.dump`, and `JFR.stop` commands are supported.
2. Select `default.jfc` for the background continuous recording.
3. Determine the history window to retain, e.g., six hours.
4. Calculate required storage from the actual event rate; set `maxage` and `maxsize`.
5. Choose a repository on a filesystem with sufficient space and write permissions.
6. Enable recording at startup or via `jcmd` for a running JVM.
7. Verify with `JFR.check`.
8. When an alert occurs, record the timestamp, timezone, PID, and incident ID.
9. Dump the time window before and after the incident if needed.
10. Open the file with JMC or use `jfr summary`/`jfr print`.
11. Correlate events with application logs, metrics, and traces.
12. Store investigation files per retention policy and protect access permissions.
13. If allocation/method profiling is needed, create a short recording with a more detailed configuration.
14. After the investigation is complete, stop the recording only if collection is no longer needed.

In the runbook, clearly document who is authorized to dump recordings, where files are stored, who has access, retention duration, and how to scrub data before sharing.

## 23. Checklist

- [ ] Confirmed JFR is supported on the target JVM.
- [ ] Selected `default.jfc` for background continuous recording.
- [ ] Understood the difference between continuous recording and profiling recording.
- [ ] Set `disk=true` if rolling data needs to be stored on disk.
- [ ] Configured `maxage` and/or `maxsize`.
- [ ] Verified repository disk space and write permissions.
- [ ] Know how to find the PID and attach with `jcmd`.
- [ ] Verified the recording with `JFR.check`.
- [ ] Know how to dump a time window with `JFR.dump`.
- [ ] Distinguished `JFR.dump` from `JFR.stop`.
- [ ] Understood that default continuous recording does not enable detailed allocation profiling.
- [ ] Know how to open the file in JMC and inspect it with `jfr summary`.
- [ ] Have a retention policy for the repository and dump files.
- [ ] Protected JFR files and scrubbed sensitive events before sharing.
- [ ] Recorded JDK version, event settings, timezone, and incident timestamp.

## 24. References

- Oracle JDK 21 Troubleshooting Guide — Flight Recorder and Continuous Recordings: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- Oracle JDK 21 Tool Reference — The `jcmd` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle JDK 21 Tool Reference — The `java` Command and `-XX:StartFlightRecording`: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- Oracle JDK 21 Tool Reference — The `jfr` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html
- Java SE 21 API — `jdk.jfr.Recording`: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html

Continuous recording retains recent runtime history to investigate incidents after they occur. Use the `default` configuration with bounded retention, dump the right time window with `JFR.dump`, and switch to detailed profiling only when the investigation question requires more data. Manage the repository, dump files, and access permissions as production diagnostic artifacts.