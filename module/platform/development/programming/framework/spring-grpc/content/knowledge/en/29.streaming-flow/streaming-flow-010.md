# Concurrency in Callbacks

## Learning Objectives

After this lesson, you will be able to:

- Understand that gRPC callbacks execute on runtime-managed executors and do not depend on a fixed thread.
- Distinguish sequential callbacks from asynchronous work offloaded by the application to a worker pool.
- Protect per-RPC state and avoid sharing mutable state across calls.
- Serialize operations on `StreamObserver`, preserving message ordering and terminal events.
- Use bounded executors, manual flow control, and readiness to control concurrency and backpressure.
- Propagate gRPC Context, handle cancellation, and test race conditions in Spring gRPC.

## 1. gRPC Callbacks Run in an Asynchronous Model

With the async API, gRPC invokes callbacks such as `onNext`, `onError`, and `onCompleted` when messages or termination events arrive. Callbacks execute on executors managed by the gRPC runtime/transport; the exact thread can vary between invocations. Do not rely on thread names, custom thread-locals, or assume callbacks always run on the thread that created the stub/server.

Callbacks are the bridge between transport and application. If a callback performs long database queries, synchronous HTTP calls, lock waits, or heavy computations, it can tie up the RPC-handling executor and slow down other calls.

In **SPRING_GRPC**, Spring service beans are typically shared across many RPCs. Therefore, callback processing must separate per-call state from shared dependencies such as repositories or service beans. Never store buffers, sequence numbers, or terminal flags of an individual RPC in shared mutable fields of a singleton service.

## 2. Sequential Callbacks Do Not Mean Sequential Application Workers

The transport dispatches callbacks according to the call contract, yet when the application submits each message to a multi-threaded pool, those tasks can run concurrently and finish out of order.

For example:

~~~text
gRPC callback: onNext(A) -> onNext(B) -> onNext(C)
                         |           |           |
                         v           v           v
                    worker-1     worker-2     worker-3
                         |           |           |
                         +---- B completes before A ----+
~~~

Callback arrival order does not automatically guarantee processing order when workers run in parallel. If message B depends on A, parallel execution can corrupt business state even though gRPC delivered messages in stream order.

Before choosing an executor, clearly determine:

- Are messages independent enough to be processed in parallel?
- Is preserving arrival order and response order required?
- How many concurrent tasks is a single RPC allowed to have running?
- What capacity and byte budget does the worker queue have?

## 3. Keeping Separate State per RPC

Spring services are usually singletons. Variables such as `currentUpload`, `lastSequence`, `terminated`, or `pendingMessages` must not be mutable fields on the service if they belong to a specific call.

Create a dedicated session object for each RPC:

~~~java
final class UploadCallState {
    final String uploadId;
    final AtomicBoolean terminated = new AtomicBoolean();
    final AtomicLong nextSequence = new AtomicLong();
    final BlockingQueue<UploadChunk> pending =
        new ArrayBlockingQueue<>(32);

    UploadCallState(String uploadId) {
        this.uploadId = uploadId;
    }
}
~~~

The handler creates state when the RPC starts and closes it when the call ends. Shared dependencies such as `UploadService`, repositories, and bounded worker pools can be injected into the service; per-call mutable data lives inside `UploadCallState`.

Never use `ThreadLocal` to hold RPC state across callbacks. Callbacks may run on different threads, and thread pools reuse threads across different calls.

## 4. Keeping Callbacks Short and Offloading Heavy Work to Workers

Callbacks should do small work with predictable duration:

1. Check call state and basic input preconditions.
2. Put the message into a bounded queue or submit a task to an executor.
3. Return control quickly to the runtime.

Illustrative example:

~~~java
@Override
public void onNext(UploadChunk chunk) {
    if (state.terminated.get()) {
        return;
    }

    if (!state.pending.offer(chunk)) {
        terminateWithResourceExhausted();
        return;
    }

    scheduleWorker();
}
~~~

Do not call `offer()` and ignore its return value; a full queue must trigger backpressure or an explicit rejection policy. `scheduleWorker()` must also bound task counts and avoid submitting a new task per message if the executor queue could grow unbounded.

Never use `Thread.sleep`, `Future.get()` without a timeout, or long semaphore waits directly inside a callback. If waiting for a resource is necessary, move the wait to a bounded worker and tie it to the RPC's deadline/cancellation.

## 5. Choosing Sequential or Parallel Processing

| Model | How it works | Suitable when |
| --- | --- | --- |
| Handle directly in callback | Finish processing message before callback returns | Work is very light and fast. |
| One serial lane per RPC | Messages processed sequentially on a shared executor | Ordering must be preserved without blocking callbacks. |
| Parallel worker pool | Multiple messages processed concurrently | Messages are independent and completion order does not matter. |
| Parallel + reorder | Process in parallel, emit results by sequence | High throughput is needed while responses must remain ordered. |

A serial lane does not require creating a dedicated thread per RPC. You can use a shared executor with a per-call sequential queue. Bound pending tasks both per call and service-wide so high RPC counts do not produce an uncontrolled number of tasks.

When processing in parallel, attach sequence numbers or correlation IDs to work items. When responses must be returned in order, use a bounded reorder buffer and only emit the next sequence when ready.

## 6. Serializing Operations on StreamObserver

Never assume an outbound `StreamObserver` can be called concurrently by multiple threads. If multiple workers call `onNext`, or one worker calls `onCompleted` while another is sending, races, misordering, and callbacks after terminal events can occur.

The safe pattern is that multiple producers only enqueue; a single writer performs:

- Checking that state is still OPEN.
- Checking outbound readiness if the observer supports it.
- Pulling messages from the queue and calling `onNext`.
- Emitting strictly one `onError` or `onCompleted`.

~~~mermaid
flowchart LR
  A["Worker A"] --> Q["Bounded outbound queue"]
  B["Worker B"] --> Q
  C["Worker C"] --> Q
  Q --> W["Single writer"]
  W --> O["StreamObserver"]
  W --> S["Terminal state"]
~~~

Serialization must span both the state check and the callback. Checking `AtomicBoolean terminated` and then calling `onNext` outside the serialized region still races: another thread can terminate the observer after the check but before the call.

## 7. Example Outbound Orchestration with a Single Writer

The example below illustrates a sequential writer using a single-threaded executor for one call:

~~~java
final class OutboundWriter<T> {
    private final StreamObserver<T> observer;
    private final Executor serialExecutor;
    private final AtomicBoolean terminal = new AtomicBoolean();

    OutboundWriter(StreamObserver<T> observer, Executor serialExecutor) {
        this.observer = observer;
        this.serialExecutor = serialExecutor;
    }

    void send(T value) {
        serialExecutor.execute(() -> {
            if (!terminal.get()) {
                observer.onNext(value);
            }
        });
    }

    void complete() {
        serialExecutor.execute(() -> {
            if (terminal.compareAndSet(false, true)) {
                observer.onCompleted();
            }
        });
    }

    void fail(Throwable error) {
        serialExecutor.execute(() -> {
            if (terminal.compareAndSet(false, true)) {
                observer.onError(error);
            }
        });
    }
}
~~~

Here, `serialExecutor` must genuinely serialize all tasks for the writer. If using a dedicated `Executors.newSingleThreadExecutor()` per call, you must shut down the executor when the RPC finishes; this is simple to illustrate but unsuitable when there are many concurrent RPCs because it creates too many executors/queues.

In production, prefer a serial lane backed by a bounded shared executor, cap pending tasks, handle `RejectedExecutionException`, and stop admission once the call is terminal. Never enqueue unbounded `send()` tasks only to check readiness inside the writer.

## 8. Combining Concurrency with Inbound Backpressure

If callbacks submit each message into a worker pool faster than workers finish, executor queues or application queues grow. Manual flow control lets you tie inbound demand to actual available slots.

On the server, obtain `ServerCallStreamObserver` from the response observer:

~~~java
ServerCallStreamObserver<UploadResult> call =
    (ServerCallStreamObserver<UploadResult>) responseObserver;

call.disableAutoRequest();
call.request(1);
~~~

Only after a worker finishes processing a chunk and frees a slot should you call `call.request(1)` to allow receiving the next one. With multiple workers, messages currently being processed also consume capacity; do not count only messages sitting in the queue.

On the client, `ClientResponseObserver.beforeStart(...)` provides `ClientCallStreamObserver` to call `disableAutoRequestWithInitial(n)` and `request(n)` for inbound responses. This controls message count; HTTP/2 flow control still manages bytes at the transport layer.

## 9. Combining Concurrency with Outbound Readiness

With server streaming, `ServerCallStreamObserver.isReady()` and `setOnReadyHandler()` let the writer pause sending when gRPC is not ready to accept more responses:

~~~java
call.setOnReadyHandler(this::scheduleDrain);

void drain() {
    while (!cancelled.get() && call.isReady()) {
        PriceUpdate update = outboundQueue.poll();
        if (update == null) {
            break;
        }
        writer.onNext(update);
    }
}
~~~

This code must run on the same serial lane as terminal events. If the on-ready callback runs on another thread, it should only wake up the writer; never drain in parallel. Producers must also pause when the outbound queue nears capacity; otherwise readiness only stops transport handoff while the application queue keeps growing.

## 10. Executors Must Be Bounded with a Rejection Policy

A `newFixedThreadPool` typically uses an unbounded queue. Thread count is bounded, yet pending tasks can grow forever if incoming load exceeds processing capacity.

For streaming RPCs, consider:

- Maximum thread count.
- Executor queue capacity.
- In-flight tasks per RPC.
- Total tasks/buffers across the entire service.
- Policy when the executor rejects tasks.
- How to shut down and drain when the application stops.

Example creating a bounded executor:

~~~java
ThreadPoolExecutor workers = new ThreadPoolExecutor(
    8,
    16,
    60,
    TimeUnit.SECONDS,
    new ArrayBlockingQueue<>(256),
    new ThreadPoolExecutor.AbortPolicy());
~~~

`AbortPolicy` throws `RejectedExecutionException` when both threads and queue are exhausted. The application must catch this condition, stop accepting more work, or terminate the RPC with an appropriate status; never ignore the exception and never accidentally run heavy work back on the callback thread.

Avoid `CallerRunsPolicy` when tasks can be long: it can cause the gRPC callback to execute the entire rejected task and block the transport executor.

## 11. Propagating gRPC Context Across Executors

gRPC `Context` typically carries deadlines, cancellation, and metadata tied to the call. When callbacks submit work to another executor, do not assume the context is automatically present on worker threads.

You can capture the current context and wrap the executor:

~~~java
Context callContext = Context.current();
Executor contextExecutor =
    callContext.fixedContextExecutor(workerPool);

contextExecutor.execute(() -> {
    if (callContext.isCancelled()) {
        return;
    }
    processChunk(chunk);
});
~~~

Propagating context lets workers access the RPC's correct context and check cancellation/deadlines. If MDC or Spring security context must also be propagated, configure corresponding propagation mechanisms; do not assume gRPC `Context` automatically copies all `ThreadLocal` values.

Do not retain an RPC `Context` longer than the required work lifecycle. When the call finishes, pending tasks must be cancelled or skipped, and references to state must be released.

## 12. Cancellation and Errors While Tasks Are Running

When the client cancels the call or the deadline expires, workers may still be running. Maintain a shared per-call state flag and wire cancellation to:

- Stop receiving or enqueueing further messages.
- Cancel upstream subscriptions.
- Cancel not-yet-started tasks when possible.
- Signal running tasks to stop at safe checkpoints.
- Emit no responses after terminal events.
- Clear queues and release byte budgets.

On the server, use `ServerCallStreamObserver.setOnCancelHandler()` to signal shutdown:

~~~java
call.setOnCancelHandler(() -> {
    state.cancelled.set(true);
    upstream.cancel();
    workerTasks.forEach(task -> task.cancel(true));
    cleanupPendingBuffers();
});
~~~

Interruption only works if workers and dependencies cooperate with interruption. For I/O or APIs that do not support cancellation, use dedicated timeouts and check state at checkpoints. Cleanup must be idempotent because cancellation can occur near the moment a worker reports an error or finishes.

## 13. Common Mistakes

| Mistake | Consequence | How to handle |
| --- | --- | --- |
| Running long queries or I/O inside callbacks | Ties up RPC-handling executor and slows other calls | Offload to bounded workers. |
| Submitting tasks to an unbounded pool | Pending tasks and memory grow without bound | Use bounded executors and admission control. |
| Storing RPC state in singleton fields | Concurrent calls overwrite each other's data | Create dedicated state per call. |
| Assuming workers finish in submission order | Responses can end up out of order | Serial lane or sequence/reorder buffer. |
| Multiple threads calling observer directly | Race between `onNext` and terminal events | Use a single sequential writer. |
| Checking only `AtomicBoolean` before callback | Race between check and observer call | Serialize both check and callback emission. |
| Using `CallerRunsPolicy` for heavy tasks | Callback thread can be blocked | Controlled rejection or dedicated executor. |
| Losing gRPC `Context` across thread hops | Loses deadline/cancellation context | Wrap tasks with a `Context` executor. |
| Failing to stop workers on client cancel | Wastes resources after RPC ends | Propagate cancellation and clean up. |

## 14. Testing Concurrency

Tests should actively create contention rather than running a single message sequentially:

1. Send messages faster than worker speed and verify queues/executors never exceed capacity.
2. Make workers process slowly to verify manual inbound demand.
3. Have multiple workers finish out of order and verify responses stay ordered if required by contract.
4. Call cancel while workers are processing; verify no responses are emitted after terminal events.
5. Trigger executor task rejection and verify the RPC terminates per policy.
6. Race `onNext` against `onCompleted`/`onError`; verify strictly one valid terminal ordering.
7. Verify `Context`/deadlines remain valid on worker threads.
8. Run multiple concurrent RPCs to detect accidentally shared state across calls.

Use latches/barriers to reproduce controlled races. Avoid `Thread.sleep()` as a test synchronization mechanism since outcomes depend on scheduler timing. Verify statuses, message ordering, queue depth, and resource cleanup.

## 15. Observing in Production

Useful indicators:

- Callback duration by RPC method.
- Active tasks and queued tasks in executors.
- Rejected task count.
- Inbound/outbound queue depth and queued bytes per call.
- Number of workers processing each RPC.
- Duration the observer is not ready.
- Counts of RPCs cancelled, deadline exceeded, or resource exhausted.
- Count of late emissions or duplicate terminal event requests.

If callback duration rises, check for blocking I/O or lock contention. If executor queues grow while callbacks stay short, the worker pool may lack capacity or consumers are slow. If queues stay low while responses lag, check readiness, transport, and peer behavior.

Never log full payloads. Use RPC IDs, sequences, queue metrics, and statuses to correlate events without exposing data.

## 16. Practice Exercises

Design a server-side bidirectional RPC that receives commands and returns progress:

1. Create a dedicated state object per call; the Spring service holds no mutable RPC state in singleton fields.
2. Inbound callbacks perform only fast validation and enqueue into a bounded queue.
3. Use manual flow control to request messages only when capacity is available.
4. Workers process via a serial lane or in parallel with sequence numbers, depending on ordering requirements.
5. Workers place responses into an outbound queue; a single writer sends when `isReady()`.
6. Propagate gRPC `Context` to workers and stop work on cancellation/deadlines.
7. Write tests for queue overflow, executor rejection, terminal event races, and multiple concurrent RPCs.

**Completion criteria:** callbacks are not blocked by heavy work, state never leaks across RPCs, observers are invoked sequentially, queues/executors are bounded, and cancellation propagates to workers.

## 17. Key Takeaways

- gRPC callbacks execute on runtime-managed executors; do not rely on a fixed thread.
- Tasks submitted to a worker pool can run concurrently and finish out of order.
- Create separate state per RPC; never store mutable call state in singleton service beans.
- Use bounded executors, bounded queues, and explicit rejection policies.
- Serialize outbound operations on `StreamObserver`, including state checks and terminal events.
- Combine manual inbound demand and outbound readiness to bound pending work.
- Propagate gRPC `Context` across executors and stop workers on cancellation/deadlines.
- Test races, queue overflow, executor rejection, and multiple concurrent RPCs.

Properly managing concurrency in callbacks helps Spring gRPC services preserve message order, protect executors and memory, and prevent race conditions when many streaming RPCs run concurrently.
