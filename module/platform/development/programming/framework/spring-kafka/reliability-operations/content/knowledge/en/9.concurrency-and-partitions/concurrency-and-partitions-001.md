# Choosing Concurrency Based on Partition Count

## 1. What Does Concurrency Mean in Spring Kafka?

In Spring Kafka, the concurrency of a listener container determines the number of Kafka consumers the container creates for parallel reading. Each consumer belonging to the same consumer group is assigned one or more partitions of the subscribed topics by Kafka.

For example, a listener container with a concurrency of 3:

- Spring creates three container-managed consumer instances.
- The consumers share the listener's group ID.
- Kafka distributes partitions among the three consumers according to the partition assignor.
- Each consumer processes records from the partitions assigned to it.

Concurrency is consumer-side parallelism. It does not create additional partitions, nor does it allow a single partition to be processed concurrently by multiple consumers in the same group. Therefore, the partition count is a key upper bound on the parallelism of a consumer group.

For a topic with P partitions and a total of C consumers in the same group:

- If C is less than P, a single consumer is typically assigned multiple partitions.
- If C equals P, the group can have one consumer per partition.
- If C is greater than P, some consumers are not assigned any partitions and do not contribute additional parallel reading capacity for that topic.

The actual consumer count must be calculated across all application instances participating in the same group, not just the concurrency of a single JVM.

## 2. Relationship Between Partitions and Consumers

### 2.1. Partitions Are Kafka's Unit of Parallelism

A topic is divided into independent partitions. Kafka guarantees record ordering within a single partition, but does not guarantee global ordering across multiple partitions.

A consumer group divides the partitions among its consumer members. At any given time, a partition is assigned to at most one consumer within the same group. Different consumer groups can read the same partition independently.

Example of a topic with 6 partitions:

~~~text
Topic orders
  P0  P1  P2  P3  P4  P5

Consumer group orders-service
  Consumer A -> P0, P1
  Consumer B -> P2, P3
  Consumer C -> P4, P5
~~~

Three consumers can read three sets of partitions in parallel. Each consumer can process records from its assigned partitions in its poll loop.

If there is only one partition:

~~~text
Topic orders
  P0

Consumer group orders-service
  Consumer A -> P0
  Consumer B -> idle
  Consumer C -> idle
  Consumer D -> idle
~~~

Even though the container creates four consumers, only one consumer receives the partition. Increasing concurrency to 4 does not make P0 get processed by four consumers simultaneously.

### 2.2. One Consumer Can Receive Multiple Partitions

A partition does not require a dedicated consumer. One consumer can own multiple partitions and poll records from all of them.

Example of a topic with 8 partitions and a group with 2 consumers:

~~~text
Consumer A -> P0, P1, P2, P3
Consumer B -> P4, P5, P6, P7
~~~

The maximum parallelism of the group is still limited by the partition count, but having fewer consumers than partitions does not cause data loss. Each consumer simply becomes responsible for more partitions and needs sufficient capacity to handle the total assigned load.

### 2.3. Excess Consumers Do Not Increase Throughput

If the number of consumers exceeds the number of partitions, the excess consumers can still connect to brokers, participate in group coordination, and send heartbeats, but they have no partitions to read. They do not make the topic process any faster.

Excess consumers also add overhead:

- Client-side threads, sockets, and buffers.
- Heartbeats and group coordination.
- Heap, CPU, and monitoring resources.
- Time spent joining or leaving the group during deployments and rebalances.

Therefore, concurrency should start from the partition count and be tuned according to actual load, rather than setting a large number simply expecting more threads to always be faster.

## 3. Calculating Total Concurrency Across the Entire Consumer Group

### 3.1. Concurrency Within a Single Instance

Suppose an application has a listener container with a concurrency of 3. The container creates three consumers in the same group.

~~~yaml
spring:
  kafka:
    listener:
      concurrency: 3
~~~

If the topic has 6 partitions, each consumer can receive roughly 2 partitions depending on the assignor. If the topic has only 2 partitions, one consumer can receive the first partition, another consumer receives the second partition, and the remaining consumer stays idle.

### 3.2. Multiple Application Replicas

In production, a service typically runs multiple pods or instances. Each instance creates its own concurrency for the listener container.

The formula to use for a listener container in the same group:

~~~text
Total consumers in the group
    = application replicas × concurrency per replica

Maximum consumers with active partitions
    <= min(total consumers in the group, assigned partitions)
~~~

For example, with 3 replicas, each configured with concurrency 2:

~~~text
Replica A: 2 consumers
Replica B: 2 consumers
Replica C: 2 consumers

Total consumers in group = 3 × 2 = 6
~~~

If the topic has 6 partitions, the group can use all 6 consumers. If the topic has only 4 partitions, at most 4 consumers receive partitions and at least 2 consumers remain idle.

| Replicas | Concurrency per replica | Total consumers | Partitions | Maximum active consumers |
|---:|---:|---:|---:|---:|
| 1 | 3 | 3 | 6 | 3 |
| 2 | 3 | 6 | 6 | 6 |
| 3 | 3 | 9 | 6 | 6 |
| 2 | 2 | 4 | 8 | 4 |
| 4 | 1 | 4 | 4 | 4 |

This table assumes one topic, one listener group, and an assignment that can distribute partitions across consumers. With multiple topics, you must count the total subscribed partitions and also examine the assignor.

### 3.3. Distinguishing Concurrency from Group Count

If two applications use the same group ID, their consumers share the partitions. The total concurrency of both applications must be calculated together.

If two applications use different group IDs, each group tracks its own independent progress and each group can receive all partitions of the topic. In that case, both applications can read the same records, but they do not increase the parallelism of a single group; they create two independent consumption streams.

This is critical when deploying a new service. Changing the group ID can turn the application into a new consumer group, re-reading history or starting from the end of the log depending on `auto.offset.reset`.

## 4. Choosing Concurrency Based on Partition Count

### 4.1. Single Topic, Single Listener Group

For a topic with P partitions, setting total consumers in the group close to P is a reasonable starting point if the goal is to utilize full partition-level parallelism.

| Partition count | Suggested initial total consumers | Typical distribution |
|---:|---:|---|
| 1 | 1 | One consumer reads the single partition |
| 2 | 2 | One consumer per partition |
| 4 | 2 | Two partitions per consumer |
| 6 | 3 | Two partitions per consumer |
| 8 | 4 | Two partitions per consumer |
| 12 | 6 | Two partitions per consumer |
| 12 | 12 | One consumer per partition |

This is a starting point for experimentation, not a mandatory rule. If the listener does lightweight work and throughput is low, fewer consumers than partitions may suffice. If processing is heavy and downstream systems can handle the load, increasing consumers toward the partition count can raise throughput.

If total consumers exceed P, excess consumers do not increase parallelism for that topic. If total consumers are below P, each consumer owns more partitions and the load must be handled across fewer consumers.

### 4.2. One Consumer per Partition Is Not Always the Goal

A single consumer can read multiple partitions effectively if the listener processes fast, batching is appropriate, and downstream has sufficient capacity. Setting one consumer per partition increases thread and connection counts, and can also increase load on the database.

You should only increase concurrency when there is evidence that the consumer is the bottleneck. If consumer lag is low and the listener processes quickly, adding consumers may bring no benefit.

Conversely, if lag grows steadily, consumer CPU is high, and the listener is the limiting stage, increasing concurrency can help distribute load across more consumers. However, check downstream systems first, because adding consumers may simply overload the database or HTTP services faster.

### 4.3. When Partition Count Is Insufficient

If a topic has only 2 partitions but requires 8 consumers processing independently in the same group, raising concurrency to 8 will not overcome that limit. You need to re-evaluate the topic's partition count or pipeline design.

Increasing the partition count is a topic-level change, not merely an application configuration change. Consider the following:

- Key-to-partition mapping may change.
- Key-based ordering may be affected between old and new records.
- Brokers require additional resources for partitions and replicas.
- The consumer group will have to rebalance when partition metadata changes.
- A higher partition count increases metadata and operational overhead.

Do not increase partitions just to match a concurrency number if the workload does not need that level of parallelism.

## 5. Choosing Concurrency When a Listener Subscribes to Multiple Topics

When a consumer subscribes to multiple topics, parallelism depends on the total partition count across the topics and the partition assignor.

Example of a listener subscribing to three topics:

~~~text
orders:       3 partitions
payments:     3 partitions
shipments:    3 partitions

Total:        9 partitions
~~~

In theory, the group can have up to 9 consumers assigned partitions. However, actual distribution also depends on the assignor and the partition count of each individual topic.

### 5.1. Impact of RangeAssignor

With `RangeAssignor`, assignment is calculated independently per topic. When the number of consumers exceeds the partition count of individual topics, some consumers may receive no partitions from any topic even when the sum of partitions across all topics exceeds the consumer count.

For example, three topics each with 5 partitions and a group with 15 consumers:

~~~text
orders:       5 partitions
payments:     5 partitions
shipments:    5 partitions
Total:       15 partitions

RangeAssignor may assign per topic:
Consumer 0-4: receive partitions from each topic
Consumer 5-14: receive no partitions
~~~

Because the assignor divides each topic among consumers by range, do not simply sum partitions across multiple topics and assume every consumer will be active.

### 5.2. RoundRobinAssignor and CooperativeStickyAssignor

`RoundRobinAssignor` distributes partitions in round-robin fashion across consumers over all subscribed topics, which can utilize consumers better in certain multi-topic topologies.

`CooperativeStickyAssignor` combines balanced distribution with stable assignment retention and cooperative rebalancing. It can also help avoid leaving a subset of consumers idle due to per-topic assignment, depending on actual subscriptions and topology.

Do not switch assignors solely to fix an idle symptom without inspecting the actual assignment. Check which partitions are assigned to each member and test on the same topology before changing it.

### 5.3. When Listeners Subscribe to Different Topics

If an application has multiple `@KafkaListener`s with different subscriptions, each listener container has its own concurrency. The application's total consumers and resources are the sum across all containers, while partition assignment is shared only among consumers with the same group ID and compatible subscriptions.

For example:

- Listener A reads `orders` with group `billing-service`.
- Listener B reads `payments` with group `payment-service`.

The two groups are independent, each tracking its own progress. Do not add the partitions of the two topics together to derive a single combined concurrency limit for these two groups.

If two listeners share `billing-service` and both subscribe to `orders`, they participate in the same group; total consumers from both containers must be counted together. Using multiple containers for the same group should be intentional because it can make assignment and concurrency harder to predict.

## 6. Configuring Concurrency in Spring Kafka

There are multiple ways to configure concurrency. Choose an approach that fits your application structure and ensure the service is using the intended listener container factory.

### 6.1. Spring Boot application.yml

Default configuration for listener containers created by Boot:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: orders-service
      enable-auto-commit: false
    listener:
      concurrency: 3
      ack-mode: record
~~~

`spring.kafka.listener.concurrency` sets the default concurrency for the listener container factory configured by Spring Boot. It does not automatically change the topic's partition count.

If a listener needs a different concurrency, you can declare it directly on the annotation or create a dedicated factory.

### 6.2. Declaring Concurrency in @KafkaListener

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-service",
    concurrency = "3"
)
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
~~~

The annotation's `concurrency` attribute is a string. This value instructs the container to create the corresponding number of consumers for that listener endpoint. If the application runs multiple replicas, each replica creates consumers according to that endpoint's configuration.

Avoid setting different values simultaneously in Boot defaults, the factory, and the annotation without understanding precedence. Verify the effective concurrency in startup logs/container metrics.

### 6.3. Configuring via ConcurrentKafkaListenerContainerFactory

When a dedicated factory is needed for a group of listeners:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        orderKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory
        ) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);

    return factory;
}
~~~

Attach the factory to the listener:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-service",
    containerFactory = "orderKafkaListenerContainerFactory"
)
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
~~~

This factory allows separating concurrency, acknowledgment mode, error handler, and container properties by listener type.

If multiple listeners use different factories with the same group ID, the group's total consumers are the sum of effective concurrency across all containers and all replicas. Avoid accidentally creating more concurrency than the partition count simply because each factory was configured independently.

## 7. Concurrency and Partition Count Across Multiple Replicas

Suppose the `orders` topic has 12 partitions. The application runs on 3 pods and each pod is configured with concurrency 2.

~~~text
Topic: 12 partitions
Pods:  3
Per-pod concurrency: 2

Total consumers = 3 × 2 = 6
Average partitions per active consumer = 12 / 6 = 2
~~~

Each consumer can receive roughly two partitions if the assignor distributes evenly. If each pod increases concurrency to 4:

~~~text
Pods: 3
Per-pod concurrency: 4

Total consumers = 3 × 4 = 12
Average partitions per active consumer = 12 / 12 = 1
~~~

At this point the group can use one consumer per partition. If increased to concurrency 6 per pod:

~~~text
Pods: 3
Per-pod concurrency: 6

Total consumers = 3 × 6 = 18
Partitions = 12

At most 12 consumers receive a partition.
At least 6 consumers remain idle.
~~~

Options table for this topology:

| Replicas | Concurrency per replica | Total consumers | Minimum idle consumers |
|---:|---:|---:|---:|
| 3 | 1 | 3 | 0 |
| 3 | 2 | 6 | 0 |
| 3 | 4 | 12 | 0 |
| 3 | 6 | 18 | 6 |

The minimum idle numbers assume a single topic with 12 partitions and all consumers subscribing to that topic. With multi-topic subscriptions or assignor constraints, observe the actual assignment.

During autoscaling, the consumer count changes with the replica count. If per-pod concurrency already equals the partition count, most new consumers will be idle while still forcing the group to rebalance. You can set per-pod concurrency based on a group-wide consumer budget and cap replicas accordingly.

## 8. Factors Beyond Partition Count to Consider

Partition count sets an upper bound on parallelism within a group, but does not by itself determine optimal concurrency. You must consider processing load and consumer resources.

### 8.1. Processing Time per Record

If a listener takes 5 ms to process a record, one consumer can handle many records per second. If a listener takes 500 ms due to database queries or API calls, one consumer has significantly lower throughput.

Measure these metrics:

- Average, p95, and p99 processing duration.
- Incoming record rate to the topic.
- Record rate processed by consumers.
- Consumer lag per partition.
- Wait time on databases and external services.

If CPU has headroom and the listener spends most time waiting on I/O, adding concurrency can increase throughput up to downstream limits. If CPU is already saturated, adding consumers can increase context switching and contention.

### 8.2. Database and Downstream Capacity

Each consumer can generate additional requests to databases, HTTP services, caches, or other systems. Before increasing concurrency, verify:

- Whether the database connection pool has enough connections.
- Whether downstream services impose request limits or rate limits.
- Whether database transactions hold locks for long durations.
- Whether external APIs experience increased latency or return 429/5xx under higher load.
- Whether enough threads and connections remain for other parts of the application.

If the database can only sustain 10 concurrent transactions, configuring 30 consumers can cause queuing and timeouts instead of speeding things up. Concurrency must match end-to-end processing capacity, not just partition count.

### 8.3. CPU, Heap, and Threads

Each consumer typically has its own processing thread in a concurrent container plus client resources such as network buffers, metadata, and heartbeats. Increasing concurrency increases thread count and management overhead.

Evaluate:

- CPU core count and CPU utilization.
- Heap usage, garbage collection, and object allocation rate.
- Broker connection count.
- Application thread pools and connection pools.
- Resources reserved for web requests or schedulers in the same JVM.

There is no fixed rule that concurrency must equal CPU core count. I/O-bound listeners may use more consumers than cores; CPU-bound listeners may peak near or below core count. Measure under realistic load.

### 8.4. Poll Size and Processing Duration

`max.poll.records` limits the number of records returned in a single poll. It does not create additional consumers and is not a substitute for concurrency.

If each poll returns too many records, the listener may take too long to process and exceed `max.poll.interval.ms`, triggering a rebalance. If set too low, poll and commit overhead may increase.

Tune these together:

- Concurrency.
- `max.poll.records`.
- Record/batch processing time.
- `max.poll.interval.ms`.
- Batch listener versus record listener.
- Acknowledgment mode and error handler.

The goal is to keep the consumer polling within limits without letting batches grow too large for the allowed processing time.

## 9. Concurrency, Ordering, and Key Distribution

### 9.1. Ordering Is Guaranteed Only Within a Single Partition

If events for the same order ID use order ID as the key, Kafka typically routes them to the same partition. One consumer in the group processes that partition and record order is preserved by offset.

Increasing concurrency does not cause events in the same partition to be processed simultaneously by multiple consumers in the same group. This is necessary to preserve basic partition ordering.

~~~text
orders partition P2:
Order-42 Created -> Order-42 Paid -> Order-42 Shipped

One consumer owns P2
        |
        v
Process in offset order
~~~

If the listener hands work off to a thread pool for asynchronous execution, side-effect order can break even though Kafka still delivers records in order. When business ordering matters, you must manage completion ordering in the application or keep processing sequential per partition/key.

### 9.2. Hot Partitions and Key Skew

A high partition count does not guarantee evenly distributed load. If most records share the same key or a few hot keys dominate, they can concentrate in a single partition.

For example:

~~~text
P0: 80% traffic
P1:  5% traffic
P2:  5% traffic
P3:  5% traffic
P4:  5% traffic
~~~

Increasing concurrency from 5 to 10 will not split P0 across two consumers in the same group. One consumer still bears most of the hot partition's load.

Inspect per-partition record rates and lag. If key distribution is skewed, consider changing the key strategy, splitting workloads, or increasing partitions with an appropriate design. Do not change keys arbitrarily if ordering per aggregate is required.

### 9.3. A Single Partition Can Be the Throughput Limit

If a hot partition already saturates the processing capacity of one consumer, increasing concurrency cannot make that partition faster. Possible solutions include:

- Optimizing listener processing time.
- Reducing round trips to databases/downstream services.
- Batching operations appropriately.
- Redesigning the key if the business allows distributing a single aggregate.
- Splitting the data stream into separate topics/partitions when semantics allow changes.

Splitting one key across multiple partitions can break ordering for that key. Decisions must be based on business requirements, not throughput alone.

## 10. Batch Listeners and Concurrency

Spring Kafka supports record listeners and batch listeners. Concurrency determines the number of consumers; listener type determines how records are passed to the handler method.

### 10.1. Record Listener

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-service",
    concurrency = "4"
)
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
~~~

Each listener invocation processes one record. One consumer can receive records from multiple assigned partitions. Concurrency creates multiple consumers so partitions are processed in parallel.

### 10.2. Batch Listener

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-service",
    concurrency = "4"
)
public void onOrders(List<OrderCreated> events) {
    orderService.processBatch(events);
}
~~~

With a batch listener, a single method invocation receives a group of records from a poll. A batch can contain records from multiple partitions. You must control error handling, commits, and per-partition ordering within the batch.

Batch listeners can reduce overhead when downstream supports bulk operations. However, larger batches also lengthen processing time per poll, increasing the risk of exceeding `max.poll.interval.ms` and widening the retry scope on failure.

Concurrency and batch size address two different aspects:

- Concurrency increases the number of consumers processing partitions in parallel.
- Batch size adjusts the number of records processed in one poll or one listener invocation.

Do not increase both at the same time without measuring, because it becomes difficult to tell which change improved throughput or caused errors.

## 11. Choosing Concurrency When Using Multiple Listener Containers

An application may have multiple `@KafkaListener`s, each using its own topic, group ID, or container factory.

Example:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "billing-service",
    concurrency = "3"
)
public void onOrder(OrderCreated event) {
    billingService.process(event);
}

@KafkaListener(
    topics = "payments",
    groupId = "payment-service",
    concurrency = "2"
)
public void onPayment(PaymentCompleted event) {
    paymentService.process(event);
}
~~~

The two listeners have different group IDs, so their concurrencies are independent. The application creates a total of 5 consumers across both containers per replica. When running multiple replicas, multiply each container's concurrency by the corresponding replica count.

If they share the same group ID and subscription, consumers from multiple listener containers can join the same group. Calculate the total consumer count and inspect assignments rather than looking only at each annotation individually.

If listeners have different workloads, use separate container factories to tune concurrency, ack mode, error handler, and consumer properties independently. An I/O-heavy listener may require a different concurrency than a CPU-bound listener.

## 12. Process for Determining the Right Concurrency

Follow a step-by-step process to avoid over-provisioning consumers or overloading downstream systems.

### Step 1: Identify the Topology

Record:

- Topics the listener subscribes to.
- Partition count of each topic.
- Listener group ID.
- Application replica count.
- Concurrency per replica.
- Partition assignor in use.
- Other listener containers sharing the same group ID.

Calculate the expected total consumers across the group before changing configuration.

### Step 2: Measure Current Load

Monitor:

- Producer record rate.
- Consumer record rate.
- Total and per-partition consumer lag.
- Processing duration p50/p95/p99.
- CPU, heap, and GC.
- Database connection usage and query latency.
- Downstream latency, errors, and rate limits.
- Rebalance count and rebalance duration.

If lag is low and processing duration is stable, there is no clear reason to increase concurrency.

### Step 3: Find Hot Partitions

Compare per-partition record rates and lag. If one partition has high lag while others are low, increasing overall concurrency may not help. Inspect key distribution and processing time on the hot partition.

### Step 4: Increase Gradually in Controlled Steps

Increase concurrency in small increments, such as from 2 to 3 or 4, and observe over the same load window. Do not jump straight from 2 to 20 without knowing database and JVM limits.

When running multiple replicas, adjust concurrency per replica or replica count so total consumers in the group do not exceed useful limits.

### Step 5: Compare Results

A concurrency increase is beneficial when:

- Consumer throughput increases.
- Consumer lag decreases or stabilizes at an acceptable level.
- Processing duration does not increase significantly.
- Database and downstream remain within limits.
- CPU, heap, and threads still have headroom.
- Rebalances do not spike abnormally.

If consumer count rises without changing throughput, look for bottlenecks in partition skew, downstream systems, or the listener before increasing further.

### Step 6: Document Operating Limits

Record the effective concurrency, maximum replicas, partition count, and metrics at peak load. When partition counts or workloads change, re-evaluate instead of keeping one value forever.

## 13. Quick Decision Table

| Observation | What to consider |
|---|---|
| Total consumers less than partitions, lag growing, downstream has headroom | Increase concurrency or replicas to utilize partitions |
| Total consumers equal partitions, lag still growing | Look for bottlenecks in listener, key skew, CPU, or downstream |
| Total consumers greater than partitions, many idle members | Reduce concurrency or replicas if no other workload needs them |
| One partition has high lag, others low | Investigate hot keys and load distribution; adding general consumers usually does not help |
| Database pool exhausted after increasing concurrency | Reduce consumers or scale database capacity in a controlled way |
| High CPU and CPU-bound listener | Optimize code; increasing concurrency may worsen contention |
| I/O-bound listener, CPU has headroom, downstream can handle it | Try increasing concurrency in small steps |
| Rebalances increase after autoscaling | Control replica count, rollout speed, and startup time |
| Multiple topics with some consumers idle under RangeAssignor | Inspect per-topic assignment and evaluate a suitable assignor |

## 14. Practical Calculation Examples

### Case A: 8 Partitions, 2 Replicas

The `orders` topic has 8 partitions. The application runs 2 replicas.

If each replica sets concurrency to 2:

~~~text
Total consumers = 2 × 2 = 4
Partitions = 8
Average = 2 partitions / consumer
~~~

This is a reasonable starting point if each consumer can handle two partitions and lag is not growing.

If concurrency is raised to 4 per replica:

~~~text
Total consumers = 2 × 4 = 8
Partitions = 8
Average = 1 partition / consumer
~~~

This can increase parallelism, but database and listener throughput must be measured.

### Case B: 4 Partitions, 4 Replicas

If each replica sets concurrency to 2:

~~~text
Total consumers = 4 × 2 = 8
Partitions = 4
Active consumers <= 4
Idle consumers >= 4
~~~

If there is no other reason to keep 8 consumers in the group, reducing concurrency to 1 per replica avoids creating surplus consumers.

### Case C: 12 Partitions, 1 Replica

A single JVM with concurrency 12 can create one consumer per partition. However, if the listener is CPU-bound and the machine has only 4 cores, 12 concurrent processing threads can cause contention.

Test concurrency 4, 6, and 12 under the same load, comparing throughput, lag, CPU, GC, and downstream metrics. The optimal level is the one that meets the SLA at an acceptable resource cost, not necessarily 12.

### Case D: 1 Hot Partition in an 8-Partition Topic

The topic has 8 partitions, but P3 receives most traffic due to key skew. Concurrency 8 still will not split P3 across multiple consumers in the same group.

Analyze keys, record sizes, and processing time on P3. If business rules allow, change key design or split streams. Otherwise, optimize the listener and downstream for the hot partition.

## 15. Common Configuration Mistakes

**Setting concurrency greater than partition count:** creates idle consumers, increases resource usage and group coordination without increasing topic throughput.

**Counting concurrency in only one pod:** ignores replica count and total group consumers. During autoscaling, total consumers can exceed partition count.

**Confusing concurrency with partition count:** concurrency does not create partitions and does not raise the parallelism limit of a single partition.

**Increasing concurrency to cure a hot partition:** a hot partition is still owned by only one consumer in the group at a time.

**Ignoring downstream systems:** adding consumers can exhaust database connection pools or trigger rate limits on external services.

**Using one concurrency for every listener:** different workloads may need different levels of parallelism; use separate container factories when needed.

**Confusing max.poll.records with concurrency:** max.poll.records controls how many records are returned per poll; it does not create more consumers.

**Not monitoring rebalances:** changing consumer counts alters assignments, which can cause disruptions during rollouts or autoscaling.

**Uncontrolled asynchronous processing:** a listener returning or committing offsets while background tasks are unfinished can cause ordering loss or duplicate processing.

**Assuming one consumer reads only one partition:** a single consumer can own multiple partitions; this is normal when consumer count is lower than partition count.

## 16. Production Operating Principles

- Calculate total consumers across the whole group as replicas multiplied by concurrency for each listener container.
- For a single topic, use partition count as the upper bound on active consumers in the group.
- Start with concurrency aligned to partition count and actual load; do not assume one consumer per partition is optimal by default.
- If subscribing to multiple topics, inspect assignment per topic and check the assignor in use.
- Monitor per-partition lag to detect hot partitions.
- Measure processing duration, CPU, heap, database pools, and downstream systems before raising concurrency.
- Adjust concurrency in small steps and compare throughput under identical load conditions.
- Coordinate concurrency with replica count, `max.poll.records`, `max.poll.interval.ms`, and acknowledgment mode.
- Preserve ordering per partition/key; manage carefully if the listener processes asynchronously.
- When parallelism beyond partition count is needed, evaluate increasing partitions or changing key design along with ordering and operational impacts.

Concurrency should be chosen based on partition count, replica count, and end-to-end processing capacity. Partitions set the parallelism limit within a consumer group; concurrency determines how many consumers compete to receive those partitions. Choosing the right level utilizes partitions effectively, keeps resources under control, and avoids creating excess consumers without gaining throughput.
