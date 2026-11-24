# 3.2 Using jcmd, jps, and ProcessHandle for Process Discovery; Understanding Output Limitations

In Java diagnostics, the first question is usually: **Which JVM is actually running the application under investigation, what is its PID, and what information do I have permission to see?** A single machine can simultaneously run multiple Java services, a build process, an IDE, and the diagnostic tools themselves. In containers, the PID seen from the host can also differ from the PID seen inside the container. Picking the wrong process leads to reading the wrong configuration, drawing false conclusions, or impacting another service.

Three tools address different parts of the problem:

- `jps` lists **JVMs detected by Java tool instrumentation** within the accessible scope.
- `jcmd` has a mode to **list JVMs** and can **send diagnostic commands** to a compatible JVM that allows attaching.
- `ProcessHandle` is a **Java API for identifying and inspecting operating system processes**, including non-JVM processes. The API does not inherently provide heap dumps, GC history, or guaranteed access to the full launch command.

The goal is to know how to use each tool properly, combine evidence, and explain **why a process may appear in one tool yet be absent from another**. The content focuses on process identification, data limitations, and reliability; advanced diagnostic commands are only mentioned as next steps.

## 1. Distinguishing What Is Being Discovered

### 1.1 Native Process, JVM Process, and Java Application Are Not Synonymous

A typical Java application runs inside **an operating system process** hosting the JVM. The process has a PID within the OS/namespace identification scope; the JVM executes Java code, manages the heap, GC, JIT, and interacts with the OS.

Not every native process is a JVM: `ps`, browsers, databases, or load generators are also OS processes. Conversely, do not assume each Java application is strictly one PID: a system may have multiple worker JVMs, launchers, supervisors, or child processes. A JVM embedded via a custom launcher may also not expose a main class name the way an application started with `java -jar` does.

During an investigation, identify at least:

| Identity | What is identified? | Limitations |
| --- | --- | --- |
| PID / native process ID | OS process at a point in time within a specific namespace | PIDs can be reused after a process terminates |
| `jps` LVMID | Local JVM identifier reported by the tool | Usually the PID, **not guaranteed to always equal the OS PID** |
| Main class / JAR | Launcher entry point or description obtained by the tool | May be a bootstrap name, framework launcher, or `Unknown` |
| Executable path | Executable command, such as the path to `java` | Does not guarantee pointing to the business artifact or full path |
| Start time | Start timestamp when provided by OS/API | May be missing, and available clocks/metadata have limits |
| Host, container, namespace | PID scope, observation permissions, and resource boundaries | Container PID does not necessarily match host PID |

**A PID is a lookup pointer, not a permanently durable identity.** For long-lived services, also record the startup timestamp, workload name, container/pod instance, build/image ID, and environment. Seeing PID 4242 yesterday does not guarantee PID 4242 today is still the same JVM.

### 1.2 A Process List Is a Snapshot, Not a History

Processes can start, exit, or change PID between two consecutive commands. Therefore:

- “Not seen in the list” does not prove the JVM never ran.
- “PID present in the list” does not guarantee the process is still alive when the next command runs.
- “Command line not shown” does not mean the process has no command line.
- “Unchanged PID” alone is not enough to prove a process is still the previously observed instance, because PIDs can be reused.

Process discovery mainly answers **what is currently visible within the permitted scope**; it does not by itself provide restart history, crash causes, multi-hour CPU levels, or GC state. For longitudinal data, you need timestamped logs, events, and metrics.

## 2. Choosing Tools by Question

| Question | `jps` | `jcmd` | `ProcessHandle` |
| --- | --- | --- | --- |
| Which instrumented JVMs are visible to the tool? | Suitable | `jcmd -l` is also suitable, with its own limits | Does not distinguish JVMs using the API alone |
| List native processes, including non-Java ones? | No | Not its purpose | `allProcesses()` lists OS-visible processes |
| Get main class/JAR and launcher info? | `-l`, `-m`, `-v` to the extent the tool reports | `-l` or `VM.command_line` if attachable | `Info.commandLine()`/`arguments()` may be missing or incomplete |
| Verify runtime flags of the target JVM? | `-v` for JVM arguments detected by `jps` | `VM.flags` and `VM.command_line` for deeper inspection | No standard API to get effective JVM flags of another process |
| View parent/children and start time of an OS process? | Not directly | Not its primary purpose | `parent()`, `children()`, `descendants()`, `Info.startInstant()` |
| Query GC/thread state of a compatible JVM? | No | Has diagnostic commands if supported and permitted | Not via `ProcessHandle` methods |
| Guaranteed to see **every** process/JVM on the machine? | No | No | Also no: permissions, OS, container/namespace, and timing limit visibility |

From this table, the right strategy is **discover candidates → verify identity and PID scope → pick sufficiently lightweight observation commands → cross-check**. There is no need to run heavy operations when you only want to find the PID.

## 3. Using jps to Find Instrumented JVMs

### 3.1 Basic Commands

`jps` comes bundled with many JDK distributions. On a machine with a JDK and appropriate permissions:

```bash
jps
jps -l
jps -lm
jps -v
jps -q
```

Key options to remember:

| Command/option | Expected output | Notes |
| --- | --- | --- |
| `jps` | LVMID and short main class or JAR name of visible JVMs | Name is not necessarily the service name |
| `jps -l` | Full package name of main class or JAR path if known | Custom launchers may leave the name unavailable |
| `jps -m` | Adds arguments passed to `main` as available to the tool | May display `null` or `Unknown` depending on JVM/launcher |
| `jps -v` | Adds JVM arguments recognized by the tool | May expose sensitive parameters to stdout |
| `jps -q` | Lists only LVMIDs | Cannot verify application identity from numbers alone |
| `jps -lm` | Combines full name and main arguments | Strings containing spaces can be hard for scripts to split |

A **hypothetical illustrative** output of `jps -l`:

```text
4120 com.example.orders.OrderApplication
4367 /srv/apps/report-worker.jar
4512 jdk.jcmd/sun.tools.jps.Jps
```

The PIDs/names in the block above only illustrate the **output shape**, not evidence of any running machine. `jps` can appear in its own list because the tool itself is a Java program running in a JVM.

### 3.2 What Does jps Actually See?

According to JDK documentation, `jps` lists accessible **instrumented Java HotSpot VMs**; it is not a detector for every Java program, every JVM implementation, or every OS process. The list is constrained by discovery mechanisms and environment permissions.

Common reasons a JVM is not shown even though the process exists:

1. **Permissions:** the principal running `jps` lacks permission to view another user's JVM.
2. **Namespace/container:** a tool on the host or in another container does not share the same observation scope or instrumentation data path.
3. **Incompatible JVM/launcher:** the JVM does not support or expose the mechanism `jps` relies on; custom launchers may not publish main class/JAR.
4. **Short lifetime:** the process exited before `jps` scanned.
5. **Minimal runtime environment:** `jps` is not installed, or the JDK tool does not match the target's runtime/architecture.

A foundational distinction: **`jps` is not defined as a complete-inventory API**. Oracle documentation even marks it as experimental/unsupported and advises **against writing scripts that tightly depend on its line output format**, as the format may change.

LVMID **usually** equals the OS PID when discovering JVMs on a local machine, but should not be treated as an absolute law in remote environments, custom configurations, or other implementations. When acting on a specific PID, verify further with OS tools and start time.

### 3.3 Avoiding Risks When Reading Names and Arguments

`jps -v` or `-m` can reveal values such as JVM system properties, keys, tokens, or connection strings if passed on the command line. Do not paste unfiltered raw output into public tickets or shared logs. For investigation reports, extract only needed flags, mask secret values, and store evidence with appropriate access controls.

If a script needs a reliable PID list for orchestration, use a dedicated API/endpoint or process-management platform source combined with identity verification. Do not parse the second token of `jps` to infer an immutable service name.

## 4. Using jcmd: From Listing to Querying the Target JVM Directly

### 4.1 Listing Local JVMs

```bash
jcmd
jcmd -l
```

According to JDK documentation, passing no arguments is equivalent to `jcmd -l`: it displays the JVM process identifiers visible to the tool's listing mechanism, along with the corresponding main class and launcher arguments if available.

**Very important note regarding Docker:** `jcmd` documentation explicitly states that `-l` does not list JVMs running inside separate Docker processes through its discovery mechanism. In that situation, you must use another source—such as `ps` in the proper namespace or container management tools—to identify the PID. **`jcmd -l` not seeing it does not prove the JVM is down.**

In multi-JVM environments, verify class/JAR name, command line, host/container, runtime version, and start time. Do not choose a PID because it looks “similar” to one from a previous investigation.

### 4.2 Querying Diagnostic Capabilities of the Right JVM

After identifying the PID, for example **PID 4242 purely to illustrate syntax**:

```bash
jcmd 4242 help
jcmd 4242 VM.command_line
jcmd 4242 VM.version
jcmd 4242 VM.flags
jcmd 4242 VM.uptime
```

- `help` lists the diagnostic commands advertised by the target JVM. You can use `jcmd 4242 help VM.command_line` to inspect details about a specific command.
- `VM.command_line` returns the JVM launch command information supported by the implementation.
- `VM.version` shows the target VM's version; this is more meaningful than running `java -version` in another terminal when confirming what the service is running.
- `VM.flags` shows the VM flags reported by the JVM; presentation and completeness depend on the command/implementation.
- `VM.uptime` provides the JVM's running time from the VM's perspective; combine with timestamps/identity to avoid misreading a restarted process.

During discovery, **there is no need** to immediately run `Thread.print` or trigger dumps. Simple informational commands are usually lighter, whereas other commands vary greatly in cost depending on load and object/thread counts. Always read a command's description/impact in `help` and target precisely.

Other diagnostic commands like `GC.heap_info`, `Thread.print`, and `JFR.*` can be useful **after you have accurately identified the JVM** and collection objective. They do not replace PID verification and are not mandatory in the discovery step.

### 4.3 What Prerequisites Does jcmd Have?

- The tool typically needs to run **on the same machine** as the target JVM with matching effective user/group IDs as documented by the implementation; OS permissions and attach policies still apply.
- The JVM must support the corresponding diagnostic/attach mechanism; settings like `-XX:+DisableAttachMechanism` on HotSpot can disable attach.
- The PID view must match the execution environment. A PID seen on the host must not be assumed equal to a PID inside a container namespace.
- Container images containing only a Java runtime may lack `jcmd`. The tool **not being in PATH** is different from the JVM **being undiagnosable**.
- The target may exit, hang, or change state between identifying the PID and attaching; commands may fail or time out depending on the tool.
- A diagnostic command might not exist in a specific JVM version. `jcmd PID help` is the way to verify support before running it.

Do not conclude “the JVM is broken” from a single attach failure message. Distinguish among *process not found*, *insufficient permissions*, *different namespace*, *attach disabled*, *incompatible tool/runtime*, *unresponsive JVM*, and *unsupported command*.

### 4.4 Commands That May Expose Sensitive Data or Mutate State

`jcmd PID VM.system_properties` can print system properties containing sensitive data; `VM.command_line` can also print launch arguments containing secrets. Some diagnostic commands are not read-only: there are commands that modify flags or control recordings/management agents. Therefore, run **only the specific read commands needed**, inspect descriptions beforehand, and avoid using `jcmd 0 ...` or targeting by main class when intending to inspect a single JVM: those forms can target **multiple** JVMs.

When including output in a report, always record the PID, host/container, timestamp, command executed, and applied filters/redaction. Do not place tokens, passwords, or unfiltered command-line strings in broadly accessible storage.

## 5. Using ProcessHandle to Discover Processes from Java Code

`ProcessHandle` (available since Java 9) resides in `java.lang` and allows interacting with **native processes** according to what the OS and permissions allow. No external dependencies beyond the JDK are needed to use this API. `ProcessHandle` includes process-control methods such as `destroy()`, but this lesson uses only the **read-only** API.

### 5.1 Commonly Used APIs

| API | Meaning | Things to remember |
| --- | --- | --- |
| `ProcessHandle.current()` | Gets the handle of the calling Java process | Describes only **the current process** |
| `ProcessHandle.of(pid)` | Looks up a handle by PID, returning `Optional<ProcessHandle>` | May be empty if the PID does not exist; OS/permissions may throw an exception |
| `ProcessHandle.allProcesses()` | Returns a snapshot stream of visible native processes | Includes non-Java processes; no guarantee of the entire host |
| `handle.pid()` | Returns the native process ID | PIDs are reused; namespace context matters |
| `handle.info()` | Returns a `ProcessHandle.Info` snapshot | Fields inside are `Optional` |
| `handle.parent()` | Finds the parent process, if determinable | May be empty if no parent or due to OS limitations |
| `handle.children()` | Snapshot of direct child processes | Processes can exit or change relationships right after the snapshot |
| `handle.descendants()` | Snapshot of children, grandchildren, and lower levels | Not a stable tree over time |
| `handle.isAlive()` | Checks current liveness | A snapshot; does not guarantee the process remains alive for the next action |
| `handle.onExit()` | Future that completes when the process exits | Useful for lifecycle monitoring; **not** a restart history log |

`allProcesses()` is a stream of OS processes visible to the runtime at snapshot time; **it does not automatically classify Java or HotSpot processes**. Searching for executable names containing `java` is only a heuristic: it can miss custom launchers, or misidentify shortened or similarly named paths.

### 5.2 What Information Does ProcessHandle.Info Provide?

`ProcessHandle.Info` has the main accessors:

| Field | Return type | Meaning and limitations |
| --- | --- | --- |
| `command()` | `Optional<String>` | Executable path/name; may be missing or truncated |
| `commandLine()` | `Optional<String>` | Best-effort representation of the command line; may not preserve exact quoting/argv |
| `arguments()` | `Optional<String[]>` | Process arguments if provided by the OS; may be missing, altered, or incomplete |
| `startInstant()` | `Optional<Instant>` | Process start time if available |
| `totalCpuDuration()` | `Optional<Duration>` | Cumulative CPU time if available; not instantaneous CPU % |
| `user()` | `Optional<String>` | Username readable via OS/API, if available |

**An empty `Optional` is a normal result that must be handled.** It does not prove the actual value is blank, zero, or “unknown Java”. On some operating systems, `commandLine()` is simply built by joining `command()` and `arguments()` with spaces; that representation cannot reliably reconstruct boundaries of arguments containing spaces or how the shell quoted them.

Do not call `arguments().get()` without checking presence; do not assume an unprivileged account can retrieve the owner/command line of every process. For an exited process, per-field data may already be gone.

### 5.3 Are CPU Time and Process Trees Easy to Interpret?

`totalCpuDuration()` is **cumulative CPU time** of the process, not CPU percentage or wall-clock uptime. Estimating CPU utilization requires at least two samples of CPU duration and elapsed wall time, a defined normalization against core count/quota, and handling resets/restarts. Two processes having the same CPU duration does not mean they currently have the same load.

`children()` and `descendants()` represent the parent-child structure **at query time**, not the set of request worker threads. A JVM's threads do not appear as “Java child processes” in this API. If an application uses `ProcessBuilder` to run external commands, those commands **can** be native child processes; threads within the same JVM remain inside one process.

## 6. Standalone Java 17+ Example: Inspecting Self, Parent, Optional PID, and Visibility Scope

Save the following code in `ProcessDiscoveryDemo.java`. The program **only reads information**, does not kill processes, does not scan command lines for keywords, and does not touch heap/JVM internals outside the process.

```java
import java.util.stream.Stream;

public class ProcessDiscoveryDemo {
    private static String describe(ProcessHandle process) {
        ProcessHandle.Info info = process.info();
        String command = info.command().orElse("(unavailable)");
        String start = info.startInstant()
                .map(Object::toString)
                .orElse("(unavailable)");
        return "pid=" + process.pid()
                + " alive=" + process.isAlive()
                + " command=" + command
                + " start=" + start;
    }

    public static void main(String[] args) {
        ProcessHandle self = ProcessHandle.current();

        System.out.println("SELF " + describe(self));
        System.out.println("PARENT " + self.parent()
                .map(ProcessDiscoveryDemo::describe)
                .orElse("(unavailable)"));

        try (Stream<ProcessHandle> children = self.children()) {
            System.out.println("DIRECT_CHILDREN_SNAPSHOT=" + children.count());
        }

        try (Stream<ProcessHandle> processes = ProcessHandle.allProcesses()) {
            System.out.println("VISIBLE_OS_PROCESSES_SNAPSHOT=" + processes.count());
        }

        if (args.length > 0) {
            try {
                long requestedPid = Long.parseLong(args[0]);
                if (requestedPid <= 0) {
                    System.out.println("TARGET invalid positive PID required");
                    return;
                }
                String target = ProcessHandle.of(requestedPid)
                        .map(ProcessDiscoveryDemo::describe)
                        .orElse("(not found)");
                System.out.println("TARGET " + target);
            } catch (NumberFormatException ex) {
                System.out.println("TARGET invalid integer PID required");
            }
        }
    }
}
```

Compile/run:

```bash
javac ProcessDiscoveryDemo.java
java ProcessDiscoveryDemo
java ProcessDiscoveryDemo 4242
```

- The second command queries only the current Java process, its parent, the count of direct children at sampling time, and the count of visible OS processes.
- The last command additionally queries **example PID 4242**; this number does not assert that such a process exists. If no such process exists, `TARGET (not found)` is a valid result, not a Java error.
- PID, command, start time, parent, and process count values **depend on the machine, container, timing, and permissions**, so there is no fixed numeric stdout. Every line has a prefix such as `SELF`, `PARENT`, `DIRECT_CHILDREN_SNAPSHOT=`, `VISIBLE_OS_PROCESSES_SNAPSHOT=`, and `TARGET` when an argument is provided.
- Counts use `Stream.count()`; `try-with-resources` ensures streams are properly closed, even though closing a stream here does not necessarily imply releasing a heavy OS resource.
- `ProcessHandle.of` returns an `Optional`; the program does not call `get()` on an empty optional. It does not claim “all Java processes” from `allProcesses()`.

If the OS, policy, or `SecurityManager` (on runtimes that still support it) forbids the operation, you may receive a `SecurityException` or `UnsupportedOperationException`. This is a simple measurement app and does not bypass permission controls. It does not replace platform inventory or `jcmd` when the goal is JVM internals.

### 6.1 Seeing Another Process Does Not Mean You Can Attach to a JVM

A Java program calling `ProcessHandle.of(4242)` can find a Python, shell, or database process normally. This only means the OS process has an accessible handle. **You cannot infer that the process is HotSpot, has a Java heap, or accepts `jcmd`**. Conversely, if `ProcessHandle.Info.command()` is empty, the process may still be a JVM recognized by `jcmd`.

### 6.2 Using PID + startInstant to Reduce Misidentification Risk

If `startInstant()` is available, record both the PID and timestamp. Before and after collecting evidence, verify that this identity pair still matches. When the timestamp is unavailable, cross-check container instance, uptime, artifact/build identity, and orchestration events. This reduces confusion from PID reuse, **not an atomic race-free protocol**: a process can still exit between the check and the observation step.

## 7. Practical Investigation Workflow: Finding the Right JVM Before Querying

A read-only workflow can proceed as follows.

### Step 1 — Identify the Environment You Are Standing In

Are you running the tool on a host, VM, container, pod, or development terminal? Record the PID namespace, account permissions, JDK executable path, and time. If you plan to compare multiple commands, ensure they run in the same observation scope or explicitly document the PID mapping.

### Step 2 — Collect Candidate Lists from Multiple Sources

In an environment with a JDK:

```bash
jps -l
jcmd -l
```

On Linux, supplement with the native process source in the proper namespace:

```bash
ps -eo pid,ppid,comm,args
```

On Windows, you can use PowerShell `Get-Process` or OS tools; do not copy Linux `ps` commands to Windows expecting equivalent results. A Java service running in a container should be matched against the pod/container name and that container's own process list.

**Do not take the union of results and conclude all of them are JVMs.** `ps` shows OS processes, while `jps` and `jcmd` have their own JVM discovery mechanisms. Differences reflect *observation scope*, not necessarily an error.

### Step 3 — Lock Down the Candidate's Identity Before Drilling Deeper

Record the PID in the proper namespace, command/executable if available, main class/JAR, start time, service instance, runtime version, and owner. If there are multiple instances of `report-worker.jar`, use instance/container/port/runtime/config to distinguish them rather than picking the first line.

### Step 4 — Lightweight Diagnostic Probing, Targeting a Specific PID

Only once PID and permissions are confirmed:

```bash
jcmd 4242 help
jcmd 4242 VM.command_line
jcmd 4242 VM.version
jcmd 4242 VM.uptime
```

PID 4242 is illustrative only. Save timestamps, stdout/stderr, and exit status; redact sensitive arguments before sharing. If attaching fails, record the actual error and re-check permissions/namespace/version/attach support—do not randomly try another PID.

### Step 5 — Verify What You Know and What Remains Unknown

After a discovery round, you should be able to answer:

- Which candidate JVMs/processes exist, and from which host/namespace am I observing?
- Which commands prove the identity, runtime version, launcher, and running time?
- Which fields were unavailable due to `Optional.empty()`, permissions, or tool limits?
- Have OS process checks been cross-verified with JVM liveness and orchestration metadata?
- Which deeper runtime metrics need to be collected **next** for the investigation hypothesis?

When a piece of information is missing, record “not observable with this method” instead of filling in a value by guessing.

## 8. Why Do the Three Tools Produce Different Results?

| Observation | Possible explanation | Appropriate verification step |
| --- | --- | --- |
| `ps` sees a Java process, `jps` does not | Permissions, instrumentation, namespace, VM implementation, process too short-lived | Check PID/owner/namespace, verify tool in the right environment |
| `jcmd -l` does not see a JVM inside Docker | Docker process listing limitation documented by `jcmd` | Use the process list of the right container/host and PID mapping |
| `jps` sees the app, but `jcmd PID ...` fails | Attach blocked, different user, PID changed, unresponsive JVM, or unsupported command | Check effective UID/GID, PID/start time, `help`, stderr |
| `ProcessHandle.allProcesses()` shows far more lines than `jps` | API lists native processes, including non-Java ones | Do not use that count as the number of JVMs |
| `Info.commandLine()` is empty, `pid()` has a value | OS/permissions do not expose the command line field | Check `Optional`, use another valid process/launcher source |
| `Info.command()` shows only `java` | That is the executable, not necessarily the app name | Cross-check JAR/main class, container metadata, and `jcmd` |
| `jps -l` shows `Unknown` | Custom launcher/JVM did not publish an entry point | Verify via VM command line or runtime metadata, if available |
| `ProcessHandle.of(pid)` is empty right after `jps` printed the PID | Process exited, different namespace, or lookup failed to see it | Check timestamps, re-verify identity/events |
| Two runs report the same PID but a different runtime | PID was reused after a restart | Include `startInstant`/uptime and instance ID when saving evidence |

This table lists **hypotheses to test**, not definitive diagnoses. A single case can have multiple causes simultaneously.

## 9. Four Important Limitations to Understand Deeply

### 9.1 Permission and Observation Scope Limits

Even with permission to run a Java program, the current user does not necessarily have permission to read processes owned by other accounts. Operating system, container runtime, namespaces, sandboxes, security policies, and JVM settings all participate in the decision.

A safe checking workflow:

1. Record the process owner and the account running the diagnostic command.
2. Confirm the same host/namespace and a valid path to the target process.
3. Inspect stderr and exit codes rather than just counting stdout lines.
4. Escalate privileges only through approved operational procedures; do not run every tool as root by default.

In particular, `jcmd` is not a general remote monitoring protocol. Its documentation requires operating on the same machine with matching permissions to send commands. `jps` describes an optional host identifier for environments using `jstatd`, but that **does not make every remote JVM queryable by default**.

### 9.2 Container and PID Namespace Limits

When a JVM is PID 1 inside a container, it can have a different PID on the host. If `ProcessHandle.current()` runs inside, `pid()` reflects that process's view. Passing the internal PID to `jcmd` running outside the container can target the wrong process or fail. Beyond PIDs, different filesystem namespaces and user mappings can also cause attach problems.

`jcmd -l` documentation notes the limitation with JVMs in separate Docker processes. Thus, a practical checklist is to record **where the tool runs, where the target runs, which namespace the PID came from, and whether a valid mapping exists**. Do not switch/alter namespaces just because output is missing without first establishing scope.

### 9.3 Information Completeness and Sensitivity Limits

`jps` may return a short name, long name, or `Unknown`. `ProcessHandle.Info` may return empty `Optional`s, and `commandLine()` may not preserve argument quoting. `jcmd VM.command_line` can give a clearer JVM view, but only when attaching succeeds.

Command lines and system properties can contain passwords, API keys, or internal paths. **More complete is not always safer**: a report only needs the fields necessary to identify the process. Do not paste sensitive raw output into public boards; if detailed data is needed, store it in restricted-access locations with clear redaction rules.

### 9.4 Timing and Consistency Limits

`jps` at T1, `jcmd` at T2, and `ProcessHandle.info()` at T3 do not form an atomic snapshot. Between T1 and T3, restarts, PID reuse, parent changes, or process termination can occur. Therefore, evidence timestamps and start/uptime values are essential for verification.

Fields like `isAlive`, `parent`, `children`, or `descendants` reflect observations near call time; they do not guarantee strict simultaneity. Do not write automation assuming “if `isAlive()` is true, every subsequent command will definitely succeed”.

## 10. Conclusions You Must Not Draw from Each Tool

- **Seeing a PID in `jps` ⇒ does not mean the JVM is healthy.** An existing process may be deadlocked, CPU-starved, or failing to serve requests.
- **Not seeing a PID in `jcmd -l` ⇒ does not mean the JVM is down.** Discovery limits exist, especially in separate Docker environments.
- **`jps -v` shows a few flags ⇒ does not mean you know the full effective JVM configuration.** Runtime ergonomics, auto-selected flags, and other config sources remain; check against the live JVM.
- **Large `ProcessHandle.Info.totalCpuDuration()` ⇒ does not mean CPU is currently high.** It is cumulative; you need two timed samples compared against quotas/CPU count to compute a rate.
- **`ProcessHandle.allProcesses().count()` ⇒ is not the number of Java processes or threads.** It counts visible native processes; many Java threads still belong to one PID.
- **`Info.commandLine()` contains the string “java” ⇒ does not prove the process hosts a `jcmd`-compatible JVM.** A script/process/native launcher can have a similar name or argument.
- **Empty `Info.startInstant()` ⇒ does not mean start time equals epoch.** It means the information is unavailable via the API.
- **Same PID across two measurements ⇒ does not ensure the same instance.** Correlate start/uptime and workload identity.
- **`jcmd PID help` succeeds ⇒ does not guarantee every diagnostic command is supported or has equal cost.** Each command has its own support and impact.

## 11. Practice Exercises

### Exercise A — Inspecting Your Own Process

1. Compile `ProcessDiscoveryDemo.java` with JDK 17+.
2. Run `java ProcessDiscoveryDemo` and record PID, parent, start time, command, and visible OS process count.
3. While the demo JVM is running, use `jps -l` and `jcmd -l` on the same machine/namespace, if available, to find it. Because the demo exits very quickly, it may finish before you type the command; **that itself is a timing limitation**, not proof the tool is broken. To observe a JVM longer, use an authorized long-running service or a separate controlled experiment.
4. Record which results were actually observed and which could not be cross-checked because the process exited.

### Exercise B — Multi-JVM Production Scenario

Suppose a host shows three Java processes: an API service, a batch worker, and a build daemon. Your task is to identify the right API service **without** capturing dumps or mutating state:

1. Use the known workload/host/container name to narrow down candidates.
2. Gather `jps -l`, `jcmd -l`, and the native process list for the appropriate scope.
3. Cross-check PID, entry point, command, runtime version, start/uptime, and instance identity.
4. If `jcmd -l` misses a process, note the observation limit and continue via OS/container sources—do not ignore a process just because a line is missing.
5. Only after verification, run a lightweight read-only command against the specific PID and save the timestamp along with sanitized output.

The result record should follow this structure:

```text
Observed: service, host/container, timestamp, PID scope
Source: jps / jcmd / ProcessHandle / OS tool
Verified: PID, runtime/launcher, start time or uptime
Unverified: empty Optional fields, missing permissions, unmapped namespace
Limitations: data is only a snapshot; process may restart
Next action: specific read command if justified
```

This is a **report structure**, not command output; it helps separate evidence from speculation.

## 12. Checklist Before Declaring “Found the Right JVM”

- [ ] Recorded the exact machine/VM/container, user, and namespace where the tool ran.
- [ ] Identified whether the PID source is the OS, `jps` LVMID, or inside a container namespace.
- [ ] Cross-checked service/main class/JAR name with the actual workload and build if available.
- [ ] Verified the running JVM version rather than just `java -version` from another shell.
- [ ] Captured start time/uptime or equivalent metadata to reduce PID reuse confusion.
- [ ] Explicitly noted which commands saw or missed the process and the **verified** cause.
- [ ] Handled `Optional.empty()` and potentially truncated/misquoted command lines.
- [ ] Accounted for attach permissions, container boundaries, and supported `jcmd` commands.
- [ ] Used only goal-appropriate read-only operations, avoiding unnecessary scans or heap dumps.
- [ ] Reviewed all shared output for sensitive data.
- [ ] Included timestamps, scope, and observation limits in conclusions; did not treat a snapshot as history.

## Reference Documentation

- [Oracle JDK 21 — jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): listing syntax, prerequisites for sending diagnostic commands, commands, and impact.
- [Oracle JDK 21 — jps](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jps.html): instrumented JVMs, `-l`/`-m`/`-v` options, LVMID, output format notes.
- [Java SE 21 API — ProcessHandle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessHandle.html): snapshots, process identity, parent/children, liveness, and permissions.
- [Java SE 21 API — ProcessHandle.Info](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessHandle.Info.html): command, arguments, start time, total CPU duration, and data optionality.

**Key takeaway:** `jps` helps discover JVMs visible to the instrumentation mechanism; `jcmd` lets you query a specific JVM when permitted and attachable; `ProcessHandle` gives Java an **OS native process** view. The three sources have different scopes. Reliable diagnostics require verifying the right PID/namespace/instance and understanding that data can be incomplete, time-sensitive, or constrained by permissions.