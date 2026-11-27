# Inbound and Outbound Message Queues

## Learning Objectives

After this lesson, you will be able to:

- Distinguish between an **inbound queue** and an **outbound queue** from the perspective of a gRPC endpoint.
- Design bounded queues to decouple network callbacks from business processing.
- Throttle inbound messages using manual flow control and **request(n)**.
- Throttle outbound messages using **isReady()** and **setOnReadyHandler(...)**.
- Preserve message ordering and handle full queues, errors, completion, and cancellation.
- Avoid unbounded data accumulation in client-streaming, server-streaming, and bidirectional streaming in Spring gRPC.

## 1. What Are Inbound and Outbound?

Inbound and outbound are defined from the perspective of the endpoint being considered:

- **Inbound messages** travel from the peer into the current endpoint.
- **Outbound messages** travel from the current endpoint out to the peer.

For a gRPC server, inbound is typically the requests sent by the client; outbound is the responses the server sends back to the client. For a client, these directions are reversed: responses are inbound, and requests are outbound.

In a streaming RPC, one side may receive or send many messages. If the callback receiving data also has to execute queries, write to a database, or call other services, the network-handling thread can slow down. If a producer generates responses faster than the transport can send them, pending data can accumulate in memory.

An **application-layer message queue** creates a boundary between receiving/sending messages and processing work. A queue needs a bound and an overflow policy; merely adding a queue does not create backpressure on its own if producers keep pushing data into it.

## 2. Inbound/Outbound Queue Architecture

A bidirectional flow on the server can be structured as follows:

~~~mermaid
flowchart LR
  C["Client"] -->|"Inbound messages"| IQ["Bounded inbound queue"]
  IQ --> W["Worker / business logic"]
  W --> OQ["Bounded outbound queue"]
  OQ --> D["Outbound drain"]
  D -->|"StreamObserver.onNext"| C
  D -.->|"isReady / on-ready"| D
~~~

- The inbound callback receives messages and places them into the inbound queue.
- The worker takes messages out, runs business logic, and creates responses.
- Responses are placed into the outbound queue.
- A single sending flow drains responses when gRPC signals readiness.

The two queues serve different purposes. The inbound queue absorbs newly received data for the worker to process; the outbound queue holds results waiting to be sent. You should not use one shared queue for both directions because it is difficult to apply appropriate bounds, ordering, and error policies for each flow.

## 3. Application Queues Differ from Transport Buffers

A streaming RPC can have multiple data buffering layers:

1. Queues created by the application to hold items waiting for processing.
2. gRPC's internal queue once a message has been passed to **StreamObserver**.
3. HTTP/2 and operating system buffers.
4. Buffers at the receiving peer.

HTTP/2 flow control limits the amount of DATA in flight according to stream and connection windows. gRPC APIs like **isReady()** report sending readiness at the gRPC layer. Application queues, meanwhile, determine how many business messages are held on the heap.

Therefore, HTTP/2 flow control does not automatically bound an **ArrayBlockingQueue** created by the application. Likewise, a bounded application queue does not replace HTTP/2 flow control or message-size limits.

## 4. Designing a Bounded Inbound Queue

The inbound queue stores messages already delivered by gRPC to the **onNext** callback. You should choose a queue with an explicit capacity:

~~~java
BlockingQueue<UploadChunk> inboundQueue =
    new ArrayBlockingQueue<>(32);
~~~

Or use a **LinkedBlockingQueue** with an explicit capacity. Avoid unbounded constructors if a producer can send faster than workers for a prolonged period.

Inside the callback:

~~~java
@Override
public void onNext(UploadChunk chunk) {
    if (!inboundQueue.offer(chunk)) {
        failCall(Status.RESOURCE_EXHAUSTED
            .withDescription("Inbound queue is full"));
        return;
    }
    scheduleWorker();
}
~~~

**offer()** returns immediately when the queue is full, allowing the application to enforce a clear policy. **put()** can block the receiving callback; if the callback runs on gRPC's shared executor, blocking for a long time can affect other RPCs.

A full queue is not a situation in which to silently drop messages. Depending on the contract, you can:

- Stop requesting more inbound messages using manual flow control.
- Reject the RPC with **RESOURCE_EXHAUSTED**.
- Slow down the producer if the application protocol supports it.
- Write data to a durable queue with a quota if longer-term load absorption is needed.

Only drop messages when business semantics permit data loss, such as certain types of best-effort telemetry; that policy must be explicitly documented.

## 5. Inbound Manual Flow Control Tied to Queue Capacity

When auto inbound flow control is enabled, gRPC automatically requests the next message using its default mechanism. If the application places messages into a queue and processes them asynchronously, the queue can fill up before workers keep pace.

With a server-side streaming handler, you can disable auto-request on **ServerCallStreamObserver** and request messages according to how many the application is ready to process:

~~~java
ServerCallStreamObserver<UploadChunk> inbound =
    (ServerCallStreamObserver<UploadChunk>) requestObserver;

inbound.disableAutoRequest();
inbound.request(1);
~~~

After finishing one chunk and freeing a slot, the application calls **request(1)** to receive another. If requesting **n** messages in advance, the queue capacity must be large enough for the number of messages permitted to arrive, plus any calculated headroom.

Important rules:

- Only request more when safe capacity is available.
- Never request more than the remaining capacity of the queue and workers.
- When the RPC is cancelled or has finished, stop requesting.
- If there are multiple workers, account for both messages currently being processed and messages sitting in the queue.

**request(n)** controls the number of inbound messages gRPC allows to be delivered to the application; it does not directly increase the HTTP/2 byte window. The transport still manages byte-level flow control separately.

## 6. Processing Inbound with One Consumer or Multiple Consumers

A single consumer usually makes it easy to preserve order:

~~~java
void consumeLoop() {
    while (!cancelled.get()) {
        UploadChunk chunk = inboundQueue.poll();
        if (chunk == null) {
            return;
        }

        process(chunk);
        requestNextMessage();
    }
}
~~~

In a real implementation, the worker should be woken up via an executor, semaphore, or signaling mechanism rather than a busy polling loop. When using manual flow control, **requestNextMessage()** must only be called after processing finishes and the queue has capacity.

Multiple consumers can increase throughput if messages are independent, but varying processing times can cause results to complete out of reception order. If the protocol requires ordering, use a single sequential consumer or attach sequence numbers and reorder results before emitting outbound messages.

## 7. Outbound Queue and Readiness

The outbound queue holds responses waiting to be sent when the business producer generates data faster than gRPC can transmit:

~~~java
BlockingQueue<UploadAck> outboundQueue =
    new ArrayBlockingQueue<>(64);
~~~

For server streaming or bidi streaming, obtain the **ServerCallStreamObserver** to check readiness:

~~~java
ServerCallStreamObserver<UploadAck> outbound =
    (ServerCallStreamObserver<UploadAck>) responseObserver;

outbound.setOnReadyHandler(this::scheduleDrain);
~~~

**isReady()** indicates that gRPC can currently accept another outbound message without exceeding the internal buffer threshold controlled by the transport. It does not mean the peer has received or processed the previous message.

When **isReady()** is false, stop draining and keep the remaining responses in the outbound queue. When readiness transitions to true, the on-ready handler wakes up the drain to continue sending.

~~~java
void drain() {
    while (!cancelled.get() && outbound.isReady()) {
        UploadAck next = outboundQueue.poll();
        if (next == null) {
            break;
        }
        outbound.onNext(next);
    }
}
~~~

This is the core algorithm; the application needs to invoke an initial drain if the observer is already ready, register the on-ready handler, and ensure the drain does not run concurrently on multiple threads. Do not use a loop waiting for **isReady()** to become true, as that wastes CPU.

## 8. Only One Thread Writes Outbound

**StreamObserver** is not an API designed for multiple producer threads to call **onNext**, **onError**, and **onCompleted** concurrently. Collect responses from producers into a queue and use a single drain executor or a single serialization mechanism to emit messages.

An orchestration pattern:

~~~java
private final AtomicBoolean draining = new AtomicBoolean();

void scheduleDrain() {
    if (!draining.compareAndSet(false, true)) {
        return;
    }

    writerExecutor.execute(() -> {
        try {
            while (!cancelled.get() && outbound.isReady()) {
                UploadAck next = outboundQueue.poll();
                if (next == null) {
                    break;
                }
                outbound.onNext(next);
            }
            completeIfInputFinishedAndQueueEmpty();
        } finally {
            draining.set(false);
            if (!cancelled.get()
                    && outbound.isReady()
                    && (!outboundQueue.isEmpty() || shouldComplete())) {
                scheduleDrain();
            }
        }
    });
}
~~~

Set the on-ready handler to call **scheduleDrain()**, and also call **scheduleDrain()** after a producer enqueues a response. The **draining** flag prevents multiple drain tasks from running concurrently. All terminal calls such as **onCompleted()** or **onError()** must also be serialized with **onNext()** and emitted strictly once.

The snippet is an orchestration skeleton; **completeIfInputFinishedAndQueueEmpty()** must check completion state using synchronized/atomic variables and only finish when the producer is done, the queue is empty, and no message is currently being sent.

## 9. Bounding Queues by Count and Byte Size

Capacity by message count is necessary but may not be sufficient. 64 small messages occupy little memory, whereas 64 messages carrying multi-megabyte payloads can spike the heap.

You should consider simultaneously:

- **Maximum message count**: maximum number of messages held.
- **Maximum queued bytes**: total estimated size of pending messages.
- **Maximum message size**: size limit for a single message.
- **Maximum in-flight work**: number of tasks currently being processed concurrently.

With Protobuf Java, **getSerializedSize()** can be used to estimate the serialized size of a message. This is a useful estimate for the payload budget; it does not include all object overhead, queue nodes, and runtime copies.

When enqueueing, check both the count and the byte budget. When dequeueing or finishing processing, release the corresponding budget. Ensure counters are updated atomically or protected by a lock so multiple producers do not exceed the quota together.

## 10. Full Queue: Choosing a Policy Based on Semantics

No single overflow policy fits every RPC:

| Policy | When appropriate | Risk |
| --- | --- | --- |
| **Backpressure** | Producer can wait or only send more when requested | Requires proper coordination of demand/readiness. |
| **Reject** | Load exceeding capacity cannot be handled | Client receives an error and may need to retry. |
| **Drop newest** | Newer data is less important; system prioritizes keeping pending history | Loss of recent data. |
| **Drop oldest** | Only the latest state is needed, e.g. snapshots/telemetry | Loss of older unprocessed events. |
| **Persist** | Longer-term load absorption is required and durability is needed | Increases complexity, latency, and storage cost. |

For business commands, payments, or upload data, dropping is usually inappropriate. You can return **RESOURCE_EXHAUSTED** so the client adjusts its rate or retries under a bounded policy. For best-effort telemetry, controlled dropping may be acceptable if there is a metric counting dropped messages.

Never retry infinitely when a queue is full. Retries require deadlines, backoff, a retry limit, and idempotent semantics to avoid amplifying load.

## 11. Message Ordering and State Synchronization

gRPC preserves message order within one direction of a stream. However, the application can break that order if:

- Multiple callbacks/producers add responses to a queue without ordering rules.
- Multiple workers process in parallel and finish out of order.
- Multiple threads call **onNext()** directly on the same observer.

If ordering is a business requirement:

1. Attach a sequence number at the source if order verification is needed.
2. Choose a single sequential producer/consumer, or use a reorder buffer.
3. Have only one drain writer for the outbound observer.
4. Do not emit a response with a later sequence number while an earlier response is still pending.

If messages are independent and order does not matter, parallel processing is possible, but you still need to serialize outbound callbacks and define how the client correlates results.

## 12. Completion, Errors, and Cancellation

Queues must have a lifecycle tied to the RPC:

- **onCompleted inbound**: no more request messages. Workers can continue processing already-received messages; only complete outbound when work is done and the outbound queue has drained.
- **onError inbound**: stop accepting more data, apply the policy to pending work, and terminate the call with an appropriate error.
- **cancel**: stop the producer, cancel cancellable tasks, and release queues and byte counters.
- **deadline exceeded**: do not continue generating useless responses after the call has expired.
- **outbound terminal**: never call **onNext()** after **onCompleted()** or **onError()**.

On the server, you can register **setOnCancelHandler(...)** on **ServerCallStreamObserver** to stop work when the client cancels the call. The handler should not block for long; signal the worker/executor to perform cleanup.

When the call ends, clear any remaining pending messages if semantics allow. If results must be retained for a client to resume after reconnecting, use durable storage and an application-layer cursor/ack rather than keeping an in-memory queue tied to a finished RPC.

## 13. Testing and Observing Queues

Tests should verify:

1. The inbound queue does not exceed its capacity when the producer sends rapidly.
2. Manual flow control only requests more when a safe slot is available.
3. The outbound producer does not call **onNext()** when the drain is not permitted to run.
4. When **isReady()** flips false then true, the drain pauses and resumes without losing or duplicating messages.
5. Multiple producers do not cause concurrent **onNext()** calls.
6. **onCompleted**, **onError**, cancellation, and deadlines do not leave workers or queues alive indefinitely.
7. A full queue enforces the documented policy accurately.

Useful metrics:

- Current message count and capacity of each queue.
- Number of queued bytes.
- Average and percentile wait times in the queue.
- Number of queue-full events, rejected messages, or dropped messages.
- Number of active workers and pending tasks.
- Duration outbound is not ready and number of drain wakeups.
- Number of RPCs cancelled or terminated due to deadlines.

Do not log full message contents to diagnose queues. Use request IDs, sizes, sequence numbers, and aggregated metrics; avoid exposing sensitive data and avoid increasing load through logging.

## 14. Common Mistakes

| Mistake | Consequence | How to handle |
| --- | --- | --- |
| Using an unbounded queue | Heap grows uncontrollably when producer outpaces consumer | Use a bounded queue and byte budget. |
| Blocking **onNext()** callback with long **put()** | Ties up the RPC receiving executor, slowing other calls | Use **offer()** and an overflow policy. |
| Auto inbound request while worker is slow | Queue can fill before processing catches up | Use manual flow control or bound queue/workers. |
| Sending outbound regardless of **isReady()** | Increases buffers and latency | Drain according to the readiness callback. |
| Multiple threads calling observer directly | Race conditions or invalid terminal ordering | Use a single sequential outbound writer. |
| Bounding only by message count | Large payloads still spike memory usage | Bound both message count and bytes. |
| Completing response immediately when inbound completes | Drops remaining work or responses still in the queue | Wait for workers to finish and the outbound queue to empty. |
| Ignoring cancellation/deadlines | Continues processing and holding resources after call ends | Signal workers to stop and clean up. |

## 15. Practice Exercises

Design a bidirectional RPC that receives image processing commands and returns statuses:

1. Define **ProcessImageRequest** and **ProcessImageUpdate**.
2. Design an inbound queue with finite capacity; explain how to choose capacity based on message count and payload size.
3. Use server-side manual flow control to request the next message only when a worker has freed a slot.
4. Put updates into an outbound queue and drain only when **ServerCallStreamObserver.isReady()** is true.
5. Guarantee a single sequential writer calls **onNext()**, **onError()**, and **onCompleted()**.
6. Define behavior when the queue is full, the client cancels the call, and the deadline expires.
7. Propose metrics to detect slow consumers or stalled outbound readiness.

**Completion criteria:** design two independent bounded queues, regulate inbound demand and outbound readiness, preserve required ordering, and release resources when the RPC terminates.

## 16. Key Takeaways

- The inbound queue holds messages awaiting processing; the outbound queue holds responses awaiting transmission.
- Application queues are a separate layer and do not replace HTTP/2 flow control or gRPC internal buffers.
- Use bounded queues, limit both message count and bytes, and clearly define overflow policies.
- Throttle inbound via manual flow control and **request(n)** when demand must match real capacity.
- Throttle outbound via **isReady()** and an on-ready handler; use only a single sequential writer for the observer.
- Preserve ordering when business rules require it; parallel workers can finish results out of order.
- Completion, errors, cancellation, and deadlines must terminate workers, queues, and all related resources.

Designing bounded inbound and outbound message queues helps Spring gRPC services absorb speed mismatches between producers and consumers, maintain data ordering, and protect memory in long-lived streaming RPCs.
