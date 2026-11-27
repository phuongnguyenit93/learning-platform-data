# Streaming Messages and Backpressure in Spring gRPC

Streaming allows a single RPC to exchange many messages over time. However, if the sender emits messages faster than the receiver can accept or process them, data can accumulate in buffers, increasing latency and memory consumption. **Backpressure** is the mechanism for regulating the send rate according to downstream receive capacity, keeping the data stream stable under changing load.

In **Spring gRPC**, applications use gRPC Java APIs such as **StreamObserver**, **isReady()**, **setOnReadyHandler()**, and inbound message demand controls. Understanding these signals lets you implement server streaming, client streaming, and bidirectional streaming without creating unbounded queues or confusing sending a message with successful processing.

## 1. Why Does Streaming Need Backpressure?

Suppose a device sends 20,000 measurement records per second while the server can only process 5,000 records per second. If the client keeps calling **onNext()** continuously, pending messages can grow by around 15,000 records every second. Over time, memory is exhausted, latency climbs, and eventually the entire system can fail.

~~~mermaid
flowchart LR
    A["Producer<br/>20.000 msg/s"] --> B["Queue / transport buffer"]
    B --> C["Consumer<br/>5.000 msg/s"]
    B --> D["Backlog grows"]
    D --> E["Latency and memory increase"]
    E --> F["Overload / failure"]
~~~

Backpressure helps the sender **pause, slow down, or emit more only when the receiver is ready**. The goal is not always maximum send speed, but keeping in-flight pending data bounded.

Backpressure is especially important when:

- Server streaming pushes events to clients on slow networks.
- Client streaming uploads a large batch of data to the server.
- Bidirectional streaming has two directions operating at different speeds.
- The server handles many concurrent streams and must share CPU, memory, connections, and downstream resources.

Unary typically has one request and one response, so there is no long sequence of messages to throttle. Even so, unary still needs limits on message size, concurrent requests, and processing time.

## 2. Three Layers of Throttling to Distinguish

Backpressure is not a single switch. In gRPC running over HTTP/2, three layers are involved:

| Layer | Mechanism | What Does It Regulate? |
| --- | --- | --- |
| **HTTP/2 transport** | Flow-control window at connection and stream levels | Number of DATA bytes that can be sent before transport-level acknowledgment |
| **gRPC Java API** | Readiness and inbound demand | When the application may send more or request additional inbound messages |
| **Application** | Bounded queues, worker limits, quotas, batching | Business processing rate and amount of queued work |

HTTP/2 flow control operates in **bytes**, without understanding the business semantics of a Reading or OrderEvent. gRPC frames Protobuf messages into DATA frames; a large message can consume many bytes of the transport window.

At the gRPC Java layer, **isReady()** and **setOnReadyHandler()** inform the sender of current write capacity. On the receiving side, **manual inbound flow control** lets you request a specific number of messages instead of receiving automatically.

At the application layer, even when transport allows sending, an unbounded internal queue can still exhaust memory. All three layers must work together; you cannot rely solely on HTTP/2 flow control to protect the whole system.

## 3. isReady() and setOnReadyHandler() When Sending Messages

In gRPC Java, observers that support sending data provide:

- **isReady()**: indicates whether more can currently be sent without growing the outbound buffer beyond gRPC's threshold.
- **setOnReadyHandler(Runnable)**: registers a callback invoked when the observer transitions to ready-to-send state.

The control pattern is **only emit messages while isReady() returns true**, and pause when it returns false. When the on-ready callback fires, resume emitting from where you left off.

~~~java
// Illustrative pattern for a server-side response stream.
ServerCallStreamObserver<Reading> output =
    (ServerCallStreamObserver<Reading>) responseObserver;

Iterator<Reading> pending = readings.iterator();
AtomicBoolean completed = new AtomicBoolean(false);

Runnable sendAvailable = () -> {
    while (output.isReady() && pending.hasNext()
            && !output.isCancelled()) {
        output.onNext(pending.next());
    }

    if (!pending.hasNext() && !output.isCancelled()
            && completed.compareAndSet(false, true)) {
        output.onCompleted();
    }
};

output.setOnReadyHandler(sendAvailable);
sendAvailable.run(); // Also handles the case where the stream is ready initially.
~~~

This pattern is for a finite list; in real applications, the data source or queue must be bounded. If data is generated asynchronously, coordinate enqueueing items and re-invoking the sender on an appropriate executor. Do not call the sender concurrently from multiple threads without serialization.

**Do not mistake isReady() for processing confirmation.** A true value is only an outbound gRPC flow readiness signal; it does not prove the peer has read, processed, or persisted the message. Returning from **onNext()** is not a business acknowledgment either.

### Readiness Can Change

Do not check isReady() once at the start and then emit the entire stream. As buffers fill, readiness can turn false. Producers must stop emitting and wait for the callback instead of continuing to push messages into the observer.

When multiple producers feed into one observer, **serialize** onNext, onCompleted, and onError operations. **StreamObserver is not thread-safe by default**; concurrent calls from multiple threads can cause races, out-of-order messages, or premature stream termination.

## 4. Controlling Received Message Count: Manual Inbound Flow Control

Readiness regulates the **send direction of the current observer**. Another requirement is limiting how many messages the application receives before finishing processing. gRPC Java supports manual inbound flow control via:

- **disableAutoInboundFlowControl()**: disables automatic requesting of additional messages.
- **request(n)**: asks gRPC to deliver up to n more inbound messages to the application.

For example, a server can request the next Reading only after finishing the current record. With **ServerCallStreamObserver**, inbound control APIs are invoked on the server-side observer, which is passed into the method as the response observer:

~~~java
ServerCallStreamObserver<UploadSummary> call =
    (ServerCallStreamObserver<UploadSummary>) responseObserver;

call.disableAutoInboundFlowControl();
call.request(1);

return new StreamObserver<Reading>() {
    @Override
    public void onNext(Reading reading) {
        processAsync(reading, result -> {
            // Only request the next message after finishing processing.
            if (!call.isCancelled()) {
                call.request(1);
            }
        });
    }

    @Override
    public void onError(Throwable error) {
        // Stop processing and release resources.
    }

    @Override
    public void onCompleted() {
        // Finalize aggregation and send UploadSummary.
    }
};
~~~

This is a **conceptual pattern**; in production applications, ensure async completion callbacks do not call request(1) after the RPC is cancelled or finished, and synchronize all state safely across threads. Handle exceptions in processAsync, enforce timeouts, and ensure accepted work never hangs indefinitely.

On the client, **ClientResponseObserver.beforeStart(ClientCallStreamObserver<ReqT>)** provides the call observer to configure controls before the stream begins. Calling **request(n)** on the call observer controls how many inbound response messages the client asks to receive. Exact usage must align with the API's inbound/outbound direction and your gRPC Java version.

Manual inbound flow control fits when message processing is expensive or must be coordinated with a worker pool. When processing is fast, sequential, and data volume is bounded, auto flow control is usually simpler.

## 5. Applying by Streaming RPC Type

| RPC Type | Direction to Regulate | Common Approach |
| --- | --- | --- |
| **Server streaming** | Server → client | Server checks readiness before emitting responses; client can limit inbound demand |
| **Client streaming** | Client → server | Client sends only when request observer is ready; server can request each request after processing |
| **Bidirectional streaming** | Both directions independently | Each side regulates its own outbound stream and its own inbound demand |

### Server Streaming

The server can emit data from large sources or continuous events. If the client is slow, the server must pause its producer when the response observer is not ready. With paginated data sources, fetch the next page only when the sender has capacity to emit; avoid loading the entire dataset into a List.

### Client Streaming

The client uploads many messages. The producer should hold a small number of pending messages, send while the observer is ready, and pause when readiness turns false. The server processes messages under a quota or bounded worker pool; do not spawn an unbounded task for every onNext.

### Bidirectional Streaming

Both directions have independent readiness and processing speeds. A client might read events slowly while still sending requests rapidly; or the server might send responses quickly while the client is busy. Each side needs its own queue, limit, and cancellation policies, without assuming throttling one direction automatically controls the other.

## 6. Bounded Queues and Overload Policies

isReady() governs gRPC's write readiness, but the application producer still needs a bounded queue. A common design:

1. Producer creates messages and inserts them into a queue with fixed capacity.
2. A single sequential sender pops messages from the queue while the observer is ready.
3. When the queue is full, apply a business policy: block the producer within a limit, reject messages, reduce rate, coalesce updates, or cancel the stream.
4. When the stream is cancelled/errored, stop the producer and drain/release the queue.

No single drop policy fits all data:

| Data Type | Options to Consider on Overload | What to Avoid |
| --- | --- | --- |
| Telemetry needing only the latest value | Coalesce multiple updates into the latest value per device | Coalescing if full history must be saved |
| Logs/audit | Backpressure or durable write to an external queue | Silently dropping events |
| Control commands | Reject with status or enforce quotas | Merging commands when order/operations are not equivalent |
| Ephemeral UI events | Coalesce or drop per defined policy | Holding unbounded queues for disconnected clients |

Queues must bound both **message count** and **total bytes**. A 100-item queue can still consume gigabytes if each message is huge. Also enforce message size limits and time-to-live limits.

## 7. When to Request More Messages vs. When to Send Next?

Two operations are frequently confused:

- **Outbound readiness:** the sender checks isReady() to know whether it should call onNext() again.
- **Inbound demand:** the receiver uses request(n) to ask gRPC to deliver n more messages to the application when manual inbound flow control is enabled.

One regulates messages **being sent out**; the other regulates messages **delivered to the receive callback**. They complement each other but are not interchangeable.

For example, an upload-receiving server can:

- Use inbound demand to accept a new chunk only after the previous chunk is processed.
- Use outbound readiness to send acknowledgments or summaries only when the response stream is ready.
- Use a bounded queue for pending DB work instead of spawning unbounded tasks.

If business logic requires confirming data was durably persisted, send an **acknowledgment message** containing the sequence or upload ID after committing. The isReady() signal, request(n), and calling onNext() carry no persistence confirmation semantics.

## 8. Stream Cancellation, Deadlines, and Overload Errors

Backpressure cannot fix a consumer that has stopped forever. Every stream needs appropriate deadline, idle timeout, or cancellation policies.

Common statuses:

| Status | When It May Be Used |
| --- | --- |
| **RESOURCE_EXHAUSTED** | Quota, queue limit, or allowed capacity exceeded |
| **CANCELLED** | Client or server proactively cancelled the stream |
| **DEADLINE_EXCEEDED** | RPC exceeded its time budget |
| **UNAVAILABLE** | Service or connection temporarily unavailable |
| **INVALID_ARGUMENT** | Message size or content violates contract |

On cancellation, stop the producer, stop generating messages, release queues, and cancel downstream tasks if possible. Never continue calling onNext() after the observer has terminated.

For streaming RPCs, deadlines normally apply to the **entire call**, not resetting after each message. A long stream needs clear lifecycle management; consider bounded-duration sessions and cursor/sequence-based reconnection instead of holding a single RPC forever.

## 9. Example Bounded Upload Design

Suppose a client sends Readings via client streaming. A resilient design requires:

- The client reads sequentially from a data source without loading an entire file into RAM.
- The client keeps a small queue and sends only when the request observer is ready.
- The server checks sequence numbers, limits count and size, and processes each message.
- The server sends UploadSummary only upon completion and makes clear whether data has been committed.
- On mid-stream failure, the client uses upload ID and sequence to query status or resume without duplicate writes.

Sender pseudocode:

~~~java
void sendWhileReady(
        ClientCallStreamObserver<Reading> requestStream,
        Iterator<Reading> source) {
    while (requestStream.isReady() && source.hasNext()) {
        requestStream.onNext(source.next());
    }

    if (!source.hasNext()) {
        requestStream.onCompleted();
    }
    // If not ready yet, wait for setOnReadyHandler to invoke this method again.
}
~~~

In real implementations, include a completed flag so onCompleted() is called only once, and synchronize if sendWhileReady can be triggered from multiple threads. Also distinguish source exhaustion from stream termination due to error/cancellation.

## 10. Testing Backpressure

A test that merely verifies the server receives all messages when the client sends fast does not prove backpressure works. You must create a slow consumer and observe whether the sender actually pauses/throttles or whether queues grow unboundedly.

Scenarios to test:

1. **Slow consumer:** add artificial delay per message; verify the sender respects readiness or inbound demand.
2. **Full queue:** verify rejection, coalescing, or producer-pausing policies behave as designed.
3. **Large messages:** byte limits take effect, not just item counts.
4. **Mid-stream cancellation:** producers and workers stop, queues are freed.
5. **Deadlines:** expired streams leave no endlessly running tasks or leaked resources.
6. **Multiple concurrent streams:** one slow client does not exhaust resources for other clients.
7. **Ordering and integrity:** no messages are lost or reordered when the sender pauses and resumes.

In Spring gRPC integration tests, run a real streaming client via a stub against a service with controlled processing speed. Measure pending message counts, readiness wait times, throughput, memory, and terminal statuses. Never rely solely on total elapsed runtime to conclude backpressure is working.

## 11. Operational Observability Metrics

To detect streams causing overload, monitor:

- **Active open streams** by method and client/tenant.
- **Messages/bytes sent and received** per RPC.
- **Queue depth**, oldest message age, and how often queues hit thresholds.
- **Readiness wait time** and how often senders pause.
- **Producer/consumer rates**, throughput, and processing latency.
- **RPC counts ending in CANCELLED, DEADLINE_EXCEEDED, or RESOURCE_EXHAUSTED**.
- **Memory, CPU, and busy worker counts**.

When queues grow steadily, look for slow consumers or producers ignoring readiness. When isReady() is frequently false, downstream clients/servers may be slow or message size/frequency exceeds current capacity. When many streams hit RESOURCE_EXHAUSTED, check whether quotas and limits match legitimate load.

## 12. Summary and Self-Check

**Backpressure** keeps send speed aligned with receive/processing capacity. In gRPC Java:

- **isReady()** and **setOnReadyHandler()** regulate the **outbound direction**.
- **disableAutoInboundFlowControl()** and **request(n)** regulate **inbound message delivery** when using manual flow control.
- Bounded queues, quotas, byte limits, and cancellation protect the **application layer**.

None of these signals prove that a message has been business-processed or durably persisted. If acknowledgments are needed, define dedicated acknowledgment responses/messages.

Self-check:

1. Why is HTTP/2 flow control alone insufficient to prevent unbounded application queues?
2. How do isReady() and request(1) control two different things?
3. When a consumer is slow, why must the sender pause emitting rather than keep calling onNext()?
4. Why do queues need byte limits in addition to message count limits?
5. If an upload is cancelled after the server persisted part of the data, what information is needed to retry safely?

Good streaming design is not just picking the right RPC type, but also controlling **rate, memory, lifecycle, and acknowledgment semantics** for every message. That is the foundation for keeping Spring gRPC services stable as load rises or clients have varying network and processing speeds.
