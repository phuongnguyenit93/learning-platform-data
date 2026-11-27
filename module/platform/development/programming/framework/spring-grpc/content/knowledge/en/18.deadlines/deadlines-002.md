# Deadlines Propagate from Client to Server

A gRPC call should not wait indefinitely for a result. A **deadline** defines the latest point in time at which the client accepts the call completing. When a client sends an RPC, gRPC propagates the time budget along with the call so the server knows how much time remains and whether to continue processing or stop work. If the server calls additional downstream services, the deadline and cancellation signal must continue to govern those calls as well.

In **Spring gRPC**, Java applications typically read the current RPC's deadline through **io.grpc.Context**. gRPC Java uses the call's context when creating outbound RPCs, allowing deadlines and cancellation to flow along the processing chain. Understanding this mechanism helps prevent child services from continuing to work longer than the time the client allowed.

## 1. Deadline flow from client to server

The client sets a deadline on the stub. When gRPC sends the call over HTTP/2, the deadline is transmitted in protocol metadata via the **grpc-timeout** header as the remaining duration. The server receives the call and interprets this duration as a deadline in the RPC's context.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant T as gRPC transport
    participant S as Spring gRPC server
    C->>C: Set 800 ms deadline
    C->>T: Send RPC + grpc-timeout
    T->>S: Forward request and remaining timeout
    S->>S: Create Context with deadline
    S->>S: Process within remaining budget
    alt Completed on time
        S-->>C: Response + grpc-status OK
    else Deadline expired
        T-->>C: DEADLINE_EXCEEDED
        T-->>S: Cancel RPC / Context cancelled
    end
~~~

For example, the client grants 800 ms. If the request takes 100 ms in transit and the server receives it after about 100 ms, the server only has roughly 700 ms remaining, before accounting for processing and response transmission time. **The server does not receive a fresh 800 ms budget** when the request arrives.

gRPC transmits the remaining duration rather than relying on the absolute clocks of both machines. This reduces clock skew issues between client and server. The grpc-timeout header is a protocol detail managed by gRPC; applications should not manually create or copy this header as business metadata.

## 2. Setting deadlines on the client

With gRPC Java, use **withDeadlineAfter** to create a stub with a time limit:

~~~java
import java.util.concurrent.TimeUnit;

GetOrderRequest request = GetOrderRequest.newBuilder()
    .setOrderId("order-2048")
    .build();

GetOrderResponse response = orderStub
    .withDeadlineAfter(800, TimeUnit.MILLISECONDS)
    .getOrder(request);
~~~

The deadline applies to the **entire RPC**: waiting for resources, transmitting the request, processing on the server, and waiting for the response. It is not a separate server-only processing time. Each call needs a budget tailored to business requirements; do not set an overly long timeout for every method.

If the client does not set a deadline, the call may wait longer than expected when the server or network encounters issues. You should set explicit deadlines for calls that affect user experience or SLAs.

## 3. Server receives the deadline via Context

When gRPC Java dispatches an RPC to a service, the call's context is attached to the callback execution thread. The server can read the deadline and remaining time:

~~~java
import io.grpc.Context;
import io.grpc.Deadline;
import java.util.concurrent.TimeUnit;

Context rpcContext = Context.current();
Deadline deadline = rpcContext.getDeadline();

if (deadline != null) {
    long remainingMs =
        deadline.timeRemaining(TimeUnit.MILLISECONDS);

    if (remainingMs <= 0 || rpcContext.isCancelled()) {
        // Do not start additional work.
        return;
    }
}
~~~

If deadline is null, the client or upstream caller did not provide an explicit deadline. For APIs requiring bounded response times, the server can enforce a default policy at the client or gateway layer. Do not assume that a call without a deadline will automatically terminate after a specific duration.

Context also carries cancellation state. When the deadline expires or the client actively cancels the RPC, the context is marked cancelled. The server should check this state before starting expensive processing steps and propagate the stop signal to cancellable tasks.

## 4. Deadlines continue to govern downstream calls

Suppose the client calls OrderService, and OrderService calls InventoryService. If the initial deadline is 800 ms and OrderService has already used 250 ms, the inventory check call has at most around 550 ms remaining, while also needing to reserve part of the budget for OrderService to finish and return the response.

~~~mermaid
flowchart LR
    A["Client<br/>800 ms"] --> B["OrderService<br/>uses 250 ms"]
    B --> C["InventoryService<br/>remaining budget"]
    C --> D["Database<br/>uses remaining share"]
    D --> E["Response before deadline"]
~~~

In gRPC Java, outbound calls created within the current context can inherit the parent RPC's deadline and cancellation. When code is running within the request context, there is no need to manually read and copy grpc-timeout into metadata. You can set a shorter explicit deadline for a downstream step; the effective budget should not exceed the parent deadline.

Example limiting the inventory call to at most 200 ms:

~~~java
var inventoryCall = inventoryStub
    .withDeadlineAfter(200, TimeUnit.MILLISECONDS);

InventoryResponse inventory =
    inventoryCall.checkAvailability(inventoryRequest);
~~~

The 200 ms limit is the downstream step's own budget. If the parent request's remaining deadline is shorter, the parent context must still govern the call; setting a longer timeout must not be used to extend the original overall request.

In production code, reserve headroom for the remaining processing steps:

~~~java
Deadline parentDeadline = Context.current().getDeadline();
long childBudgetNanos = TimeUnit.MILLISECONDS.toNanos(200);
long responseReserveNanos = TimeUnit.MILLISECONDS.toNanos(30);

if (parentDeadline != null) {
    long remaining = parentDeadline.timeRemaining(TimeUnit.NANOSECONDS);
    childBudgetNanos = Math.min(
        childBudgetNanos,
        remaining - responseReserveNanos);
}

if (childBudgetNanos <= 0) {
    throw Status.DEADLINE_EXCEEDED
        .withDescription("not enough time for inventory lookup")
        .asRuntimeException();
}

var boundedStub = inventoryStub.withDeadlineAfter(
    childBudgetNanos, TimeUnit.NANOSECONDS);
InventoryResponse result =
    boundedStub.checkAvailability(inventoryRequest);
~~~

The 30 ms reserve is only an example. Choose it based on OrderService's actual latency and serialization/response overhead. When there is no parent deadline, the example uses a local budget of 200 ms.

## 5. Context can be lost when switching threads

Deadline propagation relies on **Context.current()**. When processing synchronously inside a gRPC callback, the current RPC's context is bound to the thread. However, if the application offloads work to an executor or thread pool, the context does not automatically appear on arbitrary threads.

If an outbound RPC is created on a thread without the parent context, that call may fail to inherit the deadline/cancellation as expected. Capture the current context and propagate it across asynchronous boundaries:

~~~java
Context captured = Context.current();

executor.execute(captured.wrap(() -> {
    // Context.current() inside the task is the captured context.
    inventoryStub.checkAvailability(
        inventoryRequest,
        inventoryResponseObserver);
}));
~~~

Or create an executor that automatically attaches the context at submission time:

~~~java
Executor contextAwareExecutor =
    Context.currentContextExecutor(applicationExecutor);

contextAwareExecutor.execute(() -> {
    inventoryStub.checkAvailability(
        inventoryRequest,
        inventoryResponseObserver);
});
~~~

Context can be captured to pass across callbacks, but do not retain it longer than the RPC lifecycle. When the parent request is cancelled, child tasks must observe cancellation and stop; do not enqueue work from an expired request onto a background queue to be processed as if it were still valid.

With Spring, application-managed executors still need to be configured explicitly. Do not assume every asynchronous task or library callback automatically propagates the gRPC Context unless you have verified the integration mechanism.

## 6. Cancellation accompanies deadlines

Deadline expiration is one cause of cancellation, though the client can also actively cancel an RPC. When the context is cancelled, the server should:

- Stop starting new downstream steps.
- Cancel futures, tasks, or subscriptions if the API supports it.
- Stop producers emitting data for streaming RPCs.
- Release queues, temporary files, and held resources.
- Avoid sending additional responses after the RPC has ended.

You can register a listener to react to cancellation:

~~~java
Context rpcContext = Context.current();
rpcContext.addListener(cancelled -> {
    downstreamFuture.cancel(true);
    releaseTemporaryResources();
}, Runnable::run);
~~~

The names downstreamFuture and releaseTemporaryResources() represent application resources. Cleanup must be safe when invoked concurrently with the normal completion path; avoid double-releasing or letting cleanup callbacks block for long.

**Cancellation is not rollback.** If a transaction already committed before the deadline expired, the written data remains. A deadline only limits wait time and emits a stop signal; atomicity and side-effect recovery must be handled at the business layer.

## 7. grpc-timeout is not business metadata

The **grpc-timeout** header belongs to the gRPC protocol. The gRPC client generates this value from the deadline; the server reads it and converts it into the RPC's deadline. Applications usually do not need to add this header manually via Metadata or interceptors.

Business metadata such as authorization, tenant ID, request ID, and trace context are separate concerns. They can be passed via metadata/interceptors according to system policy, but they do not replace deadlines. Nor should you copy an old timeout value to a downstream request, because time has already elapsed; gRPC needs to propagate the remaining budget.

When inspecting network traces, you may see grpc-timeout in request headers. The value may use different time units according to protocol rules. Do not assume it is always in milliseconds or compare a raw header string directly against a server clock.

## 8. Deadline propagation with streaming RPCs

For server streaming, client streaming, and bidirectional streaming, the deadline still applies to the **entire RPC**:

- **Server streaming:** bounds the entire duration of the subscription and receiving responses.
- **Client streaming:** bounds the time spent sending requests along with waiting for the final result.
- **Bidirectional streaming:** bounds the entire two-way exchange session.

Sending more messages does not automatically extend the deadline. If a subscription needs to live for a long time, design per-session lifetimes, reconnection mechanisms, and a cursor/sequence to resume. When the deadline expires, the server must stop the producer and release the subscription.

If the server opens a downstream stream while handling a parent stream, the parent RPC's context must be propagated to that task. If a child stream outlives the parent deadline because it was detached from the context, it can continue consuming resources after the client has given up.

## 9. Testing deadline propagation across services

Tests should verify the client deadline, the server context, and downstream calls:

1. Client sets a short deadline; server reads the deadline in Context.
2. Server calls downstream; the child call does not exceed the parent call's remaining budget.
3. Server offloads work to an executor; the context is captured so deadline/cancellation remain present.
4. Deadline expires while downstream is running; the child task is cancelled if supported.
5. RPC is cancelled after commit; retries do not create duplicate side effects.
6. Streaming hits deadline; producer and subscription are cleaned up.

Example test verifying the client receives the status when the server processes longer than the budget:

~~~java
var stub = OrderServiceGrpc.newBlockingStub(channel)
    .withDeadlineAfter(100, TimeUnit.MILLISECONDS);

StatusRuntimeException failure = assertThrows(
    StatusRuntimeException.class,
    () -> stub.getOrder(request));

assertEquals(
    Status.Code.DEADLINE_EXCEEDED,
    failure.getStatus().getCode());
~~~

This test only proves that the client receives the deadline-exceeded status. To prove propagation, instrument both parent and child services, record the remaining deadline at each point, and verify the context is cancelled after the client expires. Prefer latches or controllable futures over long Thread.sleep calls to reduce test flakiness.

## 10. Observability and error handling

Track the following metrics per RPC method and service:

- Remaining deadline when the request reaches the server.
- Processing time at each layer and downstream wait time.
- Rates of **DEADLINE_EXCEEDED** and **CANCELLED**.
- Number of downstream tasks still running after the parent RPC is cancelled.
- Cleanup duration after cancellation.
- Retry rate and duplicate side effects prevented by idempotency.

If the server frequently receives requests with very little deadline remaining, latency may have occurred before reaching the service. If the parent deadline still has plenty of headroom yet downstream times out frequently, investigate the child service or its specific timeout. Do not just increase timeouts; find the layer consuming the budget.

The client receiving **DEADLINE_EXCEEDED** does not prove the server has not executed the operation. For commands with side effects, use an idempotency key or operation ID to check/return the previous result when the client resends the same request.

## 11. Summary and self-check

**Deadlines propagate from client to server** through the gRPC protocol mechanism, typically represented by the **grpc-timeout** header. The server receives the deadline in **Context.current()**; outbound RPCs created within that context can inherit the deadline and cancellation. When switching threads, propagate the context explicitly so the request's time budget is not lost.

Self-check:

1. Why does the server not receive a full new deadline budget when a request arrives?
2. How does grpc-timeout differ from metadata such as authorization or tenant ID?
3. What can happen if the server offloads processing to an executor without propagating Context?
4. Why must the parent deadline govern downstream calls even when the child stub sets its own timeout?
5. Does the client receiving **DEADLINE_EXCEEDED** prove that the transaction has not committed?

Propagating deadlines properly across the call chain helps Spring gRPC avoid doing work that is no longer useful, bound resources, and keep response times within the budget requested by the client.
