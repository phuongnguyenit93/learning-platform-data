# Virtual Threads and Workload-Based Limits

**Virtual threads** help handle many concurrent blocking tasks at lower thread overhead than platform threads. In Spring gRPC, virtual threads can be used as the service implementation executor when handlers frequently wait on JDBC, HTTP clients, or blocking gRPC stubs. However, virtual threads do not make the CPU faster and do not increase database connections, downstream capacity, or system resource limits.

A proper design has two parts: use virtual threads to reduce the cost of waiting on I/O, while enforcing **concurrency limits based on workload and actual resources**. If you replace a bounded thread pool with a virtual-thread-per-task executor and let requests enter without limits, the system can still exhaust connections, memory, or downstream service capacity.

## 1. How Do Virtual Threads Work?

A platform thread is typically tied to an OS thread for most of its lifetime. A virtual thread is a thread managed by the JVM; when it waits on a supported blocking operation, the JVM can unmount the virtual thread from its carrier thread so the carrier can run another task. When the operation is ready to resume, the virtual thread is remounted.

~~~mermaid
flowchart TD
    A["RPC handler runs on a virtual thread"] --> B{"Blocking operation?"}
    B -->|"No"| C["Continue running on carrier"]
    B -->|"Yes, unmount supported"| D["Virtual thread temporarily unmounts"]
    D --> E["Carrier runs another virtual thread"]
    E --> F["I/O becomes ready"]
    F --> G["Virtual thread is remounted"]
    G --> H["Handler continues"]
~~~

This fits sequential-style code:

~~~java
Order order = orderRepository.findById(orderId);
Inventory inventory = inventoryClient.check(order);
return toResponse(order, inventory);
~~~

The handler can wait on the database and then wait on the inventory service without holding a dedicated platform thread for the entire wait, provided the I/O libraries and blocking points allow the JVM to unmount the virtual thread.

A virtual thread is not a lighter OS thread created directly. The JVM schedules many virtual threads onto a set of carrier platform threads. CPU-bound work still requires CPU; when all carriers are busy computing, additional virtual threads cannot make the CPU run faster.

## 2. Using Virtual-Thread-Per-Task as the Server Executor

Starting in Java 21, create the executor with Executors.newVirtualThreadPerTaskExecutor():

~~~java
ExecutorService grpcVirtualExecutor =
    Executors.newVirtualThreadPerTaskExecutor();

Server server = ServerBuilder.forPort(9090)
    .executor(grpcVirtualExecutor)
    .addService(new OrderServiceImpl())
    .build()
    .start();
~~~

ServerBuilder.executor(Executor) accepts the executor used to run application calls. For a server auto-created by a Spring starter, wire this executor through the customizer/configurer or extension point supported by your exact starter version. Merely creating an executor bean without attaching it to the server builder will not change the threads running service implementations.

Do not create a new executor per RPC. A single per-task executor is managed at the application/server level and reused as an infrastructure component.

## 3. Managing Lifecycle with Spring

The executor must be closed alongside the server lifecycle. Example bean declaration:

~~~java
@Configuration
public class GrpcThreadConfiguration {

    @Bean(destroyMethod = "shutdown")
    ExecutorService grpcVirtualExecutor() {
        return Executors.newVirtualThreadPerTaskExecutor();
    }
}
~~~

The bean must be passed into the starter's server builder configuration point. During application shutdown, stop accepting new RPCs first, give the server a grace period to finish in-flight calls, and then shut down the executor. If the executor is shut down before the server stops dispatching callbacks, new requests can be rejected during shutdown.

With a manually constructed server configuration, the dependency can be expressed through constructor/method injection:

~~~java
@Bean
Server grpcServer(
        ExecutorService grpcVirtualExecutor,
        OrderServiceImpl orderService) throws IOException {
    return ServerBuilder.forPort(9090)
        .executor(grpcVirtualExecutor)
        .addService(orderService)
        .build()
        .start();
}
~~~

This example illustrates a plain gRPC Java server managed by Spring. If the starter already manages the server lifecycle, use the starter's extension point instead of creating a second server.

## 4. Which Workloads Fit Virtual Threads?

Virtual threads shine most when many concurrent requests spend most of their time waiting on I/O:

| Workload | Suitability | Rationale and Limits |
| --- | --- | --- |
| Blocking JDBC or repositories | Suitable | Waiting threads can unmount; connection count is still bounded by the database pool |
| Blocking HTTP clients | Suitable | Keeps readable sequential code; requires connection/request timeouts and concurrency limits |
| Blocking gRPC stubs | Suitable | Caller virtual thread can wait on responses; downstream still has finite capacity |
| CPU-bound transforms | Does not increase throughput via virtual threads alone | CPU and carriers remain finite; use a bounded CPU executor |
| Continuous streaming processing | Depends on implementation | Avoid holding a virtual thread in an infinite wait loop; use callbacks, backpressure, and session limits |
| Long-running background tasks | Must be isolated | Needs dedicated queues, admission control, and lifecycle so interactive RPC capacity is not consumed |

Do not switch all code to virtual threads just because you can. Measure the workload first, then choose an executor for blocking work and bounded executors for CPU-bound or rate-throttled work.

## 5. Virtual Threads Do Not Replace Resource Limits

Executors.newVirtualThreadPerTaskExecutor() spawns a new virtual thread for every submitted task and imposes no business concurrency limit. Virtual threads are cheaper than platform threads, but they still consume heap, stack state, objects, and external resources.

For example, if 5,000 RPCs wait on a database simultaneously while the connection pool only has 40 connections, most requests still queue at the pool. Virtual threads lower the cost of waiting threads; they do not make the database execute 5,000 queries concurrently.

Limits must be placed where resources are genuinely finite:

- Database connection pools and concurrent queries.
- HTTP connection pools, rate limits, and downstream capacity.
- Concurrent CPU-bound tasks.
- Active streams/subscriptions and data queues.
- Concurrent RPCs admitted into the service per tenant or method.

## 6. Using a Bulkhead to Bound Blocking Workloads

You can use a Semaphore to cap how many requests access an expensive resource concurrently:

~~~java
private final Semaphore databasePermits = new Semaphore(32);

public Order loadOrder(String orderId) {
    if (!databasePermits.tryAcquire()) {
        throw Status.RESOURCE_EXHAUSTED
            .withDescription("database concurrency limit reached")
            .asRuntimeException();
    }

    try {
        return orderRepository.findRequired(orderId);
    } finally {
        databasePermits.release();
    }
}
~~~

32 is only an illustrative value. Choose the limit based on the connection pool, instance count, background load, and database capacity. If each instance allows 32 queries and there are 10 instances, the database can receive up to 320 concurrent queries; compute capacity system-wide.

The bulkhead should wrap the protected resource and must release the permit in a finally block. If you choose to wait for a permit, bound the wait time by the remaining deadline; never let a virtual thread wait on a semaphore forever. When no more work can be accepted, return an appropriate overload status or apply admission control upstream.

## 7. Bounding CPU-Bound Work with a Dedicated Executor

CPU-bound work such as report calculation, data compression, or image processing does not become faster simply by running on a virtual thread. You can offload computation to a bounded platform thread pool:

~~~java
@Bean(destroyMethod = "shutdown")
ExecutorService cpuExecutor() {
    int cores = Runtime.getRuntime().availableProcessors();
    return Executors.newFixedThreadPool(Math.max(1, cores));
}
~~~

When a handler needs to run a CPU task, submit it to the dedicated executor and limit pending tasks. Do not use an unbounded queue for CPU work; a long queue raises latency and causes deadlines to expire before tasks even run. If the work can be split into chunks, check cancellation between chunks to stop early.

## 8. Propagating gRPC Context When Offloading Tasks

gRPC attaches the RPC's context to the service callback. When code explicitly submits work to another executor, capture the context so deadlines and cancellation remain in effect:

~~~java
Context rpcContext = Context.current();

Future<Report> task = cpuExecutor.submit(
    rpcContext.wrap(() -> buildReport(request)));

rpcContext.addListener(
    ignored -> task.cancel(true),
    cleanupExecutor);
~~~

Context.wrap(...) attaches the captured context when the task executes. The listener wires cancellation to Future.cancel(true), though the CPU task should also check interrupts or context state at safe points. Do not assume deadline expiration automatically interrupts every virtual thread.

For downstream gRPC calls made from offloaded tasks, the proper context keeps the parent deadline bounding child calls. If an independent background task must outlive the RPC, create a separate workflow with its own deadline and lifecycle rather than keeping the finished request's context.

## 9. Pinning and Blocking Libraries

A virtual thread needs a carrier thread to run. Certain blocking operations can hold onto the carrier instead of unmounting the virtual thread; this phenomenon is called **pinning**.

- On JDK 21–23, blocking while holding a synchronized monitor can pin the carrier in certain situations.
- Starting in JDK 24, JVM changes eliminated most pinning caused by synchronized monitors; however, native/foreign calls and certain runtime scenarios can still hold the carrier.
- Older libraries, drivers, or native code may exhibit blocking behavior that is not optimal for virtual threads.

Do not mechanically replace every synchronized block with another lock. Measure first with JFR and inspect stack traces. If a critical section performs blocking I/O, review the lock scope and avoid holding locks across wait periods.

You can use Java Flight Recorder to observe jdk.VirtualThreadPinned events and wait durations. Test on the exact JDK version running in production; virtual thread behavior can vary across Java releases.

## 10. ThreadLocal, Logging, and Context Propagation

Virtual threads support ThreadLocal, but the per-task model differs from traditional thread pools:

- Do not rely on a thread being reused across multiple requests.
- Avoid storing large objects or closeable resources in ThreadLocal.
- Clean up application-set ThreadLocal data when a task finishes if lifetimes can stretch or resources must be released.
- ThreadLocal-based MDC and trace contexts must be integrated with your logging/tracing context propagation mechanism.
- gRPC Context is a separate mechanism; do not assume MDC, Spring Security context, and gRPC Context propagate automatically across every executor.

Store trace IDs, tenant info, and request metadata in the appropriate context; use wrappers/decorators when crossing executors. Do not use thread names as request identifiers or assume stable thread identity across callbacks.

## 11. Deadlines and Cancellation with Virtual Threads

Virtual threads make blocking waits cheaper, but they do not allow requests to wait indefinitely. You still need finite client deadlines and propagation through nested calls. When the context is cancelled:

1. Stop starting new downstream steps.
2. Cancel futures or call handles where supported by the API.
3. Set query timeouts or call cancel on JDBC statements if supported by the driver.
4. Close HTTP requests, streams, or subscriptions appropriately.
5. Release semaphore permits and resources in finally blocks.

Future.cancel(true) can interrupt a running virtual thread, but the task stops promptly only if code and libraries respond to interrupts. Cancellation does not roll back committed transactions; commands with side effects still need idempotency keys or operation IDs.

## 12. Testing and Observing by Workload

Testing should cover:

- Many concurrent blocking RPCs: virtual threads increase while database concurrency stays within limits.
- High CPU load: the CPU executor does not exceed configured workers.
- Slow downstream: deadlines/cancellation stop tasks and release permits.
- Full queue/admission limit: the service returns controlled overload instead of spawning unbounded tasks.
- Context offload: deadlines and cancellation remain present inside offloaded tasks.
- Spring shutdown: the server stops accepting RPCs before the executor closes.
- Production JDK: no prolonged pinning or native calls holding carriers abnormally.

Monitor:

- Live virtual threads and active RPCs.
- Permits in use, permit wait time, and rejected requests.
- Database/HTTP pool utilization and connection wait times.
- CPU, carrier utilization, GC, and heap usage.
- JFR pinning events and stack traces of blocked virtual threads.
- Deadline statuses, cancellations, and tasks still running after an RPC ends.

Evaluate per workload. If virtual threads grow while throughput stays flat, the bottleneck may be the database, downstream services, CPU, or admission limits; adding more virtual threads will not resolve that bottleneck.

## 13. Takeaways and Self-Check

**Virtual threads fit high-concurrency blocking I/O handlers; workload limits must still rest on real resources.** Use virtual-thread-per-task for the service executor where appropriate, manage lifecycle through Spring, offload CPU-bound work to bounded pools, place bulkheads around databases/downstream services, propagate gRPC Context when offloading, and watch for pinning on the production JDK.

Self-check:

1. Why do virtual threads reduce the cost of waiting on I/O without speeding up CPU-bound work?
2. What can happen if you use virtual-thread-per-task without admission control?
3. Why cannot the number of concurrent virtual threads serve as a substitute limit for the database connection pool?
4. When offloading a task to another executor, what must you do to preserve deadlines and cancellation?
5. What is pinning, and what should you observe on the deployed JDK?

Combining virtual threads with bulkheads, concurrency limits, and deadlines enables Spring gRPC to handle many blocking requests while protecting databases, downstream services, and overall system stability.
