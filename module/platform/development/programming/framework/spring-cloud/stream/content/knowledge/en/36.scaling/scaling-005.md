# Registering Custom Converters, Header Mappers, and Partitioning Strategies

Spring Cloud Stream allows applications to process events through `Supplier`, `Function`, and `Consumer` without depending completely on how Kafka, RabbitMQ, or Pulsar transmit data. However, a large-scale system often needs to go beyond the defaults: partner data uses a proprietary format, certain headers must be normalized or stripped, and partition keys must be computed using business rules.

Three common extension points are **`MessageConverter`**, **header mappers**, and **partitioning strategies**. They intervene at different boundaries along the message path. Proper registration keeps services interoperating consistently; misconfiguration can cause deserialization failures, lost correlation IDs, skewed partitions, or broken event ordering.

This lesson builds an end-to-end order-event processing example, explains how to register beans and configure bindings, distinguishes Spring Cloud Stream's generic options from Kafka-, RabbitMQ-, and Pulsar-specific APIs, and shows how to test the entire path before scaling out across multiple instances.

## 1. Where Do the Three Extension Points Sit?

~~~mermaid
flowchart LR
    A["Broker: data and metadata"] --> B["Binder/Client"]
    B --> C["Header mapper"]
    B --> D["Message converter"]
    C --> E["Spring Message"]
    D --> E
    E --> F["Consumer / Function"]
    F --> G["Output Message or DTO"]
    G --> H["Message converter"]
    G --> I["Header mapper"]
    H --> J["Partition key + selector"]
    I --> J
    J --> K["Binder/Client → broker"]
~~~

This diagram is a conceptual model. Actual execution order and which steps are invoked also depend on the binder, function signature, native encoding/decoding, and framework version. The key takeaway is that each extension point owns a distinct responsibility:

| Extension point | Main input/output | Responsibility | Does not replace |
|---|---|---|---|
| `MessageConverter` | Wire payload ↔ Java object | Selects conversion by `contentType` and target type | Broker native serializer/Serde when native mode is enabled |
| Header mapper | Spring `MessageHeaders` ↔ broker headers/properties | Preserves, converts types, or filters metadata | Business payload conversion |
| `PartitionKeyExtractorStrategy` | Spring `Message<?>` → partition key | Extracts a stable business key | Partition selector |
| `PartitionSelectorStrategy` | Key + partition count → partition index | Picks target partition in the generic mechanism | Kafka native partitioner or Pulsar message router |

An event may pass through multiple extension points, but they should not share the same responsibility. For instance, do not cram a hashed partition key into `contentType` or use a payload converter to scrub tokens from headers.

## 2. Business Domain Example and Message Contract

Suppose the system receives order events from a partner using the text format `application/vnd.acme.order-line`:

~~~text
tenant-a|order-101|250000
tenant-a|order-102|125000
tenant-b|order-201|64000
~~~

The fields represent `tenantId`, `orderId`, and the amount in minor units (`totalMinor`). This format is intentionally simplified for illustration and only supports strings without `|`. A real-world system should use JSON, Avro, Protobuf, or a format with explicit escaping and schema rules for complex data.

Java object representing the event:

~~~java
public record OrderEvent(
        String tenantId,
        String orderId,
        long totalMinor) {
}
~~~

Business metadata is transmitted separately:

~~~text
event-id       = evt-001
correlation-id = checkout-7842
event-type     = OrderCreated
~~~

Implementation goals:

1. A converter reads/writes the order wire format.
2. A header mapper forwards only permitted metadata across the broker.
3. A partition extractor picks the same shard for all events of a given order.
4. A selector computes valid, stable, testable partitions.
5. Consumers receive the expected DTO and headers regardless of how many instances the app scales to.

## 3. Understanding `contentType` Before Creating a Converter

Spring Cloud Stream comes with built-in converters for JSON, byte arrays, and text. When a payload needs conversion, the framework combines the **target type** with the **content type** to select a converter.

The typical lookup order for content type is:

1. The `contentType` header already present on the `Message`.
2. The `spring.cloud.stream.bindings.<binding>.content-type` property.
3. The default value `application/json`.

Example:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrder
    stream:
      bindings:
        normalizeOrder-in-0:
          destination: orders.raw
          content-type: application/vnd.acme.order-line
        normalizeOrder-out-0:
          destination: orders.normalized
          content-type: application/vnd.acme.order-line
~~~

If a producer explicitly sends header `contentType=application/json`, the header value may take precedence over binding configuration. Therefore, when a converter is not invoked, check both actual headers and the function's declared types.

Function example:

~~~java
@Bean
Function<OrderEvent, OrderEvent> normalizeOrder() {
    return event -> new OrderEvent(
            event.tenantId().trim(),
            event.orderId().trim(),
            event.totalMinor());
}
~~~

If the input is already `OrderEvent` and the target type is also `OrderEvent`, the framework may skip conversion. If the function takes `Object`, the framework has too little information to determine a target type; declare concrete types in the contract whenever conversion is needed.

### Native Encoding/Decoding Changes the Path

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        normalizeOrder-out-0:
          producer:
            use-native-encoding: true
        normalizeOrder-in-0:
          consumer:
            use-native-decoding: true
~~~

When native mode is enabled, payload serialization/deserialization is performed by the broker client and its serializer/deserializer or schema. Do not expect a custom Spring Cloud Stream `MessageConverter` to still run on payloads handled in native mode. Kafka can use native `Serializer`/`Deserializer`, Kafka Streams uses `Serde`, and Pulsar has Pulsar schemas. Header mapping remains a separate concern and may require its own configuration.

## 4. Registering a Custom `MessageConverter`

Spring Cloud Stream automatically detects beans of type `org.springframework.messaging.converter.MessageConverter`. You can extend `AbstractMessageConverter` to advertise a MIME type and implement both conversion directions.

Example converter dedicated to `OrderEvent`:

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.converter.AbstractMessageConverter;
import org.springframework.messaging.converter.MessageConversionException;
import org.springframework.util.MimeType;

public final class OrderLineMessageConverter
        extends AbstractMessageConverter {

    public OrderLineMessageConverter() {
        super(new MimeType("application", "vnd.acme.order-line"));
    }

    @Override
    protected boolean supports(Class<?> clazz) {
        return OrderEvent.class.equals(clazz);
    }

    @Override
    protected Object convertFromInternal(
            Message<?> message, Class<?> targetClass, Object hint) {
        if (!(message.getPayload() instanceof byte[] bytes)) {
            throw new MessageConversionException(
                    message, "Order-line payload must be byte[]");
        }

        String line = new String(bytes, StandardCharsets.UTF_8);
        String[] fields = line.split("\\|", -1);
        if (fields.length != 3
                || fields[0].isBlank() || fields[1].isBlank()) {
            throw new MessageConversionException(
                    message, "Invalid order-line fields");
        }

        try {
            return new OrderEvent(
                    fields[0], fields[1], Long.parseLong(fields[2]));
        }
        catch (NumberFormatException ex) {
            throw new MessageConversionException(
                    message, "Invalid totalMinor", ex);
        }
    }

    @Override
    protected Object convertToInternal(
            Object payload, MessageHeaders headers, Object hint) {
        OrderEvent event = (OrderEvent) payload;
        if (event.tenantId().isBlank()
                || event.orderId().isBlank()
                || event.tenantId().contains("|")
                || event.orderId().contains("|")) {
            throw new IllegalArgumentException(
                    "Order identifiers cannot be blank or contain '|'");
        }

        String line = event.tenantId()
                + "|" + event.orderId()
                + "|" + event.totalMinor();
        return line.getBytes(StandardCharsets.UTF_8);
    }
}
~~~

Registering in the Spring context:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.converter.MessageConverter;

@Configuration(proxyBeanMethods = false)
class MessageConversionConfiguration {

    @Bean
    MessageConverter orderLineConverter() {
        return new OrderLineMessageConverter();
    }
}
~~~

`convertFromInternal` parses received `byte[]` into `OrderEvent`; `convertToInternal` returns `byte[]` to send to the broker. The converter accepts only the declared MIME type and supported target type.

**Controlled extensibility:** custom converters are prepended to Spring Cloud Stream's converter list, giving them higher precedence than built-in converters when handling a message. If `supports` or MIME matching is overly broad, the new converter can unintentionally intercept JSON/text for other functions. Use a dedicated MIME type, constrain the target class, and test bindings that do not use this converter as well.

This is an illustrative wire format for the lesson; production code needs size limits, schema validation, escaping rules, versioning, and error-handling policies for data arriving from untrusted systems.

## 5. Conversion Errors and Data Compatibility

A converter must do more than succeed on clean data. Define how to handle these cases:

| Scenario | Expected behavior |
|---|---|
| Content type mismatch | Converter declines; framework tries another matching converter or reports an error. |
| Missing required field | Report a conversion error with error type info; avoid logging full sensitive payloads. |
| Malformed amount | Report conversion error; apply retry/DLQ per binder and error handler. |
| Older wire format version | Convert compatibly or reject cleanly; do not guess missing data. |
| Oversized byte array | Reject before expensive decoding according to business limits. |
| Spoofed content type header | Verify data source and validate payload rather than blindly trusting headers. |

If an event has multiple versions, use a versioned `contentType`, a `schema-version` header, or an appropriate schema registry. When bumping versions, test new producers against old consumers according to your compatibility policy.

With Kafka Streams, an application converter does not replace `Serde` at repartition, state store, and changelog stages. If the topology needs custom native Serdes, configure `keySerde`/`valueSerde` per the Kafka Streams binder instead of expecting `MessageConverter` to handle every internal record.

## 6. Header Mappers Are a Separate Layer from Payload Converters

A Spring `Message<?>` consists of a payload and `MessageHeaders`. Brokers have their own header mechanisms:

| Broker | Metadata representation | Key considerations |
|---|---|---|
| Kafka | Header name and `byte[]` value | Mapper decides data types and which headers pass through; Kafka record key/partition/offset have distinct semantics. |
| RabbitMQ | AMQP properties and headers | Mapper converts Spring headers to AMQP properties and header tables; exchange/routing key/delivery tag are delivery metadata. |
| Pulsar | User properties and message metadata | User properties are usually Strings; metadata like message ID/key have separate semantics. |

Example constructing a message with business headers:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<OrderEvent> orderMessage(OrderEvent event) {
    return MessageBuilder.withPayload(event)
            .setHeader("event-id", "evt-101")
            .setHeader("correlation-id", "checkout-7842")
            .setHeader("event-type", "OrderCreated")
            .build();
}
~~~

`event-id` identifies an event; `correlation-id` links across services; `event-type` describes the contract type. Avoid variants like `Id` or `ID` as business headers if distinct names are possible: `id` and `timestamp` are special Spring Messaging headers that easily conflict with mappers.

The mapper is part of the interoperability contract. Allow only permitted headers, constrain types/sizes, and preserve tracing or schema headers when they genuinely must cross the broker. An incomplete mapper can drop headers even when the producer set them properly.

## 7. Registering a Kafka Header Mapper

The Kafka binder lets you specify a `KafkaHeaderMapper` bean name via property:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          header-mapper-bean-name: orderKafkaHeaderMapper
~~~

If no name is specified, the binder looks for a default `kafkaBinderHeaderMapper` bean of the matching type and otherwise uses the binder's default mapper. Simply creating a generic `KafkaHeaderMapper` bean in the context does not guarantee the binder picks the right bean if multiple beans exist in the project; give it an explicit name and configure the property above.

Minimal mapper example forwarding only three String headers. It illustrates bidirectional mapping and whitelist filtering:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;

import org.apache.kafka.common.header.Header;
import org.apache.kafka.common.header.Headers;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.support.KafkaHeaderMapper;
import org.springframework.messaging.MessageHeaders;

@Configuration(proxyBeanMethods = false)
class KafkaHeaderConfiguration {

    private static final List<String> ALLOWED =
            List.of("event-id", "correlation-id", "event-type");

    @Bean("orderKafkaHeaderMapper")
    KafkaHeaderMapper orderKafkaHeaderMapper() {
        return new KafkaHeaderMapper() {
            @Override
            public void fromHeaders(
                    MessageHeaders source, Headers target) {
                for (String name : ALLOWED) {
                    Object value = source.get(name);
                    if (value instanceof String text) {
                        target.add(name, text.getBytes(StandardCharsets.UTF_8));
                    }
                }
            }

            @Override
            public void toHeaders(
                    Headers source, Map<String, Object> target) {
                for (String name : ALLOWED) {
                    Header header = source.lastHeader(name);
                    if (header != null) {
                        target.put(name,
                                new String(header.value(),
                                        StandardCharsets.UTF_8));
                    }
                }
            }
        };
    }
}
~~~

**Example scope:** the mapper above intentionally omits `contentType`, `traceparent`, and other framework headers. It is only meant to demonstrate the flow of three String headers. In a real application, replacing the default mapper with such a minimalist implementation can break content conversion, tracing, or logic relying on other headers. Prefer configuring/customizing the default `BinderHeaderMapper` when possible, or compile a complete header allowlist and test against a real broker.

`spring.cloud.stream.kafka.binder.headerMapperBeanName` is scoped to the Kafka binder; it is not a generic Spring Cloud Stream option or a RabbitMQ/Pulsar setting.

### Trusted Packages and Header Types

JSON-based mappers can deserialize headers into Java objects. Never widen trusted packages to `*` for messages from untrusted sources. For IDs, correlation, and tracing, prefer `String` or simple primitives; for custom objects, allow only specific packages and verify serialization contracts on both producer and consumer.

In Kafka, `KafkaHeaders.KEY` is the record key and can be used for native partitioning. It is not the same as an arbitrary header named `partition-key`. Verify keys with a real Kafka producer/consumer rather than inferring the key from header maps alone.

## 8. RabbitMQ: Customizing AMQP Header Mapping

Spring Integration AMQP uses `DefaultAmqpHeaderMapper` to map between Spring headers and AMQP message properties. Properties like `contentType`, `correlationId`, `messageId`, routing key, and delivery metadata occupy dedicated slots; do not copy all native AMQP properties as arbitrary strings.

At the Spring Integration layer, the mapper can specify request/reply header names and filter patterns. Example configuration for an outbound AMQP adapter per application conventions:

~~~java
import org.springframework.integration.amqp.support.DefaultAmqpHeaderMapper;

DefaultAmqpHeaderMapper amqpOutboundMapper() {
    DefaultAmqpHeaderMapper mapper =
            DefaultAmqpHeaderMapper.outboundMapper();
    mapper.setRequestHeaderNames(
            "event-id", "correlation-id", "event-type");
    return mapper;
}
~~~

The snippet above constructs a mapper at the adapter level. **Simply registering this bean does not mean the Rabbit binder automatically picks it up and uses it**: the mapper must be wired into the right outbound endpoint/inbound adapter through a configuration hook or customizer supported by your binder version. Consult Spring Integration AMQP and Rabbit binder docs to find the insertion point. When you only need to pass standard String headers, the default mapper is often sufficient and needs no override.

Across multiple consumer groups, the Rabbit binder's routing keys and queue declarations have far greater impact on horizontal scaling. A header mapper does not create partitions or queues; Rabbit distribution requires dedicated partitioning and topology configuration.

## 9. Registering PulsarHeaderMapper

The Pulsar binder lets you provide a `PulsarHeaderMapper` bean to replace the default mapper. `JsonPulsarHeaderMapper` supports header filter patterns and trusted package lists:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.pulsar.support.header.JsonPulsarHeaderMapper;
import org.springframework.pulsar.support.header.PulsarHeaderMapper;

@Configuration(proxyBeanMethods = false)
class PulsarHeaderConfiguration {

    @Bean
    PulsarHeaderMapper customPulsarHeaderMapper() {
        return JsonPulsarHeaderMapper.builder()
                .inboundPatterns("!secret", "*")
                .outboundPatterns(
                        "!id", "!timestamp", "!secret", "*")
                .trustedPackages("com.acme.events")
                .build();
    }
}
~~~

Patterns support wildcards and `!` negations; **the first matching pattern wins**. Therefore `!secret` must appear before `*`. Keep `id` and `timestamp` excluded unless there is a specific reason to forward them. Never set `trustedPackages("*")` when consuming events from partners or external systems.

Pulsar user properties are distinct from internal metadata such as message ID, topic, key, or publish time. Do not assume customizing the header mapper changes the Pulsar producer's key routing mechanism. Inspect message keys, partitioned topics, and subscription types separately.

## 10. Generic Partitioning Mechanism in Spring Cloud Stream

Spring Cloud Stream splits partition selection into two steps:

1. `PartitionKeyExtractorStrategy` takes a `Message<?>` and returns a key.
2. `PartitionSelectorStrategy` takes the key and `partitionCount`, returning a partition index from `0` to `partitionCount - 1`.

For simple logic, you can use SpEL without writing a Java bean:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        normalizeOrder-out-0:
          destination: orders.normalized
          producer:
            partition-key-expression: payload.orderId
            partition-count: 12
~~~

If the rule requires normalization, composite keys, or sharding, registering dedicated strategy beans keeps logic in one unit-testable place. `partitionKeyExpression` and `partitionKeyExtractorName` are mutually exclusive. Likewise, `partitionSelectorExpression` and `partitionSelectorName` must not be used simultaneously on the same binding.

## 11. Registering `PartitionKeyExtractorStrategy` and `PartitionSelectorStrategy`

Suppose the application must preserve order per individual order, while independent orders of the same tenant may spread across partitions. A composite key `tenantId:orderId` is a sensible choice:

~~~java
import org.springframework.cloud.stream.binder.PartitionKeyExtractorStrategy;
import org.springframework.cloud.stream.binder.PartitionSelectorStrategy;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class OrderPartitionConfiguration {

    @Bean("tenantOrderExtractor")
    PartitionKeyExtractorStrategy tenantOrderExtractor() {
        return message -> {
            if (!(message.getPayload() instanceof OrderEvent event)) {
                throw new IllegalArgumentException(
                        "Expected OrderEvent payload");
            }
            if (event.tenantId().isBlank() || event.orderId().isBlank()) {
                throw new IllegalArgumentException(
                        "Partition key fields must not be blank");
            }
            return event.tenantId().trim() + ":" + event.orderId().trim();
        };
    }

    @Bean("stableSelector")
    PartitionSelectorStrategy stableSelector() {
        return (key, count) -> {
            if (count <= 0 || key == null) {
                throw new IllegalArgumentException(
                        "Partition count and key must be valid");
            }
            return Math.floorMod(key.hashCode(), count);
        };
    }
}
~~~

Configuration selecting both beans by name:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrder
    stream:
      bindings:
        normalizeOrder-in-0:
          destination: orders.raw
          content-type: application/vnd.acme.order-line
        normalizeOrder-out-0:
          destination: orders.normalized
          content-type: application/vnd.acme.order-line
          producer:
            partition-key-extractor-name: tenantOrderExtractor
            partition-selector-name: stableSelector
            partition-count: 12
~~~

The bean name in `@Bean("tenantOrderExtractor")` must match `partition-key-extractor-name`. Similarly, the selector name must match `partition-selector-name`. When multiple strategies share the same bean type, naming them per binding avoids picking the wrong bean or causing ambiguous bean errors.

The example selector simply normalizes `hashCode()` into a non-negative range. If the default hash suffices, there is no need to write a custom selector; create a custom bean only when there is a clear requirement. A key extractor should be **deterministic and side-effect-free**; do not read current time, random values, round-robin counters, or local state when events for the same entity must stay ordered.

### Distinguishing Extractor and Selector

Given key `tenant-a:order-101` and 12 partitions:

~~~text
Message<OrderEvent>
        |
        v
tenantOrderExtractor -> "tenant-a:order-101"
        |
        v
stableSelector(key, 12) -> a number from 0 to 11
        |
        v
Binder sends to the corresponding partition
~~~

If the extractor returns the wrong key, even a correct selector cannot preserve business ordering. If the extractor returns the right key but the selector is inconsistent across instances, the same key can land on different partitions.

## 12. When to Use SpEL vs. When to Use a Bean

| Requirement | Suitable approach | Example |
|---|---|---|
| Reading a simple field | `partitionKeyExpression` | `payload.orderId` |
| Reading a normalized header | `partitionKeyExpression` | `headers['partitionKey']` |
| Combining multiple fields with validation | `PartitionKeyExtractorStrategy` | `tenantId:orderId` |
| Splitting a hot tenant into shards | Extractor with deterministic sharding algorithm | `tenantId + '#' + shard` |
| Default hash is sufficient | Omit custom selector | Use default selector |
| Cross-producer hash compatibility | `PartitionSelectorStrategy` with specified algorithm | Standardized hash tested cross-language |
| Multiple distinct output bindings | Named beans per binding | `tenantOrderExtractor` and `accountExtractor` |

SpEL is concise and easy to configure, but hard to unit-test for complex branches. Java beans are clearer for validation, fallbacks, and hashing algorithms. Do not overuse custom selectors just because they can be replaced.

### Key Salting Example

A large tenant can be split across multiple shards when its orders are independent:

~~~java
String shardKey(OrderEvent event, int shards) {
    int shard = Math.floorMod(event.orderId().hashCode(), shards);
    return event.tenantId() + "#" + shard;
}
~~~

Salting **loses tenant-wide ordering**; it only preserves order for events that consistently map to the same shard. If two orders must update a single tenant-wide aggregate, design a two-stage aggregation step or keep the original key. Changing the shard count can also move an order to a new shard; plan migrations to preserve data and ordering.

## 13. Key Differences Among Kafka, RabbitMQ, and Pulsar

Partitioning capabilities are not identical across the three binders:

| Topic | Kafka | RabbitMQ | Pulsar |
|---|---|---|---|
| Native partitioning concept | Native topic partitions | Exchanges/queues; queues are not equivalent to Kafka partitions | Partitioned topics |
| Common keying approach | Kafka record key and native partitioner | Spring Cloud Stream partitioner + queue/routing conventions | Pulsar message key and routing mode |
| Scaling consumers | Consumer group distributes partitions among consumers | Multiple consumers on a queue or indexed queues | Subscription types and partitioned topics |
| Ordering guarantee | Within a single partition, in append order | Depends on topology, consumers, prefetch, and requeue | Depends on key, partition, and subscription type |
| Essential verification | Key → partition, offset, group assignment | Routing key → queue, consumer/instance index | Message key → partition, subscription, and ordering |

### Kafka: Prefer Native Keys When Appropriate

The Kafka producer picks a partition based on the record key when no explicit partition is set. The recommended configuration when preserving order by key is setting the record key with `KafkaHeaders.KEY`:

~~~java
Message<OrderEvent> output = MessageBuilder
        .withPayload(event)
        .setHeader(KafkaHeaders.KEY, event.orderId())
        .build();
~~~

Or configuring the Kafka binder producer:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          normalizeOrder-out-0:
            producer:
              message-key-expression: payload.orderId
~~~

In that case, you do not need to enable generic `partition-key-extractor-name` on the same binding. If using generic partitioning, Spring Cloud Stream computes the partition by hashing the key returned by the extractor; this algorithm **may differ** from Kafka's native partitioner, so the same key string may not map to the same partition as a plain Kafka producer.

Changing `partitionCount` or the actual partition count can remap keys; never change them silently while stateful or ordered data is live. On Kafka, Spring Cloud Stream's `partition-count` also serves as a hint when provisioning topics; do not assume changing this property automatically alters existing topics.

### RabbitMQ: Mind Both Producer and Consumer Sides

Generic partitioning lets Spring Cloud Stream route to queues/shards by partition index, while RabbitMQ consumers may need `partitioned` configured along with `instanceCount` and `instanceIndex`:

~~~yaml
spring:
  cloud:
    stream:
      instance-count: 4
      instance-index: 0
      bindings:
        consumeOrder-in-0:
          destination: orders.normalized
          group: order-worker
          consumer:
            partitioned: true
~~~

This example configures **one instance**, index `0`. Other instances must use distinct indices (`1`, `2`, `3`) when the deployment relies on instance-based partitioning. Instances sharing the same index will not receive load as intended. Inspect actual queue names, bindings, routing keys, and consumer assignments for your Rabbit binder version.

Adding consumers to the same queue does not mean messages are partitioned by key. If strict per-aggregate ordering is required, verify how messages are dispatched among consumers and review ACK/requeue policies.

### Pulsar: Keys and Subscription Types Are Two Layers

Pulsar has partitioned topics and its own message routing. With a `Key_Shared` subscription, messages with the same key are dispatched according to subscription semantics, allowing multiple keys to be processed in parallel. Producers must set stable keys and use key-based batching or disable batching if required by `Key_Shared` on your broker version.

A Spring Cloud Stream custom partition strategy does not automatically replace Pulsar's native router. If the application uses native encoding/schemas and Pulsar key routing, verify that keys are actually written onto messages and the partitioned topic has enough partitions; do not expect a generic Java `PartitionSelectorStrategy` to govern every Pulsar broker decision.

### Kafka Streams Binder: Use Its Dedicated API

Kafka Streams topologies use their own Serdes and task/partition model. If you need a custom outbound partitioner for the Kafka Streams binder, use a `StreamPartitioner` bean and the binder's `streamPartitionerBeanName` option, rather than assuming the message-channel Kafka binder's `PartitionSelectorStrategy` applies to the topology.

## 14. Processing Order, Key Stability, and Multi-Instance Deployment

A partitioning strategy is only safe when all instances enforce identical rules:

- Same normalization: casing, trimming, Unicode normalization, and null handling.
- Same encoding: UTF-8 or a specified charset, avoiding reliance on default platform charsets.
- Same hash and seed: if producers span Java, Go, and Python, the algorithm must be specified language-independently.
- Same shard count and partition mapping within a deployment phase.
- Same schema for fields used as keys.
- Same ordering requirements: clearly understand whether ordering is per tenant, order, or account.

For example, if instance A uses key `tenant-a:order-101` while instance B uses `TENANT-A:order-101`, they can land on two different partitions. Per-instance unit tests will miss this unless tested against shared key fixtures.

### Watch Out for Hot Keys

A single key can create a hot partition even if the topic has dozens of partitions. Adding instances cannot split a key pinned to one partition. To distribute load, consider narrowing the key granularity from `tenantId` to `orderId`, using a composite key, or sharding once you confirm tenant-wide ordering can be relaxed.

Never use random keys for workflows requiring idempotency or ordering. Throughput optimization must preserve business correctness; reducing lag at the cost of broken ordering or duplicate updates is not a valid improvement.

## 15. Registering Multiple Converters or Strategies in the Same Application

An application can simultaneously process JSON events, partner formats, and Protobuf:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrder;routeInvoice
    stream:
      bindings:
        normalizeOrder-in-0:
          destination: orders.raw
          content-type: application/vnd.acme.order-line
        normalizeOrder-out-0:
          destination: orders.normalized
          content-type: application/vnd.acme.order-line
          producer:
            partition-key-extractor-name: tenantOrderExtractor
            partition-count: 12
        routeInvoice-in-0:
          destination: invoices.raw
          content-type: application/json
        routeInvoice-out-0:
          destination: invoices.normalized
          content-type: application/json
          producer:
            partition-key-extractor-name: invoiceExtractor
            partition-count: 12
~~~

These functions are illustrative; the application context must provide `normalizeOrder` and `routeInvoice` beans. A custom converter bean is registered context-wide, so verify it accepts only its intended MIME type and target type. Partitioning strategies use bean names per binding so streams do not accidentally share keys.

If the application uses multiple binders, you can specify:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        normalizeOrder-out-0:
          binder: kafka
        routeInvoice-out-0:
          binder: rabbit
~~~

Binder names must match the application's binder definitions. A Kafka header mapper applies only within the Kafka binder; RabbitMQ and Pulsar have their own mechanisms. Do not expect one header mapper bean to apply across all three transports.

## 16. Unit Testing Converters

Round-trip tests with `toMessage`/`fromMessage` verify the converter produces the right bytes and parses back the exact record:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.converter.MessageConverter;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

class OrderLineMessageConverterTest {

    private final MessageConverter converter =
            new OrderLineMessageConverter();

    @Test
    void roundTrip() {
        OrderEvent event =
                new OrderEvent("tenant-a", "order-101", 250000L);
        var mime = MimeTypeUtils.parseMimeType(
                "application/vnd.acme.order-line");
        MessageHeaders headers = new MessageHeaders(
                Map.of(MessageHeaders.CONTENT_TYPE, mime));

        Message<?> encoded = converter.toMessage(event, headers);
        assertThat(encoded).isNotNull();
        assertThat(encoded.getPayload()).isInstanceOf(byte[].class);
        assertThat(new String(
                (byte[]) encoded.getPayload(),
                StandardCharsets.UTF_8))
                .isEqualTo("tenant-a|order-101|250000");

        Message<byte[]> incoming = MessageBuilder
                .withPayload((byte[]) encoded.getPayload())
                .setHeader(MessageHeaders.CONTENT_TYPE, mime)
                .build();

        OrderEvent decoded = (OrderEvent)
                converter.fromMessage(incoming, OrderEvent.class);
        assertThat(decoded).isEqualTo(event);
    }
}
~~~

Additional tests should cover blank fields, wrong delimiters, invalid amounts, oversized byte arrays, and unrelated MIME types. When rejected for unsupported types, tests should verify it does not hijack ordinary JSON converters.

## 17. Testing Header Mappers Bidirectionally

Kafka can test mappers using `RecordHeaders` without a broker:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.HashMap;
import java.util.Map;
import org.apache.kafka.common.header.internals.RecordHeaders;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.support.MessageBuilder;

class KafkaHeaderConfigurationTest {

    @Test
    void keepsAllowedHeaders() {
        var mapper = new KafkaHeaderConfiguration()
                .orderKafkaHeaderMapper();
        var source = MessageBuilder.withPayload("value")
                .setHeader("event-id", "evt-101")
                .setHeader("correlation-id", "checkout-7842")
                .setHeader("secret", "do-not-forward")
                .build();

        var kafkaHeaders = new RecordHeaders();
        mapper.fromHeaders(source.getHeaders(), kafkaHeaders);

        Map<String, Object> mapped = new HashMap<>();
        mapper.toHeaders(kafkaHeaders, mapped);

        assertThat(mapped).containsEntry("event-id", "evt-101");
        assertThat(mapped)
                .containsEntry("correlation-id", "checkout-7842")
                .doesNotContainKey("secret");
    }
}
~~~

This test snippet sits in a test class with JUnit Jupiter/AssertJ dependencies. This unit test verifies the custom mapper and allowlist, but does not prove the broker/binder actually uses the bean. Complement it with a Kafka container test checking that consumers receive the expected headers along with required content-type and tracing headers.

For Pulsar, unit tests should verify `toPulsarHeaders` and `toSpringHeaders` using fixtures compatible with your Spring Pulsar version's API. For RabbitMQ, test mapping from `MessageHeaders` to `MessageProperties` and back, then verify against a real queue.

## 18. Testing Partitioning Strategies

Key properties to verify:

1. **Determinism:** same key, same partition count → same partition.
2. **Range:** index always falls within `[0, partitionCount - 1]`.
3. **Business grouping:** events for the same order yield the same key.
4. **Distribution:** representative datasets do not overload a single partition.
5. **Compatibility:** algorithms stay consistent across producers and instances.
6. **Migration:** changing partition counts or shard counts has a plan for ordering and state.

Example testing the selector directly:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.cloud.stream.binder.PartitionSelectorStrategy;

class StableSelectorTest {

    private final PartitionSelectorStrategy selector =
            new OrderPartitionConfiguration().stableSelector();

    @Test
    void sameKeyAlwaysGetsSamePartition() {
        int first = selector.selectPartition("tenant-a:order-101", 12);
        int second = selector.selectPartition("tenant-a:order-101", 12);
        assertThat(second).isEqualTo(first);
    }

    @Test
    void resultIsWithinRange() {
        for (int i = 0; i < 1000; i++) {
            int partition = selector.selectPartition("order-" + i, 12);
            assertThat(partition).isBetween(0, 11);
        }
    }
}
~~~

Checking uniform partition distribution with random synthetic keys is not enough to prove production balance. Use realistic traffic samples or simulated distributions featuring hot tenants/accounts, measuring record counts, bytes, and processing cost. If a single key accounts for 50% of traffic, even a perfect hash still creates a hot partition.

### Testing with the Spring Integration Test Binder

Test Binder lets you verify `Function`/`Consumer`, content conversion, and binding paths via `InputDestination`/`OutputDestination`. It is useful for confirming that functions and converters are selected, but does not fully simulate partition assignment, native Kafka header mappers, RabbitMQ routing, or Pulsar subscriptions.

For custom partitioning, unit-test the beans directly and add real-broker integration tests. Do not treat Test Binder results as proof that the same key landed on the right partition in a real broker.

## 19. End-to-End Testing with Real Brokers

Maintain an integration test suite for each deployed binder, e.g., using Testcontainers:

| Test aspect | Kafka | RabbitMQ | Pulsar |
|---|---|---|---|
| Payload converter | Reads DTO from producer bytes and writes back the exact wire format | Same via AMQP payload | Same via Pulsar `Schema.BYTES` when using framework conversion |
| Header round-trip | Custom `KafkaHeaderMapper` preserves expected headers | AMQP properties and user headers match | `PulsarHeaderMapper` forwards expected user properties |
| Partition/routing | Inspects topic/partition and record key | Verifies exchange/queue/routing key | Verifies topic partition and message key |
| Scaling group | Multiple consumers share Kafka partitions | Group/queue or partitioned instance assignment | Subscription type and consumer distribution |
| Failure path | Conversion error, retry, and DLT | Reject/requeue, DLX/DLQ | NACK/redelivery, DLQ |

Integration workflow:

1. Start the test broker of the exact type and version.
2. Boot the application with the real binder; confirm no mock binder accidentally substitutes it.
3. Send messages with `contentType`, event ID, correlation ID, and key.
4. Receive at the consumer and assert payload, headers, key/partition, or routing metadata.
5. Send additional messages with the same key and verify partition stability.
6. Send a malformed message to verify error policy, retries, and DLQ.
7. Run multiple consumer instances if the system genuinely requires scaling.

Run with representative message sizes and key distributions. Asserting that a broker received one message is not enough: mapper/partition bugs often surface only with varied header types, multiple producers, or partition-count changes.

## 20. Observability and Error Handling in Scaled Environments

Adding extensions introduces specific failure modes:

| Symptom | Possible cause | What to check |
|---|---|---|
| Function receives `byte[]` instead of DTO | Wrong content type or native decoding enabled | Compare header, binding content type, native flag, and converter bean. |
| Right converter exists but is never called | Payload already matches target type; another converter matched first; native mode | Check function signature and converter precedence. |
| JSON bindings start failing after adding converter | Custom converter claims overly broad MIME/type | Narrow `supports` and supported MIME types. |
| Kafka missing `event-id` | Custom mapper omitted inbound/outbound mapping | Check both directions and the binder mapper bean name. |
| Kafka loses trace context | Mapper only allowlists a few business headers | Add required propagation or customize the default mapper more safely. |
| Pulsar drops correlation ID | `!` pattern placed after `*`, or another mapper chosen | Check pattern order, bean selection, and user property values. |
| Rabbit misses expected headers | Header mapper not attached properly to adapter/binder | Check wiring and broker-side message properties. |
| Partition out of range | Selector returns negative index or ≥ `partitionCount` | Use `Math.floorMod` and unit-test range bounds. |
| Same order lands on multiple partitions | Differing key normalization, hash, encoding, or partition count | Compare conventions and actual broker metadata records. |
| Adding instances does not boost throughput | Single hot key or fewer partitions than consumers | Measure per-partition lag, key skew, and consumer assignment. |
| Retries process data out of order | Multiple partitions, requeues, or concurrency | Clarify ordering boundaries and design idempotency. |
| Production fails while Test Binder passes | Tests omitted real broker/native mappers | Add Testcontainers or a real broker test environment. |

Diagnostic logs should include binding name, destination, content type, event ID, correlation ID, broker, partition or queue, and error type. Do not dump full message headers or payloads containing sensitive data. Capture exception stack traces only for investigation, and distinguish conversion errors (unreadable data) from business errors (parsed cleanly, failed processing).

## 21. Safe Rollout Plan for Extensions

When changing a converter, mapper, or partition strategy on a live flow, roll it out like a protocol change:

1. Lock down payload contract, content type, header names/encoding, and key semantics with producers and consumers.
2. Add unit tests for converter, header round-trip, and selector determinism.
3. Add compatibility tests with new producers against old consumers and vice versa if rolling upgrades are required.
4. Ensure all instances run the same beans/config and hash algorithm before shifting traffic.
5. If keys or partition mappings change, assess ordering, state stores, changelogs, and existing backlog.
6. Consider a new topic/version for incompatible changes to avoid mixing two semantics on one topic.
7. Run a canary with small traffic, monitoring conversion errors, DLQ rates, missing-header rates, and per-partition lag.
8. Shift traffic according to plan, checking idempotency, duplicates, and consumer ordering.
9. Keep rollback capability, while recognizing that rolling back key partitioning may require handling data produced under the new mapping.

Avoid updating converters and partition strategies simultaneously unless necessary; rolling out one change at a time makes root-cause analysis much easier if a flow breaks.

## 22. Completion Checklist

- [ ] Distinguished converter, header mapper, extractor, and selector.
- [ ] Custom converter supports only the required MIME types and target classes.
- [ ] Converter sends/receives bytes per contract when using framework conversion.
- [ ] `contentType` headers and binding configs do not conflict.
- [ ] Native encoding/decoding flags verified to avoid unintentionally bypassing converters.
- [ ] Business metadata uses clear header names without reserved conflicts.
- [ ] Kafka header mapper registered under the exact bean name and retains required headers.
- [ ] Rabbit AMQP mapper wired to the right adapter or binder extension point when customized.
- [ ] `PulsarHeaderMapper` excludes sensitive headers and trusts only required packages.
- [ ] `partition-key-extractor-name` and `partition-selector-name` match bean names.
- [ ] Expression and bean name are not set simultaneously for the same role.
- [ ] Selector is deterministic and always returns a valid partition.
- [ ] Hashing, encoding, and key normalization are consistent across all instances.
- [ ] Business ordering boundaries are verified.
- [ ] Kafka native partitioner, Rabbit queue routing, and Pulsar `Key_Shared` are not conflated.
- [ ] Unit tests and real-broker integration tests verify converter, headers, and partitioning.
- [ ] Retry, DLQ, rolling upgrade, and rollback scenarios reviewed.
- [ ] Monitoring tracks conversion errors, missing headers, skew, and consumer lag.

## Summary

Spring Cloud Stream supports deep customization while preserving the `Supplier`/`Function`/`Consumer` model: `MessageConverter` handles payload formats, header mappers protect and translate metadata, and extractors/selectors govern key distribution in generic partitioning. Register these beans with explicit names, MIME types, and scopes. Across Kafka, RabbitMQ, and Pulsar, also check each broker's native mechanisms because they serialize, route, and scale consumers differently. A change succeeds when payloads decode cleanly, headers survive end-to-end, partitioning remains stable, and business ordering holds as the system scales.

## References

- [Spring Cloud Stream — User-defined Message Converters](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-user-defined-message-converters.html)
- [Spring Cloud Stream — Content Type and Message Conversion](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/mechanics.html)
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream — Partitioning](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-partitioning.html)
- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Cloud Stream — Kafka Binder Partitioning](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/partitions.html)
- [Spring Cloud Stream — Kafka Header Mapper Tips](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka_tips.html)
- [Spring Integration — AMQP Message Headers](https://docs.spring.io/spring-integration/reference/amqp/message-headers.html)
- [Spring Cloud Stream — Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html)
- [Spring Pulsar — Header Mapping](https://docs.spring.io/spring-pulsar/reference/reference/pulsar-header.html)
