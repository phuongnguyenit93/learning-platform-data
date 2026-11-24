# 4.1 — Model for Sending a Diagnostic Command to a Running JVM

## 1. The problem: querying an active JVM without restarting it

Suppose a Java application has been running for several hours and starts responding slowly. An operator needs to know which version the JVM is running, which threads are waiting on locks, what the heap looks like, or whether any Java Flight Recorder (JFR) recording is active. Starting another Java program and printing information about **that new program itself** does not answer questions about the JVM experiencing the incident.

**`jcmd`** is a tool bundled with the JDK used to **send a diagnostic command request to a running JVM process**. In HotSpot JDK distributions, the `jcmd` process connects through the local attach mechanism, asks the target JVM to execute a command it supports, and receives the result or an error message. Each command has its own effect and impact level.

After this lesson, you should understand:

1. The roles of the **`jcmd` client**, the **target JVM's PID**, the **attach channel**, the **diagnostic command dispatcher/handler**, and the **result**.
2. The lifecycle from selecting the right JVM, opening a connection, and sending the command name/arguments to processing and receiving the response.
3. The syntax for targeting a JVM, viewing the list of commands and help from the target JVM itself; distinguishing read-only information commands from commands that mutate state or produce large data.
4. Safe practices on JDK 17+, handling attach failures, and host/container limitations.

> **Core thesis:** `jcmd` is a **client that sends requests to an already existing JVM**. It does not run arbitrary application methods on demand, does not require opening a JMX port, and does not guarantee that every command is lightweight or strictly read-only.

## 2. Components in the model

| Component | Role | Avoid confusing with |
| --- | --- | --- |
| Operator / terminal | Selects the right machine, PID, command, and collection timestamp | The logged-in user is not necessarily the JVM owner |
| `jcmd` client | Separate JDK tool process that parses arguments, sends requests, and prints results | Target application JVM |
| PID, host, PID namespace | Identifies the **process instance** the command targets | Main class/JAR name or the PID of another container |
| Attach mechanism | **Local** communication channel provided by the runtime and OS, subject to access control | HTTP endpoint, JMX remote port, or a business API |
| Diagnostic-command dispatcher inside the JVM | Receives the command name, matches available commands, arguments/permissions, and invokes the corresponding diagnostic handler | An executor for arbitrary Java code snippets |
| JVM subsystem executing the command | Can query VM state, print threads, control JFR, write a heap dump, or adjust certain settings | A group of commands with identical impact |
| Response and side effects | Text/errors returned to the client; sometimes the JVM changes state or writes files | Every command only writing to stdout with no side effects |

Simple flow diagram:

```text
Terminal on the right host / namespace
    |
    | jcmd <PID> <DiagnosticCommand> [arguments/options]
    v
jcmd process (JDK client)
    |
    | Verify target, use local attach mechanism
    v
Running JVM (target PID)
    |
    | Look up registered command; validate syntax, permissions,
    | execute diagnostic operation in the target JVM context
    v
Result / error / state change / file created by the JVM
    |
    | Respond over attach connection (for corresponding output)
    v
jcmd prints result to terminal stdout/stderr
```

In this diagram, **there is no third JVM to "run on behalf of" the application**: `jcmd` is a tool process, while thread, heap, and JFR information is provided by the target JVM through its diagnostic servicing mechanisms.

### 2.1. What to distinguish

- **`jcmd -l`** is an operation that *lists visible JVM processes* to discover candidates. This is not yet a command like `VM.version` sent to a specific PID.
- **`jcmd <PID> help`** asks the target JVM **which diagnostic commands the current runtime has**; do not infer a fixed list across all vendors/JDKs.
- **`jcmd <PID> VM.version`** is a request with an explicit target and command name; the version data is answered by the target JVM.
- **`java -version`** runs the Java launcher found in the current terminal; it may differ from the target application's JDK.
- **JMX/JMC/JFR** are related to diagnostics but serve different roles: JMX provides management/monitoring mechanisms, JFR is an event recording system; `jcmd` has diagnostic commands to manage JFR externally. `jcmd` does not need a JMX remote port open to send local requests.

## 3. Lifecycle of sending a diagnostic command

### Step 1 — Confirm the target JVM

Select the right **host**, **namespace/container**, **PID**, **start time**, **owner**, and **application launch command**. A PID can be reused after a process exits. With multiple replicas, main class names or JAR names can also be identical.

```bash
jcmd -l
```

The output usually includes the PID and main class/JAR name or command line of visible JVMs. **Do not assume `jcmd -l` sees every JVM**, especially when the process is in another container, lacks permissions, or the runtime does not support the corresponding discovery mechanism.

Illustrative example:

```text
18432 com.example.OrderService
18597 com.example.BatchJob
```

This is a **format example**, not fixed stdout across all JDKs. Cross-check candidates with OS tools or the service manager. Avoid mixing up a PID **inside a container** with a PID **on the host**.

### Step 2 — Client locates and connects to an attachable JVM

According to the JDK 17 documentation, `jcmd` operates on the **machine hosting the target JVM**, with the same **effective user and group** used to run the JVM. This is a documented condition of the HotSpot attach mechanism; OS policies, container isolation, or runtime configuration may impose additional restrictions.

On some HotSpot platforms, the attach listener can be initialized on demand and use an OS IPC mechanism (such as a local socket on Unix). File/socket details, signals, and handshakes are **OS- and JVM-version-dependent implementation details**, not a public protocol for writing your own replacement for `jcmd`.

You do not need an HTTP/JMX port address. Conversely, running `jcmd` on your laptop **does not send commands over the network** to a PID on a server: you must run the tool on the host or an authorized diagnostic environment.

### Step 3 — Target JVM looks up the command and arguments

The JVM identifies the diagnostic command name, such as `VM.uptime` or `Thread.print`, and then processes the supported options. **Each JVM decides which commands are available** and how arguments are interpreted. Use a tool/JDK version compatible with the runtime; JDK vendors do not support arbitrarily mixing tool and target JVM versions.

Querying the command list and help:

```bash
jcmd 18432 help
jcmd 18432 help VM.uptime
jcmd 18432 help Thread.print
```

A `help <command>` entry typically presents **description**, **impact**, **syntax**, **options/arguments**, and, if applicable, permission requirements. `Impact: Low/Medium/High` reflects the runtime's assessment of the operation; **Low does not mean "completely free"**, and actual impact depends on heap size, thread count, load, and configuration.

### Step 4 — JVM executes the operation and produces a response

There are different types of outcomes:

- **Direct data return**: `VM.version`, `VM.uptime`, `VM.command_line`, `VM.flags` print current JVM information.
- **Snapshots with cost**: `Thread.print` captures thread stacks; `GC.class_histogram` inspects the heap; `GC.heap_dump` creates an HPROF file.
- **Diagnostic state changes**: `JFR.start`, `JFR.stop`, `VM.log`, or some `VM.set_flag` commands alter runtime monitoring behavior/modes.
- **File writes on the target JVM**: `GC.heap_dump /path/file.hprof` and `JFR.dump filename=/path/file.jfr` ask the JVM to create files at paths visible to it.

Some commands can increase latency, GC pressure, I/O, or disk usage. **Specifying a valid command name does not mean it is safe or approved for production**; check the impact and scope of the operation first.

### Step 5 — Client prints the result and exits; JVM keeps running

`jcmd` usually prints a header with the PID followed by the content returned by the JVM or a tool error. Once the command finishes, **the `jcmd` client process exits**; the application JVM keeps running unless an operation or the application's own state stops it. Files created by the JVM, enabled recordings, or modified logging configurations may persist after the client exits.

Not every output has a fixed schema safe for arbitrary parsing: fields, versions, and formatting can change. For automation, check the exit status, data completeness, and runtime version before acting on the output.

## 4. Syntax to master

```text
jcmd -l
jcmd -h
jcmd <pid> help
jcmd <pid> help <DiagnosticCommand>
jcmd <pid> <DiagnosticCommand> [options/arguments]
jcmd <pid> -f <command-file>
```

A sequence for reading information from a JVM at PID `18432`:

```bash
jcmd 18432 help
jcmd 18432 VM.version
jcmd 18432 VM.uptime
jcmd 18432 VM.command_line
jcmd 18432 help Thread.print
```

**Explanation:**

- `VM.version` shows the runtime/version of the **target JVM**, not the JDK on the shell's `PATH`.
- `VM.uptime` shows how long the JVM has been running at query time. It helps verify start time, but **does not** by itself establish service identity.
- `VM.command_line` shows how the JVM was launched (Java command/JVM arguments); this output may contain sensitive configuration, so do not dump it directly into public logging systems.
- `help Thread.print` returns guidance from the target JVM before collecting thread stacks.
- `<pid>` is a **placeholder value to replace with the real PID**. In actual commands, do not type the angle brackets.

### 4.1. Why use PID instead of main class?

Per `jcmd` syntax, the first argument can be a PID **or main-class**. Using a main-class can match **multiple** processes with the same name; selecting a specific PID narrows the target unambiguously.

`jcmd 0 <command>` is defined in the documentation as sending the command to **all available Java processes**. Therefore:

- Do not use `0` when diagnosing only a single application.
- Do not use a short main class name when multiple JVMs share the same name.
- Do not treat a PID as a permanent identifier: re-read the process start time right before running an impactful command.
- Do not replace a container PID with a host PID without verifying the namespace mapping.

### 4.2. Arguments: follow the command's own help

Diagnostic commands **do not share a single global set of options**. For example, on HotSpot JDK 17, `Thread.print` supports `-l` to additionally display `java.util.concurrent` locks:

```bash
jcmd 18432 Thread.print -l
```

Meanwhile, `JFR.start` uses name/value parameters such as `name=...`, `settings=...`, `duration=...`. Strings containing spaces or special characters must be quoted properly according to **the shell in use** and `jcmd` syntax. Avoid guessing options based on commands from another version; use:

```bash
jcmd 18432 help JFR.start
```

For commands that support Boolean options, syntax may use `-option` or `-option=true` per that specific command's help. A name that looks like a JVM startup flag is **not necessarily a diagnostic command**.

### 4.3. Sending multiple diagnostic commands from a file

`jcmd` supports reading commands from a file **on the client side**:

```text
VM.version
VM.uptime
VM.command_line
```

Save those three lines into a file `commands.txt`, then run:

```bash
jcmd 18432 -f commands.txt
```

`-f` does not turn these commands into an atomic transaction: the process may restart or JVM state may change between commands. Do not put heavy dumps or configuration-changing commands into an automated list without evaluating impact. The file `commands.txt` is read by `jcmd` on the **client's** filesystem, unlike the output path of `GC.heap_dump` created by the **target JVM**.

## 5. Grouping diagnostic commands by impact level

| Command on HotSpot JDK 17 | What it does | Usage guidance | Notes |
| --- | --- | --- | --- |
| `help` / `help <command>` | Displays commands, syntax, impact | **Start here** | List varies by JVM/version |
| `VM.version` | Prints JVM/JDK info | Confirm target runtime | Informational, low impact |
| `VM.uptime` | Prints JVM uptime | Verify process instance | Does not by itself prove service identity |
| `VM.command_line` | Prints launch settings | Verify target/configuration | May contain secrets in arguments/properties |
| `VM.flags` | Prints runtime flags | Cross-check configuration | Not a flag-modifying command |
| `Thread.print -l` | Prints stacks, lock details | Suspected blocked threads/deadlock | Medium impact, scales with thread count |
| `GC.heap_info` | Prints general heap info | Look for heap capacity signals | Medium impact per documentation |
| `GC.class_histogram` | Class/instance statistics | Suspected object retention or heap distribution | High impact, depends on heap size/contents |
| `GC.heap_dump <file>` | Creates HPROF snapshot | Analyze live objects | **High impact**, may request a full GC, large file/may contain sensitive data |
| `JFR.check` | Views active recordings | Check JFR state | Usually low impact |
| `JFR.start` / `JFR.dump` | Starts recording / writes recording to file | Observe CPU/GC/lock timeline | Command impact is low per help, but recording has overhead and uses disk |
| `VM.log` / `VM.set_flag` | Can adjust logging or runtime flags | Intentional adjustments | **State-changing**, do not classify as read-only |

**Do not classify safety by name alone:** `GC.heap_info` only reports heap info, whereas `GC.heap_dump` writes a very large dump; `VM.flags` reads flags, while `VM.set_flag` can alter dynamically writable flag values. Before running, read `jcmd <pid> help <command>` to check impact, parameters, and actual JVM support.

### Where are output files created?

The following two commands are **fundamentally different**:

```bash
# Redirect jcmd client stdout to a file in the current shell
jcmd 18432 Thread.print -l > threads.txt

# Ask the target JVM itself to write HPROF to a filesystem visible to the target JVM
jcmd 18432 GC.heap_dump /var/tmp/app-heap.hprof
```

In the first command, `> threads.txt` is **shell redirection**. The file usually resides in the working directory of the shell running `jcmd` and is governed by client/shell permissions.

In the second command, `/var/tmp/app-heap.hprof` is a **diagnostic command argument**. The target JVM must see the path, have write permission, and have enough disk space; in a container, this path may be inside the container's filesystem/mount rather than the location the operator sees from the host. Do not run the second command as a default observation step: creating a heap dump has major impact on the application.

Similarly, `JFR.dump filename=/var/tmp/incident.jfr` writes a file via the target JVM. Use absolute paths, and verify storage location and data protection policies before running in a real environment.

## 6. JDK 17+ hands-on: sending commands to a live demo JVM

To see the **two independent processes** model clearly, create a simple application JVM that runs for 60 seconds and use a second terminal to send diagnostic requests to the exact PID.

### 6.1. Complete Java program

Create the file **`JcmdTarget.java`**:

```java
public class JcmdTarget {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("READY");
        Thread.sleep(60_000);
        System.out.println("DONE");
    }
}
```

Compile and run in **terminal 1** (JDK 17 or newer):

```bash
javac --release 17 JcmdTarget.java
java JcmdTarget
```

**Exact stdout of the program when run to normal completion:**

```text
READY
DONE
```

`READY` appears immediately; `DONE` appears after about 60 seconds. There is no fixed PID in the program's stdout because the PID depends on the operating system and each run.

### 6.2. Observing from another terminal

Once terminal 1 has printed `READY`, in **terminal 2 on the same host** run:

```bash
jcmd -l
```

Find the process with main class `JcmdTarget` and note the actual PID, for example `18432`. Replace every `18432` in the following commands with the PID you just found:

```bash
jcmd 18432 help
jcmd 18432 VM.version
jcmd 18432 VM.command_line
jcmd 18432 VM.uptime
jcmd 18432 help Thread.print
jcmd 18432 Thread.print -l
```

The inspection commands `VM.version`, `VM.command_line`, `VM.uptime`, and `help Thread.print` query that exact demo JVM; `Thread.print -l` prints a thread snapshot of that JVM at execution time. If you wait more than 60 seconds, the demo JVM has exited: the attach request will fail or the PID may belong to another process in the future.

**There is no single fixed `jcmd` output to copy**: PID, JDK version, JVM uptime, thread count, and stacks vary by environment. What to verify is that the command executed against the **right PID**, printed a definite result or error, and the thread dump includes `main` in a call stack waiting on `Thread.sleep` if captured while the demo is sleeping.

### 6.3. After the client exits, what happens to the target JVM?

Running `jcmd 18432 VM.version` does not stop `JcmdTarget`. After the `jcmd` command finishes, terminal 1 keeps waiting and prints `DONE` once the sleep duration elapses. This is direct visual proof that **the lifecycles of the `jcmd` client and the target JVM are separate**.

If the learner intentionally stops the demo before 60 seconds via an OS tool or Ctrl+C, `DONE` may not appear; that is an **interrupted run**, not a change in the source code's logic.

### 6.4. What was actually verified?

This demo can be run on JDK 17+. The code has been verified to compile with `javac --release 17`; in testing with HotSpot/OpenJDK, `VM.version`, `VM.command_line`, `VM.uptime`, and `help Thread.print` were verified to return successfully while the demo JVM was alive. **Output metrics depend on the runtime** and should not be hard-coded in documentation or unit tests.

## 7. Attach permissions and security surface

**Attach is a privileged operational action on a process**, not an API open to everyone. For `jcmd` in the Java SE 17 documentation, the client must run on the same machine as the JVM and have the same effective user/group used to launch it. Sandboxes, file permissions, security policies, and namespaces may also apply.

Points to keep in mind:

- **Do not try running under a different account** just because the PID is visible in `ps` or Task Manager. Seeing a process name does not mean attach is permitted.
- On HotSpot, the startup option `-XX:+DisableAttachMechanism` disables the attach mechanism; if the application is configured this way, `jcmd` may fail to connect. This is a runtime choice that must be understood operationally, not a random command glitch.
- A Java service in a container may not have JDK tools in the image; `jcmd -l` on the host may also not list JVMs inside isolated Docker processes. Choose the right location with proper permissions and PID mapping.
- Diagnostic commands can read sensitive information: `VM.command_line`, `VM.system_properties`, thread stacks, heap dumps, and JFR recordings can contain tokens, connection strings, request data, or user identifiers. Only write, view, and share them within authorized boundaries.
- Some commands change runtime state, such as adjusting logging/JFR/flags; do not lump them into "read-only" just because the syntax starts with `jcmd`.
- Do not use an overly privileged account or set overly permissive access on dump files merely for investigation convenience. Maintain retention periods and artifact cleanup according to operational policy.

**Attach is not remote debugging:** having a PID or IP does not mean you can send commands to a JVM on another machine. Remote management and debuggers use separate mechanisms with their own configuration and risks.

## 8. Common errors when sending diagnostic commands

| Symptom | Possible cause | Appropriate check |
| --- | --- | --- |
| `jcmd -l` does not show the application | PID namespace/container, permissions, runtime does not publish discovery info, process exited | Use process list on the right host/namespace, cross-check service manager and current PID |
| PID exists but attach fails | Wrong user/group, attach disabled, sandbox, IPC mechanism, unresponsive process | Verify owner/start time, compatible JDK, runtime flags, and permissions; do not treat as "no JVM" |
| "Unrecognized diagnostic command" or command missing in help | Command not supported by the JVM/vendor/version | Query `jcmd <pid> help` and the specific command's help |
| Command runs but creates no file | Path interpreted from target JVM, missing write permission, out of disk space, filename collision | Check filesystem/mount/permissions/disk from the target's perspective |
| Version output is unexpected | Terminal uses a different Java than target runtime, or wrong process selected | Use `VM.version`, OS executable, and launch command |
| Command only completes after a long delay | JVM is overloaded, high-impact command, or connection/dispatch delayed | Check impact description, actual load, logs, and responsiveness; avoid rapid retries |
| PID was right initially, but result belongs to another application | Process restarted, PID reused, or different host/namespace | Compare PID **together with start time**, owner, and command right before the action |
| Heap dump causes pause or fills disk | `GC.heap_dump` is a heavy operation, not a small query | Evaluate heap size, impact, and quota/retention beforehand |
| `jcmd` from JDK A hits incompatible JDK B JVM | Mixing tools/runtimes of different versions or vendors | Use matching JDK tool, confirm `VM.version` |
| Typing command name into shell as an executable | The command only has meaning when passed to `jcmd` | Use `jcmd <pid> VM.version`, do not run bare `VM.version` |

**Categorizing errors for troubleshooting:** (1) failed to identify the right **target**, (2) failed to establish **attach**, (3) attached successfully but **command/arguments invalid**, (4) command ran but **did not produce expected output**, (5) output obtained but **meaning or timing was misinterpreted**. Each class has different checks; do not fix it by guessing a new PID or repeatedly retrying heavy commands.

## 9. Production inspection workflow in increasing order of impact

### 9.1. Read-only flow first

1. From the alert, locate the exact node/pod/instance. Record host, PID namespace, PID, start time, and owner; cross-check the executable/launch command with the service under investigation.
2. On the right machine, use `jcmd -l` (if available) then `jcmd <pid> help` to discover the command list.
3. Check `jcmd <pid> VM.version`, `VM.uptime`, `VM.command_line` as needed; **mask secrets** in the output.
4. Pick a command matching your question, read `jcmd <pid> help <command>` to verify impact/syntax before running it.
5. Record collection timestamp, PID + start time, JDK version, command executed, and outcome. Correlate with metrics/logs sharing the same time window.
6. If preparing a thread dump, JFR, histogram, or heap dump, re-verify the target and evaluate impact, quota/output file suitability for the incident.

You can use an incident record structure like this:

```text
event_time_utc: 2026-10-29T08:32:15Z
host: node-03
namespace: host
pid: 18432
start_time_utc: 2026-10-29T08:02:00Z
owner: svc-orders
diagnostic_command: VM.uptime
command_impact: Low (per help on the target JVM)
result: success
notes: JVM instance and owner cross-checked against process table
```

This is an **illustrative record**, not mandatory `jcmd` output; timestamps, user, and PID must come from the real system.

### 9.2. Examples of choosing commands by question, without guessing

| Question | Command usable after verification | Prerequisites to know |
| --- | --- | --- |
| "Is this the right JVM/build to investigate?" | `VM.version`, `VM.command_line`, `VM.uptime` | Cross-check with PID/start/owner in OS |
| "What state are threads in?" | `Thread.print -l` | Snapshot, medium impact; does not prove history from a single dump |
| "How is the JVM organizing the heap?" | `GC.heap_info` | Overview info only, does not prove a memory leak |
| "Is a JFR recording running?" | `JFR.check` | Result reflects the moment queried |
| "Need to start a one-minute timeline recording?" | `JFR.start name=triage settings=default duration=60s filename=/var/tmp/triage.jfr` | Check overhead, volume/path, and file ownership |
| "Need a heap dump to analyze retained objects?" | `GC.heap_dump /var/tmp/heap.hprof` | High impact, possible full GC, sensitive file; requires capacity planning |
| "Need to inspect native memory?" | `VM.native_memory summary` | Native Memory Tracking must be enabled at startup; not available by default |

`JFR.start` starts a recording inside the target JVM; `JFR.check` reports status; `JFR.dump` can write data to a file **without automatically stopping the recording**. JFR control commands and configuration choices fit better in a dedicated JFR lesson; here they illustrate that a diagnostic command can create **side effects outliving the `jcmd` client lifecycle**.

### 9.3. If the JVM is unresponsive

A hung or resource-exhausted JVM may respond to attach very slowly or not at all. Do not conclude "no threads are stuck" from `jcmd Thread.print` failing. When a command times out or fails, record the PID, start time, JDK version, symptoms, and error; compare other sources (metrics, logs, OS process/thread state), and follow the appropriate incident procedure.

Do not replace `jcmd` with arbitrary actions that alter the process just to get output; doing so may destroy evidence.

## 10. Right mindset about commands, results, and side effects

### Distinguish three questions

1. **Did the request reach the right JVM?** Verify PID, start time, owner, runtime identity.
2. **Is the command supported and executed by the JVM?** Rely on `help`, return status, errors, and attach conditions.
3. **Does the returned data prove the hypothesis?** A single thread dump is only a snapshot; heap info does not by itself prove a leak; JFR has sampling and event configurations.

### Key misconceptions

- "`jcmd` is a remote Java command." → It uses the attach mechanism into a live JVM; same-host, proper permissions, not a network query by default.
- "`jcmd -l` is a complete list of all JVMs." → Permissions and container namespaces can hide many processes.
- "A JAR name or main class is enough to select the target." → Multiple JVMs may share the same name; PIDs can also be reused.
- "`jcmd` only reads information." → Some commands change configuration, start recordings, dump heap, or trigger GC.
- "Getting output means the analysis is accurate." → A snapshot might be taken outside the incident window; context, timing, and cross-checking are required.
- "File paths always belong to my terminal." → Shell redirection creates a client file; a command's `filename` parameter may be a file **created by the target JVM**.
- "The `help` command on a new JDK applies to every older JVM." → Capabilities depend on version and vendor; query the target JVM itself.
- "Once the tool exits, changes revert automatically." → A JFR recording or configuration change may persist; you must know how to inspect/stop/revert if you intentionally changed state.

## 11. Checklist before sending a command to a real JVM

- [ ] Identify the exact **host/node**, **container/PID namespace**, **PID**, **owner**, **start time**, and launch command.
- [ ] Use `jcmd` from a compatible JDK; verify the runtime supports attach and the user has proper permissions.
- [ ] Inspect `jcmd <pid> help` and `jcmd <pid> help <command>`; verify command name, options, impact, and permissions.
- [ ] Distinguish **query commands**, **snapshot/large-file commands**, and **state-changing commands**.
- [ ] Check file output destination, access permissions, disk capacity, and potential secret exposure for dumps/JFR.
- [ ] Re-verify PID/start time right before the action; do not use `0` or a main class matching multiple processes.
- [ ] Save results with timestamp, runtime version, command, and execution status; correlate with metrics/logs.
- [ ] If a command fails, analyze **target → attach → syntax → execution → result** before retrying.

**Official reference documentation:**

- [Oracle Java SE 17 — The jcmd Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): syntax, help, command list, impact, and arguments.
- [Oracle Java SE 17 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html): how `jcmd` is used to diagnose a running JVM.
- [Oracle Java SE 17 — The java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-XX:+DisableAttachMechanism` and serviceability options.
- [Java SE 17 — DiagnosticCommandMBean](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/DiagnosticCommandMBean.html): how diagnostic commands are exposed through the Java management mechanism.

**Key takeaway:** the `jcmd` model consists of **client → target JVM identification → authorized local attach → diagnostic-command dispatcher → result or side effect**. Getting target JVM selection and reading `help` right is just as important as memorizing commands: the same `jcmd` tool can print a version in a few milliseconds or make the JVM process a massive heap dump.