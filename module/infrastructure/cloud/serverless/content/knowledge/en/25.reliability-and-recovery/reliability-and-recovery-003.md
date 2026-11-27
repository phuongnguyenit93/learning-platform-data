# Retries with Exponential Backoff, Jitter, and Attempt Limits

In serverless architectures, a function can experience transient failures due to flaky networks, overloaded databases, partner APIs returning 503, or temporarily unavailable message brokers. Retries help complete work when errors can self-recover. However, poorly designed retries can worsen an incident: many functions simultaneously calling an already overloaded dependency create a retry storm, multiplying request volume and exhausting concurrency.

A sound retry policy must answer four questions: **which errors are retried, how long to wait before the next attempt, how many times to try at most, and when to stop**. For Java serverless workloads, the policy must also account for the invocation deadline, platform time limits, queue/event source retry mechanisms, and duplicate-handling capability. If a call may have produced a side effect before timing out, retries must be paired with idempotency.

This lesson covers classifying errors, computing exponential backoff with jitter, setting attempt and elapsed-time limits, implementing retries in Java, coordinating with platform-managed retries, and operating DLQs/redrive safely.

## 1. What is a retry and when should it be used?

A retry is re-executing an operation after a previous attempt failed. Its purpose is to overcome transient failures without requiring users or upstream systems to immediately resubmit requests manually.

Appropriate examples:

- An HTTP request to a partner API encounters a connection reset.
- A database temporarily rejects connections during a failover.
- A queue consumer receives a 503 error from a dependency.
- Object storage returns a throttling error.
- A DNS lookup or network route experiences a brief glitch.

Retries cannot fix logic bugs or invalid input data. If a request is permanently missing a required field, carries an invalid token, or violates a business rule, retrying with the exact same payload only wastes time and cost.

### Bounded retries

A retry policy typically consists of:

- **Max attempts:** Total number of executions, including the initial attempt.
- **Initial delay:** Wait duration before the first retry.
- **Backoff multiplier:** Factor by which wait time grows, commonly 2.
- **Maximum delay:** Upper bound on the wait duration.
- **Maximum elapsed time:** Maximum time budget for the retry window; per-attempt timeouts and the invocation deadline must still bound execution time.
- **Retryable classifier:** Condition determining which errors qualify for retry.
- **Jitter:** Randomness added to delays to prevent multiple clients from retrying in lockstep.

Never use unbounded retries. A prolonged dependency outage can cause functions to burn concurrency, compute spend, and user wait time without producing results.

## 2. Classifying errors before retrying

The first step is classifying errors by recoverability and business semantics.

| Error type | Examples | Typically appropriate action |
|---|---|---|
| Transient network errors | Connection reset, connect timeout, DNS timeout | Bounded retry is appropriate |
| Overload errors | HTTP 429, 503, throttling | Backoff, jitter, honor Retry-After |
| Transient server errors | HTTP 500, 502, 504 | Retryable if the operation is safe |
| Input errors | HTTP 400, invalid schema | Do not retry |
| Auth/permission errors | HTTP 401, 403 | Do not retry with the same credentials; fix identity/config |
| Business errors | Payment declined, invalid state | Generally do not auto-retry |
| Not found | HTTP 404 | Depends on contract; usually do not retry if resource truly does not exist |
| Conflict | HTTP 409 | Retry only when the contract indicates a transient conflict |
| Timeout with unknown outcome | Client timeout after server may have committed | Retry only with idempotency or a state lookup mechanism |

### HTTP status codes are not a complete classifier

Not every 5xx is guaranteed safe to retry, and not every 4xx is permanent. Always read the dependency's contract.

For example:

- 429 typically indicates a rate limit exceeded; wait according to Retry-After if provided.
- 503 may indicate maintenance or temporary overload.
- 500 may stem from a deterministic bug where repeated retries will not help.
- 409 may be an optimistic-locking conflict that can be retried after reading fresh state, or a duplicate request that should not be repeated.

Classifiers should rely on exception types, status codes, provider error codes, and operation state. Never use a blanket rule like "catch Exception and retry."

## 3. Exponential backoff

Exponential backoff increases the wait duration after each failure. Instead of hammering a dependency at a fixed interval, clients progressively space out retries to give the dependency room to recover.

Formula for delay before retry number (n):

```text
delay(n) = min(maxDelay, initialDelay × multiplier^(n - 1))
```

With a multiplier of 2:

- Retry 1: 200 ms.
- Retry 2: 400 ms.
- Retry 3: 800 ms.
- Retry 4: 1,600 ms.
- Retry 5: 3,200 ms.

If maxDelay is 2 seconds, the delay stops growing at 2 seconds.

### Calculation example

Suppose:

- initialDelay = 250 ms.
- multiplier = 2.
- maxDelay = 2,000 ms.
- maxAttempts = 5 (including the initial attempt).

| Execution | Relative timestamp without jitter | Wait before next attempt |
|---|---:|---:|
| Attempt 1 | 0 ms | 250 ms |
| Attempt 2 | 250 ms | 500 ms |
| Attempt 3 | 750 ms | 1,000 ms |
| Attempt 4 | 1,750 ms | 2,000 ms |
| Attempt 5 | 3,750 ms | Stop |

The maximum total wait time in this example is 3,750 ms, excluding the execution time of each attempt. This is why you must account for actual execution duration, not just sum the delays.

## 4. Why is jitter needed?

If thousands of functions receive 503 at the same moment and all use fixed backoff, they can retry in unison after 1 second, and again in unison after 2 seconds. Right as the dependency begins recovering, the synchronized wave of requests can knock it over again. This phenomenon is known as a thundering herd.

Jitter adds randomness to delays to spread out retry attempts over time.

### Full jitter

A widely used choice is full jitter:

```text
cap(n) = min(maxDelay, initialDelay × 2^(n - 1))
actualDelay(n) = random(0, cap(n))
```

For example, when cap is 800 ms, each client picks a random delay between 0 and 800 ms. Clients no longer retry at the exact same instant.

### Common jitter strategies

| Strategy | Calculation | Characteristics |
|---|---|---|
| No jitter | Use the full exponential delay | Prone to synchronized retry waves |
| Full jitter | Random from 0 to cap | Strong dispersion, lower average delay than cap |
| Equal jitter | cap/2 + random(0, cap/2) | Guarantees a minimum wait floor |
| Decorrelated jitter | New random delay based on previous delay and cap | Good dispersion across long retry chains |

Full jitter works well as a default for most distributed workloads. If the dependency provides a Retry-After header, the client should honor the requested wait time instead of overriding it with a shorter delay.

## 5. Capping attempt counts and total elapsed time

Max attempts and max elapsed time address two distinct risks:

- Max attempts prevents an operation from trying too many times.
- Max elapsed time prevents starting another retry once the time budget is spent, even if earlier attempts were slow or backoffs were large.

Clarify the counting convention: **maxAttempts usually includes the initial call**. If maxAttempts = 4, there is at most one initial attempt and three retries. Some SDKs use maxRetries, where total attempts equal 1 + maxRetries.

Example:

- maxAttempts = 4.
- initialDelay = 200 ms.
- maxDelay = 1 second.
- maxElapsed = 5 seconds.

If the first attempt already took 4.5 seconds, do not sleep 1 second and call again when the invocation only has 0.5 seconds left. Stop and return an error per contract, or offload the work to a queue for asynchronous processing.

### Deadlines must cover every leg

A synchronous request might have an overall deadline of 8 seconds. That includes:

- Authentication and input validation.
- Database calls.
- Partner API calls.
- Retry attempts and backoff delays.
- Building the response.

Never exhaust the entire deadline retrying a single dependency and leave no time to return a response or persist state. Propagate the deadline/remaining time across layers rather than having each layer configure independent timeouts.

Max elapsed in a retry helper bounds the retry window; it cannot forcibly abort a hanging HTTP call or undo an operation that succeeded after the deadline. Configure connect timeouts, request timeouts, and read timeouts according to your library's capabilities, and pass the remaining deadline so a new attempt is not started when insufficient time remains. Never treat a late successful result as an automatic retry error, because the side effect may have already occurred.

## 6. Synchronous vs. asynchronous retries

Not every retry should happen within the same invocation.

| Type | How it works | Best suited when |
|---|---|---|
| Synchronous retry | Function waits and re-invokes dependency within the same invocation | Brief faults, few attempts, sufficient deadline remaining |
| Platform-managed retry | Queue, event source, or workflow redelivers the event after failure | Background work that can wait and needs durable retries |
| Scheduled retry | Persist retry state and schedule the next attempt | Long delays, specific retry times, or multi-step workflows |
| Manual redrive | Replay messages from DLQ after fixing the root cause | Poison messages or incidents requiring intervention |

### Synchronous retries

The advantage is simplicity and immediate response delivery. The downside is holding the invocation, thread/concurrency, and incurring compute charges while waiting.

Use synchronous retries only for short waits. If you need to wait minutes or hours, do not hold a function invocation open sleeping; persist operation state and switch to an asynchronous mechanism.

### Platform-managed retries

For messages/events, platforms usually provide built-in retries when a handler fails or does not acknowledge. You must understand the exact retry conditions, attempt limits, visibility/ack deadlines, retention, and partial batch failure behavior of the trigger in use.

Do not stack a long retry loop inside the consumer when the event source already has its own retry policy without accounting for total attempts. Two layers of retries can multiply call volume.

## 7. Retry budgets and retry amplification

A request may traverse several layers:

1. API gateway retries the function.
2. Function retries an internal service.
3. Internal service retries the database.
4. HTTP client retries a partner API.

If each layer allows three attempts, one operation can generate up to (3^4 = 81) calls at the deepest dependency in the worst case. Actual numbers depend on topology, but the example shows how nested retries amplify load rapidly.

### Control principles

- Designate one primary retry owner per dependency.
- Other layers enforce timeouts and return clear errors.
- Cap total attempts across the whole operation, not just per client.
- Enforce a retry budget per service or dependency.
- Use circuit breakers to pause requests when a dependency fails persistently.
- Use rate limits and bulkheads to contain blast radius.
- Never retry a request already retried by an upstream caller without idempotency.

A retry budget can be defined as a maximum ratio of retry requests to initial requests within a time window. Once the budget is depleted, the system fails fast or queues work instead of adding load.

## 8. Idempotency: a critical prerequisite before retrying

An idempotent operation produces the same final outcome whether executed once or multiple times with the same request identifier.

Examples:

- Setting an order status to PAID can be idempotent if it only transitions to that target state with transition guards.
- Creating a new order is not automatically idempotent: retrying can create two orders.
- Sending an email is not automatically idempotent: retrying can send two emails.
- Calling a payment API may support an idempotency key per the provider's contract.

### Why are timeouts dangerous?

A client sends a charge payment command. The provider deducts funds, but the response is lost on the network. The function times out without knowing whether the transaction succeeded. If it retries with a new request, the customer can be charged twice.

Solution:

- Generate a stable idempotency key for the business operation.
- Send the exact same key on every attempt.
- Persist status and results keyed by that identifier.
- The provider must support deduplication or expose an operation lookup API.
- When the outcome is unknown, query state before initiating a new operation.

Never generate a new idempotency key on each retry. The key must represent the same business action across all attempts.

## 9. Storing idempotency keys in a database

A simple table can store the key, status, and result:

~~~sql
CREATE TABLE idempotency_records (
    idempotency_key VARCHAR(128) PRIMARY KEY,
    request_hash    VARCHAR(128) NOT NULL,
    status          VARCHAR(24) NOT NULL,
    response_body   TEXT NULL,
    created_at      TIMESTAMP NOT NULL,
    updated_at      TIMESTAMP NOT NULL
);
~~~

Processing flow:

1. Receive the idempotency key from the caller or generate an operation ID in the backend.
2. Compute a request hash to detect reuse of the same key with a different payload.
3. Insert a record in `IN_PROGRESS` status enforced by a unique constraint.
4. If the key already has status `COMPLETED`, return the stored result.
5. If the key is `IN_PROGRESS`, return an appropriate status or let the caller poll.
6. Execute business logic inside an appropriate transaction.
7. Save the result and transition status to `COMPLETED`.
8. For transient errors, keep a retryable state per policy; for permanent errors, record a terminal state.

A unique constraint protects against two invocations simultaneously creating records for the same key. Handle concurrent race conditions properly; never simply run `SELECT` followed by `INSERT`, as both requests could observe the key missing at the same time.

### Same key with a different payload

If the idempotency key matches but the request hash differs, return a conflict per contract. Never serve a cached result for a different payload, as doing so can mask or trigger an unintended transaction.

### TTL and retention

Idempotency records must be retained longer than the system and provider's maximum retry/replay window. Deleting records too early can allow an old redriven message to execute its side effect a second time.

## 10. Retries for HTTP clients in Java

The JDK `HttpClient` does not provide a generic business retry policy across all HTTP statuses. The application must decide which errors to retry, attempt limits, deadlines, and idempotency.

A client can classify responses as:

- Connect exceptions or certain transient I/O errors: retryable.
- HTTP 429: retry honoring Retry-After and budget.
- HTTP 502/503/504: retryable per contract.
- HTTP 400/401/403: do not retry the same request.
- HTTP 409: retry only when the provider defines it as a transient conflict.
- Timeout after sending the body: outcome may be unknown; requires an idempotency key.

For POST requests that create resources or charge payments, retry only if the API supports idempotency keys or provides a way to verify the prior operation.

### Do not blindly retry every IOException

An `IOException` can be a connection reset, or it can occur after the request was transmitted and processed by the server. Distinguish the connect, request-send, and response-receive phases if the library/provider allows. When the outcome cannot be determined, treat the operation as ambiguous and use idempotency/lookup.

## 11. Java example: capped exponential backoff with full jitter

The code below demonstrates synchronous retries for a short operation. The classifier is passed externally so each dependency can apply its own contract.

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.TimeUnit;
import java.util.function.Predicate;

record RetryPolicy(
        int maxAttempts,
        Duration initialDelay,
        Duration maxDelay,
        Duration maxElapsed) {

    public RetryPolicy {
        if (maxAttempts < 1) {
            throw new IllegalArgumentException("maxAttempts must be >= 1");
        }
        if (initialDelay == null || initialDelay.isNegative()
                || initialDelay.isZero()
                || maxDelay == null
                || maxDelay.compareTo(initialDelay) < 0
                || maxElapsed == null
                || maxElapsed.isNegative()
                || maxElapsed.isZero()) {
            throw new IllegalArgumentException("Invalid retry durations");
        }
        if (maxDelay.compareTo(Duration.ofDays(1)) > 0
                || maxElapsed.compareTo(Duration.ofDays(1)) > 0) {
            throw new IllegalArgumentException("Retry durations are too large");
        }
        if (initialDelay.toMillis() < 1 || maxDelay.toMillis() < 1) {
            throw new IllegalArgumentException(
                    "Retry delays must be at least one millisecond");
        }
    }
}

@FunctionalInterface
interface CheckedSupplier<T> {
    T get() throws Exception;
}

public final class RetryExecutor {

    private RetryExecutor() {}

    public static <T> T execute(
            CheckedSupplier<T> operation,
            RetryPolicy policy,
            Predicate<Exception> retryable) throws Exception {

        long startedAt = System.nanoTime();
        long maxElapsedNanos = policy.maxElapsed().toNanos();
        long capMillis = policy.initialDelay().toMillis();
        long maxDelayMillis = policy.maxDelay().toMillis();

        for (int attempt = 1; attempt <= policy.maxAttempts(); attempt++) {
            try {
                return operation.get();
            } catch (Exception error) {
                boolean canRetry =
                        attempt < policy.maxAttempts()
                        && retryable.test(error);

                if (!canRetry) {
                    throw error;
                }

                long elapsed = System.nanoTime() - startedAt;
                long remaining = maxElapsedNanos - elapsed;

                if (remaining <= 0) {
                    throw error;
                }

                long cap = Math.min(capMillis, maxDelayMillis);

                // Full jitter: random delay in [0, cap].
                long delayMillis =
                        ThreadLocalRandom.current().nextLong(cap + 1);
                long delayNanos =
                        TimeUnit.MILLISECONDS.toNanos(delayMillis);

                if (delayNanos >= remaining) {
                    throw error;
                }

                try {
                    Thread.sleep(delayMillis);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    interrupted.addSuppressed(error);
                    throw interrupted;
                }

                capMillis = Math.min(
                        maxDelayMillis,
                        capMillis > maxDelayMillis / 2
                                ? maxDelayMillis
                                : capMillis * 2);
            }
        }

        throw new IllegalStateException("Retry loop ended unexpectedly");
    }
}
~~~

Usage example:

~~~java
RetryPolicy policy = new RetryPolicy(
        4,
        Duration.ofMillis(200),
        Duration.ofSeconds(2),
        Duration.ofSeconds(5));

String result = RetryExecutor.execute(
        () -> partnerClient.getStatus(operationId),
        policy,
        error -> error instanceof java.io.IOException);
~~~

Place these types in the same package; the public class resides in `RetryExecutor.java`, while `RetryPolicy` and `CheckedSupplier` are package-private. This is a skeleton to illustrate the policy. In production:

- The predicate must classify errors more specifically than `IOException`.
- HTTP responses must be mapped into exceptions carrying clear status/error codes.
- Requests need per-attempt timeouts smaller than the remaining invocation deadline.
- POST requests with side effects require idempotency keys.
- Inject clock/sleeper/random sources to unit-test delays without real wall-clock waiting.
- `Thread.sleep` holds the thread and invocation during the wait; use it only for short retries, never to wait for minutes inside a function.

The helper above bounds wait times between attempts; it cannot forcefully interrupt an in-flight operation. HTTP/database client timeouts and platform deadlines must still be configured separately.

## 12. Honoring Retry-After and rate limits

Some APIs return a `Retry-After` header when rate limiting or temporarily pausing service:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 3
Content-Type: application/json
~~~

The value may be an integer number of seconds or an HTTP date depending on the contract. The client must parse the supported format properly and never retry earlier than the provider requests.

A combined policy can be:

```text
chosenDelay = max(fullJitterDelay, retryAfterDelay)
```

Then verify whether `chosenDelay` fits within the remaining deadline and retry budget. If not, stop retrying or move the operation to a queue/scheduler. Never truncate `Retry-After` to a smaller value just to keep retries fast.

For 429 responses, reduce the rate of new requests or apply a token bucket/rate limiter; merely delaying current requests while continuing to send new requests at the same pace will not resolve the overload.

## 13. Retries in message/event processing functions

Functions triggered by queues or event sources typically rely on platform-driven retries. Understand the trigger semantics:

- Messages can be redelivered if the consumer fails to acknowledge.
- Stream records can be re-read when a batch fails.
- A batch can hold multiple records; a single failing record can cause the entire batch to retry unless partial failure reporting is supported.
- Retries can continue until retention expires or the retry policy limit is reached.
- Ordering can be affected by poison messages or prolonged retries.

### Distinguishing handler retries from event source retries

Example of a consumer calling a partner API:

1. Event source delivers a message to the Java function.
2. Function calls the partner API.
3. API returns 503.
4. Function may perform one or two quick in-invocation retries.
5. If still failing, function returns an error/does not acknowledge per contract.
6. Event source redelivers the message according to its retry policy.

Total attempts can equal internal retries multiplied by event source deliveries. Account for both layers and enforce bounds.

### Do not hold an invocation waiting on long retries

If you need to wait 5 minutes or longer, let the event source, workflow, or scheduler manage the delay, or persist retry state. The function should finish the invocation after saving state rather than holding concurrency during a sleep.

## 14. SQS, visibility timeout, and dead-letter queues

With Amazon SQS, a message not deleted after successful consumer processing can reappear when its visibility timeout expires. If the function runs longer than the visibility timeout, the same message can be delivered to another consumer while the first invocation is still running.

You must:

- Set the visibility timeout long enough relative to maximum processing time and internal retries.
- Set an appropriate function timeout.
- Implement idempotency because duplicate delivery can still occur.
- Configure a redrive policy and DLQ.
- Monitor `ApproximateReceiveCount`, queue age, and DLQ depth.
- Delete/ack messages only after processing completes and results are durably persisted.

A DLQ holds messages that exceeded the receive count threshold or redrive policy. A DLQ does not fix messages by itself. Triage poison messages, identify the root cause, and decide whether to fix data/config and redrive or discard per retention/compliance rules.

## 15. Pub/Sub, streams, and other event sources

Each provider has distinct semantics:

- **Google Cloud Pub/Sub:** Subscribers must acknowledge within the ack deadline; unacknowledged messages can be redelivered. Retry policies and dead-letter topics can be configured per subscription under appropriate conditions.
- **Kinesis Data Streams:** Consumers process per shard/sequence; batch errors can cause records to be re-read and stall shard progress. Consider partial batch responses, retries, and record age limits.
- **DynamoDB Streams:** Ordering is guaranteed per item key within stream semantics; batch retries must be designed to avoid duplicate side effects.
- **Azure Queue/Service Bus:** Delivery count, lock duration, abandon/dead-letter, and auto-renew semantics vary by queue/subscription type.
- **Kafka:** Consumer offsets should only commit according to the chosen processing semantics; committing before durable side effects risks data loss, while committing after can produce duplicates.

Do not apply a single generic timeout or retry count across all providers. Read the exact contract for your trigger, function integration, and runtime generation.

## 16. Dead-letter queues and safe redrive

A DLQ isolates messages that could not be processed after policy-defined deliveries/retries. It prevents poison messages from blocking the main pipeline while preserving evidence for investigation.

A safe redrive procedure:

1. Determine whether the message failed due to code, data, permissions, or a dependency.
2. Inspect message schema and version.
3. Verify the operation has not already completed and side effects have not already occurred.
4. Fix the root cause before redriving.
5. Preserve the original business idempotency key when replaying.
6. Redrive in small batches with rate limiting.
7. Monitor success, retry, and DLQ counts.
8. Halt the redrive if errors recur or downstream becomes overloaded.

Never redrive an entire DLQ at once if downstream cannot handle the burst. Never mint a new message ID to bypass deduplication. If an operation already succeeded and an older message landed in the DLQ due to an ack failure, the consumer must recognize the idempotency record and return success without repeating the side effect.

## 17. Circuit breakers, bulkheads, and rate limiters

Retries should work alongside other protective mechanisms:

| Mechanism | Purpose | When useful |
|---|---|---|
| Circuit breaker | Pause calls to a dependency when error rates spike | Dependency is experiencing prolonged failure |
| Bulkhead | Cap concurrency per dependency or workload | One slow dependency must not exhaust all threads/connections |
| Rate limiter | Cap request rate | Partner API enforces quotas or returns 429 |
| Timeout | Cap wait time per attempt | Prevent holding invocations too long |
| Retry budget | Cap extra load generated by retries | Prevent retry amplification |
| Queue/backpressure | Regulate processing rate | Arrival rate exceeds capacity |

When a circuit breaker is open, do not continue retrying new requests to that dependency. Return a handleable error or persist the operation for later retry. When transitioning to half-open, allow only a small probe volume to check if the dependency has recovered.

## 18. Timeouts and deadlines in Java serverless

Each attempt needs its own timeout. The overall deadline must cover processing time, delays, and cleanup.

Example:

- Invocation timeout: 10 seconds.
- Pre-call processing before calling partner: 1 second.
- Up to 2 partner calls needed, each capped at 2 seconds timeout.
- One delay between retries: maximum 500 ms.
- 1 second needed to persist results and return response.

Preliminary maximum budget:

```text
1s + 2s + 0.5s + 2s + 1s = 6.5s
```

This leaves a 3.5-second buffer for variance. This is only a budget calculation; real timeouts must factor in p95/p99 and other legs.

Never configure a 30-second HTTP timeout inside a function with a 10-second invocation timeout. The platform can terminate the function before the client times out and cleans up. Set each dependency timeout shorter than the remaining deadline, and do not start a new attempt when insufficient time remains.

## 19. Observability and operations for retries

Retries alter load patterns and mask failures if you only track final success rates. A dependency might fail 30% of initial requests while retries yield eventual success; looking solely at business success hides the dependency's instability from operations teams.

Monitor:

- Attempts per operation.
- Retry counts by dependency and error class.
- Retry success rate.
- Exhausted retries.
- Actual delays and backoff distribution.
- 429/5xx responses, timeouts, and connection resets.
- Invocation duration and timeouts.
- Queue age, receive counts, and ack deadline expirations.
- DLQ depth and redrive outcomes.
- Idempotency hit/duplicate counts.
- Circuit breaker open/half-open duration.

Do not use operation ID, tenant ID, or message ID as high-cardinality metric labels. Record those values in controlled logs/traces; metrics should use dependency, error class, attempt bucket, and outcome with bounded value sets.

### Structured logging

A retry log entry might contain:

~~~json
{
  "event": "dependency_retry",
  "dependency": "payment-api",
  "operationId": "pay-918",
  "attempt": 2,
  "maxAttempts": 4,
  "errorClass": "HTTP_503",
  "delayMs": 420,
  "remainingDeadlineMs": 2800
}
~~~

Never log tokens, secrets, sensitive payment details, or full request/response bodies. Correlation IDs and operation IDs link attempts together without storing raw payloads.

## 20. Testing retry policies

Retry logic should be tested using injectable clocks, sleepers, random sources, and fake dependencies to avoid real wall-clock sleeps or network flakiness.

| Case | Expected outcome |
|---|---|
| Succeeds on first attempt | No retries |
| Transient error then success | Retries per policy and returns result |
| Permanent error | Stops immediately |
| Reaches maxAttempts | Makes no further calls |
| Exceeds maxElapsed | Does not start a new attempt |
| Delay reaches maxDelay | Cap does not grow past the limit |
| Jitter | Delay falls within the defined range |
| Retry-After | Does not retry before the provider-requested time |
| Thread interrupted | Preserves interrupt flag and stops |
| Timeout after side effect | Same idempotency key produces no duplicate |
| Two concurrent requests with same key | Unique constraint/lock allows only one operation to win |
| DLQ redrive | Already-completed operation does not repeat side effects |
| Dependency remains down | Circuit breaker/rate limit protects the system |

### Testing time without real sleeps

Inject a `Sleeper` interface and controllable random source. Unit tests verify requested delays of 200, 400, 800 ms respect the cap and fall within jitter bounds. Use a fake clock to verify `maxElapsed`.

Beyond unit tests, run integration tests against queues/event sources in a test environment to verify ack behavior, visibility timeouts, retry counts, partial batch failures, and DLQ routing for your specific provider.

## 21. Common implementation mistakes

- **Retrying every exception:** Validation and authorization errors loop pointlessly; classify retryable vs. permanent errors.
- **No max attempts:** Invocations can consume unbounded time and cost; set an explicit cap.
- **Capping attempts without capping elapsed time:** A single slow attempt can blow past the deadline; enforce both.
- **Using fixed delays across all clients:** Triggers thundering herds; add jitter.
- **Unbounded backoff growth:** Delays can exceed the deadline; configure `maxDelay`.
- **Retrying POST without idempotency:** Can create duplicate transactions or resources.
- **Generating a new idempotency key per retry:** Breaks deduplication; keep the key bound to the business operation.
- **Retrying at every layer:** Request volume multiplies; designate a retry owner and overall budget.
- **Sleeping for long durations inside a function:** Holds concurrency and inflates cost; use queues/schedulers for long delays.
- **Ignoring Retry-After:** Continues pressuring a rate-limiting provider.
- **Ignoring timeout/visibility/ack deadlines:** Messages can be redelivered while the first invocation is still running.
- **Redriving the entire DLQ at once:** Triggers a fresh burst and repeats the incident.
- **Not tracking retry counts:** Dependency degradation is masked by retry success.
- **Ignoring thread interruption:** Function keeps working after the runtime signals it to stop.
- **Treating retries as exactly-once:** Delivery can still duplicate; idempotency and durable state are required.

## 22. Retry design workflow for Java serverless

When adding retries to a dependency or function, follow these steps in order:

1. Identify the operation and any potential side effects.
2. Read the dependency's contract to classify transient, permanent, and ambiguous outcomes.
3. Decide which layer owns retries: HTTP client, workflow, or event source.
4. Set `maxAttempts`, `initialDelay`, `multiplier`, `maxDelay`, and `maxElapsed`.
5. Use exponential backoff with full jitter or an appropriate jitter strategy.
6. Check the remaining invocation deadline before each retry.
7. Configure a per-attempt timeout.
8. Honor `Retry-After` and provider rate limits.
9. Use a stable idempotency key for operations with side effects.
10. For async events, configure ack/visibility timeouts, retry policies, and DLQs.
11. Limit retry amplification with retry budgets, circuit breakers, and bulkheads.
12. Monitor retry counts, exhausted retries, duplicates, and DLQs.
13. Test transient/permanent errors, timeouts, interruption, duplicates, and redrives.
14. Redrive only after identifying the root cause and at a controlled rate.

## 23. Key takeaways

Retries help overcome transient failures, yet they also add load and can repeat side effects. Classify errors before retrying, use exponential backoff with jitter, enforce both max attempts and max elapsed time, and honor the function deadline alongside the dependency's `Retry-After`.

In Java serverless, synchronous retries should stay brief with explicit timeouts. Asynchronous workloads should leverage queue, event source, or workflow retry policies paired with visibility/ack deadlines, DLQs, and controlled redrives. Do not stack multiple retry layers without accounting for total attempts.

Every operation with side effects needs a stable idempotency key and durable state. Monitor retry counts, exhausted attempts, queue age, and duplicates to spot unstable dependencies even when subsequent attempts succeed. Retries are safe only when bounded, observable, and backed by handling for uncertain outcomes.
