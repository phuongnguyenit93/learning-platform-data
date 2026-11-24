# 14.3 Launching JFR via `-XX:StartFlightRecording` or `JFR.start` on a Running JVM

## 1. What Does JFR Record and How Do the Two Launch Methods Differ?

**Java Flight Recorder (JFR)** is the JVM's diagnostic event-recording system. A recording can contain CPU samples, garbage collection (GC), memory allocations, class loading, threads, lock contention, file/socket I/O, and many other events depending on **event settings**. After collection, data is exported to a **`.jfr`** file for inspection with the `jfr` tool or **JDK Mission Control (JMC)**.

There are two main launch paths:

- **Startup:** `-XX:StartFlightRecording` is a JVM option passed **before the main class name or `-jar`**. Use it to capture phenomena during process startup, warm-up, class loading, errors that occur only early in a process's life, or to record continuously from the very beginning.
- **Runtime:** `jcmd <PID> JFR.start` sends a diagnostic command to a **running JVM**, starting a new recording **without restarting** if the runtime supports JFR, attach is permitted, and the caller has permissions. Use it when a service is already running and high load, latency, GC, or contention has just appeared.

Both configure a JFR recording inside the JVM. The main differences are **activation timing, where the option is passed, and whether prior events can be observed**. Without a pre-enabled continuous recording, starting `JFR.start` today cannot recover events that happened yesterday.

Examples use **HotSpot/OpenJDK JDK 17+**. JFR can be used on other JDKs, but features, commands, and diagnostic details should be verified against the exact JDK/vendor running the application.

## 2. Decision Table for Choosing the Right Capture Method

| Scenario | Launch at Startup | Launch on a Running JVM |
| --- | --- | --- |
| Error occurs only during the first 10–30 seconds of startup | **Recommended** because it can capture from the moment the JVM starts | Enabling after startup may miss it |
| Production service has been running for days and latency just spiked | Would require changing startup config and restarting if not already enabled | **Recommended**: `JFR.start`, no restart needed |
| Want to always keep the most recent 2 hours of data | `settings=default,disk=true,maxage=2h,...` from startup | Can start a continuous recording while running, but cannot retain data from before it was enabled |
| Want to capture 2 minutes of profiling | `duration=2m,settings=profile` | `JFR.start ... duration=2m settings=profile` |
| Want to save a file immediately while the recording keeps running | Call `JFR.dump` targeting the process PID | Also use `JFR.dump` |
| Want to stop a running recording | `JFR.stop name=...` | Same |
| Cannot attach to the running JVM | Startup flag is an option when deployment config can be updated | `JFR.start` is unavailable until attach permissions/restrictions are resolved |

**Remember:** `-XX:StartFlightRecording` is a Java launch configuration; `JFR.start` is a diagnostic command via `jcmd`. Do **not** place `JFR.start` in JVM startup flags, and do **not** place `-XX:StartFlightRecording` after the application name.

## 3. Standard Syntax: Commas vs. Spaces

### Startup: `-XX:StartFlightRecording`

```bash
java -XX:StartFlightRecording=name=boot,settings=profile,duration=2m,filename=boot.jfr -jar application.jar
```

This is **a single JVM option** whose `key=value` pairs are separated by **commas**, and the flag must appear **before** `-jar`. If Java is launched via classpath, place it before the main class name:

```bash
java -XX:StartFlightRecording=name=boot,settings=default,dumponexit=true,filename=boot.jfr -cp classes com.example.Main
```

Wrong placement:

```bash
java -jar application.jar -XX:StartFlightRecording=filename=boot.jfr
```

In the incorrect line, `-XX:StartFlightRecording=...` is passed as an argument to the application's `main(String[] args)` rather than acting as a JVM option.

### Runtime: `jcmd <PID> JFR.start`

```bash
jcmd -l
jcmd <PID> JFR.start name=incident settings=profile duration=2m filename=incident.jfr
```

`key=value` pairs for `jcmd` are separated by **spaces**. `<PID>` is a placeholder; replace it with the real PID of the target process without typing `<` or `>`. Pick the exact PID—do not use `jcmd 0`, which may send the command to **multiple JVMs**.

Use `java -version` to check the terminal's JDK, and `jcmd <PID> VM.version` to check the **JDK running the target application**. If they differ, consult the documentation and `help` output matching the target runtime.

```bash
jcmd <PID> help JFR.start
jcmd <PID> help JFR.check
jcmd <PID> help JFR.dump
jcmd <PID> help JFR.stop
```

Parameters, limits, and tools can differ across JDKs/vendors. Cross-check the `help` output instead of copying incompatible commands.

## 4. Options That Determine What Data Is Collected

| Option | Effect | Notes |
| --- | --- | --- |
| `name=...` | Identifier for the recording, used by `JFR.check`/`dump`/`stop` | Use a name without spaces for easier shell usage. |
| `settings=default` | Low-overhead event template suited for background observation | Does not mean all events are enabled. |
| `settings=profile` | Template capturing richer profiling details | Typically higher overhead than `default`; use for targeted windows. |
| `delay=20s` | Waits 20 seconds before starting to record | Events in the first 20 seconds are **not in the recording**. |
| `duration=2m` | Auto-stops after 2 minutes of recording | Omitting `duration` usually records indefinitely until stopped or JVM exit. |
| `filename=...` | Location of the `.jfr` file created when the recording ends | The file may **not exist yet** right after start is called. |
| `disk=true` | Uses a temporary disk repository to store JFR data | Does **not mean** every event is continuously appended to `filename`. |
| `maxage=2h` | Keeps only data within a 2-hour age limit | Applies when `disk=true`; older chunks may be deleted. |
| `maxsize=256m` | Limits the size of data retained in the repository | Used with `disk=true`; value must fit JVM chunk limits. |
| `dumponexit=true` | Dumps the recording when the JVM exits normally | Not guaranteed on OOM kill, `SIGKILL`, or host crash. |
| `path-to-gc-roots=true` | Collects paths to GC roots for memory leak investigation | Can incur substantial cost; not enabled by default for every capture. |

**Default vs. profile:** the two configurations `default.jfc` and `profile.jfc` typically live in `JAVA_HOME/lib/jfr`. `default` balances events and sampling frequency for long-running recording; `profile` provides extra data for short-window investigation. Choose based on the question, because collecting more events and stack traces can increase CPU, memory, disk I/O, and data volume. To enable specific events or adjust thresholds, use `.jfc` files and `jfr configure`; inspect actual active settings with `JFR.check verbose=true`.

**`disk` vs. `filename`:** `disk=true` lets the JVM write chunks to a **temporary repository** for the duration of the recording. `filename` is the **output file** upon stop/duration expiry; `JFR.dump` can export a separate snapshot earlier. Do not treat the repository directory as the final artifact location. If `disk=false`, data stays only in bounded memory buffers, making it unsuitable for retaining multi-hour history.

## 5. Recipe A: Recording 2 Minutes from Startup

When investigating slow startup or abnormal Java/JVM class loading:

```bash
java -XX:StartFlightRecording=name=startup,settings=profile,duration=2m,filename=/var/log/app/startup.jfr -jar application.jar
```

Recording begins as soon as the JVM starts, stops after about 2 minutes, and writes the file to `filename`. The directory `/var/log/app` must already exist and be writable by the JVM user. On Windows, change this to a valid Windows path such as `C:\recordings\startup.jfr`. Use absolute paths to avoid working-directory confusion.

If you want to skip initial warm-up and inspect near-steady state:

```bash
java -XX:StartFlightRecording=name=steady,settings=profile,delay=30s,duration=2m,filename=/var/log/app/steady.jfr -jar application.jar
```

`delay` is measured from JVM startup and does **not** automatically synchronize with the service's readiness probe. Events during the delay period are skipped. If the problem occurs during startup, do not add a delay.

If the application exits **before the duration expires**, depending on configuration no output file may exist yet. You can enable `dumponexit=true` to request a dump on normal JVM exit:

```bash
java -XX:StartFlightRecording=name=quick,settings=default,dumponexit=true,filename=quick.jfr -jar application.jar
```

Cases such as `SIGKILL`, kernel/container OOM kill, or host crashes can prevent dump-on-exit; use proactive dumping or continuous recording to reduce the risk of data loss.

## 6. Recipe B: Continuous Recording Always Keeping the Most Recent History

For sporadic incidents where you want data **from before the system triggers an alert**, enable background recording at deployment time:

```bash
java -XX:StartFlightRecording=name=ring,settings=default,disk=true,maxage=2h,maxsize=256m -jar application.jar
```

This is a **continuous recording** with no `duration`, retaining the most recent data within age and size limits. When an incident occurs, open another terminal:

```bash
jcmd -l
jcmd <PID> JFR.check
jcmd <PID> JFR.dump name=ring filename=/var/log/app/ring-incident-%p-%t.jfr
```

`JFR.dump` creates a file from retained events **without stopping the recording**. `%p` and `%t` in `filename` are supported by the JDK to substitute the PID and timestamp, preventing consecutive dumps from overwriting each other. If you want another capture 10 minutes later, call `JFR.dump` again with a different filename.

`maxage` and `maxsize` are **retention** policies. If an incident occurred 3 hours ago while `maxage=2h`, the older data has already been evicted; dumping now cannot recover it. Choose retention based on incident detection delay, response time, and disk capacity. Do not look only at `maxsize` and ignore that final dump files consume additional disk space.

If you need to change where the repository is stored, HotSpot supports dedicated JFR options, for example:

```bash
java -XX:StartFlightRecording=name=ring,settings=default,disk=true,maxage=2h,maxsize=256m -XX:FlightRecorderOptions=repository=/var/tmp/jfr-repository -jar application.jar
```

`repository` is where **temporary** chunks are held, not the `.jfr` output of `JFR.dump`. Create the directory and grant proper permissions to the process; verify options against your specific runtime.

## 7. Recipe C: Enabling a Recording on an Already-Running Production JVM

When a service is running without JFR or needs an additional time-boxed `profile` configuration:

### Step 1 — Identify the process and current recordings

```bash
jcmd -l
jcmd <PID> VM.version
jcmd <PID> JFR.check
```

If the JVM already has a background `ring` recording with suitable data, you can **dump that recording immediately**. You do not always need to create a new recording. If more events are needed for a specific investigation, create a short, distinctly named `profile` recording.

### Step 2 — Capture the phenomenon within a bounded interval

```bash
jcmd <PID> JFR.start name=incident settings=profile duration=120s filename=/var/log/app/incident.jfr
jcmd <PID> JFR.check name=incident
```

A new recording starts after `JFR.start`. Once 120 seconds of recording complete, the JVM stops it and writes the file. No restart is required. To check which event settings were applied:

```bash
jcmd <PID> JFR.check name=incident verbose=true
```

If `JFR.check` no longer shows `incident` after the duration has elapsed, **check the output file**, because an expired recording is no longer running.

### Step 3 — Option without `duration`

```bash
jcmd <PID> JFR.start name=onDemand settings=default disk=true maxage=1h maxsize=256m
jcmd <PID> JFR.check name=onDemand
```

The recording continues until a stop command is issued, the JVM exits, or another policy terminates it. You can capture a snapshot:

```bash
jcmd <PID> JFR.dump name=onDemand filename=/var/log/app/snapshot.jfr
```

And stop only when finished:

```bash
jcmd <PID> JFR.stop name=onDemand filename=/var/log/app/final.jfr
```

Always pass `name` so you do not affect other recordings. When aiming to keep the results, pass `filename` on `JFR.stop` and verify that the file is created. If no path is specified, depending on command/settings, data may be discarded. You can dump before stopping to guarantee an artifact already exists.

## 8. How Do `JFR.check`, `JFR.dump`, and `JFR.stop` Differ?

| Command | Purpose | Is the Recording Still Running Afterward? |
| --- | --- | --- |
| `jcmd <PID> JFR.check` | Displays running recordings; accepts optional `name`, `verbose=true` | Yes, unchanged |
| `jcmd <PID> JFR.dump name=... filename=...` | Exports a snapshot of currently available events to a file | **Yes**, the recording continues |
| `jcmd <PID> JFR.stop name=... filename=...` | Ends the recording and writes a file if requested | **No**, that recording is stopped |

A safe and repeatable sequence:

```bash
jcmd <PID> JFR.check
jcmd <PID> JFR.dump name=incident filename=/var/log/app/incident-before-stop.jfr
jcmd <PID> JFR.stop name=incident filename=/var/log/app/incident-final.jfr
```

Use `JFR.check` to verify the exact name. JFR commands can also operate with recording IDs; when multiple recordings exist, do not rely on auto-generated names without checking first.

On supported JVMs, `JFR.dump` also accepts `maxage=10m` or `begin`/`end` to filter the **exported** time window. These are options for the **dump command**, distinct from `maxage` at `JFR.start` (which limits data **retained in the repository**). If old data has already been evicted by retention, passing `JFR.dump maxage=...` will not bring it back.

## 9. Self-Contained Java 17+ Example for Both Methods

Create the file **`JfrCaptureDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.InputStreamReader;

public class JfrCaptureDemo {
    public static void main(String[] args) throws Exception {
        System.out.println("READY");
        BufferedReader input =
                new BufferedReader(new InputStreamReader(System.in));
        input.readLine(); // Keep the JVM alive until Enter is pressed.
        System.out.println("DONE");
    }
}
```

Compile:

```bash
javac --release 17 JfrCaptureDemo.java
```

This is a **standalone** program that runs on JDK 17+ and waits for input so you have time to run `jcmd`. When you press Enter **once**, the program itself prints these exact two lines in order:

```text
READY
DONE
```

### Trying the startup method

Terminal 1:

```bash
java -XX:StartFlightRecording=name=demoBoot,settings=default,dumponexit=true,filename=demo-boot.jfr JfrCaptureDemo
```

Wait for the `READY` line; press Enter so the program exits. Check the file in terminal 2:

```bash
jfr summary demo-boot.jfr
```

Additional JVM JFR status messages or `jfr summary` output may appear depending on version and command; they are **not** the two lines printed by the program's `System.out.println`.

### Trying the runtime method

Terminal 1:

```bash
java JfrCaptureDemo
```

Wait for `READY` and **do not press Enter yet**. Terminal 2:

```bash
jcmd -l
jcmd <PID> JFR.start name=demoLive settings=profile
jcmd <PID> JFR.check name=demoLive
jcmd <PID> JFR.dump name=demoLive filename=demo-live.jfr
jcmd <PID> JFR.stop name=demoLive filename=demo-final.jfr
```

Return to terminal 1 and press Enter. Inspect:

```bash
jfr summary demo-live.jfr
jfr summary demo-final.jfr
```

Because the example simply blocks waiting for input, the file may have **few CPU samples or allocation events**. The goal of the example is to test syntax and recording lifecycle; to practice profiling, run a workload with load, check event settings, and record for an adequate duration.

**Paths are critical:** `filename` files created via `jcmd` are written in the **target JVM's** filesystem, relative to the **JVM process's** working directory, not necessarily the directory of the terminal running `jcmd`. A container host and an app container may see different filesystems.

## 10. Reading and Validating the Captured JFR File

Given the resulting file `incident.jfr`:

```bash
jfr summary incident.jfr
jfr print --events jdk.ExecutionSample incident.jfr
jfr print --events jdk.GarbageCollection incident.jfr
```

- `jfr summary` displays the time span, event types, and event counts. Use it to verify **the file exists, is readable, and contains data** before drawing conclusions.
- `jfr print --events ...` filters events. Empty output is not necessarily an error: the event may be disabled, the workload may not have triggered it, or its threshold may not have been met.
- Use **JDK Mission Control (JMC)** to analyze timelines, threads, CPU, GC, allocations, and event correlations. Pick a JMC version compatible with the JDK/file format in use.

To avoid mixing up files, include the service name, timestamp, and PID in filenames, and record Java version, GC, workload, and the incident time window. When comparing recordings, use the same `.jfc` configuration and comparable duration and load; `settings=default` versus `settings=profile` can produce different event coverage.

## 11. Evidence-Driven Handling Scenarios

### A. Sudden spike in startup time

Enable `-XX:StartFlightRecording=...` **right at launch**, without setting `delay` if the problem lies in startup. Capture class loading, JIT warm-up, GC, and framework initialization phases. If you only run `JFR.start` after the health check passes, you have already missed what you needed to observe.

### B. P99 latency rises on a service that cannot be restarted

Run `jcmd <PID> JFR.start name=latency settings=profile duration=3m filename=/var/log/app/latency.jfr`. Make sure the incident is still occurring during the three-minute capture; save trace/request IDs and application metrics for correlation. If attach fails, document and fix the attach permissions/restrictions rather than assuming JFR is unsupported.

### C. Sporadic failure that is already over when the alert arrives

Use a **continuous recording** with `settings=default,disk=true,maxage=...` long enough to cover detection lag. Once an alert fires, run `JFR.dump` to retrieve the retained history. If no recording was active prior to the incident, `JFR.start` cannot "go back in time."

### D. Multiple recordings running, unsure which one to dump

Run `JFR.check` and inspect names and settings. If `ring` already has the needed events, dump `ring`. If only `profile` captures the desired events, start another distinctly named short recording; avoid accidentally stopping a background monitoring recording.

### E. File is created but small or lacks CPU samples

Check with `jfr summary`, `JFR.check verbose=true`, actual recording duration, actual load, and event settings. The recording might have run for only a few seconds or sampling might be insufficient. A small file does not by itself prove the JVM has no bottlenecks, and a CPU profile from an idle application cannot explain peak traffic.

## 12. Symptom-Based Troubleshooting

| Symptom | Common Cause | Check / Action |
| --- | --- | --- |
| Startup flag does not work | Flag placed after `-jar`, wrong comma syntax, launcher drops flag | Place `-XX:StartFlightRecording=...` before `-jar`; check Java command and JVM logs. |
| `jcmd -l` does not list the process | Different PID namespace, insufficient user permissions, tool missing in image | Run with compatible tools and permissions in the environment that sees the JVM PID. |
| `JFR.start` is rejected | Attach restrictions, `-XX:+DisableAttachMechanism`, security permissions, unsupported JVM | Check runtime/attach policy; use the startup flag on the next suitable deploy if attach is blocked. |
| `.jfr` file does not appear immediately after start | `filename` is the output when the recording finishes | Run `JFR.check`; use `JFR.dump` for a snapshot while running. |
| File ends up in the wrong directory | JVM working directory differs from `jcmd` shell | Use an absolute path **in the target JVM's filesystem**. |
| `JFR.dump` fails to write the file | Directory missing, permissions, or disk full | Check path and JVM user, repository disk space, and output space. |
| Dump lacks the older incident | Recording started too late or retention evicted chunks | Enable continuous earlier, increase `maxage`/`maxsize` sensibly. |
| File has very few events | `settings` lacks the events, high threshold, load too light | Check `JFR.check verbose=true` and `jfr summary`; tune `.jfc`. |
| Accidentally stopped recording with no file | Destination omitted, or checking wrong path | Run `JFR.dump` before stop; use `JFR.stop name=... filename=...`. |
| JVM killed without a dump | `dumponexit` only works when shutdown gets a chance to run | Dump proactively, use background recording, and establish disk retention monitoring. |
| `profile` impacts latency | Too many events/samples, running too long, or multiple recordings | Shorten duration, switch background to `default`, measure overhead under equivalent load. |
| Analysis tool cannot open the file | File still being written/incomplete or incompatible tool | Wait for dump completion, check `jfr summary`, use matching JFR/JMC versions. |

JFR typically has low overhead with standard configurations, but it is **not a fixed overhead**. Events with heavy stack traces, dense allocation sampling, or GC-root paths can add significant cost. In production, enable only the data needed to answer your question and bound both duration and retention.

## 13. Precautions in Containers and Production Environments

- **Permissions and PID namespace:** `jcmd` generally needs a sufficiently privileged user on the same host/namespace that can see the JVM process; you may need to run inside the container/app runtime. Use the target PID, not the host shell's PID.
- **Output path:** `filename=/some/path/file.jfr` resides in the JVM's filesystem, not necessarily where `jcmd` runs. The directory must exist and be writable by the JVM user.
- **Disk capacity:** account for temporary repository chunks, periodic dump files, concurrent recordings, and artifact cleanup policies. Avoid setting `maxage=0s/maxsize=0` for continuous recording without controlling data growth.
- **Sensitive data:** some events contain command lines/system properties, paths, thread names, and stack traces; redaction capabilities vary by JDK and settings. Control access to `.jfr` files and never post production recordings publicly.
- **Time alignment:** keep time zones, clocks, and timestamps consistent across application metrics, tracing, and recordings; analyzing the wrong incident window leads to wrong conclusions.
- **Different runtimes:** syntax and event schemas can change across JDKs/vendors; do not extrapolate from a local JDK if the target PID runs a different build.

## 14. Checklist Before Considering a JFR Capture Complete

- [ ] Identified the exact JVM PID, runtime/vendor/JDK version, and question to investigate.
- [ ] Chose `-XX:StartFlightRecording` if startup is needed, or `JFR.start` if the JVM is running and attach is allowed.
- [ ] Formatted options correctly: **commas** in the startup flag, **spaces** after `jcmd ... JFR.start`.
- [ ] Selected `settings=default` for background or `profile` for targeted short capture; confirmed the needed events are enabled.
- [ ] Configured `duration`, `delay`, `filename`, and `dumponexit` for the goal; understand the file may not exist while running.
- [ ] For continuous recording, used `disk=true` with `maxage`/`maxsize` and sufficient disk space.
- [ ] Verified with `JFR.check` and `JFR.check verbose=true` when needed; used unique recording names.
- [ ] Used `JFR.dump` for snapshots without stopping; used `JFR.stop name=... filename=...` when ending a session.
- [ ] Confirmed path, write permissions, and actual `.jfr` file location on the target process.
- [ ] Ran `jfr summary`, checked recorded time span and event counts; recorded workload/incident timestamps.
- [ ] Correlated JFR with GC logs, OS/container metrics, request traces, CPU/latency, and noted coverage limits.
- [ ] Documented artifacts, JFR settings, JDK, retention, and overhead so others can reproduce the investigation.

## 15. Official References for Further Lookup

1. Oracle Java 26 `jcmd` manual — `JFR.start`, `JFR.check`, `JFR.dump`, and `JFR.stop`: https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html
2. Oracle JDK 24 Troubleshooting Guide — using `-XX:StartFlightRecording` at startup and `jcmd` on a running process: https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshooting-guide.pdf
3. Oracle JDK 26 Troubleshooting Guide — examples of flight recordings on production runtimes: https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshooting-guide.pdf
4. OpenJDK `java` manual — `-XX:StartFlightRecording` options: https://github.com/openjdk/jdk/blob/master/src/java.base/share/man/java.md
5. Dev.java, Configuring the JDK Flight Recorder — delimiter differences, settings, recording options, and event settings: https://dev.java/learn/jvm/jfr/configure/
6. Oracle Java 26, Troubleshoot Performance Issues Using Flight Recorder: https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshoot-performance-issues-using-jfr.html
7. Java SE 26 API `jdk.jfr.Recording` — retention, lifecycle, and destination: https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/Recording.html

**Practical takeaway:** if you need startup, enable JFR at JVM launch; if investigating a running service, use `jcmd <PID> JFR.start`. Pick the right `settings`, retain enough data with `duration` or `maxage`/`maxsize`, use `JFR.dump` to grab a file while the recording keeps running, and verify with `jfr summary` before analyzing.
