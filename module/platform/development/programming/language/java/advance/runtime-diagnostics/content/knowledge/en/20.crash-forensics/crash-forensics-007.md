# 20.7 Roles of `jhsdb jstack`, `jmap`, `jinfo`, and `clhsdb` for Cores or JVMs

## 1. When the JVM Has Crashed, Which Tool Inspects Its State?

A Java service abruptly dies with `SIGSEGV`/`EXCEPTION_ACCESS_VIOLATION`, possibly leaving an `hs_err_pid*.log` file and a **core dump**. At that point there is no running PID left to query with `jcmd`; the core file holds a snapshot of memory and thread state at the moment the OS took the dump. To read HotSpot structures inside that snapshot, the JDK provides **`jhsdb`**, a tool powered by the **HotSpot Serviceability Agent (SA)**.

Another situation: the process is still alive yet hung, and normal `jcmd`/attach does not respond. `jhsdb` also offers a `--pid` attach mode, but **this is an intrusive, high-risk option** and must never be treated as a “safer replacement” for `jstack`/`jcmd`. Oracle JDK 21 documentation warns that attaching SA to a live process can cause the process to hang and may crash it when detaching.

This lesson focuses on clearly distinguishing:

- **`jhsdb jstack`:** retrieves Java thread stacks and some lock information, and can show mixed Java/native frames when the platform supports it.
- **`jhsdb jmap`:** inspects the Java heap, object histogram, and class loader statistics, or exports an HPROF from the snapshot.
- **`jhsdb jinfo`:** retrieves VM flags and Java system properties from the JVM/core.
- **`jhsdb clhsdb`:** opens an interactive command-line session to drill down into threads, objects, heap, flags, and VM structures.
- **`--pid` vs. `--exe` + `--core`:** choosing live JVM vs. offline core properly; never confusing the executable with a `.jar` file.

The goal is to **choose the lowest-risk option that gives sufficient information**, read accurately what a snapshot can prove, and know when to switch to a native debugger or further investigation.

## 2. What Does the Serviceability Agent See?

The **Serviceability Agent (SA)** resides in JDK HotSpot tooling. It understands the internal layout of the JVM (Java threads, Java heap, class metadata, code cache, VM structures) and uses process or core data to interpret them into Java-meaningful information.

Visualize the three layers of evidence:

~~~text
Java Application / HotSpot VM
          |
          | Crash or OS writes snapshot
          v
   Core dump (memory + thread states/mappings)
          |
          | jhsdb + Serviceability Agent + matching JVM binary/libs
          v
   Java threads / heap / VM flags / class metadata
          |
          +--> jhsdb jstack
          +--> jhsdb jmap
          +--> jhsdb jinfo
          +--> jhsdb clhsdb (interactive)
~~~

SA differs from native debuggers like `gdb`/`lldb`/WinDbg in that it understands **HotSpot structures** to display Java stacks/objects/VM metadata; native debuggers excel at instruction pointers, native registers, machine stacks, shared library symbols, and crash signals. The two toolsets **complement each other** rather than replacing each other.

**Important limitations:**

1. `jhsdb` is specific to **HotSpot**, and parts of it are marked **experimental/unsupported** in Oracle documentation; behavior depends on JDK version, OS, architecture, collector, and core completeness.
2. If the core **is missing memory pages**, truncated, or lacks matching libraries, some queries may return no data, report symbol errors, or show only partial results.
3. A core contains only **state at capture time**. It has no GC timeline, lock contention history, request latency, or prior heap trends unless other evidence was also recorded.
4. An object histogram from a core simply **counts objects in the readable snapshot**; it does not by itself prove a memory leak or which object “crashed the JVM.”
5. SA can severely impact a **running** JVM when using `--pid`; you must have authorization, a stop/recovery plan, and an impact assessment.

## 3. Distinguishing PID, Core, HPROF, and `hs_err`

| Evidence | When does it exist? | What can you do? | What not to confuse |
| --- | --- | --- | --- |
| **Live PID** | JVM is still running; process ID exists | Use normal `jcmd`/`jstack`; SA `--pid` only when truly needed and risk is accepted | An old PID after a crash may have been reused by the OS |
| **Core dump** | OS/collector captured a snapshot on crash or on dump request | `jhsdb --exe ... --core ...`, native debugger | Not a Java heap dump; can contain lots of sensitive data |
| **`hs_err_pid*.log`** | HotSpot fatal error handler may create when VM hits a fatal error | Read crash signal, problematic frame, thread, native libs, VM flags, heap summary | Just a text file; cannot replace `--core` for SA |
| **`.hprof` heap dump** | JVM/tool exported a heap dump | MAT, VisualVM, heap dump parsers for object graph / retained size | Not an OS core; do not pass an HPROF file to `jhsdb --core` |
| **`.jfr` recording** | JFR recorded pre-crash or dumped earlier | JMC/JFR to analyze events/timeline | Does not hold full address space like a core |
| **Native stack/symbol files** | Provided by native debugger and build artifacts | Correlate machine frames, symbols, shared objects | Does not replace internal JVM metadata |

**Having `hs_err_pid` does not mean a core exists**; kernel/OS policy, `ulimit`, `systemd-coredump`, container security, and disk space determine whether a core is created/retained. Conversely, a core can be generated while a JVM is still alive via an appropriate OS mechanism (such as `gcore`), though that operation itself consumes resources and typically pauses/interrupts the process during capture; perform it only under an authorized incident procedure.

### Three things to verify before opening a core

- Which **PID, timestamp, host/container, and JDK build** does the file belong to? Check `hs_err`, core metadata, and deployment release metadata.
- Do you have the **exact Java launcher executable and JDK runtime/shared libraries** from crash time? If the JVM was created via the JNI Invocation API, the executable may be a **custom launcher**, not `$JAVA_HOME/bin/java`.
- Is the core complete and are you authorized to access it? A core can hold **tokens, passwords, keys, and user data in memory**, requiring restricted copying/sharing, controlled retention, and secure deletion after investigation.

## 4. `jhsdb` Syntax: Live and Postmortem Are Mutually Exclusive Modes

View the commands installed on the current JDK:

~~~bash
jhsdb --help
jhsdb jstack --help
jhsdb jmap --help
jhsdb jinfo --help
jhsdb clhsdb --help
~~~

Per JDK 21 and compatible HotSpot builds, the two main patterns are:

~~~bash
# Core on disk: must supply both --exe and --core.
jhsdb jstack --exe /opt/jdk/bin/java --core /var/crash/core.12345

# Live process: ONLY use when authorized and SA risks are accepted.
jhsdb jstack --pid 12345
~~~

`--exe` and `--core` **come as a pair** in postmortem mode; `--pid` is not combined with `--core`. `--exe` is the **path to the native executable that created the VM/core**, not `service.jar` or a class named `Main`. `--core` is an **OS core dump**, not `heap.hprof`.

The `jstack`, `jmap`, and `jinfo` modes are **subcommands of `jhsdb`**, distinct from traditional executables with identical/similar names:

- `jstack <PID>` typically uses the attach/serviceability interface for a live JVM.
- `jhsdb jstack --core ... --exe ...` uses SA to read an **offline core**, useful when the process is dead or normal attach channels are unavailable.
- `jmap -histo <PID>` and `jcmd <PID> GC.class_histogram` belong to the live workflow; **`jhsdb jmap --histo --core ... --exe ...`** is a postmortem workflow with different syntax.
- `jinfo <PID>` queries a live VM; **`jhsdb jinfo --flags/--sysprops --core ... --exe ...`** queries data inside the snapshot.

On JDK 21, `jhsdb debugd` and `--connect` can support remote SA, but **this remote path is marked deprecated** in documentation and adds attack/administration surface. This practice prioritizes **local core analysis in an isolated environment**, and does not recommend exposing `debugd` publicly.

## 5. `jhsdb jstack` — Thread States, Java Frames, and Mixed Stacks

### Invoking on a core

~~~bash
jhsdb jstack --exe /opt/jdk/bin/java --core /var/crash/core.12345
jhsdb jstack --locks --exe /opt/jdk/bin/java --core /var/crash/core.12345
jhsdb jstack --mixed --exe /opt/jdk/bin/java --core /var/crash/core.12345
~~~

- **No extra options:** prints stacks of Java threads that SA can read at snapshot time.
- **`--locks`:** expands details on certain `java.util.concurrent` locks / ownable synchronizers that the tool can deduce.
- **`--mixed`:** attempts to combine Java frames and native frames **if the platform/debug info supports it**. Does not promise full C/C++ symbolication or seeing every native async stack.

Read a stack trace along three dimensions:

1. **Which thread?** Thread name, Java state, native thread identifier (if shown), and whether it is the crashing thread noted in `hs_err`.
2. **What is it doing?** Which Java frames are near the top; is it blocked/waiting/parking, calling JNI, in GC/runtime, or executing business code?
3. **Who is it waiting on?** If there is monitor contention or deadlock, check lock ownership and involved threads. A single snapshot only shows **state at capture time**, not how long it waited or whether it is permanently deadlocked.

**Illustrative** example, not standard stdout across all HotSpot versions:

~~~text
"sa-lock-contender" ... java.lang.Thread.State: BLOCKED (on object monitor)
    at com.example.Worker.run(Worker.java:42)
    - waiting to lock <0x...> (a java.lang.Object)
"sa-lock-owner" ... java.lang.Thread.State: WAITING (parking)
    at jdk.internal.misc.Unsafe.park(Native Method)
    ...
~~~

Seeing `BLOCKED` is **a sign of contention at snapshot time**; do not immediately conclude deadlock or the crash culprit. When `hs_err` points to a problematic frame in `libnative.so`, also use a **native debugger with the exact core and debug symbols** to inspect signals, registers, and C stacks; SA does not replace all of that information.

### Safer options while the JVM is still alive

Before considering SA, try (with attach permissions and a responsive JVM):

~~~bash
jcmd <PID> Thread.print -l
jstack -l <PID>
~~~

These two commands follow the familiar live workflow; `jstack -l` does not share the exact options/implementation of `jhsdb jstack --locks` despite the similar goal of viewing locks. If the JVM is unresponsive, first inspect process status via the OS, attach permissions, PID namespace, and production impact; **do not reflexively switch to `jhsdb --pid` on a critical service**. Oracle documentation warns that live SA attach can hang the process and crash it on detach. Prefer **offline core/snapshot** analysis when available, or test `--pid` only on a disposable instance.

## 6. `jhsdb jmap` — Heap Summary, Object Histogram, and Class Loaders

### Questions to answer

- Roughly how much heap was in use at crash time, and which collector/regions/configuration were active?
- Which object types dominate instance counts and shallow bytes?
- Which class loaders still exist, and is there suspicious class loading/churn?
- Can an **HPROF** be extracted from the core for offline object-graph inspection?

Commands from a **core**:

~~~bash
jhsdb jmap --heap --exe /opt/jdk/bin/java --core /var/crash/core.12345
jhsdb jmap --histo --exe /opt/jdk/bin/java --core /var/crash/core.12345
jhsdb jmap --clstats --exe /opt/jdk/bin/java --core /var/crash/core.12345
jhsdb jmap --binaryheap --dumpfile recovered.hprof \
  --exe /opt/jdk/bin/java --core /var/crash/core.12345
~~~

Meaning:

| Mode | Primary data | Notes |
| --- | --- | --- |
| `--heap` | Heap configuration/summary, usage per collector/VM structures readable | Does not equal a heap dump containing the full object graph |
| `--histo` | Class/object histogram: instance counts and bytes | Usually shallow size, not retained size; snapshot may be incomplete |
| `--clstats` | Class loader statistics/metadata | Clue for further class-loader leak investigation, not conclusive by itself |
| `--binaryheap --dumpfile file.hprof` | Writes an HPROF heap dump from the snapshot, when supported by SA | Very storage-heavy, contains sensitive data, may fail if core lacks regions |

**Do not use `--dumpfile` alone**: per JDK help, this option is only valid with `--binaryheap`. `--gz 1..9` may be available to compress the dump on supported JDKs; do not use it without checking `jhsdb jmap --help`.

A histogram showing lots of `byte[]` or `String` does **not** yet prove a Java memory leak. You must check retained paths / GC roots via HPROF (if exportable) and examine the workload; a crash-time snapshot can hold lots of legitimate live data. If the JVM crashed mid-way through updating heap/GC state, some structures may be unreadable; explicitly document that limitation rather than “fixing” it by switching collectors without evidence.

If you only need heap info from a **healthy** JVM, prefer `jcmd <PID> GC.heap_info` or appropriate live tools first; generating `GC.heap_dump` incurs significant CPU/memory/disk cost and requires authorization and capacity planning.

## 7. `jhsdb jinfo` — VM Flags and System Properties at Crash Time

From a core:

~~~bash
jhsdb jinfo --flags --exe /opt/jdk/bin/java --core /var/crash/core.12345
jhsdb jinfo --sysprops --exe /opt/jdk/bin/java --core /var/crash/core.12345
# Without --flags/--sysprops: prints both kinds per JDK help.
jhsdb jinfo --exe /opt/jdk/bin/java --core /var/crash/core.12345
~~~

**Use when:** you need `-Xmx`/`-Xms`, collector, `-XX` flags, system properties, runtime configuration, or classpath/property data relevant to the crash. This is the key link to cross-check with `hs_err_pid*.log`, deployment manifests/container startup commands, and recent configuration changes.

**Do not infer:**

- System properties are not the same as all **environment variables**, startup shell scripts, OS command line, or remote configuration services.
- Not every property read from a core will be complete if the VM crashed in an unstable state or the core lacks data.
- Secrets may be exposed in `-D...` or properties; **filter/redact** before pasting logs into tickets and never send cores to unauthorized parties.
- `jhsdb jinfo` primarily **reads** state; do not confuse it with modifying live flags using certain traditional `jinfo` utilities.

When the JVM is alive and has a safe attach channel, usually start with:

~~~bash
jcmd <PID> VM.flags
jcmd <PID> VM.command_line
jcmd <PID> VM.system_properties
~~~

These commands reflect the **current** JVM; `jhsdb jinfo --core` reflects the VM at **snapshot time**. That distinction is critical if the deployment restarted with a different configuration after the crash.

## 8. `jhsdb clhsdb` — Interactive SA Tool When One-Shot Commands Are Not Enough

`clhsdb` (command-line HotSpot debugger) opens an interactive environment to explore structures known to SA. It is **not an OS shell**, and the commands inside (like `jstack`, `jhisto`) are not standalone executables you invoke directly from Bash.

Open an **offline core**:

~~~bash
jhsdb clhsdb --exe /opt/jdk/bin/java --core /var/crash/core.12345
~~~

Common commands **once inside the `clhsdb>` prompt** (illustrative session only):

~~~text
clhsdb> help
clhsdb> threads
clhsdb> jstack
clhsdb> where -a
clhsdb> jhisto
clhsdb> flags
clhsdb> sysprops
clhsdb> pmap
clhsdb> quit
~~~

| Command inside CLHSDB | Purpose |
| --- | --- |
| `help` / `help jstack` | View actually supported commands and arguments for that JDK build |
| `threads` | List Java threads recognized by SA |
| `jstack`, `where -a` | View Java stacks across all or selected threads per CLI syntax |
| `pstack` (when available) | View mixed native/Java stacks |
| `jhisto` | Heap object histogram read by SA |
| `flags`, `sysprops` | VM flags and Java system properties |
| `pmap` | `pmap`-style overview of mappings from SA |
| `inspect <address>`, `print <expression>` | Read an object/VM structure given an address and exact type |
| `quit` | Exit the SA session |

**CLHSDB commands can change across JDKs**, especially internal/struct-address commands. Run `help` before trying unfamiliar queries; never copy pointer/address formulas from a different build to decode memory. Before diving into `inspect` or `printas`, verify what type the pointer belongs to and whether memory is intact; wrong usage easily causes tool errors without proving the core is “corrupted.”

### When to choose CLHSDB instead of the three separate commands?

- You need to **follow one specific thread**, then inspect related VM/object regions.
- You want to inspect **a specific address/metadata item** in HotSpot internals hinted at by the crash.
- You want to iterate across views `threads → jstack → flags → jhisto` without spawning separate SA invocations.
- You are doing deep postmortem work alongside a native debugger when stacks or heap summaries are insufficient.

If you only need basic stacks, heap info, or flags, prefer the dedicated commands `jhsdb jstack`/`jmap`/`jinfo` and save reviewable output instead of launching CLHSDB unnecessarily. On very large cores, commands like `jhisto` or `dumpheap` can scan massive amounts of data; account for RAM and disk.

## 9. Standard Postmortem Workflow When You Have a Core

This is an **evidence-handling workflow**, not an instruction to intentionally crash an application. Examples target Linux/HotSpot JDK 17+.

### Step 1 — Collect and preserve artifacts

Store together with the incident (under restricted access):

- Crash timestamp, PID/container ID, release/commit, OS/architecture, and exact `java -version` output.
- `hs_err_pid*.log` if present, stderr, service logs, remaining JFR recordings, and deployment flags.
- **Core dump** or metadata from the OS dump manager; if using systemd, `coredumpctl list`/`coredumpctl info` can show where the core is stored or rotated.
- Compatible **JDK executable and shared libraries** matching the crashed JVM; matching debug symbol files may also be needed.

Check sizes and storage quotas before copying. Cores and HPROFs can be multiple GiB and contain secrets and PII; keep them in an isolated forensic environment. Never restart a service just to force a crash with `kill -ABRT` in production; never run a core-generating lab without authorization.

### Step 2 — Read `hs_err_pid*.log` first

Look for:

- Fatal signal / error, **problematic frame** (JVM compiler, GC, JNI/native library, or JIT code).
- **Current thread** and frames at the time of failure.
- VM/GC flags, Java/OS version, and loaded libraries.
- **Native memory**/heap sections and process status if the file managed to write them.

`hs_err` is not enough for every investigation, yet it guides the direction: native segfaults need native stacks/library symbols; OOM/native memory needs OS/cgroup/NMT/JFR; deadlocks/hangs need thread stacks and locks. Some crashes happen before `hs_err` finishes writing, leaving data incomplete.

### Step 3 — Match the JDK/OS to the core

On the analysis host, ensure you have the **exact executable that generated the core** and its related libraries. OpenJDK documentation on “transported core dumps” emphasizes that many cores **do not contain code/text pages**, so SA must read them from the executable and shared objects. Thus, **switching to a different JDK version/build** or different OS libraries can cause symbol/layout errors and untrustworthy results.

When transporting a core from a container or another host, verify:

- CPU architecture (`x86_64`/`aarch64`), OS/distro/libc, pointer width, and endianness match.
- JDK vendor/build, VM flavor (`server`), `libjvm.so`, and JNI library stack match.
- Library paths and load locations; build an **analysis image** reproducing the exact environment instead of assuming the newest JDK can open every core.

Paths in the example commands below are illustrative, **not pre-existing files on your machine**.

### Step 4 — Ask cheap questions first, deeper ones later

~~~bash
jhsdb jinfo --flags --exe /opt/jdk/bin/java --core /var/crash/core.12345
jhsdb jstack --exe /opt/jdk/bin/java --core /var/crash/core.12345
jhsdb jmap --heap --exe /opt/jdk/bin/java --core /var/crash/core.12345
~~~

Depending on the clues:

- **Crash in JNI/native:** try `jhsdb jstack --mixed`, while opening the core in a native debugger with matched symbols.
- **Suspected Java heap pressure:** try `jhsdb jmap --histo`; export an HPROF only when object-graph/retained-reference analysis is needed and disk/memory suffice.
- **Suspected classloader/metaspace issue:** use `jhsdb jmap --clstats` and CLHSDB to inspect class metadata.
- **Thread contention/deadlock:** use `jhsdb jstack --locks` or CLHSDB `threads`/`where -a`, correlating lock owners and `hs_err`.

### Step 5 — Test hypotheses, avoid overclaiming

State findings grounded in evidence: “the core at time X shows thread T BLOCKED on monitor M, with owner O at stack F” or “the core contains many instances of class C; a heap dump/retained path is needed to evaluate.” Do not assert “this is the sole root cause of the crash” without cross-checking the problematic frame, timeline, GC, OS, and preceding errors.

Fixes must tie back to **crash-time evidence** and **reproduction tests**. A single core does not show leak growth rate, how many requests were affected, or future thread states.

## 10. Java 17+ Lab: Creating a JVM with WAITING and BLOCKED Threads to Understand Snapshots

This lab **does not trigger a crash and does not collect a core**; it starts a JVM that stays alive long enough for learners to practice **low-risk live tools** such as `jcmd Thread.print`. The goal is to observe which stacks appear in a snapshot, and thereby understand why `jhsdb jstack` on a core represents **state at capture time**. **Do not run `jhsdb --pid` against this lab** unless intentionally testing SA attach in an isolated environment and accepting that the process may hang or crash.

Create **`SaSnapshotLab.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public final class SaSnapshotLab {
    private static final Object LOCK = new Object();
    private static final CountDownLatch OWNER_READY = new CountDownLatch(1);
    private static final CountDownLatch RELEASE = new CountDownLatch(1);

    private static void ownerTask() {
        synchronized (LOCK) {
            OWNER_READY.countDown();
            try {
                RELEASE.await(); // WAITING while still holding the LOCK monitor.
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }
    }

    private static void contenderTask() {
        synchronized (LOCK) {
            System.out.println("CONTENDER_ACQUIRED");
        }
    }

    public static void main(String[] args) throws Exception {
        int seconds = 30;
        if (args.length == 1 && args[0].startsWith("--seconds=")) {
            seconds = Integer.parseInt(args[0].substring(10));
            if (seconds < 0 || seconds > 300) {
                throw new IllegalArgumentException("seconds must be 0..300");
            }
        } else if (args.length != 0) {
            throw new IllegalArgumentException("Usage: SaSnapshotLab [--seconds=N]");
        }

        Thread owner = new Thread(SaSnapshotLab::ownerTask, "sa-owner");
        Thread contender = new Thread(
                SaSnapshotLab::contenderTask, "sa-contender");

        owner.start();
        OWNER_READY.await();
        contender.start();

        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(3);
        while (contender.getState() != Thread.State.BLOCKED
                && System.nanoTime() < deadline) {
            Thread.sleep(10);
        }
        if (contender.getState() != Thread.State.BLOCKED) {
            RELEASE.countDown();
            throw new IllegalStateException("Could not observe BLOCKED thread");
        }

        System.out.println("PID=" + ProcessHandle.current().pid());
        System.out.println("owner=" + owner.getState()
                + " contender=" + contender.getState());

        try {
            Thread.sleep(TimeUnit.SECONDS.toMillis(seconds));
        } finally {
            RELEASE.countDown();
        }
        owner.join();
        contender.join();
        System.out.println("END");
    }
}
~~~

**Code mechanics:** `sa-owner` holds `LOCK` and awaits `CountDownLatch`, so it is **WAITING** while still owning the intrinsic monitor. `sa-contender` attempts to enter `synchronized (LOCK)` and enters **BLOCKED**. This is **intentional contention**, not a deadlock: `main` calls `RELEASE.countDown()`, the owner releases the monitor, and the contender proceeds.

Compile and run:

~~~bash
javac -g SaSnapshotLab.java
java SaSnapshotLab
~~~

Initial output looks like:

~~~text
PID=<actual-PID>
owner=WAITING contender=BLOCKED
~~~

The default observation window is **30 seconds**; while the process is alive, in a **second terminal**, replace `<PID>` with the printed number:

~~~bash
jcmd <PID> Thread.print -l
jcmd <PID> VM.flags
jcmd <PID> GC.heap_info
~~~

In the thread dump, locate `sa-owner` awaiting the latch and `sa-contender` waiting on the monitor. If the threads are gone because the process already exited, re-run with `--seconds=60` for more observation time. Once the observation window closes, the program prints:

~~~text
CONTENDER_ACQUIRED
END
~~~

With `--seconds=1`, the whole lab finishes quickly and the expected stdout (aside from the varying PID) is:

~~~text
PID=<actual-PID>
owner=WAITING contender=BLOCKED
CONTENDER_ACQUIRED
END
~~~

Explaining the evidence:

- A **live thread dump** at second 5 shows `contender` as BLOCKED, whereas a dump taken after `RELEASE` shows the contention is gone.
- If a **core** were captured right while `contender` was BLOCKED, SA could recover that state even after the source JVM stopped; however, **this lab does not create a core**, and cores should only be generated under approved OS/test policies.
- Without a core, you **cannot** run the sample command `jhsdb ... --core ...`: `/var/crash/core.12345` is only an illustrative placeholder.

## 11. Tool and Scenario Selection Matrix

| Situation | Priority tool | What to avoid confusing |
| --- | --- | --- |
| JVM alive and responsive, need thread dump | `jcmd Thread.print -l`, `jstack -l` | Do not rush to SA attach `--pid` |
| JVM alive, need flags/properties | `jcmd VM.flags`, `VM.command_line`, `VM.system_properties` | `jhsdb jinfo` can use SA, which carries disproportionate risk here |
| JVM alive, need heap summary/histogram | `jcmd GC.heap_info`, `GC.class_histogram` when needed | Histograms/dumps have overhead and vary by GC state |
| JVM dead and core exists | `jhsdb jstack/jmap/jinfo --exe ... --core ...` | `jcmd` cannot attach to a dead PID |
| Have core, need deep HotSpot structures | `jhsdb clhsdb --exe ... --core ...` | CLHSDB is not Bash; requires matching VM/build |
| Have crash log but no core | `hs_err_pid` + logs/JFR/OS, investigate why core wasn't saved | Cannot pass a text log as `--core` |
| Suspected native segfault | Native debugger + matched libs/symbols, plus SA if core is complete | Mixed Java/native stacks do not replace registers/disassembly |
| Live JVM hung, normal attach fails | Evaluate OS signals/dump, isolate a replica, or SA `--pid` only if crash risk is accepted | Oracle docs warn SA can hang/crash the JVM on detach |
| Have `heap.hprof` but no core | MAT / heap analyzer | `jhsdb --core` does not read HPROF as an OS core |

### Common mistakes and how to prevent them

1. **Passing `--exe service.jar`:** wrong; you need the **native executable** (typically `bin/java`) matching the VM/core, or the real launcher when using JNI Invocation API.
2. **Passing only `--core` without `--exe`:** in core mode, the two options must be paired.
3. **Running `jhsdb jmap --histo <PID>`:** wrong option syntax; it must be `--pid <PID>` for live SA or `--exe ... --core ...` for a core.
4. **Using traditional `jmap -dump...` syntax with SA:** wrong; `jhsdb jmap` uses `--binaryheap --dumpfile`.
5. **Core fails to open due to different JVM/build:** assemble the exact matching executable, `libjvm`, shared libraries, and OS/architecture before assuming the core is broken.
6. **Seeing a big histogram and immediately declaring a leak:** you lack retained paths, lifecycles, or multi-point comparisons.
7. **Seeing a BLOCKED thread and immediately declaring a deadlock:** BLOCKED is a snapshot state; check the lock owner and whether a wait cycle exists.
8. **When `jcmd` fails, immediately running `jhsdb --pid` on production:** dangerous; live SA attach can freeze the service and crash it on detach.
9. **Reading only Java stacks when the crash is a `SIGSEGV` in JNI:** you need native stacks/symbols and register state.
10. **Copying the core to a machine with a newer JDK and trusting every result:** HotSpot internals depend on version/build; match the binary/runtime first.
11. **Pasting cores or `jinfo --sysprops` into public tickets:** can expose secrets; enforce access control and redaction.
12. **Reading “no errors” from a snapshot:** a core captures one instant, may miss pages or sit mid-GC, and does not prove nothing went wrong earlier.

## 12. Handover-Ready Postmortem Checklist

- [ ] Confirmed whether the application is **alive** or **dead**, and whether an actual core exists or only `hs_err`/HPROF/JFR.
- [ ] Recorded PID, timestamp, Java/OS/CPU architecture, container namespace, JDK vendor/build, and crash signal.
- [ ] If the JVM is alive, prioritized `jcmd`/live tools and weighed impact before using SA.
- [ ] If using a core, prepared the **exact `--exe` + `--core`**, without passing `.jar`/`.hprof` files as cores.
- [ ] Matched the executable and shared libraries to the build/runtime that produced the core; included debug symbols when native stacks are needed.
- [ ] Used `jhsdb jstack` for threads/locks, `jmap` for heap/classes, `jinfo` for flags/properties, and `clhsdb` when deeper inspection is needed.
- [ ] Interpreted Java frames, blocked/waiting states, and lock ownership **without jumping to a deadlock conclusion**.
- [ ] Separated snapshot evidence from hypotheses about timelines, leaks, or crash causation.
- [ ] Audited core/HPROF/system properties for sensitive data and restricted access.
- [ ] Documented exact commands, tool versions, reliable outputs, failures due to missing pages/symbols, and next steps.
- [ ] Report contains three parts: **what was observed, what remains unknown, and which test or evidence would confirm the hypothesis**.

### Official references

- Oracle JDK 21 — The `jhsdb` Command (syntax, subcommands, live attach warning): https://docs.oracle.com/en/java/javase/21/docs/specs/man/jhsdb.html
- Oracle JDK 21 — Diagnostic Tools (preferring `jcmd` on live JVMs and postmortem workflows): https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- OpenJDK — Command Line HSDB / CLHSDB commands: https://github.com/openjdk/jdk/blob/master/src/jdk.hotspot.agent/doc/clhsdb.html
- OpenJDK — Debugging Transported Core Dumps (notes on libraries and symbols): https://github.com/openjdk/jdk/blob/master/src/jdk.hotspot.agent/doc/transported_core.html

**Conclusion:** `jhsdb jstack` reads **thread/lock state**, `jmap` reads **heap/class-related state**, `jinfo` reads **VM flags/system properties**, and `clhsdb` lets you **dig interactively** into HotSpot structures. For **offline cores**, use `--exe + --core` with matching binaries and runtime; for **live JVMs**, prefer standard attach tools because SA `--pid` risks hanging or crashing the process.
