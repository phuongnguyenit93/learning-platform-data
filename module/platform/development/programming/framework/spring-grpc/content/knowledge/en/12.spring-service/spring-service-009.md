# Blocking Handlers and the Thread Model

## Lesson Objectives

In **SPRING_GRPC**, an RPC handler may call a JPA repository, an HTTP client, or another gRPC service. These calls typically wait on I/O. If the thread model is misunderstood, a slow handler can exhaust all RPC processing threads, forcing other requests to wait and driving up timeout rates.

This lesson focuses on **blocking handlers and the thread model**: distinguishing transport I/O threads from the executor that runs application callbacks, understanding the cost of blocking operations, knowing when synchronous handling makes sense, and knowing when to offload to a bounded executor.

After this lesson, you will be able to:

1. Distinguish between the Netty event loop, the gRPC application executor, and Spring business executors.
2. Explain why a blocking RPC handler occupies a worker while waiting on a dependency.
3. Choose between synchronous and asynchronous handling based on workload characteristics.
4. Offload blocking I/O using a bounded executor with explicit queue capacity and rejection policy.
5. Preserve gRPC `Context`, cancellation, and response write ordering when switching threads.
6. Handle streaming without pinning workers or emitting unbounded data.
7. Measure queueing, dependency time, saturation, and deadlines to locate bottlenecks.

> **Scope:** Examples use gRPC Java with official Spring gRPC. Server executor configuration details depend on the server factory and library version; this lesson does not assume a single Spring property across all transports.

## 1. Three Thread Groups to Distinguish

In a gRPC server running on Netty, work is typically divided across several thread groups:

| Group | Responsibility | What to Avoid |
| --- | --- | --- |
| **Transport event loop** | Network reads/writes, socket events, and HTTP/2 framing | Never run DB queries, synchronous HTTP calls, or long tasks on the event loop |
| **gRPC application executor** | Execute service callbacks such as unary methods or stream message callbacks | Never let all workers get tied up by slow, unbounded blocking I/O |
| **Business executor** | Run blocking tasks or CPU-bound work isolated by application policy | Never use unbounded pools or share indiscriminately with unrelated workloads |

The transport event loop is not the same thing as the thread running `getProduct(...)`. In standard server configurations, gRPC dispatches application callbacks onto a dedicated executor. However, low-level `directExecutor()` configuration can run callbacks directly on transport threads. Therefore, never assume every handler is automatically isolated from the event loop; verify the actual server configuration.

In gRPC Java, `ServerBuilder.executor(...)` configures the application callback executor at the builder level. Spring gRPC creates servers through a server factory; how you customize the executor depends on the factory/transport and version in use. When customization is needed, use the extension point supported by that version's documentation rather than guessing an unverified property.

## 2. How Does a Blocking Handler Consume Workers?

Example of a unary handler calling a synchronous service:

```java
@GrpcService
public class ProductGrpcEndpoint
        extends ProductGrpc.ProductImplBase {

    private final ProductService service;

    public ProductGrpcEndpoint(ProductService service) {
        this.service = service;
    }

    @Override
    public void getProduct(
            GetProductRequest request,
            StreamObserver<ProductReply> responses) {
        try {
            // Synchronous repository/JPA call that may wait on the database.
            ProductView product = service.getProduct(request.getProductId());

            responses.onNext(toProto(product));
            responses.onCompleted();
        } catch (ProductNotFoundException ex) {
            responses.onError(Status.NOT_FOUND
                    .withDescription("Product not found")
                    .asRuntimeException());
        }
    }
}
```

When the `getProduct` callback starts, an application worker executes the method. If `service.getProduct(...)` waits 180 ms on the database, that worker cannot concurrently handle another callback on the same thread. Once the call returns, the handler maps the response and completes.

This is **not inherently a bug**. A short, bounded synchronous handler can be simple, readable, and completely sufficient. Problems emerge when RPC concurrency grows, wait times become erratic, or the pool cannot absorb latency spikes.

### 2.1. Estimating the Impact of Wait Time

Suppose an executor has 16 workers and each handler holds a worker for 200 ms on average. If all workers stay nearly saturated, raw worker capacity is roughly:

```text
16 workers / 0.2 seconds ≈ 80 operations per second
```

This is only a back-of-the-envelope estimate of worker occupancy, not a guaranteed throughput. Queueing time, CPU, serialization, database connection pools, lock contention, and latency variance will all make real numbers differ.

When every worker is busy:

1. New callbacks must wait in a queue or get rejected per the executor's policy.
2. Queue wait time plus processing time increases RPC latency.
3. Client deadlines may expire before the handler even runs or before dependencies reply.
4. Uncontrolled retries can amplify load and trigger an overload spiral.

### 2.2. Not Every Synchronous Handler Must Be Offloaded

Keeping a handler synchronous is usually appropriate when:

- The use case is short with predictable maximum duration.
- Dependencies have explicit timeouts.
- The server executor is sized for load and properly monitored.
- Offloading would add queueing, context propagation, and synchronization overhead with no clear benefit.

Consider offloading when:

- The handler calls blocking systems with high or volatile latency.
- You need to isolate I/O load from gRPC's callback executor.
- You want to bound concurrent blocking operations independently of the transport.
- You have explicit overload, timeout, and cancellation policies.

Never offload merely to make a method look "asynchronous." Offloading does not make a dependency faster; it only shifts where threads are consumed and helps contain resources if the pool is properly designed.

## 3. Identifying Common Blocking Sources

| Call / Work | Why Can It Block? | How to Control |
| --- | --- | --- |
| Spring Data JPA/JDBC | Waiting for a connection, query, lock, or database response | Bound connection pool, set query timeouts, add indexes, keep transactions short |
| Synchronous HTTP client | Waiting on DNS, connect, response headers, or body | Connect/read timeouts, connection pooling, deadlines, and circuit breakers |
| gRPC blocking stub | Waiting for downstream response | Set per-call deadlines; classify `DEADLINE_EXCEEDED`/`UNAVAILABLE` |
| File I/O | Waiting on filesystem or storage device | Bound concurrency, apply timeouts where applicable, use suitable APIs |
| `Thread.sleep()` / lock wait | Holds the thread without doing useful work | Eliminate artificial sleeps; shorten critical sections |
| Heavy CPU computation | Does not wait on I/O but saturates CPU | Profile CPU; consider a dedicated CPU executor with bounded concurrency |
| `Future.get()` or `join()` | Current thread blocks waiting for an incomplete result | Use end-to-end async composition or a bounded blocking pool |

A handler calling multiple dependencies sequentially holds a worker for the sum of their wait times. If calls are independent, you can consider running them in parallel—only with bounded concurrency and safe result aggregation. Never use `parallelStream()` or the common pool as a default offload mechanism.

## 4. Model A: Synchronous Execution on the RPC Application Executor

This is the simplest model: the handler calls the application service, waits for the result, and sends the response.

```java
@Override
public void getProduct(
        GetProductRequest request,
        StreamObserver<ProductReply> responses) {
    try {
        ProductView view = service.getProduct(request.getProductId());
        responses.onNext(toProto(view));
        responses.onCompleted();
    } catch (ProductNotFoundException ex) {
        responses.onError(Status.NOT_FOUND
                .withDescription("Product not found")
                .asRuntimeException());
    } catch (RuntimeException ex) {
        log.error("getProduct failed", ex);
        responses.onError(Status.INTERNAL
                .withDescription("Unable to process request")
                .asRuntimeException());
    }
}
```

This model has clear advantages: sequential control flow, no cross-thread completion callback coordination, and the application service's transaction can commit before the adapter emits the response when transactions are placed properly in the service.

However, you must bound wait times across every dependency. If a handler can block indefinitely, the executor can exhaust its workers even under modest traffic. A client-side deadline does not automatically guarantee an in-flight JDBC query aborts immediately; you need timeouts or cancellation at the database/client layer.

## 5. Model B: Offloading Blocking I/O to a Bounded Executor

When blocking work must be isolated from the gRPC application executor, use a dedicated pool. The pool must bound both thread count and queue capacity so the system has a clear breaking point under overload.

### 5.1. Declaring a Spring Executor

Example configuring a `ThreadPoolTaskExecutor` for blocking operations:

```java
@Configuration
public class GrpcWorkExecutorConfiguration {

    @Bean(name = "grpcBlockingExecutor")
    public ThreadPoolTaskExecutor grpcBlockingExecutor() {
        var executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("grpc-blocking-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
```

These numbers are only illustrative starting values. Size them according to dependency latency, connection pool limits, and measured load. If the database only grants 12 connections for this workload, creating 50 blocking workers just creates more threads waiting for connections. An oversized queue also makes requests wait so long that their deadlines expire before work even starts.

### 5.2. Submitting Work to the Pool and Completing the Response

The snippet below illustrates a unary RPC. `Context` is captured before offloading and wraps the completion callback so the callback sees the original RPC's context.

```java
@GrpcService
public class ProductGrpcEndpoint
        extends ProductGrpc.ProductImplBase {

    private final ProductService service;
    private final Executor blockingExecutor;

    public ProductGrpcEndpoint(
            ProductService service,
            @Qualifier("grpcBlockingExecutor") Executor blockingExecutor) {
        this.service = service;
        this.blockingExecutor = blockingExecutor;
    }

    @Override
    public void getProduct(
            GetProductRequest request,
            StreamObserver<ProductReply> responses) {

        Context rpcContext = Context.current();

        try {
            CompletableFuture
                    .supplyAsync(
                            () -> service.getProduct(request.getProductId()),
                            blockingExecutor)
                    .whenComplete((product, failure) ->
                            rpcContext.wrap(() -> {
                                if (rpcContext.isCancelled()) {
                                    return;
                                }

                                if (failure != null) {
                                    responses.onError(toStatus(failure));
                                    return;
                                }

                                responses.onNext(toProto(product));
                                responses.onCompleted();
                            }).run());
        } catch (RejectedExecutionException ex) {
            responses.onError(Status.RESOURCE_EXHAUSTED
                    .withDescription("Server is overloaded")
                    .asRuntimeException());
        }
    }

    private Throwable toStatus(Throwable failure) {
        Throwable cause = failure;
        while (cause instanceof CompletionException
                && cause.getCause() != null) {
            cause = cause.getCause();
        }

        if (cause instanceof ProductNotFoundException) {
            return Status.NOT_FOUND
                    .withDescription("Product not found")
                    .asRuntimeException();
        }

        log.error("getProduct failed", cause);
        return Status.INTERNAL
                .withDescription("Unable to process request")
                .asRuntimeException();
    }
}
```

This is a structural example; add imports and mappers per your project. When `supplyAsync` is submitted, the handler returns quickly; blocking work runs on `grpc-blocking-*`. When the future finishes, the callback sends the response. If the pool rejects the task, the adapter returns `RESOURCE_EXHAUSTED` instead of spawning unbounded threads.

**Important notes:**

- `CompletableFuture` does not automatically make blocking tasks cancellable. `cancel(true)` does not guarantee JDBC or underlying libraries stop immediately.
- `Context.wrap(...)` restores gRPC `Context` inside the callback, but does not automatically propagate every application `ThreadLocal` across threads. Security contexts, tracing, and MDC require their own propagation mechanisms.
- When a client cancels an RPC, the example checks `rpcContext.isCancelled()` before sending a response. The blocking work may still be running; set database/downstream timeouts and use cancellation-aware APIs where available.
- `StreamObserver` must never be called concurrently from multiple threads. With a single future completion, the callback above has only one write path. If multiple result sources exist, serialize `onNext`, `onError`, and `onCompleted` calls.
- Never let an error callback fire after the observer has already terminated. Guard every terminal branch so it completes only once.

### 5.3. Separating Pools by Workload Type

You do not necessarily want just one executor. If your workload mixes blocking I/O and heavy CPU work, you can separate them:

| Pool | Characteristics | Examples |
| --- | --- | --- |
| Blocking I/O pool | High wait time; worker count aligned with dependency limits | JDBC, synchronous HTTP clients |
| CPU pool | Worker count close to CPU cores; avoid oversubscription | Cryptography, pure CPU calculations |
| gRPC application executor | Runs callbacks and coordinates RPCs | Request validation, fast application service calls, observer lifecycle |

Do not move every operation onto an I/O pool. Lightweight validation, Protobuf mapping, and very short logic can run directly on the callback executor. The goal is isolating blocking work intentionally, not adding another queue hop for every line of code.

## 6. Deadlines, Cancellation, and Context Across Thread Boundaries

### 6.1. A Deadline Is Not an Automatic Timeout for Every Dependency

A gRPC deadline bounds how long the client waits for the RPC. When the deadline expires, the server receives a cancellation signal in its context. Yet if the handler is stuck inside a JDBC query or HTTP call with no timeout, that call can keep running long after the client gave up.

Therefore, enforce budgets at every layer:

1. RPC deadline bounds the entire call from the client's perspective.
2. Database query/transaction timeout bounds DB wait time.
3. Downstream HTTP/gRPC deadlines are shorter than the remaining RPC budget.
4. Background work checks cancellation and exits early when APIs support it.

Never configure a downstream timeout longer than the remaining RPC deadline. Likewise, never blindly retry a write call without knowing whether the previous attempt committed; idempotency is required.

### 6.2. gRPC `Context` Does Not Propagate to Executors Automatically

`Context.current()` only returns the context attached to the thread executing at the moment of the call. When offloading to a thread pool, never assume the context appears automatically on the new thread. Capture the context before submitting and use `context.wrap(...)` or a gRPC context-propagating executor.

`Context` can carry deadlines, cancellation signals, and metadata placed by interceptors. For Spring Security, tracing, or MDC, configure their corresponding propagation mechanisms; gRPC `Context` and other `ThreadLocal`s are separate systems.

### 6.3. Cancellation Requires Cooperation from Dependencies

When cancellation occurs:

- Do not emit new responses if the RPC is already cancelled.
- Stop read/write loops or subscriptions if the data source supports cancellation.
- Use query timeouts, HTTP call timeouts, or downstream deadlines to bound in-flight operations.
- Release resources upon completion or cancellation.
- Never treat client cancellation as proof that a write operation definitely did not commit.

If a write already committed before cancellation was processed, the client may never receive the response even though data changed. Critical write requests should use idempotency keys and result lookup mechanisms for safe retries.

## 7. Thread Model in Streaming RPCs

### 7.1. Server Streaming

A synchronous server streaming handler can emit multiple responses in a loop. If each iteration queries a database or blocks on a downstream service, the application worker stays occupied for the entire duration.

For long streams, read in bounded pages/chunks and emit data according to flow control. `ServerCallStreamObserver` provides `isReady()` and `setOnReadyHandler(...)` so the application knows when the transport is ready for more data. You can also register `setOnCancelHandler(...)` to stop the data source when the client cancels.

The rule is **one serialized write flow per observer**. Never let an `onReady` callback and another worker call `onNext` concurrently without serialization.

### 7.2. Client Streaming

The handler method typically returns `StreamObserver<Request>` immediately to receive incoming messages. `onNext` may be invoked many times; if every invocation blocks on a database call, the callback executor can remain tied up for a long time.

You can process in chunks or dispatch tasks to a bounded executor, preserving order if the protocol requires it. Never spawn an unbounded future per message without capping in-flight tasks; if the client sends faster than the server processes, queues and memory will grow without bound.

### 7.3. Bidirectional Streaming

Both directions can operate concurrently. Receiving requests and emitting responses do not have to follow a strict 1:1 pairing. If requests are processed in parallel, responses may finish out of order; if ordering matters, serialize processing or attach sequence numbers and define explicit reordering rules.

For long-lived streams, never pin a thread just waiting for the next message. The handler can subscribe to an asynchronous source, accept messages, and send responses when data is ready. Still, data sources, executors, cancellation, and observers must all have clear lifecycles.

## 8. Backpressure and Resource Limits

Offloading to a pool does not solve overload if submitted task counts remain unbounded. A bounded queue merely gives the system a clear rejection point; it does not make dependencies faster.

Consider these limits together:

- **RPC concurrency:** number of active calls the server accepts.
- **Application executor:** concurrent callbacks and queue policy.
- **Blocking executor:** allowed concurrent blocking I/O tasks.
- **Database pool:** available connections.
- **Downstream pools:** connections and concurrency toward external services.
- **Message/stream limits:** request size, element count, and emission rate.

Once a queue is full, failing fast with a meaningful status is usually better than letting requests sit until deadlines expire. `RESOURCE_EXHAUSTED` can express resource limits; `UNAVAILABLE` may fit when a service temporarily refuses additional load. Choose statuses according to your API contract and client retry policies.

## 9. Measuring to Find the Real Bottleneck

Do not measure only total RPC latency. Break time down across layers:

| Metric | Question It Helps Answer |
| --- | --- |
| RPC duration and `deadline exceeded` | How long are clients waiting and how many requests expire? |
| Application executor active threads/queue | Are callbacks waiting for workers? |
| Blocking executor active threads/queue/rejections | Are blocking tasks saturating the pool? |
| Database connection wait/query duration | Is slowness caused by connection starvation, locks, or queries? |
| Downstream latency/errors | Is an external service causing handlers to hold workers? |
| Cancellation and in-flight RPCs | How much work keeps running after clients disconnect? |
| CPU utilization and GC | Is the bottleneck CPU/memory or I/O? |

Use thread name prefixes to identify pools in thread dumps. When the system slows down, a thread dump can reveal workers blocked on JDBC, socket reads, locks, or `Future.get()`. Combine that with queue metrics and dependency latencies to locate bottlenecks; never increase thread counts before knowing database/downstream limits.

## 10. Testing Blocking Behavior and Saturation

Several useful tests include:

1. **Synchronous handler:** use a fake dependency with a `CountDownLatch` to hold a call for a controlled period; observe the worker staying occupied until the latch releases.
2. **Bounded executor:** configure a small pool and small queue in tests; submit multiple blocking tasks to verify excess tasks are rejected per policy.
3. **Context propagation:** set a gRPC `Context` value before offloading; verify the completion callback reads that value after using `context.wrap(...)`.
4. **Cancellation:** cancel the RPC while work is pending; verify the adapter emits no response after cancellation and dependencies time out/cancel as designed.
5. **Streaming flow control:** create a slow-reading client; verify the server does not emit unboundedly and respects readiness/cancellation.
6. **Load testing:** ramp up concurrency, measuring p50/p95/p99, queue depth, rejections, DB wait times, and `deadline exceeded` counts—never rely solely on requests/second.

Unit testing an executor does not replace integration tests against a real server. Always verify the actual transport and server factory in use, since the thread model changes if executor or direct-execution settings differ.

## 11. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Other RPCs slow down when one dependency stalls | Blocking handlers exhaust application workers | Bound dependency duration, size executors, or offload to a bounded pool |
| Event loop thread freezes | Callbacks run inline/direct executor or blocking code runs on transport thread | Never use direct executor for blocking handlers; inspect server configuration |
| Adding threads still leaves DB slow | Worker count exceeds connection pool or DB capacity | Align concurrency with dependency limits; optimize queries |
| Queue grows continuously | Submission rate exceeds completion rate | Use bounded queues, admission control, and overload statuses |
| Client times out yet work keeps running | Deadlines do not auto-interrupt JDBC/HTTP calls | Enforce dependency timeouts/cancellation and check context |
| Callback misses metadata/security context | `ThreadLocal`/context not propagated | Capture gRPC `Context`; configure propagation for tracing/security/MDC |
| Response stream fails intermittently | Multiple threads call the same observer or send multiple terminal events | Serialize writes, keep single observer ownership, track terminal state |
| Client streaming spikes RAM | Spawning unbounded tasks per message or buffering entire stream | Cap in-flight tasks, chunk work, and apply flow control |
| Using the common pool impacts unrelated tasks | Blocking tasks starve shared workers | Use dedicated, bounded, instrumented executors |
| Retries worsen overload | Synchronized retries hit an already saturated server | Add backoff, jitter, retry budgets, and idempotency |

## 12. Hands-On Exercises

1. Measure a unary handler calling a synchronous repository. Record active workers and latency as concurrent clients increase.
2. Create a `ThreadPoolTaskExecutor` with 4 workers and a queue of 8 items. Simulate a slow dependency and verify rejection behavior once pool and queue fill up.
3. Offload a blocking call to a separate executor. Capture gRPC `Context` and check cancellation before sending the response.
4. Add database/downstream timeouts. Verify that client deadlines do not leave blocking tasks running indefinitely.
5. Switch server streaming to paged reads and readiness-aware emission. Test both a slow-reading client and a mid-stream cancellation.
6. For client streaming, cap concurrent in-flight messages and preserve ordering when required by the protocol.
7. Capture a thread dump under load; distinguish workers waiting on the DB, workers waiting downstream, and CPU-bound threads.

### Self-Check Questions

- How does the transport event loop differ from the gRPC application executor in responsibility?
- Why can a handler making synchronous JDBC calls cause other RPCs to wait?
- When is simple synchronous handling the right choice?
- Why does a bounded executor need both queue capacity and a rejection policy?
- Does `Context.current()` automatically appear on another executor thread?
- Does a gRPC deadline guarantee stopping a running SQL query?
- Why should `onNext` never be called concurrently from multiple threads?
- How must server streaming respect readiness and cancellation?
- Under what circumstances can increasing worker count actually slow down the database?

## References

- [gRPC Java — ServerBuilder](https://grpc.github.io/grpc-java/javadoc/io/grpc/ServerBuilder.html): configuring executors and server behavior.
- [gRPC Java — Context](https://grpc.github.io/grpc-java/javadoc/io/grpc/Context.html): context propagation, deadlines, and cancellation.
- [gRPC Java — ServerCallStreamObserver](https://grpc.github.io/grpc-java/javadoc/io/grpc/stub/ServerCallStreamObserver.html): readiness, cancellation, and flow control for server streaming.
- [gRPC — Deadlines](https://grpc.io/docs/guides/deadlines/): RPC time limits and propagation.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): configuring executors and task execution in Spring.

**Expected outcome:** Learners understand how blocking handlers consume application workers, distinguish application workers from transport event loops, know when to keep synchronous execution versus offloading to a bounded executor, and preserve `Context`, cancellation, response ordering, and flow control so Spring gRPC sustains low latency and reliability under load.
