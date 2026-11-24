# Limits of Increasing Concurrency

In Spring Kafka, increasing concurrency lets a consumer group process more partitions in parallel by creating additional consumers and listener threads. However, more threads do not guarantee a proportional increase in throughput. Actual parallelism is bounded by the number of subscribed partitions, how Kafka distributes partitions, per-partition load, and the capacity of downstream components such as databases, APIs, CPU, and network.

Understanding these limits helps prevent over-provisioning consumers that receive no partitions, wasting system resources, increasing rebalances, and pressuring downstream systems without improving processing speed.

## 1. What Does Concurrency Mean in Spring Kafka?

A Kafka consumer processes records from the partitions assigned to it. Within a consumer group, each partition is assigned to at most one consumer member in a stable state. One consumer can own multiple partitions, but one partition cannot be split concurrently across multiple consumer members in the same group.

Spring Kafka provides ConcurrentMessageListenerContainer to run multiple consumers through a single listener container. The concurrency property determines how many child listener containers and corresponding consumers the container manages.

Example:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        kafkaListenerContainerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(4);
    return factory;
}
~~~

Listener using the factory:

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "orders-service",
        containerFactory = "kafkaListenerContainerFactory")
public void handle(OrderEvent event) {
    orderService.process(event);
}
~~~

The factory above creates four consumer members for the listener in group orders-service. Each consumer runs on its own thread and receives one or more partitions according to the group's assignment.

Concurrency can be set directly on the listener:

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "orders-service",
        concurrency = "4")
public void handle(OrderEvent event) {
    orderService.process(event);
}
~~~

The concurrency attribute on the listener allows configuring a dedicated consumer count for that listener. If using this attribute, be aware that it overrides the container factory's default concurrency so there is no confusion during operations.

With Spring Boot, a default can be set through configuration:

~~~yaml
spring:
  kafka:
    listener:
      concurrency: 4
~~~

Concurrency is the number of consumers managed by the listener container. It is not the partition count, the number of records processed simultaneously inside a single partition, or the number of network requests a Kafka producer can send.

## 2. Partitions Limit Maximum Parallelism

Suppose the orders topic has six partitions. A group can have at most six consumer members owning partitions of that topic at the same time. If the group has only three consumers, each consumer can receive two partitions. If the group has six consumers, each consumer can receive one partition. If the group has ten consumers, four consumers receive no partitions in a stable assignment.

~~~text
Topic orders has 6 partitions

3 consumers:
  Consumer A: P0, P1
  Consumer B: P2, P3
  Consumer C: P4, P5

6 consumers:
  Consumer A: P0
  Consumer B: P1
  Consumer C: P2
  Consumer D: P3
  Consumer E: P4
  Consumer F: P5

10 consumers:
  Consumer A-F: one partition per consumer
  Consumer G-J: no partitions
~~~

With a single topic and uniform subscriptions, the number of active consumers able to receive partitions cannot exceed the topic's partition count. Increasing concurrency from 6 to 10 in this example adds no parallel reading capacity because the topic only has six partitions.

This is the most important limit when scaling a consumer group: partitions are Kafka's fundamental unit of parallelism. One consumer can process multiple partitions, but a single partition cannot be split across two consumer members in the same group merely by raising concurrency.

If a listener subscribes to multiple topics, count the total partitions eligible under that subscription. However, individual members may subscribe to different topic sets, so eligible partitions and actual assignments must be evaluated per subscription. Do not use the total partition count of the entire cluster to predict concurrency for a single listener.

## 3. Calculating Total Consumers from Concurrency and Replicas

Concurrency applies per application instance. When running multiple replicas, total consumer members in the group equal the sum of concurrencies across listener instances participating in that group.

Example:

| Application replicas | Concurrency per replica | Total consumer members |
|---:|---:|---:|
| 1 | 4 | 4 |
| 2 | 4 | 8 |
| 3 | 4 | 12 |
| 5 | 4 | 20 |

Suppose the orders topic has 12 partitions and each replica runs with concurrency 4:

- One replica creates 4 consumers; all 4 can receive partitions.
- Two replicas create 8 consumers; 8 consumers can be active.
- Three replicas create 12 consumers; all 12 partitions can be utilized.
- Five replicas create 20 consumers; at most 12 consumers receive partitions, and the rest have no partitions.

Quick calculation model:

~~~text
Total consumers in the group
    = replicas × concurrency per replica

Consumers able to own partitions
    <= eligible partitions in subscription

Consumers without partitions
    = total consumers - assigned consumers
~~~

This is an upper bound for planning. Assignments may not be strictly balanced if subscriptions differ, multiple topics have different partition counts, or the assignor applies its own strategy.

Do not look only at concurrency in application.yml. When deploying on Kubernetes or with autoscaling, factor in the maximum number of replicas the system can create. For instance, concurrency 3 looks small, yet 10 replicas create 30 consumer members in the group.

## 4. Concurrency Does Not Split a Single Partition

Kafka preserves record ordering within each partition. Consumer group assignment grants an entire partition to one consumer member during a stable assignment. Consequently, if one partition has a high record arrival rate, increasing the consumer count in the group cannot split that single partition's load across multiple consumers.

Example of the orders topic with four partitions:

~~~text
P0:  1,000 records/sec
P1:    100 records/sec
P2:    100 records/sec
P3:    100 records/sec

Total: 1,300 records/sec
~~~

If the group has four consumers, each consumer receives one partition. The consumer owning P0 still has to process 1,000 records/sec. Adding four more consumers does not allow the P0 consumer to share work with a second consumer because P0 still has only one owner in the group.

This situation is commonly called partition skew or a hot partition. Partition counts may be split evenly, yet record volumes, payload sizes, and processing costs per partition vary widely.

Common causes:

- One key accounts for a large fraction of traffic.
- One customer or entity generates disproportionately many events.
- One event type has larger payloads or higher CPU processing cost than others.
- The producer uses an unsuitable key, concentrating many records into one partition.
- A partition has older backlogged data or downstream processes a subset of records more slowly.

When facing a hot partition, find the root cause of load distribution. You can redesign keys, add partitions, separate workloads into distinct topics, or decompose business flows into independent streams if ordering rules permit. Increasing concurrency alone will not resolve a bottleneck inside one partition.

## 5. Keys and Business Ordering Limit Scalability

Producers typically use the record key to determine the partition. Records with the same key usually land in the same partition, allowing Kafka to preserve their order within that partition.

For example, if orderId is the key:

~~~text
order-1001 -> P0: Created -> Paid -> Shipped
order-1002 -> P1: Created -> Cancelled
order-1003 -> P2: Created -> Paid
~~~

The consumer group can process partitions P0, P1, and P2 in parallel. However, records for order-1001 still need to be processed in order within P0 if business logic depends on that sequence.

Increasing concurrency does not allow processing Created, Paid, and Shipped from the same partition in parallel while automatically preserving business completion order. If a listener offloads work to an async executor, tasks may complete out of order even though records were polled in order. In that case, the application must coordinate ordering itself or ensure business logic tolerates out-of-order completion.

An overly hot key can also create a hot partition. If every event uses the same key, increasing the partition count will not distribute that key across multiple partitions under default partitioning. Splitting the load requires revisiting key semantics and ordering requirements.

Increasing a topic's partition count also requires caution. When partition count changes, key-to-partition mapping can change for new records. Old and new records for the same key can end up in different partitions, breaking continuous order across the expansion window. Assess this impact before adding partitions to a topic with key-ordering requirements.

## 6. Downstream Systems Can Become the Bottleneck

Kafka can deliver records faster than the application processes or persists results. If the listener depends on a database, REST API, payment system, or another service, overall throughput is limited by the slowest component in the chain.

Example:

~~~text
Kafka partitions
       |
       v
Consumer listeners
       |
       v
Database connection pool
       |
       v
Database
~~~

Suppose each consumer can handle 500 records/sec, yet the database can only sustain 1,500 transactions/sec total. Raising consumers from 3 to 8 can cause many requests to wait on connections or database locks. Throughput stops scaling proportionally, while latency and timeout errors rise.

Common downstream limits:

- Database connection pool lacks enough connections for the number of listener threads.
- Database is constrained by CPU, IOPS, lock contention, or transaction duration.
- REST API enforces rate limits or concurrent request caps.
- Downstream service has a small thread pool or saturated internal queues.
- Network bandwidth or TLS connection setup becomes significant overhead.
- Cache misses, unoptimized queries, or large payloads inflate processing time.

If each consumer holds a database connection while processing, more consumers may require a larger pool size. However, enlarging the connection pool does not make the database faster; it can subject the database to more concurrent transactions than optimal.

Before increasing concurrency, measure listener processing time and downstream latency. If the listener is already waiting on the database, adding consumers simply moves the queue from Kafka to the database.

## 7. CPU, Memory, and Thread Overhead

Each consumer member maintains its own state, network activity, buffers, and execution thread. Increasing concurrency increases the threads and resources the JVM must manage.

Costs that can grow include:

- Thread stack memory.
- Consumer metadata, fetch state, and network buffers.
- Serialization/deserialization overhead.
- CPU for polling, callbacks, logging, and record handling.
- Garbage collection from more objects and batches existing concurrently.
- Context switching when too many threads are runnable.
- Network connections and concurrent requests to brokers.

If the application is CPU-bound, adding consumer threads can lengthen per-thread processing time due to CPU contention. If heap or GC is already a bottleneck, more consumers and batches can worsen the problem.

Do not treat one thread per consumer as free. Check container CPU/memory limits, heap, thread count, GC pauses, and CPU utilization before choosing concurrency.

## 8. Rebalances and the Cost of Adding Consumers

When increasing concurrency or replica count, new consumers join the group. The group must rebalance to redistribute partitions. During a rebalance, processing on some partitions may pause, causing consumer lag to rise.

With eager rebalancing, all currently owned partitions can be revoked before new assignments take effect. With cooperative rebalancing, only partitions that need to change owners are revoked incrementally, reducing interrupted work. Still, cooperative rebalancing has overhead and does not eliminate ownership handoff time completely.

If a system autoscales frequently, the group can rebalance repeatedly:

~~~text
Scale up
   |
   v
New consumers join group
   |
   v
Rebalance
   |
   v
Partitions change owners
   |
   v
Consumers resume processing
   |
   v
Scale down / restart
   |
   v
Rebalance again
~~~

Frequent rebalances can degrade overall throughput, especially if partition state initialization or revoke callbacks take long. Therefore, autoscaling requires cooldowns, graceful shutdown, and sensible scaling thresholds. Avoid scaling replicas up and down in response to very short-lived lag spikes.

Revoke and assign operations can also force the application to reinitialize local caches or partition-scoped state. If state must be restored from a store, ownership changes incur extra state-reloading cost.

## 9. max.poll.interval.ms and Processing Duration

A consumer must continue calling poll to maintain processing progress and group membership per protocol rules. If the listener spends too long between polls, the consumer can exceed max.poll.interval.ms and be considered stalled. Partitions can then be reassigned to other members.

Increasing concurrency does not necessarily make individual records process faster. If CPU or downstream is already saturated, processing duration can grow, making it harder for consumers to poll on time.

For example, a poll returns 100 records. The listener averages 300 ms per record and processes sequentially. Total processing time can reach roughly 30 seconds before overhead. If max.poll.interval.ms is lower than the actual interval between polls, the consumer risks leaving the group.

Mitigation approaches:

- Measure actual processing time per poll batch.
- Tune max.poll.records to limit how many records each poll returns.
- Optimize database and API operations.
- Increase max.poll.interval.ms when long processing times are a legitimate, controlled requirement.
- Avoid offloading to async processing without explicit offset commit and ownership management.

Increasing max.poll.interval.ms only extends the timeout before a consumer is treated as stalled. It does not make downstream faster and does not fix a hung listener.

## 10. Concurrency and Offset Commit Behavior

Each consumer member manages offsets for its assigned partitions. When concurrency rises, the number of independent consumers and parallel partitions increases, yet offset commit policies must still align with how the listener completes business work.

With synchronous processing inside the listener, the container can commit according to the configured ack mode. If the listener returns before async side effects finish, offsets can be committed earlier than actual business completion, depending on how the application integrates. If the process crashes, records can be lost from a business standpoint even though Kafka considers the offset processed.

If a listener processes records from the same partition in parallel, completion order and offset commits must be tracked. Committing an offset past an unfinished record can cause that record to be skipped when the consumer restarts.

Example:

~~~text
Offsets received:  100   101   102
Tasks completed:   100   102   101

Must not commit offset 103
before 101 is processed successfully.
~~~

Kafka consumers commit the next offset to read, not an arbitrary set of independent per-record acknowledgments. When processing asynchronously, the application must ensure commits advance only up to the contiguous completed offset per consumer and Spring Kafka semantics.

Increasing concurrency across partitions does not break ordering within a partition as long as each partition is processed sequentially. However, adding concurrency inside application logic with an executor can produce out-of-order completions. These are two different forms of parallelism and require separate design.

## 11. Example of Choosing Concurrency Based on Partition Count

Suppose the orders topic has 12 partitions and the application runs three replicas. You can estimate:

| Concurrency per replica | Total consumers | Maximum consumers with partitions | Potentially idle consumers |
|---:|---:|---:|---:|
| 1 | 3 | 3 | 0 |
| 2 | 6 | 6 | 0 |
| 3 | 9 | 9 | 0 |
| 4 | 12 | 12 | 0 |
| 5 | 15 | 12 | 3 |
| 6 | 18 | 12 | 6 |

In this example, concurrency 4 utilizes all 12 partitions assuming uniform assignments and subscriptions. Raising it to 5 creates three extra consumer members without increasing the number of partitions read in parallel.

However, concurrency 4 is not guaranteed to be the fastest configuration. If the database only performs well with six concurrent streams, concurrency 2 may deliver higher throughput and lower latency. If each partition carries very light load, concurrency 1 or 2 may already meet the SLO.

The goal is finding a concurrency level matched to the entire pipeline's capacity, not maximizing consumer count.

## 12. How to Identify Bottlenecks Before Raising Concurrency

Before changing configuration, pinpoint where the consumer group is constrained.

| Symptom | Possible cause | Investigation direction |
|---|---|---|
| High lag across all partitions, low consumer CPU | Consumer waiting on downstream or inefficient fetch/batching | Measure listener latency, network, database waits, and fetch metrics |
| High lag mainly on one partition | Hot partition or key skew | Check per-partition throughput and key distribution |
| Consumer CPU near 100% | CPU-bound processing | Profile code, serialization, and GC; scale across partitions if capacity allows |
| High database pool wait time | Database connection pool or database overloaded | Measure active/idle connections, query latency, locks, and transactions |
| Downstream API returns 429/5xx | Rate limits or overloaded service | Check concurrency limits, retry/backoff, and API capacity |
| Frequent rebalances | Membership churn or consumers missing poll deadline | Check deployments, autoscaling, heartbeats, poll interval, and callbacks |
| Many consumers without partitions | Total consumers exceed eligible partitions | Compute replicas × concurrency and adjust consumer count |
| Throughput unchanged despite more consumers | Partition ceiling or another bottleneck | Compare partition count, per-partition lag, and downstream capacity |

Key metrics to monitor:

- Total and per-partition consumer lag.
- Records consumed rate and bytes consumed rate.
- Listener processing time, p95, and p99.
- Consumer poll interval and processing duration between polls.
- Rebalance rate and rebalance duration.
- Commit latency and commit error rate.
- JVM CPU, heap, thread count, and GC pauses.
- Database pool active, pending, and connection acquisition time.
- Downstream API latency, error rate, and rate-limit responses.

Total lag can hide a single congested partition. Inspect lag per partition and throughput per consumer member to see where load is concentrated.

## 13. Is Adding Partitions Always the Answer?

When partition count is lower than desired parallelism, adding partitions can create more parallel processing units. However, that is a topic structural decision, not merely a concurrency adjustment.

Before adding partitions, consider:

- Are current keys distributed evenly?
- Do records with the same key require ordering?
- Will increasing partitions change key-to-partition mapping for new records?
- Do brokers have enough CPU, disk, and network capacity for additional partitions?
- Will more partitions increase metadata, file segment, and replication overhead?
- Do the consumer group and downstream have enough capacity to process the added load?

Adding partitions does not automatically split a hot key across multiple streams if the partitioner still routes that key to one partition. If business logic mandates per-key ordering, splitting a key requires explicit design, such as sub-keys when independent ordering per sub-stream is acceptable.

Do not add partitions simply to justify setting a high concurrency. Establish target throughput and limits across producers, brokers, consumers, databases, and downstream services before altering topology.

## 14. Concurrency Experimentation Workflow

A controlled approach:

1. Record a baseline: partition count, replica count, concurrency, throughput, lag, listener latency, and downstream latency.
2. Compute total consumer members as replicas multiplied by concurrency.
3. Compare total consumers against eligible partitions in the subscription.
4. Raise concurrency in small steps, such as from 1 to 2 then 3, instead of jumping straight to a large number.
5. Wait for the group to finish rebalancing and stabilize before collecting measurements.
6. Measure throughput, p95/p99 latency, per-partition lag, CPU, GC, and downstream saturation.
7. Inspect idle consumers, retries, commits, and processing errors.
8. Test scale-up, scale-down, and restart scenarios to measure rebalance cost.
9. Pick the value that meets the SLO with acceptable resource usage and stability.
10. Document the configuration rationale and maximum scale limits so autoscalers do not create more consumers than partitions.

Do not evaluate results immediately after increasing concurrency while the group is still rebalancing. Let assignments stabilize and exclude warm-up effects from caches, connection pools, and test data.

## 15. Common Misconceptions

**Increasing concurrency always increases throughput.** False. Throughput can be capped by partition count, hot partitions, CPU, or downstream systems.

**Concurrency equal to partition count is always optimal.** False. That only represents the point where every partition can have its own consumer. If downstream cannot handle that many streams, lower concurrency can be more stable and faster.

**Increasing replicas does not change concurrency.** False. Each replica adds consumer members according to listener concurrency; total consumers scale with replica count.

**One partition can be split across multiple consumers in the same group by raising concurrency.** False. A partition is the unit of assignment; one consumer member owns a partition in a stable state.

**More consumers always balance load better.** False. The assignor balances partition counts according to its strategy, unaware of per-partition processing cost or record rate.

**Adding partitions always fixes hot keys.** False. The same key typically still routes to a single partition. Splitting load requires changing key strategy or processing model and re-evaluating ordering requirements.

**Increasing max.poll.interval.ms fixes slow listeners.** False. It only extends the time limit between polls; underlying CPU or downstream slowness remains.

**Returning from the listener means async business work is complete.** False. If the application hands work to an executor and returns, offsets and ownership must be managed so commits do not occur before side effects complete.

## 16. Design Guidelines

When configuring consumer concurrency in Spring Kafka, start from partition count and target throughput. Compute total consumers from replicas and concurrency, then compare against eligible partitions and downstream processing capacity.

A deployment configuration should consider:

1. Choosing partition count based on parallelism, key ordering, and broker capacity.
2. Setting default concurrency aligned with partition count and single-instance resources.
3. Calculating maximum replicas to avoid spawning excessive idle consumers.
4. Measuring per-partition load to detect hot partitions and key skew.
5. Sizing database pools and downstream concurrency to match true capacity.
6. Configuring max.poll.records and max.poll.interval.ms according to actual processing times.
7. Using cooperative rebalancing or static membership when suited to your version and deployment workflow.
8. Using graceful shutdown and revoke handlers for safe ownership handoffs.
9. Keeping intra-partition processing sequential when business ordering is required; designing idempotently for retries or reprocessing.
10. Increasing concurrency incrementally and evaluating throughput, lag, latency, rebalances, and resources together.

Concurrency only creates more consumer members. It does not create more partitions, split an existing partition, make the database faster, or eliminate rebalance costs. Raising concurrency helps when unexploited partitions remain and backing components have spare capacity. Once any of those limits is reached, fix the actual bottleneck instead of continuing to add threads.
