# Distinguishing Instance Count, Consumer Threads, and Partition Count

When increasing the processing capacity of a Spring Cloud Stream application, three numbers are frequently confused: the application instance count, the consumer thread count, and the broker partition count. They all relate to parallel execution, yet they represent three distinct layers. Adding pods does not automatically create more partitions; increasing concurrency does not add partitions to a topic; and a consumer group can contain many consumers while still executing in parallel only up to the number of partitions the broker can distribute to that group.

To design properly, you must first determine how many replicas the application runs, how many consumers each replica opens for an input binding, how many partitions or queues the broker splits the data into, and whether consumers belong to the same group or independent groups. Only then should you choose the scaling strategy and configuration suited for Kafka, RabbitMQ, or Pulsar.

## 1. Four concepts to separate

### 1.1. Application instance

An instance is a running process or deployment replica of the application. In Kubernetes, a pod running the application is typically counted as one instance. On another deployment platform, an instance may be a container or a service replica.

If the `order-worker` service runs three pods, the application has three instances. Each instance has its own configuration, memory, threads, and broker connections. When one instance stops, the remaining instances continue running; how messages are redistributed depends on the broker and binder.

An instance is not synonymous with a consumer. One instance can open one or multiple consumers for the same input binding, depending on concurrency settings and the binder.

### 1.2. Input binding and consumer streams

An input binding is the logical port Spring Cloud Stream uses to receive messages for a Supplier, Function, or Consumer. For example, a `processOrder` bean has the default input binding `processOrder-in-0`.

One input binding can create multiple internal consumers. The `consumer.concurrency` property controls the per-instance consumer concurrency level as supported by the binder. The default value of the common property is 1.

Example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-workers
          consumer:
            concurrency: 2
~~~

With this configuration, each application instance can create two consumers for the `processOrder-in-0` binding. If three instances are deployed, the expected number of internal consumers is:

\[
3\ \text{instances} \times 2\ \text{consumers/instance} = 6\ \text{consumers}
\]

In this lesson, "consumer stream" (or consumer slot) refers to one consumer slot or consumer worker participating in reading data for an input binding. It is neither a broker partition nor an application instance.

### 1.3. Consumer group or subscription

A consumer group is the logical identity of a set of consumers receiving from a destination together. With Kafka, consumers using the same group divide the topic's partitions. Two different groups reading the same topic maintain independent read positions, so both groups can receive all events.

The RabbitMQ binder creates a queue for each consumer group on the destination exchange. Consumer instances in the same group read from the shared queue and compete for messages. Pulsar uses named subscriptions to manage consumption position and distribution across consumers sharing a subscription name; the subscription type governs load sharing or failover.

A group is not a consumer stream count. A group can have one or many instances, and each instance can have multiple internal consumers. Adding more groups also does not increase load sharing within a single group; it creates independent consuming streams.

### 1.4. Partition

A partition is a slice of a destination's data. With Kafka and Pulsar, a topic can consist of multiple partitions to increase parallel writes and reads. Each partition maintains its own ordering; there is no automatic global order across partitions.

RabbitMQ does not have native partitions like Kafka's model. Spring Cloud Stream's Rabbit binder can simulate partitioning by routing to a separate queue per partition. Therefore, when using RabbitMQ, distinguish a normal consumer group queue from the partitioned queues created by the binder.

## 2. Big picture of the relationship

The following diagram illustrates a six-partition topic consumed by one group across three instances, with each instance running two internal consumers:

~~~mermaid
flowchart TB
    T[("Topic orders.events<br/>6 partitions")]
    subgraph G["Consumer group: order-workers"]
      subgraph I0["Instance 0"]
        C00["Consumer 0"]
        C01["Consumer 1"]
      end
      subgraph I1["Instance 1"]
        C10["Consumer 0"]
        C11["Consumer 1"]
      end
      subgraph I2["Instance 2"]
        C20["Consumer 0"]
        C21["Consumer 1"]
      end
    end
    T --> G
~~~

In Kafka, six consumer members in the same group can be assigned six partitions, one partition per consumer in this example. If the topic only had four partitions, at most four consumer members could receive partitions at the same time; the other two consumers would remain without assigned partitions. If the topic had eight partitions, the six consumers would collectively receive eight partitions, with some consumers owning more than one partition.

Instance count, concurrency, and partition count should be chosen together. There is no mandatory rule that all three numbers must be equal.

## 3. Example calculating parallelism with Kafka

Kafka distributes partitions among consumer members belonging to the same consumer group. For one group and one topic, a partition at any given time is assigned to at most one consumer member in that group. One consumer can read multiple partitions.

If:

- The number of application instances is R.
- `consumer.concurrency` per instance is C.
- The topic has P partitions.

Then the expected number of consumer members is:

\[
N = R \times C
\]

The number of consumer members that can actually receive at least one partition is bounded by:

\[
N_{\text{active}} \leq \min(N, P)
\]

This is an estimate of maximum partition-level parallelism, not a throughput prediction formula. Actual speed still depends on processing time, I/O, rebalances, key distribution, batch size, and broker capacity.

### 3.1. Four common scenarios

| Instances | Concurrency per instance | Consumer members | Partitions | Possible outcome |
|---:|---:|---:|---:|---|
| 3 | 2 | 6 | 6 | All six consumers can be used, each receiving one partition |
| 3 | 2 | 6 | 4 | At most four consumers receive partitions; two consumers remain idle |
| 2 | 2 | 4 | 8 | All four consumers are active; each receives two partitions on average |
| 5 | 1 | 5 | 1 | Only one consumer receives the partition; the other four remain idle |

For example, a topic has four partitions and a group has six consumers. Increasing instances from three to four while keeping concurrency at two creates eight consumer members. Kafka still has only four partitions to assign, so increasing consumers does not increase topic parallelism.

Conversely, if there are eight partitions and only two consumers, each consumer can receive multiple partitions. This is not wrong; it simply means the number of processing threads is lower than the number of data segments that could be read in parallel.

### 3.2. Configuring concurrency for Kafka

With the Kafka binder and its default auto-rebalance mechanism, Kafka manages partition assignment when consumers join or leave the group. You can increase concurrency per input binding:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-workers
          consumer:
            concurrency: 2
~~~

When three instances are deployed with this configuration, the group has about six consumer members. If the topic has six partitions, this is a starting configuration capable of utilizing all six partitions in parallel.

With Kafka `autoRebalanceEnabled=true` (the default), you do not need to manually assign `instanceIndex` to each instance for Kafka to distribute partitions. If you disable auto-rebalance and let the binder assign partitions per instance, you must configure `spring.cloud.stream.instanceCount` and `spring.cloud.stream.instanceIndex` consistently on each instance; the partition count must be sufficient to satisfy the chosen assignment scheme.

## 4. InstanceCount and InstanceIndex serve a distinct purpose

Spring Cloud Stream has two application-level properties:

| Property | Meaning |
|---|---|
| `spring.cloud.stream.instanceCount` | Total number of instances participating in an instance-indexed partitioning scenario |
| `spring.cloud.stream.instanceIndex` | Unique index of the current instance, ranging from 0 to `instanceCount - 1` |

Example with three instances:

| Instance | instanceCount | instanceIndex |
|---|---:|---:|
| Pod A | 3 | 0 |
| Pod B | 3 | 1 |
| Pod C | 3 | 2 |

`instanceCount` is not concurrency. It describes the total number of instances in an index-based data distribution scheme. `instanceIndex` is also not the partition count; it helps an instance identify the slice of data assigned to it.

In some binders, consumers can override application-level values with the binding's `consumer.instanceCount` and `consumer.instanceIndex`. Check the documentation for your binder and Spring Cloud Stream version before configuring them.

Do not assign the same `instanceIndex` to multiple instances in a static partitioning scenario. Instances need unique indices and `instanceCount` must accurately reflect the total configured instances. If the system auto-scales without assigning stable indices, static partitioning can miss data or distribute overlapping data.

## 5. Partitioning on the producer and consumer sides

For data to be partitioned by key, both producer and consumer must be configured accordingly. The producer determines each message's key and target partition. The consumer receives data from the partitions assigned to it by the broker or binder.

Example producer using `customerId` as the partition key:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.events
          producer:
            partition-key-expression: payload.customerId
            partition-count: 6
~~~

Spring Cloud Stream computes the partition key from the message using the declared expression. By default, the partition selector typically hashes the key to select a value from `0` to `partitionCount - 1`. Messages with the same key are sent to the same partition given the same algorithm and partition count.

Choosing `customerId` ensures events for the same customer tend to land in the same partition, preserving relative per-customer order within that partition. If keys are skewed, one partition may receive far more data than others and become a hotspot.

The partition count configured on the producer must be compatible with the actual topic. With Kafka, the binder may use `partitionCount` as a hint when provisioning topics; existing topics still need enough partitions. With RabbitMQ, the binder uses the partition count to create corresponding queues and routing keys. With Pulsar, the partition count belongs to the partitioned topic configuration and must be created/provisioned according to binder support.

## 6. Differences across Kafka, RabbitMQ, and Pulsar

Binders share the Spring Cloud Stream abstraction, yet how brokers distribute data differs. Do not take a Kafka recipe and apply it verbatim to RabbitMQ or Pulsar.

### 6.1. Kafka: groups divide partitions

A Kafka topic has a defined number of partitions. Consumers in the same group divide partitions; different groups can read the same topic independently. When consumers join or leave a group, Kafka performs a rebalance to reassign partitions.

- Increasing replicas or concurrency can increase consumer members.
- Consumer members exceeding the partition count will leave members idle.
- One consumer member can receive multiple partitions.
- Increasing partitions can increase parallel read capacity, though key routing, metadata overhead, and per-key ordering must be considered.

In most cases, let Kafka auto-rebalance handle distribution among consumer members. Only use `instanceCount`/`instanceIndex` for Kafka when binder configuration requires static partition assignment or `autoRebalanceEnabled` is disabled.

### 6.2. RabbitMQ: queues and competing consumers

The RabbitMQ binder by default maps a destination to an exchange. For each consumer group, the binder creates a queue bound to that exchange. Each consumer instance has its own consumer reading from the group's queue. Multiple consumers on the same queue compete for messages; the broker dispatches messages to available consumers based on state and prefetch configuration.

In non-partitioned streams, there is no "one partition per consumer" concept like in Kafka. Increasing instances or concurrency can increase the number of consumers concurrently reading the queue, though throughput still depends on prefetch, unacknowledged message count, processing duration, and queue capacity.

RabbitMQ does not support native Kafka-style partitions. The Rabbit binder simulates partitioning by creating a separate queue per partition and using routing keys with a partition index. In this scenario:

- The producer must enable partitioning and choose a partition key.
- The consumer must mark the binding as partitioned.
- Each instance must have the right `instanceIndex` and `instanceCount`.
- The Rabbit binder's partitioned queue model does not support dynamic scaling the way Kafka groups auto-rebalance; instances and partitions must be planned in advance.

Illustrative three-partition example for RabbitMQ:

~~~yaml
spring:
  cloud:
    stream:
      instanceCount: 3
      bindings:
        publishOrder-out-0:
          destination: orders.events
          producer:
            partition-key-expression: payload.customerId
            partition-count: 3
        processOrder-in-0:
          destination: orders.events
          group: order-workers
          consumer:
            partitioned: true
~~~

Each consumer instance uses the same `instanceCount: 3` but a distinct `instanceIndex`:

~~~yaml
spring:
  cloud:
    stream:
      instanceIndex: 0
      instanceCount: 3
~~~

The second instance sets `instanceIndex: 1`, and the third sets `instanceIndex: 2`. Do not run three replicas with the same index. If frequent dynamic scaling is required, consider the standard competing-queue model or a design better aligned with binder capabilities instead of static partition mapping.

### 6.3. Pulsar: topic partitions and subscription types

Pulsar separates topics from subscriptions. A topic can be partitioned into multiple segments; a subscription tracks consumption position and governs how messages are distributed to consumers sharing the same subscription name.

Common subscription types:

| Subscription type | Distribution behavior | Ordering notes |
|---|---|---|
| Exclusive | Only one consumer can connect to the subscription | One consumer receives the entire subscription |
| Failover | Multiple consumers allowed, but one active consumer per distribution scope; others stand by | With partitioned topics, partitions can be assigned to different active consumers; per-partition order is preserved per Pulsar rules |
| Shared | Multiple consumers receive messages round-robin/balanced | No stream-wide ordering guarantees |
| Key_Shared | Multiple consumers; messages with the same key are delivered to the same consumer at a time | Supports per-key ordering when producers send appropriate keys/ordering keys |

Different subscription names create independent consuming streams, similar to fan-out across applications. Multiple consumers in the same subscription share load or provide failover depending on subscription type. Therefore, counting consumers without considering subscription type can lead to wrong parallelism estimates.

With Pulsar, partition count and subscription type are two separate choices: partitioning determines which segment of the topic a message is written to; subscription type determines which consumer receives the message. Verify Spring Cloud Stream Pulsar binder and Spring for Apache Pulsar configuration for your version; do not assume all Kafka binder concurrency properties carry identical semantics.

## 7. One binding, multiple bindings, and multiple groups

An application can have multiple input bindings. Each binding is a separate logical consuming stream with its own destination, group, and concurrency. For example, one Function may consume orders from `orders.events` and another Function may consume metrics from `metrics.events`.

| Component | Meaning |
|---|---|
| Two input bindings | Two logical input ports; each port can read its own destination |
| One input binding, concurrency 4 | One input port with four internal consumers per instance per binder |
| One group, three instances | Three replicas jointly processing one group stream |
| Three different groups | Three independent consuming streams; each group can receive all messages |

For example, if three services—inventory, analytics, and notifications—all need to process every order event, each service should have its own group. If three instances of the same inventory service just need to share work, they use the same `inventory-service` group.

Do not add more groups to speed up a single consumer group. Adding groups creates extra copies of the work for each group, which can increase read and processing load across the system.

## 8. How to choose partition count and concurrency

Choosing the partition count should be based on expected load and processing limits, not solely on current pod count.

### 8.1. Estimating parallelism needs

Suppose the system receives 1,200 events per second. One consumer worker steadily handles 100 events per second under target load conditions. The initial estimated parallelism needed is:

\[
\left\lceil \frac{1200}{100} \right\rceil = 12\ \text{workers}
\]

If using Kafka and you want one consumer member per partition in the initial setup, you might consider 12 partitions or more to leave room for growth. However, this calculation is only an estimate; measure under realistic load because I/O, batching, key skew, and broker round-trips can change throughput.

### 8.2. Choosing replicas and concurrency

Suppose the target is 12 consumer members:

| Option | Instances | Concurrency/instance | Total consumers |
|---|---:|---:|---:|
| A | 3 | 4 | 12 |
| B | 4 | 3 | 12 |
| C | 6 | 2 | 12 |
| D | 12 | 1 | 12 |

These options have the same total consumer count yet different operational characteristics:

- More instances distribute CPU, memory, and process failures; in return, they increase connection count and deployment overhead.
- Higher concurrency per instance leverages multiple threads within one process; thread safety, connection pools, and CPU resources must be verified.
- More consumers than partitions leave idle consumers in Kafka or fail to add useful parallelism.
- A hot partition can slow down one consumer even while other consumers sit idle.

### 8.3. Leaving room for growth

In Kafka, partition counts are usually difficult to reduce after creation. You can increase partitions, but doing so can change how keys map to partitions and disrupt relative per-key ordering when the partition count changes. Plan ahead for growth, yet avoid creating unnecessarily large partition counts since each partition consumes broker resources and metadata.

In RabbitMQ partitioned mode, changing partition count and instance count must be coordinated with queue topology and instance indices. In Pulsar, creating partitioned topics and changing partition counts must follow Pulsar's and the binder's topic administration procedures.

## 9. Impact on ordering and consistency

Partitioning is commonly used to process in parallel while preserving order for related records. That holds only within the scope guaranteed by the broker:

- Kafka preserves order within each partition, without guaranteeing global order across multiple partitions of a topic.
- RabbitMQ preserves enqueue/delivery order under specific queue and consumer conditions, yet multiple consumers processing in parallel may finish in a different order. Partitioned queues can use routing keys to group data by key.
- Pulsar offers subscription types with different ordering guarantees; `Shared` prioritizes load sharing with no ordering guarantees, whereas `Key_Shared` routes messages with the same key to one consumer according to its rules.

If every update to the same account must be processed sequentially, pick `accountId` as the key and ensure producer, broker, and consumer use consistent routing. If you only need parallel processing with no per-key ordering requirement, you can pick a simpler load-sharing mechanism.

Do not assume one partition equals one thread or one instance. A partition can be handled by a different consumer after a rebalance; one consumer can own multiple partitions; and one instance can host multiple consumer threads.

## 10. Monitoring to tell whether partitions or consumers are lacking

Looking at pod counts alone is insufficient to evaluate processing capacity. Monitor both application and broker metrics:

| Metric | Diagnostic meaning |
|---|---|
| Application instance count | Confirms how many replicas are running |
| Consumer concurrency | Confirms how many internal consumers are configured per binding |
| Consumer group members | Actual number of consumers participating in the group |
| Partition assignment | Which partition is assigned to which consumer; whether any consumers are idle |
| Consumer lag per partition | Which partition is lagging or accumulating backlog |
| Processing latency and throughput | Whether consumers process faster or slower than arrival rate |
| Rebalance count/time | How often the group has to redistribute partitions |
| Rabbit queue depth and unacked messages | Whether the queue is backlogged or consumers fetched messages without finishing them |
| Pulsar subscription backlog and consumer count | Whether the subscription has backlog and how many consumers participate |

Indicators to look for:

- Lag rising across all partitions: total consumer capacity may be lower than publish rate.
- Lag rising on only one partition: possible key skew, one slow consumer, or heavier payloads on that partition.
- Consumer members present with no assigned partitions: consumer count exceeds partition count or group assignment has not stabilized.
- Long RabbitMQ queue with few consumers: check concurrency, prefetch, connection errors, and processing speed.
- Growing Pulsar backlog despite many consumers: check subscription type, partition count, key distribution, and acknowledgments.

## 11. Common misconceptions

**Adding instances will always increase throughput.** With Kafka, if there are fewer partitions than consumer members, excess consumers receive no partitions. Check partition assignments before adding replicas.

**Concurrency is the partition count.** Concurrency spawns additional internal consumers per instance. Partition count is a broker data structure. The two numbers can differ.

**One instance has only one consumer.** One instance can open multiple consumers via `consumer.concurrency`, if supported by the binder.

**Each consumer reads only one partition.** In Kafka, one consumer can be assigned multiple partitions. The important rule is that one partition is never assigned to two consumer members of the same group at the same time.

**Each consumer group is a partition.** A group is a consumption identity; a partition is a slice of data. One group can read many partitions.

**Multiple groups share load for the same job.** Independent groups normally receive copies of the data stream. To share load across instances of one service, make them share the same group.

**RabbitMQ has native partitions like Kafka.** The Rabbit binder simulates partitions using dedicated queues and routing keys; scaling and instance assignment differ from Kafka.

**Pulsar Shared always preserves per-key order.** Shared does not guarantee ordering. If you need parallel distribution while preserving per-key order, consider `Key_Shared` and proper key configuration.

## 12. Process for sizing instances, consumers, and partitions

When deploying a new input binding or scaling processing capacity, follow this process:

1. Identify the destination and consumer group. Clarify how many independent services need to receive the same events.
2. Measure incoming message rate, average processing time, and target load per consumer.
3. Estimate the number of consumer workers needed for target throughput.
4. Choose instance count and `consumer.concurrency` to achieve the desired consumer count.
5. Check actual partition count and binder distribution capabilities.
6. With Kafka, review partition assignment and auto-rebalance; with RabbitMQ, distinguish standard queues from partitioned queues; with Pulsar, pick the right subscription type.
7. Choose a partition key if per-entity ordering or grouping related data is required.
8. Run load tests and observe lag, queue depth, processing latency, rebalances, and resource utilization.
9. Adjust replicas, concurrency, or partition count based on measured results.
10. Document scaling rules and binder limits to avoid scaling instances beyond useful parallelism.

For example, a Kafka service with six partitions running three instances at concurrency two already has six consumer members in one group. If lag increases uniformly, you may need to boost per-consumer processing speed, optimize logic, or add partitions before adding replicas. If lag is concentrated on a single partition, inspect key distribution and processing duration for that partition's data.

## Official References

- [Spring Cloud Stream - Partitioning](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-partitioning.html): configuring partition key, partition count, instance index, and instance count.
- [Spring Cloud Stream - Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html): `consumer.concurrency`, `partitioned`, `instanceCount`, and `instanceIndex` properties.
- [Spring Cloud Stream - Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder.html): consumer configuration and Kafka binder partition distribution mechanics.
- [Spring Cloud Stream - RabbitMQ Binder](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html): mapping destinations/groups to exchanges/queues and partitioning via dedicated queues.
- [Spring Cloud Stream - Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html): topic connections, binder, and Pulsar configuration.
- [Apache Pulsar - Messaging Concepts](https://pulsar.apache.org/docs/4.0.x/concepts-messaging/): subscription types, partitioned topics, and message distribution to consumers.
