# 4.8 — Complementary Roles and Experimental Status of jstack, jmap, jinfo, and jstat

## 1. Why know these four tools when jcmd already exists?

When diagnosing a running JVM, `jcmd` is the unified tool for sending diagnostic commands to the target process. However, documentation, runbooks, and scripts on many systems still use four specialized JDK utilities: **`jstack`**, **`jmap`**, **`jinfo`**, and **`jstat`**. They are not completely identical: each tool answers a specific group of questions and has its own data format, access mechanism, cost, and stability characteristics.

Lesson objectives:

1. Accurately identify the **complementary role** of each tool and when to use it.
2. Know the corresponding `jcmd` operations where available, while recognizing areas where **there is no one-to-one replacement**.
3. Understand the **experimental and unsupported** label in Java SE 17 tool specifications: what it means for runbooks, automation, and JDK upgrades.
4. Read valid command examples and spot wrong PID scope, wrong JVM instance, or production impact risks.
5. Apply a practical diagnostic flow: verify target → frame question → choose evidence → cross-check before concluding.

> **Principle:** "Experimental/unsupported" describes the support commitment and compatibility contract of the **command-line tool**; do not assume the tool has been removed or is useless. Conversely, the fact that a tool runs on your machine does not turn its syntax or output into a stable contract across every JDK.

## 2. Quick map: jstack / jmap / jinfo / jstat compared to jcmd

| Tool | Primary question | Typical example | Related `jcmd` | Key distinction |
| --- | --- | --- | --- | --- |
| **`jstack`** | Where are Java threads running/waiting, and is there lock contention? | `jstack -l <pid>` | `jcmd <pid> Thread.print -l` | Thread/lock snapshot, not a CPU profiler or history |
| **`jmap`** | Which classes/objects are in the heap; is a heap dump needed? | `jmap -histo <pid>`; `jmap -dump:format=b,file=... <pid>` | `GC.class_histogram`, `GC.heap_dump`, `GC.heap_info` | Can consume heavy resources, trigger GC, or write huge files; does not prove a leak on its own |
| **`jinfo`** | What are the current runtime flags and system properties? | `jinfo -flags <pid>`; `jinfo -sysprops <pid>` | `VM.flags`, `VM.command_line`, `VM.system_properties`; consider `VM.set_flag` only when authorized | Some modes **modify flags**, not strictly read-only; properties may hold secrets |
| **`jstat`** | How do JVM/GC counters change over time? | `jstat -gcutil -t <pid> 1000 5` | `PerfCounter.print` and GC commands give only **a partial view**; JFR/metrics cover time series | `jstat` samples counters periodically; no exact column-for-column `jcmd` equivalent |

**Categorized by evidence type:**

- `jstack` → **thread dump** at capture time.
- `jmap` → **class histogram** or **heap dump**, mainly for Java heap memory.
- `jinfo` → **runtime configuration** and certain dynamically changeable flags.
- `jstat` → **JVM statistical time series**, especially GC/heap/class loading/compilation.

A single symptom such as "latency increased" may require more than one tool: `jstat` reveals whether GC became more frequent, `jstack` checks whether threads are blocked, and JFR adds CPU/GC/lock analysis over time. The map above is for **choosing the right evidence**, not running every command at once.

## 3. What does "Experimental and unsupported" actually mean?

The manual pages for **`jstack`**, **`jmap`**, **`jinfo`**, and **`jstat`** in the **Oracle Java SE 17 Tool Specifications** all note that the command is **experimental and unsupported**. The documentation explains that these tools or their options may change or no longer be provided in a future JDK release.

### 3.1. Three operational consequences

1. **Do not assume a stable interface across JDKs/vendors.** Options, column names, output formatting, attach capability, and replacement commands can differ. Before use, check the actual tool with `-help`/`-options` against the running JDK.
2. **Do not build automation tightly coupled to text output.** Specifically, `jstat` docs warn against writing scripts that parse output because formats may change. If parsing is unavoidable, pin tool versions, validate headers, document upgrade risks, and maintain proper tests.
3. **Do not treat "unsupported" as "always broken".** The tools can still ship in JDK 17 and run usefully when prerequisites are met. What changes is the level of caution required when building processes that depend on them.

### 3.2. "Experimental tool" differs from "experimental VM option"

Three concepts are often conflated:

| Concept | Example | Meaning |
| --- | --- | --- |
| **Experimental/unsupported tool** | Label in `jmap`, `jstat` docs | Tool interface has no support/stability commitment like standard Java SE APIs |
| **Experimental HotSpot VM option** | Certain `-XX:...` requiring `-XX:+UnlockExperimentalVMOptions` | Category of JVM startup options with its own unlock policy |
| **Java language preview feature** | Language features requiring `--enable-preview` | Mechanism for trying language/API features in specific Java releases |

**You do not need to add `-XX:+UnlockExperimentalVMOptions` just to invoke `jstack`/`jmap`/`jinfo`/`jstat`.** That flag governs JVM startup options and **does not change** the support status of command-line tools.

### 3.3. Do not extrapolate from one JDK release to another

This lesson uses **JDK 17 reference syntax**. On newer JDKs, GraalVM, OpenJ9, minimal packaged runtimes, or other vendors, verify actual presence and behavior. The shell's `java -version` does not prove it is the target process's Java; verify with `jcmd <pid> VM.version` when attachable and check the process's executable path.

If a tool is missing or incompatible, choose an **alternative** based on the diagnostic question: `jcmd`, JFR, OS metrics, logs, or vendor-supported tools. Do not merely swap executable names and assume completely identical data.

## 4. jstack — capturing Java thread stacks

### 4.1. What questions can jstack answer?

`jstack` prints stack traces of Java threads in a JVM. On JDK 17, basic syntax:

```bash
jstack <pid>
jstack -l <pid>
```

`-l` prints additional lock information. Results help identify threads in:

- `RUNNABLE`: runnable from the JVM's perspective; **does not by itself prove** active CPU consumption.
- `BLOCKED`: waiting to enter a Java monitor (e.g., `synchronized`).
- `WAITING` / `TIMED_WAITING`: waiting via `wait`, `join`, `park`, `sleep`, or equivalent mechanisms.
- Chains of threads waiting on one monitor, or many workers stuck inside I/O or connection-pool calls.

**Illustrative** snippet:

```text
"worker-7" #31 ... java.lang.Thread.State: BLOCKED
    at example.OrderCache.get(OrderCache.java:42)
    - waiting to lock <0x...> (a java.lang.Object)
```

Addresses like `<0x...>`, thread numbers, frames, and layout are illustrative, not fixed output. From **one** snapshot you cannot tell how long a thread has been waiting. For sustained stalls, collect 2–3 dumps a few seconds apart with timestamps and metrics; avoid continuous dumping if the JVM has many threads.

### 4.2. Common jcmd alternative

```bash
jcmd <pid> Thread.print -l
```

This is the common approach for taking a **thread dump** via diagnostic commands. Both tools serve thread investigations, yet do not assume byte-for-byte identical output across all JDKs. Before running a heavier command, you can query:

```bash
jcmd <pid> help Thread.print
```

Options and impact level must be taken from the **actual JVM**. `Thread.print` can produce huge output and take time if the application has very many threads.

### 4.3. Common mistakes

- Concluding a deadlock exists just because many threads are `WAITING`. Idle thread pools normally sit in `WAITING` while polling for tasks; examine stacks and lock relationships.
- Reading a thread dump from a restarted PID and attributing it to the old application instance.
- Equating every `RUNNABLE` thread with a CPU hotspot; use JFR/CPU profiling and CPU metrics to confirm.
- Using a thread dump to answer "which object holds RAM"—that belongs to heap analysis, not current stacks.

**Choose `jstack`/`Thread.print` when:** requests hang, lock contention or deadlock is suspected, thread pools are exhausted, or you want to correlate thread states with a latency spike.

## 5. jmap — histograms, heap dumps, and memory retention

### 5.1. Viewing class/instance distribution

`jmap` inspects heap-related information of the target JVM. JDK 17 examples:

```bash
jmap -histo <pid>
```

A histogram typically shows class name, instance count, and shallow bytes—not retained size or reference paths. The corresponding `jcmd` command:

```bash
jcmd <pid> GC.class_histogram
```

**Performance note:** both histograms and dumps can incur substantial cost depending on heap size and JVM state; check help/impact and run with a clear investigative purpose. When distinguishing "live" objects, JDK 17 docs list:

```bash
jmap -histo:live <pid>
```

The `:live` mode counts only live objects, which can impact GC activity and latency; do not use it as routine monitoring. `GC.class_histogram` has an `-all` option to include unreachable objects; **do not** blindly pair `:live` with another `jcmd` option assuming identical syntax.

### 5.2. Creating an HPROF heap dump

When objects appear retained too long, a heap dump is needed for analysis in Eclipse Memory Analyzer (MAT) or equivalent tools.

`jmap` example on JDK 17:

```bash
jmap -dump:format=b,file=/var/tmp/service-heap.hprof <pid>
```

Adding `live`:

```bash
jmap -dump:live,format=b,file=/var/tmp/service-live.hprof <pid>
```

`-dump:...` is a group of suboptions for **`jmap`**, not a general option for `jcmd`. With `jcmd`:

```bash
jcmd <pid> GC.heap_dump /var/tmp/service-heap.hprof
```

JDK 17 docs classify `GC.heap_dump` as **high impact**, depending on heap size/content, and by default it requests a full GC unless `-all` is used. Therefore, never treat it as a harmless config-reading action. `jmap` and `jcmd` have **different syntax, defaults, and implementation details**; read the target runtime's help when comparing live vs. all objects.

**Output path matters:** dump files are created using the **target JVM's** filesystem and permissions, which may be a container path rather than your external terminal's directory. A heap dump can be several GB, cause major pauses/I/O, and contain tokens, sessions, and user data. Ensure sufficient disk, storage permissions, and access controls before creating one.

### 5.3. Interpreting results accurately

- A histogram shows which classes/instances occupy memory; it **does not by itself prove a memory leak**.
- **Shallow size** is the direct size of an object; **retained size** depends on the reference graph. To find what retains objects, inspect the dominator tree and paths to GC roots from a heap dump.
- A large Java heap can result from valid caches or higher load. Correlate post-GC heap used over time, allocation rate, and business behavior.
- A heap dump does not capture all **native/off-heap memory**, memory-mapped files, or file descriptors; do not assume every high RSS issue is a Java heap leak.

**Choose `jmap`/`GC.class_histogram`/`GC.heap_dump` when:** object retention is suspected, heap grows across multiple GC cycles, Java heap OOM occurs, or retained-graph analysis is needed.

## 6. jinfo — flags, system properties, and JVM configuration

`jinfo` provides configuration details of a Java process. On JDK 17:

```bash
jinfo -flags <pid>
jinfo -sysprops <pid>
jinfo -flag <flag-name> <pid>
```

- `-flags`: JVM command-line flags displayed by the tool.
- `-sysprops`: system properties of the target Java runtime.
- `-flag <name>`: read the value of a specific flag per the active JDK's syntax.

Certain `-flag` modes of `jinfo` **can modify flags**:

```text
jinfo -flag +<boolean-flag> <pid>
jinfo -flag -<boolean-flag> <pid>
jinfo -flag <flag-name>=<value> <pid>
```

These are **illustrative syntax patterns**, not recommendations to run in production: only flags allowed by the runtime to be dynamically modified can change, and values must be valid. A change can persist until the JVM stops or the setting is reverted.

### 6.1. Related jcmd commands

```bash
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> VM.system_properties
```

`VM.command_line` cross-checks the launch command/JVM arguments; `VM.flags` and `VM.system_properties` provide configuration slices. You can inspect help:

```bash
jcmd <pid> help VM.flags
jcmd <pid> help VM.set_flag
```

**`VM.set_flag` is a configuration-changing command**, not a read-only twin of `jinfo -flags`. Never test modifying a flag just to "verify the tool works". `VM.flags -all` (if supported on the target JVM) prints a broader flag set than default `VM.flags`.

### 6.2. Security implications

System properties and command-line arguments can contain database URLs, API tokens, account names, sensitive paths, or security settings. Any collection of `jinfo -sysprops` or `jcmd VM.system_properties` requires appropriate permissions and secret redaction before sharing logs or attaching to tickets.

**Choose `jinfo`/`VM.flags` when:** comparing effective runtime settings against deployment configs, verifying GC/JIT/memory flags, or spotting differences between two JVMs. For application settings, separate **startup flags**, **system properties**, **environment variables**, and **app config**; they are not identical.

## 7. jstat — periodic JVM statistical series

`jstat` differs from the three tools above in that it primarily **samples JVM counters periodically**. Typical usage:

```bash
jstat -options
jstat -gcutil <pid> 1000 5
jstat -gcutil -t <pid> 1000 5
```

Breaking down `jstat -gcutil -t <pid> 1000 5`:

1. `-gcutil`: collects the GC summary statistics set.
2. `-t`: adds a **Timestamp** column showing seconds since the target JVM started, **not UTC wall-clock time**.
3. `<pid>`: local VM identifier (vmid) in this example.
4. `1000`: sampling interval in **milliseconds** by default, i.e., 1 second between samples.
5. `5`: finite sample count. **If count is omitted**, the command keeps printing until the JVM exits or the command is stopped.

### 7.1. Understanding columns and limits

Common `-gcutil` columns on HotSpot can include memory region utilization percentages, GC counts, and GC times. Exact names/meanings **depend on JDK, collector, and tool version**. Examples:

- `YGC`: number of young GC events as defined by that collector's statistics.
- `YGCT`: total recorded young GC time.
- `FGC` and `FGCT`: count and time of full GCs per the corresponding JVM/collector mechanism.
- `GCT`: cumulative total GC time as reported by the runtime.
- `E`/`O`/`M`: can reflect Eden, old generation, and metaspace utilization in applicable generational setups.

Do not declare which collector a JVM uses from a single column, and do not force generational-collector meanings onto every collector. Cross-check the process's `java -version`, collector flags, and actual option descriptions. Dashes `-` or `0` can indicate an absent space, unsupported counter, or unupdated metric depending on context.

**Reading cumulative columns:** if `YGC` rises from 12 to 14 over 5 seconds, that represents two counter events in the observation window, not "14 GCs per second". Subtract two samples and divide by the elapsed time. `YGCT` is likewise cumulative time, not the duration of the latest GC.

### 7.2. Strengths and limits of sampling

- Useful for viewing **short-term trends**, GC frequency, heap occupancy ratios, and rising GC pause signals.
- Does not tell you which objects retain memory (needs heap dump), which threads cause latency (needs thread dump/JFR), or individual slow requests (needs logs/traces).
- Data is affected by sampling instants; a brief pause can slip between 1-second samples. Sampling does not replace latency histograms or JFR event timelines.
- The JVM must expose readable performance instrumentation data; configuration, permissions, and environment can prevent `jstat` from reading counters.
- **Do not hard-parse text output in automation.** Oracle JDK 17 warns that `jstat` formatting can change between releases.

### 7.3. Does jcmd replace jstat?

```bash
jcmd <pid> PerfCounter.print
jcmd <pid> GC.heap_info
```

`PerfCounter.print` prints JVM performance counters, while `GC.heap_info` gives a general heap snapshot. **There is no default single `jcmd` call producing the exact `jstat -gcutil` table with identical columns, semantics, and sampling interval.** When you need long-term service-labeled time series, use proper metrics instrumentation/monitoring; when explaining individual GC events and latency impact, consider GC logs/JFR.

**Choose `jstat` when:** you need short-interval GC/heap counters to narrow down an issue, or you encounter legacy runbooks using `jstat -gcutil` and need to interpret them accurately.

## 8. Command mapping table: similar goals, not completely identical

| Need | Specialized tool command (JDK 17) | `jcmd` option | Differences to verify |
| --- | --- | --- | --- |
| Java thread stacks | `jstack -l <pid>` | `jcmd <pid> Thread.print -l` | Content/format depend on runtime; both are snapshots |
| Heap histogram | `jmap -histo <pid>` | `jcmd <pid> GC.class_histogram` | Included objects and GC behavior can vary by option |
| Live-objects-only histogram | `jmap -histo:live <pid>` | Check `help GC.class_histogram` and actual options | Do not assume 1:1 option-name mapping |
| Create heap dump | `jmap -dump:format=b,file=/tmp/h.hprof <pid>` | `jcmd <pid> GC.heap_dump /tmp/h.hprof` | Path belongs to target, high overhead, verify GC/default semantics |
| Flags | `jinfo -flags <pid>` | `jcmd <pid> VM.flags` | Displayed flag scope need not match identically |
| System properties | `jinfo -sysprops <pid>` | `jcmd <pid> VM.system_properties` | Sensitive data, requires redaction |
| Read single flag | `jinfo -flag <name> <pid>` | `jcmd <pid> VM.flags -all` if suitable | `VM.flags` prints a list; filtering differs |
| GC statistical series | `jstat -gcutil -t <pid> 1000 5` | `PerfCounter.print`, `GC.heap_info`, plus metrics/JFR | Lacks identical default semantics/output/sampling |

**Modifying flags:** `jinfo -flag ...` or `jcmd ... VM.set_flag` should only be used with explicit operational approval, clear understanding of whether a flag is "manageable", and a way to verify/revert. This table is primarily for **diagnostics and comparison**, not ad-hoc runtime mutation.

**For core dumps / crashed JVMs:** `jcmd` and live-process attach commands are not core-dump readers. HotSpot provides **`jhsdb`** with `jstack`/`jmap`/`jinfo` modes for Serviceability Agent and core dumps, subject to platform/permission/compatibility constraints. That is a **separate branch** from sending diagnostic commands to a live JVM; never take JDK 8's `jstack <executable> <core>` syntax and apply it verbatim to JDK 17.

## 9. Java 17+ hands-on: observing a small JVM with all four tools

### 9.1. Create the target application

Create file **`ToolingTarget.java`**:

```java
public class ToolingTarget {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("READY");
        Thread.sleep(50_000);
        System.out.println("DONE");
    }
}
```

This is a **complete Java program** with no libraries outside the JDK. Compile and run in terminal 1:

```bash
javac --release 17 ToolingTarget.java
java ToolingTarget
```

**Exact stdout if the program runs the full 50 seconds normally:**

```text
READY
DONE
```

`READY` prints immediately and `DONE` after about 50 seconds. If stopped early or failing before sleep finishes, `DONE` will not appear—that is an **interrupted run**.

### 9.2. Find the exact PID

Once terminal 1 prints `READY`, in terminal 2 on the **same machine/namespace**:

```bash
jcmd -l
```

Locate the row matching main class `ToolingTarget`. Suppose the PID is `18432` (illustrative only); before running further actions, verify process start time and owner using appropriate OS tools.

### 9.3. Try low-impact commands first

Replace `18432` with your actual PID:

```bash
jcmd 18432 VM.version
jcmd 18432 VM.command_line
jcmd 18432 help Thread.print
jstack -l 18432
jinfo -flags 18432
jstat -gcutil -t 18432 1000 3
```

**Expectations:**

- `jstack -l` can show the `main` thread in `TIMED_WAITING` at `java.lang.Thread.sleep` while sleeping; exact positions and formatting vary by runtime.
- `jinfo -flags` prints a list of flags/JVM options; there is no identical fixed output across all machines.
- `jstat -gcutil -t ... 1000 3` typically prints a header and **3 sample rows** roughly 1 second apart if the VM exposes counters and the tool supports it.
- `jcmd VM.version` confirms the right target runtime.

To inspect a histogram on the **small demo JVM** after weighing impact:

```bash
jmap -histo 18432
```

Histograms are dynamic data; the application and class library may load objects at different times, so do not expect identical counts. Never infer a "leak" from a single snapshot. In this lesson, **there is no need to create a heap dump or change JVM flags**.

### 9.4. Why is tool output not pre-written?

Aside from `ToolingTarget`'s two stdout lines, every diagnostic command observes the JVM in **real time**: PID, thread count, GC counters, flags, class histogram, runtime build, and owner vary across machines. Copying a fixed "sample output" misleads learners into treating dynamic values as constants. The true checks are **right process, zero command errors, and output aligned with your goal**.

### 9.5. Hands-on verification

`ToolingTarget.java` compiled cleanly with `javac --release 17`. On a tested OpenJDK JVM, `jcmd VM.version`, `jcmd Thread.print -l`, `jstack -l`, `jinfo -flags`, `jstat -gcutil -t`, and `jmap -histo` all executed cleanly against the demo JVM. This lesson intentionally avoids promising fixed dynamic numbers or identical vendor behavior.

## 10. Choosing tools by scenario

### 10.1. Hung requests, thread pool out of slots

1. Use metrics/logs to bracket the hung-request window and confirm instance/PID.
2. Run `jstack -l <pid>` or `jcmd <pid> Thread.print -l` to inspect thread states and lock ownership.
3. Capture several reasonably spaced timestamped snapshots to spot threads repeatedly waiting at the same point.
4. If a timeline is needed, use JFR for monitor contention/thread park/CPU samples.
5. Do not trigger a heap dump just because one thread is `BLOCKED`.

### 10.2. Post-GC heap used climbs steadily, suspected cache retention

1. Use metrics, GC logs, or `jstat -gcutil -t` to examine heap/GC trends and pinpoint the growth phase.
2. Once sufficient evidence exists, use `jmap -histo` or `GC.class_histogram` to spot prominent classes/instances while respecting cost.
3. When you must answer **who retains objects**, consider an HPROF dump from `GC.heap_dump`/`jmap -dump` with an impact and space plan.
4. Inspect the dominator tree and GC roots in MAT against baseline and cache/storage design.
5. Do not call "many objects" a leak if that data is intentionally retained by design.

### 10.3. GC pauses increase after a config change

1. Run `jinfo -flags` or `jcmd VM.flags` to read actual runtime settings; do not infer from the shell's `java -version`.
2. Use `jstat -gcutil` or metrics to compare GC frequency/time in the same window.
3. Use GC logs/JFR to examine event types, pause durations, and causes over the timeline.
4. If flags must change, follow authorized configuration change procedures with rollback and verification.

### 10.4. Very high CPU with no exceptions

1. `jstat` helps rule out or confirm GC pressure, **not** prove code CPU hotspots.
2. `jstack` gives point-in-time snapshots; `RUNNABLE` does not directly equate to burning CPU.
3. JFR execution samples or a CPU profiler are better suited to locate hot methods.
4. Combine process CPU/GC/traffic metrics; avoid taking a heap dump merely because CPU is high.

## 11. Operational boundaries you must check

### 11.1. Identify the right JVM

A PID has meaning only inside an OS/PID namespace and can be reused. Verify **host, pod/container, PID, start time, owner, and command line** before running diagnostic commands. With multiple replicas, identical main class/JAR names are insufficient.

### 11.2. Permissions and access capability

JVM attach tools can require matching effective user/group and an allowed attach environment. `-XX:+DisableAttachMechanism` can disable `jcmd` and attach tools. `jstat` also depends on performance counters being exposed and readable. A JVM missing from `jcmd -l` or `jps` **does not prove** it does not exist.

### 11.3. Containers and minimal runtimes

A container can use internal PID `1` while the host sees a different PID. A slim JRE image or custom `jlink` runtime may lack `jstack`/`jmap`/`jinfo`/`jstat`. When tools are missing, use a compatible JDK in an authorized diagnostic context while respecting namespace mapping and attach policies; never pass a host PID into a container command without verifying.

### 11.4. Cost and sensitive data

| Action | Main risk | Control measure |
| --- | --- | --- |
| Taking repeated thread dumps | Many threads yield huge output and capture-time overhead | Take only enough timestamped snapshots and cap frequency |
| Class histogram / heap dump | GC/pauses, I/O, RAM/disk; HPROF holds sensitive data | Assess impact, capacity, storage location, retention, and access permissions |
| Printing system properties / command line | Exposes credentials, connection strings, tokens | Never post raw output; redact before sharing |
| Changing manageable flags | Alters runtime behavior beyond observation goal | Act only via authorized process; know how to revert |
| Polling `jstat` without count | Huge logs, long-running command, extra load and storage cost | Use finite interval and count for short investigations |
| Parsing experimental output | Scripts break silently after JDK upgrades | Pin tool/JDK versions; prefer stable APIs/metrics for automation |

**Do not equate "experimental" with "never use":** on a compatible JVM, these tools remain valuable during incidents. Still, **evidence cost and accuracy** matter more than muscle memory for a specific command.

## 12. Common mistakes and fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| "Experimental means enabling the JVM experimental flag" | Adds unrelated flags, confuses JVM mechanisms | Separate command-line tools from `-XX:+UnlockExperimentalVMOptions` |
| "Unsupported means JDK 17 lacks the tool" | Misses an available source of evidence | Check `-help`, runtime, and man pages for the exact JDK |
| "jcmd replaces 100% of jstat commands" | Wrong expectations on format/counters/intervals | Use metrics/JFR for timelines, `PerfCounter.print` where suitable |
| "jstack RUNNABLE = that thread is eating CPU" | Wrong CPU diagnosis | Use CPU samples and correlate with process CPU |
| "jmap -histo shows who retains objects" | Confuses shallow histogram with retained graph | Analyze HPROF, dominators/GC roots |
| "jinfo -flag is always read-only" | Can alter a runtime flag | Distinguish `-flag name` from `-flag +name` or `name=value` |
| "GC count 20 means 20 GCs/sec" | Confuses cumulative counter with rate | Subtract two samples and divide by real elapsed time |
| "Omitting count in jstat still takes one sample" | Command keeps printing continuously | Specify finite interval and count |
| "Upgrading JDK leaves jstat parsers intact" | Header/column shifts corrupt metrics | Avoid brittle parsing; test per version or use stable APIs |
| "Heap dump lands in my shell's current directory" | Cannot find file, exhausts container quota | Distinguish client-side redirection from target-JVM file writes |
| "Cannot attach means the JVM is not running" | Misses active incident | Check permissions, namespaces, PID lifecycle, vendor/JDK, and perfdata |
| "Having the tool means permission to run in production" | Resource-heavy action or data leak | Read help, impact, owner, and operational procedures first |

## 13. Practical checklist

- [ ] Verify the exact JVM instance: **host/namespace, PID, process start time, owner, launch command**.
- [ ] Clarify the question: threads, heap/objects, runtime config, or GC statistical series.
- [ ] Read **help** and verify tool/JDK/vendor; remember the four tools are marked **experimental/unsupported** by Oracle JDK 17.
- [ ] Prefer corresponding `jcmd` commands when suitable and available; do not force 1:1 option renaming or assume identical `jstat` output.
- [ ] Check impact, GC likelihood, dump size, write permissions, and target JVM file path.
- [ ] Do not alter flags when the goal is purely observation; never share unsanitized system properties or heap dumps.
- [ ] Collect enough samples for **trends**, enough context for **snapshots**, and corroborate with at least one independent source.
- [ ] Record results with timestamp, PID/start time, JDK version, command, parameters, and success/error status.
- [ ] When upgrading JDKs, re-validate runbooks and scripts relying on experimental tool output.

## 14. Official documentation (JDK 17)

- [Oracle — jstack](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstack.html): command printing Java thread stack traces, `-l`, experimental/unsupported note.
- [Oracle — jmap](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jmap.html): class histogram, heap dump options, experimental/unsupported note.
- [Oracle — jinfo](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jinfo.html): reading flags/properties and flag-update forms, experimental/unsupported note.
- [Oracle — jstat](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstat.html): VM statistics, `-gcutil`, `-t`, interval/count, and output-parsing warning.
- [Oracle — jcmd](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): diagnostic command list, syntax, help, and impact.
- [Oracle — java launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-XX:+DisableAttachMechanism` and VM startup option groups.

**Technical conclusion:** `jstack` helps inspect **threads**, `jmap` helps inspect **heap**, `jinfo` helps inspect **JVM configuration**, and `jstat` helps track **statistics over time**. `jcmd` covers many of these goals without completely replacing the syntax, data, and sampling of all four tools. Understanding the experimental/unsupported label, verifying JDK compatibility, and assessing impact beforehand will keep your evidence trustworthy and your diagnostic workflow low-risk.