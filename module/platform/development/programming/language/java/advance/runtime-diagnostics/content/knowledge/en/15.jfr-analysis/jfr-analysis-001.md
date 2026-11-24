# 15.1. JDK Mission Control is a separate tool for opening and analyzing recordings

## Objectives

After this lesson, you will be able to:

- Distinguish **JDK Flight Recorder (JFR)**, **`.jfr`** files, the **`jcmd`/`jfr`** command-line utilities, and the **JDK Mission Control (JMC)** graphical application.
- Explain why having a JDK and being able to create JFR recordings **does not mean** JMC is installed on the machine.
- Create a recording, transfer the file to an analysis machine, open it with JMC, and inspect events within the right time range.
- Use **Automated Analysis Results**, Memory, Code, Threads/Locks, I/O, and Events to find signals worth investigating, while recognizing the limitations of the collected data.
- Avoid drawing false conclusions from automated warnings, CPU samples, allocation statistics, event thresholds, or time windows that do not cover the incident.

**Environment:** Java 17+ is suitable for examples using the `jdk.jfr` API; menu names and JMC UI details may vary slightly depending on the release. JMC is a desktop application with a separate distribution and can run on a different machine from the one that generated the recording.

## 1. Clearly separate where data is recorded from where it is analyzed

**JDK Flight Recorder (JFR)** is a diagnostic/profiling event recording mechanism built into the JVM/JDK. Events can describe CPU sampling activity, garbage collection, allocations, threads, locks, I/O, the JVM environment, and application-defined events. JFR stores data along with timestamps, attributes, thread names, and stack traces **when permitted by the event type and configuration**.

**JDK Mission Control (JMC)** is a **graphical tool suite for analyzing** that data. JMC can connect to and observe a running JVM through the corresponding mechanisms, but opening an existing `.jfr` file is **offline analysis** and does not require the original process to keep running.

| Component | Main function | Key things to remember |
|---|---|---|
| **JFR in the JVM** | Emits and collects events from runtime activity | What gets collected depends on event settings, duration, and the JVM |
| **`.jfr` file** | Recording data in **binary** format | Not a text log, `.hprof` heap dump, or core dump |
| **`jcmd`** | Sends `JFR.start`, `JFR.check`, `JFR.dump`, `JFR.stop` commands to a running JVM | Command-line tool bundled with a matching JDK; requires attach/permissions for the JVM |
| **`jfr`** | Inspects an existing recording file via CLI (e.g., `summary`, `print`) | Useful when the machine has no graphical interface |
| **JMC** | Opens and analyzes recordings with timelines, tables, charts, and advisory rules | **Installed/run separately** if the JDK distribution does not bundle JMC; does not require the original JVM to open `.jfr` |

Basic flow:

```text
Java application + JVM (with JFR)
       |
       | start recording (CLI, JVM option, API, or JMC)
       v
   JFR events
       |
       | dump/stop -> save file
       v
  incident.jfr (binary file)
       |
       | copy to analysis machine if needed
       v
   JDK Mission Control
       |
       +-- Automated Analysis Results
       +-- Memory / Code / Threads / Locks / I/O / System
       +-- Event Browser, Timeline, Stack Trace
       |
       v
   Hypothesis -> cross-check code, logs, metrics -> verify
```

**Two common misconceptions:**

1. Being able to run `java -version` or the `jfr` command **does not prove JMC is installed**. JMC must be downloaded/installed from a separate distribution matching your operating system; you generally cannot assume a `jmc` command is on `PATH`.
2. Reading `incident.jfr` with JMC **does not require** opening JMX/management ports to production: you only need a valid recording file. Live connections are a separate workflow with their own access requirements.

## 2. Preparing JDK Mission Control properly

### 2.1. Obtaining the JMC application

Find a JMC release matching your operating system and the Java runtime used to run the application from official sources:

- The [Oracle JDK Mission Control](https://www.oracle.com/java/technologies/jdk-mission-control.html) page provides downloads, guides, and support information.
- The [OpenJDK JMC](https://github.com/openjdk/jmc) project contains the source code and information about distributions/projects.

JMC has a desktop UI built on Eclipse RCP. Installation usually consists of downloading the package for your OS, extracting/installing the application, and launching the bundled executable. **Do not blindly apply installation commands from one JMC release to every JDK/OS**: check the documentation for the specific JMC version you chose.

You can generate a recording on a Linux/server machine and open it in JMC running on Windows/macOS/Linux on a developer workstation. There is no need to install JMC on the server just to analyze files offline.

### 2.2. Verify the three environment layers

On a machine with a JDK:

```bash
java -version
jcmd -h
jfr help
```

These commands verify the **Java/JFR CLI**, not the command to launch JMC. After installing, open **JDK Mission Control** from the distribution's executable/menu. A `.jfr` file can come from a different Java/JDK version than JMC; format compatibility, events, and display capabilities depend on the tool version. When a file fails to open, check the JMC version, the JDK version that produced the recording, and the file status before assuming the file is corrupt.

### 2.3. How to open a file

1. Launch the **JDK Mission Control** application.
2. In the application menu, select **File → Open File...** (the exact label may vary slightly by version), choose `incident.jfr`; or open the recording from the list/file browser in JMC.
3. Wait for JMC to read/index the recording and display the analysis pages. In current JMC versions, the starting point is typically **Automated Analysis Results**.
4. Confirm that the recording matches the right **application, JVM, and time range** before reading warnings or charts.

Do not use a text editor to inspect binary `.jfr` data and conclude the file is empty when you see strange characters. If JMC is not installed yet, `jfr summary` or `jfr print` helps inspect the file via CLI.

## 3. Creating a JFR recording to open in JMC

There are several ways to produce a file. Choose the path that fits the JVM lifecycle and your diagnostic goal.

### 3.1. Starting when the application launches

Example with a Java application packaged as an executable JAR:

```bash
java -XX:StartFlightRecording=name=Startup,duration=60s,settings=profile,filename=startup.jfr -jar app.jar
```

When the configured `duration` ends, JFR writes `startup.jfr` to the requested path. This is a fixed-duration recording; it is convenient when you need to measure **startup** or reproduce a scenario in a controlled environment. Replace `app.jar` and the duration with your actual application and case.

**`settings=default` and `settings=profile` differ:** the `profile` preset typically collects additional events for profiling, at the cost of higher overhead and file size. Do not treat `profile` as the optimal default for every production workload.

### 3.2. Recording on a running JVM with jcmd

First, identify the PID of the target JVM:

```bash
jcmd -l
```

In the following commands, **replace `<PID>` with the actual PID number**; the example command lines are not meant to be run literally with angle brackets:

```bash
jcmd <PID> JFR.start name=Incident settings=profile duration=2m filename=incident.jfr
jcmd <PID> JFR.check
```

When the recording finishes after 2 minutes, JFR can write `incident.jfr`. To capture a snapshot of data **while the recording is still running**:

```bash
jcmd <PID> JFR.dump name=Incident filename=incident-now.jfr
```

**`JFR.dump` does not stop a running recording.** For a continuous recording, you can choose when to dump or call `JFR.stop name=Incident filename=incident-final.jfr` to finish and save it. Only run `stop` when you actually want to stop; a recording with a `duration` usually finishes automatically when it expires.

`jcmd` must be able to access the target JVM, typically on the same host with appropriate user permissions. Containers, disabled JVM attach, or locked-down environments can prevent the command from connecting. Opening a JMX port is not required for the local `jcmd` workflow.

### 3.3. Creating a recording from JMC when connected to a JVM

JMC also includes a **JVM Browser** to discover manageable JVMs. Once you find the target JVM:

1. Right-click the JVM in **JVM Browser** and select **Start Flight Recording...**.
2. Choose a **fixed-duration** or **continuous** recording, the name/destination file, and a template.
3. Choose event types, thresholds, and stack trace collection according to your needs.
4. Start the recording, then dump it or wait for the fixed-duration recording to complete.
5. Open the resulting recording in JMC to analyze it.

This path requires JMC to connect to the target JVM using a supported environment and permissions; if you already have a `.jfr` file from production, **skip the connection step** and open the file offline as described in section 2.3.

## 4. Java hands-on: create a .jfr file yourself without a server or JMX

Let's create a **custom JFR event** containing a work step name, start timestamp, duration, and stack trace. The standalone example runs on **Java 17+** and writes `mission-control-demo.jfr` by itself; afterward, open the file in JMC.

Create the file **`MissionControlDemo.java`**:

```java
import java.nio.file.Path;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;

public class MissionControlDemo {
    @Name("demo.WorkUnit")
    @Label("Demo work unit")
    static class WorkUnit extends Event {
        @Label("Task")
        String task;
    }

    public static void main(String[] args) throws Exception {
        Path output = Path.of("mission-control-demo.jfr");

        try (Recording recording = new Recording()) {
            recording.enable(WorkUnit.class).withStackTrace();
            recording.start();

            for (int i = 1; i <= 3; i++) {
                WorkUnit event = new WorkUnit();
                event.task = "batch-" + i;
                event.begin();
                Thread.sleep(30);
                event.end();
                event.commit();
            }

            recording.stop();
            recording.dump(output);
        }

        System.out.println("Created: " + output.getFileName());
    }
}
```

Compile and run in the directory containing the source file:

```bash
javac MissionControlDemo.java
java MissionControlDemo
jfr summary mission-control-demo.jfr
jfr print --events demo.WorkUnit mission-control-demo.jfr
```

**Exact stdout line printed by the program:**

```text
Created: mission-control-demo.jfr
```

In the `jfr print` output, you should see **three events** of type `demo.WorkUnit`, with `task = "batch-1"`, `"batch-2"`, `"batch-3"`. Values such as `startTime`, `duration` (usually at least ~30 ms due to `sleep`), `javaThreadId`, and line numbers in the stack trace **vary across runs and JDKs**, so they are not shown as fixed stdout. This example was verified with OpenJDK 24: it compiled successfully, created the `.jfr` file, and `jfr print` read all three events and stack traces.

**Code explanation:**

- `@Name("demo.WorkUnit")` sets the event type name for filtering in the CLI/JMC; `@Label` sets a human-readable label.
- `Recording` creates a JFR recording session within the JVM itself. `enable(WorkUnit.class).withStackTrace()` enables the event and captures stack traces for this type.
- `event.begin()` and `event.end()` measure the time span; `commit()` emits the event into the recording.
- `recording.stop()` followed by `dump(Path)` saves the recording; the `try` block closes the resource.
- The file may contain **other JVM events** in addition to the three custom events, depending on the recording and JDK. Use the `demo.WorkUnit` filter to isolate them.
- This file provides data to verify **opening and analyzing a recording**; it is not meant to reproduce a real CPU bottleneck, memory leak, or lock contention.

### Opening the example in JMC

1. Run the program and verify that `mission-control-demo.jfr` exists.
2. In JMC, select **File → Open File...** and point to that file.
3. Locate **Events / Event Browser** (the UI name/path varies by version) and filter for type `demo.WorkUnit`.
4. Inspect the three events, the `task` value, duration, and stack trace; select each event to view its details.
5. Compare the event count in JMC with the command `jfr print --events demo.WorkUnit mission-control-demo.jfr`.

This is an end-to-end check: **Java code → JFR binary file → JMC opens file → events visible**. No live connection to the finished JVM is needed.

## 5. Reading the JMC UI by diagnostic question

JMC versions may rename pages or adjust layouts, but the analysis flow remains fairly consistent: start at **Automated Analysis Results**, filter the time range, then drill down into specialized pages and specific events.

### 5.1. Automated Analysis Results: hints, not conclusions

JMC applies **analysis rules** to the events actually present in the file, highlighting notable findings via scores or warnings. Some versions show yellow/red indicators for priority findings and provide a toggle to view OK results as well.

How to use it:

1. Note the signal flagged by the rule: symptom name, timestamp, severity, and related data.
2. Click the result to jump to the chart/events explaining the warning.
3. Narrow down the incident time window and cross-check logs, metrics, and request traces.
4. Check whether the recording contains the **necessary events** before concluding that "no warnings means everything is normal."

**A rule score does not prove root cause.** "High allocation," "long GC pause," or "lock contention" are indicators that must be checked against workload context, latency targets, and causal relationships.

### 5.2. Selecting the right time range before reading charts

JFR is a collection of **timestamped** events; a single recording can include startup, warm-up, normal operation, and the incident window. Select the incident window in the timeline/range navigator and ensure that tables and charts reflect that scope.

For example, suppose an application has a latency spike during minutes 02:10–02:20 of a 10-minute recording:

- Focus on the spike window and compare it against a normal window immediately before it.
- If a GC pause coincides with the latency spike, that is a **temporal correlation**; inspect pause duration, thread behavior, and request data to verify causality.
- If the recording started **after** the incident or ended before it, JMC cannot recover events that were never recorded.

When reading events, check timestamps, UI/machine timezones, and coverage windows to avoid misaligning timestamps with application logs.

### 5.3. Which page fits which problem?

| Suspicion | Typical place to inspect in JMC | Data to inspect and limitations |
|---|---|---|
| **High CPU** | Code / Method Profiling / Hot Methods | Execution samples, stack traces, thread context; sample share is **not** exact wall-clock time per call |
| **Allocation pressure** | Memory / Allocation / TLAB | Allocation sites, classes, threads, stacks, allocation rate; **sampling** events do not mean every object was recorded |
| **GC pauses and heap behavior** | Memory / Garbage Collections / JVM Internals | GC timestamps and durations, heap before/after, frequency; does not by itself prove a leak |
| **Lock contention** | Threads / Locks / Java Monitor | Blocked/wait events and stacks; event thresholds may omit short waits |
| **I/O latency** | I/O / File / Socket | Event duration, thread, address/target, and stack when available; check that events are enabled with an appropriate threshold |
| **Thread behavior** | Threads / Event Browser | Active/waiting/running state based on recorded events; do not assume it is a complete snapshot of every thread |
| **Abnormal environment** | System / Environment / JVM Information | JDK, OS, runtime flags, CPU/cgroup if supported by events |
| **Custom events** | Events / Event Browser | Filter by type, attributes, and thread; results depend on events actually emitted by the application |

Not every recording contains all views or stacks. If an event type is missing or disabled, the corresponding page may be empty; do not equate "no data" with "no problem."

## 6. Repeatable diagnostic workflows

### 6.1. Analyzing a latency spike

**Symptom:** p99 latency spikes noticeably for about a minute.

1. Identify the spike window in **application metrics/logs** and verify that the recording actually covers that interval.
2. In JMC, set the exact **time range**, and check Automated Analysis Results for initial hypotheses.
3. Check **I/O** for slow socket/file operations; check **Threads/Locks** for monitor contention; check **Memory/GC** for overlapping pauses; check **Code** for prominent method execution samples.
4. Open representative events and inspect timestamps, durations, threads, stack traces, and related methods/classes.
5. Correlate with request IDs, downstream response times, database metrics, and thread dumps/OS CPU if needed.

For example, a 400 ms socket read on a slow request indicates waiting on I/O; you cannot attribute that 400 ms to "Java CPU spent 400 ms." CPU sampling may show very few samples for threads waiting on I/O even when latency is high.

### 6.2. Analyzing hot CPU

**Symptom:** process CPU rises and throughput drops.

1. Record JFR under load with execution sampling events enabled (usually requiring an appropriate profiling configuration).
2. In **Code/Method Profiling**, inspect the stacks/methods appearing most frequently in samples.
3. Cross-check threads, event time range, JVM GC/compiler activity, and OS-level CPU.
4. Inspect the code and verify with a benchmark, profiler, or trace at the suspected location.

**Note:** Sampling has statistical bias and depends on sampling period, safepoints/configuration, and stack depth. "25% of samples" must not be stated as "the method ran for exactly 25% of total wall-clock time." Short or infrequently sampled methods can still matter for individual requests.

### 6.3. Analyzing memory and GC

**Symptom:** frequent GC or steadily rising heap usage.

1. Use **Memory** to inspect heap usage, allocation rate, and GC pauses/events during the incident window.
2. Check the object types and stacks of collected allocation events.
3. Compare multiple intervals of equivalent workload; watch out for warm-up and legitimate caches.
4. When suspecting a real leak, use an appropriate heap dump/histogram/retained-object analysis to identify **live objects**, because JFR allocation samples are not proof of **retained heap**.

A critical limitation: a class with high allocation **does not necessarily** occupy much heap after GC; creating and reclaiming many short-lived objects is normal.

## 7. Why might JMC not show what you expect?

A JFR file is produced from **enabled events**, a specific duration, and specific thresholds. Assess recording quality before diagnosing the application.

| Symptom | Possible cause | How to check |
|---|---|---|
| JMC opens the file but there are no CPU method samples | Sampling event disabled, duration too short, workload hadn't started | `jfr summary`, event settings, re-record with appropriate profiling settings |
| No lock contention visible even though requests are slow | Issue caused by I/O, or monitor event threshold is too high | Check I/O and thresholds/event counts; supplement with thread dumps |
| No stack traces visible | Stack trace disabled for the event type, global stack trace setting off, or stack depth limit | Check event configuration; capture another recording if needed |
| A few allocation events represent a huge number of bytes | Sampling/estimation event, does not list every object | Distinguish sample count, estimated allocated bytes, and retained heap |
| Automated Analysis Results shows no warnings | Rules saw no issues given their data/thresholds, or recording is insufficient | Inspect events directly and cross-check metrics/logs |
| JMC shows warnings but the app still meets its SLO | Generic rule thresholds do not match actual requirements | Check workload, SLA/SLO, severity/frequency, and real impact |
| JMC cannot open or does not understand new events | Incomplete recording, version/format or events unsupported by the JMC version | `jfr summary`, check JMC/JDK versions and file integrity |
| JMC does not list the production JVM | Live connection, JMX, permissions, or network issue | If you only need analysis, fetch the `.jfr` file and open it offline |

### Choosing the right recording configuration

Two common JDK presets are **`default.jfc`** and **`profile.jfc`**; templates determine which events are enabled, their thresholds, and stack traces. `profile` generally captures more data at higher cost. If you need custom events, enable the corresponding event types. If you need to catch a rare incident, configure **retention time, size limits, and recording/dump intervals** so the file covers the target phase.

JFR aims for low overhead under standard settings, which **does not mean zero overhead**. Enabling every event, lowering thresholds too far, enabling stack traces on extremely high-frequency events, or capturing heap roots can increase CPU, I/O, and storage costs. Test the impact when changing production configurations.

## 8. Combining JMC with other tools

- **`jfr summary incident.jfr`:** verifies the file is readable and shows which event types are in the recording along with their counts and total sizes. This is a quick step before opening the GUI.
- **`jfr print --events jdk.GarbageCollection incident.jfr`:** prints a specific event type as text if the recording contains it; available event types depend on the JDK version and configuration.
- **JMC:** explores timelines, tables, event filters, charts, stacks, and automated analysis; convenient for spotting patterns over time.
- **Application logs/metrics/traces:** explain how symptoms affect real requests, transaction IDs, and downstream calls; JMC does not automatically replace application correlation IDs.
- **Thread dumps, heap dumps, OS/container metrics:** supplement JFR when you need exact snapshots of locks/threads, retained heap, RSS/cgroup, or issues outside event coverage.

Do not conflate different file types: **`.jfr`** stores diagnostic events over time; **`.hprof`** is a heap dump, typically analyzed with dedicated heap tools; a **text thread dump** is a snapshot of thread states. Each serves a different question.

Recordings may contain sensitive information such as class/method names, hostnames, paths, thread names, endpoints, or **fields placed in custom events by the application**. When transferring files to an analysis environment, follow your application's access and data-retention policies.

## 9. Common mistakes

1. **“JFR is already in the JDK, so JMC must be installed with it.”** False: JFR is the recording mechanism in the JDK/JVM, whereas JMC has its own application package. Verify what tools are actually installed.
2. **“Opening a `.jfr` file requires the server to be alive and JMX open.”** False: JMC can read a complete saved recording offline.
3. **“If the file opens, all necessary events are present.”** False: a recording only contains events that were configured, within the retained window, and passed thresholds/sampling.
4. **“A red warning in JMC means the root cause is found.”** False: it is a rule-based finding that must be checked against events, timestamps, impact, and actual code.
5. **“No warnings means the JVM has no problems.”** False: missing events, a recording from the wrong window, or rules not covering the issue can hide signals.
6. **“High allocation means a memory leak.”** False: allocation rate is not the same as objects remaining alive after GC.
7. **“A method with many samples definitely takes that proportion of wall time.”** False: sampling does not directly measure the duration of every call.
8. **“JFR and JMC have the same job.”** False: JFR primarily **collects data**, while JMC primarily **displays and analyzes** that data.
9. **“If I have a production issue, I must open a live connection.”** False: transferring the file to a secure diagnostic machine is usually sufficient for an offline workflow.
10. **“`JFR.dump` stops the recording.”** False: dump writes a snapshot file while the recording keeps running; to stop it, use `JFR.stop` or let the duration expire.

## 10. Checklist before drawing conclusions from JMC

1. Confirm **JMC is installed independently** and its version can read the recording file.
2. Confirm the file matches the right JVM, PID/application, JDK, and **time range**; run `jfr summary` if needed.
3. Check whether key events **were enabled**, along with their thresholds, stack traces, and retention period.
4. Start with **Automated Analysis Results** for orientation, then open **events/stacks/timeline** for evidence.
5. Distinguish **samples**, **duration events**, **instant events**, **counts**, and **estimated allocation**.
6. Cross-check with logs, traces, business metrics, thread/heap dumps, or OS metrics depending on the nature of the incident.
7. Record hypotheses and verification steps; do not call a generic warning the root cause without verification.

### Self-check

- A JVM on a server runs JFR, but JMC is not installed on the server. How can you analyze the recording on your laptop?
- Why can a `.jfr` file still be opened after the JVM has shut down?
- Why might a CPU profiling page in JMC be empty even though the application was active?
- Why does the number of allocation samples not equal the number of objects created?
- Why should a GC/lock warning in Automated Analysis Results be cross-checked with the application before concluding?
- In the `MissionControlDemo` example, at which step is each custom event emitted and where do you inspect them?

## Official documentation

- [Oracle JDK Mission Control](https://www.oracle.com/java/technologies/jdk-mission-control.html): application downloads, description of JMC's role, and documentation.
- [JDK Mission Control User Guide — Flight Recorder](https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/using-jdk-flight-recorder.html): creating/opening recordings, Automated Analysis Results, and analysis pages.
- [Java SE 21 — `jcmd`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `JFR.start`, `JFR.check`, `JFR.dump`, `JFR.stop`.
- [OpenJDK JMC](https://github.com/openjdk/jmc): open-source project for the JDK Mission Control tool.
- [Java SE 21 — `jdk.jfr` package](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html): APIs for recordings and custom events.
