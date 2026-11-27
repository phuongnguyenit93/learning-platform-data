# Testing mid-flight cancellation

A cancellation test is only valuable when it proves the call is stopped at the right moment and server-side work actually reacts. A test that merely calls future.cancel(true) and verifies the future is in the cancelled state does not prove the gRPC call received the signal, the worker stopped, or resources were released.

**Testing mid-flight cancellation** focuses on controlling an in-flight RPC, actively cancelling the call or letting the deadline expire, and observing both client and server. This lesson belongs to the **Cancellation** chapter of the **SPRING_GRPC** module, where gRPC services are developed in the Spring ecosystem using Protocol Buffers contracts and generated Java code, supporting unary/streaming RPCs, metadata, deadlines, statuses, interceptors, TLS, integration testing, and observability.

## 1. What a cancellation test must prove

A complete test should verify four aspects:

1. **Client terminates properly:** explicit cancellation typically ends the client call with CANCELLED; deadline expiration typically yields DEADLINE_EXCEEDED.
2. **Server receives the signal:** the RPC's Context transitions to cancelled or ServerCallStreamObserver invokes the cancellation handler.
3. **Work stops:** the worker does not proceed to the next processing step, downstream calls are requested to cancel, or the producer stops emitting messages.
4. **Resources are released:** subscriptions, cursors, statements, or call-owned resources are cleaned up exactly once.

In addition, if the test checks side effects, you must place a clear synchronization point before the side effect. Cancelling the call after the handler has already passed the commit point cannot prove rollback; in that case, the correct result may be that the operation committed and the client must look it up via an idempotency key.

## 2. Using the in-process transport to control timing

gRPC Java provides InProcessServerBuilder and InProcessChannelBuilder to create a server/channel within the same process. This approach suits integration tests at the gRPC call-lifecycle level:

- No need to open TCP ports.
- Test-double services can be attached directly to the server.
- You can control when a handler starts, continues, or finishes using CountDownLatch.
- Cancellation from client to server can be observed without depending on DNS or external networks.

The test needs the grpc-inprocess dependency at the same version as the other gRPC Java libraries. Gradle example when not using a BOM:

~~~kotlin
testImplementation("io.grpc:grpc-inprocess:<grpc-version>")
~~~

If the project manages versions via a gRPC BOM, use the project's existing version alignment instead of declaring an independent version. This lesson uses JUnit 5 for assertions and lifecycle fixtures.

## 3. Creating a server handler that can pause at a deterministic point

To cancel cleanly mid-flight, the test server service needs a latch signaling that the handler has entered processing and a latch letting the test decide when the worker continues. A cancellation listener records the signal from gRPC:

~~~java
final class BlockingGreeter extends GreeterGrpc.GreeterImplBase {

    final CountDownLatch handlerStarted = new CountDownLatch(1);
    final CountDownLatch allowContinue = new CountDownLatch(1);
    final CountDownLatch cancellationObserved = new CountDownLatch(1);
    final CountDownLatch handlerFinished = new CountDownLatch(1);
    final AtomicInteger sideEffectCount = new AtomicInteger();
    final AtomicInteger resourceCloseCount = new AtomicInteger();
    final AtomicInteger responseCount = new AtomicInteger();

    @Override
    public void sayHello(
            HelloRequest request,
            StreamObserver<HelloReply> responseObserver) {

        Context rpcContext = Context.current();
        Context.CancellationListener listener =
                ignored -> cancellationObserved.countDown();
        rpcContext.addListener(listener, Runnable::run);

        handlerStarted.countDown();
        try {
            // Hold the handler mid-work until the test lets it continue.
            allowContinue.await();

            // Do not start side effects if cancellation has already been received.
            if (rpcContext.isCancelled()) {
                return;
            }

            sideEffectCount.incrementAndGet();
            responseObserver.onNext(HelloReply.newBuilder()
                    .setMessage("Hello " + request.getName())
                    .build());
            responseCount.incrementAndGet();
            responseObserver.onCompleted();
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
        } finally {
            rpcContext.removeListener(listener);
            resourceCloseCount.incrementAndGet();
            handlerFinished.countDown();
        }
    }
}
~~~

This is a test service intentionally holding the handler at one point. In a real application, the wait is replaced by a database call, downstream RPC, business processing, or stream producer. resourceCloseCount represents a fake resource released in finally; if testing a specific resource, use a fake AutoCloseable and count close() invocations.

The handler only increments sideEffectCount after being allowed to continue and after checking context. The test can cancel the call while the handler is waiting, verify cancellation arrived, and only then open the latch. Thus the test proves the server does not cross the side-effect boundary after cancellation has been observed.

## 4. Creating server/channel fixtures and closing the lifecycle properly

The server should run handlers on a separate executor so awaiting the latch does not block the thread sending requests from the test. The fixture below uses the in-process transport:

~~~java
class CancellationIntegrationTest {

    private final String serverName = InProcessServerBuilder.generateName();
    private final BlockingGreeter service = new BlockingGreeter();
    private final ExecutorService serverExecutor =
            Executors.newFixedThreadPool(2);

    private Server server;
    private ManagedChannel channel;

    @BeforeEach
    void startGrpc() throws IOException {
        server = InProcessServerBuilder.forName(serverName)
                .executor(serverExecutor)
                .addService(service)
                .build()
                .start();

        channel = InProcessChannelBuilder.forName(serverName)
                .directExecutor()
                .build();
    }

    @AfterEach
    void stopGrpc() throws InterruptedException {
        // Prevent failing tests from leaving server workers stuck on the latch.
        service.allowContinue.countDown();

        if (channel != null) {
            channel.shutdownNow();
            channel.awaitTermination(2, TimeUnit.SECONDS);
        }
        if (server != null) {
            server.shutdownNow();
            server.awaitTermination(2, TimeUnit.SECONDS);
        }

        serverExecutor.shutdownNow();
        serverExecutor.awaitTermination(2, TimeUnit.SECONDS);
    }
}
~~~

directExecutor() on the channel runs client callbacks directly on the call's executor; the server still uses its separate serverExecutor. In larger tests, you can use a dedicated executor for client callbacks if you need to test concurrency. Always open the latch in teardown so a failed test does not block workers indefinitely.

## 5. Testing explicit cancellation while the handler is running

The client uses ClientResponseObserver.beforeStart(...) to obtain ClientCallStreamObserver, then cancels the specific running call:

~~~java
@Test
void explicitCancelStopsWorkBeforeSideEffect() throws Exception {
    AtomicReference<ClientCallStreamObserver<HelloRequest>> callRef =
            new AtomicReference<>();
    AtomicReference<Throwable> clientFailure = new AtomicReference<>();
    CountDownLatch clientTerminal = new CountDownLatch(1);
    AtomicInteger clientMessageCount = new AtomicInteger();

    ClientResponseObserver<HelloRequest, HelloReply> observer =
            new ClientResponseObserver<>() {
                @Override
                public void beforeStart(
                        ClientCallStreamObserver<HelloRequest> call) {
                    callRef.set(call);
                }

                @Override
                public void onNext(HelloReply reply) {
                    clientMessageCount.incrementAndGet();
                }

                @Override
                public void onError(Throwable failure) {
                    clientFailure.set(failure);
                    clientTerminal.countDown();
                }

                @Override
                public void onCompleted() {
                    clientTerminal.countDown();
                }
            };

    GreeterGrpc.newStub(channel).sayHello(
            HelloRequest.newBuilder().setName("Lan").build(),
            observer);

    assertTrue(service.handlerStarted.await(2, TimeUnit.SECONDS));
    ClientCallStreamObserver<HelloRequest> call = callRef.get();
    assertNotNull(call);

    call.cancel("Test cancels while handler is active", null);

    assertTrue(service.cancellationObserved.await(2, TimeUnit.SECONDS));
    assertTrue(clientTerminal.await(2, TimeUnit.SECONDS));

    // Let the worker continue after the server has observed cancellation.
    service.allowContinue.countDown();
    assertTrue(service.handlerFinished.await(2, TimeUnit.SECONDS));

    assertEquals(Status.Code.CANCELLED,
            Status.fromThrowable(clientFailure.get()).getCode());
    assertEquals(0, service.sideEffectCount.get());
    assertEquals(0, service.responseCount.get());
    assertEquals(0, clientMessageCount.get());
    assertEquals(1, service.resourceCloseCount.get());
}
~~~

The order in the test is very important:

1. Await handlerStarted to know the server has entered the RPC.
2. Cancel the call from the client.
3. Await cancellationObserved to know the server context actually received the signal.
4. Await the client terminal callback.
5. Open allowContinue so the handler reaches the cancellation check and exits.
6. Await handlerFinished, then assert side effects and cleanup.

Do not open allowContinue immediately after call.cancel(...) and immediately check side effects; at that moment the cancellation listener might not have run yet. Latches create a deterministic event order without needing Thread.sleep().

In the test above, onNext only increments the response counter, while the server also increments a counter before calling onCompleted. In real test code, use a separate counter for messages received by the client and a server-side counter for emitted messages to distinguish two facts: whether the server called the observer versus whether the client received the response.

## 6. Testing deadline expiration separately from explicit cancel

Deadline expiry also cancels the call on the server, but the client-side status differs from explicit cancellation. Create a call with a deadline shorter than the handler wait time:

~~~java
@Test
void deadlineExpiryCancelsServerWork() throws Exception {
    AtomicReference<Throwable> clientFailure = new AtomicReference<>();
    CountDownLatch clientTerminal = new CountDownLatch(1);
    AtomicInteger clientMessageCount = new AtomicInteger();

    ClientResponseObserver<HelloRequest, HelloReply> observer =
            new ClientResponseObserver<>() {
                @Override
                public void beforeStart(
                        ClientCallStreamObserver<HelloRequest> call) {
                    // No need to retain the handle because the deadline ends the call automatically.
                }

                @Override
                public void onNext(HelloReply reply) {
                    clientMessageCount.incrementAndGet();
                }

                @Override
                public void onError(Throwable failure) {
                    clientFailure.set(failure);
                    clientTerminal.countDown();
                }

                @Override
                public void onCompleted() {
                    clientTerminal.countDown();
                }
            };

    GreeterGrpc.newStub(channel)
            .withDeadlineAfter(2, TimeUnit.SECONDS)
            .sayHello(
                    HelloRequest.newBuilder().setName("Lan").build(),
                    observer);

    assertTrue(service.handlerStarted.await(2, TimeUnit.SECONDS));
    assertTrue(clientTerminal.await(4, TimeUnit.SECONDS));
    assertTrue(service.cancellationObserved.await(2, TimeUnit.SECONDS));

    service.allowContinue.countDown();
    assertTrue(service.handlerFinished.await(2, TimeUnit.SECONDS));

    assertEquals(Status.Code.DEADLINE_EXCEEDED,
            Status.fromThrowable(clientFailure.get()).getCode());
    assertEquals(0, service.sideEffectCount.get());
    assertEquals(0, clientMessageCount.get());
    assertEquals(1, service.resourceCloseCount.get());
}
~~~

A one-second deadline is the call limit; the handler is held by the latch so it cannot finish before the deadline. The test awaits handlerStarted and the latches rather than relying on sleep to guess when the server started. In slow CI environments, you can increase the deadline and corresponding assertion wait times to avoid flaky tests.

The two tests should be kept separate: explicit cancel expects CANCELLED; deadline expiry expects DEADLINE_EXCEEDED. On the server, both can make Context.isCancelled() true. Checking only whether context is cancelled is insufficient to classify the cause; testing client-side status and the context deadline provides additional evidence.

## 7. Testing resource cleanup

A test that only verifies the client receives CANCELLED does not prove that JDBC statements, subscriptions, or workers were released. Create a fake resource with a counter:

~~~java
final class CountingResource implements AutoCloseable {
    private final AtomicInteger closeCount;

    CountingResource(AtomicInteger closeCount) {
        this.closeCount = closeCount;
    }

    @Override
    public void close() {
        closeCount.incrementAndGet();
    }
}
~~~

In the handler, place the resource in try-with-resources:

~~~java
try (CountingResource ignored =
             new CountingResource(service.resourceCloseCount)) {
    service.handlerStarted.countDown();
    service.allowContinue.await();
    if (rpcContext.isCancelled()) {
        return;
    }
    performSideEffect();
}
~~~

After cancellation is received and the handler exits, assert closeCount == 1. Add normal-completion and exception-throwing cases to verify the resource is closed on all terminal paths, not only cancellation.

For real resources, verify the right APIs:

- JDBC: verify Statement.cancel() is called when the call is cancelled; ResultSet, Statement, and handler-owned connections are closed.
- Subscription: verify cancel()/close() is called once even when cancellation races with subscribe() returning the handle.
- Worker: verify the task receives an interrupt or cancellation token and is no longer active after the handler finishes.
- Downstream gRPC: verify the child server receives cancellation via setOnCancelHandler.

Do not close a shared DataSource, connection pool, executor, or ManagedChannel in response to a single RPC's cancellation.

## 8. Testing side effects before and after commit

Cancellation tests must distinguish side effects that have not yet occurred from already-committed operations:

| When client cancels | Result to verify |
| --- | --- |
| Before handler starts | No side effect; handler may not be dispatched. |
| During processing, before commit point | Cancellation token is received; transaction rolls back; no business row/outbox row exists. |
| After commit, before response | Side effect still exists; client may receive cancellation/deadline and must look up status by idempotency key. |
| While downstream is processing | Child call is requested to cancel, but downstream may have already committed; verify idempotency/reconciliation. |

For Spring transactions, use an integration test with the appropriate transaction manager and database. Use a latch to pause right before commit, cancel the client call, then let the handler proceed to the cancellation check inside the transaction. After the transaction finishes, query the database from a new transaction to verify rollback.

To test the post-commit case, place a latch after commit but before sending the response. Cancel the parent call and verify the record still exists. This test protects an important expectation: cancellation is not a rollback and must not be treated as proof that the write operation did not occur.

## 9. Testing downstream RPC cancellation

When a parent server calls a child server, the test should have two in-process servers or a clear parent/child fixture:

1. The child service holds the call running and counts down a latch when ServerCallStreamObserver.setOnCancelHandler(...) is invoked.
2. The parent service calls the child using an async stub and retains ClientCallStreamObserver in ClientResponseObserver.beforeStart(...).
3. The client calls the parent RPC and waits for the child to confirm it has started.
4. The client cancels the parent call.
5. The test awaits the child cancellation latch and verifies the parent sends no further responses.
6. Open the child's latch so the worker exits; verify child resources are cleaned up.

Also test the race when the parent is cancelled before the child's beforeStart(...) stores the handle. The parent listener must set a flag; when the child handle appears, beforeStart reads the flag and cancels immediately. If the parent calls multiple children in parallel, verify all active children receive cancellation, while children belonging to other requests keep running.

## 10. Using latches/barriers instead of sleep

Thread.sleep(...) only waits for a period of time; it does not prove an event has occurred. A test like:

~~~java
call.cancel("test", null);
Thread.sleep(100);
assertTrue(service.cancelled);
~~~

can fail when CI is slow or pass randomly when scheduling is favorable. Replace it with:

~~~java
call.cancel("test", null);
assertTrue(service.cancellationObserved.await(2, TimeUnit.SECONDS));
~~~

Some principles:

- Each latch has one specific meaning: handler started, cancellation received, worker finished, client terminal.
- Use a finite timeout on await so tests do not hang indefinitely.
- Always open latches in finally/teardown so workers can exit if an assertion fails.
- When you need to orchestrate multiple steps, use CyclicBarrier, multiple latches, or test hooks with explicit state.
- Avoid reusing one latch for multiple distinct events, as it becomes hard to tell what the test is waiting on.

## 11. When is testing over TCP/TLS needed?

The in-process transport tests call-lifecycle logic, observers, and context cancellation. It does not fully simulate:

- Abrupt TCP connection loss or killed peer processes.
- HTTP/2 resets, proxies, ingress, or service meshes.
- TLS handshakes, certificate rotation, and transport errors.
- Latency in detecting a silently severed connection.
- Infrastructure keepalive and idle-timeout policies.

Therefore, keep unit/in-process tests for deterministic logic and add a few integration tests over TCP/TLS for network behavior. There is no need to repeat the entire test matrix over the network; pick key cases such as explicit cancel, deadline expiry, peer disconnect, and downstream cleanup. When testing disconnect, verify the server detects cancellation within bounds consistent with transport configuration, without assuming it always happens instantaneously.

## 12. Common mistakes

| Test mistake | Why it is insufficient | How to improve |
| --- | --- | --- |
| Only asserting future.isCancelled() | Only proves the future was cancelled, not that the gRPC call stopped. | Keep the call handle and verify the server cancellation listener. |
| Only asserting client receives CANCELLED | Does not prove worker or resources were cleaned up. | Await handler completion and assert side-effect/resource counters. |
| Using Thread.sleep() to wait for cancellation | Timing-dependent and prone to flakiness. | Use CountDownLatch/CyclicBarrier. |
| Opening the latch right after cancel() | Worker may run ahead before the server receives the signal. | Await the cancellation latch before letting the worker continue. |
| Not cleaning up server/channel/executor | Threads and test resources leak into other tests. | Shut down in AfterEach; always release latches. |
| Testing only explicit cancel | Misses deadline expiry with a different status. | Have separate tests for CANCELLED and DEADLINE_EXCEEDED. |
| Assuming cancellation rolls back side effects | Commit may have already happened. | Test pre-commit and post-commit separately; test idempotency. |
| Using only in-process to draw conclusions about network disconnect | In-process does not simulate TCP/proxy/keepalive. | Add integration tests over TCP/TLS. |

## 13. Hands-on exercises

1. Create an in-process server with a handler containing a latch mid-work; actively cancel the client call and verify the server receives cancellation.
2. Assert client status CANCELLED, worker completion, zero side effects after cancellation, and resource closed exactly once.
3. Write a separate deadline-expiry test, asserting DEADLINE_EXCEEDED and that the server context transitions to cancelled.
4. Test cancellation while a child RPC is running; verify the parent listener cancels the child call and child cleanup completes.
5. Use latches to control cancellation before commit and after commit; verify rollback in the first case and durable state in the second.
6. Write a race test where cancellation arrives before the child call handle or subscription handle is stored.
7. Add a TCP/TLS integration test for peer disconnect and record the time from disconnect to cleanup.

After this lesson, you should be able to design cancellation tests with deterministic synchronization points, checking both client status and the reaction of the server, workers, and resources. In-process tests are well-suited for controlling mid-flight logic; TCP/TLS tests verify real transport behavior. Separating explicit cancellation, deadline expiry, and pre/post-commit side effects ensures your test suite accurately reflects the RPC lifecycle in a Spring gRPC system.
