# Separating Blocking Calls from the Event Loop

**Chapter:** Thread model  
**Scope:** Spring gRPC (`SPRING_GRPC`) using Protocol Buffers contracts, generated Java code, and server/client for unary or streaming RPCs. This lesson focuses on moving JDBC, synchronous HTTP clients, SDKs, and other blocking operations off the Netty event loop while keeping deadlines, cancellation, context, and the response observer safe.

## 1. Why Must Blocking Calls Be Separated?

The Netty event loop serves I/O events for many channels and streams. It needs to handle socket reads, socket writes, and HTTP/2 frame dispatching quickly. If an event-loop thread is held by a long-waiting operation, events for other connections managed by that same event loop can also be delayed.

Operations that commonly cause blocking:

- Synchronous JDBC/JPA: waiting on connections, queries, or transactions.
- Synchronous HTTP clients: waiting on DNS, connect, or response bodies.
- Third-party service SDKs: waiting on the network or internal locks.
- File or object storage reads/writes using synchronous APIs.
- Waiting on `Future.get()`, `CompletableFuture.join()`, `CountDownLatch.await()`, or `Thread.sleep()`.
- Holding a monitor/lock while waiting on a dependency.

A single RPC might only spend 300 ms waiting on a database, but if it runs on an event loop serving many channels, the impact is not confined to that RPC. Latency rises, clients hit deadlines and retry, and even more load hits an already congested system.

**Principle:** the event loop handles transport I/O; blocking work must run on an appropriate, bounded executor with timeouts.

## 2. Distinguishing the Event Loop from the Server Application Executor

You should not assume every Spring gRPC handler runs on the Netty event loop. In a standard gRPC Java Netty setup, the transport uses the event loop for I/O while application callbacks are dispatched on the server application executor. The two thread groups play different roles:

| Thread/Executor | Responsibility | What Is the Impact of Blocking? |
| --- | --- | --- |
| Netty event loop | Sockets, HTTP/2 frames, transport events | Can delay many channels/streams on the event loop |
| Server application executor | Service methods and server listener callbacks | Occupies workers, causing other callbacks to queue |
| Blocking I/O worker pool | Synchronous JDBC/HTTP/SDK offloaded by the app | Consumes capacity of a dedicated pool; requires bounds and timeouts |
| CPU executor | Encryption, compression, heavy computation | Consumes CPU workers; requires bounded concurrency |

Therefore, before offloading, determine where callbacks are actually running:

- If using a separate server executor, blocking handlers exhaust application workers; a dedicated I/O pool can isolate that load.
- If `directExecutor()` is configured or blocking code is invoked directly from a callback running on a transport thread, blocking can hold the event loop.
- If a custom interceptor, callback, or adapter runs directly on the event loop, it must also avoid blocking.

There is no need to move every line of code out of the handler. Short validation, protobuf mapping, and tiny CPU logic can run on the application executor. The goal is to separate operations that wait for long periods or have unpredictable execution times.

### Be Careful with `directExecutor`

`directExecutor()` tells gRPC to run callbacks directly on the thread calling the executor. With the Netty transport, that thread can be a transport/event-loop thread. This mode reduces thread-switching overhead for very short callbacks, but it is unsuitable for handlers calling JDBC or synchronous HTTP clients.

Do not enable `directExecutor` just to "speed things up" without measuring under load. If used, callbacks must be short, non-blocking, and must never wait on a future to complete.

## 3. Choosing How to Separate Blocking Work

There are three main approaches:

1. **Dedicated bounded worker pool:** suitable when you must use JDBC, SDKs, or synchronous HTTP clients. A bounded pool and queue cap the amount of waiting work.
2. **Non-blocking clients/APIs:** use async HTTP clients, reactive data access, or gRPC async stubs so no thread is held while waiting on I/O. Never call `get()` or `join()` to turn an async API back into a blocking one.
3. **Virtual threads:** can be helpful for blocking workloads in runtimes that support them, though you still need concurrency limits and protection for databases/downstream services. Virtual threads do not increase dependency capacity and must not be used to block the Netty event loop.

No single solution fits every workload. Synchronous JDBC usually needs a worker pool or a virtual-thread-per-task executor with semaphore/connection limits; CPU-intensive work needs a separate CPU pool.

## 4. Creating a Bounded Worker Pool for Blocking I/O

Example configuration of a pool dedicated to customer service I/O operations:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

@Configuration
public class BlockingIoConfiguration {

    @Bean(destroyMethod = "shutdown")
    public ExecutorService customerBlockingExecutor() {
        AtomicInteger sequence = new AtomicInteger();
        ThreadFactory threadFactory = task -> {
            Thread thread = new Thread(
                    task,
                    "customer-blocking-" + sequence.incrementAndGet());
            thread.setDaemon(false);
            return thread;
        };

        return new ThreadPoolExecutor(
                12,
                12,
                0L,
                TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(200),
                threadFactory,
                new ThreadPoolExecutor.AbortPolicy());
    }
}
```

These numbers are examples only; size the pool based on throughput, wait time, connection pool limits, and downstream load. If the database only allows 20 concurrent connections, creating hundreds of workers calling the database simultaneously will not make queries faster; it will only create more queuing and timeouts.

### Why Must the Queue Be Bounded?

- An unbounded queue holds overloaded requests for long periods, increasing memory usage and latency.
- A bounded queue establishes an early rejection point when capacity is exhausted.
- `AbortPolicy` throws `RejectedExecutionException` so the adapter can map overload to a clear status.
- Do not use `CallerRunsPolicy` for blocking tasks: when the pool is full, the task can run directly on the submitter thread, which may be a sensitive callback thread or the event loop.
- Do not use `DiscardPolicy` or `DiscardOldestPolicy` if dropping a task leaves the RPC uncompleted forever.

When the queue is full, the server can return `RESOURCE_EXHAUSTED` or an overload status specified by the contract. Never accept a task and leave the RPC hanging.

## 5. Offloading Blocking Calls in a Spring gRPC Handler

The handler validates the request quickly, captures the gRPC Context, and submits the blocking operation to the worker pool. Unary RPC example:

```java
import io.grpc.Context;
import io.grpc.ServerCallStreamObserver;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.beans.factory.annotation.Qualifier;
import java.util.concurrent.Executor;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.atomic.AtomicBoolean;

@GrpcService
public class CustomerGrpcService
        extends CustomerServiceGrpc.CustomerServiceImplBase {

    private final CustomerApplicationService applicationService;
    private final Executor customerBlockingExecutor;
    private final GrpcExceptionMapper exceptionMapper;

    public CustomerGrpcService(
            CustomerApplicationService applicationService,
            @Qualifier("customerBlockingExecutor")
                    Executor customerBlockingExecutor,
            GrpcExceptionMapper exceptionMapper) {
        this.applicationService = applicationService;
        this.customerBlockingExecutor = customerBlockingExecutor;
        this.exceptionMapper = exceptionMapper;
    }

    @Override
    public void getCustomer(
            GetCustomerRequest request,
            StreamObserver<Customer> responseObserver) {

        ServerCallStreamObserver<Customer> serverObserver =
                (ServerCallStreamObserver<Customer>) responseObserver;
        Context callContext = Context.current();
        AtomicBoolean cancelled = new AtomicBoolean(
                callContext.isCancelled());
        AtomicBoolean terminated = new AtomicBoolean(false);

        serverObserver.setOnCancelHandler(() -> cancelled.set(true));
        Executor contextAwareExecutor =
                callContext.fixedContextExecutor(customerBlockingExecutor);

        try {
            contextAwareExecutor.execute(() -> {
                if (cancelled.get() || callContext.isCancelled()) {
                    return;
                }

                try {
                    Customer customer = applicationService.findBlocking(
                            request.getCustomerId());

                    if (cancelled.get() || callContext.isCancelled()) {
                        return;
                    }
                    if (terminated.compareAndSet(false, true)) {
                        responseObserver.onNext(toProto(customer));
                        responseObserver.onCompleted();
                    }
                } catch (Exception failure) {
                    if (!cancelled.get()
                            && !callContext.isCancelled()
                            && terminated.compareAndSet(false, true)) {
                        responseObserver.onError(
                                exceptionMapper.map(failure));
                    }
                }
            });
        } catch (RejectedExecutionException overloaded) {
            if (terminated.compareAndSet(false, true)) {
                responseObserver.onError(
                        Status.RESOURCE_EXHAUSTED
                                .withDescription(
                                        "Server is temporarily at capacity")
                                .asRuntimeException());
            }
        }
    }
}
```

This is a unary pattern with one worker task and one place emitting the terminal response. Imports, mappers, and beans must match your application. Key points:

- The handler returns quickly after submitting the task; blocking JDBC/SDK work runs on the dedicated pool.
- `fixedContextExecutor` reattaches the captured gRPC Context so the worker can read the deadline, cancellation state, and per-RPC data.
- The cancellation handler only sets a flag; it does not call the response observer from the cancellation thread.
- `terminated` prevents competing branches from emitting multiple terminal signals.
- Rejections are handled immediately with an overload status; caller-runs is never used.

`StreamObserver` is not thread-safe by default. If multiple workers can send responses, calls to `onNext`, `onError`, and `onCompleted` must be serialized. With a single-worker unary RPC, only that worker emits the response; the cancellation callback only updates a flag.

Cancellation can happen right as the worker finishes. Checking flags reduces wasted work, though it does not make cancellation strictly synchronous; the transport may still have closed the call before the worker sends. Therefore, maintain terminal state, apply dependency timeouts, and handle errors when a call has already ended.

## 6. Deadlines Must Follow the Blocking Operation

Offloading to a worker must not lose the caller's deadline. Capture `Context` before submitting and read the remaining deadline inside the worker:

```java
import io.grpc.Context;
import io.grpc.Deadline;
import io.grpc.Status;
import java.util.concurrent.TimeUnit;

Deadline deadline = Context.current().getDeadline();
long configuredLimitNanos =
        TimeUnit.SECONDS.toNanos(2);
long cleanupReserveNanos =
        TimeUnit.MILLISECONDS.toNanos(50);

long usableBudgetNanos = configuredLimitNanos;
if (deadline != null) {
    long remainingNanos =
            deadline.timeRemaining(TimeUnit.NANOSECONDS);
    usableBudgetNanos = Math.min(
            configuredLimitNanos,
            remainingNanos - cleanupReserveNanos);
}

if (usableBudgetNanos <= 0) {
    throw Status.DEADLINE_EXCEEDED
            .withDescription("Request deadline exceeded")
            .asRuntimeException();
}
```

Then apply the budget to the dependency:

- Downstream gRPC: `stub.withDeadlineAfter(usableBudgetNanos, NANOSECONDS)`.
- HTTP client: connect, response, and read timeouts must not exceed the remaining budget.
- JDBC: query/statement timeout and transaction timeout adjusted to driver resolution.
- External SDK: configure its timeout if supported by the SDK.

Do not let an RPC with an 800 ms deadline invoke an HTTP client with a 10-second timeout. Once the client stops waiting, the worker can still hold a thread and connection if the dependency lacks a matching timeout.

If the caller provides no deadline, still enforce a maximum service timeout. Never treat a null deadline as permission to let a blocking call run indefinitely.

## 7. Cancellation Does Not Automatically Stop Every Blocking API

When a client cancels an RPC or the deadline expires, the gRPC Context is marked cancelled. Workers must check this state before starting new operations and after dependencies return results. However:

- A JDBC driver may require a query timeout or statement cancellation.
- An HTTP client needs its own cancellation API.
- An SDK may not support interruption.
- `Future.cancel(true)` only sends an interrupt; application code and libraries must cooperate with interrupts.

If the application retains a `Future` or task handle, the cancellation handler can request task cancellation. Even so, timeouts at the dependency layer are still essential because interrupts do not guarantee an immediate stop to socket or database calls.

Never call `onNext`, `onError`, or `onCompleted` after the call has been cancelled. During cleanup, release resources and transactions; do not commit an operation merely because the worker reached the end if the deadline/cancellation policy requires stopping.

## 8. When Should You Use Non-Blocking APIs?

If a downstream dependency already provides an asynchronous API, you typically do not need to tie up a worker thread just to wait:

```java
import java.util.concurrent.CompletionStage;

CompletionStage<Customer> result =
        customerClient.findAsync(customerId);

result.whenCompleteAsync((customer, failure) -> {
    if (failure != null) {
        responseObserver.onError(exceptionMapper.map(failure));
        return;
    }
    responseObserver.onNext(toProto(customer));
    responseObserver.onCompleted();
}, responseExecutor);
```

This example uses `whenCompleteAsync` to choose the executor that runs the callback. Production code needs cancellation propagation, deadline checks, and terminal guards just like the worker pool pattern. Never call `result.get()` or `result.join()` inside the handler; doing so turns an async API into a blocking one.

Non-blocking does not mean unlimited concurrency. You still need to bound in-flight requests, memory held by pending futures, and backpressure toward dependencies.

## 9. Streaming Requires Flow Control as Well

For server streaming or bidirectional streaming, moving a blocking producer off the event loop only decides where it runs; it does not regulate sending speed.

Use `ServerCallStreamObserver.isReady()` and `setOnReadyHandler()` so the producer emits only when the transport is ready:

```java
import io.grpc.stub.ServerCallStreamObserver;

ServerCallStreamObserver<Update> serverObserver =
        (ServerCallStreamObserver<Update>) responseObserver;

serverObserver.setOnReadyHandler(() -> {
    while (serverObserver.isReady() && hasNextUpdate()) {
        serverObserver.onNext(nextUpdate());
    }
});

serverObserver.setOnCancelHandler(this::stopProducer);
```

This is an outline: a real producer must ensure only one thread emits messages on the observer at a time. If `onReady` schedules the producer onto a worker, serialize those runs and stop the producer on cancellation. Flow control regulates outbound messages; the worker pool bounds blocking work. Both mechanisms complement each other.

For client streaming, if each `onNext` needs a synchronous database call, do not block the callback thread. You can enqueue each message onto a worker queue, but you must bound the number of queued messages and preserve ordering if business logic requires it. When the queue is full, apply an explicit policy: reject the call, pause reading, or throttle upstream; never queue without bound.

## 10. Avoiding Common Design Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling JDBC on the Netty event loop | Blocks I/O for many channels | Offload to a worker pool |
| Using direct executor for blocking handlers | Callbacks may run on transport threads | Use an appropriate application executor |
| Unbounded worker pool | Excessive thread/queue growth, downstream overload | Use a bounded pool and queue |
| Using `CallerRunsPolicy` | Blocking tasks can run on sensitive submitter threads | Use `AbortPolicy` and map rejections |
| Using `DiscardPolicy` | RPCs may never terminate | Report overload explicitly |
| Waiting on futures with `get`/`join` | Holds threads while waiting on I/O | Compose callbacks/`CompletionStage` |
| Not propagating deadlines | Workers keep running after caller expires | Propagate timeouts to dependencies |
| Relying only on interrupts | Blocking drivers may not stop | Use dependency timeouts and cancel APIs |
| Multiple workers calling observer concurrently | Undefined response order and terminal signals | Serialize output and guard terminal state |
| Offloading streaming without flow control | Producers can accumulate messages too fast | Use readiness/backpressure |

## 11. Testing and Observability

### Testing Thread Separation

With a real Netty transport, record the thread name inside the handler and inside the blocking operation. Use a prefix such as `customer-blocking-` to confirm the operation was offloaded. In-process transport is useful for testing statuses and lifecycles, but it does not prove Netty event-loop behavior; thread isolation tests must run against the Netty transport.

### Testing Overload, Deadlines, and Cancellation

| Case | Expectation |
| --- | --- |
| Worker pool has capacity | Blocking operation runs on a worker thread |
| Worker queue is full | RPC terminates promptly with the defined overload status |
| Caller deadline is shorter than default dependency timeout | Dependency timeout is shortened to match caller budget |
| Client cancels while task waits in queue | Task skips work if cancellation is already observed |
| Client cancels while JDBC is running | Statement/query times out or cancels where supported by the driver |
| Worker throws an exception | Mapper converts it to a status; RPC does not hang |
| Two branches race to finish | Only one terminal response is emitted |
| Streaming client reads slowly | Producer respects readiness/backpressure |

### Metrics to Monitor

- Active threads, queue depth, and rejection count for the blocking pool.
- Queue wait time separately from execution time.
- JDBC connection pool active/idle/pending counts and query latency.
- HTTP/downstream connection pools, timeouts, and cancellation rates.
- Number of RPCs expiring while workers are still running.
- Netty event-loop CPU and transport latency.
- Number of streaming messages delayed due to not-ready.

If the worker queue grows while the event loop remains healthy, the bottleneck is in application or dependency capacity. If event-loop CPU or I/O latency spikes unusually, check whether a custom callback or direct executor is running blocking code on transport threads.

## 12. Self-Practice

1. In the default gRPC Netty setup, why must you distinguish the server application executor from the Netty event loop before deciding to offload?
2. Why can `CallerRunsPolicy` bring a blocking call back onto the very thread you are trying to protect?
3. Design a bounded worker pool for JDBC with a finite queue and a status mapping for rejections.
4. A client cancels an RPC while a JDBC query is running. How do you combine gRPC Context, query timeouts, and statement cancellation?
5. For client streaming, how do you bound the number of messages waiting for workers while still preserving processing order?

**Key takeaway:** Separate blocking calls from the event loop by reserving the Netty event loop for transport I/O and moving synchronous JDBC/HTTP/SDK work onto bounded worker pools or non-blocking APIs. Do not use `directExecutor()` for blocking handlers, do not use `CallerRunsPolicy`, and always propagate deadlines and cancellation to dependencies. For streaming, combine worker isolation with flow control and serialize response observer calls.
