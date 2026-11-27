# Verifying Deadline and Cancellation Semantics

In Spring gRPC, deadlines and cancellation define how long an RPC remains useful and how work is stopped when the caller is no longer waiting for the result. A client may receive `DEADLINE_EXCEEDED` even though the server already began processing; a call actively cancelled by the caller typically ends on the client with `CANCELLED`. On the server side, both scenarios must be propagated to the processing logic to stop queries, producers, or downstream RPCs when possible.

This is part of the contract between consumer and provider. If a client sets an 800 ms deadline, the server should not keep processing indefinitely after the budget expires. If a client cancels a stream, the server must stop emitting messages and release resources. Contract tests need to verify the status observed by the client, the cancellation signal on the server side, behavior with downstream calls, and that no side effects are produced after the request has expired.

## 1. Distinguishing Deadline, Timeout, and Cancellation

- **Timeout** is typically a configured duration, e.g., 800 ms.
- **Deadline** is the absolute point in time by which a call must complete. Clients usually configure via a relative timeout; gRPC converts it into a deadline internally.
- **Cancellation** is the signal that the call no longer needs to continue, due to caller-initiated cancellation, deadline expiration, or another cancellation cause.

A deadline is a total budget for the entire call. If a client allocates 800 ms for an RPC, connection time, request transmission, server processing, and response delivery all consume that budget. Do not grant a fresh 800 ms to each downstream step, as total elapsed time could then exceed the caller's deadline.

| Scenario | Typical Client Outcome | Expected Server Behavior |
| --- | --- | --- |
| Server completes within deadline | `OK` | Completes exactly once |
| Deadline expires before response arrives | `DEADLINE_EXCEEDED` | Receives cancellation and stops interruptible work |
| Caller actively cancels | `CANCELLED` | Receives cancellation and stops producer/downstream |
| Request already expired before being processed | Possibly `DEADLINE_EXCEEDED` | May skip running handler or stop early |
| Server completes but response arrives late | Client may still receive `DEADLINE_EXCEEDED` | Do not assume client received the result |

Deadlines/cancellation are not a transaction rollback mechanism. If the server already committed data before the deadline expired while the response arrived late, the client may not know the operation succeeded. Write APIs need an idempotency key or a result lookup mechanism so clients can handle uncertain outcomes.

## 2. Setting Deadlines on the Client

With a generated blocking stub, configure a deadline per call:

```java
CatalogServiceGrpc.CatalogServiceBlockingStub callStub =
        blockingStub.withDeadlineAfter(800, TimeUnit.MILLISECONDS);

try {
    Product product = callStub.getProduct(
            GetProductRequest.newBuilder()
                    .setProductId("P-100")
                    .build());
    handle(product);
} catch (StatusRuntimeException error) {
    Status.Code code = Status.fromThrowable(error).getCode();
    if (code == Status.Code.DEADLINE_EXCEEDED) {
        recordTimeout();
    } else {
        throw error;
    }
}
```

Stubs are immutable with respect to call options: `withDeadlineAfter` returns a new stub with the deadline applied to calls made through that stub. Do not mutate a shared stub with per-request state. You can keep a base stub in a bean and create derived stubs per operation.

Deadlines should match the SLO and caller's budget. If an API has multiple steps, divide the budget deliberately and leave headroom for serialization, network, and response handling. Too short a value causes false timeouts under load; too long a value holds resources for requests that are no longer useful.

With an async stub, deadlines are configured similarly:

```java
CatalogServiceGrpc.CatalogServiceStub callStub =
        asyncStub.withDeadlineAfter(800, TimeUnit.MILLISECONDS);

callStub.getProduct(request, new StreamObserver<Product>() {
    @Override
    public void onNext(Product product) {
        handle(product);
    }

    @Override
    public void onError(Throwable error) {
        Status.Code code = Status.fromThrowable(error).getCode();
        if (code == Status.Code.DEADLINE_EXCEEDED) {
            recordTimeout();
        } else {
            recordFailure(error);
        }
    }

    @Override
    public void onCompleted() {
        complete();
    }
});
```

In the async API, terminal errors are delivered through `onError`. Do not assume callbacks run on the thread that invoked the stub or on a fixed thread.

## 3. Reading Deadlines and Cancellation on the Server

The server can read the deadline from the current gRPC `Context`:

```java
@Override
public void getProduct(
        GetProductRequest request,
        StreamObserver<Product> observer) {
    Context context = Context.current();
    Deadline deadline = context.getDeadline();

    if (context.isCancelled()) {
        return;
    }

    if (deadline != null
            && deadline.timeRemaining(TimeUnit.MILLISECONDS) <= 0) {
        return;
    }

    Product product = catalog.find(request.getProductId());
    observer.onNext(product);
    observer.onCompleted();
}
```

This example shows how to read the context, but checking `isCancelled` once is insufficient for long-running work. Cancellation can occur immediately after the check. Long-running work should check cancellation at safe points, use downstream APIs that support cancel/timeout, and avoid holding threads in non-cancellable blocking operations.

`Context` can register a listener to receive cancellation notifications:

```java
Context callContext = Context.current();

callContext.addListener(
        cancelledContext -> stopWorkForCurrentCall(),
        cancellationExecutor);
```

The listener is invoked when the context is cancelled or the deadline expires. Keep listeners short, thread-safe, and free of blocking I/O in the callback. If registering a listener in a component that outlives the RPC, remove the listener when the call completes to avoid retaining unnecessary references.

A deadline does not guarantee the server automatically interrupts arbitrary Java code. The server must cooperate: propagate cancellation to repositories/downstream clients, cancel scheduled tasks, stop loops, and stop enqueueing messages. A JDBC query or blocking HTTP call only stops if the driver/client API supports timeout/cancel and the application invokes that mechanism properly.

## 4. Distinguishing Client Status from Server Cancellation Signal

When a deadline expires, the client typically sees `DEADLINE_EXCEEDED`. When the caller actively cancels, the client typically sees `CANCELLED`. The server typically observes the call context becoming cancelled; the server does not necessarily receive the same status the client sees and should not attempt to send a new status after the client has closed the call.

Points to test separately:

- Client timeout/cancel is reflected as the right status on the client.
- Server cancellation listener is triggered.
- Producer or downstream operation receives cancellation.
- Server does not send additional responses after terminal state.
- If a side effect already committed before cancellation, the client has a way to determine the outcome or retry safely.

Do not map every cancellation to an `INTERNAL` error. Cancellation is often a normal lifecycle event when a client leaves a page, disconnects, or a deadline expires. Logs and metrics should distinguish deadline expiration, caller cancellation, and business errors.

## 5. Deadline Propagation Across Downstream RPCs

One service often calls another. If the incoming RPC has a deadline, downstream calls must use the remaining budget. gRPC Java uses `Context` to propagate the deadline when creating outgoing calls within the current context. When switching to another executor, you must propagate `Context`; otherwise, downstream calls can lose the deadline and run longer than the caller allows.

Example dispatching work to an executor with a captured context:

```java
Context parentContext = Context.current();

applicationExecutor.execute(parentContext.wrap(() -> {
    ProductDetails details = inventoryStub
            .getDetails(request)
            .getDetails();

    sendResponse(details);
}));
```

When code runs inside the wrapped context, outgoing gRPC calls can inherit the parent call's deadline. If setting a deadline explicitly for a downstream call, that deadline must be shorter than or equal to the parent's remaining budget; do not reset the full initial timeout at each hop.

Not all database/HTTP libraries understand gRPC `Context` automatically. Pass remaining time into dependency timeouts or use the corresponding cancellation integration. If a dependency does not support cancellation, set explicit time bounds and ensure late results do not keep causing side effects.

## 6. Cancellation in Server-Streaming and Bidirectional Streaming

With server streaming, the server typically emits responses via `ServerCallStreamObserver`. You can register a cancellation handler and check status before emitting further:

```java
@Override
public void watchProduct(
        WatchProductRequest request,
        StreamObserver<ProductEvent> observer) {
    if (!(observer instanceof ServerCallStreamObserver<?> raw)) {
        throw new IllegalStateException("Expected server stream observer");
    }

    @SuppressWarnings("unchecked")
    ServerCallStreamObserver<ProductEvent> serverObserver =
            (ServerCallStreamObserver<ProductEvent>) raw;

    AtomicBoolean stopped = new AtomicBoolean();
    AtomicReference<Subscription> subscriptionRef = new AtomicReference<>();

    serverObserver.setOnCancelHandler(() -> {
        stopped.set(true);
        Subscription current = subscriptionRef.getAndSet(null);
        if (current != null) {
            current.cancel();
        }
    });

    Subscription created = eventSource.subscribe(event -> {
        if (stopped.get() || serverObserver.isCancelled()) {
            return;
        }
        serverObserver.onNext(toProto(event));
    });
    subscriptionRef.set(created);
    if (stopped.get() && subscriptionRef.compareAndSet(created, null)) {
        created.cancel();
    }
}
```

This is an illustrative skeleton; `Subscription` represents the application's event source handle. The subscription holder handles the race where cancellation arrives before `subscribe` returns: cancellation sets `stopped`, and the check after `subscribe` cancels the newly created handle. If callbacks from the event source run on multiple threads, serialize writes to the observer. The cancellation handler must stop the subscription and release queues.

With client streaming or bidi, the client also needs to cancel the request stream when it is no longer interested in the result. Use `ClientCallStreamObserver` from `ClientResponseObserver.beforeStart` to retain the ability to cancel the call. Do not merely stop reading responses while leaving the producer sending requests indefinitely.

## 7. Testing Deadlines in a Controlled Way

Deadline tests should prove both sides: the client receives `DEADLINE_EXCEEDED` and the server receives cancellation. Avoid using `Thread.sleep` as the primary synchronization mechanism. Use one latch to confirm the handler started and another latch to confirm cancellation:

```java
final class SlowCatalogService
        extends CatalogServiceGrpc.CatalogServiceImplBase {
    final CountDownLatch entered = new CountDownLatch(1);
    final CountDownLatch cancelled = new CountDownLatch(1);
    final CountDownLatch release = new CountDownLatch(1);
    final ExecutorService worker = Executors.newSingleThreadExecutor();

    @Override
    public void getProduct(
            GetProductRequest request,
            StreamObserver<Product> observer) {
        Context callContext = Context.current();
        entered.countDown();

        callContext.addListener(
                ignored -> cancelled.countDown(),
                Runnable::run);

        worker.execute(() -> {
            try {
                release.await();
                if (!callContext.isCancelled()) {
                    observer.onNext(Product.newBuilder()
                            .setProductId(request.getProductId())
                            .build());
                    observer.onCompleted();
                }
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
        });
    }
}
```

The test calls the service over an in-process channel with a finite deadline:

```java
@Test
void deadlineExpiresAndCancelsServerWork() throws Exception {
    SlowCatalogService service = new SlowCatalogService();
    // server/channel initialized via InProcessServerBuilder
    // and InProcessChannelBuilder in the fixture.
    var shortDeadlineStub = stub.withDeadlineAfter(2, TimeUnit.SECONDS);

    Future<Status.Code> result = testExecutor.submit(() -> {
        StatusRuntimeException error = assertThrows(
                StatusRuntimeException.class,
                () -> shortDeadlineStub.getProduct(request));
        return Status.fromThrowable(error).getCode();
    });

    assertTrue(service.entered.await(1, TimeUnit.SECONDS));
    assertEquals(Status.Code.DEADLINE_EXCEEDED,
            result.get(3, TimeUnit.SECONDS));
    assertTrue(service.cancelled.await(1, TimeUnit.SECONDS));

    service.release.countDown();
}
```

In real tests, the fixture must always release latches and shut down executors/servers/channels in `finally` or teardown. The 2-second deadline in the example gives enough window to confirm the handler entered; tune for the CI environment and use bounded awaits. Do not use a test deadline so short that the call expires before the server receives the request.

This test does not prove a specific database query can be cancelled. To verify that, replace the fixture worker with a test dependency that has a cancellation hook and assert the hook was called.

## 8. Testing Caller Cancellation Separately from Deadlines

Caller cancellation is an active action, so tests should explicitly cancel the call instead of waiting on a timer. With an async stub, `ClientResponseObserver` allows obtaining `ClientCallStreamObserver` and calling `cancel`:

```java
final class CancellableWatch
        implements ClientResponseObserver<WatchRequest, ProductEvent> {
    final CountDownLatch terminal = new CountDownLatch(1);
    volatile ClientCallStreamObserver<WatchRequest> call;
    volatile Status.Code terminalCode;

    @Override
    public void beforeStart(
            ClientCallStreamObserver<WatchRequest> requestStream) {
        this.call = requestStream;
    }

    @Override
    public void onNext(ProductEvent event) {
        // Receive event if the call has not been cancelled.
    }

    @Override
    public void onError(Throwable error) {
        terminalCode = Status.fromThrowable(error).getCode();
        terminal.countDown();
    }

    @Override
    public void onCompleted() {
        terminalCode = Status.Code.OK;
        terminal.countDown();
    }
}
```

In the test, invoke the async stub with the observer, wait on a separate latch in the server-side fixture confirming the handler started, then call `observer.call.cancel("test cancellation", null)`. Verify the client receives `CANCELLED` and the server cancellation handler is invoked. Do not rely on the first event deterministically arriving before cancel.

The deadline test and explicit cancel test must be independent. Deadline expiration is due to the time budget; explicit cancellation is a caller decision. Both must stop server-side work, yet client statuses differ.

## 9. Side Effects, Retries, and Race Conditions

Deadlines/cancellations can happen concurrently with committing or sending responses. Therefore the contract must answer:

- If the client hits a deadline while the server already committed, how does the client look up the outcome?
- Can retries create duplicate records?
- Is the idempotency key preserved across retries?
- Does the server check cancellation before deferrable side effects?
- Can a late callback send a response after the call already ended?

For write operations, generate a stable idempotency key per business intent and store results so retries can return the previous outcome. Do not generate a new key on every retry if the goal is deduplicating the same operation.

Status `DEADLINE_EXCEEDED` does not prove the server did nothing. Status `CANCELLED` is not a transaction rollback either. If a commit completed, the server must ensure data consistency; the client must handle unknown states via idempotent retries or querying operation results.

For streaming, terminal signals may only be sent once. Once cancellation occurs, stop `onNext`, stop the producer, and drop queued messages according to policy. Do not call `onCompleted` after `onError` or keep writing after a terminal state.

## 10. Deadline and Cancellation Contract Checklist

- [ ] Every RPC has a default deadline or explicit caller policy.
- [ ] Deadlines are treated as a total budget, never reset at each downstream hop.
- [ ] Client tests verify `DEADLINE_EXCEEDED` when the limit is exceeded.
- [ ] Client explicit-cancel tests verify `CANCELLED`.
- [ ] Server reads `Context` deadlines and registers cancellation listeners.
- [ ] `Context` is propagated when switching to another executor.
- [ ] Downstream gRPC/HTTP/database calls have appropriate timeouts/cancellations.
- [ ] Streaming producers stop when `ServerCallStreamObserver` is cancelled.
- [ ] No messages or terminal signals are emitted after the call has ended.
- [ ] Tests use latches/barriers and finite timeouts instead of sleep for synchronization.
- [ ] Side effects have an idempotency strategy when the client does not know the final outcome.
- [ ] Channels, servers, executors, listeners, and subscriptions are released in teardown.
- [ ] Metrics distinguish deadline expiry, caller cancellation, and business errors.

**Self-Check**

**Question 1.** How does a deadline differ from a timeout?

*Answer:* A timeout is a configured duration; a deadline is the point in time by which the call must finish. Multiple steps in an RPC share a single deadline budget.

**Question 2.** Which status does a client typically receive when a deadline expires vs. when the caller actively cancels?

*Answer:* Deadline expiration typically yields `DEADLINE_EXCEEDED`; active caller cancellation typically yields `CANCELLED`. The server typically observes both via call context cancellation.

**Question 3.** Why must the server check cancellation even after gRPC closes the call?

*Answer:* Closing the call does not automatically stop arbitrary Java tasks, database queries, or producers. The application must propagate cancellation to dependencies and stop interruptible work.

**Question 4.** Why should you not grant the full timeout again for each downstream RPC?

*Answer:* Doing so can cause total elapsed time to exceed the caller's budget. Downstream calls must inherit the deadline or use the parent's remaining time.

**Question 5.** Does `DEADLINE_EXCEEDED` prove the operation has not committed?

*Answer:* No. The server may have committed while the response arrived late. Write operations need an idempotency key or result lookup mechanism for safe retries.

Deadline and cancellation contract tests must verify status on the client along with the stop signal on the server. When deadlines flow throughout the call chain, cancellations reach dependencies and streaming producers, and side effects are protected by idempotency, Spring gRPC can release resources on time and keep behavior consistent when clients stop waiting.
