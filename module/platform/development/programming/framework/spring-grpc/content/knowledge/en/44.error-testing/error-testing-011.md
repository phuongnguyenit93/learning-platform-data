# Testing Errors After Partial Streaming

In a streaming RPC, the server or client may have already sent and received several messages before the call ends with an error. In that case, tests must not only check the final status, but also verify which messages were observed, their order, which terminal callback was invoked, and whether resources were released. An error arriving after the second message has different semantics from an error occurring before the first message.

**Testing errors after partial streaming** means testing gRPC behavior when a stream has exchanged part of the data and then terminates with an error status, cancellation, or deadline. This lesson belongs to the **Error testing** chapter of the **SPRING_GRPC** module: developing gRPC services in the Spring ecosystem with Protocol Buffers contracts, generated Java code, and client/server implementations for unary or streaming RPCs; learners handle metadata, deadlines, statuses, interceptors, TLS, integration testing, and performance/reliability monitoring. The focus is verifying partial messages and terminal statuses by RPC type, controlling asynchronous callbacks, distinguishing application errors from transport failures, and designing cursors/idempotency when recovering unprocessed data.

## 1. A Stream Can End After Delivering Data

A gRPC streaming call has two parts to observe:

1. Messages exchanged during the stream.
2. Terminal outcome: normal completion, error, or cancellation.

Server-streaming example:

~~~text
Client                         Server
  |                               |
  |---- Watch(request) ---------->|
  |<--- Event(sequence=1) ---------|
  |<--- Event(sequence=2) ---------|
  |<--- DATA_LOSS ----------------|
  |                               |
~~~

The client received two events before receiving the DATA_LOSS error. Those two events were already delivered to the onNext callback; the final status does not erase what the client observed. The application must decide whether to retain partial results, mark the operation incomplete, or resume from a cursor.

An RPC has exactly one terminal outcome. With StreamObserver, the terminal callback is either onError or onCompleted; after either callback, no further onNext or second terminal callback may occur. Tests should catch violations of this lifecycle.

## 2. Distinguish the Four RPC Types

| RPC Type | Message Flow | Where Is a Post-Partial-Data Error Observed? |
| --- | --- | --- |
| Unary | One request, one response | Typically no partial response message; client receives a status/error. |
| Server-streaming | One request, multiple responses | Client may have received some responses via onNext before onError. |
| Client-streaming | Multiple requests, one response | Server may have processed some requests; client receives an error instead of the final response. |
| Bidirectional streaming | Multiple requests, multiple responses | Both sides may have exchanged partial messages before the terminal error. |

Tests must match the method's semantics. Do not use a server-streaming test to conclude that client-streaming or bidirectional streaming behaves identically. For client-streaming, sending request messages does not mean the server processed or committed them. For bidirectional streaming, the two directions progress independently and may observe different message counts when an error occurs.

## 3. What to Assert After a Partial Failure

A good test typically verifies:

- The number of messages the client received or the server processed before the error.
- Message order and sequence/cursor if defined by the protocol.
- Status code and required error details/trailers.
- onError is called exactly once; onCompleted is not called after an error.
- No onNext occurs after the terminal callback.
- Cancellation is propagated to the handler and background work is stopped.
- Queues, timers, listeners, and resources tied to the stream are released.
- No retry/replay duplicates messages or side effects outside the contract.

Do not only assert that the client received StatusRuntimeException. If the server already sent two responses before failing, omitting assertions on those two responses skips the most critical part of the scenario.

## 4. Create a Server-Streaming Service That Fails After Two Messages

Example service that sends two events and then terminates with DATA_LOSS:

~~~java
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

public final class PartialWatchService
        extends EventServiceGrpc.EventServiceImplBase {

    @Override
    public void watch(
            WatchRequest request,
            StreamObserver<Event> responseObserver) {

        responseObserver.onNext(Event.newBuilder()
                .setSequence(1)
                .setPayload("first")
                .build());

        responseObserver.onNext(Event.newBuilder()
                .setSequence(2)
                .setPayload("second")
                .build());

        responseObserver.onError(
                Status.DATA_LOSS
                        .withDescription("event log is inconsistent")
                        .asRuntimeException());
    }
}
~~~

This is a deterministic test fixture. A production service might detect an error while reading from a broker, decoding an event, or verifying a checksum; when that happens, it must choose the appropriate status and terminate the stream exactly once.

Do not call onCompleted() after onError(). Nor should you catch an exception and keep sending messages as if the stream were still active. After a terminal signal, the listener/observer is finished.

## 5. Test Server-Streaming: Retain Partial Messages and Check Terminal Status

An asynchronous client receives each message via onNext, then receives the terminal callback. Use CountDownLatch instead of Thread.sleep() to synchronize the test:

~~~java
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.*;

class PartialServerStreamTest {

    @Test
    void receivesMessagesBeforeTerminalError() throws Exception {
        List<Long> sequences = new CopyOnWriteArrayList<>();
        AtomicReference<Throwable> failure = new AtomicReference<>();
        AtomicInteger terminalCallbacks = new AtomicInteger();
        AtomicInteger completedCallbacks = new AtomicInteger();
        CountDownLatch terminal = new CountDownLatch(1);

        EventServiceGrpc.EventServiceStub stub = testStub();
        stub.watch(WatchRequest.getDefaultInstance(),
                new StreamObserver<>() {
                    @Override
                    public void onNext(Event event) {
                        sequences.add(event.getSequence());
                    }

                    @Override
                    public void onError(Throwable error) {
                        terminalCallbacks.incrementAndGet();
                        failure.set(error);
                        terminal.countDown();
                    }

                    @Override
                    public void onCompleted() {
                        terminalCallbacks.incrementAndGet();
                        completedCallbacks.incrementAndGet();
                        terminal.countDown();
                    }
                });

        assertTrue(terminal.await(2, TimeUnit.SECONDS));
        assertEquals(List.of(1L, 2L), sequences);
        assertEquals(1, terminalCallbacks.get());
        assertEquals(0, completedCallbacks.get());
        assertNotNull(failure.get());
        assertEquals(
                Status.Code.DATA_LOSS,
                Status.fromThrowable(failure.get()).getCode());
    }
}
~~~

testStub() is a helper that creates a channel connected to the fixture server. CopyOnWriteArrayList keeps the test safe when callbacks run on another transport thread. For high-throughput tests, a concurrent queue may be more suitable; here the goal is clear assertions.

The test proves two responses were observed before the terminal DATA_LOSS, only one terminal callback occurred, and onCompleted did not run. The latch await timeout prevents the test from hanging indefinitely if the server fails to send a terminal event.

## 6. Message Ordering and Terminal Errors

gRPC preserves message order within a stream. When the server calls onNext sequentially followed by onError, the client observes the messages sent before the terminal status in stream order. However, do not rely on log ordering across multiple threads or across different RPCs.

If messages carry sequence numbers, tests should assert both content and order:

~~~java
assertEquals(List.of(10L, 11L, 12L), receivedSequences);
assertEquals(Status.Code.DATA_LOSS, terminalStatus);
~~~

If a test only checks receivedSequences.size() == 3, it can miss duplicate or out-of-order messages. For event streams, sequence/cursor is part of the contract that lets clients detect gaps and duplicates.

Do not assume every message the server passed to onNext was processed by the client application before a network reset. With normal application status termination over gRPC transport, message order and terminal trailers are preserved; with sudden transport failures, an in-flight message may never reach the client callback. Transport failure tests must allow distinguishing observed messages from messages the server merely sent.

## 7. Test Client-Streaming: Server Fails After Receiving Partial Requests

In client-streaming, the client sends multiple request messages over a StreamObserver. The server may process several messages and then emit an error instead of returning a summary response:

~~~java
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public final class PartialUploadService
        extends UploadServiceGrpc.UploadServiceImplBase {

    final AtomicInteger received = new AtomicInteger();
    final AtomicBoolean terminal = new AtomicBoolean();

    @Override
    public StreamObserver<UploadChunk> upload(
            StreamObserver<UploadReply> responseObserver) {

        return new StreamObserver<>() {
            @Override
            public void onNext(UploadChunk chunk) {
                int count = received.incrementAndGet();
                if (count == 2 && terminal.compareAndSet(false, true)) {
                    responseObserver.onError(
                            Status.RESOURCE_EXHAUSTED
                                    .withDescription("upload quota reached")
                                    .asRuntimeException());
                }
            }

            @Override
            public void onError(Throwable error) {
                // Stop processing and release upload state.
                terminal.set(true);
            }

            @Override
            public void onCompleted() {
                if (terminal.compareAndSet(false, true)) {
                    responseObserver.onNext(
                            UploadReply.newBuilder()
                                    .setAcceptedChunks(received.get())
                                    .build());
                    responseObserver.onCompleted();
                }
            }
        };
    }
}
~~~

When the server emits an error, the client receives a terminal onError on its response observer; it does not receive the summary UploadReply. The server counter shows the handler received two chunks. Do not assert that a third chunk definitely reached the server just because the client called requestObserver.onNext(chunk3) before observing the error; a send call enqueues a message into the client call, not an application acknowledgement from the server.

In real fixtures, guard against the server calling onCompleted after onError; the example above illustrates the error branch after the second chunk and the completion branch if the stream ends early.

## 8. Test Client-Streaming from the Caller Side

The client test must await the terminal response and check the status:

~~~java
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

AtomicReference<Throwable> failure = new AtomicReference<>();
AtomicInteger responseCount = new AtomicInteger();
CountDownLatch terminal = new CountDownLatch(1);

StreamObserver<UploadReply> responseObserver =
        new StreamObserver<>() {
            @Override
            public void onNext(UploadReply reply) {
                responseCount.incrementAndGet();
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

StreamObserver<UploadChunk> requestObserver =
        asyncStub.upload(responseObserver);

requestObserver.onNext(chunk(1));
requestObserver.onNext(chunk(2));

assertTrue(terminal.await(2, TimeUnit.SECONDS));
assertNotNull(failure.get());
assertEquals(0, responseCount.get());
assertEquals(
        Status.Code.RESOURCE_EXHAUSTED,
        Status.fromThrowable(failure.get()).getCode());
assertEquals(2, service.received.get());
~~~

The example skips sending subsequent chunks once the server has reported an error. In race-condition tests, the client may have already enqueued extra request messages before receiving the terminal callback; in that case assert what the server actually received and do not treat client-side onNext call counts as server-committed messages.

## 9. Test Bidirectional Streaming: Both Directions Progress Independently

A bidirectional stream allows the client and server to send messages independently. One side may have received responses while the other is sending the next request. When an error occurs, tests should record:

- Number of request messages processed by the server.
- Number of response messages received by the client.
- Sequence/correlation between requests and responses.
- Final status and terminal callback.
- Cancellation/cleanup on both sides.

Example where the server replies to the first two requests and then fails:

~~~java
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public final class PartialChatService
        extends ChatGrpc.ChatImplBase {

    @Override
    public StreamObserver<ChatRequest> chat(
            StreamObserver<ChatReply> responseObserver) {

        AtomicInteger received = new AtomicInteger();
        AtomicBoolean terminal = new AtomicBoolean();
        return new StreamObserver<>() {
            @Override
            public void onNext(ChatRequest request) {
                int index = received.incrementAndGet();
                if (index <= 2 && !terminal.get()) {
                    responseObserver.onNext(
                            ChatReply.newBuilder()
                                    .setSequence(index)
                                    .setText("ack-" + index)
                                    .build());
                }
                if (index == 2 && terminal.compareAndSet(false, true)) {
                    responseObserver.onError(
                            Status.INTERNAL
                                    .withDescription("chat stream failed")
                                    .asRuntimeException());
                }
            }

            @Override
            public void onError(Throwable error) {
                // Cleanup session state.
                terminal.set(true);
            }

            @Override
            public void onCompleted() {
                if (terminal.compareAndSet(false, true)) {
                    responseObserver.onCompleted();
                }
            }
        };
    }
}
~~~

The client test records response sequences and the terminal status. Do not assert that the server received every request the client sent; after the server ends the stream, queued messages may go unprocessed. If the protocol requires confirming individual requests, the server must send application acknowledgements containing a sequence/event ID.

## 10. In-Process Tests and Transport-Level Tests

In-process transport is suitable for testing service logic and callback order at the gRPC API level. It is fast, deterministic, and needs no TCP sockets. However, it does not fully test HTTP/2 framing, TLS, proxy timeouts, TCP resets, or real network errors.

| Goal | Test Type to Use |
| --- | --- |
| Server calls onNext then onError | In-process gRPC test. |
| Status code/trailers from service | In-process test; add Netty loopback if transport verification is needed. |
| Client cancels after receiving partial responses | In-process test for logic; Netty loopback for transport behavior. |
| TCP reset between messages | Netty loopback or proxy/network fault testing. |
| TLS handshake error during active stream | Netty TLS test or equivalent integration environment. |
| Proxy idle timeout/maximum stream duration | Test through the actual production-configured proxy/gateway. |

Do not use an in-process test to conclude behavior when a TCP connection resets. Nor do you need network fault injection for every status mapping test; choose the test layer based on what you are proving.

## 11. Use an In-Process Fixture for Status After Partial Messages

A minimal fixture can create the server/channel in the same process:

~~~java
String serverName = InProcessServerBuilder.generateName();

Server server = InProcessServerBuilder
        .forName(serverName)
        .directExecutor()
        .addService(new PartialWatchService())
        .build()
        .start();

ManagedChannel channel = InProcessChannelBuilder
        .forName(serverName)
        .directExecutor()
        .build();

try {
    EventServiceGrpc.EventServiceStub stub =
            EventServiceGrpc.newStub(channel);
    // Call the method and await the terminal callback with CountDownLatch.
} finally {
    channel.shutdownNow();
    server.shutdownNow();
    channel.awaitTermination(2, TimeUnit.SECONDS);
    server.awaitTermination(2, TimeUnit.SECONDS);
}
~~~

directExecutor() can run callbacks directly on the calling thread; never assume callbacks always execute on a separate thread. Still use thread-safe collections if the test might later switch to Netty or another executor. The fixture must close the channel and server in finally to avoid leaking resources.

## 12. Cancellation After the Client Has Received Partial Data

A client may decide to stop a stream after several messages, such as a user cancelling a download or a UI no longer needing events. With an async stub, use ClientResponseObserver to grab ClientCallStreamObserver in beforeStart and call cancel:

~~~java
import io.grpc.stub.ClientCallStreamObserver;
import io.grpc.stub.ClientResponseObserver;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

AtomicReference<ClientCallStreamObserver<WatchRequest>> callRef =
        new AtomicReference<>();
CountDownLatch twoMessages = new CountDownLatch(2);

ClientResponseObserver<WatchRequest, Event> observer =
        new ClientResponseObserver<>() {
            @Override
            public void beforeStart(
                    ClientCallStreamObserver<WatchRequest> requestStream) {
                callRef.set(requestStream);
            }

            @Override
            public void onNext(Event event) {
                twoMessages.countDown();
            }

            @Override
            public void onError(Throwable error) {
                // Cancellation typically finishes client-side with CANCELLED.
            }

            @Override
            public void onCompleted() {
                // Server may complete before the client cancels.
            }
        };

asyncStub.watch(watchRequest, observer);
assertTrue(twoMessages.await(2, TimeUnit.SECONDS));
callRef.get().cancel("client no longer needs events", null);
~~~

Server tests must observe cancellation via ServerCallStreamObserver.setOnCancelHandler() or gRPC Context.CancellationListener, then verify queues/subscriptions/timers are cleaned up. Because a race between the second message and the terminal callback is possible, tests should use a fixture that keeps the stream open after two messages or synchronize with a latch to ensure the client cancels before the server finishes on its own.

Do not treat client cancellation as a server business error. The client may have received all the data it needed for its use case and intentionally closed the stream.

## 13. Deadline Expiration After Partial Messages

Deadlines apply to the whole RPC. Server-streaming can send several responses before the call ends due to the deadline:

~~~text
Client deadline: 500 ms

0 ms     request accepted
120 ms   response sequence=1
240 ms   response sequence=2
500 ms   deadline expires
         client terminal status: DEADLINE_EXCEEDED
~~~

Tests should configure the server to emit messages on a controlled schedule or use a fake dependency with latches. Do not use long Thread.sleep() calls to guess which messages arrive before the deadline. Use a deadline generous enough for CI, synchronize messages with latches, and verify the terminal status.

Observed status can differ by side: the client typically receives DEADLINE_EXCEEDED, while the server observes cancellation when the deadline expires. The server should not continue reading from a broker or doing background work after the call is cancelled if that work only serves the stream.

## 14. Partial Results Are Not Automatically Rolled Back

Once the server sends a response message and the client receives it, gRPC cannot retract that message just because the stream later ends with an error. In client-streaming, the server may have processed part of the requests before failing. In bidirectional streaming, both sides may have created side effects.

The application must define the semantics:

- **Valid partial results:** the client retains data received so far and marks the operation incomplete.
- **All-or-nothing:** the server stages data and commits only when the stream completes successfully; the client does not treat intermediate messages as final commits.
- **Resumable stream:** messages carry a sequence/cursor and the client resumes from the last acknowledged checkpoint.
- **At-least-once:** reconnecting may redeliver events; the client deduplicates using event IDs or sequences.

If all-or-nothing semantics are required for an upload, do not commit business side effects on each onNext unless explicit transactions/staging and cleanup exist. If partial progress is desired, responses should expose sequence/progress and terminal failure so clients do not mistake interim data for a completed result.

## 15. Retries After Partial Streaming

Do not assume gRPC automatically replays a stream after data has already been delivered to the application. Retry commitment depends on call state, response headers, retry buffers, and RPC semantics. Once response headers reach the client, the call is committed and the retry policy stops replaying that attempt.

For streaming workflows, design recovery at the application layer:

1. Every event has a stable event ID and sequence/cursor.
2. The client persists checkpoints after processing data per durability requirements.
3. When the stream fails, the client opens a new RPC from the acknowledged cursor.
4. The server may resend unacknowledged events.
5. The client deduplicates and commits business effects only once.

Tests must prove reconnecting neither drops events nor duplicates side effects. This is a resume protocol, not automatic gRPC retry.

## 16. Verify Trailers and Error Details

The final status may carry trailers containing metadata or rich error details. If the contract requires the client to distinguish transient errors, quotas, or expired cursors, check both the status code and the standardized error detail.

Do not place sensitive payloads in the status description. Error details should contain error codes, retry hints, or permitted checkpoints, not raw request/response messages. Tests should verify:

- Exact status code.
- Description does not leak data.
- Trailer keys are within the allowlist.
- Client can parse the defined error detail.
- No onCompleted follows onError.

## 17. Partial Streaming Failure Test Matrix

| Case | Setup | Key Assertions |
| --- | --- | --- |
| Server-streaming: error after two events | Server calls onNext twice then onError(DATA_LOSS). | Client receives sequences 1, 2 in order; final status DATA_LOSS. |
| Server-streaming: error before first event | Server calls onError immediately. | No onNext; terminal error exactly once. |
| Client-streaming: server fails after two chunks | Server counts two requests then returns RESOURCE_EXHAUSTED. | Client receives no summary response; server processed two chunks. |
| Bidirectional: error after two acks | Server returns two responses then terminates with INTERNAL. | Client receives two acks in order and terminal error. |
| Client cancels after two events | Client cancels after receiving two messages. | Server receives cancellation and cleans up session. |
| Deadline after partial result | Deadline expires while stream is active. | Client receives DEADLINE_EXCEEDED; server stops work. |
| Transport reset | Proxy/socket closes after partial messages. | Assert only messages actually observed; distinguish transport failure. |
| Reconnect/resume | Stream fails after cursor N. | Client resumes from checkpoint and handles duplicates idempotently. |
| Terminal callback lifecycle | Server fails or completes. | Exactly one terminal callback; no messages after terminal. |

## 18. Common Mistakes

| Symptom | Cause | How to Fix |
| --- | --- | --- |
| Test only checks status | Ignores messages received before the error. | Assert partial payloads, sequences, and terminal status. |
| Calling onCompleted after onError | Missing terminal lifecycle management. | Use a terminal guard and a single termination path. |
| Assuming client-sent implies server-received | Confusing client-side onNext with application acknowledgement. | Count messages on the server or use an ack protocol. |
| Testing transport reset with in-process transport | In-process does not simulate TCP/HTTP2 failures. | Use Netty loopback or proxy fault injection. |
| Test depends on sleep | Race between callbacks and assertions. | Use latches, queues, and finite deadlines. |
| Client cancels but server keeps processing | Cancellation not propagated to broker/task. | Register a cancel handler and perform idempotent cleanup. |
| Retries duplicate events/side effects | Missing cursor or idempotency. | Resume protocol, event IDs, and deduplication. |
| Partial response treated as complete | Missing terminal state/progress contract. | Distinguish partial results from committed results. |

## 19. Hands-On Exercises

1. Write a server-streaming fixture that emits two events and terminates with DATA_LOSS; assert both sequences and terminal status.
2. Write a client-streaming fixture that receives two chunks and returns RESOURCE_EXHAUSTED; verify no summary response arrives.
3. Write a bidirectional fixture that returns two acknowledgements and terminates with INTERNAL.
4. Use an in-process server/channel to test application status and Netty loopback to test transport resets.
5. Cancel a stream after partial responses; verify the server receives cancellation and releases subscriptions/queues.
6. Set a deadline shorter than the expected stream duration; verify partial messages and final DEADLINE_EXCEEDED.
7. Design cursor/resume and test duplicate delivery after reconnect.
8. Verify a single terminal callback, no onNext after terminal, and no out-of-contract side effects.

After this lesson, you should know how to test messages exchanged before an error for each streaming RPC type, verify terminal status/callbacks and cleanup, and distinguish application statuses from transport failures. When partial progress has clear sequences, cursors, and acknowledgements, a Spring gRPC system can recover streams without silently losing data or duplicating side effects.
