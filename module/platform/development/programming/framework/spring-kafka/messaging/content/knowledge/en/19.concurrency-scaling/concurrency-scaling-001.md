# Listener Container Concurrency

In Spring Kafka, `concurrency` determines the number of consumers a listener container creates to read data concurrently within the same consumer group. Increasing concurrency can help process multiple partitions in parallel, reduce consumer lag, and make better use of CPU. However, the number of usefully active consumers is capped by the number of assigned partitions; setting concurrency too high can create extra threads and connections without increasing throughput.

To choose the right concurrency, you need to understand how Spring Kafka creates child consumers, how Kafka distributes partitions within a group, the relationship between concurrency and partition count, as well as the limits of the listener, database, and downstream services.

## 1. How Does the Listener Container Manage Consumers?

When using `@KafkaListener`, the application does not create a `KafkaConsumer` or call `poll()` directly. Spring Kafka creates a listener container to manage the consumer, the poll loop, invoking the listener method, and committing offsets.

When configured with concurrency greater than one, Spring Kafka uses `ConcurrentMessageListenerContainer`. This container manages multiple child `KafkaMessageListenerContainer` instances. Each child container owns a Kafka consumer and runs its poll loop on its own thread.

```text
@KafkaListener
      |
      v
ConcurrentMessageListenerContainer
      |
      +--------------------+--------------------+
      |                    |                    |
      v                    v                    v
Child container 0   Child container 1   Child container 2
      |                    |                    |
      v                    v                    v
KafkaConsumer 0      KafkaConsumer 1      KafkaConsumer 2
      |                    |                    |
      v                    v                    v
Consumer thread 0    Consumer thread 1    Consumer thread 2
      |                    |                    |
      +--------------------+--------------------+
                           |
                           v
                    Kafka consumer group
```

Therefore, `concurrency=3` means the listener endpoint has three child consumers, each with its own thread and poll loop. It does not mean a single `KafkaConsumer` is called concurrently from three threads. `KafkaConsumer` is not thread-safe; Spring Kafka manages consumer ownership per child container.

## 2. Declaring Concurrency with `@KafkaListener`

Concurrency can be specified directly on the annotation:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    @KafkaListener(
            id = "order-created-listener",
            topics = "orders.created",
            groupId = "order-projection",
            concurrency = "3")
    public void onMessage(String payload) {
        // Process a single record.
    }
}
```

`concurrency` in the annotation accepts a string value to support placeholders or SpEL. For example, you can externalize the value to configuration:

```java
@KafkaListener(
        topics = "orders.created",
        groupId = "order-projection",
        concurrency = "${app.kafka.order-listener-concurrency:3}")
public void onMessage(String payload) {
    // Process the record.
}
```

```yaml
app:
  kafka:
    order-listener-concurrency: 3
```

This approach lets you change concurrency per environment without modifying source code. Make sure the configured value is a positive integer and does not exceed the resources the application can support.

## 3. Configuring Concurrency on the Listener Container Factory

If multiple listeners share the same factory, you can set the default concurrency on `ConcurrentKafkaListenerContainerFactory`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
public class KafkaListenerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, String>
            kafkaListenerContainerFactory(
                    ConsumerFactory<String, String> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);
        return factory;
    }
}
```

A listener using this factory:

```java
@KafkaListener(
        topics = "orders.created",
        groupId = "order-projection",
        containerFactory = "kafkaListenerContainerFactory")
public void onMessage(String payload) {
    // Process the record.
}
```

With Spring Boot, you can configure the default concurrency for listener containers via `spring.kafka.listener.concurrency`:

```yaml
spring:
  kafka:
    listener:
      concurrency: 3
```

This value applies to the factory/container auto-configured by Boot. If the application declares its own factory, set concurrency directly on that factory. The `concurrency` value on `@KafkaListener` can override the factory default for that specific endpoint.

Use factory configuration when multiple listeners share the same concurrency level. If individual listeners have different loads and requirements, configuring them individually via the annotation or separate factories is easier to control.

## 4. Relationship Between Concurrency and Partition Count

Kafka distributes partitions across consumers within the same group. At any point in time, a partition is assigned to at most one consumer in the group. Therefore, the number of consumers that can process data in parallel is capped by the number of partitions the group subscribes to.

For example, the topic `orders.created` has six partitions:

```text
Topic orders.created: P0  P1  P2  P3  P4  P5

concurrency = 1
  Consumer 0: P0 P1 P2 P3 P4 P5

concurrency = 3
  Consumer 0: P0 P1
  Consumer 1: P2 P3
  Consumer 2: P4 P5

concurrency = 6
  Consumer 0: P0
  Consumer 1: P1
  Consumer 2: P2
  Consumer 3: P3
  Consumer 4: P4
  Consumer 5: P5

concurrency = 8
  Six consumers have assigned partitions;
  the remaining two consumers have no partitions to read.
```

The diagram is a balanced distribution example for illustration, not a guarantee that partition assignment will always follow those exact pairs. Actual results depend on the partition assignor, other consumers in the group, subscriptions, and rebalance state.

When concurrency is lower than the partition count, a consumer can receive multiple partitions. When concurrency equals the partition count, you can achieve one consumer per partition if there are no other consumers in the group. When concurrency exceeds the partition count, some consumers receive no partition assignments and do not increase read parallelism for that topic.

## 5. Calculating Total Consumers Across Multiple Instances

The concurrency of a listener endpoint applies per application instance. When scaling the application horizontally, the total number of consumers in the same group increases with the number of replicas.

For example, with three pods, each running a listener with concurrency set to two:

```text
Pod A: 2 consumer threads
Pod B: 2 consumer threads
Pod C: 2 consumer threads
-------------------------
Total: 6 group members
```

If the topic has six partitions, the group can distribute the six partitions across the six consumers. If the topic only has four partitions, at most four consumers receive assigned partitions; the remaining two consumers stay idle.

For an endpoint subscribing to multiple topics, the parallelism limit relates to the total number of partitions the group subscribes to. However, subscription patterns, topics with uneven partition counts, or other listener endpoints in the same group can make distribution more complex.

Do not mechanically add up the concurrency of every application if they use different group IDs. Two different group IDs are two independent consumer groups; each group can read all partitions of the topic.

## 6. Concurrency and Record Ordering

Kafka only guarantees ordering within a single partition. When Spring Kafka increases concurrency, different partitions can be processed in parallel on different consumer threads.

For example:

```text
Partition 0: A1 -> A2 -> A3  -- Consumer 0
Partition 1: B1 -> B2 -> B3  -- Consumer 1
Partition 2: C1 -> C2 -> C3  -- Consumer 2
```

Consumer 0 preserves the order of records in Partition 0; Consumer 1 preserves order in Partition 1. There is no global order across A1, B1, and C1.

If events for the same order need to be processed in order, the producer should use `orderId` as the key so they are routed to the same partition. Increasing concurrency does not break ordering within a partition when the listener processes sequentially on the consumer thread. However, if the listener hands off work to an executor or processes asynchronously and returns early, business completion order may differ from offset order. When ordering is required, both the asynchronous processing flow and acknowledgement/commit must be controlled.

## 7. Record Listener and Batch Listener Under Concurrency

With a record listener, the container invokes the listener method for each record. One consumer thread can receive a batch from poll and invoke the listener sequentially for those records. Other child consumers process their assigned partitions in parallel.

With a batch listener, the container invokes the listener once with the list of records from a poll. One batch is processed on that child container's consumer thread; concurrency creates additional child consumers to process other partitions in parallel.

Batch listener example:

```java
import java.util.List;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;

@KafkaListener(
        topics = "orders.created",
        groupId = "order-batch-projection",
        concurrency = "3",
        containerFactory = "batchKafkaListenerContainerFactory")
public void onMessages(List<ConsumerRecord<String, String>> records) {
    // Process the batch on the child container's consumer thread.
}
```

The factory must be configured for batch mode using `setBatchListener(true)`. Concurrency does not automatically turn a record listener into a batch listener; they are two independent settings.

## 8. Thread Safety of the Listener and Dependencies

When concurrency is greater than one, the same listener bean in the Spring context can be invoked concurrently from multiple consumer threads. Because beans are typically singletons, any mutable state in listener fields can be accessed concurrently.

Unsafe example:

```java
@Component
public class UnsafeOrderListener {

    private int processedCount;

    @KafkaListener(topics = "orders.created", concurrency = "3")
    public void onMessage(String payload) {
        processedCount++; // Unsafe when multiple threads update concurrently.
    }
}
```

`processedCount++` is not an atomic operation. Threads can overwrite each other's updates. If statistics are needed, use a Micrometer counter, `LongAdder`, or an appropriate synchronization mechanism instead of unprotected mutable fields.

Stateless listener example:

```java
@Component
public class OrderListener {

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(topics = "orders.created", concurrency = "3")
    public void onMessage(OrderCreatedEvent event) {
        orderService.process(event);
    }
}
```

`OrderService` and the dependencies it uses also need to be safe when called concurrently. Spring repositories are generally designed for concurrent use, but self-managed mutable state, non-thread-safe caches, shared formatters, or custom clients may require special handling.

Prefer stateless listeners, local variables, and thread-safe dependencies. Do not store payloads or request-specific data in fields of a singleton listener.

## 9. Concurrency and Downstream Capacity

Increasing the number of consumer threads does not just increase load on Kafka brokers. Each thread can concurrently call a database, REST API, cache, or other systems. If downstream services lack capacity, high concurrency increases contention, timeouts, and retries instead of throughput.

Database-writing listener example:

```text
6 consumer threads
       |
       v
6 concurrent record processing operations
       |
       v
Database connection pool (size = 4)
       |
       +--> 4 threads get a connection
       +--> 2 threads wait for a connection
```

If the connection pool is smaller than the number of concurrent processing threads, some consumer threads will wait to acquire a connection. Wait time prolongs poll processing and can lead to exceeding `max.poll.interval.ms`.

When increasing concurrency, review these together:

- Database connection pool size and database connection limits.
- HTTP client connection pool, timeouts, and rate limits of downstream services.
- JVM CPU, heap, garbage collection, and thread count.
- Partition count and broker throughput.
- Record/batch processing time and `max.poll.interval.ms`.
- Retry/backoff behavior and the potential to generate duplicate load when downstream is failing.

Do not increase concurrency just because consumer lag is growing. First determine whether consumers lack processing capacity or are being blocked by downstream services.

## 10. Relationship with `max.poll.records` and `max.poll.interval.ms`

Concurrency determines the number of consumers, while `max.poll.records` limits the number of records returned in a single poll. `max.poll.interval.ms` limits the maximum interval between two polls.

Suppose each consumer receives 100 records and processes them sequentially, averaging 80 ms per record:

```text
100 records x 80 ms = 8,000 ms = 8 seconds
```

Actual time also includes database, network, GC, and auxiliary logic time. If a batch takes too long before the next poll, the consumer can leave the group and trigger a rebalance. Increasing concurrency does not fix a hung listener thread or an oversized batch.

Adjustment directions:

1. Measure processing time at high percentiles rather than looking only at the average.
2. Reduce `max.poll.records` if each batch takes too long.
3. Increase `max.poll.interval.ms` when business logic genuinely needs a long time, while setting I/O timeouts.
4. Optimize database batches or reduce synchronous work inside the listener.
5. Only increase concurrency if there are enough partitions and downstream resources.

## 11. Rebalance When Changing Concurrency or Replicas

When the number of consumers in a group changes, Kafka needs to redistribute partitions. Rebalances occur in situations such as:

- The application starts additional replicas.
- A replica stops or loses connection.
- Changing concurrency increases or decreases the number of child consumers.
- Partitions are added to a topic or a pattern subscription discovers a new topic.
- A consumer fails to poll within the deadline or is considered inactive.

During a rebalance, partitions may temporarily pause processing while the group revokes and reassigns assignments. Frequent rebalances increase latency and consumer lag.

Monitor rebalance logs, assignment duration, and consumer lag. Choose stable concurrency based on load rather than constantly changing it on short-term fluctuations. For systems needing reduced disruption time, consider cooperative assignment strategies and static membership when appropriate for the Kafka version, Spring Kafka version, and deployment model. These mechanisms require consistent configuration across the whole group; they do not completely eliminate rebalances.

## 12. Monitoring Consumer Concurrency

To evaluate whether concurrency adds throughput or just adds threads, observe multiple metrics simultaneously:

| Metric | Question to answer |
| --- | --- |
| Consumer count in group | How many members are participating in the group? |
| Partition assignment | How many partitions is each consumer assigned? Are any consumers idle? |
| Records consumed rate | Is the total number of records processed per second increasing? |
| Consumer lag by partition | Which partition is falling behind? |
| Listener processing time | How long does each record/batch take? |
| Poll interval | Is the consumer calling poll regularly and within limits? |
| Rebalance count/duration | Is the group frequently reassigning partitions? |
| Downstream pool usage | Is the database/HTTP pool exhausted? |
| CPU and heap | Does the JVM still have headroom? |

When increasing concurrency from 2 to 4, if throughput does not increase while database wait time and rebalances rise, the system may have hit a downstream limit. If a few partitions have high lag while others are nearly empty, key distribution may be skewed or there may be hot partitions.

## 13. Practical Concurrency Selection Workflow

You can start with the following steps:

1. Determine the topic partition count or total partitions the listener subscribes to.
2. Measure target throughput and average/high-percentile processing time per record.
3. Choose an initial concurrency not exceeding the number of assignable partitions.
4. Run tests with representative load, observing consumer lag, throughput, poll interval, and downstream saturation.
5. Increase concurrency or replica count step by step, then compare results.
6. Stop increasing when throughput no longer improves or latency/downstream resources degrade.
7. If more parallelism than the current partition count is needed, evaluate increasing partition count and its impact on key ordering before changing the topic.

There is no single optimal concurrency number for every listener. A listener that only parses lightweight payloads can use more consumer threads than one performing multiple database queries or calling external services.

## 14. Common Pitfalls

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Concurrency increased but throughput does not increase | Consumer count already exceeds partition count or downstream is the bottleneck | Check assignment, partition count, and downstream latency |
| Some consumers receive no records | No partitions assigned to excess consumers | Reduce concurrency or increase partitions if appropriate |
| Listener encounters race conditions | Singleton listener has mutable fields shared across multiple threads | Make listener stateless, use thread-safe structures, or synchronize |
| Consumers frequently rebalance | Long processing, poll interval exceeded, or unstable instances | Measure processing time, check poll/heartbeat, and reduce load |
| Database connection pool exhausted | Concurrency exceeds connection capacity or slow queries | Adjust pool carefully, optimize queries, and cap concurrency |
| Business ordering is inverted | Listener offloads processing asynchronously or keys map to different partitions | Control async completion and choose keys by aggregate |
| Lag concentrated on a single partition | Hot key or uneven data distribution | Analyze key distribution and redesign partitioning when needed |
| Increasing replicas causes latency spikes | Rebalance and consumer warm-up | Monitor assignments, scale in steps, and use appropriate strategies |

## 15. Checklist Before Increasing Concurrency

- [ ] Total partitions the listener can read are known.
- [ ] Current consumer count across the entire group, including all replicas, has been checked.
- [ ] Concurrency does not exceed useful partition parallelism.
- [ ] Listener bean and dependencies are safe when called concurrently.
- [ ] Database/HTTP connection pools have sufficient capacity for concurrent load.
- [ ] Batch processing time stays within `max.poll.interval.ms`.
- [ ] Ordering by key and partition has been verified.
- [ ] Metrics for consumer lag, processing time, and rebalances are available.
- [ ] Tested with representative load and measured throughput before/after increasing.
- [ ] Rollback plan for concurrency is ready if downstream becomes overloaded.

## 16. Conclusion

Spring Kafka listener container `concurrency` determines the number of child consumers and poll loop threads created for a listener endpoint. Increasing concurrency helps process multiple partitions in parallel, but a partition within the same consumer group is assigned to at most one consumer at a time. Therefore, partition count, total replicas, and concurrency together determine actual parallelism.

When scaling, ensure listeners and dependencies are thread-safe, downstream has enough capacity, processing time does not exceed the poll interval, and per-partition ordering still meets business requirements. Measure consumer lag, processing time, assignments, and rebalances before adding more consumers. Effective concurrency is the level that increases throughput without destabilizing downstream systems or the consumer group.

## References

- [Spring for Apache Kafka — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring for Apache Kafka — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/annotation-driven.html)
- [Spring Boot — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
- [Apache Kafka — Consumer Groups](https://kafka.apache.org/documentation/#intro_consumers)
