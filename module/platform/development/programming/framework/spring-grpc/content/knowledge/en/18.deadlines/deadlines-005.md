# Checking Context.isCancelled

When a client cancels an RPC or a deadline expires, gRPC marks the **call's context** as cancelled. The server needs to detect this signal to stop work that is no longer needed, cancel downstream tasks, and release resources. In gRPC Java, the direct check is **Context.current().isCancelled()**.

In **Spring gRPC**, Context is bound to RPC execution. **isCancelled()** indicates whether the current context has been cancelled; it does not automatically stop loops, database queries, or tasks running on an executor. Therefore, you must combine checks at appropriate processing points with listeners and each resource's cancellation mechanism.

## 1. What does Context.isCancelled() tell you?

**io.grpc.Context** carries call-scoped data, including the deadline and cancellation state. In a server handler, get the current context via:

~~~java
Context rpcContext = Context.current();
boolean cancelled = rpcContext.isCancelled();
~~~

If **isCancelled()** returns true, the call is no longer considered active. Common causes include:

- The client actively cancelled the RPC.
- The client's deadline expired.
- A parent context was cancelled and cancellation propagated to the child context.
- The application explicitly cancelled a separately created context.

If it returns false, it only means the context **had not been cancelled at the moment of the check**. It does not guarantee the RPC will remain active until processing finishes; cancellation can happen immediately afterward. For long-running tasks, do not check once at the start of the method and ignore the state for the rest of the execution.

## 2. Checking cancellation in a server handler

For unary RPCs with multiple processing steps, check the context at expensive work boundaries:

~~~java
@Override
public void getReport(
        ReportRequest request,
        StreamObserver<ReportResponse> responseObserver) {

    Context rpcContext = Context.current();
    if (rpcContext.isCancelled()) {
        return;
    }

    ReportData data = reportService.loadData(request);
    if (rpcContext.isCancelled()) {
        return;
    }

    ReportResponse response = reportService.buildResponse(data);
    if (rpcContext.isCancelled()) {
        return;
    }

    responseObserver.onNext(response);
    responseObserver.onCompleted();
}
~~~

This is an illustrative pattern; reportService represents application logic. Once an RPC has been cancelled, the server usually does not need to attempt sending further responses or error statuses to a client that has already left. These checks help avoid starting the next step when its result will no longer be used.

Checks between steps cannot interrupt an in-flight blocking call. If loadData() is waiting on a database, configure a query timeout/cancellation or use an async API that supports cancellation. **Context.isCancelled()** is a signal for application coordination, not a mechanism that automatically interrupts every thread.

## 3. Reacting immediately to cancellation with a listener

For streaming RPCs or long-running tasks, periodic checks may not be enough. You can register a **cancellation listener** to be notified when the context is cancelled:

~~~java
Context rpcContext = Context.current();

rpcContext.addListener(cancelledContext -> {
    stopProducer();
    closeSubscription();
    releaseTemporaryResources();
}, cleanupExecutor);
~~~

**addListener** takes a callback and an executor to run the callback. In this example, cleanupExecutor is an application-managed executor; stopProducer, closeSubscription, and releaseTemporaryResources represent real resources.

Listeners are useful when the server is:

- Continuously emitting events in server streaming.
- Reading files or uploading data in chunks.
- Holding a subscription to an event source.
- Running asynchronous tasks or calling multiple downstream services.

Cleanup callbacks should be short and not block for long on a gRPC processing thread. If I/O or closing multiple resources is needed, offload the appropriate work to a managed, bounded executor.

## 4. Cleanup must be idempotent and race-safe

Cancellation can arrive at nearly the same moment as normal completion. For example, just as the server finishes sending the response, the listener also triggers. If both paths close the subscription or release resources, the code must tolerate cleanup being invoked multiple times.

~~~java
AtomicBoolean cleaned = new AtomicBoolean(false);

Runnable cleanup = () -> {
    if (cleaned.compareAndSet(false, true)) {
        subscription.close();
        workerPool.releasePermit();
    }
};

rpcContext.addListener(ignored -> cleanup.run(), cleanupExecutor);

try {
    runStream();
} finally {
    cleanup.run();
}
~~~

subscription and workerPool are assumed application resources. The AtomicBoolean flag ensures cleanup runs only once even when the cancellation path and normal completion path race. With multiple resources, clean up in order and still release the remaining resources if closing one fails.

For **StreamObserver**, calls to onNext, onError, and onCompleted must also be serialized. Do not emit messages after the RPC has ended or after the context has been cancelled.

## 5. Distinguishing isCancelled() from deadline expiration

**isCancelled()** checks the general cancellation state. It does not indicate whether the cause was a deadline, a client cancel, or a cancelled parent context.

If you need to diagnose a deadline, you can read the deadline attached to the context:

~~~java
Context rpcContext = Context.current();
Deadline deadline = rpcContext.getDeadline();

if (rpcContext.isCancelled()) {
    // The RPC has been cancelled.
}

if (deadline != null && deadline.isExpired()) {
    // The deadline has expired.
}
~~~

You can check **rpcContext.cancellationCause()** to retrieve the cause if the context provides one. This is diagnostic information; do not rely solely on the cause to drive every business policy. On the client side, an expired deadline is typically surfaced as **DEADLINE_EXCEEDED**; the server side typically observes a cancelled context.

| Check | Question Answered |
| --- | --- |
| **isCancelled()** | Has the context been cancelled? |
| **getDeadline()** | What deadline does the context have? |
| **deadline.isExpired()** | Has the deadline timestamp passed? |
| **cancellationCause()** | Is a cancellation cause attached to the context? |

Do not assume **isCancelled() == true** always means the client's deadline expired. The client may have cancelled actively, or a parent context may have been cancelled for another reason.

## 6. Context cancellation is not Thread interruption

This is a common confusion in Java:

- **Context.isCancelled()** checks the gRPC context's cancellation state.
- **Thread.currentThread().isInterrupted()** checks the Java thread's interrupt flag.
- **Future.cancel(true)** requests task cancellation and may interrupt the thread running that task.

These three mechanisms are related, but not automatically equivalent. When the context is cancelled, do not assume the processing thread will automatically receive an interrupt. The application must wire cancellation to each resource's API:

| Work Type | Appropriate Reaction |
| --- | --- |
| Loop processing multiple records | Check context at safe points between iterations |
| Future running on an executor | Register a listener and call future.cancel(true) if the task supports interrupts |
| JDBC query | Set query timeout or invoke the statement/driver cancellation mechanism |
| Downstream HTTP/gRPC | Use a cancellable call API and maintain appropriate context/deadline |
| Subscription/event producer | Cancel the subscription, stop the producer, and release queues |

Do not swallow **InterruptedException**. When catching this exception, you typically need to restore the interrupt flag via **Thread.currentThread().interrupt()** and then exit or propagate the error as designed.

## 7. Preserving Context when offloading to an executor

**Context.current()** relies on the context bound to the current execution thread. When the server offloads work to a thread pool without context attachment, Context.current() in the new thread may be a different context or the root context. Without propagating context, cancellation checks and outbound RPCs may no longer be linked to the parent call.

Capture the context in the handler and wrap the task:

~~~java
Context rpcContext = Context.current();

Future<?> task = applicationExecutor.submit(
    rpcContext.wrap(() -> {
        while (!rpcContext.isCancelled() && hasMoreWork()) {
            processNextItem();
        }
    }));

rpcContext.addListener(
    ignored -> task.cancel(true),
    cancellationExecutor);
~~~

Or use an executor bound to the captured context:

~~~java
Context rpcContext = Context.current();
Executor contextExecutor =
    rpcContext.fixedContextExecutor(applicationExecutor);

contextExecutor.execute(() -> {
    if (!Context.current().isCancelled()) {
        callDownstreamService();
    }
});
~~~

Wrapping the task preserves the parent RPC's context across asynchronous execution. The listener connects cancellation to Future.cancel(true); the loop still checks isCancelled() because interrupts may not stop all types of work.

Do not retain a finished RPC's context in a singleton or long-lived background queue. Independent background tasks need their own lifecycle, deadline, and context; they should not continue using an expired request's context.

## 8. Checking cancellation in streaming RPCs

For server streaming, the client may cancel when it no longer needs events. The server should stop the event source and close the subscription:

~~~java
Context rpcContext = Context.current();
ServerCallStreamObserver<Event> serverObserver =
    (ServerCallStreamObserver<Event>) responseObserver;

AtomicBoolean closeRequested = new AtomicBoolean(false);
AtomicBoolean subscriptionClosed = new AtomicBoolean(false);
AtomicReference<EventSubscription> subscriptionRef =
    new AtomicReference<>();

Runnable closeOnce = () -> {
    closeRequested.set(true);
    EventSubscription current = subscriptionRef.get();
    if (current != null
            && subscriptionClosed.compareAndSet(false, true)) {
        current.close();
    }
};

EventSubscription subscription = eventSource.subscribe(event -> {
    if (rpcContext.isCancelled() || serverObserver.isCancelled()) {
        closeOnce.run();
        return;
    }
    responseObserver.onNext(event);
});
subscriptionRef.set(subscription);

// Handle race if cancellation occurs before subscription is assigned.
if (closeRequested.get()
        && subscriptionClosed.compareAndSet(false, true)) {
    subscription.close();
}

rpcContext.addListener(ignored -> closeOnce.run(), cleanupExecutor);
serverObserver.setOnCancelHandler(closeOnce);
~~~

This example assumes EventSubscription has a close method that throws no checked exceptions and that event callbacks are serialized before writing to the response observer. In a real service, handle both normal completion and errors through the same cleanup mechanism; if the event source can invoke callbacks concurrently, serialize calls to onNext/onCompleted/onError. Checking both context and the server observer helps detect cancellation at both the RPC and call levels.

On the server side, **ServerCallStreamObserver** also provides **isCancelled()** and **setOnCancelHandler()** to observe/act on call state. Use them when you need server-call-level detail; **Context.isCancelled()** remains useful for checking context and propagating cancellation across nested calls. The client side uses **ClientCallStreamObserver** for outbound operations such as readiness, requesting demand, or cancelling the call.

## 9. Testing Context.isCancelled

A good test should prove that cancellation not only causes the client to receive an error, but also causes the server to stop work:

1. Invoke an RPC with a long-running task or an open stream.
2. Client actively cancels or sets a short deadline to trigger cancellation.
3. Server listener is triggered or loop observes isCancelled() == true.
4. Producers, futures, subscriptions, and temporary resources are cleaned up.
5. No new messages are emitted after the stream ends.
6. Normal completion and cancellation racing still run cleanup only once.

With gRPC in-process transport, you can hold a ClientCall or client-side observer to actively cancel; for deadline tests, set a short withDeadlineAfter. Use CountDownLatch or CompletableFuture to await cleanup signals instead of arbitrary sleeps.

Beyond gRPC tests, test database or HTTP client adapters to confirm cancellation actually stops I/O. A test that only checks Context.isCancelled() returning true does not prove database queries or thread pool tasks stopped running.

## 10. Observability and error handling

Track per RPC method:

- Number of calls cancelled by the client and number that hit the deadline.
- Duration from when the context is cancelled until cleanup completes.
- Number of tasks/futures still running after cancellation.
- Number of subscriptions, queues, and temporary resources released.
- Rate of messages emitted after the client is no longer receiving.
- Status received by the client: **CANCELLED**, **DEADLINE_EXCEEDED**, or other errors.

If clients frequently see DEADLINE_EXCEEDED while the server still has many tasks running long afterward, cancellation is not fully wired to internal work. If the server sees many CANCELLED statuses, use traces and context cause to distinguish users leaving requests, parent services being cancelled, or upstream deadlines expiring.

Do not log sensitive payloads or credentials when logging cancellation. Trace ID, full method name, status, processing duration, and cleanup duration are usually sufficient for investigation.

## 11. Summary and self-check

**Context.isCancelled()** indicates whether the RPC's context has been cancelled. On the server, the context can be cancelled due to client cancellation, deadline expiration, or parent context cancellation. Checking the flag does not automatically stop threads, databases, or producers; the application must connect that signal to each resource's cancellation mechanism.

Self-check:

1. Why does isCancelled() == false at the start of a handler not guarantee the RPC is still active at the end?
2. When the client's deadline expires, does the server typically observe a status or context cancellation?
3. Why is Context.isCancelled() not equivalent to Thread.isInterrupted()?
4. When offloading work to an executor, what must be done to preserve the parent RPC's context?
5. Why must cleanup be idempotent when a listener and the normal completion path can run concurrently?

Checking cancellation in the right places, propagating context across asynchronous tasks, and cleaning up safely keep Spring gRPC services from wasting resources on calls the client has already cancelled or timed out on.
