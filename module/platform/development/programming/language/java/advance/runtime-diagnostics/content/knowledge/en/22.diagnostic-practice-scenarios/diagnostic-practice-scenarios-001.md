# 22.1 Building a Sample Application with Thread Names, Basic Metrics, and a Custom JFR Event

## 1. Objective of the Integrated Practice Lab

When a Java application responds slowly or consumes high resources, three sources of information are often read separately:

- **Thread:** which request/task is running, which worker is handling it, and whether the thread is blocked/waiting?
- **Metrics:** how many jobs were accepted, finished, failed, or are currently running; how do queue time and work time fluctuate?
- **Java Flight Recorder (JFR):** which specific event occurred, how long did it last, which task/thread did it belong to, and is it related to GC, allocation, CPU, or lock contention?

Looking at only one source makes incomplete diagnosis very likely. For example, `active=2` does not show which tasks the two workers are processing; a `jdk.JavaMonitorEnter` event does not by itself tell you which business task caused contention; a `task failed` log does not explain whether the JVM was under GC pressure.

This lesson builds a **standalone Java 17+ application**, requiring no Maven or external libraries, to integrate:

1. A `ThreadFactory` that creates worker threads with stable names `diag-worker-1`, `diag-worker-2`.
2. An `ExecutorService` with **two workers**, receiving **four tasks**, with one task simulated to fail.
3. **Basic metrics**: `submitted`, `finished`, `successes`, `failures`, `active`, `peakActive`, total `queueNanos`, and `workNanos`.
4. A **custom JFR event** `demo.WorkTask` with `taskId`, `workerName`, `outcome`, `queueNanos`, and `workNanos`.
5. A `Recording` that opens/closes itself to produce the file `thread-metrics-lab.jfr`.
6. A `RecordingFile` reader that reads back the JFR file and verifies event count, outcomes, thread names, and durations.

You will also learn how to use `jfr summary`/`jfr print`, distinguish counters from gauges, verify time units, avoid high-cardinality metric labels, and apply this pattern during incident troubleshooting.

**Scope:** This is a *diagnostic lab*. `Thread.sleep(30)` simulates work with a duration, **not real I/O**, and not a CPU or throughput benchmark. Metrics are kept in memory to study the mechanism; production systems typically export them via a dedicated monitoring system. Count results are deterministic by design, while actual durations and which worker picks up each task can vary by JVM/OS.

## 2. Sample Application Architecture

```text
                           main thread
                                |
                                v
              submit task-1, task-2, task-3, task-4
                                |
                      ExecutorService(2)
                                |
                       task queue / dispatch
                           /          \
                          v            v
                  diag-worker-1    diag-worker-2
                   execute(...)     execute(...)
                          \            /
                           \          /
                            v        v
                      Metrics in memory
                    counters + gauges + sums
                                |
                     per-task WorkTaskEvent
                                |
                          JFR Recording
                                |
                        thread-metrics-lab.jfr
                                |
                        RecordingFile reader
                                |
                        invariants / checks
```

**Three perspectives must be correlatable:**

- `taskId` identifies a single task instance.
- `workerName` (and JFR event thread metadata if recorded) shows which worker executed the task.
- `outcome` and durations allow comparing success/failure, queue wait/work, and spotting outliers.

Thread names help operators read thread dumps/JFR more easily, but **are not a unique request ID**. A worker pool reuses threads across many tasks, so correlating business logic still requires recording `taskId` or a separate trace/span ID.

### 2.1. Phases within a Task

```text
main:      enqueuedNano  --submit()----------------->
                          |
executor:                 | waiting for worker
                          v
worker:                  startedNano -- work --> endedNano
                          |                        |
                          |<------ workNanos ------>|
            |<---------- queueNanos --------------?|
            |<------------- total elapsed ---------------->|

queueNanos = startedNano - enqueuedNano
workNanos  = endedNano - startedNano
```

The diagram is a conceptual representation; `queueNanos` in the actual example covers **the time from before calling submit until the worker starts**, meaning it includes scheduling and dispatch, not only time spent strictly inside the queue structure. If pure enqueue/dequeue time must be measured, timestamps must be added directly on the queue API boundaries.

JFR's `Event.begin()` is called once the worker has started the task, and `Event.end()` when the work portion finishes. Therefore **the JFR intrinsic event duration approximates work time**, excluding wait time before STARTED. We store `queueNanos` as a separate field to observe the wait portion.

## 3. Designing Thread Names and Executor Lifecycle

### 3.1. Why Name Threads?

A thread dump with dozens or hundreds of threads bearing default names like `pool-7-thread-2` is hard to map back to business components. Structured names make tracing much simpler:

```text
diag-worker-1
diag-worker-2
```

In large applications, prefix by **component** rather than a per-request ID on each thread: `order-io-worker-1`, `sync-job-worker-2`, `cache-refresh-1`. Workers serve many requests; if attaching a request ID to a thread name, you must swap and restore it safely to avoid leaking stale info to another task.

A thread name is a **diagnostic hint**, not sole proof. You should also use thread ID/native ID, process/PID, timestamp, and task/trace ID. Two JVMs on two containers can both have `diag-worker-1`.

### 3.2. A Properly Implemented ThreadFactory

The lesson's example uses `AtomicInteger` to assign sequence numbers and creates threads directly:

```java
// Illustrative fragment; namedFactory is used in the full program in section 7.
AtomicInteger sequence = new AtomicInteger();
ThreadFactory namedFactory = task -> {
    Thread worker = new Thread(task,
            "diag-worker-" + sequence.incrementAndGet());
    worker.setDaemon(false);
    return worker;
};
```

`ThreadFactory.newThread(Runnable)` lets you set name, daemon status, priority, or an uncaught exception handler when needed. Do not arbitrarily raise priority, change daemon status on production executors, or put secrets into thread names.

**Why `AtomicInteger`?** `ThreadFactory` can be called from multiple worker creation paths; incrementing the sequence must be concurrency-safe. Numbers 1, 2 only guarantee uniqueness **within this factory instance**, not system-wide.

**Why `setDaemon(false)`?** These are platform threads that need to process accepted tasks; daemon threads do not keep the JVM alive on their own and can be terminated when the process exits. Even when using non-daemon threads, you must still shut down the executor cleanly.

### 3.3. Choosing a Fixed Thread Pool for the Lab

`Executors.newFixedThreadPool(2, namedFactory)` uses at most two active workers, with an internal queue holding waiting tasks. This is convenient for observing queue-to-start latency. However, **a default fixed thread pool has an unbounded queue**; do not copy it to production under unbounded load without backpressure, deadlines, and a rejection policy.

In production, you should usually consider a `ThreadPoolExecutor` with a bounded queue and an appropriate `RejectedExecutionHandler`, along with metrics for queue depth and rejected count.

At shutdown, the example calls `shutdown()`, `awaitTermination(...)`, and `shutdownNow()` if necessary. `shutdownNow()` requests interruption of running tasks, without guaranteeing every task stops on its own; task code must honor interruption contracts properly.

## 4. Choosing Metrics: Counters, Gauges, and Duration Measurements

### 4.1. Metrics Used

| Metric | Type | Meaning | Useful Invariant |
| --- | --- | --- | --- |
| `submitted` | Counter | Number of tasks accepted into the demo flow and submitted | Monotonically non-decreasing |
| `finished` | Counter | Tasks reaching the `finally` block and completing the execution path | Monotonically non-decreasing |
| `successes` | Counter | Tasks with outcome SUCCESS | Monotonically non-decreasing |
| `failures` | Counter | Tasks with outcome other than SUCCESS in the demo | Monotonically non-decreasing |
| `active` | Gauge | Number of tasks currently being processed by workers at measurement time | From 0 to 2 in the demo |
| `peakActive` | High-water mark | Highest observed active count | Does not exceed capacity=2 |
| `queuedNanos` | Sum | Total wait-to-start time of finished tasks | Meaningful only with the same clock/unit |
| `workedNanos` | Sum | Total work duration of finished tasks | Not the wall-clock elapsed time of the whole pool |

After all Futures complete successfully from an **orchestration** standpoint, we expect:

```text
submitted = finished = successes + failures = 4
successes = 3
failures = 1
active = 0
0 <= peakActive <= 2
```

In practice, `peakActive` is expected to be at least 1 when tasks run, though parallel execution **does not guarantee** observing exactly 2 on every run — it depends on scheduling.

### 4.2. LongAdder for Multi-Writer Counters

`LongAdder` is useful for counters incremented concurrently by multiple threads: it typically reduces contention compared to `AtomicLong` under heavy load. It fits **aggregation**:

```java
// Illustrative fragment, used when java.util.concurrent.atomic.* imports are present.
LongAdder completed = new LongAdder();
completed.increment();
long total = completed.sum();
```

**Important:** `sum()` while multiple writers are updating **is not an atomic snapshot of the entire system**. If you read counters sequentially while a service is still running, you may temporarily see `finished != successes+failures` due to update ordering. Do not trigger false alerts on an unsynchronized read; take a snapshot after all Futures complete to check lab invariants.

In a live incident flow, metric scrapes can happen mid-update; counters should be treated as **eventually consistent** by design.

### 4.3. AtomicInteger for the Active Gauge

`active.incrementAndGet()` when a task starts and `active.decrementAndGet()` in `finally` when the task finishes. If you only decrement on the SUCCESS branch, the counter will grow indefinitely after failures and create the illusion of stuck workers.

`peakActive.accumulateAndGet(nowActive, Math::max)` is an atomic max operation; avoid `if (nowActive > peak) peak = nowActive` because updates can easily be lost across threads.

### 4.4. Measuring Duration with nanoTime, Not Wall-Clock Timestamps

`System.nanoTime()` is for measuring **elapsed time**, not UTC timestamps. You must take two or three timestamps within **the same JVM** and subtract them. Absolute values must never be compared across two machines/JVMs.

In the lab:

```java
// Fragment illustrating duration measurements.
long enqueuedNano = System.nanoTime();
// Task is submitted and later executed by a worker:
long startedNano = System.nanoTime();
// When the operation finishes:
long endedNano = System.nanoTime();

long queueNanos = startedNano - enqueuedNano;
long workNanos = endedNano - startedNano;
double workMillis = workNanos / 1_000_000.0;
```

`1 ms = 1,000,000 ns`. Never turn a nanosecond measurement into milliseconds by slapping an `ms` label on it without converting the unit.

**Do not use `System.currentTimeMillis()` as the sole clock for short durations.** Wall clocks can be adjusted; use `Instant.now()` or epoch millis when you need to correlate with UTC logs, and use a monotonic clock for durations.

### 4.5. Histograms and p95/p99 Come Later

Having only `workedNanos.sum()` and `finished.sum()` allows computing the **average** across finished tasks, but **cannot compute accurate p95/p99**. For tail latency, you need a timer/histogram with buckets or a properly designed quantile mechanism.

Nor should you sum `workedNanos` to infer the pool's elapsed wall-clock time: two workers can run simultaneously, so total task processing time exceeds wall-clock elapsed time.

In production, you can use Micrometer/OpenTelemetry Metrics or a Prometheus-compatible exporter for counters/gauges/timers; **this lesson has no external dependencies** so it remains runnable directly on JDK 17+.

## 5. Designing Meaningful Custom JFR Events

### 5.1. What Is a JFR Event?

JFR records runtime events into a recording, which can include JVM events and application-defined events. For a custom event, you subclass `jdk.jfr.Event`, declare recordable fields, and control its lifecycle:

```text
new WorkTaskEvent()
        |
     event.begin()  <- start of work
        |
     execute task
        |
     event.end()    <- end of work
        |
     assign taskId, workerName, outcome, durations
        |
     event.commit() <- submit event for JFR to decide whether to record
        |
     recording dumped to .jfr
```

`commit()` can be called after `end()` and after populating the fields to store; JFR checks `enabled`/`threshold` settings to decide whether to write it. In the example, `withThreshold(Duration.ZERO)` keeps even short events. If you raise the threshold, events shorter than the threshold will not appear and the read-back event count may be lower than `finished`.

### 5.2. The WorkTaskEvent Class

The program includes:

```java
@Name("demo.WorkTask")
@Label("Work task")
@Category({"Demo", "Diagnostics"})
@StackTrace(false)
public static final class WorkTaskEvent extends Event {
    @Label("Task ID")
    public String taskId;
    @Label("Worker name")
    public String workerName;
    @Label("Outcome")
    public String outcome;
    @Timespan(Timespan.NANOSECONDS)
    public long queueNanos;
    @Timespan(Timespan.NANOSECONDS)
    public long workNanos;
}
```

This is a **fragment inside the full program class** in section 7; on its own it lacks imports/main. The annotations give JFR metadata meaning:

- `@Name("demo.WorkTask")` gives a **stable** event type name to search in `jfr summary`, `jfr print`, JMC, or `RecordingFile`.
- `@Label` is the display name, not a technical key.
- `@Category` groups events in the JFR/JMC UI.
- `@StackTrace(false)` defaults to not capturing call stacks to reduce overhead; a recording can override it with `withStackTrace()` if needed.
- `@Timespan(Timespan.NANOSECONDS)` explicitly states that the two `long` fields carry time units, so tools understand their semantics.

If you want to see call sites, enable stack traces on the corresponding recording while weighing event volume and overhead. In the demo, worker name and task ID already provide simple correlation, so stacks are not needed for every task.

### 5.3. Which Fields Should Go into a Custom Event?

A production schema might use `taskId`, `operation` (a low-cardinality categorical value), `workerName`, `outcome`, `queueNanos`, `workNanos`, `errorType`. However, payload must be bounded:

- Avoid raw HTTP bodies, SQL parameters, access tokens, cookies, secrets, email/PII.
- Do not put arbitrary object graphs into events; JFR event fields have a supported set of types.
- Use `String` / primitive fields and appropriate class/thread metadata; do not expect JFR to automatically serialize custom `Map<String,Object>` objects.
- Do not put `taskId` into a Prometheus metric **label**: each request creates a new time series, causing cardinality explosion. Task ID fits JFR/logs/traces with controlled retention and sampling.
- When the schema evolves, consider versioning so downstream parsers identify fields correctly.

### 5.4. Event Duration and Field Duration Are Two Different Measurements

`event.getDuration()` in `RecordingFile` gives the intrinsic duration between `begin()` and `end()`. In the lab, `workNanos` is computed as `endedNano - startedNano`, which includes slight overhead around `event.begin/end`; the two values are close but **need not be strictly identical**.

`queueNanos` is an application-computed field and **is not part of the intrinsic event duration**. If a worker starts very late but the work is fast, a JFR event with a high threshold can still be filtered out even when `queueNanos` is large. That is why boundaries and thresholds must match diagnostic goals.

## 6. Lab Structure and How to Run It

The lesson uses **a single Java file** and one JFR output file:

```text
lab/
├── ThreadMetricsJfrLab.java
├── ThreadMetricsJfrLab.class     (created after javac)
├── ThreadMetricsJfrLab$*.class   (nested classes after javac)
└── thread-metrics-lab.jfr        (created after running the program)
```

Requirements:

- **JDK 17+** with the `jdk.jfr` module.
- Run from a terminal with write permission in the current directory.
- No Maven, Gradle, or external JVM agent required.
- JFR is enabled and configured directly inside `main()`.
- Each run creates/overwrites `thread-metrics-lab.jfr` in the working directory; **do not use this name/path on production data you need to keep**.

Create a dedicated lab directory before running to avoid overwriting unintended artifacts.

## 7. Complete Runnable Java 17+ Program

Create **`ThreadMetricsJfrLab.java`** with the following contents:

```java
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import jdk.jfr.*;
import jdk.jfr.consumer.*;

public final class ThreadMetricsJfrLab {
    @Name("demo.WorkTask")
    @Label("Work task")
    @Category({"Demo", "Diagnostics"})
    @StackTrace(false)
    public static final class WorkTaskEvent extends Event {
        @Label("Task ID")
        public String taskId;
        @Label("Worker name")
        public String workerName;
        @Label("Outcome")
        public String outcome;
        @Timespan(Timespan.NANOSECONDS)
        public long queueNanos;
        @Timespan(Timespan.NANOSECONDS)
        public long workNanos;
    }

    private static final class Metrics {
        final LongAdder submitted = new LongAdder();
        final LongAdder finished = new LongAdder();
        final LongAdder successes = new LongAdder();
        final LongAdder failures = new LongAdder();
        final LongAdder queuedNanos = new LongAdder();
        final LongAdder workedNanos = new LongAdder();
        final AtomicInteger active = new AtomicInteger();
        final AtomicInteger peakActive = new AtomicInteger();
    }

    private static String execute(String taskId, boolean fail,
                                  long enqueuedNano, Metrics metrics) {
        long startedNano = System.nanoTime();
        int nowActive = metrics.active.incrementAndGet();
        metrics.peakActive.accumulateAndGet(nowActive, Math::max);

        WorkTaskEvent event = new WorkTaskEvent();
        event.begin();
        String outcome = "SUCCESS";
        try {
            Thread.sleep(30);
            if (fail) {
                throw new IllegalStateException("simulated failure");
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            outcome = "CANCELLED";
        } catch (IllegalStateException exception) {
            outcome = "ERROR";
        } finally {
            event.end();
            long endedNano = System.nanoTime();
            long queueNanos = startedNano - enqueuedNano;
            long workNanos = endedNano - startedNano;

            event.taskId = taskId;
            event.workerName = Thread.currentThread().getName();
            event.outcome = outcome;
            event.queueNanos = queueNanos;
            event.workNanos = workNanos;
            event.commit();

            metrics.queuedNanos.add(queueNanos);
            metrics.workedNanos.add(workNanos);
            if ("SUCCESS".equals(outcome)) {
                metrics.successes.increment();
            } else {
                metrics.failures.increment();
            }
            metrics.finished.increment();
            metrics.active.decrementAndGet();
        }
        return outcome;
    }

    private static void verifyRecording(Path path) throws Exception {
        Map<String, String> outcomes = new TreeMap<>();
        int count = 0, ok = 0, error = 0;
        try (RecordingFile file = new RecordingFile(path)) {
            while (file.hasMoreEvents()) {
                RecordedEvent event = file.readEvent();
                if (!"demo.WorkTask".equals(
                        event.getEventType().getName())) {
                    continue;
                }
                count++;
                String taskId = event.getString("taskId");
                String outcome = event.getString("outcome");
                String worker = event.getString("workerName");
                if (!worker.matches("diag-worker-[12]")) {
                    throw new IllegalStateException("Worker name mismatch");
                }
                if (event.getLong("queueNanos") < 0 ||
                        event.getLong("workNanos") < 0) {
                    throw new IllegalStateException("Negative duration");
                }
                if (outcomes.put(taskId, outcome) != null) {
                    throw new IllegalStateException("Duplicate event");
                }
                if ("SUCCESS".equals(outcome)) ok++;
                if ("ERROR".equals(outcome)) error++;
            }
        }
        if (count != 4 || ok != 3 || error != 1 ||
                outcomes.size() != 4 ||
                !"ERROR".equals(outcomes.get("task-3"))) {
            throw new IllegalStateException("Unexpected JFR results: " + outcomes);
        }
        System.out.printf("jfrEvents=%d jfrSuccess=%d jfrError=%d%n",
                count, ok, error);
    }

    public static void main(String[] args) throws Exception {
        Metrics metrics = new Metrics();
        AtomicInteger workerSequence = new AtomicInteger();
        ThreadFactory namedFactory = runnable -> {
            Thread worker = new Thread(runnable,
                    "diag-worker-" + workerSequence.incrementAndGet());
            worker.setDaemon(false);
            return worker;
        };

        Path path = Path.of("thread-metrics-lab.jfr");
        try (Recording recording = new Recording()) {
            recording.enable(WorkTaskEvent.class)
                    .withThreshold(Duration.ZERO)
                    .withoutStackTrace();
            recording.start();

            ExecutorService executor =
                    Executors.newFixedThreadPool(2, namedFactory);
            List<Future<String>> results = new ArrayList<>();
            try {
                for (int n = 1; n <= 4; n++) {
                    String taskId = "task-" + n;
                    boolean fail = n == 3;
                    long enqueuedNano = System.nanoTime();
                    metrics.submitted.increment();
                    results.add(executor.submit(() ->
                            execute(taskId, fail, enqueuedNano, metrics)));
                }
                for (Future<String> result : results) {
                    result.get();
                }
            } finally {
                executor.shutdown();
                if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                    executor.shutdownNow();
                }
            }

            recording.stop();
            recording.dump(path);
        }

        System.out.printf(
                "submitted=%d finished=%d success=%d failure=%d active=%d%n",
                metrics.submitted.sum(), metrics.finished.sum(),
                metrics.successes.sum(), metrics.failures.sum(),
                metrics.active.get());
        verifyRecording(path);
        System.out.println("checks=PASS");
    }
}
```

### 7.1. Compile and Run Commands

In a terminal inside the directory containing the file:

```bash
javac --release 17 ThreadMetricsJfrLab.java
java ThreadMetricsJfrLab
```

Depending on your terminal, run `java -version` and `javac -version` to ensure you are using a JDK with JFR. `--release 17` checks that the code uses only APIs and syntax compatible with Java 17; the `java` command still runs on the machine's actual JVM.

**Verified stdout** compiled with `--release 17` and run on JDK 24:

```text
submitted=4 finished=4 success=3 failure=1 active=0
jfrEvents=4 jfrSuccess=3 jfrError=1
checks=PASS
```

Those three lines are **the expected stable output when the program executes successfully**, without printing scheduling-dependent parts such as task-to-worker assignment, nanoTime, RSS, or wall-clock timestamps. In the same test run, `jfr summary` confirmed four `demo.WorkTask` instances.

### 7.2. The ThreadFactory Part

In `main()`, `workerSequence` assigns names `diag-worker-1`, `diag-worker-2` when the executor needs to create workers. `ThreadFactory` is not called once per task: **threads are reused**. There are four tasks, yet at most two threads are needed.

The `verifyRecording` method checks that the recorded event's worker name matches `diag-worker-[12]`. This is an **actual verification inside the JFR file**, not just reading the code and assuming threads were named.

### 7.3. The Metric Counters and Gauges Part

`Metrics` holds standard Java concurrency types:

- `LongAdder` for counts and total durations.
- `AtomicInteger` for the active gauge and high-water mark.
- No static global metrics; a `Metrics` instance belongs to the lifecycle of a single lab run. In a real service, scope the metric registry to the appropriate component/lifetime.

In `execute`, when a task starts, `active` increments; when passing through `finally`, `active` decrements. Status `SUCCESS` increments `successes`, and status `ERROR`/`CANCELLED` increments `failures` under the lab's simple counting scheme.

**Failure boundary note:** the example catches `IllegalStateException` to produce an `ERROR` outcome instead of letting the Future throw an exception. That choice illustrates telemetry with complete results and deterministic output. In production, after recording metrics/events you must **propagate the error or fail the future per contract**, never hiding failures from the caller.

### 7.4. The JFR Event Part

`WorkTaskEvent` is created when a worker enters `execute`, then:

1. `event.begin()` marks the start of work.
2. `Thread.sleep(30)` simulates activity; `task-3` throws an error.
3. `event.end()` marks the end of work right at the start of `finally`.
4. Fields `taskId`, `workerName`, `outcome`, `queueNanos`, and `workNanos` are assigned.
5. `event.commit()` submits the event to the JFR recording.

The recording is configured with:

```java
recording.enable(WorkTaskEvent.class)
        .withThreshold(Duration.ZERO)
        .withoutStackTrace();
```

This is a **fragment extracted from the full program**, not a standalone class. `Duration.ZERO` keeps short demo events; `withoutStackTrace()` disables stacks in this recording. A custom event is not recorded automatically without an active matching recording or if the event type is disabled.

### 7.5. Reading JFR and Verifying Results

`RecordingFile` reads the `.jfr` file sequentially; each `RecordedEvent` is filtered by `event.getEventType().getName()`. The program checks:

- There are exactly **4** `demo.WorkTask` events.
- There are **3 SUCCESS** and **1 ERROR**.
- `task-3` is the simulated failing task.
- Each `workerName` matches one of the two expected worker names.
- `queueNanos` and `workNanos` are non-negative.
- No duplicate task IDs exist.

Because results are checked **after writing and reading back the file**, the `checks=PASS` line carries stronger meaning than merely counting `event.commit()` calls. Still, this is a lab self-test and does not replace performance testing or full production telemetry.

### 7.6. Do Not Infer Unprinted Output

The example does not print `peakActive`, average duration, or task-to-worker mapping because those values vary. You can experiment by adding output yourself:

```java
// Illustrative fragment at the end of main(), where the metrics variable is in scope.
// Read after all Futures complete so the numbers are easy to interpret.
System.out.println("peakActive=" + metrics.peakActive.get());
System.out.println("averageWorkMs="
        + (metrics.workedNanos.sum() / 1_000_000.0)
        / Math.max(1L, metrics.finished.sum()));
```

**There is no fixed stdout** for these two lines. `peakActive` falls between 1 and 2 when tasks have run, while average work hovers around `Thread.sleep(30)` plus overhead, and can be noticeably higher on a busy machine. `Thread.sleep` does not guarantee waking up at exactly 30 ms.

## 8. Inspecting the JFR File with Bundled JDK Tools

After running, `thread-metrics-lab.jfr` is in the current directory. Use the CLI:

```bash
jfr summary thread-metrics-lab.jfr
jfr print --events demo.WorkTask thread-metrics-lab.jfr
jfr metadata thread-metrics-lab.jfr
```

### 8.1. What Does `jfr summary` Tell You?

`jfr summary` lists event type names, counts, and approximate event data sizes depending on JDK version. On a successful run you expect:

```text
demo.WorkTask                 4
```

The line above is a **key excerpt**, not the entire verbatim stdout of `jfr summary`. Size columns, metadata, and other event types depend on the JVM and how the file was recorded. Do not conclude every event in the JFR file is `demo.WorkTask`, because the file may contain JVM events from default settings.

### 8.2. What Does `jfr print` Tell You?

With `--events demo.WorkTask`, the CLI displays each record, e.g., fields `taskId`, `workerName`, `outcome`, `queueNanos`, `workNanos` along with timestamps/durations formatted by the JDK. **There is no single exact common transcript** because timestamps, durations, and worker-to-task mapping change with scheduling.

A conceptual view of field values (**hypothetical illustrative data**, not verbatim output):

```text
taskId       = "task-3"
workerName   = "diag-worker-1"
outcome      = "ERROR"
queueNanos   = <nonnegative duration in ns>
workNanos    = <nonnegative duration in ns>
```

The read-back event count and outcomes must match the program; worker assignment or nanosecond values should not be hardcoded.

### 8.3. Viewing in JDK Mission Control

Open the file in JDK Mission Control (JMC) and look for the event type `demo.WorkTask`. Try to:

1. Find events by type name `demo.WorkTask`.
2. View total event count and duration distribution.
3. Group or filter by `workerName` and `outcome`.
4. Compare timestamps against GC, CPU/threads, and built-in events if collected.
5. Check correlation between event duration and `queueNanos`, separating queue wait from execution.

The lab's four tasks are too few to infer a real performance distribution; JMC here is a **tool-handling exercise**, not a benchmark source.

## 9. Separating Three Frequently Conflated Diagnostic Questions

### 9.1. "How Busy Are the Workers?"

`metrics.active` is a gauge updated while tasks execute. If active=2 on a fixed pool of capacity 2, the pool is using both workers **at the moment of reading**. However, you cannot conclude overload without knowing **queue depth**, arrival rate/second, processing rate, and wait time.

`peakActive=2` means 2 workers were active concurrently at some point, not that the pool is continuously saturated.

### 9.2. "How Long Did Tasks Wait Before Running?"

`queueNanos` on each event measures from before `submit` until `execute` begins. An increasing queue duration while work duration stays stable is a signal worth investigating for worker saturation, queueing, or dispatch overhead.

Queue depth/rejection count and arrival rate are also needed to conclude. With a default fixed pool's unbounded queue, tasks can wait longer and longer without immediate rejections appearing.

### 9.3. "Why Are Tasks Processing Slowly?"

`workNanos` gives total time inside the task, but **does not automatically break down CPU, blocking I/O, lock contention, GC pauses, or scheduling**. When spotting outliers, use built-in JFR events like `jdk.ExecutionSample`, `jdk.JavaMonitorEnter`, `jdk.FileRead`/`jdk.SocketRead`, and GC/safepoint events (if enabled) to investigate deeper.

Having `workerName` and task ID makes correlation easier, though an individual JFR event does not guarantee full root-cause details or a call stack when `stackTrace=false`.

## 10. Extension: Snapshotting Heap and Thread Count with MXBeans

Thread names and task metrics only describe **the executor component**. For JVM context, Java provides `java.lang.management`:

- `MemoryMXBean`: heap/non-heap used/committed/max.
- `ThreadMXBean`: live thread count, peak thread count, thread info, and CPU time if supported by the JVM.
- `RuntimeMXBean`: uptime, JVM runtime identity.
- `OperatingSystemMXBean`: OS name, available processors, and standard JVM info.

Example **fragment**, not a standalone program (add `import java.lang.management.*;` to the application):

```java
MemoryMXBean memoryBean = ManagementFactory.getMemoryMXBean();
ThreadMXBean threadBean = ManagementFactory.getThreadMXBean();
RuntimeMXBean runtimeBean = ManagementFactory.getRuntimeMXBean();

MemoryUsage heap = memoryBean.getHeapMemoryUsage();
long heapUsedBytes = heap.getUsed();
int liveJVMThreads = threadBean.getThreadCount();
long uptimeMs = runtimeBean.getUptime();

System.out.println("heapUsedBytes=" + heapUsedBytes);
System.out.println("jvmThreadCount=" + liveJVMThreads);
System.out.println("jvmUptimeMs=" + uptimeMs);
```

These numbers vary by JVM and moment in time. `heapUsedBytes` **is not process RSS**; `ThreadMXBean` counts threads using VM semantics, which differs from the executor's `active`. Take JVM and task metric snapshots within the same time window, tagged with UTC timestamp and PID/instance ID if used for comparison.

### 10.1. Thread Names in a Thread Dump

While a program or real service is alive, you can use:

```bash
jcmd -l
jcmd 12345 Thread.print -l
```

Replace `12345` with the real PID. Thread names `diag-worker-*` can appear in a thread dump **while workers are alive**, though a short lab may finish before you attach. Do not use a dummy PID and conclude threads are missing.

In long-running production services, consistent naming and correlation IDs help link JFR events with concurrent thread dumps. Also distinguish Java thread IDs from native OS TIDs (`nid`, often shown in hex in dumps).

## 11. Making the Demo More Production-Like Without Breaking the Lesson

### 11.1. Adding Queue Depth and Rejected Task Metrics

A default fixed pool has an unbounded queue; in high-load services consider a bounded executor:

```java
// Illustrative fragment; requires imports and an already created namedFactory.
// Not a standalone program.
ThreadPoolExecutor executor = new ThreadPoolExecutor(
        2, 2,
        0L, TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(100),
        namedFactory,
        new ThreadPoolExecutor.AbortPolicy());

int queueDepth = executor.getQueue().size();
int activeWorkers = executor.getActiveCount();
```

`getQueue().size()` and `getActiveCount()` are **point-in-time/approximate** measurements under concurrency; they do not replace historical metrics. With a bounded queue, `RejectedExecutionException` can occur **before a worker ever runs the task**. In that case `submitted` must be clearly defined as **attempted** or **accepted**: if incremented before `submit`, the metric actually measures attempted; if you want accepted, increment after `submit` succeeds.

The lab increments `submitted` before `submit`, though there is no rejection in the demo's configuration and workload. In production, distinguish `attempted`, `accepted`, and `rejected` clearly so invariants stay meaningful.

### 11.2. Recording Operation Name and Correlation ID

To analyze by work type, add `operation` with a finite set of values like `"cache.refresh"`, `"db.read"`, `"file.write"`. This lets you group durations by operation without creating millions of metric series.

A request can have multiple attempts, so use `requestId` + `attemptId` or trace/span IDs. These values have high cardinality: use them in JFR/logs/traces with appropriate retention, **not** as labels for time-series metrics.

### 11.3. Propagating Context When Tasks Switch Threads

`ThreadLocal` or logging MDC is not automatically copied from the request-receiving thread to the worker in every framework. Pass `TaskContext` via constructor/lambda or set/clear MDC in a controlled manner:

```java
// Conceptual fragment: context is passed into the task.
// Exact MDC depends on the application's logging library.
executor.submit(() -> processWithContext(context));
```

When using a worker pool, always clean up context in `finally` so new requests do not inherit the previous task's request ID. With virtual threads/reactive execution, propagation mechanisms must match the concurrency model.

### 11.4. Handling Errors, Timeouts, and Cancellation Properly

The demo intentionally turns `task-3`'s failure into an `ERROR` outcome while still returning a successful `Future<String>` from a Java exception-flow perspective. In real systems:

- For `ERROR`, callers may need to receive an exception/failure response; telemetry is a diagnostic side effect, not a replacement for the contract.
- For `TIMEOUT`, distinguish caller deadline from when downstream execution actually stops.
- For `CANCELLED`, restore interrupt status when catching `InterruptedException` and stop processing appropriately; do not assume interruption has certainly freed I/O resources.
- If a task is **REJECTED before running**, there is no worker `begin/end`; record a separate rejection event or metric on the submit path.
- If a process is killed with `SIGKILL`, `finally` may not run and JFR events may remain uncommitted/files undumped. Monitoring/live logs must tolerate telemetry gaps.

A production application should aim for **one terminal outcome per attempt**, avoiding completion callbacks and timeouts both emitting finishing events.

## 12. Understanding JFR Configuration to Avoid Wrong Conclusions

### 12.1. Enabled, Threshold, Stack Trace

Within a recording:

- `enabled` determines whether the event type can be captured.
- `threshold` filters by **intrinsic duration between begin and end**. `Duration.ZERO` keeps events even when work is fast.
- `stackTrace` determines whether Java call stacks are recorded for supported events.
- `period` applies to periodic/sampling events, **not** a mechanism that generates custom `demo.WorkTask` events every N ms.

**In the demo**, Java code explicitly calls `commit()` every time a task finishes. If the recording is disabled or threshold exceeds work duration, the JFR event count **will not equal** `finished`. That does not automatically mean code lost tasks — it may simply be JFR collection policy.

When using JFR in production, you do not always need `Duration.ZERO` continuously for every task under high volume. You can filter long-duration events, sample, or record only during incidents, but then any aggregation from the file must note **selection bias**.

### 12.2. JFR Is Not a Native 24/7 Metrics Store

A JFR file is a snapshot of a recording bounded by time/size. It does not replace monitoring aggregation, alerting, or storage/retention. If a service runs 50,000 tasks/s and JFR records one event per task, data volume and overhead can become significant even though JFR is optimized for low overhead.

Keep an eye on:

- `jfr summary`: event counts and event types with unusually high volume.
- Recording size and retention.
- CPU/GC overhead during windows with stack traces or detailed capture enabled.
- `jdk.jfr.Recording` / `jcmd JFR.start` configuration and actual event settings.
- Ability to persist artifacts across container restarts.

### 12.3. Sensitive Data

A JFR file may contain thread names, class/method names, file paths, stack traces, JVM metadata, and custom fields. Protect `.jfr` files as diagnostic artifacts potentially containing sensitive data. Never publicly share an unredacted/uncontrolled production recording.

## 13. Minimum Recommended Dashboard

When turning the lab into a service, a basic dashboard should have **two tiers**:

| Tier | Metric/Column | Purpose |
| --- | --- | --- |
| Component work | `tasks_accepted_total` | Volume of accepted tasks |
| Component work | `tasks_completed_total{result="success/error/..."}` | Outcomes by status |
| Component work | `tasks_active` | Number of tasks currently executing on workers |
| Component work | `tasks_queued` | Queue depth at scrape time |
| Component work | `task_wait_seconds` histogram | Distribution of wait time before execution |
| Component work | `task_work_seconds` histogram | Distribution of work duration |
| JVM | Heap used/max/committed | Memory/GC context |
| JVM | Live threads, CPU, GC pause | Runtime context |
| Diagnostic detail | `demo.WorkTask` event | Specific task/thread/outcome/duration over time |

Names in the table are **schema suggestions**, not automatically exported by the demo. For histograms, use consistent units such as seconds per your metrics system's convention, rather than exporting nanoseconds under a `seconds` label.

**Note on status labels:** a finite set of outcomes (SUCCESS/ERROR/CANCELLED...) is typically low-cardinality. `taskId`/`workerName` can grow unbounded or churn with scale-out, so keep them as fields in events/logs for tracing rather than default metric labels across all combinations.

### 13.1. Invariants and Alerts

A few useful checks once semantics are precisely defined:

- `active >= 0`; active does not exceed bounded processing capacity in a given model.
- `finished <= accepted` if accepted counts every task truly accepted by the executor and there is only one terminal event per task.
- `success + failure == finished` **after processing finishes and reads are synchronized** in the demo; during concurrent scrapes they can differ momentarily.
- Unusual failure rate spike compared to baseline (avoid paging on a single isolated error).
- Rising p95/p99 `queue wait` while `work` remains flat: check worker saturation/backpressure.
- Dropping JFR event counts do not necessarily mean fewer tasks: check `enabled`/`threshold`/recording window.

Automated alerting needs sufficient data and time windows; avoid drawing conclusions from a single instantaneous metric reading.

## 14. Common Mistakes When Doing the Lab Yourself

**Mistake 1 — Not using a ThreadFactory and not knowing which worker did the work.** Default names are hard to correlate; prefix by component and sequence number.

**Mistake 2 — Assuming four tasks mean four threads.** An executor with two workers can process multiple tasks sequentially; task IDs must be independent of worker names.

**Mistake 3 — Using a plain `long++` across multiple threads.** Updates are unsafe under concurrency; use `LongAdder` or `AtomicLong` as needed.

**Mistake 4 — Forgetting to decrement `active` on the error branch.** The gauge climbs endlessly and lies; use `finally`.

**Mistake 5 — Calling `submit` and immediately treating the task as STARTED.** Tasks can wait in the queue; measure timestamps inside the real worker.

**Mistake 6 — Subtracting `System.currentTimeMillis()` as the standard duration.** Wall clock can jump and has limited resolution; use `System.nanoTime()` in the same JVM.

**Mistake 7 — Annotating `@Timespan(NANOSECONDS)` while passing milliseconds.** Tools will misinterpret durations; verify units at the source.

**Mistake 8 — Omitting `event.commit()`.** Creating the event object and calling begin/end is not enough to record a custom event.

**Mistake 9 — Not enabling the event in the recording.** You can get 0 events even though code calls commit; verify the right recording, event name, and settings.

**Mistake 10 — Setting threshold too high.** An event for a task that waited long in the queue but ran fast can still be filtered because intrinsic event duration covers only work.

**Mistake 11 — Setting stackTrace=true on every high-frequency task.** Stack traces have overhead; enable when code locations are needed, and consider sampling/thresholds.

**Mistake 12 — Calling `RecordingFile.readAllEvents` on very large files.** It can retain millions of events on the heap; use `hasMoreEvents()/readEvent()` and bounded aggregation.

**Mistake 13 — Summing `workedNanos` and calling it wall time.** Workers run in parallel; total durations are not the pool's elapsed wall time.

**Mistake 14 — Taking the average and inferring p99.** You cannot reconstruct percentiles from sum and count; use histograms/distributions.

**Mistake 15 — Emitting every task ID as a metric label.** Cardinality explodes; use IDs in logs/JFR/traces, and metrics for categories.

**Mistake 16 — Swallowing exceptions while collecting metrics.** Demo code handles errors intentionally; real applications must preserve error-reporting contracts.

**Mistake 17 — Not shutting down the executor.** Non-daemon worker threads can keep the JVM alive; use `shutdown`/`awaitTermination` and safe cleanup.

**Mistake 18 — Concluding there is no incident because JFR has no events.** It could be disabled recording, threshold, sampling, missing file, wrong process, or recording window.

## 15. Extended Practice Exercises

### Exercise A — Computing Metrics from Four Tasks

Suppose (**illustrative** numbers) four tasks have:

| Task | Queue wait | Work | Outcome |
| --- | ---: | ---: | --- |
| task-1 | 5 ms | 30 ms | SUCCESS |
| task-2 | 6 ms | 31 ms | SUCCESS |
| task-3 | 36 ms | 32 ms | ERROR |
| task-4 | 38 ms | 30 ms | SUCCESS |

Compute total queue wait, total work, average work, and error count.

**Answer:** Total queue wait = `5+6+36+38=85 ms`. Total work = `30+31+32+30=123 ms`. Average work = `123/4=30.75 ms`. ERROR count = `1`. You **cannot** conclude the pool's elapsed wall-clock time is `123 ms` because tasks can overlap.

### Exercise B — Changing Pool Configuration

Change the worker count from 2 down to 1 (in the lab environment only) and run multiple times. Does queue wait in JFR tend to increase for later-arriving tasks? Why does total work stay relatively stable?

**Hint:** When one worker processes sequentially, later tasks wait longer while the simulated 30 ms work does not change significantly. Actual results still include scheduling overhead; do not assume exact absolute durations.

### Exercise C — Getting a Histogram

To know p99 task latency from metrics, are `workedNanos.sum()` and `finished.sum()` enough?

**Answer:** No. Those two numbers give the average over completed tasks, not the distribution. Use a histogram/timer; inspect results grouped by operation and outcome with sufficient data volume.

### Exercise D — Catching Errors Without Losing Semantics

In the demo, `task-3` is recorded as `ERROR` yet `Future.get()` does not throw because `execute()` caught the exception. Propose how the caller can still receive the failure without missing telemetry.

**Hint:** Record outcome/metrics/JFR event in `catch/finally`, then rethrow/propagate the exception or complete a `CompletableFuture` exceptionally per contract. Ensure you do not emit two terminal events.

### Exercise E — JFR Missing Two Events

You enable `threshold=100 ms` while simulated work is only around 30 ms. The JFR file shows 0 `demo.WorkTask` events even though `finished=4`. Is this a lost task?

**Answer:** Not necessarily. `threshold` filters by the event's intrinsic duration. All tasks may have completed and simply been filtered out. Check `enabled`, recording window, and event settings before concluding telemetry is broken.

### Exercise F — Reading Stack Traces

Change `withoutStackTrace()` to `withStackTrace()` in the recording, then inspect `getStackTrace()` or JMC. Why is an event's stack not by default a full request trace?

**Hint:** A stack only reflects the call stack at the point JFR captured the event, without covering every service hop or thread handoff. Trace IDs and distributed tracing are needed for the full causal path.

### Exercise G — Same Thread Name on Two Pods

Two replicas both have `diag-worker-1`. How do you match events to the right instance?

**Answer:** Add pod/container identity, process start time, PID/host namespace, JFR file/recording ID, timestamp, and `taskId/traceId`. Thread name is not a global key.

## 16. Practice Completion Checklist

- [ ] File `ThreadMetricsJfrLab.java` compiles with `javac --release 17`.
- [ ] A `ThreadFactory` is used to name workers `diag-worker-1`/`diag-worker-2`.
- [ ] An `ExecutorService` with two workers exists and cleans up via `shutdown`/`awaitTermination`.
- [ ] Submitted/finished/successes/failures counters are consistent after Futures complete.
- [ ] The `active` gauge increments on start and decrements in `finally`, returning to 0 at program end.
- [ ] `peakActive` is updated atomically and does not exceed pool size in the demo.
- [ ] Queue/work durations use `System.nanoTime()` in the same JVM, in nanoseconds.
- [ ] Custom event has appropriate `@Name`, `@Category`, `@Label`, and `@Timespan`.
- [ ] `Event.begin()`, `end()`, and `commit()` are called in proper order with outcome set on the error path.
- [ ] Recording enables `demo.WorkTask` with a threshold low enough to keep demo events.
- [ ] File `thread-metrics-lab.jfr` is dumped and read back using `RecordingFile`.
- [ ] Intrinsic event duration is distinguished from the application's own `queueNanos`.
- [ ] `jfr summary` reports 4 `demo.WorkTask` events when the demo runs properly.
- [ ] Final output is `checks=PASS`; nanosecond values and worker mappings are not hardcoded.
- [ ] Metric label cardinality, JFR privacy, and differences between lab and production are understood.
- [ ] Able to correlate task events with runtime GC/CPU/thread events if those JVM events are captured.

**Key takeaway:** Thread names answer **which worker**; counters/gauges/timers answer **how many, how many running, how long waiting and processing**; custom JFR events answer **what outcome and duration each specific task had during JVM execution**. All three sources complement one another. In real deployments, keep correlation IDs, time units, lifecycles, and recording settings consistent to avoid false conclusions.

## References

- Oracle Java 17 — [`ThreadFactory` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadFactory.html): how to create and name workers.
- Oracle Java 17 — [`Executors` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executors.html): fixed thread pools, thread factories, and how executors manage tasks.
- Oracle Java 17 — [`LongAdder` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): counters under concurrency and limitations of `sum()`.
- Oracle Java 17 — [`System.nanoTime()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()): elapsed time measurement.
- Oracle JDK 21 — [`jdk.jfr.Event` API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Event.html): `begin`, `end`, `commit`, and capturing custom events.
- Oracle JDK 21 — [`Recording` API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html): enabling events, start/stop/dump.
- Oracle JDK 21 — [`@Timespan` API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Timespan.html): declaring units for duration fields.
- Oracle JDK 21 — [`RecordingFile` API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): reading events from `.jfr` files.
- Oracle JDK 21 — [`RecordedEvent` API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html): type, fields, duration, thread metadata.
- Oracle JDK 21 — [`jfr` CLI](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): `summary`, `print`, `metadata`.
- Oracle JDK 21 — [`jcmd` CLI](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `Thread.print` and JFR diagnostics.