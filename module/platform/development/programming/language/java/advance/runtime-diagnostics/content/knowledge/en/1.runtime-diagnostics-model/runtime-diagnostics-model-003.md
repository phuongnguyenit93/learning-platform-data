# 1.3. Distinguishing Functional Failures, Latency, Throughput, Hangs, Memory Exhaustion, and JVM Crashes

When a Java service "is not working properly," that description is not enough for diagnostics. A wrong response, a slow request, a system processing too little work, a stuck thread, an out-of-memory JVM, and a process hitting a native fault are different phenomena. They can occur simultaneously, yet must be **classified by evidence** before searching for root causes.

**Objective:** from observations with clear timestamps and scope, recognize the incident category, choose initial measurements and evidence, and avoid concluding from a single signal. This lesson builds the classification model; it does not replace deep-dive investigation workflows for deadlocks, GC, heap dumps, or native crashes.

## 1. Ask the Right Questions Before Choosing Tools

Identify the **affected unit** (one request, a group of requests, one thread, the entire process, a pod/container, or the whole cluster), the **time window** (start/end, before/after changes), and the **expectation** (business result, SLO, processing rate, task progress). The same indicator means different things at different scopes.

| Symptom Group | Decisive Question | First Identifying Evidence | Do Not Jump to Conclude |
| --- | --- | --- | --- |
| **Functional failure** | Do the output and data state match the specification? | Input, expected/actual output, violated invariants, exceptions/traces | HTTP 200 is always right; HTTP 500 is always a business-logic bug |
| **Latency degradation** | How long does a single unit of work take to complete? | End-to-end and per-step duration, p50/p95/p99 by endpoint | A good average means good tail latency |
| **Throughput degradation** | How many units of work complete per unit time, under what incoming load? | Arrivals/s, completions/s, success/s, queue depth, saturation | Low requests/s is automatically an incident when demand itself is low |
| **Hang/stall** | Is the process alive yet failing abnormally to make progress? | Heartbeats/progress markers, wait duration, consecutive thread dumps | One thread in WAITING/BLOCKED proves a JVM deadlock |
| **Memory exhaustion/pressure** | Is heap, non-heap, native memory, or a container limit being exhausted? | OOME type, heap/GC, RSS, native allocations, cgroup OOM events | High heap used equals a memory leak |
| **JVM crash** (fatal VM/native failure) | Did the JVM terminate abnormally due to a fatal VM/native code error? | Fatal error log, `hs_err_pid*.log`, signals such as SIGSEGV, core dump | Every process death is a JVM crash |

An incident may carry **multiple symptom labels**: for example, prolonged GC causes higher latency and lower throughput; an exhausted thread pool causes requests to stall; memory exhaustion can lead to process exit. Record all of them, then separate **measured symptoms**, **causal mechanisms**, and **root causes**. Call it a "crash" only when evidence matches that termination mode.

## 2. Deep Identification of Each Group

### 2.1. Functional Failure: "What Did It Return?"

Functional failures occur when observed behavior violates the contract: wrong monetary calculation, returning another owner's data, saving invalid state, losing events, violating idempotency rules, or throwing an exception instead of returning a promised result. A request can return **200 OK while being business-wrong**; conversely, a 4xx response may strictly honor the contract.

How to verify: capture minimal reproducible input, dependency states, expected/actual values, request ID/trace ID, build version, and execution path; check against tests, specifications, or invariants. If error rates spike concurrently with timeouts, OOMEs, or crashes, look for the **operational cause** behind the errors instead of automatically assuming the algorithm is wrong.

### 2.2. Latency: "How Long Does It Take to Complete?"

Latency is the time from start to finish of **one execution**. Always state whether it is measured at the client, gateway, or inside the JVM; client latency may also include DNS, network, TLS, retries, and queueing. Per-segment timings (queue wait, DB, locks, GC pauses, application processing) help localize cost. A request timeout is usually the **result of exceeding a deadline**, not yet the cause.

Use p50/p95/p99 percentiles together with sample count, time window, endpoint/request type, and success vs. error status. Averages can hide distribution tails; do not add p95 values of individual steps to estimate end-to-end p95. Percentiles over 10 requests only illustrate the calculation and are not representative of a production system.

### 2.3. Throughput: "How Much Work Is Processed?"

Throughput is the number of **completed units of work** per unit time: requests/s, transactions/s, messages/s. Distinguish:
- **Arrival/offered load:** work entering the system per second.
- **Completion throughput:** completed work (including successes/failures if the counter defines it so).
- **Successful throughput:** successful work per second.
- **Concurrency/queue:** work currently running or waiting, not throughput.

For example, over 30 seconds, 240 jobs arrive, 180 complete, and 165 succeed: arrival = 8/s, completion = 6/s, success = 5.5/s. Assuming no drops/cancellations and consistent counting, net backlog increases by 60. When load increases while completion throughput stalls and queues plus latency grow, suspect **bottleneck/saturation** (CPU, pools, locks, I/O, DB, rate limits). If requests/s is low simply because there are no users, it cannot be called capacity degradation.

In steady state with consistent measurement conditions and scope, Little's Law gives the average relation **L = λ × W** (items in system = completion rate × residence time). It is a sanity check on measurements, not self-sufficient proof of cause.

### 2.4. Hang: "Alive, Yet Making Progress?"

An **alive** JVM can still fail to process work: lock deadlocks, I/O waits without timeouts, infinite waits on Futures/conditions, exhausted pools, all workers held, livelocks, or CPU loops making no progress. Sometimes only **one request** is stuck while the system serves other requests; state the scope accurately.

Better evidence than a single thread state is: no new completions/heartbeats across multiple expected intervals, and consecutive thread dumps or JFR recordings showing the same wait chains/locks/call paths. Threads in `WAITING`, `TIMED_WAITING`, or `BLOCKED` can be completely normal (e.g., idle pool workers waiting for tasks). `RUNNABLE` also does not guarantee progress; it could be spinning or blocked in native I/O. Detect Java monitor deadlocks with thread dumps or `ThreadMXBean.findDeadlockedThreads()`, but not all hangs are deadlocks.

Distinguish **very slow** from **no progress** using deadlines, completed-work counts over time, and repeated observations. Do not declare "JVM hung" from a single HTTP timeout.

### 2.5. Memory Exhaustion: "Which Type of Memory Ran Out?"

In Java 17+, running out of memory does not only mean Java heap. Read the **exact message** and observe actual limits:

| Signal | Investigation Direction |
| --- | --- |
| `OutOfMemoryError: Java heap space` | Live objects, retention, post-GC heap usage, heap size; distinguish heavy load from leaks |
| `OutOfMemoryError: GC overhead limit exceeded` | GC running too frequently while reclaiming little; inspect GC logs/heap and allocation pressure |
| `OutOfMemoryError: Metaspace` | Class metadata, class loaders, and class generation/loading |
| `OutOfMemoryError: Direct buffer memory` | Direct buffer limits and lifecycles, off-heap memory |
| `OutOfMemoryError: unable to create native thread` | Thread limits, native memory, pid/OS limits; do not conclude the heap is full |
| Container/pod reports **OOMKilled** | Kernel/cgroup killed the process upon exceeding the memory limit; there may be no Java OOME or `hs_err` |

Track heap **used/committed/max**, GC pause/frequency, RSS, and cgroup limits. RSS can rise due to native buffers, threads, mmap, metaspace, or libc even when heap does not grow. A nearly full heap before GC does not by itself prove a leak; observe the **live set after GC cycles** and correlate with load. `OutOfMemoryError` also does not necessarily cause the **entire JVM** to exit immediately: it depends on the thread, handlers, and resource shortfall.

### 2.6. JVM Crash: "Why Did the Process Terminate?"

A JVM crash in the strict sense occurs when VM/native code encounters a **fatal error**, such as SIGSEGV/SIGBUS on Unix or EXCEPTION_ACCESS_VIOLATION on Windows, potentially producing `hs_err_pid*.log` and a core dump. Possible sources include JNI/JNA/native libraries, unsafe memory operations, JIT/VM/JDK bugs, or hardware faults; a **fatal log is evidence for analysis**, not proof that the bug lies in the JVM vendor's code.

Separate crashes from:
- `System.exit(...)`, self-initiated shutdown, or service manager stop requests.
- Uncaught exceptions on the main thread or startup failures causing process exit without a VM fatal error.
- `SIGTERM` during redeployment, or `SIGKILL`/exit 137 from administration or the OOM killer (confirm via OS/container events).
- Host restarts, container evictions, or health-check kills/restarts.

If the process is already dead, live `jcmd`/thread dumps are no longer usable; prioritize final logs, exit reason, container events, crash artifacts, timestamps, and versions. On Linux, exit 139 may suggest SIGSEGV; **an exit code alone is insufficient** to distinguish a crash from other causes.

## 3. Diagnostic Decision Tree

Start from the **strongest evidence at the exact time of the incident**, not from the ticket title.

1. **Is the Java process still alive?** If **no**, collect exit code/reason, logs right before termination, OS/container events, and check for `hs_err_pid*.log`/core dumps. Verified fatal error → **JVM crash** branch. `OOMKilled` → **OS/container memory limit exhaustion** branch. Intentional exit/redeployment → process stop state, do not automatically classify as a crash.
2. **If alive, is the system making progress?** Check completion counters, queue depth, heartbeats, and multiple thread dumps when needed. No progress beyond a reasonable deadline → record **hang/stall**, then distinguish deadlock, I/O wait, pool exhaustion, livelock, or long GC. If progress continues, do not label it a system-wide hang.
3. **Is there evidence of memory pressure or OOME?** Match the exact OOME message against heap, non-heap, native, GC, and RSS/cgroup. Record **memory exhaustion** when substantiated; it can simultaneously make requests slow or hang.
4. **Do results violate the contract?** Based on expected/actual and invariants, label failing requests/flows as **functional failure**, even if the process and performance metrics look normal.
5. **For work that still completes, measure latency and throughput separately.** Compare p95/p99, arrival/s, completion/s, and success/s with baseline under the **same workload type and window**. Bad latency with stable completion/s → primarily latency degradation; completion/s hitting a ceiling under rising load → primarily throughput capacity; both bad → possibly a shared bottleneck.
6. **Assemble timeline and causal hypotheses.** Example: rising allocation → rising GC pauses → rising latency → growing queues → falling throughput. Time-series data is required to support this chain; co-moving variables do not by themselves prove causation.

Classification outcomes should follow the pattern: **"Target + time + phenomenon + magnitude + evidence + unknowns."** Example: "Service A, 10:02–10:07, p99 rose from 150 ms to 2.4 s, completions/s held at ~90, many requests waiting on DB; end-to-end slowdown confirmed, DB cause under investigation."

## 4. Minimum Evidence on Java 17+

Collect from least invasive to more intensive; preserve timestamps, timezone, hostname/pod, PID, JDK vendor/version, build, CPU/memory limits, load volume, error logs, and request/trace IDs. Prioritize comparing **during the incident** with a recent prior baseline.

**If the JVM is alive and attachable**, run the following commands on a host/container that has the JDK and access permissions to that process. Replace 12345 with the real PID; do not run from a machine that cannot see the PID namespace.

~~~bash
jcmd 12345 VM.version
jcmd 12345 Thread.print -l
jcmd 12345 GC.heap_info
jcmd 12345 JFR.start name=triage settings=profile duration=60s filename=triage.jfr
~~~

- **Thread dump:** captures lock ownership, thread states, stacks, and pool counts; compare at least two points in time to observe progress/changes and avoid mistaking idle workers for a deadlock. Attach may fail if the JVM is unresponsive or permissions differ.
- **Heap/GC:** `GC.heap_info` is a snapshot, not a substitute for retention analysis. GC logs/JFR help correlate pauses or allocations with tail latency. Taking a heap dump can consume time, memory, and disk space; perform only deliberately.
- **JFR:** uses execution samples, allocations, GC, and thread/lock events depending on configuration to guide investigation; the output file needs a writable path and sufficient disk space. Profiling also adds overhead, so weigh production conditions.
- **If already exited:** collect final stderr/stdout, `hs_err`, core dump if present, exit code, OS/kernel/cgroup events, and restart reason; `jcmd` can no longer attach to the old process.

Tracing collection can be configured at **application startup** (illustrative example, requiring a writable directory and enough space):

~~~bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags \
  -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=./dumps \
  -XX:ErrorFile=./hs_err_pid%p.log -jar app.jar
~~~

The command assumes `app.jar` and the `./dumps` directory exist. Heap dumps, JFR files, and crash dumps may contain sensitive application data: restrict read/retention permissions and do not attach them publicly. Options must be enabled before an incident to capture artifacts in time; configure alerts/disk quotas appropriately to avoid filling the disk.

## 5. Java Example: Separating Three Rates and One Percentile

The Java 17+ program below calculates metrics from **hypothetical data for a 30-second window**. This is a measurement example, not a root-cause classifier. Ten latency samples only illustrate how to compute nearest-rank p95; real statistics require representative sample sizes and per-endpoint grouping.

~~~java
import java.util.Arrays;
import java.util.Locale;

public class DiagnoseWindow {
    public static void main(String[] args) {
        long arrivals = 240;
        long completions = 180;
        long successes = 165;
        double seconds = 30.0;
        long[] latencyMs = {40, 45, 50, 55, 60, 70, 90, 110, 150, 1200};

        Arrays.sort(latencyMs);
        int rank = (int) Math.ceil(0.95 * latencyMs.length);
        long p95 = latencyMs[rank - 1];

        System.out.printf(Locale.ROOT,
                "incoming=%.1f/s, completed=%.1f/s, success=%.1f/s%n",
                arrivals / seconds, completions / seconds, successes / seconds);
        System.out.printf(Locale.ROOT,
                "p95(sample)=%d ms, backlog change=%d%n",
                p95, arrivals - completions);
    }
}
~~~

Save as **DiagnoseWindow.java** and run:

~~~bash
javac DiagnoseWindow.java
java DiagnoseWindow
~~~

Exact stdout:

~~~text
incoming=8.0/s, completed=6.0/s, success=5.5/s
p95(sample)=1200 ms, backlog change=60
~~~

**How to read it:** requests arrive faster than they complete (8 vs. 6/s); with no drops/cancellations in this example, unfinished work increases by 60. Completion throughput and successful throughput differ. A high sample p95 indicates tail latency, **and does not by itself prove the cause is deadlock, GC, or memory exhaustion**. To conclude saturation, you need time-series data across load levels, queues, resource utilization, and dependency health. Do not compare p95 across different request types or incompatible windows.

## 6. Six Easily Confused Scenarios

**A — Wrong result, yet fast:** API returns 200 in 20 ms with an incorrectly updated balance; CPU, GC, and requests/s are normal. **Classification:** functional failure. Action needed: reproduce with input, check transactions/invariants, and fix logic; do not start with a heap dump.

**B — Tail latency rises while completion rate holds:** 90 requests/s stays steady, but p99 increases from 150 ms → 2.4 s; traces show DB queries taking longer. **Classification:** latency degradation (suspected DB/queue), insufficient evidence of throughput degradation. Measure with the same endpoint, load level, and percentile.

**C — Hitting a throughput ceiling:** load sends 400 requests/s, but only 150/s complete; queues grow, deadlines are breached, CPU or pools reach limits. **Classification:** throughput bottleneck accompanied by latency and timeouts. Increasing timeouts will not increase serving capacity; verify where saturation occurs.

**D — Alive with no progress:** PID exists, TCP health endpoint is open, completion counter stays flat longer than the deadline; two consecutive thread dumps show a lock cycle or all workers waiting on an unresponsive dependency. **Classification:** hang/stall within the proven scope. `WAITING` on one idle worker alone is not enough to conclude this.

**E — OOME vs. OOMKilled:** logs show `java.lang.OutOfMemoryError: Java heap space` → Java heap exhaustion requiring live-object/GC analysis; whereas a pod reports `OOMKilled` with no Java OOME → OS/cgroup killed it for memory limit. **Both belong to the memory branch**, but the mechanism and investigative evidence differ. Do not label a pod OOMKilled as a "JVM native crash."

**F — VM fatal error vs. normal shutdown:** stderr shows "A fatal error has been detected by the Java Runtime Environment", `SIGSEGV`, and a path `hs_err_pid12345.log` → grounds for a JVM/native crash; whereas an orchestration system sending SIGTERM and the service exiting per lifecycle → intentional stop. Analyze `hs_err` along with version/JNI/native stacks before blaming the JDK.

## 7. False Inferences to Avoid

- **An HTTP 500 = functional failure.** HTTP status only reflects the request outcome; the root cause could be connection exhaustion, timeouts, OOME, or logic.
- **Latency increase = throughput drop.** A system can maintain completions/s while tail percentiles degrade; or throughput may be low simply due to lack of load.
- **One request timeout = JVM hang.** It can stem from network, dependencies, queues, retries, or client deadlines. Check progress and scope.
- **Thread in BLOCKED/WAITING = deadlock.** You need lock relationships and persistence across multiple samples, not a single state.
- **High heap = leak.** The heap may hold valid live data or spike temporarily; inspect GC, retention, workload, and limits.
- **OOME = JVM crashed.** OOME is a Java error; the process can remain alive. OOMKilled is an OS kill; a native fatal error is a different category.
- **Missing PID = JVM crash.** Identify the exit reason first: deployment, stop, signal, cgroup, or fatal error.
- **Optimize before measuring.** Keep a timeline and baseline, and check recent changes; otherwise it is easy to "fix" the wrong symptom or destroy evidence.

## 8. Checklist When Recording Conclusions

Before moving the investigation to root cause, the record must answer: **(1)** what scope and since when; **(2)** whether the process is alive or exited, with evidence of the exit reason; **(3)** what correctness, latency percentiles, arrival/completion/success throughput, and progress look like; **(4)** whether OOME/GC/RSS/cgroup or thread/lock evidence exists; **(5)** primary/secondary symptom labels with testable next hypotheses; **(6)** what data is still missing to avoid overclaiming.

**Practical rule:** first distinguish **wrong output – slow per item – few items completed – no progress – memory exhaustion – fatal VM/native failure**, then use independent metrics and logs to substantiate and separate symptoms from causes.