# Setting Throughput, Latency, and Reliability Targets

The performance of a Spring Cloud Stream application cannot be evaluated solely by the number of messages processed per second. A system can achieve high throughput while leaving messages waiting too long in a queue; it can also have low latency under light load yet become unstable during traffic spikes. When optimizing, you need to set targets simultaneously for throughput, latency, backlog, and delivery reliability.

Spring Cloud Stream provides a function, binding, and binder model to connect Supplier, Function, and Consumer with Kafka, RabbitMQ, or Pulsar. Common properties such as consumer concurrency, retry, and batching help tune the application; each binder also has its own mechanisms such as Kafka partitions, producer batching, and consumer polling, or RabbitMQ prefetch, consumer concurrency, and acknowledgement. There is no single optimal configuration set for every binder or every workload. Define your SLOs, measure a baseline, find the bottleneck, and then change one configuration group at a time.

## 1. Three targets to establish

### Throughput

Throughput is the number of messages successfully processed per unit of time, usually measured in messages/second (msg/s). Distinguish between:

- **Offered rate**: the number of messages the source sends to the system.
- **Ingress rate**: the number of messages the broker receives and accepts.
- **Processing rate**: the number of messages the consumer finishes processing.
- **Completion rate**: the number of messages that complete the entire business flow, including downstream publishing or writing to the target data store.

Do not use the ingress rate as completion throughput. If the producer sends 2,000 msg/s while the consumer only processes 1,500 msg/s, the backlog grows by 500 messages every second even though the producer charts look great.

### Latency

Latency is the time from a defined start milestone to a defined end milestone. For event processing, track at least:

- **Publish latency**: the time for the producer to send a message and receive the result according to the acknowledgement policy.
- **Queue wait**: the time a message waits before being processed by a consumer.
- **Processing latency**: the time the function takes to execute business logic.
- **End-to-end latency**: from when an event is created or accepted until the final result is confirmed.

Measure p50, p95, and p99 instead of looking only at the average. p50 indicates the typical experience; p95/p99 help detect tail latency caused by queueing, retries, GC pauses, network, or broker throttling. If a message passes through multiple functions/brokers, measure both each hop and the full path.

### Reliability

Reliability describes whether the system processes enough messages and processes them accurately under high load or failures. Quantify:

- The percentage of messages completed successfully.
- The number of retried, dead-lettered, and rejected messages.
- The number of redeliveries/duplicates and the rate of idempotent processing.
- Maximum backlog and the time for the backlog to return to normal.
- Recovery capability when a consumer, broker, or application node stops.
- Acceptable data loss; for critical flows, the target is usually zero loss of messages acknowledged by the broker.

High throughput does not compensate for lost messages or duplicate processing that corrupts balances. Never lower acknowledgement, replication, or durability just to improve a benchmark number.

## 2. Write SLOs before tuning configuration

A good SLO describes the load, duration, and measurement conditions. The example below only illustrates how to write targets; replace the numbers with actual requirements:

| Metric | Example target | Verification method |
|---|---:|---|
| Steady throughput | 1,500 msg/s for 30 minutes | Count completed messages at the output |
| Burst | 3,000 msg/s for 5 minutes | Check backlog and recovery capability |
| End-to-end latency | p95 under 250 ms, p99 under 1 s | Timestamp/correlation ID at the start and end of the flow |
| Backlog recovery | Return to normal within 3 minutes after a burst | Measure drain rate |
| Error handling | No loss of broker-acknowledged messages; duplicates handled idempotently | Fault injection and reconciliation |
| DLQ | All poison messages retained for investigation | Count, inspect, and replay DLQ |

The SLO must specify payload size, partition/queue count, consumer group, instance count, broker type, durability settings, and simulated error rate. If you change one condition, benchmark results are no longer directly comparable to the old baseline.

## 3. Describe the workload before sizing

Collect real data or model the following factors:

| Characteristic | Questions to answer | Impact |
|---|---|---|
| Arrival rate | Average, peak, and how long do bursts last? | Determines capacity and backlog |
| Payload | Median, p95, and p99 size? | Affects network, memory, serialization, and batching |
| Key distribution | Are keys evenly distributed or are there hot keys? | Affects partitions and ordering |
| Processing cost | How long does the function take, and is it CPU-bound or I/O-bound? | Determines concurrency and thread pools |
| Fan-out | How many outputs does one input generate? | Downstream throughput may exceed ingress |
| Ordering | Global ordering, per-key ordering, or none required? | Limits partitions/concurrency |
| Failure rate | How many transient errors vs. poison messages? | Affects retries, DLQ, and latency |
| Retention | How long does the broker retain backlog? | Determines recovery capability after an incident |

For example: 1,000 input msg/s where each input produces three outputs means downstream must handle 3,000 output msg/s, excluding retries. Measure each binding separately to find the stage with the lowest capacity.

## 4. Basic capacity formulas

Let:

- λ be the message arrival rate (messages/second).
- μ be the maximum processing rate of a single worker (messages/second).
- N be the number of workers processing in parallel.
- S be the average processing time for one message on one worker (seconds).
- ρ be the target worker utilization.

For a worker processing sequentially, approximately μ = 1 / S. Total theoretical capacity is N × μ. To prevent the backlog from growing indefinitely, capacity must exceed the arrival rate: N × μ > λ.

Do not design a system to run near 100% utilization at all times. When the arrival rate approaches capacity, queueing delay can grow rapidly and the system lacks headroom to absorb bursts. You can use a preliminary sizing formula:

N >= (λ × S) / ρ

For example, to process 1,500 msg/s with an average worker processing time of 8 ms (0.008 s) and a target utilization of 65%:

N >= (1500 × 0.008) / 0.65 = 18.46

The initial estimate is 19 workers. This is only an approximate model; you must benchmark because processing time varies, I/O may run concurrently, and the broker/partitions may limit the number of active consumers.

### Little's Law and backlog

In a stable system:

L = λ × W

Where L is the average number of messages in the system, λ is throughput, and W is the average time a message stays in the system. If you process 1,000 msg/s and there are on average 20,000 messages waiting or being processed, the average residence time is approximately 20 seconds.

Backlog drain time can be estimated by:

T_drain = B / (C - λ)

B is the current backlog, and C is the processing capacity while the system is still receiving traffic. For example, with a backlog of 60,000 messages, capacity of 1,800 msg/s, and new incoming traffic of 1,200 msg/s, the net drain rate is 600 msg/s; it takes about 100 seconds to clear the backlog. If C is less than or equal to λ, the backlog cannot drain on its own.

## 5. Partitions and concurrency determine parallelism

With Kafka, a partition is the basic unit of parallelism within a consumer group. At any point in time, one partition is assigned to only one consumer member in the group. Therefore:

- If a topic has 8 partitions, a consumer group generally cannot utilize more than 8 active consumers for that topic.
- If you run 12 consumers for an 8-partition topic, at least 4 consumers will have no partitions to read.
- Increasing partitions can increase parallelism, but it also increases metadata, file, replication, rebalance, and broker resource overhead.
- Keys are hashed to select partitions; a hot key can overload one partition while other partitions sit idle.

In Spring Cloud Stream, consumer concurrency is a common property for input bindings. With the Kafka binder, concurrency creates corresponding consumer containers; effectiveness is still bounded by the number of assigned partitions. With the Kafka Streams binder, concurrency on the input binding is translated into the number of stream threads (`num.stream.threads`), so distinguish it from the regular Kafka binder.

Do not increase concurrency by guesswork. First check partition count, instance count, key skew, consumer lag, and CPU. If a partition is hot due to skewed key distribution, adding consumers will not solve the root cause.

### Example regular Kafka consumer configuration

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-in-0:
          destination: orders.events
          group: order-service
          consumer:
            concurrency: 4
~~~

With a 12-partition topic, you can test 4 consumers per instance or split instances/concurrency so that total consumers do not exceed the partition count if the goal is to avoid idle consumers. The actual number also depends on deployment layout, rebalancing, and processing load.

### Example for the Kafka Streams binder

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        aggregateOrders-in-0:
          destination: orders.events
          consumer:
            concurrency: 3
~~~

With the Kafka Streams binder, this property is translated to `num.stream.threads` according to the binder documentation. When a function has multiple input bindings, set concurrency on the first input binding. Verify the exact binder and version in use before applying.

## 6. Kafka Producer: batching, compression, and acknowledgement

A Kafka producer groups records per partition into batches. Larger batches usually reduce the number of requests and improve throughput, but may have to wait for more data before sending. Compression compresses the entire batch, so its effectiveness depends on batch size and how well batches fill.

Properties that commonly need benchmarking:

| Property | Effect | Trade-off |
|---|---|---|
| batch.size | Maximum batch size in bytes | Too small reduces batching; too large uses more memory |
| linger.ms | Time to wait for additional records to form a batch | Can increase latency at low load |
| compression.type | Batch compression (lz4, zstd, snappy, gzip) | Reduces network/disk, costs CPU |
| buffer.memory | Memory the producer uses to buffer records waiting to be sent | Increases burst absorption capability but increases memory usage |
| acks | Level of acknowledgement from the broker | Durability and latency depend on configuration |
| enable.idempotence | Prevents duplicates from producer retries within Kafka producer guarantees | Has specific configuration constraints and overhead |
| delivery.timeout.ms | Upper bound on time to report success or failure for a send | Too low causes false failures during broker slowdowns; too high delays error handling |

Example testing batching and compression on an output binding:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          orders-out-0:
            producer:
              configuration:
                batch.size: 65536
                linger.ms: 5
                compression.type: lz4
                buffer.memory: 67108864
                acks: all
                enable.idempotence: true
~~~

This is a starting point for benchmarking, not a default optimal configuration. Measure p95/p99 latency, producer CPU, batch fill rate, network throughput, and buffer exhaustion count. When increasing `linger.ms`, check latency under low load because sparse messages may have to wait the full linger duration.

The Spring Cloud Stream Kafka binder also has `producer.bufferSize` and `producer.batchTimeout`. `bufferSize` is the binder-side buffer/batch limit; `batchTimeout` is the wait time for additional messages to batch. They have distinct meanings from the Kafka client's `batch.size` and `linger.ms`. Avoid tuning multiple layers at once without knowing which property is actually governing behavior.

`acks=all` together with replication is suitable when data durability is important. Reducing acknowledgement can lower send latency, but it changes the probability of data loss when a broker fails. Only choose an acknowledgement level after defining RPO and durability requirements.

## 7. Synchronous or asynchronous producer?

The Kafka binder has a producer `sync` property. When enabled, the producer waits for the send result instead of continuing immediately; this lets the caller know the send outcome, but can reduce throughput and increase latency on the calling flow.

Use synchronous send when business logic must know the broker has acknowledged before proceeding. If you only need asynchronous publishing, keep it asynchronous and observe the send result/error channel or appropriate metadata. Do not ignore publish failures simply because the API returns quickly.

When you need to observe send results, the Kafka binder can send success metadata to `recordMetadataChannel`; metadata includes partition and offset. This is useful for distinguishing that the function created a message from the broker having recorded it.

## 8. Kafka Consumer: poll, fetch, and batch

A Kafka consumer receives records via `poll()`. Several properties have major impact:

| Property | Role | Trade-off |
|---|---|---|
| max.poll.records | Maximum number of records returned in a single poll | Larger batches increase efficiency but lengthen processing time per poll |
| fetch.min.bytes | Minimum amount of data the broker should return | Larger values can increase throughput but increase waiting |
| fetch.max.wait.ms | Time the broker waits for enough data to fetch | Increasing this can increase batching and latency |
| max.poll.interval.ms | Maximum time between polls | If batch processing takes too long, the consumer may be considered inactive and trigger a rebalance |
| max.partition.fetch.bytes | Limit on data fetched per partition | Needs to match record batch sizes |

Example configuration for an input binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-in-0:
          consumer:
            batch-mode: true
      kafka:
        bindings:
          orders-in-0:
            consumer:
              configuration:
                max.poll.records: 200
                fetch.min.bytes: 65536
                fetch.max.wait.ms: 10
                max.poll.interval.ms: 300000
~~~

When `batch-mode` is enabled, the function receives a `List` or `Message<List<?>>` according to the appropriate signature. Batch processing can reduce function invocation overhead and improve bulk write efficiency. However, large batches increase memory usage, per-poll processing time, and the number of messages that may be redelivered on failure.

With the Kafka binder, binder-level retry is not supported when batch mode is enabled; `maxAttempts` is overridden to 1. If you need retries for batches, you must configure an error handler on the listener container and clearly define how partial batches/offsets are handled. Do not enable batch mode just to boost throughput without checking error semantics.

## 9. Acknowledgement and consumer reliability

Committing offsets after every record reduces the number of records that can be redelivered when a consumer fails, but adds overhead. Committing per batch/poll can improve throughput, but if the process dies mid-batch, some already-processed records may be redelivered.

Choose acknowledgement according to requirements:

- **Record-level acknowledgement**: suitable when you want to limit the duplicate window; may incur additional commit cost.
- **Batch acknowledgement**: suitable for batch processing and high-throughput workloads; requires accepting the possibility of redelivering more records.
- **Manual acknowledgement**: used when the application must control when commits happen; ensure you only ack after work is complete and do not commit beyond records that are genuinely safe.
- **Kafka transaction**: used when you need to synchronize writing Kafka outputs and committing offsets within a single transaction; must configure the appropriate transaction manager and consumer isolation level.

Producer idempotence does not replace business-level idempotency at the consumer. If a consumer writes to a database and fails before the offset is committed, the record may be redelivered. Use a unique event ID, unique constraint, inbox table, or conditional upsert to handle duplicates safely.

## 10. RabbitMQ Consumer: concurrency and prefetch

RabbitMQ distributes messages from a queue to consumers. Two critical parameters are concurrency and prefetch:

- `concurrency`/`maxConcurrency` determines how many consumers can operate concurrently.
- `prefetch` limits the number of unacknowledged messages delivered to each consumer.

A large prefetch can keep consumers busy and increase throughput, but it increases the number of unacked messages held in client memory. With large messages or slow processing, an excessively high prefetch can cause memory pressure. If strict ordering or even distribution across multiple consumers under low load is needed, a low prefetch (possibly 1) is usually more appropriate.

Example configuration:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-in-0:
          destination: orders
          group: order-service
          consumer:
            concurrency: 4
      rabbit:
        bindings:
          orders-in-0:
            consumer:
              max-concurrency: 8
              prefetch: 100
~~~

This example starts with 4 consumers and allows scaling up to 8 consumers per container/binder. A prefetch of 100 is an experimental starting value; measure queue depth, unacked messages, memory, processing latency, and load distribution before keeping the setting.

If strict ordering is needed, consider a single consumer/queue partition or single active consumer with low prefetch. You cannot simultaneously require strict global ordering and arbitrarily increase concurrency on the same queue.

## 11. Batching on RabbitMQ

The Rabbit binder supports both producer-side and consumer-side batching. Producer batching groups multiple messages into a single batch before publishing; consumer batching groups received messages into a `List` to process in one call.

Example consumer-side batching:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-in-0:
          group: order-service
          consumer:
            batch-mode: true
      rabbit:
        bindings:
          orders-in-0:
            consumer:
              enable-batching: true
              batch-size: 10
              receive-timeout: 200
~~~

A batch may be emitted when the count is reached or when the receive timeout expires, so actual batches can be smaller than `batch-size` when traffic is low. Batching reduces per-message overhead but increases wait time to accumulate enough messages. Measure p95/p99 at both low and high load.

Producer-side batching has properties such as `batching-enabled`, `batch-size`, `batch-buffer-limit`, and `batch-timeout`. When using it, verify that the listener handles batches properly and that DLQ/ack semantics are appropriate. Do not confuse batches created by the producer with batches assembled by the consumer; the two mechanisms transfer payloads differently.

## 12. Retry, backoff, and DLQ are part of performance

Retries are not free. A failing message can keep a consumer busy, reduce throughput for that partition/queue, and increase latency for subsequent messages. If you retry every exception, permanent data errors can trigger a retry storm.

Spring Cloud Stream consumer properties include common settings:

| Property | Role | Default value in docs |
|---|---|---:|
| max-attempts | Total processing attempts, including the initial attempt | 3 |
| back-off-initial-interval | First wait interval | 1,000 ms |
| back-off-max-interval | Maximum wait interval | 10,000 ms |
| back-off-multiplier | Backoff multiplier factor | 2.0 |

Only retry transient errors such as brief timeouts or temporarily unavailable dependencies. Schema errors, invalid data, or business rule violations generally belong in reject/DLQ or a data remediation workflow. Use bounded exponential backoff with jitter when needed to prevent multiple consumers from retrying simultaneously.

Example configuration:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-in-0:
          consumer:
            max-attempts: 4
            back-off-initial-interval: 500
            back-off-max-interval: 5000
            back-off-multiplier: 2.0
~~~

With the Kafka binder, if total retry and backoff time exceeds `max.poll.interval.ms`, the consumer may trigger a rebalance. The binder documentation describes moving retry/DLQ to the listener container when total retry time is too long. With the Rabbit binder, avoid `requeueRejected=true` for permanent errors because the message may be redelivered continuously.

A DLQ retains failed messages for investigation and controlled replay. It does not make messages disappear from the business backlog: you need dashboards, alerts, owners, SLAs for remediation, and a replay process. If the DLQ grows continuously, successful throughput may still look good, but pipeline reliability has degraded.

## 13. Kafka reliability: acknowledgement, replication, and transactions

With Kafka, data durability depends on producer acknowledgement, replication, ISR, and broker/topic policies. The Kafka binder currently has the `requiredAcks` property; the binder documentation notes the default is `all`. Producers can use `acks=all` and idempotence to improve safety during producer retries.

Options must be evaluated together:

- `acks=all` requires the broker to wait for acknowledgements from in-sync replicas according to Kafka's rules.
- Replication factor determines the number of topic replicas.
- `min.insync.replicas` at the broker/topic level determines the minimum number of replicas required to accept writes with `acks=all`.
- `enable.idempotence` allows the producer to retry while avoiding duplicates from resends within producer guarantees.
- The transactional binder can combine output records and input offsets in a single Kafka transaction when configured properly.

Do not lower `acks` or `min.insync.replicas` just to hit a benchmark if the requirement is zero loss of acknowledged messages. Also do not call a transaction spanning Kafka and a database "exactly-once" merely because Kafka transactions are enabled; you must design synchronization with systems outside Kafka.

## 14. RabbitMQ reliability: durable, persistent, confirm, and acknowledgement

With RabbitMQ, reliability requires considering exchange/queue durability, message delivery mode, publisher confirms, consumer acknowledgement, queue type, and dead-letter policy. Publisher confirms indicate the broker processed the publish per broker semantics; consumer acknowledgement indicates the message was processed or rejected by the consumer.

These choices affect performance:

- Confirming every publish or waiting on confirms can increase round-trips.
- Batch publish/confirm can increase throughput but widens the failure window.
- Quorum queues provide different replication semantics than classic queues and carry their own resource costs.
- High prefetch increases utilization but holds more unacked messages.
- Transactional channels have higher overhead than non-transactional publish/ack.

Benchmark with the actual queue type and durability settings. Results from temporary, non-durable queues or non-persistent messages cannot predict throughput for production workloads that require durability.

## 15. Backpressure and memory limits

A stable pipeline needs to limit the rate at which messages enter each processing step. If the producer emits faster than the consumer over an extended period, the backlog will grow. If the consumer pulls too many messages into memory, heap and GC can become the bottleneck even before the broker.

Mechanisms to control:

- Cap concurrency and the number of pending async tasks.
- Cap internal queues or buffers between stages.
- Choose `max.poll.records`, `prefetch`, and batch size appropriate for the message size.
- Do not retain the full payload in memory when only metadata or a subset of fields is needed.
- Use I/O timeouts and circuit breakers appropriate for downstream dependencies.
- Do not use `parallel()` or unbounded thread pools to mask a slow dependency.

Reactive functions can use backpressure inside a Reactor pipeline, but not every binder/transport supports end-to-end backpressure in the same way. Verify the capabilities of your binder; the broker queue can still grow even if downstream Reactor has a bounded request pattern.

## 16. Isolate bottlenecks stage by stage

When latency or lag rises, measure each segment rather than increasing concurrency across the whole system:

| Symptom | Where to check | First action |
|---|---|---|
| Producer latency increases | Serialization, compression, buffer, broker ack, network | Measure send time, batch fill, buffer exhaustion, and broker request latency |
| Kafka lag grows on one partition | Hot key, partition assignment, consumer processing time | Check key distribution, partition lag, and per-key processing |
| Lag grows on all partitions | Consumer capacity lower than arrival rate | Measure CPU/I/O, increase workers within limits, optimize logic |
| Rabbit queue depth grows, consumer utilization is low | Consumer blocked, low prefetch, or slow dependency | Check unacked, prefetch, thread pools, and downstream |
| High p99 but low p50 | Tail events, retries, GC, hot partition, or I/O timeouts | Break down traces and per-step time distributions |
| Heap grows with backlog | Large buffer/prefetch/batch or payload retention | Reduce in-flight messages, limit concurrency, analyze heap |
| Repeated rebalances | Poll interval exceeded, dead/slow consumer, or frequent deploys | Reduce batch/work per poll, check retries and `max.poll.interval` |
| DLQ grows | Poison messages, schema incompatibility, or dependency errors | Classify exceptions, retry selectively, fix contract/data |

A common bottleneck lies in a downstream dependency such as a database, HTTP API, or object storage. Adding consumers only increases concurrent requests to that dependency, which can trigger even more errors and retries.

## 17. Repeatable benchmark workflow

### Step 1: Record a baseline

Run with the current configuration and record:

- Ingress throughput, processed throughput, and output throughput.
- p50/p95/p99 end-to-end latency.
- Consumer lag or queue depth and the rate of backlog change.
- CPU, heap, GC pauses, thread count, network, and disk.
- Broker request latency, bytes in/out, under-replicated partitions, or unacked messages.
- Retry, DLQ, timeout, duplicate, and error rates.

### Step 2: Run multiple load profiles

1. **Warm-up:** let the JVM, JIT, and connection pools stabilize.
2. **Steady load:** hold the target load long enough to measure stability.
3. **Peak load:** ramp up to the expected peak load.
4. **Burst:** send a rapid spike for a short period and measure backlog drain time.
5. **Soak:** run for a long duration to uncover memory leaks, GC issues, or connection/resource exhaustion.
6. **Failure:** stop a consumer or broker/node per test scenario to verify recovery.

### Step 3: Change one configuration group at a time

For example, test in sequence:

- Increase consumer concurrency while keeping partition count fixed.
- Increase partitions if more parallelism is needed and key distribution allows.
- Test different batch sizes or `max.poll.records`.
- Test producer compression and linger.
- Test RabbitMQ prefetch/concurrency.
- Test retry/backoff and acknowledgement policies.

Keep the workload and environment constant across runs. Record configuration, binder/client versions, payload size, and results so the benchmark is reproducible.

### Step 4: Select configuration against SLOs

Choose the smallest configuration that meets target throughput and latency with headroom for bursts while still satisfying durability and recovery requirements. Do not pick a configuration solely for peak throughput if p99 exceeds the threshold or the backlog cannot drain.

## 18. Example tuning plan for an order flow

Suppose the flow has:

- Kafka topic `orders.events`.
- One consumer group `order-service`.
- A function that validates data, calls an inventory service, and writes results to `orders.accepted`.
- Target load 1,200 msg/s, burst 2,400 msg/s for 2 minutes.
- Requirement: p95 end-to-end under 300 ms and p99 under 1.2 s.

Plan:

1. Measure function time and inventory call time separately. If the inventory dependency accounts for 80% of latency, tuning serialization or Kafka batching will not fix p99.
2. Check partition count and key distribution. If a single customer key generates most of the traffic, check for a hot partition.
3. Measure consumer lag per partition. If all partitions grow evenly, overall capacity is too low; if one partition grows alone, there may be key skew.
4. Try increasing concurrency within the partition count limit and monitor CPU/dependencies.
5. Try batch mode if the logic can process a list and accepts batch-mode retry/DLQ semantics.
6. Try producer batching/compression for output and check p95/p99.
7. Run a burst test, then measure backlog drain time. Do not conclude the SLO is met based only on the moment the burst ends.
8. Stop one instance, wait for rebalance, and confirm messages continue processing without data loss.

If calling inventory synchronously per message, consider a bulk API or controlled caching. If using a bulk API, preserve per-order idempotency and know how to handle partial batch failures.

## 19. Monitoring in production

A performance dashboard should display signals over the same time window:

- Ingress, processed, and completed throughput.
- p50/p95/p99 latency per binding and per step.
- Kafka consumer lag by topic/partition/group; Rabbit queue depth and unacked counts.
- Producer send latency, errors, retries, and batch/compression metrics.
- Consumer concurrency, active/idle consumers, and partition assignments.
- DLQ rate, retry rate, redeliveries, and message age.
- CPU, heap, GC pauses, thread pools, connection pools, and network.
- Broker health, replication/ISR, disk, request latency, and throttling.

Set alerts based on SLOs and rate of change, not just a fixed queue depth threshold. For example, a backlog of 50,000 messages may be normal for a consumer processing 20,000 msg/s, yet critical for a consumer processing only 200 msg/s. Combine queue depth, oldest-message age, processing rate, and estimated drain time.

## 20. Common tuning mistakes

**Increasing concurrency without increasing partitions.** With Kafka, extra consumers create no additional parallelism if there are no partitions to assign. With RabbitMQ, excessive concurrency can overload downstream dependencies.

**Increasing batch size to cut overhead while ignoring latency.** Batches wait for enough messages or a timeout; at low load, messages can wait a long time. Large batches also increase memory and the number of messages that may be redelivered.

**Setting very high prefetch for large messages.** Many unacked messages in flight at once can consume heap, increase GC, and reduce stability.

**Retrying every exception.** Poison messages or business errors will repeat, keeping partitions/consumers busy and growing the backlog.

**Lowering acknowledgement to gain throughput.** Benchmark numbers may look better, but RPO and redelivery guarantees have changed.

**Measuring only producer throughput.** A sent message is not necessarily finished by the consumer, nor is its output necessarily confirmed by the broker.

**Running benchmarks that are too short.** JIT, caches, connection pools, and batching have not stabilized; results do not represent production.

**Tuning multiple properties at once.** When results change, you will not know whether the cause was concurrency, batching, compression, or acknowledgement.

## 21. Pre-release checklist

- [ ] Throughput, p95/p99 latency, backlog recovery, and reliability SLOs are clearly documented.
- [ ] Load tests include realistic payload size, key skew, bursts, and error rates.
- [ ] Baseline ingress, processing, and completion rates were measured separately.
- [ ] Partition count matches parallelism and ordering requirements.
- [ ] Consumer concurrency does not exceed broker, partition, or dependency capacity.
- [ ] Producer batching/compression was tested under both low and high load.
- [ ] Consumer batch/prefetch stays within memory and poll/ack time limits.
- [ ] Retries apply only to transient errors; poison messages have a DLQ or remediation workflow.
- [ ] Acknowledgement, replication, idempotence, and transactions meet durability requirements.
- [ ] Duplicates are handled idempotently at the business layer.
- [ ] Post-burst backlog drain meets the target.
- [ ] Consumer restarts, rebalances, and broker/dependency outages were tested.
- [ ] Dashboards cover p95/p99, lag/queue age, retry/DLQ, and runtime resources.
- [ ] Benchmarks are reproducible with the same workload and configuration.

Spring Cloud Stream performance is the combined result of producer, broker, consumer, function, and dependencies. Establish SLOs first, calculate capacity and parallelism from the workload, and then tune batching, concurrency, partitions, prefetch, retries, and acknowledgement for your specific binder. A good configuration must achieve target throughput, keep p95/p99 within bounds, drain backlog after bursts, and maintain the committed delivery semantics.

## References

- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Cloud Stream — Kafka Binder Reference Guide](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-kafka.html)
- [Spring Cloud Stream — RabbitMQ Binder Reference Guide](https://docs.spring.io/spring-cloud-stream-binder-rabbit/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html)
- [Apache Kafka — Producer Configuration](https://kafka.apache.org/44/configuration/producer-configs/)
- [Apache Kafka — Consumer Configuration](https://kafka.apache.org/44/configuration/consumer-configs/)
- [Spring AMQP — Message Listener Container Configuration](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html)
- [Spring AMQP — Listener Concurrency](https://docs.spring.io/spring-amqp/reference/amqp/listener-concurrency.html)
