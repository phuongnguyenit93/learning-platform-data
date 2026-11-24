# Handling Undeserializable Data

Kafka stores records as bytes. When a consumer reads a record, the deserializer converts keys and values from bytes into data types the application understands. If a payload is malformed, a schema is incompatible, or the deserializer is misconfigured, this conversion can fail before the listener method is ever called.

A malformed record of this kind is often called a **poison pill**: whenever the consumer encounters that record again, reading can repeatedly fail and slow down or block partition progress. The application must detect the error, preserve the original data for investigation, decide when to retry recoverable errors, and move unprocessable records to a dead-letter topic (DLT).

This lesson belongs to the **Serialization** chapter of the **SPRING_KAFKA_MESSAGING** module, focusing on how Spring Kafka handles deserialization failures, combining `ErrorHandlingDeserializer` with an error handler, storing failed records in a DLT, and building a safe recovery workflow.

## Learning Outcomes

After this lesson, you will be able to:

- Explain why deserialization errors happen before the listener executes business logic.
- Distinguish deserialization errors from errors inside listener logic.
- Identify poison pills and their impact on consumer polls, offsets, and partitions.
- Configure `ErrorHandlingDeserializer` for keys and values.
- Combine `DefaultErrorHandler` with `DeadLetterPublishingRecoverer`.
- Choose retry or DLT based on the recoverability of the root cause.
- Preserve raw bytes, keys, headers, and metadata to investigate failed records.
- Handle JSON type headers, trusted packages, and schema evolution.
- Test deserialization errors, DLT routing, and replay workflows with a real broker.

## 1. Where Does Deserialization Happen in the Consumer Flow?

Producers serialize keys and values into bytes before sending records to Kafka. The broker stores and forwards bytes; the broker does not need to know whether a payload is JSON, Avro, or a specific Java class.

When the consumer polls data, the Kafka client runs the configured deserializer to turn bytes into objects. The Spring Kafka listener container then delivers the decoded record to the `@KafkaListener` method.

~~~mermaid
flowchart LR
    P[Producer object] --> S[Serializer]
    S --> B[Kafka broker stores bytes]
    B --> C[Consumer poll]
    C --> D[Deserializer]
    D -->|Success| L["@KafkaListener"]
    D -->|Failure| E[Deserialization exception]
    E --> H[Error handling]
    H --> R[Retry or DLT]
~~~

If the deserializer throws an exception during consumer poll, the listener normally has not received the record to catch the error itself. This is a crucial difference from business errors arising inside the listener method.

If the consumer lacks a mechanism to surface deserialization errors to the listener container, the bad record can cause polls to fail repeatedly. The application may fail to advance to subsequent records in the partition as expected. Handling must occur early enough for the container to identify which record failed and apply retries or recovery.

## 2. Common Causes

Deserialization errors can originate from the producer, data contract, schema, or consumer configuration.

| Cause | Example | Where to check |
|---|---|---|
| Malformed payload format | Consumer expects JSON but receives plain text or non-JSON bytes | Check serializer and actual payload. |
| Invalid JSON | Missing brace, misplaced comma, or truncated payload | Inspect raw bytes and record source. |
| Wrong data type | Field `amount` is a string while DTO expects `BigDecimal` | Compare JSON against event contract. |
| Missing or changed field | Producer changed structure before consumer was compatible | Review schema evolution and producer version. |
| Mismatched type header | Header points to a class missing or disallowed on consumer | Check type mappings and trusted packages. |
| Wrong serializer/deserializer | Producer uses Avro while consumer uses `JsonDeserializer` | Align formats and configuration on both sides. |
| Schema Registry or schema service error | Consumer cannot fetch the required schema | Check connectivity, authentication, and registry status. |
| Legacy data remaining in topic | New consumer reads records emitted by an older version | Verify compatibility and historical data. |
| Key deserialization failure | Key has unexpected encoding or format | Check key serializer and key deserializer. |

Not every deserialization failure has the same recoverability. Structurally invalid JSON is usually a deterministic error; retrying the same payload will keep failing. A Schema Registry timeout may be transient and call for a different retry policy.

## 3. Distinguishing Deserialization Errors from Business Errors

These two error types happen at different stages and require tailored handling mechanisms.

| Criterion | Deserialization error | Business error in listener |
|---|---|---|
| Timing | While consumer converts bytes into objects | After listener receives the record/object |
| Listener invoked | Normally not invoked for the failed record | Invoked |
| Examples | Invalid JSON, incompatible schema, wrong type | Insufficient inventory, database temporarily unreachable |
| Available data | Raw bytes, key, headers, and exception metadata | Deserialized object and business context |
| Handling mechanism | `ErrorHandlingDeserializer` and container error handler | `DefaultErrorHandler`, retries, business-level recovery |
| Retryability | Depends on cause; malformed payloads usually cannot be retried | Dependency outages may recover after retries |

Do not funnel every error into a single retry policy. For malformed payloads, repeated retries only waste processing time and increase lag. If Schema Registry is temporarily unreachable, immediately sending every record to a DLT may unnecessarily inflate the backlog requiring replay.

## 4. What Problem Does ErrorHandlingDeserializer Solve?

Spring Kafka provides **ErrorHandlingDeserializer** to wrap the real deserializer. It delegates decoding to the underlying deserializer. If the delegate throws an exception, `ErrorHandlingDeserializer` preserves the error details and original data in record headers, returning `null` for the failed key or value.

The listener container detects the deserialization error header and routes the record to the error handler. As a result, the application can apply retries or recover the record rather than letting errors surface only inside poll.

Structure:

~~~mermaid
flowchart TD
    K[Kafka record bytes] --> E[ErrorHandlingDeserializer]
    E --> D[Delegate deserializer]
    D -->|Success| V[Decoded key/value]
    D -->|Failure| X[Store exception and raw bytes in header]
    X --> N[Return null for failed field]
    N --> C[Spring listener container detects failure]
    C --> H[Common error handler]
    H --> R[Retry or Dead-letter recoverer]
~~~

`ErrorHandlingDeserializer` does not repair payloads and does not decide on its own whether to skip or DLT a record. It supplies the metadata needed for the listener container and error handler to handle failures in a controlled way.

If `JsonDeserializer` is used directly and fails during poll, the container may lack a decoded record to pass to the error handler in the standard way. Therefore, when poison-pill handling via Spring Kafka's error handler is needed, configure `ErrorHandlingDeserializer` as the outer wrapper.

## 5. Configuring ErrorHandlingDeserializer in Spring Boot

Example consumer using `String` keys and JSON values:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: orders-fulfillment
      enable-auto-commit: false
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.events.OrderCreatedEvent
        spring.json.trusted.packages: com.example.events
        spring.json.use.type.headers: false
~~~

Explanation:

- `ErrorHandlingDeserializer` is the deserializer invoked directly by the Kafka client.
- `spring.deserializer.key.delegate.class` specifies the actual key deserializer.
- `spring.deserializer.value.delegate.class` specifies `JsonDeserializer` for values.
- `spring.json.value.default.type` declares the default type when type headers are not used.
- `spring.json.trusted.packages` restricts packages permitted for deserialization.
- `spring.json.use.type.headers=false` instructs the consumer to use the default type instead of reading types from headers.

Delegate and `JsonDeserializer` properties are passed through consumer properties. Verify exact property names and binding behavior against your project's Spring Kafka/Spring Boot version.

If the application uses type headers to support multiple event types, configure type mappings instead of disabling headers. Example:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        spring.json.trusted.packages: com.example.events
        spring.json.type.mapping: orderCreated:com.example.events.OrderCreatedEvent
        spring.json.use.type.headers: true
~~~

Producer and consumer must agree on type mappings. Never widen trusted packages excessively just to silence configuration errors; trust only packages containing types actually permitted for deserialization.

## 6. Combining DefaultErrorHandler and DeadLetterPublishingRecoverer

Once `ErrorHandlingDeserializer` converts the failure into container-visible metadata, Spring Kafka can use `DefaultErrorHandler` to decide on retry or recovery.

`DeadLetterPublishingRecoverer` is the standard component for publishing failed records to another topic, typically suffixed with `.DLT`.

Configuration example:

~~~java
@Bean
DeadLetterPublishingRecoverer deadLetterPublishingRecoverer(
        KafkaTemplate<Object, Object> dltKafkaTemplate) {

    return new DeadLetterPublishingRecoverer(
            dltKafkaTemplate,
            (record, exception) -> new TopicPartition(
                    record.topic() + ".DLT",
                    record.partition()
            )
    );
}

@Bean
DefaultErrorHandler kafkaErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    // Do not retry deterministic bad payloads; send to recoverer immediately.
    return new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(0L, 0L)
    );
}
~~~

Attach the error handler to the listener container factory:

~~~java
factory.setCommonErrorHandler(kafkaErrorHandler);
~~~

This last line belongs inside the application's actual container factory bean configuration. If using Spring Boot auto-configuration, verify that the factory used by `@KafkaListener` actually receives this common error handler.

In the example, `FixedBackOff` with 0 retries illustrates deterministic malformed payloads going straight to the recoverer without retry. For transient errors, classify exceptions and apply appropriate backoff. Do not apply a single policy to all causes.

`DefaultErrorHandler` classifies several exceptions as fatal/non-retryable by default, including Spring Kafka's deserialization exceptions. Exact default classification behavior can vary across versions; if you need to retry a specific failure, configure the classifier intentionally and test the underlying exception cause.

## 7. DLTs Must Preserve Raw Bytes

A critical point when handling deserialization failures is that the original value may never have become a Java object. `ErrorHandlingDeserializer` stores the original data inside `DeserializationException` so the framework can recover and publish the failed record.

The DLT producer must be able to serialize both:

- Normal objects from records that deserialized fine but failed later in processing.
- Raw `byte[]` from records that failed deserialization.

If the DLT `KafkaTemplate` uses only `JsonSerializer` or a serializer tied to one DTO, publishing raw `byte[]` may fail or alter the original content. Configure a serializer capable of handling both `byte[]` and valid object types, such as `DelegatingByTypeSerializer` or a dedicated DLT template for raw bytes.

When designing a DLT, verify:

- Whether the original key is preserved intact.
- Whether the original value retains the exact byte sequence.
- Whether deserialization error headers are preserved for investigation.
- Whether source metadata such as topic, partition, and offset is attached.
- Whether the DLT serializer handles both `byte[]` and normal objects properly.
- Whether the DLT topic exists and has enough partitions for the routing strategy.

In the resolver example above, records route to the same partition number as the source topic. Therefore, the DLT needs at least as many partitions as the source topic. If you prefer a single-partition centralized DLT or separate DLT topics per error category, adjust the destination resolver accordingly.

## 8. What Information Should a Dead-Letter Record Retain?

A useful DLT must let operators determine where a record came from, why it failed, and how to recover it.

Information to retain:

| Information | Purpose |
|---|---|
| Original topic | Identifies the source data stream. |
| Original partition | Identifies the source partition. |
| Original offset | Locates the exact record in the source log. |
| Original key/value bytes | Inspects the payload and attempts re-deserialization. |
| Exception class/message | Classifies the failure cause. |
| Stack trace | Assists in debugging complex failures. |
| Timestamp | Identifies when the record was created or written. |
| Correlation ID/event ID | Correlates logs across producer, consumer, and downstream services. |

Spring Kafka attaches DLT headers carrying source metadata and exception details. Use the `KafkaHeaders` constants appropriate for your Spring Kafka version instead of hardcoding header strings throughout the application.

DLTs can contain sensitive data just like source topics. Apply appropriate ACLs, retention, encryption, and access policies. Never send raw payloads or stack traces containing sensitive details to public logs.

## 9. Classifying Errors to Decide Between Retry and DLT

Retry decisions should depend on root cause, not merely on the fact that an exception occurred in a deserializer.

| Cause | Recoverability | Handling strategy |
|---|---|---|
| Structurally invalid JSON | Low unless payload changes | Do not retry or retry very sparingly; route to DLT. |
| Wrong data type or contract field | Low unless consumer or payload changes | DLT, fix contract or consumer, then replay. |
| Type header pointing to nonexistent class | Low until mapping/deployment is fixed | DLT or pause stream to fix configuration. |
| Payload outside trusted packages | Low unless configuration changes | Update allowlist carefully, then replay. |
| Schema Registry temporarily disconnected | Potentially recoverable | Retry with backoff and time cap if classified as transient. |
| Incompatible schema | Usually does not self-heal | DLT, adjust schema/consumer, and replay. |
| Database error inside listener after deserialization | Potentially recoverable depending on cause | Retry via business error handler; do not treat as deserialization error. |

Never infinitely retry a poison pill. A malformed record will not become valid a few seconds later; continuous retries keep the partition busy and build lag.

Conversely, if a schema service is temporarily unreachable, immediately dumping all records to a DLT can rapidly grow the replay backlog. Classify root causes and bound retry durations.

## 10. Key Deserialization Can Also Fail

Many examples focus solely on values, yet keys are also bytes with their own deserializer. If a key has the wrong encoding or a producer changes key format, the consumer can fail before the listener receives the record.

Configure `ErrorHandlingDeserializer` for both key and value whenever either can fail. When key deserialization fails, the key on `ConsumerRecord` may be `null` while error details and raw key bytes are stored in the corresponding header.

When investigating, distinguish:

- Value deserialization failure.
- Key deserialization failure.
- Failures in both key and value.
- Valid `null` keys permitted by the producer contract.

Never treat every `null` key as an error. If the system allows `null` keys, inspect the exception header to distinguish a deserialization-induced `null` from a legitimate `null` key.

## 11. Batch Listeners and Failed Records

With a record listener, the container can route failed records to the error handler via its standard record error-handling flow. With a batch listener, a single method invocation can receive multiple records from poll; if a record fails deserialization, the container must identify and handle the failed item using exception headers and batch error-handling policies.

If a batch listener encounters a business error on a specific record, `BatchListenerFailedException` can indicate the failing record or index. This helps the error handler distinguish already-processed items in the batch from the portion needing retry or recovery.

Do not detect deserialization exceptions by checking `value == null` and assuming it is a poison pill. `null` may be a legitimate value if permitted by the producer contract. Inspect the deserialization exception header to distinguish accurately.

If a batch listener processes a list manually, clearly design how partial success is recorded. When earlier items in a batch have produced side effects and a later item fails, redelivered records may repeat effects. Protect business logic with `eventId` and idempotency.

## 12. Fixing Root Causes and Replaying Records from DLT

A DLT is not an indefinite dumping ground without an operational process. A recovery workflow should include these steps:

1. Group failed records by exception, source topic, and event version.
2. Determine whether the failure stems from payload, schema, type mapping, serializer, or configuration.
3. Fix the producer contract or consumer deserializer.
4. Write a test using the actual raw bytes from a failed record.
5. Select replayable records and assess expected side effects.
6. Replay to the source topic or a dedicated recovery topic under controlled procedures.
7. Use `eventId`/idempotency to prevent duplicate side effects.
8. Monitor outcomes and record which items have been recovered.

You can build a recovery consumer reading the DLT as `byte[]` to inspect payloads before re-deserializing. This is especially helpful when original classes or schemas are no longer compatible with the current application.

Never replay an entire DLT into production immediately after fixing one bug. Test a small batch first, verify schema, ordering, and side effects, and then scale up.

## 13. Testing Deserialization Errors and DLT

Unit tests can verify error-classification logic or callbacks, but verifying `ErrorHandlingDeserializer` and the container error handler requires integration tests with a real broker.

Scenarios to include:

| Test | What to verify |
|---|---|
| Valid JSON | Delegate deserializes to the expected object. |
| Malformed JSON | `ErrorHandlingDeserializer` preserves exception and raw bytes. |
| Invalid type header | Consumer handles mapping failure per policy. |
| Malformed key encoding | Key failures are distinguished from valid `null` keys. |
| Incompatible value schema | Record is retried or recovered per classifier. |
| DLT publish | Failed record lands in the right DLT topic and partition. |
| Raw bytes preservation | Value in DLT preserves the exact original bytes. |
| DLT headers | Contains original topic, partition, offset, and exception details. |
| Retry limit | Retry count matches configured backoff. |
| Replay | Fixed records can be re-read and processed idempotently. |

Example constructing a malformed payload in an integration test:

~~~java
ProducerRecord<String, byte[]> badRecord =
        new ProducerRecord<>(
                "orders.raw",
                "order-1001",
                "{invalid-json".getBytes(StandardCharsets.UTF_8)
        );

KafkaTemplate<String, byte[]> rawProducer =
        rawBytesKafkaTemplate;

rawProducer.send(badRecord).get(10, TimeUnit.SECONDS);
~~~

The test producer uses `ByteArraySerializer` to send raw bytes without re-serializing the string as JSON. The test consumer uses `ErrorHandlingDeserializer` wrapping `JsonDeserializer`. After the error handler recovers the record, the test reads the DLT using `ByteArrayDeserializer` and compares the byte array against the sent payload.

To avoid hanging, use Awaitility or bounded polling to wait for the DLT to receive the record. Never use fixed `Thread.sleep` calls to guess when recovery finishes.

## 14. Monitoring and Operating Poison Pills

A poison pill can drive up consumer lag even while brokers remain healthy. Monitor deserialization errors separately from business errors.

Metrics to track:

- Deserialization failure count by topic and exception type.
- Retried record count.
- Records recovered to DLT.
- DLT publish failure count.
- Consumer lag by partition.
- Replay success and failure counts.
- Time from error detection to completed recovery.

Logs should include topic, partition, offset, `eventId` if readable from key/header, exception class, and source metadata. When the value cannot be deserialized, `eventId` may be unreachable inside the payload; consider placing a correlation ID in Kafka headers so traceability remains intact.

Alert when:

- Deserialization failure rate spikes suddenly.
- One partition repeats the same error continuously.
- DLT publishing fails.
- DLT backlog grows without an assigned owner.
- A producer version emits incompatible schemas.
- Consumer group lag climbs despite normal CPU and broker load.

A DLT requires an owner, retention policy, ACLs, dashboards, and an operational runbook. Without them, a DLT only moves problems out of the main stream without recovering business data.

## 15. Safe Configuration Checklist

Before deploying a consumer that handles undeserializable data, confirm:

- Key/value deserializers are wrapped by `ErrorHandlingDeserializer` wherever failures must be caught.
- Delegate deserializers match the producer serializers.
- JSON type headers or default types are configured consistently.
- Trusted packages are restricted to valid models.
- `DefaultErrorHandler` is attached to the right listener container factory.
- Deterministic errors do not retry infinitely.
- Transient errors have explicit backoff and retry limits.
- `DeadLetterPublishingRecoverer` routes to the right topic and partition.
- DLT serializers support raw `byte[]` and objects as needed.
- DLT topics have enough partitions for the active destination resolver.
- DLT headers and raw bytes are preserved for investigation.
- ACLs, retention, and sensitive data are managed properly.
- Tests cover key errors, value errors, type headers, DLT routing, and replay.
- Dashboards and an owner exist for handling the DLT.

## 16. Capstone Exercise: Handling Poison Pills in orders.created

Build a consumer for the `orders.created` topic using a JSON deserializer and `ErrorHandlingDeserializer`.

Requirements:

1. Configure key and value deserializers with `ErrorHandlingDeserializer`.
2. Send a valid JSON event and verify the listener receives `OrderCreatedEvent`.
3. Send raw bytes containing malformed JSON.
4. Verify the listener does not process the malformed payload as a valid event.
5. Configure `DefaultErrorHandler` and `DeadLetterPublishingRecoverer`.
6. Route failed records to `orders.created.DLT`.
7. Read the DLT as `byte[]` and compare with the original payload.
8. Verify DLT headers include topic, partition, offset, and exception metadata.
9. Send an event with a bad type header to test type mapping.
10. Simulate a transient schema service outage and distinguish it from permanently corrupted payloads.
11. Fix the data or schema and replay a DLT record in a test environment.
12. Verify replay does not duplicate side effects thanks to `eventId`/idempotency.
13. Monitor consumer lag, retry count, and DLT backlog.
14. Write a poison-pill operational runbook for the operations team.

The exercise is complete when you can divert undeserializable records out of the main stream while preserving raw bytes and metadata, distinguish retryable errors from DLT-bound errors, and replay records safely after fixing the root cause.

## 17. Learning Sequence and Completion Criteria

| Stage | Core topic | Self-check criterion |
|---|---|---|
| 1. Deserialize flow | Serializers, bytes, and deserializers | Can explain why failures occur before the listener. |
| 2. Error types | Payload, schema, type, key/value | Can classify root causes and recoverability. |
| 3. ErrorHandlingDeserializer | Delegates and exception headers | Container detects failed records. |
| 4. Error handler | `DefaultErrorHandler` and retries | Configure bounded retries per root cause. |
| 5. DLT | `DeadLetterPublishingRecoverer` | Publish failed records while preserving raw bytes. |
| 6. Schema | JSON type headers, schema evolution | Consumer reads compatible data cleanly. |
| 7. Recovery | DLT replay and idempotency | Recover records without duplicating side effects. |
| 8. Testing | Raw bytes, headers, DLT integration tests | Verify both payload and source metadata. |
| 9. Operations | Metrics, ACLs, retention, runbook | Monitor and process DLT backlogs effectively. |

This lesson is complete when you can configure `ErrorHandlingDeserializer`, wire an error handler to a DLT, preserve raw bytes and metadata, and decide accurately when to retry versus when to recover. The goal is to prevent a single corrupted record from derailing the consumer stream while keeping failed data available for investigation and recovery.

Kafka brokers store bytes; producers and consumers must agree on the serialization contract. When that contract breaks, preserve the original data, identify the root cause, apply selective retries, and treat the DLT as part of an owned recovery process.
