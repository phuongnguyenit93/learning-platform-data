# Using jcmd to Inspect Processes and Diagnostic Capabilities in Java 17

When a Java application runs slowly, consumes high CPU, uses a lot of memory, or has stuck threads, the first step is to identify **which JVM is running** and collect data from that exact process. Java 17 provides the `jcmd` command-line tool to list JVMs, view runtime information, take thread dumps, inspect the heap, check JVM flags, and control Java Flight Recorder (JFR).

`jcmd` is the JDK's local diagnostic tool. It sends diagnostic commands to a running JVM through the attach mechanism. Each command has a different scope and impact level: some only read metadata, while others traverse the heap, trigger garbage collection, or generate very large dump files.

This lesson explains how to locate the right process, discover commands supported by the JVM, choose appropriate diagnostic commands, and collect data safely in a Java 17 environment.

## 1. What Is jcmd?

`jcmd` is a utility in the JDK located in the `bin` directory, used to send diagnostic commands to Java processes. The tool can:

- List running JVMs visible to the attach mechanism.
- Display the list of commands supported by the target JVM.
- Print the command line, system properties, JVM flags, version, and uptime.
- Capture thread dumps and class loader information.
- View heap summaries, class histograms, and create heap dumps.
- Inspect Native Memory Tracking if the JVM was started with this feature enabled.
- Start, check, dump, and stop Java Flight Recorder recordings.

Example directory layout:

~~~text
JDK_HOME/
  bin/
    java
    javac
    jcmd
~~~

You should use `jcmd` from a JDK matching the target JVM version. In production, verify the exact JDK and the exact host/container running the application before issuing commands.

### 1.1. General Syntax

~~~text
jcmd <pid | main-class> <command> [arguments]
~~~

Components:

- `pid`: process ID of the JVM to diagnose.
- `main-class`: main class name to select the JVM where applicable; PID is usually clearer and less ambiguous.
- `command`: diagnostic command sent to the JVM.
- `arguments`: arguments specific to that command.

Common invocations:

~~~bash
jcmd -l
jcmd -h
jcmd <pid> help
jcmd <pid> help Thread.print
jcmd <pid> VM.version
~~~

`jcmd -h` displays the tool's syntax help on the current machine. `jcmd <pid> help` asks the target JVM itself to list the commands it supports.

## 2. Listing Java Processes with jcmd -l

Common starting command:

~~~bash
jcmd -l
~~~

The output typically includes the PID and main class or command-line information of each process:

~~~text
24680 com.example.orders.OrderApplication
25104 org.gradle.launcher.daemon.bootstrap.GradleDaemon
~~~

In the example, `24680` and `25104` are PIDs. Choose the PID of the application under investigation, avoiding confusion with a Gradle daemon, build tool, or another JVM.

### 2.1. Cross-Checking with the Operating System

If you are unsure which PID belongs to which application, cross-check using OS tools.

Linux:

~~~bash
ps -eo pid,ppid,user,etime,args | grep '[j]ava'
~~~

Windows PowerShell:

~~~powershell
Get-CimInstance Win32_Process -Filter "Name = 'java.exe' OR Name = 'javaw.exe'" |
    Select-Object ProcessId, ParentProcessId, ExecutablePath, CommandLine
~~~

Do not rely solely on the main class name. One machine can run multiple instances of the same application, multiple Java services, or helper JVMs. Check the PID, user, uptime, command line, and working directory if needed.

### 2.2. Limitations of the jcmd -l List

`jcmd -l` lists JVMs visible to the tool via the attach mechanism within the current environment scope. It is not a general process manager and does not guarantee visibility of every JVM on the machine.

Reasons a process may not appear include:

- The process runs under a different user or current permissions are insufficient.
- The JVM has exited, is still starting up, or the attach listener is not ready yet.
- The JVM was launched with `-XX:+DisableAttachMechanism`.
- The tool and target are in different containers or PID namespaces.
- The temporary directory used for attach is not shared or has incompatible permissions.
- The process is not a HotSpot/OpenJDK JVM compatible with the attach mechanism in use.

If a PID is not found via `jcmd -l`, verify using the OS process list and runtime environment before concluding the JVM does not exist.

## 3. Requirements to Attach to a Target JVM

`jcmd` is not a remote command-sending tool over the network. It generally must run on the same machine as the target JVM and under the same effective user/group required by the attach mechanism.

Practical conditions to check:

1. A JDK with `jcmd` is available in the execution environment.
2. You are running the command on the right host or in the right container/PID namespace.
3. The user running `jcmd` has permission to attach to the target process.
4. The target JVM has not disabled the attach mechanism.
5. The target JVM is alive and able to handle diagnostic requests.

A JVM may be launched with:

~~~bash
java -XX:+DisableAttachMechanism -jar application.jar
~~~

When this option is enabled, attach-based tools such as `jcmd` cannot attach in the normal way. This is an operational/security decision that must be considered at launch time; no standard `jcmd` command can re-enable attach on an already running JVM.

### 3.1. Containers and PID Namespaces

In containerized environments, the PID seen from the host may differ from the PID seen inside the container. Running `jcmd -l` on the host may not see JVMs in a separate namespace; conversely, the PID inside a container is not necessarily the PID on the host.

A sound workflow typically is:

- Identify the container or pod running the application.
- Run the tool inside the same container or an environment that can access the exact PID namespace and attach endpoint.
- Use JDK tools whose version matches the target JVM.
- Check the user and permissions for the temporary directory used by attach.

Do not guess PIDs between host and container. Re-verify the PID directly inside the environment where `jcmd` is executed.

### 3.2. What Impact Does Attaching Have?

`jcmd` sends requests into the target JVM. Depending on the command, the JVM may need to perform synchronized operations, traverse metadata, or pause certain threads briefly. Therefore:

- Metadata-reading commands generally have less impact than heap dumps or class histograms.
- Thread dumps can generate a substantial amount of data if the application has very many threads.
- Heap histograms and heap dumps can affect latency and CPU.
- JFR has overhead depending on event types, configuration, and recording duration.

Read the description/impact in `help` from the target JVM itself before running high-impact commands.

## 4. Discovering Supported Commands

The list of diagnostic commands depends on the JVM, version, build, and configuration. So once you identify the PID, query the process directly:

~~~bash
jcmd 24680 help
~~~

To view details of a specific command:

~~~bash
jcmd 24680 help Thread.print
jcmd 24680 help GC.heap_dump
jcmd 24680 help JFR.start
~~~

This is an important step before running commands with arguments. The syntax, options, and impact reported by the target JVM are more reliable than guessing from another machine.

### 4.1. Running a Command

~~~bash
jcmd 24680 VM.version
~~~

The result prints directly to the terminal. You can save output to a file to compare across collection runs:

Linux:

~~~bash
jcmd 24680 VM.flags -all > vm-flags.txt
~~~

Windows PowerShell:

~~~powershell
jcmd 24680 VM.flags -all | Out-File -Encoding utf8 vm-flags.txt
~~~

If using a different shell, redirection syntax and output file encoding may vary. Ensure the target directory is writable and avoid overwriting diagnostic evidence you need to keep.

### 4.2. Running Commands from a File

`jcmd` has an `-f <filename>` option to read commands from a file:

~~~bash
jcmd -f diagnostics.txt 24680
~~~

The file contains commands in the format supported by the tool. Before running a batch, review the file contents and evaluate the impact of each command. Do not include commands that mutate JVM state in a batch just to gather a lot of data at once.

## 5. Inspecting Basic Runtime Information

Some useful commands that typically have lower impact than heap-traversal operations:

| Command | Information |
| --- | --- |
| `VM.version` | JVM version |
| `VM.uptime` | How long the JVM has been running |
| `VM.command_line` | JVM launch arguments |
| `VM.flags` | Current JVM flags |
| `VM.system_properties` | System properties |
| `VM.info` | JVM runtime and environment information |
| `VM.dynlibs` | Loaded native libraries |
| `VM.classloader_stats` | Class loader statistics |

Examples:

~~~bash
jcmd 24680 VM.version
jcmd 24680 VM.uptime
jcmd 24680 VM.command_line
jcmd 24680 VM.flags
jcmd 24680 VM.system_properties
~~~

### 5.1. VM.command_line

~~~bash
jcmd 24680 VM.command_line
~~~

Helps inspect the main class or JAR and arguments passed at launch. This information can reveal:

- Which configuration profile the JVM is using.
- Whether heap size, GC, or diagnostic options are enabled.
- Whether environment-related system properties were passed.
- Whether the process is running the expected artifact and arguments.

The command line may contain tokens, passwords, or sensitive data if the application is misconfigured. Restrict access permissions on the output file and do not paste raw output into public tickets or logs.

### 5.2. VM.flags

~~~bash
jcmd 24680 VM.flags
jcmd 24680 VM.flags -all
~~~

`VM.flags` displays JVM flags. The `-all` option requests broader output, including flag values and metadata depending on the implementation.

Useful information during investigation:

- Heap sizing such as `InitialHeapSize` and `MaxHeapSize`.
- Selected GC.
- Compiler/JIT options.
- Diagnostic or experimental flags.
- Whether Native Memory Tracking was enabled at startup.

Do not change a flag merely because you see a different value on another machine. Some flags can only be set at JVM startup; `VM.set_flag` only supports certain manageable flags at runtime and remains subject to JVM constraints.

### 5.3. VM.system_properties

~~~bash
jcmd 24680 VM.system_properties
~~~

This command lists JVM system properties. They can help identify:

- `java.version`, `java.vendor`, `java.home`.
- `user.dir`, `user.timezone`, `file.encoding`.
- Profiles or endpoints configured via properties.
- Temporary paths and application directories.

System properties may contain secrets if the application or startup script passes credentials via properties. Filter/redact before sharing output.

## 6. Diagnosing Threads with Thread.print

A thread dump is a snapshot of thread states at a point in time. It helps locate:

- Threads running on CPU or waiting on I/O.
- Deadlocks.
- Lock contention.
- Thread pool worker exhaustion.
- Threads waiting on monitors or conditions.
- Multiple threads simultaneously waiting on a dependency.

Command:

~~~bash
jcmd 24680 Thread.print
~~~

Options:

~~~bash
jcmd 24680 Thread.print -l
jcmd 24680 Thread.print -e
~~~

- `-l`: prints additional information about `java.util.concurrent` locks.
- `-e`: requests extended thread information per the target JVM's command help.

### 6.1. Reading a Thread Dump

An illustrative output snippet:

~~~text
"http-worker-12" #84 daemon prio=5 os_prio=0
   java.lang.Thread.State: BLOCKED
        at com.example.store.Cache.refresh(Cache.java:84)
        - waiting to lock <0x0000000712345678>
        at com.example.api.OrderHandler.handle(OrderHandler.java:51)
~~~

Components:

- Thread name helps identify the worker group.
- `Thread.State` indicates the JVM state such as `RUNNABLE`, `BLOCKED`, `WAITING`, or `TIMED_WAITING`.
- Stack trace shows the call path at capture time.
- Monitor/lock ID helps link waiting threads to the lock-holding thread when the output provides corresponding details.

`RUNNABLE` does not always mean the thread is continuously consuming CPU; from the JVM's perspective it can also be in the runnable state while waiting on native operations or I/O.

### 6.2. Deadlocks

If the thread dump includes a deadlock section, look for circular lock waits. For example:

~~~text
Thread A holds Lock-1 and waits for Lock-2
Thread B holds Lock-2 and waits for Lock-1
~~~

A single dump can reveal a deadlock state at capture time. If a transient stall is suspected, collect multiple dumps a few seconds apart to compare stacks and states. Do not conclude a deadlock solely from seeing one thread in `BLOCKED`.

### 6.3. Collecting Multiple Thread Dumps

Linux:

~~~bash
for i in 1 2 3; do
  jcmd 24680 Thread.print -l > "threads-$i.txt"
  sleep 5
done
~~~

PowerShell:

~~~powershell
1..3 | ForEach-Object {
    jcmd 24680 Thread.print -l |
        Out-File -Encoding utf8 "threads-$_.txt"
    Start-Sleep -Seconds 5
}
~~~

Three snapshots spaced a few seconds apart help distinguish normal brief waits from long-stuck threads. The interval and count should match how fast the incident reproduces, avoiding unnecessary bulk output.

## 7. Inspecting the Heap and Class Histograms

### 7.1. GC.heap_info

~~~bash
jcmd 24680 GC.heap_info
~~~

This command displays an overview of the heap according to the active GC, such as heap regions and allocated/used capacity. Output format varies by garbage collector and JVM version.

This is useful for quickly checking whether the heap is near its limit. It does not replace heap dump analysis and does not directly explain which objects retain memory.

### 7.2. GC.class_histogram

~~~bash
jcmd 24680 GC.class_histogram
~~~

A class histogram aggregates instance counts and total bytes per class. It can help identify:

- A class with an abnormally growing instance count.
- Byte or char arrays occupying large amounts of memory.
- Caches or collections holding huge numbers of entries.
- Object types with a notable footprint.

The `-all` option requests including unreachable objects instead of the default live-objects-only behavior:

~~~bash
jcmd 24680 GC.class_histogram -all
~~~

`-all` changes the meaning of the statistics: results can include objects eligible for collection by GC. Thus counts and bytes may be higher than a live-object histogram. Check `help GC.class_histogram` on the target JVM before running, because histogram inspection traverses heap information and can cause significant pauses/impact, especially when a service already has high latency.

A histogram is an aggregate snapshot; it does not show full reference chains keeping objects alive. To find GC roots or retention paths, you may need a heap dump and an appropriate analysis tool.

### 7.3. GC.heap_dump

A heap dump saves the JVM object graph to a file for deep analysis:

~~~bash
jcmd 24680 GC.heap_dump /var/tmp/orders-heap.hprof
~~~

Command options may include:

- `-all`: include unreachable objects in the dump.
- `-gz=<level>`: compress output at a supported level.
- `-overwrite`: allow overwriting the target file if supported by the command.

Check `jcmd 24680 help GC.heap_dump` for exact syntax on the target JDK. By default, a heap dump may require a Full GC before writing; this is a high-impact operation that can pause the application significantly.

Before taking a dump:

1. Verify the target directory and available free disk space.
2. Check maximum heap size and estimate dump size.
3. Ensure write permissions exist.
4. Choose a timing compatible with acceptable impact.
5. Restrict read permissions on the dump file and securely delete it once the investigation concludes.

Heap dumps can contain passwords, tokens, sessions, user data, and in-memory request/response payloads. Treat them as sensitive data.

## 8. Native Memory Tracking

The heap is not all the memory used by a Java process. The JVM also uses native memory for thread stacks, metaspace, code cache, GC, compiler, direct buffers, and other native components.

Native Memory Tracking (NMT) allows the JVM to track native memory allocations for diagnostics. In Java 17, NMT must be enabled when the JVM starts:

~~~bash
java -XX:NativeMemoryTracking=summary -jar application.jar
~~~

Or use the detailed level:

~~~bash
java -XX:NativeMemoryTracking=detail -jar application.jar
~~~

Full NMT cannot be enabled on an already-running JVM simply by calling `jcmd`. If the target did not enable NMT, `VM.native_memory` will report that the feature is not enabled.

### 8.1. Viewing the Native Memory Summary

~~~bash
jcmd 24680 VM.native_memory summary
~~~

The NMT summary groups native memory by JVM-tracked categories, helping pinpoint unusual consumption outside the Java heap.

### 8.2. Creating a Baseline and Comparing

~~~bash
jcmd 24680 VM.native_memory baseline
~~~

After some time or after reproducing load:

~~~bash
jcmd 24680 VM.native_memory summary.diff
~~~

Comparing against a baseline reveals increases/decreases between two points in time. If NMT was enabled at the `detail` level, corresponding detail/diff modes can be used per `help VM.native_memory`.

NMT incurs memory and CPU overhead. The `detail` level is typically more expensive than `summary`; enable only the level needed for the investigation. NMT does not track every native allocation performed by all external libraries, so it is not a comprehensive measurement of every byte in the process.

## 9. Diagnosing Class Loaders and Code Cache

When an application loads many plugins, generates classes dynamically, or shows signs of metaspace growth, class loader commands can be helpful:

~~~bash
jcmd 24680 VM.classloader_stats
jcmd 24680 VM.classloaders
jcmd 24680 VM.class_hierarchy
~~~

Available commands and specific parameters depend on the target JVM. Run `help` for each command.

`VM.classloader_stats` provides statistics on class loaders and loaded class counts per loader. `VM.classloaders` can display the class loader hierarchy. `VM.class_hierarchy` supports inspecting inheritance relationships depending on options supported by the JVM.

If class loaders are not released, the application may retain classes and metadata longer than expected. Analyze references and loader lifecycles before concluding a class loader leak; an increasing class count alone is not enough to prove a leak.

### 9.1. Compiler and Code Cache

Some compiler-related commands:

~~~bash
jcmd 24680 Compiler.codecache
jcmd 24680 Compiler.queue
jcmd 24680 Compiler.codelist
~~~

These help observe the code cache, compilation queue, or list of compiled methods if supported by the target JVM. Useful when investigating JIT behavior, code cache pressure, or abnormal compiler activity.

## 10. Controlling and Checking Java Flight Recorder with jcmd

Java Flight Recorder (JFR) is the JVM's runtime event recording mechanism. It can collect CPU sampling, allocations, GC, threads, lock contention, class loading, and other events.

JFR is built into modern OpenJDK/Oracle JDK releases, including Java 17; legacy commercial unlock flags are not required.

Key commands:

| Command | Purpose |
| --- | --- |
| `JFR.check` | List recordings and their status |
| `JFR.start` | Start a recording |
| `JFR.dump` | Write existing recording data to a file |
| `JFR.stop` | Stop a recording |
| `JFR.configure` | View or configure certain JFR settings |

### 10.1. Checking Recordings

~~~bash
jcmd 24680 JFR.check
~~~

If recordings already exist, the output shows names, states, and related info. Check before starting a new recording to avoid running unnecessary duplicate sessions.

### 10.2. Starting a Time-Limited Recording

~~~bash
jcmd 24680 JFR.start name=triage settings=profile duration=5m filename=/var/tmp/triage.jfr
~~~

Explanation:

- `name=triage`: names the recording for future reference.
- `settings=profile`: uses the profile configuration with more events than default, suited for short-term investigation.
- `duration=5m`: limits recording duration.
- `filename=...`: specifies where to save the recording upon completion per command behavior.

The file path must exist or be creatable as required by the command, and the JVM needs write permissions. Check `help JFR.start` on the target to verify supported options.

### 10.3. Dumping a Running Recording

~~~bash
jcmd 24680 JFR.dump name=triage filename=/var/tmp/triage-snapshot.jfr
~~~

`JFR.dump` writes a snapshot of the recording to a file without necessarily stopping the recording. This is useful when you want to capture data at the time an issue is detected while continuing to monitor.

### 10.4. Stopping a Recording

~~~bash
jcmd 24680 JFR.stop name=triage
~~~

If the recording was configured with a `filename` or a matching output destination, data is saved accordingly. Verify that the file was created and can be opened with JDK Mission Control (JMC) or a JFR analysis tool.

### 10.5. Choosing default or profile?

- `default`: generally captures fewer events, suitable for longer general observation.
- `profile`: captures more detail, useful for short-term investigation; overhead may be higher.

There is no single optimal configuration for every workload. Start with a short duration and an appropriate configuration, then increase detail if the data is insufficient to explain the incident.

JFR recordings can contain class names, methods, threads, file paths, and runtime data. Protect `.jfr` files according to your organization's data policies.

## 11. Other Useful Commands During Investigation

| Command | Scenario |
| --- | --- |
| `VM.info` | Need overall JVM, OS, and runtime info |
| `VM.dynlibs` | Investigating loaded native libraries |
| `VM.classloader_stats` | Investigating class loading/metaspace |
| `Compiler.codecache` | Checking code cache |
| `GC.heap_info` | Viewing heap overview |
| `GC.class_histogram` | Finding classes with high instance counts or memory usage |
| `VM.native_memory` | Investigating native memory when NMT is enabled |
| `JFR.*` | Collecting runtime events over a time window |

These are common command groups on HotSpot JDK 17. Not every JVM vendor/build has the exact same list or options. Use `help` on the target JVM as the authoritative syntax reference.

## 12. Symptom-Driven Diagnostic Workflows

### 12.1. Application Responds Slowly or Requests Hang

1. Use `jcmd -l` and the OS process list to identify the exact PID.
2. Run `VM.uptime`, `VM.command_line`, and `VM.flags` to understand the environment.
3. Capture 2–3 thread dumps with `Thread.print -l`, spaced a few seconds apart.
4. Compare stacks of relevant threads; look for locks, waits, socket reads, or non-progressing stacks.
5. If data is still insufficient, run a short JFR recording to observe CPU, locks, GC, and allocations.

### 12.2. Heap Growing Rapidly or Near OOM

1. Check `GC.heap_info` for an overall picture.
2. Run `GC.class_histogram` if impact permits to find classes/arrays consuming significant memory.
3. If reference paths must be analyzed, plan a heap dump with adequate disk space and data protection.
4. Compare multiple snapshots or recordings to distinguish normal load growth from abnormally retained objects.

### 12.3. Process Uses High RAM While Heap Is Small

1. Compare process RSS with committed/allocated heap.
2. Check `VM.flags` to see if NMT is enabled.
3. If NMT is active, capture `VM.native_memory summary`.
4. If a baseline exists, use `summary.diff` to see which native memory categories grew.
5. Inspect thread count, direct buffers, native libraries, and GC/compiler settings.

NMT provides one perspective; cross-reference with OS metrics and the application's native libraries.

### 12.4. High CPU

1. Capture multiple thread dumps to see which threads repeatedly appear on relevant stacks.
2. Run JFR `profile` for a short window to inspect CPU samples and hot methods.
3. Check GC activity, compiler, and code cache if the data points there.
4. Correlate with application metrics to identify the endpoint or workload generating load.

A thread dump is not a CPU profiler. JFR or an appropriate profiler provides better quantitative data.

## 13. Preserving Evidence and Limiting Impact

Production diagnostics require balancing information richness against service impact.

Before running commands:

- Confirm the exact PID, host, container, and user.
- Check `help <command>` for syntax and impact.
- Choose lower-impact commands first; only use heap dumps or heavy operations when justified.
- Check disk space and write permissions.
- Name files with PID, timestamp, and data type.
- Record the timestamp, command, JDK version, and observed symptoms.

After collection:

- Store output in a location with restricted access.
- Redact secrets before sharing.
- Do not upload heap dumps or JFR files containing sensitive data to public storage.
- Delete diagnostic data once the retention period expires.
- Correlate findings with application and OS metrics/logs.

Heap dump files can be huge and contain nearly all reachable data on the heap. Thread dumps, command lines, and system properties can also expose usernames, paths, endpoints, and secrets.

## 14. jcmd Is Not a Remote Monitoring Tool

`jcmd` operates on a JVM attachable from the local environment. It does not inherently provide a remote management protocol over the network.

In multi-host or Kubernetes environments:

- Use SSH, container exec mechanisms, or your operations platform to run the tool in the exact target environment.
- Respect process and container access controls.
- Collect data under controlled procedures.
- If continuous monitoring or remote management is needed, use appropriate metrics systems, JMX/management agents, APM, or observability platforms.

Do not expose attach mechanisms or broad process access over the network just to make running `jcmd` convenient.

## 15. Quick Comparison of Diagnostic Tools

| Tool | Primary Role |
| --- | --- |
| `jcmd` | Send various diagnostic commands to a target JVM; recommended all-in-one tool for many HotSpot diagnostics |
| `jps` | List JVM processes and main class information |
| `jstack` | Dedicated tool for capturing thread dumps |
| `jmap` | Dedicated tool for heap/memory mapping |
| `jstat` | Periodically monitor JVM statistics such as GC |
| JDK Mission Control | Analyze JFR recordings and diagnostic data |

Specialized tools remain useful, but many tasks can be done via `jcmd`. With Java 17, start with `jcmd <pid> help` to discover commands supported by the target rather than assuming an option exists on every build.

## 16. Comprehensive Diagnostic Session Example

Suppose `OrderApplication` has rising latency and signs of continuous heap growth. A controlled collection session might include:

~~~bash
# 1. Identify the JVM
jcmd -l

# 2. Check startup information
jcmd 24680 VM.version
jcmd 24680 VM.uptime
jcmd 24680 VM.command_line
jcmd 24680 VM.flags

# 3. Capture several spaced thread dumps
jcmd 24680 Thread.print -l > threads-1.txt
sleep 5
jcmd 24680 Thread.print -l > threads-2.txt
sleep 5
jcmd 24680 Thread.print -l > threads-3.txt

# 4. Inspect heap and class histogram if impact permits
jcmd 24680 GC.heap_info
jcmd 24680 GC.class_histogram

# 5. Record short JFR for runtime analysis
jcmd 24680 JFR.start name=triage settings=profile duration=5m filename=/var/tmp/orders-triage.jfr
~~~

Commands in the example must substitute the real PID and paths for your environment. Do not run the entire sequence mechanically: assess impact, disk space, and effect before each command. If `GC.class_histogram` or a heap dump risks a long pause for the service, skip it during peak load and collect it during a maintenance window.

Once the recording finishes, open the `.jfr` file with an appropriate analysis tool. Combine thread dumps, heap metrics, JFR, and application metrics to find the root cause rather than inferring from a single snapshot.

## 17. Common Errors When Using jcmd

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| JVM missing from `jcmd -l` | Wrong namespace/user, attach disabled, or incompatible JVM | Check OS process list, container, user, and `DisableAttachMechanism` |
| `AttachNotSupportedException` | Cannot attach to target in the current environment | Verify same host/namespace, permissions, and target state |
| `Unknown diagnostic command` | Target JVM does not support that command | Run `jcmd PID help` and choose a listed command |
| `IllegalArgumentException` for arguments | Wrong syntax or unsupported option | Run `jcmd PID help <command>` |
| Failed to write dump | Invalid path, missing permissions, or out of disk space | Check filesystem and write permissions |
| Heap dump pauses service for a long time | High-impact operation, large heap, or required GC | Plan ahead; evaluate timing and size before running |
| NMT reports not enabled | JVM was not launched with `-XX:NativeMemoryTracking` | Enable for the next launch; cannot be fully enabled retroactively |
| Expected JFR file missing | Wrong recording name, filename, or recording not finished/dumped | Check `JFR.check`, `help JFR.start`, `JFR.dump`, `JFR.stop` |
| Output contains secrets | Command line/properties or heap contain sensitive data | Restrict access and redact before sharing |

## 18. Self-Check Questions

**1. What is `jcmd` used for?**  
Sending diagnostic commands to a running JVM to query runtime information and collect diagnostic data.

**2. Which command lists JVMs visible to the tool?**  
`jcmd -l`.

**3. How do you view the list of commands supported by a JVM?**  
`jcmd <pid> help`.

**4. How do you view the syntax of a specific command?**  
`jcmd <pid> help <command>`.

**5. Is `jcmd` a remote attach tool over the network?**  
No. It uses the local attach mechanism and must run in an environment that can access the target process.

**6. Which command captures a thread dump?**  
`jcmd <pid> Thread.print`; `-l` can be used to print additional lock information.

**7. Which command displays a heap summary?**  
`jcmd <pid> GC.heap_info`.

**8. What does `GC.class_histogram` show?**  
Instance counts and total size per class in the heap according to the scope selected by the command.

**9. Can Native Memory Tracking be enabled via `jcmd` after the JVM is already running?**  
No. NMT must be enabled when the JVM starts.

**10. Which JFR command starts a recording?**  
`JFR.start`; related commands include `JFR.check`, `JFR.dump`, and `JFR.stop`.

**11. Why must you be cautious with `GC.heap_dump`?**  
Heap dumps can cause significant pauses, require substantial disk space, and contain sensitive data in memory.

**12. If a JVM does not appear in `jcmd -l`, can you conclude it is not running?**  
No. Check the OS process list, user, container/PID namespace, and attach mechanism.

**13. What data can `VM.command_line` and `VM.system_properties` expose?**  
Launch arguments, endpoints, paths, and sometimes tokens/passwords if the application is misconfigured.

**14. Is a thread dump enough to find CPU hot spots?**  
No. A thread dump is a snapshot; JFR or an appropriate profiler provides quantitative CPU data.

**15. Why must you check `help` on the target JVM?**  
Supported commands, arguments, and impact depend on the version, build, and configuration of the running JVM.

## Official References

- [Java SE 17 — jcmd Tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): syntax, process listing, commands, and tool options.
- [Java SE 17 — Diagnostic Commands](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): list of diagnostic commands and how to invoke them.
- [Java SE 17 — Java Flight Recorder](https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder-api-programmers-guide.pdf): recording mechanisms and JFR event analysis.
- [Java SE 17 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/17/vm/native-memory-tracking.html): enabling NMT at startup, baselining, and comparing native memory.
- [Java SE 17 — Troubleshooting Guide](https://docs.oracle.com/en/java/javase/17/troubleshoot/): JVM, heap, thread, and GC diagnostic workflows and supporting tools.
