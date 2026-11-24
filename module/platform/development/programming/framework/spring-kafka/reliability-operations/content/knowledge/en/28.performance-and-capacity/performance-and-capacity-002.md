# batch.size and max.poll.records

In Spring Kafka, producer and consumer performance is heavily influenced by how records are grouped into batches. The producer accumulates multiple records before sending them to the broker; the consumer retrieves records in batches when calling `poll()`. Two settings frequently mentioned together are `batch.size` and `max.poll.records`, yet they control opposite sides and use different units:

- `batch.size` is the target size in **bytes** for a single producer batch per partition.
- `max.poll.records` is the **maximum number of records** returned by a single `poll()` call to the consumer application.

Understanding both limits properly helps increase throughput while keeping latency, memory usage, processing time, and consumer group rebalance risk under control.

## 1. Two Types of Batches on Two Sides of Kafka

Kafka does not have a single shared batch configuration for both producer and consumer. The producer and consumer have separate mechanisms for batching, transmitting, and processing data.

| Configuration | Component | Unit | Primary Impact |
|---|---|---|---|
| `batch.size` | Producer | Byte | Target size limit of the batch the producer accumulates per partition |
| `linger.ms` | Producer | Millisecond | Time the producer can wait to accumulate more records |
| `max.poll.records` | Consumer | Record | Maximum number of records returned in a single `poll()` call |
| `max.partition.fetch.bytes` | Consumer | Byte | Limit on fetched data per partition in a response, with an exception to guarantee progress on the first batch |
| `fetch.max.bytes` | Consumer | Byte | Limit on total fetched data in a response, also with an exception so the consumer is not blocked by the first batch |
| `max.poll.interval.ms` | Consumer | Millisecond | Maximum interval between `poll()` calls before the consumer is considered no longer making progress in the group |

Because one side is measured in bytes and the other in records, you cannot derive `max.poll.records` directly from `batch.size`. Actual record size varies with schema, payload, headers, and compression level.

## 2. Producer: `batch.size` and `linger.ms`

When the application calls `KafkaTemplate.send()`, the producer usually does not send each record as an independent request. The Kafka producer buffers records and groups them into batches per topic-partition inside the accumulator. A single request sent to a broker can contain batches belonging to multiple partitions.

### What Does `batch.size` Limit?

`batch.size` sets the target maximum size for a batch accumulated by the producer **per partition**. The value is typically configured in bytes. For example, `65536` corresponds to 64 KiB for one batch of one partition.

This value does not mean every batch will reach the exact configured size. If traffic arrives sparsely, a batch may be sent while still small. If many records arrive continuously on the same partition, the batch can fill quickly and be sent before the wait timeout expires.

Increasing `batch.size` can help the producer group more data into a single send, reduce request counts, and improve compression efficiency. However, larger batches also require more memory and can increase wait time under low traffic. If an application writes to many active partitions concurrently, total memory allocated for batches can grow significantly.

### `linger.ms` Creates Opportunities to Accumulate More Records

`linger.ms` is the duration the producer can wait before sending a partially filled batch. When a batch reaches its target size, the producer can send it immediately; when it is not yet full, reaching the wait timeout also triggers sending.

For example, if `linger.ms` is 5 ms, the producer can wait up to that duration to receive more records for the batch. This is a trade-off between throughput and latency:

- Low linger helps records get sent sooner, suiting latency-sensitive flows.
- High linger creates more opportunities to fill batches and compress more effectively when traffic is steady enough, but can increase end-to-end latency.

Do not increase `linger.ms` mechanically. If traffic is already high enough that batches fill consistently, increasing wait time may not bring commensurate benefits.

### Related Producer Configurations

`batch.size` should be evaluated alongside the following settings:

- `buffer.memory`: memory capacity the producer uses to buffer records waiting to be sent. When the buffer is exhausted, send operations may block up to `max.block.ms` and raise an error if space still cannot be obtained.
- `compression.type`: batch compression algorithm, such as `lz4`, `zstd`, `snappy`, or `gzip`. Compression is typically more effective when batches have enough data, though it consumes CPU.
- `max.request.size`: limit on the request size a producer can send. This limit is separate from `batch.size`; a request can contain batches for multiple partitions.
- `acks`, `enable.idempotence`, and retries: affect send reliability. Batch optimization should not compromise the delivery guarantees the system requires.

The producer can group multiple `KafkaTemplate.send()` calls into the same batch if they are sent through the same producer to the same partition within the right window. Calling `flush()` after every record usually eliminates batching opportunities, so only flush when application semantics truly require it.

## 3. Consumer: `max.poll.records`

The consumer pulls data from the broker via fetch requests. When the application calls `poll()`, Kafka returns at most the number of records specified by `max.poll.records` in a single call.

For example, with `max.poll.records=300`, a single `poll()` call may return 300 records, or fewer if not enough data is currently available. This is an upper bound, not a guarantee that every poll will return 300 records.

`max.poll.records` controls how many records the application receives in one poll. It does not directly cap the fetch response byte size and does not replace `fetch.min.bytes`, `fetch.max.wait.ms`, `fetch.max.bytes`, or `max.partition.fetch.bytes`. The consumer may prefetch data and hold fetched data in an internal buffer; the record count limit returned to the application is applied when `poll()` draws from that already-fetched data.

### Why Limit the Number of Records per Poll?

After polling, the consumer must process the records before returning to the next poll. If a single poll returns too many records, the application can encounter the following issues:

1. **Prolonged processing time:** the consumer takes longer before calling `poll()` again.
2. **Increased memory pressure:** deserialized records, intermediate objects, and business data can occupy far more memory than the raw network payload.
3. **Longer failure recovery time:** if a batch fails to process, many records may have to be reprocessed depending on commit configuration and the error handler.
4. **Risk of exceeding `max.poll.interval.ms`:** if the interval between two polls exceeds the threshold, the consumer may be evicted from the group and partitions reassigned.

Conversely, if `max.poll.records` is too low, the application may poll frequently with small batches, increasing overhead and reducing throughput utilization, especially when each processing cycle carries significant fixed cost.

### Relationship with `max.poll.interval.ms`

`max.poll.interval.ms` sets the time limit between two `poll()` calls from a consumer participating in a group. This setting is especially important when the listener processes records synchronously.

Suppose a single poll returns 300 records and the listener processes sequentially at an average of about 8 ms per record. Record processing takes around 2.4 seconds, excluding deserialization, external service calls, database writes, offset commits, and JVM pauses. This is only an estimate for time budgeting; in operations, you must measure the actual time distribution, especially p95 and p99.

Keep sufficient headroom so the consumer completes processing and returns to poll before hitting `max.poll.interval.ms`. If a batch consistently takes too long, lowering `max.poll.records`, optimizing processing, or scaling processing capacity may be more appropriate. Only increase `max.poll.interval.ms` when long processing times are intentional and the system has adequate memory, fault tolerance, and corresponding recovery mechanisms.

`session.timeout.ms` plays a different role: it relates to the coordinator detecting a consumer's lost heartbeat. In modern Java consumers, heartbeats can be maintained in the background while the application processes, yet exceeding `max.poll.interval.ms` can still mark the consumer as stalled and trigger group departure/rebalance. These two timeouts should not be used interchangeably.

## 4. Configuration in Spring Boot

The example below configures the producer to accumulate 64 KiB batches, wait up to 5 ms, and use LZ4; the consumer receives up to 300 records per poll. These values are starting points for experimentation, not optimal parameters for every workload.

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
        enable.idempotence: true
    consumer:
      enable-auto-commit: false
      max-poll-records: 300
      properties:
        max.poll.interval.ms: 300000
        fetch.min.bytes: 1
        fetch.max.wait.ms: 500
        max.partition.fetch.bytes: 1048576
```

In the configuration above:

- `batch-size` is the Spring Boot property that maps to Kafka producer `batch.size`.
- `max-poll-records` maps to Kafka consumer `max.poll.records`.
- Kafka properties without a dedicated Spring Boot field can be passed under `properties`.
- `enable-auto-commit: false` lets the Spring Kafka container manage commits according to the chosen acknowledgment mode. Configure the acknowledgment mode and error handling to match the application's delivery requirements.

If using Spring Kafka directly via Java configuration, you can set the corresponding properties in `ProducerConfig` and `ConsumerConfig` and pass them into `DefaultKafkaProducerFactory` and `DefaultKafkaConsumerFactory`. Whether using YAML or Java config, the Kafka property names and semantics remain the same.

## 5. `max.poll.records` and Batch Listeners in Spring Kafka

`max.poll.records` limits the number of records returned from a single poll in the Kafka client. This setting **does not automatically turn a single-record listener into a list-receiving listener**.

With a record listener, Spring Kafka invokes the listener method for each record. If you want the application to receive the entire batch in a single listener invocation, enable batch listener mode on the container factory or choose the batch listener type in Spring Boot configuration.

For example, with Spring Boot configuration:

```yaml
spring:
  kafka:
    listener:
      type: batch
```

The listener can receive a list of records as follows:

```java
@KafkaListener(topics = "orders", groupId = "order-worker")
public void consume(List<ConsumerRecord<String, OrderEvent>> records) {
    for (ConsumerRecord<String, OrderEvent> record : records) {
        orderService.process(record.value());
    }
}
```

When a batch listener returns normally, the container applies the configured acknowledgment mode to commit offsets. Clearly define commit timing and exception handling. If processing fails mid-batch, previously processed records may be redelivered depending on the error handler, committed offsets, and retry strategy. Therefore, business operations should be idempotent or include deduplication safeguards.

With a record listener, the application is still affected by the number of records in a poll: the container must process the received records before continuing the poll loop. A batch listener changes how the listener receives data; it does not remove the need to control total processing time.

## 6. How to Choose Values by Workload

There is no single pair of `batch.size` and `max.poll.records` values that fits every system. Choose them based on record size, traffic, processing time, and latency targets.

### For the Producer

1. Measure typical record size and traffic per partition.
2. Observe `batch-size-avg` and `batch-size-max` to see whether actual batches are close to the configured size.
3. If batches are frequently small because records arrive sparsely, try increasing `linger.ms` in small increments and monitor latency.
4. If batches regularly fill up while the request rate stays high, try increasing `batch.size` within memory and request size limits.
5. Monitor compression ratio, CPU, buffer wait time, and request latency to determine whether the benefits outweigh the costs.

If the producer serves transactions requiring immediate responses, prioritize latency and only increase wait time when metrics prove the benefit. If the producer sends large, steady event streams and can tolerate a few extra milliseconds of wait, larger batches can improve throughput.

### For the Consumer

1. Measure single-record processing time and total poll processing time under realistic load.
2. Choose `max.poll.records` so that a single poll's processing time stays well below `max.poll.interval.ms`, even when slow records or delayed external dependencies occur.
3. Monitor heap, allocation, GC, and payload size. The same record count with larger payloads can create very different memory pressure.
4. Check lag and consumption rate when changing record counts. Increasing batch size does not solve bottlenecks in databases or downstream services.
5. Test with partition skew, burst traffic, large records, retries, and rebalances to verify behavior under non-ideal conditions.

An initial estimate for sequential processing is:

\[
N_{poll} \times T_{record} + T_{overhead} < T_{poll\ interval\ budget}
\]

Where `N_poll` is the number of records processed in one poll, `T_record` is the representative processing time for one record, and `T_overhead` includes deserialization, commits, dependency calls, and other overhead. Use p95/p99 measurements and peak load to set a realistic budget; do not rely solely on average times.

For example, if one record typically takes 20 ms and processing is sequential, a batch of 500 records already needs about 10 seconds for the core processing alone. If some records occasionally take several seconds due to external service calls, total poll duration can rise sharply. In that scenario, reducing batch size, setting dependency timeouts, using controlled retries, or designing asynchronous processing may be necessary.

## 7. Signs of Misconfiguration

| Symptom | Possible Cause | What to Check |
|---|---|---|
| Producer sends many small requests | Low traffic per partition, `linger.ms` too low, or small batch size | Check `batch-size-avg`, try increasing linger or batch size, and measure latency |
| Producer latency rises when increasing linger | Batch accumulation wait time exceeds latency budget | Reduce `linger.ms`, inspect latency percentiles |
| Producer waits on buffer or send blocks | Buffer lacks space, slow broker, congested requests, or send rate exceeds capacity | Check buffer pool wait, request latency, broker, and `buffer.memory` |
| Consumer lag grows despite polling many records | Business processing or downstream dependency is the bottleneck | Measure listener, database, API time, and actual processing rate |
| Consumer rebalances frequently | Processing time between two polls is too long, consumer hangs, or loses connection | Compare poll duration against `max.poll.interval.ms`, inspect group logs and GC pauses |
| Consumer uses high heap or GC increases | One poll holds too many records or large payloads | Reduce `max.poll.records`, inspect deserialized object sizes and heap |
| Low throughput with very small batches | High poll/listener overhead or consumer is not utilizing enough data | Gradually increase `max.poll.records` and measure throughput, latency, and memory |

The signs above are starting points for investigation. Correlate producer, consumer, broker, and dependency metrics to pinpoint the exact bottleneck.

## 8. Metrics to Monitor

When tuning batching, monitor throughput, latency, and resources simultaneously.

**Producer:**

- `batch-size-avg`, `batch-size-max`: actual batch sizes.
- `records-per-request-avg`: average records per outgoing request.
- `compression-rate-avg`: compression efficiency.
- `record-queue-time-avg`: time records spend in the queue before sending.
- `bufferpool-wait-time`: wait time to acquire buffer space.
- Request latency, retries, and error rate: broker or network impact on sending.

**Consumer:**

- `records-consumed-rate`: record consumption rate.
- `records-lag-max`: maximum observed partition lag.
- `fetch-size-avg` and `fetch-rate`: fetch size and frequency.
- `fetch-latency-avg`: fetch latency.
- `poll-idle-ratio-avg` and listener processing time: how busy the consumer and application are.
- Heap, GC pauses, commit latency, and rebalance count: batching impact on the process.

Exact metric names may vary by Kafka client version and monitoring system. Verify the metrics actually exported in the running environment before creating alerts.

## 9. Operational Principles

- Change one configuration group at a time and keep a baseline for comparison.
- Measure both throughput and p95/p99 latency; higher throughput with latency or error rate exceeding SLOs is still a bad outcome.
- Check per partition. A hot partition can produce large batches while other partitions have small batches.
- When increasing `max.poll.records`, inspect both deserialized memory and processing time, not just network fetch size.
- Maintain idempotency in consumer processing if retries or batch failures can cause records to be redelivered.
- When scaling consumption capacity, check partition count and concurrency. Adding consumers beyond assigned partitions does not create additional parallelism for the same group.
- Put configurations validated through load testing and production observation into controlled configuration management; avoid changing multiple parameters simultaneously, which makes root-cause analysis difficult.

## 10. Technical Conclusion

`batch.size` governs byte-based batching on the producer; `linger.ms` governs how long the producer can wait to accumulate a batch. `max.poll.records` governs the maximum number of records a consumer receives from a single poll; `max.poll.interval.ms` caps how long the application can process before the next poll.

Optimize the producer based on actual batch sizes, request rate, compression, and latency. Optimize the consumer based on processing time per poll, memory, lag, and consumer group stability. When tuning is grounded in metrics and representative load tests, the system can achieve better throughput while maintaining appropriate latency and resilience.
