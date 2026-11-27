# Cleaning up resources when an RPC is cancelled

When a client cancels an RPC or the deadline expires, the server must stop the associated work and release the resources held by the call. If the handler merely stops sending responses while leaving database queries, downstream HTTP requests, subscriptions, or workers running, the system continues consuming resources for a result nobody is waiting for anymore.

**Cleaning up resources when an RPC is cancelled** is designing the lifecycle of resources opened while handling a call: who owns them, how cancellation requests stopping, where cleanup runs, and how to avoid duplicate closes or leaks when events arrive concurrently. This lesson belongs to the **Cancellation** chapter of the **SPRING_GRPC** module. The module develops gRPC services in the Spring ecosystem from Protocol Buffers contracts and generated Java code, supporting unary/streaming RPCs, metadata, deadlines, statuses, interceptors, TLS, integration testing, and observability. The focus here is managing resources according to the RPC lifecycle in a Spring/gRPC Java server.

## 1. Inventorying resources along the RPC lifecycle

A handler may open multiple resources throughout a call:

| Resource | Risk when RPC is cancelled | Common cleanup action |
| --- | --- | --- |
| JDBC ResultSet, Statement, Connection | Query keeps running; cursors and connections remain held. | Cancel the query if the driver supports it; close result set, statement, and connection in order. |
| HTTP client call to another service | Downstream request keeps running even though the original caller left. | Keep the call handle and invoke the HTTP client's cancel API. |
| Future/worker task | Thread keeps computing or waiting on I/O. | Emit a cancellation token, Future.cancel(true), and ask the underlying API to stop. |
| Subscription/message feed | Producer keeps emitting events and holding buffers. | Unsubscribe, stop the producer, and release queues. |
| File, stream, or buffer | File descriptors, memory, and temporary data are not released. | Close in finally or try-with-resources; delete temp files per ownership. |
| Downstream gRPC call | Sub-RPC continues after the original RPC was cancelled. | Cancel the specific call handle or propagate deadline/cancellation downstream. |

The rule is that **resources with a lifetime shorter than or equal to the RPC must be released when the RPC ends**. Do not close shared resources such as DataSource, connection pools, executors, or ManagedChannel just because a single call was cancelled; they belong to the application or Spring bean lifecycle.

## 2. Distinguishing a cancellation request from resource closing

Cancellation and cleanup are related, but they are not the same operation:

1. **Signal stop:** set a flag or emit a signal so the worker knows the RPC no longer needs the result.
2. **Cancel in-flight I/O:** call a specialized API like Statement.cancel() or Call.cancel() to try to make a blocking operation terminate early.
3. **Close resources:** release cursors, statements, connections, subscriptions, files, or buffers after the work has stopped or according to the resource's safety contract.
4. **Stop emitting responses:** do not produce further messages after the call is cancelled; do not try to send an error in place of a response to a client that has already closed the call.

A cancellation callback should do brief work and not wait on the worker. Closing a resource can block or be unsafe while the worker is still using it. Therefore, the callback usually emits a signal and invokes a specialized cancel API; the worker or resource owner performs close in finally once the operation has exited.

Typical flow: RPC starts → open call-owned resources → perform work → client cancels or deadline expires → emit stop signal → cancel I/O/worker if possible → worker exits → close resources → complete call lifecycle.

Context.CancellationListener and ServerCallStreamObserver.setOnCancelHandler(...) help receive the signal; they do not automatically close application-created resources. Cleanup must be explicitly wired to the owner.

## 3. Using try-with-resources for synchronous work

If the handler performs synchronous work on the same thread, try-with-resources is a simple and reliable way to close resources whether it succeeds, throws an error, or exits early:

    @Override
    public void getStock(
            StockRequest request,
            StreamObserver<StockReply> responseObserver) {

        Context rpcContext = Context.current();
        if (rpcContext.isCancelled()) {
            return;
        }

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(
                     "select available_units from inventory where sku = ?")) {

            statement.setQueryTimeout(2);
            statement.setString(1, request.getSku());

            try (ResultSet resultSet = statement.executeQuery()) {
                if (rpcContext.isCancelled()) {
                    return;
                }

                int units = resultSet.next() ? resultSet.getInt(1) : 0;
                if (rpcContext.isCancelled()) {
                    return;
                }

                responseObserver.onNext(StockReply.newBuilder()
                        .setAvailableUnits(units)
                        .build());
                responseObserver.onCompleted();
            }
        } catch (SQLException failure) {
            if (!rpcContext.isCancelled()) {
                responseObserver.onError(Status.INTERNAL
                        .withDescription("Unable to read inventory")
                        .withCause(failure)
                        .asRuntimeException());
            }
        }
    }

Connection, PreparedStatement, and ResultSet are closed in the reverse order of opening. On return, exception, or when cancellation has been detected at a checkpoint, the resources are still closed. setQueryTimeout(2) is an additional limit for the query; whether the driver enforces the timeout and its precision depend on the JDBC driver/database.

However, if executeQuery() is blocking, checking rpcContext.isCancelled() after the statement does not stop the query immediately. To interrupt in-flight I/O, you need to wire cancellation to Statement.cancel() or the driver's timeout/cancel mechanism. try-with-resources guarantees close after control flow exits; it does not cancel a blocking call on its own.

## 4. Cancelling a running JDBC query while closing resources in the right owner

With JDBC, one approach is keeping a reference to the current statement, registering a listener to request query cancellation, while the handler closes the result set, statement, and connection in try-with-resources:

    Context rpcContext = Context.current();
    AtomicReference<Statement> activeStatement = new AtomicReference<>();
    AtomicBoolean cancellationRequested =
            new AtomicBoolean(rpcContext.isCancelled());

    Context.CancellationListener listener = ignored -> {
        cancellationRequested.set(true);
        Statement statement = activeStatement.get();
        if (statement != null) {
            cancellationExecutor.execute(() -> {
                try {
                    statement.cancel();
                } catch (SQLException cancelFailure) {
                    log.debug("Unable to cancel JDBC statement", cancelFailure);
                }
            });
        }
    };
    rpcContext.addListener(listener, Runnable::run);

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(SQL)) {

        activeStatement.set(statement);
        statement.setQueryTimeout(3);

        // Cancellation may arrive before the statement is stored in the reference.
        if (cancellationRequested.get() || rpcContext.isCancelled()) {
            cancellationExecutor.execute(() -> cancelQuietly(statement));
            return;
        }

        try (ResultSet resultSet = statement.executeQuery()) {
            // Convert result to response if the call still needs the result.
        }
    } finally {
        activeStatement.set(null);
        rpcContext.removeListener(listener);
    }

cancellationExecutor is a bounded executor managed at the application level; do not create a new thread per cancellation. The listener only sets a flag and dispatches the cancel request to the executor to avoid executing a potentially blocking JDBC operation directly on the cancellation callback. The handler remains the owner closing ResultSet, Statement, and Connection via try-with-resources.

The example has two safeguards: checking the flag after the statement is stored to handle early cancellation, and query timeout to bound duration if the driver does not respond quickly to cancel. In real code, handle executor task rejection, bound query wait time, log cancel errors selectively, and verify the driver supports Statement.cancel(). Do not close a shared connection pool from a cancellation listener.

## 5. Managing worker tasks and cleanup when work runs on an executor

If the handler offloads work to an ExecutorService, keep the task handle and wire cancellation to the worker:

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
            try (ReportCursor cursor = reportService.openCursor(request)) {
                if (cancelled.get() || rpcContext.isCancelled()) {
                    return;
                }

                ReportReply reply = buildReply(cursor);
                if (!cancelled.get() && !rpcContext.isCancelled()
                        && !Thread.currentThread().isInterrupted()) {
                    responseObserver.onNext(reply);
                    responseObserver.onCompleted();
                }
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
        if (cancelled.get() || rpcContext.isCancelled()) {
            task.cancel(true);
        }
    } catch (RejectedExecutionException rejected) {
        rpcContext.removeListener(listener);
        if (!rpcContext.isCancelled()) {
            responseObserver.onError(Status.RESOURCE_EXHAUSTED
                    .withDescription("Server is overloaded")
                    .withCause(rejected)
                    .asRuntimeException());
        }
    }

ReportCursor is an assumed AutoCloseable resource; the worker closes it in try-with-resources. rpcContext.wrap(...) propagates the RPC context to the worker. Future.cancel(true) requests an interrupt but does not force-stop an uncooperative API. Blocking operations still require their own timeout or cancel API.

A race must be handled: cancellation may occur before taskRef is assigned. The listener sets the flag; after submission, the handler rechecks the flag and cancels the task if needed. One additional detail in production implementations: if the task is cancelled while still in the queue and never starts, the finally block inside the task may not run. Therefore, the owner must have a mechanism to remove the listener/close the scope when the task is cancelled before execution, such as using a task wrapper with done() cleanup or an idempotent lifecycle coordinator. Do not rely solely on the finally block of the task body for the case where the task never ran.

## 6. Idempotent cleanup and resource closing order

Cancellation, errors, and normal completion can happen close together. A resource may be requested to close from multiple paths; cleanup must be safe when called multiple times. Use an atomic flag or a scope with clear ownership:

    public final class RpcResourceScope implements AutoCloseable {

        private final Object lock = new Object();
        private final Deque<AutoCloseable> resources = new ArrayDeque<>();
        private boolean closed;

        public <T extends AutoCloseable> T add(T resource) {
            boolean closeNow;
            synchronized (lock) {
                closeNow = closed;
                if (!closed) {
                    resources.push(resource);
                }
            }
            if (closeNow) {
                closeQuietly(resource);
            }
            return resource;
        }

        @Override
        public void close() {
            Deque<AutoCloseable> snapshot;
            synchronized (lock) {
                if (closed) {
                    return;
                }
                closed = true;
                snapshot = new ArrayDeque<>(resources);
                resources.clear();
            }

            while (!snapshot.isEmpty()) {
                closeQuietly(snapshot.pop());
            }
        }

        private static void closeQuietly(AutoCloseable resource) {
            try {
                resource.close();
            } catch (Exception ignored) {
                // Production code should log safely without masking the primary error.
            }
        }
    }

The scope closes resources in LIFO order: resources registered later are closed first. For example, if you register connection first, statement second, and result set last, cleanup closes result set, statement, then connection. close() is idempotent thanks to the closed flag checked/updated inside the synchronized block; resources added after the scope has closed are closed immediately.

This scope is a resource ownership mechanism, not a cancellation engine. Do not call scope.close() directly on the cancellation callback if closing a resource can block or the worker is still using it. The callback should emit a stop signal or call a specialized cancel API; the owner closes the scope when the work ends. If cleanup must run on an executor, ensure the executor still accepts tasks during shutdown and have a plan for handling rejection.

## 7. Cleaning up resources in streaming RPCs

Streaming RPCs often hold subscriptions, cursors, or producers longer than a single method invocation. The server needs to close the subscription when the client cancels, when the stream finishes normally, and when the stream errors. A handle management pattern:

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

        // Cancellation may arrive while subscribe is creating the handle.
        if (stopped.get() || call.isCancelled()) {
            cleanup.run();
        }
    }

Subscription is a handle provided by the application's priceFeed. The handler is registered before starting the subscription; if cancellation occurs before the handle is stored, the stopped flag is rechecked right after the subscription is created and the handle is closed. getAndSet(null) ensures only one branch obtains the handle to close it. Cleanup also removes the listener, so when the stream completes normally or errors, the handler only needs to call cleanup.run() in the terminal path before finishing the observer.

Subscription.close() in the example needs to be a cancel/close operation conforming to priceFeed's contract. If it can block, the cancellation callback should not invoke it directly; emit a signal and hand cleanup off to the appropriate executor/owner. If priceFeed callbacks run concurrently on multiple threads, serialize onNext per the gRPC contract. For producers faster than the client, implement flow control with isReady()/setOnReadyHandler(...) or a bounded queue; do not drop messages just because the observer is temporarily not ready.

## 8. Cleaning up downstream calls and related resources

An RPC server may call another gRPC service or an HTTP API. If the root RPC is cancelled, the downstream call should not continue indefinitely. Keep the downstream call handle or context to propagate cancellation:

- With an async gRPC stub, use ClientResponseObserver.beforeStart(...) to get ClientCallStreamObserver and call cancel(...) when the root RPC is cancelled.
- With an HTTP client, retain the request handle and call cancel/dispose per the library's API.
- With a database, use a query timeout or Statement.cancel() if the driver supports it.
- With a file or stream, close in the proper owner via try-with-resources/finally.

When calling downstream gRPC, pass the remaining deadline from the root RPC's context instead of re-granting the full initial timeout. If the deadline has expired or the context is already cancelled, do not start a new downstream call. Deadlines bound time; cancellation reflects that the caller abandoned the call; both need to be propagated across layers to avoid orphaned work.

## 9. Testing resource cleanup

Tests should not only verify that the client receives CANCELLED; they should verify resources are actually released. A unit test can use a fake resource counting close calls:

    AtomicInteger closeCount = new AtomicInteger();
    AutoCloseable fakeResource = closeCount::incrementAndGet;

    RpcResourceScope scope = new RpcResourceScope();
    scope.add(fakeResource);

    scope.close();
    scope.close();

    assertEquals(1, closeCount.get());

This test verifies RpcResourceScope.close() is idempotent. Add a race test: add a resource concurrently with close and verify the resource is closed exactly once. For JDBC, use a fake Statement or test database to verify cancel() is called and result set/statement/connection are closed.

With a gRPC in-process server, create a handler holding a fake resource, register a cancellation listener, then cancel the client call. Use a CountDownLatch to wait for the signal and verify resource close/cancel is executed. Important tests include:

1. Client cancels while a query is running; verify statement cancel is requested and resources close after the worker exits.
2. Deadline expires; verify cleanup matches the cancellation path and no further responses are sent.
3. Handler completes normally; verify resources still close even without cancellation.
4. Handler throws an error; verify resources close and the error is translated to an appropriate status.
5. Cancellation arrives before the subscription/task handle is stored; verify the handle is closed immediately after creation.
6. Cleanup is invoked from multiple paths; verify idempotency and that shared resources are not closed.

In-process tests verify lifecycle logic; integration tests over TCP/TLS are still needed to evaluate cancellation propagation across proxies, DNS, transport, and client-disconnect detection latency.

## 10. Common mistakes

| Symptom | Cause | How to fix |
| --- | --- | --- |
| Client cancels but JDBC query keeps running | Only checking context after the query without cancelling blocking I/O. | Wire cancellation to Statement.cancel() and set a query timeout. |
| Connection pool closed when one RPC cancels | Confusing per-call resources with application-wide shared resources. | Only close connection/statement/result set owned by the call; keep the pool alive. |
| Resource closed while worker still uses it | Cancellation callback directly closes all resources. | Callback emits signal/cancels; worker owner closes in finally. |
| Cleanup runs twice | Cancellation, error, and terminal callback all call close. | Use idempotent cleanup or RpcResourceScope. |
| Subscription leaked when cancel occurs during subscribe | Race before the handle is stored is not handled. | Register listener first, store handle, then recheck cancellation. |
| Task cancelled while still in queue but listener remains | finally inside task never ran. | Have task wrapper/owner cleanup for the case where the task never started. |
| Future.cancel(true) does not stop I/O | Underlying library does not cooperate with interrupts. | Use the database or HTTP client's dedicated cancel/timeout API. |
| Cancellation callback is slow | Performing close/blocking work directly inside the listener. | Emit only a quick signal; delegate lengthy cleanup to the owner/executor. |
| Retrying after cancellation creates duplicate side effects | Treating cancellation as rollback. | Use an idempotency key and check state before retrying. |

## 11. Hands-on exercises

1. Write a unary handler using try-with-resources for JDBC connection, statement, and result set; set a query timeout and check context before sending the response.
2. Register a Context.CancellationListener to call Statement.cancel() via a bounded executor; verify the worker closes resources in finally.
3. Create RpcResourceScope closing resources in LIFO order and idempotently; test a resource added after the scope has closed.
4. Create a server-streaming RPC using a subscription; cancel the subscription when the client cancels, the stream completes, or the stream errors.
5. Simulate cancellation occurring before the worker/subscription handle is stored; verify no resource leak occurs.
6. Call downstream gRPC/HTTP from a handler; propagate cancellation and remaining deadline to the sub-call, then verify the sub-call also terminates.
7. Write an in-process test verifying resource cleanup actually happens, not merely verifying the client receives status CANCELLED.

After this lesson, you should be able to identify which resources belong to an RPC, distinguish a cancellation request from a close operation, wire cancellation to specialized I/O APIs, and ensure idempotent cleanup in the right owner. Proper resource lifecycle handling helps a Spring gRPC server avoid orphaned queries, workers, and subscriptions when clients cancel calls or deadlines expire.
