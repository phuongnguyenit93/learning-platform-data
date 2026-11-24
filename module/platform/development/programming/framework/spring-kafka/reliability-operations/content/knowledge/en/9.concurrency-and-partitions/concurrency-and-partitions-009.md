# Executor Thread Starvation Preventing Consumers from Starting

In Spring Kafka, each Kafka consumer needs a thread to run its `poll()` loop, receive records, invoke the listener, and coordinate offset commits. The listener container creates and runs consumer tasks through an `AsyncTaskExecutor`. If the application attaches an executor with too low a thread limit, shares an already busy executor, or configures a queue that causes consumer tasks to stall, some consumers may fail to start running.

This issue commonly appears after increasing `concurrency`, adding new listeners, or sharing one `ThreadPoolTaskExecutor` across multiple background workloads. The container may have been asked to start, yet consumer tasks remain queued or get rejected by the executor. As a result, the application does not receive records as expected even though the topic has data.

## 1. Why Does a Consumer Need Its Own Thread?

A Kafka consumer is not an object that can be called arbitrarily from multiple threads concurrently. Spring Kafka manages the consumer inside the listener container and executes consumer operations on container-coordinated threads. This thread runs the poll loop, processes records or batches, coordinates rebalances, and commits offsets.

With `ConcurrentMessageListenerContainer`, the `concurrency` property creates multiple child containers/consumers for parallel processing. Each consumer task needs a thread running continuously for the entire lifetime of the active container.

Example:

```java
@KafkaListener(
        id = "orders-listener",
        topics = "orders",
        groupId = "order-projection",
        concurrency = "4")
public void handle(OrderEvent event) {
    orderProjectionService.apply(event);
}
```

This listener requires four consumers in the same listener container. If the listener executor can run at most two consumer tasks concurrently, at most two consumers can enter the poll loop; the other two tasks must wait or are rejected depending on executor policy. Active consumers normally hold their threads to keep polling, so waiting tasks do not automatically get a turn just because a single record finished processing.

Kafka can assign partitions to active consumers. If consumer count exceeds partition count, some consumers will receive no partitions and sit idle, yet their consumer tasks still need threads to join the group and maintain their lifecycle. Therefore, required thread count does not depend solely on how many partitions currently have work.

## 2. Where Does the Listener Task Executor Operate?

Spring Kafka allows configuring the executor that runs listener containers via `ContainerProperties.setListenerTaskExecutor(...)`. This executor runs the container's consumer tasks. It is distinct from any executor business code uses to run asynchronous tasks inside the listener.

```text
ApplicationContext
       |
       v
KafkaListenerEndpointRegistry
       |
       v
Listener container (concurrency = N)
       |
       +---- consumer task 1 ----> listener thread 1 ----> poll()
       +---- consumer task 2 ----> listener thread 2 ----> poll()
       +---- consumer task 3 ----> listener thread 3 ----> poll()
       |
       v
Listener code can call a separate business executor if needed
```

`listenerTaskExecutor` must have enough capacity to run all required consumer tasks. If the listener calls `@Async` or submits work to another executor, that is an additional execution layer with its own thread demand. Do not confuse a listener task having started with an asynchronous business task having completed.

When no custom executor is configured, Spring Kafka uses the container's default executor according to the framework version. When the application replaces it with a shared thread pool, that pool's `corePoolSize`, `maxPoolSize`, queue capacity, and rejection policy directly govern whether consumers can start.

## 3. How a Thread Pool Causes Consumer Tasks to Stall

### Pool Smaller Than Total Concurrency

Suppose an application has three listeners:

| Listener | Concurrency |
|---|---:|
| `orders-listener` | 4 |
| `payments-listener` | 3 |
| `inventory-listener` | 2 |
| **Total** | **9** |

If all three listeners share an executor limited to four concurrent threads, the remaining five consumer tasks cannot enter the poll loop. Because the four running tasks are long-lived, they keep holding their threads. The queue may stay backed up indefinitely or the executor rejects tasks once the queue fills.

### Large Queue Hiding Thread Starvation

`ThreadPoolExecutor` normally prioritizes core threads, then enqueues tasks; only when the queue is full does it expand up to `maxPoolSize`. With an unbounded queue, setting `maxPoolSize` higher than `corePoolSize` may fail to grow thread count under normal conditions.

For example, a pool with `corePoolSize=2`, `maxPoolSize=12`, and an unbounded queue. Once the first two consumer tasks start, subsequent tasks are placed into the queue. Because the first two consumers keep holding their threads inside the poll loop, the queue never fills and the pool never scales up to 12 threads. The remaining consumers wait indefinitely.

### Shared Executor Already Exhausted

An executor might already be running other tasks such as sending emails, calling APIs, processing files, or `@Async` jobs. If those tasks hold threads for long durations, new consumer tasks have no threads left to start. Sharing a pool couples Kafka availability to unrelated workloads.

### Rejection Policy Rejecting Tasks

When the pool reaches its thread limit and the queue is also full, the executor can throw `TaskRejectedException` or `RejectedExecutionException`. Depending on the call site and Spring Kafka version, the error may surface during container startup or appear in logs when consumer tasks are submitted. Search logs for the root exception rather than relying solely on `isRunning()`.

## 4. Calculating Required Thread Count

For an executor shared across multiple listener containers, sum the concurrency of all containers using that executor.

```text
requiredConsumerThreads = sum(concurrency of each listener container)
```

Example:

```text
orders-listener       concurrency = 4
payments-listener     concurrency = 3
inventory-listener    concurrency = 2
--------------------------------------
Total concurrent consumer tasks needed = 9
```

The pool needs at least nine threads capable of running concurrently so every consumer task across the three listeners can operate. If the executor also runs other workloads, add their demand or isolate pools so consumers do not contend for threads.

| Component | How to account for it |
|---|---|
| One listener with `concurrency=N` | Budget N consumer tasks |
| Multiple listeners sharing an executor | Sum concurrency across all those listeners |
| Container spawning multiple consumers | Count every child consumer, including those potentially idle due to fewer partitions |
| Business tasks running on another executor | Size the business pool separately; do not double-count into listener task executor if pools are separate |
| Background tasks sharing the executor | Budget additional threads or isolate from the Kafka pool |

This is the minimum concurrency requirement, not the final sizing for the whole application. Reserve resources for the JVM, HTTP server, schedulers, database pools, and management threads. Never allocate all process threads exclusively to Kafka consumers.

## 5. Configuring a Dedicated ThreadPoolTaskExecutor for Kafka

A controllable approach is creating a dedicated `ThreadPoolTaskExecutor` for running listener containers. The example below budgets up to six concurrent consumer tasks:

```java
@Configuration
public class KafkaListenerExecutorConfiguration {

    @Bean
    public ThreadPoolTaskExecutor kafkaListenerExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(6);
        executor.setMaxPoolSize(6);
        executor.setQueueCapacity(0);
        executor.setThreadNamePrefix("kafka-listener-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        return executor;
    }
}
```

With `queueCapacity=0`, tasks are not parked in a large queue waiting indefinitely; the pool must have a thread ready to run the task. Since `corePoolSize` and `maxPoolSize` are both six, this configuration provides up to six consumer threads. Total concurrency of listeners using this pool must not exceed six if all consumer tasks are expected to run simultaneously.

Attach the executor to the container factory:

```java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            ThreadPoolTaskExecutor kafkaListenerExecutor) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(4);
        factory.getContainerProperties()
                .setListenerTaskExecutor(kafkaListenerExecutor);
        return factory;
    }
}
```

In this example, the orders listener factory creates four consumer tasks and uses a six-thread pool. If this factory is used by additional listeners or another factory references the same executor, sum the concurrency of all those listeners before sizing the pool.

`ThreadPoolTaskExecutor` has its lifecycle managed by Spring when declared as a `@Bean`; calling `initialize()` manually is unnecessary in typical cases. With `queueCapacity=0`, submitting more tasks than `maxPoolSize` causes the executor to reject tasks. Therefore, configuration must stay aligned with actual concurrency and scaling plans.

## 6. Understanding corePoolSize, maxPoolSize, and queueCapacity

These three properties govern how the pool reacts when new tasks arrive:

| Property | Meaning | Risk if misconfigured |
|---|---|---|
| `corePoolSize` | Core threads retained per pool policy | Too small can leave consumer tasks queued if the queue accepts tasks before pool expansion |
| `maxPoolSize` | Maximum threads the pool can create | Raising max does nothing if an unbounded queue absorbs every task |
| `queueCapacity` | Number of tasks that can wait in the queue | Overly large queue hides thread starvation; full queue triggers rejections |

With `ThreadPoolTaskExecutor`, a positive queue capacity creates a bounded queue; negative or very large queue capacities depending on configuration can produce a virtually unbounded queue. A queue capacity of zero uses direct handoff, allowing the pool to scale threads up to `maxPoolSize` before rejecting tasks.

For consumer tasks, queuing does not solve sustained thread shortages. Consumer tasks are long-lived tasks, not short jobs finishing in milliseconds. If a pool can only run four consumer tasks, those four hold threads for as long as the listener runs; a fifth task cannot wait for a thread to become "free" from the first four like a normal short-lived task.

A predictable configuration sets `corePoolSize` equal to the number of concurrent consumer tasks needed, `maxPoolSize` equal or higher per scaling plans, and a small or zero queue capacity. If using a queue, understand clearly how it affects pool expansion and task waiting.

## 7. Do Not Share Pools Uncontrolledly

A shared executor reduces the number of pools in the application, yet forces workloads to compete for threads. A hung HTTP call or long file-processing batch can occupy threads needed for Kafka consumers to keep polling.

Another dangerous scenario is when the listener task executor and the business processing executor share one small pool. Consumer threads receive records, submit work to that same pool, and block on `Future.get()`. If all threads are running consumer tasks waiting for work sitting in that same pool's queue, business tasks never get a thread to execute. This is thread starvation or deadlock caused by executor design.

Anti-pattern example:

```text
Pool with 4 threads
  thread 1: consumer task -> waiting on Future from pool
  thread 2: consumer task -> waiting on Future from pool
  thread 3: consumer task -> waiting on Future from pool
  thread 4: consumer task -> waiting on Future from pool

Queue:
  business task A
  business task B
  business task C
  business task D

No threads remain to run queued business tasks.
```

Separate executors by role:

```text
kafkaListenerExecutor
  -> runs poll loop and listener container

businessExecutor
  -> runs async work submitted by listener

httpExecutor / scheduler
  -> handles HTTP clients or scheduled tasks
```

If the listener runs synchronously, the consumer thread can execute business logic directly. If the listener hands work to another executor, manage acknowledgments, exceptions, and in-flight task limits. Separating pools does not automatically prevent premature offset commits; the listener must still acknowledge only after business effects complete.

## 8. Concurrency Must Align with Partitions and Resources

`concurrency` determines how many consumers the container creates. Having more consumers than partitions in a consumer group does not increase the number of partitions processed in parallel; excess consumers receive no partitions. Even so, those consumers still require threads and resources to run.

Example of a topic with three partitions:

| Concurrency | Consumers able to receive partitions | Consequence |
|---:|---:|---|
| 1 | 1 consumer receives all three partitions | Fewer threads, less parallelism |
| 3 | 3 consumers can receive one partition each | Exploits partition-level parallelism |
| 6 | At most 3 consumers receive partitions; rest idle | Uses extra threads without increasing parallelism for this topic |

When multiple listeners consume different topics, total consumer tasks can exceed the partition count of any single topic. Calculate per listener container and sum them if sharing an executor.

Do not increase concurrency to fix consumer lag when the executor lacks enough threads. Increasing concurrency raises demand for threads, sockets, memory, broker connections, and can increase pressure on databases or backing services. Without more partitions, extra consumers may not improve throughput.

## 9. Distinguishing Thread Starvation from Other Kafka Failures

A consumer failing to process records can have several causes. Determine whether consumer tasks are running at all before changing broker or offset settings.

| Symptom | Likely cause | What to check next |
|---|---|---|
| No `kafka-listener-*` threads and tasks are queued | Executor not allocating threads or not wired properly | Pool active count, queue size, factory configuration |
| `TaskRejectedException` or `RejectedExecutionException` at startup | Pool reached limits and rejected tasks | `maxPoolSize`, queue capacity, total concurrency |
| Only some consumers start when concurrency is high | Pool lacks enough threads for all consumer tasks | Sum concurrency across all containers sharing the pool |
| Consumers started but hold no partitions | Rebalance, group membership, or partition assignment incomplete | Consumer events, group state, topic partition count |
| Consumers polling but listener processes slowly | Slow business logic, I/O, or blocked threads | Listener duration, thread dumps, dependency latency |
| Consumers leave group during long processing | Exceeded `max.poll.interval.ms` or lost heartbeats | Poll interval, record processing, rebalance logs |
| Pool has threads but no records arrive | Empty topic, offsets at end, wrong group, or different partitions | Topic data, group ID, committed offsets, assignments |

In particular, thread starvation before a consumer runs differs from a running consumer processing slowly. `max.poll.interval.ms` applies to time between polls while a consumer is active; it does not grant extra threads to a consumer task stuck in an executor queue.

## 10. Diagnostic Workflow

### Step 1: Calculate Needed Consumer Tasks

List all `@KafkaListener`s, each listener's `concurrency`, and which factories/containers share an executor. Sum concurrency to get minimum thread demand.

```text
orders-listener       4
payments-listener     3
inventory-listener    2
--------------------------------
Total                   9 consumer tasks
```

Check concurrency configured on annotations, factories, and runtime config. If a listener uses default concurrency, record the effective value provided by its factory.

### Step 2: Check the Executor Attached to the Container

Locate where `ConcurrentKafkaListenerContainerFactory` is constructed or `ContainerProperties` is configured. Confirm the intended executor is passed to `setListenerTaskExecutor(...)`. Check whether multiple factories share the same bean.

Do not assume `spring.task.execution.pool.*` automatically configures the listener executor. Those properties affect Spring Boot's auto-configured task executor; listener containers only use that pool if the application or specific auto-configuration wires it to the factory.

### Step 3: Observe Thread Counts and Queue Size

With `ThreadPoolTaskExecutor`, observe metrics such as pool size, active count, queue size, and completed task count. These metrics distinguish an under-threaded pool, a saturated pool, and queued tasks.

Example reading metrics from the bean:

```java
@Component
public class KafkaExecutorMetrics {

    private final ThreadPoolTaskExecutor kafkaListenerExecutor;

    public KafkaExecutorMetrics(ThreadPoolTaskExecutor kafkaListenerExecutor) {
        this.kafkaListenerExecutor = kafkaListenerExecutor;
    }

    public void logState() {
        ThreadPoolExecutor executor =
                kafkaListenerExecutor.getThreadPoolExecutor();

        log.info("Kafka executor: poolSize={}, active={}, queued={}, completed={}",
                executor.getPoolSize(),
                executor.getActiveCount(),
                executor.getQueue().size(),
                executor.getCompletedTaskCount());
    }
}
```

In production applications, export these values to Micrometer or your metrics backend instead of logging only. Avoid calling `getThreadPoolExecutor()` before the executor is initialized; guard against an unready bean if metrics are scraped very early.

### Step 4: Inspect Thread Dumps

A thread dump shows whether threads are running consumer loops, waiting in a queue, or blocked in a dependency. Search for the configured thread prefix, such as `kafka-listener-`. If active threads stay pinned at the pool limit while queue size grows, the executor may be saturated.

If consumer threads are waiting on `Future.get()` while business tasks sit queued in the same pool, check for shared-pool starvation. If threads are blocked on JDBC or HTTP, that is a processing/dependency latency problem; check timeouts and business pool capacity rather than blindly raising Kafka threads.

### Step 5: Verify the Consumer Group

Once certain that consumer tasks are running, verify group state and partition assignments. You can use the Kafka CLI:

```bash
kafka-consumer-groups.sh \\
  --bootstrap-server kafka.example:9092 \\
  --describe \\
  --group order-projection
```

If the group has no members, consumers may not have joined the group yet or connection/authentication failed. If the group has members without expected assignments, check topic partitions, subscriptions, rebalances, and group config. This command is part of Kafka diagnostics; it does not replace checking executors inside the JVM.

## 11. Remediation Options

### Size the Pool to Total Concurrency

Ensure the pool has enough threads to run all concurrent consumer tasks simultaneously. If concurrency increases from four to eight, update executor sizing at the same time.

### Separate the Kafka Pool from Background Work

Create a dedicated executor for listener containers so email, HTTP, or scheduled tasks cannot consume threads needed by consumers. Separating pools also clarifies metrics and alerting.

### Adjust Queue Capacity

Do not use a large queue to hide thread shortages. Consumer tasks are long-lived, so queuing merely delays when consumers join the group. Consider a small or zero queue alongside an appropriate `maxPoolSize`, while ensuring total concurrency does not exceed the pool's concurrent execution capacity.

### Reduce Concurrency When Resources Are Constrained

If an instance is allocated limited CPU or threads, lower `concurrency` to what the executor and dependencies can support. You can add partitions or replicas after measuring throughput, rather than adding consumers without accounting for thread cost.

### Avoid Pool Starvation from Same-Pool Waiting

Do not let consumer tasks occupy all threads and then wait on business tasks submitted to the same pool. Isolate executors or design non-blocking async processing; if using async acknowledgments, control in-flight task counts and error handling explicitly.

### Handle Rejections Explicitly

If the executor rejects tasks, log the exception with the listener/container name and pool state. Do not use `CallerRunsPolicy` arbitrarily for consumer tasks: the calling thread submitting the task could be forced to run a long-lived consumer loop, altering lifecycle flow or blocking management threads. Choose a rejection policy only after understanding exactly which thread submits tasks and how the container handles errors.

## 12. Integration with Spring Boot

Spring Boot can auto-configure an executor for certain application background tasks. However, do not assume `spring.task.execution` always governs Spring Kafka consumer threads. Listener containers use the executor configured on `ContainerProperties`; to use a specific executor bean, wire that bean into the listener container factory.

Example with explicit bean naming and direct wiring:

```java
@Bean("kafkaListenerExecutor")
ThreadPoolTaskExecutor kafkaListenerExecutor() {
    var executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(8);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(0);
    executor.setThreadNamePrefix("kafka-consumer-");
    return executor;
}

@Bean
ConcurrentKafkaListenerContainerFactory<String, PaymentEvent>
paymentListenerFactory(
        ConsumerFactory<String, PaymentEvent> consumerFactory,
        @Qualifier("kafkaListenerExecutor") ThreadPoolTaskExecutor executor) {

    var factory = new ConcurrentKafkaListenerContainerFactory<String, PaymentEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(5);
    factory.getContainerProperties().setListenerTaskExecutor(executor);
    return factory;
}
```

In this example, the pool has eight threads and the factory creates five consumer tasks. If another factory also uses this bean, add that factory's concurrency to the total demand. Using `@Qualifier` prevents injecting the wrong executor when the application defines multiple `TaskExecutor` beans.

APIs and ways to customize the auto-configured factory vary across Spring Boot/Spring Kafka versions. If retaining the Boot-created factory, customize it through your version's customizer/configurer mechanism; what matters is that the listener container ultimately receives the intended executor.

## 13. Shutdown and Executor Lifecycle

Listener consumer tasks typically run continuously until the container stops. Therefore, shutdown order must ensure containers get a chance to stop and finish consumer tasks before the executor closes. If the executor shuts down too early, the container may fail to submit tasks or active consumer tasks may not be managed cleanly.

When using a dedicated executor bean, let Spring manage its lifecycle and coordinate stop order with listener containers. Configuring `setWaitForTasksToCompleteOnShutdown(true)` and `setAwaitTerminationSeconds(...)` helps the executor, though it does not replace properly invoking container lifecycle stop. Wait times must fit within the graceful shutdown budget of the application and deployment platform.

If the process is killed before consumers stop and commit offsets, uncommitted records can be redelivered. This is why listeners must be idempotent for side effects outside Kafka. Do not attempt to hold consumer threads indefinitely during executor shutdown; establish explicit timeouts and stop procedures.

## 14. Runbook When Consumers Fail to Start After Increasing Concurrency

Suppose `orders-listener` previously ran with concurrency 2 and a two-thread executor. After raising concurrency to 6, only two consumers become active. Follow this sequence:

1. Confirm effective concurrency is now six and identify which listener factory is used.
2. Check whether `ContainerProperties.listenerTaskExecutor` points to the two-thread pool.
3. Inspect pool size, active count, queue size, and rejection exceptions.
4. Check whether other listener containers or background tasks share the pool.
5. Expand or separate the executor to provide at least six threads for this listener, plus demand from any sharing containers.
6. Restart the container following proper lifecycle procedures; do not merely raise queue capacity.
7. Verify all expected consumer tasks are running, the consumer group has members, and partition assignments are healthy.
8. Monitor consumer lag, listener duration, thread utilization, and database load after the change.

If enough threads exist yet consumers still do not join the group, shift to checking broker connectivity, authentication, topic subscriptions, group ID, and rebalances. Do not keep enlarging the pool when evidence points to Kafka connectivity or configuration errors.

## 15. Design Principles

| Principle | Reason |
|---|---|
| Sum concurrency across all containers sharing an executor | Every consumer task needs a thread for its poll loop |
| Dedicate a separate executor for listeners in complex workloads | Prevents background tasks from starving Kafka threads |
| Do not let large queues mask thread shortages | Consumer tasks are long-lived and can wait indefinitely |
| Align pool size with concurrency and resource limits | Avoids rejections or excessive thread consumption |
| Monitor active threads, queues, and rejections | Detects starvation early before consumer lag climbs |
| Separate listener executor from business executor | Avoids deadlocks when consumer tasks wait on same-pool work |
| Stop containers before closing the executor | Ensures consumer tasks terminate cleanly under lifecycle control |

When an executor lacks threads, consumer tasks cannot enter their `poll()` loop and do not participate in partition processing as expected. Calculate consumer task counts from actual concurrency, ensure the listener executor has enough concurrent threads, isolate pools from competing workloads, and monitor queues/rejections. When execution capacity is sufficient yet consumers still fail to start, inspect container state, Kafka connectivity, and consumer group state to pinpoint the failing layer.
