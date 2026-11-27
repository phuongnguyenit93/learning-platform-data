# Cancelling Work When Deadlines Expire

When an RPC's deadline expires, gRPC terminates the call on the client side and reports **DEADLINE_EXCEEDED**. On the server side, the RPC's context is marked **cancelled**. If the service keeps querying databases, calling downstream services, or processing files as usual, the system continues consuming resources for a result the client is no longer waiting for.

In **Spring gRPC**, work cancellation must be designed around **cooperative cancellation**: the application receives the signal from **io.grpc.Context**, propagates it to cancellable tasks, checks state at safe points, and releases resources. A deadline does not automatically stop every Java thread or roll back committed transactions.

## 1. What happens when a deadline expires?

Suppose a client calls **GenerateReport** with a 700 ms deadline. If the RPC has not completed when time runs out, the client receives **DEADLINE_EXCEEDED**. gRPC cancels the call; the context bound to the server handler transitions to the cancelled state.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Spring gRPC server
    participant W as Worker / downstream
    C->>S: GenerateReport (700 ms deadline)
    S->>W: Start report generation
    Note over C,S: Deadline expires
    C-->>C: DEADLINE_EXCEEDED
    S->>S: Context.isCancelled() = true
    S->>W: Request work cancellation
    W-->>S: Stop / release resources if supported
~~~

Both sides observe different symptoms:

| Side | Observation |
| --- | --- |
| Client | RPC terminates with **DEADLINE_EXCEEDED** |
| Server | RPC Context is cancelled; call is no longer valid for sending responses |
| Java tasks | Stop only if the application or task API handles cancellation |
| Database / HTTP client | Stop only when the driver/client has a timeout or matching cancel API |

**DEADLINE_EXCEEDED** is not necessarily thrown as an exception inside the server handler. The server typically needs to monitor **context cancellation** to stop work. At the same time, cancellation may stem from the client actively cancelling or a parent context being cancelled; **isCancelled()** only indicates the state, not the cause.

## 2. Checking Context before and during processing

Inside a gRPC Java callback, obtain the current context via **Context.current()**:

~~~java
Context rpcContext = Context.current();

if (rpcContext.isCancelled()) {
    return;
}

ReportData data = reportService.loadFirstPart(request);

if (rpcContext.isCancelled()) {
    return;
}

ReportData completed = reportService.loadSecondPart(data);

if (rpcContext.isCancelled()) {
    return;
}

responseObserver.onNext(toResponse(completed));
responseObserver.onCompleted();
~~~

This is a pattern for a multi-step handler; reportService and toResponse represent business logic. Checking at step boundaries avoids starting new work after the RPC is cancelled.

Do not check only once at the start of the method. Cancellation can arrive while the server is processing. Conversely, checking **isCancelled()** cannot interrupt a blocking call already in progress; if loadFirstPart() waits 20 seconds on the database, code only checks again after that method returns.

## 3. Using a cancellation listener to react immediately

For long-running work or resources that need closing, register a listener on the context:

~~~java
Context rpcContext = Context.current();

rpcContext.addListener(cancelledContext -> {
    stopProducer();
    cancelDownstreamCall();
    closeTemporaryFile();
}, cleanupExecutor);
~~~

The listener is invoked when the context transitions to cancelled. cleanupExecutor is an application-managed executor. The callback should be short and avoid long blocking I/O on a gRPC processing thread.

Listeners are suitable for:

- Cancelling a running Future or task.
- Closing a subscription to an event source.
- Stopping a server-streaming producer.
- Requesting cancellation of a downstream HTTP/gRPC call.
- Closing temporary files, streams, or held resources.

If the context was already cancelled before the listener was registered, the listener is still notified per Context semantics. Therefore, design callbacks to be safe even when cancellation happens very early.

## 4. Cancelling tasks on an Executor or Future

**Context.isCancelled()** does not automatically interrupt threads. If work runs on an executor, connect cancellation to **Future.cancel(true)** and have the task react to interrupts or context state:

~~~java
Context rpcContext = Context.current();

Future<?> task = applicationExecutor.submit(
    rpcContext.wrap(() -> {
        try {
            while (!rpcContext.isCancelled() && hasMoreItems()) {
                processNextItem();
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        } finally {
            releaseWorkerResources();
        }
    }));

rpcContext.addListener(
    ignored -> task.cancel(true),
    cancellationExecutor);
~~~

rpcContext.wrap(...) preserves the parent RPC's context inside the task. When the deadline expires, the listener requests future cancellation; cancel(true) can interrupt the running thread. The loop also checks isCancelled() to stop at a safe point.

Adapt this pattern to the type of task:

- If the task finishes before cancellation, cancel(true) has no meaningful side effect.
- If the task is running non-interruptible code, cancel only issues a request; the task may continue.
- If the task is waiting on I/O, use an I/O API that supports timeouts or cancellation.
- Cleanup in finally must be safe when the task is interrupted mid-way.

Do not swallow InterruptedException. Typically you must restore the interrupt flag via **Thread.currentThread().interrupt()** and then exit the task or propagate a stop signal as designed.

## 5. Cancelling downstream gRPC calls

When a server calls a child service within the current context, gRPC Java can propagate the deadline and cancellation to the outbound call. If the child call is made in the proper context, when the parent RPC is cancelled, the child call is also bounded by that context.

~~~java
Context rpcContext = Context.current();

Future<InventoryResponse> downstream = applicationExecutor.submit(
    rpcContext.wrap(() ->
        inventoryStub.checkAvailability(inventoryRequest)));

rpcContext.addListener(
    ignored -> downstream.cancel(true),
    cancellationExecutor);
~~~

This example illustrates running a blocking stub on a worker; in a real application, consider an async stub or a call API with explicit cancellation handling. Do not create a new channel per request. Channels should be reused, whereas deadline/cancellation belong to each call.

If code creates a downstream call after switching to an executor, propagate Context via wrap, fixedContextExecutor, or an equivalent mechanism. Otherwise, the call can lose the parent context and keep running after the client has expired.

Do not simply cancel a Future wrapping a blocking call and assume the child RPC has definitely stopped. For async calls, hold a handle to the call and invoke the appropriate cancel API; also verify that the downstream service actually observes cancellation.

## 6. Databases and I/O need dedicated cancellation mechanisms

gRPC context cancellation does not automatically stop every database query or socket I/O operation. Wire the signal to each resource's API:

| Task | How to Limit or Cancel |
| --- | --- |
| JDBC query | Set query timeout; hold the Statement to call cancel() if the driver supports it |
| HTTP client | Keep a handle to the request and call cancel; set a client timeout |
| File reading | Close the stream/channel when the RPC is cancelled |
| Long CPU task | Check context between steps or chunks |
| Message/event subscription | Cancel the subscription and stop the producer |

Illustrative example with JDBC:

~~~java
Context rpcContext = Context.current();
AtomicReference<Statement> statementRef = new AtomicReference<>();

rpcContext.addListener(ignored -> {
    Statement statement = statementRef.get();
    if (statement != null) {
        try {
            statement.cancel();
        } catch (SQLException ex) {
            log.warn("Unable to cancel JDBC statement", ex);
        }
    }
}, cleanupExecutor);
~~~

This is the cancellation coordination part; connection/statement creation, query execution, and resource closing must still live within proper transaction/resource management. Statement.cancel() depends on the driver and database, so verify it against your actual stack. Always set a query timeout as an independent bound when the cancel signal does not arrive or the driver fails to react in time.

## 7. Cleanup must be idempotent and race-safe

A deadline can expire at the exact moment normal work completes. Both the cancellation listener and the finally branch may attempt to close a subscription or release a permit. Use a cleanup mechanism that runs only once:

~~~java
AtomicBoolean cleaned = new AtomicBoolean(false);

Runnable cleanupOnce = () -> {
    if (cleaned.compareAndSet(false, true)) {
        closeSubscription();
        releaseWorkerPermit();
        deleteTemporaryFile();
    }
};

rpcContext.addListener(
    ignored -> cleanupOnce.run(),
    cleanupExecutor);

try {
    processRequest();
} finally {
    cleanupOnce.run();
}
~~~

The cleanup methods are examples. If one cleanup step can throw an exception, catch and log the error separately so the remaining resources are still released. Do not let a cleanup error overwrite an already-completed business result.

With StreamObserver, serialize onNext, onError, and onCompleted. Once the call is cancelled, do not attempt to send a final response or error status as if the client were still listening. If work finishes concurrently with cancellation, only one branch should terminate the stream.

## 8. Cancelling work in streaming RPCs

For server streaming, the client may leave the screen or no longer need events. The server should stop the producer and close the subscription. **ServerCallStreamObserver** provides **isCancelled()** and **setOnCancelHandler()** to react at the call level:

~~~java
ServerCallStreamObserver<Event> serverObserver =
    (ServerCallStreamObserver<Event>) responseObserver;

AtomicBoolean stopped = new AtomicBoolean(false);
Runnable stopOnce = () -> {
    if (stopped.compareAndSet(false, true)) {
        eventSubscription.close();
        producerExecutor.shutdownNow();
    }
};

serverObserver.setOnCancelHandler(stopOnce);

eventSubscription.onEvent(event -> {
    if (serverObserver.isCancelled()) {
        stopOnce.run();
        return;
    }
    responseObserver.onNext(event);
});
~~~

eventSubscription and producerExecutor represent application components. In production implementations, register the handler before the producer can emit events, serialize observer callbacks, and use the same stopOnce for normal completion, errors, and cancellation. Do not call shutdownNow() on an application-wide shared executor; only stop the task or an executor dedicated to the stream.

For client streaming or bidirectional streaming, apply the same principle to both receiving and sending directions: stop reading the source, cancel in-flight tasks, stop emitting messages, and release queues when the RPC is cancelled.

## 9. Cancellation is not rollback

If the deadline expires after a transaction has committed, data may still have been written even though the client receives DEADLINE_EXCEEDED. Cancellation only requests that work stop; it does not reverse side effects that have already happened.

For commands with side effects:

1. Use a stable idempotency key or operation ID.
2. Record state and results consistently with the business transaction.
3. When the client times out, allow querying status by operation ID.
4. On retry, reuse the same key to avoid executing the action a second time.

For long work that can be split, save checkpoints to track which parts finished. When cancelled, stop at a safe chunk boundary instead of leaving an unrecoverable half-finished state.

## 10. Testing work cancellation on deadline expiration

Tests must verify not only that the client receives DEADLINE_EXCEEDED, but also prove the server actually stops or requests stopping work:

1. Create an RPC with a long-running worker or an open stream.
2. Client sets a deadline shorter than the processing duration.
3. Verify the client receives DEADLINE_EXCEEDED.
4. Verify the context listener is invoked or the call observer receives cancellation.
5. Verify futures, downstream calls, queries, or subscriptions are requested to cancel.
6. Verify cleanup runs only once even when cancellation and completion occur close together.
7. Verify no new messages are sent after the stream is cancelled.

Use CountDownLatch, controllable CompletableFutures, or fake resources to synchronize tests. Avoid long Thread.sleep calls, as they make tests flaky. For JDBC or HTTP clients, write dedicated adapter tests to confirm the driver/client actually stops I/O when requested.

## 11. Observing cancellation in production

Track by full method name and service:

- Number of RPCs exceeding deadline and number cancelled by the client.
- Duration from context cancellation until the worker stops.
- Number of futures/tasks still running after cancellation.
- Number of queries or downstream calls requested to cancel.
- Cleanup duration and error count while closing resources.
- Number of streams/producers still alive after the client leaves.
- Retry rate and duplicate side effects prevented by idempotency.

If clients time out yet workers keep running long afterward, the cancellation signal is not wired to tasks or I/O. If cancellation arrives quickly yet cleanup drags on, check whether resource closing is blocking or waiting on locks. Trace IDs help correlate client status, server context, and downstream calls.

## 12. Summary and self-check

When a deadline expires, gRPC cancels the RPC and the server observes a cancelled context. **The application must actively stop work**: check **Context.isCancelled()**, register listeners, cancel futures/downstream calls, apply timeouts/cancellation to I/O, and clean up resources idempotently. Context cancellation does not automatically interrupt every thread and does not roll back committed transactions.

Self-check:

1. Why does Context.isCancelled() not automatically stop a running JDBC query?
2. When should you use a cancellation listener instead of only checking state at the start of a handler?
3. Does Future.cancel(true) guarantee that every task stops immediately?
4. Why must cleanup be idempotent when deadline expiration and completion happen close together?
5. If the client receives DEADLINE_EXCEEDED after a transaction commits, what mechanism is needed for safe retries?

Properly cancelling work keeps Spring gRPC from wasting threads, connections, and downstream resources after a deadline expires, while protecting data consistency and system resilience.
