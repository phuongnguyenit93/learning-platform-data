# Calculating Partitions, Instances, and Concurrency for Load

To scale a Spring Cloud Stream application, you need to answer three related but distinct questions: how many partitions are needed to divide the data, how many instances are needed to run the application, and how many concurrent consumers each instance needs. If you only increase pod count while the broker lacks capacity to distribute data, new instances may receive no extra work. If you increase concurrency too high, the database, connection pool, or CPU can become the bottleneck.

Reliable sizing starts from actual load and measurements on a single consumer worker. Next, calculate the required number of workers, distribute workers across instances, and then check partition limits and broker capacity. Kafka, RabbitMQ, and Pulsar have different distribution models, so you cannot apply a single partition formula to all three.

## 1. Distinguishing partitions, instances, and concurrency

| Concept | Meaning | What does it control? |
|---|---|---|
| Partition | An independent slice of a topic or partitioned stream | Load splitting, parallelism, and ordering within the partition |
| Instance | A running application process, typically a pod/container/VM | CPU, RAM, network resources, and fault isolation |
| Concurrency | Number of consumers/listeners processing concurrently in one instance for a binding | Number of concurrent message-processing threads per instance |
| Worker slot | One concurrent message-processing unit verified by capacity testing | Total processing capacity to deploy |
| Consumer group/subscription | A group of consumers sharing progress on a stream | How the broker distributes messages to consumers |

For example, an application with 12 pods and concurrency 2 per pod has up to 24 consumer slots for that binding. That does not mean the application always handles 24 times the load of a single pod: performance also depends on partitions, key skew, processing time, broker, database, and downstream limits.

Do not equate partitions with instances. One partition may be handled by one consumer; one instance may own multiple partitions; one instance may also have multiple consumer threads. The exact relationship depends on the binder and subscription mode.

## 2. Gathering load data before calculating

Before choosing partition count or replicas, measure at least the following parameters:

| Symbol | Parameter | How to obtain |
|---|---|---|
| λavg | Average event rate, events/second | Broker metrics or application counters |
| λpeak | Peak event rate over a relevant load window | 1-minute, 5-minute, or business peak window |
| S | Time a worker is busy processing one event | Timer/benchmark, separating CPU time and I/O wait |
| μworker | Sustainable throughput of one consumer slot | Load test at target latency and error rate |
| B | Existing backlog | Kafka lag, RabbitMQ ready/unacked, or Pulsar backlog |
| Tdrain | Desired time to clear the backlog | Operational SLO |
| C | Concurrency per instance | Consumer binding configuration and measurement |
| I | Number of application instances | Deployment/HPA/replica count |
| P | Number of partitions or partitioning units | Broker topic/queue topology |

Do not use average rate alone. A system might receive 200 events/second most of the time but spike to 1,500 events/second during order settlement windows. Sizing for the average causes the backlog to grow during peak hours.

Measure processing time on the same payload types and the same dependencies as production. A small event that only checks a cache is not representative of an event that calls three services, writes to a database, and publishes output. Measure p50/p95/p99, error rate, CPU, heap, database connections, and broker lag in the same load test.

## 3. Calculating required workers

There are two ways to estimate. The first uses the time a worker is occupied; the second uses measured throughput.

### 3.1. From arrival rate and service time

Let:

- λpeak be the peak event rate, events/second.
- S be the seconds a worker is busy processing one event.
- ρ be the target worker utilization, less than 1 to keep headroom.
- W be the number of worker slots required.

A worker processing sequentially has a theoretical capacity of about 1/S events/second. To avoid running workers continuously near 100%, apply target utilization:

    W = ceil((λpeak × S) / ρ)

This formula assumes each worker processes one event at a time and S is the duration the worker is occupied. It is an initial estimate; load testing is still required to confirm latency and throughput.

For example, the stream receives 800 events/second at peak. One consumer worker takes 40 ms on average to process an event, meaning S = 0.04 seconds. Choose target utilization 65%:

    W = ceil((800 × 0.04) / 0.65)
      = ceil(32 / 0.65)
      = 50 worker slots

One worker has a theoretical throughput of 25 events/second, but at 65% utilization you should plan for about 16.25 events/second. Fifty slots provide a target capacity of around 812.5 events/second, just enough for 800 events/second with headroom under these assumptions.

ρ is not a mandatory constant. For CPU-bound workloads, 60–75% can be a starting point to reserve headroom for bursts and GC. For I/O-bound workloads, many requests may need to wait concurrently; in that case use benchmarking rather than mechanically applying CPU utilization.

### 3.2. From measured throughput

If load testing shows one consumer slot sustainably processes μworker events/second while meeting latency and error budgets, compute:

    W = ceil(λpeak / μworker)

For example, one slot sustainably processes 32 events/second at p95 under 100 ms. With a peak of 800 events/second:

    W = ceil(800 / 32)
      = 25 worker slots

Do not multiply by an extra utilization factor if μworker was already measured at a safe load with headroom. If throughput was measured at saturation, scale it down by target utilization before applying the formula.

Measuring sustainable throughput is usually more reliable because it reflects actual code, serialization, database, network, broker, and configuration. You can use the service-time formula to cross-check benchmark results.

### 3.3. Do not substitute end-to-end time for service time

End-to-end latency can include broker wait time, retry backoff, and downstream delays. If you use that entire latency as S, the calculated worker count can be exaggerated. Measure the time the worker is actually busy separately from the time the message waits before processing.

With asynchronous I/O, one worker can have many requests waiting concurrently. In that case, the number of in-flight operations can exceed the thread count. Measure the actual concurrency of your function/runtime and dependency connection limits.

## 4. Adding capacity to drain backlog

Sizing only for incoming traffic will not automatically clear an accumulated backlog. If there are B waiting events and you want to drain them within Tdrain seconds, additional processing rate needed is:

    λdrain = B / Tdrain

Total capacity required during drain:

    λrequired = λpeak + λdrain

Then compute worker slots using the corresponding throughput or service-time formula.

For example, with 600,000 backlogged events to clear in 10 minutes:

    λdrain = 600,000 / 600 = 1,000 events/second
    λrequired = 800 + 1,000 = 1,800 events/second

With S = 40 ms and ρ = 65%:

    W = ceil((1,800 × 0.04) / 0.65)
      = 111 worker slots

This is recovery-phase capacity, which can be much larger than normal sizing. If downstream only supports 900 requests/second, you cannot scale consumers to 111 slots without overloading downstream. In that situation, lengthen the drain window, reduce ingress rate, or scale the dependency.

## 5. Calculating instances from worker slots

Once you have worker slots W and select concurrency C per instance:

    I = ceil(W / C)

Using the example W = 50:

| Concurrency per instance | Instances required | Total slots provisioned |
|---:|---:|---:|
| 1 | 50 | 50 |
| 2 | 25 | 50 |
| 4 | 13 | 52 |
| 5 | 10 | 50 |
| 8 | 7 | 56 |

Provisioned slots may exceed demand due to rounding up instances. This provides some headroom but also consumes CPU/RAM and connections. Choose C by benchmarking a single instance, then choose I based on resource budget and HA requirements.

### 5.1. When to increase instances?

Increasing instances is appropriate when:
- A single instance already uses most of its CPU/RAM or threads.
- You want to isolate failure domains and deploy in smaller increments.
- There is enough partition/queue consumer capacity to distribute additional work.
- Downstream can handle additional connections and requests.
- You need independent scaling with load.

Increasing instances does not help if the broker has only one partition being processed by a single consumer, or if the database has already hit connection/IO limits. In those cases, new instances may sit idle or overload dependencies further.

### 5.2. When to increase concurrency?

Increasing per-instance concurrency is appropriate when:
- The consumer has significant I/O wait time.
- CPU and heap still have headroom.
- Database/API pools have sufficient connections and quota.
- The broker can assign more partitions/messages to new consumers.
- Load tests prove throughput rises without degrading p95/p99.

Do not increase concurrency just to raise CPU utilization. If the function is CPU-bound and already saturates cores, adding threads typically increases context switching and contention. If messages must be processed in order or share non-thread-safe state, increasing concurrency can break semantics.

## 6. Key limits when using Kafka

In Kafka, a topic's records are divided into partitions. Within a single consumer group, at any moment each partition is assigned to at most one consumer in the group. Therefore, the number of usefully active consumers is capped by the partition count.

Let:
- P be the topic's partition count.
- I be the number of application instances.
- C be the concurrency per instance.
- A be the number of consumers assigned a partition.

In a standard Kafka consumer group:

    A ≤ min(P, I × C)

This is the partition-bounded parallelism limit. If I × C exceeds P, some consumers receive no partition assignment and add no throughput. If P exceeds I × C, some partitions are handled alongside others by the current consumers in the group and provide room when scaling out.

For example, a topic with 64 partitions:
- 25 instances × concurrency 2 = 50 consumer slots.
- Up to 50 consumers have work; 14 partitions share consumers within the group (some consumers handle 2 partitions).
- When scaling to 32 instances × concurrency 2 = 64 slots, all 64 partitions can be processed in parallel by one consumer each.
- When scaling to 40 instances × concurrency 2 = 80 slots, at most 64 consumers get partitions; the remaining 16 slots sit idle.

Therefore, partition count must be sized for the consumer group's planned maximum scale, not just today's running pod count.

### 6.1. Calculating partitions for Kafka

For a consumer group processing each partition sequentially, you can use:

    Ptarget ≥ Imax × C

Where Imax is the maximum number of instances the system plans to scale to. This ensures enough partitions for the planned consumer slots; it does not prove the broker has enough throughput or that partitions are evenly loaded.

Next, verify:
- Producer and consumer throughput per partition.
- Message size and network bandwidth.
- Broker count and partition leader distribution.
- Replication factor and disk capacity.
- Hot keys and load imbalance across partitions.
- Rebalance duration when instances scale up/down.
- Metadata, file handle, and recovery overhead of many partitions.

Do not set partition counts arbitrarily high just for unlimited headroom. Every partition carries broker, replication, metadata, and operational costs.

### 6.2. Key distribution and hot partitions

Adding partitions does not guarantee higher throughput if data is skewed. For example, 40% of events belong to one large customer and the partition key is `customerId`. All events for that customer may land in the same partition while other partitions stay lightly loaded.

Choose keys based on ordering requirements and load distribution. If per-order ordering is required, using `orderId` as the key is usually sensible. If one key is very hot, consider finer-grained aggregates, controlled sharding, or isolating hot workloads; do not change keys arbitrarily because that can break business ordering.

### 6.3. What happens when increasing partitions?

Kafka allows increasing a topic's partition count, but not reducing it through normal means. When partitions increase, key-to-partition mapping can change. New events with the same key may be written to a different partition than older events, breaking ordering assumptions across the change boundary.

For systems requiring per-key ordering, plan migrations carefully or keep the partitioning strategy stable. Do not treat adding partitions as a completely risk-free scaling operation.

## 7. Distinguishing Spring Cloud Stream partitionCount from broker partitions

Spring Cloud Stream provides a partitioning abstraction on producers and consumers:

- Producers use `partitionKeyExpression` or `PartitionKeyExtractor` to extract keys.
- Producers use `partitionCount` to define the partition space used by binder partitioning.
- Consumers use `partitioned` with `instanceCount`/`instanceIndex` in partitioned consumer scenarios.
- Brokers may have native partitioning, such as Kafka topic partitions or Pulsar partitioned topics.

For Kafka, Spring Cloud Stream's producer `partitionCount` is treated as a hint; the binder uses the greater of that value and the topic's actual partition count. Configuring producer partitioning does not automatically replace managing topic partition counts in the cluster.

Example producer partitioning configuration:

    spring:
      cloud:
        stream:
          bindings:
            publishOrder-out-0:
              destination: orders
              producer:
                partition-key-expression: payload.orderId
                partition-count: 64

The expression extracts `orderId` as the partition key. This configuration only takes effect when partitioning is enabled and `partitionCount` is greater than 1. Verify that the destination has the corresponding partition count per the binder.

### 7.1. instanceCount and instanceIndex

Spring Cloud Stream provides these properties:
- `spring.cloud.stream.instanceCount`: total number of instances in a partitioned application.
- `spring.cloud.stream.instanceIndex`: unique zero-based index of the instance, from 0 to `instanceCount - 1`.

With Kafka and the default `autoRebalanceEnabled=true`, Kafka automatically distributes partitions within the consumer group; consumers do not need `instanceIndex` for normal rebalancing. If `autoRebalanceEnabled` is disabled and the binder performs static partition assignment, `instanceCount`/`instanceIndex` must be configured accurately.

With RabbitMQ partitioned consumers, `instanceCount`/`instanceIndex` determines which partitions/queues an instance receives. Do not assign the same `instanceIndex` to all pods when static partitioning is required; each instance must have a unique index.

## 8. Configuring Kafka consumer concurrency

The generic Spring Cloud Stream consumer concurrency property sits on the input binding:

    spring:
      cloud:
        function:
          definition: processOrder
        stream:
          bindings:
            processOrder-in-0:
              destination: orders
              group: order-workers
              consumer:
                concurrency: 2
        kafka:
          binder:
            auto-create-topics: true
            auto-add-partitions: true
            min-partition-count: 64

In this example:
- Each instance has consumer concurrency of 2 for binding `processOrder-in-0`.
- Kafka rebalances partitions within consumer group `order-workers` automatically by default.
- The binder can apply `min-partition-count` when `auto-create-topics` or `auto-add-partitions` is enabled.
- Pre-existing topics may need prior provisioning; verify the actual partition count after provisioning.

If the topic already exists and `auto-add-partitions` is disabled, the binder will not automatically increase partitions when the actual count is lower than needed. Manage topics via infrastructure workflows and verify before rollout.

Concurrency is per input binding. If an application has multiple functions/input bindings, calculate capacity for each binding separately and check total consumer threads, connections, and memory per instance. Do not sum or look at a single binding's concurrency and assume it represents the whole application.

## 9. RabbitMQ: queues and competing consumers

RabbitMQ does not have native partitions like Kafka topics. With the default RabbitMQ Binder, a destination typically maps to an exchange; each consumer group gets its own queue bound to the exchange. Multiple consumer instances in the same group can consume from that queue as competing consumers.

With non-partitioned queues:
- You can increase instances or listener concurrency to add consumers.
- There is no strict `P ≥ I × C` rule like Kafka topic partitions.
- Queue, broker node, prefetch, acknowledgement, message size, and downstream still limit throughput.
- Multiple consumers processing in parallel can cause completion order to differ from enqueue order.

The RabbitMQ Binder supports consumer `concurrency` and `maxConcurrency` on the listener container depending on binder/version configuration. With the `direct` container type, some options such as `maxConcurrency` are not supported; check the exact container type and release you are using.

Example configuration:

    spring:
      cloud:
        stream:
          bindings:
            orders-in-0:
              destination: orders
              group: order-workers
              consumer:
                concurrency: 4
          rabbit:
            bindings:
              orders-in-0:
                consumer:
                  max-concurrency: 8
                  prefetch: 20

Initial concurrency is 4 and the listener can scale up to 8 consumers as supported by the container. A prefetch of 20 allows each consumer up to that many unacknowledged messages per Rabbit client semantics; increasing prefetch can raise throughput but also increases in-flight messages and memory usage.

### 9.1. RabbitMQ partitioning when per-key ordering is needed

The Spring Cloud Stream Rabbit Binder supports partitioning by creating a queue per partition with corresponding routing keys. This is a binder-level abstraction, not native RabbitMQ partitions.

In a partitioned consumer scenario:
- Producer computes the partition from the key.
- Binder routes messages to the partition's queue.
- Instances are assigned partitions via `instanceCount`/`instanceIndex`.
- Each partition has its own queue, keeping events with the same key on the same partition as configured.

Partitioned Rabbit setups require producer and consumer coordination; simply adding consumers to one queue does not create more partitions. If using RabbitMQ Streams/Super Streams, the partition and concurrency model differs from standard AMQP queues; read the stream plugin documentation before sizing.

## 10. Pulsar: partitioned topics and subscription types

Pulsar separates two decisions:
- Partitioned topics determine how producers distribute data across partitions/brokers.
- Subscription types determine how consumers share messages and progress.

A partitioned topic must be created with a partition count. Subscription type changes parallelism limits and ordering:

| Subscription type | Distribution behavior | Scaling impact |
|---|---|---|
| Exclusive | Only one consumer can attach to the subscription | Cannot scale multiple active consumers on the same subscription |
| Failover | Multiple consumers attach, one active per topic/partition, others standby | Partitioned topics distribute active partitions across consumers; excess instances remain standby |
| Shared | Multiple consumers receive distributed messages concurrently | Scales consumers in parallel; no message ordering guarantee |
| Key_Shared | Multiple consumers on the same subscription; messages with the same key go to one consumer at a time | Parallelism across keys while preserving per-key ordering when producer batching/routing is configured properly |

With `Shared` or `Key_Shared`, do not mechanically apply Kafka formulas. Consumer count, partitions, routing, subscription type, and broker capacity jointly determine useful parallelism. `Key_Shared` requires producers to use keys/ordering keys and compatible batching; if batching groups mismatched keys, per-key routing may not behave as expected.

When using the Pulsar Binder, configure consumers and subscription types using the extended binding properties for your running version. After changing a subscription type, verify restart procedures and subscription state because a subscription can only have one type at a time.

## 11. CPU-bound and I/O-bound workloads require different concurrency choices

### 11.1. CPU-bound

Examples: image encryption, compression, scoring calculations, or large JSON processing. Each message consumes significant CPU.

- Start with concurrency close to the number of CPU cores allocated to the instance.
- Measure CPU throttling, context switches, GC, and p95.
- Add instances when more cores are needed and the broker can distribute more work.
- Do not add unbounded threads on the same core count.

If a container has 2 vCPUs, setting concurrency to 16 for a CPU-bound function usually does not yield 8x throughput; it can worsen latency due to CPU contention.

### 11.2. I/O-bound

Examples: database reads/writes, REST API calls, or waiting on object storage. Workers spend much of their time waiting on I/O, so more concurrent operations than cores may be needed.

- You can increase concurrency above core count after benchmarking.
- Check connection pools and dependency request limits.
- Cap in-flight operations to avoid building queues inside the process.
- Monitor downstream timeouts, retries, and p99.

If concurrency is 20 while the database connection pool has only 5 connections, most messages will wait on a connection. Increasing concurrency then simply moves the backlog from the broker into application memory.

### 11.3. Reactive functions

Reactive functions use `Publisher`/`Flux` and can execute asynchronously. Thread count, subscription count, and in-flight requests do not necessarily equal message-driven listener consumer concurrency. Do not infer worker count solely from thread count. Measure demand, buffers, operator concurrency, and client I/O limits across the reactive pipeline.

## 12. Controlling memory and prefetch

Each consumer slot can hold messages being processed, prefetched messages, deserialized payloads, and intermediate objects. In-flight memory can be roughly estimated as:

    Memory_inflight ≈ concurrent_messages × average_payload_memory × overhead_factor

Deserialized payload objects are usually larger than their wire size. The overhead factor depends on object graphs, headers, buffers, converters, and batches; measure it via heap profiling/load testing.

For example, 16 consumers each with a prefetch of 50 can hold hundreds of delivered/pending messages depending on the binder. If a deserialized message averages 200 KB, payloads alone can consume substantial memory, before object overhead and other buffers.

Do not increase concurrency and prefetch at the same time without a baseline. Change one parameter at a time and watch heap, GC pauses, unacked count, and backlog age.

## 13. Sizing partitions for keys and business ordering

Partition count does more than serve throughput. It also defines ordering scope and how state is sharded.

Before choosing a partition key, answer:
- Which events must be processed in order?
- Must ordering hold by `orderId`, `customerId`, `accountId`, or `sensorId`?
- Does any key carry far more traffic than the rest?
- Might partition count need to change in the future?
- Do consumers keep local state per partition?

If all events for the same order must be sequential, choose `orderId` as the key. If you use `customerId` and one customer generates massive event volume, that partition can become a hot partition. If you use a random `eventId`, load may spread evenly, but events for the same aggregate no longer land in the same partition.

Do not choose a partition key solely for load balancing; preserve business invariants first.

## 14. Complete sizing example

Suppose an order-event processing function has these measured metrics:

| Parameter | Value |
|---|---:|
| Peak input rate | 800 events/second |
| Average service time per slot | 40 ms |
| Target utilization | 65% |
| Required worker slots | 50 |
| Concurrency per pod | 2 |
| Required pods | 25 |
| Current partition count | 64 |
| Planned maximum scale | 32 pods |

Compute workers:

    W = ceil((800 × 0.04) / 0.65) = 50

Compute instances:

    I = ceil(50 / 2) = 25

Verify Kafka at maximum scale:

    Imax × C = 32 × 2 = 64 consumer slots
    P = 64 partitions

The topic has enough partitions for the maximum scaling plan. At current load, 25 pods create 50 consumers; when scaled to 32 pods, up to 64 active consumers can run if partition assignment and the broker allow.

Before finalizing, run a load test with 25 pods at the 800 events/second peak and test scaling up to 32 pods. Verify p95/p99, lag, database pool, CPU, GC, and broker throughput. If one hot partition carries most traffic, actual results may fall short of the calculation.

## 15. Configuring and deploying multiple instances

Example Kafka configuration for the order processing function:

    spring:
      cloud:
        function:
          definition: processOrder
        stream:
          bindings:
            processOrder-in-0:
              destination: orders
              group: order-workers
              consumer:
                concurrency: 2
          kafka:
            binder:
              min-partition-count: 64
              auto-create-topics: true
              auto-add-partitions: true

With a Kafka consumer group using default auto-rebalancing, instances share the same group and Kafka distributes partitions. Replica count is set by the deployment platform; concurrency applies per instance.

If using static partition assignment with Kafka or RabbitMQ partitioned consumers, pass the right `instanceCount` and `instanceIndex` to each instance. Example environment variables:

    SPRING_CLOUD_STREAM_INSTANCE_COUNT=25
    SPRING_CLOUD_STREAM_INSTANCE_INDEX=0

Other instances must each get a unique index from 0 to 24. Do not use the same index for all replicas in a static partition assignment model. On Kubernetes, use a mechanism that provides stable ordinals/indices or a runtime such as Spring Cloud Data Flow to supply instance metadata.

## 16. Autoscaling on lag and backlog

CPU is not the only signal for scaling consumers. An I/O-bound application may show low CPU while its backlog grows rapidly. Conversely, high CPU with zero lag may simply show consumers are productively busy.

Suitable scaling signals:
- Kafka consumer group lag and lag growth rate.
- RabbitMQ ready message count, unacked count, and message age.
- Pulsar subscription backlog and backlog age.
- Processing rate compared to input rate.
- p95/p99 processing time.
- CPU, memory, and downstream saturation.

An autoscaling policy can target lag per consumer slot, such as 5,000 records/slot, paired with min/max replica bounds and stabilization windows. Never scale beyond partition or queue topology capacity.

### 16.1. Kafka scaling limits

With Kafka, useful consumers in a group are capped by partition count. An HPA might request 100 pods while the topic has only 48 partitions; at most 48 consumers can receive partitions in that group. Remaining pods consume resources without processing partitions.

### 16.2. RabbitMQ and Pulsar scaling limits

With standard RabbitMQ queues, multiple competing consumers can read from one queue, though broker, queue throughput, prefetch, and ordering impose limits. With RabbitMQ partitioned queues or Super Streams, partition/stream segment count and consumer assignment govern parallelism.

With Pulsar, check subscription type. `Exclusive` allows only one consumer; `Failover` keeps extra consumers on standby; `Shared` and `Key_Shared` allow multiple active consumers with different ordering semantics. Do not scale consumers purely by partition count while ignoring subscription type.

## 17. Load testing to validate sizing

A calculation is only a hypothesis until measured on a representative workload. Load tests should cover:

1. Steady load at `λavg` long enough to establish a baseline.
2. Peak load `λpeak` to confirm no sustained backlog growth.
3. Short bursts above peak to test headroom.
4. Skewed-key load to detect hot partitions/queues.
5. Large payloads and complex schemas.
6. Slow or timing-out dependencies to measure impact on concurrency.
7. Partial instance restarts/rebalances to verify recovery.
8. Scaling replicas up and down to ensure autoscaling does not trigger a rebalance storm.
9. Backlog drain to confirm recovery time meets the SLO.

Record input rate, processed rate, p50/p95/p99, lag/backlog, oldest message age, errors/retries/DLQ, CPU, heap, GC, threads, connection pools, and broker resources. A configuration passes only if it achieves both target throughput and target latency and error rates.

## 18. Practical sizing workflow

1. Measure peak arrival rate over business windows, not just daily averages.
2. Measure service time and sustainable throughput of one consumer slot.
3. Choose target utilization and headroom based on workload type.
4. Calculate required worker slots from service time or measured throughput.
5. Add capacity for backlog drain if there is a recovery objective.
6. Choose per-instance concurrency based on CPU, I/O, connection pools, and memory.
7. Calculate instance count by dividing worker slots by concurrency.
8. Check broker-specific parallelism: Kafka partitions, Rabbit queues/partitions, Pulsar partitions/subscription type.
9. Choose partition keys and check skew/ordering.
10. Configure bindings, binder, and instance metadata for the chosen model.
11. Load test, check SLOs, and tune one parameter at a time.
12. Set min/max replicas and autoscaling thresholds according to broker/downstream limits.

## 19. Common mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Sizing from average traffic | Backlog grows during peaks | Use peak rate and burst testing |
| Adding pods when Kafka topic has too few partitions | New consumers sit idle | Size partitions for max consumer slots |
| Setting concurrency too high | CPU contention, heap pressure, connection exhaustion | Benchmark by CPU/I/O workload type |
| Confusing `partitionCount` with broker partition count | Assuming the topic is partitioned enough | Verify actual partitions on the broker |
| Using the same key for too many events | Hot partition | Analyze key distribution and pick a suitable aggregate key |
| Using `eventId` as partition key when order-level ordering is needed | Events for the same order go to different partitions | Use `orderId`/`accountId` as key |
| Scaling RabbitMQ consumers while ignoring prefetch | High in-flight messages and memory pressure | Tune concurrency and prefetch together deliberately |
| Using Pulsar `Exclusive` while scaling multiple consumers | New consumers stay inactive | Choose a subscription type matching semantics |
| Scaling Kafka past partition count | Extra pods/consumers receive no partitions | Cap max replicas at `P/C` |
| Autoscaling on CPU alone | Misses I/O-bound backlogs | Combine lag, age, and input/output rates |
| Increasing partitions abruptly | Key mapping and ordering can shift | Plan migration and test thoroughly |
| Ignoring downstream capacity | Database/API overload | Size the whole pipeline, not just consumers |

## 20. Pre-deployment checklist

- [ ] Realistic peak input rate and burst profile documented.
- [ ] Service time and throughput of one consumer slot measured.
- [ ] Target utilization and headroom defined.
- [ ] Worker slots calculated for both new traffic and backlog drain.
- [ ] Concurrency chosen based on CPU, I/O, memory, and dependency pools.
- [ ] Instance count calculated as worker slots / concurrency.
- [ ] For Kafka, partition count covers consumer slots at maximum scale.
- [ ] Actual Kafka topic partition count verified.
- [ ] Partition key satisfies ordering without creating severe hot partitions.
- [ ] Distinguished Spring Cloud Stream producer `partitionCount` from physical broker partitions.
- [ ] For RabbitMQ, appropriate queues/partitioning and concurrency selected.
- [ ] For Pulsar, subscription type matches ordering and parallelism needs.
- [ ] `instanceCount`/`instanceIndex` configured where the partitioning model requires it.
- [ ] Max replicas bounded by broker partitions/queues and downstream capacity.
- [ ] Load tests cover peak, burst, key skew, dependency slowdowns, and restarts.
- [ ] Dashboards monitor lag/backlog, oldest age, p95/p99, errors, and resource saturation.

Properly sizing partitions, instances, and concurrency is a balancing act across ingress rate, per-worker processing capacity, application resources, and broker message distribution. Start from peak rate and measured throughput, compute worker slots, translate into replicas/concurrency, and apply the specific constraints of Kafka, RabbitMQ, or Pulsar. Finally, only load testing and observing backlog/latency will confirm whether the configuration meets real production load.

## References

- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream — Partitioning](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-partitioning.html)
- [Spring Cloud Stream — Instance Index and Instance Count](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-instance-index-instance-count.html)
- [Spring Cloud Stream — Kafka Binder Configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Cloud Stream — RabbitMQ Binder Configuration](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html)
- [Apache Pulsar — Messaging and Subscription Types](https://pulsar.apache.org/docs/5.0.x/concepts-messaging/)
