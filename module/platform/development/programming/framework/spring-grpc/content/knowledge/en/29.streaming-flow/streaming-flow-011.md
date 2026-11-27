# Stream Observer Thread Safety

In gRPC Java, `StreamObserver` is the asynchronous API for sending and receiving messages. A stream may have data produced by multiple parts of an application while the transport continues sending/receiving messages and handling cancellation. If multiple threads concurrently call `onNext`, `onError`, or `onCompleted` on the same observer, messages can interleave, terminal signals can execute out of order, or the call may close while producers are still sending.

Core rule: **an observer that the application actively writes to must have a serialized write path**. gRPC dispatches receiving callbacks for a single call sequentially, yet callbacks can run on different threads over time; different RPCs can also run concurrently. Therefore, distinguish observers used for sending from observers receiving callbacks, and manage separate state per call.

## 1. Identifying Who Writes to the Observer

The name `StreamObserver` appears in both directions. Identify which side calls the methods:

| Location | Who calls `onNext`? | Threading rule |
| --- | --- | --- |
| Server returning responses from unary/server-streaming handler | Application calls response observer | Application must serialize writes if there are multiple producers |
| Server receiving requests in client-streaming/bidi | gRPC calls observer returned by service | Callbacks for the same call are serialized by gRPC; do not assume a fixed thread |
| Client sending requests in client-streaming/bidi | Application calls request observer returned by async stub | Application must serialize writes |
| Client receiving responses from async stub | gRPC calls response observer provided by application | Callbacks for the same call are serialized by gRPC; other calls may still run concurrently |

Client-streaming example:

```java
StreamObserver<ImportRequest> requestObserver =
        asyncStub.importProducts(new StreamObserver<ImportSummary>() {
            @Override
            public void onNext(ImportSummary summary) {
                handleSummary(summary);
            }

            @Override
            public void onError(Throwable error) {
                handleFailure(error);
            }

            @Override
            public void onCompleted() {
                handleCompletion();
            }
        });

// The application writes requests to the observer returned by the stub.
requestObserver.onNext(firstBatch);
requestObserver.onCompleted();
```

`requestObserver` is the application's write endpoint. If multiple workers call it concurrently, the application is responsible for synchronization. The observer receiving `ImportSummary` is called back by gRPC for that call; you do not need to spawn extra threads just to invoke this callback.

## 2. Why Does Concurrent Writing Cause Bugs?

An observer has three primary operations:

- `onNext(value)`: sends a message.
- `onError(error)`: terminates the stream with an error.
- `onCompleted()`: terminates the stream successfully.

These operations must follow a consistent order. Common dangerous situations:

1. Two producers call `onNext` at the same time; messages may lose business order.
2. One thread calls `onCompleted` while another thread is still calling `onNext`.
3. One thread calls `onError` after another thread has already completed via `onCompleted`.
4. A producer holds a reference to the observer after the RPC has been cancelled or its deadline has expired.

`onError` and `onCompleted` are terminal signals. After either has been sent, never send another message or another terminal signal. Synchronization must cover both messages and termination operations, not just `onNext` alone.

## 3. Simple Approach: Serializing with a Lock

If multiple threads must write directly to the same observer, wrap the observer in a synchronizing decorator. All write operations and terminal signals share one monitor:

```java
import io.grpc.stub.StreamObserver;

public final class SerializedStreamObserver<T>
        implements StreamObserver<T> {

    private final StreamObserver<T> delegate;
    private boolean terminated;

    public SerializedStreamObserver(StreamObserver<T> delegate) {
        this.delegate = delegate;
    }

    @Override
    public synchronized void onNext(T value) {
        if (terminated) {
            throw new IllegalStateException("stream is already terminated");
        }
        delegate.onNext(value);
    }

    @Override
    public synchronized void onError(Throwable error) {
        if (terminated) {
            return;
        }
        terminated = true;
        delegate.onError(error);
    }

    @Override
    public synchronized void onCompleted() {
        if (terminated) {
            return;
        }
        terminated = true;
        delegate.onCompleted();
    }
}
```

This wrapper guarantees no two concurrent calls enter the delegate and no `onNext` is sent after a terminal signal. It is suitable when write operations are short and the number of producers is small.

A lock only guarantees serialization in the order threads acquire the monitor; it **does not guarantee deterministic business ordering** among competing producers. If messages must follow a sequence, assign sequence numbers where data is produced and sort or route through a single writer. Never perform database/network I/O while holding the lock.

## 4. Recommendation for Multiple Producers: A Single Sequential Writer

When multiple workers generate messages, a more controllable design is having them send messages into a queue while a single consumer invokes the observer. The queue must be bounded:

```java
BlockingQueue<ImportRequest> queue =
        new ArrayBlockingQueue<>(256);

ExecutorService streamWriter =
        Executors.newSingleThreadExecutor();

streamWriter.execute(() -> {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            ImportRequest message = queue.take();
            requestObserver.onNext(message);
        }
    } catch (InterruptedException interrupted) {
        Thread.currentThread().interrupt();
        requestObserver.onError(interrupted);
    }
});
```

This is an illustrative skeleton; production needs a protocol to stop the writer and emit the terminal signal strictly once. When a producer calls `queue.offer(message)` and the queue is full, there must be a clear policy: wait within bounds, reject the producer, throttle the source, or cancel the stream. Never use an unbounded queue and never silently drop messages.

Only the writer may call `requestObserver.onNext`, `onError`, or `onCompleted`. When all producers finish, send a terminal command through the same queue to guarantee it is processed after already-received messages. If order across multiple producers matters, assign sequence numbers before enqueueing; the order threads insert messages into the queue may not match business order.

## 5. Receiving Callbacks Have No Thread Affinity

On the receiving side, gRPC invokes observer callbacks for each call in order, but does not guarantee all callbacks of that call always execute on the same thread. Callbacks of different RPCs can run concurrently.

Therefore:

- Do not rely on custom `ThreadLocal` variables to hold state across callbacks.
- Do not store per-call data in mutable fields of singleton services/clients.
- Use local variables or a dedicated state object for each RPC.
- If a callback offloads work to a custom executor, propagate gRPC Context and OpenTelemetry Context when needed.
- If a callback updates a cache or counter shared across multiple RPCs, that data structure must be thread-safe.

Example creating separate state for each call:

```java
public void getProduct(
        GetProductRequest request,
        StreamObserver<ProductEvent> responseObserver) {

    AtomicLong eventCount = new AtomicLong();
    // eventCount belongs only to the current RPC.
    eventPublisher.subscribe(event -> {
        eventCount.incrementAndGet();
        responseObserver.onNext(toProto(event));
    });
}
```

The example above still needs to serialize `responseObserver` if `eventPublisher` calls subscribers from multiple threads. `AtomicLong` only protects the counter; it does not make `responseObserver.onNext` thread-safe.

## 6. Flow Control and Readiness Must Also Be Coordinated

Serializing calls does not solve backpressure on its own. Producers can outpace the network or consumer; if you keep enqueueing messages, memory grows.

In server streaming/bidi, the response observer can be a `ServerCallStreamObserver`. You can check `isReady()` and register `setOnReadyHandler` to emit further only when the transport is ready:

```java
if (responseObserver instanceof ServerCallStreamObserver<?> rawStream) {
    @SuppressWarnings("unchecked")
    ServerCallStreamObserver<ProductEvent> serverStream =
            (ServerCallStreamObserver<ProductEvent>) rawStream;
    serverStream.setOnReadyHandler(() -> {
        if (serverStream.isReady() && !serverStream.isCancelled()) {
            drainBoundedQueue(serverStream);
        }
    });
    serverStream.setOnCancelHandler(this::stopProducer);
}
```

This illustrative snippet needs to be set up in the handler before starting to send messages. `drainBoundedQueue` must ensure only one drain loop writes to the observer at a time, check `isReady()` before sending further, and run no blocking I/O inside the on-ready callback.

In client streaming/bidi, `ClientCallStreamObserver` provides `isReady()` and `setOnReadyHandler` for the request stream. You can use `ClientResponseObserver.beforeStart` to obtain request stream control before sending. Readiness is a flow-control signal, not a synchronization lock; a sequential writer is still required.

## 7. Terminal Signals, Cancellation, and Deadlines

A stream can terminate via completion, error, cancellation, or deadline:

| Situation | What the producer must do |
| --- | --- |
| All messages sent | Send `onCompleted` strictly once |
| Business error | Send `onError` with an appropriate status |
| Client cancels stream | Stop producer and release queue/state |
| Deadline expires | Stop work that is no longer useful; do not keep enqueueing endlessly |
| Queue full | Apply backpressure or fail/cancel per policy |

On the server side, you can use `ServerCallStreamObserver.isCancelled()` and `setOnCancelHandler` to stop the emitting source. On the client side, retain the ability to cancel the call if the application no longer needs results. RPC cancellation does not automatically stop every Java task the application has submitted; producers need their own cancellation token/flag and must check it in loops.

Never call `onCompleted` concurrently from an `onError` callback. Have a single place decide terminal state, such as a per-call state machine with OPEN, COMPLETED, FAILED, or CANCELLED states. Transition state via atomic compare-and-set or a lock so only one termination path wins.

## 8. Common Implementation Mistakes

- Sharing a single request observer across multiple different RPCs.
- Letting multiple producers call `onNext` concurrently without serialization.
- Synchronizing only `onNext` while leaving `onCompleted` or `onError` outside the lock.
- Thinking that `AtomicLong` or `volatile` makes an observer thread-safe.
- Sending a terminal signal and continuing to emit messages.
- Using an unbounded queue for a streaming producer.
- Relying on `isReady()` as a lock instead of coordinating readiness with a single writer.
- Storing an observer in a singleton field and accidentally reusing it for the next call.
- Failing to stop producers when the client cancels or the deadline expires.

A dedicated observer per RPC and a single sequential writer per stream limit state scope, making it easier to reason about and test.

## 9. Testing Stream Observer Thread Safety

Tests must create real contention between producers and terminal signals, rather than just calling the observer sequentially on a single thread:

| Test case | What to verify |
| --- | --- |
| Multiple producers sending messages | Delegate is never invoked concurrently |
| Producer and completion racing | No messages after terminal signal |
| Error and completion racing | Strictly one terminal signal sent |
| Multi-producer sequence | Business ordering preserved per chosen rule |
| Queue full | Producer experiences backpressure or stream terminates per policy, with no silent message loss |
| Server not ready | Writer pauses drain and resumes on on-ready |
| Client cancel/deadline | Producer stops and queue is released |
| Two concurrent streams | Observers and state are not cross-shared |
| Callbacks on different threads | Required context/state remains accurate |

You can use a fake `StreamObserver` that records the maximum concurrent call count and message order. Key assertions are `maxConcurrentCalls` equals 1, terminal count does not exceed 1, and no `onNext` after terminal. For flow control, use an in-process server/channel and stream many messages to verify queues, readiness, and cancellation.

## 10. Implementation Checklist

- [ ] Identify whether the observer is the application's write endpoint or receives callbacks from gRPC.
- [ ] Each RPC has its own observer and state.
- [ ] All write calls to the same observer are serialized.
- [ ] Serialize `onNext`, `onError`, and `onCompleted` together.
- [ ] Use a single writer/serial executor when there are multiple producers or deterministic order is required.
- [ ] Queues are bounded and have an overflow policy.
- [ ] Readiness/flow control is coordinated with the writer, not used as a replacement for synchronization.
- [ ] Stop producers on cancel, deadline, or terminal signal.
- [ ] Do not assume callbacks across multiple RPCs run on the same thread.
- [ ] Never store per-call observers/state in mutable singleton fields.
- [ ] Have concurrency tests for message ordering, terminal races, overload, and cancellation.

**Self-Check**

**Question 1.** Can multiple threads call `onNext` concurrently on a single `StreamObserver`?

*Answer:* They should not. Observers are not guaranteed thread-safe for application write calls; writes must be serialized with a lock or a single writer.

**Question 2.** Does gRPC guarantee that receiving callbacks for the same call always run on the same thread?

*Answer:* No. Callbacks for the same call are dispatched sequentially, yet can run on different threads over time. Callbacks for multiple RPCs can also run concurrently.

**Question 3.** Why must `onCompleted` and `onError` also be synchronized?

*Answer:* They are terminal signals. If they do not share the same synchronization mechanism as `onNext`, one thread could close the stream while another thread is still sending a message or sending a second terminal signal.

**Question 4.** Does `isReady()` replace a lock or single writer?

*Answer:* No. It reports transport flow-control status, not producer serialization. The application still needs a single writer or synchronization.

**Question 5.** When a client cancels, do already-running Java producers stop automatically?

*Answer:* Not necessarily. A cancellation handler/token is needed to stop producers, stop enqueueing, and release queues/state.

Stream observer thread safety depends on write-flow ownership and how calls terminate. Keep one sequential writer per stream, serialize both messages and terminal signals, bound queues with flow control, and stop producers on cancel/deadline; streaming in Spring gRPC will then avoid races, out-of-order delivery, and emitting messages after a call has ended.
