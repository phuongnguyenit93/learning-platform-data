# Executor Queue Limits

## Learning Objectives

After this lesson, you can:

- Explain the role of executors and queues during RPC processing.
- Distinguish gRPC's dispatch executor from business-processing executors managed by the application.
- Configure bounded queues with ThreadPoolExecutor or Spring ThreadPoolTaskExecutor.
- Choose core size, maximum pool size, and queue capacity based on workload, deadlines, and resource budgets.
- Choose an appropriate rejection policy when the queue is full and map overload to gRPC statuses.
- Avoid blocking transport/callback threads and avoid creating unbounded queues in streaming RPCs.
- Combine queue limits with flow control, deadlines, concurrency limits, and per-tenant admission.
- Monitor queue depth, wait time, task latency, and rejections; test overload behavior.

## 1. What problem does an executor queue solve?

In **SPRING_GRPC**, an RPC passes through transport, interceptors, and service handlers, and may call databases, HTTP clients, brokers, or other services. gRPC callbacks must execute on an executor. Applications can also offload blocking or CPU-intensive work to a separate executor so callback threads are not held for too long.

An executor typically has a pool of worker threads and a queue holding waiting tasks. When all workers are busy, new tasks are queued. If the queue is unbounded, a traffic spike exceeding processing capacity can accumulate thousands or millions of tasks, holding requests/messages in memory and causing latency to climb continuously.

**Executor queue limits** place a finite capacity on waiting tasks. When the queue is full and workers have reached their limit, the system must reject, defer, or apply backpressure. A bounded queue turns overload into a clear signal instead of turning it into memory exhaustion.

Distinguish:

- **Worker threads:** number of tasks that can run concurrently.
- **Queue capacity:** number of tasks accepted to wait but not yet running.
- **Active tasks:** number of tasks currently executing.
- **Rejected tasks:** number of tasks refused because the executor is saturated or shut down.
- **RPC concurrency:** number of open calls; not identical to the number of tasks in the executor queue.

~~~mermaid
flowchart TD
    A["gRPC service receives RPC"] --> B["Authenticate and check deadline"]
    B --> C["Submit business work"]
    C --> D{"Worker slot free?"}
    D -- "Yes" --> E["Worker executes"]
    D -- "No" --> F{"Queue space free?"}
    F -- "Yes" --> G["Enqueue task in bounded queue"]
    G --> E
    F -- "No" --> H["Reject / backpressure"]
    E --> I["Return result or response"]
    H --> J["RESOURCE_EXHAUSTED or appropriate policy"]
~~~

Queues only absorb short bursts. If the task arrival rate continuously exceeds the processing rate, the queue will fill up no matter how large its capacity is. Admission limits and load shedding are required, not just larger queues.

## 2. Two types of executors to distinguish in gRPC and Spring

### 2.1. gRPC server executor

The grpc-java server builder can accept an executor to run server application callbacks/listeners. This executor handles dispatching from the gRPC runtime to the service implementation. If not configured, the runtime may use a default executor depending on transport/version.

Do not treat this executor as the place to run all long-running blocking work. If service handlers wait on databases or run long CPU-intensive operations, callback workers become occupied and slow down other RPCs.

If replacing the default executor with a bounded executor, understand exactly how your grpc-java version/transport uses that executor and how the runtime handles RejectedExecutionException. Do not set a tiny queue and assume every rejection automatically turns into RESOURCE_EXHAUSTED. Test the behavior with the exact server builder and transport in use.

### 2.2. Application/business executor

Applications typically have a dedicated executor for work that needs to be separated from gRPC callback threads, for example:

- Calling blocking libraries without async APIs.
- Generating reports or processing files.
- Running CPU-intensive transformations.
- Processing batches or events.
- Executing auxiliary tasks with bounded concurrency.

This executor is under the application's control. The service can actively catch rejections upon task submission and terminate the RPC with an appropriate status.

### 2.3. Spring @Async executor

Spring can manage an executor for @Async or task submission via ThreadPoolTaskExecutor. This executor is not automatically identical to the gRPC server executor. An application can have multiple distinct pools; each pool needs a clear name, capacity, metrics, and shutdown policy.

Do not create a new pool per RPC. Reuse a Spring-managed singleton executor and shut it down with the application context lifecycle.

## 3. Configuring a bounded ThreadPoolExecutor

Java ThreadPoolExecutor accepts core size, maximum size, keep-alive, queue, and rejection handler. Example of a pool handling blocking work:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

AtomicLong threadSequence = new AtomicLong();

ThreadPoolExecutor reportExecutor = new ThreadPoolExecutor(
        8,
        16,
        30,
        TimeUnit.SECONDS,
        new ArrayBlockingQueue<>(200),
        runnable -> {
            Thread thread = new Thread(runnable);
            thread.setName("grpc-report-" + threadSequence.incrementAndGet());
            thread.setDaemon(false);
            return thread;
        },
        new ThreadPoolExecutor.AbortPolicy());
~~~

Meaning:

- 8 workers is the core pool size.
- The pool can scale up to 16 workers as load increases.
- At most 200 tasks wait in the queue.
- When both workers and queue are full, AbortPolicy throws RejectedExecutionException.
- Keep-alive allows workers above core size to be reclaimed when idle.

This is a sizing example, not a universal recommendation. Queue capacity must be finite. Avoid LinkedBlockingQueue without a capacity argument because it is effectively unbounded and hides overload.

Thread naming in this example uses AtomicLong to generate unique suffixes and remain compatible across common Java versions.

## 4. Configuring with Spring ThreadPoolTaskExecutor

In Spring, ThreadPoolTaskExecutor manages the pool alongside the application context lifecycle:

~~~java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class GrpcWorkExecutorConfiguration {

    @Bean
    public ThreadPoolTaskExecutor grpcWorkExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(200);
        executor.setKeepAliveSeconds(30);
        executor.setThreadNamePrefix("grpc-work-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }
}
~~~

Spring initializes and manages the executor bean. Queue capacity 200 is an example. When the queue is full, submitting via Spring's task executor can throw TaskRejectedException, a form of rejection that must be handled at the submission boundary.

If using @Async, specify the executor explicitly to avoid accidentally using a common/default executor:

~~~java
@Async("grpcWorkExecutor")
public CompletableFuture<Report> generateReport(ReportRequest request) {
    return CompletableFuture.completedFuture(reportService.generate(request));
}
~~~

Do not rely on default bean names to assume which pool is in use. In integration tests, verify the service actually submits to the configured bean and that queue capacity is enforced.

## 5. Choosing queue capacity and pool size

Queue capacity is the number of waiting tasks, not running tasks. Total tasks held by a pool are roughly active workers plus queue capacity. If each task holds a request, protobuf object, tracing context, or large buffer, a large queue can consume substantial memory.

Choose configuration based on these factors:

1. **Task service time:** average and p95/p99 time to process one task.
2. **Arrival rate:** tasks arriving per second during normal hours and bursts.
3. **Worker capacity:** how many tasks can run concurrently without overloading downstreams.
4. **Task memory:** objects/buffers each task retains while waiting.
5. **Deadline:** a task waiting in the queue must still have enough time left to run and finish.
6. **Downstream capacity:** database pools, HTTP connection pools, broker quotas, and rate limits.
7. **Fairness:** one method or tenant must not occupy the entire queue.

You can use Little's Law to estimate the relationship between tasks in the system, throughput, and wait time:

\[
L = \lambda W
\]

Where L is the average number of tasks in the system, λ is throughput in tasks/second, and W is the average time a task spends in the system. This is an average steady-state relationship, not a formula for directly sizing queue capacity for bursts or tail latency.

A large queue increases wait time. If 300 ms remain on the deadline yet a task waits 2 seconds in the queue, running the task when it starts is pointless. Check the deadline before submitting and discard already-expired tasks before execution.

Do not enlarge the queue to compensate for sustained low throughput. If arrival rate exceeds service capacity over a sustained period, the queue will fill up; you need controlled worker scaling, load shedding, rate limiting, or processing optimization.

## 6. Rejection policies when the queue is full

When workers reach max size and the queue is full, ThreadPoolExecutor invokes RejectedExecutionHandler. Each policy has different semantics:

| Policy | Behavior | Risks/when to use |
| --- | --- | --- |
| AbortPolicy | Throws RejectedExecutionException | Explicit; application can map to an overload response |
| CallerRunsPolicy | Runs the task on the submitting thread | Can block gRPC callback/transport threads; use only when the caller thread is allowed to run tasks |
| DiscardPolicy | Silently drops the task | Risks losing RPCs/tasks and hanging responses without extra handling |
| DiscardOldestPolicy | Drops the head of the queue and retries submitting the new task | Can drop older requests and break ordering |

For gRPC services, AbortPolicy is usually easiest to control on application executors because the service can catch rejections and terminate the call. Avoid CallerRunsPolicy if submission happens from a gRPC callback thread or transport-related executor: a blocking task will run on that thread, slowing down other RPCs and breaking isolation.

Do not use DiscardPolicy for RPCs where the client is waiting for a response, unless the application has a separate failure-reporting mechanism. Dropping a task without terminating the observer can leave the call hanging until its deadline.

## 7. Mapping rejections to gRPC statuses

When the application submits work and the executor rejects it, the service can terminate the RPC cleanly:

~~~java
public void generateReport(
        ReportRequest request,
        StreamObserver<ReportResponse> responseObserver) {

    try {
        reportExecutor.execute(() -> {
            try {
                Report report = reportService.generate(request);
                responseObserver.onNext(toResponse(report));
                responseObserver.onCompleted();
            } catch (Exception failure) {
                responseObserver.onError(mapFailure(failure));
            }
        });
    } catch (RejectedExecutionException rejected) {
        responseObserver.onError(
                Status.RESOURCE_EXHAUSTED
                        .withDescription("Server is at capacity")
                        .asRuntimeException());
    }
}
~~~

This illustrative example needs a terminal guard if multiple error/cancellation paths can race. Never call onNext after onError/onCompleted. If the client cancels while the task is running, cancel the task if possible and send no further responses.

RESOURCE_EXHAUSTED fits when the server rejects because a quota or capacity limit is reached. UNAVAILABLE may fit if the system policy treats the instance as temporarily unavailable; pick a consistent contract. Do not use PERMISSION_DENIED for overload because this is not an authorization error.

Do not let a rejection exception escape a callback and expect grpc-java to always map it to the right status. On application executors, catch the error at the submission site. For gRPC server's internal executor, behavior depends on runtime/transport and requires dedicated testing.

## 8. Queue wait must fit within the deadline

The RPC deadline includes time spent waiting in the executor queue. A task should not start if the call has already expired or lacks enough time left to do useful work.

You can capture Context/deadline with the task and check before running:

~~~java
Context rpcContext = Context.current();
Deadline deadline = rpcContext.getDeadline();

try {
    reportExecutor.execute(() -> {
        if (rpcContext.isCancelled()) {
            return;
        }

        if (deadline != null
                && deadline.isExpired()) {
            return;
        }

        Context previous = rpcContext.attach();
        try {
            Report report = reportService.generate(request);
            // Complete the RPC only if it is still active.
        } finally {
            rpcContext.detach(previous);
        }
    });
} catch (RejectedExecutionException rejected) {
    responseObserver.onError(
            Status.RESOURCE_EXHAUSTED.asRuntimeException());
}
~~~

This is a skeleton highlighting Context propagation across thread boundaries. In production implementations, use Context.wrap or an equivalent propagation mechanism to avoid incorrect attach/detach, and ensure cleanup when tasks are canceled. Do not retain Context after the RPC has ended.

If the remaining deadline is less than the minimum expected time for the task, reject early or do not submit. Do not enqueue an already-expired task; it only occupies a slot and may run after the caller has given up.

Queue capacity should also be sized so p95/p99 queue wait fits the latency budget. Measure queue wait separately rather than looking only at total RPC latency.

## 9. Streaming RPCs and bounded work queues

In client-streaming or bidirectional streaming, each inbound message can spawn a task. If the callback simply submits tasks and keeps receiving messages without bounds, the application executor queue can fill up very quickly.

Combine:

- Bounded executor queue.
- Limit on pending tasks per stream.
- Manual inbound flow control to request the next message only when capacity is available.
- Total stream bytes/message count limits.
- Cancellation to stop producers and queued tasks.
- Per-stream or per-tenant admission so one stream does not monopolize the queue.

With grpc-java, ServerCallStreamObserver can disable automatic inbound flow control and request subsequent messages in a controlled manner. Conceptual example:

~~~java
if (responseObserver instanceof ServerCallStreamObserver<?> serverObserver) {
    serverObserver.disableAutoRequest();
    serverObserver.request(1);
}
~~~

After finishing one message and freeing capacity, the service requests the next message. Check the exact API and thread-safety rules for your grpc-java version. Do not request the next message immediately after submitting a task if the queue has no room or the previous task has not completed; otherwise backpressure has no effect.

On outbound streaming, use isReady/on-ready handlers so the producer does not push responses faster than the transport can accept them. Bounded executor queues and flow control protect two different layers.

## 10. Fairness and workload isolation

A finite global queue can still be monopolized by a single tenant or method. Small requests from other tenants then get rejected even though their workload is light.

You can apply:

- Separate queues or semaphores per workload group.
- Per-tenant in-flight task limits.
- Per-method concurrency limits.
- Weighted admission for tasks with different costs.
- Bounded priority for health/admin tasks if required by contract.
- Separate pools for CPU-intensive and blocking I/O work.

Do not create unbounded executors per tenant; pool/thread counts would scale with tenants and cause resource exhaustion another way. Use an admission controller or a quota map with lifecycle/eviction, then submit to a small bounded set of pools.

Separating blocking I/O from CPU-bound work prevents one workload type from starving the other's workers. However, too many pools complicate capacity planning and easily create chained queues. Split pools only when justified by measurement.

## 11. Shutdown and queued tasks

When a Spring application shuts down, the executor needs an explicit policy for running tasks and queued tasks:

- Stop accepting new tasks.
- Allow running tasks to finish within a finite grace period if appropriate.
- Cancel or mark remaining queued tasks when the shutdown deadline expires.
- Terminate waiting RPCs with an explicit status/cancellation if possible.
- Do not hold channels, subscriptions, or transactions open after the context closes.

ThreadPoolTaskExecutor supports configuring wait-for-tasks-on-shutdown and shutdown await timeout. However, never wait indefinitely because a blocking task can hang shutdown. Tasks must have their own dependency deadlines/timeouts.

For tasks submitted on behalf of an RPC, track terminal/cancellation state so workers do not send responses after the call has ended. If work must continue after the RPC disconnects, turn it into a background job with its own ID/status API and lifecycle instead of retaining the RPC observer.

## 12. Observing executor queues

Important metrics:

- Pool size, active thread count, and core/max size.
- Queue depth and remaining queue capacity.
- Task submission rate, completion rate, and rejection count.
- Queue wait time p50/p95/p99.
- Task execution time p50/p95/p99.
- Tasks skipped because the deadline expired before execution.
- Tasks canceled when clients cancel RPCs.
- Executor-related RESOURCE_EXHAUSTED/UNAVAILABLE RPC statuses.
- Downstream pool utilization and latency.

Tag metrics with executor name and workload group. Avoid using arbitrary request IDs, user IDs, or tenant IDs as metric labels because cardinality can grow unboundedly. Normalized tenant/quota tiers can be recorded in logs or traces when needed for investigation.

If queue depth consistently stays near capacity, wait times rise, and rejections appear, the system is saturated. Increasing queue size only delays rejection and can cause more deadline misses.

## 13. Testing bounded queues and rejections

Tests should prove the queue never exceeds capacity and overload is handled accurately:

| Scenario | Expected result |
| --- | --- |
| Worker has free capacity | Task executes |
| Workers busy, queue has room | Task is enqueued |
| Workers at max, queue full | New task is rejected |
| Rejection inside gRPC handler | Client receives status per overload contract |
| Task waits until deadline expires | Task does not execute business logic |
| Client cancels while task waits | Task is dropped/canceled if possible |
| Streaming sends faster than consumer | Flow control prevents unbounded queue growth |
| One tenant reaches quota | Other tenants still have capacity per policy |
| Shutdown with queued tasks | Tasks complete/cancel per configured lifecycle |

Use a small executor in tests, such as one worker and queue capacity one. Use CountDownLatch to hold the worker busy, submit a second task into the queue, and submit a third task to verify rejection. Do not use Thread.sleep as the primary synchronization mechanism.

For gRPC integration tests, invoke the method via a generated stub, verify the client receives RESOURCE_EXHAUSTED when the application executor rejects, and verify the observer receives only one terminal signal. Cancellation/deadline tests must verify that tasks produce no side effects after the RPC has ended.

For Spring application tests, inject the actual ThreadPoolTaskExecutor bean, verify queue capacity and rejection handler, and start the server using the real starter configuration to check wiring.

## 14. Common implementation pitfalls

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| Using nearly unbounded queues | Uncontrolled memory growth and latency | Use bounded queues |
| Increasing queue size on rejections | Hides overload and causes tasks to expire in queue | Measure throughput, wait time, and scale/limit admission |
| Using CallerRuns on gRPC callback threads | Callback threads get blocked by business tasks | Use AbortPolicy and map rejections |
| Using DiscardPolicy for RPCs | Clients wait for responses until deadline | Terminate calls explicitly on rejection |
| Running blocking tasks on server executor | Starves gRPC callback dispatch | Separate application worker executor |
| Submitting every streaming message without backpressure | Queue fills and retains many messages | Manual flow control, bounded pending work |
| Not propagating Context/deadline to workers | Tasks run after RPC expires | Propagate Context and check cancellation |
| Sharing one queue across vastly different workloads | Heavy workloads block lightweight tasks | Separate pools/admission as needed |
| Not closing executors on shutdown | Threads and tasks outlive application | Manage lifecycle and shutdown timeouts |
| Not testing rejections | Unclear overload behavior | Test full queue and actual statuses |

## 15. Hands-on exercises and self-check questions

### Hands-on exercises

1. Create a ThreadPoolTaskExecutor bean for blocking work invoked by a gRPC service.
2. Set core size, max size, finite queue capacity, and AbortPolicy.
3. Submit tasks from an async gRPC handler; catch rejections and return RESOURCE_EXHAUSTED.
4. Propagate Context/deadline into workers and skip already-expired tasks.
5. For client-streaming, use manual flow control to accept the next message only when workers have capacity.
6. Add per-tenant in-flight quotas and bounded queues for relevant workloads.
7. Add metrics for queue depth, wait time, execution time, and rejection counts.
8. Write tests for busy worker + full queue, RPC rejection, cancellation, deadlines, shutdown, and Spring bean wiring.

### Self-check questions

**1. What does an executor queue limit?**  
The number of tasks accepted by the executor that are waiting and not yet executed by a worker.

**2. Is queue capacity the number of concurrently running tasks?**  
No. Running tasks depend on worker count; the queue only holds waiting tasks.

**3. Why should unbounded queues be avoided?**  
Accumulated tasks consume memory and increase queue wait time; requests may miss their deadlines before running.

**4. Which rejection policy is easiest to handle for application RPCs?**  
AbortPolicy, because it signals rejection so the service can terminate the call cleanly.

**5. Why is CallerRunsPolicy dangerous with gRPC callbacks?**  
Tasks can run directly on callback/transport-related threads and block dispatching of other RPCs.

**6. Does flow control replace a bounded queue?**  
No. Flow control regulates in-flight messages; a bounded queue limits waiting tasks on the application executor.

**7. Does queue wait count toward the RPC deadline?**  
Yes. Time spent waiting in the queue consumes the call's time budget.

**8. When should multiple executors be separated?**  
When workloads differ in CPU, blocking behavior, latency, or downstream capacity and the benefit of separation is measurable.

## Summary

Executor queue limits control the number of waiting tasks while workers are busy. In Spring gRPC, distinguish grpc-java's callback dispatch executor from application executors handling blocking/CPU-intensive work and from executors used by @Async. Use bounded queues, size pools based on throughput and resources, check deadlines before running tasks, and handle rejections explicitly. Avoid CallerRuns on gRPC callback threads; for streaming, combine queue limits with manual flow control and pending-message caps. Monitor queue depth, wait time, task latency, and rejections; test full queues, cancellation, deadlines, and Spring wiring to prove overload is handled safely.
