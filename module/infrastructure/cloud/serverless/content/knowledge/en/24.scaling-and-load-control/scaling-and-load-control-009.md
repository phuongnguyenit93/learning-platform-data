# Handling downstream throttling and allocating retry budgets

## Learning objectives

After this lesson, you will be able to:

- Identify downstream throttling and distinguish it from network errors, application errors, or ingress rate limits.
- Explain why autoscaling and retries can amplify load onto databases, APIs, or queues.
- Classify retryable errors vs. errors that require stopping immediately.
- Design retry budgets aligned with request deadlines and service capacity.
- Apply exponential backoff, jitter, `Retry-After`, circuit breakers, bulkheads, and rate limiters.
- Tune concurrency, batch sizes, and queue consumption speeds to protect downstreams.
- Write Java clients with timeouts, bounded retries, and idempotency.
- Monitor retry ratios, throttling, queue age, and saturation to refine policies.

## 1. What is downstream throttling?

A downstream is any service a function calls to complete work: a database, cache, HTTP API, object storage, message broker, or another internal service. Downstream throttling occurs when that service limits or rejects a portion of requests because a quota, concurrency, connection, throughput, or capacity threshold has been reached.

For example, an order-processing Java function might query a database for inventory, call a payment API, and publish a message. When traffic spikes suddenly, the function scales out faster than the database can handle. The database begins rejecting connections or returning overload errors; the payment API may return `429 Too Many Requests`; the message broker may enforce publish quotas.

Throttling can be an intentional protective mechanism. It tells callers that the current rate exceeds the limit the service will accept. If callers keep sending requests at the same pace, error counts climb and the downstream struggles even harder to recover.

### 1.1. Common symptoms

| Symptom | Possible meaning |
|---|---|
| HTTP `429` | Caller exceeded rate limit or quota |
| HTTP `503` | Service is temporarily overloaded or unavailable |
| HTTP `Retry-After` | Server hints when to retry |
| Database connection timeout | Out of connections, pool exhausted, or DB not accepting new connections |
| `Too many connections` | Database connection limit reached |
| gRPC `RESOURCE_EXHAUSTED` | Exhausted quota, capacity, or resource |
| Growing queue backlog | Consumers are not keeping up with producers |
| Rising p95/p99 latency alongside error rate | Downstream is saturating or waiting on resources |
| Throttling appears only during scale-out | Function growth rate exceeds downstream capacity |

Not every `429` or `503` shares the same root cause. Inspect response bodies, error codes, provider metrics, and target service logs. For example, an API may enforce `429` on per-project, per-user, or per-endpoint quotas; recovery approaches differ accordingly.

### 1.2. Throttling vs. application errors

- **Input or validation errors:** invalid request; resending the same data will usually keep failing.
- **Authorization errors:** missing permissions or invalid tokens; retrying repeatedly will not grant permissions.
- **Throttling:** the request may be valid, but the rate or concurrency exceeds limits.
- **Network errors:** may be transient, or caused by misconfigured DNS, routing, or firewalls.
- **Server errors:** `5xx` may be transient or persistent; classify by error code and API contract.

Retries help only when an error is likely to resolve within a reasonable window. Retrying configuration errors, malformed data, or denied permissions merely wastes resources and pollutes logs.

### 1.3. Multi-tier request model

~~~mermaid
flowchart LR
    A[Client] --> B[HTTP Java function]
    B --> C[Order service]
    C --> D[Inventory database]
    C --> E[Payment API]
    C --> F[Message broker]
    D --> G[Throttling / quota]
    E --> G
    F --> G
~~~

A function can receive requests cleanly yet still fail at a dependency. Measure each downstream independently; a single aggregate `function errors` metric cannot reveal which dependency is bottlenecking.

## 2. Why can serverless amplify load?

Serverless can spin up extra instances as requests rise. This scaling capability helps handle bursts, whereas downstreams often have fixed limits or scale much more slowly. If each invocation opens multiple connections, downstream load can grow faster than incoming request volume.

### 2.1. Fan-out multiplies request volume

Suppose each invocation calls 3 downstreams, and each downstream receives 2 requests. At 100 concurrent invocations, total dependency calls can reach:

\[
100 \times 3 \times 2 = 600
\]

If one dependency can sustain only 150 concurrent requests, the function can drive it into throttling even though each individual invocation looks lightweight.

### 2.2. Retries amplify load yet again

Suppose there are 1,000 initial requests and 20% fail transiently. If every failed request retries 3 times, maximum extra calls are:

\[
1,000 \times 20\% \times 3 = 600
\]

The downstream takes up to 1,600 calls instead of 1,000. If retries keep failing, load swells while the service is at its weakest.

This is *retry amplification*. When multiple function instances retry on a fixed schedule, they can create a retry storm: waves of fresh requests hitting the downstream in lockstep after every wait interval.

### 2.3. Little's Law and in-flight requests

A helpful relationship for understanding concurrency is Little's Law:

\[
L = \lambda \times W
\]

Where:

- \(L\): average number of requests in the system.
- \(\lambda\): completion or arrival rate (requests/second).
- \(W\): average time a request spends in the system (seconds).

If downstreams slow down, \(W\) rises. At the same arrival rate, waiting requests and held connections increase accordingly. If the function keeps scaling out or opening connections, the downstream saturates even faster.

For example, 200 requests/second with an average duration of 0.1 seconds corresponds to roughly 20 active requests. If latency rises to 2 seconds, active requests climb to roughly 400. This is why concurrency, timeouts, and queue depth must be controlled together.

### 2.4. Connection pools can amplify load

Suppose each Java instance opens a pool of 20 database connections. If the function scales to 30 instances, combined pools allow up to 600 connections. The database may support only 250 connections for that application.

A larger pool does not make a database faster. Compute:

\[
\text{Potential connections}
= \text{max instances} \times \text{pool size per instance}
\]

Add connections from other services, migrations, admin tools, and workers. Pool sizes must fit within real database limits.

## 3. Classifying errors before retrying

Retry policies must follow error and operation semantics. Never write a loop that catches every exception and retries blindly.

### 3.1. Errors typically safe to retry

Depending on the API contract, these cases may be transient:

- HTTP `429` or equivalent quota codes.
- HTTP `500`, `502`, `503`, `504` when the service documents them as transient.
- gRPC `UNAVAILABLE` or `RESOURCE_EXHAUSTED` when quota/capacity can recover.
- Connection resets or timeouts while calling a dependency.
- Database deadlocks or transient transaction conflicts.
- Transient broker errors during publish/consume.

For throttling, prioritize `Retry-After` if the server returns that header. Never assume every `5xx` is retryable; for example, an unsupported-request error will not change when retried.

### 3.2. Errors you should not retry blindly

- HTTP `400` from invalid payloads.
- HTTP `401` when credentials/tokens are invalid.
- HTTP `403` when the principal lacks permission.
- HTTP `404` when the resource does not exist and will not imminently appear.
- Parse/schema errors or permanent business errors.
- Certificate hostname mismatches or TLS trust configuration failures.
- Persistent DNS/routing/firewall misconfigurations.
- Requests exceeding fixed size limits.

Some errors may warrant a corrective step before retrying. For instance, `401` might be retried once after refreshing a token if the API client has a valid refresh flow. That is a targeted policy, not a blanket retry for every `401`.

### 3.3. Decision matrix

| Situation | Recommended action |
|---|---|
| `429` with `Retry-After` | Wait per header, bounded by deadline and retry budget |
| `429` without header | Exponential backoff + jitter, bounded attempts |
| Transient `503` | Bounded retries if the operation is safe |
| Timeout before knowing whether server received request | Retry only if idempotent or carrying an idempotency key |
| `400` validation | Stop retrying, return input error |
| `401`/`403` | Fix credentials or permissions; do not keep retrying |
| `404` | Follow API semantics; do not retry by default |
| Database deadlock | Bounded transaction retry if the entire transaction can safely re-run |
| Prolonged downstream disconnect | Open circuit, shed load, or offload work to a queue |

## 4. What is a retry budget?

A retry budget limits how much extra work the system is permitted to spend retrying failed operations. It stops retries from consuming all capacity during a downstream incident.

Budgets can be managed across multiple scopes:

1. **Per request:** each request may retry only a bounded number of times and must finish within its deadline.
2. **Per dependency:** total retries to a downstream are capped by ratio or token bucket.
3. **Per service/worker:** caps total retries across all instances or a consumer group.
4. **System-wide:** coordinates limits across services so independent per-layer retries do not amplify load.

A `maxAttempts=3` limit is only a per-request cap. If one million concurrent requests all retry three times, the downstream still receives up to two million extra calls. Production systems therefore typically need both per-request limits and service-level budgets.

### 4.1. Per-request budgets and deadlines

Every request should define:

- An end-to-end deadline set by the caller or service.
- Maximum attempt count.
- Maximum duration per dependency call attempt.
- Reserve margin for result processing, logging, and returning the response.

For example, a caller has a 3-second deadline. The function already spent 1 second validating and reading data; the dependency has a 1-second timeout. When the first call times out after 1 second, only about 1 second remains. Sleeping 2 seconds for backoff and retrying guarantees breaching the deadline.

Never start a new attempt if remaining time cannot cover backoff, connect timeout, and minimum processing time.

### 4.2. Per-dependency budgets

A policy can cap the retry ratio:

\[
\text{Retry ratio}
= \frac{\text{Retry calls}}{\text{Initial calls}}
\]

For instance, an organization sets a max retry ratio target of 10% over a time window. With 10,000 initial calls, at most roughly 1,000 retry calls are allowed in that window. This illustrates how budgets are defined; real thresholds must reflect downstream capacity and SLAs.

When the budget is exhausted:

- Stop retrying immediately.
- Return a controlled error to the caller or route messages to a queue/DLQ per semantics.
- Optionally open a circuit breaker to halt new calls for a cooldown period.
- Emit budget exhaustion metrics so operations knows the downstream is under pressure.

### 4.3. Token buckets for retry budgets

One implementation uses a token bucket:

- The bucket has a bounded capacity.
- Tokens replenish at a set rate or upon successful original requests.
- Each retry consumes one token.
- When no tokens remain, stop retrying and apply fallbacks.

For example, every 10 successful initial requests replenish 1 retry token, up to a 20-token cap. This bounds retry rate relative to healthy traffic while permitting small retry bursts. Token refill rules must be designed carefully; refilling on successes gradually restores the budget as the downstream recovers without triggering massive bursts.

An in-process token bucket works for one instance, yet across many instances each holds its own bucket and aggregate budget multiplies with instance count. When system-wide limits are required, use a distributed rate limiter, gateway/downstream quotas, or explicit per-instance budget slices.

### 4.4. Allocating budgets across layers

A request may traverse an API gateway, function, application service, and SDK. If every layer independently retries 3 times, final calls can multiply exponentially:

\[
3 \times 3 \times 3 = 27
\]

Designate a primary retry owner for each dependency. Remaining layers should propagate deadlines and errors upward, or retry only specific failures owned by that layer. Inspect default retries in SDKs, database drivers, HTTP clients, and service meshes to avoid accidentally stacking multiple retry layers.

~~~mermaid
flowchart TD
    A[Caller deadline] --> B[Function request budget]
    B --> C[Dependency attempt timeout]
    C --> D[Retry budget token]
    D -->|Token available| E[Backoff and retry]
    D -->|Budget exhausted| F[Fail fast / queue / fallback]
~~~

## 5. Exponential backoff and jitter

Exponential backoff progressively lengthens wait times between retries. Jitter adds randomness so clients do not retry in lockstep.

### 5.1. Backoff formula

A common full-jitter formulation:

\[
d_n \sim U(0,\min(d_{\max},d_0 \times 2^{n-1}))
\]

Where:

- \(d_n\): wait duration before retry attempt \(n\).
- \(d_0\): initial base delay.
- \(d_{\max}\): maximum delay cap.
- \(U(0,x)\): uniform random selection between 0 and \(x\).

Example with 200 ms base delay and 5-second cap:

| Retry attempt | Maximum wait window | Full jitter selection |
|---:|---:|---|
| 1 | 200 ms | Random 0–200 ms |
| 2 | 400 ms | Random 0–400 ms |
| 3 | 800 ms | Random 0–800 ms |
| 4 | 1,600 ms | Random 0–1,600 ms |
| 5 | 3,200 ms | Random 0–3,200 ms |
| 6 onward | 5,000 ms | Random 0–5,000 ms |

Jitter spreads retry timestamps across instances. Never use a fixed interval like 1 second across all clients; after a wave of errors, all clients will retry at the exact same instant.

### 5.2. Honoring Retry-After

When an HTTP response includes a `Retry-After` header, the server may specify seconds or an HTTP date/time for retrying. Clients should:

1. Parse the header in supported formats.
2. Never retry before the server-requested time.
3. Check remaining time within the deadline.
4. Bound wait times against application policy.
5. If wait time exceeds the deadline, fail or shift work to async processing.

Never add negative jitter that causes a client to retry earlier than `Retry-After`. You can add small positive jitter after that timestamp so clients do not wake up simultaneously, provided it still fits within the deadline and budget.

### 5.3. Bounding backoff

Backoff needs:

- A base delay small enough not to waste the deadline.
- A cap so wait durations do not grow unboundedly.
- A maximum retry count.
- An overall deadline for the entire operation.
- Jitter to prevent synchronization.
- Special handling when servers return `Retry-After`.

Backoff does not add capacity to downstreams. It only slows retry rates and gives services time to recover. For prolonged outages, circuit breakers, queues, or fail-fast responses are more appropriate.

## 6. Deadlines, timeouts, and retries must be planned together

A single dependency call timeout differs from the overall request deadline. The deadline is the latest point at which the caller still accepts a result. Every attempt, backoff, and final serialization must fit within that budget.

### 6.1. Time budget

Example HTTP request with a 5-second deadline:

| Stage | Budget |
|---|---:|
| Validation and setup | 300 ms |
| Attempt 1 | 1,000 ms |
| Backoff 1 | 200 ms |
| Attempt 2 | 1,000 ms |
| Backoff 2 | 400 ms |
| Attempt 3 | 1,000 ms |
| Serialize and return response | 300 ms |
| Margin | 800 ms |

Total elapsed time must remain less than or equal to the deadline. If the first attempt burns most of the budget, do not attempt to exhaust every preconfigured retry.

### 6.2. Propagating deadlines to dependencies

When one service calls another, propagate the deadline or remaining timeout instead of letting every tier configure an independent long timeout. Over HTTP, pass deadlines via internal context/headers per contract. Over gRPC, use RPC deadlines. Never trust a client-supplied deadline unless validated and clamped to service SLAs.

### 6.3. Avoiding overlapping timeouts

A request may pass through timeouts at the load balancer, API Gateway, function runtime, HTTP client, database driver, and query level. Align them:

- Dependency timeout shorter than the function's remaining time.
- Function timeout shorter than or equal to the caller's designed deadline.
- Database query timeout fits inside the database time budget.
- Retries finish before the function runs out of time.
- Reserve time for transaction commits, logging, and responses.

If the caller times out first while the function keeps retrying and commits a side effect, the caller may resend the request because it received no response. Idempotency is essential to protect business side effects in this scenario.

## 7. Mechanisms for protecting downstreams

Retries are only one piece of load control. Pair them with rate limits, concurrency caps, and behavior for unhealthy dependencies.

### 7.1. Rate limiters

Rate limiters cap request volume over time. Token buckets allow small bursts while keeping average rates bounded. They can be enforced at the API Gateway, service, worker, or client.

For example, a payment API accepts 100 requests/second. A function can use a limiter allowing up to 80 requests/second, preserving headroom for other traffic and variance. Real numbers must reflect quotas and allocation across callers.

Across multiple function instances, a local limiter per instance cannot cap aggregate rate. For example, 10 instances at 80 requests/second each can produce 800 requests/second. Use distributed limiters, gateway quotas, queues, or per-instance quota slicing.

### 7.2. Concurrency limiters and bulkheads

Concurrency limiters cap simultaneous in-flight calls to a dependency. Bulkheads isolate resources per dependency so one slow system cannot consume all threads, connections, or workers across the entire function.

Example:

- Payment API: max 20 concurrent requests.
- Inventory database: max 40 concurrent queries.
- Email provider: max 10 concurrent requests.

Account for these limits across all instances. If each instance allows 20 requests and 15 instances run, downstreams can receive 300 concurrent requests. Coordinate with max instances or centralized limiters.

### 7.3. Circuit breakers

Circuit breakers monitor dependency errors/timeouts:

- **Closed:** requests are allowed through.
- **Open:** temporarily stops calling the dependency when errors breach thresholds.
- **Half-open:** permits a small number of probe requests to check recovery.

Circuit breakers enable fail-fast behavior and stop piling requests onto an overloaded service. They do not replace retry budgets: when a circuit opens, retries must halt too. Avoid configuring all instances to probe simultaneously; jitter or probe quotas reduce load during half-open transitions.

### 7.4. Load shedding and fallbacks

When the system nears saturation, reject a portion of less critical requests early instead of letting all requests time out. Return HTTP 429 or 503 with appropriate retry guidance; if `Retry-After` is known, include when to try again.

Fallbacks can use caches, recent snapshots, partial results, or enqueuing work. Never use a fallback that corrupts business semantics—such as confirming payment succeeded when the payment provider never confirmed it.

### 7.5. Queues to absorb bursts

Queues decouple intake speed from processing speed:

~~~mermaid
flowchart LR
    A[HTTP request] --> B[Validate and enqueue]
    B --> C[Queue]
    C --> D[Worker function]
    D --> E[Downstream API / database]
    D -->|Transient failure| C
    D -->|Permanent failure| F[DLQ / quarantine]
~~~

Queues let workers process at concurrency and rates suited to downstreams. In return, applications must accept asynchronous execution, monitor queue age, design idempotency, and expose job status to callers.

### 7.6. Batching and caching

Batching reduces downstream requests when services offer bulk APIs. However, overly large batches increase latency, memory, and retry blast radius. When one item fails, know whether you must retry the entire batch or just the failing item.

Caching cuts repeated reads. Define TTLs, invalidation, and consistency requirements. Caching does not solve every throttling problem, especially for writes or data requiring immediate strict accuracy.

## 8. Safe retries with side effects and idempotency

Retrying a read is generally safer than retrying a write. If the server processed a request but the response was lost, the client cannot tell whether the operation succeeded.

### 8.1. Why can timeouts create duplicate side effects?

For example, a function submits a payment creation command. The payment provider creates the transaction, but the response is lost to a network timeout. The function retries with a fresh request and the provider creates a second transaction.

You cannot conclude an operation failed simply because the client received no response. Its state may be an *unknown outcome*.

### 8.2. Idempotency keys

With APIs supporting idempotency, generate a stable key for one business operation and resend that same key across every attempt. Providers store results keyed by that value so duplicate requests do not trigger new side effects.

Example:

~~~java
HttpRequest request = HttpRequest.newBuilder(paymentUri)
        .header("Idempotency-Key", orderPaymentId)
        .header("Content-Type", "application/json")
        .POST(HttpRequest.BodyPublishers.ofString(payload))
        .build();
~~~

The key must represent one business operation—never generate a new UUID on every retry. If each attempt carries a different key, the server cannot recognize it as the same operation.

### 8.3. Idempotency in databases

When downstreams lack idempotency APIs, persist operation keys with a unique constraint in a database. Claiming the key, updating state, and writing results require transactions or consistent protocols.

A state model:

| State | Meaning |
|---|---|
| `NEW` | Not yet processed |
| `IN_PROGRESS` | Claimed by a worker |
| `SUCCEEDED` | Side effect completed |
| `FAILED_PERMANENT` | Non-retryable failure |
| `RETRYABLE` | Can be tried again later |

Handle leases/timeouts for `IN_PROGRESS` in case a worker crashes mid-flight. When side effects live in external systems, use idempotency keys at that system, outbox/inbox patterns, or reconciliation to resolve unknown outcomes.

### 8.4. Delivery semantics

Event sources can typically redeliver messages if consumers do not confirm success. Event-driven functions should therefore be designed for at-least-once delivery where the service provides these semantics. Never assume end-to-end exactly-once merely because a broker offers deduplication features; downstream database/API side effects still require idempotency.

## 9. Applying retry budgets to queues and event functions

Queues help govern processing speed, yet flawed retry handling can still bloat backlogs and overload downstreams.

### 9.1. AWS Lambda with Amazon SQS

When Lambda reads SQS, the event source mapping polls the queue and invokes the function in batches. If the function errors, messages can redeliver after the visibility timeout. Configure:

- Batch sizes matching processing duration and memory.
- Maximum concurrency or event source mapping concurrency caps to protect downstreams.
- Visibility timeouts long enough for function timeouts, batch windows, and retry behavior per AWS recommendations.
- Redrive policies and DLQs for persistently failing messages.
- Partial batch responses to return only failed messages when batches partially succeed.
- Per-message idempotency, not just per-batch.

Without partial batch responses, one failing message can force the entire batch to redeliver, re-running already-succeeded messages. Within batches, distinguish per-message retryable errors from permanent errors requiring quarantine.

### 9.2. Google Cloud Pub/Sub and Eventarc

With Pub/Sub, subscriptions govern ack deadlines, retry policies, and dead-letter topics. Consumers must ack after durable processing. If the ack deadline expires before completion, messages may redeliver while the previous worker is still running.

Limit outstanding messages and subscriber concurrency to keep downstream pressure within bounds. With Cloud Run functions/Eventarc, inspect retry policies, event retention, and dead-letter support for the specific trigger. Never assume every trigger shares identical semantics.

### 9.3. Distinguishing in-handler retries from broker retries

If a handler retries 3 times internally before throwing an exception, the broker may redeliver the message and repeat all 3 attempts again. If the broker also retries multiple times, total attempts escalate sharply.

Make clear boundaries:

- Short retries for transient failures within one invocation while deadline permits.
- Let the broker manage longer retries by failing the invocation cleanly.
- Route permanent or threshold-exceeding failures to DLQs/quarantines.
- Log event ID, message ID, and attempt count for traceability.
- Use idempotency so repeated deliveries of the same message remain safe.

### 9.4. Queue age matters more than queue depth in some workloads

Queue depth tells you how many messages are waiting; queue age tells you how long the oldest message has waited. A queue with 10,000 messages draining rapidly may be healthy; a queue with 100 messages waiting 30 minutes may be breaching SLAs.

Track all of:

- Queue depth and age of oldest message.
- Message receive count/attempt count.
- DLQ depth.
- Consumer concurrency and processing duration.
- Downstream throttling and error rates.
- Producer rate vs. consumer rate.

## 10. Java example: bounded retries and deadlines

A retry helper should accept the operation, retry predicate, max attempts, deadline, and retry budget. It must never blindly retry every exception. The application must classify errors according to dependency contracts.

### 10.1. Generating full-jitter delays

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public final class Backoff {

    private Backoff() {}

    public static Duration fullJitter(
            int retryNumber,
            Duration baseDelay,
            Duration maxDelay) {

        if (retryNumber < 1) {
            throw new IllegalArgumentException("retryNumber must be >= 1");
        }

        long base = Math.max(1, baseDelay.toMillis());
        long cap = Math.max(base, maxDelay.toMillis());
        long ceiling = base;

        for (int i = 1; i < retryNumber && ceiling < cap; i++) {
            ceiling = ceiling > cap / 2 ? cap : ceiling * 2;
        }

        long delay = ThreadLocalRandom.current().nextLong(ceiling + 1);
        return Duration.ofMillis(delay);
    }
}
~~~

This function returns a random wait duration between 0 and the capped exponential window. It only computes the delay; callers must still check deadlines, retry budgets, and `Retry-After`.

### 10.2. Retry budget interface

~~~java
public interface RetryBudget {
    // Returns true if budget remains and a token has been reserved for this retry.
    boolean tryAcquire();
}
~~~

A local implementation can use a thread-safe token bucket. However, when a function scales across multiple instances, each instance holds its own budget. To cap total retries to a dependency system-wide, use distributed budgets, gateway quotas, or per-instance quota slicing.

### 10.3. Retry loop with deadline

The following example illustrates the control structure. `operation` must enforce its own per-attempt timeout; `retryable` must accept only identified transient failures:

~~~java
import java.time.Duration;
import java.util.concurrent.Callable;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.function.Predicate;

public final class RetryExecutor {

    private RetryExecutor() {}

    public static <T> T execute(
            Callable<T> operation,
            Predicate<Exception> retryable,
            RetryBudget budget,
            int maxAttempts,
            long deadlineNanos,
            Duration baseDelay,
            Duration maxDelay) throws Exception {

        if (maxAttempts < 1) {
            throw new IllegalArgumentException("maxAttempts must be >= 1");
        }

        Exception lastFailure = null;

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            if (deadlineNanos - System.nanoTime() <= 0) {
                break;
            }

            try {
                return operation.call();
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                throw interrupted;
            } catch (Exception failure) {
                lastFailure = failure;

                boolean canRetry =
                        retryable.test(failure)
                        && attempt < maxAttempts
                        && budget.tryAcquire();

                if (!canRetry) {
                    throw failure;
                }

                long remaining = deadlineNanos - System.nanoTime();
                long delay = Backoff.fullJitter(
                        attempt, baseDelay, maxDelay).toNanos();

                if (delay >= remaining) {
                    throw failure;
                }

                try {
                    TimeUnit.NANOSECONDS.sleep(delay);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw interrupted;
                }
            }
        }

        if (lastFailure != null) {
            throw lastFailure;
        }

        throw new TimeoutException("Request deadline exhausted");
    }
}
~~~

Key details to keep intact when integrating:

- `maxAttempts` includes the initial attempt.
- Each dependency call must have connect/read/request timeouts shorter than remaining time.
- `retryable` must not return `true` for every exception.
- `budget.tryAcquire()` is invoked only when actually preparing to retry.
- Delay must fit inside the deadline; otherwise, stop and return the failure.
- `InterruptedException` must never be swallowed; let interrupted threads stop properly.
- If the server sends `Retry-After`, adjust delay logic so retries never fire before the server-requested time, while still checking the deadline.
- Never use this helper to retry writes lacking idempotency.

### 10.4. Classifying HTTP responses

An HTTP client should classify responses per the API contract. Example:

~~~java
static boolean isRetryableStatus(int statusCode) {
    return statusCode == 429
            || statusCode == 500
            || statusCode == 502
            || statusCode == 503
            || statusCode == 504;
}
~~~

This is only an example for an API whose contract permits retrying these status codes. Some services use different error codes or custom rules. Always check response bodies and headers, especially for 429/503.

### 10.5. Never nest retries inside retries

If an HTTP SDK already retries 3 times internally, do not wrap it in another retry helper also running 3 times without calculating total attempts. Total calls can reach 9. Inspect retry configs in SDKs, database drivers, and service clients; designate one primary place to manage budgets.

## 11. Designing retries by operation type

Not every request needs the same policy. Distinguish reads, writes, event deliveries, and long-running tasks.

| Operation type | Recommended retry approach | Critical condition |
|---|---|---|
| HTTP GET data reads | Safe to retry transient errors | Timeouts, deadlines, rate limits |
| HTTP POST creating transactions | Retry only with idempotency | Stable key and provider support |
| Database reads | Bounded transient retries | Connection/query timeouts |
| Database write transactions | Retry whole transaction on eligible errors | Transaction can re-run cleanly without external side effects |
| Publishing messages | Retry per SDK/broker | Message ID or idempotency key |
| Consuming messages | Broker redelivery + DLQ | Ack after commit, idempotent handler |
| Sending emails | Can send duplicates on ambiguous timeouts | Idempotency or delivery-state tracking |
| Calling non-idempotent APIs | Generally do not retry blindly | State lookup or idempotency contract required |

If an operation is non-idempotent and the downstream lacks idempotency keys, a timeout can leave an ambiguous state. Instead of resending immediately, query operation status by business ID before deciding how to proceed.

## 12. Tuning concurrency and consumption speed

When downstreams throttle, lowering incoming pressure is usually more effective than raising retry counts.

### 12.1. Capping function concurrency

Set max instances or concurrency to match downstream capacity. For instance, if a database allocates only 100 connections to a function and each instance opens a pool of 10 connections, the theoretical ceiling is 10 instances; in practice, leave headroom for other connections and bursts.

Platform limits do not replace in-application limiters. One instance can handle multiple concurrent requests all calling the same API. Account for total concurrent requests across all instances.

### 12.2. Reducing batch sizes when dependencies overload

Large batch sizes raise throughput when downstreams are healthy, yet overly large batches create bursts and wide retry blast radii. During throttling:

- Reduce batch size.
- Lower consumer maximum concurrency.
- Lengthen poll intervals or apply flow control.
- Separate heavy vs. light message classes if they have different capacities.
- Retry only failed items when brokers and event sources support partial failures.
- Ramp concurrency back up gradually after downstream recovery—do not restore full concurrency all at once.

### 12.3. Adaptive concurrency

A system can tune concurrency dynamically from downstream latency and error rates. When p95/p99 or throttling rises, lower concurrency limits; when the service stabilizes, raise them slowly.

Never raise concurrency simply because queue depth rises. Queues may be growing because a downstream is slow; adding consumers then only worsens the outage. Use queue age, downstream saturation, and success throughput to decide.

## 13. Observing retry budgets and downstream health

Retry policies cannot operate well without measurement. Distinguish original requests, total attempts, and retries.

### 13.1. Metrics to monitor

| Metric | Meaning |
|---|---|
| Original request count | Volume of fresh work |
| Attempt count | Total calls including retries |
| Retry count and retry ratio | Load amplification level |
| Retry budget exhausted | Count of retries blocked by budget |
| Throttling count by dependency | Which downstream is rejecting requests |
| Latency p50/p95/p99 | Response time and saturation level |
| Timeouts and connection errors | Connectivity or capacity problems |
| Circuit breaker state | Whether dependency is closed/open/half-open |
| Active concurrency | Number of running calls |
| Connection pool utilization | Pool usage level |
| Queue depth and oldest message age | Whether consumers keep pace |
| DLQ depth | Volume of work needing investigation |

Define retry ratio consistently. You can measure retries per original request or percentage of total attempts that are retries; those two formulas differ. Dashboards must state the exact formula to avoid misinterpretation.

### 13.2. Structured logging

Each attempt should capture fields such as:

- `requestId` or `traceId`.
- `dependency` and `operation`.
- `attempt` and `maxAttempts`.
- `retryReason` or status/error code.
- `backoffMs` and `remainingDeadlineMs`.
- `retryBudgetAllowed`.
- `durationMs`.
- Masked or hashed `idempotencyKey` if sensitive.

Never log tokens, passwords, sensitive payloads, or full authorization headers. Log retries blocked by budgets as well so you know the policy is actively engaging.

### 13.3. Meaningful alerts

Alerts should tie to business impact, not raw error counts alone:

- Retry ratio exceeds threshold over a window.
- Throttling rises continuously on a critical dependency.
- Queue age breaches SLA.
- New messages appear in or rapidly fill the DLQ.
- Circuit breakers remain open for an extended duration.
- Database connection pools approach exhaustion.
- Success throughput drops even as concurrency climbs.

## 14. Procedure when a downstream throttles

When rising throttling is detected, proceed sequentially:

1. Pinpoint which dependency is throttling using per-dependency metrics/logs.
2. Check downstream quotas, concurrency, connection pools, and capacity.
3. Inspect retry ratios and check for stacked retry layers.
4. Lower concurrency, batch sizes, or producer rates to relieve pressure.
5. Apply backoff + jitter and honor `Retry-After`.
6. Stop retrying once request deadlines expire.
7. Open circuit breakers if failures persist; serve fallbacks or controlled errors.
8. Offload deferrable work to queues; move unprocessable messages to DLQs per policy.
9. Verify idempotency and side-effect state before redriving.
10. Ramp load back up gradually as downstreams stabilize, watching success throughput and queue age.

Never redrive an entire DLQ at once before downstreams recover. Replay in small, rate-limited batches and observe results.

## 15. Testing retries and throttling

Tests for retry policies must verify call counts, total elapsed time, and side effects—not merely that the final exception is thrown.

Scenarios to include:

- Downstream returns 429 with `Retry-After`.
- Downstream returns 429 continuously until the budget exhausts.
- Transient 503 followed by recovery.
- Timeout after the server committed side effects while the response was lost.
- 400 or 403 errors are not retried.
- Deadline expires before the next attempt can run.
- Multiple instances retry concurrently while jitter spreads timestamps.
- Circuit breaker opens and permits only bounded probes in half-open state.
- Queue redelivers the same message and the handler remains idempotent.
- A batch contains succeeded, retryable, and permanent failure items together.
- Downstream recovers without consumers unleashing a retry storm.
- Distributed retry budgets hold limits as instance counts scale up.

Use mock servers or test doubles to control status codes, headers, and latency. For load tests, step load up gradually and observe the onset of throttling—do not measure only peak throughput while downstreams are healthy.

## 16. Common design mistakes

- **Retrying every exception:** repeats permanent failures and drives up costs.
- **Having no deadline:** requests can keep retrying longer than callers tolerate.
- **Fixed backoff:** multiple instances synchronize retries and cause retry storms.
- **No jitter:** retry attempts bunch up into bursts.
- **Capping attempts per request only:** system-wide retry volume can still grow massive.
- **Retrying at every layer:** attempt counts multiply across gateways, services, and SDKs.
- **Ignoring `Retry-After`:** clients keep hammering a server that explicitly asked them to wait.
- **Retrying non-idempotent POSTs:** creates duplicate transactions or side effects.
- **Per-instance limiters only:** total rate scales up with instance count.
- **Raising concurrency to clear queue backlogs:** can overload downstreams even further.
- **Acking messages before durable writes:** messages can be lost before business work finishes.
- **Unbounded DLQ redrives:** can immediately recreate the incident.
- **Not measuring retry ratios:** leaves teams blind to how much capacity retries consume.
- **Ignoring total connection pool sizing:** each instance looks fine, yet aggregate connections exceed database limits.

## 17. Production checklist

- [ ] Transient and permanent errors are classified per dependency contracts.
- [ ] Every attempt has a dedicated timeout and every request has an end-to-end deadline.
- [ ] Maximum attempts includes the initial call.
- [ ] Exponential backoff has a cap and jitter.
- [ ] `Retry-After` is honored when provided by servers.
- [ ] Per-request retry budgets and per-dependency/service retry limits exist.
- [ ] Multiple retry layers do not stack unexpectedly.
- [ ] Operations with side effects are protected by idempotency keys or transactions.
- [ ] Circuit breakers, bulkheads, or concurrency limiters are used where needed.
- [ ] Rate limiters account for total instance count.
- [ ] Max instances, batch sizes, and consumer concurrency fit downstream capacity.
- [ ] Queue visibility/ack deadlines, retry policies, and DLQs are properly configured.
- [ ] Partial batch failures are handled when supported by the event source.
- [ ] Metrics track original requests, attempts, retry ratios, and budget exhaustions.
- [ ] Dashboards cover downstream throttling, latency, queue age, and DLQs.
- [ ] Post-side-effect timeouts, duplicate deliveries, and retry storms have been tested.
- [ ] DLQ replays use rate limits and reconciliation procedures.

## 18. Self-check

**Question 1.** Why can retries make downstream throttling worse?

**Suggested answer:** Retries inject extra requests right when a dependency is already overloaded. When many instances retry at the same time or multiple retry layers stack, the extra load can trigger a retry storm and hinder service recovery.

**Question 2.** How does a retry budget differ from `maxAttempts`?

**Suggested answer:** `maxAttempts` caps attempts for a single request. A retry budget additionally bounds total retry volume per dependency, worker, or across the whole system so aggregate retries do not exceed capacity.

**Question 3.** Why is jitter needed with exponential backoff?

**Suggested answer:** Jitter spreads retry timestamps across clients. If every client uses the exact same fixed backoff schedule, they can retry in lockstep and create fresh bursts.

**Question 4.** When should you avoid retrying a `POST` request?

**Suggested answer:** When you do not know whether the server already executed the side effect and the API lacks idempotency support. Use an idempotency key or query operation status before resending.

**Question 5.** Why can't a local retry budget per instance cap total system retries?

**Suggested answer:** Each instance holds its own bucket. As instance counts grow, total tokens and retry rates climb proportionally. To enforce a system-wide limit, use distributed budgets, centralized quotas, or per-instance quota slicing.

**Scenario exercise:** A Java function receives 500 HTTP requests/second. Each invocation calls a payment API and a database. The payment API limits traffic to 100 requests/second and returns 429 with `Retry-After`; the database begins rejecting connections when total connections exceed 200. The function autoscales to 30 instances, each opening a 10-connection pool. Design the retry budget, backoff, concurrency limits, connection pools, queues/fallbacks, and metrics. Explain how to handle requests where payment succeeded but the response timed out.

**Hint:** Total potential pool connections equal 30 × 10 = 300, exceeding the 200-connection limit. Shrink the per-instance pool or cap max instances/concurrency so total connections retain headroom. The payment API accepts only 100 requests/second, so system-wide rate limits or queue workers must hold rates under quota rather than relying on unsynchronized local limiters. On 429, honor `Retry-After`, add positive jitter within the deadline, and retry only while budget remains. For payment operations, attach a stable idempotency key per payment operation; on ambiguous timeouts, look up operation status by key before issuing a new request. Monitor retry ratio, 429 counts, payment latency, connection pool utilization, DB errors, queue age, and DLQs.

## Conclusion

Downstream throttling signals that caller rates or concurrency exceed what a dependency can accept. Unbounded retries amplify load, prolong outages, and risk duplicate side effects. A resilient policy combines error classification, deadlines, per-attempt timeouts, jittered exponential backoff, `Retry-After`, per-request and per-dependency retry budgets, and concurrency/rate limits. For events and writes, idempotency, post-commit acks, and DLQs are essential. Monitoring retry ratios, throttling, queue age, connection pools, and success throughput enables tuning load to match real downstream capacity.
