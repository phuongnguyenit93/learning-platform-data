# Accumulating Failure Headers

In a Spring Kafka system, a record that fails processing can pass through multiple stages: the main listener, a retry topic, a dead-letter topic (DLT), and then a recovery flow or parking topic. At each hop, the application may attach additional **failure headers** describing the error and the record's origin. Because Kafka allows multiple headers with the **same name**, error metadata can accumulate across publishes.

This accumulation provides a useful diagnostic history, but it also has downsides: duplicate headers, large stack traces, difficulty identifying the latest error, and the risk of exceeding record size limits after multiple forwards. Spring Kafka provides mechanisms to decide whether to retain or strip previous exception headers. This is an important part of **Dead letter and recovery** design, especially when records may be replayed or routed across multiple DLTs.

## 1. Where do failure headers appear in a flow?

Consider a service consuming payment events from `payments.requested`. The listener calls a dependent service, encounters a timeout, and retries. After exhausting attempts, the error handler uses `DeadLetterPublishingRecoverer` to publish the record to the DLT:

```text
payments.requested
    |
    | listener fails; retry per backoff
    v
DefaultErrorHandler
    |
    | retries exhausted -> DeadLetterPublishingRecoverer
    v
payments.requested.DLT
    |
    | recovery team reads, fixes, or reprocesses
    v
payments.requested.parking   (if the organization has a parking flow)
```

When moving to the DLT, Spring Kafka can attach Kafka headers containing **exception** information, the source topic/partition/offset, and metadata related to the original record. If the DLT consumer fails again and is published to another DLT or parking topic, the system may append a new set of metadata.

Not all retry types generate the same set of failure headers. **Blocking retry** may reprocess on the same topic before publishing to the DLT; **non-blocking retry** routes records through retry topics and has its own coordination headers. Header handling depends on the framework, recoverer configuration, and Spring Kafka version.

## 2. Kafka headers can hold multiple values with the same name

Kafka headers are a collection of `key -> byte[]` pairs, not a `Map<String, String>` with unique keys. Each header has a name and a byte value; multiple entries can share the same name.

For example, a record that has passed through two recovery steps may carry headers with identical names:

```text
X-Correlation-Id         = 8fa2...        (provided by the original producer)
kafka_dlt-original-topic = payments.requested
kafka_dlt-exception-fqcn  = java.net.SocketTimeoutException
kafka_dlt-exception-fqcn  = java.lang.IllegalStateException
```

The names in the example illustrate the concept. In Java code, use the `KafkaHeaders.DLT_*` constants from your running Spring Kafka version rather than hard-coding internal header strings.

The Kafka API provides two different ways to access them:

```java
Header latest = record.headers().lastHeader(headerName);

Iterable<Header> all = record.headers().headers(headerName);
```

- `lastHeader(name)` retrieves the last element with that name in the header list. It does not infer which error is most important from a business perspective.
- `headers(name)` lets you iterate through all elements with that name in the order they appear.
- `remove(name)` deletes headers with that name in a mutable `Headers` collection; removing them on a deserialized record does not automatically alter the record stored in Kafka.

Therefore, when a record carries multiple failure headers, the reader must decide whether it needs the **latest error**, the **original error**, or the **full history**. Using a helper that converts headers into a `Map<String, String>` can silently drop same-named values without throwing an error.

## 3. Common header groups when publishing to a DLT

`DeadLetterPublishingRecoverer` can attach standard Spring Kafka headers to record the error and origin. Common constant names include:

| Group | Spring Kafka constant | Meaning |
|---|---|---|
| Exception | `KafkaHeaders.DLT_EXCEPTION_FQCN` | Fully qualified name of the exception class. |
| Exception | `KafkaHeaders.DLT_EXCEPTION_CAUSE_FQCN` | Class name of the exception cause, when present. |
| Exception | `KafkaHeaders.DLT_EXCEPTION_MESSAGE` | Exception message. |
| Exception | `KafkaHeaders.DLT_EXCEPTION_STACKTRACE` | Stack trace to assist investigation. |
| Record origin | `KafkaHeaders.DLT_ORIGINAL_TOPIC` | Source topic recorded by the recoverer. |
| Record origin | `KafkaHeaders.DLT_ORIGINAL_PARTITION` | Source partition. |
| Record origin | `KafkaHeaders.DLT_ORIGINAL_OFFSET` | Source offset. |
| Record origin | `KafkaHeaders.DLT_ORIGINAL_TIMESTAMP` | Source timestamp. |
| Record origin | `KafkaHeaders.DLT_ORIGINAL_TIMESTAMP_TYPE` | Timestamp type of the source record. |

Depending on the version and failure scenario, there may also be dedicated headers for **key** or **value** deserialization errors, along with headers for retry-topic coordination. Not every header in the table always appears: for example, if an exception has no cause, cause metadata may not be created.

Note **data types**: text headers such as exception class or message are typically represented as UTF-8 bytes, whereas numeric headers like partition/offset are encoded in binary form. Do not decode every header with `new String(bytes, UTF_8)` and assume the result is valid.

## 4. Why do failure headers accumulate?

Forwarding to a DLT typically starts from a source record that already has headers. The recoverer creates a new producer record, carries over appropriate metadata, and adds headers recording the current failure.

When a DLT record passes through a recovery pipeline and is published again by a recoverer, two forms of accumulation must be distinguished:

1. **Origin information**: a record may carry origin metadata from multiple hops, helping trace back from the DLT/parking topic to both the initial topic and the most recent topic.
2. **Exception information**: each stage can raise a different exception; if all are kept, exception headers repeat under the same names and header payload size grows.

Example of a failure chain:

```text
Stage 1: payments.requested
    error: Timeout calling payment gateway
    -> payments.requested.DLT

Stage 2: consumer of payments.requested.DLT
    error: Unable to validate payload for replay
    -> payments.requested.parking

The record in parking may still contain information from both stages
if configured to retain previous headers.
```

The first header does not necessarily describe the current failure. Conversely, the last header may only describe a failure in the recovery listener, while the root cause occurred in an earlier processing attempt. You should clearly define the meaning of each field and the history-retention policy.

## 5. Two important options on DeadLetterPublishingRecoverer

Spring Kafka provides options to control metadata retention when a record that already has DLT headers is recovered again:

- `setAppendOriginalHeaders(boolean)`: controls appending additional headers representing origin information to the forwarded record.
- `setStripPreviousExceptionHeaders(boolean)`: controls removing exception headers from prior recoveries before adding new exception details.

Method names and default values should be verified against your Spring Kafka version; releases may differ in defaults and how certain header types are handled. These two options are particularly relevant when **a DLT is republished** or a record goes through multiple recovery stages.

Example configuring the recoverer to prevent piling up old exception info:

```java
@Bean
DefaultErrorHandler deadLetterErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

    recoverer.setAppendOriginalHeaders(false);
    recoverer.setStripPreviousExceptionHeaders(true);

    return new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L));
}
```

This is an illustrative configuration for a **listener not running in a transactional container**. For transactional listeners, select a compatible exception/rollback handling mechanism, such as an appropriately configured after-rollback processor; do not copy a non-transactional setup directly onto a transactional container.

In a simple **main -> DLT** pipeline, the difference between keeping and stripping old exceptions may not be obvious. It stands out once a record has passed through a DLT and is published onward to another DLT or a parking topic.

### 5.1. appendOriginalHeaders

When appending `DLT_ORIGINAL_*` headers at each hop, the record can carry multiple origin checkpoints. This helps trace its path, but also requires readers to distinguish the initial source from the most recent recovery source.

Disabling appending additional original headers can keep origin metadata more compact. However, you must determine how to preserve the initial origin if the system still needs it for replay and audit. Never assume all origin traces remain intact when another consumer builds a new producer record and only forwards a subset of headers.

### 5.2. stripPreviousExceptionHeaders

When stripping old exception headers, the forwarded record focuses on the exception that just occurred. This is useful when the goal is to avoid multiplying long stack traces across multiple recovery hops.

If you want to preserve full error history, you can choose not to strip exception headers, but you must control data volume and how they are read. In particular, do not treat every copy of `DLT_EXCEPTION_MESSAGE` as the same failure; they may come from different stages.

### 5.3. Comparing two metadata retention strategies

| Policy | Benefit | Considerations |
|---|---|---|
| Keep exception history | Trace of multiple failures right in the record | Large headers, harder to tell root/latest error, potential data leaks in stack traces. |
| Keep only latest exception | Compact record and easy diagnosis of current state | Error history can be lost unless logged/traced or stored in an audit store. |
| Keep controlled original provenance | Replay easily traces back to source | Must clearly specify which field is initial origin vs. current stage. |
| Custom summary headers only | Easy to query by short error tags | Must manage versioning, format, and metadata consistency yourself. |

## 6. Reading all failure headers in a DLT listener

When debugging, start by checking **how many values exist for the same header**, then decide which value to display. The following example reads the exception classes stored in a record:

```java
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;
import org.apache.kafka.common.header.Headers;
import org.springframework.kafka.support.KafkaHeaders;

public final class FailureHeaderReader {

    private FailureHeaderReader() {
    }

    public static List<String> exceptionClasses(Headers headers) {
        List<String> result = new ArrayList<>();

        for (Header header :
                headers.headers(KafkaHeaders.DLT_EXCEPTION_FQCN)) {
            byte[] value = header.value();
            if (value != null) {
                result.add(new String(value, StandardCharsets.UTF_8));
            }
        }

        return result;
    }

    public static String latestExceptionClass(Headers headers) {
        Header latest =
                headers.lastHeader(KafkaHeaders.DLT_EXCEPTION_FQCN);

        return latest == null || latest.value() == null
                ? null
                : new String(latest.value(), StandardCharsets.UTF_8);
    }
}
```

The DLT listener can call these two methods to record the entry count and the latest exception:

```java
@KafkaListener(topics = "payments.requested.DLT")
public void onDeadLetter(ConsumerRecord<String, PaymentEvent> record) {
    List<String> classes =
            FailureHeaderReader.exceptionClasses(record.headers());

    String latest =
            FailureHeaderReader.latestExceptionClass(record.headers());

    log.warn("DLT record topic={} partition={} offset={} "
                    + "exceptionHeaderCount={} latestException={}",
            record.topic(), record.partition(), record.offset(),
            classes.size(), latest);

    recoveryService.handle(record);
}
```

In production, avoid logging full exception messages, stack traces, or payloads for every record if they may contain sensitive information. If detailed investigative data is needed, use storage with appropriate access controls.

## 7. Understanding original headers vs. current headers

After multiple forwards, a record has at least three concepts that must be kept distinct:

| Concept | Example | Purpose |
|---|---|---|
| Initial origin | `payments.requested`, partition 2, offset 105 | Trace the original business record. |
| Current stage | `payments.requested.DLT`, partition 2, offset 41 | Know where the current consumer is reading from. |
| Latest error | `IllegalStateException` in recovery listener | Diagnose why the current stage failed. |

`ConsumerRecord.topic()`, `partition()`, and `offset()` always refer to the **record currently being read**, not the original record. To find the initial origin, read provenance headers or a stable event identifier carried with the payload.

When using `DLT_ORIGINAL_PARTITION` or `DLT_ORIGINAL_OFFSET`, remember that numeric values are binary-encoded bytes. If decoding is needed, use an API/serializer compatible with the format Spring Kafka writes. Do not convert raw bytes directly to a string and interpret them as a partition or offset.

An architecture with multiple hops should explicitly define a **business event ID** or **correlation ID** from the original producer. These fields help correlate records across topics even though Kafka offsets and partitions change on each publish.

## 8. Deserialization failure and raw payloads

Not every failure begins inside the listener method. A record may fail to deserialize into a Java object due to malformed JSON, incompatible schemas, or serializer changes.

When `ErrorHandlingDeserializer` is configured, Spring Kafka can place deserialization error details into headers for the error handler and recoverer to process. For this error type, be extra careful:

- The payload object may never have been constructed; the listener may not be invoked.
- The raw bytes of the key/value may need to be forwarded to the DLT for investigation or replay.
- Deserialization error headers may contain exception details serialized in an internal format.
- The producer sending to the DLT must support the actual data emitted by the recoverer, which may be raw bytes rather than normal Java objects.

Do not assume every failure header is UTF-8 or safe to expose in logs. For deserialization failures, use handlers/recoverers supported by Spring Kafka and an appropriate quarantine workflow rather than manually decoding all bytes in headers.

## 9. Custom headers and replacing old values

Beyond standard headers, applications often want to store short, searchable metadata:

```text
x-correlation-id = c8d7c5...
x-first-failed-at = 2026-11-15T12:00:00Z
x-last-failure-stage = inventory-lookup
x-failure-category = TRANSIENT_DEPENDENCY
x-recovery-owner = order-platform
```

These `x-*` headers are application conventions, not headers automatically provided by Kafka or Spring Kafka. They can be added via the recoverer's `headersFunction` or a dedicated pipeline publisher, depending on design.

When adding a header whose name already exists, Kafka normally appends another entry with the same name. If the goal is to store **a single latest value**, write headers intentionally: remove previous entries on the outgoing producer record, or use a single-value/replacement header mechanism supported by your Spring Kafka version. Do not simply call `headers.add("x-last-failure-stage", value)` and assume the old value was overwritten.

A consistent design can split custom headers into two groups:

- **Immutable**: `x-event-id`, `x-correlation-id`, `x-first-failed-at`; set once and forwarded intact.
- **Mutable/current state**: `x-last-failure-stage`, `x-last-error-code`, `x-recovery-attempt`; replaced per clear policy at each stage.

If you need to retain complete multi-stage history, consider a separate audit store. You do not need to stuff every stack trace or processing state into Kafka headers.

## 10. Header size and message limits

Kafka headers are part of the record stored and transmitted through brokers. Each time an exception stack trace or another set of origin metadata is added, the record can grow substantially.

For example, if each recovery attaches an 8 KB stack trace and a record passes through 20 stages without stripping old metadata, the stack traces alone can occupy roughly 160 KB, excluding key/value, other headers, and encoding overhead.

Consequences may include:

- Records exceeding request/message size limits at the producer, broker, or topic, causing retry/DLT publishing to fail.
- Increased network traffic and storage usage, especially during high error volume.
- Higher logging and operational costs if the system exports all headers to traces/logs.
- Exception data containing internal details or personal data being replicated across multiple topics.

Do not fix this by blindly raising all message size limits. Address the root cause of accumulation, trim metadata, and limit forwarding hops. If full stack traces are needed, store them once in logs or an observability backend keyed by correlation ID for lookup during investigation.

## 11. Differences in behavior between blocking retry and retry topics

**Blocking retry** via `DefaultErrorHandler` typically retries processing the record before recovery. DLT exception headers are usually added when the recoverer actually publishes the record to the destination topic, not necessarily on every listener failure within the same poll.

**Non-blocking retry** via `@RetryableTopic` creates retry destinations and the information needed to coordinate attempt counts, delays, and routing. A record can be published multiple times through retry topics before reaching the DLT. The framework may update headers related to retry attempts and timestamps; exception and DLT header usage may differ from a manually configured recoverer.

Therefore, do not rely on the count of `DLT_EXCEPTION_FQCN` headers to determine the exact **number of retries**. Retries within the same container might not add new headers, whereas a DLT republish can add multiple headers in a single step. To track attempt counts, use the delivery-attempt API or retry metadata provided by the specific retry mechanism, and measure on the actual running topology.

## 12. Choosing a history retention policy based on recovery needs

No single header policy fits every pipeline. Classify your requirements first:

| Requirement | Suggested policy |
|---|---|
| DLT consumer only needs the current error | Strip old exceptions and keep one latest error set. |
| Need to trace back to the original business topic record | Keep stable event ID and provenance; define how original headers are preserved. |
| Need audit across multiple retries/recoveries | Store compact history or write separate audit events, with bounded size. |
| Records risk containing sensitive payloads | Do not duplicate stack traces/headers with sensitive data across multiple topics. |
| DLT is automatically replayed in multiple rounds | Enforce replay limits, markers, and a policy to replace failure headers. |
| Multiple services handle a failed record | Use a shared correlation ID and explicit owner/stage fields. |

If using multiple recovery pipelines, document the header contract for each stage. For example, `x-event-id` is immutable; `x-last-failure-stage` always represents the latest stage; original headers are stored once; standard exception headers follow the agreed strip/append setting.

## 13. Production workflow for inspecting failure headers

When a DLT starts growing rapidly or records fail to publish due to size, investigate in order:

1. Identify the current topic, partition, and offset of the failed record.
2. Read headers as an **entry list**, avoiding immediate conversion to a map that drops duplicate header names.
3. Count `DLT_EXCEPTION_*` and `DLT_ORIGINAL_*` entries and identify repeated names.
4. Distinguish the first error, the latest error, and any error from the recovery listener.
5. Check `DeadLetterPublishingRecoverer` settings, including append-original and strip-previous-exception policies.
6. Trace the record's forwarding path: main, retry topic, DLT, parking, or replay.
7. Measure record size and how much large stack traces/headers contribute.
8. Determine whether the record can still be replayed or needs quarantine for manual investigation.

Useful metrics include ingress counts per DLT, publish failures, retry attempts, replayed record counts, record sizes on recovery topics, and message-size-limit errors. Metrics should be tagged by topic/service and error category at controlled cardinality.

When investigating in production, maintain appropriate access controls on the DLT and logs. Stack traces can contain internal class names, dependency URLs, or sensitive info in messages; avoid copying raw headers into public dashboards.

## 14. Testing header accumulation behavior

Integration tests with Embedded Kafka or Kafka Testcontainers help confirm how your Spring Kafka version actually adds and removes headers. This is much more reliable than assuming behavior from a general description.

Recommended test scenarios:

1. Send a valid record that makes the listener throw an exception; verify the record reaches the DLT with the expected failure headers.
2. Read the DLT record and republish it via a recoverer; verify the count of same-named headers when configured to keep old exceptions.
3. Repeat with `setStripPreviousExceptionHeaders(true)`; verify old error metadata does not keep piling up as before.
4. Test `setAppendOriginalHeaders(false)` across multiple hops; verify provenance needed for replay is preserved as designed.
5. Attach two custom headers with the same name; verify the difference between `headers(name)` and `lastHeader(name)`.
6. Trigger a deserialization error; verify error info and raw key/value are still handled safely in the DLT.
7. Create a record with a large stack trace or multiple replays; observe how the system behaves when exceeding message size limits.
8. Trigger an exception in the recovery listener; verify the current error is not mistaken for the original business failure.

Write assertions against the **actual header values**, occurrence counts, and destination record. Do not rely on field ordering printed when serializing headers to JSON, as that conversion can drop duplicate-name entries.

## 15. Common mistakes

- **Treating headers as a single-value map per name:** failure history can be lost when deserializing metadata.
- **Using `lastHeader()` as the complete error history:** it only returns the last value and omits prior failures.
- **Assuming every retry creates a set of DLT exception headers:** behavior depends on the retry mechanism and publish timing.
- **Always keeping every stack trace:** headers grow across recovery hops, leading to publish failures and higher costs.
- **Deleting all headers to keep records small:** you may lose correlation IDs, event IDs, and provenance essential for replay.
- **Confusing original topic with current topic:** `ConsumerRecord.topic()` is the topic currently being read, which may be the DLT rather than the initial source.
- **Reading partition/offset as UTF-8 strings:** numeric fields may be binary-encoded.
- **Retrying failed DLT records indefinitely:** easily creates republish loops and uncontrolled header accumulation.
- **Not checking the Spring Kafka version:** default append/strip behavior and framework header sets can change.
- **Logging raw error headers without controls:** can expose sensitive payloads and overload the logging system.

## 16. Design principles for long-term operable recovery

A good dead-letter flow retains enough information to identify the **original record, latest error, recovery owner, and replay status**. Start with a stable event identifier, explicitly define the original-header retention policy, bound exception history, and carry only the metadata genuinely needed for the next step.

When investigating repeated failures, store structured history in an audit log or suitable datastore rather than forcing Kafka headers to carry unbounded history. When republishing a record, explicitly choose which fields are preserved, which are replaced, and which are appended. In particular, a record entering a DLT must have a bounded replay policy to prevent endless loops.

**Accumulating failure headers** is a natural consequence of Kafka allowing multiple headers with the same name and of multi-step recovery pipelines. Understanding append, strip, and multi-value header reading rules lets a Spring Kafka system retain needed error trails while keeping message size, sensitive data, and retry/replay behavior under control.
