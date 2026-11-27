# DEADLINE_EXCEEDED Due to Slow Downstream

In **SPRING_GRPC**, an RPC typically calls one or more dependencies such as inventory, pricing, a database, or a REST service. If a downstream dependency responds slowly, total processing time can exceed the deadline set by the client. The client then receives `DEADLINE_EXCEEDED`; the server also receives cancellation status in Context and needs to stop whatever work can still be stopped safely.

This error does not simply mean the downstream is "hung". An RPC can exceed its deadline due to waiting in a worker queue, waiting on a connection pool, multiple retries, sequential calls to multiple dependencies, or response mapping/serialization time. To fix it properly, track the budget across the entire request, propagate remaining time down to dependencies, configure dedicated I/O timeouts, and avoid retries that exhaust the budget.

## 1. A Deadline Differs from a Single Dependency Timeout

A **deadline** is the final point in time by which the entire RPC is allowed to complete. A **timeout** usually limits how long a specific operation waits, such as a database query or an HTTP response.

For example, the client sets a 900 ms deadline for `GetOrder`. The server needs to call inventory and pricing, then aggregate the results:

| Stage | Expected Budget |
| --- | ---: |
| Queue and dispatch | 50 ms |
| Inventory downstream | 300 ms |
| Pricing downstream | 250 ms |
| Mapping and business processing | 150 ms |
| Serialize and send response | 100 ms |
| Total | 850 ms |

The remainder provides headroom for variance. If the server gives each downstream a 900 ms timeout, two sequential calls could stretch to nearly 1.8 seconds, exceeding the overall deadline.

A gRPC deadline is represented using monotonic time, avoiding direct dependence on system clock adjustments. When propagating to a dependency, use the remaining time at the moment you prepare the call rather than reusing the client's initial budget.

## 2. The Client Must Set an RPC Deadline

If the client does not set a deadline, the RPC may wait too long depending on dependency and transport behavior. Set a deadline according to business requirements:

```java
CatalogServiceGrpc.CatalogServiceBlockingStub client =
        CatalogServiceGrpc.newBlockingStub(channel)
                .withDeadlineAfter(900, TimeUnit.MILLISECONDS);

GetOrderReply reply = client.getOrder(
        GetOrderRequest.newBuilder()
                .setOrderId("order-42")
                .build());
```

Choose the deadline based on target latency and operation SLA. Do not set a single overly short value for all RPCs; cache reads and multi-service aggregations have different profiles. Also do not set an overly long deadline just to reduce visible errors, because expired-value requests still occupy threads, connections, and downstream resources.

If the client is an intermediary service, the inbound RPC's deadline must be treated as the overall upper bound. Never start a downstream operation with a budget larger than the parent request's remaining time.

## 3. Read the Remaining Deadline on the Server

Inside a server handler, the current gRPC Context may contain the inbound call's deadline:

```java
Context rpcContext = Context.current();
Deadline deadline = rpcContext.getDeadline();

if (rpcContext.isCancelled()) {
    throw Status.CANCELLED
            .withDescription("RPC is no longer active")
            .asRuntimeException();
}

long remainingNanos = deadline == null
        ? TimeUnit.MILLISECONDS.toNanos(900)
        : deadline.timeRemaining(TimeUnit.NANOSECONDS);
```

If there is no inbound deadline, the service should still apply an internal maximum operation budget. Do not treat `null` as permission for downstream calls to wait forever.

Leave time for post-downstream steps. For instance, reserve 60 ms for mapping and sending the response:

```java
long responseReserveNanos =
        TimeUnit.MILLISECONDS.toNanos(60);

long downstreamBudgetNanos =
        Math.min(
                TimeUnit.MILLISECONDS.toNanos(500),
                remainingNanos - responseReserveNanos);

if (downstreamBudgetNanos <= 0) {
    throw Status.DEADLINE_EXCEEDED
            .withDescription("Insufficient time to call dependency")
            .asRuntimeException();
}
```

A dependency's budget is the smaller of the dependency's own cap and the remaining inbound time minus the reserve. Do not round remaining time up to a timeout larger than the actual deadline.

Encapsulate the calculation in a helper so adapters apply the same rule. When a request has no deadline, the helper still applies the maximum dependency time as an internal cap:

```java
public long forDownstream(
        Context context,
        Duration maxDependencyTime,
        Duration responseReserve) {

    Deadline deadline = context.getDeadline();
    long remaining = deadline == null
            ? maxDependencyTime.plus(responseReserve).toNanos()
            : deadline.timeRemaining(TimeUnit.NANOSECONDS);

    return Math.min(
            maxDependencyTime.toNanos(),
            remaining - responseReserve.toNanos());
}
```

## 4. Propagate Remaining Deadline to gRPC Downstreams

A service calling a downstream via a blocking stub can apply the computed budget:

```java
long budgetNanos = deadlineBudget.forDownstream(
        Context.current(),
        Duration.ofMillis(500),
        Duration.ofMillis(60));

if (budgetNanos <= 0) {
    throw Status.DEADLINE_EXCEEDED
            .withDescription("Insufficient downstream budget")
            .asRuntimeException();
}

InventoryReply inventory = inventoryStub
        .withDeadlineAfter(budgetNanos, TimeUnit.NANOSECONDS)
        .getStock(
                InventoryRequest.newBuilder()
                        .setSku(order.getSku())
                        .build());
```

`deadlineBudget` is an application helper performing the calculation from the previous section. Use `withDeadlineAfter` immediately before the call so the downstream receives a limit matching the time remaining at that moment.

Do not assume every client stub or custom executor automatically carries over the inbound RPC's exact deadline. In grpc-java, Context has a propagation mechanism, yet adapters should verify the behavior of their version and how stubs/call options are constructed. Setting the deadline explicitly at the outbound boundary makes the budget easy to verify and avoids relying on whether Context is attached to the right thread.

If offloading calls to an executor, capture and wrap Context before submitting. Otherwise, the worker may lose the request's deadline/cancellation context:

```java
Context rpcContext = Context.current();

executor.execute(rpcContext.wrap(() -> {
    callInventoryWithRemainingBudget(rpcContext);
}));
```

The executor must be bounded; queue wait also consumes deadline. If a task only starts when the budget is nearly gone, rejecting early can be better than calling downstream and almost certainly timing out.

## 5. One Request Calling Multiple Downstreams

With sequential calls, each step must recompute remaining time after the previous step completes:

```java
InventoryReply stock = callInventoryWithBudget(
        order.getSku(), currentBudget());

PricingReply price = callPricingWithBudget(
        order.getSku(), currentBudget());

return orderMapper.toReply(order, stock, price);
```

Do not compute two budgets once at the start of the request and reuse the original value for both calls. Time spent by inventory reduces the remaining budget for pricing.

If two downstreams are independent and can be called in parallel, use bounded-concurrency fan-out. Each call receives a budget not exceeding the remaining deadline, while the parent only completes once required results arrive or policy permits partial results. Cancel remaining calls once results are no longer needed or the parent is cancelled.

Do not spawn an unbounded thread per downstream. Use a bounded executor/bulkhead and set a limit on queue wait. With multiple dependencies, total time is not just network latency; it also includes scheduling, connection acquisition, retries, and aggregation.

## 6. Configure Timeouts per Dependency Type

A gRPC deadline does not automatically configure timeouts for JDBC, HTTP clients, or SDKs. Each dependency needs its own appropriate timeouts:

| Dependency | Timeouts/Cancellation to Configure |
| --- | --- |
| gRPC downstream | `withDeadlineAfter` or deadline based on remaining budget |
| HTTP client | Connect timeout, response/read timeout, and request cancellation |
| JDBC | Query/statement timeout, network timeout, and driver cancellation support |
| Redis/cache client | Command timeout and connection acquisition limit |
| Object storage/SDK | API call timeout, attempt timeout, and abort/cancel if supported |
| Executor | Queue capacity, queue wait limit, and rejection policy |

Do not set the HTTP read timeout equal to the entire deadline if further steps remain after HTTP. Likewise, an overly long JDBC query timeout can hold connections even after the client has received `DEADLINE_EXCEEDED`.

Some JDBC APIs only accept timeouts in whole seconds. Do not arbitrarily round up if the remaining budget is under one second; use database/driver timeouts with finer resolution or another operation limit to avoid exceeding the deadline. Always verify actual driver behavior.

## 7. Retries Can Exhaust the Deadline Faster

Retries help with transient failures, but every attempt and backoff consumes the same end-to-end budget. Do not grant a fresh full timeout to each attempt.

For example, with 400 ms of budget remaining:
- First attempt takes 180 ms and receives a transient error.
- Backoff takes 50 ms.
- Second attempt has only about 170 ms left, before even counting the response reserve.

If there is not enough time for a meaningful attempt, stop retrying and return an appropriate status. Retries should:
- Apply only to errors identified as transient.
- Include backoff and jitter.
- Respect the remaining deadline.
- Cap the number of attempts.
- Only retry idempotent operations or operations with an idempotency key.
- Avoid retrying an operation that may have already committed while the response arrived late.

`DEADLINE_EXCEEDED` does not prove the server never executed the operation. A write may have committed while the response failed to reach the client in time. Retrying a write without idempotency protection can cause duplicate side effects.

## 8. Cancellation When the Deadline Expires

When the inbound deadline expires, the server Context is cancelled. Handlers and application work should check for cancellation at safe checkpoints:

```java
Context context = Context.current();

if (context.isCancelled()) {
    return;
}

InventoryReply result = inventoryStub
        .withDeadlineAfter(
                remainingBudgetNanos(context),
                TimeUnit.NANOSECONDS)
        .getStock(request);

if (context.isCancelled()) {
    return;
}

observer.onNext(mapper.toProto(result));
observer.onCompleted();
```

This snippet illustrates a synchronous flow. If a handler runs asynchronously, wrap Context when submitting and ensure workers do not emit a response after the call has been cancelled.

Cancellation does not automatically interrupt all I/O. A JDBC driver, socket, or SDK may keep running without its own timeout/cancel API. Register cancellation handlers to request worker termination, close cursors/streams, and release resources. `Future.cancel(true)` only sends an interrupt; verify whether the dependency actually responds to interrupts.

Do not send `onError(DEADLINE_EXCEEDED)` from the server after the transport has already closed the call due to deadline. The client already received the status from the gRPC runtime; the server needs to clean up and emit appropriate telemetry.

## 9. Distinguish Downstream Slowness from Overall Deadline

Not every `DEADLINE_EXCEEDED` is caused by a slow downstream. It can be broken down into:

- **Queue delay**: request waiting for a worker or connection pool before calling downstream.
- **Dependency latency**: downstream taking too long or failing to respond.
- **Retry amplification**: multiple attempts and backoffs consuming the budget.
- **Fan-out tail latency**: one slow dependency holding back the entire response.
- **Local processing**: mapping, lock contention, or CPU saturation.
- **Response path**: server finishes near the deadline, yet serialization/network delivers it late to the client.

A downstream call expiring under its own deadline is an important signal, yet you need to record the stage and elapsed time to verify whether it is the root cause. Do not blame the downstream service from the final status alone.

## 10. Observe Budget and Latency per Stage

To pinpoint the bottleneck, record comparable measurements:

| Measurement | Purpose |
| --- | --- |
| Remaining inbound deadline on receipt | Know how much budget the caller has left |
| Queue wait and executor active/queue depth | Detect worker saturation |
| Connection pool acquisition time | Detect connection exhaustion |
| Downstream latency by service/method | Find slow dependencies |
| Retry count and backoff duration | Measure retry amplification |
| Local processing/serialization time | Detect in-service overhead |
| RPC final status and total duration | Compare deadline against actual latency |

Use trace spans for each downstream call to see which stage consumes the budget. You can record remaining budget at call start and status at completion, without logging tokens or sensitive payloads.

Metric labels should stay bounded to service, method, dependency, and status code. Do not put order IDs, user IDs, or trace IDs into metric labels due to high cardinality. Use trace/log correlation to look up a specific request.

## 11. Test Deadline Propagation with a Slow Downstream

Use two in-process servers to verify the full budget path: an Inventory server hosting `slowDownstream`; an Order server hosting `OrderService`, which calls Inventory using `withDeadlineAfter` via the helper above. Have Inventory wait on a latch and set a short deadline on the Order client:

```java
CatalogServiceGrpc.CatalogServiceBlockingStub client =
        CatalogServiceGrpc.newBlockingStub(channel)
                .withDeadlineAfter(150, TimeUnit.MILLISECONDS);

StatusRuntimeException error = assertThrows(
        StatusRuntimeException.class,
        () -> client.getOrder(
                GetOrderRequest.newBuilder()
                        .setOrderId("order-42")
                        .build()));

assertEquals(
        Status.Code.DEADLINE_EXCEEDED,
        Status.fromThrowable(error).getCode());
assertTrue(slowDownstream.started.await(2, TimeUnit.SECONDS));
assertTrue(slowDownstream.cancelled.await(2, TimeUnit.SECONDS));
assertTrue(slowDownstream.cleaned.await(2, TimeUnit.SECONDS));
```

`slowDownstream` is a test service with `started`, `cancelled`, and `cleaned` latches; when the downstream call is cancelled/times out, the handler records cancellation, releases the worker, and closes resources. `OrderService` must recompute the remaining budget and set a deadline on the Inventory call; if you only set a deadline on the Order client without applying a budget on the outbound call, the test does not prove propagation. In a complete test, verify worker cleanup and close both servers, both channels, and the executor in `finally`.

Use wait timeouts generous enough for CI while keeping an upper bound. Do not use `Thread.sleep` to simulate synchronization, because it does not prove the downstream received the request or ran cancellation.

## 12. Test the Remaining Budget Calculation Helper

Extract the budget calculation into a pure Java helper to test boundary cases:

```java
long downstreamBudgetNanos(
        long remainingNanos,
        Duration maxDependencyTime,
        Duration responseReserve) {

    return Math.min(
            maxDependencyTime.toNanos(),
            remainingNanos - responseReserve.toNanos());
}
```

Tests should cover:
- Remaining budget larger than dependency cap → uses dependency cap.
- Small remaining budget → uses remaining time after reserve.
- Remaining budget equal to reserve → result is zero.
- Remaining budget smaller than reserve → result is negative and adapter skips calling downstream.
- Missing or unbounded deadline → applies internal maximum operation budget.

Ensure the adapter checks `budgetNanos <= 0` before invoking the stub. Do not pass negative or zero durations to a downstream call and do not rely on the client library to interpret that case on its own.

## 13. Common Mistakes

| Mistake | Consequence | Resolution |
| --- | --- | --- |
| Giving every downstream a timeout equal to total deadline | Total time exceeds deadline | Compute remaining budget for each call |
| Setting no deadline on the client | RPC can wait indefinitely | Set deadline according to SLA |
| Unbounded queues | Requests expire before running | Bounded executor and queue wait limit |
| Retries granting a full timeout again | Retries run past the budget | Share the end-to-end budget |
| JDBC/HTTP lacking dedicated timeouts | Workers and connections held after RPC | Configure dependency timeout/cancel |
| Failing to propagate cancellation | Downstream keeps running after caller gives up | Context, cancel handler, and cancel APIs |
| Rounding timeouts upward | Dependency runs longer than remaining budget | Keep exact units or enforce strict caps |
| Retrying non-idempotent writes | Duplicate side effects when response arrives late | Idempotency keys and retry policy |
| Looking only at the final status | Misattributing blame to downstream | Trace each stage and queue/connection wait |

## 14. Practice Exercises

1. Set a deadline on the `GetOrder` client and record total RPC duration.
2. On the server, read `Context.current().getDeadline()` and compute remaining time.
3. Write a helper that subtracts response reserve and enforces a per-dependency maximum cap.
4. Call Inventory using a stub with `withDeadlineAfter` based on remaining budget.
5. Call Pricing afterward and recompute the budget after Inventory completes.
6. Set JDBC query timeout and HTTP response timeout from the same budget.
7. Simulate a slow downstream using an in-process server and latches.
8. Verify the client receives `DEADLINE_EXCEEDED`, the server receives cancellation, and the worker cleans up.
9. Test retry with backoff on an idempotent operation; verify retries stop when budget runs out.
10. Add traces/metrics for queue wait, downstream latency, retry count, and remaining deadline.

### Remember

**`DEADLINE_EXCEEDED` signals that the end-to-end RPC exceeded its allotted time; a slow downstream is only one possible cause.** Read the remaining deadline on the server, keep a response reserve, apply the smaller remaining budget to each downstream call, configure dedicated JDBC/HTTP timeouts, and bound retries. When the deadline expires, propagate cancellation and clean up workers/resources. Use per-stage traces and in-process tests with latches to pinpoint where the budget is spent.

## References

- [gRPC — Deadlines](https://grpc.io/docs/guides/deadlines/)
- [gRPC — Cancellation](https://grpc.io/docs/guides/cancellation/)
- [gRPC Java — Deadline](https://grpc.github.io/grpc-java/javadoc/io/grpc/Deadline.html)
- [gRPC Java — Context](https://grpc.github.io/grpc-java/javadoc/io/grpc/Context.html)
- [gRPC Java — AbstractStub](https://grpc.github.io/grpc-java/javadoc/io/grpc/stub/AbstractStub.html)
- [Spring Boot — Task Execution and Scheduling](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html)
