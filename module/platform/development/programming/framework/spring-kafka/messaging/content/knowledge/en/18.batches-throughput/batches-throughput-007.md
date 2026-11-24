# Splitting a batch into smaller chunks

A large batch typically reduces function-call overhead, database queries, or network round trips. However, when processing an entire batch as a single unit, one slow record can stall the whole batch, an error near the end can force already-completed work to rerun, and memory usage grows with input size.

In Spring Kafka applications, you can split a batch into smaller parts (*chunks*) of bounded size. Each chunk becomes a manageable processing unit for controlling duration, memory, and retry scope. To split effectively, first identify which layer a batch lives in.

## 1. Distinguishing batch layers

The term "batch" in Kafka often refers to several different mechanisms. They are related, yet not interchangeable.

| Layer | What "batch" means | Related parameter or mechanism |
|---|---|---|
| Kafka producer | Records grouped into a transmission batch sent to brokers per partition | `batch.size`, `linger.ms` |
| Consumer poll | Records returned by a single `poll()` call | `max.poll.records`, byte-level fetch limits |
| Spring Kafka listener | Listener receives individual records or the full list of records from one poll | `setBatchListener(true)`, `@KafkaListener` |
| Business processing | Application groups multiple records into a smaller work unit | Application-defined chunk size |
| Source system logical batch | A large business request split into multiple Kafka messages | `batchId`, `chunkIndex`, `chunkCount` if tracking is needed |

For example, a producer might send 1,000 events. Kafka groups records into transport batches per partition. The consumer might receive up to 500 records in one poll. The listener then splits those 500 records into 5 chunks of 100 records each to write to the database.

These numbers only illustrate how the layers interact. `batch.size` is not a business chunk size; `max.poll.records` likewise does not automatically split the list received by the listener into smaller pieces.

## 2. When should you split a batch?

Splitting a batch helps when the current unit of work exceeds the practical limits of a processing component:

- Writing too many database rows at once elongates transactions or holds excessive locks.
- One batch consumes excessive heap because each record must be deserialized, mapped, and held alongside intermediate data.
- A downstream service enforces an item cap per request or an ingestion rate limit.
- Processing duration for one poll batch approaches `max.poll.interval.ms`, risking the consumer being marked inactive.
- When an element fails, the system needs clear boundaries for what work must be retried.

Do not split too finely just because you can. Every chunk carries coordination, service invocation, transaction opening, or request overhead. Overly small chunks can degrade overall performance. Choose chunk size based on processing time, downstream limits, and measured metrics.

An important note: splitting a list after the consumer has already received and deserialized it only bounds the application's processing unit. It does not shrink an oversized Kafka record while traveling through the broker. If a single record carries a huge array of data, split it on the producer side into multiple records before sending.

## 3. Choosing chunk boundaries and size

A good chunk has clear boundaries and can be reprocessed safely. When designing chunks, consider the following factors.

**Target system limits.** If a database or API reliably handles only a certain number of items per request, chunk size must stay within that limit. For bulk writes, balance rows per write against transaction duration and lock retention.

**Processing duration.** The listener must finish work for the current poll and return to polling within `max.poll.interval.ms`. When processing multiple chunks sequentially, the relevant duration is the sum of all chunks in the poll, plus data conversion and other overhead. Splitting into chunks does not automatically shorten this total time.

**Memory.** Estimate memory based on post-deserialization record size and intermediate structures, not just bytes on the wire. One hundred Java objects can occupy substantially more memory than the corresponding JSON payloads.

**Ordering.** Kafka guarantees ordering within a partition. If events for the same entity must be processed in order, use a stable key so they land in the same partition and process sequentially within that partition. Do not assume a global order across multiple partitions.

**Duplicate detection and handling.** A chunk can be re-executed after a failure or consumer restart. Every event should have a stable identifier, such as `eventId` or a unique business key. Write operations should be idempotent: receiving the same event multiple times yields the same final state.

Start with a modest size, measure p95/p99 processing time and memory usage, then scale up or down incrementally. No single chunk value fits every topic and every service.

## 4. Splitting received batches in a Spring Kafka listener

Spring Kafka supports batch listeners so one `@KafkaListener` method receives a list of records from a single poll. The factory must enable batch listening:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent> batchListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
            new ConcurrentKafkaListenerContainerFactory<>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.getContainerProperties()
            .setAckMode(ContainerProperties.AckMode.BATCH);

    return factory;
}
```

Next, the listener splits the received list into slices of at most `CHUNK_SIZE` records:

```java
@Component
public class OrderBatchListener {

    private static final int CHUNK_SIZE = 200;

    private final OrderService orderService;

    public OrderBatchListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            topics = "${app.kafka.topics.orders}",
            containerFactory = "batchListenerFactory")
    public void consume(
            List<ConsumerRecord<String, OrderEvent>> records) {

        for (int start = 0; start < records.size(); start += CHUNK_SIZE) {
            int end = Math.min(start + CHUNK_SIZE, records.size());

            List<ConsumerRecord<String, OrderEvent>> chunk =
                    records.subList(start, end);

            List<OrderEvent> events = chunk.stream()
                    .map(ConsumerRecord::value)
                    .collect(Collectors.toList());

            orderService.processChunk(events);
        }
    }
}
```

In this example, `max.poll.records` caps how many records the consumer can receive in one poll, while `CHUNK_SIZE` caps how many events `processChunk` handles per call. If a poll returns 450 records and chunk size is 200, the listener processes chunks of 200, 200, and 50 records in sequence.

`subList` creates a view over the original list. The example above uses the view immediately inside the loop synchronously. If you need to pass a chunk to another thread or retain it after the listener finishes, copy it via `new ArrayList<>(records.subList(start, end))`; never retain a view of the listener's list for asynchronous use.

`processChunk` can map events to entities and invoke a bulk write operation. If each chunk needs its own database transaction, place the transaction boundary on the corresponding service method. A Kafka transaction does not automatically make database writes part of the same transaction.

## 5. Error handling and offsets when a chunk fails

This must be designed before deploying chunking to production.

With a batch listener using `AckMode.BATCH`, the container commits offsets after the listener successfully processes the poll's records under the configured ack mechanism. Suppose the listener finishes the first chunk, and the second chunk throws an exception. Business changes from the first chunk may already be committed to the database while the poll batch remains incomplete. When the batch is redelivered, the first chunk can run again.

Therefore, splitting a batch inside a listener does not give each chunk an independent offset commit. Choose an appropriate error strategy:

- **Retry the entire poll batch:** simple, but any chunk executed before the failure can run again. Business operations must be idempotent.
- **Pinpoint the failed record:** with batch listeners, `DefaultErrorHandler` and `BatchListenerFailedException` can indicate the failing record. The error handler must be configured properly for the desired retry and recovery policy.
- **Route unprocessable items to a dead-letter topic (DLT):** configure a recoverer to store failed records with metadata needed for investigation and replay. DLT routing does not happen automatically just because the listener splits chunks.

If a chunk is processed in a single bulk write and you only know the whole chunk failed, the application may not know which individual record failed. Decide explicitly whether to retry the entire chunk, subdivide the failing chunk further, or send the chunk to a separate recovery flow. Never swallow the error and let the listener return normally: the container may treat the poll as successful and commit offsets, dropping unprocessed events from the retry path.

One way to limit rerun impact is recording processed `eventId` values via unique constraints or appropriate upserts. If an event has already been applied, redelivery must produce no duplicate business effect. For Kafka-to-Kafka flows, consider Kafka transactions and matching read isolation; this still does not automatically cover side effects in systems external to Kafka.

## 6. Splitting a large business batch at the producer

If the source system has a large list where each item can be handled independently, it is usually better to emit each item as its own record. Kafka can then group records per partition at the transport layer:

```java
for (OrderEvent event : events) {
    kafkaTemplate.send(
            "order-events",
            event.orderId().toString(),
            event);
}
```

Here the key is the order ID. Events for the same order route by the same key, preserving order within their partition. The producer can still group multiple records into one network batch; sending individual records via `KafkaTemplate` does not mean each record creates a separate network request.

If downstream needs to receive a group of items as one self-contained message, wrap each chunk in an event carrying metadata:

```java
public record OrderChunk(
        String batchId,
        int chunkIndex,
        int chunkCount,
        List<OrderEvent> items) {
}
```

The producer builds multiple `OrderChunk` messages from the source batch and sends each chunk:

```java
List<List<OrderEvent>> chunks = partition(events, CHUNK_SIZE);

for (int index = 0; index < chunks.size(); index++) {
    OrderChunk chunk = new OrderChunk(
            batchId,
            index,
            chunks.size(),
            chunks.get(index));

    kafkaTemplate.send("order-chunks", batchId, chunk);
}
```

The partitioning helper can be written as:

```java
static <T> List<List<T>> partition(List<T> items, int size) {
    if (size <= 0) {
        throw new IllegalArgumentException("size must be positive");
    }

    List<List<T>> result = new ArrayList<>();

    for (int start = 0; start < items.size(); start += size) {
        int end = Math.min(start + size, items.size());
        result.add(new ArrayList<>(items.subList(start, end)));
    }

    return result;
}
```

In this example, using `batchId` as the key sends all chunks of the same batch to the same partition under the default key-based partitioner. This helps if chunk ordering matters, though a huge batch can concentrate load on a single partition. When load distribution takes priority, key by business entity and design batch ordering or completion tracking accordingly.

The `batchId`, `chunkIndex`, and `chunkCount` fields tell the consumer which batch a chunk belongs to, its position, and the expected total chunk count. They do not automatically guarantee batch completion. If a completion signal is needed, define the completion condition explicitly: all chunks succeeded, or all results recorded. Also handle chunks that arrive late, are resent, or appear in duplicate.

When a producer sends large record volumes, track asynchronous send results and bound in-flight sends. Creating millions of pending futures at once shifts memory pressure from the consumer to the producer. Specific future APIs depend on your project's Spring Kafka version.

## 7. Combining chunking with concurrency

Chunking and concurrency solve two distinct problems:

- Chunking bounds the size of one unit of work.
- Concurrency allows multiple consumers or worker threads to run in parallel.

In Spring Kafka, the listener container's `concurrency` property creates multiple parallel consumers. How many consumers actually receive partitions depends on how many partitions are assigned to the group. Raising concurrency above the partition count does not allow a single partition to be safely processed in parallel by multiple consumers in the same group.

Avoid pushing every record in a chunk into `parallelStream()` or an unbounded executor without considering ordering and offsets. If the listener returns while background tasks are still running, the container may commit offsets before business work completes. If multiple events sharing a key require ordering, parallelizing them can scramble order even though Kafka ordered them in the partition.

A safer pattern is increasing concurrency at the partition level, keeping sequential processing per partition, and parallelizing only independent tasks whose completion is awaited before acknowledgment. If asynchronous work inside a listener is unavoidable, the listener must wait for all related tasks to finish and propagate errors back to the container before returning.

## 8. Tuning and observing throughput

During testing, adjust one limit at a time and observe its effect:

| Signal | What to check |
|---|---|
| Consumer lag grows steadily | Is processing slower than record production; is downstream bottlenecked |
| High poll-batch processing duration | Is total chunk time approaching `max.poll.interval.ms` |
| Sharp heap growth | Are chunks holding many intermediate objects or too many queued tasks |
| Slow database or long locks | Are chunks too large, transactions too long, or too many consumers writing concurrently |
| Rising retries and DLT volume | Are errors concentrated in one record type, oversized chunks, or an unstable dependency |
| Throughput drops with tiny chunks | Is service call, transaction, or request overhead outweighing actual work |

`max.poll.records` caps records in one poll. Lowering it reduces how much work arrives per poll, yet increases poll frequency. `max.poll.interval.ms` sets the time limit between polls. If total processing time still exceeds the limit, reduce work per poll, optimize downstream calls, or change the processing model; merely splitting one poll into multiple loops does not address the root cause.

On the producer side, `batch.size` and `linger.ms` govern how records are grouped for transmission. Increasing `linger.ms` can pack more records per batch at the cost of extra wait latency. Tune them for latency and throughput targets, and keep them distinct from business chunk size.

Track at least records per poll, chunks per poll, actual chunk sizes, per-chunk duration, retry counts, events routed to DLT, and consumer lag. These metrics reveal whether the bottleneck sits in the consumer, database, downstream API, or partition distribution.

## 9. Pre-production checklist

- [ ] Identified whether batching refers to producer, poll, listener, or business layer.
- [ ] Chunks are bounded in size and suited to downstream capacity.
- [ ] Total processing duration for one poll stays safely within the poll interval.
- [ ] Events have stable identifiers and business operations tolerate reprocessing.
- [ ] Retry policy, failed-record identification, and DLT routing are explicitly configured.
- [ ] Key/partition ordering is preserved on flows that require order.
- [ ] Asynchronous tasks never finish after the listener has already acknowledged.
- [ ] Both producer and consumer bound pending in-flight work.
- [ ] Metrics track latency, throughput, lag, retries, and chunk size.

Splitting a batch into smaller chunks helps an application control resource usage and limit reprocessing scope. It pays off only when chunk boundaries align with business boundaries, offsets commit at the right moment, and each unit of work is identifiable on retry. In Spring Kafka, treat poll size, chunk size, partitioning, and error policy as interconnected decisions when designing reliable messaging pipelines.

