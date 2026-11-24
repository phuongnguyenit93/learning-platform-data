# Memory When Retaining Records for Retry in Spring Kafka

When a Kafka listener fails to process a record, Spring Kafka can retry that record after a backoff interval. During the wait, the record and its associated objects may remain in the consumer process's heap. With large payloads, multi-record batches, high concurrency, or prolonged retries, retaining this data can occupy substantial memory, lengthen GC pauses, create allocation pressure, and eventually trigger `OutOfMemoryError`.

Therefore, a retry policy is not just the question "how many retries and how long to wait?". It is also a **decision about where to store records while waiting for retry**:

- Retain records in application memory and redeliver them.
- Seek offsets so the Kafka consumer re-fetches records from the broker later.
- Republish records to a retry topic so the broker persists them and another consumer processes them later.
- Place records into a dedicated durable store/outbox/quarantine.

These approaches carry different trade-offs in heap, network, broker storage, latency, ordering, and delivery semantics. This lesson focuses on **memory when retaining records for retry** in Spring Kafka, specifically the behavior of `DefaultErrorHandler`, the `seekAfterError` option, batches/concurrency, backoff, retry topics, and capacity sizing.

The most important point: **serialized record size does not equal the amount of heap a record occupies in the consumer JVM**. After fetching, decompression, deserialization, and conversion into an object graph, a message can consume far more memory than its original byte size. Measure with realistic workloads and cap how many records/batches/in-flight tasks can exist concurrently.

## 1. Where Can a Record Live During a Retry?

A record passes through multiple layers before and during a retry:

~~~text
Kafka broker
   |
   | Fetch response (serialized bytes, possibly compressed)
   v
Kafka consumer fetch buffers
   |
   | poll()
   v
Spring Kafka listener container
   |
   | convert / deserialize / dispatch
   v
Listener receives ConsumerRecord / payload object
   |
   +-- Success --> acknowledgement / offset handling
   |
   +-- Failure --> error handler
                    |
                    +-- Seek offsets; re-fetch after backoff
                    |
                    +-- Retain unprocessed records in memory
                    |
                    +-- Republish to retry topic
                    |
                    +-- Recover to DLT
~~~

Not every retry keeps an independent copy of the entire record. Many components hold a **reference** to the same object or batch. Even so, those references prevent the garbage collector from reclaiming the objects. If the listener creates extra object copies, holds tasks in an executor queue, or stores separate retry state, the memory footprint grows further.

A helpful distinction is:

| Where Data Is Held | Example | Memory Impact |
|---|---|---|
| Kafka client fetcher | Fetched batches not yet fully returned via poll | Consumer heap and buffers |
| Poll result | Records returned from `poll()` | Record set awaiting container processing |
| Listener/container | Current record and remaining records in batch | Holds object references |
| Error handler | Retry/recovery state, records to redeliver | Can extend record lifetimes |
| Deserializer/converter | Object graph, byte arrays, Strings, DTOs | Can be larger than serialized bytes |
| Application executor | Queued or running async tasks | Queue and in-flight objects |
| Kafka producer | Records waiting to send to retry/DLT/output | Producer buffers and serialized data |
| Retry topic/DLT | Records persisted on the broker | Shifts retention to broker; client buffers still exist |

A memory incident usually comes not from a single record, but from **many records coexisting longer than expected**.

## 2. Why Serialized Size Underestimates Heap Usage

Suppose a record has a 200 KB value in Kafka. Inside the consumer JVM, that data may go through several forms:

1. Byte arrays or buffers fetched from the broker.
2. Decompression if the batch/record is compressed.
3. Deserialization into Strings, JSON trees, or Java DTOs.
4. Object graphs containing nested objects, collections, Strings, and boxed primitives.
5. Business transformations allocating additional objects.
6. Retry/error handling holding references to records and payloads.
7. Logging/tracing/conversion potentially creating extra metadata or copies depending on implementation.

A 200 KB JSON payload can expand into a much larger object graph, especially when it has many String fields, maps, lists, and nested DTOs. There is no single fixed multiplier that fits every serializer, JVM, and schema.

### 2.1. Example of Object Amplification

A JSON payload:

~~~json
{
  "orderId": "order-42",
  "customer": {
    "name": "Example Customer",
    "addresses": [
      { "city": "HCMC", "postalCode": "700000" }
    ]
  },
  "items": [
    { "sku": "A-1", "quantity": 2, "price": 10.5 },
    { "sku": "B-2", "quantity": 1, "price": 25.0 }
  ]
}
~~~

Upon deserialization, the JVM allocates many objects: root DTO, customer DTO, address list, address DTO, items list, item DTOs, Strings, and numeric wrappers or primitive fields depending on the model. Every object carries header/alignment/reference overhead. Strings hold backing arrays; collections hold internal arrays and references.

For one record, overhead may be tiny. For 10,000 records of the same shape, object overhead becomes substantial.

### 2.2. Compression Does Not Reduce Heap Proportionally

Kafka batch compression reduces bytes over the network and in log storage. Once the consumer fetches and decompresses, the application still needs the data in a processable form. Never use compressed size to size listener heap.

Example:

- Compressed batch: 5 MB.
- Decompressed record data: 30 MB.
- Deserialized DTO graph: 55 MB.

The figures above merely illustrate possible amplification. Measure with production-like payloads, your actual serializer, and your actual JVM.

### 2.3. Byte Arrays, Strings, and Copies

If the listener receives `byte[]`, the application may retain the raw bytes. If it receives a String and parses JSON, bytes/String/tree/DTO may coexist for a period. If code re-serializes the record to publish to retry/DLT, the producer may hold additional byte buffers.

Avoid creating unnecessary copies, yet do not optimize by sharing mutable objects across threads if doing so causes data races or mutates payloads during retries.

## 3. DefaultErrorHandler and Two Ways to Handle Remaining Records

In modern Spring Kafka, `DefaultErrorHandler` handles listener exceptions, retries according to a `BackOff`, and forwards records to a recoverer once the retry policy exhausts.

When one record in a poll fails, the remaining unprocessed records in that poll must also be handled properly. Spring Kafka offers two important approaches:

- **Seek behavior:** the error handler seeks the necessary offsets so records are fetched/redelivered later.
- **Retain behavior:** with `seekAfterError=false` in supported versions, the container retains unprocessed records in memory and resubmits them after a paused poll to maintain consumer liveness.

The retain option can be useful when you want to avoid seeks/re-fetches, yet in return the records awaiting retry occupy heap throughout the wait.

### 3.1. Seek-Based Retry

Conceptual model:

~~~text
poll() returns records 100..109
       |
       v
listener handles 100, 101, 102
       |
       v
record 103 fails
       |
       v
error handler seeks relevant offset(s)
       |
       v
backoff / retry handling
       |
       v
consumer polls again
       |
       v
Kafka redelivers from the seek position
~~~

In seek-based handling, the container/error handler uses consumer positions to request re-reading the necessary records. Records from the previous poll do not need to be kept as a retained in-memory collection for resubmission under the retain mechanism; however, the Kafka client still has fetch buffers and the container still holds references during active processing.

Seek does not mean zero memory usage. It simply changes where the container gets the record for the next delivery: the broker/client fetch path instead of retaining the unprocessed record set in memory for resubmission.

### 3.2. Retain-Based Retry with seekAfterError=false

In Spring Kafka versions supporting `setSeekAfterError(false)`, the container can retain unprocessed records and redeliver them after performing a poll in a paused state.

~~~text
poll() returns records 100..109
       |
       v
listener handles 100, 101, 102
       |
       v
record 103 fails
       |
       v
records requiring redelivery are retained in memory
       |
       v
container pauses delivery and performs poll to maintain liveness
       |
       v
backoff expires
       |
       v
retained records are resubmitted
~~~

This avoids seeks/re-fetches for the records retained under the container's mechanism, yet **record object lifetimes become longer**. With large batches or long backoffs, object references can linger in the heap.

This choice must be weighed during memory sizing. Do not enable retain mode simply because it seems simpler than seeking without measuring how many records and payloads are retained.

### 3.3. Version-Dependent Options

`seekAfterError` and retain/resubmit semantics can vary across Spring Kafka versions. Before using them, check the Javadoc/reference for your exact dependency version, especially if the service runs an older version or uses a custom error handler.

Do not assume every error handler behaves like `DefaultErrorHandler`. Custom handlers may seek, retain, discard, or publish records differently.

## 4. Memory Trade-off Between Seek and Retain

| Criterion | Seek/Re-fetch | Retain/Resubmit |
|---|---|---|
| Where records are retrieved from | Kafka broker via consumer fetch | Records held by the container |
| Old batch heap lifetime | Can be shorter once references are released | Can extend until resubmission/recovery |
| Network/fetch work | May re-fetch data | Avoids part of re-fetching for retained records |
| Long backoff | Consumer/container still must handle poll/liveness properly | Retained objects can sit in heap for the whole wait |
| Large batches | Does not keep a retained collection across retries via the same mechanism | Can consume substantial heap |
| Ordering/redelivery | Follows seek/consumer semantics | Follows container resubmission order |
| Best suited for | Need to bound heap and tolerate re-fetching | Want records kept in memory and sized adequately |

There is no single best choice for every workload. With small payloads, small batches, and short backoffs, retain can work well. With large payloads, large batches, or long outages, seek or retry topics may be more suitable.

## 5. Capacity Formula for Retained Records

An initial estimation model:

~~~text
Retained heap estimate
  ≈ concurrent consumers
    × retained records per consumer
    × average in-memory bytes per record
    × retention multiplier
~~~

Where:

- **Concurrent consumers**: number of active child consumer containers in the instance.
- **Retained records per consumer**: number of records that may remain held from a poll/batch during retry.
- **Average in-memory bytes per record**: heap footprint measured from the deserialized object graph, not Kafka serialized size.
- **Retention multiplier**: extra overhead from references, batch/list structures, error state, conversion, and coexisting objects. This is a measured factor, not a Spring Kafka constant.

Total heap must also add fetch buffers, listener allocations, producer buffers, executor queues, framework overhead, and other application state.

### 5.1. Calculation Example

Suppose an instance has:

- 4 child consumers.
- Each consumer can retain 250 records from a poll.
- Average heap footprint after deserialization is 80 KB/record.
- Headroom factor for object/batch overhead is 1.5 in the measured example.

~~~text
4 × 250 × 80 KB × 1.5
= 120,000 KB
≈ 117 MiB
~~~

Roughly 117 MiB is only the estimate for the retained batch under those assumptions. It excludes fetch buffers, producer buffers, application state, thread stacks, caches, and records being processed elsewhere.

If average payload doubles or concurrency rises from 4 to 8, estimated memory also rises nearly linearly in this simple model.

### 5.2. P95/P99 Matters More Than Average

Payload sizes often follow a skewed distribution: most records are small while a few are very large. Using averages can underestimate peak-hour memory.

Measure:

- Serialized value size p50/p95/p99.
- Deserialized object graph size p50/p95/p99.
- Records per poll/batch.
- Number of records retained on retry.
- Number of child consumers per pod.
- How long records remain in memory.
- Proportion of records with unusually large payloads.

Sizing should rest on peak workloads or SLO-accepted percentiles, not just a quiet day's average.

### 5.3. Do Not Mechanically Multiply by Retry Attempts

If the same record objects are retained and resubmitted, the retry count does not necessarily create another full object copy on every attempt. Memory may depend mainly on the retained record count and allocations generated per attempt.

Conversely, if code appends each attempt to a list/cache, creates transformed copies, or enqueues new tasks, memory can grow with attempts. Analyze object references and heap dominators instead of assuming retry count is always a multiplier.

## 6. max.poll.records: Capping Records Returned per Poll

`max.poll.records` is the consumer setting that limits how many records a single `poll()` returns to the application. It is one of the primary knobs controlling batch size and the volume of data a listener container may have to hold.

Spring Boot example:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        max.poll.records: 100
~~~

If a consumer polls at most 100 records instead of 500, the number of records in one processing cycle drops, reducing retained batch size in many scenarios.

However, `max.poll.records` is **not an absolute byte limit for heap**:

- 100 records could be 100 KB or hundreds of MB depending on payload.
- The Kafka consumer fetcher may already have buffered data from the broker before poll returns records.
- A single record/batch can exceed normal fetch limits under Kafka's progress guarantee rules.
- Deserialized objects can exceed serialized bytes.
- Multiple child consumers maintain separate poll/fetch state.

### 6.1. Choosing max.poll.records by Memory and Processing Time

Lowering `max.poll.records` generally shrinks the records processed per poll, though it can increase poll frequency and lower throughput when batch processing is optimized.

Beyond memory, compare total batch processing time against `max.poll.interval.ms`. Smaller batches help the consumer return to poll more frequently, yet do not replace a timeout on a stalled record.

### 6.2. Batch Listeners Hold Large Batch Objects

With a batch listener, the container delivers multiple records to one invocation. A 500-record batch with large payloads can hold the list, `ConsumerRecord` wrappers, and DTO objects simultaneously.

Example:

~~~java
@KafkaListener(
    topics = "orders.bulk",
    groupId = "orders-bulk-service"
)
public void consumeBatch(List<OrderEvent> events) {
    bulkService.process(events);
}
~~~

If a batch listener fails on one record, error handling and retry semantics must be understood in batch mode. Retaining/replaying the batch can keep many other records in memory even when only one record failed.

Do not measure only the size of the failing record; measure the entire batch and object graph held by the listener.

## 7. Fetch Byte Limits Are Not a Heap Cap

The Kafka consumer has settings such as:

- `fetch.max.bytes`: limits total bytes of a fetch response per client semantics.
- `max.partition.fetch.bytes`: limits fetched bytes per partition.
- `max.poll.records`: records returned per poll.
- `fetch.min.bytes` and `fetch.max.wait.ms`: govern how the broker accumulates data before returning a fetch response.

Example:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        fetch.max.bytes: 52428800
        max.partition.fetch.bytes: 1048576
        max.poll.records: 100
~~~

Values are illustrative. Choose based on payload size, partition count, throughput, and memory budget.

### 7.1. A Batch Can Exceed Expected Limits

The Kafka consumer has rules allowing progress when the first batch in a partition exceeds `max.partition.fetch.bytes` or the corresponding fetch limit. Therefore, do not treat these byte settings as an absolute hard heap ceiling.

If producers permit very large records, consumers must have matching capacity and handling policies. It is better to enforce payload size limits in producer/topic/broker contracts.

### 7.2. The Fetcher Can Hold More Data Than One Poll

`max.poll.records` limits records returned per poll, not necessarily bytes already fetched/cached in the client. The consumer may hold buffered data for subsequent polls.

When investigating heap, inspect both Kafka client fetch buffers and records promoted to application objects.

### 7.3. Multiple Concurrent Partitions

One fetch request can pull data from multiple assigned partitions. With high concurrency, each child consumer has its own fetch state. Total pod memory must sum across **all consumers**, not a single consumer.

## 8. Concurrency Multiplies Memory Consumption

A `ConcurrentMessageListenerContainer` can manage multiple child consumers. Each child maintains its own consumer client, fetch buffers, assignments, and poll batches.

~~~text
orders-listener (concurrency=4)
    |
    +-- child-0: fetch buffers + current/retained records
    +-- child-1: fetch buffers + current/retained records
    +-- child-2: fetch buffers + current/retained records
    +-- child-3: fetch buffers + current/retained records
~~~

If each child can hold 200 records and each record has a 150 KB heap footprint, the retained payload estimate before overhead is:

~~~text
4 × 200 × 150 KB = 120,000 KB ≈ 117 MiB
~~~

Raising concurrency can boost throughput when partitions and downstream capacity allow, yet also multiplies consumer instances, fetch buffers, batches, and in-flight listener work.

### 8.1. Concurrency Does Not Create More Partitions

If a topic has only 3 partitions while listener concurrency is 8, 8 consumers cannot process one partition in parallel. Some child consumers may receive no partitions, yet still incur thread/client lifecycle overhead depending on implementation.

Calculate memory based on actively running and assigned child consumers, and measure during rebalances as well.

### 8.2. Multiple Listener Containers in the Same JVM

A Spring Boot application can host multiple listener factories and listeners:

- Orders listener concurrency 4.
- Payments listener concurrency 3.
- Audit listener concurrency 2.

Total child consumers equal 9, excluding producer templates, retry listeners, and `AdminClient`. Sizing each listener in isolation can push total heap past the pod limit.

Use a service-wide memory budget and metrics broken down by listener ID/container.

## 9. Prolonged Backoff Keeps Records Alive Longer

A retry policy may have a small attempt count yet retain records for a long duration:

~~~java
DefaultErrorHandler errorHandler =
        new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(10_000L, 5L)
        );
~~~

This example uses a 10-second backoff with the retry count configured per Spring Kafka API. Total time a record remains in the retry flow also depends on listener processing, redeliveries, recovery, and how the handler counts attempts.

When records are retained in memory, long backoffs keep object references alive longer. When multiple partitions hit dependency failures simultaneously, retained records accumulate and GC cannot reclaim them.

### 9.1. Backoff and Heap Occupancy

A simple view:

~~~text
Memory pressure
  ∝ records retained concurrently
    × heap footprint per record
    × time records remain reachable
~~~

This is not an exact GC formula, yet it highlights two drivers: how many records are held concurrently and their lifetime.

If a database outage lasts 20 minutes, retain mode may hold unprocessed records for a substantial period. If many records are polled while the dependency fails, memory pressure grows with the backlog sitting inside the process.

### 9.2. Many Retries Do Not Mean Linear Heap Growth

If the handler resubmits the same records, reference count may not grow with attempt count. However, each attempt can allocate exception objects, stack traces, temporary payload transformations, logs, and DB/network buffers.

A retry storm increases allocation rate even when the retained set stays flat. Monitor both heap occupancy and allocation/GC rates.

## 10. ContainerPausingBackOffHandler and Poll Liveness

With long backoffs, blocking the consumer thread with sleep can prevent frequent enough polling and violate `max.poll.interval.ms`. Spring Kafka provides `ContainerPausingBackOffHandler` in supported versions to coordinate backoff with container pausing, allowing the container to keep polling as needed.

Illustrative configuration example:

~~~java
DefaultErrorHandler errorHandler =
        new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(30_000L, 3L),
                new ContainerPausingBackOffHandler()
        );
~~~

Verify constructors/APIs on your exact Spring Kafka version before using. Handling long backoffs protects group liveness, yet **does not by itself solve memory retention**.

If paired with `seekAfterError=false`, retained records can still remain in memory while the container pauses/backs off. Polling to maintain liveness does not mean retained records are freed.

### 10.1. Pause vs. Stop

Pausing a container temporarily halts delivery/fetching from paused partitions according to container semantics, while the container can still poll to maintain group membership. Stopping closes the consumer and exits the lifecycle/group.

Do not stop consumers solely to free retained records without assessing offsets, in-flight work, redelivery, and rebalances. Restarting can cause records to be re-read, so business side effects must be idempotent.

### 10.2. Backoff Handler Does Not Replace Capacity Planning

A handler keeps the poll loop healthy, yet heap can still exhaust if the retained set is large. You still need record/batch sizing, memory metrics, bounded retries, and an independent recovery path.

## 11. Stateful Retry and Retry State Caches

Some applications use Spring Retry or custom stateful retry to store attempt state keyed by message key/record identity. Memory can then grow not only from record payloads, but also from **retry state entries**.

A state cache might store:

- Record identifying key.
- Retry count.
- Last attempt timestamp.
- Exception or retry context.
- Metadata deciding whether to continue or stop.

If the cache lacks capacity/TTL/eviction bounds or keys are unstable, entries can linger longer than expected.

### 11.1. Retry State Should Be Bounded

Cache design must define:

1. Maximum entry count.
2. TTL or expiry policy.
3. Cleanup upon successful recovery.
4. Behavior on process restart.
5. Whether the retry state key stays stable across redelivery.
6. Whether exceptions/stack traces or large payloads are stored.

Do not store entire `ConsumerRecord` instances or DTO graphs inside a retry cache when only keys and attempt metadata are needed.

### 11.2. In-Memory State Is Not a Durable Retry Log

If the process crashes, retry state in heap can be lost. Kafka committed offsets and redelivery form a separate recovery mechanism. Never treat an in-memory retry cache as proof a record is durably persisted.

If retry state must survive process restarts, consider retry topics or a durable store with explicit idempotency/reconciliation.

## 12. Retry Topics Shift Part of Retention to the Broker

With non-blocking retries, records are published to a retry topic and consumed again after a delay. Instead of holding records in application heap throughout backoff, the system stores records on the Kafka broker.

~~~text
source topic
   |
   v
listener fails
   |
   v
producer sends retry record
   |
   v
retry topic (broker retention)
   |
   | delay / due time
   v
retry listener consumes record
   |
   +-- success
   |
   +-- fail --> next retry topic / DLT
~~~

This shortens record retention inside the consumer JVM for long backoffs, though it does not reduce memory cost to zero:

- Consumers still fetch batches from retry topics.
- Producers still buffer/serialize retry records.
- Retry listeners still deserialize payloads.
- Retry headers and metadata enlarge records.
- Brokers need disk/network/replication capacity.
- Many retry topics can increase metadata and operational overhead.

### 12.1. When Are Retry Topics Suitable?

Retry topics are often worth considering when:

- Backoffs span tens of seconds to minutes.
- You do not want to hold consumer threads/batches in memory during the wait.
- Altered ordering semantics between source and retry topics are acceptable.
- Sufficient broker capacity and retention policies exist.
- Retry processing can be designed idempotently.

### 12.2. When Is Blocking Retry Suitable?

Blocking retry may fit when:

- Errors are typically short and transient.
- Simple partition-level processing order must be preserved.
- Payloads are small and batches/concurrency are bounded.
- Backoffs are short.
- You prefer not to add retry topics and routing infrastructure.

Do not pick retry topics solely to reduce heap if brokers lack disk/network capacity or ordering requirements prohibit moving records to another topic.

### 12.3. Ordering Must Be Evaluated

When a failing record moves to a retry topic, subsequent records in the source topic can continue processing depending on configuration. This can alter business completion order.

If strict per-key/partition ordering is required, design a retry strategy that preserves sequencing or pauses progress appropriately. Memory optimization must not break domain ordering.

## 13. Async Listeners and Application Executor Queues

A very large memory source sits outside the Spring Kafka error handler: listeners submitting tasks to an executor and returning.

~~~java
@KafkaListener(topics = "orders.created")
public void consume(OrderCreated event) {
    workerPool.submit(() -> orderService.process(event));
}
~~~

If the executor queue is unbounded, the consumer can poll and submit records faster than workers process them. The queue holds references to event objects, growing heap unboundedly even though Spring Kafka retains no records for retry.

This is an **application queue**, not `DefaultErrorHandler`'s retained records collection.

### 13.1. Bounded Executor Queues

Use a bounded queue and an explicitly designed rejection/backpressure policy:

~~~java
@Bean
public ThreadPoolTaskExecutor orderWorkerPool() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(8);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(200);
    executor.setThreadNamePrefix("order-worker-");
    executor.initialize();
    return executor;
}
~~~

Numbers are illustrative. A bounded queue caps waiting tasks, yet queue-full behavior must be handled. A `RejectedExecutionException` can propagate back to the listener for error handling, or the application can pause the container via an appropriate control plane.

### 13.2. Ack After Async Tasks Complete

If a listener returns before workers finish, the container may acknowledge/commit input records per policy before business tasks succeed. Both memory queues and data correctness are then at risk.

A reliable design must:

- Only ack once work completes per contract.
- Or write to a durable inbox/work item before acking Kafka.
- Cap in-flight task count.
- Use idempotency for redeliveries.
- Drain/cancel tasks cleanly on shutdown.

Never treat an unbounded in-memory queue as a durable retry store.

## 14. Producer Buffers When Publishing Retries or DLT

When a recoverer sends records to a retry topic/DLT, the producer may hold serialized records in its accumulator/buffer until brokers accept them or delivery timeout occurs.

Related settings:

- `buffer.memory`: memory budget of the producer accumulator.
- `batch.size`: batch size per partition.
- `linger.ms`: wait time to accumulate batches.
- `max.block.ms`: how long `send()` can block waiting for metadata/buffers.
- `delivery.timeout.ms`: delivery time cap per producer semantics.
- `max.request.size`: producer-side request size limit.

Spring Boot example:

~~~yaml
spring:
  kafka:
    producer:
      properties:
        buffer.memory: 33554432
        batch.size: 16384
        linger.ms: 5
        max.block.ms: 60000
        delivery.timeout.ms: 120000
~~~

Values are illustrative, not a universal recommendation. If multiple consumers generate DLT/retry sends simultaneously during an outage, producer buffers can grow alongside retained consumer records.

### 14.1. Producer and Consumer Memory Add Up

A service that both consumes and publishes retries/DLT can hold:

- Consumer fetch buffers.
- Retained records from listener failures.
- Deserialized payload objects.
- Producer accumulator buffers for retry/DLT sends.
- Send futures/callback state.
- Temporary serialization buffers.

Sizing pods solely by `-Xmx` and `max.poll.records` while ignoring producer buffers is incomplete.

### 14.2. Send Results Must Be Handled Properly

Do not treat calling `KafkaTemplate.send()` as proof a record is durably persisted. With `DeadLetterPublishingRecoverer`, configure send result verification as supported by your version—such as `setFailIfSendResultIsError(true)`—and set appropriate timeouts.

If DLT publishing fails, recovery must be treated as failed per policy. Never ack the source record just to free memory when no durable storage exists for it.

## 15. Deserialization, Conversion, and Payload Size

Memory retention can surge if deserializers build huge object graphs or converters allocate extra copies.

Questions to answer:

- Does the listener receive `ConsumerRecord<K,V>`, a DTO, or a batch?
- What objects does the deserializer allocate and does it copy bytes?
- Does the JSON parser create an intermediate tree before the DTO?
- Does the message converter allocate new Strings/`byte[]`?
- Does the listener capture payloads in caches or closures?
- Do exceptions retain references to payloads/contexts?
- Does logging/tracing re-serialize payloads?

### 15.1. Avoid Retaining Records in Exceptions or Custom Caches

A custom exception might store an entire DTO as a field for diagnostics. If retry state or an error queue holds that exception for long, the entire payload graph stays alive.

Usually only safe metadata needs to be recorded: event ID, topic, partition, offset, and exception category. If raw payloads must be preserved, use a durable quarantine/DLT with access controls and retention rather than holding them indefinitely in heap.

### 15.2. Large Payloads Need Explicit Contracts

Set payload size limits in producer/schema/API contracts. For large files or blobs, consider storing objects in object storage and sending only references plus checksums/metadata through Kafka.

This lowers memory, network, and broker storage usage, though it requires lifecycle/authorization for external objects and ensuring objects remain available throughout any replay window.

## 16. Batch Listeners and Memory When One Record Fails

Batch listeners can hold many records in a single invocation. If one record throws an exception, the error handler must know which record failed or handle batch retries according to configured semantics.

Example:

~~~java
@KafkaListener(
    topics = "orders.bulk",
    groupId = "orders-bulk"
)
public void consume(List<ConsumerRecord<String, OrderEvent>> records) {
    for (ConsumerRecord<String, OrderEvent> record : records) {
        bulkService.process(record.value());
    }
}
~~~

Suppose a batch has 500 records; if record 490 fails, earlier records may already have produced side effects while later ones remain unprocessed. Retrying the entire batch can re-invoke many records.

Memory concerns:

- The entire batch list remains reachable.
- Payload DTOs in the batch remain alive.
- Temporary processing results may be held in lists/maps.
- Retry/recovery logic may need references to remaining records.
- Error objects may hold stacks/contexts.

### 16.1. Batch Size Must Be Grounded in Bytes and Objects

`max.poll.records=500` does not guarantee small batches. A batch of 500 tiny records differs vastly from 500 records carrying multi-hundred-KB payloads.

Measure batch heap footprint at high percentiles and choose fitting limits. If payload sizes vary widely, enforce message size limits at the producer/schema layer or offload large payloads outside Kafka.

### 16.2. Batch Failure Semantics

Batch listeners can throw `BatchListenerFailedException` to pinpoint the failing record index on supported APIs. How retry/seek/recovery proceeds depends on the handler and version.

Do not manually cache a copy of the entire batch in application memory to "retry later" when the container already provides error handling. That can double memory without improving reliability.

## 17. Backpressure When Downstream Fails

If a database or HTTP dependency goes down, many records may fail repeatedly and enter retry. Three general options exist:

1. **Short bounded retries:** suited for transient failures.
2. **Pause/backpressure:** throttle intake while waiting for the dependency.
3. **Retry topic/durable queue:** move pending work out of consumer heap.

A circuit-breaker flow:

~~~text
Listener failure rate rises
       |
       v
Classify exception
       |
       +-- transient, short outage --> bounded retry
       |
       +-- downstream unavailable --> pause / backpressure
       |
       +-- long delay needed --> retry topic
       |
       +-- permanent payload error --> DLT/quarantine
~~~

Do not pause on every exception. Invalid payload errors can recover to DLT immediately if the DLT is healthy; prolonged dependency outages may require backpressure to prevent retry storms.

### 17.1. Pause Does Not Automatically Free Retained Records

If the container is retaining records in memory for resubmission, calling `pause()` does not make those references vanish. Pausing controls record intake/delivery; memory is only freed once references become unreachable and GC reclaims them.

Verify exact error handler/container state before assuming pause will reduce heap.

### 17.2. Pause Scope

One failing child consumer does not necessarily require pausing all listeners in the JVM. Pick container/partition scope based on dependencies and ordering. If a dependency is shared service-wide and all consumers rely on it, a service-level gate may fit better.

## 18. GC and Signs of Memory Pressure

When records are retained for long periods, GC cannot collect them even when the application is not actively processing them at that moment. Heap occupancy can stay elevated across many GC cycles.

Manifestations:

- Rising old-generation occupancy.
- More frequent mixed/full GCs.
- Prolonged GC pauses.
- Rising allocation rates as retries create exceptions/transformation objects.
- Promotion failures or evacuation failures.
- Containers OOMKilled for exceeding pod memory limits.
- Producer buffers/fetch buffers competing for heap with application objects.

### 18.1. Heap Dumps and Dominator Trees

During a memory incident, a heap dump reveals which object graphs retain memory:

- `ConsumerRecord` / payload DTOs.
- `ArrayList` or batch collections.
- Byte arrays / Strings.
- Retry state/cache entries.
- Executor queue tasks.
- Producer accumulators/buffers.
- Application caches or closures.

The dominator tree reveals which objects hold references to many others. This finds the real retained set far better than guessing from configuration.

Heap dumps can contain sensitive payloads. Collect, store, and share them under security policies; avoid leaving dump files in publicly accessible locations.

### 18.2. Heap Is Not All Container Memory

Kubernetes memory limits include regions outside the Java heap: metaspace, code cache, thread stacks, direct buffers, native memory, mmap, and process overhead.

If `-Xmx` sits right up against the pod memory limit, Kafka client/direct buffers or native allocations can OOMKill the container even before heap hits max.

For sizing, reserve headroom for non-heap and OS/container overhead.

## 19. Metrics to Monitor for Retry Memory

A capacity dashboard should combine application, JVM, and Kafka metrics.

| Metric | Meaning |
|---|---|
| JVM heap used / max | Heap utilization |
| Old-gen occupancy | Long-lived/retained objects |
| Allocation rate | Object creation rate |
| GC pause duration/count | Cost of reclaiming memory |
| Process/container RSS | Actual resident process memory |
| Direct buffer pool used | Native/direct buffer memory |
| Records per poll | Records received per poll |
| Batch size bytes | Total batch payload bytes |
| Retained retry record count | Records held for retry, if instrumented |
| Retry duration / attempts | Retry lifetime and frequency |
| In-flight listener count | Active work in flight |
| Executor queue depth | Waiting tasks |
| Producer buffer available/wait | Producer memory pressure |
| Consumer lag / oldest record age | Broker-side backlog |
| DLT/retry publish failures | Health of retry offload path |

Metrics like `retained_retry_record_count` may require custom instrumentation; do not assume Spring Kafka exposes every internal retained collection out of the box.

### 19.1. Metrics on Record Retention Duration

If the application needs to know how long memory retention lasts, instrument when a record enters the retry flow and when retry/recovery finishes. You do not need to store full payloads in metric state; store compact metadata in a bounded cache or emit appropriate events/metrics.

Be careful with event IDs as metric tags due to high cardinality. Event IDs belong in logs/traces where policy permits.

### 19.2. Correlating Memory with Retries

A meaningful timeline:

~~~text
10:00 downstream DB begins slowing down
10:02 retry attempts increase
10:03 retained retry records increase
10:04 old-gen occupancy increases
10:05 GC pause p99 increases
10:06 consumer lag increases
10:08 circuit breaker opens / listener pauses
10:12 DB recovers, retries resume
10:15 heap and lag gradually drop
~~~

If heap rises before retry rates climb, the cause may lie in a cache or another workload. Correlation forms hypotheses; heap dumps and thread dumps confirm references.

## 20. Sample Configuration for Bounded Retained Records

An example listener factory and error handler configuration:

~~~java
@Configuration
public class RetryMemoryConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
            kafkaListenerContainerFactory(
                    ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        var properties = factory.getContainerProperties();
        properties.setPollTimeout(1_000L);

        return factory;
    }

    @Bean
    public CommonErrorHandler commonErrorHandler(
            DeadLetterPublishingRecoverer recoverer) {

        DefaultErrorHandler handler =
                new DefaultErrorHandler(
                        recoverer,
                        new FixedBackOff(2_000L, 2L)
                );

        // Only use on supported versions and after sizing the retained batch.
        handler.setSeekAfterError(false);

        return handler;
    }
}
~~~

This snippet illustrates retain mode. Constructors/imports and APIs must match your Spring Kafka version. In production, the factory also needs appropriate serializer, transaction, error handler, observation, and consumer properties.

**This is not a "safe default" for every payload.** When enabling `seekAfterError=false`, size retained records and test behavior under batches, concurrency, and outages.

### 20.1. Seek-Based Alternative

If you want the container to seek and re-fetch instead of retaining records in memory across retries, keep `seekAfterError` at your version's default behavior or configure it explicitly per supported API.

Do not enable retain mode merely to avoid broker fetches; re-fetching is often a sensible trade-off when memory headroom is the primary constraint.

### 20.2. Capping Record Counts

Example consumer properties:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
      properties:
        max.poll.records: 100
        max.partition.fetch.bytes: 1048576
        fetch.max.bytes: 52428800
~~~

Values must be chosen alongside payload limits and concurrency. Do not treat byte fetch limits as hard heap caps, as explained above.

## 21. Sizing Memory for a Spring Kafka Pod

One way to structure the budget:

~~~text
Pod memory limit
  >= JVM heap budget
   + metaspace / code cache
   + thread stacks
   + direct/native buffers
   + OS/container overhead
   + safety headroom

JVM heap budget
  >= application baseline
   + consumer fetch buffers
   + retained/retry records
   + active listener object graphs
   + executor queues
   + producer buffers and callbacks
   + caches/framework state
   + GC headroom
~~~

Never set `-Xmx` equal to the entire pod memory limit. Leave room for native/direct memory, thread stacks, and process overhead.

### 21.1. Size per Instance, Not Cluster Total

Suppose a cluster has 12 consumer instances, each pod with a 1 GiB memory limit. You cannot divide total heap across 12 pods by average to conclude a single pod has enough memory.

A partition hotspot or rebalance can temporarily give one pod more records/assignments than expected. Sizing must reflect per-pod peaks, concurrency, and worst-case assignments.

### 21.2. Headroom During Rebalances

During a rebalance, assignments shift and consumers may fetch/process records from new partitions. References from old polls/batches, in-flight work, and new fetch activity can overlap briefly depending on lifecycle.

Do not benchmark only steady state. Check peak memory during rolling deployments, restarts, partition reassignments, and dependency outages.

## 22. Prolonged Outages: Retain in Heap or Move to Durable Retry?

If a downstream outage lasts 30 minutes, holding many records in consumer heap is likely no longer a good strategy. Evaluate where pending work should live.

| Strategy | Where Does Pending Data Live? | Pros | Cost/Risk |
|---|---|---|---|
| In-memory retain | Consumer JVM heap | Avoids re-fetch, fast handling | Heap pressure, state lost on crash |
| Seek/re-fetch | Kafka source topic + client fetch | Shortens retained collection lifetime | Re-fetches data, consumer still retries |
| Retry topic | Kafka broker log | Long backoff without keeping source records in heap | Extra produce/consume, disk/network, ordering |
| Durable outbox/inbox | Database/storage | Durable and orchestratable | DB capacity, duplicates/reconciliation |
| DLT/quarantine | Kafka topic or durable store | Preserves failed payloads for investigation/replay | Requires write success, ACLs, retention, replay policy |

Never use in-memory retain as durable storage. Process crashes or pod OOMs wipe out in-memory retry state; Kafka committed offsets determine which records are redelivered.

### 22.1. Source Retention Still Matters

With seek/re-fetch, records must still exist in the Kafka source topic when the consumer returns. If an outage outlasts retention and records are deleted before re-reading, the consumer cannot re-fetch expired data.

Monitor oldest unprocessed event age, topic retention, consumer lag, and outage duration. Retry topics also have their own retention that must exceed wait and operational recovery windows.

### 22.2. Retry Topics Do Not Automatically Guarantee Exactly-Once

Republishing to a retry topic and crashing before committing the source offset can produce duplicate retry records when the source is re-read. Implement idempotency, original topic/partition/offset metadata, and consumer deduplication where appropriate.

## 23. Ordering and Partition Semantics During Retries

Retaining records in memory or seeking back can affect delivery order within a partition depending on handler/container behavior. Retry topics can let the source partition proceed while failing records wait.

Define requirements clearly:

- Is strict partition-wide ordering required?
- Can records with different keys be processed in parallel?
- Does one failing record block subsequent records?
- Can retries be sequenced per key/aggregate?
- Could replays execute after newer events?

If business logic requires per-aggregate ordering, a memory optimization that delays failing records past newer ones can cause invalid state transitions. Enforce sequence/version checks and idempotency.

### 23.1. Do Not Skip Records to Free Heap

Do not ack/commit a failing record merely to free a batch from memory without durable recovery. Doing so can drop the record from the source processing path.

If business policy permits quarantining/skipping, persist the record durably, audit it, and only then complete recovery per defined semantics.

## 24. Common Mistakes

**Using serialized size to size heap.** Deserialization, object graphs, copies, and batch wrappers make the footprint very different from bytes in Kafka.

**Enabling `seekAfterError=false` without sizing retained batches.** Unprocessed records can live in heap throughout backoff/retries.

**Assuming every retry allocates a full copy.** The same object references may be resubmitted; measure the real retained set rather than multiplying attempts mechanically.

**Assuming seek means zero memory.** Consumer fetch buffers and active poll objects still consume memory.

**Only lowering `max.poll.records`.** Fetcher buffers, payload sizes, concurrency, producer buffers, and executor queues can still drive heap/native memory high.

**Treating `max.partition.fetch.bytes` as a hard heap limit.** Kafka has first-batch progress behavior; deserialized objects also exceed wire bytes.

**Raising concurrency to clear backlogs without sizing heap.** More child consumers mean more fetch buffers, batches, and in-flight objects.

**Using long backoffs on retained records without monitoring heap.** Record lifetimes grow and GC cannot reclaim reachable objects.

**Using unbounded executor queues.** Listeners may ack quickly while task queues hold unbounded payloads.

**Waiting indefinitely on producer sends during DLT outages.** Producer buffers and retained source records can grow simultaneously.

**Using retry topics while forgetting broker capacity.** Heap drops while disk/network/metadata/consumer load climbs.

**Swallowing exceptions so the listener returns normally.** Offsets may be committed even though output/recovery is not durable.

**Acking before async tasks complete.** Memory queues and delivery semantics both become unsafe.

**Holding exceptions containing large payloads in retry caches.** Stack/context references can keep entire object graphs alive.

**Having no upper bound on stateful retry caches.** Entries accumulate over time and process lifetimes.

**Setting `-Xmx` right up to the container memory limit.** Direct buffers, metaspace, and thread stacks can OOMKill the pod.

**Skipping long-outage testing.** Steady-state memory does not reflect retained records during dependency failures.

**Relying on average heap usage.** P99 payloads and batch sizes dictate peak memory.

**Skipping records to relieve memory.** Can lose data and break offset ordering.

## 25. Runbook When Heap Grows During Retries

### Phase A — Identify the Retry Mode

1. Identify listener ID, group, topic, and consumer concurrency.
2. Identify the active handler: `DefaultErrorHandler`, custom handler, or retry topics.
3. Check `seekAfterError` and exact behavior for your Spring Kafka version.
4. Record backoff, attempts, `max.poll.records`, and fetch byte limits.
5. Determine whether records are being retained, sought/re-fetched, or published to retry/DLT.
6. Identify which dependency is causing listener failures.

### Phase B — Identify the Memory Owner

1. Inspect heap used/max and old-gen occupancy.
2. Inspect GC logs, allocation rates, and pause durations.
3. Capture a heap dump if permitted and safe.
4. Inspect the dominator tree for `ConsumerRecord`, DTOs, byte arrays, lists, retry caches, and executor queues.
5. Check producer buffers/direct memory.
6. Compare records per poll, payload sizes, and concurrency.
7. Check per-pod peak memory, not just cluster averages.

### Phase C — Stabilize Intake

1. Recover the downstream dependency if possible.
2. Lower `max.poll.records` or batch size in a controlled way if retained batches are too large.
3. Lower concurrency if total per-pod buffers/records exceed budget.
4. Use pause/backpressure when intake must stop, without assuming pause frees retained records.
5. Consider seek/re-fetch or retry topics for long backoffs if semantics permit.
6. Bound executor queues and retry state caches.
7. Ensure DLT/retry publish failures are never treated as recovery success.

### Phase D — Recover and Verify

1. Resume per policy once the dependency recovers.
2. Monitor heap/old-gen/GC as records retry.
3. Confirm committed offsets and consumer lag progress.
4. Check for duplicate side effects and idempotency.
5. Monitor retry topic/DLT ingress and backlogs.
6. Wait for heap to return to baseline after retained references are released.
7. Update the capacity model with measurements from the incident.

Do not conclude a memory leak simply because heap has not dropped immediately after retries end. GC may not have run yet, or the JVM may keep committed heap for reuse. Inspect live sets/GC behavior and heap dumps.

## 26. Integration and Load Tests for Retry Memory

A unit test merely verifying that a listener throws an exception is insufficient to prove container memory behavior. Run integration/load tests with a real Kafka broker and representative payload sizes.

### 26.1. Testing Seek Behavior

1. Create a multi-partition topic.
2. Configure a record listener and `DefaultErrorHandler`.
3. Send a batch of records with one record designed to fail.
4. Confirm the handler seeks/redelivers per policy.
5. Measure consumer fetches and listener attempts.
6. Monitor heap after current poll references are released.
7. Confirm no offset is committed past the unrecovered record.

### 26.2. Testing Retain Mode

1. Use a version supporting `seekAfterError=false`.
2. Configure fixed `max.poll.records` and concurrency.
3. Send records with known payload sizes.
4. Fail one record and hold backoff long enough to observe.
5. Measure heap occupancy and retained objects.
6. Confirm the container maintains poll/liveness per mechanism.
7. Let the retry succeed and observe references freed afterward.

Do not assert an exact byte count in every CI run since GC/JVM/environment variations occur. Compare trends, retained object counts, and capacity limits in a stable environment.

### 26.3. Payload Size Distribution

Test with:

- Small payloads.
- Typical payloads.
- P95 payloads.
- P99/maximum allowed payloads.
- Compressed payloads with high expansion ratios.
- Payloads deserializing into deeply nested object graphs.

Verify peak memory remains within budget at target concurrency and batch sizes.

### 26.4. Batch Listener Failures

Send a large batch and fail a record mid-batch. Verify batch retry semantics, record ordering, side effects created before the failure, and heap retention. Use idempotency to verify re-invoked records do not duplicate business effects.

### 26.5. Long Outages

Make the downstream dependency unavailable long enough to build backlogs/retries.

Observe:

- Retained record count/heap.
- Old-gen occupancy and GC pauses.
- Consumer lag.
- Retry attempts and duration.
- Container poll/group membership.
- DLT/retry topic producer behavior.
- Recovery once the dependency comes back online.

This is the most critical test because memory pressure typically emerges when many records are retained together during an outage, not during a single isolated retry.

### 26.6. OOM/Restart Recovery

In an isolated test environment, restart the consumer process while records are retrying. Verify Kafka committed offsets enable the needed redelivery, side effects are idempotent, and in-memory retry state is not treated as durable.

Never intentionally trigger OOM in production for testing. Use staging with matching resource limits and controlled payloads/throughput.

## 27. Capacity Review Before Changing Retry Policy

Before increasing backoff, concurrency, or `max.poll.records`, recalculate:

1. Post-deserialization payload heap footprint.
2. P95/P99 payload sizes and batch sizes.
3. Actual child consumer count per pod.
4. Records potentially held concurrently during retry.
5. Backoff duration and outage duration to withstand.
6. Producer buffer budget if publishing retries/DLT.
7. Executor queue depth and in-flight tasks.
8. JVM non-heap/direct memory.
9. Pod/container memory limits and safety headroom.
10. Kafka source/retry topic retention.
11. Consumer lag catch-up capacity after recovery.
12. Ordering/idempotency requirements.

A retry policy is only sound when it protects delivery semantics while staying within real memory and broker capacity.

### 27.1. Quick Decision Table

| Condition | Direction to Consider |
|---|---|
| Small payloads, short retries, small batches | Blocking retry may suffice |
| Large payloads, low heap headroom | Prioritize capping batches; consider seek/re-fetch |
| Long backoffs | Container pausing backoff or retry topics depending on semantics |
| Prolonged downstream outage | Backpressure and durable retry instead of retaining in heap indefinitely |
| Strict per-partition ordering | Design blocking/partition-level policies carefully |
| Many consumers in one JVM | Sum fetch/retained memory across all child containers |
| Async listener | Bounded queue and ack after completion/durable enqueue |
| DLT producer may fail | Verify send results, keep offsets safe, do not skip |
| Payloads can be very large | Enforce contract limits or store blobs outside Kafka |
| Stateful retry | Bounded cache, TTL, and explicit cleanup |

## 28. Code Review Questions

When reviewing a listener with retries, ask:

- Is the error handler `DefaultErrorHandler` or custom?
- Is `seekAfterError` true or false under effective config?
- If retain mode, at most how many records can be held?
- Batch listener or record listener? How large can batches get?
- Have serialized payload sizes and deserialized heap sizes been measured?
- Are `max.poll.records`, `fetch.max.bytes`, and `max.partition.fetch.bytes` appropriate?
- What is the concurrency per pod?
- What is the maximum backoff duration?
- Do long backoffs use an appropriate container pausing handler?
- Can retries move to a retry topic to avoid holding heap long?
- Does the application have any unbounded executors/caches holding payloads?
- Are producer retry/DLT buffers included in the memory budget?
- Are DLT send results verified before recovery succeeds?
- Can consumer offsets be committed prematurely?
- Can rebalances/restarts cause redeliveries and duplicate side effects?
- Are heap/GC metrics and retained objects monitored?
- Is there a long-outage/load test with P99 payloads?

If you cannot answer the maximum number of records that can coexist in memory, you do not have enough basis to increase concurrency or enable retain mode in production.

## 29. Version-Specific Reference Documentation

Consult documentation for your exact Spring Kafka/Kafka client versions:

- **Spring for Apache Kafka Reference — Handling Exceptions**: `DefaultErrorHandler`, seeks, retries, recovery, and `seekAfterError`.
- **Spring Kafka Javadoc — `DefaultErrorHandler`**: retry/backoff configuration, `setSeekAfterError`, and recovery behavior.
- **Spring Kafka Reference — Container Pausing**: `ContainerPausingBackOffHandler` and long backoffs.
- **Spring Kafka Reference — Non-blocking Retries / Retryable Topics**: republishing to retry topics, delays, and DLT.
- **Spring Kafka Reference — Listener Containers and Batch Listeners**: record/batch delivery, concurrency, and poll behavior.
- **Apache Kafka Consumer Configs**: `max.poll.records`, `fetch.max.bytes`, `max.partition.fetch.bytes`, `max.poll.interval.ms`.
- **Apache Kafka Producer Configs**: `buffer.memory`, `batch.size`, `linger.ms`, `max.block.ms`, `delivery.timeout.ms`.
- **Java Virtual Machine documentation**: heap, garbage collection, object allocation, and memory diagnostics.
- **Micrometer/Spring Boot Actuator documentation**: JVM memory, GC, executor, and Kafka client metrics.
- **Kubernetes resource documentation**: container memory requests/limits and OOMKilled behavior.

APIs, defaults, and retry semantics can change between Spring Kafka releases. In particular, verify `seekAfterError=false` and retain/resubmit behavior on your exact version before relying on it for capacity planning.

**Technical conclusion:** retaining records for retry can extend object lifetimes in the heap, especially with retain/resubmit mode, large batches, large payloads, high concurrency, or long backoffs. Size around **deserialized heap footprint and concurrent record counts**, bound `max.poll.records`, fetch limits, executor queues, and producer buffers, and consider seek/re-fetch or retry topics when outages or backoffs are long. The goal is preserving retry and offset semantics within a finite memory budget, not turning the consumer heap into an unbounded storage buffer.
