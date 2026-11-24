# Load Testing with Realistic Partitions

A Kafka load test is only meaningful when its topic structure, key distribution, consumer count, and data processing complexity mirror the real operational environment. A test using a 3-partition topic, tiny payloads, and a consumer that simply reads and discards records can post very high throughput, yet those numbers cannot predict the capacity of a system running 24 partitions, hot keys, and database writes.

The goal of the test is to find the load level the entire pipeline can sustain for a sufficient duration while keeping latency and consumer lag within SLOs, with enough headroom left for bursts and common failures. Results must answer: how many records or bytes per second the system processes steadily, whether the bottleneck sits in the producer, broker, consumer, or downstream services, and how many partitions and consumers are needed for the expected load.

## 1. Why Test with Realistic Partition Counts?

Partitions are Kafka's unit of storage and parallel distribution. Within a consumer group, at any given time, each partition is assigned to at most one consumer. Therefore, how many consumers can process in parallel inside a group is bounded by the assigned partition count.

For example, for a 12-partition topic:

- One application instance with concurrency 4 creates at most 4 consumers in the group.
- Three instances, each with concurrency 4, can create 12 consumers total and utilize all 12 partitions.
- Four instances, each with concurrency 4, create 16 consumers; at most 12 consumers receive partitions, leaving 4 consumers with no partitions to read.

Concurrency in Spring Kafka is the number of consumer threads created by a listener container. When running multiple pods or instances, sum consumers across all instances in the same group:

**Total consumers = instance count × concurrency per instance**

The number of consumers able to work in parallel never exceeds the partitions actively used by the group. Raising concurrency past partition count does not increase group processing capacity; it also spawns extra consumers and complicates group management.

Partition count also affects how producers distribute records. When producers send keyed records, the partitioner typically routes identical keys to the same partition to preserve per-key order. An overly frequent key can turn one partition into a hot spot while other partitions still have ample capacity. If tests only use random or uniform keys, production load skew will never surface.

Adding partitions is not free either. Every partition carries metadata, log segments, indexes, and replica work that brokers must manage. Increasing partitions can alter key-to-partition mapping for newly produced records; thus, ordering for the same key across that time boundary may no longer land on the same partition as before. Pick partition count based on parallelism needs, measured throughput, and operational limits, then verify through testing.

## 2. Describe a Production-Like Workload

Before running tests, clearly document the workload the test must represent. Writing merely "1,000 records/second" is insufficient because processing cost also depends on record size, key count, key distribution, data types, and consumer work.

| Attribute | What to Define |
|---|---|
| Throughput | Average load, peak-hour load, bursts, and ramp-up rate |
| Record size | Distribution of small, medium, and large payloads; serialized byte size |
| Keys | Whether keys are actually used, key cardinality, and per-key frequency |
| Distribution | Uniform or skewed; whether hot keys or key groups dominate traffic |
| Event types | Proportions of each event type, headers, schemas, and field sizes |
| Producer | Application count, producer count, send rate, and batching settings |
| Consumer | Instance count, concurrency, synchronous vs. asynchronous processing |
| Downstream processing | API calls, database queries, cache writes, business logic, or downstream publishing |
| Latency | Acceptable duration from send until business processing completes |

Use real data distributions or synthetic data with matching characteristics. There is no need to copy sensitive production data. If production payloads span multiple sizes, generate test data with a matching distribution rather than using one fixed record. If certain keys carry most traffic, preserve that ratio in tests.

Specifically, distinguish three types of latency:

1. **Producer send latency:** time the producer waits for Kafka to acknowledge the record.
2. **Consumer processing latency:** time the consumer takes to process a record or batch.
3. **End-to-end latency:** time from when the event is created or sent until the business task finishes.

Producers can send very fast while consumer lag grows continuously. Measuring send speed alone hides a pipeline falling behind.

## 3. Prepare the Environment and Topics

The test environment should match attributes that directly govern Kafka capacity:

- Same partition count as production topics, or the exact partition count planned after expansion.
- Same replication factor and durability policy, including producer acknowledgment and `min.insync.replicas`.
- Equivalent broker count, disk types, I/O limits, network, and Kafka version.
- Equivalent retention, compression, TLS, authentication, and quota settings when present in production.
- Same application version, serializers, producer/consumer configs, and instance deployment layout.
- Same database or downstream service types, connection pools, and resource limits if they sit on the processing path.

If production cannot be replicated completely, document the differences explicitly. Do not extrapolate results from a single broker to a multi-broker cluster with replication without additional measurements.

Create a dedicated test topic on the cluster for load testing. The example below creates a 24-partition topic with replication factor 3:

~~~bash
kafka-topics.sh \
  --bootstrap-server broker1:9092 \
  --create \
  --topic orders-load-test \
  --partitions 24 \
  --replication-factor 3
~~~

Verify topic structure and replicas:

~~~bash
kafka-topics.sh \
  --bootstrap-server broker1:9092 \
  --describe \
  --topic orders-load-test
~~~

Compare partition count, leaders, and replicas against target settings before running. If the environment uses TLS or SASL, pass a client configuration file via the appropriate command-config option.

Never run load tests against production topics without an approved plan. Test load can consume shared CPU, network, disk I/O, connections, and quotas; test data can also trigger real business consumers if the wrong topic or group is used.

## 4. Application Settings to Keep Consistent

The Spring Boot configuration example below illustrates properties typically held constant during measurements. Values are starting points only; replace them with the real configuration of the system under test.

~~~yaml
spring:
  kafka:
    bootstrap-servers: broker1:9092,broker2:9092,broker3:9092
    producer:
      acks: all
      properties:
        enable.idempotence: true
        linger.ms: 5
        batch.size: 65536
        compression.type: lz4
    consumer:
      group-id: orders-load-test
      enable-auto-commit: false
      max-poll-records: 500
      properties:
        max.poll.interval.ms: 300000
    listener:
      concurrency: 12
      ack-mode: batch
~~~

Key considerations:

- **acks and replication:** if production uses `acks=all` and replication factor 3, testing with `acks=1` or replication factor 1 measures a system with different durability and cost.
- **Idempotence and retries:** keep producer configs equivalent to production. Retries can raise send times and alter observed ordering if misconfigured.
- **Batching and compression:** `linger.ms`, `batch.size`, and `compression.type` affect throughput, CPU, network size, and latency. Measure with production settings first, then vary one parameter at a time in separate benchmark runs.
- **Consumer polling:** `max.poll.records` and `max.poll.interval.ms` must match processing duration. If processing a batch takes too long, the consumer can exceed the poll interval and be deemed inactive, triggering a rebalance.
- **Acknowledgment and commits:** keep ack modes, transactions, and commit behavior identical to the real application. Changing these can alter latency, replay behavior, and processing semantics.

If production uses Kafka transactions or exactly-once semantics, tests must include that transactional path. A consumer that merely reads records and commits quickly cannot represent a consumer executing business logic and committing transactions.

In Spring Kafka, total concurrency must be summed across all instances. For instance, 3 pods with concurrency 4 create 12 consumers in the same group. If a topic has 24 partitions, the group may still have underutilized partitions; with 8 pods at concurrency 4, at most 24 consumers receive partitions simultaneously.

## 5. Run Baselines to Separate Kafka Capacity from Application Capacity

Measure each layer before running integrated tests. Kafka's bundled benchmark tools are useful for establishing broker reference baselines:

~~~bash
kafka-producer-perf-test.sh \
  --topic orders-load-test \
  --num-records 1000000 \
  --record-size 1024 \
  --throughput -1 \
  --producer-props \
    bootstrap.servers=broker1:9092 \
    acks=all \
    linger.ms=5 \
    batch.size=65536 \
    compression.type=lz4
~~~

Measure consumer baseline on the same topic:

~~~bash
kafka-consumer-perf-test.sh \
  --bootstrap-server broker1:9092 \
  --topic orders-load-test \
  --messages 1000000 \
  --group orders-perf-baseline \
  --from-beginning
~~~

Perf test tools provide useful baselines, yet their workloads are simpler than real applications. Producer perf test with fixed records does not reflect application key distributions, payloads, or callbacks. Consumer perf test does not reflect business logic, databases, or APIs either. Use them to locate relative broker limits, then run real load generators and application consumers for end-to-end measurement.

In integrated tests, track record counts per partition via producer metadata or application metrics. A producer callback can capture which partition Kafka chose for each record:

~~~java
producer.send(new ProducerRecord<>(topic, key, payload), (metadata, exception) -> {
    if (exception != null) {
        sendErrorCounter.increment();
        return;
    }

    sentByPartition
        .computeIfAbsent(metadata.partition(), ignored -> new LongAdder())
        .increment();
});
~~~

This is a clean way to observe per-partition record distribution in a load generator. In real applications, keep metric cardinality controlled; avoid creating labels per record key or ID.

## 6. Design Load Test Phases

A good test run separates warm-up, steady load, bursts, and recovery into distinct phases. Keep configurations constant between comparison runs; change only one intentional variable group.

### 6.1. Warm-Up and Baseline

Start producers, consumers, and downstream services. Wait for caches, connection pools, JVM JIT, and background components to stabilize. Record baseline metrics under minimal load to establish idle CPU, memory, network, and lag.

Then run light load for several minutes. Confirm records distribute across the right partitions, consumer group assignments match expectations, and no serialization, authentication, or commit errors appear.

### 6.2. Ramp-Up and Steady Load

Step load up incrementally—for example, 10%, 25%, 50%, 75%, 100%, and 120% of target load. Hold each step long enough to observe trends rather than reading a momentary throughput sample. Hold times can start at 15–30 minutes and extend longer for systems with long processing cycles.

At each step, record:

- Producer throughput in records/second and bytes/second.
- Producer send latency p50, p95, p99, and send error rate.
- Consumer throughput, processing latency, and lag per partition.
- End-to-end latency from event creation to processing completion.
- Broker CPU, disk I/O, network, request queues, and replica health.
- Application and downstream service resources.

A load level counts as sustainable only when consumers keep pace with producers, lag does not climb steadily over time, latency stays within SLOs, and errors do not spike abnormally.

### 6.3. Burst and Recovery

Generate a load burst above normal levels for a fixed window, then drop load back to normal. The goal is observing backlog buildup, time for consumers to clear the backlog, and post-burst stability.

Do not record only peak throughput. Measure **recovery time**: the time from when load returns to normal until lag drops back to target levels. If lag fails to drop even after producers throttle back, consumers or downstream services may be bottlenecked.

### 6.4. Soak Test

Sustain production-representative load for an extended period—such as 1–4 hours or longer depending on goals. Soak tests expose cumulative issues like creeping memory growth, prolonged GC, connection leaks, full disks, rapid log segment growth, accumulating retries, or drifting consumer lag.

Watch both data growth rate on brokers and remaining disk space. Retention and write speeds can fill cluster disks even while short-term throughput looks healthy.

### 6.5. Rebalances and Consumer Count Changes

In a dedicated test environment, stop one consumer at a time, restart instances, or change instance counts. Record:

- Time for the group to detect membership changes and complete rebalancing.
- Duration during which consumers pause processing.
- How much lag accumulates during the rebalance.
- Time for the group to return to normal throughput.
- Whether duplicates, reprocessing, or commit errors occur relative to application semantics.

This test is especially critical when concurrency is high, partition counts are large, or batches take long to process. Frequent rebalances can drive real throughput far below steady-group benchmarks.

## 7. Measure Partition Distribution and Consumer Lag

Never look only at total group lag. Total lag can hide one congested partition while remaining partitions sit nearly empty. Track lag, throughput, and processing time per partition.

Inspect the group using Kafka tools:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker1:9092 \
  --describe \
  --group orders-load-test
~~~

Output normally shows current offset, log end offset, and lag for each partition. Pair this with application metrics to locate which partition builds lag or processes slowly.

Check three distribution dimensions:

1. **Records per partition:** which partition receives the most records?
2. **Bytes per partition:** variable record sizes can balance record counts while leaving bytes unbalanced.
3. **Consumer processing time per partition:** identical record counts with differing payloads or keys can carry very different processing costs.

If one partition receives most traffic, identify which key causes the skew and check partitioner logic. Do not blindly switch to random keys just to make charts look balanced: that can break per-key ordering requirements. If business logic requires ordering, re-evaluate key design, data sharding, or dedicated handling for hot keys.

Consumer lag is the offset gap between the latest record on the broker and the offset the consumer has processed or committed, depending on tooling and commit strategy. Lag does not directly equal business delay. To measure event age, record event creation timestamps and completion timestamps, then compute end-to-end latency. Both lag and event age are useful, yet answer different questions.

## 8. Metrics to Observe

| Component | Metrics to Monitor | Signals to Investigate |
|---|---|---|
| Producer | Records/sec, bytes/sec, send latency, retries, errors, buffer waits | Rising send latency, frequent retries, or producer blocking on buffers |
| Broker | CPU, disk I/O, network, request handler idle, request queue, produce/fetch latency | Saturated CPU or disk, growing request queue, lengthening request processing |
| Replica | Under-replicated partitions, ISR shrink/expand, replica fetch lag | Followers falling behind or ISR flapping |
| Consumer | Records/sec, processing time, poll interval, commit errors, rebalances, per-partition lag | Steadily rising lag, slow processing, poll timeouts, or repeated rebalances |
| Application | CPU, heap, GC pauses, thread pools, connection pools, exceptions | Blocked threads, long GC, exhausted pools, or rising exceptions |
| Downstream services | DB latency, query rate, connection usage, API latency and errors | Consumers waiting on downstream, slowing polls and processing |

On brokers, observe load both per node and per partition/leader. One broker can become a hot spot if it hosts many leaders of high-traffic partitions. On consumers, inspect partition assignments alongside processing time and lag to distinguish too few consumers from one heavy-workload partition.

If using Micrometer or another monitoring system, standardize metric names, units, and sampling intervals across test runs. Align dashboard and log timelines with the load generator so cause and effect stay clear when latency or lag shifts.

## 9. Estimating Capacity from Results

Use steady-state throughput measured under production-like conditions, not a few-second peak spike. For a specific workload, initial partition count can be estimated as:

~~~text
required partitions
    = ceil(target throughput / measured safe throughput per partition)
~~~

For example, if one partition sustains 800 records/second with the chosen payload, replication, and consumer processing, and target load is 12,000 records/second, initial division gives 15 partitions. This is only an estimate. Partition throughput is not completely independent because partitions share CPU, network, disk, and brokers. Re-test with the planned total partition count, real replication factor, key distribution, and actual consumer count.

Leave headroom for peaks, bursts, rebalances, broker maintenance, and traffic growth. Headroom levels should reflect SLOs, load volatility, and scaling time; no fixed percentage fits every workload.

When reporting capacity, explicitly state:

- Steady-state throughput in records/second and bytes/second.
- p95/p99 producer latency and end-to-end latency.
- Normal consumer lag, peak lag, and post-burst recovery time.
- Partition count, replication factor, broker count, and topic configs.
- Producer count, consumer count, instance count, and concurrency per instance.
- Record sizes, key distribution, compression, and acknowledgment config.
- Broker, application, and downstream resource usage at that load.
- Observed bottlenecks and conditions under which results no longer hold.

## 10. Reading Results and Finding Bottlenecks

| Symptom | Possibilities to Check |
|---|---|
| Rising producer latency, high broker CPU or request queue | Brokers or network approaching limits |
| Producer sends fast while lag climbs steadily | Consumers or downstream failing to keep up |
| One partition has high lag while others are low | Hot keys, skewed key distribution, or uneven processing |
| Adding consumers does not change throughput | Hit partition, broker, or downstream limits |
| Frequent consumer rebalances | Batch processing too long, improper poll interval, unstable instances, or group churn |
| High broker disk I/O, rising replica lag | Disk or replication bounding throughput |
| Low consumer CPU yet high processing time | Likely waiting on DB, APIs, locks, or connection pools |
| Initial throughput good, then degrades over time | Check GC, memory, disk growth, connection leaks, retries, and downstream backlog |

Vary one factor at a time in controlled runs. For instance, if concurrency is suspect, hold producer rate, payloads, partition count, and broker configs steady and change only concurrency. Raising partitions, adding consumers, and changing batch sizes simultaneously makes it impossible to tell which change produced the result.

## 11. Test Completion Criteria

Before starting, define acceptance criteria tied to system SLOs. A typical set includes:

- Target throughput sustained throughout the full hold window.
- Adequate headroom above projected peak.
- p95 and p99 end-to-end latency within bounds.
- Consumer lag steady at normal load and draining to acceptable thresholds after bursts.
- No prolonged abnormal send, processing, commit, or retry errors.
- No prolonged under-replicated partitions or continuously shrinking ISR.
- Application, brokers, and downstream services free of resource saturation.
- After consumer restarts or rebalances, the group recovers within acceptable time.

A failed test is still valuable if it pinpoints a bottleneck and reproducible conditions. Record the load at which degradation began, which metric moved first, affected partitions, and attempted configuration changes.

## 12. Common Errors That Skew Test Results

1. **Using fewer partitions than production:** results fail to reflect real parallelism, leader distribution, and metadata cost.
2. **Omitting hot keys:** traffic spreads evenly in tests yet concentrates on one partition in production.
3. **Measuring only the producer:** high producer throughput does not prove consumers can keep up.
4. **Consumers skipping real business work:** omits serialization, validation, database, API, and commit costs.
5. **Using different replication or acknowledgment settings:** benchmarks measure a different durability tier than production.
6. **Not tracking lag per partition:** total lag hides hot partitions or lagging consumers.
7. **Running for only a few minutes:** misses GC, memory leaks, retention, disk growth, and cumulative degradation.
8. **Changing multiple settings at once:** prevents attributing improvements or regressions.
9. **Ignoring rebalances:** steady-group benchmarks miss recovery time when instances change.
10. **Sharing environments with uncontrolled workloads:** noise from other applications makes results non-repeatable.

## 13. Pre-Conclusion Checklist

- [ ] Topic has the target partition count and replication factor.
- [ ] Brokers, Kafka version, storage, network, and durability settings are documented.
- [ ] Workload has production-like record sizes, key distribution, and event ratios.
- [ ] Producers, consumers, instance counts, and concurrency are defined.
- [ ] Measured broker baseline and integrated tests with the real application.
- [ ] Dashboards show throughput, latency, per-partition lag, and downstream resources.
- [ ] Executed ramp-up, steady-state, burst/recovery, and soak tests.
- [ ] Tested consumer restarts or rebalances in the test environment.
- [ ] Results state test conditions, bottlenecks, SLOs, and headroom.

A trustworthy capacity conclusion is always bound to a specific configuration and workload. Whenever partition counts, key distributions, replication, payloads, or consumer logic change significantly, re-run the corresponding benchmarks before using old results to commit system capacity.
