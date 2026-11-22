# Summary Checklist: Thread Safety, Cancellation, Observability

> Scope: concurrency in **Java SE 17+**. This is a practical checklist for designing, reviewing, testing, and operating concurrent code using `Thread`, `ExecutorService`, `Future`, `Lock`, `java.util.concurrent` classes, and JVM monitoring APIs. The concepts apply to Java in general, independent of Spring.

## 1. Goal: When Is a Concurrent Task Considered "Correct"?

A program may produce the right answer in a few runs and still be wrong regarding concurrency: results can be corrupted when multiple threads access them simultaneously, a task may be cancelled without stopping, or an incident may occur with no information to trace it.

Three pillars must be verified **at the same time**:

| Pillar | Question to Answer | Acceptance Evidence |
| --- | --- | --- |
| **Thread safety** | Are there data races, lost updates, reads of unsafely published state, or violated invariants? | State ownership diagram; happens-before mechanisms; invariant tests under contention |
| **Cancellation** | Who has the authority to cancel, across which layers is cancellation propagated, does work stop and release resources? | Interrupt/deadline policy; tests for cancel before, during, and after execution; cleanup completion signal |
| **Observability** | When slow/hung/failing, can you tell where the task is, how long it waited, why it was cancelled, and whether workers are still alive? | Metrics, logs, scenario-based thread dumps/JFR, with correlation and without exposing sensitive data |

It is **not enough** to just say "used `AtomicInteger`", "called `future.cancel(true)`", or "added logs". You must verify **the entire lifecycle**: task creation → acceptance → queueing → start → execution → completion/failure/cancellation → cleanup → worker/executor shutdown.

## 2. Thread Safety Checklist: Identify State, Ownership, and Visibility

### 2.1. Identify Shared Mutable State

- [ ] List all data that can be **read/written by multiple threads**: fields, caches, collections, counters, connections/sessions, queues, flags.
- [ ] Distinguish between **thread-confined** (owned by only one thread), **immutable** (unchangeable after construction), and **shared mutable**.
- [ ] Every piece of shared mutable data has a clear protection policy: lock, atomic, concurrent collection, message passing, or ownership transfer.
- [ ] Do not expose a newly created object to another thread before the object is fully constructed and **safe publication** is complete.
- [ ] Every compound action such as "check-then-act", "read-modify-write", or "withdraw if balance is sufficient" is protected **atomically as a whole**, not just each individual step.
- [ ] Methods that invoke external callbacks do not run under an overly broad lock if the callback can block or call back in (reentrant).
- [ ] Lock acquisition order for multiple locks is defined to avoid circular waiting; avoid holding locks during slow I/O calls whenever possible.

**Example of a lost update bug:**

```java
// Two threads executing concurrently can cause a lost update.
private int completed;
void markDone() {
    completed++; // read → increment → write, not atomic
}
```

If the requirement is only an independent counter:

```java
private final AtomicInteger completed = new AtomicInteger();
void markDone() {
    completed.incrementAndGet();
}
```

The two snippets above are **illustrative code inside a class**, not standalone programs. You need to import `java.util.concurrent.atomic.AtomicInteger`. When you need to update **multiple fields that must stay consistent with one another**, do not assume replacing each field with an atomic is sufficient.

### 2.2. What Are `volatile`, Atomics, and Locks Used For?

| Tool | Used For | Does Not Solve by Itself |
| --- | --- | --- |
| `volatile` | Status flags, publication/visibility for a single variable; happens-before relationship between matching volatile write and read | `count++` or multi-field invariants |
| `AtomicInteger`, `AtomicReference` | CAS, get/set, atomic update operations on a single variable | Transactions across multiple atomics |
| `synchronized` / `ReentrantLock` | Protecting critical sections and multi-step invariants | Performance when holding locks for long; deadlocks if lock ordering is wrong |
| `ConcurrentHashMap` | Concurrent map access and atomic operations provided by the API | Multi-step workflows outside the map without coordination |
| `BlockingQueue` | Thread-safe producer–consumer data transfer and bounding the number of queued items | Deadlines, total work limits, business error handling |
| `CountDownLatch`, `Semaphore` | Coordinating lifecycle/work counts | Replacing locks for all application invariants |
| Immutable object | Sharing unmodifiable state | Safe publication of nested mutable objects |

**Happens-before** is the Java Memory Model rule governing ordering and visibility. For example: unlocking a monitor happens-before the next lock of the same monitor; writing to a `volatile` variable happens-before the next read of that variable; actions before `CountDownLatch.countDown()` are visible to the thread that passes the corresponding `await()`. Calling `Thread.sleep()` **does not establish a happens-before relationship** just because it waited long enough.

### 2.3. Analyze Ownership at Async Boundaries

An easily overlooked case: a method running on a caller thread creates an object and passes it into `executor.submit(...)`. According to the memory-consistency contract of `ExecutorService`, actions prior to submission happen-before actions in the task; and actions of the task happen-before code following the corresponding `Future.get()` return. This **does not** make a collection that the caller continues to mutate in parallel automatically thread-safe.

Anti-pattern example:

```java
List<String> shared = new ArrayList<>();
executor.submit(() -> shared.add("worker"));
shared.add("caller"); // may run concurrently, ArrayList is not thread-safe
```

This is an illustrative snippet; it requires importing `java.util.ArrayList` and `java.util.List` along with an active `executor` variable. The fix depends on requirements: have only one thread own the collection, return the result via `Future`, use an appropriate concurrent collection, or protect **all** accesses with the same lock.

## 3. Cancellation Checklist: Clear and Time-Bounded Cancellation Contract

### 3.1. Separate Cancellation Request from Confirmation That the Task Stopped

- [ ] Define who can request cancellation: caller, supervisor, timeout, shutdown, or business rule.
- [ ] Distinguish between "**cancellation requested**", "**Future marked cancelled**", and "**task code has actually stopped and finished cleanup**".
- [ ] If a running task needs to be stopped, use `Future.cancel(true)` when appropriate, but treat interrupt as a **cooperative request**, not a forced kill command.
- [ ] Long-running loops have check points for cancellation flags / interrupts, and blocking calls have an exit path.
- [ ] When catching `InterruptedException`, usually **exit or propagate**; if not rethrowing, restore the flag via `Thread.currentThread().interrupt()`.
- [ ] Do not `catch(Exception)` and keep looping indefinitely, accidentally swallowing `InterruptedException`.
- [ ] Resources are released in `finally` or `try-with-resources`, even when an exception/cancellation occurs.
- [ ] A timeout on *waiting for a result* does not automatically cancel the running work: have a separate action for still-alive tasks.
- [ ] Do not promise that cancel stops every I/O API immediately: it depends on the interruptibility of the specific API and driver.
- [ ] After shutdown, have a policy to wait for a bounded duration, record remaining tasks, and handle them safely.

**`Future` Contract:**

- `cancel(false)` attempts to cancel the task without requesting an interrupt on an already-executing task.
- `cancel(true)` attempts to cancel the task and requests an interrupt on the executing thread **if the thread is known**; the task may ignore the interrupt or take a long time to clean up.
- `isCancelled()` indicates the cancellation state of the `Future`; `isDone()` returns `true` upon normal completion, error, or cancellation.
- `get()` on a cancelled `Future` throws `CancellationException`.
- `get(timeout, unit)` throws `TimeoutException` when expired, **without automatically calling `cancel()`**.
- `cancel(true)` returning `true` is not sufficient proof that cleanup has finished. A dedicated completion/termination mechanism is required if the application demands that guarantee.

### 3.2. Interrupt Handling Policy

For tasks sleeping or waiting on `BlockingQueue.take()`, `CountDownLatch.await()`, or `Thread.sleep()`, an interrupt typically triggers `InterruptedException`. This exception normally **clears the interrupt status** before being caught. If the task cannot declare `throws InterruptedException`, catching it, restoring the flag, and exiting is a reasonable choice:

```java
try {
    queue.take();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
```

The snippet above is an illustration inside a method, where `queue` is a valid `BlockingQueue`. Distinguish cancellation from cases where the application wants to retry: do not retry infinitely after an interrupt, as that can prevent the task from ever stopping. For APIs that do not support interruption, design an additional deadline, close the socket/channel if supported, or use a cancellation flag with reasonable polling intervals.

### 3.3. Shutting Down the Executor Properly

`ExecutorService.shutdown()` stops accepting new tasks and allows already-accepted tasks to continue processing; it **does not wait automatically**. `shutdownNow()` attempts to interrupt running tasks and returns the list of tasks that have not started, but does not guarantee all tasks terminate. `awaitTermination(timeout, unit)` waits up to a bounded time limit. For critical work, decide how to handle unstarted tasks: mark them failed, persist them durably, or notify the caller, depending on business requirements.

Ensure cleanup follows a clear order:

```text
Cancellation / shutdown requested
   ↓
Stop accepting new tasks
   ↓
Propagate interrupt/deadline to appropriate tasks
   ↓
Task exits loop, runs finally, releases resources
   ↓
Observe task stopped + executor terminated
   ↓
Report result / update final state
```

The policy differs between **graceful shutdown** (prioritizes finishing accepted work) and **forced cancellation** (prioritizes stopping as soon as possible). Choose explicitly before going to production.

## 4. Observability Checklist: Know What the System Is Doing

### 4.1. Contextual Logging

- [ ] Log at least the meaningful lifecycle events: submit/accepted, started, completed, failed, cancel requested, cancel observed, timeout, rejected.
- [ ] Every important task has a stable **task ID / correlation ID** from creation through completion.
- [ ] Logs clearly indicate **status** and **reason** (e.g., timeout, shutdown, upstream error), rather than just printing `Exception.toString()`.
- [ ] Errors include stack traces at the right point; do not silently drop errors during asynchronous execution.
- [ ] Give threads/pools meaningful names; avoid relying on thread names as the unique identifier of a task.
- [ ] Do not log sensitive payloads, secret keys, or personal data in logs or thread names.
- [ ] Limit per-item logging under high load to prevent logging from saturating I/O.

With `ExecutorService.submit()`, exceptions from `Callable`/`Runnable` are captured inside the `Future`; if `get()` is never called or there is no other failure observation path, errors can be **missed** in monitoring. `execute()` and `submit()` have different error-propagation behaviors, so choose an appropriate collection path.

### 4.2. Essential Metrics to Distinguish Bottlenecks

| Group | Metric | Used to Answer |
| --- | --- | --- |
| Lifecycle | submitted / accepted / started / completed / failed / cancelled / rejected | At which stage is work being lost or stopped? |
| Timing | queue wait, execution time, total latency, timeout rate | Is the delay from queueing or execution? |
| Pool | active threads, pool size, queue size, completed task count | Are workers saturated? |
| Contention | contention/blocked time, deadlock observations | Are threads waiting on each other for locks? |
| Resources | CPU, heap, GC, connection/FD usage | Is the limit hardware/runtime or business logic? |

Counters must have **non-overlapping definitions**. For example, `submitted` counts requests sent to the executor; `accepted` counts only tasks accepted by the executor; `rejected` counts those rejected by the pool. An accepted task can still be cancelled before running. Do not infer `completed = submitted - rejected - cancelled` without clearly defining completion timing, retries, caller-runs execution, and tasks dropped by a discard policy.

Use `System.nanoTime()` to measure **duration** by taking the difference of two readings; do not use its absolute value as a timestamp or add a duration to an epoch time. Measure p50/p95/p99 instead of only averages; saturation can spike tail latency even while average throughput still looks relatively good.

Getters such as `ThreadPoolExecutor.getActiveCount()`, `getQueue().size()`, and `getCompletedTaskCount()` are **approximate** snapshots, not atomic readings of a single instant. Use them for trends, not as business conditions like "if queue size is 1, submit will definitely be accepted".

### 4.3. When to Take Thread Dumps and JFR?

- **Thread dump:** slow/hung system, many `BLOCKED` threads, suspected deadlock, workers waiting on `Future.get()`, or tasks waiting in a queue. Use `jcmd <pid> Thread.print -l -e`; `jstack -l <pid>` can also be used on supported JDKs.
- **`ThreadMXBean`:** inspect platform thread states and some CPU/blocked time metrics; check `isThreadCpuTimeSupported()` and `isThreadContentionMonitoringSupported()` before enabling features with overhead.
- **Java Flight Recorder (JFR):** inspect trends and time-series events to investigate contention, CPU, allocation, or pauses at appropriate points; choose recording profiles and durations according to operational cost.
- **Heap/GC metrics:** when a growing queue retains many `Runnable` instances or closure objects, check heap and GC pressure rather than just increasing pool size.

A dump is a **snapshot**: `WAITING` may simply mean an idle worker, `RUNNABLE` does not necessarily mean active CPU usage, and `BLOCKED` reflects waiting on an intrinsic monitor rather than covering all `ReentrantLock` contention. Take multiple samples over an appropriate interval and correlate them with progress metrics.

**Java 21 and virtual threads:** standard `ThreadMXBean` manages platform threads and does not enumerate all virtual threads. Therefore `getThreadCount()` and `findDeadlockedThreads()` are insufficient for diagnosing total counts or cycles involving virtual threads. When an application uses virtual threads, verify dump/JFR tools compatible with the **actual JDK version**. The runnable example in this article uses Java 17 and regular platform threads.

## 5. Runnable Example: Safe Cancellation and Verifying Cleanup

The following exercise uses **one worker**, two wait signals, and atomic counters. The task signals that it has started, then waits on a latch that is never released. The caller invokes `Future.cancel(true)`. The task observes the interrupt, performs cleanup, updates metrics, and exits. We wait on `finished` before asserting cleanup to avoid drawing premature conclusions from `Future.isDone()` alone.

Save as **`CancellationObservationDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class CancellationObservationDemo {
    static final class BlockingJob implements Runnable {
        final CountDownLatch started = new CountDownLatch(1);
        final CountDownLatch waitForRelease = new CountDownLatch(1);
        final CountDownLatch finished = new CountDownLatch(1);
        final AtomicBoolean interruptObserved = new AtomicBoolean();
        final AtomicInteger cleanupCount = new AtomicInteger();

        @Override
        public void run() {
            try {
                started.countDown();
                waitForRelease.await();
            } catch (InterruptedException e) {
                interruptObserved.set(true);
                Thread.currentThread().interrupt();
            } finally {
                cleanupCount.incrementAndGet();
                finished.countDown();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor(
                r -> new Thread(r, "review-worker"));
        BlockingJob job = new BlockingJob();
        try {
            Future<?> result = executor.submit(job);
            if (!job.started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Job did not start");
            }

            boolean cancellationAccepted = result.cancel(true);
            if (!job.finished.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Job did not clean up");
            }

            System.out.println("cancellationAccepted=" + cancellationAccepted);
            System.out.println("futureCancelled=" + result.isCancelled());
            System.out.println("interruptObserved=" + job.interruptObserved.get());
            System.out.println("cleanupCount=" + job.cleanupCount.get());
        } finally {
            executor.shutdownNow();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Executor did not terminate");
            }
        }
    }
}
```

Run on JDK 17+:

```bash
javac CancellationObservationDemo.java
java CancellationObservationDemo
```

Stdout (verified with OpenJDK 24, using only APIs available in Java 17):

```text
cancellationAccepted=true
futureCancelled=true
interruptObserved=true
cleanupCount=1
```

### 5.1. Why Does the Example Avoid Races in Verification?

1. `started.countDown()` signals that the worker has started. `started.await()` on the caller ensures the task has entered `run()` before the caller attempts to cancel.
2. `waitForRelease.await()` is never released normally. Whether the interrupt arrives right before or during the `await()` call, the task has an exit path via `InterruptedException`.
3. `cancel(true)` attempts to interrupt the worker. If the task is still active, the flag is observed in `catch`; the `finally` branch executes and counts down `finished`.
4. The caller waits for `finished.await()` to succeed before reading `interruptObserved` and `cleanupCount`. This proves cleanup ran **in the example**, rather than inferring it from `Future.isDone()`.
5. `AtomicBoolean` and `AtomicInteger` represent metrics safely across threads; the latches also establish happens-before relationships via `countDown`/`await`.
6. The `finally` block in `main` runs `shutdownNow()` and waits for executor termination to prevent worker leaks when tests fail.

In a real application, `waitForRelease` is a bounded-condition resource or operation; a permanently closed latch is only used to create a deterministic test scenario. If `await()` times out, the program throws a clear error instead of recording the result as successful. When multiple tasks run concurrently, manage cancellation ownership to avoid one caller accidentally cancelling another caller's task.

### 5.2. What the Example Does **Not** Prove

- `Future.cancel(true)` does not guarantee every task receives an interrupt: a task may run non-interruptible I/O or swallow interrupts itself.
- `cleanupCount=1` does not prove external resources were closed; you must verify specific close/commit/rollback calls.
- Per-field atomic counters do not form a consistent snapshot across dozens of metrics. Use an immutable snapshot under a lock when multi-field invariants are required.
- `newSingleThreadExecutor` uses an effectively unbounded queue: only suitable for small demos with controlled work counts. Applications under continuous load should consider bounded queues, admission control, and rejection policies with feedback.
- The program does not provide distributed tracing or log aggregation by itself; that is the responsibility of the operational environment.

## 6. Testing Checklist: From Invariants to Cancellation Races

| Scenario | Controlled Setup | What to Assert |
| --- | --- | --- |
| Lost update | Multiple tasks increment a counter concurrently, waiting on a `CountDownLatch` start gate | Final total equals the exact number of increments |
| Compound invariant | Multiple threads transfer values between two fields | Total sum is conserved and no invalid intermediate state appears in snapshots |
| Safe publication | Task is submitted after object configuration is complete | No stale or uninitialized configuration is read |
| Cancel before execution | Keep worker busy, submit new task, then cancel the waiting task's `Future` | Task body does not execute, status is cancelled |
| Cancel while waiting | Task is in `BlockingQueue.take()`/`await()`, call `cancel(true)` | Task observes interrupt, cleans up, and stops |
| Cancel after completion | `Future.get()` succeeds, then call `cancel(true)` | `cancel` does not turn a completed task into cancelled |
| Timeout without cancel | `get(timeout)` on a waiting task | `TimeoutException`; task may still be running |
| Exception in task | `Callable` throws exception, caller calls `get()` | `ExecutionException` contains the cause |
| Shutdown | Shut down executor while tasks are active | No new tasks accepted; running tasks have clear lifecycle and deadline |
| Saturation | Workers busy and bounded queue full | Rejections are handled/counted; no tasks silently lost |
| Observability | Assign task ID, induce failure/cancellation | Logs/metrics match the execution path, no sensitive data leaked |

### 6.1. Making Concurrency Tests Reliable

Use `CountDownLatch`, `CyclicBarrier`, `Phaser`, or appropriate primitives to align the exact contention point. `Thread.sleep(100)` only adds delay and **does not guarantee** two threads touch the same data concurrently. Add finite timeouts to all wait operations in tests; on timeout, fail the test and clean up the executor in `finally`.

Tests must verify **invariants and actual outcomes**; running 1,000 iterations cannot prove a program is free of data races. Stress tests are useful for uncovering races, but they do not replace reasoning about the JMM, ownership, safe publication, and atomicity.

An effective strategy is to design pure computation independently of scheduling, and then test concurrency only at shared-state/cancellation boundaries. Avoid making tests depend on thread names, scheduling order, or log ordering that lacks a happens-before relationship.

### 6.2. Testing Failure Paths Also Needs Observability

If a task throws an exception during cleanup, application policy must decide which final error is returned to the caller and where secondary errors are recorded. Never swallow exceptions just to make a test pass "green". When a task is cancelled, distinguish **cancel requested** from **cleanup completed** in metrics; looking only at `Future.isCancelled()` can misrepresent how long resources remain held.

With `CompletionService` or `CompletableFuture`, verify that completion handlers cover results, exceptions, and cancellation. Inside async callbacks, avoid performing long blocking operations on a shared executor if that could lead to starvation.

## 7. Pre-Merge Design Review Checklist

### 7.1. Thread Safety — Mandatory Questions

- [ ] I know which thread creates, reads, modifies, and destroys each piece of state.
- [ ] No `ArrayList`, `HashMap`, or mutable field is updated by multiple threads without protection.
- [ ] Object publication paths, `Future.get()`, and synchronization all have explicit happens-before guarantees.
- [ ] Every multi-step invariant is protected by a consistent mechanism.
- [ ] No locks are held during slow I/O or uncontrolled callbacks; lock acquisition order is clear.
- [ ] "Thread-safe" is not inferred merely from passing a test once.

### 7.2. Cancellation — Mandatory Questions

- [ ] The owner and cancellation authority for tasks/pools are defined.
- [ ] Timeout, exception, shutdown, and explicit cancel are clearly distinguished.
- [ ] Tasks cooperate with interrupts/deadlines; interrupts are not swallowed.
- [ ] Resources are cleaned up whether the task succeeds, fails, or is cancelled.
- [ ] Callers can receive the final result or appropriate failure reason.
- [ ] If confirmation that a task stopped is required, a separate completion signal exists; do not rely solely on `Future.isDone()`.
- [ ] The executor is shut down and awaited for termination with an appropriate deadline.

### 7.3. Observability — Mandatory Questions

- [ ] Task identifiers, useful pool/thread names, and start/end status logs are present.
- [ ] Counters for accepted/completed/failed/cancelled/rejected exist with clear definitions.
- [ ] Queue wait, execution time, timeouts, and tail latency are measured under load.
- [ ] There is a way to capture thread dumps/JFR and inspect lock contention during incidents.
- [ ] Metrics/logging overhead and sensitive data exposure are controlled.
- [ ] Dashboards/alerts distinguish temporary backlogs from sustained saturation.

**Acceptance criterion:** another reviewer can describe *what state is shared, by what mechanism it is cancelled, what signal must be observed after cancellation, and what evidence to collect when the system stops making progress* without having to guess from method names.

## 8. Applied Scenario: Workers Processing Tasks from a Queue

Suppose a Java service receives events from a producer, submits them to a `ThreadPoolExecutor`, and workers update state and call an external system. The three pillars connect directly:

| Symptom | Thread Safety | Cancellation | Observability |
| --- | --- | --- | --- |
| Producer sends duplicate events | Processing/idempotency state is safe under contention | Cancel duplicates that are no longer needed per policy | Count duplicates and skipped outcomes |
| Worker holds lock during I/O call | May block other threads waiting on the lock | Interrupt may not stop I/O immediately | Thread dump, blocked time, dependency latency |
| Queue grows continuously | Queue is structurally sound but does not create throughput | Deadlines expire stale tasks that are no longer valuable | Queue wait p95/p99, active count, rejected |
| Caller times out then retries | May process the same work twice | Decide whether to cancel the original task or let it continue | Correlation ID, timeout, retry count |
| Shutdown in progress | Closing state must be safely published | Stop accepting new work and handle live tasks | Outstanding, cleanup completed, termination |

A sound baseline operational design includes a **bounded** queue, explicit rejection feedback, timeouts for external I/O, owned cancel/shutdown states, and per-stage metrics. Specific thread/queue sizing must go through load testing; simply increasing queue size can cause tasks to complete past their deadlines and increase retained memory.

## 9. Mistakes Often Missed in Checklists

**1. "Using a concurrent collection makes every workflow safe."** A `ConcurrentHashMap` protects individual API operations; a "check absent → call I/O → write to map" flow can still run twice. You need `computeIfAbsent`, locks, single-flight, or transactional/idempotent design as required.

**2. "`volatile` makes variable increments atomic."** `volatile int count` does not make `count++` atomic; use `AtomicInteger.incrementAndGet()` or a lock.

**3. "`cancel(true)` means the task has exited."** It requests cancellation and may interrupt. The `Future` can transition to cancelled before the task's `finally` block finishes; proving cleanup requires waiting separately.

**4. "A `get` timeout automatically cancels the task."** No. The caller must decide whether to call `cancel` and how to handle the still-running task.

**5. "Catching all `Exception`s and continuing is resilient."** It can swallow `InterruptedException`, causing shutdown to hang; catch blocks must have an explicit retry/exit policy.

**6. "`shutdownNow()` kills all threads."** It only attempts to interrupt. If a task ignores interrupts, there is no guarantee it stops immediately; a deadline/resource contract is needed.

**7. "Having a completed counter metric is enough."** That counter misses tasks queued, timed out, rejected, or cancelled before running. Lifecycle stages must be observed.

**8. "A thread dump with many `WAITING` threads is a deadlock."** Idle thread pool workers waiting on a queue are completely normal. Deadlocks require analyzing lock ownership/wait cycles and consecutive samples.

**9. "Queue size zero means no overload."** `SynchronousQueue` stores no elements, yet the pool can still saturate and reject many tasks. Also monitor active count, completions, rejections, and caller latency.

**10. "`ThreadMXBean` sees every thread in every JDK."** Java 21 does not monitor virtual threads through this standard API; check your JVM version and available diagnostic tools.

## 10. End-of-Article Mini Review

Answer these yourself before considering a concurrency feature ready:

1. If two workers modify an object concurrently, **which mechanism protects the invariant** and where is the happens-before proof?
2. If a request times out while a task is still doing I/O, **who requests cancellation**, how does the task find out, and when are resources released?
3. If `Future.isCancelled()` is already `true`, is there enough evidence to conclude `finally` has finished running?
4. If a pool has 8 busy workers and 500 waiting tasks, **which numbers** represent queue length, active work, and when rejection occurs?
5. If p99 latency increases today while throughput drops, **which metrics and dumps** tell you whether the cause is queue wait, contention, GC, or downstream?
6. If using virtual threads on JDK 21, why is `ThreadMXBean.getThreadCount()` not the total thread count of the application?
7. If a reviewer only has a test that sleeps 100 ms and then asserts the result, how do you convert it into a test with condition synchronization and explicit timeouts?

A reliable design must answer all three groups: **state safety**, **controlled task termination**, and **observable evidence when things go wrong**.

## 11. Official Java Documentation

- [Java Language Specification §17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html)
- [ExecutorService — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Future — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html)
- [ThreadPoolExecutor — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [CountDownLatch — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [ThreadMXBean — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html)
- [jcmd — JDK 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
