# The jcmd Command: Diagnosing a Running JVM

## 1. What is jcmd?

`jcmd` is a command-line tool included with the JDK for sending diagnostic commands to a running Java Virtual Machine (JVM) on the local machine. You can query the JVM for its version, startup arguments, flags, heap, threads, native memory, and Java Flight Recorder (JFR) recordings.

Unlike `javac` or `java`, `jcmd` typically interacts with an already running Java process. The tool sends a request to the target JVM; the JVM itself executes the command and returns the result.

Common use cases:

- Identify running Java processes and their JVM versions.
- Inspect startup commands, classpath, and VM flags.
- Capture thread dumps to investigate deadlocks or long-waiting threads.
- Inspect heap and native memory usage.
- Collect JFR recordings for performance analysis.
- Check which diagnostic commands a specific JVM supports.

`jcmd` is a diagnostic tool for the host running the JVM. It is not a remote process management tool over the network, nor does it replace a profiler, logging, metrics, or application testing.

## 2. Syntax and Finding JVMs

General syntax:

~~~bash
jcmd <pid | main-class> <command> [arguments]
~~~

Where:

- `pid` is the process ID of the JVM.
- `main-class` is the main class name used to launch Java; the tool can match the full or partial name.
- `command` is a diagnostic command supported by the target JVM.
- `arguments` are options specific to that command.

View tool help:

~~~bash
jcmd -h
~~~

List JVMs on the machine:

~~~bash
jcmd -l
~~~

If no options are passed, `jcmd` also lists Java processes, equivalent to `jcmd -l`.

Example output:

~~~text
24816 demo.DiagnosticsTarget
39120 jdk.jcmd/sun.tools.jcmd.JCmd -l
~~~

In this example, `24816` is the PID of the application to inspect. The actual PID changes with each run.

Once you have the PID, view the commands supported by the target JVM:

~~~bash
jcmd 24816 help
~~~

View the syntax and impact level of a specific command:

~~~bash
jcmd 24816 help Thread.print
jcmd 24816 help GC.heap_dump
jcmd 24816 help JFR.start
~~~

The list of commands depends on the JDK version, JVM implementation, and process configuration. Always run `help` against the target JVM itself before executing an unfamiliar command.

## 3. Continuous Java Example for Practicing jcmd

Create the file `src/demo/DiagnosticsTarget.java`:

~~~java
package demo;

/** A small process for practicing local JVM diagnostics. */
public final class DiagnosticsTarget {
    /**
     * Keeps the JVM alive for local inspection.
     *
     * @param args command-line arguments
     * @throws InterruptedException if the wait is interrupted
     */
    public static void main(String[] args) throws InterruptedException {
        System.out.println("READY");
        while (true) {
            Thread.sleep(1000);
        }
    }
}
~~~

Compile the source compatible with Java 17:

~~~bash
javac --release 17 -d out src/demo/DiagnosticsTarget.java
~~~

Open Terminal 1 and run:

~~~bash
java -cp out demo.DiagnosticsTarget
~~~

Exact stdout:

~~~text
READY
~~~

The process continues running and waiting. Keep Terminal 1 open so the JVM stays alive.

Open Terminal 2 and list the processes:

~~~bash
jcmd -l
~~~

Find the line containing `demo.DiagnosticsTarget`, note the actual PID, and run:

~~~bash
jcmd 24816 VM.version
jcmd 24816 VM.command_line
jcmd 24816 GC.heap_info
jcmd 24816 Thread.print -l
~~~

Replace `24816` with the PID displayed on your machine. When finished, return to Terminal 1 and press Ctrl+C to stop the program.

This example is only for practicing on a process you launched yourself. When inspecting another application, verify the correct PID and access permissions before sending commands.

## 4. Viewing JVM Information and Startup Arguments

Some basic commands:

| Command | Information |
|---|---|
| `VM.version` | JVM and JDK version |
| `VM.uptime` | Time the JVM has been running |
| `VM.command_line` | Startup command and arguments |
| `VM.flags` | Current VM flags |
| `VM.system_properties` | System properties |
| `PerfCounter.print` | Performance counters exposed by the JVM |

Examples:

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.uptime
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
~~~

`VM.command_line` helps verify which classpath, main class, or arguments the JVM is running with. `VM.flags` shows which VM options—such as the garbage collector and heap sizing—are in effect.

`VM.system_properties` may display paths, environment names, or sensitive configuration values. Command-line arguments can also sometimes contain tokens or passwords due to misconfigured applications. Do not post raw output to tickets or public chats without reviewing and redacting sensitive data.

## 5. Inspecting Heap and Garbage Collection

### GC.heap_info

View an overview of the Java heap:

~~~bash
jcmd <pid> GC.heap_info
~~~

The output typically includes reserved, committed, and used heap, along with regions or generations depending on the garbage collector. This is a point-in-time snapshot when the command runs; it is not a continuous metric and does not by itself explain why memory is growing.

### GC.class_histogram

Display instance counts and memory usage by class:

~~~bash
jcmd <pid> GC.class_histogram
~~~

The results can help identify classes occupying the most heap space. However, this command is marked **Impact: High** by the JVM; its cost depends on the size and contents of the heap. Do not run it repeatedly in production just to collect metrics.

### GC.heap_dump

Create a heap dump in HPROF format:

~~~bash
jcmd <pid> GC.heap_dump /var/tmp/application-heap.hprof
~~~

A heap dump is useful for analyzing memory leaks or object retention with tools such as Java Mission Control or Eclipse MAT. The JVM marks this command **Impact: High** and may trigger a full GC before dumping unless the `-all` option is used.

Heap dumps can be very large, increase disk I/O, and contain sensitive in-memory data such as personal information, tokens, or request payloads. Check available disk space, file permissions, and data policies before creating or sharing one.

### GC.run

~~~bash
jcmd <pid> GC.run
~~~

This command invokes `System.gc()`. It is not a fix for memory leaks; a full GC can pause the application and does not guarantee freeing objects that are still referenced. Use it only when you have a specific diagnostic goal.

## 6. Capturing Thread Dumps with Thread.print

A thread dump shows which threads are running, waiting on monitors, waiting on conditions, or blocked at the time of capture.

Basic command:

~~~bash
jcmd <pid> Thread.print
~~~

Include additional lock information:

~~~bash
jcmd <pid> Thread.print -l
~~~

Sample output excerpt:

~~~text
"main" #1 prio=5 os_prio=0
   java.lang.Thread.State: TIMED_WAITING (sleeping)
    at java.lang.Thread.sleep(Native Method)
    at demo.DiagnosticsTarget.main(DiagnosticsTarget.java:12)
~~~

Common thread states:

| State | General Meaning |
|---|---|
| RUNNABLE | Thread is running or ready to run in the JVM |
| BLOCKED | Waiting to acquire an intrinsic monitor |
| WAITING | Waiting for another thread or condition |
| TIMED_WAITING | Waiting with a time limit |
| TERMINATED | Thread has finished execution |

When investigating a deadlock or hung requests:

1. Capture a thread dump.
2. Wait a short interval appropriate to the incident.
3. Capture one or two additional dumps.
4. Compare stack traces, thread states, and locks across dumps.
5. Look for threads with unchanged stacks, long-held locks, or circular wait chains.

A single dump is only a snapshot at one point in time. Comparing multiple dumps helps distinguish threads doing normal work from threads that are stuck. `Thread.print` has a Medium impact level, and its cost depends on the number of threads.

## 7. Tracking Native Memory with Native Memory Tracking

The Java heap is not all the memory used by a JVM process. The JVM also uses native memory for metaspace, thread stacks, code cache, GC structures, and other runtime components.

`VM.native_memory` displays Native Memory Tracking (NMT) data:

~~~bash
jcmd <pid> VM.native_memory summary
~~~

NMT must be enabled when the JVM starts. For example:

~~~bash
java -XX:NativeMemoryTracking=summary -jar application.jar
~~~

You can use `detail` mode to collect more granular information at the cost of higher tracking overhead.

If NMT is not enabled, the command may return:

~~~text
Native memory tracking is not enabled
~~~

NMT cannot be enabled for the first time via `jcmd` after the application has started. You must restart the JVM with the appropriate flag.

You can take a baseline and compare changes:

~~~bash
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary.diff
~~~

NMT reflects native memory regions tracked by HotSpot; it should not be treated as a complete measurement of all native allocations managed by external libraries or the operating system.

## 8. Recording Java Flight Recorder with jcmd

Java Flight Recorder (JFR) collects JVM and application events to analyze CPU usage, allocations, GC, threads, locks, I/O, and more.

Start a time-bounded recording:

~~~bash
jcmd <pid> JFR.start name=diagnostic settings=default duration=60s filename=diagnostic.jfr
~~~

Check recordings:

~~~bash
jcmd <pid> JFR.check
~~~

Dump a snapshot while a recording is running:

~~~bash
jcmd <pid> JFR.dump name=diagnostic filename=diagnostic-snapshot.jfr
~~~

Stop a recording by name:

~~~bash
jcmd <pid> JFR.stop name=diagnostic
~~~

Key points:

- `settings=default` uses a lower-overhead collection profile suitable for longer monitoring.
- `settings=profile` collects more data but may increase overhead; suitable for short profiling sessions.
- `duration=60s` automatically stops the recording after the specified duration.
- The recording file is written using the permissions and working directory of the target JVM process; choose a path the process can write to.
- `JFR.start` has a Medium impact level (`Impact: Medium`); check `help JFR.start` for options supported by your current JDK.

You can open `.jfr` files with Java Mission Control or a compatible JFR analysis tool. A recording captures events during the collection window; record the timestamp and workload to correlate with observed symptoms.

## 9. Changing VM Flags at Runtime

`VM.flags` displays the flags currently in effect:

~~~bash
jcmd <pid> VM.flags
~~~

Some JVMs allow changing manageable flags at runtime using:

~~~bash
jcmd <pid> VM.set_flag <flag-name> <value>
~~~

Not all flags can be modified after JVM startup. `help VM.set_flag` describes the syntax, while modifiability depends on the specific flag and JVM.

Changing flags can alter GC, memory, compiler, or runtime behavior. Understand the impact, record the original value, and have a rollback plan. For critical configuration changes, updating startup flags for the next restart is usually easier to control and reproduce.

## 10. Diagnostic Command Impact Levels

Each command has a different cost. You can check the impact level with:

~~~bash
jcmd <pid> help <command>
~~~

On JDK 24.0.2, several impact levels are reported as follows:

| Command | Reported Impact | Notes |
|---|---|---|
| `VM.version` | Low | Version information |
| `JFR.check` | Low | Inspect active recordings |
| `JFR.dump` | Low | Copy recording data |
| `Thread.print` | Medium | Depends on thread count |
| `GC.heap_info` | Medium | Reads heap state |
| `VM.native_memory` | Medium | Depends on NMT configuration |
| `JFR.start` | Medium | Depends on event settings |
| `GC.class_histogram` | High | Depends on heap size |
| `GC.heap_dump` | High | May trigger a full GC and heavy I/O |

Impact levels are informational estimates provided by the JVM, not guarantees of fixed pause times. The same command can incur different overhead on applications with different heap sizes, thread counts, or workloads.

Before running a command in production:

- Read `help <command>` to check syntax and impact.
- Define your diagnostic goal and timing.
- Check CPU, heap, disk space, and output storage capacity.
- Avoid running high-impact commands repeatedly in automated loops.
- Log the timestamp, PID, and executed command to correlate with metrics.

## 11. Permissions and the Attach Mechanism

`jcmd` must be able to attach to the target JVM. Common requirements include:

- The Java process must be on a host the tool can attach to.
- The user running `jcmd` typically needs the same user identity or appropriate OS permissions as the target process.
- The JVM must allow attach; `-XX:+DisableAttachMechanism` disables this mechanism.
- Containers or PID namespaces may prevent a process from appearing in the list or block attaching from another namespace.
- Use a JDK that includes `jcmd` and select commands supported by the target JVM.

Do not send commands to an unverified PID. `jcmd 0` sends the command to all accessible Java processes; avoid PID `0` unless you genuinely intend to broadcast.

Diagnostic commands can read sensitive runtime information or create files containing in-memory data. Restrict access permissions and protect outputs as operational application data.

## 12. Common Errors and Troubleshooting

### jcmd is not recognized

`jcmd` is part of the JDK. Verify that you are using a full JDK rather than a minimal runtime, or invoke the tool using its path inside the JDK's `bin` directory.

### PID not found in jcmd -l

Verify that the application is still running, in the expected host/PID namespace, and that you have permission to see the process. If running inside a container, run diagnostics from an environment that can see the JVM's PID.

### AttachNotSupportedException or unable to attach

Check the user running the tool, OS permissions, the attach mechanism, and the `-XX:+DisableAttachMechanism` flag. Some JVMs or hardened environments may actively block attach.

### Unknown diagnostic command

The command may not exist in the target JVM's version or implementation. Run `jcmd <pid> help` followed by `jcmd <pid> help <command>` to see the actual list and syntax.

### Native memory tracking is not enabled

Restart the JVM with `-XX:NativeMemoryTracking=summary` or `detail` if NMT is needed. It cannot be enabled for the first time after the JVM is already running.

### Unable to write heap dump

Check the path as seen by the target JVM, write permissions of the JVM user, and available disk space. Heap dumps can be large and contain sensitive data.

### JFR does not create a file

Verify that the recording has started using `JFR.check`, that the file path is writable, whether the recording has already ended, and that the recording name is correct. Check `help JFR.start`, `help JFR.dump`, and `help JFR.stop` for the running JDK.

## 13. Practical JVM Diagnostic Workflow

A lightweight workflow to get started:

1. Use `jcmd -l` to identify the right JVM and PID.
2. Run `VM.version`, `VM.uptime`, `VM.command_line`, and `VM.flags` to understand the environment.
3. Use `GC.heap_info` if you suspect heap growth or abnormal GC behavior.
4. Use `Thread.print -l` if requests are hanging, threads are blocked, or there are signs of deadlock.
5. If time-based analysis is needed, record a short JFR session with appropriate settings.
6. Only generate a class histogram or heap dump after evaluating impact, disk space, and permissions.
7. Save outputs with timestamps, PID, JDK version, and symptoms for correlation.
8. Once enough data is collected, stop the recording and handle diagnostic files according to retention policies.

Do not run every diagnostic command at once in a default script. Choose commands based on the hypothesis you are testing; high-impact commands should only be run when lighter data cannot answer the question.

## 14. Checklist for Safe and Effective jcmd Usage

- [ ] Use `jcmd -h` and `jcmd -l` to explore the tool and local JVMs.
- [ ] Confirm the exact PID or main class before sending a command.
- [ ] Use `jcmd <pid> help` to see which commands the target JVM supports.
- [ ] Use `help <command>` to verify syntax, arguments, and impact level.
- [ ] Use `VM.version`, `VM.command_line`, and `VM.flags` to understand runtime configuration.
- [ ] Use `GC.heap_info` and `Thread.print` for initial checks.
- [ ] Enable NMT at startup if native memory analysis is needed.
- [ ] Use time-bounded JFR recordings with appropriate settings.
- [ ] Assess impact before running `GC.class_histogram`, `GC.heap_dump`, or `GC.run`.
- [ ] Check write permissions, disk space, and data sensitivity for heap dump/JFR outputs.
- [ ] Do not use PID `0` unless you intend to send commands to every attachable JVM.
- [ ] Record commands and timestamps so results can be correlated and reproduced.

`jcmd` lets you observe a running JVM without modifying source code or restarting the application for basic checks. Using the exact PID, checking `help` on the target JVM, and assessing impact before running commands will help you gather useful diagnostic data while keeping operational risk under control.
