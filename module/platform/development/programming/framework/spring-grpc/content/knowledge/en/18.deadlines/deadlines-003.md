# Deadline Propagation Across Nested Calls

A request often passes through multiple services before producing a result: the client calls OrderService, which calls InventoryService, and may then call PricingService or a database. If each layer sets a fresh timeout without accounting for elapsed time, total processing duration can far exceed what the client accepts.

**Deadline propagation** means preserving the parent call's time budget when making nested gRPC calls inside it. In **Spring gRPC** with gRPC Java, deadlines and cancellation state are attached to the current RPC's **io.grpc.Context**. When a service creates an outbound RPC within that context, gRPC can propagate the remaining deadline to the child service. As a result, all layers adhere to a single final limit instead of each layer starting an independent clock.

## 1. Why do nested calls need propagation?

Suppose the client allows the entire order-placement operation to complete within 900 ms. OrderService needs to check inventory, calculate pricing, and persist the order. If each child service were granted a fresh 900 ms timeout, sequential steps could consume nearly 2.7 seconds or more.

~~~mermaid
flowchart TD
    C["Client<br/>total deadline: 900 ms"] --> O["OrderService"]
    O --> I["InventoryService"]
    O --> P["PricingService"]
    O --> D["Order database"]
    I --> R["Result back to OrderService"]
    P --> R
    D --> R
    R --> C
~~~

Sequential budget example:

| Step | Time Used | Approx. Remaining Budget |
| --- | ---: | ---: |
| Client starts | 0 ms | 900 ms |
| Request transit and enter OrderService | 80 ms | 820 ms |
| Check inventory | 220 ms | 600 ms |
| Calculate price | 140 ms | 460 ms |
| Persist order and return response | 300 ms | 160 ms |

These numbers only illustrate budget allocation. The key takeaway: **child services use the parent request's remaining time**, and must not restart the entire budget.

## 2. Deadlines live in the RPC Context

On the client, set the deadline on the stub:

~~~java
GetOrderResponse response = orderStub
    .withDeadlineAfter(900, TimeUnit.MILLISECONDS)
    .getOrder(request);
~~~

When the request arrives at the server, gRPC Java creates a context for the call. Inside the handler, you can read the deadline and remaining time:

~~~java
Context rpcContext = Context.current();
Deadline deadline = rpcContext.getDeadline();

if (deadline != null) {
    long remainingMs =
        deadline.timeRemaining(TimeUnit.MILLISECONDS);
    if (remainingMs <= 0 || rpcContext.isCancelled()) {
        throw Status.DEADLINE_EXCEEDED
            .withDescription("request budget exhausted")
            .asRuntimeException();
    }
}
~~~

Context.current() is the context currently bound to the active callback. getDeadline() may return null if the call has no deadline. For APIs requiring time limits, the client or gateway should set an explicit deadline; the server may also apply an appropriate default policy if the system requires one.

Context also carries cancellation state. When the deadline expires or the client actively cancels the RPC, the context is marked cancelled. Subsequent processing steps should stop if they are no longer useful to the original request.

## 3. gRPC Java automatically propagates deadlines when calling child services

When an outbound gRPC call is made within the current server RPC's context, gRPC Java supports **deadline propagation**: the parent deadline is applied to the child call. Therefore, if OrderService calls InventoryService directly inside the handler running under the request's context, there is no need to manually read the grpc-timeout header and reattach it to metadata.

Example:

~~~java
@Service
public class OrderServiceImpl
        extends OrderServiceGrpc.OrderServiceImplBase {

    private final InventoryServiceGrpc.InventoryServiceBlockingStub inventoryStub;

    public OrderServiceImpl(
            InventoryServiceGrpc.InventoryServiceBlockingStub inventoryStub) {
        this.inventoryStub = inventoryStub;
    }

    @Override
    public void getOrder(
            GetOrderRequest request,
            StreamObserver<GetOrderResponse> responseObserver) {
        try {
            InventoryResponse inventory =
                inventoryStub.checkAvailability(
                    CheckAvailabilityRequest.newBuilder()
                        .setProductId(request.getProductId())
                        .setQuantity(request.getQuantity())
                        .build());

            // Continue business logic with the parent RPC's remaining budget.
            GetOrderResponse response = buildOrderResponse(request, inventory);
            responseObserver.onNext(response);
            responseObserver.onCompleted();
        } catch (StatusRuntimeException ex) {
            responseObserver.onError(ex);
        }
    }
}
~~~

Helper methods like buildOrderResponse(...) and constructor configuration are abbreviated to fit the application. What matters is that inventoryStub.checkAvailability(...) is called within the parent RPC's context; that context's deadline and cancellation continue to govern the child call.

You do not have to create a new ManagedChannel for each nested call. Channels should be managed and reused; stubs can be created/configured from that channel. A deadline is a property of the **call**, not the lifetime of the channel.

## 4. Setting a shorter explicit deadline for a downstream step

Propagation preserves the parent limit, but a child step may need a **shorter** budget. For example, OrderService allocates at most 200 ms to the inventory check so there is still time left for pricing and persisting the order.

~~~java
var boundedInventoryStub = inventoryStub
    .withDeadlineAfter(200, TimeUnit.MILLISECONDS);

InventoryResponse inventory =
    boundedInventoryStub.checkAvailability(request);
~~~

The effective deadline of an outbound call must not exceed the deadline currently in the parent context. In gRPC Java, limits from CallOptions and the context deadline are combined using the earlier limit. Thus, a shorter explicit deadline can tighten the child step; a new longer deadline must not be used to extend the parent request.

If you need to proactively allocate the budget, read the remaining time and reserve headroom for post-downstream processing:

~~~java
Deadline parent = Context.current().getDeadline();
long childLimit = TimeUnit.MILLISECONDS.toNanos(200);
long responseReserve = TimeUnit.MILLISECONDS.toNanos(40);

if (parent != null) {
    long remaining = parent.timeRemaining(TimeUnit.NANOSECONDS);
    childLimit = Math.min(childLimit, remaining - responseReserve);
}

if (childLimit <= 0) {
    throw Status.DEADLINE_EXCEEDED
        .withDescription("insufficient budget for inventory")
        .asRuntimeException();
}

var childStub = inventoryStub.withDeadlineAfter(
    childLimit, TimeUnit.NANOSECONDS);
InventoryResponse inventory = childStub.checkAvailability(request);
~~~

The 40 ms reserve is an example; tune it based on the parent service's latency, serialization, and response transmission time. If there is no parent deadline, the system can still apply the 200 ms local limit.

## 5. Sequential nested calls and parallel calls

### Sequential calls

If the parent service calls InventoryService and then PricingService in sequence, each step consumes part of the budget. The later call automatically receives the remaining time in the context; it is not granted the initial time again.

~~~java
InventoryResponse inventory =
    inventoryStub.checkAvailability(inventoryRequest);

PriceResponse price =
    pricingStub.calculatePrice(priceRequest);
~~~

If the inventory check takes 300 ms out of a 900 ms budget, the pricing step has at most about 600 ms left, not counting headroom for the final response.

### Parallel calls

If two steps are independent, the parent service can call them concurrently. Each child call is still constrained by the parent deadline, but the total duration is typically close to the slowest step rather than the sum of both steps.

~~~java
Context parentContext = Context.current();
Executor contextExecutor =
    parentContext.fixedContextExecutor(applicationExecutor);

CompletableFuture<InventoryResponse> inventoryFuture =
    CompletableFuture.supplyAsync(
        () -> inventoryStub.checkAvailability(inventoryRequest),
        contextExecutor);

CompletableFuture<PriceResponse> priceFuture =
    CompletableFuture.supplyAsync(
        () -> pricingStub.calculatePrice(priceRequest),
        contextExecutor);

InventoryResponse inventory = inventoryFuture.join();
PriceResponse price = priceFuture.join();
~~~

This example uses the same context for both tasks and an application-managed executor. Handle CompletionException, timeouts, and cancellation; when one branch fails or the parent request is cancelled, cancel the remaining branch if it is no longer needed. Do not use an unbounded executor for large fan-outs.

## 6. Preserving Context when switching threads

A common mistake is receiving an RPC on a thread with context, then offloading work to an executor or CompletableFuture without propagating the context. The new thread may lack the parent deadline; outbound RPCs created there no longer receive the expected budget and cancellation.

Capture the context while still inside the gRPC callback:

~~~java
Context captured = Context.current();

applicationExecutor.execute(captured.wrap(() -> {
    // Context.current() inside the task is the parent RPC's context.
    inventoryStub.checkAvailability(
        inventoryRequest,
        inventoryResponseObserver);
}));
~~~

Or use an executor bound to the captured context:

~~~java
Context rpcContext = Context.current();
Executor contextExecutor =
    rpcContext.fixedContextExecutor(applicationExecutor);

contextExecutor.execute(() -> {
    pricingStub.calculatePrice(
        priceRequest,
        priceResponseObserver);
});
~~~

Context.currentContextExecutor(delegate) can also be used when you want an executor bound to the current context at the time of the API call. Using fixedContextExecutor on a captured context makes it explicit which context is being passed across the asynchronous boundary.

Context should live only for the scope of the RPC's work. Do not store a request's context in a singleton or long-lived queue to run work after the RPC finishes. Independent background tasks need their own lifecycle and deadline rather than depending on an old request's expired context.

## 7. Cancellation must also propagate downstream

Deadline expiration is one cause of cancellation; clients can also actively cancel an RPC. When the parent context is cancelled, child calls attached to that context can be cancelled as well. However, custom Java tasks, database queries, or executor work only stop if their APIs support cancellation or the application explicitly checks the signal.

You can register a listener:

~~~java
Context rpcContext = Context.current();
rpcContext.addListener(cancelled -> {
    downstreamFuture.cancel(true);
    releaseTemporaryResources();
}, Runnable::run);
~~~

The names downstreamFuture and releaseTemporaryResources() represent application resources. Cleanup must be idempotent, safe when occurring concurrently with the normal completion path, and must not block the callback for long.

**Cancellation is not rollback.** If a child service already committed data before receiving the cancellation signal, side effects may still exist. For commands that may be retried, use an idempotency key or operation ID to avoid creating duplicate effects.

## 8. Do not manually propagate grpc-timeout via metadata

grpc-timeout is a header belonging to the gRPC protocol. The client library creates the header from the deadline; the server library interprets it into a deadline in the context. When nested calls are made within the right context, gRPC Java handles propagation.

Avoid doing the following:

- Reading the grpc-timeout string from metadata and copying it verbatim to child calls.
- Resetting the timeout to the full initial value in each service.
- Passing deadlines through custom metadata as a business field.
- Dropping context when switching threads and expecting gRPC to somehow know the parent request.

Business metadata such as authorization, tenant ID, request ID, and trace context are separate concerns. They can be passed via metadata/interceptors, whereas deadlines should be managed using gRPC's deadline and context APIs.

## 9. Testing deadline propagation

A test that only verifies the client receives DEADLINE_EXCEEDED does not prove that deadlines propagated properly across nested calls. You need to test the parent service, child service, and executor boundaries:

1. Client sets a short overall deadline and calls the parent service.
2. Parent service reads Context.current().getDeadline() and records remaining time.
3. Parent service calls child service; child service confirms it has a deadline and a budget less than or equal to the parent's budget at receipt time.
4. Test offloading the child call to both a context-aware executor and a non-context-aware executor to detect lost propagation.
5. Make the child service process slower than the deadline; verify the client receives the timeout status and the downstream task is cancelled if supported.
6. Verify cleanup and ensure a post-commit timeout does not create duplicate data on retry.

You can use gRPC in-process transport for service-to-service tests and a controllable executor. Use latches or controllable futures to create repeatable slow scenarios; avoid relying on long Thread.sleep calls. Spring integration tests should start the context to verify actual beans, interceptors, and channels are configured properly.

## 10. Observing budgets across the service chain

Track metrics by trace ID and RPC method:

- Remaining deadline when requests arrive at each service.
- Internal processing time and wait time for each downstream.
- Number of nested calls started with too little budget remaining.
- Rates of DEADLINE_EXCEEDED and CANCELLED at each layer.
- Number of downstream tasks still running after the parent request ends.
- Cleanup duration and retry rate.

If the parent service still has plenty of time but a child service times out frequently, investigate the child service's latency or specific limit. If requests arrive at the parent service already near deadline expiration, the issue may lie in the gateway, queue, or an earlier layer. Span-separated traces help pinpoint exactly where budget is being consumed.

## 11. Summary and self-check

**Deadline propagation across nested calls** maintains a shared time limit from the client through the parent service to child services. gRPC Java attaches deadline/cancellation to Context; outbound RPCs created in that context can inherit the limit. When setting a child deadline, only tighten the budget; when switching threads, propagate context explicitly.

Self-check:

1. Why should each child service not receive the full initial timeout again?
2. How does gRPC Java use Context to propagate deadlines and cancellation?
3. Why can an outbound call created from a thread pool without context lose the parent deadline?
4. When two downstream calls run in parallel, how is the deadline budget accounted for?
5. Why does RPC cancellation not guarantee rolling back an already-committed transaction?

Keeping deadlines consistent across nested calls helps Spring gRPC bound end-to-end processing time, prevent downstream work from continuing after the client has given up, and make timeout behavior observable, testable, and operable.
