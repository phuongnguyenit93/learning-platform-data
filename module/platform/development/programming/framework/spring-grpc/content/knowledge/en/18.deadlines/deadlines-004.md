# Expired Deadlines Produce DEADLINE_EXCEEDED

**DEADLINE_EXCEEDED** is the gRPC status indicating that a call did not complete within the time allowed by the client. When the client sets a deadline, gRPC tracks the remaining time throughout the RPC. If the deadline expires before the client receives a completed result, the client ends the call with this status.

In **Spring gRPC**, Java applications typically observe this status via a **StatusRuntimeException** on a blocking stub or the **onError(Throwable)** callback on an async stub. The server side typically observes RPC **cancellation** through **io.grpc.Context**, because the client-side deadline means the call no longer needs to continue. Distinguishing these two perspectives is essential for handling timeouts, stopping work, preserving side effects, and deciding when retries are safe.

## 1. What does DEADLINE_EXCEEDED mean?

An RPC with a deadline is a call with a **latest completion timestamp**. For example, the client grants 500 ms. If after 500 ms the client still has not received the completed result, gRPC reports **DEADLINE_EXCEEDED**.

This status does not necessarily prove the server spent the entire 500 ms processing slowly. The budget may have been consumed by:

- Waiting for a connection, channel, or client-side resources.
- Network transmission latency for request and response.
- Queuing before the request is processed.
- Server business logic execution or database queries.
- Downstream calls across one or more other services.
- A response that was produced but arrived at the client after the deadline expired.

~~~mermaid
flowchart LR
    A["Client sets deadline"] --> B["Wait / transmit request"]
    B --> C["Server processing"]
    C --> D["Downstream / database"]
    D --> E["Return response"]
    E --> F{"Client receives before deadline?"}
    F -->|"Yes"| G["Status OK"]
    F -->|"No"| H["DEADLINE_EXCEEDED"]
~~~

The deadline applies to the **entire RPC**, not just server business code. For streaming RPCs, the entire stream lifetime also falls within the budget; sending more messages does not automatically restart the clock.

## 2. How does the client receive DEADLINE_EXCEEDED?

With a blocking stub, the deadline is typically set using withDeadlineAfter. When it expires, the call throws StatusRuntimeException:

~~~java
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import java.util.concurrent.TimeUnit;

GetPaymentRequest request = GetPaymentRequest.newBuilder()
    .setPaymentId("payment-901")
    .build();

try {
    GetPaymentResponse response = paymentStub
        .withDeadlineAfter(500, TimeUnit.MILLISECONDS)
        .getPayment(request);

    System.out.println(response.getState());
} catch (StatusRuntimeException ex) {
    Status.Code code = ex.getStatus().getCode();

    if (code == Status.Code.DEADLINE_EXCEEDED) {
        // The client did not receive a result within the budget.
        // Check business state before retrying a command.
    } else {
        throw ex;
    }
}
~~~

With an async stub, errors are delivered to the onError callback:

~~~java
var stub = PaymentServiceGrpc.newStub(channel)
    .withDeadlineAfter(500, TimeUnit.MILLISECONDS);

stub.getPayment(request, new StreamObserver<GetPaymentResponse>() {
    @Override
    public void onNext(GetPaymentResponse response) {
        handleResponse(response);
    }

    @Override
    public void onError(Throwable error) {
        Status.Code code = Status.fromThrowable(error).getCode();
        if (code == Status.Code.DEADLINE_EXCEEDED) {
            handleTimeout();
        } else {
            handleRpcFailure(code, error);
        }
    }

    @Override
    public void onCompleted() {
        // RPC completed normally.
    }
});
~~~

For unary calls, the client typically receives either one response or one error. For streaming calls, the client may have already received several messages via onNext before onError reports DEADLINE_EXCEEDED. Already-received messages do not turn the RPC into a success; the client must apply business rules for partial data.

## 3. Client status and server cancellation are two perspectives

This is the most important point when diagnosing timeouts:

| Observing Side | What is typically seen when the client deadline expires |
| --- | --- |
| **Client** | RPC terminates with **DEADLINE_EXCEEDED** |
| **Server handler** | RPC Context is marked cancelled |
| **Server outbound calls** | Child calls bound to the context may be cancelled as well |
| **Custom Java tasks** | Only stop if the code or task API supports cancellation |

The server does not necessarily receive an application callback carrying the DEADLINE_EXCEEDED status to handle. When the client deadline expires, the transport cancels the call; the server usually observes context cancellation. Therefore, do not wait only for a DEADLINE_EXCEEDED exception in server code before cleaning up.

Conversely, if the server itself invokes a downstream RPC and the downstream returns DEADLINE_EXCEEDED, the server may receive the corresponding StatusRuntimeException. That is an error from the child call; it differs from the parent RPC being cancelled by the client.

## 4. Server detects deadline expiration and stops work

In a gRPC Java handler, read the current context to check the deadline and cancellation:

~~~java
import io.grpc.Context;
import io.grpc.Deadline;
import java.util.concurrent.TimeUnit;

Context rpcContext = Context.current();
Deadline deadline = rpcContext.getDeadline();

if (rpcContext.isCancelled()
        || (deadline != null
            && deadline.timeRemaining(TimeUnit.NANOSECONDS) <= 0)) {
    // Do not start further work for an expired RPC.
    return;
}
~~~

This check is useful before expensive steps, but it does not replace end-to-end cancellation. If the server is waiting on a blocking query or a background task, you need a cancellable API, a dedicated timeout for that resource, or a mechanism that checks context during processing.

You can register a listener to release resources when the RPC is cancelled:

~~~java
Context rpcContext = Context.current();
rpcContext.addListener(cancelledContext -> {
    downstreamFuture.cancel(true);
    closeTemporaryFile();
    releaseReservationLock();
}, Runnable::run);
~~~

The future and cleanup method names are application-specific examples. Cleanup must be idempotent, must not release resources twice, and should not block the gRPC callback for long. If work has already committed, cancellation does not automatically roll back the transaction.

## 5. Common causes and how to narrow them down

Do not treat every DEADLINE_EXCEEDED by increasing the deadline. First identify where time is being consumed:

| Symptom | Possible Cause | Where to Investigate |
| --- | --- | --- |
| Request reaches server with very little deadline left | Slow client, gateway, queue, or network | Measure pre-call time and transit time |
| Server receives request with sufficient budget but takes long | Business logic, lock contention, thread pool, or DB | Trace each step and measure wait times |
| Parent service times out calling child service | Slow downstream or misconfigured child budget | Track remaining deadline at each hop |
| Timeouts increase under high load | Overload, queue growth, pool exhaustion | Inspect CPU, memory, queue depth, and pool saturation |
| Server finished but client still timed out | Late response/trailers or unstable network | Compare server, client, and trace timestamps |
| Only streaming times out | Stream lives longer than deadline or slow consumer | Check stream age, throughput, and reconnect policy |

A short deadline can expose overload that already existed. Increasing the deadline may reduce the immediate error rate, while simultaneously holding requests, threads, or resources longer and making overload worse.

## 6. DEADLINE_EXCEEDED does not prove the operation did not happen

The client only knows that it **did not receive a result before the deadline**. The server may have executed and committed the operation, while the response was delayed or lost. This is especially dangerous for commands with side effects:

- Creating an order.
- Charging money or issuing a payment instruction.
- Reserving or releasing inventory.
- Sending notifications or creating external tasks.

If the client blindly retries with a new request, the operation may execute twice. Safe handling:

1. Generate a stable **idempotency key** for a business intent.
2. Have the server persist the key together with the processing result atomically alongside the business state change.
3. If the same key and same payload are received again, return the recorded result.
4. If the same key arrives with a different payload, reject it according to clear rules.
5. If status must be known after a timeout, provide a query API by operation ID or idempotency key.

Idempotency does not happen automatically just because a request contains a key field; the server must enforce and persist deduplication state. For long-running tasks, you can use a fast command-acceptance pattern that returns an operation ID, then lets the client query or track status separately.

## 7. Distinguishing from CANCELLED and UNAVAILABLE

These statuses can appear in network and deadline scenarios, yet carry different meanings:

| Status | Core Meaning | How to Handle |
| --- | --- | --- |
| **DEADLINE_EXCEEDED** | Did not complete before the call's deadline | Review budget and task state |
| **CANCELLED** | Call cancelled by client, parent context, or another actor | Stop work and clean up |
| **UNAVAILABLE** | Service or connection temporarily unavailable | Controlled retry if the operation is safe |
| **RESOURCE_EXHAUSTED** | Quota or resource limit exceeded | Shed load, check quota and backpressure |
| **FAILED_PRECONDITION** | Current state does not allow the operation | Fix business preconditions before retrying |

Do not convert every downstream error into DEADLINE_EXCEEDED. Preserve meaningful statuses so clients, telemetry, and retry policies classify failures accurately. If the server enforces its own timeout on a business step and decides to return DEADLINE_EXCEEDED, the error description should indicate which step ran out of budget without leaking sensitive internal details.

## 8. DEADLINE_EXCEEDED in streaming RPCs

A streaming RPC's deadline applies to the **entire call**, not per message:

- **Server streaming:** the client may receive several responses before the stream terminates due to deadline.
- **Client streaming:** the client may have sent part of the requests; the server may have processed part of them before the deadline expires.
- **Bidirectional streaming:** both directions may have exchanged many messages before the call is cancelled.

With server streaming, the client must distinguish normal stream completion via onCompleted from stream failure via onError. If events up to sequence 120 were received before hitting DEADLINE_EXCEEDED, the client can use the sequence/cursor to reconnect from the appropriate position, if the server supports replay.

With client streaming or bidirectional streaming, do not blindly replay all data. Use message IDs, sequences, upload IDs, and deduplication mechanisms to avoid duplicate processing. The server must stop the producer and release subscriptions/queues when the context is cancelled.

## 9. Testing DEADLINE_EXCEEDED

A useful test suite should verify both client outcomes and server behavior:

1. **Server responds within budget:** client receives the response and status OK.
2. **Server processes longer than deadline:** client receives DEADLINE_EXCEEDED.
3. **Server cleanup:** context is cancelled and cancellable resources/tasks are stopped.
4. **Nested calls:** downstream does not continue working after the parent request expires.
5. **Commit before timeout:** retrying with the same idempotency key does not create a second side effect.
6. **Partial streaming:** client receives some messages and then the deadline expires; final state is recognized as an error.

Example checking the status on the client:

~~~java
var stub = PaymentServiceGrpc.newBlockingStub(channel)
    .withDeadlineAfter(50, TimeUnit.MILLISECONDS);

StatusRuntimeException error = assertThrows(
    StatusRuntimeException.class,
    () -> stub.getPayment(request));

assertEquals(
    Status.Code.DEADLINE_EXCEEDED,
    error.getStatus().getCode());
~~~

For reliable tests, simulate slow services using a latch or controllable future instead of relying on long sleeps. In-process tests verify basic gRPC Java behavior; Spring integration tests should start the context to verify service beans, executors, downstream channels, and interceptors under realistic configuration.

## 10. Observing timeouts in production

Monitor by service and full method name:

- Ratio of **DEADLINE_EXCEEDED** to total RPCs.
- p50, p95, and p99 latency relative to the configured deadline.
- Remaining deadline when requests enter the server and before each downstream call.
- Queue, business logic, DB, and network durations.
- Number of tasks still running after cancellation and cleanup duration.
- Retry rate, idempotency hit rate, and errors from mismatched payload/key.
- For streaming: stream age, messages received before error, and reconnect count.

Per-service traces help pinpoint the exact hop consuming the budget. Logs should record status, method, trace ID, and remaining time; do not log credentials or sensitive payloads.

## 11. Summary and self-check

**DEADLINE_EXCEEDED** means the client did not receive a completed result within the allowed time. Clients typically see this status via **StatusRuntimeException** or the **onError** callback. Servers typically see **Context cancellation** and must stop cancellable work. A timeout does not prove a transaction has not committed, so commands with side effects require idempotency and status lookup capabilities.

Self-check:

1. Why can a client receive DEADLINE_EXCEEDED even when the server already committed the operation?
2. What does the server typically observe when the client's deadline expires?
3. How does DEADLINE_EXCEEDED differ from CANCELLED from the client's perspective?
4. Why shouldn't a command be retried with a new idempotency key after a timeout?
5. When a stream times out after several messages, what does the client need a sequence/cursor for?

Handling DEADLINE_EXCEEDED properly requires looking at both sides of the RPC: the client must classify statuses and decide retries safely; the server must detect cancellation, stop appropriate work, and release resources. Combining deadline propagation, idempotency, and telemetry helps Spring gRPC services remain reliable as load or network latency varies.
