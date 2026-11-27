# Packaging an Application and Observing It with JFR

A program that runs fine on a developer workstation may not behave identically once packaged and deployed. When an application runs from a JAR or custom runtime image, it uses the actual classpath/module path, JVM flags, libraries, and environment far closer to real operations. That is also the right moment to capture Java Flight Recorder (JFR) data to observe CPU, allocations, garbage collection, threads, locks, and I/O.

JFR is a runtime event recording system built into the HotSpot JVM and available in JDK 17. A recording can start at application launch or be attached to a running JVM via `jcmd`. The resulting `.jfr` file can then be analyzed with JDK Mission Control (JMC) or the `jfr` command-line tool.

This hands-on lab walks through the entire lifecycle: preparing artifacts, packaging a JAR, running the packaged artifact, enabling JFR, collecting a recording, analyzing the data, and formulating optimization hypotheses. The goal is to understand the workflow of observing a packaged application, not merely running a single command to dump a recording file.

## 1. What Does JFR Observe?

Java Flight Recorder records timestamped events across the JVM and application. Depending on configuration, a recording can capture:

- **CPU and execution:** thread execution stack samples, JIT compiler activity, and execution timing.
- **Memory:** heap usage, allocation samples, object statistics, and garbage collections.
- **Threads and locks:** thread states, monitor contention, thread parks, and wait durations.
- **I/O:** file reads/writes, socket reads/writes, and I/O wait times.
- **Runtime:** class loading, exceptions, safepoints, JVM flags, and environment details.

JFR is especially effective for diagnosing latency spikes, high CPU usage, excessive allocations, GC pauses, or lock contention. Recordings preserve the surrounding context when an event occurred, enabling post-incident analysis after the issue has passed.

JFR has low overhead across many workloads and is designed for production use, though overhead is never zero. Data volume and runtime cost depend on the template, event settings, stack traces, recording duration, and workload. Choose settings aligned with your observation goal.

### 1.1. JFR, JMC, and the jfr Command

| Component | Role |
| --- | --- |
| JFR in the JVM | Captures runtime events and writes recordings |
| `jcmd` | Starts, inspects, dumps, and stops recordings on a running JVM |
| `jfr` | Reads, summarizes, filters, and exports events from `.jfr` files |
| JDK Mission Control (JMC) | Graphical tool for inspecting charts, events, stack traces, and automated analysis |

`jfr` resides in the JDK `bin` directory. JMC is a separate tool not bundled with a standard JDK installation; install it separately to visualize recordings.

## 2. Preparing the Application Before Packaging

For a recording to be meaningful, establish how the application will be packaged and launched:

1. Select JDK 17 as both the build toolchain and target runtime.
2. Identify the application entry point.
3. Identify required libraries and resources to include in or alongside the artifact.
4. Choose the execution mode: executable JAR, classpath, module path, or custom runtime image.
5. Prepare a reproducible workload so the recording contains representative data to analyze.

JFR observes the JVM running the application. Launching a class directly inside an IDE can cause recordings to reflect IDE classpaths, agents, and flags rather than the deployed artifact. Therefore, run the actual packaged artifact in this lab.

### 2.1. Example Project Structure

A simple Java project might have this layout:

~~~text
orders-app/
├── src/
│   └── com/example/orders/
│       └── OrdersApp.java
├── build/
│   └── classes/
└── recordings/
~~~

`build/classes` holds compiled bytecode; `recordings` is a dedicated directory for `.jfr` files. In Maven or Gradle projects, use the JAR or distribution produced by the build tool. The `jar` commands below illustrate basic packaging and do not replace build-tool dependency management.

### 2.2. Sample Application Code to Observe

The example below simulates a service accepting work, allocating objects, computing values, and sleeping briefly between batches. It generates enough activity to observe CPU sampling, allocations, threads, and runtime events:

~~~java
package com.example.orders;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

public final class OrdersApp {
    private static final AtomicLong completed = new AtomicLong();
    private static volatile long checksum;

    private OrdersApp() {
    }

    public static void main(String[] args) throws InterruptedException {
        int workers = Math.max(2,
                Runtime.getRuntime().availableProcessors() / 2);
        ExecutorService executor = Executors.newFixedThreadPool(workers);

        for (int i = 0; i < workers; i++) {
            executor.submit(OrdersApp::processOrders);
        }

        long end = System.nanoTime() + TimeUnit.MINUTES.toNanos(4);
        while (System.nanoTime() < end) {
            Thread.sleep(1000);
            System.out.printf("completed=%d checksum=%d%n",
                    completed.get(), checksum);
        }

        executor.shutdown();
        if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
            executor.shutdownNow();
        }
    }

    private static void processOrders() {
        while (!Thread.currentThread().isInterrupted()) {
            List<byte[]> payloads = new ArrayList<>();
            long local = 0;

            for (int i = 0; i < 40; i++) {
                payloads.add(new byte[16 * 1024]);
                local += calculate(i);
            }

            checksum = checksum ^ local;
            completed.incrementAndGet();

            try {
                Thread.sleep(10);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
        }
    }

    private static long calculate(int seed) {
        long value = seed + 1;
        for (int i = 0; i < 20_000; i++) {
            value = (value * 31 + i) ^ (value >>> 3);
        }
        return value;
    }
}
~~~

This is an illustrative workload, not a benchmark. The worker count depends on the processors visible to the JVM; output and data volume will vary across machines. When practicing, keep workload and JVM configuration identical across runs for valid comparisons.

## 3. Compiling and Packaging as an Executable JAR

A JAR is an archive format containing classes and resources. An executable JAR declares a `Main-Class` attribute in its manifest so the launcher knows which class to start.

Create output directories:

~~~bash
mkdir -p build/classes
mkdir -p recordings
~~~

Compile with JDK 17:

~~~bash
javac --release 17 -d build/classes src/com/example/orders/OrdersApp.java
~~~

Create the executable JAR:

~~~bash
jar --create \
    --file build/orders-app.jar \
    --main-class com.example.orders.OrdersApp \
    -C build/classes .
~~~

`--main-class` writes the entry point into the manifest. You can inspect the archive contents:

~~~bash
jar --list --file build/orders-app.jar
~~~

For modular JARs, inspect the module descriptor with the appropriate flag. For non-modular JARs, this step is unnecessary to run an executable JAR.

### 3.1. Running the Packaged JAR

~~~bash
java -jar build/orders-app.jar
~~~

If the application starts and prints completed work counts, the artifact has a valid entry point.

### 3.2. Standard JARs Do Not Bundle External Dependencies

A JAR built with `jar` packages only the specified classes and resources. It does not automatically bundle external dependencies into the archive.

If an application uses external libraries, you can:

- Use an executable/fat JAR built by a build tool or packaging plugin.
- Distribute a `lib` directory and launch via the classpath.
- Configure a manifest `Class-Path` matching the distribution layout.
- Use the module path if the application is modular.

Example running with libraries in a `lib` directory:

~~~bash
java -cp "build/orders-app.jar:lib/*" com.example.orders.OrdersApp
~~~

On Windows, the classpath separator is a semicolon:

~~~powershell
java -cp "build/orders-app.jar;lib/*" com.example.orders.OrdersApp
~~~

When `-jar` is used, the launcher ignores external classpaths specified via `-cp`/`-classpath`; if an executable JAR has dependencies, bundle them properly or declare `Class-Path` in the manifest.

## 4. Running the Packaged Application with JFR

JFR can be started at JVM launch using `-XX:StartFlightRecording`. JVM options must precede `-jar`, the main class name, or the module entry point.

Example recording a three-minute profile:

~~~bash
java -XX:StartFlightRecording=name=orders-profile,settings=profile,duration=3m,filename=recordings/orders-profile.jfr -jar build/orders-app.jar
~~~

Parameters:

| Parameter | Meaning |
| --- | --- |
| `name=orders-profile` | Recording name for management commands |
| `settings=profile` | Selects the higher-detail profiling template |
| `duration=3m` | Records for three minutes then stops |
| `filename=...` | Output JFR file path written when the recording ends |

Create the target directory beforehand and verify the JVM user has write permission. When the duration elapses, JFR writes the recording to the specified file. Add `dumponexit=true` if you want the recording saved when the JVM shuts down before the duration expires.

Example:

~~~bash
java -XX:StartFlightRecording=name=orders-profile,settings=profile,duration=3m,filename=recordings/orders-profile.jfr,dumponexit=true -jar build/orders-app.jar
~~~

`dumponexit` writes the dump on normal JVM shutdown. Do not treat it as a guarantee that the file is always written after power loss, `kill -9`, or severe crashes.

### 4.1. Capturing a Recording on a Running Application

You do not need to restart an application to capture a short recording. Use `jcmd` to attach to the running JVM:

~~~bash
jcmd -l
~~~

Identify the PID of `OrdersApp`, then run:

~~~bash
jcmd 24680 JFR.start name=orders-profile settings=profile duration=3m filename=recordings/orders-profile.jfr
~~~

Inspect active recordings:

~~~bash
jcmd 24680 JFR.check
~~~

To grab an immediate snapshot while keeping the recording active:

~~~bash
jcmd 24680 JFR.dump name=orders-profile filename=recordings/orders-snapshot.jfr
~~~

`JFR.dump` exports current data to a file while the recording keeps running. To stop the recording, run:

~~~bash
jcmd 24680 JFR.stop name=orders-profile filename=recordings/orders-profile-final.jfr
~~~

If you call `JFR.stop` without specifying an output filename, recorded data can be discarded. Check `help JFR.start`, `help JFR.dump`, and `help JFR.stop` on the target JVM for full parameters and behavior.

`jcmd` must run on the same host as the JVM under a compatible effective user/group. Inside containers, run the tool where it can access the target PID namespace and attach endpoint.

## 5. Choosing Recording Settings: default or profile?

JDK 17 ships with two built-in templates:

| Template | Goal | When to use |
| --- | --- | --- |
| `default.jfc` | Useful diagnostics with low overhead | Continuous recording, long-term observation, or production |
| `profile.jfc` | Captures more events and finer detail | Short-term profiling, investigating a specific symptom |

Templates live in `JAVA_HOME/lib/jfr`. If `settings` is omitted, JFR uses `default.jfc`.

`default` fits continuous recording and generally incurs very low overhead. However, it omits certain events, such as full heap statistics or allocation profiling. `profile` collects richer detail, though overhead and file size can be higher.

A practical approach:

1. Keep a `default` recording active if continuous runtime context is needed.
2. When symptoms appear, start a short `profile` recording.
3. Correlate the recording with metrics and logs from the same window.
4. Enable custom events only after confirming default data is insufficient.

Avoid running long-term `profile` recordings merely to collect extra data. Choosing events based on an investigative question keeps overhead low and analysis focused.

## 6. Continuous Recordings and Disk Limits

For long-running services, you can start a continuous recording at launch. JFR retains the most recent window of data bounded by age or size so recent history can be dumped during an incident.

Example:

~~~bash
java -XX:StartFlightRecording=name=orders-continuous,settings=default,disk=true,maxage=6h,maxsize=512m -XX:FlightRecorderOptions=repository=/var/tmp/orders-jfr -jar build/orders-app.jar
~~~

In this configuration:

- `settings=default` selects the lightweight template for continuous recording.
- `disk=true` enables writing chunks to a disk repository.
- `maxage=6h` bounds retained data by age.
- `maxsize=512m` bounds retained data size on disk.
- `repository=...` sets the directory for temporary recording chunks.

In Java 17, the `disk` parameter of `StartFlightRecording` defaults to `false`; to use a disk repository for continuous recording, explicitly set `disk=true`. `maxage` and `maxsize` only take effect when disk recording is enabled.

Chunks in the repository are temporary buffers. To preserve incident evidence, dump the recording to a `.jfr` file in a separate location:

~~~bash
jcmd 24680 JFR.dump name=orders-continuous filename=/var/tmp/orders-incident.jfr
~~~

The recording keeps running after the dump. You can dump again whenever a fresh snapshot is needed. Manage permissions, disk space, and retention for both the repository and exported recording files.

### 6.1. Continuous Recordings Are Not Infinite Logs

A JFR continuous recording acts as a rolling window of recent events. Once `maxage` or `maxsize` is reached, older chunks are evicted. If an incident happens and is not dumped before rotation evicts it, that context is lost.

Production setups should therefore dump on incident detection or trigger dumps automatically on appropriate thresholds. Never set unbounded limits when repository disk capacity is finite.

## 7. Analyzing Recordings with the jfr Command

Once you have a `.jfr` file, you can begin inspection from the terminal without a GUI.

### 7.1. Viewing the Summary

~~~bash
jfr summary recordings/orders-profile.jfr
~~~

The summary displays recording metadata, time span, event counts by type, and byte sizes. This is the first step to confirm the file contains data and see which events dominate volume.

### 7.2. Printing Events of Interest

For example, print only CPU execution samples and garbage collection events:

~~~bash
jfr print --events jdk.ExecutionSample,jdk.GarbageCollection recordings/orders-profile.jfr
~~~

Filter by category:

~~~bash
jfr print --categories GC recordings/orders-profile.jfr
~~~

Export as JSON for script processing:

~~~bash
jfr print --json --events jdk.ExecutionSample recordings/orders-profile.jfr
~~~

Avoid dumping every event of a large recording to the terminal if you only need one subset. Use `--events`, `--categories`, and `--stack-depth` to constrain output.

### 7.3. Inspecting Event Metadata

~~~bash
jfr metadata recordings/orders-profile.jfr
~~~

Metadata shows the event types, categories, and field schemas present in the recording. This helps identify which events were captured and which field names are available for analysis tools.

### 7.4. Checking Tool Version and Help

~~~bash
jfr --version
jfr --help
jfr --help print
~~~

Subcommands and flags depend on the JDK version shipping the tool. For Java 17 recordings, prefer `jfr` from JDK 17 or a compatible release, then open in JMC for visual exploration.

## 8. Analyzing Recordings with JDK Mission Control

JMC offers a rich UI organized by subsystem. Open the `.jfr` file in JMC, then review the Automated Analysis Results page and detailed views.

Key views:

| View | Questions to answer |
| --- | --- |
| Overview / Automated Analysis | What prominent anomalies stand out in the recording? |
| Code | Which packages, classes, or methods consume the most CPU? |
| Memory | How does heap usage fluctuate, where do allocations come from, and how frequent is GC? |
| Garbage Collections | Which GCs occurred, how long were pauses, and what were pre/post-GC heap sizes? |
| Threads | Which threads are most active, waiting, or blocked? |
| Locks | Is there monitor contention or prolonged lock waiting? |
| I/O | Are file or socket read/write durations high? |
| Environment | How do CPU, memory, OS, and other processes affect behavior? |

Automated Analysis Results is a starting point to pinpoint areas for deeper inspection. Colored warnings are investigative leads, not definitive root-cause conclusions.

### 8.1. Finding CPU Hot Spots

In the Code or Threads views:

1. Inspect CPU usage and execution samples during high-latency windows.
2. Rank the most frequently sampled stack traces or methods.
3. Distinguish application code from library internals.
4. Expand stack traces to trace call paths from entry points.
5. Correlate with endpoints, request types, or active workloads.

Execution samples are statistical sampling data, not exact execution timers for every method. Frequently sampled methods warrant investigation, verified against workload and source code.

### 8.2. Finding Allocations and GC Pressure

In Memory and Garbage Collections views:

- Observe heap usage over time.
- Check GC event counts and pause durations.
- Inspect allocation samples or allocations by class if enabled in the template.
- Identify classes or call sites allocating heavily.
- Distinguish short-lived temporary allocations from long-lived retained objects.

A sawtooth heap pattern dropping after GC is normal. An upward-trending post-GC heap across many cycles can suggest retained objects, though a single short recording is rarely sufficient proof of a memory leak.

If allocation events are missing from a `default` recording, capture a short `profile` recording or enable specific allocation events. Never conclude zero allocations occurred simply because the active template did not collect that event.

### 8.3. Finding Lock Contention

In Locks and Threads views:

1. Look for monitor enter/wait events with long durations.
2. Inspect waiting threads and their stack traces.
3. Identify lock-holding threads or contended code regions.
4. Correlate with worker count, throughput, and request latency.

A `WAITING` or `BLOCKED` thread alone does not prove a deadlock. Examine durations, stack traces, lock ownership relationships, and states of involved threads.

### 8.4. Finding Slow I/O

In the I/O view, inspect file read/write and socket read/write events. If requests spend significant time waiting on sockets, the bottleneck may lie in the network or downstream services. If file I/O lags, check storage performance, payload sizes, and read/write patterns.

JFR records only enabled events exceeding their thresholds. The absence of I/O events does not prove zero I/O occurred; verify event settings and thresholds first.

## 9. Designing a Repeatable Observation Session

To compare runs reliably, keep test conditions constant.

### 9.1. Preparation

- Build a single artifact and record its checksum/version.
- Run with the exact same JDK 17 build and JVM flags.
- Use identical inputs/workloads or identical run durations.
- Save recordings in separate, clearly named files per run.
- Record start time, end time, and processed request/item counts.

### 9.2. Running a Baseline

Run the packaged application without JFR enabled:

~~~bash
java -jar build/orders-app.jar
~~~

Record throughput, latency, CPU, and memory from your existing telemetry. This serves as the comparison baseline.

### 9.3. Running with a JFR Profile

~~~bash
java -XX:StartFlightRecording=name=orders-profile,settings=profile,duration=3m,filename=recordings/orders-profile.jfr -jar build/orders-app.jar
~~~

Apply the same workload as the baseline. After the recording completes, run:

~~~bash
jfr summary recordings/orders-profile.jfr
~~~

Open the file in JMC and inspect CPU, allocations, GC, threads, locks, or I/O based on observed symptoms.

### 9.4. Recording Hypotheses and Remeasuring

For example, if you spot heavy allocations in a request-handling method:

1. Record the method name and stack trace from JFR.
2. Read the code to identify which objects are repeatedly allocated.
3. Propose a concrete change, such as safely reusing buffers or eliminating unnecessary conversions.
4. Build the new artifact.
5. Run the identical workload and JFR configuration.
6. Compare throughput, latency, allocations, and GC across both runs.

Never optimize based on a single chart. A change that cuts allocations could increase lock contention or CPU usage; evaluate all related metrics together.

## 10. Selecting Event Settings for Investigative Questions

JFR uses event settings to control which events are enabled, what duration thresholds apply, and whether stack traces are recorded.

If built-in templates lack needed events, create a custom `.jfc` file:

1. Open the JMC Template Manager.
2. Duplicate the `default` or `profile` template.
3. Enable only the required events.
4. Adjust thresholds or stack-trace capture with clear justification.
5. Save as a new file and use it in the next recording.

Never edit default templates inside `JAVA_HOME/lib/jfr` directly. Keep custom copies in project configuration so they can be versioned and rolled back.

Example using a custom configuration file:

~~~bash
java -XX:StartFlightRecording=settings=config/orders-debug.jfc,filename=recordings/orders-debug.jfr,duration=2m -jar build/orders-app.jar
~~~

`settings` accepts either a built-in template name or a path to a `.jfc` file. When the file is outside the JDK template directory, pass its path explicitly.

### 10.1. Thresholds and Missing Events

Many duration-based events are recorded only when their duration exceeds a threshold. For example, if the monitor-wait threshold is 20 ms, shorter waits will not appear. To investigate shorter waits, lower the threshold in a custom `.jfc`, keeping in mind that event volume and overhead will grow.

Avoid dropping every threshold to zero. Start with the specific events tied to your hypothesis, record briefly, and evaluate data quality.

## 11. Targeted Recordings for Memory Leaks

JFR provides events and mechanisms for tracking long-lived objects. However, collecting paths to GC roots can be expensive and pause the JVM.

When suspecting a memory leak:

1. Start with a `profile` recording to capture allocation context.
2. Observe heap trends and long-lived object samples over time.
3. If GC root paths are needed, enable `path-to-gc-roots` during recording/dumping per JDK 17 syntax.
4. Enable this option only when investigating a leak hypothesis and the extra pause cost is acceptable.
5. Combine findings with a heap dump if full retained sizes and reference chains are needed.

Example dumping a running recording while saving paths to GC roots:

~~~bash
jcmd 24680 JFR.dump name=orders-continuous filename=recordings/orders-leak.jfr path-to-gc-roots=true
~~~

GC root paths reveal which objects hold references to suspected leaks. Never leave it enabled routinely just for extra data; Oracle recommends enabling it only when actively diagnosing a memory leak because it can pause the application.

## 12. Packaging Modular Applications or Custom Runtime Images

If the application defines `module-info.java`, package a modular JAR and run on the module path. Example:

~~~bash
jar --create --file build/orders-app.jar --main-class com.example.orders.OrdersApp -C build/classes .
~~~

Run the modular application:

~~~bash
java -XX:StartFlightRecording=name=orders,settings=profile,duration=3m,filename=recordings/orders.jfr --module-path build/orders-app.jar --module com.example.orders/com.example.orders.OrdersApp
~~~

The module name must match `module-info.java`, and the main class must define `public static void main(String[] args)`.

When building a minimal runtime image with `jlink`, verify which modules the application and diagnostics require. If the runtime image must support the JFR API or JFR recordings, ensure the `jdk.jfr` module is included in the image. Analysis tools `jfr` and `jcmd` can be invoked from a full JDK on the host environment.

Conceptual image creation command:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:build/modules" --add-modules com.example.orders,jdk.jfr --output build/orders-runtime
~~~

Module paths and required modules depend on the application. On Windows, the module-path separator differs from Linux/macOS. Use `jdeps` or `jlink --suggest-providers` to determine dependencies and test the generated image in a deployment-like environment.

## 13. Access Control and Protecting Recording Files

Recordings can contain sensitive environment and application details:

- Class, method, and package names plus stack traces.
- File paths, socket addresses, and host environment info.
- System properties and runtime metadata.
- Allocation or object details depending on settings.
- Data emitted by the application into custom events.

Best practices:

- Write recordings into directories with restricted permissions.
- Never publish `.jfr` files to public locations.
- Redact or scrub sensitive data before sharing.
- Enforce retention limits and delete files after investigation.
- Audit custom events so passwords, tokens, or private payloads are never recorded.

`jcmd` requires appropriate local attach permissions. Never expose attach mechanisms or JMX openly over the network merely for convenience in capturing recordings.

## 14. Common Errors When Packaging and Observing with JFR

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `no main manifest attribute` | JAR lacks `Main-Class` | Build an executable JAR or launch the main class/module directly |
| `ClassNotFoundException` running JAR | Dependencies missing from JAR or classpath | Package dependencies or run with the proper classpath/module path |
| JFR produces no file | Invalid path, missing write permissions, or recording has not stopped | Check `filename`, output directory, `JFR.check`, and `JFR.stop` |
| Recording file is tiny or missing events | Template disabled needed events or threshold is too high | Run `jfr summary`, use `profile` or a custom `.jfc` |
| `jcmd` cannot find PID | Different user/namespace or attach disabled | Check process in matching host/container and attach permissions |
| `JFR.dump` does not stop the recording | Expected behavior; dump only exports a snapshot | Run `JFR.stop` when you want to end the recording |
| Continuous recording fills disk | Missing `maxage`/`maxsize` or dumps/rotation unmanaged | Enable `disk=true`, set limits, and manage the repository |
| No allocations visible in `default` | `default` template prioritizes minimal overhead | Use `profile` or enable required allocation events |
| JMC cannot open JFR file | Incomplete file, transfer corruption, or incompatible JMC version | Run `jfr summary`, re-transfer cleanly, and use a compatible JMC |
| Behavior differs between IDE and JAR | Different classpath, flags, agents, or JDK builds | Run the exact packaged artifact with documented JDK and flags |
| Recording adds unwanted overhead | Running `profile` too long, too many events, or overly low thresholds | Shorten duration and narrow event settings |

## 15. Recommended Operational Workflow

A workflow suitable for every build:

1. Build and package the artifact with JDK 17.
2. Record version, checksum, and runtime configuration.
3. Launch the artifact via `java -jar`, classpath, or module path matching production.
4. Enable `default` for continuous observation or `profile` for a short investigation.
5. Name recordings with application name, version, and timestamp.
6. Run `jfr summary` to verify file integrity and event counts.
7. Open in JMC and review Automated Analysis, Code, Memory, Threads, Locks, I/O, and GC.
8. Document hypotheses and apply code or configuration fixes.
9. Build a new artifact and replay the identical workload.
10. Compare before/after measurements and record verifiable conclusions.

Always tie each recording to its exact artifact, JDK, JVM flags, workload, and timestamp. Without those records, comparing two files can lead to false conclusions.

## 16. Lab Checklist

- [ ] Application built with JDK 17.
- [ ] Executable artifact or distribution packaged with all dependencies.
- [ ] Entry point and launch command verified.
- [ ] Reproducible workload prepared.
- [ ] Recordings directory created with write permissions verified.
- [ ] `default` or `profile` selected based on the goal.
- [ ] Recording started at launch or attached via `jcmd`.
- [ ] Recording verified via `JFR.check` or `jfr summary`.
- [ ] CPU, allocations, GC, threads, locks, or I/O analyzed for symptoms.
- [ ] Hypothesis and before/after measurements documented.
- [ ] Recording files secured and cleaned up per retention policy.

## 17. Self-Check Questions

**1. What does JFR observe?**  
JFR records runtime events such as CPU samples, allocations, GC, threads, locks, I/O, class loading, and JVM metadata.

**2. Is JFR built into JDK 17?**  
Yes. JFR is integrated into the HotSpot JVM and controlled via startup options or diagnostic commands.

**3. What attribute must an executable JAR have to run with `java -jar`?**  
The manifest needs a `Main-Class` attribute pointing to a class with a valid `main` method.

**4. Why run the packaged artifact before capturing JFR?**  
So the recording reflects the real classpath/module path, dependencies, JVM flags, and deployment configuration.

**5. What is the difference between `default` and `profile`?**  
`default` captures data with low overhead suitable for continuous recording; `profile` captures more detailed events suited for short-term investigations.

**6. Which JVM option starts JFR at application launch?**  
`-XX:StartFlightRecording`.

**7. Which tool starts a recording on an already running JVM?**  
`jcmd <pid> JFR.start`.

**8. Does `JFR.dump` stop the recording?**  
No. It writes current data to a file while the recording continues running.

**9. Can `JFR.stop` write an output file?**  
Yes. Pass `filename` to save data when stopping; omitting the filename can discard recorded data.

**10. What are `disk=true`, `maxage`, and `maxsize` used for?**  
They govern continuous recording retention in a disk repository; `maxage` and `maxsize` apply only when disk recording is enabled.

**11. Which command prints a summary of a JFR file?**  
`jfr summary recording.jfr`.

**12. How does JMC assist JFR analysis?**  
JMC renders charts and tables for code, memory, GC, threads, locks, I/O, and automated analysis results.

**13. Why might allocation events be missing from a recording?**  
The template may not enable allocation events or thresholds may be too high; verify settings and consider `profile` or a custom `.jfc`.

**14. Should `path-to-gc-roots` be enabled for all recordings?**  
No. Collecting GC root paths can be slow and pause the JVM; enable it only when investigating suspected memory leaks.

**15. Why record artifact versions and JVM flags alongside recordings?**  
To make runs reproducible and allow meaningful before/after comparisons.

## Official References

- [Java SE 17 — The jar Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html): creating executable JARs, modular JARs, and manifest main classes.
- [Java SE 17 — JAR File Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html): manifests, `Main-Class`, modular JARs, and classpaths.
- [Java SE 17 — The java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): syntax for launching JARs/modules and `-XX:StartFlightRecording`.
- [Java SE 17 — The jcmd Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `JFR.start`, `JFR.check`, `JFR.dump`, `JFR.stop`, and options.
- [Java SE 17 — The jfr Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html): `jfr summary`, `jfr print`, `jfr metadata`, `assemble`, and `disassemble`.
- [Java SE 17 — Diagnostic Tools: Flight Recorder](https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html): starting recordings at startup, via `jcmd`, or via JMC and analyzing recordings.
- [Java SE 17 — Flight Recorder Configurations](https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder-configurations.html): `default.jfc`, `profile.jfc`, and custom event settings.
