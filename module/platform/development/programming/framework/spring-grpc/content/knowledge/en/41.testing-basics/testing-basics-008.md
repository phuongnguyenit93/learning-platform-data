# Testing async stubs

An async stub is a client API generated from a Protobuf service to invoke gRPC without blocking the calling thread while waiting for responses. Results are delivered through `StreamObserver`: the client receives messages via `onNext`, finishes successfully via `onCompleted`, or receives failures via `onError`. This is the API required when testing client-streaming and bidirectional-streaming RPCs; it is also suitable for testing unary and server-streaming RPCs under a callback model.

In Spring gRPC, async stub tests must verify both the RPC outcome and the callback lifecycle: which callbacks fire, message count and order, error statuses, deadlines, cancellation, and resource cleanup. Because callbacks may execute on a different thread than the test thread, assertions must be synchronized via latches, futures, or queues; never read a collection updated by callbacks without synchronization.

## 1. Async stubs and callback lifecycle

A generated async stub delivers results via callbacks rather than returning responses directly:

```text
Client calls asyncStub.method(request, responseObserver)
                   |
                   v
              gRPC call
                   |
          +--------+--------+
          |                 |
       success             error
          |                 |
       onNext(...)        onError(...)
          |                 |
       onCompleted       terminal
          |
       terminal
```

For unary RPCs, success normally produces one `onNext(response)` followed by `onCompleted()`. For server-streaming, there can be multiple `onNext` calls before `onCompleted`. If the RPC fails, `onError` is the terminal callback; the client must not expect `onCompleted` afterward.

For client-streaming and bidirectional-streaming, the async stub method returns a `StreamObserver<Request>` for the client to send requests. Responses are still received via the `StreamObserver<Response>` passed in when starting the call. The client finishes the request stream with `onCompleted()`; the server may send a final response after receiving all requests.

Never assume callbacks always run on the thread that invoked the stub. The executor, transport, and server configuration determine how callbacks are scheduled. Tests must be safe for asynchronous callbacks even if in-process tests sometimes execute callbacks directly.

## 2. RPC types supported by async stubs

| RPC type | Calling generated async stub | Client-side outcome |
| --- | --- | --- |
| Unary | `stub.getOrder(request, responseObserver)` | One response or one error |
| Server-streaming | `stub.watchOrders(request, responseObserver)` | Multiple responses in one stream |
| Client-streaming | `StreamObserver<Request> requests = stub.upload(responseObserver)` | Send multiple requests, receive one final response |
| Bidirectional-streaming | `StreamObserver<Request> requests = stub.chat(responseObserver)` | Send and receive multiple independent messages over the stream |

Async stubs support all four RPC types. This is an important difference from blocking stubs, which provide synchronous APIs only for unary and server-streaming RPCs.

## 3. Setting up an in-process server and channel

The in-process transport enables testing services and generated async stubs within the same JVM without opening a TCP port:

```java
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import java.io.IOException;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;

class GreeterAsyncStubTest {
    private Server server;
    private ManagedChannel channel;
    private GreeterGrpc.GreeterStub stub;

    @BeforeEach
    void setUp() throws IOException {
        String serverName = InProcessServerBuilder.generateName();

        server = InProcessServerBuilder.forName(serverName)
            .addService(new GreeterService())
            .build()
            .start();

        channel = InProcessChannelBuilder.forName(serverName)
            .build();

        stub = GreeterGrpc.newStub(channel);
    }

    @AfterEach
    void tearDown() throws InterruptedException {
        if (channel != null) {
            channel.shutdownNow()
                .awaitTermination(5, TimeUnit.SECONDS);
        }
        if (server != null) {
            server.shutdownNow()
                .awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

`GreeterGrpc.GreeterStub` is the generated async stub; `newStub(channel)` creates a stub bound to the test channel. Generate a fresh server name per fixture so tests do not accidentally connect to another server. Close the channel before the server and use a finite timeout so teardown does not hang forever.

This example assumes test dependencies include `grpc-inprocess`, generated Protobuf classes, grpc-stub, and JUnit 5, with grpc-java versions managed consistently by a BOM/version catalog. This test verifies the in-JVM gRPC call pipeline; it does not test TLS, HTTP/2 over sockets, or ingress.

## 4. Testing unary callbacks

For unary RPCs, use a `CountDownLatch` to await callback completion within a finite duration. Store responses and errors in `AtomicReference` instances so the test thread can read them safely:

```java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.stub.StreamObserver;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;

@Test
void receivesUnaryResponse() throws InterruptedException {
    HelloRequest request = HelloRequest.newBuilder()
        .setName("An")
        .build();

    CountDownLatch completed = new CountDownLatch(1);
    AtomicReference<HelloReply> response = new AtomicReference<>();
    AtomicReference<Throwable> failure = new AtomicReference<>();
    AtomicInteger responseCount = new AtomicInteger();

    stub.sayHello(request, new StreamObserver<>() {
        @Override
        public void onNext(HelloReply value) {
            response.set(value);
            responseCount.incrementAndGet();
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

    assertTrue(completed.await(2, TimeUnit.SECONDS),
        "RPC did not complete before test timeout");
    assertNull(failure.get());
    assertEquals(1, responseCount.get());
    assertEquals("Hello, An", response.get().getMessage());
}
```

The two-second timeout on `await` is a test safety limit to prevent the suite from hanging; it does not replace an RPC deadline. In production-like tests, set an explicit deadline on the stub to test the client's timeout policy.

Do not place JUnit assertions directly inside `onNext` expecting assertion failures to propagate back to the test thread. The callback may execute on another thread and assertion failures might not fail the test as intended. Capture results, await the terminal callback, and run assertions on the test thread.

## 5. Testing error statuses via onError

When the server terminates an RPC with an error status, the async stub invokes `onError`. Use `Status.fromThrowable` to read the status code:

```java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

@Test
void receivesInvalidArgument() throws InterruptedException {
    HelloRequest request = HelloRequest.newBuilder()
        .setName(" ")
        .build();

    CountDownLatch terminal = new CountDownLatch(1);
    AtomicReference<Throwable> failure = new AtomicReference<>();
    AtomicInteger unexpectedResponses = new AtomicInteger();

    stub.sayHello(request, new StreamObserver<>() {
        @Override
        public void onNext(HelloReply value) {
            unexpectedResponses.incrementAndGet();
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

    assertTrue(terminal.await(2, TimeUnit.SECONDS));
    assertNotNull(failure.get());
    assertEquals(0, unexpectedResponses.get());
    assertEquals(
        Status.Code.INVALID_ARGUMENT,
        Status.fromThrowable(failure.get()).getCode());
}
```

In real tests, replace `fail` inside callbacks with a flag or counter to avoid running assertions on the callback thread. You can use `AtomicInteger unexpectedResponses` and assert after the latch completes. Verify statuses per contract: `INVALID_ARGUMENT`, `NOT_FOUND`, `UNAUTHENTICATED`, `PERMISSION_DENIED`, `UNAVAILABLE`, or other expected codes.

## 6. Testing server-streaming and message ordering

With server-streaming, the `onNext` callback can be invoked multiple times. Collect messages into a thread-safe collection, then wait for `onCompleted`:

```java
import java.util.List;
import java.util.concurrent.ConcurrentLinkedQueue;

@Test
void receivesServerStreamInOrder() throws InterruptedException {
    ConcurrentLinkedQueue<String> messages =
        new ConcurrentLinkedQueue<>();
    CountDownLatch completed = new CountDownLatch(1);
    AtomicReference<Throwable> failure = new AtomicReference<>();

    stub.sayHelloMany(
        HelloRequest.newBuilder().setName("An").build(),
        new StreamObserver<>() {
            @Override
            public void onNext(HelloReply value) {
                messages.add(value.getMessage());
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

    assertTrue(completed.await(2, TimeUnit.SECONDS));
    assertNull(failure.get());
    assertEquals(
        List.of("Hello, An", "Welcome, An", "Goodbye, An"),
        List.copyOf(messages));
}
```

Verify both the count and order of responses. If a stream can emit a huge number of messages, avoid buffering all payloads in memory just for testing; use a bounded queue, counter, checksum, or per-message assertions. Always configure a deadline or test timeout so a server forgetting `onCompleted` never hangs the suite forever.

## 7. Testing client-streaming

For client-streaming RPCs, call the method on the async stub to obtain `StreamObserver<Request>`. The client sends multiple messages via `onNext`, then calls `onCompleted` to signal it is done sending. The server returns one final response through the response observer.

Example contract:

```proto
service UploadService {
  rpc Upload(stream UploadChunk) returns (UploadSummary);
}
```

Test sending chunks and waiting for the summary:

```java
@Test
void uploadsMultipleChunks() throws InterruptedException {
    CountDownLatch completed = new CountDownLatch(1);
    AtomicReference<UploadSummary> summary = new AtomicReference<>();
    AtomicReference<Throwable> failure = new AtomicReference<>();

    StreamObserver<UploadSummary> responseObserver =
        new StreamObserver<>() {
            @Override
            public void onNext(UploadSummary value) {
                summary.set(value);
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
        };

    StreamObserver<UploadChunk> requests = stub.upload(responseObserver);
    requests.onNext(chunk(1, "part-a"));
    requests.onNext(chunk(2, "part-b"));
    requests.onNext(chunk(3, "part-c"));
    requests.onCompleted();

    assertTrue(completed.await(2, TimeUnit.SECONDS));
    assertNull(failure.get());
    assertEquals(3, summary.get().getChunkCount());
}
```

`chunk(...)` is a test factory creating an UploadChunk matching the application schema. Never call `requests.onCompleted()` before sending all messages. If the client terminates the request stream with `onError`, the server should treat the call as abnormally terminated and must not be assumed to return a successful summary.

## 8. Testing bidirectional-streaming

With bidi-streaming, the client and server can send messages independently on the same call. The client provides a response observer when opening the stream and uses the request observer to send messages:

```proto
service ChatService {
  rpc Chat(stream ChatMessage) returns (stream ChatMessage);
}
```

Tests should verify:

- Each valid request produces a response per contract.
- Response order is preserved if the contract requires it.
- The client can send subsequent requests before earlier responses complete.
- The server can finish with `onCompleted` or an error status.
- The client can cancel the stream and the server stops related work.

Never assume an `onNext` from the client means the server has already processed the request and its response has arrived. When verifying round-trips per message, include a correlation ID in the message and wait for the corresponding response instead of merely counting sent requests.

Concise example for a correlation-ID echo service:

```java
BlockingQueue<String> receivedIds = new LinkedBlockingQueue<>();
CountDownLatch terminal = new CountDownLatch(1);
AtomicReference<Throwable> failure = new AtomicReference<>();

StreamObserver<ChatMessage> responses = new StreamObserver<>() {
    @Override
    public void onNext(ChatMessage value) {
        receivedIds.add(value.getCorrelationId());
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
};

StreamObserver<ChatMessage> requests = stub.chat(responses);
requests.onNext(chatMessage("c-1", "first"));
requests.onNext(chatMessage("c-2", "second"));
requests.onCompleted();

assertTrue(terminal.await(2, TimeUnit.SECONDS));
assertNull(failure.get());
assertEquals(List.of("c-1", "c-2"), List.of(
    receivedIds.poll(), receivedIds.poll()));
```

This example assumes the server echoes each correlation ID once; `chatMessage` is a factory constructing messages per the application schema. For protocols that do not guarantee response ordering, match against a map of correlation IDs rather than comparing list order.

## 9. Deadlines, cancellation, and flow control

Async does not mean a call finishes by itself. Always set a finite deadline:

```java
GreeterGrpc.GreeterStub boundedStub =
    stub.withDeadlineAfter(300, TimeUnit.MILLISECONDS);

boundedStub.sayHello(request, responseObserver);
```

When a deadline expires, the client observer receives `onError` typically with status `DEADLINE_EXCEEDED`. Active cancellation can be triggered via `ClientResponseObserver` and `ClientCallStreamObserver`:

```java
AtomicReference<ClientCallStreamObserver<HelloRequest>> callControl =
    new AtomicReference<>();
CountDownLatch callStarted = new CountDownLatch(1);

ClientResponseObserver<HelloRequest, HelloReply> observer =
    new ClientResponseObserver<>() {
        @Override
        public void beforeStart(
                ClientCallStreamObserver<HelloRequest> requestStream) {
            callControl.set(requestStream);
            callStarted.countDown();
        }

        @Override
        public void onNext(HelloReply value) {
            // Capture response for assertions.
        }

        @Override
        public void onError(Throwable error) {
            // Capture terminal status.
        }

        @Override
        public void onCompleted() {
            // Record successful completion.
        }
    };

stub.sayHello(request, observer);
assertTrue(callStarted.await(1, TimeUnit.SECONDS));
callControl.get().cancel("test cancellation", null);
```

In a complete test, wait for `beforeStart` to run before grabbing the control handle and assert the terminal status after cancellation. Server handlers should observe cancellation via gRPC Context or a cancellation callback to stop long-running work; canceling only on the client while the server keeps processing forever is a resource leak bug.

For streaming responses, `ClientResponseObserver.beforeStart` also enables inbound flow control:

```java
@Override
public void beforeStart(
        ClientCallStreamObserver<WatchRequest> requestStream) {
    requestStream.disableAutoInboundFlowControl();
    requestStream.request(1);
}

@Override
public void onNext(WatchReply value) {
    process(value);
    callControl.get().request(1);
}
```

The example above demonstrates message-by-message demand. Flow-control tests should verify that the client receives only the requested number of messages and requests more after processing; never call `request` concurrently from arbitrary threads without designed synchronization.

## 10. Thread safety and preventing hanging tests

Callbacks can run concurrently with the test thread. Choose synchronization primitives suited to the data:

| Need | Suitable storage |
| --- | --- |
| Single response | `AtomicReference<T>` |
| Single terminal error | `AtomicReference<Throwable>` |
| Counting callbacks | `AtomicInteger` or `LongAdder` |
| Multiple messages | `ConcurrentLinkedQueue<T>` or synchronized collection |
| Waiting for terminal callback | `CountDownLatch` |
| Async result with timeout | `CompletableFuture<T>` with `get(timeout, unit)` |

Guidelines:

- Never use `Thread.sleep()` to guess whether callbacks have executed.
- Always wait with a finite timeout and fail clearly if time expires.
- Never call `onNext` after `onCompleted` or `onError`.
- Each observer has at most one terminal event.
- Never block inside a callback waiting for another callback that requires the same executor.
- Clean up streams, channels, servers, and executors when the test finishes.

If `directExecutor()` is used on an in-process server, callbacks may run immediately on the calling thread. That helps simple logic tests but misses many race conditions. Add tests using a bounded asynchronous executor to verify thread safety and scheduling.

## 11. Spring gRPC integration and transport boundaries

In-process tests verify that generated stubs call the right service implementation and callbacks receive the expected results. To verify Spring wiring, use a test context with the same starter and production configuration:

1. Register service implementations, interceptors, and dependencies as Spring beans.
2. Start the starter-managed server on a test port or dynamic port.
3. Obtain channels/stubs from the real client configuration.
4. Call unary/streaming RPCs and verify callbacks/statuses.
5. Close the Spring context, channel, and server; verify no executors/streams remain alive.

The in-process transport does not verify TCP, TLS/mTLS, HTTP/2 negotiation, DNS, proxies, ingress, or service meshes. Those require TCP/TLS integration tests. Never conclude the Spring starter exposed the right port solely from a fixture built with `InProcessServerBuilder`.

## 12. Test matrix and practice exercise

| Group | Test case | PASS condition |
| --- | --- | --- |
| Unary success | Valid request | One `onNext`, then `onCompleted` |
| Unary error | Invalid request | `onError` carrying expected status |
| Server streaming | Multiple responses | Correct count and order |
| Client streaming | Multiple requests then complete | Receives one accurate summary |
| Bidirectional | Interleaved requests/responses | Correlation and ordering match contract |
| Deadline | Call exceeds budget | `onError` with `DEADLINE_EXCEEDED` |
| Cancellation | Client cancels stream | Terminal status and proper server cleanup |
| Flow control | Message-by-message request | Does not receive beyond demand |
| Metadata | Request ID/credentials | Server reads verified metadata |
| Concurrency | Multiple concurrent calls | No state leaked across observers |
| Cleanup | Test finishes | No remaining streams/channels/servers/executors |
| Spring wiring | Starter-managed server | Beans, interceptors, and lifecycle correct |
| Transport | TCP/TLS | HTTP/2, certificates, and networking work |

**Exercise:** `OrderService` has unary `GetOrder`, server-streaming `WatchOrderEvents`, client-streaming `UploadOrderLines`, and bidi-streaming `ExchangeUpdates`. The client uses an async stub; every call must carry a deadline and a request ID.

1. Set up an in-process server/channel and create a generated async stub.
2. Write a unary test using a latch, checking a single response and terminal callback.
3. Write a status test verifying `NOT_FOUND` and `INVALID_ARGUMENT` via `onError`.
4. Verify `WatchOrderEvents` returns events in the right order.
5. Send multiple lines via `UploadOrderLines`, call `onCompleted`, and verify the summary.
6. Test the bidi stream using correlation IDs to verify each round-trip.
7. Test deadlines, cancellation, and server cleanup.
8. Test flow control using `request(1)` and handling each response.
9. Verify the request ID through an interceptor without sharing mutable fields across calls.
10. Add Spring context and TCP/TLS integration tests for their respective boundaries.

**Self-check questions:**

- Why do async stubs deliver results through `StreamObserver`?
- What is the callback order for a successful unary call?
- When is `onError` a terminal event?
- Where does client-streaming obtain its request observer?
- Why does client-side `onNext` not prove the server has processed the message?
- How do you synchronize assertions using latches and atomic references?
- How do deadlines and cancellation differ?
- What do `disableAutoInboundFlowControl` and `request(n)` control?
- Why should you not block inside callbacks?
- Which transport properties cannot be verified by in-process tests?

**Remember:** Testing async stubs requires verifying callback lifecycles, responses/statuses, message order, deadlines, and cancellation. Use latches/futures with timeouts, atomic references, and thread-safe collections to synchronize results; test unary, server-streaming, client-streaming, and bidi-streaming separately. In-process tests verify call behavior, Spring context tests verify wiring, and TCP/TLS tests verify production transport.
