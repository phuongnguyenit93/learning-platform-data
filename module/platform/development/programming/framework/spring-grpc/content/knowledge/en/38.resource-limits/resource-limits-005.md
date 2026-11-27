# Mandatory Deadlines

## Learning Objectives

After this lesson, you can:

- Explain a deadline as a finite time budget for an RPC.
- Distinguish a deadline from socket timeouts, retry policies, and server-only processing time.
- Set mandatory deadlines on the client using grpc-java stubs and CallOptions.
- Check deadlines on the server, reject calls without a deadline, and enforce maximum limits.
- Propagate the remaining budget to databases, HTTP clients, and downstream gRPC calls.
- Handle cancellation, cleanup, and race conditions when a deadline expires.
- Design deadlines for unary and streaming RPCs, including long-lived streams requiring reconnect/resume.
- Test missing deadlines, overly short deadlines, expiration, and retries.

## 1. A deadline is the time budget of an RPC

In **SPRING_GRPC**, an RPC may wait on the network, queues, databases, downstream services, and business processing. If the caller does not bound time, a stuck request can hold threads, connections, buffers, or subscriptions longer than genuinely needed.

**Deadline** defines the final point in time until which the caller is still willing to wait for the result of an RPC. It is the total time budget for the call, not just the wait time for a single socket or processing step. When the deadline expires, gRPC cancels the call and reports the appropriate status; the server should stop cancelable work and release resources.

A deadline differs from a relative timeout in that a deadline represents an ending point in time. Clients usually set a relative timeout via **withDeadlineAfter**; grpc-java converts it into an internal deadline and transmits the remaining time over the wire. Propagating remaining timeout avoids relying on absolute clock synchronization across machines.

A useful deadline must be applied across the entire processing chain:

~~~mermaid
flowchart TD
    A["Client sets finite deadline"] --> B["gRPC sends remaining timeout"]
    B --> C["Server checks mandatory deadline"]
    C --> D{"Valid deadline with time left?"}
    D -- "Missing" --> E["Reject call"]
    D -- "Expired" --> F["DEADLINE_EXCEEDED"]
    D -- "Yes" --> G["Process with remaining budget"]
    G --> H["Database / downstream gRPC / HTTP"]
    H --> I{"Budget left?"}
    I -- "Yes" --> J["Return response"]
    I -- "No" --> K["Cancel, clean up, terminate"]
~~~

Without a deadline, a slow service can keep consuming resources even after the caller has given up. Mandatory deadlines establish a clear boundary for both client and server.

## 2. What does a mandatory deadline mean?

A mandatory deadline is an operational contract: every RPC permitted to be processed must have a finite time limit. The rule must be enforced on both sides:

- **Client:** every stub/call must be created with a deadline or timeout appropriate to the method.
- **Server:** inspect the received deadline; reject calls missing a deadline per policy.
- **Server policy:** enforce a maximum duration ceiling so callers cannot request an overly long-lived call.
- **Application:** propagate the remaining budget to databases, HTTP clients, and downstream RPCs.
- **Streaming:** define a maximum lifetime or per-session deadline; long-lived streams need a reconnect/resume mechanism.

Setting a default timeout only in the client SDK is not enough, because another client can call the server directly. Checking only on the server is not enough either, because official clients can still wait too long if deadlines are not configured. Both sides must enforce the contract together.

Do not use arbitrary metadata like x-timeout-ms as a replacement for gRPC deadlines. The gRPC runtime already has its own deadline mechanism; clients should use the CallOptions/stub API so the library transmits timeouts properly. Do not manually craft or overwrite the grpc-timeout header.

## 3. Setting deadlines on the client with grpc-java

grpc-java generated stubs support **withDeadlineAfter**. This is the common way to set a timeout for a call:

~~~java
import java.util.concurrent.TimeUnit;

OrderServiceGrpc.OrderServiceBlockingStub stub =
        OrderServiceGrpc.newBlockingStub(channel);

GetOrderResponse response = stub
        .withDeadlineAfter(800, TimeUnit.MILLISECONDS)
        .getOrder(request);
~~~

800 ms is just an example. Choose the timeout based on the method's latency budget, network time, queueing, and dependencies. A cache-read method may need a small budget; a method aggregating multiple services may need a larger one. Do not set a very long timeout for every method to mask abnormal latency.

With async or streaming stubs, the deadline is similarly set on the stub before invoking the method:

~~~java
OrderServiceGrpc.OrderServiceStub asyncStub =
        OrderServiceGrpc.newStub(channel)
                .withDeadlineAfter(5, TimeUnit.SECONDS);

asyncStub.watchOrders(request, responseObserver);
~~~

A call's deadline covers the entire lifetime of a streaming RPC. For long-lived streams, a finite deadline means the stream will terminate when the budget runs out; client design must know how to open a new stream and resume from a cursor.

### 3.1. Centralizing deadlines in a client factory

In large applications, you should not rely on every developer remembering to call withDeadlineAfter. You can provide a factory or per-method wrapper:

~~~java
public final class GrpcStubFactory {

    private final ManagedChannel channel;

    public GrpcStubFactory(ManagedChannel channel) {
        this.channel = channel;
    }

    public OrderServiceGrpc.OrderServiceBlockingStub orderStub() {
        return OrderServiceGrpc.newBlockingStub(channel)
                .withDeadlineAfter(800, TimeUnit.MILLISECONDS);
    }

    public ReportServiceGrpc.ReportServiceBlockingStub reportStub() {
        return ReportServiceGrpc.newBlockingStub(channel)
                .withDeadlineAfter(4, TimeUnit.SECONDS);
    }
}
~~~

This is a simple example illustrating per-method policies. You can use centralized configuration, typed clients, or application interceptors/wrappers to reduce omissions. However, ensure every stub creation path goes through the factory and has tests for each RPC group.

With Spring, register channel/stub factories as beans using the mechanism of the starter in use. Avoid creating a new ManagedChannel per request; channels should be reused for the application lifecycle and shut down when the context closes.

## 4. Server checks for mandatory deadlines

On a grpc-java server, the active deadline can be read from **Context.current().getDeadline()**. If there is no deadline, the server can reject the call immediately in an interceptor:

~~~java
import io.grpc.Context;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

public final class RequiredDeadlineInterceptor
        implements ServerInterceptor {

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        if (Context.current().getDeadline() == null) {
            call.close(
                    Status.FAILED_PRECONDITION
                            .withDescription("A finite RPC deadline is required"),
                    new Metadata());
            return new ServerCall.Listener<ReqT>() {};
        }

        return next.startCall(call, headers);
    }
}
~~~

FAILED_PRECONDITION here indicates the call does not satisfy the API's operational precondition. A system may choose a different status per its error contract, but it must be consistent and explicitly tested. Do not return UNAUTHENTICATED: a missing deadline does not mean invalid credentials.

The interceptor must run before the handler creates subscriptions or side effects. Register it in the server interceptor chain managed by the Spring gRPC starter; test the actual application configuration to ensure every protected service passes through the interceptor.

A deadline may already have expired by the time the server receives the call. Therefore, in addition to checking null, verify that the deadline still has remaining validity before starting expensive work.

## 5. Enforcing a maximum deadline on the server

Requiring a deadline is not enough: callers could specify an excessively long timeout. The server should enforce a maximum allowed duration per method or workload group.

Example of checking the remaining time:

~~~java
Deadline deadline = Context.current().getDeadline();

if (deadline == null) {
    rejectMissingDeadline(call);
    return new ServerCall.Listener<ReqT>() {};
}

long remainingNanos =
        deadline.timeRemaining(TimeUnit.NANOSECONDS);

if (remainingNanos <= 0) {
    call.close(
            Status.DEADLINE_EXCEEDED
                    .withDescription("RPC deadline has expired"),
            new Metadata());
    return new ServerCall.Listener<ReqT>() {};
}

long maxAllowedNanos =
        TimeUnit.SECONDS.toNanos(5);

if (remainingNanos > maxAllowedNanos) {
    call.close(
            Status.INVALID_ARGUMENT
                    .withDescription("Requested deadline exceeds the method limit"),
            new Metadata());
    return new ServerCall.Listener<ReqT>() {};
}
~~~

This is an example of a strict policy rejecting timeouts larger than allowed. Another option is applying a server-side cap via a child Context deadline and executing the call within that Context. Such an implementation must ensure listener callbacks still run in the child Context and cancellation propagates properly. Do not merely check and ignore long deadlines if the goal is to genuinely bound execution time.

Different thresholds can be used:

| RPC group | Example maximum duration | Notes |
| --- | ---: | --- |
| Small read | 1 second | Fast response, few dependencies |
| Write command | 3 seconds | Includes transaction and downstream |
| Aggregation report | 8 seconds | Multiple dependencies, explicit budget |
| Streaming session | 2 minutes | Reconnect/resume before expiration |

These numbers are illustrative only. Choose based on SLOs, latency distributions, retry policies, and resource costs.

## 6. Splitting the deadline budget across processing steps

If the client grants 2 seconds, the server should not spend the entire 2 seconds on the database before calling another service. Split the budget across queueing, validation, database, downstreams, and response serialization.

Example budget:

| Phase | Illustrative budget |
| --- | ---: |
| Network/queue and dispatch | 150 ms |
| Authentication/authorization and validation | 100 ms |
| Database | 500 ms |
| Downstream gRPC/HTTP | 700 ms |
| Mapping and returning response | 150 ms |
| Headroom | 400 ms |

The total budget must fit within the remaining deadline. This is not a rigid schedule; steps can run in parallel or take less time. The goal is to prevent a single dependency from consuming the entire time of the call.

Before each expensive operation, check the remaining time. If the remaining budget is insufficient to start useful work, fail early rather than creating work guaranteed not to finish.

Do not subtract wall-clock time manually to make deadline decisions. Use **Deadline.timeRemaining(...)** or the dependency's timeout API; grpc-java Deadline is designed to measure remaining time safely across system clock changes.

## 7. Propagating deadlines to downstream gRPC

A server often calls other services downstream. The inbound call's deadline must bound the total time of the entire chain, preventing downstreams from running longer than the caller is waiting.

Read the current deadline:

~~~java
Deadline inboundDeadline = Context.current().getDeadline();

if (inboundDeadline == null) {
    throw Status.FAILED_PRECONDITION
            .withDescription("A finite RPC deadline is required")
            .asRuntimeException();
}
~~~

When creating an outbound stub, pass the same deadline or a shorter child deadline if time must be reserved for mapping/response:

~~~java
long remainingNanos =
        inboundDeadline.timeRemaining(TimeUnit.NANOSECONDS);

long reserveNanos = TimeUnit.MILLISECONDS.toNanos(100);
long downstreamBudget = remainingNanos - reserveNanos;

if (downstreamBudget <= 0) {
    throw Status.DEADLINE_EXCEEDED
            .withDescription("No time budget remains for downstream call")
            .asRuntimeException();
}

InventoryServiceGrpc.InventoryServiceBlockingStub downstream =
        inventoryStub.withDeadlineAfter(
                downstreamBudget,
                TimeUnit.NANOSECONDS);
~~~

This example reserves 100 ms for the remaining processing. In systems with multiple dependencies, allocate budget by critical path and concurrency. Do not give each downstream the full remaining time if calls are sequential; total time could exceed the inbound operation's deadline.

Some frameworks/runtimes have deadline propagation mechanisms via Context. Even so, verify the behavior of your version and stub creation pattern in the application. Explicitly setting deadlines on outbound calls makes the contract clear and avoids accidentally calling downstreams without timeouts.

## 8. Databases and HTTP clients also need corresponding timeouts

A gRPC deadline does not automatically configure timeouts for JDBC, JPA, HTTP clients, or message brokers. If a server thread runs a database query without a timeout, the RPC may be canceled while the query keeps running.

Map the remaining budget to dependency timeouts:

- JDBC statement/query timeout.
- Framework transaction timeout.
- HTTP connect timeout and response/read timeout.
- Timeouts for Redis, brokers, or object storage clients.
- Timeouts for lock acquisition and semaphore waits.

Some APIs accept timeouts in whole milliseconds or seconds, whereas gRPC Deadline has higher precision. Round carefully and never set a dependency timeout longer than the remaining time. Reserve headroom for cleanup and response.

If a library does not support true cancellation or timeouts, understand that limitation. Sending an interrupt or canceling a future does not guarantee the external database/server has stopped processing. Monitor running queries and use driver cancel mechanisms whenever possible.

## 9. Deadlines and cancellation must go together

When a deadline expires, the gRPC call is canceled. The server should observe cancellation and stop cancelable tasks:

~~~java
Context context = Context.current();

context.addListener(
        cancelledContext -> {
            cancelDatabaseQuery();
            cancelDownstreamFuture();
            closeSubscription();
        },
        cleanupExecutor);
~~~

The listener must be registered on the RPC's Context. Cleanup must be idempotent because cancellation may occur right around when the handler finishes or a dependency returns an error. Do not run slow cleanup on the transport event loop; use an appropriate executor and bound its queue.

For streaming, cancellation must stop producers and subscriptions, releasing buffers and concurrency permits. Do not continue reading from a broker or database only to discard responses after the client disconnects the stream.

Deadlines do not roll back committed transactions. If an operation already produced side effects before timing out, the client may receive DEADLINE_EXCEEDED without knowing whether the server committed. For commands with side effects, you need idempotency keys, operation status, or reconciliation so clients can query outcomes.

## 10. Deadlines for streaming RPCs

A streaming call has a deadline covering the entire lifetime of the stream; it does not reset after each message. If the client sets a 30-second deadline, the stream ends when the 30-second budget expires even if the last message was just sent.

For short streams like a batch upload, an overall deadline fits well. For long-lived subscriptions, avoid creating infinite streams without deadlines. Use a finite maximum lifetime, after which the client reconnects and resumes with a cursor/sequence.

Reconnect design needs:

1. Server returns a confirmed cursor or sequence.
2. Client saves checkpoints safely.
3. When the deadline expires, the client opens a new stream with a new deadline.
4. Server re-validates credentials and authorization.
5. Client resumes from the checkpoint; server deduplicates if messages may be replayed.
6. Old subscription is cleaned up before or immediately when the stream terminates.

Do not use heartbeats to extend deadlines indefinitely. Heartbeats only help detect peer/connection liveness; they do not replace maximum stream lifetimes and resource policies.

## 11. Retries must not create unbounded new deadlines

Retries are part of the same operation and must stay within the total time budget. If every retry gets a brand-new full timeout, total elapsed time can exceed caller expectations.

For example, the caller has 2 seconds. The first attempt takes 700 ms, backoff takes 100 ms, leaving the second attempt only about 1.2 seconds minus headroom. Do not reset to 2 seconds on every attempt.

Principles:

- Retry policies must respect the remaining deadline.
- Backoff must be bounded with jitter.
- Do not retry INVALID_ARGUMENT, PERMISSION_DENIED, or calls rejected for missing deadlines.
- For DEADLINE_EXCEEDED, retry only if budget remains and the operation is safe.
- Mutations require idempotency keys or deduplication.
- Do not use wait-for-ready to wait indefinitely; it must still fall within the deadline.
- Do not start a new retry if the remaining budget is insufficient for a useful attempt.

If the server already committed yet the response did not arrive in time, retrying can cause duplicate side effects. Clients need an operation ID or idempotency key to query status or avoid re-execution.

## 12. Choosing statuses for deadlines and related errors

| Scenario | Suggested status | Meaning |
| --- | --- | --- |
| Client omits mandatory deadline per contract | FAILED_PRECONDITION | Call missing operational precondition |
| Deadline already expired before processing | DEADLINE_EXCEEDED | No time budget remains |
| Requested deadline exceeds maximum policy | INVALID_ARGUMENT or contract-specific status | Invalid timing parameter |
| Dependency times out while inbound deadline remains | Map from dependency error and remaining budget | Distinguish downstream error from overall deadline |
| Client actively cancels | CANCELLED | Caller no longer needs result |
| Dependency unavailable while time remains | UNAVAILABLE | Infrastructure error, conditional retry |

Clients may observe DEADLINE_EXCEEDED even when the server completed side effects but the response was delayed or lost. Do not treat this status as proof that a transaction rolled back.

Do not confuse missing deadlines with UNAUTHENTICATED or PERMISSION_DENIED. Authentication and authorization are security decisions; a deadline is a timing condition of the call.

## 13. Observing deadlines in production

Monitor by method and RPC type:

- Rejection rate for calls missing a deadline.
- Remaining time when the server receives the call.
- Latency p50/p95/p99 and DEADLINE_EXCEEDED rate.
- Processing time per dependency.
- Number of downstream calls canceled when inbound deadlines expire.
- Stream lifetimes, reconnect/resume rates, and cancellations.
- Retry counts, backoff times, and attempts skipped due to exhausted budget.
- Queries/tasks still running after the RPC has ended.

Do not put absolute deadlines or high-cardinality request IDs into metric labels. Record remaining budgets in buckets and trace spans to pinpoint where time is spent. Never log tokens or sensitive payloads.

If deadline expiration rates rise, separate queue delay, application processing, downstream latency, and network time. Mechanically increasing timeouts may only make requests hold resources longer and raise concurrent call counts.

## 14. Testing mandatory deadlines

Tests must verify both the client contract and server enforcement:

| Scenario | Expected result |
| --- | --- |
| Client sets valid deadline | RPC is processed within budget |
| Client sets no deadline | Server rejects before handler runs |
| Deadline already expired | DEADLINE_EXCEEDED or appropriate cancellation |
| Deadline exceeds maximum policy | Rejected or capped per policy |
| Slow downstream | Outbound call bounded by remaining budget |
| Slow database query | Query times out/cancels per budget |
| Client cancels | Server stops work and cleans up |
| Streaming deadline expires | Stream terminates, subscriptions/permits released |
| Multi-attempt retry | Total duration does not exceed operation deadline |
| Mutation response times out | Idempotency/status query prevents duplicate side effects |

An important test is sending a call without a deadline using a raw generated stub, bypassing the official factory. That proves the server interceptor protects even against non-compliant SDK clients. Another test sets a very short deadline and uses a latch to hold the handler; verify cancellation is observed and cleanup executes.

In Spring application integration tests, start the server using the real starter configuration and verify the mandatory interceptor is registered for every protected service. In-process tests that hand-assemble an interceptor chain do not prove production bean wiring is correct.

## 15. Common implementation pitfalls

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| Only setting timeouts in client SDK | Other clients can call without deadlines | Server checks mandatory deadlines |
| Only checking deadline is non-null | Callers can request overly long durations | Enforce maximum duration |
| Creating a fresh timeout for each retry | Total operation stretches indefinitely | Share overall deadline budget |
| Not propagating budget to database/HTTP | Dependencies keep running after RPC expires | Map remaining time to timeouts/cancellation |
| Treating DEADLINE_EXCEEDED as rollback | Retries create duplicate side effects | Idempotency keys and operation status |
| Using heartbeats to keep streams infinite | Holds subscriptions and permits forever | Maximum lifetime and resume cursors |
| Running cleanup on the event loop | Blocks transport when cleanup is slow | Use a bounded cleanup executor |
| Testing only through client factory | Misses non-compliant callers | Raw-stub integration tests |
| Configuring interceptor in tests but forgetting Spring | Production does not enforce | Spring application integration tests |

## 16. Hands-on exercises and self-check questions

### Hands-on exercises

1. Create a client stub factory with separate deadlines for GetOrder, CancelOrder, and GenerateReport.
2. Write a server interceptor rejecting RPCs without a deadline and checking maximum duration.
3. Register the interceptor via the Spring gRPC configuration in use.
4. In the application service, propagate remaining budget to downstream gRPC and HTTP/database clients.
5. Add a cancellation listener to stop futures, queries, or subscriptions.
6. For server-streaming, set a maximum lifetime and implement a resume cursor on deadline expiration.
7. Define a total retry budget, backoff, and idempotency for commands with side effects.
8. Write integration tests for missing deadline, expired deadline, overlong deadline, slow dependency, cancellation, and retry.

### Self-check questions

**1. How does a deadline differ from a timeout?**  
A deadline is an absolute ending point in time; a timeout is a relative duration used to compute a deadline.

**2. Why must deadlines be mandatory on the server?**  
Because client SDKs can be bypassed; the server must protect resources against callers that omit timeouts.

**3. Why is checking that the deadline is non-null not enough?**  
Callers can send overly long deadlines; the server needs a per-method maximum duration.

**4. Does a gRPC deadline automatically stop JDBC or HTTP requests?**  
No. The application must propagate the remaining budget to the dependency's timeout/cancellation API.

**5. Should retries receive the full initial timeout again?**  
No. Attempts must share the operation's overall deadline budget.

**6. Does deadline expiration guarantee transaction rollback?**  
No. Side effects may already have committed; idempotency and status lookup mechanisms are needed.

**7. How should long-lived streaming handle deadlines?**  
Use a finite lifetime, cursors/sequences, and reconnect/resume instead of infinite streams.

**8. Which status is used when a client omits a mandatory deadline?**  
Per contract; for example, this lesson uses FAILED_PRECONDITION to indicate a missing operational precondition.

## Summary

**Mandatory deadlines** mean every RPC must have a finite time budget, set by the client and enforced by the server. Clients use grpc-java stubs/CallOptions to set deadlines; the server inspects Context.current().getDeadline(), rejects calls missing a deadline, and enforces maximum durations. Remaining time must be propagated to databases, HTTP, and downstream gRPC calls; cancellation must stop work and clean up resources. Retries must share the total budget, while long-lived streams need maximum lifetimes paired with cursors/resume. Test raw clients without deadlines, expired deadlines, slow dependencies, and Spring wiring to prove the policy is enforced on the actual server.
