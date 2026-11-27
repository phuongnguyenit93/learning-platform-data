# Extension Properties by Kafka, RabbitMQ, and Pulsar Namespace

Spring Cloud Stream provides a common configuration model for input and output bindings. Properties such as `destination`, `group`, and `content-type` describe the data stream at the application level. Each message broker also has its own rules: Kafka works with topics, partitions, offsets, and consumer groups; RabbitMQ uses exchanges, queues, acknowledgements, and routing; Pulsar uses tenants, namespaces, topics, and subscriptions.

To express those broker-specific capabilities, each binder has an **extension property namespace**. The Kafka binder uses `spring.cloud.stream.kafka`, the Rabbit binder uses `spring.cloud.stream.rabbit`, and the Pulsar binder uses `spring.cloud.stream.pulsar`. Within each namespace, an application can configure binder-level defaults or fine-tune settings per binding.

This lesson explains how to read those namespaces, distinguish shared properties from broker-specific properties, configure consumers and producers, and pick the right scope when deploying Spring Cloud Stream.

## 1. Why are extension properties needed?

A binding describes an input or output port of an application. Common configuration lets the application declare destination, group, content type, and general options without depending directly on a broker.

Example consumer:

```java
@Bean
Consumer<OrderCreated> processOrder(OrderHandler handler) {
    return handler::handle;
}
```

Common configuration:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
          content-type: application/json
```

This configuration states that input binding `processOrder-in-0` reads destination `orders` in group `order-processor`. However, it does not specify broker-specific options such as:

- Kafka: which offset the consumer starts reading from, how offsets are committed, how a dead-letter topic is enabled, or how many records to fetch per poll.
- RabbitMQ: whether the queue automatically binds a dead-letter exchange, how many messages to prefetch, which acknowledgement mode is used, or the producer's routing key.
- Pulsar: whether the subscription uses `Shared` or `Key_Shared`, the receiver queue size, or whether the producer uses batching or compression.

Those choices are expressed using extension properties of the corresponding binder. As a result, business function code stays focused on event processing, while delivery mechanics are described in infrastructure configuration.

## 2. Namespace structure and configuration scope

There are three configuration layers to distinguish.

| Scope | Typical namespace | What it is used for |
|---|---|---|
| Spring Cloud Stream common properties | `spring.cloud.stream.bindings.<bindingName>` | Destination, group, content type, common consumer/producer properties |
| Application-level binder properties | `spring.cloud.stream.kafka.binder`, `spring.cloud.stream.rabbit.binder`, `spring.cloud.stream.pulsar.binder` | Binder defaults or shared binder policies; connection endpoints may live in a separate Spring Boot namespace |
| Per-binding extension properties | `spring.cloud.stream.kafka.bindings.<bindingName>`, `spring.cloud.stream.rabbit.bindings.<bindingName>`, `spring.cloud.stream.pulsar.bindings.<bindingName>` | Consumer- or producer-specific options for a single binding |

`<bindingName>` is the binding name, such as `processOrder-in-0` or `publishOrder-out-0`. Under the binding namespace, properties are normally divided into two branches:

- `consumer`: options for an input binding.
- `producer`: options for an output binding.

Structure template:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
      kafka:
        binder:
          # Common properties for the Kafka binder
        bindings:
          processOrder-in-0:
            consumer:
              # Extension properties for the Kafka consumer
```

In real configurations, `kafka` can be replaced with `rabbit` or `pulsar` to select the corresponding extension namespace. The `binder` and `bindings` branches sit at the same level under `spring.cloud.stream`.

Spring Cloud Stream also supports default values to avoid repeating configuration. Core uses `spring.cloud.stream.default.consumer.*` and `spring.cloud.stream.default.producer.*`. The Kafka binder supports `spring.cloud.stream.kafka.default.consumer.*` and `spring.cloud.stream.kafka.default.producer.*`; the Rabbit binder has the `spring.cloud.stream.rabbit.default.*` namespace. For Pulsar, shared producer/consumer properties can be placed under `spring.cloud.stream.pulsar.binder.producer.*` and `spring.cloud.stream.pulsar.binder.consumer.*`. Only set defaults when bindings genuinely share the same requirements.

### Common properties and extension properties do not replace each other

Some properties look similar but serve different layers:

- `spring.cloud.stream.bindings.processOrder-in-0.group` defines the logical group of the input binding.
- `spring.cloud.stream.kafka.bindings.processOrder-in-0.consumer.enable-dlq` instructs the Kafka binder to apply dead-letter handling in the way Kafka supports.
- `spring.cloud.stream.rabbit.bindings.processOrder-in-0.consumer.prefetch` tunes how many messages RabbitMQ can deliver ahead to a consumer.
- `spring.cloud.stream.pulsar.bindings.processOrder-in-0.consumer.subscription-type` selects the Pulsar subscription type.

Do not put every property under `spring.cloud.stream.bindings` assuming the framework will automatically map it to every broker. A property is only recognized when it belongs to the right namespace and is supported by the binder in use.

## 3. Kafka binder: topic, consumer, producer, and client properties

The Kafka binder connects bindings to a Kafka cluster. Common namespaces include:

- `spring.cloud.stream.kafka.binder`: general settings for the Kafka binder, such as broker addresses and topic management policies.
- `spring.cloud.stream.kafka.bindings.<bindingName>.consumer`: extension properties for an input binding.
- `spring.cloud.stream.kafka.bindings.<bindingName>.producer`: extension properties for an output binding.

### Binder-level configuration

Example:

```yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          brokers: localhost:9092
            auto-create-topics: true
          auto-add-partitions: false
          min-partition-count: 3
          replication-factor: 1
```

Meaning:

- `brokers` specifies the broker or list of brokers the binder connects to.
- `auto-create-topics` controls whether the binder automatically creates topics when needed.
- `auto-add-partitions` controls whether the binder automatically adds partitions in supported cases.
- `min-partition-count` is the minimum number of partitions the binder uses when provisioning topics per related settings.
- `replication-factor` is the default replication factor for topics created by the binder.

Binder-level properties have broad scope. `min-partition-count` only takes effect when `auto-create-topics` or `auto-add-partitions` is enabled; `replication-factor` applies to topics auto-created by the binder. If `auto-create-topics: false` is set, non-existent destinations must be pre-created by the infrastructure team. This is useful when production requires managing topics through Infrastructure as Code. Do not enable auto-topic creation without checking partition count, replication factor, retention, and topic creation permissions.

### Per-binding consumer properties

Example where an input binding commits offsets and routes failed messages to a dead-letter topic:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
          content-type: application/json
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              ack-mode: record
              enable-dlq: true
              dlq-name: orders.errors
              configuration:
                "max.poll.records": 100
                "isolation.level": read_committed
```

These options have distinct meanings:

- `ack-mode` controls the offset acknowledgement/commit mode as supported by the Kafka binder. `record` is a common choice to tie acknowledgement to each individual record.
- `enable-dlq` enables the Kafka binder's dead-letter handling for the consumer binding.
- `dlq-name` specifies the dead-letter topic name.
- `configuration` passes additional Kafka client properties for the consumer.
- `max.poll.records` limits the number of records returned in a single poll.
- `isolation.level` sets Kafka's transactional read level; `read_committed` reads only records from committed transactions.

A dead-letter topic is a separate resource that needs appropriate partition policies and access permissions. If the binder must auto-create the DLQ topic, check permissions and provisioning settings. When configuring DLQ partitions or a DLQ producer, check the requirements of your binder version; do not assume the DLQ always has the same partition count as the source topic.

### Per-binding producer properties

A producer may need compression, synchronous sends, or Kafka producer client properties:

```yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders
          content-type: application/json
      kafka:
        bindings:
          publishOrder-out-0:
            producer:
              sync: true
              configuration:
                "compression.type": snappy
                "acks": all
                "enable.idempotence": true
```

In this example:

- `sync` instructs the producer to wait for the send result using the binder's synchronous mechanism; this can impact throughput and latency.
- `compression.type` picks a record-batch compression algorithm supported by the Kafka client.
- `acks` specifies the broker acknowledgement level for a send.
- `enable.idempotence` enables producer idempotence when the corresponding Kafka client conditions are met.

`configuration` is a key extension point: it lets you pass Kafka client properties that do not have a dedicated binder property. Only use valid Kafka client properties and check whether each belongs to the producer or consumer. Putting `max.poll.records` on a producer has no effect because it is a consumer property.

### Binder configuration vs. client configuration

The Kafka binder can provide a `configuration` map at the binder level to pass shared Kafka client properties. When a single binding needs custom settings, use the `configuration` map inside that binding's `consumer` or `producer` branch.

For example, a cluster using TLS or SASL may require client security settings. Shared connection parameters should live at the binder level if all bindings share the same cluster and policy. If multiple bindings or clusters have different requirements, place them on the appropriate binder instance or supported binding scope.

Do not confuse Spring for Apache Kafka's `spring.kafka.*` namespace with the Kafka binder's `spring.cloud.stream.kafka.*` extension namespace. An application can use both libraries, but they may create separate clients and lifecycles. Settings in one namespace do not automatically apply to clients created by the other.

## 4. Rabbit binder: exchange, queue, acknowledgement, and routing

The Rabbit binder connects Spring Cloud Stream to RabbitMQ. Extension namespaces include:

- `spring.cloud.stream.rabbit.binder`: connection and binder-wide policies.
- `spring.cloud.stream.rabbit.bindings.<bindingName>.consumer`: queue, acknowledgement, prefetch, retry, and DLQ settings for input.
- `spring.cloud.stream.rabbit.bindings.<bindingName>.producer`: exchange, routing key, delivery, and publisher behavior for output.

### Binder-level configuration

Example:

```yaml
spring:
  rabbitmq:
    addresses: localhost:5672
    username: app-user
    password: ${RABBITMQ_PASSWORD}
    virtual-host: /orders
```

`addresses` specifies the RabbitMQ addresses; `virtual-host` selects the virtual host. The Rabbit binder uses Spring Boot's `ConnectionFactory` by default, so connection properties such as host, port, addresses, username, password, and virtual host belong to the `spring.rabbitmq` namespace. The binder has its own properties under `spring.cloud.stream.rabbit.binder`, such as `nodes` and `adminAddresses` for locating queues in a RabbitMQ cluster. Passwords are read from environment variables to avoid committing secrets into config files.

Binder-level settings are suited for shared connections. If the application connects to multiple brokers or independent virtual hosts, consider configuring multiple binder instances and assigning a binder alias to each binding.

### Per-binding consumer properties

RabbitMQ uses queues to store messages for subscribers. Multiple consumers in the same group can consume from that queue together. Extension settings typically control how queues are declared and how consumers receive messages.

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              acknowledge-mode: auto
              prefetch: 20
              max-concurrency: 4
              auto-bind-dlq: true
              republish-to-dlq: true
              dlq-ttl: 60000
```

Explanation:

- `acknowledge-mode` chooses how the consumer acknowledges messages. In `auto` mode, the container manages acknowledgements based on processing outcomes.
- `prefetch` limits how many unacknowledged messages the broker delivers ahead to a consumer.
- `max-concurrency` caps the maximum concurrency of the consumer container when supported by the binder.
- `auto-bind-dlq` instructs the binder to declare and bind a dead-letter queue per its rules.
- `republish-to-dlq` enables republishing failed messages to the DLQ with error metadata per binder capabilities.
- `dlq-ttl` sets the time-to-live for messages in the DLQ in the unit defined by the binder property (typically milliseconds).

Prefetch directly impacts load distribution. If prefetch is too high, one consumer can hold many unacknowledged messages while another consumer sits idle. If too low, the broker may wait for the consumer to finish each message before delivering more, lowering throughput. Tune it based on processing time and downstream capacity.

`auto-bind-dlq` can cause the binder to create additional queues or exchanges. In production, verify the account's `configure` permissions and DLQ naming policies. If infrastructure is pre-provisioned, configure the binder so its declaration behavior aligns with that policy.

### Per-binding producer properties

A Rabbit producer may need to choose a routing key or set outgoing headers:

```yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders
          content-type: application/json
      rabbit:
        bindings:
          publishOrder-out-0:
            producer:
              routing-key-expression: "'orders.created'"
              delivery-mode: persistent
              declare-exchange: true
```

- `routing-key-expression` is an expression used to determine the routing key when sending messages. The fixed string in the example is written as a SpEL expression.
- `delivery-mode` selects persistent or non-persistent message delivery as supported by the binder and broker.
- `declare-exchange` controls whether the binder declares the exchange per producer configuration.

If the routing key depends on message data, the expression can read headers or payload. Ensure the exchange type and consumer queue bindings match the routing key. A producer successfully sending to an exchange does not mean the message was routed to a queue; publisher confirms/returns and routing metrics help detect unrouted messages.

### Retry and dead-lettering in RabbitMQ

The Rabbit binder can support auto-bind DLQ, dead-letter exchanges, dead-letter routing keys, TTL, and queue arguments. These properties affect the created queues/exchanges or how messages are routed when a consumer fails.

Distinguish two things:

1. In-application/container retry: messages can be retried according to the retry policy.
2. Broker-level dead-lettering: messages are routed to a DLQ when rejected, expired by TTL, or meeting a queue policy condition.

Do not configure infinite retries for a poison message or undecodable payload. Cap attempt counts, set reasonable backoff, and capture error details so operations can investigate, fix data, or perform controlled replays.

## 5. Pulsar binder: tenant, namespace, and subscription

The Pulsar binder uses dedicated namespaces for per-binding extension properties and binder-level producer/consumer defaults. Client and admin endpoints are typically configured via Spring Boot properties from Spring for Apache Pulsar:

- `spring.cloud.stream.pulsar.binder`: default partition count and shared producer/consumer properties; client/admin endpoints are usually configured via Spring Boot properties under `spring.pulsar.*`.
- `spring.cloud.stream.pulsar.bindings.<bindingName>.consumer`: subscription type, receiver, acknowledgement, and consumer options.
- `spring.cloud.stream.pulsar.bindings.<bindingName>.producer`: batching, routing, compression, timeout, and producer options.

### Binder configuration

Example:

```yaml
spring:
  pulsar:
    client:
      service-url: pulsar://localhost:6650
    administration:
      service-url: http://localhost:8080
  cloud:
    stream:
      pulsar:
        binder:
          partition-count: 4
```

`spring.pulsar.client.service-url` is the Pulsar protocol endpoint the client connects to; `spring.pulsar.administration.service-url` is the admin endpoint used by the provisioner when calling the Pulsar Admin API. These are Spring Boot properties for Spring for Apache Pulsar. In the binder namespace, `spring.cloud.stream.pulsar.binder.partition-count` sets the default partition count for provisioned topics according to binder capabilities.

Pulsar topic names typically have the full form `persistent://<tenant>/<namespace>/<topic>`. Specify tenant and namespace in the destination or in Spring for Apache Pulsar defaults per your version; do not assume the binder has separate `tenant` and `namespace` properties under `spring.cloud.stream.pulsar.binder`.

### Per-binding consumer properties

Example where a consumer load-balances across multiple instances:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: persistent://public/orders/orders
          group: order-processor
      pulsar:
        bindings:
          processOrder-in-0:
            consumer:
              subscription-type: shared
              receiver-queue-size: 100
```

`subscription-type` determines how multiple consumers on the same subscription coordinate. `shared` lets multiple consumers receive messages from the subscription; `exclusive` allows only one active consumer; `failover` allows a standby consumer to take over; `key-shared` distributes by key to preserve affinity of the same key to one consumer per Pulsar semantics.

`receiver-queue-size` tunes how many messages the client can buffer before the application processes them. Too large a buffer can increase memory usage and messages held on the client; too small can hurt throughput. Exact property names and types depend on the binder version, so check the configuration metadata for your version.

When using Pulsar native decoding, the core property `spring.cloud.stream.bindings.<bindingName>.consumer.use-native-decoding` enables decoding at the broker/client. Schema and target data types are declared in the extension namespace, such as `schema-type` and `message-type` under `spring.cloud.stream.pulsar.bindings.<bindingName>.consumer`. On the producer side, corresponding properties exist under `producer`, combined with core `use-native-encoding`. Producer and consumer must agree on the schema; only enable native conversion when both sides understand the same format.

### Per-binding producer properties

A producer can enable batching to group multiple messages into a batch before sending:

```yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: persistent://public/orders/orders
      pulsar:
        bindings:
          publishOrder-out-0:
            producer:
              batching-enabled: true
              batching-max-messages: 100
              batching-max-publish-delay: 10ms
```

Batching can improve throughput and reduce network overhead, but it also increases wait time to accumulate messages. `batching-max-messages` limits the number of messages in a batch; `batching-max-publish-delay` sets the maximum wait delay before sending a batch per the binder property. Balance throughput, latency, and message size.

With the current Pulsar binder, Spring for Apache Pulsar properties can also be set at the application level via `spring.pulsar.producer.*` or at the binder level via `spring.cloud.stream.pulsar.binder.producer.*`. Per-binding extension properties have the highest precedence; the precedence order is extended binding properties, then binder properties, then Spring Boot properties. This allows setting a shared batching default while overriding it for one output binding.

The Pulsar producer can also support compression, send timeout, routing mode, and schema type. Only enable those properties when the corresponding consumer can decode them and schemas on both sides are compatible.

## 6. Comparing property placement across the three binders

The same business requirement can be configured differently depending on the broker. For example, to handle failed messages and avoid letting a consumer hold too many messages, you may need:

| Need | Kafka | RabbitMQ | Pulsar |
|---|---|---|---|
| Share consumer load | Consumer group and partition assignment | Multiple consumers on the same queue | Multiple consumers on the same subscription |
| Limit prefetched data | Kafka client poll/fetch properties | `prefetch` | Receiver queue size |
| Choose acknowledgement mode | Ack mode / offset commit | Acknowledge mode | Ack / negative ack |
| Route failed messages | Dead-letter topic | Dead-letter queue/exchange | Dead-letter policy/topic |
| Tune producer | Kafka producer configuration | Routing, delivery mode, confirms | Batching, routing, compression |
| Provision resources | Topic/partition | Exchange/queue/binding | Tenant/namespace/topic/subscription |

There is no single property that is strictly equivalent across all three brokers. For instance, RabbitMQ's `prefetch` limits unacked messages delivered to a consumer. Kafka's `max.poll.records` caps records returned in a single poll, which is not the same as all data the client fetches or holds in memory. Pulsar's `receiver-queue-size` tunes the consumer client buffer. Understand broker semantics before choosing values.

## 7. Binder level or binding level?

Choose the configuration scope based on how widely the requirement is shared.

### Place at binder level when applying to the whole connection or cluster

Examples:

- Kafka brokers, default TLS/SASL settings, topic auto-create policy.
- RabbitMQ addresses, virtual host, and connection settings.
- Pulsar client/admin endpoints via Spring Boot properties; partition count and producer/consumer defaults via Pulsar binder properties.

If multiple bindings share one cluster and one policy, binder-level configuration avoids duplication.

### Place at binding level when each stream has distinct needs

Examples:

- One Kafka consumer needs `enable-dlq`, while another does not.
- One Rabbit queue needs low prefetch due to heavy processing, while another can accept more messages.
- One Pulsar subscription needs `Key_Shared` to preserve key affinity, while another uses `Shared` to maximize throughput.
- One binding's producer needs batching, while another prioritizes low latency.

Placing a property too broadly can cause a new binding to inherit an unsuitable policy by accident. Conversely, repeating identical settings across every binding makes configuration hard to maintain. Choose binder level for shared defaults and binding level for intentional differences.

### Example with two consumers having different policies

Suppose the same application has two consumers:

- `processOrder-in-0` executes order-update business logic; failures need a DLQ.
- `auditOrder-in-0` writes audit logs; it may need its own concurrency and batching, but should not share a DLQ policy with the business consumer.

Core configuration and extensions:

```yaml
spring:
  cloud:
    function:
      definition: processOrder;auditOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
        auditOrder-in-0:
          destination: orders
          group: order-audit
      kafka:
        binder:
          brokers: kafka.internal:9092
        bindings:
          processOrder-in-0:
            consumer:
              enable-dlq: true
              dlq-name: orders.processor.dlq
          auditOrder-in-0:
            consumer:
              configuration:
                "max.poll.records": 500
```

Both consumers read the same topic but belong to independent groups. Extension properties are configured per binding so the DLQ policy and poll size are not mistakenly applied to the other consumer.

## 8. Combining common and binder-specific properties

A binding typically needs both groups of settings:

1. Core properties define destination, group, and content type.
2. Extension properties define how the binder performs delivery on the broker.

Example:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
          content-type: application/json
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              enable-dlq: true
              dlq-name: orders.dlq
```

If you omit the core part, the binder may not know which destination or logical group to use. If you omit the extension part, the binder uses its defaults. Defaults may suffice for a simple stream, but do not rely on defaults when business requirements involve ordering, durability, retry, dead-lettering, or throughput.

### Avoiding duplicate and conflicting configuration

Do not specify the same intent in multiple places with conflicting values. For instance, concurrency might be declared in core consumer properties or in a binder-specific extension property. If both affect the consumer container, know which one takes precedence in the current version.

When conflicts occur, do not guess from YAML ordering. Check configuration metadata, binder documentation, and startup logs. Some properties are aliases or are translated into client properties; others are container settings and cannot be overridden directly via a Kafka client property.

### Separating configuration per environment

Use Spring profiles or environment variables to separate endpoints and operational parameters across local, test, staging, and production.

Example:

```yaml
spring:
  config:
    activate:
      on-profile: local
  cloud:
    stream:
      kafka:
        binder:
          brokers: localhost:9092
```

In production, endpoints and credentials can be injected from the deployment environment or a secret manager. Never commit passwords, SASL secrets, TLS private keys, or tokens into configuration files. Keep infrastructure configuration separate from source code and restrict access.

## 9. How to find the right extension property

When you need an unfamiliar option, look it up in order:

1. Identify the binding's actual binder via its `binder` property or the default binder.
2. Determine whether the property belongs to the binder level, consumer, or producer.
3. Consult the exact documentation for the binder and dependency version in use.
4. Check the property name in configuration metadata or IDE completion.
5. Verify whether the property belongs to the Spring Cloud Stream binder or the broker client library.
6. Confirm valid values, time units, data types, and defaults.
7. Write an integration test or inspect the broker to verify actual impact.

Do not copy a property from an article targeting a different version without checking. Spring Cloud Stream and binders can change property names, types, defaults, or mapping behavior across versions.

### Distinguishing binder properties from client properties

Some settings are abstractions defined by the binder, such as `enable-dlq` in the Kafka binder or `auto-bind-dlq` in the Rabbit binder. They can trigger multiple operations in the binder/provisioner rather than being a single native client property.

Other settings are passed straight through to the client, such as `max.poll.records` for a Kafka consumer or `acks` for a Kafka producer. These properties are usually placed in the `configuration` map under the corresponding client scope.

With RabbitMQ and Pulsar, many extension properties are mapped by the binder to client APIs or container configuration. Not every property of the Rabbit Java Client or Pulsar client is exposed by the binder through a generic map. Check the binder's extension properties before assuming any option can be passed through.

## 10. Common mistakes when configuring namespaces

**Putting extension properties into the core namespace.** For example, putting `enable-dlq` directly under `spring.cloud.stream.bindings`. Core will not recognize this property. Place it in the Kafka binder namespace under the `consumer` branch.

**Confusing `binder` with `bindings`.** `binder` configures the binder instance or cluster; `bindings` configures per-binding extensions by binding name. Being off by one namespace level can prevent a property from binding.

**Putting a consumer property on a producer.** `max.poll.records` does not control a producer; `routing-key-expression` has no meaning on an input binding. Always verify the binding direction before configuring.

**Using the wrong binder namespace.** `spring.cloud.stream.kafka.bindings` does not configure RabbitMQ or Pulsar. If a binding uses the Rabbit binder, use the Rabbit namespace.

**Putting client properties in the wrong place.** Kafka `acks` belongs to the producer; `isolation.level` belongs to the consumer. Placing one in the wrong branch can cause the client to ignore it or fail at startup.

**Assuming identically named properties mean the same thing.** A property with the same name across two binders can have different units, defaults, or semantics. Compare documentation and runtime behavior, not just string names.

**Not checking auto-provisioned resources.** A topic, queue, or subscription might be created with undesired partitions, retention, DLQ, or routing. Inspect broker metadata after the application boots.

**Not checking properties against your version.** A property may be newly introduced, deprecated, or have changed types. Align your Spring Cloud release train, Spring Cloud Stream, and binder dependency versions before applying it.

## 11. Testing and verifying configuration

A YAML file parsing cleanly does not prove the binder applied the property. Testing should verify both binding metadata and broker behavior.

### Verifying bound configuration

You can use Spring Boot Actuator configuration properties or condition/configuration diagnostics in a secure environment to verify loaded properties. Be careful not to expose endpoints or secret values publicly. Binder startup logs often show destination, group, and partial connection details; avoid enabling overly verbose logging in production if it could expose credentials.

### Testing with a real broker

With Kafka, inspect topics, partitions, consumer groups, committed offsets, and dead-letter topics. Emit an intentional failing message to verify the DLQ is used per configuration; then inspect the original message and error metadata.

With RabbitMQ, inspect exchanges, queues, bindings, routing keys, consumer count, unacked count, and dead-letter queues. Try interrupting a consumer mid-processing to verify acknowledgement and redelivery.

With Pulsar, inspect tenant, namespace, topic, subscription type, backlog, and acknowledgement state. Start multiple consumers in the same subscription to verify how the chosen subscription type distributes load.

### Suggested verification matrix

| Configuration change | What to observe |
|---|---|
| Change Kafka `max.poll.records` | Records returned per poll and processing impact |
| Enable Kafka DLQ | Error topic created/routed and receives failed records |
| Change Rabbit `prefetch` | Maximum unacked messages delivered ahead to consumer |
| Enable Rabbit auto-bind DLQ | Dead-letter queue/exchange and routing key created properly |
| Change Pulsar subscription type | Active consumer count and how messages are distributed |
| Enable Pulsar batching | Throughput, batch size, and publish latency |
| Change binder-level endpoint | Binding connects to the right cluster or namespace |
| Change binding-level property | Only the specified binding receives that policy |

Spring Cloud Stream's test binder is useful for function logic and framework-level binding flows, but it does not replace integration tests when verifying offsets, queues, subscriptions, DLQs, acknowledgements, or real client configuration.

## 12. Process for selecting extension properties

When tuning a binding, answer in order:

1. Does the binding use Kafka, RabbitMQ, or Pulsar? Confirm the binder alias and dependency.
2. Does the property belong to general connection settings, consumer, or producer?
3. Does the policy apply to the whole cluster/binder or only one binding?
4. Does a core property satisfy the requirement, or is an extension property needed?
5. Does the property belong to the binder or the client library? Place it in the right namespace and branch.
6. What are the valid values, units, defaults, and version compatibility?
7. Do broker resources need to be created or modified?
8. Which test proves the binder applied the configuration?
9. Which metrics or broker UI will confirm post-deployment behavior?

A good configuration makes boundaries explicit: common properties describe destination and group; extension namespaces describe how the binder implements delivery; broker client properties tune details where the binder permits. Once you understand these three layers, you can tune Kafka, RabbitMQ, and Pulsar while keeping the application's event-processing code readable, testable, and maintainable.

## References

- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Cloud Stream — RabbitMQ Binder Reference Guide](https://docs.spring.io/spring-cloud-stream-binder-rabbit/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html)
- [Spring Cloud Stream — Binder for Apache Pulsar](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html)
- [Spring for Apache Pulsar — Reference Documentation](https://docs.spring.io/spring-pulsar/reference/)
