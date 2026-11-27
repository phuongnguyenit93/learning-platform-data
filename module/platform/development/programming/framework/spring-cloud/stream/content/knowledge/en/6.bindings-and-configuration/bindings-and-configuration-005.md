# Common Properties, Producer Properties, and Consumer Properties

In Spring Cloud Stream, a binding is the connection point between an application's processing function and a destination on the broker. A binding can be an input to receive messages or an output to send messages. Each binding has common properties such as destination, consumer group, content type, and binder; in addition, there are properties specific to the producer side or the consumer side. Understanding the exact scope of each property helps configure event flows clearly, avoiding misplacing a producer option on an input binding or applying a Kafka-specific property to RabbitMQ.

Spring Cloud Stream provides the `Supplier`, `Function`, `Consumer` functional model, bindings, and binders. The binder translates common properties into corresponding configurations for Kafka, RabbitMQ, or Pulsar. Core properties are shared at the abstraction level; broker-specific options are placed in the extension namespace of the respective binder. Property names and support may vary across Spring Cloud Stream and binder versions, so always cross-check the documentation for the exact version in use.

## 1. Configuration model of a binding

For a function named `processOrder`, Spring Cloud Stream creates two default bindings:

- `processOrder-in-0`: input binding, receiving messages from the input destination.
- `processOrder-out-0`: output binding, sending messages to the output destination.

Core properties are declared under `spring.cloud.stream.bindings.<bindingName>`:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processor
          content-type: application/json
          consumer:
            concurrency: 3
            max-attempts: 4
        processOrder-out-0:
          destination: orders.accepted
          content-type: application/json
          producer:
            partition-key-expression: payload.orderId
            partition-count: 6
```

In this example, the input binding receives events from destination `orders.created` under group `order-processor`. The output binding sends results to destination `orders.accepted` and uses `orderId` as the partition key according to Spring Cloud Stream's partitioning mechanism. The `consumer` section applies only to inputs; the `producer` section applies only to outputs.

## 2. Common binding properties

Common properties describe where a binding connects, which group it uses, and how payloads are interpreted.

| Property | Meaning | Notes |
|---|---|---|
| `destination` | Destination name on the broker, typically a topic or exchange/queue depending on the binder | Physical name and provisioning rules depend on the binder |
| `group` | Consumer group or logical receiving group name | Primarily meaningful for input bindings; affects how multiple instances share messages |
| `content-type` | Message content format, e.g. `application/json` | Related to message conversion; not the broker serializer name |
| `binder` | Specifies the binder that serves the binding | Useful when the application has multiple binders on the classpath |
| `consumer` | Property group for the receiving side | Configured only on input bindings |
| `producer` | Property group for the sending side | Configured only on output bindings |

### destination

`destination` maps a binding to a resource on the broker. With Kafka, the destination is typically a topic. With RabbitMQ, the binder maps the destination via an exchange and associated queues according to configuration. With Pulsar, the destination is typically a topic. Even with the same property name, physical resources and resource-creation rules can differ across binders.

If `destination` is omitted, some configurations can infer a default name from the binding; however, in real applications it should be declared explicitly for readability, operations, and broker access control. Destination names should also follow the system's naming conventions.

### group

`group` identifies a logical consumer group for an input binding. Multiple instances using the same group generally share message consumption according to the broker's mechanism. With Kafka, instances in the same consumer group divide partitions. With RabbitMQ, the queue bound to the group is typically competed over by multiple consumers. With Pulsar, `group` is mapped to a subscription in the binder's manner.

If `group` is not declared, the binder may create an anonymous consumer group or an instance-specific subscription. Retention and message-sharing behavior then differ from a stably named group. For services that need to resume reading after restarts and load-balance across multiple instances, declare `group` explicitly and check how the binder provisions resources.

### content-type

`content-type` tells Spring Cloud Stream the payload format so it can pick a message converter, such as `application/json` or `text/plain`. It describes the content format at the message abstraction layer. When native encoding/decoding is enabled, the binder/client serializer or deserializer may handle conversion at the broker layer; in that case configure it in sync with the data type expected by the function.

### binder

When multiple binders are on the classpath, the `binder` property selects the binder for a specific binding. For instance, an application might use Kafka to emit business events and RabbitMQ to send internal commands. Adding multiple binders only makes sense when the application genuinely needs to connect to multiple brokers; configure each binder carefully and avoid letting a binding accidentally pick the wrong broker.

## 3. Default configuration and per-binding configuration

Spring Cloud Stream supports default settings for multiple bindings under `spring.cloud.stream.default`. When a specific binding needs different behavior, declare its own properties under `spring.cloud.stream.bindings.<bindingName>`. For example:

```yaml
spring:
  cloud:
    stream:
      default:
        content-type: application/json
        consumer:
          max-attempts: 3
          back-off-initial-interval: 1000
          back-off-max-interval: 10000
        producer:
          error-channel-enabled: true
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processor
          consumer:
            max-attempts: 5
        processOrder-out-0:
          destination: orders.accepted
```

In this example, bindings use JSON by default. Consumer `processOrder-in-0` overrides the attempt count to 5; other consumer properties still inherit from the default configuration unless overridden. Default configuration reduces repetition, while per-binding configuration expresses exceptions right where they apply.

Distinguish Spring Cloud Stream's `default` configuration from Spring Boot's configuration precedence. Spring Boot also merges configuration sources such as YAML files, profile-specific files, environment variables, system properties, and command-line arguments. When values differ, higher-priority configuration sources can override values in files. When investigating effective configuration, check the binding name, active profiles, and deployed configuration sources.

## 4. Producer properties

The producer is the side sending messages to an output binding. The `producer` property group controls how messages are produced and routed on the sending side. Common properties include partition keys, partition counts, consumer groups to provision, native encoding, and error channels.

### partition-key-expression and partition-count

`partition-key-expression` is a SpEL expression used to extract a partition key from the payload or message. `partition-count` indicates the expected number of partitions used by Spring Cloud Stream's partitioning mechanism. For example:

```yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.created
          producer:
            partition-key-expression: payload.orderId
            partition-count: 8
```

If messages share the same `orderId`, they can be routed to the same partition according to the partition selector algorithm. This is useful when you need to preserve ordering of events for the same order. The key should be stable, well-distributed, and non-null. If all messages use the same key, one partition can become a hotspot.

Partitioning at the Spring Cloud Stream layer must be distinguished from broker-level partition configuration. The Kafka binder can also use Kafka's own partitioner or key serializer; RabbitMQ and Pulsar have their own routing mechanisms. Do not assume the same partition expression behaves identically across every binder. Check the binder documentation and the actual destination configuration.

### partition-selector-expression

When you need to control how a partition is chosen from the extracted key, you can use `partition-selector-expression`. Normally you do not need to customize the selector if the default algorithm meets requirements. Only change it for load-distribution reasons or compatibility with existing routing conventions; changing the selector can route the same key to a different partition after deployment.

### required-groups

`required-groups` lists consumer groups for which the binder should provision resources before or as soon as the producer binding is created, depending on the binder. For example:

```yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.created
          producer:
            required-groups:
              - order-projection
              - audit-service
```

This property is helpful when a producer starts emitting messages before consumer groups start up. With brokers/binders that support this provisioning mechanism, receiving resources can be pre-created so messages are not lost simply because consumers are not running yet. Exact behavior depends on the binder, destination type, and retention policy; do not treat `required-groups` as a delivery guarantee independent of broker configuration.

### use-native-encoding

`use-native-encoding` instructs the binder/client to use the broker's native serialization mechanism instead of Spring Cloud Stream's message converter for output. This property should generally only be enabled when a matching serializer is configured and the consumer has a compatible deserializer. If enabled with a serializer that does not match the payload type, messages may be sent in a format the consumer cannot read.

The example below only illustrates where the property goes:

```yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.created
          producer:
            use-native-encoding: true
```

With native encoding, serializer configuration usually lives in the binder extension section, such as Kafka producer properties. Do not enable this option merely to work around a message conversion error; identify the actual wire format and configure both sides properly.

### error-channel-enabled

`error-channel-enabled` controls generating an error channel for binding-related errors according to framework and binder capabilities. The error channel lets the application or an integration component observe asynchronous send failures and handle them by policy. It does not automatically guarantee message resending or storage in a DLQ. Retries, error handling, and DLQs must be designed separately.

## 5. Consumer properties

The consumer is the side receiving messages from an input binding. Consumer properties typically control concurrency, retries, partitioning, native decoding, and error handling.

### concurrency

`concurrency` specifies the number of concurrent consumers or processing threads the binder/container creates for a binding, within the limits supported by the binder. For example:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processor
          consumer:
            concurrency: 3
```

Increasing concurrency can improve throughput when there are enough partitions or messages to process and sufficient application resources. With Kafka, having more consumers in the same group than partitions leaves extra consumers idle. With RabbitMQ and Pulsar, practical limits depend on queues/subscriptions, consumer count, prefetch, partitions, and binder implementation. Setting concurrency too high can increase database load, resource contention, or out-of-order processing at the business layer.

### max-attempts and backoff

Core retry properties include:

| Property | Meaning |
|---|---|
| `max-attempts` | Total processing attempts including the initial attempt and retries |
| `back-off-initial-interval` | Initial wait interval before a retry |
| `back-off-max-interval` | Maximum cap on the wait interval |
| `back-off-multiplier` | Multiplier applied to the wait interval between retries |
| `default-retryable` | Default rule for whether an exception is retryable when no explicit rule exists |
| `retryable-exceptions` | Map of exception classes to boolean values allowing or denying retries |

For example:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processor
          consumer:
            max-attempts: 4
            back-off-initial-interval: 1000
            back-off-max-interval: 8000
            back-off-multiplier: 2.0
            default-retryable: true
            retryable-exceptions:
              com.example.TemporaryGatewayException: true
              com.example.InvalidOrderException: false
```

With this configuration, transient errors can be retried with exponential backoff; invalid data errors are marked non-retryable. `max-attempts: 1` means only the initial invocation runs, with no subsequent retries. Retries are only suitable for errors likely to resolve on their own; retrying permanent data errors usually just prolongs processing time and increases load.

Abstraction-level retries can occur within the consumer process. If the process stops abruptly, the broker may redeliver the message via its own mechanism. Therefore, in-application retry and broker redelivery are two distinct mechanisms. Use idempotency to protect business logic from duplicate processing.

### partitioned, instance-count, and instance-index

In partition-aware deployment models, `partitioned` indicates that the consumer binding participates in Spring Cloud Stream's partitioning mechanism. `instance-count` and `instance-index` specify the total number of instances and the index of the current instance in configurations requiring partition assignment. Some versions/configurations place the two instance properties at the `spring.cloud.stream` level; verify the documentation for your exact version and binder.

Illustrative example for two instances:

```yaml
spring:
  cloud:
    stream:
      instance-count: 2
      instance-index: 0
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processor
          consumer:
            partitioned: true
```

The other instance uses the same `instance-count` but `instance-index: 1`. Do not configure two replicas with the same instance index when the partitioning mechanism requires unique indices. With Kafka, Kafka's own consumer group and partition assignment also participate in actual distribution; do not confuse Spring Cloud Stream's `instance-index` with Kafka's internal partition assignment.

### use-native-decoding

`use-native-decoding` instructs the binder/client to use the broker's native deserializer instead of Spring Cloud Stream's message converter for input. This option normally needs to be paired with the corresponding deserializer configuration. Producer and consumer must agree on serializer/deserializer and schema. If native decoding is enabled only on the consumer while the producer still sends JSON via a different mechanism, data may fail to decode.

## 6. Distinguishing core properties from binder-specific extension properties

Core properties live under `spring.cloud.stream.bindings`. Binder-specific extension properties live under a specific binder namespace, such as `spring.cloud.stream.kafka.bindings` or `spring.cloud.stream.rabbit.bindings`. Extensions expose broker-specific capabilities.

For example, the Kafka binder may have consumer configuration to enable a DLQ:

```yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              enable-dlq: true
              dlq-name: orders.created.dlq
```

Names and capabilities of extension properties such as DLQ, offset, acknowledgement, or transactions depend on the Kafka binder version. Do not put `enable-dlq` into the core `consumer` section and expect every binder to interpret it the same way.

The Rabbit binder has its own options to create dead-letter exchanges/queues, control requeue, or configure prefetch. Example showing namespace placement:

```yaml
spring:
  cloud:
    stream:
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              auto-bind-dlq: true
              republish-to-dlq: true
```

Check the exact property names and support conditions in the documentation for your Rabbit binder version. The Pulsar binder also has its own extensions for subscriptions, dead-letter policies, and acknowledgements. You cannot copy a Kafka configuration to RabbitMQ or Pulsar simply by changing the destination name.

## 7. Combined configuration example

Suppose the `processOrder` function receives `OrderCreated`, validates the order, and returns `OrderAccepted`. The core configuration can be organized as follows:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      default:
        content-type: application/json
        consumer:
          max-attempts: 3
          back-off-initial-interval: 1000
          back-off-max-interval: 10000
          back-off-multiplier: 2.0
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processor
          consumer:
            concurrency: 2
            max-attempts: 4
            retryable-exceptions:
              com.example.InvalidOrderException: false
        processOrder-out-0:
          destination: orders.accepted
          producer:
            partition-key-expression: payload.orderId
            partition-count: 6
            required-groups:
              - order-projection
              - audit-service
```

Reading the configuration from top to bottom:

1. `processOrder` is the activated function.
2. Bindings use JSON by default.
3. The input reads from `orders.created` with consumer group `order-processor`.
4. The consumer has concurrency 2 and up to 4 attempts; `InvalidOrderException` is not retried.
5. The output sends to `orders.accepted`, uses `orderId` as the partition key, and declares two receiving groups to provision if supported by the binder.

This example illustrates core properties and does not yet include broker connection details, credentials, native serializers, or binder-specific DLQ settings. Those parts must be configured according to the environment and broker type.

## 8. Choosing properties and avoiding configuration errors

| Need | Properties to consider | Applicable binding |
|---|---|---|
| Change target topic/queue | `destination` | Input or output |
| Load-balance across consumer instances | `group` | Input |
| Choose payload format | `content-type` | Input or output |
| Choose broker when multiple binders exist | `binder` | Input or output |
| Increase concurrent consumers | `consumer.concurrency` | Input |
| Retry transient errors | `consumer.max-attempts`, `back-off-*`, `retryable-exceptions` | Input |
| Partition by business key | `producer.partition-key-expression`, `partition-count` | Output |
| Pre-provision resources for receiving groups | `producer.required-groups` | Output |
| Use native serializer/deserializer | `producer.use-native-encoding`, `consumer.use-native-decoding` | Output/input respectively |
| Enable broker-specific features | Binder extension namespace | Depends on binder and direction |

Some common configuration mistakes:

- Placing producer properties on an input binding or consumer properties on an output binding. The properties may be ignored or fail to behave as expected.
- Confusing the binding name with `destination`. The binding name is an application configuration key; `destination` is the broker resource name.
- Treating `content-type` as if it were a Kafka serializer class. The two configuration layers have different roles.
- Enabling native encoding/decoding without configuring compatible serializers/deserializers on both sides.
- Increasing concurrency without considering partition count, broker limits, or downstream processing capacity.
- Using the same group for two applications with independent consumption goals, causing them to compete for messages instead of each receiving its own copy.
- Copying extension properties between binders without checking the target binder's documentation.

When a property has no effect, check the spelling of the binding name, namespace placement, active profiles, higher-priority configuration sources, and binding initialization logs. In multi-binder applications, check whether the binding selected the right binder.

## 9. Testing and operating configuration

Configuration tests should verify observable behavior rather than just checking that YAML parses:

- Boot the context and confirm the right function and input/output bindings are created.
- Send a valid JSON message, verify the payload converts to the right type, and confirm output reaches the expected destination.
- Send a message causing a transient failure and confirm retry counts/backoff follow configuration.
- Send a message with a non-retryable failure and confirm the binder-specific error/DLQ path.
- Run multiple instances in the same group to observe message distribution and check concurrency/partitioning.
- Test partition keys across multiple key values to confirm events for the same aggregate route as required.
- Test native encoding/decoding using the actual serializer and deserializer.

The test binder is useful for testing function logic and bindings within the application scope. It does not replace integration tests with Kafka, RabbitMQ, or Pulsar when verifying partition assignment, publisher confirmation, offset/acknowledgement, dead-letter routing, durability, or redelivery behavior.

In production, monitor inbound/outbound message rates, consumer lag, processing latency, retry counts, DLQ depth, conversion errors, active consumer counts, and broker connectivity health. Log binding name, destination, group, and event ID so configuration issues can be correlated with specific messages. Avoid logging sensitive payloads.

## 10. Pre-deployment checklist

- [ ] Every binding has a clear name and points to the right destination.
- [ ] Input bindings have stable groups when load sharing and restart resumption are needed.
- [ ] Content type matches payload types and message converters.
- [ ] Consumer properties are placed only on input bindings; producer properties only on output bindings.
- [ ] Concurrency matches partition count, broker limits, and downstream capacity.
- [ ] Retries are bounded and classify exceptions; DLQs are configured per binder when needed.
- [ ] Partition keys are stable and distribute load reasonably.
- [ ] Native encoding/decoding is only enabled when serializer/deserializer are configured in sync.
- [ ] Extension properties are verified against the exact binder and version.
- [ ] Tests against a real broker have verified critical behavior before release.

When common, producer, and consumer properties are cleanly separated, Spring Cloud Stream configuration accurately reflects each binding's responsibility. Combining core configuration with the right binder extensions keeps the application portable at the abstraction level while still tapping into the required capabilities of Kafka, RabbitMQ, or Pulsar.
