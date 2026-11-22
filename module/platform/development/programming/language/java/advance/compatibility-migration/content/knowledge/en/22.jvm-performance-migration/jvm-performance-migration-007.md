# Verifying Concurrent Tasks When Changing the JVM or Concurrency Libraries

A Java system can compile cleanly when upgrading from JDK 8 to 11, 17, or 21 yet still suffer elusive failures: lost updates, duplicate processing of the same request, hanging tasks, latency spikes, or wrong results appearing only under heavy load. In particular, when upgrading asynchronous execution libraries, changing thread pools, updating reactive frameworks, or adopting virtual threads, **task scheduling order can change** even when business logic stays practically unchanged.

Therefore, verifying concurrency in Java Advance Compatibility Migration is more than running a few tasks without exceptions. You must simultaneously verify **correctness (safety)**, **progress to completion (liveness)**, **load handling (throughput/latency)**, and **observability, cancellation, and recovery** on the new JDK and library environment.

This lesson belongs to the **JVM and Performance** chapter and focuses on establishing baselines, designing reproducible tests, catching regressions from shifted interleavings, and verifying real behavior when swapping JVMs or concurrency libraries. Examples use Java/JUnit and common concurrency APIs; the same principles apply to executors, schedulers, reactive pipelines, and other task-processing platforms.

## 1. What Does Concurrency Verification Actually Test?

### 1.1. Four Quality Axes to Separate

| Axis | Question to Answer | Failure Examples |
| --- | --- | --- |
| **Safety** | Do results and business invariants always remain valid? | Two workers decrement a balance concurrently causing a lost update; processing an event twice. |
| **Liveness** | Do tasks make progress and finish when conditions allow? | Deadlock; a `Future` waiting forever; task starvation. |
| **Performance** | Under equal load, how do throughput, latency, and resources shift? | p99 climbs from thread-pool queueing; higher GC; high CPU yet lower throughput. |
| **Operability** | Can tasks be stopped, cancelled, observed, and recovered? | Shutdown hangs; interrupts get swallowed; missing queue metrics or traces. |

Passing safety tests does not prove a system cannot deadlock. Conversely, higher throughput does not prove zero lost updates. Report each axis independently in migration reports.

### 1.2. Why Can Changing the JDK or Libraries Expose "Old" Bugs?

An application containing a data race may appear stable in one environment purely by scheduling luck. After migration, the following shifts alter interleavings:

- Different JIT compilers, garbage collectors, or CPU architectures.
- Different CPU counts reported to the JVM inside containers, shifting default pool sizes.
- Newer library versions changing executors, queues, timeouts, batching, or callback scheduling.
- Reactive schedulers switching callbacks onto different threads without propagating legacy contexts.
- Workloads mixing more concurrent tasks or blocking operations.
- Async API upgrades changing completion ordering or exception propagation.
- Virtual threads (Java 21+) changing thread creation models for I/O-bound tasks.

**Key distinction:** A new JDK does not necessarily create bugs. It may expose an existing concurrency assumption invalid under the Java Memory Model. On the other hand, a library may genuinely alter its contracts, default executors, or cancellation behavior. Base conclusions on evidence rather than blaming every failure on the new scheduler.

## 2. Capturing a Baseline Before Changing the JVM or Dependencies

### 2.1. Anchor the Baseline to Exact Configuration

Record at minimum:

- Exact JDK vendor, full version, and runtime JDK executing the application.
- OS, CPU architecture, JVM-visible processor count, and container CPU/memory quotas.
- JVM flags covering GC, heap, container awareness, and thread scheduling.
- Versions of concurrency libraries, frameworks, reactive runtimes, and transitive dependencies.
- Thread pool config: core/max sizes, queue type/capacity, keep-alive, and rejection policy.
- Workload profile: concurrent requests/tasks, CPU-bound vs. I/O-bound mix, payloads, and downstream latency distribution.
- Timeouts, retries, backoff, idempotency, and shutdown policies.
- Metrics and traces under normal and peak load.
- Existing test/benchmark reports: completed counts, errors, p50/p95/p99, known deadlocks/leaks.

For instance, a service may construct `Executors.newFixedThreadPool(16)` while `CompletableFuture.supplyAsync(...)` silently uses `ForkJoinPool.commonPool()` when no executor argument is passed. Document both **explicit and implicit executors**.

### 2.2. Build a Before/After Matrix

| Sample | JDK | Concurrency Library | Workload | Goal |
| --- | --- | --- | --- | --- |
| A – baseline | Old JDK | Old lib | Controlled load | Establish current behavior and metrics. |
| B – JDK only changed | Target JDK | Old lib (if supported) | Identical load | Isolate JVM effects. |
| C – lib only changed | Supported JDK | New lib | Identical load | Isolate library effects. |
| D – target pair | Target JDK | New lib | Identical load | Validate production target configuration. |

Not every cell is vendor-supported. If B or C is invalid, **do not force running unsupported setups to draw compatibility claims**. Step through supported upgrade stages instead and document comparison limits.

### 2.3. Assert Invariants Rather Than "Fixed Thread Order"

In concurrency, avoid tests expecting Thread A to always precede Thread B without a true happens-before guarantee. Assert invariants instead:

- Total persisted transactions match accepted successful transactions.
- Every task reaches a valid terminal state: completed, failed, or cancelled.
- Zero tasks linger in-flight past deadline expiration.
- Never allow two workers to hold the same exclusive lock/lease simultaneously.
- Retries produce zero duplicate side effects.
- Final business outcomes stay equivalent even when completion order varies.
- Queues and pending counts stay bounded by policy rather than growing unboundedly.

## 3. Java Memory Model: The Root of Hidden Bugs

### 3.1. Data Races and Visibility

Consider a counter:

```java
public final class UnsafeCounter {
    private int value;

    public void increment() {
        value++;
    }

    public int get() {
        return value;
    }
}
```

`value++` is a **read → add → write** sequence, not an atomic update. Two threads can read the same old value and write the same incremented value, causing a lost update.

Worse, without proper synchronization, other threads lack visibility guarantees for updates. A test can pass thousands of runs and still violate the Java Memory Model.

### 3.2. `volatile` Does Not Make Increments Atomic

`volatile` provides visibility and ordering guarantees under the Java Memory Model for individual accesses, yet never makes read-modify-write expressions atomic:

```java
private volatile int value;

void increment() {
    value++; // Still not atomic.
}
```

Spot this clearly during migration. Running a test more times may expose races more often; it never turns broken code into correct code.

### 3.3. Use Appropriate Synchronization Primitives

For simple counters:

```java
import java.util.concurrent.atomic.AtomicInteger;

public final class SafeCounter {
    private final AtomicInteger value = new AtomicInteger();

    public int incrementAndGet() {
        return value.incrementAndGet();
    }

    public int get() {
        return value.get();
    }
}
```

For multi-variable invariants, use `synchronized`, `Lock`, database transactions, or unshared state designs. Multiple separate `AtomicInteger` instances do not guarantee an invariant spanning **multiple fields updated together**.

### 3.4. Happens-Before Enables Reliable Observation

Common happens-before relationships in Java:

- Unlocking a monitor happens-before every subsequent lock of that same monitor.
- Writing to a `volatile` field happens-before subsequent reads respecting its synchronization order.
- Actions before calling `Thread.start()` happen-before actions inside the started thread.
- Actions inside a thread happen-before another thread returns successfully from `join()`.
- Task execution obeys memory-consistency contracts between submission and result retrieval via `ExecutorService`/`Future` APIs.
- `java.util.concurrent` primitives document their specific memory-consistency effects.

Rely on these guarantees when designing tests. Sleeping with `Thread.sleep(100)` **creates no happens-before edge** between producer and consumer and cannot verify visibility.

### 3.5. Safe Publication and Immutable Objects

If an object is shared across threads before construction completes, another thread may observe inconsistent state.

Prefer:

- Immutable objects with `final` fields and safe construction.
- Publication via concurrent collections, `volatile` references, locks, or thread-safe queues.
- Never leaking `this` from constructors before initialization finishes.
- Avoiding unsynchronized mutable singletons holding per-request data.

When upgrading DI frameworks or changing lifecycles, check whether objects get published earlier or accessed from more threads.

## 4. Concurrency APIs Prone to Behavioral Shifts During Migration

### 4.1. `ExecutorService` and `ThreadPoolExecutor`

`ThreadPoolExecutor` embodies critical design decisions:

- Core pool size and maximum pool size.
- Queue choice: bounded vs. unbounded.
- Keep-alive timeouts and thread factories.
- Rejected execution policy.
- Shutdown, interruption, and task draining behavior.
- How tasks handle blocking I/O.

Example pool with a bounded queue:

```java
import java.util.concurrent.*;

ExecutorService executor = new ThreadPoolExecutor(
        4,
        8,
        30,
        TimeUnit.SECONDS,
        new ArrayBlockingQueue<Runnable>(200),
        new ThreadPoolExecutor.AbortPolicy()
);
```

When full, `AbortPolicy` throws `RejectedExecutionException` instead of silently buffering unbounded work. That backpressure/rejection choice must align with your system's API contracts.

Conversely, an unbounded queue can accumulate huge task backlogs in memory and spike p99 latency before failures surface. Pool thread count alone cannot describe load capacity; **queue bounds and rejection policies matter equally**.

### 4.2. Framework Default Changes

Upgrading a framework can alter auto-configured executors:

- Default pool sizes.
- Thread naming conventions.
- Queue capacities.
- Fallback behavior when no custom executor bean is declared.
- Propagation of `ThreadLocal`, MDC, or security contexts.
- Timeout enforcement and exception handlers.

Verify **effective runtime configurations** rather than assuming legacy property files still match. A renamed or ignored property can leave frameworks on new defaults without obvious errors.

### 4.3. `CompletableFuture` and Implicit Executors

Example:

```java
CompletableFuture<Result> future =
        CompletableFuture.supplyAsync(() -> loadData());
```

Overloads without an explicit executor generally use `ForkJoinPool.commonPool()` under `CompletableFuture`'s contract, subject to runtime configuration. When resource isolation is needed, pass an explicit executor:

```java
CompletableFuture<Result> future =
        CompletableFuture.supplyAsync(
                () -> loadData(),
                ioExecutor
        );
```

Verify:

- `thenApply` may execute on either the completing thread or calling thread depending on completion timing; never equate it with `thenApplyAsync`.
- `thenApplyAsync` uses an executor per overload/contract, potentially switching threads unexpectedly.
- Exceptions wrap inside `CompletionException` on `join()` vs. `ExecutionException` on `get()`.
- Completion order across multiple futures does not equal submission order.
- Cancelling a `CompletableFuture` does not necessarily interrupt underlying background work.

When frameworks or libraries alter how futures compose, test **failure propagation, timeouts, and cancellation**—not merely happy paths.

### 4.4. `ForkJoinPool` and the Common Pool

`ForkJoinPool` targets forkable CPU work and commonly backs parallel streams and async APIs. Its work-stealing model differs from traditional fixed pools.

Key risks:

- Running long blocking I/O inside pools sized for CPU-bound work.
- Calling `parallelStream()` while relying on side-effect ordering.
- Sharing `ForkJoinPool.commonPool()` across unrelated features so one workload starves another.
- Assuming parallelism equals a fixed constant while container CPU counts change.

Never gauge health by total thread count alone. Monitor queue depths, blocked/parked threads, CPU usage, latency, and throughput.

### 4.5. `ScheduledExecutorService` and Timing

Periodic tasks can behave differently when:

- Hardware clocks or CPUs change.
- Executions take longer than the scheduled period.
- Timeouts confuse duration vs. deadline semantics.
- Frameworks swap default schedulers or task queues.
- Applications pause on GC or container CPU throttling.

Distinguish:

- `scheduleAtFixedRate`: schedules at a fixed cadence conceptually; concurrent executions of the same periodic task do not overlap under `ScheduledThreadPoolExecutor`'s contract.
- `scheduleWithFixedDelay`: waits a fixed delay *after* the previous run finishes.

Never assert exact millisecond wall-clock timestamps in scheduler tests. Check bounded time windows, expected execution counts, absence of unintended overlap, and clean shutdown stopping the scheduler.

### 4.6. Reactive Libraries and Schedulers

In Reactor, RxJava, or other reactive runtimes, tasks rarely map 1:1 with OS threads. Publish/subscribe schedulers, event loops, and backpressure govern where callbacks run.

Check upgrade migration guides for:

- Default schedulers and thread affinity.
- Blocking calls accidentally executing on non-blocking event-loop threads.
- Backpressure strategies, buffer caps, and overflow errors.
- Retry and timeout semantics.
- Cancellation signals when subscribers dispose early.
- Propagation of tracing, security, and MDC contexts.
- Operator ordering and terminal signal guarantees.

Never rely on `ThreadLocal` assuming callbacks stay on one thread. Use framework-supported context propagation and test live execution paths.

### 4.7. Virtual Threads Moving to Java 21+

Virtual threads became standard in Java 21. They enable lower-overhead thread-per-task scaling for I/O-blocking workloads than platform threads, yet **do not speed up CPU-bound computation**.

Java 21+ example:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

try (ExecutorService executor =
        Executors.newVirtualThreadPerTaskExecutor()) {
    for (int i = 0; i < 1000; i++) {
        executor.submit(() -> performBlockingIo());
    }
}
```

Verify carefully:

- Bounded **concurrency to external resources** remains mandatory: database pools, downstream HTTP endpoints, file descriptors, and rate limits stay finite even with abundant virtual threads.
- Do not remove a bounded pool that previously acted as a throttle without replacing it with a semaphore/bulkhead under thread-per-task.
- `ThreadLocal`, MDC, and request contexts can carry overhead or propagation issues depending on framework design.
- In Java 21, `synchronized` blocks and native/foreign calls can trigger carrier pinning; pinning behavior and observability tools evolve across newer JDKs, so verify on your **exact target JDK** rather than generalizing Java 21 caveats to all releases.
- Shutdown, interruption, deadlines, and exception handling still need clear contracts.
- Legacy blocking libraries can remain functionally compatible yet saturate downstream resource pools.

Virtual threads alter execution architecture; redesign concurrency and load tests around actual external resource bottlenecks.

## 5. Safety: Verifying Results and Invariants Under Contention

### 5.1. Lost Updates

Suppose two tasks increment a counter 1,000 times each; the right sum is 2,000. Unsynchronized `int value++` can finish with a lower value.

JUnit Jupiter test illustrating verified `AtomicInteger` usage:

```java
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.*;

class ConcurrentCounterTest {
    @Test
    void incrementsAreNotLost() throws Exception {
        int workers = 8;
        int perWorker = 1_000;
        AtomicInteger counter = new AtomicInteger();

        ExecutorService pool = Executors.newFixedThreadPool(workers);
        CountDownLatch ready = new CountDownLatch(workers);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<?>> futures = new ArrayList<>();

        try {
            for (int i = 0; i < workers; i++) {
                futures.add(pool.submit(() -> {
                    ready.countDown();
                    if (!start.await(5, TimeUnit.SECONDS)) {
                        throw new TimeoutException("Start signal missing");
                    }
                    for (int j = 0; j < perWorker; j++) {
                        counter.incrementAndGet();
                    }
                    return null;
                }));
            }

            assertTrue(ready.await(5, TimeUnit.SECONDS));
            start.countDown();

            for (Future<?> f : futures) {
                f.get(10, TimeUnit.SECONDS);
            }

            assertEquals(workers * perWorker, counter.get());
        } finally {
            start.countDown(); // Avoid leaving workers blocked if an assertion fails.
            pool.shutdownNow();
            assertTrue(pool.awaitTermination(10, TimeUnit.SECONDS));
        }
    }
}
```

Here `CountDownLatch` **increases contention by starting workers together**, without micro-controlling instruction order. This validates an essential invariant yet never proves an arbitrary lock-free algorithm holds across every interleaving.

You can run unsafe implementations through this same harness to hunt bugs, yet **never assert a race *must* reproduce on every run**: data races may pass intermittently.

### 5.2. Multi-Step Atomicity

Consider "check remaining seats then book":

```java
if (availableSeats.get() > 0) {
    availableSeats.decrementAndGet();
    issueTicket();
}
```

`AtomicInteger` makes each individual method atomic, **not the compound sequence check → decrement → side effect**. Two threads can both observe 1 seat left and both book it.

Sound fixes use CAS loops, locks, database transactions, atomic conditional updates in the data store, or serialized queues depending on system design. Tests should assert invariants like "never issue more tickets than capacity," not just call counts on `decrementAndGet`.

### 5.3. Concurrent Collections

Using `ConcurrentHashMap`, `ConcurrentLinkedQueue`, or `BlockingQueue` does not make compound logic around them atomic.

Unsafe compound sequence:

```java
if (!map.containsKey(key)) {
    map.put(key, createValue());
}
```

Multiple threads may execute `createValue()` concurrently. Under compatible contracts, use atomic operations like `computeIfAbsent`:

```java
Value value = map.computeIfAbsent(key, k -> createValue(k));
```

Note that `ConcurrentHashMap`'s mapping function imposes constraints regarding side effects, reentrancy, blocking, and exceptions. Never assume arbitrary callbacks execute exactly once across every setup, especially when mutating maps or combining retries at higher layers.

### 5.4. Business Task Idempotency

In message queues and background jobs, tasks can replay after timeouts or retries. JVM thread safety **cannot** guarantee idempotency for external side effects.

Tests should cover:

- Receiving duplicate events with identical IDs concurrently.
- Worker crashing between DB write and queue ack.
- Task timing out while downstream actually succeeded.
- Jobs resubmitted across process restarts.
- Ensuring customers are never double-charged or double-ordered.

Solutions require idempotency keys, unique database constraints, transactions, or the outbox pattern. Changing executors never fixes distributed business invariants.

## 6. Liveness: Deadlocks, Starvation, Livelocks, and Backlogs

### 6.1. Lock-Ordering Deadlocks

Two threads acquire locks in opposite orders:

```java
synchronized (lockA) {
    synchronized (lockB) {
        update();
    }
}

// Another code path:
synchronized (lockB) {
    synchronized (lockA) {
        update();
    }
}
```

When interleaved, one holds A waiting for B while the other holds B waiting for A. A bug hidden on an old JDK can surface frequently under new schedulers or loads.

Fix by enforcing a **strict global lock order**, shrinking lock scopes, avoiding alien callbacks inside locks, and using lock timeouts where appropriate.

### 6.2. Fixed Thread Pool Starvation

Suppose a 2-thread pool runs tasks that submit child tasks to **the very same pool** and block on `Future.get()`:

```java
ExecutorService pool = Executors.newFixedThreadPool(2);

Callable<String> outer = () -> {
    Future<String> inner =
            pool.submit(() -> "done");
    return inner.get();
};
```

If both workers execute `outer`, both block waiting for queued `inner` tasks while zero idle workers remain to run them. This is a **thread starvation deadlock** caused by cyclic pool waiting rather than Java monitor deadlocks.

Avoid blocking cycles inside bounded pools by separating executors, composing asynchronously, or redesigning non-blocking pipelines.

### 6.3. Livelocks and Retry Storms

Livelocks happen when threads keep executing without useful progress—for instance, workers repeatedly colliding, retrying immediately with zero backoff, and amplifying pressure without succeeding.

When upgrading retry or scheduling libraries, check:

- Are retries bounded with exponential backoff and jitter?
- Are transient errors distinguished from permanent errors?
- Is there an overall global deadline?
- Are bulkheads or rate limits protecting failing downstreams?
- Do metrics separate attempts, successes, and failures?

Rising retry attempt counts never indicate rising business throughput.

### 6.4. Queue Backlogs and Backpressure

Model the queue pipeline:

```text
Request arrival rate
        |
        v
Admission / rate limit
        |
        v
Executor queue  ---> Rejected / dropped / backpressure policy
        |
        v
Workers
        |
        v
Downstream DB / HTTP / filesystem
```

When arrival rates exceed sustainable processing capacity, queues grow. Upgrading dependencies can silently change defaults from bounded to unbounded queues, delaying failures while inflating memory and tail latency.

Define explicit overload policies: controlled rejection, bounded waits, load shedding, or upstream throttling. Load tests must verify **how the system degrades under overload**, not only steady-state load.

## 7. Cancellation, Interruption, and Shutdown

### 7.1. `Future.cancel(true)` Is Not "Kill Thread"

On `Future`, `cancel(true)` requests cancellation and may interrupt the executing thread. Timely exit depends on whether code and blocking/I/O operations respect interruption.

Never build business correctness assuming cancellation immediately halts every side effect.

### 7.2. Never Swallow `InterruptedException`

Common anti-pattern:

```java
try {
    blockingOperation();
} catch (InterruptedException e) {
    // Ignore and keep running.
}
```

If shutdown or cancellation was requested, swallowing interrupts keeps tasks running past deadlines. For interruptible workers:

```java
try {
    blockingOperation();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
```

If the method declares `throws InterruptedException`, propagate it instead of catching unnecessarily. Restoring the interrupt flag must pair with stopping or signaling callers—never re-enter infinite loops after restoring the flag without an exit condition.

### 7.3. Two-Phase Graceful Shutdown

For traditional `ExecutorService`s:

```java
static void shutdownGracefully(ExecutorService pool)
        throws InterruptedException {
    pool.shutdown(); // Reject new tasks.

    if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
        pool.shutdownNow(); // Request interrupts on running tasks.

        if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
            System.err.println("Executor chưa kết thúc");
        }
    }
}
```

Wrap this at the application layer to handle coordinator-thread interruption, in-flight request draining, open transactions, queues, and resource cleanup. `shutdownNow()` never guarantees instant termination; uninterruptible tasks can keep running.

### 7.4. Pass Deadlines Instead of Per-Step Timeouts

If a request carries a 2-second deadline and executes three sequential steps with independent 2-second timeouts, total latency can stretch to multiple seconds. Changing executors or pipelines often exposes broken timeout budgets.

Propagate **remaining time budgets** across steps using monotonic clocks (such as `System.nanoTime()` for elapsed duration) and keep cancellation propagation consistent.

Never measure elapsed durations with `System.currentTimeMillis()` in timeout-sensitive tests because wall clocks can jump.

## 8. Designing More Reliable Concurrency Tests

### 8.1. Do Not Coordinate Tasks with `Thread.sleep`

Tests like:

```java
startWorker();
Thread.sleep(100);
assertEquals(expected, state);
```

flake easily because 100 ms never proves a worker reached the expected point. Under CPU-throttled CI runners, JIT compilation, or GC, workers may lag behind; longer sleeps slow suites down without adding correctness.

Prefer:

- `CountDownLatch` to await readiness or trigger synchronized starts.
- `CyclicBarrier` or `Phaser` for multi-party synchronization steps.
- `BlockingQueue` to hand off events or outcomes.
- `Future.get(timeout, unit)` to await completion and capture exceptions.
- Test-only hooks/instrumentation to pause at critical boundaries.
- Controllable clocks/schedulers in time-based unit tests.

### 8.2. Start Barriers Do Not Fix Full Interleaving

Using `CountDownLatch` to release workers together triggers contention yet never determines instruction-by-instruction order. Never rely on unsynchronized scheduling order in tests.

To force specific interleavings, introduce test seams pausing before/after reads and writes via explicit barriers. For complex lock-free algorithms, consider dedicated stress harnesses or model checkers.

### 8.3. Always Surface Worker Exceptions to the Test Thread

Common bug:

```java
executor.submit(() -> {
    throw new IllegalStateException("Worker failed");
});

// Test thread finishes without calling Future.get().
```

With `submit`, uncaught exceptions get captured inside the returned `Future`. Failing to call `get()` or check completion causes **false passes**.

Keep references to every `Future` and call `get(timeout, unit)` so worker failures surface as `ExecutionException` with the real underlying cause.

### 8.4. Keep Timeouts Bounded and Clean Up Resources

Infinite waits on barriers hang CI builds. Always:

- Set bounded timeouts on readiness latches and task completion.
- Use `finally` blocks to release barriers cleanly when assertions fail.
- Cancel futures and shut down test executors.
- Await executor termination with timeouts.
- Capture thread dumps or diagnostics on timeouts.
- Be cautious with `assertTimeoutPreemptively` if tasks hold transactions, `ThreadLocal`s, or uncancellable side effects; preemptive timeouts run logic on another thread and do not kill background work automatically.

### 8.5. Separate Correctness Tests from Performance Tests

Keep unit tests short with crisp invariants and explicit synchronization primitives. Keep performance tests separate with warmups, controlled load, percentile metrics, and statistical runs.

Never assert "task completes under 5 ms" in unit tests on shared CI runners. That causes flakiness; latency thresholds belong in dedicated isolated benchmark environments with error margins.

## 9. Stress Tooling and Verifying Concurrent Algorithms

### 9.1. Why Repeating a Test 1,000 Times Still Falls Short

A lock-free algorithm can fail only on a rare interleaving or a weakly ordered CPU architecture. Looping JUnit tests raises detection odds yet never offers formal proof across every interleaving.

Combine:

- Unit tests verifying business invariants.
- Multi-threaded stress tests across varying contention levels.
- Fault injection and cancellation tests.
- Happens-before verification by algorithm design.
- Specialized concurrency testing tools where warranted.

### 9.2. `jcstress`

**OpenJDK jcstress** tests concurrency behavior at the Java Memory Model level. Tests coordinate actors accessing shared state and tally all observed outcomes.

Helpful for:

- Checking visibility and ordering guarantees.
- Comparing implementations before and after refactoring.
- Detecting unexpected outcomes under data races.
- Verifying across multiple JDKs and CPU architectures.

"Zero invalid outcomes observed" still does not equal exhaustive mathematical proof; define valid outcomes under the JMM and interpret sample statistics carefully.

### 9.3. Linearizability and State-Machine Testing

For concurrent maps, queues, caches, or multi-operation client libraries, verify **linearizability**: concurrent execution histories must correspond to some valid sequential history respecting real-time order of non-overlapping calls.

A checker generates histories like:

```text
T1: put(k, A) --------> complete
T2:      get(k) -----> returns ?
T3:            put(k, B) -----> complete
```

and tests whether observed results match a valid linearization.

Not every async API guarantees linearizability; confirm exact API contracts before enforcing strict criteria.

### 9.4. Race Detectors Do Not Replace Synchronized Design

Dynamic race detectors inspect access patterns, yet Java concurrency traverses multiple compiler/JIT optimizations and memory-model rules. No single test guarantees every race condition in a large system is gone.

In migration sign-offs, report **confidence levels and residual risks** rather than claiming "stress tests proved zero races exist."

## 10. Fault Injection: Verifying Failure Scenarios

### 10.1. Faults Worth Simulating Deliberately

Concurrent tasks can experience:

- Downstream API timeouts or HTTP 5xx errors.
- Exhausted database connection pools.
- Dropped message broker connections.
- Thread interruptions.
- One future failing ahead of sibling futures.
- Executor shutdown while tasks sit queued.
- Full queues rejecting tasks.
- Process restarts between database commits and message acks.
- GC pauses or throttled container CPU quotas under load.

Failure-path tests must assert both **business state** and **resource hygiene**: no infinite retry loops, connections returned to pools, callbacks fired at most/exactly once per contract.

### 10.2. Cancellation Across Multi-Stage Pipelines

Example:

```java
CompletableFuture<Result> pipeline =
        CompletableFuture.supplyAsync(
            () -> fetchFromRemote(), ioExecutor
        ).thenApply(result -> transform(result));
```

If an external request aborts, calling `cancel` on `pipeline` does not automatically interrupt `fetchFromRemote()` or abort underlying HTTP requests. Test cancellation propagation in your actual HTTP client and async abstractions.

When upgrading concurrency libraries, check behavior for:

- Calling `cancel` on upstream vs. terminal futures.
- Timeouts firing before vs. after downstream calls begin.
- Exceptions in the initial stage.
- Multiple stages finishing nearly simultaneously.
- Resource cleanup when subscribers cancel early.

### 10.3. Overload Handling Pairings with Retries

When a thread pool rejects tasks, immediate unbacked retries pin CPUs and worsen overload cascading.

Define clear policies: when to retry, max attempts, backoff intervals, jitter, and global deadline drops. Assert *bounded retries* and *bounded queues* in tests rather than equating higher thread counts with scalability.

## 11. Context Propagation: Where Does Request State Go Across Thread Hops?

### 11.1. `ThreadLocal` Does Not Propagate Request Context Automatically

Legacy code often stores:

- Request IDs and logging MDC.
- User identity and security principals.
- Active transactions or sessions.
- Locale and timezone overrides.
- Distributed tracing spans.
- Tenant IDs.

in `ThreadLocal` fields, assuming downstream callbacks stay on the origin thread.

With `CompletableFuture`, reactive schedulers, or custom executors, callbacks run on worker threads lacking that `ThreadLocal`. Logs lose correlation IDs—or worse, pooled threads leak stale security/tenant contexts across requests when cleanup fails.

### 11.2. Explicit Context Passing Is Safer

Effective strategies include:

- Passing immutable context objects directly as parameters.
- Wrapping `Runnable`/`Callable` to capture, install, and restore context safely.
- Adopting context propagation libraries integrated with framework tracing/security/reactive stacks.
- Limiting context lifetimes and cleaning up reliably when pooled threads reuse workers.

Explicit passing example:

```java
final class RequestContext {
    final String requestId;
    final String tenantId;

    RequestContext(String requestId, String tenantId) {
        this.requestId = requestId;
        this.tenantId = tenantId;
    }
}

void handleAsync(RequestContext context, Executor executor) {
    CompletableFuture.runAsync(
        () -> process(context.requestId, context.tenantId),
        executor
    );
}
```

In production code, apply security controls and avoid writing sensitive fields directly to logs.

### 11.3. Virtual Threads and Context

Virtual threads implement standard Java `ThreadLocal` semantics per virtual thread, yet spawning huge numbers of short-lived virtual threads can make heavy `ThreadLocal` state expensive and breaks assumptions tied to thread-pool reuse.

Never assume virtual threads inherit legacy framework contexts automatically in the way older apps expect. Run integration tests verifying transactions, security, tracing, and MDC on your exact JDK and framework versions.

## 12. Runtime Observability: Thread Dumps, JFR, and Metrics

### 12.1. Essential Metrics

For traditional executors/pools:

- Active threads alongside current/core/max pool sizes.
- Queue depth and queue wait duration.
- Submitted, completed, and rejected task counts.
- Execution duration and end-to-end latency.
- Cancellation and timeout counts.
- CPU, heap/off-heap memory, and GC pause metrics.
- Database/network connection wait times.

For reactive or virtual-thread architectures, track event-loop metrics, scheduler delays, and downstream concurrency semaphores. Never treat thread count as the sole KPI.

### 12.2. Thread Dumps

When suspecting deadlocks or hung tasks, capture live thread dumps:

```bash
jcmd <pid> Thread.print -l
```

Dumps show `BLOCKED`, `WAITING`, and `TIMED_WAITING` threads, lock owners, and stack frames. Note that starvation issues rarely show monitor deadlocks; cross-reference queue depths and workflow progress.

Thread dump tooling differs across JDKs; with massive counts of virtual threads, use JDK-appropriate dump formats rather than dumping unmanageably huge unfiltered stack traces.

### 12.3. Java Flight Recorder (JFR)

JFR captures CPU samples, lock contention, thread parking, allocations, GC pauses, and concurrency events. Start a bounded recording:

```bash
jcmd <pid> JFR.start name=concurrency-check duration=60s filename=concurrency.jfr
```

Configure event profiles and retention for your environment. Never turn on high-frequency verbose events in production without measuring overhead.

Analyze recordings using JDK Mission Control or compatible viewers, correlating p99 latency spikes with GC pauses, lock contention, or downstream blocking.

### 12.4. JFR Does Not Prove Safety

JFR profiles expose long waits or lock contention, yet never prove updates are atomic. Conversely, clean latency metrics never rule out rare silent data-race corruption.

Combine runtime profiling with invariant tests, stress harnesses, and careful code audits.

### 12.5. Logging Can Perturb Scheduling

Adding debug logs at every instruction to "catch a race" changes timing and hides races—the **observer effect**.

Prefer:

- Structured logs at meaningful lifecycle points (submit, start, complete, cancel, fail).
- Correlation IDs tied to requests/tasks.
- Aggregated metrics over verbose instruction-level logging.
- Sampled JFR profiling.
- Low-overhead distributed traces and counters.

Never assume a race is fixed merely because enabling debug logging made a test pass.

## 13. Measuring Concurrency Performance Meaningfully

### 13.1. Throughput Alone Is Insufficient

Increasing a pool from 8 to 64 threads can raise, maintain, or *reduce* throughput depending on workload bottlenecks. If a downstream database allows only 10 connections, adding threads shifts queueing without adding throughput.

Track at minimum:

- Completed business operations per second.
- Error, rejection, and timeout rates.
- p50, p95, and p99 end-to-end latency.
- Queue wait time vs. execution time.
- CPU, memory, GC pauses, and context switches where observable.
- Connection pool utilization and downstream latency.

Compare measurements under identical workloads and resource quotas. Never benchmark one run on a laptop against a CPU-throttled container and attribute differences solely to the JDK.

### 13.2. JIT Warmup and Microbenchmarks

Java microbenchmarks must account for JIT warmup, dead-code elimination, constant folding, allocation elimination, and steady-state measurement. **JMH** is the standard tool for microbenchmarking Java reliably compared to ad-hoc `System.nanoTime()` loops.

Never use JMH in place of integration load tests: microbenchmarks isolate small operations under controlled conditions without modeling real databases, networks, queues, or schedulers.

### 13.3. Workload Classification

| Category | Characteristics | Key Evaluation Focus |
| --- | --- | --- |
| CPU-bound | Heavy computation. | Parallelism matched to CPU capacity, contention, cache locality, GC. |
| Blocking I/O | Waits on network, DB, or filesystem. | Threading model, downstream pools, timeouts, cancellation. |
| Mixed | Combines compute and I/O. | Pool isolation or resource partitioning to avoid starvation. |
| Reactive | Event loops/schedulers, non-blocking flows. | Blocking inside event loops, backpressure, context propagation. |
| Batch / parallel stream | Splits work into many subtasks. | Work stealing, common-pool interference, ordering. |

Swapping concurrency frameworks can shift workloads across categories, so test both steady load and burst/outlier profiles.

### 13.4. Controlled Comparisons

Hold constant:

- Input datasets and endpoint ratios.
- Client counts and arrival rates.
- CPU/memory quotas, DB pool sizes, and downstream versions.
- JDK flags and GC policies when isolating library changes.
- Warmup durations, measurement runs, and percentile reporting methods.

Document any variables that cannot stay fixed (such as changed JDK GC defaults or updated OS base images). Report those runs as **full-stack system comparisons**, not isolated single-variable JDK causal benchmarks.

## 14. Containers, CPU Quotas, and Auto-Sizing

### 14.1. `availableProcessors()` Can Shift

Frameworks and executors commonly size defaults via:

```java
int processors = Runtime.getRuntime().availableProcessors();
```

In containers, the CPU count visible to the JVM depends on cgroup quotas/limits and container-awareness logic. Upgrading the JDK or container configuration can alter the returned value.

If common-pool parallelism, worker pools, or schedulers scale off `availableProcessors()`, changed values alter throughput, queueing, and race timing.

### 14.2. Never Assume Container CPUs Equal Host Logical CPUs

For container deployments, document:

- CPU requests, limits, and quotas.
- JDK release and container-awareness behavior.
- Runtime `availableProcessors()` output.
- Actual thread-pool sizes configured after boot.
- Container CPU throttling metrics.
- Memory limits vs. thread counts and stack footprints.

If an application slows down after migration, check whether CPU quotas shrank auto-sized pools before rewriting algorithms.

### 14.3. Oversized Thread Pools Carry Heavy Costs

Inflating pool sizes increases:

- OS context switching overhead.
- Lock contention.
- Stack and platform-thread memory footprints.
- Connection pressure on databases and HTTP downstreams.
- Queued tail latency when downstreams saturate.

Avoid blindly setting "max threads = several thousand" as a catch-all fix. Even with virtual threads allowing high task counts, external capacity-limited resources still require explicit concurrency limits.

## 15. End-to-End Verification Scenario

### 15.1. Context

Suppose an order-processing service executes:

```text
HTTP request
    |
    v
Validate
    |
    v
Submit task to executor
    |
    +----> Check inventory (DB)
    |
    +----> Reserve payment (remote API)
    |
    v
Persist order state
    |
    v
Publish event
```

The project is upgrading the JDK while swapping its async client library. Prior to migration, rare timeouts caused client retries that risked creating duplicate orders.

### 15.2. Mandatory Invariants

- One idempotency key produces at most one logical order.
- Inventory never decrements below zero available units.
- Payment is never charged twice for one transaction.
- Cancelled tasks settle into well-defined terminal states rather than leaving records stuck in `"processing"` forever.
- Events publish only after database state commits per contract.
- When downstream slows down, internal queues stay bounded.
- Security and request contexts never drop across async hops.

### 15.3. Normal Concurrency Tests

Send concurrent requests across distinct IDs and verify complete, accurate outputs with zero dropped tasks.

Send concurrent requests sharing the **exact same idempotency key** and verify only one compliant business side effect occurs.

### 15.4. Contention Tests

Use latches or barriers so multiple workers arrive at inventory checks together. Never rely on a race happening spontaneously in one run. Verify invariants once every future settles or deadlines expire.

### 15.5. Fault Injection

Simulate remote API timeouts, DB rollbacks, executor rejections, process restarts, and pre-commit cancellations. Verify retries, compensations, and final persisted states.

### 15.6. Before/After Load Tests

Replay identical workloads on baseline and target configurations. Compare p99 latency, throughput, queue depth, CPU, GC pauses, error/timeout/rejection rates, open connections, and residual active tasks after traffic stops.

### 15.7. Rollback Planning

If the new deployment triggers duplicate side effects or unbounded backlogs, rolling back application binaries alone may not fix mutated DB records or queued messages. Verify data compatibility, message reprocessing rules, and reconciliation for timed-out tasks that actually succeeded downstream.

## 16. Step-by-Step Migration Workflow

### Step 1: Freeze Change Scope

Pin source/target JDKs, concurrency library versions, framework releases, and executors/schedulers changing. Avoid bundling unrelated variables in one step when isolating root causes.

### Step 2: Capture Baseline Metrics and Configs

Record JVM flags, dependencies, thread pools, CPU/container quotas, task counts, latency percentiles, queue depths, errors, timeouts, and shutdown behaviors. Archive test reports and workloads.

### Step 3: Specify Concurrency Contracts

Document safety invariants, liveness guarantees, ordering rules, deadlines, retries, cancellation, context propagation, and throughput targets.

Translate every behavioral note from release guides into concrete tests or metrics assertions.

### Step 4: Build a Deterministic Test Harness

Coordinate contention with latches/barriers, enforce bounded completion timeouts, call `Future.get` to catch worker exceptions, and shut down executors cleanly to prevent thread leaks. Add stress runs for high-risk synchronization logic.

### Step 5: Upgrade JDK and Tooling in Supported Configurations

Verify build tools, JVM options, Byte Buddy/ASM/agents, JFR support, and concurrency libraries. Where intermediate combinations are unsupported, transition across officially supported upgrade legs.

### Step 6: Upgrade Concurrency Libraries Per Guides

Audit API shifts, default executors, schedulers, context propagation, timeouts, and cancellation. Go beyond fixing compilation errors to confirm effective runtime behavior.

### Step 7: Verify Correctness and Liveness Before Performance

Run unit/integration concurrency suites, fault injection, shutdown/restart checks, queue overload tests, and stress harnesses. Reject any performance gain that breaks safety invariants.

### Step 8: Run Controlled Performance Measurements

Apply steady workloads, warmups, and repeated runs. Report throughput, tail latency, error rates, and resource usage—never single-request timings.

### Step 9: Canary and Monitor in Production-Like Environments

Gradually shift traffic behind safety limits. Watch queue backlogs, completion rates, duplicates, p99 latency, CPU/GC, blocked threads, and downstream saturation, backed by predefined rollback thresholds.

### Step 10: Finalize Documentation and Retire Workarounds

Update docs for executor configurations, timeout/retry policies, JDK/toolchain baselines, thread dump / JFR collection runbooks, backlog recovery steps, and residual risks.

## 17. Common Pitfalls

**"A test passed 100 times so there is no data race."** False. Observed schedules never cover every possible interleaving. Synchronize properly under the Java Memory Model and test invariants directly.

**"`volatile` makes `counter++` thread-safe."** False. Visibility and atomicity are distinct guarantees.

**"Adding more threads always boosts throughput."** False. Extra threads can overload downstreams, increase contention, and hurt p99 latency.

**"`Thread.sleep` is enough to wait for workers."** False. Sleeping provides no completion guarantee or happens-before edge.

**"`Future.cancel(true)` always stops a task."** False. Tasks and I/O must cooperate with interruption per contract.

**"`CompletableFuture` callbacks always run on the request thread."** False. Thread selection depends on stage type, executor, and completion state.

**"Green builds mean async tasks succeeded."** False. Exceptions can sit unobserved inside `Future`s or unasserted callbacks.

**"Zero monitor deadlocks in thread dumps means nothing is stuck."** False. Starvation, bounded resource exhaustion, and downstream hangs break liveness without monitor deadlocks.

**"Virtual threads remove all concurrency limits."** False. Database pools, downstream rate limits, and CPUs remain capacity-constrained.

**"The new JDK broke previously correct code."** Not necessarily. Latent bugs often remain hidden until scheduling or runtime conditions change. Separate pre-existing data races from true library contract changes.

## 18. Pre-Release Verification Checklist

- [ ] Recorded before/after JDK vendors/versions, concurrency libraries, and framework versions.
- [ ] Audited CPU quotas, container awareness, and runtime `availableProcessors()`.
- [ ] Inventoried all explicit and implicit executors, common pools, and schedulers.
- [ ] Documented pool sizes, queue bounds, rejection policies, timeouts, and shutdown rules.
- [ ] Defined safety invariants and idempotency guarantees for external side effects.
- [ ] Verified atomicity, visibility, safe publication, and lock ordering.
- [ ] Used latches/barriers for contention tests rather than sleeping.
- [ ] Enforced bounded test timeouts, checked `Future` exceptions, and cleaned up executors.
- [ ] Verified cancellation/interruption, deadlines, retries, and failure propagation.
- [ ] Tested deadlocks, starvation, livelocks, queue backlogs, and overload behavior.
- [ ] Verified context propagation across threads: MDC, tracing, security, tenant, transactions.
- [ ] Verified reactive/virtual-thread behavior if adopted.
- [ ] Executed fault injection for timeouts, shutdowns, downstream errors, and restarts.
- [ ] Collected throughput, p95/p99 latency, error rates, queue depths, CPU, GC, and downstream metrics.
- [ ] Compared performance under controlled workloads and equal resource quotas.
- [ ] Prepared thread dump, JFR, and backlog recovery runbooks for liveness incidents.
- [ ] Defined canary steps, rollback triggers, and reconciliation for in-flight side effects.
- [ ] Archived test evidence confirming business invariants hold after migration.

## 19. Summary

When swapping JVMs or concurrency libraries, verification must go well beyond compiling cleanly and passing sequential tests. Validate **safety**, **liveness**, **performance**, and **operability** across varying schedules and load levels. The Java Memory Model governs visibility and atomicity; executors, futures, schedulers, reactive engines, and virtual threads add specific contracts around scheduling, cancellation, and resource bounds.

In Java Advance Compatibility Migration, establish baselines and business invariants upfront, build deterministic synchronization harnesses, exercise failure paths, observe live JVMs via metrics, thread dumps, and JFR, and compare behavior on exact target JDKs and dependencies. Only when the system proves **data-accurate**, **responsive and recoverable**, and **within latency/throughput budgets** is a concurrency migration genuinely ready for production.
