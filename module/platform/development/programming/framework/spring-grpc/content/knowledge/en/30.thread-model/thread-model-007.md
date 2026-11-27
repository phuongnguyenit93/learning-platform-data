# Callback Threads in Async Stubs

Generated asynchronous stubs in gRPC Java deliver results through `StreamObserver` callbacks. These callbacks are not guaranteed to run on the thread that invoked the stub; gRPC dispatches them via an executor dedicated to application callbacks. Therefore, `onNext`, `onError`, and `onCompleted` must execute quickly, avoid blocking the thread, and make no assumptions about thread identity.

In Spring gRPC, stubs and channels are typically shared across many requests. Callbacks for multiple RPCs can run concurrently, so shared state requires concurrency control. If a callback needs to query a database, call a blocking service, or perform heavy CPU work, offload that work to a bounded application executor.

## 1. Where Does an Async Stub Invoke Callbacks?

```java
stub.getProduct(request, new StreamObserver<>() {
    @Override
    public void onNext(Product response) {
        handleResponse(response);
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
```

The call above starts the RPC and returns control to the caller. When a response or error arrives, gRPC invokes the observer on the executor designated for application callbacks. If no custom executor is configured, gRPC uses a runtime-managed default executor.

Do not rely on assumptions that callbacks always run on the stub-calling thread, that all RPCs share a single thread, that callbacks have a fixed thread name, or that callbacks finish before the method invoking the stub returns. For a single RPC, callbacks follow the call's lifecycle; different RPCs can be processed concurrently on different threads.

## 2. Distinguishing Transport Threads from the Callback Executor

| Component | Role | How to Use |
| --- | --- | --- |
| Transport/event-loop thread | Handles I/O and transport events | Do not run blocking logic or heavy business processing |
| gRPC callback executor | Dispatches callbacks to the application | Short callbacks, non-blocking, no long-held locks |
| Application executor | Runs business logic, blocking I/O, or bounded CPU work | Has its own queue/concurrency policy and lifecycle |

In gRPC Java, a channel builder can accept an executor for application callbacks. The server builder also has an executor mechanism for server-side callbacks. If unconfigured, gRPC picks its default executor. Do not refer to every callback thread as a Netty event-loop thread; the transport type and executor configuration determine execution details.

In particular, `directExecutor()` instructs gRPC to run callbacks directly rather than dispatching them through a separate executor. The callback may then run directly on the thread performing the gRPC operation or the current dispatch thread; a blocking callback can hold that thread and impact the transport or other calls. Only use direct executor when callbacks are very short, the call path is thoroughly understood, and appropriate load tests are in place.

A callback should perform brief work such as checking a status, completing a future, updating per-call state, or submitting a task to an application executor. Synchronous database queries, blocking HTTP calls, waiting on long locks, or running heavy CPU algorithms inside a callback can exhaust the callback pool and slow down other RPCs.

## 3. Configuring a Callback Executor for a Channel

You can provide a custom executor when building a channel:

```java
Executor callbackExecutor = grpcCallbackExecutor;

ManagedChannel channel = ManagedChannelBuilder
        .forAddress("catalog.internal", 9090)
        .useTransportSecurity()
        .executor(callbackExecutor)
        .build();

CatalogServiceGrpc.CatalogServiceStub stub =
        CatalogServiceGrpc.newStub(channel);
```

In this example, `grpcCallbackExecutor` is an application-managed executor injected into the client configuration. In Spring, you can declare the executor as a bean and configure thread names, concurrency limits, queue capacity, metrics, and shutdown lifecycle according to application conventions.

Only configure a custom callback executor when there is a clear operational reason. An executor that is too small causes callbacks to queue; one that is too large increases context switching and memory pressure. Unbounded queues can turn overload into steadily climbing latency. Monitor active threads, queue depth, task rejections, and callback duration to tune it.

If you use a custom executor for a channel, clearly define ownership. The application typically must shut down any executor it created after the channel stops accepting calls and remaining callbacks have drained. Never shut down a shared executor when a single client bean terminates if other channels still use it.

## 4. Callbacks Must Be Short and Non-Blocking

Example of what not to do:

```java
stub.getProduct(request, new StreamObserver<>() {
    @Override
    public void onNext(Product response) {
        // Avoid: the callback is held while waiting on the database.
        inventoryRepository.loadByProductId(response.getId());
        updateSearchIndex(response);
    }

    @Override
    public void onError(Throwable error) {
        log.error("RPC failed", error);
    }

    @Override
    public void onCompleted() {
    }
});
```

If the database or search index is slow, the callback executor stays occupied for the entire wait. When many RPCs finish at the same time, other callbacks must wait for a free thread.

The callback should hand the data off to an application executor:

```java
stub.getProduct(request, new StreamObserver<>() {
    @Override
    public void onNext(Product response) {
        applicationExecutor.execute(() -> {
            inventoryRepository.loadByProductId(response.getId());
            updateSearchIndex(response);
        });
    }

    @Override
    public void onError(Throwable error) {
        handleRpcFailure(error);
    }

    @Override
    public void onCompleted() {
        markRpcCompleted();
    }
});
```

This is an outline for the unary case. In production, determine whether tasks can be rejected when the executor is overloaded, handle rejections, bound queues, and preserve ordering if steps depend on one another. Never push a large stream into an unbounded queue; apply backpressure or cap the number of queued messages waiting to be processed.

If the application executor rejects a task, handle the error in the callback according to your use case policy. Never let an exception from submitting the task escape the callback unintentionally, and never silently drop messages.

## 5. Using Futures to Separate Callbacks from Follow-Up Processing

For unary RPCs, you can complete a CompletableFuture inside the callback and run async continuations on an application executor:

```java
public CompletableFuture<ProductView> getProductAsync(String productId) {
    GetProductRequest request = GetProductRequest.newBuilder()
            .setProductId(productId)
            .build();

    CompletableFuture<Product> response = new CompletableFuture<>();

    stub.getProduct(request, new StreamObserver<>() {
        @Override
        public void onNext(Product value) {
            response.complete(value);
        }

        @Override
        public void onError(Throwable error) {
            response.completeExceptionally(error);
        }

        @Override
        public void onCompleted() {
            // The unary response has already been delivered to the future via onNext.
        }
    });

    return response.thenApplyAsync(
            this::toView,
            applicationExecutor);
}
```

The callback merely completes the future; mapping runs on the application executor. If mapping can fail, the resulting future completes exceptionally and callers can handle it via `exceptionally` or `handle`. For unary RPCs, there is normally at most one `onNext` before `onCompleted`; for streaming, model multiple messages instead of using a single future for all data.

Do not use `thenApply` if the mapping can block and you do not want it running on whichever thread completed the future. Use `thenApplyAsync` with an explicitly chosen executor to keep the callback thread light.

## 6. Preserving gRPC Context When Switching Executors

gRPC Context carries call-scoped data such as deadlines, cancellation, and data attached by interceptors. The current context inside a callback does not automatically cross into arbitrary custom executors. When you need to preserve context, capture it in the callback and wrap the task:

```java
@Override
public void onNext(Product response) {
    io.grpc.Context captured = io.grpc.Context.current();
    applicationExecutor.execute(captured.wrap(() -> {
        processProduct(response);
    }));
}
```

`Context.wrap` installs the captured context while the task runs and restores the previous context afterward. This is useful when `processProduct` needs to read a correlation ID or deadline from the gRPC Context.

Never store context in a mutable field on a singleton service. Each callback/RPC must keep its own context. If work continues after the RPC has already ended, the original context and deadline may no longer apply; pass required data as explicit inputs and define a fresh timeout for the background work.

OpenTelemetry Context is a separate context. If your application uses tracing and switches to custom executors, propagate OpenTelemetry Context with its corresponding wrapper or executor instrumentation; gRPC Context does not automatically replace that.

## 7. Streaming Callbacks and Message Ordering

For server streaming, `onNext` can be invoked multiple times before the terminal callback. For client streaming or bidirectional streaming, the application also sends requests via the `StreamObserver` returned by the stub. Distinguish between them:

- Response-receiving observer: gRPC calls `onNext`, `onError`, or `onCompleted`.
- Request-sending observer: the application calls `onNext` and eventually `onCompleted` or `onError`.

Do not assume callbacks across different RPCs share a global order. Within a single stream, message processing must preserve business ordering whenever order matters. If you submit each message to a multi-threaded pool, tasks can finish out of order; use a sequential per-stream executor or attach sequence numbers and perform bounded reordering.

Never let an `onNext` callback push every message into an unbounded queue. When the producer outpaces the consumer, memory grows until the process comes under pressure. Bound the number of pending messages, coordinate demand/flow control where supported by the API, and cancel the stream if the application cannot safely keep up.

## 8. Deadlines, Cancellation, and Errors in Callbacks

An async call ends through a terminal callback:

| Outcome | Client-Side Callback | Required Action |
| --- | --- | --- |
| Success | `onCompleted` after response message(s) | Release per-call state |
| Server returned error | `onError` | Classify the gRPC status; do not retry blindly |
| Deadline expired | Usually delivered via `onError` with `DEADLINE_EXCEEDED` | Stop call-dependent processing and record the timeout |
| Call cancelled | Usually delivered via `onError` with `CANCELLED` | Stop work that is no longer needed |

Do not synchronously wait on callbacks using `CountDownLatch.await()` on a callback thread; that can exhaust the executor or cause a deadlock if the callback needs that very executor to complete.

Callback implementations should not throw exceptions outward. Catch errors originating in callback code, route them to your application's future or error handler, and ensure no second terminal signal is emitted. `onError` and `onCompleted` are terminal; after them, do not process further messages as though the call were still active.

When a deadline or cancellation occurs, tasks already submitted to the application executor may still be running. If the task is no longer needed, use a cancellation token or per-call flag to stop work; never assume cancelling the RPC automatically stops every Java task the application submitted.

## 9. Managing Executors in Spring and Testing

In Spring, the callback executor and application executor can be two separate beans:

```java
@Configuration
public class GrpcExecutionConfiguration {

    @Bean(destroyMethod = "shutdown")
    ExecutorService grpcCallbackExecutor() {
        return Executors.newFixedThreadPool(8);
    }

    @Bean(destroyMethod = "shutdown")
    ExecutorService grpcApplicationExecutor() {
        return Executors.newFixedThreadPool(12);
    }
}
```

This is a simple example to illustrate ownership. Production configurations must consider bounded-queue pools, overload policies, metrics, and shutdown with timeouts; do not copy fixed thread counts without measuring load. If Spring gRPC or auto-configuration already manages the callback executor, use the proper extension point and avoid creating duplicate pools.

Testing should cover:

| Test Case | What to Verify |
| --- | --- |
| Successful unary call | Callback receives response followed by terminal completion |
| Failed RPC | `onError` receives status and completion is not called a second time |
| Callback thread | Code does not depend on a fixed thread identity |
| Slow callback | Application executor handles blocking work; callback pool is not held long |
| Overloaded executor | Rejection is handled without silently dropping messages |
| Context propagation | Required correlation/deadline is present inside the wrapped task |
| Streaming | Message order is preserved and queues are bounded |
| Deadline/cancel | Call-dependent tasks are stopped or marked cancelled |
| Shutdown | Channel stops accepting calls, callbacks drain per policy, and executors close in order |

You can use an in-process channel/server and controllable executors in tests. To verify thread dispatch, record thread names in tests or diagnostic logs; do not assert a fixed thread name as a gRPC contract.

## 10. Callback Thread Checklist

- [ ] Never assume callbacks run on the stub-calling thread or a thread with a fixed name.
- [ ] Distinguish transport threads, the gRPC callback executor, and the application executor.
- [ ] Keep callbacks short, with no blocking I/O or long lock waits.
- [ ] Offload heavy work to a bounded application executor.
- [ ] Handle task rejections and never silently drop messages.
- [ ] Preserve processing order when streaming requires ordering.
- [ ] Propagate gRPC Context and OpenTelemetry Context separately when switching executors.
- [ ] Treat `onError`/`onCompleted` as terminal callbacks.
- [ ] Never wait synchronously on callbacks from a callback thread.
- [ ] Give background tasks an explicit cancellation policy when the RPC hits a deadline or cancels.
- [ ] Define clear ownership/lifecycle for executors and channels in Spring.
- [ ] Test success, failure, overload, streaming, context, and shutdown cases.

**Self-Check**

**Question 1.** Do async stub callbacks always run on the thread that invoked the stub?

*Answer:* No. gRPC dispatches callbacks via the application callback executor; the default or configured executor determines the execution thread. Code should not rely on thread identity.

**Question 2.** Why should you avoid running blocking database queries directly inside `onNext`?

*Answer:* The callback executor stays occupied while waiting on I/O, forcing callbacks for other RPCs to wait. Offload blocking work to a bounded application executor.

**Question 3.** How do the callback executor and application executor differ?

*Answer:* The callback executor runs listeners/observers dispatched by gRPC; the application executor runs business work forwarded by callbacks, such as blocking I/O or CPU work.

**Question 4.** Why do you need to wrap gRPC Context when submitting a task?

*Answer:* Context does not automatically cross every custom executor. Wrapping the task preserves deadlines, correlation, or call-scoped data while the task runs.

**Question 5.** When a deadline expires, do tasks already submitted to the application executor stop automatically?

*Answer:* Not necessarily. A cancelled RPC does not automatically stop every submitted Java task; the application needs a cancellation token or per-call flag and must check it before or during processing.

Callback threads in async stubs are a critical part of the concurrency model: callbacks must stay lightweight, independent of thread identity, and free of long resource waits. Separating the callback executor from application work, propagating context intentionally, bounding queues for streaming, and handling cancellation explicitly will help Spring gRPC sustain steady latency when many RPCs run concurrently.
