# Buffer Limits

## Learning Objectives

After this lesson, you can:

- Identify the buffer layers in a gRPC processing flow and know which layers need limits.
- Distinguish transport buffers, deserialized messages, and application-managed queues.
- Design limits by item count and by bytes to control real memory usage.
- Use manual inbound flow control so messages are not received faster than processing capacity.
- Use isReady/on-ready handlers to throttle outbound responses.
- Combine buffer limits with message-size limits, byte quotas, concurrency, and deadlines.
- Handle full queues, cancellation, and cleanup without losing or duplicating data.
- Test buffer high-water marks, backpressure, and overload on grpc-java/Spring gRPC.

## 1. What is a buffer in a gRPC service?

In **SPRING_GRPC**, data passes through multiple layers before reaching a business handler or leaving the server. The transport can hold bytes in socket, TLS, and HTTP/2 buffers; grpc-java receives and deframes gRPC messages; protobuf allocates objects on the heap; the application may further place messages into queues for asynchronous processing.

A **buffer** is a temporary holding area for data or work waiting to be processed. Buffers help absorb short-term speed differences between producer and consumer, yet unbounded buffers turn bursts into memory growth. If the producer continuously outpaces the consumer, queues grow until heap or direct memory runs out.

Clearly identify which buffer is being bounded:

| Layer | Examples | Related limit/mechanism |
| --- | --- | --- |
| Network/transport | Socket, TLS, HTTP/2 frames and flow-control windows | Transport/OS configuration; flow control |
| gRPC message | Bytes being deframed/serialized | Max inbound/outbound message size |
| Protobuf/application object | Request, response, decoded byte arrays | Message-size and field validation |
| Application queue | ArrayBlockingQueue, pending response list | Item capacity and byte budget |
| In-flight work | Submitted tasks, messages currently being processed | Concurrency limits and bounded executors |
| Streaming producer | Event sources, database cursors, broker subscriptions | Backpressure, pause/resume, and cancellation |

A limit at one layer does not automatically bound the other layers. maxInboundMessageSize bounds the size of one incoming message, yet does not bound how many messages sit in an application queue. HTTP/2 flow control throttles bytes on the transport, yet does not guarantee the business consumer has finished processing messages.

~~~mermaid
flowchart TD
    A["Socket / TLS / HTTP2"] --> B["gRPC framing and messages"]
    B --> C["Protobuf objects"]
    C --> D["Application bounded queue"]
    D --> E["Worker / business consumer"]
    E --> F["Database or downstream"]
    D --> G["Queue full: pause, reject, or shed"]
    G --> H["Backpressure / RESOURCE_EXHAUSTED"]
~~~

## 2. Why must buffers be bounded?

Buffers are useful when producer and consumer speeds differ briefly. For example, a broker might emit a burst of 2,000 events over a few seconds, while the service processes 500 events per second. A finite queue absorbs part of the burst without forcing transport callbacks to wait.

If buffers are unbounded:

- Heap grows as protobuf objects, byte arrays, and domain objects are retained.
- Direct memory grows from transport/network buffers.
- Queue wait increases, causing deadlines to expire before tasks even start.
- One fast stream can starve other streams of resources.
- Cancellation fails to release data if producers keep enqueueing.
- Garbage collection increases and degrades latency for every RPC.
- When the process hits OOM, the entire instance can stop serving.

The goal is not to eliminate all buffers. The goal is to set intentional capacities, define explicit full-buffer behavior, and observe high-water marks.

## 3. Limiting by item count alone is not enough

An ArrayBlockingQueue bounds the number of items, yet individual items can vary in size. A queue holding 100 tiny messages is lightweight; 100 messages near 4 MiB each can hold hundreds of MiB of payload, not counting object overhead.

Therefore, buffers typically need two limits:

- **Item capacity:** maximum number of messages/tasks in the queue.
- **Byte budget:** total payload size permitted in the queue.

For example, a queue bounded to 128 messages and 16 MiB of payload. A message must satisfy both conditions to be accepted. When dequeuing a message for processing or discarding it, release the exact byte budget that was reserved.

For protobuf generated messages, getSerializedSize() reports the serialized payload size in bytes. This is a useful measurement for setting budgets, though it does not equal exact heap footprint: protobuf objects, collections, strings, byte arrays, and references carry overhead. Add headroom or measure actual heap during load tests.

## 4. Thread-safe byte budgets with multiple producers

You can use an atomic budget to reserve/release bytes for a queue. Check whether current exceeds maximum minus bytes to avoid overflow when adding:

~~~java
import java.util.concurrent.atomic.AtomicLong;

public final class ByteBudget {

    private final long maximumBytes;
    private final AtomicLong usedBytes = new AtomicLong();

    public ByteBudget(long maximumBytes) {
        if (maximumBytes <= 0) {
            throw new IllegalArgumentException(
                    "maximumBytes must be positive");
        }
        this.maximumBytes = maximumBytes;
    }

    public boolean tryReserve(long bytes) {
        if (bytes <= 0 || bytes > maximumBytes) {
            return false;
        }

        while (true) {
            long current = usedBytes.get();
            if (current > maximumBytes - bytes) {
                return false;
            }
            if (usedBytes.compareAndSet(current, current + bytes)) {
                return true;
            }
        }
    }

    public void release(long bytes) {
        if (bytes <= 0) {
            throw new IllegalArgumentException("bytes must be positive");
        }

        while (true) {
            long current = usedBytes.get();
            if (bytes > current) {
                throw new IllegalStateException("Byte budget underflow");
            }
            if (usedBytes.compareAndSet(current, current - bytes)) {
                return;
            }
        }
    }

    public long usedBytes() {
        return usedBytes.get();
    }

    public long remainingBytes() {
        return maximumBytes - usedBytes.get();
    }
}
~~~

When enqueueing, reserve bytes first and then offer the item to the queue. If queue offer fails, release immediately:

~~~java
int bytes = message.getSerializedSize();

if (!byteBudget.tryReserve(bytes)) {
    return false;
}

if (!pending.offer(new PendingMessage(message, bytes))) {
    byteBudget.release(bytes);
    return false;
}

return true;
~~~

When the consumer takes an item from the queue, clearly decide when to release. If the message remains retained during processing, release after processing finishes; if the queue budget only measures queued data and workers have a separate budget, release upon dequeue and reserve against the in-flight budget. Never release early while the object is still retained without another budget covering it.

CAS in release avoids temporary negative totals when multiple producers/consumers run concurrently. However, a total counter cannot detect if one specific reservation was released twice while other reservations remain outstanding. In production code, wrap each reservation in a lease with AtomicBoolean/idempotent close and attach that lease to the exact item. Never let multiple complete/error/cancel branches release the same reservation. If you need to bound both queued and in-progress worker data, manage queue bytes and in-flight bytes separately or use one unified budget throughout.

## 5. Bounded queues and behavior when full

Queues need finite capacity. For example:

~~~java
BlockingQueue<PendingMessage> pending =
        new ArrayBlockingQueue<>(128);
~~~

When offer returns false, the queue is full. Choose a policy per contract:

| Behavior | When appropriate | Risks |
| --- | --- | --- |
| Pause inbound reads | Producer supports backpressure | Must resume in time and avoid deadlocks |
| Reject stream/call | Hard quota exhausted | Client must understand RESOURCE_EXHAUSTED |
| Drop by policy | Only for telemetry/events whose semantics allow loss | Potential data loss; must measure and document |
| Persist to durable storage | Need to absorb bursts longer than memory budget | Increases latency and storage cost |
| Block callback thread | Almost never suitable for gRPC callbacks | Can block transport and cause starvation |

Do not use unbounded queues or blocking put() inside gRPC callbacks if doing so can block the transport executor. Do not use CallerRunsPolicy to run heavy tasks directly on callback threads. When the queue is full, pause the producer, reject in a controlled way, or offload to a durable queue.

Never silently drop messages for commands, payments, uploads, or data requiring completeness. If the system allows dropping telemetry, clearly specify the sampling/drop policy and track dropped-count metrics.

## 6. Inbound streaming: manual flow control to bound buffers

For client-streaming or bidirectional streaming, the server can actively control how many request messages may be sent next. grpc-java provides ServerCallStreamObserver.disableAutoRequest() to turn off automatic inbound flow control; the application calls request(n) when capacity is available.

Conceptual handling pattern for client-streaming:

~~~java
@Override
public StreamObserver<UploadChunk> upload(
        StreamObserver<UploadResult> responseObserver) {

    ServerCallStreamObserver<UploadResult> call =
            (ServerCallStreamObserver<UploadResult>) responseObserver;

    call.disableAutoRequest();
    call.request(1);

    return new StreamObserver<>() {
        private boolean terminal;

        @Override
        public synchronized void onNext(UploadChunk chunk) {
            if (terminal || call.isCancelled()) {
                return;
            }

            processChunkAndReleaseCapacity(chunk);

            if (!terminal && !call.isCancelled()) {
                call.request(1);
            }
        }

        @Override
        public synchronized void onError(Throwable error) {
            if (!terminal) {
                terminal = true;
                cleanupUpload();
            }
        }

        @Override
        public synchronized void onCompleted() {
            if (terminal) {
                return;
            }
            terminal = true;
            finishUpload(responseObserver);
            cleanupUpload();
        }
    };
}
~~~

This illustrative example processes sequentially right inside the callback. If processing blocks, do not hold the callback thread for long; offload the task to a bounded worker executor and call request(1) only after the worker finishes, frees its buffer, and capacity remains. If multiple in-flight tasks are allowed, the initial request count should equal only the reserved slots, not an arbitrary large number.

request(n) controls message count, not byte budget. Combine it with max inbound message size and a byte budget so a single large message does not blow past memory budgets. Calling the next request too early defeats backpressure.

## 7. Outbound streaming: isReady and on-ready handlers

On the server-to-client response side, ServerCallStreamObserver.isReady() indicates whether the transport can currently accept more data under flow control. setOnReadyHandler() registers a callback invoked when readiness transitions to ready.

~~~java
ServerCallStreamObserver<EventResponse> call =
        (ServerCallStreamObserver<EventResponse>) responseObserver;

ArrayBlockingQueue<EventResponse> pending =
        new ArrayBlockingQueue<>(128);

call.setOnReadyHandler(() -> {
    while (call.isReady()) {
        EventResponse next = pending.poll();
        if (next == null) {
            break;
        }
        call.onNext(next);
    }
});
~~~

This is an illustrative skeleton; production code must ensure only one producer/serialized drain calls onNext at a time and no blocking work runs inside the on-ready callback. When the producer enqueues the first response, trigger a drain immediately if the call is already ready; do not only wait for a readiness transition callback, because the transport may already have been ready before the queue had data. When the queue empties, the producer can continue fetching from the source; when the queue fills, pause the source or apply the defined policy.

isReady() does not tell you exactly how many bytes of free space remain in the transport buffer. It is a readiness signal, not a memory measurement or byte limit. You still need a bounded application queue and byte budget. If response objects vary in size, limiting only to 128 items does not guarantee total memory.

With asynchronous producers, use a sequential drain loop and check isReady() before each emission. When the client cancels, cancel subscriptions/producers and clear pending queues. Never call onNext after a terminal event.

## 8. Flow control, buffer limits, and message-size limits are three distinct mechanisms

| Mechanism | What does it limit? | What does it not solve? |
| --- | --- | --- |
| Max inbound/outbound message size | Bytes of one gRPC message | Message count or stream queues |
| HTTP/2/gRPC flow control | In-flight bytes per stream and connection | Tasks waiting in the application |
| Application buffer limit | Items and/or bytes held by the application | Transport buffers and message parsing before handler |
| Message count limit | Total messages in one RPC | Size of individual messages |
| Stream concurrency limit | Number of open RPCs | Queue bytes of each RPC |
| Deadline | Duration call/resources are held | Instantaneous memory cap |

Do not enlarge HTTP/2 flow-control windows to fix a full application queue. Larger windows allow more in-flight bytes and increase memory pressure. Likewise, do not shrink windows and assume the application already has proper backpressure; producer/consumer throttling at the application layer is still required.

A solid design places limits where data is received, where data is buffered, and where data is processed.

## 9. Calculating memory budgets per stream and per instance

To choose buffer capacity, estimate the memory held by each stream and total concurrent streams:

\[
M_{\text{instance}} \approx
M_{\text{base}} +
N_{\text{streams}} \times
(M_{\text{state}} + M_{\text{inflight}} + M_{\text{queue}})
\]

Where:

- \(M_{\text{base}}\): baseline heap/direct memory for the process, caches, and framework.
- \(N_{\text{streams}}\): number of concurrent streaming RPCs.
- \(M_{\text{state}}\): state, principal, subscription, and callbacks per stream.
- \(M_{\text{inflight}}\): messages currently being processed and corresponding buffers.
- \(M_{\text{queue}}\): data waiting in application queues.

This formula is an estimation model. Protobuf objects and Java collections have overhead; Netty direct memory is separate from heap; compression can cause payloads to expand on decompression. Measure memory in load tests with near-limit payloads and production-like concurrency.

If each stream has a 4 MiB queue and the server allows 500 streams, the theoretical queue budget alone reaches 2 GiB. Therefore, per-stream capacity must be multiplied by concurrency when calculating total memory. A global cap is needed so combined queues do not exceed the instance budget.

Do not double-count or omit memory across budgets; pinpoint when ownership transfers from transport to application and from queue to worker. Reserve headroom for bursts, garbage collection, response buffers, and administrative tasks.

## 10. Cancellation and buffer cleanup

When a client cancels a stream or a deadline expires, the server must stop producers and free pending data:

~~~java
call.setOnCancelHandler(() -> {
    upstreamSubscription.cancel();
    pending.clear();
    releaseAllOutstandingReservations();
    stopProducer();
});
~~~

Illustrative code like this needs an idempotent mechanism. If a consumer concurrently dequeues a message while cancel clears the queue, each reservation must still be released exactly once. Use per-entry leases/atomic state or a single owner managing queue lifecycle.

Resources to clean up:

- Pending message queues and byte reservations.
- Broker/database subscriptions or cursors.
- Scheduled tasks and heartbeats.
- Futures/tasks waiting in executors.
- Stream concurrency permits.
- Temporary files or staging buffers.
- Context/references holding principals or request payloads.

On completion/error/cancellation, set terminal state before cleanup so producers do not enqueue more items. Never call onNext after onError or onCompleted. If a running task cannot be interrupted immediately, it must check cancellation before committing side effects or emitting responses.

## 11. Full queues: overload, retries, and durable buffering

When an application buffer fills up, the right action depends on data semantics:

- For commands or uploads, stop accepting messages and return a clear error if backpressure cannot be applied.
- For resumable event subscriptions, pause the source and persist the cursor; if a hard quota is exhausted, end the stream so the client reconnects.
- For droppable telemetry, apply a sampling/drop policy backed by metrics and documented in the contract.
- For work that must survive beyond the RPC, write to a durable queue/job store instead of buffering indefinitely in memory.

RESOURCE_EXHAUSTED fits when a stream or buffer hits its quota/capacity. UNAVAILABLE may be used if the service is temporarily unable to accept work per contract; pick a stable mapping. Never use PERMISSION_DENIED for a full buffer.

Clients should not retry immediately in a tight loop. Use exponential backoff, jitter, and cursor/sequence to resume. For operations with side effects, use idempotency keys to avoid duplicate processing when the client does not know whether the last message committed.

Durable buffering also requires disk quotas, retention, retry limits, and dead-letter policies. Moving everything from memory to disk without limits merely shifts resource exhaustion onto disk.

## 12. Buffers in executors and downstreams

An RPC can pass through multiple queues: gRPC callback dispatch, application executor, HTTP client connection pool, database pool, and broker client. Each queue needs its own capacity and timeout.

If an application executor queue holds 500 tasks while the database pool has only 20 connections, tasks will queue again at the database layer. Chained queues make latency unpredictable and keep requests alive too long. Prefer admission limits at the front of the pipeline and avoid submitting tasks beyond downstream capacity.

When queue wait plus expected processing time exceeds the remaining deadline, discard the task before starting. Do not use CallerRunsPolicy to turn a full queue into running business logic on gRPC callback threads. Use bounded executors, explicit rejections, and appropriate statuses.

Monitor queue depth at every tier to locate bottlenecks. One shallow queue does not mean the system is free of buffer pressure; data may be backing up in the network, downstream clients, or brokers.

## 13. Observing buffers and high-water marks

Recommended metrics:

- Current item count, capacity, and high-water mark of each queue.
- Reserved bytes, maximum bytes, and byte high-water mark.
- In-flight message/task count.
- Number of failed queue offers or rejected buffer budget reservations.
- Inbound messages requested/paused/resumed.
- Time messages spend in queues and processing latency.
- Outbound readiness stall duration and producer pause count.
- Streams canceled while queues still held data.
- Heap, direct memory, allocation rate, and GC pauses.
- RESOURCE_EXHAUSTED by method/quota group.

Do not use stream IDs, user IDs, or arbitrary tenant IDs as metric labels because cardinality can grow unchecked. Use method, direction, workload class, and quota tier; use redacted logs/traces to investigate individual calls.

Alert when queue depth or reserved bytes stay near capacity, high-water marks trend upward, rejections spike, or queue wait approaches deadlines. A buffer that is constantly full signals a producer/consumer imbalance, not merely a reason to raise capacity.

## 14. Testing buffer limits and backpressure

Tests should verify both capacity and reservation lifecycle:

| Scenario | Expected result |
| --- | --- |
| Queue has slot and byte budget | Message is enqueued |
| Queue is full | Offer fails or admission pauses |
| Queue has slot but byte budget exhausted | Message is rejected |
| Dequeue and processing finish | Byte reservation is released accurately |
| Enqueue fails after reserve | Reservation is rolled back |
| Inbound flow control enabled | Server receives only requested message count |
| Consumer finishes processing | Server requests additional messages |
| Outbound observer not ready | Producer stops emitting unboundedly |
| Client cancels | Queue, subscriptions, and reservations cleaned up |
| Multiple concurrent streams | Per-stream and global budgets are not exceeded |
| Message near max size | Buffer memory stays within budget |
| Deadline expires while message waits | Task produces no side effects after terminal state |

Use deterministic tests with small queue capacities, small byte budgets, and latches to hold consumers busy. Do not use Thread.sleep as the primary synchronization mechanism. Test N+1 items, exact byte limit, and one byte over to verify boundaries.

In-process gRPC tests work well for checking application queues, counters, and cancellation logic. For isReady, HTTP/2 windows, and transport buffer behavior, add integration tests using the actual Netty transport/version; in-process transport may not fully simulate network backpressure.

In Spring application tests, verify executors, interceptors, and streaming services are wired through the real application context. Measure heap/direct memory in separate load tests to confirm chosen capacities fit your deployment.

## 15. Common implementation pitfalls

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| Limiting only item count | Large messages push total memory over budget | Add byte budget |
| Limiting only max message size | Many small messages accumulate unboundedly | Bounded queues and stream quotas |
| Using unbounded queues | Heap grows until OOM | Finite queue capacity |
| Calling put/blocking in callbacks | Blocks gRPC executor and causes starvation | Manual flow control or reject |
| Requesting next message right after submit | Consumer has not finished yet while messages keep arriving | Request after capacity is freed |
| Ignoring isReady when emitting responses | Transport/application buffers grow | Bounded outbound queue and on-ready drain |
| Treating isReady as free byte count | Misestimates memory | Treat as readiness signal, keep separate byte budget |
| Releasing reservation on dequeue while worker holds object | Budget underreports actual memory | Release when object is dropped or transfer to in-flight budget |
| Non-idempotent queue cleanup | Double release or leaks | Leases/terminal guards |
| Testing only in-process | Misses transport flow-control behavior | Add Netty integration tests |

## 16. Hands-on exercises and self-check questions

### Hands-on exercises

1. Create a bounded queue of 128 items and a 16 MiB byte budget for a streaming method.
2. Reserve serialized size before enqueueing; roll back the reservation if queue offer fails.
3. Use manual inbound flow control to request the next message only when workers have capacity.
4. Use ServerCallStreamObserver.isReady/on-ready handler to emit outbound responses cleanly.
5. Add a cancellation handler to stop the producer, clear the queue, and release reservations.
6. Combine per-stream budgets with global stream concurrency and max inbound message size.
7. Record metrics for item count, reserved bytes, high-water mark, and rejection count.
8. Write unit/in-process tests for full queue, full bytes, N+1, cancellation, and multiple concurrent streams; add Netty tests for readiness/flow control.

### Self-check questions

**1. Why is limiting item count alone insufficient?**  
Because message sizes vary; a queue with few items but huge payloads can still retain too much memory.

**2. Does getSerializedSize() equal heap footprint?**  
No. It measures the serialized protobuf payload; object graphs and buffers have separate overhead.

**3. Does request(n) limit bytes or messages?**  
It requests the next n inbound messages; combine it with message-size limits and byte budgets.

**4. What does isReady() tell you?**  
That the transport can currently accept more responses per flow-control state; it does not report exact free buffer bytes.

**5. When should a byte reservation be released?**  
When the data is no longer retained under that budget, or when ownership is transferred to another budget.

**6. Should a full queue block the callback thread?**  
No. Use manual flow control, pause the producer, or reject in a controlled manner.

**7. When is RESOURCE_EXHAUSTED appropriate?**  
When a buffer/stream quota has hit its limit and the service cannot accept more data per contract.

**8. Why are Netty integration tests needed in addition to in-process tests?**  
To verify readiness, HTTP/2 flow control, and real transport buffer behavior.

## Summary

Buffer limits must be applied at the right layers: transport, gRPC messages, protobuf objects, and application queues. Queues must have finite capacity in both items and bytes; with streaming, manual inbound flow control lets the server accept more messages only when consumers have room, while outbound isReady/on-ready handlers let producers respect transport readiness. Combine buffer budgets with message-size, total-byte, stream-concurrency, and deadline limits. When full, pause or reject explicitly; cancellation must stop producers and release queues/reservations exactly once. Monitor high-water marks and test both application logic and Netty transport to prevent memory growth and cascading overload.
