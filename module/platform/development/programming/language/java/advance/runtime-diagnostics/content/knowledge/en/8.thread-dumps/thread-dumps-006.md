# 8.6 Capturing multiple spaced thread dumps to establish progress

> **Java Advance – runtime-diagnostics** · **8. Thread dumps**

## 1. Why take multiple snapshots instead of just one?

A single **thread dump** shows where Java threads are on their call stacks, what states they are in, and — depending on the tool/JVM — which locks they hold or wait on **at the moment of collection**. It is very useful for forming hypotheses about blocked requests, contention, deadlocks, or non-progressing thread pools. However, a single snapshot cannot tell you how long a thread has been waiting, whether it just completed a task, or whether the observed state is merely normal idle rest.

**Capturing multiple spaced thread dumps** lets you compare points in time to observe **signs of progress** (*progress*): threads changing stacks/states; lock owners changing; requests/tasks completing; queues shrinking; counters rising; or conversely, many workers continuing to wait on the same resource while the system completes no additional work.

Crucially: **multiple snapshots are point-in-time evidence, not a continuous movie**. Even with the exact same stack across three captures, a thread could have left that stack, completed work, and returned between captures. Conversely, a thread constantly changing frames yet completing zero requests could be in a *livelock*, retry loop, or futile work.

### Learning objectives

After this lesson, you should be able to:

1. Design a thread dump sampling run with **sample count, interval, capture timing, and impact limits** appropriate to the symptom.
2. Capture snapshots of **the exact JVM instance**, recording process identity, UTC timestamps, commands, errors, and file paths.
3. Compare thread identities, states, stack signatures, monitor/lock owners, and appearances/disappearances **within proper scope**.
4. Distinguish **real business progress** from “seeing a thread move”, “seeing the same stack”, or “state changed”.
5. Combine thread dumps with **completed-task/request counters, queue depth, traces, logs, OS CPU, JFR, and GC logs** to increase confidence.
6. Know what **cannot** be inferred, even from multiple discrete dumps.
7. Practice a Java 17+ example proving **two snapshots both showing WAITING while a task completed in between**.
8. Write incident conclusions following **observation → hypothesis → verification → limitations**, without confusing correlation with causation.

## 2. Three layers of “progress” to distinguish

The word *progress* sounds simple, yet in Java systems there are at least three distinct layers.

| Layer | Sign | Why thread dumps alone are insufficient |
| --- | --- | --- |
| **Thread-level** | Frame/state/owner changes; thread exits a wait site | Thread may simply have woken up and slept again, or looped back |
| **Task/request-level** | A task completes, request gets a response, span finishes, queue shrinks | Dumps do not inherently contain task IDs, request IDs, or completion counters |
| **Service-level** | Throughput rises, backlog shrinks, errors/latency recover | Requires time-series metrics from the right instance/load |

**Example:** a worker is at *LinkedBlockingQueue.take()* in two snapshots 5 seconds apart. That could mean:

- The worker was **idle** the whole interval because there were no tasks.
- The worker **processed a task** between the two snapshots and returned to *take()*.
- The worker received no work due to a producer/dispatcher malfunction.
- The worker is blocked on the wrong queue due to misconfigured data routing.

If you only read two snapshots showing the same *WAITING* and the same stack, **all four possibilities remain open**. You need *submitted counts, completed counts, queue depth, application logs*, or traces to distinguish them.

An accurate technical phrasing is:

> “At both sampling timestamps, thread X was observed waiting at queue.take(). There is not yet enough data to tell whether it processed tasks in between.”

Avoid writing:

> “Thread X was stuck for 5 seconds because both dumps showed WAITING.”

## 3. When should you take multiple samples?

Taking multiple dumps is useful when a symptom **persists long enough to observe**:

- HTTP requests are waiting for a very long time while the process remains alive.
- A thread pool has a backlog, throughput drops, and workers appear not to drain it.
- Many threads contend for a monitor or wait on one lock owner.
- CPU rises persistently, requiring stack comparison and per-thread CPU correlation.
- The service still accepts requests without completing work.
- *Deadlock*, *livelock*, starvation, or repeated retry/parking is suspected.
- The system slows down intermittently, and captures can be triggered actively in the right window.

**When it is not suitable:** an incident lasted only 50 ms and you started capturing 30 seconds later; the snapshots may look completely normal. For brief events, JFR, traces, logging, or metrics/histograms already enabled before the incident are usually more useful.

### 3.1 Sample count and interval are operational decisions

A common initial run is **3–5 snapshots spaced a few seconds apart**, such as 3 snapshots spaced roughly **5 seconds after the previous command completes**, when this fits the symptom duration and actual cost. This is only an **example** — there is no mandatory JVM rule saying “take exactly three dumps exactly five seconds apart”.

Choose the interval based on the **hypothesis**:

| Symptom | Suggested window | Notes |
| --- | --- | --- |
| Thread pool hung for minutes | Several snapshots a few seconds apart | Enough to see repetition, though it still does not measure exact state duration |
| Lock contention lasting a few hundred ms | Manual thread dumps may miss it | Prefer JFR monitor contention events and metrics |
| Sustained high CPU for tens of seconds | Multiple timestamped snapshots plus per-thread CPU deltas | Dumps only suggest frames; they are not a CPU profiler |
| Sporadic timeouts a few times per hour | Controlled triggers or continuous event telemetry | Random post-event sampling rarely aligns |
| Very many threads/virtual threads | Lower frequency; choose appropriate tools | Large files, high overhead, changing coverage |

**Waiting 5 seconds after the previous dump finishes does not mean the two snapshots' timestamps are exactly 5 seconds apart.** If each dump takes 1.2 seconds to collect, the time between the *start* of snapshot 1 and snapshot 2 is roughly 6.2 seconds. Record **capture start/end**; if steady cadence is needed, design a scheduler with overhead monitoring and never run concurrent dumps against the same JVM.

### 3.2 Pre-define stop conditions

To keep collection controlled, define:

- **Maximum sample count** (e.g., three snapshots in the first pass).
- **Total investigation window** and cooldown interval.
- Resource/disk/log impact thresholds that require stopping.
- **Responsible owner** and storage location.
- **Companion data** to collect concurrently (latency/queue/CPU/errors).
- Handling when the PID disappears, attach fails, or the process restarts.

Do not run a `while true; jcmd Thread.print` loop in production. Diagnostic tools also consume CPU/I/O, can alter scheduling, and affect the very symptom you want to measure.

## 4. Preflight: ensure all snapshots belong to the **same JVM**

A series of multiple files can only be compared meaningfully if you know **which process each file measured**.

### 4.1 Identifiers to record

- Service, application version, deployment/commit version.
- Host/container/pod and **pod UID** if on Kubernetes.
- JVM process ID in **the namespace where the tool runs**.
- VM vendor/build/version, JVM start time or uptime (to detect restarts).
- **UTC start and end timestamps** of each capture.
- Capture command, tool/JDK version, options.
- Filename, file size, **capture success/failure status**.
- Incident/load context at capture time, if available.
- Coverage: platform threads vs. virtual threads, whether locks/ownable synchronizers are included.

**PID is not enough.** A process can restart and the OS can reuse the PID. Two JVMs in two different pods can both show PID 1 **inside their containers**. Nor does an ObjectName or thread name substitute for process identity.

If *JVM start time* changes between two captures, those are **two distinct JVM instances**. Do not infer a new thread “progressed” simply because its thread name matches one from the previous JVM. A restart also resets counters like GC count, process CPU time, and many thread IDs.

### 4.2 jcmd attach prerequisites

On HotSpot, *jcmd* typically needs to run on the **same machine** as the JVM, with appropriate OS permissions (same effective user/group on Unix per documentation), matching PID namespace/attach mechanism, and compatible JDK tools. In containers, *jcmd -l* does not always list JVMs in other Docker namespaces; verify PIDs using authoritative process discovery in that environment.

Start against the target JVM:

~~~bash
java -version
jcmd -l
jcmd 12345 help Thread.print
~~~

*12345* is an **example PID** and must be replaced with a verified JVM PID; never run against an arbitrary PID. *jcmd -l* is only a listing aid, not proof that “no JVM exists” if results are missing.

If the tool fails to attach, **do not** arbitrarily escalate container privileges, change system directory permissions, open unsecured JMX, or disable security controls just to take a dump. Use an approved collection path via the operator/platform team.

## 5. Capturing three dumps with jcmd: a timestamped workflow

On a supporting HotSpot JVM, a single platform-thread stack capture with ownable synchronizer information can use:

~~~bash
jcmd 12345 Thread.print -l
~~~

Depending on version, *-e* is also available for extended thread information. Check **help from the target JVM**, because flags, output, and virtual-thread coverage can vary between releases:

~~~bash
jcmd 12345 help Thread.print
~~~

Oracle documentation rates *Thread.print* as **impact medium**, depending on thread count. Therefore the example below **takes at most three captures**, and does not self-detect-and-remediate or loop indefinitely.

### 5.1 Bash example (Linux/macOS when jcmd is available)

This is an **illustrative** standalone script; run only in authorized environments, substituting the PID and choosing a safe output directory first:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

PID=12345
OUT_DIR="./thread-dumps-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p -- "$OUT_DIR"

for i in 1 2 3; do
  started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  file="$(printf '%s/thread-%02d.txt' "$OUT_DIR" "$i")"

  if jcmd "$PID" Thread.print -l > "$file"; then
    finished="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'sample=%s start=%s end=%s status=ok file=%s\n' \
      "$i" "$started" "$finished" "$file" >> "$OUT_DIR/manifest.txt"
  else
    finished="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'sample=%s start=%s end=%s status=failed file=%s\n' \
      "$i" "$started" "$finished" "$file" >> "$OUT_DIR/manifest.txt"
    exit 1
  fi

  if [ "$i" -lt 3 ]; then
    sleep 5
  fi
done
~~~

**How to interpret the result:**

- Three files are created, numbered by sample index. *manifest.txt* records UTC **start/end** and the outcome of each run. You can append instance ID, JVM start time, and service version from external orchestration outside the script.
- *sleep 5* runs **after** the dump command returns, so it is not exactly five seconds between every snapshot timestamp.
- Redirection *>* writes stdout of the **jcmd client** to the file. It does **not** instruct the target JVM to write files to the JVM process's filesystem.
- If *jcmd* returns an error, the script stops. An empty/partial file upon error **is not proof of zero threads**.
- If the JVM restarts, the script might still hit a new/different PID; **the manifest must be checked against process identity** before diffing.
- Recorded timestamps only have **second** resolution in the example; when finer resolution is needed and supported by the OS, use timestamps with fractional seconds. Do not claim microsecond timing from this script.
- The command can fail if run from another host/pod, without a JDK, or with insufficient attach permissions. Do not use its failure to guess a deadlock cause.

### 5.2 PowerShell example (Windows)

In PowerShell, **$PID** is an automatic variable holding the current PowerShell PID. Never assign *$PID = 12345*; use another variable name such as *$targetPid*.

~~~powershell
$ErrorActionPreference = "Stop"
$targetPid = 12345
$out = Join-Path (Get-Location) (
    "thread-dumps-" + (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
)
New-Item -ItemType Directory -Path $out -ErrorAction Stop | Out-Null

for ($i = 1; $i -le 3; $i++) {
    $started = (Get-Date).ToUniversalTime().ToString("o")
    $file = Join-Path $out ("thread-{0:D2}.txt" -f $i)

    & jcmd.exe $targetPid Thread.print -l |
        Out-File -FilePath $file -Encoding UTF8 -Width 32767
    $exitCode = $LASTEXITCODE
    $finished = (Get-Date).ToUniversalTime().ToString("o")

    "sample=$i start=$started end=$finished exit=$exitCode file=$file" |
        Add-Content -Path (Join-Path $out "manifest.txt") -Encoding UTF8

    if ($exitCode -ne 0) {
        throw "jcmd failed for sample $i with exit code $exitCode"
    }
    if ($i -lt 3) {
        Start-Sleep -Seconds 5
    }
}
~~~

PowerShell *Out-File* can add a BOM or re-encode text; the file itself is a **text diagnostic capture** and must not be claimed as a byte-for-byte stream from the JVM without checking encoding. Use an appropriate encoding/collector when automated parsing is required. Redirection and stderr errors must also be checked separately; exit code 0 does not replace verifying the file actually holds a dump from the intended JVM.

### 5.3 When snapshots are very large

Each dump can be megabytes or more on JVMs with many threads. Reading/writing it all in a terminal, shipping via a collector, or copying files can incur overhead. Limit sample count, file size, storage permissions, and retention TTL, and avoid pasting raw production data into public tools. Do not take dumps in a tight loop trying to catch a brief glitch; JFR/metrics may be more appropriate.

## 6. Comparing multiple dumps: match the right thread before diffing

A common mistake is using *thread name* as a unique key. However, pool worker names can repeat after restarts, threads can be renamed, or multiple threads can share identical names. Some dumps print *tid*, *nid*, Java ID, and stack frames; these IDs **do not share the same meaning**.

### 6.1 Order of identity matching

1. **Same JVM instance:** process start time + host/pod UID + PID within the capture namespace.
2. **Same thread within that instance:** Java thread ID if accurately provided by the output, or native ID *nid* when encoding/OS namespace are certain; account for thread lifecycle/ID reuse.
3. **Thread name:** hints at role, but **must not** be used alone to join samples.
4. **Stack + pool metadata:** helps detect recreated workers or identical names on different code paths.
5. **Application correlation:** requestId/taskId/traceId if available from logs/tracing (not inherently inside thread dumps).

In some HotSpot *Thread.print* outputs:
- *nid=0x...* is the native thread ID as represented by the tool; convert hex/decimal and match the right OS thread when using OS metrics.
- *tid=0x...* is an internal identifier/address and should not automatically be treated as *Thread.getId()*.
- *#n* in the header is not a request number.
- The JVM main PID differs from individual native thread IDs.

Do not turn *Thread A no longer appears in dump 2* into “A completed successfully”. It may have terminated with an error, been replaced, fallen outside snapshot coverage, or the JVM may have restarted.

### 6.2 Only diff after normalizing metadata and filtering noise

Between two raw files, many things change that **do not reflect business progress**:

- Timestamps and VM uptime in headers.
- Cumulative process/thread CPU time.
- Counters, allocator addresses, JIT frame details.
- Thread ordering in the file, and lock object addresses if not from the same process.
- GC/JIT helper threads, schedulers, and logging collectors.
- During capture, the diagnostic/tool thread itself may appear.

**Do not delete all dynamic fields.** CPU deltas, owners, native IDs, and timestamps can be critical evidence. Keep **the original raw file** and create a separate annotated normalized extract; explicitly document which fields were stripped. Never simply run *diff -u* on two files and treat differing line counts as a progress metric.

## 7. Comparison table model per capture

A good analysis table includes not only state; it also captures wait site, owner, stack signature, counters, and confidence statements.

| UTC/sample | JVM/thread identity | State | Stack/wait site | Lock/owner | Progress counter/metric | Snapshot-level conclusion |
| --- | --- | --- | --- | --- | --- | --- |
| 10:00:00 / A | JVM-1 / worker-7 | WAITING | queue.take | — | completed=100 | Waiting for task at A |
| 10:00:06 / B | JVM-1 / worker-7 | WAITING | queue.take | — | completed=121 | Service had completions between A–B, **does not prove worker-7 did them** |
| 10:00:12 / C | JVM-1 / worker-7 | WAITING | queue.take | — | completed=140 | Waiting for task at C; overall service still progressing |

**Important note:** if *completed* in the table is a **service-wide counter**, it does not prove **worker-7** handled 21 tasks. It only proves **the service or group covered by that counter** made progress. To claim worker-7 progressed, you need per-thread/per-task evidence, such as a worker-specific counter in a lab, trace mapping, or reliable task completion logs.

For lock contention:

| Sample | Thread | State | Waiting on | Owner | Interpretation |
| --- | --- | --- | --- | --- | --- |
| A | request-12 | BLOCKED | monitor X | worker-3 | Contending for X at A |
| B | request-12 | BLOCKED | monitor X | worker-3 | Seen waiting on X again at B |
| C | request-12 | RUNNABLE | method after critical section | — | Evidence thread changed position/state at C |

**Do not say “request-12 waited on X continuously for 10 seconds” merely because BLOCKED appeared at A and B.** Between the two snapshots the thread could have entered the lock and returned to contend for it again. To measure true duration, prefer JFR monitor enter events or controlled contention timing.

### 7.1 What is a stack signature?

A **stack signature** is a normalized summary of key frames — typically the top N frames, application methods, wait site, and lock/condition type — for comparing multiple samples. Example:

~~~text
request-12
  com.example.Inventory.reserve(...)
  com.example.Checkout.placeOrder(...)
  waiting monitor X; owner=worker-3
~~~

The goal is to group threads **exhibiting the same symptom pattern**, not to prove they are handling the same request. Avoid lumping every stack containing *Unsafe.park* into one bucket: *park* is a low-level primitive; look at the frames below it such as *LinkedBlockingQueue.take*, *CompletableFuture.get*, or *ReentrantLock.lock*.

### 7.2 Supplemental progress table

Maintain a second table showing progress signals **outside the dumps**:

| Timestamp | Submitted tasks | Completed tasks | In-flight | Queue depth | Error rate | p99 latency |
| --- | --- | --- | --- | --- | --- | --- |
| A | 1,000 | 980 | 20 | 5 | 1% | 400 ms |
| B | 1,100 | 985 | 115 | 90 | 8% | 2,000 ms |
| C | 1,200 | 987 | 213 | 170 | 12% | 4,000 ms |

The numbers above are **illustrative only**, not production data. When *submitted* rises rapidly while *completed* barely moves, *queue depth* climbs, and request workers are observed waiting on the same resource across multiple snapshots, the lack-of-progress hypothesis has **much stronger evidence**. However, counters must belong to the same instance/group, not reset, and have matching semantics; during autoscale/restarts, never mechanically subtract raw fleet-wide totals.

## 8. Repeating patterns that must be interpreted differently

### 8.1 Same WAITING + same queue, yet completion counter rises

This can be a **healthy worker** repeatedly picking up work and returning to wait for tasks. Multiple snapshots showing *queue.take()* may simply occur because the worker spends most of its time idle between short tasks.

**Conclusion:** insufficient evidence that the thread is stuck. Per-worker progress is needed if you truly want to evaluate that specific thread.

### 8.2 Same BLOCKED + same monitor + same owner across multiple snapshots

This is a **high-priority contention sign**. Still, ask what the owner is doing: holding the monitor during long I/O, stuck on another lock, or delayed by OS scheduling? Inspect the lock owner's stack and telemetry during that window.

**Accurate conclusion:** “At the captured timestamps, multiple request threads were waiting on monitor X held by worker Y.” You still do not know **continuous wait duration** or root cause without JFR/lock timings and request correlation.

### 8.3 Same WAITING at Future.get or CountDownLatch.await

This can be legitimate when awaiting an asynchronous task result. It can also be **starvation** if the task needed to complete was submitted to the very same busy thread pool that is waiting. Understand the task dependency graph, queue depth, and executor completion; a dump alone does not know which task completes that future.

### 8.4 Same RUNNABLE with compute top frames across multiple samples

This may suggest a CPU hotspot or tight loop, but **RUNNABLE does not equal CPU%**. A thread in native I/O can also appear RUNNABLE. Use **per-thread CPU deltas** with the right native ID and JFR/profiler in the same window; avoid concluding “method is burning CPU” from two stack frames.

### 8.5 Stacks/locks changing constantly yet zero completions

This may be a **livelock** or retry loop. Threads are “active” at the CPU level while the system makes no business progress. Inspect business progress counters, retry counts, errors, and state transitions. **State changes show execution**, not necessarily useful progress.

### 8.6 Thread disappears from a later dump

This can happen due to completion, uncaught exception, thread pool shrinking, thread renaming, JVM restart, or different tool coverage. Check application completion/event logs, lifecycle metadata, and instance identity; never write “thread fixed” automatically.

### 8.7 Idle pool while backlog grows

Some workers are WAITING at *BlockingQueue.take()* while the dashboard queue depth climbs. Before concluding the queue is broken, verify **exact queue instance/endpoint**, same pod, same timestamp, and metrics semantics. The producer might be writing to a different queue or the dashboard might measure the whole fleet while the dump covers one pod.

### 8.8 Deadlock detector reports no deadlock

Seeing no **Java-level deadlock** in a dump does not rule out starvation, database/distributed deadlocks, livelocks, socket waits, or deadlocks outside the detector's scope. Multiple dumps likewise do not prove full coverage of every synchronization mechanism.

## 9. Java 17+ Lab: WAITING twice while work completed in between

The hands-on exercise below is a **standalone Java 17+ program** simulating a thread receiving a task and returning to wait for the next task. Main captures **two ThreadInfo snapshots** via *ThreadMXBean*. A second thread simply waits on a latch for comparison.

This is not *jcmd* generating a full thread dump file; it uses **the same Java management observation foundation** to demonstrate the argument “snapshots A/B showing the same state do not prove lack of progress”.

Controlled experiment setup:

1. *progress-worker* waits at *BlockingQueue.take()* at a single call-site.
2. *idle-worker* waits at *CountDownLatch.await()*.
3. At snapshot A, both have state **WAITING**, completed=0.
4. Main puts a task into the queue; the worker takes it, increments the counter, and signals completion.
5. The worker returns to **the exact same take() statement** to wait for a second task.
6. At snapshot B, both are **WAITING** again, yet completed=1.
7. *finally* wakes/interrupts and joins to avoid leaving dangling threads.

Create file **RepeatedThreadDumpDemo.java**:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class RepeatedThreadDumpDemo {
    private static final BlockingQueue<Integer> TASKS = new LinkedBlockingQueue<>();
    private static final CountDownLatch DONE_SIGNAL = new CountDownLatch(1);
    private static final CountDownLatch RELEASE_IDLE = new CountDownLatch(1);
    private static final AtomicInteger COMPLETED = new AtomicInteger();

    public static void main(String[] args) throws Exception {
        Thread worker = new Thread(() -> {
            try {
                for (int cycle = 0; cycle < 2; cycle++) {
                    TASKS.take(); // Same call-site in both snapshots.
                    if (cycle == 0) {
                        COMPLETED.incrementAndGet();
                        DONE_SIGNAL.countDown();
                    }
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "progress-worker");

        Thread idle = new Thread(() -> {
            try {
                RELEASE_IDLE.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "idle-worker");

        try {
            worker.start();
            idle.start();
            awaitState(worker, Thread.State.WAITING);
            awaitState(idle, Thread.State.WAITING);

            ThreadMXBean mx = ManagementFactory.getThreadMXBean();
            printSample("A", mx, worker, idle);

            TASKS.put(1);
            if (!DONE_SIGNAL.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not finish task");
            }
            awaitState(worker, Thread.State.WAITING);
            printSample("B", mx, worker, idle);
        } finally {
            RELEASE_IDLE.countDown();
            worker.interrupt();
            worker.join(2_000);
            idle.join(2_000);
        }
    }

    private static void printSample(String label, ThreadMXBean mx,
                                    Thread worker, Thread idle) {
        long[] ids = {worker.getId(), idle.getId()};
        ThreadInfo[] infos = mx.getThreadInfo(ids, 8);
        if (infos[0] == null || infos[1] == null) {
            throw new IllegalStateException("Thread ended before snapshot");
        }
        System.out.println(label + ".workerState=" + infos[0].getThreadState());
        System.out.println(label + ".idleState=" + infos[1].getThreadState());
        System.out.println(label + ".completed=" + COMPLETED.get());
    }

    private static void awaitState(Thread thread, Thread.State desired)
            throws InterruptedException {
        for (int attempt = 0; attempt < 200; attempt++) {
            if (thread.getState() == desired) {
                return;
            }
            Thread.sleep(10);
        }
        throw new IllegalStateException("Expected " + desired
                + ", observed " + thread.getState());
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 RepeatedThreadDumpDemo.java
java RepeatedThreadDumpDemo
~~~

**Six lines of program stdout tested on JDK:**

~~~text
A.workerState=WAITING
A.idleState=WAITING
A.completed=0
B.workerState=WAITING
B.idleState=WAITING
B.completed=1
~~~

*javac* on some newer JDKs may print **a separate warning** that *Thread.getId()* is deprecated; that is not program stdout, and the code uses APIs available on Java 17. This lab uses **platform threads**, not virtual threads. Latch synchronization + bounded-loop state checking reduce scheduler sensitivity, though under extreme overload *awaitState* could still time out and throw rather than printing the six lines.

### 9.1 What conclusions are certain from the lab?

At A: progress-worker is waiting for a task and completed=0. After A, main has proof via *DONE_SIGNAL* that the worker processed a task and incremented its own counter. At B, the worker has returned to **WAITING at the same take() call-site**, yet counter=1.

Because the counter is tied to **that exact worker**, this proves it **made progress between the two captures**. The stack frame at B did not need to differ from A. This is an intentional counterexample to the inference “two identical stacks/states = the thread made no progress”.

Conversely, *idle-worker* is WAITING at both A and B because it awaits the latch; yet **you cannot conclude an error** — main releases the latch in finally. Steady waiting can be the intended design.

### 9.2 How should this be combined with app metrics?

In real systems, you rarely have a clean per-worker counter like the lab. Instead:

- **Service-wide completed counter rises:** proves some tasks in the service completed, not specifically worker X.
- **Queue depth drops:** may be due to consumer processing, or a producer/policy purging tasks; combine with completed/failed metrics.
- **Request spans finish:** evidence of request-level progress if tracing is complete and sampling did not drop them.
- **Worker-specific logs/context:** can indicate tasks handled by worker X, though check thread reuse and correlation.
- **OS per-thread CPU delta:** shows CPU activity, which does not by itself prove business progress.

Separate the identity layer from the progress layer before drawing conclusions.

## 10. Comparing snapshots on a timeline instead of reading file by file

A persuasive workflow builds a **timeline**:

~~~text
10:00:00  Incident: p99 latency increased, completed/s dropped
10:00:02  Dump A: 20 request workers BLOCKED waiting on monitor X
10:00:04  Metrics: queue length increased; throughput near 0
10:00:08  Dump B: many workers still waiting on X, owner stack at DB call
10:00:11  Traces: downstream DB wait increased, same window
10:00:14  Dump C: owner moved past that code section; BLOCKED worker count dropped
10:00:16  Metrics: completed/s recovered
~~~

The timestamps and data above are a **hypothetical scenario**. Appropriate conclusion: lock X and its owner have a time correlation worth investigating with the incident; request workers were observed waiting on X at A/B; metrics and traces provide service-level progress evidence. You cannot yet claim lock X is **definitely** the root cause without critical-section code details, load variation checks, competing causes, and verification checks.

### 10.1 An eight-step analysis workflow

1. **Define the symptom and time window.** Select service, route, pod, error rate, latency, throughput, queue depth, and incident timestamps.
2. **Frame the capture target.** Process instance, VM version, PID namespace, permissions, tool, and expected virtual-thread coverage.
3. **Capture the minimum needed.** For example, three intentionally spaced snapshots with start/end timestamps, limiting impact.
4. **Validate the files.** jcmd exit codes, presence of headers/stacks/threads, same JVM; never analyze empty files from failed attaches.
5. **Match threads across snapshots.** Same JVM/thread identity; classify pools, request workers, schedulers, GC/JIT/helpers.
6. **Group stack/lock signatures.** Wait sites, lock owners/owner stacks, whether they share a pool/queue/call path; record per-snapshot states.
7. **Correlate external progress.** Completed counters, queues, request spans, JFR, CPU deltas, GC pauses; ensure same instance and timestamps.
8. **Write conclusions with confidence levels, limitations, and next validation steps.** Never turn correlation into an unsubstantiated causal claim.

If after step 4 you discover the JVM restarted, **split into two separate series** and do not diff thread IDs as if they were one process. If after step 7 service progress is clearly occurring, revise the stuck hypothesis even if one thread group's stacks/states look repetitive.

## 11. Limits even when you have 3, 5, or 10 dumps

### 11.1 Cannot measure exact wait duration

Seeing thread X *BLOCKED* at t0 and t10 **does not** prove X waited continuously for 10 seconds. It could have released and reacquired the lock multiple times between snapshots. The t0–t10 span is only an **observation interval**, not a dwell-time measurement. You need JFR monitor events or supported contention timing enabled under control.

### 11.2 Cannot prove lack of progress from identical stacks alone

A thread can return to the same call-site each time it picks up a task. The lab proved this. Concluding “no progress” requires an observable **completion metric or business state transition** over time within the same scope.

### 11.3 Cannot prove a CPU hotspot from a few RUNNABLE stacks

A RUNNABLE thread may not yet be scheduled by the OS or may be in a native call. CPU time is a cumulative measurement; to find CPU load, compute **deltas for the same thread over the same interval**. Manually counting top-frame occurrences across three snapshots is not equivalent to a statistically sampled CPU profiler.

### 11.4 Does not provide request latency distribution

Thread dumps do not provide all request durations to compute p95/p99. You need metrics/tracing with appropriate samples/windows and business semantics. A group of threads waiting across 5 seconds **does not** mean p99 = 5 seconds.

### 11.5 Does not automatically detect all deadlocks/livelocks

In-JVM detectors cover a specific set of locks. Waiting across networks, DB transactions, distributed locks, queues, futures, thread pool starvation, or non-progressing retry loops may not create a Java-level monitor deadlock. Not seeing “Found deadlock” is insufficient to rule these out.

### 11.6 No guarantee of an atomic snapshot across all tools

A dump takes time to execute, so output may not represent a single nanosecond. Virtual-thread-specific formats on newer JDKs have different coverage and consistency guarantees. Taking multiple dumps does not cure this; record tool/version/capture window.

### 11.7 Does not necessarily show every virtual thread

On Java 21+, virtual threads are managed by the JVM and do not map 1:1 to OS native threads. Traditional tools/dump formats may only cover platform threads and currently mounted virtual threads. *ThreadMXBean* in the Java Management API also has a different scope from dedicated virtual-thread dump tools.

For JDK 21, Oracle documentation describes *Thread.dump_to_file* producing text/JSON files containing platform and virtual threads, without all the object addresses/lock/JNI/heap metadata of traditional dumps. Check *jcmd PID help Thread.dump_to_file* on **the exact JDK build**; syntax and capabilities vary by version. Never directly compare virtual thread counts between two files from **different tools/coverage** and call it progress.

### 11.8 Does not prove a vanished thread succeeded

A thread could terminate from an uncaught exception, be replaced by a thread pool, or end due to a JVM restart; its absence in a new file cannot determine outcome. Check error/completion logs, task IDs, active/in-flight counters, and lifecycle events.

## 12. Virtual threads and multi-sample strategies on JDK 21+

Applications using virtual threads require a different sampling design than traditional platform-thread pools.

On Oracle JDK 21, reference syntax example:

~~~bash
jcmd 12345 help Thread.dump_to_file
jcmd 12345 Thread.dump_to_file -format=json threads-01.json
~~~

*threads-01.json* is a path created by the command in **the target JVM's filesystem**, which may differ from where the `jcmd` terminal runs. Avoid overwriting older files; sample-indexed/timestamped naming and protective permissions should be planned ahead. JSON format suits parsers and supports observing virtual threads in this version, but must not be assumed to include deadlock detection or all lock internals.

**When comparing virtual threads:**

- Record whether *Thread.dump_to_file* or *Thread.print* was used, JDK version, and content scope.
- Check which identities actually exist in that format and their stability across samples.
- Do not treat carrier OS threads as persistent identities of virtual threads; virtual threads mount/unmount.
- Use trace/task IDs, scheduler/queue metrics, and JFR events to distinguish “many WAITING virtual threads” from genuine lack of task completion.
- Avoid dumping millions of virtual threads too frequently: file/processing overhead and security exposure can be significant.
- On JDKs other than 21, **read the VM's help** rather than blindly copying *-format=json* or command names.

If a program uses virtual threads and three platform-thread dumps show no request workers, that **does not prove requests do not exist**. You may have used a tool with the wrong coverage.

## 13. Correlating with CPU, GC, queues, and application data for true progress

### 13.1 OS thread CPU deltas

If a dump records native thread *nid*, you can correlate OS per-thread CPU metrics — after verifying **nid/PID namespace and no restart**. A positive CPU delta shows the thread consumed CPU during the interval; it does not necessarily mean it completed a business task.

To avoid unit errors:

\[
\text{Average CPU cores} \approx \frac{\Delta \text{thread CPU seconds}}
{\Delta \text{wall seconds}}
\]

A thread cannot run on multiple cores simultaneously under the standard native thread model; a value computed from a single native thread is typically in 0–1 core when data is valid. Process CPU deltas can exceed 1 core across multiple threads. Do not confuse cumulative CPU seconds with instantaneous CPU%.

**Trap:** hex *nid* from HotSpot cannot be string-matched directly against decimal TIDs in OS tools; convert properly and verify host/namespace.

### 13.2 Queue metrics and thread pool metrics

For ExecutorService/ThreadPoolExecutor, track:
- Active worker count.
- Queue depth.
- Submitted/completed task counts (matching the executor's semantics).
- Rejection count.
- Time in queue and execution duration if instrumented.
- Task error/timeout rate.
- Nested tasks depending on the same pool.

A pool with 100 WAITING workers and queue depth=0 may be completely healthy. Conversely, active=100, rising queue depth, and completed/s≈0 across multiple timestamps is a sign worth investigating; inspect what workers are waiting on and why producers keep pushing work.

### 13.3 App logs/tracing

In a Java service, a request can cross multiple threads (async continuations, executor handoffs, virtual threads). **Thread name is not request identity**. To link dumps to symptoms:
- Include secure traceId/requestId in logs/spans.
- Record task start/end and dependency calls.
- Inspect retry loops, timeouts, circuit breakers, and queue waits.
- Separate actual event time from collector-assigned timestamps.
- Check whether sampling/truncation dropped some events.

### 13.4 GC logs and JFR

During GC pauses/safepoints, dump capture can be affected in timing and how the JVM produces the snapshot. If throughput stalls alongside prolonged GC pauses, GC Unified Logging and JFR provide better event/duration detail than discrete thread dumps.

JFR recordings include events for monitor enter, thread park, execution sampling, and CPU allocation/GC depending on JDK and configuration. Do not equate “JFR is recording” with “every useful event is enabled and captured”; configuration and sampling windows determine evidence quality.

## 14. Real-world diagnostic scenarios

### 14.1 HTTP thread pool appears “frozen”

**Observation:**
- Dumps A/B/C: most request workers are WAITING at *CompletableFuture.get()*.
- Metrics on the same pod: submitted increases, completed barely moves, queue is growing.
- Logs: many requests await results of tasks submitted to **the very same pool whose workers are already waiting**.

**Strong hypothesis:** thread pool starvation due to nested blocking dependencies. Not concluded from dumps alone; metrics and the task dependency graph supply the decisive evidence. Inspect executor topology, synchronous waits, and whether any task can actually complete.

**Do not:** restart repeatedly without saving evidence, or blindly increase pool size without understanding nested dependencies.

### 14.2 Many threads contending for a monitor

**Observation:** 12 request workers BLOCKED at *Inventory.reserve*, all waiting on monitor X across two snapshots. Owner Y has its stack in a network call; throughput drops.

**Hypothesis:** a synchronized block holds the monitor while waiting on downstream I/O, causing a lock convoy. Verify using critical section code, JFR monitor enter durations, downstream traces, and additional samples if needed.

**Limitation:** you cannot claim each worker was continuously BLOCKED between the two snapshots; the owner could have changed at uncaptured moments.

### 14.3 CPU 250%, RUNNABLE stack repeats at JSON parser

**Observation:** one thread is RUNNABLE in a JSON parser across multiple files; process CPU is high.

**Must not conclude:** the JSON parser is definitely burning 250% CPU. A single native thread normally cannot consume 2.5 cores at once. Map native thread IDs, capture per-thread CPU deltas, and gather execution samples via JFR/profiler. Other threads (GC/JIT/native) may account for most of the CPU.

### 14.4 Identical WAITING yet request throughput keeps rising

**Observation:** three dumps all show worker-7 at *LinkedBlockingQueue.take()*; completed request count on the same service climbs steadily.

**Appropriate conclusion:** the service is progressing; there is no evidence worker-7 is stuck. If knowing whether worker-7 itself completed tasks matters, use per-worker context or traces; service-wide counters only indicate service-level progress.

### 14.5 Tasks retry continuously, completions equal 0

**Observation:** stacks flip continuously between retry/future/HTTP calls, CPU shows activity, completed counter does not increase, error count is high.

**Hypothesis:** livelock/retry amplification or dependency failure. Check request/task outcomes, retry policies, and dependency traces. Simply seeing threads change states is not business progress.

### 14.6 Thread “vanishes” after deploy restart

**Observation:** dump A in pod X, dump B in a new pod of the same logical workload; thread name *worker-1* appears in both, yet PID/start time differ.

**Conclusion:** two process instances; you cannot diff identity/CPU/stacks as one thread. Split the incident into before/after restart, and inspect shutdown/recovery logs and counter resets.

### 14.7 Virtual-thread app has thousands of WAITING requests

**Observation:** platform Thread.print shows a few dozen carrier/OS threads, yet app metrics report thousands of in-flight requests.

**Do not conclude:** the JVM lacks threads/requests. The tool may not list unmounted virtual threads; use virtual-thread-aware dumps/JFR and task/request progress data. “Many WAITING virtual threads” can also be normal if waiting on I/O; measure timeouts/latency to evaluate.

## 15. Common mistakes when collecting and comparing multiple dumps

| Mistake | Why it is wrong | Fix |
| --- | --- | --- |
| Two snapshots both WAITING ⇒ thread stuck | Worker may have processed work between snapshots | Pair with completion/task counters |
| Same stack ⇒ time in frame equals interval between dumps | Thread may have exited and returned | Use timing/JFR; state only “observed at both timestamps” |
| Frame changed ⇒ request finished | Could be a retry loop/livelock | Check business completion |
| Joining only by thread name | Names can duplicate/be reused | Match JVM instance + thread identity |
| Assuming PIDs are never reused | Restarts/OS PID reuse can happen | Record JVM start time/pod UID |
| Counting diff lines to measure progress | Timestamps/addresses/order change | Semantic diff: state/stack/lock/counter |
| Dump missing thread ⇒ thread never existed | Thread may have ended or tool coverage differs | Check lifecycle/format/virtual threads |
| Captures “exactly 5s apart” just because of sleep 5 | Dump execution takes time itself | Log start/end timestamps |
| One dump failed yet file exists ⇒ valid snapshot | Redirection can create an empty/partial file | Verify exit code and file contents |
| Repeated RUNNABLE ⇒ guaranteed CPU hotspot | May be native I/O or OS wait | Per-thread CPU delta/JFR |
| No GC pause visible ⇒ unrelated to GC | Thread dump is not a GC event log | GC logging/JFR and timestamps |
| No deadlock found ⇒ no starvation | Detector is limited to certain lock/cycle types | Queue/progress/dependency analysis |
| All WAITING ⇒ service dead | Workers may be normally idle | Throughput, incoming load, and queue metrics |
| Completed counter rose ⇒ thread X worked | Counter may be service-wide | Per-thread/task correlation |
| Putting files from two JVMs into one table | Different processes do not share thread identities | Separate instances before comparing |
| Every snapshot is an atomic snapshot | Tool/VM may capture over a duration | Record capture window/coverage |
| Taking 100 dumps every 100 ms | Overhead/I/O can worsen the incident | Cap samples, use dedicated telemetry |
| Publicly uploading raw thread dumps | Easily leaks class paths, internals, identifiers | Access controls, redaction, and retention |

## 16. Exercises with answers

### Exercise 1 — WAITING twice

A at 10:00:00 and B at 10:00:05: worker-1 is WAITING at *queue.take()* in both. That specific worker's completed tasks increased 10 → 11.

**Question:** Is there progress?

**Answer:** There is evidence **worker-1 completed at least one task between the two samples**, even though its state/stack at both timestamps are identical. It must not be called stuck from the two snapshots alone.

### Exercise 2 — No per-worker counter

Both snapshots show worker-1 WAITING; total service completed rose 300 → 350.

**Question:** Can you assert worker-1 handled 50 requests?

**Answer:** No. A service-wide counter only proves the measured service or instance group completed work. Concluding about worker-1 specifically requires task-level correlation.

### Exercise 3 — BLOCKED twice

Thread A is BLOCKED on monitor X at t0 and t10, with the same lock owner B.

**Question:** Did A wait continuously for 10 seconds?

**Answer:** Insufficient evidence. A may have entered the lock and returned to wait between snapshots. We only know A was observed BLOCKED at both timestamps. Timing/monitor events are needed to measure duration.

### Exercise 4 — Constantly changing stack

A thread transitions through *send → timeout → retry → send* across multiple samples, while successful requests equal 0.

**Question:** Is there progress?

**Answer:** There is thread-level activity, **no business progress**. This may be retry amplification/livelock; check dependency traces/error metrics and retry budgets.

### Exercise 5 — Same thread name after restart

Both files contain *pool-1-thread-1*, yet B's JVM start time is 2 minutes after A's.

**Question:** Can the two threads be compared as one thread?

**Answer:** No. Different process instances; thread names can be reassigned. Split the timeline and inspect shutdown/startup evidence.

### Exercise 6 — Script sleep 5

A script runs *jcmd Thread.print* taking 1.8 seconds, then *sleep 5*.

**Question:** Is the interval between the start of two captures exactly 5 seconds?

**Answer:** No. The interval is roughly 6.8 seconds excluding other overhead; actual timestamps are required to know precisely.

### Exercise 7 — Very high CPU

The process uses an average of 300% CPU; one RUNNABLE thread on a parser appears across three snapshots.

**Question:** Can all 300% be attributed to that thread?

**Answer:** No. You need per-native-thread CPU deltas, `nid` mapping, and a profiler. One thread may be only part of the issue.

### Exercise 8 — Deadlock conclusion

Three snapshots show many threads WAITING at Future.get, yet the Java-level detector finds no deadlock.

**Question:** Can starvation due to tasks waiting on each other be ruled out?

**Answer:** No. Future/task dependencies do not necessarily form a monitor deadlock detectable by the detector. You need executor graphs and task progress metrics.

### Exercise 9 — Empty dump file

Capture B produces *thread-02.txt* of 0 bytes, with *jcmd* exit code 1.

**Question:** Can you say “at B there were no live threads left”?

**Answer:** No. This is a collection failure. Record status failed, check attach/PID/permissions, and do not use B as a valid snapshot.

### Exercise 10 — Virtual threads

A JDK 21 service has 50,000 virtual threads waiting on network; a platform-thread dump tool sees only 80 platform threads.

**Question:** Have all requests been observed?

**Answer:** Not yet. Verify coverage and use virtual-thread-aware dumps/JFR/traces. Counting carrier threads does not represent the number of virtual threads/tasks.

### Exercise 11 — Queue grows, workers wait for tasks

Metrics report rising queue backlog while a pod's dump shows workers WAITING at queue.take().

**Question:** Is the queue definitely broken?

**Answer:** Not yet. Verify the metric and dump belong to **the same pod/queue instance**, same timestamp, and executor topology; a fleet-wide queue can differ from a local queue.

### Exercise 12 — Owner changes

A: thread W1 is BLOCKED waiting on monitor X held by W2. B: W1 is RUNNABLE, and W2 is no longer in the dump.

**Question:** Is it certain W2 finished resolving all issues?

**Answer:** No. There is evidence W1 was no longer observed BLOCKED at B, but no W2 completion outcome or business progress. W2 may have finished normally, failed, or vanished due to process/coverage differences.

### Exercise 13 — Confidence level

Four snapshots over 20 seconds consistently observe 15 request workers BLOCKED on the same monitor X; queue grows, completed/s is near 0, and JFR shows monitor wait durations rising in the same window.

**Question:** State an appropriate conclusion.

**Answer:** There is **strong evidence** for lock contention associated with reduced progress, especially as JFR measures durations and metrics align. You still need to inspect the owner's code path and relationship to requests to establish exact root cause.

### Exercise 14 — Thread vanishes

A worker is RUNNABLE at A, absent at B; completed metrics do not increase, and error logs show an uncaught exception from that worker.

**Question:** Can this be called “successful progress”?

**Answer:** No. Lifecycle evidence suggests the worker terminated with an error. “No longer in the dump” does not equate to success.

## 17. Operational checklist and report template

### 17.1 Before capturing

- [ ] Identify the **specific symptom** and occurrence window.
- [ ] Verify the exact service, JVM instance, PID namespace, and start time/pod UID.
- [ ] Check tool/version and attach permissions; run *help* on the actual command.
- [ ] Choose sample count, interval, and resource/disk limits.
- [ ] Define file storage location, access permissions, and TTL/retention.
- [ ] Prepare companion metrics/logs/traces to correlate.

### 17.2 During capture

- [ ] Record **UTC start/end**, tool, options, exit code, and filename for each sample.
- [ ] Capture sequentially; do not pile concurrent dumps onto a struggling JVM.
- [ ] Stop on attach errors, PID changes, or risk of production impact.
- [ ] Do not automatically enable heavy diagnostic operations without approval.
- [ ] Keep raw files intact, restrict sharing, and redact when needed.

### 17.3 During analysis

- [ ] Verify files share the same JVM instance and tool coverage.
- [ ] Match thread identities; never use thread name as the sole key.
- [ ] Compare state + stack signature + locks/owners at **each timestamp**.
- [ ] Read **completed/failed/in-flight/queue** metrics for the same instance/time.
- [ ] If CPU is suspected, correlate per-thread CPU deltas/JFR.
- [ ] If lock wait duration is suspected, correlate JFR/contended monitor events.
- [ ] If virtual threads are used, check coverage/format before counting.
- [ ] Formulate competing hypotheses and flag what remains **unproven**.

### 17.4 Incident report template

~~~text
Service/Version:
JVM identity: host/pod UID/PID/start time/JDK build
Symptom and affected window (UTC):
Capture method: tool/version/options/coverage
Samples: count, UTC start/end, file sizes, exit codes
Observed thread groups and stack signatures:
Repeated lock/owner or queue-wait evidence:
Evidence of progress: submitted/completed/failed/queue deltas
Other evidence: traces/app logs/GC/JFR/OS CPU
Hypotheses ranked by evidence:
What snapshots cannot establish:
Next safe validation:
Operational impact and data retention:
~~~

**Example of a sound conclusion:**

> On JVM checkout-pod-7 (same PID/start time), three captures at 10:00:02, 10:00:08, and 10:00:14 UTC recorded 14–18 HTTP workers BLOCKED on the same monitor X, with the owner's stack inside a dependency call. Over the corresponding interval, completed requests barely rose while queue depth continued climbing. This supports the hypothesis that lock contention is impeding progress. Continuous per-thread wait duration has not yet been measured; JFR monitor-enter durations and the owner's trace calls must be checked before concluding root cause.

**Example of a flawed conclusion:**

> Because three dumps had WAITING threads, all requests were deadlocked for 12 seconds; restarting is the only solution.

There is no inherent evidence for *deadlock*, *12 continuous seconds*, *all requests*, or *only solution* from three snapshots alone.

## 18. Official references to check for your exact JVM

- **Oracle JDK 21 – jcmd**, *Thread.print* impact/options and diagnostic commands: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- **Oracle JDK 21 – Diagnostic Tools**, how to obtain thread dumps and understand tool impact: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- **Java SE 17 – ThreadMXBean**, *getThreadInfo*, *dumpAllThreads*, deadlock/monitor support: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html
- **Java SE 17 – ThreadInfo**, stack/state/lock owner and snapshot semantics: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadInfo.html
- **Java SE 17 – Thread.State**, the six Java thread states: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html
- **Oracle JDK 21 – Virtual Threads**, thread dumps for virtual-thread applications: https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html

Syntax, virtual-thread support, output fields, attach behavior, and consistency of thread dumps **vary across JDKs/VMs/tools**. Always check *help* and documentation for the **exact version** of the process being diagnosed.

## Conclusion

**Multiple thread dumps enable comparing snapshots over time, without turning discrete snapshots into a continuous history.** Two identical *WAITING* states or identical stacks do not prove a thread is stuck; a worker can complete a task and return to the same wait site. Conversely, constantly changing stacks do not prove business progress.

The right approach is **choose sensible sample count/interval → record complete identity/timestamps/status → match the right threads → compare states, stacks, locks, and owners → correlate counters, traces, CPU/JFR/GC → conclude proportionally to the evidence**. Never infer duration or root cause from the gap between discrete snapshots.