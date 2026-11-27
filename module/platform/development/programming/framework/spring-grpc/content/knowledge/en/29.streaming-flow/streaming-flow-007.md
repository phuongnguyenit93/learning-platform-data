# Never Call onNext After onError or onCompleted

## Learning Objectives

After this lesson, you will be able to:

- Describe the valid lifecycle of a gRPC stream observer.
- Distinguish between open, completed successfully, failed with error, and cancelled states.
- Explain why every `onNext` call must stop after `onError` or `onCompleted`.
- Detect race conditions when multiple workers send messages or terminate an RPC concurrently.
- Serialize callbacks and guarantee strictly one terminal event.
- Safely handle cancellation, deadlines, and asynchronous errors in Spring gRPC services.

## 1. The StreamObserver Lifecycle Rule

In gRPC Java, **StreamObserver<T>** receives messages through three callbacks:

- **onNext(T)**: delivers a message while the stream is still active.
- **onError(Throwable)**: terminates the stream due to an error.
- **onCompleted()**: terminates the stream successfully.

A stream can receive many `onNext` calls, but only one termination. Once `onError` or `onCompleted` has been called, the sender must treat the observer as finished and never invoke any further callbacks on that observer.

This rule applies per RPC direction. In server-streaming, the service sends responses via the response observer. In client-streaming, the client sends requests via the request observer returned by the async stub. Do not confuse the request-receiving observer on the server with the response-sending observer: each observer has a distinct role and a distinct caller.

## 2. State Machine of a Stream

The valid lifecycle can be represented by three primary states:

~~~mermaid
stateDiagram-v2
  [*] --> OPEN
  OPEN --> OPEN: onNext
  OPEN --> COMPLETED: onCompleted
  OPEN --> FAILED: onError
  COMPLETED --> [*]
  FAILED --> [*]
~~~

**OPEN** is the only state where `onNext` is permitted. **COMPLETED** and **FAILED** are both terminal states. There is no valid transition from a terminal state back to OPEN or to another terminal state.

For example, the following sequence is valid:

~~~text
onNext(A) -> onNext(B) -> onNext(C) -> onCompleted()
~~~

The following sequences are invalid:

~~~text
onCompleted() -> onNext(D)
onError(error) -> onNext(D)
onCompleted() -> onError(error)
onError(error) -> onCompleted()
~~~

In practice, some bugs only surface under multiple asynchronous callbacks. Therefore, manage stream state at a single coordination point instead of relying on each worker remembering whether the stream has ended.

## 3. Why Is Calling onNext After a Terminal Event an Error?

Once an observer receives `onCompleted` or `onError`, gRPC considers that stream direction closed. A subsequent `onNext` violates the contract and can cause:

- Runtime exceptions or internal call errors.
- Messages being dropped or not delivered as the application expects.
- Hard-to-trace error logs because producers keep running after the RPC has ended.
- Leaked resources because workers fail to stop.
- Non-deterministic outcomes when multiple threads send or terminate the stream concurrently.

Do not rely on a particular transport happening to ignore extra callbacks. Correct behavior must be guaranteed at the application layer before invoking the observer.

## 4. The Two Terminal Events Have Different Meanings

| Callback | Meaning | When to use |
| --- | --- | --- |
| **onCompleted()** | Successful completion, no more messages | The producer has finished and all required responses have been emitted. |
| **onError(Throwable)** | Termination due to failure | A business, validation, upstream, or transport error requires terminating the RPC. |

Never call both to "make sure" the stream finishes. You must choose strictly one terminal event. Once `onCompleted` has been called, do not call `onError` to report a late-discovered error. Once `onError` has been called, do not call `onCompleted` in a `finally` block.

An error discovered after the stream has already completed can be recorded via logs/metrics or handled in another workflow; it cannot alter the terminal outcome of an already-finished RPC.

## 5. Common Anti-Patterns with Asynchronous Processing

Unsafe example:

~~~java
void streamPrices(StreamObserver<PriceUpdate> observer) {
    executor.execute(() -> observer.onNext(loadFirstPage()));

    if (isSourceFinished()) {
        observer.onCompleted();
    }
}
~~~

The producer is dispatched to an executor, yet the current thread may call `onCompleted` immediately if the source reports finished. The worker later executes and calls `onNext` on an already-terminated observer.

Another bug is calling `onError` in `catch` and then calling `onCompleted` in `finally`:

~~~java
try {
    observer.onNext(buildResponse());
} catch (RuntimeException ex) {
    observer.onError(ex);
} finally {
    observer.onCompleted(); // Wrong: may be called after onError.
}
~~~

A `finally` block is suitable for releasing resources, not for unconditionally emitting `onCompleted`. Terminal events must belong to a single exclusive control branch.

## 6. Race Conditions When Multiple Threads Send Concurrently

Checking a standalone boolean before calling the observer can still fail:

~~~java
if (!terminated.get()) {
    observer.onNext(message);
}
~~~

The following interleaving can occur:

1. Worker A reads `terminated` as `false`.
2. Worker B calls `onCompleted` and sets `terminated` to `true`.
3. Worker A proceeds to call `onNext` after the stream has already completed.

`AtomicBoolean` only makes reading/writing the flag itself thread-safe; it does not make the compound operation "check state then invoke observer" atomic. You must serialize the state check and callback invocation as a single atomic unit.

Another cause is two workers emitting terminal events concurrently. If both detect an error, or one worker completes while another reports an error, the observer can receive two competing terminal callbacks.

## 7. Guarding the Observer with a Serial Gate

For a simple sending flow, route all calls through an emitter with synchronized state:

~~~java
final class SafeEmitter<T> {
    private enum State {
        OPEN, COMPLETED, FAILED, CANCELLED
    }

    private final StreamObserver<T> delegate;
    private State state = State.OPEN;

    SafeEmitter(StreamObserver<T> delegate) {
        this.delegate = delegate;
    }

    synchronized boolean next(T value) {
        if (state != State.OPEN) {
            return false;
        }
        try {
            delegate.onNext(value);
            return true;
        } catch (RuntimeException ex) {
            state = State.FAILED;
            throw ex;
        }
    }

    synchronized boolean complete() {
        if (state != State.OPEN) {
            return false;
        }
        state = State.COMPLETED;
        delegate.onCompleted();
        return true;
    }

    synchronized boolean fail(Throwable error) {
        if (state != State.OPEN) {
            return false;
        }
        state = State.FAILED;
        delegate.onError(error);
        return true;
    }

    synchronized boolean cancel() {
        if (state != State.OPEN) {
            return false;
        }
        state = State.CANCELLED;
        return true;
    }
}
~~~

All producers must use **SafeEmitter** and never retain or call `delegate` directly elsewhere. Synchronization spans both the state check and the callback so two threads cannot slip an `onNext` in after a terminal event. Observer callbacks should execute quickly; never perform database queries or long work inside the synchronized block.

If callbacks may run long or you need to avoid holding a lock while calling external code, use a sequential executor as the sole place emitting all events. In that case, checking state and enqueueing events must also be synchronized; do not merely submit callbacks to an executor while allowing producers to enqueue `onNext` after a terminal task has already been queued.

A `false` return value from `next`/`complete`/`fail` indicates the observer is already terminal or cancelled. The application should record the late emission as a logic error, stop the producer, and not attempt to invoke `delegate` again.

## 8. Emitting Responses and Terminating in the Right Order

A server-streaming handler may generate multiple responses asynchronously. The orchestration flow should:

1. Generate the response.
2. Send the response through the emitter while the stream is still OPEN.
3. When the source finishes, ask the emitter to complete.
4. When an error occurs before a terminal event, ask the emitter to fail.
5. Once one terminal request wins, subsequent terminal requests emit no further callbacks.

Example:

~~~java
void publishPrice(
        SafeEmitter<PriceUpdate> emitter,
        PriceUpdate update) {

    if (!emitter.next(update)) {
        stopPriceProducer();
        recordLateEmission();
    }
}

void finishPrices(SafeEmitter<PriceUpdate> emitter) {
    emitter.complete();
}

void failPrices(
        SafeEmitter<PriceUpdate> emitter,
        Throwable error) {
    emitter.fail(Status.INTERNAL
        .withDescription("Price stream failed")
        .withCause(error)
        .asRuntimeException());
}
~~~

In production code, choose a status matching the actual cause instead of always using `INTERNAL`. Do not include sensitive details or full payloads in the status description.

## 9. Combining Readiness with Terminal State

Server-streaming often uses **ServerCallStreamObserver.isReady()** and **setOnReadyHandler()** to avoid pushing too many responses into gRPC buffers. Readiness does not change terminal rules:

- Only drain the queue when the observer is ready and the emitter is still OPEN.
- If the emitter is already terminal, cancel the drain task and do not call `onNext`.
- Only request completion once the queue is empty and the producer has finished.
- If the producer fails before finishing, request fail instead of complete.

Do not call `onCompleted` just because the queue is temporarily empty; the producer may still be creating the next response. There must be an explicit signal indicating the source has finished.

## 10. Distinguishing Terminal Events from Cancellation

A client cancelling the RPC or a deadline expiring can cause the server to receive a cancellation signal. This is not a reason to keep sending `onNext`, nor should you try to invoke extra `onError`/`onCompleted` calls on an already-cancelled call.

With **ServerCallStreamObserver**, register a cancellation handler:

~~~java
ServerCallStreamObserver<PriceUpdate> response =
    (ServerCallStreamObserver<PriceUpdate>) responseObserver;

SafeEmitter<PriceUpdate> emitter = new SafeEmitter<>(response);

response.setOnCancelHandler(() -> {
    emitter.cancel();
    stopPriceProducer();
    clearPendingWork();
});
~~~

Cancellation closes the message-emitting path and stops the data source. Do not send a second terminal callback merely to echo a cancellation already signaled by the transport. Cleanup of queues, subscriptions, and resources must be idempotent when invoked multiple times.

## 11. Roles of Client and Server Observers

In client-streaming or bidirectional streaming, identify who is calling which observer:

| Location | Observer | Who calls onNext? |
| --- | --- | --- |
| Server receiving request stream | Request observer returned by service | gRPC invokes the service's callbacks when the client sends requests. |
| Server sending response stream | Response observer passed into service | Service calls `onNext`/`onError`/`onCompleted`. |
| Client sending request stream | Request observer returned by async stub | Client calls `onNext`/`onError`/`onCompleted`. |
| Client receiving response stream | Response observer provided by client | gRPC invokes the client's callbacks. |

The rule against calling `onNext` after a terminal event applies to the observer on which the application is emitting messages. For observers receiving callbacks from gRPC, the application handles those callbacks per contract and does not invoke them itself as if they were sending channels.

## 12. Testing Terminal Lifecycle

Tests should cover:

1. Multiple `onNext` calls followed by strictly one `onCompleted`.
2. Multiple `onNext` calls followed by strictly one `onError`.
3. Calling `next` after `complete` forwards no further messages to the delegate.
4. Calling `next` after `fail` forwards no further messages to the delegate.
5. Two threads simultaneously requesting `complete`/`fail`, yet only one terminal event is emitted.
6. A race between `next` and `complete` produces no callbacks after the terminal event.
7. Cancellation stops the producer and prevents all subsequent emissions.
8. Worker errors do not cause `finally` to invoke `onCompleted` a second time.

JUnit 5 example with a mock observer:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.stub.StreamObserver;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class SafeEmitterTest {
    @Test
    void doesNotEmitAfterCompletion() {
        List<String> events = new ArrayList<>();
        StreamObserver<String> delegate = new StreamObserver<>() {
            public void onNext(String value) {
                events.add("next:" + value);
            }
            public void onError(Throwable error) {
                events.add("error");
            }
            public void onCompleted() {
                events.add("completed");
            }
        };

        SafeEmitter<String> emitter = new SafeEmitter<>(delegate);
        assertTrue(emitter.next("first"));
        assertTrue(emitter.complete());
        assertFalse(emitter.next("late"));
        assertFalse(emitter.fail(new IllegalStateException("late error")));

        assertEquals(
            List.of("next:first", "completed"),
            events);
    }
}
~~~

This test verifies the wrapper does not invoke the delegate after completion. Add multithreaded tests using a latch/barrier to force a race between `next` and `complete`/`fail`; valid outcomes must exhibit a linear order with no `next` after a terminal event.

## 13. Common Mistakes

| Mistake | Consequence | How to handle |
| --- | --- | --- |
| Calling `onCompleted` inside `finally` | May run after `onError` | Emit terminal events in a single control branch only. |
| Checking `AtomicBoolean` then calling `onNext` outside | Race between check and terminal callback | Synchronize both check and callback emission or use a serial executor. |
| Multiple workers calling the observer | Two terminal events or `next` after terminal | Use a single sequential callback gate. |
| Continuing producer after cancellation | Generates messages with nowhere to go and holds resources | Stop producer, cancel upstream, and clean up. |
| Calling `onError` after `onCompleted` for late errors | Violates observer contract | Record error outside the RPC or handle in another workflow. |
| Treating an empty queue as producer completion | Completes prematurely, dropping later responses | Track source completion state separately. |
| Calling `onNext` directly from multiple callbacks | Out-of-order messages and hard-to-control concurrency | Enqueue and use a single writer. |
| Swallowing late emissions silently without telemetry | Logic bugs stay hidden | Record metrics/logs and stop the producer. |

## 14. Practice Exercises

A server-streaming service emits report processing progress:

1. Build an emitter with states OPEN, COMPLETED, FAILED, and CANCELLED.
2. Have multiple workers generate progress updates while only one gate is permitted to emit responses.
3. When the report finishes, emit `onCompleted` strictly once after the final update.
4. When a worker fails before completion, emit `onError` and do not emit `onCompleted`.
5. Deliberately trigger a late emission after a terminal event and verify the delegate receives no `onNext`.
6. Cancel the client mid-stream; verify the producer stops and no redundant terminal callback is emitted.
7. Write a multithreaded race test between `onNext` and `onCompleted`.

**Completion criteria:** no `onNext` after any terminal event, strictly one terminal event, races serialized, and cancellation stops background work.

## 15. Key Takeaways

- **onNext** is only valid while the observer is OPEN.
- **onError** and **onCompleted** are terminal events; only one may be emitted, with no subsequent callbacks.
- Checking state separately with `AtomicBoolean` is insufficient if another thread can interleave between the check and callback.
- Serialize all `onNext`/terminal events with an appropriately scoped lock or a serial executor.
- Never call `onCompleted` inside `finally`; cleanup and RPC termination are separate responsibilities.
- Cancellation/deadlines must stop the producer and prevent further message emissions without creating a second terminal callback.
- Test success paths, error paths, late emissions, and multithreaded races.

Respecting the StreamObserver lifecycle keeps Spring gRPC services from invoking callbacks after a stream has closed, eliminates races between workers, and guarantees consistent streaming results for clients.
