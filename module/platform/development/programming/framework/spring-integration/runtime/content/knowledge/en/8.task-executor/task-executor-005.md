# ThreadPoolTaskExecutor and Bounded Queues

In **SPRING_INTEGRATION_RUNTIME**, the executor decides which thread runs a task and how many tasks can wait for a worker. When a message flow offloads processing to an executor, the thread pool bounds parallelism, while a **bounded queue** limits how many tasks wait in memory. Both limits matter whenever producer arrival rates temporarily exceed handler processing rates.

Spring provides `ThreadPoolTaskExecutor` to configure and manage a Java thread pool under Spring's abstraction. Used with Spring Integration, the executor can be attached to an `ExecutorChannel`, a poller, or other components requiring asynchronous task execution. To keep the thread pool stable, you must understand task admission order, how the queue fills, rejection policies, transaction implications, and shutdown behavior.

## 1. Where Does the Executor Sit in the Message Flow?

A message flow can run synchronously on the sending thread or offload part of its work to worker threads. With `DirectChannel`, subscribers are usually invoked on the sending thread. With `ExecutorChannel`, the channel delegates dispatching to an executor.

~~~mermaid
flowchart LR
    A["Producer"] --> B["DirectChannel"]
    B --> C["Endpoint / handler"]
    C --> D["ExecutorChannel"]
    D --> E["ThreadPoolTaskExecutor"]
    E --> F["Task queue"]
    E --> G["Worker threads"]
    G --> H["Downstream handler"]
~~~

Each component has a distinct responsibility:

- **Channel** determines how messages pass between steps.
- **Dispatcher** selects which subscriber receives the message.
- **Executor** executes the task on the current thread or a worker thread.
- **Task queue** holds accepted tasks waiting for a worker.
- **Handler** executes business processing.

When a message passes through an `ExecutorChannel`, dispatch is handed off to the executor. The producer usually does not wait for the handler to finish; the send call can return once the executor accepts the task. Therefore, handler execution time and exceptions can occur after the sender has moved on.

## 2. What Is ThreadPoolTaskExecutor?

`ThreadPoolTaskExecutor` is Spring's `TaskExecutor` implementation built on Java's `ThreadPoolExecutor`. It exposes properties to control worker counts, queuing, idle-thread keep-alive time, thread naming, rejection policies, and shutdown.

Key parameters:

| Property | Meaning | Operational impact |
|---|---|---|
| `corePoolSize` | Baseline number of workers | Baseline parallelism of the pool |
| `maxPoolSize` | Maximum number of workers | Upper limit on concurrent running tasks |
| `queueCapacity` | Maximum number of queued tasks | Bounds the executor's in-memory backlog |
| `keepAliveSeconds` | Time non-core workers can remain idle before reclamation | Controls pool scale-down behavior |
| `allowCoreThreadTimeOut` | Allows core workers to time out | Can shrink threads during low load |
| `threadNamePrefix` | Worker thread name prefix | Aids reading logs and thread dumps |
| `rejectedExecutionHandler` | Behavior when the pool cannot accept more tasks | Determines rejection, caller execution, or task dropping |
| `taskDecorator` | Wraps a task before execution | Propagates MDC or appropriate context to the worker |

In common default configurations of `ThreadPoolTaskExecutor`, `corePoolSize` is 1, `maxPoolSize` is very large, and `queueCapacity` defaults to `Integer.MAX_VALUE`. A nearly unbounded default queue causes tasks to be queued instead of expanding workers beyond core. Therefore, when you need to cap backlog and control concurrency, explicitly configure `queueCapacity` together with `corePoolSize` and `maxPoolSize`.

An illustrative configuration:

~~~java
@Configuration
class IntegrationExecutorConfiguration {

    @Bean("integrationTaskExecutor")
    ThreadPoolTaskExecutor integrationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(12);
        executor.setQueueCapacity(100);
        executor.setKeepAliveSeconds(30);
        executor.setThreadNamePrefix("si-worker-");

        executor.setRejectedExecutionHandler(
            new ThreadPoolExecutor.AbortPolicy());

        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);

        return executor;
    }
}
~~~

Spring manages the executor bean and invokes its initialization lifecycle. When the executor is needed across multiple flows, inject this bean into the corresponding channels or poller configurations.

The numbers in this example are illustrative only. An actual pool must be sized based on processing time, message arrival rate, CPU limits, database connection pools, and external system capacity.

## 3. What Does a Bounded Queue Limit?

### 3.1 Task Queues Differ from Message Queues

The queue inside `ThreadPoolTaskExecutor` holds **`Runnable` tasks** awaiting worker execution. When Spring Integration hands a message to an executor, the task may hold a reference to the message and the dispatch logic.

This differs from `QueueChannel`:

| Criterion | ThreadPoolTaskExecutor Queue | QueueChannel |
|---|---|---|
| What is stored? | Executable tasks, usually holding the message inside | `Message` objects |
| Who takes items? | Executor worker threads | Polling consumers calling `receive()` |
| Purpose | Coordinate tasks and bound work waiting for workers | Buffer messages between producer and consumer |
| Capacity setting | `queueCapacity` | Channel queue capacity |
| Durability | Usually process memory | Depends on channel type and configured `MessageStore` |
| On abrupt process stop | Queued tasks can be lost | Messages in an in-memory queue can also be lost |

An executor's bounded queue is not a message broker and provides no durable messaging guarantees. It only bounds how many tasks can wait inside a single pool.

### 3.2 Why Is a Bounded Queue Needed?

If the queue is unbounded, producers can continue submitting tasks faster than workers process them. Backlog grows steadily, leading to:

- Memory consumed by tasks and the messages retained inside them.
- Increasing message wait times.
- Old messages waiting excessively long before processing.
- Upon recovery, a massive backlog continuing to overload databases or external services.
- Potential heap exhaustion and out-of-memory failures under memory pressure.

A bounded queue places an explicit cap on pending work. When the queue is full and the pool has reached its worker limit, the executor must apply its rejection policy. That is the point where the application decides how to react to overload.

### 3.3 What Does Queue Capacity 0 Mean?

In `ThreadPoolTaskExecutor`, a positive queue capacity creates a bounded `LinkedBlockingQueue`. A queue capacity of 0 or negative uses a `SynchronousQueue`, which performs a direct handoff between the submitting thread and a worker.

`SynchronousQueue` does not hold waiting tasks in a queue. If no worker is immediately ready to take the task, the thread pool can spawn a new worker up to `maxPoolSize`; once at the limit, the task is rejected according to the rejection policy.

Thus, a queue capacity of 0 does not mean "unbounded queue." It means no tasks are buffered waiting in a queue.

## 4. In What Order Does ThreadPoolExecutor Accept Tasks?

To tune a pool accurately, understand Java `ThreadPoolExecutor`'s task admission algorithm. With standard configurations, the general sequence is:

1. If fewer than `corePoolSize` workers are running, the pool tries to create a new worker to run the task.
2. Once core workers are all in use, the pool tries to enqueue the task.
3. If the queue cannot accept the task because it is full, the pool tries to create a new worker up to `maxPoolSize`.
4. If the queue is full and the worker count has reached `maxPoolSize`, the task is rejected.

~~~mermaid
flowchart TD
    A["Submit task"] --> B{"Workers < core?"}
    B -->|Yes| C["Create worker to run task"]
    B -->|No| D{"Queue has space?"}
    D -->|Yes| E["Enqueue task"]
    D -->|No| F{"Workers < max?"}
    F -->|Yes| G["Create additional worker"]
    F -->|No| H["Rejection policy"]
~~~

Key takeaway: the pool normally prefers queuing once `corePoolSize` is reached, and only scales workers beyond core when the queue fills up. Hence, raising `maxPoolSize` while keeping a huge queue may never grow workers as expected.

For example, with `corePoolSize=4`, `maxPoolSize=12`, and `queueCapacity=100`:

- The first four tasks can be assigned to the four core workers.
- Subsequent tasks are queued while queue space remains.
- Only once the queue is full can the pool spawn workers 5 through 12.
- Once all 12 workers are active and the queue remains full, new tasks are rejected.

This is why `corePoolSize`, `maxPoolSize`, and `queueCapacity` must always be evaluated together.

## 5. Configuring a Bounded Queue with ExecutorChannel

### 5.1 Wiring the Executor to the Channel

`ExecutorChannel` uses an executor to dispatch messages to subscribers. Example:

Imports and the `OrderService` type are omitted to focus on wiring the channel with the executor.

~~~java
@Configuration
class OrderFlowConfiguration {

    @Bean
    MessageChannel ordersAsyncChannel(
            @Qualifier("integrationTaskExecutor") Executor executor) {
        return new ExecutorChannel(executor);
    }

    @Bean
    IntegrationFlow orderFlow(
            MessageChannel ordersAsyncChannel,
            OrderService orderService) {

        return IntegrationFlow.from("orders.input")
            .channel(ordersAsyncChannel)
            .handle(orderService, "process")
            .get();
    }
}
~~~

In this example:

1. The producer sends a message to the input channel.
2. The flow routes the message to `ordersAsyncChannel`.
3. The executor accepts the dispatch task.
4. A worker thread invokes the `orderService.process` handler.

If queue space is available, the task is queued and the sender can continue. If both the pool and queue are saturated, send behavior follows the rejection policy.

### 5.2 ExecutorChannel Is Not QueueChannel

Both can introduce a time gap between send and processing, but their mechanisms differ:

- `ExecutorChannel` dispatches to a subscriber via an executor. Its internal queue holds tasks waiting for workers.
- `QueueChannel` holds `Message` instances and requires consumers to poll for messages.
- An executor queue does not expose a `receive()` API for applications to pull tasks.
- `QueueChannel` does not create a worker pool on its own; concurrency depends on consumers and downstream configuration.

Choose `ExecutorChannel` when you need to offload dispatch to workers. Choose `QueueChannel` when you need a message buffer from which consumers actively pull messages. When durability is required, consider a broker or an appropriate message store.

## 6. Rejection Policies When the Pool Saturates

When all workers are busy, the queue is full, and no additional workers can be created, the executor invokes its `RejectedExecutionHandler`. This policy directly affects the message flow.

### 6.1 AbortPolicy

`AbortPolicy` throws an exception when a task is rejected. This option is easy to observe because the producer or calling layer can immediately tell the system is saturated.

~~~java
executor.setRejectedExecutionHandler(
    new ThreadPoolExecutor.AbortPolicy());
~~~

In a flow, task submission failures can surface right at the dispatch operation. Determine where to catch the error, record logs/metrics, and decide whether to retry or return an error to the caller. Do not catch and swallow the exception if the message must be processed.

### 6.2 CallerRunsPolicy

`CallerRunsPolicy` makes the thread calling `execute()` run the task itself when the executor is still active but saturated.

~~~java
executor.setRejectedExecutionHandler(
    new ThreadPoolExecutor.CallerRunsPolicy());
~~~

This creates natural backpressure: the producer has to spend time executing the task, reducing its submission rate. However, the asynchronous boundary can shift under load. Handlers sometimes run on a worker thread and sometimes run directly on the message-sending thread.

This can alter producer latency, active thread-bound transactions, and how the application uses `ThreadLocal`. Do not rely on `CallerRunsPolicy` to guarantee that handlers always run on a specific thread. Once the executor has shut down, the JDK's `CallerRunsPolicy` does not run rejected tasks.

### 6.3 DiscardPolicy and DiscardOldestPolicy

- `DiscardPolicy` drops the newly rejected task without throwing an exception.
- `DiscardOldestPolicy` discards the oldest waiting task and retries submitting the new task.

Both policies can drop work without giving the application a clear error signal. For message flows handling orders, payments, or data requiring delivery guarantees, avoid these unless compensation, auditing, and explicit acceptance of message loss are in place.

### 6.4 Choosing a Policy Based on Business Requirements

| Policy | Behavior | When to consider |
|---|---|---|
| `AbortPolicy` | Rejects with an exception | Need to detect overload and handle failures explicitly |
| `CallerRunsPolicy` | Sending thread runs the task | Acceptable for applying backpressure when blocking the producer is tolerable |
| `DiscardPolicy` | Drops the new task | Only for droppable work with separate monitoring |
| `DiscardOldestPolicy` | Drops the oldest queued task | Only when newest data takes priority and losing older data is acceptable |
| Custom handler | Application-defined behavior | Need custom metrics, auditing, or specialized routing |

No single rejection policy fits every system. Align it with SLAs, retry capabilities, message criticality, and how producers react to rejection.

## 7. Choosing corePoolSize, maxPoolSize, and queueCapacity

### 7.1 Measuring Arrival Rate and Processing Time

Before choosing pool sizes, gather:

- Average and peak task arrival rates.
- Average, p95, and p99 handler processing times.
- Ratio of CPU-bound vs. I/O-bound tasks.
- Connection pool limits for databases and external services.
- Allowed parallelism per business key.
- Maximum tolerable wait time per message.

A rough estimate: if a handler takes 100 ms on average and 8 workers are active, theoretical capacity is roughly 80 tasks/second when workers stay busy. This is only a rough estimate; I/O waits, locks, GC, downstream systems, and latency distributions can alter actual throughput substantially.

If a database permits only 10 concurrent connections, scaling workers to 100 can simply cause more tasks to wait on connections instead of increasing throughput. Tune the pool to match the real bottleneck.

### 7.2 The Queue Is a Burst Buffer, Not an Unbounded Backlog Store

`queueCapacity` should be large enough to absorb short bursts that the system can drain within acceptable latency limits. An overly large queue can mask insufficient processing capacity and cause messages to wait too long.

For example, if the system processes 80 tasks/second and a burst adds 160 tasks to the backlog, a queue of 160 can absorb about two seconds of work under ideal conditions. If arrival rate stays above completion rate, the queue will fill again; enlarging the queue only delays when rejection starts.

An operational rule of thumb:

- Size workers to the concurrency CPU and dependencies can sustain.
- Size the queue for bursts and maximum wait time.
- Pick a rejection policy matching backpressure or retry capabilities.
- Add metrics to detect queue growth before it stays chronically full.

### 7.3 Why Can a Large Queue Worsen Latency?

When a queue holds 1,000 tasks, a newly arriving task must wait behind all preceding tasks. If workers run slowly, even tasks that are not rejected can violate SLAs.

Bounded queues should be sized for acceptable wait time, not merely message count. Queue capacity limits waiting tasks; it makes no promise about completion time.

## 8. Backpressure and Protecting Downstream Systems

Backpressure slows the upstream source when downstream systems can no longer accept more work. A bounded queue combined with a rejection policy can signal overload or force producers to slow down.

Common strategies:

- **Abort + retry with backoff:** producer catches the error and retries after progressively longer delays.
- **CallerRunsPolicy:** producer executes the task itself, naturally throttling submission rate.
- **Concurrency limits:** reduce worker counts to protect databases or APIs.
- **QueueChannel/broker:** decouple producer and consumer with dedicated storage semantics.
- **Rate limiting:** cap submission rate before submitting tasks.
- **Circuit breaker:** temporarily stop calling a failing dependency to avoid piling up waiting tasks.

Never retry immediately in a tight loop when an executor rejects tasks. That adds pressure precisely when the system is overloaded. Use delays, jitter, retry limits, and a dead-letter/error flow when messages cannot proceed.

## 9. Thread Context, Transactions, and Exceptions

### 9.1 Transactions Do Not Propagate Automatically to Worker Threads

Standard Spring transactions are bound to the current thread. When a message crosses an `ExecutorChannel`, the handler runs on a worker thread; the producer's transaction does not propagate automatically to the worker.

If the handler needs a transaction, place the transaction boundary on the endpoint or service executing on the worker thread. Do not rely on sender and handler occasionally sharing a thread under `CallerRunsPolicy`; that behavior only occurs during pool saturation.

### 9.2 MDC and ThreadLocal

Values in `ThreadLocal`, such as logging MDC, are not copied automatically to worker threads. If logs need correlation IDs or tracing fields, use a `TaskDecorator` to capture context on the submitting thread and restore it inside the worker.

Illustrative example with SLF4J MDC:

~~~java
executor.setTaskDecorator(task -> {
    Map<String, String> captured = MDC.getCopyOfContextMap();

    return () -> {
        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            if (captured == null) {
                MDC.clear();
            }
            else {
                MDC.setContextMap(captured);
            }
            task.run();
        }
        finally {
            if (previous == null) {
                MDC.clear();
            }
            else {
                MDC.setContextMap(previous);
            }
        }
    };
});
~~~

This snippet requires the corresponding `MDC` and `Map` imports. Restoring the previous context in `finally` prevents data from a prior task from leaking into the next task running on the same worker thread.

For tracing or security contexts, prefer propagation mechanisms provided by the respective libraries; do not copy arbitrary `ThreadLocal` values indiscriminately.

### 9.3 Exceptions in Asynchronous Processing

If a task is rejected during submission, the error can surface on the sender. If the task is accepted and the handler throws an exception later, the sender usually cannot receive that exception as a synchronous call error.

Configure flow error handling using an error channel or appropriate monitoring. Track separately:

- Submission errors caused by a full queue or executor shutdown.
- Handler exceptions thrown while a task runs.
- Dependency errors such as database or HTTP failures.
- Failures after exhausting retries.

Never equate "send succeeded" with "handler succeeded." With an executor, a successful send typically only indicates the task was accepted for execution.

## 10. Shutdown and Queued Tasks

`ThreadPoolTaskExecutor` is a lifecycle-managed resource. When the application stops, define how running tasks and remaining queued tasks should be handled.

You can configure:

~~~java
executor.setWaitForTasksToCompleteOnShutdown(true);
executor.setAwaitTerminationSeconds(30);
~~~

Meaning:

- Instructs the executor to wait for submitted tasks to finish during shutdown.
- Caps the wait duration in this example at 30 seconds.
- If the timeout expires, the application must recognize that remaining tasks may still be incomplete.

Graceful shutdown should coordinate with the message flow:

1. Stop accepting new messages from ingress or producers.
2. Wait for submitted tasks to finish within the allowed timeout.
3. Monitor active workers and queue size.
4. Stop endpoints and release the executor per lifecycle.
5. Record unfinished tasks for recovery if business requirements demand it.

An executor's queue resides only in memory. If the process is killed or the machine loses power, queued tasks are not guaranteed to survive. For messages requiring durability, persist them in a broker or durable store before handing work to workers.

## 11. Observing ThreadPoolTaskExecutor at Runtime

`ThreadPoolTaskExecutor` exposes runtime details such as pool size, active count, and completed task count. Combine these with application metrics for observability:

| Metric | Meaning | Warning sign |
|---|---|---|
| Pool size | Current number of workers | Constantly pinned at max may indicate under-provisioning |
| Active count | Number of busy workers | Always equal to pool size means the pool is chronically saturated |
| Queue size | Number of waiting tasks | Steadily growing means arrival rate exceeds processing rate |
| Completed task count | Completed tasks | Useful for calculating throughput over time |
| Rejected task count | Rejected tasks, if tracked separately | Sudden spikes indicate overload or shutdown |
| Queue wait time | Time a task waits before running | High values can breach SLAs even without rejections |
| Handler duration | Business processing time | Distinguishes executor bottlenecks from downstream bottlenecks |

Several properties can be read from an initialized executor:

~~~java
int poolSize = executor.getPoolSize();
int activeCount = executor.getActiveCount();
int queueSize = executor.getThreadPoolExecutor()
    .getQueue()
    .size();
~~~

Only call `getThreadPoolExecutor()` after the executor has been initialized. If the bean has not initialized yet, the underlying executor is not ready.

Use meaningful thread names to locate threads in logs and thread dumps, such as `si-order-` or `si-invoice-`. Track queue size alongside queue wait time; looking at CPU or active count alone is insufficient to pinpoint why processing is slow.

## 12. Diagnostic Workflow When the Queue Fills Up

When the executor repeatedly fills its queue or rejects tasks, inspect in order:

1. Identify which tasks are being submitted and from which endpoint or channel.
2. Measure task arrival rate over a representative window.
3. Measure average and p95/p99 handler processing durations.
4. Inspect pool size, active count, and queue size.
5. Check dependencies: database pools, remote APIs, locks, and file I/O.
6. Inspect the rejection policy and where exceptions are handled.
7. Check whether overly aggressive retries are amplifying load.
8. Compare queue wait time against SLAs.
9. Tune workers, queue, or backpressure, then re-measure.

Do not increase queue capacity before understanding why workers are falling behind. If the database is the bottleneck, adding workers may merely pile up more threads waiting on connections. If a handler has a CPU-bound section, raising concurrency too high can increase context switching and reduce throughput.

## 13. Testing Bounded Queues and Rejection

Test both normal operation and saturation:

- Pool scales between core and max according to test load.
- Queue never exceeds its configured capacity.
- Tasks are accepted while queue space remains.
- Rejection policy triggers properly when both workers and queue are full.
- `CallerRunsPolicy` slows down producers as intended.
- `AbortPolicy` raises an error signal so callers can handle it.
- `TaskDecorator` restores MDC after tasks complete.
- Shutdown waits for tasks up to the configured timeout.
- Rejected tasks and handler errors are captured via logs, metrics, or error flows.

To test rejection deterministically, use a mock handler with a latch to hold workers busy, submit enough tasks to fill the queue, and then submit one extra task. Avoid arbitrary sleeps to guess when the queue is full.

## 14. Common Misconceptions to Avoid

- **A bounded executor queue is not a QueueChannel:** one stores tasks, the other stores `Message` instances.
- **`maxPoolSize` does not mean the pool always grows to max:** thread pools queue tasks after reaching core and only grow beyond core once the queue is full.
- **A larger queue does not raise throughput:** it only buffers more waiting tasks and can worsen latency.
- **Queue capacity 0 is not an unbounded queue:** it uses direct handoff instead.
- **`ExecutorChannel` does not guarantee processing success:** it only delegates dispatch to an executor.
- **`CallerRunsPolicy` shifts the execution thread:** do not depend on a fixed thread boundary during pool saturation.
- **Discard policies can drop tasks:** never use them for critical messages without compensation mechanisms.
- **Transactions and `ThreadLocal` do not propagate automatically across workers:** configure explicit boundaries and context propagation.
- **In-memory queues are not durable:** use a broker or durable store when messages must not be lost.
- **Enlarging the pool does not always increase throughput:** factor in database, API, CPU, and lock limits.

## 15. Self-Check

1. With `corePoolSize = 4`, `maxPoolSize = 12`, and `queueCapacity = 100`, when is the 5th worker created?
2. Why can an unbounded queue prevent `maxPoolSize` from ever taking effect?
3. Does `ThreadPoolTaskExecutor`'s queue hold `Runnable` tasks or `Message` objects? How does it differ from `QueueChannel`?
4. When the queue is full, how do `AbortPolicy` and `CallerRunsPolicy` behave differently?
5. Why can `CallerRunsPolicy` change the observed transaction and thread context?
6. If queue size grows steadily while CPU stays low, which dependencies should be checked before adding workers?
7. Why can you not rely on an executor queue to preserve messages after a process kill?
8. When removing a flow or shutting down an application, in what order should the executor and ingress be coordinated?

## References

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — ThreadPoolTaskExecutor API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Java — ThreadPoolExecutor API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Spring Integration — ExecutorChannel API](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/channel/ExecutorChannel.html)

## Conclusion

`ThreadPoolTaskExecutor` manages worker threads and a task queue for components needing asynchronous execution. A bounded queue caps waiting tasks, while `corePoolSize` and `maxPoolSize` bound parallelism. When the queue fills, the rejection policy dictates how the system responds, affecting backpressure, potential task loss, and which thread runs the work. For stable configuration, measure task arrival rates, processing durations, queue wait times, and downstream limits, then size pools, queues, and rejection policies to match SLAs. Because an executor queue is only an in-memory buffer, messages requiring durability must be persisted in a broker or durable store before asynchronous processing.
