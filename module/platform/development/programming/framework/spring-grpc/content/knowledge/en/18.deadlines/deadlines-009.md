# Deadlines and Retries

**Retrying** means resending an RPC when a previous attempt fails for a recoverable reason. A **deadline** bounds the total time the caller accepts waiting for a result. Both mechanisms must be designed together: retries can improve success rates during transient network or service disruptions, yet every attempt and backoff interval consumes the deadline budget.

In **Spring gRPC**, deadlines are set on the gRPC Java stub; retries can be configured at the gRPC layer via service config or controlled at the application layer. Either way, you must never create a fresh, longer deadline for each retry attempt. For commands with side effects, idempotency or a status lookup mechanism is required because a timeout does not prove the server did not perform the operation.

## 1. The deadline is the shared budget for all retries

Suppose a client grants 1,000 ms for GetPayment. The first attempt takes 250 ms and receives UNAVAILABLE; the client backs off for 100 ms and retries. The second attempt only has about 650 ms remaining, before accounting for subsequent transmission and processing costs.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as gRPC service
    C->>S: Attempt 1 (1,000 ms total deadline)
    S-->>C: UNAVAILABLE after 250 ms
    Note over C: Backoff 100 ms
    C->>S: Attempt 2 (remaining budget)
    S-->>C: Response OK
~~~

The **logical RPC** deadline encompasses:

- The initial attempt.
- Subsequent retry attempts.
- Backoff intervals between attempts.
- Request/response transmission and processing time on each attempt.

If the deadline expires, the client receives DEADLINE_EXCEEDED and has no budget left to keep retrying. Do not reset withDeadlineAfter(1, SECONDS) per attempt, as doing so allows total duration to grow with the number of attempts and exceed the caller's limit.

## 2. Only retry recoverable errors

Not every gRPC status is appropriate to retry. Distinguish transient errors, input errors, authorization errors, and business state errors:

| Status | Should You Retry? | How to Handle |
| --- | --- | --- |
| **UNAVAILABLE** | Usually yes, if the operation is safe | Retry with backoff; service or connection may be temporarily unavailable |
| **RESOURCE_EXHAUSTED** | Only when known to be transient throttling | Wait according to backoff/quota; do not aggressively retry while overloaded |
| **ABORTED** | May require transaction-level retry | Re-read state and re-run the entire transaction per business rules |
| **DEADLINE_EXCEEDED** | Do not auto-retry by default | Overall budget expired or outcome unknown; query state if there are side effects |
| **CANCELLED** | Usually no | Caller or parent context cancelled; retrying goes against cancellation intent |
| **INVALID_ARGUMENT** | No | Fix the request before calling again |
| **UNAUTHENTICATED / PERMISSION_DENIED** | Not with the same credentials/permissions | Refresh credentials or fix permissions via a separate flow |
| **FAILED_PRECONDITION** | Usually not with the same state | Change business preconditions before trying again |

The list of retryable statuses must reflect the service contract. For example, RESOURCE_EXHAUSTED may mean temporary throttling or a quota exhausted for hours; status code alone is insufficient to justify unbounded retries.

## 3. gRPC retry policy via service config

gRPC supports per-service/per-method retry policies through **service config**. The following example retries GetPayment only when receiving UNAVAILABLE:

~~~json
{
  "methodConfig": [
    {
      "name": [
        {
          "service": "acme.payment.v1.PaymentService",
          "method": "GetPayment"
        }
      ],
      "retryPolicy": {
        "maxAttempts": 3,
        "initialBackoff": "0.1s",
        "maxBackoff": "0.8s",
        "backoffMultiplier": 2.0,
        "retryableStatusCodes": ["UNAVAILABLE"]
      }
    }
  ]
}
~~~

Meaning:

- **maxAttempts** is the maximum total number of attempts, **including the initial call**.
- **initialBackoff** is the initial wait time before the first retry.
- **maxBackoff** caps the growing wait duration.
- **backoffMultiplier** controls backoff growth between attempts.
- **retryableStatusCodes** specifies which statuses permit retrying.

Service config can be supplied by a name resolver or default channel configuration, depending on how the application builds channels. gRPC Java and the resolver must support retries in the version being used; verify actual configuration in your Spring environment. Do not assume simply placing JSON in any config file automatically applies the policy to every channel.

A retry policy only operates within the logical RPC's deadline. If the deadline expires before all attempts are used, the call ends per the deadline. Once gRPC receives response headers and the call is considered committed, the retry mechanism stops starting new attempts for that call.

## 4. Exponential backoff and avoiding retry storms

If many clients retry simultaneously right after a service recovers, they can trigger another load spike and overload the service again. **Exponential backoff** increases wait time with each attempt:

\[
B_n = \min(B_{\max}, B_0 \times m^{n-1})
\]

Where:

- \(B_0\) is the initial backoff.
- \(m\) is the multiplier.
- \(B_{\max}\) is the maximum backoff.

Include **jitter** to spread out retry timing across multiple clients. Combining attempt limits, retry throttling, circuit breakers, and concurrency limits helps avoid amplifying incidents.

Do not retry when too little deadline remains for a reasonable attempt to complete. Starting a retry with only a few milliseconds left usually adds load and fails immediately with a timeout.

## 5. Set the deadline once per logical RPC

With a gRPC Java client, set the deadline on the stub before calling:

~~~java
GetPaymentResponse response = paymentStub
    .withDeadlineAfter(1200, TimeUnit.MILLISECONDS)
    .getPayment(request);
~~~

If using gRPC's retry policy, attempts belong to the same logical call and are bounded by this deadline. Do not wrap individual attempts with a stub carrying a fresh timeout equal to the initial timeout.

In nested calls, the parent RPC's remaining deadline continues to bound child services. Downstream retries must also fit within that remaining budget; do not grant the full budget again to each service.

## 6. Manual retries at the application layer

Some business flows need to decide retries based on state, idempotency, or multi-step results. In those cases, you can control retries at the application layer. The example below illustrates bounded retries for a read query:

~~~java
Deadline deadline = Deadline.after(1200, TimeUnit.MILLISECONDS);
long backoffMs = 50;
int maxAttempts = 3;

for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    if (deadline.isExpired()) {
        throw Status.DEADLINE_EXCEEDED
            .withDescription("overall RPC budget exhausted")
            .asRuntimeException();
    }

    try {
        return paymentStub
            .withDeadline(deadline)
            .getPayment(request);
    } catch (StatusRuntimeException ex) {
        boolean retryable =
            ex.getStatus().getCode() == Status.Code.UNAVAILABLE;

        if (!retryable || attempt == maxAttempts) {
            throw ex;
        }

        long remainingMs =
            deadline.timeRemaining(TimeUnit.MILLISECONDS);
        long reserveMs = 30;
        if (remainingMs <= backoffMs + reserveMs) {
            throw ex;
        }

        try {
            TimeUnit.MILLISECONDS.sleep(backoffMs);
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw Status.CANCELLED
                .withDescription("retry interrupted")
                .withCause(interrupted)
                .asRuntimeException();
        }

        backoffMs = Math.min(backoffMs * 2, 400);
    }
}
throw Status.UNAVAILABLE
    .withDescription("retry attempts exhausted")
    .asRuntimeException();
~~~

This is a synchronous example for a read operation; import Deadline, Status, StatusRuntimeException, and TimeUnit. In production, add jitter, per-attempt telemetry, and tests for deadline expiration during backoff. For async flows, use a scheduler/future instead of sleep to avoid tying up threads.

Do not combine manual retries with automatic channel retries in an uncontrolled way. If both layers retry, actual attempts can multiply. Choose one layer as the primary owner or explicitly budget attempts across both.

## 7. Commands with side effects require idempotency

Suppose a client calls CreatePayment. The server records the payment, but the response is lost or arrives after the deadline. The client receives DEADLINE_EXCEEDED; if it sends a new command, the system may create a second payment.

The solution is a stable **idempotency key** for the same business intent:

~~~proto
rpc CreatePayment(CreatePaymentRequest)
    returns (CreatePaymentResponse);

message CreatePaymentRequest {
  string customer_id = 1;
  int64 amount_minor = 2;
  string currency = 3;
  string idempotency_key = 4;
}
~~~

The server must:

1. Scope the key uniquely, for example by tenant and operation.
2. Store the key alongside a hash of the payload and processing state.
3. Persist the key/result atomically with the side effect or use an appropriate transaction/outbox.
4. When receiving the same key and same payload again, return the stored result or current operation status.
5. Reject the same key with a different payload.

Simply adding an idempotency_key field to Protobuf does not create idempotency. Storage, concurrency locking, retention periods, and handling of in-flight requests must be implemented on the server.

If the client does not know whether the operation committed, provide a query method by operation ID/idempotency key. That is usually safer than issuing a new command after a timeout.

## 8. Retries with streaming RPCs

Retrying streaming RPCs is more complex than unary because part of the data may already have been sent or processed:

- **Client streaming:** the server may have already persisted several chunks before the stream failed.
- **Server streaming:** the client may have already received and processed partial events before the failure.
- **Bidirectional streaming:** both directions may have exchanged commands/events before the session was cancelled.

Do not blindly replay the entire stream. Design the protocol with:

- A stable session or upload ID.
- A message ID or sequence for each chunk/event.
- Acknowledgements to confirm which data was accepted.
- A cursor to resume from the last processed position.
- Deduplication to safely handle resent messages.

For server-streaming subscriptions, the client can reconnect from the last saved sequence. For uploads, the client resends chunks by upload ID and sequence; the server acknowledges received chunks to avoid duplicate writes. Resume logic is application behavior and does not appear automatically just by enabling a retry policy.

## 9. When the deadline expires during retries

When the deadline expires during an attempt or during backoff, the logical RPC ends with DEADLINE_EXCEEDED. The client should not start a new attempt with a fresh deadline if it is still the same request.

If the final status is DEADLINE_EXCEEDED:

1. Do not conclude the server never executed side effects.
2. For commands, query operation state or retry with the same idempotency key per the server contract.
3. For streams, use session ID/cursor to resume if the protocol supports it.
4. Record attempt count, backoff duration, and remaining budget.
5. Stop retrying if the caller cancelled or the overall deadline expired.

CANCELLED usually indicates the caller no longer wants the result; automatic retries at that point can work against the caller's intent.

## 10. Testing retries and deadlines

Tests should verify attempt counts, timing, and side effects:

| Scenario | What to Verify |
| --- | --- |
| First attempt UNAVAILABLE, next attempt OK | Retries the right number of times and returns the result |
| All attempts UNAVAILABLE | Stops at maxAttempts |
| Deadline expires during backoff | Does not start the next attempt |
| Caller sets a short deadline | Total duration does not exceed the deadline |
| Command commits but response is lost | Same idempotency key does not create a second side effect |
| INVALID_ARGUMENT or PERMISSION_DENIED | Does not wastefully retry |
| Stream fails after partial messages | Resumes with cursor/sequence without duplicate processing |

You can use a gRPC in-process server or a fake downstream to control statuses and delays. Use latches/futures instead of long Thread.sleep calls in tests. With Spring, integration tests should verify service config/interceptors are attached to the right channel and the retry policy takes effect in the real environment.

## 11. Observing retries in production

Track by full method name:

- Total logical RPCs and total attempts.
- First-attempt success rate and post-retry success rate.
- Status of each attempt and final status.
- Backoff duration and remaining deadline before each attempt.
- Number of logical calls ending in DEADLINE_EXCEEDED.
- Retry throttling, circuit breaker trips, and queue saturation.
- Idempotency hit rate, key conflicts, and operations with unknown status.
- For streaming: reconnect counts and duplicate or missing sequences.

If the retry rate climbs, investigate root causes such as unavailable services, exhausted pools, growing queues, or unstable networks. Do not treat successful retries as proof of a healthy system; high attempt counts may be masking failures and increasing load.

## 12. Summary and self-check

**Deadlines bound the entire logical RPC; retries only consume the remaining budget.** Choose retryable statuses per contract, use bounded backoff, and avoid retry storms. For commands with side effects, use an idempotency key or operation ID because a timeout does not prove the server did not commit. For streaming, use sessions, sequences, and resume rather than blind replay.

Self-check:

1. Why must each retry not be granted the full initial deadline again?
2. Which calls are included in maxAttempts in a retry policy?
3. Why is DEADLINE_EXCEEDED not an appropriate default status to retry?
4. How can you retry CreatePayment without creating duplicate payments?
5. Why do streams need a cursor or sequence when reconnecting after an error?

Combining deadlines, controlled retry policies, idempotency, and per-attempt observability helps Spring gRPC recover from transient failures while preserving time bounds, system load limits, and business consistency.
