# Consumer Fetch Sizing

In Spring Kafka, **consumer fetch sizing** is the practice of choosing the size and cadence of data that a Kafka consumer retrieves from the broker. Fetch settings directly affect **throughput, latency, memory, network utilization, the ability to handle large records, and consumer group stability**. A consumer that fetches too little data can generate many small requests, waste network round trips, and miss batching opportunities. A consumer that fetches too much data can hold large amounts of records in memory, prolong listener processing, increase garbage collection, and exceed the time limit between polls.

Key settings include **fetch.min.bytes**, **fetch.max.wait.ms**, **max.partition.fetch.bytes**, **fetch.max.bytes**, and **max.poll.records**. They do not substitute for one another: some control the response size from the broker, while others control how many records a single poll returns. To size properly, you must understand **the Kafka fetch protocol, compressed record batches, Spring listener containers, consumer concurrency, partition assignment, max.poll.interval.ms, and downstream processing capacity**.

There is no single optimal set of fetch values for every application. The goal is to pick sizes large enough to achieve target throughput, small enough to keep latency and memory within budget, and balanced so the listener finishes processing before the consumer must poll again.

## 1. How Does Consumer Fetch Work?

A Kafka consumer does not ask the broker to send records one by one. The consumer sends a **FetchRequest** for the partitions it owns. The broker returns available record batches according to the configured fetch limits and wait conditions.

A simplified cycle:

~~~text
Spring Kafka listener container
          |
          v
KafkaConsumer.poll()
          |
          v
FetchRequest to broker
  - partitions
  - fetch limits
  - minimum bytes
          |
          v
Kafka broker
  - checks available data
  - waits if below fetch.min.bytes
  - waits no longer than fetch.max.wait.ms
          |
          v
FetchResponse
  - record batches
  - offsets
  - metadata
          |
          v
KafkaConsumer buffer/cache
          |
          v
poll() returns records to container
          |
          v
@KafkaListener processes
~~~

The consumer can prefetch data and keep it in internal buffers. Therefore, when the broker returns a FetchResponse and when the listener processes each record do not necessarily coincide.

**Fetch sizing controls how data is retrieved from the broker; max.poll.records controls how many records are returned in one poll call.** This is the most important distinction when tuning.

## 2. Five Settings to Distinguish

| Setting | Controls | Unit |
|---|---|---|
| **fetch.min.bytes** | Minimum amount of data the broker tries to accumulate before returning a response | bytes |
| **fetch.max.wait.ms** | Maximum time the broker waits when fetch.min.bytes is not yet met | milliseconds |
| **max.partition.fetch.bytes** | Limit on fetched data per partition in a single request | bytes |
| **fetch.max.bytes** | Limit on total FetchResponse data for a single request | bytes |
| **max.poll.records** | Maximum number of records returned in one poll call | records |

These settings are related, yet none replaces another:

- `fetch.min.bytes` and `fetch.max.wait.ms` create a trade-off between batching and latency.
- `max.partition.fetch.bytes` protects against a single partition dominating a fetch.
- `fetch.max.bytes` bounds response size at the request level.
- `max.poll.records` limits the number of records the application receives per poll.
- `max.poll.interval.ms` caps the time between poll calls; it is not a fetch-size setting, yet it directly influences the choice of `max.poll.records`.

## 3. fetch.min.bytes: Waiting for Enough Data to Batch

**fetch.min.bytes** is the minimum amount of data the broker tries to return for a FetchRequest. If available data is below the threshold, the broker can wait for more records until enough bytes accumulate or `fetch.max.wait.ms` expires.

The default is typically **1 byte**, meaning the broker can return data as soon as suitable data is available without waiting to accumulate a large batch.

Example:

~~~text
fetch.min.bytes = 65536  (64 KiB)
fetch.max.wait.ms = 200

t=0ms    Consumer sends FetchRequest
t=20ms   Broker has 8 KiB
t=60ms   Broker has 24 KiB
t=110ms  Broker has 70 KiB
         -> min bytes reached
         -> broker returns response
~~~

If 64 KiB has still not accumulated after 200 ms, the broker does not wait indefinitely; it returns whatever data is available according to fetch semantics.

Increasing `fetch.min.bytes` can:
- Reduce small responses under steady traffic.
- Increase data volume per response.
- Improve network efficiency and batching.
- Increase latency for low-traffic topics or low-volume partitions.
- Increase the burst of data arriving together, affecting memory and processing spikes.

Do not set a large `fetch.min.bytes` solely to maximize throughput if business requirements demand processing records as soon as they arrive.

## 4. fetch.max.wait.ms: Bounding Batch Wait Time

**fetch.max.wait.ms** is the maximum time the broker waits to reach `fetch.min.bytes` before returning a response.

Example:
- `fetch.min.bytes` = 128 KiB
- `fetch.max.wait.ms` = 100 ms

If the consumer receives data rapidly, the broker can respond as soon as 128 KiB is reached. Under slow traffic, the broker returns after at most roughly 100 ms with whatever data is currently available.

Effects:
- Lower values: shorten wait time; may increase small fetch responses.
- Higher values: increase batching opportunities, but add latency under low traffic.
- Excessive values: new records may sit in broker buffers longer even when the consumer is healthy.

`fetch.max.wait.ms` is not the time the listener is allowed to process records and does not replace `max.poll.interval.ms`.

## 5. max.partition.fetch.bytes: Per-Partition Limit

**max.partition.fetch.bytes** is the maximum amount of data the consumer asks the broker to return per partition in a single FetchResponse.

Example:
- Topic `orders` has 12 partitions.
- The consumer currently owns 3 partitions.
- `max.partition.fetch.bytes` = 1 MiB.

Each partition can contribute data up to the corresponding limit in the response, subject to overall `fetch.max.bytes` and broker fetch rules.

This setting is useful when:
- One partition has higher traffic than other partitions.
- The consumer needs to cap data pulled from individual partitions.
- Large record batches are present.
- You want to prevent a single partition from monopolizing fetch buffers.

A common default is **1 MiB**. Verify against your Kafka client version and actual largest record batch size.

### 5.1. Progress Exception for the Consumer

`max.partition.fetch.bytes` is not an absolute hard cap in all cases. Kafka guarantees the consumer can still make progress: if the first batch in the first non-empty partition of a fetch request exceeds the limit, the broker can still return that batch so the consumer is not permanently stuck unable to fetch any batch small enough.

This means:
- Do not rely on `max.partition.fetch.bytes` to reject all oversized records.
- The consumer can still receive a batch exceeding the configured limit in special cases.
- If large record batches exist, size memory and downstream accordingly.
- Producer/broker message size limits must still be designed separately.

## 6. fetch.max.bytes: FetchResponse-Level Limit

**fetch.max.bytes** limits the total amount of data the broker tries to return for a single FetchRequest. This is an aggregate limit, distinct from the per-partition limit.

Example:
~~~text
fetch.max.bytes = 16 MiB
max.partition.fetch.bytes = 4 MiB

A response can pull data from multiple partitions,
but the total requested data is capped
at fetch.max.bytes under Kafka semantics.
~~~

`fetch.max.bytes` prevents a single request from pulling too much data across many partitions at once. However, just like `max.partition.fetch.bytes`, Kafka includes an exception for the first batch needed so the consumer can make progress. Thus, this is not an absolute hard memory cap.

A common default is **50 MiB**. Do not raise this value without accounting for:
- Number of consumers per pod.
- Number of broker connections.
- Number of assigned partitions.
- Number of FetchResponses that may be in flight.
- Compression ratio.
- Deserialized object sizes.
- Records remaining in consumer buffers and application queues.

## 7. max.poll.records: Records per Poll

**max.poll.records** caps the maximum number of records returned to the application by a single `KafkaConsumer.poll()` call.

Example:
~~~text
max.poll.records = 200

poll() may return:
  200 records
  or 120 records
  or 5 records
  or 0 records
~~~

A common default is **500**.

`max.poll.records` does not directly control how many bytes the broker fetches. The Kafka consumer may already have prefetched data into buffers before poll returns records. If `max.poll.records` is set low, buffered data can be handed out across multiple polls.

Increasing `max.poll.records`:
- Can lower per-record overhead and leverage batch processing.
- Can increase throughput when the listener processes batches efficiently.
- Increases processing time per poll when the listener runs synchronously.
- Raises the risk of exceeding `max.poll.interval.ms`.
- Can increase the volume of records held in application memory.

Decreasing `max.poll.records`:
- Reduces the number of records in a single poll.
- Helps the listener return to poll more frequently when processing record by record.
- Can reduce processing bursts.
- Can reduce throughput if per-poll overhead is significant.
- Does not guarantee proportional memory reduction because the consumer may already have prefetched data.

**max.poll.records is a record count limit, not a byte limit.**

## 8. Fetch Sizing and max.poll.interval.ms

A Kafka consumer group expects the consumer to call poll at a steady cadence. **max.poll.interval.ms** bounds the maximum interval between polls in the corresponding consumer group model.

If the listener takes too long before the next poll:
- The consumer may be considered stalled.
- Partition assignments may be revoked.
- The consumer group may rebalance.
- Uncommitted records may be redelivered.
- Business side effects may repeat if not idempotent.

Example:
~~~text
max.poll.records = 500
processing time per record = 100 ms

Theoretical max processing time:
  500 × 100 ms = 50,000 ms
~~~

Fifty seconds excludes deserialization, logging, database waits, transaction commits, error handling, and scheduling delays. If `max.poll.interval.ms` is 60 seconds, the safety margin can be very thin.

A rough estimate:
\[
T_{\mathrm{poll}} \approx N_{\mathrm{records}} \times T_{\mathrm{record}}
\]

Ensure poll processing time at tail latency (e.g., p99) stays well below `max.poll.interval.ms` with adequate margin.

Do not pick `max.poll.records` based solely on average processing time. An unusually slow record or downstream timeout can stretch out an entire batch.

## 9. Relationship Between Fetch Limits and Memory

Consumer fetch sizing affects memory across multiple layers:
1. Bytes received from the broker.
2. Compressed record batches in network/client buffers.
3. Decompressed data.
4. Deserialized Java objects.
5. Records returned from poll and held in the container/listener.
6. Application work queues or asynchronous tasks.
7. Logging/metrics/tracing context.

A 10 MiB response on the wire can produce a much larger footprint after decompression and deserialization, especially when payloads are JSON with many objects/strings.

You cannot calculate memory accurately from `fetch.max.bytes` alone.

An initial application estimate:
~~~text
memory pressure
  ≈ fetch buffers
  + decompressed batches
  + deserialized records
  + listener in-flight work
  + application queues
  + JVM overhead
~~~

With concurrency 8, you cannot treat one consumer fetch buffer as the entire pod's memory. Each consumer maintains its own state/buffers and multiple consumers can fetch simultaneously.

When sizing:
- Use the actual number of consumers per pod.
- Measure p95/p99 record and batch sizes.
- Measure compression ratio.
- Measure deserialized object footprint.
- Measure queue depth/in-flight tasks.
- Leave heap headroom for GC, transactions, and framework objects.

## 10. Compression Changes the Math

Kafka producers can compress record batches using gzip, snappy, lz4, or zstd depending on configuration and client version.

The consumer receives compressed data over the network and then must decompress it to process records. Consequently:
- Bytes on the wire can be far smaller than the object graph in heap.
- `fetch.max.bytes` does not directly reflect post-deserialization data size.
- A single compressed batch can contain many records.
- Compression ratios vary with payload content.
- Repetitive text/JSON payloads may compress better than already-encrypted or pre-compressed payloads.

Example:
~~~text
Compressed batch on wire: 2 MiB
After decompression:       12 MiB
After deserialization:     25 MiB heap estimate
~~~

These numbers are illustrative only. Measure with production-like payloads rather than applying a fixed compression ratio across all topics.

## 11. Record Batch Size and Producer/Broker Limits

Consumer fetch settings must align with message/batch size limits in other components:
- Producer `max.request.size`.
- Producer `batch.size`.
- Broker `message.max.bytes` or topic `max.message.bytes`.
- Consumer `max.partition.fetch.bytes`.
- Consumer `fetch.max.bytes`.
- Record batch and serializer limits.

If the producer is allowed to send batches larger than `max.partition.fetch.bytes`, Kafka still has the first-batch exception to ensure progress, yet applications should be configured intentionally rather than relying on the exception.

For large records:
1. Determine the actual maximum batch size.
2. Check whether broker/topic limits allow it.
3. Check whether producer request limits allow it.
4. Size consumer partition fetch adequately for normal workloads.
5. Evaluate post-deserialization heap.
6. Check timeouts, retries, and DLTs that may carry large records.
7. Prevent a single giant record from exhausting the memory budget.

Do not raise all message/fetch limits to hundreds of MiB just to make one special record work. Consider storing large payloads in object storage and sending only a reference through Kafka.

## 12. Example of Calculating a Poll Processing Budget

Suppose:
- `max.poll.records` = 120.
- Processing time p50 = 8 ms/record.
- Processing time p95 = 20 ms/record.
- Processing time p99 = 45 ms/record.
- `max.poll.interval.ms` = 300,000 ms.

Estimates:
~~~text
p50 poll work:
  120 × 8 ms = 960 ms

p95 poll work:
  120 × 20 ms = 2,400 ms

p99 worst-like poll work:
  120 × 45 ms = 5,400 ms
~~~

These multiplications assume sequential processing and use percentiles as a simplified estimate. Tail latency for an entire batch can be higher due to distributions and downstream contention.

If the listener processes in parallel, account for worker concurrency, queuing, and completion wait times; do not simply divide total time by thread count.

The objective is to maintain a safe margin between poll calls, not to consume all of `max.poll.interval.ms`.

## 13. Configuring Fetch Properties in Spring Boot

Spring Boot lets you configure Kafka consumer properties in application YAML. Example:

~~~yaml
spring:
  kafka:
    consumer:
      bootstrap-servers: localhost:9092
      group-id: orders-service
      properties:
        "[fetch.min.bytes]": 65536
        "[fetch.max.wait.ms]": 100
        "[max.partition.fetch.bytes]": 4194304
        "[fetch.max.bytes]": 16777216
        "[max.poll.records]": 200
        "[max.poll.interval.ms]": 300000
~~~

The values above form an illustrative configuration:
- `fetch.min.bytes` = 64 KiB.
- `fetch.max.wait.ms` = 100 ms.
- `max.partition.fetch.bytes` = 4 MiB.
- `fetch.max.bytes` = 16 MiB.
- `max.poll.records` = 200.
- `max.poll.interval.ms` = 5 minutes.

Bracket notation keeps dotted property keys intact inside the properties map under Spring Boot binding conventions. Verify the exact syntax against your Boot version.

Do not copy this exact set of values into production without measuring throughput, latency, and memory.

## 14. Configuration via DefaultKafkaConsumerFactory

If creating `ConsumerFactory` manually, you can put Kafka `ConsumerConfig` properties in a map:

~~~java
@Bean
ConsumerFactory<String, OrderEvent> orderConsumerFactory() {
    Map<String, Object> props = new HashMap<>();

    props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
    props.put(ConsumerConfig.GROUP_ID_CONFIG, "orders-service");

    props.put(ConsumerConfig.FETCH_MIN_BYTES_CONFIG, 64 * 1024);
    props.put(ConsumerConfig.FETCH_MAX_WAIT_MS_CONFIG, 100);
    props.put(ConsumerConfig.MAX_PARTITION_FETCH_BYTES_CONFIG, 4 * 1024 * 1024);
    props.put(ConsumerConfig.FETCH_MAX_BYTES_CONFIG, 16 * 1024 * 1024);
    props.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 200);
    props.put(ConsumerConfig.MAX_POLL_INTERVAL_MS_CONFIG, 300_000);

    return new DefaultKafkaConsumerFactory<>(
            props,
            new StringDeserializer(),
            new JsonDeserializer<>(OrderEvent.class));
}
~~~

This is illustrative code; serializers/deserializers must be configured with type mappings, trusted packages, and schema policies appropriate for your application.

`ConsumerConfig` constants help avoid property name typos. Keep security properties like SASL/TLS and other consumer options from your real configuration rather than replacing them with the minimal map in the example.

## 15. Configuring Fetch for the Listener Container

`ConsumerFactory` creates consumers with Kafka client properties. The listener container determines how records are polled and dispatched.

Example factory:
~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        ordersKafkaListenerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    factory.getContainerProperties()
            .setPollTimeout(1_000L);

    return factory;
}
~~~

**concurrency** is the number of consumer threads/child containers for the listener, subject to partition assignments and container type. Raising concurrency can increase parallel consumption, but also increases Kafka consumers, connections, buffers, and memory footprint.

The Spring container's `pollTimeout` is how long the container waits for poll to return in its poll invocation; it is not `fetch.max.wait.ms` and does not replace `fetch.max.wait.ms`.

A sound configuration must coordinate:
- Kafka fetch limits in `ConsumerFactory`.
- Listener container concurrency.
- Poll timeout.
- AckMode.
- Record/batch listener mode.
- Error handler/backoff.
- `max.poll.interval.ms`.

## 16. Record Listeners and Batch Listeners

Record listener:
~~~java
@KafkaListener(
        topics = "orders.created",
        containerFactory = "ordersKafkaListenerFactory")
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

Batch listener:
~~~java
@KafkaListener(
        topics = "orders.created",
        containerFactory = "ordersBatchListenerFactory")
public void consumeBatch(List<OrderEvent> events) {
    orderService.processBatch(events);
}
~~~

A batch listener can leverage database batch writes or bulk APIs, however:
- A single callback can process many records.
- Callback duration grows with batch size.
- One failing record can affect batch processing/error handling.
- You must understand acknowledgment and partial batch failure semantics.
- `max.poll.records` affects how many records may be returned from one poll.

With a record listener, the container usually dispatches records individually, yet poll can still retrieve a large batch of records. Do not mistakenly assume that a record listener means Kafka fetches only one record per request.

## 17. Concurrency and Total Fetch Capacity

Suppose:
- 6 partitions.
- Listener concurrency = 3.
- Each consumer receives roughly 2 partitions.
- `fetch.max.bytes` = 16 MiB.

Do not conclude that the whole pod uses at most 16 MiB. `fetch.max.bytes` applies to a single FetchRequest; multiple consumers and requests can be active concurrently.

One way to view the budget:
~~~text
Pod
  |
  +-- Consumer 0 -> fetch buffers, records, listener work
  |
  +-- Consumer 1 -> fetch buffers, records, listener work
  |
  +-- Consumer 2 -> fetch buffers, records, listener work
  |
  +-- Spring container + application heap
~~~

Increasing concurrency:
- Can increase total throughput when partitions are sufficient and processing runs in parallel.
- Increases network connections and broker requests.
- Increases memory buffers and deserialization work.
- Can worsen database/API contention.
- Brings no benefit if concurrency exceeds the partitions assignable to the group.

Fetch sizing must be evaluated at the **pod and cluster level**, not merely per consumer.

## 18. How Does Partition Count Affect Fetch Sizing?

Consumer fetch requests can span multiple partitions. A consumer owning multiple partitions can pull data from several partitions in a single request, subject to fetch limits.

Example:
~~~text
Consumer A owns:
  orders/P0
  orders/P1
  orders/P2
  orders/P3

Consumer B owns:
  orders/P4
  orders/P5
  orders/P6
  orders/P7
~~~

If P0 has heavy traffic while P1–P3 are nearly empty, Consumer A's fetch response may come mostly from P0. `max.partition.fetch.bytes` helps cap how much is pulled from each partition, while `fetch.max.bytes` caps the total request level.

Increasing partition count can:
- Increase the number of partitions fetched by a consumer.
- Increase metadata and per-partition state.
- Increase partition-level buffers/requests.
- Increase total series/metrics.
- Create more parallelism opportunities if consumer capacity exists.

Do not simply increase `fetch.max.bytes` when adding partitions; measure response sizes, broker load, and consumer memory.

## 19. Partition Skew and Hot Partitions

A topic may have uneven traffic distribution:
~~~text
P0: 80% traffic
P1: 5%
P2: 5%
P3: 5%
P4: 5%
~~~

If one consumer owns P0, it may be bottlenecked by the hot partition even though other partitions have little data.

Tuning `fetch.max.bytes` cannot fix partition skew. Instead:
- Inspect the partition key strategy.
- Measure throughput/lag per partition.
- Check whether a hot key concentrates records in one partition.
- Consider changing key distribution or topic partitioning.
- Verify ordering requirements before changing keys.
- Review consumer assignment/concurrency.

Do not raise `max.partition.fetch.bytes` for every partition just to handle one hot partition without measuring memory and broker impact.

## 20. fetch.min.bytes Has Different Implications by Traffic Profile

### High-Throughput Stream

When records arrive continuously, a higher `fetch.min.bytes` can group larger responses and lower overhead.

### Low-Throughput Command Topic

If only a few records arrive per minute, a large `fetch.min.bytes` causes the consumer to frequently wait until `fetch.max.wait.ms`. This adds latency to commands.

### Bursty Workload

When traffic arrives in bursts, min bytes can pack records well during bursts yet add delay in between bursts.

### Latency-Sensitive Event

If every record must be processed immediately, keeping `fetch.min.bytes` small and `fetch.max.wait.ms` low is usually more appropriate.

Do not tune based on average throughput. Measure p50/p95/p99 latency across both quiet periods and peaks.

## 21. Example of the Trade-off Between Batching and Latency

Suppose:
- Incoming rate = 2,000 records/second.
- Average compressed record size = 1 KiB.
- `fetch.min.bytes` = 64 KiB.
- `fetch.max.wait.ms` = 100 ms.

At a steady rate, 64 KiB can accumulate quickly; the broker returns the response before the timeout. Yet at 10 records/second, 64 KiB could take many seconds to accumulate, so the broker responds according to `fetch.max.wait.ms`.

~~~text
High traffic:
  min bytes reached quickly
  -> low additional wait

Low traffic:
  min bytes not reached
  -> wait until max wait
  -> return smaller response
~~~

That is why `fetch.max.wait.ms` is a critical latency bound under low traffic. `fetch.min.bytes` does not mean the consumer will wait for that many bytes regardless of elapsed time.

## 22. fetch.min.bytes Is Not Broker-Side batch.size

Two commonly confused settings:
- Producer `batch.size` controls how the producer groups records before sending.
- Consumer `fetch.min.bytes` controls how much data the broker waits for in a fetch response.
- `fetch.max.wait.ms` bounds how long the broker waits for data.
- Producer `linger.ms` controls how long the producer waits to accumulate a batch.

Producer batching and consumer fetch batching sit at opposite ends of the pipeline.

~~~text
Producer:
  linger.ms + batch.size
       |
       v
Kafka record batches
       |
       v
Broker log
       |
       v
Consumer:
  fetch.min.bytes + fetch.max.wait.ms
       |
       v
FetchResponse
~~~

Increasing `linger.ms` can improve producer batching but adds latency on the input side. Increasing `fetch.min.bytes` can improve fetch response batching but adds latency on the output side. Measure end-to-end latency rather than optimizing each side in isolation.

## 23. receive.buffer.bytes and Network Socket Buffers

**receive.buffer.bytes** configures the consumer's socket receive buffer, which differs from `fetch.max.bytes`. It controls the TCP socket receive buffer size in the Kafka client/network stack.

Increasing `receive.buffer.bytes` can help throughput on high-bandwidth/high-latency networks in some cases, however:
- The OS may adjust the actual value.
- Many connections increase total socket memory.
- It does not make the broker return more records at the protocol level.
- It does not replace fetch limits.
- TCP/network behavior must be measured.

Do not scale socket receive buffers proportionally with `fetch.max.bytes` without understanding the network path and connection count.

## 24. request.timeout.ms and fetch.max.wait.ms

These two settings serve different purposes:
- `fetch.max.wait.ms`: maximum time the broker waits to satisfy `fetch.min.bytes`.
- `request.timeout.ms`: how long the client waits for a response to a request before treating it as timed out under Kafka client semantics.
- `default.api.timeout.ms`: default timeout for certain AdminClient APIs, not consumer fetch waits.
- `max.poll.interval.ms`: maximum time between polls.

Avoid setting `request.timeout.ms` too low relative to `fetch.max.wait.ms` plus network latency. If a request timeout triggers before the broker can return a normal fetch response, the consumer can generate unnecessary errors/retries.

Do not raise `request.timeout.ms` to mask a slow listener callback; listener processing time belongs to the poll interval and application processing, not fetch request timeout.

## 25. Fetch Sizing and Broker Quotas

Brokers may enforce quotas per client/user and on network/request rates. Overly aggressive consumer fetch tuning can:
- Increase network throughput.
- Increase fetch request rate if batches are small.
- Increase response size if fetches are large.
- Increase broker memory/network pressure.
- Trigger throttling when quotas are exceeded.

When consumer throughput fails to rise despite higher fetch limits, check:
- Consumer lag.
- Broker throttling metrics.
- Network throughput.
- Request latency.
- Number of fetch requests.
- Consumer CPU and GC.
- Listener processing latency.
- Quota configuration.

Do not conclude `fetch.max.bytes` is too low if the consumer is actually being throttled or downstream is slow.

## 26. Broker Replica Fetch Settings Are Not Consumer Fetch Settings

Kafka brokers have **replica.fetch.max.bytes** and other replication fetch settings. These serve follower replicas fetching data from the leader for replication.

Consumer settings such as `fetch.max.bytes` and `max.partition.fetch.bytes` serve application consumers.

Do not change `replica.fetch.max.bytes` merely to increase a Spring Kafka listener's throughput. They are two separate data flows:
~~~text
Application consumer:
  Consumer fetch properties
  -> application

Broker replication:
  Replica fetch properties
  -> follower broker
~~~

If replication lags or the ISR shrinks, investigate broker replication rather than using consumer fetch sizing to address it.

## 27. Isolation Level Affects What Data the Consumer Sees

A consumer using **isolation.level=read_committed** only receives committed transactional records and does not advance past the Last Stable Offset when an open transaction exists.

This can prevent the consumer from receiving new records even though the broker has already stored data behind an open transaction.

~~~text
Log:
  committed record A
  open transaction T1
  later record B

read_committed consumer:
  may wait for T1 to finish before reading past that region
~~~

If the consumer appears stalled despite large fetch settings, check:
- Transaction duration.
- Producer commit/abort.
- Last Stable Offset.
- Transaction coordinator.
- Consumer lag semantics.

Increasing `fetch.max.bytes` will not help a consumer read past an open transaction when isolation semantics forbid it.

## 28. max.poll.records and Batch Listener Sizing

With a batch listener, `max.poll.records` acts largely as the cap on how many records can be delivered in a single poll. A large batch can improve bulk operation efficiency, yet also causes:
- Longer database transactions.
- Higher heap object counts.
- Costlier batch retries.
- More complex partial failures.
- Longer intervals between poll calls.

Example:
~~~text
max.poll.records = 500
average DB write = 3 ms/record

Sequential batch work:
  500 × 3 ms = 1,500 ms
~~~

If a bulk insert takes 200 ms for 500 records, batching can be more efficient. Still, measure p99 and inspect transaction/lock contention.

Choose batch size based on:
- Database batch capacity.
- Downstream API request limits.
- Memory footprint.
- Retry semantics.
- Poll interval budget.
- Latency objective.

Do not use a large `max.poll.records` merely because a batch listener can accept a list.

## 29. max.poll.records and Asynchronous Processing

A listener can hand records off to an executor and return. The poll loop can then continue rapidly, yet the application work queue grows.

~~~text
Kafka poll
  |
  v
max.poll.records records
  |
  v
listener enqueues work
  |
  v
poll returns
  |
  v
next poll
  |
  v
worker queue grows
~~~

If enqueuing outpaces worker processing:
- Memory grows with queue depth.
- The consumer may commit offsets before business tasks finish if acknowledgment design is flawed.
- Rebalances can occur while workers are still processing.
- Duplicate side effects can happen.

Fetch sizing must account for the **in-flight work queue**, not just listener return latency. Bound queues, use bounded executors, and design acknowledgments properly.

## 30. Backpressure and Fetch Sizing

When downstream slows down, reducing fetch/poll batches can dampen bursts, yet does not replace end-to-end backpressure.

A system can combine:
- Smaller `max.poll.records` to limit records per poll.
- Lower `fetch.min.bytes` to avoid waiting on batching if latency matters.
- Container pause/resume when queues cross high/low watermarks.
- Bounded worker pools.
- Rate limiting at dependency boundaries.
- Appropriate concurrency.
- Lag alerts and pause duration monitoring.

~~~text
Queue depth >= HIGH
       |
       v
pause consumer
       |
       v
downstream drains queue
       |
       v
Queue depth <= LOW
       |
       v
resume consumer
~~~

Do not use `fetch.max.bytes` as a rate limiter. Fetch limits control fetch payload size, not guaranteed records/second rates.

## 31. Sizing by Throughput Target

A quantitative workflow:
1. Define the target throughput in records/second.
2. Measure average and p99 compressed batch/record sizes.
3. Measure processing time per record and per batch.
4. Determine partitions and consumer concurrency.
5. Determine the memory budget per pod.
6. Choose `max.poll.records` according to the poll processing budget.
7. Choose `max.partition.fetch.bytes` according to record batch size and per-partition bursts.
8. Choose `fetch.max.bytes` according to aggregate response and memory budgets.
9. Choose `fetch.min.bytes`/`fetch.max.wait.ms` according to latency targets.
10. Load test at peak and burst traffic.
11. Measure GC, lag, fetch latency, and broker throttling.
12. Adjust one group of settings at a time and compare.

Do not change all settings simultaneously, or it becomes hard to identify which factor changed throughput/latency.

## 32. Sizing Example for a Latency-Sensitive Service

Suppose:
- Each record is small, averaging 2 KiB compressed.
- Peak 500 records/s.
- Listener requires fast response.
- Concurrency 4.
- Processing p99 15 ms/record.

A test configuration could be:
~~~yaml
spring:
  kafka:
    consumer:
      properties:
        "[fetch.min.bytes]": 1
        "[fetch.max.wait.ms]": 50
        "[max.partition.fetch.bytes]": 1048576
        "[fetch.max.bytes]": 8388608
        "[max.poll.records]": 100
        "[max.poll.interval.ms]": 300000
~~~

Rationale:
- Low `fetch.min.bytes` avoids waiting for large batches.
- Low `fetch.max.wait.ms` caps fetch wait on low-traffic topics.
- Partition fetch limit at 1 MiB for small records.
- 8 MiB fetch response cap as a starting point to test.
- `max.poll.records` 100 limits the processing batch per poll.

This is only a **starting point**, not a universal best practice. Benchmark and tune based on partitions, broker response size, and memory.

## 33. Sizing Example for a Throughput-Oriented Worker

Suppose:
- Average record 4 KiB compressed.
- High, steady traffic.
- Efficient batch database writes.
- Consumer has heap headroom.
- Target latency allows a bit of batching delay.

A test configuration:
~~~yaml
spring:
  kafka:
    consumer:
      properties:
        "[fetch.min.bytes]": 131072
        "[fetch.max.wait.ms]": 100
        "[max.partition.fetch.bytes]": 4194304
        "[fetch.max.bytes]": 33554432
        "[max.poll.records]": 400
        "[max.poll.interval.ms]": 300000
~~~

More records can be grouped per response and poll. Still, verify:
- Batch listener finishes within the poll budget.
- Heap does not grow excessively.
- Brokers are not throttled.
- Consumer lag drops rather than merely creating bursts.
- The error handler does not retry an overly large batch.
- The downstream DB has corresponding capacity.

If listener p99 processing takes too long, lower `max.poll.records` or intentionally raise the poll interval while checking side effects/rebalances.

## 34. Sizing Example for Large Records

Suppose some records have a batch size of 3 MiB compressed and 15 MiB decompressed.

You need to:
- Verify the producer and broker permit this batch.
- Set `max.partition.fetch.bytes` appropriately for normal batch sizes.
- Set `fetch.max.bytes` large enough for multiple partitions if responses need data from multiple partitions.
- Check the first-batch exception that can exceed fetch limits.
- Measure decompressed heap size and deserialized object graphs.
- Check HTTP/database limits when payloads are forwarded.

A consumer can read a large batch yet OOM after deserialization. Successful fetch sizing at the network layer does not prove heap is large enough.

## 35. Observing Fetch Metrics

Useful Kafka consumer metrics may include:
- `fetch-rate`.
- `fetch-size-avg` / `fetch-size-max`.
- `records-per-request-avg`.
- `bytes-consumed-rate`.
- `records-consumed-rate`.
- `fetch-latency-avg` / `max`.
- `records-lag` / `records-lag-max`.
- partition assignment.
- request latency/throttle time.
- `poll-idle-ratio` or poll-related metrics depending on client version.

Exact metric names depend on the Kafka client version, JMX/Micrometer binder, and exporter naming conventions.

Questions to ask when reading them:
- Is small fetch size caused by `fetch.min.bytes` being too low?
- Is high fetch latency caused by `fetch.max.wait.ms`?
- Is low records per request due to low topic traffic or partition distribution?
- Are bytes consumed rising without listener throughput rising due to a downstream bottleneck?
- Is lag rising despite large fetch responses because the listener processes slowly?
- Is rising throttle time caused by broker quotas?

Never tune based on a single metric in isolation.

## 36. Reading Fetch Size and Latency Together

A few interpretation patterns:

| Observation | Possible Cause | Investigation Direction |
|---|---|---|
| Small fetch size, high fetch rate | Sparse traffic or low min bytes | Review latency targets and `fetch.min.bytes` |
| Fetch latency near `fetch.max.wait.ms` | Broker frequently waits for min bytes | Review min bytes and traffic profile |
| Large fetch size, rising GC | Large batches/decompression/object graphs | Reduce batch size or memory pressure |
| Rising consumer lag, low fetch rate | Consumer unable to fetch or assignment/network issue | Check broker, group, errors |
| High fetch rate, low records/request | Many small fetches | Check min bytes, partitions, and traffic |
| High bytes consumed, low processing throughput | Listener/downstream bottleneck | Inspect DB/API latency and queues |
| Rising broker throttle | Quotas or broker capacity | Inspect quota/broker metrics |

These are diagnostic hypotheses, not guaranteed one-to-one mappings.

## 37. fetch.max.bytes Is Not a Memory Limit

A common sizing mistake is setting:
~~~text
fetch.max.bytes = 32 MiB
JVM heap = 64 MiB
~~~

and expecting the consumer to never hold more than 32 MiB.

That is wrong because:
- There may be multiple fetch requests/consumer buffers.
- Multiple consumers may run in one pod.
- The broker can return a first batch larger than the limit to ensure progress.
- Compression makes decompressed data larger than wire size.
- Deserialized objects carry overhead.
- Listeners and executors hold references.
- Frameworks/GC require headroom.

Use heap profiling/load testing to determine memory footprint. Fetch limits are only part of the budget.

## 38. When to Increase fetch.max.bytes?

Consider increasing when:
- Fetch responses are frequently capped at `fetch.max.bytes`.
- Many partitions have backlogs simultaneously.
- Consumer network round trips are the bottleneck.
- Heap has headroom.
- Brokers/network have capacity.
- Poll processing time remains within budget.

Avoid increasing when:
- The consumer is bottlenecked on DB/API.
- GC is already high.
- Pod memory is near its limit.
- The listener is exceeding `max.poll.interval.ms`.
- Brokers are throttling or overloaded.
- Partition skew is the primary cause.

Raising `fetch.max.bytes` when downstream is slow can grow queues/buffers without increasing business throughput.

## 39. When to Decrease max.poll.records?

Consider decreasing when:
- The listener processes sequentially and batch callbacks take too long.
- Consumers frequently exceed `max.poll.interval.ms`.
- A single poll creates too large a burst on the database.
- Retrying a batch is expensive.
- Memory per poll is high.
- You want more frequent polls to maintain group progress.

Yet if lowered too much:
- Per-poll overhead rises.
- Database bulk operations become less efficient.
- Throughput drops.
- Consumers may underutilize network fetch buffers.

Choose based on p99 processing time and throughput, not just averages.

## 40. When to Increase max.partition.fetch.bytes?

Consider increasing when:
- Normal record batches approach or exceed the current limit.
- The consumer needs to read valid large batches.
- One partition experiences large bursts and responses are capped.
- Heap and downstream have sufficient capacity.

Do not increase if:
- Record sizes are small.
- The bottleneck is in the listener/DB.
- A hot partition is causing memory pressure.
- You are trying to work around message sizes violating broker/topic policy.

For large records, coordinate producer `max.request.size`, broker/topic message size, and consumer limits. Do not change only the consumer setting.

## 41. fetch.min.bytes and Latency SLOs

If event-to-processing p99 must stay under 100 ms, setting `fetch.max.wait.ms = 500 ms` may not suit low-traffic flows. Yet end-to-end p99 also includes:
- Producer linger/batch wait.
- Broker append/replication.
- Fetch wait.
- Consumer poll scheduling.
- Listener processing.
- Database/API.
- Commit/transaction.
- Queuing.

You cannot assume `fetch.max.wait.ms` equals the p99 SLO; it is only one slice of the latency budget.

A latency budget:
~~~text
End-to-end latency
  = producer delay
  + broker delay
  + fetch wait
  + listener queue/process
  + downstream
  + commit/transaction
~~~

Optimizing fetch wait when listener processing accounts for 95% of latency will not make a major difference.

## 42. Backoff, Retries, and Fetch Sizing

Blocking retries can prevent the consumer from advancing normal polls during backoff or hold up partition processing. A single poison record can raise lag even with large fetch settings.

Retry topics move records to retry topics, allowing the source listener to continue with other records according to the topology. However, retry topic consumers also have their own fetch settings.

Size separately for:
- Main consumer group.
- Retry topic consumers.
- DLT consumers.
- Replay/rebuild consumers.

Do not assume a single `ConsumerFactory` configuration is optimal for all of them. Retry topics often have different burst traffic than the main topic; DLTs may have low traffic yet large records needing investigation.

## 43. Fetch Sizing When Using Multiple Clusters

A service may consume from multiple Kafka clusters. Each `ConsumerFactory` may have:
- Its own bootstrap servers.
- Its own security config.
- Its own fetch limits.
- Its own concurrency.
- Its own topic/partition profile.

Do not share one `ConsumerFactory` or `AdminClient` across clusters if configs/security/metric scopes differ.

A high-throughput analytics cluster may use large fetch batching, whereas a latency-sensitive command cluster uses low `fetch.min.bytes` and short `fetch.max.wait.ms`.

## 44. Sizing and Autoscaling

When scaling consumer replicas:
- Partitions are rebalanced across instances.
- Consumer count rises.
- Total fetch requests may rise.
- Total memory buffers rise.
- Broker connection count rises.
- Per-consumer assigned partitions may drop.
- Throughput may rise until downstream/broker/partition limits hit a ceiling.

If consumers outnumber partitions, some consumers may receive no partitions. Scaling replicas beyond partition count does not automatically increase throughput.

Lag-based autoscaling must consider:
- Lag per partition and lag age.
- Processing throughput.
- Consumer concurrency.
- Downstream capacity.
- Broker quotas.
- Fetch response sizes.
- Memory/CPU headroom.

Do not scale consumer replicas solely based on CPU if the bottleneck is fetch/network or the downstream database.

## 45. Fetch Sizing and Broker-Side Load

Fetch requests have costs on the broker:
- Request parsing/dispatch.
- Partition log reads.
- Network responses.
- Page cache/disk activity depending on workload.
- Quota accounting.
- Request queuing.

Many consumer instances with very low `fetch.max.wait.ms` and small `fetch.min.bytes` can generate many fetch requests. Conversely, large fetch responses can cause network egress spikes.

Consumer optimization must not overload brokers. Load tests must observe both consumers and brokers.

## 46. Consumer Fetch and Rack Awareness

In Kafka deployments with rack-aware replica selection, consumers can prefer nearby replicas to reduce network costs depending on client/broker settings and version support.

Fetch sizing still applies to consumer requests; rack awareness influences which broker/replica is selected rather than replacing fetch limits.

When deploying across multiple zones/availability zones:
- Measure cross-zone/network egress.
- Inspect rack metadata and replica placement.
- Measure latency when fetching from nearby replicas.
- Do not assume increasing `fetch.max.bytes` will solve cross-zone latency.
- Ensure consistency/isolation semantics match Kafka configuration.

## 47. Step-by-Step Tuning Workflow

Change one group of settings at a time in sequence:

1. **Baseline**: measure fetch size, fetch latency, records/request, bytes/sec, lag, processing duration, GC, and memory.
2. **Poll budget**: choose `max.poll.records` based on p99 processing time and `max.poll.interval.ms`.
3. **Partition fetch**: check p99 batch size and set `max.partition.fetch.bytes` sufficient for normal workloads.
4. **Request fetch cap**: set `fetch.max.bytes` based on partition count, response size, and memory budget.
5. **Batch wait**: tune `fetch.min.bytes`/`fetch.max.wait.ms` to match latency/throughput targets.
6. **Concurrency**: check total consumers, partition distribution, and per-pod memory.
7. **Network**: check receive buffers, broker quotas, fetch request rates, and throttling.
8. **Stress test**: peak traffic, bursts, large records, downstream slowdowns, and broker recovery.
9. **Canary rollout**: apply to a subset of consumers first.
10. **Compare**: compare throughput, p99 latency, GC, lag, and broker load before and after.
11. **Document**: record workload assumptions and the rationale behind each value.
12. **Revisit**: re-size whenever record size, partition count, or concurrency changes.

There is no benefit in just bumping a number without knowing which metric needs to improve.

## 48. Reference Workload Matrix

| Workload | fetch.min.bytes | fetch.max.wait.ms | max.poll.records | Priority |
|---|---|---|---|---|
| Command latency-sensitive | Low | Low | Moderate/small | Minimize wait and poll duration |
| High-throughput event stream | Moderate/large | Moderate | Moderate/large if processing is fast | Batching and network efficiency |
| Large record processing | Per traffic | Per latency | Low/moderate | Memory and record batch size |
| Batch DB writer | Moderate | Moderate | Large if batch callback is fast | Bulk throughput |
| Retry/DLT consumer | Per retry traffic | Per processing need | Moderate | Recovery reliability |
| Sparse topic | Low | Low/moderate | Not critical | Avoid waiting long for min bytes |

This table is a qualitative starting point. There are no universal byte/millisecond values for every workload.

## 49. Common Configuration Errors

| Symptom | Possible Cause | Remediation |
|---|---|---|
| High latency on low-traffic topic | Large `fetch.min.bytes` and long `fetch.max.wait.ms` | Lower min bytes or max wait |
| Many small fetch requests | Low min bytes, sparse traffic, or many low-volume partitions | Measure fetch rate and latency before raising min bytes |
| Consumer OOM | Large responses/batches, high concurrency, decompression/object overhead | Dampen bursts, bound queues, profile heap |
| Consumer lag grows despite large fetch size | Listener/downstream bottleneck | Measure processing latency and queues |
| Rebalance due to poll timeout | Large `max.poll.records` or slow listener processing | Reduce poll batch, optimize processing, review `max.poll.interval` |
| Large record batches processed unstably | Partition fetch sizing and message limits out of sync | Check batch sizes and consumer/broker limits |
| Throughput flat when raising `fetch.max.bytes` | Broker quota, hot partition, downstream bottleneck | Inspect broker/client metrics |
| Broker egress spikes | Large fetch responses or many consumers | Measure total consumers and response rates |
| GC rises after increasing concurrency | More buffers and object graphs | Lower concurrency/batch or increase capacity |
| Batch retries take too long | Large `max.poll.records` with one failing record | Adjust batch/error handling semantics |

These are diagnostic hypotheses; confirm the actual root cause using metrics and logs.

## 50. Testing Fetch Sizing with a Kafka Broker

Use a real Kafka broker in integration tests, such as **Testcontainers Kafka** or EmbeddedKafka appropriate for your dependency version.

### Test 1: Fetch Batching Under Steady Traffic

1. Create a multi-partition topic.
2. Configure `fetch.min.bytes` and `fetch.max.wait.ms`.
3. Produce records at a steady rate.
4. Measure fetch size/records per request and end-to-end latency.
5. Compare against a smaller `fetch.min.bytes`.
6. Confirm throughput and p95/p99 latency shift as expected.

### Test 2: Low-Traffic Latency

1. Send one record per long interval.
2. Set `fetch.min.bytes` larger than record size.
3. Set a known `fetch.max.wait.ms`.
4. Measure record delivery latency.
5. Lower `fetch.max.wait.ms`.
6. Compare latency rather than looking only at consumer lag.

### Test 3: max.poll.records

1. Produce a large volume of records.
2. Run record listeners and batch listeners with different `max.poll.records` settings.
3. Measure records per poll/callback.
4. Measure poll processing time and memory.
5. Confirm `max.poll.interval.ms` is not exceeded.
6. Verify offset/ack semantics on batch failures.

### Test 4: Large Record Batches

1. Produce record batches near configured limits.
2. Test `max.partition.fetch.bytes` smaller than batch size.
3. Verify first-batch behavior and consumer progress for your Kafka client/broker version.
4. Inspect heap after decompression/deserialization.
5. Confirm no OOM and no retry loop.

### Test 5: Concurrency and Memory

1. Run multiple listener consumers.
2. Increase concurrency step by step.
3. Measure heap, GC, network connections, and fetch throughput.
4. Confirm total pod memory stays within budget.
5. Confirm consumer group assignment does not leave excessive idle consumers.

### Test 6: Downstream Slowdown

1. Slow down the database in a controlled manner.
2. Measure poll processing duration and lag.
3. Try lowering `max.poll.records`.
4. Test bounded queues/pause-resume if using async processing.
5. Confirm consumers do not rebalance unexpectedly.
6. Verify duplicates/idempotency during retries.

### Test 7: Broker Throttling

1. Apply test quotas if the environment supports them.
2. Measure throttle time and fetch rate.
3. Try adjusting fetch sizing.
4. Confirm quota bottlenecks are not mistaken for fetch size bottlenecks.
5. Restore quotas and compare.

Tests should have timeouts, metric collection, and repeatable workloads. A single benchmark run does not represent every production traffic profile.

## 51. Reading Benchmark Results

When comparing two configurations, record:
- Throughput in records/sec.
- Throughput in bytes/sec.
- End-to-end latency p50/p95/p99.
- Fetch size avg/max.
- Fetch latency avg/max.
- Records per request.
- Max consumer lag and lag age.
- Listener processing duration.
- Poll interval distribution.
- Heap usage and GC pauses.
- Broker request rate, network egress, and throttling.
- Rebalance count.
- Error/retry/DLT rates.

Example table:
| Metric | Config A | Config B |
|---|---:|---:|
| Throughput | 8,000 rec/s | 9,500 rec/s |
| p99 latency | 90 ms | 145 ms |
| Max lag | 12,000 | 8,000 |
| Heap peak | 1.2 GiB | 1.8 GiB |
| Rebalances | 0 | 2 |

These numbers merely illustrate how to compare. Config B increases throughput and lowers lag, yet latency and heap rise; the choice must rest on SLOs and capacity budgets rather than a single metric.

## 52. Checklist When a Consumer Is Slow

When consumer lag increases:
1. Confirm the consumer holds valid assignments.
2. Check fetch request rate and fetch latency.
3. Check fetch size avg/max and records per request.
4. Check `bytes-consumed-rate` and `records-consumed-rate`.
5. Measure listener processing p95/p99.
6. Check `max.poll.records` and `max.poll.interval`.
7. Check DB/API latency, executor queues, and pause state.
8. Check broker throttling and network throughput.
9. Check partition skew/hot keys.
10. Check compression and deserialization CPU.
11. Check rebalance/retry/DLT events.
12. Only modify fetch settings when data shows the fetch path is the bottleneck.

Consumer lag equals producer rate minus consumer processing/commit progress; raising fetch limits does not guarantee lag drops if the listener cannot process faster.

## 53. Common Misconceptions

**`fetch.max.bytes` is a hard consumer memory limit.** False. Multiple requests, consumers, decompression, and object overhead can push memory higher.

**`max.partition.fetch.bytes` smaller than a record batch means the record can never be read.** False in general; Kafka has a first-batch exception so consumers make progress.

**`max.poll.records` controls fetch bytes from the broker.** False. It caps the number of records returned from a single poll.

**Increasing `max.poll.records` always increases throughput.** False. The listener may process longer, raise memory usage, and exceed the poll interval.

**Large `fetch.min.bytes` is always better because responses are larger.** False. Low-traffic topics can suffer higher latency while the broker waits for data.

**`fetch.max.wait.ms` is listener processing time.** False. It is the time the broker waits to meet `fetch.min.bytes`.

**The Spring container's `pollTimeout` is `fetch.max.wait.ms`.** False. They operate at two different layers.

**`fetch.max.bytes` and `max.partition.fetch.bytes` are the same.** False. One applies to the overall fetch request, the other per partition.

**Increasing fetch limits solves hot partitions.** False. Partition skew usually requires reviewing key distribution and partitioning.

**Increasing concurrency always increases throughput.** False if partitions are insufficient or downstream is already saturated.

**A `read_committed` consumer having no data is due to small fetch size.** Not necessarily. The consumer may be waiting for a transaction to finish / Last Stable Offset.

**`receive.buffer.bytes` replaces `fetch.max.bytes`.** False. One relates to the TCP socket buffer, the other to Kafka fetch response sizing.

**Broker `replica.fetch.max.bytes` controls the Spring consumer.** False. It serves broker replication fetches.

**Increasing `request.timeout.ms` fixes slow listener callbacks.** False. Listener processing time requires reviewing the poll interval and application design.

## 54. Production Rollout Workflow

When tuning consumer fetch sizing in Spring Kafka:

1. Measure the real workload: record size, batch size, traffic rate, compression ratio, and partition skew.
2. Define latency SLOs, throughput targets, and pod memory budgets.
3. Choose `max.poll.records` based on p99 processing time and `max.poll.interval.ms`.
4. Choose `max.partition.fetch.bytes` based on record batch sizes and per-partition bursts.
5. Choose `fetch.max.bytes` based on expected total responses and assigned partition counts.
6. Choose `fetch.min.bytes`/`fetch.max.wait.ms` based on the batching-versus-latency trade-off.
7. Align producer/broker/topic message size limits with consumer fetch limits.
8. Calculate total resources by consumer/concurrency count per pod.
9. Measure post-decompression and post-deserialization memory, not just bytes on the wire.
10. Check broker quotas, fetch request rates, network egress, and throttling.
11. Do not use fetch sizing in place of backpressure, bounded queues, or downstream rate limits.
12. Test record listeners, batch listeners, retry topics, and DLT consumers separately.
13. Load test high traffic, sparse traffic, bursts, large records, and downstream slowdowns.
14. Canary roll out one change at a time and compare throughput, latency, lag, GC, and broker load.
15. Document assumptions, versions, configuration values, and rationale to inform future tuning.

**Consumer fetch sizing** is a balancing problem across the volume of data the broker returns, the number of records the listener receives per poll, processing time, and memory held by each consumer. `fetch.min.bytes`/`fetch.max.wait.ms` govern batching and wait time; `max.partition.fetch.bytes`/`fetch.max.bytes` bound fetch size per partition and per request; `max.poll.records` governs how many records are returned to the application. A sound configuration must match record size, partition distribution, concurrency, compression, downstream capacity, and `max.poll.interval.ms`. Measure the entire path from broker to listener and business side effects, then validate each group of settings one change at a time.
