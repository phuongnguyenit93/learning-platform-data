# The jcmd Command: Sending VM Commands to a Running JVM

## Objectives

After this lesson, you will be able to find a JVM process and send diagnostic commands to a running Java process; discover the commands supported by the target JVM; inspect version, flags, system properties, uptime, threads, heap, class loaders, and metaspace; generate heap dumps; collect Java Flight Recorder (JFR) recordings; use Native Memory Tracking (NMT); understand the impact of each command; and apply jcmd in a safe diagnostic workflow.

## 1. What is jcmd?

**jcmd** is a command-line tool included with the JDK used to send diagnostic command requests to a running Java Virtual Machine (JVM). The target JVM executes the diagnostic operation and returns the result to the tool.

Common uses for jcmd:

- Listing JVM processes and identifying their PIDs.
- Discovering the commands supported by the target JVM.
- Inspecting the JVM version, command line, flags, and system properties.
- Printing thread dumps to investigate slow, hung, or deadlocked applications.
- Viewing heap information and class histograms.
- Generating heap dumps to analyze memory leaks.
- Starting, checking, dumping, and stopping Java Flight Recordings.
- Viewing native memory if NMT is enabled.
- Inspecting class loaders, metaspace, code cache, and VM logging.

jcmd is very useful when you need to investigate a running JVM without stopping the application or restarting it with new diagnostic options. However, not every diagnostic command is impact-free for the application. Some commands can cause pauses, trigger garbage collection, create large files, or alter runtime configuration.

## 2. Syntax and Selecting the Target JVM

General syntax:

~~~bash
jcmd [pid | main-class] command [arguments]
~~~

Main usage forms:

~~~bash
jcmd -l
jcmd <pid>
jcmd <pid> help
jcmd <pid> help <command>
jcmd <pid> <command> [options] [arguments]
jcmd <pid> -f commands.txt
~~~

Where:

- pid: process ID of the target JVM.
- main-class: name of the main class used to launch the application; can be a partial or full match.
- command: diagnostic command supported by the target JVM.
- arguments: arguments for the diagnostic command.
- -f: read and execute commands from a file.

### Listing JVM processes

~~~bash
jcmd -l
~~~

This command displays the PID, main class, and command-line arguments of the Java processes found by jcmd. Running jcmd without arguments is equivalent to jcmd -l.

Example output:

~~~text
4128 com.example.OrderService
7852 org.apache.catalina.startup.Bootstrap
9011 jdk.jcmd/sun.tools.jcmd.JCmd
~~~

The PIDs and process names on a real machine will differ from this example. jcmd itself often appears in the list because the tool runs on a JVM.

In some Docker environments, jcmd -l does not list JVMs running in a separate Docker process. In that case, identify the PID using an OS tool such as ps inside the appropriate container/PID namespace, then run jcmd in an environment that can attach to that process.

### Selecting by PID or main class

~~~bash
jcmd 4128 VM.version
jcmd com.example.OrderService VM.version
~~~

Using the PID is the clearest approach when a machine has multiple applications with the same main class. If the main class matches multiple Java processes, the command may be sent to all matching processes.

### Sending a command to all JVM processes

~~~bash
jcmd 0 VM.uptime
~~~

PID 0 means sending the command to all available Java processes. Only use this when you genuinely want to collect information from every JVM; do not use it arbitrarily with commands that create dumps, trigger GC, or change configuration.

### Viewing help

~~~bash
jcmd -h
jcmd 4128 help
jcmd 4128 help Thread.print
~~~

The list of commands depends on the JVM, JDK version, vendor, OS, and runtime configuration. Always run help on the target JVM itself before relying on a specific command.

## 3. Conditions for jcmd to Attach to a JVM

According to the JDK documentation, jcmd must run on the **same machine** as the target JVM and have the same effective user ID and group ID used to launch the JVM.

Practical conditions to check:

- Use the correct JVM PID—do not confuse it with the PID of a shell, container host, or another process.
- jcmd and the JVM must be in an environment where they can communicate via the platform's attach mechanism.
- The user running jcmd must have an effective UID/GID matching the user running the JVM.
- The process must allow attaching; a JVM can be launched with -XX:+DisableAttachMechanism, which disables diagnostic command attach.
- For containers, ensure the correct PID namespace, user, access permissions, and execution location for the tool.
- The target JVM must be alive and responsive to attach requests.

jcmd is not a tool for sending arbitrary commands to a JVM from a remote machine. For remote administration, another mechanism such as properly configured and secured JMX or the application's observability/management system is required.

If jcmd cannot attach, check the environment conditions and the actual error message before changing permissions or restarting the service.

## 4. Discovering Diagnostic Commands on the Target JVM

### Listing and viewing command details

~~~bash
jcmd <pid> help
jcmd <pid> help GC.heap_dump
jcmd <pid> help Thread.print
jcmd <pid> help JFR.start
~~~

The help output describes the syntax, option names, data types, required/optional arguments, default values, and Impact level if the command publishes that information.

### Rules for passing options and arguments

Diagnostic commands can accept options and arguments:

- Options use the form key or key=value, depending on the command.
- Arguments are passed as values, without writing name=value unless the command documentation requires it.
- If a value contains spaces, enclose it in single or double quotes according to shell syntax.
- Quotes must be escaped when the value itself contains quotes.

Example of options with values:

~~~bash
jcmd <pid> VM.classloaders show-classes=true verbose=true
~~~

Example of an argument that is a filename:

~~~bash
jcmd <pid> GC.heap_dump heap.hprof
~~~

Option names, hyphenation, and argument types can vary between commands. Use jcmd <pid> help <command> to confirm the syntax on the JVM you are inspecting.

## 5. Inspecting JVM Information and Configuration

The commands below typically have low impact and are suitable for starting an investigation.

### VM.version

~~~bash
jcmd <pid> VM.version
~~~

Prints JVM/HotSpot and JDK version information. Useful when the process was launched from a different JDK than the one in PATH.

### VM.command_line

~~~bash
jcmd <pid> VM.command_line
~~~

Prints the command line used to launch the JVM. This helps confirm the main class/JAR, heap options such as -Xms and -Xmx, -D... system properties, module/class path, JVM flags, and agent options.

The command line may contain tokens, passwords, or sensitive values if the application is misconfigured. Protect the output and redact secrets before sharing.

### VM.flags

~~~bash
jcmd <pid> VM.flags
jcmd <pid> VM.flags -all
~~~

Prints VM flags along with their current values. The -all option requests displaying all flags supported by the VM.

### VM.system_properties

~~~bash
jcmd <pid> VM.system_properties
~~~

Prints the JVM's system properties, such as java.home, java.version, os.name, os.arch, user.dir, file.encoding, and application properties set via -Dname=value.

The output can be very long and may contain internal endpoints, usernames, file paths, tokens, or sensitive information. Do not post the raw output to public tickets or chats.

### VM.uptime and VM.info

~~~bash
jcmd <pid> VM.uptime
jcmd <pid> VM.info
~~~

VM.uptime prints how long the JVM has been running, which is useful for correlating with deployment, restart, or incident start times. VM.info prints an overview of the JVM environment and state.

### VM.log

~~~bash
jcmd <pid> VM.log list=true
~~~

Lists the current logging configuration. VM.log can also configure outputs, tags, decorators, or log rotation. Because this command can alter runtime logging, read its help and only modify configuration when you have a clear plan.

## 6. Thread Dumps and Hung Applications

A thread dump shows what state each thread is in and which stack frame it is executing. This is essential data when an application is hung, requests are slow, a thread pool is exhausted, or a deadlock is suspected.

### Printing a thread dump

~~~bash
jcmd <pid> Thread.print
~~~

This command prints platform threads and mounted virtual threads along with their stack traces.

Print additional lock information:

~~~bash
jcmd <pid> Thread.print -l
~~~

The -l option requests printing lock information from java.util.concurrent along with the thread dump.

### Saving a thread dump to a file

~~~bash
jcmd <pid> Thread.dump_to_file threads.txt
jcmd <pid> Thread.dump_to_file -format=json threads.json
~~~

This command writes threads and their stack traces to a file. The impact depends on the number of threads.

### How to read a thread dump

1. Look for threads in the BLOCKED, WAITING, or TIMED_WAITING state.
2. Inspect stack traces to see which lock, I/O, queue, or condition a thread is waiting on.
3. Look for multiple threads waiting on the same monitor or lock.
4. Check whether RUNNABLE threads are looping in the same stack frame or processing a single task for too long.
5. Compare multiple thread dumps taken at intervals to identify stuck states.
6. Correlate thread names with requests, executors, schedulers, or application subsystems.

A thread in the WAITING state does not automatically indicate an error; worker threads normally wait for tasks. You need to understand each thread's role and compare it against its expected state.

### Virtual threads

Recent JDKs support diagnostic commands related to virtual threads:

~~~bash
jcmd <pid> Thread.vthread_scheduler
jcmd <pid> Thread.vthread_pollers
~~~

Thread.vthread_scheduler prints information about the virtual-thread scheduler and delayed-task scheduler. Thread.vthread_pollers prints the I/O pollers supporting virtual threads during blocking network operations. These commands are only available on JVMs that support virtual threads and the corresponding diagnostic commands.

## 7. Inspecting the Heap and Garbage Collection

### GC.heap_info

~~~bash
jcmd <pid> GC.heap_info
~~~

Prints general information about the Java heap. This is a useful snapshot to start checking heap usage, but it does not replace a heap dump or GC log analysis.

### GC.class_histogram

~~~bash
jcmd <pid> GC.class_histogram
jcmd <pid> GC.class_histogram -all
~~~

Prints a histogram of instance counts and heap usage by class. The -all option requests inspecting unreachable objects as well. According to the JDK 26 documentation, this command has high impact, depending on heap size and contents.

You can save the output using shell redirection:

~~~bash
jcmd <pid> GC.class_histogram > class-histogram.txt
~~~

### GC.heap_dump

~~~bash
jcmd <pid> GC.heap_dump heap.hprof
~~~

Generates a heap dump in HPROF format to open with heap analysis tools such as Java Mission Control, Eclipse Memory Analyzer, or compatible tools.

According to the JDK 26 documentation, this command has high impact; by default it requests a full GC unless the -all option is used. Heap dumps can be very large, cause pauses, and contain sensitive application data.

You can compress the output:

~~~bash
jcmd <pid> GC.heap_dump -gz=1 heap.hprof.gz
~~~

The -overwrite option allows overwriting an existing file; do not enable it without confirming the target path and file contents.

Before generating a heap dump, verify sufficient disk space, directory write permissions, a secure storage location, and file transfer procedures. Heap dumps may contain passwords, access tokens, personal data, and request payloads.

### GC.run

~~~bash
jcmd <pid> GC.run
~~~

This command calls System.gc() in the target JVM. It is a GC request, not a guarantee that a specific full GC cycle will run. Do not use it as a periodic way to "free RAM" or conclude that a memory leak has been fixed.

| Goal | Command | Impact according to JDK 26 docs |
|---|---|---|
| View heap overview | GC.heap_info | Medium |
| View object counts by class | GC.class_histogram | High |
| Take full heap snapshot | GC.heap_dump | High |
| Request System.gc() | GC.run | Medium |

Start with GC.heap_info; only use histograms or heap dumps when deeper data is needed and the impact has been evaluated.

## 8. Tracking Native Memory with Native Memory Tracking

The Java heap is only part of a process's memory. The JVM also uses native memory for thread stacks, metaspace, code cache, GC, the compiler, and other subsystems. An application's native libraries can also allocate memory outside the heap.

**Native Memory Tracking (NMT)** is a HotSpot VM feature that tracks internal memory used by the JVM/HotSpot. NMT is disabled by default and must be enabled at JVM startup.

### Enabling NMT at startup

Summary mode:

~~~bash
java -XX:NativeMemoryTracking=summary -jar app.jar
~~~

Detail mode:

~~~bash
java -XX:NativeMemoryTracking=detail -jar app.jar
~~~

- summary: tracks aggregated memory by subsystem.
- detail: adds more granular data by call site and memory region.
- off: disables tracking; this is the default.

NMT cannot be enabled or restarted using jcmd after the JVM is already running. If the current process was launched with NMT off, you must plan a restart with the appropriate startup option to collect NMT data.

NMT incurs overhead and should be evaluated before enabling in production. It also does not fully track allocations from third-party native code/JNI or all native libraries.

### Viewing native memory and comparing baselines

~~~bash
jcmd <pid> VM.native_memory summary
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary.diff
~~~

If detail mode is enabled:

~~~bash
jcmd <pid> VM.native_memory detail.diff
~~~

A baseline serves as a reference point for comparing subsequent changes. Diff data helps identify which subsystem is growing in memory over time. A single snapshot is not enough to conclude there is a leak; collect multiple data points under similar load conditions.

NMT tracks internal HotSpot/JVM memory, not the total memory counter for the entire process. If the process's RSS grows but NMT cannot explain it, check native libraries, direct buffers, memory mappings, and OS tools.

## 9. Collecting Java Flight Recordings with jcmd

Java Flight Recorder (JFR) records JVM and application events to analyze performance, latency, allocations, threads, GC, and many other runtime activities.

JFR commands in jcmd:

- JFR.start: starts a recording.
- JFR.check: checks running recordings.
- JFR.dump: writes current recording data to a file while the recording continues.
- JFR.stop: stops a recording and optionally writes data to a file.
- JFR.configure: views or configures JFR parameters.
- JFR.view: displays data using built-in views.

### Starting a time-bounded recording

~~~bash
jcmd <pid> JFR.start name=diagnostic settings=profile duration=2m filename=diagnostic.jfr
~~~

- name: recording name for later reference.
- settings=profile: selects the built-in profile configuration.
- duration=2m: the recording automatically stops after two minutes.
- filename: where to write the recording when it finishes.

You can set maxage and maxsize to limit data stored on disk when the recording uses a disk repository:

~~~bash
jcmd <pid> JFR.start name=bounded settings=profile maxage=10m maxsize=250M
~~~

Choose settings appropriate for the investigation goal. The profile configuration may collect more events than the default configuration; consider overhead and file size.

### Checking recordings

~~~bash
jcmd <pid> JFR.check
~~~

Displays active recordings. You can specify name=diagnostic or verbose=true to see more event settings.

### Dumping data while keeping the recording running

~~~bash
jcmd <pid> JFR.dump name=diagnostic filename=diagnostic-snapshot.jfr
~~~

JFR.dump writes current data to a file; the recording continues running. You can dump a specific time range using begin, end, maxage, or limit the size according to the syntax supported by the command.

The path-to-gc-roots=true option can be useful when a memory leak is suspected, but collecting paths to GC roots can cause the application to pause for a period of time. Only enable it when you have a clear investigative goal.

### Stopping a recording and saving the file

~~~bash
jcmd <pid> JFR.stop name=diagnostic filename=diagnostic-final.jfr
~~~

If you stop a recording without specifying filename, the data may be discarded. Check the command help and verify that the output file has been created.

You can open .jfr files with Java Mission Control (JMC) or use the JDK's jfr tool to read and export data. jcmd manages recordings on a running JVM; the jfr tool processes recorded files.

## 10. Inspecting Class Loaders, Classes, and Metaspace

When an application uses plugins, an application server, dynamic class loading, or has a suspected class loader leak, the following commands are useful.

### VM.classloader_stats and VM.classloaders

~~~bash
jcmd <pid> VM.classloader_stats
jcmd <pid> VM.classloaders
jcmd <pid> VM.classloaders show-classes=true verbose=true
~~~

VM.classloader_stats prints statistics for ClassLoaders. VM.classloaders prints the class loader hierarchy; the show-classes and verbose options provide additional details.

### VM.classes and VM.class_hierarchy

~~~bash
jcmd <pid> VM.classes
jcmd <pid> VM.class_hierarchy com.example.Order
~~~

VM.classes prints loaded classes. The -verbose option requests more detailed class information; the output can be very large.

VM.class_hierarchy prints the hierarchy of a specific class. You can use -s to display subclasses along with superclasses and -i to print inherited interfaces.

### VM.metaspace

~~~bash
jcmd <pid> VM.metaspace basic=true scale=MB
~~~

Prints metaspace statistics. You can request information by class loader or class when detailed investigation is needed; check jcmd <pid> help VM.metaspace to see options supported by the target JVM.

If the number of classes or class loaders grows continuously after each deploy/reload, compare histograms, classloader stats, and metaspace across multiple points in time. Uncollected class loaders can retain classes and metadata.

## 11. Other Useful Diagnostic Commands

| Command | Purpose |
|---|---|
| Compiler.queue | Prints methods waiting for JIT compilation |
| Compiler.CodeHeap_Analytics | Analyzes the code heap |
| VM.dynlibs | Lists loaded dynamic libraries |
| VM.events | Prints the VM event log |
| VM.stringtable | Dumps the string table |
| VM.symboltable | Dumps the symbol table |
| VM.cds | Creates a static/dynamic CDS archive under appropriate conditions |
| ManagementAgent.status | Views management agent status |
| ManagementAgent.start_local | Starts the local management agent |
| ManagementAgent.start | Starts the remote management agent |
| ManagementAgent.stop | Stops the management agent |

Some commands are only available on Linux, and some only appear when supported by the VM/provider or when required startup options were set. In particular, ManagementAgent.start can expose a remote administration surface; do not enable remote JMX without configuring authentication, authorization, TLS, network binding, and firewall rules according to policy.

Commands such as JVMTI.agent_load, GC.run, VM.log, or VM.set_flag can modify JVM state. Read the help and assess risks before running them on production services.

## 12. Running Multiple Commands from a File

You can save commands in a text file, with one diagnostic command per line:

~~~text
VM.version
VM.uptime
VM.flags
GC.heap_info
Thread.print
~~~

Send the file to the JVM:

~~~bash
jcmd <pid> -f diagnostics.txt
~~~

This is convenient for a standard snapshot bundle. However, classify commands by impact level before putting them into a shared file. Do not include heap dumps, class histograms, or configuration-changing commands in periodic collection scripts without evaluating their impact.

## 13. Complete Practical Example: Creating a Target JVM and Diagnosing with jcmd

This example creates a continuously running Java program so you have time to attach from another terminal.

Create DiagnosticTarget.java:

~~~java
public class DiagnosticTarget {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("pid=" + ProcessHandle.current().pid());
        System.out.println("jcmd-target-ready");

        while (true) {
            Thread.sleep(1_000);
        }
    }
}
~~~

### Compile

Using JDK 17 or later:

~~~bash
javac --release 17 DiagnosticTarget.java
~~~

### Launch the target JVM

Terminal A:

~~~bash
java DiagnosticTarget
~~~

Output:

~~~text
pid=<PID of the running JVM>
jcmd-target-ready
~~~

The PID changes on every run. Keep Terminal A active so the JVM continues running.

### Find the PID and view help

Terminal B:

~~~bash
jcmd -l
jcmd <PID> help
jcmd <PID> help VM.uptime
~~~

Replace <PID> with the number printed in Terminal A.

### Inspect the JVM

~~~bash
jcmd <PID> VM.version
jcmd <PID> VM.uptime
jcmd <PID> VM.flags
jcmd <PID> VM.system_properties
~~~

### Print a thread dump

~~~bash
jcmd <PID> Thread.print
~~~

Because the program is sleeping, the main thread typically shows stack frames related to Thread.sleep. This is the normal waiting state for the example, not a deadlock.

### View heap and class histogram

~~~bash
jcmd <PID> GC.heap_info
jcmd <PID> GC.class_histogram
~~~

Histograms have higher impact than heap info. Only run them when you need to inspect objects on the heap.

### Record JFR for two minutes

~~~bash
jcmd <PID> JFR.start name=lab settings=profile duration=2m filename=lab.jfr
jcmd <PID> JFR.check
~~~

After the recording finishes, open lab.jfr with JDK Mission Control or a compatible JFR tool.

### Stop the target JVM

Return to Terminal A and press Ctrl+C. There is no need to send GC.run or another command to stop the sample program.

This example illustrates the workflow for attaching to a running JVM. In a production environment, use the correct PID, check available commands, and choose diagnostic commands based on their impact.

## 14. Choosing Commands by Incident Scenario

| Scenario | First step | Next step |
|---|---|---|
| Application responding slowly | VM.uptime, VM.flags, Thread.print | JFR.start and analyze the recording |
| Suspected deadlock | Thread.print -l | Compare multiple thread dumps and lock owners |
| Heap growing continuously | GC.heap_info | GC.class_histogram, then heap dump if needed |
| Suspected memory leak | JFR and histograms over time | Heap dump, analyze dominator/retained size |
| High process RSS but small heap | VM.native_memory summary if NMT is enabled | Compare baseline/diff and use OS tools |
| Metaspace growing | VM.classloader_stats, VM.metaspace | VM.classloaders show-classes=true |
| JVM using wrong configuration | VM.command_line, VM.flags, VM.system_properties | Compare against deployment config |
| Abnormal JIT/code cache | Compiler.queue, Compiler.CodeHeap_Analytics | Collect JFR and inspect compilation events |

Do not run all commands at once. Start with low-impact commands, form a hypothesis, and only then collect heavier data.

## 15. Impact Levels and Safety in Production

The JDK 26 jcmd documentation describes the impact for each diagnostic command. Some examples:

- **Low:** VM.version, VM.uptime, VM.flags, VM.system_properties, JFR.check.
- **Medium:** Thread.print, GC.heap_info, VM.metaspace, GC.run.
- **High:** GC.class_histogram, GC.heap_dump.

Impact levels are not fixed time guarantees. Actual impact depends on heap size, thread/class counts, application load, collector, and environment.

Guidelines when running in production:

1. Confirm the PID, main class, and host/container before sending a command.
2. Start with low-impact commands and only escalate when needed.
3. Check disk space before generating a heap dump or large JFR file.
4. Choose an output directory with write permissions, appropriate quota, and retention.
5. Protect heap dumps, thread dumps, system properties, and command lines because they may contain sensitive data.
6. Do not send commands to PID 0 unless you intend to affect multiple JVMs.
7. Do not run GC.run as a routine optimization operation.
8. Do not modify VM flags, logging, or the management agent without a change plan.
9. Record the command, timestamp, PID, JDK version, and operator for audit purposes.
10. Delete or archive diagnostic data according to your organization's data policy.

If a command times out or the JVM responds slowly, do not repeatedly re-run high-impact commands. Check process status, system load, and any generated output before deciding on the next step.

## 16. Common Errors and Troubleshooting

### PID not found

**Symptom:** jcmd -l does not list the application.

**Cause:** The process is running in a different container/PID namespace, the user lacks permission to see the process, the JVM has exited, or it is not a Java process.

**Resolution:** Check processes with OS tools in the appropriate environment; identify the JVM's PID; run jcmd from the matching host/namespace.

### Attach failed or Operation not permitted

**Symptom:** jcmd cannot attach to the process.

**Cause:** Different effective UID/GID, wrong namespace, insufficient permissions, the JVM disabled the attach mechanism, or the process is unresponsive.

**Resolution:** Verify user/group, PID, container environment, and the -XX:+DisableAttachMechanism startup option; do not arbitrarily grant broad privileges or alter production configuration.

### Unknown diagnostic command

**Symptom:** The JVM reports that the command does not exist.

**Cause:** The command is not supported on that JVM/vendor/version or the command name is misspelled.

**Resolution:** Run jcmd <pid> help, then jcmd <pid> help <command>; use an equivalent command available on the target.

### Command reports invalid option/argument

**Symptom:** The command rejects the parameters.

**Cause:** Incorrect key=value syntax, wrong hyphenation, missing argument, or differences between JDK versions.

**Resolution:** Read the command help on the target JVM itself; pass options and arguments using the exact syntax listed.

### Unable to write heap dump

**Symptom:** The command reports a file creation error or out-of-space error.

**Cause:** The path does not exist, lacks write permission, the disk is full, or the file already exists without overwrite enabled.

**Resolution:** Choose a valid directory, check disk space/permissions and overwrite policy; do not unintentionally overwrite old dump files.

### Histogram or heap dump pauses the application

**Symptom:** Latency spikes during collection.

**Cause:** The command has high impact and depends on heap size/object contents; heap dump by default may request a full GC.

**Resolution:** Schedule an appropriate collection window, start with GC.heap_info, limit frequency, and only dump when necessary.

### VM.native_memory has no data

**Symptom:** NMT reports that tracking is not enabled or provides no useful information.

**Cause:** The JVM was launched with NMT off (default), or is a JVM that does not support HotSpot NMT.

**Resolution:** Plan a restart with -XX:NativeMemoryTracking=summary or detail; NMT cannot be enabled for a running process using jcmd.

### JFR fails to write file

**Symptom:** JFR.start/JFR.stop reports an error or the file does not appear.

**Cause:** Wrong recording name, missing write permission, full disk, invalid option, or the JVM does not support the requested configuration.

**Resolution:** Use JFR.check, read JFR.start help, verify filename/permissions/disk space, and inspect the output of stop/dump.

### Command line or properties contain secrets

**Symptom:** Diagnostic output contains passwords, tokens, or internal URLs.

**Cause:** Secrets were passed via -D, the command line, or system properties.

**Resolution:** Protect the output file, restrict read permissions, redact data before sharing, and move secrets to a more secure management mechanism.

## 17. Operational Checklist for jcmd

### Before running

- [ ] Confirm the correct host, container, and PID namespace.
- [ ] Identify the PID using jcmd -l or an appropriate OS tool.
- [ ] Ensure the same effective user/group as the target JVM.
- [ ] Run jcmd <pid> help to see available commands.
- [ ] Read the impact and options of the command to be run.
- [ ] Verify the output directory, write permissions, disk space, and retention.
- [ ] Assess sensitive data in the output.

### While running

- [ ] Start with VM.version, VM.uptime, VM.flags, or VM.info.
- [ ] Use Thread.print when investigating threads/blocking.
- [ ] Use heap histograms/dumps only when needed and after impact assessment.
- [ ] Use JFR with appropriate duration/maxage/maxsize.
- [ ] Only use NMT if it was enabled at JVM startup.
- [ ] Avoid sending commands to multiple processes unintentionally.
- [ ] Do not repeat heavy commands before knowing the result of the previous run.

### After running

- [ ] Verify command exit/output and that the file was actually created.
- [ ] Record the PID, JDK version, timestamp, and commands used.
- [ ] Protect thread/heap/JFR dumps according to data policy.
- [ ] Analyze data alongside logs, metrics, and the deployment timeline.
- [ ] Delete or archive diagnostic artifacts according to the retention policy.
- [ ] Summarize the root cause and next actions in the incident record.

## 18. Official References

- [The jcmd Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html) — syntax, selecting PID/main class, attach requirements, list of diagnostic commands, and command impacts.
- [Diagnostic Tools — Java SE 26 Troubleshooting Guide](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html) — common commands for inspecting the JVM, threads, heap, and JFR.
- [Troubleshoot Memory Leaks — Java SE 26](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshooting-memory-leaks.html) — histograms, heap dumps, and Java Flight Recordings when investigating memory leaks.
- [Native Memory Tracking — Java Virtual Machine Guide 26](https://docs.oracle.com/en/java/javase/26/vm/) — enabling NMT, capturing summary/detail, baselines, and diffs with jcmd.
- [Java Flight Recorder — Java SE 26](https://docs.oracle.com/en/java/javase/26/jfapi/) — JFR API and managing/reading recordings.
- [The java Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html) — JVM options such as -XX:NativeMemoryTracking and -XX:+DisableAttachMechanism.

jcmd is the practical entry point for asking a running JVM to provide diagnostic data. Discover the commands on the target JVM, start with low-impact operations, only generate dumps/recordings when needed, and protect all collected data.
