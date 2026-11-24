# Log DLT destination

When a record cannot be processed after the configured number of retries, Spring Kafka can forward that record to a **Dead Letter Topic (DLT)** via `DeadLetterPublishingRecoverer`. In production, knowing only “sent to DLT” is not enough for investigation. Operations teams need to know **which source topic/partition/offset the record came from, which destination topic/partition the recoverer chose, why the record was routed, and whether the publish was truly acknowledged by the broker**.

**Logging the DLT destination** is the structured recording of the recovery destination in a way that can be cross-checked against metadata attached to the DLT record. In Spring Kafka, the target is chosen by the destination resolver of `DeadLetterPublishingRecoverer`; the application can log that decision, configure the recoverer to wait for the send result, and record success/failure accurately.

One principle to keep clear: **logging that the recoverer chose a destination does not mean the record was published successfully**. To confirm the send, observe the Kafka send result or configure the recoverer to fail when a send errors. This lesson covers how to log both stages, how to use DLT headers for correlation, and how to avoid turning logs/metrics into data leaks or cardinality explosions.

## 1. Where is the DLT destination decided?

Typical recovery flow in Spring Kafka:

```text
Kafka topic orders
       |
       v
@KafkaListener
       |
       +--> processing succeeds --> commit per container
       |
       +--> exception
                |
                v
          DefaultErrorHandler
                |
          retry/backoff policy
                |
          retries exhausted or non-retryable error
                |
                v
       DeadLetterPublishingRecoverer
                |
         destination resolver
                |
                v
       KafkaTemplate.send(DLT topic, partition, record)
```

`DeadLetterPublishingRecoverer` acts as a `ConsumerRecordRecoverer`: it receives the original `ConsumerRecord` and exception, determines the target `TopicPartition`, constructs the record to publish, and sends it via the configured `KafkaTemplate`/`KafkaOperations`.

With the default single-template constructor, the common destination convention is **`<originalTopic>.DLT` and the same partition index as the source record**. For example, `orders` partition 2 routes to `orders.DLT` partition 2. When custom rules are needed, you can pass a `BiFunction<ConsumerRecord<?, ?>, Exception, TopicPartition>` as the destination resolver.

The logged destination must come from the **resolver's decision**, never by concatenating `record.topic() + ".DLT"` elsewhere and assuming that is always the real target. Applications may route by exception type, tenant class, source topic, or operational policy; the resolver is where that decision lives.

## 2. Distinguishing the source record and the DLT record

While processed on the source topic, a record has coordinates:

```text
Source record:
  topic     = orders
  partition = 2
  offset    = 18420
```

After recovery, the new record is written to the DLT:

```text
Published DLT record:
  topic     = orders.DLT
  partition = 2
  offset    = 930

Original source metadata (headers):
  original topic     = orders
  original partition = 2
  original offset    = 18420
```

Offset `930` is the new offset in the DLT partition; `18420` is the original record's offset on the source topic. These two coordinates are not interchangeable. When a consumer reads the DLT, `ConsumerRecord.topic()` returns `orders.DLT`; source metadata must come from the original headers attached by the recoverer.

Good logs capture **both sides**:

- Source: topic, partition, offset, timestamp, and listener/group if known with certainty.
- Destination: topic and partition selected by the resolver.
- Recovery reason: exception class or normalized error category.
- Outcome: destination selected, send acknowledged, or send failed.

You do not need to log raw payloads to know where a record went. Payloads may contain personal information, tokens, secrets, or untrusted data; provenance and Kafka coordinates are usually enough to locate the record in an authorized environment.

## 3. Using the destination resolver to determine and log the target

The constructor taking `KafkaOperations` and a destination resolver lets the application choose the target topic/partition. The following example logs the chosen destination:

```java
import java.util.function.BiFunction;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.TopicPartition;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;

public class DltRecovererConfiguration {

    private static final Logger log = LoggerFactory.getLogger(
            DltRecovererConfiguration.class);

    public static DeadLetterPublishingRecoverer create(
            KafkaTemplate<Object, Object> dltTemplate) {

        BiFunction<ConsumerRecord<?, ?>, Exception, TopicPartition> resolver =
                (record, exception) -> {
                    TopicPartition destination = new TopicPartition(
                            record.topic() + ".DLT",
                            record.partition());

                    log.warn(
                            "DLT destination selected: sourceTopic={}, "
                                    + "sourcePartition={}, sourceOffset={}, "
                                    + "destinationTopic={}, destinationPartition={}, "
                                    + "exceptionType={}",
                            record.topic(),
                            record.partition(),
                            record.offset(),
                            destination.topic(),
                            destination.partition(),
                            exception.getClass().getName());

                    return destination;
                };

        return new DeadLetterPublishingRecoverer(dltTemplate, resolver);
    }
}
```

Logging inside the resolver records **destination selected** — the routing decision prior to sending. It does not confirm the broker received the record. If publishing fails afterward, the destination log remains accurate about routing intent but must never be interpreted as “the DLT record exists”.

The resolver should be a pure, deterministic, fast function: the same record/exception under the same conditions must return the same destination. Never make synchronous database or HTTP calls from the resolver just to look up topic names; that prolongs recovery on the consumer thread and can stall polling. If routing depends on dynamic config, read from controlled config/caches.

## 4. Confirming publish success via `setFailIfSendResultIsError`

`KafkaTemplate.send()` normally returns a future because sends happen asynchronously. If the app logs destination and moves on, the send can still fail later due to missing topic, ACLs, serialization, broker unavailability, or timeouts.

`DeadLetterPublishingRecoverer` offers `setFailIfSendResultIsError(true)` so the recoverer waits for the send result and throws on failure, in Spring Kafka versions supporting this API. Once enabled, the application can wrap the recoverer to log after `accept()` returns normally:

```java
DeadLetterPublishingRecoverer delegate =
        new DeadLetterPublishingRecoverer(dltTemplate, resolver);

delegate.setFailIfSendResultIsError(true);

ConsumerRecordRecoverer loggingRecoverer = (record, exception) -> {
    TopicPartition destination = resolver.apply(record, exception);

    log.warn(
            "Publishing failed record to DLT: sourceTopic={}, "
                    + "sourcePartition={}, sourceOffset={}, "
                    + "destinationTopic={}, destinationPartition={}, "
                    + "exceptionType={}",
            record.topic(), record.partition(), record.offset(),
            destination.topic(), destination.partition(),
            exception.getClass().getName());

    // With failIfSendResultIsError=true, send errors are surfaced
    // instead of treating recovery as complete.
    delegate.accept(record, exception);

    log.info(
            "DLT publish acknowledged: sourceTopic={}, sourcePartition={}, "
                    + "sourceOffset={}, destinationTopic={}, destinationPartition={}",
            record.topic(), record.partition(), record.offset(),
            destination.topic(), destination.partition());
};
```

`ConsumerRecordRecoverer` belongs to `org.springframework.kafka.listener`; `resolver` should be defined once and shared by both the delegate and wrapper. In this example the resolver runs once for logging and once inside the delegate, so it must be **side-effect free**. To avoid recomputing, an app abstraction can hold the per-call routing result, without using a global offset cache lacking cleanup.

`setFailIfSendResultIsError(true)` is critical: if the recoverer throws on a send failure, the error handler treats recovery as incomplete and does not advance the source offset as if the record recovered safely. Final commit/retry behavior still depends on `DefaultErrorHandler`, ack mode, transaction manager, and Spring Kafka version; configure and test your actual flow.

Without waiting for the send result, a log line after `delegate.accept()` only proves the recoverer method returned, **not that the broker acknowledged the write**. Never log `DLT publish succeeded` in that case.

## 5. Attaching the recoverer to `DefaultErrorHandler`

A complete container-factory-level configuration can use the logging-wrapped recoverer:

```java
@Bean
DefaultErrorHandler ordersErrorHandler(
        KafkaTemplate<Object, Object> dltTemplate) {

    BiFunction<ConsumerRecord<?, ?>, Exception, TopicPartition> resolver =
            (record, exception) -> new TopicPartition(
                    record.topic() + ".DLT",
                    record.partition());

    DeadLetterPublishingRecoverer delegate =
            new DeadLetterPublishingRecoverer(dltTemplate, resolver);
    delegate.setFailIfSendResultIsError(true);

    ConsumerRecordRecoverer loggingRecoverer = (record, exception) -> {
        TopicPartition destination = resolver.apply(record, exception);
        log.warn(
                "DLT recovery selected: source={}-{}@{}, destination={}-{}, cause={}",
                record.topic(), record.partition(), record.offset(),
                destination.topic(), destination.partition(),
                exception.getClass().getSimpleName());

        delegate.accept(record, exception);

        log.info(
                "DLT recovery send acknowledged: source={}-{}@{}, destination={}-{}",
                record.topic(), record.partition(), record.offset(),
                destination.topic(), destination.partition());
    };

    return new DefaultErrorHandler(
            loggingRecoverer,
            new FixedBackOff(1_000L, 2L));
}
```

The snippet uses `log` as an SLF4J logger declared in the configuration class. The example shows two retries after the initial attempt; `FixedBackOff(1_000L, 2L)` is not a mandatory rule for all errors. Classify retryable vs. non-retryable exceptions by root cause: permanently malformed payloads can route to the DLT immediately, while transient dependency failures need bounded backoff.

Attach the handler to the right listener container factory:

```java
@Bean("ordersKafkaListenerContainerFactory")
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory,
        DefaultErrorHandler ordersErrorHandler) {

    ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
            new ConcurrentKafkaListenerContainerFactory<>();
    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(ordersErrorHandler);
    return factory;
}
```

The listener must reference this factory via `containerFactory`. If the handler is wired onto a factory unused by the listener, DLT destination logs will not appear as expected.

## 6. Routing to multiple DLTs by error category

Some systems split DLTs by cause so responsible teams can triage the right stream: schema errors to `orders-invalid-format.DLT`, business contract errors to `orders-business-error.DLT`, and unclassified errors to `orders.DLT`.

```java
BiFunction<ConsumerRecord<?, ?>, Exception, TopicPartition> resolver =
        (record, exception) -> {
            String suffix;

            if (exception instanceof InvalidPayloadException) {
                suffix = ".invalid-format.DLT";
            }
            else if (exception instanceof UnsupportedOrderStateException) {
                suffix = ".business-error.DLT";
            }
            else {
                suffix = ".DLT";
            }

            return new TopicPartition(
                    record.topic() + suffix,
                    record.partition());
        };
```

Exceptions in the example are application-defined classes. In practice, classify by root cause rather than checking only the outermost exception; a `ListenerExecutionFailedException` may wrap the original exception. Also decide whether to preserve the source partition index or use another partition resolver.

When multiple targets exist, logs should carry `destination_reason` or `error_category` from a small enum such as `INVALID_FORMAT`, `BUSINESS_REJECTED`, `UNCLASSIFIED`. Never use the full exception message as a label or routing key; messages vary per record, can contain PII, or violate topic naming rules.

## 7. The destination partition must exist

If the resolver preserves the source partition index, the DLT needs enough matching partitions. For example, if the source topic has 12 partitions yet `orders.DLT` only has 6 partitions, a record from `orders-9` cannot be sent to `orders.DLT-9` if partition 9 does not exist.

| Source topic | Source partition | DLT partitions | Result when keeping partition index |
|---|---:|---:|---|
| `orders` | 0 | 12 | Valid if DLT has partition 0 |
| `orders` | 5 | 12 | Valid if DLT has partition 5 |
| `orders` | 9 | 6 | Invalid: DLT lacks partition 9 |

Handle this in one of these ways:

- Provision the DLT with partition count equal to or greater than the source when keeping partition indices.
- Use a resolver mapping to a valid partition, accepting altered ordering/parallelism.
- Use dedicated DLT topologies designed around triage needs rather than assuming 1-to-1 partition parity.

Do not log an inferred destination partition as valid without checking topology. `DeadLetterPublishingRecoverer` performs partition checks depending on version/config; if the destination is invalid, recovery can fail. Topic creation and ACL grants must be managed before consumers start sending to DLTs, not discovered only when a poison record arrives.

## 8. Destination log vs. send outcome log are two separate events

To avoid misinterpretation, distinguish three states in logs:

| State | Meaning | Log example |
|---|---|---|
| `destination_selected` | Resolver picked topic/partition | `DLT destination selected ...` |
| `send_acknowledged` | Recoverer awaited send and got success | `DLT publish acknowledged ...` |
| `send_failed` | Send errored/timed out/serialization/ACL; recovery incomplete | `DLT publish failed ...` |

An event sequence might look like:

```text
WARN  dlt.destination_selected source=orders-2@18420
      destination=orders.DLT-2 cause=InvalidPayloadException

INFO  dlt.send_acknowledged source=orders-2@18420
      destination=orders.DLT-2
```

If the send fails, only `destination_selected` appears followed by an exception from the recoverer. Never put a success log inside `finally`; `finally` executes even when the delegate throws. Use `catch` to log `send_failed` and rethrow to the error handler:

```java
try {
    delegate.accept(record, exception);
    log.info("DLT send acknowledged: source={}-{}@{}, destination={}-{}",
            record.topic(), record.partition(), record.offset(),
            destination.topic(), destination.partition());
}
catch (RuntimeException sendFailure) {
    log.error("DLT send failed: source={}-{}@{}, destination={}-{}, failureType={}",
            record.topic(), record.partition(), record.offset(),
            destination.topic(), destination.partition(),
            sendFailure.getClass().getName());
    throw sendFailure;
}
```

This wrapper only confirms the send when the delegate is configured to wait for the result and surface errors. Otherwise, it only confirms the recoverer accepted the send request. Failure logs should avoid repeating full stack traces at multiple layers if the framework already logs the exception; choose one owner for detailed stack logging and emit structured context elsewhere.

## 9. DLT headers used to cross-check logs

`DeadLetterPublishingRecoverer` attaches metadata to the published record's headers, including key source headers such as:

- `KafkaHeaders.DLT_ORIGINAL_TOPIC`
- `KafkaHeaders.DLT_ORIGINAL_PARTITION`
- `KafkaHeaders.DLT_ORIGINAL_OFFSET`

These headers tell DLT consumers where the record was routed from. Spring Kafka also supports exception metadata such as exception class/message/stack trace depending on version and config, though you should not assume every header survives multiple recoveries/replays intact.

Example DLT consumer reading provenance:

```java
@KafkaListener(topics = "orders.DLT", groupId = "orders-dlt-triage")
public void inspect(
        ConsumerRecord<String, byte[]> record,
        @Header(KafkaHeaders.DLT_ORIGINAL_TOPIC) String originalTopic,
        @Header(KafkaHeaders.DLT_ORIGINAL_PARTITION) Integer originalPartition,
        @Header(KafkaHeaders.DLT_ORIGINAL_OFFSET) Long originalOffset) {

    log.warn(
            "DLT record received: dltTopic={}, dltPartition={}, dltOffset={}, "
                    + "sourceTopic={}, sourcePartition={}, sourceOffset={}",
            record.topic(), record.partition(), record.offset(),
            originalTopic, originalPartition, originalOffset);
}
```

This example uses `byte[]` values to illustrate a triage consumer reading raw payloads; actual key/value types depend on DLT serializers. Check header constants and conversions against your Spring Kafka version. If headers are missing or produced by another system, method argument binding can fail; production code should handle missing metadata gracefully or read headers defensively.

Never rely solely on the DLT record offset to find the source record. Store original topic/partition/offset in logs and headers; they are far clearer investigation keys.

## 10. Structured logging: which fields should be present?

A useful DLT log may include:

| Field | Example | Purpose |
|---|---|---|
| `event` | `dlt.send_acknowledged` | Categorize the log event |
| `source_topic` | `orders` | Original topic |
| `source_partition` | `2` | Original partition |
| `source_offset` | `18420` | Original offset |
| `destination_topic` | `orders.DLT` | Chosen DLT |
| `destination_partition` | `2` | Target partition |
| `exception_type` | `InvalidPayloadException` | Technical reason at class level |
| `error_category` | `INVALID_FORMAT` | Stable error group for filtering |
| `consumer_group` | `order-service` | Associated consumer group, if available in context |
| `listener_id` | `ordersListener` | Listener handling the record, if available in context |
| `correlation_id` | normalized/permitted value | Link business logs if needed |

Not all fields exist directly on `ConsumerRecord` or the exception. Listener ID/group may need to be placed in context at the container or wrapper layer; never guess values and log them as verified data.

Key-value SLF4J log example compatible with JSON encoders:

```java
log.warn(
        "DLT destination selected source_topic={} source_partition={} "
                + "source_offset={} destination_topic={} destination_partition={} "
                + "error_category={} exception_type={}",
        record.topic(),
        record.partition(),
        record.offset(),
        destination.topic(),
        destination.partition(),
        errorCategory,
        exception.getClass().getSimpleName());
```

Final formatting depends on the logging backend/encoder. If using MDC, remember to clean up MDC on the right thread so context does not leak to the next record. `eventId` is helpful in logs when permitted, but should not become a metric label.

## 11. Data that should not go into DLT logs

A failing record can contain untrusted or sensitive data. Avoid logging:

- Full keys/values or JSON/Avro/Protobuf payloads.
- Authorization headers, access tokens, cookies, passwords, or secrets.
- Unvetted exception messages if they might contain part of a payload/PII.
- Full stack traces on every retry when the same error repeats thousands of times.
- Arbitrary producer-sent headers without size/encoding limits.

Log injection is also a risk: header values with newlines or control characters can forge log entries. For fields taken from records/headers, use escaping encoders, normalize lengths, and restrict characters. To inspect payloads, access the DLT using authorized, audited tooling rather than copying payloads into centralized logs by default.

A practical rule is **log coordinates and error categories; keep payloads inside the Kafka DLT**. Operators can then find the record without replicating sensitive data into log systems with different retention or access rules.

## 12. Log on every retry or only on final recovery?

Not every exception immediately sends a record to the DLT. `DefaultErrorHandler` may execute multiple retries before invoking the recoverer. Logging every retry as “DLT publish” skews dashboard counts.

```text
Delivery #1 -> exception -> retry
Delivery #2 -> exception -> retry
Delivery #3 -> exception -> recoverer
                          |
                          v
                    destination selected
                          |
                          v
                    DLT send acknowledged
```

Separate logs across layers:

- `record_processing_failed`: listener attempt failed.
- `record_retry_scheduled` or error handler retry log: will retry.
- `dlt.destination_selected`: reached recovery and resolver chose destination.
- `dlt.send_acknowledged`: DLT send confirmed under wait-for-result config.
- `dlt.send_failed`: send failed, recovery incomplete.

One record can have several `record_processing_failed` logs yet only one successful DLT publish. When recovery itself retries after a send failure, destination logs may reappear. That does not necessarily mean a duplicate DLT record; cross-check send results, source offset, and event ID.

## 13. Destination logs do not replace metrics

Per-record logs help investigations, while dashboards and alerts need low-cardinality metrics. Systems should track dedicated counters and timers:

| Metric | Answers |
|---|---|
| DLT recovery attempts | How many times was the recoverer called? |
| DLT sends acknowledged | How many records did the broker acknowledge? |
| DLT send failures | How many DLT publishes failed? |
| DLT rate by source topic/error category | Which topic/error category drives the most DLTs? |
| DLT backlog / oldest record age | How many records await triage/replay? |
| Recovery latency | How long from record failure until DLT send finishes? |

Restrict tags to `source_topic`, `error_category`, `service`, `environment`, or a bounded set of destination topics. Never use `source_offset`, `event_id`, `order_id`, raw exception messages, or payloads as metric tags.

Increment `dlt.send.acknowledged` only after the recoverer confirms the send; increment `dlt.send.failed` when the send fails. Never increment a success counter just because the resolver returned a `TopicPartition`.

## 14. Retries, DLT, and Kafka transactions

With a non-transactional producer, a DLT record is sent as a normal Kafka record; `read_committed` consumers can still read non-transactional records. If the recoverer uses a transactional `KafkaTemplate`, DLT publishing can occur inside a Kafka transaction. Downstream `read_committed` consumers then see the DLT record only after the transaction commits.

In some recovery flows, Spring Kafka can coordinate DLT publishing and source offset commits within the same Kafka transaction using appropriate transactional recovery config. This differs from calling `DeadLetterPublishingRecoverer` on a non-transactional producer.

Logs should distinguish:

- Resolver chose destination.
- Producer sent DLT record.
- Kafka transaction committed/aborted if transactional.
- Source offset committed per container/error handler.

A producer `send_acknowledged` log inside a transaction does not guarantee the DLT record is **visible** to `read_committed` consumers yet; the transaction may still be open or eventually abort. For transactional recovery, log “recovery committed” only with proof the transaction completed, or rely on transaction manager instrumentation. Do not infer transaction outcomes from a single send future.

## 15. Troubleshooting when logs show destination selected yet DLT lacks the record

Common causes:

1. Logs only recorded `destination_selected`; the producer send never finished or failed afterward.
2. `setFailIfSendResultIsError(true)` was not enabled, so the recoverer did not wait for send results as expected.
3. Destination topic does not exist or broker disables auto-creation.
4. ACL lacks write permissions for the target topic/partition.
5. DLT serializer does not support the actual runtime key/value type, especially raw `byte[]` from deserialization failures.
6. Partition index from resolver exceeds the DLT's partition count.
7. Transactional send executed, yet the transaction aborted or has not committed.
8. Triage consumer reads the DLT with a different group/offset or `read_committed` cannot see transactional records yet.
9. The record was written, yet retention, compaction, or admin actions removed or moved it.

Investigation should reconcile source coordinates, destination coordinates, producer errors/acks, transaction outcomes, committed source offsets, and DLT consumer offsets. Do not search only by `eventId` in logs if logs omitted event ID or the value is non-unique.

## 16. Logging DLT publish failures while preserving errors for the error handler

When a send fails, the wrapper should log context and **rethrow the exception** so the error handler knows recovery did not succeed:

```java
ConsumerRecordRecoverer loggingRecoverer = (record, exception) -> {
    TopicPartition destination = resolver.apply(record, exception);

    try {
        delegate.accept(record, exception);
        log.info("DLT send acknowledged source={}-{}@{} destination={}-{}",
                record.topic(), record.partition(), record.offset(),
                destination.topic(), destination.partition());
    }
    catch (RuntimeException failure) {
        log.error("DLT send failed source={}-{}@{} destination={}-{} type={}",
                record.topic(), record.partition(), record.offset(),
                destination.topic(), destination.partition(),
                failure.getClass().getName());
        throw failure;
    }
};
```

This example assumes `delegate` has `setFailIfSendResultIsError(true)`. Without awaiting results, `try` catches only synchronous errors during the recoverer call, missing asynchronous send failures. Also avoid catching `Throwable` and swallowing JVM errors; catch only exception types matching your version's contract.

When the recoverer throws, the source record proceeds according to the container's error-handler/transaction policy. Test explicitly to verify the source offset is not committed as if recovery succeeded. Never place `acknowledge()` inside `finally` to prevent a stuck consumer.

## 17. Destination routing by environment and ownership

DLT names may differ across environments, domains, or security policies. Instead of scattering hardcoded suffixes, centralize routing in one place:

```java
public interface DltDestinationPolicy {
    TopicPartition destinationFor(
            ConsumerRecord<?, ?> record,
            Exception exception);
}
```

An implementation can read validated configuration:

```java
@Component
public class OrdersDltDestinationPolicy implements DltDestinationPolicy {

    @Override
    public TopicPartition destinationFor(
            ConsumerRecord<?, ?> record,
            Exception exception) {

        String topic = record.topic() + ".DLT";
        return new TopicPartition(topic, record.partition());
    }
}
```

The resolver turns the result into logs and destinations:

```java
BiFunction<ConsumerRecord<?, ?>, Exception, TopicPartition> resolver =
        policy::destinationFor;
```

In practice, validate policies before running: topics must belong to an allowlist, partitions must be valid, names must satisfy broker rules, and each DLT must have defined owner/retention/ACLs. Never let arbitrary exception messages or headers dictate topic names directly, as that can create uncontrolled destinations or route data to wrong places.

If sharing a DLT across multiple services, logs need source topic and owner so ops teams do not triage the wrong records. A shared DLT also needs a clear schema/serializer strategy across payload types.

## 18. Logging when reading from DLT and replaying

Once a record is in the DLT, triage consumers should log both current coordinates and source coordinates:

```text
event=dlt.record_inspected
dlt_topic=orders.DLT
dlt_partition=2
dlt_offset=930
source_topic=orders
source_partition=2
source_offset=18420
error_category=INVALID_FORMAT
```

During replay, also log `replay_id`, `replay_attempt`, and the new destination topic per approved workflow. Keep original metadata so the full chain stays traceable:

```text
orders-2@18420
       |
       v
orders.DLT-2@930
       |
       v
orders-2@19001  (new record published by replay)
```

Offset `19001` is a new position; replay cannot overwrite old offset `18420`. When consumers reprocess the event, idempotency or state versioning is required. DLT destination logs must not replace business audits, nor should original provenance be stripped during replay.

Never log `traceId` or `replayId` as metric tags. They belong in structured logs/traces with appropriate retention and access controls; stable business event IDs serve deduplication, while trace IDs support telemetry.

## 19. Common logging and configuration mistakes

| Symptom | Possible cause | Remediation |
|---|---|---|
| Log shows DLT destination yet topic has no record | Logged only resolver; send unacknowledged or failed | Enable fail-on-send-error and log outcomes separately |
| DLT record exists yet source coordinates are unclear | Provenance headers stripped or triage consumer does not read headers | Check recoverer header policy and `KafkaHeaders.DLT_ORIGINAL_*` |
| Log prints wrong destination | Log manually concatenated `.DLT` while resolver routed elsewhere | Log from the actual configured resolver |
| Same record has multiple destination logs | Retries/recovery invoked multiple times or resolver invoked in wrapper and delegate | Separate attempts from outcomes; pure resolver, clear event names |
| Success logged despite failed send future | Did not wait for / check send result | Use `setFailIfSendResultIsError(true)` in supported versions |
| Recovery fails yet offset advances | Wrong ack/handler/transaction setup or swallowed exception | Rethrow recovery exception and test committed offsets |
| DLT partition does not exist | DLT has fewer partitions than source while resolver keeps index | Provision enough partitions or change resolver |
| Logs contain PII/payloads | Logged full record or exception message | Log only provenance and error category; redact data |
| Dashboards have millions of series | Used offset/event ID/exception message as metric tags | Move details to logs/traces; keep metric tags low-cardinality |
| DLT consumer misses transactional record | DLT transaction not committed or consumer isolation differs | Check transaction outcome and `read_committed` visibility |

## 20. Testing destination logs and publish outcomes

Tests should verify **routing**, **actual records**, and **log outcomes** rather than only checking that a log string exists.

Important test cases:

1. **Default destination:** a record from `orders-2` routes to `orders.DLT-2` per selected policy.
2. **Custom destination:** different exception categories produce allowlisted target topics.
3. **Resolver log:** source topic/partition/offset and destination topic/partition are logged accurately.
4. **Send success:** with fail-on-send-error enabled, recoverer returns normally after send succeeds; outcome logs as acknowledged.
5. **Nonexistent topic:** send fails, failure log includes target coordinates, and recovery exception is rethrown.
6. **Invalid partition:** destination error is detected and source offset is not marked as safely recovered.
7. **Serializer mismatch:** test both raw `byte[]` and normal objects if the DLT receives both.
8. **Header provenance:** DLT record retains original topic/partition/offset and triage consumer reads them.
9. **Retries:** retry attempt logs are not confused with DLT send success; only the recoverer logs final destination.
10. **Transactional recovery:** separate producer send result from transaction commit/abort and `read_committed` visibility.
11. **PII/log injection:** malformed payloads/headers never appear raw in logs.
12. **Metric cardinality:** event IDs, offsets, and raw exceptions never become tags.

In integration tests, use a real test Kafka broker or Testcontainers to confirm the target record actually exists. Mocking `KafkaTemplate` alone proves the resolver ran, not that serializers, broker, ACLs, partitions, or send acknowledgments work.

## 21. Runbook when locating a record sent to DLT

When operations need to locate a specific record or verify a recovery, follow this order:

1. **Search logs by source coordinates:** source topic, partition, offset; add event ID/correlation ID if available and permitted.
2. **Identify log state:** `destination_selected`, `send_acknowledged`, or `send_failed`.
3. **Read destination:** topic and partition from the resolver log; do not guess by suffix if custom routing applies.
4. **Check producer/send:** serializer errors, ACLs, topic/partition existence, timeouts, and transaction outcomes if applicable.
5. **Read the DLT with proper permissions:** verify the actual record, DLT offset, and original metadata headers.
6. **Cross-check source offset:** confirm recovery completed and the consumer group advanced offsets per policy.
7. **If replaying:** record replay ID, preserve provenance, bound records, rate, and idempotency; never replay the entire DLT just because one record was missing in logs.
8. **If send failed:** restore topic/ACLs/serializers/broker, then let error handler/recovery retry per policy.
9. **Reconcile:** compare recovery attempts, send acknowledgments, DLT records, and triaged records.
10. **Preserve evidence:** log IDs, source/destination coordinates, error category, and operator per audit policy.

Never reset source offsets to “force records into the DLT” without knowing whether recovery already published. Resetting backward can reprocess and duplicate DLT sends; resetting forward can skip records lacking durable DLT copies.

## 22. Production principles

1. Obtain the DLT destination from the **actual destination resolver** of `DeadLetterPublishingRecoverer`, never log an assumed topic name elsewhere.
2. Separate `destination_selected` from `send_acknowledged` and `send_failed`.
3. Enable `setFailIfSendResultIsError(true)` when the recoverer must await send results and report errors; verify API/semantics for your Spring Kafka version.
4. When a send fails, log with context and rethrow so recovery is not treated as successful.
5. Log source topic/partition/offset alongside destination topic/partition; DLT offset is a new offset on a different topic.
6. Use `KafkaHeaders.DLT_ORIGINAL_TOPIC`, `DLT_ORIGINAL_PARTITION`, and `DLT_ORIGINAL_OFFSET` to cross-check provenance.
7. Ensure target topics and partitions exist, serializers support runtime keys/values, and ACLs permit publishing.
8. Log error classes/categories and coordinates; avoid payloads, tokens, PII, unvetted exception messages, and arbitrary headers.
9. Use only low-cardinality metric tags; per-record logs must never become metric series keyed by offset/event ID.
10. Distinguish retry attempts, DLT publishes, Kafka transaction commits, and consumer offset commits.
11. During replays, preserve provenance, stable business event IDs, and idempotency; never use trace IDs as deduplication keys.
12. Test routing, send failures, transactional visibility, offset recovery, and log sanitization prior to rollout.

**Conclusion:** logging the DLT destination must show where the source record was routed and whether the publish was acknowledged. `DeadLetterPublishingRecoverer` offers a natural extension point via its destination resolver; pairing resolver logs with send-result handling, DLT provenance headers, and structured logging yields an auditable trail for investigations. When logs stay separate from metrics, sensitive payloads stay out of logs, and recovery failures are never swallowed, operations can locate the exact record, verify the DLT, and replay safely without corrupting offsets or hiding publish errors.
