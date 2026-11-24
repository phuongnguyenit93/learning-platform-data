# Handling RecordTooLarge

`RecordTooLarge` occurs when a Kafka record or record batch exceeds the size limit accepted by a component along the path. In producer operations, the error typically appears when an application sends an event larger than the limit configured on the Kafka producer or broker/topic. In other cases, the producer succeeds, yet the consumer cannot fetch the batch because its fetch settings are not large enough.

The proper fix is to identify which component rejected the record, measure the serialized size, and reconcile limits across the entire pipeline: producer, broker/topic, replication, and consumer. Increasing a single property alone may simply shift the failure to the next component.

## 1. What does RecordTooLarge mean?

Kafka transfers data in record batches. A record can contain a key, value, headers, and metadata; the producer can group multiple records into a batch and compress the batch before sending. Consequently, the original JSON or object size does not always equal the request or batch size that Kafka validates.

In a typical producer pipeline:

```text
Application
  |
  v
Serializer + headers
  |
  v
Kafka producer: max.request.size
  |
  v
Broker / topic: message.max.bytes / max.message.bytes
  |
  v
Replication: replica.fetch.max.bytes
  |
  v
Consumer: max.partition.fetch.bytes / fetch.max.bytes
```

The limits serve distinct roles:

| Property | Component | Role |
|---|---|---|
| `max.request.size` | Kafka producer client | Limits producer request size; also effectively limits the uncompressed record batch size the producer can send |
| `message.max.bytes` | Kafka broker | Default limit for record batch size accepted by the broker |
| `max.message.bytes` | Kafka topic | Record batch size limit for a topic; can override the broker default |
| `replica.fetch.max.bytes` | Broker replication | Limits data a replica fetches from each partition in a single fetch |
| `max.partition.fetch.bytes` | Kafka consumer client | Limits maximum data fetched from a single partition per fetch |
| `fetch.max.bytes` | Kafka consumer client | Limits total data returned for a single fetch request |

Fetch properties have a progress guarantee exception: Kafka may return the first batch of a non-empty partition even if that batch exceeds configured fetch limits. However, do not rely on this exception as a substitute for configuring appropriate fetch sizes.

### Commonly confused properties

- `batch.size` is the target size of a producer batch per partition. It is not the maximum size limit of a single record.
- `buffer.memory` is the producer buffer capacity used to hold records waiting to be sent. It does not make an oversized record valid.
- `compression.type` selects how batches are compressed. Compression can reduce network bytes and compressed batch size, but should not be treated as a guaranteed fix for records exceeding producer limits. `max.request.size` also acts as an effective limit on uncompressed batches.
- Raising consumer limits does not help the broker accept a batch rejected at the produce stage.
- Raising broker/topic limits does not help the producer send a record that already exceeds `max.request.size`.

## 2. Locating where the error occurred

Before changing any configuration, determine exactly which component threw the exception and the actual record size.

### 2.1. Inspecting the root exception

In a Spring Kafka application, send errors may be wrapped by Spring exceptions or future classes. Walk the entire cause chain to find the root exception, such as `org.apache.kafka.common.errors.RecordTooLargeException`.

Capture operational context:

- Target topic and partition if known.
- Producer client ID and application version.
- Event type or schema version.
- Serialized size of key, value, and total headers.
- Name of the effective limit configuration.
- Timestamp, failure count, and involved broker if provided by the exception.

Never log the entire payload for diagnostics. Payloads may contain personal data or secrets, and logging large payloads increases I/O load and storage costs.

### 2.2. Measuring size after serialization

Measure the byte length after the serializer converts the object into transmitted bytes. For JSON, character string length before encoding does not necessarily equal UTF-8 byte count. Keys and headers also contribute to record size.

For example, if the producer uses `KafkaTemplate<String, byte[]>`:

```java
byte[] payload = objectMapper.writeValueAsBytes(event);

log.info(
    "Preparing Kafka event: topic={}, eventType={}, payloadBytes={}",
    topic,
    event.getClass().getSimpleName(),
    payload.length
);

kafkaTemplate.send(topic, event.id(), payload);
```

This measures the value. When exact record size is needed, measure the key, headers, and encoding/batch overhead as well. Use this measurement for comparison against configuration rather than treating `payload.length` as the complete request size.

### 2.3. Distinguishing a single oversized record from an oversized batch/request

Consider two situations:

- **Single oversized record:** one individual event already exceeds the producer or broker/topic limit. Reducing `batch.size` usually will not solve this.
- **Multiple records grouped into a batch/request:** individual records may be valid, yet the combined batch or request still exceeds the limit. In that case, inspect partition count, send rate, batching, compression, and `max.request.size`.

If only one event type fails, inspect its schema, unusually large fields, sudden spikes in list element counts, or content embedded directly inside the payload.

### 2.4. Checking effective configuration

Inspect the running application's producer configuration, the cluster's topic configuration, and broker configuration. Do not just read YAML files or `server.properties`: environment configs, environment variables, Spring profiles, and topic overrides can make effective values differ from what you are viewing.

| Symptom | First place to check |
|---|---|
| Producer reports record exceeds limit before sending | `max.request.size` and post-serialization size |
| Broker returns error upon receiving batch | `message.max.bytes` and topic `max.message.bytes` |
| Producer succeeds but consumer fails while reading | `max.partition.fetch.bytes`, `fetch.max.bytes`, and broker batch limits |
| Error appears after increasing topic size limit | Replica fetch, consumer fetch, and compatibility across all consumers |
| Only one event type fails | Serializer, headers, schema, and that event's size |
| Error appears only under increased load | Batching, request size, partition count, and producer config |

## 3. Catching send errors in Spring Kafka

In Spring Kafka 3.x, `KafkaTemplate.send()` returns `CompletableFuture<SendResult<K, V>>`. The producer sends asynchronously, so `send()` returning does not mean the broker confirmed the write. The application must observe the future result.

The example below illustrates catching send errors and logging useful metadata:

```java
import java.util.concurrent.CompletableFuture;

import org.apache.kafka.common.errors.RecordTooLargeException;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, byte[]> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, byte[]> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, byte[]>> publish(
            String topic,
            String eventId,
            byte[] payload) {

        CompletableFuture<SendResult<String, byte[]>> future =
            kafkaTemplate.send(topic, eventId, payload);

        future.whenComplete((result, error) -> {
            if (error == null) {
                return;
            }

            Throwable cause = rootCause(error);

            if (cause instanceof RecordTooLargeException) {
                // Log metadata and route to the designed oversize handling flow.
                // Do not infinitely retry the same payload.
                System.err.printf(
                    "Kafka record too large: topic=%s, eventId=%s, bytes=%d%n",
                    topic,
                    eventId,
                    payload.length
                );
                return;
            }

            // Handle other send errors per corresponding policy.
            System.err.printf(
                "Kafka send failed: topic=%s, eventId=%s, cause=%s%n",
                topic,
                eventId,
                cause.getClass().getSimpleName()
            );
        });

        return future;
    }

    private static Throwable rootCause(Throwable error) {
        Throwable current = error;

        while (current.getCause() != null
                && current.getCause() != current) {
            current = current.getCause();
        }

        return current;
    }
}
```

This snippet is an example for Spring Kafka 3.x and illustrates error observation. In real applications, use a logger and a handler capable of persisting or routing events per business policy. If using older Spring Kafka versions, future and callback types may differ; check the API of your running version.

Never swallow the exception and return success to the caller. If sending the event is required to complete the business operation, propagate the failure to the caller or store the event in a durable mechanism for later handling. If the producer only emits auxiliary events, explicitly define what level of event loss is acceptable.

## 4. Choosing a remediation approach

There are two main approaches: reduce event size or increase limits in a controlled manner across all required components. Prioritize reviewing payload design before raising cluster-wide limits.

### 4.1. Reducing payload size

Check whether the event carries data that consumers do not actually need:

- Send only fields required by consumers.
- Avoid embedding images, PDFs, file attachments, or large binary blobs in messages.
- Avoid duplicating data that can already be looked up by ID.
- Bound collection sizes and text field lengths.
- Review headers to avoid attaching large or redundant metadata to every record.
- Use compact schemas and appropriate serialization formats.

For large content, it is usually better to store the content in object storage or a dedicated file store, then send a small event containing a reference:

```json
{
  "eventId": "evt-12345",
  "eventType": "document.created",
  "documentId": "doc-987",
  "objectKey": "documents/2026/11/doc-987",
  "contentType": "application/pdf",
  "contentLength": 18432000,
  "checksum": "sha256:..."
}
```

Consumers use `objectKey` to fetch the content and verify the checksum. This design must address access permissions, object retention, deletion lifecycle, the possibility that the object is not yet available when the event arrives, and event reprocessing. Never put URLs containing credentials or long-lived access tokens inside Kafka messages.

### 4.2. Using compression for the right purpose

The producer supports compression codecs such as gzip, snappy, lz4, and zstd depending on the Kafka client and broker versions. Example configuration:

```yaml
spring:
  kafka:
    producer:
      properties:
        "[compression.type]": zstd
```

Compression works well for repetitive payloads or large text. Already compressed data or high-entropy data may shrink very little. Compression also consumes CPU and can affect latency.

Measure sizes before and after compression using realistic workloads. If a single record already exceeds the producer's uncompressed limit, enabling compression alone may still fail to resolve `max.request.size` errors.

### 4.3. Raising producer limits when large size is valid

If large events are an intentional business requirement, configure `max.request.size` on the producer. The example below sets a 5 MiB limit:

```yaml
spring:
  kafka:
    producer:
      properties:
        "[max.request.size]": 5242880
```

The value in the example is 5 × 1024 × 1024 bytes. Choose the value based on the largest measured size, accounting for key, headers, and overhead. Set the business event size cap lower than the technical limit to leave headroom.

Spring Boot binds Kafka client properties through the `spring.kafka.producer.properties` map. Square brackets preserve dotted property names in YAML.

### 4.4. Aligning broker and topic limits

The broker uses `message.max.bytes` as the default limit for record batches. A topic can set `max.message.bytes` to override that limit.

Example in broker configuration:

```properties
message.max.bytes=5242880
replica.fetch.max.bytes=6291456
```

Example altering the limit for a single topic using Kafka CLI:

```bash
kafka-configs.sh \
  --bootstrap-server kafka-1:9092 \
  --entity-type topics \
  --entity-name orders.created \
  --alter \
  --add-config max.message.bytes=5242880
```

After changing it, verify the effective topic configuration:

```bash
kafka-configs.sh \
  --bootstrap-server kafka-1:9092 \
  --entity-type topics \
  --entity-name orders.created \
  --describe
```

CLI syntax and how broker configs are applied may vary by Kafka version and cluster management tooling. For managed Kafka clusters, apply changes through the platform's supported configuration mechanism.

`replica.fetch.max.bytes` must be reviewed alongside batch limits so follower brokers can fetch and replicate large batches. Kafka has a mechanism to return a first batch larger than the fetch limit to guarantee progress, yet sizing replication fetch adequately still keeps behavior predictable and stable.

### 4.5. Aligning consumer limits

Consumers must be able to fetch the batches permitted by the topic. In Spring Boot you can configure:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[max.partition.fetch.bytes]": 6291456
        "[fetch.max.bytes]": 16777216
```

The example sets a 6 MiB per-partition limit and a 16 MiB total fetch response limit. Adjust according to the number of partitions fetched concurrently, batch size, consumer count, and application memory budget.

Not all consumers are Spring applications. Check consumers written with the plain Kafka client, Kafka Connect, Kafka Streams, and consumer services managed by other teams before raising topic limits. A producer succeeding does not mean every consumer is ready to receive large batches.

### 4.6. Example of a synchronized configuration set

Suppose the largest allowed event at the business layer is around 4 MiB. An illustrative set of values could be:

| Component | Illustrative value | Purpose |
|---|---:|---|
| Business event size limit | 4 MiB | Reject abnormal payloads early |
| Producer `max.request.size` | 5 MiB | Provide headroom for batch/request |
| Broker `message.max.bytes` | 5 MiB | Accept batches per cluster policy |
| Topic `max.message.bytes` | 5 MiB | Topic-specific limit |
| Broker `replica.fetch.max.bytes` | 6 MiB | Allow replicas to fetch large batches |
| Consumer `max.partition.fetch.bytes` | 6 MiB | Fetch batches from a single partition |
| Consumer `fetch.max.bytes` | 16 MiB | Cap total fetch response |

These are illustrative numbers, not defaults for every cluster. Values must be validated against your Kafka version, compression, actual batch sizes, partition counts, consumer counts, and resource limits. Do not copy these numbers if your workload has different requirements.

## 5. Do not infinitely retry RecordTooLarge errors

`RecordTooLarge` is usually a configuration or data-limit error rather than a transient issue like a lost broker connection. Re-sending the exact same record with the same payload and configuration will usually fail again.

Your handling policy should classify:

| Error type | Handling approach |
|---|---|
| Valid record but producer limit configured too low | Adjust producer after verifying end-to-end limits |
| Valid record but broker/topic rejects it | Adjust broker/topic limits and affected consumers |
| Payload exceeds business limit | Reject event, fix source data, or move large content to object storage |
| Serializer produces abnormally large payload | Fix schema, serializer, or input data |
| Transient network or broker error | Retry with backoff and limits per send policy |

For producers, a dead-letter topic does not automatically solve oversized records. If the payload itself cannot be written to Kafka, sending that same payload to a DLT can hit the exact same error. You can persist the payload to durable storage and emit a small quarantine message containing event ID, object key, checksum, target topic, and failure reason. This workflow requires clear access controls and retention policies.

If the event originates from a business transaction, ensure send failures do not lose track of the event. The outbox pattern can persist the event in the database within the business transaction, after which a publisher handles sending and status tracking. Even with an outbox, oversized records must still be classified and handled; the outbox only preserves the work item so events are not lost.

## 6. Operational impact of increasing limits

Raising size limits can increase resource demand across the entire system:

- **Heap and memory:** producers, brokers, and consumers may need to retain larger batches in memory. Many partitions or concurrent requests accelerate memory growth.
- **Network:** larger requests and responses increase bandwidth usage, transfer time, and sensitivity to network glitches.
- **Replication:** followers must fetch and write larger batches; replication latency may rise.
- **Consumer latency:** deserializing and processing large payloads consumes CPU, memory, and time. Review `max.poll.interval.ms` if processing takes longer.
- **Retries and replay:** large messages re-sent multiple times amplify network load and storage usage.
- **Observability:** logging large payloads can inflate costs; log size, event type, and event ID instead of full contents.

Higher limits also magnify the blast radius of a producer sending abnormal payloads. Enforce size limits at the API or domain layer, collect event-size distribution metrics, and alert when payloads approach thresholds.

## 7. Safe rollout procedure for limit changes

When limits must be raised, follow this sequence:

1. Gather the root exception, post-serialization size, topic, producer client ID, and current configs.
2. Confirm large events are valid and that consumers genuinely need the full payload.
3. Check limits on producer, broker, topic, replication, and every consumer reading the topic.
4. Pick a maximum business limit; set technical limits with appropriate headroom.
5. Test in staging with near-limit payloads, over-limit payloads, and concurrent load.
6. Confirm producers receive acknowledgements, consumers fetch and deserialize successfully, and replication stays stable.
7. Monitor send error rate, record size, request latency, consumer lag, broker request metrics, heap, and replication lag after rollout.
8. Document the new config, topic/broker scope, owner, and rollback procedure.

When changing topic limits, inspect older consumers and related connectors. If all consumers cannot be upgraded or reconfigured, keep payloads below the lowest common limit or offload large content outside Kafka.

## 8. Quick diagnostic checklist

- [ ] Root exception and failing component have been identified.
- [ ] Post-serializer bytes have been measured, including key and headers.
- [ ] Single oversized record vs. oversized batch/request have been distinguished.
- [ ] Running producer's `max.request.size` has been checked.
- [ ] Broker `message.max.bytes` and topic `max.message.bytes` have been checked.
- [ ] `replica.fetch.max.bytes` has been checked if batch limits were raised.
- [ ] Consumer `max.partition.fetch.bytes` and `fetch.max.bytes` have been checked.
- [ ] Every consumer, connector, and downstream app is verified to read the new batch size.
- [ ] Near-limit, over-limit, and concurrent load scenarios have been tested.
- [ ] Policy exists for over-limit events without infinite retries.
- [ ] Metrics and alerts are set up for event sizes and send error rates.

## 9. Operational principles

Treat `RecordTooLarge` as a signal to review both the data contract and technical limits. If an event carries large content while consumers only need identifiers or metadata, move the content to object storage and send a reference over Kafka. If large sizes are a genuine business requirement, raise limits in a controlled manner and align producer, broker, topic, replication, and consumers together.

In all cases, enforce size limits at the business layer, monitor post-serialization event sizes, and test the full path from producer to consumer. Doing so surfaces errors early, avoids pointless retries, and prevents a configuration change from triggering a downstream incident.

