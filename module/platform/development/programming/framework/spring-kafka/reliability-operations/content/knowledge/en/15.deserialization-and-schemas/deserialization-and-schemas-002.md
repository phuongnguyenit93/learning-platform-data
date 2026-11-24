# DeserializationException in headers

## 1. Overview

In Spring Kafka, producers send keys and values to brokers as bytes. When a consumer reads a record, the Kafka client must use a deserializer to convert those bytes into Java objects before passing the data to the listener.

If a producer sends invalid JSON, introduces an incompatible schema change, or the consumer misconfigures class/type mapping, the delegate deserializer can throw an exception right inside the `poll` call. This error occurs **before the @KafkaListener method is invoked**, so a `try/catch` inside the listener cannot handle it on its own.

**ErrorHandlingDeserializer** solves this problem by wrapping the real deserializer. When the delegate fails, the wrapper writes **DeserializationException information as bytes in a Kafka record header**, while supplying a fallback value such as null. The Spring Kafka container and error handler thereby have the information needed to retry, recover, or route the failed record to a dead-letter topic (DLT).

~~~text
Producer
   |
   | key bytes + value bytes
   v
Kafka topic
   |
   v
KafkaConsumer.poll()
   |
   v
ErrorHandlingDeserializer
   |
   +-- delegate deserialization succeeded --> Java value --> listener
   |
   +-- delegate throws exception
             |
             +--> create DeserializationException
             +--> write serialized exception to header
             +--> return null / fallback
             |
             v
       ConsumerRecord carrying error header
             |
             v
       Spring Kafka error handling
~~~

This lesson focuses on the meaning of error headers, how to detect them properly in record listeners and batch listeners, configuring ErrorHandlingDeserializer, preserving raw data when publishing to a DLT, and schema-related reliability considerations.

## 2. Why place DeserializationException in a header?

If JsonDeserializer is used directly and the payload is corrupted, KafkaConsumer can throw an exception during poll, before creating a Java record that the listener can receive. Without supporting mechanisms, a single unreadable record can get the consumer stuck at that position and repeatedly hit the same error.

Placing the information in a header allows the client to preserve the failed record's context:

1. **Location:** the record's topic, partition, and offset can still be identified.
2. **Original input:** the failing bytes are stored in DeserializationException for recovery.
3. **Error source:** whether the failure occurred in the key or value is known.
4. **Cause:** the original exception is preserved as the cause.
5. **Policy:** the error handler can decide to retry, skip with tracking, or route to DLT.
6. **Do not equate failed records with valid null:** listeners can rely on the header rather than only the payload.

Importantly, the header here is **not a Java exception object attached directly to the Kafka record**. A Kafka header contains a byte array. Spring Kafka serializes DeserializationException into a byte array and uses corresponding utilities to read it back.

### 2.1. Information inside DeserializationException

Depending on the Spring Kafka version, DeserializationException can provide these fields:

| Field | Meaning |
|---|---|
| Raw data | Original bytes of the key or value that failed to deserialize |
| Cause | Exception from the delegate deserializer or validator |
| isKey | Whether the error occurred in the key or value |
| Message | Error description message |
| Stack trace | Error context for diagnostics |

Raw data may contain sensitive data such as emails, phone numbers, addresses, or order details. Do not log or arbitrarily emit this data into metrics, alerts, or broadly accessible logging systems.

### 2.2. Headers are created at the consumer, not by modifying records on the broker

ErrorHandlingDeserializer adds headers when the consumer deserializes the record. That **does not mean the original record stored on the Kafka broker is modified**.

If you use another raw Kafka consumer without ErrorHandlingDeserializer configured, that tool will not see the internal headers created by the Spring Kafka consumer during reading. This is important when comparing output between the application and console consumer tools.

## 3. Header names for key and value errors

Spring Kafka distinguishes two cases:

| Common internal header | Meaning |
|---|---|
| springDeserializerExceptionKey | Key deserializer failed |
| springDeserializerExceptionValue | Value deserializer failed |

When writing code, use constants provided by Spring Kafka instead of repeating string literals across the application:

~~~java
SerializationUtils.KEY_DESERIALIZER_EXCEPTION_HEADER
SerializationUtils.VALUE_DESERIALIZER_EXCEPTION_HEADER
~~~

In applicable Spring Kafka versions, these constants live in the **org.springframework.kafka.support.serializer** package. If your running version's API differs from the example, check the actual dependency's JavaDoc and use the corresponding constant.

Do not treat these header names as an event contract that producers must send. This is consumer-side error-handling metadata.

### 3.1. Key errors and value errors have different impacts

**Value error:** the consumer cannot build a valid Java payload for business processing. Usually requires a DLT with raw bytes or compatible serializer/schema changes.

**Key error:** the application cannot recover the Java key. If the key determines entity ID, ordering, or deduplication, replacing a failed key with a default value can corrupt business logic.

Example:

~~~text
Record A:
  topic=orders.created
  partition=1
  offset=130
  key=order-17
  value=null
  header=springDeserializerExceptionValue

Record B:
  topic=orders.created
  partition=1
  offset=131
  key=null
  value=OrderCreated(...)
  header=springDeserializerExceptionKey
~~~

The two records must be classified separately. Do not assume every DeserializationException is a value error.

## 4. Comparing authentication, schema, and deserialization

Not every exception in a consumer is related to the payload:

| Error | Where does it happen? | Typical symptom |
|---|---|---|
| Authentication failure | Connecting to broker | Client fails to authenticate |
| Authorization failure | Broker permission check | Topic/group operation rejected |
| Deserialization failure | Deserializer during consumer poll | Cannot convert bytes into Java object |
| Message conversion failure | Spring converter after poll | Value deserialized but cannot convert to listener parameter type |
| Business processing failure | Inside listener/service | DB, HTTP, business validation |

A **DeserializationException header** is a signal of an error at the deserializer layer, typically present only when the consumer uses ErrorHandlingDeserializer or an equivalent configured mechanism.

Do not use an authorization or network error to conclude that the producer sent a bad schema. First, pinpoint the exact layer where the exception originated.

## 5. Configuring ErrorHandlingDeserializer with Spring Boot

Suppose topic **orders.created** has a String key and a JSON value matching Java class **OrderCreated**. It can be configured as follows:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: orders-reader
      enable-auto-commit: false
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.key.delegate.class]": org.apache.kafka.common.serialization.StringDeserializer
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
        "[spring.json.value.default.type]": com.example.orders.events.OrderCreated
        "[spring.json.use.type.headers]": false
        "[spring.json.trusted.packages]": com.example.orders.events
    listener:
      ack-mode: batch
~~~

Meaning:

- **key-deserializer / value-deserializer:** Spring Kafka wrappers catching delegate errors.
- **spring.deserializer.key.delegate.class:** actual deserializer for the key.
- **spring.deserializer.value.delegate.class:** actual deserializer for the value.
- **spring.json.value.default.type:** Java class used when not resolving type from type headers.
- **spring.json.use.type.headers=false:** example choosing not to use Spring JSON type headers for type resolution.
- **spring.json.trusted.packages:** package scope permitted to deserialize into classes.

The **com.example.orders.events** package in the example must be replaced with actual classes. If the system uses type headers, Schema Registry, Avro, or Protobuf, delegate configuration will differ; do not apply JSON type mapping mechanically.

### 5.1. Should both key and value be wrapped?

You may wrap only the value if payload errors are the focus. However, keys can also break due to format, encoding, or schema changes. Wrapping both key and value lets you detect failures on either side.

| Configuration | Error header created by wrapper |
|---|---|
| Wrap key only | Key failure header |
| Wrap value only | Value failure header |
| Wrap both | Corresponds to whichever deserializer failed |

This is not an automatic data-repair mechanism. The wrapper only allows errors to reach a recovery path in a controlled manner.

### 5.2. Why verify trusted packages?

JsonDeserializer enforces a type trust policy to restrict which classes can be instantiated from type metadata. Do not open all packages with a wildcard just because the consumer is throwing errors, especially when the topic has producers that are not fully trusted.

Verify whether producers send type headers, whether consumers use type headers, and whether Java DTOs match the actual schema.

## 6. Configuring via ConsumerFactory

For applications explicitly creating a ConsumerFactory, delegates can be wrapped in code:

~~~java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.support.serializer.ErrorHandlingDeserializer;
import org.springframework.kafka.support.serializer.JsonDeserializer;

@Bean
public ConsumerFactory<String, OrderCreated> consumerFactory() {
    Map<String, Object> props = new HashMap<>();

    props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
    props.put(ConsumerConfig.GROUP_ID_CONFIG, "orders-reader");
    props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);

    var keyDeserializer =
        new ErrorHandlingDeserializer<>(new StringDeserializer());

    var valueDeserializer =
        new ErrorHandlingDeserializer<>(
            new JsonDeserializer<>(OrderCreated.class, false)
        );

    return new DefaultKafkaConsumerFactory<>(
        props,
        keyDeserializer,
        valueDeserializer
    );
}
~~~

This example illustrates wrapping delegates; the application still needs the `OrderCreated` class, security settings, and JSON type/trust configuration compatible with the running version.

If Spring Boot already auto-configures the factory, prefer `application.yml` to reduce the risk of two factories having inconsistent settings. If creating your own factory, ensure `@KafkaListener` actually uses this factory.

## 7. What happens when delegate deserialization fails?

A typical processing flow:

1. KafkaConsumer receives key bytes, value bytes, and headers.
2. ErrorHandlingDeserializer calls the delegate.
3. Delegate throws an exception.
4. Wrapper creates a DeserializationException containing raw bytes and cause.
5. Wrapper adds the serialized exception to the corresponding header.
6. Wrapper returns null or a configured fallback value.
7. Spring Kafka container receives the ConsumerRecord with the error header.
8. Container or batch listener determines the recovery path.

~~~text
Input value bytes: {invalid-json
          |
          v
      JsonDeserializer
          |
          X  JSON parsing exception
          |
          v
  ErrorHandlingDeserializer
          |
          +-- exception cause
          +-- raw data bytes
          +-- isKey=false
          |
          v
ConsumerRecord(
  key="order-1",
  value=null,
  headers=[springDeserializerExceptionValue=...]
)
~~~

Do not use **new String(header.value(), UTF_8)** to read the error message text: the header value is serialized exception bytes, not a normal UTF-8 string.

## 8. Differences between record listeners and batch listeners

### 8.1. Record listener

With a record listener, the Spring Kafka container can inspect error headers created by ErrorHandlingDeserializer and route the failed record to `CommonErrorHandler` instead of invoking the listener as though it had a valid payload.

Example:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "orders-reader"
)
public void handle(OrderCreated event) {
    orderService.process(event);
}
~~~

Malformed JSON can be handled by DefaultErrorHandler and a configured recoverer. The listener does not need a `try/catch` to catch errors occurring before it is invoked.

Specific header inspection mechanics vary by version, so confirm actual behavior in the deployment environment.

### 8.2. Batch listener

With a batch listener, a single batch can contain both valid records and undeserializable records:

~~~text
index 0: valid OrderCreated
index 1: valid OrderCreated
index 2: value=null + error header
index 3: valid OrderCreated
~~~

In common Spring Kafka batch listener configurations, the application needs to check each record's error header. When an error header is found, the listener should report the failed index to DefaultErrorHandler via **BatchListenerFailedException**.

If looking only at a null payload, the listener could confuse a deserialization failure with a valid Kafka tombstone. If throwing only a generic exception, the handler will not know which record failed and may retry the entire batch.

## 9. Detecting headers in a batch listener

Example of a listener receiving `ConsumerRecord` to retain metadata:

~~~java
import java.util.List;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.listener.BatchListenerFailedException;
import org.springframework.kafka.support.serializer.SerializationUtils;

@KafkaListener(
    topics = "orders.created",
    groupId = "orders-reader",
    containerFactory = "ordersBatchContainerFactory"
)
public void consume(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (int index = 0; index < records.size(); index++) {
        var record = records.get(index);

        Header keyFailure = record.headers().lastHeader(
            SerializationUtils.KEY_DESERIALIZER_EXCEPTION_HEADER
        );

        Header valueFailure = record.headers().lastHeader(
            SerializationUtils.VALUE_DESERIALIZER_EXCEPTION_HEADER
        );

        if (keyFailure != null || valueFailure != null) {
            throw new BatchListenerFailedException(
                "Record cannot be deserialized",
                new IllegalArgumentException(
                    keyFailure != null
                        ? "Key deserialization failed"
                        : "Value deserialization failed"
                ),
                index
            );
        }

        orderService.process(record.value());
    }
}
~~~

This example checks for the presence of error headers and passes the index to the handler. The cause created in the example only describes the error; the original cause remains stored in the header. To read the original cause, use the Spring Kafka utility API appropriate for your version.

### 9.1. Index is not offset

| Data | Example | failedIndex |
|---|---|---|
| List position | records.get(2) | 2 |
| Kafka offset | record.offset() = 94 | Do not use 94 |
| Partition | record.partition() = 4 | Do not use 4 |
| Event ID | order-94 | Do not use event ID |

One poll can include records from multiple partitions. The handler must track offset progression per partition rather than using a single offset for the entire batch.

### 9.2. Do not check only value == null

A null value can be:

- A valid tombstone on a compacted topic.
- The result of ErrorHandlingDeserializer when value deserialization fails.
- A fallback configured by a failed-deserialization function.

Headers help distinguish these cases. If a topic permits tombstones, the listener must clearly define how to handle a null value without an error header.

## 10. How to read DeserializationException from a header

The error header carries a serialized exception. When needing to read raw data, `isKey`, message, or cause, use Spring Kafka's official utility instead of manually decoding uncontrolled bytes with `ObjectInputStream`.

Some versions provide helper methods to convert an exception header back into `DeserializationException` in **ListenerUtils**. The exact signature should be checked against the JavaDoc of the actual dependency.

Logic flow:

~~~text
header = record.headers().lastHeader(
    SerializationUtils.VALUE_DESERIALIZER_EXCEPTION_HEADER
)

if header is present:
    exception = Spring Kafka utility converts header to exception
    originalBytes = exception.getData()
    originalCause = exception.getCause()
    failedOnKey = exception.isKey()

    classify, observe, recover
~~~

This is pseudocode describing the reading flow, not a directly compilable Java snippet.

Do not write arbitrary Java object deserialization logic for headers received from untrusted sources. Beyond security risks, custom decoding easily breaks across library upgrades.

### 10.1. Information safety when logging

Log only the metadata needed for investigation:

- Topic, partition, offset.
- Key failure vs. value failure.
- Exception/cause class.
- Raw byte length.
- Schema ID or event type if valid metadata exists.
- Non-sensitive correlation ID, if available.

Avoid logging raw payloads by default because failed records can still contain PII or confidential data even when unparseable. For sensitive data, the DLT also needs encryption, ACLs, and appropriate retention.

## 11. DefaultErrorHandler handling deserialization failures

**DefaultErrorHandler** decides retries and recovery when record processing fails. For deserialization errors, distinguish two types of causes:

| Cause | Might retries help? |
|---|---|
| Broken JSON syntax | Usually no; bytes do not fix themselves |
| Incompatible schema | Usually requires producer/consumer fix |
| Schema registry timeout | Can help once the dependency recovers |
| Registry missing permissions | Needs credential/permission fix |
| Wrong wire format | Usually no |
| Custom validator temporarily depends on service | Depends on application policy |

A DefaultErrorHandler configuration with a recoverer:

~~~java
@Bean
DefaultErrorHandler ordersErrorHandler(
        KafkaTemplate<Object, Object> dltTemplate) {

    var recoverer = new DeadLetterPublishingRecoverer(dltTemplate);

    return new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 2L)
    );
}
~~~

The example uses a 1-second FixedBackOff between retries and two retry attempts after the initial try. In practice, deterministic schema errors should usually recover early so the consumer does not keep retrying an unprocessable payload.

### 11.1. BatchListenerFailedException avoids retrying the entire batch

If the batch listener knows the failed record is at index 2, DefaultErrorHandler can handle the successful portion before the error and redeliver the remaining portion per policy.

~~~text
Batch: [R0, R1, R2, R3]
        OK  OK  X   ?

BatchListenerFailedException(index=2)
              |
              v
       DefaultErrorHandler
              |
        retry/recover R2
        and process remaining records
~~~

If the listener throws a generic exception without a failed index, fallback batch retry may reprocess the entire batch, including records that already completed side effects.

To stay safe, business side effects still require idempotency because a crash can happen after DB commit but before Kafka offset commit.

## 12. Configuring a batch factory with an error handler

Example of a factory:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        ordersBatchContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory,
                DefaultErrorHandler ordersErrorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.setCommonErrorHandler(ordersErrorHandler);

    return factory;
}
~~~

A corresponding Spring Boot configuration for the consumer:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-reader
      enable-auto-commit: false
      max-poll-records: 100
    listener:
      type: batch
      ack-mode: batch
~~~

If the application uses a custom factory, Boot's listener properties are not guaranteed to apply automatically to that factory. Configure the factory deliberately and ensure `@KafkaListener` points to the right factory name.

## 13. The DLT must preserve raw bytes

When deserialization fails, the value in ConsumerRecord may be null, while DeserializationException holds the raw byte data. **DeadLetterPublishingRecoverer** in Spring Kafka can recover the failed record's bytes when sending to the DLT according to supported behavior.

Important detail: the DLT publisher can receive:

- Normal Java objects for valid records that failed in business logic.
- Byte arrays from payloads that failed to deserialize.
- Null keys or raw key bytes when key deserialization fails.

Therefore, a KafkaTemplate using only JsonSerializer for `OrderCreated` may not meet DLT requirements if the recoverer needs to publish raw `byte[]`.

Example selecting serializer by runtime type:

~~~java
Map<Class<?>, Serializer<?>> delegates = new LinkedHashMap<>();

delegates.put(byte[].class, new ByteArraySerializer());
delegates.put(OrderCreated.class, new JsonSerializer<>());

var valueSerializer = new DelegatingByTypeSerializer(
    delegates,
    true
);
~~~

This snippet illustrates selecting the value serializer; the application must also configure the key serializer, producer factory, KafkaTemplate, and corresponding security. If the DLT receives additional event types, declare those valid types or an explicit serializer policy.

### 13.1. DLT headers can change

The recoverer may add source metadata and exception information to the DLT record. Internal headers holding the serialized DeserializationException may be stripped or transformed during DLT publishing, depending on version/configuration.

Do not design a DLT consumer assuming the internal headers on the original ConsumerRecord always remain intact. Treat the DLT contract as raw payload, source topic/partition/offset, and the error information that recovery actually guarantees.

### 13.2. Avoid false recovery

Some reasons DLT publishing fails:

- DLT topic does not exist yet.
- Unsuitable DLT partition mapping.
- Producer lacks WRITE permission.
- Serializer cannot handle `byte[]`.
- Broker or network unavailable.
- Delivery timeout.

If DLT publishing fails, do not consider the record recovered merely because code called publish. The handler must inspect publish results properly and preserve redelivery eligibility per policy.

## 14. Conversion errors differ from deserialization errors

In Spring Kafka, two type-conversion steps can occur:

1. Kafka deserializer converts bytes into String, JSON object, or another Java type.
2. Spring message converter converts the deserialized value into the parameter type requested by the listener.

For example, Kafka StringDeserializer reads JSON into a String successfully, but the message converter cannot convert that String into `OrderCreated`. This is a **message conversion failure**, not a Kafka deserializer error.

With batch listeners using message converters, separate metadata may exist for conversion failures, such as **KafkaHeaders.CONVERSION_FAILURES** in supported versions.

| Error layer | Typical signal |
|---|---|
| Kafka deserializer | DeserializationException header when using ErrorHandlingDeserializer |
| Spring message converter | ConversionException / conversion failures metadata |
| Business listener | Domain exception or dependency exception |

Do not look for deserializer exception headers when the error actually occurred in the message converter or business service.

## 15. Schema evolution and compatibility

A common cause of DeserializationException is a producer changing a schema before consumers are compatible.

Example old payload:

~~~json
{"orderId":"o-101","total":125.5}
~~~

New payload:

~~~json
{"orderId":"o-101","total":{"currency":"USD","amount":125.5}}
~~~

An old consumer expecting `total` to be a number can fail when encountering an object. Retrying the same bytes with the same model does not help.

Schema management should include:

- Backward/forward compatibility rules.
- Deployment order of producers and consumers.
- Nullable fields, default values, and required constraints.
- Data types, enums, renames, and deprecation.
- Type headers and Java class mapping rules.
- Schema registry when using Avro, Protobuf, or JSON Schema.
- Contract tests in the release pipeline.
- Plans to replay records written under old/new schemas.

The error header is evidence that helps classify incompatibility; it does not replace schema governance.

### 15.1. Registry timeout differs from malformed payload

If using Schema Registry, exceptions can stem from registry timeout, unknown schema ID, authorization error, or wrong wire format.

| Cause | Handling direction |
|---|---|
| Registry temporarily unavailable | Bounded retry/backoff and monitor registry |
| Wrong or nonexistent schema ID | Check producer/registry config, inspect ID |
| Incompatible consumer model | Fix model/schema, roll out as planned |
| Wrong wire format | Identify actual producer and serializer |
| Registry authorization failure | Fix registry credentials and ACLs |
| Registry endpoint pointing to wrong cluster | Adjust endpoint/configuration |

Read the root cause before deciding between retry and DLT. Two records may both carry DeserializationException while having different causes and recoverability.

## 16. FailedDeserializationFunction and fallbacks

ErrorHandlingDeserializer can support a **failed-deserialization function** to return a replacement object when the delegate fails. This feature is useful when you want to route bad data into a special handling flow.

However, if the listener receives a fallback object and treats it as a normal `OrderCreated`, the system may commit a record that was never properly processed.

When using fallbacks:

1. Define the fallback data type explicitly.
2. Preserve necessary error metadata and raw bytes.
3. Check headers before business processing.
4. Distinguish fallbacks from valid DTOs.
5. Make recovery and offset commits transparent.
6. Test cases where the fallback cannot be built or also fails.

A custom validator at the ErrorHandlingDeserializer layer can also mark a record as failed when it fails validation rules supported by the wrapper. Distinguish syntax/schema errors from business validation errors.

## 17. Tombstones and null values

In a compacted topic, a producer can send a tombstone with a null value to represent deleting a key. A tombstone is a valid record, not an error.

~~~text
Tombstone:
  key=customer-81
  value=null
  deserialization error header: absent

Malformed value:
  key=customer-81
  value=null
  deserialization error header: present
~~~

If a listener checks only for a null value and throws an exception, tombstones can be mistakenly sent to the DLT and the consumer fails to apply deletions.

Therefore, when a record has a null value, check whether a DeserializationException value header is present before applying tombstone or fallback logic.

## 18. Offset commits and recovery

Kafka stores the next offset the consumer group needs to read. When a failed record has not been processed or successfully recovered, do not intentionally commit past that record unless the business permits skipping.

Example:

~~~text
Partition 0:
  offset 10 -> processed OK
  offset 11 -> deserialization failure
  offset 12 -> not yet processed
~~~

Without valid recovery for offset 11, committing 13 can cause the group to resume past the failed record on restart. This is not just a metrics issue; it can cause lost data processing opportunities.

Situations to distinguish:

- Recovery/DLT succeeded and policy allows skipping: handler can advance the offset.
- DLT publishing failed: retain retry/recovery eligibility.
- JVM crashes before commit: record may be redelivered.
- Listener swallows the error and returns normally: container may mistakenly commit as success.

If valid records already produced side effects before hitting a failed record, idempotency is required because already-processed records can still be redelivered after a crash or rebalance.

## 19. Controlled malformed message testing

A useful test is sending value bytes that are not valid JSON via a producer configured with `ByteArraySerializer`:

~~~java
byte[] malformed = "{not-valid-json".getBytes(
    StandardCharsets.UTF_8
);

rawTemplate.send(
    "orders.created",
    "order-bad-1",
    malformed
);
~~~

In the test, the consumer must be configured with ErrorHandlingDeserializer wrapping JsonDeserializer. Expected observations:

1. Valid JSON events still process normally.
2. Malformed event produces a DeserializationException value header.
3. Record listener or batch listener routes through the appropriate error handler.
4. Batch listener identifies the failed index.
5. DLT receives the failed data and metadata.
6. Raw bytes are preserved per DLT policy.
7. Offset commit does not skip the record if recovery fails.
8. Subsequent valid events still process once recovery completes.
9. Key deserializer errors are also detected.
10. Valid null tombstones are not treated as malformed records.

If using Schema Registry, add tests for registry timeout, missing schema ID, and authorization failure. Do not use production data containing PII for failure testing without data-protection safeguards.

## 20. Operational metrics and logging

Signals to monitor:

| Signal | Purpose |
|---|---|
| Deserialization failure count/rate | Detect spikes in bad data per topic |
| Key vs value failure | Distinguish error location |
| Exception class | Identify parser, schema, or registry failures |
| DLT publish success/failure | Confirm recovery |
| DLT backlog | Volume of records awaiting investigation/replay |
| Consumer lag by partition | Whether a partition is stuck at a bad record |
| Event freshness | Whether valid events after a bad record are delayed |
| Schema version distribution | Detect producers emitting inconsistent schemas |

Logs can be structured as:

~~~text
listener=orders-reader
topic=orders.created
partition=4
offset=28012
stage=deserialization
part=value
cause=JsonMappingException
rawSizeBytes=241
action=published-to-dlt
~~~

Do not use raw payloads, event IDs, or offsets as high-cardinality metric labels. Offsets can appear in logs to help investigate individual records, but do not turn every offset into a metric time series.

### 20.1. Practical alerting

Alert when the deserialization failure rate rises above baseline, especially alongside rising consumer lag or DLT ingress. When alerted, correlate with producer releases, consumer deployments, schema registry changes, or credential rotations.

## 21. Runbook for handling DeserializationException in headers

1. Identify listener type: record or batch.
2. Record topic, partition, offset, consumer group, and client ID.
3. Identify the key/value header and exception cause.
4. Inspect the actual configured ErrorHandlingDeserializer and delegate.
5. Compare producer format/schema against the consumer's Java model.
6. Check type headers, trusted packages, and schema registry.
7. Classify the error as deterministic or transient.
8. If transient, apply bounded retry/backoff.
9. If deterministic, recover/DLT per policy instead of infinite retries.
10. Confirm the DLT serializer supports raw `byte[]`.
11. Confirm DLT publish and offset commit work properly.
12. Perform controlled replay after fixing the schema, with idempotency.
13. Document root cause and add contract tests.

The runbook should enable operations teams to verify recovery with real data, rather than relying only on logs stating the recoverer method was called.

## 22. Common pitfalls

**Using only JsonDeserializer and expecting the listener to catch errors.** The delegate can throw an exception in poll; the listener is never invoked.

**Reading the header as UTF-8 text.** The DeserializationException header contains serialized bytes; use the appropriate Spring Kafka utility to read it.

**Assuming the error header already lives in the Kafka log.** The consumer-side wrapper adds the header during deserialization without modifying the original broker record.

**Relying on a null value to detect errors.** Tombstones also have null values; inspect headers.

**Forgetting to check key failures.** The key deserializer can fail independently of the value.

**Using a batch listener without checking each record's headers.** Can miss malformed records or unnecessarily retry the entire batch.

**Passing Kafka offset instead of failed index.** `BatchListenerFailedException` expects the zero-based index in the listener's list.

**Manually decoding Java object headers from untrusted sources.** Use official APIs and avoid arbitrary Java deserialization.

**DLT producer unable to serialize `byte[]`.** The recoverer may need to publish the failed record's raw bytes.

**Assuming the DLT preserves all internal headers unchanged.** Verify the DLT metadata contract after recovery.

**Retrying a permanent schema mismatch infinitely.** Retrying does not make schema-incompatible data valid.

**Committing offsets when recovery has not succeeded.** Can prevent the record from ever being reprocessed.

**Logging raw failing payloads.** Malformed bytes can still contain sensitive information.

## 23. Implementation checklist

- [ ] ErrorHandlingDeserializer enabled for keys/values needing protection.
- [ ] Delegate deserializers and type mapping declared accurately.
- [ ] Consumer does not auto-commit independently of container error handling.
- [ ] Record listeners have appropriate DefaultErrorHandler/recoverer.
- [ ] Batch listeners inspect key/value error headers per record.
- [ ] BatchListenerFailedException receives the accurate zero-based index.
- [ ] Null tombstones are distinguished from deserialization failures.
- [ ] Deterministic schema errors do not retry infinitely.
- [ ] Transient registry/network errors have bounded retry/backoff.
- [ ] DLT serializer can publish raw `byte[]`.
- [ ] DLT preserves source metadata and investigative data.
- [ ] DLT publish failures are not treated as recovery success.
- [ ] Dashboards track failure rate, lag, DLT, and event freshness.
- [ ] Tests cover malformed keys, malformed values, tombstones, and DLT failures.
- [ ] Runbook exists for schema compatibility and replay handling.

## 24. Key takeaways

**DeserializationException in headers** is the mechanism ErrorHandlingDeserializer uses to preserve byte-conversion error details on the consumer side. The header contains a serialized exception, including original data and error cause, not plain text or a JSON payload.

Record listeners can be routed directly to the error handler by the container. Batch listeners generally need to inspect each record, detect key/value exception headers, and report the failed index so DefaultErrorHandler handles the failure with the right scope.

For a resilient system, combine proper deserializers, schema compatibility, a DLT serializer supporting raw bytes, offset commits, idempotent side effects, and observability tools. Recovery is complete only when failed data is processed or isolated per policy and the consumer can continue without dropping business operations.
