# Backpressure When Clients Are Slow

## Learning Objectives

After this lesson, you will be able to:

- Recognize signs that the server is generating responses faster than the client can consume them.
- Use gRPC Java outbound readiness to throttle response emission.
- Combine client inbound demand with bounded queues to achieve end-to-end backpressure.
- Design a producer that can pause/resume and handle non-pausable data sources.
- Choose policies for full queues, client-cancelled RPCs, and expired deadlines.
- Test and monitor streaming with slow-reading clients without unbounded memory growth.

## 1. Why Do Slow Clients Put Pressure on the Server?

In server-streaming or bidirectional streaming, the server can continuously generate responses. A client may read slowly because of time-consuming business processing, disk writes, downstream service calls, or network bandwidth constraints.

If the server keeps generating and queuing responses faster than they can be sent, pending data accumulates in memory. When multiple RPCs experience this simultaneously, heap usage grows, garbage collection runs frequently, and other requests can be affected.

**Backpressure** is a way of signaling upstream to the producer that the consumer is not ready to receive more data. The producer slows down, pauses, or refuses to continue upon hitting a limit. In Spring gRPC, you need to coordinate gRPC's readiness mechanism, HTTP/2 flow control, and application-layer queues.

## 2. Backpressure Flow from Client to Server

With server-streaming, data flows from the server to the client. When the client reads slowly, the transport layers progressively restrict how much data the server can send. At the application layer, **ServerCallStreamObserver.isReady()** lets the server know when gRPC is ready to accept more responses.

~~~mermaid
flowchart LR
  P["Server producer"] --> Q["Bounded outbound queue"]
  Q --> D["gRPC response writer"]
  D --> T["HTTP/2 transport"]
  T --> C["Client"]
  C -. "Slow reading / reduced demand" .-> T
  T -. "Readiness drops" .-> D
  D -. "Pause drain" .-> Q
  Q -. "Threshold reached" .-> P
~~~

A safe processing flow has the following steps:

1. The producer creates a response and places it into a bounded outbound queue.
2. The writer only pulls messages from the queue when the observer is ready.
3. When the observer is not ready, the writer pauses; the queue holds pending data within limits.
4. When readiness returns, the writer resumes draining the queue.
5. If the queue fills up, the application pauses the producer or applies the documented overflow policy.

Backpressure is effective when the readiness/demand signal ultimately slows down data generation. If you only stop sending while continuing to generate and store responses in an unbounded queue, memory still grows.

## 3. isReady() and the On-Ready Callback on the Server

The server can cast the response observer to **ServerCallStreamObserver<T>**:

~~~java
ServerCallStreamObserver<PriceUpdate> outbound =
    (ServerCallStreamObserver<PriceUpdate>) responseObserver;
~~~

Two key APIs:

- **isReady()**: indicates whether gRPC can currently accept more outbound messages according to the implementation's buffer/readiness thresholds.
- **setOnReadyHandler(...)**: registers a callback invoked when readiness transitions to ready to continue sending.

Example:

~~~java
outbound.setOnReadyHandler(this::scheduleDrain);

// Need to trigger the initial drain if the observer is already ready.
scheduleDrain();
~~~

Do not interpret **isReady() == true** as meaning the client has read or finished processing the previous response. It is a capacity signal at the sending/transport layer, not a business confirmation or per-message ACK. Similarly, false indicates that you should stop sending more to avoid buffer accumulation; it does not necessarily prove client code is hung.

Never use a busy loop like **while (!outbound.isReady()) {}**. Return control to the executor and wait for the callback when readiness changes.

## 4. Bounded Outbound Queues

A dedicated queue per RPC helps limit the amount of pending responses:

~~~java
BlockingQueue<PriceUpdate> pending =
    new ArrayBlockingQueue<>(128);
~~~

When the producer creates a response:

~~~java
boolean accepted = pending.offer(update);
if (!accepted) {
    // Pause the producer or transition the RPC to the overflow policy.
}
~~~

**offer()** does not block for long when the queue is full. Avoid calling **put()** on data-producing threads or gRPC callbacks if waiting could hold a shared executor.

Bounding by message count is not enough when payloads vary greatly in size. For large data, add a **byte budget**:

- Maximum number of pending messages.
- Maximum total pending serialized size, which can be estimated using **getSerializedSize()**.
- Maximum size of a single response.
- Number of concurrently running producer tasks.

The byte budget must be updated atomically or under synchronization on enqueue/dequeue. Serialized size only estimates the Protobuf payload; it does not include all object, queue node, and transport buffer overhead.

## 5. Draining Responses Based on Readiness

Only one writer should call **onNext()** on the same response observer. All producers put responses into the queue; the writer pulls them when the observer is ready:

~~~java
void drain() {
    while (!cancelled.get() && outbound.isReady()) {
        PriceUpdate next = pending.poll();
        if (next == null) {
            break;
        }
        outbound.onNext(next);
    }
}
~~~

Register **setOnReadyHandler(this::scheduleDrain)** and call **scheduleDrain()** after each enqueue. The `scheduleDrain` method should ensure only one drain task is active at a time, for example using an `AtomicBoolean` with a sequential executor.

This is the core logic, not a complete service. In a real implementation:

- Call **onNext**, **onError**, and **onCompleted** sequentially on the same writer.
- Do not let two threads drain the same queue for the same observer concurrently.
- After a drain finishes, re-check readiness and the queue to avoid missing a signal when a producer enqueues right as the writer yields.
- If the executor rejects a task or the producer fails, terminate the RPC through a single terminal path.

Do not emit **onCompleted()** simply because the producer has finished. Wait until the outbound queue is empty and no response is still waiting to be drained.

## 6. Pausing and Resuming the Producer

Readiness is only useful if the producer can react. If the producer queries a database page by page, reads a file in chunks, or consumes from a pausable source, connect queue/readiness state to continuing data generation.

Example producer flow:

~~~text
produce page/chunk
      |
      v
enqueue response
      |
      v
queue nearly full or outbound not-ready?
      |                 |
     No                Yes
      |                 |
produce next       pause source
                        |
                 readiness returns
                        |
                   resume source
~~~

Use the data source's pause/resume API if available. Do not pre-generate thousands of responses before checking **isReady()**. If the source can only be read sequentially, keep a cursor or offset to resume after the consumer is ready.

With asynchronous producers, avoid blocking event-loop threads or gRPC executors while waiting for queue space. Use signals, semaphores, or a scheduler to resume when capacity becomes available.

## 7. Clients Can Throttle Inbound Demand

A client streaming responses can also use manual inbound flow control to request more messages only after finishing the previous one. With gRPC Java, **ClientResponseObserver** provides **ClientCallStreamObserver** inside **beforeStart(...)**.

Example of a client requesting only one response initially:

~~~java
ClientResponseObserver<SubscribeRequest, PriceUpdate> observer =
    new ClientResponseObserver<>() {

        private ClientCallStreamObserver<SubscribeRequest> call;

        @Override
        public void beforeStart(
                ClientCallStreamObserver<SubscribeRequest> requestStream) {
            this.call = requestStream;
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

Here, the client requests only the first message; after the worker finishes processing one response, the client calls **request(1)** to allow receiving the next. In production code, guard against calling `request` when the call has already finished/cancelled and handle errors from `consumerExecutor`.

When the client reduces demand, gRPC and HTTP/2 can slow down DATA delivery from the server. The server usually observes this effect via readiness once buffers/transmission windows are consumed. This is layered backpressure; it does not mean a single `request(1)` translates 1-to-1 into a corresponding `WINDOW_UPDATE` frame.

## 8. Full Queue: Never Let the Producer Continue Unbounded

A full queue signals that generation speed has exceeded consumption capacity over a period of time. Choose a policy based on data semantics:

| Policy | When appropriate | Notes |
| --- | --- | --- |
| **Pause producer** | Source can pause and resume | Preferred when every message must be kept. |
| **Reject RPC** | Cannot hold more data and cannot pause | Can return **RESOURCE_EXHAUSTED**; client must handle the error. |
| **Drop newest** | Newer data is less important than pending data | Must measure and document dropped message counts. |
| **Drop oldest** | Only the latest state is needed, e.g. snapshots | Unsuitable for events that must preserve history. |
| **Persist** | Longer-term load absorption is needed with durability requirements | Requires quotas, retention, and a resume mechanism. |

For business events, transactions, or auditable data, do not arbitrarily drop messages. You can stop the source or terminate the RPC with **RESOURCE_EXHAUSTED**. Never retry infinitely; require deadlines, backoff, and a retry limit.

If a client needs to resume after reconnecting, design cursors/sequence numbers and a resume mechanism at the application layer. An in-memory queue tied to a terminated RPC cannot guarantee redelivery.

## 9. Slow Client, Slow Network, and Cancelled Client

Three situations can produce similar symptoms yet require different handling:

- **Client processes slowly**: the client receives messages, but the application consumes them slowly; manual demand can reduce the number of requested messages.
- **Slow network or packet loss**: transport/TCP is constrained even if the client application is ready. Readiness can still drop because sent data has not cleared buffers.
- **Client cancels RPC or disconnects**: the server must stop the producer and release resources instead of continuing to wait for readiness.

On the server, use **setOnCancelHandler(...)** to receive notification when the call is cancelled:

~~~java
outbound.setOnCancelHandler(() -> {
    cancelled.set(true);
    cancelUpstreamProducer();
    pending.clear();
});
~~~

The snippet illustrates signaling shutdown. If the queue has a byte budget, cleanup must also reset/release the counter; if the producer holds subscriptions or file handles, cancel/close them properly.

An expired deadline must also stop response generation. Do not continue querying or computing just to push data into a stream that the client is no longer waiting on.

## 10. One Slow RPC Must Not Exhaust System-Wide Resources

Queues should be bounded per RPC and across the entire service:

- **Per-RPC limit** prevents one client from consuming excessive memory.
- **Global limit** prevents thousands of RPCs, each within its own quota, from collectively exceeding heap.
- **Concurrency limit** bounds the number of active producers/workers.
- **Fair scheduling** prevents one stream from monopolizing the writer or executor.

Do not set a large per-RPC queue while ignoring concurrent RPC counts. For instance, 1,000 RPCs with a 128-message queue can hold up to 128,000 messages, excluding payload bytes and object overhead.

When the global quota is exhausted, reject new RPCs or apply explicit admission control. Do not hold semaphores or permits forever after cancellation; release resources in the cleanup path.

## 11. Testing with Slow-Consuming Clients

A useful test needs to deliberately make the client read slowly rather than just sending a few small messages:

1. Create a server-streaming RPC that emits a large number of responses of known size.
2. Use a client **ClientResponseObserver** with **disableAutoRequestWithInitial(1)**.
3. In the consumer, delay processing each message before calling **request(1)**.
4. Observe server readiness, queue depth, and byte budget.
5. Verify that the producer pauses/resumes or the RPC is rejected per policy when the queue fills up.
6. Cancel the client mid-stream and verify that the producer, worker, and queue are cleaned up.
7. Run multiple slow RPCs concurrently to verify global quotas and fairness.

You should not assert that **isReady()** immediately turns false the instant the client stops calling **request(1)**. The transport may still have buffers and windows that allow some data to keep flowing before transmission pressure surfaces on the server. Tests should verify memory bounds and eventual behavior rather than depending on an exact readiness timestamp.

Metrics to monitor:

- Queue depth and queued bytes per RPC.
- Count of queue threshold/capacity exhaustion events.
- Time producers spend paused.
- Duration outbound is not ready.
- Counts of sent, processed, rejected, or dropped messages.
- Counts of RPCs cancelled, deadline exceeded, or resource exhausted.
- Number of active producers/workers and total queue memory.

Do not log full payloads just to identify slow clients. Use request IDs, sequence numbers, message sizes, and aggregated metrics.

## 12. Common Mistakes

| Mistake | Consequence | How to handle |
| --- | --- | --- |
| Continuing to generate responses when **isReady()** is false | Outbound queue grows even though transport is congested | Pause the producer or bound the queue. |
| Using an unbounded queue | Slow client causes continuous heap growth | Bounded queue and byte budget. |
| Treating **isReady()** as a client ACK | Wrongly inferring that messages were processed | Use application-layer acknowledgements if confirmation is needed. |
| Using readiness alone without queue bounds | Data still accumulates ahead of the writer | Bound the queue and producer rate. |
| Blocking gRPC callbacks to wait for the client | Ties up executors and impacts other RPCs | Use asynchronous callbacks/signals. |
| Multiple threads writing to the observer | Race conditions, wrong ordering, or duplicate terminal events | Use a single sequential outbound writer. |
| Ignoring cancellation/deadlines | Producer keeps running for a departed client | Cancel upstream and clean up resources. |
| Retrying streaming infinitely after overflow | Amplifies load and may send duplicates | Backoff, retry limits, idempotency, and resume cursors. |

## 13. Practice Exercises

Design a server-streaming RPC that sends price updates to clients:

1. Define **SubscribePricesRequest** and **PriceUpdate**.
2. Create an outbound queue bounded by both message count and total bytes.
3. Use **ServerCallStreamObserver.isReady()** and the on-ready handler to drain.
4. When the queue is nearly full, pause the upstream subscription; when the queue drains down, resume.
5. On the client, use manual inbound flow control and only call **request(1)** after finishing an update.
6. Define behavior when the client is slow for too long, the queue is full, the deadline expires, or the client cancels.
7. Design metrics to distinguish a fast producer, a slow consumer, and a slow network.
8. Write an integration test with a client that delays processing and verify the queue stays within quota.

**Completion criteria:** backpressure propagates upstream to the producer, queues have explicit bounds, responses are sent according to readiness, and all resources are released when the RPC terminates.

## 14. Key Takeaways

- Slow clients cause pending responses to accumulate; backpressure must slow down the producer rather than merely pausing the writer.
- **ServerCallStreamObserver.isReady()** and **setOnReadyHandler()** throttle outbound at the gRPC layer; readiness is not a business ACK.
- Clients can use **ClientResponseObserver** and **disableAutoRequestWithInitial(n)** to throttle inbound demand.
- Use queues bounded by both message count and bytes; define pause, reject, drop, or persist policies based on semantics.
- Only one sequential writer may call the observer; never block gRPC callbacks waiting on queues or readiness.
- Cancellation and deadlines must stop producers, workers, and release quotas.
- Test with slow-reading clients and multiple concurrent RPCs to verify memory limits both per-RPC and service-wide.

Properly designed backpressure enables Spring gRPC to adapt to clients with varying consumption speeds, protect server memory, and maintain streaming RPC reliability under increasing load.
