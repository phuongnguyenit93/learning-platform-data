# Controlling Java Flight Recorder with jcmd

## 1. What are JFR commands in jcmd?

Java Flight Recorder (JFR) is an event recording system for the JVM and Java applications. JFR collects data on garbage collection, allocation, threads, lock contention, class loading, JIT compilation, file I/O, socket I/O, and many other runtime activities. The data is stored in a binary `.jfr` file for later analysis.

`jcmd` is a diagnostic tool included with the JDK. It sends diagnostic commands to a running JVM on the same machine. The `JFR.*` command group lets you control recordings directly without restarting the application:

- `JFR.start` starts a recording.
- `JFR.check` inspects running recordings and event configurations.
- `JFR.dump` dumps recording data to a file while the recording continues.
- `JFR.stop` stops a recording and writes the data to a file.
- `JFR.configure` views or configures JFR resources and repository settings.
- `JFR.view` displays built-in analysis tables from JFR data.

It is important to distinguish between two tools:

| Tool | Role |
|---|---|
| `jcmd PID JFR.start`, `JFR.dump`, `JFR.stop` | Controls recordings inside a running JVM. |
| `jfr summary`, `jfr print`, `jfr view` | Reads and analyzes `.jfr` recording files after they have been dumped. |

A common investigation workflow is to identify the PID, start a recording, check the configuration, dump a snapshot or stop the recording, and then analyze the file using the `jfr` tool or JDK Mission Control.

## 2. Requirements for jcmd to connect to a JVM

Before running a JFR command, identify the correct Java process:

~~~bash
jcmd -l
~~~

The output looks like:

~~~text
18420 com.example.orders.OrderService
27116 com.example.worker.BatchWorker
~~~

The first number is the process ID (PID). Use the specific PID for subsequent commands:

~~~bash
jcmd 18420 help
jcmd 18420 help JFR.start
~~~

Key requirements:

- `jcmd` runs on the same machine as the target JVM; it is not a remote network JVM control tool.
- The user running `jcmd` generally must be the same user/effective user that launched the target JVM.
- The target JVM must allow the Attach mechanism. If Attach is disabled, the tool may not be able to connect.
- Processes in containers may have their own PID namespace; use the PID visible from an environment with permission to attach.
- Diagnostic commands can vary by JDK and JVM vendor. Always run `jcmd PID help` to see the commands actually supported by the target JVM.

Do not use PID `0` indiscriminately. According to `jcmd` help, PID `0` sends the command to all Java processes capable of receiving commands. For starting or stopping a recording, specify the PID of the exact application.

## 3. Viewing supported JFR commands

List the commands of a JVM:

~~~bash
jcmd 18420 help
~~~

View the syntax and impact level of a specific command:

~~~bash
jcmd 18420 help JFR.start
jcmd 18420 help JFR.check
jcmd 18420 help JFR.dump
jcmd 18420 help JFR.stop
jcmd 18420 help JFR.configure
jcmd 18420 help JFR.view
~~~

The command help provides:

- Command name and purpose.
- Optional parameters.
- Default values.
- Accepted time or path formats.
- Expected impact level of the command on the JVM.

For example, in JDK 24.0.2, `JFR.check` has a low impact, `JFR.dump` has a low impact, while `JFR.start` has a medium impact depending on the recording configuration. `JFR.view` can also have a medium impact.

The impact level is not a guarantee that a command will never affect performance. Read the help output of the target JVM and choose event settings appropriate for the investigation window.

## 4. Starting a recording with JFR.start

Syntax:

~~~bash
jcmd 18420 JFR.start [options]
~~~

Start a recording with the default configuration:

~~~bash
jcmd 18420 JFR.start name=incident-recording settings=default
~~~

Commonly used options:

| Option | Meaning |
|---|---|
| `name` | Names the recording for reuse in `JFR.check`, `JFR.dump`, and `JFR.stop`. |
| `settings` | Selects the event configuration file, typically `default`, `profile`, or `none`. |
| `duration` | Recording duration; for example `30s`, `5m`, or `1h`. A value of `0s` means unlimited duration. |
| `delay` | Waits for a specified period before starting the recording. |
| `filename` | Path to the recording file written when the recording completes. |
| `maxage` | Limits how long data is retained in the disk repository. |
| `maxsize` | Limits the size of recording data on disk. |
| `disk` | Enables writing recording data to disk; defaults to `true`. |
| `dumponexit` | Writes the recording to a file when the JVM shuts down. |
| `path-to-gc-roots` | Collects paths from objects to GC roots for memory leak investigations; this operation can be expensive and cause pauses. |

Durations can use seconds, minutes, or hours. For example:

~~~bash
jcmd 18420 JFR.start name=short-check duration=30s settings=default
jcmd 18420 JFR.start name=delayed-check delay=2m duration=5m settings=default
~~~

If `duration` is omitted, the recording runs until stopped or until the JVM exits. Give recordings clear `name` values when managing multiple recordings simultaneously.

## 5. Choosing default, profile, or none

The JDK provides sample JFR configurations in the `JAVA_HOME/lib/jfr` directory:

| Configuration | Purpose | Data level and overhead |
|---|---|---|
| `default.jfc` | Continuous monitoring or long-running production observation. | Lower overhead, focused on essential information. |
| `profile.jfc` | Short-term performance investigation. | More events and stack traces, higher overhead. |
| `none` | Starts a recording without loading a built-in event configuration. | Only collects events that are explicitly enabled. |

Example of a short recording for deep investigation:

~~~bash
jcmd 18420 JFR.start name=profile-incident settings=profile duration=2m
~~~

Example of a lightweight recording for longer observation:

~~~bash
jcmd 18420 JFR.start name=continuous-monitor settings=default maxage=1h maxsize=512M
~~~

`default` is generally suitable for extended recordings. `profile` should be used for bounded periods when you need more detail on allocation, method profiling, or contention.

Do not choose `profile` simply because it collects more data. More detailed events and stack traces can increase overhead, file size, and analysis cost.

## 6. Limiting size and automatically saving files

For disk-backed recordings, you can set time and size limits:

~~~bash
jcmd 18420 JFR.start name=bounded-recording settings=default maxage=30m maxsize=256M
~~~

- `maxage=30m` retains up to approximately 30 minutes of data.
- `maxsize=256M` limits recording data on disk to 256 MB.
- These limits apply when the recording writes data to disk.
- `maxsize` must meet the minimum limit based on JFR's `maxchunksize`.

You can automatically save a recording when the JVM shuts down:

~~~bash
jcmd 18420 JFR.start name=shutdown-recording settings=default dumponexit=true
~~~

If no filename is specified, the JVM generates a filename containing the PID, recording ID, and timestamp in the process's working directory.

If a filename is specified, supported placeholders include:

- `%p` is replaced with the PID.
- `%t` is replaced with a timestamp in `yyyy_MM_dd_HH_mm_ss` format.

Example:

~~~bash
jcmd 18420 JFR.start name=service-recording settings=default filename=recordings/service-%p-%t.jfr dumponexit=true
~~~

Ensure the target directory exists and the user running the JVM has write permission. For recordings that must be saved reliably before the application exits, use `JFR.dump` or `JFR.stop` with an explicit filename.

## 7. Checking running recordings with JFR.check

View all current recordings:

~~~bash
jcmd 18420 JFR.check
~~~

The output looks like:

~~~text
Recording 1: name=incident-recording maxsize=256.0MB maxage=30m (running)
~~~

View detailed event settings:

~~~bash
jcmd 18420 JFR.check verbose=true
~~~

Filter by name:

~~~bash
jcmd 18420 JFR.check name=incident-recording
~~~

`verbose=true` displays the recording's event settings, such as which events are enabled, their thresholds, and whether stack traces are collected.

If the command returns `No available recordings`, the recording may not have been started, may have finished after its duration elapsed, or may have already been stopped. Use `JFR.start` to start a new recording if needed.

## 8. Dumping a snapshot without stopping the recording

`JFR.dump` copies the current data of a recording to a file. The recording continues running after the dump.

Basic syntax:

~~~bash
jcmd 18420 JFR.dump name=incident-recording filename=recordings/incident-snapshot.jfr
~~~

This is useful when:

- You need to capture evidence before an incident disappears.
- You want to analyze current data while continuing to observe the application.
- You want to take multiple snapshots at different points in time.
- You need to save a specific time window from a long-running recording.

You can limit the time range of data included in the dump file:

~~~bash
# Capture data from the last 15 minutes
jcmd 18420 JFR.dump name=incident-recording begin=-15m filename=recordings/recent-15m.jfr

# Capture a specific time range
jcmd 18420 JFR.dump name=incident-recording begin=2026-11-10T10:00:00 end=2026-11-10T10:15:00 filename=recordings/incident-window.jfr
~~~

`begin` and `end` accept local time, timestamps, or negative relative times such as `-15m` or `-30s`. Values are matched against timestamps inside the recording.

A dump can also use `maxage` and `maxsize` to bound the exported data. `path-to-gc-roots=true` can add useful information for memory leaks, but collecting GC roots can pause the application; only enable it when investigating a specific memory leak hypothesis.

## 9. Stopping a recording and saving data with JFR.stop

Stop a recording by name and save it to a file:

~~~bash
jcmd 18420 JFR.stop name=incident-recording filename=recordings/incident-final.jfr
~~~

The output looks like:

~~~text
Stopped recording "incident-recording", 516.9 kB written to:
recordings/incident-final.jfr
~~~

You can use the recording ID instead of the name when needed, but using a readable name makes scripts and logs easier to follow.

**Always specify a filename when you need to keep the data.** JDK 24's `JFR.stop` help states that if no filename is provided, the recording data is discarded upon stopping.

After stopping:

~~~bash
jcmd 18420 JFR.check
~~~

The stopped recording will no longer appear in the list of active recordings. The saved file can be analyzed independently of the JVM.

## 10. Customizing events when starting a recording

`JFR.start` allows modifying event settings directly using the syntax:

~~~text
<event-name>#<setting-name>=<value>
~~~

For example, lowering the threshold for the lock contention event:

~~~bash
jcmd 18420 JFR.start name=lock-investigation settings=default jdk.JavaMonitorEnter#threshold=1ms
~~~

Also enabling stack traces for the event:

~~~bash
jcmd 18420 JFR.start name=lock-stacks settings=default jdk.JavaMonitorEnter#threshold=1ms jdk.JavaMonitorEnter#stackTrace=true
~~~

To add settings for a custom event, prefix the event name with `+`:

~~~bash
jcmd 18420 JFR.start name=custom-event-recording settings=none +com.example.OrderProcessed#enabled=true +com.example.OrderProcessed#stackTrace=true
~~~

Settings can include `enabled`, `threshold`, `period`, and `stackTrace` depending on the event. Not every event supports all settings.

JFR can load multiple `.jfc` files by repeating the `settings` parameter. When a command-line setting conflicts with a setting in `.jfc`, the command-line setting takes precedence.

To find valid event names and settings, check `jcmd PID help JFR.start`, the `jdk.jfr` documentation, and recording metadata.

## 11. Viewing live data with JFR.view

`JFR.view` displays built-in summary tables directly from the JVM without needing to dump a file first.

Examples:

~~~bash
# GC information
jcmd 18420 JFR.view gc

# CPU-intensive methods based on sampling
jcmd 18420 JFR.view hot-methods

# Object allocations by class
jcmd 18420 JFR.view allocation-by-class

# Contention by thread
jcmd 18420 JFR.view contention-by-thread
~~~

You can adjust the width and display query details:

~~~bash
jcmd 18420 JFR.view width=160 hot-methods
jcmd 18420 JFR.view verbose=true allocation-by-class
~~~

List the views and event types supported by the JVM:

~~~bash
jcmd 18420 JFR.view all-views
jcmd 18420 JFR.view all-events
jcmd 18420 JFR.view types
~~~

Other useful views include `gc-pauses`, `thread-count`, `exception-by-type`, `file-reads-by-path`, `socket-reads-by-host`, and `memory-leaks-by-class`.

View names depend on the JDK version. If a view does not exist, run `jcmd PID help JFR.view` to see the list for that specific JVM. A view requires matching event data; an empty table does not necessarily mean JFR is broken.

## 12. Configuring resources and repository with JFR.configure

`JFR.configure` manages the JVM's JFR resource configuration:

~~~bash
jcmd 18420 JFR.configure
~~~

Some parameters:

| Parameter | Purpose |
|---|---|
| `memorysize` | Total memory allocated for JFR buffers. |
| `maxchunksize` | Maximum size of a single data chunk. |
| `repositorypath` | Temporary repository directory holding recording data before dumping to a file. |
| `dumppath` | Directory for saving dump files when the JVM encounters a fatal error. |
| `stackdepth` | Maximum stack trace depth. |
| `thread_buffer_size` | Size of the local buffer for each thread. |
| `preserve-repository` | Preserves repository files after the JVM exits. |

Example of viewing and adjusting the repository:

~~~bash
jcmd 18420 JFR.configure repositorypath=/var/tmp/jfr-repository
~~~

Some parameters, such as `memorysize`, `maxchunksize`, and `stackdepth`, cannot be changed after JFR has been initialized. Check the configuration early in the JVM lifecycle and read the help before making changes in production.

Do not arbitrarily change buffer sizes or stack depth to fix missing recording data. These parameters can affect JVM performance and memory usage.

## 13. Analyzing files with the jfr tool

After dumping or stopping a recording, use the `jfr` tool for offline analysis.

Summarize a recording:

~~~bash
jfr summary recordings/incident-final.jfr
~~~

The output displays the recording version, chunk count, start time, duration, and the count of each event type.

Print specific events:

~~~bash
jfr print --events CPULoad,GarbageCollection recordings/incident-final.jfr
~~~

Print events by category:

~~~bash
jfr print --categories "GC,JVM,Java*" recordings/incident-final.jfr
~~~

Print as JSON:

~~~bash
jfr print --json --events CPULoad recordings/incident-final.jfr
~~~

View built-in analysis tables from a file:

~~~bash
jfr view hot-methods recordings/incident-final.jfr
~~~

`jfr summary` helps verify that the file contains data and shows which events were recorded. `jfr print` is suitable when inspecting individual events; `jfr view` aggregates data into tables.

## 14. Creating custom .jfc configurations

When you need to reuse event configurations repeatedly, you can create a `.jfc` file instead of passing many event settings in every command.

Use the interactive wizard:

~~~bash
jfr configure --interactive
~~~

Or generate a file from an input configuration:

~~~bash
jfr configure --input default.jfc --output incident.jfc jdk.JavaMonitorEnter#threshold=1ms
~~~

Use the newly created configuration:

~~~bash
jcmd 18420 JFR.start name=custom-profile settings=incident.jfc
~~~

A `.jfc` file describes which events are enabled, along with their thresholds, periods, and stack trace settings. Store the configuration alongside your operational source control if it is part of a standardized diagnostic workflow.

Test the configuration file on the exact target JDK version. Events or settings may differ across JDK releases.

## 15. Complete example: investigating a running JVM

Create a sample application `src/demo/JfrCommandDemo.java`:

~~~java
package demo;

public class JfrCommandDemo {
    private static final Object LOCK = new Object();

    public static void main(String[] args) throws InterruptedException {
        long count = 0;

        while (!Thread.currentThread().isInterrupted()) {
            byte[] payload = new byte[32 * 1024];

            synchronized (LOCK) {
                payload[0] = (byte) (count++ & 0xff);
            }

            Thread.sleep(25);
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
mkdir -p out recordings
javac --release 17 -d out src/demo/JfrCommandDemo.java
java -cp out demo.JfrCommandDemo
~~~

In another terminal, find the PID:

~~~bash
jcmd -l
~~~

Suppose the PID is `18420`. Start a recording:

~~~bash
jcmd 18420 JFR.start name=lesson-recording settings=default maxage=10m maxsize=50M
~~~

Check the recording:

~~~bash
jcmd 18420 JFR.check verbose=true
~~~

View live data:

~~~bash
jcmd 18420 JFR.view hot-methods
jcmd 18420 JFR.view allocation-by-class
~~~

Dump a snapshot and continue recording:

~~~bash
jcmd 18420 JFR.dump name=lesson-recording filename=recordings/jfr-snapshot.jfr
~~~

Stop the recording and save the final file:

~~~bash
jcmd 18420 JFR.stop name=lesson-recording filename=recordings/jfr-final.jfr
~~~

Analyze the file:

~~~bash
jfr summary recordings/jfr-final.jfr
jfr print --events CPULoad,GarbageCollection recordings/jfr-final.jfr
~~~

Observed results in a JDK 24.0.2 verification environment:

- `JFR.start` returns the recording ID.
- `JFR.check verbose=true` displays the running recording and event settings.
- `JFR.dump` creates a snapshot while the recording continues running.
- `JFR.stop` stops the recording and writes the final file.
- `jfr summary` reads the file with version, chunk, duration, and event count information.
- `jfr print` displays data for the selected events.

Example using a recording with a duration so it stops automatically:

~~~bash
jcmd 18420 JFR.start name=timed-recording settings=default duration=3s filename=recordings/timed-recording.jfr
~~~

After about three seconds, the recording finishes automatically and the file is written. At that point, `JFR.check` no longer lists this recording. This approach is useful when you need to capture a fixed time window.

## 16. Reading and handling sensitive data in recordings

JFR can record extensive environment and application details, such as:

- Command line arguments, JVM flags, and system properties.
- Environment variables recorded in their corresponding events.
- Thread, class, and method names, as well as stack traces.
- File paths, I/O details, and network hosts depending on enabled events.
- Class loader, module, runtime, and system configuration details.

A `.jfr` file can therefore contain sensitive data or internal information. Restrict access permissions, retention periods, and file transfer destinations; review recordings before sending them outside your organization.

If you need to remove events or threads from a file before sharing, you can use `jfr scrub`:

~~~bash
jfr scrub --exclude-events "jdk.InitialEnvironmentVariable,jdk.InitialSystemProperty" input.jfr scrubbed.jfr
~~~

Scrub syntax and filters depend on the tool version. Check `jfr help scrub` before running and verify the output file with `jfr summary`. Scrubbing does not replace data classification procedures; always inspect the remaining contents before sharing.

## 17. Impact level and production considerations

JFR is designed to support JVM observability with low overhead under appropriate settings, but its impact depends on event settings, recording duration, stack trace volume, and application activity.

Key principles:

- Start with `settings=default` for continuous monitoring.
- Use `settings=profile` for short windows when deep investigation is needed.
- Bound recordings with `duration`, `maxage`, and `maxsize`.
- Use `JFR.check` to verify which recordings are running.
- Use `JFR.dump` to take a snapshot without stopping the recording.
- Use `JFR.stop` with an explicit filename to save the final data.
- Only enable `path-to-gc-roots` when investigating memory leaks, as collecting it can cause pauses.
- Do not run commands against PID `0` unless you intend to target multiple JVMs.
- Check the impact in `jcmd PID help COMMAND` before running a command on latency-sensitive systems.

JFR is not a heap dump. Recordings are typically smaller and store a sequence of events over time; a heap dump captures detailed heap state at a single point in time and can cause significant pauses. Choose the tool based on the hypothesis you need to test.

## 18. Common errors and troubleshooting

| Symptom | Common cause | Resolution |
|---|---|---|
| `jcmd -l` does not list the JVM | Different user, container PID namespace, JVM cannot be attached to, or process has exited. | Check user, namespace, PID, and the Attach mechanism. |
| `AttachNotSupportedException` | JVM disabled attach or the environment does not allow attaching. | Check JVM configuration, permissions, and runtime environment. |
| `Unknown diagnostic command` | Target JVM does not support the command or command name is misspelled. | Run `jcmd PID help` and check the JDK version. |
| `JFR.start` reports recording already exists | Duplicate recording name or recording is already running. | Run `JFR.check`, choose another name, or handle the existing recording. |
| `JFR.check` reports no recordings | Recording has not started, its duration expired, or it was stopped. | Run `JFR.start` and check again. |
| Dump file does not exist | Invalid path, directory does not exist, or JVM lacks write permission. | Create the directory, check permissions, and use an absolute path if needed. |
| `JFR.stop` does not keep data | No filename specified when stopping. | Re-run the workflow and provide `filename=...` in `JFR.stop`. |
| JFR file is too large | Using `profile`, too many events enabled, or recording for too long. | Switch to `default`, and bound `duration`, `maxage`, and `maxsize`. |
| Recording is missing expected events | Event is disabled, threshold is too high, or event did not occur during the recording window. | Check `JFR.check verbose=true` and adjust event settings. |
| `JFR.view` has no data | Recording does not have matching events yet or the view does not exist in this JDK. | Check the recording, events, and the list via `JFR.view all-views`. |
| Recording causes long pauses | Collecting GC roots or deep stack traces, or high-overhead events enabled. | Disable expensive options, use lighter settings, and record for short windows. |
| Cannot analyze file with `jfr` | File was not dumped completely or is corrupted. | Check with `jfr summary`, re-dump the recording, and check for file write errors. |

## 19. Checklist before ending an investigation session

- Identified the correct PID and user of the target JVM.
- Verified supported JFR commands with `jcmd PID help`.
- Gave the recording a clear name and settings suited to the goal.
- Configured `duration`, `maxage`, and `maxsize` appropriately for the investigation window.
- Used `JFR.check` to confirm the recording is running.
- Dumped a snapshot if evidence needed to be preserved while the recording continued.
- Stopped the recording with `JFR.stop` and provided a filename.
- Verified the `.jfr` file exists and is readable with `jfr summary`.
- Inspected the necessary events with `jfr print` or `jfr view`.
- Reviewed for sensitive data before sharing the recording.
- Stopped any recordings no longer needed to avoid unintended collection.
- Recorded the JDK version, PID, recording time, and event configuration alongside the analysis results.

## 20. References

- [The jcmd Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [The jfr Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jfr.html)
- [JDK Flight Recorder API — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/jdk/jfr/package-summary.html)

`jcmd` provides JFR commands to control recordings directly on a running JVM: `JFR.start`, `JFR.check`, `JFR.dump`, `JFR.stop`, `JFR.configure`, and `JFR.view`. Choose appropriate settings, bound time and size, save recordings with a clear filename, and use `jfr` to inspect the data before concluding your investigation.