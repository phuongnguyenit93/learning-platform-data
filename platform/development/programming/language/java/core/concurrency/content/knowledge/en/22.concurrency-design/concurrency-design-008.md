# Rate Limiting and In-Flight Request Limits in Java Concurrency

Both mechanisms control load, yet they answer **two different questions**:

- **Rate limiting:** how many requests are allowed to start within a unit of time (for example, 100 requests/second)?
- **In-flight limit (concurrency limit):** at any given moment, how many requests may have been admitted for processing and **not yet completed** (for example, 20 concurrent requests)?

A system can comply with 100 requests/second and still overload if each request takes several seconds. Conversely, a limit of 20 running requests can still let thousands of very short requests pass through in a single second. Therefore, many Java systems need **two independent budgets**: the rate of accepting work and the amount of work currently in progress.

## 1. Concepts, Units of Measurement, and Relationship to Latency

| Quantity | Meaning | Example |
| --- | --- | --- |
| Arrival rate (λ) | Number of incoming requests per second | 150 requests/s |
| Admitted rate | Number of accepted requests per second | 100 requests/s |
| In-flight (L) | Number of requests that have started but not yet completed | 20 requests |
| Service time/latency (W) | Time a request remains in the in-flight state | 200 ms |
| Queue length | Number of requests waiting to be admitted for processing | 30 requests |
| Throughput | Number of requests completed per second | 95 requests/s |

A request counts as **in-flight** from the moment it consumes processing budget until it succeeds, fails, expires, or is canceled **and the underlying operation actually finishes**. If you only return a timeout error to the caller while the work is still running, the actual load has not been released.

For a stable system over a sufficiently long observation window, **Little's Law** gives the approximation:

```text
L ≈ λ × W
20 requests ≈ 100 requests/s × 0.2 seconds
```

In this formula, λ must be the rate **actually entering** the system being measured, W is the **average time** at the same measurement boundary, and L is the **average** in-flight level. This is neither a peak-load guarantee nor a way to choose limits solely from p95/p99. For example, at the same 100 requests/s, if the average duration increases from 0.2 to 2 seconds, the average number of backlogged requests rises from about 20 to 200 if there is no blocking mechanism. When the downstream resource can only handle 30 concurrent tasks, queues and latency can grow out of control.

**Distinction:** a rate limit controls the **inflow**; a concurrency limit controls the **busy capacity**; a queue limit controls the **number of waiting tasks**. Limiting the thread count does not completely replace these three mechanisms: a thread can handle multiple asynchronous tasks, and virtual threads can still overload a database or target API.

## 2. Common Rate Limiting Algorithms

### 2.1. Fixed window counter

Time is divided into fixed windows, such as 10:00:00–10:00:59; each request increments a counter and is rejected when the threshold is exceeded. Pros: easy to implement, stores little state. Cons: at window boundaries, a client can send nearly the entire quota at the end of the old window and then nearly the entire quota at the start of the new window, creating a large burst in a very short period.

### 2.2. Sliding window

Tracks usage over a sliding window. **Sliding log** stores the timestamp of each request, which is accurate for a sliding threshold but costly in memory and log cleanup. **Sliding window counter** combines counters from adjacent windows to estimate usage at lower cost, in exchange for some approximation error. Suitable when limiting by the number of requests per minute/hour and boundary bursts are a concern.

### 2.3. Token bucket

A bucket has a maximum capacity of `B` tokens and refills at `r` tokens/second. Each admitted operation consumes one token (or multiple tokens if weighted).

```text
new_tokens = min(B, old_tokens + r × elapsed_time)
accept if new_tokens >= cost; if accepted, subtract cost
```

When the bucket is full, it can immediately accept a burst of up to `B` requests; over the long run, the rate is maintained at approximately `r`. For example, `B = 10`, `r = 5/s` allows up to 10 immediate requests after the bucket refills, and an average of 5 requests/second thereafter. **Bucket capacity is a burst allowance, not an in-flight limit.** Token state must be synchronized because multiple threads can contend for the same bucket.

### 2.4. Leaky bucket / steady pacing

Requests enter a bounded queue and are emitted at a steady pace, smoothing out bursts. If the queue is full, requests must be rejected or subjected to a drop policy; a long queue increases latency. Some literature uses the term leaky bucket for a counter variant equivalent to token bucket, so when designing, explicitly specify **the dispatch behavior and queuing rules**.

**Choosing an algorithm by semantics:** to limit quota within a window, use a window; to allow controlled bursts, use a token bucket; to require a fairly steady processing pace, use pacing/queueing. Limiting by user, API key, tenant, or endpoint requires defining the **quota key** and how to evict state for infrequently used keys.

## 3. Java 17 Example: Thread-Safe Token Bucket

The example below illustrates an **in-JVM** limiter using `synchronized` to protect tokens and a monotonic nanosecond clock. The clock is injected via the constructor for testing without `Thread.sleep`; `AtomicLong` merely serves as a fake clock in `main`. Each call to `tryAcquire()` attempts to take **one** token; if insufficient, it returns `false` immediately.

```java
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.LongSupplier;

public class TokenBucketDemo {
    static final class TokenBucket {
        private final int capacity;
        private final double tokensPerNano;
        private final LongSupplier nanoClock;
        private double tokens;
        private long lastNanos;

        TokenBucket(int capacity, double tokensPerSecond, LongSupplier nanoClock) {
            if (capacity <= 0 || !Double.isFinite(tokensPerSecond)
                    || tokensPerSecond <= 0 || nanoClock == null) {
                throw new IllegalArgumentException("Invalid bucket configuration");
            }
            this.capacity = capacity;
            this.tokensPerNano = tokensPerSecond / 1_000_000_000.0;
            this.nanoClock = nanoClock;
            this.tokens = capacity;
            this.lastNanos = nanoClock.getAsLong();
        }

        synchronized boolean tryAcquire() {
            long now = nanoClock.getAsLong();
            long elapsed = now - lastNanos;
            if (elapsed > 0) {
                tokens = Math.min(capacity, tokens + elapsed * tokensPerNano);
                lastNanos = now;
            }
            if (tokens < 1.0) {
                return false;
            }
            tokens -= 1.0;
            return true;
        }
    }

    public static void main(String[] args) {
        AtomicLong fakeClock = new AtomicLong(0);
        TokenBucket bucket = new TokenBucket(3, 2.0, fakeClock::get);

        System.out.println(bucket.tryAcquire());
        System.out.println(bucket.tryAcquire());
        System.out.println(bucket.tryAcquire());
        System.out.println(bucket.tryAcquire());

        fakeClock.addAndGet(500_000_000L);
        System.out.println(bucket.tryAcquire());
        fakeClock.addAndGet(500_000_000L);
        System.out.println(bucket.tryAcquire());
    }
}
```

Save as `TokenBucketDemo.java`, compile, and run with JDK 17 or later:

```bash
javac TokenBucketDemo.java
java TokenBucketDemo
```

Deterministic output (independent of machine speed):

```text
true
true
true
false
true
true
```

Initially there are three tokens. The fourth call is rejected. At a rate of two tokens/second, each 500 ms advance of the fake clock refills one token. No sleeping, spinning, or spawning threads is needed just to wait for tokens.

**Boundaries of this example:** `synchronized` makes a single instance safe for concurrent calls; it **does not** share quota across multiple JVMs/processes and does not guarantee fairness among threads contending for tokens. `System.nanoTime()` is suitable for measuring elapsed intervals within a process; do not use `currentTimeMillis()` as an elapsed-time clock because the system clock can be adjusted. In real applications, you can construct the bucket with `System::nanoTime`; with multiple keys, you must manage bucket lifecycles and avoid retaining an object indefinitely for every key. `double` arithmetic is fine for illustrating typical rates; systems requiring strict precision/rounding rules should choose an explicit representation and test rounding error.

## 4. Limiting In-Flight Requests with Semaphore

`java.util.concurrent.Semaphore` represents the number of available **permits**. With `new Semaphore(20)`, at most 20 operations are admitted when each operation acquires exactly one permit:

1. **Before** starting work, attempt to acquire a permit with `tryAcquire()` or wait with a timeout using `tryAcquire(timeout, unit)`.
2. If no permit is obtained, **do not start** the intended work; return a rejection/busy result or place it in a bounded queue.
3. If a permit was obtained, `release()` it **exactly once** when the work actually finishes, even on error.
4. Do not `release()` if `acquire` failed; `Semaphore` does not tie ownership to a thread, so an extra release can silently raise the concurrency count above the threshold.

For **synchronous** code:

```java
if (!permits.tryAcquire()) {
    throw new java.util.concurrent.RejectedExecutionException("Busy");
}
try {
    performBlockingOperation();
} finally {
    permits.release();
}
```

The snippet above is an **illustrative pattern** requiring the application's `permits` object and `performBlockingOperation()` method; it is not a standalone runnable Java file. `finally` is necessary because the inner call may throw an exception. However, if the method only **launches** asynchronous work and returns immediately, releasing in `finally` will be **too early**; the release must be attached to the actual completion of the work.

### Complete Java 17 Example: Guarding CompletableFuture

Here each `CompletableFuture` represents an incomplete task. `call` attempts to acquire a permit before invoking the supplier, and releases the permit when the source future completes; if the supplier throws an exception or returns `null`, it also returns the permit. When permits are exhausted, the supplier is not invoked. The demo controls completion manually so the output does not depend on a scheduler.

```java
import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;
import java.util.function.Supplier;

public class InFlightDemo {
    static final class InFlightLimiter {
        private final int maximum;
        private final Semaphore permits;

        InFlightLimiter(int maximum) {
            if (maximum <= 0) {
                throw new IllegalArgumentException("maximum must be positive");
            }
            this.maximum = maximum;
            this.permits = new Semaphore(maximum);
        }

        <T> CompletableFuture<T> call(Supplier<CompletableFuture<T>> operation) {
            Objects.requireNonNull(operation, "operation");
            if (!permits.tryAcquire()) {
                return CompletableFuture.failedFuture(
                        new RejectedExecutionException("Too many in-flight requests"));
            }

            CompletableFuture<T> source;
            try {
                source = Objects.requireNonNull(operation.get(), "future");
            } catch (RuntimeException | Error failure) {
                permits.release();
                return CompletableFuture.failedFuture(failure);
            }
            return source.whenComplete((value, failure) -> permits.release());
        }

        int inFlight() {
            return maximum - permits.availablePermits();
        }
    }

    public static void main(String[] args) {
        InFlightLimiter limiter = new InFlightLimiter(2);
        CompletableFuture<String> sourceA = new CompletableFuture<>();
        CompletableFuture<String> sourceB = new CompletableFuture<>();
        CompletableFuture<String> sourceD = new CompletableFuture<>();

        CompletableFuture<String> resultA = limiter.call(() -> sourceA);
        CompletableFuture<String> resultB = limiter.call(() -> sourceB);
        CompletableFuture<String> rejected =
                limiter.call(() -> CompletableFuture.completedFuture("C"));

        System.out.println("rejected=" + rejected.isCompletedExceptionally());
        System.out.println("inFlight=" + limiter.inFlight());

        sourceA.complete("A"); // A finishes: its permit returns.
        CompletableFuture<String> resultD = limiter.call(() -> sourceD);
        sourceB.complete("B");
        sourceD.complete("D");

        System.out.println("results="
                + resultA.join() + resultB.join() + resultD.join());
        System.out.println("inFlight=" + limiter.inFlight());
    }
}
```

Save as `InFlightDemo.java` and run:

```bash
javac InFlightDemo.java
java InFlightDemo
```

Stdout:

```text
rejected=true
inFlight=2
results=ABD
inFlight=0
```

Call C is rejected while A and B are still incomplete; supplier C is never executed. After A finishes, D can start. `whenComplete` is also triggered when the source completes exceptionally or is canceled, so the permit is returned in those cases **if the source future itself actually completes**.

**Note on cancellation:** `resultA` is a dependent future, distinct from `sourceA`. Canceling the returned future does not automatically cancel `sourceA` or immediately release the permit; in the example, the permit is held until `sourceA` completes. In production code, you must clearly define who owns the source future, how cancellation and deadlines propagate to the task/downstream, and only release when the task is considered finished under the chosen resource boundary. Never release once in a timeout branch and then release again when the completion callback runs.

**Note on fairness:** `new Semaphore(maximum, true)` supports a FIFO policy for queued waiting operations; `tryAcquire()` itself does not fully participate in fairness rules. Fairness can trade off throughput and does not replace bounded queues, deadlines, or SLAs.

## 5. Combining Rate and In-Flight Limits at the Right Boundary

General model:

```text
incoming request
  → identify key/quota
  → check rate token (allow / reject)
  → check in-flight permit (admit / reject or bounded wait)
  → run work
  → work truly finishes (success/failure/cancel)
  → release permit
```

In this diagram, if quota counts **attempts**, a token is consumed even when no permit is available; this can be a valid policy to curb spam. If quota counts **work actually admitted**, the two steps must be coordinated under a different policy: acquire the permit first and then try the token; if tokens are exhausted, release the permit immediately. **Do not hold a permit while waiting for tokens to refill**, as doing so wastes capacity unnecessarily. "Refunding" a token when permits are exhausted must be designed as a consistent operation; naively adding a token back without proper synchronization can exceed the quota.

Choose clearly where each limit applies:

- **Global instance:** protects the total resources of a single JVM; the limit applies only to that instance.
- **Per-key:** prevents a single user/tenant from monopolizing quota; requires key normalization, eviction, and handling high-cardinality keys.
- **Per-downstream:** separate concurrency limits can be set for databases, HTTP connections, devices, or CPU-heavy tasks; measure against actual resources.
- **Per-operation cost:** a request costing 10× resources may need 10 tokens or weighted admission, rather than assuming all requests are equal.

With multiple processes or machines, each instance having its own 100/s bucket means the **total quota can approach the number of instances times 100/s**. If a **cluster-wide** quota is needed, you must use a shared counter/bucket with **atomic** updates (for example, centralized storage with an appropriate script/transaction), or explicitly distribute the budget across instances. Define behavior when the quota store fails, latency spikes, clocks drift, or two requests contend for a token; simply reading and then writing a counter in two separate commands easily causes races. Likewise, the JDK `Semaphore` does not natively provide cluster-wide in-flight limits.

## 6. Waiting, Backpressure, Timeouts, and Queues

`tryAcquire()` is **fail fast**: suitable when callers upstream can handle a busy response and retry appropriately. `tryAcquire(timeout, TimeUnit.MILLISECONDS)` allows **bounded waiting** on blocking threads; the wait time must be accounted for in the overall deadline. `acquire()` can wait indefinitely and easily ties up threads/virtual threads as well as connections, allowing hidden load to accumulate.

Unbounded queues turn a concurrency limit into **unbounded latency growth and memory usage under overload**. For example, `Executors.newFixedThreadPool(n)` uses an effectively unbounded queue; simply tuning the worker count does not mean the system has safe backpressure. If a queue is needed, use a queue with a well-designed capacity, item deadlines, a full-queue policy, and queue-age monitoring.

**Do not use spin loops** repeatedly calling `tryAcquire()`; that burns CPU and is unfair. If you must wait for a token, use scheduled/bounded waiting for the earliest time sufficient tokens will be available; ensure the scheduler does not introduce another unbounded queue. For asynchronous pipelines, prefer composition/callbacks and mechanisms that bound the number of waiting tasks rather than blocking threads just to hold a spot.

When rejecting, you can return a too-many-requests status (such as HTTP 429 for rate/quota constraints) or service-busy status (such as HTTP 503 in overload scenarios), along with a retry delay if it **can be computed reliably**. Do not emit an arbitrary `Retry-After`: in-flight saturation alone does not tell you when a task will finish. Clients need exponential backoff with jitter, bounded total duration, and a retry cap; immediate bulk retries can trigger a **retry storm**. If the API has idempotency/side-effect concerns, evaluate retry safety.

Timeouts must apply as an **end-to-end deadline** across the queue, permit acquisition, and downstream call; a caller-side timeout alone does not guarantee that background work stops. For long-lived work such as streaming, decide when the request stops holding a permit and provide an explicit mechanism to close the source/terminate the task.

## 7. Choosing Parameters from Measurements, Not Guesswork

Suppose a downstream normally completes 100 requests/s with an average latency of 200 ms. Little's Law gives an average in-flight load of about 20. However, you should not set `maxInFlight = 20` from this multiplication alone: there are bursts, long tails, lock contention, stop-the-world pauses, headroom needs, and performance degradation under overload. Start from actual resource capacity (connection pool, CPU, target service limits), validate with load tests, and tune based on throughput, latency, and errors.

A practical process:

1. **Define targets:** sustained load, allowed burst, latency/timeout, per-key quota, and downstream resource thresholds.
2. **Measure baseline:** completed throughput, p50/p95/p99 latency, in-flight count, saturation, and error rate across load levels.
3. **Set the long-term rate** below the measured sustained rate if headroom is needed; choose `capacity` based on the burst the downstream can absorb.
4. **Set max in-flight** according to real resources and test scenarios where latency increases several-fold; avoid letting hundreds of tasks pile up on a 20-connection pool.
5. **Define overload behavior:** reject early, wait very briefly with a deadline, or use a bounded queue; do not open an unbounded queue to "hold" every request.
6. **Test abnormal conditions:** many concurrent clients, slow/hung tasks, downstream errors, timeouts/cancellations, hot keys, autoscaling, and retries.

Metrics to monitor:

| Metric | What to watch |
| --- | --- |
| `requests_attempted_total`, `rate_rejected_total` | Total attempts and rate-limiter rejections; split by key with cardinality control |
| `concurrency_rejected_total` | Requests that failed to acquire an in-flight permit |
| `inflight_current`, `inflight_limit` | Permit utilization and how long it stays near the ceiling |
| `queue_depth`, `queue_wait_seconds` | Whether the queue grows continuously and whether waits exceed deadlines |
| `request_duration_seconds` (p50/p95/p99) | Latency of admitted work; distinguish queue time |
| `downstream_errors_total`, `timeouts_total` | Failures, timeouts, and whether downstream is saturating |
| `completed_total` / throughput | Whether the limiter stabilizes throughput or throttles too aggressively |

Attaching every user ID directly as a metric label causes **high cardinality**; typically measure totals and bounded groups, and use separate logs/audits when per-client tracing is needed. Peak gauges aggregated per second/minute can hide short bursts; choose an appropriate observation resolution.

## 8. Design Pitfalls and How to Test

**Confusing rate with concurrency:** "50 requests/s" does not limit "50 concurrent requests." Write two separate tests: an immediate burst with a full bucket, and multiple futures intentionally left incomplete.

**Releasing too early:** returning the permit right after creating a `CompletableFuture` allows actual operations to exceed the ceiling. Tie the release to the completion of the source representing the real operation.

**Leaking or double-counting permits:** forgetting to release on failure paths gradually stalls the system; releasing twice defeats the limit. Every successful acquire must have exactly one release, including when the supplier throws or on cancellation.

**Unbounded waiting:** tasks queued longer than their deadline still get executed, wasting resources and inflating tail latency. Enforce queue/wait-time bounds and re-check the deadline before execution.

**Using system clock for refills:** clock adjustments/NTP can cause erratic token refills. Use monotonic elapsed time within a process; if distributed, use a time/logic source consistent with the state store.

**Missing race checks:** `if (count < limit) count++` is non-atomic and can overshoot. Use proper synchronization/atomic CAS loops or an atomic store if shared across processes.

**Quota multiplied on scale-out:** each machine independently applying the full budget causes the total allowed rate to grow with the number of machines. Document whether quota is per-instance or global and test with multiple instances.

**Forgetting side-effect policies:** if a request times out while a write command continues, a retry can create duplicate operations. Combine deadlines, cancellation where feasible, and idempotency for operations that need it.

A minimal test suite should cover:

- **Token bucket:** a full bucket accepts up to `capacity` immediate requests; the next request is rejected; advancing a fake clock by the expected interval produces a new token; multiple threads contending on the same instance never exceed total tokens.
- **In-flight:** creating `N` incomplete futures causes the `(N+1)`-th future to be rejected and its supplier not to run; after one source completes, a new task can enter.
- **Errors:** a supplier throwing an exception, a future completing exceptionally, and a source future being canceled all return the permit; an exception before acquiring a permit does not trigger a release.
- **Cancellation/timeout:** a late completion callback does not cause a double release; caller timeouts are distinguished from a still-running source.
- **Overload:** queues never exceed capacity or deadlines, throughput does not collapse from retry storms, and per-key limits remain independent while global limits still hold.

## 9. Practical Conclusion

In Java concurrency, a **rate limiter** quantifies *how much work is admitted over time*, whereas an **in-flight limiter** quantifies *how much work can hold resources simultaneously*. Token bucket is a straightforward choice for rates with bursts; `Semaphore` is an effective building block for single-JVM concurrency limits. Combining the two only solves the problem completely when paired with **accurate completion boundaries, deadlines, backpressure, bounded queues, observability, and distributed policies** suited to your system.