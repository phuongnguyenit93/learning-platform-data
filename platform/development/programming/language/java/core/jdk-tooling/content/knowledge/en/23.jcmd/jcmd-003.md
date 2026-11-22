# Sending Diagnostic Commands with jcmd

**`jcmd`** is a diagnostic utility included with the JDK that lets you send management commands and collect information from a running Java Virtual Machine (JVM). Instead of stopping the application to attach a debugger, you can use `jcmd` to inspect thread dumps, the heap, classloaders, VM flags, system properties, or start a Java Flight Recorder (JFR) recording.

`jcmd` is especially useful when investigating issues in a running environment, such as high CPU usage, slow application response, suspected deadlocks, unexpected heap growth, or when collecting performance data. Each diagnostic command has a different scope and impact level; check the target JVM's own help output before sending a command.

## 1. How Does jcmd Work?

`jcmd` uses the HotSpot Attach mechanism to connect to a local JVM, send a diagnostic command, and receive the returned output.

Basic flow:

1. Identify the Java process to inspect.
2. Obtain the process's PID or main class name.
3. Ask the target JVM to list the supported diagnostic commands.
4. Choose a command suitable for the issue under investigation.
5. Send the command and collect the output.
6. Save and analyze the results; then stop any recording or turn off debugging if enabled.

General syntax:

```text
jcmd <pid | main-class> <command> [arguments]
```

Where:

- `pid`: process ID of the target JVM.
- `main-class`: full or partial name of the main class used to launch the JVM.
- `command`: diagnostic command supported by the target JVM.
- `arguments`: command-specific options, typically in `key=value` or flag form.

You can view general help with:

```bash
jcmd -h
```

`jcmd` is not a tool for sending commands to a remote JVM over the network. It attaches to a JVM on the same machine/host using OS-level mechanisms. For containers, pay attention to the PID namespace, user, and attach permissions.

## 2. Listing Running JVMs with jcmd -l

Before sending a diagnostic command, find the process you want to inspect:

```bash
jcmd -l
```

Sample output:

```text
18420 com.example.DiagnosticsTarget
29116 org.apache.catalina.startup.Bootstrap
32780 jdk.jshell/jdk.internal.jshell.tool.JShellToolProvider
```

Each line typically contains the PID and the main class name or module/class information used to launch the JVM.

For example:

- PID `18420` is the `com.example.DiagnosticsTarget` application.
- PID `29116` is a Tomcat process.
- PID `32780` is JShell.

The PIDs in the example are illustrative only; actual values change on each startup.

An alternative command for listing JVMs is `jps -l`, but `jcmd -l` is the direct way to start a diagnostic workflow with `jcmd`.

**Note:** `jcmd -l` only displays JVMs that the attach mechanism can discover within the current environment's scope. JVMs running under a different user or in another PID namespace/container may not appear.

## 3. Selecting the Right Target JVM

After finding the PID, send a command by PID:

```bash
jcmd 18420 VM.uptime
```

You can use the main class name instead of the PID:

```bash
jcmd com.example.DiagnosticsTarget VM.uptime
```

If the main class name is not unique or multiple processes are running the same application, prefer the PID to avoid sending the command to the wrong target.

Common target forms:

| Target | Meaning |
| --- | --- |
| `18420` | Specific PID |
| `com.example.DiagnosticsTarget` | Full main class name |
| `DiagnosticsTarget` | Partial main class name can be used if it matches |
| `0` | Sends the command to all JVMs found by the tool; use with extreme caution |

Do not use target `0` during routine operations. A single command could generate thread dumps, heap dumps, or change the state of multiple applications at once.

PIDs can change after an application restarts. Re-run `jcmd -l` and confirm the right process before every new investigation.

## 4. Viewing Diagnostic Commands Supported by the JVM

Available commands depend on the JDK version, JVM type, provider, and process state. Do not assume every JVM has the exact same list.

List commands:

```bash
jcmd 18420 help
```

View help for a specific command:

```bash
jcmd 18420 help Thread.print
jcmd 18420 help GC.heap_info
jcmd 18420 help JFR.start
```

Some common commands:

| Command | Purpose |
| --- | --- |
| `VM.uptime` | How long the JVM has been running |
| `VM.version` | JVM version |
| `VM.command_line` | Command line used to launch the JVM |
| `VM.flags` | VM flag values |
| `VM.system_properties` | System properties |
| `VM.info` | General information about the JVM |
| `VM.classloader_stats` | Classloader statistics |
| `VM.classes` | Information on loaded classes |
| `GC.heap_info` | Overview of the Java heap |
| `GC.class_histogram` | Object statistics by class |
| `GC.heap_dump` | Creates an HPROF heap dump |
| `Thread.print` | Prints thread dump and stack traces |
| `JFR.start` | Starts a JFR recording |
| `JFR.check` | Checks running recordings |
| `JFR.dump` | Exports recording data to a file |
| `JFR.stop` | Stops a recording |

Command names and parameters may differ across JDK releases. Running `help` against the target JVM itself is the most reliable reference.

## 5. Sending Simple Commands to Inspect the JVM

Several read-only status commands can be used to begin an investigation.

View uptime:

```bash
jcmd 18420 VM.uptime
```

View JVM version:

```bash
jcmd 18420 VM.version
```

View VM flags:

```bash
jcmd 18420 VM.flags
```

List all flags supported by the VM:

```bash
jcmd 18420 VM.flags -all
```

View general information:

```bash
jcmd 18420 VM.info
```

View classloader statistics:

```bash
jcmd 18420 VM.classloader_stats
```

Example output of `VM.uptime`:

```text
18420:
163.650 s
```

The value is the uptime at the moment the command is processed, so it is not fixed.

## 6. Inspecting the Heap with GC.heap_info

`GC.heap_info` provides an overview of the Java heap, such as total reserved/committed capacity, used capacity, and collector information.

Send the command:

```bash
jcmd 18420 GC.heap_info
```

Sample output with G1:

```text
18420:
garbage-first heap   total reserved 30932992K, committed 245760K, used 52538K
region size 16384K, 3 young, 1 survivors
Metaspace       used 17878K, committed 18368K
class space     used 1926K, committed 2112K
```

Numbers and formatting depend on the collector, JVM version, and application state. Do not rely on a single heap reading to conclude there is a memory leak; observe trends over time and correlate them with GC, allocation, and workload.

Key distinctions:

- **Reserved:** memory address space reserved upfront by the VM.
- **Committed:** memory region committed by the VM so it can be used.
- **Used:** memory currently in use according to collector statistics.
- **Metaspace:** native memory used for class metadata.

`GC.heap_info` has lower impact than a heap dump, but it is still a diagnostic operation on the JVM. Read the Impact description from `help GC.heap_info` on the target environment.

## 7. Generating a Class Histogram with GC.class_histogram

`GC.class_histogram` summarizes the number of objects and heap size by class. This is a useful way to find which object types consume the most memory.

Send the command:

```bash
jcmd 18420 GC.class_histogram
```

You can also include unreachable objects:

```bash
jcmd 18420 GC.class_histogram -all
```

Sample output:

```text
 num     #instances         #bytes  Class description
-------------------------------------------------------
   1:         152340        9134400  [B
   2:          45320        3625600  java.lang.String
   3:          12000        1920000  java.util.HashMap$Node
   4:           8200         656000  java.lang.Object
```

Meaning:

- `#instances`: number of objects belonging to the class.
- `#bytes`: estimated memory size of objects belonging to the class.
- `Class description`: class name or array type descriptor.

**Impact:** according to JVM help, this command has High impact and depends on heap size and contents. Do not run it continuously or during sensitive application periods without evaluating its impact. A histogram only shows object distribution; it does not by itself explain why objects are being retained.

## 8. Creating a Heap Dump with GC.heap_dump

A heap dump saves the state of objects in the heap to an HPROF file for analysis with tools such as Java Mission Control or Eclipse Memory Analyzer (MAT).

Windows PowerShell:

```powershell
jcmd 18420 GC.heap_dump C:\diagnostics\app-heap.hprof
```

macOS/Linux:

```bash
jcmd 18420 GC.heap_dump /var/tmp/app-heap.hprof
```

The JVM must have write permission to the target directory. Ensure the disk has enough free space and that only authorized users can access the directory.

According to modern HotSpot JVM help:

- `GC.heap_dump` has High impact, depending on heap size and contents.
- By default, the command requests a full GC before dumping.
- The `-all` option requests dumping unreachable objects as well and changes the default full-GC behavior.
- The dump file can be very large.

A heap dump can contain sensitive data residing in memory, such as tokens, session data, request payloads, or personal information. Protect the file, restrict access permissions, encrypt it at rest and in transit, and delete it according to your retention policy.

Do not create heap dumps in production just to test the command. Only do so when you have a clear diagnostic goal, sufficient disk space, and an acceptable application pause tolerance.

## 9. Taking a Thread Dump with Thread.print

A thread dump shows Java threads, their states, and stack traces at the time of sampling. It is useful when investigating:

- A hung or slow-responding application.
- Thread pool worker exhaustion.
- Deadlocks or lock contention.
- Threads waiting on I/O or monitors.
- High CPU caused by a few continuously running threads.

Request a thread dump:

```bash
jcmd 18420 Thread.print
```

Include lock information:

```bash
jcmd 18420 Thread.print -l
```

On supported versions, you can enable extended thread information:

```bash
jcmd 18420 Thread.print -e
```

Sample output:

```text
"main" #1 prio=5 os_prio=0 tid=0x... nid=0x... waiting
   java.lang.Thread.State: WAITING
   at java.lang.Object.wait(Native Method)
   at com.example.DiagnosticsTarget.main(DiagnosticsTarget.java:...)
```

Reading a thread dump:

- Thread names help identify their roles.
- `java.lang.Thread.State` indicates the Java thread state.
- The stack trace shows what code the thread is executing or waiting at.
- `locked`, `waiting to lock`, and `parking` lines help identify synchronization relationships.

A thread dump is a point-in-time snapshot. When investigating deadlocks or stuck threads, take multiple thread dumps a few seconds apart and compare stack traces and states. If they are identical across captures, that is a strong signal for further investigation, though it does not automatically prove a deadlock.

## 10. Inspecting VM Flags and System Properties

View current flags:

```bash
jcmd 18420 VM.flags
```

View all flags:

```bash
jcmd 18420 VM.flags -all
```

Flags can reveal heap configuration, GC, compiler settings, compressed pointers, and other runtime options.

View system properties:

```bash
jcmd 18420 VM.system_properties
```

View launch command line:

```bash
jcmd 18420 VM.command_line
```

These outputs may contain internal paths, environment names, endpoints, or sensitive values if the application passes secrets via system properties or command-line arguments. Do not paste the full output into tickets, chat, or public logs without filtering and reviewing it first.

`VM.flags`, `VM.system_properties`, and `VM.command_line` are primarily for observation. Do not confuse them with configuration-changing commands. `VM.set_flag` is a separate command that can modify a flag if it is writable; only use it when you understand its impact and have an appropriate operational procedure.

## 11. Inspecting Classloaders with VM.classloader_stats

Classloader statistics help investigate the number of loaded classes and metaspace usage per classloader.

Send the command:

```bash
jcmd 18420 VM.classloader_stats
```

The output may include:

- Classloader and parent classloader.
- Class loader data address.
- Number of loaded classes.
- Metaspace chunk/block sizes.
- Aggregate statistics by classloader.

This command is useful when:

- The application dynamically generates too many classes.
- A classloader leak is suspected after redeployment.
- Metaspace grows abnormally.
- Multiple plugins or frameworks create their own classloaders.

Classloader leaks often involve old classloaders still being referenced by threads, `ThreadLocal`, static fields, JDBC drivers, logging frameworks, or other libraries. A single statistics snapshot only provides a baseline; compare snapshots across multiple deployments or over time.

## 12. Recording with Java Flight Recorder Using JFR.start

Java Flight Recorder (JFR) collects runtime events such as GC, allocation, compiler activity, threads, lock contention, I/O, and many other JVM events.

Start a named recording:

```bash
jcmd 18420 JFR.start name=incident settings=default
```

Check recordings:

```bash
jcmd 18420 JFR.check
```

View detailed recording configuration:

```bash
jcmd 18420 JFR.check name=incident verbose=true
```

JFR includes built-in configurations:

- `default`: collects common events with low overhead, suitable for long-running recordings.
- `profile`: collects more data with higher overhead; best used for short periods when deep analysis is needed.

You can set the duration and filename right when starting:

```bash
jcmd 18420 JFR.start name=incident settings=default duration=60s filename=incident.jfr
```

After 60 seconds, the recording ends automatically and writes the file as configured. Relative paths are resolved against the target JVM's working directory, not necessarily the terminal directory where `jcmd` was invoked.

JFR can introduce overhead depending on the settings and enabled events. Do not run a heavy profile continuously in production without evaluating its impact.

## 13. Dumping and Stopping a JFR Recording

While a recording is running, you can export a snapshot to a file without stopping the recording:

```bash
jcmd 18420 JFR.dump name=incident filename=incident-snapshot.jfr
```

Once enough data has been collected, stop the recording and write the remaining data:

```bash
jcmd 18420 JFR.stop name=incident filename=incident-final.jfr
```

Main commands:

| Command | Meaning |
| --- | --- |
| `JFR.start` | Starts a recording |
| `JFR.check` | Checks running recordings |
| `JFR.dump` | Copies current data to a file; recording continues |
| `JFR.stop` | Stops the recording; can write data to a file |

Once you have a `.jfr` file, open it with Java Mission Control (JMC) or use the `jfr` tool bundled with the JDK to view a summary:

```bash
jfr summary incident-final.jfr
```

You can export event data as JSON or XML using `jfr print` options; see `jfr help` to choose appropriate events and formats.

A JFR recording can contain sensitive information about application activity, URLs, class names, threads, and partial event data. Protect recording files as internal diagnostic artifacts.

## 14. Inspecting Native Memory with VM.native_memory

The Java heap is not the entire process memory. The JVM also uses native memory for thread stacks, metaspace, code cache, compiler, GC structures, direct buffers, and native libraries.

If Native Memory Tracking (NMT) was enabled at JVM startup, you can use:

```bash
jcmd 18420 VM.native_memory summary
```

To compare against a baseline:

```bash
jcmd 18420 VM.native_memory baseline
jcmd 18420 VM.native_memory summary.diff
```

You can request more detail:

```bash
jcmd 18420 VM.native_memory detail
```

NMT must be enabled when starting the JVM, for example:

```bash
java -XX:NativeMemoryTracking=summary -jar app.jar
```

Or:

```bash
java -XX:NativeMemoryTracking=detail -jar app.jar
```

If the JVM did not enable NMT at startup, `VM.native_memory` may report that Native Memory Tracking is not enabled. NMT cannot be fully enabled retroactively on a running process.

NMT has its own overhead and memory cost; choose `summary` or `detail` based on your needs and evaluate its impact before enabling it in production.

## 15. Sending Multiple Commands from a File

When you need to run a group of diagnostic commands, you can save them in a file and use the `-f` option.

Example **`diagnostics.txt`** file:

```text
VM.uptime
VM.flags
GC.heap_info
VM.classloader_stats
```

Send commands from the file:

```bash
jcmd 18420 -f diagnostics.txt
```

This lets you save a checklist and reuse it in an operational runbook. Each command is still executed on the target JVM; make sure every command in the file is appropriate and safe for that process.

Do not put high-impact commands such as `GC.heap_dump`, `GC.run`, or `VM.set_flag` into an automated command file without prior approval and impact assessment.

## 16. Sending Diagnostic Commands on Windows and Linux

The `jcmd` syntax is the same across operating systems; the main differences are how paths are specified and access permissions.

**Windows PowerShell:**

```powershell
jcmd -l
jcmd 18420 help
jcmd 18420 VM.uptime
jcmd 18420 Thread.print -l
jcmd 18420 GC.heap_dump C:\diagnostics\app-heap.hprof
```

**macOS/Linux:**

```bash
jcmd -l
jcmd 18420 help
jcmd 18420 VM.uptime
jcmd 18420 Thread.print -l
jcmd 18420 GC.heap_dump /var/tmp/app-heap.hprof
```

On Linux/macOS, the user executing `jcmd` typically needs the same effective user/group as the target JVM. On Windows, the calling process also needs appropriate access permissions for the account running the JVM.

When running in Docker/Kubernetes, you may need to execute `jcmd` inside the container or from an environment sharing the PID namespace and appropriate attach permissions. The PID seen from the host may differ from the PID inside the container.

Do not escalate privileges or run commands against another user's process without administrator authorization.

## 17. Common Limitations and Attach Errors

`jcmd` has several requirements:

- The target JVM must be on the same machine/host for the attach mechanism.
- The user and OS permissions must allow attaching.
- A JVM can disable attach via `-XX:+DisableAttachMechanism`.
- Some container environments, sandboxes, or security policies may block attach.
- Supported commands vary by JDK version and JVM type.
- A PID may have exited or been reused.
- Some commands have high impact and can pause the application.

Common errors:

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `jcmd` is not recognized | JDK not installed or `bin` directory missing from `PATH` | Check `JAVA_HOME` and `PATH` |
| JVM not visible in `jcmd -l` | JVM running under a different user, different container, or attach is restricted | Check user, PID namespace, and runtime environment |
| `AttachNotSupportedException` | Unable to attach to the target process | Check PID, permissions, and attach mechanism |
| `Access is denied` | Current account lacks permission to access the target JVM | Run under an authorized account or contact an admin |
| `No such process` | Wrong PID or JVM has stopped | Re-run `jcmd -l` to find the current PID |
| `Unknown diagnostic command` | Target JVM does not support the command or typo in name | Use `jcmd <pid> help` and `help <command>` |
| Failed to write heap dump | Directory does not exist, missing permissions, or out of disk space | Choose a writable path and check disk space |
| `VM.native_memory` reports NMT not enabled | JVM was not started with Native Memory Tracking | Enable NMT on the next startup |
| JFR recording fails to start | Invalid option, missing write permission, or JFR does not support the configuration | Check `help JFR.start` and the output path |

If attach is disabled or OS permissions do not allow it, no standard diagnostic command can safely bypass that restriction. Work with your administrator or use pre-configured observability mechanisms such as JMX, pre-enabled JFR, metrics, or logs.

## 18. Impact Levels and Diagnostic Safety

Not all commands have the same cost. The JVM usually displays an **Impact** line in `help <command>`.

| Command Group | Examples | Notes |
| --- | --- | --- |
| Low | `VM.uptime`, `VM.flags`, `VM.version`, `VM.classloader_stats` | Generally suitable for initial status checks |
| Medium | `Thread.print`, `GC.heap_info`, `JFR.start` | Impact depends on application size, thread count, and recording settings |
| High | `GC.class_histogram`, `GC.heap_dump` | Can consume significant time, CPU, memory, or cause noticeable pauses |

State-changing commands such as `JFR.start`, `JFR.stop`, `GC.run`, and `VM.set_flag` require separate review. Some commands generate large files or expose data from the heap.

Safe practices:

- Start with low-impact commands.
- Read `help <command>` before sending an unfamiliar command.
- Only choose commands that answer a specific diagnostic question.
- Avoid running heap dumps or class histograms repeatedly without need.
- Plan disk capacity and protect heap dump/JFR files.
- Filter system properties and command lines before sharing logs.
- Bound the duration and settings of JFR recordings.
- Record the PID, timestamp, JDK version, and commands executed.
- Do not use `jcmd 0` unless you truly intend to affect all discovered JVMs.

## 19. Hands-On Example: Creating a Java Process for Diagnostics

Create **`DiagnosticsTarget.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicLong;

public class DiagnosticsTarget {
    private static final AtomicLong COUNTER = new AtomicLong();

    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(() -> {
            while (!Thread.currentThread().isInterrupted()) {
                COUNTER.incrementAndGet();

                try {
                    Thread.sleep(100);
                } catch (InterruptedException exception) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "diagnostic-worker");

        worker.setDaemon(true);
        worker.start();

        System.out.println("PID=" + ProcessHandle.current().pid());
        System.out.println("Diagnostic target is running.");

        new CountDownLatch(1).await();
    }
}
```

Compile with Java 17:

```bash
javac --release 17 DiagnosticsTarget.java
```

Run the application:

```bash
java DiagnosticsTarget
```

Output:

```text
PID=18420
Diagnostic target is running.
```

The PID varies by environment. To keep the process running, do not close this terminal; open a second terminal to send commands.

Find the PID:

```bash
jcmd -l
```

Assuming the printed PID is `18420`, try these commands:

```bash
jcmd 18420 VM.uptime
jcmd 18420 GC.heap_info
jcmd 18420 VM.flags
jcmd 18420 VM.classloader_stats
jcmd 18420 Thread.print -l
```

Test JFR:

```bash
jcmd 18420 JFR.start name=practice settings=default duration=30s filename=practice.jfr
jcmd 18420 JFR.check name=practice
```

After the recording finishes, locate `practice.jfr` in the target JVM's working directory and view the summary:

```bash
jfr summary practice.jfr
```

Stop the process with Ctrl+C in the terminal running `DiagnosticsTarget`.

This example creates a worker thread so the thread dump has an easily recognizable stack trace. It does not simulate production load and is not meant for performance benchmarking.

## 20. Recommended Diagnostic Workflow

When an application shows abnormal behavior, you can proceed in this order:

1. Identify the exact host/container and account running the JVM.
2. Run `jcmd -l` to find the PID.
3. Run `jcmd <pid> help` to see supported commands.
4. Collect `VM.uptime`, `VM.version`, `VM.flags`, and `GC.heap_info`.
5. If thread blockage is suspected, capture multiple `Thread.print -l` outputs a few seconds apart.
6. If heap retention is suspected, consider a class histogram; only take a heap dump when you have an analysis plan and sufficient resources.
7. If time-based performance analysis is needed, use JFR with appropriate settings and duration.
8. If the heap is stable but process memory is growing, inspect NMT if it was enabled at startup.
9. Store diagnostic artifacts in a secure location and record timestamps/commands.
10. Analyze results, correlate with metrics/logs, and plan remediation.
11. Stop the JFR recording once enough data has been collected.
12. Delete or archive dumps/recordings according to retention policies.

Do not fire off a batch of commands before defining a goal. A small, ordered capture sequence with clear timestamps is usually easier to analyze than a large collection of outputs without context.

## 21. Key Takeaways

- `jcmd` sends diagnostic commands to a running local JVM.
- Use `jcmd -l` to find the PID and `jcmd <pid> help` to list commands.
- Use `jcmd <pid> help <command>` to check syntax and Impact level.
- `VM.uptime`, `VM.flags`, `GC.heap_info`, and `VM.classloader_stats` help observe JVM state.
- `Thread.print -l` generates a thread dump with lock information.
- `GC.class_histogram` and `GC.heap_dump` can have high impact; heap dumps may also contain sensitive data.
- `JFR.start`, `JFR.check`, `JFR.dump`, and `JFR.stop` support recording runtime events.
- `VM.native_memory` requires NMT to be enabled at JVM startup.
- Attach depends on PID namespace, user, OS permissions, and JVM configuration.
- Choose commands by Impact level, protect diagnostic artifacts, and stop recordings when finished.

Once you master the workflow of finding the PID → checking supported commands → sending diagnostic commands → analyzing output, you can collect data from a running JVM in a controlled way, supporting incident investigation without stopping the application just to start observing.