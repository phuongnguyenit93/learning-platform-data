# Bulkhead: Limiting Load by Resource Type in Java

## 1. Objectives and Scope

A bulkhead is a design pattern for protecting concurrent systems: **partitioning capacity across work groups** so that one slow or overloaded group cannot exhaust the resources needed by other groups. After this lesson, you will be able to identify thread/connection/queue contention, choose an appropriate isolation mechanism, implement limits in Java, handle overload, and test isolation.

This lesson covers **general Java concurrency**, using `java.util.concurrent` APIs and JVM resources; no framework or Spring configuration mechanism is required.

## 2. Why Do We Need a Bulkhead?

Suppose an application handles three workloads: calling a slow payment service over the network, querying a database, and processing data in memory. If all three share 20 workers, 20 stuck payment calls will force the other two workloads to wait in the queue even though they are healthy. When new requests arrive faster than they complete, the queue, latency, and memory usage can grow continuously.

That is a **cascading failure through shared resources**: a failure in one dependency spreads to other features because threads, connections, or queues are completely occupied. The bulkhead pattern borrows the idea of watertight compartments on a ship: flooding one compartment does not sink the entire vessel. Each work group has its own limit; when group A saturates, new load for A is either queued within its limit or rejected, while B can continue serving requests.

```text
Without isolation:
    Payment  ──┐
    DB query ──┼──> Shared executor (20 workers) ──> blocks all work types
    Compute  ──┘

With bulkhead:
    Payment  ──> Pool A (8 workers, queue 16) ──> Payment API
    DB query ──> Pool B (6 workers, queue 12) ──> Database
    Compute  ──> Pool C (4 workers, queue 8)  ──> CPU
```

The numbers above are illustrative only, not default configurations. You must check actual resource limits before choosing pool sizes.

## 3. Partitioning by the Actual Contended Resource

| Resource / workload group | Suitable mechanism | Budget to observe |
| --- | --- | --- |
| Platform threads for blocking tasks | Dedicated `ThreadPoolExecutor` with a bounded queue | Active workers, queued tasks, rejections |
| Requests calling an API/backend | Per-downstream `Semaphore` | In-flight calls, latency, timeouts |
| JDBC/HTTP/socket connections | Bounded connection pool; semaphore before borrowing a connection if needed | Active connections, wait time, quota |
| CPU-bound work | Executor sized to CPU capacity | CPU saturation, context switching |
| Memory and event buffers | Bounded queue, item count or byte limit | Queue depth, heap, backlog age |

A single task may simultaneously occupy a thread, a connection, and memory. Splitting into two executors will **not isolate** two groups if both still compete for the same undersized JDBC pool; nor does it increase physical CPU. Choose boundaries based on the **observed bottleneck** and account for the budget of shared resources.

A bulkhead limits the **number of concurrent operations**; a rate limiter limits the **initiation rate** of operations over time. For example, two permits can process hundreds of requests/second if each request finishes very quickly, or only a few requests/second when the downstream is slow. You may need both.

## 4. Two Types of Bulkheads in Java

### 4.1. Thread-pool bulkhead

Create a dedicated executor for each work group that needs isolation, including **maximum workers, a bounded queue, and a full-queue policy**. Tasks from A cannot occupy workers or queue slots belonging to B. With `ThreadPoolExecutor`, `corePoolSize`, `maximumPoolSize`, and `BlockingQueue` determine capacity; `RejectedExecutionHandler` handles new requests when no more can be accepted.

Note: `Executors.newFixedThreadPool(n)` uses an unbounded queue by default. Therefore, it limits workers but **has no bounded backlog limit**; queued work can grow until memory becomes a problem. For explicit fail-fast behavior, create a `ThreadPoolExecutor` with a bounded queue such as `ArrayBlockingQueue` and `AbortPolicy`.

Dedicated pools carry thread, heap, and operational overhead; creating dozens of oversized pools can make the system worse. Also manage lifecycle properly with `shutdown()`, `awaitTermination()`, and `shutdownNow()`.

### 4.2. Semaphore bulkhead

`Semaphore(k)` allows at most `k` concurrent operations to hold a permit, which is well suited for capping the number of in-flight calls to the same API or connection group. Callers may originate from different executors while still sharing one semaphore.

A semaphore **does not allocate threads**, does not separate schedulers, and does not automatically stop running calls. For blocking callers, an unbounded `acquire()` can make callers wait indefinitely; you should usually use `tryAcquire(timeout)` and reject in a controlled way. If all callers are stuck in a shared executor, available permits still do not guarantee that a new task will be scheduled.

## 5. Runnable Java 17+ Example: Isolating a Slow Pool and a Healthy Pool

This example fills a `slow` pool with one worker and a queue of capacity one. The third task is rejected; the `fast` pool still processes normally. Latches control ordering so the output is deterministic and verifiable.

Save with the exact filename **`BulkheadDemo.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class BulkheadDemo {
    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor slow = newPool("slow");
        ThreadPoolExecutor fast = newPool("fast");
        CountDownLatch slowStarted = new CountDownLatch(1);
        CountDownLatch releaseSlow = new CountDownLatch(1);

        try {
            Future<String> running = slow.submit(() -> {
                slowStarted.countDown();
                releaseSlow.await();
                return "slow: running completed";
            });

            slowStarted.await(); // The slow worker is running and holding the latch.
            Future<String> queued = slow.submit(() -> "slow: queued completed");

            try {
                slow.submit(() -> "will be rejected");
                throw new AssertionError("Expected rejection");
            } catch (RejectedExecutionException expected) {
                System.out.println("slow: rejected");
            }

            Future<String> healthy = fast.submit(() -> "fast: OK");
            System.out.println(healthy.get(2, TimeUnit.SECONDS));

            releaseSlow.countDown();
            System.out.println(running.get());
            System.out.println(queued.get());
        } finally {
            releaseSlow.countDown();
            slow.shutdownNow();
            fast.shutdownNow();
        }
    }

    private static ThreadPoolExecutor newPool(String name) {
        return new ThreadPoolExecutor(
                1, 1,
                0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                task -> new Thread(task, "bulkhead-" + name),
                new ThreadPoolExecutor.AbortPolicy()
        );
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac BulkheadDemo.java
java BulkheadDemo
```

Output:

```text
slow: rejected
fast: OK
slow: running completed
slow: queued completed
```

**Explanation:** After `slowStarted.await()`, the first task holds the `slow` worker and waits on the latch. The second task enters the single-slot queue. The third task exceeds both limits, so `AbortPolicy` throws `RejectedExecutionException` immediately on `submit()`. Meanwhile, `fast` has its own worker and completes. Releasing the latch lets `slow` finish the two earlier tasks; `Future.get()` ensures deterministic output order.

`shutdownNow()` in the demo simplifies cleanup on exception. It attempts to interrupt tasks and **does not guarantee** that all blocking/I/O APIs will stop immediately. In production systems, prefer a timed lifecycle: `shutdown()`, wait for a bounded duration, then consider `shutdownNow()` and monitor tasks that have not stopped.

## 6. Semaphore Example: Limiting Two Concurrent Calls

This is a **component class** used inside an application (it has no `main()`; do not run it standalone with `java SemaphoreBulkhead`):

```java
import java.util.concurrent.Callable;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

final class SemaphoreBulkhead {
    private final Semaphore slots = new Semaphore(2);

    public <T> T execute(Callable<T> action) throws Exception {
        if (!slots.tryAcquire(100, TimeUnit.MILLISECONDS)) {
            throw new RejectedExecutionException("Bulkhead full");
        }
        try {
            return action.call();
        } finally {
            slots.release();
        }
    }
}
```

Assuming `bulkhead` is a shared instance, callers can invoke `bulkhead.execute(() -> remoteClient.fetch())`. **Do not create a new instance per request**, because each instance would have its own two permits and would fail to limit total concurrency to the dependency.

Permit lifecycle notes:

- `tryAcquire` returns `false` when the wait time expires; if interrupted before acquiring a permit, it throws `InterruptedException`. Enter `try/finally` and call `release()` only when acquisition succeeded.
- `finally` returns the permit whether `action.call()` succeeds or throws an exception. Never call `release()` twice: that increases the permit count beyond the intended limit.
- The **permit wait** timeout is not the **call execution** timeout. You must configure connection/read/request timeouts on the client and an overall deadline if needed.
- You can request approximate fairness with `new Semaphore(2, true)`, but fairness does not replace deadlines and can reduce throughput.
- If `action.call()` merely starts a `CompletableFuture` and returns before the work finishes, this synchronous wrapper releases the permit **too early**. When writing an asynchronous version, hold the permit until the real completion callback and ensure it is released exactly once even on error or cancellation.

## 7. Setting Limits: Concurrency, Queue, and Latency Budget

Limits must be derived from measurements and the downstream's capacity.

**Step 1: Define the budget.** Which group holds threads/connections/CPU, which group can be slow, and which group needs priority? How many DB connections or concurrent requests does the downstream actually support? Account for all other instances sharing it.

**Step 2: Estimate concurrency.** In steady state, Little's Law gives `L = λ × W` (average work in the system = average throughput × average time in the system). For example, 40 requests/second with an average resource hold time of 0.2 seconds corresponds to about 8 concurrent operations holding the resource. This is only a starting point: account for bursts, tail latency, retries, connection/CPU limits, and ensure `W` measures the exact section being limited.

**Step 3: Choose workers/permits.** For CPU-bound work, typically start near available CPU cores and measure context switching and throughput. For blocking I/O, you may need more threads than CPUs, but do not exceed the dependency's budget. With virtual threads, connection/remote-call limits still require an independent mechanism.

**Step 4: Size the bounded queue based on acceptable wait time.** If 100 tasks/second arrive at a pool that can only process 20 tasks/second, the backlog grows by roughly 80 tasks/second. A 160-slot queue can fill up in about two seconds starting from empty if that gap persists. Increasing queue size only delays rejection and can increase latency; it does not increase throughput by itself.

**Step 5: Choose the overload response.** You can reject immediately, allow a very short wait, return a safe fallback result, or shed lower-priority work. For HTTP applications, status codes such as 429 or 503 depend on the API contract and root cause; do not default to the same code for everything. Producers must know how to stop, back off, or handle errors instead of retrying immediately without limit.

**Step 6: Load test and tune.** Measure p95/p99 latency, queue wait, rejections, CPU, connection wait, and especially the latency of healthy groups when one group is intentionally slowed down.

## 8. Timeouts, Cancellation, Retries, and Backpressure

A bulkhead is only effective when the overload path is explicitly designed:

1. **Bound wait time for a slot:** use `tryAcquire(timeout)` or a bounded queue with rejection; never let callers wait indefinitely when a dependency stops responding.
2. **Bound execution time:** configure timeouts on sockets, HTTP clients, or JDBC drivers and propagate deadlines from the incoming request when appropriate. `Future.get(timeout)` only bounds the time **waiting for the future**, not the underlying task itself. `cancel(true)` requests an interrupt, while actual termination depends on the task and library.
3. **Do not release permits early on cancellation:** if a task is still using a connection after the caller stops waiting, the permit must reflect the work still holding the resource. Avoid creating extra load by letting another request in before the old task has stopped.
4. **Backpressure/load shedding:** block at the boundary or fail fast when resources saturate, rather than piling backlog onto the heap.
5. **Budgeted retries:** retry only recoverable failures, cap attempts and duration, and use appropriate backoff/jitter; immediate retries when a bulkhead is full often cause a retry storm.
6. **Fallbacks must also be bounded:** do not route all failed requests into another shared pool and overload it.

`CallerRunsPolicy` executes rejected tasks on the calling thread in certain situations, which slows down the producer but can propagate latency back to the caller and defeat isolation. `DiscardPolicy` and `DiscardOldestPolicy` can silently drop work; in particular, when using `submit()`, the `Future` of a discarded task may never complete. Use them only if loss semantics are explicitly designed. `AbortPolicy` makes rejections visible so you can react and record them.

## 9. CompletableFuture, Virtual Threads, and Deadlock

`CompletableFuture.supplyAsync(supplier)` without an explicit executor uses `ForkJoinPool.commonPool()` by default. To isolate blocking tasks by dependency, use `CompletableFuture.supplyAsync(supplier, dedicatedExecutor)`; remember to handle scheduling rejection errors and manage the executor's lifecycle. Do not assume that wrapping work in a future creates a bulkhead.

Java 21 introduces virtual threads with lower thread overhead for many blocking operations, but virtual threads **do not create more** DB connections, API quotas, or CPUs. You still need semaphores or resource-bounded pools, timeouts, and cancellation. The main code in this lesson targets Java 17 so it runs on JDK 17+.

If a task must acquire multiple permits or locks, enforce a consistent acquisition order and avoid holding a scarce resource while waiting too long for another. For example, tasks in group A holding a DB permit while waiting for an API permit, while tasks in group B do the reverse, can create a circular wait. Hold resources only for the section of code that truly needs them.

## 10. Comparison with Other Protection Mechanisms

| Mechanism | What problem does it solve? | Example |
| --- | --- | --- |
| **Bulkhead** | Limits how many tasks in each group can occupy resources concurrently | 8 in-flight for backend A, separate capacity for B |
| **Rate limiter** | Limits how many requests are initiated over time | 100 requests/second |
| **Circuit breaker** | Temporarily stops calling a repeatedly failing backend per policy | Open circuit when error rate is high |
| **Timeout/deadline** | Limits wait/execution time | 500 ms request deadline |
| **Load shedding** | Drops excess load to preserve serving capacity | Reject low-priority work when saturated |

These mechanisms complement one another. A bulkhead does not detect that a dependency is broken on its own, a timeout does not allocate per-group quotas, and a circuit breaker does not partition thread pools.

## 11. Observability and Testing Isolation

Track metrics **per bulkhead**, including active workers/permits, queue depth, wait time, rejection count/rate, timeouts, cancellations, p95/p99 latency, and connection hold duration. Also monitor shared CPU, heap, GC, and DB connections: two bulkheads may still share a physical bottleneck.

Meaningful tests:

- Hold all slots of group A using a `CountDownLatch` or a simulated slow server; send extra load exceeding A's queue.
- At the same time, continuously submit valid work to group B. Verify B still completes within its latency threshold.
- Verify A is rejected according to policy, does not leak permits on exception/interruption/cancellation, and recovers after the bottleneck clears.
- Test slow downstream, timeouts, bursts, retries, and shutdown. Use latches for coordination rather than relying on `Thread.sleep()` and non-deterministic scheduling.

If group B also slows down significantly, check which real resource is still shared: CPU, heap, DB pool, sockets, log I/O, locks, or another executor.

## 12. Common Mistakes

- Using a single shared executor for all blocking tasks: a slow dependency exhausts all workers.
- Using `newFixedThreadPool` and assuming the backlog is bounded: the queue can grow uncontrollably.
- Increasing thread counts arbitrarily without increasing downstream capacity: increases context switching and contention.
- Creating a `Semaphore` per request: the global quota has no effect.
- Calling `release()` before an async operation actually completes, or releasing multiple times: breaks the limit.
- Setting a timeout only when acquiring a permit while forgetting I/O timeouts afterward.
- Retrying immediately on rejection: piles more load onto an already saturated component.
- Splitting executors without measuring shared DB connections/CPU/heap.
- Not tracking rejections and queue wait per group: impossible to tell whether the bulkhead is protecting the system.
- Forgetting shutdown, interruption handling, or releasing permits when operations end.

## 13. Application Checklist

1. Map the execution path of each group and pinpoint the exact contended resource.
2. Choose a dedicated pool to isolate workers/queues; choose a semaphore to cap in-flight calls; limit connections at the layer that owns them.
3. Set concurrency budgets, bounded queues, timeouts, cancellation, and overload responses.
4. Share the limiter instance properly; guarantee permit/resource release on all exit paths.
5. Throttle or stall one group in a controlled test and verify healthy groups remain unaffected; monitor and tune.

**Core takeaway:** a bulkhead shrinks the **blast radius** of a slow or overloaded part of the system. Success is measured by bounded capacity, controlled latency, and the ability to keep serving healthy groups—not by trying to avoid all rejections.
