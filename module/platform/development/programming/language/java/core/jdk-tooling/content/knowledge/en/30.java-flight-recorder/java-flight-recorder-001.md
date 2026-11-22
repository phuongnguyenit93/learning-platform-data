# What is JFR? Java Flight Recorder in the JDK

**Java Flight Recorder (JFR)** is a timeline-based event and diagnostic data recording system built into the Java Virtual Machine (JVM). JFR collects events such as CPU sampling, object allocation, garbage collection (GC), threads, synchronization locks, I/O, class loading, and JIT compiler activity. This data helps identify why an application is slow, consuming excessive CPU, allocating too much memory, experiencing long GC pauses, or suffering from lock contention.

JFR is built into the HotSpot JDK. You can start a recording at application launch or enable a recording on a running JVM using **jcmd**. Data is saved to a binary file with the **.jfr** extension, which can then be analyzed with JDK Mission Control (JMC) or the **jfr** command-line tool.

JFR is well suited for observing an application at runtime and collecting evidence when an incident occurs. It is not a line-by-line code logger, nor does it guarantee recording every single program operation. Each event type has its own enable/disable configuration, threshold, and collection mechanism.

## 1. What data does JFR collect?

JFR records **events** with timestamps and descriptive fields. Depending on the event type, a record may include start/end times, thread, class, size, stack trace, or JVM-related information.

| Category | Example data | Questions you can investigate |
|---|---|---|
| CPU and execution | Execution samples, thread CPU load, compiler activity | Which thread or method is consuming CPU? |
| Memory and allocation | Object allocation samples, heap summary, allocation requiring GC | Where and how frequently is the application allocating objects? |
| Garbage collection | Garbage collection, GC phases, heap usage, pause duration | Why is GC happening frequently or causing long pauses? |
| Thread and synchronization | Thread park, monitor enter/wait, thread start/end | Where are threads waiting? Is there lock contention? |
| I/O and network | File read/write, socket read/write, file force | Which I/O operation is slowing down the application? |
| Class loading | Class load/unload, classloader statistics | Are too many classes being loaded or are classloaders staying alive too long? |
| Exceptions and errors | Exception throw, error event | Which exception types appear most frequently? |
| JVM and OS | JVM flags, system properties, process/OS information | What configuration and environment is the process running with? |

Not all events are enabled in every recording. Some I/O events are only recorded when an operation's duration exceeds a threshold; some allocation events use sampling and therefore do not represent every individual object allocated. Always check the event settings and event types before drawing conclusions from the data.

JFR supports three common event types:

- **Instant event:** occurs at a single point in time, such as an operation or state recorded immediately.
- **Duration event:** has a start time and an end time, such as waiting for a lock or performing an I/O operation.
- **Sample event:** sampled periodically, such as an execution sample to observe where a thread is currently running.

An event with a stack trace helps trace back from the event to the relevant method. However, a stack trace is only present when the event is configured to collect stacks and the JVM can provide that data.

## 2. How does JFR work?

When a recording is enabled, the JVM writes configured events into internal buffers. A recording can keep data in memory buffers or write to a disk repository depending on the configuration. When analysis is needed, JFR dumps the data to a .jfr file.

~~~text
Java application
       |
       v
HotSpot JVM + JFR event producers
       |
       v
Configured events and buffers
       |
       +------> Disk repository / rolling data
       |
       v
Dump recording to .jfr
       |
       +------> jfr CLI
       |
       +------> JDK Mission Control
       |
       +------> JFR consumer API
~~~

JFR can record data continuously over a long period with an appropriate configuration, or run a profiling recording for a short period. The event configuration determines the data volume and overhead.

JFR typically has low overhead with the default configuration, but it is **not zero**. Profiling recordings, enabling additional events with stack traces, lowering thresholds, or collecting detailed data can increase CPU usage, file size, and affect latency. Choose a configuration based on your investigation goal and verify the impact in an appropriate environment.

## 3. Two built-in configurations: default and profile

The JDK typically provides two recording templates in the JAVA_HOME/lib/jfr directory:

| Template | Characteristics | When to use |
|---|---|---|
| **default.jfc / default** | Collects a useful set of events with low overhead | Continuous recording, long-term production observation |
| **profile.jfc / profile** | Collects more information, higher overhead | Short-term profiling when deep investigation is needed |

**default** is usually the right choice to start long-term observation. **profile** helps analyze methods, allocations, and JVM activity in greater detail, but should be used for a limited duration.

The template files are located at:

~~~text
<JAVA_HOME>/lib/jfr/default.jfc
<JAVA_HOME>/lib/jfr/profile.jfc
~~~

Do not edit the template files bundled with the JDK directly. If you need to change events, create a custom configuration based on an existing template and use the new configuration for your recording.

## 4. Starting JFR at Java launch

You can enable a recording right when running an application using the **-XX:StartFlightRecording** option.

Example of a 60-second recording:

~~~sh
java -XX:StartFlightRecording=filename=app-startup.jfr,settings=profile,duration=60s -jar app.jar
~~~

Options:

- **filename=app-startup.jfr**: where to write the recording file.
- **settings=profile**: uses the profile configuration.
- **duration=60s**: automatically stops the recording after 60 seconds.

If you want to start after a delay:

~~~sh
java -XX:StartFlightRecording=delay=20s,duration=60s,filename=app.jfr,settings=profile -jar app.jar
~~~

The JVM will wait 20 seconds and then record for 60 seconds. This is useful when you only want to capture data after the application has finished starting up or when a specific workload begins.

To run a continuous recording with bounded stored data:

~~~sh
java -XX:StartFlightRecording=disk=true,settings=default,maxage=6h,maxsize=500m -jar app.jar
~~~

**maxage** and **maxsize** limit the data retained in the disk repository. When you need to extract data for analysis, you can dump the recording to a .jfr file.

## 5. Starting a recording on a running JVM with jcmd

In many situations, the application is already running and you do not want to restart it. You can use **jcmd** to control JFR on the target JVM.

List Java processes:

~~~sh
jcmd -l
~~~

Example output:

~~~text
69872 com.example.Server
84664 com.example.Worker
~~~

Select the correct PID of the application you want to inspect. Start a recording:

~~~sh
jcmd 69872 JFR.start name=Incident settings=profile duration=60s filename=incident.jfr
~~~

A continuous recording can be started as follows:

~~~sh
jcmd 69872 JFR.start name=Continuous settings=default disk=true maxage=2h maxsize=500m
~~~

Some commonly used parameters:

| Parameter | Meaning |
|---|---|
| **name** | Recording name used for check/dump/stop |
| **settings** | Template default, profile, or a .jfc file |
| **duration** | How long the recording runs before stopping automatically |
| **filename** | Path of the file written when the recording stops |
| **disk** | Enables writing recording data to disk while running |
| **maxage** | Age limit for data stored in the disk repository |
| **maxsize** | Size limit for data stored on disk |

View commands supported by the target JVM:

~~~sh
jcmd 69872 help JFR.start
jcmd 69872 help JFR.dump
jcmd 69872 help JFR.stop
~~~

The parameter list may vary by JDK version. Check **help** on the actual JVM before using advanced options.

## 6. Checking, dumping, and stopping a recording

After starting a recording, you can check its status:

~~~sh
jcmd 69872 JFR.check
~~~

Or view details of a specific recording:

~~~sh
jcmd 69872 JFR.check name=Incident verbose=true
~~~

Dump current data to a file without stopping the recording:

~~~sh
jcmd 69872 JFR.dump name=Incident filename=incident-snapshot.jfr
~~~

**JFR.dump** writes a file from the recording data at the time of the dump; the running recording can continue collecting events.

When you want to stop the recording and save the file:

~~~sh
jcmd 69872 JFR.stop name=Incident filename=incident-final.jfr
~~~

If you have already dumped using **JFR.dump**, you can stop the recording afterward:

~~~sh
jcmd 69872 JFR.stop name=Continuous
~~~

Note: if you call **JFR.stop** without providing **filename**, the recording data may be discarded when stopped. Dump first or specify a filename if you need to keep the data.

Typical control workflow:

1. **jcmd <pid> JFR.start ...** to start.
2. **jcmd <pid> JFR.check** to confirm the recording is running.
3. **jcmd <pid> JFR.dump ...** to save a snapshot if you want to continue collecting.
4. **jcmd <pid> JFR.stop ...** to stop and save the final file.

## 7. Reading recording files with the jfr command

The JDK provides the **jfr** tool to inspect .jfr files without opening a graphical interface.

View a recording summary:

~~~sh
jfr summary incident.jfr
~~~

The output displays the recording version, duration, chunk count, each event type, count, and data size. This is the first step to check whether the recording contains the events you need.

Print events to the terminal:

~~~sh
jfr print incident.jfr
~~~

Print only the events you need to investigate:

~~~sh
jfr print --events jdk.ObjectAllocationSample,jdk.GarbageCollection incident.jfr
~~~

Some commonly inspected events:

- **jdk.ExecutionSample**: sample of where a thread is executing.
- **jdk.ObjectAllocationSample**: sample of object allocation.
- **jdk.GarbageCollection**: GC event details.
- **jdk.JavaMonitorEnter**: time spent waiting to enter a monitor/lock.
- **jdk.SocketRead** and **jdk.SocketWrite**: socket operations when the events are enabled.
- **jdk.FileRead** and **jdk.FileWrite**: file operations when the events are enabled.

Example of viewing only allocation samples:

~~~sh
jfr print --events jdk.ObjectAllocationSample incident.jfr
~~~

An event output may look like:

~~~text
jdk.ObjectAllocationSample {
  startTime = 19:34:05.700
  objectClass = byte[]
  weight = 21.7 MB
  eventThread = "main"
  stackTrace = [
    com.example.Worker.run() line: 42
  ]
}
~~~

This is an illustrative output. **weight** in an allocation sample is an estimated weight that JFR uses to represent the sampled allocation amount; it should not be interpreted as a single object whose size equals the entire weight.

View the event metadata present in the recording:

~~~sh
jfr metadata incident.jfr
~~~

View the tool's commands and options:

~~~sh
jfr help
jfr help print
~~~

## 8. Analyzing with JDK Mission Control

**JDK Mission Control (JMC)** is a graphical tool for opening and analyzing .jfr files. JMC provides views that help spot issues that are difficult to see when reading text output.

| View / group | What to inspect |
|---|---|
| General | Recording duration, JVM, operating system, overview information |
| Method Profiling | Methods and stack traces with high execution sample counts |
| Threads | Thread state, thread activity, and wait times |
| Memory | Heap usage, allocation, objects, and GC |
| Garbage Collections | GC count, pause durations, and phases |
| Locks | Monitor contention, threads waiting on locks |
| I/O | File/socket operations and execution durations |
| Exceptions | Exception events when the corresponding configuration is enabled |

When CPU is high, open Method Profiling to see which stack traces appear frequently in execution samples. When heap grows rapidly, check allocation and GC to find classes with high allocation rates. When the application responds slowly despite low CPU, check thread states, monitor contention, and I/O.

Do not draw conclusions from a single chart alone. Correlate timestamps, workload, threads, stack traces, and related events within the same time window.

## 9. Scenarios where JFR helps investigate

### 9.1. High CPU

Symptom: process CPU spikes while requests are slow.

1. Create a recording with **settings=profile**.
2. Open Method Profiling or inspect **jdk.ExecutionSample**.
3. Find stack traces that appear frequently.
4. Check for CPU-intensive loops, large data processing, regex, serialization, or code called too frequently.
5. Fix the bottleneck and capture a new recording to compare.

Execution samples are taken periodically; they help estimate where CPU is spent rather than providing an exhaustive list of every method call.

### 9.2. High allocation or suspected memory leak

Symptom: heap grows with workload, frequent GC, or memory does not drop after load ends.

1. Inspect allocation samples and stack traces to find where objects are created.
2. Inspect GC events and heap summaries to understand the impact on the heap.
3. Compare recordings across equivalent workload phases.
4. If a leak is suspected, consider configuring memory leak events or collecting path to GC roots per the JDK documentation.
5. Analyze a heap dump when you need to identify which objects are holding references.

**path-to-gc-roots** can be expensive and cause short pauses. Only enable it when you already have a memory leak hypothesis; do not enable it routinely just to collect everything.

### 9.3. Blocked threads or lock contention

Symptom: throughput drops and requests wait a long time even though CPU is not high.

1. Inspect **jdk.JavaMonitorEnter** and thread/lock-related events.
2. Find threads waiting on monitors for long durations.
3. Read stack traces to identify the code holding the lock.
4. Check for overly broad synchronized blocks, lock ordering, or I/O tasks running inside a lock.
5. Re-measure after optimizing.

### 9.4. Slow I/O

Symptom: requests are slow, but CPU is low and threads are often waiting.

1. Inspect file/socket events if the recording has them enabled.
2. Find operations with high duration or high frequency.
3. Correlate with threads and stack traces.
4. Check the filesystem, network, remote services, timeouts, and payload sizes.
5. Adjust event thresholds if more data is needed, while considering overhead.

## 10. Customizing events and recording templates

If the default templates do not collect the events you need, you can create a custom .jfc configuration file. The JDK provides the command:

~~~sh
jfr configure --interactive
~~~

You can copy the profile.jfc template from JAVA_HOME/lib/jfr to a working directory and create a custom configuration:

~~~sh
jfr configure --input profile.jfc --output custom.jfc
~~~

The configuration is passed when starting a recording:

~~~sh
jcmd 69872 JFR.start name=Custom settings=C:/jfr/custom.jfc duration=60s filename=custom.jfr
~~~

Event settings can enable/disable events, enable stack traces, set thresholds, or adjust sampling intervals. For duration events, thresholds ensure only operations long enough to be relevant for bottleneck investigation are recorded. A threshold that is too low can increase recording size and overhead.

Do not enable all events at once without a specific goal. Start from a suitable template, enable additional events relevant to your hypothesis, and record configuration changes so measurements are repeatable.

## 11. JFR API and custom events

In addition to command-line tools, applications can use the **jdk.jfr** module to create custom business events. For example, a system can record an event when processing an order, completing a batch, or invoking a critical processing step.

Example of a custom event:

~~~java
import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;

@Name("com.example.OrderProcessed")
@Label("Order Processed")
@Category({"Application", "Orders"})
class OrderProcessed extends Event {
    @Label("Order ID")
    String orderId;

    @Label("Item Count")
    int itemCount;
}
~~~

When you want to record the event in code:

~~~java
OrderProcessed event = new OrderProcessed();
event.orderId = "ORD-1001";
event.itemCount = 3;
event.begin();
processOrder();
event.end();
event.commit();
~~~

This snippet illustrates how to define and emit an event; **processOrder()** represents the application's business logic. In a real project, you should check **event.shouldCommit()** before computing expensive data solely for the event. This method checks both whether the event is enabled and the active threshold. Event classes are enabled by default unless marked with **@Enabled(false)** or disabled in the recording settings. An event is only recorded when a recording is running and the event is enabled.

Custom events help connect business context with JVM events. During analysis, you can place an order's processing time alongside allocations, GC, threads, and I/O occurring in the same time window.

## 12. How does JFR differ from logs, JMX, and profilers?

| Tool | Primary information | Strengths |
|---|---|---|
| Application log | Business messages explicitly written by the application | Tracking errors, states, and business actions |
| JMX / MXBean | Gauges, counters, and JVM management state | Reading current metrics and monitoring integration |
| JFR | Events with timestamps, durations, stacks, and JVM/OS data | Timeline-based root-cause investigation |
| CPU profiler | Stack samples or instrumentation focused on CPU | Finding CPU-consuming methods |
| Heap dump | Object snapshot and reference graph | Analyzing objects retaining memory |

JFR complements logs and metrics. For example, logs may show that a request timed out; JFR can show that during the same time window the thread was waiting on a socket, blocked on a monitor, or affected by GC.

JFR does not replace application logs because it does not inherently understand full business semantics. Nor does it replace a heap dump when you need detailed analysis of the reference graph or retained heap.

## 13. Performance impact and production usage

JFR is designed for JVM diagnostics with low overhead when configured appropriately. However, overhead depends on events, thresholds, stack traces, sampling frequency, heap size, workload, and recording duration.

- Use **default** for continuous recordings and limit **maxage/maxsize**.
- Use **profile** for short durations when more data is needed.
- Only enable additional events when you have a specific hypothesis.
- Do not set thresholds too low without evaluating event volume and overhead.
- Use **duration** to automatically terminate short-term recordings.
- Monitor the disk repository size and the directory storing .jfr files.
- Watch latency/CPU during a recording, especially when many events are configured.
- Test configurations on staging or a replica before rolling out broadly.

JFR is not a "zero overhead" tool. Some diagnostic commands can have a noticeable impact depending on the operation and heap size. Read the impact notes in **jcmd <pid> help JFR.start** and the JDK documentation before enabling intensive configurations.

## 14. Recording data security

A .jfr file can contain sensitive information:

- Internal class, method, package names, and stack traces.
- File paths, process names, and operating system details.
- System properties and certain recorded environment variables.
- Endpoints, hostnames, I/O details, or business data appearing in custom events.
- Thread information, request context, or data attached to events by the application.

Treat .jfr files as internal diagnostic data:

1. Store files in a directory with restricted access permissions.
2. Do not commit recordings to a repository or upload them to public locations.
3. Mask or remove sensitive data before sharing externally.
4. Use scrubbing tools or configure events to reduce unnecessary data.
5. Delete recordings and copies according to your organization's retention policy.

Do not put passwords, tokens, or personal data into custom events. Stack traces and property names can also reveal system structure.

## 15. Complete hands-on example with Java 17+

The following example creates a workload that continuously allocates byte arrays. You will launch the application, start a recording with **jcmd**, dump the file, and use **jfr** to read allocation samples.

Create **JfrProbe.java**:

~~~java
public class JfrProbe {
    static final byte[][] retained = new byte[200][];

    public static void main(String[] args) throws InterruptedException {
        int next = 0;
        System.out.println("jfr-probe-ready");

        while (true) {
            retained[next] = new byte[64 * 1024];
            next = (next + 1) % retained.length;
            Thread.sleep(20);
        }
    }
}
~~~

Compile:

~~~sh
mkdir -p out
javac --release 17 -d out JfrProbe.java
~~~

Run the program:

~~~sh
java -Xms128m -Xmx128m -cp out JfrProbe
~~~

Exact stdout when the application starts:

~~~text
jfr-probe-ready
~~~

Keep this terminal open. Open a second terminal and find the PID:

~~~sh
jcmd -l
~~~

Suppose the PID is **69872**. Start a recording:

~~~sh
jcmd 69872 JFR.start name=Demo settings=profile disk=true maxage=2m maxsize=64m
~~~

Check the recording:

~~~sh
jcmd 69872 JFR.check name=Demo
~~~

Dump a snapshot to a file:

~~~sh
jcmd 69872 JFR.dump name=Demo filename=demo.jfr
~~~

Read the summary:

~~~sh
jfr summary demo.jfr
~~~

View allocation samples:

~~~sh
jfr print --events jdk.ObjectAllocationSample demo.jfr
~~~

Stop the recording:

~~~sh
jcmd 69872 JFR.stop name=Demo
~~~

In a test with JDK 24.0.2, **JfrProbe** compiled with **javac --release 17** and printed **jfr-probe-ready** exactly. The profile recording was created, checked, dumped, and stopped successfully. **jfr summary** reported a recording of about 2 seconds with 253 KB of data; **jfr print** showed class **byte[]**, thread **main**, and a stack trace pointing to **JfrProbe.main**. These numbers are only the results of that test run, not fixed output.

When finished, return to the terminal running **JfrProbe** and press **Ctrl+C** to terminate the JVM.

## 16. Common errors and troubleshooting

| Symptom | Common cause | Resolution |
|---|---|---|
| Unknown diagnostic command: JFR.start | JVM does not support JFR or command is unavailable on the target runtime | Check JDK/JVM and **jcmd <pid> help** |
| Cannot attach to PID | Wrong PID, wrong user, JVM stopped, or attach disabled | Re-verify PID and check attach permissions |
| JFR.start ran but no file found | Recording not dumped, not stopped with filename, or invalid path | Use **JFR.dump** or **JFR.stop ... filename=...** |
| JFR.check does not show expected recording | Wrong recording name or recording already ended | Check all recordings without passing name, then identify the right ID/name |
| .jfr file is too large | Used profile for too long or enabled too many events | Use default, limit maxage/maxsize, and shorten duration |
| Expected event is missing | Event is disabled, threshold is too high, or recording type does not collect it | Check event settings, metadata, and .jfc configuration |
| Allocation samples do not match actual object count | Sampling data, not a log of every allocation | Use weight as an estimate and choose appropriate events/config |
| JFR slows down the application | Profile recording or detailed events causing overhead | Reduce events, raise thresholds, use default, or shorten duration |
| Cannot open file | File incomplete, partially written, or incompatible tool | Verify **JFR.stop**/dump completed and use a compatible JDK/JMC |
| No stack trace | Event setting does not enable stack trace or event does not support it | Check the specific event configuration |
| Recording missed the incident window | Started too late or only used a short recording | Use a continuous recording with maxage/maxsize limits and dump on incident |

## 17. Investigation workflow with JFR

1. Identify the symptom: high CPU, frequent GC, high allocation, lock contention, slow I/O, or exceptions.
2. Identify the JVM/PID with **jcmd -l**.
3. Choose **default** for continuous recording or **profile** for short profiling.
4. Start the recording with **-XX:StartFlightRecording** or **jcmd JFR.start**.
5. Confirm with **JFR.check**.
6. Reproduce the workload or wait for the incident during the recording.
7. Dump data with **JFR.dump** or stop and save with **JFR.stop filename=...**.
8. Inspect the recording with **jfr summary**.
9. Open the file in JMC or filter events with **jfr print**.
10. Correlate timestamps, threads, events, stack traces, and workload to find the root cause.
11. Propose changes, re-measure with an equivalent recording, and compare.
12. Protect the .jfr file and delete it according to your data retention policy.

### Checklist

- [ ] Identified the correct JVM/PID.
- [ ] Selected a template suited to the goal and duration.
- [ ] Verified the recording with **JFR.check**.
- [ ] Dumped or stopped with a filename to save the data.
- [ ] Checked **jfr summary** and confirmed the required events are present.
- [ ] Distinguished sampled events from per-operation events.
- [ ] Analyzed timestamps, threads, and stack traces in the context of the workload.
- [ ] Evaluated overhead, file size, and latency impact.
- [ ] Protected the recording as it may contain sensitive information.
- [ ] Compared recordings before and after changes to verify results.

Java Flight Recorder provides timestamped, contextual event data for investigating JVM internals. By choosing the right template, bounding recording duration and size, and combining **jcmd**, **jfr**, or JMC, you can gather evidence on CPU, memory, GC, threads, and I/O to pinpoint root causes without adding manual logging everywhere in your application.

## References

- [Oracle JDK 24 — Diagnostic Tools: Java Flight Recorder](https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html)
- [Oracle JDK 24 — The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [Oracle JDK 24 — Flight Recorder Configurations](https://docs.oracle.com/en/java/javase/24/jfapi/flight-recorder-configurations.html)
- [Oracle JDK 24 — JFR Recording API](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/jdk/jfr/Recording.html)
- [Oracle JDK 24 — JFR Event API](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/jdk/jfr/Event.html)
- [Oracle JDK Mission Control 9 — User Guide](https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/using-jdk-flight-recorder.html)
