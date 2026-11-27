# Propagating cancellation to downstream RPCs

A gRPC server often calls other services to fulfill a request. For example, an Order service calls Inventory to check stock and Payment to authorize payment. If the client cancels the RPC to Order, downstream calls may keep running unless the application propagates the stop signal to them. In that case, the system wastes resources on an abandoned request and may even create side effects whose results the caller is no longer waiting for.

**Propagating cancellation to downstream RPCs** connects the lifecycle of child calls to the parent call: when the parent RPC is cancelled, active child RPCs are asked to stop; when the parent deadline is running out, child RPCs only receive the remaining time budget. This lesson belongs to the **Cancellation** chapter of the **SPRING_GRPC** module, focusing on gRPC Java in Spring applications, async stubs, Context, deadline propagation, race conditions, cleanup, and testing.

## 1. Parent RPC and downstream RPC relationship

Suppose a client calls OrderService.GetSummary. The server in turn calls InventoryService.GetStock and PricingService.GetPrice. The two child calls exist to serve the parent call:

~~~mermaid
flowchart TD
    C[Client] -->|GetSummary| P[OrderService - parent RPC]
    P -->|GetStock| I[InventoryService - child RPC]
    P -->|GetPrice| R[PricingService - child RPC]
    C -.->|Cancel / disconnect| P
    P -.->|Propagate cancellation| I
    P -.->|Propagate cancellation| R
~~~

When the parent is cancelled, the server needs to:

1. Stop initiating new downstream calls.
2. Request active child calls to cancel.
3. Ignore late results arriving after the parent has ended.
4. Release listeners, call handles, and resources belonging to the request.

Do not close ManagedChannel to cancel a child RPC. A channel may be shared by many other requests; destroying the channel will affect unrelated calls. Cancel the specific child ClientCall instead.

## 2. Cancellation and deadline are two complementary signals

Cancellation indicates the parent caller no longer needs the result. Deadline limits the remaining time allowed for processing. If the parent's deadline expires, the parent call is cancelled; if the caller actively cancels earlier, the parent can be cancelled while deadline time remains.

| Signal from parent | Action for child RPC |
| --- | --- |
| Explicit cancellation | Cancel child call immediately upon receiving the signal. |
| Parent deadline still valid | Child may only use the parent's remaining time. |
| Parent deadline expired | Do not create new children; cancel running children. |
| Parent completes normally | Let necessary children finish; clean up listeners and handles. |
| Parent ends due to business error | Apply the operation's policy; do not automatically treat all errors as cancellation. |

Setting a fresh longer deadline on each child can push total duration past the original request budget. Conversely, propagating only the deadline without propagating explicit cancellation can leave children running until the deadline expires even though the caller left early.

## 3. Obtaining the parent Context in the server handler

In gRPC Java, Context.current() inside a server handler is the current RPC's context. Context provides the deadline and cancellation status:

~~~java
Context parentContext = Context.current();
Deadline parentDeadline = parentContext.getDeadline();

if (parentContext.isCancelled()) {
    // Parent has already ended; do not initiate downstream work.
    return;
}

if (parentDeadline != null && parentDeadline.isExpired()) {
    // Parent's budget has expired.
    return;
}
~~~

isCancelled() does not indicate a single cause. Explicit cancel, deadline expiry, and certain transport situations can all cancel the context. getDeadline() and isExpired() help tell whether the deadline has expired at check time.

gRPC Java has built-in Context propagation along call paths where the current context remains attached. When creating a child call within the parent's context scope, deadline/cancellation may be inherited by the library's mechanism. However, when code switches to an executor, detaches context, or manages call handles across a separate lifecycle, you must ensure the context is captured/propagated and children are stopped on time. The next example demonstrates explicit wiring via call handles to control and test child lifecycles.

## 4. Wiring parent cancellation to an async child RPC

With an async stub, ClientResponseObserver.beforeStart(...) provides the ClientCallStreamObserver representing the child call. Retain this handle so parent cancellation can call cancel(...).

Example of Order service calling Inventory:

~~~java
public void getSummary(
        SummaryRequest request,
        StreamObserver<SummaryReply> responseObserver) {

    Context parentContext = Context.current();
    AtomicBoolean parentCancelled =
            new AtomicBoolean(parentContext.isCancelled());
    AtomicBoolean cancelSent = new AtomicBoolean();
    AtomicBoolean cleaned = new AtomicBoolean();
    AtomicReference<ClientCallStreamObserver<StockRequest>> childCall =
            new AtomicReference<>();
    AtomicReference<StockReply> stockReply = new AtomicReference<>();

    Context.CancellationListener listener = ignored -> {
        parentCancelled.set(true);
        ClientCallStreamObserver<StockRequest> call = childCall.get();
        if (call != null && cancelSent.compareAndSet(false, true)) {
            call.cancel("Parent RPC cancelled", null);
        }
    };

    Runnable cleanup = () -> {
        if (cleaned.compareAndSet(false, true)) {
            parentContext.removeListener(listener);
            childCall.set(null);
        }
    };

    parentContext.addListener(listener, Runnable::run);

    if (parentCancelled.get() || parentContext.isCancelled()) {
        cleanup.run();
        return;
    }

    Deadline deadline = parentContext.getDeadline();
    InventoryGrpc.InventoryStub childStub = inventoryStub;
    if (deadline != null) {
        long remainingNanos =
                deadline.timeRemaining(TimeUnit.NANOSECONDS);
        if (remainingNanos <= 0) {
            cleanup.run();
            if (!parentContext.isCancelled()) {
                responseObserver.onError(Status.DEADLINE_EXCEEDED
                        .withDescription("Parent RPC time budget exhausted")
                        .asRuntimeException());
            }
            return;
        }
        childStub = childStub.withDeadlineAfter(
                remainingNanos, TimeUnit.NANOSECONDS);
    }

    ClientResponseObserver<StockRequest, StockReply> childObserver =
            new ClientResponseObserver<>() {
                @Override
                public void beforeStart(
                        ClientCallStreamObserver<StockRequest> call) {
                    childCall.set(call);
                    // Parent may be cancelled before the child handle appears.
                    if (parentCancelled.get() || parentContext.isCancelled()) {
                        if (cancelSent.compareAndSet(false, true)) {
                            call.cancel("Parent RPC already cancelled", null);
                        }
                    }
                }

                @Override
                public void onNext(StockReply reply) {
                    if (!parentCancelled.get()
                            && !parentContext.isCancelled()) {
                        stockReply.set(reply);
                    }
                }

                @Override
                public void onError(Throwable failure) {
                    cleanup.run();
                    if (!parentCancelled.get()
                            && !parentContext.isCancelled()) {
                        responseObserver.onError(mapChildFailure(failure));
                    }
                }

                @Override
                public void onCompleted() {
                    cleanup.run();
                    if (parentCancelled.get()
                            || parentContext.isCancelled()) {
                        return;
                    }

                    StockReply stock = stockReply.get();
                    if (stock == null) {
                        responseObserver.onError(Status.INTERNAL
                                .withDescription("Inventory returned no result")
                                .asRuntimeException());
                        return;
                    }

                    responseObserver.onNext(toSummary(request, stock));
                    responseObserver.onCompleted();
                }
            };

    try {
        childStub.getStock(toStockRequest(request), childObserver);
    } catch (RuntimeException failure) {
        cleanup.run();
        if (!parentContext.isCancelled()) {
            responseObserver.onError(mapChildFailure(failure));
        }
    }
}
~~~

This is a pattern for a unary downstream async call; types like InventoryGrpc, StockRequest, StockReply, mapChildFailure(...), and toSummary(...) belong to the illustrative application. Key points:

- The parent listener sets the flag and cancels the child handle if the handle already exists.
- beforeStart(...) stores the handle and then rechecks the flag. This handles the case where the parent is cancelled before gRPC creates the child call.
- cancelSent prevents sending duplicate cancel commands from both the listener and beforeStart.
- onNext(...) ignores results arriving after the parent is cancelled.
- onError(...) and onCompleted() clean up the listener. They only send a terminal callback to the parent if the parent is still active.
- cleanup is idempotent so multiple termination paths do not tear down lifecycle state repeatedly.

In production code, if the parent's deadline has already expired before the child is created, terminate per the handler's policy without initiating the child. If the parent call is already closed, do not send another status; if the call is still open and a processing step's deadline expires, you can return an appropriate status.

## 5. Handling the race when the child handle is not yet ready

An important race happens between the moment the parent is cancelled and the moment the async stub invokes beforeStart(...):

| Order | What happens | How to handle |
| --- | --- | --- |
| Child handle exists first | Listener retrieves the handle and calls cancel. | Child stops via call-level cancellation. |
| Parent cancels first | Listener sets parentCancelled, but there is no handle to cancel yet. | beforeStart stores the handle, sees the flag, and cancels immediately. |
| Cancel occurs concurrently with beforeStart | One branch may not see the handle yet. | Both branches check the same flag; cancelSent lets only one branch issue the command. |
| Child completes before parent cancels | Terminal callback cleans up listener and completes parent if parent is still open. | Parent cancellation arriving later has no active child left to cancel. |

Do not store child call handles in mutable fields of a Spring singleton. Each parent RPC must have its own reference, flag, and listener. If a parent calls multiple children, use a per-parent registry to cancel all active children.

## 6. Propagating the remaining deadline

The parent may have already spent part of its budget before calling downstream. Compute the remaining time right before creating the child call:

~~~java
Deadline deadline = parentContext.getDeadline();
InventoryGrpc.InventoryStub childStub = inventoryStub;

if (deadline != null) {
    long remaining = deadline.timeRemaining(TimeUnit.NANOSECONDS);
    if (remaining <= 0) {
        throw new ParentDeadlineExpiredException();
    }

    childStub = childStub.withDeadlineAfter(
            remaining, TimeUnit.NANOSECONDS);
}
~~~

If the parent has 250 ms left, the child should not be granted a fresh 2 seconds. withDeadlineAfter(...) sets a deadline for the child from the moment of the call; therefore, fetch timeRemaining(...) close to call creation rather than saving a remaining time value too early and reusing it after a long wait.

If there is no parent deadline, do not infer a value from null. Use an application default policy or service config to protect downstream from waiting indefinitely. When a parent deadline exists, the child must be bounded by the remaining budget and must not allow the root request to run longer.

In grpc-java, context deadlines may be inherited automatically along call paths where the context remains attached. Setting the deadline explicitly is useful when the adapter wants to express the remaining budget or when the call is created after context has crossed an asynchronous boundary. Never set a new deadline longer than the parent deadline.

## 7. Parent calling multiple downstream RPCs

If a handler calls multiple services in parallel, cancellation must stop all active children. Call handles can be managed in a registry dedicated to the parent request:

~~~java
final class ChildCallRegistry {
    private final Set<ClientCallStreamObserver<?>> calls = new HashSet<>();
    private boolean cancelled;

    void register(ClientCallStreamObserver<?> call) {
        boolean cancelNow;
        synchronized (this) {
            cancelNow = cancelled;
            if (!cancelNow) {
                calls.add(call);
            }
        }
        if (cancelNow) {
            cancel(call);
        }
    }

    synchronized void unregister(ClientCallStreamObserver<?> call) {
        calls.remove(call);
    }

    void cancelAll() {
        List<ClientCallStreamObserver<?>> snapshot;
        synchronized (this) {
            cancelled = true;
            snapshot = new ArrayList<>(calls);
            calls.clear();
        }
        snapshot.forEach(this::cancel);
    }

    private void cancel(ClientCallStreamObserver<?> call) {
        call.cancel("Parent RPC cancelled", null);
    }
}
~~~

The registry uses the same lock to coordinate register() and cancelAll(): if a call is registered before cancellation, it appears in the snapshot to be cancelled; if registered afterward, register() sees the cancelled flag and cancels immediately. After a child completes or errors, call unregister(...). When the parent is cancelled, call cancelAll() and clean up the registry.

If children are called in parallel, only send the parent response once required results have completed. When one child fails in a way that prevents the use case from continuing, decide whether to cancel the remaining children according to the operation's policy; this is orchestration-failure cancellation, distinct from parent caller cancellation yet using the same call-level cancel mechanism.

## 8. Context propagation across executors

The current context does not automatically appear on every thread created by the application. If the handler dispatches work to an executor before creating a child RPC, capture the context:

~~~java
Context parentContext = Context.current();

executor.execute(parentContext.wrap(() -> {
    if (parentContext.isCancelled()) {
        return;
    }

    callDownstreamWithParentLifecycle(parentContext);
}));
~~~

wrap(...) attaches the captured context while the task runs and restores the previous context after the task finishes. Without propagation, child calls created on a worker may fail to inherit the proper deadline/cancellation. Do not store Context.current() in a singleton field or share it across requests.

If the worker has a Future, wire parent cancellation to Future.cancel(true) and still cancel the downstream call handle. Interrupting a thread does not always stop I/O; the call handle is the direct way to control a child gRPC call. Other HTTP/database dependencies require their own cancel/timeout APIs.

## 9. Cancellation does not roll back child side effects

Calling childCall.cancel(...) only signals that the caller no longer needs the child's result. The child service may already have committed to its database or sent commands to external systems before receiving the signal. Therefore:

- Do not treat child cancellation as proof that the operation did not happen.
- For write RPCs, pass a stable idempotency key down to the child.
- If the parent needs multiple steps to succeed or fail together, use an appropriate saga/state machine and compensation.
- If the child has accepted a durable command, return an operation ID and a status lookup API; parent cancellation does not automatically delete committed commands.
- Do not retry a child just because the parent was cancelled. Retries must originate from an operation still requested by the caller/application and must be safe with respect to side effects.

Example: Order service calls Payment to authorize. If the parent is cancelled after Payment has authorized, child cancel does not automatically release the authorization. The system needs an idempotency key and a void/compensation step based on payment status if business rules require it.

## 10. Testing propagation

Tests should prove that parent cancellation actually reaches the child call, not merely check that the parent context is cancelled:

1. Use a downstream in-process server holding an RPC incomplete.
2. Call the parent handler through a second in-process server; parent creates an async child call.
3. Use a latch to confirm the child handler has started.
4. Cancel the parent call from the client using ClientCallStreamObserver.cancel(...).
5. Downstream server registers ServerCallStreamObserver.setOnCancelHandler(...); await the latch and verify the child receives cancellation.
6. Verify the parent sends no further responses and the listener/registry are cleaned up.

Additional cases:

- Parent is cancelled before child beforeStart runs; child must be cancelled as soon as the handle appears.
- Parent deadline expires; child also must not run beyond the remaining budget.
- Parent explicitly cancels while deadline still has time; child must stop before the deadline.
- One of multiple children fails; verify whether policy cancels the remaining children.
- Child commits a side effect before cancellation; verify idempotency/status lookup reflects the true outcome.
- Executor rejects the task or child call creation throws synchronously; listener and handle must be cleaned up.

In-process tests verify gRPC lifecycle logic but do not replace tests over TCP/TLS, proxies, and service meshes. Real networks help evaluate cancellation propagation latency and silent peer-disconnect scenarios.

## 11. Observability and common mistakes

You should measure active child calls per parent method, time from parent cancellation to child termination, cancelled child count, final status, and listeners/handles still remaining after terminal events. Logs should include parent trace ID, child method, status, and duration; do not log payloads or tokens.

| Symptom | Cause | How to fix |
| --- | --- | --- |
| Parent cancels but child keeps running | Only cancelling parent response or not retaining child call handle. | Wire parent listener to ClientCallStreamObserver.cancel(...). |
| Child is not cancelled on very early cancel | Listener runs before child handle is created. | Use a cancellation flag and recheck inside beforeStart. |
| Child runs longer than parent | Granting a fresh timeout instead of remaining budget. | Use Deadline.timeRemaining(...). |
| Child created on worker does not see parent context | Context not propagated across executor. | Capture context and use wrap(...)/context-aware executor. |
| One request cancels another request's child | Sharing a call handle field in a singleton. | Keep per-parent-RPC registry and state. |
| Parent completes but listener retains references | Forgot to remove listener/unregister child. | Clean up on all terminal paths: complete, error, cancel, and start failure. |
| Retrying child after parent cancellation causes duplicate writes | Treating cancellation as rollback. | Idempotency key, operation status, and compensation. |

## 12. Hands-on exercises

1. Write a server handler calling a downstream unary async RPC; obtain the child call handle via ClientResponseObserver.beforeStart(...).
2. Register a Context.CancellationListener to cancel the child; handle the race when the parent cancels before the child handle appears.
3. Propagate the parent's remaining deadline to the child and verify you do not re-grant the full timeout.
4. Open two downstream calls in parallel; use a per-parent registry to cancel all children when the parent is cancelled.
5. Move child call creation to an executor; use Context.wrap(...) and verify deadline/cancellation are still propagated.
6. Write an in-process test proving the child server receives cancellation when the parent client cancels the call.
7. Test cancellation after the child has committed a side effect; verify idempotency/status lookup and business-driven compensation.

After this lesson, you should know how to wire parent RPC cancellation to each downstream call, propagate the remaining deadline, handle races when call handles are not yet ready, and clean up listeners/registries on every terminal path. Parent cancellation stops child work that is no longer needed, but does not roll back committed side effects; idempotency and operation status are still essential to maintain correctness in a Spring gRPC system.
