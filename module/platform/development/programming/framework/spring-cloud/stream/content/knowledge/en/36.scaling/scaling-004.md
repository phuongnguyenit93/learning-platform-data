# Customizing Binders in Multi-Binder Applications

Spring Cloud Stream allows a single application to use multiple middleware technologies simultaneously: consuming events from Kafka, processing them with a `Function`, and publishing to RabbitMQ or Pulsar; or reading from two separate Kafka clusters without rewriting the broker connection layer. Such a setup is called a **multi-binder application**.

When there is only one binder, Spring Cloud Stream usually discovers it on the classpath automatically, and many customization beans in the application context can be picked up directly by the binder. When there are **multiple binders**—especially multiple instances of the same binder type connecting to different clusters—you must make explicit:

- Which binding is attached to which binder?
- Which connection, credentials, and broker configuration does that binder use?
- Does a customization bean apply to all binders or only a single instance?
- Why does a bean in the main application context not automatically appear inside each binder's own context?
- What delivery guarantees apply when forwarding events from broker A to broker B?
- How do you prove no binding accidentally talks to the wrong broker?

This lesson focuses on three mechanisms: **selecting a binder per binding**, **declaring named binders with isolated environments**, and **using `BinderCustomizer` to customize a binder before it is used**. Examples use Spring Cloud Stream's `Supplier`/`Function`/`Consumer` model, Kafka, RabbitMQ, and Pulsar, while highlighting the Kafka Streams binder exception. This knowledge applies when scaling a system into multiple flows and brokers, not just when increasing replica counts.

## 1. Three Concepts to Distinguish

| Concept | Meaning | Example |
|---|---|---|
| Function bean | Business logic transforming data | `bridgeOrder` |
| Binding | Input/output port of a function | `bridgeOrder-in-0`, `bridgeOrder-out-0` |
| Destination | Topic/exchange/topic URI on the broker | `orders.created`, `orders.enriched` |
| Binder type | Implementation connecting to a middleware type | `kafka`, `rabbit`, `pulsar` |
| Named binder configuration | A named binder configuration | `ordersKafka`, `notificationsRabbit` |
| Binder instance | The actual binder created and used by the framework | `KafkaMessageChannelBinder` connecting to cluster A |
| `BinderCustomizer` | Java callback customizing a binder instance before bindings use it | Attaching a Kafka rebalance listener to `ordersKafka` |

The **binder configuration** name can differ from the **binder type**. For instance, `ordersKafka` and `auditKafka` both have `type: kafka` but point to two different Kafka clusters. The configuration name distinguishes the two instances.

An application can have multiple bindings while still using one binder; for example, two Kafka inputs and one Kafka output are still one binder type and can share one binder instance. Conversely, a single `Function` with two bindings becomes multi-binder if its input uses Kafka and its output uses RabbitMQ.

## 2. Diagram: One Function Bridging Two Brokers

~~~text
            Spring Boot / Spring Cloud Stream
  +----------------------------------------------------+
  |                                                    |
  | Kafka binder: ordersKafka                          |
  |   binding: bridgeOrder-in-0                         |
  |               |                                    |
  |               v                                    |
  |        Function<OrderCreated, OrderForwarded>      |
  |               |                                    |
  |               v                                    |
  | Rabbit binder: notificationsRabbit                  |
  |   binding: bridgeOrder-out-0                        |
  |                                                    |
  +-----------------^-----------------+----------------+
                    |                 |
                    |                 v
               Kafka cluster     RabbitMQ broker
               orders.created    orders.forwarded
~~~

This path is purely a logical pipeline. There is no automatic distributed transaction committing the Kafka offset and publishing to RabbitMQ atomically. When choosing a multi-binder topology, design for idempotency, retries, and destination-broker failure scenarios rather than declaring two binders and assuming exactly-once processing.

## 3. Adding the Right Dependencies for the Binders Used

Maven example for an application needing Kafka and RabbitMQ:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-binder-kafka</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-binder-rabbit</artifactId>
  </dependency>
</dependencies>
~~~

If the Pulsar binder is needed:

~~~xml
<dependency>
  <groupId>org.springframework.cloud</groupId>
  <artifactId>spring-cloud-stream-binder-pulsar</artifactId>
</dependency>
~~~

If the topology processes `KStream`/`KTable`, the Kafka Streams binder dependency is chosen separately:

~~~xml
<dependency>
  <groupId>org.springframework.cloud</groupId>
  <artifactId>spring-cloud-stream-binder-kafka-streams</artifactId>
</dependency>
~~~

Use a Spring Cloud BOM compatible with your project's Spring Boot version to manage dependency versions. Do not mix incompatible binder versions merely because the artifacts share the `spring-cloud-stream` prefix.

Having multiple implementations on the classpath means the application must explicitly choose a binder for each binding or set an appropriate `defaultBinder`. Adding dependencies does not automatically infer that input should be Kafka and output should be RabbitMQ according to business intent.

## 4. Example Function Bridging Kafka Events to RabbitMQ

A pure function can remain unchanged regardless of which binder is chosen:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderBridgeFunctions {

    public record OrderCreated(
        String eventId,
        String orderId,
        long amount
    ) {}

    public record OrderForwarded(
        String eventId,
        String orderId,
        String status
    ) {}

    @Bean
    Function<OrderCreated, OrderForwarded> bridgeOrder() {
        return event -> new OrderForwarded(
            event.eventId(),
            event.orderId(),
            "RECEIVED"
        );
    }
}
~~~

Spring Cloud Stream generates default binding names:

~~~text
bridgeOrder-in-0    -- Function input
bridgeOrder-out-0   -- Function output
~~~

The function above does not need to call `KafkaConsumer`, `RabbitTemplate`, or `PulsarClient`. The framework creates input/output adapters and handles message conversion according to the configured content type.

Basic configuration when there is only one Kafka binder and one Rabbit binder on the classpath:

~~~yaml
spring:
  cloud:
    function:
      definition: bridgeOrder
    stream:
      bindings:
        bridgeOrder-in-0:
          destination: orders.created
          group: order-bridge-v1
          binder: kafka
          content-type: application/json
        bridgeOrder-out-0:
          destination: orders.forwarded
          binder: rabbit
          content-type: application/json
~~~

`binder` is a **binding** property, whereas `destination` is a broker resource. Setting `binder: rabbit` does not turn `orders.forwarded` into a queue name; with the RabbitMQ binder, the destination is typically an exchange and `group` determines the receiving queue. Check the specific binder's mapping rules.

Using the binder type name directly works when there is only one instance of each type and connection properties are configured at the application level. For multiple clusters or configuration isolation, switch to named binders.

## 5. Global defaultBinder vs. Per-Binding Binder

There are two ways to select an implementation:

~~~yaml
spring:
  cloud:
    stream:
      default-binder: kafka
~~~

`defaultBinder` is used for bindings that do not declare their own `binder`. An individual binding configuration can override it:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        bridgeOrder-out-0:
          binder: rabbit
~~~

Rules:

1. A binding with its own `binder` uses that binder.
2. A binding without `binder` uses the default binder if one is configured or uniquely resolved.
3. If multiple binders exist without a unique selection, the application may fail to create the intended binding and report an ambiguous configuration.
4. Do not let a default binder silently decide the route of critical events.

In production, for architectures whose inputs and outputs span different middleware, specify `binder` **explicitly on every binding** so the configuration is easy to review, especially when adding new binder dependencies.

`default-binder` is the kebab-case form of `spring.cloud.stream.defaultBinder` in Spring Boot configuration. Documentation may show camelCase; depending on property binding, use the form supported by your deployed release.

## 6. Naming Binder Configurations Explicitly

To define binders explicitly, use:

~~~text
spring.cloud.stream.binders.<configuration-name>
~~~

A binder configuration has these main fields:

| Field | Effect |
|---|---|
| `type` | Binder type registered via `META-INF/spring.binders` metadata |
| `environment` | Properties used in the isolated context when creating the binder |
| `inheritEnvironment` | Whether to inherit the main application's environment; defaults to `true` |
| `defaultCandidate` | Whether to participate in default binder selection; defaults to `true` |

Simple example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        bridgeOrder-in-0:
          destination: orders.created
          binder: ordersKafka
        bridgeOrder-out-0:
          destination: orders.forwarded
          binder: notificationsRabbit

      binders:
        ordersKafka:
          type: kafka
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: kafka-orders:9092
        notificationsRabbit:
          type: rabbit
          environment:
            spring:
              rabbitmq:
                host: rabbit-notifications
                port: 5672
                virtual-host: orders
~~~

Name relationships:

~~~text
bridgeOrder-in-0.binder   = ordersKafka
binders.ordersKafka.type  = kafka

bridgeOrder-out-0.binder  = notificationsRabbit
binders.notificationsRabbit.type = rabbit
~~~

When `spring.cloud.stream.binders` is declared explicitly, Spring Cloud Stream **disables automatic default binder configuration**. Therefore, every binder the application uses must be declared under `binders`. Do not declare one custom binder and expect a second binder to always appear automatically via classpath detection.

## 7. Dedicated Environment per Broker

Each binder can use an `environment` containing the relevant Spring Boot and Spring Cloud Stream properties.

More complete example:

~~~yaml
spring:
  cloud:
    function:
      definition: bridgeOrder

    stream:
      bindings:
        bridgeOrder-in-0:
          destination: orders.created
          group: order-bridge-v1
          binder: ordersKafka
          content-type: application/json
        bridgeOrder-out-0:
          destination: orders.forwarded
          binder: notificationsRabbit
          content-type: application/json

      binders:
        ordersKafka:
          type: kafka
          inherit-environment: false
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: ${KAFKA_ORDERS_BROKERS:localhost:9092}
                      auto-create-topics: false

        notificationsRabbit:
          type: rabbit
          inherit-environment: false
          environment:
            spring:
              rabbitmq:
                host: ${RABBIT_HOST:localhost}
                port: ${RABBIT_PORT:5672}
                virtual-host: ${RABBIT_VHOST:orders}
                username: ${RABBIT_USER}
                password: ${RABBIT_PASSWORD}
~~~

Explanation:

- `type` selects the implementation, not the broker address.
- `environment.spring.cloud.stream.kafka.binder.brokers` configures brokers for the named Kafka binder.
- `environment.spring.rabbitmq.*` configures RabbitMQ connectivity within that binder context.
- `inherit-environment: false` prevents the binder from inheriting unwanted global environment properties; in that case you must supply all required properties, including connectivity and security.
- Environment variables merely illustrate externalizing secrets/hosts; production should use a secrets manager and proper access controls.

Some setups use `inheritEnvironment` instead of `inherit-environment`; both map to the same `BinderProperties` field. Before rollout, verify bound properties and configuration/metadata endpoints for your project version.

**Security note:** `inheritEnvironment=false` separates properties, but is not a strict security sandbox. Binders still execute in the same JVM/process, sharing CPU/RAM and application-managed components. It does not replace IAM and network isolation.

## 8. Two Kafka Clusters with the Same Binder Type

A common scenario: an application reads from production cluster A and writes to analytics cluster B.

~~~text
Kafka A                              Kafka B
orders.created --- input Function --- orders.enriched
    |                                      |
    +-- ordersKafka                        +-- analyticsKafka
        type=kafka                             type=kafka
        brokers=kafka-a                        brokers=kafka-b
~~~

Configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: enrichOrder

    stream:
      bindings:
        enrichOrder-in-0:
          destination: orders.created
          group: order-enricher-v1
          binder: ordersKafka
        enrichOrder-out-0:
          destination: orders.enriched
          binder: analyticsKafka

      binders:
        ordersKafka:
          type: kafka
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: kafka-a:9092

        analyticsKafka:
          type: kafka
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: kafka-b:9092
~~~

Two distinct named binders exist even though both have `type: kafka`. This is why `BinderCustomizer` receives both `binder` and `binderName`: checking `KafkaMessageChannelBinder` by class alone cannot distinguish cluster A from cluster B.

Forwarding records across two Kafka clusters does not automatically create an atomic cross-cluster transaction. If output has been sent while the source offset has not yet committed, the record can be redelivered. Design an idempotent downstream or a bridge strategy with appropriate delivery guarantees.

## 9. defaultCandidate: Should a Binder Be Considered Default?

Optional configuration:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        auditKafka:
          type: kafka
          default-candidate: false
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: kafka-audit:9092
~~~

`default-candidate: false` means this binder is **only used when explicitly referenced**, and does not participate in default binder selection. This is useful when adding a secondary binder for observability or dynamic use without changing the application's default binder.

This does not disable the binder: bindings specifying `binder: auditKafka` can still use it. If all binders in the application are non-default candidates, every binding must specify a name explicitly.

Do not use `defaultCandidate=false` to isolate credentials or guarantee a broker is never connected to. It only affects binder selection.

## 10. Three-Tier Configuration Table

Mental model for configuration order:

| Tier | Prefix | Scope |
|---|---|---|
| Function/Binding | `spring.cloud.stream.bindings.<name>` | Sets destination/group/binder for one binding |
| Binder instance | `spring.cloud.stream.binders.<name>` | Selects type, environment, isolation, and `defaultCandidate` |
| Binder-specific | Inside binder environment or `spring.cloud.stream.<type>.bindings.<name>` | Configures extended Kafka/Rabbit/Pulsar properties |

Kafka example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        bridgeOrder-in-0:
          destination: orders.created
          group: order-bridge-v1
          binder: ordersKafka
          consumer:
            concurrency: 2

      kafka:
        bindings:
          bridgeOrder-in-0:
            consumer:
              ack-mode: RECORD
~~~

Here `concurrency` is a generic binding property, whereas `ack-mode` is a Kafka extended consumer property. `ack-mode` does not carry the same meaning in RabbitMQ or Pulsar and is not declared under `spring.cloud.stream.bindings.*.consumer` as a generic field.

In applications with multiple instances of the **same binder type**, do not blindly assume an extended property placed in the main application context stays isolated per cluster. Check precedence and applicability in your binder version. Connection properties and shared settings that differ across clusters belong inside `binders.<name>.environment`; customizing the `Binder` object itself should filter by `binderName`.

## 11. Why Might a Customization Bean Not Reach the Binder?

In a single-binder application, the binder can usually see customization beans in the main context. In a multi-binder application, however, Spring Cloud Stream can create each binder in its **own application context**. Beans such as a Kafka rebalance listener, Rabbit listener-container customizer, or dedicated configuration are not necessarily auto-discovered inside each binder context.

~~~text
Main application context
  |
  +-- @Bean Function
  +-- @Bean BinderCustomizer
  +-- @Bean MyKafkaRebalanceListener
  |
  +--> Binder context: ordersKafka
  |       +-- KafkaMessageChannelBinder
  |
  +--> Binder context: analyticsKafka
  |       +-- KafkaMessageChannelBinder
  |
  +--> Binder context: notificationsRabbit
          +-- RabbitMessageChannelBinder
~~~

`BinderCustomizer` solves this via a callback invoked by Spring Cloud Stream **before the binder is used**. The callback receives the `Binder` instance and configuration name, allowing you to inspect type/name and register the corresponding customization.

Do not confuse this with ordinary `@Configuration`: placing a bean in the main context does not automatically mean every isolated binder context uses that bean.

## 12. Using BinderCustomizer Across Multiple Binders

Spring Cloud Stream provides the `org.springframework.cloud.stream.binder.BinderCustomizer` interface:

~~~java
void customize(
    Binder<?, ? extends ConsumerProperties, ? extends ProducerProperties> binder,
    String binderName
);
~~~

When registering the bean, you can use a lambda:

~~~java
import org.springframework.cloud.stream.binder.BinderCustomizer;
import org.springframework.cloud.stream.binder.kafka.KafkaMessageChannelBinder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MultiBinderCustomization {

    @Bean
    BinderCustomizer binderCustomizer(
            OrdersRebalanceListener ordersListener) {

        return (binder, binderName) -> {

            if ("ordersKafka".equals(binderName)
                    && binder instanceof KafkaMessageChannelBinder kafka) {
                kafka.setRebalanceListener(ordersListener);
            }

            // analyticsKafka is also a KafkaMessageChannelBinder
            // but does NOT receive the listener meant only for ordersKafka.
        };
    }
}
~~~

`OrdersRebalanceListener` here is an application-defined class implementing `KafkaBindingRebalanceListener`. The next section illustrates the implementation.

Rules:

- **Check the type** before casting or calling binder-specific APIs.
- **Check the name** if multiple instances share the same type.
- Call only the necessary APIs without altering out-of-scope binders.
- The callback runs at binder configuration time; do not use it to process business messages.
- Avoid slow operations, arbitrary HTTP calls, or dynamic secret fetching inside the startup callback.
- Do not assume `BinderCustomizer` can be re-run to swap connections while the binder is processing; changing config at runtime typically requires a restart or rebind.

## 13. Example KafkaBindingRebalanceListener Selected by binderName

Example listener that only logs partition assignments without arbitrarily seeking offsets:

~~~java
import java.util.Collection;

import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.clients.consumer.Consumer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.stream.binder.kafka.KafkaBindingRebalanceListener;
import org.springframework.stereotype.Component;

@Component
public class OrdersRebalanceListener
        implements KafkaBindingRebalanceListener {

    private static final Logger log =
        LoggerFactory.getLogger(OrdersRebalanceListener.class);

    @Override
    public void onPartitionsAssigned(
            String bindingName,
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions,
            boolean initial) {

        log.info(
            "binding={} initial={} partitions={}",
            bindingName,
            initial,
            partitions
        );
    }
}
~~~

Combining this class with the `BinderCustomizer` from the previous section gives `ordersKafka` the designated listener, while `analyticsKafka` does not get the same logic.

**Warning on seek/reset:** Kafka binder docs disallow using `resetOffsets=true` together with a rebalance listener. If a listener performs seeks for replay, control seek counts and groups/partitions carefully to avoid re-reading history on every rebalance.

If a listener bean is already discovered by a binder via context inheritance, do not attach the listener twice through two mechanisms without verifying behavior. In multi-binder setups, keep one clear registration point and verify with integration tests.

## 14. BinderCustomizer Is Not ListenerContainerCustomizer

The two mechanisms have different scopes:

| Mechanism | Target affected | When to use |
|---|---|---|
| `BinderCustomizer` | Binder instance selected by type/name | Passing Java configuration to a binder in a multi-binder context |
| `ListenerContainerCustomizer` | Specific message listener container | Tuning the container for a destination/group |
| Kafka consumer/producer config customizer | Kafka client config map | Overriding client properties per binding/topic |
| `spring.cloud.stream.bindings.*` | Binding properties | Changing destination/group/concurrency/content type |
| `binders.<name>.environment` | Binder environment/context | Isolating brokers, hosts, and credentials |

If a declarative property exists, **prefer YAML**. If you need to customize a listener container by destination/group, use that binder's extension point. In multi-binder setups, that bean may need to be placed in the binder context or attached via an API supported by `BinderCustomizer`. Do not try to use `BinderCustomizer` as a router for events.

In a Kafka + RabbitMQ application, never cast `RabbitMessageChannelBinder` to `KafkaMessageChannelBinder`. APIs like rebalance listeners only make sense for Kafka consumers.

## 15. When You Need Dedicated Configuration Classes in a Binder Environment

Besides `BinderCustomizer`, each binder environment can declare its own configuration sources using `spring.main.sources`:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        ordersKafka:
          type: kafka
          environment:
            spring:
              main:
                sources: com.example.stream.config.OrdersBinderOnlyConfig
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: kafka-orders:9092
~~~

This is an extension point for adding beans/configuration to a named binder context. Be very careful:

- `OrdersBinderOnlyConfig` must exist on the classpath.
- Avoid letting the main application context component-scan that class and register duplicate beans.
- Do not define beans with the same names as framework configurations unintentionally.
- Verify lifecycle, context scope, and bean dependencies.
- For simple needs, a `BinderCustomizer` in the main context is usually easier to understand.

`spring.profiles.active` can be set inside a binder environment to activate dedicated profiles. However, if profiles alter connection/auth settings differently, test actual startup to ensure one binder's config does not leak into another.

## 16. StreamBridge in Multi-Binder Applications

`StreamBridge` is used when the application must send messages from an HTTP handler, scheduler, or callback that is not directly a function's output.

Example:

~~~java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;

@Service
public class AuditPublisher {

    private final StreamBridge streamBridge;

    public AuditPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(String json) {
        return streamBridge.send(
            "audit-out-0",
            "auditKafka",
            json
        );
    }
}
~~~

The overload with the second parameter `binderName` allows choosing a binder when creating a **dynamic binding**. This differs from `send(bindingName, data)`, which relies on a default binder or an already configured binding.

However, Spring Cloud Stream docs note: **if the output binding already exists or was created via `spring.cloud.stream.output-bindings`, the `binderName` argument on a new send will not change that binding's binder**. Therefore, for fixed-name outputs, the clearest approach is configuring binder and destination directly in YAML:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        audit-out-0:
          destination: audit.events
          binder: auditKafka
          content-type: application/json
~~~

Do not send `audit-out-0` to broker A in one request and expect the same binding to switch to broker B in the next. To target two destinations, declare two separate bindings/destinations and call `StreamBridge.send` with distinct binding names.

## 17. Example: Supplier and Consumer Using Different Binders

It is not only a `Function` that can span multiple binders; an application can have independent function beans:

~~~java
import java.time.Instant;
import java.util.function.Consumer;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OperationsFunctions {

    @Bean
    Supplier<String> heartbeat() {
        return () -> "alive-" + Instant.now();
    }

    @Bean
    Consumer<String> auditEvent() {
        return message -> {
            // Write audit log or invoke business service.
        };
    }
}
~~~

Configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: heartbeat;auditEvent

    stream:
      bindings:
        heartbeat-out-0:
          destination: system.heartbeat
          binder: auditKafka
        auditEvent-in-0:
          destination: persistent://acme/audit/events
          group: audit-reader-v1
          binder: auditPulsar
~~~

This example assumes `auditKafka` and `auditPulsar` are declared under `binders` with the right types and broker environments. `heartbeat` is a pollable `Supplier`; its emission schedule is driven by Spring Cloud Stream's poller/scheduling rather than inferred from instance counts.

When independent functions use multiple binders, they are not automatically chained together. A `Consumer` has no output binding and a `Supplier` has no input binding. Placing them in the same process does not create a shared transaction or retry scope.

## 18. Pulsar Binder: Binder-Level and Binding-Level Properties

The Pulsar binder builds on Spring for Apache Pulsar, so shared Spring Boot properties exist such as:

~~~text
spring.pulsar.client.service-url
spring.pulsar.consumer.*
spring.pulsar.producer.*
~~~

Additionally, the Pulsar binder provides:

~~~text
spring.cloud.stream.pulsar.binder.consumer.*
spring.cloud.stream.pulsar.binder.producer.*

spring.cloud.stream.pulsar.bindings.<input>.consumer.*
spring.cloud.stream.pulsar.bindings.<output>.producer.*
~~~

Pulsar binder docs describe the precedence order:

~~~text
Extended binding properties
    > Pulsar binder properties
    > Spring Boot Pulsar properties
~~~

Example specifying subscription type for a particular input:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        auditEvent-in-0:
          destination: persistent://acme/audit/events
          group: audit-reader-v1
          binder: auditPulsar

      pulsar:
        bindings:
          auditEvent-in-0:
            consumer:
              subscription:
                type: Shared
                mode: Durable
~~~

When an application has multiple Pulsar functions, declare extended binding settings to avoid unintentionally applying the same subscription configuration to every consumer.

If you have **multiple Pulsar clusters** and named binders, place the service URL and connection details in each named binder's environment; do not use a single global URL and expect the two clusters to stay separate.

## 19. Kafka Streams Binder Is a Special Case

The regular Kafka binder uses `KafkaMessageChannelBinder` for message channels, whereas the Kafka Streams binder targets `KStream`, `KTable`, `GlobalKTable`, and stateful topologies.

Therefore, when a multi-binder app includes both Kafka Streams and regular Kafka:

- Do not cast the Kafka Streams binder to the regular Kafka binder.
- Do not apply a regular Kafka binder rebalance listener to a Kafka Streams topology.
- Separate `application.id` and cluster configuration per topology.
- Verify the exact binder types registered in `META-INF/spring.binders`, especially when combining `kstream`, `ktable`, and `globalktable` in complex multi-binder setups.
- State stores, internal changelog/repartition topics, and Kafka Streams lifecycle have their own constraints.

Illustrative Kafka Streams function:

~~~java
@Bean
Function<KStream<String, String>, KStream<String, String>> normalize() {
    return input -> input.mapValues(String::trim);
}
~~~

When Kafka Streams binder types coexist with the regular Kafka binder, select `binder` for each binding according to the mapping published by your binder family's release. Do not take a regular binder `type: kafka` example and apply it to a `KStream` input.

Changing the broker or `application.id` of Kafka Streams can create a new state/changelog namespace and consumer group, causing input replays. Never treat it as merely changing a broker address.

## 20. Multiple Binders Do Not Imply Distributed Transactions

Consider these steps:

~~~text
1. Kafka consumer receives OrderCreated.
2. Function produces OrderForwarded.
3. Rabbit publisher sends the message successfully.
4. Kafka consumer commits offset.
~~~

If the JVM crashes **after step 3 but before step 4**, Kafka can redeliver `OrderCreated` after restart and Rabbit will receive a duplicate `OrderForwarded`. If the application acks Kafka too early before Rabbit publishing is confirmed, outbound events can be lost.

Guarantees to distinguish:

| Property | Meaning |
|---|---|
| Kafka consumer group offset | Position from which the consumer group resumes reading |
| Rabbit publisher confirm | Broker confirmation of publish per configured assurance level |
| Pulsar producer send acknowledgment | Publish acknowledgment per client/broker |
| Function invocation | Java logic ran; does not prove all side effects committed |
| Cross-broker atomicity | Not automatically provided by Spring Cloud Stream merely from having two `binder`s |

Do not promise end-to-end exactly-once across Kafka → RabbitMQ → PostgreSQL solely via `binder` configuration or a Kafka client's `transactional.id`.

Options:

- **Idempotent consumer:** receive duplicate messages while applying side effects only once per event ID.
- **Transactional outbox:** commit state alongside an outbox record in a database transaction, then let a separate publisher dispatch messages.
- **Inbox/deduplication:** store processed message IDs per consumer group/domain.
- **Saga/compensation:** handle multi-step stateful workflows with compensating actions.
- **Retry + DLQ:** recover from transient errors and quarantine poison records once retries exhaust.

Pick a strategy and verify it with failure injection; this is an essential part of multi-binder design, not an optional optimization.

## 21. Conversion and Schemas Across Two Middleware Systems

Spring Cloud Stream provides content-type conversion, yet brokers differ in headers, keys, and serializers.

Example with a Function from Kafka to RabbitMQ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        bridgeOrder-in-0:
          content-type: application/json
          binder: ordersKafka
        bridgeOrder-out-0:
          content-type: application/json
          binder: notificationsRabbit
~~~

This is only the high-level contract. Verify:

1. Input Kafka record serializer/deserializer, key, and header mapping.
2. Function receives the DTO or `Message<DTO>` with the expected type.
3. Output Rabbit serializer/header mapping is compatible with downstream consumers.
4. Fields `eventId`, `schemaVersion`, and `correlationId` are preserved or freshly generated validly.
5. Tombstones, null payloads, schema evolution, timestamps, and ordering are handled properly.

If using `useNativeDecoding`/`useNativeEncoding`, the binder may skip normal content-type conversion. You must supply appropriate serializers/Serdes on the binder and test real payloads on the target broker.

Do not assume that using JSON on both ends automatically preserves every Kafka header into RabbitMQ or Pulsar. Header mappers and how each broker encodes metadata can differ.

## 22. Consumer Groups and Subscriptions When Switching Binders

The meaning of `group` depends on the binder:

| Binder | `group` typically maps to |
|---|---|
| Kafka | Kafka consumer group ID |
| RabbitMQ | Queue created/bound by the binder for destination + group |
| Pulsar | Subscription identity |
| Kafka Streams | `application.id` managing group and state, with its own rules |

For example, `group: order-bridge-v1` in Kafka is not a shared group with Rabbit or Pulsar. Two middleware systems maintain separate checkpoint/backlog mechanisms.

If migrating an input binding from Kafka to RabbitMQ while keeping the same group string, nothing automatically translates Kafka offsets into Rabbit queue ack states. Migration requires:

- Defining a cutover point.
- Deciding on dual-write, replay, or backfill.
- Checking duplicate handling/idempotency.
- Isolating outputs to avoid double publishing.
- Measuring backlog and acknowledgments on both brokers.
- Having a rollback and old-resource cleanup plan.

## 23. Security and Least-Privilege Permissions per Binder

A process containing multiple binders holds multiple connections and credentials. Whenever possible, separate service identities per broker:

~~~text
ordersKafka         -> Kafka principal: orders-bridge-consumer
notificationsRabbit -> Rabbit user:    orders-bridge-publisher
auditPulsar         -> Pulsar role:    audit-publisher
~~~

The Kafka identity has Read only on the input topic and group. The Rabbit user has Write only on the output exchange when not auto-provisioning; the Pulsar publisher has Produce only on the required topic/namespace.

Never put one superuser credential across all binder contexts. In particular, auto-provisioning topics/queues/exchanges may require Create/Configure permissions. In production, provision resources via infrastructure pipelines and run workloads with minimal runtime permissions.

If a binder context has `inheritEnvironment=true`, assess the risk of global connection/credential properties applying unintentionally. For distinct brokers, prefer declaring secrets explicitly under each named binder and verifying in integration tests.

Do not expose Actuator binding/config endpoints publicly: they can leak hosts, connection metadata, or security parameters if unsanitized.

## 24. Scaling Individual Bindings vs. Scaling the Whole Application

A single Spring Boot process can simultaneously host:

- A Kafka consumer input.
- A Rabbit producer output.
- A second Pulsar consumer input.
- A dedicated Kafka Streams topology.

When increasing process replicas, **every binding is replicated**. This increases Kafka consumers, Rabbit producer connections, and Pulsar subscription consumers simultaneously, even if only one branch needs extra capacity.

For instance, if the Kafka input has 6 partitions, the Rabbit output handles fixed load, and Pulsar `Key_Shared` requires key ordering, scaling pods from 2 to 8 does not linearly boost throughput on each branch; it can also inflate client connections or leave Kafka consumers idle without partitions.

Before scaling a multi-binder application:

1. Measure lag/backlog per binding and broker.
2. Pinpoint bottlenecks by function, partition, or downstream dependency.
3. Check concurrency/`instanceCount` against partition counts, queues, and subscription types.
4. Estimate total connections and memory if the whole process scales out.
5. Consider splitting into two applications when branches have different SLOs or scaling cadences.
6. Test failover and rebalancing when scaling replicas up or down.

Binder customization organizes configuration, but does not replace independent scaling architecture.

## 25. Observing Binding and Broker State

In production, enable Actuator and Micrometer alongside broker-specific metrics.

Example exposing the bindings endpoint:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,bindings,metrics
~~~

Requires Spring Boot Actuator and Web/WebFlux dependencies. Endpoints:

~~~text
GET /actuator/bindings
GET /actuator/bindings/{bindingName}
~~~

You can verify:

- Has `bridgeOrder-in-0` bound to `ordersKafka`?
- Has `bridgeOrder-out-0` bound to `notificationsRabbit`?
- Are inputs running?
- What are Kafka lag per group/partition, rebalances, and retries?
- What are Rabbit publisher confirms, queue backlog, nacks, and connections/channels?
- What are Pulsar subscription backlog, unacked counts, and redeliveries?

Do not rely solely on overall app health `UP`: one broker may be impaired while another function keeps processing. Each binder's health indicator and broker metrics must be cross-checked along each business path. The bindings endpoint may not show full credential/type details; broker-side tools provide stronger verification.

## 26. Testing with the Test Binder and Real Brokers

Use `spring-cloud-stream-test-binder` to test function transformations and basic wiring in the JVM. It is great for `OrderCreated -> OrderForwarded` logic, but **does not prove** messages actually travel from Kafka cluster A to Rabbit broker B.

Test layers:

| Layer | Objective |
|---|---|
| Function unit test | DTO mapping, validation, schema rules |
| Test binder | Input/output function binding inside the JVM |
| Two-broker integration test | Real Kafka input, real Rabbit output, credentials, and routing |
| Two-Kafka-cluster integration test | Binders `ordersKafka` vs. `analyticsKafka` are not mixed up |
| Failure injection | Kafka down, Rabbit down, publish succeeds / offset commit fails |
| Scale test | Replicas, group assignments, and per-broker backlog |

An integration test for Kafka → Rabbit:

1. Start one Kafka Testcontainer and one RabbitMQ Testcontainer.
2. Supply dynamic host/port properties to `ordersKafka` and `notificationsRabbit` (e.g., via Spring test properties).
3. Grant exact ACL/vhost permissions; pre-create topics/exchanges/queues if testing no-provisioning mode.
4. Boot the application with the target function and named binders.
5. Publish `OrderCreated(eventId=evt-101)` to Kafka `orders.created`.
6. Consume from the Rabbit queue bound to `orders.forwarded`.
7. Assert `eventId`, `orderId`, `status`, content type, and headers.
8. Restart the consumer; verify group/offset behavior and ensure no extra events violate expected semantics.
9. Temporarily block Rabbit and verify retry/failure and recovery.
10. Verify messages targeting the wrong broker **do not** produce output on other resources.

When configuring explicit binders, the test configuration must supply full named-binder definitions. Do not rely on the in-memory test binder to prove `BinderCustomizer` attached the right Kafka listener to broker A.

## 27. Testing BinderCustomizer Independently

Because `BinderCustomizer` receives a binder instance and binder name, name/type filtering logic can be unit-tested without real brokers.

Scenarios:

| Callback input | Expected outcome |
|---|---|
| `ordersKafka` + `KafkaMessageChannelBinder` | Attaches `OrdersRebalanceListener` |
| `analyticsKafka` + `KafkaMessageChannelBinder` | Does not attach the orders-only listener |
| `notificationsRabbit` + Rabbit binder | Does not cast to Kafka or attach listener |
| Newly added binder type | Unaffected unintentionally |

Beyond unit tests, integration tests should verify the listener actually fires when the Kafka group receives partitions. Asserting that `@Bean BinderCustomizer` exists does not prove the callback was invoked with the expected instance/named configuration.

Keep the callback simple, deterministic, and free of network side effects. When a binder name changes in YAML, tests should fail loudly rather than silently skipping critical customization.

## 28. Common Pitfalls

| Symptom | Common cause | Diagnosis / fix |
|---|---|---|
| Input reads from the wrong cluster | Missing `bindings.<input>.binder` | Specify binder explicitly, test against both brokers |
| Output goes to the wrong broker | Unintended default binder selected | Check `defaultBinder` and binding config |
| Binder configuration fails to initialize | Wrong `type` or missing dependency | Check `META-INF/spring.binders` and classpath |
| Adding a second binder makes the first disappear | Explicit `binders` disables auto-configuration | Declare every binder in use explicitly |
| Two Kafka clusters share the same config | Relying on one shared `spring.kafka.*` | Use named binders with separate environments |
| Customizer never runs | Bean not registered or binder unused | Check binding creation and callback logs |
| Listener applied to both Kafka binders by mistake | Only checked instance type | Also filter by `binderName` |
| Listener cannot see a bean | Binder runs in an isolated context | Wire via `BinderCustomizer` or binder-specific sources |
| `StreamBridge` still sends to the old broker | Binding was already created with the prior binder | Use a distinct binding name, configure binder explicitly |
| Kafka consumer duplicates after crash | Cross-broker publish/offset is non-atomic | Event ID, inbox/outbox, idempotency |
| Pulsar binding lacks expected subscription | Wrong group/subscription name/type | Inspect broker subscription and config |
| RabbitMQ publishes to exchange but queue receives nothing | Routing/exchange-binding mismatch | Check bindings, routing keys, permissions |
| Kafka Streams state replays unexpectedly | Unintended `application.id`/cluster change | Plan state/offset migration |
| Scaling entire pod wastes connections | All binders scale together | Consider splitting services by branch |
| In-memory tests PASS but production FAILS | Never tested against real brokers | Run integration tests with real brokers/credentials |

## 29. Pre-Rollout Checklist

| Area | Question to verify |
|---|---|
| Dependencies | Are the right binder artifacts and Spring Cloud BOM used? |
| Function | Does `spring.cloud.function.definition` match the intended beans? |
| Bindings | Does every `<function>-in/out-*` have the right destination/group/binder? |
| Explicit binders | Are all used named binders declared when `binders` is enabled? |
| Binder type | Does `type` match an implementation on the classpath? |
| Environment | Are broker host/port and security isolated by name? |
| Inheritance | Is `inheritEnvironment` set as intended? |
| Default | Could `defaultBinder`/`defaultCandidate` cause an accidental selection? |
| Customizer | Filtered by type/name, runs before binder use, and integration-tested? |
| Schema | Are content types/Serdes/headers compatible across both brokers? |
| Delivery | Is there a plan for crashes between publish and offset commit? |
| Idempotency | Are event IDs, inbox/outbox, or deduplication in place? |
| Security | Do runtime identities follow least privilege? |
| Ops | Are metrics/health/backlog tracked separately per broker? |
| Scaling | Will scaling replicas unintentionally scale every binding? |
| Testing | Have real-broker and failure-injection tests been run? |
| Rollback | Can a binding revert to the old broker without losing or duplicating data? |

## 30. Hands-On Exercise: Kafka → RabbitMQ and Two Kafka Clusters

### Part A — Function Bridge

1. Create `bridgeOrder` taking `OrderCreated` and returning `OrderForwarded`.
2. Add the Kafka and RabbitMQ binder dependencies.
3. Define `ordersKafka` (`type: kafka`) and `notificationsRabbit` (`type: rabbit`).
4. Set `bridgeOrder-in-0.binder=ordersKafka`.
5. Set `bridgeOrder-out-0.binder=notificationsRabbit`.
6. Configure destinations, group, content types, and environment connections.
7. Send a real message to Kafka and verify Rabbit receives the same `eventId`.
8. Simulate Rabbit down and describe Kafka redelivery behavior.

### Part B — Two Kafka Clusters

1. Add `analyticsKafka` also with `type: kafka` but different `brokers`.
2. Route output of an independent function to `analyticsKafka`.
3. Write a `BinderCustomizer` attaching a rebalance listener only to `ordersKafka`.
4. Verify the listener is not attached to `analyticsKafka`.
5. Inspect the real target broker using Kafka CLI tools.
6. Explain why cross-cluster writes cannot be treated as an atomic transaction.

### Part C — Operations

1. Add Actuator/Micrometer.
2. Observe health, binding state, and per-broker lag/backlog.
3. Run multiple replicas; note consumer/connection growth on each binder.
4. Disconnect one broker from the network temporarily, then recover.
5. Reconcile input, output, retries, DLQ, and duplicates.
6. Finalize the production checklist and rollback plan.

**Completion criteria:** explain how binder type differs from binder configuration name; map every binding to the right broker; isolate environments/credentials; accurately describe `BinderCustomizer`'s role in multi-binder contexts; test dynamic `StreamBridge` bindings; and design tests plus delivery guarantees for cross-broker bridges.

## 31. Official References

- [Spring Cloud Stream — Multiple Binders on the Classpath](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/multiple-binders.html) — per-binding binder selection and `defaultBinder`.
- [Spring Cloud Stream — Connecting to Multiple Systems](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/multiple-systems.html) — named binders, `environment`, and multiple clusters of the same type.
- [Spring Cloud Stream — Binder Configuration Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binder-configuration-properties.html) — `type`, `inheritEnvironment`, `environment`, `defaultCandidate`.
- [Spring Cloud Stream — Customizing Binders in Multi Binder Applications](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binder-customizer.html) — `BinderCustomizer` and filtering by binder type/name.
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html) — destination, group, binder, and extended properties.
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html) — functional model and `StreamBridge` `binderName`.
- [Spring Cloud Stream — Kafka Binder Configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html) — Kafka binder properties, consumer/producer extensions.
- [Spring Cloud Stream — KafkaBindingRebalanceListener](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/rebalance_listener.html) — rebalance callbacks and offset seeking.
- [Spring Cloud Stream — Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html) — binding-level producer/consumer properties and Spring Pulsar integration.
- [Spring Cloud Stream — Multi Binders with Kafka Streams](https://docs.spring.io/spring-cloud-stream-binder-kafka/docs/current/reference/html/spring-cloud-stream-binder-kafka.html) — `KStream`/`KTable` and regular Kafka in the same application.
- [Spring Cloud Stream — Binding Visualization and Control](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding_visualization_control.html) — Actuator binding state and lifecycle.
