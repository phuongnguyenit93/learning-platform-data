# Starting, Saving, and Stopping JFR Recordings in Java 17

## 1. What Is JFR Used For?

Java Flight Recorder (JFR) is a mechanism that records events occurring inside the JVM and application to support performance diagnostics. A recording can contain information on:

- Garbage collection and the heap.
- CPU sampling and thread activity.
- Lock contention, monitors, and thread parking.
- Object allocations.
- Class loading and JIT compilation.
- File I/O, socket I/O, and various runtime events.
- Custom events emitted by the application or libraries.

JFR stores data in a binary file with the `.jfr` extension. After recording, you can use the JDK's `jfr` tool or Java Mission Control (JMC) to view summaries, filter events, and analyze behavior over time.

In Java 17, JFR is a supported technology built into the JDK and can be used in production with appropriate configuration. You do not need legacy commercial unlock flags or older activation flags mentioned in outdated JDK guides.

A typical workflow:

~~~text
Choose workload and recording duration
          |
          v
Start recording
          |
          v
Run workload / wait for incident
          |
          v
Check recording status
          |
          v
Dump snapshot or stop recording
          |
          v
Save .jfr file
          |
          v
Analyze with jfr or JMC
~~~

After completing this lesson, you should be able to:

1. Start a recording at JVM startup using `-XX:StartFlightRecording`.
2. Start a recording on a running JVM using `jcmd`.
3. Distinguish between `JFR.dump` and `JFR.stop`.
4. Save recordings to files and manage size/duration limits.
5. Choose `default`, `profile`, or a custom JFC configuration file appropriately.
6. Create recordings using the `jdk.jfr.Recording` API in Java code.
7. Inspect files using `jfr summary`, `jfr print`, or JMC.
8. Manage overhead, sensitive data, and recording lifecycles.

## 2. Preparing the Java 17 Environment

### 2.1. Using Bundled JDK Tools

Common tools:

| Tool | Role |
|---|---|
| `java` | Launches the application and can start a recording right at startup |
| `jcmd` | Sends diagnostic commands to a running JVM, including JFR start/check/dump/stop |
| `jfr` | Summarizes and prints data from recording files |
| `jconsole` | Observes selected JVM management metrics via JMX |
| Java Mission Control (JMC) | Analyzes recordings with a graphical UI; may be installed separately |

Verify runtime and tool versions:

~~~bash
java -version
jcmd -h
jfr --help
~~~

Use tools from a JDK compatible with the running JVM. For attach operations, the process must be in an environment visible to the tool and the user running `jcmd` must have appropriate permissions.

### 2.2. JFR Is Built Into Java 17

JFR was integrated into OpenJDK and expanded across JDK releases. In Java 17, you can directly use:

- `-XX:StartFlightRecording` at JVM launch.
- `jcmd <pid> JFR.start` to start a recording on an already-running JVM.
- The `jdk.jfr` API when controlling recordings from Java code.

Do not follow legacy guides instructing you to pass `-XX:+UnlockCommercialFeatures` or `-XX:+FlightRecorder` for Java 17. Those flags are not required to initialize JFR in modern JDKs.

## 3. Choosing a Recording Configuration

JFR uses event configurations (event settings) to determine which events are recorded, sampling frequencies, and recording thresholds.

### 3.1. The default Configuration

`default` aims to capture useful data with low overhead, making it suitable for longer observation or background recordings in many scenarios.

Example:

~~~bash
jcmd <pid> JFR.start name=continuous settings=default
~~~

Do not assume `default` records every event or always provides enough detail for every bottleneck. If deeper analysis is needed, consider `profile` or a custom JFC configuration.

### 3.2. The profile Configuration

`profile` records more detailed events, making it helpful for time-bounded profiling sessions:

~~~bash
jcmd <pid> JFR.start name=investigation settings=profile duration=120s
~~~

The `profile` configuration can generate more data and higher overhead than `default`. Use a duration suited to your investigation goal rather than leaving detailed `profile` recordings running indefinitely.

### 3.3. Custom JFC Configuration Files

JFR supports JFC configuration files. You can use configurations bundled with the JDK or create your own to enable/disable events and tune thresholds, periods, and stack traces as needed.

Example passing a configuration file:

~~~bash
jcmd <pid> JFR.start name=custom settings=/opt/app/jfr/custom.jfc
~~~

The path must exist and be readable by the JVM. Custom configurations should be versioned alongside the application or operational runbooks to prevent undocumented drift across runs.

### 3.4. Choosing a Configuration by Goal

| Goal | Starting Configuration |
|---|---|
| Background recording to retain recent data near an incident | `default`, with size/age limits |
| Investigating CPU, allocations, or locks over a short window | `profile` |
| Tracking a specific group of events | Custom JFC |
| Deep investigation of class/object retention | Configuration with relevant events; weigh overhead and sensitive data |

Do not enable every event at maximum detail by default. Select events based on the hypothesis you need to test.

## 4. Starting a Recording at JVM Startup

If you want to record starting from the startup phase, pass `-XX:StartFlightRecording` when running the application.

~~~bash
java -XX:StartFlightRecording=name=startup,settings=profile,duration=2m,filename=recordings/startup.jfr,dumponexit=true -jar app.jar
~~~

Components:

- `name=startup`: recording name.
- `settings=profile`: uses the `profile` configuration.
- `duration=2m`: recording automatically stops after two minutes.
- `filename=recordings/startup.jfr`: target file for saving data.
- `dumponexit=true`: requests dumping the recording when the JVM exits.

The `recordings` directory must already exist and the process must have write permissions. Use absolute paths in deployment environments to avoid relying on the working directory.

### 4.1. When Is Startup Recording Useful?

Some issues only appear during:

- Class loading and framework initialization.
- Connection pool initialization.
- JIT compilation of first-invoked methods.
- Cache warm-up.
- Reading configuration or loading initial datasets.

If you only attach after the application has stabilized, earlier events are not present in the new recording. Use a startup recording when investigating these early phases.

### 4.2. Recordings Do Not Have to Specify a Duration

You can start a recording at startup and let it run until the JVM exits or is controlled through an appropriate mechanism:

~~~bash
java -XX:StartFlightRecording=name=background,settings=default,filename=recordings/background.jfr,dumponexit=true -jar app.jar
~~~

For long-running recordings, manage disk capacity carefully. Do not let files grow unchecked on small filesystems or ephemeral containers.

### 4.3. Common Options

| Option | Meaning |
|---|---|
| `name` | Recording name |
| `settings` | JFC file or built-in configuration such as `default`/`profile` |
| `duration` | Recording duration |
| `filename` | Where to write the file when dumped/completed per configuration |
| `dumponexit` | Dump recording when the JVM exits |
| `maxage` | Maximum age of data retained in a disk recording |
| `maxsize` | Maximum size of data retained in a disk recording |
| `disk` | Whether recording data is stored on disk or in memory |

Specific options and combinations must follow Java 17 syntax. Run:

~~~bash
java -XX:StartFlightRecording=help
~~~

to inspect the option descriptions supported by your runtime.

## 5. Starting a Recording on a Running JVM with jcmd

This is the common approach when investigating an already-started application without restarting it.

### 5.1. Finding the PID

List JVMs the tool can attach to:

~~~bash
jcmd -l
~~~

Output typically shows PIDs and main class/JAR names. Select the application process to record. Inside containers, the PID seen inside the container may differ from the host PID; run the tool inside the proper namespace or management environment.

### 5.2. Checking Existing Recordings

~~~bash
jcmd <pid> JFR.check
~~~

This displays existing recordings and their status. You can pass verbose for more details:

~~~bash
jcmd <pid> JFR.check verbose=true
~~~

Checking before starting prevents creating duplicate recordings or name collisions.

### 5.3. Starting a Time-Bounded Recording

~~~bash
jcmd <pid> JFR.start name=incident settings=profile duration=120s filename=/var/tmp/incident.jfr
~~~

The JVM starts a recording named `incident`. The recording stops automatically after the specified duration, saving data to the target file. The target directory must be writable.

You can check status again:

~~~bash
jcmd <pid> JFR.check
~~~

If you need exact runtime syntax:

~~~bash
jcmd <pid> help JFR.start
~~~

### 5.4. Starting a Bounded Background Recording

To maintain a recent rolling window for incident investigation:

~~~bash
jcmd <pid> JFR.start name=continuous settings=default disk=true maxage=6h maxsize=512M
~~~

Meaning:

- `disk=true`: the recording uses disk storage.
- `maxage=6h`: retains data within roughly a six-hour time window.
- `maxsize=512M`: caps retained data size per configuration.

When the age or size limit is reached, older data is evicted to preserve the recent recording window. This is useful for background recordings, though disk I/O and remaining space must be considered.

## 6. How Do Dump, Stop, and Save Differ?

Distinguish three operations:

| Command | Effect | Does the Recording Continue? |
|---|---|---|
| `JFR.check` | View recording status | Yes |
| `JFR.dump` | Write a snapshot of current data to a file | Yes |
| `JFR.stop` | Stop the recording and optionally write data to a file | No |

### 6.1. Dumping a Snapshot While Continuing to Record

When you want to save data collected so far while continuing observation:

~~~bash
jcmd <pid> JFR.dump name=continuous filename=/var/tmp/incident-snapshot.jfr
~~~

`JFR.dump` creates a snapshot file. The `continuous` recording keeps running, so you can dump again later once more data accumulates.

This is suitable when:

- A latency spike was just detected and you want to preserve data before the ring buffer overwrites it.
- You want to save a snapshot for analysis while still monitoring ongoing behavior.
- You want multiple timestamps to compare before and after an action.

### 6.2. Stopping a Recording and Saving the File

Once sufficient data has been captured:

~~~bash
jcmd <pid> JFR.stop name=continuous filename=/var/tmp/continuous-final.jfr
~~~

This stops the recording named `continuous` and writes remaining data to the target file. Once stopped, that recording no longer accepts new events.

If a `filename` was configured at start time, the runtime may use that configured destination. Operationally, passing an explicit `filename` on dump/stop ensures you know exactly where the resulting file is saved.

### 6.3. Automatic Completion via Duration

If started with:

~~~bash
jcmd <pid> JFR.start name=short-profile settings=profile duration=90s filename=/var/tmp/short-profile.jfr
~~~

the recording stops automatically after the configured duration. You do not need to send `JFR.stop` if your goal is simply to record that exact window. Use `JFR.check` to verify whether the recording is still running or has finished.

### 6.4. Dump Does Not Replace Stop

A common operational mistake is dumping a file and forgetting the recording is still running. The snapshot file is saved, yet the JVM continues collecting events and consuming resources.

When the recording is no longer needed, stop it:

~~~bash
jcmd <pid> JFR.stop name=incident
~~~

If you need a final file, specify `filename` on the stop command or use the previously configured destination. Afterward, verify with `JFR.check`.

## 7. Storage and Capacity Management

### 7.1. Clear Filenames

Recording files typically end in `.jfr`. Name files to reflect:

- Service or instance name.
- Timestamp or incident ID.
- Recording purpose.
- Application version if needed.

Example:

~~~text
orders-api-2026-11-15-p99-spike.jfr
~~~

Avoid generic names like `recording.jfr` where multiple instances or runs could overwrite or mix up files.

### 7.2. Limiting maxage and maxsize

For long-running disk recordings, use `maxage` and `maxsize` to bound the data window:

~~~bash
jcmd <pid> JFR.start name=rolling settings=default disk=true maxage=2h maxsize=256M
~~~

These two limits prevent unbounded storage growth. They can cause older events to be evicted as recording continues; therefore, when an incident occurs, dump a snapshot early to preserve the data needed for analysis.

### 7.3. Memory Recordings vs. Disk Recordings

JFR can retain data in memory or on disk:

- Disk recordings suit longer durations managed by age/size limits.
- Memory recordings suit short windows or controlled snapshotting; un-dumped data may be lost if the JVM exits.

Example starting an in-memory recording:

~~~bash
jcmd <pid> JFR.start name=memory-window settings=profile disk=false
~~~

When saving a snapshot:

~~~bash
jcmd <pid> JFR.dump name=memory-window filename=/var/tmp/memory-window.jfr
~~~

Do not run long-term memory recordings without understanding memory limits and old-data eviction. In production situations needing data preserved across restarts, dump to a file before the process exits.

### 7.4. Recording Data Can Be Sensitive

JFR can record stack traces, thread names, class names, file paths, I/O details, exception messages, and custom events. Depending on events and configuration, recordings may expose implementation details or application data.

Be sure to:

- Store files in locations with restricted access permissions.
- Avoid attaching recordings to public tickets without reviewing contents first.
- Enforce retention limits and deletion policies per operational rules.
- Protect directory paths and permissions inside containers/hosts.
- Verify custom events do not record unnecessary secrets, tokens, or personal information.

## 8. Using the jfr Tool to Inspect Recordings

Once you have a file, JDK 17 provides the `jfr` command to read basic contents.

### 8.1. Summarizing a File

~~~bash
jfr summary /var/tmp/incident-snapshot.jfr
~~~

The summary displays recording duration, event counts by type, and overview details. This is the first step to confirm the file contains data and check which event types appear.

### 8.2. Printing a Group of Events

~~~bash
jfr print --events jdk.GarbageCollection,jdk.ExecutionSample /var/tmp/incident-snapshot.jfr
~~~

You can select other events depending on your goal, such as:

- `jdk.CPULoad`.
- `jdk.ThreadPark`.
- `jdk.JavaMonitorEnter`.
- `jdk.SocketRead`.
- `jdk.FileRead`.
- `jdk.ObjectAllocationSample`.

Event names and available data depend on the recording configuration. If an event was disabled or did not occur during the recording window, the file may not contain it.

### 8.3. Printing in JSON Format

To convert event data to JSON for downstream processing:

~~~bash
jfr print --json --events jdk.GarbageCollection /var/tmp/incident-snapshot.jfr
~~~

JSON output can be large; limit events or data ranges appropriately. Do not dump a massive recording to the terminal when you only need to inspect a few events.

### 8.4. Viewing in Java Mission Control

JMC provides a UI to:

- Inspect timelines and events over time.
- Analyze CPU samples and hot methods.
- Inspect GC pauses and heap behavior.
- Locate blocked/parked threads or lock contention.
- Analyze allocations and I/O.
- Filter events by thread, class, stack trace, or time window.

JMC can be installed separately; it is not necessarily bundled in every JDK installation. Use a JMC version that supports Java 17's JFR format.

## 9. Controlling JFR from Java Code

If an application or test harness needs to start/stop recordings around a specific scenario, use the `jdk.jfr.Recording` API.

### 9.1. Programmatic Recording Example

~~~java
import jdk.jfr.Configuration;
import jdk.jfr.Recording;

import java.nio.file.Path;
import java.time.Duration;

public class ProgrammaticJfr {
    public static void main(String[] args) throws Exception {
        Path output = Path.of("recordings/workload.jfr");

        try (Recording recording =
                     new Recording(Configuration.getConfiguration("profile"))) {
            recording.setName("workload");
            recording.setToDisk(true);
            recording.setMaxAge(Duration.ofMinutes(10));
            recording.setMaxSize(256L * 1024 * 1024);

            recording.start();

            runWorkload();

            recording.stop();
            recording.dump(output);
        }
    }

    private static void runWorkload() {
        // Run the workload to measure.
    }
}
~~~

Explanation:

1. `Configuration.getConfiguration("profile")` retrieves the built-in profile configuration.
2. `new Recording(configuration)` creates a new recording.
3. `setName` assigns an identifying name.
4. `setToDisk(true)` configures a disk-backed recording.
5. `setMaxAge` and `setMaxSize` set retention limits.
6. `start()` begins recording.
7. `stop()` stops recording.
8. `dump(output)` writes captured data to a file.
9. `close()` from try-with-resources closes the recording and releases managed resources.

The target directory must exist and be writable. If the project uses the module system, declare the dependency:

~~~java
module com.example.app {
    requires jdk.jfr;
}
~~~

### 9.2. Dumping a Snapshot and Continuing Recording

Through the API, you can dump recorded data while the recording stays active:

~~~java
recording.dump(Path.of("recordings/snapshot.jfr"));
~~~

After the snapshot, the recording continues. When ready to finish:

~~~java
recording.stop();
recording.dump(Path.of("recordings/final.jfr"));
~~~

Use distinct filenames to avoid confusing intermediate snapshots with the final file.

### 9.3. Using RecordingStream for Continuous Event Processing

`RecordingStream` can consume JFR events as they are emitted, useful for custom observability or alerting. This differs from simply writing a file for post-mortem analysis.

If your goal is to save a recording for investigation, `Recording` is usually more direct. Use `RecordingStream` only when the application genuinely needs continuous event processing and has accounted for callbacks, backpressure, processing cost, and stream lifecycle.

## 10. Choosing How to Start a Recording by Situation

| Situation | Appropriate Approach |
|---|---|
| Need to capture startup | `-XX:StartFlightRecording` |
| JVM is running and a latency spike just appeared | `jcmd JFR.start` or dump an existing background recording |
| Want to retain a recent rolling window | Background recording with `default`, `disk=true`, `maxage`, and `maxsize` |
| Need detailed profiling over a short window | `profile` with `duration` |
| Application needs to control recording along a code path | `jdk.jfr.Recording` API |
| Need quick inspection in the terminal | `jfr summary` and `jfr print` |
| Need visual timeline/stack analysis | JMC |

Do not start a new recording if an appropriate background recording is already active. Check with `JFR.check`, dump a snapshot if needed, and stop recordings when collection is no longer required.

## 11. Common Issues When Starting, Dumping, or Stopping

### 11.1. JVM Not Found to Attach

`jcmd -l` does not list the target process.

Possible causes:

- Running `jcmd` in a different host/container namespace.
- The user running the tool lacks attach permissions.
- The JVM exited or its PID changed.
- The runtime restricts attach per environment configuration.

Re-check the PID, user, container, and JDK in use. Do not mistake an attach error for JFR being unsupported.

### 11.2. Recording Not Saved to File

Possible causes:

- `JFR.dump` or `JFR.stop` was not invoked with a proper `filename`.
- The target directory does not exist or lacks write permissions.
- The JVM exited before a memory recording was dumped.
- The recording was already stopped or the recording name was misspelled.

Check `JFR.check`, the path, and write permissions; verify the exact recording name.

### 11.3. Recording Keeps Running After Dump

This is the expected behavior of `JFR.dump`. Dumping only creates a snapshot.

If you do not want recording to continue, invoke `JFR.stop` or let the recording expire via `duration`.

### 11.4. Stopped Without Producing the Expected File

Check the `filename` configured at start and the `filename` passed at stop. Do not assume the file is saved into the current working directory if no explicit path was specified.

### 11.5. Recording Too Large

Possible causes:

- Running `profile` for too long.
- Enabling too many events or setting thresholds too low.
- Omitting `maxage`/`maxsize` on a background recording.
- Emitting many custom events with large payloads.

Shorten duration, choose appropriate settings, cap storage limits, and filter events to match your goal.

### 11.6. Expected Events Missing

The event may not be enabled in settings, may not have occurred during the recording window, or may have been filtered out by threshold/period. Check the JFC configuration and recording time span before drawing conclusions.

### 11.7. Using Legacy Flags

Do not add `-XX:+UnlockCommercialFeatures` or `-XX:+FlightRecorder` from outdated guides. JFR is integrated and supported in JDK 17; use current `java`/`jcmd` syntax.

## 12. Overhead and Data Safety

JFR is designed for low-overhead event recording in many scenarios, though overhead is never zero. Impact depends on:

- Settings and number of enabled events.
- Event frequency and stack trace capture.
- Recording duration.
- Workload, thread count, and event emission rate.
- Storage device and disk recording configuration.

Before enabling detailed recordings in production:

1. Choose settings suited to your goal.
2. Set `duration` or `maxage`/`maxsize`.
3. Measure the recording's impact under a representative workload.
4. Confirm storage location and disk quota.
5. Check whether sensitive data could appear in events.
6. Establish a procedure to dump/stop and clean up files after investigation.

If long-term monitoring is needed, start with `default` and cap the rolling window. When an incident occurs, dump a snapshot before older data is evicted. Switch to detailed `profile` only for the brief window needed.

## 13. Practical Scenario: Capturing a Recording When p99 Spikes

Suppose a Java 17 service is running and p99 latency suddenly spikes. A workflow could be:

### Step 1: Check the JVM and Active Recordings

~~~bash
jcmd -l
jcmd <pid> JFR.check
~~~

If a background recording already exists, dump a snapshot first to preserve data around the incident time.

### Step 2: Dump the Background Recording

~~~bash
jcmd <pid> JFR.dump name=continuous filename=/var/tmp/orders-before-change.jfr
~~~

The recording keeps running after this command.

### Step 3: Start a Time-Limited Detailed Profiling Session

~~~bash
jcmd <pid> JFR.start name=p99-investigation settings=profile duration=120s filename=/var/tmp/orders-p99-profile.jfr
~~~

Run or wait for the spike-inducing workload during the recording window. Avoid injecting artificial load unlike production if your goal is finding the real-world cause.

### Step 4: Check Status

~~~bash
jcmd <pid> JFR.check verbose=true
~~~

If the recording is still running and you have enough data, dump a snapshot:

~~~bash
jcmd <pid> JFR.dump name=p99-investigation filename=/var/tmp/orders-p99-snapshot.jfr
~~~

### Step 5: Stop When Recording Is No Longer Needed

~~~bash
jcmd <pid> JFR.stop name=p99-investigation filename=/var/tmp/orders-p99-final.jfr
jcmd <pid> JFR.stop name=continuous
~~~

Stop the background recording only if you no longer need the rolling window. If background recording is part of long-term observability policy, leave it running per operational procedures.

### Step 6: Inspect Summary and Events

~~~bash
jfr summary /var/tmp/orders-p99-final.jfr
jfr print --events jdk.GarbageCollection,jdk.ExecutionSample,jdk.ThreadPark /var/tmp/orders-p99-final.jfr
~~~

Open the file in JMC to correlate GC, CPU samples, thread states, and lock events against the spike timestamps.

### Step 7: Record Findings

Save:

- Recording name and settings.
- Start/stop timestamps.
- PID, JDK version, and application version.
- Workload during the recording window.
- JFR file and secure storage location.
- Events or stack traces relevant to the hypothesis.

Do not conclude from a single event alone. Correlate with application metrics, logs, tracing, and OS resources.

## 14. Practice Exercises

### Exercise 1 — Recording at Startup

Launch a Java 17 application with `-XX:StartFlightRecording`, name `startup`, `profile` settings, 60-second duration, and a specific filename. Open the file with `jfr summary` and note the event counts.

### Exercise 2 — Attaching to a Running JVM

Run an application in the background, find its PID with `jcmd -l`, start a `default` recording, verify with `JFR.check`, and then stop and save the file.

### Exercise 3 — Dumping Without Stopping

Start a recording without a duration. Call `JFR.dump` twice at different points in time. Verify the recording remains active between dumps; then call `JFR.stop`.

### Exercise 4 — Limiting a Background Recording

Start a disk recording with `maxage` and `maxsize`. Explain why this controls the data window for long-running recordings.

### Exercise 5 — Comparing default and profile

Run the same workload with `default` and `profile` settings for equivalent durations. Compare event counts, file sizes, and observed overhead. Do not assume `profile` is always better.

### Exercise 6 — Using the Java API

Create a recording with `Configuration.getConfiguration("profile")`, start it, run a task, stop it, and dump to a file. Ensure the recording is closed even if the workload throws an exception.

### Exercise 7 — Analyzing Files

Use `jfr summary` and `jfr print` to filter `GarbageCollection` and `ExecutionSample`. Open the file in JMC and identify relationships among CPU, GC, and thread activity.

## 15. Completion Criteria

Learners complete this lesson when they can:

1. Explain what events a JFR recording captures and what format the output file uses.
2. Start a recording at JVM launch using `-XX:StartFlightRecording`.
3. Find a PID and use `jcmd` to start/check/dump/stop recordings.
4. Distinguish dumping a snapshot from stopping a recording.
5. Choose `default`, `profile`, or a JFC file based on the goal.
6. Bound recording duration, size, and data age.
7. Use the `jdk.jfr.Recording` API to control recordings from Java code.
8. Inspect files using `jfr summary`, `jfr print`, or JMC.
9. Recognize overhead, attach permissions, output paths, and sensitive data risks.
10. Avoid legacy JFR flags or leaving recordings/files unbounded.

## 16. Official Documentation

- [Java SE 17 JFR Runtime Guide](https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder.html): overview of Java Flight Recorder and usage.
- [Java SE 17 API — `jdk.jfr.Recording`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Recording.html): creating, starting, stopping, dumping, and closing recordings.
- [Java SE 17 API — `jdk.jfr.Configuration`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Configuration.html): built-in and JFC configurations.
- [Java SE 17 man page — `jcmd`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): diagnostic commands for a running JVM.
- [Java SE 17 man page — `java`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-XX:StartFlightRecording` option.
- [Java SE 17 man page — `jfr`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html): `summary`, `print`, and operations on recording files.
- [OpenJDK JEP 328 — Flight Recorder](https://openjdk.org/jeps/328): JFR in OpenJDK.

**Key Takeaway:** `JFR.start` begins collection, `JFR.dump` saves a snapshot while the recording continues, and `JFR.stop` ends the recording. Choose settings to match your goal, limit duration/capacity, store files securely, and analyze data alongside application metrics. Java 17 supports JFR out of the box; no legacy unlock flags are needed.
