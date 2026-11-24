# Do Not Retry Immediately and Worsen Overload

> **Module:** Spring Framework – concurrency  
> **Parent topic:** Overload and Rejection  
> **Objective:** Understand why retrying immediately after rejection or transient errors can turn overload into a cascading failure; learn how to design attempt limits, deadlines, backoff, jitter, and retry coordination without overloading the executor further.

## 1. The Problem: A Busy System Is Forced to Do Even More Work

Suppose a Spring `ThreadPoolTaskExecutor` has all workers busy and its queue full. Calling `execute()` or `submit()` is rejected according to the pool's policy (for example, `AbortPolicy` leading to `TaskRejectedException`). The author sees the error and immediately calls it again:

~~~java
for (;;) {
    try {
        executor.execute(task);
        break;
    } catch (TaskRejectedException rejected) {
        // Retry immediately again, with no limit.
    }
}
~~~

This is an **anti-pattern**, not code to adopt: `executor`, `task`, and Spring imports are omitted. The loop can burn CPU on the calling thread, resubmitting the exact same work thousands of times per second without creating a single worker or queue slot. If hundreds of requests do the same thing, the "error recovery" mechanism itself chokes the application further.

When the issue lies in an external service, the situation is similar: if a backend returns `429 Too Many Requests`, `503 Service Unavailable`, or times out from overload, every caller retrying immediately adds extra requests at the exact moment the backend needs reduced load to recover. Retry requests consume the same connection pools, CPU, threads, and network, lengthening response times for new requests as well.

**Principle:** Failure due to overload is a signal to **slow down or stop admitting more work**, not a signal to spin in an immediate retry loop.

## 2. The Positive Feedback Loop That Creates a Retry Storm

A typical load-amplification loop:

~~~text
Many new requests
       |
       v
Pool/DB/downstream already near overload
       |
       v
Long queue wait, deadlines breached, rejections/timeouts rise
       |
       v
Callers retry immediately -> higher submission/call rate
       |
       v
More CPU + threads + connections + queue contention
       |
       v
Latency and errors rise -> even more retries -> loop repeats
~~~

A **retry storm** is a wave of retry requests that sustains or worsens overload. When many clients retry on the exact same cadence, a *thundering herd* also occurs: crowds of requests hit the backend at the exact instant it opens capacity again.

Retrying can help when errors are brief, infrequent, and the system has time to recover. Yet when the cause is **sustained capacity exhaustion**, each retry is another request consuming resources and likely to fail again.

## 3. By the Numbers: How Many Calls Can One Request Turn Into?

Suppose there are 1,000 business requests/sec. If every failed request is allowed up to **four execution attempts** (initial attempt + three retries) and the backend keeps failing, the *attempt* rate can hit **4,000/sec**. If the backend can sustain only 800/sec, 4,000 attempts do not produce more successes; they make queuing and recovery harder.

If the probability of a single attempt failing is `p`, assuming independent attempts with equal failure probability, the expected number of attempts with at most `k` executions is:

`E[attempts] = 1 + p + p² + ... + p^(k-1)`

For example, `p=0.8`, `k=4`: expectation `1 + 0.8 + 0.64 + 0.512 = 2.952` attempts per request. This is only an explanatory model; in reality, overload failures are usually **not independent**: consecutive attempts during a congestion window may all fail.

Another hazard is **multi-layer retries**. If the gateway, an intermediate service, and the DB client each allow three attempts independently, one top-level action can generate up to `3 × 3 × 3 = 27` calls at the lowest layer when every layer exhausts its attempts. Clearly assign which layer owns retries to avoid unintended multiplication.

## 4. Distinguish Three Failure Cases Before Retrying

| Case | Meaning | How to react |
| --- | --- | --- |
| `TaskRejectedException` right upon submitting to Spring executor | Pool is not accepting more work under its current policy, or is closing | Do not resubmit immediately; return backpressure, schedule a bounded delay if allowed, or move work to a durable queue |
| Task was accepted, yet calling another service timed out/`429`/`503` | Work may have partially executed; outcome at destination may be unknown | Verify transient failure, idempotency, deadline; may retry with backoff and respect backend guidance |
| Permanent error: invalid data, invariant violation, bug, unauthorized | Retrying will not make the request valid | Fail fast; return an error matching the root cause and fix input/code/permissions |

**Important note:** `TaskRejectedException` can arise **synchronously from the submission call**, whereas an exception inside an accepted `Runnable` does not necessarily return to the caller thread. With `submit()`, task errors can be captured inside the `Future`; you need `Future.get()` or an appropriate observer. Never catch errors on `submit` and assume you have covered all runtime execution failures.

Moreover, a timeout does not prove a remote operation **never happened**. If a payment request was committed yet the network response was lost, retrying without an idempotency key can cause a duplicate charge.

## 5. Backoff: Giving the System Time to Regain Capacity

**Backoff** is an intentional pause before the next retry attempt. Instead of trying right away, the client spaces out calls and stops after a bounded budget.

An easy-to-understand formula is **capped exponential backoff**:

`delay(n) = min(maxDelay, baseDelay × 2^(n-1))`

Where `n = 1` is **the first retry after the initial attempt fails**, `baseDelay` is the base wait interval, and `maxDelay` prevents wait times from growing unboundedly.

With `baseDelay = 200 ms` and `maxDelay = 1,600 ms`:

| Retry attempt n | Wait before retry without jitter |
| --- | ---: |
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1,600 ms |
| 5 onward | 1,600 ms (capped) |

This is only **a delay calculation**, not an instruction to "keep retrying forever." A complete policy also caps total attempts, business deadlines, and service-wide retry volume.

Do not use `Thread.sleep()` on a worker of the overloaded pool itself to perform backoff. That occupies a worker idly, shrinking already scarce processing capacity even further.

## 6. Why Is Exponential Backoff Alone Still Not Enough?

If 10,000 clients fail simultaneously and all follow the sequence `200 ms → 400 ms → 800 ms`, they can still fire thousands of requests at **the exact same instant** after each interval. The retry wave is delayed, yet still synchronized.

**Jitter** adds random variation to the wait interval to spread retry attempts across time. Several common policies:

| Policy | How delay is chosen | Characteristics |
| --- | --- | --- |
| No jitter | Fixed `delay(n)` for all clients | Easy to implement, yet easily synchronizes retries |
| Full jitter | Random in `[0, delay(n)]` | Strong dispersion; can pick 0, so consider requirements against immediate retries |
| Equal jitter | Random in `[delay(n)/2, delay(n)]` | Guarantees a minimum pause while still dispersing retry attempts |
| Server-guided jitter | Respect `Retry-After`, add spread if contract and deadline permit | Reduces contention when the server already knows minimum recovery time |

With the goal of **never retrying immediately**, equal jitter is a clear illustrative choice: the first retry waits `100–200 ms` when the nominal delay is `200 ms`; the second waits `200–400 ms`, and so on. This is **not** an optimal formula for every workload; intervals must reflect SLOs, recovery times, caller counts, and processing deadlines.

Each instance should have a suitable random source so clients do not generate identical delay sequences. There is no need to roll a custom RNG when the JDK already offers `ThreadLocalRandom` or equivalent facilities.

## 7. Attempt Limits, Deadlines, and Retry Budgets

Three bounds address three failure shapes:

1. **maxAttempts:** for example, four total attempts (one initial, up to three retries), then terminate with a clear failure status. Do not confuse `maxRetries=3` with `maxAttempts=3`.
2. **End-to-end deadline:** if the business allows only three seconds, all connections, pool waits, backoffs, and retries must fit within that budget. Do not start a retry if the delay plus expected execution time already exceeds the deadline.
3. **Service-wide retry budget:** even if each request gets at most three retries, total retries across all requests must still be capped. For example, issue a finite number of retry tokens per second or per time window so a burst of errors cannot self-multiply load.

A deadline can stop a request from retrying even before reaching `maxAttempts`; a retry budget can also skip a retry if the overall service is congested. That is the right behavior when the system must protect capacity for fresh requests.

**Measurements are essential:** separate initial calls from retry attempts; track `retry_attempts_total`, `retry_exhausted_total`, `rejected_tasks_total`, retry wait latency, and deadline expirations. Without separating them, retries can disguise themselves as "organic traffic."

## 8. Standalone Java 17+ Example: No Immediate Retry, No Thread Blocking to Sleep

The following example uses `ScheduledExecutorService` to illustrate three attempts: the first two hit transient failures and each is **scheduled after a delay**; the third succeeds. This is a deterministic local simulation requiring no Spring libraries.

Create file **ScheduledRetryDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class ScheduledRetryDemo {
    private static final int MAX_ATTEMPTS = 3;
    private static final ScheduledExecutorService TIMER =
            Executors.newSingleThreadScheduledExecutor();
    private static final AtomicInteger CALLS = new AtomicInteger();
    private static final CountDownLatch FINISHED = new CountDownLatch(1);

    private static long delayMillis(int failedAttempt) {
        return Math.min(800L, 100L << (failedAttempt - 1));
    }

    private static void attempt(int number) {
        int call = CALLS.incrementAndGet();

        if (call <= 2) {
            System.out.println("Attempt " + call + ": transient failure");

            if (number >= MAX_ATTEMPTS) {
                System.out.println("Retry budget exhausted");
                FINISHED.countDown();
                return;
            }

            long delay = delayMillis(number);
            System.out.println("Retry after " + delay + " ms");
            TIMER.schedule(() -> attempt(number + 1),
                    delay, TimeUnit.MILLISECONDS);
            return;
        }

        System.out.println("Attempt " + call + ": success");
        FINISHED.countDown();
    }

    public static void main(String[] args) throws InterruptedException {
        try {
            TIMER.execute(() -> attempt(1));
            if (!FINISHED.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Retry demo timed out");
            }
        } finally {
            TIMER.shutdown();
            if (!TIMER.awaitTermination(5, TimeUnit.SECONDS)) {
                TIMER.shutdownNow();
            }
        }
    }
}
~~~

Run with Java 17 or later:

~~~bash
javac ScheduledRetryDemo.java
java ScheduledRetryDemo
~~~

**Stdout printed by the program** when the machine can execute three tasks within the five-second wait limit:

~~~text
Attempt 1: transient failure
Retry after 100 ms
Attempt 2: transient failure
Retry after 200 ms
Attempt 3: success
~~~

Explanation:

- `TIMER.schedule()` only registers a future run—no immediate retry loop and no `Thread.sleep()` holding a worker during backoff.
- `MAX_ATTEMPTS=3` means at most **three total calls**, not three retries after the initial attempt.
- The example intentionally uses deterministic delays `100 ms` and `200 ms` so stdout is easy to verify. In real systems, add jitter and deadlines.
- This scheduler executes tiny simulated work directly on the timer thread; **never** place slow HTTP calls or DB operations straight on a scheduler thread in large application designs. When the time arrives, the scheduler should **dispatch** work to a bounded executor or enqueue a message back into a queue/job store.
- The example has no durability or multi-JVM coordination: if the JVM dies, in-memory scheduled tasks are lost. If work must finish across restarts, use a durable queue/job store.

### Computing Equal Jitter in Java

The function below separately illustrates choosing a jittered delay, usable in a production service with `retryNumber >= 1` and an attempt-limit policy:

~~~java
import java.util.concurrent.ThreadLocalRandom;

static long retryDelayMs(int retryNumber) {
    if (retryNumber < 1) {
        throw new IllegalArgumentException("retryNumber starts at 1");
    }
    long cap = 200;
    for (int i = 1; i < retryNumber && cap < 1600; i++) {
        cap = Math.min(1600, cap * 2);
    }
    long minimum = cap / 2;
    return ThreadLocalRandom.current().nextLong(minimum, cap + 1);
}
~~~

This is an **illustrative method**, not a standalone compilable Java file because it lacks an enclosing class declaration. With `retryNumber=1` the result lies in `[100,200]` ms; with `retryNumber=2`, in `[200,400]` ms. `nextLong(origin, bound)` has an exclusive upper bound, so `cap + 1` is used to include `cap`. Apply the cap before adding 1 to avoid overflow if parameters change; this example uses a small, safe cap.

## 9. Applying in Spring: Separating Scheduler and Work Executor

Spring Framework provides `TaskExecutor` to execute tasks and `TaskScheduler` to schedule delayed runs. `TaskScheduler.schedule(Runnable, Instant)` schedules a one-shot task at a specified instant. With `ThreadPoolTaskScheduler`, a timer manages triggers; `ThreadPoolTaskExecutor` manages bounded workers.

Spring integration configuration example:

~~~java
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration(proxyBeanMethods = false)
public class RetryInfrastructure {
    @Bean("workExecutor")
    ThreadPoolTaskExecutor workExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(4);
        pool.setMaxPoolSize(8);
        pool.setQueueCapacity(32);
        pool.setThreadNamePrefix("work-");
        pool.setRejectedExecutionHandler(
            new ThreadPoolExecutor.AbortPolicy());
        return pool;
    }

    @Bean("retryScheduler")
    ThreadPoolTaskScheduler retryScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("retry-");
        return scheduler;
    }
}
~~~

This is a **configuration snippet for a Spring project**, requiring an ApplicationContext to load this class and appropriate Spring dependencies. Values `4/8/32` are illustrative examples, not defaults or universal recommendations. Keep executors bounded so overload is visible; a huge queue usually just converts rejection errors into unmonitored backlogs and wait times.

A retry path when **submission is rejected** can be structured as follows:

~~~text
Receive command (operationId, deadline)
             |
             v
Try workExecutor.execute(task)
   | accepted                  | TaskRejectedException
   v                           v
Worker processes and         Check retry count,
records outcome              deadline, retry budget
                               |
                         budget left?
                         /         \
                       yes         no
                       |            |
             delay + jitter     report failure /
                       |        persist state
                       v
             retryScheduler.schedule(
                 () -> resubmit command,
                 Instant.now() + delay
             )
                       |
               retry when due
~~~

This diagram only covers retrying when **executor submission is rejected**. If a worker accepted the task yet execution failed, you need a separate path capturing the worker's result/exception and retrying only genuinely transient failures. `Future.get()` or a suitable completion handler provides observability; never assume `execute` returning normally means business execution succeeded.

**Do not recurse immediately** from `catch(TaskRejectedException)`: if `submitAgain()` calls itself directly inside the catch block, that is still a hot retry loop. Scheduling a callback after a delay is fundamentally different. However, timers can also overload/reject, and in-memory schedules are not durable; production requires clear terminal states, metrics, and fallbacks.

## 10. Place Retries at the Right Layer and Avoid Holding Resources Idly

A deceptively "simple" yet harmful snippet:

~~~java
try {
    doRemoteCall();
} catch (TransientException ex) {
    Thread.sleep(1000);
    doRemoteCall();
}
~~~

This is a **non-standalone anti-pattern** with hypothetical exceptions/dependencies and missing `InterruptedException` handling. Even with a delay, sleeping right **inside a scarce worker** occupies the thread while doing nothing. If many workers sleep together, the pool runs out of slots for new requests. Small, bounded synchronous calls outside a scarce pool may tolerate blocking backoff; evaluate resources rather than banning `sleep` in every context.

For long-running work or large retry volumes, it is better to return control to the caller, record the scheduled retry timestamp in a job store, or register a timer and release the worker. When due, the task is re-dispatched to an executor/consumer with backpressure. Never let unbounded delayed jobs pile up in scheduler memory, since moving a backlog from one queue to another does not solve capacity.

## 11. When Must You Give Up on Retrying and Fail Fast?

Not every error is worth retrying:

- **Bad input, validation errors, `400`, most `401/403` permission errors:** fix input/permissions; retrying immediately or with backoff does not solve the root cause.
- **Business invariant conflicts:** `409` or optimistic-lock conflicts sometimes permit reloading data and reapplying an operation **designed safely for re-execution**, yet never blindly retry every conflict.
- **`429` and `503`:** usually indicate throttling/unavailability; inspect `Retry-After` if present, obey server limits, deadlines, and appropriate jitter.
- **Timeouts and dropped connections:** it is uncertain whether the remote side executed the operation; retry only if the operation is idempotent or has an idempotency key/state check.
- **Programming bugs, cancelled data, operations no longer meaningful:** record the error/route to proper handling instead of burning more resources.
- **Expired deadline, exhausted retry budget, open circuit breaker, system shedding load:** stop retrying and prioritize protecting system capacity.

The error seen by an API client differs from the root cause. A `503` may originate at a gateway or a dependency; use logging/tracing to locate the originating layer and agree on which layer owns retries.

## 12. Idempotency: Avoiding Duplicate Side Effects When Accepted Without Response

Suppose a client calls an order-creation API, the server commits successfully, yet the response is lost. The client times out and retries immediately—or retries one second later—and can still create a duplicate order **if business logic lacks deduplication**.

A stable idempotency key bound to business intent lets the server detect duplicate attempts. When processing the same key multiple times, the server can return the original outcome or maintain a single state, depending on the contract. Unique constraints/transactions, key-indexed result tables, consumer dedupe, and outboxes can all serve as implementation pieces.

Key rules:

1. **Keep the exact same idempotency key across retries** of the same intent; never generate a fresh key per attempt.
2. Distinguish the key of a new business intent from the key of a technical attempt.
3. Define how to handle in-flight attempts, ambiguous failures, and key retention TTL.
4. Never assume `Future.cancel(true)` or a timeout undoes side effects that already occurred.
5. Test duplicates and lost responses before enabling auto-retry on data-mutating or payment operations.

Backoff limits **resource pressure**; idempotency limits **duplicate side effects**. The two mechanisms solve different problems and usually belong together.

## 13. Coordinating With Backpressure, Rate Limits, and Circuit Breakers

| Mechanism | What it solves | Relationship to retry |
| --- | --- | --- |
| Bounded pool/queue | Caps concurrent/waiting tasks in-process | When saturated, reject explicitly instead of accepting unbounded backlog |
| Rate limiting | Caps incoming traffic per client/tenant/service | Reduces baseline load, including retries |
| Backpressure/load shedding | Asks callers to slow down or sheds partial load | Retries must obey these signals |
| Circuit breaker | Temporarily stops calling a persistently failing dependency | Cuts wasted attempts; probes recovery only per policy |
| Timeout/deadline | Prevents operations from holding resources too long | Do not schedule retries past the deadline |
| Exponential backoff + jitter | Spreads retries over time, avoiding synchronized waves | Use only when errors are recoverable and operations are retryable |
| Retry budget | Caps retries system-wide | Prevents bursts of requests from doubling or tripling load |
| Durable queue/job store | Preserves work across restarts, controls retries system-wide | Requires idempotency, monitoring, and poison-pill rules |

`ThreadPoolExecutor`'s **`CallerRunsPolicy`** can force the submitting thread to run tasks itself for backpressure while the pool is active and saturated. This is **a design trade-off**, not a reason to add a hot retry loop; it increases caller latency and demands deadline control. This policy also has special behavior when the executor has shut down, so it cannot be treated as a guarantee that tasks are always accepted.

Spring Framework provides executor/scheduler abstractions and allows integrating protective mechanisms. Choosing specific retry/circuit-breaker libraries (such as Spring Retry or dedicated resilience tools) is an additional architectural decision; **`ThreadPoolTaskExecutor` does not automatically provide backoff-and-jitter retries for every task**.

## 14. Two Real-World Scenarios

### A. Report-Generation Endpoint Rejected at the Executor

**Before:** HTTP handler calls `reportExecutor.submit(job)`; on `TaskRejectedException`, it runs `while(true)` to retry. When the queue fills, request threads get trapped in the loop, CPU spikes, and reports still do not complete.

**After:** decide whether the API is synchronous or job-based. For a synchronous API, return an appropriate overload response (such as `429` or `503` depending on service semantics) with retry guidance so clients do not hammer the endpoint. For critical job APIs, persist the job/idempotency key to durable storage and let workers consume within limits. If a service-internal retry path exists, enforce maxAttempts/deadlines/budgets and a bounded scheduler; never block request threads indefinitely.

### B. Slow Downstream Payment Service

**Before:** three layers all retry immediately on timeout. One payment request explodes into many calls while the payment gateway is slow, risking duplicate charges and choking downstream further.

**After:** consolidate retry ownership in a single layer; reuse the same idempotency key, cap total duration, attempt count, and retry budget. Respect rate limits/`Retry-After`, apply jittered backoff, and query payment status on ambiguous outcomes. For unrecoverable errors or expired deadlines, terminate with recorded failure instead of generating extra load.

## 15. How to Test a Safe Retry Policy

1. **Controlled rejection:** use `CountDownLatch` to hold `ThreadPoolTaskExecutor` workers, fill the queue, and verify new tasks are rejected per policy. Do not write tests relying on `Thread.sleep()` hoping the pool saturates.
2. **No hot retries:** use a fake clock/virtual time or controllable scheduler; measure timestamps between attempts and assert the next retry does not fire immediately.
3. **Max attempts and deadline:** against a permanently failing dependency, verify total call count never exceeds the cap and terminates after the deadline.
4. **Jitter:** verify delays fall within valid bounds; test bounds and fixed seeds at the calculation layer when reproducibility is needed. Avoid asserting an exact random timestamp in integration tests.
5. **Retryable vs non-retryable:** verify input/permission errors are never retried; timeouts with ambiguous outcomes retry only when idempotent.
6. **Concurrent load spikes:** trigger errors for many callers simultaneously; measure total attempts/sec and retry distribution to detect thundering herds.
7. **Partial failures:** simulate a remote call succeeding while its response is lost; verify the idempotency key prevents duplicate records/side effects.
8. **Restart/shutdown:** for critical work, test recovery from the job store; never assume in-memory timers survive a process crash.

Monitor baseline request rate, retry rate, rejections, queue depth, active workers, wait times, error rate, and p95/p99 latency side by side. If **retries rise alongside errors and backlog**, the system may be self-amplifying an incident.

## 16. Checklist When Designing to Avoid Retry Storms

- I have separated **submission-time rejection** from **in-flight task execution failure**.
- I retry only genuinely transient errors and operations safe to retry.
- I enforce `maxAttempts`, an overall deadline, and a service-wide retry budget.
- I use delay/backoff and jitter, with zero immediate retry loops.
- I do not hold scarce workers idle just to sleep during backoff.
- I handle timeouts, cancellations, shutdowns, and scheduler rejections explicitly.
- I respect `429`, `503`, and `Retry-After` signals where appropriate for the contract.
- I guarantee idempotency for side effects whenever duplicates are possible.
- I observe retry rate separately from baseline load, and test saturation plus lost responses.
- I know the final path once retry budget runs out: return error, record failure, route to manual review, or dead-letter per business rules.

**Remember:** When a pool or downstream is overloaded, **immediate retries consume even more of the scarce resource** and create a feedback loop that prolongs incidents. Proper retries must be **conditional**, **bounded**, **jittered**, **idempotent**, and have an explicit stopping point.

## References

- [Spring Framework – Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `TaskExecutor`, `TaskScheduler`, queues, rejection, and scheduling.
- [Spring Framework – TaskScheduler Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/TaskScheduler.html): `schedule(Runnable, Instant)`.
- [Spring Framework – TaskRejectedException Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/TaskRejectedException.html).
- [Google SRE Book – Addressing Cascading Failures](https://sre.google/sre-book/addressing-cascading-failures/): retry storms, randomized backoff, retry budgets, and avoiding multi-layer retries.
- [Java SE 17 – ScheduledExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html): how to schedule tasks without holding workers while waiting.
