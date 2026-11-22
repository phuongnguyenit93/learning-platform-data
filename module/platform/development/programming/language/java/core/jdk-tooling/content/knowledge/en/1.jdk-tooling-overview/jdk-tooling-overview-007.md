# Diagnostic Tools in JDK Tooling

JDK diagnostic tools help you observe a running Java process, identify why an application is slow or hung, monitor garbage collection (GC), inspect the heap, and collect data for deeper analysis. They are typically used when an application is already running in development, testing, or production environments and you need evidence directly from the JVM.

No single tool can answer every question. Start with low-overhead data such as process information and thread dumps before taking a heap dump or running tools that may pause the JVM.

## 1. Tool Categories and When to Use Them

| Area to inspect | Primary tools | Data collected |
|---|---|---|
| Process discovery and JVM configuration | jps, jcmd, jinfo | PID, main class, startup arguments, JVM flags, and system properties |
| Threads and locks | jcmd Thread.print, jstack | Stack traces, thread states, monitors, and locks being waited on |
| Heap and objects | jcmd GC.heap_info, GC.class_histogram, GC.heap_dump; jmap | Heap status, object counts by class, heap dump |
| GC and performance | jstat, unified logging, JFR | GC frequency, heap region utilization, pauses, and runtime events |
| Native memory | Native Memory Tracking, jcmd VM.native_memory, jhsdb | Native memory allocations tracked by HotSpot |
| Visual monitoring | JConsole, VisualVM | Charts for heap, threads, GC, MBeans, and profiling |

In modern JDKs, **jcmd** is usually the best starting point because it consolidates many diagnostic commands into a single interface. Standalone commands such as jstack and jmap remain useful, especially when following established workflows, but you should check what jcmd supports on the target JVM version first.

## 2. Preparation Before Diagnosing

Command-line tools are located in the JDK's **bin** directory, such as **$JAVA_HOME/bin** on Linux/macOS or **%JAVA_HOME%\\bin** on Windows. You can add this directory to your PATH to invoke the commands from anywhere.

A few important guidelines:

- Run the tools on the same machine as the target JVM and usually under the same OS user account that started the JVM.
- Prefer using a JDK with the same major version as the target JVM. Some commands or output fields change across versions.
- Identify the exact PID before running a command. A single machine may run multiple Java processes.
- The attach mechanism can be disabled with the **-XX:+DisableAttachMechanism** JVM option, or restricted by OS permissions, containers, namespaces, or runtime configuration.
- In containers, the PID visible from the host and the PID inside the container may differ. Run the tool inside the same environment and namespace as the JVM.
- Do not assume every command is available in every JDK distribution. Use the tool's and target JVM's help command to confirm.

The examples below use **<pid>** as a placeholder for the actual PID. Replace this placeholder with the numeric PID you found, without typing the angle brackets.

## 3. Finding Java Processes and Viewing JVM Configuration

### Listing processes

**jps** lists the JVMs that the tool can discover:

~~~bash
jps -lv
~~~

Commonly used options:

- **-l**: displays the full main class name or JAR path.
- **-v**: displays JVM arguments.
- **-m**: displays arguments passed to the main method.

You can use **jcmd -l** to list attachable JVMs:

~~~bash
jcmd -l
~~~

If a process does not appear, check the user account running the command, the PID namespace, access permissions, and whether attach has been disabled. The output of jps is not always a complete list of every Java process on the host.

### Viewing information for a JVM

Before collecting data, ask the JVM which commands it supports:

~~~bash
jcmd <pid> help
~~~

Some commonly useful commands:

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> VM.system_properties
~~~

Meaning:

- **VM.version**: the running JVM version.
- **VM.command_line**: main class, JAR, and startup arguments.
- **VM.flags**: active JVM configuration flags.
- **VM.system_properties**: system properties of the process.

You can use **jinfo** to inspect similar information:

~~~bash
jinfo -flags <pid>
jinfo -sysprops <pid>
~~~

Command-line details and system properties may contain file paths, tokens, or connection information. When sharing diagnostic logs, review them and redact sensitive data.

## 4. Analyzing Threads and Hangs

A thread dump is a point-in-time snapshot of thread stack traces. It helps you find threads that are running for a long time, waiting on locks, waiting on I/O, or caught in a deadlock.

### Capturing a thread dump with jcmd

~~~bash
jcmd <pid> Thread.print -l
~~~

The **-l** option requests additional information about locks that threads are holding or waiting for. You can save the output to a file for comparison:

~~~bash
jcmd <pid> Thread.print -l > thread-1.txt
~~~

Repeat after about 5–10 seconds to capture additional snapshots:

~~~bash
jcmd <pid> Thread.print -l > thread-2.txt
jcmd <pid> Thread.print -l > thread-3.txt
~~~

If a thread repeatedly appears at the same stack frame, it may be stuck or processing a long-running task. If the stack changes across samples, the thread may still be making progress.

### Using jstack

~~~bash
jstack -l <pid>
~~~

**jstack** generates a thread dump directly. For a locally running JVM, jcmd is usually the more flexible choice; jstack remains useful in existing scripts or when a familiar command is needed.

### Understanding thread states

- **RUNNABLE**: the thread is executing or ready to run. This state does not guarantee the thread is consuming CPU; it may also be inside a native call or waiting for an OS-level resource.
- **BLOCKED**: the thread is waiting to acquire an intrinsic monitor to enter or re-enter a synchronized block.
- **WAITING**: the thread is waiting for another thread to perform an action, typically without a timeout, such as via Object.wait or LockSupport.park.
- **TIMED_WAITING**: the thread is waiting with a timeout, such as Thread.sleep or wait with a timeout.
- **TERMINATED**: the thread has finished; this state usually no longer appears as an active thread in a dump.

When reading a dump, pay attention to:

1. The thread name and its role, such as an HTTP worker, scheduler, or consumer.
2. The thread state and current stack trace.
3. Lines describing the locks the thread is waiting on or holding.
4. Which thread holds a lock that multiple other threads are waiting on.
5. The deadlock section at the end of the dump, if the JVM detected a deadlock.

A thread in WAITING or TIMED_WAITING is not automatically a bug. Thread pools routinely have workers waiting for tasks. Combine thread state, stack traces, load levels, and multiple snapshots before drawing conclusions.

### Small example program for practice

Create **DiagnosticDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;

public class DiagnosticDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(() -> {
            while (!Thread.currentThread().isInterrupted()) {
                try {
                    Thread.sleep(1_000);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "diagnostic-worker");

        worker.start();
        System.out.println("DiagnosticDemo started");
        new CountDownLatch(1).await();
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac DiagnosticDemo.java
java DiagnosticDemo
~~~

Stdout:

~~~text
DiagnosticDemo started
~~~

The program keeps the process running so you have time to observe it. Open another terminal, find the PID with **jps -lv**, and run **jcmd <pid> Thread.print -l**. In the dump, the **diagnostic-worker** thread is usually in TIMED_WAITING because it is sleeping; the **main** thread is waiting on the CountDownLatch. This is the intended state of the example, not a deadlock.

## 5. Inspecting the Heap and Objects

### Viewing a heap overview

~~~bash
jcmd <pid> GC.heap_info
~~~

This command provides an overview of the JVM heap, depending on the garbage collector and JVM version. Use it to get a quick sense of current heap usage, then combine it with GC logs or JFR to understand trends over time.

### Viewing a class histogram

~~~bash
jcmd <pid> GC.class_histogram
~~~

A histogram lists instance counts and total size by class. It is useful for finding classes that account for an unusual number of objects or amount of memory. Exact options and behavior depend on the JVM version; this command may trigger a Full GC by default, so consider the impact in production.

You can also use jmap:

~~~bash
jmap -histo <pid>
jmap -histo:live <pid>
~~~

The **:live** variant counts only live objects after a GC and may trigger a GC. A histogram only shows counts and sizes by class; it does not show the full reference paths keeping objects in memory.

### Capturing a heap dump

A heap dump is a recording of objects and their reference relationships in the heap at the time of collection. You can use jcmd:

~~~bash
jcmd <pid> GC.heap_dump filename=heap-dump.hprof
~~~

Or use jmap:

~~~bash
jmap -dump:live,format=b,file=heap-dump.hprof <pid>
~~~

A heap dump can be very large, and generating it may pause the JVM or trigger a GC. Only capture one when you have sufficient disk space and have evaluated the impact on the application.

You can open an HPROF file with Eclipse Memory Analyzer (MAT) or a compatible tool. When analyzing, typically start with:

- **Dominator Tree**: find objects or groups of objects retaining the largest share of the heap.
- **Retained Heap**: estimate how much memory would be freed if an object were no longer retained.
- **Path to GC Roots**: find the reference chain keeping an object alive.
- **Histogram**: compare object counts by class.

A class having many instances is not enough by itself to conclude there is a memory leak. Check whether objects are unexpectedly retained, how fast they grow over time, and whether they can be reclaimed after GC.

Heap dumps may contain passwords, tokens, user data, request payloads, or business data. Treat them as sensitive data: restrict access, store them securely, and follow your organization's retention policies.

## 6. Monitoring Garbage Collection

### Using jstat

**jstat** polls JVM statistical counters at a fixed interval. For example:

~~~bash
jstat -gcutil <pid> 1000 10
~~~

This command samples every 1,000 milliseconds for a total of 10 samples. Common columns:

- **S0, S1**: utilization of the two Survivor spaces.
- **E**: utilization of Eden.
- **O**: utilization of the Old generation.
- **M**: utilization of Metaspace.
- **CCS**: utilization of Compressed Class Space, if present.
- **YGC, YGCT**: count and total time of Young GCs.
- **FGC, FGCT**: count and total time of Full GCs.
- **GCT**: total recorded GC time.

You can also view capacities and usage in size units for each heap region:

~~~bash
jstat -gc <pid> 1000 10
~~~

Column names and exact meanings may vary by collector and JVM version. Do not draw conclusions from a single sample. Observe the trend: whether Old generation keeps growing, whether GC runs more frequently, and whether post-GC usage returns to a stable baseline.

### Enabling unified logging for GC

Java 9 and later use unified logging. You can enable it at application startup:

~~~bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar app.jar
~~~

The log shows GC timestamps, event types, pause durations, and heap size changes. Configure log rotation in long-running environments to prevent the file from growing without bound.

If the application is already running without GC logging enabled, you can use jstat or JFR to collect part of the runtime data. Not all historical details can be recovered after an event has already occurred.

## 7. Java Flight Recorder (JFR)

JFR records JVM and application events such as CPU sampling, allocations, GC, lock contention, thread parks, and certain I/O events. It is a powerful tool for diagnosing performance issues because it provides timeline data rather than a single snapshot.

### Starting a recording with jcmd

~~~bash
jcmd <pid> JFR.start name=diagnostic settings=profile duration=60s filename=diagnostic.jfr
~~~

The command above starts a 60-second recording and writes the result to a file when complete. The profile setting collects more detail than the default configuration and can add extra overhead; choose a duration appropriate for the situation.

Check running recordings:

~~~bash
jcmd <pid> JFR.check
~~~

If a recording was started without a duration or filename, you can dump the data and then stop the recording:

~~~bash
jcmd <pid> JFR.dump name=diagnostic filename=diagnostic.jfr
jcmd <pid> JFR.stop name=diagnostic
~~~

The recording name must match the recording that was started. Check **jcmd <pid> help JFR.start**, **JFR.dump**, and **JFR.stop** if the syntax differs on your JDK version.

### Reading JFR files

The JDK provides the **jfr** command to summarize or print events:

~~~bash
jfr summary diagnostic.jfr
jfr print --events jdk.ExecutionSample,jdk.GarbageCollection diagnostic.jfr
~~~

You can open the file in Java Mission Control (JMC) to inspect the timeline, CPU hot methods, allocations, GC pauses, and lock contention. JMC is distributed separately in many environments; do not assume it is included in every JDK installation.

JFR typically has low overhead when configured appropriately, though it is not zero. For short-lived issues, record during the window when the issue reproduces and correlate timestamps with application logs.

## 8. Inspecting Native Memory with Native Memory Tracking

The heap is not the entirety of a Java process's memory. Process RSS also includes Metaspace, code cache, thread stacks, direct buffers, native libraries, and internal JVM structures.

**Native Memory Tracking (NMT)** tracks a portion of HotSpot's native memory allocations. NMT must be enabled when the JVM starts:

~~~bash
java -XX:NativeMemoryTracking=summary -jar app.jar
~~~

You can choose **detail** for finer-grained tracking at the cost of higher overhead. Once the JVM is running with NMT, use jcmd:

~~~bash
jcmd <pid> VM.native_memory summary
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary.diff
~~~

- **summary**: view allocations by category.
- **baseline**: set a baseline for comparison.
- **summary.diff**: view changes relative to the baseline.

NMT does not track every native memory region allocated by third-party libraries or arbitrary native code. If RSS grows while NMT does not explain it, combine OS tools, a native profiler, and checks on direct buffers or JNI libraries.

## 9. Serviceability Agent and jhsdb

**jhsdb** is the Serviceability Agent toolset used to deeply inspect JVM state or core dumps. For example:

~~~bash
jhsdb jstack --pid <pid>
jhsdb jmap --heap --pid <pid>
jhsdb jmap --histo --pid <pid>
~~~

You can open the Serviceability Agent command-line interface:

~~~bash
jhsdb clhsdb --pid <pid>
~~~

This is an advanced set of tools, typically used only when standard commands are not enough. Attaching the Serviceability Agent to a live process can suspend the process during analysis and risks impacting service availability. Prefer testing in a reproduction environment or analyzing a core dump when operational procedures allow. Use appropriate permissions and a JDK compatible with the target JVM.

## 10. GUI Tools: JConsole and VisualVM

### JConsole

**jconsole** is a GUI tool bundled with the JDK. It connects to a JVM via JMX and displays:

- Heap and memory pools.
- Thread counts and thread dumps.
- GC activity.
- MBeans and runtime attributes.

Launch it with:

~~~bash
jconsole
~~~

JConsole is suitable for quick trend observation and inspecting MBeans. It does not replace heap dumps or JFR when deep analysis is required.

### VisualVM

VisualVM supports monitoring processes, threads, heap, sampling, and profiling. VisualVM is distributed separately in modern JDKs; installation and compatible versions depend on your environment.

Both JConsole and VisualVM can connect remotely over JMX if the JVM is configured for it. Remote JMX requires proper authentication and encryption; never expose an unauthenticated management port to a public network.

## 11. Symptom-Based Diagnostic Workflows

### High CPU usage

1. Identify the exact PID with **jps -lv**.
2. Capture several thread dumps with **jcmd <pid> Thread.print -l**, a few seconds apart.
3. Look for RUNNABLE threads with repeated stacks or consistently appearing in the same processing path.
4. Use JFR with the profile setting for a short period to identify CPU-consuming methods.
5. Correlate with OS tools such as top, pidstat, or Process Explorer to see which thread or process is using CPU.

A RUNNABLE thread in a dump does not by itself prove it is the thread causing load. Combine thread dumps, JFR, and CPU metrics.

### Continuously growing heap or suspected memory leak

1. Check the trend with **jstat -gcutil <pid> 1000 10**.
2. Capture histograms at separate times and compare object counts.
3. If you need to identify which objects are being retained, capture a heap dump.
4. Use MAT to inspect Dominator Tree, Retained Heap, and Path to GC Roots.
5. Confirm that the growing objects are genuinely not reclaimed after GC and have unexpected live references.

Heap growth during a high-load period can be normal behavior. The concerning signal is post-GC usage rising steadily across multiple cycles without stabilizing.

### Long or overly frequent GC pauses

1. Use jstat to observe GC frequency and duration.
2. Read GC logs if unified logging is enabled.
3. Capture JFR to correlate GC with allocations, CPU, and lock contention.
4. Check heap size, allocation rate, collector type, and workload.
5. Evaluate pauses alongside actual application latency; total GC time alone does not show the full impact on users.

### Hung application or stuck requests

1. Capture at least three thread dumps over time.
2. Look for deadlocks, lock contention, and exhausted thread pool workers.
3. Check for threads waiting on I/O, databases, network calls, or futures/promises.
4. Correlate stack traces with request logs and timeouts.
5. Identify the thread holding the lock and the chain of work preventing the lock from being released.

### Growing RSS without corresponding heap growth

1. Compare heap usage against process RSS.
2. If NMT was enabled at startup, use **VM.native_memory summary** and **summary.diff**.
3. Check thread counts, stacks, Metaspace, code cache, and direct buffers.
4. If NMT does not explain the increase, inspect native libraries, JNI, and OS observability tools.

## 12. Choosing Tools by Operational Impact

| Tool / operation | Purpose | Operational notes |
|---|---|---|
| jps, VM.version, VM.flags | Process identification and configuration | Usually a low-impact first step |
| Thread.print, jstack | Capture thread stacks | Dumps can be large; take multiple snapshots when investigating hangs |
| jstat | Monitor GC counters | Sampled data; look at trends |
| JFR | Record runtime events | Choose appropriate settings and duration |
| GC.class_histogram | Object statistics by class | May trigger a Full GC depending on version/options |
| GC.heap_dump, jmap dump | Dump the entire heap | Can consume significant disk space and cause substantial pauses |
| jhsdb | Deep JVM analysis | May suspend the process; use only when necessary |

## 13. Diagnostic Checklist

- Record the timestamp, timezone, PID, hostname/container, and JDK version.
- Clearly note the symptom: high CPU, growing heap, GC pauses, deadlock, or request timeouts.
- Start with low-impact commands; only capture a heap dump or use jhsdb when there is a specific reason.
- Save the command line and relevant JVM configuration, and redact secrets before sharing.
- Name files after the service and timestamp to avoid overwriting data across collections.
- Correlate JVM data with application logs, metrics, and OS statistics.
- Record the commands executed, collection duration, and observed impact.
- Restrict access permissions and retention periods for thread dumps, JFR files, and heap dumps because they may contain sensitive data.

## 14. Key Takeaways

- **jcmd** is the versatile starting point for querying a JVM and running many diagnostic commands.
- **Thread dumps** answer what threads are doing at a moment in time; multiple snapshots reveal whether work is progressing or stuck.
- **Histograms** show which classes have many objects; **heap dumps** let you trace references and GC roots.
- **jstat** and GC logs show GC trends; **JFR** connects runtime events along a timeline.
- Process memory is larger than the Java heap; use **NMT** and OS tools when investigating native memory.
- Every conclusion should be backed by multiple sources of evidence and weigh the cost of data collection.