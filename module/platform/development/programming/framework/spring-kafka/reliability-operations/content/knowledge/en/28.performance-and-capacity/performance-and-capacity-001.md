# Throughput and Latency

In Spring Kafka operations, throughput and latency are two metrics that describe a system's processing capability from two different perspectives. Throughput indicates how much data the system processes per unit of time. Latency indicates how long a record must wait from the time it is sent until it reaches the processing milestone the application cares about. A Kafka cluster can achieve high throughput while still making users wait a long time; conversely, low latency under light load does not prove the system has enough capacity to handle peak-hour traffic.

When designing or optimizing Spring Kafka, you need to measure both metrics on the same data flow, clearly define the start and end points of the measurement, and then identify bottlenecks in the producer, broker, consumer, or business processing layer. The operational goal is to handle real-world traffic with appropriate latency, maintain resilience under fluctuations, and retain sufficient headroom for traffic spikes or a broker failure.

## 1. Understanding Throughput Properly

**Throughput** is the amount of work completed in a unit of time. With Kafka, it is usually necessary to track at least two representations:

- **Records per second (records/s):** the number of records sent, persisted, or consumed per second.
- **Bytes per second (bytes/s, KiB/s, MiB/s):** the amount of data transferred or processed per second.

These two units complement each other. A system processing 20,000 small records per second may consume less bandwidth than a system processing 2,000 large records per second. Therefore, reporting throughput solely in records/s can hide pressure on the network and disk; reporting solely in bytes/s does not show how many logic invocations the application must process.

You should distinguish throughput at each stage:

| Scope | Question to Answer | Measurement Examples |
|---|---|---|
| Producer | How much data is the application generating and sending? | Records successfully sent/sec, bytes sent/sec |
| Broker | How much data is the Kafka cluster receiving, writing, and serving? | Bytes in/out, request rate, replication traffic |
| Consumer | How much data is the consumer group processing? | Records consumed/sec, bytes fetched/sec |
| Business | How many events have completed the final task? | Number of orders, payments, or updates processed/sec |

Input throughput and output throughput do not necessarily match in every time interval. The consumer can process more slowly than the producer and build lag; it can also process faster than the producer for a period to catch up on a backlog. For a steady data stream, if the production rate continuously exceeds the consumption rate, lag will grow over time, even if neither the producer nor the consumer has encountered any errors.

For example, the producer sends an average of 8,000 records/s, while the consumer only completes 6,500 records/s. The backlog grows by about 1,500 records per second. Increasing producer throughput in this situation only makes the problem worse; you need to find the bottleneck in the consumer or increase consumption capacity.

## 2. Understanding Latency Properly

**Latency** is the duration from a clearly defined start milestone to a clearly defined end milestone. In a Kafka system, the term “latency” can refer to several different intervals:

- **Producer send latency:** the time from when the application calls send for a record until the producer receives a success or failure result.
- **Broker request latency:** the time it takes a broker to process a Kafka request. This metric does not represent the entire time an event takes to travel through the system.
- **Consumer processing latency:** the time it takes the consumer to receive a record and complete business processing.
- **End-to-end latency:** the time from when the event is created at the source until the target task completes.

A measurement is only useful when both ends of the interval are defined consistently. For example, measuring the time until the producer receives a success callback is not equivalent to measuring the time until an order is written to the database by the consumer. If the business requirement is “an event must appear in the target system within two seconds,” you must measure up to the point when the target system confirms completion.

Latency is usually analyzed using percentiles rather than just averages:

| Metric | Meaning |
|---|---|
| p50 | Half of the measurements have latency at or below this value; represents the typical experience |
| p95 | 95% of the measurements have latency at or below this value; helps reveal most slow cases |
| p99 | 99% of the measurements have latency at or below this value; sensitive to prolonged slowdowns in a small fraction of requests |
| max | The maximum observed value; useful during investigation, though easily dominated by a single outlier |

For example, a p50 of 40 ms but a p99 of 2.5 seconds shows that most events are processed quickly, yet a small subset must wait a very long time. Looking only at the average can miss this issue. When defining an SLO, specify the percentile, measurement window, and event scope—for example, “p99 end-to-end under 1 second over a 5-minute window.”

## 3. Relationship Between Throughput and Latency

Throughput and latency are related, but they cannot substitute for each other. When load is still low, the system has idle resources and can process records immediately. As load approaches capacity limits, requests must wait in queues, the producer must wait for buffers, the broker must schedule requests, and the consumer must wait to process. Queuing causes latency to rise rapidly as service capacity nears saturation.

Batching is a clear example of this trade-off. Grouping multiple records into a batch on the producer reduces the number of requests and improves data transfer efficiency. However, a record may have to wait longer for the batch to grow large enough. Increasing `linger.ms` sometimes improves throughput and lowers per-request overhead, but it also adds intentional wait time. Decreasing `linger.ms` can reduce wait time at low load, yet produces smaller batches at high load.

A useful relationship when analyzing systems is Little's Law:

\[
L = \lambda \times W
\]

Where:

- `L` is the average number of items currently in the system or waiting to be processed.
- `λ` is the average completion rate, such as records/s.
- `W` is the average time an item spends in the system, in seconds.

If a processing pipeline completes 10,000 records/s and each record stays in the system for an average of 0.1 seconds, the average number of records currently being processed or waiting within the measurement boundary is approximately 1,000. This relationship helps estimate the amount of work in flight within the system; you must use the same measurement boundary and steady-state conditions when applying it.

You should not optimize throughput at any cost. If increasing batch size or concurrent requests causes p99 to exceed the SLO, that change does not fit the business requirements. Conversely, if latency is very low while CPU, network, and brokers still have plenty of headroom, you can increase batching or concurrency to make better use of resources.

## 4. Where Does Latency Originate in a Kafka Flow?

An event passes through multiple stages before completing. The diagram below illustrates the intervals that typically need to be separated during an investigation:

```text
Application creates event
        |
        v
Producer serializes and waits for batch/buffer
        |
        v
Sends request over the network
        |
        v
Broker receives, writes log, and handles replication
        |
        v
Consumer fetches records
        |
        v
Application executes business processing
        |
        v
Writes result / commits offset
```

Total end-to-end latency can be broken down into the time spent in the stages above, but you must avoid double-counting overlapping metrics. For example, the time the producer waits for a callback can include network time and broker processing; do not add those entire intervals again if they are already included in the producer measurement.

Common sources of slowness include:

1. **Producer application:** CPU-intensive JSON or Avro serialization, generating large payloads, blocked sending threads, buffer exhaustion, or waiting for metadata.
2. **Network:** latency between the application and brokers, saturated bandwidth, retransmissions, or unstable connections.
3. **Broker:** growing request queues, busy CPU, resource-intensive TLS or compression handling, slow disk writes, delayed replication, or uneven leader distribution.
4. **Consumer:** fetch waiting for enough data, low active consumer count, slow business processing, slow external service calls, or inappropriate offset commits.
5. **Downstream systems:** databases, HTTP services, caches, or locks in the application becoming the bottleneck after the consumer has fetched the data.

## 5. Factors Affecting Throughput and Latency

### 5.1. Producer and Batching

A Kafka producer sends records in batches per partition. A larger batch generally reduces the number of requests per record, improves compression efficiency, and utilizes bandwidth better. Commonly reviewed settings include:

| Configuration | Primary Impact | Considerations |
|---|---|---|
| `batch.size` | Limits batch size in bytes | Too small a batch increases request count; too large a batch can increase memory usage and data accumulation wait time |
| `linger.ms` | Time the producer can wait for more data to form a batch | Larger values can improve batch efficiency but add latency, especially under low load |
| `buffer.memory` | Memory capacity the producer allocates for records waiting to be sent | A small buffer easily causes blocking; increasing the buffer does not solve a broker or network lacking capacity |
| `compression.type` | Compresses batches before transmission | Reduces bytes over the network and log size; in return, consumes CPU and depends on data characteristics |

Compression helps most when payloads have repetitive patterns or compressible structure. Already-compressed or high-entropy data may not shrink much. Measure transmitted bytes, producer/broker CPU, and latency before choosing a codec. The codec must be supported by the client and broker versions in use.

Asynchronous producer sends allow the application to keep working while requests are in flight. However, the application must observe callbacks or future results to detect send failures. Ignoring send outcomes can make throughput look high on the surface while data is actually lost or errors go unhandled.

If the producer runs out of buffer space, send calls may have to wait until space frees up or `max.block.ms` expires. Monitor available buffer memory, buffer wait time, and timeout errors. Increasing `buffer.memory` only helps absorb short bursts; if the long-term send rate exceeds the rate brokers can accept, the queue continues to grow.

### 5.2. Partitions and Key Distribution

Partitions enable parallel processing. A producer can write to multiple partitions, and a consumer group can assign partitions across multiple consumers. However, total partition count does not automatically translate into high throughput if broker, network, or application resources are already saturated.

The key determines how records are distributed across partitions when using the default partitioner. Records with the same key generally go to the same partition, preserving per-key ordering within that partition. If one key appears too frequently, the corresponding partition can become a **hot partition**: one consumer must process most of the data while other consumers sit idle.

When considering increasing partitions, keep in mind:

- The maximum number of consumers that can work in parallel within a group is bounded by the number of partitions assigned to that group.
- Adding partitions can improve load distribution, but also increases metadata, management overhead, log segment count, and replication work.
- Changing a topic's partition count can alter how keys map to partitions in the future; consider ordering requirements and how the application relies on partitions.
- Leaders and replicas must be distributed evenly across brokers. Many partitions whose leaders are concentrated on a single broker still create a bottleneck.

Check traffic per partition instead of looking only at the topic total. Large disparities across partitions can indicate key skew or uneven leader distribution.

### 5.3. Broker, Disk, and Replication

Brokers receive requests, write data to logs, and serve fetch requests. Throughput is constrained by multiple interacting resources:

- **Network:** bytes in/out, connection throughput between brokers and between clients and brokers.
- **Disk:** write, read, and log segment maintenance capacity; Kafka relies on the OS page cache, so both memory pressure and disk activity must be monitored.
- **CPU:** request processing, TLS, compression/decompression, checksums, and background tasks.
- **Replication:** the leader streams data to followers; replication traffic shares network resources and can affect client-serving capacity.
- **Load distribution:** leaders, partitions, and replicas must be balanced properly across brokers.

`acks` affects when the producer receives acknowledgment. With `acks=0`, the producer does not wait for broker acknowledgment; with `acks=1`, the leader acknowledges after writing to its local log; with `acks=all`, the leader waits for replicas in the ISR to satisfy the acknowledgment condition. Configuring `acks=all` is commonly paired with an appropriate replication factor and `min.insync.replicas` to increase data durability. In return, acknowledgment time may increase, and a lack of replicas in the ISR can prevent the producer from sending when write requirements are no longer satisfied.

Do not lower acknowledgment levels just to reduce latency without evaluating the risk of data loss. Choose `acks`, replication factor, and `min.insync.replicas` according to durability requirements, then measure performance under that exact operational configuration.

### 5.4. Consumer Fetch and Parallel Processing

Consumers fetch data by request. Important settings include:

| Configuration | Impact |
|---|---|
| `fetch.min.bytes` | Minimum amount of data the broker tries to accumulate before returning a fetch response; increasing it can reduce request count but makes consumers wait longer under low traffic |
| `fetch.max.wait.ms` | Maximum time the broker waits to satisfy the minimum fetch condition; must be balanced against target latency |
| `max.partition.fetch.bytes` | Limit on fetched data per partition in a single request |
| `fetch.max.bytes` | Limit on total fetched data in a single request, subject to Kafka's rules for handling large batches |
| `max.poll.records` | Maximum number of records returned in one `poll` call; affects the amount of work the application must process between polls |

Increasing `fetch.min.bytes` can improve efficiency under high, steady traffic, but for low-volume topics, the consumer may have to wait up to `fetch.max.wait.ms`. Therefore, a configuration suited for high-volume telemetry streams may not suit notification flows requiring fast responses.

In Spring Kafka, listener container `concurrency` creates consumers running in parallel. A consumer group cannot have multiple consumers assigned to the same partition at the same time. If a topic has 8 partitions and a listener has concurrency 12, at most 8 consumers in the group can receive partitions from that topic; the extra consumers add no consumption capacity for that topic.

Concurrency only helps when there are enough partitions and downstream processing can handle the increased load. If consumers share an already saturated database, increasing concurrency can exhaust the connection pool, increase lock contention, and worsen latency.

### 5.5. Business Processing and Offset Commits

After fetching, the consumer still must deserialize, validate data, call services, or write to a database. This is often the dominant component of end-to-end latency in business systems.

A listener that processes records sequentially one by one can achieve low throughput if each record has to wait for a slow I/O call. You can improve this by batching suitable operations, using bounded asynchronous I/O, or optimizing target queries. Keep concurrency limits and backpressure mechanisms in place so you do not overload downstream systems.

`max.poll.records` should be chosen based on actual processing time. If a single poll returns too many records and the application takes too long before the next poll, the consumer may exceed `max.poll.interval.ms` and be considered no longer active in the group. If the value is too low, the application may perform many poll cycles and increase overhead. Measure the processing time of a poll and tune it alongside the related timeouts.

Committing offsets also carries overhead and ties into delivery semantics. Committing too frequently can increase requests and affect throughput; committing too infrequently can increase the amount of work reprocessed after a failure. Choose the ack mode and commit timing based on at-least-once requirements, idempotent processing, and duplicate tolerance. Do not commit offsets before required business operations have completed if doing so could cause records to be skipped after a failure.

## 6. Measure Properly Before Optimizing

Before changing configurations, establish a baseline under repeatable load conditions. A good baseline should record:

- Producer rate in records/s and bytes/s.
- Consumer completion rate in records/s and bytes/s.
- End-to-end latency at p50, p95, and p99.
- Consumer lag per partition and the trend of lag increasing or decreasing.
- CPU, heap, garbage collection, network, and disk on both applications and brokers.
- Error rate, retries, timeouts, rebalances, and reprocessed record count.
- Topic configuration: partition count, replication factor, `min.insync.replicas`, retention, and leader distribution.

### 6.1. Measuring End-to-End Latency

A common approach is to write the event creation timestamp into the payload or header, and then have the consumer record the completion timestamp. Record latency is calculated as:

\[
\text{end-to-end latency} = t_{\text{completed}} - t_{\text{created}}
\]

Both timestamps require clocks with adequate synchronization across machines. If clocks are skewed, the subtraction can produce negative or inaccurate results. For internal measurements within the same process, a monotonic clock is appropriate for measuring intervals; for timestamps spanning multiple machines, time synchronization and understanding measurement error are required.

Kafka record timestamps such as `CreateTime` or `LogAppendTime` have their own semantics and do not automatically represent business completion time. Choose the timestamp source that matches the SLO being tracked.

### 6.2. Monitoring the Producer

Useful producer metric groups include:

- Record and byte send rate.
- Average number of records per request/batch.
- Request latency and send wait time.
- Available buffer space, buffer wait time, and buffer exhaustion count.
- Send error rate, retries, timeouts, and rejected records.

If `records-per-request` is low while the request rate is high, batching may not be effective. If buffer wait increases, the producer is generating data faster than buffers can drain or there is a connection/request issue. If retries and timeouts increase alongside broker request latency, investigate the brokers or network before increasing the buffer.

### 6.3. Monitoring the Broker

Monitor bytes in/out, request rate, request queue wait time, request processing time, network processor and request handler idle ratios, CPU, disk I/O, network, and replication health. Specific JMX metric names and representations may vary by Kafka version and monitoring system.

Signals to watch for include:

- Request queue growing while request handlers or network processors have decreasing idle time.
- Bytes in/out approaching machine or infrastructure network limits.
- Increasing disk latency or heavy pressure on the page cache.
- Under-replicated partitions appearing or persisting.
- Skewed leader distribution causing one broker to carry noticeably higher load than others.

### 6.4. Monitoring the Consumer

Monitor records consumed/s, fetch rate, fetch latency, lag per partition, listener processing time, commit time, and rebalance count. Consumer lag is the difference between the current log position and the position the consumer group has committed/read, depending on the metric and how the tool represents it.

Lag is an indicator of backlog, not a direct measure of end-to-end latency. A consumer can have zero lag at the moment of inspection while each record still takes a long time to process. Conversely, lag can spike temporarily during a burst while the consumer quickly catches up. Look at both the lag value, the rate of change of lag, and actual record processing time.

## 7. Controlled Optimization Process

Optimizing throughput and latency should proceed step by step so you know which change produces which result. A practical workflow:

1. **Define goals.** State target throughput, maximum p95/p99 latency, acceptable error rate, and durability requirements. Specify whether measurement ends at producer acknowledgment, consumer completion, or the target system.
2. **Generate representative load.** Use payloads with sizes and key distributions close to production; keep the intended replication, `acks`, TLS, compression, and producer/consumer counts.
3. **Measure the baseline.** Run long enough to observe steady state, separate warm-up time, and record metrics at all stages.
4. **Find the bottleneck.** Identify the stage with growing queues, saturated resources, or abnormal latency. Inspect per-partition metrics to detect hot partitions.
5. **Change one small group of settings.** For example, tune producer batching first, then adjust consumer fetch or concurrency. Avoid changing many settings at once because it is hard to determine cause and effect.
6. **Re-run the same scenario.** Compare throughput, p95/p99, lag, errors, and resources against the baseline. A change is only beneficial if it improves the goal without violating SLOs or durability requirements.
7. **Test under appropriate simulated failures.** Evaluate behavior when a consumer stops, a broker becomes unavailable, or traffic spikes in a test environment.
8. **Roll out with observability.** Apply changes in a controlled manner, watch metrics, and prepare to revert to the previous configuration if production results differ from testing.

Avoid benchmarks that only measure how fast the producer can send without verifying that data has been processed by the consumer. The test must share the same completion boundary as real-world requirements.

## 8. Reference Configuration in Spring Boot

The following example illustrates a starting configuration for experimenting with producer batching and consumer fetch. The numbers are sample values only; tune them based on record size, traffic, Kafka version, partition count, and system SLOs.

```yaml
spring:
  kafka:
    producer:
      acks: all
      batch-size: 65536
      buffer-memory: 67108864
      compression-type: lz4
      properties:
        linger.ms: 5
    consumer:
      enable-auto-commit: false
      fetch-min-size: 65536
      fetch-max-wait: 50
      max-poll-records: 500
    listener:
      concurrency: 6
```

Meaning of the choices in the example:

- `acks: all` requires acknowledgment based on the current ISR; configure replication and `min.insync.replicas` to match durability requirements.
- `batch-size` is the batch size in bytes. `linger.ms` gives the producer extra time to accumulate data; 5 ms is not optimal for every flow.
- `buffer-memory` is the producer buffer capacity. Monitor buffer wait to see whether buffer space is genuinely insufficient.
- `compression-type: lz4` is an illustrative choice. Benchmark codecs on real data and verify version compatibility.
- `fetch-min-size` and `fetch-max-wait` control data accumulation during fetch. Increasing them can improve transfer efficiency but also increases wait time.
- `max-poll-records` limits the number of records returned in one poll; ensure processing time does not cause the consumer to exceed `max.poll.interval.ms`.
- `concurrency: 6` creates up to six consumers in the listener container. Ensure enough partitions are assigned and sufficient capacity exists in downstream databases/services.

If you need to observe a single listener separately, you can declare concurrency directly on `@KafkaListener`:

```java
@KafkaListener(
    topics = "orders",
    groupId = "order-processor",
    concurrency = "6"
)
public void consume(OrderEvent event) {
    orderService.process(event);
}
```

This example assumes `orderService.process` completes the necessary work before the listener acknowledges processing according to the configured ack mode. If the method performs slow I/O, measure processing time and check connection pools, database queries, locks, and service limits. Increasing concurrency without checking those components may only shift the bottleneck to the target system.

When using a batch listener, the application can process a group of records in a single call to reduce overhead or leverage database batch APIs. Design per-record or per-batch error handling clearly; an error in the middle of a batch can affect retry behavior and offset commits.

## 9. Capacity Planning and Headroom

Capacity planning must be based on normal load, bursts, expected growth, and behavior when a component loses availability. Do not use the highest throughput ever measured as the safe operating capacity.

Suppose the system receives an average of 4,000 records/s, but during peak hours this rises to 9,000 records/s. The consumer group must sustain a processing rate higher than the input rate during normal periods if it needs to drain backlogs after a burst. Measure capacity with replication, TLS, compression, and business processing all enabled as in production.

When the consumer falls behind, backlog catch-up time depends on the **rate by which consumption exceeds production**, not merely on the absolute consumption rate:

\[
\text{catch-up time} \approx \frac{\text{backlog}}{\text{consume rate} - \text{produce rate}}
\]

This formula only applies when both rates are relatively steady and the consume rate exceeds the produce rate. For example, with a backlog of 1,500,000 records, a consumer processing 12,000 records/s, and a producer still sending 4,000 records/s, the net backlog drain capacity is 8,000 records/s, so it takes about 187.5 seconds to catch up if conditions remain unchanged.

When planning capacity, evaluate:

- Average load, short-term peaks, and burst duration.
- Average record size and maximum size distribution.
- Key proportions and the likelihood of hot partitions.
- Required throughput when a broker or consumer instance is down.
- Network and disk capacity reserved for replication, retention, and client traffic.
- Allowed time to drain a backlog after an incident.
- Headroom for growth, rolling restarts, rebalances, and maintenance tasks.

Headroom should be determined through testing and load modeling of the system. If a design runs close to measured limits, a burst or the loss of a broker can cause latency to spike sharply and lag to persist.

## 10. Diagnosing Common Symptoms

| Symptom | Possible Cause | Investigation Direction |
|---|---|---|
| Low producer throughput, rising buffer wait | Slow broker ingestion, network congestion, insufficient buffer for bursts, or too many producer requests | Check request latency, buffer metrics, broker/network; review batch size and linger |
| Higher throughput but sharp rise in p99 | Queues starting to build, a hot partition, or broker/target service nearing saturation | Analyze latency by stage, lag, and per-partition metrics; inspect resources when p99 rises |
| Consumer lag growing continuously | Consumer throughput is lower than producer throughput | Compare records in/out, partition count, concurrency, listener time, and downstream system capacity |
| One consumer busy, others idle | Key skew or uneven partition distribution | Measure records/s per partition and inspect keys; re-evaluate partitioning strategy |
| High broker CPU while disk is idle | TLS, compression, request processing, or many small requests | Check per-process CPU, request rate, batch efficiency, and compression settings |
| Network saturated | Large records, heavy replication traffic, or large bytes/request | Check bytes in/out, payload size, compression, and replica distribution |
| Persistent under-replicated partitions | Followers falling behind leader, broker/network/disk issues | Check replica fetch, broker health, disk, and network; assess impact on `acks=all` |
| Frequent consumer rebalances | Consumer missing heartbeats, poll processing taking too long, instance restarts, or improper timeout settings | Check rebalance logs, poll processing time, `max.poll.interval.ms`, session, and heartbeat |
| Low lag but high end-to-end latency | Slow business processing or lag metric not reflecting actual wait time | Measure timestamps from event creation to completion; separate DB/API time and commit time |

When investigating, correlate metrics along the same timeline. A full-day average CPU chart will not explain a one-minute p99 spike; you need data at fine enough resolution around the incident time.

## 11. Mistakes to Avoid

- **Measuring only records/s:** ignores record size, bytes/s, latency, and error rate.
- **Looking only at average latency:** obscures slow requests at p95 or p99.
- **Treating consumer lag as end-to-end latency:** lag describes offset backlog, not the full processing time of each event.
- **Blindly increasing partitions:** can add overhead without resolving CPU, network, or target system limits.
- **Increasing concurrency without limits:** can overload databases, connection pools, and downstream services.
- **Increasing buffers to fix chronic congestion:** a larger buffer only delays when the producer blocks if brokers consistently process slower than the send rate.
- **Lowering `acks` solely to cut latency:** can degrade durability without addressing the root cause.
- **Benchmarking unlike production:** load tests without replication, TLS, compression, key skew, or business processing yield misleadingly optimistic results.
- **Changing multiple settings at once:** makes it impossible to tell which change caused an improvement or regression.
- **Ignoring send errors and retries:** application-side throughput measurements may not reflect successfully processed records.

## 12. Operational Checklist

When evaluating a change related to throughput or latency, confirm the following points:

- [ ] Clearly defined throughput at the producer, broker, consumer, or business level.
- [ ] Clearly defined start and end points for latency; includes p50, p95, and p99.
- [ ] Measured records/s and bytes/s with production-like record sizes.
- [ ] Checked lag and lag rate of change per partition.
- [ ] Monitored CPU, memory/GC, network, disk, and replication.
- [ ] Checked key, partition, and leader distribution to detect skewed load.
- [ ] Checked listener processing time, commit time, and downstream services.
- [ ] Tested with real durability settings, including `acks`, replication factor, and `min.insync.replicas`.
- [ ] Changed one configuration group at a time and re-ran the same scenario for comparison.
- [ ] Confirmed throughput meets targets while p95/p99, errors, and durability requirements remain within limits.
- [ ] Calculated backlog catch-up time and defined headroom for bursts or failures.

Throughput tells you how much data the system can process; latency tells you how long data must wait. In Spring Kafka, both are influenced simultaneously by batching, partitioning, brokers, replication, fetching, concurrency, and business processing. Measuring stage by stage, observing latency percentiles, and testing with representative loads help pinpoint the right bottleneck, allowing configuration adjustments while preserving data durability and stable operations.
