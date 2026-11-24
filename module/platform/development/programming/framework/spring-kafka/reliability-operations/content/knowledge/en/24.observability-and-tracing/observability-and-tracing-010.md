# Tracing when publishing to a DLT in Spring Kafka

In a high-reliability Spring Kafka system, sending a failing record to a **Dead Letter Topic (DLT)** should not be an untraceable operation. When a message fails in a listener, goes through retries, and is routed by `DeadLetterPublishingRecoverer` to a DLT, operators need to know **where the record originated, what error triggered recovery, when the DLT publish was attempted, whether the send succeeded or failed, and which trace corresponds to that execution**.

The **Observability and Tracing** chapter asks a deeper question than merely logging an exception: **how do you see a record's path across the consumer, business processing, error handler, Kafka producer, and DLT consumer in a distributed tracing system?**

Spring Kafka supports **Micrometer Observation** for Kafka listener and `KafkaTemplate` operations in modern versions. When configured with `ObservationRegistry`, Micrometer Tracing, and a matching exporter, instrumentation can emit spans and propagate trace context via Kafka headers. Still, **DLT recovery does not automatically guarantee every span belongs to the same parent-child trace**: the error handler may run after the listener observation scope closes; publishing is asynchronous; and the DLT record may retain source headers or receive new propagation headers. These details must be verified in your actual version and configuration.

This lesson aims to build a reliable observability path: separating record metadata from trace context, enabling instrumentation in the right places, adding an observation around the recovery step itself, handling publish failures, and having reconciliation strategies when traces split or are sampled out.

## 1. What does tracing when publishing to a DLT mean?

A trace describes the steps belonging to a distributed operation. Each **span** represents an execution interval with start/end timestamps, status, and attributes. In Kafka, spans can wrap record publishing and consumption.

An ideal path:

~~~text
HTTP POST /orders
      |
      v
HTTP server span
      |
      v
Kafka producer span: orders.events
      |
      v
Kafka listener span: orders.events
      |
      +--> business process / database span
      |
      +--> Exception: invalid order
      |
      v
DLT recovery observation
      |
      v
Kafka producer span: orders.events.DLT
      |
      v
Kafka listener span: orders.events.DLT
      |
      v
Quarantine / investigation
~~~

This diagram shows the desired relationship, **without guaranteeing every span sits in a single tree by default**. Actual structure depends on trace context carried in the Kafka record, the observation scope active when the recoverer runs, sampling, and instrumentation versions.

When tracing works well, operators can answer:

- Which producer or upstream request created the event?
- Which consumer group and listener hit the error?
- Did the first error occur in deserialization, validation, or the database?
- How many times did the record retry, and over what intervals?
- Which destination topic/partition did `DeadLetterPublishingRecoverer` pick?
- Did the broker acknowledge the DLT send?
- Did the DLT consumer read and handle the record afterward?
- Did the trace split across retries or replays?

Traces complement logs, metrics, and record metadata; they do not replace offsets, DLT retention, or replay procedures.

## 2. Distinguishing Kafka messages, Observations, spans, and trace headers

| Component | Role | Example |
|---|---|---|
| Kafka `ConsumerRecord` | Data, key, headers, topic, partition, offset | Record in `orders.events`, partition 2, offset 105 |
| Spring Kafka listener container | Polls, invokes listener, manages commit/retry | `ordersListener` |
| `DefaultErrorHandler` | Decides retry or recovery after error | 2 retries then recover |
| `DeadLetterPublishingRecoverer` | Builds `ProducerRecord` for DLT and sends via `KafkaTemplate` | `orders.events.DLT` |
| `ObservationRegistry` | Manages active Observation and handlers | Observation context |
| Micrometer Tracing | Links Observation to trace/span context | `traceId`, `spanId` |
| Propagation headers | Carry trace context across Kafka boundaries | `traceparent`, `tracestate`, or configured format |
| DLT metadata headers | Store source location and failure reason | Original topic/partition/offset |
| Telemetry exporter | Ships spans to observability backend | OpenTelemetry collector / Tempo / Jaeger |

Two header groups often coexist on a DLT record yet mean different things:

1. **Tracing headers** answer which trace the record links to.
2. **DLT origin/error headers** answer which source record failed, where, and why.

A record carrying `traceparent` does not mean the recoverer wrote complete DLT original offsets. Conversely, a DLT record carrying original topic/offset does not prove trace context propagated properly.

## 3. Path when a record fails and is recovered

Example source topic:

~~~text
orders.events, partition=1

offset 500: valid OrderCreated
offset 501: OrderCreated with validation error
offset 502: valid OrderCreated
~~~

A listener:

~~~java
@Component
public class OrderListener {

    private final OrderService service;

    public OrderListener(OrderService service) {
        this.service = service;
    }

    @KafkaListener(
            id = "ordersListener",
            topics = "orders.events",
            groupId = "order-service"
    )
    public void handle(OrderCreated event) {
        service.validateAndApply(event);
    }
}
~~~

When offset 501 throws an exception, the high-level flow is:

~~~text
Poll source record 501
       |
       v
Listener invocation
       |
       +--> validateAndApply throws
       |
       v
DefaultErrorHandler
       |
       +--> Retry/backoff if retryable
       |
       +--> Attempts exhausted or non-retryable
       |
       v
DeadLetterPublishingRecoverer
       |
       +--> Select DLT destination
       +--> Create new record
       +--> Copy/add appropriate headers
       |
       v
KafkaTemplate.send(DLT)
       |
       +--> Send success
       |        |
       |        v
       |    Recovery considered complete
       |
       +--> Send error
                |
                v
           Must not be treated as successful recovery
~~~

Traces should capture **at minimum** the listener failure and the DLT produce attempt. A dedicated observation around recovery can add destination, outcome, and latency of that step.

Do not treat `send` returning a future as proof the broker accepted the record. Whether the recoverer awaits the result or surfaces send failures depends on your configuration and the semantics of `DeadLetterPublishingRecoverer` in your Spring Kafka version.

## 4. Prerequisites for tracing to work

An application generally needs:

- A Spring Kafka version with Observation instrumentation for listeners and `KafkaTemplate`.
- Micrometer Observation and `ObservationRegistry`.
- A compatible Micrometer Tracing bridge.
- An exporter/SDK to ship traces to the backend.
- A sampling policy.
- A propagator matching the header format understood across services.
- Observation enabled on the right `KafkaTemplate` and listener container.
- A backend/query UI to view `traceId` and spans.

In Spring Boot 3.x, dependencies usually include Spring Kafka, Actuator, and a tracing bridge. Maven example:

~~~xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-tracing-bridge-otel</artifactId>
</dependency>
~~~

To export spans, you also need exporter/collector configuration matching the Micrometer Tracing and OpenTelemetry SDK/bridge of your Spring Boot version. Do not assume adding a tracing bridge alone makes spans appear in the backend if no exporter is configured.

Specific dependencies and configuration must align with the **Spring Boot BOM**. Never mix arbitrary Micrometer, Spring Kafka, and OpenTelemetry versions, as that can silently break tracing or cause class incompatibilities.

## 5. Enabling Observation on the listener container

In Java configuration, enable Observation on the container factory:

~~~java
@Configuration
public class KafkaListenerObservationConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    observedOrderListenerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<
                        String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);

        factory.getContainerProperties()
                .setObservationEnabled(true);

        return factory;
    }
}
~~~

Listener referencing that factory:

~~~java
@KafkaListener(
        id = "ordersListener",
        topics = "orders.events",
        groupId = "order-service",
        containerFactory = "observedOrderListenerFactory"
)
public void onOrder(OrderCreated event) {
    orderService.validateAndApply(event);
}
~~~

Observation is enabled on **the actual factory creating the container**. If the application has multiple container factories, enabling it on one factory does not enable it for listeners using another factory.

With consumer transactions, batch listeners, or specialized error paths, event/span boundaries may differ. Verify instrumentation in your application's Spring Kafka version instead of assuming every record emits an ideal span regardless of handling mode.

## 6. Enabling Observation on the KafkaTemplate used to publish DLT

The `KafkaTemplate` used to send to the DLT also needs instrumentation:

~~~java
@Configuration
public class DltProducerObservationConfiguration {

    @Bean
    KafkaTemplate<String, byte[]> dltKafkaTemplate(
            ProducerFactory<String, byte[]> dltProducerFactory) {

        KafkaTemplate<String, byte[]> template =
                new KafkaTemplate<>(dltProducerFactory);

        template.setObservationEnabled(true);

        return template;
    }
}
~~~

This example uses `byte[]` to illustrate a DLT storing raw bytes. In practice, a failed record may carry an already-deserialized domain object or raw `byte[]` from `ErrorHandlingDeserializer`. `ProducerFactory` and serializers must match the actual DLT key/value types.

Key distinction:

- **Listener observation:** measures the consumer processing the record.
- **`KafkaTemplate` observation:** measures the producer sending a record to a topic—here, the DLT.
- **Optional recovery observation:** measures the error handler/recoverer logic deciding to send the failed record.

Enabling listener observation alone does not guarantee a DLT producer span. Conversely, a producer span does not explain why the listener threw an exception unless linked with proper context/metadata.

## 7. DeadLetterPublishingRecoverer and producer spans

A common record error handler setup:

~~~java
@Configuration
public class KafkaErrorHandlingConfiguration {

    @Bean
    DefaultErrorHandler orderErrorHandler(
            KafkaTemplate<Object, Object> dltKafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(
                        dltKafkaTemplate,
                        (record, exception) -> new TopicPartition(
                                record.topic() + ".DLT",
                                -1
                        )
                );

        DefaultErrorHandler handler =
                new DefaultErrorHandler(
                        recoverer,
                        new FixedBackOff(1_000L, 2L)
                );

        handler.addNotRetryableExceptions(
                InvalidOrderException.class
        );

        return handler;
    }
}
~~~

This example assumes `dltKafkaTemplate` has proper serializers and Observation enabled. The destination resolver returns partition `-1` so the Kafka producer picks the partition rather than forcing the source partition—useful when the DLT has a different partition count from the source topic.

For retryable errors, the handler retries per `BackOff`. When an error is non-retryable or retries exhaust, the recoverer creates a new `ProducerRecord` and calls `KafkaTemplate` to send to the DLT.

If the template is instrumented with Micrometer Observation, a **producer observation/span** can be created for the DLT send. However, **the parent-child relationship of that span** depends on the scope when the error handler invokes the recoverer.

Do not describe a unified trace as guaranteed across every path. The producer span may become a root span or link to another context if the listener observation already closed or no tracing scope is active when recovery runs.

## 8. Why can traces split at the error handler boundary?

An Observation typically holds a **current scope** bound to the thread's execution context. When `KafkaTemplate` starts a producer observation, it picks up its parent from the active scope. However, error handler exception processing may execute **outside** the listener observation's scope.

~~~text
Kafka listener observation
        |
        +--> Listener calls business service
        |
        +--> Exception
        |
        v
Listener observation scope closes
        |
        v
DefaultErrorHandler
        |
        +--> DeadLetterPublishingRecoverer
                    |
                    v
               KafkaTemplate.send(DLT)
                    |
                    +--> Not guaranteed to still have
                         listener span as parent
~~~

This is a **possibility to verify**, not a claim about exact implementation ordering in every version. When the observation closes and how the recoverer is invoked depend on Spring Kafka instrumentation and the error-handling path.

Practical consequence: the DLT producer span may appear in a different trace from the listener failure span, even for the exact same business record. If an operator opens only the original trace and sees no DLT producer span, check scope, propagation, and record metadata before concluding the recoverer never ran.

Mitigations:

1. Enable Observation properly on both listener and `KafkaTemplate`.
2. Wrap recovery in its own observation with valid context.
3. Retain correlation IDs and Kafka source metadata in logs.
4. Use supported context propagation when crossing async boundaries.
5. Inspect `traceparent`/`tracestate` on the actual DLT record.
6. Never force a false parent-child trace just to make a dashboard look continuous.

## 9. Wrapping recovery in a dedicated Observation

You can wrap the recoverer in an explicitly named observation, such as `app.kafka.dlt.recovery`. This observation measures duration and attaches bounded key-values.

~~~java
@Configuration
public class DltRecoveryTracingConfiguration {

    @Bean
    DefaultErrorHandler observedDltErrorHandler(
            KafkaTemplate<Object, Object> dltKafkaTemplate,
            ObservationRegistry observationRegistry) {

        DeadLetterPublishingRecoverer delegate =
                new DeadLetterPublishingRecoverer(
                        dltKafkaTemplate,
                        (record, error) -> new TopicPartition(
                                record.topic() + ".DLT",
                                -1
                        )
                );

        BiConsumer<ConsumerRecord<?, ?>, Exception> observedRecoverer =
                (record, error) -> {

                    Observation observation =
                            Observation.createNotStarted(
                                    "app.kafka.dlt.recovery",
                                    observationRegistry
                            );

                    observation.lowCardinalityKeyValue(
                            "source_topic_group",
                            topicGroup(record.topic())
                    );
                    observation.lowCardinalityKeyValue(
                            "error_category",
                            classifyError(error)
                    );

                    observation.observe(() ->
                            delegate.accept(record, error)
                    );
                };

        DefaultErrorHandler handler =
                new DefaultErrorHandler(
                        observedRecoverer,
                        new FixedBackOff(1_000L, 2L)
                );

        return handler;
    }

    private static String topicGroup(String topic) {
        return topic.startsWith("orders.") ? "orders" : "other";
    }

    private static String classifyError(Exception error) {
        return error instanceof InvalidOrderException
                ? "validation"
                : "other";
    }
}
~~~

Meaning:

- `DeadLetterPublishingRecoverer` still performs the DLT send.
- The recovery step gets a dedicated named observation.
- Low-cardinality key-values allow grouping metrics/traces safely.
- With a tracing handler registered, this step emits a corresponding span.
- The observation scope stays active while `delegate.accept` runs.
- An instrumented `KafkaTemplate` invoked inside that window can adopt the recovery observation as its parent, depending on `ObservationRegistry`/tracing integration setup.

**Limitation:** If `delegate.accept` returns before the broker confirms the send completed, the recovery observation's duration reflects only the recoverer call, not automatically the broker acknowledgment. Final success/error must be observed via the `KafkaTemplate` send result or matching recoverer configuration.

Hence, a recovery span alone does not prove the DLT record was durably persisted.

## 10. Parent spans, trace links, and correlation IDs

In distributed tracing, not every relationship should be forced into parent-child.

- **Parent-child:** a new step starts within the parent's active trace context.
- **Trace link:** a new span links to the context of an earlier message—well suited to async/retry workflows without requiring the same synchronous call stack.
- **Correlation ID:** a stable business identifier used to reconcile records, logs, and traces.
- **Original Kafka coordinates:** source topic, partition, and offset, pinpointing the exact record position in the log.

Example:

~~~text
Trace T1: Source producer -> Source consumer -> failure

Trace T2: DLT recovery -> DLT producer -> DLT consumer

Correlation:
  event_id = evt-100
  original_topic = orders.events
  original_partition = 1
  original_offset = 501
~~~

Even if T1 and T2 have different trace IDs, you can still connect them via event ID, DLT original metadata, and logs. If your tracing implementation supports span links, you can represent that context relationship even more accurately.

**Never hand-edit `traceparent` just to force a DLT producer span under an already-closed span** without a clear propagation design. That can falsify causal relationships or create conflicting context sources.

## 11. How do trace headers travel across Kafka?

Distributed tracing uses propagation to place trace context into a message carrier—such as Kafka headers.

A Kafka record might carry:

~~~text
topic = orders.events
partition = 1
offset = 501

headers:
  traceparent = 00-<trace-id>-<span-id>-01
  tracestate = ...
  event-id = evt-100
~~~

Values illustrate W3C Trace Context style. Actual header names depend on the configured propagator and tracing stack.

When producer Observation is active, instrumentation injects context into Kafka record headers. When consumer Observation is active, instrumentation extracts that context to create a matching observation/span.

A DLT record may retain some original headers from the source record while the recoverer appends DLT metadata. When `KafkaTemplate` publishes to the DLT within an active Observation, tracing instrumentation may add or update propagation headers on the `ProducerRecord`.

Therefore, inspect **headers on the DLT record after publishing**, not only source record headers or header-copying code. In particular, a tracing header on a DLT record may represent either the original context or a new produce operation's context depending on configuration and send path.

Never claim a specific `traceparent` is present without checking the configured propagator format and actual output.

## 12. DLT origin headers vs. trace headers

`DeadLetterPublishingRecoverer` typically attaches metadata to the DLT record to aid investigating the source record, such as:

- Original topic.
- Original partition.
- Original offset.
- Original timestamp and timestamp type, depending on capability/version.
- Consumer group or exception metadata where supported by the framework.
- Exception class/message/stacktrace headers, per configuration and version.

Spring Kafka defines DLT header constants in `KafkaHeaders`, such as `DLT_ORIGINAL_TOPIC`, `DLT_ORIGINAL_PARTITION`, and `DLT_ORIGINAL_OFFSET`.

Illustrative DLT record:

~~~text
DLT record:
  destination topic: orders.events.DLT
  destination partition: 0
  destination offset: 112

DLT origin metadata:
  original_topic: orders.events
  original_partition: 1
  original_offset: 501

Trace propagation:
  traceparent: ...
  tracestate: ...
~~~

Destination offset 112 is **the new record's offset inside the DLT**, not the source record's offset. Operators need both to reconcile.

Never read `DLT_ORIGINAL_OFFSET` as a UTF-8 string if the framework encodes the header in a binary/numeric format. Use Spring Kafka's appropriate helper/API or a controlled decoder matching the header contract.

## 13. Should original trace headers be kept when sending to a DLT?

There is no single answer for every case. Three distinct needs exist:

1. **Preserve correlation to the original journey.**
2. **Represent the DLT publish as a new step.**
3. **Avoid mixing the original trace context with the current context.**

Copying all original headers may leave the original `traceparent` intact. If `KafkaTemplate` instrumentation injects fresh context, tracing headers may be updated by the propagator. If no context is active in the recoverer, the DLT consumer may extract the original context rather than a new DLT producer span.

What to do:

- Standardize one tracing propagation format across producers and consumers.
- Inspect actual output headers after publishing.
- Never write multiple entries with the same tracing header name in a way that makes consumers pick inconsistently.
- Use `event-id` and DLT origin metadata as complementary correlation.
- If you want to retain the original trace for forensics, store a separate **`original trace ID`** under privacy and retention policies—never disguise it as a fake propagation header.
- Avoid keeping raw baggage containing sensitive data when unnecessary.

A dedicated tracking header can be named clearly, such as `original-trace-id`, though that is an **application-defined contract**, not a built-in header always present in Spring Kafka.

## 14. Propagation when DLT publishing is asynchronous

`KafkaTemplate.send` normally returns a `CompletableFuture` in modern Spring Kafka:

~~~java
CompletableFuture<SendResult<String, OrderEvent>> future =
        kafkaTemplate.send(
                "orders.events",
                "order-100",
                event
        );
~~~

Calling `send` and receiving broker confirmation can happen at different times and on different threads.

~~~text
Consumer thread
       |
       +--> DeadLetterPublishingRecoverer
                 |
                 +--> KafkaTemplate.send(DLT)
                          |
                          +--> creates observation / producer span
                          |
                          +--> send future returned
                                   |
                                   v
                            Kafka producer I/O
                                   |
                            +------+------+
                            |             |
                            v             v
                        Success        Failure
~~~

When observing, separate:

- **Recoverer invocation started**.
- **`KafkaTemplate` send invoked**.
- **Broker acknowledged publish**.
- **Future completed exceptionally**.
- **Source offset considered recovered**.

A trace showing a producer span ending normally can be interpreted differently depending on instrumentation details. Never equate the `send` method returning with the broker having persisted the record.

In production, decide whether the recoverer awaits the send result, fails on timeout, or accepts async handling. To ensure a source offset is never marked recovered when DLT publishing fails, configure appropriate behavior and test the failure path.

## 15. Tracking DLT publish failures and avoiding early offset commits

A dangerous scenario:

~~~text
Source record E fails
        |
        v
Recoverer sends to DLT
        |
        v
Broker rejects due to topic/ACL/serializer error
        |
        v
Application still treats recovery as succeeded
        |
        v
Commits source offset
        |
        v
Record E is neither in the DLT nor re-read
~~~

The desired behavior is **never marking recovery as succeeded** until DLT publishing reaches the acknowledgment level your system requires.

With `DeadLetterPublishingRecoverer`, Spring Kafka provides options to verify send results, such as `setFailIfSendResultIsError(true)` in supported versions. Example:

~~~java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(dltKafkaTemplate);

recoverer.setFailIfSendResultIsError(true);
~~~

Options for awaiting send results and timeouts depend on version, producer configuration, and use case. Explicitly define **producer acknowledgments**, producer retries, and the recovery contract.

In tracing:

- The **recovery attempt** span needs a clear outcome.
- Failures must record exception/error categories.
- Logs must include source and destination topic/partition/offset.
- Metrics must count DLT publish failures.
- Alert if recovery fails repeatedly.
- Never rely on spans alone, since sampling can drop a failing execution.

## 16. When Kafka transactions are used

In a transactional listener container, an exception can **abort** the active Kafka transaction; then `AfterRollbackProcessor` decides seek/retry/recovery. The recovery flow differs from a non-transactional `DefaultErrorHandler`.

~~~text
Transactional listener
        |
        +--> Kafka output in transaction
        |
        +--> Exception
                |
                v
         Kafka transaction ABORT
                |
                v
        AfterRollbackProcessor
                |
                +--> Retry/seek
                |
                +--> Recovery/DLT when attempts exhaust
                           |
                           v
                      DLT produce
~~~

Seeing a DLT producer span does not prove the DLT publish and source offset commit shared the same transaction. If you need **transactional recovery** for failed records, use capabilities supported by your Spring Kafka version, such as `DefaultAfterRollbackProcessor` configured with a transactional `KafkaTemplate` and `commitRecovered` when appropriate.

Never commit a source offset just because a produce span looks successful. Designing safe recovery requires clarifying transaction boundaries, producer acknowledgments, and behavior when the process crashes between DLT publish and offset commit.

Tracing reveals the steps; it adds zero atomicity across steps not already protected by a transaction.

## 17. Retries can create multiple spans for one record

A record can be processed multiple times:

~~~text
Event E, source offset 501
    |
    +--> attempt 1: DB timeout
    |
    +--> attempt 2: DB timeout
    |
    +--> attempt 3: DB timeout
    |
    +--> DLT publish attempt
~~~

Depending on the error handler, seek/redelivery, and instrumentation, multiple listener invocations can produce multiple observations/spans. One **Kafka record** does not mean a **single span**.

Distinguish:

- **`eventId`:** logical event.
- **topic/partition/offset:** Kafka coordinates.
- **delivery attempt:** processing attempt.
- **`traceId`/`spanId`:** a specific tracing context.
- **DLT publish attempt:** operation sending the failed record.
- **replay attempt:** a later processing run, possibly under a different trace.

Using trace ID as a unique event ID turns retries/replays of the same event into multiple logical entities because trace context is not stable across a business workflow. Use an `eventId` or business operation ID independent of tracing.

## 18. Non-blocking retries and traces across multiple topics

With retry topics, a record can walk a chain:

~~~text
orders.events
      |
      +--> failure
      |
      v
orders.events-retry-1000
      |
      +--> failure
      |
      v
orders.events-retry-5000
      |
      +--> failure
      |
      v
orders.events.DLT
~~~

Topic names here are illustrative, not mandatory naming rules for every Spring Kafka version.

Each publish/consume step is a new boundary:

- Producer to retry topic.
- Consumer on retry topic.
- Producer to next retry topic.
- Consumer on next retry topic.
- Producer to DLT.
- DLT consumer.

When tracing headers propagate, the steps can link together. If sampling or context propagation is inconsistent, traces can split. A retry delayed by several minutes can also leave large gaps between spans.

Do not assume non-blocking retry is compatible with every transactional listener setup. Verify framework version limits and how the error handler / retry topics operate.

A helpful dashboard pairs spans with `eventId` + original topic/offset to follow long-lived workflows.

## 19. Poison pills before @KafkaListener and missing listener spans

A record can fail during deserialization:

~~~text
KafkaConsumer.poll()
      |
      v
JsonDeserializer throws
      |
      v
Listener method is not invoked
      |
      v
Not guaranteed to produce a listener observation/span
      |
      v
Error handling or consumer poll failure
~~~

With `ErrorHandlingDeserializer`, Spring Kafka stores exception details and raw bytes in headers so the container can route the record to the error handler/recoverer.

Example consumer configuration:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.key.delegate.class]": org.apache.kafka.common.serialization.StringDeserializer
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
        "[spring.json.value.default.type]": com.example.events.OrderCreated
        "[spring.json.trusted.packages]": com.example.events
~~~

When a poison pill routes to the DLT, **a DLT producer span may exist even though no listener span exists**. That is not necessarily a tracing bug: the record never entered the listener method.

Use DLT original metadata, error handler logs, deserialization exception headers, and source coordinates to diagnose the root cause. Never count only listener span failures and assume every data error is observed.

## 20. DLT serializers and raw bytes affecting traces

A record that fails value deserialization can be emitted to the DLT as **raw `byte[]`**. A record failing business validation after deserialization may be sent as a domain object.

~~~text
Valid source JSON value
      |
      v
OrderCreated object
      |
      +--> validation failure
      |
      v
DLT value may be OrderCreated


Corrupt source JSON value
      |
      v
ErrorHandlingDeserializer
      |
      +--> raw bytes + error metadata
      |
      v
DLT value may be byte[]
~~~

The DLT `ProducerFactory` must provide serializers supporting the actual data types. If the DLT serializer fails before send completes, there will be neither a broker acknowledgment nor a successful trace span.

A producer with perfect tracing yet a serializer incapable of serializing `byte[]` still fails recovery. Tracing never replaces checking `ProducerFactory`, ACLs, topics, partitions, and message size limits.

When a DLT handles multiple payload types, you may need type-aware serializers or multiple templates; ensure tracing covers the exact `KafkaTemplate` sending the DLT record.

## 21. Low-cardinality and high-cardinality in spans/metrics

Observations can attach low-cardinality key-values to group metrics, and high-cardinality attributes in tracing per conventions and tracing integration.

**Low-cardinality**, suitable for metrics:

~~~text
source_topic_group = orders | payments | other
error_category = validation | deserialization | database | other
recovery_action = dlt | retry | skip
destination_class = dlt | quarantine
~~~

**High-cardinality**, helpful when investigating one record but unsuitable as metric tags:

~~~text
event_id = evt-100
original_partition = 1
original_offset = 501
trace_id = ...
message_key = order-100
~~~

Maintain a dedicated policy for sensitive data. Being a span attribute does not permit logging raw payloads, `customerId`, payment tokens, or headers containing PII.

Never create a Micrometer `Timer` series per offset or `eventId`. Even for logs/traces, bound sizes, sampling, and retention—especially when exception stack traces are long.

Example custom recovery observation using normalized categories:

~~~java
Observation observation =
        Observation.createNotStarted(
                "app.kafka.dlt.recovery",
                observationRegistry
        )
        .lowCardinalityKeyValue(
                "error_category",
                "validation"
        )
        .lowCardinalityKeyValue(
                "source_topic_group",
                "orders"
        );
~~~

To capture offsets in traces/logs, use tracing attributes or structured logging without turning them into unbounded metric labels.

## 22. Sampling and limits when searching DLT traces

Trace sampling lowers cost. Yet it also means a failing record may **lack a complete trace** in the backend.

A scenario:

~~~text
1,000,000 events
       |
       +--> A fraction of spans are sampled
       |
       +--> Some failing records enter DLT
       |
       +--> DLT publish has no stored trace
~~~

Therefore:

- Never rely on tracing as the sole audit ledger.
- For recovery failures, logs and counters must exist independently.
- Consider error-prioritized sampling policies if your tracing stack supports them.
- Never assume a span was exported just because code invoked the Observation API.
- With tail-based sampling, spans may appear in the backend with a delay.
- If the original trace was not sampled, DLT producer/consumer spans may also be incomplete.
- Keep `eventId` and original topic/partition/offset in DLT metadata and structured logs.

Sampling is a cost-vs-observability tradeoff; balance it against forensic needs for severe incidents.

## 23. Structured logging to bridge split traces

When traces split between the failing consumer and the DLT producer, structured logs reconstruct the link.

Example log in the recoverer:

~~~text
event=kafka_dlt_recovery
event_id=evt-100
source_topic=orders.events
source_partition=1
source_offset=501
destination_topic=orders.events.DLT
error_category=validation
recovery_phase=send_requested
trace_id=...
span_id=...
~~~

After broker confirmation:

~~~text
event=kafka_dlt_publish_result
event_id=evt-100
source_topic=orders.events
source_partition=1
source_offset=501
destination_topic=orders.events.DLT
result=success
destination_partition=0
destination_offset=112
trace_id=...
~~~

These two logs illustrate **two distinct stages**. Never log `result=success` before the DLT publish outcome is confirmed per your application contract.

A practical template should include:

- Validated `eventId` or business operation ID.
- Source topic/partition/offset.
- DLT topic/partition and offset once metadata is received.
- Exception category without recklessly logging raw payloads.
- `traceId`/`spanId` when tracing context is available.
- Producer send outcome and processing duration.
- Retry attempt if reliably supplied by the framework context.
- Consumer group and listener ID where needed for investigation.

If log MDC auto-populates `traceId`/`spanId`, remember async callbacks can run on another thread. Never assume MDC from the consumer thread automatically moves to the producer callback thread without context propagation.

## 24. Propagation across callbacks and async threads

A common failure mode:

~~~text
Consumer thread: has trace context
       |
       +--> recoverer submits async task
                |
                v
Worker thread: lacks matching scope
                |
                v
KafkaTemplate.send(DLT)
                |
                +--> producer span becomes a new root
~~~

If recovery dispatches to another executor, context bound to the original thread can be lost. To cross async boundaries, use context propagation supported by Micrometer and your runtime—never share thread-local state or `KafkaConsumer` manually.

Options:

1. Use a context-propagating `TaskExecutor`/`TaskDecorator` suited to your Spring/Micrometer version.
2. Pass immutable tracing context snapshots via official APIs.
3. When creating a producer observation, specify a valid parent context.
4. Never hold scopes open indefinitely waiting on async tasks.
5. Never call `KafkaConsumer` from another thread; `KafkaConsumer` is not thread-safe.
6. If continuous parent linkage is undesirable, start a fresh trace and correlate via `eventId`/original coordinates.

**Never copy a `traceId` string into MDC and treat that as full context propagation.** Span context also includes trace flags, sampling state, and other metadata; a bare `traceId` does not guarantee valid tracing relationships.

## 25. Attaching error categories to traces without inflating metric cardinality

A recoverer can encounter many exception types: `InvalidOrderException`, `SerializationException`, `TimeoutException`, or wrapper exceptions.

Never use the full `exception.toString()` as a tag, because the message can leak Kafka keys, payloads, or request IDs. Replace it with a bounded classifier:

~~~java
private static String errorCategory(Throwable throwable) {

    Throwable current = throwable;

    while (current != null) {
        if (current instanceof InvalidOrderException) {
            return "validation";
        }

        if (current instanceof java.net.SocketTimeoutException) {
            return "network";
        }

        if (current instanceof org.apache.kafka.common.errors
                .SerializationException) {
            return "serialization";
        }

        current = current.getCause();
    }

    return "other";
}
~~~

This is an illustrative classifier; tailor it to your real exception hierarchy. Avoid infinite loops on anomalous cause cycles; in production, guard with a step cap or visited identity set.

Low-cardinality `error_category` key-values support clean error-rate charts. Detailed stack traces belong in exception recordings/logs governed by security policies, never in per-message metric tags.

## 26. DLT consumers and the replay flow

Records in a DLT can be handled by a quarantine consumer or replay tool:

~~~text
orders.events.DLT
      |
      v
DLT listener
      |
      +--> Log origin metadata
      +--> Persist to quarantine DB
      +--> Await operator decision
      |
      v
Replay tool
      |
      +--> Republish to orders.events
      |
      v
Source consumer reprocesses
~~~

Regarding tracing:

- A DLT listener can emit a consumer span if observation is enabled.
- A replay publisher can emit a new producer span.
- Replays occur hours or days later; stretching a single parent-child tree from the initial trace is not always desirable.
- DLT original metadata and a stable `eventId` connect the event across time.
- When a replay starts a new trace, record its link to the original event in audit logs or via span links if supported.
- Never turn DLT replay into an infinite loop when a record remains invalid.

When replaying, preserve the business idempotency key; never generate a new ID for an operation that already caused side effects outside Kafka. `traceId` is not an idempotency key.

A DLT consumer should record **read**, **quarantined**, or **replayed successfully** as distinct states—never log one DLT consume span and consider the incident closed.

## 27. Metrics that must accompany DLT tracing

Traces show details of a single execution; metrics reveal incident trends and magnitude.

| Metric / signal | Purpose |
|---|---|
| DLT publish attempts | How many records were attempted for DLT |
| DLT publish success/failure | How many times brokers acknowledged or rejected |
| Recovery latency | Time spent in the recoverer step |
| Listener failure rate | Errors before reaching recovery |
| Retry attempt rate | Retry volume prior to DLT |
| Consumer lag per partition | Whether failing records are stalling partitions |
| DLT topic ingress rate | Rate of records arriving in DLT |
| DLT oldest record age | Whether investigation backlog is aging |
| DLT replay success/failure | Operational quality of recovery |
| Trace export errors / dropped spans | Whether the telemetry pipeline is losing data |
| Sampling rate | Fraction of traces observable |
| Kafka producer send errors | Errors at the producer/broker layer |
| Schema/deserialization errors | Errors that can fire before listener spans |

Never add `eventId`, offset, `orderId`, or `traceId` labels to metric counters. Those belong in logs, traces, or forensic stores.

A dashboard can drill down from **rising DLT failure rate** into sampled traces and structured logs keyed by original topic/partition/offset.

## 28. Testing tracing against real Kafka

A unit test invoking `DeadLetterPublishingRecoverer` directly does not prove `KafkaTemplate` Observation, propagation headers, and consumer spans work inside a real listener container.

With Testcontainers Kafka or `EmbeddedKafka`, build a test covering:

1. Publish an `OrderCreated` with a fixed `eventId`.
2. Enable Observation on the source listener container.
3. Deliberately throw `InvalidOrderException`.
4. Have the error handler recover the record to the DLT.
5. Enable Observation on the DLT producer `KafkaTemplate`.
6. Have a DLT consumer receive the record.
7. Collect spans in an appropriate test Observation/Tracing setup.
8. Read the DLT record's headers and metadata.
9. Assert source record, DLT destination, outcome, and trace/correlation behavior.

Test matrix to cover:

| Scenario | What to verify |
|---|---|
| Listener succeeds | Listener observation emits per configuration |
| Listener fails then retry succeeds | No DLT publish outside policy |
| Permanent error, retries exhausted | Recoverer sends to DLT |
| DLT producer observation enabled | Producer instrumentation fires |
| DLT consumer observation enabled | Consumer instrumentation fires |
| Separate recovery observation | Recovery span/metric emits per sampling and registry |
| Listener scope closes before recovery | Parent-child or trace split is clearly understood |
| Source `traceparent` present | DLT record propagation semantics verified |
| Source `traceparent` missing | Recovery still logs metadata without crashing |
| Deserializer fails before listener | Listener span is not required |
| DLT send fails due to ACL/topic | Recovery error surfaces; no wrong commit |
| DLT serializer fails | No false publish success recorded |
| DLT raw bytes | Producer serializer supports failed payloads |
| Async recovery/executor | Context propagation is never assumed |
| Sampling disabled | Metrics/logs still diagnose issues |
| Transaction abort/recovery | Traces are not mistaken for transaction commits |
| DLT replay hours later | `eventId` and origin metadata still link history |

Inspect trace exports, DLT records, source offsets, and broker acknowledgments together. Seeing a trace span alone does not prove the DLT send succeeded.

## 29. Diagnosing missing DLT traces

### Source consumer has a span, DLT producer does not

Check whether the `KafkaTemplate` actually used by `DeadLetterPublishingRecoverer` has `observationEnabled` and a valid `ObservationRegistry`/tracing bridge. A different template bean or manually created `ProducerFactory` can bypass configuration.

### DLT producer span exists, but as a new trace

Check the scope when the recoverer runs. The error handler may run outside the listener observation scope, or recovery may dispatch to another thread. Use a recovery observation, context propagation, or correlation via origin metadata as designed.

### DLT consumer is not in the same trace as the producer

Inspect injected/extracted headers, propagator formats, duplicate tracing headers, and sampling state. Do not assume headers were lost if the trace simply wasn't sampled.

### Trace shows DLT send, yet record is absent from broker

The span may reflect the send attempt or method call while the broker send failed asynchronously. Check future/producer acknowledgments, recoverer send-result policy, ACLs, topics, serializers, and producer logs.

### DLT holds the record, yet no trace exists

Sampling may have skipped the trace; instrumentation may be disabled; the error may have occurred before the listener; or the tracing exporter may have suffered an outage. DLT origin metadata and logs must still suffice for investigation.

### Trace displays the same record multiple times

This can result from retries, redeliveries, rebalances, or replays. Never use `traceId` as a unique event ID; reconcile via `eventId` and original coordinates.

### DLT spans spike sharply after an outage

Inspect error classification and backoff. A database outage can push valid records into the DLT if retry policies are misconfigured. Tracing reveals the symptom, not a substitute for retry tuning or pause/backpressure.

### Trace carries sensitive data in tags

Audit custom Observation conventions, baggage, Kafka headers, and log correlation. Remove PII/secrets from telemetry and apply proper retention/access controls.

### Broker acknowledgment duration is missing

Recovery Observation wraps only the recoverer call and may exclude async broker I/O. Use send-result callbacks or appropriate `KafkaTemplate` instrumentation to observe producer outcomes at the right layer.

## 30. Runbook for investigating a DLT incident

Suppose dashboards show a surge in DLT rate:

1. Identify the DLT topic, consumer group, and when the spike began.
2. Check DLT publish success/failure metrics and Kafka broker/producer health.
3. Pull one DLT record to inspect origin topic, partition, offset, and exception metadata.
4. Search source listener logs by original coordinates or `eventId`.
5. Inspect related `traceId`/spans if trace sampling captured data.
6. Determine whether the listener failure happened before or after deserialization.
7. Check the retry policy and how many attempts were consumed.
8. Inspect the DLT producer template and serializer handling that payload type.
9. If DLT sends failed, confirm source offsets were not marked recovered/committed improperly.
10. If traces split, reconcile via `eventId`/origin headers and inspect observation scopes.
11. If many records fail together, separate data poison pills from dependency outages.
12. Decide whether to quarantine, fix producer schemas, restore the database, or replay per procedure.
13. Audit the replay decision and verify idempotency.
14. Reconcile consumer lag, DLT backlog, and business state after remediation.

Never trigger bulk replays just because a trace pointed out an error. You must know whether records executed side effects in databases/payments before failing, since Kafka rollbacks and DLT recovery do not undo external systems.

## 31. Checklist for implementing DLT tracing

- Source Kafka listener container enables `observationEnabled` where needed.
- The `KafkaTemplate` actually used for DLT enables `observationEnabled`.
- `ObservationRegistry`, tracing bridge, propagator, and exporter are compatibly configured.
- Listener observation scope vs. error handler/recoverer timing is understood.
- Dedicated recovery Observation added if measuring/spanning the recovery step is desired.
- Do not assume DLT producer spans are children of listener spans on every error path.
- Stable correlation ID or `eventId` exists independently of `traceId`.
- DLT origin topic/partition/offset and exception metadata are preserved for forensics.
- Trace propagation headers verified on actual DLT records.
- Avoid duplicate/conflicting tracing headers when copying source headers and injecting new context.
- Never replace official context propagation APIs with raw `traceparent` string manipulation.
- Async callbacks/executors have explicit context propagation or trace-link strategies.
- DLT send results are verified per recoverer policy; send attempts are not treated as publish successes.
- DLT serializers support both domain objects and raw bytes where needed.
- Never commit source offsets as recovered if DLT publishing fails.
- Transactional listeners use matching `AfterRollbackProcessor`/recovery semantics.
- Retry topics, DLT, and replays are tracked across multiple spans or traces by design.
- Pre-listener deserialization errors have dedicated logs/metrics.
- Low-cardinality metric tags never contain `eventId`/offset/`traceId`.
- High-cardinality trace attributes/logs comply with privacy policies.
- Sampling is never the sole audit source.
- DLT metrics, producer errors, consumer lag, and replay status accompany tracing.
- Tested source failures, DLT success/failure, async propagation, and missing headers.
- Operators have a runbook correlating DLT records with traces and logs.

**Conclusion:** Tracing DLT publishing means more than enabling consumer tracing. You must observe **listener failures, error handler/recoverer execution, `KafkaTemplate` producer sends, and DLT consumers**, while preserving full origin metadata so investigations work even when traces split or are sampled out. Micrometer Observation provides the instrumentation, yet span relationships, propagation headers, and broker acknowledgments must be verified for your exact version and recovery path. A trustworthy Spring Kafka system pairs **traces, structured logs, DLT headers, metrics, and offset/recovery semantics** rather than treating a span's existence as proof a failed record was safely persisted.

