# Capacity Planning for Peak Traffic

Capacity planning for Spring Kafka is the process of determining how much capacity producers, brokers, consumers, networks, disks, and downstream services need to handle expected traffic while meeting latency, data durability, and recovery targets. When planning for peak traffic, use operationally meaningful peak load rather than average traffic alone. A system that comfortably handles 5,000 records/s most of the time can still destabilize when a campaign generates 30,000 records/s for 15 minutes.

Peak traffic also takes many shapes. A load increase can last a few seconds, minutes, or hours; it can rise steadily with seasonality, spike abruptly from an event, or concentrate on a few partitions due to skewed key distribution. Each shape places different stress on batching, buffers, consumer lag, broker disks, and replication. Therefore, capacity planning must model rate, duration, record size, key distribution, and failure scenarios together.

## 1. Define Goals and Load Scope

Before calculating partition or broker counts, define what the system must serve. Goals should be expressed with concrete numbers and measurement scopes:

- **Peak throughput:** records/s and bytes/s to process across intervals such as 1 second, 1 minute, and 5 minutes.
- **Duration:** how long the system must sustain peak load, such as 30 seconds, 15 minutes, or 4 hours.
- **Latency objective:** maximum p95/p99 end-to-end latency during peak periods.
- **Error objective:** acceptable rate of send failures, timeouts, or processing errors.
- **Durability:** requirements for replication, `acks`, `min.insync.replicas`, and broker fault tolerance.
- **Recovery objective:** maximum time for consumers to drain backlogs after a peak or incident.
- **Growth horizon:** expected traffic growth over the design period, such as 6 or 12 months.

Agree on the throughput boundary. Producer send success, broker persistence, consumer fetch, and business completion are different milestones. If the requirement is that every order be written to the target system within two seconds, capacity must cover the entire flow up to business completion. Measuring only how fast the producer sends into Kafka will not prove that requirement.

An initial workload table might include:

| Attribute | Example | Design Impact |
|---|---|---|
| Normal rate | 8,000 records/s | Sets baseline load and off-peak backlog drain speed |
| Short-term peak | 30,000 records/s for 15 minutes | Determines processing capacity under heavy bursts |
| Sustained peak | 18,000 records/s for 3 hours | Strongly drives consumer capacity and sustained resources |
| Record size | Average 1.5 KB, p99 8 KB | Affects bytes/s, batching, network, and storage |
| Key distribution | 20% of records belong to one hot key | Can create a hot partition despite high total partition count |
| Retention | 3 days | Determines log storage capacity to retain |
| Replication factor | 3 | Multiplies storage footprint and replication traffic |
| SLO | p99 end-to-end under 1 second | Bounds queuing time and safe resource utilization |

Numbers in the table are examples only. Production data or representative benchmarks must replace them before finalizing configurations.

## 2. Measure Peak Traffic by Its True Shape

### 2.1. Collect Data Across Multiple Time Windows

A 5-minute average can hide a 2-second burst. Conversely, taking a single extreme sample can cause over-provisioning if that sample was a measurement glitch or an anomaly the system does not need to process instantaneously. Store time series at multiple resolutions and choose windows aligned with SLOs:

- 1-second or few-second windows to see micro-bursts and producer buffer absorption.
- 1-minute windows to see short peaks and consumer lag shifts.
- 5- or 15-minute windows to see sustained peak loads.
- Hourly/daily windows to identify seasonality, campaign schedules, and growth trends.

Do not use only daily averages to size throughput. Nor should you use a single max sample to represent every target. Record peaks per window, window percentiles, and how long load exceeds key thresholds.

### 2.2. Classify Peak Shapes

**Sustained peak** is high load lasting long enough that brokers, consumers, and downstream systems must process continuously. This usually drives CPU, network, disk throughput, and required consumer counts.

**Short burst** is a sharp load spike over a brief period. Producer buffers, batching, queues, and backlog-draining capacity can absorb part of a burst, provided the system has enough memory and recovery time. Buffers only defer processing; they do not replace sustained capacity.

**Ramp-up peak** is gradually rising load, such as traffic climbing during a flash-sale opening. The system must be able to scale before hitting the crest. If autoscaling reacts only after lag has climbed high, consumers may fail to scale out in time before SLOs breach.

**Replay or reprocessing peak** occurs when applications re-read data after an incident, run backfills, or replay events. Read and write traffic can overlap normal user traffic. Capacity planning must include this scenario if replay is a supported operational activity.

**Retry amplification** occurs when a downstream service slows down or fails, causing consumers to retry, producers to resend, or multiple components to emit extra requests simultaneously. Generated load can exceed the original business traffic. Model retry policies, backoffs, retry limits, and dead-letter topics.

**Skewed peak** occurs when total traffic rises while a few keys or partitions receive most of the data. Cluster-wide throughput may still have headroom while the single consumer handling a hot partition is saturated.

### 2.3. Use Production Data and Benchmarks

When gathering data, measure records/s and bytes/s across producer, broker, consumer, and business stages; average and p95/p99 record sizes; record counts per partition; consumer lag; listener processing time; retry rates; and CPU, memory, network, and disk resources.

If production has not yet experienced the projected peak, generate load via benchmarks. Payloads, key distribution, compression, TLS, replication, producer counts, and processing logic must mirror production. A test sending tiny records to a single broker routinely underestimates the capacity needed for a replicated system whose consumers write to a database.

## 3. Calculate Design Load Rate

### 3.1. From Observed Peak to Design Peak

Let `R_peak` be the representative peak rate observed in the chosen time window. If traffic is forecast to grow by `g` over the design horizon, the design load rate is:

\[
R_{design} = R_{peak} \times (1 + g)
\]

For example, with an observed peak of 30,000 records/s and 20% projected growth over 12 months:

\[
R_{design} = 30,000 \times 1.2 = 36,000\ records/s
\]

This is the forecast load to serve. Next, add headroom or choose a safe resource utilization cap. Avoid both multiplying design load by a headroom factor and dividing by a utilization target without realizing both represent the same reserve; doing so can accidentally double-count reserves.

Two common formulations:

- **Headroom factor:** `C_required = R_design × H`, where `H` might be 1.2 or 1.3 depending on chosen reserve.
- **Target utilization:** `C_required = R_design / U_target`, where `U_target` is the target utilization, e.g., 0.7.

Both keep spare capacity in resources. Pick the one fitting your operational model and apply it consistently across calculations. Reserve levels should rest on load volatility, scaling speed, N-1 requirements, and benchmark results; no single ratio fits every cluster.

### 3.2. Convert records/s to bytes/s

Logical byte throughput can be estimated as:

\[
B_{logical} = R_{design} \times S_{avg}
\]

Where `S_avg` is average record size in bytes. Also use p95/p99 sizes and maximum valid record sizes to verify batch, request, and fetch limits. When payload sizes vary widely, using averages alone underestimates risks on large batches.

Example with 30,000 records/s and 1,500-byte average size:

\[
30,000 \times 1,500 = 45,000,000\ bytes/s \approx 45\ MB/s
\]

This is logical data rate before compression and protocol overhead. Producer compression can reduce transmitted and stored log bytes, though compression ratio depends on data and batching. Benchmark with real payloads to measure compression ratio rather than assuming every topic shrinks by a fixed percentage.

### 3.3. Account for Derived Load

Initial business traffic is not always the entire load Kafka must handle. Add or model separately:

- Retries and resends after timeouts.
- Events fanned out to multiple topics or multiple consumer groups.
- Dead-letter topics and recovery flows.
- Backfills, replays, reprocessing, and migrations.
- Repeated consumer fetches when processing fails or offsets reset.
- Inter-broker replication.

Do not lump every component into a single number if they measure different flows. For instance, replication increases broker network and disk traffic, yet does not mean the producer receives additional logical records. Keep separate load tables for producers, brokers, consumers, and downstream services to avoid double-counting.

## 4. Size Consumer Capacity and Partition Count

The consumer group is where many applications hit limits during peak traffic. A group can process in parallel only up to the number of partitions assigned to it. Scaling pods or `concurrency` beyond partition count adds no useful consumers for that topic.

### 4.1. Measure Single-Consumer Processing Capacity

Benchmark one consumer instance under production-like conditions, including deserialization, validation, service calls, database writes, and offset commits. Record the records/s rate one instance sustains while meeting p95/p99 latency and avoiding downstream saturation.

Let `r_consumer` be the sustainable capacity of one consumer under those conditions. Required active consumers can be estimated as:

\[
N_{consumer} = \left\lceil \frac{R_{required}}{r_{consumer}} \right\rceil
\]

`R_required` must include the chosen headroom. If the system must survive losing one consumer instance, ensure remaining consumers still cover capacity:

\[
(N_{consumer} - 1) \times r_{consumer} \ge R_{required}
\]

For example, if required load is 39,000 records/s and each consumer sustains 4,000 records/s, at least 10 active consumers are needed. To survive losing one consumer, provision at least 11 active consumer instances before failure.

This is an initial calculation. Actual throughput does not always scale linearly with consumers because brokers, partitions, database connection pools, or downstream services can form shared bottlenecks. Benchmark at target scale and test losing one instance.

### 4.2. Choose Partition Count

Partition count must be large enough to support desired parallel active consumers. An initial estimate is:

\[
P \ge N_{consumer,peak}
\]

Where `P` is the topic's partition count and `N_consumer,peak` is the number of consumers desired to run concurrently in the group. You can add extra margin for growth or topology changes, yet avoid raising partitions arbitrarily.

Final partition count also depends on:

- **Ordering:** Kafka preserves order within a partition. Records with the same key normally route to the same partition under the default partitioner.
- **Key skew:** a hot key can overload the partition holding it even while other consumers sit idle.
- **Broker capacity:** many partitions increase metadata, segment files, leader/replica overhead, and management work.
- **Consumer assignment:** partitions assigned per consumer and load balance must be verified via benchmarks.
- **Changing partition counts:** adding partitions can alter key-to-partition mapping for new records, affecting ordering or per-key processing assumptions.

If an application needs global ordering across an entire topic, you cannot simply add partitions to parallelize consumers while keeping the same ordering semantics. Clarify ordering requirements before deciding partition count.

### 4.3. Calculate Backlog Drain Capacity

During a peak, if production rate exceeds consumer completion rate, a backlog builds. Under relatively steady rates:

\[
Backlog = (R_{in} - R_{out}) \times T
\]

`R_in` is incoming record rate, `R_out` is completion rate, and `T` is duration of the mismatch in seconds. The formula applies only when `R_in > R_out` over the interval.

After the peak, backlog drain time is estimated as:

\[
T_{drain} = \frac{Backlog}{R_{recovery} - R_{normal}}
\]

`R_recovery` is the sustainable consumer rate post-peak and `R_normal` is normal input rate. If `R_recovery` does not exceed `R_normal`, the backlog cannot shrink in that state.

For example, a 15-minute peak at 30,000 records/s while consumers process 24,000 records/s:

\[
Backlog = (30,000 - 24,000) \times 900 = 5,400,000\ records
\]

After the peak, the producer returns to 8,000 records/s and consumers can process 32,000 records/s. Net backlog drain capacity is 24,000 records/s, so catch-up time is roughly 225 seconds, or 3 minutes 45 seconds. If downstream only allows consumers to run at 10,000 records/s during recovery, the backlog will drain very slowly or not at all; size capacity across the entire processing chain.

Offset-based consumer lag is a useful backlog indicator, yet does not automatically express wait time for individual events. Monitor record lag count, lag growth/drain rate, and oldest record age if your system tracks it.

## 5. Calculate Storage Capacity for Peaks and Retention

Kafka stores logs per partition and maintains replicas according to replication factor. Required storage depends on data rate across the full retention window, post-compression record size, replication factor, overhead, and target disk utilization.

Total cluster storage estimate:

\[
S_{cluster} = R_{avg} \times S_{avg} \times T_{retention} \times C \times RF \times (1 + O)
\]

Where:

- `R_avg` is average record rate across the retention window, not a short-term peak.
- `S_avg` is average uncompressed record size.
- `T_retention` is retention duration in seconds.
- `C` is post-compression to pre-compression size ratio; e.g., 0.5 means roughly half.
- `RF` is replication factor.
- `O` is reserve factor for indexes, segments, metadata, and real-world variance.

If the cluster is allowed to use at most `U_target` of disk space, required provisioned physical storage is:

\[
S_{provisioned} = \frac{S_{cluster}}{U_{target}}
\]

For example, a topic averaging 8,000 records/s, 1,500-byte average records, 0.5 measured compression ratio, 3-day retention, replication factor 3, and 20% overhead reserve:

\[
8,000 \times 1,500 = 12,000,000\ bytes/s = 12\ MB/s
\]

Logical data per day is roughly 1,036.8 GB before compression. After compression, roughly 518.4 GB/day. Over 3 days, that is roughly 1.555 TB for one replica; multiplying by replication factor 3 and 20% overhead yields roughly 5.60 TB total cluster usage. With a 70% target disk utilization cap, total provisioned physical storage is roughly 8.0 TB.

This example uses the average rate across the retention window. Do not multiply a 30,000 records/s peak across all 3 days if the peak lasts only 15 minutes; doing so exaggerates storage needs. Conversely, if peaks last many hours daily, include those hours in the weighted average rate. For compacted topics, tombstones, byte-based retention, or variable-sized data, inspect actual broker disk usage rather than relying solely on simple formulas.

When allocating storage, check per broker and per volume. Cluster-wide total storage may suffice while one broker fills its disk due to uneven leader/replica placement. Leave spare space for segment rolls, recovery, reassignment, and maintenance.

## 6. Size Network and Broker Capacity

Brokers handle producer requests, log writes, consumer fetches, and replica synchronization. Capacity planning must evaluate network ingress, network egress, disk throughput, IOPS, CPU, memory/page cache, and replication traffic separately.

### 6.1. Network Ingress and Egress

Producer network ingress depends on bytes/s after serialization and compression. Consumer egress depends on how many consumer groups read the topic, fetch rates, and whether consumers read all data or a subset. A topic read completely by five independent consumer groups can generate far more egress than a single group.

Replication factors above 1 generate inter-broker traffic as followers pull data from leaders. With replication factor 3, each logical record has one leader replica and two follower replicas. Extra replicas give a rough estimate of replication traffic, yet actual network usage depends on broker distribution, batch fetching, compression, leader placement, and network topology.

Do not simply sum cluster-wide bytes/s and divide evenly across brokers. Partition leaders may be unevenly distributed; one broker may take heavy producer writes while serving heavy consumer fetches simultaneously. Estimate per broker and verify with per-node bytes in/out metrics.

### 6.2. Disk and Page Cache

Kafka writes logs sequentially and leverages the OS page cache. Disk write throughput is not the only factor; examine disk latency, flush behavior, read activity, page cache hits, and memory pressure. Consumer fetches typically read data already in page cache, yet heavy replay workloads or working sets exceeding RAM can drive up disk reads.

When checking broker disks, separate:

- Storage capacity needed for retention.
- Write throughput during peaks.
- Read throughput when consumer groups fetch data.
- IOPS and latency during segment rolls, recovery, or reassignments.
- Spare capacity when a broker or volume goes offline.

Disks with plenty of free space can still miss peak SLAs if write/read throughput or latency falls short.

### 6.3. CPU and Memory

Broker CPU handles request processing, TLS, compression/decompression, checksums, replication, and background tasks. Producer/consumer CPU is further impacted by serialization, deserialization, business processing, and garbage collection. A compression setting lowers network usage yet can raise CPU; measure both sides.

Memory must suffice for application heaps, producer buffers, fetch buffers, metadata, and OS page cache. Do not allocate all RAM to JVM heap when brokers rely on page cache. As consumer concurrency grows, buffers, requests, and connections can also grow.

### 6.4. Replication and Durability

`replication.factor`, `min.insync.replicas`, and producer `acks` affect both durability and write capacity. With `acks=all`, the leader waits for ISR replicas to satisfy acknowledgment rules. When followers lag or the ISR shrinks, producer latency can rise; if ISR replicas drop below `min.insync.replicas`, writes may be rejected.

Capacity must cover replication during peaks and leave headroom when a broker goes down. Never plan using throughput measured with replication disabled if production requires RF=3. Lowering `acks` or `min.insync.replicas` for higher throughput must be weighed against data loss risk.

## 7. Design Headroom and Fault Tolerance

Peak traffic often coincides with times the business least tolerates disruption. Therefore, clusters need spare capacity when a broker, consumer instance, availability zone, or downstream service fails.

### 7.1. N-1 Capacity

N-1 planning checks whether the system still meets target load when losing one component. For consumers, sum capacity across remaining instances after one stops. For brokers, inspect leader reassignment, replica availability, network, and disk on remaining brokers.

For example, if 12 consumer instances each sustain 4,000 records/s, nominal total capacity is 48,000 records/s. Losing one instance leaves 44,000 records/s. If required capacity with headroom is 39,000 records/s, the consumer group still covers load in this model, provided partition assignments and downstream tolerate the shifted load.

N-1 is not just addition. When a broker fails, partition leaders move to other brokers; remaining brokers may serve additional network egress, writes, and replica fetches. Test broker restarts or node losses to confirm post-failover load distribution.

### 7.2. Headroom by Resource Type

Do not use a single CPU threshold to represent total capacity. A broker may have spare CPU while network is saturated; a consumer may have spare CPU while the database connection pool is exhausted. Define separate headroom for:

- CPU and request processing time.
- Network ingress, egress, and inter-broker traffic.
- Disk capacity, disk throughput, and disk latency.
- JVM heap, garbage collection, and page cache.
- Consumer concurrency, partition assignment, and database connections.
- Quotas, connection counts, request limits, and cloud service limits.

Alert and scaling thresholds must rest on baselines, benchmarks, and SLOs. A resource running at 80% may be stable under steady load yet lack room for bursts or failover. A resource at 50% can still cause high latency if one specific partition or thread is saturated.

### 7.3. Autoscaling and Reaction Time

Lag-based consumer autoscaling can help on gradual peaks, yet must account for detection time, pod startup, consumer creation, group join, and rebalancing. If a peak lasts only a few seconds, autoscaling reacts too late; pre-provisioned capacity or adequate buffering is required.

Consumer scaling is also bounded by partition count. Once consumers equal assigned partitions, adding pods adds no processing power for that topic. If partitions must be expanded, evaluate ordering, key mapping, and operational impact first.

Broker autoscaling is usually more complex because adding brokers does not automatically rebalance partitions and replicas. You need a reassignment workflow, disk/network checks, and replication monitoring during data movement.

## 8. Connecting Capacity Planning to Spring Kafka Settings

Spring Kafka exposes producer, consumer, and listener container settings to tune batching, fetching, concurrency, and poll behavior. Values must be chosen from benchmarks; they do not substitute for adequate partitions, brokers, and downstream capacity.

Illustrative Spring Boot configuration example:

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
      max-poll-records: 500
      fetch-min-size: 65536
      fetch-max-wait: 50ms
    listener:
      concurrency: 12
```

These settings mean:

- `batch-size` caps producer batch size in bytes. Larger batches can lower request counts, yet require enough data to fill.
- `linger.ms` gives the producer extra time to accumulate records. Larger values can improve batch efficiency and add wait time.
- `buffer-memory` sets producer memory reserved for pending records. Buffers absorb short bursts; if sustained load outpaces broker capacity, buffers still fill.
- `compression-type` selects the batch compression codec. Measure compression ratio and CPU with real payloads.
- `acks: all` requires acknowledgment across the ISR. Set matching replication factor and `min.insync.replicas`.
- `max-poll-records` caps records returned per `poll`; balance processing batch size against the interval between polls.
- `fetch-min-size` and `fetch-max-wait` control how much data the broker tries to accumulate and how long fetches wait. Higher values can improve transfer efficiency yet raise low-load latency.
- `listener.concurrency` sets parallel consumers in the listener container. Useful consumers remain bounded by assigned partitions and downstream capacity.

Listener example:

```java
@KafkaListener(
    topics = "orders",
    groupId = "order-processor",
    concurrency = "12"
)
public void consume(OrderEvent event) {
    orderService.process(event);
}
```

If the topic has 8 partitions, concurrency 12 will not give 12 consumers data from that topic simultaneously; at most 8 consumers in the group receive partitions at a time. To run 12 consumers in parallel, the topic needs enough partitions and key distribution must allow load to spread evenly.

During peaks, do not raise `max-poll-records`, concurrency, or buffers based on a single metric. Inspect poll processing time, `max.poll.interval.ms`, heartbeats, rebalances, database connection counts, and external service limits. A consumer can fetch fast yet process too slowly, triggering group rebalances and lowering real throughput.

## 9. Scaling Capacity Layer by Layer

### 9.1. Producer

If the producer is the bottleneck, check serialization, batch efficiency, compression, buffer waits, sending threads, and network connections. You can raise batching or optimize payloads when CPU and latency allow. When producers write to multiple partitions, balanced key distribution utilizes broker resources more evenly.

Do not scale producers indefinitely to compensate for slow consumers. That makes backlogs grow faster, fills buffers, and adds broker pressure.

### 9.2. Broker

When brokers are the limit, identify which resource is saturated before adding nodes. You may need more network capacity, disk throughput, CPU, leader/replica rebalancing, or cluster expansion. Adding brokers without reassigning partitions may not immediately relieve load on existing brokers.

Also weigh replica movement impact: reassignments generate extra network and disk I/O, which can raise latency during peaks. Schedule partition moves outside peak windows when possible and throttle movement rates to cluster capacity.

### 9.3. Consumer

When consumers are the bottleneck, find whether the limit is CPU processing, I/O, partition count, or downstream. Optimize database queries, use suitable batch APIs, cap concurrency and connection pools, or scale the consumer group if partitions allow.

If adding consumers saturates the database, system-wide throughput can fall. Consumer group capacity must be sized alongside databases, HTTP services, caches, and systems called inside listeners.

### 9.4. Downstream Systems

Consumers can process faster than target databases or services can accept writes. Examine batch writes, indexes, transaction sizes, connection pools, target partitioning, and rate limits. Ensure changes preserve processing semantics, idempotency, and retryability.

One way to protect downstream is capping concurrency or applying backpressure. This may raise Kafka lag temporarily, yet prevents target systems from collapsing. Capacity plans must define maximum allowed backlog, retention windows, and catch-up time once downstream recovers.

## 10. Capacity Planning Workflow

A practical process can follow these steps:

1. **Define SLOs and scope.** Specify peak throughput, p95/p99 latency, error rate, durability, recovery time, and business completion boundaries.
2. **Collect workloads.** Measure rates across multiple windows, record sizes, key distributions, topic counts, consumer groups, retention, retries, and replays.
3. **Forecast growth.** Apply growth factors for the design period; document seasonality and business event assumptions.
4. **Calculate consumer capacity.** Benchmark records/s per consumer under SLOs, compute consumer count, and verify N-1.
5. **Choose partition count.** Support required parallelism, maintain required ordering, and check for hot partitions.
6. **Calculate broker resources.** Estimate network, disk capacity, disk throughput, CPU, memory, and replication traffic per broker.
7. **Calculate storage.** Use average rate across the retention window, measured compression ratio, replication factor, overhead, and target disk utilization.
8. **Verify downstream.** Confirm databases, APIs, caches, connection pools, and quotas sustain expected consumer rates.
9. **Benchmark representative loads.** Run baseline, sustained peak, short burst, key-skewed peak, and replay scenarios as applicable.
10. **Test failures.** Stop a consumer, restart a broker, or simulate slow downstream to verify headroom and recovery times.
11. **Document assumptions and thresholds.** Record calculation models, settings, metrics, measured limits, and alert thresholds so they can be updated as workloads evolve.
12. **Review periodically.** Update the capacity plan whenever new peaks, record sizes, retention, partition counts, consumer groups, or SLO requirements change.

## 11. Essential Benchmark Scenarios

A capacity planning benchmark should cover these cases:

| Scenario | Purpose | Primary Observations |
|---|---|---|
| Normal load | Confirm baseline | Normal throughput, latency, CPU, and lag |
| Sustained peak | Test long-term capacity | Broker/consumer resources, p99, and lag over time |
| Short burst | Test burst absorption | Buffer waits, queue growth, drain duration |
| Ramp-up | Test scaling responsiveness | Autoscaling time, rebalances, and latency during ramp |
| Key skew | Test hot partitions | Per-partition records/s and consumer imbalance |
| Large records | Test byte/batch limits | Request size, fetches, network, memory, and disk |
| Retry/replay | Test derived extra load | Retry rate, dead-lettering, consumer lag, and downstream capacity |
| Consumer failure | Test N-1 | Remaining capacity, rebalances, and catch-up |
| Broker failure | Test replication/failover | ISR, leader movement, network, and recovery latency |
| Slow downstream | Test backpressure | Queue growth, connection pools, timeouts, and post-recovery drain |

Do not record only peak throughput. For every scenario, record p50/p95/p99 latency, errors, consumer lag, CPU, memory/GC, network, disk, request queues, and time to return to normal.

## 12. Monitoring Capacity in Operations

A capacity plan is a living model that must be updated with production metrics. Dashboards should provide an overview plus drill-downs by topic, partition, consumer group, and broker.

### Producer

- Records sent/s and bytes sent/s.
- Average batch size and records per request.
- Request latency, retries, timeouts, and send errors.
- Available buffer space, buffer waits, and buffer exhaustions.

### Broker

- Bytes in/out per broker.
- Request rate, request queue time, and request processing time.
- CPU, network, disk throughput, disk latency, and free disk space.
- Leader/replica distribution, ISR shrinks/expands, and under-replicated partitions.
- Quota status, connections, and request handler utilization.

### Consumer

- Records consumed/s and bytes consumed/s.
- Lag per group and partition, plus lag growth/drain rate.
- Oldest record age or end-to-end latency if measured by the application.
- Listener processing time, poll duration, commit latency, and rebalance count.
- Retries, dead-letter rate, and active consumer count.

### Downstream

- Database transaction rate, query latency, connection pool usage, and lock waits.
- HTTP request rate, latency, timeouts, and quota limits.
- Target system queues or worker backlogs.

Set alerts based on trends and SLOs. For instance, consumer lag rising steadily for 10 minutes means something very different from a brief lag spike that drains away. Steadily rising disk utilization warns earlier than waiting for a broker disk to fill. Rising p99 latency alongside request queues or database latency pinpoints the bottleneck layer.

Do not alert solely when CPU crosses one threshold. One hot partition can saturate a single consumer while cluster-wide average CPU stays low. Likewise, network or disk can bottleneck before CPU climbs high.

## 13. Common Mistakes

- **Using average traffic to design for peaks:** misses bursts and sustained loads during special events.
- **Taking a single max value without a window:** easily skewed by measurement spikes or unrepresentative events.
- **Applying short-peak rates across the full retention window:** inflates storage estimates when duration and weighted averages are ignored.
- **Counting only records/s:** ignores record size, bytes/s, compression, replication, and consumer group counts.
- **Assuming total cluster capacity suffices:** an overloaded broker or hot partition can still saturate from uneven distribution.
- **Adding consumers without adding partitions:** excess consumers get no partitions and create zero extra throughput.
- **Adding partitions without checking keys:** hot keys can still funnel into a single partition.
- **Ignoring downstream:** faster consumers can overwhelm databases or APIs.
- **Omitting replays and retries:** post-incident catch-up traffic can overlap normal user peaks.
- **Skipping N-1 testing:** normal throughput does not prove the cluster survives losing a node.
- **Scaling brokers without reassigning partitions:** new nodes may not pick up needed load.
- **Picking headroom by gut feel:** too little reserve breaks SLOs; too much inflates cost without evidence.
- **Failing to update the model:** growth, payload changes, and new consumer groups invalidate old assumptions.

## 14. Capacity Planning Checklist

Before locking in a capacity plan for a topic or consumer group, verify:

- [ ] Defined SLOs, throughput boundaries, and end-to-end latency bounds.
- [ ] Collected peak metrics across multiple windows and peak durations.
- [ ] Classified sustained peaks, bursts, ramp-ups, retries, replays, and key skew.
- [ ] Measured average and p95/p99 record sizes and compression ratios.
- [ ] Applied growth factors for the design horizon.
- [ ] Explicitly chose headroom factor or target utilization and avoided double-counting reserves.
- [ ] Benchmarked consumer capacity under real business processing conditions.
- [ ] Chose partition counts matching concurrency, ordering, and key distribution.
- [ ] Calculated backlogs and post-peak drain times.
- [ ] Calculated retention using average rates over the retention window, compression, replication, and overhead.
- [ ] Verified network, disk, CPU, memory, and replication per broker.
- [ ] Confirmed databases, APIs, quotas, and downstream services withstand peak load.
- [ ] Tested N-1 scenarios for both consumers and brokers.
- [ ] Benchmarked sustained peaks, bursts, key skew, replays, and failure scenarios.
- [ ] Set up dashboards, alerts, and a capacity review schedule.

Capacity planning for peak traffic must combine real workloads, growth forecasts, measured processing capacity, and failure headroom. In Spring Kafka, partition and consumer counts determine parallelism; brokers, replication, network, and disk determine ingestion and storage capacity; downstream services determine business completion speed. When you size each layer independently, verify N-1, and benchmark representative peak shapes, the system can handle traffic surges while preserving latency, durability, and recovery targets.
