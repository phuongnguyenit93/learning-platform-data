# BlockingStub and Calling Threads

## 1. BlockingStub Executes RPCs on the Calling Thread

In **SPRING_GRPC**, Protocol Buffers define services and messages; the Java code generation plugin creates stubs for the application to invoke gRPC methods. `BlockingStub` is the synchronous variant: when a method is called, the calling thread waits for the RPC result or an error before continuing execution.

Example:

~~~java
GetOrderReply reply = ordersBlockingStub.getOrder(
        GetOrderRequest.newBuilder()
                .setOrderId("ORD-42")
                .build());

// This line only runs after the RPC completes successfully
return toView(reply);
~~~

For a unary RPC, the method returns a single response. While waiting for the server, the caller is blocked. `BlockingStub` does not spawn a separate thread for each call, nor does it turn the RPC into a background task. The transport still handles I/O on gRPC's internal threads, while the calling thread waits for the result.

This determines where `BlockingStub` can be called: use it on a thread that is allowed to wait; avoid calling it directly on an event loop or a thread that needs to continue processing many other events.

## 2. RPC Types Supported by BlockingStub

In gRPC Java, a generated blocking stub typically provides:

| RPC Type | How to Call from BlockingStub | Caller Behavior |
|---|---|---|
| Unary | Call the method and receive one response | Waits until the response or an error |
| Server streaming | Call the method and receive `Iterator<Response>` | Iterates over the iterator; fetching the next element may wait for the next message |
| Client streaming | No corresponding blocking API in the standard generated stub | Use `AsyncStub` and `StreamObserver` |
| Bidirectional streaming | No corresponding blocking API in the standard generated stub | Use `AsyncStub` and `StreamObserver` |

Server-streaming example:

~~~java
Iterator<ProgressEvent> events =
        ordersBlockingStub
                .withDeadlineAfter(30, TimeUnit.SECONDS)
                .watchOrder(
                        WatchOrderRequest.newBuilder()
                                .setOrderId("ORD-42")
                                .build());

while (events.hasNext()) {
    ProgressEvent event = events.next();
    process(event);
}
~~~

Calling `watchOrder(...)` returns an iterator, but reading from the iterator is still a blocking operation. `hasNext()` may have to wait for the server to send the next event or end the stream. If the server keeps the stream open for a long time, the thread iterating over it can also be held for a long time.

Do not confuse receiving an `Iterator` with the RPC having completed. For server streaming, the RPC only ends when the server closes the stream, the client cancels the call, or a deadline/cancellation terminates the call.

## 3. BlockingStub and AsyncStub Differ in Execution Model

Generated gRPC Java code typically provides these stub variants:

- **BlockingStub:** Synchronous API for unary and server-streaming; the caller waits for the result.
- **FutureStub:** Future-based API for unary methods; the caller receives a future and can wait on it or compose it with other execution flows.
- **AsyncStub:** Asynchronous API using callbacks/`StreamObserver`; suitable for client-streaming, bidirectional streaming, and event-driven integration.

Example of creating the stubs from the same channel:

~~~java
OrdersGrpc.OrdersBlockingStub blocking =
        OrdersGrpc.newBlockingStub(channel);

OrdersGrpc.OrdersFutureStub future =
        OrdersGrpc.newFutureStub(channel);

OrdersGrpc.OrdersStub async =
        OrdersGrpc.newStub(channel);
~~~

The stubs share the same channel, but differ in their API and how the application receives results. Choose the stub based on the threading model of the calling layer. Do not choose `BlockingStub` just because linear code is easier to read if the caller is running on an event loop.

## 4. Which Threads Are Suitable for Calling BlockingStub?

A blocking call holds the thread until the RPC finishes. Therefore, you need to consider whether that thread is allowed to wait:

| Call Site | Suitability | Reason |
|---|---|---|
| Spring MVC servlet request thread | Can be suitable | The request/response model is inherently synchronous; requires time bounds and enough threads to serve traffic |
| Dedicated bounded executor | Suitable | Allows controlling concurrency, queue, and rejection |
| Java virtual thread | Can be suitable if supported by the runtime/version | Reduces the cost of waiting threads, but does not increase backend capacity or RPC limits |
| WebFlux/Netty event loop | Not suitable | Blocking the event loop slows down many other requests on the same loop |
| gRPC server callback/event loop | Not suitable | Can tie up threads needed to handle I/O and callbacks |
| ForkJoin common pool | Generally should not be used by default | Blocking can starve workers needed for other tasks |

In Spring MVC, a synchronous RPC can hold a servlet thread for the duration of the call. This is a straightforward choice if RPC duration is bounded, concurrent requests stay within pool capacity, and the application accepts a waiting model.

With Spring WebFlux, do not call `BlockingStub` directly in a controller running on the event loop. Use `AsyncStub`/`FutureStub` for asynchronous integration, or offload the blocking task to a dedicated bounded executor if the API cannot be changed yet.

## 5. Integrating BlockingStub in Spring

`ManagedChannel` should be managed as a long-lived application resource. Create the channel and stub once, then inject them into services:

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
    OrdersGrpc.OrdersBlockingStub ordersBlockingStub(
            ManagedChannel ordersChannel) {
        return OrdersGrpc.newBlockingStub(ordersChannel);
    }
}
~~~

Service calling the stub:

~~~java
import org.springframework.stereotype.Service;
import java.util.concurrent.TimeUnit;

@Service
public class OrdersFacade {
    private final OrdersGrpc.OrdersBlockingStub orders;

    public OrdersFacade(OrdersGrpc.OrdersBlockingStub orders) {
        this.orders = orders;
    }

    public GetOrderReply getOrder(String orderId) {
        GetOrderRequest request = GetOrderRequest.newBuilder()
                .setOrderId(orderId)
                .build();

        return orders
                .withDeadlineAfter(800, TimeUnit.MILLISECONDS)
                .getOrder(request);
    }
}
~~~

Stubs generated from the same channel can be reused concurrently. gRPC Java stubs are immutable and thread-safe; methods such as `withDeadlineAfter(...)` return a new stub with adjusted `CallOptions` without modifying the original shared stub. This lets a service hold a base stub and create per-request deadline variants.

Do not create a new channel or transport stub for every RPC. Doing so increases the number of connections, TLS handshakes, resource usage, and discovery overhead.

## 6. Deadlines Bound How Long a Thread Must Wait

A blocking call should not wait indefinitely. Set a deadline according to the business time budget:

~~~java
GetOrderReply reply = orders
        .withDeadlineAfter(800, TimeUnit.MILLISECONDS)
        .getOrder(request);
~~~

The deadline applies to the entire RPC, including connection wait time, server processing, and response transmission. When the deadline expires, the caller receives an error such as `DEADLINE_EXCEEDED`; the thread is released when the call terminates.

If a service calls multiple dependencies sequentially, you must split the total budget. For example, an HTTP request with a 2-second budget should not grant 2 seconds to each sequential RPC. You can propagate the remaining time or set shorter deadlines for each step so there is still time left to assemble the response.

`withWaitForReady()` can cause a call to wait until the channel has a ready backend, but the deadline still bounds the total time. Do not use wait-for-ready without a deadline for requests with a strict SLA.

## 7. Error Handling and Interruption

RPC errors are typically thrown as `StatusRuntimeException`. With blocking calls, handle the status at the service boundary to map it to an appropriate application error:

~~~java
try {
    return orders
            .withDeadlineAfter(800, TimeUnit.MILLISECONDS)
            .getOrder(request);
} catch (StatusRuntimeException ex) {
    Status.Code code = ex.getStatus().getCode();

    if (code == Status.Code.DEADLINE_EXCEEDED) {
        throw new OrderLookupTimeoutException(ex);
    }
    if (code == Status.Code.UNAVAILABLE) {
        throw new OrdersServiceUnavailableException(ex);
    }
    throw ex;
}
~~~

Do not retry every error just because the call is blocking. `INVALID_ARGUMENT`, `PERMISSION_DENIED`, or `NOT_FOUND` usually require business-level handling. Retries are only appropriate when the status is retryable, the logical RPC has not committed, and the operation can be safely retried.

When a thread is interrupted, treat it as a signal to cancel the work. Preserve the interrupt flag if catching `InterruptedException` at the executor or orchestration layer:

~~~java
try {
    return performBlockingWork();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new RequestCancelledException(ex);
}
~~~

gRPC Java blocking APIs may represent interruption/cancellation as `StatusRuntimeException` depending on the call path. Do not swallow an interruption and continue processing as if the request were still valid.

## 8. Bounding Calling Thread Concurrency

If each synchronous RPC holds a thread, the number of concurrent RPCs is bounded by the capacity of the executor or request thread pool. For example, a pool with 40 workers can run at most around 40 blocking tasks concurrently in that pool; additional tasks must wait in a queue or be rejected.

~~~text
HTTP requests
     |
     v
Bounded executor (40 workers)
     |
     +--> worker 1 --> BlockingStub RPC
     +--> worker 2 --> BlockingStub RPC
     +--> ...
     +--> worker 40 -> BlockingStub RPC
     |
     +--> bounded queue
~~~

Pool design should be based on RPC latency, expected concurrency, upstream limits, and maximum wait time. An unbounded queue can turn overload into ever-increasing latency and hold requests for too long. Rejection should be handled explicitly—for example, returning an overload error instead of queuing indefinitely.

Do not mechanically increase thread pool sizes to cope with a slow backend. Doing so can push concurrent RPCs past server, database, or connection limits. Combine deadlines, admission control, bulkheads, and per-dependency concurrency limits.

## 9. Offloading Blocking Work to a Dedicated Executor

If a layer requires an API that returns immediately while the underlying layer only has a blocking client, you can run the RPC on a dedicated executor:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

@Service
public class AsyncOrdersFacade {
    private final OrdersGrpc.OrdersBlockingStub orders;

    public AsyncOrdersFacade(OrdersGrpc.OrdersBlockingStub orders) {
        this.orders = orders;
    }

    @Async("grpcBlockingExecutor")
    public CompletableFuture<GetOrderReply> getOrder(String orderId) {
        GetOrderReply reply = orders
                .withDeadlineAfter(800, TimeUnit.MILLISECONDS)
                .getOrder(GetOrderRequest.newBuilder()
                        .setOrderId(orderId)
                        .build());
        return CompletableFuture.completedFuture(reply);
    }
}
~~~

The `grpcBlockingExecutor` executor should be declared with a bounded worker count and bounded queue. `@Async` only shifts execution to the executor; it does not make `BlockingStub` itself non-blocking. The executor's worker thread is still held for the duration of the RPC.

Do not use the default `CompletableFuture.supplyAsync(...)` if the task can block for a long time, as it can occupy the shared common pool used by other tasks. Pass an explicitly managed executor.

## 10. Virtual Threads Do Not Replace Resource Limits

Java virtual threads can reduce the cost of creating and waiting on threads compared to platform threads in many blocking workloads. If using them to call `BlockingStub`, verify the Java version, gRPC transport, and actual behavior in the deployment environment.

Virtual threads do not allow a server to process unlimited concurrent RPCs. Each call still consumes resources on the client, transport, proxy, server, and dependencies. You still need deadlines, in-flight call limits, backpressure, and quotas. Removing limits simply because threads are cheaper to create can push overload down to the backend.

## 11. Server Streaming Holds the Thread While Reading the Iterator

With server streaming, the calling thread can block in `hasNext()` while waiting for the next event:

~~~java
Iterator<ProgressEvent> stream = orders
        .withDeadlineAfter(60, TimeUnit.SECONDS)
        .watchOrder(request);

while (stream.hasNext()) {
    ProgressEvent event = stream.next();
    handle(event);
}
~~~

If events arrive slowly, the thread remains held while waiting. If streams stay open for several minutes and there are thousands of clients, the number of blocking threads can become the primary bottleneck. When many concurrent streams are needed, consider `AsyncStub` and handling `StreamObserver` on an appropriate executor/event loop.

The consumer must also keep up with the data arrival rate. If `handle(event)` is slow, reading from the iterator slows down; gRPC flow control helps regulate data flow, but the application still needs bounded buffers and consumer error handling.

For potentially long-lived streams, design cursors/checkpoints so clients can reconnect/resume when a deadline, network issue, or server terminates the stream. Do not assume a blocking iterator will automatically fail over to another backend when an instance stops.

## 12. When Should You Switch to AsyncStub?

| Requirement | Appropriate Choice |
|---|---|
| Synchronous Spring MVC, bounded requests, bounded latency with deadline | `BlockingStub` |
| WebFlux or Netty event loop | `AsyncStub` or `FutureStub` |
| Client-streaming/bidirectional streaming | `AsyncStub` |
| Many concurrent, long-lived server streams | Usually `AsyncStub` |
| Synchronous background task with a bounded executor | `BlockingStub` on a dedicated executor |
| Composing unary calls with `CompletableFuture` | `FutureStub` or an asynchronous adapter |

Using async does not automatically give you proper backpressure. `AsyncStub` still requires managing callbacks, request demand, cancellation, and executors. Choose a model so that the running thread is not blocked unintentionally.

## 13. Testing and Observing Calling Threads

Tests should verify both RPC outcomes and how threads are used:

| Scenario | What to Verify |
|---|---|
| Unary success | Caller only proceeds after the response |
| Server returns gRPC error | `StatusRuntimeException` is mapped correctly |
| Deadline expires | Call ends at the deadline and the thread is released |
| Server streaming has not sent an event yet | Iterator waits; not running on the event loop |
| Stream ends | Iterator finishes normally |
| Thread is interrupted | Cancellation/interruption is propagated and interrupt flag is not swallowed |
| Executor runs out of workers/queue | Rejection or overload is handled explicitly |
| Many concurrent RPCs | Concurrency does not exceed design limits |
| WebFlux controller | Does not block the Netty event loop |
| Spring shutdown | Channel and executor are closed according to lifecycle |

Observability:

- Number of threads running blocking RPCs and number of threads waiting in the queue.
- Number of in-flight RPCs, latency, and deadline exceeded counts.
- Executor wait time and rejection counts.
- Open stream count, stream age, and event rate.
- Status codes, cancellations, and interruptions.
- Thread pool saturation ratio when upstream is slow.

If RPC latency increases while client CPU is low, many threads may be waiting on I/O. If the servlet pool or executor is exhausted, check in-flight calls, deadlines, queues, and backend latency instead of just increasing thread counts.

## 14. Common Pitfalls

| Mistake | Consequence | Fix |
|---|---|---|
| Calling `BlockingStub` on the Netty event loop | Blocks processing of many other requests | Use async APIs or a dedicated blocking executor |
| Assuming BlockingStub spawns a background thread | Caller gets blocked unexpectedly | Call from a thread allowed to wait |
| Not setting a deadline | Thread can be held indefinitely | Set a deadline based on the request budget |
| Using an unbounded pool | Queue grows and overload cascades | Bounded executor, rejection, and admission control |
| Using the common pool for blocking RPCs | Starvation of other tasks sharing the pool | Dedicated executor |
| Sharing session-specific stubs/interceptors with mutable state | Data between requests can leak or mix | Keep stubs immutable; keep per-call data scoped to the call |
| Using blocking iterators for thousands of long-lived streams | Thread exhaustion | Consider AsyncStub and flow control |
| Catching errors and ignoring interrupts | Cancelled requests keep consuming resources | Preserve interruption/cancellation |

**Takeaway:** `BlockingStub` executes unary or server-streaming RPCs synchronously; the calling thread waits for the response or the next iterator message. Use it on servlet threads or bounded executors when the application model permits waiting; avoid WebFlux/Netty event loops. Reuse thread-safe channels/stubs, set per-RPC deadlines, bound concurrency, and switch to `AsyncStub` when you need client/bidirectional streaming or many concurrent streams. `@Async` only changes the executor—it does not turn a blocking call into a non-blocking one.
