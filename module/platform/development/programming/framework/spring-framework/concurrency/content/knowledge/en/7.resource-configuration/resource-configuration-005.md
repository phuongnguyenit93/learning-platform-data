# Distinguishing Concurrency Limits from Time-Based Request Rate Limits

> **Scope:** Spring Framework – concurrency, resource configuration section. This lesson explains two system protection mechanisms commonly confused with each other: **concurrency limit** (limiting how many operations are actively running at the same time) and **rate limit** (limiting how many requests are allowed to start within a time window). They measure different quantities, mitigate different risks, and often need to work together.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish in-flight/concurrent requests (*in-flight/concurrent requests*) from request throughput over time (*requests per second – RPS*, *requests per minute – RPM*).
2. Explain why a limit of 10 concurrent tasks does not mean 10 requests/second, and why a limit of 100 requests/second does not mean at most 100 tasks running simultaneously.
3. Use a `Semaphore` or bulkhead to cap concurrent work; understand fixed window, sliding window, and token bucket algorithms for rate limiting.
4. Connect these limits to `ThreadPoolTaskExecutor`, HTTP controllers, `@Async` tasks, and multi-instance Spring deployments.
5. Distinguish decisions around queueing, rejecting, waiting, HTTP 429, and 503; set limits that are observable and testable.
6. Write and run a Java 17 example with deterministic output, without relying on `Thread.sleep` as proof of correctness.

## 2. Two Limits Answer Two Different Questions

### 2.1. Concurrency Limit

A **concurrency limit** constrains how many tasks currently **hold the right to use a resource** at one instant.

For example: a semaphore with **8 permits** allows at most 8 calls to a report-processing service to execute at the same moment inside one JVM. The ninth call must wait or be rejected, depending on program policy. When a task finishes or fails, it **releases its permit** for another task to use.

Notation:

~~~text
In-flight(t) = number of jobs that entered the protected region
               but have not yet left that region at time t

Requirement: In-flight(t) <= C at all times t
         C = concurrency limit
~~~

The unit of `C` is **active in-flight jobs**, not jobs/second.

The scope of "in-flight job" must be defined upfront: an HTTP request from controller entry to response completion, a downstream call, a task executing in a worker, or tasks sitting in a queue as well? Those are different scopes; a limit is only meaningful if permits are acquired and released at the exact intended boundary.

### 2.2. Time-Based Request Limit (Rate Limit)

A **rate limit** constrains how many **entries are accepted/started** within a time period, or the average admission rate under an algorithm.

For example: a user may start at most **60 requests in 60 seconds**. Each accepted request typically consumes one unit of quota; the request finishing **does not immediately refund that unit**. Permission continues to be granted as time/windows/tokens refresh according to the algorithm.

A simple window model:

~~~text
Accepted(user, window_60s) <= 60

Unit: requests / 60 seconds (or requests/second)
~~~

Rate limits can be tracked per user, API key, IP, tenant, endpoint, whole service, or a combination of criteria. A service-wide quota and a per-client quota cannot substitute for each other.

### 2.3. Core Comparison Table

| Criterion | Concurrency Limit | Time-Based Rate Limit |
| --- | --- | --- |
| Question | "How many tasks are running/occupying the resource right now?" | "How many requests are allowed to enter within this time interval?" |
| Quantity | In-flight count, held permits | Requests/second, requests/minute, tokens/period |
| Unit | **Concurrent** jobs/requests/calls | Jobs/requests/calls **per unit of time** |
| When acquired | Before entering the protected resource region | When the request is admitted under the quota |
| When released/refilled | When work completes, fails, or cancels; typically in `finally` | Over time or refill schedule; task completion does not refund tokens |
| Common mechanisms | `Semaphore`, semaphore bulkhead, active worker cap | Fixed/sliding window, token bucket, rate limiter |
| Mitigated risks | Exhausting connections/workers/memory due to many long-running tasks | Bursts, rapid polling, exceeding partner quotas, per-user abuse |
| Guarantees the other limit? | **Does not guarantee RPS** | **Does not guarantee in-flight count** |
| Deployment scope | One JVM, service, pool, or cluster-wide with a shared coordinator | One process, API key, gateway, or cluster-wide depending on quota store |

**Quick rule:** concurrency limit is **capacity at an instant**; rate limit is **throughput allowed over time**.

## 3. Intuitive Example: Same Limit, Very Different Throughput

Suppose a service allows at most **10 concurrent requests**.

- If each request takes **0.05 seconds** on average and work is always waiting, in an ideal model without overhead or other bottlenecks, capacity is roughly `10 / 0.05 = 200 requests/second`.
- If each request takes **5 seconds** on average, the same 10-concurrent-request limit yields roughly `10 / 5 = 2 requests/second`.

Therefore, saying "the pool has 10 threads so the API is capped at 10 RPS" is wrong. Thread count bounds parallelism of work running in the pool, whereas completed tasks per second also depend on task duration and other resource limits. If there is a queue, accepted-but-queued tasks diverge even further from active threads.

In the opposite direction, suppose you allow **100 requests/second** and each request takes **10 seconds** on average. If traffic stays steady long enough with no other cap, average concurrent requests can approach `100 × 10 = 1,000`, even while fully obeying the rate limit. A service with 50 downstream connections will quickly overload without an appropriate admission/concurrency control layer.

### A Quick Visualization

~~~text
RATE LIMIT:          100 entries allowed to start within 1 second
                       | | | | | | | | ...
                       v v v v v v v v
                         queue / tasks
                              |
CONCURRENCY LIMIT:        [ 8 held slots ]
                          [request 1 ... 8]
                              |
                          complete -> release slot
~~~

The two layers can sit at different places: rate limiting at the API gateway, concurrency limiting close to the downstream/database. Their order and placement decide which resource is protected first.

## 4. Mathematical Relationship: Little's Law

In a **stable** system, looking at long-term averages with a consistently defined scope, **Little's Law** states:

\[
L = \lambda W
\]

Where:

- `L`: average number of tasks **inside the system under consideration**.
- `λ`: average rate of tasks passing through the system, in tasks/second.
- `W`: average time a task spends in the system, in seconds.

If measuring only the service processing segment, `W` is the corresponding resource hold time; if measuring queue plus processing, `W` must include **queue wait time as well**. Never take throughput from one scope and multiply it by latency from another scope.

Examples under steady state:

| Throughput `λ` | Average Time `W` | Average In-Flight `L` |
| ---: | ---: | ---: |
| 20 req/s | 0.1 s | 2 |
| 20 req/s | 1 s | 20 |
| 20 req/s | 5 s | 100 |
| 100 req/s | 0.2 s | 20 |

Notice: **at the same RPS, rising latency drives up in-flight count**. When a downstream slows down, rate limiting alone is usually insufficient to protect connection pools or memory.

Little's Law is a relationship of **averages**; it does not prove maximum in-flight count and does not replace checking p95/p99, bursts, queues, or timeouts. You cannot derive a hard concurrency cap from an RPS number alone.

## 5. How Does a Concurrency Limiter Work?

A typical pattern uses `Semaphore(C)`:

~~~text
Incoming request
    |
    v
Try to acquire permit
    |
    +-- Permit available: active++ -> do work -> finally release -> active--
    |
    +-- No permit left:
           +-- Reject immediately
           +-- Or wait with a bound (timeout, queue)
~~~

Crucially: a permit must only be released if acquired successfully, and must be released **exactly once** across all completion, exception, and cancellation paths.

Java example:

~~~java
Semaphore slots = new Semaphore(8);

if (!slots.tryAcquire()) {
    throw new IllegalStateException("capacity exhausted");
}

try {
    performBlockingWork(); // At most 8 invocations inside this region
} finally {
    slots.release();
}
~~~

**Illustrative snippet:** a real `performBlockingWork()` is required in the application. `tryAcquire()` does not wait; thus the ninth request is rejected immediately. If using `tryAcquire(timeout, TimeUnit.MILLISECONDS)`, callers may wait and hold the request thread; pick a sensible timeout, handle `InterruptedException`, and assess resource impact.

### Limiting "Running" Differs from Limiting "Accepted into Queue"

Where permits are acquired matters:

1. **Right before submitting to the thread pool:** the permit may be held during **queue wait** as well, and released only after the task finishes. This bounds total accepted-but-unfinished jobs, useful for capping backlog.
2. **Inside the worker right as execution begins:** permits count only **actively executing** jobs, while the queue can hold more tasks, requiring a separate queue limit.
3. **In a synchronous HTTP controller:** the permit wraps the business call, counting invocations inside that region; it does not necessarily match total open request sockets.

No single choice is universally right for every system. Name metrics accurately for their scope, such as `downstream_in_flight`, `executor_active`, and `executor_queued`.

## 6. How Does a Rate Limiter Work?

A rate limiter decides whether to grant a **start allowance** when a request arrives, based on a time policy.

### 6.1. Fixed Window

Allow up to 60 requests per calendar minute:

~~~text
Minute A:  [60 accepted]  [61st: rejected]
Minute B:  [counter resets to 0]
~~~

Pros: easy to understand and implement. Cons: at the **boundary** between two windows, a client can send 60 requests near the end of Minute A and 60 right at the start of Minute B, producing a 120-request burst in a very short span. Hence "60/min fixed window" is not equivalent to "at most 60 in any sliding 60-second span."

### 6.2. Sliding Window

Counts requests within a **rolling time span** (or uses approximations/buckets). This controls boundary bursts better, though state and complexity can be higher than fixed windows. You must define precisely how timestamps determine the window, where state lives, and how cleanup runs.

### 6.3. Token Bucket

A bucket holds at most `B` tokens; the system refills tokens at rate `r` tokens/second. Each request consumes a token (or tokens proportional to cost). Without enough tokens, the request waits or is rejected.

- `r` determines the long-term average refill rate.
- `B` determines the maximum burst absorbable when the bucket is full.
- Consumed tokens are not "refunded" just because a request ends; they replenish over time.

For example, `r = 10 tokens/s` and `B = 20` can absorb a 20-request burst immediately when full, then admit at the refill pace. That is not a guarantee of at most 10 requests in **every** 1-second interval.

### 6.4. Leaky Bucket and Controlled Queueing

A shaper can emit requests at a relatively steady pace, placing excess arrivals into a bounded queue. If the queue is full, reject. This smooths bursts toward downstreams in exchange for queueing latency. **The queue must have a capacity and timeout**: an unbounded queue does not give the system infinite resources.

### 6.5. Time-Based Allowance Does Not Bound Processing Duration

A limit of "10 requests per second" can still produce 100 concurrent invocations if each takes 10 seconds. Therefore, whenever the risk is connection exhaustion or slow tasks holding resources, add a concurrency limiter/bulkhead.

## 7. Runnable Java 17: Simulating Two Independent Limits

The following example uses **one program** to demonstrate:

- `Semaphore(2)` allowing only two tasks to hold permits simultaneously.
- A fixed-window counter allowing only three entries in each 1,000 ms window.
- `CountDownLatch` locking experiment milestones for deterministic output. Fixed-window timestamps are **passed explicitly** for testing; the demo does not claim to be a complete production rate limiter.

Save to **`LimitsDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicInteger;

public class LimitsDemo {
    static final class FixedWindow {
        private final int quota;
        private final long periodMillis;
        private long currentWindow = Long.MIN_VALUE;
        private int used;

        FixedWindow(int quota, long periodMillis) {
            if (quota <= 0 || periodMillis <= 0) {
                throw new IllegalArgumentException("limits must be positive");
            }
            this.quota = quota;
            this.periodMillis = periodMillis;
        }

        synchronized boolean allowAt(long millis) {
            long window = Math.floorDiv(millis, periodMillis);
            if (window != currentWindow) {
                currentWindow = window;
                used = 0;
            }
            if (used >= quota) {
                return false;
            }
            used++;
            return true;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Semaphore slots = new Semaphore(2);
        CountDownLatch bothInside = new CountDownLatch(2);
        CountDownLatch releaseWorkers = new CountDownLatch(1);
        AtomicInteger inFlight = new AtomicInteger();
        AtomicInteger peak = new AtomicInteger();

        Runnable slowJob = () -> {
            if (!slots.tryAcquire()) {
                throw new IllegalStateException("unexpected rejection");
            }
            try {
                int now = inFlight.incrementAndGet();
                peak.accumulateAndGet(now, Math::max);
                bothInside.countDown();

                try {
                    releaseWorkers.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            } finally {
                inFlight.decrementAndGet();
                slots.release();
            }
        };

        Thread first = new Thread(slowJob);
        Thread second = new Thread(slowJob);
        first.start();
        second.start();

        bothInside.await(); // Ensure both are holding permits.
        boolean thirdAccepted = slots.tryAcquire();
        if (thirdAccepted) {
            slots.release();
        }

        System.out.println("inFlight = " + inFlight.get());
        System.out.println("thirdAccepted = " + thirdAccepted);

        releaseWorkers.countDown();
        first.join();
        second.join();
        System.out.println("peakInFlight = " + peak.get());
        System.out.println("permitsAfter = " + slots.availablePermits());

        FixedWindow rate = new FixedWindow(3, 1_000);
        int accepted = 0;
        for (int i = 0; i < 5; i++) {
            if (rate.allowAt(0)) {
                accepted++;
            }
        }
        System.out.println("t=0ms accepted = " + accepted);
        System.out.println("t=999ms accepted = " + rate.allowAt(999));
        System.out.println("t=1000ms accepted = " + rate.allowAt(1_000));

        // Two adjacent windows each have their own quota.
        FixedWindow boundary = new FixedWindow(3, 1_000);
        int boundaryAccepted = 0;
        for (int i = 0; i < 3; i++) {
            if (boundary.allowAt(999)) boundaryAccepted++;
        }
        for (int i = 0; i < 3; i++) {
            if (boundary.allowAt(1_000)) boundaryAccepted++;
        }
        System.out.println("boundaryAccepted = " + boundaryAccepted);
    }
}
~~~

Compile and run on JDK 17+:

~~~bash
javac LimitsDemo.java
java LimitsDemo
~~~

**Deterministic stdout:**

~~~text
inFlight = 2
thirdAccepted = false
peakInFlight = 2
permitsAfter = 2
t=0ms accepted = 3
t=999ms accepted = false
t=1000ms accepted = true
boundaryAccepted = 6
~~~

**Why is the output deterministic?**

1. Two workers acquire both permits and call `bothInside.countDown()` after incrementing `inFlight`; main proceeds only after both have entered the protected region.
2. Both workers wait on `releaseWorkers.await()`, so main's `tryAcquire()` is guaranteed to fail and print `false`.
3. Main releases the latch and calls `join()` before checking peak/permits, avoiding races in observing the result.
4. The fixed-window counter is invoked with simulated timestamps `0`, `999`, `1000`, without relying on wall-clock time or `sleep`.
5. `boundaryAccepted = 6` shows three entries at the end of one window and three at the start of the next window are all accepted, even though the two timestamps are only **1 ms** apart.

**Limitations of the example:** `FixedWindow.allowAt` synchronizes within a single JVM object and lets callers pass timestamps. Production systems must use a reliable time source, handle clock skew, state cleanup, atomic locking, and multiple replicas; use a proper library/gateway instead of copying this class to production.

## 8. Applying Concurrency Limits in Spring MVC

For a **synchronous** HTTP endpoint, you can declare a semaphore as a bean and wrap the business call with permits.

### 8.1. Configuration Bean

In a Spring Web project with matching component scanning, file **`CapacityConfiguration.java`**:

~~~java
import java.util.concurrent.Semaphore;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CapacityConfiguration {
    @Bean("reportSlots")
    public Semaphore reportSlots() {
        return new Semaphore(8);
    }
}
~~~

This is a Spring configuration: the container manages one default semaphore instance **per application context**, serving consumers injecting that bean. It does not automatically create a cluster-wide quota when deploying multiple JVMs.

### 8.2. Service Guarding the Processing Block

File **`ReportService.java`**:

~~~java
import java.util.concurrent.Semaphore;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    private final Semaphore reportSlots;

    public ReportService(@Qualifier("reportSlots") Semaphore reportSlots) {
        this.reportSlots = reportSlots;
    }

    public String generate(long id) {
        if (!reportSlots.tryAcquire()) {
            throw new CapacityExceededException();
        }
        try {
            // In a real application, this is a synchronous business call.
            return "report-" + id;
        } finally {
            reportSlots.release();
        }
    }

    public static final class CapacityExceededException
            extends RuntimeException {
    }
}
~~~

File **`ReportController.java`**:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {
    private final ReportService reports;

    public ReportController(ReportService reports) {
        this.reports = reports;
    }

    @GetMapping("/reports/{id}")
    public String getReport(@PathVariable long id) {
        return reports.generate(id);
    }
}
~~~

These classes are **components of a Spring MVC project**, requiring Web dependencies and a running Spring application; they are not standalone Java SE programs with `main`. Place them in the same package (or add matching `import`s) to reference `ReportService`.

### 8.3. Overload Response

To demonstrate a temporary resource error, file **`CapacityAdvice.java`**:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class CapacityAdvice {
    @ExceptionHandler(ReportService.CapacityExceededException.class)
    public ResponseEntity<String> busy() {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body("Server capacity exhausted");
    }
}
~~~

Here **503 Service Unavailable** represents temporary server overload. When a per-user/client **time-based request quota** is exceeded, **429 Too Many Requests** is usually clearer. This mapping is by intent; the HTTP specification does not mandate one single status code for every permit-exhaustion event.

Returning a string immediately only illustrates the acquire/release structure; it does not simulate long processing. In real projects, the `try/finally` block must enclose the downstream call, data access, or computation being bounded. Never release a permit right after merely **submitting** an async job if that job is still running.

### 8.4. When a Service Returns CompletableFuture or Mono

For asynchronous calls, the resource boundary usually lasts until the work actually **completes, fails, or is cancelled**, rather than just when the scheduling method returns.

Example `CompletableFuture` pattern (assuming `asyncClient.fetch(id)` returns `CompletableFuture<String>` and `slots` is a semaphore):

~~~java
if (!slots.tryAcquire()) {
    return CompletableFuture.failedFuture(
            new IllegalStateException("busy"));
}
try {
    return asyncClient.fetch(id)
            .whenComplete((result, failure) -> slots.release());
} catch (RuntimeException ex) {
    slots.release();
    throw ex;
}
~~~

**Non-standalone illustrative snippet**, requiring context defining `slots` and `asyncClient`. The permit is released by the completion callback or if creating the future throws synchronously. You must also cover cancellation/timeout paths of the real client. With Reactor `Mono`/`Flux`, subscription time, terminal signals, and cancellation carry distinct semantics; constructs like `doFinally(...)` are often suitable for cleanup, provided permits are acquired at subscription time and released exactly once. Never mechanically wrap Publisher construction in `try/finally` assuming the reactive task is already done.

## 9. Is ThreadPoolTaskExecutor a Rate Limiter?

**No.** `ThreadPoolTaskExecutor` manages **workers and a queue** inside one JVM:

~~~java
@Bean("reportExecutor")
ThreadPoolTaskExecutor reportExecutor() {
    ThreadPoolTaskExecutor e = new ThreadPoolTaskExecutor();
    e.setCorePoolSize(4);
    e.setMaxPoolSize(4);
    e.setQueueCapacity(20);
    e.setThreadNamePrefix("reports-");
    return e;
}
~~~

This is a **Spring configuration snippet**, requiring `@Bean`, `ThreadPoolTaskExecutor` imports, and a `@Configuration` class. The container manages initialization and shutdown. With this example config:

- At most **4 workers** in the pool execute tasks simultaneously under normal dispatch.
- Up to **20 tasks can wait in the queue** before rejection occurs, if workers are busy and tasks do not finish in time.
- Very short tasks can process hundreds or thousands of times per second; `corePoolSize=4` does not mean 4 RPS.
- Queued tasks consume RAM and lengthen wait times, even though they are not counted in `getActiveCount()`.
- A rejection handler like `CallerRunsPolicy` can run tasks **on the submitting thread**, so even the assumption "only 4 concurrent executions across the JVM" breaks if caller-runs executes outside the pool. `AbortPolicy` rejects more transparently when no more tasks can be accepted.

**A thread pool bound** is not the same as bounding total in-flight HTTP calls, DB connections, or concurrent downstream invocations. When protecting a specific resource, put a semaphore/bulkhead **right at the boundary calling that resource**.

An executor with a very long queue sometimes hides overload by inflating latency. Measure queue depth, task wait time, and rejected counts. Never build a "rate limiter" merely by calling `Thread.sleep(...)` inside workers: sleeping still holds workers and can create massive backlogs.

## 10. How Do Both Protection Layers Work Together?

Suppose a document lookup API has two constraints:

- Per API key: at most **60 requests/minute**, to enforce fair usage.
- Per service instance: at most **8 concurrent calls to the search system**, because the downstream has finite connections/quotas.

Suggested flow:

~~~text
HTTP / API Gateway
    |
    +-- Authenticate, identify API key / tenant
    |
    v
Rate limiter: 60 requests/minute/key
    |
    +-- Quota exceeded -> 429, optionally with Retry-After
    |
    v
Spring controller / service
    |
    v
Semaphore / Bulkhead: max 8 downstream calls/instance
    |
    +-- No slot -> brief bounded wait or 503
    |
    v
Call downstream -> release permit -> response
~~~

Order can be reversed in other scenarios, provided costs are weighed: doing expensive I/O **before** rate limiting lets quota-exceeding users still consume resources; holding a semaphore while waiting for a rate token consumes permits on waiting rather than business work.

| Configuration Question | Required Answer |
| --- | --- |
| Quota scoped to whom? | Per user, API key, tenant, or whole system? |
| Which event is counted? | Every incoming request, valid request, accepted request, or downstream call? |
| Concurrency bounded at which segment? | Synchronous controller, HTTP client, DB connection, or one task worker? |
| What happens over threshold? | Reject immediately, bounded wait, finite queue, or upstream retry? |
| Sharing scope? | Per process, per pod, per region, or cluster-wide? |
| Needs survival across restarts? | Short-lived local memory quota or durable state? |
| Is bursting allowed? | Maximum burst `B`, period, and window/token-bucket algorithm? |

A system may need both a **rate limiter at ingress** and **concurrency limiters at critical resources**; the two layers count distinct events and can carry separate metrics/policy names.

## 11. Suitable Libraries: Bulkhead and RateLimiter

In Spring applications, you can use **Resilience4j** instead of hand-rolling production limiters:

- **Semaphore Bulkhead**: limits concurrent calls to a dependency (`maxConcurrentCalls`); permits are released when the call scope ends per library contract.
- **ThreadPool Bulkhead**: uses a dedicated pool with a bounded queue to isolate workloads; configure core/max pool and queue.
- **RateLimiter**: grants permissions according to `limitForPeriod` and `limitRefreshPeriod`, with `timeoutDuration` controlling wait time for permission.

An **illustrative** configuration in `application.yml` of a project with a compatible Resilience4j Spring Boot starter installed:

~~~yaml
resilience4j:
  ratelimiter:
    instances:
      partnerApi:
        limitForPeriod: 30
        limitRefreshPeriod: 1s
        timeoutDuration: 0
  bulkhead:
    instances:
      partnerApi:
        maxConcurrentCalls: 8
        maxWaitDuration: 0
~~~

Meaning of the settings: RateLimiter grants up to 30 permits per 1-second cycle under the library's algorithm without waiting when exhausted; Bulkhead allows at most 8 concurrent calls without waiting when full. These are **two independent policies**; this config takes effect only if the app includes the dependencies/aspects/decorators and actually applies them to the intended call.

Example method annotation in an app with Resilience4j AOP enabled:

~~~java
@RateLimiter(name = "partnerApi")
@Bulkhead(name = "partnerApi")
public String requestPartner(String id) {
    return partnerClient.fetch(id);
}
~~~

This is a **method snippet**, assuming `partnerClient` and imports `io.github.resilience4j.ratelimiter.annotation.RateLimiter`, `io.github.resilience4j.bulkhead.annotation.Bulkhead`. When using AOP, understand aspect ordering, self-invocation, async/reactive methods, and how exception mappers handle exceptions (such as `RequestNotPermitted` or `BulkheadFullException`). Never assume annotations work automatically without the starter/config or when calls bypass the proxy.

**Note:** Resilience4j RateLimiter limits per permission/cycle; it does not automatically create a **centralized cross-pod** quota when each pod holds a local limiter. For global quotas, an API gateway or shared state backend is more appropriate.

## 12. Multiple Spring Instances: How Do Limits Add Up?

Suppose **3 pods** are deployed, each configured with:

~~~text
Semaphore(8)
RateLimiter(60 requests/minute)
~~~

If each pod keeps independent state and the load balancer distributes evenly, the cluster-wide effective level **can** reach around **24 concurrent calls** and **180 entries/minute** in an ideal model. Never advertise "8 concurrent system-wide" or "60/minute system-wide" when the implementation only guards each pod locally.

General model:

~~~text
N independent pods, each with C slots   ->  up to roughly N*C slots
N independent pods, each with quota R   ->  may accept up to roughly N*R/period total
~~~

Actual numbers depend on request distribution, churn/rolling deployments, replica scaling, and algorithms; this is not a fixed aggregate guarantee.

To enforce cluster-wide limits:

- **Global rate limit:** enforce at an API gateway or shared state like Redis with **atomic permission-granting operations**. Keys must represent the exact user/tenant/API scope; set proper TTL/expiry and define fallback behavior if the store fails.
- **Global concurrency limit:** requires coordinating lease/slot counts across the cluster, timeouts/heartbeats, and reclamation when a node dies. This is harder than a local `Semaphore`; consider limiting close to the downstream resource instead of distributed locks if architecture permits.
- **Combined:** global rate for fairness/quotas, local concurrency to protect each pod's resources, plus optional caps at the downstream.
- **Clock:** for timing control within one process, use a monotonic source for elapsed time where appropriate; for centralized limiters, rely on store-side clocks/logic to minimize replica clock skew.

If the system autoscales, local quotas change total capacity as pods scale up or down. Explicitly document whether each policy is **per instance** or **cluster-wide** and test during scaling.

## 13. HTTP 429 and 503, Retry-After, and Backpressure

### 13.1. When to Use 429?

**HTTP 429 Too Many Requests** per RFC 6585 indicates a client sent too many requests in a given amount of time. It fits when a user/API key exceeds a rate limit quota. The server can send `Retry-After` to suggest when to retry when the quota policy makes that known.

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
Content-Type: text/plain

Rate limit exceeded
~~~

`Retry-After: 30` indicates a suggested wait of **30 seconds**, not a permit count or concurrency level. Do not invent a wait duration if the algorithm cannot determine when the next allowance becomes available.

### 13.2. When to Use 503?

**HTTP 503 Service Unavailable** per RFC 9110 is commonly used when a service is temporarily unable to handle requests due to overload or maintenance. It can fit when global capacity/bulkheads are full. `Retry-After` may be included when there is a sound basis for predicting the wait interval.

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: text/plain

Service temporarily busy
~~~

The exact status code also depends on the API contract: the same semaphore might implement a **per-client quota** or **server capacity protection**. Analyze the root cause and client contract rather than turning 429/503 into a rigid rule for every case.

### 13.3. "Waiting" Is a Resource Decision

When exceeding a threshold, options include:

1. **Fail fast:** reject immediately, keeping latency low and preventing backlog buildup. Clients should retry with backoff + jitter when valid.
2. **Bounded wait:** allow a short wait, recognizing the request thread/connection still occupies resources while waiting.
3. **Finite queue:** convert bursts into bounded backlog; requires capacity, deadlines, metrics, and cancellation policies.
4. **Persist then process in background:** return a job ID and use a durable queue/job store if business rules allow asynchrony.

Infinite waits, unbounded queues, and unlimited retries can turn a minor hiccup into a pileup of stalled requests. Design timeouts from the request's total deadline, not per-layer settings whose sum exceeds the SLA.

## 14. Choosing the Right Thresholds: Measure First, Then Tune

A practical workflow:

1. **Identify the bottleneck:** 20-connection DB pool, downstream tolerating only 8 concurrent requests, CPU, memory, or 100-req/min partner API quota.
2. **Separate the two requirements:** cap concurrency to protect finite slots; cap rate to control velocity/cost/clients.
3. **Measure workload:** mean and p95/p99 duration, active counts, queue wait, throughput, error rates, timeouts, CPU load, downstream saturation.
4. **Estimate initially with Little's Law:** if target throughput is 40 req/s and mean resource hold time is 0.2 s, roughly 8 in-flight *on average* are needed; add sensible headroom for bursts/tail latency, without treating 8 as a guaranteed optimal hard cap.
5. **Choose rate algorithm:** need a burst of 10? Use a token bucket with matching capacity; need an exact 24-hour quota? Use an appropriate window/counter mechanism.
6. **Bound queues and waits:** enforce deadlines and define responses when capacity runs out.
7. **Apply policies at the right scope:** per-user, per-instance, or cluster-wide; plan how autoscaling affects them.
8. **Load test and chaos test:** steady load and bursts, slow downstreams, timeouts/cancellations, multiple pods, rolling deployments, and rate-limit store failures.

Examples of threshold selection:

| Problem | More Suitable Limit | Reason |
| --- | --- | --- |
| DB has only 20 connections, slow queries | Concurrency cap <= actual resource capacity | Prevents too many queries from contending for connections |
| Partner API grants 300 calls/minute | Stateful rate cap matching the quota's scope | Complies with time-based calling quota |
| Prevent one tenant from monopolizing the API | Per-tenant rate quota + optional concurrency cap | Balances request volume and active resource usage |
| Thousands of fast tasks in a few seconds | Rate bucket with defined burst | Smooths peaks even when execution duration is tiny |
| Some tasks hang for several minutes | Concurrency cap + timeout/cancellation | Rate cap alone does not reclaim held resources |
| Process with multiple executors | Limit per dependency, not just worker counts | Multiple pools may call the same dependency |

## 15. Metrics and Tests for Both Separated Layers

### Concurrency Metrics

- `in_flight`: gauge of permits currently held, labeled by resource scope.
- `available_permits`, failed `tryAcquire` count, permit wait time, timeouts.
- Thread pool: `activeCount`, `poolSize`, `queueSize`, rejection count.
- Slot hold duration, cancelled tasks, and exactly-once permit release verification.

### Rate Metrics

- Accepted/denied requests per interval, API key/tenant (control cardinality).
- Remaining tokens or quota, refresh cycles, token wait counts.
- HTTP 429 rate, actual arrival rate, bursts, and skew across replicas.
- When changing a policy threshold, monitor its impact on latency and 5xxs, not just 429 rates.

### Essential Tests

**Concurrency tests:** use latches so a group of tasks holds slots while extra tasks attempt entry. Assert held count **never exceeds C**, then release and verify permits return even on exceptions.

**Rate tests:** use a **mock clock or clock abstraction** to verify exact windows, refills, boundary crossings, and concurrent competing requests. Avoid `Thread.sleep(1000)` as a pass condition.

**Combined tests:** submit many slow tasks while staying under the RPS quota. The rate limiter may still admit them, yet the concurrency limiter must protect the downstream. Conversely, submit many ultra-fast tasks: concurrency may stay low, yet the rate limiter must block bursts past quota.

**Distributed tests:** start multiple instances sharing a quota key and verify total admitted entries; test scale-up/rolling restarts, store timeouts, and concurrent boundary requests.

When inspecting outcomes, distinguish `allowed`, `queued`, `started`, `completed`, and `rejected`; these five states are not one metric.

## 16. Common Mistakes

1. **"10 workers = 10 RPS."** False: workers bound concurrent execution, while RPS also depends on processing time. With short tasks, RPS can be much higher.
2. **"100 RPS = at most 100 running requests."** False: requests lasting several seconds can produce far more than 100 in-flight requests.
3. **"ThreadPoolTaskExecutor is already a rate limiter."** False: pools and queues do not grant time-based quotas.
4. **"Calling `Semaphore.release()` right when submitting a `Future` works."** False if work continues running; release must tie cleanly to completion/cancellation/exception.
5. **"Tokens return as soon as the response finishes."** False for time-based rate limiters; quotas replenish per policy, not request duration.
6. **"A 60/minute fixed window guarantees at most 60 in any sliding 60 seconds."** False at window boundaries.
7. **"Per-pod limits equal global limits."** False unless pods share state/coordination.
8. **"Large queues make systems healthier for free."** False: they increase wait times and RAM, potentially masking overload until deadlines expire.
9. **"Every semaphore rejection should return HTTP 429."** Not necessarily; when server capacity is temporarily exhausted, 503 may describe the cause better.
10. **"Just raise the concurrency limit to boost throughput."** False when downstream/database/CPU is already saturated; more parallelism can raise latency and error rates.
11. **"Waiting indefinitely for a permit is safe."** False: caller threads and request connections remain held, easily amplifying overload.
12. **"Using `@Async` removes the need for limits."** False: `@Async` only dispatches execution; it neither protects downstreams nor creates rate quotas.
13. **"Checking requests/second alone proves the system is healthy."** False: you also need in-flight counts, tail latency, queues, errors, and saturation.
14. **"An unsynchronized `HashMap` and `System.currentTimeMillis` are enough."** False: rate state can race, wall clocks can jump, and distributed setups add more failure modes.

## 17. Self-Check Questions

**Q1.** An API applies `Semaphore(5)`, handling each request in 100 ms on average. Does that mean at most 5 RPS?

**Answer:** no. `5` is the concurrent job count. In an ideal model with 5 slots continuously busy and 0.1 s per task, throughput is roughly 50 req/s; that number is not guaranteed if overhead or other bottlenecks exist.

**Q2.** An API is rate-limited at 30 requests/second, yet each request takes 4 seconds. Is there a risk of more than 30 in-flight requests?

**Answer:** yes. Under steady load, Little's Law gives roughly `30 × 4 = 120` average in-flight requests unless blocked by another resource.

**Q3.** A pool has 4 workers and a queue of 100. Why are many tasks "accepted" while only 4 are running?

**Answer:** `ThreadPoolTaskExecutor` holds waiting tasks in its queue; `active workers` differ from `accepted/queued jobs`. It is not a rate limiter.

**Q4.** Can a 60 requests/minute fixed window admit 60 entries at the end of the old minute and 60 at the start of the new minute?

**Answer:** possibly, depending on window reset timing. That is the boundary burst issue; consider sliding window/token bucket if tighter burst control is required.

**Q5.** Three pods each use `Semaphore(10)`. Without a shared coordinator, can you report "at most 10 concurrent requests cluster-wide"?

**Answer:** no. When all pods are loaded, total concurrent permits can approach 30; 10 is only a per-pod local threshold.

**Q6.** When using `@Async`, should the semaphore be released right after calling the async method or when the future completes?

**Answer:** if the permit guards the executing async work, release must tie to **completion/failure/cancellation** of the work, not immediately upon receiving the future, while ensuring it is never released twice.

**Q7.** A user is blocked for exceeding 100 requests/minute; should you return 429 or 503?

**Answer:** 429 describes a client's time-based quota better. If the whole service is overloaded and temporarily rejecting due to exhausted processing capacity, 503 may fit better.

## 18. Pre-Deployment Checklist

- [ ] Clearly documented whether each cap is **concurrency** or **rate**, with explicit units and measurement scope.
- [ ] Concurrency: defined permit acquisition event, release timing, error/cancellation handling, and bounded waiting.
- [ ] Rate: defined algorithm, window/refill, burst, quota key, state storage, and waiting policy.
- [ ] Distinguished **queued**, **running**, **in-flight request**, and **completed** tasks.
- [ ] Separate bounds configured for thread pools, queues, DB connections, and downstreams as needed.
- [ ] Verified behavior across multiple pods and under autoscaling.
- [ ] Designed HTTP 429/503 responses, error messages, and `Retry-After` when determinable.
- [ ] Metrics cover rate, in-flight, queue, latency, and rejections.
- [ ] Tests cover bursts, slow dependencies, cancellation, overload, shutdown, and cluster-wide limits.
- [ ] `Semaphore` or `RateLimiter` is not treated as persistence, idempotency, or job durability.

## 19. Summary

**Concurrency limit** answers: *"How many jobs are allowed to hold the resource at once?"* Permissions are usually **returned when work ends**. **Rate limit** answers: *"How many entries are allowed to start within this period?"* Permissions usually **replenish over time**.

Because arrival rates and task durations vary, the two limits are conceptually independent. In Spring, use a **Semaphore/Bulkhead** to protect in-flight calls to scarce resources, a **RateLimiter/gateway** for time-based quotas, and configure `ThreadPoolTaskExecutor` with bounded queues to manage workers. Measure, test, and accurately document the local/global scope of every limit before scaling the application.

## References

- Java SE 17 — `Semaphore`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html
- Java SE 17 — `ThreadPoolExecutor`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- Java SE 17 — `CountDownLatch`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html
- Spring Framework — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework — `ThreadPoolTaskExecutor` API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Resilience4j — RateLimiter: https://resilience4j.readme.io/docs/ratelimiter
- Resilience4j — Bulkhead: https://resilience4j.readme.io/docs/bulkhead
- [RFC 6585, Section 4 — 429 Too Many Requests](https://www.rfc-editor.org/rfc/rfc6585.html)
- [RFC 9110, Section 15.6.4 — 503 Service Unavailable](https://www.rfc-editor.org/rfc/rfc9110.html)
