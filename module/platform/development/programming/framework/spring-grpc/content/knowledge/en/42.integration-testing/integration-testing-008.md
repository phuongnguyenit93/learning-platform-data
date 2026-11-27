# End-to-End Streaming Testing

## Learning Objectives

After this lesson, you will be able to:

- Design integration tests that run through a gRPC server, HTTP/2 transport, and generated client stubs.
- Test server-streaming, client-streaming, and bidirectional streaming.
- Synchronize the test thread with asynchronous callbacks without relying on Thread.sleep.
- Verify message ordering, terminal events, error statuses, and cancellation.
- Set deadlines, wait timeouts, and clean up channels/streams according to lifecycle.
- Distinguish end-to-end testing over TCP from direct service testing or in-process transport.

## 1. End-to-End Means Testing the Real RPC Path

A test that invokes a service's Java method directly only tests the business method. It does not verify Protobuf serialization, generated stubs, HTTP/2 transport, server dispatch, metadata, status mapping, or how the client receives callbacks.

End-to-end streaming tests require a real gRPC client connecting to a running server. Requests and responses must travel through generated code and transport. In **SPRING_GRPC**, the server typically uses Spring-managed service beans and dependencies; tests should start the proper application context and call the bound gRPC endpoint.

A good test verifies both message content and stream lifecycle: which messages are sent, the order received, when the stream completes, what status represents errors, and how resources are released.

## 2. Three Streaming Patterns to Test

Protobuf defines three streaming RPC patterns:

| Pattern | Request | Response | Example Use Cases |
| --- | --- | --- | --- |
| Server-streaming | One message | Multiple messages | Price feeds, event streams, or progress updates. |
| Client-streaming | Multiple messages | One final message | Uploading chunks, aggregating metrics. |
| Bidirectional streaming | Multiple messages | Multiple messages | Chat, two-way synchronization, device control. |

Each pattern has a different lifecycle. Server-streaming ends when the server calls onCompleted/onError. Client-streaming usually ends the request side when the client calls onCompleted; the server then sends the final response. Bidirectional streaming has two independent directions: the client can keep sending while receiving responses.

## 3. Protobuf Contract for Testing

Example of a service covering all three streaming patterns:

~~~proto
syntax = "proto3";

package acme.inventory.v1;

option java_package = "com.example.inventory.grpc";
option java_multiple_files = true;

message WatchRequest {
  string sku = 1;
}

message StockUpdate {
  string sku = 1;
  int64 available = 2;
  int64 sequence = 3;
}

message StockChunk {
  string upload_id = 1;
  int64 quantity = 2;
}

message UploadSummary {
  string upload_id = 1;
  int64 chunk_count = 2;
  int64 total_quantity = 3;
}

message ClientMessage {
  int64 sequence = 1;
  string text = 2;
}

message ServerMessage {
  int64 sequence = 1;
  string text = 2;
}

service InventoryStream {
  rpc WatchStock(WatchRequest) returns (stream StockUpdate);
  rpc UploadStock(stream StockChunk) returns (UploadSummary);
  rpc Exchange(stream ClientMessage) returns (stream ServerMessage);
}
~~~

Generated code provides async stubs and server base classes for each method. Tests use the exact generated types from the project's contract; never construct fake request/response objects to bypass real serialization.

## 4. Starting the Server with the Spring Test Context

Integration tests should use Spring-injected service implementations and a server lifecycle managed by the starter or a test fixture. If the starter starts the gRPC server automatically, get the actual port from the starter's test support. If the test owns the server, register the service bean in a server fixture whose lifecycle is tied to the context.

Key requirements:

- The server has bound successfully before the test creates the channel.
- The test retrieves the actual gRPC port, not confusing it with the Spring Boot web port.
- Use a dynamic port so parallel tests do not collide.
- Keep only one server lifecycle owner per context.
- If the goal is to test transport, use a real TCP channel; in-process tests cannot replace HTTP/2 socket checks.

Earlier lessons covered starting the server and getting a dynamic port in detail. Here, tests focus on streams once the endpoint is ready.

## 5. Creating the Channel and Async Stub

Streaming APIs typically use async stubs. Create the channel after the Spring context has refreshed:

~~~java
@SpringBootTest
class InventoryStreamingIntegrationTest {
    @Autowired
    GrpcTestEndpoint grpcEndpoint;

    private ManagedChannel channel;
    private InventoryStreamGrpc.InventoryStreamStub stub;

    @BeforeEach
    void connect() {
        channel = ManagedChannelBuilder
            .forAddress("127.0.0.1", grpcEndpoint.port())
            .usePlaintext()
            .build();

        stub = InventoryStreamGrpc.newStub(channel)
            .withDeadlineAfter(5, TimeUnit.SECONDS);
    }

    @AfterEach
    void closeChannel() throws InterruptedException {
        if (channel == null) {
            return;
        }
        channel.shutdown();
        if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
            channel.shutdownNow();
        }
    }
}
~~~

GrpcTestEndpoint is a test-only abstraction providing the port of the Spring/starter-managed server. Replace it with your project's actual accessor. usePlaintext is strictly for loopback tests without TLS; if production uses TLS, create a test suite connecting with trust certificates.

Set a deadline on the stub or individual calls so RPCs do not hang indefinitely. The test's callback wait timeout should be slightly longer than the RPC deadline so the test can receive and assert the final error.

## 6. Synchronizing Callbacks with the Test Thread

Async stubs deliver results via StreamObserver. Test methods and callbacks typically execute on different threads, so you cannot invoke an RPC and assert immediately.

A useful pattern:

- Use a CountDownLatch to signal the terminal event.
- Use CopyOnWriteArrayList or a synchronized collection to store messages.
- Use AtomicReference to capture callback errors.
- Assert on the test thread only after the latch completes.
- Set a finite timeout on await.

Never use Thread.sleep to guess when messages arrive. Sleeping makes tests depend on machine speed and leads to flakiness in CI. Never let assertion failures happen inside a callback without forwarding errors back to the test thread; exceptions on callback threads may not fail the test method as expected.

## 7. Testing Server-Streaming

Server-streaming returns multiple responses for a single request. For example, a client watches inventory for an SKU:

~~~java
@Test
void receivesAllStockUpdatesInOrder() throws Exception {
    List<StockUpdate> received = new CopyOnWriteArrayList<>();
    AtomicReference<Throwable> failure = new AtomicReference<>();
    CountDownLatch completed = new CountDownLatch(1);

    stub.watchStock(
        WatchRequest.newBuilder().setSku("SKU-42").build(),
        new StreamObserver<>() {
            @Override
            public void onNext(StockUpdate update) {
                received.add(update);
            }

            @Override
            public void onError(Throwable error) {
                failure.set(error);
                completed.countDown();
            }

            @Override
            public void onCompleted() {
                completed.countDown();
            }
        });

    assertTrue(completed.await(6, TimeUnit.SECONDS));
    assertNull(failure.get());
    assertEquals(3, received.size());
    assertEquals(
        List.of(1L, 2L, 3L),
        received.stream().map(StockUpdate::getSequence).toList());
}
~~~

The test verifies both the count and sequence of messages, not merely that at least one response arrived. If the contract does not guarantee ordering, assert by correlation ID or result set instead of enforcing an ordering not present in the contract.

The server must invoke exactly one terminal event. If a server streams indefinitely, the test must actively cancel once the condition is met; do not wait for onCompleted since it may never occur.

## 8. Testing Client-Streaming

Client-streaming sends multiple request messages and receives one final response. The async stub method returns a request observer; the test calls onNext multiple times and calls onCompleted to finish the sending side:

~~~java
@Test
void uploadsChunksAndReceivesOneSummary() throws Exception {
    AtomicReference<UploadSummary> result = new AtomicReference<>();
    AtomicReference<Throwable> failure = new AtomicReference<>();
    CountDownLatch completed = new CountDownLatch(1);

    StreamObserver<StockChunk> request = stub.uploadStock(
        new StreamObserver<>() {
            @Override
            public void onNext(UploadSummary summary) {
                result.set(summary);
            }

            @Override
            public void onError(Throwable error) {
                failure.set(error);
                completed.countDown();
            }

            @Override
            public void onCompleted() {
                completed.countDown();
            }
        });

    request.onNext(StockChunk.newBuilder()
        .setUploadId("upload-7").setQuantity(2).build());
    request.onNext(StockChunk.newBuilder()
        .setUploadId("upload-7").setQuantity(5).build());
    request.onNext(StockChunk.newBuilder()
        .setUploadId("upload-7").setQuantity(3).build());
    request.onCompleted();

    assertTrue(completed.await(6, TimeUnit.SECONDS));
    assertNull(failure.get());
    assertNotNull(result.get());
    assertEquals(3, result.get().getChunkCount());
    assertEquals(10, result.get().getTotalQuantity());
}
~~~

onCompleted on the request observer signals that the client finished sending input; it does not mean the final response has arrived. The test is only complete when the response observer receives a terminal event. Never call request.onCompleted before sending all chunks.

If the client encounters an error while sending, use request.onError to terminate the request side with an error. Do not continue calling onNext after a terminal event.

## 9. Testing Bidirectional Streaming

With bidirectional streaming, client and server can send messages independently in both directions. The client receives a request observer immediately upon opening the stream and supplies a response observer to receive messages:

~~~java
@Test
void exchangesMessagesInBothDirections() throws Exception {
    List<ServerMessage> received = new CopyOnWriteArrayList<>();
    AtomicReference<Throwable> failure = new AtomicReference<>();
    CountDownLatch completed = new CountDownLatch(1);

    StreamObserver<ClientMessage> request = stub.exchange(
        new StreamObserver<>() {
            @Override
            public void onNext(ServerMessage message) {
                received.add(message);
            }

            @Override
            public void onError(Throwable error) {
                failure.set(error);
                completed.countDown();
            }

            @Override
            public void onCompleted() {
                completed.countDown();
            }
        });

    request.onNext(ClientMessage.newBuilder()
        .setSequence(1).setText("first").build());
    request.onNext(ClientMessage.newBuilder()
        .setSequence(2).setText("second").build());
    request.onCompleted();

    assertTrue(completed.await(6, TimeUnit.SECONDS));
    assertNull(failure.get());
    assertEquals(List.of(1L, 2L),
        received.stream().map(ServerMessage::getSequence).toList());
}
~~~

The example sends all requests before asserting responses to keep the test simple. A truly interactive two-way test can send the next message after receiving a response or coordinate both directions using latches/queues. Do not assume the server must return a response immediately for every request unless that is the method's contract.

## 10. Checking Errors and Mid-Stream Statuses

A streaming call can terminate with an error status after sending several messages. Tests should check both messages received before the error and the final status:

~~~java
@Test
void preservesMessagesBeforeTerminalError() throws Exception {
    List<StockUpdate> received = new CopyOnWriteArrayList<>();
    AtomicReference<Throwable> failure = new AtomicReference<>();
    CountDownLatch terminal = new CountDownLatch(1);

    stub.watchStock(
        WatchRequest.newBuilder().setSku("MISSING").build(),
        new StreamObserver<>() {
            @Override
            public void onNext(StockUpdate update) {
                received.add(update);
            }

            @Override
            public void onError(Throwable error) {
                failure.set(error);
                terminal.countDown();
            }

            @Override
            public void onCompleted() {
                terminal.countDown();
            }
        });

    assertTrue(terminal.await(6, TimeUnit.SECONDS));
    assertNotNull(failure.get());
    assertEquals(
        Status.Code.NOT_FOUND,
        Status.fromThrowable(failure.get()).getCode());
}
~~~

In practice, the status may originate from validation before the first message or mid-stream after partial output. Tests must reflect the actual contract. Avoid asserting overly detailed message descriptions if that wording is not part of the API contract; status codes are typically more stable.

## 11. Cancellation and Clients Stopping Stream Consumption

For long-lived server streams, the client can cancel when it no longer needs data. Use ClientResponseObserver to obtain the ClientCallStreamObserver in beforeStart:

~~~java
AtomicReference<ClientCallStreamObserver<WatchRequest>> callRef =
    new AtomicReference<>();
CountDownLatch firstUpdate = new CountDownLatch(1);

stub.watchStock(
    WatchRequest.newBuilder().setSku("SKU-42").build(),
    new ClientResponseObserver<>() {
        @Override
        public void beforeStart(
                ClientCallStreamObserver<WatchRequest> requestStream) {
            callRef.set(requestStream);
        }

        @Override
        public void onNext(StockUpdate update) {
            firstUpdate.countDown();
        }

        @Override
        public void onError(Throwable error) {}

        @Override
        public void onCompleted() {}
    });

assertTrue(firstUpdate.await(3, TimeUnit.SECONDS));
callRef.get().cancel("test no longer needs updates", null);
~~~

A thorough test should verify that the server observes cancellation and stops the associated producer or subscription. Cancellation does not mean the server can always stop instantaneously; the service must propagate the signal to background work and release buffers. Avoid asserting a single client-side status if transport/cancellation races can produce different observed statuses; verify cleanup behavior and that no further messages arrive after cancellation is processed.

## 12. Testing Deadlines and Stalled Streams

A stream may emit no messages or fail to complete. Set a deadline on the call:

~~~java
InventoryStreamGrpc.InventoryStreamStub boundedStub =
    stub.withDeadlineAfter(2, TimeUnit.SECONDS);
~~~

In tests, use a separate timeout for the latch. When the deadline expires, the client receives a terminal error, typically DEADLINE_EXCEEDED if the client-side deadline caused it. The server must observe cancellation/deadline and stop work.

Do not arbitrarily set the latch timeout shorter than the deadline, because the test may fail before gRPC delivers the final status. A small buffer helps capture the actual error.

## 13. Checking Backpressure and Message Limits

A basic end-to-end test typically sends few messages. To test stream load, verify the application does not accumulate unbounded queues when the producer outpaces the consumer.

Points to verify:

- Manual inbound flow control only requests more messages when capacity is available.
- Outbound writers respect isReady and pause sending when transport is not ready.
- Application queues are bounded by message count and/or total bytes.
- When limits are exceeded, the server enforces a clear reject/status policy.
- Cancellation releases held queues and buffers.

Do not turn a small E2E test into a benchmark. Use separate controlled load tests to measure throughput, memory, and latency; integration tests here verify semantics and lifecycle.

## 14. Real TCP Tests vs. In-Process Tests

| Approach | What it verifies | Limitations |
| --- | --- | --- |
| Calling service method directly | Java logic in handler | Does not test generated stubs, serialization, or transport. |
| In-process gRPC | Stubs, dispatch, callbacks, and some interceptors | Does not test TCP sockets, HTTP/2 network paths, or TLS handshakes. |
| TCP gRPC over dynamic port | Server startup, Protobuf serialization, HTTP/2, callbacks, and statuses | Requires managing ports, channels, and lifecycle. |
| TCP gRPC over TLS | All of the above plus certificate/trust/hostname handshake | Requires test certificates and client trust configuration. |

To be truly end-to-end for transport, prefer TCP tests against a running server. In-process tests are useful for fast suites but do not replace TCP/TLS test coverage.

## 15. Common Mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Asserting immediately after calling async stub | Callbacks have not run yet, test reads empty collection | Wait for terminal event using a timed latch. |
| Using Thread.sleep to wait for messages | Flaky tests in CI | Use latches, queues, or conditions. |
| Asserting only message count | Misses out-of-order or wrong content | Assert sequence, correlation ID, and payload. |
| Confusing request onCompleted with response completion | Test exits prematurely | Wait for the response observer terminal event. |
| Not storing callback errors | Tests may miss asynchronous failures | Capture Throwable and assert on the test thread. |
| Calling onNext after onCompleted | Violates stream lifecycle | Respect one terminal event per direction. |
| Not cancelling infinite streams | Leaks calls, threads, and buffers | Cancel after test condition and verify cleanup. |
| Omitting deadlines | Test suite can hang | Set RPC deadlines and test wait timeouts. |
| Testing only in-process | Misses transport bugs | Add TCP end-to-end tests. |

## 16. End-to-End Streaming Testing Matrix

A baseline test suite should include:

1. Server-streaming: receives all messages with expected payload and sequence, then onCompleted.
2. Client-streaming: sends multiple chunks, closes request stream, and receives accurate summary.
3. Bidirectional streaming: sends/receives multiple messages and verifies ordering per contract.
4. Error: stream terminates with the right status, even when prior messages were emitted.
5. Cancellation: client cancels the stream and server stops background work.
6. Deadline: incomplete stream terminates within the time limit.
7. Flow control: queues are bounded and producers stay within capacity.
8. Lifecycle: channel closes after test, server stops when Spring context shuts down.

Each test should include a deadline, wait timeout, payload/status assertions, and cleanup. Tests must not depend on execution order with other test methods or leftover state in singleton services.

## 17. Hands-On Exercise

Implement integration tests for the InventoryStream service:

1. Start the Spring test context with a server registering the InventoryStream service.
2. Create a ManagedChannel over a dynamic port and a generated async stub.
3. Test WatchStock receiving three updates in sequence and then completing.
4. Test UploadStock receiving three chunks and returning an accurate summary.
5. Test Exchange sending two messages and receiving corresponding responses.
6. Add a case where the server returns NOT_FOUND or a mid-stream validation error.
7. Cancel a long-lived WatchStock and verify the worker/subscription is cleaned up.
8. Test deadline expiration for an incomplete stream.
9. Close the channel and verify the server adheres to Spring lifecycle.

**Completion criteria:** all three streaming patterns travel through generated stubs and TCP transport, messages/statuses match the contract, callbacks are synchronized with timeouts, and no streams or resources leak after tests.

## 18. Takeaways

- End-to-end tests must call through generated stubs against a running server; calling methods directly is only a unit test.
- Server-streaming, client-streaming, and bidirectional streaming have distinct lifecycles.
- Wait for callbacks using timed latches/queues; never use Thread.sleep for synchronization.
- Capture callback errors and assert them on the test thread.
- Verify payloads, sequence, message counts, and terminal statuses.
- Request onCompleted only closes the sending side; wait for the response observer to finish.
- Cancellation and deadlines must propagate to workers for cleanup.
- Use TCP tests to verify HTTP/2 transport; in-process does not prove TCP/TLS behavior.
- Manage channels per test and servers per the Spring context lifecycle.

End-to-end streaming testing verifies the complete message path through Spring gRPC—from generated client to server handler and response callbacks—while validating statuses, ordering, cancellation, and resource lifecycles.
