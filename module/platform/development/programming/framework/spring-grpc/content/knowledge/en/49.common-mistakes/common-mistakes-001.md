# Treating gRPC as a Local Function Call and Ignoring Deadlines

## 1. Why is this a design flaw?

In **SPRING_GRPC**, a gRPC call looks like a Java method call: the client calls a stub, the server runs the implementation, and returns a response. However, an RPC crosses process and network boundaries. Between both sides lie Protobuf serialization, HTTP/2, TLS, load balancing, server queues, network latency, and potential failure points.

A local Java method usually returns a result or throws an exception within the same process. An RPC can:

- Fail to connect to the server or drop mid-call.
- Wait in a queue or wait on a database longer than expected.
- Have its deadline expire while the server is still processing.
- Commit a side effect, yet lose the response on the way back.
- Be retried by the client or proxy, causing the same command to arrive at the server multiple times.

If an RPC is treated as a local function call, code typically omits deadlines, retries arbitrarily, and leaves the state ambiguous on timeout. As a result, threads and connections are held for a long time, stale requests continue consuming resources, or a single command produces side effects multiple times.

**A deadline is the end-to-end time limit of an RPC.** Clients and servers must use deadlines to bound work, propagate the budget to dependencies, and stop processing when the result is no longer useful.

## 2. Local method calls and RPC calls have different semantics

| In-process method call | gRPC call over network |
| --- | --- |
| No wire serialization required | Request/response encoded with Protobuf |
| Does not depend on DNS, TLS, or network route | Can fail on connection, handshake, proxy, or network |
| Typically shares heap and process lifecycle | Client and server have independent lifecycles |
| Exceptions propagate directly on the call stack | Errors are represented by gRPC status/trailers |
| Wait time is usually controlled by code | Involves queueing, network latency, and deadlines |
| No ambiguity from a lost response on the network | Server may commit while client receives no response |
| Retries are usually decided by calling code | Retries may occur at the client, gRPC policy, or intermediate layer |

A gRPC stub is a client proxy, not a server object residing in the same JVM. Do not hold locks or database transactions while making a remote RPC call as if it were a fast, reliable method.

An RPC can be slow even when the server processes quickly: total time also includes connection wait, queueing, round-trip network latency, and processing in dependencies.

## 3. Setting deadlines on the client

The client should set a deadline for every RPC with an expected completion time. With a blocking stub:

```java
OrderReply reply = blockingStub
    .withDeadlineAfter(800, TimeUnit.MILLISECONDS)
    .getOrder(request);
```

The 800 ms example is illustrative only. Choose deadlines based on SLOs, p95/p99 latency, operation complexity, and how long the caller can still wait.

Guidelines:

- Do not rely on an infinite default deadline.
- Choose separate deadlines by RPC type; simple queries and complex commands can have different budgets.
- The deadline must cover connection time, queueing, server work, and response.
- If the caller already has a deadline, dependency calls must use the remaining budget rather than starting a fresh full timeout.
- Avoid setting deadlines too short, which causes valid requests to fail frequently and retries to add extra load.

With asynchronous stubs, deadlines are also set on the stub before calling the method. A deadline is a per-call property, not a timeout for the entire channel.

## 4. Relative timeouts vs. absolute deadlines

A timeout usually expresses a duration measured from the start of an operation. A deadline expresses an absolute point in time by which the operation must finish.

Suppose a client has a total budget of 1 second:

- The RPC to service A consumes 300 ms.
- Service A calls service B.
- If A sets a new 1-second timeout for B, total time can exceed 1 second.
- If A propagates the original deadline, B only has about 700 ms remaining, minus further overhead.

Resetting a full timeout at each hop accumulates budgets and breaks the end-to-end limit. Propagate the original deadline or compute the remaining budget and apply a smaller cap according to service policy.

## 5. Reading and propagating deadlines on the server

In gRPC Java, the server can read the current deadline from `Context`:

```java
Deadline deadline = Context.current().getDeadline();

if (deadline == null) {
    // Client did not send a deadline: apply a service-level cap.
} else {
    long remainingMs =
        deadline.timeRemaining(TimeUnit.MILLISECONDS);

    if (remainingMs <= 0) {
        throw Status.DEADLINE_EXCEEDED
            .withDescription("Request deadline has expired")
            .asRuntimeException();
    }
}
```

When calling downstream gRPC, use the current deadline instead of granting a full new budget:

```java
Deadline parentDeadline = Context.current().getDeadline();

OrderReply reply;
if (parentDeadline != null) {
    reply = orderBlockingStub
        .withDeadline(parentDeadline)
        .getOrder(downstreamRequest);
} else {
    reply = orderBlockingStub
        .withDeadlineAfter(700, TimeUnit.MILLISECONDS)
        .getOrder(downstreamRequest);
}
```

The example assumes the stub and request are already configured. When no parent deadline exists, the service should still apply a finite service-level cap. When a parent deadline exists, an earlier deadline can be chosen if the service has a lower internal limit.

If work is handed off to an arbitrary executor, do not assume the gRPC Context automatically appears on the new thread. Capture/propagate Context using gRPC Java's mechanism or pass the deadline explicitly via the application command. For background tasks detached from the RPC lifecycle, use a separate deadline policy instead of keeping an expired Context.

## 6. Splitting the budget across dependencies

An RPC may perform multiple steps: reading the database, calling an inventory service, calling a payment service, and writing results. Each step must consume from the same end-to-end budget.

Example for a request with 900 ms remaining:

| Step | Illustrative budget |
| --- | ---: |
| Validation and application logic | 50 ms |
| Waiting for connection pool | 100 ms |
| Database query and commit | 200 ms |
| Downstream RPC | 350 ms |
| Response mapping and buffer | 100 ms |
| Remainder for variance | 100 ms |

This is an illustrative allocation, not a standard configuration. Measure actual latency to choose budgets.

Before each dependency call:

1. Read the remaining deadline.
2. Subtract the buffer needed for subsequent steps.
3. Apply a service cap if the dependency has its own limit.
4. Do not start work if the remaining budget is insufficient.
5. Record which dependency consumes time.

Do not give every dependency the same timeout equal to the initial deadline. If each step is allowed to wait 1 second, a single request can stretch across multiple seconds.

## 7. Deadline expiration does not mean the server automatically stops all work

When a deadline expires, gRPC marks the call as expired and the server Context is cancelled. However, this does not automatically stop every piece of Java code.

Operations that may continue if they do not support cancellation:

- CPU loops that do not check cancellation.
- JDBC queries where the driver/database has not yet received or handled the cancel.
- Downstream HTTP calls or RPCs without their own deadline.
- Futures running in an executor that are not cancelled.
- Work already placed in a queue without checking whether the call is still valid.

Therefore, cancellation must be handled cooperatively. Check Context before starting resource-intensive steps; propagate deadlines to dependencies; set query/statement timeouts; and cancel tasks if the API supports it.

With JDBC, gRPC cancellation does not guarantee a Statement stops immediately. Use a query timeout or database-side statement timeout and test with the actual driver. Do not assume cancelling an RPC will roll back an already-committed transaction.

## 8. Checking cancellation on the server

For unary RPCs, Context state can be checked at safe points:

```java
if (Context.current().isCancelled()) {
    throw Status.CANCELLED
        .withDescription("Call was cancelled")
        .asRuntimeException();
}

return applicationService.execute(command);
```

For streaming RPCs, the server can use `ServerCallStreamObserver` to be notified when the client cancels:

```java
if (observer instanceof ServerCallStreamObserver<?> serverObserver) {
    serverObserver.setOnCancelHandler(() -> {
        cancellationSignal.cancel();
    });
}
```

The example uses `cancellationSignal` as an application-managed mechanism to signal producers/workers to stop. The handler must be brief; do not perform blocking cleanup or long database work directly inside the cancellation callback.

Do not emit further messages after the stream has been cancelled or a terminal signal has been sent. If work already committed before cancellation arrived, preserve the committed data and provide idempotency/status queries if the caller needs to determine the outcome.

## 9. Distinguishing deadlines, internal timeouts, and cancellation

| Scenario | Common gRPC status | Meaning |
| --- | --- | --- |
| Client deadline expires before receiving result | DEADLINE_EXCEEDED | Caller has exhausted its wait budget |
| Client actively cancels the RPC | CANCELLED | Caller no longer wants to wait |
| Database query exceeds query timeout | May map to DEADLINE_EXCEEDED or status per contract | Internal dependency timeout |
| Downstream temporarily unavailable | UNAVAILABLE | Dependency cannot serve temporarily |
| Transaction hits optimistic conflict | ABORTED | Need to re-read and retry workflow |
| Invalid request | INVALID_ARGUMENT | Caller must fix input |

Status does not fully describe commit state. A client receiving DEADLINE_EXCEEDED cannot conclude the server did not execute the command. If the database committed before the response was lost, the side effect still exists.

Do not turn every timeout into UNAVAILABLE. Classifying by root cause and contract helps clients decide whether to retry, wait, or fix the request.

## 10. Retries must stay within the total deadline and have safe semantics

Retries can be useful for transient errors, but each attempt consumes additional time and resources. Retry policies must limit attempts, use backoff with jitter, and stop when the remaining deadline is insufficient.

Principles:

- Only retry statuses defined by the contract as retryable.
- Keep the same idempotency key for the same command.
- Do not retry INVALID_ARGUMENT or unrecoverable business errors.
- For ABORTED, re-read the data and re-run the entire use case in a new transaction.
- For UNAVAILABLE or DEADLINE_EXCEEDED, the outcome may be unknown; commands with side effects require idempotency.
- Do not retry simultaneously at the client, server, proxy, and worker without accounting for total attempts.
- Do not use retries to mask an overloaded database or dependency.

Backoff example:

```text
delay = min(max_delay, base_delay × 2^(attempt - 1))
wait  = delay + random_jitter
```

Before sleeping or starting a new attempt, check the remaining deadline. Do not create a fresh full deadline for each retry attempt.

## 11. Idempotency protects commands when responses are lost

For commands like CreateOrder or CapturePayment, the client needs to send a stable idempotency key for a single business intent.

The server stores the key, request fingerprint, and result in the same transaction as the business update. A database unique constraint protects when two attempts with the same key arrive concurrently.

On retry:

- Same key and same fingerprint: the server returns the stored result.
- Same key but different payload: the server rejects the request.
- First attempt rolled back: a subsequent attempt can execute.
- First attempt committed but response was lost: a subsequent attempt replays the result and creates no new side effect.

If the command needs to emit an event, write to an outbox in the same transaction. Do not call a payment provider or broker and assume a database rollback will undo external side effects; use downstream idempotency keys, outbox, or saga/compensation.

## 12. Do not hold transactions while waiting on remote RPCs

A related mistake is opening a database transaction, reading/locking rows, and then calling a downstream gRPC service before committing. If downstream is slow, the transaction holds connections and locks for the entire duration of the network call.

Consequences:

- Connection pool exhausts quickly under load.
- Lock contention and deadlocks increase.
- Downstream deadline may expire while the transaction still holds resources.
- Retries may repeat both the network call and database updates.

The design should separate steps:

1. Read/write necessary data in a short transaction.
2. Write an outbox intent if an event needs to be emitted or an async task invoked.
3. Commit and release the connection.
4. Dispatcher/worker calls downstream outside the transaction.
5. Use idempotency and a state machine to handle retry/recovery.

If business logic strictly requires a synchronous downstream call before completion, clearly define consistency and compensation. Keeping a transaction open while waiting on the network should only be a deliberate decision after evaluating load and failure modes.

## 13. Observing deadlines end-to-end

Do not measure total RPC latency alone. Collect:

- Deadline/remaining budget when the server receives the call.
- Queueing and application processing time.
- Pool acquisition, query, lock wait, and transaction duration.
- Latency of each downstream RPC.
- Counts of deadline expirations, client cancellations, and query timeouts.
- Number of requests that continue running after the caller has cancelled.
- Retry count, backoff time, and final status.

Traces should show each dependency span to pinpoint where time is being spent. Avoid putting high-cardinality request IDs or user IDs into metric labels; use trace/log correlation to investigate individual calls.

If RPCs frequently hit deadlines downstream, increasing the deadline will not necessarily solve the problem. First identify whether the bottleneck is queueing, network, database, locks, or dependency latency.

## 14. Testing deadlines and cancellation

Integration tests through a real gRPC server are needed:

| Test | What to verify |
| --- | --- |
| Client sets short deadline | Client receives DEADLINE_EXCEEDED |
| Server receives request without deadline | Service-level cap still bounds processing |
| Slow downstream RPC | Downstream uses parent deadline/remaining budget |
| Slow database query | Query timeout bounds duration and transaction handles properly |
| Client actively cancels | Server receives cancellation and stops cancellable work |
| Executor task | Context/deadline is propagated explicitly |
| Commit then lost response | Retry with same key replays result without duplicates |
| Multiple downstream hops | Total time does not reset timeout at each hop |
| RPC deadline expires while streaming | No further messages sent after cancellation |

Do not test solely with sleeps and approximate timing assertions. Use controllable latches/fake downstreams to create deterministic wait points, then verify Context cancellation, query state, and database state. Different drivers cancel queries differently; test with a driver/database close to production.

## 15. Review checklist

- Every critical RPC has a finite deadline aligned with its SLO.
- Stubs are not treated like local Java methods or assumed to have an always-available network.
- End-to-end deadlines are propagated downstream; full timeouts are not reset at each hop.
- Server reads remaining deadline and has a service-level cap when the client omits one.
- Async work propagates Context/deadline explicitly.
- Pool/query/transaction timeouts align with the remaining budget.
- Cancellation is checked at safe points.
- JDBC/HTTP/downstream calls have their own timeout/cancellation mechanisms.
- Database transactions/locks are not held while waiting on the network.
- DEADLINE_EXCEEDED is not interpreted as a guaranteed transaction rollback.
- Retries have limits, backoff/jitter, and respect the total deadline.
- Commands with side effects use idempotency keys; external events use an outbox.
- Metrics/traces break down latency per dependency.
- Integration tests cover deadlines, cancellation, downstream propagation, and lost responses.

In **SPRING_GRPC**, an RPC is a call across process boundaries and therefore has latency, network failures, and uncertain outcomes. Set finite deadlines on the client, preserve the same budget across downstream hops, and configure appropriate database/query timeouts. When a deadline expires, stop cancellable work; for commands with side effects, use idempotency to handle cases where the server committed but the client did not receive the response.
