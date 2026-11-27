# FutureStub and ListenableFuture

## 1. FutureStub Returns Asynchronous Results for Unary RPCs

In **SPRING_GRPC**, Protocol Buffers define services and messages; the gRPC Java plugin generates stubs for the application to invoke methods from that contract. `FutureStub` is the client variant for unary RPCs: instead of waiting for the response immediately in the called method, it returns a `ListenableFuture<Response>` representing the result that will complete later.

Example:

~~~java
ListenableFuture<GetOrderReply> result =
        ordersFutureStub.getOrder(
                GetOrderRequest.newBuilder()
                        .setOrderId("ORD-42")
                        .build());
~~~

When `getOrder(...)` returns, the RPC may still be in progress. The application can register callbacks, compose the future with another processing step, or wait for the result on a thread allowed to block.

`FutureStub` does not spawn a separate application thread per RPC, nor does it mean all downstream code is automatically asynchronous. It provides a handle to track the result. If you call `result.get()` immediately after creating the future, the current thread still blocks and the benefit of the asynchronous API is lost.

## 2. ListenableFuture Adds Listeners to Future

`ListenableFuture` belongs to Guava (`com.google.common.util.concurrent`) and extends Java's `Future` model with the ability to register listeners:

- `isDone()` checks whether the future has completed.
- `isCancelled()` checks whether the future has been cancelled.
- `get()` waits for the result; it may throw `InterruptedException` or `ExecutionException`.
- `get(timeout, unit)` waits only for a bounded duration on the caller side.
- `addListener(listener, executor)` registers work to run when the future completes.

A key point is that the listener requires an `Executor`. The executor determines where the callback runs. If you use `MoreExecutors.directExecutor()`, the listener may run directly on the thread that completes the future; a heavy or blocking callback can slow down that thread. For non-trivial processing, use a dedicated bounded executor.

`ListenableFuture` is still a Future: calling `get()` can still block. Asynchrony comes from registering listeners and composing results, not from the type name.

## 3. FutureStub Is Only for Unary Methods

Generated gRPC Java code typically produces three stub variants:

| Stub | Typical API | RPC Types |
|---|---|---|
| `BlockingStub` | Returns the response directly or `Iterator<Response>` | Unary and server streaming |
| `FutureStub` | Returns `ListenableFuture<Response>` | Unary |
| `AsyncStub` | Uses callbacks/`StreamObserver` | Unary, server streaming, client streaming, and bidirectional streaming |

`FutureStub` does not provide a `ListenableFuture` API for client-streaming or bidirectional-streaming because those RPCs involve multiple messages in two directions. For server streaming, the response is a sequence of messages rather than a single value; use `BlockingStub` if a blocking iterator is acceptable, or `AsyncStub` if asynchronous handling is needed.

Example of creating the stubs from the same channel:

~~~java
OrdersGrpc.OrdersBlockingStub blocking =
        OrdersGrpc.newBlockingStub(channel);

OrdersGrpc.OrdersFutureStub future =
        OrdersGrpc.newFutureStub(channel);

OrdersGrpc.OrdersStub async =
        OrdersGrpc.newStub(channel);
~~~

The stubs can share a channel. Choose the stub type based on the RPC kind and the threading model of the call site.

## 4. Register Callbacks Instead of Calling get Immediately

Guava's `Futures.addCallback` lets you handle success and failure in one place:

~~~java
import com.google.common.util.concurrent.FutureCallback;
import com.google.common.util.concurrent.Futures;
import com.google.common.util.concurrent.ListenableFuture;
import io.grpc.Status;

ListenableFuture<GetOrderReply> result =
        ordersFutureStub.getOrder(request);

Futures.addCallback(
        result,
        new FutureCallback<GetOrderReply>() {
            @Override
            public void onSuccess(GetOrderReply reply) {
                publishOrder(reply);
            }

            @Override
            public void onFailure(Throwable failure) {
                Status status = Status.fromThrowable(failure);
                recordFailure(status.getCode(), failure);
            }
        },
        callbackExecutor
);
~~~

`onSuccess` receives the response when the unary RPC completes successfully. `onFailure` receives transport errors, gRPC statuses, or other completion failures. Use `Status.fromThrowable(...)` to extract the status when the error originates from gRPC; you still need to handle cancellations or application exceptions according to context.

Callbacks should not perform long blocking work such as calling another service with `BlockingStub`, running synchronous database queries, or waiting on another future. If a follow-up step is needed, compose futures or dispatch the work to an appropriate executor.

## 5. The Executor Determines Where Callbacks Run

Heavy callbacks should not run by default on the thread completing the RPC. In Spring, inject a dedicated executor with bounded concurrency and queue capacity:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import java.util.concurrent.Executor;

@Configuration
public class GrpcCallbackConfiguration {

    @Bean
    Executor grpcCallbackExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("grpc-callback-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.initialize();
        return executor;
    }
}
~~~

These numbers are only examples; choose them based on callback latency, concurrent RPC count, and downstream capacity. An unbounded queue can accumulate results when callbacks process slowly. Rejection policy should also be decided explicitly: log/count, reject the task, or switch to an appropriate backpressure mechanism.

Do not use the WebFlux/Netty event loop as the executor for callbacks that might block. If a callback only updates a tiny piece of state, a direct executor may be suitable, but you must ensure the callback does not hold the RPC-completing thread for too long.

## 6. Integrating FutureStub in Spring

Channels and stubs should be created once and managed according to the application lifecycle:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersGrpcClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel ordersChannel() {
        return ManagedChannelBuilder
                .forTarget("dns:///orders.internal:9090")
                .useTransportSecurity()
                .build();
    }

    @Bean
    OrdersGrpc.OrdersFutureStub ordersFutureStub(
            ManagedChannel ordersChannel) {
        return OrdersGrpc.newFutureStub(ordersChannel);
    }
}
~~~

A service can return `ListenableFuture` to its caller:

~~~java
import com.google.common.util.concurrent.ListenableFuture;
import org.springframework.stereotype.Service;
import java.util.concurrent.TimeUnit;

@Service
public class OrdersQueryService {
    private final OrdersGrpc.OrdersFutureStub orders;

    public OrdersQueryService(OrdersGrpc.OrdersFutureStub orders) {
        this.orders = orders;
    }

    public ListenableFuture<GetOrderReply> getOrder(String orderId) {
        GetOrderRequest request = GetOrderRequest.newBuilder()
                .setOrderId(orderId)
                .build();

        return orders
                .withDeadlineAfter(700, TimeUnit.MILLISECONDS)
                .getOrder(request);
    }
}
~~~

`FutureStub` is immutable and thread-safe; configuration methods such as `withDeadlineAfter(...)` return a new stub with the corresponding `CallOptions`. A single stub bean can be shared across many concurrent requests. Each returned future belongs to an individual RPC; do not store an in-flight future in a shared singleton field across all callers.

There is no need to wrap a `FutureStub` call in `@Async` just to make it asynchronous: the gRPC method already returns a future. `@Async` can be useful for other orchestration, but if you only call the stub and return the future, it adds an unnecessary executor hop.

## 7. Composing Multiple Steps with Futures

Guava provides future transformation functions to build pipelines without calling `get()` in the middle:

~~~java
ListenableFuture<GetOrderReply> orderFuture =
        ordersFutureStub.getOrder(request);

ListenableFuture<OrderView> viewFuture =
        Futures.transform(
                orderFuture,
                reply -> toView(reply),
                callbackExecutor);
~~~

`Futures.transform` runs the transformation function on the specified executor after the source future succeeds. If the next step also returns a `ListenableFuture`, use `Futures.transformAsync` to chain futures without blocking a thread waiting for the result.

A few notes:

- Transformation functions should be short and non-blocking.
- If a transformation requires blocking I/O, offload it to an executor dedicated to blocking work.
- Errors from the source future propagate to the resulting future.
- Cancellation of the resulting future and cancellation propagation behavior must be verified for the composition pattern in use.
- Avoid deeply nested callback chains that are hard to observe; give steps clear names and trace/correlation IDs.

## 8. RPC Deadlines Differ from get Timeouts

Two kinds of timeouts are frequently confused:

| Mechanism | What Does It Bound? | When Time Expires |
|---|---|---|
| `withDeadlineAfter(...)` on stub | Total RPC duration in gRPC | The RPC expires; the server receives a deadline/cancellation signal over the transport |
| `future.get(timeout, unit)` | How long the current thread waits on the future | The caller receives `TimeoutException`; the RPC may continue running |

Example of setting a deadline on the RPC:

~~~java
ListenableFuture<GetOrderReply> result = ordersFutureStub
        .withDeadlineAfter(700, TimeUnit.MILLISECONDS)
        .getOrder(request);
~~~

If the caller only waits up to 200 ms:

~~~java
try {
    GetOrderReply reply = result.get(200, TimeUnit.MILLISECONDS);
    return toView(reply);
} catch (TimeoutException ex) {
    // Local wait expired; the RPC may still be running.
    result.cancel(true);
    throw new OrderLookupTimeoutException(ex);
}
~~~

`get(timeout, unit)` does not change the deadline of the gRPC call itself. If the caller no longer needs the result after the local timeout, call `cancel(...)` to cancel the future/RPC. If the RPC is still useful for a background task, another component can continue tracking the future, provided there are clear time bounds and lifecycle management.

## 9. Cancellation and Interruption

`ListenableFuture` supports `cancel(...)`. For a future returned by gRPC `FutureStub`, cancelling the future requests cancellation of the corresponding RPC. The server can receive cancellation via context, but it must check for cancellation and stop work cooperatively; you cannot assume every side effect already started will roll back automatically.

~~~java
ListenableFuture<GetOrderReply> result =
        ordersFutureStub.getOrder(request);

if (requestNoLongerNeeded()) {
    result.cancel(true);
}
~~~

The `mayInterruptIfRunning` parameter is part of the `Future` contract; it should not be taken as a guarantee that gRPC will forcibly interrupt every server thread processing the call. Cancellation is an RPC cancellation signal. The server must be designed to handle cancellation to stop queries, release resources, or stop emitting messages.

If using `get()` and the calling thread is interrupted, `get()` throws `InterruptedException`. Restore the interrupt flag when handling it at the appropriate layer:

~~~java
try {
    return result.get();
} catch (InterruptedException ex) {
    result.cancel(true);
    Thread.currentThread().interrupt();
    throw new RequestCancelledException(ex);
}
~~~

Do not swallow an interruption and keep waiting or perform side effects when the request has already been cancelled.

## 10. Handling Errors from ListenableFuture

When calling `get()`, RPC errors are typically wrapped in `ExecutionException`; the underlying cause is usually `StatusRuntimeException`. You can classify them:

~~~java
try {
    return result.get();
} catch (ExecutionException ex) {
    Throwable cause = ex.getCause();
    Status status = Status.fromThrowable(cause);

    if (status.getCode() == Status.Code.NOT_FOUND) {
        throw new OrderNotFoundException(cause);
    }
    if (status.getCode() == Status.Code.UNAVAILABLE) {
        throw new OrdersServiceUnavailableException(cause);
    }
    throw new OrderQueryException(cause);
}
~~~

When using callbacks, handle errors in `onFailure`. Distinguish at least:

- `StatusRuntimeException`: the RPC terminated with a gRPC status.
- `CancellationException`: the future was cancelled.
- Application error in transform/callback: result-processing logic failed.
- `TimeoutException`: only appears from timed `get()` when the caller's local wait expires.

Do not retry all errors. `INVALID_ARGUMENT`, `PERMISSION_DENIED`, and `NOT_FOUND` usually need business-level handling. Retries must follow status policy, deadlines, and operation idempotency.

## 11. Thread Safety and Per-Request State

Generated stubs are immutable/thread-safe and can be shared. In contrast, the request, future, and callback data belong to each individual call:

~~~text
Shared OrdersFutureStub
   |
   +--> RPC A -> Future A -> callback A
   |
   +--> RPC B -> Future B -> callback B
   |
   +--> RPC C -> Future C -> callback C
~~~

Do not store `currentRequest`, `currentFuture`, or shared mutable variables in a singleton service to correlate responses back to the right caller. Use local variables, immutable contexts, or per-RPC correlation IDs.

If callbacks need Spring Security, tracing, or MDC context, you must intentionally propagate/restore that context when switching executors. A thread pool does not automatically guarantee that callback threads have the same ThreadLocal context as the thread that initiated the RPC.

## 12. Concurrency Limits and Backpressure

The Future API reduces holding threads while waiting for results, but it does not allow the backend to process unlimited RPCs. Every RPC still consumes resources on the client, channel, network, proxy, server, and dependencies. If callers create futures faster than they complete, the number of in-flight RPCs can grow continuously.

You need:

- Limits on in-flight RPCs per service or tenant.
- Bounded queues for callback work.
- Admission control when the system reaches thresholds.
- Deadlines and cancellation when results are no longer needed.
- Concurrency limits to databases/downstream services on the server.
- Metrics for pending future count and oldest pending future age.

Do not use `ListenableFuture` as an unbounded queue. A future only represents a pending result; it does not automatically apply backpressure to the request producer.

## 13. Testing FutureStub and Callbacks

Tests should verify results, executors, and RPC lifecycle:

| Scenario | What to Verify |
|---|---|
| Unary success | Future completes with the expected response |
| Server returns error status | `onFailure` receives the error and status is classified properly |
| Listener registered after future already completed | Listener still executes on the executor |
| Callback runs on dedicated executor | Callback thread belongs to the expected pool, not the event loop |
| `get(timeout)` expires | Caller receives `TimeoutException`; RPC only stops if cancelled or deadline expires |
| `cancel(true)` | Future transitions to cancelled and RPC receives cancellation signal |
| Caller interrupted during `get()` | Interrupt is preserved and call is handled per policy |
| Transform fails | Resulting future fails |
| Callback executor full | Rejection is observed and handled |
| Many concurrent RPCs | Responses/callbacks do not mix across requests |
| WebFlux event loop | No blocking `get()` calls on the event loop |
| Spring shutdown | Channel and executor are closed according to lifecycle |

Do not just check `future.isDone()`. Verify that callbacks run on the right executor, cancellation reaches the server, and resources are released when the request no longer needs the result.

## 14. Metrics and Diagnostics

Track:

- Pending RPC count and pending duration.
- Latency from future creation to completion.
- Counts of succeeded, failed, and cancelled futures.
- Active callbacks, queue depth, and rejections.
- `TimeoutException` counts from local waits versus `DEADLINE_EXCEEDED` from RPCs.
- Error counts by gRPC status code.
- Failed transform/compose counts.
- In-flight RPCs remaining when the Spring context shuts down.

If a future completes but the callback does not run, check for executor shutdown, queue/rejection behavior, and how the listener was registered. If callers are still blocking, look for `get()`/`join()` on the execution path and check whether that thread is allowed to wait.

## 15. Common Pitfalls

| Mistake | Consequence | Fix |
|---|---|---|
| Calling `get()` right after receiving the future | Calling thread still blocks | Register a listener or compose futures |
| Assuming `FutureStub` supports all streaming types | No suitable API for client/bidirectional streaming | Use `AsyncStub` for streaming |
| Using `directExecutor` for heavy callbacks | Blocks the thread completing the RPC | Use a dedicated bounded executor |
| Confusing timed `get()` with gRPC deadline | RPC keeps running after caller times out | Set deadline on stub and cancel if no longer needed |
| Not handling cancellation | RPC and downstream work continue consuming resources | Propagate cancellation and check on the server |
| Storing mutable future in a singleton field | Results mix across requests | Use a separate future per call |
| Callback blocks to call another service | Starves the callback executor | Compose futures or use an appropriate executor |
| Not bounding pending RPCs | Increased memory usage and downstream load | Admission control, concurrency limits, and deadlines |

**Takeaway:** `FutureStub` provides an asynchronous unary API via `ListenableFuture`; futures let you register listeners and compose results without blocking the calling thread. `get()` still blocks, and `get(timeout)` only bounds local waiting; gRPC deadlines must be set on the stub. Use an appropriate executor for callbacks, handle errors/cancellation explicitly, bound pending RPCs, and switch to `AsyncStub` for client or bidirectional streaming.
