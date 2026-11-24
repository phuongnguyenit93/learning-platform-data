# 20.8. Severe Impact of Attaching `jhsdb` Directly to a Live Process

**Warning to remember before any operation:** `jhsdb` is based on the **HotSpot Serviceability Agent (SA)** to inspect internal JVM structures. According to **Oracle JDK 21** documentation, attaching `jhsdb` to a **live Java process** will hang the process and will likely **crash it when the debugger detaches**. This is not merely a performance hit: an action intended for diagnostics can directly cause a service outage.

The principle of this lesson: **never treat `jhsdb ... --pid` as a routine status-reading command in production**. For a responsive JVM, prefer metrics, JFR, logs, or `jcmd` diagnostic commands whose impact levels are documented. If you have a core dump, use `jhsdb ... --exe ... --core ...` for **postmortem analysis**. Capturing a core from a live process is a separate step that also carries risk and requires approval.

Learning objectives:

- Accurately identify which `jhsdb` operations perform a **live SA attach**, including seemingly harmless `jstack`/`jmap` modes.
- Understand why live attach can cause hangs, crashes, timeouts, restarts, loss of evidence, and cascading impacts.
- Distinguish `--pid` from `--exe --core`, `jhsdb` from `jcmd`, JFR, and heap dumps.
- Choose evidence-collection methods according to risk level and JVM state.
- Read cores offline with `jhsdb` by example, and practice with Java 17+ **without attaching SA to a live process**.
- Design runbooks, impact bounds, and data protections when handling JVM incidents.

## 1. The Serviceability Agent and the Real Role of `jhsdb`

The **HotSpot Serviceability Agent (SA)** provides the ability to read internal structures such as heap layout, threads, class metadata, code cache, and native JVM data. Unlike ordinary monitoring APIs, SA can read JVM state from a **core dump** or from a running process when a debugger attaches.

The modes listed in JDK 21 `jhsdb` documentation:

| Command | Primary data or capability | Warning when used with a live JVM's `--pid` |
| --- | --- | --- |
| `jhsdb jstack` | Java thread stacks, lock info; can include native frames with `--mixed` | Carries live SA attach risk |
| `jhsdb jmap` | Heap summary, histogram, class loader statistics, HPROF in supported modes | Carries live SA attach risk |
| `jhsdb jinfo` | VM flags and system properties | Carries live SA attach risk |
| `jhsdb jsnap` | Performance counters | Carries live SA attach risk |
| `jhsdb clhsdb` | Interactive JVM-level CLI debugger | Carries live SA attach risk |
| `jhsdb hsdb` | Interactive GUI debugger | Carries live SA attach risk |
| `jhsdb debugd` | SA debug server for remote access | Carries live SA attach risk if the server attaches to a live PID |

**Common mistake:** assuming a command named `jstack`/`jmap` only prints data and therefore cannot affect the program. In fact, the decisive keywords are **`jhsdb` and `--pid`**, not whether output is read-only or interactive. `jhsdb jstack --pid` uses a **different mechanism** from `jcmd PID Thread.print`. Oracle's warning applies to `jhsdb`'s live attach operation.

## 2. Distinguishing Live Attach from Core-Based Postmortem

The two analysis paths have very different operational implications:

~~~text
A. LIVE ATTACH WITH SA — DO NOT TRY ON PRODUCTION SERVICES

   JVM handling requests
           |
           +-- jhsdb ... --pid <PID>
                       |
                       +-- debugger/SA attaches to live process
                       +-- process may stop making progress
                       +-- detaching debugger may leave process crashed
                       +-- timeouts, liveness failure, restart, outage

B. POSTMORTEM / OFFLINE — PREFERRED PATH

   JVM crashed and valid core dump exists
           |
           +-- [core file] + [original JVM executable] + [runtime/symbols]
                       |
                       +-- jhsdb ... --exe ... --core ...
                       |
                       +-- read stacks / heap / flags on analysis host
                           without attaching to running production JVM
~~~

`--pid` selects **an existing live process**. `--exe` and `--core` select an **executable file** and a **core image**; the original JVM does not need to stay alive to read them. This is Oracle-documented syntax, not an arbitrary filename transformation.

Why is live attach dangerous? SA must inspect low-level HotSpot structures, typically via native debugger mechanisms and process-state control. Having the debugger suspend threads directly disrupts the serving JVM. Oracle warns of **hanging during attach and likely crashing on detach**. Exact behavior depends on OS, debugger, HotSpot build, and JVM state; **there is no guarantee that exiting the tool restores normal process execution**.

Key distinction: **reading a core offline does not impact the running original JVM**, whereas **creating a core of a live JVM** may pause the process, use `ptrace`, or generate heavy I/O. “Offline analysis” is safer during the analysis phase; it does not make every **core capture** method cost-free.

## 3. Severe Consequences in Production

| Impact | Illustrative scenario | Consequence |
| --- | --- | --- |
| **Process hang** | Threads stop progressing while debugger is attached | HTTP timeouts, unprocessed messages, growing backlog |
| **Crash on detach** | After operator exits `jhsdb`, JVM fails to resume | Lost instance requiring recovery |
| **Health check failure** | Readiness/liveness probes go unanswered | Kubernetes evicts or restarts the pod |
| **Cascading impact** | Load balancer shifts traffic to remaining replicas | Retry storm, overload, latency spike |
| **Disrupted operational data** | Active requests, transactions, or queue consumers stall | Rollbacks, duplicate retries, lease timeouts |
| **Loss of original evidence** | JVM crash/restart destroys the very heap/thread state under investigation | Cannot rewind to re-measure the old state |
| **Host resource exhaustion** | Core/dump or heavy memory reads write huge files | Full disk, I/O contention, disruption to co-located processes |
| **Data exposure** | SA/core can read strings, secrets, properties, and object state | PII/credential risk and storage liability |

Not every consequence occurs on every attach; however, **the probability of losing the process** is high enough that the action must be classified as an **outage risk**. Never say “just attach for a few seconds,” because debugger attach/detach duration has **no fixed short SLA** the application can rely on.

Even in high-availability setups, one stalled replica alters available throughput. If spare capacity is tight, retries and failover can slow down remaining replicas as well. If the JVM hangs mid-transaction, transaction state and retry idempotency must be evaluated after recovery.

## 4. Recognizing Operations Never to Use as Routine Checks

Below are **dangerous syntax patterns to recognize**, not instructions to run:

~~~text
DO NOT RUN LIVE SA ATTACH FORMS IN PRODUCTION:

jhsdb jstack --pid <PID>
jhsdb jmap --pid <PID>
jhsdb jinfo --pid <PID>
jhsdb jsnap --pid <PID>
jhsdb clhsdb --pid <PID>
jhsdb hsdb --pid <PID>
jhsdb debugd --pid <PID>
~~~

Substituting a real PID turns those lines into live process attaches. No `jhsdb` subcommand on that list becomes safe merely because you “don't intend to modify anything.” Nor is `jhsdb debugd --pid` made safe by connecting remotely: **the server still attaches to the live PID**. Remote SA can also expose a network attack surface if not strictly isolated.

**Rule:** when no core dump exists and an operator feels tempted to add `--pid` to make a `jhsdb` command work, that is the signal to **stop, assess risk, and choose another method**.

## 5. Alternatives While the JVM Is Still Responsive

On HotSpot JDK 21, `jcmd` provides diagnostic commands with documented **Impact** ratings. This is the more reasonable path for live triage when permissions match and the JVM is responsive, though **no diagnostic command is completely free**.

| Question | Choice before considering live SA | Impact per JDK 21 or note |
| --- | --- | --- |
| Which VM/version is running? | `jcmd PID VM.version` | Low |
| What are command line/flags? | `jcmd PID VM.command_line` / `VM.flags` | Low |
| Summary VM information? | `jcmd PID VM.info` | Low |
| Which threads are blocked/deadlocked? | `jcmd PID Thread.print -l` | Medium, depends on thread count |
| Current heap usage? | `jcmd PID GC.heap_info` | Medium |
| Which object types hold heap? | JFR trends, JMX; consider `jcmd PID GC.class_histogram` | Histogram is High impact |
| Need a Java heap snapshot? | `jcmd PID GC.heap_dump filename=...` | High impact, usually forces a Full GC |
| Need a timeline over time? | Appropriately configured JFR | Recording is typically low overhead, depends on event settings |
| JVM already dead? | `hs_err_pid*.log`, saved JFR, core dump | Use postmortem; never attach to a dead PID |

**Example commands for PID 12345** (PID is illustrative; confirm exact process, host, and permissions before running):

~~~bash
jcmd 12345 VM.version
jcmd 12345 VM.command_line
jcmd 12345 VM.info
jcmd 12345 Thread.print -l
~~~

Per JDK 21, `VM.info` is Low and `Thread.print` is Medium. If the JVM is under heavy load or has thousands of threads, even `Thread.print` can take noticeable time. Never run infinite loops of thread dumps and never spam `jcmd` once it starts timing out.

Example using JFR to collect time-series data while the JVM is running, where the path is on the JVM's filesystem and writable:

~~~bash
jcmd 12345 JFR.check
jcmd 12345 JFR.start name=triage settings=default duration=2m filename=/var/tmp/triage-12345.jfr
~~~

`duration=2m` gives the recording a bounded end time; it is an event-collection method, **not** a snapshot of all process memory. The file may not appear until the recording finishes as configured. `JFR.start` does not guarantee zero overhead; `settings=profile` typically captures more detail than `default`.

### Why is `GC.heap_dump` not a risk-free solution?

`GC.heap_dump` writes an HPROF of the **Java heap**, not the entire native process. JDK 21 rates it High impact and by default triggers a Full GC unless `-all` is passed. Writing a multi-GiB file can pause the application and fill the disk. Never substitute a heavy heap dump for live `jhsdb` when all you wanted was thread stacks or flags.

## 6. Decision Workflow During a Service Incident

~~~text
Java service failing / slow / showing crash signs
    |
    +-- Are logs, JFR, metrics, or hs_err available? --> analyze first
    |
    +-- Is the JVM alive and responsive?
    |       |
    |       +-- YES --> choose jcmd/JFR/JMX by question,
    |       |           limit frequency and weigh Impact
    |       |
    |       +-- NO  --> do not switch to jhsdb --pid on your own;
    |                   page incident owner and prepare approved
    |                   runbook path to capture a core
    |
    +-- Is a core dump already available from the old failure?
            |
            +-- YES --> assemble exact binary, libraries, and symbols;
            |           run jhsdb --exe --core on the offline core
            |
            +-- NO  --> prioritize service recovery,
                        record the evidence gap,
                        add pre-collection plan for next time
~~~

Do not run multiple tools in parallel “just to be sure”: thread dumps, heap dumps, native cores, and SA attach have cumulative impact. Every step needs a clear question to answer, a decision owner, timing, resource limits, and a post-action health check.

### When `jcmd` does not respond

That is an important observation, yet **it does not by itself prove** live SA attach is safe or necessary. If the JVM/OS is unresponsive or diagnostic attach is disabled/permission-blocked:

1. Record timestamp, PID/namespace, CPU/RSS, thread count, disk state, cgroup, host, and error messages.
2. Check whether previously recorded JFR, logs, or thread dumps exist.
3. Evaluate failover/recovery and any core-capture procedure in the runbook, recognizing that live core capture also causes pauses.
4. Do not fire off a barrage of `jhsdb ... --pid` commands just because a lightweight command failed.
5. Once artifacts are obtained, analyze offline and cross-check timestamps against logs/metrics to avoid mixing timelines.

## 7. Analyzing a Core Dump Offline with `jhsdb`

Postmortem inputs typically include:

- **The real core dump** (`core.*` or OS-generated name), confirmed to belong to the relevant JVM.
- **The original executable** used to launch the JVM (sometimes not named `java` if using the JNI Invocation API).
- Matching JDK/HotSpot build/vendor, architecture, OS, native libraries, `libjvm`, and symbols.
- `hs_err_pid*.log`, application logs, GC logs, JFR recordings, timestamps, and container/host metadata.

Per Oracle JDK 21, examples **when the files already exist**:

~~~bash
jhsdb jstack --exe /opt/jdk-21/bin/java --core /secure/incident/core.12345
jhsdb jmap --heap --exe /opt/jdk-21/bin/java --core /secure/incident/core.12345
jhsdb jinfo --flags --exe /opt/jdk-21/bin/java --core /secure/incident/core.12345
~~~

Paths and filenames are **examples**, not defaults guaranteed on every host. Run only when the core matches that exact executable/JVM build. These commands **do not use `--pid`**, so they never attach to a newly restarted live production JVM.

Useful options when supported by the platform:

~~~bash
jhsdb jstack --mixed --exe /opt/jdk-21/bin/java --core /secure/incident/core.12345
jhsdb jmap --histo --exe /opt/jdk-21/bin/java --core /secure/incident/core.12345
jhsdb clhsdb --exe /opt/jdk-21/bin/java --core /secure/incident/core.12345
~~~

- `--mixed` attempts to display both Java and native stack frames, depending on symbols and OS.
- `--histo` produces a class-by-class heap object histogram from the core, not standalone proof of a memory leak.
- `clhsdb` allows deep exploration of core contents. It can consume substantial CPU/RAM on the analysis host without ever touching the running production JVM.
- `jhsdb jmap --binaryheap` can write an HPROF from a core when data and environment allow; see `jhsdb jmap --help` for `--dumpfile` and file-size considerations.
- A core missing memory regions, truncated, or mismatched in version/architecture can cause SA to fail; report **result limitations** rather than picking a random alternative runtime.

**Never pass `hs_err_pid12345.log` to `--core`.** `hs_err` is a text fatal-error report, not a native process memory image. Never pair service A's core with service B's executable just because both run Java.

## 8. Capturing a Core While the JVM Is Alive Also Has Costs

After reading the `jhsdb` warning, someone might react with “then just grab a core using `gcore` and analyze it.” That **avoids live SA attach during the reading phase**, yet `gcore` or native snapshot mechanisms can pause the process, use `ptrace`, read huge amounts of memory, and write massive files.

Specific risks:

- **Service pause** to capture a consistent image; duration depends on memory size and dump mechanism.
- **Disk full / quota exhaustion** when cores are huge; total process memory is not bounded by `-Xmx` because native stacks, Metaspace, mappings, and other regions also exist.
- **Incomplete snapshot** due to OS limits, container permissions, core filters, or crashing mid-capture.
- **Security exposure** because cores can contain bearer tokens, passwords, customer data, request payloads, and heap objects.
- **Analysis incompatibility** if the core, executable, shared libraries, or symbols do not match.
- **Cascading failures** if writing the core saturates I/O on a volume shared with data or logs.

Therefore, live core capture must be **an approved procedure** with disk monitoring, safe storage paths, rollback plans, and evaluated pause tolerance. Never alter `ulimit`, `core_pattern`, `systemd-coredump`, or container security contexts in production on a whim just to grab a one-off dump.

**Terminology distinction:**
- *Postmortem analysis* = analyzing saved post-incident data without attaching to a live original JVM.
- *Core capture* = the act of collecting evidence; if done on a live process, it still carries risk.
- *Live Serviceability Agent attach* = the specific action Oracle warns can hang or crash the JVM.

## 9. Safe Java 17+ Example: Inspecting a JVM with `jcmd` Instead of Live SA

To practice observing threads and the JVM, create a small Java program with a bounded sleeping worker. We intentionally **do not invoke `jhsdb --pid`**, even on this test JVM, because the exercise reinforces avoiding the dangerous pattern.

Create **`SafeDiagnosticsDemo.java`**:

~~~java
public final class SafeDiagnosticsDemo {
    public static void main(String[] args)
            throws InterruptedException {
        Thread worker = new Thread(() -> {
            try {
                Thread.sleep(120_000L);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
        }, "diagnostics-lab-worker");

        worker.start();
        System.out.println("PID=" + ProcessHandle.current().pid());
        System.out.println("Worker=" + worker.getName());
        worker.join();
        System.out.println("Finished");
    }
}
~~~

Compile and run with JDK 17 or newer:

~~~bash
javac SafeDiagnosticsDemo.java
java SafeDiagnosticsDemo
~~~

Application output before waiting:

~~~text
PID=<actual OS-assigned PID, varies each run>
Worker=diagnostics-lab-worker
~~~

While `worker` is sleeping, open another terminal on the **same host/namespace with attach permissions**, replacing **12345** with the actual PID:

~~~bash
jcmd 12345 VM.version
jcmd 12345 VM.info
jcmd 12345 Thread.print -l
~~~

During the wait window, `Thread.print` will typically show `diagnostics-lab-worker` in `TIMED_WAITING` at `Thread.sleep`, while the `main` thread awaits `join`. Exact states, line numbers, and `VM.info` output depend on timing, JVM, and OS, with **no fixed stdout**. Once the worker finishes, the application prints:

~~~text
Finished
~~~

This lab demonstrates observing threads **without using live SA attach**. `Thread.print` still has Medium impact, so use it purposefully and never call it in an infinite loop. If `jcmd` cannot connect due to PID, permissions, or namespace, do not “work around” it with `jhsdb --pid`.

### Practice recognizing wrong commands

~~~text
Recognize only, DO NOT execute:

jhsdb jstack --pid <REAL_PID>
jhsdb jmap --pid <REAL_PID>
jhsdb debugd --pid <REAL_PID>
~~~

All of these target a **live PID**. You do not need to hang or crash a process yourself to verify Oracle's warning.

## 10. Preparation and Post-Crash Handling Workflow

### 10.1. Before an incident

- Clearly define who is authorized to run diagnostics on services, acceptable impact levels, and permitted windows.
- Configure metrics, JFR, or logs at acceptable overhead with retention to protect data before a process crashes.
- Establish `hs_err_pid*.log` and core dump storage strategies aligned with OS, quotas, and security, tested in staging. `-XX:ErrorFile` can specify the fatal error log path if supported by the runtime.
- Record a release manifest: JDK vendor/build, container digest, JVM flags, native libraries, and needed symbols.
- Rehearse incident response on an **isolated JVM with no real data**; never test live `jhsdb` on a serving instance.
- Budget disk space, encryption, access controls, and deletion deadlines for cores/HPROFs.

### 10.2. When an incident occurs

1. Record timestamp, host/container, PID, health check status, GC/JFR metrics, and load level.
2. Check whether the system is still responsive; pick a measurement matching both the question and acceptable impact.
3. Consider traffic draining/failover if in-flight requests need protection.
4. If a core already exists from a crash, prioritize reading it **offline**. If none exists and live capture is considered, decide strictly by runbook rules on pause, size, and permissions.
5. Never escalate severity with an unauthorized live SA command.
6. After collection, verify request success rate, latency, queue/backlog, restarts, and disk free space.

### 10.3. Artifact bundle to preserve

~~~text
incident-2026-10-29/
  hs_err_pid12345.log
  core.12345
  runtime-manifest.txt
  gc.log
  application.log
  recording.jfr
  checksums.txt
~~~

This is an example folder layout, **not** a guarantee that the JDK automatically writes all of these exact filenames. Clearly note which files actually exist, which failed to be created, and why. A JVM native crash might not produce an HPROF; a Java `OutOfMemoryError` might produce an HPROF with `-XX:+HeapDumpOnOutOfMemoryError` without producing an OS core.

In particular, a container **`OOMKilled`** by the OS can lose its process before the JVM can write `hs_err` or an HPROF. Never attach to a new PID after restart to “fill in the gap.” Use previously stored telemetry and prepare better collection for next time.

## 11. Comparing Commonly Confused Evidence Types

| Artifact | What it contains | How to use it | What it cannot replace |
| --- | --- | --- | --- |
| `hs_err_pid*.log` | Text report of fatal HotSpot error: signal, problematic frame, threads, VM flags, modules | Read immediately to identify crash site and version | **Not** a core dump |
| **OS core dump** | Process memory/state snapshot per OS and core settings | `jhsdb ... --exe ... --core ...`, native debugger | Not a timeline recording; huge and sensitive |
| **HPROF heap dump** | Java heap objects and reference graph | Eclipse MAT / histogram / dominator tree | Does not fully reflect native stacks / OS memory |
| **JFR `.jfr`** | Time-ordered recorded events (GC, allocation samples, threads/locks, I/O) | `jfr summary`, Java Mission Control | Not a full memory snapshot |

Having `hs_err` does not mean a core exists; having JFR does not mean you have the exact state at crash instant; having HPROF does not reveal the cause of a native `SIGSEGV`. Choose artifacts based on hypotheses, not whichever tool name is easiest to remember.

## 12. Four Common Scenarios

### A. “Just grabbing the stack once”

The app is slow, and the on-call engineer wants to run `jhsdb jstack --pid` believing it is like `jcmd Thread.print`. If the process hangs and crashes on detach, a diagnostic turns into an outage.

**Right approach:** prioritize metrics/logs/JFR, then `jcmd Thread.print` when the JVM is responsive and impact is acceptable. If the JVM is severely hung, follow the runbook for core capture rather than escalating risk with live SA.

### B. Thinking remote `debugd` avoids risk

An operator launches `jhsdb debugd --pid` on the host and connects from a laptop. Remote access does not make the backend less intrusive: **debugd still attaches to the live PID**, and it also expands the RMI/network attack surface if unisolated.

**Right approach:** if remote SA is needed, serve only an **existing core file** in a secure administrative environment, or analyze directly offline.

### C. Capturing a live core onto the application volume

A multi-GiB core fills the logs volume. The service can no longer write logs and co-located instances on the host are impacted. Even though `jhsdb --core` afterward is offline, **the act of creating the core** caused severe impact.

**Right approach:** evaluate quotas, dedicated volumes, pauses, permissions, encryption, and storage paths; capture only with approval.

### D. Old JVM crashed, new instance restarted

The new PID does not hold the crashed state. Attaching `jhsdb --pid` to the new instance both misses the old evidence and risks taking down the serving instance.

**Right approach:** analyze the old instance's core with the matching executable/runtime; cross-check `hs_err`/logs/JFR before drawing conclusions.

## 13. Checklist Before Typing Any Diagnostic Command

- [ ] Verified the **exact PID**, host/container namespace, target JVM, and operational authorization.
- [ ] Clarified the question: thread hang, native crash, Java heap leak, GC pressure, or RSS/native memory?
- [ ] Checked the command's Impact rating for the **target JVM's JDK**; never assume every `jcmd` is lightweight.
- [ ] If you see `jhsdb` with `--pid` on a live service, **stop**—never run it as a routine diagnostic.
- [ ] Checked whether already-saved data (JFR, logs, `hs_err`, core) can be read first.
- [ ] If planning to capture a core or heap dump, weighed pause, disk, I/O, security, and process-loss risk.
- [ ] If reading a core offline with `jhsdb`, verified matching binary, build, libraries, and core completeness.
- [ ] Identified the approver, failover readiness, and post-action service health verification steps.

**Rule to remember:** `jhsdb --pid` is **high-risk live SA attach**; `jhsdb --exe --core` is **postmortem core analysis**; `jcmd`/JFR are live-JVM observation choices whose impact **must be evaluated individually**. Never let an investigative action cause a bigger outage than the original fault.

## 14. Self-Check

**Q1:** Why can `jhsdb jinfo --pid` still be dangerous even though you only want to view flags?

*Answer:* Because the danger lies in **SA attaching to a live process**, not in whether output is read-only. Oracle warns the process may hang during attach and crash on detach.

**Q2:** Can you replace `--pid` with `--exe ... --core ...` when a core already exists?

*Answer:* Yes. Offline reading analyzes saved data without attaching to a running production JVM; it requires a real core and a compatible executable. If no core exists, you cannot substitute the `hs_err` text file.

**Q3:** If `jcmd Thread.print` times out, should you immediately run `jhsdb jstack --pid`?

*Answer:* No. A timeout simply shows the diagnostic command did not respond under current conditions; inspect host/process state and the core-capture runbook while prioritizing service protection.

**Q4:** Is capturing a core from a live process using OS tools completely impact-free?

*Answer:* No. It can pause the process, consume heavy CPU/I/O/disk, and is subject to quotas and permissions; evaluate beforehand.

**Q5:** Do JFR, HPROF, and a core dump contain the same thing?

*Answer:* No. JFR is an event timeline; HPROF is a Java heap snapshot; a native core is an OS-level process snapshot. They complement each other rather than replacing one another.

## Official References

- Oracle JDK 21 — **The jhsdb Command** (live attach warning, `--pid`, `--exe`/`--core`, modes): https://docs.oracle.com/en/java/javase/21/docs/specs/man/jhsdb.html
- Oracle JDK 21 — **The jcmd Command** (Impact ratings; `VM.info`, `Thread.print`, `GC.heap_dump`, `JFR.start`): https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle JDK 21 — **Diagnostic Tools** (postmortem, SA, JFR, `jcmd`, and core examples): https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- Oracle JDK 21 — **Troubleshooting Guide** (fatal errors, core dumps, and incident investigation): https://docs.oracle.com/en/java/javase/21/troubleshoot/
