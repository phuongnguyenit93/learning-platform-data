# Client reading individual messages and backpressure

## 1. The problem: server sends faster than client processes

In the **SPRING_GRPC** module, we develop gRPC services on Spring from Protocol Buffers contracts, generate Java code, and implement unary or streaming RPCs. The **Server streaming** section covers the scenario where the client sends **one request**, and the server emits **multiple responses** over time. The client can display or process each response as soon as it arrives, without waiting for the entire result set.

Receiving individual messages is very useful for progress tracking, log streaming, status change notifications, reading records from a long query, or returning batches of results. However, an operational question arises immediately: **what happens when the server produces 1,000 messages/second while the client can only process 100 messages/second?**

If the application keeps receiving and pushing every message into an unbounded queue, the backlog grows by roughly 900 messages/second. In 60 seconds, this queue alone can accumulate about 54,000 messages. Actual memory footprint also depends on payload size, metadata, and object structure.

**Backpressure** is the mechanism for limiting or propagating consumption capacity backward so the source does not continuously produce more data than the system can process. With gRPC Java, distinguish three layers:

1. **Client application:** callbacks, iterators, and tasks writing to a database, updating UI, or processing data.
2. **gRPC/HTTP/2:** transport buffers and flow control mechanisms; can delay transmitting further data when the receiver is not ready.
3. **Server producer:** where events are created (database cursor, timer, broker, worker, or computed data), where we must bound queues, throttle upstream, or implement storage/replay.

~~~mermaid
flowchart LR
    P["Producer on server"] --> Q["Bounded buffer"]
    Q --> S["gRPC server: onNext"]
    S --> H["HTTP/2 flow control"]
    H --> C["gRPC Java client"]
    C --> A["Client processes each message"]
    A -. "Processing capacity / request(n)" .-> C
    H -. "Transmission limit" .-> S
    Q -. "Upstream throttling" .-> P
~~~

**Do not conflate these three layers.** HTTP/2 flow control does not automatically bound every application queue. Calling `onNext` on the server is not confirmation that the client has finished processing the message. And a client requesting only one more message does not automatically force an independent event source to stop producing.

## 2. Backpressure concepts in server streaming

Suppose the server emits the sequence 1, 2, 3, 4, 5 over a single RPC. gRPC preserves the order of messages sent sequentially on that RPC. What needs to be controlled is **the rate at which new messages are delivered to client-side processing code**, while bounding the amount of data sitting in buffers.

| Scenario | What can happen | Appropriate handling |
|---|---|---|
| Server and client have similar speeds | Callbacks are processed steadily | Use automatic receive mode if resources are stable |
| Client is temporarily slow | Messages wait in buffers | Limit in-flight processing count and buffered message count |
| Client is persistently slow | Backlog grows, latency rises, or OOM occurs | Throttle producer, bound queue, cancel, or apply a data-loss policy |
| Old data may be dropped | Only the latest state matters | Coalesce/overwrite older state under an explicit contract |
| Every event must be kept | Cannot arbitrarily drop messages | Use durable storage, cursor/replay, quotas, and upstream backpressure |
| Client no longer needs data | Stream may still be open | Cancel RPC, stop subscription, and clean up resources |

Backpressure does not guarantee **zero queued messages**: gRPC, HTTP/2, the kernel, and the application may already hold buffered data before throttling signals take effect. The practical goal is to keep queue sizes and in-flight work within predictable bounds, control latency, and define behavior when limits are exceeded.

### Two questions to answer before writing code

- **Which messages must never be lost?** For example, a payment event must be fully persisted; progress updates 31%, 32%, 33% may only need 33% if the contract permits.
- **Under overload, can the data source slow down?** A database cursor or backpressure-aware publisher is easier to throttle than an external event source pushing continuously without waiting for consumers. A source that cannot slow down needs bounded buffers and an explicit durability, coalescing, or rejection policy.

## 3. Protocol Buffers contract for the example

We build a finite event-emitting API to observe how the client reads each message. File `src/main/proto/event_feed.proto`:

~~~proto
syntax = "proto3";

package feed.v1;

option java_multiple_files = true;
option java_package = "com.example.feed.rpc";
option java_outer_classname = "EventFeedProto";

service EventFeedService {
  rpc WatchEvents(WatchEventsRequest) returns (stream FeedEvent);
}

message WatchEventsRequest {
  string topic = 1;
  int32 max_events = 2; // Limit 1..5 for this example.
}

message FeedEvent {
  string topic = 1;
  int64 sequence = 2;
  string payload = 3;
}
~~~

The `stream` keyword in `returns (stream FeedEvent)` defines **server streaming**: one `WatchEventsRequest` and multiple `FeedEvent` responses. `protoc` together with the `protoc-gen-grpc-java` plugin generates the Java messages, `EventFeedServiceGrpc.EventFeedServiceImplBase`, and client stubs.

The `sequence` field helps verify receive order and detect duplicate/missing messages at the business layer. Simply adding this field does **not** create network disconnect recovery; resuming from a specific sequence requires designing an event store and a cursor/replay contract.

## 4. Demo server: emitting ordered messages

The following example is a Spring gRPC service generating up to five messages directly in a loop. We intentionally keep the server simple to observe how the client controls **when messages are delivered to callbacks**.

~~~java
package com.example.feed;

import com.example.feed.rpc.EventFeedServiceGrpc;
import com.example.feed.rpc.FeedEvent;
import com.example.feed.rpc.WatchEventsRequest;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Service;

@Service
public class EventFeedServiceImpl
        extends EventFeedServiceGrpc.EventFeedServiceImplBase {

    @Override
    public void watchEvents(
            WatchEventsRequest request,
            StreamObserver<FeedEvent> responses) {

        String topic = request.getTopic().trim();
        int count = request.getMaxEvents();

        if (topic.isEmpty() || count < 1 || count > 5) {
            responses.onError(Status.INVALID_ARGUMENT
                    .withDescription("topic required; max_events must be 1..5")
                    .asRuntimeException());
            return;
        }

        for (long i = 1; i <= count; i++) {
            FeedEvent event = FeedEvent.newBuilder()
                    .setTopic(topic)
                    .setSequence(i)
                    .setPayload("Event " + i)
                    .build();
            responses.onNext(event);
        }

        responses.onCompleted();
    }
}
~~~

In a Spring gRPC application with automatic detection of Spring beans implementing `BindableService`, `@Service` registers the service through the container. With other integrations, configure service registration according to the library in use; the protobuf contract and `StreamObserver` remain the same.

**Very important limitation of the demo:** this code may call `onNext` all five times before the client finishes processing the first message. The gRPC runtime may buffer the remaining messages. **Client manual flow control does not force the demo producer to stop creating messages right after one `onNext`.** When event counts are large or streams are long-lived, the server must monitor readiness, stop the producer appropriately, and use bounded buffers.

## 5. Approach 1: blocking stub reading message by message with Iterator

A blocking client receives an `Iterator<FeedEvent>` from the streaming method. `hasNext()` and `next()` pull one response at a time, potentially blocking the calling thread if the next message has not arrived yet.

~~~java
package com.example.feed.client;

import com.example.feed.rpc.EventFeedServiceGrpc;
import com.example.feed.rpc.FeedEvent;
import com.example.feed.rpc.WatchEventsRequest;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.StatusRuntimeException;

import java.util.Iterator;
import java.util.concurrent.TimeUnit;

public class BlockingFeedReader {
    public static void main(String[] args) {
        // Dev example; production needs TLS and configured host/port.
        ManagedChannel channel = ManagedChannelBuilder
                .forAddress("localhost", 9090)
                .usePlaintext()
                .build();

        try {
            WatchEventsRequest request = WatchEventsRequest.newBuilder()
                    .setTopic("stock")
                    .setMaxEvents(5)
                    .build();

            Iterator<FeedEvent> stream = EventFeedServiceGrpc
                    .newBlockingStub(channel)
                    .withDeadlineAfter(15, TimeUnit.SECONDS)
                    .watchEvents(request);

            while (stream.hasNext()) {
                FeedEvent event = stream.next();
                // Intentionally process each message on the same thread.
                process(event);
            }
            System.out.println("Received complete stream");
        } catch (StatusRuntimeException error) {
            System.err.println("RPC failed: " + error.getStatus());
        } finally {
            channel.shutdownNow();
        }
    }

    private static void process(FeedEvent event) {
        System.out.printf("sequence=%d payload=%s%n",
                event.getSequence(), event.getPayload());
    }
}
~~~

When `process(event)` runs synchronously, the client does not build an application queue holding every event before processing. However, the `Iterator` may still use underlying buffers, and reading slowly does not guarantee the server has not already produced more messages.

Pros: readable, clear processing order, suitable for batch jobs or console tools with few connections. Cons: thread is blocked waiting for messages, hard to integrate with applications requiring high-concurrency async processing. If `process` performs slow I/O, set appropriate deadlines and check stream volume. **Do not** run this blocking loop on an event loop or request thread that must return quickly.

If the server returns `onError` after a few responses, `hasNext()`/`next()` can throw `StatusRuntimeException`. The client must not treat receiving three events as proof that the entire RPC succeeded.

## 6. Approach 2: async stub receiving messages automatically

With the asynchronous stub, the client passes a `StreamObserver<FeedEvent>` to receive callbacks:

~~~java
WatchEventsRequest request = WatchEventsRequest.newBuilder()
        .setTopic("stock")
        .setMaxEvents(5)
        .build();

EventFeedServiceGrpc.newStub(channel)
        .withDeadlineAfter(15, TimeUnit.SECONDS)
        .watchEvents(request, new StreamObserver<FeedEvent>() {
            @Override
            public void onNext(FeedEvent value) {
                System.out.println(value.getSequence());
            }

            @Override
            public void onError(Throwable error) {
                System.err.println(Status.fromThrowable(error));
            }

            @Override
            public void onCompleted() {
                System.out.println("Stream finished");
            }
        });
~~~

This snippet assumes `channel` along with imports for messages, stubs, `StreamObserver`, `Status`, and `TimeUnit` are already present. The async call returns immediately; the application must keep the channel alive until receiving `onError` or `onCompleted`.

In default receive mode, gRPC Java manages requests for additional messages on behalf of the observer. This works well if `onNext` executes fast and does not offload data into an unbounded queue. However:

~~~java
@Override
public void onNext(FeedEvent value) {
    unboundedQueue.add(value); // Dangerous if the queue consumer is slow.
}
~~~

Because the callback finishes very quickly, the runtime may keep delivering events while the worker draining the queue falls behind. This is an example of **fast network reading but slow business processing**. Backpressure must be tied to **completed work**, not merely how fast the callback returns.

## 7. Approach 3: ClientResponseObserver controlling receive demand

gRPC Java provides `ClientResponseObserver<ReqT, RespT>` for async clients that want to control inbound message flow. Before the RPC starts, the runtime calls:

~~~java
void beforeStart(ClientCallStreamObserver<ReqT> requestStream)
~~~

Inside `beforeStart`, the client can disable automatic message requesting and grant an **initial receive count**:

~~~java
requestStream.disableAutoRequestWithInitial(1);
~~~

After finishing processing a message, the client explicitly grants more demand:

~~~java
requestStream.request(1);
~~~

The meaning of `request(1)` here is **allowing gRPC to deliver one more response to the observer**. It does not send a new application message to the server, nor is it a data persistence ACK. This is how *demand* is expressed on the receiving side in the gRPC Java API.

### Java example: requesting the next message only after finishing processing

~~~java
package com.example.feed.client;

import com.example.feed.rpc.EventFeedServiceGrpc;
import com.example.feed.rpc.FeedEvent;
import com.example.feed.rpc.WatchEventsRequest;
import io.grpc.stub.ClientCallStreamObserver;
import io.grpc.stub.ClientResponseObserver;

import java.util.concurrent.CompletableFuture;

public final class ManualDemandFeedReader {

    public static CompletableFuture<Void> read(
            EventFeedServiceGrpc.EventFeedServiceStub stub,
            WatchEventsRequest request) {

        CompletableFuture<Void> finished = new CompletableFuture<>();

        stub.watchEvents(
                request,
                new ClientResponseObserver<WatchEventsRequest, FeedEvent>() {

                    private ClientCallStreamObserver<WatchEventsRequest> control;

                    @Override
                    public void beforeStart(
                            ClientCallStreamObserver<WatchEventsRequest> stream) {
                        this.control = stream;
                        stream.disableAutoRequestWithInitial(1);
                    }

                    @Override
                    public void onNext(FeedEvent event) {
                        try {
                            // Synchronous processing example, creating no extra queue.
                            applyEvent(event);

                            // Only request the next response after processing completes.
                            control.request(1);
                        } catch (RuntimeException error) {
                            // Client-side error: proactively stop the call.
                            control.cancel("Cannot process feed event", error);
                            finished.completeExceptionally(error);
                        }
                    }

                    @Override
                    public void onError(Throwable error) {
                        finished.completeExceptionally(error);
                    }

                    @Override
                    public void onCompleted() {
                        finished.complete(null);
                    }
                });

        return finished;
    }

    private static void applyEvent(FeedEvent event) {
        System.out.printf("Applied #%d: %s%n",
                event.getSequence(), event.getPayload());
    }
}
~~~

How to invoke from a client holding a `ManagedChannel`:

~~~java
WatchEventsRequest request = WatchEventsRequest.newBuilder()
        .setTopic("stock")
        .setMaxEvents(5)
        .build();

EventFeedServiceGrpc.EventFeedServiceStub stub =
        EventFeedServiceGrpc.newStub(channel)
                .withDeadlineAfter(15, TimeUnit.SECONDS);

ManualDemandFeedReader.read(stub, request)
        .get(20, TimeUnit.SECONDS);
~~~

At the call site, `channel` must be managed and closed appropriately; imports for `WatchEventsRequest`, `EventFeedServiceGrpc`, `TimeUnit`, and `ManualDemandFeedReader` must be available. In a Spring application, inject/reuse a managed channel or stub rather than creating a new channel per request. `CompletableFuture.get` is only suitable for console/test examples; never block an event loop in a production application.

**Points to understand accurately:**

- `disableAutoRequestWithInitial(1)` must be called in `beforeStart`, before response reception begins.
- `request(1)` does not "tell the server to generate exactly one event"; the server may already have called `onNext` multiple times and the runtime may be holding queued messages.
- In the example, calling `request(1)` after `applyEvent` ties receive capacity to **synchronous** processing completion. If `applyEvent` merely enqueues work onto another thread and returns, this bound no longer reflects actual processing speed.
- `onCompleted` and `onError` are mutually exclusive outcomes. Once a terminal callback arrives, no further messages should be requested.
- If client processing fails, cancel the RPC via the appropriate gRPC API and handle the application error; simply throwing an exception from `onNext` does not replace proper cancellation/cleanup.

### Multi-message receive window

Reading one message at a time is easy to reason about, but it can reduce throughput because each message waits for processing to finish before requesting the next. An alternative is a small window:

~~~java
stream.disableAutoRequestWithInitial(8);
~~~

After **one** event finishes processing, replenish **one** receive permit via `request(1)`. When the application maintains exact tracking of in-flight work, this window bounds the number of responses delivered to—but not yet processed by—the client layer. The value 8 is illustrative only; tune based on latency, payload size, CPU, memory, and processing speed. Do not confuse this with HTTP/2 window size measured in bytes.

## 8. Processing asynchronously while preserving backpressure

Suppose writing an event to the database takes 200 ms. Performing heavy work directly inside `onNext` blocks the gRPC callback and can affect other calls sharing the executor. A better approach is to offload processing to an appropriate executor, yet **call `request(1)` only after the task completes**.

Pseudocode example focusing on coordination:

~~~text
beforeStart(stream):
    control = stream
    control.disableAutoRequestWithInitial(1)

onNext(event):
    submit_to_single_worker(() -> {
        try:
            persist_and_apply(event)
            control.request(1)  // Demand is replenished after processing.
        catch error:
            control.cancel("processing failed", error)
    })

onCompleted():
    submit_to_single_worker(() -> mark_rpc_completed_after_prior_work())

onError(error):
    submit_to_single_worker(() -> mark_rpc_failed_after_prior_work(error))
~~~

When using a **single sequential executor**, processing of earlier messages finishes before the client records RPC termination on the same queue. A receive window of `1` also keeps the number of pending tasks created by this stream bounded. If a larger window is used, employ a **bounded** queue and account for concurrently executing messages.

Pseudocode must be hardened for production: handle rejected execution errors, shut down the executor cleanly with the lifecycle, handle cancellation, and ensure `request` is never called after the call terminates. If processing across multiple parallel workers, results may finish out of receive order; if business logic requires ordering, serialize the state-application step or track sequences to reorder.

**Avoid two opposite mistakes:**

1. **Requesting too early:** receiving a message and immediately calling `request(1)`, then pushing heavy work into an unbounded queue. The data stream can outrun the real consumer.
2. **Never requesting more:** disabling auto-request, granting one initial message, and forgetting to call `request(1)` after processing. The client receives the first message and stalls forever even though the server has more data, until the deadline eventually expires.

## 9. Server side: readiness and throttling the producer

Controlling receive callbacks on the client is **half the problem**. If the server producer keeps pushing events into an unbounded queue, server memory still grows. In gRPC Java, the server can cast `StreamObserver` to `ServerCallStreamObserver` to observe write readiness:

~~~java
ServerCallStreamObserver<FeedEvent> out =
        (ServerCallStreamObserver<FeedEvent>) responses;

out.setOnCancelHandler(() -> {
    // Unsubscribe event source, cancel timers, release RPC resources.
    stopProducerForThisCall();
});

out.setOnReadyHandler(() -> {
    // Ask the sequential sender to resume draining the bounded buffer.
    scheduleDrainForThisCall();
});
~~~

In the snippet above, `responses` is the observer from the service method, while `stopProducerForThisCall` and `scheduleDrainForThisCall` are application-implemented methods. This is an API example, **not yet** a full backpressure implementation.

Inside a sequential sender, the logic typically looks like:

~~~text
while notCancelled and out.isReady() and boundedQueue.hasNext():
    out.onNext(boundedQueue.removeNext())

if producerFinished and boundedQueue.empty() and notCancelled:
    out.onCompleted()

if producerFailed and notCancelled:
    out.onError(mappedGrpcStatus)
~~~

Emitting, error reporting, and completion operations must be **serialized**; never allow a producer callback, an `onReady` handler, and an error handler to invoke the same observer concurrently. `ServerCallStreamObserver.isReady()` is a **write-path readiness hint**, not confirmation that the client has processed data. The `onReady` callback can fire multiple times; avoid busy loops, leaked jobs, or sending the same message twice.

| Location | API / signal | Interpretation |
|---|---|---|
| Client wants more responses | `ClientCallStreamObserver.request(n)` | Grants additional inbound receive demand to client observer |
| Client controls receive from start | `disableAutoRequestWithInitial(n)` in `beforeStart` | Disables auto-request and sets initial demand |
| Server wants to emit response | `ServerCallStreamObserver.isReady()` | Write path is ready to accept more data per runtime |
| Server waits for writability recovery | `setOnReadyHandler(...)` | Signal to try draining via coordinated scheduling |
| Server detects client cancellation | `setOnCancelHandler(...)` or `isCancelled()` | Clean up RPC resources |
| Transport | HTTP/2 flow control | Throttles byte/frame transmission, distinct from business message counts |

**Note on data direction:** on the client side, `ClientCallStreamObserver.isReady()` primarily concerns capacity to send **outbound requests**, not a signal of how many responses the client has processed. In **server streaming**, the initial application request is sent only once; use `request(n)` to control **inbound responses**.

### Policies when a client is too slow

- **Data must not be lost:** use a bounded queue with a producer capable of slowing down, or write the event source to durable storage supporting sequence-based replay. When demand cannot be met, close the RPC with an appropriate status and let the client resync per contract.
- **Continuously updated state:** coalesce multiple changes into the latest state if the client does not need every intermediate transition. Document this clearly in the API contract.
- **Best-effort telemetry or log streams:** apply rate limiting, sampling, or dropping stale entries according to a published policy.
- **Large client counts:** share upstream subscriptions where appropriate and limit concurrent streams, memory, and response rates per caller.

Never dedicate a thread calling `Thread.sleep` to wait per client in a system with many streams. Use managed schedulers/publishers/executors and clean up when the server/client terminates the RPC.

## 10. Interaction with deadlines, cancellation, and status

Backpressure can cause a client to take longer to consume all responses. A gRPC deadline **bounds the entire RPC**, not extended automatically after each message:

~~~text
0s          3s          6s        10s
|-- #1 proc --|-- #2 proc --|-- ... --X
                                       DEADLINE_EXCEEDED
~~~

When processing long streams, choose a deadline aligned with business goals or design multiple checkpointed sessions rather than arbitrarily setting infinite deadlines. For open-ended watch streams, establish cancellation, reconnection, and duration-monitoring policies.

Common outcomes:

| Outcome | Client observes | What server must do |
|---|---|---|
| All events received and completed | `onCompleted` or iterator ends normally | Emit `onCompleted` once; release subscription |
| Invalid request | `INVALID_ARGUMENT` | Return `onError` with appropriate status |
| Data source unavailable | `UNAVAILABLE` or suitable status | Stop producer, release buffers, report error |
| Client no longer needs stream | `CANCELLED` or cancellation-context termination | Stop sending and release RPC resources |
| Deadline expires | `DEADLINE_EXCEEDED` at client | Detect call cancellation, stop related work |
| Quota or buffer exceeded | `RESOURCE_EXHAUSTED` if API chooses this code | Shed load, return meaningful status, allow controlled retry |

With `ClientResponseObserver`, proactively cancel using `ClientCallStreamObserver.cancel(message, cause)` when the application no longer wishes to continue. Never call `onError` on your own receiving observer to cancel an RPC: the callback is merely a notification sink, whereas cancellation must be signaled to the runtime.

**Partial reception is different from RPC success.** The client may process sequences 1–3 and then receive `DEADLINE_EXCEEDED`. If the business operation cannot lose data, persist checkpoints **after successful processing** and support replay from the checkpoint. gRPC itself does not provide exactly-once event delivery or durable data storage.

## 11. Metadata, TLS, interceptors, and monitoring

In a Spring gRPC application, request metadata typically carries authentication credentials, correlation IDs, or **RPC-level** control parameters. Fields that vary per message—such as `sequence` and status—belong in the protobuf payload. Interceptors can enforce authentication, authorization, tracing, message/duration metrics, and final outcomes.

Long-lived streams make caller identity, quotas, and connection lifecycles especially important:

- Use **TLS** for real connections; `usePlaintext()` in the demo client is only appropriate for trusted dev environments. Verify server certificates, and use mTLS if system policy requires it.
- Enforce authorization per `topic`, and limit concurrent streams, payload sizes, and usage rates per caller.
- Never log access tokens or sensitive payloads.
- For time-limited tokens, establish a clear policy for streams running past token expiration.

Metrics that help detect backpressure:

| Metric | Meaning |
|---|---|
| Responses/sec produced and sent by server | Reveals producer and transport rate |
| Responses/sec **completed** by client | Shows real consumer throughput |
| In-flight response count and queue depth | Detects application backlog buildup |
| Buffer size at server and client | Warns of memory growth risk |
| Wait and processing time per message | Detects rising end-to-end latency |
| Count of server `isReady() == false` | Signals write path unready |
| Open RPC count, RPC duration | Forecasts service load capacity |
| `CANCELLED`, `DEADLINE_EXCEEDED`, `RESOURCE_EXHAUSTED` | Analyzes why streams terminate |
| Sequence gaps, duplicates, and checkpoints | Evaluates replay capability and data reliability |

Merely counting `onNext` calls on the server is insufficient to claim the client processed them. Business completion metrics must be measured right after client processing, or via a separate application-level acknowledgment mechanism.

## 12. Testing manual inbound flow control

Using `ClientResponseObserver` with `disableAutoRequestWithInitial(1)` lets you verify one concrete behavior: **until the client grants additional demand, subsequent `onNext` callbacks are not delivered**. This can be tested with gRPC **in-process transport**, exercising real protobufs, stubs, and services without opening network ports.

This JUnit 5 example uses the demo server from section 4:

~~~java
import com.example.feed.EventFeedServiceImpl;
import com.example.feed.rpc.EventFeedServiceGrpc;
import com.example.feed.rpc.FeedEvent;
import com.example.feed.rpc.WatchEventsRequest;
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.ClientCallStreamObserver;
import io.grpc.stub.ClientResponseObserver;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.*;

class ClientDemandTest {

    @Test
    void onlyDeliversFurtherMessagesWhenRequested() throws Exception {
        String name = InProcessServerBuilder.generateName();
        Server server = InProcessServerBuilder.forName(name)
                .directExecutor()
                .addService(new EventFeedServiceImpl())
                .build()
                .start();
        ManagedChannel channel = InProcessChannelBuilder.forName(name)
                .directExecutor()
                .build();

        try {
            AtomicReference<ClientCallStreamObserver<WatchEventsRequest>>
                    control = new AtomicReference<>();
            AtomicReference<Throwable> failure = new AtomicReference<>();
            List<Long> received = new ArrayList<>();
            CountDownLatch first = new CountDownLatch(1);
            CountDownLatch second = new CountDownLatch(1);
            CountDownLatch terminal = new CountDownLatch(1);

            WatchEventsRequest request = WatchEventsRequest.newBuilder()
                    .setTopic("stock")
                    .setMaxEvents(3)
                    .build();

            EventFeedServiceGrpc.newStub(channel)
                    .withDeadlineAfter(5, TimeUnit.SECONDS)
                    .watchEvents(
                            request,
                            new ClientResponseObserver<WatchEventsRequest,
                                                       FeedEvent>() {
                                @Override
                                public void beforeStart(
                                        ClientCallStreamObserver<
                                                WatchEventsRequest> stream) {
                                    control.set(stream);
                                    stream.disableAutoRequestWithInitial(1);
                                }

                                @Override
                                public void onNext(FeedEvent event) {
                                    received.add(event.getSequence());
                                    if (received.size() == 1) {
                                        first.countDown();
                                    }
                                    if (received.size() == 2) {
                                        second.countDown();
                                    }
                                    // Do not call request() automatically in the test.
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

            assertTrue(first.await(2, TimeUnit.SECONDS));
            assertEquals(List.of(1L), received);

            // Test explicitly permits delivery of exactly one more message.
            control.get().request(1);
            assertTrue(second.await(2, TimeUnit.SECONDS));
            assertEquals(List.of(1L, 2L), received);

            control.get().request(1);
            assertTrue(terminal.await(2, TimeUnit.SECONDS));
            assertNull(failure.get());
            assertEquals(List.of(1L, 2L, 3L), received);
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

**Test scope:** the test verifies demand-granting mechanics and callback ordering on the client. It does **not** prove the server generates only one message at a time, does not measure internal buffer sizes, and does not verify that a real producer system pauses when the client is slow. In environments running callbacks on a different executor, protect the collected message list with synchronization or only read it after an explicit happens-before relationship; production applications also need resource limits and cleanup on test timeouts.

Additional tests to include:

1. **No additional demand granted:** after the first event, wait a controlled short interval and verify no subsequent event callback fires; then grant demand to complete.
2. **Multi-message window:** configure initial demand of 2 or 8; measure in-flight responses and queue depth during async processing.
3. **Slow client:** process each event slower than the emission rate; observe memory, latency, readiness, and quotas on both sides.
4. **Mid-stream interruption:** cancel from client after one message; verify server releases subscription/producer.
5. **Deadline:** set a deadline shorter than total stream processing time; client sees `DEADLINE_EXCEEDED` and handles partial data per contract.
6. **Client processing error:** `applyEvent` fails; verify RPC is cancelled, no unbounded requesting occurs, and the error is surfaced to the caller.
7. **Replay:** disconnect after sequence 3 and resume from checkpoint; check for gaps/duplicates if the API supports replay.
8. **Spring integration:** verify service registration, metadata/interceptors, TLS, proxy timeouts, and stream limits in a realistic environment.

## 13. Common mistakes and how to fix them

| Mistake | Impact | How to fix |
|---|---|---|
| Receiving and enqueueing unboundedly in `onNext` | Slow consumer bloats queue | Use manual demand or bounded queue and grant demand only after processing |
| Calling `request(1)` **before** heavy processing finishes | Demand does not reflect consumer capacity | Move `request(1)` to completion time |
| Disabling auto-request but forgetting to request more | Stream stalls after a few messages | Grant demand per completed event and handle error paths clearly |
| Thinking client `request(1)` forces server to `onNext` only once | Server keeps generating and buffering data | Throttle producer, monitor readiness, and bound server buffers |
| Using `ClientCallStreamObserver.isReady()` to measure inbound responses | Reading the wrong data direction | For inbound, use `request(n)`; outbound readiness belongs to the sender side |
| Calling `onNext` concurrently from multiple server threads | Races and undefined ordering | One sequential sender per RPC |
| Dropping events whenever `isReady() == false` | Mandatory business events lost | Choose durable storage, bounded buffers, or apply a published data-loss policy |
| Skipping cleanup when client cancels | Leaked timers, cursors, and subscriptions | Use a cancel handler, stop producer, and release buffers |
| Treating received messages as full RPC success | Wrong when an error occurs mid-stream | Wait for `onCompleted` or `OK` status and manage checkpoints |

### Self-check questions

1. If the client reads 100 messages/sec while the server produces 1,000 messages/sec, what happens if the application uses an unbounded queue?
2. Is `ClientCallStreamObserver.request(1)` an additional protobuf request sent to the server or a demand to receive one more response?
3. Why is `disableAutoRequestWithInitial(1)` insufficient to guarantee the server will not grow in memory?
4. In an application using a thread pool to process `FeedEvent`, when should the next `request(1)` be called?
5. How does `ServerCallStreamObserver.isReady()` differ from the client having finished processing a message?
6. Why can a client have already received several messages and still observe `DEADLINE_EXCEEDED`?
7. When mandatory events must not be lost, what is needed in addition to backpressure?

**Key takeaway:** A server streaming client can **read and process messages incrementally** using `Iterator` or `StreamObserver`. When you need to control the rate of response delivery to application code, `ClientResponseObserver` with `disableAutoRequestWithInitial(n)` and `request(n)` ties receive demand to processing capacity. Reliable backpressure requires **end-to-end** management: client processing, bounded queues, transport flow control, server producers, cancellation, deadlines, status handling, TLS, testing, and monitoring.
