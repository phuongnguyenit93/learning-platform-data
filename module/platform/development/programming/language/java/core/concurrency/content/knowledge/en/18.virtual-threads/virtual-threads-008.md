# Limiting External Resources with Semaphores and Connection Pools When Using Virtual Threads

## 1. The problem: many virtual threads do not mean many external resources

Virtual Threads (stable since Java 21) allow writing synchronous, blocking code in a one-task-per-thread style with lower thread overhead than platform threads for I/O-bound waiting work. However, **cheap virtual threads do not make database connections, sockets, connection sessions, API quotas, or external services infinite**.

Suppose an application receives 5,000 concurrent requests. Each request runs on a virtual thread and must query a service that allows at most 20 concurrent calls. Calling it immediately without any limit can overload the external side, cause errors, increase latency, or trigger connection refusals. Two types of limits must be separated:

- **Java task concurrency:** there can be very many live virtual threads, including threads that are waiting.
- **External resource concurrency:** only a bounded number of tasks are allowed inside the resource-using section at the same time.

**Principle:** create virtual threads per task; use a `Semaphore` or the allocation mechanism of a **connection pool** to control scarce resources. Do not create a "pool of virtual threads" just to limit the number of tasks accessing a service.

## 2. What is a Semaphore, and what can it limit?

`java.util.concurrent.Semaphore` holds a number of **permits** (logical permissions). Each `acquire()` call requests one permit; when no permits are left, the caller must wait. `release()` returns a permit so another task can proceed. No physical "permit" object is issued: it is a counter and synchronization mechanism.

For example, `new Semaphore(3)` allows at most **three tasks that have acquired a permit and not yet released it** inside the guarded section at the same time. A virtual thread blocked on `acquire()` is waiting for access permission, not holding an actual connection. This waiting phase generally fits the virtual thread model well because Java can park the virtual thread and free the carrier for other work.

```text
Many tasks on virtual threads
    ├── task A ── acquire ──► use external service ──► release
    ├── task B ── acquire ──► use external service ──► release
    ├── task C ── acquire ──► use external service ──► release
    ├── task D ── wait for permit ───────────────────► ...
    └── task E ── wait for permit ───────────────────► ...
                 Semaphore(3)
```

Crucially, **the permit-holding boundary must enclose the exact resource usage that needs to be limited**. If a permit is acquired before an I/O call but released as soon as an asynchronous call is merely initiated, the number of operations actually in flight can exceed the limit. With asynchronous APIs, release the permit after the operation completes, including on failure or cancellation.

Operations to know:

| API | Meaning | Notes |
| --- | --- | --- |
| `acquire()` | Waits until a permit is acquired | Can throw `InterruptedException`; do not `release()` if not acquired |
| `tryAcquire()` | Attempts to acquire immediately without waiting | Returns `false` when no permit is available; the no-timeout overload can barge ahead of waiting threads in a fair semaphore |
| `tryAcquire(timeout, unit)` | Waits up to a specified duration | Returns `false` on timeout, or throws `InterruptedException` if interrupted |
| `release()` | Increases the number of available permits by one | `Semaphore` does not check whether the caller ever called `acquire()`; extra releases break the limit |
| `availablePermits()` | Number of permits currently available at a point in time | Only an instantaneous snapshot; do not use it to check-then-`acquire()` |
| `new Semaphore(n, true)` | Requests a fair waiter selection policy | Balances waiting order against overhead/throughput; does not guarantee strict start order |

`Semaphore` limits **concurrent in-flight usage**; it does not create, reuse, close, or health-check actual connections. A semaphore is also not a **requests-per-second** rate limiter: 10 permits can serve far more than 10 requests/second if each request finishes very quickly.

## 3. Java 21+ example: 12 virtual threads, at most 3 external calls

The standalone example below simulates an I/O service with `Thread.sleep(100)`. In a real application, replace the simulation with a JDBC call, HTTP client call, or the I/O operation to be limited. Every task still has its own virtual thread; at most **three** tasks can be inside the "external resource region" at the same time.

Save as `LimitExternalCalls.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicInteger;

public class LimitExternalCalls {
    private static final int LIMIT = 3;
    private static final Semaphore GATE = new Semaphore(LIMIT, true);

    private static final AtomicInteger IN_FLIGHT = new AtomicInteger();
    private static final AtomicInteger PEAK = new AtomicInteger();
    private static final AtomicInteger COMPLETED = new AtomicInteger();

    private static void callExternalService() throws InterruptedException {
        // If interrupted while waiting, no permit is owned yet.
        GATE.acquire();
        try {
            int now = IN_FLIGHT.incrementAndGet();
            PEAK.accumulateAndGet(now, Math::max);
            try {
                // Simulate a blocking I/O call.
                Thread.sleep(100);
                COMPLETED.incrementAndGet();
            } finally {
                IN_FLIGHT.decrementAndGet();
            }
        } finally {
            // Only runs after acquire() has succeeded.
            GATE.release();
        }
    }

    public static void main(String[] args) throws Exception {
        List<Future<?>> futures = new ArrayList<>();

        try (ExecutorService executor =
                 Executors.newVirtualThreadPerTaskExecutor()) {
            for (int i = 0; i < 12; i++) {
                futures.add(executor.submit(() -> {
                    callExternalService();
                    return null;
                }));
            }

            // Propagate errors from each task instead of only waiting for the executor to finish.
            for (Future<?> future : futures) {
                future.get();
            }
        }

        System.out.println("completed=" + COMPLETED.get());
        System.out.println("active=" + IN_FLIGHT.get());
        System.out.println("peak<=3: " + (PEAK.get() <= LIMIT));
    }
}
```

Compile and run with **JDK 21+**:

```bash
javac LimitExternalCalls.java
java LimitExternalCalls
```

```text
completed=12
active=0
peak<=3: true
```

These three lines are deterministic when the program exits normally. The actual value of `PEAK` can be between 1 and 3 depending on scheduling; what needs to be proven is that it is **never greater than 3**. `Future.get()` waits for the task and surfaces task failures as `ExecutionException` on the calling thread, avoiding the illusion that everything succeeded even when a task failed. `ExecutorService` in `try-with-resources` closes after the tasks finish.

Breakdown of the guarded section:

1. Acquire the permit **before** incrementing `IN_FLIGHT` or accessing the external service.
2. Use `try/finally` to decrement the active counter even if I/O fails or is interrupted.
3. Use an outer `try/finally` to release the permit **exactly once** after a successful `acquire()`.
4. Never place `release()` in a `finally` block that wraps `acquire()` in a way that could run when `acquire()` throws `InterruptedException` before acquiring a permit.

`AtomicInteger` only makes the measurements thread-safe; **`Semaphore` is what protects the resource**. Place the semaphore in an object shared among all tasks accessing the same quota. If each request creates its own `new Semaphore(3)`, every request has its own quota and the system-wide limit no longer takes effect.

## 4. Bounded waiting, handling timeouts and interrupts properly

`acquire()` can wait indefinitely if no permits ever return. On a request-handling path, consider wait time budgets, load limits, and failure policies. The example below is an **illustrative method**, assuming an existing shared `Semaphore gate` and a blocking `callRemote()` method to guard:

```java
String callWithTimeout(Semaphore gate) throws InterruptedException {
    boolean acquired = gate.tryAcquire(500, java.util.concurrent.TimeUnit.MILLISECONDS);
    if (!acquired) {
        throw new IllegalStateException("Dich vu dang qua tai: het thoi gian cho permit");
    }
    try {
        return callRemote(); // Application-provided method.
    } finally {
        gate.release();
    }
}
```

`callRemote()` is not declared here, so this snippet is **not a standalone runnable program**. In a real program, that call may throw HTTP/JDBC-specific exceptions; `finally` must still release the permit. If interrupted while `tryAcquire(...)` is waiting, Java throws `InterruptedException` and **there is no permit to release**. When a task handles `InterruptedException` instead of propagating it, it usually needs to restore the interrupt flag with `Thread.currentThread().interrupt()` and exit early rather than continuing I/O.

A permit wait timeout does not replace connection, query, or HTTP timeouts. They are independent deadlines: permit wait timeout, connection establishment time, and command execution time must each be managed separately. Nor should you retry indefinitely after running out of permits; each retry increases the number of waiting tasks.

## 5. Connection pools already manage the number of real connections

A **connection pool** manages a finite set of physical connections for reuse. Borrowing a connection from the pool typically reduces the number of idle connections; when returned, the connection can serve another task. Pools have their own policies such as maximum connections, borrow timeout, connection validation, lifecycle, and eviction.

With JDBC, applications typically obtain connections from `javax.sql.DataSource`; **the `DataSource` interface itself does not guarantee pooling** — an actual pooling implementation must be configured. Illustrative example:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

long countUsers(DataSource dataSource) throws SQLException {
    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement =
             connection.prepareStatement("SELECT COUNT(*) FROM users");
         ResultSet resultSet = statement.executeQuery()) {
        resultSet.next();
        return resultSet.getLong(1);
    }
}
```

This is an **illustrative method**, not a standalone class; it requires a `users` table and a configured `DataSource`. When using a connection pool, `connection.close()` normally **returns the connection to the pool**; closing resources via `try-with-resources` is mandatory so the pool is not exhausted. `DataSource.getConnection()` may wait for an idle connection or fail on timeout, depending on the pool. Each task should borrow and return the connection in the shortest scope possible; do not hold onto a connection for the entire lifetime of a virtual thread just because the thread is lightweight.

**A pool with a maximum size of 10 already limits how many connections it hands out at the same time.** Do not wrap connection borrowing with an extra `Semaphore(10)` by default: you will end up with two queues and two timeout mechanisms, making the system harder to tune and diagnose. Only add a semaphore if it protects **an independent limit** that the pool is unaware of—for example, the DB only allows 10 heavy queries concurrently even though the pool has 30 connections, or an accompanying API also caps the number of in-flight requests.

| Situation | Primary tool | Reason |
| --- | --- | --- |
| External API only accepts 8 concurrent tasks | Shared `Semaphore(8)` | Limits logical calls; does not own connections |
| Database only grants at most 20 connections | Pool with `maximumPoolSize=20` (name depends on implementation) | Pool manages, reuses, and allocates real connections |
| 20 DB connections, but only 5 heavy queries may run at once | Pool of 20 + semaphore of 5 **dedicated to the heavy query path** | Two independent limits; timeouts must be measured at both places |
| External side enforces 100 requests/second | Rate limiter | Semaphore limits concurrent in-flight work, not time-windowed quota |
| Task arrival rate exceeds the system's waiting capacity | Bounded admission/queue and backpressure | Semaphore does not bound the number of waiting virtual threads |

## 6. Choosing limits that match the resource

Limits must be based on the **actual capacity and quota** of the external side, not on how many virtual threads can be created or the number of cores on the Java machine. Questions to answer:

- How many concurrent connections, in-flight requests, or active sessions does the service/DB allow at most? Which applications share this quota?
- How long does each task hold the resource, what is the error/timeout rate, and how does the queue depth grow as load increases?
- How many different resources can a single request hold simultaneously? Is there a risk of two paths holding A while waiting for B and holding B while waiting for A?
- After how long should the system respond "busy" instead of waiting forever?

Little's Law for a stable system gives intuition: **average in-flight tasks ≈ throughput × average processing time**. For example, a service taking 0.2 seconds per call at 50 calls/second averages about 10 calls in flight. This is an estimate to start measuring, **not an automatic formula for choosing permits**, because service limits, tail latency distributions, replica counts, and request paths also matter.

Hold the permit only for the section that actually needs the quota: do not lock a slot while parsing unrelated JSON, reading a cache, or doing lengthy data preparation. Conversely, if a workflow has two I/O steps that both consume the same quota across the entire span, be explicit about when the slot is actually held. When running multiple instances, **each instance has its own semaphore**: 5 replicas × 8 permits can send 40 concurrent tasks to a service that only allows 8. When a quota is system-wide, you need per-replica budgets or a distributed coordination mechanism; an in-JVM semaphore does not coordinate across processes.

## 7. Failure modes and how to fix them

**Forgetting to release a permit.** Certain exception paths or early returns leak permits; after enough occurrences, all subsequent tasks wait forever. Fix this by placing `try/finally` immediately after a successful permit acquisition, and wrapping real resource borrowing/returning in `try-with-resources`.

**Releasing a permit without acquiring it or releasing twice.** `Semaphore.release()` does not require the caller to own a permit and does not prevent over-releasing. As a result, concurrency can exceed the original limit. Never call `release()` in a timeout/interrupt branch where acquisition did not succeed; never split release responsibility across two layers at the same time.

**Using `availablePermits() > 0` to decide whether to enter.** The value can change right after the check; another task may have already taken the permit. Call `acquire()` or `tryAcquire()` directly so taking the permit is atomic/synchronized.

**Using a fixed thread pool to throttle virtual threads.** Limiting worker threads does not directly express service usage concurrency. A pool of virtual threads also defeats the one-virtual-thread-per-task model. Put the semaphore directly around the I/O section; keep the per-task virtual thread executor.

**Adding a semaphore of the same size as the connection pool everywhere.** Redundant queues and timeouts make it unclear which one exhausts first. Verify that the pool already enforces the connection limit properly; only add a gate if there is a separate business/external quota.

**Increasing permits to shrink the queue without measuring the external system.** This can turn a Java-side queue into a longer queue at the DB/API, increasing timeouts and errors. Limits exist to protect the external side; incoming work must also be controlled.

**Assuming FIFO is always strict.** `new Semaphore(n, true)` grants permits to waiters according to internal queueing, but does not promise the start or completion order of I/O operations. `tryAcquire()` without a timeout can barge ahead of waiting threads even when `fair=true`; check actual fairness requirements before relying on it.

**Holding a permit while doing unrelated work.** Waiting on another lock, waiting for a response that does not use the resource, or doing long CPU work inside the guarded section reduces useful throughput. Measure permit hold time and narrow the scope to the quota being protected; avoid multiple gates with inconsistent lock ordering.

## 8. Observing and verifying in production

Track **workload**, **wait time**, and **real resources** separately:

- Semaphore: slots in use, `acquire` wait time, `tryAcquire` timeout counts, waiting task count; `getQueueLength()` is only an **estimate**, not an exact counter for throttling decisions.
- Connection pool: active/idle/max connections, requests waiting to borrow a connection, borrow timeouts, connection hold time, connection leaks.
- External service: in-flight calls, throughput, timeouts, error rate, p95/p99 latency, quota-based throttling.
- Inbound load: tasks waiting at the request intake gate, memory consumed by pending tasks/inputs. Virtual threads are lightweight, not infinite-memory.

A good test is to generate more concurrent tasks than the permit count, measure `inFlight` inside the external operation section itself, and assert `peak <= limit`. Then intentionally inject exceptions, interrupts, and timeouts to verify permits return to the initial count and connections are returned. When testing with a pool, verify physical connections never exceed the configured maximum. Do not use the number of live virtual threads to infer how many connections are in use.

## 9. Takeaways

- Virtual threads keep blocking code readable when handling many I/O tasks; **they do not increase database/API quotas**.
- A semaphore protects a **section of work with bounded concurrent in-flight execution**; only `release()` after a successful `acquire()`, exactly once, in `finally`.
- A connection pool manages **real connections** and already has allocation blocking/timeout mechanisms; an extra semaphore with the same role is usually unnecessary.
- Timeouts, interruption, backpressure, system-wide limits, and observability are all required to keep resource limiting safe in production.

## References

- Oracle, [Virtual Threads — Java SE 21](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): guide on virtual threads, semaphores, and connection pools.
- Oracle, [`Semaphore` Java API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Semaphore.html): semaphore operations and guarantees.
- Oracle, [`Executors` Java API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html): `newVirtualThreadPerTaskExecutor()`.
