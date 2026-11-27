# Response ordering within a stream

## 1. Why response ordering matters

In the **SPRING_GRPC** module, we build gRPC services in the Spring ecosystem from Protocol Buffers contracts, generate Java code, and implement clients/servers for unary or streaming RPCs. In the **Server streaming** chapter, the client sends **one request** and receives **multiple responses** on the same RPC call. A core property of this communication pattern is that **the order of messages within that stream is preserved**.

Suppose a service sends data import progress updates. The client receives:

~~~text
Response 1: File read
Response 2: Data validated
Response 3: Database written
Response 4: Completed
~~~

If response 3 arrives before response 2, the UI or receiving system could display incorrect progress. Server streaming lets the client receive messages sequentially **in the exact order they were validly sent into the same RPC**. However, gRPC does not guess the business ordering the application intends: when multiple processing sources run in parallel, the server must design how to order results before sending.

Lesson goals:

- Distinguish **send order**, **receive order**, **data generation order**, and **business processing completion order**.
- Understand the exact scope of gRPC's ordering guarantees.
- Build a Spring gRPC server streaming example with explicit sequence numbers.
- Avoid race conditions when multiple threads produce responses concurrently.
- Verify ordering, disconnects, cancellation, and duplicate handling through tests.

## 2. What does gRPC guarantee within a stream?

In a server streaming RPC, each server call to `onNext(response)` produces a distinct gRPC message. When calls are made **sequentially, in strict order**, the client observes the received messages in that same order within that RPC.

~~~mermaid
sequenceDiagram
    participant S as Spring gRPC server
    participant T as RPC HTTP/2 stream
    participant C as Java client
    S->>T: onNext(A)
    S->>T: onNext(B)
    S->>T: onNext(C)
    T-->>C: onNext(A)
    T-->>C: onNext(B)
    T-->>C: onNext(C)
    S->>T: onCompleted()
    T-->>C: onCompleted() / status OK
~~~

Each Protocol Buffers message is framed by gRPC over HTTP/2. Bytes/frames are transmitted using HTTP/2 and gRPC mechanisms so the client reconstructs messages in order within **one stream**. Splitting a large message across multiple frames does not turn it into multiple responses at the application layer.

| Statement | True or false? | Explanation |
|---|---|---|
| Within one RPC, messages sent sequentially are received by the client in that order. | **True** | This is gRPC's per-stream ordering guarantee. |
| gRPC automatically sorts responses by the time workers produced the data. | **False** | The application decides the order in which `onNext` is called. |
| Two different RPCs always share a consistent global order. | **False** | Streams are independent; network speed, schedulers, and processing may differ. |
| If the client receives message 4, the server definitely sent messages 1–3 beforehand on that same valid RPC. | **True** | For a stream where the server sequentially sends messages 1–4 in order. |
| Once the server calls `onNext`, the message has definitely arrived and been persisted by the client. | **False** | `onNext` is neither business processing acknowledgment nor client-side durability. |
| If the RPC ends in an error, the client is guaranteed to receive all emitted messages. | **False** | Trailing data may not arrive; the RPC did not complete successfully. |
| gRPC guarantees the client processes background work results in order. | **False** | The client can offload processing to other threads and alter business completion order. |

**Important scope:** Ordering is guaranteed **within each individual RPC**. There is no automatic global ordering across RPCs, across multiple services, or across reconnects after a failure.

## 3. Four easily confused ordering concepts

### 3.1. Result generation order

This is the time when a producer, async task, or event source creates data. For example, worker A starts processing record #1 first, but worker B finishes record #2 faster:

~~~text
09:00:00  Worker A starts processing record 1
09:00:01  Worker B starts processing record 2
09:00:02  Worker B finishes producing result 2
09:00:05  Worker A finishes producing result 1
~~~

If the server emits immediately as each worker finishes, the client receives **2 then 1**. This is neither a network bug nor a gRPC bug. The send order simply reflected the workers' completion order.

### 3.2. Stream send order

This is the order in which `StreamObserver.onNext(...)` calls are executed sequentially. The server is responsible for determining and protecting this order. With a single sequential producer, preserving it is trivial; with multiple producers, results must be merged according to business rules.

### 3.3. Client message receive order

When the server sends validly on the same RPC, the client receives responses **in send order**. An async client receives them sequentially via the `onNext` callback; a blocking client can iterate over responses via an `Iterator`.

This applies only to messages actually received. If the connection drops, gRPC does not turn a failed stream into a complete, auto-recoverable list.

### 3.4. Client processing completion order

Suppose the client receives A, B, C in order and dispatches each item to a thread pool. A takes 500 ms, B takes 50 ms, and C takes 100 ms. Processing may finish in the order **B, C, A**. gRPC does not control async logic after the callback.

To apply changes in order, the client must process sequentially or track sequence/checkpoints when processing runs in parallel.

~~~mermaid
flowchart LR
    A["Producer A: result #1"] --> M["Business ordering unit"]
    B["Producer B: result #2"] --> M
    C["Producer C: result #3"] --> M
    M --> S["Single sequential sender"]
    S --> G["gRPC stream: #1 → #2 → #3"]
    G --> R["Client receives: #1 → #2 → #3"]
    R --> P["Process / persist per client policy"]
~~~

## 4. Declaring a Protocol Buffers contract with sequence numbers

To observe ordering in logs, tests, and post-disconnect resumption, we add a `sequence` field to each response. Suppose an application tracks the processing steps of an order:

~~~proto
syntax = "proto3";

package order.v1;

option java_multiple_files = true;
option java_package = "com.example.order.rpc";
option java_outer_classname = "OrderProto";

service OrderProgressService {
  rpc WatchOrder(WatchOrderRequest) returns (stream OrderUpdate);
}

message WatchOrderRequest {
  string order_id = 1;
}

enum OrderPhase {
  ORDER_PHASE_UNSPECIFIED = 0;
  ACCEPTED = 1;
  PAID = 2;
  PACKED = 3;
  SHIPPED = 4;
}

message OrderUpdate {
  string order_id = 1;
  int64 sequence = 2;
  OrderPhase phase = 3;
  int64 created_at_epoch_ms = 4;
}
~~~

In the `WatchOrder` method, the `stream` keyword on the **response** type defines server streaming. `protoc` and the `protoc-gen-grpc-java` plugin generate message classes and gRPC Java classes such as `OrderUpdate`, `WatchOrderRequest`, and `OrderProgressServiceGrpc`.

The `sequence` field serves to:

1. Represent **business** order that the client can inspect, not merely network arrival order.
2. Allow the client to detect duplicate or missing responses in the event stream **according to the application contract**.
3. Serve as the foundation for checkpoint/replay **if** the server stores history and exposes a resume API.
4. Aid logging and tracing during incident investigations.

**Do not misunderstand:** having `sequence` does not automatically sort messages, add retries, or guarantee exactly-once delivery. In the example, `sequence` is a monotonically increasing number per order, and the server must enforce that rule.

## 5. Spring gRPC server sending responses in order

The following example intentionally emits from a single sequential call flow to demonstrate the exact `onNext` → client ordering relationship. This is simulated data, not a real payment workflow.

~~~java
package com.example.order;

import com.example.order.rpc.OrderPhase;
import com.example.order.rpc.OrderProgressServiceGrpc;
import com.example.order.rpc.OrderUpdate;
import com.example.order.rpc.WatchOrderRequest;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class OrderProgressServiceImpl
        extends OrderProgressServiceGrpc.OrderProgressServiceImplBase {

    @Override
    public void watchOrder(
            WatchOrderRequest request,
            StreamObserver<OrderUpdate> responses) {

        String orderId = request.getOrderId().trim();
        if (orderId.isEmpty()) {
            responses.onError(Status.INVALID_ARGUMENT
                    .withDescription("order_id must not be blank")
                    .asRuntimeException());
            return;
        }

        List<OrderPhase> phases = List.of(
                OrderPhase.ACCEPTED,
                OrderPhase.PAID,
                OrderPhase.PACKED,
                OrderPhase.SHIPPED);

        for (int index = 0; index < phases.size(); index++) {
            OrderUpdate response = OrderUpdate.newBuilder()
                    .setOrderId(orderId)
                    .setSequence(index + 1L)
                    .setPhase(phases.get(index))
                    .setCreatedAtEpochMs(System.currentTimeMillis())
                    .build();

            responses.onNext(response);
        }

        responses.onCompleted();
    }
}
~~~

Expected output for `order_id = "ORD-101"`:

~~~text
sequence=1, phase=ACCEPTED
sequence=2, phase=PAID
sequence=3, phase=PACKED
sequence=4, phase=SHIPPED
gRPC status: OK
~~~

The code above calls `onNext` in a fixed order within a loop. `onCompleted` is called only after all four messages have been emitted. If the request is invalid, `onError(INVALID_ARGUMENT)` terminates the RPC and the server emits nothing further.

With updates from a real system, the four statuses might occur minutes or hours apart. **Do not** keep an RPC thread busy-waiting with `Thread.sleep` between states. Instead, subscribe to an asynchronous data source, have a sequential sender emit messages when events occur, and unsubscribe when the RPC closes.

Depending on the Spring gRPC version/integration library, a `@Service` bean may be auto-discovered as a `BindableService` or require a corresponding registration mechanism. The ordering rules of `StreamObserver` belong to the gRPC Java API and do not change with how beans are registered.

## 6. Java client verifying received order

A client using the **blocking stub** can iterate over `Iterator<OrderUpdate>` in response order:

~~~java
import com.example.order.rpc.OrderProgressServiceGrpc;
import com.example.order.rpc.OrderUpdate;
import com.example.order.rpc.WatchOrderRequest;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.StatusRuntimeException;

import java.util.Iterator;
import java.util.concurrent.TimeUnit;

public class OrderProgressClient {
    public static void main(String[] args) {
        ManagedChannel channel = ManagedChannelBuilder
                .forAddress("localhost", 9090)
                .usePlaintext() // Use only for dev examples / trusted environments.
                .build();

        try {
            WatchOrderRequest request = WatchOrderRequest.newBuilder()
                    .setOrderId("ORD-101")
                    .build();

            Iterator<OrderUpdate> stream = OrderProgressServiceGrpc
                    .newBlockingStub(channel)
                    .withDeadlineAfter(10, TimeUnit.SECONDS)
                    .watchOrder(request);

            long expectedSequence = 1;
            while (stream.hasNext()) {
                OrderUpdate update = stream.next();

                if (update.getSequence() != expectedSequence) {
                    throw new IllegalStateException(
                            "Expected sequence " + expectedSequence
                            + " but received " + update.getSequence());
                }

                System.out.println(
                        update.getSequence() + ": " + update.getPhase());
                expectedSequence++;
            }
        } catch (StatusRuntimeException error) {
            System.err.println("RPC failed: " + error.getStatus());
        } finally {
            channel.shutdownNow();
        }
    }
}
~~~

`expectedSequence` verifies the example's **business contract**: responses must have sequences 1, 2, 3, 4. If the server sends 1, 3, 2, gRPC will still faithfully deliver **1, 3, 2** in the order `onNext` was called, while the client detects that the business order is wrong.

Port 9090 is an example; match your project's gRPC server configuration. In a Spring application, reuse a container-managed channel and configure **TLS** for production environments.

### Async stub also receives in stream order

An async client receives each message via `StreamObserver.onNext`:

~~~java
WatchOrderRequest request = WatchOrderRequest.newBuilder()
        .setOrderId("ORD-101")
        .build();

OrderProgressServiceGrpc.newStub(channel)
        .withDeadlineAfter(10, TimeUnit.SECONDS)
        .watchOrder(request, new StreamObserver<OrderUpdate>() {
            private long expected = 1;

            @Override
            public void onNext(OrderUpdate update) {
                if (update.getSequence() != expected) {
                    System.err.println("Unexpected sequence: " + update.getSequence());
                }
                expected = update.getSequence() + 1;
                processInOrder(update);
            }

            @Override
            public void onError(Throwable error) {
                System.err.println(Status.fromThrowable(error));
            }

            @Override
            public void onCompleted() {
                System.out.println("Stream completed");
            }
        });
~~~

The async snippet assumes `channel`, `processInOrder(update)`, and corresponding imports already exist. `processInOrder` is an illustrative application function; if it offloads work to a thread pool, **completion** of those offloaded tasks may get reordered. When state must be applied sequentially, use an ordered processing queue or coordinate by sequence.

Do not manually call `onError` or `onCompleted` on the client's receiving observer to control server ordering. Those are RPC output callbacks on the client.

## 7. Concurrent data sources: gRPC does not auto-sort by sequence

This is the most common mistake when implementing server streaming. Suppose the server analyzes three parts of a report simultaneously:

~~~text
Producer 1: creates message #1 after 300 ms
Producer 2: creates message #2 after 100 ms
Producer 3: creates message #3 after 200 ms

If sent immediately upon completion: #2 → #3 → #1
~~~

The client will receive `#2, #3, #1` if the server emits them sequentially in that order. **gRPC preserved the send order, but the business order is wrong.**

Furthermore, never let multiple workers directly call `responseObserver.onNext(...)` concurrently. `StreamObserver` is not thread-safe by default for concurrent write calls; ordering between concurrent calls is also not determined by sequence numbers inside the payload.

### 7.1. Designing a sequential sender

Separate **data generation** from **RPC emission**:

~~~mermaid
flowchart TD
    A["Worker A produces event #1"] --> Q["Bounded buffer / reorder buffer"]
    B["Worker B produces event #2"] --> Q
    C["Worker C produces event #3"] --> Q
    Q --> R{"Have nextExpected yet?"}
    R -- "Not yet" --> W["Hold or wait, apply timeout/error policy"]
    W --> R
    R -- "Yes" --> S["Single sender: onNext(nextExpected)"]
    S --> I["Increment nextExpected; check next item"]
    I --> R
    S --> G["gRPC stream"]
    G --> H["Client: #1, #2, #3"]
~~~

One implementation approach:

1. **Assign sequence numbers** according to business rules before executing parallel work (e.g., row order in an `ORDER BY` query).
2. As workers finish, submit `(sequence, result)` to an aggregator; do not call the observer directly.
3. The aggregator holds early-arriving results in a **bounded** buffer.
4. A single sender emits only the element with `sequence == nextExpected` and then increments `nextExpected`.
5. Once all required items are confirmed complete, the sender calls `onCompleted()`. If a mandatory item cannot be retrieved, apply a timeout/retry policy or terminate with `onError(...)`.
6. When the client cancels, stop producers, unsubscribe, and release buffers.

Pseudocode example:

~~~text
nextExpected = 1
pending = bounded_map()

onWorkerResult(sequence, event):
    enqueueIntoSingleSender(() -> {
        pending.put(sequence, event)
        while pending.contains(nextExpected) and transportCanAcceptMore():
            responseObserver.onNext(pending.remove(nextExpected))
            nextExpected += 1
    })

onAllWorkersFinished():
    enqueueIntoSingleSender(() -> {
        if pending.isEmpty() and nextExpected == totalExpected + 1:
            responseObserver.onCompleted()
        else:
            waitOrFailAccordingToPolicy()
    })

onCancellation():
    stopProducers()
    stopSenderAndReleaseBuffers()
~~~

This is **architectural pseudocode**, not Java to copy verbatim. In gRPC Java, `transportCanAcceptMore()` can be based on `ServerCallStreamObserver.isReady()` and the `setOnReadyHandler` callback; both ready events and worker results must be coordinated on the sequential sender. Producers must face backpressure or have a storage/replay mechanism when the buffer hits its limit. Never spin in a busy-wait loop, and never drop critical updates merely because `isReady()` is currently false.

### 7.2. When is sending in completion order acceptable?

Not every stream requires sequence 1, 2, 3 to mirror initialization order. For **independent results**, sending in task completion order can be valid business behavior and reduce latency:

~~~text
SearchResults(request) → result B → result A → result C
~~~

In that case, the contract should explicitly state that results have **no fixed business order**. gRPC still preserves the order of emitted messages, but the client must not implicitly assume result A must precede result B. If the client requires ordering by score, event timestamp, or ID, the server must sort according to that criterion itself.

## 8. How do HTTP/2, flow control, and deadlines interact?

### 8.1. HTTP/2 can interleave streams, but never reorders messages within one RPC

A single HTTP/2 connection can carry multiple independent streams:

~~~text
RPC A: A1 -------- A2 ------ A3
RPC B: ---- B1 -------- B2

Transmission at a given moment may interleave A1, B1, A2, B2, A3.
Internal order of RPC A remains A1, A2, A3.
Internal order of RPC B remains B1, B2.
There is no guarantee A2 arrives before B2 or vice versa.
~~~

Inter-RPC concurrency is a benefit of HTTP/2 multiplexing. It does not provide cross-RPC ordering for the application. If business logic must coordinate across multiple streams, you need logical timestamps, a global sequence, or an explicit merge protocol.

### 8.2. Flow control affects speed, not order

If a client reads slowly, gRPC/HTTP/2 can throttle the send rate. Message #2 will not overtake message #1 within the same stream because of that; however, latency and pending queued messages can increase.

`ServerCallStreamObserver.isReady()` reports write-path readiness under flow control; it is **not** confirmation that the client has processed the message. For long-lived streams, bound buffers, combine `setOnReadyHandler` or a backpressure-aware publisher, and establish a transparent data-loss/recovery policy.

### 8.3. Deadlines or cancellation can stop a stream mid-way

Suppose the server intends to emit 1, 2, 3, 4, but the client cancels after 2:

~~~text
Server intended: 1 → 2 → 3 → 4 → onCompleted()
Client sees:     1 → 2 → CANCELLED (or termination matching actual cause)
~~~

Ordering is preserved for responses **actually received**, but there is no promise of receiving all four responses. Deadlines apply to the **entire RPC**, not refreshed after each message. The server must stop producers/subscriptions when the call is cancelled or the deadline expires, via gRPC Java's cancellation signals.

### 8.4. onError and onCompleted are distinct outcomes

A server can emit multiple `onNext` calls and then terminate with:

- `onCompleted()`: no more messages, RPC completed successfully.
- `onError(Status...asRuntimeException())`: RPC failed; the client must handle the status and not treat earlier responses as proof of overall RPC success.

Never call `onNext` after a terminal callback, never call both `onError` and `onCompleted`, and serialize these calls alongside message emission operations. On the client side, the `onError` callback may fire after the client has already received some messages, while in-flight messages may never be delivered.

## 9. Ordering after reconnect: requires a business contract

When an old RPC terminates due to a network error and a new RPC is started, they are **two independent streams**. gRPC does not guarantee the new stream automatically resumes from the missing response of the previous stream. In particular, the client having seen `sequence = 7` is not enough to infer that every update was processed and durably saved.

A resumable contract can add a cursor:

~~~proto
message WatchOrderRequest {
  string order_id = 1;
  int64 after_sequence = 2;
}
~~~

When the client reconnects with `after_sequence = 7`, the server must be able to read history **after** sequence 7 and transition to live events without creating gaps. This requires a durable event store, sequence assignment rules, retention limits, and consistent snapshot/subscribe operations.

The client needs to:

1. Record a checkpoint only after successfully processing the event.
2. Skip duplicate events during replay if the record was already processed.
3. Detect gaps—for instance expecting 8 but receiving 10—and request resynchronization per contract.
4. Never treat the entire dataset as complete until receiving the proper termination signal.

Verification example:

~~~java
// Inside the message-receiving callback, using a sequential processing executor.
long receivedSequence = update.getSequence();
if (receivedSequence <= lastAppliedSequence) {
    return; // Duplicate record after retry/replay.
}
if (receivedSequence != lastAppliedSequence + 1) {
    throw new IllegalStateException("Missing event before " + receivedSequence);
}

applyEvent(update); // Update checkpoint only after successful processing.
lastAppliedSequence = receivedSequence;
~~~

The snippet above is illustrative, assuming `update`, `lastAppliedSequence`, and `applyEvent` are already defined; in a real application, state updates and checkpoint persistence should be coordinated consistently, such as within a single transaction when stored together. Throwing an exception from a client callback **does not replace** an RPC cancellation/resync policy; production code must handle application errors and cancel/open new calls in a controlled manner.

## 10. Metadata, TLS, and observing ordering

In the Spring gRPC ecosystem, metadata/interceptors are commonly used for authentication, authorization, correlation IDs, and tracing. For ordered streams, include `order_id` and `sequence` in the payload or appropriate observability fields to diagnose gaps/duplicates; metadata is RPC-level information, not a place to update per-message sequences.

On real networks, use TLS to protect the transport; authorize access to `order_id` before opening the stream and control stream counts per caller. If logs or traces record event sequences, avoid exposing sensitive payloads or access tokens.

Metrics that help diagnose ordering issues:

| Metric | Operational value |
|---|---|
| `messages_sent` and `messages_received` | Measure throughput; comparisons must be scoped to the same RPC and account for collection limits. |
| `last_sequence` / `expected_sequence` | Detect gaps, duplicates, or business ordering violations. |
| Reorder buffer size | Detect producers arriving at uneven speeds and memory growth risks. |
| Wait time for `nextExpected` | Detect slow workers or missing events. |
| `isReady()` / queue depth | Evaluate backpressure and slow-consuming clients. |
| `CANCELLED`, `DEADLINE_EXCEEDED`, `UNAVAILABLE` | Distinguish why streams stopped. |
| Time from data generation to client application | Measure timeliness of business ordering. |

Because logs from multiple threads and hosts do not necessarily appear in actual occurrence order, rely on sequence/correlation IDs rather than comparing two log timestamps and concluding gRPC reordered messages.

## 11. Testing ordering on gRPC transport

You can verify the event sequence using **gRPC in-process transport**: exercising the real service class, Java serialization/stubs, and gRPC statuses without opening network ports. JUnit 5 example for the service in section 5:

~~~java
import com.example.order.OrderProgressServiceImpl;
import com.example.order.rpc.OrderPhase;
import com.example.order.rpc.OrderProgressServiceGrpc;
import com.example.order.rpc.OrderUpdate;
import com.example.order.rpc.WatchOrderRequest;
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class OrderProgressServiceTest {

    @Test
    void responsesKeepServiceSendOrder() throws Exception {
        String serverName = InProcessServerBuilder.generateName();
        Server server = InProcessServerBuilder.forName(serverName)
                .directExecutor()
                .addService(new OrderProgressServiceImpl())
                .build()
                .start();
        ManagedChannel channel = InProcessChannelBuilder.forName(serverName)
                .directExecutor()
                .build();

        try {
            var stub = OrderProgressServiceGrpc.newBlockingStub(channel)
                    .withDeadlineAfter(5, TimeUnit.SECONDS);
            var request = WatchOrderRequest.newBuilder()
                    .setOrderId("ORD-101")
                    .build();

            List<OrderUpdate> events = new ArrayList<>();
            stub.watchOrder(request).forEachRemaining(events::add);

            assertEquals(List.of(1L, 2L, 3L, 4L),
                    events.stream().map(OrderUpdate::getSequence).toList());
            assertEquals(List.of(
                    OrderPhase.ACCEPTED,
                    OrderPhase.PAID,
                    OrderPhase.PACKED,
                    OrderPhase.SHIPPED),
                    events.stream().map(OrderUpdate::getPhase).toList());

            var invalid = WatchOrderRequest.newBuilder()
                    .setOrderId(" ")
                    .build();
            StatusRuntimeException error = assertThrows(
                    StatusRuntimeException.class,
                    () -> stub.watchOrder(invalid).hasNext());
            assertEquals(Status.Code.INVALID_ARGUMENT,
                    error.getStatus().getCode());
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

This test verifies the **order of responses sent by the service** and the `INVALID_ARGUMENT` error branch. It does not prove the system can properly merge messages from multiple real producers or maintain ordering across distinct streams. Those scenarios require application-level tests and Spring integration tests.

A more comprehensive test suite should include:

1. **Sequential emission:** 1, 2, 3, 4 arrive at the client in the same order, stream completes `OK`.
2. **Concurrent sources:** worker #2 finishes before #1 yet the client still receives 1, 2 when the contract requires ID order.
3. **Missing element:** never call `onCompleted` successfully if the contract requires complete data and event #3 is missing.
4. **Slow client:** producer does not let buffers grow unboundedly; once the client catches up, order is still preserved.
5. **Cancellation/deadline:** mid-stream interruption; stop sender/workers, release queues, and emit no duplicate terminal signals.
6. **Retry/reconnect:** replay some messages; client deduplicates and resumes from checkpoint per contract.
7. **Multiple concurrent RPCs:** do not mistakenly enforce global ordering across two independent streams.
8. **Spring integration:** verify service registration, interceptors, TLS, and proxy configuration in a realistic environment.

## 12. Common design mistakes

| Mistake | Why it happens | How to fix |
|---|---|---|
| Confusing worker completion order with business order | Producers run in parallel and emit immediately | Assign explicit sequences, use a reorder buffer and sequential sender. |
| Multiple threads calling `onNext` concurrently | Observer is shared across workers | Serialize all write calls for an RPC. |
| Client processes in parallel and persists state out of order | Callbacks arrive in order but tasks finish at different speeds | Use an ordered processing queue or sequence-based transactions/checkpoints. |
| Assuming two RPCs share a common order | HTTP/2 multiplexes independent streams | Design a global sequence if business logic truly requires it. |
| Treating `onNext` as confirmation that data was saved | Send API is not a business ACK | Design explicit acknowledgments/checkpoints as needed. |
| Waiting indefinitely for a missing element | Reorder buffer has no timeout or quota | Bound queue size, add timeouts and error/replay policies. |
| Completing successfully after skipping a mandatory event | Not validating sequence completeness before `onCompleted` | Verify all required elements per contract before terminal callback. |
| Not handling cancellation when client disconnects | Producers keep running and holding resources | Register a cancel handler and clean up along the RPC lifecycle. |

### Self-check questions

1. Server emits `onNext(B)` then `onNext(A)`; will gRPC automatically reorder them to A then B because A's timestamp is smaller?
2. Client receives A, B, C in order and processes them in a thread pool. Is it guaranteed to finish writing A before B?
3. Why do multiple RPCs running over the same HTTP/2 connection lack a global order?
4. What problem does `sequence` in protobuf solve, and what does it **not** solve on its own?
5. If worker #4 finishes before worker #3, what must the server do if required to send in order 1, 2, 3, 4?
6. When the connection drops after message #7, what conditions enable a new RPC to safely resume from #8?

**Key takeaway:** gRPC preserves the order of **messages sent sequentially within the same stream**. The server must still establish business ordering before calling `onNext`, serialize writes from multiple threads, manage backpressure, and handle errors/cancellations. The client receives messages in transport order but must protect its own processing order and data recovery when an RPC is interrupted.
