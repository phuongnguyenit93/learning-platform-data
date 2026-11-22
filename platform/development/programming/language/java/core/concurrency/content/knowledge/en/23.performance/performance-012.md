# Resource Limits and Backpressure to Protect the System

In a concurrent Java system, adding more threads or accepting more tasks does not increase throughput indefinitely. The CPU has a finite number of cores, the heap cannot hold an endlessly growing queue, a database only has a fixed number of connections, and external APIs have quotas and latency. When the incoming workload exceeds processing capacity for a long enough period, the backlog grows, responses slow down, and timeouts and retries generate new load. **Resource limits** keep the number of tasks occupying resources within a safe range; **backpressure** propagates signals that the receiver cannot keep up back to the sender to regulate the sending rate.

This article covers concurrency in **general Java**, including `Executor`, `BlockingQueue`, `Semaphore`, rate limiting, and `java.util.concurrent.Flow`. Spring-specific integration mechanisms belong to another chapter.

## 1. Load Model: Producer, Queue, Worker, Downstream

```text
Producer(s) -- admission / demand --> [ bounded queue ] --> Worker(s)
     ^                                                   |
     |<-- accepted / back off / rejected / completed ----|
                                                         v
                                               CPU / DB / API / disk
```

- **Producer** is the source generating work: an HTTP handler, scheduler, listener, batch importer, or a thread calling `execute()`.
- **Queue** buffers short bursts and holds pending tasks; a queue does not increase processing capacity on its own.
- **Worker/consumer** executes the work. The number of workers does not necessarily equal the number of tasks that can safely run on the downstream.
- **Admission control** decides whether to accept immediately, wait with a bound, reject, or degrade when the system is full.
- **Backpressure** informs the producer about the downstream's capacity to accept more work. When a demand-control protocol is present, the receiver explicitly specifies the amount of data it wants to receive.

A bounded queue that rejects tasks helps limit the backlog, but **it is not yet a complete backpressure protocol** if the producer ignores the signal and retries indefinitely. Conversely, a queue can be bounded and tasks can be rejected quickly without requiring the producer to be able to pause: what matters is a transparent overload contract.

## 2. Distinguishing Throughput, Concurrency, Queue Depth, and Rate

| Concept | Question | Metric |
|---|---|---|
| Arrival rate | How many new tasks arrive per second? | `incoming/s` |
| Throughput | How many tasks complete per second? | `completed/s` |
| In-flight concurrency | How many tasks are currently running / holding resources? | Active requests, active threads, permits |
| Backlog | How many tasks have been accepted but not yet processed? | Queue size |
| Queue wait | How long does a task wait before being picked up by a worker? | p50/p95/p99 wait time |
| Service time | How long does the execution itself take? | p50/p95/p99 processing time |
| End-to-end latency | How long does it take from request arrival to result? | Queue + service + network |
| Rejection/drop | How much work is not accepted or is discarded? | Rejected/s, dropped/s |

If the arrival rate is 120 tasks/second while the downstream processes at most 100 tasks/second, the backlog grows by approximately 20 tasks per second as long as this state persists. A large queue only delays the time before it fills up and increases tail latency.

In a stable system, Little's Law states: `L = λ × W`, where `L` is the average number of items in the system, `λ` is the **actual completion rate**, and `W` is the average time an item spends in the system. For example, with a throughput of 80 requests/second and an average end-to-end time of 0.25 seconds, there are about `80 × 0.25 = 20` requests in the system. You must measure over the same scope: if `L` only counts running tasks, then `W` must be the execution time, not including queue wait time. Do not use an arrival rate that exceeds throughput to infer a false steady state.

**A queue should be sized based on wait-time and memory budgets**, not just element count. A 1,000-element queue is not useful if a task at the tail has to wait 30 seconds while the client only waits 2 seconds. Each task can also retain a large object graph, so 1,000 `Runnable` instances do not equate to a fixed amount of RAM.

## 3. Executor with a Bounded Queue

`Executors.newFixedThreadPool(n)` limits the number of workers, but its internal queue (`LinkedBlockingQueue`) has no capacity bound set via the factory constructor parameter, so the number of waiting tasks can grow until memory is exhausted. `Executors.newCachedThreadPool()` can grow the number of threads with load and should not be treated as a resource limit. When you need to control both workers and backlog, create a `ThreadPoolExecutor` with a bounded queue and an explicit rejection policy.

A notable behavior of `ThreadPoolExecutor`: first it creates workers up to `corePoolSize`; once core threads are full, it prefers enqueuing work; **only when the queue cannot accept more** does it expand workers up to `maximumPoolSize`; after that, it rejects if there is still no room. Therefore, if you want to avoid queue latency increasing before scaling threads, you must carefully design the queue size and core/max sizes; do not assume max threads will be used immediately.

### Complete Java 17 Example: Rejecting Tasks When Full

Create the file `BoundedExecutorDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class BoundedExecutorDemo {
    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy());

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<?> first = pool.submit(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });

            started.await(); // The single worker is running the first task.
            Future<?> second = pool.submit(() -> { }); // Queue full: 1/1.

            try {
                pool.submit(() -> { }); // No worker or queue slot available.
                System.out.println("Không mong đợi: nhận task thứ ba");
            } catch (RejectedExecutionException e) {
                System.out.println("Task thứ ba bị từ chối");
            }

            release.countDown();
            first.get();
            second.get();
            System.out.println("Hai task được hoàn thành");
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
```

Run from the directory containing the file:

```bash
javac BoundedExecutorDemo.java
java BoundedExecutorDemo
```

Deterministic output:

```text
Task thứ ba bị từ chối
Hai task được hoàn thành
```

`CountDownLatch` synchronizes the point where the first task has occupied the worker, so the second task sits in the queue and the third task is guaranteed to hit the limit. With `AbortPolicy`, `RejectedExecutionException` is thrown at **`submit()`**, not when calling `Future.get()`. Even though the third task is rejected, the first two tasks still complete. The demo uses `awaitTermination` and `shutdownNow` to clean up resources; in a real application, shutdown should be designed according to the contract for unfinished work rather than canceling arbitrarily.

### Rejection Policies When Full

| Policy | Behavior | Notes |
|---|---|---|
| `AbortPolicy` | Throws `RejectedExecutionException` | The caller can respond to overload or perform bounded retries |
| `CallerRunsPolicy` | The caller executes the task while the pool is still active | Creates natural throttling but can block the calling thread; during executor shutdown it may drop tasks |
| `DiscardPolicy` | Drops the task without reporting an error | Use only when task loss is acceptable; the `Future` of a dropped task may never complete |
| `DiscardOldestPolicy` | Drops the task at the head of the queue and retries submitting the new task | Can break ordering, lose older work, or cause starvation |
| Application-written handler | Can wait with a timeout, return an error, or route to a durable queue | Must avoid deadlocks, blocking on an event loop, and races with shutdown |

Do not choose `DiscardPolicy` for tasks that must be preserved (orders, payments, critical data updates). `CallerRunsPolicy` also does not guarantee that every task will be processed after shutdown. If a worker in the pool submits work back into the same full pool and **waits** for a slot to submit a subtask, a deadlock can occur because all workers are busy waiting on a queue that nobody is consuming.

## 4. Semaphore: Limiting the Exact Scarce Resource

A thread pool controls the number of threads in the pool, but an application may have multiple executors, asynchronous callbacks, or virtual threads. If what needs protection is **8 concurrent requests to an API**, use a `Semaphore` close to the API call site.

Compilable Java class example without `main`:

```java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

final class ApiGate {
    private final Semaphore permits = new Semaphore(8, true);

    String call() throws InterruptedException {
        if (!permits.tryAcquire(200, TimeUnit.MILLISECONDS)) {
            throw new IllegalStateException("Downstream đang quá tải");
        }
        try {
            return callApi();
        } finally {
            permits.release();
        }
    }

    private String callApi() {
        return "OK"; // Illustration: replace with the actual API call.
    }
}
```

`tryAcquire(timeout)` ensures the caller waits at most the allowed duration; if it cannot acquire a permit, it rejects. `finally` releases the permit even if `callApi()` throws an exception. **Never release when acquire fails**, and do not perform resource-intensive calls before acquiring. If `tryAcquire` is interrupted, `InterruptedException` propagates; this branch does not hold a permit. Fairness `true` reduces long waits in many cases but has a performance cost and does not guarantee strict ordering at every point.

Permits in a `Semaphore` only apply **within a single JVM**. If there are 5 instances and each allows 8 connections, the system can issue up to 40 concurrent connections. To protect a cluster-wide quota, you need coordinated limiting (at a gateway, shared service, distributed limiter, or verified quota partitioning).

**Java 21+ virtual threads** make waiting on I/O cheaper in terms of platform threads, but they do not create more CPU, database connections, socket quotas, or external API capacity. They still require semaphores, admission limits, deadlines, and backlog management.

## 5. Rate Limit and Concurrency Limit Solve Different Problems

`Semaphore(8)` allows at most 8 **in-flight** tasks; an API quota of 100 requests/second limits the number of **requests started over time**. If each request only takes 1 ms, 8 permits can still pass thousands of requests/second; if each request takes 10 seconds, a rate of 100/s can still lead to too many concurrent requests.

Commonly used techniques:

- **Token bucket:** receives tokens at an average rate `r`, up to `burstCapacity`. Each request consumes a token. Allows bounded bursts while capping the long-term rate.
- **Leaky bucket:** emits requests at a steady pace, with a bounded buffer/wait.
- **Fixed-window or sliding-window counter:** limits the number of calls within a window; fixed-window can allow bursts across the boundary between two windows.
- **Concurrency limiter:** uses a semaphore, worker cap, or adaptive in-flight cap; protects resources held by slow requests.

Systems often need a combination of **rate limit + concurrency limit + bounded queue**. A local rate limiter per JVM is not a cluster-wide quota. When implementing your own token bucket, use a monotonic clock to compute elapsed time rather than relying on a wall clock that can be adjusted, and guard against overflow and token rounding issues.

## 6. Backpressure via `java.util.concurrent.Flow`

Java 9+ provides `Flow.Publisher`, `Flow.Subscriber`, `Flow.Subscription`, and `Flow.Processor`. A subscriber signals demand via `subscription.request(n)`; the publisher adheres to the contract by only emitting `onNext` according to the remaining positive demand after the subscription has been established. This is a structured, signal-based control mechanism.

```text
Publisher ---- onSubscribe(subscription) --> Subscriber
Publisher <----------- request(1) --------- Subscriber
Publisher ---------------- onNext(item) ---> Subscriber
Publisher <----------- request(1) --------- Subscriber
                  ...
Publisher ------------ onComplete() ------- Subscriber
          or onError(error)
```

The `OneAtATimeSubscriber.java` class below compiles standalone without `main`. It only requests more after synchronous `process` finishes:

```java
import java.util.concurrent.Flow;

final class OneAtATimeSubscriber<T> implements Flow.Subscriber<T> {
    private Flow.Subscription subscription;

    @Override
    public void onSubscribe(Flow.Subscription s) {
        this.subscription = s;
        s.request(1);
    }

    @Override
    public void onNext(T item) {
        try {
            process(item);
            subscription.request(1);
        } catch (RuntimeException error) {
            subscription.cancel();
            onError(error);
        }
    }

    private void process(T item) {
        System.out.println(item); // Synchronous processing.
    }

    @Override
    public void onError(Throwable error) {
        System.err.println("Lỗi: " + error.getMessage());
    }

    @Override
    public void onComplete() {
        System.out.println("Hoàn thành");
    }
}
```

`request(1)` does **not** guarantee that the actual data source stops producing on its own. The publisher may have a buffer, an unpausable I/O source, or multiple subscribers at different speeds. When `process` simply offloads work to an asynchronous executor and returns immediately, requesting the next item at the end of `onNext` can cause in-flight work to surge; demand must be returned when **processing actually completes**, and a corresponding semaphore or in-flight counter is usually needed.

`SubmissionPublisher` provides a convenient API, but `submit` can block when there is no buffer, while `offer` has variants for handling insufficient capacity and drop policies. It is **not** a durable queue; the producer still has to decide how to handle excess data. Do not assume system-wide memory is bounded merely because a subscriber uses `request(1)`.

## 7. Deadlines, Timeouts, Cancellation, and Retries

A request can span multiple stages: queue wait, semaphore wait, database, HTTP, and response serialization. If the end-to-end deadline is 800 ms and it has already waited 500 ms in the queue, allowing the downstream call another 2 seconds makes no sense. Propagate the **remaining budget** across stages and drop work that can no longer meet its deadline; for measuring elapsed time within the JVM, use a monotonic time source like `System.nanoTime()`.

`Future.cancel(true)` requests thread interruption and **does not guarantee** that the task stops or rolls back side effects. Blocking tasks should respond to `InterruptedException` and terminate cleanly; if caught and not rethrown, you should generally restore `Thread.currentThread().interrupt()`. With external APIs, a timeout does not tell you for sure whether the peer has executed the request or not.

Unbounded retries can trigger a **retry storm**, especially when multiple layers each retry independently. Use exponential backoff with jitter, bound total retry time/attempts, keep idempotency keys stable, and respect overload signals. Work rejected due to overload should not necessarily be retried immediately. Only return retry guidance when the downstream has a chance to recover; for external APIs, check state and use idempotency to avoid duplicate side effects.

## 8. Bulkheads, Fairness, and Degradation Policies

If a batch import shares the same queue with interactive requests, a long-running batch can cause user requests to time out. A **bulkhead** sets separate quotas for different groups of work or per downstream: one pool for CPU-bound work, one permit budget for a slow API, one queue for background jobs. There must also be a **global cap** so multiple independent pools do not collectively exhaust RAM or CPU.

In multi-tenant applications, one tenant can monopolize all permits. Consider per-tenant quotas, a global cap, service-class priorities, or weighted fair scheduling. Priority is not free: low-priority tasks can suffer starvation. Java's `PriorityBlockingQueue` has no capacity bound in its default constructors; to support priority while still limiting backlog, you need separate admission control.

Under overload, choose an explicit contract:

| Workload characteristic | Choice |
|---|---|
| Interactive request with a short deadline | Reject early, signal overload, provide bounded retry guidance |
| Job that cannot be lost | Write to a durable queue and process idempotently; also rate-limit ingestion |
| Recomputable metrics / cache updates | Drop/coalesce according to a documented policy and count losses |
| Idempotent tasks by key where only the latest result matters | Coalesce requests by key when business semantics truly allow it |
| Temporarily degraded downstream | Limit concurrency, degrade non-essential features, preserve the core path |

Ordering and consistency also matter: a FIFO queue does not guarantee results complete in order when there are multiple workers. When operations must be serialized per business key, partition by key or guard with transactions/versioning rather than hoping the queue itself preserves order.

## 9. Sizing Based on Measurements, Not Hardcoded Numbers

For CPU-bound work with little blocking, the initial worker count usually starts around the number of available CPU cores and is then tuned via benchmarking; adding too many threads can increase context switching. For I/O-bound work, concurrent tasks can exceed the core count, but are bounded by connection quotas, memory, timeouts, and latency. The rule of thumb `threads ≈ cores × (1 + waitTime / computeTime)` can serve as a baseline estimate for a steady workload; it does not replace profiling.

For example, if a system processes at most 100 tasks/second and a 3-second burst arrives at 120 tasks/second, the resulting backlog is approximately `(120 - 100) × 3 = 60` tasks. In a FIFO queue, 60 waiting tasks at a processing rate of 100/s take about 0.6 seconds to drain completely if no new requests arrive and the service rate stays steady. If the maximum allowed wait time is 100 ms, you should **not** choose a queue size of 60 just because it fits in RAM; you must shed load or increase capacity.

A systematic design approach:

1. Identify scarce resources: CPU, heap, DB, API quotas, file descriptors, network bandwidth.
2. Measure sustainable throughput, service latency, p95/p99, and maximum connections/permits; avoid mistaking short peaks for sustainable capacity.
3. Place in-flight limits close to the real resource and size queue capacity according to the **queue wait budget**.
4. Choose a policy when full: bounded wait, reject, allowable drop, coalesce, or durable handoff.
5. Propagate deadlines across stages and control retries so they do not amplify load.
6. Test steady load, bursts, slow downstreams, timeouts, and shutdown; tune based on measurements.

Do not measure only the latency of accepted requests while ignoring rejected ones; observe the end-to-end outcome.

## 10. Observing and Testing Protection Mechanisms

| Test scenario | Expected outcome |
|---|---|
| Tasks accepted within capacity | Complete normally, backlog stays within bounds |
| Burst exceeds workers + queue | Rejection or backpressure occurs per policy, no unbounded RAM growth |
| Downstream 10x slower | Concurrent requests do not exceed permits, wait time stays bounded |
| Producer ignores overload | Rejections are recorded; retry storm does not take down the system |
| Worker throws exception / is interrupted | Permits are released, in-flight counters do not get stuck |
| One tenant sends excessive traffic | Global cap and fairness preserve resources for other workload classes |
| Executor shuts down with queued work | Accepted/completed/rejected are distinguished, critical work is not silently lost |
| Task canceled after causing side effects | No assumption of rollback; retries use idempotency |
| Worker submits subtask into its own full pool | No deadlock from waiting on the same full queue |
| Multiple JVMs share an external quota | Total load does not exceed the committed limit |

Monitor `arrival/s`, `completed/s`, `rejected/s`, `dropped/s`, `activeWorkers`, `queueDepth`, `queueWait`, `permitWait`, `serviceLatency`, `endToEndLatency`, GC, CPU, heap, and active connections. `ThreadPoolExecutor.getActiveCount()` or `getQueue().size()` are observational snapshots that can change instantaneously; do not treat them as exact transactional records. Instrument metrics at the admission gate and at completion to derive reliable accept/reject rates.

Load testing should include bursts, long-running (soak) tests, downstream faults, timeouts, and concurrent cancellation. If queue depth grows while completion rate flattens, the system has exceeded capacity; if p99 latency rises while CPU is low, the bottleneck may be locks, queues, the DB, or external APIs rather than a lack of threads.

## 11. Common Mistakes

- **Limiting only threads:** ignoring that the queue can grow without bound.
- **Increasing queue size to "never reject":** masks overload, increasing memory usage and tail latency.
- **Adding virtual threads to fix every bottleneck:** downstream quotas and connection limits do not change on their own.
- **Using a JVM-local semaphore for a cluster-wide quota:** the number of instances multiplies the permit count.
- **Using a rate limit instead of a concurrency limit:** slow requests still pile up.
- **Treating `Flow.request(1)` as a limit on all buffers:** upstream or async processing can still hold a lot of work.
- **Waiting indefinitely under the assumption that it is backpressure:** blocked producers can exhaust all threads and deadlock the system.
- **Choosing `DiscardPolicy` for critical tasks:** loses data without notifying the caller.
- **Retrying immediately on overload:** amplifies load right when the downstream is weakest.
- **Treating timeout/cancel as proof that a task had no effect:** side effects may have already occurred.
- **Looking only at average throughput:** ignores tail latency, rejections, fairness, and SLAs.

Guiding principle: place limits directly at the resource you need to protect; size queues by the latency budget; propagate overload signals early enough for producers to react; keep task states explicit and use timeouts, cancellation, retries, and idempotency appropriately. **The goal is not to accept every task, but to keep the system behaving predictably when load exceeds serving capacity.**
