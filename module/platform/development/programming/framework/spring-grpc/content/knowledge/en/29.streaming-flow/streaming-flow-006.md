# Buffering in Stream Observers

## Learning Objectives

After this lesson, you will be able to:

- Explain that **StreamObserver** is a callback contract and identify which layers actually hold pending data.
- Distinguish inbound buffering, outbound buffering, gRPC transport buffers, and HTTP/2 flow-control buffers.
- Design application queues bounded by both message count and byte capacity.
- Throttle inbound via manual flow control and **request(n)**; throttle outbound via **isReady()**/**setOnReadyHandler()**.
- Serialize observer calls and handle terminal events, cancellation, and queue overflow.
- Choose an appropriate buffering or batching strategy for streaming RPCs in Spring gRPC.

## 1. StreamObserver Is Not a Message Queue

In gRPC Java, **StreamObserver<T>** is a callback interface with three core signals:

- **onNext(T)**: delivers a message to the observer.
- **onError(Throwable)**: terminates the stream with an error.
- **onCompleted()**: terminates the stream successfully.

This interface does not provide capacity, does not define a bounded application queue, and does not guarantee that calling `onNext()` means the message has already been sent over the network or processed by the peer.

In **SPRING_GRPC**, Spring Boot may manage server lifecycle and service registration, but buffering semantics still come from gRPC Java, the HTTP/2 transport, and application logic. To control memory, you must clearly identify which layer is holding messages and who is responsible for stopping the producer.

## 2. Layers That Can Hold Messages

A streaming RPC typically has multiple buffer zones:

1. **Application inbound queue**: messages received by callbacks and held by the application for workers to process.
2. **Application outbound queue**: responses generated but not yet passed to the observer.
3. **gRPC internal buffers**: messages already passed via `onNext()` but not yet completely written by the transport.
4. **HTTP/2 and socket buffers**: bytes waiting to be transmitted or waiting to be read by the peer.
5. **Receiver-side queues**: messages received but not yet processed by the peer application.

~~~mermaid
flowchart LR
  P["Producer"] --> OQ["App outbound queue"]
  OQ --> G["gRPC observer / transport buffer"]
  G --> H["HTTP/2 and socket buffers"]
  H --> I["Peer inbound callback"]
  I --> IQ["Peer application queue"]
  IQ --> W["Consumer worker"]
~~~

These buffers can coexist. For instance, if the application drains the entire outbound queue into the observer without checking readiness, data moves from the application queue into gRPC's internal buffers. The application queue looks empty, yet total memory holding messages remains high.

Therefore, you must control handoff points between layers rather than observing only the size of a single queue.

## 3. Inbound Buffering: Messages Entering the Application

On the server, inbound typically means request messages from the client. On the client, inbound typically means response messages from the server. When the `onNext()` callback is invoked, gRPC has delivered a parsed message up to the application layer.

If the callback performs quick validation and puts the message into a queue for a worker to process, that queue becomes the application's inbound buffer:

~~~java
BlockingQueue<UploadChunk> inbound =
    new ArrayBlockingQueue<>(32);

void onChunk(UploadChunk chunk) {
    if (!inbound.offer(chunk)) {
        rejectCall(Status.RESOURCE_EXHAUSTED
            .withDescription("Inbound buffer is full"));
        return;
    }
    scheduleConsumer();
}
~~~

**offer()** allows detecting a full queue without blocking the callback indefinitely. Avoid calling **put()** for long periods on gRPC callback threads; blocking the message-receiving executor can impact other RPCs.

A queue bounded only by message count is insufficient when payloads vary widely in size. Combine element limits with byte budgets, maximum message sizes, and active worker counts.

## 4. Throttling Inbound with Manual Flow Control

If the application receives messages faster than workers process them, the queue can fill up. With streaming, you can tie the number of messages permitted to arrive to real capacity using manual inbound flow control.

On the server, **ServerCallStreamObserver** lets you disable auto-request and request more messages when the application is ready:

~~~java
ServerCallStreamObserver<UploadResult> call =
    (ServerCallStreamObserver<UploadResult>) responseObserver;

call.disableAutoRequest();
call.request(1);
~~~

Only after a worker finishes processing the current chunk and frees a slot does the application call **call.request(1)** to allow the next message to be delivered. With multiple workers, account for both messages in the queue and messages currently being processed.

On the client, **ClientResponseObserver.beforeStart(...)** provides **ClientCallStreamObserver** to throttle inbound responses:

~~~java
ClientResponseObserver<SubscribeRequest, PriceUpdate> observer =
    new ClientResponseObserver<>() {
        private ClientCallStreamObserver<SubscribeRequest> call;

        @Override
        public void beforeStart(
                ClientCallStreamObserver<SubscribeRequest> requestStream) {
            call = requestStream;
            requestStream.disableAutoRequestWithInitial(1);
        }

        @Override
        public void onNext(PriceUpdate update) {
            consumerExecutor.execute(() -> {
                process(update);
                call.request(1);
            });
        }

        @Override
        public void onError(Throwable error) {
            handleFailure(error);
        }

        @Override
        public void onCompleted() {
            finishConsumption();
        }
    };
~~~

This example demonstrates demanding one message at a time. In production code, synchronize `request` calls with the call's state, handle executor errors, and stop requesting after cancellation/terminal events.

**request(n)** controls the number of inbound messages delivered to the observer. It does not directly increase the HTTP/2 byte window; the transport still manages byte-based flow control on its own.

## 5. Outbound Buffering: Messages Leaving the Application

On the server, outbound typically means responses; on the client, outbound typically means requests. When a producer generates responses faster than they can be sent, the application can hold them in a queue:

~~~java
BlockingQueue<PriceUpdate> outbound =
    new ArrayBlockingQueue<>(128);
~~~

Producers only enqueue; a single writer transfers messages to the observer. With **ServerCallStreamObserver**, the writer checks readiness:

~~~java
ServerCallStreamObserver<PriceUpdate> call =
    (ServerCallStreamObserver<PriceUpdate>) responseObserver;

call.setOnReadyHandler(this::scheduleDrain);
~~~

**isReady()** indicates whether gRPC can currently accept more outbound messages according to the implementation's readiness threshold. If it returns false, pause draining and leave remaining messages in the application queue. When readiness returns, the callback wakes up the writer.

Client streaming requests can likewise use **ClientCallStreamObserver.isReady()** and **setOnReadyHandler()** to throttle sending request messages.

## 6. Draining Queues Without Creating Unbounded Extra Buffers

A simple drain:

~~~java
void drain() {
    while (!cancelled.get() && call.isReady()) {
        PriceUpdate next = outbound.poll();
        if (next == null) {
            break;
        }
        call.onNext(next);
    }
}
~~~

This code needs to be called when the producer enqueues a message and when the on-ready callback indicates sending can continue. In a real implementation:

- Use a sequential executor or a single-writer mechanism per observer.
- Do not let multiple threads drain the queue and call `onNext()` concurrently.
- Do not use a busy loop to wait for `isReady()` to become true.
- Handle the race between when a drain finishes and when a producer enqueues a new message by re-checking the queue/readiness upon yielding.
- Serialize `onNext()`, `onError()`, and `onCompleted()` on the same sending path.

Returning from **onNext()** does not mean the peer has received or processed the message. If business logic requires confirmation, define an ACK in the application-layer protocol.

## 7. Bounding Buffers by Message Count and Bytes

Bounding a queue solely by count can lead to surprises. A queue of 100 messages with 1 KiB payloads is vastly different from a queue of 100 messages with 5 MiB payloads.

Set these simultaneously:

| Limit | Meaning |
| --- | --- |
| **Message capacity** | Maximum number of messages in the queue. |
| **Queued byte budget** | Maximum total serialized bytes pending. |
| **Single-message limit** | Maximum size of a single message. |
| **In-flight work** | Number of messages workers are processing concurrently. |
| **Per-RPC quota** | Total data or message count over the lifetime of one RPC. |
| **Global quota** | Shared buffer budget across the entire service. |

With Protobuf Java messages, **getSerializedSize()** is useful for estimating the byte budget. This size does not include all object overhead, references, queue nodes, or temporary copies during serialization.

When enqueueing, update both the message count and byte count atomically. When dequeueing or finishing processing, release the exact corresponding quota. If multiple producers enqueue concurrently, use a lock or reservation mechanism so races do not exceed the budget.

## 8. Full Queue and Overflow Policies

A full queue means producer speed has exceeded consumer capacity over that interval. The application must choose a policy suited to its semantics:

- **Pause/backpressure**: pause the producer or stop requesting inbound messages; preferred when all data must be preserved.
- **Reject**: terminate the RPC with **RESOURCE_EXHAUSTED** when no more data can be accepted.
- **Drop newest**: discard new messages if newer data is less important than pending data.
- **Drop oldest**: keep only the latest state, suitable for certain snapshot/telemetry streams.
- **Persist**: write to durable storage with a quota if longer-term load absorption is needed.

Do not arbitrarily drop messages for business commands, payments, or auditable data. For best-effort telemetry, dropping may be acceptable if metrics are recorded and documented clearly.

Never retry infinitely when a queue is full. Retries require deadlines, backoff, a retry limit, and idempotency to avoid amplifying load or duplicate processing.

## 9. Buffering and Batching Are Not the Same

**Buffering** holds messages waiting to be processed or transmitted. **Batching** groups multiple units of work together for combined processing, such as writing multiple records to a database in one transaction.

Batching can reduce database round-trips or processing overhead, but increases latency and memory if waiting for too many items. A batcher should have at least three thresholds:

1. Maximum number of messages per batch.
2. Maximum total bytes per batch.
3. Maximum wait time before flushing.

For example, flush upon reaching 100 records, 512 KiB, or 50 ms elapsed. Actual values must be based on load and latency targets. When the stream completes, flush the final partial batch; on error/cancellation, clearly define whether to discard or persist the in-progress batch.

Never collect an entire stream into a list before processing. That turns streaming into whole-stream buffering, causing memory to grow with the total stream size.

## 10. Observer Lifecycle and Terminal Events

An observer has a clear lifecycle:

- **onNext()** delivers messages while the stream is active.
- **onError()** terminates the stream with an error.
- **onCompleted()** terminates the stream successfully.

After a terminal event, never call `onNext()` or a second terminal event. With asynchronous queues, this requires managing call state synchronously so producers do not keep enqueueing after the RPC has ended.

On the server, **ServerCallStreamObserver.setOnCancelHandler(...)** can notify when the client cancels the call. When cancellation or a deadline occurs:

- Stop the producer/upstream subscription.
- Stop receiving or requesting further inbound messages.
- Cancel cancellable workers.
- Clear remaining queues according to semantics.
- Release byte budgets, semaphores, file handles, and related resources.

If recovery after reconnection is needed, use cursors/sequence numbers and durable state storage. An in-RAM queue tied to a terminated observer is not a resume mechanism.

## 11. Thread Safety and Message Ordering

You should not assume every **StreamObserver** implementation is thread-safe. In particular, multiple producers calling `onNext()` concurrently on the same observer can cause races, wrong ordering, or conflicts with `onCompleted()`/`onError()`.

A safe pattern is:

1. Multiple producers write only to a thread-safe queue.
2. A single writer drains the queue.
3. The writer checks readiness before each message.
4. The writer is the sole issuer of terminal events.

If workers process inbound messages in parallel, results can finish out of reception order. When business ordering matters, use a single sequential consumer or attach sequence numbers and reorder before enqueueing outbound.

If order does not matter, you still need clear rules for correlation IDs so the client can match responses to their corresponding requests.

## 12. Observing Buffering in Production

Useful metrics:

- Inbound/outbound queue depth and capacity.
- Total queued bytes and global buffer bytes.
- Average, p95/p99 queue wait time.
- Counts of queue-full, reject, or drop events.
- Duration the observer is not ready.
- Number of times the on-ready callback fires.
- Number of messages currently being processed by workers.
- Counts of RPCs ending due to cancellation, deadline, or `RESOURCE_EXHAUSTED`.

Observing each layer separately helps pinpoint bottlenecks:

- Application queue growing: producer is faster than workers or the writer.
- Application queue low but not-ready time high: pressure is likely in gRPC/HTTP/2/network or the peer.
- Inbound callbacks arriving fast but processing slow: business consumer is the bottleneck.
- Queue depth low yet heap still growing: inspect large payloads, object retention, and other buffers.

Do not log full payloads to investigate. Use RPC IDs, sequences, message sizes, queue metrics, and statuses; avoid leaking data or increasing logging load.

## 13. Common Mistakes

| Mistake | Consequence | How to handle |
| --- | --- | --- |
| Treating **StreamObserver** as a bounded queue | Cannot control the volume of pending messages | Create bounded queues at the application layer. |
| Looking only at the application queue | Overlooks gRPC internal and transport buffers | Monitor readiness and flow control across layers. |
| Draining the entire queue into the observer | Shifts pressure into gRPC buffers | Drain according to **isReady()**. |
| Bounding queues only by message count | Large payloads can still occupy huge heap | Add byte budgets and single-message limits. |
| Doing heavy business work inside callbacks | Blocks callback threads and slows other RPCs | Offload heavy work to bounded workers. |
| Multiple threads calling the observer directly | Race conditions and broken terminal ordering | Use one sequential writer per observer. |
| Batching without a time threshold | First messages wait too long | Include count, byte, and time thresholds. |
| Not cleaning up on cancel | Queues and workers hold resources after RPC ends | Cancel producers and release all quotas. |

## 14. Practice Exercises

Design a bidirectional RPC that receives sensor events and returns alerts:

1. Create an inbound queue bounded by both message count and bytes.
2. Disable auto inbound requests; call **request(1)** only when a worker has freed capacity.
3. Create a separate outbound queue for alerts; drain only when **isReady()** is true.
4. Ensure a single writer calls **onNext()**, **onError()**, and **onCompleted()**.
5. Try batching 50 events or flushing after 100 ms, whichever comes first.
6. Define policies when a queue is full, the client cancels the call, or the deadline expires.
7. Propose metrics to distinguish a slow inbound consumer from an outbound transport that is not ready.

**Completion criteria:** explain all buffering layers, bound memory by both messages and bytes, throttle inbound/outbound using the right APIs, and handle the full observer lifecycle.

## 15. Key Takeaways

- **StreamObserver** is a callback contract, not a bounded application queue.
- Buffers can reside in the application, gRPC runtime, HTTP/2/sockets, and the receiving peer.
- Use bounded queues, limiting both message count and bytes; avoid shifting the entire backlog into gRPC internal buffers.
- Throttle inbound via manual flow control/**request(n)**; throttle outbound via **isReady()** and on-ready handlers.
- Only one sequential writer may call the observer; terminal events must be emitted strictly once.
- Buffering differs from batching; batches need count, byte, and time thresholds.
- Cancellation, deadlines, and errors must stop producers and workers and release queues/quotas.

Managing stream observer buffering layer by layer helps Spring gRPC services keep memory within bounds, preserve message ordering, and continue operating stably when send, receive, and processing speeds differ.
