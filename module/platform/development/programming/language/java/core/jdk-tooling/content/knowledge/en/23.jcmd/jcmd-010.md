# Using jcmd Safely

**jcmd** is a command-line tool included with the JDK for sending diagnostic commands to a running JVM. It supports inspecting JVM state, threads, heap, class loading, native memory, logging, and Java Flight Recorder (JFR). jcmd is useful when you need to collect diagnostic data without stopping the application.

Using jcmd safely means sending the right command to the right process, understanding the command's impact before running it, protecting diagnostic data, and restricting access permissions. Not every diagnostic command is read-only: some commands can trigger garbage collection, create large heap dumps, modify logging, or load a native agent.

This guide focuses on JDK 26 and the HotSpot JVM. The list of available commands, syntax, and impact levels may vary by JDK release or JVM implementation; always check the target process's help output before running a command.

## 1. How Does jcmd Work?

jcmd sends a diagnostic command request to a running JVM. The JVM processes the request and returns the result to the terminal or writes it to a file, depending on the selected command.

Execution flow:

~~~text
Operator / diagnostic script
          |
          v
        jcmd
          |
          | local attach request
          v
      Target JVM
          |
          | diagnostic command
          v
 JVM serviceability subsystem
          |
          v
 Output / dump / JFR recording
~~~

jcmd does not restart the application and is not an interactive line-by-line debugger. It instructs a running JVM to perform a specific diagnostic operation.

Key characteristics:

- jcmd must run on the same machine as the target JVM.
- The user running jcmd must have the same effective user ID and group ID as the account that started the JVM.
- Commands and arguments depend on the target JVM.
- jcmd is not a direct remote tool over the network.
- Diagnostic commands have different impact levels; read the command description before using it.

Use jcmd from the same JDK release as the target JVM whenever possible. Oracle does not support using serviceability tools from one JDK release to troubleshoot a different release.

## 2. Identifying the Right JVM Before Sending Commands

The first step is to list the running Java processes:

~~~bash
jcmd -l
~~~

Running `jcmd` with no arguments is equivalent to `-l`.

Example output:

~~~text
2125 com.acme.DemoServer
5485 jdk.jcmd/sun.tools.jcmd.JCmd -l
~~~

Actual output may also include the process's command-line arguments. The PID is the process identifier; the main class helps distinguish between running applications.

### Selecting a Specific PID

Once you have identified the right process, use its PID:

~~~bash
jcmd 2125 VM.version
~~~

Using a specific PID is the safest approach when multiple Java applications are running on the same machine.

### Avoiding Main-Class Selection When Multiple Instances Exist

You can pass the main class name:

~~~bash
jcmd com.acme.DemoServer VM.version
~~~

The main class name may match multiple running JVMs. In that case, jcmd sends the command to every process whose main class name matches. Do not use this approach unless you are certain only one matching instance is running.

### Do Not Use PID 0 in Routine Operations

PID 0 means sending the command to all available Java processes:

~~~bash
jcmd 0 VM.version
~~~

This has a broad blast radius. A command like `Thread.print` can produce massive output; a high-impact command can affect multiple applications simultaneously. In production, never use PID 0 as a shortcut to target a single application.

### Verifying Process Identity

Before running a medium- or high-impact command, verify the process using low-impact commands:

~~~bash
jcmd 2125 VM.version
jcmd 2125 VM.command_line
jcmd 2125 VM.uptime
~~~

`VM.command_line` and `jcmd -l` output can display startup arguments. If an operations team inadvertently passed secrets on the command line, the output may expose them. Do not paste raw output into public tickets or unauthorized chat channels.

## 3. Attach Requirements and Access Restrictions

jcmd uses the JVM's local attach mechanism. Common requirements to check:

| Requirement | Meaning |
|---|---|
| Same host | jcmd must run on the machine hosting the target JVM |
| Same effective user/group | The account running jcmd must match the account that launched the JVM |
| Attach mechanism enabled | The JVM must allow tool attachment |
| Correct PID namespace | In containers, the PID visible from the host may differ from the PID inside the container |
| Compatible tool | Use the serviceability tool matching the target process's JDK |

If the JVM was started with the option:

~~~bash
-XX:+DisableAttachMechanism
~~~

then attach tools such as jcmd cannot connect through the normal mechanism. This is a protective configuration decided at JVM startup; jcmd cannot re-enable attach from the outside.

### Running in Docker or Containers

`jcmd -l` does not list JVMs running in separate Docker processes. Oracle recommends using OS tools such as `ps` to find the PID in the appropriate environment.

Common operational practices:

- Run jcmd inside the container where the PID namespace sees the target JVM.
- Use `ps` inside the container to identify the PID, then invoke jcmd with that PID.
- If using the host PID namespace, verify that the host PID actually points to the intended process.
- Ensure the account running the command has the appropriate attach permissions.

Never take a PID from one namespace and use it in another without verification. The PID may point to a completely different process.

## 4. Discovering Commands Before Running Them

Available diagnostic commands vary by JVM and JDK release. Query the target process:

~~~bash
jcmd 2125 help
~~~

View the syntax for a specific command:

~~~bash
jcmd 2125 help Thread.print
~~~

You can view the full help output:

~~~bash
jcmd 2125 help -all
~~~

The target process's help output tells you:

- Whether the command is supported.
- Which options and arguments are valid.
- Default values.
- The documented impact level.
- Any command-specific conditions or limitations.

### Option and Argument Syntax

jcmd uses two forms:

- Options are typically written as `key` or `key=value`.
- Arguments are plain values; do not prefix them with `option=value` when the command defines positional arguments.

For example, `JFR.start` uses `key=value` options:

~~~bash
jcmd 2125 JFR.start name=incident settings=default duration=120s
~~~

`GC.heap_dump` takes the filename as a positional argument:

~~~bash
jcmd 2125 GC.heap_dump /secure/diagnostics/heap.hprof
~~~

If an argument contains spaces, wrap it in single or double quotes appropriate for your shell. Check `help` to avoid confusing options with arguments.

## 5. Classifying Commands by Impact Level

JDK 26 documents an impact level for each diagnostic command. This is an estimated guideline; actual impact depends on heap size, thread count, number of classes, and application load.

| Level | Examples | Usage |
|---|---|---|
| Low | VM.version, VM.uptime, VM.flags, VM.info | Generally suitable for initial checks |
| Medium | Thread.print, GC.heap_info, VM.native_memory | Run when investigating a specific diagnostic question |
| High | GC.class_histogram, GC.heap_dump | Plan ahead; control pauses, disk usage, and output data |

Impact level does not equate to data sensitivity. A low-impact command like `VM.system_properties` can still output sensitive configuration details.

### Low-Impact Commands to Start With

~~~bash
jcmd 2125 VM.version
jcmd 2125 VM.uptime
jcmd 2125 VM.flags
jcmd 2125 VM.info
~~~

These commands reveal the JVM version, uptime, flags, and status information without creating a heap dump.

### Commands Requiring More Consideration

~~~bash
jcmd 2125 GC.heap_info
jcmd 2125 Thread.print
~~~

`GC.heap_info` has a Medium impact level. `Thread.print` is also Medium and scales with the number of threads. For applications with a very large number of platform threads or virtual threads, the output can be huge.

### High-Impact Commands

~~~bash
jcmd 2125 GC.class_histogram
jcmd 2125 GC.heap_dump /secure/diagnostics/heap.hprof
~~~

`GC.class_histogram` is classified as High impact in JDK 26. `GC.heap_dump` is also High and depends on heap size and contents. By default, a heap dump requests a full GC unless the `-all` option is used to dump unreachable objects as well.

Do not run these commands repeatedly at short intervals in production. Before executing them, verify sufficient disk space, write permissions, acceptable pause duration, and a secured output location.

## 6. Commonly Used Status Inspection Commands

### VM.version

Prints the JVM version:

~~~bash
jcmd 2125 VM.version
~~~

Use this to confirm that the target JVM is running the expected JDK release.

### VM.uptime

Prints how long the JVM has been running:

~~~bash
jcmd 2125 VM.uptime
~~~

Uptime helps put metrics such as thread count, heap usage, or class loading into operational context.

### VM.flags

Prints active VM flags and their current values:

~~~bash
jcmd 2125 VM.flags
~~~

View all flags supported by the JVM:

~~~bash
jcmd 2125 VM.flags -all
~~~

The output helps identify heap size, GC, diagnostic settings, and effective options. Do not share output if it reveals internal paths, configuration, or sensitive details.

### VM.info

~~~bash
jcmd 2125 VM.info
~~~

Prints JVM environment and state information.

### VM.command_line

~~~bash
jcmd 2125 VM.command_line
~~~

Prints the command line used to start the JVM. Treat this as sensitive data because some applications may improperly pass tokens, passwords, or secrets via command-line arguments.

### VM.system_properties

~~~bash
jcmd 2125 VM.system_properties
~~~

Prints the JVM's system properties. The output can span hundreds of lines. Properties such as endpoints, file paths, usernames, or application-defined secrets may appear in the results.

Collect only what is truly needed and redact sensitive data before sharing.

## 7. Using Thread.print to Investigate Threads

`Thread.print` prints platform threads and mounted virtual threads along with their stack traces.

~~~bash
jcmd 2125 Thread.print
~~~

To also print `java.util.concurrent` lock information:

~~~bash
jcmd 2125 Thread.print -l
~~~

This command is useful when:

- The application is responding slowly.
- Threads remain `BLOCKED` for a long time.
- Multiple threads are waiting on the same monitor.
- A deadlock is suspected.
- You need to see which method a thread is executing or waiting in.

### Reading a Thread Dump

A thread dump typically contains:

- Thread name.
- Thread state such as `RUNNABLE`, `WAITING`, `TIMED_WAITING`, or `BLOCKED`.
- Stack trace.
- Monitors/locks held or awaited, when available.

Example output:

~~~text
"main" #1 prio=5 os_prio=0
   java.lang.Thread.State: WAITING
    at java.lang.Object.wait(Native Method)

"pool-1-thread-1" #21
   java.lang.Thread.State: RUNNABLE
    at com.acme.service.ReportService.generate(ReportService.java:42)
~~~

Do not conclude there is a deadlock from a single thread in `WAITING`. Inspect lock relationships, take multiple thread dumps over time, and check application state.

For applications with many threads, dumps can be very large. If the goal is to observe trends, JFR or continuous observability tools may be more appropriate than repeated thread dumps.

## 8. Inspecting the Heap and Class Histograms

### GC.heap_info

~~~bash
jcmd 2125 GC.heap_info
~~~

Provides summary information about the Java heap. Use it to check heap state before deciding whether deeper data collection is needed.

### GC.class_histogram

~~~bash
jcmd 2125 GC.class_histogram
~~~

Prints object statistics by class in the Java heap. Classes with the highest instance counts or memory usage typically appear at the top.

JDK 26 classifies this command as High impact. Cost depends on heap size and contents; run it only with a clear reason and prepare for the impact on the application.

The `-all` option inspects unreachable objects as well:

~~~bash
jcmd 2125 GC.class_histogram -all
~~~

Use `-all` only when you understand the difference between reachable and unreachable objects. Results can differ significantly.

### GC.heap_dump

~~~bash
jcmd 2125 GC.heap_dump /secure/diagnostics/heap-2125.hprof
~~~

Creates a heap dump in HPROF format. This is valuable for investigating memory leaks, retained objects, and the object graph.

Impact and risks:

- JDK 26 classifies `GC.heap_dump` as High impact.
- By default, the command requests a full GC unless `-all` is specified.
- The dump file can be nearly as large as the live heap data to be written.
- Creating the dump can cause a significant pause.
- The dump may contain tokens, passwords, user data, request payloads, and sensitive in-memory objects.

Before dumping:

1. Confirm the right process and environment.
2. Check available disk space.
3. Choose a directory readable only by authorized personnel.
4. Avoid unintentionally overwriting existing files.
5. Encrypt or protect the file according to data retention policies.
6. Set a retention period and securely delete the file once the investigation ends.

Never upload heap dumps to public file-sharing services or attach them to tickets without access controls.

## 9. Using Java Flight Recorder via jcmd

JFR collects events about the JVM and application over time. jcmd supports starting, checking, dumping, and stopping recordings.

### Checking Active Recordings

~~~bash
jcmd 2125 JFR.check
~~~

### Starting a Short Recording

~~~bash
jcmd 2125 JFR.start name=incident settings=default duration=120s filename=/secure/diagnostics/incident.jfr
~~~

The JDK provides two common configurations:

| Settings | Characteristics |
|---|---|
| default.jfc | Collects a predefined set of events with low overhead; suitable for continuous recording |
| profile.jfc | Collects more data with higher overhead; use for short periods when detailed data is needed |

If you need to stop a recording before its duration expires:

~~~bash
jcmd 2125 JFR.stop name=incident filename=/secure/diagnostics/incident-final.jfr
~~~

If you need to export a snapshot while the recording continues:

~~~bash
jcmd 2125 JFR.dump name=incident filename=/secure/diagnostics/incident-snapshot.jfr
~~~

`JFR.dump` writes data to a file while keeping the recording running.

### Limiting JFR Overhead

- Choose `default.jfc` for lightweight collection.
- Use `profile.jfc` for short, targeted sessions.
- Set `duration`, `maxage`, or `maxsize` to bound time and size where appropriate.
- Do not enable `path-to-gc-roots` casually; collecting GC root paths can cause pauses and take significant time.
- Protect `.jfr` files because events may contain information about the system, threads, classes, I/O, and application activity.

JFR helps investigate CPU, allocations, GC, lock contention, I/O, and time-series events that a single snapshot cannot capture.

## 10. Native Memory Tracking via jcmd

Native Memory Tracking (NMT) tracks internal allocations of the HotSpot JVM. NMT does not fully track native allocations from JNI or third-party native libraries.

NMT must be enabled at JVM startup:

~~~bash
java -XX:NativeMemoryTracking=summary -jar app.jar
~~~

Or enabled at detail level:

~~~bash
java -XX:NativeMemoryTracking=detail -jar app.jar
~~~

NMT cannot be enabled or restarted via jcmd after the JVM is already running.

### Viewing the Summary

~~~bash
jcmd 2125 VM.native_memory summary
~~~

### Setting a Baseline

After the application warms up:

~~~bash
jcmd 2125 VM.native_memory baseline
~~~

### Comparing Against the Baseline

~~~bash
jcmd 2125 VM.native_memory summary.diff
~~~

Or view the detail diff if the JVM was started with NMT `detail`:

~~~bash
jcmd 2125 VM.native_memory detail.diff
~~~

NMT helps identify which JVM native memory category is growing, such as Java Heap, Class, Thread, Code, GC, or Compiler.

### NMT Overhead

Oracle notes that enabling NMT can reduce JVM performance by roughly 5–10% and increase tracking memory usage. Evaluate the overhead before enabling it in production.

NMT only tracks JVM/HotSpot memory allocations within its supported scope. If JNI or a native library is leaking memory, combine NMT with OS tools or a native profiler.

## 11. Commands That Can Modify JVM State

Some diagnostic commands are not read-only. Review them carefully before running:

| Command | Action | Notes |
|---|---|---|
| GC.run | Calls `System.gc()` | Can cause a GC pause and alter load |
| GC.run_finalization | Calls `System.runFinalization()` | Can trigger finalization work |
| VM.set_flag | Modifies a VM flag | Can change JVM behavior or performance |
| VM.log | Enables, disables, reconfigures, or rotates logs | Modifies process logging |
| JVMTI.agent_load | Loads a native JVMTI agent | The agent can deeply interfere with the JVM |
| ManagementAgent.start | Starts the remote management agent | Exposes an additional management surface; requires network and authentication setup |
| JFR.start | Starts a recording | Collects events and consumes resources |
| JFR.stop | Stops a recording | May write a file or discard recording data depending on parameters |

Do not use these commands as default diagnostic checks. Before running them, define the purpose, owner, effective duration, rollback plan, and service impact.

In particular, do not use `ManagementAgent.start` to casually open remote JMX. If remote management is required, enforce authentication, TLS, network restrictions, and proper authorization.

## 12. Protecting Output and Sensitive Information

Diagnostic output is production data. It can expose:

- Internal file paths and hostnames.
- JVM arguments and system properties.
- Class, package, thread, and method names.
- System architecture, dependencies, and runtime configuration.
- User data or secrets residing in the heap.
- Traces of application activity in JFR recordings.

Recommended safeguards:

1. Write output to a directory with restricted access permissions.
2. Never store dumps in a web root or publicly shared directory.
3. Never send raw `VM.command_line` or `VM.system_properties` output over unprotected channels.
4. Avoid placing secrets in command-line arguments in the first place.
5. Enforce retention limits for heap dumps, thread dumps, and JFR files.
6. Encrypt diagnostic data at rest and in transit according to organizational policy.
7. Redact or remove sensitive data before sharing.
8. Log who collected the data, when, which PID, with which command, and where the file is stored.

Access to run jcmd should follow the principle of least privilege. Anyone with attach permission can request sensitive data from the JVM or execute state-modifying commands on the process.

## 13. Using a Command File with -f

jcmd supports reading and executing commands from a file:

~~~bash
jcmd 2125 -f diagnostics.txt
~~~

Example `diagnostics.txt` contents:

~~~text
VM.version
VM.uptime
VM.flags
GC.heap_info
~~~

This is useful when repeating an approved set of checks.

Safety rules:

- Read the entire file before running it.
- Include only necessary commands.
- Never run a command file received from an untrusted source.
- Do not include state-modifying commands without prior approval.
- Explicitly record the target PID and owner.
- Never use PID 0 to run a command file across all JVMs.

A command file is not a sandbox. If the file contains `GC.heap_dump`, `VM.set_flag`, or `JVMTI.agent_load`, jcmd will execute those commands on the target process if supported by the JVM.

## 14. Java 17+ Example: Running an Application and Inspecting with jcmd

Create the directory structure:

~~~text
project/
  src/
    com/acme/DemoServer.java
  out/
~~~

File `src/com/acme/DemoServer.java`:

~~~java
package com.acme;

import java.util.concurrent.CountDownLatch;

public final class DemoServer {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("READY");
        new CountDownLatch(1).await();
    }
}
~~~

Compile:

~~~bash
javac --release 17 -d out src/com/acme/DemoServer.java
~~~

Run the application:

~~~bash
java -cp out com.acme.DemoServer
~~~

Stdout:

~~~text
READY
~~~

The program waits indefinitely to keep the JVM alive during practice. Open a second terminal and list processes:

~~~bash
jcmd -l
~~~

Find the PID of `com.acme.DemoServer` and substitute it into the commands below:

~~~bash
jcmd 2125 VM.version
jcmd 2125 VM.uptime
jcmd 2125 VM.flags
jcmd 2125 help Thread.print
jcmd 2125 Thread.print
~~~

PID `2125` is only an example. Use the actual PID shown on your machine.

When finished, return to the terminal running `DemoServer` and press `Ctrl+C` to stop the test program.

This example uses only inspection commands and a thread dump. Neither a heap dump nor VM flag changes are needed to practice the basic safe workflow.

## 15. Safe Production Workflow for jcmd

1. **Define the incident**: clarify whether you need JVM version, thread state, heap, native memory, or time-series events.
2. **Confirm the environment**: host, container, service name, JDK release, and collection timestamp.
3. **Select the right process**: use `jcmd -l` or OS tools; verify the PID and command line.
4. **Verify process identity**: use `VM.version`, `VM.uptime`, and `VM.command_line` if needed.
5. **Discover commands**: run `help` and `help <command>` on the target JVM.
6. **Start with low-impact commands**: `VM.version`, `VM.uptime`, `VM.flags`, or `VM.info`.
7. **Escalate collection only with a clear question**: `Thread.print`, heap histogram, heap dump, JFR, or NMT.
8. **Estimate impact**: pause duration, CPU, disk space, output size, and data sensitivity.
9. **Store output safely**: protected directory, filename with PID/timestamp, and clear retention.
10. **Verify the output**: check that the file was created, is complete, and contains no data beyond sharing permissions.
11. **Stop recordings or temporary settings**: use `JFR.stop` or restore logging/flags if modified.
12. **Document the action**: command, operator, process, timestamp, impact, and output location.

If a service is already overloaded or experiencing a severe outage, prioritize low-impact commands and avoid creating large heap dumps before assessing pause tolerance and disk capacity.

## 16. Troubleshooting When jcmd Does Not Work

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `jcmd` not recognized | `PATH` does not include the JDK `bin` directory | Verify JDK installation and `PATH` |
| Process missing from `jcmd -l` | JVM is in a separate Docker process or different PID namespace | Use `ps` in the right namespace or run `jcmd` inside the container |
| Attach failed or permission denied | Different effective user/group or OS permissions | Run with the matching account and check permissions |
| Cannot attach to JVM | JVM started with `DisableAttachMechanism` | Check startup flags; attach cannot be enabled from `jcmd` |
| Unknown diagnostic command | Target JVM does not provide that command | Run `jcmd PID help` to list available commands |
| Invalid option | Syntax differs for the target command | Run `help` for that specific command and verify options/arguments |
| PID no longer exists | Process exited or PID changed | Re-list processes and confirm the new PID |
| Command takes a long time | Large heap, many threads, or high-impact command | Stop retrying repeatedly; assess impact and wait for the current command |
| Cannot write heap dump | Directory lacks write permission or disk is full | Choose an authorized directory and check disk space |
| `VM.native_memory` has no data | NMT was not enabled at JVM startup | Restart with NMT if the overhead is acceptable |
| `JFR.start` not supported | JDK/provider or JVM does not support the command | Check `help` and target JVM capabilities |
| Output contains sensitive data | Command line, properties, heap, or recording holds internal data | Restrict access, redact before sharing, and enforce retention |

## 17. Pre-Flight Checklist Before Sending a Diagnostic Command

- [ ] Identified the correct host, container, and PID.
- [ ] Confirmed the process belongs to the right service.
- [ ] Used an account with the matching effective user/group.
- [ ] Checked `jcmd help` on the target JVM.
- [ ] Understood the command's impact level.
- [ ] Avoided PID 0 and main-class selectors when multiple processes could match.
- [ ] Assessed CPU, pause, disk, and output size impact.
- [ ] Chosen a secured output directory.
- [ ] Accounted for sensitive data in command line, properties, thread dumps, heap dumps, and JFR.
- [ ] Set recording duration or size limits where appropriate.
- [ ] Know how to stop recordings or revert changes.
- [ ] Recorded the command, operator, timestamp, and outcome.

## 18. Key Takeaways

- jcmd sends diagnostic commands to a running JVM; it is not a remote debugger.
- jcmd must run on the same machine and under the same effective user/group as the target JVM.
- `jcmd -l` lists Java processes, but does not list JVMs in separate Docker processes.
- Target a specific PID; main-class names can match multiple processes, and PID 0 sends commands to every available JVM.
- Always use `help` and `help <command>` to confirm commands, options, and arguments on the target JVM.
- `VM.version`, `VM.uptime`, `VM.flags`, and `VM.info` are low-impact starting checks.
- `Thread.print` has Medium impact; `GC.class_histogram` and `GC.heap_dump` are classified as High impact in the JDK 26 manual.
- Heap dumps may trigger a full GC and contain sensitive in-memory data.
- JFR `default.jfc` has low overhead; `profile.jfc` collects more data with higher overhead.
- NMT must be enabled at JVM startup; enabling NMT can reduce performance by roughly 5–10%.
- `GC.run`, `VM.set_flag`, `VM.log`, `JVMTI.agent_load`, and `ManagementAgent.start` can alter process state or management surfaces.
- Diagnostic output is sensitive data; protect access permissions, storage locations, and retention periods.
- Use jcmd deliberately: right process, right command, right impact level, and right purpose.

## Official References

- [The jcmd Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html)
- [Diagnostic Tools — JDK 26](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html)
- [The java Command: DisableAttachMechanism — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [Native Memory Tracking — JDK 26](https://docs.oracle.com/en/java/javase/26/vm/java-virtual-machine-guide.pdf)
- [Troubleshooting Memory Leaks — JDK 26](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshooting-memory-leaks.html)
