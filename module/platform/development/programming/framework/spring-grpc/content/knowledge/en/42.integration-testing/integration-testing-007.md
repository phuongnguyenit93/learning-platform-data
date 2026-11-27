# Testing Retries and Server Restarts

## Learning Objectives

After this lesson, you will be able to:

- Distinguish retrying an RPC from ManagedChannel automatically reconnecting to the server.
- Configure a retry policy per service/method and choose retryable status codes.
- Understand when an RPC is committed and why not every failure can be safely retried.
- Design idempotent operations to avoid duplicate side effects when responses are lost.
- Test controlled retries using a server that returns UNAVAILABLE on the first few calls.
- Test server restarts, channel reconnection, and the boundaries of in-flight RPCs.
- Manage deadlines, wait-for-ready, health state, and server lifecycle in Spring integration tests.

## 1. Retries and Server Restarts Are Two Different Problems

When a gRPC server is temporarily unavailable, clients can encounter failures at two layers:

- **RPC retry**: the client re-executes an eligible call according to a retry policy. Each attempt may trigger a new execution on the server.
- **Channel reconnect**: ManagedChannel detects a broken connection and attempts to reconnect to the endpoint via its resolver/load balancer and backoff. Reconnecting does not automatically replay in-flight RPCs.

Distinguishing these two behaviors is critical when testing **SPRING_GRPC**. A channel can return to READY after the server restarts, yet calls that were in flight when the server stopped may have already failed. Conversely, a retry policy can re-invoke a unary RPC over the same channel if the call has not committed and the status is retryable.

A test that only verifies channel reconnection does not prove that the retry policy works. Likewise, a test that only verifies an RPC was called multiple times does not prove that the channel recovers after a server restart.

## 2. Types of Retries in gRPC

gRPC can perform retries in several situations:

1. **Transparent retry**: the runtime may retry when it knows the request has not been processed by the server application yet, such as when the call has not been dispatched to the server listener.
2. **Configured retry**: service config defines a retry policy for a method, including max attempts, backoff, and retryable status codes.
3. **Application retry**: the application re-invokes the operation itself after receiving an error. This approach requires manually managing deadlines, idempotency, and attempt counts.

Configured retry does not mean every error is retried. Only statuses listed in retryableStatusCodes are retried by the policy. For example, UNAVAILABLE usually fits transient failures; INVALID_ARGUMENT, UNAUTHENTICATED, or PERMISSION_DENIED typically cannot be resolved by resending the same request.

Do not confuse a retry policy with reconnection. Reconnection restores the transport; a retry policy decides whether a call should be resent.

## 3. When Is an RPC Committed?

The gRPC retry runtime retains call history within the limits of a retry buffer. A call can be retried while the runtime can still validly replay the request. Once a call is committed, the runtime will no longer automatically retry that call.

Conditions that can commit a call include:

- The client receives response headers from the server.
- The retry buffer can no longer hold the request history.
- The call passes a point where the runtime cannot guarantee safe replay under the retry contract.

For unary RPCs, servers typically send response headers together with or before the final response; thus retries are usually feasible only before the call commits. For streaming RPCs, requests and responses may already have exchanged multiple messages, making full stream replay more complex. Do not design uploads or bidirectional streams around an assumption that gRPC will replay the entire stream after any failure.

An already-committed RPC can still return an error to the client if the server or connection breaks before the client receives the final response. The client cannot conclude that the operation never happened solely from a transport error.

## 4. Choosing Retryable Status Codes

A retry policy must reflect operation semantics and failure causes:

| Status | Consider retrying? | Reason |
| --- | --- | --- |
| UNAVAILABLE | Usually yes | Server or dependency is temporarily unavailable; requires bounded attempts and backoff. |
| RESOURCE_EXHAUSTED | Only with a clear recovery policy | May indicate overload or quota exhaustion; immediate retries can worsen load. |
| ABORTED | Depends on transaction semantics | May require rerunning the entire transaction at the application layer. |
| DEADLINE_EXCEEDED | With caution | Further retries may lack remaining deadline and the previous operation might have completed. |
| INVALID_ARGUMENT | Usually no | An invalid request will remain invalid if resent. |
| UNAUTHENTICATED / PERMISSION_DENIED | No | Requires valid credentials or permissions, not retrying the same request. |
| FAILED_PRECONDITION | Usually no | Business preconditions must change before retrying. |

Status codes are part of the contract between client and server. Never return UNAVAILABLE for validation or business errors just to trigger retries. Doing so can cause clients to generate duplicate load and hide real bugs.

## 5. Configuring a Retry Policy via Service Config

gRPC Java supports service config to attach policies to a service or method. The example below limits retries for the unary GetStock method:

~~~java
Map<String, Object> retryPolicy = Map.of(
    "maxAttempts", 4.0,
    "initialBackoff", "0.1s",
    "maxBackoff", "1s",
    "backoffMultiplier", 2.0,
    "retryableStatusCodes", List.of("UNAVAILABLE"));

Map<String, Object> methodConfig = Map.of(
    "name", List.of(Map.of(
        "service", "acme.catalog.v1.CatalogService",
        "method", "GetStock")),
    "retryPolicy", retryPolicy);

Map<String, Object> serviceConfig = Map.of(
    "methodConfig", List.of(methodConfig));

ManagedChannel channel = ManagedChannelBuilder
    .forAddress("127.0.0.1", server.port())
    .defaultServiceConfig(serviceConfig)
    .build();
~~~

In the example, maxAttempts includes the initial attempt; a value of 4 means at most four total executions, not four retries plus the initial attempt. Backoff grows according to the multiplier up to maxBackoff. The runtime may also apply jitter to prevent multiple clients from retrying simultaneously.

Service and method names must match the full service name and method name in Protobuf. Malformed or mistyped service configs can be rejected when building the channel. Use configuration managed by a resolver or defaultServiceConfig appropriate for your project's gRPC Java version. Ensure retries are not disabled on the channel.

Do not apply a broad retry policy across all methods if some methods produce side effects. Prefer declaring policies on methods with explicit retry contracts.

## 6. Deadlines Span All Attempts

A deadline is the time budget for the entire RPC, not a separate budget per attempt. Backoff waiting time also consumes that budget.

~~~java
CatalogServiceGrpc.CatalogServiceBlockingStub stub =
    CatalogServiceGrpc.newBlockingStub(channel)
        .withDeadlineAfter(3, TimeUnit.SECONDS);

StockReply reply = stub.getStock(
    StockRequest.newBuilder()
        .setSku("SKU-42")
        .build());
~~~

If very little deadline remains after the first attempt, the runtime may not have time to execute the next attempt. Do not set an overly short deadline and mistakenly conclude that retries are broken. Conversely, an overly long deadline can hold resources open too long while the server is failing.

In integration tests, both RPC deadlines and test framework wait timeouts must be finite. Latch/future timeouts should be slightly longer than the RPC deadline so tests can observe the final outcome.

## 7. Idempotency Protects Side Effects During Retries

Retries can cause duplicate executions. For example, a client sends an order-creation request, the server persists the order successfully, but the response is lost due to a server restart. The client sees UNAVAILABLE and resends. If the server does not recognize duplicate requests, the system may create two orders.

An idempotent operation for a given idempotency key produces the same logical outcome when executed multiple times. Typical designs include:

- The client generates a unique request ID / idempotency key per logical operation.
- The server stores the key together with the result or processing state in durable storage.
- Upon receiving a previously processed key, the server returns the stored result instead of repeating side effects.
- Recording the key and applying the side effect must be atomic or backed by a consistent recovery mechanism.

~~~proto
message CreateOrderRequest {
  string idempotency_key = 1;
  string customer_id = 2;
  repeated OrderLine lines = 3;
}
~~~

Never generate a new idempotency key on each retry. Attempts belonging to the same operation must share the same key. Read operations are generally easier to make safe for retries; write operations require an explicit idempotency contract.

## 8. Controlled Retry Testing

A deterministic test can create a mock service that returns UNAVAILABLE on the first two calls and succeeds on the third. An invocation counter proves the actual number of attempts:

~~~java
final class RetryCatalogService
        extends CatalogServiceGrpc.CatalogServiceImplBase {
    final AtomicInteger attempts = new AtomicInteger();

    @Override
    public void getStock(
            StockRequest request,
            StreamObserver<StockReply> responseObserver) {
        int attempt = attempts.incrementAndGet();
        if (attempt < 3) {
            responseObserver.onError(
                Status.UNAVAILABLE
                    .withDescription("Temporary test failure")
                    .asRuntimeException());
            return;
        }

        responseObserver.onNext(
            StockReply.newBuilder().setAvailable(7).build());
        responseObserver.onCompleted();
    }
}
~~~

Start the server with this test service, build a channel with a retry policy for the exact method, call the stub, and assert:

~~~java
StockReply reply = stub.getStock(
    StockRequest.newBuilder().setSku("SKU-42").build());

assertEquals(7, reply.getAvailable());
assertEquals(3, retryService.attempts.get());
~~~

Tests need a deadline large enough for backoff, and no response headers should be sent prior to retryable errors. The server implementation in the example only calls onError; if metadata/headers are sent before the error, the call may become committed and retries will not happen as expected.

Do not use Thread.sleep to guess attempt counts. You can use latches in the test service to control each execution and observe invocation counts. Keep backoff small yet finite so the suite does not slow down.

## 9. Retries Do Not Replace Application-Level Resume for Streaming

For client-streaming or bidirectional streaming, errors can occur after the server has already received and processed part of the messages. Opening a new stream does not automatically restore the processing position.

Design resume at the application layer:

- Attach a sequence number or offset to every message.
- The server acknowledges durably persisted checkpoints.
- The client persists the last acknowledged checkpoint.
- On reconnect, the client opens a new stream and resumes from the next sequence.
- Use idempotency keys to safely handle messages that may be resent.

For long-lived streams, gRPC retry policies are not a full-session recovery mechanism. Test reconnect/resume by stopping the server after several messages, restarting it, and verifying no acknowledged data is lost or duplicated.

## 10. What Does ManagedChannel Do When the Server Restarts?

ManagedChannel manages connections and can transition through states such as IDLE, CONNECTING, READY, TRANSIENT_FAILURE, and SHUTDOWN. When a connection drops, the channel can attempt to reconnect according to its backoff. When the server returns at the same address and port, the channel can establish a new transport without requiring the client to create a new channel.

However:

- Channel reconnection does not guarantee that in-flight RPCs continue.
- Already-failed calls do not revive automatically just because the server becomes READY.
- New RPCs can succeed once the channel reconnects.
- If the server moves to a new port, a channel pointing to the old address will not automatically discover the new port unless the resolver/service discovery updates the endpoint.

Keep channels long-lived alongside the client lifecycle. Do not create a new channel for every retry; doing so bypasses the connection pooling, resolver, and backoff already provided by ManagedChannel.

## 11. wait-for-ready Differs from Retry

The withWaitForReady option tells the client to wait for the channel to return to a state capable of sending calls instead of failing immediately when the channel is temporarily unavailable. The call is still subject to its deadline; if the server does not recover before the deadline, the call fails.

wait-for-ready does not replay an already-committed call and does not guarantee the server will succeed. It controls when the call is sent over the channel. A retry policy controls re-executing an eligible call after a retryable status.

Do not use wait-for-ready for every call if queuing requests while the server is down could cause a traffic spike when the server recovers. Set deadlines, bound concurrency, and enable it only on suitable methods.

## 12. Testing Server Restarts on the Same Endpoint

To test channel reconnection, the client must keep pointing to the same address after the server restarts. A test fixture can:

1. Start the server on a dynamic port and record the assigned port.
2. Create a channel pointing to that port and verify an RPC succeeds.
3. Gracefully stop the server and wait for termination.
4. Start a new server on the exact recorded port.
5. Use the existing channel to call a new RPC with a deadline and wait-for-ready if the scenario needs to wait for reconnection.
6. Verify the new RPC succeeds after the transport is re-established.

The server restart fixture must wait for the old server to release the port before rebinding. If binding the same port fails, the test must fail clearly rather than silently choosing a different port, because changing ports no longer tests channel reconnection to the old endpoint.

If a test starts a new server on a different port, create a new channel or update the resolver. That tests endpoint discovery/updates, not reconnection to the same endpoint.

Example minimal helper for a self-managed server fixture:

~~~java
synchronized void restartOnSamePort() throws InterruptedException {
    Server old = server;
    int oldPort = old.getPort();

    old.shutdown();
    if (!old.awaitTermination(5, TimeUnit.SECONDS)) {
        old.shutdownNow();
        throw new IllegalStateException("Old server did not terminate");
    }

    try {
        server = NettyServerBuilder.forPort(oldPort)
            .addService(service)
            .build()
            .start();
    } catch (IOException ex) {
        throw new IllegalStateException(
            "Cannot restart gRPC server on the same port", ex);
    }
}
~~~

The test can keep the old channel and call again after the restart:

~~~java
grpcServer.restartOnSamePort();

StockReply reply = stub.withWaitForReady()
    .withDeadlineAfter(5, TimeUnit.SECONDS)
    .getStock(StockRequest.newBuilder().setSku("SKU-42").build());

assertEquals(7, reply.getAvailable());
~~~

This illustrates a single-service server fixture; a real fixture must synchronize access to the server field and preserve the same list of services/interceptors when creating the new server. Tests should verify an RPC succeeds after the channel reconnects, not merely that the restart helper returns.

## 13. In-Flight RPCs When the Server Stops

An in-flight call may receive UNAVAILABLE, CANCELLED, or another transport status when the server stops; the observed status depends on timing and transport. If the server already executed the side effect before the response reached the client, the business outcome may be indeterminate from the client's perspective.

Restart tests should distinguish:

- **Calls before shutdown**: actively processing and interrupted.
- **Calls during downtime**: fail immediately, or wait if using wait-for-ready.
- **Calls after server recovery**: succeed over the reconnected channel.

Never claim an in-flight call will resume from the exact last instruction or message. For operations with side effects, use idempotency keys and status queries so clients can determine the outcome.

## 14. Coordinating Restarts in the Spring Test Context

If the server is managed by the Spring gRPC starter, restarts need to go through the lifecycle API supported by the starter. If the test manages the server itself, the fixture can close and recreate io.grpc.Server within the same test.

When shutdown starts, readiness should switch to NOT_SERVING so load balancers and client health checking stop sending new calls. Then the server shuts down gracefully within a timeout; only if it does not terminate in time use shutdownNow. When the new server is ready, update health state back to SERVING.

Never call shutdown on a Spring context-owned server from individual @AfterEach methods if the context is cached and shared across tests. Restart tests may need an isolated context or a fixture with explicit lifecycle control. Client channels must be closed in final teardown.

## 15. Common Mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Treating channel reconnect as RPC retry | In-flight calls still fail | Test reconnection and retry policies separately. |
| Retrying every status | Repeats invalid requests or worsens overload | Only choose appropriate transient statuses. |
| Retrying non-idempotent write operations | Creates duplicate side effects | Use idempotency keys and persist outcomes. |
| Setting an overly short deadline | Backoff exhausts the budget before the next attempt | Choose a deadline sufficient for total attempts/backoff. |
| Server sends response headers before error | Call is committed, so retries stop happening | Understand commit points and design tests accurately. |
| Concluding retries are broken from streaming tests | Streaming has different retry semantics than unary | Use unary to test retry policies; resume streams at the application layer. |
| Restarting server on a new port while keeping old channel | Channel keeps calling the old endpoint | Keep the same port or update the resolver/recreate the channel. |
| Using Thread.sleep to wait for reconnect | Tests are flaky based on machine speed | Use latches, wait-for-ready, and deadlines. |
| Not checking server invocation count | Unknown whether the call ran multiple times | Use counters or an idempotency store in tests. |

## 16. Retry and Restart Testing Matrix

An integration test suite should include these scenarios:

1. Unary method returns UNAVAILABLE twice then succeeds: client receives response and server records three attempts.
2. Non-retryable status such as INVALID_ARGUMENT: executed only once.
3. Deadline expires before backoff completes: client receives DEADLINE_EXCEEDED.
4. Server stops while an RPC is in flight: client observes an error and the operation is verified via idempotency key.
5. Server restarts on the same port: old channel reconnects and a new RPC succeeds.
6. Server restarts on a new port: resolver is updated or client creates a new channel.
7. Client uses wait-for-ready during temporary downtime: call waits until server recovers or deadline expires.
8. Streaming interrupted after a checkpoint: client resumes from checkpoint without losing or duplicating acknowledged messages.

Tests should set finite deadlines, wait timeouts, and attempt counts. Record statuses, invocation counts, endpoint/port, and server lifecycle timestamps to diagnose failures.

## 17. Hands-On Exercise

Build an integration test for CatalogService:

1. Configure a retry policy for unary GetStock, retrying only UNAVAILABLE up to four attempts.
2. Create a test service that returns UNAVAILABLE on the first two calls and then succeeds.
3. Assert the final response and invocation count.
4. Create an INVALID_ARGUMENT case and verify no retry occurs.
5. Stop the server after the channel has connected, then restart the server on the same port.
6. Use the existing channel to call a new RPC and verify channel reconnection.
7. Trigger an in-flight RPC when the server stops; verify the error and check operation state using an idempotency key.
8. If streaming upload exists, add sequence/checkpoint handling and a dedicated resume test.

**Completion criteria:** clearly distinguish retries from reconnects, configure policy per method/status, control deadlines, prove channel recovery after restart, and prevent duplicate side effects.

## 18. Takeaways

- Retry re-executes an eligible RPC; reconnect only restores ManagedChannel transport.
- Configured retry relies on service config, retryable status codes, max attempts, and backoff.
- An already-committed call is not automatically retried by gRPC; response headers are a key commit point.
- Deadlines span all attempts and backoff waiting time.
- Operations with side effects require idempotency keys to avoid duplicate execution.
- Streaming RPCs require application-level checkpoint/resume when failing after messages are exchanged.
- A channel can reconnect to the same endpoint after a server restart, but in-flight calls do not automatically continue.
- wait-for-ready delays sending calls when the channel is temporarily unavailable; it does not replace a retry policy.
- Same-endpoint restart tests must rebind the exact port; a new port requires a resolver update or new channel.
- Test retry, reconnect, in-flight failure, and resume separately to draw accurate conclusions about reliability.

Testing retries and server restarts verifies that Spring gRPC services recover cleanly from transient failures, bound repeated executions, and keep business outcomes consistent when transport is interrupted.
