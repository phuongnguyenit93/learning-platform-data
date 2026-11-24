# max.poll.records and read batch size

A Kafka consumer does not necessarily deliver records to the application one by one as soon as the broker returns data. The consumer calls `poll()` to retrieve records currently ready from assigned partitions. The `max.poll.records` property caps the maximum number of records returned to the application by a single `poll()` call. In Spring Kafka, this limit directly affects how many records are processed in one poll cycle and the size of the list received by a batch listener.

Choosing the right read batch size balances throughput, latency, memory, and processing time. Too small a batch can reduce batch-processing efficiency; too large a batch can cause the listener to take too long, exceed `max.poll.interval.ms`, and trigger a rebalance. To configure this properly, distinguish the record-count limit of `max.poll.records` from the byte-based limits of the fetch mechanism.

## 1. Consumers read data via poll()

A Kafka consumer maintains its assigned partitions and typically repeats the following cycle:

1. The consumer sends fetch requests to brokers to retrieve data from assigned partitions.
2. The Kafka client receives and buffers fetched records internally.
3. The application calls `poll(Duration)` to retrieve available records.
4. The consumer or listener container processes records, updates progress, and calls `poll()` again.

You can picture a consumer reading three partitions as follows:

```text
Consumer of group order-projection
          |
          +---- Partition 0: records A, B, C, ...
          +---- Partition 1: records D, E, F, ...
          +---- Partition 2: records G, H, I, ...
          |
          v
      poll(Duration)
          |
          v
   ConsumerRecords up to N records
          |
          v
   Spring Kafka listener container
          |
          +---- Record listener: invokes handler per record
          |
          +---- Batch listener: invokes handler with a list of records
```

`poll()` retrieves records from all partitions assigned to the consumer. A single poll can return records from multiple partitions; the record limit is counted across the total result of that poll, not applied separately per partition.

## 2. What does `max.poll.records` limit?

`max.poll.records` is a Kafka consumer property specifying the maximum number of records returned in a single call to `poll()`. The Kafka consumer default is `500`.

For example, a consumer is assigned three partitions and configured with:

```properties
max.poll.records=100
```

A single `poll()` call can return up to 100 records combined across all three partitions. It does not mean each partition returns 100 records. If only 27 records are currently ready, the poll result may contain just 27 records. If no records are ready within the poll wait duration, the result may be empty.

Points to remember:

- This is an upper bound, not a guarantee that every poll returns the full configured count.
- The limit applies per `KafkaConsumer` instance, not as a combined limit across the entire consumer group.
- This value counts records, not bytes, and does not cap record counts per individual partition.
- The Kafka client may have already fetched and buffered data before the application retrieves it via `poll()`. Lowering `max.poll.records` does not mean the broker only sends that exact number of records per fetch request.
- `max.poll.records` does not change a topic's partition count and does not by itself create additional parallelism.

If a consumer group runs multiple consumers, each consumer has its own poll limit. Therefore, total records being processed concurrently in the group can exceed `max.poll.records`, depending on consumer count, assigned partitions, and available data.

## 3. Distinguishing record count from byte-based fetch sizes

Kafka has fetch configurations distinct from `max.poll.records`. Key settings include:

| Property | Meaning |
|---|---|
| `max.poll.records` | Maximum number of records returned to the application in one `poll()` call |
| `max.partition.fetch.bytes` | Data limit fetched per partition in a single fetch request |
| `fetch.max.bytes` | Total data limit a broker returns for a single fetch request |
| `fetch.min.bytes` | Minimum amount of data the consumer wants to receive before the broker answers a fetch, if it can wait |
| `fetch.max.wait.ms` | Maximum time the broker waits to satisfy `fetch.min.bytes` before answering a fetch |

The two groups of settings answer different questions:

- Byte-based fetch settings decide under which size and time bounds the Kafka client pulls data from brokers.
- `max.poll.records` decides at most how many records are handed to the application in one poll.

Thus, setting `max.poll.records=200` does not guarantee every poll delivers 200 records. Fetches may not have pulled enough data yet, partitions may have sparse data, or buffered data may hold fewer ready records than the limit. Conversely, fetches may have buffered more data than the current poll returns; the remainder can be returned in subsequent polls.

Record count also does not accurately reflect memory usage. One hundred small records can be far lighter than one hundred records carrying large payloads. Actual memory also depends on message size, fetched batches, deserialized objects, and temporary data created by the application during processing.

Byte-based fetch limits are also not always absolute boundaries for a single record batch. Kafka can return a first batch larger than the configured limit in certain cases so the consumer can still make forward progress. Therefore, treat fetch values as normal data-throttling bounds and also check the maximum message size permitted by the system.

## 4. How `max.poll.records` relates to Spring Kafka listeners

Spring Kafka uses a listener container to manage `KafkaConsumer`, invoke poll, pass records to listeners, and manage offsets. Two common ways to receive records exist.

### Record listener

With a record listener, the `@KafkaListener` method receives one `ConsumerRecord` at a time. A single poll can retrieve many records, but the container invokes the listener method individually for each record in that result.

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderRecordListener {

    @KafkaListener(topics = "orders.events", groupId = "order-projection")
    public void onEvent(ConsumerRecord<String, String> record) {
        System.out.printf(
                "partition=%d, offset=%d, key=%s%n",
                record.partition(), record.offset(), record.key()
        );

        process(record.value());
    }

    private void process(String payload) {
        // Process a single order event.
    }
}
```

In this mode, `max.poll.records=100` can let the container receive up to 100 records in one poll. The `onEvent` method is still called sequentially for each record by the container's processing mechanism. Therefore, do not interpret this configuration as meaning the listener will receive a 100-element list.

### Batch listener

With a batch listener, the container passes the records received from a single poll as a batch for the listener to process together. This is appropriate when the business layer or backing store supports bulk operations, such as writing multiple records to a database in a single batch insert.

The record listener and batch listener examples here illustrate two alternative implementations. When testing, pick one listener style for that consumption stream; if multiple listeners run concurrently on the same topic and same group ID, they will join the same consumer group and divide partitions via Kafka's assignment mechanism.

You can create a dedicated listener container factory for batch listeners:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
            batchKafkaListenerContainerFactory(
                    ConsumerFactory<String, String> consumerFactory) {

        var factory = new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(true);
        return factory;
    }
}
```

The listener can receive a list of `ConsumerRecord` instances:

```java
import java.util.List;
import java.util.stream.Collectors;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderBatchListener {

    @KafkaListener(
            topics = "orders.events",
            groupId = "order-projection",
            containerFactory = "batchKafkaListenerContainerFactory"
    )
    public void onEvents(List<ConsumerRecord<String, String>> records) {
        if (records.isEmpty()) {
            return;
        }

        for (ConsumerRecord<String, String> record : records) {
            System.out.printf(
                    "partition=%d, offset=%d%n",
                    record.partition(), record.offset()
            );
        }

        processBatch(records.stream()
                .map(ConsumerRecord::value)
                .collect(Collectors.toList()));
    }

    private void processBatch(List<String> payloads) {
        // Process the event batch using an appropriate business operation.
    }
}
```

In this example, `max.poll.records` is the upper limit on how many elements the container can pass in a single batch listener invocation. The actual batch may be smaller than the limit. If the listener needs to know which partition or offset each record came from, receiving `ConsumerRecord` supplies that metadata.

A batch can contain records from multiple partitions assigned to the same consumer. Kafka preserves order within each partition, but the batch list does not impose a global business order across partitions. If processing requires strict ordering per entity, the producer must route that entity's events to the same partition using an appropriate key.

With Spring Boot, you can select the default listener style via `spring.kafka.listener.type=batch`. When configuring record listeners and batch listeners side by side, creating separate container factories and specifying `containerFactory` on each `@KafkaListener` keeps configuration clearer.

## 5. Configuration in Spring Boot

Kafka consumer properties can be configured directly in `application.yml`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-projection
      enable-auto-commit: false
      max-poll-records: 100
      properties:
        "[max.poll.interval.ms]": 300000
    listener:
      type: batch
      ack-mode: batch
```

Meaning of key settings:

- `max-poll-records: 100`: each consumer retrieves at most 100 records in a single poll.
- `max.poll.interval.ms: 300000`: maximum time allowed between two poll calls per Kafka consumer config, here 5 minutes.
- `listener.type: batch`: Spring Boot configures the default listener container in batch mode.
- `listener.ack-mode: batch`: the container commits offsets after finishing the records received from a poll in batch mode.
- `enable-auto-commit: false`: lets Spring Kafka manage offset commits according to container and acknowledgment mode settings.

If the application uses a record listener, omit `listener.type: batch` or set `record`. If a custom container factory is declared in Java, ensure the listener type matches the factory used by the listener. Configuration syntax and supported properties should be cross-checked with the project's Spring Boot/Spring Kafka version.

`AckMode.BATCH` is a common choice for batch processing. Other acknowledgment modes have different commit timings; do not change `max.poll.records` while ignoring how the application commits offsets. If the application uses manual acknowledgment, acknowledge only after the corresponding work has completed according to the application's rules.

## 6. Relationship with `max.poll.interval.ms` and rebalances

`max.poll.interval.ms` specifies the maximum duration a consumer is allowed to go without calling the next `poll()`. If the application processes a batch for too long, the consumer can exceed this duration. Kafka then considers the consumer no longer keeping up with the poll cadence and may put its partitions through a rebalance to hand them to another consumer.

In Spring Kafka, the listener is typically invoked on the consumer-managed thread. While the listener synchronously processes a batch, that thread cannot call poll again. Hence, batch processing duration directly affects the gap between polls.

Suppose a batch listener processes sequentially and each record takes 80 ms on average. If one poll returns 100 records, processing alone can take roughly 8 seconds, excluding database access, external service calls, deserialization, commits, and retry waits. When the record count rises to 500, processing time can grow substantially.

An initial estimate for sequential processing is:

\[
T_{batch} \approx N \times T_{record} + T_{overhead}
\]

Where:

- `N` is the actual number of records in the batch, at most `max.poll.records`.
- `T_record` is the processing time of one record under representative load.
- `T_overhead` includes batch handling time, resource access, retries, and auxiliary tasks.

Ensure batch processing time under heavy load remains below `max.poll.interval.ms` with sensible headroom. Do not configure based on average times alone; account for slow cases such as long database queries, slow downstream services, or repeated retries.

If a consumer exceeds `max.poll.interval.ms`, a rebalance may assign partitions to another consumer while prior work is still unfinished. Depending on commit timing and error handling, records may be reprocessed. Therefore, consumers should be safe against duplicate processing and never commit progress before the corresponding business work completes.

## 7. How to choose read batch size

There is no single optimal `max.poll.records` value for every application. Choose based on payload characteristics, processing time, downstream batch capabilities, and latency requirements.

| Scenario | Initial configuration direction | Reason |
|---|---|---|
| Each event processes quickly and independently | Can try a larger batch | Reduces listener invocation overhead and leverages throughput |
| Processing per record runs slow queries or API calls | Start with a small or medium batch | Keeps processing time per poll within limits |
| Database supports batch insert/update | Try a medium batch then increase gradually | Takes advantage of bulk operations while controlling duration |
| Large payloads or memory-heavy deserialization | Keep the batch smaller | Limits how many large objects coexist during processing |
| Fast response needed per event | Pick a small/medium batch and measure latency | Avoids queuing too much work into a single processing cycle |

A practical tuning workflow:

1. Start with a moderate value, such as `100`, instead of jumping immediately to thousands of records.
2. Measure records per poll, batch processing time, poll wait time, end-to-end latency from producer send to listener handling, and memory usage.
3. Check partition count and active consumer count. Within the same group, each partition at any moment is assigned to at most one consumer; raising concurrency past partition count adds no parallel reading from that topic.
4. Increase or decrease `max.poll.records` incrementally and compare results under production-like load.
5. Inspect processing duration at high percentiles and compare against `max.poll.interval.ms`; leave headroom for traffic spikes or slow dependencies.
6. Verify commits, retries, rebalances, and record reprocessing safety after configuration changes.

If the goal is higher throughput, simply raising `max.poll.records` may not solve the bottleneck. The consumer might be constrained by partition count, business processing time, database speed, network, or byte-based fetch limits. Observe the full record path before concluding the read batch size is the cause.

## 8. Common misconceptions

1. **Treating `max.poll.records` as records per partition.** It is a cap on the total records returned in a single poll of one consumer across all assigned partitions.
2. **Treating the configured value as a guaranteed batch size.** It is only a maximum; actual record count depends on ready data and fetch results.
3. **Treating `max.poll.records` as a byte limit.** Fetch size is governed by fetch configurations; large payloads can still spike memory even at low record counts.
4. **Assuming a record listener receives a list.** Record listeners are invoked once per record; only batch listeners receive a batch of records per invocation.
5. **Increasing batch size without checking `max.poll.interval.ms`.** Large batches lengthen processing time and can trigger rebalances if the consumer fails to poll on time.
6. **Assuming higher concurrency always increases throughput.** A group can only parallelize usefully up to its assigned partition count; excess consumers receive no partitions.
7. **Committing offsets before processing finishes.** If the process stops after committing yet before business work finishes, records may be skipped when reading resumes.

When configuring `max.poll.records`, think of it as bounding the unit of work each consumer pulls in a single poll cycle. Combining this limit with the listener type, processing duration, offset commit strategy, and fetch bounds helps Spring Kafka sustain steady throughput without increasing the risk of unexpected rebalances.
