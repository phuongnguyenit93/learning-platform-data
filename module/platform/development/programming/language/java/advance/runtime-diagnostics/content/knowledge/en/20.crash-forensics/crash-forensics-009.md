# 20.9 Distinguishing JVM Self-Reported Fatal Errors from OS-Terminated Processes

## Learning Objectives

When a Java application suddenly disappears, multiple mechanisms can lead to the same symptom: the service stops responding, the process is gone, the pod restarts, and logs stop mid-stream. However, **the JVM detecting a severe error itself and writing a fatal error log** vs. **the process being terminated by the operating system or orchestrator** are two distinct investigation branches. An uncaught Java exception, a `System.exit` call, a container `OOMKilled` event, or a `SIGSEGV` in a native library must not be lumped together as one generic “JVM crash.”

This lesson belongs to **Crash and Post-Failure Analysis**, focusing on identifying **who or what mechanism caused the process to terminate**, which evidence is trustworthy, which traces may be absent, and how to investigate methodically after an incident.

After this lesson, you will be able to:

1. Distinguish application-level Java errors, intentional JVM exits, HotSpot fatal errors, external signals, and Linux OOM killer / cgroup OOM kills.
2. Read the right evidence types accurately: `hs_err_pid*.log`, stack traces, heap dumps, core dumps, exit statuses, kernel logs, cgroup `memory.events`, and container termination reasons.
3. Explain why **exit code 137 does not by itself prove `OOMKilled`**, why **absence of `hs_err` does not prove an OS kill**, and why an `OutOfMemoryError` does not necessarily kill the entire JVM.
4. Build a source–evidence–cause timeline across the JVM, OS, service manager, and orchestrator without confusion.
5. Collect evidence early, securely, and non-intrusively, then state conclusions calibrated by confidence level.
6. Practice with a Java 17+ program simulating **controlled** exit paths, without attempting to exhaust memory or break a real JVM.

Scope: Java 17+ running on HotSpot/OpenJDK, with Linux or containers/Kubernetes where OS examples apply. Logging behavior, exit statuses, signals, core dumps, and management tools depend on OS/JDK/vendor/container runtime. Always verify on your specific environment; **never use kill/crash operations to test on production services**.

## 1. Ask the Right Question: By What Mechanism Did the Process Terminate?

When an application dies, at minimum separate five groups:

| Group | Description | Typical evidence | What not to infer hastily |
| --- | --- | --- | --- |
| **Java-level failure** | A thread throws an uncaught exception, including some `OutOfMemoryError`s | Java exception stack trace, app logs, sometimes nonzero exit | Not automatically a fatal JVM crash or OS OOM kill |
| **Intentional JVM termination** | `main` finishes, `System.exit`, `Runtime.halt`, or `ExitOnOutOfMemoryError` policy | Exit status and pre-exit logs; hooks may run | Non-zero exit code is not necessarily an OS signal |
| **JVM fatal error / native crash** | HotSpot or native code hits a severe fault: `SIGSEGV`, `SIGBUS`, fatal internal error, intentional `CrashOnOutOfMemoryError` | `hs_err_pid*.log`, possibly core dump, signal-related status | A `SIGSEGV` signal from the kernel does not mean OOM killer termination |
| **External termination** | `systemd`, operator, deploy controller, liveness probe, or timeout sends `SIGTERM` and possibly `SIGKILL` | Service manager/events, signal status, lifecycle records | `SIGKILL` is not necessarily due to running out of memory |
| **OS/cgroup OOM kill** | Kernel selects one or more tasks to kill due to memory pressure/limit | Kernel OOM message, cgroup `oom_kill` increments, Kubernetes reason `OOMKilled` | Low `heap used` does not rule out total cgroup memory exceeding the limit |

A single process death can have **multiple contributing factors**. For example, growing native memory pushes the container past `memory.max`; the kernel `SIGKILL`s Java without letting the JVM run its fatal-error handler. Or Java code catches OOME and calls `System.exit`: there is an OOME and a nonzero exit, yet no OOM killer. Therefore, distinguish:

- **Symptom:** the process vanished or the application stopped serving.
- **Termination mechanism:** normal exit, signal, fatal error, or kernel kill.
- **Root cause:** code bug, data growth, memory budget, native library, deployment, watchdog, storage failure, etc.
- **Evidence:** artifact type and the source that produced it, with matching timestamp/instance.

“The OS sent the signal” and “the fault originated in JVM/native code” are not always strict opposites. For instance, an invalid memory access in native code causes the kernel to deliver `SIGSEGV`; the JVM may catch that signal, write `hs_err`, and then terminate. That differs from **the kernel OOM killer sending `SIGKILL` to reclaim memory**.

## 2. Understanding Three Easily Confused Termination Paths

### 2.1. A Java exception is not automatically a JVM fatal error

If a thread throws an uncaught `RuntimeException`, the runtime typically prints a stack trace via the uncaught exception handler; **only that thread terminates**. The JVM can keep running if non-daemon threads remain. If `main` was the last user thread, the JVM may exit on its own and the shell sees an error code; this is not evidence of a HotSpot/native crash.

`java.lang.OutOfMemoryError` is a **Java-level `Error`**: it can stem from heap, metaspace, native threads, direct buffers, or another limit depending on its message and origin. It can also be thrown, caught, or handled by the JVM according to flags. Do not assume `hs_err` exists for every OOME. A heap dump from `-XX:+HeapDumpOnOutOfMemoryError` is not the same as a fatal error log.

### 2.2. A JVM fatal error is a different situation

HotSpot invokes fatal error reporting when it hits a fault from which it cannot safely continue—such as an internal VM error, a memory access fault in native/VM code, certain fatal native allocation failures, or an intentional crash configuration. The JVM may write `hs_err_pid*.log` with “A fatal error has been detected by the Java Runtime Environment”, “Problematic frame”, thread state, native/Java stacks, and VM/OS details.

Key points:
- **Having `hs_err` with matching timestamp/PID** is strong evidence that the JVM's fatal-error reporting mechanism ran.
- **Having `hs_err` does not prove pure Java code caused the bug**, because JNI, native agents, drivers, JVM bugs, or hardware may be involved.
- **Not seeing `hs_err`** does not prove there was no JVM fatal error: the JVM may have run out of time to write, lacked permissions/disk, been killed abruptly, written elsewhere, been deleted, or produced a partially corrupted log.

### 2.3. Receiving a signal does not default to an OOM kill

On Linux:
- **`SIGTERM` (15)** is a termination request; a standard HotSpot JVM gets a chance for controlled shutdown if signal handling is normal.
- **`SIGKILL` (9)** cannot be caught, ignored, or blocked by shutdown hooks: the process stops immediately with no chance to write `hs_err` or a heap dump via normal JVM paths.
- **`SIGSEGV` (11)** is a memory access fault; HotSpot may handle it to write a fatal error report, or it may die before finishing artifacts.
- **`SIGABRT` (6)** can appear when native code/JVM intentionally aborts or from another actor; you must verify the source.
- **`SIGBUS` (7, on Linux)** can relate to memory-mapped region access or memory/hardware faults; insufficient to call it `OOMKilled`.

An operator running `kill -9`, a service manager escalating shutdown, and the kernel OOM killer can all produce a `SIGKILL` termination status. **You must know who sent the signal, why, and when**, rather than merely reading the number 9.

## 3. Quick Diagnostic Table by Clue

| Observation | Reasonable hint | What to verify |
| --- | --- | --- |
| Fresh `hs_err_pid1234.log`, header shows `SIGSEGV`, problematic frame is `libxyz.so` | JVM/native fatal error occurred | Exact PID/start time? JNI/agent/JVM versions? core dump? |
| App logs show “Exception in thread main” then exit 1 | Uncaught Java exception may have ended the JVM | Any live threads left? `System.exit` in an error handler? |
| App logs show “OutOfMemoryError: Java heap space” | JVM threw a Java heap OOME | Did it actually exit? heap dump? heap/GC trend? `ExitOnOOME` flags? |
| Pod `lastState.terminated.reason = OOMKilled`, `exitCode 137` | Container was confirmed OOM-killed by runtime/orchestrator | Exact container, timestamp, cgroup/Node/kernel evidence, and memory source |
| Only `exitCode 137` seen | Usually consistent with `SIGKILL` under shell conventions | What is the Kube reason? did the system send `SIGKILL`? could the app call `exit(137)`? |
| `ExitCode 143` alongside rollout/termination event | Possibly `SIGTERM` per `128+15` convention | Deployment/liveness/systemd logs? did the JVM have shutdown hooks? |
| `ExitCode 139`, `hs_err` shows `SIGSEGV` | High likelihood of native/VM memory fault | Core/native stack, JVM/JNI/agent; do not assume OOM killer |
| No `hs_err`, logs stop abruptly, `memory.events` `oom_kill` increments | Suspect kernel/cgroup OOM kill | Counters from the right cgroup? kernel log / termination reason? |
| No `hs_err`, process died after liveness probe failed | Suspect orchestrator restart | Probe failure reason, grace period, signal/exit code, prior app hang |
| Core dump exists without `hs_err` | Process died from a fatal signal / core-producing mechanism | Which PID and signal produced the core, core handler; do not rush to blame JVM bug |
| Service restarted yet old PID has no exit evidence | Could be rolling deploy, process supervisor, runtime reset | Lifecycle events, previous logs, restart reason, PID/instance mapping |
| `oom_kill` counters did not increment, app logs show exit request | No evidence yet of kernel OOM kill | Same cgroup/time window? systemd/container audit? |

This table is an **investigation guide**, not a 1-to-1 deduction rule. A container may receive `SIGTERM` followed by `SIGKILL` after its grace period and report exit 137, with a reason other than `OOMKilled`. A JVM can crash natively while the container reports a generic `Error`. Exits 1, 134, 137, 139, and 143 all require corroborating sources.

## 4. Reading `hs_err_pid*.log`: When the JVM Managed to Report a Fatal Error

### 4.1. Typical contents

A HotSpot fatal error log, depending on JDK/version and completeness, may record:

- Header “A fatal error has been detected by the Java Runtime Environment”.
- Signal/code: `SIGSEGV`, `SIGBUS`, `SIGILL`, internal error, and related addresses.
- PID, thread ID, timestamp, VM/version/build, uptime.
- **Problematic frame:** e.g., JIT code, `libjvm.so`, `libc.so`, JNI library, native agent, etc.
- Current thread, thread state, native/Java stacks, dynamic libraries.
- Heap/metaspace, VM arguments, command line, OS environment, and memory map.
- Instruction pointers/registers or lower-level details, not always complete.

**Read accurately:** “Problematic frame” is where the fault was observed or detected, **not necessarily where the bug began**. Heap corruption may have happened earlier; buggy JNI memory writes can make the JVM die later in unrelated code. A `libjvm.so` frame is insufficient to prove a “JDK bug” if an agent, JNI, or prior native corruption caused it.

### 4.2. Sample trace, for recognition only

~~~text
# A fatal error has been detected by the Java Runtime Environment:
#
#  SIGSEGV (...) at pc=..., pid=1234, tid=...
#
# Problematic frame:
# C  [libexample.so+...]
#
# An error report file with more information is saved as:
# /var/log/app/hs_err_pid1234.log
~~~

This is an **illustrative format sample**, not output from a program in this lesson, nor a guarantee that every log looks identical. `C` on the frame line denotes a native C/C++ frame in HotSpot notation; you may also see `J` (compiled Java), `V` (VM code), `j` (interpreted Java), and other markers depending on version.

### 4.3. Verifying artifact accuracy

When searching for `hs_err`, ask:
1. Where did the JVM actually write? Is the startup working directory where the operator is looking?
2. Was `-XX:ErrorFile` set to redirect output? Was `%p` replaced by the PID?
3. Does the file belong to the **exact process**, instance/container, and timestamp?
4. Was it written completely or truncated due to a full disk or being killed mid-report?
5. Which native libraries/agents are in the loaded modules? Did any version/build change right before the incident?
6. Is there a matching core dump or symbol/debug info for deeper investigation?

If `hs_err` still exists after the process restarted, **preserve the original intact**, record timestamp, path, and checksum when needed, and restrict public sharing because it may contain sensitive data.

## 5. When `hs_err` Is Missing and What That Means

Many scenarios **do not expect** an `hs_err`:

- A Java exception or `OutOfMemoryError` was handled at the Java layer.
- The main thread finished and the JVM exited normally.
- `System.exit(code)` was called.
- `Runtime.halt(code)` terminated immediately without running normal shutdown sequences.
- The process received `SIGKILL` from an operator, service manager, or kernel OOM killer.
- The container was deleted/killed while the JVM had no chance to execute its fatal-error handler.

Yet **the absence of `hs_err` does not prove** any of the above, because it could also be a JVM fatal error that **failed to write a file**: full disk, permission denied, missing directory, deleted ephemeral filesystem, severely corrupted VM, very early native crash, fatal signal/core policy interaction, a non-HotSpot JVM, or the file being written elsewhere.

Conversely, the presence of `hs_err` does not rule out external factors: an operator-installed native agent, file-mapping errors, hardware/OS faults, or the process being stopped after the JVM had already started reporting a fatal error. You must connect **multiple evidence sources with the same PID/timestamp**.

## 6. Distinguishing Java `OutOfMemoryError` from Kernel/Cgroup OOM Kills

### 6.1. `OutOfMemoryError` is a JVM/Java-level event

Example messages:
- `java.lang.OutOfMemoryError: Java heap space`;
- `java.lang.OutOfMemoryError: GC overhead limit exceeded`;
- `java.lang.OutOfMemoryError: Metaspace`;
- `java.lang.OutOfMemoryError: Direct buffer memory`;
- `java.lang.OutOfMemoryError: unable to create native thread`.

They reflect different resource regions/conditions and do not mean the OS killed the process. Some cases are Java-level OOMEs thrown by Java libraries/classes; not every variant guarantees a heap dump.

The application may:
- catch OOME and keep running in a degraded state;
- fail to catch it in one thread, killing that thread while the JVM stays alive;
- exit via a fatal policy, wrapper, or `System.exit`;
- get cgroup OOM-killed at another time if total memory keeps climbing.

**Do not conclude “out of heap” just because a pod was `OOMKilled`**: container memory includes many components beyond the Java heap such as metaspace, code cache, direct/native buffers, thread stacks, `malloc`/JNI, page cache, and other processes in the cgroup. Equally, do not conclude “OS kill” just because logs contain `OutOfMemoryError`.

### 6.2. HotSpot JVM flags that change termination paths

Relevant options include:
- `-XX:+HeapDumpOnOutOfMemoryError`: attempts to create a heap dump for supported VM-detected OOMEs; requires disk space/permissions and is not guaranteed for OS kills.
- `-XX:HeapDumpPath=...`: destination for the heap dump when triggered; verify path/volume.
- `-XX:+ExitOnOutOfMemoryError`: policy telling the JVM to exit on OOME.
- `-XX:+CrashOnOutOfMemoryError`: attempts to trigger a fatal-error crash on OOME for specially designed diagnostic cases; never enable casually in production.
- `-XX:ErrorFile=...`: destination for HotSpot fatal error logs.
- `-XX:OnOutOfMemoryError=...`: runs a configured command on OOME under supported conditions; not guaranteed to run on kernel `SIGKILL`.

**Note:** flags do not change cgroup memory semantics. Even with `HeapDumpOnOutOfMemoryError`, a `SIGKILL` can strike before the JVM notices or writes a Java OOME. Heap dumps can also cause disk pressure and contain sensitive data.

### 6.3. The OS OOM killer takes a different path

When the Linux kernel runs out of memory system-wide or a memory cgroup exceeds its limit, OOM logic selects a task and sends `SIGKILL`. For the chosen JVM, the process **has no say in the matter**: shutdown hooks do not run, and the JVM gets no normal opportunity to write `hs_err` or a heap dump at kill time.

Evidence close to the source:
- Kernel logs show an OOM message and **Killed process** with PID/comm/memory context.
- cgroup v2 `memory.events` (or `memory.events.local`) shows the `oom_kill` counter incrementing **in the exact window**.
- Container runtime / Kubernetes reports last terminated reason `OOMKilled` for that exact container.
- Metrics `memory.current`, `memory.max`, working set/RSS, `restartCount`, node/container pressure, and matching time series.

**Never treat a post-restart snapshot as pre-crash memory.** The old cgroup may be gone, counters reset, or logs rotated; you need historical metrics or runtime/monitoring records.

### 6.4. Cgroup OOM, node OOM, userspace OOM management, and eviction

These phenomena are not identical:

| Mechanism | Decision maker | Typical trace |
| --- | --- | --- |
| Memory cgroup exceeds limit | Kernel memcg OOM | `memory.events` `oom_kill`, container `OOMKilled`, exit via `SIGKILL` |
| Node/global memory pressure | Kernel global OOM killer | Kernel OOM message, victim PID, node memory metrics; container status varies by runtime |
| `systemd-oomd` or pressure daemon | Userspace daemon picks cgroup/process to kill | Daemon journal, cgroup/pressure metrics, signal; may have **no kernel OOM message** |
| Kubelet node-pressure eviction | Kubelet evicts pod per eviction policy | Pod events/reason `Evicted`, kubelet logs; not by default kernel `OOMKilled` |
| Liveness probe / deploy / timeout | Controller, kubelet, service manager | Probe failures, rollout events, `SIGTERM` and possibly `SIGKILL` after grace period |
| App exits itself due to OOME | JVM or app policy | OOME log/flag, process exit, not necessarily `OOMKilled` |

When an operator says “the pod OOM'd,” ask them to clarify whether it was **`OOMKilled`**, **`Evicted` due to `MemoryPressure`**, **application OOME logs**, or a **node/global kill**. Remediation differs completely: live heap tuning, native memory/cgroup budgeting, node capacity, request/limit/eviction policy, or an application bug.

## 7. Exit Status and Signals: Clues, Not Verdicts

### 7.1. Commonly seen numbers

In Linux shells and many container runtimes, a common convention is **`128 + signal number`** when a process is terminated by a signal. For example:

| Observed code | Possible correspondence | Verification required |
| --- | --- | --- |
| 0 | Completed successfully per app convention | Did the app actually serve / meet SLOs before exiting? |
| 1 | General error, uncaught exception, explicit `exit(1)` | Stack trace, framework exit policy, service manager |
| 134 | `128 + SIGABRT(6)` | Fatal/native abort or external actor? `hs_err`/core? |
| 137 | `128 + SIGKILL(9)` | OOM killer or `kill -9`/timeout/probe? |
| 139 | `128 + SIGSEGV(11)` | Native/VM memory fault or another signal? `hs_err`/core? |
| 143 | `128 + SIGTERM(15)` | Deploy, pod termination, service manager, operator? |

This is not a guaranteed mapping across every OS, shell, and runtime. **An exit code by itself does not record who sent the signal.** A Java program can call `System.exit(137)` and produce code 137 **without any `SIGKILL`**. A wrapper/supervisor may report its own status or transform a child process's status.

On Linux, a parent process can distinguish **`WIFEXITED`** from **`WIFSIGNALED`** in raw wait status; orchestrator logs may present a normalized exit code. Never take the string “exitCode: 137” on a dashboard as complete proof that the kernel killed the process for running out of memory.

### 7.2. `SIGTERM` vs. `SIGKILL`

`SIGTERM` normally gives the program an opportunity to:
- receive the signal via runtime handlers;
- run shutdown hooks if the JVM is shutting down normally and is not forced;
- release connections, flush logs, fail readiness, or drain traffic.

Yet `SIGTERM` may still fail to produce a clean shutdown: the process may be hung, a hook may take too long, a signal handler may be altered, or the controller sends `SIGKILL` after the grace period. After `SIGKILL`, no further Java shutdown logs appear; the absence of “shutting down” cannot tell a kernel OOM apart from an operator kill.

**Never test `kill -9` on live services** just to verify code 137. If demonstration is needed, use a standalone Java process in a lab environment with its PID noted and scope clearly bounded.

### 7.3. Is `SIGSEGV` an “OS termination”?

A memory access fault in native/JIT/JVM code typically causes the kernel to deliver `SIGSEGV`. Yet the root nature of the incident is a **memory fault** on the process's execution path; HotSpot usually tries to write a fatal error report. Therefore, an `hs_err` with `SIGSEGV` belongs to **native/JVM crash analysis**, not external administrative kills.

If the JVM uses JNI, monitoring agents, native libraries, `Unsafe`, or foreign/native interfaces, you cannot look solely at a `libjvm` frame and conclude HotSpot core has a bug; inspect caller/callee, versions, native memory corruption, and reproducibility.

## 8. Evidence from Linux: Kernel, Cgroups, and Service Managers

### 8.1. Kernel logs in the exact time window

Illustrative read-only commands (depending on distro and permissions):

~~~bash
journalctl -k --since "2026-10-29 09:00:00" \
  --until "2026-10-29 09:20:00"
dmesg -T
~~~

In a real incident, substitute the **exact incident window with the proper timezone**; `-T` converts kernel timestamps to wall time and can be skewed if the system clock changed. Prefer journal logs with accurate timestamps when available.

Look for:
- “Out of memory” and “Killed process PID ... (java)”;
- “Memory cgroup out of memory” or kernel/distro variants;
- PID and memory context, cgroup path, node/pod association;
- other kernel/device error signs where relevant.

**Missing OOM lines in `dmesg` do not rule out an OOM kill**: read permissions may be restricted, the ring buffer may have wrapped, logs may lack long-term retention, a userspace OOM daemon may have killed the process, or you checked the wrong node/time.

### 8.2. Cgroup v2 memory counters

Inside the **exact cgroup of the container/process** on a cgroup v2 system:

~~~bash
cat /sys/fs/cgroup/memory.events
cat /sys/fs/cgroup/memory.events.local
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
~~~

Meaning:
- **`memory.events`:** counters for states such as `low`, `high`, `max`, `oom`, `oom_kill`, etc., depending on kernel/config, usually hierarchical.
- **`memory.events.local`:** events local to this cgroup itself, avoiding propagation from descendants.
- **`memory.current`:** memory currently charged to the cgroup at read time.
- **`memory.max`:** hard memory limit or literal “max” if unlimited.
- **`oom_kill`:** number of OOM kills in the counter's scope. Compare **deltas over time**, not just a single cumulative value.
- **`oom`:** number of times the cgroup hit OOM conditions per kernel semantics; **not equal to kill count**.
- **`high`/`max`:** indicate pressure or hitting the respective limit; also do not by themselves prove a process was killed.

Verify the mount/cgroup path via `/proc/PID/cgroup` **before the process dies** or via the orchestrator/runtime. A container's `/sys/fs/cgroup` may be namespaced, visibility-restricted, or different from the host view's cgroup path. **If the cgroup was deleted on restart, you cannot read the new cgroup's counters and pretend they are pre-crash figures.**

A spike in `oom_kill` on a parent cgroup does not automatically mean Java was the victim: sidecars or other descendants may share the pod/cgroup. Match the kernel victim PID, container status, and timestamps.

### 8.3. `systemd` and userspace OOM managers

For a `systemd`-managed service:

~~~bash
systemctl status my-java-service
systemctl show my-java-service \
  -p Result -p ExecMainCode -p ExecMainStatus
journalctl -u my-java-service --since "2026-10-29 09:00:00"
journalctl -u systemd-oomd --since "2026-10-29 09:00:00"
~~~

Service names and timestamps above are examples. `systemd` can report `code=exited` or `code=killed` and signal status when available, along with restart/timeout/watchdog reasons depending on version. If `systemd-oomd` acted, its journal may be the primary evidence even when kernel logs lack a kernel OOM killer “Killed process” line.

Do not equate “service is active after restart” with “the old JVM never died.” Pull logs from the **old process run** and check the restart count.

### 8.4. Core dumps are not exclusive JVM evidence

On Linux, core dumps can be produced on fatal signals for many programs, not only the JVM. You can inspect:

~~~bash
ulimit -c
cat /proc/sys/kernel/core_pattern
coredumpctl list
~~~

`coredumpctl` depends on whether the host uses `systemd-coredump`. `ulimit`/`core_pattern` govern how cores are created/collected; files can be large, highly sensitive, and pruned by retention. **Having no core dump** does not prove the process did not crash; **having a core dump** does not automatically prove the root cause is inside the JVM core.

For a JVM fatal error, core/native stack + `hs_err` + symbols and native library versions complement each other; verify matching PID/timestamp/architecture.

## 9. Kubernetes and Containers: Inspect the Exact Container That Died

### 9.1. Common read-only commands

~~~bash
NS=default
POD=example-pod
CONTAINER=example-container

kubectl describe pod "$POD" -n "$NS"
kubectl logs "$POD" -n "$NS" -c "$CONTAINER" --previous
kubectl get pod "$POD" -n "$NS" -o json
~~~

Use real names and appropriate permissions. `--previous` fetches logs from the prior container instance if the runtime still keeps them; it **does not guarantee** full history across multiple restarts. Pod events have limited retention; JSON may contain sensitive metadata and must not be distributed raw.

Check:
- **`status.containerStatuses[].lastState.terminated.reason`**, `exitCode`, `startedAt`, `finishedAt`, `message`;
- `restartCount` of the **exact container** in the pod;
- pod phase/reason and Events: `OOMKilled`, `Evicted`, `Killing`, `Unhealthy`/liveness, rollout/drain, sandbox changes;
- memory limits/requests, actual resource usage **before death**, CPU throttling, node `MemoryPressure`;
- container IDs, pod UID, node ID, and process start times so you do not confuse a newly created pod with the same logical name.

**`reason=OOMKilled`** on a container's termination state is strong orchestrator/runtime-level evidence of an OOM kill. Still cross-check kernel/cgroup records, container memory breakdown, and workload to explain **why** it hit the limit. **`ExitCode=137` with `reason=Error`** may be a different kill; inspect events and the shutdown timeline.

### 9.2. Restart after liveness failure and shutdown escalation

Hypothetical example:

~~~text
12:00:00 liveness probe failed
12:00:01 kubelet requested termination (SIGTERM)
12:00:31 grace period expired; SIGKILL
12:00:32 container exit code 137
~~~

This produces exit 137 **without any kernel OOM killer**. To confirm it, look for liveness/probe failures, kubelet events, and the grace period. The underlying cause may be a JVM deadlock, GC pause, network timeout, or overly aggressive probe; `SIGKILL` was merely the **final termination mechanism**.

Conversely, `OOMKilled` can strike even if liveness probes were green just moments before; a kernel kill can outpace `SIGTERM`. Never rely on the presence or absence of a shutdown hook log as your sole criterion.

### 9.3. Docker runtime and non-Kubernetes setups

In Docker environments, with authorization:

~~~bash
docker inspect --format '{{.State.OOMKilled}} {{.State.ExitCode}} {{.State.FinishedAt}}' example-container
docker logs --timestamps example-container
~~~

This is illustrative Docker CLI syntax; substitute the real container ID/name. `OOMKilled=true` helps distinguish runtime-reported OOM termination from other nonzero exits. Docker does not necessarily keep all rotated logs; correlate timestamps, kernel/cgroup records, resource limit settings, and causes of memory growth.

On ECS, Nomad, `containerd`, or other platforms, look for **equivalent** termination reasons, exit statuses, and events rather than assuming every platform uses Kubernetes status fields.

## 10. Assembling Evidence: Which Source Answers Which Question?

| Question | Priority source | Limitations |
| --- | --- | --- |
| Did the JVM itself detect a fatal error? | `hs_err` file and header matching PID/timestamp; JVM stderr | Not finding the file does not rule it out |
| Was there a Java-level exception/OOME? | App logs/stderr, exception stack trace, heap dump, and JVM flags | Having an OOME does not mean the kernel killed the process |
| Did the process exit normally or via signal? | Parent/supervisor raw wait status, container runtime / service manager | Flattened `exitCode` can be ambiguous |
| If `SIGKILL`, who sent it? | Kernel OOM logs, cgroup `oom_kill`, orchestrator/events, audit/supervisor | Exit 137 alone does not identify the sender |
| Why was memory exhausted? | Memory timeline, container `memory.max`/`current`/`peak`, JVM heap/native memory, process RSS, workload | Post-restart snapshots are insufficient |
| Was there a native/JVM crash? | `hs_err`, core dump/native stack, loaded libraries, JDK build, agents/JNI | Problematic frame is not necessarily root cause |
| Was there a liveness/probe/rollout? | Pod events, kubelet/controller logs, service manager journal | Events have retention limits and clock skew |
| Was there node-level eviction/OOM? | Node kernel logs, `MemoryPressure`, eviction messages, kubelet/`systemd-oomd` | Do not confuse with container `OOMKilled` |
| Did a crash occur before a kill? | Timeline combining `hs_err`, manager signals, kernel logs | Both traces can appear in a single sequence |
| Is there enough evidence to change heap size? | Heap trend, GC/native memory, cgroup budget, OOM reason | Heap size does not fix every native/cgroup OOM |

**One artifact is never the whole story.** Strong evidence usually involves **two independent sources** describing the same PID/instance and timestamp: e.g., container `lastState` `OOMKilled` + kernel/cgroup `oom_kill` delta; or `hs_err` `SIGSEGV` + core dump/native frame from the exact same process.

## 11. Runbook for Investigating a Recently Disappeared Java Process

### Step 1 — Prove the process terminated, rather than merely hanging

Identify service instance, container ID, pod UID, PID, process start/end times, node, and UTC timestamps. An application failing to respond can be caused by deadlock, pool saturation, network partition, probe failure, or process death. Do not assume “crash” if the process is still alive.

If the process died and a supervisor restarted it, record the **old PID** and restart timestamp. Never use `jcmd`/heap data from the new PID to draw conclusions about the old PID's memory.

### Step 2 — Collect volatile clues before they vanish

Prioritize:
- Final app stderr/stdout and pre-restart logs; `logs --previous` where applicable.
- `hs_err`, heap dumps, and core dumps still on persistent volumes or working directories.
- Container last termination reason/`exitCode`/`finishedAt`; runtime/systemd/kubelet events.
- Kernel logs from the exact node and cgroup memory events / monitoring time series.
- Deployment/rollout/health probe/scale-down/eviction events.
- If the process is still alive yet reporting errors: JFR/GC logs/metrics, `jcmd`, or thread dumps per safety policy.

**Do not restart, rotate, or delete files and wipe evidence before saving if the system is safe to collect from.** During active incidents, restoring availability may take precedence; document evidence gaps if you cannot wait.

### Step 3 — Determine whether the JVM self-reported a fatal error

- Is there a matching `hs_err`? Read header/signal/problematic frame and JVM arguments.
- Is there a matching core dump? Collect metadata and native stacks per authorization.
- Was a fatal JVM error printed to stderr without writing a file?
- Do `ErrorFile` settings, disk path, ephemeral container FS, or permissions explain missing artifacts?
- If none exist: **do not jump to external kill yet**; move to inspecting OS/runtime evidence.

### Step 4 — Check signal/exit reason from supervisor sources

- Read the exit status and encoding: exited(code) or killed(signal)?
- If 137/9: identify who sent `SIGKILL`—OOM killer, liveness grace timeout, manual operator action, or userspace OOM daemon.
- If 143/15: check rollouts, stop commands, shutdown timeouts, and hook behavior.
- If 134/6, 139/11, or fatal `hs_err`: investigate native/JVM faults.
- If 1 or custom status: inspect Java exceptions, `System.exit`, and startup/launcher errors.

**Always ask:** does the status belong to the main Java process or only a shell/wrapper entrypoint? A wrapper can handle signals and exit codes differently from the JVM.

### Step 5 — Investigate memory along the exact boundaries

If OOM is suspected:
1. Identify pod/container/node memory limits and **pre-kill** memory time series.
2. Check kernel OOM lines and cgroup `oom_kill` deltas, ensuring the exact cgroup path.
3. Correlate Java heap usage/`-Xmx`, metaspace, direct memory, native `malloc`/NMT if enabled, thread counts/stacks, and page cache.
4. If a Java OOME occurred, read the **message** to identify the failing resource region; use a heap dump only if created and relevant to the error type.
5. Check total process/container RSS and any other processes in the cgroup.
6. Evaluate memory growth, traffic, batches, native libraries, deployments, and known memory budgets.

**Low `heap used` does not refute cgroup `OOMKilled`**; cgroup memory usage includes allocations the JVM does not manage directly plus caches. Nor should you raise `-Xmx` if the container memory limit is fixed and native headroom is already tight.

### Step 6 — Build a timeline and competing hypotheses

One timeline might look like this (hypothetical):

~~~text
14:10:00 Service A starts, pid=3210, Xmx=1GiB, memory.max=1.5GiB
14:10:05 Memory.current rises after a new batch begins
14:12:20 Memory.current approaches memory.max
14:12:21 Kernel records memcg OOM and victim pid=3210
14:12:21 Container lastState reason=OOMKilled, exit=137
14:12:25 New container starts with a new pid
~~~

Based on **kernel victim + container `OOMKilled` + exact cgroup and timeline**, the OS kill branch is strong. The absence of `hs_err` is consistent, though not the primary proof.

Another timeline:

~~~text
14:10:00 Java process pid=3210 starts
14:12:20 hs_err_pid3210.log begins, header SIGSEGV
14:12:20 Core dump process pid=3210 records SIGSEGV
14:12:21 Supervisor restarts service
~~~

The JVM/native fatal error branch is strong; do not infer a kernel OOM kill merely because the process vanished afterward.

### Step 7 — Assign confidence levels and decide actions

Use explicit labels:
- **Confirmed mechanism:** sufficiently strong sourced and timestamped evidence.
- **High likelihood:** sources align, though one key source is missing.
- **Insufficient evidence:** only an exit code, only a final log line, or only a post-restart graph.
- **Conflicting:** contradicting clues requiring checks of PID, clock, instance, or aggregation.

Act according to the mechanism: native crash → core/`hs_err`/JNI/JDK; Java OOME → heap/native root cause; OS `OOMKill` → cgroup budget/memory trend; liveness kill → probe/health/deadlock/queues/GC; controlled exit → app/supervisor logic. A change is considered successful only after verifying the same trace does not recur and SLOs plus memory/CPU guardrails hold.

## 12. Java 17+ Demo: Intentional Exit Paths, Not a JVM Crash

To study **what does or does not run shutdown hooks**, use a standalone Java program that consumes no extra memory, triggers no segmentation fault, and sends no signals to other processes. It demonstrates that a nonzero exit code **does not require an OS OOM killer**, and `Runtime.halt` can terminate **without running shutdown hooks** while still not being a HotSpot fatal crash.

Create **`TerminationModesDemo.java`**:

~~~java
public final class TerminationModesDemo {

    public static void main(String[] args) {
        String mode = args.length == 0 ? "normal" : args[0];

        Runtime.getRuntime().addShutdownHook(
                new Thread(
                        () -> System.out.println("HOOK: shutdown"),
                        "demo-shutdown-hook"));

        switch (mode) {
            case "normal" -> System.out.println("MODE: normal");
            case "exit" -> {
                System.out.println("MODE: exit");
                System.exit(7);
            }
            case "halt" -> {
                System.out.println("MODE: halt");
                System.out.flush();
                Runtime.getRuntime().halt(9);
            }
            case "throw" -> {
                System.out.println("MODE: throw");
                throw new IllegalStateException("demo-exception");
            }
            default -> System.out.println("MODE: unknown");
        }
    }
}
~~~

Compile with JDK 17+:

~~~bash
javac TerminationModesDemo.java
~~~

Run each mode one by one **in a lab shell**, never on a traffic-serving process:

~~~bash
java TerminationModesDemo normal
java TerminationModesDemo exit
java TerminationModesDemo halt
java TerminationModesDemo throw
~~~

In **normal** mode, stdout produced by the program:

~~~text
MODE: normal
HOOK: shutdown
~~~

In **exit** mode, stdout produced by the program:

~~~text
MODE: exit
HOOK: shutdown
~~~

Explanation by mode:

| Mode | Exit mechanism | Typical exit status | Shutdown hook | `hs_err` by default? |
| --- | --- | --- | --- | --- |
| normal | `main` completes, normal JVM shutdown | 0 | Yes | No |
| exit | `System.exit(7)` | 7 | Yes | No |
| halt | `Runtime.halt(9)`, immediate termination | 9 | No | No |
| throw | Uncaught `IllegalStateException` in `main`; JVM exits when no non-daemon threads remain | Usually nonzero | Yes, during normal JVM shutdown | No |

`halt` mode prints `"MODE: halt"` and flushes stdout before terminating; it does **not** print “HOOK: shutdown”. `throw` mode prints “MODE: throw”, followed by a stack trace on **stderr** with file-dependent line numbers; interleaving order between stdout and stderr is not guaranteed. This table describes typical HotSpot behavior for this example and does not replace measuring actual exit status in your shell.

An optional check on a Linux shell:

~~~bash
java TerminationModesDemo exit
printf 'exit status=%s\n' "$?"
~~~

The second shell line for this program is:

~~~text
exit status=7
~~~

Learning takeaways:
- Exit 7 came from **Java itself calling `System.exit`**, not an OS kill.
- Exit 9 came from **`Runtime.halt(9)`** in Java, not proof of `SIGKILL(9)`. **Exit code 9 differs from signal number 9.**
- A Java exception does not turn into a native `hs_err`.
- Missing the hook in `halt` mode illustrates why **missing shutdown logs do not prove `SIGKILL`**.
- If you change `exit` mode to `System.exit(137)`, the system can report exit code 137 **with no kernel OOM kill**—purely illustrating how ambiguous a bare exit code can be.

**Never run demos that trigger OOME, `SIGSEGV`, or `SIGKILL` in production.** The goal is to grasp exit-path semantics safely before analyzing real-world incidents.

## 13. Scenario A — OOME Appears Yet the Process Has Not Died

Example:
- An application thread logs `java.lang.OutOfMemoryError: Java heap space`.
- At the same time, there are no kernel OOM victim messages; `memory.events` `oom_kill` does not increment.
- The Java process still has the same PID and the health endpoint still responds in a degraded state.
- No `hs_err` exists, only the Java stack trace and a heap dump if the relevant flag was enabled.

**Interpretation:** There was a Java-level heap allocation failure; there is no evidence of a kernel kill. Inspect GC/heap live-set, allocations, and retention, and verify which thread died and whether the system truly recovered. The application remaining alive **does not** prove OOME is harmless: state may be corrupted or capacity degraded.

**Mistake:** filing a ticket as “OOMKilled” merely upon seeing the word `OutOfMemoryError`. The appropriate action is investigating heap/OOME and health status, not blindly editing cgroup limits.

## 14. Scenario B — Pod `OOMKilled` While Java Heap Still Has Headroom

Hypothetical example:
- Pod container memory limit is 2 GiB; `-Xmx` is 1 GiB.
- Pre-crash metrics show `heap used` around 700 MiB, yet container memory usage climbs near 2 GiB.
- Kernel logs show a memcg OOM victim matching the Java PID; cgroup `oom_kill` increments.
- Kubernetes `lastState` `reason=OOMKilled`, `exitCode=137`.
- No `hs_err` or Java `OutOfMemoryError` stack trace.

**Interpretation:** Kernel/cgroup kill has strong evidence. Causes may lie in native/direct buffers, metaspace, thread stacks, `malloc`/JNI, memory-mapped/file cache, or another process in the cgroup. Do **not** immediately **increase `-Xmx`** while the total limit stays fixed.

**Data to gather:** cgroup `memory.stat`, container working set/RSS trend, JVM Native Memory Tracking if **already enabled beforehand**, thread count, direct/mapped buffers, metaspace, native allocators, and batch/workload details. NMT does not cover all third-party native allocations or total page cache. If not enabled ahead of time, an NMT snapshot of the killed process cannot be reconstructed.

## 15. Scenario C — JVM Fatal Error in a Native Library

Example:
- `hs_err_pid5500.log` reports `SIGSEGV` and a problematic frame in a native library.
- A core dump with matching PID/timestamp records `SIGSEGV`.
- Container exit status is typically compatible with 139 if signal termination is surfaced per runtime convention.
- The kernel shows no OOM kill evidence; orchestrator reason may simply say `Error`.

**Interpretation:** A native/JVM fatal error is strongly supported; investigators should check JNI/agents/native libraries, memory access safety, versions/ABI, and JDK builds. If the fault is in `libjvm`, still inspect native code and extensions to distinguish a direct VM bug from earlier memory corruption.

**Do not conclude:** “Linux killed Java because it ran out of RAM” solely from a signal-related exit code. `SIGSEGV` and `SIGKILL` are two different mechanisms.

## 16. Scenario D — Liveness Probe Leads to `SIGKILL`, Not OOM

Hypothetical example:
- 09:00:00: consecutive liveness probes fail while the JVM is still running with a congested thread pool.
- 09:00:05: controller sends `SIGTERM`, starting the termination grace period.
- 09:00:35: process still has not exited; `SIGKILL` is sent.
- Container finally exits 137; reason is not `OOMKilled`.
- cgroup `oom_kill` does not increment and kernel logs show no OOM victim message.

**Interpretation:** Exit 137 matches `SIGKILL` from lifecycle shutdown escalation. The initial root cause could be deadlock, GC pause, health probe design, workload, network, or a native hang, requiring separate investigation. Raising the memory limit simply because you saw 137 is unfounded.

**Follow-up data:** `--previous` logs, kubelet events, probe timings, readiness vs. liveness, shutdown hook duration, thread dumps if captured prior to kill, and latency/CPU/GC/queue metrics before the failure.

## 17. Scenario E — JVM Writes `hs_err`, Then `systemd` Restarts It

Example:
- 11:02:10 HotSpot writes a fatal error log from the old PID.
- 11:02:11 process dies with a fault or abort signal.
- 11:02:12 `systemd` detects termination and restarts per `Restart=on-failure`.
- 11:02:13 a new PID appears, and the service responds normally.

**Interpretation:** `systemd` is the **restart agent**, not automatically the cause of the fatal error. Seeing “systemd started service” after a crash does not prove `systemd` killed the JVM beforehand. Inspect **logs immediately prior** to the restart and artifacts from the old PID.

Notably, healthy current status does not erase evidence of the old fault. Metrics from the new PID cannot substitute for memory/stack state when the old PID crashed.

## 18. Exceptions to Keep in Mind Before Finalizing Root Cause

### 18.1. Shell wrappers/entrypoints can transform exit codes

The container command may be a shell script or process supervisor rather than directly `exec`ing `java`. The status reported by the runtime may be the PID 1 wrapper's exit code while the Java child died via a different mechanism. Inspect the process tree, init/entrypoint behavior, signal forwarding, and wrapper logs. Never map a container exit code straight to a JVM signal unless you are certain Java was PID 1 or the status was passed through untouched.

### 18.2. Crash reports can be only partially written

Fatal signals, low disk, or low memory can truncate `hs_err` or a core. A file containing a header yet missing problematic frame/threads still has evidentiary value, though not enough to assign root cause. Do not delete a file just because a parser fails on it, and do not present an incomplete report as a full crash analysis.

### 18.3. `SIGTERM`/`SIGINT` and shutdown hooks have no guaranteed SLA

Even on a normal shutdown path, hooks can throw, hang, or hit the grace-period deadline. Hooks are started concurrently per JVM semantics; ordering across **multiple** hooks is not guaranteed. A “begin shutdown” log may exist while “end shutdown” is absent. Conversely, missing hook logs can be due to log buffering and are insufficient to prove `SIGKILL`.

### 18.4. The OS can raise a signal due to a native fault, not an intentional kill

`SIGSEGV`/`SIGBUS` triggered by a program fault is how the OS notifies the process of an error. The HotSpot fatal handler may write `hs_err`. When classifying, never use a loose phrase like “OS sent a signal” to blur the difference between **an in-process fault** and **an external kill for resource reclamation or administration**.

### 18.5. Java `OutOfMemoryError` and native allocation failures do not always take the same path

Some native memory allocation failures produce a fatal JVM error message, whereas some resource exhaustion conditions throw a Java OOME. The exact message and context determine the investigation path; seeing the word “memory” alone is not enough. When Java runs under container CPU/memory quotas, interactions can occur among automatic heap sizing, native allocations, and `memory.max`.

### 18.6. Core dumps, `hs_err`, and heap dumps answer different questions

| Artifact | What it records | When most useful | What it is not |
| --- | --- | --- | --- |
| `hs_err` | Snapshot of HotSpot fatal state: signal, threads, VM/native context | Native/JVM crash, fatal VM error | Not a Java heap dump |
| Core dump | Snapshot of process memory/registers at crash per OS/core policy | Native stack, library versions, memory corruption | Not guaranteed on `SIGKILL`/`OOMKilled` |
| Heap dump (`.hprof`) | Java heap object graph at capture time | Java heap leak/retention, certain OOMEs | Does not represent all native memory or signal cause |
| GC log / JFR | Recorded runtime timeline / GC / JIT / events | Pre-error history if data was flushed | Not a durable persistence system against `SIGKILL` |
| Kernel logs / cgroup counters | OS memory/signal/resource evidence | OOM victim / pressure / limits | Does not show which Java objects hold memory |
| Orchestrator status/events | Container lifecycle / reason / exit code | `OOMKilled`, `Evicted`, probes/rollouts | Does not analyze JNI/JVM root causes by itself |

A `.jfr` file from a continuous recording might not be dumped or flushed to an artifact before `SIGKILL`. **Setting `dumponexit=true` does not guarantee JFR survives `SIGKILL`.** To preserve pre-kill history, design out-of-process dumps/metrics with appropriate storage permissions and retention.

## 19. Pre-Incident Preparation: Enabling Investigability Instead of Waiting for a Crash

### 19.1. Startup flags weighed against risk

Examples intended only for compatible HotSpot/JDK builds and writable environments:

~~~bash
java \
  -XX:ErrorFile=/var/log/myapp/hs_err_pid%p.log \
  -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=/var/log/myapp \
  -Xlog:gc*:file=/var/log/myapp/gc.log:time,uptime,level,tags:filecount=5,filesize=50M \
  -jar app.jar
~~~

Notes:
- `/var/log/myapp` must exist and be writable from the target JVM's filesystem. In containers, verify volume mounts, ownership, and ephemeral storage.
- `%p` in HotSpot `ErrorFile` is replaced by the PID as supported by the flag; include instance-unique names in centralized storage to avoid collisions.
- Heap dumps can be huge, fill storage, and expose secrets. If the risk is unacceptable, do not enable them indiscriminately.
- GC log files rotate; size retention to cover enough pre-incident window without letting logs fill the disk.
- `HeapDumpOnOutOfMemoryError` **does not create crash artifacts on OS `SIGKILL`**. `ErrorFile` is for HotSpot fatal reports, not ordinary Java exceptions.

Never add `-XX:+CrashOnOutOfMemoryError` to “debug OOM” in production without an explicit policy and risk analysis; that flag changes the termination path itself and can make the application die immediately.

### 19.2. Out-of-process telemetry

To tell a JVM crash apart from an OS kill once the process has vanished, you need sources that do not die with the JVM:

- Container `lastState`/exit reason, restart counters, pod/container IDs.
- cgroup `memory.current`/`max`/`events`/pressure time series from an exporter/agent.
- Node kernel logs, kubelet/`systemd`/`systemd-oomd` logs, and event streams.
- JVM heap/non-heap/direct/thread/GC metrics exported to monitoring with instance labels.
- CPU throttling, native RSS, process memory, file descriptors, and container page cache.
- Deployment, rollout, termination, and liveness/readiness events.
- Centralized stdout/stderr, fatal error logs, or an artifact collector stored outside ephemeral filesystems.

Crucially, metrics need **timestamps, process/container identity, and high enough sampling frequency**. A “5-minute average memory” chart can easily miss a brief spike right before an OOM kill.

### 19.3. Native Memory Tracking and postmortem tools

If native memory pressure is anticipated, consider enabling NMT at startup with appropriate JVM flags, then querying `jcmd VM.native_memory` while the process is alive; this feature has overhead and does not cover all allocations outside HotSpot. Once the process receives `SIGKILL`, `jcmd` can no longer attach. **Without a pre-crash NMT snapshot, you cannot reconstruct it from the new PID.**

For native crashes: core dumps, symbols, loaded libraries, `hs_err`, and JVM/JNI agent versions aid investigation. Never attempt to pull massive cores or run debuggers on production without authorization and security controls.

## 20. Writing Reports That Stay Within the Evidence

A good report always separates **observed facts** from **hypotheses**. Examples:

**Insufficient evidence:**
> Container exited with code 137 at 15:04 UTC. Neither `lastState` reason nor kernel/cgroup logs are available yet; cannot conclude `OOMKilled`. Need runtime termination reason, probe/rollout events, and memory events for the exact cgroup.

**Strong basis for OS OOM kill:**
> Container X reported `lastState` `reason=OOMKilled`, `exitCode=137` at 15:04 UTC; kernel logs confirm the memcg OOM victim was Java PID 3451 in the same cgroup and `memory.events` `oom_kill` incremented. Termination mechanism is confirmed as a kernel memory cgroup OOM kill. The specific driver of memory growth still requires investigating heap/native/cache/workload.

**Strong basis for JVM/native fatal error:**
> `hs_err_pid3451.log` shows a fatal `SIGSEGV` header and problematic frame in `libnative.so`, matching the PID/timestamp of the core dump. This is a JVM/native fatal crash; `libnative.so` is not yet proved to be the original root cause if earlier memory corruption occurred. No OOM killer evidence appears in the inspected window.

**Do not write:**
> “Exit 137 => Java ran out of heap; increase `-Xmx`.”

This statement conflates **termination status**, **memory source**, and **remediation**. Increasing heap under a fixed container limit can even shrink native headroom and make `OOMKill` happen more often.

## 21. Concise Runbook Upon Receiving a “JVM Died” Alert

~~~text
[1] Did the process actually die?
    |-- No: investigate hang / unresponsiveness / dependencies first
    '-- Yes: record PID/containerID/podUID/node/start-end UTC
          |
          v
[2] Is there an hs_err matching the PID/timestamp?
    |-- Yes: investigate JVM/native fatal error + core/agents/JDK
    '-- No or incomplete: do not conclude yet; gather OS evidence
          |
          v
[3] Was exit normal, explicit code, or signal?
    |-- custom exit code: check Java exception / System.exit / wrapper
    |-- SIGTERM: check deploy / probe / service manager / stop
    |-- SIGKILL: check kernel OOM, cgroup, controller grace, operator
    '-- SIGSEGV/SIGABRT/SIGBUS: check native/JVM fault/core
          |
          v
[4] OOM evidence?
    |-- reason OOMKilled + matching kernel/cgroup/time:
    |      confirm kernel/cgroup kill, find memory source
    |-- Java OutOfMemoryError with no OS kill:
    |      investigate JVM exception / resource region
    '-- Only exit 137:
           insufficient; collect runtime/kubelet/kernel records
          |
          v
[5] Correlate evidence, counter-evidence, scope, and decide fix
~~~

The flow above is a reasoning guide, **not a rigid sequence**. If the orchestrator clearly shows `OOMKilled`, grab kernel/cgroup logs immediately before retention expires, then return to `hs_err`/Java logs. If `hs_err` exists yet the kernel also OOM-killed later, build a timeline to see which happened first and which PID was killed.

## 22. Investigation and Handover Checklist

- [ ] Confirmed the process actually terminated, not just that the app hung.
- [ ] Identified the exact PID, instance, container ID/pod UID, node, start/end times, and JVM version.
- [ ] Distinguished Java exceptions/OOME, `System.exit`, `Runtime.halt`, JVM fatal errors, `SIGTERM`/`SIGKILL`, and the OOM killer.
- [ ] Searched for `hs_err` and checked paths/permissions/timestamps; did not infer “missing file = OS kill.”
- [ ] If `hs_err` exists, read fatal header, signal, problematic frame, native/JVM frames, and VM arguments.
- [ ] Pulled process/container status, not just a bare exit code.
- [ ] For 137, sought `SIGKILL` evidence plus sender/reason; did not assume `OOMKilled` automatically.
- [ ] For `OOMKilled`, collected properly scoped kernel/cgroup memory events and memory trends.
- [ ] Did not confuse Java heap `OutOfMemoryError` with container `OOMKilled`; checked native/direct/cache/thread memory.
- [ ] Checked probes, rollouts, grace periods, watchdogs, `systemd-oomd`, and node eviction.
- [ ] Distinguished core dumps, heap dumps, `hs_err`, JFR/GC logs, and kernel evidence.
- [ ] Did not use a new PID or post-restart memory snapshot as evidence for the old process.
- [ ] Aligned timestamps in UTC, accounting for clock skew and log retention.
- [ ] Formulated at least one competing hypothesis and a check that could falsify the primary hypothesis.
- [ ] Protected sensitive data in `hs_err`/core/heap dumps with retention, deletion, and access policies.
- [ ] Conclusion states **termination mechanism**, **root-cause hypothesis**, **confidence level**, and **next measurements**.

## 23. Conclusion

The most critical distinction:

**The JVM self-reporting a fatal error** means the VM's reporting mechanism had a chance to run and could write **`hs_err`** (usually with signal/native/VM context). **The OS or orchestrator terminating the process** may use `SIGTERM`/`SIGKILL`; with `SIGKILL`, the JVM has no time to run shutdown hooks or produce normal diagnostic artifacts.

In practice there are more branches: Java exceptions, `OutOfMemoryError`, `System.exit`, `Runtime.halt`, native `SIGSEGV`, kernel/cgroup OOM kills, `systemd-oomd`, kubelet evictions, liveness restarts, and wrapper exit statuses. Therefore, never turn a single clue (exit 137, missing `hs_err`, one OOME line, or a pod restart) into the entire conclusion.

A sound investigation follows this chain:

**Verify process/instance → collect `hs_err`/Java logs → correlate exit/signal/reason → read kernel/cgroup/orchestrator timeline → separate termination mechanism from root cause → apply a verified fix.**

### References

- Oracle JDK 21, Java launcher/HotSpot flags (`-XX:ErrorFile`, `HeapDumpOnOutOfMemoryError`...): https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- Oracle JDK 21, `jcmd` (VM flags, JFR, native memory commands when supported): https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle Java 21, Troubleshooting Guide: https://docs.oracle.com/en/java/javase/21/troubleshoot/
- Linux kernel cgroup v2 (`memory.events`, `memory.events.local`, `memory.max`): https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html
- Linux `signal(7)`: https://man7.org/linux/man-pages/man7/signal.7.html
- Kubernetes, Node-pressure eviction: https://kubernetes.io/docs/concepts/scheduling-eviction/node-pressure-eviction/
- Kubernetes, Debug Running Pods: https://kubernetes.io/docs/tasks/debug/debug-application/debug-running-pod/
