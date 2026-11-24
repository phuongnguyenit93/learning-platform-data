# Defining Bounded Retry Policies and Re-Execution Safety

> **Module:** Spring Framework – concurrency  
> **Group:** Exception Handling  
> **Goal:** design **bounded retry** (retrying with finite attempt count and time budget) while proving a task is **safe to re-execute** under its business contract. Retries help overcome transient failures, yet can also cause duplicate transactions, cascading overload, or mask permanent errors if done wrong.

## 1. Learning outcomes

After this lesson, you will be able to:

1. Decide **whether to retry or not** based on failure nature, operation safety, and uncertain outcome of the previous call.
2. Specify an explicit policy covering `maxAttempts`, per-attempt timeout, overall deadline, exponential backoff, jitter, stopping conditions, and exhaustion handling.
3. Distinguish a **retryable failure** from an **idempotent operation**: an error that can clear on retry does not automatically mean re-running the operation is safe.
4. Understand idempotency keys, deduplication, transaction boundaries, unique constraints, outbox, and handling “server already executed, client missed the response”.
5. Write a Java 17 program using bounded retry, test it without waiting on wall-clock time, and assert exact invocation counts.
6. Apply it to `ThreadPoolTaskExecutor`, `CompletableFuture`, and Spring Retry/Resilience4j without blocking workers indefinitely or multiplying calls across layered retries.
7. Design metrics, logging, load testing, cancellation cases, and graceful shutdown to govern retries in production.

## 2. Root problem: failure does not mean the operation did not execute

Picture an application submitting a payment request:

~~~text
Client                       Payment service
   |                                |
   +----- POST /charge ------------>|
   |                                +--- records transaction successfully
   |                                |
   |<-------- lost response ----- X |
   |                                |
   +--- timeout on client           |
   |                                |
   +--- retry without identity ---->|--- may record a second charge
~~~

The client sees only `TimeoutException` or a socket error, so it **cannot know for sure** that the server did not process it. If it retries as a new transaction, the customer can be charged twice. This is an **ambiguous outcome**, not proof of non-execution.

Proper retrying must answer **two independent questions**:

- **Is the error likely transient?** For example, a TCP connect timeout caused by brief downstream overload.
- **If the previous attempt actually succeeded, will re-executing the same request cause a new side effect?** If yes, you need idempotency/dedup/reconciliation or must not auto-retry.

An API can be **technically retryable** yet **unsafe to re-execute in business terms**. Never apply a single retry policy to all requests merely because they all throw `RuntimeException`.

## 3. Definitions: retry, attempt, idempotency, and duplicate

| Concept | Meaning |
| --- | --- |
| **Attempt** | One actual invocation of the operation/remote endpoint |
| **Retry** | An additional attempt **after** a previous attempt failed |
| **Max attempts** | Total number of attempts, **including** the initial attempt, when defined that way by the API |
| **Backoff** | Wait duration before the next attempt |
| **Jitter** | Random variation added to backoff duration to spread out retries |
| **Retry budget** | Limit on resources allowed for retries (count, time, ratio) |
| **Deadline** | Final point in time by which the entire operation must finish |
| **Idempotent** | Repeating the same request has the same **intended effect** on the system as executing it once |
| **Deduplication** | Detecting multiple deliveries with the same identity and not applying side effects twice |
| **At-least-once delivery** | May resend to avoid losing work, so the receiver must handle duplicates |
| **Unknown outcome** | Caller lost the response and does not know whether the prior work committed |

**Counting caveat:** if an application policy says **`maxAttempts = 3`**, it usually means **1 initial call + up to 2 retries**. However, another API may name it `maxRetries = 3`, meaning **1 initial call + 3 retries = up to 4 attempts**. Read the library contract and measure actual invocation counts rather than guessing from property names.

### Idempotency does not mean byte-for-byte identical responses

Under RFC 9110, idempotency refers to the **intended effect** on the server, not requiring every HTTP status code, timestamp, log, or response body to be identical. Repeating a `PUT` with the same representation may leave the same resource state, even if each request writes an audit log entry. Payment workflows carry a stricter requirement: **never record the same charge twice** when retrying the same operation identity.

## 4. Classify errors before deciding to retry

There is no universal “retry all 5xx, never retry 4xx” rule valid for every API. A starting matrix:

| Error category | Should you retry? | Conditions/explanation |
| --- | --- | --- |
| Validation error/missing required field, `400`, `422` | Usually **no** | Resending identically without fixing input will not succeed |
| Auth failure `401`/`403` | Do not retry identically | Requires credential refresh or permission change via separate logic; avoid loops |
| `404` for a permanently nonexistent resource | Usually no | Eventual-consistency systems may allow short retries if the contract states so |
| `409` conflict / optimistic locking | Analyze first | May require re-reading new state, merging, or reporting conflict; do not loop blindly |
| `408 Request Timeout` | Possible | Only when the operation is safe to re-run or has identity/dedup |
| `429 Too Many Requests` | Possible after waiting | Respect `Retry-After`/quota, cap total attempts, avoid synchronized retries |
| `502 Bad Gateway` / `503 Service Unavailable` / `504 Gateway Timeout` | Usually candidates | Check downstream behavior and idempotency; do not hammer an overloaded service |
| `500 Internal Server Error` | Maybe or maybe not | Some systems return 500 after committing; do not assume zero side effects |
| TCP connect failure before request is sent | Usually possible | Confirm the client/transport genuinely never sent the request |
| Read timeout / connection reset **after sending** | **Uncertain outcome** | Must ensure idempotency or perform status lookup/reconciliation |
| Deterministic data/parse error | No | Same input will fail again; retrying only wastes resources |
| `CancellationException` or intentional cancellation | Usually no | User or system already decided not to continue |
| `InterruptedException` | Do not auto-retry blindly | Restore interrupt flag or propagate to cancellation policy |
| JVM `Error` / `OutOfMemoryError` | Do not use ordinary retry | Handle system failure; avoid amplifying the incident |

Classification should be **made concrete by exception type and contract**. For instance, an HTTP library may group timeouts and connection errors under one common exception class, yet you must inspect the **send phase** to know whether effects may already have occurred.

Never write `catch (Exception e) { retry(); }` for all exceptions. In particular, programming bugs like `NullPointerException` or invalid data will repeat in bursts, polluting logs and inflating load.

### Retryable does not mean recoverable

- **Retryable:** trying again has a chance to change the outcome.
- **Recoverable:** there is an alternative path when completion fails (returning fallback, durable queue, requesting manual intervention).
- **Idempotent:** repeating does not increase the intended side effects.
- **Compensatable:** a compensating action can be executed after an effect already happened. Compensation is not an exactly-once guarantee.

A task can be retryable yet non-idempotent, such as calling a “create new invoice” API on each POST without an operation key.

## 5. What attributes must a retry policy have?

Write the policy as a verifiable specification:

~~~text
Operation: partner.readProduct
Identity: tenantId + productId
Max attempts: 3 (including initial call)
Retry only: connect timeout; HTTP 429/502/503/504 per contract
Never retry: validation, authorization, cancellation, interrupt
Per-attempt timeout: 700 ms
Overall deadline: 2.5 s from start
Backoff: exponential base=100 ms, cap=500 ms, full jitter
Retry-After: honor if still within deadline
On exhaustion: return error with root cause + metrics + clear status
Idempotency: read-only; no business side effects
Concurrency budget: bounded executor/queue, no unbounded retry
~~~

This is a **design example**, not default parameters for every system. The exact same strategy must not be blindly applied to `partner.createPayment` without a duplicate-charge prevention mechanism.

### 5.1. Total attempt count

Let `A` be max attempts:

~~~text
A = 1 -> 1 initial call, 0 retries
A = 2 -> 1 initial call, at most 1 retry
A = 3 -> 1 initial call, at most 2 retries
~~~

Each attempt can end in success, a non-retryable error, a timeout, or cancellation. Once the threshold is reached, **stop**—never loop forever or re-enqueue work without an overall policy.

If the system has an HTTP client that retries itself and the service layer also retries, actual requests can exceed expectations:

~~~text
service retries 3 attempts
  × SDK retries 3 attempts / service attempt
  = up to 9 downstream requests for 1 logical operation
~~~

If an API gateway also retries twice, the theoretical maximum becomes 18 calls. Know the policy at **every layer** to avoid a “retry storm”.

### 5.2. Per-attempt timeout and overall deadline

Setting `maxAttempts` is not enough. Suppose each attempt has a 10-second read timeout and 3 attempts: even with tiny backoff, the request can take over 30 seconds, far exceeding a 2-second HTTP SLA.

Distinguish:

- **Per-attempt timeout:** bounds a single network/I/O call.
- **Overall deadline:** bounds the entire logical operation including attempts and wait intervals between them.
- **Queue wait budget:** if a task must wait in `ThreadPoolTaskExecutor` before starting, that wait counts against the deadline too.
- **Client disconnect/cancellation:** if the request was cancelled, stop retrying unless work was intentionally handed off to a background workflow.

Before starting a new attempt, check whether remaining time covers **min attempt timeout + backoff** or at least a useful window. Never compute deadlines from execution start while forgetting queue wait time.

### 5.3. Increasing backoff

An exponential backoff formula without jitter:

\[
d_k = \min(d_{\max}, d_0 \cdot 2^{k-1})
\]

Where `k` is the number of failures before the next retry (`k=1` is the first delay), `d_0` is the base delay, and `d_max` is the cap.

Example with `d_0 = 100 ms`, `d_max = 500 ms`:

| After failed attempt # | Delay before next retry |
| --- | ---: |
| 1 | 100 ms |
| 2 | 200 ms |
| 3 | 400 ms |
| 4 | 500 ms (cap reached) |
| 5 | 500 ms |

Do not double a `long` unboundedly before calling `Math.min`: the expression can overflow. Compare before doubling or use a backoff library that handles overflow.

### 5.4. Jitter to prevent synchronized retry waves

If 10,000 clients receive 503 simultaneously and all wait exactly 1 second, they retry together, triggering a second load spike.

One approach is **full jitter**: given computed backoff `d_k`, pick a random delay in `[0, d_k]` (exact inclusive/exclusive bounds depend on implementation). Equal jitter and decorrelated jitter also exist with different distributions; choose per need.

Jitter does not mean dropping the cap or deadline. After picking a delay, still verify enough budget remains to execute the retry. If the server returns `Retry-After`, respect when retrying is allowed and stay within budget; do not use jitter to retry **earlier** than the server requested when the contract mandates a minimum wait.

### 5.5. Valid stopping conditions

Stop retrying when:

1. The operation succeeds.
2. A non-retryable error occurs.
3. Max attempts is reached.
4. The overall deadline expires or insufficient budget remains for the next attempt.
5. Cancelled/interrupted, Spring context is shutting down, or the client no longer needs the result.
6. A circuit breaker is open, rate/concurrency budget disallows retrying, or overload shedding commands a stop.

When attempts are exhausted, **return/emit a failed state with the cause** per contract. Never log and return a fake success, or keep retrying unboundedly in the background without job ownership.

## 6. Standalone Java 17 example: bounded retry with deterministic output

The following example implements a **loop with at most 3 attempts**, retrying only the error type explicitly tagged by the application as transient. It uses an injectable `Sleeper` so tests do not rely on `Thread.sleep`.

Create the file **`BoundedRetryDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class BoundedRetryDemo {

    @FunctionalInterface
    interface CheckedOperation<T> {
        T run() throws Exception;
    }

    @FunctionalInterface
    interface Sleeper {
        void pause(long millis) throws InterruptedException;
    }

    static final class TransientFailure extends Exception {
        TransientFailure(String message) {
            super(message);
        }
    }

    static final class RetryPolicy {
        private final int maxAttempts;
        private final long baseMs;
        private final long capMs;
        private final Sleeper sleeper;

        RetryPolicy(int maxAttempts, long baseMs, long capMs,
                    Sleeper sleeper) {
            if (maxAttempts < 1 || baseMs < 0 || capMs < baseMs) {
                throw new IllegalArgumentException("invalid policy");
            }
            this.maxAttempts = maxAttempts;
            this.baseMs = baseMs;
            this.capMs = capMs;
            this.sleeper = sleeper;
        }

        long backoffAfterFailure(int failedAttempt) {
            long delay = baseMs;
            for (int i = 1; i < failedAttempt; i++) {
                if (delay > capMs / 2) {
                    return capMs;
                }
                delay = Math.min(capMs, delay * 2);
            }
            return Math.min(capMs, delay);
        }

        <T> T call(CheckedOperation<T> action) throws Exception {
            for (int attempt = 1; attempt <= maxAttempts; attempt++) {
                try {
                    return action.run();
                } catch (TransientFailure failure) {
                    if (attempt == maxAttempts) {
                        throw failure;
                    }

                    long delay = backoffAfterFailure(attempt);
                    System.out.println(
                            "retry after " + attempt + " = "
                                    + delay + "ms");

                    try {
                        sleeper.pause(delay);
                    } catch (InterruptedException interrupted) {
                        Thread.currentThread().interrupt();
                        throw interrupted;
                    }
                }
            }
            throw new AssertionError("unreachable");
        }
    }

    public static void main(String[] args) throws Exception {
        // Test sleeper: does not wait in real wall-clock time.
        RetryPolicy retry = new RetryPolicy(3, 100, 500, ms -> {});

        AtomicInteger calls = new AtomicInteger();
        String result = retry.call(() -> {
            int attempt = calls.incrementAndGet();
            System.out.println("call = " + attempt);
            if (attempt < 3) {
                throw new TransientFailure("temporary");
            }
            return "OK";
        });

        System.out.println("result = " + result);
        System.out.println("attempts = " + calls.get());

        AtomicInteger invalidCalls = new AtomicInteger();
        try {
            retry.call(() -> {
                invalidCalls.incrementAndGet();
                throw new IllegalArgumentException("bad request");
            });
        } catch (IllegalArgumentException failure) {
            System.out.println(
                    "not retryable = " + failure.getMessage());
        }
        System.out.println(
                "validation attempts = " + invalidCalls.get());

        AtomicInteger downCalls = new AtomicInteger();
        try {
            retry.call(() -> {
                downCalls.incrementAndGet();
                throw new TransientFailure("service unavailable");
            });
        } catch (TransientFailure failure) {
            System.out.println(
                    "exhausted = " + failure.getMessage());
        }
        System.out.println(
                "exhausted attempts = " + downCalls.get());
    }
}
~~~

### Compile and run

~~~bash
javac BoundedRetryDemo.java
java BoundedRetryDemo
~~~

**Exact program stdout**:

~~~text
call = 1
retry after 1 = 100ms
call = 2
retry after 2 = 200ms
call = 3
result = OK
attempts = 3
not retryable = bad request
validation attempts = 1
retry after 1 = 100ms
retry after 2 = 200ms
exhausted = service unavailable
exhausted attempts = 3
~~~

### Output explanation

- In the first case, attempts 1 and 2 throw `TransientFailure`, so retries are scheduled after the computed delays; attempt 3 returns `"OK"`. Total: **3 attempts**, **2 retries**.
- `IllegalArgumentException` is not caught by the retry loop, so it is **called only once**, rather than trying to “fix” invalid input by retrying.
- When downstream keeps failing, the loop stops at attempt 3 and **rethrows the final error** `TransientFailure`; no fourth attempt is made.
- Wait durations are only **planned/recorded** rather than actually sleeping because `ms -> {}` is passed. That tests backoff logic without scheduler flakiness.
- If replaced with `Thread::sleep`, the **thread calling `RetryPolicy.call`** itself blocks while waiting; that fits only synchronous or managed worker environments. Never call it on an event loop or use it to tie up request threads for long durations.
- The demo intentionally isolates core policy mechanics (maxAttempts, error type, backoff, interruption) from full production policies, which must add **overall deadlines, per-attempt timeouts, jitter, HTTP status/`Retry-After`, metrics observability, and idempotency**. Do not copy the demo verbatim into a real-money client.

### Why not write a while(true)?

`while(true)` is safe only when every path proves a finite stopping condition. The policy here uses `for (attempt <= maxAttempts)`, preventing infinite loops even if transient errors repeat forever. Components with **multi-layer** retries must still enforce an overall budget, rather than relying solely on local limits.

## 7. Re-execution safety: three operation types

### 7.1. Read-only and operations with no intended side effects

Looking up a product by ID or reading a well-defined status can usually be retried after network errors. However, **GET is not automatically safe** if the endpoint actually mutates critical state (e.g., using GET to trigger a money transfer): that is an API with broken semantics. Time bounds are still required to avoid bombarding downstream.

### 7.2. State-setting operations (business-idempotent)

For example `setInventoryLevel(productId, 10)`: calling the same request multiple times still sets inventory to 10. In HTTP, `PUT` is idempotent by standard semantics when the resource server honors the contract.

Contrast with `incrementInventory(productId, 10)`: calling it twice adds 20—**not idempotent**. Method names or HTTP verbs alone do not make addition safe to retry.

### 7.3. Creation or money-transfer operations (non-idempotent without a key)

Example:

~~~text
createPayment(order=7, amount=500000)
createPayment(order=7, amount=500000)
~~~

If the API generates a new payment ID on every call, the result is **two payments**, despite identical payloads. To make retries safe, identify a single logical operation—for instance `Idempotency-Key: pay-order-7-v1`—and deduplicate on the receiving side.

**Do not generate a new key on each attempt.** The same logical operation must carry the same idempotency key across retries, including after timeouts/lost responses. If a request is genuinely a new transaction, it must use a new identity per business contract.

## 8. Idempotency key: minimum contract

A payment or job-creation model may define:

~~~http
POST /payments HTTP/1.1
Idempotency-Key: 8fb1e0c4-... 
Content-Type: application/json

{"orderId":"order-7","amount":500000,"currency":"VND"}
~~~

This is an **illustrative HTTP example**; the key is a structural placeholder, not a real issued token.

The server side needs to:

1. **Authenticate/scope** the key: scope keys under tenant/account or namespace so customer A cannot accidentally collide with B.
2. **Verify payload consistency** using a stable request fingerprint. If the key matches but amount/quantity differs, reject as conflict/invalid per API contract instead of silently returning the old response.
3. **Claim the key atomically**: two concurrent requests with the same key must never both pass the check and execute side effects.
4. **Persist state** such as `IN_PROGRESS`, `SUCCEEDED`, `FAILED_FINAL`, and the business result so duplicate requests know how to act.
5. **Define a policy for `IN_PROGRESS`**: bounded wait, return 202/409, or instruct polling; never claim success prematurely.
6. **Retain keys long enough** to cover the window in which clients may retry/replay, with clear TTL and cleanup procedures.
7. **Handle mid-step crashes**: key stored before side effect ran, or side effect ran before outcome was saved; use transaction boundaries/outbox/provider idempotency/reconciliation.

### Basic state table

| Key state | New request with same key/payload | Conditions to remember |
| --- | --- | --- |
| Key absent | Attempt atomic claim and start operation | UNIQUE constraint/transaction/conditional write |
| `IN_PROGRESS` | Do not execute side effect a second time; return status/bounded wait | If owner dies, need safe lease/timeout/recovery |
| `SUCCEEDED` | Return stored result or status of prior operation | Do not create another payment/job |
| `FAILED_FINAL` | Return stored terminal error, or contract allows a new operation with a new key | Do not treat the same key as a brand-new transaction |
| Existing key, different payload | Reject per contract (usually 409 or corresponding error) | Prevent misusing keys |

Never write `if (!map.containsKey(key)) { performSideEffect(); map.put(key,...); }` in a concurrent environment: two threads/pods can both pass the check before writing. Local `synchronized` or `ConcurrentHashMap` also **does not** solve multi-pod/replica deployments or durability across restarts.

### Atomic claim and business transactions

If the side effect updates **the same database**, you can leverage a UNIQUE index and transaction to claim the key + apply business writes + save outcome within an appropriate boundary. If the side effect calls an **external payment provider**, a local DB transaction **cannot** make a remote HTTP call and DB commit atomic. In that case, forward the **same idempotency key to the provider** if supported, write an outbox/status record, and reconcile uncertain outcomes.

**Do not promise end-to-end exactly-once merely because an idempotency table exists.** In practice, the goal is a single logical effect per key within the contract and failure model the system can control.

## 9. Java 17: single-JVM internal idempotency demo

This short example shows the same identity returning the same result within **one process's memory**, without incrementing logical operations a second time. It is **not** a production payment implementation or distributed idempotency.

Create the file **`LocalIdempotencyDemo.java`**:

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

public class LocalIdempotencyDemo {
    private static final ConcurrentHashMap<String, String> operations =
            new ConcurrentHashMap<>();

    private static final AtomicInteger committed =
            new AtomicInteger();

    static String recordOnce(String key) {
        return operations.computeIfAbsent(key, ignored -> {
            int number = committed.incrementAndGet();
            return "operation-" + number;
        });
    }

    public static void main(String[] args) {
        System.out.println("first = " + recordOnce("order-7"));
        System.out.println("retry = " + recordOnce("order-7"));
        System.out.println("logical operations = " + committed.get());
    }
}
~~~

Run:

~~~bash
javac LocalIdempotencyDemo.java
java LocalIdempotencyDemo
~~~

**Deterministic stdout:**

~~~text
first = operation-1
retry = operation-1
logical operations = 1
~~~

In the demo, `computeIfAbsent` is an appropriate atomic operation for inserting one entry in a `ConcurrentHashMap` within the same JVM; the callback computes an in-memory value without calling downstream.

**Important warning:** Never place real money transfers or email sends inside a `computeIfAbsent` callback and assume production safety. If the callback causes an external side effect and the JVM dies before the map stores the entry, a retry can repeat the side effect. If multiple pods each have their own map, each pod can execute once. Avoiding real duplicates requires durable state coordinated with the business operation/provider.

## 10. Realistic data model for idempotent operations

An illustrative PostgreSQL table:

~~~sql
CREATE TABLE idempotent_operations (
    tenant_id        VARCHAR(100) NOT NULL,
    operation_key    VARCHAR(200) NOT NULL,
    request_hash     VARCHAR(128) NOT NULL,
    status           VARCHAR(30)  NOT NULL,
    response_payload TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, operation_key)
);
~~~

This is **illustrative DDL**; add length limits, indexes, retention, and access controls per system requirements. `PRIMARY KEY` guarantees two transactions cannot insert the same key in one database. However, this table alone **does not** guarantee atomicity with an external system.

A reference flow:

~~~text
Request (tenant, idempotency key, request body)
                |
                v
Validate + fingerprint request body
                |
                v
Atomic INSERT / claim key
                |
       +--------+--------------------+
       |                             |
    claimed                    already exists
       |                             |
       v                             +-- mismatch body -> reject
 status IN_PROGRESS                  |
       |                             +-- SUCCEEDED -> reuse outcome
       v                             |
 perform business side effect        +-- IN_PROGRESS -> wait/poll policy
       |                             |
       v                             +-- failed -> follow explicit contract
 Save durable outcome
       |
       v
 Return response
~~~

The hardest part is a **crash between the side effect and saving the outcome**. If both mutations target the same database, use an appropriate transaction. When calling an external system, rely on remote idempotency tokens or a real-state verification workflow.

### When IN_PROGRESS gets stuck

An `IN_PROGRESS` record must not stay locked forever if the old processing instance died. Use leases + owner tokens/fencing; when the lease expires, the new worker must determine whether the previous attempt already took effect before re-running. Simply deleting the record and re-running without reconciliation can cause duplicates.

### When the payload changes

Same key, one request asks for 500,000 VND and another asks for 700,000 VND: that is **not** the same logical command. The server must reject per contract rather than returning the old result or triggering another side effect under the same key.

### When the key expires

A TTL shorter than the client's replay window turns a late retry into a brand-new operation. Choose retention based on retry SLAs, queue processing, reconciliation windows, and business characteristics; payments/orders require more durable business audit trails than short-lived quota caches.

## 11. Concurrency patterns and where to place retries

### 11.1. Retrying in the HTTP client

For downstream calls, retries usually fit best **at the remote call boundary**, where error types, HTTP status codes, send status, and deadlines are known. Pass the operation identity via headers rather than generating a new key per attempt.

~~~java
public Receipt callProvider(String key, ChargeRequest request) {
    return paymentHttpClient.charge(key, request);
}
~~~

This is a **service snippet**; `Receipt`, `ChargeRequest`, and `paymentHttpClient` belong to the application. For `charge`, retrying is safe only when the provider supports idempotency semantics on `key`, or strong status lookup/reconciliation exists.

### 11.2. Retrying inside ThreadPoolTaskExecutor

A `ThreadPoolTaskExecutor` manages only **workers/queues**, without creating a business-error retry policy on its own. If a task throws an exception:

- `execute(Runnable)` with a plain Runnable may let errors escape to the worker/error observer.
- `submit(Callable)` typically captures the error in a `Future`; the caller calls `get()` to see `ExecutionException` with its cause.
- **Task rejection** errors when the pool is saturated happen at submission time; resubmitting immediately in a zero-delay loop worsens overload.
- A worker sleeping in `Thread.sleep(backoff)` continues **occupying a slot**; thousands of waiting retries can starve threads. Use a bounded scheduler/delayed queue or non-blocking async retries when many retries can be pending.

**Never** run an unbounded retry loop inside a `Runnable` without checking state: if the task is cancelled, shut down, or the context closes, the worker may fail to exit promptly.

### 11.3. Retrying with CompletableFuture

A failed future **does not re-run itself** merely because you call:

~~~java
future.exceptionally(error -> fallback);
~~~

That is **stage error recovery**, not creating a new attempt. To retry a `CompletableFuture`, you need a **supplier producing a fresh future per attempt** and coordination for delays/exhaustion:

~~~java
Supplier<CompletableFuture<Receipt>> freshAttempt =
        () -> provider.chargeAsync(sameIdempotencyKey, request);
~~~

This is a **snippet**, assuming `provider`, `sameIdempotencyKey`, `request`, and `Receipt` exist.

Each attempt must invoke `freshAttempt.get()` to start a new operation under the same logical idempotency identity; merely attaching another callback to **the same already-exceptional future** does not retry.

A bounded scheduler can schedule the next attempt:

~~~java
scheduler.schedule(
        () -> startNextAttemptIfAllowed(),
        delayMillis,
        TimeUnit.MILLISECONDS);
~~~

This is a **snippet**, requiring `scheduler`, `startNextAttemptIfAllowed()`, `delayMillis`, and real deadline logic. Non-blocking scheduling avoids tying up workers, yet the job scheduler also needs queue capacity, ownership, cancellation, and shutdown handling. When a composed future fails, distinguish retrying the **whole chain** vs. only the failing source.

### 11.4. @Async and Spring proxies

`@Async` controls how a method is dispatched through a Spring proxy—it **does not retry automatically**. When combining `@Async` with retry annotations:

- Verify interceptor ordering and actual return types.
- `@Async void` returns no Future for callers to inspect, requiring `AsyncUncaughtExceptionHandler` or separate job monitoring.
- `@Async CompletableFuture` requires observing exceptional futures; retrying a completion stage differs from retrying a synchronous method.
- Self-invoking `this.method()` inside the same bean in default proxy mode bypasses `@Async` and proxy advice such as retry.
- Do not assume caller transactions or MDC/security context transfer automatically into workers.

When work has critical side effects, a persistent queue with job IDs and durable retry state usually fits better than an in-JVM fire-and-forget callback.

## 12. Spring Retry and Spring Framework 7: two easily confused counting rules

There are **two distinct APIs** to distinguish by version/dependency, even when the annotation shares the name `@Retryable`.

### 12.1. Spring Retry 2.x (separate module used in many Spring 6 / Boot 3 apps)

Spring Retry lives in dependency **`org.springframework.retry:spring-retry`**, not an out-of-the-box feature automatically active simply by having Spring 6.2. For annotation/proxy usage, configure `@EnableRetry` and the required Spring AOP components.

Spring Retry 2.x example:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.annotation.EnableRetry;

@Configuration
@EnableRetry
public class RetryConfiguration {
}
~~~

A service:

~~~java
import org.springframework.retry.annotation.Backoff;
import org.springframework.retry.annotation.Retryable;
import org.springframework.stereotype.Service;

@Service
public class RemoteCatalog {
    private final PartnerClient client;

    public RemoteCatalog(PartnerClient client) {
        this.client = client;
    }

    @Retryable(
            retryFor = TemporaryPartnerFailure.class,
            maxAttempts = 3,
            backoff = @Backoff(
                    delay = 200,
                    multiplier = 2.0,
                    maxDelay = 1000))
    public Product load(String productId) {
        return client.fetch(productId);
    }
}
~~~

These are **illustrative classes in a Spring Retry 2.x application**, requiring project-defined `PartnerClient`, `TemporaryPartnerFailure`, `Product`, and Spring Retry/AOP dependencies. `maxAttempts = 3` means **3 total invocations** (initial call + up to 2 retries). Example backoffs: 200 ms then 400 ms, if both retries occur.

**Proxy warning:** calling `this.load(...)` from the same bean in proxy mode can bypass retry advice. Call from another bean through the Spring proxy. Retry annotations also do not replace overall deadlines/idempotency and can block the thread during backoff depending on the interceptor.

### 12.2. Spring Framework 7 core resilience

Starting in **Spring Framework 7.0**, core Spring Framework introduces its own resilience API, including an `@Retryable` annotation in package **`org.springframework.resilience.annotation`**. It is **not identical** to `org.springframework.retry.annotation.Retryable` from the Spring Retry module.

In the Framework 7 mechanism, the attribute counting retries after the initial call (for example `maxRetries` in the reference) is defined as the **number of retries**; core documentation specifies total attempts equal **1 initial attempt + permitted retries**. This is a critical reason to verify the exact **version** and **package** of the annotation you import—do not port `maxAttempts=3` from Spring Retry to a `maxRetries=3` API assuming there will still be only 3 total calls.

When upgrading Spring/Boot, verify the dependency graph, annotation imports, proxy activation, and actual retry semantics with invocation-counting tests. Do not assume a Spring Framework 6 app has Framework 7's core `@Retryable` package.

### 12.3. When to use a library instead of writing your own loop?

- **Spring Retry:** synchronous method retry logic, bean/proxy integration, straightforward exception classifiers and recovery.
- **Resilience4j Retry:** retry configuration, metrics, composition with CircuitBreaker/RateLimiter/Bulkhead; pay attention to decorators and how async results are handled.
- **HTTP clients/SDKs with built-in retries:** leverage when endpoint semantics are known and deadlines/idempotency are in place.
- **Custom loop:** fits learning examples or highly specialized policies, provided you manage timeouts, schedulers, observability, and race conditions yourself.

Whichever tool you use, **never let multiple layers auto-retry the same operation** without knowing total attempts.

## 13. Retry vs. Circuit Breaker, Rate Limiter, and Bulkhead

| Mechanism | Core question | When does it help? |
| --- | --- | --- |
| Retry | “Is this transient failure worth trying again within budget?” | Brief glitches, transient errors, operation safe to re-run |
| Circuit Breaker | “Downstream is failing en masse; should we pause sending requests temporarily?” | Avoid hammering an unhealthy dependency |
| Rate Limiter | “How many requests per time window are permitted?” | Enforce quotas/rates per client or backend |
| Bulkhead/Semaphore | “How many concurrent calls may hold resources?” | Protect DB/HTTP connections, memory, workers |
| Timeout | “How long may one attempt or the whole operation wait?” | Prevent requests from hanging forever |
| Idempotency | “Will repeating the same operation create duplicate side effects?” | Prevent double-charging/double-ordering/duplicate jobs |
| Outbox/Job store | “Will a crash/restart lose execution intent or retry state?” | Workflows needing durability and retries across process restarts |

**Retries add load**, rather than shedding load: with a 10% failure rate and continuous retries, downstream receives more traffic than the baseline request rate. When downstream is saturated, backoff/jitter, circuit breakers, rate limits, and retry budgets curb amplification.

### Calculating multi-layer retry storms

If a frontend API allows 3 attempts and a backend service also allows 3 attempts on the same remote call, one business request can generate **9 remote calls** during persistent failures. If the user client also retries twice, total becomes **18 remote calls**. Decide **which layer owns primary retries**, while other layers propagate causes/enforce deadlines instead of multiplying attempts.

### Ratio-based retry budgets

Besides per-operation `maxAttempts`, many systems enforce “retry tokens” or cap retries within a time window. The goal is preventing thousands of concurrent operations each retrying 3 times during a dependency outage from overwhelming the system. Permitted retry ratios should reflect SLOs/downstream capacity and throttle down when circuit breakers open.

## 14. Handling HTTP Retry-After properly

`Retry-After` is an HTTP header expressing either **a delay in seconds** or **an HTTP-date timestamp**; do not blindly interpret every value as milliseconds. Example:

~~~http
HTTP/1.1 503 Service Unavailable
Retry-After: 3
Content-Type: text/plain

Temporarily unavailable
~~~

The client can consider retrying **after at least 3 seconds** if still within the overall deadline and the operation is safe to re-run. If the SLA allows waiting at most 1 second, the right policy may be **not retrying**, returning an error with cause instead of ignoring the header.

With 429, a rate limiter may suggest when quota recovers. However, not every 429/503 response includes `Retry-After`; clients need fallback backoff with capped jitter. Parse HTTP-dates per standard, use a reliable clock, and account for network latency.

## 15. Controlling timeouts and cancellation in Spring concurrency

A request timeline:

~~~text
HTTP request deadline = 2.5 s
    |
    +-- thread pool queue wait
    +-- attempt 1: connect + read timeout
    +-- backoff
    +-- attempt 2
    +-- backoff
    +-- attempt 3
    |
    v
Response / failure before deadline
~~~

**Queue wait time** in the executor still comes out of the overall budget and cannot be ignored. Track deadlines using an appropriate elapsed-time source such as `System.nanoTime()` for in-JVM timeouts (do not rely on `currentTimeMillis()` as a monotonic source).

### When interrupted

In blocking code:

~~~java
try {
    Thread.sleep(delayMillis);
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException(
            "Retry interrupted", interrupted);
}
~~~

This is a **snippet**, requiring `delayMillis` to be already computed. Tasks must respect shutdown/cancellation; never catch an interrupt and immediately retry again.

### When CompletableFuture times out

`future.orTimeout(2, TimeUnit.SECONDS)` completes the future exceptionally if unfinished by the deadline. It does not automatically stop remote requests or roll back side effects that already happened. Similarly, `future.get(2, TimeUnit.SECONDS)` expiring **only means the caller stopped waiting**, while the task may keep running.

When orchestrating multiple attempts, propagate cancellation to the active attempt if the underlying client supports it and cancelling creates no new side effects; never cancel a payment request that already reached the server and then assume no payment occurred.

## 16. Uncertain outcomes: handling per business contract

Suppose an order-creation service:

1. Client sends `createOrder(orderKey=K)`.
2. Server commits the order successfully.
3. Connection resets before the client receives the order ID.
4. Client receives `IOException`.

Three strategies:

**A. Idempotency key + server dedup:** client retries with **the same K**. Server returns the existing order ID without creating a new order.

**B. Status lookup:** before retrying a creation operation, query by `clientOrderId=K` or check committed state. Only if confirmed absent do you consider resending; lookup itself must account for races/concurrent requests.

**C. No identity/dedup and high impact:** do not auto-retry. Report an indeterminate status, record details for reconciliation, or require operator/manual review.

Avoid reporting “order failed” as a certainty when the true outcome is **unknown**; if the user clicks again as a brand-new order, the consequences can be worse.

### Outbox and retries after crashes

In workflows that must emit events alongside DB writes, a **transactional outbox** persists business state and an outbox row in the same transaction; a worker publishes the outbox afterward. Delivery may be **at-least-once**, so consumers must still be idempotent on event ID. Never treat outbox as a magical cross-system exactly-once guarantee.

## 17. Decision flowchart before every retry

~~~text
Attempt failed
        |
        v
Cancelled / interrupted / shutting down?
   | yes -> STOP; return cancellation/interruption
   | no
   v
Does the exception/HTTP status genuinely have a chance to recover?
   | no -> STOP; report original error
   | yes
   v
Is the operation safe to re-execute?
   | no/unknown -> STATUS LOOKUP / RECONCILE / STOP
   | yes
   v
Reached maxAttempts / retry budget?
   | yes -> STOP; report exhaustion
   | no
   v
Remaining deadline after backoff/Retry-After?
   | no -> STOP; report deadline exhaustion
   | yes
   v
Choose delay with backoff + jitter / Retry-After
        |
        v
Wait non-blockingly if async, control queue
        |
        v
Retry SAME logical operation identity
        |
        +-- record attempt metric and loop back
~~~

The workflow must distinguish “status lookup” from “side-effecting retry”; some read-only lookups also have their own quotas and timeouts.

## 18. Monitoring to tell whether retries are helping or hurting

Minimum metrics:

| Metric | Meaning |
| --- | --- |
| `operation_attempts_total` | Total actual attempts per operation/endpoint |
| `operation_retries_total` | Additional attempts after the first |
| `operation_retry_exhausted_total` | Logical operations exhausting retry quota |
| `retry_delay_ms` | Distribution of delays and jitter |
| `attempt_latency_ms` | Latency per attempt |
| `operation_latency_ms` | Total latency including queue/backoff |
| `retry_success_after_failure` | Share of operations succeeding after retries |
| `retry_not_safe_total` | Times retry was skipped due to unknown outcome/missing idempotency |
| `idempotency_duplicate_total` | Duplicate-key requests deduplicated |
| `idempotency_in_progress` | In-flight keys and how long they have been held |
| `downstream_rejections` | 429/503/connection saturation, indicating retries are amplifying load |

Attach correlation ID, logical operation ID, and **attempt number** to logs/traces. Avoid treating each retry as an unrelated transaction with a brand-new ID, which breaks causal correlation.

Do not log raw payment keys, security tokens, sensitive payloads, or unmasked PII; hash/scope keys and use internal job IDs instead. Alert when retry exhaustion rises or p99 latency climbs even when final success rate looks healthy.

## 19. Critical tests

### 19.1. Exact invocation count tests

Use a fake operation throwing `TransientFailure` twice before succeeding. Assert total calls = 3, scheduled delays = 100/200 ms in the example config, result = OK. For validation errors, assert calls = 1. For permanent transient failures, assert calls never exceed `maxAttempts`.

### 19.2. Timing tests using fake clocks/sleepers

No need for `Thread.sleep(1000)` in unit tests. Inject a controllable `Sleeper`/`Clock` or scheduler; assert the policy chose delays, deadlines, and cancellation correctly. When testing full jitter, inject a seeded or fake `Random` to test distribution/bounds without measuring OS wall-clock precision.

### 19.3. Post-commit timeout tests

Simulate the server **already committing** while the response is lost. Client retries with the same key; assert actual business transactions = 1 and the same resource is returned. If the system lacks dedup, this test must fail fast as **unsafe to retry**, rather than masking it with more retries.

### 19.4. Concurrent duplicate-key request tests

Have two threads/pods concurrently claim the same key: only one owner executes the side effect. The second receives the prior result, pending status, or conflict per contract. Use `CountDownLatch` in unit tests and real database/Redis transactions in integration tests; local `synchronized` does not prove multi-pod safety.

### 19.5. Retry storm and nested policy tests

Load-test with 30% of downstream calls returning 503 while holding client request rate constant and observing **total requests reaching downstream**. If both upstream and SDK retry, verify the multiplier. Test circuit-breaker/retry-budget protection and behavior when downstream never recovers.

### 19.6. Cancellation/shutdown tests

Close the Spring context or cancel the future while waiting in backoff. Verify no new attempts start after cancellation/deadline; workers are freed, resources released, and no infinite retry queue remains.

### 19.7. Error classification tests

Write separate tests for validation, authentication, conflict, pre-send timeout, post-send timeout, 429/503 with `Retry-After`, 500 after commit, interrupt/cancel, and internal code bugs. **Do not** test only the happy path of “fail once then succeed”.

## 20. Common mistakes

**Mistake 1: “Catch every Exception and retry”.**  
Data errors, programming bugs, or permission denials will not heal themselves; retrying adds load and hides root causes.

**Mistake 2: “maxAttempts=3 means 3 retries plus the first call”.**  
Wrong in Spring Retry 2.x: `maxAttempts` includes the initial call. Other APIs use `maxRetries` for subsequent tries; read the exact contract.

**Mistake 3: “A timeout proves the server never ran the work”.**  
Wrong: the server may have committed and merely lost the response. Account for unknown outcomes.

**Mistake 4: “POST with the same payload is idempotent”.**  
Not by default. If the API creates a new record each time, identical payloads still create two records/payments.

**Mistake 5: “Generate a new idempotency key per attempt just to be safe”.**  
On the contrary, that breaks deduplication across attempts of the same logical operation.

**Mistake 6: “ConcurrentHashMap alone is safe”.**  
It is not shared across pods, not durable across crashes, and not atomic with remote side effects.

**Mistake 7: “Fixed backoff is enough when thousands of clients fail together”.**  
Synchronized retries after the same fixed delay cause thundering herds; add jitter and budgets.

**Mistake 8: “We have maxAttempts so we don't need a deadline”.**  
Three 20-second I/O attempts still blow past a one-minute SLA.

**Mistake 9: “We have an overall deadline so we don't need per-attempt timeouts”.**  
An unbounded I/O attempt may not honor the deadline if the client is not configured to abort.

**Mistake 10: “Thread.sleep inside @Async costs no resources”.**  
It holds the worker thread and can fill pools and queues; use a scheduler for many long retries.

**Mistake 11: “CompletableFuture.exceptionally is retry”.**  
It handles exceptional completion; retrying requires calling a supplier to create a fresh attempt.

**Mistake 12: “Every layer retrying 3 times improves success for free”.**  
It can generate 9 or 27 real calls to the same dependency.

**Mistake 13: “@Retryable works on any method”.**  
With proxy-based Spring Retry, self-invocation usually bypasses advice; call through a bean/proxy, configure AOP properly, and test for real.

**Mistake 14: “@Async void throws errors up to the caller”.**  
Exceptions in workers do not propagate automatically to callers; use a handler or Future/status tracking.

**Mistake 15: “Saving an idempotency key guarantees exactly-once”.**  
Crashing after a remote side effect yet before saving the outcome can still cause duplicates. Use provider keys, transactions/outbox, and reconciliation.

**Mistake 16: “If retries exhaust, return success to keep users happy”.**  
That hides failures. Report failed/indeterminate status or a trackable pending job.

**Mistake 17: “Always retry once Retry-After elapses”.**  
If the deadline has expired or the operation is unsafe, stop.

**Mistake 18: “Retries always help an overloaded system”.**  
Retries increase traffic. When backends are saturated, they prolong outages; combine backoff/jitter, rate limits, bulkheads, and circuit breakers.

## 21. Self-practice exercises

### Exercise 1 — Count attempts accurately

Policy `maxAttempts=4`, operation keeps failing transiently. How many total calls happen?

**Answer:** at most 4 attempts—1 initial call + 3 retries if the policy code uses this definition. Do not confuse with `maxRetries=4` in other APIs.

### Exercise 2 — Validation error

An API receives a missing `customerId` and returns 400. Should it auto-retry?

**Answer:** do not retry the same payload. Fix the input or return a validation error to the client.

### Exercise 3 — Timeout after sending payment

Client sent a transfer request and hit a read timeout. Can it resend with a new key?

**Answer:** unsafe. The server may have recorded the transaction. Reuse the same idempotency key if the provider supports it, or run status lookup/reconciliation; without guarantees, handle unknown outcome per contract.

### Exercise 4 — Calculate backoff

Base = 100 ms, multiplier 2, cap 500 ms, `maxAttempts=5`. If every attempt fails, what delays occur between attempts before exhaustion?

**Answer:** 100 ms, 200 ms, 400 ms, 500 ms — 4 wait intervals for up to 5 calls. Jitter may vary actual delays within defined bounds.

### Exercise 5 — Spring Retry vs. Framework 7

One team uses Spring Retry `org.springframework.retry.annotation.Retryable(maxAttempts=3)`. Another references Spring Framework 7 core `@Retryable` with `maxRetries=3`. Is the maximum invocation count the same?

**Answer:** no. In Spring Retry, `maxAttempts=3` is 3 total calls; in Framework 7 core, `maxRetries=3` can yield 1 initial call + 3 retries. Verify the exact API and imports.

### Exercise 6 — Multi-layer retries

The HTTP client retries 3 attempts, and the service also retries 3 attempts. On continuous failure, what is the maximum downstream calls for one operation?

**Answer:** potentially 9. Choose a single retry owner and enforce an overall budget.

### Exercise 7 — Idempotency across multiple pods

Two requests with the same key hit two pods, each using its own `HashMap` to dedup. Does this guarantee once-only execution?

**Answer:** no. The two maps share no state. Use a database/atomic coordination or provider idempotency to block duplicates cluster-wide.

### Exercise 8 — Full thread pool

A `ThreadPoolTaskExecutor` is full. A service catches `TaskRejectedException` and immediately resubmits in a `while(true)` loop. Consequence?

**Answer:** the loop burns CPU and pushes more pressure onto an already full executor. Fail fast or retry with bounded attempts/backoff while addressing queue limits and ownership.

### Exercise 9 — Missing Retry-After

Server returns 503 with no `Retry-After` header. What should you do?

**Answer:** if the operation is safe to re-run, use backoff with jitter while respecting attempts/deadline/budget; if unsafe, stop and reconcile instead of blindly retrying.

### Exercise 10 — CompletableFuture

Does `future.exceptionally(ex -> defaultValue)` issue another HTTP request?

**Answer:** no. It only recovers the future's failure. Real retry requires a supplier creating a fresh attempt plus delay/exhaustion orchestration.

## 22. Spring production checklist

- [ ] Define logical operations and idempotency scope clearly: user/tenant/key/payload hash.
- [ ] Classify retryable exceptions/statuses; never blindly retry validation/bugs/interrupts.
- [ ] **Bounded** max attempts, with counting behavior verified by tests.
- [ ] Enforce per-attempt timeouts, overall deadlines, and cross-layer retry budgets.
- [ ] Capped backoff with jitter; parse `Retry-After` with proper units and bounds.
- [ ] Never retry non-idempotent operations on unknown outcomes without dedup/lookup.
- [ ] Preserve the **same idempotency key** across all retries of one logical operation.
- [ ] Use atomic claim/unique constraints; handle mismatches, `IN_PROGRESS`, crashes, and TTLs.
- [ ] For external side effects: provider idempotency/outbox/reconciliation, never infer exactly-once from a local DB alone.
- [ ] Avoid excessive nested retries; account for retries already enabled inside SDKs/clients.
- [ ] Avoid long sleeps on small pools or request threads; prefer bounded schedulers when async.
- [ ] With Spring Retry: verify dependencies and proxies, public methods invoked via beans; distinguish Spring Framework 7 core.
- [ ] With `@Async`/`CompletableFuture`: attach error observers and handle cancellation lifecycles.
- [ ] Metrics cover attempts, retries, exhaustion, deadlines, duplicates, latency, and saturation.
- [ ] Tests cover post-commit timeouts, concurrent duplicates, failover, and shutdown.
- [ ] Never return fake success on exhaustion/unknown outcome; report trackable status.

## 23. Summary

**Good retry = right error + right operation + finite attempts + time/resource budget + backoff/jitter + observable outcome.** None of these conditions are optional when errors can affect business state.

**Re-execution safety** requires more than resending the same request: identify the same **logical operation identity**, guarantee **the same side effect is not applied twice** within the contract, and handle uncertain outcomes caused by timeouts/crashes.

In Spring concurrency, `ThreadPoolTaskExecutor`/`@Async` handles task dispatch, not retries or idempotency on its own. Spring Retry or Resilience4j helps orchestrate retries, yet cannot make an unkeyed money transfer safe. If you cannot prove a retry is safe, **stop, look up status, or reconcile**, instead of retrying blindly.

## References

- Java SE 17 — `ExecutorService`, `Future`, `ScheduledExecutorService`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html
- Java SE 17 — `ConcurrentHashMap`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html
- Java SE 17 — `CompletableFuture`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- RFC 9110 — HTTP Semantics, safe/idempotent methods and `Retry-After`: https://www.rfc-editor.org/rfc/rfc9110.html
- RFC 6585 — HTTP 429 Too Many Requests: https://www.rfc-editor.org/rfc/rfc6585.html
- Spring Retry 2.x `@Retryable` (maxAttempts includes initial attempt): https://docs.spring.io/spring-retry/docs/current/apidocs/spring.retry/org/springframework/retry/annotation/Retryable.html
- Spring Retry `@EnableRetry`: https://docs.spring.io/spring-retry/docs/current/apidocs/spring.retry/org/springframework/retry/annotation/EnableRetry.html
- Spring Framework 7 — Core Resilience Features: https://docs.spring.io/spring-framework/reference/core/resilience.html
- Spring Framework — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- AWS Builders' Library — Timeouts, retries, backoff with jitter: https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/
- Microservices.io — Transactional Outbox Pattern: https://microservices.io/patterns/data/transactional-outbox.html
