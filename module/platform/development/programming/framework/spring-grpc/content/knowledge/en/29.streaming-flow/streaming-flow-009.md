# Mid-Stream Errors and Buffer Cleanup

## Learning Objectives

After this lesson, you will be able to:

- Describe what happens when a streaming RPC encounters an error after exchanging some messages.
- Distinguish stream errors, half-close, cancellation, and deadlines.
- Terminate responses with strictly one terminal event and stop producers from continuing to send.
- Identify ownership of messages, queue entries, and buffers across the application, gRPC runtime, and Netty.
- Release queues, byte budgets, subscriptions, and reference-counted resources strictly once.
- Test mid-stream errors to detect memory leaks, late emissions, and misprocessed data.

## 1. Mid-Stream Errors Differ from Pre-RPC Errors

Unary RPCs typically have one request and one response. With streaming RPCs, many messages may have already been sent or processed before an error occurs. For example, a multi-chunk upload may persist part of the data and then encounter a checksum error on the next chunk; a server-streaming RPC may emit several updates before its data source disconnects.

When an error occurs mid-stream, gRPC terminates the call with an error status. The client may have already received several messages before the error callback is invoked. Messages already processed on the client are not automatically rolled back when the stream fails.

Therefore, the application must clearly define:

- Which portion of data has been acknowledged or durably stored.
- Which portion only sat in buffers and was never delivered.
- Which resources need to be stopped or released.
- Whether the client can retry the entire RPC or must resume from an acknowledged sequence/offset.

In **SPRING_GRPC**, this matters for chunked uploads/downloads, event streams, and long-running bidirectional RPCs. A terminal error with the right status that leaves producers, queues, or buffers alive is still a lifecycle bug.

## 2. What Happens to Messages Sent Before an Error?

Suppose the server emits three messages and then hits an error:

~~~text
Server -> Client: onNext(A)
Server -> Client: onNext(B)
Server -> Client: onNext(C)
Server -> Client: onError(UNAVAILABLE)
Client: onNext(A), onNext(B), onNext(C), onError(...)
~~~

This is an observable sequence if the first three messages were delivered to the client before the terminal status. However, calling `onNext` is not a business ACK: the sender cannot conclude the peer processed or durably saved a message merely because `onNext` returned.

If an error happens while some messages remain in internal buffers, do not assume all of them reached the client application. The transport may terminate the stream before pending data finishes flushing.

Consequently, for data requiring delivery guarantees, define ACKs, sequence numbers, idempotency keys, or cursors at the application layer. Terminal status only describes the RPC outcome; it provides no transactional rollback for already-processed messages.

## 3. Distinguishing Errors, Half-Close, Cancellation, and Deadlines

These situations carry different meanings:

| Situation | Meaning | Primary action |
| --- | --- | --- |
| **Stream error** | One side terminates the RPC direction with an error | Send/receive error status, stop producer, and clean up. |
| **Half-close** | One side signals no more messages on the request direction | Finish processing received data; response direction can remain active. |
| **Cancellation** | Client or runtime cancels an active call | Stop background work and release resources; do not try to send more responses. |
| **Deadline exceeded** | RPC timeout expires before completion | Stop work that is no longer useful and free buffers. |
| **Successful completion** | Response direction completes successfully | Drain remaining valid pending data then call `onCompleted` strictly once. |

In particular, receiving `onCompleted` on the request observer in client-streaming only signals the client finished sending requests. The server can still process the last chunk, emit the summary response, and complete the response observer.

Never treat cancellation as success, and never call `onCompleted` to mask an error that occurred.

## 4. Choosing the Right Status for Mid-Stream Errors

The server should map errors by cause rather than using a single generic status for everything:

| Cause | Typically appropriate status |
| --- | --- |
| Malformed chunk data or input rule violation | INVALID_ARGUMENT |
| Resource or queue exceeds quota | RESOURCE_EXHAUSTED |
| Requested resource does not exist | NOT_FOUND |
| Transient dependency failure such as upstream unavailable | UNAVAILABLE |
| Unexpected internal processing failure | INTERNAL |

Example terminating server-streaming when an upstream source fails:

~~~java
responseObserver.onError(
    Status.UNAVAILABLE
        .withDescription("Update source is temporarily unavailable")
        .asRuntimeException());
~~~

The status is a terminal event. After calling `onError`, stop the producer, cancel subscriptions, and never call `onNext` or `onCompleted` again on that observer. Do not put tokens, payload contents, or internal stack traces in descriptions sent to clients.

If an error occurs after responses have already completed, the outcome of the finished RPC cannot be changed. Record late errors via logs/metrics or handle them in a separate workflow.

## 5. Buffers Exist Across Multiple Layers

When handling mid-stream errors, distinguish the places where data may still reside:

1. **Application queue**: messages waiting for workers or the writer.
2. **In-flight work**: messages taken from the queue that a worker is still processing.
3. **gRPC runtime buffer**: messages passed to the observer not yet fully written to the transport.
4. **HTTP/2 and socket buffers**: bytes waiting to be transmitted or read by the peer.
5. **Peer application queue**: messages that reached the peer but have not been processed by the application.

~~~mermaid
flowchart LR
  P["Producer"] --> Q["Application queue"]
  Q --> W["In-flight worker"]
  W --> G["gRPC runtime buffer"]
  G --> H["HTTP/2 / socket"]
  H --> R["Peer receiver"]
  E["Error / cancel / deadline"] -.-> P
  E -.-> Q
  E -.-> W
  E -.-> G
~~~

The application directly manages only the queues and work it creates. The gRPC runtime and transport manage their own internal buffers. Never arbitrarily clear or release gRPC's internal buffers using Netty APIs.

An empty application queue does not mean all data reached the peer; conversely, transport termination does not automatically release subscriptions, file handles, or objects to which the application still holds references.

## 6. Buffer Ownership and When to Release

A core rule is that **every resource must have a single owner responsible for releasing it**:

- Ordinary Protobuf messages and `ByteString` instances are immutable/GC-managed Java objects; the application drops references when no longer needed.
- Application-created queue entries must be removed and have associated resources released when discarded or finished.
- Byte budgets, semaphore permits, and counters must be returned strictly once.
- Netty `ByteBuf` is reference-counted; the owning party must release it the exact number of times it was retained.
- Internal buffers owned by the gRPC transport must have their lifecycle managed by gRPC.

Do not release a `ByteBuf` merely because `observer.onNext` was called if serializer code or an asynchronous task still holds a reference to it. Equally, do not keep a `ByteBuf` alive indefinitely after the stream ends.

When there is no clear ownership contract, a simpler approach is copying payloads into an application-owned `ByteString` or byte array before placing them into Protobuf messages. Once copied, the application can release its source buffer.

## 7. Safely Converting Netty ByteBuf to Protobuf

Example adapter receiving a `ByteBuf` from an application layer and producing an independent Protobuf payload:

~~~java
ByteString payload;
try {
    ByteBuffer view = source.nioBuffer(
        source.readerIndex(),
        source.readableBytes());
    payload = ByteString.copyFrom(view);
} finally {
    ReferenceCountUtil.release(source);
}

UploadChunk chunk = UploadChunk.newBuilder()
    .setData(payload)
    .build();
~~~

`ByteString.copyFrom` creates a copy of the data; the Protobuf message no longer depends on the source `ByteBuf` lifecycle. This example assumes the adapter owns the reference released in `finally`. If the buffer is shared or retained extra times, adhere to the allocator's ownership/reference-count rules.

Never release a buffer still owned by other code. Never call `release` twice for the same reference. When a queue holds objects with closeable resources, queue entries should expose an explicit `close`/`release` method so cleanup can dispose of unsent messages as well.

## 8. Cleanup Must Be Idempotent

Errors, cancellations, and deadlines can occur close together. For instance, upstream emits an error right as the client cancels the call. Multiple callbacks may request cleanup simultaneously.

A safe cleanup function needs to:

- Have a flag or synchronization mechanism guaranteeing disposal logic runs only once.
- Cancel upstream subscriptions/producers.
- Stop workers or signal workers to stop at safe checkpoints.
- Drain the queue, closing/releasing each entry and returning byte budgets.
- Cancel timers, tasks, and registered callbacks.
- Close cursors, file handles, or business resources.

Example cleanup skeleton:

~~~java
final class StreamResources {
    private final AtomicBoolean cleaned = new AtomicBoolean();
    private final Queue<PendingChunk> pending = new ConcurrentLinkedQueue<>();
    private final AtomicReference<Subscription> upstream =
        new AtomicReference<>();

    void cleanup() {
        if (!cleaned.compareAndSet(false, true)) {
            return;
        }

        Subscription subscription = upstream.getAndSet(null);
        if (subscription != null) {
            subscription.cancel();
        }

        PendingChunk item;
        while ((item = pending.poll()) != null) {
            item.close();
        }
    }
}
~~~

**PendingChunk.close()** must be idempotent or invoked strictly once by its owner. If producers can enqueue concurrently with cleanup, synchronize state checks with enqueueing; otherwise, a new entry can appear after the cleanup loop has drained the queue.

Never hold locks while performing I/O or waiting for workers to stop. Cleanup should signal shutdown, close fast resources, and let longer steps run on an appropriate executor.

## 9. Stopping Producers and Writers After a Terminal Event

When a stream fails, calling `onError` only terminates the observer. Asynchronous producers can keep running if the application does not cancel them. Writers may also still have tasks queued to drain.

A safe termination path needs to:

1. Transition call state from OPEN to FAILED/CANCELLED via an atomic operation or serial executor.
2. Block new enqueues and prevent the writer from emitting `onNext`.
3. Cancel upstream subscriptions or producers.
4. Clear queues and in-flight tasks per policy.
5. Emit strictly one terminal event if the call can still send.
6. Release remaining application-owned resources.

On the server, register a cancellation handler:

~~~java
ServerCallStreamObserver<Update> call =
    (ServerCallStreamObserver<Update>) responseObserver;

call.setOnCancelHandler(() -> {
    session.markCancelled();
    session.stopProducer();
    session.cleanup();
});
~~~

When the transport has already signaled cancellation, do not call `onError` or `onCompleted` in response to cancellation. The handler only stops work and cleans up; it is not a response-emitting path.

For errors detected by the application while the call is still active, the writer/terminal coordinator emits `onError` strictly once and then runs cleanup. Every producer must check state before enqueueing or sending messages.

## 10. Inbound Stream Errors

On a server receiving client-streaming, gRPC invokes callbacks on the request observer returned by the service. If processing a chunk fails:

- Stop receiving or requesting additional chunks.
- Cancel work depending on the invalid data.
- Close the upload session and release pending buffers.
- If the call is still active, terminate the response with an appropriate error status.

If the request stream is cancelled by the client, the server should use the cancellation handler to stop work. Do not assume every disconnect is a business error requiring a response; the call may already be cancelled at the transport level.

On a client receiving server-streaming, the `onError` callback is a terminal result from the server or transport. The client must stop the consumer, clear pending queues per policy, and release resources; never call `request` again after a terminal event.

## 11. Already-Processed Data and Resumability

Mid-stream errors do not roll back business state. With uploads, some chunks may have been durably written while a subsequent chunk fails. With event streams, the client may have applied a subset of events before losing connectivity.

If retry or resume is needed:

- Attach stable sequence numbers or offsets to each message.
- Acknowledge only after data reaches the durability level required by the contract.
- Use idempotency keys so chunks/events can be reprocessed without duplicate side effects.
- Persist cursors/checkpoints somewhere that survives across RPCs.
- Define a policy for chunks currently in flight but not yet acknowledged.

Do not blindly retry an entire stream if earlier messages already caused side effects. An `UNAVAILABLE` status may indicate a transient error, but it does not prove previous operations were not executed.

## 12. Testing Mid-Stream Errors and Buffer Cleanup

Actively inject errors at multiple points:

1. Error before the first message.
2. Error after several messages have been sent.
3. Error while the outbound queue still holds messages.
4. Error while a worker is actively processing an entry.
5. Client cancels at the exact moment upstream emits an error.
6. Deadline expires while queues are non-empty.
7. Error after request half-close but before the final response.

After each case, verify:

- Client receives the expected status and receives no callbacks after the terminal event.
- Producers/subscriptions have been cancelled.
- Queue depth and queued bytes return to 0.
- Byte permits, semaphores, and reference-counted buffers are returned the exact right number of times.
- No lingering workers or scheduled tasks retain the terminated session.
- Acknowledged messages are stored correctly; unacknowledged portions can be retried per contract.

With Netty `ByteBuf`, leak-detection tools can be used in appropriate test environments. Do not rely solely on heap after a single run; repeat tests many times and observe trends in retained memory, active tasks, and queue metrics.

## 13. Observing and Diagnosing in Production

Metrics should be attached to RPC IDs or trace contexts, not directly to payloads:

- Terminal status by RPC method.
- Counts of messages and bytes sent/received before error.
- Queue depth, queued bytes, and evicted entry counts.
- Number of times cleanup is invoked versus actually executed.
- Count of upstream subscriptions/workers still active after terminal events.
- Failed buffer releases or abnormal reference counts if instrumented.
- Time elapsed from terminal event until resources are released.

If error statuses rise while queues and workers remain non-zero, the cleanup path may be failing to stop producers. If queues drop to 0 yet memory does not drop immediately, distinguish garbage collection, buffer pools, and true leaks. Never manually free transport buffers simply because heap metrics appear high.

Do not log tokens, file contents, or full messages on error. Logging status codes, sizes, sequences/offsets, and correlation IDs suffices for most diagnostics.

## 14. Common Mistakes

| Mistake | Consequence | How to handle |
| --- | --- | --- |
| Calling `onError` without stopping the producer | Messages keep being generated after terminal event | Transition state, cancel producer, and stop writer. |
| Clearing the queue without closing entries | Internal `ByteBuf`/files/resources leak | Drain queue and release/close each entry. |
| Releasing `ByteBuf` immediately after passing reference to an async task | Consumer accesses an already-released buffer | Copy payload or establish explicit ownership handoff. |
| Releasing internal buffers of gRPC/Netty transport | Data corruption or double-release | Only release application-owned resources. |
| Non-idempotent cleanup | Double-release or returning permits multiple times | Use state/atomics and clear ownership. |
| Enqueueing concurrently with unsynchronized cleanup | New entries missed after queue has been cleared | Synchronize admission with closed state. |
| Treating `onNext` as a durable storage ACK | Retries can lose or duplicate side effects | Use application-layer ACKs/checkpoints. |
| Retrying the whole stream after an error | Reprocesses already-succeeded messages | Use sequences, idempotency, and resume cursors. |

## 15. Practice Exercises

Design a client-streaming upload that receives chunks and persists them to storage:

1. Each chunk has an upload ID, sequence, offset, payload, and checksum.
2. Bound the inbound queue by both message count and bytes.
3. When a checksum fails on chunk N, terminate the RPC with an appropriate status.
4. Cancel producers/workers, drain the queue, and release all buffers held by the application.
5. Simulate client cancellation occurring concurrently with a checksum error; verify cleanup runs only once.
6. Save checkpoints for durably written chunks and design resume after reconnection.
7. Write integration tests confirming no `onNext` after terminal events and zero remaining queue entries after cleanup.

**Completion criteria:** distinguish sent data from acknowledged data, terminate streams strictly once, release buffers according to ownership, and explain a safe retry/resume strategy.

## 16. Key Takeaways

- Mid-stream errors terminate the RPC but do not roll back messages already processed by the client.
- Distinguish stream errors, request half-close, cancellation, deadlines, and successful completion.
- After a terminal event, stop producers/writers; emit no further `onNext` or terminal callbacks.
- Clean application queues by closing/releasing each entry, returning byte budgets, and cancelling background tasks.
- Protobuf `ByteString` is generally GC-managed; Netty `ByteBuf` must be released according to ownership/reference count.
- Never manually free internal buffers owned by the gRPC transport.
- Cleanup must be idempotent and safe when errors, cancellation, and deadlines happen concurrently.
- For safe retry/resume, use sequences, checkpoints, ACKs, and idempotency at the application layer.

Handling mid-stream errors alongside ownership-safe buffer cleanup helps Spring gRPC services stop work promptly, avoid memory leaks and double-releases, and preserve recovery capabilities in long-lived streaming RPCs.
