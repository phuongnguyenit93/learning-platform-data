# Dynamic tags from ConsumerRecord

## 1. Context and goals

A Spring Kafka application can process millions of records belonging to many different event groups. If there are only metrics for total messages, errors, and latency of a listener, operations teams struggle to tell why one event group is slower than the rest.

For example, the **`orders.events`** topic contains `OrderCreated`, `OrderConfirmed`, `OrderCancelled`, and `OrderRefundRequested`. The producer sends additional headers **`event-family`** and **`event-version`** so consumers can classify events. This information can be added to metrics or traces as **dynamic tags from `ConsumerRecord`**.

~~~text
Kafka topic: orders.events
          |
          v
ConsumerRecord
  topic=orders.events
  partition=3
  offset=4021
  headers:
    event-family=order
    event-version=v2
          |
          v
Spring Kafka listener container
          |
     +----+-------------------------+
     |                              |
Legacy Micrometer Timers      Micrometer Observation
     |                              |
micrometerTagsProvider        KafkaListenerObservationConvention
     |                              |
     v                              v
Dynamic metric labels         Low/high-cardinality key values
                                    |
                                    v
                             Metrics + tracing spans
~~~

A dynamic tag must solve a real observability need. **Not every field on `ConsumerRecord` is suitable as a metric label**. Keys, offsets, user IDs, or payloads can create a massive number of time series or leak sensitive data.

This lesson explains how to pick the right API for your Spring Kafka version, safely read metadata and headers, distinguish low/high cardinality, attach a custom observation convention, handle batch listeners, and test observability.

## 2. What does ConsumerRecord contain?

`KafkaConsumer.poll` receives messages as `ConsumerRecord` instances. When a listener receives the record directly:

~~~java
@KafkaListener(
    id = "orders-observer",
    topics = "orders.events",
    groupId = "orders-reader"
)
public void consume(ConsumerRecord<String, OrderEvent> record) {
    log.debug(
        "topic={} partition={} offset={}",
        record.topic(),
        record.partition(),
        record.offset()
    );

    orderService.process(record.value());
}
~~~

Key fields:

| Attribute | API | Assessment for tagging |
|---|---|---|
| Topic | `record.topic()` | Usually useful if topic count is bounded |
| Partition | `record.partition()` | Useful for traces; weigh metric cardinality |
| Offset | `record.offset()` | Changes continuously; never use as a metric label |
| Key | `record.key()` | May be an entity ID/PII; do not use raw as a label |
| Value | `record.value()` | Business payload; never attach directly to telemetry |
| Headers | `record.headers()` | May carry family/version or secrets; allowlist required |
| Timestamp | `record.timestamp()` | Used for latency calculations, not per-timestamp tags |
| Serialized sizes | `serializedKeySize()`, `serializedValueSize()` | Suitable for histograms, not label values |

A concrete record might look like:

~~~text
topic=orders.events
partition=3
offset=4021
key=order-913828
headers:
  event-family: order
  event-version: v2
  producer-service: checkout
  traceparent: 00-...-...-01
value=OrderConfirmed(...)
~~~

**`event-family=order`** can be a low-cardinality tag if the producer contract permits only a fixed set. **`order-913828`** or a trace ID changes per event and is unsuitable as a metric label.

## 3. Static tags vs. dynamic tags

**Static tags** are declared in listener or service configuration and hold the same value for every record:

~~~text
application=fulfillment-service
environment=prod
team=orders
~~~

**Dynamic tags** are computed from each `ConsumerRecord`:

~~~text
app.event.family=order
app.event.version=v2
~~~

If the next record has `event-family=payment`, the dynamic tag switches to `payment` while `environment` stays `prod`.

| Tag type | Example | Data source |
|---|---|---|
| Static | `application=fulfillment` | Deployment/configuration |
| Dynamic low-cardinality | `event.family=order` | Standardized header |
| Dynamic low-cardinality | `event.version=v2` | Whitelisted header |
| High-cardinality trace attribute | Approved opaque correlation ID | Message context |
| Should not be tagged | Raw payload, password, JWT, offset, customer ID | Sensitive or unbounded data |

Semantics must be consistent: a tag should keep a stable key name and value set across deployments, avoiding alternating between `v2` and `version-2` for the same concept.

## 4. Two monitoring mechanisms in Spring Kafka

Spring Kafka has two distinct instrumentation paths.

### 4.1. Legacy Micrometer Timers

Listener containers can create Micrometer timers when Micrometer and a `MeterRegistry` are configured. You can add:

- **`micrometerTags`**: fixed tags.
- **`micrometerTagsProvider`**: function reading `ConsumerRecord` to return dynamic tags.

Spring Kafka added **`micrometerTagsProvider`** starting in versions **2.9.8 / 3.0.6**.

API documentation clearly states the provider applies only to **record listeners**, is ignored for **batch listeners**, and **does not apply when Observation is enabled**.

### 4.2. Micrometer Observation

Starting in Spring Kafka **3.0**, the framework supports Micrometer Observation for `KafkaTemplate` and listener containers. For record listeners, Observation can produce timers and tracing spans depending on the handlers in `ObservationRegistry`.

Main components:

~~~text
KafkaListenerObservationConvention
KafkaRecordReceiverContext
KafkaListenerObservation.DefaultKafkaListenerObservationConvention
~~~

Starting in Spring Kafka **3.0.6**, the receiver context exposes **`getRecord()`** to retrieve the `ConsumerRecord`, letting custom conventions inspect headers and metadata per message.

### 4.3. Choosing the right mechanism

| Scenario | Recommended API |
|---|---|
| Legacy Micrometer Timer, Observation off | `setMicrometerTagsProvider` |
| Listener with `observationEnabled=true` | `KafkaListenerObservationConvention` |
| Observed Kafka producer | `KafkaTemplateObservationConvention` |
| Only static tags on legacy Timer | `setMicrometerTags` |
| Want to add attributes to an active span | Observation API within a valid scope |
| Batch listener needing per-record tags | Check version and batch observation mode |

**Do not configure `micrometerTagsProvider` and expect it to populate tags on tracing spans** if the application has already moved to Observation.

## 5. Option A: micrometerTagsProvider

Example for a record listener using legacy timers:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        legacyOrdersFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);

    var properties = factory.getContainerProperties();

    properties.setMicrometerEnabled(true);

    properties.setMicrometerTags(Map.of(
        "application", "fulfillment-service"
    ));

    properties.setMicrometerTagsProvider(record -> Map.of(
        "app.event.family", RecordTags.family(record),
        "app.event.version", RecordTags.version(record)
    ));

    return factory;
}
~~~

The **`setMicrometerTagsProvider`** function accepts a `ConsumerRecord` and returns **`Map<String,String>`**. When metrics are created, dynamic tags are combined with static tags according to framework behavior.

Define **`RecordTags`** so values are normalized, bounded, never throw exceptions on malformed headers, and never expose payloads.

### 5.1. Limits to remember

- The provider works for **record listeners**, not batch listeners.
- When **`observationEnabled=true`**, the provider is not the mechanism used for tagging.
- The function can run frequently on the hot path, so do not make HTTP/DB calls inside it.
- Return only low-cardinality values to prevent metric series explosion.
- With multiple factories, only listeners using the configured factory receive those tags.

## 6. Reading Kafka headers safely

Kafka headers store values as **`byte[]`**, which are not always valid strings. Headers can be missing, abnormally long, or hold out-of-contract values.

Example helper:

~~~java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;

public final class RecordTags {

    private RecordTags() {
    }

    private static String headerValue(
            ConsumerRecord<?, ?> record,
            String name) {

        Header header = record.headers().lastHeader(name);

        if (header == null || header.value() == null) {
            return "missing";
        }

        byte[] bytes = header.value();

        if (bytes.length == 0 || bytes.length > 64) {
            return "invalid";
        }

        return new String(bytes, StandardCharsets.UTF_8);
    }

    public static String family(ConsumerRecord<?, ?> record) {
        return switch (headerValue(record, "event-family")) {
            case "order" -> "order";
            case "payment" -> "payment";
            case "inventory" -> "inventory";
            default -> "other";
        };
    }

    public static String version(ConsumerRecord<?, ?> record) {
        return switch (headerValue(record, "event-version")) {
            case "v1" -> "v1";
            case "v2" -> "v2";
            case "v3" -> "v3";
            default -> "other";
        };
    }
}
~~~

With this design, even if a producer sends `event-family=order-913828`, it only produces **`other`**, never creating a new metric label per event.

If header formats require different normalization, adjust the helper against a **clear schema contract**. Do not guess from untrusted data.

### 6.1. Multiple headers with the same name

Kafka permits multiple headers with the same key. **`lastHeader(name)`** returns the last header matching that name. The application must define clear producer/gateway rules: are duplicate headers allowed, is the last header trusted, and when is metadata treated as invalid?

If the contract allows only one value, check for duplicates and return **`other`** when multiple headers share the same name instead of picking an arbitrary one.

### 6.2. Do not use exception headers as tags

Spring Kafka's `ErrorHandlingDeserializer` can attach serialized exception headers. Those are not ordinary UTF-8 messages and may hold sensitive raw bytes. Never use error contents or serialized exceptions directly as metric labels.

## 7. Low cardinality and high cardinality

**Low cardinality** means a small, stable, predictable set of values:

~~~text
app.event.family:
  order
  payment
  inventory
  other

app.event.version:
  v1
  v2
  v3
  other
~~~

**High cardinality** means a very large set of values or values that change per record:

~~~text
orderId=order-913828
correlationId=5d91...
offset=4021
customerId=928172
~~~

In time-series metrics backends, every new label set can create a new series. Tracing backends typically handle higher-cardinality span attributes better, but still remain subject to sampling, retention, privacy, and quotas.

| Data field | Metric label | Trace attribute |
|---|---|---|
| Allowlisted event family | Yes | Yes |
| Finite schema version | Yes | Yes |
| Topic with bounded set | Possibly | Yes |
| Partition | Weigh budget | Usually useful |
| Offset | No | Possibly, when needed for debugging |
| Approved opaque correlation ID | No | Possibly |
| Order ID, customer ID | No | Requires privacy approval |
| Email, phone, JWT, password | No | No |
| Raw JSON payload | No | No |

**High-cardinality does not automatically mean data is permitted in traces.** Traces can be stored long-term, accessed by many teams, and exported to external platforms.

## 8. Cardinality multiplies rather than adds

Suppose a metric has:

~~~text
service:       5 values
topic:         8 values
event.family:  4 values
event.version: 4 values
result:        2 values
~~~

Total theoretical combinations:

~~~text
5 x 8 x 4 x 4 x 2 = 1280 time series
~~~

Adding **`customer.id`** with 100,000 values increases combinations by orders of magnitude. That is why putting `record.key()` into metrics is so dangerous.

Example not to deploy:

~~~java
properties.setMicrometerTagsProvider(record -> Map.of(
    "order.id", String.valueOf(record.key())
));
~~~

Although filtering by a single order looks convenient, it makes series count grow roughly with order volume.

**Alternative:** use `event.family` or a normalized business class such as `priority=standard|express|other`.

## 9. Option B: KafkaListenerObservationConvention

When **Micrometer Observation** is enabled, dynamic tags are produced through a custom **`KafkaListenerObservationConvention`**.

Receiver context class:

~~~java
org.springframework.kafka.support.micrometer.KafkaRecordReceiverContext
~~~

This context provides **`getRecord()`**, returning the corresponding `ConsumerRecord` in supported versions.

Prefer extending the default convention instead of replacing all default tags. Built-in tags describing messaging system, topic, listener, and consumer group are vital for dashboards and tracing semantic conventions.

### 9.1. Custom convention example

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.support.micrometer.KafkaListenerObservation;
import org.springframework.kafka.support.micrometer.KafkaRecordReceiverContext;

public final class OrderListenerObservationConvention
        extends KafkaListenerObservation
            .DefaultKafkaListenerObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(
            KafkaRecordReceiverContext context) {

        ConsumerRecord<?, ?> record = context.getRecord();

        return super.getLowCardinalityKeyValues(context)
            .and(KeyValue.of(
                "app.event.family",
                RecordTags.family(record)
            ))
            .and(KeyValue.of(
                "app.event.version",
                RecordTags.version(record)
            ));
    }
}
~~~

This Java code targets Spring Kafka versions supporting `getRecord()` on `KafkaRecordReceiverContext`—namely Spring Kafka 3.0.6 and later in matching releases.

**Calling `super`** preserves the low-cardinality tags defined by the framework. Returning only application `KeyValues` can accidentally strip `messaging.*` and `spring.kafka.listener.id`.

### 9.2. Attaching the convention to the container

~~~java
import io.micrometer.observation.ObservationRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        observedOrdersFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory,
                ObservationRegistry observationRegistry) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);

    var properties = factory.getContainerProperties();

    properties.setObservationEnabled(true);
    properties.setObservationRegistry(observationRegistry);
    properties.setObservationConvention(
        new OrderListenerObservationConvention()
    );

    return factory;
}
~~~

**Version note:** the **`setObservationRegistry`** setter appeared in newer Spring Kafka lines such as 3.3.1+. On 3.0.x versions, the API for wiring the registry may differ. Consult the Javadoc for your exact version.

Listener:

~~~java
@KafkaListener(
    id = "orders-observer",
    topics = "orders.events",
    groupId = "orders-reader",
    containerFactory = "observedOrdersFactory"
)
public void consume(ConsumerRecord<String, OrderEvent> record) {
    orderService.process(record.value());
}
~~~

You do not need to call the custom convention manually inside the listener. The container creates the observation context and invokes the convention within the instrumentation pipeline.

## 10. ObservationRegistry and tracing handlers

**`ObservationRegistry`** coordinates Micrometer's `ObservationHandler` instances. Depending on configuration, an observation can:

- Produce a timer measuring listener duration.
- Record outcome/error metadata.
- Create a tracing span.
- Attach low/high-cardinality `KeyValues`.
- Restore trace context propagated from the producer.

~~~text
ConsumerRecord
      |
      v
KafkaRecordReceiverContext
      |
      v
KafkaListenerObservationConvention
      |
      +-- low-cardinality keys
      +-- high-cardinality keys
      |
      v
Observation
      |
      +-- Metrics handler --> Prometheus/Grafana
      |
      +-- Tracing handler --> Tempo/Jaeger/Zipkin
~~~

Enabling **`observationEnabled=true`** does not guarantee spans are exported. The application also needs a Micrometer Tracing bridge, propagation configuration, exporter, and backend.

If an `ObservationHandler` for a backend is missing, the convention may still build valid `KeyValues` while nothing shows up in your observability platform.

## 11. High-cardinality tracing tag: controlled example

If you need to link a message to a workflow and policy permits, you can read an **opaque correlation ID** and add it to high-cardinality attributes.

~~~java
@Override
public KeyValues getHighCardinalityKeyValues(
        KafkaRecordReceiverContext context) {

    String correlationId =
        TraceTags.approvedCorrelationId(context.getRecord());

    return super.getHighCardinalityKeyValues(context)
        .and(KeyValue.of(
            "app.correlation.id",
            correlationId
        ));
}
~~~

**`TraceTags.approvedCorrelationId`** is an application-written helper, not a Spring Kafka class. It must enforce length and format limits, accept only approved opaque IDs, and return a fallback **`none`** for anything else.

A workable policy:

~~~text
Accepted:
  32 hexadecimal characters, opaque random ID

Rejected:
  email
  phone number
  JWT
  URL containing query secrets
  arbitrary user input
  raw JSON
~~~

In many systems, tracing already carries a **trace ID** through the trace context, so adding a correlation ID is unnecessary unless an operational use case requires it.

Never put that same high-cardinality ID into **`getLowCardinalityKeyValues`**, or it could become a metric label.

## 12. Trace context propagation vs. dynamic tags

Kafka headers can carry **`traceparent`**, **`tracestate`**, or baggage.

~~~text
HTTP request
      |
      v
Order API span
      |
      v
KafkaTemplate producer
      |
      +-- inject trace context into headers
      |
      v
Kafka topic
      |
      v
Spring Kafka consumer
      |
      +-- extract trace context
      |
      v
Listener processing span
~~~

**Context propagation** links spans belonging to the same distributed transaction. **Dynamic tags** describe the message or operation for filtering, aggregation, or investigation.

Never put raw `traceparent` headers into metric labels; they carry per-request trace IDs and create extreme cardinality.

Baggage is likewise not a tag list to copy automatically. If baggage contains `userId` or `sessionId`, putting it into metrics/traces requires evaluating cardinality and data policies.

## 13. Tag names and default conventions

Depending on the Spring Kafka version, listener observations carry default tags such as:

- **`messaging.system`**
- **`messaging.operation`**
- **`messaging.source.name`**
- **`messaging.source.kind`**
- **`messaging.kafka.consumer.group`**
- **`spring.kafka.listener.id`**

Some span attributes also include partition, offset, client ID, or consumer ID.

Custom tags should use their own namespace:

~~~text
app.event.family
app.event.version
app.producer.role
app.processing.tier
~~~

Do not arbitrarily overwrite framework tags like `messaging.system` or `spring.kafka.listener.id`. Altering them can break dashboards, tracing conventions, or backend queries.

### 13.1. Tag keys should not be dynamic either

Avoid generating keys like:

~~~text
app.event.order-913828=true
app.event.order-913829=true
~~~

Tag keys must stay fixed, for example:

~~~text
Key:   app.event.family
Value: order | payment | inventory | other
~~~

Values are not the only source of cardinality: unbounded dynamic tag keys also hurt telemetry cost and schemas.

## 14. Dynamic tags from topic or partition

Topic is often a useful tag, though it is not always low cardinality.

~~~text
orders.events
payments.events
inventory.events
~~~

Three stable topics fit metrics well.

Conversely:

~~~text
orders.tenant-000001
orders.tenant-000002
...
orders.tenant-500000
~~~

If a system creates topics per tenant, using `record.topic()` directly as a custom label causes huge cardinality. Use a bounded **`topic.family`** instead.

Partitions are bounded per topic and usually fit traces or dedicated per-partition dashboards better. Kafka offsets increment per record, so never use offsets as standard metric labels.

If default observations already supply partition/offset span attributes, do not duplicate them.

## 15. Dynamic tags from record key

Record keys are often order IDs, payment IDs, user IDs, or routing keys. Using raw keys as metric labels increases cardinality and risks data leaks.

If the key contract has fixed prefixes representing routing classes, you can classify without keeping the ID:

~~~java
public static String routingClass(ConsumerRecord<?, ?> record) {
    Object key = record.key();

    if (!(key instanceof String text)) {
        return "unknown";
    }

    if (text.startsWith("priority-")) {
        return "priority";
    }

    if (text.startsWith("standard-")) {
        return "standard";
    }

    return "other";
}
~~~

This snippet works only when the prefix is a stable system contract. **Hashing an ID and using the hash as a tag does not solve cardinality**, because unique hashes still generate just as many distinct values.

## 16. Missing, malformed, or oversized headers

Older producers may not send `event-family`. Middleware may append duplicate headers. Tombstone records legitimately have `value=null`. A delegate deserializer may fail.

Tag extraction should include fallbacks:

| Situation | Handling |
|---|---|
| Header absent | Return `other` |
| Header `value=null` | Return `other` |
| Header exceeds byte limit | Return `other` |
| Header outside allowlist | Return `other` |
| Header within standard value set | Return normalized value |
| Tombstone `value=null` | Do not access `value.getClass()` |
| Deserialization failure | Do not attempt to parse raw payload in convention |
| Header contains token/PII | Do not log, do not emit as tag |

**Telemetry must never fail a listener over an invalid header.** Helpers should be pure data logic, non-blocking, network-free, avoid arbitrary Java object deserialization, and provide safe fallbacks.

### 16.1. Why not parse payloads for tags?

A convention can run on the hot path for every record. If it reparses JSON payloads, calls a schema registry, or queries a DB for customer tier, processing latency climbs and a monitoring bug can disrupt business logic.

Prefer Kafka metadata or headers with a clear contract. If business-dependent classification is needed, consider computing it at the producer and sending a standardized header.

## 17. Producer-side dynamic tags

On the `KafkaTemplate` side, the source data is **`ProducerRecord`**, not `ConsumerRecord`.

Spring Kafka provides:

~~~text
KafkaTemplateObservationConvention
KafkaRecordSenderContext
~~~

When a producer-side custom convention reads the record, it can inspect topic and headers to enrich producer observations.

On the legacy timer path, `KafkaTemplate` has **`setMicrometerTagsProvider(Function<ProducerRecord<?, ?>, Map<String,String>>)`** in supported versions. This provider likewise does not apply when Observation is enabled.

Do not configure `KafkaTemplateObservationConvention` expecting it to change consumer listener tags. Attach conventions to the right side of the pipeline.

## 18. Batch listeners: differences by Spring Kafka version

This is an important exception.

For **Spring Kafka 3.x**, legacy Micrometer Observation documentation notes that batch listeners are not supported the same way as record listeners and typically use Micrometer Timers. Likewise, **`micrometerTagsProvider`** applies only to record listeners, not batch listeners.

The **Spring Kafka 4.x** line expands batch observability. Documentation for **4.2** describes:

- When **`observationEnabled=true`** and **`recordObservationsInBatch=false`** (default), a single **batch-level observation** is created for the whole batch, using source metadata matching the first record.
- When **`recordObservationsInBatch=true`**, per-record observations can be created for records within the batch.
- Per-record observations in a batch do not necessarily propagate as the current observation inside the batch listener method.

Example for versions providing this API:

~~~java
factory.setBatchListener(true);

var properties = factory.getContainerProperties();

properties.setObservationEnabled(true);
properties.setRecordObservationsInBatch(true);
properties.setObservationConvention(
    new OrderListenerObservationConvention()
);
~~~

**Do not copy this batch API into Spring Kafka 3.x without checking your version.** Certain behaviors, meter names, and tags change across 4.x releases.

### 18.1. A representative batch tag does not represent every record

Example batch:

~~~text
record[0] event-family=order
record[1] event-family=payment
record[2] event-family=inventory
~~~

If batch-level observation reads metadata from the first record, `event-family=order` **does not mean the entire batch contains only order events**.

When accurate counts per family in mixed batches are needed, use per-record observations on supported versions or design separate metric aggregations with a cardinality budget.

## 19. Observability during consumer retries or replays

A record may be redelivered due to retries, rebalances, or restarts:

~~~text
P0 offset 900
  attempt 1 -> failure
  attempt 2 -> failure
  attempt 3 -> success
~~~

Depending on where instrumentation sits:

- **`listener.invocations`** may increment by three.
- **`processing.attempts`** may increment by three.
- **`processing.successes`** increments once for the successful attempt.
- **Unique business events** require separate idempotency/deduplication.

Dynamic tags only classify data; they do not define metric semantics or provide exactly-once processing.

A listener timer measuring listener invocations does not necessarily equal end-to-end latency from producer event timestamp to business completion.

## 20. Performance at high record volume

A topic consuming 20,000 records/second can generate huge volumes of observations, allocations, and tracing spans if every record is fully measured.

Necessary measures:

- Use low-cardinality metrics to aggregate total traffic.
- Apply **trace sampling** suited to throughput.
- Set a **cardinality budget** before adding new tags.
- Read headers without I/O and without reparsing payloads.
- Limit size and count of trace attributes.
- Do not log every event at `INFO` by default at high volume.
- Measure CPU/GC/latency before and after enabling Observation.
- Monitor metric series counts and tracing ingestion quotas.

Reducing tags while still exporting spans for every record may not control cost enough. Design sampling alongside metrics that must stay accurate.

## 21. Unit testing helpers with ConsumerRecord

A unit test without a Kafka broker can construct a `ConsumerRecord` directly.

~~~java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class RecordTagsTest {

    @Test
    void extractsAllowedFamily() {
        var record = new ConsumerRecord<String, String>(
            "orders.events", 2, 42L, "order-42", "payload"
        );

        record.headers().add(
            "event-family",
            "order".getBytes(StandardCharsets.UTF_8)
        );

        assertThat(RecordTags.family(record))
            .isEqualTo("order");
    }

    @Test
    void missingFamilyReturnsOther() {
        var record = new ConsumerRecord<String, String>(
            "orders.events", 0, 10L, "key", "payload"
        );

        assertThat(RecordTags.family(record))
            .isEqualTo("other");
    }

    @Test
    void unboundedValueDoesNotBecomeTag() {
        var record = new ConsumerRecord<String, String>(
            "orders.events", 0, 11L, "key", "payload"
        );

        record.headers().add(
            "event-family",
            "order-913828".getBytes(StandardCharsets.UTF_8)
        );

        assertThat(RecordTags.family(record))
            .isEqualTo("other");
    }
}
~~~

Add tests for null headers, oversized byte arrays, multiple headers with the same name, unknown versions, and tombstones. The goal is guaranteeing the helper returns a **finite set of values**, not just passing the happy path.

## 22. Integration testing Observation in practice

After unit testing the helper, write integration tests proving Spring Kafka actually invokes the convention.

1. Create a Spring context with an `ObservationRegistry` and suitable handlers / test registry.
2. Create a listener container with **`observationEnabled=true`**.
3. Attach `OrderListenerObservationConvention` to the right factory.
4. Send a record with `event-family=order` and `event-version=v2`.
5. Wait for `@KafkaListener` to process it.
6. Verify observation low-cardinality tags contain `app.event.family=order` and `app.event.version=v2`.
7. Confirm default `messaging.*` tags remain intact.
8. Send an unknown header and verify fallback to `other`.
9. Verify the metrics registry creates no labels from `record.key()`/`offset`.
10. If tracing is enabled, verify span export and trace context propagation per sampler.
11. If using batching, verify version and `recordObservationsInBatch` behavior.
12. Measure series count when sending many distinct event IDs.

Calling the custom convention directly in a unit test does not prove it is wired into the running listener factory.

### 22.1. Why test the registry?

`ObservationRegistry` can exist without having the expected export handler. Distinguish between:

- Convention builds the right `KeyValues`.
- Container actually enables Observation.
- `ObservationRegistry` is wired properly.
- Metrics handler creates meters.
- Tracing handler creates spans.
- Exporter sends data.
- Sampling policy retains spans for the test scenario.

An issue in the tracing exporter does not mean dynamic tag logic is wrong.

## 23. Meaningful dashboards and queries

Example dashboard tracking Order Fulfillment:

| Panel | Dimensions | Operational value |
|---|---|---|
| Listener processing latency | topic, event.family | Which event group is slow |
| Error rate | listener, event.family, result | Which event group fails most |
| Event version distribution | event.version | Whether producers are rolling out a new schema |
| Listener throughput | topic, listener | Which listener has rising load |
| Consumer lag | group, topic, partition | Which partition has backlog |
| Span detail | trace ID, source topic, partition | Investigate a specific execution |

Never add event IDs to metric labels just to click from a dashboard to a single order. For drill-down, use trace/log correlation on approved IDs with access-controlled queries.

### 23.1. Unknown/other tags are useful signals

If `app.event.version=other` spikes after a producer deployment, a new producer may be emitting a version not yet added to consumer monitoring's allowlist.

You can alert on the **`other`** ratio and check schema contracts; do not change code to accept arbitrary unknown strings as tags.

## 24. Security of dynamic tags

A Kafka header may contain:

- Authorization tokens.
- Tenant IDs or user IDs.
- Trace baggage.
- Request URLs containing query parameters.
- Debug payloads.
- Customer information.
- Data controlled by external producers.

Even when a tag is only attached to traces, data can still be exported to a backend and stored outside the application database.

Principles:

1. Use only approved fields.
2. Never put secrets, JWTs, emails, phone numbers, or payloads into tags.
3. Enforce value whitelists and length limits.
4. Never log full headers when extraction fails.
5. Enforce retention and access controls on the tracing backend.
6. Never extract sensitive data from headers just to debug a metric.
7. Perform compliance reviews before rolling out high-cardinality attributes.

Do not rely on hashing an email or customer ID and assuming the data is anonymized: hashes can still link identities and still cause high cardinality.

## 25. Common mistakes

**Using `micrometerTagsProvider` when `observationEnabled=true`.** The legacy provider does not apply, so dynamic tags do not appear as expected.

**Attaching `KafkaTemplateObservationConvention` to measure a consumer.** Producers and consumers use different observation contexts.

**Overriding `getLowCardinalityKeyValues` without calling `super`.** Important default tags can be lost.

**Using `record.key()` as a metric label.** Easily causes time-series explosion.

**Using raw `traceparent` as a metric tag.** It carries a trace ID that changes per request.

**Using raw headers without an allowlist.** Producers can emit unbounded values or sensitive data.

**Using offset as a metric label.** Values increase continuously with every record.

**Parsing payloads inside a convention.** Adds latency and introduces another failure point on the hot path.

**Assuming Observation always emits spans.** Tracing handlers, an exporter, and a sampler are still required.

**Assuming batch listeners always create per-record Observations.** Depends on version and mode.

**Assuming a batch-level `event-family` represents the whole batch.** A batch can contain mixed event groups.

**Assuming one listener invocation equals one unique business event.** Retries/replays can cause multiple invocations.

**Failing to check series count after deployment.** A high-cardinality tag can overload the observability backend.

## 26. Runbook when dynamic tags do not appear

1. Identify the Spring Kafka and Micrometer versions.
2. Determine whether the listener is record or batch mode.
3. Check **`observationEnabled`** on the container.
4. If Observation is enabled, inspect `KafkaListenerObservationConvention`.
5. If Observation is disabled, inspect `micrometerEnabled` and `micrometerTagsProvider`.
6. Confirm `@KafkaListener` uses the right `containerFactory`.
7. Check whether `context.getRecord()` has the expected headers.
8. Check whether the helper is returning default `other` due to invalid or missing headers.
9. Confirm `ObservationRegistry` and handlers are registered.
10. Check tracing sampling and exporter settings.
11. For batch listeners, verify mode and version-specific behavior.
12. Confirm default metric tags remain intact after the custom convention.
13. Check backend label filtering or schema changes.
14. Measure cardinality and ingestion cost.
15. Verify privacy/security policies for the tags.
16. Send a sample record with clear headers and inspect the resulting metric/span.
17. Document the actual configuration and verification steps in the upgrade runbook.

## 27. Combined example: Order Fulfillment

Order Fulfillment reads the **`orders.events`** topic. The producer writes headers:

~~~text
event-family: order
event-version: v2
producer-service: checkout
~~~

The consumer enables Observation with a custom convention. Upon receiving:

~~~text
Topic: orders.events
Partition: 3
Offset: 7821
Key: order-913828
Headers:
  event-family: order
  event-version: v2
~~~

Expected telemetry has low-cardinality tags:

~~~text
messaging.system=kafka
messaging.source.name=orders.events
spring.kafka.listener.id=orders-observer
app.event.family=order
app.event.version=v2
~~~

Actual framework tags depend on version. Metric tags **do not contain** `order-913828` or offset `7821`.

If the producer sends:

~~~text
event-family: order-913828
event-version: v999999
~~~

The helper returns:

~~~text
app.event.family=other
app.event.version=other
~~~

Series count does not grow per unknown event ID. Operations can still watch the `other` ratio rise to investigate producer metadata contracts.

## 28. Implementation checklist

- [ ] Identify Observation mode and Spring Kafka version.
- [ ] Use `micrometerTagsProvider` only for legacy record listener timers.
- [ ] Use `KafkaListenerObservationConvention` when Observation is enabled.
- [ ] Attach the convention to the right container factory.
- [ ] Configure `ObservationRegistry` and handlers for your stack.
- [ ] Read `ConsumerRecord` via `KafkaRecordReceiverContext.getRecord()`.
- [ ] Preserve default tags by extending the default convention and calling `super`.
- [ ] Use only allowlisted low-cardinality values.
- [ ] Never place keys, offsets, event IDs, payloads, or secrets into metric tags.
- [ ] Handle missing, malformed, duplicate, null, oversized headers, and tombstones.
- [ ] Distinguish trace context propagation from dynamic tags.
- [ ] Control high-cardinality trace attributes per privacy policy.
- [ ] Never perform I/O inside an observation convention.
- [ ] Understand batch observation behavior for your version.
- [ ] Test helpers, conventions, and the integration pipeline.
- [ ] Monitor time-series counts, span rates, and CPU overhead.
- [ ] Keep a runbook for tags disappearing after upgrades.

## 29. References

- Spring Kafka Reference — Monitoring: https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html
- Spring Kafka Reference — Micrometer Observation conventions: https://docs.spring.io/spring-kafka/reference/appendix/micrometer.html
- Spring Kafka JavaDoc — KafkaListenerObservationConvention: https://docs.spring.io/spring-kafka/api/org/springframework/kafka/support/micrometer/KafkaListenerObservationConvention.html
- Spring Kafka JavaDoc — KafkaRecordReceiverContext: https://docs.spring.io/spring-kafka/api/org/springframework/kafka/support/micrometer/KafkaRecordReceiverContext.html
- Spring Kafka 4.2 Reference — Batch Listener Observations: https://docs.spring.io/spring-kafka/reference/4.2/kafka/micrometer.html

When upgrading Spring Kafka 3.x to 4.x, check the API and behavior of the exact target version, especially regarding batch observation, default tags, and per-record observation support.

## 30. Key takeaways

**Dynamic tags from `ConsumerRecord`** let Spring Kafka classify listener metrics/traces using per-message metadata, such as event family or schema version. With **legacy Micrometer Timers**, use **`micrometerTagsProvider`** on record listeners. With **Micrometer Observation**, use **`KafkaListenerObservationConvention`** and read the record via **`KafkaRecordReceiverContext.getRecord()`**.

The core principles are **cardinality and security**: low-cardinality metric tags accept only bounded, standardized values; never use order IDs, Kafka offsets, raw payloads, or tokens as labels. High-cardinality trace attributes must also follow policies and quotas.

A resilient rollout keeps default convention tags, wires `ObservationRegistry`/handlers properly, checks batch mode for the exact version, and tests from helper to instrumentation pipeline. Good dynamic tags speed up diagnostics without turning observability into a new source of incidents.
