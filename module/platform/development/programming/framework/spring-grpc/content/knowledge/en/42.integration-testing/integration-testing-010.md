# Cleaning Up Channels and Servers After Tests

## Learning Objectives

After this lesson, you will be able to:

- Distinguish the lifecycles of client ManagedChannel, gRPC Server, and Spring ApplicationContext.
- Shut down channels gracefully, await termination, and fall back to shutdownNow on timeout.
- Stop servers in a safe order, handle in-flight RPCs, and verify server termination.
- Cancel streaming calls before closing channels.
- Let Spring manage servers owned by a starter or lifecycle bean.
- Write safe teardown logic whether tests pass, fail, or get interrupted.
- Detect leaked channels, streams, threads, and executors after integration tests.

## 1. Why Is Cleanup Part of Integration Testing?

A gRPC integration test creates resources that outlive a normal Java method call: ManagedChannel, HTTP/2 transport, connections, executors, server listeners, streaming calls, and sometimes service worker threads. If tests fail to close these resources properly, the suite can hold onto sockets/threads after tests finish, leaving ports occupied, affecting subsequent tests, or preventing the JVM from exiting.

In **SPRING_GRPC**, distinguish resources created by the test from resources managed by Spring. Tests usually own client channels; the Spring context or gRPC starter owns the server. Cleaning up the channel in a test method's teardown does not mean stopping the server after every method, because Spring Test can cache and reuse the context.

Proper cleanup must be bounded, ordered, and verified. Calling shutdown only initiates closing; tests must await awaitTermination and provide a fallback if resources do not terminate.

## 2. Who Owns Which Resource?

| Resource | Typical Owner | Cleanup Timing |
| --- | --- | --- |
| Client ManagedChannel | Test or client fixture | After all RPCs/streams in the test have finished. |
| Generated stub | Test, created from channel | No separate close; stop using when channel closes. |
| Client interceptor channel wrapper | Test, wrapping underlying channel | Close underlying channel; wrapper is not an independent ManagedChannel. |
| Starter-managed gRPC Server | Spring gRPC starter/Spring lifecycle | When the ApplicationContext closes. |
| Self-managed server fixture | Test fixture or Spring test bean | After client channels have closed. |
| Streaming call | Test/client code | Cancel or wait for terminal callback before teardown. |
| Executor/service worker | Spring bean or test fixture | Executor owner shuts it down after related work completes. |

Do not close a resource merely because you hold a reference to it. Identify who created it and who is responsible for stopping it. In particular, never call shutdownNow on a starter-managed server from @AfterEach; the context may still be shared with other tests.

## 3. ManagedChannel Has Two Shutdown Phases

ManagedChannel.shutdown() begins a graceful shutdown. The channel stops accepting new calls while giving in-flight calls a chance to finish. Next, call awaitTermination(timeout, unit) to wait a bounded duration for the channel to stop.

If the timeout expires before the channel terminates, shutdownNow() requests cancellation of remaining calls and closes transport faster. You can wait another short period to confirm termination:

~~~java
static void closeChannel(ManagedChannel channel)
        throws InterruptedException {
    if (channel == null) {
        return;
    }

    channel.shutdown();
    if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
        channel.shutdownNow();
        if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException(
                "ManagedChannel did not terminate");
        }
    }
}
~~~

Timeouts in the example are illustrative test values. Choose timeouts based on your suite and CI environment; never wait indefinitely because one hung call can stall the entire test process.

shutdownNow() is a forceful termination measure. Use it as a fallback after graceful shutdown, not as the default when RPCs can finish normally.

## 4. Cleaning Up Channels in JUnit and Spring Boot

For channels created per test method, @AfterEach is the appropriate place to close them:

~~~java
@SpringBootTest
class GreeterIntegrationTest {
    private ManagedChannel channel;
    private GreeterGrpc.GreeterBlockingStub stub;

    @BeforeEach
    void connect() {
        channel = ManagedChannelBuilder
            .forAddress("127.0.0.1", grpcTestEndpoint.port())
            .usePlaintext()
            .build();

        stub = GreeterGrpc.newBlockingStub(channel)
            .withDeadlineAfter(2, TimeUnit.SECONDS);
    }

    @AfterEach
    void tearDown() throws InterruptedException {
        closeChannel(channel);
        channel = null;
        stub = null;
    }
}
~~~

This example assumes grpcTestEndpoint is a port accessor for the server running in the Spring context. The channel belongs to the test and is closed after the method. The server is not stopped here if it belongs to a Spring-cached context.

If a channel is created in @BeforeAll and shared across the class, close it in @AfterAll. Do not close a channel after each method if subsequent methods still use it.

Stubs do not have a close() method. A stub is a lightweight object attached to a channel; closing the underlying channel releases the transport used by the stub.

## 5. Channel Wrappers and Interceptors

When using ClientInterceptors.intercept(channel, interceptor), the result is a Channel wrapper that attaches the interceptor to calls. This wrapper is not a new ManagedChannel and has no separate shutdown lifecycle.

~~~java
ManagedChannel managedChannel = ManagedChannelBuilder
    .forAddress("127.0.0.1", grpcTestEndpoint.port())
    .usePlaintext()
    .build();

Channel intercepted = ClientInterceptors.intercept(
    managedChannel,
    new CorrelationIdClientInterceptor());

GreeterGrpc.GreeterBlockingStub stub =
    GreeterGrpc.newBlockingStub(intercepted);

// When the test finishes, close managedChannel.
closeChannel(managedChannel);
~~~

Keep a reference to the original ManagedChannel for cleanup. Do not cast the wrapper to ManagedChannel or try to close the wrapper as an independent transport.

## 6. Graceful Server Shutdown

When a test owns its own gRPC server, cleanup is similar to channels but must account for calls the server is processing:

~~~java
static void closeServer(Server server)
        throws InterruptedException {
    if (server == null) {
        return;
    }

    server.shutdown();
    if (!server.awaitTermination(5, TimeUnit.SECONDS)) {
        server.shutdownNow();
        if (!server.awaitTermination(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException(
                "gRPC Server did not terminate");
        }
    }
}
~~~

Server.shutdown() initiates a graceful shutdown: the server stops accepting new calls and gives active calls a chance to complete. Server.shutdownNow() requests cancellation of remaining active calls. The server is only considered stopped once awaitTermination returns true or isTerminated() confirms it.

Do not check only isShutdown(): shutdown may have been requested while the server is still finishing calls and releasing resources. If you need to guarantee ports/threads are freed, await termination.

## 7. Closing Clients Before Servers

When a test owns both client and server, the typical cleanup order is:

1. Stop initiating new RPCs.
2. Cancel or wait for open streaming calls to finish.
3. Close the ManagedChannel and wait for channel termination.
4. Trigger graceful server shutdown and wait for server termination.
5. Shut down test-owned executors/workers after calls and the server no longer use them.

Closing the channel before the server lets the client finish calls and release transport while the server is still able to complete winding-down calls. If the server stops first, client calls can receive transport errors; that makes sense for restart/failure tests, not standard teardown.

If the server is managed by the Spring context, tests only close the channel. Spring or the starter stops the server when the context actually closes.

## 8. Handling Thread Interruption During Cleanup

awaitTermination can throw InterruptedException. Never swallow the exception and pretend cleanup succeeded. When interrupted, request forceful shutdown, restore the interrupt flag, and propagate the error:

~~~java
static void closeChannelPreservingInterrupt(
        ManagedChannel channel) throws InterruptedException {
    if (channel == null) {
        return;
    }

    channel.shutdown();
    try {
        if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
            channel.shutdownNow();
        }
    } catch (InterruptedException ex) {
        channel.shutdownNow();
        Thread.currentThread().interrupt();
        throw ex;
    }
}
~~~

If the helper is used in test teardown, let the test framework record the interruption. Do not convert InterruptedException into an RPC status or ignore it so a test passes green while resources remain uncleaned.

## 9. Streaming Calls Must Finish Before Teardown

Channel shutdown does not replace managing stream lifecycles. For infinite streams or streams waiting on input, tests should retain a handle to the call for cancellation:

~~~java
AtomicReference<ClientCallStreamObserver<WatchRequest>> callRef =
    new AtomicReference<>();
CountDownLatch terminal = new CountDownLatch(1);

stub.watchStock(
    WatchRequest.newBuilder().setSku("SKU-42").build(),
    new ClientResponseObserver<>() {
        @Override
        public void beforeStart(
                ClientCallStreamObserver<WatchRequest> call) {
            callRef.set(call);
        }

        @Override
        public void onNext(StockUpdate update) {
            // Collect messages for assertions.
        }

        @Override
        public void onError(Throwable error) {
            terminal.countDown();
        }

        @Override
        public void onCompleted() {
            terminal.countDown();
        }
    });

// After the test has verified enough data:
callRef.get().cancel("test finished", null);
assertTrue(terminal.await(2, TimeUnit.SECONDS));
~~~

In real tests, verify callRef.get() is non-null before cancelling and capture callback errors for scenario assertions. Cancellation usually delivers an onError terminal callback on the client; do not wait for onCompleted() on a cancelled stream.

For client-streaming, call requestObserver.onCompleted() once all input is sent to tell the server to finalize the response. For bidirectional streams, close each direction per contract or cancel the whole call. Never send onNext after a terminal event.

## 10. Service Executors and Background Work

gRPC server shutdown does not automatically manage custom executors created by services. If a handler offloads work to a custom ExecutorService, scheduler, or queue, the component that created the executor is responsible for shutting it down.

In Spring, shared executors should be lifecycle-managed beans. Do not shut down a singleton executor in @AfterEach if the application context remains cached and other tests still use that bean.

For test-created executors, clean up in order:

- Stop submitting new tasks.
- Call shutdown().
- Wait on awaitTermination with a timeout.
- Use shutdownNow() on timeout.
- Inspect cancelled tasks and handle any unstarted task list if needed.

Streaming services must tie RPC cancellation/deadlines to background work. If a client cancels while a worker keeps generating messages or querying dependencies, the test may finish while threads and buffers continue leaking.

## 11. Servers Managed by the Spring gRPC Starter

With an auto-configured server, never call server.shutdown() directly from tests if the starter owns its lifecycle. Spring Test typically caches ApplicationContext across test methods/classes with compatible configuration. As a result, the server may stay running after @AfterEach and be reused by subsequent tests.

Practical rules:

- Close test-created channels in @AfterEach or @AfterAll depending on scope.
- Let the starter/Spring stop the server when the context closes.
- Never call shutdownNow() on a shared server from an individual test method.
- If a test must force context closure after a class, consider @DirtiesContext at the appropriate scope.
- Do not put @DirtiesContext on every test by default, as restarting the context slows down the suite.

If the starter provides its own lifecycle/port accessor, use the API for that exact starter and version. Never spin up a manual server alongside an auto-configured server just so you can call stop.

## 12. Server Fixtures Managed by Spring

When you need to create a server manually for integration tests, register the fixture as a Spring bean with init/destroy methods or SmartLifecycle. When the context closes, Spring invokes the cleanup hook:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class GrpcServerTestConfiguration {
    @Bean(initMethod = "start", destroyMethod = "stop")
    TestGrpcServer testGrpcServer(GreeterServiceImpl service) {
        return new TestGrpcServer(service);
    }
}
~~~

TestGrpcServer.stop() should invoke graceful shutdown, await termination, and only then call shutdownNow() if the timeout expires. Do not declare both a destroy method and another lifecycle callback that both stop the server if that creates two cleanup owners; choose one consistent mechanism.

With context caching, the fixture lives alongside the context. Do not call stop() in @AfterEach; let Spring invoke it when the context actually closes.

## 13. @DirtiesContext and When the Server Stops

@DirtiesContext instructs Spring Test to evict the ApplicationContext from the cache and close it according to the annotation scope. Lifecycle beans are destroyed, including Spring-managed server fixtures.

Use it when a test mutates the context or needs to verify shutdown/restart behavior directly. Do not use it merely to release a test-created channel; channels can be closed directly.

If you need to test that the server stopped after context closure, hold a suitable observable reference to the fixture/test signal and verify termination. Do not access beans through an already-closed context and conclude cleanup failed simply because the bean can no longer be retrieved.

## 14. Cleanup When Assertions or Setup Fail

A test can fail after creating a channel but before initializing the stub. Store resources in fields and perform null-safe cleanup in teardown so nothing is missed.

If creating multiple channels or servers manually inside a test helper, use try/finally or an AutoCloseable fixture to guarantee cleanup:

~~~java
try (GrpcClientFixture client =
         GrpcClientFixture.connect("127.0.0.1", port)) {
    HelloReply reply = client.greeter()
        .sayHello(request);
    assertEquals("Hello, Linh", reply.getMessage());
}
~~~

The fixture's close() method should perform bounded graceful shutdown with forceful fallback. Avoid placing cleanup only after assertions in the test body; when an assertion throws, subsequent lines never execute.

## 15. Checking for Post-Test Leaks

Thorough cleanup tests can verify:

- The channel is terminated after teardown.
- The server fixture is terminated when the context closes.
- No unexpected stream observers/calls remain active.
- Test executors have terminated.
- Ports are released if the test owns the server.
- No background tasks continue writing to collections or logs of finished tests.

For diagnostics, record channel/server state, invocation counts, open stream counts, and thread names belonging to test executors. Do not rigidly assert total JVM thread counts since Spring, JUnit, and the runtime may spawn shared threads. Observe the resources owned by your test.

Never rely on GC or JVM exit to clean up channels or servers. Cleanup must be explicit and deterministic.

## 16. Common Mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Calling shutdown() only and ending the test | Channel may still remain active | Wait for awaitTermination with a timeout. |
| Calling only shutdownNow() | Cancels normal calls and hides lifecycle bugs | Graceful first, forceful on timeout. |
| Stopping starter server in @AfterEach | Breaks the server shared via context cache | Let Spring/starter own shutdown. |
| Stopping server before client streams finish | Calls receive unintended errors | Cancel/complete streams, close channel, then stop server. |
| Not cancelling infinite streams | Leaks calls, observers, and workers | Cancel and wait for terminal callback. |
| Closing wrapper channel instead of underlying channel | Unclear cleanup ownership | Keep and close the original ManagedChannel. |
| Shutting down singleton executor per test | Subsequent tests use a stopped executor | Let Spring manage shared executors. |
| Swallowing InterruptedException | Cleanup may be incomplete while test passes | Force shutdown, restore interrupt, and propagate error. |
| Waiting indefinitely for termination | Suite hangs when a resource gets stuck | Use finite timeouts and fallback. |
| Putting @DirtiesContext on every method | Slow suite due to constant context restarts | Close channels directly; dirty context only when needed. |

## 17. Cleanup Testing Matrix

An integration test suite should include:

1. Per-method channel: channel is shut down and terminated after each test.
2. Per-class channel: channel stays usable across methods and closes only after the class.
3. Starter-managed server: remains running across cached contexts and stops when context closes.
4. Spring-managed server fixture: destroy hook stops the server after context close.
5. Long-lived streaming call: cancellation ends both the call and worker.
6. Hung RPC: deadline/cancellation frees the call within timeout.
7. Cleanup timeout: shutdownNow fallback runs and test reports a leak if still unterminated.
8. Test fails mid-setup: already-created resources are still cleaned up via teardown/finally.
9. Test-specific executor: no remaining tasks/threads after fixture closes.

Tests should run reliably both independently and as part of the full suite to uncover leftover resources between tests.

## 18. Hands-On Exercise

Create a Spring gRPC integration test with both unary and streaming calls:

1. Start the server using starter lifecycle or a Spring test fixture.
2. Create a ManagedChannel in @BeforeEach and call a unary RPC with a deadline.
3. Open a server-streaming call, receive all data, and verify the terminal callback.
4. Open another long-lived stream and cancel it before teardown.
5. In @AfterEach, wait for graceful channel shutdown; fall back to forceful shutdown on timeout.
6. Verify the channel is terminated and the stream receives no further callbacks.
7. Let Spring stop the server when the context closes; if the test owns the server, close the server after the channel.
8. Write a test that intentionally fails after creating the channel and verify teardown still runs.

**Completion criteria:** every channel, stream, and server has a clear owner; graceful shutdown is preferred; timeouts and interrupts are handled; and Spring context caching is not broken by out-of-scope cleanup.

## 19. Takeaways

- ManagedChannel and Server support graceful shutdown, awaiting termination, and forceful shutdown.
- shutdown() initiates closing; awaitTermination() confirms the resource has finished stopping.
- Use shutdownNow() when graceful shutdown times out or when calls must be cancelled.
- Stop streaming calls before teardown and wait for terminal callbacks with a timeout.
- Close test-owned channels; let Spring/starter close context-owned servers.
- Self-managed server fixtures should be Spring lifecycle beans or cleaned up with try/finally.
- Context caching can keep the server alive across multiple test methods; do not stop a shared server in @AfterEach.
- Application/test-created executors and workers also need dedicated cleanup.
- Handle InterruptedException with forceful shutdown, interrupt flag restoration, and error propagation.
- Cleanup must be verified via terminated state and absence of lingering test background work.

Cleaning up channels and servers according to their lifecycles ensures Spring gRPC integration tests leave no leaked connections, streams, or threads while keeping shared Spring context servers stable across tests.
