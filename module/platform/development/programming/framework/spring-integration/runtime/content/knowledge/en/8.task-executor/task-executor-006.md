# Core Pool, Max Pool, and Queue Capacity

In Spring Integration Runtime, a `TaskExecutor` determines which thread executes tasks and how much work can run concurrently. With `ThreadPoolTaskExecutor`, the three most important parameters are `corePoolSize`, `maxPoolSize`, and `queueCapacity`.

These three parameters do not operate independently. `corePoolSize` sets the baseline worker count; `queueCapacity` determines how many tasks wait before the pool expands; `maxPoolSize` caps the worker count once the queue is full. Consequently, increasing `maxPoolSize` while keeping an unbounded queue usually never causes the pool to spawn extra threads. Conversely, setting the queue too small or to 0 can rapidly multiply threads and push load onto databases, HTTP clients, or downstream systems.

To configure this properly, understand `ThreadPoolExecutor`'s task admission algorithm, then choose limits based on workload, downstream resources, and saturation policies.

## 1. How Does TaskExecutor Participate in a Message Flow?

Spring Framework defines `TaskExecutor` so applications can submit a `Runnable` to an execution mechanism. An implementation may run the task on a dedicated thread, a thread pool, or even synchronously; the abstraction name alone does not guarantee a thread pool.

In Spring Integration, executors typically appear at two boundaries:

- **ExecutorChannel** uses an executor to dispatch messages to subscribers on worker threads. Sending the message and executing the handler become two separate execution phases.
- **Polling endpoints** can configure a `TaskExecutor` so polling tasks run on workers instead of occupying `TaskScheduler` threads.

Simple diagram:

~~~mermaid
flowchart TD
    P["Producer / Poller"] --> S["Submit task"]
    S --> E["ThreadPoolTaskExecutor"]
    E --> A{"Pool admission"}
    A -->|"Worker available / create core"| W["Worker thread"]
    A -->|"Queue has capacity"| Q["Work queue"]
    Q --> W
    A -->|"Queue full, below max"| X["Create extra worker"]
    X --> W
    A -->|"At max and queue full"| R["Reject task"]
    W --> H["Handler / business work"]
~~~

An executor controls task execution. It does not determine whether messages are persisted durably, acknowledged, or retried. When a message travels through an `ExecutorChannel`, the executor queue is an in-JVM `Runnable` queue; it differs from a `QueueChannel` holding messages and differs from a broker queue.

### Why Distinguish Between These Queues?

| Queue | What does it hold? | Who pulls items out? |
|---|---|---|
| `QueueChannel` | `Message<?>` waiting for a consumer | Polling consumer |
| Executor work queue | `Runnable` tasks waiting for a worker | Executor worker thread |
| Broker queue | Messages stored by a broker | Broker consumer/adapter |

A message may already have been pulled from a `QueueChannel`, yet its processing task is still waiting on the executor. Conversely, the executor queue may hold polling tasks waiting for workers while the message queue has no data yet. When investigating backlog, inspect the right queue.

## 2. The Three Core Parameters

| Parameter | Meaning | Primary impact |
|---|---|---|
| `corePoolSize` | Number of core workers maintained according to timeout policy | Determines when the pool begins queuing tasks |
| `maxPoolSize` | Maximum number of workers permitted in the pool | Caps concurrency when the queue cannot accept more tasks |
| `queueCapacity` | Number of tasks that can wait in the work queue | Determines when the pool spawns workers beyond core |

A worker does not necessarily exist right at application startup. By default, threads are typically created on demand as tasks arrive. You can prestart core threads if you want the pool ready before receiving traffic.

`corePoolSize` is neither a cap on total active tasks nor a fixed count of always-live threads. It is `ThreadPoolExecutor`'s core worker threshold. `maxPoolSize` is the upper bound, while `queueCapacity` governs whether the pool ever expands from core toward max.

### Default Values of ThreadPoolTaskExecutor

According to the Spring Framework Javadoc, `ThreadPoolTaskExecutor` defaults to:

| Property | Default value |
|---|---:|
| `corePoolSize` | 1 |
| `maxPoolSize` | `Integer.MAX_VALUE` |
| `queueCapacity` | `Integer.MAX_VALUE` |
| `keepAliveSeconds` | 60 |
| `allowCoreThreadTimeOut` | `false` |

The default configuration behaves much like a single-worker executor because an almost unbounded queue absorbs tasks once the core thread is busy. A huge `maxPoolSize` does not expand threads while the queue keeps accepting tasks.

These are the defaults of the `ThreadPoolTaskExecutor` class. If your application uses Spring Boot auto-configuration or declares its own executor bean, inspect the actual bean and configuration properties; never assume every application's executor shares identical values.

## 3. ThreadPoolExecutor's Task Admission Algorithm

The most critical detail is the priority order between workers and the queue. When a new task is submitted, `ThreadPoolExecutor` generally proceeds as follows:

1. If the current worker count is less than `corePoolSize`, try creating a new worker to run the task.
2. Once core size is reached, try adding the task to the work queue.
3. If the queue cannot accept the task because it is full, try creating a new worker beyond core size, provided `maxPoolSize` has not been reached.
4. If the task cannot be queued and no additional worker can be created, reject the task per the rejection policy.

Visualize it as a flowchart:

~~~mermaid
flowchart TD
    N["New task submitted"] --> C{"Worker count < core?"}
    C -->|"Yes"| NC["Create core worker to run task"]
    C -->|"No"| Q{"Queue accepts task?"}
    Q -->|"Yes"| ENQ["Enqueue task"]
    Q -->|"No"| M{"Worker count < max?"}
    M -->|"Yes"| NM["Create worker above core"]
    M -->|"No"| RJ["Rejection policy"]
~~~

Example configuration:

- `corePoolSize = 4`
- `maxPoolSize = 12`
- `queueCapacity = 100`

If tasks arrive continuously and workers have not finished yet:

| Task batch | Behavior |
|---|---|
| Tasks 1–4 | Creates up to 4 core workers to execute them |
| Subsequent tasks, up to 100 tasks | Placed into the queue |
| Once the queue is full | Pool starts creating workers 5 through 12 |
| Once 12 workers are active and queue remains full | New tasks are rejected |

These numbers illustrate saturation while workers remain busy. In live runtime, workers finish and pull tasks from the queue while new tasks arrive, so counts in each tier fluctuate continuously.

### Why Is the Queue Checked Before maxPoolSize?

This is intentional `ThreadPoolExecutor` behavior. Once core workers exist, the executor prefers queuing tasks. Only when the queue rejects a task does it scale workers past core.

Therefore, `maxPoolSize` takes effect only when the queue is bounded and already full. A configuration of `core=4`, `max=20`, `queueCapacity=Integer.MAX_VALUE` will normally still run at most 4 workers under typical loads while queued tasks accumulate heavily.

## 4. Queue Capacity Determines the Scaling Strategy

`queueCapacity` is not just how many tasks may wait. It determines how long the executor buffers tasks in the queue before adding workers.

Spring `ThreadPoolTaskExecutor` creates the backing queue based on `queueCapacity`:

- A positive value creates a `LinkedBlockingQueue` with that capacity.
- A value of `0` creates a `SynchronousQueue`, a direct handoff mechanism that stores no waiting tasks.
- With an unbounded queue, tasks continue entering the queue and the pool never needs to grow past core.

### Unbounded Queue

Example:

~~~java
executor.setCorePoolSize(4);
executor.setMaxPoolSize(20);
// queueCapacity not set: default is very large
~~~

Once 4 workers are busy, incoming tasks keep entering the queue. The executor never needs to spawn a 5th worker because the queue still accepts tasks.

Consequences:

- `maxPoolSize=20` has virtually no effect while the queue continues accepting tasks.
- Task wait time can climb steadily when arrival rate exceeds completion rate.
- The queue can consume heap until memory pressure or `OutOfMemoryError` occurs.
- The pool may look calm because thread counts stay low, even as latency and backlog grow.

An unbounded queue can fit certain workloads with controlled load and independent tasks, but it is not a safe default for messaging systems facing bursts or unconstrained producers.

### Bounded Queue

Example:

~~~java
executor.setCorePoolSize(4);
executor.setMaxPoolSize(12);
executor.setQueueCapacity(100);
~~~

The pool starts with up to 4 core workers. When all core workers are busy, up to 100 subsequent tasks wait. Only when the queue fills does the executor create workers above core up to 12. Once all 12 workers are busy and the queue is full, new tasks are rejected.

Advantages:

- Bounds the number of waiting tasks held in memory.
- Establishes a clear threshold for pool expansion.
- Predictably bounds roughly active plus waiting tasks.
- At saturation, overload surfaces via rejection instead of unbounded backlog growth.

In return, a queue that is too small can make the pool scale up frequently and reject brief bursts. A queue that is too large forces tasks to wait longer before scaling workers and can mask slow downstream dependencies.

### SynchronousQueue with queueCapacity 0

`SynchronousQueue` stores no elements. Each submission must hand off directly to an immediately available worker or trigger creating a new worker if below max.

Example:

~~~java
executor.setCorePoolSize(4);
executor.setMaxPoolSize(12);
executor.setQueueCapacity(0);
~~~

When all 4 core workers are busy, a new task cannot wait in a queue. The pool creates workers beyond core up to 12. When all 12 workers are busy and none can accept directly, the task is rejected.

This responds quickly by adding threads, but concurrency can spike sharply during bursts. Always set a finite `maxPoolSize` and verify database, HTTP connection, CPU, and memory limits. `queueCapacity=0` does not mean "unlimited tasks"; it means no queue waiting buffer.

## 5. Comparing Queue Configurations

| Queue configuration | Behavior when core is busy | Effect on maxPoolSize | Primary risk |
|---|---|---|---|
| Unbounded (`Integer.MAX_VALUE`) | Almost always queues tasks | Max is rarely utilized | Backlog and heap growth |
| Bounded (e.g., 100) | Queues up to 100 tasks | Adds workers once queue is full | Poorly chosen capacity increases latency or rejections |
| Direct handoff (`0`) | Stores no tasks; hands off or creates worker | Scales rapidly to max | Rapid thread growth; early rejections once max is hit |

No single queue type is universally best. Choose based on burst intensity, task duration, latency tolerance, and downstream concurrency capacity.

## 6. Example ThreadPoolTaskExecutor Configuration in Spring

A configuration bounding both workers and queue:

~~~java
@Configuration
class IntegrationExecutorConfiguration {

    @Bean("integrationTaskExecutor")
    ThreadPoolTaskExecutor integrationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(12);
        executor.setQueueCapacity(100);
        executor.setKeepAliveSeconds(60);

        executor.setThreadNamePrefix("si-worker-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy()
        );

        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);

        return executor;
    }
}
~~~

Spring manages the lifecycle of `ThreadPoolTaskExecutor` when the bean is registered in the application context. Key properties to note:

- `corePoolSize`: baseline workers retained according to timeout policy.
- `maxPoolSize`: upper worker limit.
- `queueCapacity`: tasks permitted to wait before scaling beyond core.
- `keepAliveSeconds`: idle time allowed for non-core workers before reclamation.
- `threadNamePrefix`: helps identify the pool in logs and thread dumps.
- `rejectedExecutionHandler`: policy when the executor cannot accept more tasks.
- `waitForTasksToCompleteOnShutdown`: requests waiting for tasks to complete during shutdown.
- `awaitTerminationSeconds`: maximum wait time for pool termination as configured.

The values 4, 12, and 100 are only examples to explain the algorithm. Do not copy them into production without measuring your application's load and resource constraints.

## 7. Rejection Policies When the Pool Saturates

Once worker count reaches max and the queue has no remaining room, the executor must decide what to do with new tasks. This forms part of the behavioral contract between producer and executor.

| Policy | Behavior | When to consider |
|---|---|---|
| `AbortPolicy` | Throws `RejectedExecutionException`; Spring `ThreadPoolTaskExecutor` translates it to `TaskRejectedException` per `TaskExecutor` contract | When you want an explicit error to retry, alert, or handle at the caller |
| `CallerRunsPolicy` | Submitting thread runs the task itself if the executor has not shut down | Creates backpressure when the caller can tolerate blocking |
| `DiscardPolicy` | Drops the new task without raising an error | Use only when tasks are safely droppable and explicitly approved |
| `DiscardOldestPolicy` | Drops the oldest queued task and retries submitting the new task | Consider only when old tasks are expendable and ordering has been evaluated |

For critical message processing, `DiscardPolicy` and `DiscardOldestPolicy` can silently lose work without proper recovery. Avoid using them merely to suppress exceptions.

### CallerRunsPolicy Can Provide Backpressure

When the executor saturates, `CallerRunsPolicy` forces the submitting thread to execute the task itself. Producer throughput slows down as a result, creating a simple form of backpressure.

However, identify which thread is doing the submitting:

- With `ExecutorChannel`, it may be the thread calling `send()`.
- With a poller, it may be the scheduler thread.
- With a request-handling service, it may be an HTTP request thread.

If the caller is a shared scheduler thread, `CallerRunsPolicy` can delay other pollers. If the caller holds a transaction or lock while running the task, it can extend resource hold times or cause a deadlock if the task depends back on the caller.

### Rejection Differs from Handler Failure

`TaskRejectedException` means the executor declined to accept the task under its current policy. It does not mean the handler ran and failed.

Distinguish between:

- **Submit failure:** the task was not accepted by the executor.
- **Execution failure:** the task ran, but code inside threw an exception.
- **Business failure:** the handler ran cleanly technically, yet business rules rejected the request.

These three failure types often require different retry, logging, and error-handling strategies.

## 8. How Does Queue Capacity Affect Latency?

A large queue reduces rejections during brief bursts, but tasks can wait a long time before processing. When the queue stays nearly full, users often see rising latency even when CPU is well below 100%.

For example, consider an executor with 4 workers where each task averages 200 ms. If 100 tasks sit in the queue, wait time for the last task can reach several seconds even if no new tasks arrive. This is just an estimate assuming sequential drain by four workers; actual times depend on task length variation and worker scheduling.

Queue capacity must balance three goals:

1. Absorb short bursts without immediate rejections.
2. Keep task wait times within acceptable latency bounds.
3. Avoid retaining too many tasks on the heap when downstream slows down.

A full queue is not necessarily an immediate failure if the burst is ending and workers are draining it. However, continuously growing queue depth over an extended period signals that arrival rate exceeds completion rate.

### Estimating Capacity for Bursts

If arrival rate is `λin` tasks/second and completion rate is `λout` tasks/second, when `λin > λout`, backlog grows roughly by:

\[
\Delta Q \approx (\lambda_{in} - \lambda_{out}) \times t
\]

Where `t` is the burst duration. For instance, if the system receives 80 tasks/second and processes 60 tasks/second during a 5-second burst, backlog grows by approximately 100 tasks. This is an initial estimate; actual backlog also depends on concurrency, task durations, and arrival distribution.

Do not size `queueCapacity` solely from average task counts. Observe real bursts, p95/p99 latency, and how quickly downstream recovers from slowdowns.

## 9. Sizing corePoolSize and maxPoolSize by Workload

Pool sizing should reflect task characteristics and resource constraints.

| Workload | Initial sizing approach |
|---|---|
| CPU-bound | Start near available CPU cores; too many threads increase context switching |
| I/O-bound | Can use more threads because workers spend time waiting on I/O, but bound by connection pools and target services |
| Short tasks, steady traffic | Core size sufficient for baseline load; moderate queue to smooth fluctuations |
| Long tasks, heavy bursts | Bounded queue and finite max pool to control concurrency |
| Low-latency responsive tasks | Smaller queue or direct handoff, while managing rejections and max size |
| Background tasks tolerant of delay | Larger queue if latency is acceptable and heap is bounded |

An initial concurrency estimate can use Little's Law:

\[
N \approx \lambda \times W
\]

Where `λ` is target throughput (tasks/second), `W` is average processing time (seconds), and `N` is average concurrent tasks needed in steady state.

For instance, processing 20 tasks/second where each takes 0.25 seconds yields average concurrency of roughly 5 tasks. A 5-thread pool is only a theoretical starting point; leave headroom for processing-time variance, retries, and I/O waits, and verify whether downstream can handle 5 or more concurrent requests.

### Core and Max Do Not Substitute for Each Other

- Core too low can slow baseline processing if a large queue prevents the pool from expanding.
- Core too high keeps many idle threads consuming resources even during low load.
- Max too low rejects tasks when bursts exceed pool and queue capacity.
- Max too high spawns too many threads, straining CPU, stack memory, database connections, or API rate limits.
- Queue too large delays scaling and increases latency.
- Queue too small triggers early worker expansion and rejects short bursts.

Adjust all three together based on metrics instead of raising max alone to cure every problem.

## 10. keepAlive and Worker Lifecycle

Once a pool scales past `corePoolSize`, non-core workers can be reclaimed if idle longer than `keepAliveSeconds`.

Example:

~~~java
executor.setCorePoolSize(4);
executor.setMaxPoolSize(12);
executor.setKeepAliveSeconds(30);
executor.setAllowCoreThreadTimeOut(false);
~~~

With this setup, workers above core can be reclaimed after roughly 30 seconds idle. Core workers are retained by default.

Enabling `allowCoreThreadTimeOut(true)` allows core threads to time out when idle as well, provided keep-alive time is greater than 0. This lets the pool shrink further under low traffic, at the cost of recreating threads when traffic returns.

`prestartAllCoreThreads` can pre-create core workers before the first task arrives. This reduces thread-creation latency on the first task but allocates pool resources immediately on startup.

## 11. Using Executors in Spring Integration

### ExecutorChannel

`ExecutorChannel` uses a `TaskExecutor` to dispatch messages to subscribers:

~~~java
@Bean
MessageChannel asyncOrdersChannel(
        @Qualifier("integrationTaskExecutor") TaskExecutor executor
) {
    return new ExecutorChannel(executor);
}
~~~

When a producer sends a message, the executor receives the dispatch task. The handler runs on a worker thread. This boundary drops single-thread execution context between sender and receiver; transaction context bound to the sending thread does not propagate automatically to the handler. If the handler throws an exception after the sender has returned, that exception cannot propagate up the normal call stack.

Accordingly, `ExecutorChannel` requires appropriate `queueCapacity` and rejection policies. When the executor saturates, `send()` may hit task-rejection errors depending on executor and channel configuration.

### Poller with TaskExecutor

A polling endpoint can use a dedicated executor:

~~~java
@Bean
IntegrationFlow ordersPollingFlow(
        QueueChannel ordersQueue,
        @Qualifier("integrationTaskExecutor") TaskExecutor executor,
        OrderHandler handler
) {
    return IntegrationFlow.from(
                    ordersQueue,
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(500)
                                    .maxMessagesPerPoll(10)
                                    .taskExecutor(executor)
                    )
            )
            .handle(handler, "process")
            .get();
}
~~~

Here, the executor runs the polling tasks. `corePoolSize`, `maxPoolSize`, and `queueCapacity` determine how many poll tasks execute, wait, or get rejected. When multiple pollers share an executor, one poller with long batches or a large `receiveTimeout` can occupy workers and starve other endpoints.

### Sharing vs. Splitting Executors?

| Organization | Advantage | Risk |
|---|---|---|
| One shared executor | Fewer pools, centralized management | Slow workloads can starve workers needed by critical flows |
| Executor per workload group | Better resource isolation | More pools increase total threads and configuration complexity |
| Dedicated executor per endpoint | Fine-grained control | Easy to spawn too many threads and duplicate configuration |

Group executors by SLA and workload profile. Avoid creating one pool per flow if flows carry light traffic under the same operational policy. Equally, avoid dumping every task into one pool if one workload can monopolize all workers.

## 12. Avoiding Starvation and Deadlock When the Queue Fills

Some failures stem not from too few threads, but from how tasks depend on each other.

For example, suppose a pool has 4 workers. All 4 workers are running task A; each task A blocks waiting for a task B submitted to the same executor. The queue is full or no idle worker exists to run B. Task A cannot finish, and task B cannot run. This is thread starvation or thread-pool deadlock.

Keep in mind:

- Avoid having tasks in a pool synchronously wait on `Future.get()` for another task submitted to the exact same pool unless concurrency headroom is guaranteed.
- Do not let a callback require the same executor while blocked by tasks waiting on that callback.
- Never use `CallerRunsPolicy` when the caller holds a lock that the task itself must acquire.
- Avoid unbounded queues if tasks have cross-dependencies that could pile up.
- Separate executors for work groups with distinct dependencies or SLAs when necessary.

A bounded queue and finite max make saturation visible sooner, but they do not fix deadlocks on their own. Design task dependencies and timeouts carefully.

## 13. TaskDecorator and Context Propagation

Worker threads are reused across tasks. `ThreadLocal` values such as logging MDC, tracing context, or security context must not be assumed to transfer automatically from the submitting thread to the worker.

`ThreadPoolTaskExecutor` supports `TaskDecorator` to wrap tasks before execution. Use a decorator to capture and restore context appropriate for your libraries.

General illustrative example with MDC:

~~~java
executor.setTaskDecorator(task -> {
    Map<String, String> context = MDC.getCopyOfContextMap();

    return () -> {
        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            if (context != null) {
                MDC.setContextMap(context);
            }
            else {
                MDC.clear();
            }
            task.run();
        }
        finally {
            if (previous != null) {
                MDC.setContextMap(previous);
            }
            else {
                MDC.clear();
            }
        }
    };
});
~~~

This example only illustrates capturing and restoring MDC. For tracing and security contexts, use the official propagation mechanisms provided by those libraries to avoid incorrect copying or context leaks between tasks. Always restore or clear context in `finally`, because worker threads are reused.

## 14. Observing the Pool at Runtime

`ThreadPoolTaskExecutor` exposes management and monitoring attributes such as `corePoolSize`, `maxPoolSize`, `keepAliveSeconds`, `poolSize`, and `activeCount`. Some configuration properties can be adjusted at runtime depending on version and bean management.

Metrics to track:

| Metric | Meaning | Signal to investigate |
|---|---|---|
| Pool size | Current worker count | Continuously climbing toward max |
| Active count | Busy workers | Constantly equal to max |
| Queue depth | Waiting tasks | Rising steadily without draining after bursts |
| Queue capacity | Waiting task limit | Frequently hitting 100% |
| Rejected task count | Rejected tasks | Sudden spikes or sustained rejections |
| Task wait time | Time from submission to execution start | Rising p95/p99 |
| Task execution time | Time worker spends running task | Increasing due to slow downstream |
| Completed task count | Completed tasks | Growing slower than submission rate |

`activeCount` equaling `corePoolSize` is not automatically a problem; look at queue depth, task wait time, and completion rate. Pool size pinned at max alongside a full queue and rising rejections is a much clearer sign of saturation.

### Interpreting Common Observations

| Observation | Likely interpretation |
|---|---|
| Pool stays at core workers while queue grows | Queue still has capacity, so executor has not scaled past core yet |
| Pool grows to max and queue is full | Load exceeds current capacity; new tasks may be rejected |
| Small pool, flat queue, low latency | Capacity likely matches current load |
| Low active count while queue grows | Tasks may be blocked on another resource, or metrics point to a different executor than actually used |
| Empty queue while active count stays at max | Workers are occupied with long-running tasks or I/O waits |
| Rejections rise while CPU stays low | Queue capacity may be small, tasks are blocking on I/O, or executor is shutting down |

Never judge solely by CPU when deciding to add threads. On I/O-bound workloads, CPU can stay low while every worker is blocked waiting on a database or HTTP call.

## 15. Controlled Tuning Process

When a pool fails to meet throughput or latency targets, tune systematically:

1. **Identify the right executor.** Check which bean is actually injected into the `ExecutorChannel`, poller, or service; avoid tuning the wrong pool.
2. **Measure a baseline.** Record arrival rate, completion rate, task duration, wait time, active count, queue depth, and rejections.
3. **Classify the workload.** Distinguish CPU-bound, I/O-bound, short tasks, and long tasks.
4. **Inspect downstream.** Check database connection pools, HTTP connection limits, broker throughput, and rate limits.
5. **Set core size.** Match baseline concurrency to steady-state traffic.
6. **Set queue capacity.** Bound burst absorption within acceptable latency limits.
7. **Set max size.** Cap concurrency when the queue fills while staying within downstream capacity.
8. **Set rejection policy.** Define whether rejected tasks retry, fail explicitly, apply backpressure, or follow another policy.
9. **Load-test bursts and saturation.** Test ramp-up, ramp-down, and slow downstream scenarios.
10. **Monitor post-deployment.** Confirm queues drain cleanly, rejections do not persist, and latency meets SLAs.

Do not change core, max, and queue simultaneously without measuring. Changing all three at once makes it hard to tell which adjustment helped or caused side effects.

## 16. Pre-Production Checklist for Executors

- [ ] Have you confirmed the exact executor bean used by the endpoint or channel?
- [ ] Does `corePoolSize` match steady-state load and CPU resources?
- [ ] Does `maxPoolSize` bound concurrency safely for downstream systems?
- [ ] Is `queueCapacity` finite and aligned with bursts and latency targets?
- [ ] Do you account for the queue being filled before scaling workers past core?
- [ ] If using an unbounded queue, have you explicitly accepted backlog and heap risks?
- [ ] If `queueCapacity=0`, is `maxPoolSize` finite?
- [ ] Do `keepAliveSeconds` and `allowCoreThreadTimeOut` fit traffic fluctuations?
- [ ] Does the rejection policy preserve message and business semantics?
- [ ] Could `CallerRunsPolicy` block a scheduler, request thread, or lock holder?
- [ ] Can tasks depend on other tasks in the same pool and risk starvation?
- [ ] Can databases, HTTP clients, and brokers sustain the chosen concurrency?
- [ ] Are MDC, tracing, and security contexts propagated safely?
- [ ] Are metrics collected for pool size, active count, queue depth, wait time, and rejections?
- [ ] Does shutdown wait for tasks with a defined timeout and clear ownership?

`corePoolSize`, `maxPoolSize`, and `queueCapacity` form a unified admission and concurrency policy. Core sets baseline workers; queue sets waiting capacity and scaling threshold; max caps workers once the queue fills. Understanding this exact sequence allows you to size pools that absorb bounded bursts, protect downstream systems, and expose saturation before backlog destabilizes the runtime.

## References

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html) — `TaskExecutor` abstraction and core, queue, max, and rejection ordering.
- [Spring Framework — ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html) — default values, `queueCapacity`, `poolSize`, `activeCount`, and runtime management.
- [Java Platform — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html) — worker creation, queuing strategies, and rejection.
- [Spring Integration — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html) — `ExecutorChannel` and thread/transaction boundaries.
- [Spring Integration — Message Endpoints](https://docs.spring.io/spring-integration/reference/endpoint.html) — `TaskExecutor` support for polling endpoints.

Default values and implementation details can vary across Spring Framework, JDK, and Spring Integration versions. Cross-check Javadoc matching your application's exact dependencies and inspect the actual executor bean before applying configurations.
