# Configuring Concurrency and Partition Count Limits

Kafka achieves parallel message processing by splitting a topic into partitions and distributing those partitions among consumers within the same consumer group. Spring Cloud Stream lets you configure concurrency on an input binding to spin up multiple concurrent consumers per application instance. However, the number of consumers that can actually receive data in a group is bounded by the number of subscribed partitions.

This is a critical limit when scaling an application. Increasing replica counts or raising concurrency does not automatically increase throughput if the topic lacks enough partitions. Consumers exceeding the partition count receive no partition assignment and sit idle. Conversely, if there are more partitions than consumers, each consumer can be assigned multiple partitions.

This lesson explains the relationship between partitions, consumer groups, concurrency, and instance counts; how to configure concurrency in the Spring Cloud Stream Kafka binder; how to distinguish concurrency from `max.poll.records` and `max.poll.interval.ms`; the impact on ordering, rebalancing, throughput, and operations; and how to test and select an appropriate configuration.

## Learning Objectives

After this lesson, you will be able to:

- Explain why the number of active consumers in a group cannot exceed the number of assigned partitions.
- Calculate total consumer count based on concurrency and application instance count.
- Configure `consumer.concurrency` on a Spring Cloud Stream input binding.
- Distinguish `concurrency` from `max.poll.records` and `max.poll.interval.ms`.
- Predict which consumers are active or idle as partition and replica counts change.
- Understand consumer group rebalancing when instances join, leave, or disconnect.
- Preserve key-based processing order and recognize the limits of parallel processing.
- Measure lag, load skew, and scaling efficiency to tune configuration.

## 1. Partitions and Consumers in Kafka

A Kafka topic is divided into one or more partitions. Each partition is an ordered log containing sequentially appended records numbered by offsets. Kafka distributes partitions across consumers belonging to the same consumer group.

Key rules:

- Within a single consumer group, at any given time, a partition is assigned to at most one consumer.
- One consumer can be assigned multiple partitions.
- A consumer group may have unassigned idle consumers if the number of consumers exceeds the number of partitions.
- Different consumer groups can read the same topic independently; each group maintains its own offset progress.

For example, suppose topic `orders` has six partitions:

~~~text
Topic orders
  P0  P1  P2  P3  P4  P5
~~~

If group `order-processor` has three consumers, Kafka can assign two partitions to each consumer. If the group has six consumers, each consumer can receive one partition. If the group has eight consumers, at most six consumers receive partitions; the remaining two receive no records from that topic.

This limit applies per consumer group. If a service runs two different groups, each group can independently read all six partitions. Do not create a separate group ID per replica when the goal is load sharing, as that creates multiple independent consumption copies instead of sharing partitions across replicas.

## 2. concurrency in Spring Cloud Stream

With the Kafka binder, the `concurrency` property on a consumer binding specifies how many concurrent consumers an application instance creates for that binding. Each consumer has its own Kafka client and poll loop lifecycle managed by the container.

Example:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
          consumer:
            concurrency: 3
~~~

In this example, each application instance creates three consumers for the `processOrder-in-0` input binding. When multiple replicas are deployed, the total number of consumers in the same group is the sum of concurrency across all replicas.

`concurrency` is a per-binding property. If an application has multiple input bindings, each binding can have its own concurrency configuration. Calculate total consumers per topic/group rather than looking only at a single application-wide concurrency number.

### 2.1. Formula for Consumer Count

For an input binding subscribed to a single topic:

\[
C = I \times K
\]

Where:

- I: number of running application instances/replicas.
- K: concurrency per instance for that binding.
- C: total consumers in the same consumer group.

If the topic has P partitions, the maximum number of consumers assigned partitions at any time is:

\[
A = \min(P, C)
\]

The number of unassigned consumers in the single-topic model is:

\[
U = \max(0, C-P)
\]

These formulas describe quantitative bounds. The exact partition distribution also depends on the assignor, number of subscribed topics, and group state.

### 2.2. Concurrency Calculation Example

Suppose a service has three replicas and concurrency is two:

\[
C = 3 \times 2 = 6
\]

If the topic has six partitions, all six consumers can be active:

~~~text
6 partitions / 6 consumers

Replica A: Consumer A1 <- P0
           Consumer A2 <- P1
Replica B: Consumer B1 <- P2
           Consumer B2 <- P3
Replica C: Consumer C1 <- P4
           Consumer C2 <- P5
~~~

If the topic only has four partitions, at most four consumers are assigned:

~~~text
4 partitions / 6 consumers

Consumer A1 <- P0
Consumer A2 <- P1
Consumer B1 <- P2
Consumer B2 <- P3
Consumer C1 <- idle
Consumer C2 <- idle
~~~

The diagram shows one possible distribution; exact consumer-to-partition assignment is decided by the Kafka assignor.

### 2.3. Quick Comparison Table

Assume a topic with six partitions and all replicas sharing the same group:

| Replicas | Concurrency per Replica | Total Consumers | Max Active Consumers | Excess Consumers |
|---:|---:|---:|---:|---:|
| 1 | 2 | 2 | 2 | 0 |
| 2 | 2 | 4 | 4 | 0 |
| 3 | 2 | 6 | 6 | 0 |
| 4 | 2 | 8 | 6 | 2 |
| 3 | 3 | 9 | 6 | 3 |
| 6 | 1 | 6 | 6 | 0 |

Both adding replicas and increasing concurrency raise the total consumer count. Choose how to scale based on CPU/memory resources, deployment constraints, and workload isolation needs.

## 3. Configuring concurrency in Spring Cloud Stream

Concurrency is declared on the consumer binding:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
          consumer:
            concurrency: 4
~~~

In this example, each replica creates four consumers for the binding. With two replicas running, the group has eight consumers in total. For all eight consumers to receive partitions from a topic, the topic needs at least eight partitions.

Use a stable group ID across replicas sharing work. If `group` is omitted, the binder may use an anonymous group per framework rules; this is generally unsuitable for consumers that must preserve progress across restarts.

### 3.1. Checking Actual Partition Count

Do not assume a topic has enough partitions based on the configured concurrency value. Inspect topic metadata on the broker or via Kafka admin tools.

Example CLI command:

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic orders
~~~

The topic description displays the partition count and leader for each partition. If a topic was previously created with fewer partitions than needed to scale, plan to increase partitions or create a new topic through operational procedures. Raising concurrency does not automatically create more partitions.

### 3.2. Multiple Instances in the Same Group

When deploying multiple replicas, all replicas of the same service must use the same group ID so Kafka distributes partitions among them:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
          consumer:
            concurrency: 2
~~~

The group ID must be consistent across replicas. If each replica uses a different group ID, each group reads the entire topic and reprocesses the same events. That is fan-out across groups, not scale-out within a single group.

### 3.3. Default Rebalance Mechanism

By default, the Kafka binder uses Kafka's consumer group mechanism to let Kafka manage partition assignments. When a new consumer joins, an old consumer leaves, or a heartbeat is missed, Kafka can rebalance to redistribute partitions.

With this automatic mode, you normally do not need to assign partitions manually per replica using `instance-index`. If `autoRebalanceEnabled` is disabled, the binder can use `instanceCount` and `instanceIndex` for static partition assignment. In that case, instance counts and indices must be managed in lockstep with the deployment; do not mix static configuration while expecting Kafka to auto-balance like the default mode.

## 4. Concurrency Limits Based on Partition Count

### 4.1. Excess Consumers Sit Idle

Suppose a topic has three partitions, each replica creates two consumers, and two replicas are running:

\[
C = 2 \times 2 = 4,\quad P = 3
\]

At most three consumers are assigned partitions. The remaining consumer cannot process records from that topic in that group until an assignment change occurs.

This is not necessarily an error. Excess consumers can serve as headroom if partitions are increased in the future or deployments shift. However, they still consume threads, Kafka clients, connections, and memory; avoid provisioning excessive concurrency without justification.

### 4.2. One Consumer Can Receive Multiple Partitions

If a topic has twelve partitions and a group has three consumers, each consumer may be assigned roughly four partitions. That consumer reads records from all its assigned partitions via `poll()`.

Having more partitions than consumers does not mean the entire topic is processed sequentially. The consumers still run in parallel; each consumer simply handles multiple partitions.

### 4.3. Scaling Concurrency Has a Ceiling

If the partition count is six, increasing per-replica concurrency from three to six on a single replica scales consumers from three to six. Increasing it to twelve will not raise active consumers beyond six.

Once the partition limit is reached, increasing parallelism at the consumer group level requires increasing the partition count or changing the processing model. Increasing partitions affects key mapping, ordering, and broker resources, so evaluate carefully beforehand.

### 4.4. Multiple Topics on One Binding

If a binding subscribes to multiple topics, the total assignable partitions equal the sum of partitions across all subscribed topics, though exact assignment and balance depend on the assignor. Do not blindly apply the single-topic formula while ignoring multiple topics or pattern subscriptions.

## 5. Distinguishing concurrency from max.poll.records

These two properties control two distinct dimensions:

| Property | Controls | Unit |
|---|---|---|
| consumer.concurrency | Number of concurrent consumers per instance/binding | Consumers |
| max.poll.records | Maximum records Kafka returns in a single poll for one consumer | Records per poll |

For example, an instance with concurrency 3 and `max.poll.records` set to 100 has three Kafka consumers; each consumer can receive up to 100 records per poll, depending on available records and assigned partitions.

`max.poll.records` does not create extra consumers and does not add partitions. It adjusts the batch size of records each consumer pulls in a single poll.

### 5.1. Configuring max.poll.records

The Kafka binder lets you pass native consumer properties via binding configuration:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
          consumer:
            concurrency: 3
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              configuration:
                max.poll.records: 100
~~~

In this example, concurrency is three consumers per instance; each consumer has a limit of 100 records per poll. With a record-by-record consumer, the container passes records to the handler one by one. With a batch listener or different processing configuration, how the application receives the batch can differ.

Do not blindly raise `max.poll.records` just to boost throughput. If processing a single record takes a long time, a large batch can push processing time between polls past the allowed limit and trigger a rebalance.

## 6. max.poll.interval.ms and Processing Duration

Kafka requires consumers to keep calling `poll()` within the configured interval. `max.poll.interval.ms` sets the maximum time between poll calls before the consumer is considered stalled and may leave the group, causing partitions to be reassigned.

This value must be large enough for the actual processing time of a batch, but should not be set arbitrarily high because it delays detection of a stuck consumer.

Example configuration:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
          consumer:
            concurrency: 3
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              configuration:
                max.poll.records: 50
                max.poll.interval.ms: 300000
~~~

In this example, each consumer fetches at most 50 records per poll and has a configured maximum interval between polls. These are illustrative values; measure tail-percentile batch processing time, include internal retry time, and pick appropriate bounds.

### 6.1. Relationship Between Batch Size and Processing Time

If a consumer processes records sequentially and the average time per record is `t`, a batch of `B` records takes approximately:

\[
T_{\text{batch}} \approx B \times t
\]

This is only a rough estimate. Actual time depends on I/O, databases, retries, GC, networking, and data skew. Evaluate worst-case processing time, not just averages.

If `T_batch` approaches or exceeds `max.poll.interval.ms`, consider:

- Reducing `max.poll.records`.
- Improving per-record processing efficiency.
- Raising `max.poll.interval.ms` within operationally acceptable limits.
- Moving long-running tasks to an asynchronous processing model with proper pause/resume and commit semantics.
- Reducing blocking retries on the consumer thread.

Do not offload work to another thread and commit offsets immediately without guaranteeing the async task finishes before the offset commits. Doing so can lose messages if the application crashes.

## 7. Concurrency, Ordering, and Partition Keys

Concurrency increases parallel processing across multiple partitions. Kafka preserves record ordering within a single partition, but provides no global ordering across partitions.

If events for the same order must be processed in order, the producer must use a stable key such as `orderId` so those events land in the same partition. In Spring Cloud Stream, partition keys can be configured as:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders
          producer:
            partition-key-expression: payload.orderId
            partition-count: 6
~~~

The Kafka binder computes the partition according to the binding's partitioning configuration. If the application or another Kafka consumer needs to read the actual Kafka record key for compaction or custom routing, check the binder's message key configuration and verify the record key on the broker; partition selection and record key are two distinct aspects to understand clearly.

### 7.1. One Partition Has Only One Consumer in a Group

Kafka never assigns the same partition to two consumers in the same group simultaneously. Thus, two consumer threads can process two different partitions concurrently, while records within a single partition remain with the same consumer.

However, an application might offload messages to an executor or reactive pipeline. Doing so can cause multiple records from the same partition to complete out of read order. When business order matters, process sequentially per partition or key and only commit offsets once preceding records have finished.

### 7.2. Retries and Ordering

Blocking retries in the consumer can stall the partition being processed. If failures are routed to a retry topic or DLQ, later records may proceed while an earlier record awaits retry. When strict ordering is required, decide whether retries may break ordering or whether the partition must remain paused.

You cannot simultaneously maximize parallelism and preserve global ordering. Identify the exact ordering boundary that genuinely needs protection—usually per aggregate or per key.

## 8. Choosing Concurrency and Partition Count

There is no single formula for all workloads. Start from target throughput, processing time, and resources:

1. Measure single-record processing time and single-consumer throughput.
2. Determine the service's target throughput.
3. Estimate the required number of active consumers.
4. Multiply per-replica concurrency by the planned replica count.
5. Ensure the topic has enough partitions to support the required active consumers.
6. Benchmark with realistic data and load.
7. Monitor lag and load distribution to refine tuning.

For example, if one consumer steadily handles 200 records/sec and the service requires 900 records/sec, an initial estimate calls for at least five active consumers. You might deploy two replicas with concurrency three (six consumers total) and a topic with at least six partitions. Actual numbers must be re-measured since brokers, databases, key skew, and processing overhead all impact throughput.

### 8.1. Do Not Over-Partition

More partitions enable higher parallelism and scaling headroom, but they also increase:

- Broker metadata and partition management overhead.
- File handles, log segments, and replication overhead.
- Rebalance work and recovery time.
- Complexity of lag monitoring and key distribution.

Choose partition counts based on current demand and reasonable growth plans. Do not create huge partition counts just in case they might someday be needed.

### 8.2. Increasing Partitions Can Change Key Mapping

With hash-based partition selectors modulo partition count, increasing partitions can map a key to a different partition. Older records remain in the old partition; newer records may land in the new partition. This can cause events for the same aggregate to be processed concurrently during the transition.

If per-key ordering is mandatory, plan a migration: pause or drain producers, clear old backlogs, transition topology in phases, or create a new versioned topic. Never increase partitions in production without assessing the impact.

## 9. Rebalancing and Multi-Instance Deployments

When a new instance joins a consumer group, Kafka redistributes partitions via the assignor. When an instance stops or disconnects, the group may also rebalance. During a rebalance, consumption may briefly pause.

### 9.1. Causes of Rebalances

- A new replica starts up and joins the group.
- A replica stops or restarts.
- A consumer fails to call `poll()` within the allowed interval.
- Session timeout or heartbeat is not maintained.
- Subscriptions or consumer counts change.
- Certain group/assignor configuration changes.

### 9.2. Reducing Rebalance Impact

- Use graceful shutdown so consumers leave the group cleanly.
- Size `max.poll.records` appropriately for processing time.
- Avoid overly long blocking handlers.
- Monitor rebalance duration and consumer lag.
- Provision enough partitions for the target consumer count.
- Consider a cooperative assignor if supported by your Kafka and binder versions, after testing compatibility.

### 9.3. Rolling Deployments

During a rolling deployment, old replicas leave the group and new replicas join in waves. Kafka may rebalance multiple times. Avoid simultaneous restarts that drop all consumers briefly, and configure readiness/liveness probes properly so instances do not appear ready before the binder is ready.

If consumer counts fluctuate continuously due to autoscaling, frequent rebalances may occur. Tune scale cooldown periods, minimum/maximum replica bounds, and rebalance costs.

## 10. Observing Concurrency Effectiveness

Looking only at CPU or replica counts is insufficient to evaluate concurrency. Monitor:

| Metric | What to Observe |
|---|---|
| Consumer count per group | Actual consumers versus partition count |
| Partition assignment | Which partitions are assigned to which consumers |
| Consumer lag per partition | Which partitions are accumulating backlog |
| Records consumed per second | Actual throughput |
| Processing duration | Time to process each record/batch |
| Poll duration and poll interval | Whether consumers call `poll()` on time |
| Rebalance count/duration | Whether the group is shifting assignments too frequently |
| CPU, memory, GC | Whether concurrency exceeds instance resources |
| Partition skew | Whether one partition carries abnormally high load |
| Error/retry rate | Whether failures are slowing consumers or causing loops |

If consumer lag does not drop when increasing concurrency, check whether the partition limit has been reached, whether keys are skewed, whether consumers are bottlenecked on a database or downstream dependency, and whether processing latency is too high.

## 11. Testing Concurrency and Partition Limits

The Spring Cloud Stream Test Binder is useful for testing bindings and message logic, but it does not fully simulate Kafka's group coordinator, partition assignment, and rebalancing. These behaviors require integration tests against real Kafka, such as with Testcontainers.

### 11.1. Testing Consumer Count and Assignment

An integration test can:

1. Start a test Kafka broker.
2. Create an `orders` topic with a known partition count, such as four.
3. Start the consumer application with concurrency 2 and a fixed group ID.
4. Wait for group assignment to complete.
5. Inspect group state to verify at most two consumers hold partition assignments and each partition belongs to only one consumer.
6. Start a second replica and verify assignments rebalance.

Do not merely assert that the concurrency property bound correctly. Verify consumers actually join the group and partitions distribute as intended.

### 11.2. Testing Consumer Limits

With a three-partition topic and four consumers in the group, verify at most three consumers hold assignments. The excess consumer may exist but receives no partitions from that topic.

With a six-partition topic and three consumers, verify each consumer can receive multiple partitions. Do not assert that the assignor always distributes exactly two partitions per consumer across every multi-topic configuration.

### 11.3. Testing Key Affinity and Ordering

Send multiple records with the same `orderId` and verify they land in the same partition. Send records across multiple `orderId` values and verify distribution across partitions. Then verify the consumer processes records from the same partition according to the application's ordering requirements.

### 11.4. Testing max.poll.records and max.poll.interval.ms

Create a controlled-latency workload to verify:

- `max.poll.records` caps the records returned in one poll.
- Larger batches increase processing time between polls.
- A consumer can leave the group if it exceeds `max.poll.interval.ms`.
- Reducing batch size or optimizing handlers avoids timeout-induced rebalances.

Do not intentionally induce timeouts in production. Use a test broker and controlled data to test this scenario.

## 12. Common Pitfalls

1. **Increasing concurrency without increasing partitions**: excess consumers receive no partitions. Calculate total consumers as replicas times concurrency.
2. **Each replica using a different group ID**: each group reads the entire topic, causing unintended duplicate processing. Share the same group across replicas that should share load.
3. **Confusing concurrency with records per poll**: `concurrency` creates consumers; `max.poll.records` limits records per poll. Tune the right property.
4. **Confusing partition count with replica count**: partitions are data distribution units; replicas are application processes. Design both together.
5. **Setting `max.poll.records` too high**: batch processing time can exceed `max.poll.interval.ms`. Measure processing time and size batches accordingly.
6. **Processing asynchronously while committing offsets too early**: the application can lose unfinished tasks on crash. Coordinate ack/commit with completion.
7. **Assuming higher concurrency always increases throughput**: brokers, databases, hot keys, or CPU may be the bottleneck. Measure lag and throughput.
8. **Ignoring rebalances during autoscaling**: constant scaling can pause consumption. Use cooldowns and graceful shutdown.
9. **Increasing partitions arbitrarily**: keys may remap to new partitions and break per-aggregate ordering. Plan migrations.
10. **Not checking actual partition assignments**: valid properties do not prove consumers are assigned as expected. Run integration tests with Kafka.
11. **Ignoring partition skew**: one hot partition can hold lag high while other consumers sit idle. Choose keys carefully and inspect data distribution.

## 13. Concurrency Configuration Workflow

When optimizing a Kafka consumer in Spring Cloud Stream:

1. Identify the topic and actual partition count.
2. Define a shared group ID for replicas sharing load.
3. Measure throughput and processing time of a single consumer.
4. Estimate the total number of consumers required.
5. Choose replica count and per-replica concurrency so total consumers do not far exceed partition count.
6. Configure `consumer.concurrency` on the input binding.
7. Tune `max.poll.records` based on batch size and processing time.
8. Tune `max.poll.interval.ms` for worst-case processing duration.
9. Test assignment, rebalancing, key affinity, and ordering.
10. Monitor consumer lag, partition skew, throughput, and resource usage after deployment.
11. Change partition counts only after evaluating key remapping and a migration plan.

## Conclusion

Concurrency in the Spring Cloud Stream Kafka binder defines the number of concurrent consumers per instance for an input binding. When multiple replicas share a group, total consumers equal replicas times concurrency. For a topic with P partitions and C consumers, at most min(P,C) consumers can be assigned partitions; the rest remain idle if C exceeds P.

`concurrency`, `max.poll.records`, and `max.poll.interval.ms` address three distinct concerns: consumer count, records per poll, and maximum time between polls. Choosing a good configuration balances partition count, replicas, batch size, processing duration, key distribution, and resources. Verify with actual consumer assignments and lag rather than raising concurrency by guesswork.

## References

- [Spring Cloud Stream — Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/index.html)
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Apache Kafka — Consumer Configs](https://kafka.apache.org/documentation/#consumerconfigs)
