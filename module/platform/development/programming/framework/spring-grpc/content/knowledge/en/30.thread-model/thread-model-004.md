# Executor for Service Implementation

In gRPC Java, the service implementation handles requests on an executor managed by the server. The executor determines which threads run business callbacks, how many tasks are processed concurrently, and how long requests wait when the system is busy. Choosing an appropriate executor helps Spring gRPC maintain stable latency, prevents one blocking service from stalling the entire server, and keeps resources under control as load increases.

ServerBuilder.executor(Executor) configures the executor used to execute application call work on the server. This is the **executor for service handlers**, not an executor for arbitrarily running all application tasks. In a Spring application, the server is typically created by a starter or auto-configuration; you need to supply the executor to the server builder through the extension point supported by your integration version. If not configured, gRPC/the framework uses its default executor; exact characteristics depend on the transport and starter.

## 1. Where Does the Executor Sit in the RPC Processing Flow?

When a client sends an RPC, the transport receives HTTP/2 data, decodes frames, and hands the request off to the service. Business logic execution is dispatched through the server's executor:

~~~mermaid
flowchart LR
    C["gRPC client"] --> T["HTTP/2 transport"]
    T --> D["Dispatch application call"]
    D --> E["Server application executor"]
    E --> H["Service implementation"]
    H --> DB["Database / downstream"]
    H --> R["Response observer"]
    R --> T
    T --> C
~~~

The transport and the application executor have distinct roles. The transport is responsible for I/O and the protocol; the service executor runs business callbacks. Heavy blocking work should not run directly on the transport's event loop or I/O threads.

Having an executor does not mean each RPC is pinned to one fixed thread for its entire lifetime. A single call can trigger multiple callbacks; gRPC dispatches them according to the server's execution model. Application code should not rely on thread affinity unless explicitly guaranteed by the API.

## 2. Configuring an Executor on gRPC ServerBuilder

For a gRPC Java server created directly, you can pass an ExecutorService to the builder:

~~~java
ThreadPoolExecutor grpcServiceExecutor =
    new ThreadPoolExecutor(
        16,
        32,
        60,
        TimeUnit.SECONDS,
        new ArrayBlockingQueue<>(400),
        runnable -> {
            Thread thread = new Thread(
                runnable,
                "grpc-service-" + SERVICE_THREAD_COUNTER.incrementAndGet());
            thread.setDaemon(false);
            return thread;
        },
        new ThreadPoolExecutor.AbortPolicy());

Server server = ServerBuilder.forPort(9090)
    .executor(grpcServiceExecutor)
    .addService(new InventoryServiceImpl())
    .build()
    .start();
~~~

This example illustrates the gRPC Java API; SERVICE_THREAD_COUNTER is an AtomicInteger declared by the application. In Spring, define the executor as a bean and configure the server builder through the integration point provided by your starter. Do not create a new thread pool per RPC or per service instance.

If the starter auto-creates the server and registers services via annotations, look up the exact ServerBuilder customizer/configurer mechanism provided by that version. Interface names and customizer ordering can differ across integration libraries; do not copy a configuration class from another starter without verifying it.

## 3. Managing the Executor as a Spring Bean

An executor is a lifecycle-managed resource. Spring should create a shared pool for the server and shut it down when the application context closes:

~~~java
@Configuration
public class GrpcExecutorConfiguration {

    @Bean(destroyMethod = "shutdown")
    public ExecutorService grpcServiceExecutor() {
        return new ThreadPoolExecutor(
            16,
            32,
            60,
            TimeUnit.SECONDS,
            new ArrayBlockingQueue<>(400),
            new ThreadFactoryBuilder()
                .setNameFormat("grpc-service-%d")
                .build(),
            new ThreadPoolExecutor.AbortPolicy());
    }
}
~~~

ThreadFactoryBuilder in the example is from Guava; you can replace it with a custom ThreadFactory if the project does not use Guava. The bean must be wired into the actual server builder. Merely declaring the bean without configuring the server to use it does not change gRPC's executor.

During shutdown, stop accepting new requests first, give in-flight RPCs time to finish, and then shut down the executor. If the grace period expires, call shutdownNow() and monitor remaining tasks. Do not shut down a shared executor before the gRPC server stops dispatching callbacks.

## 4. Choosing Pools by Workload Characteristics

No single pool size is optimal for every service. First classify the work:

| Workload Type | Characteristics | Executor Guidance |
| --- | --- | --- |
| CPU-bound | Computation, extra serialization, encryption, or in-memory data processing | Pool sized close to available cores; avoid creating too many threads competing for CPU |
| Blocking I/O | JDBC, files, blocking HTTP clients, or calling blocking stubs | May need more workers than cores, but must be bounded by connection pool and downstream capacity |
| Long-running background tasks | Exports, batch jobs, large file processing | Separate pool, queue, and concurrency limit; do not starve workers serving short RPCs |
| Fast callbacks | Validation, request/response mapping, dispatching | Keep callback execution short so workers quickly return to serve the next call |

If all handlers share a single pool, a batch of requests waiting on a slow database can occupy every worker and force fast read RPCs to queue as well. Separating executors by workload type limits cross-impact.

Example of separating an executor for blocking I/O work:

~~~java
@Bean(destroyMethod = "shutdown")
ExecutorService reportIoExecutor() {
    return new ThreadPoolExecutor(
        8,
        24,
        30,
        TimeUnit.SECONDS,
        new ArrayBlockingQueue<>(100),
        new ThreadFactoryBuilder()
            .setNameFormat("report-io-%d")
            .build(),
        new ThreadPoolExecutor.AbortPolicy());
}
~~~

A service handler can offload part of its work to reportIoExecutor, but it must manage deadlines/cancellation and asynchronous results. Do not let the handler wait indefinitely on Future.get(); set a deadline on the RPC and a dedicated wait time aligned with the remaining budget.

## 5. Avoiding Deadlocks When Sharing a Pool

A common mistake is a handler running on a pool of size N, submitting child tasks to that same pool, and blocking on the result. If N handlers do this concurrently, every worker can be held by parent tasks while child tasks sit in the queue. With no workers left to run the child tasks, the system deadlocks due to thread starvation.

~~~mermaid
flowchart TD
    A["N handlers occupy N workers"] --> B["Each handler submits a child task"]
    B --> C["Handlers block waiting on Future"]
    C --> D["Child tasks sit in the queue"]
    D --> E["No free workers remain"]
    E --> F["Thread starvation / deadlock"]
~~~

Ways to avoid this:

- Use async composition instead of blocking on child tasks.
- Use a separate executor for blocking/downstream tasks.
- Never submit child tasks into the same pool whose workers are blocked waiting for them.
- Limit fan-out and concurrent tasks per request.
- Set deadlines and cancellation for both parent and child tasks.

Separating pools does not automatically solve every deadlock; you still need to check dependency chains across executors, connection pools, and downstream services.

## 6. Propagating gRPC Context When Offloading Tasks

Context.current() is bound to the current callback execution thread. When a handler moves work to another executor, the context does not automatically appear on the new thread. If the child task calls a downstream gRPC service or needs to check cancellation, capture the context before submitting:

~~~java
Context rpcContext = Context.current();

reportIoExecutor.execute(rpcContext.wrap(() -> {
    if (rpcContext.isCancelled()) {
        return;
    }

    ReportData data = reportRepository.load(request);

    if (!rpcContext.isCancelled()) {
        downstreamStub.withDeadlineAfter(
            300, TimeUnit.MILLISECONDS)
            .enrich(toRequest(data));
    }
}));
~~~

The 300 ms budget is just an example; the downstream call must also obey the parent deadline. You can use a context-bound executor:

~~~java
Context rpcContext = Context.current();
Executor contextualExecutor =
    rpcContext.fixedContextExecutor(reportIoExecutor);

contextualExecutor.execute(() -> processReport(request));
~~~

If a task may run for a long time, register a cancellation listener to cancel the Future, close resources, or stop the producer. Context cancellation does not automatically interrupt every thread and does not automatically stop JDBC/HTTP I/O.

## 7. Bounded Queues and Overload Behavior

A pool with an unbounded queue can keep accepting requests even when processing rate falls below arrival rate. As the queue grows, latency climbs, requests hit their deadlines before being processed, and memory is consumed by waiting tasks.

Size a bounded queue based on:

- Maximum waiting requests permitted by the SLA.
- Average and p95/p99 processing times.
- Worker count and database/downstream capacity.
- Memory required per queued task.

When the queue is full, you need a clear load-shedding policy. AbortPolicy causes execute to throw RejectedExecutionException; you must know how your gRPC server/starter handles dispatch exceptions and translate overload into controlled behavior. Avoid defaulting to CallerRunsPolicy for a handler executor if tasks can block, as it can push work back onto the thread calling execute and stall the dispatch/transport thread depending on the call path.

You can combine admission control, per-method/per-tenant concurrency limits, and an appropriate overload status such as RESOURCE_EXHAUSTED. Never turn the queue into a holding pen where requests wait longer than the caller's deadline.

## 8. Callbacks and Streaming Should Not Hold Workers in Wait Loops

With async stubs or streaming RPCs, callbacks can be invoked multiple times over a call's lifecycle. Do not hold a worker in a polling loop waiting for messages or sleeping. Process messages inside short callbacks, offload heavy work to an appropriate executor, and manage backpressure.

For server streaming, if the producer is faster than the consumer, bound queues and respect ServerCallStreamObserver readiness/backpressure. Never let each stream spawn an unbounded queue or a dedicated forever-running thread.

The executor for service implementations is responsible for application callbacks; executors for producers, I/O, or background tasks can be separate pools. Clearly define who owns each task, who cancels it, and who closes resources when the RPC completes or is cancelled.

## 9. Observing and Tuning Executors

Monitor per server and per service group:

- Active workers, pool size, and idle/waiting workers.
- Queue depth, queue wait time, and rejected task count.
- Handler execution time, broken down by method.
- Rates of DEADLINE_EXCEEDED, CANCELLED, and RESOURCE_EXHAUSTED.
- CPU, memory, context switches, and GC pauses.
- JDBC/HTTP connection pool utilization and downstream wait times.
- Number of tasks still running after an RPC has been cancelled.

If the queue grows while CPU is low, workers may be blocked on I/O or constrained by a connection pool. If CPU stays high and the queue grows, review computation costs, worker count, and concurrency limits. Never blindly increase maxPoolSize without checking database and downstream capacity.

## 10. Testing the Executor for Service Implementations

Tests should verify:

1. The server builder actually uses the configured executor.
2. Handlers run on threads with the expected name/prefix.
3. The pool does not exceed configured worker and queue bounds.
4. A full queue produces controlled overload behavior without stalling the transport.
5. Blocking handlers do not exhaust the pool serving fast RPCs.
6. Context deadline/cancellation is propagated when tasks move to another executor.
7. Spring shutdown stops the server before closing the executor and leaves no stray threads behind.

You can use an in-process server, an executor with distinct thread names, and latches to control ordering. With Spring integration tests, boot the application context to verify the executor bean is actually wired into the server builder, not merely present in the context.

## 11. Takeaways and Self-Check

The **executor for service implementation** is where gRPC Java dispatches application callbacks on the server. Choose pools by workload type, keep queues bounded, separate blocking I/O from short callbacks, avoid handlers blocking on child tasks in the same pool, and propagate Context when offloading. In Spring, the executor must be managed with a bean lifecycle and actually attached to the server builder used by the starter.

Self-check:

1. Which part of gRPC server processing does ServerBuilder.executor(...) control?
2. Why can a single pool become exhausted when many handlers wait on blocking I/O?
3. What scenario causes thread starvation when a handler submits child tasks to the same pool running the handler?
4. Why must Context be propagated when offloading to another executor?
5. How do bounded queues and load shedding protect deadlines, memory, and downstream services?

A properly designed executor helps Spring gRPC allocate threads in a controlled way, keeps callbacks responsive, and prevents one slow workload from degrading the entire service.
