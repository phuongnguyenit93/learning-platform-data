# Storing Error Metadata and Tracing Original Records

When a Kafka record is routed to a Dead Letter Topic (DLT/DLQ), operations teams need answers to clear questions: which topic did the record come from, which partition and offset, which consumer group failed, when did the error happen, how many times was it retried, and where does the record currently reside? If only a log line like "processing failed" is saved, investigation, reconciliation, and replay become very difficult.

Error metadata must travel with the failed record or be stored in a durable lookup store. With the Spring Cloud Stream Kafka binder, the built-in DLQ mechanism adds headers such as `x-original-topic`, `x-exception-message`, and `x-exception-stacktrace`. With Spring Kafka's `DeadLetterPublishingRecoverer`, the standard DLT header set also includes original partition, offset, timestamp, and consumer group. The two mechanisms have different header sets; you must know which mechanism your application uses so you do not misread headers or infer missing data.

This lesson builds a strategy for storing error metadata, uniquely identifying original records, preserving lineage across multiple retries/replays, and indexing so records can always be traced back.

## 1. Why Is Error Metadata Needed?

A message can fail because its payload violates a schema, breaks a business rule, or encounters a temporarily unavailable dependency. After retries are exhausted, the message may be published to a DLT. If the DLT only contains the payload, operators still lack the information needed to know where the message came from and why it was routed there.

A useful failure record should answer:

- **Origin:** Kafka cluster, topic, partition, offset, timestamp, and original key.
- **Consumption context:** consumer group, binding, application/service, and deployment version.
- **Root cause:** exception class, cause, error code, message, and a bounded stack trace.
- **Business identity:** event ID, event type, correlation ID, causation ID, and trace ID if readable.
- **Processing history:** attempt count, first/last failure timestamps, intermediate topics, and replay count.
- **Current location:** DLT topic, partition, offset, and DLT publish timestamp.
- **Operational state:** newly received, investigating, awaiting fix, replayed, resolved, or moved to parking lot.

Not every field is always available. For example, a deserialization error can happen before the payload becomes a DTO, making an event ID inside JSON unreadable. In that case, preserving raw bytes and Kafka coordinates still enables tracing back to the original record.

## 2. Distinguishing Original Location from DLT Location

A Kafka offset is only meaningful within a single topic-partition. When a record is published to a DLT, it becomes a new record and receives a new offset in the DLT. The DLT offset does not replace the original offset.

~~~text
Original topic: orders.created
  cluster = kafka-prod-a
  partition = 2
  offset = 8451
  key = order-1001
  value = {...}
       |
       | consumer group order-projection failed processing
       v
DLT: orders.created.dlt
  partition = 2          <- may match partition by default
  offset = 197           <- new offset, independent from original topic
  headers = error metadata + origin details
  value = original payload
~~~

Store the two sets of coordinates separately:

| Field | Meaning |
|---|---|
| `originalCluster` | Identifier of the cluster holding the original record |
| `originalTopic` | Original topic |
| `originalPartition` | Original partition |
| `originalOffset` | Original offset |
| `originalTimestamp` | Timestamp of the original record |
| `dltTopic` | Topic currently holding the failed record |
| `dltPartition` | Partition of the record in the DLT |
| `dltOffset` | New offset of the record in the DLT |

Do not infer `originalOffset` from `dltOffset`. Also do not always infer `originalPartition` from the DLT partition: the Kafka binder sends to the same partition number by default, but `DlqPartitionFunction` can select a different partition. If exact tracing is required, record the original partition and offset explicitly in metadata.

A commonly used physical trace key is:

`cluster + originalTopic + originalPartition + originalOffset`

When the same record is processed by multiple consumer groups, include `consumerGroup` in the key to distinguish independent failures. For business tracing, also store a stable event ID; event ID does not replace Kafka coordinates because the same event may be republished at a different topic/offset.

## 3. Default DLQ Headers of the Spring Cloud Stream Kafka Binder

When DLQ is enabled on a consumer binding, the Kafka binder adds the following default headers to failed records:

| Kafka Header | Type | Meaning |
|---|---|---|
| `x-original-topic` | `byte[]` | Original topic name |
| `x-exception-message` | `byte[]` | Exception message |
| `x-exception-stacktrace` | `byte[]` | Error stack trace |

This is the built-in header set of the Spring Cloud Stream Kafka binder. It is not synonymous with Spring Kafka's DLT header set. Under default binder settings, the failed record is sent to the same partition number as the original record; hence the DLT needs enough matching partitions. If the application uses a custom partition resolver, you cannot rely on matching partition numbers to recover the original location.

Example configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder

    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-projection
          consumer:
            max-attempts: 3

      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              enable-dlq: true
              dlq-name: orders.created.dlt
~~~

Points to remember:

- DLQ requires a named consumer group; anonymous consumers cannot use this DLQ mechanism.
- `enable-dlq` enables forwarding failed records to the DLT after retries.
- `max-attempts: 3` is the maximum total processing attempts, consisting of the initial attempt plus two retries.
- `dlq-name` sets the error topic name; if omitted, the binder uses the default name `error.<destination>.<group>`.
- By default, the DLT partition matches the original partition; ensure the DLT has enough partitions.
- If `dlq-partitions` is greater than 1, the binder requires a `DlqPartitionFunction` bean to select the partition.
- When `destination-is-pattern: true` is used, the binder does not support `enable-dlq`.
- If the consumer uses native decoding, configure matching serializers for the DLQ producer in `dlq-producer-properties`.

Property names can be written in kebab-case in YAML or camelCase per the version's binding metadata. Use the exact property names supported by your project's BOM and Spring Cloud Stream version.

## 4. Enabling DLQ and Inspecting Forwarded Records

An illustrative consumer:

~~~java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderConsumerConfiguration {

    @Bean
    Consumer<OrderCreated> processOrder(OrderService service) {
        return event -> service.process(event);
    }

    public record OrderCreated(
        String eventId,
        String orderId,
        long total
    ) {}
}
~~~

If `OrderService.process` throws an exception and exhausts the configured retries, the binder can forward the record to the DLT. When reading the DLT with Kafka console consumer, inspect the headers `x-original-topic`, `x-exception-message`, and `x-exception-stacktrace`.

Example command to read the DLT topic:

~~~bash
bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic orders.created.dlt \
  --from-beginning \
  --property print.key=true \
  --property print.headers=true
~~~

The console consumer gives quick visibility into keys, payloads, and headers. For byte-encoded headers, the tool may display contents as text or escaped bytes depending on its version. For exact investigation, use a small consumer reading `ConsumerRecord` and print header names alongside valid UTF-8 values or hex output.

## 5. Reading Binder Metadata in Spring Cloud Stream

Headers from Kafka are typically mapped into Spring `MessageHeaders`. Header values may be `byte[]` or types converted by a mapper. Do not cast directly without checking first.

Example DLT consumer reading raw payload and the three binder headers:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;

@Configuration
public class DeadLetterInspector {

    @Bean
    Consumer<Message<byte[]>> inspectFailedRecord() {
        return message -> {
            String originalTopic = headerAsText(
                message.getHeaders().get("x-original-topic")
            );

            String exceptionMessage = headerAsText(
                message.getHeaders().get("x-exception-message")
            );

            String stackTrace = headerAsText(
                message.getHeaders().get("x-exception-stacktrace")
            );

            byte[] originalPayload = message.getPayload();

            // Persist metadata and payload reference to the investigation store.
        };
    }

    private static String headerAsText(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof byte[] bytes) {
            return new String(bytes, StandardCharsets.UTF_8);
        }
        return value.toString();
    }
}
~~~

This example uses `Consumer<Message<byte[]>>` to keep the payload as bytes. That is helpful when the original record could not be deserialized into a DTO. If the DLT producer used another serializer or the binder converted the payload to another type, configure the corresponding deserializer/consumer.

Stack traces can be long and expose internal paths, SQL, URLs, or sensitive data inside exception messages. Before storing or displaying them to users, bound their length and mask sensitive data.

## 6. Spring Kafka Has a Richer Set of DLT Headers

When an application configures Spring Kafka's `DeadLetterPublishingRecoverer` directly, DLT records receive a different standard header set. Constants are declared in `KafkaHeaders`:

| Spring Kafka Constant | Information stored |
|---|---|
| `DLT_EXCEPTION_FQCN` | Exception class name |
| `DLT_EXCEPTION_CAUSE_FQCN` | Cause class name if present |
| `DLT_EXCEPTION_MESSAGE` | Error message |
| `DLT_EXCEPTION_STACKTRACE` | Stack trace |
| `DLT_ORIGINAL_TOPIC` | Original topic |
| `DLT_ORIGINAL_PARTITION` | Original partition |
| `DLT_ORIGINAL_OFFSET` | Original offset |
| `DLT_ORIGINAL_TIMESTAMP` | Original timestamp |
| `DLT_ORIGINAL_TIMESTAMP_TYPE` | Original timestamp type |
| `DLT_ORIGINAL_CONSUMER_GROUP` | Failing consumer group |

For key deserialization errors, Spring Kafka also provides a separate `DLT_KEY_EXCEPTION_*` header group. Original headers and exception headers are added per `DeadLetterPublishingRecoverer` semantics.

`DLT_EXCEPTION_CAUSE_FQCN` and `DLT_ORIGINAL_CONSUMER_GROUP` were added in Spring Kafka 2.8. Check the Spring Kafka version managed by your project's BOM before referencing these constants.

Do not confuse Spring Kafka header names with the built-in binder header names:

| Target | Spring Cloud Stream Kafka binder DLQ | Spring Kafka DeadLetterPublishingRecoverer |
|---|---|---|
| Original topic | `x-original-topic` | `KafkaHeaders.DLT_ORIGINAL_TOPIC` |
| Original partition | Not in the default binder header set above | `DLT_ORIGINAL_PARTITION` |
| Original offset | Not in the default binder header set above | `DLT_ORIGINAL_OFFSET` |
| Exception message | `x-exception-message` | `DLT_EXCEPTION_MESSAGE` |
| Stack trace | `x-exception-stacktrace` | `DLT_EXCEPTION_STACKTRACE` |
| Consumer group | Not in the default binder header set above | `DLT_ORIGINAL_CONSUMER_GROUP` |

If you only use the built-in binder DLQ, do not assume the original offset is already in the headers. When full coordinates are required, add metadata via a custom mechanism or use Spring Kafka's custom error handler/Recoverer with clear understanding of retry and acknowledgment boundaries.

## 7. Adding Application Metadata with DeadLetterPublishingRecoverer

Spring Kafka allows adding custom headers via `setHeadersFunction`. The recoverer still creates the standard DLT headers; the function appends application-specific details such as an error code, service version, or event ID if readable from the record.

The example below is for an application directly using Spring Kafka's `DefaultErrorHandler`, not concurrently using binder-managed DLQ configuration:

Place the method in a Spring `@Configuration` class:

~~~java
import java.nio.charset.StandardCharsets;

import org.springframework.context.annotation.Bean;
import org.apache.kafka.common.header.Headers;
import org.apache.kafka.common.header.internals.RecordHeaders;
import org.apache.kafka.common.header.internals.RecordHeader;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.util.backoff.FixedBackOff;

@Bean
DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> template) {

    DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(template);

    recoverer.setHeadersFunction((record, exception) -> {
        Headers headers = new RecordHeaders();

        headers.add(new RecordHeader(
            "failure-code",
            classify(exception).getBytes(StandardCharsets.UTF_8)
        ));

        headers.add(new RecordHeader(
            "failed-service",
            "order-projection".getBytes(StandardCharsets.UTF_8)
        ));

        return headers;
    });

    return new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1000L, 2L)
    );
}

private String classify(Exception exception) {
    if (exception instanceof IllegalArgumentException) {
        return "INVALID_EVENT";
    }
    return "PROCESSING_FAILURE";
}
~~~

`setHeadersFunction` receives the original record and exception and returns additional Kafka headers. The recoverer automatically adds standard DLT headers for original topic, partition, offset, timestamp, and consumer group. To remove or alter headers copied from the original record, subclass `DeadLetterPublishingRecoverer` and customize `createProducerRecord`; the headers function is strictly additive.

Do not simultaneously register binder-managed retry/DLQ and another error handler on the same binding without clearly defining which mechanism owns retries, DLT publishing, and offset commits. Two layers may unexpectedly both publish or acknowledge records.

## 8. Preserving Original Payload on Deserialization Errors

Deserialization errors can occur before the function receives the message. If a consumer only accepts a DTO, application code never gets to inspect the failing payload. To preserve the original record, Kafka consumers commonly wrap the actual deserializer with `ErrorHandlingDeserializer`.

Example native deserialization configuration:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-projection
          consumer:
            use-native-decoding: true

      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              enable-dlq: true
              dlq-name: orders.created.dlt
              configuration:
                key.deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
                value.deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
                spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
                spring.deserializer.value.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
~~~

This configuration illustrates `ErrorHandlingDeserializer` wrapping String deserializers. Choose the delegate matching the original record format and configure corresponding serializers for the DLQ producer. If native decoding is enabled, the binder needs to know how to serialize failed records when publishing to the DLT; otherwise, the error can turn into a DLQ publish failure.

For example, if the DLT producer receives raw `byte[]`, it may need `ByteArraySerializer`; if it receives a String or deserialized DTO, the serializer must match that type. For streams containing both successfully deserialized payloads and raw bytes from deserialization failures, check actual types or use Spring Kafka's multi-`KafkaTemplate` configuration to choose serializers by payload type.

When using `ErrorHandlingDeserializer`, Spring Kafka stores deserialization exception information in internal headers. `DeadLetterPublishingRecoverer` can restore the original payload bytes to publish to the DLT instead of sending only the failed-deserialization null value. Cases where key and value have different deserializers may require multiple matching KafkaTemplates/serializers.

Do not convert raw bytes into a UTF-8 String if the actual payload is Avro, Protobuf, compressed bytes, or other binary data. Store the payload as-is and record the serializer/schema version if identifiable.

## 9. Designing a Durable Failure Record in a Database

A DLT stores failed records and metadata inside Kafka. To search by event ID, processing state, timestamp, or owning team, you can build an indexed table populated from the DLT.

Example schema:

~~~sql
CREATE TABLE kafka_failure_record (
    failure_id           VARCHAR(80) PRIMARY KEY,
    source_cluster       VARCHAR(120) NOT NULL,
    consumer_group       VARCHAR(200),
    original_topic       VARCHAR(249) NOT NULL,
    original_partition   INTEGER,
    original_offset      BIGINT,
    original_timestamp   TIMESTAMP WITH TIME ZONE,
    original_timestamp_type VARCHAR(40),
    original_key         BYTEA,
    event_id             VARCHAR(200),
    correlation_id       VARCHAR(200),
    event_type           VARCHAR(160),
    dlt_cluster          VARCHAR(120) NOT NULL,
    dlt_topic            VARCHAR(249) NOT NULL,
    dlt_partition        INTEGER NOT NULL,
    dlt_offset           BIGINT NOT NULL,
    exception_type       VARCHAR(500),
    exception_cause_type VARCHAR(500),
    error_code           VARCHAR(120),
    error_message        TEXT,
    stack_trace_excerpt  TEXT,
    failed_at            TIMESTAMP WITH TIME ZONE NOT NULL,
    attempt_count        INTEGER,
    origin_metadata_complete BOOLEAN NOT NULL DEFAULT FALSE,
    status               VARCHAR(40) NOT NULL,
    replay_count         INTEGER NOT NULL DEFAULT 0,
    last_replayed_at     TIMESTAMP WITH TIME ZONE,
    payload_reference    TEXT,
    created_at           TIMESTAMP WITH TIME ZONE NOT NULL
);
~~~

When origin coordinates are complete, you can create a unique index on the original record and consumer group:

~~~sql
CREATE UNIQUE INDEX uq_kafka_failure_origin
ON kafka_failure_record (
    source_cluster,
    consumer_group,
    original_topic,
    original_partition,
    original_offset
);
~~~

A unique key on original coordinates reflects a single failure of a logical consumer on an original record. The index above only applies when origin coordinate fields are populated. In PostgreSQL, rows with NULL values in a unique key may not conflict; therefore, add a unique index on the DLT location as well so the indexer never inserts duplicate rows for the same DLT record:

~~~sql
CREATE UNIQUE INDEX uq_kafka_failure_dlt_record
ON kafka_failure_record (
    dlt_cluster,
    dlt_topic,
    dlt_partition,
    dlt_offset
);
~~~

`source_cluster` identifies the cluster holding the original record; `dlt_cluster` identifies the cluster holding the failure record. They may be the same or different. `original_partition` and `original_offset` allow NULL when the DLQ mechanism in use does not supply them; `origin_metadata_complete` indicates whether coordinates are sufficient for physical tracing. `consumer_group` can come from Spring Kafka headers or indexer config; if there is no reliable source, leave it blank rather than guessing from topic names.

`original_key` uses `BYTEA` to preserve the key verbatim even when the key serializer is not UTF-8. If the system strictly uses string keys, an extra decoded display column can be added. `attempt_count` should only be populated when the error handler provides attempt counts; the Kafka binder's default DLQ headers do not include this field automatically.

If the same record enters the DLT multiple times due to retries/replays or manual operations, the indexer can upsert the existing record, increment `attempt_count`, or store history in a child table. If you need to store separate failure occurrences, use `failure_id` per occurrence and keep a separate origin table to group them.

Never use event ID alone as the unique key of a failure record: an event can be republished at another offset, or the same record can fail in multiple consumer groups. Original coordinates plus consumer group pinpoint the exact processing attempt that failed.

## 10. Building an Indexer to Read the DLT and Persist Metadata

The indexer is a separate consumer reading the DLT topic. It translates Kafka headers and metadata into searchable records. This consumer must be idempotent because it too can receive redelivered messages.

~~~java
import java.nio.charset.StandardCharsets;
import java.util.function.Consumer;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;

@Configuration
public class FailureIndexConsumer {

    @Bean
    Consumer<Message<byte[]>> indexFailure(
            FailureRecordRepository repository,
            @Value("${app.kafka.source-cluster}") String sourceCluster,
            @Value("${app.kafka.dlt-cluster}") String dltCluster,
            @Value("${app.failure.original-consumer-group:}") String configuredGroup) {

        return message -> {
            String originalTopic = text(
                message.getHeaders().get("x-original-topic")
            );
            if (originalTopic == null) {
                originalTopic = text(message.getHeaders()
                    .get(KafkaHeaders.DLT_ORIGINAL_TOPIC));
            }
            String errorMessage = text(
                message.getHeaders().get("x-exception-message")
            );
            if (errorMessage == null) {
                errorMessage = text(message.getHeaders()
                    .get(KafkaHeaders.DLT_EXCEPTION_MESSAGE));
            }
            String stackTrace = text(
                message.getHeaders().get("x-exception-stacktrace")
            );
            if (stackTrace == null) {
                stackTrace = text(message.getHeaders()
                    .get(KafkaHeaders.DLT_EXCEPTION_STACKTRACE));
            }
            String exceptionType = text(message.getHeaders()
                .get(KafkaHeaders.DLT_EXCEPTION_FQCN));
            String exceptionCauseType = text(message.getHeaders()
                .get(KafkaHeaders.DLT_EXCEPTION_CAUSE_FQCN));
            String errorCode = text(message.getHeaders().get("failure-code"));
            String eventId = text(message.getHeaders().get("event-id"));
            String correlationId = text(
                message.getHeaders().get("correlation-id")
            );
            String eventType = text(message.getHeaders().get("event-type"));

            String dltTopic = message.getHeaders()
                .get(KafkaHeaders.RECEIVED_TOPIC, String.class);
            Integer dltPartition = message.getHeaders()
                .get(KafkaHeaders.RECEIVED_PARTITION, Integer.class);
            Long dltOffset = message.getHeaders()
                .get(KafkaHeaders.OFFSET, Long.class);
            Long dltTimestamp = message.getHeaders()
                .get(KafkaHeaders.RECEIVED_TIMESTAMP, Long.class);

            // DLT_ORIGINAL_* fields are present when records are created by
            // Spring Kafka DeadLetterPublishingRecoverer; default binder DLQ
            // does not add original partition/offset.
            Integer originalPartition = message.getHeaders()
                .get(KafkaHeaders.DLT_ORIGINAL_PARTITION, Integer.class);
            Long originalOffset = message.getHeaders()
                .get(KafkaHeaders.DLT_ORIGINAL_OFFSET, Long.class);
            Long originalTimestamp = message.getHeaders()
                .get(KafkaHeaders.DLT_ORIGINAL_TIMESTAMP, Long.class);
            String originalTimestampType = text(message.getHeaders()
                .get(KafkaHeaders.DLT_ORIGINAL_TIMESTAMP_TYPE));
            String originalGroup = text(message.getHeaders()
                .get(KafkaHeaders.DLT_ORIGINAL_CONSUMER_GROUP));
            if (originalGroup == null || originalGroup.isBlank()) {
                originalGroup = configuredGroup.isBlank() ? null : configuredGroup;
            }
            byte[] dltKey = keyBytes(
                message.getHeaders().get(KafkaHeaders.RECEIVED_KEY)
            );

            // With the default binder, original partition/offset are not part
            // of the x-original-topic/x-exception-* set.
            // Custom DLT headers or recoverer are needed if storing them is mandatory.

            repository.upsertFromDlq(
                sourceCluster,
                dltCluster,
                originalTopic,
                originalPartition,
                originalOffset,
                originalTimestamp,
                originalTimestampType,
                originalGroup,
                eventId,
                correlationId,
                eventType,
                exceptionType,
                exceptionCauseType,
                errorCode,
                errorMessage,
                stackTrace,
                dltTopic,
                dltPartition,
                dltOffset,
                dltTimestamp,
                dltKey,
                message.getPayload()
            );
        };
    }

    private static String text(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof byte[] bytes) {
            return new String(bytes, StandardCharsets.UTF_8);
        }
        return value.toString();
    }

    private static byte[] keyBytes(Object value) {
        if (value instanceof byte[] bytes) {
            return bytes;
        }
        if (value instanceof String text) {
            return text.getBytes(StandardCharsets.UTF_8);
        }
        return null; // For other key types, use the matching serializer/adapter.
    }
}
~~~

This snippet is an illustrative skeleton; `FailureRecordRepository` should also receive original coordinates and DLT record metadata if the corresponding headers are configured. Do not mark a record as "complete" if original partition/offset fields were not supplied. Mark those fields absent or supply them via a custom recoverer.

`KafkaHeaders.RECEIVED_PARTITION` and `RECEIVED_KEY` are in newer Spring Kafka versions; in older versions, the corresponding names may be `RECEIVED_PARTITION_ID` and `RECEIVED_MESSAGE_KEY`. `DLT_ORIGINAL_CONSUMER_GROUP` was introduced in Spring Kafka 2.8. Check your BOM before choosing constants. If the binder mapper returns the key as another Java type, use the matching serializer/adapter instead of casting to bytes arbitrarily.

The indexer should use a unique key per DLT record and upsert. If the indexer commits to the database before committing the Kafka offset, it will receive the exact same DLT record again; the DLT unique index prevents duplicate rows. When full origin coordinates exist, the origin unique index also helps group redeliveries of the same record. If database index and offset must stay consistent, use an appropriate transaction/offset strategy and test failure windows.

## 11. Preserving Error History Across Multiple Retries and Replays

A record can pass through multiple topics: the original topic, retry topics, DLT, parking lot, and replay topics. Distinguish among:

- **Origin:** where the record was first produced on the original topic.
- **Current location:** current topic/partition/offset.
- **Failure history:** failed processing attempts and their exceptions.
- **Replay history:** who requested replay, when, from where, and for what reason.

Do not overwrite origin with intermediate topics on every replay. You can maintain separate headers:

| Header | Purpose |
|---|---|
| `x-origin-topic` | First topic |
| `x-origin-partition` | First partition |
| `x-origin-offset` | First offset |
| `x-current-attempt` | Current attempt count |
| `x-replay-id` | ID of the replay action |
| `x-replayed-at` | Replay timestamp |
| `x-replayed-by` | Actor or service initiating replay |
| `x-last-failure-code` | Most recent error code |

If a record is forwarded multiple times, do not keep appending the same stack trace to headers indefinitely. Kafka permits duplicate header names, but record sizes are bounded; Spring Kafka also notes that repeated exception headers can bloat records and cause publish failures. Keep detailed history in databases/logs/traces, while headers carry origin and the latest state or a replay ID.

Spring Kafka's `DeadLetterPublishingRecoverer` supports policies for appending original headers and stripping stale exception headers per configuration. If you need to modify copied headers, override `createProducerRecord`; do not just keep adding new headers while letting stale data grow endlessly.

## 12. Tracing Business Events and Distributed Traces

Kafka coordinates locate the physical record. Event ID and trace context track the business journey across services.

~~~text
HTTP request
    |
    v
orders-api
  eventId = evt-9001
  correlationId = corr-9001
  traceparent = 00-...
    |
    v
orders.created (partition 1, offset 400)
    |
    v
inventory-projection
    |
    +---- error while updating inventory
    |
    v
orders.created.dlt (partition 1, offset 88)
    |
    v
failure-indexer
  store origin + error + DLT location
~~~

Store these together when available:

- `eventId`: stable business event identifier.
- `correlationId`: links events across a workflow.
- `causationId`: identifies the message/command that caused the event.
- `traceparent`: W3C Trace Context.
- `consumerGroup`: the failing consumption task.
- `cluster/topic/partition/offset`: physical record location.

Do not use correlation ID as a unique key: multiple events in one workflow can share a correlation ID. Do not use trace ID in place of event ID. If a deserialization error prevents reading the payload or business headers, still persist Kafka coordinates and DLT metadata so the raw record can be investigated.

## 13. Controlled Replay and Parking Lot

Not every DLT record should be resent immediately. Transient errors can be replayed after dependencies recover; permanent schema or data errors require fixing contracts/payloads first. Resending failed records back to the original topic without limits can create an infinite loop.

An operational workflow may include:

1. Indexer records the DLT record and metadata.
2. Operators classify the failure and inspect origin and payload.
3. Fix the dependency, schema, or data.
4. Create a replay request with `replayId`, actor, and reason.
5. Replay the exact payload/key to the target topic per policy.
6. Preserve the event ID and origin coordinates; increment replay count.
7. Consumer processes idempotently; indexer updates status.
8. If replay limits are exceeded, move to a parking lot for manual resolution.

Example replay headers:

~~~java
import java.time.Instant;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<byte[]> replay = MessageBuilder
    .withPayload(originalPayload)
    .setHeader("x-origin-topic", originalTopic)
    .setHeader("x-origin-partition", originalPartition)
    .setHeader("x-origin-offset", originalOffset)
    .setHeader("x-replay-id", replayId)
    .setHeader("x-replay-count", replayCount + 1)
    .setHeader("x-replayed-at", Instant.now().toString())
    .build();
~~~

This is illustrative metadata for a replay application; map it to Kafka headers and preserve the original key when publishing. Do not assume `StreamBridge.send` returning true means the broker durably persisted the message. When publish confirmation is required, use the binder's producer confirmation mechanism and record replay status only after a verifiable result.

Spring Cloud Stream does not provide a single generic DLT workflow for every business domain. Applications must build their own consumer/replay workflow and avoid running replay concurrently with the primary retry stream in ways that exhaust retries or create loops.

## 14. Security and Metadata Size Limits

Error metadata often contains more sensitive details than normal events. Stack traces can expose internal packages, SQL, URLs, table names, request data, or file paths.

- Never store access tokens, passwords, cookies, or secrets in headers.
- Mask personal data and sensitive payloads before logging or displaying in dashboards.
- Bound the length of exception messages and stack traces.
- Store raw payloads in an access-controlled store if records are too large.
- Use payload references/checksums when storing payloads outside Kafka.
- Restrict DLT read access since it may hold malformed or personal data.
- Configure retention on DLTs and metadata tables according to business requirements.
- Record actor and reason on manual replays.
- Never expose public or unauthenticated replay endpoints.

If a stack trace is too long, store a truncated excerpt in headers and keep the full version in centralized logs keyed by correlation/failure ID. Headers only need enough context to locate the detailed failure record.

## 15. Testing Traceability

Tests must not stop at confirming a record appeared in the DLT. Verify that enough metadata survives to trace back to the original record.

| Scenario | Expected verification |
|---|---|
| Function throws exception after deserialization | DLT contains payload, key, and exception metadata |
| JSON fails deserialization | Raw payload is preserved per deserializer/recoverer configuration |
| Binder default DLQ | Has `x-original-topic`, `x-exception-message`, `x-exception-stacktrace` |
| Spring Kafka recoverer | Has original topic/partition/offset/timestamp/group headers |
| DLT partition differs from original partition | Metadata still points to the exact original partition |
| Same record fails in two consumer groups | Failure records are distinguished by group |
| Indexer receives DLT twice | Upsert does not create duplicate records |
| Replayed record | Origin remains unchanged; replay ID/count increment |
| Overly long stack trace | Truncated or offloaded to external store |
| Binary payload | Raw bytes are not corrupted by wrong encoding conversions |
| Record missing event ID | Still traceable via cluster/topic/partition/offset |

With Testcontainers Kafka, create the original topic and DLT, send a record, make the consumer throw an exception, and read the record from the DLT. Inspect keys, payload bytes, header names, and header values. Run a separate deserialization failure test to verify ErrorHandlingDeserializer preserves the original record.

Also test failure windows: DLT publish succeeds, but the indexer stops before committing its offset. When the indexer restarts, it may re-read the record; unique keys/upserts must prevent duplicate metadata.

## 16. Pre-Production Checklist

| Item | Question to answer |
|---|---|
| DLT config | Which bindings enable DLQ, and which group owns each? |
| DLT partitioning | Are there enough partitions? Is there a custom resolver/function? |
| Origin coordinates | Are original cluster, topic, partition, offset, and timestamp stored? |
| Consumer context | Are consumer group, binding, and application version captured? |
| Error metadata | Are error code, exception class/message, and bounded stack trace captured? |
| Raw payload | Are raw bytes preserved when deserialization fails? |
| Business trace | Are event ID, correlation ID, causation ID, and traceparent captured? |
| Metadata index | Is there a unique key and idempotent upsert? |
| Replay | Are replay ID, actor, reason, attempt limits, and parking lot in place? |
| Security | Do the DLT, stack traces, and payloads have proper access controls/retention? |
| Observability | Are DLT count, oldest age, replay count, and failure type metrics present? |
| Version | Have Spring Cloud Stream, Spring Kafka, kafka-clients, and broker versions been recorded? |

## 17. Practice Sequence and Completion Criteria

Run the exercise with `orders.created`:

1. Create consumer group `order-projection` and enable DLQ on the binding.
2. Send one valid record and one record that triggers an exception.
3. Read the DLT and verify payload, key, and the three default Kafka binder headers.
4. Use a consumer reading the DLT as `Message<byte[]>` and decode metadata safely.
5. Compare binder headers with Spring Kafka `DeadLetterPublishingRecoverer`'s standard header set.
6. Design the origin key `cluster + group + topic + partition + offset`.
7. Create the `kafka_failure_record` table and unique indices.
8. Write an indexer that upserts metadata; resend the same DLT record to verify idempotency.
9. Simulate a deserialization failure and confirm raw bytes are preserved.
10. Create a replay request with replay ID, actor, timestamp, and attempt limit.
11. Route unfixable records to a parking lot.
12. Verify dashboards/metrics can trace from failure ID back to the DLT record and original record.

The lesson is complete when you can pinpoint the exact original record from metadata; distinguish original offset from DLT offset; explain header differences between the Kafka binder and Spring Kafka's recoverer; persist durable failure records; and perform controlled replays without losing origin history.

## 18. Official References

- [Spring Cloud Stream Kafka Binder — Retry and Dead Letter Processing](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-kafka.html) — enabling DLQ, default headers, partition selection, and failed record handling.
- [Spring Cloud Stream Kafka Binder — Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html) — `enableDlq`, `dlqName`, `dlqPartitions`, and `dlqProducerProperties`.
- [Spring Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html) — `DeadLetterPublishingRecoverer`, DLT headers, headers function, and header management during replay.
- [Spring Kafka — ErrorHandlingDeserializer](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html) — preserving deserialization error details and recovering original payloads.
- [Apache Kafka — ConsumerRecord API](https://kafka.apache.org/40/javadoc/org/apache/kafka/clients/consumer/ConsumerRecord.html) — record topic, partition, offset, timestamp, key, value, and headers.
