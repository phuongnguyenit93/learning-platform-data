# Retrying Every Exception Without Considering Transience and Duplicate Side Effects

**Retry** is a recovery mechanism when an operation may fail temporarily. However, handling errors with a pattern like `catch (Exception e) { retry(); }` can turn a minor error into a much more severe one: retrying inputs that are always invalid, duplicating payments or emails, overwhelming an already overloaded system, masking programming bugs, and causing a workflow to never terminate. An exception **does not prove by itself** that a failure is transient, and the caller not receiving a response **does not prove** that the operation has not produced any side effects.

To decide whether to retry properly in Java, three independent questions must be answered:

1. **Is the error recoverable over time?** Is there reason to believe that a subsequent attempt can succeed without changing the input or business state?
2. **Is retrying safe with respect to duplicate side effects?** If the first attempt already executed part or all of the side effect, will a new attempt create duplicate data, charge money a second time, or send multiple notifications?
3. **What are the limits and cancellation rules?** Are there a clear deadline, attempt limit, backoff, jitter, retry budget, and interruption/cancellation signals?

The answers to these three questions determine the retry policy; **not just the `Exception` class name**. This article belongs to the *Common Pitfalls* section of Java Core – Exception, focusing on error classification, idempotency, and designing controlled retries in Java 17+.

## 1. Why `catch (Exception)` Followed by Unconditional Retry Is Wrong

The following illustrative code demonstrates this anti-pattern:

```java
while (true) {
    try {
        sendPayment();
        break;
    } catch (Exception error) {
        // Wrong: no error classification, no attempt limit,
        // no check for duplicate side effects, no respect for interruption.
    }
}
```

This is a **dangerous illustration**, not a standalone program; `sendPayment()` is defined by the application. It can cause:

- **Infinite loop:** if the amount is negative or the token is invalid, calling again with the same data will not make the error disappear.
- **Duplicate side effects:** if the server already recorded the transaction but the response was lost, retrying can record the transaction a second time.
- **Retry storm:** when a dependency is overloaded, all callers retrying rapidly at the same time make the dependency even more overloaded.
- **Masking bugs:** `NullPointerException`, `ClassCastException`, or invariant violations may be mistaken for network errors.
- **Lost interruption signals:** if caught broadly and `InterruptedException` is not handled properly, shutdown may be delayed.
- **Increased latency:** a request continues waiting across multiple attempts until it exceeds the caller's deadline.
- **Poor observability:** logs only appear on the last attempt, or every attempt prints a full stack trace causing a log storm; the original cause is obscured.
- **Resource leaks:** each attempt opens a connection/stream and fails without proper cleanup by its owner.

An error being **catchable** does not mean the catching code understands enough to **recover** from it. The retry layer should understand the operation type, error source, and consistency constraints.

## 2. Classify by Recoverability, Not by Checked/Unchecked

Java distinguishes checked and unchecked exceptions at compile time; however, **checked does not mean transient**, just as unchecked does not necessarily mean permanent.

| Situation type | Example | Is retrying immediately with the same input reasonable? |
| --- | --- | --- |
| **Transient** — may change over time | Connection to a service temporarily interrupted, server temporarily overloaded, short-lived resource contention | Possibly, if the operation is safe to repeat and the policy includes backoff. |
| **Permanent / deterministic** | Missing required field, malformed data, fixed rule violation, access denied | Usually no; input/permissions/configuration must be fixed. |
| **Ambiguous outcome** | Server may have processed the request but response/ack was lost, client timed out after sending request | Safe to retry only with idempotency/deduplication or a state reconciliation mechanism. |
| **Cancellation/interruption** | Caller interrupted while waiting, task canceled | Should not fight a stop request with automatic retries. |
| **Programming bug** | `NullPointerException` due to broken invariant, cast error, index access bug | No; fix the code, preserve the stack trace, and alert appropriately. |
| **Resource exhaustion** | Pool exhausted, out-of-memory error, disk full | Depends on the resource and policy; aggressive retrying usually makes it worse. |

An `IOException` could be a fleeting connection drop, or it could be a non-existent path, permission denied, or invalid data that cannot be fixed by retrying. A `SQLException` could indicate a retryable deadlock or a unique constraint violation that will fail repeatedly. **Do not retry all `IOException` or `SQLException` instances just because they are checked exceptions.**

Conversely, an unchecked application-domain exception, such as `TemporaryCapacityException extends RuntimeException`, can represent an explicitly declared transient error. What matters is the **API contract of the error**, not a single inheritance branch.

## 3. What Is a Transient Failure?

A *transient* failure is a situation where there is reason to believe the state causing the error **may change**, giving a retry a probability of succeeding. Examples:

- A downstream service returns a temporary overload signal and asks to retry later.
- A connection is reset before sending the request in a safe read operation, provided it is known that the request has not been processed by the server.
- A deadlock/serialization conflict whose contract allows repeating **the entire transaction**, not just an isolated statement.
- A resource updated by another service may become available after a period of time.

However, "transient" does not mean "retry immediately and infinitely":

1. The dependency may still be failing — backoff is needed.
2. Multiple callers may retry simultaneously — jitter and load limiting are needed.
3. The request's deadline may have already expired — further retries are no longer useful.
4. Side effects may have already occurred before the exception surfaced — safety under repetition must be determined.
5. Increasing retries means increasing total attempts, which does not always improve availability.

A timeout also **does not prove transience by itself**: it only states that a wait operation or call did not complete within the time budget. The remote outcome may be in progress, committed, or failed. The retry policy must also consider the **degree of outcome uncertainty**.

## 4. Permanent Failure: Retrying Does Not Change the Failure Condition

Some errors can only be fixed by changing data, permissions, or the program:

- `IllegalArgumentException` due to a negative quantity.
- Payload schema/validation errors where retries still send the exact same bytes.
- Expired token or insufficient permissions; may require re-issuing a token through a **separate workflow**, not endlessly repeating the same request.
- Database unique constraint violated with unchanged data.
- Non-existent endpoint or configuration according to the contract.
- Programming errors such as an invalid `null` dereference.

If the caller retries the exact same request verbatim after one of these errors, the result will likely just repeat the error, waste CPU/network, and pollute metrics. You should **fail fast with actionable information**: fix the input, request permissions, update configuration, or fix the code.

Sometimes an HTTP status like `404` may be temporary in an eventually consistent system, while permanent in another API. Similarly, `409 Conflict` may be a version conflict resolved by **re-reading and recomputing**; retrying the exact old payload may not help. Do not label entire status codes as transient/permanent without a contract.

## 5. Ambiguous Outcome: The Most Dangerous Error for Operations with Side Effects

Suppose a client sends a command to "deduct 100,000 VND":

```text
Client                           Server
   |                               |
   |---- POST /payments ---------->|
   |                               | Record transaction successfully
   |                               | Commit data
   |<---- response lost -----------X
   |
   +-- client timeout
   +-- retry POST /payments ------> ?
```

If the system only looks at `SocketTimeoutException` and retries, the server might process **two transactions**. A timeout is a transport/observation error; it does not confirm that the request never reached the server. This is an **ambiguous outcome** scenario.

Safer design approaches:

- **Idempotency key:** the caller provides a stable identifier for **the same logical operation** across attempts. The server remembers the result for that key and returns the previous result instead of performing the side effect again.
- **Deduplication based on business key:** order number, transaction ID, unique operation ID; enforced via transactions/unique constraints.
- **Reconciliation/status query:** check whether the ID has already been processed before deciding to resend.
- **Transactional outbox/inbox:** record business state and events transactionally, then handle duplicate deliveries with an idempotent consumer.
- **Compensation:** may be needed when systems lack cross-service atomic transactions; compensating actions do not replace preventing duplicate side effects.

**Never generate a new idempotency key on each attempt of the same operation**: doing so turns the attempts into independent logical commands in the eyes of the server. The same operation must use **the same key and matching payload**. A genuinely different business request must use a different key.

An idempotency key is not "just having a UUID string". The server must validate the key **along with the payload/client identity**, persist the state/result durably, handle concurrent contention, define a retention period, and prevent key reuse with a different payload.

## 6. Safety Under Repetition: Reads, Writes, and Idempotency

**Idempotent** means repeating the same operation multiple times has the same **intended effect on state** as executing it once (according to the observable contract). It does not necessarily mean the execution count is one or every response byte is identical.

Examples:

| Operation | Retryability | Points to check |
| --- | --- | --- |
| Reading data without side effects | Usually safer | Cache, snapshot, timeout, read and download semantics. |
| Setting `status = ACTIVE` | May be idempotent in state | Audit logs/emails emitted each time may still be duplicate side effects. |
| Incrementing `counter = counter + 1` | **Not idempotent** without dedup | Repetition produces an incorrect total. |
| `POST` creating a payment | Not inherently safe | Requires idempotency key/dedup or reconciliation. |
| `PUT` replacing resource state | Usually designed to be idempotent in HTTP semantics | Business hooks, versions, side effects, and conditional requests must still be checked. |
| `DELETE` by identifier | May be idempotent in final state | Second response may differ; audit/notifications may also repeat. |
| Sending email/webhook | Not inherently idempotent | Requires message ID, downstream dedup, or accepting at-least-once and handling duplicates. |

Do not assume HTTP `GET` is always safe regardless of an implementation violating semantics, or that HTTP `POST` can never be retried. The endpoint's contract and server-side deduplication decide.

Operations with *at-least-once delivery* can often receive the same event multiple times. The consumer must be idempotent if the goal is correct state across duplicate events. The term "exactly once" in distributed systems must be understood within **specific guarantee boundaries**, not as a blanket promise that retries or duplicate processing never happen at any layer.

## 7. Java 17 Example: Retry Only Transient Errors

This example clearly separates retryable errors from input errors that should not be retried. To keep stdout deterministic, the program uses an attempt counter and **does not sleep/backoff**; delays are a production mechanism that must be added, not proof of a complete production policy.

Create `SelectiveRetryDemo.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

public class SelectiveRetryDemo {

    private static final class TemporaryFailureException
            extends RuntimeException {
        TemporaryFailureException(String message) {
            super(message);
        }
    }

    private static <T> T retryTransient(
            String label, Supplier<T> action, int maxAttempts) {
        if (maxAttempts < 1) {
            throw new IllegalArgumentException("maxAttempts must be positive");
        }

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                T value = action.get();
                System.out.println(label + " attempt " + attempt + ": SUCCESS");
                return value;
            } catch (TemporaryFailureException ex) {
                System.out.println(label + " attempt " + attempt + ": TRANSIENT");
                if (attempt == maxAttempts) {
                    throw ex;
                }
            } catch (IllegalArgumentException ex) {
                System.out.println(label + " attempt " + attempt + ": PERMANENT");
                throw ex;
            }
        }

        throw new AssertionError("unreachable");
    }

    public static void main(String[] args) {
        AtomicInteger readCalls = new AtomicInteger();

        String read = retryTransient("read", () -> {
            int number = readCalls.incrementAndGet();
            if (number <= 2) {
                throw new TemporaryFailureException("temporarily offline");
            }
            return "DATA";
        }, 3);
        System.out.println("read result: " + read);

        try {
            retryTransient("validate", () -> {
                throw new IllegalArgumentException("invalid input");
            }, 3);
        } catch (IllegalArgumentException ex) {
            System.out.println("validate stopped");
        }

        try {
            retryTransient("offline", () -> {
                throw new TemporaryFailureException("still offline");
            }, 2);
        } catch (TemporaryFailureException ex) {
            System.out.println("offline stopped");
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 SelectiveRetryDemo.java
java SelectiveRetryDemo
```

Stdout:

```text
read attempt 1: TRANSIENT
read attempt 2: TRANSIENT
read attempt 3: SUCCESS
read result: DATA
validate attempt 1: PERMANENT
validate stopped
offline attempt 1: TRANSIENT
offline attempt 2: TRANSIENT
offline stopped
```

Key takeaways:

1. `TemporaryFailureException` in the example is a **domain error type with a contract allowing retries**; the `RuntimeException`/checked class hierarchy does not decide on its own.
2. `read` fails twice and succeeds on the third attempt; the entire operation is allowed 3 attempts, **not 3 additional retries**.
3. `validate` receives a permanent error and stops immediately on the first attempt, without looping three times.
4. `offline` has a limit of 2 attempts and propagates the final exception outward; the outer callback decides whether to return an error or monitor it.
5. `Supplier.get()` can throw unchecked exceptions. The demo does not catch general `Exception`; errors other than the explicitly known types propagate out, avoiding masking bugs.
6. The demo has no I/O, no side effects, and does not implement delays, deadlines, jitter, circuit breakers, or interruption. In a real application, use it only as an **illustration of classification and limits**, not copied verbatim as a production retry framework.

For an operation that can mutate state, **verify repetition safety before calling `retryTransient`**. A temporary-type exception does not make a write operation idempotent.

## 8. Java 17 Example: Idempotency Key Prevents Duplicate Side Effects

This example simulates a scenario where the server commits and then the client fails to receive the response. The client calls again using the **same operation ID** and the server returns the recorded result instead of incrementing the counter again.

Create `IdempotencyKeyDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;

public class IdempotencyKeyDemo {

    private static final class OutcomeUnknownException
            extends RuntimeException {
        OutcomeUnknownException(String message) {
            super(message);
        }
    }

    private static final class PaymentService {
        private final Map<String, Integer> committed = new HashMap<>();
        private int charges;

        int charge(String operationId, int amount, boolean loseResponse) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }

            Integer previous = committed.get(operationId);
            if (previous != null) {
                if (previous != amount) {
                    throw new IllegalArgumentException(
                            "same key with different amount");
                }
                return previous;
            }

            charges++;
            committed.put(operationId, amount);

            if (loseResponse) {
                throw new OutcomeUnknownException("response lost after commit");
            }
            return amount;
        }

        int chargeCount() {
            return charges;
        }
    }

    public static void main(String[] args) {
        PaymentService service = new PaymentService();

        try {
            service.charge("order-42", 50, true);
        } catch (OutcomeUnknownException ex) {
            System.out.println("client: outcome unknown");
        }

        int result = service.charge("order-42", 50, false);
        System.out.println("retry result: " + result);
        System.out.println("charges: " + service.chargeCount());

        try {
            service.charge("order-42", 75, false);
        } catch (IllegalArgumentException ex) {
            System.out.println("key conflict: rejected");
        }

        service.charge("order-43", 50, false);
        System.out.println("charges after new order: " + service.chargeCount());
    }
}
```

Run with Java 17+:

```bash
javac -encoding UTF-8 IdempotencyKeyDemo.java
java IdempotencyKeyDemo
```

Output:

```text
client: outcome unknown
retry result: 50
charges: 1
key conflict: rejected
charges after new order: 2
```

Explanation:

- The first call for `order-42` executes `charges++` and stores the result, **then** simulates a lost response with `OutcomeUnknownException`.
- Retrying with the **same key `order-42` and amount 50** detects the existing result and returns `50` without incrementing the charge count.
- The same key with a different amount is rejected; this protects against reusing a key with a mismatched payload.
- A new operation with `order-43` increments the counter to 2, which is correct because it is a different request.
- **This is only a single-threaded, in-memory model.** `HashMap`/counter is not thread-safe, is not protected by durable transactions, and will lose data on restart. Production must guarantee atomic dedup when multiple requests with the same key arrive concurrently, scope keys by tenant/context, persist state/results with an expiration policy, and synchronize with the business commit.
- The example also assumes "charge" and writing `committed` happen as one logical step; with a real DB/payment provider, both actions must be coordinated via transactions, unique constraints, or the provider's idempotency API, not merely by adding a `HashMap` on the client.

**A post-commit timeout cannot be safely resolved just by retrying the same payload** if the server lacks an idempotency/dedup contract. This example illustrates the exact additional guarantee the server must provide.

## 9. Idempotency Is Not Just Handling Duplicates After Harm Is Done

In a multi-threaded server, a non-atomic check-then-write pattern is a bug:

```java
if (!processedIds.contains(id)) {
    performSideEffect();
    processedIds.add(id);
}
```

This is an anti-pattern illustration snippet. Two concurrent requests can both see that the ID does not exist yet and **both execute the side effect**, before either manages to add the ID.

Design according to each case:

- **Unique constraint + transaction:** store the operation key and update business state in the same transaction to prevent duplicates at the DB level.
- **Per-key lock/coordinator:** prevent concurrent execution of the same operation; must handle crashes/restarts and multi-node distribution.
- **Clear `IN_PROGRESS`/`COMPLETED`/`FAILED` states:** prevent another request from replaying while the first attempt has not finished.
- **Store response or resource ID:** enables returning a consistent result for duplicates.
- **Payload mismatch rules:** reject the same key with different input rather than treating it as the same operation.
- **Retention/expiration:** if a key expires while the caller still retries, the risk of re-execution must be documented.
- **Tenant isolation:** key `order-42` from two different customers must not collide if they are independent operations.

In a message queue, the consumer should handle duplicate deliveries using the message/operation ID. Retry and dedup are two halves of the design; missing one can make a system work on the healthy path but fail during failures.

## 10. Backoff: Do Not Retry Aggressively

Even with transient errors and idempotent operations, retrying immediately after every exception can create a **retry storm**. Gradually increasing backoff gives the dependency time to recover.

A simple approach is capped exponential backoff:

\[
d_k = \min(d_{\max},\, d_0 \times 2^{k-1})
\]

Where `d_0` is the initial delay, `d_{\max}` is the cap, and `k` is the **retry number after a failed attempt**, starting at 1. For example, `d_0 = 100 ms`, cap `500 ms`:

| Retry # | Delay without jitter |
| --- | ---: |
| 1 | 100 ms |
| 2 | 200 ms |
| 3 | 400 ms |
| 4 | 500 ms (capped) |
| 5 onward | 500 ms (capped) |

Do not compute the delay using unchecked multiplication when the attempt count is large, as integer overflow can occur. Production code should use bounded functions, `long` types, and appropriate time constraints.

### Jitter to Prevent Retry Synchronization

If thousands of clients fail at the same time and all wait exactly 100 ms, after 100 ms they will all hit the server simultaneously again. **Jitter** adds randomness to the delay so attempts are spread out.

One strategy is *full jitter*, where the delay is chosen randomly in `[0, cappedDelay]`. There is no single jitter formula optimal for all systems; the main requirement is a reasonable distribution, staying within the deadline, and being monitored.

**Illustrative** snippet, not standalone:

```java
long cappedDelayMillis = Math.min(maxDelayMillis, exponentialMillis);
long actualDelayMillis =
        ThreadLocalRandom.current().nextLong(cappedDelayMillis + 1);
Thread.sleep(actualDelayMillis);
```

This assumes `maxDelayMillis` and `exponentialMillis` are valid and non-negative, `cappedDelayMillis + 1` does not overflow, and `java.util.concurrent.ThreadLocalRandom` is imported. `Thread.sleep` can throw `InterruptedException`; do not swallow interruption just to finish a retry. In event-loop/async systems, prefer a scheduler instead of blocking worker threads with `Thread.sleep`.

Server guidance such as HTTP `Retry-After` should take precedence when present and supported by a trusted API; still apply deadlines, caps, and repetition safety checks. Do not ignore retry hints and invent a conflicting backoff against the contract.

## 11. Java 17 Example: Computing a Backoff Schedule Without Real Waiting

To demonstrate a capped delay without depending on timing/scheduling, this program only **computes and prints the schedule**, without calling sleep or network I/O.

Create `BackoffScheduleDemo.java`:

```java
public class BackoffScheduleDemo {

    static long cappedExponentialMillis(
            int retryNumber, long baseMillis, long maxMillis) {
        if (retryNumber < 1 || baseMillis < 0 || maxMillis < 0) {
            throw new IllegalArgumentException("invalid retry config");
        }

        long delay = Math.min(baseMillis, maxMillis);

        for (int i = 1; i < retryNumber; i++) {
            if (delay >= maxMillis) {
                break;
            }
            delay = delay > maxMillis / 2
                    ? maxMillis
                    : Math.min(maxMillis, delay * 2);
        }
        return delay;
    }

    public static void main(String[] args) {
        for (int retry = 1; retry <= 5; retry++) {
            System.out.println(
                "retry " + retry + ": "
                    + cappedExponentialMillis(retry, 100, 500) + " ms");
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 BackoffScheduleDemo.java
java BackoffScheduleDemo
```

Stdout:

```text
retry 1: 100 ms
retry 2: 200 ms
retry 3: 400 ms
retry 4: 500 ms
retry 5: 500 ms
```

This function does not implement jitter, a full retry policy, or a scheduler; it only demonstrates the capped delay rule with sample inputs. In production, add a condition not to sleep past the **remaining deadline**, measure elapsed time using an appropriate time source, and check for cancellation.

## 12. Retry Limit, Retry Budget, and Deadline

Do not limit only `maxAttempts`. A practical retry policy usually needs **all three types of limits**:

**1. Attempt limit:** the total number of calls (including the first one) does not exceed the allowed limit. `maxAttempts=3` means the initial call + at most two retries, not three additional retries.

**2. Overall deadline:** only continue if there is enough time left to attempt and return the result to the caller. If a request has 50 ms remaining but the minimum backoff is 200 ms, retrying is useless or violates the deadline.

**3. System-wide retry budget:** limits the number of retries generated relative to successful/overall traffic to avoid amplifying load on dependencies. A service with thousands of requests each retrying 3 times can nearly quadruple call volume during an outage; additional limits per host/tenant/operation or a global retry budget are needed.

Conceptual example:

```text
Request budget: 2.0 s
Attempt 1: 350 ms → transient failure
Backoff:   100 ms
Attempt 2: 400 ms → transient failure
Backoff:   200 ms
Remaining: 950 ms (before other overhead)
Attempt 3: only start if estimated timeout + response processing
           still fits within the remaining deadline
```

The timings in this example are illustrative assumptions, not measurements. The policy can use a per-attempt timeout ≤ remaining deadline and **disallow retry** if calling again is no longer beneficial.

Do not rely solely on `Thread.sleep` to enforce a deadline: it only delays the thread. Deadlines must be propagated/checked at the appropriate network/DB call layers or workflow boundaries.

## 13. Interruption and Cancellation: Retries Must Not Fight Shutdown

`InterruptedException` usually represents a request to stop a waiting operation. If retry code swallows this exception and continues to `sleep`/call the network, it can prevent shutdown from completing.

Example to avoid:

```java
for (;;) {
    try {
        doBlockingCall();
        break;
    } catch (InterruptedException ignored) {
        // Wrong: ignores the interrupt signal and retries forever.
    }
}
```

This is an illustrative snippet, with `doBlockingCall` assumed. For APIs that can declare `throws InterruptedException`, it is usually best to propagate it up to a caller with sufficient authority to decide. If it must be wrapped into another exception, you usually need to **restore the interrupt flag**:

```java
try {
    doBlockingCall();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new OperationCancelledException("operation interrupted", ex);
}
```

`OperationCancelledException` is an illustrative type, not defined in this standalone snippet. The core point is never to treat interruption as a transient failure to be retried.

A `Future.get(timeout)` throwing `TimeoutException` only indicates **the caller timed out waiting**; the task may still be running. `Future.cancel(true)` may request interrupting the worker depending on the implementation, but does not guarantee the worker has stopped or cleanup has completed. If retrying a new task while the old task can still produce side effects, idempotency/cancellation acknowledgement or reconciliation is required.

With `CompletableFuture`, `orTimeout` can complete the future exceptionally, **but does not guarantee background work is stopped**. `exceptionally(error -> retry().join())` can block the callback thread and lose deadline control; prefer async composition and a bounded scheduler when needed.

## 14. Classifying IOException, HTTP, Database, and Business Errors

Do not write a policy like:

```java
catch (IOException | RuntimeException ex) {
    // Retry everything.
}
```

This is an anti-pattern illustration snippet. A good policy relies on the **dependency's contract** and operation characteristics:

### HTTP/network

| Signal | Possible handling | Additional conditions |
| --- | --- | --- |
| HTTP 429 / rate limit signal | Retry after the server-specified interval when appropriate | `Retry-After`, quota, deadline, concurrency limit, idempotency. |
| HTTP 503 / server unavailable | May be transient | Backoff, jitter, avoid retry storm; writes must be idempotent/deduped. |
| HTTP 500 | May be transient or a server-side bug | Do not blindly retry POSTs with side effects; check the API contract. |
| HTTP 400 validation | Usually permanent for the same payload | Fix the request; do not automatically retry verbatim. |
| HTTP 401/403 | Usually requires separate authentication/authorization handling | Refresh token only if policy allows; do not loop infinitely. |
| HTTP 404 | May be permanent or temporary under eventual consistency | Depends on resource workflow and contract. |
| HTTP 409 | May be a conflict requiring re-reading state | Retrying verbatim may not help; needs an optimistic concurrency policy. |
| Connection lost / read timeout | Outcome may be unknown | Check whether the request may have been processed, idempotency key, or reconciliation. |

Do not use the `SocketTimeoutException` name alone to conclude it is safe to retry: a connect timeout differs from a read timeout waiting for a response after the server has already received the request. Data transmission conditions and remote semantics decide.

### SQL/database

- **Deadlock/serialization conflict:** many databases allow retrying the entire transaction after rollback based on the appropriate error type/SQLState. Ensure the old transaction has rolled back and any non-DB side effects are not erroneously duplicated.
- **Unique constraint violation:** for the same data, usually permanent; if using a unique key for dedup, it may be a signal to query the operation result again, **not** blindly retry the insert.
- **Connection failure:** may be transient, but the transaction outcome is sometimes unknown if the connection drops near commit time. Requires recovery/transaction ID design.
- **Syntax error/schema mismatch:** usually requires code/migration fixes; infinite retries are useless.
- **Lock timeout:** may be retried with limits, but requires understanding transaction isolation, deadlock policy, and impact on concurrent load.

JDBC provides exception subtypes like `SQLTransientException` and `SQLNonTransientException` to hint at retryability. Even so, the driver vendor and specific operation still matter; **do not treat a subclass as an unconditional license to retry**, especially if data has already committed or the operation involves multiple side effects.

### Business logic

An `InsufficientBalanceException` cannot be resolved by retrying a few milliseconds later on the same account, whereas a `TemporaryInventoryLockException` may be retried after contention subsides. Design business error types/codes according to their meaning; do not decide retries by catching every `RuntimeException`.

## 15. Do Not Retry Programming Bugs or Severe Resource Errors

`NullPointerException`, `ClassCastException`, `AssertionError`, and `OutOfMemoryError` are usually not appropriate signals to retry the same code/path. Attempting to retry can cause:

- Repeating the bug continuously.
- Creating more allocations during memory exhaustion.
- Losing diagnostic ability due to a log storm.
- Leaving resources/locking mechanisms in an undefined state.
- Making health checks report healthy even though a core component is broken.

Do not catch `Throwable` to retry. `Throwable` includes `Error`; many errors indicate severe runtime states and are not designed as business recovery signals.

Errors caused by `InterruptedException` belong to the cancellation channel; return decision authority to the lifecycle owner. A `CancellationException` from `Future` is also usually a cancellation state that should be preserved rather than turned into a "temporary error" to re-run.

If a real bug is discovered, fix the code and tests; do not add `catch(RuntimeException)` to make the symptom disappear.

## 16. Every Attempt Must Clean Up Resources by Its Proper Owner

If an attempt opens a stream/connection/subscription and throws an exception, retrying will open more resources. Failing to clean up the previous attempt can accelerate leaks with every loop iteration.

Illustrative structure:

```java
for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try (ConnectionHandle owned = acquireConnection()) {
        return performOperation(owned);
    } catch (TransientConnectionException ex) {
        if (attempt == maxAttempts) {
            throw ex;
        }
        // Only retry if the operation is safe to repeat.
    }
}
throw new AssertionError("unreachable");
```

This is an **illustrative** snippet, where `ConnectionHandle` implements `AutoCloseable` and the remaining symbols are defined in the application. `try-with-resources` closes each attempt's handle **before** deciding to retry. Do not close a shared pool if the connection was borrowed; only release/close the handle according to the pool contract.

If `close()` also throws, preserve primary/suppressed exception information. If retrying immediately after a cleanup error could leave state undefined, classify the cleanup error and repetition safety rather than simply treating it as transient.

In multi-step systems, clearly define the **retry boundary**: retry the whole transaction or just the statement? Has a partial commit occurred? If an operation writes to a DB and then sends an email, retrying the whole operation could send duplicate emails even if the DB rolled back, or vice versa.

## 17. Multi-Layer Retries Amplify Load

Suppose a request passes through three services A → B → C. If each layer independently retries up to 3 attempts, in the worst case, a single external request can generate up to:

\[
3 \times 3 \times 3 = 27
\]

calls to the deepest operation, if each layer retries when downstream reports an error. This is an **illustrative bound** in a three-tier structure, not a mandatory number for every architecture.

When a dependency is failing, multiplicative retries can worsen the incident. Ways to mitigate this:

- Designate a **retry-owning layer** at the appropriate boundary, avoiding blind retries in every library/adapter.
- Propagate the overall deadline and **retry budget** across layers.
- Use circuit breakers/rate limiting/bulkheads when needed, with verifiable policies.
- Limit concurrency and queue depth.
- Respect server `Retry-After`/backpressure.
- Collect metrics per attempt, request, and dependency; do not count only failed requests.

A circuit breaker is not a magic fix for business logic; it mainly helps shed load to a failing dependency to limit damage. When a breaker is open, callers should receive a clear error/response rather than creating another loop to bypass the breaker.

## 18. Retry, Fallback, and the "Unknown" State

These three responses are distinct:

**Retry:** re-invokes the task, potentially increasing side effects; safe only when conditions are met.

**Fallback:** returns a backup result with a clear contract, such as an empty recommendation list when the recommendation service is unavailable. Fallback does not mean the original operation succeeded.

**Unknown/pending:** the final outcome of an operation with side effects has not yet been verified. It may be necessary to return an operation ID so the client can query status, rather than falsely reporting success or failure.

For example, a payment API should distinguish:

```text
SUCCESS     — transaction confirmed
FAILED      — transaction known to have failed
PENDING     — processing / no final result yet
UNKNOWN     — unsure whether remote committed; reconciliation needed
```

These are **illustrative** states; actual names and contracts belong to the application system. Blindly retrying can turn UNKNOWN into two successful charges, while a fake `SUCCESS` fallback can corrupt data.

For read-only operations, a cache fallback can make clear sense if the data is still valid. For writes with critical impact, avoid "recovering with a default value" that hides an unconfirmed outcome.

## 19. Asynchronous Retries and CompletableFuture

When using `CompletableFuture`, errors can be stored in a stage as an exceptional completion. A chain like:

```java
serviceCall()
    .exceptionally(error -> serviceCall().join());
```

is an **anti-pattern illustration snippet**: `serviceCall()` is assumed to return `CompletableFuture<T>`. The `exceptionally` lambda may execute on the completion thread, calling blocking `join()` and causing contention/deadlock if the executor runs out of threads. It also lacks error classification, attempt limits, and can duplicate side effects.

For falling back to another async source, Java 17 provides `exceptionallyCompose` to chain stages without blocking via `join()`. However, `exceptionallyCompose` **is not a retry framework by itself**: if used to re-invoke an operation, it still needs error classification, attempt limits, deadlines, a jitter/backoff scheduler, cancellation, and idempotency.

A practical way to structure this is to let the component owning the workflow manage a retry state machine (attempt count, last failure, remaining deadline), create a new attempt when permitted, and complete an overall `CompletableFuture` upon success/final failure/cancellation. Use a scheduled executor with a clear lifecycle rather than blocking `Thread.sleep` inside callbacks.

When a caller of `Future.get(timeout)` hits `TimeoutException`, only **that wait** has expired; the background stage/task may still be running. Do not start a new attempt with side effects without resolving cancellation authority, result tracking, and idempotency.

## 20. Proper Logging and Observability for Retries

If every failed attempt prints a full stack trace and then the outer layer logs again when attempts are exhausted, a single request can produce dozens of records for the same root cause. During a widespread dependency outage, this can cause a log storm and slow down the system.

What should be recorded:

| Metric/attribute | Purpose |
| --- | --- |
| Safe `operation_id` / idempotency key | Correlate attempts of the same operation for reconciliation. |
| `attempt_number` and `max_attempts` | Distinguish the initial call from retries. |
| `retry_reason` / error code | Understand why the policy allowed a retry. |
| `retry_outcome` | Succeeded after retry, exhausted, permanent, canceled, deadline exceeded. |
| Backoff delay | Analyze latency and retry synchronization. |
| Retry amplification | Attempts per request, per downstream. |
| Pending/unknown outcomes | Track operations needing reconciliation. |
| Circuit state and queue saturation | Identify whether the system is being protected or overloaded. |

The retry layer can record a metric for **every attempt**, while full stack traces should usually be logged selectively per policy at a boundary with context, not necessarily once for every attempt. When sampling logs, metrics counting all errors are still needed so incidents are not underestimated.

Do not use full exception messages, URLs containing tokens, payment payloads, or personal IDs as metric labels/log keys; choose error codes and protected correlation fields.

When a final attempt fails, preserve the `cause` and sufficient attempt context for investigation. Do not wrap every error into `RuntimeException("retry failed")` and discard the root cause.

## 21. Consistency of Retries with Transactions

Suppose a transaction does two things: writes an order and publishes an "order created" event. If the DB write succeeds but publishing the event fails, retrying the entire flow could create duplicate orders or publish multiple events.

Options depending on architecture:

- **Properly scoped DB transaction:** for deadlocks, you can roll back and retry *the entire transaction*. You must know what work is inside the transaction.
- **Transactional outbox:** write business state and the outbox event in the same transaction; the event-publishing worker can retry sending, and the consumer uses dedup.
- **Optimistic concurrency:** each conflict may require reading the new version, recomputing the decision, and writing; retrying the exact old payload may keep failing.
- **Idempotency token:** the server knows the same operation ID has already been processed and returns a stable result.
- **SAGA/compensation:** if multiple systems cannot share a transaction, a workflow orchestrates state and compensates when needed; retrying a single action carries its own risks.

Do not design retries first and then ask "are there side effects?" afterward. **Business and transactional properties determine the retry policy**, not the other way around.

## 22. Cases That Are Retryable but Should Not Be Automatically Retried Immediately

There are situations where an error is recoverable, yet automatic retrying is still inappropriate:

- A payment transaction has an unknown outcome and no idempotency key.
- A rate-limit error requires waiting 60 seconds, but the caller's deadline only has 2 seconds left.
- A service is under maintenance with a retry hint longer than the request budget.
- The caller has canceled the request or the service is shutting down.
- The dependency shows signs of overload and the retry budget is exhausted.
- The operation has non-compensable side effects or violates uniqueness when repeated.
- An error can be resolved by asking the user to confirm a data change; automatic retries cannot do that.
- An attempt has already exceeded the entire workflow's deadline and the old work may still be running.

In these cases, the right action may be **returning a pending status**, **enqueuing a job into a durable queue**, **requesting reconciliation**, **alerting operations**, or **stopping with a meaningful error**, rather than firing another request immediately.

## 23. Testing Retry Policies by Scenario

A good test suite must verify both: **when retries are allowed** and **when retries are strictly forbidden**.

| Scenario | Expectation |
| --- | --- |
| Transient fails twice then succeeds | Total of 3 attempts, one successful result, no further retries. |
| Permanent validation failure | Only 1 attempt, clear error propagated. |
| Transient keeps failing until limit | Exactly `maxAttempts`, then returns final failure. |
| Deadline expires before next attempt | No further calls, reports deadline exhausted. |
| Capped backoff | Delay does not exceed cap and does not exceed remaining deadline. |
| 1000 callers hit transient failure concurrently | Jitter/limits prevent simultaneous retries; measure attempt count and queue depth. |
| Caller/worker interrupted | Terminates per cancellation policy, restores/propagates interrupt when appropriate. |
| Server commits but response is lost | Retry with the same idempotency key creates no additional side effect. |
| Two concurrent retries with same key | Server does not execute side effect twice; duplicate receives correct result or status. |
| Same key with different payload | Rejected/handled per contract, not silently treated as a valid duplicate. |
| Idempotency key retention expires | Clear contract regarding risk and retry window. |
| Database deadlock | Retries at the proper transaction boundary after rollback, without duplicating external side effects. |
| Retry runs out of resources | Each attempt cleans up acquired resources, no connection/permit leaks. |
| Unclassified exception | Fails/propagates, does not automatically retry arbitrary `RuntimeException`. |
| Retry logs/metrics | Tracks total attempts and outcomes without stack trace spam or data leaks. |

When testing concurrency/idempotency, use a latch/barrier to force two requests with the same key to run simultaneously; do not only run sequentially and conclude the server is race-safe.

When testing backoff, it is better to **inject a clock/scheduler** or compute pure delays for deterministic tests; do not rely on `Thread.sleep(100)` and CI wall-clock time. For real I/O, use fake adapters for pre-send failures, post-commit failures, and lost responses to verify outcomes.

## 24. Common Anti-Patterns

**Retrying every `Exception` or `Throwable`.** Wrong because permanent errors, cancellations, bugs, and resource exhaustion have different meanings. Classify by contract, not by arbitrary broad catches.

**Retrying every HTTP 5xx or `IOException` for write operations.** Insufficient: the request may have already committed and the response may have been lost. Idempotency/dedup or reconciliation is required.

**Retrying the same payload on validation failure.** Does not change the root cause; fix the input.

**Retrying immediately with no delay.** Can overload the dependency further and synchronize clients.

**Using backoff without maxAttempts/deadline.** Can prolong the workflow indefinitely and hold onto resources.

**Uncoordinated retries across multiple layers.** Load can multiply by the product of attempts at each layer.

**Generating a new idempotency key on every retry.** Turns duplicates into new operations; risks executing side effects multiple times.

**Using a check-then-write `HashMap` in a multi-threaded server as if it were exactly-once.** Suffers from races/crashes/restarts; needs atomic/durable dedup per operation.

**Treating a timeout as a guaranteed server failure.** A timeout may only indicate loss of observability of the outcome.

**Swallowing `InterruptedException` to keep retrying.** Fights shutdown/cancellation; can hang the service.

**Using `CompletableFuture.exceptionally(...join())` for "async retry".** Can block callback threads and lacks a complete policy.

**Logging full stack traces on every attempt.** Causes a log storm, increases CPU/I/O, and degrades observability.

**Not cleaning up after a failed attempt.** Each retry multiplies resource leaks.

**Checking only the final result without checking the attempt count.** A "eventually succeeds" test can hide retrying 1000 times or sending duplicate emails.

**Confusing retry and fallback.** Fallback is a backup result; it does not prove the original operation succeeded.

## 25. Self-Check Exercises

**Question 1.** An API throws `IllegalArgumentException("quantity must be positive")`. The caller retries 5 times with quantity -2. Is this useful?

**Answer:** No. This is a permanent input error; nothing changes between calls.

**Question 2.** A client sends a money transfer command, the server commits, and then the response is lost. The caller receives `SocketTimeoutException`. Can it retry immediately with a new request?

**Answer:** Not safe yet. The outcome is unknown; a fixed idempotency key for the same operation or a status query/reconciliation is required. Sending a new request without dedup could transfer the money twice.

**Question 3.** A read-only operation encounters `TemporaryServiceUnavailableException`. The caller has 3 seconds left on its deadline, and the server sends `Retry-After: 10` seconds. What should be done?

**Answer:** Do not wait and retry within the 3-second request. Respect the deadline, return an appropriate error/status, or offload to a background workflow with its own ownership if the contract allows.

**Question 4.** Layer A retries 3 attempts, B retries 3, and C retries 3. When everything fails, what is the maximum number of attempts C can receive for a single request to A?

**Answer:** Under a simple nested model, up to `3 × 3 × 3 = 27` attempts at the deepest layer. This is why retry budgets and ownership must be coordinated.

**Question 5.** `Future.get(timeout)` throws `TimeoutException`. Has the background task stopped and rolled back?

**Answer:** Cannot be concluded. This is a timeout of the wait operation; the task may still be running or may have already produced side effects.

**Question 6.** `retryTransient` in `SelectiveRetryDemo` is called with `maxAttempts=3` and the task fails transiently twice before succeeding. How many retries occur *after* the initial call?

**Answer:** Two retries; three attempts in total.

**Question 7.** A server uses `processedIds.contains(id)` followed by `performSideEffect()` and `processedIds.add(id)`. Are two concurrent requests with the same id safe?

**Answer:** No. Both can see that the ID does not exist yet and both execute the side effect. Atomic dedup/transaction/locking per key and deployment environment is required.

**Question 8.** An `InterruptedException` is thrown during `Thread.sleep(backoff)`. Should the retry loop catch it and sleep again until attempts run out?

**Answer:** No. Respect the interrupt signal; propagate `InterruptedException` or restore the flag and terminate according to the lifecycle policy.

## 26. Checklist Before Adding Retries to a Java API

- [ ] Classified transient errors, permanent errors, ambiguous outcomes, cancellations, and bugs.
- [ ] Only retry **errors permitted by the API** and operations safe to repeat.
- [ ] Know whether side effects could have occurred before the failure point, or have idempotency/reconciliation in place.
- [ ] The same operation uses the same idempotency key; the server guarantees atomic dedup and persists state appropriately.
- [ ] Have a clear maxAttempts, distinguishing total attempts from additional retries.
- [ ] Have an overall deadline and per-attempt timeout that does not exceed remaining time.
- [ ] Have bounded backoff, jitter, and respect appropriate retry hints.
- [ ] Have a retry budget and concurrency limit/circuit breaker when dependencies are overloaded.
- [ ] Do not swallow interruption/cancellation; do not retry when the caller has stopped.
- [ ] Each attempt cleans up owned resources and rolls back/compensates at the proper boundary.
- [ ] No uncoordinated multi-layer retries.
- [ ] Record metrics per request and attempt; avoid uselessly double-logging full stack traces.
- [ ] Have tests for permanent errors (single attempt), transient recovery, exhaustion, and timeouts.
- [ ] Have tests for lost responses **after commit**, concurrent duplicates, and key reuse with mismatched payloads.
- [ ] Verified correctness, duplicate side effects, p95/p99 latency, and dependency load during error bursts.

## 27. Conclusion

**Not every exception should be retried.** Temporary errors may deserve a retry, but only when the operation is **safe to repeat**, the caller still has time budget, and the system does not amplify load. Input errors, programming bugs, and cancellation signals usually require stopping immediately; network errors after sending a command with side effects can also mean an **unknown outcome**, not a guaranteed failure.

Proper retrying is a **business and operational policy**: error classification, attempt/deadline limits, backoff with jitter, idempotency or reconciliation guarantees, ownership-based cleanup, and per-attempt observability. Clarifying these conditions before writing a `catch/retry` loop helps a system recover when it should without creating duplicate data, cascading failures, or losing diagnostic visibility.
