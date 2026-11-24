# 5.8 Discovering Available Tags and Changing Logging Configuration via VM.log

**Unified JVM Logging** is HotSpot's logging mechanism. When diagnosing GC, safepoints, class loading, or Java runtime behavior, you can select messages by **tag** and **level**, choose the destination via **output**, and attach timestamps/PIDs via **decorators**. On **JDK 21 using HotSpot**, **`jcmd <PID> VM.log`** lets you inspect and modify logging configuration while the JVM is still running, usually without restarting the application.

Three easily confused tasks:

1. **Discover supported tags and syntax:** run **java -Xlog:help** on the exact JDK/VM binary under investigation.
2. **Inspect active configuration on the target process:** run **jcmd PID VM.log list**.
3. **Modify an output's configuration:** run **jcmd PID VM.log output=... what=... decorators=...**, verify again, and **restore** once sufficient evidence is gathered.

This lesson belongs to **Logging and Stack Traces** in the **runtime-diagnostics** module. `VM.log` modification commands apply to **HotSpot/JDK 21**; Java SE does not mandate every JVM implementation to provide `jcmd`, `VM.log`, or the exact same tag catalog. PIDs, filenames, and sample logs in this lesson are **illustrative**, not telemetry from a specific production JVM.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish **tag**, **tag set**, **selector**, **level**, **output**, **decorator**, and **output options** in Unified Logging.
- Use **-Xlog:help** to discover supported tags, understanding the difference between the tag catalog and actively emitted events.
- Read **VM.log list** and determine which output writes to **stdout**, **stderr**, or a specific file.
- Distinguish **gc=info**, **gc*=debug**, **gc+heap=debug**, **all=warning**, and trace/debug levels.
- Configure **VM.log output, what, decorators, output_options**, and understand file rotation semantics.
- Modify runtime configuration while preserving existing outputs; avoid wiping out warnings with **VM.log disable**.
- Check impact on **CPU, disk, latency, container logging**, handle missing-log cases, and restore original configuration.
- Build a runnable Java 21 program to test `VM.log` from another terminal in an isolated environment.

## 2. Core Concepts in Unified JVM Logging

Every log site in HotSpot has a **tag set** and a **level**. The JVM matches them against each output's **selector**; if matched, the log line is written to that destination with the selected **decorators**.

| Concept | Example | Purpose |
| --- | --- | --- |
| **Tag** | **gc**, **heap**, **class**, **load**, **safepoint**, **os**, **thread** | Describes a runtime subsystem/topic. |
| **Tag set** | **gc**; **gc+heap**; **class+load** | A single message may carry multiple tags. |
| **Selector / what** | **gc=info** or **gc*=debug** | Chooses which tag sets and levels are logged. |
| **Level** | **error**, **warning**, **info**, **debug**, **trace** | Indicates verbosity/severity of messages. |
| **Output** | **stdout**, **stderr**, **file=/diagnostics/gc.log** | Where logs from the **target JVM** are written. |
| **Decorator** | **time**, **uptime**, **pid**, **tid**, **level**, **tags** | Metadata aiding reading and correlation. |
| **Output options** | **filecount=5,filesize=10M** | Configures file rotation for file outputs. |

The following log line is an illustrative example:

~~~text
[2026-10-29T12:01:02.000+0700][1.314s][info][gc] GC(3) Pause Young ... 6.31ms
~~~

It contains timestamp, uptime, level, tags, and event content. **Never treat specific message text, timestamps, or GC counts as fixed stdout**: they vary by JVM, collector, load, and enabled decorators.

### 2.1. Log Levels Are Verbosity Thresholds

Common levels in HotSpot in increasing verbosity order:

~~~text
off < error < warning < info < debug < trace
~~~

**gc*=debug** enables matching events from **error** up through **debug**, not solely lines labeled debug; it excludes trace-level logs. **gc*=trace** is broader and can consume substantial CPU/I/O.

Defaults typically log **warning** and **error** levels across many tag sets to stdout, conceptually matching **all=warning**. Never rely on assumptions when debugging a live process: **VM.log list** reveals the actual active configuration, since startup flags or earlier runtime commands may have changed it.

These are **HotSpot** logs, and do not automatically alter **application loggers**. `VM.log` does not control SLF4J, Logback, Log4j, Spring Boot logging, or `java.util.logging`. For business/application-layer errors, use the corresponding application logging tools.

### 2.2. Crucial Difference Between Tag and Tag Set

Consider three log sites:

~~~text
[info][gc] ...
[debug][gc,heap] ...
[debug][gc,ergo] ...
~~~

**gc=info** without a wildcard matches only the exact tag set **gc**; it **does not match** `gc+heap` or `gc+ergo`. **gc*=info** includes a wildcard, selecting tag sets containing **gc**, including broader combinations. **gc+heap=debug** matches the exact `gc/heap` pair; if a site carries an extra tag, covering it requires **gc+heap*=debug**.

| Selector | Selection scope | Key point |
| --- | --- | --- |
| **gc=info** | Tag set with only `gc`, up to info | Narrow scope. |
| **gc*=info** | Any tag set containing `gc`, up to info | Covers `gc+...` combinations. |
| **gc*=debug** | Any tag set containing `gc`, up to debug | More detailed; logs can grow large. |
| **gc+heap=debug** | Exact tag set `gc+heap`, up to debug | Does not cover tag sets with a third tag. |
| **safepoint=info** | Tag set `safepoint` up to info | Other selectors may be needed for deeper detail. |
| **class+load=info** | Tag set `class+load` up to info | Sees events only from the moment enabled onward. |
| **all=warning** | All tag sets, up to warning | Typical baseline, though verify with `list`. |
| **all=off** | Disables log selection on the configured output | Do not use lightly on stdout carrying warnings. |
| **gc*=info,safepoint=info** | Two selectors in one `what` string | Commas separate selectors. |

If no log lines appear after enabling, do not conclude the tag doesn't exist: the event may not have occurred in the window, the selector may be too narrow, the level insufficient, or the output misconfigured/uncollected.

## 3. Discovering Available Tags with `-Xlog:help`

On a **HotSpot JDK 21** installation:

~~~bash
java -Xlog:help
~~~

This prints **-Xlog** usage, including levels, supported tags, decorators, output options, and examples. It does not attach to a running app and exits after printing help.

Crucial question: **which `java` binary is being invoked?**

~~~bash
java -version
jcmd 12345 VM.version
jcmd 12345 VM.command_line
~~~

**12345 is an illustrative PID only.** The first command queries your shell's JDK, while the next two query the **target JVM** if attach succeeds. A host can have multiple JDKs; a Docker image can contain a different JDK from the host; another vendor's Java 21 build might not use HotSpot. Therefore:

- Run **-Xlog:help** on the **binary matching the target JVM** to inspect available tags.
- Record **full Java version, VM name/vendor, active GC**, and JDK/runtime environment.
- Never copy tags from a blog post for JDK 8, 17, or 24 and assume they exist and emit events on your target JDK 21.
- In **runtime images built with jlink** or distroless images, **jcmd** may not exist inside the image. That is a tooling packaging difference, not proof the JVM lacks tags.

### 3.1. Distinguishing Three Query Forms

| Command | What it answers | What it does not answer |
| --- | --- | --- |
| **java -Xlog:help** | What syntax/tags does this invoked Java binary support? | Which outputs are active on the target app process? |
| **jcmd PID help VM.log** | What options does `VM.log` support on this process? | Full list of all tags or how many events occurred? |
| **jcmd PID VM.log list** | Which outputs/selectors/decorators are currently active? | All tags capable of firing in this version? |

Never run **VM.log list** and treat the active selectors as the full catalog of supported tags. If `list` shows only **all=warning**, that does not mean the JVM lacks **gc** or **safepoint**.

## 4. Before Changing Configuration: Verify Target JVM and Permissions

A low-impact read sequence:

~~~bash
jcmd -l
jcmd 12345 VM.version
jcmd 12345 help VM.log
jcmd 12345 VM.log list
~~~

On Linux/containers, **jcmd -l** may fail to list processes due to separate PID namespaces or attach policies. Use the exact PID valid in the **environment where `jcmd` runs**, identifying the JVM via process manager, Docker, or Kubernetes if needed. PID 1 inside a container is not guaranteed to be the JVM if **tini**, a shell wrapper, or `shareProcessNamespace` is used.

**`VM.log` is rated Impact: Low in JDK 21 documentation** for the diagnostic command operation itself. However, enabling massive trace logging can incur heavy overhead over several minutes; that is the **ongoing cost of emitted log volume**, which does not contradict the command's own low impact rating.

If **jcmd PID help** does not list **VM.log**, do not send the command blindly. Verify VM implementation, JDK, PID, permissions, and attach capability. `jcmd` targets JVMs supporting diagnostic commands; Java SE 21 does not mandate every JVM expose the same interface.

### 4.1. Reading `VM.log list` Output

This example is **simplified for explanation** and is not guaranteed to match an exact real JVM output:

~~~text
Log output configuration:
 #0: stdout all=warning uptime,level,tags
 #1: stderr all=off uptime,level,tags
 #2: file=/diagnostics/gc.log gc*=debug time,uptime,level,tags filecount=5,filesize=10240K
~~~

- **#0 / #1 / #2** are output IDs **within the current process**. Never assume `#2` is always `gc.log`.
- **stdout, stderr** are the standard output/error streams of the **target JVM**, not the terminal running `jcmd`.
- **file=/diagnostics/gc.log** is a path opened by the **target JVM** inside its own filesystem view.
- **all=warning, gc*=debug** are the selectors configured on those outputs.
- **time, uptime, level, tags** are the decorators.
- **filecount/filesize** are file output options, where applicable.

**Save the entire `VM.log list` output before making changes**, rather than remembering one line. It is your evidence for exact restoration, especially when multiple outputs already exist.

## 5. `VM.log` Parameters Documented in JDK 21

The `jcmd` documentation specifies:

~~~text
jcmd PID VM.log [output=...] [output_options=...]
                [what=...] [decorators=...]
                [list] [rotate] [disable]
~~~

This is a multi-line syntax reference for reading, **not a multi-line shell command to copy verbatim**. Named options follow **key** or **key=value** syntax per the target JVM's help output.

| Name | Meaning | Example |
| --- | --- | --- |
| **output** | Selects output name or `#N` index to configure | `stdout`, `stderr`, `file=/diagnostics/log.txt`, `#2` |
| **what** | Selects tag sets/levels | `gc*=debug`, `safepoint=info` |
| **decorators** | Line-prefix metadata; `none` disables decorators | `uptime,pid,level,tags` |
| **output_options** | File options, typically set when creating a new output | `filecount=5,filesize=10M` |
| **list** | Lists current output configurations | `VM.log list` |
| **rotate** | Requests log file rotation per policy | `VM.log rotate` |
| **disable** | Disables all Unified Logging, clearing configuration | `VM.log disable` |

**Distinguish two ways of turning logging off:**

- **what=all=off** applied to **one specific output** disables selectors on that output, which you then verify with `list`.
- **VM.log disable** is a **global** operation that can shut off warnings/errors collected by other outputs. It is not an undo button for a small debug session.

**output_options** on an existing output may not be dynamically modifiable the same way as `what`/`decorators`. Set rotation options when **creating a new output**; if rotation of an active output must change, plan the change separately and test on the target JDK instead of assuming arbitrary live updates.

## 6. Practice: Modifying Logs on a New File Output

Suppose you verified the HotSpot JDK 21 JVM PID is **12345**, the container/host has a **/diagnostics** directory genuinely writable by the JVM, and sufficient disk/quota exists. You have saved **VM.log list** beforehand.

Enable debug-level GC logging:

~~~bash
jcmd 12345 VM.log \
  output='file=/diagnostics/gc-investigation.log' \
  what='gc*=debug' \
  decorators='time,uptime,pid,level,tags' \
  output_options='filecount=5,filesize=10M'
~~~

**Explanation:**

- **output=file=...**: creates or configures the file output on the **target JVM**.
- **what=gc*=debug**: matches every tag set containing **gc**, up to **debug**.
- **decorators**: attaches timestamp, uptime, PID, level, and tag set.
- **output_options**: rotates files around the approximate size threshold and file count.

The example uses **Bash** quoting. In Windows PowerShell/cmd, quoting rules differ; ensure special characters—especially **`*`**, commas, and `#`—reach `jcmd` intact. Never run commands in production without assessing impact, disk capacity, and cleanup.

Immediately afterward:

~~~bash
jcmd 12345 VM.log list
~~~

Locate the **exact output name** and verify selectors/decorators/rotation. If missing, check stderr/exit status, attach permissions, tag validity, file path from the JVM's perspective, read-only filesystems, or full disks. **Never treat sending the command as proof logging was enabled.**

### 6.1. Caution When Modifying stdout

The following modifies an **existing output**:

~~~bash
jcmd 12345 VM.log output=stdout what='gc=info' decorators='uptime,level,tags'
~~~

If stdout previously had **all=warning** or other selectors, overwriting it like this can drop important warning logs. To preserve warnings, combine known selectors—for instance, **if the baseline was solely `all=warning`**:

~~~bash
jcmd 12345 VM.log output=stdout what='all=warning,gc=info'
~~~

**Use this only after reading the actual baseline.** If stdout previously carried more selectors (e.g., `class+load=info`), replacing them with just those two selectors is not a full preservation. A lower-risk approach is usually **creating a dedicated investigation file output** and leaving stdout untouched.

**JVM stdout differs from `jcmd` stdout.** In Docker/Kubernetes, Java's stdout may go to **docker logs** or **kubectl logs** via the runtime collector; the terminal running `jcmd` only prints the diagnostic command response. Never confuse `VM.log output=stdout` with shell redirection into your current terminal.

### 6.2. Updating Selectors on an Existing Output by ID

Suppose **VM.log list run right beforehand** confirmed:

~~~text
#2: file=/diagnostics/gc-investigation.log gc*=debug ...
~~~

If raising verbosity very briefly is truly needed:

~~~bash
jcmd 12345 VM.log output='#2' what='gc*=trace'
jcmd 12345 VM.log list
~~~

**`#2` is an example**—always verify the current ID. Raising to `trace` can generate large log volume and overhead; enforce a time cap, an owner responsible for turning it off, and a rollback plan. Never hardcode `#2` from another JVM or from before a restart.

## 7. Decorators and Reading Time

Decorators make logs usable for correlation:

| Decorator | Interpretation | When useful |
| --- | --- | --- |
| **time** | Wall-clock timestamp of the message | Aligning with incident times, app logs, and monitoring systems. |
| **uptime** | Elapsed time since JVM startup | Separating startup/warmup from steady-state events. |
| **pid** | PID from the JVM's perspective | Distinguishing multiple processes/instances sharing storage. |
| **tid** | VM/native-level thread ID | Investigating a thread group; not identical to Java thread ID. |
| **level** | Message level | Distinguishing info/debug/trace during analysis. |
| **tags** | Message tag set | Seeing why a selector matched the log. |
| **none** | Omits decorations | Reduces metadata at the cost of losing context; weigh carefully. |

A configuration might be:

~~~bash
jcmd 12345 VM.log \
  output='file=/diagnostics/safepoint.log' \
  what='safepoint=info' \
  decorators='time,uptime,pid,tid,level,tags' \
  output_options='filecount=3,filesize=10M'
~~~

If a latency spike happens at 12:05 and a safepoint line appears near that time, **time overlap is a clue**, not proof that safepoints were the sole cause. Cross-check request traces, GC events, CPU/throttling, load, and clock sync.

**The `pid` decorator inside a container** can be the JVM's namespaced PID, differing from the Linux host PID. When correlating events between node exporters and Java, rely on **container/Pod identity, host, and JVM start timestamp** rather than PID alone.

## 8. File Output and Rotation

Log files grow quickly when multiple tags are enabled at debug/trace. **filesize=10M,filecount=5** limits retained logs per HotSpot's rotation policy; this is a **target threshold**, and actual file sizes can vary slightly due to write/rotation timing. **JDK 21 `java` docs** describe default file rotation up to **5 rotated files** of roughly **20 MB** each unless configured otherwise. **filecount=0** disables rotation, allowing the file to grow until filesystem/quota exhaustion.

Example:

~~~bash
jcmd 12345 VM.log \
  output='file=/diagnostics/class-load.log' \
  what='class+load=info' \
  decorators='time,uptime,level,tags' \
  output_options='filecount=4,filesize=10M'
~~~

The **-Xlog** docs support **%p** (JVM PID) and **%t** (startup timestamp) placeholders in filenames, helping prevent collisions. Still, PIDs can be reused, so for stable identification combine service/instance/incident metadata.

**Only disable rotation with `filecount=0`** when another capacity control strategy is in place for a special capture need. Never write an unbounded **all=trace** file onto a container's root filesystem.

### 8.1. File Paths Always Depend on the Target JVM's Context

When you run on the host:

~~~bash
jcmd 12345 VM.log output='file=/diagnostics/gc.log' what='gc*=info'
~~~

the file **/diagnostics/gc.log** is opened by the **target JVM**. If the JVM runs inside Docker, that path resolves inside the **container's mount namespace/filesystem**, not automatically the host's. If the container mounts **/srv/diag/host** at **/diagnostics**, the host may see the same file under a different path, which you confirm by inspecting mount metadata.

Preflight from inside the JVM's environment when tools are available:

~~~bash
id
ls -ld /diagnostics
df -h /diagnostics
df -i /diagnostics
~~~

Check the **UID/GID of the JVM process itself**, not just a root debug shell. Account for read-only filesystems, volume quotas, free disk space, inodes, log collectors, and retrieval paths. When a distroless image lacks **sh/df**, use authorized node/debug tooling rather than guessing paths from the host.

### 8.2. Three Boundaries to Watch in Docker and Kubernetes

1. **PID namespace:** the JVM's PID inside the container can differ from the Java process PID seen from the host. Pass the PID valid in the environment where `jcmd` attaches.
2. **Mount namespace:** **file=/diagnostics/gc.log** lives in the JVM's namespace. `kubectl exec` into a sidecar does not guarantee the sidecar shares that mount path; each container needs explicit mounts declared.
3. **Logging pipeline:** **output=stdout** from the JVM goes to the runtime/container log collector if wired properly. It does not write a file on the workstation running **kubectl** or Docker CLI.

In **Kubernetes**, an **emptyDir** volume lives with the Pod and counts against ephemeral-storage limits; **emptyDir medium: Memory** is memory-backed tmpfs. A **PVC** can fit when logs must survive Pod replacement, though permissions, quotas, throughput, and security must still be checked. Logs written to a container's rootfs can be lost when the container is replaced.

Read-only observation commands (substitute actual Pod and namespace):

~~~bash
kubectl get pod java-app-0 -o wide
kubectl exec java-app-0 -c app -- id
kubectl exec java-app-0 -c app -- df -h /diagnostics
kubectl logs java-app-0 -c app --since=10m
~~~

**kubectl logs** reads the runtime-collected stream, typically stdout/stderr; it does not automatically read arbitrary files under **/diagnostics**. To copy files, use shared volumes or **kubectl cp** when `tar` and permissions allow.

### 8.3. `VM.log rotate`

~~~bash
jcmd 12345 VM.log rotate
~~~

This command asks HotSpot to rotate **file log outputs** per configured policy; it does not delete old logs or free unlimited disk space. Check **VM.log list** and evidence retention needs before running. If a filesystem is filling up, address the producer, quotas, and logging config rather than repeatedly rotating.

## 9. Reverting Changes When the Collection Window Ends

**Restoring requires knowing the pre-change state.** `VM.log` keeps no automatic history for an "undo" button. When the investigation ends, follow this sequence:

1. Confirm the added output's name/ID via **jcmd PID VM.log list**.
2. If that output was **dedicated solely to this incident**, set its selector to **all=off**.
3. If you modified an existing stdout/stderr/file output, restore the **exact `what` and `decorators` from your pre-session snapshot**, rather than shutting off all logs.
4. Run **VM.log list** again to confirm and record the post-rollback state.
5. Retrieve and integrity-check the files, then retain/clean up per policy.

Suppose **#2 was just verified as the dedicated debug file**:

~~~bash
jcmd 12345 VM.log output='#2' what='all=off'
jcmd 12345 VM.log list
~~~

This disables log selection for output #2 without deleting already written files. **Never target `#2` without verifying right then that it points to the intended output.**

Avoid using the following as a way to end a single debug session:

~~~bash
jcmd 12345 VM.log disable
~~~

Because **disable** shuts off **all Unified Logging** and clears existing settings, it can suppress warning/error lines operations depend on. Use it only when intentionally managing all outputs with a full restoration plan.

If the old stdout snapshot was:

~~~text
#0: stdout all=warning uptime,level,tags
~~~

and an operator modified stdout, the corresponding restoration is:

~~~bash
jcmd 12345 VM.log output=stdout \
  what='all=warning' decorators='uptime,level,tags'
jcmd 12345 VM.log list
~~~

**This example applies only to the baseline above.** If the real config held additional selectors, restore all prior settings from your snapshot.

## 10. Distinguishing Startup `-Xlog` from Runtime `VM.log`

| Mechanism | Scenario | Boundary |
| --- | --- | --- |
| **java -Xlog:help** | Query a Java binary for tags/levels/outputs | Does not inspect a running JVM. |
| **-Xlog:...** at startup | Capture class/GC/safepoint events from session start | Changing startup flags requires redeploy/restart. |
| **jcmd PID VM.log list** | Inspect outputs of a live process | Does not replay past logs. |
| **jcmd PID VM.log output=...** | Enable/adjust logging on a running app | Cannot retroactively emit events prior to enabling. |
| **-Xlog via deploy config** | Persist selectors across restarts | Must manage files/rotation/permissions at deploy time. |

Startup configuration example:

~~~bash
java '-Xlog:gc*=info:file=/diagnostics/gc-start.log:time,uptime,level,tags:filecount=5,filesize=10M' \
  -jar application.jar
~~~

**application.jar** is an example JAR name. When investigating **startup**, enabling logs at launch captures events before `jcmd` could even attach. When a service is already warm and needs temporary observation, `VM.log` is suited for time-bounded verbosity increases.

**Runtime changes do not survive JVM restarts.** Seeing a file still on a volume after a deploy does not prove the new JVM uses the same selectors. Run **VM.log list** on the new process.

## 11. Runnable Java 21 Practice Program

The small program below prints its PID and runs for roughly one minute so you can test `VM.log` from a second terminal. It performs small allocations, though **there is no guarantee all GC log types will appear**, since actual GC activity depends on collector, heap, runtime conditions, and compiler optimizations.

**File `LogProbe.java`**

~~~java
public final class LogProbe {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("READY pid="
                + ProcessHandle.current().pid());

        byte[][] recent = new byte[8][];
        for (int i = 0; i < 300; i++) {
            byte[] payload = new byte[128 * 1024];
            payload[0] = (byte) i;
            recent[i % recent.length] = payload;

            if (i % 100 == 0) {
                System.out.println("PHASE " + i);
            }
            Thread.sleep(200);
        }
        System.out.println("DONE");
    }
}
~~~

Compile/run with JDK 21:

~~~bash
javac --release 21 LogProbe.java
java -Xms32m -Xmx32m LogProbe
~~~

**Stdout on normal completion:** the first line is **READY pid=<actual PID>**, followed sequentially by **PHASE 0**, **PHASE 100**, **PHASE 200**, and finally **DONE**. The PID varies per run and timing fluctuates slightly by system; **never hardcode a fake PID as expected output**.

From a second terminal, assuming the program printed PID **24680**, substitute the real PID:

~~~bash
jcmd 24680 VM.version
jcmd 24680 help VM.log
jcmd 24680 VM.log list
~~~

To test a file output locally where permissions and disk space are confirmed:

~~~bash
jcmd 24680 VM.log \
  output='file=/tmp/log-probe-gc.log' \
  what='gc*=debug' \
  decorators='uptime,level,tags' \
  output_options='filecount=2,filesize=5M'
jcmd 24680 VM.log list
~~~

**/tmp** is only a local test path. Inside containers, `/tmp` may be a small volume, tmpfs, or writable layer requiring separate checks; never copy this path mechanically to production.

If the program exits before you finish, start **a new JVM and read the new PID**. Never target an old PID with `jcmd`, as the OS can reuse PIDs. Once enabled, inspect the file and event counts, then disable the test output per Section 9 before ending a long session.

## 12. Choosing Tags for Diagnostic Scenarios

| Issue | Possible starting selector | How to interpret results |
| --- | --- | --- |
| Abnormal GC, need overview | **gc=info** or **gc*=info** | Pair with heap occupancy, allocation, pause metrics. |
| Need GC/heap details | **gc*=debug** or **gc+heap=debug** | Mind level thresholds, tag sets, collector, and overhead. |
| Suspected safepoint latency | **safepoint=info** | Compare request timestamps, CPU, thread states. |
| Class loading after deploy | **class+load=info** | Shows only events from enable time onward, not full history. |
| Native thread activity | Selector like **os+thread=info** if supported | Distinguish native TID from Java thread ID. |
| JIT compilation | Look up matching tags in target's **-Xlog:help** | Correlate with JFR/compiler activity; never invent tag names. |

**There is no one-size-fits-all selector.** Log just enough to test your hypothesis, escalating from info to debug/trace only when needed while watching write rates. **all=trace** is generally far too broad for production outside strictly controlled scenarios.

To separate **no events occurred** from **events were not captured**, always record: when logging started, actual selectors from `list`, duration, workload, collector, file output, and any log loss.

## 13. Observer Effect of Logging

Increasing logging can raise:

- CPU cost for formatting messages, metadata, and writing files.
- Disk I/O, latency when storage/remote volumes stall, and pressure on log collectors.
- Filesystem/ephemeral-storage consumption, risking rotation overwriting files before collection.
- CPU/lock contention and jitter in p95/p99 latency under high log volume.
- Risk of exposing VM config, paths, class/module names, or sensitive details depending on events.

**Never treat `VM.log` as zero-cost invisible observation.** Record enable/disable timestamps, capture baselines, compare metrics over the same window, and account for workload shifts. A p99 increase after enabling trace can be a mix of the incident and logging overhead.

**-Xlog:async** is an asynchronous Unified Logging mode supported in modern JDKs, reducing direct I/O waits at the cost of buffer/CPU usage and possible message drops on buffer overflow or crash. Never assume every mode can be toggled dynamically via `VM.log`; check docs/flags of the running JVM before changing logging mechanisms.

When file rotation overwrites older lines before collection, the data no longer represents the full incident. Size `filecount`/`filesize` against expected write rate, observation window, and disk capacity, and inspect remaining files afterward.

## 14. Troubleshooting When `VM.log` Does Not Work as Expected

| Symptom | Hypothesis | How to check |
| --- | --- | --- |
| **`jcmd` missing in image** | Minimal/jlink runtime image or wrong PATH | Check JDK tools in container/node; use supported debug tooling. |
| **Could not attach / process not found** | Wrong PID namespace, different user/permissions, attach restricted | Verify target PID, user, JVM vendor, container PID namespace. |
| **Unknown diagnostic command: VM.log** | VM does not support command or non-HotSpot VM | Run **jcmd PID help** and **VM.version**. |
| **`VM.log list` shows no debug output** | Not enabled or modification failed | Check exit status, stdout/stderr, and `list` after command. |
| **Output file not created** | Wrong path in JVM view, missing permissions, read-only, disk/quota full | Check mounts, UID/GID, `df -h/-i` on target filesystem. |
| **File exists but has no logs** | Selector too narrow, level insufficient, event didn't happen | Compare **gc** vs. **gc***, enable time, workload, collector. |
| **Far more logs than expected** | Broad wildcard/trace, multiple outputs | Narrow selector, lower level, cap `filecount`/`filesize`. |
| **stdout appears only in `docker logs`** | stdout belongs to JVM in container, scraped by collector | Check Docker/Kubernetes logging pipeline. |
| **Output `#2` isn't the intended file** | ID shifted or misremembered | Always run **VM.log list** right before editing. |
| **Debug level lost after restart** | Runtime changes do not persist across restarts | Put `-Xlog` in startup flags if needed permanently. |
| **Cannot alter rotation on existing output** | `output_options` does not flexibly update existing outputs | Create a new output with desired rotation. |
| **Latency worsens when trace enabled** | Observer effect and/or genuine incident | Lower level, run A/A comparison, inspect timing, CPU/disk. |

When a command is documented **Impact: Low**, that refers solely to the JDK diagnostic command invocation; it **does not** prove debug/trace logging has no load impact over several minutes. Evaluate both impacts separately.

## 15. Practical Scenario: Enabling GC Logs for 5 Minutes

Suppose service p99 latency spikes and the team needs more GC visibility. A structured collection session:

**Step 1 — Identify target:** Pod/container/host, JVM PID, version/vendor, collector type. Never guess a PID; verify with **VM.version**.

**Step 2 — Snapshot current config:** run **VM.log list**, save output selectors/decorators and important files. Check tags via **-Xlog:help on the matching binary**.

**Step 3 — Choose file and limits:** e.g., **/diagnostics/incident-gc.log** on a mount writable by the JVM; verify disk/quota/inodes. Choose **gc*=debug**, 5 minutes, rotation, and retrieval path. If only a summary is needed, start narrower.

**Step 4 — Enable temporarily:**

~~~bash
jcmd 12345 VM.log \
  output='file=/diagnostics/incident-gc.log' \
  what='gc*=debug' \
  decorators='time,uptime,pid,level,tags' \
  output_options='filecount=5,filesize=10M'
jcmd 12345 VM.log list
~~~

**Step 5 — Monitor:** observe generated logs, CPU/disk/I/O, and request latency. Record start/change timestamps; do not blame every spike on GC merely for overlapping in time.

**Step 6 — Restore:** identify the new investigation output via **list**, set **all=off** on that output when done, or restore the exact baseline if an existing output was touched. Run **list** after rollback.

**Step 7 — Preserve evidence:** verify the file on the JVM filesystem, copy it out, check size/checksum once writes stop, and enforce proper permissions/retention. Never post sensitive logs publicly.

This is a verifiable workflow. No `VM.log` command creates causal proof by itself; combine timelines and metrics.

## 16. Self-Check with Answers

**1. `VM.log list` shows only `all=warning`. Does that mean the JVM lacks `gc` support?**

No. That shows **currently enabled** configuration, not the tag catalog. Run **-Xlog:help** on the matching binary to see supported tags.

**2. Why does `gc=info` not show `[gc,heap]`?**

Without a wildcard, it matches only the **gc** tag set. To match all tag sets containing `gc`, use **gc*=info** (expecting higher volume).

**3. Is `VM.log disable` a safe way to turn off a debug file?**

No. **disable** shuts off all Unified Logging, not just one output. Turn off selectors on that specific output or restore the saved configuration.

**4. Why was `VM.log output=file=/diagnostics/gc.log` run from the host, yet no file appeared on the host?**

Because the path is opened by the **target JVM**, potentially inside a container mount namespace. Check volume mappings, JVM permissions, and container filesystem paths.

**5. `VM.log list` confirms `gc*=debug` is enabled, yet the file has no GC lines. Can we conclude no GC occurred?**

No. Appropriate events may not have occurred yet, logging may have started too late, the output may be inaccessible, or event/tag/level may differ. Check timing, selectors, collector, and other telemetry.

**6. Why does `output=stdout` not necessarily print in the terminal running `jcmd`?**

Because stdout is the **JVM's** stream, not **`jcmd`'s** stdout. A container runtime may forward JVM stdout to `docker logs`/`kubectl logs`.

**7. Do tag changes made via `VM.log` persist across process restarts?**

Normally no. They are runtime-only; to persist across restarts, place **-Xlog** options in startup flags and verify on the new JVM.

**8. Can you reuse output ID `#2` from a previous deployment?**

No. Output IDs belong to each running JVM's current configuration. Always run a fresh **VM.log list** to verify names and IDs.

**9. Why not immediately enable `gc*=trace` in production?**

Trace can emit massive log volume, impacting CPU/I/O, disk, and latency. Pick a level sufficient for your hypothesis, bound the duration, and prepare a rollback.

**10. `-Xlog:help` lists a tag—does that guarantee at least one matching line will appear within a minute?**

No. That only means the binary recognizes the tag. Actual log sites and events depend on workload, VM, config, level, and observation timing.

## 17. Mental Traps to Avoid

1. Mistaking **VM.log list** for the full list of supported tags.
2. Taking **-Xlog:help** output from `java` on PATH without checking JDK vendor/version against the target.
3. Assuming **gc=debug** covers every **gc+...** tag set.
4. Thinking debug logging emits only debug-level lines; more severe levels are included too.
5. Overwriting stdout and losing initial warning/error selectors.
6. Using **VM.log disable** to roll back a single output.
7. Hardcoding output IDs from another process or across restarts.
8. Ignoring file rotation, disk/quotas, inodes, and write rate when raising verbosity.
9. Assuming files are created in **`jcmd`**'s cwd rather than the **target JVM**'s cwd/filesystem.
10. Confusing the JVM's stdout with the terminal running `jcmd`.
11. Thinking **VM.log** alters application Logback/Log4j loggers.
12. Treating **no logs seen** as proof **no event occurred**.
13. Enabling debug after an incident and expecting to see past events.
14. Assuming runtime configuration survives restarts.
15. Blaming every new latency spike on GC without accounting for logging overhead.
16. Copying an actively written file and treating checksums as final.

## 18. Post-Collection Checklist

- [ ] Verified exact **JVM PID, VM version/vendor, container/host**.
- [ ] Discovered tags via **java -Xlog:help** on the matching binary.
- [ ] Saved **VM.log list** before making changes.
- [ ] Chose selector with right **tag set + wildcard + level**.
- [ ] Selected output, decorators, rotation, and bounded collection window.
- [ ] Verified path, **JVM** permissions, filesystem, quota, inodes, and file retrieval.
- [ ] Confirmed changes with **VM.log list** and actual emitted logs.
- [ ] Recorded enable/disable timestamps and CPU/I/O/latency to guard against observer bias.
- [ ] Turned off **only the target output** or restored old selectors without global disable.
- [ ] Ran **VM.log list** after rollback and secured retrieved files/evidence.

## Technical References

- [JDK 21 — jcmd: VM.log (output, what, list, rotate, disable)](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [JDK 21 — java: Unified JVM Logging and -Xlog:help](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [OpenJDK JEP 158 — Unified JVM Logging](https://openjdk.org/jeps/158)
- [OpenJDK JEP 271 — Unified GC Logging](https://openjdk.org/jeps/271)
- [Inside Java — JVM Logging and runtime VM.log](https://inside.java/2022/11/07/sip071/)
- [AWS Corretto — Asynchronous Logging and dynamic VM.log configuration](https://aws.amazon.com/blogs/developer/asynchronous-logging-corretto-17/)
- [Java SE 21 — ProcessHandle.current().pid()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessHandle.html)

**Success criterion:** you can state **which tags exist, which selectors are active, where the output file lands, the verbosity level, the observation window, the logging cost**, and **how to restore cleanly**. Without these, raising logs via `VM.log` may generate many lines yet fail to produce reliable evidence for JVM diagnostics.
