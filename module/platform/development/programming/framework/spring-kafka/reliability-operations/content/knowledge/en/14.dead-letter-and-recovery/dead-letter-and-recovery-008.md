# Stripping Exception Headers

In Spring Kafka, an unprocessable record is often moved to a **dead-letter topic (DLT)** for investigation, remediation, or replay. When writing a record to a DLT, Spring Kafka can attach Kafka headers describing the exception, source topic/partition/offset, and details needed for recovery. These headers are very helpful on the first failure, but can become a burden if the record repeatedly passes through retry, DLT, and re-drive flows.

**Stripping exception headers** is the mechanism of removing headers describing exceptions from **previous failures** when DeadLetterPublishingRecoverer prepares to publish a failed record once more. The goal is to avoid accumulating stack traces and error messages at each hop while keeping the exception information relevant to the current processing attempt.

In Spring Kafka, the property commonly referenced is **stripPreviousExceptionHeaders** on DeadLetterPublishingRecoverer. Distinguish it from **appendOriginalHeaders**, from application-added headers, and from handling payloads that failed deserialization. Separating these concepts helps avoid accidentally deleting metadata needed for recovery.

## 1. What is a Kafka header?

Every Kafka record has a topic, partition, offset, timestamp, key, value, and a collection of **Headers**. Headers are name/value pairs; values are stored as byte arrays. A single record can hold multiple headers with the same name.

Example business record:

    Topic: orders
    Partition: 2
    Offset: 418
    Key: order-123
    Value: {"eventId":"evt-001","type":"OrderCreated",...}

    Headers:
      event-id = evt-001
      trace-id = trace-abc
      schema-version = 3

When the listener fails to process it and the recoverer publishes the record to orders.DLT, the DLT record may carry additional headers:

    kafka_dlt-original-topic = orders
    kafka_dlt-original-partition = 2
    kafka_dlt-original-offset = 418
    kafka_dlt-exception-fqcn = ...
    kafka_dlt-exception-message = ...
    kafka_dlt-exception-stacktrace = ...

The exact names and set of added headers depend on the Spring Kafka version and error type. Use the constants in KafkaHeaders rather than assembling header names manually as strings in code.

Because Kafka Headers can contain multiple values under the same name, a reader that only calls lastHeader() might miss the full header history. When investigating header growth issues, inspect both the headers() list by name and total header size.

## 2. Header groups to distinguish

| Group | Example | Purpose |
|---|---|---|
| Business headers | event-id, tenant-id, schema-version | Identify and interpret the event |
| Tracing headers | trace-id, correlation-id | Correlate logs across services |
| DLT origin headers | DLT_ORIGINAL_TOPIC, DLT_ORIGINAL_PARTITION, DLT_ORIGINAL_OFFSET | Trace back to where the record originated |
| DLT exception headers | DLT_EXCEPTION_FQCN, DLT_EXCEPTION_MESSAGE, DLT_EXCEPTION_STACKTRACE | Diagnose the cause of failure |
| Deserializer headers | DeserializationException info added by ErrorHandlingDeserializer | Describe errors that occurred before the listener |
| Custom retry headers | attempt, retry-stage, first-failed-at | Track application retry policy |

The uppercase names in the table represent the KafkaHeaders constants; actual wire names are the corresponding Kafka header strings.

**Stripping exception headers** targets the old DLT exception header group managed by the recoverer. It does not mean deleting all headers, does not automatically erase event-id/trace-id, and does not replace the policy for preserving origin metadata.

If the application adds its own header holding a stack trace under a custom name, such as x-error-trace, the default mechanism cannot infer that it is also an exception header to strip. Controlling custom headers requires a custom policy.

## 3. Why can exception headers accumulate?

Consider a multi-stage recovery workflow:

    orders
      |
      | Listener fails: DatabaseTimeout
      v
    orders.DLT
      |
      | Operator fixes dependency and re-drives
      v
    orders.replay
      |
      | Listener fails again: ValidationError
      v
    orders.replay.DLT

If re-drive preserves all old headers and the recoverer on the second failure appends new exception headers, the final record can carry both DatabaseTimeout and ValidationError details.

This leads to several issues:

- Stack trace headers are often large and can substantially inflate record size after multiple DLT hops.
- Diagnostic tools may misread an old exception as the current failure cause.
- Headers containing internal class details, call stacks, or error messages should not be proliferated unnecessarily.
- Larger records increase bandwidth, storage, and deserialization overhead.
- In the worst case, record size exceeds producer/broker limits and DLT publishing itself fails.

For an event that can be replayed multiple times, decide clearly whether the system only needs the **latest** error state or a **full history** of all failures. If history is needed, store it in an investigative system or a bounded audit structure rather than repeatedly appending stack traces to Kafka headers.

## 4. What does stripPreviousExceptionHeaders do?

DeadLetterPublishingRecoverer supports the setting:

~~~java
recoverer.setStripPreviousExceptionHeaders(true);
~~~

When enabled, the recoverer removes exception headers from prior recoveries that it recognizes, then constructs exception info for the current recovery attempt per the active policy.

Key points:

1. It acts while the **recoverer prepares the record to publish** to the DLT.
2. It handles **previous exception headers**, not deleting all Kafka headers by default.
3. It is not a function running automatically on every record passing through Kafka.
4. It does not erase logs/exceptions already written elsewhere.
5. It does not stop other code from re-adding old headers after the recoverer creates the record.

Spring Kafka in versions supporting this option typically enables stripping old exception headers by default. However, defaults, recognized header sets, and customization options have evolved across versions. Check the Javadoc of DeadLetterPublishingRecoverer for your exact version and configure it explicitly if it is an operational requirement.

Comparison:

| State | Exception headers in new DLT |
|---|---|
| Do not strip old headers | May retain exceptions from prior hops and append the current hop's exception |
| Strip old headers | Old exception headers recognized by the recoverer are removed; current error details are freshly written |
| Manually delete all headers | Risks losing event-id, tracing, DLT origin, and metadata needed for recovery |

Stripping aligns with displaying the latest failure cause, not storing history. If operations needs to track multiple re-drives, write an audit record with eventId, timestamp, source/destination topics, and exception class, with clear retention bounds.

## 5. Configuring DefaultErrorHandler and DeadLetterPublishingRecoverer

The example below uses Java Configuration in Spring Kafka 3.x. A failing listener retries twice after the initial attempt; if still failing, the recoverer sends the record to the DLT.

~~~java
@Configuration
public class KafkaRecoveryConfiguration {

    @Bean
    CommonErrorHandler commonErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(kafkaTemplate);

        // Do not retain exception headers from prior recoveries.
        recoverer.setStripPreviousExceptionHeaders(true);

        // Keep original metadata logic per explicit choice.
        recoverer.setAppendOriginalHeaders(false);

        DefaultErrorHandler handler = new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(1_000L, 2L)
        );

        handler.addNotRetryableExceptions(
                IllegalArgumentException.class
        );

        return handler;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    kafkaListenerContainerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            CommonErrorHandler commonErrorHandler) {

        ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
                new ConcurrentKafkaListenerContainerFactory<>();

        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(commonErrorHandler);
        factory.getContainerProperties()
                .setAckMode(ContainerProperties.AckMode.RECORD);

        return factory;
    }
}
~~~

Key imports:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.CommonErrorHandler;
import org.springframework.kafka.listener.ContainerProperties;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;
~~~

OrderEvent is an application event type and must be defined by you. KafkaTemplate must have producer serializers compatible with the actual keys/values sent to the DLT. The example focuses on error handler setup and omits topic declarations or a full Spring Boot application.

In applications with multiple listener container factories, ensure the factory used by `@KafkaListener` actually calls `setCommonErrorHandler()`. Creating a recoverer bean without wiring it into the container will not change the listener's behavior.

## 6. Difference between stripPreviousExceptionHeaders and appendOriginalHeaders

These two properties govern two distinct metadata groups.

**stripPreviousExceptionHeaders** decides whether to remove DLT exception headers from prior recovery attempts.

**appendOriginalHeaders** decides whether to keep appending origin headers describing the record's source when the record is moved to a DLT again, even if origin headers already exist from a prior attempt.

Example:

    orders partition=2 offset=418
        |
        v
    orders.DLT partition=2 offset=57
        |
        | re-drive, keep headers
        v
    orders.replay partition=0 offset=19
        |
        v
    orders.replay.DLT

At the final stage, the system may need to know both the initial position in orders and the replay position. If appendOriginalHeaders is enabled, origin headers can be appended across hops. If disabled, the recoverer's policy favors keeping existing origin info according to the running version's rules.

Comparison table:

| Option | Metadata group | Question it answers |
|---|---|---|
| stripPreviousExceptionHeaders | Exceptions from prior recoveries | Should old errors be kept in the new DLT? |
| appendOriginalHeaders | Source topic/partition/offset | Should a chain of origin metadata be appended across multiple DLTs? |
| HeadersFunction / custom headers | Application-created headers | Which markers, correlation, or audit info should be added? |

Do not enable appendOriginalHeaders just to preserve exception history; that property does not serve that purpose. Likewise, disabling stripPreviousExceptionHeaders does not automatically guarantee a complete, reliable audit trail, because a record may be recreated by another producer with a different set of headers.

## 7. An illustrative recovery lifecycle

Suppose the initial record has eventId evt-001.

**First failure:** the orders listener hits DatabaseTimeoutException. The recoverer publishes to orders.DLT with source metadata and the current exception.

    event-id: evt-001
    DLT_ORIGINAL_TOPIC: orders
    DLT_ORIGINAL_PARTITION: 2
    DLT_ORIGINAL_OFFSET: 418
    DLT_EXCEPTION_FQCN: DatabaseTimeoutException
    DLT_EXCEPTION_MESSAGE: database unavailable
    DLT_EXCEPTION_STACKTRACE: ...first trace...

**Re-drive:** a process reads orders.DLT, fixes the data, and resends it to orders.replay. That process may keep or selectively forward required headers. The replay fails due to a different ValidationException.

**Second failure with stripping enabled:** the recoverer removes old exception headers it recognizes, then writes ValidationException details for the current processing attempt:

    event-id: evt-001
    DLT_ORIGINAL_TOPIC: orders
    ...
    DLT_EXCEPTION_FQCN: ValidationException
    DLT_EXCEPTION_MESSAGE: invalid state transition
    DLT_EXCEPTION_STACKTRACE: ...second trace...

This example demonstrates the configuration's intent; it is not a promise that every DLT record contains only one exception header. Key/value deserialization error headers, custom content, or your version's behavior may yield a different header set.

If the business goal is preserving history of both errors, record a separate audit event with eventId, attempt/replayId, and exception class. When detailed stack traces are needed, store them with controlled retention in a logging or incident management system.

## 8. Application-added headers and customization hooks

Producers and consumers can add headers directly:

~~~java
record.headers().add(
    "event-id",
    eventId.getBytes(StandardCharsets.UTF_8)
);
~~~

This header is not automatically recognized as a DeadLetterPublishingRecoverer exception header. If the application uses names like x-last-error or x-retry-stacktrace, manage their lifecycle separately.

You can attach headers via the recoverer's headers function in versions supporting `addHeadersFunction()`:

~~~java
recoverer.addHeadersFunction((record, exception) -> {
    Headers additional = new RecordHeaders();
    additional.add(
        "x-recovery-stage",
        "orders-consumer".getBytes(StandardCharsets.UTF_8)
    );
    return additional;
});
~~~

Relevant imports:

~~~java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.common.header.Headers;
import org.apache.kafka.common.header.internals.RecordHeaders;
~~~

The purpose of that function is adding markers for investigation, not recording a fresh stack trace at every hop. If you need to replace a same-named custom header, check APIs supporting replacement rather than assuming `add()` overwrites, since Kafka allows multiple headers with the same name.

Some Spring Kafka versions support mechanisms like ExceptionHeadersCreator or choosing which exception headers are generated. Those APIs offer finer control over publishing class, message, or stack trace, though method names and signatures depend on version. Check the Javadoc for your project's dependency before configuring them.

## 9. Should DLT_EXCEPTION_STACKTRACE be kept?

Stack traces are very useful for debugging code errors or how a listener called a dependency. Yet they are also typically the largest header, exposing package names, methods, line numbers, and implementation details.

You can tier the amount of information retained:

| Level | Retained information | When suitable |
|---|---|---|
| Minimal | exception class, eventId, origin, and timestamp | High-volume streams, centralized log investigation |
| Moderate | exception class, message, origin, correlation ID | Need direct visibility inside the DLT |
| Detailed | stack trace and cause chain | Low-volume DLT needing deep diagnosis |
| Multi-attempt history | External audit outside Kafka headers with replayId and failure attempt | Multi-stage re-drive workflows |

If messages or stack traces contain sensitive data, check retention policies and DLT access permissions. Adding a stack trace to a header writes data into the Kafka log; that data can be replicated, kept per retention, and read by authorized consumers.

Stripping old exception headers curbs accumulation, but does not automatically sanitize sensitive info in the **current exception**. Avoid throwing exceptions whose messages embed tokens, passwords, private payloads, or unsanitized content.

## 10. Deserialization errors require separate handling

Deserialization errors happen while the consumer reads records, before the business listener receives an object. With ErrorHandlingDeserializer, Spring Kafka can place DeserializationException details into a separate header for the error handler to process.

Example configuration:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.trusted.packages: com.example.events
~~~

Some DeadLetterPublishingRecoverer versions recover the original `byte[]` of deserialization-failed data to send to the DLT. This requires the DLT's KafkaTemplate/serializer to handle the actual value type being sent; you cannot always assume the DLT value remains an OrderEvent.

Keep these distinct:

- DLT exception headers describe the failure published by the recoverer.
- Headers from ErrorHandlingDeserializer store deserialization error details for container recognition.
- Original key/value may still need to be preserved to investigate schema or encoding bugs.

Do not delete all headers containing the word exception using a naive name filter: you might accidentally delete data Spring Kafka needs to classify deserialization failures or reconstruct payloads. Configuring stripPreviousExceptionHeaders and verifying actual library behavior is safer than an arbitrary filter.

## 11. Original headers vs. new headers across multiple topics

Operations typically needs two distinct kinds of information:

**Original source** identifies where the record started. This helps trace back to the producer or initial input.

**Current failure location** identifies which topic/partition/offset failed in the current processing attempt. If a record was re-driven through an intermediate topic, this may differ from the original source.

Not every re-drive program preserves all headers. Therefore, define the replay contract explicitly:

1. eventId must remain intact so consumers recognize the same event.
2. correlationId/traceId should be kept only when truly needed and compliant with data policy.
3. A new replay ID or attempt ID should be generated when distinguishing re-drive rounds.
4. Origin metadata must be recorded per explicit policy.
5. Exception headers from prior failures should be stripped or moved to audit.

A replayId field can be a business marker, but should not replace eventId. ReplayId identifies a replay round; eventId identifies the original event.

## 12. DLT publishing can also fail

Stripping headers can shrink record size, yet it does not guarantee the recoverer sends to the DLT successfully. Failure causes still include:

- DLT does not exist yet or producer lacks publish permissions.
- DLT has fewer partitions than the partition returned by the resolver.
- KafkaTemplate's serializer does not support the key/value or `byte[]` being sent.
- Broker is unavailable, ISR requirements are unmet, or message is too large.
- Delivery timeout leaves publish status uncertain.

In supported versions, configure the recoverer to detect send-result errors under an appropriate synchronous policy:

~~~java
recoverer.setFailIfSendResultIsError(true);
recoverer.setWaitForSendResultTimeout(Duration.ofSeconds(10));
~~~

When using these two settings, review timeouts, producer retries, and your Spring Kafka version's behavior. If recovery throws an exception, the error handler must retain the ability to retry or recover the source record per defined policy. Only commit the source record's offset once recovery satisfies the system's completion criteria.

Do not treat stripped headers as proof that the DLT persisted the record durably. They are two independent concerns.

## 13. Does enabling strip impair investigation?

It removes some information about **prior failures** from the new DLT record. That is an intentional trade-off: reducing redundant data in the current record while storing history in a more appropriate place if business requires it.

You can preserve investigative capability via:

- Structured logs keyed by eventId, replayId, topic, partition, offset, and exception class.
- Traces or correlation IDs connecting processing attempts.
- An audit table storing attempts, timestamps, errors, and re-drive decisions.
- Appropriate DLT retention and access control policies.
- Dashboards counting events entering the DLT, re-drives, successes, and failures.

The critical metric is not merely DLT record count; you need to know how many recovery rounds an eventId has repeated and why it failed most recently.

Without external auditing, a record re-driven multiple times may only retain the final exception. Make this clear to operations before enabling stripping.

## 14. Inspecting headers with the Kafka Consumer API

When reading from the DLT, inspect the exact headers each record actually received.

~~~java
for (ConsumerRecord<String, byte[]> record : records) {
    Headers headers = record.headers();

    Header latest = headers.lastHeader(
        KafkaHeaders.DLT_EXCEPTION_FQCN
    );

    String errorClass = latest == null
            ? "unknown"
            : new String(latest.value(), StandardCharsets.UTF_8);

    int exceptionHeaderCount = 0;

    for (Header ignored : headers.headers(
            KafkaHeaders.DLT_EXCEPTION_FQCN)) {
        exceptionHeaderCount++;
    }

    log.info(
        "DLT event topic={} partition={} offset={} errorClass={} count={}",
        record.topic(),
        record.partition(),
        record.offset(),
        errorClass,
        exceptionHeaderCount
    );
}
~~~

Required imports:

~~~java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;
import org.apache.kafka.common.header.Headers;
import org.springframework.kafka.support.KafkaHeaders;
~~~

This snippet illustrates reading metadata and omits building ConsumerRecords or configuring deserializers. If the DLT holds multiple value types (objects and raw `byte[]`), use a consumer or payload format capable of handling all expected cases.

Never print DLT_EXCEPTION_STACKTRACE or all headers directly to production logs. Measure total byte length and exception class if size monitoring is needed.

## 15. Testing strip behavior across two recoveries

A useful integration test must create a record carrying old exception headers, have the recoverer process a new exception, and read the record published to the DLT. The goal is verifying actual header contents after real publishing.

Scenario:

1. Create the source topic and DLT with enough partitions.
2. Create a record with a fixed eventId and some business headers.
3. Have the listener fail and move the record to the DLT the first time.
4. Re-drive the record, keeping headers per the application contract.
5. Have the listener fail a second time with a different exception class.
6. Read the new DLT record with a test consumer.
7. Assert that the old exception header was removed per the strip setting.
8. Assert that the current failure's exception was placed in the appropriate header.
9. Assert that eventId and retained source metadata are still present.
10. Assert that the record does not grow unboundedly in header size across multiple re-drives.

Use Embedded Kafka or a test broker compatible with your project's Spring Kafka version. Producer/consumer serializer setup should mirror production payloads.

Conceptual check:

~~~java
Headers headers = dltRecord.headers();

Header current = headers.lastHeader(
    KafkaHeaders.DLT_EXCEPTION_FQCN
);

assertThat(current).isNotNull();

String currentClass = new String(
    current.value(),
    StandardCharsets.UTF_8
);

assertThat(currentClass).contains("ValidationException");

// Old error marker is no longer in the corresponding exception header.
// Application event-id header must still remain intact.
assertThat(headers.lastHeader("event-id")).isNotNull();
~~~

This is an illustrative assertion; dltRecord is the record read by the test consumer from the final DLT. If the library adds key or value exception headers depending on failure type, assert against the corresponding header group. Do not rely solely on header count because valid cases can have multiple distinct exception header types.

## 16. Controlling size and sensitive information

A DLT record is still subject to the same size limits and retention as any other Kafka record. Large exception headers can cause a DLT publish to fail even when the business payload is small.

Operational safeguards:

- Measure total header size before and after re-drive.
- Bound the contents of custom headers.
- Never embed sensitive payloads inside exception messages.
- Use eventId/correlationId to link logs rather than copying full stack traces across records.
- Set DLT retention according to investigation and re-drive needs.
- Restrict DLT read ACLs because it may hold failed data and original payloads.
- Alert on DLT send failures or unusual growth in record size.

Stripping exception headers prevents header bloat across multiple recoveries. It does not shrink value size, change compression policy, or replace checking max.request.size and message.max.bytes when needed.

## 17. Common scenarios

| Scenario | Behavior to consider |
|---|---|
| Record moves to DLT the first time | Current exception headers should be added for investigation |
| Re-drive from DLT fails again | Strip old exceptions so the new record reflects the current failure |
| Replay preserves eventId and traceId | Keep business headers for idempotency and tracing |
| Full failure history required | Store audit outside Kafka headers or design bounded history |
| Very large stack trace header | Trim exception details and monitor size |
| ErrorHandlingDeserializer reports error | Distinguish deserialization headers from DLT exception headers |
| Application adds custom x-error-stacktrace | Manage that header yourself; default strip cannot guess it |
| DLT publish fails | Do not commit the source record as successfully recovered |
| Same-named header appears multiple times | Inspect headers(name) list, not just lastHeader() |

## 18. Common configuration mistakes

### Confusing strip with deleting all headers

Some applications sanitize by creating a brand-new Kafka record with no headers at all. That can erase eventId, traceId, source metadata, and schema info, making safe re-drive difficult. Remove only the target header group.

### Disabling strip to keep history

If you turn off stripPreviousExceptionHeaders merely to retain full failure history, header count can grow endlessly across re-drive rounds. Audit history should have its own structure, retention, permissions, and size limits.

### Assuming the DLT always has exactly one exception header

Failures involving key/value deserialization, cause chains, or custom headers can complicate the header set. Check specific exception headers and version contracts rather than writing logic dependent on count == 1.

### Configuring the recoverer without the listener using it

If the application has multiple ConcurrentKafkaListenerContainerFactory beans, the handler bean must be attached to the factory used by `@KafkaListener`. Using the wrong factory leaves stripping inactive on the intended listener.

### Not guarding against DLT producer send errors

If DLT publishing fails yet the error handler considers recovery complete, the source record may be committed and never reprocessed. Verify the DLT send path, serializers, timeouts, topic existence, and recovery failure handling.

### Hard-coding string header names throughout code

Header names can change across versions or differ for keys vs. values. Use KafkaHeaders constants and centralize header reading/writing in a well-scoped utility.

## 19. When should you NOT keep only the latest exception?

Some systems have long-term investigative requirements, such as payments, business auditing, or multi-service incident response. In those cases, keeping only the last error in the DLT may not suffice to explain the event's full path.

Instead of blindly turning off stripping, you can:

1. Keep the latest exception in the current DLT record.
2. Emit an audit event for each failure with eventId and replayId.
3. Store sanitized exception class/message and a trace reference.
4. Limit retention and access permissions for history.
5. Build a view or query joining failures by eventId.

This keeps Kafka headers compact while preserving structured investigative history. It also separates permission to inspect failed payloads from permission to view internal stack traces.

## 20. Production operations and observability

Monitor the entire retry, DLT, and re-drive workflow:

**DLT**

- Records moved to DLT by topic and exception class.
- DLT publish success/failure rate.
- Age of the oldest record in the DLT.
- Average/p95 record and header sizes.
- Records containing multiple exception headers of the same type.

**Re-drive**

- Events replayed by eventId/replayId.
- Re-drive success rate.
- Events returning to the DLT multiple times.
- Latest and most frequent errors across re-drive rounds.
- Time from initial failure to business recovery.

**Consumer**

- Consumer lag by group/topic/partition.
- Record processing time.
- Retry counts and recovery failures.
- Rebalances and offset commit failures.
- Duplicates detected by idempotent consumers.

Logs should include eventId, topic, partition, offset, groupId, recovery stage, and correlationId. Do not log full payloads or stack traces on every retry just to prove headers were stripped; that can expose sensitive data outside Kafka.

## 21. Spring Kafka version considerations

Spring Kafka has evolved retry/DLT APIs and behavior across releases. When applying these examples:

- Verify DeadLetterPublishingRecoverer exposes `setStripPreviousExceptionHeaders(boolean)`.
- Verify the default value in your running version; explicit configuration aids maintainability.
- Check `setAppendOriginalHeaders(boolean)` and how origin metadata is chosen after multiple recoveries.
- Check exception-header creation mechanisms and related key/value deserialization headers.
- If using a custom exception headers creator, verify how it interacts with stripping.
- Verify DLT send mechanics and conditions under which the recoverer reports publish failures.
- If using `@RetryableTopic`, check whether the framework creates its own recoverer or uses the application-configured recoverer.

CommonErrorHandler configuration serves container error handling. With `@RetryableTopic`, Spring Kafka introduces additional components managing retry/DLT topics, so do not assume every recoverer in the system shares the example bean. Identify the exact component publishing at each hop.

## 22. Guiding principles

- Enable stripPreviousExceptionHeaders when you want exception headers in the new DLT to reflect the current error and avoid accumulating old errors.
- Distinguish exception headers, origin metadata, business headers, and deserializer headers.
- Use appendOriginalHeaders for origin metadata strategy, not for controlling exception history.
- Keep eventId stable across retry/DLT/re-drive to support idempotency.
- Do not wipe all headers when you only need to remove old exception groups.
- If multi-failure history is needed, store a separate bounded audit trail.
- Control inclusion of stack traces and sensitive data in DLTs.
- Ensure the recoverer is actually attached to the target listener or retry infrastructure.
- Confirm DLT publish success before considering the source record recovered.
- Test multi-hop paths and inspect actual DLT records after recovery.
- Monitor header sizes, DLT failures, re-drive loops, and offset commits.
- Check Javadoc against the exact Spring Kafka version your application runs.

Stripping exception headers keeps DLT records after each recovery focused on the current failure cause, avoids multiplying old stack traces, and lowers the risk of header bloat. Combined with origin metadata, a stable eventId, audit policies, and reliable DLT publishing, a Spring Kafka system can replay and investigate errors repeatedly while keeping record sizes and operational visibility under control.
