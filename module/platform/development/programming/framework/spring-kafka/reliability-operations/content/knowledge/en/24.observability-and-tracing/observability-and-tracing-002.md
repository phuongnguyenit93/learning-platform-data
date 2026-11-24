# ObservationConvention

In Spring Kafka, observability does not stop at knowing whether a Kafka consumer is running or whether a producer called `send()`. Operations teams need to follow an event across multiple services, measure processing duration, classify errors, and identify which topic is slow—without overloading the metrics system with millions of distinct tag values.

**ObservationConvention** in **Micrometer Observation** is the mechanism that defines how to construct the **observation name**, **contextual name**, and **KeyValues (tags)** from an Observation Context. Spring Kafka provides two key specializations:

- **KafkaListenerObservationConvention**: customizes the observation of a listener receiving Kafka records.
- **KafkaTemplateObservationConvention**: customizes the observation of a `KafkaTemplate` sending records.

These two interfaces build on Micrometer's `ObservationConvention` and let an application add controlled business attributes to metrics/traces, such as `app.pipeline=orders-projection` or `app.domain=payments`. They do not alter the Kafka payload, do not create retries, and do not replace tracing propagation mechanisms.

This lesson belongs to the **Observability and Tracing** chapter of **Spring Kafka Reliability Operations**, progressing from the Observation model to writing conventions, wiring them into containers and `KafkaTemplate`, managing low/high cardinality, testing, version migration, and production runbooks.

## 1. Purpose of ObservationConvention

Suppose an order event flows through this chain:

~~~text
checkout-api
    -> Kafka topic orders.created
    -> orders-projection consumer
    -> PostgreSQL orders_read_model
    -> Kafka topic orders.projected
    -> notification-service
~~~

With only disconnected logs, when an order processes slowly, an operator must manually search each service. With only a single timer that does not distinguish listener or domain, dashboards also struggle to tell which component is causing tail latency.

An observation can provide:

1. A **stable name** for the measured operation, such as `spring.kafka.listener`.
2. **Low-cardinality tags**, used to group metrics with a finite set of values.
3. **High-cardinality tags**, useful for traces/spans but unsuitable as metric dimensions.
4. A **contextual name**, making spans readable in the tracing UI.
5. **Operation context**, such as the Kafka topic, listener ID, group ID, or record metadata accessible to the convention depending on the version.

**ObservationConvention** partially governs how this metadata is mapped into names and tags. It does not enable Micrometer Observation by itself, create exporters, or guarantee that data reaches Prometheus/Jaeger/Tempo if the registry, handlers, or tracing backend are not configured.

### 1.1 Overall diagram

~~~mermaid
flowchart TD
    A["Kafka ProducerRecord / ConsumerRecord"] --> C["Spring Kafka observation context"]
    C --> V["ObservationConvention"]
    V --> N["Observation name + KeyValues"]
    N --> R["ObservationRegistry"]
    R --> M["Metrics ObservationHandler"]
    R --> T["Tracing ObservationHandler"]
    M --> P["MeterRegistry / Prometheus"]
    T --> X["Tracer / OTLP / tracing backend"]
~~~

Looking at the diagram, the convention is the **naming and classification layer**, while `ObservationRegistry` and `ObservationHandlers` determine how the observation is turned into metrics/tracing.

## 2. Why distinguish Observation from Timer?

Spring Kafka has two common mechanisms:

| Mechanism | Switch | Goal |
|---|---|---|
| Legacy Micrometer listener timers | `ContainerProperties.micrometerEnabled` | Measure listener invocations via Micrometer Timer |
| Micrometer Observation | `ContainerProperties.observationEnabled` | Create Observations that can yield metrics and tracing |
| Legacy Micrometer template timers | `KafkaTemplate.micrometerEnabled` | Measure Kafka send operations |
| KafkaTemplate Observation | `KafkaTemplate.observationEnabled` | Observation for the producer send flow |

In Spring Kafka **3.0 and later**, Micrometer Observation is supported for `KafkaTemplate` and listener containers. When Observation is enabled, the corresponding legacy Micrometer timer mechanism is disabled so Observation handles instrumentation, per framework semantics. Different Spring Kafka releases vary in batch listener support; check the version section near the end of this lesson.

### 2.1 Setting ObservationConvention does not enable Observation

The following snippet only sets the convention:

~~~java
factory.getContainerProperties()
       .setObservationConvention(customConvention);
~~~

If `observationEnabled` remains `false`, the convention may not be used on that listener path.

Both are required:

~~~java
factory.getContainerProperties()
       .setObservationEnabled(true);

factory.getContainerProperties()
       .setObservationConvention(customConvention);
~~~

Similarly for `KafkaTemplate`:

~~~java
kafkaTemplate.setObservationEnabled(true);
kafkaTemplate.setObservationConvention(templateConvention);
~~~

A common mistake is declaring a convention bean and assuming Spring Kafka will automatically apply it to every listener container. Do not assume that without verifying actual auto-configuration and factory wiring: **attach the convention explicitly to the exact `KafkaTemplate` or `ContainerProperties`**.

## 3. Specialized interfaces in Spring Kafka

Micrometer provides the general interface:

~~~java
ObservationConvention<T extends Observation.Context>
~~~

Spring Kafka introduces two specialized interfaces:

~~~java
KafkaListenerObservationConvention
KafkaTemplateObservationConvention
~~~

Comparison table:

| Interface | Context type | Where configured |
|---|---|---|
| `KafkaListenerObservationConvention` | `KafkaRecordReceiverContext` | `ContainerProperties.setObservationConvention(...)` |
| `KafkaTemplateObservationConvention` | `KafkaRecordSenderContext` | `KafkaTemplate.setObservationConvention(...)` |

These classes belong to the Spring Kafka package:

~~~java
org.springframework.kafka.support.micrometer
~~~

The corresponding contexts live in the same package.

### 3.1 Default listener convention

Spring Kafka provides:

~~~java
KafkaListenerObservation.DefaultKafkaListenerObservationConvention
~~~

This is the default implementation of `KafkaListenerObservationConvention`. You can **extend the default class** and append tags rather than rewriting everything from scratch.

### 3.2 Default template convention

Spring Kafka provides:

~~~java
KafkaTemplateObservation.DefaultKafkaTemplateObservationConvention
~~~

Likewise, this class produces the default names/tags for producer observations. When adding a few application-specific attributes, extending the default is usually safer than replacing the entire contract.

### 3.3 Receiver and sender contexts

**`KafkaRecordReceiverContext`** represents the context of receiving a `ConsumerRecord`. In compatible versions, it exposes accessors such as:

~~~java
context.getListenerId();
context.getSource();      // Source topic
context.getRecord();      // ConsumerRecord
~~~

Newer versions may add:

~~~java
context.getGroupId();
context.getClientId();
context.getPartition();
context.getOffset();
~~~

**`KafkaRecordSenderContext`** represents the context of sending a `ProducerRecord`:

~~~java
context.getBeanName();
context.getDestination(); // Destination topic
context.getRecord();      // ProducerRecord
~~~

Do not call `getRecord()` in code targeting an overly old Spring Kafka version: this method was added for dynamic tags in Spring Kafka **3.0.6** and later. Some receiver accessors such as `getGroupId`/`getClientId` were added in later releases. Always check the exact API against your project's pinned dependency.

## 4. The four methods of an ObservationConvention

A custom `ObservationConvention` can customize these aspects:

### 4.1 getName()

**`getName()`** returns a stable observation operation name. Spring Kafka defaults use these well-known names:

~~~text
spring.kafka.listener
spring.kafka.template
~~~

This name is commonly used across metrics/tracing instrumentation. Changing `getName()` arbitrarily can break continuity in dashboards, alerts, and semantic conventions.

### 4.2 getContextualName(context)

**`getContextualName()`** provides a human-readable name for a specific operation in the tracing UI. For example, names tied to the topic or consume/publish action:

~~~text
orders.created receive
orders.projected publish
~~~

The contextual name is not a metric label for grouping every business record. Avoid putting UUIDs/order IDs into the span name of every event unless necessary.

### 4.3 getLowCardinalityKeyValues(context)

This method returns **low-cardinality tags**—labels with a bounded set of values suitable as metric dimensions.

Examples:

~~~text
app.domain=orders
app.pipeline=projection
app.stage=consume
messaging.system=kafka
~~~

Low-cardinality tags can appear on both metrics and traces. They must remain very stable, have a predictable list of values, and avoid containing personal data.

### 4.4 getHighCardinalityKeyValues(context)

This method returns **high-cardinality tags**, typically meaningful in tracing. Examples can include offset metadata, partition, client ID, or more detailed attributes depending on version and default convention.

High-cardinality does not mean "free license to put arbitrary sensitive content into traces." Tracing backends also impose limits on ingestion, retention, sampling, access control, and privacy.

### 4.5 supportsContext(context)

The `ObservationConvention` interface includes a mechanism to decide whether a convention supports a specific `Observation.Context`. When using `KafkaListenerObservationConvention`/`KafkaTemplateObservationConvention`, the specialized interface provides default semantics supporting the corresponding context.

Override `supportsContext()` only when you have a real reason and understand convention selection mechanics. A wrong predicate can prevent your custom convention from being applied.

## 5. How do low-cardinality and high-cardinality differ?

This is the most important design decision when implementing an `ObservationConvention`.

| Property | Low-cardinality | High-cardinality |
|---|---|---|
| Value set | Finite, relatively small | Can change on every event |
| Safe example | `app.domain=orders` | Kafka offset if needed for trace |
| Primary purpose | Metrics aggregation and trace classification | Trace detail/correlation |
| Risk | Metric series explosion when misused | Tracing storage/cost, privacy |
| Typically used as Prometheus labels | Yes | Should not be |
| Should contain orderId/eventId | No | Only if truly required and checked against data policy |
| Can vary per message | Should not | Possibly, but must be controlled |

### 5.1 Why can a single bad tag break monitoring?

Suppose a timer has:

- 10 listener IDs.
- 2 results.
- 5 error categories.
- 3 environments.
- 20 pod instances.

The theoretical combination is already:

~~~text
10 x 2 x 5 x 3 x 20 = 6,000 series
~~~

Adding `app.order_id` with 1 million values causes series count to explode. With histogram buckets, the cost can be even higher.

**Do not put Kafka offsets, event IDs, user IDs, order IDs, request IDs, tokens, or raw keys into low-cardinality `KeyValues`.**

### 5.2 High-cardinality also needs a budget

Traces are not "a free dumping ground for any data." Traces may be exported to a third-party vendor system, indexed for organization-wide search, and retained for long periods.

Before adding a high-cardinality field:

1. Is the field actually needed for debugging?
2. Does it contain PII or secrets?
3. Can a hash or safer correlation ID be used instead?
4. Are sampling/retention policies appropriate?
5. Is there a value length limit?
6. Who has permission to view and export traces?
7. Does it duplicate data already supplied by the default convention?

A safe approach is to add only **classification** business tags and use structured logs to store record details under proper access control.

## 6. Custom KafkaListenerObservationConvention template

The lowest-risk pattern is extending the default convention and **appending tags**, retaining the framework's semantic tags.

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;

import org.springframework.kafka.support.micrometer.KafkaListenerObservation;
import org.springframework.kafka.support.micrometer.KafkaRecordReceiverContext;

public class OrdersListenerObservationConvention
    extends KafkaListenerObservation.DefaultKafkaListenerObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(
            KafkaRecordReceiverContext context) {

        return super.getLowCardinalityKeyValues(context)
            .and(KeyValue.of("app.domain", "orders"))
            .and(KeyValue.of("app.pipeline", "projection"));
    }
}
~~~

This example does not invent a new metric name; it keeps the default name and adds two low-cardinality tags with small value sets.

### 6.1 Why call super?

The default convention may attach semantic `KeyValues` defined by Spring Kafka, such as listener identity, messaging system, source topic, or group metadata depending on version.

If you override and return:

~~~java
return KeyValues.of(
    KeyValue.of("app.domain", "orders")
);
~~~

you may accidentally **strip important default tags** from metrics/traces. That causes dashboards using default tags to lose data or traces to lack key context.

Therefore, when you only need to add tags, prefer:

~~~java
return super.getLowCardinalityKeyValues(context)
    .and(KeyValue.of("app.domain", "orders"));
~~~

Replace the convention completely only when you have an intentional semantic convention design and have verified the metric schema and tracing backend.

### 6.2 Namespace your key names

Names like `app.domain` and `app.pipeline` avoid colliding directly with standard Kafka/Micrometer semantic keys.

Do not reuse a standard key, such as `messaging.system`, to hold custom domain values. Adding duplicate keys with different values can cause confusing downstream behavior, deduplication issues, or inconsistent labels.

### 6.3 Do not add topic as a custom tag if the default already provides it

In modern versions, the default Kafka listener observation already includes messaging semantic attributes such as source topic. If you only want to group by topic, check the default tags first.

Adding both `app.topic` and `messaging.source.name` with identical values duplicates data and increases cost. Only add a custom tag when you need a different business-level grouping.

## 7. Attaching the convention to a listener container factory

Example bean declarations:

~~~java
@Configuration
public class OrdersListenerObservationConfiguration {

    @Bean
    OrdersListenerObservationConvention ordersObservationConvention() {
        return new OrdersListenerObservationConvention();
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            OrdersListenerObservationConvention convention) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        factory.getContainerProperties()
               .setObservationEnabled(true);

        factory.getContainerProperties()
               .setObservationConvention(convention);

        return factory;
    }
}
~~~

Listener referencing that exact factory:

~~~java
@Component
public class OrderProjectionListener {

    private final OrderProjectionService service;

    public OrderProjectionListener(OrderProjectionService service) {
        this.service = service;
    }

    @KafkaListener(
        id = "orders-projection",
        groupId = "orders-projection-prod",
        topics = "orders.created",
        containerFactory = "ordersListenerFactory"
    )
    public void handle(OrderEvent event) {
        service.apply(event);
    }
}
~~~

`OrderEvent` and `OrderProjectionService` are illustrative examples. `ConsumerFactory` must have Kafka bootstrap/security, deserializers, error handler, and concurrency settings appropriate for your real environment.

### 7.1 Custom factories must preserve other reliability settings

If the application already has a factory with `DefaultErrorHandler`, `AckMode`, transaction manager, interceptors, or message converters, do not replace it with a bare-bones factory just to enable Observation.

Observability changes must not accidentally alter:

- Consumer group ID or assignment.
- Deserializers / `ErrorHandlingDeserializer`.
- Retry and DLT policies.
- `AckMode` or manual acknowledgment.
- Transaction boundaries.
- Threading/concurrency.
- Pause/resume behavior.

Apply Observation settings to the existing factory or through a clearly controlled factory customizer.

### 7.2 Conventions attach to factories, not globally across a deployment

A project may have:

~~~text
ordersListenerFactory  -> OrdersListenerObservationConvention
paymentsListenerFactory -> PaymentsListenerObservationConvention
auditListenerFactory    -> Default convention
~~~

Each factory can have a different policy. Across multiple pods, a convention bean inside one pod affects only the instance running in that pod. Deployment-wide metrics/tracing are aggregated by the monitoring backend.

## 8. Dynamic tags from ConsumerRecord

Starting with Spring Kafka **3.0.6** and later, the observation context exposes the record to custom conventions so they can build dynamic tags.

Example categorizing the source topic into a bounded **enum-like route**:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.support.micrometer.KafkaListenerObservation;
import org.springframework.kafka.support.micrometer.KafkaRecordReceiverContext;

public class RoutedListenerObservationConvention
    extends KafkaListenerObservation.DefaultKafkaListenerObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(
            KafkaRecordReceiverContext context) {

        ConsumerRecord<?, ?> record = context.getRecord();

        String route = switch (record.topic()) {
            case "orders.created" -> "orders";
            case "payments.completed" -> "payments";
            default -> "other";
        };

        return super.getLowCardinalityKeyValues(context)
            .and(KeyValue.of("app.route", route));
    }
}
~~~

This snippet uses a Java switch expression; if the project uses an older Java version, replace it with a switch statement or `if-else`.

**Key takeaway:** `route` only takes three values regardless of changing record keys, offsets, or event IDs. It is a dynamic record-derived tag that remains **low cardinality**.

### 8.1 Do not perform heavy work inside a convention

`getLowCardinalityKeyValues` can be invoked on the processing path of every record. Never use a convention to:

- Query a database.
- Call an HTTP API.
- Parse large JSON payloads solely to extract a tag.
- Call a secrets service.
- Increment/decrement business counters.
- Mutate Kafka record headers or offsets.
- Throw exceptions due to invalid business data.

If you need event-type classification from payloads, establish a simple header/contract metadata with a whitelist or instrument it separately at the service layer.

### 8.2 Headers can be missing or malformed

If you extract an event type from a header, make sure to:

1. Check the header for `null`.
2. Decode UTF-8 according to the contract.
3. Validate length.
4. Map onto a whitelist with a fixed set of values.
5. For unknown values, return `"other"` rather than creating a new tag from the raw header.
6. Never throw an exception from the convention and crash the whole consumer over a bad header.

An observation convention **must never become a mandatory parser or validator of business payloads**. Listener reliability takes priority over metric label granularity.

## 9. High-cardinality KeyValues for listeners

A custom convention can add high-cardinality metadata:

~~~java
@Override
public KeyValues getHighCardinalityKeyValues(
        KafkaRecordReceiverContext context) {

    return super.getHighCardinalityKeyValues(context);
}
~~~

The example intentionally adds nothing because Spring Kafka's default may already provide Kafka offset, partition, client ID, or other semantic attributes depending on version.

When you need to add an approved correlation attribute, construct the appropriate `KeyValue` from context or application metadata. However, do not copy raw keys/values or customer information into traces by default.

### 9.1 Why shouldn't high-cardinality tags be used for metrics?

Micrometer metrics handlers primarily consume low-cardinality `KeyValues` to create time series. High-cardinality `KeyValues` fit trace tags better, and must not be used as per-record metric dimensions.

If you force offsets into low-cardinality tags to query offsets in Prometheus, every message with a new offset can spawn a new series. Use offsets only in logs or controlled traces.

### 9.2 Sampling and tracing a single event

Traces are normally sampled. You cannot guarantee a specific record has a span just because Observation is enabled, unless your sampling policy captures that trace.

When you need to investigate an exact event ID, maintain structured logs with event ID, topic, partition, and offset, and use trace/span IDs to correlate when a trace exists. `ObservationConvention` only standardizes context tags; it is not a durable audit system.

## 10. KafkaTemplateObservationConvention

The producer side has its own specialized interface **`KafkaTemplateObservationConvention`**, with context **`KafkaRecordSenderContext`**.

Safe customization mirrors the listener approach:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;

import org.springframework.kafka.support.micrometer.KafkaRecordSenderContext;
import org.springframework.kafka.support.micrometer.KafkaTemplateObservation;

public class OrdersTemplateObservationConvention
    extends KafkaTemplateObservation.DefaultKafkaTemplateObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(
            KafkaRecordSenderContext context) {

        return super.getLowCardinalityKeyValues(context)
            .and(KeyValue.of("app.domain", "orders"))
            .and(KeyValue.of("app.pipeline", "publication"));
    }
}
~~~

If a producer sends to multiple topics, you can use `context.getDestination()` or `context.getRecord().topic()` on supported versions to select a whitelisted route category.

### 10.1 Configuring KafkaTemplate

~~~java
@Bean
KafkaTemplate<String, OrderConfirmed> orderKafkaTemplate(
        ProducerFactory<String, OrderConfirmed> producerFactory,
        OrdersTemplateObservationConvention convention) {

    KafkaTemplate<String, OrderConfirmed> template =
        new KafkaTemplate<>(producerFactory);

    template.setObservationEnabled(true);
    template.setObservationConvention(convention);

    return template;
}
~~~

With Spring Boot auto-configuration, a `KafkaTemplate` bean may already exist. Do not create a second template solely for observability if doing so drops your transactional `ProducerFactory`, producer listeners, security settings, or serializers.

### 10.2 Template bean name vs. consumer listener ID

The producer context can expose **`getBeanName()`**, whereas the consumer context exposes **`getListenerId()`**. These are distinct identifiers.

Example:

~~~text
Producer KafkaTemplate bean: orderKafkaTemplate
Destination topic: orders.created

Consumer @KafkaListener id: orders-projection
Source topic: orders.created
Consumer group: orders-projection-prod
~~~

`ObservationConvention` can retain these details in semantic tags to distinguish send and receive spans. Do not set the same `app.role` tag value `"consumer"` on both template and listener if you want dashboards to distinguish processing direction.

## 11. End-to-end tracing across Kafka

A producer service sends an event; a consumer service receives it. To achieve continuous tracing across both services, **trace context** must be propagated via Kafka record headers and extracted at the consumer.

~~~mermaid
sequenceDiagram
    participant A as checkout-api
    participant P as KafkaTemplate
    participant K as Kafka broker
    participant C as orders listener
    participant T as Tracing backend
    A->>P: send OrderCreated
    P->>K: ProducerRecord + trace headers
    K->>C: ConsumerRecord + trace headers
    C->>T: Receiver span / child work
    P->>T: Sender span
~~~

In Spring Kafka with Micrometer Observation support:

- Enable Observation on `KafkaTemplate` to create sender observations.
- Enable Observation on listener containers to create receiver observations.
- Configure `ObservationRegistry`, tracing bridge, propagators, and exporter properly.
- Ensure headers are not stripped by producers/interceptors during publish.
- For non-Spring producers/consumers, ensure a compatible propagation format.

**`ObservationConvention` does not install a tracer or exporter**, nor does it write trace headers if the Observation/Tracing infrastructure is not functioning.

### 11.1 Names and tags are not trace propagation

A custom convention that simply adds `app.domain=orders` will not automatically make consumer traces children of producer spans.

Trace continuity requires:

1. Sender context capable of injecting propagation headers.
2. Producer records actually carrying the headers.
3. Receiver context extracting the headers properly.
4. Configured tracer and `ObservationHandlers`.
5. A sampling policy that allows retaining data if you expect to see traces in the backend.

If traces break between producer and consumer, inspect the propagation path before modifying the convention.

### 11.2 Tracing does not replace exactly-once semantics

A trace can show a record processed multiple times after a rollback or rebalance. That is an observability signal, not a deduplication mechanism.

Kafka EOS still requires transactional producers, listener container transactions, offsets-in-transaction, and `read_committed` downstream consumers where appropriate. Do not attach a trace ID and treat it as a business event idempotency key.

### 11.3 Trace headers also require security

Trace headers normally carry correlation identifiers, not full payloads. Still, do not expand propagation by stuffing JWTs, emails, session secrets, or personal data into baggage.

Baggage can propagate across many services and Kafka topics; every field needs justification, size bounds, and proper data classification.

## 12. Default semantic tags in Spring Kafka

According to modern Spring Kafka Micrometer Observation documentation, listener and template observations use distinct semantic naming:

~~~text
spring.kafka.listener
spring.kafka.template
~~~

Examples of documented semantic attributes:

| Group | Example tag | Meaning |
|---|---|---|
| Listener | `messaging.system` | Messaging system, e.g., Kafka |
| Listener | `messaging.operation` | Receive/process operation |
| Listener | `messaging.source.name` | Source topic |
| Listener | `messaging.kafka.consumer.group` | Consumer group |
| Listener | `spring.kafka.listener.id` | Listener/container identity |
| Producer | `messaging.destination.name` | Destination topic |
| Producer | `spring.kafka.template.name` | `KafkaTemplate` bean name |
| Producer | `messaging.operation` | Send/publish operation |
| Kafka metadata | `messaging.kafka.source.partition` | Partition metadata |
| Kafka metadata | `messaging.kafka.message.offset` | Kafka offset metadata |

The exact set of low/high-cardinality keys and names can change across Spring Kafka 3.0, 3.3, 4.x, and Micrometer semantic convention versions. Do not build long-lived dashboards based solely on a blog post from a mismatched version.

### 12.1 Preserving default tags when adding application tags

If adding `app.domain` drops `messaging.system` or `listener.id`, existing dashboards may stop grouping properly.

Extending default conventions and calling `super` is the straightforward way to preserve default semantic tags. If you want to redesign the semantic schema more deeply, you must:

- Design the versioned schema.
- List affected metrics/traces.
- Audit all dashboards/alerts.
- Test on canary.
- Prepare a rollback plan.

### 12.2 Contextual name vs. metric name

Contextual name is the display name of a specific observation in a trace:

~~~text
orders.created receive
orders.projected publish
~~~

Stable metric names are:

~~~text
spring.kafka.listener
spring.kafka.template
~~~

Changing the contextual name can improve readability in the trace UI; changing the metric name can break existing queries. Never embed order IDs or offsets into a metric name.

## 13. Custom contextual name

When you want spans readable by topic:

~~~java
public class OrdersListenerObservationConvention
    extends KafkaListenerObservation.DefaultKafkaListenerObservationConvention {

    @Override
    public String getContextualName(KafkaRecordReceiverContext context) {
        return context.getSource() + " receive";
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(
            KafkaRecordReceiverContext context) {

        return super.getLowCardinalityKeyValues(context)
            .and(KeyValue.of("app.domain", "orders"));
    }
}
~~~

If a listener subscribes to thousands of dynamically created topics, contextual names can take on many values. While not identical to high-cardinality metric labels, this still affects trace analysis and search.

Prefer finite topic naming conventions whenever possible. Never build contextual names from `eventId`, raw message keys, or PII.

### 13.1 Do not change getName() arbitrarily

Overriding `getName()` to change `spring.kafka.listener` into a custom per-domain name can fragment metrics and traces.

Do so only with a clear semantic metric schema plan, since dashboards may depend on the standard name. When merely adding app-specific metadata, **keep the default `getName()`** and add low-cardinality `KeyValues`.

## 14. Dynamic key-values from headers: whitelist, never raw values

Suppose a producer supplies an `event-type` header with valid values:

~~~text
OrderCreated
OrderConfirmed
OrderCancelled
~~~

If you want to group by `app.event.type` in metrics, you must avoid accepting arbitrary values from producers.

Safe workflow:

1. Read the header according to a standardized contract.
2. Enforce a maximum byte size.
3. Decode with the right charset.
4. Map onto an enum / allowed set.
5. If the header is null, malformed, or outside the whitelist, map to `other`.
6. Never throw exceptions from the convention.
7. Never place raw headers into low-cardinality tags.
8. Never log raw headers if they might contain sensitive data.

Example mapping function:

~~~java
private static String knownEventType(String raw) {

    if ("OrderCreated".equals(raw)) {
        return "created";
    }
    if ("OrderConfirmed".equals(raw)) {
        return "confirmed";
    }
    if ("OrderCancelled".equals(raw)) {
        return "cancelled";
    }
    return "other";
}
~~~

If a header carries an event UUID, never turn the raw UUID into a low-cardinality label just to "make individual events easy to look up."

## 15. ObservationConvention vs. other extension points

To avoid placing logic in the wrong layer, distinguish:

| Extension point | Purpose | When to use |
|---|---|---|
| `ObservationConvention` | Name and low/high `KeyValues` from context | Standardize metrics/tracing semantic tags |
| `ObservationRegistry` | Registry managing observations/handlers | Connect metrics/tracing lifecycle |
| `ObservationHandler` | Handle observation start/stop/error | Record metrics or create tracing spans |
| `ObservationFilter` | Modify observation context by policy | Adjust tags broadly at the registry layer |
| `ObservationPredicate` | Decide whether an observation is recorded | Reduce instrumentation for unneeded operations |
| Micrometer `MeterFilter` | Deny/transform meters/tags | Control metrics cardinality |
| Spring Kafka `RecordFilterStrategy` | Filter `ConsumerRecord` before listener | Skip certain business records |
| Kafka `ProducerInterceptor` / `ConsumerInterceptor` | Intercept record flow in Kafka client | Intentional metadata/serialization logic |
| Spring Kafka `CommonErrorHandler` | Retry/recover errors | Reliability when record processing fails |

`ObservationConvention` **should never** be where you:

- Skip invalid records.
- Commit offsets.
- Publish to a DLT.
- Control pause/resume.
- Call external services to enrich payloads.
- Decide Kafka transaction commits.

Those actions belong to other layers with different semantics.

### 15.1 Convention vs. business validation

If an `OrderCreated` event has a negative amount, the convention must not throw `InvalidOrderException` just to attach `valid=false`. Validation belongs in the schema/business layer.

A convention may add `app.event.type=created` when permitted, but must never become a data-processing step with side effects.

## 16. Impact on latency and resources

`ObservationConvention` runs on the Kafka record processing path. A slow convention increases listener overhead.

Operations that are safe to do:

- Read topic/listener ID from context.
- Map values onto an enum / finite set.
- Return small `KeyValues`.
- Reuse constant `KeyValues` where possible.
- Avoid heavy regexes / repeated JSON parsing per record.
- Avoid network and disk I/O.

Operations to avoid:

- Querying PostgreSQL for the domain.
- Calling a feature-flag server on every record.
- Serializing the entire Kafka payload into a tag.
- Reading configuration files per invocation.
- Emitting `INFO` logs for every `KeyValue`.
- Allocating megabyte strings from raw records.

### 16.1 Errors in a convention can disrupt the business flow

A convention does not run in an isolated process separate from the listener. Throwing an exception on the thread instrumenting a Kafka operation can affect control flow, logging, errors, or record processing depending on the implementation/version.

Therefore, a custom convention needs:

- Null safety.
- Whitelisted values.
- Zero reliance on external systems.
- No parsing of untrusted payloads unless strictly required.
- No exposure of secrets.
- Unit tests for edge-case inputs.

Observability must never become the cause of a stalled consumer or a retry storm.

## 17. Micrometer Observation and batch listeners

Batch observation behavior **varies by version**.

In Spring Kafka 3.x documentation, Micrometer Observation was described as **not supporting batch listeners**, with legacy listener timers used instead in batch mode.

In newer Spring Kafka documentation (e.g., the 4.2 line), batch-level observation is available when configured appropriately; properties like **`recordObservationsInBatch`** control whether observations are created for the entire batch or per record. Default semantics and support may change across releases.

**Do not apply a single rule across every version.**

### 17.1 Consequences for a custom listener convention

If batch listeners do not use Observation in your running Spring Kafka version, a custom `KafkaListenerObservationConvention` may never be called for batch invocations. In that case:

- Legacy listener timers may still be recorded.
- Custom convention tags will not appear.
- Per-record tracing context will not behave like a record listener.
- You cannot verify batch behavior with a test that only exercises a record listener.

### 17.2 On versions supporting batch observation

Check:

- Whether the observation context is record-level or batch-level.
- Whether default low-cardinality tags match meter names used by record listeners.
- Whether `ConsumerRecord` is available in the context.
- Whether one observation represents a batch or a record.
- Whether any added tags increase cardinality per batch/partition.

For throughput metrics, **batch invocation count does not equal the number of processed records**. If you need a business record rate, instrument batch size separately.

## 18. Kafka client metrics vs. ObservationConvention

Spring Kafka also supports Kafka client metrics via `MicrometerConsumerListener`/`MicrometerProducerListener` or corresponding binders. Those metrics describe:

- Records consumed rate.
- Fetch latency.
- Producer request latency.
- Bytes in/out.
- Retry or network statistics.
- Consumer coordinator/rebalance metrics.

Those client metrics **are not automatically produced simply by** configuring a `KafkaListenerObservationConvention`.

If you need consumer lag by topic/partition/group, use appropriate Kafka client/broker/admin metrics. Listener Observation helps explain why a listener is slow, but does not replace lag monitoring.

### 18.1 Complete reliability dashboard

A production dashboard should combine:

1. Listener observation duration and failures.
2. Kafka consumer lag and throughput.
3. Producer send success/failure.
4. Retry/DLT recovery metrics.
5. Kafka transaction commits/aborts if using EOS.
6. Business completion and duplicate detection.
7. End-to-end event age.
8. Trace sampling and propagation health.

Conventions merely standardize how the corresponding observations are classified.

## 19. ObservationRegistry and the tracing backend

Enabling `observationEnabled` alone is not enough to see traces in the backend. Ensure you have:

- Micrometer Observation on the classpath.
- An `ObservationRegistry` configured by Spring Boot/Micrometer.
- A handler that records metrics.
- A Micrometer Tracing bridge to a tracer implementation.
- An exporter/sender to the tracing backend.
- A consistent propagation format across services.
- Sampling configured to retain the needed traces.

An illustrative Spring Boot dependency setup:

~~~groovy
dependencies {
    implementation("org.springframework.kafka:spring-kafka")
    implementation("org.springframework.boot:spring-boot-starter-actuator")

    implementation("io.micrometer:micrometer-registry-prometheus")

    // Choose a tracing bridge/exporter compatible with the project's BOM.
    implementation("io.micrometer:micrometer-tracing-bridge-otel")
    implementation("io.opentelemetry:opentelemetry-exporter-otlp")
}
~~~

Actual dependencies depend on your Spring Boot/Spring Kafka version. Use Spring Boot dependency management / BOM to align Micrometer, the tracing bridge, and the OpenTelemetry SDK/exporter.

### 19.1 Metrics and traces can take separate paths

~~~mermaid
flowchart TD
    O["Kafka Observation"] --> R["ObservationRegistry"]
    R --> H1["Metrics handler"]
    R --> H2["Tracing handler"]
    H1 --> M["MeterRegistry / Prometheus"]
    H2 --> T["Tracer / OTLP collector"]
    M --> G["Metrics dashboard"]
    T --> Z["Trace UI"]
~~~

If metrics appear but traces do not, the convention may still be working fine; the issue may lie in the tracing handler, sampler, exporter, backend, or Kafka trace headers.

If traces appear but metrics do not, inspect `MeterRegistry`/metrics handlers and exporters. Do not tweak low-cardinality tags before identifying where the pipeline broke.

### 19.2 Trace sampling

If the sampler retains only 10% of traces, missing a trace for a particular message can be completely normal. Do not treat the absence of a trace as proof of message loss.

When you need a forensic audit for every event, use a durable audit store/log with appropriate policies rather than expecting the tracing backend to retain all records.

## 20. ObservationConvention and Kafka headers

Kafka headers are typically used to carry trace propagation context.

On the producer:

~~~text
HTTP trace context
  -> KafkaTemplate sender observation
  -> inject propagation metadata into ProducerRecord headers
  -> broker stores Kafka record and headers
~~~

On the consumer:

~~~text
Kafka ConsumerRecord headers
  -> listener receiver observation
  -> extract trace context
  -> span/child operations during record processing
~~~

Conventions primarily control **operation labels**; propagation is handled by sender/receiver contexts and tracing handlers.

### 20.1 Do not write traceparent with homemade code in a convention

If you want W3C Trace Context or a corresponding format, configure Micrometer Tracing and propagators properly.

Manually injecting a `traceparent` string into headers from a convention can:

- Produce an invalid format.
- Mismatch sampled flags.
- Overwrite existing producer metadata.
- Lack proper parent/span semantics.
- Break or corrupt cross-service traces.

`ObservationConvention` is not a Kafka `ProducerInterceptor` meant for mutating record headers.

### 20.2 When a consumer receives a record without trace headers

The system can still start a new receiver observation/span that is not linked to the original sender context. Do not reject messages merely for lacking trace context; tracing is an observability concern, not a mandatory business schema.

If upstream is a non-Spring producer, align on a propagation format to connect traces. If alignment is not possible, start a fresh trace on the consumer and include the event ID in structured logs for correlation.

## 21. Threading and Observation scope

Observation/tracing context can rely on thread-local scopes or context propagation mechanisms. For synchronous record listeners, the framework manages scope while invoking the listener.

However, if the listener offloads work to an executor:

~~~java
@KafkaListener(topics = "orders.created")
public void handle(OrderEvent event) {
    executor.submit(() -> service.process(event));
}
~~~

The child task may execute outside the original observation scope. It can lose trace context if not propagated properly, and the listener invocation can finish before business work completes.

For safe design:

- Never assume trace context crosses thread boundaries automatically.
- Use context propagation APIs / executor integrations appropriate for your Micrometer version.
- Keep Kafka acknowledgment and transaction semantics accurate.
- Measure business processing completion separately from listener method return.
- Avoid using `KafkaConsumer` from async threads.
- Test both trace parent-child relationships and offset commit behavior.

### 21.1 Reactor/coroutines take a different path

If the application uses Reactor, Kotlin coroutines, or reactive pipelines, scope propagation differs from plain imperative Java `ThreadLocal`. Use the integration suited to your runtime; do not copy a `ThreadLocal` wrapper across every environment.

`ObservationConvention` still defines tags/names, while scope propagation needs its own mechanism.

## 22. Unit testing a custom convention

You do not need a real Kafka broker to unit test the logic mapping context to `KeyValues`. You can instantiate `KafkaRecordReceiverContext` from a sample `ConsumerRecord` if the constructor matches your Spring Kafka version.

Conceptual example based on the Spring Kafka 3.3 API:

~~~java
@Test
void addsBoundedDomainTag() {

    ConsumerRecord<String, String> record =
        new ConsumerRecord<>(
            "orders.created",
            0,
            42L,
            "order-1001",
            "payload"
        );

    KafkaRecordReceiverContext context =
        new KafkaRecordReceiverContext(
            record,
            "orders-projection",
            "orders-client-0",
            "orders-projection-prod",
            () -> "test-kafka-cluster"
        );

    var convention = new OrdersListenerObservationConvention();

    KeyValues tags =
        convention.getLowCardinalityKeyValues(context);

    assertThat(tags).contains(
        KeyValue.of("app.domain", "orders")
    );
}
~~~

This example assumes JUnit/AssertJ and appropriate imports. Constructor parameters for `clientId`/`groupId` were added in newer Spring Kafka versions; if your project is on 3.0.x, use the constructor available in that version.

### 22.1 Unit test cases to include

- Valid topic within the whitelist.
- Topic outside the whitelist mapped to `other`.
- Null header.
- Oversized header.
- Header with invalid UTF-8 or unusual characters.
- Dynamic tags never use raw event IDs.
- Default `KeyValues` preserved when calling `super`.
- Convention never throws exceptions on malformed inputs.
- `getContextualName` remains stable for the same logical operation.

### 22.2 Do not assert only added tags

For example, tests should not only verify `app.domain=orders`, but also check that important default semantic keys were not accidentally dropped. This catches bugs when a developer overrides a method and forgets to call `super`.

However, default key names can change across framework versions. Tie tests to your chosen version rather than hardcoding a contract unsupported by that version.

## 23. Integration testing with real KafkaTemplate and listener containers

Unit testing a convention proves only the mapping function. It does not prove that `observationEnabled` and the convention are properly wired into the Kafka listener factory or `KafkaTemplate`.

Use Embedded Kafka or Testcontainers Kafka, a Spring `ApplicationContext`, and an inspectable `ObservationRegistry`.

### 23.1 Listener Observation test

1. Configure a listener container factory with `observationEnabled=true`.
2. Attach `OrdersListenerObservationConvention`.
3. Start the Kafka broker and listener.
4. Send a valid record to `orders.created`.
5. Wait for the listener to process the real record.
6. Read metrics/tracing observations recorded by registry handlers.
7. Assert `app.domain=orders` and `app.pipeline=projection`.
8. Assert operation name / contextual name matches policy.
9. Check listener ID suffixes when `concurrency > 1`.
10. Verify there is no double-counting from legacy timers.

### 23.2 KafkaTemplate Observation test

1. Create a `KafkaTemplate` with `observationEnabled` enabled.
2. Attach `OrdersTemplateObservationConvention`.
3. Send a `ProducerRecord`.
4. Wait for the send future and observation to complete per framework lifecycle.
5. Assert `app.pipeline=publication`.
6. Assert destination semantic tags are still present.
7. Inspect trace headers if tracing is enabled and applicable.
8. Test producer errors/aborts in separate tests.

### 23.3 End-to-end trace propagation test

1. Start a parent observation or HTTP trace on the producer.
2. Send a Kafka message with template observation enabled.
3. Have the consumer receive the message with listener observation enabled.
4. Capture spans using an in-memory test tracer or test exporter.
5. Verify trace relationships are linked when propagation/sampling allow.
6. Verify the consumer does not require a trace ID inside the payload.
7. Disable the tracing bridge in a test to confirm Kafka business processing does not break.

### 23.4 Testing with concurrent listeners

- Set `concurrency=3` on a topic with at least three partitions.
- Let child containers receive messages.
- Inspect listener identity tags generated at runtime.
- Ensure custom tags never alter consumer assignment or group IDs.
- Verify timer/tracing cardinality does not grow with event IDs.
- Verify spans are not lost during consumer retries or group rebalances.

### 23.5 Testing observationEnabled migration

If previously using `micrometerEnabled`:

- Record meter names/tags from the legacy system.
- Enable Observation on a canary.
- Compare emitted data schemas.
- Verify Prometheus queries/alerts still work.
- Verify no duplicate metrics are recorded.
- Verify batch behavior for your Spring Kafka version.
- Ensure trace context propagation works properly.

## 24. When metrics exist but custom tags are missing

Runbook:

1. Identify which `containerFactory` the `@KafkaListener` uses.
2. Check `factory.getContainerProperties().isObservationEnabled()` or the effective property.
3. Confirm `setObservationConvention` was called on the **right** `ContainerProperties`.
4. For producers, check which `KafkaTemplate` bean is actually used.
5. Confirm the convention bean is created by Spring and not overwritten by another customizer.
6. Verify your Spring Kafka version provides the corresponding API.
7. Confirm Observations are actually created: the listener receives records and the template sends messages.
8. Check `MeterRegistry`/`ObservationRegistry`, handlers, and backend.
9. Inspect actual `KeyValues` and metric tags; do not guess tag names.
10. For batch listeners, verify batch Observation support for your version.
11. If custom `getLowCardinalityKeyValues` returns empty or omits `super`, fix the convention.
12. Check whether `MeterFilter`/`ObservationFilter` drops or renames tags.

**Do not change Kafka group IDs or reset offsets** to fix missing tags. This is an instrumentation/wiring issue, independent of Kafka committed offsets.

## 25. When traces break between producer and consumer

If you see a producer span, but the consumer span is not a child / not in the same trace:

1. Confirm producer `KafkaTemplate.observationEnabled=true`.
2. Confirm consumer `ContainerProperties.observationEnabled=true`.
3. Check the tracing bridge and `ObservationHandlers`.
4. Check the propagation format supported by both services.
5. Inspect Kafka record headers in an appropriate test environment.
6. Confirm serializers/interceptors do not strip headers.
7. Confirm the consumer still has the same record headers when converters run.
8. Check the sampler; spans may be created yet not exported.
9. Check context propagation across async executors.
10. Check exporter/collector/network connectivity.
11. Check whether `ObservationConvention` incorrectly overrides `getName`/`getContextualName`, though do not treat that as the only cause.
12. Test with a minimal producer/consumer and in-memory tracing to isolate the fault.

Do not inject Kafka headers manually with ad-hoc code as a "quick fix" for tracing without understanding the propagation contract.

## 26. When the metrics backend is overloaded by cardinality

Symptoms:

- Prometheus series count spikes sharply after rolling out a new convention.
- Metrics collector memory/CPU rises.
- Scrape duration or remote write latency increases.
- Dashboard queries time out.
- `MeterRegistry` heap grows.
- Tracing backend receives too many distinct attributes.

Remediation steps:

1. Identify the convention that changed recently.
2. List tags and distinct value counts.
3. Find `eventId`, `orderId`, keys, offsets, client UUIDs, or exception messages mistakenly placed in low-cardinality tags.
4. Roll back the convention or replace values with a whitelisted category.
5. Check for duplicate metric schemas from combined Observation and Timer configuration.
6. Reduce histogram buckets or publish scope if needed.
7. Add appropriate `Metric`/`MeterFilter` guards.
8. Monitor series count after re-rollout.
9. Update the review checklist for all custom observation tags.

Do not treat cardinality explosion as merely a Prometheus issue; it starts with how `KeyValues` are produced on producers/consumers and also impacts application memory.

## 27. When a listener succeeds while the business operation fails

A listener might swallow an exception and return normally:

~~~java
@KafkaListener(topics = "orders.created")
public void handle(OrderCreated event) {

    try {
        projectionService.apply(event);
    }
    catch (Exception ex) {
        log.error("Projection failed", ex);
        // Do not rethrow.
    }
}
~~~

Observation may record an invocation success because the framework saw no exception. That does not prove the database committed or the Kafka offset committed accurately.

If errors require retry/rollback:

- Let exceptions propagate per policy.
- Use `DefaultErrorHandler` or an appropriate transactional rollback policy.
- Record business completion/recovery metrics separately.
- Do not modify a convention to "fake" a failure tag if the error was swallowed in business code.

A custom convention only reads context tags; it does not replace error classification or recovery semantics.

## 28. Difference between tags and span links

In Kafka, a consumer may receive multiple records, a record may be retried, or a batch may carry multiple parent trace contexts. Not every scenario is well represented by a simple parent-child relationship.

Micrometer Tracing, OpenTelemetry, and Spring Kafka offer span context/link mechanisms depending on version and mode. `ObservationConvention` is not the place to decide span link topology.

If using batch listeners, fan-in/fan-out, or asynchronous processing, consult the specific tracing integration documentation and test actual context propagation.

### 28.1 Do not treat event ID as a single trace identity

Event ID serves business identity/idempotency. Trace ID serves observability of one execution path. A single event may be processed multiple times, generating multiple traces or spans; that does not automatically mean duplicate business events.

Log both event ID and trace/span IDs when policy permits, while keeping them two independent concepts.

## 29. Version compatibility and API migration

Spring Kafka Observation support depends on version:

| Milestone or version line | Key point |
|---|---|
| Before 3.0 | Does not support the 3.x `KafkaTemplate`/Listener Observation API directly |
| From 3.0 | `KafkaTemplate` and listener containers support Micrometer Observation |
| From 3.0.6 | Custom conventions can read the record from observation context for dynamic tags |
| Spring Kafka 3.2+ | Adds receiver context accessors such as `groupId`/`clientId` |
| Spring Kafka 3.x | Batch observation support was limited; may fall back to legacy timers |
| Newer Spring Kafka 4.x | Batch observation capabilities and semantic conventions may change; check docs for the exact minor version |

Do not simply look at code samples from the latest release and copy them into a project on 3.0.x. Specifically verify:

- Packages and method signatures of contexts/conventions.
- `setObservationEnabled()` and `setObservationConvention()`.
- `ContextualName` behavior.
- Default low/high-cardinality keys.
- Batch mode.
- `ObservationRegistry` integration.
- Tracing propagation format.
- `KafkaAdmin` cluster ID lookup.

### 29.1 Kafka cluster ID in observations

Spring Kafka can use `KafkaAdmin` to retrieve the cluster ID and set `remoteServiceName` on sender/receiver observation contexts in supported versions. If the environment restricts `describeCluster` permissions, this metadata may be unavailable or require configuring a manual cluster ID per your version's API.

This can affect how the tracing backend displays the remote service, but must never stop the listener from processing business records simply because an enrichment field is unavailable.

Do not use cluster ID as a user-facing business identifier. It is infrastructure metadata.

## 30. ObservationConvention design checklist

**Choosing instrumentation**

- [ ] Decided whether to use legacy Micrometer timers or Micrometer Observation.
- [ ] `observationEnabled=true` set on the right `KafkaTemplate` or listener factory.
- [ ] `ObservationRegistry`, metrics/tracing handlers, and exporter are properly configured.
- [ ] Verified batch listener support for the Spring Kafka version.
- [ ] Preserved reliability configuration when adding instrumentation.

**Convention code**

- [ ] Using the right `KafkaListenerObservationConvention` or `KafkaTemplateObservationConvention`.
- [ ] Prefer extending the default convention and calling `super`.
- [ ] Keep operation name stable.
- [ ] `getContextualName` is concise and contains no per-record IDs.
- [ ] Low-cardinality tags have a finite value set.
- [ ] High-cardinality tags comply with privacy/security/retention policies.
- [ ] No large payload parsing or external system calls inside the convention.
- [ ] Null-safe fallbacks and whitelist mapping implemented.
- [ ] No duplication of framework semantic keys.
- [ ] Policies in place to prevent tag collisions and cardinality explosion.

**Tracing**

- [ ] `KafkaTemplate` sender observation works.
- [ ] Listener receiver observation works.
- [ ] Trace headers/propagators are compatible across services.
- [ ] Sampler and exporter are properly configured.
- [ ] Async work includes context propagation where needed.
- [ ] No PII/secrets placed in baggage or tags.
- [ ] Traces are not treated as durable business audits.

**Verification and operations**

- [ ] Unit tests cover `KeyValues`/contextual names.
- [ ] Integration tests use real `KafkaTemplate` and listeners.
- [ ] Concurrency and retry tests are in place.
- [ ] Tests cover missing/invalid/unknown header values.
- [ ] Batch flow tested if the project uses batching.
- [ ] Inspected actual metrics/traces before changing dashboards.
- [ ] Monitoring in place for series cardinality and tracing ingestion.
- [ ] Runbooks ready for missing tags, broken propagation, and high-cardinality incidents.

## 31. References

Official documentation to cross-check against your **project's Spring Kafka version**:

- Spring Kafka — Monitoring / Micrometer Observation: https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html
- Spring Kafka — Micrometer Observation Documentation: https://docs.spring.io/spring-kafka/reference/appendix/micrometer.html
- Spring Kafka API — KafkaListenerObservationConvention: https://docs.spring.io/spring-kafka/api/org/springframework/kafka/support/micrometer/KafkaListenerObservationConvention.html
- Spring Kafka API — KafkaTemplateObservationConvention: https://docs.spring.io/spring-kafka/api/org/springframework/kafka/support/micrometer/KafkaTemplateObservationConvention.html
- Spring Kafka API — KafkaRecordReceiverContext: https://docs.spring.io/spring-kafka/api/org/springframework/kafka/support/micrometer/KafkaRecordReceiverContext.html
- Spring Kafka API — KafkaRecordSenderContext: https://docs.spring.io/spring-kafka/api/org/springframework/kafka/support/micrometer/KafkaRecordSenderContext.html
- Micrometer Documentation — Observation: https://docs.micrometer.io/micrometer/reference/observation.html

## 32. Conclusion

**ObservationConvention** is where you standardize how a Kafka operation is **named and tagged with `KeyValues`** in Micrometer Observation. With Spring Kafka, use **`KafkaListenerObservationConvention`** for receivers and **`KafkaTemplateObservationConvention`** for senders; custom conventions should prefer extending default implementations, preserving built-in semantic tags, and adding only attributes with appropriate cardinality.

The vital distinction is: **low-cardinality tags aggregate metrics**, while **high-cardinality tags can provide trace detail yet still require privacy/cost policies**. `ObservationConvention` does not enable observation on its own, set up tracing propagation, perform Kafka error recovery, or replace business correctness metrics. A reliable production rollout attaches conventions to the right container/template, configures `ObservationRegistry` and a suitable tracing bridge, verifies version-specific APIs, monitors cardinality, and validates end-to-end with integration tests from producer to consumer.

