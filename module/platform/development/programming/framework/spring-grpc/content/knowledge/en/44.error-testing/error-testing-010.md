# Testing Retryable and Non-Retryable Statuses

Retries help a gRPC client recover from transient failures, but retrying every error can increase load, extend latency, and duplicate side effects. A status is only retried when policy permits, the call is still retryable, and sufficient overall deadline budget remains. Therefore, you must test both statuses that can be retried and statuses that must terminate immediately, while verifying the actual attempt count and the final outcome received by the caller.

**Testing retryable and non-retryable statuses** means testing a gRPC client's retry behavior according to status code, retry policy, and RPC commitment state. This lesson belongs to the **Error testing** chapter of the **SPRING_GRPC** module: developing gRPC services in the Spring ecosystem with Protocol Buffers contracts, generated Java code, and client/server implementations for unary or streaming RPCs; learners handle metadata, deadlines, statuses, interceptors, TLS, integration testing, and performance/reliability monitoring. The focus is configuring retryableStatusCodes, distinguishing attempt status from final status, testing maxAttempts, backoff, and deadlines, and ensuring operations can tolerate repeated requests.

## 1. A Retryable Status Does Not Mean Every Call Is Retried

gRPC retries rely on the client's service config. A method can declare:

- maxAttempts: maximum total number of attempts, including the initial attempt.
- initialBackoff: wait time before the first retry.
- maxBackoff: upper bound on backoff.
- backoffMultiplier: backoff growth factor.
- retryableStatusCodes: allowlist of status codes permitted for retry.

The client only retries per policy when an attempt finishes with a status in the allowlist and the RPC has not yet committed. Overall deadline, retry throttling, server pushback, retry buffer limits, and call state can all prevent a subsequent retry.

For example, a policy permits UNAVAILABLE with maxAttempts=3. If the first attempt returns UNAVAILABLE, the client may issue a second attempt. If the second attempt succeeds, the caller receives only the final status OK; the intermediate UNAVAILABLE error is not the logical call's final status.

Having a status in retryableStatusCodes is a necessary condition, not a guarantee that a retry will always occur.

## 2. Distinguish Logical Call, Attempt, and Final Status

Keep three units clearly separated when writing tests:

| Unit | Meaning | Where Observed |
| --- | --- | --- |
| Logical call | A single application invocation of a gRPC method. | Client stub/call boundary. |
| Attempt | A single try to send the RPC over the transport/server. | Retry instrumentation or server handler invocation count. |
| Final status | The final outcome received by the client application. | Client terminal callback or exception from a blocking stub. |

Example of one logical call:

1. Attempt 1 reaches the server and ends with UNAVAILABLE.
2. The client waits for backoff.
3. Attempt 2 reaches the server and returns a successful response.
4. The client receives final status OK.

The expected outcome is one logical call, two server-observed attempts, and one final status OK. Do not count two attempts as two application-level invocations.

A server invocation counter only counts attempts that reached the service handler. It does not count connection failures occurring before the request reached the server. To observe all client attempts, use instrumentation at the retry layer or telemetry supporting attempt-level metrics.

## 3. Choose Statuses Based on Error Semantics

The status code must accurately describe the cause, after which the retry policy decides whether to retry:

| Status | Usually Appropriate Handling | Reason |
| --- | --- | --- |
| UNAVAILABLE | Usually retryable with backoff. | Service/transport may be temporarily unavailable. |
| RESOURCE_EXHAUSTED | Retry only when server indicates a recoverable condition and client has proper backoff/pushback. | Immediate retries can worsen overload. |
| DEADLINE_EXCEEDED | Retry only when policy and overall deadline still have budget; usually the call is near or past expiration. | Retries cannot create extra time beyond the overall deadline. |
| ABORTED | Usually needs retry at a higher transaction/workflow layer. | May require re-reading state or re-running the whole transaction. |
| FAILED_PRECONDITION | Do not retry until system conditions change. | Resending the same request does not fix the precondition. |
| INVALID_ARGUMENT | Do not retry. | Request has invalid data or violates the contract. |
| UNAUTHENTICATED / PERMISSION_DENIED | Do not retry automatically with the same credentials/permissions. | Proper authentication or authorization is needed. |
| NOT_FOUND | Usually do not retry if the object truly does not exist. | Repeating the same query will not make the resource appear. |

This is common design guidance, not a mandatory gRPC classification table. The service config is what declares which statuses are retried. Do not blindly add statuses to the allowlist just to boost success rates.

## 4. Configure a Retry Policy for a Unary Method

Example configuration that retries only UNAVAILABLE for inventory.Inventory/GetStock:

~~~java
import java.util.List;
import java.util.Map;

Map<String, ?> retryPolicy = Map.of(
        "maxAttempts", 3.0,
        "initialBackoff", "0.05s",
        "maxBackoff", "0.2s",
        "backoffMultiplier", 2.0,
        "retryableStatusCodes", List.of("UNAVAILABLE")
);

Map<String, ?> methodConfig = Map.of(
        "name", List.of(Map.of(
                "service", "inventory.Inventory",
                "method", "GetStock")),
        "retryPolicy", retryPolicy
);

Map<String, ?> serviceConfig = Map.of(
        "methodConfig", List.of(methodConfig)
);
~~~

maxAttempts=3 means at most three tries: the initial attempt plus at most two retries. Values in service config are JSON-compatible; for instance, 3.0 for attempt count and duration strings following the gRPC service config format.

retryableStatusCodes is an allowlist. In this example, INVALID_ARGUMENT is not retried even if the server returns that status repeatedly. Policies should be scoped to the specific services/methods that need retries; do not enable retries broadly across all RPCs if their semantics differ.

## 5. Create a Deterministic Test Server

To test a retry policy, use a test service that returns statuses based on invocation count. For example, the first attempt returns UNAVAILABLE, and the next attempt succeeds:

~~~java
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

import java.util.concurrent.atomic.AtomicInteger;

final class RetryTestInventoryService
        extends InventoryGrpc.InventoryImplBase {

    final AtomicInteger receivedAttempts = new AtomicInteger();

    @Override
    public void getStock(
            StockRequest request,
            StreamObserver<StockReply> responseObserver) {

        int attempt = receivedAttempts.incrementAndGet();
        if (attempt == 1) {
            responseObserver.onError(
                    Status.UNAVAILABLE
                            .withDescription("temporary test failure")
                            .asRuntimeException());
            return;
        }

        responseObserver.onNext(StockReply.newBuilder()
                .setAvailableUnits(7)
                .build());
        responseObserver.onCompleted();
    }
}
~~~

The counter lives in the service instance, so it reflects how many times requests actually reached the handler. In real tests, use the generated classes, methods, and fields matching the project's Protobuf contract.

To test a non-retryable status, create another fixture that always returns INVALID_ARGUMENT and increments the same kind of counter. Do not reuse a service fixture carrying state from an earlier test; each test needs independent state so attempt counts do not depend on execution order.

## 6. Use Loopback Transport to Test Retries

Retry behavior should be tested over a client channel with a service config and a real server transport. The example below uses Netty loopback:

~~~java
Server server = NettyServerBuilder.forPort(0)
        .addService(retryTestService)
        .build()
        .start();

ManagedChannel channel = ManagedChannelBuilder
        .forAddress("127.0.0.1", server.getPort())
        .usePlaintext()
        .enableRetry()
        .defaultServiceConfig(serviceConfig)
        .build();

try {
    InventoryBlockingStub stub =
            InventoryGrpc.newBlockingStub(channel)
                    .withDeadlineAfter(3, TimeUnit.SECONDS);

    StockReply reply = stub.getStock(request);

    assertEquals(7, reply.getAvailableUnits());
    assertEquals(2, retryTestService.receivedAttempts.get());
} finally {
    channel.shutdownNow();
    server.shutdownNow();
    channel.awaitTermination(5, TimeUnit.SECONDS);
    server.awaitTermination(5, TimeUnit.SECONDS);
}
~~~

This is a test skeleton; retryTestService, serviceConfig, and request come from the fixtures above. Use port 0 so the OS assigns an available port. The channel must be created after the server starts and closed in teardown to avoid leaking threads/sockets across tests.

Netty loopback tests retries over a more realistic transport than in-process transport. Exact behavior also depends on grpc-java version, resolver, and retry configuration; use your application's actual version and verify retries are enabled and the service config applies to the exact full service/method name.

## 7. Test Retryable Status: First Attempt Fails, Next Succeeds

With a policy that retries only UNAVAILABLE, the success test must verify both the response and the attempt count:

~~~java
@Test
void retriesUnavailableAndReturnsOk() {
    // Arrange: server returns UNAVAILABLE first, OK on the second attempt.
    RetryTestInventoryService service =
            new RetryTestInventoryService();
    RunningGrpcFixture fixture =
            RunningGrpcFixture.start(service, retryServiceConfig());

    try {
        InventoryBlockingStub stub =
                fixture.stub().withDeadlineAfter(3, TimeUnit.SECONDS);

        // Act
        StockReply reply = stub.getStock(validRequest());

        // Assert
        assertEquals(7, reply.getAvailableUnits());
        assertEquals(2, service.receivedAttempts.get());
    } finally {
        fixture.close();
    }
}
~~~

RunningGrpcFixture is an application test helper responsible for starting and closing the Netty server/channel. The test does not only assert a successful response; if it only checked the response, the test could pass even if the retry policy were not applied and the fixture accidentally returned OK on the first attempt.

Do not assert backoff down to the exact millisecond. Schedulers, CI load, and the runtime can cause retry timing to fluctuate. Assert the attempt count, final status, and overall deadline; if you need to verify backoff, measure elapsed duration with wide tolerance or inspect retry instrumentation.

## 8. Test Non-Retryable Status: Terminates After One Attempt

With the same retry policy, when the service returns INVALID_ARGUMENT, the client must terminate the logical call without performing a policy retry:

~~~java
@Test
void doesNotRetryInvalidArgument() {
    AtomicInteger receivedAttempts = new AtomicInteger();
    InventoryGrpc.InventoryImplBase service =
            new InventoryGrpc.InventoryImplBase() {
                @Override
                public void getStock(
                        StockRequest request,
                        StreamObserver<StockReply> responseObserver) {
                    receivedAttempts.incrementAndGet();
                    responseObserver.onError(
                            Status.INVALID_ARGUMENT
                                    .withDescription("invalid test input")
                                    .asRuntimeException());
                }
            };

    RunningGrpcFixture fixture =
            RunningGrpcFixture.start(service, retryServiceConfig());
    try {
        InventoryBlockingStub stub =
                fixture.stub().withDeadlineAfter(3, TimeUnit.SECONDS);

        StatusRuntimeException error = assertThrows(
                StatusRuntimeException.class,
                () -> stub.getStock(invalidRequest()));

        assertEquals(
                Status.Code.INVALID_ARGUMENT,
                error.getStatus().getCode());
        assertEquals(1, receivedAttempts.get());
    } finally {
        fixture.close();
    }
}
~~~

This test proves INVALID_ARGUMENT is not in retryableStatusCodes. It also verifies the final status received by the caller is genuinely INVALID_ARGUMENT, not transformed into UNAVAILABLE or a generic error.

## 9. Test a Retryable Status When Policy Disallows It

Status and policy must be tested separately. If the server returns UNAVAILABLE but the method has no retry policy, the client does not perform a policy retry. You can write a test with a channel lacking a retry service config and a server fixture returning UNAVAILABLE after the handler receives the request:

~~~java
StatusRuntimeException error = assertThrows(
        StatusRuntimeException.class,
        () -> stubWithoutRetryPolicy.getStock(validRequest()));

assertEquals(
        Status.Code.UNAVAILABLE,
        error.getStatus().getCode());
assertEquals(1, service.receivedAttempts.get());
~~~

When testing the no-policy case, ensure the request reached the service handler and the handler proactively returned UNAVAILABLE. gRPC can perform limited transparent retries in certain cases where the transport knows the request was never processed by the server; that differs from service-policy retries. The handler counter helps verify which case the test is exercising.

## 10. Retry Exhaustion and Final Status

If every attempt returns a retryable status, the client tries up to maxAttempts or stops early when deadline/commitment/throttling disallows continuing:

~~~text
Logical call (maxAttempts = 3)
  attempt 1 -> UNAVAILABLE
  backoff
  attempt 2 -> UNAVAILABLE
  backoff
  attempt 3 -> UNAVAILABLE
  final status -> UNAVAILABLE
~~~

Tests should verify:

- The server handler is invoked three times when all attempts reach the server.
- The client receives final status UNAVAILABLE.
- There is no fourth attempt.
- Total duration does not exceed the test deadline.

If an attempt does not reach the server due to a connection failure, the server counter may be lower than the client attempt count. In that case, use client-side retry instrumentation to verify attempt count rather than inferring all attempts from the server counter.

## 11. Deadlines Can End Retries Before maxAttempts

The deadline applies to the entire logical call, including all attempts and backoff intervals:

~~~text
Total deadline: 300 ms

Attempt 1:  UNAVAILABLE
Backoff:    wait
Attempt 2:  in progress
Deadline:   expired
Final:      DEADLINE_EXCEEDED
~~~

When the deadline expires, the client must not extend its budget by granting a fresh timeout per attempt. Deadline tests should use a slow handler or sufficiently large backoff so the overall deadline expires before the next retry; verify the final status and actual attempt count without depending on exact absolute timing.

DEADLINE_EXCEEDED can also be declared retryable in a policy, but if the logical call's deadline has already expired there is no time left for another attempt. Do not use retries to mask an overly tight deadline budget or a chronically slow dependency.

## 12. Commitment Can Prevent Retries

An attempt can only be retried while gRPC is still able to replay the call. Once a call has committed, the retry policy stops creating new attempts. Key cases include:

- The client has received response headers from the server.
- A request message exceeds the retry buffer limit, causing the call to commit.
- A streaming call has exchanged data in a way that cannot be safely replayed.

Therefore, retry tests should start with a simple unary method that sends no response headers before failing. If you want to test commitment, write a separate test where the server sends response headers before ending the attempt with a status; verify the client does not retry a committed attempt according to the semantics of your runtime/version.

Do not confuse a status being in the allowlist with a call being guaranteed to retry. A retryable status on an already committed call can still terminate immediately.

## 13. Idempotency and Side Effects During Retries

Retries can cause the same logical operation to reach the server multiple times. A common scenario:

1. The server receives the request and writes data successfully.
2. The response is lost or the connection drops before the client receives the result.
3. The client sees a retryable error and resends the request.
4. The server receives the same operation a second time.

If the method performs side effects, retries can create duplicate orders, charge twice, or emit duplicate events. For write RPCs, design for idempotency:

- The client sends a stable idempotency key for the logical operation.
- The server stores the result keyed by that key within an appropriate transaction.
- Repeated requests with the same key return the stored result instead of executing side effects again.
- Keys have clear scope, TTL, and access control.
- Tests simulate a lost response after side effects have committed.

Do not generate a new idempotency key on every attempt. Nor is a request ID used for log correlation automatically an idempotency key; the two fields have different lifecycles and semantics.

## 14. Retries and Streaming RPCs

Do not generalize unary test results to every streaming method. With client-streaming or bidirectional streaming, the request may have sent multiple messages; the server may have partially processed them before failing. With server-streaming, the client may have already received response messages before the stream ended.

Once a call is committed, gRPC cannot replay the entire stream by default. If the application needs recovery, design a resume protocol using cursors/sequence numbers, acknowledgements, and idempotent processing. Opening a new RPC from an acknowledged position is application-level resume, different from gRPC's automatic retry.

Streaming tests must separately check duplicates, lost messages, reconnects, and resume cursors. Do not claim that a unary retry policy proves streaming retries are safe.

## 15. Observability When Testing Retries

To see what a test is actually doing, track separately:

| Signal | Purpose |
| --- | --- |
| Logical calls started/completed | One application method invocation and its final status. |
| Server handler invocation count | Number of attempts that actually reached the test handler. |
| Client attempt count | Number of times the client retry layer started an attempt, if supported by instrumentation. |
| Attempt status | Status of each attempt. |
| Final status | The single status the caller receives. |
| Logical call duration | Total duration including backoff and all attempts. |

A ClientInterceptor at the application boundary typically observes the final onClose; it does not necessarily see individual retry attempts inside the channel. Do not increment an attempt counter on every onClose in a regular interceptor. Use OpenTelemetry/gRPC instrumentation or telemetry with attempt-level semantics when client attempt metrics are needed.

In tests, a server invocation counter is useful evidence of how many attempts reached the server. Combine it with final status and response assertions to avoid one-sided tests.

## 16. Essential Test Scenarios

| Case | Policy/Server Fixture | Expected Result |
| --- | --- | --- |
| Retryable then success | UNAVAILABLE, then OK; policy permits retry. | Multiple attempts; final status OK. |
| Non-retryable | INVALID_ARGUMENT; policy allows only UNAVAILABLE. | One attempt; final status INVALID_ARGUMENT. |
| Retryable but no policy | Server handler returns UNAVAILABLE; channel has no retry policy. | No policy retry; final status UNAVAILABLE. |
| Retry exhaustion | All attempts return UNAVAILABLE; maxAttempts=3. | At most three attempts; final status error. |
| Deadline during backoff | Attempt fails, backoff exceeds remaining budget. | Final status DEADLINE_EXCEEDED; no retry past deadline. |
| Commitment | Server sends response headers before retryable error. | Do not assume committed attempts are retried. |
| Side effects and lost response | Server commits then transport fails. | Idempotency prevents duplicate side effects. |
| Caller cancellation | Client cancels logical call during backoff. | Stops creating new attempts. |
| Inappropriate status | Server uses INVALID_ARGUMENT for transient error. | Test catches wrong contract/status mapping. |

Each test should have its own fixture, a finite deadline, channel/server cleanup, and assertions on both attempt count and final status. Do not use Thread.sleep() to guess that a retry happened; use counters, latches, or a test observer with timeouts.

## 17. Common Mistakes

| Symptom | Cause | How to Fix |
| --- | --- | --- |
| UNAVAILABLE is not retried | Method lacks policy or status is missing from allowlist. | Check service config and full method name. |
| INVALID_ARGUMENT is retried | Data error status added to retryableStatusCodes. | Retry only transient errors per semantics. |
| Test asserts only OK response | Does not prove a retry actually happened. | Assert server invocation/attempt count. |
| Asserting attempt count greater than maxAttempts | Interpreting maxAttempts as retries in addition to initial attempt. | Remember maxAttempts includes the first attempt. |
| Server counter lower than client attempt count | Some attempts failed before reaching handler. | Use client attempt instrumentation and name metrics accurately. |
| Retry does not occur despite allowlisted status | Call committed, deadline expired, or throttling/pushback active. | Inspect response headers, buffer, deadline, and retry telemetry. |
| Side effects duplicated | Operation is not idempotent. | Use idempotency keys and server-side deduplication. |
| Flaky tests | Relies on sleep/timing or shared fixture state. | Use latches, reasonable deadlines, and isolated fixtures. |

## 18. Hands-On Exercises

1. Configure a policy that retries only UNAVAILABLE for a unary read method.
2. Write a test service that returns UNAVAILABLE on the first call and OK afterwards; verify one logical call produces two server-observed attempts.
3. Write a test returning INVALID_ARGUMENT; verify only one attempt occurs and the final status is preserved.
4. Write a test for UNAVAILABLE when the channel has no retry policy; distinguish policy retries from transparent retries.
5. Test retry exhaustion with maxAttempts=3.
6. Test deadline expiration during backoff and caller cancellation.
7. Design commitment and idempotency tests for a write RPC.
8. Create a dashboard/test report separating logical call, attempt status, final status, and logical call duration.

After this lesson, you should know how to prove whether a status is retried per policy, distinguish intermediate errors from final statuses, and test conditions that can prevent retries such as commitment or deadlines. Combining attempt counts, final status, and idempotency tests helps Spring gRPC services recover from transient errors without causing retry storms or duplicate side effects.
