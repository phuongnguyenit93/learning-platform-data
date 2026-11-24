# Executor Capacity

In Spring Kafka, each listener container needs a consumer task to run the `poll()` loop, manage the Kafka consumer, and invoke the listener. As an application increases `concurrency`, the number of consumer tasks and required threads also rises. If the executor lacks sufficient capacity, some tasks may have to wait in a queue or be rejected. Conversely, spawning too many consumer threads can cause contention over CPU, database connections, and downstream service resources.

**Executor capacity** is the executor's ability to supply enough worker threads for the tasks it manages. In the **Performance and Capacity** chapter, capacity must be calculated across the full topology: replicas, listener endpoints, per-endpoint concurrency, partitions in the consumer group, thread pools, CPU, and dependency limits.

Key point: **configured concurrency, the number of consumers actually assigned partitions, executor thread count, and parallel business processing count are distinct quantities**. Increasing one value does not automatically scale throughput proportionally.

## 1. What Does the Executor Do in Spring Kafka?

With `@KafkaListener`, Spring Kafka creates listener containers to manage Kafka consumers. Each consumer runs inside a long-lived task. The container uses an executor to run consumer tasks; in common Spring Kafka versions, the default executor is `SimpleAsyncTaskExecutor`. Applications can supply a dedicated executor via `ContainerProperties.setListenerTaskExecutor(...)`.

~~~text
KafkaListenerEndpointRegistry
          |
          v
Listener container
          |
          +---- submit consumer task to listenerTaskExecutor
                         |
                         v
                  consumer thread
                         |
                         +---- KafkaConsumer.poll()
                         +---- listener invocation
                         +---- ack / commit handling
                         +---- next poll
~~~

In the standard record listener model, the consumer thread executes polling and invokes the listener. Thus, this thread is not a short-lived worker task submitted per record. It is a long-running task occupying a thread for as long as the container is active.

This makes capacity planning different from an executor used for short tasks such as sending emails or handling HTTP requests. If a pool has six threads yet the application needs to run ten long-lived consumer tasks, six tasks can occupy the entire pool; the remaining tasks must wait or be rejected depending on queue and rejection policy.

## 2. Distinguishing Concurrency, Consumer, Partition, and Thread

| Concept | Meaning |
|---|---|
| Listener endpoint | A Spring-managed `@KafkaListener` method/configuration |
| Container concurrency | Number of child consumer containers created by the endpoint |
| Kafka consumer | A client/member participating in a consumer group |
| Consumer thread | Thread executing the consumer task and listener in standard container mode |
| Partition | Ordered log unit within a Kafka topic |
| Executor thread capacity | Number of tasks the executor can run concurrently |
| Business parallelism | Amount of business work actually processed in parallel |

Example:

~~~java
@KafkaListener(
        id = "orders-listener",
        groupId = "orders-service",
        topics = "orders.events",
        concurrency = "3")
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
~~~

This endpoint requests three child consumer containers. In a standard listener container, each consumer task requires one thread. If the topic has six partitions, three consumers can be assigned partitions according to the assignment strategy. If the topic only has two partitions, at most two consumers in the group receive partitions from that topic; the remaining consumer may still run without any assigned partitions.

**A consumer with no partitions still consumes thread capacity** if its container is running. Therefore, raising concurrency beyond partition count can increase threads without increasing topic parallelism.

## 3. Calculate Total Consumer Tasks Before Choosing Pool Size

Capacity must be calculated at the **application-wide and per-consumer-group** level, not by looking at a single annotation.

Suppose each replica has three listener endpoints:

| Listener | Concurrency per replica |
|---|---:|
| `orders-listener` | 4 |
| `payments-listener` | 2 |
| `audit-listener` | 1 |
| **Total** | **7** |

If four replicas are deployed, the cluster may have roughly 28 consumer instances from these endpoints. However, executors live **inside each JVM**, not shared across Pods. Hence, each replica needs the capacity to run its own seven consumer tasks.

General formula for one process:

\[
T_{\text{required}} = \sum_{i=1}^{N} concurrency_i
\]

Only sum endpoints that actually start and use the executor under consideration. If different factories use separate executors, calculate each pool separately. If one executor is shared across multiple endpoints, sum the concurrency of all those endpoints.

For a consumer group, total members also depend on replicas, listener IDs/group IDs, subscriptions, and any other consumers joining the group. Do not sum all consumers in the application into one group if they actually use different group IDs.

## 4. Partitions Cap Useful Parallelism

Within a consumer group, a partition is assigned to at most one consumer member at a time. For a topic with six partitions:

~~~text
Topic orders.events: 6 partitions

Concurrency = 3:
  consumer-0 -> p0, p1
  consumer-1 -> p2, p3
  consumer-2 -> p4, p5

Concurrency = 6:
  consumer-0 -> p0
  consumer-1 -> p1
  consumer-2 -> p2
  consumer-3 -> p3
  consumer-4 -> p4
  consumer-5 -> p5

Concurrency = 9:
  consumer-0..consumer-5 -> can receive p0..p5
  consumer-6..consumer-8 -> no partition from this topic
~~~

For a single topic, useful consumer parallelism in a group generally cannot exceed partition count. When subscribed to multiple topics, consider total assignable partitions and the assignment strategy.

An approximation can be used:

\[
C_{\text{assigned}} \leq \min(C_{\text{group members}}, P_{\text{subscription}})
\]

This is an assignment bound, not an exact throughput forecast. Partition skew, key distribution, record processing time, and downstream bottlenecks still affect performance.

**Expanding a thread pool without adding partitions or improving the workload does not guarantee higher throughput.** Conversely, adding partitions brings no benefit if the database or CPU is already the bottleneck.

## 5. ListenerTaskExecutor and Dedicated Executors

You can configure an executor for listener containers using `ContainerProperties.setListenerTaskExecutor(...)`. Example using a `ThreadPoolTaskExecutor` with six threads for an endpoint with concurrency six:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class KafkaExecutorConfiguration {

    @Bean
    public AsyncTaskExecutor kafkaListenerExecutor() {
        var executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(6);
        executor.setMaxPoolSize(6);
        executor.setQueueCapacity(0);
        executor.setThreadNamePrefix("kafka-orders-");

        return executor;
    }
}
~~~

Attach to the factory:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        ordersFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory,
                AsyncTaskExecutor kafkaListenerExecutor) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(6);
    factory.getContainerProperties()
            .setListenerTaskExecutor(kafkaListenerExecutor);

    return factory;
}
~~~

In the example:
- `corePoolSize=6` and `maxPoolSize=6` create a fixed pool of six worker threads.
- `queueCapacity=0` requires direct handoff instead of holding consumer tasks in a large queue.
- `threadNamePrefix` helps identify consumer threads in thread dumps and logs.
- Concurrency of six requires six threads of capacity in this pool.

`ThreadPoolTaskExecutor` is managed by Spring as a bean and initializes automatically via lifecycle hooks. There is no need to call `initialize()` manually in standard bean configuration.

### 5.1. Choose queueCapacity Intentionally

`ThreadPoolTaskExecutor` often has a very large default queue capacity. For short tasks, a queue can absorb bursts. Yet consumer tasks are long-lived tasks, each holding a thread for the container's lifetime.

If a pool has six threads, queue capacity 1,000, and the application submits ten consumer tasks, the last four tasks may sit waiting for a very long time. The container may have received the start request while the consumer task has not actually started polling. This creates a gap between **container requested to start** and **consumer actually running**.

A large queue does not increase the number of polling consumers. It merely delays when tasks run.

### 5.2. Rejection Policy

If the pool has no free thread capacity and the queue refuses tasks, the executor can reject the task according to its rejection policy. For consumer containers, rejection is a deployment/configuration error that should surface clearly; do not use a policy that silently drops tasks.

Avoid `DiscardPolicy` or `DiscardOldestPolicy` for long-lived consumer tasks. Dropping a task can leave a listener container without its expected active consumer threads.

`CallerRunsPolicy` also requires caution: it can force the thread submitting the task to run a long-lived consumer loop, unexpectedly blocking lifecycle/startup threads or other threads. Size the pool with enough capacity and let rejections surface rather than masking shortages.

## 6. One Executor Shared Across Multiple Listeners

An application may have several container factories and endpoints. If all share one executor, the pool's capacity must cover **all active consumer tasks** on that executor.

Example per replica:
- `orders-listener`: concurrency 4.
- `payments-listener`: concurrency 3.
- `audit-listener`: concurrency 2.

In total, nine consumer task threads are needed in the process. A six-thread pool is insufficient even though no single endpoint has concurrency above six.

~~~text
Shared listenerTaskExecutor (6 threads)
       |
       +---- orders: 4 tasks
       +---- payments: 3 tasks
       +---- audit: 2 tasks
                    |
                    v
             Total demand = 9
             Capacity = 6
             At least 3 tasks wait/reject
~~~

There are two approaches:

1. **Sufficiently large shared pool:** easy to manage a single capacity budget, though listeners compete for resources.
2. **Separate executors per workload:** isolates resources—for example, giving the payment listener its own pool so the audit listener cannot exhaust payment threads.

A shared pool reuses thread capacity when one listener stops, yet can create noisy-neighbor issues. Separate pools improve isolation, yet can leave threads idle in one pool while another lacks capacity.

### 6.1. Splitting Pools by Criticality

If the payment listener has a stricter SLA than the audit listener, separate executors can be used:

~~~text
paymentListenerExecutor: 4 threads
ordersListenerExecutor:  4 threads
auditListenerExecutor:   2 threads
~~~

This limits cross-workload interference at the executor layer. However, they still share CPU, heap, network, brokers, and possibly the same database pool. Splitting executors does not eliminate shared bottlenecks.

## 7. Do Not Confuse listenerTaskExecutor with the @Async Executor

These two executors serve different purposes:

| Executor | Responsibility |
|---|---|
| `listenerTaskExecutor` | Runs consumer tasks of listener containers |
| `@Async` executor | Runs application methods offloaded via Spring async |
| `applicationTaskExecutor` | May be used by certain Spring Boot/application tasks depending on config |
| Scheduler executor | Runs scheduled jobs |
| Web request executor | Handles web server request threads |

If listener containers and `@Async` share a small pool, consumer loops can monopolize all threads and starve async business tasks. Conversely, an overly large `@Async` pool can contend with consumers over CPU/database resources.

Give each pool distinct names and metrics. Never treat a 20-thread `ThreadPoolTaskExecutor` as "capacity 20 for everything" if it is shared across multiple task types.

## 8. Thread Capacity Does Not Equal Business Parallelism

In a standard container setup, each consumer thread polls and invokes the listener sequentially. When the listener performs blocking I/O, the thread is held while waiting on the database/HTTP call.

Example:
- 4 consumers assigned partitions.
- Each record takes 100ms CPU and 900ms waiting on the database.
- Each consumer processes sequentially one record at a time.

Four consumers can hide part of the wait time by running in parallel across different partitions. Yet if the database allows only two connections and all listeners need a connection at once, the remaining consumers wait on the pool or time out.

Effective capacity is bounded by multiple factors:

\[
C_{\text{effective}} \leq \min(C_{\text{consumer}}, C_{\text{assigned partitions}}, C_{\text{executor}}, C_{\text{downstream}})
\]

`C_downstream` can be DB connection capacity, HTTP concurrency limits, or dependent service limits. CPU-bound workloads are also bounded by core count and CPU time required per record.

This is a conceptual model; systems with batching, asynchronous processing, or multiple dependencies may require a more detailed model.

## 9. Estimating Throughput from Processing Time

A simple calculation for sequential processing per consumer:

\[
Throughput \approx \frac{C_{\text{active}}}{S}
\]

Where:
- `C_active` is the number of consumers actually able to process in parallel with assigned partitions.
- `S` is the average processing time per record, in seconds.

For example, four active consumers, each record averaging 200ms:

\[
Throughput \approx \frac{4}{0.2}=20
\]

Roughly 20 records/second in the simple model, before factoring in overhead, batching, skew, and bottlenecks.

If concurrency increases from four to eight yet the topic only has four partitions, `C_active` may remain four. If the database serves only two concurrent operations efficiently, throughput may not scale according to the ideal formula.

Measure **p50/p95/p99 processing time**, not just average. A few very slow records can cause a consumer to exceed its poll interval and trigger rebalances even when the average remains low.

## 10. CPU-Bound and I/O-Bound Workloads

### 10.1. CPU-Bound

If the listener primarily performs CPU computation:
- Having far more consumer threads than cores can increase context switching.
- GC pressure can rise due to more concurrent records/objects.
- Throughput does not necessarily scale with concurrency.
- Batch processing and algorithmic optimization may beat adding threads.

Start with concurrency aligned to partition count and CPU quota, then measure CPU utilization, throttling, GC pauses, and processing latency.

### 10.2. I/O-Bound

If the listener frequently waits on databases or HTTP:
- Extra threads can help hide wait time.
- However, downstream systems have connection/rate/concurrency limits.
- Too many consumers can exhaust connection pools or trigger retry storms.
- Timeouts and circuit breakers matter more than unbounded thread counts.

Raising concurrency only makes sense if dependencies have capacity to serve concurrent requests.

## 11. Coordinating Consumer Concurrency with Database Pools

Suppose each consumer processes one record at a time and each record needs a DB connection:

~~~text
Kafka consumers: 8
Hikari maximumPoolSize: 4
~~~

At most four consumers can hold DB connections simultaneously; the remaining consumers wait on the pool. If wait times grow long, listener duration increases and can impact `max.poll.interval.ms`.

The DB pool does not always need to equal consumer count, since DB connections may be held briefly or only some records need the DB. Still, measure:
- Hikari active/idle/pending connections.
- Connection acquisition timeouts.
- SQL query latency and lock waits.
- Listener processing p95/p99.
- Consumer lag and rebalances.

A good initial guideline is to bound how many consumers can concurrently enter DB-critical sections to what the database can sustain. If concurrency is higher, use bounded queues/backpressure and finite timeouts.

**Never use unbounded queues in either the executor or the database pool.** When backlogs grow, the system can hold too many records/requests in memory, increasing latency and OOM risk.

## 12. Coordinating with max.poll.interval.ms and max.poll.records

A Kafka consumer must call `poll()` frequently enough. `max.poll.interval.ms` limits the maximum time between polls per consumer config. In standard containers, the listener runs on the consumer thread; if the listener takes too long, the next poll is delayed.

Example:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        max.poll.interval.ms: 300000
        max.poll.records: 100
~~~

If one poll returns 100 records and the container processes sequentially, total batch processing time is roughly:

\[
T_{\text{batch}} \approx \sum_{i=1}^{100} T_{\text{record}_i}
\]

Include deserialization, interceptors, error handling, commits, and overhead. If batch processing exceeds `max.poll.interval.ms`, the consumer may lose group membership and trigger a rebalance.

Executor capacity cannot fix a slow listener. Adding threads to the pool will not make a consumer thread call poll while that very thread is running a synchronous listener.

### 12.1. Async Listener/Offloading Requires Explicit Semantics

Applications can offload business work to another executor or use asynchronous listener return types supported by their Spring Kafka version. Yet when processing asynchronously:
- Do not ack/commit a record before work actually completes if guaranteeing at-least-once delivery.
- Understand the async acknowledgment semantics of your Spring Kafka version.
- Never share `KafkaConsumer` or invoke consumer APIs arbitrarily from worker threads.
- Bound the number of in-flight records.
- Preserve ordering if required by business key/partition.
- Retries and exception handling must cover failures occurring after task offload.
- Shutdown must wait for or cancel in-flight work according to policy.

Offloading is not a free way to raise consumer capacity. It shifts the bottleneck from the consumer thread to another executor and demands careful management of offsets, ordering, memory, and backpressure.

## 13. Bounded Queues and Backpressure

Queues help absorb bursts, yet `listenerTaskExecutor`'s queue is not the right place to park hundreds of consumer tasks waiting for threads. Those tasks are long-lived consumer loops, not short jobs.

For offloaded business work, a bounded queue can cap memory and apply backpressure:

~~~text
Kafka consumer
      |
      v
bounded work queue
      |
      +---- capacity available -> worker executes
      |
      +---- queue full -> reject / pause / controlled retry
~~~

When the queue is full, define a clear policy:
- Temporarily pause the container/partition to stop pulling more records.
- Keep records unacknowledged so redelivery remains possible.
- Reject the task and propagate the failure to appropriate error handling.
- Cap in-flight count and wait duration.

Never silently drop tasks or commit offsets only to discover later that workers did not process them. When using manual acknowledgment or async listeners, verify exact ack semantics.

### 13.1. Queue Latency Is Part of Processing Latency

If records have been polled from Kafka and sit in an application queue, consumer lag by committed offset may not fully reflect time spent waiting in the queue. Measure separately:
- Queue depth.
- Queue wait time.
- In-flight task count.
- Processing duration.
- Age of queued records waiting for processing.
- Offset commit delay.

If queues hold records for a long time, treat that time as part of the end-to-end latency and memory budget.

## 14. Executor Metrics and Observing Capacity

Useful metrics for executors:

| Metric | Meaning |
|---|---|
| Pool size | Current number of threads |
| Active count | Number of threads running tasks |
| Queue size | Number of waiting tasks |
| Remaining queue capacity | Remaining capacity in the queue |
| Task rejection count | Number of rejected task submissions |
| Task execution duration | Task run duration |
| Thread creation rate | Rate of thread creation |
| Consumer start delay | Time from start command until consumer is actually active |

With `ThreadPoolTaskExecutor`, you can observe `getPoolSize()`, `getActiveCount()`, and the underlying executor's queue via appropriate APIs. Micrometer/Spring Boot can instrument certain executor beans depending on config; if creating custom metrics, keep names and tags low-cardinality.

Do not treat `activeCount == poolSize` alone as an error. For long-lived consumer listener tasks, a full pool can be the **expected healthy state**: each consumer holds one thread. Watch for signs that demand exceeds capacity: queued/rejected tasks, consumers failing to start, or worsening processing/lag.

## 15. Kafka Metrics to View Alongside Executor Metrics

Executor metrics alone cannot explain throughput. Combine them:

| Group | Metrics |
|---|---|
| Executor | Pool size, active threads, queue depth, rejections |
| Consumer | Records consumed, poll rate, poll duration, assignments |
| Kafka group | Lag per partition, rebalance count/duration |
| Listener | Processing p50/p95/p99, error/retry rates |
| Producer | Send rate, request latency, error/retry rates |
| Database | Active/pending connections, acquisition latency, query latency |
| JVM | CPU, thread count, heap, GC pauses, CPU throttling |
| Application queue | Depth, wait time, in-flight work |

Interpretation examples:
- Pool active count is sufficient, yet consumer lag rises and DB pool pending is high: downstream DB may be the bottleneck.
- Pool queue grows and some consumers are not polling: executor capacity is insufficient for container tasks.
- Pool active count is low, consumers have assignments, yet throughput is low: check listener logic, polling, pause state, or dependencies.
- Consumer lag is low while the application work queue grows: backlog has shifted from Kafka into memory queues.
- CPU throttling and processing p99 rise: adding threads may make things worse.

## 16. Layered Capacity Planning

A practical workflow:

1. Count listener endpoints started per replica.
2. Sum each endpoint's concurrency to get consumer tasks per JVM.
3. Identify which executor manages each endpoint and sum demand per pool.
4. Compare consumer group member count against subscription partitions.
5. Determine whether processing is CPU-bound or I/O-bound.
6. Identify DB connection limits, HTTP downstream concurrency, and producer throughput.
7. Choose pool sizes and bounded queue policies.
8. Run representative load tests and measure p95/p99, lag, rebalances, queue depth, CPU, and DB waits.
9. Scale concurrency or pool size step by step without changing every variable at once.
10. Size capacity with appropriate headroom for rebalances, rollouts, and bursts.

Example for one replica:

~~~text
orders-listener:       concurrency 4
payments-listener:     concurrency 2
audit-listener:        concurrency 1
-------------------------------------
consumer tasks:        7

shared listener pool:  7 threads
database pool:          5 connections
CPU quota:              4 cores
topic partitions:
  orders:               8
  payments:             4
  audit:                2
~~~

A seven-thread pool can run seven consumer tasks, yet a five-connection DB pool limits concurrent DB-dependent sections. A four-core CPU quota can constrain CPU-bound workloads. Partition counts do not form a single combined sum if the three listeners use different group IDs; analyze assignments separately for each group.

## 17. Thread Naming and Thread Dumps

Setting a distinct thread name prefix helps identify consumer tasks:

~~~java
executor.setThreadNamePrefix("kafka-orders-");
~~~

In thread dumps, threads can appear as `kafka-orders-1`, `kafka-orders-2`, depending on the executor. During investigation:
- Thread `RUNNABLE` with high CPU usage: possibly CPU-bound.
- Thread waiting on JDBC connection: inspect pool and database.
- Thread waiting on HTTP response: inspect downstream timeouts.
- Multiple consumer threads waiting on a shared lock: locate contention.
- Consumer tasks uncreated/sitting in executor queue: inspect pool capacity and rejections.
- Consumer thread blocked inside listener: cross-check `max.poll.interval.ms` and rebalances.

A thread state is point-in-time evidence. Capture multiple thread dumps spaced shortly apart to distinguish normal waiting from a thread stuck long-term.

## 18. Executor Lifecycle and Shutdown

Consumer tasks are long-lived tasks. When the application shuts down:

1. Spring requests listener containers to stop.
2. Consumer threads exit their loops and close `KafkaConsumer` via container mechanics.
3. The executor shuts down according to the Spring bean lifecycle.
4. Other resources close in appropriate order.

If the executor shuts down before containers finish stopping, listener tasks may be interrupted/rejected or shut down unexpectedly. Let Spring manage lifecycle beans and check the shutdown ordering of custom executors.

Do not blindly enable `waitForTasksToCompleteOnShutdown` on pools hosting consumer loops: these tasks only finish when the container stop signal is processed. If the executor waits for tasks to finish before the container is stopped, shutdown can hang or drag out.

Coordinate:
- Spring lifecycle phase timeouts.
- Kafka container shutdown timeouts.
- Kubernetes `terminationGracePeriodSeconds`.
- Dependency request timeouts.
- In-flight business task policies if async offloading is used.

When a process receives `SIGKILL`, cleanup is not guaranteed. Uncommitted offsets may redeliver, so business side effects require idempotency.

## 19. Common Mistakes

- **Pool smaller than total consumer concurrency:** some consumer tasks must wait or get rejected.
- **Calculating capacity per listener while ignoring endpoints sharing an executor:** total demand exceeds the pool.
- **Confusing pool size with partitioned consumers:** idle consumers still hold threads.
- **Raising concurrency beyond partition count:** adds threads without adding useful parallelism.
- **Using an unbounded queue for long-lived consumer tasks:** container startup is delayed and queues mask capacity shortages.
- **Using DiscardPolicy:** consumer tasks can be dropped without clear signals.
- **Sharing a small pool between `listenerTaskExecutor` and `@Async`:** consumer loops starve async work.
- **Treating `activeCount == poolSize` as an error:** for long-lived consumer tasks, that can be normal.
- **Adding threads to fix a DB bottleneck:** creates more connection waits and database load.
- **Ignoring `max.poll.interval.ms`:** slow listener processing causes consumers to lose group membership.
- **Offloading records and acking early:** can commit offsets before business work finishes.
- **Using `KafkaConsumer` from worker threads:** violates thread-safety/ownership rules.
- **Not measuring application queues:** Kafka lag may appear low while work piles up in memory queues.
- **Forgetting to compute capacity per replica:** JVM pools are not shared across Pods.
- **Shutting down executors out of order:** consumer tasks lose the chance for graceful stop.
- **Measuring only average latency:** tail latency can trigger poll interval and rebalance issues.

## 20. Integration Tests for Executor Capacity

Use Kafka Testcontainers or Embedded Kafka to verify container tasks actually run on the configured executor.

Scenarios:
1. **Pool with sufficient capacity:** concurrency equals pool size; verify all consumer tasks start.
2. **Pool lacking capacity:** concurrency exceeds pool; observe task queuing/rejection and consumer start delays.
3. **Multiple endpoints sharing a pool:** total concurrency exceeds capacity; confirm behavior is understood and monitored.
4. **Partition count lower than concurrency:** confirm unassigned consumers still occupy threads.
5. **Consumer group rebalance:** thread tasks remain healthy and assignments shift properly.
6. **Slow listener processing:** verify poll interval and rebalance behavior.
7. **Small downstream DB pool:** measure pending connections and listener latency under load.
8. **Pause/resume:** container preserves lifecycle properly and drains backlog after resuming.
9. **Shutdown:** stop containers before the executor terminates; verify consumer resources close.
10. **Thread leaks:** start/stop/restart containers repeatedly; verify thread count returns to expected levels.

### 20.1. Verifying Thread Names and Consumer Start

You can inject a custom executor, start a listener with small concurrency, and use a latch inside the listener/test observer to confirm consumer tasks run. Thread name prefixes help verify thread names if the test harness inspects them.

Do not merely assert `container.isRunning()` and conclude the consumer task is polling or assigned partitions. Verify separately:
- Container lifecycle state.
- Consumer start/assignment callbacks or group metadata.
- Thread count/active pool.
- Actual records received by the listener.

### 20.2. Controlled Rejection Tests

If intentionally configuring a pool short on thread capacity, the test must:
- Use a dedicated executor for the test.
- Bound wait times.
- Capture rejection/start failures.
- Clean up containers and executors within the test lifecycle.
- Avoid queuing consumer tasks indefinitely and hanging the suite.

The goal is to prove capacity mismatches are observable and handled, not to build a flaky timing-dependent test.

## 21. Workflow for Investigating Executor Saturation

When consumer lag rises or a listener fails to start, inspect in order:

1. Identify listener endpoint, group ID, and expected concurrency.
2. Count container/consumer tasks on the process.
3. Identify the executor attached to each factory.
4. Compare demand against pool size, active count, queue depth, and rejections.
5. Verify consumers actually have running threads and are polling.
6. Inspect partitions/assignments in the group.
7. Measure listener processing duration and tail latency.
8. Correlate DB/HTTP connection pools, CPU, and JVM thread dumps.
9. Check `max.poll.interval.ms`, `max.poll.records`, and retry/backoff settings.
10. Scale capacity or adjust queues/concurrency incrementally, then monitor lag and downstream health.

If the pool is full while all consumer threads are running normally, do not enlarge the pool merely because active count hits the maximum. Look for signs of blocked demand: queuing/rejections, unstarted consumers, slow processing, or downstream saturation.

## 22. Production Checklist

Before deploying or changing executor capacity:
- Did you sum concurrency across all listener endpoints per replica?
- Did you identify which endpoints share `listenerTaskExecutor`?
- Is the pool size sufficient for all long-lived consumer tasks?
- Is queue capacity bounded and intentional?
- Does the rejection policy surface failures instead of silently dropping tasks?
- Does concurrency fit partition counts and group topology?
- Are consumer threads sitting idle because concurrency exceeds partition count?
- Have CPU-bound vs. I/O-bound characteristics been measured?
- Do downstream DB/HTTP systems have capacity for planned concurrency?
- Does listener p95/p99 stay within `max.poll.interval.ms` limits?
- Does `max.poll.records` make batch processing too long?
- Is the listener task pool shared with `@Async` or schedulers?
- If offloading business work, are bounded queues, backpressure, and ack semantics explicit?
- Do metrics cover pool size, active count, queue depth, rejections, and consumer lag?
- Do thread names help pinpoint the right listener in thread dumps?
- Does shutdown order stop containers before closing executors?
- Have you tested sufficient/insufficient pool capacity, rebalances, and graceful shutdown?

**Executor capacity** is one pillar of capacity planning for Spring Kafka: each consumer task needs a thread to poll and run the listener, yet thread count is only one constraint among many. Calculate total demand from replicas and concurrency, check partition assignments, configure executors with explicit queue/rejection policies, and align with CPU and downstream pools. Expanding a thread pool only helps when the executor is truly the bottleneck; if the limit lies in partitions, databases, listener processing, or `max.poll.interval.ms`, adding threads can consume more resources without increasing throughput.

