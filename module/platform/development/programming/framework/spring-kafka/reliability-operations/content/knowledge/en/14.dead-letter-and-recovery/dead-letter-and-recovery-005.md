# Preserving Original Topic and Offset

When a Kafka record fails after processing attempts or retries, a Spring Kafka application often sends it to a **dead-letter topic (DLT)** for later investigation and reprocessing. A record in the DLT receives a new offset in a new topic; if you only look at the current topic and offset, operators can no longer tell where the failed record originated. Therefore, you must preserve the **original topic**, **original partition**, and **original offset** along with related details as metadata.

In Spring Kafka, **DeadLetterPublishingRecoverer** can add headers describing the source record and the exception when publishing to the DLT. These headers assist incident tracing, locating the original record, distinguishing retry stages, and supporting controlled replay. However, tracing metadata does not automatically provide an exactly-once guarantee and does not replace a business event ID.

## 1. Why can't you just use the current topic and offset?

Kafka splits data into independent logs by topic and partition. An offset is a position within **a specific partition's** log, not a cluster-wide sequence number. When a record is sent to another topic, the broker assigns a new offset in the destination topic.

Example:

~~~text
Topic orders
  partition 3, offset 1254
          |
          | listener fails
          v
Topic orders-retry-1000
  partition 3, offset 87
          |
          | retry still fails
          v
Topic orders.DLT
  partition 3, offset 12
~~~

The three offsets 1254, 87, and 12 are simply positions in three separate logs. You cannot conclude that offset 12 on orders.DLT corresponds to offset 12 on orders, nor use offset 87 from the retry topic to seek directly on the original topic.

A complete Kafka location identifier needs at least:

~~~text
(topic, partition, offset)

Example:
  (orders, 3, 1254)       -- original record position
  (orders.DLT, 3, 12)     -- record position on DLT
~~~

When tracing from the DLT back to the original record, the application must retain the source tuple and distinguish it from the current DLT record's tuple.

## 2. What does original metadata include?

With Spring Kafka's DeadLetterPublishingRecoverer, commonly used headers for storing source information include:

| Spring Kafka Header | Meaning | Typical data format |
|---|---|---|
| **KafkaHeaders.DLT_ORIGINAL_TOPIC** | Topic of the record recorded as the source in the recovery flow | UTF-8 string |
| **KafkaHeaders.DLT_ORIGINAL_PARTITION** | Source partition | 32-bit integer as bytes |
| **KafkaHeaders.DLT_ORIGINAL_OFFSET** | Source offset | 64-bit integer as bytes |
| **KafkaHeaders.DLT_ORIGINAL_TIMESTAMP** | Timestamp of the source record | 64-bit integer as bytes |
| **KafkaHeaders.DLT_ORIGINAL_TIMESTAMP_TYPE** | Source timestamp type such as CREATE_TIME or LOG_APPEND_TIME | Metadata represented as bytes |
| **KafkaHeaders.DLT_EXCEPTION_FQCN** | Class name of the exception recorded during recovery | String |
| **KafkaHeaders.DLT_EXCEPTION_MESSAGE** | Exception message when provided | String |
| **KafkaHeaders.DLT_EXCEPTION_STACKTRACE** | Stack trace for investigation when enabled/provided | String, potentially long |

Depending on the Spring Kafka version and how the recoverer is built, headers for consumer group, exception cause, or additional metadata may also be present. Do not assume all listed headers are always present or that their names/behaviors are identical across every version. Rely on the constants and APIs of your exact Spring Kafka dependency.

Specifically:

- **Original topic** is not the DLT name.
- **Original partition** does not necessarily equal the DLT partition if the record was rerouted.
- **Original offset** is not the consumer group committed offset.
- **Original timestamp** is not the time the record was written to the DLT.
- **Exception metadata** explains one failure, not guaranteed proof of business state.

This metadata typically resides in **Kafka record headers**, separate from the record's key and value. That is why you should not overwrite the business payload with an arbitrary error JSON if you still want to deserialize and replay the original record.

## 3. Flow for preserving metadata when moving to the DLT

An error-handling workflow typically looks like:

~~~text
Consumer group orders-service
         |
         v
poll orders/P3/1254
         |
         v
OrderListener.process(record)
         |
         +----- succeeded ------> continue
         |
         v
Throws exception
         |
         v
DefaultErrorHandler + BackOff
         |
         +----- retries remaining --> listener reprocesses
         |
         v
Retries exhausted / non-retryable error
         |
         v
DeadLetterPublishingRecoverer
         |
         +-- keep required key/value/headers
         +-- add original topic/partition/offset
         +-- add exception metadata
         |
         v
Kafka producer publish orders.DLT
         |
         v
Broker assigns new DLT offset
         |
         v
DLT consumer / investigation system
~~~

If a record passes through multiple retry topics before reaching the DLT, there are intermediate publish/consume steps. Each step is a record in a separate log, and whether metadata retains the **first** record or the **most recent hop** must be determined by how the infrastructure and recoverer configure headers.

Do not assume a header named original always points to the very first position across the entire journey if the record has been forwarded across multiple topics, custom recoverers, or replays. Which header serves as the canonical origin must be verified against your topology's actual configuration and data.

## 4. DefaultErrorHandler and DeadLetterPublishingRecoverer

For listener containers not using Kafka transactions, a common configuration combines **DefaultErrorHandler** with **DeadLetterPublishingRecoverer**.

~~~java
@Configuration
public class KafkaRecoveryConfiguration {

    @Bean
    DefaultErrorHandler orderErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(kafkaTemplate);

        FixedBackOff backOff = new FixedBackOff(1_000L, 3L);

        DefaultErrorHandler handler =
                new DefaultErrorHandler(recoverer, backOff);

        handler.addNotRetryableExceptions(
                InvalidOrderException.class);

        return handler;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
            kafkaListenerContainerFactory(
                    ConsumerFactory<String, OrderEvent> consumerFactory,
                    DefaultErrorHandler orderErrorHandler) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(orderErrorHandler);
        return factory;
    }
}
~~~

OrderEvent and InvalidOrderException are application example types. In a real environment, you must properly configure the producer factory, key/value serializers, consumer deserializers, security, and partition counts. The snippet illustrates the Spring Kafka API; exact imports and wiring depend on the library version.

When a record can no longer be processed, DeadLetterPublishingRecoverer builds the record sent to the DLT and attaches DLT headers per default policy or custom settings. Consequently, the destination record can hold both its **current position on the DLT** and **source location metadata**.

DefaultErrorHandler does not send every failure to the DLT immediately. It relies on classification, BackOff, and the recoverer. If a retry succeeds, no DLT record is needed. If the recoverer fails, the DLT write may not have succeeded; that is a separate situation requiring its own handling policy.

## 5. DLT destination configuration and partition mapping

A common default of DeadLetterPublishingRecoverer sends records from topic **orders** to **orders.DLT**, with the destination partition equal to the source partition. For instance, orders/P3/1254 is sent to orders.DLT/P3.

To express routing explicitly, pass a destination resolver:

~~~java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
                kafkaTemplate,
                (record, exception) ->
                        new TopicPartition(
                                record.topic() + ".DLT",
                                record.partition()));
~~~

With this approach, the DLT topic must have enough partitions to include the destination partition. For example, if orders has six partitions, orders.DLT must have at least six partitions to route P0 through P5 properly.

When you want the Kafka producer to choose the destination partition via its partitioner instead of preserving the exact source index, use a destination resolver returning a TopicPartition with a negative partition under the recoverer API semantics supported by your Spring Kafka version:

~~~java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
                kafkaTemplate,
                (record, exception) ->
                        new TopicPartition(
                                record.topic() + ".DLT", -1));
~~~

When no fixed partition is specified on the published record, the Kafka producer selects a partition using the key and partitioner. In this case, the **current DLT partition may differ from the original partition**. Source headers become even more critical for tracing.

Do not configure a DLT with too few partitions or assume adding partitions changes the meaning of the original offset. The original offset still belongs to the source partition, not the destination partition.

### Controlled DLT creation

Example where the application proactively registers the topic:

~~~java
@Bean
NewTopic ordersDlt() {
    return TopicBuilder.name("orders.DLT")
            .partitions(6)
            .replicas(3)
            .build();
}
~~~

Partition count and replication factor here are illustrative. The cluster needs enough brokers for a replication factor of three. In production, align topic names, retention, replication, min.insync.replicas, ACLs, and quotas with Kafka operational procedures.

## 6. Reading original topic, partition, and offset in a DLT consumer

When reading records from a DLT, use ConsumerRecord and KafkaHeaders to extract source metadata. Example handler in Spring Kafka:

~~~java
@DltHandler
public void handleDlt(ConsumerRecord<String, OrderEvent> record) {
    Headers headers = record.headers();

    String originalTopic = readUtf8Header(
            headers, KafkaHeaders.DLT_ORIGINAL_TOPIC);

    Integer originalPartition = readIntHeader(
            headers, KafkaHeaders.DLT_ORIGINAL_PARTITION);

    Long originalOffset = readLongHeader(
            headers, KafkaHeaders.DLT_ORIGINAL_OFFSET);

    log.error(
            "DLT record current={}/{}/{}, original={}/{}/{}, key={}",
            record.topic(),
            record.partition(),
            record.offset(),
            originalTopic,
            originalPartition,
            originalOffset,
            record.key());

    failureAuditService.recordFailure(
            record.key(),
            originalTopic,
            originalPartition,
            originalOffset);
}
~~~

In this example, **readUtf8Header**, **readIntHeader**, and **readLongHeader** are application helpers, not built-in Kafka APIs. They can be implemented as:

~~~java
private static String readUtf8Header(
        Headers headers, String headerName) {
    Header header = headers.lastHeader(headerName);
    if (header == null || header.value() == null) {
        return null;
    }
    return new String(header.value(), StandardCharsets.UTF_8);
}

private static Integer readIntHeader(
        Headers headers, String headerName) {
    Header header = headers.lastHeader(headerName);
    if (header == null || header.value() == null
            || header.value().length != Integer.BYTES) {
        return null;
    }
    return ByteBuffer.wrap(header.value()).getInt();
}

private static Long readLongHeader(
        Headers headers, String headerName) {
    Header header = headers.lastHeader(headerName);
    if (header == null || header.value() == null
            || header.value().length != Long.BYTES) {
        return null;
    }
    return ByteBuffer.wrap(header.value()).getLong();
}
~~~

The example uses ByteBuffer's default byte order and the integer encoding convention common to Spring Kafka DLT headers. Do not decode partition or offset as ASCII strings, because they are normally byte-encoded integers. If your application uses a custom recoverer or custom header encoding, decode using the exact convention used when publishing.

When using **@DltHandler**, the method is configured alongside a @RetryableTopic topology, and records are delivered by the DLT listener container. If the application creates a standalone DLT consumer with @KafkaListener, reading headers from ConsumerRecord works the same way.

Practical note: **lastHeader()** returns the last value if a header has multiple entries. This is not always the very first source position of an entire retry chain. For workflows with multiple forwards, review your header append/retain policy before choosing the first or last entry.

## 7. Original metadata and current metadata must be stored separately

A DLT record has two sets of location fields:

| Field | Current record | Original record |
|---|---|---|
| Topic | record.topic() | Header DLT_ORIGINAL_TOPIC |
| Partition | record.partition() | Header DLT_ORIGINAL_PARTITION |
| Offset | record.offset() | Header DLT_ORIGINAL_OFFSET |
| Timestamp | record.timestamp() | Header DLT_ORIGINAL_TIMESTAMP, if preserved |
| Consumer group | Group reading the DLT | Initial processing group if tracked separately |

Example of accurate logging:

~~~text
eventId=E-2871
currentTopic=orders.DLT
currentPartition=3
currentOffset=12
originalTopic=orders
originalPartition=3
originalOffset=1254
exception=TemporaryPaymentException
~~~

Avoid ambiguous logs like:

~~~text
topic=orders.DLT offset=1254
~~~

That ambiguous log mixes the destination topic with the source offset, which can mislead operators into seeking the wrong offset or concluding the DLT record does not exist.

An audit data model should name them distinctly:

~~~text
FailureAudit
  eventId
  originalTopic
  originalPartition
  originalOffset
  dltTopic
  dltPartition
  dltOffset
  exceptionClass
  firstFailureAt
  recoveredAt
  recoveryStatus
~~~

Kafka coordinates are very useful for operations, but the business event ID is a better key when preventing duplicates or joining with databases and external systems.

## 8. Preserving headers across multiple retry topics

In non-blocking retries, a record can pass through multiple topics:

~~~text
orders/P3/1254
       |
       v
orders-retry-1000/P3/87
       |
       v
orders-retry-2000/P3/24
       |
       v
orders.DLT/P3/12
~~~

When forwarding, the framework can preserve original headers, update error headers, and add attempt, delay, or current-stage details. Because Kafka headers allow multiple entries with the same name, a record can accumulate multiple values related to processing.

Design principles:

- Distinguish the **initial business record** from the **direct source record of the latest publish**.
- Never assume an original header has a single value when multiple forwards occur.
- If you need the initial origin across the whole pipeline, set dedicated application headers like x-origin-topic, x-origin-partition, and x-origin-offset at the first hop or use an immutable event ID.
- When a custom recoverer builds a new ProducerRecord, intentionally preserve source metadata; do not copy only the value and drop headers.
- Avoid appending stack traces repeatedly, which bloats record size at each hop.

Spring Kafka has options on DeadLetterPublishingRecoverer to control adding original headers or keeping/stripping prior exception headers, such as APIs related to appending original headers and stripping previous exception headers depending on version. Use the mechanisms matching your actual dependency rather than relying on unverified method names.

### Immutable application headers when the first origin is needed

If the architecture requires tracing the very first record after multiple topic hops, you can define your own convention:

~~~text
x-event-id:       E-2871
x-origin-topic:   orders
x-origin-part:    3
x-origin-offset:  1254
~~~

These names are **application-defined headers**, not mandatory Spring Kafka constants. When forwarding a record, set them only if they do not already exist, and do not overwrite them at later stages. Agree on integer encoding/decoding between producer and consumer.

Do not completely replace framework DLT headers with application headers if existing investigative tools rely on KafkaHeaders.DLT_ORIGINAL_*. The best approach is a clear convention: framework metadata serves recovery, while application metadata serves end-to-end correlation.

## 9. When can headers be missing or inaccurate?

Not every record in a topic named DLT was created by DeadLetterPublishingRecoverer. For instance:

- A service publishes directly to the DLT itself.
- A replay batch job copies values without copying headers.
- A legacy application does not use current header constants.
- A custom recoverer alters or filters metadata.
- Data is mirrored from another cluster via a pipeline that drops some headers.
- A system uses a custom JSON wrapper instead of Kafka record headers.

Therefore, DLT consumers should verify:

1. Does the original topic header exist?
2. Do partition and offset have the expected byte lengths?
3. Is the source topic an allowed topic for lookup/replay?
4. Does the source partition exist?
5. Is the source offset still within current retention?
6. Are there duplicate header names where the first or last entry must be selected?

If metadata is missing, do not guess the original topic by stripping the suffix from the DLT name and treat that as fact. Topic naming rules can be customized and retry topologies can have multiple stages. Mark the state as **missing origin metadata** for operator review.

## 10. Original record position is not the committed offset

The original offset points to the **position of the failing record** in the source log. The consumer group's committed offset represents the next position the group will read when resuming.

Example:

~~~text
Failed record:
  original topic: orders
  partition: 3
  offset: 1254

Consumer group committed offset:
  orders/P3 = 1255
~~~

In the example, the group has moved past position 1254 under its error-handling and recovery policy. The original offset header remains 1254 so the failed record can be investigated, even though the committed offset has advanced to 1255.

Do not use the original offset to automatically reset the entire consumer group back to offset 1254 when replaying one record. A seek/offset reset can cause the group to re-read all subsequent records, creating duplicate side effects and impacting other partitions.

If you need to replay a record from the DLT, a common approach is creating a dedicated replay flow or publishing the approved record to an appropriate processing topic with a stable event ID and idempotency. Resetting group offsets should only be done in a carefully designed procedure with scope and downtime assessment.

## 11. The original offset may no longer be readable

Kafka topics have retention and cleanup policies. Once the source record passes retention, the original topic/partition/offset values may remain in the DLT header, yet the original record is no longer in the log to fetch.

Example:

~~~text
Monday:
  orders/P3/1254 fails
  record is moved to orders.DLT/P3/12

Two weeks later:
  orders retention deleted the segment containing offset 1254
  orders.DLT still retains the failed record

Result:
  Original offset metadata exists
  But the original payload cannot be fetched at the old offset
~~~

Headers are therefore a **historical trace pointer**, not a guarantee that the source record still exists. The DLT needs retention long enough for investigation, and you should not rely solely on the source topic to recover payloads.

With compacted topics, a record at an old offset can also be compacted out of the log. With topics truncated due to incidents or administrative actions, offsets or log history can change. Treat original topic/partition/offset as diagnostic metadata captured at the time of failure.

## 12. Linking the DLT with logs and tracing

A reliable system connects three layers of data:

1. **Kafka location:** topic, partition, and offset at each stage.
2. **Business identity:** event ID, order ID, or transaction ID.
3. **Execution context:** trace ID, span ID, exception category, and application instance.

Example:

~~~text
eventId=EVT-552
traceId=trace-abc
orderId=ORD-1009
origin=orders/P3/1254
dlt=orders.DLT/P3/12
attempt=4
exception=DownstreamTimeoutException
consumerGroup=orders-service
~~~

With event ID, you can locate every processing attempt of an event across topics and instances. With original offset, you can locate the source record if still within retention. With trace ID, you can inspect calls to services and databases.

Do not use the original offset as a system-wide idempotency key if records can be republished to other topics or across clusters. Offsets are Kafka log positions, not immutable business identifiers across forwards.

When emitting metrics, avoid attaching event ID, offset, or trace ID as high-cardinality metric labels. Use them in logs/traces and use exception category, outcome, and listener ID as metric tags.

## 13. Recovery failures and DLT publishing issues

Recording metadata accurately is not enough to guarantee successful recovery. DeadLetterPublishingRecoverer uses a Kafka producer; publishing can fail because:

- The DLT has not been created or is misnamed.
- The destination partition does not exist.
- ACLs do not allow produce.
- Brokers or network are unavailable.
- Serializers cannot handle a value that failed deserialization.
- The record is too large due to payload plus exception headers.
- Timeouts or replication fail to meet acknowledgement requirements.

When the recoverer fails, the application needs a clear policy for redelivering the record or continuing retries. **Never commit/ack to skip a failed record uncontrollably merely because sending to the DLT was attempted.**

In addition, succeeding on DLT publish and committing the source offset are two separate operations. If a crash happens between them, the source record can be re-read and published to the DLT again. Two DLT records can carry the same original topic/partition/offset while having **different DLT offsets**.

~~~text
DLT record 1:
  currentOffset=12
  original=orders/P3/1254

DLT record 2:
  currentOffset=13
  original=orders/P3/1254

Two DLT records may share the same origin,
but not the same position on the DLT.
~~~

This shows that the original location tuple is useful for detecting repeated recovery attempts, though you still need event IDs and business rules to decide whether to skip a record.

## 14. Deserialization failure cases

Some records fail before entering the listener, such as bytes that cannot decode into OrderEvent. In those cases, error handling must receive error details from the deserializer layer.

Spring Kafka commonly uses ErrorHandlingDeserializer to pass deserialization failure info to the container/error handler. Depending on configuration, the record sent to the DLT may carry the raw bytes of the malformed value rather than an OrderEvent object.

Key points to watch:

- Do not assume DLT values can always deserialize into the same class as the source topic.
- The DLT producer needs serializers compatible with both normal payloads and raw-byte failure payloads.
- Original topic/partition/offset headers remain vital, especially since the business listener was never invoked.
- Exception headers may hold stack traces, classes, and messages; limit exposure of sensitive data.
- When a DLT consumer receives raw bytes, provide an investigation path or safe payload viewer rather than blindly re-deserializing with the failing schema.

For unrecoverable schema errors, repeated retries rarely help. You can route them straight to the DLT per classifier, retaining raw bytes and metadata sufficient to fix schemas or reprocess under control.

## 15. Replaying from the DLT without losing provenance

Replay is the process of returning DLT records to processing after the failure is resolved. During replay, decide how to preserve both source history and DLT history.

A safe workflow:

1. Select DLT records by event ID or current DLT topic/partition/offset.
2. Read original headers and verify event ID, payload type, and failure cause.
3. Confirm the error is fixed and downstream systems are ready.
4. Check whether the record was already processed successfully elsewhere.
5. Publish the record to the appropriate replay topic, keeping the event ID and needed provenance.
6. Attach metadata about the replay action: operator, reason, timestamp, and replay attempt.
7. Monitor processing results and prevent infinite DLT → replay → DLT loops.
8. Record audit state without confusing current offset with original offset.

Example audit metadata:

~~~text
eventId=EVT-552
original=orders/P3/1254
firstDlt=orders.DLT/P3/12
replayedTo=orders-replay/P1/42
replayAttempt=1
replayReason=payment-service-recovered
~~~

Do not overwrite original topic/partition/offset with the replay location if those fields mean the **first origin of the event**. Use separate fields or headers for the replay location. If the pipeline uses the framework's append-original-headers option, distinguish immutable provenance from the latest recovery hop.

A record partially processed prior to failure can still cause duplicate side effects during replay. Therefore, use idempotency keys, unique constraints, or business state checks. Original offset metadata only helps trace; it does not prevent duplicates.

## 16. How should a DLT consumer react to metadata?

Do not have the DLT handler automatically replay every record immediately upon receipt. The DLT is a staging point for failures needing visibility; if the DLT handler calls the same failing service again, the system can fall into a fresh retry loop.

A safer option is having the DLT handler record failures in a failure store for operational investigation:

~~~java
@DltHandler
public void handleDlt(ConsumerRecord<String, OrderEvent> record) {
    String originTopic = readUtf8Header(
            record.headers(), KafkaHeaders.DLT_ORIGINAL_TOPIC);
    Integer originPartition = readIntHeader(
            record.headers(), KafkaHeaders.DLT_ORIGINAL_PARTITION);
    Long originOffset = readLongHeader(
            record.headers(), KafkaHeaders.DLT_ORIGINAL_OFFSET);

    failureAuditService.upsertByEventId(
            record.value().eventId(),
            originTopic,
            originPartition,
            originOffset,
            record.topic(),
            record.partition(),
            record.offset());
}
~~~

This example assumes the value deserialized into OrderEvent and exposes eventId(). For deserialization failures, a different handler is needed for `byte[]` or raw payloads. If upserting by event ID, decide how to store multiple DLT entries for the same event ID; do not erase failure history if audit data is needed for investigation.

From the DLT handler, you can also emit alerts or open tickets, while avoiding placing full sensitive payloads/stack traces into systems with broad access.

## 17. Protecting metadata integrity and security

Headers are part of a Kafka record's data. Depending on the system, producers and consumers can read, alter, or rewrite them. Therefore, do not treat original headers as tamper-proof signatures.

For workflows with strict audit requirements:

- Control ACLs for producers writing to the DLT and consumers reading from the DLT.
- Restrict who can change retry/DLT routing.
- Write audit records outside Kafka when records enter critical failure states.
- Use event IDs and data signatures when integrity must hold across trust boundaries.
- Limit personal data in exception messages and stack traces.
- Disallow arbitrary replays from a DLT holding unverified data.

If an untrusted service has permission to publish directly to the DLT, the original topic and offset it supplies might not reflect an actual existing position. Investigative tooling should verify provenance and permissions before making critical decisions.

## 18. Observability and operations

Logs/metrics should answer three questions: where did the failed record originate, what retry steps did it go through, and what was the recovery outcome?

Emit structured logs:

~~~text
eventId=EVT-552
listener=orders-listener
consumerGroup=orders-service
currentTopic=orders.DLT
currentPartition=3
currentOffset=12
originalTopic=orders
originalPartition=3
originalOffset=1254
exceptionClass=DownstreamTimeoutException
outcome=published_to_dlt
~~~

Track:

- Number of records published to the DLT, by source topic and exception category.
- DLT publish error rate and latency.
- DLT consumer lag and age of the oldest record.
- Rate of records missing original topic/partition/offset headers.
- Duplicate DLT records sharing the same event ID or original location.
- Replay requests, replay successes, and replay failures.
- Time from first failure to successful resolution or incident closure.
- DLT disk usage, retention, and expiration risk.

Topic/partition/offset and event ID belong in logs or traces; avoid using offsets as metric labels. To break down by source topic, use a label with a controlled set of values; protect dashboards from unexpected cardinality growth.

When spotting a record on the DLT, investigation can start from the **current DLT location**, read the original headers, locate the event ID and trace, and correlate with the original listener's logs. If the origin record has expired past retention, use the DLT payload and audit store as primary investigative evidence.

## 19. Common failure scenarios

### Missing DLT_ORIGINAL_TOPIC

The record may have been published manually, copied without headers, or not sent via Spring Kafka's recoverer. Flag it as missing metadata; do not derive a source topic by stripping the DLT suffix and assert it as fact.

### Original partition differs from current partition

A destination resolver or partitioner may have rerouted the record. Do not assume this is automatically an error. Read the original partition header properly and inspect the routing strategy.

### Original offset is larger than DLT offset

Completely normal. Offsets are assigned independently within each partition of each topic; there is no ordering comparison between offsets in two separate logs.

### Two DLT records share the same original offset

This can happen from a retry after a crash between publish and commit, from a replay, or from custom recovery. Use event ID and audit records to determine whether the event was processed once or multiple times.

### Seeking the original offset finds no record

The original record may have passed retention or been compacted, the topic/partition may be wrong, or metadata may have changed. Do not jump to the conclusion that the DLT record is invalid; inspect log start offset and cleanup policy.

### Cannot decode original offset

Verify the header exists and is exactly eight bytes in the expected encoding. A custom recoverer might write a string or another format. Do not call Long.parseLong on binary bytes without knowing the encoding.

### Record passed through multiple retry topics and has multiple original headers

Check the append/strip policy and whether firstHeader or lastHeader is used. If you need an immutable first origin, maintain a dedicated event ID and origin metadata across the topology.

### Replay succeeds yet the record returns to the DLT

The root cause may remain unfixed, the replay may have used the wrong payload type, or idempotency/state may have drifted. Inspect logs by event ID and retry stage, not just the current DLT offset.

## 20. Testing preservation of original metadata

You should have integration tests using a test Kafka broker or equivalent environment to verify real records are published to the DLT with expected headers.

Scenarios to cover:

1. Listener throws a non-retryable exception: record arrives in DLT with accurate original topic, partition, and offset.
2. Listener retries several times and fails: source metadata remains traceable after stage transitions.
3. Destination resolver changes partition: original partition differs from current partition yet is read accurately.
4. Custom recoverer copies headers: original metadata is not lost.
5. Record processed by @RetryableTopic across multiple retry topics: source header selection policy holds.
6. Payload fails deserialization: raw bytes and source metadata remain usable for investigation per configuration.
7. DLT publish fails: recovery is not falsely recorded as succeeded.
8. Crash or replay produces two DLT records with the same origin: audit detects the duplicate.
9. Source record passed retention: investigation workflow still works using DLT data.
10. Missing or malformed-length header: DLT consumer does not crash uncontrollably and emits a missing-metadata warning.

A simple assertion on a DLT ConsumerRecord:

~~~java
String originalTopic = readUtf8Header(
        dltRecord.headers(), KafkaHeaders.DLT_ORIGINAL_TOPIC);

Integer originalPartition = readIntHeader(
        dltRecord.headers(), KafkaHeaders.DLT_ORIGINAL_PARTITION);

Long originalOffset = readLongHeader(
        dltRecord.headers(), KafkaHeaders.DLT_ORIGINAL_OFFSET);

assertThat(originalTopic).isEqualTo("orders");
assertThat(originalPartition).isEqualTo(3);
assertThat(originalOffset).isEqualTo(1254L);
~~~

The value 1254L is just an example; real tests should capture the source record's topic/partition/offset from confirmed produce or consumer metadata rather than hard-coding arbitrary offsets, since Kafka assigns offsets based on actual log state.

## 21. Common misconceptions

**A record sent to the DLT keeps its Kafka offset.** False. A DLT is a different topic/log and the broker assigns a new offset. The original offset is kept in metadata.

**The original offset is the group's committed offset.** False. The original offset points to the failing record's position. The committed offset is the next position the group will read.

**Having only the original offset is enough to find the source record.** False. You also need the original topic and partition; moreover, the record may have passed retention.

**The DLT partition always equals the original partition.** False if a destination resolver or partitioner picks another partition; read the source metadata.

**Using the source offset as a business idempotency key is sufficient.** False for general cases. Events can be republished or moved across clusters; a stable event ID is usually better.

**DLT headers are guaranteed on every record in a topic named DLT.** False. Custom publishers may omit them; DLT consumers must handle missing headers.

**Moving to the DLT means business processing is complete.** False. A DLT is a recovery/investigation flow and does not prove business side effects succeeded.

**Original headers always point to the very first record regardless of retry hops.** Do not assume this. Verify header append settings and forwarding steps.

**Having original topic/offset guarantees exactly-once.** False. Metadata only serves tracing; publishes and commits can create duplicates, so side effects still require idempotency.

**You can replay by resetting the group offset to the original offset without side effects.** False. Resetting can re-read large batches of records and re-execute side effects.

## 22. Recommended implementation workflow

When designing dead-letter recovery for a Spring Kafka listener, define how metadata is preserved from the start rather than adding it after an incident.

1. Choose appropriate DLT naming, retention, partition count, and ACLs.
2. Use DeadLetterPublishingRecoverer or a custom recoverer with an explicit metadata-retention policy.
3. Include original topic, partition, and offset headers with the proper encoding.
4. Preserve an immutable business event ID to correlate across the main topic, retry topics, and DLT.
5. Across multiple hops, decide how to store the first origin vs. the most recent hop, avoiding overloading one field for both.
6. Configure a reliable DLT producer and monitor publish failures.
7. Build DLT handlers capable of safely handling missing or malformed headers.
8. Store current DLT location and original Kafka location in separate audit log fields.
9. Design replay with approvals, idempotency, and outcome tracking.
10. Test missing headers, different partition mappings, duplicate records, crashes, and expired source records.

**Preserving the original topic and offset** is the foundation for turning a DLT from a bucket of failed records into an investigable, traceable recovery mechanism. Retain original topic, original partition, and original offset, keep them distinct from the DLT record's position, and combine them with event IDs, headers, logs, audits, and idempotency. Operations teams can then tell where a failed record came from, what steps it went through, and how to replay it without equating tracing metadata with exactly-once processing guarantees.
