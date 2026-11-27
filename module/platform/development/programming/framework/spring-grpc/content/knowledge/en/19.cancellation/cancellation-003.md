# Context cancellation in handlers

When a client cancels an RPC or the deadline expires, gRPC Java marks the server-side call context as cancelled. The handler can observe this state through `io.grpc.Context`. If the handler simply hands work off to an executor and keeps processing as normal, the worker may continue querying the database, calling other services, or generating data even though the caller has stopped waiting.

**Context cancellation in handlers** is how the RPC's termination signal is propagated to processing steps inside the server. This lesson belongs to the **Cancellation** chapter of the **SPRING_GRPC** module: developing gRPC services in the Spring ecosystem from Protocol Buffers contracts and generated Java code, supporting unary/streaming RPCs, metadata, deadlines, statuses, interceptors, TLS, testing, and observability. The focus here is obtaining the RPC context, observing cancellation/deadlines, propagating context across executors, and safely stopping dependent work.

## 1. What is the RPC Context?

`io.grpc.Context` is a mechanism that carries information along the execution flow of an RPC, including deadline, cancellation, and values attached to the context. When gRPC invokes a server handler, the context corresponding to that RPC is set as the current context while the handler runs.

```java
import io.grpc.Context;

Context rpcContext = Context.current();
boolean cancelled = rpcContext.isCancelled();
```

`Context.current()` retrieves the context attached to the current thread. Inside a server handler, that is typically the current RPC's context. `isCancelled()` indicates whether the context has been cancelled; `cancellationCause()` provides the cause if any; `getDeadline()` returns the deadline attached to the context, if the RPC has one.

Context lets handlers perceive the RPC lifecycle without passing a cancellation flag through every function. However, context **does not automatically stop all work**. A JDBC query, HTTP request, or executor task only stops when the corresponding API supports timeout/cancel or application code actively checks and reacts to the signal.

## 2. Checking cancellation and deadline in handlers

A synchronous handler can check the context at safe points before starting resource-intensive work and before sending the result:

```java
@Override
public void getReport(
        ReportRequest request,
        StreamObserver<ReportReply> responseObserver) {

    Context rpcContext = Context.current();

    if (rpcContext.isCancelled()) {
        return;
    }

    Report report = reportService.load(request.getReportId());

    if (rpcContext.isCancelled()) {
        return;
    }

    responseObserver.onNext(toReply(report));
    responseObserver.onCompleted();
}
```

This snippet illustrates the checking principle; `reportService.load(...)` must have a time bound or its own cancellation mechanism if it can block for a long time. Checking `isCancelled()` before and after the call only reduces wasted work; it cannot prevent cancellation from occurring right after the last check. The transport will handle the closed call; the server must still ensure resources are released.

Deadlines can also be read from the context:

```java
import io.grpc.Deadline;
import java.util.concurrent.TimeUnit;

Deadline deadline = rpcContext.getDeadline();
if (deadline != null) {
    long remainingMillis = deadline.timeRemaining(TimeUnit.MILLISECONDS);
    if (remainingMillis <= 0) {
        return;
    }
    // Use remainingMillis to bound the next processing step.
}
```

No deadline means `getDeadline()` returns `null`; do not assume every client sets a timeout. In systems with clear timing requirements, set deadlines on the client and check the remaining time before critical processing steps.

## 3. Registering a listener to receive cancellation as soon as it occurs

Polling `isCancelled()` only detects cancellation at the next check. When a handler needs to notify a waiting or running worker, it can register a `Context.CancellationListener`:

```java
Context rpcContext = Context.current();
AtomicBoolean cancelled = new AtomicBoolean(rpcContext.isCancelled());

Context.CancellationListener listener = ignored ->
        cancelled.set(true);

rpcContext.addListener(listener, Runnable::run);
try {
    performWork(cancelled);
} finally {
    rpcContext.removeListener(listener);
}
```

The listener is invoked when the context is cancelled. In the example, the callback only sets an atomic flag to notify the running work. `Runnable::run` executes the callback directly on the notifying thread; therefore, the listener must be **fast and non-blocking**. If you need to call a database, wait on a lock, or perform lengthy cleanup, dispatch the signal to an appropriate worker/executor.

Always remove the listener with `removeListener(...)` when the work completes so unnecessary references are not retained. You should also check `isCancelled()` before and after registration if your logic has a race between obtaining the context and installing the listener. The context may already have been cancelled before the handler begins the next step.

## 4. Propagating Context to an executor

A common mistake is calling `Context.current()` in the handler, submitting a lambda to an `ExecutorService`, and then calling `Context.current()` inside the worker expecting the original RPC context. **Context is not automatically attached to every thread created by the application.** Thread pools can reuse threads across many requests; without proper context propagation, a worker may see a different root context or the default context.

Capture the context while still in the handler and wrap the task with `rpcContext.wrap(...)`:

```java
Context rpcContext = Context.current();

workers.execute(rpcContext.wrap(() -> {
    if (rpcContext.isCancelled()) {
        return;
    }

    processReport(request);
}));
```

`wrap(Runnable)` attaches the captured context while the task runs, then restores the previous context when the task finishes. For `Callable`, gRPC Java also provides a corresponding wrap method. You can use `rpcContext.fixedContextExecutor(executor)` when you want every task submitted through that executor to run in the same captured context.

Do not store `Context.current()` in a singleton field of a Spring service. A context belongs to a single RPC; storing it in a shared field can mix concurrent requests and retain references for too long. Capture it in a local variable within the handler and pass it to the specific task whose lifecycle is tied to that RPC.

## 5. Combining Context cancellation with `Future.cancel(true)`

When a worker may run for a long time, only setting a cancellation flag is not enough if the worker is blocking. You can register a listener to cancel the `Future`, while rechecking after submitting the task to handle races:

```java
Context rpcContext = Context.current();
AtomicBoolean cancelled = new AtomicBoolean(rpcContext.isCancelled());
AtomicReference<Future<?>> taskRef = new AtomicReference<>();

Context.CancellationListener listener = ignored -> {
    cancelled.set(true);
    Future<?> task = taskRef.get();
    if (task != null) {
        task.cancel(true);
    }
};

rpcContext.addListener(listener, Runnable::run);

try {
    Future<?> task = workers.submit(rpcContext.wrap(() -> {
        try {
            if (cancelled.get() || rpcContext.isCancelled()) {
                return;
            }

            String report = reportService.generate(request);

            if (cancelled.get() || rpcContext.isCancelled()
                    || Thread.currentThread().isInterrupted()) {
                return;
            }

            responseObserver.onNext(toReply(report));
            responseObserver.onCompleted();
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
        } catch (Exception failure) {
            if (!cancelled.get() && !rpcContext.isCancelled()) {
                responseObserver.onError(Status.INTERNAL
                        .withDescription("Unable to generate report")
                        .withCause(failure)
                        .asRuntimeException());
            }
        } finally {
            rpcContext.removeListener(listener);
        }
    }));

    taskRef.set(task);
    // Cancellation may arrive before taskRef is assigned.
    if (cancelled.get() || rpcContext.isCancelled()) {
        task.cancel(true);
    }
} catch (RejectedExecutionException rejected) {
    rpcContext.removeListener(listener);
    if (!rpcContext.isCancelled()) {
        responseObserver.onError(Status.RESOURCE_EXHAUSTED
                .withDescription("Server is not accepting additional tasks")
                .withCause(rejected)
                .asRuntimeException());
    }
}
```

This snippet requires the variables `workers`, `request`, `reportService`, `responseObserver`, and the `toReply(...)` function from the handler. `Future.cancel(true)` sends an interrupt to the worker if the task is running; it does not guarantee stopping I/O libraries that do not support interrupts. Database/HTTP APIs need their own query timeout or cancellation mechanism.

The race is handled in both directions: the listener cancels the task if `taskRef` is already populated; if cancellation arrives before `taskRef.set(task)`, the `cancelled` flag is rechecked after submission and the task is cancelled immediately. The worker removes the listener in `finally`. If the executor rejects the task, the handler removes the listener and returns an appropriate status when the call has not yet been cancelled.

## 6. Propagating deadline and cancellation to other dependencies

If the handler calls another gRPC service, you can use the remaining deadline from the current context to bound the downstream RPC:

```java
Deadline deadline = rpcContext.getDeadline();
InventoryGrpc.InventoryBlockingStub callStub = inventoryStub;

if (deadline != null) {
    long remainingNanos = deadline.timeRemaining(TimeUnit.NANOSECONDS);
    if (remainingNanos <= 0 || rpcContext.isCancelled()) {
        return;
    }
    callStub = callStub.withDeadlineAfter(
            remainingNanos, TimeUnit.NANOSECONDS);
}

StockReply stock = callStub.getStock(stockRequest);
```

This snippet illustrates propagating the **remaining budget**, rather than granting the full timeout again at each hop. If there is no deadline, the system needs a separate default policy to avoid downstream RPCs waiting indefinitely. When a worker is interrupted due to cancellation, make sure the downstream call is also terminated; with a blocking stub, use a finite deadline and design a cancellation mechanism suited to the call/transport. With an async downstream stub, keep the call handle to cancel the specific RPC when the context is cancelled.

Context propagation lets layers read the same deadline/cancellation state, but does not automatically stop libraries outside gRPC. JDBC, HTTP clients, message consumers, and SDKs require their own cancellation APIs. Never call `Thread.stop()` to force-stop work.

## 7. Cancellation in streaming handlers

With server-streaming or bidirectional-streaming, the context exists throughout the RPC. When the client cancels the stream, the handler must stop the producer, close subscriptions, and release buffers/cursors. You can combine `Context.CancellationListener` with `ServerCallStreamObserver` to inspect call state and pace message sending.

```java
Context rpcContext = Context.current();
ServerCallStreamObserver<PriceUpdate> call =
        (ServerCallStreamObserver<PriceUpdate>) responseObserver;
AtomicBoolean stopped = new AtomicBoolean(rpcContext.isCancelled());
AtomicReference<Subscription> subscriptionRef = new AtomicReference<>();
AtomicReference<Context.CancellationListener> listenerRef = new AtomicReference<>();

Runnable cleanup = () -> {
    stopped.set(true);
    Subscription subscription = subscriptionRef.getAndSet(null);
    if (subscription != null) {
        subscription.close();
    }
    Context.CancellationListener registered = listenerRef.get();
    if (registered != null) {
        rpcContext.removeListener(registered);
    }
};
Context.CancellationListener listener = ignored -> cleanup.run();
listenerRef.set(listener);
rpcContext.addListener(listener, Runnable::run);

if (!stopped.get() && !call.isCancelled()) {
    Subscription subscription = priceFeed.subscribe(symbol, update -> {
        if (!stopped.get() && !call.isCancelled()) {
            responseObserver.onNext(toProto(update));
        }
    });
    subscriptionRef.set(subscription);

    // Handle cancellation occurring while subscribe is creating the handle.
    if (stopped.get() || call.isCancelled()) {
        cleanup.run();
    }
}
```

`Subscription` is a handle provided by the application's `priceFeed`. The handler is registered before starting the subscription; if cancellation occurs before the handle is stored, the `stopped` flag is checked again right after the subscription is created and the handle is closed. `getAndSet(null)` ensures retrieving the handle succeeds in only one branch, avoiding closing the same subscription multiple times. When the data source completes normally, the owner must also call `cleanup.run()` and then `responseObserver.onCompleted()`; if the stream errors, clean up before terminating with `onError(...)`. You must follow the thread-safety contract of `priceFeed` and avoid allowing `onNext` callbacks to run concurrently from multiple threads if the observer is not designed for it.

The example above illustrates cancellation and cleanup; it does not yet implement full flow control. In production, if the producer can outpace the client, use `call.isReady()` together with `setOnReadyHandler(...)` and a bounded queue to send only when the call is ready. Do not simply drop messages when `isReady()` returns `false`, as that can cause data loss. Readiness is different from `isCancelled()`: a stream may not be cancelled yet while currently not ready to accept more messages. Cancellation terminates the entire call; readiness/backpressure paces the rate while the call is still active.

## 8. Cleanup and limitations of cancellation

A cancellation listener should only emit a quick stop signal. Lengthy cleanup work should be delegated to the worker or the API owning the resource. Some examples:

| Resource/work | How to react |
| --- | --- |
| Executor task | Store `Future`, set flag, and request interrupt. |
| JDBC query | Set query timeout; use `Statement.cancel()` if supported by the driver; close cursors/result sets. |
| HTTP call to dependency | Keep the call handle and invoke cancel per the HTTP client's API. |
| Subscription | Unsubscribe and stop the producer. |
| File/stream/buffer | Close resources in `finally` or `try-with-resources`. |

Cleanup needs to be idempotent because it can be triggered by multiple termination paths: cancellation listener, `finally`, processing error, or server shutdown. Only close resources owned by the handler/worker; do not close a shared executor or connection pool just because one RPC was cancelled.

Cancellation is a best-effort signal. The client may lose network connectivity abruptly; the server may detect it late. If a side effect has already committed, cancellation does not roll it back. Write operations need idempotency keys or a status-determination mechanism to avoid creating duplicate data when a caller retries after not receiving a response.

## 9. Testing Context cancellation

Tests should verify all three points: the handler gets the right RPC context, the listener is invoked when the client cancels, and the worker/resources actually stop. With a gRPC in-process server, a test can use latches:

```java
CountDownLatch handlerStarted = new CountDownLatch(1);
CountDownLatch contextCancelled = new CountDownLatch(1);

GreeterGrpc.GreeterImplBase service = new GreeterGrpc.GreeterImplBase() {
    @Override
    public void sayHello(
            HelloRequest request,
            StreamObserver<HelloReply> responseObserver) {
        Context rpcContext = Context.current();
        Context.CancellationListener listener = ignored ->
                contextCancelled.countDown();
        rpcContext.addListener(listener, Runnable::run);
        handlerStarted.countDown();
    }
};
```

Start an in-process server and channel with the service above. The client calls using an async stub and implements `ClientResponseObserver.beforeStart(...)` to retain `ClientCallStreamObserver`; after `handlerStarted.await(...)` succeeds, the client calls `cancel(...)` and the test awaits `contextCancelled.await(...)`. In a complete fixture, remove the listener when the handler finishes and close the channel/server in `finally`.

Additional cases to include:

1. Client cancels while the worker is running; verify the listener sets the flag and the worker stops.
2. Deadline expires; verify the context transitions to cancelled and downstream work receives the remaining budget.
3. Cancellation occurs before the task handle is stored; verify the race is handled.
4. Executor rejects the task; verify the listener is removed and the server returns an appropriate status.
5. Streaming producer is cancelled; verify the subscription is closed and no new messages remain.
6. Handler completes normally; verify the listener is removed and no references are retained after the RPC.

In-process tests verify gRPC/context mechanics but do not replace integration tests over TCP/TLS, proxies, or ingress. Real network testing is useful to observe peer-disconnect detection latency and ensure cleanup remains safe when connections drop.

## 10. Common mistakes

| Symptom | Cause | How to fix |
| --- | --- | --- |
| Worker does not see cancellation | Reading `Context.current()` in a thread pool without propagating context. | Capture context in the handler and use `rpcContext.wrap(...)`. |
| Context held in a singleton field | Sharing context across concurrent RPCs. | Keep context in local variables scoped to the handler/task. |
| Listener not called or resources do not stop | Listener not registered or listener only logs. | Set a flag and connect it to task/resource cancellation. |
| Handler blocks inside cancellation callback | Listener performs I/O or waits for worker completion. | Callback only emits a quick signal; clean up in the worker. |
| `Future.cancel(true)` but query keeps running | Driver/API does not respond to interrupts. | Use the dependency's own timeout/cancel API. |
| Downstream RPC has a longer wait than the original request | Re-granting the initial timeout instead of the remaining deadline. | Compute `timeRemaining(...)` and pass it downstream. |
| Listener retains references after RPC ends | Forgot `removeListener(...)`. | Remove the listener during handler/task cleanup. |
| Cancellation treated as rollback | Server may have already committed side effects. | Use idempotency and check business state. |

## 11. Hands-on exercises

1. In a server handler, get `Context.current()`, log `isCancelled()` and `getDeadline()`; test behavior when the client sets a short deadline.
2. Register a `Context.CancellationListener` to set a flag; cancel the client RPC and verify the listener is invoked.
3. Offload work to an `ExecutorService` using `rpcContext.wrap(...)`; prove the worker receives the correct RPC context.
4. Connect the listener to `Future.cancel(true)` and test the race when cancellation arrives before the task handle is stored.
5. Call a downstream gRPC service using the remaining deadline time; verify the downstream call does not continue running past the original RPC's budget.
6. Create a server-streaming producer, cancel the subscription when the context is cancelled, and verify cleanup/backpressure.
7. Write in-process tests for cancellation, deadline, executor rejection, and normal completion; verify the listener is always removed.

After this lesson, you should know how to obtain the RPC context in a handler, read cancellation/deadlines, register a listener, propagate context to an executor, and wire cancellation signals to underlying workers or I/O. `Context` provides state and propagation; the application must still actively stop work and clean up. Doing this properly helps a Spring gRPC server avoid wasted processing, free resources, and maintain reliability when clients cancel RPCs or deadlines expire.
