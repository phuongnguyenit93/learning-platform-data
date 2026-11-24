# Poison Pill Messages

In Kafka, a **poison pill message** is a record that causes a consumer to fail repeatedly every time it reads or processes it. The fault may lie in undeserializable payload bytes, an incompatible schema, a wrong data type, or a business condition the current record can never satisfy. Without an explicit handling policy, the consumer can get stuck at the same offset, repeat errors, grow consumer lag, and fail to process subsequent records on the partition.

Under **Deserialization and Schemas**, poison pills are especially dangerous because the error can occur **inside `Consumer.poll()`, before `@KafkaListener` ever receives the record**. In that case, wrapping listener logic in `try/catch` does not address the root cause. Spring Kafka provides **ErrorHandlingDeserializer** to capture deserialization failures, pass error details to the listener container, and coordinate with **DefaultErrorHandler** and **DeadLetterPublishingRecoverer** to recover the record.

The goal is not to "ignore errors to make them go away", but to **prevent a single invalid record from halting an entire partition, preserve data for investigation, and advance offsets only under the chosen recovery policy**.

## 1. How does a poison pill differ from an ordinary failing record?

A record may fail once because a database temporarily lost connectivity or an HTTP API returned 503. That is usually a transient error: retrying with backoff can succeed.

A poison pill has different characteristics:

- The same record, same payload, and same configuration always produce the same error.
- Retrying does not change the root cause, so the record will not succeed.
- The consumer keeps returning to the same topic/partition/offset.
- Subsequent records on the partition are delayed or never processed.
- If the consumer restarts or rebalances, the failure keeps recurring at that offset.

For example, the producer sends:

~~~json
{
  "orderId": "O-202",
  "amount": "not-a-number",
  "currency": "VND"
}
~~~

while the consumer expects **amount** as a decimal. If the deserializer or converter cannot turn that string into a number, every re-poll of the old record with the same schema will fail.

Not every record retried multiple times is a poison pill. A dependency might go down for a long window and then recover, allowing the same record to succeed. Classify based on root cause, data, schema, and recovery time.

## 2. At which layers can a poison pill appear?

| Layer | Example | Where does the error occur? | Appropriate handling |
|---|---|---|---|
| Kafka key deserializer | Key has wrong encoding or type | Inside `poll()` | `ErrorHandlingDeserializer` for key |
| Kafka value deserializer | Broken JSON, incompatible Avro/Protobuf | Inside `poll()` | `ErrorHandlingDeserializer` for value |
| Schema Registry / schema resolution | Schema ID not found, registry error | During deserialization | Distinguish transient errors vs. genuinely invalid schemas |
| Spring message conversion | Payload bytes valid yet unconvertible to argument | After poll, before or at listener call | Error handler with proper classification |
| Listener business validation | Invalid state, field, or invariant | Inside `@KafkaListener` | Throw domain exception, DLT recovery |
| Side effect | Database/API rejects data | In service called by listener | Classify transient/permanent, idempotency |

Key distinction: **errors inside the Kafka Deserializer usually occur before the listener is invoked**. A retry annotation on the listener or a `try/catch` inside the listener cannot handle errors at the poll boundary on its own.

## 3. What happens if the consumer cannot handle deserialization?

A normal Kafka consumer executes:

~~~text
Broker returns record bytes
       |
       v
KafkaConsumer.poll()
       |
       +-- KeyDeserializer.deserialize()
       |
       +-- ValueDeserializer.deserialize()
       |
       v
ConsumerRecords<K,V>
       |
       v
Spring Kafka container invokes @KafkaListener
~~~

If a deserializer throws an exception, `poll()` may fail to produce a deserialized `ConsumerRecord<K,V>` to hand to the listener. The Kafka client may throw **RecordDeserializationException** or **SerializationException** wrapping the root cause, depending on version and context.

A typical failure loop:

~~~text
Topic orders, partition 0, offset 52
          |
          v
poll() reads bytes at offset 52
          |
          v
Deserializer throws error
          |
          v
Listener has not been invoked
          |
          v
Consumer does not advance as intended
          |
          v
poll() or subsequent processing hits offset 52 again
~~~

An error handler that only handles exceptions after the listener receives a record may lack sufficient record metadata/payload to forward to a DLT. In Spring Kafka, a standard solution is placing **ErrorHandlingDeserializer** as the key/value deserializer to turn poll-time errors into error data the container can handle.

## 4. How does ErrorHandlingDeserializer solve the poll boundary?

Spring Kafka's **ErrorHandlingDeserializer** wraps a real deserializer, called the delegate. If the delegate deserializes cleanly, the value returns normally. If the delegate throws an exception, `ErrorHandlingDeserializer` records the error in record headers and returns an appropriate value for the container per framework mechanics.

Conceptually:

~~~text
KafkaConsumer.poll()
        |
        v
ErrorHandlingDeserializer
        |
        +-- delegate deserialization succeeds
        |             |
        |             v
        |         Normal record
        |
        +-- delegate throws exception
                      |
                      v
             Header containing error info
                      |
                      v
             Spring Kafka container
                      |
                      v
               DefaultErrorHandler
                      |
                      v
               Recoverer / DLT
~~~

The container can detect deserialization error details from headers before invoking the listener. When an error is present, the container routes the record through the error handler, generally skipping invoking the listener with an invalid object. When configured properly, the recoverer can send original raw bytes to the DLT for investigation and replay.

**Do not parse error headers manually in an uncontrolled way or rely on guessed header names.** Spring Kafka maintains internal headers and utilities with version-specific semantics; using framework-provided APIs carries far less risk during upgrades.

## 5. Configuring ErrorHandlingDeserializer in Spring Boot

Example topic with String keys and JSON values for `OrderEvent`:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: order-projection
      enable-auto-commit: false
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.orders.OrderEvent
        spring.json.trusted.packages: com.example.orders
~~~

Here:

- The Kafka consumer uses `ErrorHandlingDeserializer` for both **key** and **value**.
- `StringDeserializer` is the delegate converting key bytes into `String`.
- `JsonDeserializer` is the delegate converting value bytes into `OrderEvent`.
- Default type and trusted packages are examples; configure according to your producer contract and actual data trust boundaries.
- Auto-commit is disabled so the Spring Kafka listener container controls offsets per `AckMode`.

If the producer uses Avro, Protobuf, or a Schema Registry-backed format, the delegate must be that format's corresponding deserializer; do not use `JsonDeserializer` if the bytes are not JSON.

### 5.1. Why wrap the key too?

If only the value is wrapped while the key deserializer throws an exception, the consumer can still get stuck in `poll()`. In many applications keys are `String` and fail less often than values, yet keys can still have wrong encoding, versions, or be sent with the wrong serializer by a producer.

Do not assume keys are safe merely because topics usually carry valid keys. Wrap both when you need a consistent recovery mechanism for untrusted input data.

### 5.2. A null value is not a poison pill by default

Kafka supports records with null values, known as **tombstones**, especially in compacted topics. A valid null value is not the same as a deserialization failure.

If an application uses compacted topics, listeners and deserializers must handle tombstones per contract. Never send every null value to the DLT without checking whether a deserialization error header exists or whether it is a valid tombstone.

## 6. Recovery with DefaultErrorHandler and DeadLetterPublishingRecoverer

For non-transactional record listeners, **DefaultErrorHandler** handles retries and recovery. **DeadLetterPublishingRecoverer** can publish unprocessable records to the DLT.

Configuration example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Bean
DeadLetterPublishingRecoverer deadLetterRecoverer(
        KafkaTemplate<Object, Object> dltTemplate) {

    DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(dltTemplate);
    recoverer.setFailIfSendResultIsError(true);
    return recoverer;
}

@Bean
DefaultErrorHandler kafkaErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    DefaultErrorHandler handler =
        new DefaultErrorHandler(recoverer, new FixedBackOff(1_000L, 3L));

    handler.addNotRetryableExceptions(
        InvalidOrderEventException.class,
        UnsupportedEventVersionException.class
    );

    return handler;
}
~~~

This example uses three blocking retries with a 1-second delay for retryable exceptions. Permanent domain exceptions are marked non-retryable to reach recovery faster.

**DeserializationException**, **MessageConversionException**, and certain other format errors usually appear in `DefaultErrorHandler`'s default fatal/non-retryable list in modern Spring Kafka versions. Verify the exact list and APIs for your running version; do not assume one config applies identically across all versions.

Setting **setFailIfSendResultIsError(true)** helps avoid treating recovery as succeeded when the DLT producer reports an error. If DLT publishing fails, recovery must fail to preserve redelivery eligibility per configuration instead of silently committing the offset.

### 6.1. Attaching the error handler to the container factory

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory,
        DefaultErrorHandler kafkaErrorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(kafkaErrorHandler);
    factory.getContainerProperties()
           .setAckMode(ContainerProperties.AckMode.RECORD);
    return factory;
}
~~~

Listener using the corresponding factory:

~~~java
@KafkaListener(
    topics = "orders.events",
    groupId = "order-projection",
    containerFactory = "ordersListenerFactory"
)
public void consume(OrderEvent event) {
    projectionService.apply(event);
}
~~~

If a record fails deserialization and `ErrorHandlingDeserializer` recorded the error header, the listener is normally not invoked to process an invalid object. The error handler receives the record and can route it to the DLT.

These snippets are illustrative structures; applications must add appropriate imports, producer/consumer factory beans, domain classes, `KafkaTemplate`, and DLT topics. Ensure the error handler bean is actually used by the container, not merely declared in the Spring context.

## 7. The DLT must preserve raw bytes of poison pills

When deserialization fails, no `OrderEvent` object exists. The only data available for fixing the bug may be the record's **original bytes**.

`ErrorHandlingDeserializer` and `DeadLetterPublishingRecoverer` in compatible Spring Kafka versions can pass raw bytes from the failed record to the DLT. However, the `KafkaTemplate` publishing to the DLT must have a serializer that understands that data type.

Example:

~~~text
Source topic: corrupted value bytes
         |
         v
ErrorHandlingDeserializer fails to build OrderEvent
         |
         v
DeadLetterPublishingRecoverer builds DLT record
         |
         v
Value in DLT may be byte[]
         |
         v
Producer serializer supports only JSON objects?
         |
         +-- Yes -> May throw SerializationException
         |
         +-- Supports byte[] -> Preserves original raw payload
~~~

One configuration approach is **DelegatingByTypeSerializer**:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import org.apache.kafka.common.serialization.ByteArraySerializer;
import org.apache.kafka.common.serialization.Serializer;
import org.springframework.kafka.support.serializer.DelegatingByTypeSerializer;
import org.springframework.kafka.support.serializer.JsonSerializer;

Map<Class<?>, Serializer<?>> serializers = new LinkedHashMap<>();
serializers.put(byte[].class, new ByteArraySerializer());
serializers.put(OrderEvent.class, new JsonSerializer<OrderEvent>());

DelegatingByTypeSerializer valueSerializer =
    new DelegatingByTypeSerializer(serializers, true);
~~~

This selects `ByteArraySerializer` for raw `byte[]` and `JsonSerializer` for `OrderEvent`. Configure a matching **key serializer** if keys can also fail deserialization and become `byte[]` when entering the DLT. You cannot share one serializer across all types without checking runtime types.

Also store source metadata: original topic, partition, offset, timestamp, exception class, and schema version if identifiable. Raw payloads may contain sensitive data; apply proper ACLs, retention, encryption, and access procedures to the DLT.

## 8. How do schema mismatches create poison pills?

A record can be valid for the producer yet incompatible with the current consumer.

Scenarios:

- Producer changes a field type, e.g., number to string.
- Producer renames or removes a field required by the consumer.
- Old consumer does not support a new enum value.
- Producer uses a new schema version before the consumer is updated.
- Schema ID in payload is unrecognized by the registry.
- Deserializer is misconfigured with the wrong subject naming strategy or registry endpoint.
- Data from a different serializer is accidentally sent to the topic.

For example, the consumer expects:

~~~json
{
  "eventType": "OrderCreated",
  "orderId": "O-100",
  "amount": 125000
}
~~~

Yet the producer sends:

~~~json
{
  "eventType": "OrderCreated",
  "orderId": "O-100",
  "amount": {"value": 125000, "currency": "VND"}
}
~~~

If the consumer still expects `amount` to be a number, Jackson or the converter fails. Retrying the same bytes will not make schemas compatible again.

Prevention practices:

1. Define clear schema contracts and manage versions.
2. Check compatibility on schema changes.
3. Use tolerant consumers for intentional compatible changes.
4. Test producers/consumers against both old and new schemas prior to rollout.
5. Record event schema versions or schema IDs for investigation.
6. Establish processes to upgrade consumers before or alongside producers depending on the change type.

A true schema error should usually go to a DLT or wait for a contract fix rather than doing infinite blocking retries.

## 9. A Schema Registry outage is not necessarily a permanent poison pill

When using Avro/Protobuf or Schema Registry-integrated serializers, the consumer may need the registry to look up schema IDs and deserialize records.

Two distinct incidents:

**Schema ID does not exist or payload is corrupted:** the same bytes generally cannot be decoded even when the registry is healthy. This may be a permanent poison pill.

**Registry is disconnected or temporarily overloaded:** the record may be valid, yet the deserializer could not fetch the schema. Once the registry recovers, retries can succeed.

Therefore, do not push every exception from the deserializer straight to the DLT without checking the root cause. If the library wraps a registry timeout inside a `DeserializationException`, Spring Kafka's default classification may treat it as fatal. You may need dedicated policies at the registry/client layer or error handler to allow bounded retries, depending on version and how errors propagate.

Set finite timeouts on registry clients, monitor registry availability, and configure schema caching properly. Do not retry infinitely on consumer threads if the registry stays down for a long time.

## 10. Listener poison pills differ from poll-time errors

Not every poison pill lives in the deserializer. An event can deserialize into a completely valid object yet violate a business rule.

Example:

~~~java
@KafkaListener(topics = "orders.events")
public void consume(OrderEvent event) {
    if (event.totalAmount().signum() < 0) {
        throw new InvalidOrderEventException(
            "Order amount must not be negative"
        );
    }
    projectionService.apply(event);
}
~~~

In this case, the listener was invoked, so `DefaultErrorHandler` receives the listener's exception directly. `ErrorHandlingDeserializer` is not needed to catch this validation error, though it should still be configured if incoming bytes can be invalid.

Distinguish:

| Error | Is listener invoked? | Handling path |
|---|---|---|
| Broken JSON syntax right inside deserializer | Usually no | `ErrorHandlingDeserializer` + container error handler |
| Cannot fetch schema ID | Possibly no | Distinguish transient registry vs. permanent schema error |
| Spring message converter fails | Possibly before method | Error handler and converter/classification |
| Business validation exception | Yes | Domain exception + error handler/DLT |
| Database timeout | Yes | Retry with backoff, timeout controls |

Pinpointing the exact boundary prevents modifying listener code when the real fault lies in poll or serialization configuration.

## 11. Why do infinite retries make poison pills more dangerous?

If a record cannot be parsed, using **FixedBackOff.UNLIMITED_ATTEMPTS** or unbounded non-blocking retries causes the same payload to be reprocessed endlessly with no termination condition.

Consequences:

- Consumer lag per partition climbs.
- One partition fails to advance past the broken record.
- Retry logs and metrics surge.
- The container spends resources on errors that cannot self-heal.
- With long blocking backoffs, the consumer may hit `max.poll.interval.ms` issues depending on processing mechanics.
- If retry topics are used, backlog shifts into retry topics without solving the root cause.

Classifying permanent errors, setting finite retry budgets for recoverable errors, and routing poison pills to the DLT is far easier to operate.

Do not rely on restarting consumers or scaling consumer counts to fix a poison pill. A partition belongs to only one consumer in a group at a time; a new member will hit the exact same error at that offset.

## 12. Offset commits and data safety

Poison pills commonly arise under at-least-once delivery semantics. When a listener fails to process a record, decide when the source offset may advance.

| State | What is complete | Offset action |
|---|---|---|
| Listener succeeded | Business work complete | Commit per `AckMode` |
| Poison pill confirmed durably persisted to DLT | Recovery complete per policy | Offset can advance per recovery mechanism |
| DLT publish failed | No safe recovery yet | Do not intentionally mark as recovered |
| DLT send timed out, outcome unknown | Broker may or may not have written it | Preserve replayability, guard against duplicates |
| DLT publish succeeded yet source offset commit failed | DLT has record; group did not record progress | Source record may be re-read |

Never manually commit offsets just to make consumer lag drop if the poison pill has not been processed or saved to durable recovery storage.

A mistake:

~~~java
try {
    // Try to parse/validate record
    process(event);
} catch (Exception ex) {
    log.error("Invalid event", ex);
    // Swallow error and return normally
}
~~~

If the listener swallows the exception and returns normally, the container may commit the offset per `AckMode`, even though the record was neither processed nor saved in the DLT. Let the exception reach the error handler or implement a recovery protocol guaranteeing durability.

## 13. DLT publishing can also fail

Even with `ErrorHandlingDeserializer` configured, the DLT is still a Kafka producer flow and can fail due to:

- DLT topic does not exist.
- Topic has fewer partitions than the destination resolver requests.
- DLT `KafkaTemplate` lacks Write ACLs.
- Serializer does not support raw bytes or key type.
- Payload is too large or error headers push the request past limits.
- Unstable broker/ISR.
- Producer delivery timeout or network failure.

In versions providing the API, **DeadLetterPublishingRecoverer.setFailIfSendResultIsError(true)** makes the recoverer fail if the DLT send result fails. Sending asynchronously and returning immediately can cause the error handler to mark recovery successful too early.

If DLT publishing succeeds while source offset committing fails, the source record can be redelivered and the DLT receives a duplicate. Design DLT consumers to deduplicate by event ID or original topic/partition/offset.

## 14. What should the DLT hold for investigation?

A poison pill should be stored alongside origin and root-cause info:

- Original topic, partition, and offset.
- Key and raw value bytes or recoverable payload.
- Source timestamp.
- Exception class, root cause, and location info if available.
- Schema ID/version and producer application version if identifiable.
- Correlation ID and event ID/business key.
- Detection timestamp, consumer group, and application build.
- Retry/recovery metadata if present.

The DLT does not need to cram every exception stack trace into headers if headers grow too large or expose sensitive data. Store a sanitized error summary and a correlation ID pointing to logs/traces.

A record in the DLT is an **uncompleted business record**; its presence in the DLT only shows the pipeline has a recovery path. It still requires an owner, alerting, and a replay process.

## 15. Replaying after fixing schemas or data

After fixing the producer schema, consumer deserializer, or bad data, replay poison pills in a controlled manner.

Suggested workflow:

1. Confirm the root cause is fixed; otherwise replay creates poison pills all over again.
2. Read the DLT record while keeping original metadata.
3. Determine whether raw bytes can be replayed verbatim or the payload must be transformed to a valid schema.
4. Keep a stable event ID/idempotency key across replays.
5. Choose destination topic, key, and partitioning consistent with business ordering.
6. Publish the replay record and wait for producer confirmation.
7. Observe consumer processing and side-effect completion.
8. Record replay status to avoid re-emitting multiple times.

Never automatically republish every DLT record back to the source topic in a loop. If the payload was not fixed, the record fails again and spawns more DLT records.

A failing record may already have been partially processed by the app before throwing an exception, such as succeeding an API call then failing commit. Therefore, replay needs **idempotency** even after the payload is fixed.

### 15.1. Ordering after replay

Replayed records may arrive after newer records with the same key. If business logic requires event ordering, design aggregate versions, sequence numbers, or state machines to reject stale updates and recover via dedicated procedures.

Never treat DLT replay as re-inserting a record at its exact old offset; Kafka does not support writing a new record back into a prior partition offset.

## 16. Preventing duplicates during recovery

A common pattern is a **consumer inbox** or `processed_events` table keyed by a unique event ID:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(128) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Inside one database transaction, the consumer attempts to insert the event ID and then apply business updates:

- If the event ID does not exist yet, record it and apply side effects.
- If the event ID already exists, do not apply side effects a second time.
- If the transaction fails, roll back both the processed marker and business updates.

A plain `SELECT` checking event ID before updating is not enough to prevent race conditions when two consumers process an event simultaneously. Use a unique constraint and transaction.

For HTTP APIs, pass a stable idempotency key if the API supports it; if a call outcome is unclear due to a timeout, query state before retrying side-effecting requests.

Kafka **producer idempotence** does not automatically deduplicate at the consumer business-logic layer or across DLT replays. Those are two separate scopes.

## 17. Poison pills in batch listeners and transactions

### 17.1. Batch listeners

With a batch listener, a single poll can return many records. If a poison record sits mid-batch, its failure affects how the entire batch is recovered and committed per configuration.

Spring Kafka provides batch failure handling and **BatchListenerFailedException** to pinpoint the failing record when appropriate. However, deserialization errors occurring at the poll boundary differ from errors after the listener receives batch objects. Configure `ErrorHandlingDeserializer` and verify that error headers are handled properly by your batch listener.

Do not automatically skip an entire batch for one broken record if the other records remain valuable. Nor should you commit the entire batch before establishing the policy for the failing record.

### 17.2. Transactional listeners

With Kafka transactions managed by the listener container, exceptions can abort the transaction and cause records to be re-read. **DefaultAfterRollbackProcessor** is typically the component handling post-rollback recovery.

Do not assume a non-transactional `DefaultErrorHandler` configuration applies verbatim to a transactional listener. Verify:

- Which transaction includes the source offsets?
- Is DLT publishing included in the recovery transaction as required?
- If the transaction aborts, are records redelivered?
- Are external side effects (databases/HTTP) protected by idempotency?

Kafka transactions provide guarantees within configured Kafka boundaries; they do not automatically roll back external systems.

## 18. Common mistakes

| Mistake | Consequence | Correction |
|---|---|---|
| Catching exceptions only inside `@KafkaListener` | Cannot catch pre-listener deserialization failures | Wrap delegates with `ErrorHandlingDeserializer` |
| Using `ErrorHandlingDeserializer` only for values | Poison keys still fail `poll()` | Configure key too when needed |
| Retrying every `DeserializationException` infinitely | Poison pill stalls partition and grows lag | Classify permanent, route to DLT quickly |
| Treating null values as always errors | Valid tombstones get sent to DLT | Distinguish tombstones from deserialization error headers |
| DLT `KafkaTemplate` uses only JSON serializer | Raw `byte[]` fails to publish | Use serializer handling both objects and bytes |
| Assuming DLT send succeeded right after `KafkaTemplate.send()` | Future may fail later while offset advanced | Verify send result and handle recovery failures |
| Committing offsets before DLT persistence | Silent loss of failing record | Commit per safe recovery policy |
| Resetting offsets to skip records | May skip multiple unprocessed records | Prefer DLT/recovery; reset only with controls |
| Scaling consumer concurrency to fix poison pills | Failing partition still goes to one member | Fix data/serializer and policy |
| Replaying DLT without preserving event ID | Duplicate side effects | Use stable idempotency keys |
| Not monitoring Schema Registry | Mistakes registry outage for permanent payload error | Classify root causes and track registry metrics |
| Not protecting DLT payloads | Leaks sensitive data | Apply ACLs, retention, encryption, and log redaction |

## 19. Observability and alerting

High consumer lag is a symptom, not definitive proof of a poison pill. Correlate it with deserialization errors and per-partition progress.

| Signal | Question to answer |
|---|---|
| Deserialization failure count | Which payloads/keys cannot be decoded? |
| Exceptions by root cause | JSON, schema, registry, or conversion failure? |
| Repeated topic/partition/offset | Is the consumer stuck at the exact same position? |
| Consumer lag by partition | Which partition is not advancing? |
| Retry count and duration | How long has the record been failing? |
| DLT publish attempts/success/failures | Is recovery persisting records? |
| DLT lag and oldest record age | How long have failed records been waiting? |
| Rebalance count | Are poll delays/errors causing group churn? |
| Schema Registry error rate/latency | Is the registry down or is the contract broken? |
| Processing success rate post-replay | Was the underlying bug truly fixed? |

Logs should include topic, partition, offset, exception class, root cause, schema version, consumer group, and correlation ID. Do not log full raw bytes if they contain sensitive data; log checksums and keep payloads in an access-controlled DLT.

Useful alerts:

- Same offset failing repeatedly within a time window.
- Deserialization errors spiking right after a producer/consumer deployment.
- DLT publish failures sustained above 0.
- Oldest DLT record age exceeding SLO.
- Lag rising on only one partition while all other partitions keep advancing.

## 20. Poison pill handling runbook

### Step 1: Identify the error type

Read the root exception: did it occur in poll/deserializer, message converter, or listener business logic? Never look only at the outermost wrapper exception line.

### Step 2: Locate the record

Record topic, partition, offset, key identifier, and first-seen timestamp. Check whether the consumer group is looping at the same offset or already routed the record to the DLT.

### Step 3: Inspect schema and raw payload

Identify producer serializer, consumer delegate deserializer, schema ID/version, byte contents, and compatibility. With a Registry, determine whether the registry is temporarily failing or the schema ID truly does not exist.

### Step 4: Check ErrorHandlingDeserializer

Verify both required key/value paths are wrapped; delegate classes are accurate; the container uses the right consumer factory; and error headers are handled by the error handler.

### Step 5: Verify the DLT

Check topic, partitions, ACLs, raw-byte serializers, producer send results, and publish durability. If the DLT has not persisted it, do not mark the record recovered.

### Step 6: Choose a safe action

- If permanent error: DLT and fix payload/schema.
- If Registry or dependency is transiently failing: bounded retry with backoff.
- If misconfigured: fix consumer/producer before resuming.
- If side effects are unclear: reconcile by event ID to avoid duplicates.

### Step 7: Recover and confirm

After fixing, perform controlled replay. Confirm the consumer processes cleanly, offsets advance validly, lag drops, DLT backlog is managed, and no duplicate side effects occur.

## 21. Pre-production checklist

1. Have producers and consumers agreed on format, encoding, and schema evolution rules?
2. Can deserializers receive invalid external bytes?
3. Is `ErrorHandlingDeserializer` attached to required keys and values?
4. Are poll-time parse errors routed to the container error handler?
5. Does `DefaultErrorHandler` classify deserialization/permanent exceptions properly?
6. Does the DLT `KafkaTemplate` have serializers able to handle original raw bytes?
7. Does the DLT topic exist with enough partitions, ACLs, replication, and retention?
8. Does the recoverer fail if DLT producer publishing fails?
9. Do source offsets advance only when processing or recovery succeeds per policy?
10. Are there metrics detecting repeated failures at the same offset and DLT publish failures?
11. Is there a process to distinguish permanent schema errors from transient Registry outages?
12. Does DLT replay preserve event IDs and ensure idempotency?
13. Is there a fix/replay process that respects business ordering?
14. Are failed records in the DLT and logs properly secured?
15. Have tombstones, key failures, value failures, batch listeners, and transactional listeners been evaluated?

**Conclusion:** A poison pill message is not just an exception thrown multiple times. It is a record capable of halting partition progress, especially when deserialization fails right inside `poll()`. In Spring Kafka, combining `ErrorHandlingDeserializer`, exception classification, `DefaultErrorHandler`, a durable DLT, and idempotent replay provides a safe escape hatch: failing records are preserved for investigation rather than dropped, while consumers keep processing valid data under clear operational policies.
