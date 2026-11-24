# Choosing Concurrency Based on Processing Speed

When a Spring Kafka application needs to consume more events, increasing the number of consumers running in parallel can help raise throughput. Spring Kafka provides the `concurrency` property on the listener container to create multiple consumers in the same consumer group. However, increasing concurrency only helps when the topic has enough partitions and downstream systems still have capacity to handle additional load.

Choosing the right concurrency must be based on measured processing speed, partition count, allowable latency, and the capacity of dependent services. Setting it too low leaves partitions underutilized; setting it too high creates extra consumers and processing threads without increasing the number of partitions that can be consumed in parallel.

## 1. How Does `concurrency` Work in Spring Kafka?

A standard `KafkaMessageListenerContainer` manages a single Kafka consumer. When configured with concurrency greater than one, Spring Kafka's `ConcurrentMessageListenerContainer` manages multiple child containers; each child container has its own consumer and execution thread. These consumers join the listener's consumer group and receive partitions via Kafka's assignment mechanism.

For example, configuring concurrency to 3 creates up to three consumers for the listener container on each application instance:

```java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, Order> orderListenerFactory(
            ConsumerFactory<String, Order> consumerFactory) {

        ConcurrentKafkaListenerContainerFactory<String, Order> factory =
                new ConcurrentKafkaListenerContainerFactory<>();
        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);
        return factory;
    }
}
```

Listener using the factory above:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "orderListenerFactory")
public void handleOrder(Order order) {
    orderService.process(order);
}
```

If using the default factory auto-configured by Spring Boot, you can set the default concurrency via properties:

```yaml
spring:
  kafka:
    consumer:
      group-id: order-service
    listener:
      concurrency: 3
```

When creating a custom factory as in the Java example, set `factory.setConcurrency(...)` directly on that factory. `concurrency` is the number of consumers for a listener container on a single application instance; if running multiple instances, the total number of consumers in the group also depends on the number of instances and each instance's concurrency.

Spring Kafka creates a separate consumer for each child container. Do not share a single `KafkaConsumer` object across multiple threads because Kafka consumer is not thread-safe. However, child containers can invoke the same listener method on the same Spring bean; if the bean holds mutable state, it must be designed to be thread-safe or state must be isolated per execution.

## 2. Partition Count Caps Parallelism

Within a consumer group, at any point in time, each partition is assigned to at most one consumer. Therefore, for a subscription with a total of `P` partitions, the number of consumers actually receiving data concurrently cannot exceed `P`:

\[
C_{active} \leq \min(C_{total}, P)
\]

Where:

- `C_total` is the total number of consumers belonging to the group and subscribing to that subscription, counted across all instances and listener containers using the same group.
- `P` is the total number of partitions of the topics the group subscribes to.
- `C_active` is the number of consumers assigned at least one partition.

For example, topic `orders` has 6 partitions:

| Total consumers in group | Consumers that can receive partitions | Result |
|---:|---:|---|
| 2 | 2 | Each consumer can receive multiple partitions. |
| 4 | 4 | All four consumers can be active. |
| 6 | 6 | Can exploit parallelism across all six partitions. |
| 8 | At most 6 | At least two consumers are unassigned and do not increase throughput. |

The upper limit applies to total consumers in the group, not just a single process. For instance, three application instances, each with concurrency set to 2, create a total of up to 6 consumers in the group. If the group has 4 partitions, at most 4 consumers can receive data at a time.

If a listener subscribes to multiple topics, count the total number of partitions in the subscription. If different listeners use the same `group.id` and the same subscription, their consumers also participate in partition distribution within that group. Therefore, calculations must consider all group members, not just a single `@KafkaListener` annotation.

Kafka guarantees ordering within a single partition. Records with the same key are typically routed to the same partition, allowing per-key processing order to be preserved when the listener processes sequentially. Increasing the partition count can change how keys map to partitions for new records; if business logic depends strictly on per-key ordering, evaluate this impact before expanding partitions.

## 3. Estimating Concurrency from Processing Speed

Measure the sustainable processing capacity of a single consumer using data close to the real environment. If a consumer processes one record sequentially in `T_record` seconds on average, its approximate theoretical capacity is:

\[
R_{consumer} \approx \frac{1}{T_{record}}
\]

With a target throughput `R_target`, the initial estimated number of consumers is:

\[
C_{required} = \left\lceil \frac{R_{target}}{R_{consumer}} \right\rceil
\]

This is a starting estimate for load testing. Actual capacity also depends on poll time, batching, record distribution across partitions, offset commits, CPU, memory, and downstream services.

**Example:** a listener processes each order sequentially in about 20 ms. One consumer has an approximate capacity of 50 records/second. If the system needs to process 200 records/second, the initial estimate is:

\[
C_{required} = \left\lceil \frac{200}{50} \right\rceil = 4
\]

If the topic has at least 4 partitions and the database can serve 4 concurrent processing threads, you can begin testing with concurrency set to 4. If the topic only has 2 partitions, raising concurrency to 4 will not produce 4 active consumers; review the partition count and ordering requirements before changing the topic structure.

For batch processing, do not take single-record processing time and apply the formula directly while ignoring batch size. Measure completed records per second on one consumer under batch and commit conditions similar to production. Use p95/p99 processing times to evaluate stability, as averages can hide long-running batches.

## 4. Factors Limiting Scalability

Partition count is only the parallelism limit on the Kafka side. Concurrency can be increased while throughput remains flat if another component is already saturated.

**Application resources.** Each consumer needs a thread and processing resources. Increasing the number of consumers can increase CPU usage, heap, connection count, and GC activity. If the work is CPU-bound, too many processing threads can cause CPU contention rather than increasing capacity.

**Database and dependent services.** If each record calls a database, the number of connections in the connection pool and database write capacity may be the real limit. Concurrency higher than the pool limit can cause multiple threads to wait for connections, prolonging processing time and increasing consumer lag. HTTP services, rate limits, or a shared write system can create similar bottlenecks.

**Partition distribution and per-key load.** Six partitions do not guarantee six threads always have equal workloads. A high-frequency key can create a hot partition while other partitions have little data. The consumer assigned the hot partition still has high lag even when other consumers are mostly idle. In that case, review key selection, data distribution, and per-key processing logic.

**Processing time and polling.** Every consumer must continue calling `poll()` within `max.poll.interval.ms`. Increasing concurrency does not make an individual batch process faster. If a listener processes a batch for too long, that consumer can still exceed the poll interval and cause the group to rebalance. Measure per-consumer processing time and configure batching appropriately.

**Rebalance overhead.** Adding or removing instances, changing concurrency, or consumer disconnections can trigger a group rebalance. During partition redistribution, consumption may be temporarily interrupted or slowed down. Avoid constantly changing concurrency on minor load fluctuations; use sufficiently stable metrics to decide.

## 5. Process for Choosing and Tuning Concurrency

1. **Measure the baseline.** Run with an initial concurrency and record records consumed rate, consumer lag, p95/p99 processing time, CPU, heap, GC, connection pool, and downstream errors. Use traffic and message sizes representative of production.
2. **Count partitions and group-wide consumers.** Determine total partitions used by the subscription, number of application instances, number of listener containers, and current concurrency. Do not count a single process in isolation if the group has multiple instances.
3. **Estimate required concurrency.** Base this on target throughput and measured sustainable capacity of one consumer. Treat the result as a starting point, while checking partition limits and downstream resources.
4. **Increase in steps.** Try levels such as 1, 2, 4 in turn and measure again after the group stabilizes. Only increase further if throughput improves and latency, errors, CPU, memory, and dependent services remain within limits.
5. **Find the saturation point.** If adding consumers does not increase throughput, check hot partitions, CPU, database, connection pool, brokers, and processing time. Increasing concurrency further when a bottleneck is already saturated usually only increases queuing and resource contention.
6. **Scale partitions when necessary.** If every partition already has an active consumer and lag keeps rising, you may need to increase partitions or optimize per-partition processing speed. Before increasing, evaluate per-key ordering, key distribution, broker capacity, and long-term operability.
7. **Verify after deployment.** Observe group rebalances, partition assignments, consumer lag, and throughput after changes. Ensure the system remains stable when instances restart or a consumer temporarily leaves the group.

## 6. Reading Operational Signals to Decide on Scaling

| Observation | Likely Cause | Action |
|---|---|---|
| Consumer lag increases, some partitions lack a dedicated consumer, and resources have headroom | Group has fewer active consumers than partitions | Increase concurrency or instance count in steps. |
| Consumer lag increases, all partitions are assigned, and application CPU has headroom | Per-partition processing capacity or downstream may be the limit | Check listener time, hot partitions, and dependent services before adding partitions. |
| Throughput stops increasing when concurrency rises, CPU near saturation | Application is CPU-bound or experiencing thread contention | Optimize CPU work, measure useful threads, and try a lower concurrency level. |
| Throughput stops increasing, database or connection pool wait time rises | Database or connection pool is the bottleneck | Check queries, batch writes, and connection limits before adding consumers. |
| One partition has high lag while other partitions have low lag | Uneven key distribution or hot partition | Inspect keys, work size, and processing capacity specific to that partition. |
| Frequent rebalances, processing interrupted | Consumers starting/stopping repeatedly, poll timeout exceeded, or unstable infrastructure | Check container logs, processing time, `max.poll.interval.ms`, and deployment schedule. |

Metrics should be viewed together. Rising consumer lag does not automatically mean more consumers are needed; if the database is already overloaded, increasing concurrency can cause both lag and processing time to rise together. Conversely, low CPU while some partitions remain unexploited can indicate the group does not have enough active consumers.

## 7. Principles to Remember

- `concurrency` controls the number of consumers managed by a listener container per instance; total consumers in the group also depend on instance count and other containers in the same group.
- A partition is assigned to at most one consumer in the same group at a time. Consumers exceeding the partition count do not increase subscription parallelism.
- To sustainably increase throughput, you need sufficient partitions, sufficient listener processing capacity, and sufficient resources for downstream services simultaneously.
- Preserve per-partition ordering through proper key design; scaling partitions can affect how keys map to partitions for new records.
- Choose concurrency using measured throughput and latency metrics, then increase in steps and check for the saturation point.

The right concurrency is the lowest level that meets target throughput while keeping consumer lag, latency, and resources within operational limits. Once partition parallelism is fully utilized, the next step must be based on the measured bottleneck and business ordering requirements, rather than simply continuing to add threads.
