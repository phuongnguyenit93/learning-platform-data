# Executor Sizing

**Executor sizing** is the practice of selecting thread counts, queue types, and pending task limits so gRPC handles RPCs reliably under expected load. In **SPRING_GRPC**, the executor affects queue wait time before handlers run, throughput, tail latency, CPU usage, memory, and resilience when downstream services slow down.

An undersized executor forces RPCs to queue even when CPU or dependencies still have capacity. An oversized executor can create excessive threads, context switching, stack memory overhead, and connection pool contention. An unbounded queue can turn a brief overload spike into prolonged latency or heap exhaustion. Sizing must therefore reflect workload type, concurrency, CPU quota, blocking time, and downstream limits.

## 1. Understanding which executor is being sized

In gRPC Java, distinguish the executor running application callbacks from threads handling transport I/O:

| Component | Role | Sizing considerations |
| --- | --- | --- |
| Server application executor | Runs server service implementations/callbacks | Size based on CPU work, blocking, and handler concurrency |
| Client application executor | Runs async client callbacks and some application tasks | Size based on callback volume, processing time, and client blocking |
| Transport event loop | Handles I/O, HTTP/2 frames, and network events | Managed by transport; never run blocking work here |
| Offload executor | Runs certain internal tasks that may block or do not fit the event loop, depending on API/runtime | Configure only when you understand the tasks and version guidance |
| Downstream pool | For example, JDBC connection pool or HTTP client pool | Separate capacity limit; do not uselessly size executors beyond downstream capacity |

`ServerBuilder.executor(Executor)` configures the executor for server application code. `ManagedChannelBuilder.executor(Executor)` configures the executor for client application callbacks. Exact APIs may differ when using a Spring gRPC starter; use the configuration mechanism of your starter/version while preserving the distinction between application executors and transport event loops.

Do not assume a single gRPC RPC always occupies a thread from start to finish. In async services, a thread can run a callback and return to the pool. A long-lived stream occupies a thread continuously only if the handler or callback performs blocking work or holds a thread in a loop.

## 2. Classifying workloads before picking thread counts

Sizing begins by identifying what handlers actually do:

| Workload type | Characteristics | Initial sizing direction |
| --- | --- | --- |
| CPU-bound | Computation, encryption, data transformation; minimal I/O wait | Thread count near available CPUs, tuned to target utilization |
| Blocking I/O | Waiting on JDBC, synchronous HTTP clients, files, or locks | May need more threads than CPUs, but bounded by downstream capacity |
| Non-blocking I/O | Async clients/reactive APIs, callbacks complete later | Does not need one thread per waiting request; size by callback work |
| Mixed workload | Both computation and blocking | Split executors by work type if practical |
| Streaming callback | Processes messages individually, possibly over long durations | Size by callback processing time and concurrent callbacks, not open stream count alone |

A service with 2,000 open streams does not necessarily need 2,000 threads. If streams are mostly idle and callbacks are brief, far fewer threads are needed. Conversely, just 100 concurrent RPCs can exhaust a pool if each handler holds a thread waiting on a database or synchronous downstream call.

## 3. Estimating threads for CPU-bound and blocking workloads

For CPU-bound tasks, concurrent thread count usually starts near the number of CPUs actually allocated to the process. Creating more CPU-bound threads than cores does not increase compute capacity; they mostly contend for CPU and add context switching.

For blocking workloads, a classic rule-of-thumb formula gives an initial estimate:

\[
N \approx N_{cpu} \times U_{cpu} \times
\left(1 + \frac{W}{C}\right)
\]

Where:

- \(N\): estimated thread count.
- \(N_{cpu}\): CPUs available to the process/container.
- \(U_{cpu}\): target CPU utilization, from 0 to 1.
- \(W\): average wait time per task.
- \(C\): actual CPU compute time per task.

For example, a container with 8 CPUs, target CPU utilization 0.8, 10 ms CPU time, and 30 ms I/O wait:

\[
N \approx 8 \times 0.8 \times (1 + 30/10)
  = 25.6
\]

You can start benchmarking around 24–26 threads for that workload. This is only an initial estimate, not a production default. If the downstream allows only 16 concurrent requests, a 26-thread pool merely queues extra threads waiting for connections without raising throughput. Bound concurrency at the right layer and re-measure.

### 3.1. Using actual CPU quotas

`Runtime.getRuntime().availableProcessors()` is a reference point, but confirm the JDK/container runtime correctly detects the CPU quota. A container might run on a 64-core host while only granted 4 CPUs. Sizing against host core counts creates an oversized pool.

When evaluating, record:

- Container CPU quota/limit and actual allocated CPUs.
- Core count visible to the runtime process.
- CPU utilization and throttling.
- Replica count and total cluster-wide concurrency.

Scaling replicas also multiplies total threads and downstream connections. Sizing one instance without accounting for cluster-wide load can overload databases or dependencies.

## 4. Bounding executors by downstream capacity

Executors do not create extra capacity in databases or downstream services. If each synchronous RPC checks out a JDBC connection, concurrent DB operations are limited by the connection pool and database capacity.

For example:

- Server executor has 64 threads.
- JDBC pool has 16 connections.
- Many handlers call the database synchronously at once.

At most ~16 handlers can hold DB connections simultaneously; the rest wait in the connection pool while still occupying executor threads. Active threads rise, queues grow, and latency spills over to other RPCs.

Define concurrency limits per dependency. You can place semaphores/admission control before blocking sections so only an appropriate number of tasks run concurrently. If the system has multiple dependencies, avoid one blanket limit that fails to distinguish them.

## 5. Bounded pools and bounded queues

In production, executors should define explicit bounds for:

- Core thread count.
- Maximum thread count.
- Queue capacity.
- Keep-alive for threads above core.
- Rejection/overload behavior.

Example using `ThreadPoolExecutor`:

```java
int coreThreads = 12;
int maxThreads = 24;
int queueCapacity = 128;

ThreadPoolExecutor grpcExecutor = new ThreadPoolExecutor(
    coreThreads,
    maxThreads,
    60,
    TimeUnit.SECONDS,
    new ArrayBlockingQueue<>(queueCapacity),
    runnable -> {
        Thread thread = new Thread(
            runnable,
            "grpc-app-" + THREAD_IDS.incrementAndGet());
        thread.setDaemon(false);
        return thread;
    },
    new ThreadPoolExecutor.AbortPolicy()
);
```

This illustrates the structure; numbers must be benchmarked. `THREAD_IDS` is an `AtomicInteger` declared at configuration scope. A bounded queue gives the system an observable overload boundary rather than holding unbounded tasks on the heap.

With `ThreadPoolExecutor`, once threads reach core size, tasks are queued first; only when the queue fills does the pool grow toward maximum threads. Consequently, an overly large queue delays tasks while the pool never scales up. Pick queue capacity from your wait-time budget and verify actual behavior.

### 5.1. Sizing queue capacity by latency budget

A queue is not an arbitrary backlog store. One way to estimate capacity is Little's Law:

\[
L = \lambda \times W_q
\]

Where \(L\) is average waiting tasks, \(\lambda\) is task arrival rate, and \(W_q\) is average wait time. If a service receives ~500 tasks/s and can afford only ~40 ms of queue wait, average waiting tasks are ~20. Real capacity must also account for bursts, service time, and variance; do not treat the average as the sole cap.

Large queues increase wait times and retain request contexts/payloads longer. If an RPC has only 100 ms of remaining deadline while sitting 300 ms in a queue, the work is already stale before the handler starts. Drop or reject expired work instead of wasting capacity processing it.

## 6. Rejection policies and load shedding

When both pool and queue are full, the system needs explicit overload behavior:

| Policy | Behavior | Evaluation for gRPC |
| --- | --- | --- |
| Abort/reject | Rejects submission with an exception | Makes overload observable; test how the gRPC runtime handles rejections |
| CallerRuns | Submitting thread runs the task itself | Dangerous if the caller is a transport/event-loop thread, as it blocks I/O |
| Discard | Drops the new task | Unsuitable for RPCs when silent work loss is unacceptable |
| DiscardOldest | Drops the oldest queued task | Can silently drop already accepted requests without caller awareness |

Never use `CallerRunsPolicy` as automatic backpressure for a server executor unless you have proven the caller is never a transport thread. Likewise, avoid discard policies for RPCs requiring reliable semantics.

Do not rely on `RejectedExecutionException` automatically mapping to a specific gRPC status. How the gRPC runtime reacts depends on where rejection happens and version behavior. If you need controlled overload statuses like `RESOURCE_EXHAUSTED` or `UNAVAILABLE`, enforce admission control at the application boundary/interceptor before dispatching heavy work, and integration-test the actual status returned.

Load shedding should be early and bounded: reject new requests when overloaded, preserve capacity for in-flight work, and prevent deep queues from degrading latency across the entire service.

## 7. Configuring executors in Spring

Application executors can be managed as Spring beans. Example with `ThreadPoolTaskExecutor`:

```java
@Configuration
class GrpcExecutorConfiguration {

    @Bean
    ThreadPoolTaskExecutor grpcServerExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(12);
        executor.setMaxPoolSize(24);
        executor.setQueueCapacity(128);
        executor.setKeepAliveSeconds(60);
        executor.setThreadNamePrefix("grpc-server-");
        executor.setRejectedExecutionHandler(
            new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }
}
```

Spring initializes `ThreadPoolTaskExecutor` via the bean lifecycle. It provides an `Executor` to pass into the gRPC server builder. Example integrating with the standard gRPC Java API:

```java
@Bean(destroyMethod = "shutdown")
Server grpcServer(
        @Qualifier("grpcServerExecutor") Executor grpcExecutor,
        GreeterService greeterService) throws IOException {

    return ServerBuilder.forPort(9090)
        .executor(grpcExecutor)
        .addService(greeterService)
        .build()
        .start();
}
```

This example uses standard gRPC Java APIs. If your starter manages the server itself, configure the executor via the starter's extension point rather than spinning up a second server. Property/annotation names depend on the starter and version; never copy configuration from another library without checking.

Ensure the server shuts down before the executor it uses. Through Spring's dependency graph, the server bean depends on the executor bean so Spring destroys the dependent bean before its dependency. With custom lifecycles, coordinate explicitly: stop accepting new RPCs, shut down the server, await active calls, and only then shut down the executor.

## 8. Separating executors for server, client, and blocking work

Not every task needs to run on one shared pool:

- Server application executor runs server callbacks/handlers.
- Client callback executor runs async stub callbacks when configured separately.
- Blocking I/O executor handles code that must wait on JDBC/HTTP/files.
- CPU executor handles heavy transforms or computation.

Separating pools keeps one blocking workload from starving threads needed by other callbacks. However, too many pools add threads, queues, and operational complexity. Split only when workloads or SLOs differ and metrics prove it necessary.

For example, a gRPC handler can offload blocking work to a dedicated bounded executor:

```java
blockingIoExecutor.execute(() -> {
    try {
        Item item = repository.findById(request.getItemId());
        responseObserver.onNext(toReply(item));
        responseObserver.onCompleted();
    } catch (Exception error) {
        responseObserver.onError(mapToGrpcStatus(error));
    }
});
```

This is an illustrative skeleton. Ensure the observer is emitted to from a single serialized execution path, handle cancellation/deadlines, and never send responses after the call has closed. If task submission is rejected, handle overload per contract; never swallow exceptions.

Do not casually use `ForkJoinPool.commonPool()` for blocking JDBC/HTTP calls. Blocking tasks can exhaust shared workers and impact unrelated work.

## 9. Avoiding starvation and deadlock

Some executor bugs stay hidden under light load and surface in production:

**Nested blocking calls on the same pool:** a handler holds a thread, submits a subtask to the same pool, and blocks on `Future.get()`. If all threads are occupied by parent handlers waiting on subtasks, subtasks have no threads to run; the pool deadlocks/starves.

**Blocking callbacks:** gRPC callbacks block on databases, locks, or slow networks, starving other callbacks of threads.

**One pool for all workloads:** heavy CPU tasks stall lightweight callbacks; blocking tasks exhaust workers.

**Overly deep queues:** threads may not even appear saturated yet RPCs still miss deadlines while queued.

**Excessive thread counts:** context switching and memory overhead climb, and downstream services get hammered.

Mitigations:

- Avoid submitting subtasks to the same pool and blocking on their completion.
- Use async/non-blocking APIs where feasible.
- Separate CPU-bound and blocking work when needed.
- Set deadlines on downstream calls and propagate cancellation.
- Use bounded queues and admission control.
- Capture thread dumps when latency climbs or workers remain `BLOCKED`/`WAITING`.

## 10. Streaming and thread occupancy duration

A bidirectional stream can live for minutes or hours. That does not mean a thread must stay pinned for the stream's lifetime. With gRPC Java's callback model, the application receives callbacks when messages or completion events arrive.

What occupies threads is the work done inside callbacks:

- Parsing/validating large messages.
- Synchronous database writes.
- Waiting for downstream responses.
- Tight loops emitting many messages continuously.
- Contending on locks or queues.

On high-message-frequency streams, short but dense callbacks can keep an executor continuously busy. Measure callback duration and message rate, not just active stream counts. Use manual flow control/backpressure so consumers do not receive messages faster than they can process them.

For outbound streams, avoid loops emitting large message volumes on a single worker without checking readiness. For inbound streams, never request more messages before the consumer has capacity when using manual flow control.

## 11. Client executors and async stub callbacks

Clients using async stubs execute callbacks when responses arrive. If callbacks perform blocking work or heavy payload processing, consider configuring a dedicated client application executor:

```java
ExecutorService clientCallbacks =
    new ThreadPoolExecutor(
        4,
        8,
        60,
        TimeUnit.SECONDS,
        new ArrayBlockingQueue<>(64));

ManagedChannel channel = ManagedChannelBuilder
    .forAddress("catalog.internal", 8443)
    .useTransportSecurity()
    .executor(clientCallbacks)
    .build();
```

This example only illustrates the API and bounds; production needs thread factories, rejection policies, and lifecycle management for both executor and channel. The client callback executor is not the transport event loop. Never share one executor between server and client if sharing allows one side to starve the other's threads.

If callbacks merely forward results into a reactive pipeline or bounded queue, a small pool may suffice. If callbacks perform blocking I/O, offload blocking work to an appropriate pool rather than holding callback threads while waiting.

## 12. Deadlines, cancellation, and context propagation

A task waiting in an executor queue may no longer be useful once the RPC deadline expires or the caller cancels. Before performing expensive work, check call context/cancellation and propagate remaining deadlines downstream.

gRPC Java uses `io.grpc.Context` to propagate certain call-scoped context. However, framework `ThreadLocal` values such as MDC or security context do not automatically cross every executor boundary. If you need correlation IDs, principals, or tracing context, use interceptors/context propagation mechanisms appropriately and test on the callback execution thread.

When handing tasks off to a separate executor:

- Capture context when the RPC arrives.
- Restore context when the task executes via supported APIs.
- Clear context after task completion to prevent cross-request leakage.
- Cancel tasks whenever cancellation can propagate safely.
- Do not retain sensitive requests/credentials in queues longer than needed.

## 13. Measurement-driven sizing process

Never pick thread counts by guesswork. A practical workflow:

1. **Build a workload profile:** separate unary and client/server/bidi streaming; measure CPU, blocking, and payload ratios.
2. **Identify hard limits:** CPU quota, JDBC pool, HTTP connection pool, downstream rate limits, and max concurrent streams.
3. **Pick a baseline:** CPU pools near core count; blocking pools estimated from wait/compute ratio and downstream capacity.
4. **Set a queue budget:** determine max wait time allowed by deadlines/SLOs and size a bounded queue accordingly.
5. **Step up load:** increase concurrency and arrival rate, holding each step long enough to observe steady state.
6. **Change one variable at a time:** thread count, queue capacity, downstream concurrency, or callback duration.
7. **Watch for saturation:** find where throughput stops growing while queue wait, p95/p99, or CPU throttling rises.
8. **Test overload:** verify controlled rejection and clean recovery once load subsides.

Example benchmark matrix:

| Run | Core threads | Max threads | Queue | Goal |
| --- | ---: | ---: | ---: | --- |
| A | 8 | 8 | 32 | Baseline near CPU count |
| B | 8 | 16 | 64 | Test higher concurrency |
| C | 12 | 24 | 128 | Test larger pool |
| D | 12 | 24 | 32 | Reduce queue wait, shed load earlier |

This is an example matrix, not default values. Keep payload, TLS, JVM options, CPU quota, and downstream configuration constant for fair comparisons.

## 14. Metrics to monitor

| Metric | Meaning |
| --- | --- |
| Pool size / active threads | Worker utilization |
| Queue depth | Pending backlog |
| Queue wait time | Time tasks wait before running |
| Task execution time | Time workers spend running tasks |
| Rejected task count | Frequency of hitting executor limits |
| RPC latency p50/p95/p99 | Real impact on clients |
| RPC throughput/error/cancel | Capacity and reliability |
| CPU utilization/throttling | Whether CPU is the bottleneck |
| GC pauses/allocation/heap | Memory pressure from threads, queues, and payloads |
| JDBC/HTTP pool active, pending, wait | Whether the executor is pushing excessive load downstream |
| Thread states/thread dumps | Detects `BLOCKED`, `WAITING`, deadlocks, or long-held callbacks |

Metrics should carry bounded-cardinality labels like service/method and workload type. Never use request ID, user ID, or tokens as labels. Combine metrics with traces and thread dumps when investigating.

## 15. Common sizing mistakes

| Mistake | Consequence | Better approach |
| --- | --- | --- |
| Using host core count instead of CPU quota | Over-provisioned threads in containers | Size to actual CPUs allocated to the process |
| Setting huge max threads | Context switching and downstream overload | Estimate from workload and measure |
| Unbounded queues | Memory growth and prolonged latency | Bounded queues aligned with latency budget |
| Using `CallerRuns` on transport path | Can block event loops | Admission control and tested overload rejection |
| Using discard policies | Silent RPC/task loss | Explicit overload behavior |
| Mixing CPU and blocking workloads in one pool | Starvation across work types | Separate pools when needed and bound each |
| Treating each stream as one thread | Oversized pools for idle streams | Measure callback occupancy and message rate |
| Sizing executor larger than JDBC pool | Threads pile up waiting on connections | Bound DB concurrency appropriately |
| Using `directExecutor` for blocking handlers | Blocks transport threads | Use only for lightweight, non-blocking code |
| Ignoring deadlines/cancellation | Continues doing expired work | Propagate deadlines and stop work promptly |

## 16. Production checklist

Before releasing an executor configuration, confirm:

1. **Executor boundaries:** know which executor runs application callbacks vs. transport/offload work.
2. **Workload:** classify CPU-bound, blocking, non-blocking, and streaming callbacks.
3. **CPU:** size against actual container CPU quotas.
4. **Downstream:** thread concurrency does not uselessly exceed DB/HTTP/dependency capacity.
5. **Bounds:** core/max threads and queue capacity are all bounded.
6. **Queue budget:** wait time fits deadlines and latency SLOs.
7. **Rejection:** avoid discard policies; avoid `CallerRuns` on transport paths; test overload behavior.
8. **Spring lifecycle:** server drains/stops before the executor shuts down.
9. **Client callbacks:** never block callback threads; offload blocking work if needed.
10. **Streaming:** measure callback duration and message rate; enforce backpressure.
11. **Context:** correlation/security/tracing context propagates and clears cleanly.
12. **Cancellation:** tasks honor deadlines/cancellation whenever possible.
13. **Benchmarks:** include warm-up, steady state, stepped load, and overload tests.
14. **Observability:** track active threads, queue wait/depth, rejections, RPC p95/p99, CPU, and downstream pools.

## 17. Key takeaway

Executor sizing in Spring gRPC balances parallelism, wait time, CPU, memory, and downstream capacity. CPU-bound workloads typically start near available CPU count; blocking workloads may need more threads but must be bounded by connection pools and dependency capacity. Wait/compute formulas are only initial estimates that must be validated under realistic CPU quotas and production-like traffic.

Distinguish application executors from transport event loops, use bounded thread pools and queues, avoid uncontrolled `CallerRuns`/discard policies, and never block callbacks or use `directExecutor` for blocking work. Manage executors with the Spring lifecycle, propagate deadlines/cancellation/context across thread boundaries, and monitor active threads, queue wait, rejections, p95/p99, and downstream wait times. Under overload, early, observable load shedding protects reliability far better than endlessly adding threads or enlarging queues.

### References

- [gRPC – Performance](https://grpc.io/docs/guides/performance/)
- [gRPC Java – ServerBuilder API](https://grpc.github.io/grpc-java/javadoc/io/grpc/ServerBuilder.html)
- [gRPC Java – ManagedChannelBuilder API](https://grpc.github.io/grpc-java/javadoc/io/grpc/ManagedChannelBuilder.html)
- [Java – ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Spring Framework – Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
