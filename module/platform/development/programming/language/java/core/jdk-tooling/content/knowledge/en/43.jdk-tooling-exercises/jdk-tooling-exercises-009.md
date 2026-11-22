# Diagnosing Java Applications with `jcmd`

This lesson belongs to the **Hands-on Projects** group with the topic **Diagnostics with jcmd**. `jcmd` is a JDK command-line tool used to send diagnostic commands to a JVM running on the same machine. It helps retrieve JVM version and configuration information, thread dumps, heap statistics, class histograms, Native Memory Tracking (NMT), and control Java Flight Recorder (JFR).

This hands-on lab builds a small Java application with a sleeping thread, a thread blocked on acquiring a monitor, and a number of objects retained on the heap. Then, `jcmd` is used to find the right process, inspect the JVM state, collect thread/heap snapshots, record JFR, and read the results. The commands have been verified on Zulu/OpenJDK 24.0.2 running on Windows 11; the sample source is compatible with Java 17+.

## 1. When Should You Use `jcmd`?

Choose `jcmd` when you need to ask a running JVM specific questions:

- Which JDK version, JVM vendor, and command line is this process running?
- Which heap size, GC, or VM flags was the JVM started with?
- Which threads are RUNNABLE, BLOCKED, WAITING, or TIMED_WAITING?
- Which thread is holding a monitor that another thread is waiting for?
- How much used/committed/reserved space does the heap currently have?
- Which classes have the most instances or occupy the most shallow bytes?
- How is the JVM recording allocations, GC, lock contention, or execution samples?
- How is HotSpot native memory allocated across the heap, class metadata, thread stacks, code cache, and other subsystems?

`jcmd` is useful because a single command interface can invoke many diagnostic commands supported by the JVM. It does not perform root-cause analysis on its own. Operators still need to correlate the output with workload, logs, metrics, configuration, and the time of the incident.

## 2. How Does `jcmd` Work?

`jcmd` uses the JVM attach mechanism to send commands to a local Java process. Basic syntax:

~~~text
jcmd <pid | main-class> <command> [arguments]
~~~

Some usage examples:

~~~text
jcmd -l
jcmd 12345 help
jcmd 12345 VM.version
jcmd 12345 Thread.print -l
~~~

- `-l` lists local Java processes recognized by the tool.
- `<pid>` is the process ID of the target JVM.
- `<main-class>` can be used to select a process by its main class, though PID is usually clearer when multiple instances are running on the machine.
- `help` lists the diagnostic commands supported by the target JVM.
- `help <command>` displays the syntax, options, and impact level of a specific command.

The command `jcmd help` is not equivalent to `jcmd <pid> help`: without a PID, `jcmd` may interpret `help` as the main class name to look for and return a process-not-found error.

`jcmd 0 <command>` sends the command to all supported local JVMs. Only use this when you truly intend to affect multiple processes; in this lab, specify a single PID.

## 3. Prerequisites and Access Permissions

To attach successfully, keep the following in mind:

- The target JVM must be running on the same machine as `jcmd`; this tool is not a remote management client over the network.
- The user running `jcmd` usually needs the same effective user and group as the target JVM.
- The JVM must allow attach. `-XX:+DisableAttachMechanism` disables this mechanism.
- Use a JDK that includes `jcmd` in its `bin` directory; a minimal runtime image may not contain diagnostic tools.
- Commands and options depend on the JDK/vendor/version. Always query the target JVM itself with `jcmd <pid> help`.
- Inside containers, run the tool in the same container or matching PID namespace; the PID seen from the host may differ from the PID inside the container.
- PIDs can be reused by the operating system after a process terminates. Run `jcmd -l` again before diagnosing a new process.

If attach fails, do not immediately conclude that the application is dead. Check the process, user, container namespace, permissions, JVM flags, and tool logs.

## 4. A Repeatable Diagnostic Workflow

A practical workflow usually follows this order:

1. Identify the symptom and the time window in which it occurred.
2. Find the right Java process and record its PID, command line, and JDK version.
3. Collect low-intrusiveness JVM information: version, flags, heap info.
4. If threads/locks are suspected, take a thread dump; repeat after a few seconds to see if the state changes.
5. If memory is suspected, check heap info and the class histogram; only create a heap dump when object graph analysis is genuinely needed.
6. If you need to understand behavior over time, record JFR for a short interval and analyze the events.
7. If native memory is suspected, inspect NMT when the JVM was started with this feature enabled.
8. Tie every output to its corresponding timestamp, PID, application version, and workload.

A single snapshot shows the state at one point in time. Multiple snapshots under the same workload help distinguish transient states from sustained trends.

## 5. Creating the Hands-on Project

Create the structure:

~~~text
jcmd-lab/
  src/
    com/
      example/
        diagnostics/
          JcmdLab.java
  out/
~~~

The `JcmdLab.java` file creates four observable signals:

- 48 byte arrays retained on the heap, totaling about 3 MiB of payload.
- `demo-sleeper` periodically in the TIMED_WAITING state.
- `demo-lock-owner` holding a monitor while sleeping.
- `demo-lock-waiter` waiting on that monitor and appearing in the BLOCKED state.

The lock owner releases the monitor on its own after 90 seconds; this is time-bounded lock contention for practice, not a circular deadlock.

## 6. Sample Application Source Code

~~~java
package com.example.diagnostics;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;

public final class JcmdLab {
    private static final Object LOCK = new Object();
    private static final List<byte[]> RETAINED = new ArrayList<>();

    private JcmdLab() {
    }

    public static void main(String[] args) throws InterruptedException {
        for (int i = 0; i < 48; i++) {
            RETAINED.add(new byte[64 * 1024]);
        }

        System.out.println(
                "JCMD_LAB_READY pid=" + ProcessHandle.current().pid());
        System.out.println("RETAINED_ARRAYS=" + RETAINED.size());

        Thread sleeper = new Thread(() -> {
            while (!Thread.currentThread().isInterrupted()) {
                try {
                    Thread.sleep(1000);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "demo-sleeper");
        sleeper.setDaemon(true);
        sleeper.start();

        CountDownLatch ownerReady = new CountDownLatch(1);
        Thread owner = new Thread(() -> {
            synchronized (LOCK) {
                ownerReady.countDown();
                try {
                    Thread.sleep(90_000);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "demo-lock-owner");
        owner.setDaemon(true);
        owner.start();
        ownerReady.await();

        Thread waiter = new Thread(() -> {
            synchronized (LOCK) {
                System.out.println("WAITER_ACQUIRED_LOCK");
            }
        }, "demo-lock-waiter");
        waiter.setDaemon(true);
        waiter.start();

        Thread.sleep(120_000);
    }
}
~~~

`ProcessHandle.current().pid()` has been available since Java 9. `CountDownLatch` ensures the lock owner has acquired the monitor before the waiter starts. `Thread.sleep()` inside the `synchronized` block holds the monitor while sleeping, creating a BLOCKED situation observable via a thread dump.

## 7. Compiling and Running the Application

From the `jcmd-lab` directory, compile for Java 17:

Windows PowerShell:

~~~powershell
javac --release 17 -encoding UTF-8 -Xlint:all -Werror -d out src\com\example\diagnostics\JcmdLab.java
~~~

Linux/macOS:

~~~sh
javac --release 17 -encoding UTF-8 -Xlint:all -Werror -d out src/com/example/diagnostics/JcmdLab.java
~~~

Run the application with Native Memory Tracking in summary mode:

Windows/Linux/macOS:

~~~text
java -XX:NativeMemoryTracking=summary -cp out com.example.diagnostics.JcmdLab
~~~

Initial output looks like:

~~~text
JCMD_LAB_READY pid=58340
RETAINED_ARRAYS=48
~~~

The actual PID varies by machine. Keep this terminal running and open a second terminal to execute `jcmd` commands. The sample application exits automatically after about two minutes; you can stop it early with Ctrl+C in the terminal running the application.

`-XX:NativeMemoryTracking=summary` must be enabled at JVM startup. If this flag is omitted, the `VM.native_memory` command will have no NMT data to report.

## 8. Finding the Right JVM Process

List processes:

~~~text
jcmd -l
~~~

Example:

~~~text
58340 com.example.diagnostics.JcmdLab
~~~

On Windows PowerShell, you can filter processes by main class:

~~~powershell
jcmd -l | Select-String 'com.example.diagnostics.JcmdLab'
~~~

Once the PID is identified, save it to the `$javaPid` variable for subsequent commands:

~~~powershell
$javaPid = 58340
jcmd $javaPid VM.version
~~~

PowerShell has an automatic variable `$PID` containing PowerShell's own process ID. Use the name `$javaPid` to avoid overwriting that automatic variable.

On Linux/macOS, you can retrieve the PID using:

~~~sh
JAVA_PID=$(jcmd -l | awk '/com.example.diagnostics.JcmdLab/ {print $1; exit}')
printf 'Target JVM PID: %s\n' "$JAVA_PID"
~~~

If there are multiple instances with the same main class, verify the command line, working directory, or service identity before choosing a PID. Do not run diagnostic commands against a PID just because it is the first line in the list.

## 9. Discovering Commands Supported by the JVM

List commands:

~~~text
jcmd <pid> help
~~~

View details for a command:

~~~text
jcmd <pid> help Thread.print
jcmd <pid> help GC.heap_dump
jcmd <pid> help JFR.start
~~~

The help output can provide:

- Command description.
- Syntax and options.
- Default values.
- Impact such as Low, Medium, or High.
- Warnings about pauses, GC, or the amount of data that may be generated.

For example, on JDK 24, `GC.heap_dump` is described as High impact and may request a full GC; `JFR.check` and `JFR.dump` are Low impact. `JFR.start` has an impact level that depends on the settings used.

This is an important step before running commands in production. Do not assume a command has the same options or the same impact level across all JDKs.

## 10. Checking Version, Command Line, and VM Flags

Confirm the JVM version:

~~~text
jcmd <pid> VM.version
~~~

View the command line used to start the process:

~~~text
jcmd <pid> VM.command_line
~~~

View current VM flags:

~~~text
jcmd <pid> VM.flags
~~~

This information helps identify:

- JVM vendor/version.
- Main class or JAR being run.
- Classpath/module path.
- `-X` and `-XX` flags.
- Heap sizing, GC collector, and Native Memory Tracking configuration.

You can view system properties:

~~~text
jcmd <pid> VM.system_properties
~~~

System properties and command-line arguments sometimes contain tokens, passwords, connection strings, or sensitive paths. Do not paste raw output into public tickets/chats; filter and redact secret values before sharing.

## 11. Taking a Thread Dump with `Thread.print`

Take a thread dump with stack traces and lock information:

~~~text
jcmd <pid> Thread.print -l
~~~

You can save the output to a file:

Windows PowerShell:

~~~powershell
jcmd $javaPid Thread.print -l > thread-1.txt
~~~

Linux/macOS:

~~~sh
jcmd "$JAVA_PID" Thread.print -l > thread-1.txt 2>&1
~~~

`-l` requests printing information about `java.util.concurrent` locks and synchronizers. `-e` requests extended thread information; check `jcmd <pid> help Thread.print` to confirm the options of the JDK you are using.

In the sample application, look for the threads:

~~~text
"demo-sleeper"
"demo-lock-owner"
"demo-lock-waiter"
~~~

Actual test results show:

~~~text
"demo-lock-waiter" ...
java.lang.Thread.State: BLOCKED (on object monitor)
- waiting to lock <...> (a java.lang.Object)
~~~

The owner thread is in the TIMED_WAITING state because it is sleeping inside the `synchronized` block. The waiter thread is in the BLOCKED state because it is waiting to acquire that monitor.

## 12. Reading Thread States and Identifying Deadlocks

Common states:

| State | Meaning | When to investigate |
|---|---|---|
| RUNNABLE | Thread is running or ready to run; may be in native I/O | Sustained high CPU or stack not making progress |
| BLOCKED | Thread is waiting to enter an intrinsic monitor (`synchronized`) | Multiple threads waiting on the same lock or lock owner is stuck |
| WAITING | Thread is waiting indefinitely for an action from another thread | Unsignaled/unnotified waiters or tasks not completing |
| TIMED_WAITING | Thread is waiting for a bounded time, e.g., `sleep`, `wait(timeout)` | Unusually repeated timeouts or delayed scheduling |
| TERMINATED | Thread has finished | Critical task ended early or no workers remain |

`RUNNABLE` does not necessarily mean a thread is actively consuming CPU; the thread may be in a native call or waiting on I/O. Use JFR/OS metrics to understand CPU usage.

A single BLOCKED thread is not enough to conclude a deadlock. In this example, the owner will wake up and release the monitor after 90 seconds, so the waiter can proceed. A true deadlock typically involves a cycle of lock dependencies: thread A holds lock X and waits for Y, while thread B holds Y and waits for X.

Take at least two thread dumps a few seconds apart:

~~~text
jcmd <pid> Thread.print -l
~~~

Compare thread states, stack traces, monitor owners, and wait locations. If the same thread repeats on the same stack without making progress, correlate it with logs and workload. A thread dump usually includes deadlock information at the end of the output if the JVM detects a Java-level deadlock.

## 13. Inspecting the Heap with `GC.heap_info`

Take a heap snapshot:

~~~text
jcmd <pid> GC.heap_info
~~~

Abbreviated example output:

~~~text
garbage-first heap   total reserved 30932992K, committed 2113536K, used 14963K
region size 16384K, 1 young (16384K), 0 survivors (0K)
Metaspace       used 376K, committed 576K, reserved 1114112K
class space    used 27K, committed 128K, reserved 1048576K
~~~

Meaning:

- **used:** space currently occupied by objects/metadata at the time of the snapshot.
- **committed:** memory the JVM has committed and can use.
- **reserved:** address space the JVM has reserved.
- **Metaspace:** area storing class metadata.
- **Class space:** portion of metaspace dedicated to compressed class pointers when enabled by the JVM configuration.

Numbers vary with heap sizing, GC, class loading, and workload. A single snapshot does not prove a memory leak. Compare multiple times under the same workload and check after natural GC cycles.

## 14. Viewing the Class Histogram with `GC.class_histogram`

Command:

~~~text
jcmd <pid> GC.class_histogram
~~~

Output typically has these columns:

~~~text
num     #instances         #bytes  class name
------------------------------------------------
1:          8581        3526520  [B
2:          1716         212768  java.lang.Class
3:          8455         202920  java.lang.String
~~~

The histogram shows the instance count and total shallow bytes per class. It helps find object types with high counts or large sizes.

In the example, 48 `byte[]` arrays are retained, so the `[B` class appears in the histogram. The class name `[B` is the JVM representation of `byte[]`.

`#bytes` in the histogram is not the retained heap size. It does not account for the entire object graph kept alive by an object. To find which object holds references to most of the heap, you need a heap dump and a dominator/retained-set analysis tool such as Eclipse Memory Analyzer.

`GC.class_histogram` can have High impact depending on heap size and object count. Avoid running it repeatedly in quick succession in production. Check `jcmd <pid> help GC.class_histogram` before using it.

## 15. Taking a Heap Dump with `GC.heap_dump`

A heap dump creates an HPROF file for object graph analysis:

Windows:

~~~powershell
New-Item -ItemType Directory -Force C:\diagnostics | Out-Null
jcmd $javaPid GC.heap_dump C:\diagnostics\heap.hprof
~~~

Linux:

~~~sh
mkdir -p /var/tmp/jvm-diagnostics
jcmd "$JAVA_PID" GC.heap_dump /var/tmp/jvm-diagnostics/heap.hprof
~~~

According to JDK 24 command help, a heap dump has High impact and requests a full GC by default, unless the `-all` option is used. Compression can be requested:

~~~text
jcmd <pid> GC.heap_dump -gz=1 C:\diagnostics\heap.hprof.gz
~~~

Use `-all` when you want to include unreachable objects as well:

~~~text
jcmd <pid> GC.heap_dump -all C:\diagnostics\heap-all.hprof
~~~

A heap dump can be as large as a significant portion of the heap and cause a pause. Check disk space, write permissions, and appropriate timing before creating one.

A heap dump can contain tokens, sessions, passwords, request payloads, user data, and sensitive content residing in memory. Protect the file like production data; restrict access, do not send it publicly, and delete it according to retention policy. This lab does not create a heap dump because it is a high-impact command; the syntax was verified via JVM help.

## 16. Recording JFR from a Running JVM

Java Flight Recorder records events over a period of time. A recording can be started without restarting the application:

~~~text
jcmd <pid> JFR.start name=diagnostic settings=default duration=30s filename=diagnostic.jfr
~~~

- `name=diagnostic` names the recording.
- `settings=default` uses the built-in low-overhead configuration.
- `duration=30s` automatically stops the recording after 30 seconds.
- `filename=diagnostic.jfr` specifies the output file.

Check running recordings:

~~~text
jcmd <pid> JFR.check name=diagnostic
~~~

Output while the recording is active looks like:

~~~text
Recording 1: name=diagnostic duration=30s (running)
~~~

When the duration expires, the JVM writes the file according to the recording configuration. If you run `JFR.check` after the recording has finished, you may receive `No available recordings`; this does not mean the recorded file was lost. Check the file and read it with `jfr summary`.

When more events are needed to investigate over a short interval, you can use:

~~~text
jcmd <pid> JFR.start name=profiled settings=profile duration=15s filename=profiled.jfr
~~~

`profile` collects more data than `default` and has higher overhead. Only use it for short durations, suitable for the application's workload and load tolerance.

## 17. Dumping or Stopping a Recording Manually

If you need a continuous recording and want to actively capture a slice of data:

~~~text
jcmd <pid> JFR.start name=rolling settings=default maxage=15m maxsize=250M
~~~

When a snapshot is needed:

~~~text
jcmd <pid> JFR.dump name=rolling filename=incident.jfr
~~~

After finishing:

~~~text
jcmd <pid> JFR.stop name=rolling
~~~

`JFR.dump` copies the recording contents to a file; `JFR.stop` ends the recording. If `duration` and `filename` are specified directly in `JFR.start`, manual dump/stop is usually unnecessary.

You can request paths to GC roots:

~~~text
jcmd <pid> JFR.dump name=rolling filename=leak-investigation.jfr path-to-gc-roots=true
~~~

Collecting GC root paths can pause the application and take time. Enable it only when investigating a suspected memory leak; do not use it by default for routine recordings.

## 18. Analyzing JFR Files with `jfr`

View a recording summary:

~~~text
jfr summary diagnostic.jfr
~~~

View specific events:

~~~text
jfr print --events jdk.ExecutionSample,jdk.GarbageCollection diagnostic.jfr
~~~

You can also filter lock contention events when the recording captures them:

~~~text
jfr print --events jdk.JavaMonitorEnter diagnostic.jfr
~~~

`jfr summary` displays duration, chunk count, and event counts by type. `jfr print` outputs event contents matching the filter.

Actual events depend on settings, workload, and recording timing. If there are no `jdk.ExecutionSample` events in a short recording, there may have been no significant thread CPU activity during that window or sampling did not capture a matching event. Re-record under a representative workload and check event settings before drawing conclusions.

JFR recordings can contain thread names, class names, command lines, and event payloads. Protect `.jfr` files with appropriate access controls, especially when captured from production.

Java Mission Control (JMC) provides a GUI to filter events and view thread timelines, allocations, GC, and execution samples. JMC may need to be installed separately; `.jfr` files can be read using the `jfr` CLI included in the JDK.

## 19. Native Memory Tracking with `VM.native_memory`

The heap is only part of process memory. The JVM also uses native memory for thread stacks, code cache, class metadata, GC structures, and other subsystems.

To enable NMT, start the JVM with:

~~~text
-XX:NativeMemoryTracking=summary
~~~

Or use `detail` when more detailed allocation call-site information is needed and the additional overhead is acceptable. NMT cannot be enabled retroactively via `jcmd` after the JVM has started.

Get a summary:

~~~text
jcmd <pid> VM.native_memory summary
~~~

Create a baseline:

~~~text
jcmd <pid> VM.native_memory baseline
~~~

After a period of workload, compare:

~~~text
jcmd <pid> VM.native_memory summary.diff
~~~

NMT categorizes reserved/committed native memory by subsystem. It is useful when RSS grows while the Java heap does not grow correspondingly. NMT focuses on allocations tracked by HotSpot; it is not guaranteed to cover every third-party native library allocation or all OS-managed memory.

If the JVM was not started with NMT, the command will report that tracking is not enabled. Add the flag and restart the process on the next run to obtain data.

## 20. Choosing Commands by Impact Level

Impact is published by the JVM in `jcmd <pid> help <command>`. On JDK 24, some commands are classified as follows:

| Command | Impact/usage per JDK 24 help | Purpose |
|---|---|---|
| `VM.version` | Reads JVM metadata | Confirm JVM version |
| `VM.command_line` | Reads JVM metadata | View startup arguments |
| `VM.flags` | Reads JVM metadata | View VM flags |
| `Thread.print` | Medium, depends on thread count | Thread dump |
| `GC.heap_info` | Medium | Heap snapshot |
| `GC.class_histogram` | High, depends on heap/object count | Histogram |
| `GC.heap_dump` | High | HPROF heap dump; requests full GC by default |
| `VM.native_memory` | Medium | NMT summary/detail |
| `JFR.check` | Low | Check recording |
| `JFR.dump` | Low | Export recording |
| `JFR.start` | Medium; depends on settings | Start recording |

This table is a guide for JDK 24; always check help on the actual JVM. For high-impact commands, consider timing, heap size, disk capacity, pause tolerance, and data sensitivity.

## 21. Saving Results and Comparing Over Time

Each diagnostic session should have its own directory:

~~~text
diagnostics/
  incident-2026-11-10/
    environment.txt
    vm-version.txt
    vm-flags.txt
    thread-1.txt
    thread-2.txt
    heap-info.txt
    class-histogram.txt
    recording.jfr
    jfr-summary.txt
~~~

Record:

- Timestamp and timezone.
- PID and main class.
- Application version/build identifier.
- JDK vendor/version.
- Commands run and options.
- Observed symptoms.
- Workload or request rate during collection.
- Results before/after configuration changes.

Do not compare two heap snapshots if the workload or GC timing is completely different without explicitly noting the context. For thread dumps, compare stacks and lock owners. For histograms, check whether class counts/shallow bytes grow continuously. For JFR, examine events within the same time window as the incident.

## 22. Troubleshooting When `jcmd` Does Not Work

### Process not found

**Cause:** the process has terminated, is running under a different user, is in a different container/PID namespace, or `jcmd -l` cannot see it.

**Resolution:** check the process with OS tools, run `jcmd -l` from the right host/container, and verify the new PID.

### `AttachNotSupportedException` or attach failure

**Cause:** user/group mismatch, attach is disabled, the JVM does not support attach in that environment, or the temporary attach directory is inaccessible.

**Resolution:** run as the right user, check `-XX:+DisableAttachMechanism`, container namespace, and filesystem permissions.

### `Unknown diagnostic command`

**Cause:** the command does not exist in the target JVM's JDK/vendor/version.

**Resolution:** run `jcmd <pid> help`, then `jcmd <pid> help <command>` to see supported names and syntax.

### `VM.native_memory` reports not enabled

**Cause:** the JVM was not started with `-XX:NativeMemoryTracking=summary` or `detail`.

**Resolution:** add the flag at launch and restart the process according to the deployment plan; tracking cannot be enabled after the JVM is already running.

### JFR file has not appeared

**Cause:** the recording is still running, a relative path points to the target process's working directory, or the recording has not been dumped/stopped.

**Resolution:** check `JFR.check`, use an absolute path, wait for `duration` to finish, or run `JFR.dump` and check the file.

### Heap dump runs out of space or fails to write

**Cause:** the heap dump is large, the directory lacks disk space, or the user running the JVM lacks write permission.

**Resolution:** choose a filesystem with sufficient space, check permissions, and only create dumps when a proper storage/analysis plan is in place. Do not change the path to a public directory just to bypass permission errors.

### Output is too long

**Cause:** the JVM has many threads/classes or `VM.system_properties` contains many values.

**Resolution:** redirect to a file, filter for the threads/classes of interest, and redact sensitive data before sharing.

## 23. When to Choose Another Tool?

`jcmd` is a good starting point for many questions about a HotSpot JVM, but several tools provide specialized information:

| Tool | Choose when |
|---|---|
| `jps` | Only need to list Java processes |
| `jstack` | Need a thread dump using a standalone tool |
| `jmap` | Need a heap histogram/dump per an existing workflow |
| `jstat` | Need to monitor GC/heap statistics periodically |
| `jconsole` | Need GUI monitoring via JMX |
| `jfr` | Need to read/analyze recordings |
| JMC | Need visual JFR analysis |
| Eclipse Memory Analyzer | Need retained heap, dominator tree, and object references |
| OS tools | Need CPU/RSS/process I/O or native process metrics |

Avoid running multiple tools simultaneously that take the same type of snapshot if they can cause pauses or add load to the JVM. Choose the output that directly answers the question under investigation.

## 24. Hands-on Exercises

After running `JcmdLab`, complete the following exercises:

1. Use `jcmd -l` to find the PID and confirm it with `VM.version`.
2. Use `VM.command_line` to verify `-XX:NativeMemoryTracking=summary`.
3. Run `Thread.print -l` and find `demo-lock-waiter`. Identify the monitor it is waiting on.
4. Take a second thread dump after 10 seconds. Compare whether the waiter is still BLOCKED.
5. Run `GC.heap_info` and record used/committed/reserved.
6. Run `GC.class_histogram`, find `[B`, and correlate it with the 48 byte arrays in the source.
7. Run `VM.native_memory summary`, then `baseline` and `summary.diff`.
8. Record 20 seconds of JFR using `settings=default`, then run `jfr summary`.
9. Use `jfr print` to filter `jdk.ExecutionSample` and `jdk.GarbageCollection`.
10. Explain why a heap histogram does not show which object keeps most of the heap alive.
11. Explain why `demo-lock-waiter` being BLOCKED is not yet a deadlock.
12. Try `jcmd <pid> help GC.heap_dump` and list the risks before performing a heap dump.

When finished, stop the sample application with Ctrl+C in the terminal running Java. Delete the lab diagnostic files if no longer needed; do not delete production incident files before the retention period expires.

## 25. Safe Diagnostics Checklist

- [ ] Identified the correct host/container, PID, and main class.
- [ ] Confirmed JVM version and command line.
- [ ] Checked `jcmd <pid> help` before using unfamiliar commands.
- [ ] Started with metadata and lower-impact snapshots.
- [ ] Compared thread dumps across multiple points in time when needed.
- [ ] Distinguished BLOCKED/WAITING from an actual deadlock.
- [ ] Understood the limitations of heap info and histograms.
- [ ] Created heap dumps only with a clear reason, sufficient space, and an appropriate storage location.
- [ ] Selected JFR settings and duration according to the goal.
- [ ] Enabled Native Memory Tracking from JVM startup.
- [ ] Included timestamp, PID, JDK, and application build with outputs.
- [ ] Reviewed command line, properties, JFR, and heap dumps for sensitive data.
- [ ] Stored and shared diagnostic files with proper access controls.
- [ ] Avoided reusing an old PID after a process restart.

## 26. References

- Oracle JDK 24 — `jcmd`: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html
- Oracle JDK 24 — `jfr`: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jfr.html
- Oracle JDK 24 — `jps`: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jps.html
- Oracle JDK 24 — `jstack`: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jstack.html
- Oracle JDK 24 — `jmap`: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jmap.html
- Oracle JDK 24 — Java Flight Recorder: https://docs.oracle.com/en/java/javase/24/jfapi/flight-recorder-api-programmers-guide.pdf
- Oracle Java Troubleshooting Guide — Diagnostic Tools: https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html
- OpenJDK — Java Mission Control: https://openjdk.org/projects/jmc/
- Eclipse Memory Analyzer: https://eclipse.dev/mat/

`jcmd` turns a running JVM into an inspectable source of evidence: process metadata shows how it was started, thread dumps show where threads are waiting, heap/NMT shows how memory is used, and JFR shows activity over a period of time. Choose commands based on the question, check impact before running, and compare multiple snapshots to reach well-grounded conclusions.