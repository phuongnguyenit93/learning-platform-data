# Executor and Queue Limits

## 1. Why Must Executors and Queues Be Bounded?

In Spring gRPC, each RPC must be dispatched to a callback or service handler, which may then call a database, HTTP client, broker, or another service. If all work shares an unbounded executor, a traffic spike or slow dependency can pile up a huge number of waiting tasks. Memory climbs, latency stretches out, and new requests keep getting accepted even when the system has no capacity left to process them.

The executor governs how many tasks can run concurrently and how they are scheduled. The queue holds waiting tasks when no worker is free. Both limits must be designed together:

- **Concurrency limit:** bounds how much work runs concurrently.
- **Queue capacity:** bounds how much work waits.
- **Rejection policy:** defines behavior when both workers and the queue are full.
- **Deadline/cancellation:** stops expired tasks from continuing to consume resources.
- **Backpressure:** throttles message intake when producers outpace consumers.

An unbounded queue only delays the moment overload becomes visible. When the arrival rate exceeds processing capacity for long enough, the queue keeps growing and exhausts memory.

## 2. Distinguishing Executors in gRPC Java

A gRPC application can have several distinct categories of work:

| Executor / Thread Group | Work | Risk If Blocked |
| --- | --- | --- |
| Netty event loop | I/O and transport events | Can slow down many connections if blocking business logic runs on it |
| gRPC server application executor | Dispatches listener/service callbacks | Other RPCs wait if callbacks block |
| gRPC client callback executor | Client call callbacks | Response and completion callbacks are delayed |
| Business worker executor | Databases, blocking HTTP, CPU work | Pool exhaustion drives queue growth |
| Scheduled executor | Timeouts, retry timers, housekeeping | Timers are delayed if running blocking tasks |

Never use the Netty event loop as a business executor. Never call a database or blocking HTTP client directly on the event loop. Nor should you share a single pool across gRPC callbacks, blocking tasks, and heavy CPU work; congestion in one group can drag down the entire system.

gRPC Java can accept executors via ServerBuilder/NettyServerBuilder and ManagedChannelBuilder. If unconfigured, the runtime uses its implementation-default executor. When you need load control and thread naming, configure executors explicitly at server/channel creation or via the customizer provided by your Spring gRPC version.

Avoid using directExecutor() for callbacks that may block. Direct executor runs callbacks on the calling thread or the relevant transport thread; one slow operation can hold a thread needed for other RPCs to make progress.

## 3. Core Size, Maximum Size, and Queue Capacity

With ThreadPoolExecutor, the standard worker allocation sequence is:

1. Create workers up to corePoolSize.
2. Once core workers are busy, enqueue tasks into the queue.
3. Once the queue is full, scale workers beyond core up to maxPoolSize.
4. Once maxPoolSize is reached and the queue is still full, apply the rejection policy.

This means an overly large queue can prevent the pool from ever scaling from core to maximum even while latency is already high. A smaller queue helps the system detect saturation early and scale workers within configured limits.

| Parameter | Meaning | Impact |
| --- | --- | --- |
| corePoolSize | Baseline workers maintained | Baseline concurrency level |
| maxPoolSize | Maximum workers allowed | Ceiling on thread resources |
| queueCapacity | Maximum waiting tasks | Ceiling on backlog and memory |
| keepAliveSeconds | How long excess workers stay alive when idle | Tunes pool shrink/grow behavior |
| rejection handler | Behavior when pool and queue are full | Determines how overload is signaled |

An initial starting point for a blocking task group might be 8 core workers, max 24 workers, and a queue of 128 tasks. This is only a starting point; measure processing times, core counts, connection pool limits, and real load before finalizing.

## 4. Estimating Capacity from Load and Wait Time

One way to estimate concurrency is Little's Law:

\[
L = \lambda W
\]

Where:

- L is the average number of requests in the system.
- λ is the average throughput (requests/second).
- W is the average time a request spends in the system (seconds).

For example, if a dependency handles 200 requests/second and each request takes 0.05 seconds on average, the average number of concurrent in-flight requests is approximately 10. This gives intuition for concurrency, not a direct formula for corePoolSize, since CPU, blocking, bursts, and latency distributions also matter.

Queue capacity should tie to the maximum acceptable wait time. An initial estimate is:

\[
queueCapacity \approx arrivalRate \times maxQueueWait
\]

If the system receives 400 tasks/second and tolerates at most 0.1 seconds of queuing before execution starts, a queue of roughly 40 tasks is a reasonable initial test point. Then load test and adjust for bursts, memory footprint, and RPC deadlines.

Never set a queue of tens of thousands of items just to avoid rejections. A task waiting too long may already be past its deadline before execution starts; keeping it in the queue only wastes memory and increases latency for still-useful tasks.

## 5. Configuring Bounded Executors in Spring

Spring's ThreadPoolTaskExecutor lets you configure core size, max size, queue capacity, thread name prefix, and rejection handler. Example:

~~~java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class RpcExecutorConfiguration {

    @Bean
    ThreadPoolTaskExecutor grpcCallbackExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(128);
        executor.setKeepAliveSeconds(30);
        executor.setThreadNamePrefix("grpc-callback-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }

    @Bean
    ThreadPoolTaskExecutor blockingWorkerExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(12);
        executor.setMaxPoolSize(24);
        executor.setQueueCapacity(96);
        executor.setKeepAliveSeconds(30);
        executor.setThreadNamePrefix("grpc-worker-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
~~~

Spring manages the lifecycle of ThreadPoolTaskExecutor beans and initializes them in the application context. The two pools are separated so gRPC callbacks are not starved of workers by blocking operations.

Do not copy these numbers verbatim into production. Account for replica count, allocated CPUs, database connection limits, downstream HTTP connection limits, and the maximum concurrent requests the service can sustain.

## 6. Attaching Executors to gRPC Servers and Channels

With the gRPC Java Netty transport, you can attach an executor when building the server:

~~~java
import io.grpc.Server;
import io.grpc.netty.NettyServerBuilder;
import java.io.IOException;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class GrpcTransportConfiguration {

    @Bean(destroyMethod = "shutdown")
    Server catalogGrpcServer(
            @Qualifier("grpcCallbackExecutor")
            ThreadPoolTaskExecutor grpcCallbackExecutor,
            CatalogServiceImpl catalogService) throws IOException {
        return NettyServerBuilder.forPort(9090)
                .executor(grpcCallbackExecutor)
                .addService(catalogService)
                .build()
                .start();
    }
}
~~~

This example is for when the application manages the Netty gRPC server directly. If Spring gRPC already auto-creates the server, do not create a second server; pass the executor into the server builder/customizer supported by your Spring gRPC version. Customizer registration and property names can vary across versions.

A client channel can also accept an executor for callbacks:

~~~java
ManagedChannel channel = ManagedChannelBuilder
        .forAddress("catalog.internal", 9090)
        .useTransportSecurity()
        .executor(clientCallbackExecutor)
        .build();
~~~

Manage channels and executors alongside the application lifecycle. During shutdown, stop accepting new RPCs, wait within a time bound for in-flight calls, and then close channels/servers and executors. Never create a new pool or channel per RPC.

## 7. Do Not Block gRPC Callbacks: Dispatch Bounded Work

If a service needs to call a blocking dependency, offload that part to a business worker executor. Capture the gRPC Context before leaving the callback thread so deadlines, cancellation, and required context values remain accessible.

~~~java
import io.grpc.Context;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class CatalogServiceImpl
        extends CatalogServiceGrpc.CatalogServiceImplBase {

    private final CatalogRepository repository;
    private final ThreadPoolTaskExecutor blockingWorkerExecutor;

    public CatalogServiceImpl(
            CatalogRepository repository,
            @Qualifier("blockingWorkerExecutor")
            ThreadPoolTaskExecutor blockingWorkerExecutor) {
        this.repository = repository;
        this.blockingWorkerExecutor = blockingWorkerExecutor;
    }

    @Override
    public void getItem(
            GetItemRequest request,
            StreamObserver<GetItemResponse> responseObserver) {

        Context rpcContext = Context.current();
        try {
            blockingWorkerExecutor.execute(rpcContext.wrap(() -> {
                if (rpcContext.isCancelled()) {
                    return;
                }
                try {
                    Item item = repository.findById(request.getItemId())
                            .orElseThrow(() ->
                                    Status.NOT_FOUND.asRuntimeException());

                    if (rpcContext.isCancelled()) {
                        return;
                    }

                    responseObserver.onNext(toResponse(item));
                    responseObserver.onCompleted();
                } catch (RuntimeException error) {
                    if (!rpcContext.isCancelled()) {
                        responseObserver.onError(error);
                    }
                }
            }));
        } catch (TaskRejectedException rejected) {
            responseObserver.onError(Status.RESOURCE_EXHAUSTED
                    .withDescription("Server is busy; retry later")
                    .asRuntimeException());
        }
    }
}
~~~

This example illustrates dispatching a unary operation. In a real application, map repository exceptions to appropriate gRPC statuses instead of returning INTERNAL/UNKNOWN for every error, and define a cancellation policy for each dependency. Context.wrap() preserves the gRPC Context while the task runs on the worker.

When the queue is full, AbortPolicy causes Spring's execute to throw TaskRejectedException. The service returns RESOURCE_EXHAUSTED to signal that the server cannot accept more work right now. Clients should only retry this status when policy, backoff, deadlines, and method semantics allow it; unbounded synchronized retries worsen overload.

Do not use CallerRunsPolicy casually. When the pool is full, this policy runs the task directly on the submitting thread. That thread may be a gRPC callback thread; if the task blocks, callbacks and other RPCs can stall.

## 8. Full Queues and Rejection Policies

A bounded queue requires an explicit overload policy:

| Policy | Behavior | Assessment for RPCs |
| --- | --- | --- |
| AbortPolicy | Throws a rejection exception | Often suitable so the service translates it into RESOURCE_EXHAUSTED |
| CallerRunsPolicy | Submitting thread runs the task itself | Can block gRPC callback/transport-related threads; use only when proven safe |
| DiscardPolicy | Drops the new task | Unsuitable for RPCs because requests vanish without a clear outcome |
| DiscardOldestPolicy | Drops the oldest task in the queue | Unsuitable for requests awaiting responses; silently drops pending operations |

For RPCs, never silently drop tasks. If the server rejects due to overload, return an explicit status, record metrics, and let clients apply backoff. If a task was already accepted and is running, cancellation and deadlines should stop work whenever possible.

Rejection is not a caller validation error. RESOURCE_EXHAUSTED fits when the server is out of capacity or quota; UNAVAILABLE may be used per contract for certain temporary unavailability scenarios. Choose statuses consistently with your API and retry policy.

## 9. Deadlines and Queue Wait Time

An RPC's deadline covers queue wait time, processing time, and response transmission time. If 100 ms remain on the deadline but a task waits 500 ms in the queue, the task is already stale before it starts.

When a task is dequeued:

1. Check whether the gRPC Context has been cancelled or the deadline has expired.
2. If expired, skip the work and do not call dependencies.
3. If time remains, propagate the remaining deadline to downstream calls.
4. When a dependency returns a result, check cancellation before emitting the response.

Never grant a brand-new full timeout to every dependency. Downstream time budgets must fit within the parent RPC's remaining deadline.

For blocking operations that cannot stop immediately, set timeouts on the database/HTTP client and use cancellation tokens or cooperative interrupts. Context cancellation does not automatically kill a thread blocked inside a driver.

## 10. Queues Do Not Replace Backpressure for Streaming

For server streaming or bidirectional streaming, a producer can emit messages faster than a client can receive them. If the server puts every message into an unbounded queue, memory grows without bound even if the executor itself is bounded.

Combine:

- A bounded queue for pending data.
- gRPC flow control to bound messages sent/received.
- Checking ServerCallStreamObserver.isReady() before emitting outbound messages.
- Registering setOnReadyHandler() to resume draining when the transport becomes ready.
- Stopping the producer and closing subscriptions when the call is cancelled.

Skeleton outbound server stream example:

~~~java
ServerCallStreamObserver<OrderEvent> call =
        (ServerCallStreamObserver<OrderEvent>) responseObserver;

call.setOnReadyHandler(() -> {
    while (call.isReady() && !call.isCancelled()) {
        OrderEvent next = boundedEventQueue.poll();
        if (next == null) {
            break;
        }
        call.onNext(next);
    }
});
~~~

This snippet is an illustrative skeleton; the onReady callback and producer may run on different threads. Serialize draining, ensure only a single writer calls onNext, and never emit after a terminal signal. The queue must have finite capacity; when full, the producer must pause, wait, or apply an overflow policy allowed by the contract.

For inbound streaming, the server can disable automatic inbound flow control using disableAutoInboundFlowControl() on ServerCallStreamObserver and call request(n) once capacity is available to process more messages. Once the consumer finishes one message, request the next. Check exact APIs against your gRPC Java version.

Queue capacity only bounds local backlogs; flow control regulates how many messages are allowed to travel over the stream. Both mechanisms complement each other.

## 11. Bulkheads: Separating Pools by Workload Type

Do not let one slow dependency consume all workers serving every RPC. Separate executors by workload profile:

| Pool | Work | Additional Limits |
| --- | --- | --- |
| grpc-callback | RPC callbacks/dispatching | Short tasks, non-blocking |
| database-worker | Blocking database queries | Do not exceed connection pool and DB capacity |
| http-worker | Blocking HTTP clients | Do not exceed max connections and downstream quota |
| cpu-worker | Encryption, compression, or computation | Close to available CPU cores |
| stream-worker | Event stream processing | Small queue, flow control, and cancellation |

Bulkheads prevent a failure in one dependency from spreading across the whole RPC server. However, each pool still needs its own bounded queue, rejection policy, deadlines, and metrics. Separating pools does not increase the total capacity of a database or downstream service.

## 12. Observing Executors and Queues

Metrics to track per pool:

| Metric | Meaning |
| --- | --- |
| active workers | Workers currently executing tasks |
| pool size / max pool size | Current pool size and upper limit |
| queue size | Tasks currently waiting |
| queue remaining capacity | Remaining capacity in the queue |
| task rejected | Number of rejected tasks |
| task wait duration | Time from submission until execution starts |
| task execution duration | Execution time |
| deadline expired before start | Tasks whose deadline expired while still queued |
| cancelled queued/running tasks | Tasks cancelled before or during execution |

Use pool names as labels since the number of pools is finite. Never use request IDs, tenant IDs, or user IDs as metric labels.

A dashboard should plot queue depth alongside latency and rejections. Steadily rising queue depth, growing wait duration, and active workers hitting max are signs of saturation. If queues stay low while rejections are high, inspect bursts, queue capacity, executor sharing, and execution durations.

## 13. Testing Saturation and Overload

Do not test throughput only under low load. Actively push executors to their limits:

| Scenario | What to Verify |
| --- | --- |
| Low load, fast dependency | Stable latency, nearly empty queue |
| Load exceeds core pool | Queue grows while staying within capacity |
| Queue full, pool scales to max | Workers never exceed the configured cap |
| Queue and pool both full | New requests receive an explicit overload status |
| Task expires while waiting | Dependency is not called once the task is dequeued |
| Caller cancels running task | Work stops cooperatively, no late response emitted |
| Slow dependency | Dependency pool is capped; callback pool keeps serving other RPCs |
| Streaming producer faster than client | Flow control/bounded queue keeps memory within bounds |
| Application shutdown | No tasks or threads linger outside expected lifecycle |

In tests, use latches to hold workers busy and fill the queue predictably; do not use fixed sleeps for synchronization. Assert active task counts, queue size, rejection counts, and gRPC statuses. Run load tests with latency distributions and bursts close to production.

## 14. Common Mistakes

1. **Using an unbounded queue.** Backlogs can exhaust memory and stretch latency.
2. **Enlarging the queue to hide insufficient capacity.** Requests can exceed deadlines before ever running.
3. **Setting only corePoolSize while ignoring maxPoolSize/queueCapacity.** Misunderstands the ordering between queuing and worker scaling.
4. **Using directExecutor for blocking services.** Can block threads needed by RPCs or the transport.
5. **Using CallerRunsPolicy without evaluating the submitting thread.** Callback threads can be dragged into slow tasks.
6. **Silently discarding requests.** Callers get no clear outcome and cannot reconcile.
7. **Using one pool for every dependency.** One slow downstream service can occupy all workers.
8. **Treating a bounded queue as backpressure.** Streaming still needs gRPC flow control and producer throttling.
9. **Failing to check deadlines/cancellation before running queued tasks.** Expired work still consumes resources.
10. **Not measuring queue wait time and rejections.** Looking only at CPU can miss saturation.

## 15. Applied Exercises

For CatalogService in Spring gRPC:

1. Create a separate callback executor and blocking worker executor, both with finite queue capacities.
2. Attach the callback executor to the gRPC server/channel builder using your Spring gRPC version's mechanism.
3. Dispatch blocking queries to the worker pool using gRPC Context wrapping.
4. Use AbortPolicy and translate rejections into RESOURCE_EXHAUSTED.
5. Generate load past core size, fill the queue, and verify the pool never exceeds max size.
6. Set a short deadline, let a task wait in the queue, and verify the expired task does not call the database.
7. For server streaming, use a bounded queue and onReady flow so emission never outpaces the transport.
8. Collect queue depth, wait duration, execution duration, and rejection counts; define alert thresholds.

**Completion criteria:** learners can configure bounded executors and queues, explain core/max/queue/rejection mechanics, avoid blocking callback/transport threads, propagate deadlines/cancellation to workers, apply backpressure for streaming, and test behavior under saturation.

### References

- [gRPC Java ServerBuilder API](https://grpc.github.io/grpc-java/javadoc/io/grpc/ServerBuilder.html): configuring server executors.
- [gRPC Java ManagedChannelBuilder API](https://grpc.github.io/grpc-java/javadoc/io/grpc/ManagedChannelBuilder.html): configuring client channel executors.
- [Java ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/): workers, queues, and rejection policies.
- [Spring ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): configuring executors in Spring.
- [gRPC Flow Control](https://grpc.io/docs/guides/flow-control/): regulating messages in streaming RPCs.
- [gRPC Deadlines](https://grpc.io/docs/guides/deadlines/): RPC deadlines and time budgets.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): gRPC client/server integration in Spring.
