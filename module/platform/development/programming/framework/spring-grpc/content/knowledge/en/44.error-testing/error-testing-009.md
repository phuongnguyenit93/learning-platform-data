# Testing Cancellation

In **SPRING_GRPC**, an RPC may end before the application use case completes. The client may explicitly cancel the call, the deadline may expire, or the connection may be closed. The server must recognize cancellation, safely stop work that can still be stopped, and release resources such as cursors, subscriptions, file handles, or background tasks.

Testing cancellation must verify both sides: the client receives the appropriate termination outcome, and the server actually stops processing and cleans up. Simply asserting that the client received `CANCELLED` is not enough, because a worker or database query may still be running. This lesson focuses on cancellation in gRPC Java/Spring adapters, propagating the signal into the application layer, and writing deterministic unit/in-process tests.

## 1. Distinguish Cancellation, Deadlines, and Business Errors

Three scenarios are often confused:

| Situation | Cause | Status Client Typically Sees | What Server Must Do |
| --- | --- | --- | --- |
| Client cancel | Caller no longer needs the result | `CANCELLED` | Stop stoppable work and clean up |
| Deadline expired | RPC duration exceeded the limit | `DEADLINE_EXCEEDED` | Handle as cancellation on server, stop dependencies |
| Business error | Business rule disallows the operation | Status per contract, e.g., `NOT_FOUND` | Return business error; do not treat as cancellation |

When the client cancels or a deadline expires, the server call is cancelled. On the server side, both causes must trigger the work-stopping path; do not rely on distinguishing the cause to decide whether to clean up.

Cancellation does not mean rolling back all side effects. If a transaction has already committed or a message has been published, gRPC cannot undo it automatically. For operations with side effects, define commit points, idempotency, and a way to query results when the client does not receive a response.

## 2. Server Recognizes Cancellation

In generated service implementations, the server's response observer is typically a `ServerCallStreamObserver`. The adapter can register `setOnCancelHandler` to be notified when the client cancels the call or the deadline expires:

```java
@Override
public void watchItems(
        WatchItemsRequest request,
        StreamObserver<ItemReply> responseObserver) {

    ServerCallStreamObserver<ItemReply> serverObserver =
            (ServerCallStreamObserver<ItemReply>) responseObserver;

    serverObserver.setOnCancelHandler(() -> {
        // Request the application operation to stop and release resources.
        cancellationSignal.cancel();
    });

    // Start processing the stream...
}
```

Only cast the observer in a server implementation running under the gRPC runtime. When unit tests invoke the method directly, tests must pass a compatible fake observer or test cancellation logic through a dedicated abstraction.

Do not call `observer.onError()` from the cancellation handler just to announce that the client cancelled. The transport has already terminated the call; the server needs to stop the producer and clean up. Once the call is cancelled, do not emit further `onNext`, `onCompleted`, or `onError`.

## 3. Decouple the Cancellation Signal from the gRPC API

Application/domain layers should not depend on `ServerCallStreamObserver` or `io.grpc.Context`. The adapter can translate cancellation into a pure Java abstraction:

```java
public interface CancellationSignal {
    boolean isCancelled();
    void cancel();
}
```

A simple implementation uses an atomic flag:

```java
public final class AtomicCancellationSignal
        implements CancellationSignal {

    private final AtomicBoolean cancelled = new AtomicBoolean();

    @Override
    public boolean isCancelled() {
        return cancelled.get();
    }

    @Override
    public void cancel() {
        cancelled.set(true);
    }
}
```

The application operation accepts the signal when cooperative stopping is needed:

```java
public interface WatchItemsUseCase {
    void stream(
            WatchItemsQuery query,
            CancellationSignal cancellation,
            Consumer<ItemView> emit);
}
```

The use case checks the signal at safe points:

```java
@Override
public void stream(
        WatchItemsQuery query,
        CancellationSignal cancellation,
        Consumer<ItemView> emit) {

    try (ItemCursor cursor = repository.openCursor(query)) {
        while (!cancellation.isCancelled() && cursor.hasNext()) {
            // I/O inside hasNext() may block; check again before emitting.
            if (cancellation.isCancelled()) {
                break;
            }
            emit.accept(ItemView.from(cursor.next()));
        }
    }
}
```

`try-with-resources` ensures the cursor is closed when the loop exits normally or throws an exception. Checking the signal cannot interrupt a blocking I/O call; the dependency still needs a query timeout or its own cancellation API.

## 4. Connect Server Cancellation to the Application Operation

The adapter creates a cancellation signal per RPC, registers the handler, and passes the signal into the use case:

```java
@Override
public void watchItems(
        WatchItemsRequest request,
        StreamObserver<ItemReply> responseObserver) {

    ServerCallStreamObserver<ItemReply> serverObserver =
            (ServerCallStreamObserver<ItemReply>) responseObserver;

    AtomicCancellationSignal cancellation =
            new AtomicCancellationSignal();

    serverObserver.setOnCancelHandler(cancellation::cancel);

    try {
        watchItemsUseCase.stream(
                new WatchItemsQuery(request.getCategory()),
                cancellation,
                item -> {
                    if (!cancellation.isCancelled()
                            && !serverObserver.isCancelled()) {
                        serverObserver.onNext(mapper.toProto(item));
                    }
                });

        if (!cancellation.isCancelled()
                && !serverObserver.isCancelled()) {
            serverObserver.onCompleted();
        }
    } catch (RuntimeException error) {
        if (!serverObserver.isCancelled()) {
            serverObserver.onError(errors.toStatus(error));
        }
    }
}
```

This is a synchronous style to illustrate the boundary. If the use case is long-running or blocking, do not hold the RPC handling thread for the entire stream; use a bounded executor and ensure the cancellation signal is propagated to the worker.

Each RPC must have its own signal. Do not store the signal in a field of a singleton Spring service because concurrent RPCs would overwrite or interfere with each other's state.

## 5. Cancel Asynchronous Tasks

If the adapter offloads work to an executor, it can store the `Future` and request cancellation when the call is cancelled:

```java
AtomicReference<Future<?>> taskRef = new AtomicReference<>();

serverObserver.setOnCancelHandler(() -> {
    cancellation.cancel();

    Future<?> task = taskRef.get();
    if (task != null) {
        task.cancel(true);
    }
});

Context rpcContext = Context.current();

Future<?> task = executor.submit(rpcContext.wrap(() -> {
    try {
        watchItemsUseCase.stream(
                query,
                cancellation,
                item -> {
                    if (!rpcContext.isCancelled()
                            && !serverObserver.isCancelled()) {
                        serverObserver.onNext(mapper.toProto(item));
                    }
                });

        if (!rpcContext.isCancelled()
                && !serverObserver.isCancelled()) {
            serverObserver.onCompleted();
        }
    } catch (RuntimeException error) {
        if (!rpcContext.isCancelled()
                && !serverObserver.isCancelled()) {
            serverObserver.onError(errors.toStatus(error));
        }
    } finally {
        closeResources();
    }
}));

taskRef.set(task);

// Cover the case where the call is cancelled before the Future is stored.
if (serverObserver.isCancelled()) {
    cancellation.cancel();
    task.cancel(true);
}
```

`Context.current().wrap(...)` preserves the gRPC Context when the task runs on a worker thread. This allows the worker to observe the current cancellation/deadline, though it does not automatically transfer Spring transactions, MDC, or other thread-locals to the new thread.

There is a race between registering the cancellation handler, submitting the task, and storing the `Future`. The example above rechecks state after storing the task; real applications should encapsulate registration, submission, and cancellation into a separately tested lifecycle helper. Do not call the observer from multiple workers; each stream should have only one producer responsible for emitting responses.

## 6. `Future.cancel(true)` Does Not Guarantee I/O Has Stopped

`cancel(true)` requests interrupting the running thread. It is effective for interrupt-cooperative tasks, such as waiting on a `CountDownLatch`, but does not guarantee all blocking I/O will stop.

Combine cancellation with each dependency's own mechanisms:

- JDBC: query timeouts, statement cancellation, or appropriate driver APIs.
- HTTP clients: connect/read/response timeouts and request cancellation if supported by the client.
- Blocking gRPC stubs: set deadlines on downstream calls; parent call cancellation should be propagated per design.
- File/object storage: close streams or call appropriate abort APIs.
- Reactive publishers: dispose/cancel subscriptions.
- Cursors/transactions: close resources in `finally`/try-with-resources; transaction rollback follows exceptions and the transaction manager, not gRPC cancellation automatically.

Do not treat `Thread.interrupt()` as the sole cancellation mechanism. Tests must verify resource cleanup and bounded wait times, not just check whether a thread received an interrupt.

## 7. Deadlines Also Trigger Server-Side Cancellation

The client sets a deadline on the RPC:

```java
CatalogServiceGrpc.CatalogServiceStub client =
        CatalogServiceGrpc.newStub(channel)
                .withDeadlineAfter(250, TimeUnit.MILLISECONDS);
```

When the deadline expires, the client usually receives `DEADLINE_EXCEEDED`; the server call is marked cancelled and the cancellation handler is invoked. The server side must use the remaining time to bound downstream operations, rather than letting queries keep running for seconds after the caller has timed out.

An RPC deadline does not automatically configure query timeouts for JDBC or HTTP clients. Read the remaining time from `Context.current().getDeadline()` and apply the smaller timeout between the remaining budget and the dependency's own limit. Reserve time for mapping/response; do not spend the entire budget on the final I/O step.

## 8. Unit Test Cancellation Logic Without a Server

You can test the application operation in isolation using a fake cancellation signal. The test controls cancellation timing with latches rather than `Thread.sleep`:

```java
@Test
void stopsReadingWhenCancellationIsRequested() throws Exception {
    AtomicCancellationSignal cancellation =
            new AtomicCancellationSignal();

    CountDownLatch waitingForSecondRead = new CountDownLatch(1);
    CountDownLatch releaseSecondRead = new CountDownLatch(1);
    AtomicInteger hasNextCalls = new AtomicInteger();
    AtomicBoolean cursorClosed = new AtomicBoolean();
    List<ItemView> emitted = new CopyOnWriteArrayList<>();

    ItemCursor cursor = new ItemCursor() {
        @Override
        public boolean hasNext() throws InterruptedException {
            if (hasNextCalls.incrementAndGet() == 1) {
                return true;
            }
            waitingForSecondRead.countDown();
            releaseSecondRead.await();
            return true;
        }

        @Override
        public Item next() {
            return new Item("item-1");
        }

        @Override
        public void close() {
            cursorClosed.set(true);
        }
    };
    when(repository.openCursor(query)).thenReturn(cursor);

    Future<?> work = executor.submit(() -> {
        useCase.stream(query, cancellation, emitted::add);
        return null;
    });

    assertTrue(waitingForSecondRead.await(2, TimeUnit.SECONDS));
    cancellation.cancel();
    releaseSecondRead.countDown();

    work.get(2, TimeUnit.SECONDS);
    assertEquals(1, emitted.size());
    assertTrue(cursorClosed.get());
}
```

The example assumes `ItemCursor` is an interface with `hasNext()`, `next()`, and `close()`; add imports/Mockito setup per your project. The test shows that cancellation can arrive while `hasNext()` is blocking, so the use case rechecks the signal before emitting the next item and still closes the cursor. It does not prove the gRPC server receives client cancellation; that requires adapter/transport tests.

## 9. In-Process Test: Client Explicitly Cancels a Server-Streaming RPC

In-process transport lets you call a generated async stub and cancel the call without opening a TCP port. Use `ClientResponseObserver` to obtain `ClientCallStreamObserver` inside `beforeStart`.

Service simulating long-running work using a latch:

```java
final class CancellableCatalogService
        extends CatalogServiceGrpc.CatalogServiceImplBase {

    final CountDownLatch started = new CountDownLatch(1);
    final CountDownLatch cancelled = new CountDownLatch(1);
    final CountDownLatch cleaned = new CountDownLatch(1);

    private final ExecutorService executor =
            Executors.newSingleThreadExecutor();

    private final CountDownLatch releaseWorker = new CountDownLatch(1);

    @Override
    public void watchItems(
            WatchItemsRequest request,
            StreamObserver<ItemReply> observer) {

        ServerCallStreamObserver<ItemReply> serverObserver =
                (ServerCallStreamObserver<ItemReply>) observer;

        AtomicReference<Future<?>> taskRef = new AtomicReference<>();

        serverObserver.setOnCancelHandler(() -> {
            cancelled.countDown();
            Future<?> task = taskRef.get();
            if (task != null) {
                task.cancel(true);
            }
        });

        Future<?> task = executor.submit(() -> {
            started.countDown();
            try {
                releaseWorker.await();
                if (!serverObserver.isCancelled()) {
                    serverObserver.onNext(ItemReply.getDefaultInstance());
                    serverObserver.onCompleted();
                }
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            } finally {
                cleaned.countDown();
            }
        });

        taskRef.set(task);
        if (serverObserver.isCancelled()) {
            task.cancel(true);
        }
    }

    void shutdown() {
        releaseWorker.countDown();
        executor.shutdownNow();
    }
}
```

The test starts an in-process server/channel and cancels after confirming the worker has started:

```java
@Test
void clientCancelStopsServerWorkAndRunsCleanup() throws Exception {
    CancellableCatalogService service =
            new CancellableCatalogService();

    String name = InProcessServerBuilder.generateName();
    Server server = InProcessServerBuilder.forName(name)
            .directExecutor()
            .addService(service)
            .build()
            .start();

    ManagedChannel channel = InProcessChannelBuilder.forName(name)
            .directExecutor()
            .build();

    AtomicReference<ClientCallStreamObserver<WatchItemsRequest>> callRef =
            new AtomicReference<>();

    try {
        ClientResponseObserver<WatchItemsRequest, ItemReply> response =
                new ClientResponseObserver<>() {
                    @Override
                    public void beforeStart(
                            ClientCallStreamObserver<WatchItemsRequest> call) {
                        callRef.set(call);
                    }

                    @Override
                    public void onNext(ItemReply value) {
                    }

                    @Override
                    public void onError(Throwable error) {
                    }

                    @Override
                    public void onCompleted() {
                    }
                };

        CatalogServiceGrpc.newStub(channel).watchItems(
                WatchItemsRequest.getDefaultInstance(), response);

        assertTrue(service.started.await(2, TimeUnit.SECONDS));
        assertNotNull(callRef.get());

        callRef.get().cancel("test cancellation", null);

        assertTrue(service.cancelled.await(2, TimeUnit.SECONDS));
        assertTrue(service.cleaned.await(2, TimeUnit.SECONDS));
    } finally {
        service.shutdown();
        channel.shutdownNow();
        server.shutdownNow();
        channel.awaitTermination(2, TimeUnit.SECONDS);
        server.awaitTermination(2, TimeUnit.SECONDS);
    }
}
```

The test proves client cancellation travels through the gRPC runtime, triggers the server handler, and runs worker cleanup. The abbreviated example omits response content assertions because the goal is the cancellation lifecycle. In a full test suite, capture `onError` on the client side and confirm status `CANCELLED` if that is the client API behavior you want to lock down.

`grpc-inprocess` must match the version of the other grpc-java dependencies. Do not use this test to conclude that TLS, HTTP/2 sockets, or proxy timeouts work properly.

## 10. Test Deadline Expiry

A deadline test is similar to a client cancel test, except it creates the call with a short time limit. The service keeps the worker running with a latch; the test confirms the cancellation handler is invoked after the deadline expires.

```java
CatalogServiceGrpc.CatalogServiceStub client =
        CatalogServiceGrpc.newStub(channel)
                .withDeadlineAfter(150, TimeUnit.MILLISECONDS);

AtomicReference<Throwable> clientError = new AtomicReference<>();
CountDownLatch clientFinished = new CountDownLatch(1);

ClientResponseObserver<WatchItemsRequest, ItemReply> response =
        new ClientResponseObserver<>() {
            @Override
            public void beforeStart(
                    ClientCallStreamObserver<WatchItemsRequest> call) {
            }

            @Override
            public void onNext(ItemReply value) {
            }

            @Override
            public void onError(Throwable error) {
                clientError.set(error);
                clientFinished.countDown();
            }

            @Override
            public void onCompleted() {
                clientFinished.countDown();
            }
        };

client.watchItems(WatchItemsRequest.getDefaultInstance(), response);

assertTrue(clientFinished.await(2, TimeUnit.SECONDS));
assertEquals(
        Status.Code.DEADLINE_EXCEEDED,
        Status.fromThrowable(clientError.get()).getCode());
assertTrue(service.cancelled.await(2, TimeUnit.SECONDS));
assertTrue(service.cleaned.await(2, TimeUnit.SECONDS));
```

Deadline tests depend on the scheduler and environment execution timing; use a timeout large enough for the server to begin processing and wait via latches with an upper bound wider than the deadline. Avoid `Thread.sleep(150)` because it does not prove the server received the call or finished cleanup. If the test environment is heavily loaded, use reasonable test timeouts and log latch states to diagnose flaky tests.

## 11. Cancellation and Streaming Flow Control

Cancellation and backpressure solve two different problems:

- Cancellation: the caller no longer needs the result; stop the entire call.
- Flow control/readiness: the caller still wants the stream, but temporarily cannot receive more messages.

With server-streaming, use `ServerCallStreamObserver.isReady()` and `setOnReadyHandler` to pace emission. When the call is cancelled, stop the producer and close resources. Do not use readiness as a substitute for a cancellation check; a call can be cancelled while the producer is waiting on the consumer.

With client-streaming/bidirectional streaming, cancellation must stop both input consumption and any downstream tasks currently processing. If each chunk is committed independently, already committed chunks remain after cancellation; the contract must specify resume, finalize, or cleanup semantics.

## 12. What Cancellation Does Not Do Automatically

| Wrong Assumption | Reality | What to Test/Design |
| --- | --- | --- |
| Client cancel automatically rolls back the database | Already committed transactions remain | Idempotency, transaction boundaries, and status queries |
| `Future.cancel(true)` stops all I/O | Many drivers/SDKs do not react to interrupts | Dependency timeouts and cancel APIs |
| Server stops immediately upon deadline expiration | Server must observe and propagate cancellation | Cancellation handler and dependency timeouts |
| Calling `onError(CANCELLED)` is required | Transport already closed the call due to client cancel | Stop the worker; do not send a second terminal signal |
| Context propagates automatically to all executors | Custom executors may lose Context | Capture and wrap Context when submitting |
| `isReady() == false` means cancelled | Only indicates transport is temporarily not ready | Use readiness for flow control, cancellation for aborting calls |
| Client seeing CANCELLED proves the worker stopped | Worker may still be running in the background | Assert server cancellation and cleanup latches |

## 13. Common Testing Mistakes

- Using `Thread.sleep` to wait for cancellation, leading to flaky tests.
- Asserting only the client-side status without checking server cleanup.
- Using an unbounded executor so tests cannot simulate overload.
- Failing to handle the race where cancellation occurs before the `Future` is stored.
- Calling `onError` from the cancellation handler while the worker also calls `onCompleted`.
- Sharing a single cancellation signal across multiple RPCs.
- Assuming interrupts always stop JDBC/HTTP calls.
- Using in-process tests to conclude TLS or network disconnect behavior.
- Failing to close channels, servers, executors, or cursors after tests.

## 14. Hands-On Exercises

1. Write a server-streaming adapter that registers `ServerCallStreamObserver.setOnCancelHandler`.
2. Create a pure Java `CancellationSignal` and pass it into the application use case.
3. Use a fake cursor to verify the use case stops looping and closes the cursor when the signal is cancelled.
4. Offload the worker using a bounded executor; capture and wrap the gRPC Context.
5. Write an in-process test where the client explicitly cancels the stream after the worker has started.
6. Assert that both the server cancellation handler and the cleanup latch are triggered.
7. Write a deadline test and verify the client receives `DEADLINE_EXCEEDED` while the server still cleans up.
8. Simulate a blocking dependency; verify query/read timeouts bound the stopping time.
9. Verify no `onNext`/`onCompleted` occurs after cancellation.
10. Verify already committed transactions/side effects are not assumed to roll back when the client cancels.

### Takeaways

**Cancellation is a signal to end the RPC and asks the server to safely stop any work that can still be stopped.** The adapter receives the signal via `ServerCallStreamObserver` or gRPC Context, translates it into an application cancellation abstraction, cancels the worker, and closes resources. `Future.cancel(true)` is only best-effort; dependencies need their own timeout/cancel APIs. Good tests must verify client status, the server cancellation handler, and actual cleanup using latches rather than fixed sleeps.

## References

- [gRPC — Cancellation](https://grpc.io/docs/guides/cancellation/)
- [gRPC — Deadlines](https://grpc.io/docs/guides/deadlines/)
- [gRPC Java — ServerCallStreamObserver](https://grpc.github.io/grpc-java/javadoc/io/grpc/stub/ServerCallStreamObserver.html)
- [gRPC Java — ClientCallStreamObserver](https://grpc.github.io/grpc-java/javadoc/io/grpc/stub/ClientCallStreamObserver.html)
- [gRPC Java — Context](https://grpc.github.io/grpc-java/javadoc/io/grpc/Context.html)
- [gRPC Java — InProcessServerBuilder](https://grpc.github.io/grpc-java/javadoc/io/grpc/inprocess/InProcessServerBuilder.html)
