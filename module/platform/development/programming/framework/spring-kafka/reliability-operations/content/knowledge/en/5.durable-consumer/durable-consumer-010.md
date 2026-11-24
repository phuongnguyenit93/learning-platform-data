# max.partition.fetch.bytes

`max.partition.fetch.bytes` is the Kafka consumer configuration that determines the maximum amount of data the broker is asked to return **per partition in a single fetch response**. This is an important parameter when operating consumers with large payloads, many partitions, or high throughput. It affects fetch sizes, round-trips between consumer and broker, consumer memory buffers, and the ability to handle large record batches.

In Spring Kafka, this remains a configuration of the underlying Kafka Java Consumer. Spring Kafka and Spring Boot pass the value down to the consumer; the listener container does not alter this parameter's meaning.

## 1. What Does This Parameter Control?

Kafka stores records in record batches. When a consumer calls `poll()`, the Kafka client sends a Fetch request to brokers to pull data from partitions owned by that consumer. The broker returns data in batches.

`max.partition.fetch.bytes` caps the data a broker returns for a single partition in one fetch. The Kafka consumer default is **1 MiB**. For example, if configured to 4 MiB, the consumer allows the broker to return up to roughly 4 MiB of data per partition in a fetch response, subject to available data and the overall fetch request limit.

This parameter bounds the fetch operation. It does not set the maximum size a producer may send, does not determine how many records a single `poll()` returns, and is not a hard cap on the consumer's entire JVM heap.

### 1.1. Per-Partition Limit

Suppose a consumer is assigned three partitions: `orders-0`, `orders-1`, and `orders-2`. With `max.partition.fetch.bytes = 4 MiB`, each partition has its own fetch cap inside a request. If available data is smaller than the limit, the broker returns only what is available. When multiple partitions have data, the total response is also constrained by `fetch.max.bytes`.

Illustrative example assuming every partition has plenty of data and total fetch stays below the global cap:

| Partition | Per-Partition Limit |
|---|---:|
| `orders-0` | 4 MiB |
| `orders-1` | 4 MiB |
| `orders-2` | 4 MiB |

The 4 MiB limit applies individually to each partition; total response size also depends on `fetch.max.bytes` and actual available data.

Do not assume the consumer will always receive exactly 12 MiB in this example. Brokers may return less because partitions lack enough data, the fetch request hits `fetch.max.bytes`, or partitions reside on different brokers and are fetched in separate requests.

### 1.2. Large Record Batch Exception to Ensure Progress

Kafka has an important exception: if the first record batch in the first non-empty partition of a fetch exceeds the configured limit, that batch can still be returned so the consumer continues making progress. Thus, `max.partition.fetch.bytes` is not an absolute hard cap on received data size.

This mechanism prevents a consumer from getting stuck unable to read the next batch merely because the batch exceeds the fetch limit. However, never rely on this exception as a configuration strategy. Set a limit matching the largest batch the application expects to handle and account for the possibility of a batch exceeding the configured threshold.

## 2. Distinguishing from Other Fetch and Poll Configurations

Kafka consumer properties related to fetching and polling operate at different scopes. Confusing them easily leads to ineffective tuning or misjudging memory consumption.

| Property | Control Scope | Primary Meaning |
|---|---|---|
| `max.partition.fetch.bytes` | Per partition in a fetch | Limits data returned for one partition |
| `fetch.max.bytes` | Total data in one fetch response | Caps total data a broker returns for a single fetch request |
| `max.poll.records` | Per `poll()` call | Caps number of records returned to the application |
| `fetch.min.bytes` | Fetch response | Minimum data the consumer wants before the broker responds |
| `fetch.max.wait.ms` | Fetch wait duration | Maximum time the broker waits to satisfy `fetch.min.bytes` |
| `max.poll.interval.ms` | Interval between polls | Maximum time between `poll()` calls before the consumer may be considered inactive in the group |

### 2.1. max.partition.fetch.bytes and fetch.max.bytes

These two parameters complement each other:

- `max.partition.fetch.bytes` limits data per partition.
- `fetch.max.bytes` limits total data returned by the broker for a single fetch request.

The common default for `fetch.max.bytes` is 50 MiB. If a consumer reads many partitions, this total limit may be reached before every partition consumes its individual allowance. Conversely, a partition with a large record batch may need more than its normal per-partition limit; the first-batch exception can still apply to preserve progress.

A single consumer can fetch data from multiple brokers. The Kafka client can issue fetch requests in parallel, so do not treat `fetch.max.bytes` as a total memory cap for the entire consumer process.

### 2.2. max.partition.fetch.bytes and max.poll.records

`max.poll.records` caps how many records a single `poll()` returns to the application. It does not directly limit bytes fetched from the broker and does not alter how the client fetches data in the background.

For example, a poll returning 500 tiny records may consume less memory than a poll returning 50 records with large payloads. Lowering `max.poll.records` is therefore no substitute for configuring fetch bytes when large batches or payloads are the main issue.

If the listener takes long to process records, examine `max.poll.interval.ms`, concurrency, and batch handling as well. Raising or lowering `max.partition.fetch.bytes` does not by itself fix a consumer failing to call `poll()` frequently enough.

### 2.3. fetch.min.bytes and fetch.max.wait.ms

`fetch.min.bytes` tells the broker the minimum amount of data the consumer prefers before returning a fetch response when waiting is possible. `fetch.max.wait.ms` bounds how long the broker waits for that condition.

Raising `fetch.min.bytes` can accumulate more data in one response and improve throughput efficiency on steady-traffic workloads, though it can raise latency during low traffic. These two parameters tune time-based accumulation; `max.partition.fetch.bytes` caps maximum data per partition.

## 3. Relationship to Message Size and Broker Configuration

Consumers can only read record batches that producers successfully wrote to Kafka. Broker/topic batch acceptance limits and consumer fetch limits are two separate stages.

Distinguish these configurations:

- Producer `max.request.size`: caps request size sent by the producer.
- Broker `message.max.bytes`: caps record batch size accepted by the broker.
- Topic `max.message.bytes`: caps record batch size accepted for the topic.
- Consumer `max.partition.fetch.bytes`: caps data the broker returns per partition in a fetch.

When an application must support large payloads, evaluate the entire path from producer through broker to consumer. Raising `max.partition.fetch.bytes` alone will not let a producer send a batch the broker rejects. Likewise, raising broker limits does not guarantee consumers have enough memory or can process large batches in time.

Compression must also be factored in. Kafka transmits and stores records in batches; wire size can differ from decompressed payload size. Measure real batches in workloads using production-like compression settings rather than relying solely on application JSON or object sizes.

## 4. Configuration in Raw Kafka Client

You can configure via property keys:

```java
Properties props = new Properties();

props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
          "kafka-1:9092,kafka-2:9092");
props.put(ConsumerConfig.GROUP_ID_CONFIG, "orders-service");
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
          StringDeserializer.class);
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
          ByteArrayDeserializer.class);

// Allow up to ~4 MiB of data per partition in a fetch.
props.put(ConsumerConfig.MAX_PARTITION_FETCH_BYTES_CONFIG,
          4 * 1024 * 1024);

// Cap total data of a single fetch response.
props.put(ConsumerConfig.FETCH_MAX_BYTES_CONFIG,
          50 * 1024 * 1024);

try (KafkaConsumer<String, byte[]> consumer =
         new KafkaConsumer<>(props)) {
    consumer.subscribe(List.of("orders"));
    while (!Thread.currentThread().isInterrupted()) {
        ConsumerRecords<String, byte[]> records =
            consumer.poll(Duration.ofMillis(500));

        for (ConsumerRecord<String, byte[]> record : records) {
            process(record);
        }
    }
}
```

This is an illustrative configuration example. Production applications need proper error handling, shutdown/wakeup, offset commits, and record processing policies. Byte properties are specified in bytes, so 4 MiB corresponds to `4 * 1024 * 1024`, not a record count.

When using `Map<String, Object>` to create `DefaultKafkaConsumerFactory`, place the same `ConsumerConfig.MAX_PARTITION_FETCH_BYTES_CONFIG` key in the consumer configuration map. Spring Kafka passes this property down to the Kafka Java Consumer.

## 5. Configuration in Spring Boot and Spring Kafka

With Spring Boot, declare it directly in `application.yml`:

```yaml
spring:
  kafka:
    consumer:
      bootstrap-servers: kafka-1:9092,kafka-2:9092
      group-id: orders-service
      max-partition-fetch-bytes: 4194304
      properties:
        "[fetch.max.bytes]": 52428800
```

In this example:

- `max-partition-fetch-bytes: 4194304` equals 4 MiB per partition.
- `fetch.max.bytes: 52428800` equals 50 MiB for the total fetch response.

Spring Boot maps `max-partition-fetch-bytes` to the corresponding consumer property. If the application declares its own `ConsumerFactory` or supplies a custom configuration map, ensure the desired values are included in the factory actually used by the listener container.

With listener concurrency, each consumer instance has its own fetch configuration and receives a share of the group's partitions. Example:

```java
@KafkaListener(
    topics = "orders",
    groupId = "orders-service",
    concurrency = "3"
)
public void consume(OrderEvent event) {
    orderService.handle(event);
}
```

Concurrency of 3 means the container runs three consumer instances for this listener. It does not turn `max.partition.fetch.bytes` into an aggregate limit for the whole listener. When sizing memory, account for consumer instance count, partitions assigned per consumer, brokers being fetched from, and actual batch sizes.

## 6. How to Choose the Right Value

No single value is optimal for every system. The right value depends on record batch size, partitions assigned per consumer, consumer instance count, throughput, target latency, and available memory.

### Step 1: Determine the Largest Batch Size

Measure actual batch sizes producers emit under production conditions. Consider:

- The largest payload allowed by business rules.
- Number of records in a producer batch.
- Compression codec and compression ratio.
- Producer `max.request.size` limit.
- Broker `message.max.bytes` and topic `max.message.bytes` limits.

Distinguish single-record size from record-batch size. Consumers fetch by batch, so a batch containing many records can be larger than an individual record.

### Step 2: Set the Partition Limit High Enough for Expected Batches

Set `max.partition.fetch.bytes` so normal and valid large batches can be fetched efficiently. If the application routinely emits multi-megabyte batches while consumers configure a tiny limit, the client may have to make extra fetch round-trips or rely on the first-batch exception to keep reading.

Do not set a huge value without measurement data. A large limit increases how much data a consumer can pull and buffer in memory, especially when owning many partitions.

### Step 3: Check the Total Fetch Limit

Compare `fetch.max.bytes` against the number of simultaneously active partitions and target throughput. If the total limit is too small for the data needed across multiple partitions, it can become a bottleneck even when per-partition limits are ample.

Remember that Kafka can fetch from multiple brokers in parallel. Therefore, you cannot calculate peak heap usage simply by multiplying `fetch.max.bytes` by a single fixed constant.

### Step 4: Factor in Concurrency and Partition Count

In Spring Kafka, concurrency spawns multiple consumer instances. Each instance has its own fetch buffers and partition assignments. Increasing concurrency can increase total memory consumption and fetch requests across the application.

For instance, a service with 24 partitions and concurrency 6 runs up to six consumer instances in that listener container; each consumer receives partitions per group assignment. Raising `max.partition.fetch.bytes` to 8 MiB does not mean the entire listener's heap footprint is bounded at 8 MiB. Test the full container with large payloads and realistic traffic.

### Step 5: Measure and Tune

Adjust configuration groups systematically. Monitor indicators such as:

- Average and peak fetch sizes.
- Average and peak fetch latencies.
- Bytes consumed rate and records consumed rate.
- Consumer lag per partition.
- Heap usage, allocation rate, and GC pauses.
- Listener processing duration and intervals between polls.

If fetch sizes consistently hit the cap while lag persists, inspect batch sizes, total fetch cap, partition count, broker throughput, and processing speed. If raising the limit spikes heap usage or GC, consider smaller batches, fewer partitions per consumer, adjusted concurrency, or scaling resources appropriately.

## 7. Impact on Reliability and Operations

### 7.1. Values Too Low

A low limit can shrink how much data each fetch pulls and increase round-trips when the consumer needs to drain heavy traffic. Kafka allows the first batch to exceed the limit when needed to preserve consumer progress, so a low value cannot serve as an absolute blocker against large batches.

However, relying on that exception makes memory consumption and response sizes unpredictable. If your workload legitimately produces large batches, configure an appropriate limit and test with real batches.

### 7.2. Values Too High

A high limit allows consumers to receive more data in a single fetch. Across many partitions and consumer instances, queued data awaiting processing can swell, bringing heap pressure, GC overhead, and risk to other components in the process.

A high value does not automatically boost throughput. If the listener processes slowly, the database is a bottleneck, or brokers lack headroom, large fetches merely pile more unconsumed data into memory.

### 7.3. Do Not Use This Parameter to Fix Producer or Broker Errors

If producers hit record/batch-too-large errors when sending, inspect `max.request.size`, `message.max.bytes`, and `max.message.bytes`. Raising `max.partition.fetch.bytes` on the consumer does not change broker write-acceptance rules.

If the consumer fails to read due to deserialization errors, invalid payloads, or listener exceptions, raising fetch limits will not resolve the root cause either. Separate write errors, fetch errors, deserialization errors, and business processing errors.

### 7.4. Coordinating with Processing Policy and Offset Commits

Fetch size only controls how data arrives at the consumer. It does not determine offset commit timing or delivery semantics. In Spring Kafka, choose an appropriate AckMode and error handler; with raw Kafka clients, define sync/async commits clearly and commit offsets only after successful processing.

If a listener processes large batches or many records per poll, processing time can grow. Check `max.poll.interval.ms` and structure processing so consumers keep calling `poll()` within bounds. Setting large fetch byte caps without accounting for processing duration increases the risk of consumer group eviction during long processing cycles.

## 8. Diagnosing Fetch-Size-Related Incidents

| Symptom | What to Check |
|---|---|
| Consumer lag climbs when large payloads appear | Batch size, fetch size, broker throughput, and listener processing duration |
| Large fetch sizes, rising heap, or long GC | Assigned partitions, concurrency, fetch.max.bytes, and processing speed |
| Consumer reads slowly despite high fetch limits | Broker/network throughput, partition count, deserialization, downstream, and listener latency |
| Producer reports batch/request too large | Producer max.request.size and broker/topic message size limits |
| Listener rebalances while processing a batch | Processing duration between polls, max.poll.interval.ms, and max.poll.records |
| High lag on only one partition | Key distribution, batch sizes, anomalous data, and processing speed on that partition |

When investigating, inspect effective consumer configuration after Spring Boot binding and custom factories finish initializing. A setting in YAML is not guaranteed to be active at runtime if custom configuration overrides it.

A useful investigation workflow:

1. Identify the consumer group, listener container, and consumer instance experiencing lag.
2. Check which partitions lag and whether those partitions hold unusually large record batches.
3. Inspect runtime consumer settings, especially `max.partition.fetch.bytes`, `fetch.max.bytes`, `max.poll.records`, and `max.poll.interval.ms`.
4. Correlate fetch size, fetch latency, bytes consumed rate, heap, and GC over the same time window.
5. Check producer, broker, and topic write limits if errors originate at publish time.
6. Re-test with the largest valid batch and production-like concurrent load before rolling out broad changes.

## 9. Common Configuration Mistakes

**Assuming this is a single-record size limit.** This parameter regulates fetched data per partition, and Kafka transmits records in batches. Inspect actual batch sizes.

**Assuming this is a total memory limit.** A consumer can fetch from multiple brokers, buffer data for multiple partitions, and run alongside other consumer instances. This parameter is not a heap cap.

**Raising max.partition.fetch.bytes while ignoring fetch.max.bytes.** When multiple partitions hold data concurrently, the global fetch cap also constrains returned data.

**Using max.poll.records instead of byte limits.** A record-count cap cannot control byte volume when payload sizes vary widely.

**Increasing concurrency without accounting for memory cost.** Every consumer instance maintains its own fetch activity. Higher concurrency increases fetch requests and buffered data inside the process.

**Changing only the consumer when brokers reject batches.** Oversized write errors must be addressed at the producer and broker/topic. Fetch settings only apply after data is accepted into Kafka.

**Relying on defaults across every environment.** Batch sizes, partition counts, and concurrency can differ between test and production. Test against realistic load and payloads.

## 10. Deployment Checklist

Before changing `max.partition.fetch.bytes`, confirm:

- [ ] Measured or soundly estimated the largest record batch size.
- [ ] Producer and broker/topic permit writing batches of that size.
- [ ] Partition fetch value accommodates expected batches.
- [ ] `fetch.max.bytes` fits data arriving from multiple partitions concurrently.
- [ ] Accounted for partitions per consumer and listener concurrency.
- [ ] Checked heap, GC, and listener processing time under large payloads.
- [ ] Checked `max.poll.records` and `max.poll.interval.ms` if processing duration increases.
- [ ] Tested with largest valid batches, concurrent data across partitions, and production-like load.
- [ ] Dashboards or alerts exist for consumer lag, fetch latency, and memory.

`max.partition.fetch.bytes` is a tuning lever for per-partition fetch sizing. Choose values based on valid batch sizes and the memory budget of the entire consumer deployment, then validate with metrics and load tests. In Spring Kafka, this setting flows down to the Kafka consumer used by the listener container; decisions around commits, retries, error handling, and poll intervals still require dedicated design.

