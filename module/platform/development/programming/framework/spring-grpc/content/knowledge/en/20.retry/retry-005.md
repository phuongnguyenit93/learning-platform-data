# Retry delay and remaining deadline

## 1. How does retry delay consume the deadline?

In **Spring gRPC**, retry does not create a fresh time budget for each attempt. A logical RPC has **one shared deadline**; the processing time of the initial attempt, the backoff delay between attempts, and subsequent attempts all consume that same budget.

For example, the client calls `GetItem` with a 2-second deadline. The first attempt takes 500 ms and returns `UNAVAILABLE`; the client waits 300 ms for backoff; the second attempt begins with only about 1.2 seconds remaining. If it fails again, the next retry only has whatever time remains from the original deadline.

This means:

- Backoff is not outside the deadline.
- Retrying does not reset the deadline back to its initial value.
- An RPC can stop before exhausting `maxAttempts`.
- If the deadline expires while waiting in backoff or executing an attempt, the call terminates; no new attempt is made on that call.

In gRPC, the deadline is the time limit for the **entire RPC**, whereas `initialBackoff`/`maxBackoff` only adjust when the next attempt starts. Both groups of settings must be designed together.

## 2. Calculating remaining time budget

Let:

- (D): the absolute deadline timestamp of the logical RPC.
- (t): the current timestamp.
- (R(t)): remaining time.
- (d_k): waiting time before the next attempt.
- (a_k): time consumed by the next attempt.

Remaining budget at time (t):

[
R(t) = D - t
]

After waiting for backoff (d_k), the remaining budget is approximately:

[
R_{after_wait} = R(t) - d_k
]

If the next attempt consumes (a_k), the budget left after the attempt is:

[
R_{after_attempt} = R(t) - d_k - a_k
]

This is a planning model. Actual elapsed time also includes jitter, scheduling, network, and server-side processing. The gRPC runtime manages deadlines and retries; the application should not assume an attempt is guaranteed to finish simply because time remained when it started.

### 2.1. Example of a 2-second deadline

Suppose the total deadline is 2,000 ms and the durations below are for illustration only:

| Phase | Time consumed | Remaining budget |
| --- | ---: | ---: |
| Start logical RPC | 0 ms | 2,000 ms |
| Attempt 1 | 450 ms | 1,550 ms |
| Backoff before Attempt 2 | 200 ms | 1,350 ms |
| Attempt 2 | 500 ms | 850 ms |
| Backoff before Attempt 3 | 400 ms | 450 ms |
| Attempt 3 | at most 450 ms remaining | 0 ms when deadline expires |

The client can start Attempt 3, but that attempt only has about 450 ms left before the entire call expires. If the server needs more time, the client still receives a deadline result rather than getting an extra 2 seconds.

Actual backoff can differ from the base value due to jitter or server pushback. Therefore, use the timeline for estimation and test within time bounds rather than treating it as an exact execution schedule.

## 3. Backoff and deadline are two separate limits

A retry policy typically contains the following fields:

| Field | Role | Does it reset the deadline? |
| --- | --- | --- |
| `initialBackoff` | Base waiting interval before the first retry | No |
| `backoffMultiplier` | Increases waiting interval after each eligible error | No |
| `maxBackoff` | Caps the base waiting interval | No |
| `maxAttempts` | Maximum total attempts, including the initial one | No |
| Call deadline | Time limit for the entire logical RPC | Is the shared time limit |

Example policy for the unary method `catalog.v1.CatalogService/GetItem`:

```json
{
  "methodConfig": [
    {
      "name": [
        {
          "service": "catalog.v1.CatalogService",
          "method": "GetItem"
        }
      ],
      "retryPolicy": {
        "maxAttempts": 4,
        "initialBackoff": "0.2s",
        "maxBackoff": "1s",
        "backoffMultiplier": 2,
        "retryableStatusCodes": ["UNAVAILABLE"]
      }
    }
  ]
}
```

The policy permits up to four attempts if every failure is eligible and the call has not committed. However, if the deadline expires after the second attempt, the client cannot make a third or fourth attempt merely because the policy still allows them.

### 3.1. Attaching a deadline to a client call

In gRPC Java, a deadline is set on the stub:

```java
import io.grpc.Deadline;
import java.util.concurrent.TimeUnit;

Deadline deadline = Deadline.after(2, TimeUnit.SECONDS);

CatalogGrpc.CatalogBlockingStub callStub =
        catalogStub.withDeadline(deadline);

long remainingBeforeCall =
        deadline.timeRemaining(TimeUnit.MILLISECONDS);

GetItemResponse response = callStub.getItem(
        GetItemRequest.newBuilder()
                .setItemId("item-42")
                .build());
```

`withDeadline(deadline)` attaches an absolute deadline to the logical RPC. When gRPC performs retries, attempts stay within that time budget. In a Spring gRPC application, stubs are typically injected or built from a channel managed by client configuration; set the deadline on the stub per call according to business requirements.

Do not create a fresh deadline inside each retry at the application layer if your goal is to bound the entire operation. Doing so accidentally grants a new budget and lets total latency exceed the caller's SLA.

## 4. Backoff can make the next attempt no longer useful

Suppose 250 ms remain on the deadline, while the base backoff for the next retry is 500 ms. If the client waits out the full backoff, the deadline will expire before the attempt even starts. The runtime will terminate the call when the deadline expires rather than continuing indefinitely.

Even when the remaining deadline exceeds the backoff, you must still account for the minimum time needed for an attempt to have a chance of completing. For example:

- 700 ms remain on the deadline.
- Expected backoff is 200 ms.
- Only about 500 ms remain for the next attempt and overhead.

If the method normally takes 1 second to process, this attempt is unlikely to deliver value. However, a gRPC retry policy does not provide a general guarantee that the runtime will accurately predict required processing time and only start an attempt when sufficient budget exists. The deadline is a hard stop; deciding whether to retry when little budget remains depends on your SLA and application logic.

With an application-managed retry loop, you can check the budget before scheduling:

```java
long remainingMs = deadline.timeRemaining(TimeUnit.MILLISECONDS);
long delayMs = computedBackoff.toMillis();
long minimumUsefulAttemptMs = 300;

if (remainingMs <= delayMs + minimumUsefulAttemptMs) {
    completeAsTimedOutOrUnavailable();
    return;
}

scheduler.schedule(this::startNextAttempt,
        delayMs, TimeUnit.MILLISECONDS);
```

This is **application-level retry** logic, not an automatic extension of gRPC service config. `minimumUsefulAttemptMs` must come from the method's SLA/measurements; it is not a value gRPC can infer automatically. When managing retries yourself, you must still bound attempts, cancel timers when the caller cancels, and ensure idempotency.

## 5. How is the deadline propagated to the server?

gRPC propagates deadline information over the wire as remaining timeout. When a logical RPC is retried, the server handling a later attempt receives the remaining time, not a brand-new full deadline as when the client started.

This matters across a chain of services:

```text
Client (total deadline 2 seconds)
   |
   |  attempt 1 takes 500 ms, backoff 200 ms
   v
Service A (approx. 1.3 seconds left when attempt 2 starts)
   |
   |  calls Service B
   v
Service B (receives the remaining budget of the call, not a fresh 2 seconds)
```

If Service A calls Service B and creates a new deadline longer than the remaining budget, total time can exceed the limit set by the client. Propagate the appropriate deadline/cancellation context when making downstream calls, and do not arbitrarily extend the deadline.

In a Spring gRPC system, metadata/interceptors can carry a trace ID, tenant, or authentication details. Deadlines are gRPC's built-in timing mechanism; there is no need to pass a custom header to replace standard deadlines.

## 6. Server pushback can change waiting time

When overloaded, the server can use retry pushback to instruct the client to wait longer or stop retrying. The gRPC mechanism uses the special metadata `grpc-retry-pushback-ms`:

- A positive value indicates the waiting time before the next retry.
- A negative value requests not retrying that call.
- Pushback does not grant extra deadline; the specified waiting time still consumes the logical RPC's budget.

For example, suppose 600 ms remain on the deadline, while the server requests a 1,000 ms pushback. The client cannot wait a full second and still run an attempt under the same deadline; the call will expire before then.

Pushback and backoff should not be added together or overridden based on application guesswork. Let the gRPC runtime handle them per retry policy semantics; if implementing retries yourself, clearly define the precedence between backoff, pushback, and deadline.

## 7. Choosing deadline and retry delay based on SLA

Design the policy around the duration the caller actually tolerates, rather than picking `maxAttempts` first and trying to squeeze it into a deadline.

A practical workflow:

1. Measure normal latency and latency while a dependency is recovering.
2. Define the overall SLA for the operation, including network, processing, and retry time.
3. Choose the deadline for the entire logical RPC.
4. Choose `initialBackoff`, `maxBackoff`, multiplier, and `maxAttempts` so useful attempts still have a chance within that window.
5. Retry only transient statuses and respect pushback/throttling.
6. For write operations, use an idempotency key because deadline expiration does not prove the server has not executed the operation.

For example, a read method with a 2-second SLA might use a 2-second deadline and retry up to three attempts with small backoff. A critical write operation might need a longer deadline with fewer attempts, combined with idempotency and status querying to resolve uncertain outcomes.

## 8. Retry delay and streaming RPCs

For unary RPCs, each attempt is a request/response execution that can be retried if the call has not committed. For client streaming and bidirectional streaming, automatic retry is constrained by commitment and the retry buffer:

- Once the client receives response headers or the request exceeds the retry buffer limit, the call may already be committed.
- After commit, gRPC does not automatically replay the entire stream when a new error occurs.
- The deadline still applies to the entire stream; both stream lifetime and backoff intervals consume the budget.
- `maxAttempts` cannot be used to recover an active stream from the last message.

If a committed stream disconnects, the application needs to open a new RPC and resume using `request_id`, sequence/cursor, and idempotency. The deadline of the new RPC is a new budget decided by the caller; it should not be reset indefinitely if the business SLA has already expired.

## 9. Testing remaining deadline

Tests should verify total elapsed time and attempt counts, not just the final status:

| Scenario | Assertion |
| --- | --- |
| First attempt fails quickly with plenty of deadline left | Client can wait for backoff and retry |
| Backoff nearly equals remaining time | Call ends due to deadline; does not wait indefinitely |
| Deadline expires while an attempt is running | Client receives `DEADLINE_EXCEEDED` or the corresponding terminal state |
| Multiple attempts within one logical RPC | Total time does not exceed the configured deadline, beyond minor measurement variance |
| Server pushback longer than remaining time | No useful attempt occurs after deadline expiration |
| Downstream call | Receives remaining deadline budget, not granted the full SLA again |
| Caller cancels during backoff | Retry timer is cancelled and no subsequent attempt is issued |
| Retrying write operation after timeout | Idempotency prevents side effects from executing twice |
| Committed bidi stream disconnects | Reconnect/resume per protocol; do not assume retry delay restores the old stream |

For stable tests, use a test server that returns statuses per attempt and logs request arrival timestamps. Check timings within an allowed range because backoff includes jitter and schedulers are not millisecond-exact. For custom retries, inject a fake clock/scheduler to test tight-deadline cases without waiting in real time.

Metrics to monitor include remaining deadline at the start of each attempt, actual backoff duration, attempt count, calls terminated by deadline, retry success rate, and the rate of attempts aborted before starting due to insufficient budget.

## 10. Common mistakes

1. **Granting a new deadline for each attempt.** This turns one overall limit into multiple separate limits and can breach the SLA.
2. **Treating backoff as outside the deadline.** Retry waiting time still consumes the logical RPC's budget.
3. **Expecting `maxAttempts` to always be exhausted.** The deadline can terminate the call before the attempt budget runs out.
4. **Assuming enough time for backoff means enough time for an attempt.** The attempt still needs network and processing time.
5. **Ignoring pushback.** The server may ask to wait longer or stop retrying; the deadline keeps ticking meanwhile.
6. **Creating a downstream deadline longer than the remaining deadline.** The service chain can exceed the caller's SLA.
7. **Retrying after `DEADLINE_EXCEEDED` without idempotency.** The server may have already completed side effects before the client timed out.
8. **Using automatic retry to resume a bidi stream.** A committed stream requires an application-layer reconnect/resume protocol.

## 11. Practice exercises

For `catalog.v1.CatalogService/GetItem`:

1. Set a total deadline of 2 seconds, `maxAttempts=4`, `initialBackoff=200ms`, `maxBackoff=1s`.
2. Make the server return `UNAVAILABLE` after varying processing times; record remaining budget before each attempt.
3. Create a case where expected backoff is longer than the remaining deadline; verify the call stops on time.
4. Simulate pushback longer than the remaining deadline and verify no attempts run after the call expires.
5. Make a downstream call from the server, propagate the remaining deadline, and compare against accidentally creating a fresh deadline.
6. For a write operation, simulate the server completing while the response arrives after the deadline; verify the retry uses the same idempotency key.

**Completion criteria:** learners can calculate remaining deadline after each attempt/backoff, understand why retry delay consumes the total budget, configure policies matching the SLA, and avoid prolonging calls or causing duplicate side effects.

### References

- [gRPC Deadlines](https://grpc.io/docs/guides/deadlines/): deadlines and propagating time budgets across services.
- [gRPC Retry](https://grpc.io/docs/guides/retry/): retry policy, backoff, commitment, and pushback.
- [gRPC Service Config](https://grpc.io/docs/guides/service-config/): configuring retries per service/method.
- [gRPC Java Deadline API](https://grpc.github.io/grpc-java/javadoc/io/grpc/Deadline.html): creating deadlines and querying remaining time.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): gRPC client/server integration in Spring.
