# JVM Debugging: Workflows and Tools

**JVM debugging** is the process of finding why a Java application behaves incorrectly, runs slowly, hangs, consumes abnormal resources, or crashes. Debugging can happen at multiple levels: inspecting code with breakpoints, observing threads and memory of a running JVM, analyzing events over time with Java Flight Recorder (JFR), or investigating a crash dump after a process terminates.

No single command solves every type of issue. An effective approach starts from the symptom, gathers the right evidence, and chooses the least intrusive tool possible. For many diagnostic commands on HotSpot, Oracle recommends using `jcmd` instead of older tools such as `jstack`, `jmap`, and `jinfo`. For source-level logic debugging, use an IDE debugger or `jdb`. For runtime trends, use JFR/JDK Mission Control (JMC), JConsole, and JVM metrics.

## 1. Identify the Issue Type Before Debugging

Before running tools, clearly describe what is happening and when it started. A Java application can encounter several distinct categories of issues:

| Symptom | First Question | Evidence to Collect |
|---|---|---|
| Exception or incorrect result | Which method throws the exception? What input reproduces the bug? | Stack trace, logs with request ID, input, and breakpoints |
| Hung process or unresponsive requests | Are threads running, waiting on locks, or waiting on I/O? | Multiple thread dumps, lock information, JFR |
| High CPU | Which threads/methods are consuming CPU? | JFR execution samples, thread dumps, OS process metrics |
| Growing heap or OutOfMemoryError | Which objects are being retained? | Heap usage, class histogram, heap dump |
| GC pauses or continuous GC | How do allocation rate, live set, and GC time change? | GC logs, JFR, jstat, JMX metrics |
| Growing Metaspace | Which classes are loaded and which classloaders remain alive? | Class-loading metrics, classloader statistics, heap dump |
| JVM or native code crash | Is there a fatal error log or core dump? | `hs_err_pid` log, core dump, native stack, and OS logs |
| Issue only occurs in production | How do environment, configuration, and workload differ from staging? | JDK/version, JVM flags, properties, environment, JFR, and logs |

One symptom can have multiple causes. For example, high CPU may be caused by an infinite loop, tight retries, lock contention, GC pressure, or native code. Do not change heap size or GC flags before having data to support a hypothesis.

## 2. A Repeatable JVM Debugging Workflow

Use the following workflow to avoid collecting excessive unrelated data:

1. **Record the context:** JDK vendor/version, OS, container, PID, JVM arguments, timestamp, workload, and recent deployment changes.
2. **Reproduce or isolate:** identify the request, input, thread, or time window that triggers the issue.
3. **Collect initial evidence:** application logs, exception stack trace, `jcmd -l`, uptime, JVM flags, and system properties.
4. **Choose tools by symptom:** `jdb` for logic; thread dumps for hangs/deadlocks; JFR for CPU/latency/GC; histograms/heap dumps for memory; crash logs/core dumps for JVM/native crashes.
5. **Form a testable hypothesis:** for example, an unbounded cache, thread pool worker exhaustion, a lock held too long, or a method allocating too many objects.
6. **Verify with an appropriate measurement:** compare multiple thread dumps, recordings, or histograms under an equivalent workload.
7. **Fix the root cause and re-verify:** run the same scenario, confirm the symptom disappears, and ensure no regression is introduced.
8. **Document the results:** record commands, timestamps, PID, JDK version, artifacts, and conclusions so others can reproduce the findings.

Avoid changing multiple parameters at once. If you simultaneously increase heap size, switch garbage collectors, expand the thread pool, and modify a cache, it becomes very hard to know which change affected the issue.

## 3. Distinguish Code Debugging from JVM Diagnostics

These activities serve different purposes:

| Activity | Goal | Tools |
|---|---|---|
| Source-level debugging | Pause at a line of code, inspect variables, call stack, and step through execution | IntelliJ IDEA, Eclipse, VS Code Java debugger, `jdb` |
| Runtime diagnostics | Inspect the state of a running JVM without source breakpoints | `jcmd`, `jstat`, JConsole, JFR/JMC |
| Memory analysis | Find classes/objects occupying the heap and references keeping objects alive | `jcmd GC.class_histogram`, heap dump, Eclipse MAT |
| Postmortem analysis | Analyze after a process crashes or stops | `hs_err_pid` log, core dump, `jhsdb`, native debugger |

Breakpoints can pause threads and alter application timing. Runtime diagnostics are usually better suited for observing production. Heap dumps or heap inspection commands can consume significant time, memory, and I/O, so assess their impact before running them.

## 4. Finding the Right JVM Process

Diagnostic tools require the PID or VMID of the target JVM. List Java processes with:

```sh
jcmd -l
```

Or:

```sh
jps -l
```

Example:

```text
24680 com.example.OrderService
25120 com.example.PaymentWorker
```

The PIDs here are illustrative. Match the main class/JAR, command line, service name, or deployment metadata to select the right process.

If JDK tools do not list the process, use OS tools:

Linux/macOS:

```sh
ps -ef
```

Windows PowerShell:

```powershell
Get-Process java, javaw -ErrorAction SilentlyContinue
```

In containers, the PID on the host may differ from the PID inside the container's PID namespace. Run the tool inside the appropriate container or namespace, and use the PID visible in that environment.

`jcmd` must run on the same machine as the target JVM and with an effective user/group ID matching the account that started the JVM. If attach is refused, check the user, namespace, OS permissions, and attach mechanism before switching tools.

## 5. Getting Started with jcmd

`jcmd` sends diagnostic commands directly to a running JVM. Available commands depend on the runtime; query the target JVM instead of assuming every version supports the same command set.

List commands:

```sh
jcmd 24680 help
```

View help for a specific command:

```sh
jcmd 24680 help Thread.print
```

Useful commands:

| Command | Purpose |
|---|---|
| `VM.version` | JVM version |
| `VM.command_line` | Command line used to launch the JVM |
| `VM.flags` | Current JVM flags |
| `VM.system_properties` | Java system properties |
| `VM.uptime` | JVM uptime |
| `Thread.print` | Thread dump and stack traces |
| `GC.heap_info` | Heap information |
| `GC.class_histogram` | Instance histogram by class |
| `GC.heap_dump` | Generate a heap dump |
| `VM.classloader_stats` | Classloader statistics |
| `VM.native_memory summary` | Native memory summary if NMT is enabled |
| `JFR.start` / `JFR.check` / `JFR.dump` / `JFR.stop` | Control Flight Recorder |

Example of collecting basic information:

```sh
jcmd 24680 VM.version
jcmd 24680 VM.uptime
jcmd 24680 VM.command_line
jcmd 24680 VM.flags
```

You can save output to files to attach to an incident report:

```sh
jcmd 24680 VM.flags > vm-flags.txt
jcmd 24680 VM.system_properties > system-properties.txt
```

These files may contain paths, service names, endpoints, or secrets accidentally passed via `-D`. Redact sensitive information before sharing.

## 6. Debugging Logic with jdb

`jdb` is the JDK's reference command-line debugger. It uses the Java Debug Interface (JDI), part of the Java Platform Debugger Architecture (JPDA), to launch or connect to a JVM being debugged.

There are two common approaches:

- Let `jdb` launch the program: convenient for exercises and local environments.
- Launch the JVM with the JDWP agent and attach `jdb`: useful when connecting to a process already prepared for debugging.

View help:

```sh
jdb -help
```

List connectors:

```sh
jdb -listconnectors
```

When using a debugger, source files and debug information allow setting line breakpoints, inspecting local variables, and stepping through methods. Compile with `javac -g` to generate fuller debug information, especially local variable tables.

## 7. Common jdb Commands

| Command | Effect |
|---|---|
| `stop in Class.method` | Set a breakpoint at the start of a method |
| `stop at Class:line` | Set a breakpoint at a source line |
| `clear Class:line` | Remove a breakpoint at a line |
| `run` | Run the program launched by the debugger |
| `cont` | Continue after stopping at a breakpoint/exception |
| `step` | Step into the method called on the next line |
| `next` | Execute the next line without stepping into methods |
| `step up` | Run until the current method returns |
| `where` | Print the call stack of the current thread |
| `where all` | Print the stacks of all threads |
| `locals` | View local variables in the current stack frame |
| `print expression` | Evaluate and print an expression |
| `dump expression` | Print detailed object/expression information |
| `threads` | List threads |
| `thread id` | Select a thread to inspect |
| `catch ExceptionClass` | Stop when a matching exception is thrown |
| `ignore ExceptionClass` | Remove a stop request set by `catch` |
| `help` | View help |
| `quit` | Exit the debugger |

Example of setting a method breakpoint:

```text
stop in com.example.DebugDemo.calculateTotal
```

Line breakpoint:

```text
stop at com.example.DebugDemo:18
```

Line breakpoints depend on line numbers in the compiled source. If the source changes, verify breakpoint positions.

For overloaded methods, you may need to specify parameter types so the debugger selects the right method. `step` and `next` help trace execution flow; `where` shows the call stack to see where a method was called from.

## 8. Java 17+ Example: Finding a Bug with Breakpoints

Suppose there is a discount calculation bug: the program is intended to apply a 10% discount, but the code subtracts a fixed 10 units instead.

Create `src/com/example/DebugDemo.java`:

```java
package com.example;

public class DebugDemo {
    public static void main(String[] args) {
        int result = calculateTotal(3, 450);
        System.out.println("total=" + result);
    }

    static int calculateTotal(int quantity, int unitPrice) {
        int subtotal = quantity * unitPrice;
        int discount = subtotal > 1_000 ? 10 : 0;
        return subtotal - discount;
    }
}
```

Compile with debug information:

```sh
javac -g -d out src/com/example/DebugDemo.java
```

Run normally:

```sh
java -cp out com.example.DebugDemo
```

Stdout:

```text
total=1340
```

If the requirement is a 10% discount, the expected result should be 1215. The program currently returns 1340 because `discount` is 10 instead of 135.

Start the debugger:

```sh
jdb -classpath out com.example.DebugDemo
```

At the `jdb` prompt, set a breakpoint and run:

```text
stop in com.example.DebugDemo.calculateTotal
run
```

When the debugger stops at the method, run:

```text
locals
where
next
print subtotal
next
print discount
```

`locals` shows the parameters and local variables in the current stack frame; `where` shows the call stack. After confirming `subtotal` and `discount`, continue:

```text
cont
quit
```

The application prints `total=1340`. You can fix the formula to `int discount = subtotal > 1_000 ? subtotal / 10 : 0;`, recompile, and run to get `total=1215`.

`jdb` prompts and messages may vary slightly across JDKs, but the program's stdout in both runs is determined by the input data and formula.

## 9. Debugging Exceptions

A stack trace is usually the first piece of evidence when an application throws an exception. Read from the first exception line, find the first frame belonging to application code, and trace backward up the call chain.

Example:

```text
Exception in thread "main" java.lang.NullPointerException
    at com.example.OrderService.calculate(OrderService.java:42)
    at com.example.OrderService.main(OrderService.java:18)
```

Steps:

1. Read the exception type and message.
2. Identify the first class, method, and line number belonging to the application.
3. Inspect inputs, state, and data at the time of failure.
4. Find where an object could become null or state could be mutated.
5. Reproduce with the smallest possible input.
6. Set a breakpoint before the failing line and observe variables.
7. Add a regression test for the failing scenario.

In `jdb`, you can tell the debugger to stop when an exception is thrown:

```text
catch java.lang.NullPointerException
```

Or a specific application exception:

```text
catch com.example.InvalidOrderException
```

The `catch` command makes the debugger stop at the throw site when a matching exception occurs. Use `ignore` to remove that stop request. Avoid catching all exceptions in a large application if doing so causes the debugger to stop constantly and obscure the bug under investigation.

## 10. Debugging a Running Process with JDWP

JDWP (Java Debug Wire Protocol) allows a debugger to communicate with a target JVM. On HotSpot, enable the agent using the `-agentlib:jdwp` option.

Example of starting an application and waiting for a debugger to attach:

```sh
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 -cp out com.example.DebugDemo
```

Parameters:

- `transport=dt_socket`: uses a TCP socket.
- `server=y`: the target JVM opens a socket and waits for a debugger to connect.
- `suspend=y`: the JVM pauses at startup until a debugger attaches.
- `address=127.0.0.1:5005`: listens on the machine's loopback interface at port 5005.

Open a second terminal:

```sh
jdb -attach 127.0.0.1:5005
```

After attaching, set a breakpoint and resume the program:

```text
stop in com.example.DebugDemo.calculateTotal
cont
```

If you want the application to start running before the debugger connects, use `suspend=n`. In that case, breakpoints may miss lines that executed before attaching. Use `suspend=y` when you need to debug from the very start of the program.

To let `jdb` launch the program instead of attaching manually, run directly:

```sh
jdb -classpath out com.example.DebugDemo
```

You do not need `-Xdebug` on modern JDKs; `-agentlib:jdwp` is the standard way to configure the debug agent.

## 11. Securing the JDWP Port

JDWP is a debugger control protocol with very high privileges over the target JVM. Anyone connected can inspect program state, pause threads, read variables, and control execution flow. Do not treat a debug port like an ordinary metrics port.

Security rules:

- Only enable JDWP when genuinely needed.
- For local debugging, bind to loopback such as `127.0.0.1`, not a wildcard address.
- Never expose a debug port to the Internet or untrusted networks.
- If remote debugging is required, prefer an SSH tunnel or VPN; restrict firewalls and connection sources.
- Disable the debug agent after investigation.
- Do not enable `suspend=y` in production without assessing the impact, as the application will wait for a debugger and stop serving requests.
- Do not leave debug ports enabled in default production configurations.

Example of using an SSH tunnel when the JVM on a remote machine is bound to its own loopback interface:

```sh
ssh -L 5005:127.0.0.1:5005 user@server.example
```

Once the tunnel is active, the debugger on the development machine connects to:

```sh
jdb -attach 127.0.0.1:5005
```

The JDWP socket transport is not a JMX endpoint protected by a username and password. An SSH tunnel encrypts the connection and leverages SSH authentication. If an environment requires remote debugging, coordinate with your organization's access control and firewall policies.

## 12. Investigating Hung Processes with Thread Dumps

When requests stop responding, CPU is not necessarily high. The process may be waiting on a lock, waiting on the network, waiting on a database, or deadlocked.

Generate a thread dump:

```sh
jcmd 24680 Thread.print
```

To include lock/synchronizer information:

```sh
jcmd 24680 Thread.print -l
```

You can save it to a file:

```sh
jcmd 24680 Thread.print -l > thread-01.txt
```

For a prolonged hang, capture several thread dumps spaced a few seconds apart, such as 5–10 seconds. Compare the stacks of the same threads across samples:

- An unchanged stack may indicate a thread stuck at a single point.
- Multiple threads waiting on the same lock may indicate lock contention.
- A group of threads waiting on each other may indicate a deadlock.
- A thread pool with all workers waiting on I/O can cause queues to grow.

A thread in `WAITING` or `TIMED_WAITING` is not automatically a bug; idle worker threads normally wait for work. Read the stack frames and lock states before drawing conclusions.

`Thread.print` has an impact proportional to the number of threads. Check `jcmd PID help Thread.print` on the target JVM and avoid taking dumps too frequently in sensitive processes.

## 13. Identifying Deadlocks

A deadlock occurs when threads hold locks that other threads need, forming a wait cycle that cannot resolve on its own.

Logical example:

- Thread A holds Lock 1 and waits for Lock 2.
- Thread B holds Lock 2 and waits for Lock 1.
- Neither thread can proceed to release its lock.

In a thread dump, look for deadlock notices and `waiting to lock`/`locked` sections. JConsole has a Detect Deadlock button. You can use thread dumps from `jcmd` to preserve evidence.

When fixing the code:

- Maintain a consistent acquisition order across multiple locks.
- Keep critical sections short.
- Avoid performing I/O or invoking external callbacks while holding a lock.
- Use `tryLock` with a timeout where appropriate.
- Consider concurrent collections or immutable designs to reduce shared mutable state.

Do not try to solve a deadlock by increasing thread pool size. Adding threads may simply increase the number of stuck threads.

## 14. Investigating High CPU and Latency

If CPU is high:

1. Identify the Java process consuming CPU using OS tools.
2. Record the PID and threads with high CPU time if the OS supports it.
3. Collect a JFR recording or execution samples.
4. Correlate thread IDs with stack traces.
5. Inspect hot methods, loops, retries, serialization, or data-processing code.
6. Check lock contention and GC if CPU is not spent in obvious application methods.

Start JFR on a running JVM:

```sh
jcmd 24680 JFR.start name=cpu-investigation settings=profile duration=2m
```

Check the recording:

```sh
jcmd 24680 JFR.check name=cpu-investigation
```

Dump to a file:

```sh
jcmd 24680 JFR.dump name=cpu-investigation filename=cpu-investigation.jfr
```

Open the file in JDK Mission Control or inspect it with:

```sh
jfr summary cpu-investigation.jfr
```

`profile` collects more detailed data than `default` and can introduce higher overhead. Choose a short duration, assess the impact, and avoid enabling multiple detailed recordings simultaneously.

High CPU can also be caused by GC. Correlate JFR with GC logs, allocation rate, thread count, and OS CPU metrics to distinguish an application hot loop from GC overhead.

## 15. Investigating Growing Heap and OutOfMemoryError

When the heap grows, start by examining heap usage and GC trends. A single snapshot does not prove a memory leak.

Get heap information:

```sh
jcmd 24680 GC.heap_info
```

Generate a class histogram:

```sh
jcmd 24680 GC.class_histogram
```

The histogram shows instance counts and shallow bytes by class. It helps identify notable object groups, but does not show which objects hold references to them.

If you need the object graph, create a heap dump:

```sh
jcmd 24680 GC.heap_dump /var/tmp/order-service.hprof
```

Open the file with Eclipse Memory Analyzer (MAT) or a suitable heap analysis tool. Inspect the dominator tree, retained heap, and path to GC roots to find what retains the objects.

Heap dumps can be very large and are high-impact operations that can cause pauses and require substantial disk space. Check the target JVM's help before running, pick an appropriate time, and protect the file because it may contain business data, tokens, or user information.

For `OutOfMemoryError` caused by the Java heap, you can configure this at startup:

```sh
java -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/var/tmp/heap-dumps -jar app.jar
```

The target path must be writable and have enough free space. Automatic heap dumps do not replace collecting logs and metadata around the time of failure.

## 16. Distinguishing Java Heap from Native Memory

Not every memory issue lives in the Java heap. Process RSS can grow due to:

- Metaspace and compressed class space.
- Thread stacks.
- JIT code cache.
- Direct byte buffers.
- JNI or native libraries.
- Internal JVM and garbage collector structures.

If the heap histogram is stable while RSS continues to grow, inspect native memory and off-heap regions.

Native Memory Tracking (NMT) must be enabled at JVM startup:

```sh
java -XX:NativeMemoryTracking=summary -jar app.jar
```

While running, view the summary:

```sh
jcmd 24680 VM.native_memory summary
```

You can view differences if you have taken a baseline:

```sh
jcmd 24680 VM.native_memory baseline
jcmd 24680 VM.native_memory summary.diff
```

NMT only tracks native allocation categories managed by HotSpot; it does not necessarily cover all allocations made by third-party native libraries. For deeper investigation, combine OS tools and native profilers.

## 17. Investigating GC and Class Loading

For a quick view of GC activity, you can use:

```sh
jstat -gcutil 24680 1000 10
```

Columns such as Eden/Old utilization, young GC count, and full GC count help reveal trends across multiple samples. `jstat` has limitations and its output depends on the JDK and collector; do not parse its output as a stable API.

To view classloader statistics:

```sh
jcmd 24680 VM.classloader_stats
```

To inspect Metaspace:

```sh
jcmd 24680 VM.metaspace
```

If class counts or Metaspace grow continuously, check dynamic proxies, class generation, plugins, redeployments, and classloader lifecycles. Old classloaders may fail to be collected if threads, `ThreadLocal` values, static references, or registries still retain them.

## 18. JConsole and JDK Mission Control

JConsole is a JMX GUI tool included with the JDK. It displays heap/non-heap memory, threads, class loading, CPU, and MBeans. Use JConsole when you need visual observation of a running JVM or want to inspect platform or custom MBeans.

JDK Mission Control (JMC) is a tool suite for analyzing JFR recordings and monitoring JVMs. JMC is typically installed separately and is not bundled with every JDK distribution. Use JMC to view CPU samples, allocations, GC, lock contention, threads, and I/O on a timeline.

| Tool | Strengths |
|---|---|
| JConsole | Observing JMX, memory, threads, classes, and MBeans |
| JMC | Analyzing JFR recordings, event timelines, and profiling |
| `jcmd` | Sending diagnostic commands directly to the JVM |
| `jdb` | Source debugging with breakpoints and stepping |

Avoid using JConsole as a long-running production polling system if frequent MBean queries or operations could alter application state. For long-term investigation, prefer JFR, JMX metrics, and approved observability systems.

## 19. JVM Crashes and Postmortem Debugging

When the JVM crashes, look for a fatal error log typically named:

```text
hs_err_pid24680.log
```

The file location depends on configuration and working directory. You can specify the path with:

```sh
java -XX:ErrorFile=/var/log/java/hs_err_pid%p.log -jar app.jar
```

In the fatal error log, check:

- The signal or exception that caused the crash.
- Current thread and native/Java stack.
- Problematic frame.
- JVM version, OS, and CPU.
- Loaded libraries.
- Command line and VM arguments.
- Memory map or core dump information if available.

If a core dump is available, you can use `jhsdb` and a native debugger such as `gdb` or WinDbg depending on the OS, symbols, and crash type. Commands such as `jhsdb jstack`, `jhsdb jmap`, or `jhsdb clhsdb` can help analyze core files. You need the matching binary/JDK build and the corresponding core dump.

Crashes in native code, JNI, or the JVM may not produce a Java exception. Do not look only for application stack traces; check the `hs_err_pid` log, native libraries, and OS logs.

## 20. JNI and Native Integration

If the application uses JNI or native libraries, you can enable JNI checks at startup:

```sh
java -Xcheck:jni -jar app.jar
```

`-Xcheck:jni` helps detect certain invalid JNI usages, such as incorrect API call sequences or passing invalid references. It can add overhead and produce more logging, so use it purposefully in test environments or targeted investigation sessions.

For more detailed JNI logging, consider `-verbose:jni`, though output can be very large. Do not enable every verbose option at once before identifying what you are looking for.

## 21. Virtual Threads and Debugging

With Java 21, applications can use virtual threads. The number of virtual threads can be very large; a debugger or thread inspection tool that tries to track all of them can create overhead and overwhelm the tooling.

In `jdb`, not all virtual threads are tracked from creation by default. The `-trackallthreads` option requests tracking of all threads, including virtual threads:

```sh
jdb -trackallthreads -classpath out com.example.DebugDemo
```

Enable this only when truly needed. If the number of virtual threads is very large, the debugger may consume substantial resources and the thread list can become unwieldy. Some virtual threads created before attaching may not appear completely depending on timing and debug agent configuration.

When investigating virtual-thread applications, combine JFR, thread dumps, events, and executor/scheduler metrics. Do not assume every virtual thread maps to its own dedicated OS thread.

## 22. Common Errors and Troubleshooting

| Symptom | Common Cause | Resolution |
|---|---|---|
| `jcmd` cannot find the process | Wrong PID, process already stopped, or different PID namespace | Run `jcmd -l`/`jps -l` in the right environment |
| Attach refused | Different user/group, OS permissions, or attach disabled | Run with the matching account and check JVM flags |
| `jdb` cannot find class | Wrong classpath or incorrect package/class name | Check `javac -d` output and pass `-classpath` |
| Breakpoint does not hit | Breakpoint on wrong method/line, class not loaded, or missing debug info | Use `javac -g`, check sourcepath, and verify breakpoint list |
| Cannot view local variables | Compiled without local variable debug info or wrong stack frame | Recompile with `javac -g` and select the right thread/frame |
| JDWP connection refused | Target lacks debug agent, wrong port, or blocked by firewall | Check startup options, port, bind address, and tunnel |
| JVM hangs immediately at startup | JDWP uses `suspend=y` and debugger has not attached | Attach the debugger or switch to `suspend=n` when appropriate |
| Thread dump shows no clear cause | Only one snapshot taken or stacks changing rapidly | Capture multiple dumps and compare the same threads |
| Heap dump fails to generate | Insufficient disk space, missing write permissions, or nonexistent path | Check disk space, permissions, and path on the JVM host |
| Histogram grows without proving a leak | Increased workload or objects still validly in use | Compare live sets multiple times and inspect a heap dump |
| RSS grows while heap is stable | Native/off-heap memory growth | Check NMT, direct buffers, and native libraries |
| JFR missing expected events | Template does not enable the event or threshold not met | Check settings and create an appropriate recording |
| `jhsdb` cannot read core | Mismatched binary/JDK or incompatible core | Use the exact executable and core from the same process/build |
| Debugger makes bug disappear | Breakpoints alter timing/thread scheduling | Use logging, JFR, or a less intrusive profiler |

When a tool fails, verify the target JVM, permissions, namespace, and JDK version first. Do not conclude the application has no bug simply because a diagnostic command failed to attach.

## 23. Choosing Tools by Investigation Question

| Question | Starting Tool |
|---|---|
| Which line of code produces the wrong result? | IDE debugger or `jdb` |
| Where is an exception thrown? | Stack trace, breakpoints, `catch` in `jdb` |
| What are threads doing? | `jcmd Thread.print -l` |
| Is there a deadlock? | Thread dump, JConsole Detect Deadlock |
| Which methods consume CPU? | JFR/JMC or a profiler |
| Which classes occupy the most heap? | `jcmd GC.class_histogram` |
| Which objects retain heap memory? | Heap dump + MAT dominator tree/path to GC roots |
| Is GC causing latency? | JFR, GC logs, `jstat`, JMX |
| Why is Metaspace growing? | `VM.classloader_stats`, `VM.metaspace`, heap dump |
| Is RSS growing outside the heap? | NMT and native OS tools |
| Did the JVM crash in native code? | `hs_err_pid` log, core dump, `jhsdb`, native debugger |

Choosing tools based on the specific question reduces overhead and produces easier-to-interpret evidence.

## 24. Checklist for a JVM Debugging Session

- [ ] Recorded JDK vendor/version, OS, container, PID, and JVM arguments.
- [ ] Identified the symptom and when it started.
- [ ] Saved application logs, exception stack traces, and request/correlation IDs.
- [ ] Used `jcmd -l` or `jps -l` to identify the right JVM.
- [ ] Checked `jcmd PID help` before running unfamiliar commands.
- [ ] Selected source-level debugging or runtime diagnostics based on the question.
- [ ] Captured multiple thread dumps when investigating hangs/deadlocks.
- [ ] Used JFR when a timeline of CPU, GC, locks, or I/O was needed.
- [ ] Used histograms/heap dumps when memory analysis was needed.
- [ ] Checked native memory if RSS did not match Java heap usage.
- [ ] Protected heap dumps, JFR files, and diagnostic output.
- [ ] Avoided exposing JDWP debug ports on untrusted networks.
- [ ] Assessed impact before running heap dumps or high-impact commands.
- [ ] Fixed the root cause and re-ran the same workload to verify.

## 25. References

- Oracle JDK 21 Troubleshooting Guide — Diagnostic Tools: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- Oracle JDK 21 Tool Reference — The `jcmd` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle JDK 21 Tool Reference — The `jdb` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdb.html
- Java Platform Debugger Architecture — Connection and Invocation Details: https://docs.oracle.com/en/java/javase/21/docs/specs/jpda/conninv.html
- Oracle Java SE 21 Management Guide — JConsole: https://docs.oracle.com/en/java/javase/21/management/using-jconsole.html

Effective JVM debugging starts by classifying the symptom and gathering the right kind of evidence. Use `jdb` for source logic, `jcmd` and thread dumps for process state, JFR/JMC for performance over time, heap dumps for object retention, and `hs_err_pid`/core dumps for crashes. Assess impact and protect diagnostic data, especially when enabling JDWP or collecting heap dumps in production.
