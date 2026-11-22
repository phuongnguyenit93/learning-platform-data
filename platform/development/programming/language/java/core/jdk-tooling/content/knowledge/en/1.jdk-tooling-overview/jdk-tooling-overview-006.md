# Runtime Tools in the JDK

Runtime tools help observe a running JVM: which classes a process is executing, where threads are waiting, how the heap and garbage collector (GC) are behaving, or where execution time is concentrated in the code. This group of tools is essential when an application is already running but exhibits slowdowns, hangs, memory growth, or unexpected behavior.

Most command-line tools are located in the JDK's **bin** directory. They typically connect to a local JVM via the Attach mechanism. For most diagnostic scenarios, start with **jcmd**, then choose a specialized tool based on the type of data you need to observe.

## 1. Choosing a Tool by Goal

| Need | Tool to Start With | Data Collected |
|---|---|---|
| Find a Java process | **jcmd -l** or **jps** | PID, main class, or running JAR |
| View JVM configuration | **jcmd** with **VM.flags** and **VM.command_line** | JVM flags and launch command line |
| Investigate hung threads | **jcmd** with **Thread.print** or **jstack** | Thread states, stack traces, locks held or awaited |
| Monitor GC | **jstat** | Counters and usage of heap regions across multiple samples |
| Inspect the heap | **jcmd** with **GC.heap_info** or **GC.class_histogram** | Heap info and object counts by class |
| Deep memory analysis | **jcmd GC.heap_dump** or **jmap** | Heap dump file for offline analysis |
| Time-based performance profiling | JDK Flight Recorder (JFR) and the **jfr** command | GC events, threads, allocations, CPU sampling, and JVM events |
| GUI observation | **jconsole** | Charts and MBeans via JMX |
| Low-level analysis | **jhsdb** | Serviceability Agent data from a process or core dump |

You do not need to run all tools at once. Define the question you need to answer first, collect the least intrusive data, and only then move on to heavier operations such as a heap dump.

## 2. Finding the Right JVM Process

Before sending diagnostic commands, you need to identify the exact PID of the application. Two commonly used commands are:

~~~bash
jcmd -l
jps -lmv
~~~

- **jcmd -l** lists local JVMs that the tool can detect, usually along with their PID and main class.
- **jps** lists JVMs discovered by the tool. The **-l** option displays the full class name or JAR path, **-m** displays arguments passed to the main method, and **-v** displays JVM arguments.

For example, the output might contain a line like:

~~~text
18420 com.example.orders.OrderApplication
~~~

In this example, **18420** is the PID to use for subsequent commands. The PID changes on every launch, so do not copy a PID from an older run. If the machine runs multiple Java applications, verify the class name, JAR, and launch arguments to avoid targeting the wrong process.

## 3. jcmd — The Starting Point for JVM Diagnostics

**jcmd** sends diagnostic commands to a running JVM. The available commands depend on the JVM version and environment, so it is best to query the target process itself first:

~~~bash
jcmd <pid> help
jcmd <pid> help Thread.print
~~~

Some commonly useful commands:

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> VM.system_properties
jcmd <pid> Thread.print
jcmd <pid> GC.heap_info
~~~

Meaning:

- **VM.version** reports the version of the running VM.
- **VM.command_line** displays the command line used to launch the JVM.
- **VM.flags** displays the current VM flags, useful for checking heap size, GC, or runtime options.
- **VM.system_properties** displays system properties. The output may contain internal paths or sensitive information; review it before sharing logs.
- **Thread.print** prints stack traces of Java threads, along with states such as RUNNABLE, BLOCKED, WAITING, or TIMED_WAITING.
- **GC.heap_info** provides an overview of the heap and memory regions managed by GC.

To view additional information about synchronization locks, use:

~~~bash
jcmd <pid> Thread.print -l
~~~

To view object counts and total memory usage by class:

~~~bash
jcmd <pid> GC.class_histogram
~~~

A histogram helps identify which classes account for the most objects or memory. However, this operation can noticeably impact the application depending on heap size and JVM state.

When you truly need a heap snapshot, you can instruct the JVM to generate a heap dump:

~~~bash
jcmd <pid> GC.heap_dump /absolute/path/heap.hprof
~~~

An **.hprof** file can be very large. Generating a dump can cause pauses and consume disk space; make sure the destination has enough free space and protect the file, as it may contain data currently held in application memory.

A special case is native memory. The following command only provides data if Native Memory Tracking (NMT) was enabled at JVM startup:

~~~bash
jcmd <pid> VM.native_memory summary
~~~

You can enable NMT when starting the JVM with flags such as **-XX:NativeMemoryTracking=summary** or **-XX:NativeMemoryTracking=detail**. It cannot be enabled retroactively on a JVM that was started without NMT.

## 4. jstat — Monitoring GC with Consecutive Samples

**jstat** reads JVM counters and metrics periodically. For example:

~~~bash
jstat -gcutil <pid> 1000 10
~~~

This command samples every 1,000 milliseconds for 10 iterations. The **-gcutil** option displays the utilization percentage of heap regions along with several GC counters. You can use **-gc** to view capacity values instead of percentages:

~~~bash
jstat -gc <pid> 1000 10
~~~

Common columns include:

- **S0, S1**: utilization of the Survivor spaces.
- **E**: utilization of Eden.
- **O**: utilization of the Old Generation.
- **M**: utilization of Metaspace.
- **YGC, YGCT**: count and total time of Young GC.
- **FGC, FGCT**: count and total time of Full GC.
- **GCT**: total recorded GC time.

Column names and formatting may vary by JDK version or garbage collector. Use the headers returned by the command itself to interpret the output.

A single sample is rarely enough to draw a conclusion. Watch the trend: is the Old Generation growing continuously, is GC occurring more frequently, is total GC time rising rapidly, and does the heap recover after GC? For example, an Old Generation that grows across multiple samples and does not drop after GC cycles may indicate a need to inspect objects held by long-lived references. On its own, it does not prove a memory leak; combine it with a histogram, heap dump, or JFR.

## 5. jstack, jmap, and jinfo

These are well-known diagnostic tools in the JDK. Many of their tasks can now be performed with **jcmd**, but it is still useful to know how to read the older commands when encountering documentation or operational runbooks that use them.

### jstack — Capturing a Thread Dump

~~~bash
jstack -l <pid>
~~~

**jstack** prints stack traces of threads in the JVM. The **-l** option adds information about synchronization locks. A thread dump is useful when:

- Multiple threads are in the BLOCKED state waiting on the same monitor.
- A thread remains in the WAITING or TIMED_WAITING state for a long time.
- Request-handling threads repeatedly appear at the same stack frame.
- You need to check for signs of a deadlock.

With modern JDKs, you can start with **jcmd <pid> Thread.print -l**. When suspecting an application hang, take multiple thread dumps a few seconds apart. Comparing snapshots helps distinguish threads that are simply waiting normally from threads stuck at the exact same location.

### jmap — Viewing a Histogram or Creating a Heap Dump

~~~bash
jmap -histo:live <pid>
jmap -dump:live,format=b,file=heap.hprof <pid>
~~~

**-histo:live** lists classes and live object counts after the JVM determines which objects are collectible. The **-dump** option creates a binary heap dump for analysis with a heap dump reader tool.

These operations can trigger GC or significant pauses, especially with large heaps. In modern workflows, prefer the corresponding **jcmd** commands and only create a heap dump once you have planned for disk space, execution time, and file storage location.

### jinfo — Viewing Flags and System Properties

~~~bash
jinfo -flags <pid>
jinfo -sysprops <pid>
~~~

**jinfo** displays the JVM flags and system properties of a process. If you only need to read information, **jcmd <pid> VM.flags** and **jcmd <pid> VM.system_properties** are usually more convenient. Some **jinfo** options can modify runtime flags; do not use modifying options when your goal is strictly observation.

## 6. Java Flight Recorder and the jfr Command

Java Flight Recorder (JFR) records JVM events over time, such as execution sampling, GC, thread activity, memory allocation, and other runtime events. JFR is especially useful when you need to find the root cause of a performance issue rather than just viewing state at a single point in time.

You can start a short recording with **jcmd**:

~~~bash
jcmd <pid> JFR.start name=incident settings=profile duration=60s filename=runtime.jfr
~~~

The command above instructs the JVM to record for 60 seconds and save the output to **runtime.jfr**. **settings=profile** collects more detailed data, suitable for a short investigation window. For longer recordings, consider the **default** configuration to reduce data volume and overhead.

You can check running recordings:

~~~bash
jcmd <pid> JFR.check
~~~

If a recording was started without a duration, you can explicitly dump or stop it:

~~~bash
jcmd <pid> JFR.dump name=incident filename=runtime.jfr
jcmd <pid> JFR.stop name=incident
~~~

Once you have the file, use the **jfr** tool for offline analysis:

~~~bash
jfr summary runtime.jfr
jfr print --events jdk.ThreadSleep,jdk.GarbageCollection runtime.jfr
~~~

**jfr summary** summarizes the recording and event types. **jfr print** prints event data; the **--events** filter narrows the output to the events you want to inspect. For large recordings, filter events or redirect output to a file for easier analysis.

JFR helps you see how behavior unfolds over time. For example, GC events show the timing and duration of collections; execution sampling events help identify stacks that frequently appear when CPU is busy. Correlate the results with the timestamps of user error reports, system load, and application logs. JFR files can also contain class names, stack traces, paths, or environment details; store and share them with appropriate access controls.

## 7. jconsole — Observing the JVM via JMX

**jconsole** is a graphical tool that uses Java Management Extensions (JMX). It can display:

- JVM overview, uptime, and memory usage.
- Heap and GC activity charts.
- Thread list and thread details.
- Loaded class counts.
- MBeans exposed by the JVM or the application.

Run the following command to launch the UI:

~~~bash
jconsole
~~~

It can connect to local Java processes that it discovers. For remote processes, JMX must be configured on the target application. Remote connections must use proper authentication and transport security; never expose an unauthenticated JMX port to a public network. JConsole is convenient for visual observation, whereas **jcmd** and JFR are better suited for collecting command-line data that can be saved and compared.

## 8. jhsdb — Low-Level Analysis

**jhsdb** is the Serviceability Agent tool for deep investigation scenarios, such as analyzing a core dump or internal JVM structures. Several modes can extract stacks or heap information:

~~~bash
jhsdb jstack --pid <pid>
jhsdb jmap --heap --pid <pid>
~~~

This is not the first choice for routine diagnostics. Attaching the Serviceability Agent to a running JVM can pause the process during analysis and noticeably impact the application. Use it only when higher-level tools cannot answer the question, you understand the impact, and you have the necessary permissions on the process.

## 9. Symptom-Based Investigation Workflows

### Application Responds Slowly or Appears Hung

1. Use **jcmd -l** or **jps -lmv** to identify the right PID.
2. Capture a thread dump with **jcmd <pid> Thread.print -l**.
3. Repeat after a few seconds and compare the stacks. Look for BLOCKED threads, monitor owners, deadlocks, or groups of RUNNABLE threads consistently at the same code location.
4. If the issue is CPU-related, record JFR during the incident window and inspect execution sampling events.

A WAITING thread is not necessarily a bug: worker threads in a thread pool normally wait for work when the system is idle. Evaluate thread states, stacks, thread counts, and incident timing together in context.

### Heap Growth or Suspected Memory Leak

1. Check the overview with **jcmd <pid> GC.heap_info**.
2. Use **jstat -gcutil <pid> 1000 10** to observe heap utilization trends and GC activity.
3. If you need to identify classes consuming the most memory, capture **GC.class_histogram** and compare snapshots.
4. When you need to trace references, generate a heap dump and analyze it offline.

Memory leaks in Java typically occur when objects are no longer needed but are still retained by a live reference. A histogram only shows counts and sizes by class; a heap dump provides the reference graph needed to trace which objects are holding onto others.

### Frequent GC or Long Pauses

1. Use **jstat** to inspect GC counters and heap region utilization across multiple samples.
2. Use JFR to examine the timing, duration, and types of GC events.
3. Correlate with request load, allocation rate, and heap configuration.
4. Adjust JVM flags only after gathering evidence of the root cause and understanding the impact of the change.

Do not draw conclusions from a single Full GC or a single heap percentage value. Look at trends, frequency, pause durations, and memory reclamation effectiveness.

### Suspected Native Memory Growth

If the heap is not growing correspondingly while total process memory keeps increasing, check native areas such as thread stacks, code cache, or native allocations. When the JVM was started with NMT enabled, run:

~~~bash
jcmd <pid> VM.native_memory summary
~~~

NMT provides visibility into native allocation categories tracked by the JVM. It does not replace OS-level monitoring tools and cannot account for all native memory allocated by external libraries.

## 10. Hands-On Example with Java 17+

The following program retains a small amount of data on the heap, creates a clearly named thread, and waits so you have time to observe it. It has no external library dependencies.

Create the file **RuntimeToolsDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;

public class RuntimeToolsDemo {
    private static volatile List<byte[]> retained;

    public static void main(String[] args) throws InterruptedException {
        retained = new ArrayList<>();
        for (int i = 0; i < 8; i++) {
            retained.add(new byte[1024 * 1024]);
        }

        Thread worker = new Thread(() -> {
            while (!Thread.currentThread().isInterrupted()) {
                try {
                    Thread.sleep(1_000);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "demo-worker");
        worker.start();

        System.out.println("PID=" + ProcessHandle.current().pid());
        System.out.println("Ready for diagnostics.");
        new CountDownLatch(1).await();
    }
}
~~~

Compile and run in the first terminal:

~~~bash
javac RuntimeToolsDemo.java
java RuntimeToolsDemo
~~~

The program prints the JVM's own PID and keeps the process alive:

~~~text
PID=<PID of the current process>
Ready for diagnostics.
~~~

The PID value changes on each run. Open a second terminal and replace **<PID>** with the printed value:

~~~bash
jcmd <PID> VM.version
jcmd <PID> Thread.print -l
jcmd <PID> GC.heap_info
jstat -gcutil <PID> 1000 5
~~~

In the thread dump, look for the thread named **demo-worker**. This thread is usually in the TIMED_WAITING state because it is sleeping in **Thread.sleep**. This is the expected state for the example, not a deadlock.

You can record JFR for 30 seconds:

~~~bash
jcmd <PID> JFR.start name=demo settings=profile duration=30s filename=runtime-demo.jfr
~~~

After the recording finishes, analyze the file:

~~~bash
jfr summary runtime-demo.jfr
jfr print --events jdk.ThreadSleep,jdk.GarbageCollection runtime-demo.jfr
~~~

If running in a real environment, replace the filename with an absolute path to a directory where the JVM process has write permissions. Stop the demo program with Ctrl+C in the first terminal.

## 11. Safe Operating Principles

- **Identify the exact process:** always verify the PID against the class name, JAR, and launch arguments before sending commands.
- **Proper permissions and environment:** Attach typically requires the tool to run on the same host and under the same effective user as the target JVM. In containers, the PID namespace may differ from the host; when needed, run the tool inside the container itself or use the PID visible inside the container.
- **Check Attach availability:** a JVM may be launched with **-XX:+DisableAttachMechanism**, or the security environment may block Attach. In that case, commands cannot connect even with the right PID.
- **Prefer compatible tools:** use a JDK version compatible with the target JVM; check **help** on the target process itself to see which commands are supported.
- **Assess impact:** thread dumps are generally lighter than heap dumps, histograms, or forced GC operations. Avoid repeatedly running heavy commands on systems under high load.
- **Prepare storage:** heap dumps and JFR files can be large. Check disk space, write permissions, and retention policies before generating files.
- **Protect diagnostic data:** heap dumps may contain in-memory application data; system properties, command lines, JFR files, and thread dumps can also expose internal information. Never upload them to public locations or share them raw without reviewing them first.

A good workflow starts with a specific question, chooses a low-impact tool, captures data from the time of the incident, and compares multiple samples. Use **jcmd** for JVM state, **jstat** for GC trends, JFR for performance timelines, and heap dumps when deep reference tracing is needed.
