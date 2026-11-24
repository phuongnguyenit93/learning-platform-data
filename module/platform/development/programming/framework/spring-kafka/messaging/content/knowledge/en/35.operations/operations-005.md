# Calculating and Interpreting Consumer Lag

Consumer lag indicates how far behind a consumer group is relative to the data currently available in Kafka. It is a critical operational signal for detecting consumers falling behind producer rates, a bottlenecked partition, continuous consumer rebalances, or an overloaded downstream dependency.

Do not look only at a single total lag figure. You must understand which offsets are used in the calculation, examine lag per partition, compare incoming and outgoing record rates, and track the age of the oldest unprocessed record. A group with high lag that is draining quickly can be healthier than a group with small lag that is growing steadily.

## 1. What is consumer lag?

Kafka stores records in order within each partition and assigns monotonically increasing offsets. A consumer group reads its assigned partitions and stores committed offsets to record how far it has processed. Consumer lag describes the distance between the consumer's position and the end of readable data in a partition.

Lag is commonly expressed in offsets or estimated records. For instance, if a partition's committed offset is `120` and the end offset is `150`, the offset gap is `30`. The consumer group is 30 offsets behind the end of that partition's log.

Lag should be computed per partition before aggregating by topic or group. A consumer group can keep up smoothly on most partitions while falling behind on one partition due to a hot key, malformed data, or repeated business errors.

## 2. Offset types to distinguish

To read lag accurately, distinguish three positions:

- **Committed offset:** the next offset the consumer group has confirmed it will read. This is the durably stored position for the group.
- **Consumer position:** the next offset the current consumer will receive on its next poll. Position can advance past committed offset because records were polled or processed but not yet committed.
- **Log end offset (LEO):** the next offset the broker will assign to a new record in the partition. This is the end of the log from the leader's perspective; it does not mean every record is already replicated or visible to `read_committed` consumers.

Under the common offset formulas:

\[
\text{Committed lag} = \text{LEO} - \text{Committed offset}
\]

\[
\text{Fetch lag} = \text{Readable end offset} - \text{Consumer position}
\]

Committed lag measures the distance from the committed offset to the end of the log. Fetch lag is closer to the remaining data the consumer still needs to poll from its current position. These two values can differ noticeably when a consumer is actively processing records without having committed offsets yet.

Kafka defines offsets using the convention of the next position to read. Therefore, if committed offset is `120`, record offset `119` is the last record confirmed at that position. Do not add or subtract one under the assumption that offset represents the ordinal number of the last processed record.

## 3. Example of calculating lag per partition

Suppose partition `orders-0` has the following positions:

| Metric | Offset |
| --- | ---: |
| Committed offset | 12,300 |
| Consumer position | 12,380 |
| Log end offset | 12,450 |

Then:

- Committed lag = `12,450 - 12,300 = 150` offsets.
- Fetch lag = `12,450 - 12,380 = 70` offsets, assuming the readable end corresponds to LEO in this case.
- The gap between position and committed offset is `80`, reflecting records the consumer has already moved past without committing yet.

As the consumer keeps processing and committing, committed offset approaches the end offset. If the listener is slow or fails to commit, committed lag can stay high even though the consumer has already polled many records.

| Partition | Committed offset | End offset | Lag |
| --- | ---: | ---: | ---: |
| orders-0 | 12,300 | 12,450 | 150 |
| orders-1 | 8,900 | 8,920 | 20 |
| orders-2 | 5,100 | 5,100 | 0 |
| **Total** |  |  | **170** |

Total lag is the sum of offset gaps across partitions. It helps track overall trends, but can mask a bottlenecked partition. In this example, `orders-0` accounts for most of the lag and should be investigated individually.

## 4. Offset distance does not always equal actual record count

The difference between end offset and committed offset is often called the number of lagging records, though more accurately it is an offset distance. The two can differ:

- A compacted topic can remove old records while preserving subsequent offsets, leaving gaps in the offset sequence.
- Aborted transactions can leave offsets invisible to `read_committed` consumers.
- Control records and Kafka internal mechanisms can make offset distance differ from the number of business records delivered to the listener.
- Some exporters report lag by offset distance, whereas consumer metrics may be based on position and readable records.

Thus, a lag of `1,000` does not necessarily mean the listener will receive exactly 1,000 business records. Treat it as a progress-distance indicator and combine it with record rates, timestamps, and consumer state.

## 5. High watermark and Last Stable Offset

Beyond LEO, Kafka has two important markers when analyzing lag:

- **High watermark (HW):** the trailing boundary of data sufficiently replicated under Kafka's rules to be readable by normal consumers. HW is always less than or equal to LEO.
- **Last Stable Offset (LSO):** the boundary limiting what `read_committed` consumers can read when incomplete transactions exist. LSO can sit below HW if the partition has an open transaction.

For example, LEO is `500`, HW is `490`, while LSO is `470` due to an unfinished transaction starting around that offset. A `read_committed` consumer cannot read past LSO until the associated transaction commits or aborts. If a dashboard computes lag from LEO, it may show a larger gap than the data currently readable.

When using Kafka transactions or EOS, know whether your tool computes lag from LEO, HW, or LSO. Do not conclude a consumer is slow solely from a gap against LEO if an open transaction is holding LSO back.

## 6. Inspecting consumer lag with kafka-consumer-groups

The `kafka-consumer-groups` tool is a fast way to check committed offsets, end offsets, and lag for a group. On Windows, you can run the `.bat` script in the Kafka directory:

```powershell
.\bin\windows\kafka-consumer-groups.bat `
  --bootstrap-server localhost:9092 `
  --describe `
  --group orders-service
```

The output typically includes columns such as:

| Column | Meaning |
| --- | --- |
| `TOPIC` | Topic the group is reading |
| `PARTITION` | Specific partition |
| `CURRENT-OFFSET` | Group's committed offset |
| `LOG-END-OFFSET` | End offset used by the tool for comparison |
| `LAG` | Distance between end offset and committed offset |
| `CONSUMER-ID` | Consumer currently assigned the partition |
| `HOST` | Consumer's host |
| `CLIENT-ID` | Consumer's client ID |

To view group state and members, you can run:

```powershell
.\bin\windows\kafka-consumer-groups.bat `
  --bootstrap-server localhost:9092 `
  --describe `
  --group orders-service `
  --state

.\bin\windows\kafka-consumer-groups.bat `
  --bootstrap-server localhost:9092 `
  --describe `
  --group orders-service `
  --members `
  --verbose
```

Column names and options can vary by Kafka CLI version. If `CURRENT-OFFSET` is missing, the group may not have committed offsets for that partition yet; check group state and `auto.offset.reset` before interpreting lag.

## 7. Monitoring lag with consumer metrics

The Kafka Java consumer exposes useful metrics for analyzing speed and progress. Metric names can vary by client version and JMX/Micrometer exposure, but common metric groups to monitor include:

| Metric | Operational meaning |
| --- | --- |
| `records-lag-max` | Maximum lag across partitions tracked by the consumer per client metric definition |
| `records-consumed-rate` | Rate at which the consumer receives records |
| `bytes-consumed-rate` | Data consumption rate in bytes/second |
| `fetch-rate` | Rate of fetch requests |
| `fetch-latency-avg` | Average latency of fetch requests |
| `commit-rate` | Frequency of offset commits |
| `commit-latency-avg` | Average latency of commits |
| `assigned-partitions` | Number of partitions assigned to the consumer |
| `poll-idle-ratio-avg` | Fraction of time the consumer is idle outside poll processing per client definition |
| `heartbeat-rate` | Rate of heartbeats sent in the consumer group |

`records-lag-max` is a consumer-side metric and does not necessarily equal committed lag derived from group offsets. Label dashboards clearly to distinguish consumer-position lag metrics from committed-offset lag.

In Spring Kafka, Kafka client metrics can be exposed to JMX or Micrometer depending on application configuration. With Spring Boot Actuator and Micrometer, inspect the actual metrics exposed on the metrics endpoint and Prometheus scrape; do not assume every Kafka metric automatically carries the exact same name across versions.

## 8. Distinguishing record lag from time lag

Offset lag shows distance in offsets. Time lag shows how long the oldest unprocessed record has been waiting. Both indicators complement each other:

- **Offset lag:** offset gap between the end and the consumer/committed position.
- **Time lag / record age:** age of the oldest unprocessed record, measured from the appropriate timestamp.

For example, a 10,000-record lag may be harmless if the consumer processes 50,000 records/second and the backlog is draining. Conversely, a 50-record lag can violate an SLA if the oldest record has waited 20 minutes on a stream requiring 30-second processing.

When computing time lag, know whether the timestamp is producer-supplied `CreateTime` or broker-assigned `LogAppendTime`. `CreateTime` can be skewed by producer clocks; event times inside payloads can also be older than when the record was published. Choose a timestamp consistently aligned with your business SLA.

## 9. Reading lag trends instead of a single snapshot

Lag changes according to the difference between incoming data rate and processing rate:

\[
\Delta \text{lag} \approx (\text{incoming rate} - \text{processing rate}) \times \Delta t
\]

This is an approximate model over a time window assuming partition assignments and offsets are not reset. If producers write faster than consumers process, lag rises. If consumers process faster than new records arrive, lag shrinks.

| Trend | Initial interpretation |
| --- | --- |
| Low and steady lag | Consumer is keeping up with current load |
| Steadily growing lag | Processing rate is slower than incoming record rate |
| Sudden lag spike then drop | Traffic burst or temporary consumer interruption followed by catch-up |
| High lag but shrinking steadily | Consumer is draining backlog; track estimated time to catch up |
| Lag high on only one partition | Possible hot key, skewed key distribution, or slow-processing record |
| Lag rising across all partitions | Possible insufficient consumer capacity, slow downstream, or broker/network issue |
| Lag at 0 yet SLA still missed | Metric may not reflect time lag, commits are too early, or timestamps/offsets are misinterpreted |

Do not alert on a single scrape. Use time windows, lag growth rate, and record age to separate brief bursts from sustained incidents.

## 10. Common causes of rising lag

### Slow consumer processing

Listeners call databases, REST services, or run CPU-heavy work. As per-record processing time grows, consumer throughput drops. Measure listener duration, downstream latency, and records processed per second before raising concurrency.

### Consumer group lacks consumers or partitions

A group can only process in parallel up to the number of assigned partitions. Raising concurrency past the partition count adds no useful parallelism. If more capacity is needed, check partition count, consumer count, key distribution, and downstream limits.

### Repeated rebalances

Consumers processing longer than `max.poll.interval.ms`, losing heartbeats, or restarting continuously can trigger group rebalances. During rebalances, processing pauses and lag rises. Monitor rebalance rate, heartbeats, poll intervals, and container logs.

### Failing records retried repeatedly

A poison record or failing dependency can tie up consumers in retries. With blocking retries, a failing record can block subsequent records on the same partition. With retry topics, monitor lag separately on retry topics and the DLT.

### Backpressure or paused partitions

Applications may intentionally pause consumers when downstream queues fill up. While paused, consumers receive no new records from paused partitions, so rising lag is expected behavior. Monitor pause duration, queue depth, and resume conditions.

### Offsets not being committed

Listeners may process records without acknowledging under the configured `AckMode`, or transactions may abort. Consumer position advances while committed offset stalls, keeping committed lag high. Check commit rate, commit latency, exceptions, and the acknowledgment flow.

## 11. Analyzing lag by partition and key

Total group lag can hide a hot partition. Sort partitions by descending lag and inspect:

- Whether the high-lag partition receives most of the traffic.
- Which keys account for the most records or unusually slow processing.
- Whether a specific record triggers retries or blocks the listener.
- Whether the partition is paused or lacks an assigned consumer.
- Whether consumer count and partition count match desired concurrency.

Kafka guarantees ordering within a partition. If one key continuously maps to a slow-processing partition, adding consumers cannot split that key's ordering. You may need to revisit the partition key, redesign the work, or split workloads by event type if business rules allow.

## 12. Lag and retention risk

Kafka retention does not wait for consumers to finish before deleting records. Topics can delete segments based on `retention.ms` or `retention.bytes` even while a consumer group still has lag. Once unread records exceed retention, the consumer can no longer re-read that data from Kafka.

Compare the age of the oldest unprocessed record against the topic's effective retention. During prolonged backlogs:

1. Estimate catch-up time from incoming rate and processing rate.
2. Compare that duration against remaining retention on the oldest record.
3. If retention expiry is at risk, scale processing capacity or adjust retention through an operational process that evaluates broker disk capacity.
4. If data has already expired past retention, identify an appropriate replay/backup source; do not assume Kafka can recover deleted records.

On compacted topics, old data can be compacted by key even before retention expires. When assessing backlogs on compacted topics, offset distance is even less reliable as an exact business record count.

## 13. How to handle high lag

Follow a structured investigation order:

1. Confirm the exact `group.id`, topic, and lagging partitions; check whether the group is `Stable`, `PreparingRebalance`, `Empty`, or another state.
2. Inspect per-partition lag and determine whether lag is concentrated or widespread.
3. Compare producer rate against consumer record rate to see whether the backlog is growing or shrinking.
4. Check consumer assignments, active consumer count, rebalances, and heartbeats.
5. Check listener processing time, downstream latency, retries, DLT, and queue backpressure.
6. Check commit rate/latency, AckMode, and transactions if position advances while committed offset stalls.
7. Check brokers/networking, request latency, fetch rates, and quotas if consumers cannot fetch fast enough.
8. Estimate catch-up time and compare it against retention and SLAs.
9. Take appropriate action: fix downstream errors, reduce listener latency, scale consumers within partition limits, tune batching, or add partitions after assessing ordering and key distribution.

Never reset offsets just to zero out dashboard lag. Resetting can skip unprocessed data or cause data to be reprocessed. Only modify offsets under an approved procedure that checks the group, partitions, target positions, and business impact.

## 14. Designing dashboards and alerts

Operational dashboards should include at minimum:

- Total lag by consumer group and topic.
- Maximum per-partition lag and top-N lagging partitions list.
- Lag over time and rate of growth/drain.
- Age of the oldest unprocessed record.
- Producer incoming rate and consumer processing rate.
- Consumer count, assigned partitions, rebalance rate, and heartbeats.
- Listener processing time, retry count, DLT rate, and pause duration.
- Broker request/fetch latency and network throughput for deep dives.

Base alerts on SLAs rather than a single threshold across every topic. For example, an order-status stream might require time lag under a few tens of seconds, while a batch analytics stream may tolerate multi-minute backlogs. Combine lag exceeding a threshold over a sustained window with record age breaching SLA to reduce false alerts.

## 15. Operations checklist

- [ ] Identified whether lag is measured from committed offset or consumer position.
- [ ] Understood whether end offset uses LEO, HW, or readable end/LSO.
- [ ] Monitored lag per partition rather than group total alone.
- [ ] Combined offset lag with time lag/record age.
- [ ] Compared incoming rate and processing rate to see if backlog is growing or shrinking.
- [ ] Tracked consumer count, assigned partitions, heartbeats, and rebalances.
- [ ] Checked retries, DLT, pause/backpressure, and commit flow when lag rises.
- [ ] Compared catch-up time against topic retention.
- [ ] Built dashboards and alerts aligned with each event stream's SLA.
- [ ] Avoided resetting offsets just to clear lag from a dashboard.

Consumer lag is an indicator of consumer group reading progress, not an isolated number sufficient to declare a system healthy or broken. Interpret committed offset, consumer position, and end offset accurately; examine lag by partition and over time; then correlate with throughput, rebalances, retries, and retention. This perspective shows whether consumers genuinely lack capacity, are absorbing a normal traffic burst, or are blocked by a specific operational fault.
