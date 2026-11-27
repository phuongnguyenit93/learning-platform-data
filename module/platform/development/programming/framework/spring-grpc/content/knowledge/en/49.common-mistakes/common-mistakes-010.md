# Unbounded Streams or Buffers

In a Spring gRPC service, a streaming RPC can be long-lived and transfer many messages within a single call. If the application receives data faster than it can process, or sends data faster than the client can consume, data accumulates in memory. An unbounded queue, a list holding an entire stream, or a workflow without backpressure can cause heap usage to climb continuously, raise latency, trigger `OutOfMemoryError`, and impact other RPCs.

This is a common design mistake when using `StreamObserver`: the API lets you call `onNext` repeatedly, but being able to call that method does not mean the receiver has finished processing the previous message. You must bound pending work, regulate send/receive rates, and release resources when the stream ends.

## Where do streams and buffers accumulate?

A gRPC data stream passes through multiple layers: the application producing messages, queues inside the service, grpc-java buffers, HTTP/2 flow control, sockets, and proxies; on the receiving side, there are separate queues, Protobuf decoders, and processing work. HTTP/2 flow control helps regulate data over the connection, but it does not automatically bound collections or queues created by your application.

The following code patterns easily cause trouble:

```java
// Risk: holds the entire stream's data in the heap.
List<Record> allRecords = new ArrayList<>();

repository.streamAll().forEach(allRecords::add);
allRecords.forEach(record -> responseObserver.onNext(toProto(record)));
responseObserver.onCompleted();
```

```java
// Risk: unbounded queue when the producer is faster than the consumer.
BlockingQueue<Event> pending = new LinkedBlockingQueue<>();
```

In the first example, memory grows with the total number of records. In the second example, `LinkedBlockingQueue` defaults to a huge capacity; if the producer keeps adding while the consumer lags behind, the queue can consume the entire heap. Even a queue bounded by element count can still consume too much memory if each message is large or varies widely in size.

## Bound both count and capacity

A safe design sets limits at levels aligned with business requirements:

| Resource | Limit to consider | Purpose |
|---|---|---|
| Single Protobuf message | Maximum size in bytes | Prevent one message from consuming excessive memory |
| Queue of a single stream | Message count and total queued bytes | Prevent producer from overwhelming consumer |
| Single stream | Total bytes, message count, or duration | Prevent long-lived streams from accumulating unbounded resources |
| Streams of one client/tenant | Concurrent streams and quota | Prevent one identity from exhausting service capacity |
| Entire service | Concurrent RPCs, workers, and global queues | Protect shared heap, threads, and dependencies |

Do not just set `queueCapacity = 1000` and assume it is safe. If each message can be several megabytes, 1,000 items is still an enormous amount of memory. Whenever possible, track both item count and estimated total bytes. The memory budget must account for decoded Protobuf objects, working copies during processing, queues, and concurrently active streams.

Inbound message limits such as `maxInboundMessageSize` only control individual message sizes at the receiver. They do not replace total stream data limits, queue limits, or concurrent RPC limits.

## Apply backpressure to outgoing data

For server streaming or bidirectional streaming, the service must not call `onNext` continuously while the client is not ready to receive more data. grpc-java provides `ServerCallStreamObserver.isReady()` and `setOnReadyHandler()` so the service can pace sending. When `isReady()` is `false`, stop emitting messages and resume when the callback signals the stream is ready.

The following example illustrates emitting a finite data source according to readiness. `serialExecutor` is the application's sequential executor; the iterator should read data incrementally rather than loading all results into a list upfront.

```java
ServerCallStreamObserver<RecordReply> out =
    (ServerCallStreamObserver<RecordReply>) responseObserver;

Iterator<Record> records = repository.streamFor(request).iterator();
AtomicBoolean terminated = new AtomicBoolean();

Runnable pump = () -> {
    if (terminated.get() || out.isCancelled()) {
        return;
    }

    while (out.isReady() && !out.isCancelled() && records.hasNext()) {
        out.onNext(toReply(records.next()));
    }

    if (!out.isCancelled() && !records.hasNext()
            && terminated.compareAndSet(false, true)) {
        closeUnderlyingResource(); // Close cursor once all data has been read.
        out.onCompleted();
    }
};

out.setOnReadyHandler(() -> serialExecutor.execute(pump));
out.setOnCancelHandler(() -> {
    if (terminated.compareAndSet(false, true)) {
        closeUnderlyingResource(); // Close cursor or cancel running query.
    }
});

// Run initially because the stream may already be ready before registering the callback.
serialExecutor.execute(pump);
```

This is an illustrative skeleton; production code must ensure `pump` and all observer operations are serialized, close iterators/cursors on every termination path, and never call `onCompleted` after the stream has been cancelled. If the data source is asynchronous, distinguish a temporarily empty queue from a completed source. When the queue is empty but the producer is not finished, do not prematurely complete the RPC.

`isReady()` reflects the ability to send more data at the moment of checking; it is not a license to pre-generate an unlimited number of messages. The producer must also block or pause when buffers reach their threshold. On-ready callbacks should stay short and hand off appropriate processing to a bounded sequential executor.

## Control incoming data

For client-streaming or bidirectional streaming, the service must also regulate the rate of reading and processing messages. grpc-java supports manual inbound flow control via `disableAutoRequest()` and `request(n)` on `ServerCallStreamObserver`. On the client side, `ClientResponseObserver.beforeStart` can configure `ClientCallStreamObserver` to request additional responses only after the application finishes processing the previous message.

The pattern is to allow only a bounded number of messages in flight, then request more as slots free up. For example, if the application can only process sequentially, start with one requested message and call `request(1)` after finishing the current message. For parallel processing, demand counts must match the bounded number of processing slots.

Do not forward received messages to an executor with an unbounded queue and immediately request more messages. That merely shifts the accumulation point from gRPC to the executor. If processing must be offloaded, use a worker pool with a bounded queue; when space runs out, pause demand or reject the stream per API contract.

## Use bounded queues and explicit overload policies

When producer and consumer must be decoupled, choose a queue with bounded capacity. Example:

```java
BlockingQueue<Event> pending = new ArrayBlockingQueue<>(128);

boolean accepted = pending.offer(event);
if (!accepted) {
    // Do not keep accepting indefinitely when the consumer has fallen behind.
    // Apply the overload policy defined for this RPC.
}
```

`offer` lets the application detect a full queue without blocking indefinitely. Depending on business needs, the policy when full can be:

- Pause requesting the next message via inbound flow control to give the consumer time to catch up.
- Reject new RPCs when concurrency or quota limits are reached.
- Cancel the current stream with an appropriate status and message if safe continuation is impossible.
- Persist data to durable storage with quotas and cleanup policies when business logic requires long-running processing.

Never silently drop messages if the protocol requires complete processing. If business rules allow dropping data, explicitly define which messages may be discarded, how the client learns about it, and how recovery works. Avoid blindly using `CallerRunsPolicy` on gRPC callbacks: executing heavy work on the callback-invoking thread can stall other RPC processing paths.

## Bound stream lifetimes and concurrency

Long-lived open streams still consume resources even when no messages are flowing at a given moment. Consider deadlines or maximum durations, concurrent stream limits per tenant and service-wide, and appropriate idle timeout policies. RPC deadlines must be propagated to and respected by downstream calls; otherwise, a stream that already expired on the client side can still leave background work running.

When the client cancels the RPC or the deadline expires, the service must stop the producer, cancel downstream queries/work, and close resources such as cursors, file handles, or subscriptions. With `ServerCallStreamObserver`, register `setOnCancelHandler` to react when the client cancels. Ensure the cancel callback does not free a resource while another worker is still using it; stopping and closing must be properly synchronized.

Set separate limits for:

- Open streams per user or tenant.
- Total active streams per instance.
- Stream worker count and worker queue length.
- Total bytes or message count allowed per stream.
- Idle timeout and maximum stream duration.

Limits must coordinate with connection limits and proxy/load balancer settings. If limits are enforced only per instance across multiple instances, tenant-wide quotas may require a shared counter or an explicit capacity allocation mechanism.

## Example of a controlled streaming design

Suppose a client uploads a large file to a Spring gRPC service via a client-streaming RPC. A safe design splits the file into small chunks, bounds each chunk's size, allows only a bounded number of chunks in flight, and writes each chunk directly to storage as it streams. The server verifies permissions before allocating resources, checks total bytes and chunk counts, and confirms completion after verifying the checksum.

In this design, the server never assembles the entire file into a single `byte[]` on the heap. When storage slows down, the server reduces demand so the client cannot keep pushing chunks into an unbounded queue. If the total quota is exceeded, the server terminates the RPC with the agreed error and records the cause. When the client disconnects, the server aborts incomplete writes or persists resumable state according to business policy.

For a server-streaming RPC returning large data, apply the same principle in reverse: read page by page or via cursor, send only when `isReady()` permits, and close the data source when the stream completes or is cancelled.

## Observability and testing

Monitoring key metrics helps detect accumulating buffers before the heap runs out:

| Metric | What to observe |
|---|---|
| Active stream count and stream duration | Streams steadily rising or abnormally long-lived streams |
| Item count and total bytes in queues | Prolonged queue growth, frequently hitting limits |
| Queue wait time and message processing time | Consumer falling behind producer |
| Queue-full counts or rejected RPCs | System frequently hitting protective thresholds |
| Heap, GC pauses, and active thread counts | Memory or thread pressure rising with load |
| Cancelled, timed-out, and failed stream rates | Client or downstream unable to keep up |

At a minimum, test the following cases:

1. Producer sends faster than consumer over an extended period; verify queues stay within bounds and heap remains stable.
2. Client reads responses slowly; verify the server respects `isReady()` and does not pre-build all responses.
3. Send large messages and bursts of messages; verify both byte-based and count-based limits hold.
4. Open many concurrent streams from one tenant and across multiple tenants; verify quotas and service-wide limits.
5. Client cancels mid-stream or deadline expires; verify producers, cursors, subscriptions, and workers stop/release.
6. Slow down a dependency such as database or object storage; verify backpressure propagates back to the data source.
7. Fill the queue; verify the system applies the intended rejection, pause, or cancellation policy and emits matching metrics/logs.

## Practices to avoid

- Collecting an entire stream into a `List`, `byte[]`, or `String` when input size has no strict bound.
- Using unbounded queues or queues sized far beyond the memory budget.
- Calling `onNext` in a loop without checking readiness and without bounding producer rate.
- Receiving messages and pushing them into an executor with an unbounded queue.
- Allowing streams to remain open indefinitely without quotas, idle timeouts, or cancellation mechanisms.
- Limiting only individual message sizes while ignoring total bytes, message counts, and concurrent streams.
- Ignoring cancellation, leaving queries, cursors, or background work running after the client has left.

In Spring gRPC, services are typically registered as Spring beans and use grpc-java's streaming APIs. Spring managing the beans does not automatically provide backpressure for `StreamObserver`; the application must still design queue limits, flow control, quotas, and RPC lifecycle handling. When these limits are clearly defined and measurable, rising load leads to controlled throttling or rejection instead of unbounded memory growth.
