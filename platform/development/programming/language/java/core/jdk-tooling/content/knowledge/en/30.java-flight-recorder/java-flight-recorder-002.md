# Starting a Recording with Java Flight Recorder

## 1. What is a Recording in JFR?

Java Flight Recorder (JFR) records events that occur in the JVM and Java applications over time. A recording can contain data about garbage collection, object allocation, CPU sampling, threads, lock contention, class loading, JIT compilation, file I/O, socket I/O, and other runtime activities.

Each recording is a data collection session with its own configuration. When a recording starts, the JVM applies the selected event settings and begins storing events in memory or in a disk repository. A recording can be stopped manually or end automatically after a configured duration to produce a binary `.jfr` file.

Starting a recording is the first step in a performance investigation workflow:

1. Identify the target JVM to observe.
2. Choose when to start and configure the events.
3. Set the duration, size limits, and where to store the data.
4. Confirm that the recording is running.
5. Stop the recording and keep the file for analysis.

There are three common ways to start a recording:

| Approach | Timing | Tool |
|---|---|---|
| At JVM startup | From the very beginning of the application lifecycle. | `-XX:StartFlightRecording` |
| On a running JVM | Attach to the process without restarting. | `jcmd PID JFR.start` |
| From Java code | The application controls the recording itself. | `jdk.jfr.Recording` API |

If you need to capture the startup phase as well, use the JVM option or the Java API before the workload begins. If the issue appears after the application has been running for a while, attaching with `jcmd` is usually more convenient.

## 2. Prerequisites Before Starting a Recording

Before starting a recording, identify the right JVM and check the environment:

- Use a JDK that includes JFR and `jcmd`, `jfr` tools matching the runtime.
- The target JVM must support JFR and must not have this feature disabled.
- When attaching with `jcmd`, the tool must run on the same machine as the target JVM.
- The user running `jcmd` typically must match the user running the JVM.
- The JVM must allow the Attach mechanism.
- In containers, the PID seen from the host may differ from the PID inside the container; use the PID from the correct namespace.
- The user running the JVM must have write permission to the directory containing the recording file.

Find Java processes:

~~~bash
jcmd -l
~~~

Example:

~~~text
18420 com.example.orders.OrderService
27116 com.example.worker.BatchWorker
~~~

The number at the beginning of each line is usually the local PID. Check the main class or command line to select the right application. Do not use PID 0 to start a recording in production because PID 0 can send the diagnostic command to multiple JVMs capable of receiving commands.

Verify the JFR commands supported by the JVM:

~~~bash
jcmd 18420 help JFR.start
jcmd 18420 help JFR.check
jcmd 18420 help JFR.stop
~~~

The target JVM's help output is the authoritative source for syntax, default values, and impact on the exact JDK version currently running.

## 3. Choosing an Event Configuration: default, profile, and none

The JDK provides template configurations in the `JAVA_HOME/lib/jfr` directory:

| Configuration | Contents | Use Case |
|---|---|---|
| `default.jfc` | Pre-selected set of events with low overhead. | Continuous recording or longer production observation. |
| `profile.jfc` | Collects more data, typically with more detailed sampling and stack traces. | Short-term performance investigation. |
| `none` | Loads no built-in event configuration. | Manually enabling only the exact events needed. |

If `settings` is omitted in `JFR.start`, the default configuration is `default.jfc`.

Example using the lightweight configuration:

~~~bash
jcmd 18420 JFR.start name=continuous-observation settings=default
~~~

Example for a short-term deep investigation:

~~~bash
jcmd 18420 JFR.start name=short-profile settings=profile duration=2m
~~~

Example starting with an empty configuration:

~~~bash
jcmd 18420 JFR.start name=selected-events settings=none
~~~

`default` is suitable for routine observation because it enables only a curated set of events to minimize overhead. `profile` records additional data, but increases event volume, stack traces, file size, and performance impact. Do not use `profile` indefinitely just to get more data.

`none` is useful when only a few specific events are needed. If no events are enabled, the recording may contain only metadata and baseline events; configure events before expecting the file to contain data for analysis.

## 4. JFR.start Syntax with jcmd

General syntax:

~~~bash
jcmd <pid> JFR.start [options] [event-settings]
~~~

Simple example:

~~~bash
jcmd 18420 JFR.start
~~~

Example with name, settings, and duration:

~~~bash
jcmd 18420 JFR.start name=api-investigation settings=default duration=10m
~~~

Commonly used parameters:

| Parameter | Meaning |
|---|---|
| `name` | Recording name to identify it when checking or stopping. |
| `settings` | Event configuration file, e.g., `default`, `profile`, `none`, or a path to a `.jfc` file. |
| `duration` | Recording duration. The default `0s` means no time limit. |
| `delay` | Wait time before starting to record. |
| `filename` | Path to the recording file when the recording completes or is stopped. |
| `disk` | Whether to write recording data to the disk repository while running; default is `true`. |
| `maxage` | Maximum age of data retained in the disk repository. |
| `maxsize` | Maximum size of data retained on disk. |
| `dumponexit` | Automatically save the recording when the JVM shuts down. |
| `path-to-gc-roots` | Collect paths from objects to GC roots when the recording ends. |

`name` is optional. If omitted, the JVM generates a name automatically and returns the name/ID in the command output. Giving a readable name helps avoid confusing recordings when multiple sessions are running concurrently.

Example:

~~~bash
jcmd 18420 JFR.start name=checkout-latency settings=default
jcmd 18420 JFR.start name=allocation-profile settings=profile duration=90s
~~~

JFR allows multiple recordings to exist simultaneously. Each recording can use a different name, duration, and configuration; however, overhead and storage usage increase with the number of active recordings.

## 5. Setting Duration and Start Timing

### duration

`duration` determines how long the recording runs:

~~~bash
# Record for 30 seconds
jcmd 18420 JFR.start name=quick-check duration=30s settings=default

# Record for 5 minutes
jcmd 18420 JFR.start name=service-check duration=5m settings=default

# Record for 1 hour
jcmd 18420 JFR.start name=long-check duration=1h settings=default
~~~

Valid units are seconds (`s`), minutes (`m`), and hours (`h`). A value of `0s` means the recording runs until stopped or the JVM exits.

If you only want to capture a specific incident window, set an explicit duration so the recording ends automatically. If continuous monitoring is needed, you can omit `duration`, but you must manage storage limits and when to stop it.

### delay

`delay` postpones when recording begins:

~~~bash
jcmd 18420 JFR.start name=scheduled-profile delay=2m duration=5m settings=profile
~~~

In this example, the JVM waits two minutes before recording for five minutes. `delay` is useful when preparing a recording ahead of a scheduled load burst or synchronizing with a test run.

Both `delay` and `duration` use the `s`, `m`, or `h` suffixes. When using both, specify them explicitly in the command and verify the recording with `JFR.check`.

### Combining duration with filename

~~~bash
jcmd 18420 JFR.start name=timed-profile settings=profile duration=4s filename=recordings/profile.jfr
~~~

After about four seconds, the recording finishes automatically and the file is written. The file does not necessarily appear as soon as the command starts; when the file is written depends on when the recording finishes or is dumped.

## 6. Naming and Setting the File Path

When you need to keep a recording, specify `filename` explicitly:

~~~bash
jcmd 18420 JFR.start name=incident settings=default filename=recordings/incident.jfr
~~~

Relative paths are resolved in the target JVM's environment. In production, use an absolute path to avoid confusion over the working directory.

JFR supports two placeholders in `filename`:

- `%p` is replaced with the JVM's PID.
- `%t` is replaced with a timestamp in `yyyy_MM_dd_HH_mm_ss` format.

Example:

~~~bash
jcmd 18420 JFR.start name=service-profile settings=profile duration=3m filename=recordings/service-%p-%t.jfr
~~~

Ensure the directory already exists and the user running the JVM has write permission. For paths containing spaces, quote the parameter value appropriately for the shell in use.

If `filename` is not specified, the JVM may generate a filename based on the PID and date/time according to the command's rules and save time. For predictable operations workflows, always provide an explicit `filename`.

## 7. Saving a Recording on JVM Shutdown

`dumponexit` instructs the JVM to save the recording on shutdown:

~~~bash
jcmd 18420 JFR.start name=shutdown-capture settings=default dumponexit=true
~~~

The default is `dumponexit=false`. If set to `true` without a `filename`, the JVM generates an automatic filename in the process's working directory. You can specify an explicit `filename`:

~~~bash
jcmd 18420 JFR.start name=shutdown-capture settings=default filename=recordings/shutdown.jfr dumponexit=true
~~~

This option is useful when the application might exit before an operator can dump the data. However, the file is only written when the JVM shuts down; for long-running processes, `dumponexit` cannot replace actively saving the recording.

For recordings with a `duration`, the specified `filename` is used when the recording completes automatically. For unbounded recordings, you can use `dumponexit` or stop it manually and provide a `filename`.

## 8. Size Limits and the Disk Repository

When `disk=true`, JFR writes data to the disk repository while the recording is running. This is the default and is suitable for longer recordings.

You can limit the age and size of retained data:

~~~bash
jcmd 18420 JFR.start name=bounded-recording settings=default maxage=30m maxsize=256M
~~~

- `maxage=30m` limits the data kept in the repository to roughly the most recent 30 minutes.
- `maxsize=256M` limits the data size on disk to 256 MB.
- `maxage=0s` means no age limit.
- `maxsize=0` means no size limit.

`maxage` and `maxsize` are only valid when `disk=true`. `maxsize` supports `M`/`m` suffixes for megabytes and `G`/`g` for gigabytes. The value must not be smaller than `maxchunksize` configured for JFR; the default in JDK 24 is 12 MB.

You can check the JFR configuration:

~~~bash
jcmd 18420 JFR.configure
~~~

Do not set `maxsize` too low relative to the volume of event data you need to capture. If the repository fills up or older data is evicted, the recording may no longer contain the time window you need to investigate.

## 9. Choosing Disk or In-Memory Recording

The `disk` parameter controls whether data is written to disk during the recording:

~~~bash
jcmd 18420 JFR.start name=memory-recording settings=default disk=false duration=30s
~~~

When `disk=false`, JFR does not continuously write recording data to the disk repository. This mode is suitable for short recordings with bounded memory usage. The `maxage` and `maxsize` options are invalid when disk is disabled.

When you need to collect over a longer period or maintain a stable rolling window of data, use `disk=true` and set appropriate `maxage`/`maxsize` limits. Check JFR's help on your exact JDK to understand memory limits and how data is exported in in-memory mode for that version.

## 10. Customizing Events When Starting a Recording

Besides selecting a settings file, `JFR.start` allows overriding event settings directly on the command line.

Syntax:

~~~text
<event-name>#<setting-name>=<value>
~~~

Example lowering the threshold for monitor contention events:

~~~bash
jcmd 18420 JFR.start name=lock-profile settings=default jdk.JavaMonitorEnter#threshold=1ms
~~~

Enabling stack traces for an event:

~~~bash
jcmd 18420 JFR.start name=lock-stacks settings=default jdk.JavaMonitorEnter#threshold=1ms jdk.JavaMonitorEnter#stackTrace=true
~~~

When using `settings=none`, prepend a `+` sign before the event name to add a new event setting:

~~~bash
jcmd 18420 JFR.start name=custom-events settings=none +jdk.JavaMonitorEnter#enabled=true +jdk.JavaMonitorEnter#threshold=1ms +jdk.JavaMonitorEnter#stackTrace=true
~~~

Common settings include:

| Setting | Meaning |
|---|---|
| `enabled` | Enable or disable the event. |
| `threshold` | Only record events whose duration exceeds the threshold. |
| `period` | Sampling interval for periodic events. |
| `stackTrace` | Collect stack traces alongside the event. |

Not every event supports every setting. Valid event names and values should be checked against the metadata of the JDK in use.

JFR also supports configuration-level options such as `gc`, `allocation-profiling`, `method-profiling`, `locking-threshold`, and `socket-threshold`. When a command-line option conflicts with a setting in a `.jfc` file, the command-line parameter takes precedence.

## 11. Creating a Custom .jfc Configuration File

When you need to reuse the same set of events repeatedly, create a `.jfc` file with `jfr configure`.

Example increasing GC and method profiling detail:

~~~bash
jfr configure gc=high method-profiling=high --output incident.jfc
~~~

Example configuring a lock event:

~~~bash
jfr configure jdk.JavaMonitorEnter#threshold=1ms --output locks.jfc
~~~

Start a recording using the newly created file:

~~~bash
jcmd 18420 JFR.start name=incident-profile settings=incident.jfc duration=3m
~~~

The configuration file describes which events are enabled, along with their thresholds, periods, and stack trace settings. If the file is not in `JAVA_HOME/lib/jfr`, pass the path to the file:

~~~bash
jcmd 18420 JFR.start name=custom-profile settings=recordings/incident.jfc
~~~

Multiple settings files can be combined by repeating the `settings` parameter. Use `.jfc` files verified on the exact JDK version to avoid incompatible events or settings.

## 12. Starting a Recording at JVM Startup

The JVM option `-XX:StartFlightRecording` enables a recording before the application begins processing its workload.

Example:

~~~bash
java -XX:StartFlightRecording=name=boot-recording,settings=default,duration=3m,filename=recordings/boot.jfr -jar app.jar
~~~

Values are comma-separated. You can set `name`, `settings`, `duration`, `filename`, `dumponexit`, `maxage`, and `maxsize` as needed.

Example of a short recording to investigate startup:

~~~bash
java -XX:StartFlightRecording=name=startup-profile,settings=profile,duration=60s,filename=recordings/startup.jfr -jar app.jar
~~~

Example of continuous monitoring saved when the process exits:

~~~bash
java -XX:StartFlightRecording=name=continuous,settings=default,dumponexit=true -jar app.jar
~~~

`-XX:StartFlightRecording` is appropriate when you need to start collecting before the `main` method runs. If you use `jcmd` after the application has started, events that occurred before attaching will not be in the recording.

## 13. Starting a Recording via the Java API

Applications can create recordings using `jdk.jfr.Recording`. This approach is useful when recording depends on application logic or needs to be enabled for a specific section of code.

Key steps:

1. Load a configuration using `Configuration.getConfiguration("default")`.
2. Create a `Recording`.
3. Set the name and age/size limits if needed.
4. Enable additional events.
5. Call `start()` to begin collecting.
6. Call `stop()` and `dump(Path)` to save the file.

Java 17 example:

~~~java
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Configuration;
import jdk.jfr.Recording;

public class JfrApiStartDemo {
    public static void main(String[] args) throws Exception {
        try (Recording recording =
                 new Recording(Configuration.getConfiguration("default"))) {
            recording.setName("api-start-recording");
            recording.setMaxAge(Duration.ofMinutes(5));
            recording.setMaxSize(64L * 1024 * 1024);

            recording.enable("jdk.JavaMonitorEnter")
                     .withThreshold(Duration.ofMillis(1))
                     .withStackTrace();

            recording.start();
            System.out.println("API recording started");

            for (int i = 0; i < 20; i++) {
                synchronized (JfrApiStartDemo.class) {
                    Thread.sleep(10);
                }
            }

            recording.stop();
            recording.dump(Path.of(args[0]));
            System.out.println("API recording saved");
        }
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -d out src/JfrApiStartDemo.java
java -cp out JfrApiStartDemo recordings/api-recording.jfr
~~~

Stdout:

~~~text
API recording started
API recording saved
~~~

In this example, the recording begins at `recording.start()`. The `jdk.JavaMonitorEnter` event is enabled with a 1 ms threshold and stack traces. After stopping, `recording.dump()` writes the JFR file. The try-with-resources block closes the recording when finished.

If you only need to enable a recording conditionally within the application, you can call `start()` when the condition occurs and stop/dump when the workload finishes. Avoid leaving recordings unclosed or unbounded when data collection is no longer needed.

## 14. Verifying That a Recording Has Started

After running `jcmd JFR.start`, verify that the recording is running:

~~~bash
jcmd 18420 JFR.check
~~~

Example output:

~~~text
Recording 1: name=incident-recording maxsize=256.0MB maxage=30m (running)
~~~

View event settings:

~~~bash
jcmd 18420 JFR.check verbose=true
~~~

Verbose output shows which events are enabled along with their thresholds, periods, and stack trace settings. Use this output to confirm the configuration before waiting for the workload under investigation.

If you do not see the recording:

- Check the name or ID returned when starting.
- Check whether the `duration` was too short and the recording already finished.
- Confirm the PID belongs to the right JVM.
- Check whether the command was rejected due to an invalid event setting or configuration file.

After the recording finishes and the file is written, verify the file with:

~~~bash
jfr summary recordings/incident.jfr
~~~

`jfr summary` displays the file version, start time, duration, chunk count, and event counts. If the file does not appear while the recording is still running, that can be normal behavior; the file is typically finalized when the recording ends or is dumped.

## 15. Complete Example: Attaching to a Running JVM

Create `src/JfrStartDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class JfrStartDemo {
    public static void main(String[] args) throws Exception {
        List<byte[]> retained = new ArrayList<>();

        System.out.println("JfrStartDemo ready");

        long until = System.nanoTime() + 30_000_000_000L;
        while (System.nanoTime() < until) {
            retained.add(new byte[64 * 1024]);

            if (retained.size() > 32) {
                retained.remove(0);
            }

            Thread.sleep(10);
        }

        System.out.println("JfrStartDemo complete");
    }
}
~~~

Compile and run:

~~~bash
mkdir -p out recordings
javac --release 17 -d out src/JfrStartDemo.java
java -cp out JfrStartDemo
~~~

Stdout:

~~~text
JfrStartDemo ready
JfrStartDemo complete
~~~

The application runs for about 30 seconds, generating allocations while active. Open a second terminal and find the PID:

~~~bash
jcmd -l
~~~

Suppose the PID is `18420`. Start a `default` recording:

~~~bash
jcmd 18420 JFR.start name=runtime-default settings=default maxage=2m maxsize=64M filename=recordings/runtime-default.jfr
~~~

Verify the recording:

~~~bash
jcmd 18420 JFR.check
~~~

After about two seconds, stop and save the file:

~~~bash
jcmd 18420 JFR.stop name=runtime-default filename=recordings/runtime-default.jfr
~~~

Quickly inspect the file:

~~~bash
jfr summary recordings/runtime-default.jfr
~~~

Verified results on JDK 24.0.2:

- `JFR.start` returns the recording ID and running state.
- `JFR.check` lists the recording with its name and size/age limits.
- `JFR.stop` writes a file of about 244.5 KB in the sample run.
- `jfr summary` reads the file with a duration of about two seconds and lists the events.

If you want the recording to end automatically, specify `duration` when starting:

~~~bash
jcmd 18420 JFR.start name=runtime-profile settings=profile duration=4s filename=recordings/runtime-profile.jfr
~~~

After four seconds, the recording finishes automatically and the file can be inspected with `jfr summary`.

## 16. Example: Starting a Recording at Startup

Reuse the compiled `JfrStartDemo` program:

~~~bash
java -XX:StartFlightRecording=name=startup-recording,settings=default,duration=3s,filename=recordings/startup-recording.jfr -cp out JfrStartDemo
~~~

JFR starts when the JVM boots. The application continues running after the recording ends; the recording is written to the file after about three seconds.

Verify:

~~~bash
jfr summary recordings/startup-recording.jfr
~~~

In the JDK 24.0.2 test, the JVM displays the message `Started recording 1`, the program prints `JfrStartDemo ready` and `JfrStartDemo complete`, and the startup recording file is created and read successfully with a three-second duration.

This approach is suitable for capturing startup, initial class loading, or events that occur before `jcmd` can be used.

## 17. Performance Impact and Data Protection

`JFR.start` has an impact described by JDK 24 as Medium; actual impact can range from low to high depending on event settings. Some guidelines:

- Start with `settings=default` for long recordings or routine monitoring.
- Use `settings=profile` for short periods when more detail is needed.
- Set `duration`, `maxage`, and `maxsize` to bound the data.
- Avoid enabling too many events and stack traces before forming an investigation hypothesis.
- Do not increase stack depth or buffer sizes arbitrarily.
- Monitor disk space and write permissions.
- Confirm that recordings are stopped when collection is no longer needed.

`path-to-gc-roots=true` collects paths from objects to GC roots when the recording ends. This is an expensive operation; enable it only when suspecting a memory leak. With `settings=profile`, the data may include stack traces where potentially leaked objects were allocated.

A recording can contain command lines, JVM flags, system properties, environment variables, thread names, classes, methods, stack traces, file paths, and host information depending on the enabled events. Protect JFR files as internal operational data: restrict access permissions, retention time, and where they are shared.

## 18. Common Errors When Starting a Recording

| Symptom | Common Cause | Resolution |
|---|---|---|
| `Unknown diagnostic command` | Target JVM does not support the command or is not a compatible HotSpot JVM. | Run `jcmd PID help` and check the JDK/JVM version. |
| `AttachNotSupportedException` | Attach mechanism is disabled or the environment prevents attaching. | Check the user, JVM options, PID namespace, and permissions. |
| PID not found | Process has exited or the PID does not belong to the current namespace. | Run `jcmd -l` and match the process. |
| `.jfc` file does not exist | Incorrect path or configuration name. | Use the full path and verify the file has been created. |
| Invalid event setting | Incorrect event name, setting name, or value. | Check event metadata and JFR help. |
| Recording lacks expected events | Event is disabled, threshold is too high, or the event did not occur. | Use `JFR.check verbose=true` and adjust settings. |
| File does not appear right after start | Recording is still running or has not been dumped/stopped. | Check `JFR.check`; use `duration`, `filename`, or stop with `filename`. |
| Stopped recording has no file | `JFR.stop` was called without `filename`, so data was discarded. | Stop with `filename=...` in `JFR.stop`. |
| `JFR.check` returns `No available recordings` | Recording has not started, duration expired, or it was already stopped. | Confirm PID and recording name, then start a new session if needed. |
| File write error | Directory does not exist or the user running the JVM lacks write permission. | Create the directory and check permissions. |
| `maxsize` rejected | Value is smaller than `maxchunksize`. | Check `JFR.configure` and set a sufficiently large `maxsize`. |
| Recording stops before workload occurs | `duration` is too short or `delay`/`duration` is misconfigured. | Adjust `delay` and `duration`, and verify with `JFR.check`. |
| High overhead | Using `profile` for too long or enabling overly detailed events/stack traces. | Switch back to `default`, reduce events, and limit duration. |

Note: According to JDK 24 `JFR.stop` help, if `filename` is not provided when stopping, the recording data is discarded. Always provide `filename` when you need to keep the file.

## 19. Pre-Flight Checklist Before Starting a Recording in Production

- Identified the exact PID, host/container, and JDK version.
- Confirmed the JVM supports JFR and allows attach if using `jcmd`.
- Chosen the right timing: startup, runtime attach, or Java API.
- Selected `default`, `profile`, `none`, or a `.jfc` file based on the goal.
- Assigned a clear recording name.
- Set `duration` and `delay` to match the observation window.
- Configured `disk`, `maxage`, and `maxsize` appropriate for retention needs.
- Determined `filename` and target directory, with write permission for the JVM user.
- Enabled `dumponexit` if data must be preserved on JVM shutdown.
- Verified event settings with `JFR.check verbose=true` on runtime attach.
- Considered the overhead of `profile`, stack traces, and GC roots.
- Protected recording files according to internal data policies.
- Planned how to stop the recording and save the file with an explicit `filename`.
- Verified the file is readable using `jfr summary`.

## 20. References

- [The jcmd Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [The java Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html)
- [The jfr Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jfr.html)
- [JDK Flight Recorder API — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/jdk/jfr/package-summary.html)

Starting a JFR recording is a matter of choosing the right JVM, timing, event settings, and storage limits. Use `-XX:StartFlightRecording` when you need to collect from startup, `jcmd PID JFR.start` when the JVM is already running, or `jdk.jfr.Recording` when the application needs programmatic control. Always confirm the recording is active, specify a clear output path, and inspect the file after the recording finishes.
