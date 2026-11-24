# Reading and Processing Dead-Letter Records

A dead-letter topic (DLT) stores records that a consumer could not process successfully under the configured retry and recovery policies. A record moved to a DLT is still a Kafka record: it preserves its key, value, and forwarded headers, while typically carrying extra metadata indicating which topic, partition, and offset it originated from and what error sent it to the DLT.

Reading a DLT is not just writing a listener subscribed to a `.DLT`-suffixed topic. The consumer must understand that payloads can be either deserialized objects or raw bytes that failed deserialization, read source metadata accurately, classify the root cause, persist enough evidence for investigation, and decide whether the record can be replayed or needs manual handling. When replaying, you must control idempotency, ordering, offsets, and business impact so recovery does not turn into duplicate processing.

This lesson belongs to the **Dead letter and recoverer** chapter of the **SPRING_KAFKA_MESSAGING** module, focusing on reading dead-letter records, investigating failures, persisting records, and recovering data with Spring Kafka.

## Target Outcomes

After this lesson, you will be able to:

- Explain how a DLT record is created and what information it carries.
- Distinguish metadata of the record in the DLT from metadata of the original record.
- Create a DLT consumer with an appropriate group ID and deserializer.
- Read raw bytes when the original record failed to deserialize.
- Extract original topic, partition, offset, and exception headers.
- Classify errors to decide whether to fix data, fix the consumer, or replay.
- Persist dead-letter records durably while preventing duplicate storage.
- Replay records to the original topic or a controlled recovery stream.
- Preserve keys and required headers while accounting for partition ordering.
- Operate a DLT with retention, ACLs, monitoring, ownership, and a runbook.

## 1. What Is a Dead-Letter Record?

When a listener fails to process a record, the error handler may retry. If the record still cannot be processed after the allowed attempts or is classified as non-retryable, the recoverer can publish it to a separate topic, usually named with the source name plus a `.DLT` suffix.

Example:

~~~text
orders.created
      |
      | listener fails
      v
DefaultErrorHandler
      |
      | retry exhausted / non-retryable
      v
DeadLetterPublishingRecoverer
      |
      v
orders.created.DLT
~~~

A record in the DLT typically carries:

- Key and value of the recovered record, which may be objects or raw bytes depending on where the error occurred and serializer configuration.
- Any application headers already present on the record.
- Metadata headers added by Spring Kafka to capture provenance and exception details.
- New metadata of the DLT record itself, such as topic, partition, offset, and timestamp assigned by Kafka when writing to the DLT.

A DLT is an isolation zone for investigation and recovery. Putting a record into the DLT does not mean business processing succeeded; it only means the main stream moved the record aside according to configured policy.

## 2. Distinguishing DLT Metadata from Original Record Metadata

A record read from `orders.created.DLT` has two distinct sets of metadata:

| Field | Meaning |
|---|---|
| DLT topic | Topic that the DLT consumer is reading from. |
| DLT partition | Partition of the record inside the DLT topic. |
| DLT offset | Offset of the record inside the DLT topic. |
| DLT timestamp | Timestamp of the DLT entry. |
| Original topic | Topic where the record originally failed. |
| Original partition | Source partition of the original record. |
| Original offset | Offset of the original record. |
| Exception headers | Exception class, message, and error details recorded by the recoverer. |

Do not use the DLT offset in place of the original offset. For example, a record may sit at `orders.created.DLT-2@15`, while its headers indicate the source record was `orders.created-2@841`. Those are two independent positions in two different logs.

Source details are essential when correlating producer logs, consumer lag, original data, or locating the record within the source topic's retention window.

## 3. Common Metadata Headers

Spring Kafka defines constants in `KafkaHeaders` for reading dead-letter metadata. Commonly used names include:

| Constant | Content |
|---|---|
| `KafkaHeaders.DLT_ORIGINAL_TOPIC` | Original topic name. |
| `KafkaHeaders.DLT_ORIGINAL_PARTITION` | Original partition. |
| `KafkaHeaders.DLT_ORIGINAL_OFFSET` | Original offset. |
| `KafkaHeaders.DLT_ORIGINAL_TIMESTAMP` | Original timestamp. |
| `KafkaHeaders.DLT_ORIGINAL_TIMESTAMP_TYPE` | Original timestamp type. |
| `KafkaHeaders.DLT_EXCEPTION_FQCN` | Fully qualified exception class name. |
| `KafkaHeaders.DLT_EXCEPTION_MESSAGE` | Exception message. |
| `KafkaHeaders.DLT_EXCEPTION_STACKTRACE` | Stack trace stored in the header. |
| `KafkaHeaders.DLT_ORIGINAL_CONSUMER_GROUP` | Source consumer group in supported versions. |

The exact set of headers depends on the Spring Kafka version and `DeadLetterPublishingRecoverer` configuration. Use the constants available in your project's actual dependency rather than hardcoding header names or assuming every version populates the same metadata set.

Kafka header values are `byte[]`. Some metadata headers are UTF-8 text; numeric values are encoded in Spring Kafka's format. When reading `ConsumerRecord` directly, decode according to the header's actual type. When receiving via Spring `MessageHeaders`, the mapper may have already converted values into Java types.

## 4. A DLT Consumer Should Have Its Own Group ID

A DLT-processing consumer is typically a separate operational concern: classifying, archiving, repairing data, or replaying. Therefore, give it a dedicated group ID, such as `orders-dlt-review`.

Replicas of the same DLT handler share that group ID to divide partitions among themselves. Another consumer group can read the DLT independently for auditing or analytics.

Example:

~~~java
@Component
public class OrdersDeadLetterListener {

    @KafkaListener(
            topics = "orders.created.DLT",
            groupId = "orders-dlt-review"
    )
    public void inspect(ConsumerRecord<byte[], byte[]> record) {
        // Persist the failed record for investigation and classification.
    }
}
~~~

The DLT consumer's group ID must never accidentally match the group processing the source topic. DLT offsets must remain independent so reading and investigating the DLT does not alter the progress of the business consumer.

If a new DLT consumer has no committed offset yet, `auto.offset.reset` determines where it starts. For a DLT that must inspect an existing backlog, actively configure `earliest` or use an appropriate seek workflow. `auto.offset.reset` applies only when the group lacks a valid offset; it does not rewind a group that has already committed.

## 5. Why Read the DLT as Raw Bytes?

A DLT can hold multiple value representations:

- Records that deserialized into objects, then failed business processing in the listener.
- Records that failed deserialization, leaving the original value solely as `byte[]`.
- Records forwarded across services or retry stages with different serializers.

If you configure a single DTO deserializer for the entire DLT, the consumer can fail again when encountering a record that entered the DLT precisely due to a deserialization error. A safe way to build an investigation tool is to read keys and values as `byte[]`, then manually deserialize only after determining the format.

Example creating a raw-bytes consumer factory:

~~~java
@Bean
ConsumerFactory<byte[], byte[]> dltRawConsumerFactory(
        @Value("${spring.kafka.bootstrap-servers}") String bootstrapServers) {

    Map<String, Object> props = new HashMap<>();
    props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
    props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
    props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

    return new DefaultKafkaConsumerFactory<>(
            props,
            new ByteArrayDeserializer(),
            new ByteArrayDeserializer()
    );
}
~~~

Creating the listener container factory:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<byte[], byte[]>
dltRawListenerFactory(
        ConsumerFactory<byte[], byte[]> dltRawConsumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<byte[], byte[]>();

    factory.setConsumerFactory(dltRawConsumerFactory);
    factory.getContainerProperties()
            .setAckMode(ContainerProperties.AckMode.RECORD);

    return factory;
}
~~~

Listener using the dedicated factory:

~~~java
@KafkaListener(
        topics = "orders.created.DLT",
        groupId = "orders-dlt-review",
        containerFactory = "dltRawListenerFactory"
)
public void inspect(ConsumerRecord<byte[], byte[]> record) {
    // record.key() and record.value() remain byte[].
}
~~~

A raw-bytes factory preserves payloads intact for investigation without depending on current Java classes. If a DLT strictly holds one event type with a stable schema and a controlled DLT serializer, a typed deserializer can be used. However, general-purpose quarantine/recovery tooling should usually preserve raw bytes.

`ByteArrayDeserializer` only controls how the DLT consumer reads data. It does not fix serialization errors on the DLT publishing side. If the same DLT receives both raw `byte[]` from deserialization errors and decoded objects from business errors, the `KafkaTemplate` used by `DeadLetterPublishingRecoverer` must be able to serialize both forms. You can use a type-routing serializer or separate `KafkaTemplate` instances; test both paths before deploying.

## 6. Reading Source Metadata from ConsumerRecord

You can read a header using `record.headers().lastHeader(name)`. Example helper for reading a UTF-8 text value:

~~~java
private String headerAsString(Headers headers, String name) {
    Header header = headers.lastHeader(name);
    if (header == null || header.value() == null) {
        return null;
    }
    return new String(header.value(), StandardCharsets.UTF_8);
}
~~~

Reading common metadata fields:

~~~java
String originalTopic =
        headerAsString(record.headers(), KafkaHeaders.DLT_ORIGINAL_TOPIC);

String exceptionType =
        headerAsString(record.headers(), KafkaHeaders.DLT_EXCEPTION_FQCN);

String exceptionMessage =
        headerAsString(record.headers(), KafkaHeaders.DLT_EXCEPTION_MESSAGE);
~~~

For partition and offset, decode numbers according to the header format of your Spring Kafka version. For example, if numeric headers are encoded as big-endian integers/longs:

~~~java
private Integer headerAsInt(Headers headers, String name) {
    Header header = headers.lastHeader(name);
    if (header == null || header.value() == null) {
        return null;
    }
    return ByteBuffer.wrap(header.value()).getInt();
}

private Long headerAsLong(Headers headers, String name) {
    Header header = headers.lastHeader(name);
    if (header == null || header.value() == null) {
        return null;
    }
    return ByteBuffer.wrap(header.value()).getLong();
}
~~~

These helpers illustrate decoding binary numeric headers; verify the encoding used by your actual Spring Kafka version and handle unexpected header byte lengths. Do not coerce every header into a String and parse it if the framework stores numbers in binary form.

To inspect all duplicate headers sharing a name, use `record.headers().headers(name)`. A record may have passed through multiple dead-letter/recovery rounds and thus carry repeated headers; `lastHeader` only returns the last value.

## 7. Reading Raw Payloads Without Exposing Sensitive Data

Raw bytes help investigate deserialization errors, but you should not dump entire payloads into logs. Payloads may contain personal data, tokens, or payment details.

A listener can build an envelope to store in a quarantine repository:

~~~java
@KafkaListener(
        topics = "orders.created.DLT",
        groupId = "orders-dlt-review",
        containerFactory = "dltRawListenerFactory"
)
public void inspect(ConsumerRecord<byte[], byte[]> record) {
    DltEnvelope envelope = new DltEnvelope(
            record.topic(),
            record.partition(),
            record.offset(),
            record.key(),
            record.value(),
            headerAsString(record.headers(), KafkaHeaders.DLT_ORIGINAL_TOPIC),
            headerAsString(record.headers(), KafkaHeaders.DLT_EXCEPTION_FQCN),
            headerAsString(record.headers(), KafkaHeaders.DLT_EXCEPTION_MESSAGE)
    );

    deadLetterRepository.saveIfAbsent(envelope);
}
~~~

`saveIfAbsent` is illustrative. In production, enforce a unique key—such as DLT topic + partition + offset—to avoid persisting the same DLT record multiple times. If you also need to identify the source record, store original topic + partition + offset as well.

Logs should only contain identifiers, error types, and essential metadata. Store raw keys/values in a repository with proper ACLs, encryption, and retention.

## 8. Classifying Records Before Deciding How to Handle Them

Do not replay every record in a DLT the same way. Identify the root cause and recoverability first.

| Error category | Example | Handling approach |
|---|---|---|
| Invalid payload | Malformed JSON, truncated bytes | Save raw bytes, verify producer; fix or discard per business decision. |
| Incompatible schema | Producer added/changed fields incompatibly | Update consumer/schema and test before replaying. |
| Incorrect type mapping | Header points to missing or untrusted class | Fix type mapping or trusted packages in a controlled manner. |
| Transient dependency error | Prolonged database or HTTP service timeout | Verify dependency recovery, then perform rate-limited replay. |
| Business error | Order state disallows transition | Check current state; may require a business action rather than raw replay. |
| Configuration error | Wrong endpoint, credential, or ACL | Fix configuration and verify consumer health before replaying. |
| Obsolete record | Business-expired event | Close the case with a clear reason and record an audit log. |

A record may have sat in the DLT for a long time. Current business state may have moved on, so an old payload is not necessarily still valid to re-execute. Handlers must verify both technical root cause and current business state.

## 9. Dead-Letter Record Handling Workflow

An operational workflow may include these steps:

1. Consume the record from the DLT with a dedicated consumer group.
2. Record DLT topic, partition, offset, and original topic/partition/offset.
3. Persist raw key, value, and headers into a durable quarantine store.
4. Classify the failure using the exception, schema/version, and related logs.
5. Tag case status: `NEW`, `INVESTIGATING`, `READY_TO_REPLAY`, `RESOLVED`, or `REJECTED`.
6. Assign an owner and an approver if replaying triggers side effects.
7. Fix the root cause: payload, schema, code, configuration, or dependency.
8. Test against the exact raw bytes and metadata of the failed record.
9. Replay a single test record or a small pilot batch.
10. Verify business outcomes, ordering, and idempotency.
11. Scale replay up in bounded batches.
12. Close the case and preserve the audit trail.

The DLT consumer should complete durable persistence before the DLT offset is committed. If the listener writes to a database and crashes before Kafka commits the offset, the DLT record may be redelivered. Persistence must therefore be idempotent, such as a unique key on DLT topic/partition/offset.

## 10. Replaying Records to the Original Topic

Once the root cause is fixed, you can publish records back to the source topic. Two common approaches:

- Raw-bytes replay: fits when you want to keep exact key/value bytes, especially for records that failed deserialization.
- Deserialize then publish object: fits when the schema is verified and you want to emit the record under a new contract.

For raw replay, use a producer with `ByteArraySerializer` for both key and value. Example:

~~~java
ProducerRecord<byte[], byte[]> replay = new ProducerRecord<>(
        originalTopic,
        originalPartition,
        null,
        dltRecord.key(),
        dltRecord.value(),
        replayHeaders
);

rawBytesKafkaTemplate.send(replay);
~~~

`originalTopic`, `originalPartition`, and `replayHeaders` are constructed from verified metadata. Only specify `originalPartition` if that partition still exists and the architecture decides to pin the record to that exact partition. If the partition count changed or the old partition is no longer valid, choose a new partitioning strategy intentionally.

Do not blindly copy all DLT headers back to the source topic. Build a fresh header set preserving needed correlation ID/event ID/trace context and adding metadata such as `replay_id`, `replayed_from`, or `replay_timestamp`. Old exception and original-DLT headers can cause confusion if they appear as active errors on a fixed record.

If using typed replay, deserialize with a verified schema version and send via a `KafkaTemplate` configured with the right serializer for the source topic. Do not pass a JSON string through `JsonSerializer` if that double-serializes it into a nested JSON string.

## 11. Replay Does Not Automatically Restore Old Ordering

A DLT is a separate stream with its own offsets and processing timeline. While the original record sat in the DLT, subsequent records in the source topic may already have been processed. When replaying an older record, it may arrive after newer events.

Example:

~~~text
Source topic:
offset 40: OrderCreated
offset 41: OrderPaid
offset 42: OrderShipped

Record at offset 41 failed and moved to DLT.
Source consumer continued processing offset 42 after recovery.

Later, offset 41 is replayed to source topic:
replayed record is appended at a new offset, e.g. 57.
~~~

The replayed record at offset 57 does not return to position 41. Kafka never inserts records into the middle of an existing log. Therefore, replay can produce a new physical order, and listeners must check sequence/version or aggregate state before applying it.

If business ordering is mandatory, consider:

- Pausing or isolating the affected stream before replaying.
- Replaying per aggregate/key with controlled sequence ordering.
- Using an event version or sequence number to reject stale updates.
- Sending to a separate recovery topic and merging with business logic.
- Checking current state before executing side effects.

Preserving the partition number during replay only targets the same partition; it does not restore the old offset or guarantee ordering relative to records already processed later.

## 12. Idempotency and Preventing Duplicate Processing During Replay

Replay is a new record delivery from the consumer's perspective, even if the payload is identical to the old record. If the listener already produced side effects before the record entered the DLT or during a previous attempt, replay can repeat the action.

Use a stable event ID to prevent duplicates:

~~~java
@Transactional
public void handle(OrderCreatedEvent event) {
    if (processedEventRepository.existsById(event.eventId())) {
        return;
    }

    orderService.createOrder(event);

    processedEventRepository.save(
            new ProcessedEvent(event.eventId())
    );
}
~~~

In production, a unique constraint on the event ID must protect the check-and-insert within the same database transaction as the business update. Checking with `existsById` alone without a unique constraint suffers race conditions when two consumers process concurrently.

If you need to replay an already-processed event to trigger a new action, use a command/recovery workflow with its own identifier and clear business rules. Do not arbitrarily delete idempotency markers just to force an event to run again.

## 13. When Should the DLT Consumer Commit Its Offset?

The DLT consumer's offset should advance only after the record has been safely handled according to application policy. For instance, the listener successfully saves the envelope to the quarantine store before returning; the container then commits per its configured `AckMode`.

If the listener logs and returns even though database persistence failed, the offset may be committed and the record will never be redelivered. Conversely, if persistence succeeds but offset commit fails, the record may be redelivered; persistence must therefore be idempotent.

Principles:

- Do not acknowledge a record before required data is durably persisted.
- Use a unique key to prevent duplicate storage.
- Separate failures in persisting DLT records from failures in business processing/replay.
- Cap retries of the DLT consumer itself and provide a secondary DLT or alert if needed.
- Never allow a DLT handler to fail repeatedly forever with no owner.

Even if a DLT consumer only feeds a dashboard or observability, decide explicitly whether to archive records or only inspect them ephemerally. Offset commits do not replace DLT topic retention.

## 14. DLT Retention, Partitions, and Access Control

DLTs usually contain failure data that must be kept longer than the main stream for investigation, yet infinite retention incurs cost and data risk.

Define:

- Retention long enough for incident detection and resolution.
- Projected storage capacity based on failure rate and payload size.
- Appropriate partition count and replication factor.
- ACLs restricting read or replay access to authorized services/operators.
- Encryption and personal-data handling policies.
- Procedures to archive or purge records after cases close.
- An owner accountable for the DLT backlog.

If `DeadLetterPublishingRecoverer` sends records to the same partition index as the source topic, the DLT needs matching partitions. If the DLT has fewer partitions, publishing can fail with invalid partition errors. If using a centralized destination resolver, evaluate whether a single partition can handle the volume of failed records.

Monitor DLTs like any production topic: under-replicated partitions, disk usage, bytes in/out, and consumer lag.

## 15. DLT Metadata Can Repeat When Records Are Forwarded Multiple Times

A record can pass through multiple retry or DLT tiers. Headers may then contain multiple values under the same name or exception details from earlier attempts.

Do not assume the first or last header always represents the entire history. Instead:

- Read all headers with the same name when auditing.
- Record metadata of the current DLT hop alongside prior source metadata.
- Use DLT topic/partition/offset as the unique identifier for each DLT entry.
- Use original topic/partition/offset to link back to the source record.
- Record a replay ID for each replay attempt.
- Avoid logging unnecessary stack traces or sensitive payloads.

If using a Spring Kafka header mapper, verify how it converts `byte[]` and repeated headers. When reading `ConsumerRecord` directly, the application can iterate Kafka `Headers` without relying on Spring `MessageHeaders`.

## 16. Testing Reading and Processing the DLT

Test against a real broker via EmbeddedKafka or Testcontainers, because pure unit tests cannot verify actual serialization, headers, and offsets.

| Scenario | What to verify |
|---|---|
| Read DLT record | Listener receives exact key, value, and headers. |
| Raw bytes | Deserialization-failed payloads preserve exact byte sequences. |
| Original metadata | Reads accurate source topic, partition, and offset. |
| Exception headers | Contains expected exception class/message. |
| Mixed payloads | DLT consumer handles both raw bytes and JSON bytes. |
| Persist envelope | DLT record is saved durably and deduplicated. |
| Persist failure | DLT offset is not mistakenly committed when persistence fails. |
| Raw replay | Key/value bytes are resent without double serialization. |
| Typed replay | Event is deserialized and serialized under a verified contract. |
| Ordering | Replaying old records does not regress aggregate version or corrupt state. |
| Idempotency | Replay does not duplicate side effects. |
| DLT retention/ACLs | Consumers and operators have proper permissions and records are retained per policy. |

When testing original offsets, distinguish the source offset inside headers from the DLT record's offset. Use `AdminClient` to inspect committed offsets of the DLT group and wait with Awaitility/latches with timeouts rather than fixed `Thread.sleep`.

## 17. Observability and Runbook for the DLT

Operational metrics to maintain:

- Number of records published to the DLT by source topic and exception class.
- DLT consumer lag and backlog per partition.
- Number of records in `NEW`, `INVESTIGATING`, `READY_TO_REPLAY`, and `RESOLVED` states in the quarantine store.
- Mean time from entering the DLT to resolution.
- Successful/failed replay counts.
- Replay counts per event ID.
- Errors publishing to or reading from the DLT.
- Topic disk usage, retention, and under-replicated partitions.

A runbook should answer:

1. Who owns the DLT?
2. When must replay be halted?
3. How do we look up a record by source topic/partition/offset?
4. How do we inspect raw bytes without leaking sensitive data into logs?
5. Who approves replays that trigger side effects?
6. How do we pilot one record before bulk replay?
7. How do we throttle replay throughput?
8. How do we mark a record resolved or rejected?
9. When must a record be retained longer for investigation?
10. How do we close a case and store the audit trail?

Never auto-replay every record arriving in the DLT. A schema mismatch or business bug can generate thousands of records; replaying before fixing the root cause simply cycles the same failures between the DLT and the main topic.

## 18. Capstone Exercise: Building DLT Review and Replay

Build a handling flow for the `orders.created` topic and the `orders.created.DLT` DLT.

Requirements:

1. Create a DLT consumer with group ID `orders-dlt-review`.
2. Use `ByteArrayDeserializer` for key and value to preserve raw payloads.
3. Read DLT topic, partition, offset, and original topic/partition/offset.
4. Read exception class/message and correlation ID if present.
5. Persist `DltEnvelope` into a quarantine store with a unique key.
6. Classify JSON, schema, database, and business validation errors.
7. Maintain case statuses so operators know whether a record is under investigation or ready for replay.
8. Replay raw bytes for a deserialization-failed record after fixing the consumer.
9. Replay a typed event for a business-error record after verifying state.
10. Generate a replay ID and persist an audit trail.
11. Keep the key and required application headers; strip old exception headers from the new record.
12. Check partition counts and decide whether to keep the original partition or use a partitioner.
13. Use `eventId`/version to prevent duplicate processing and stale updates.
14. Simulate a failure when persisting the envelope and verify the DLT offset is not committed prematurely.
15. Measure lag, backlog, replay throughput, and processing time.
16. Write a runbook and retention/ACL policies for the DLT.

The exercise is complete when an operator can locate a failed record, identify its provenance and root cause, preserve evidence, fix the cause, replay in a controlled way, and verify business results without losing data or duplicating side effects.

## 19. Learning Sequence and Completion Criteria

| Stage | Core focus | Self-check criteria |
|---|---|---|
| 1. DLT model | Dead-letter records and metadata | Distinguish a DLT record from its source record. |
| 2. DLT consumer | Group ID and listener container | Read the DLT using a dedicated consumer group. |
| 3. Raw payload | `ByteArrayDeserializer` | Preserve payloads that failed deserialization. |
| 4. Metadata | Original topic/partition/offset and exception headers | Trace back to source and failure cause. |
| 5. Quarantine | Persistence and case lifecycle | Store durably, deduplicate, and assign an owner. |
| 6. Replay | Raw/typed publish | Republish matching the right contract and needed metadata. |
| 7. Ordering | Partition, sequence, and aggregate version | Do not assume replay restores old offsets/ordering. |
| 8. Reliability | Commit and idempotency | No data loss on persistence failure; no duplicate side effects. |
| 9. Operations | Retention, ACLs, monitoring, runbook | Manage DLT backlog safely. |
| 10. Testing | EmbeddedKafka/Testcontainers | Verify raw bytes, headers, offsets, and replay. |

This lesson is complete when you can read dead-letter records with a dedicated consumer, preserve raw payloads, decode source metadata, classify root causes, and execute controlled recovery. A DLT is only valuable when records can be investigated, have clear ownership, and follow a safe replay workflow.

A dead-letter record is evidence of a failed processing attempt. Preserve the original data, distinguish DLT metadata from source metadata, fix the root cause before replaying, and always enforce idempotency and business ordering.

