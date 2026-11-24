# Spring for Apache Pulsar and Custom Integration Layers

## 1. The problem of integrating Pulsar in Spring applications

Apache Pulsar provides a distributed messaging system with topics, subscriptions, producers, consumers, schemas, acknowledgements, redelivery, and transactions. Spring applications can use the Pulsar Java Client directly, but doing so forces business code to manage many connection and lifecycle details itself.

**Spring for Apache Pulsar** brings familiar Spring abstractions to Pulsar:

- `PulsarTemplate` for sending messages.
- `@PulsarListener` and listener containers for consuming messages.
- `@PulsarReader` when reading a topic from an application-specified starting position/cursor.
- Spring Boot auto-configuration for client, producer factory, consumer factory, listener infrastructure, and configuration properties.
- Support for schemas, acknowledgements, retries, Dead Letter Topics, transactions, and Micrometer observation.

An application may still need a **custom integration layer** to translate domain events into message contracts, standardize metadata, enforce organizational policies, or hide broker details from application services. This layer should add application-specific rules on top of existing Spring abstractions.

Do not confuse three layers:

1. **Apache Pulsar Java Client:** foundational API directly controlling producers, consumers, readers, admin, and transactions.
2. **Spring for Apache Pulsar:** integrates the client into Spring via templates, listeners, containers, schemas, transactions, and auto-configuration.
3. **Application's custom integration layer:** system-owned adapters and policies, such as event contracts, topic mapping, correlation, idempotency, outbox, or error-handling rules.

Each layer has a distinct responsibility. Separating them clearly lets the application leverage Spring/Pulsar capabilities while keeping business contracts independent of the broker.

## 2. Choosing the right project and version

This lesson focuses on the Spring-maintained **Spring for Apache Pulsar** project, with Java package `org.springframework.pulsar` and Spring Boot starter `spring-boot-starter-pulsar`.

With Spring Boot, the starter dependency is usually the entry point:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-pulsar</artifactId>
</dependency>
~~~

Or Gradle:

~~~groovy
implementation("org.springframework.boot:spring-boot-starter-pulsar")
~~~

Let Spring Boot dependency management/BOM manage starter and related dependency versions. Only override Pulsar Client when the compatibility matrix and deployment requirements allow it.

The compatibility matrix for Spring for Apache Pulsar 2.0.x lists combinations of Pulsar Client 4.1.x, 4.0.x, or 3.3.x, Spring Boot 4.0.x, and Java 17+. The 1.2.x line supports Spring Boot 3.4.x/3.5.x with Pulsar Client 3.3.x or documented compatible configurations. Matrices change across releases; verify the exact Spring Boot, Spring for Apache Pulsar, and Pulsar Client versions of your project before upgrading.

The name of the Pulsar integration project for Spring can cause confusion. Apache Pulsar documentation currently references a separate project under artifact group `org.apache.pulsar` and module `pulsar-spring`. This is a different project line from the Spring-maintained `org.springframework.pulsar:spring-pulsar`. Do not mix dependencies, packages, or API examples between the two projects.

## 3. Architecture from application to broker

The publish flow typically looks like this:

~~~text
Domain / Application Service
          |
          | domain event or command
          v
Application-owned messaging port
          |
          | map to message contract
          v
Spring Pulsar adapter
          |
          | PulsarTemplate
          v
Pulsar Producer / Client
          |
          v
Topic / Partition / Broker
~~~

The consume flow goes in the reverse direction:

~~~text
Pulsar Topic
     |
     v
Pulsar Consumer
     |
     v
Spring Listener Container
     |
     v
@PulsarListener adapter
     |
     | validate + map contract
     v
Application Service / Use Case
     |
     v
Domain state / Database
~~~

The Spring listener container creates and manages the Pulsar consumer, receives messages, and dispatches them to the listener method. The `@PulsarListener` annotation is a convenient declaration style; when more control is needed, a listener container factory or the Pulsar Java Client inside a dedicated adapter can be used.

The custom integration layer should sit at the boundary between the application and transport. The domain model does not need to know topic names, subscription types, `PulsarTemplate`, or Pulsar `MessageId`.

## 4. Connection configuration and auto-configuration

Spring Boot auto-configures `PulsarClient` when the starter is on the classpath. By default, the client connects to `pulsar://localhost:6650`; this can be changed via property:

~~~yaml
spring:
  pulsar:
    client:
      service-url: pulsar://localhost:6650
~~~

This is the Pulsar protocol URL, not the HTTP Admin URL. Spring Boot can also auto-configure the Pulsar administration client; the Admin API defaults to `http://localhost:8080` and is configured separately via `spring.pulsar.admin.service-url`.

Common property groups:

| Prefix | Role |
|---|---|
| `spring.pulsar.client.*` | PulsarClient, service URL, timeouts, authentication, TLS, and threads |
| `spring.pulsar.admin.*` | PulsarAdministration and Admin API |
| `spring.pulsar.producer.*` | Default producer, batching, compression, routing, and caching |
| `spring.pulsar.consumer.*` | Default consumer, subscription, receiver queue, and acknowledgement |
| `spring.pulsar.listener.*` | Listener container and concurrency |
| `spring.pulsar.reader.*` | Reader factory and reader properties |
| `spring.pulsar.transaction.*` | Enabling and configuring transaction support |

Example OAuth2 authentication configuration:

~~~yaml
spring:
  pulsar:
    client:
      service-url: pulsar+ssl://pulsar.example.net:6651
      authentication:
        plugin-class-name: org.apache.pulsar.client.impl.auth.oauth2.AuthenticationOAuth2
        param:
          issuerUrl: https://auth.example.net/
          privateKey: file:/run/secrets/pulsar-private-key.json
          audience: urn:example:pulsar:production
~~~

Parameter names in the authentication map must match the exact names expected by the authentication plugin; these keys do not undergo relaxed binding like standard Spring properties. When using TLS, check trust certificates, hostname verification, and provider configurations per deployment documentation.

Spring Boot supports customizers when standard properties are not enough:

- `PulsarClientBuilderCustomizer` to customize the client.
- `PulsarAdminBuilderCustomizer` to customize the admin client.
- `ProducerBuilderCustomizer` and `ConsumerBuilderCustomizer` for producers/consumers.
- `PulsarContainerFactoryCustomizer` for the listener container factory.
- `PulsarTemplateCustomizer` for the template.

Prefer properties first, then add customizers for specialized options. Do not create a new `PulsarClient` on every message send; use the Spring-managed client and factories to reuse connections and resources.

## 5. Sending messages with PulsarTemplate

### 5.1. Simple API

Spring Boot auto-configures `PulsarTemplate<T>`. A component can inject the template and send messages:

~~~java
import org.springframework.pulsar.core.PulsarTemplate;
import org.springframework.stereotype.Component;

@Component
public class OrderEventPublisher {

    private final PulsarTemplate<String> pulsarTemplate;

    public OrderEventPublisher(PulsarTemplate<String> pulsarTemplate) {
        this.pulsarTemplate = pulsarTemplate;
    }

    public void publish(String payload) {
        pulsarTemplate.send("persistent://acme/orders/order-events", payload);
    }
}
~~~

`send` is a synchronous operation: the method waits for the publish result and returns `MessageId` once the message is persisted by the broker according to producer semantics. If the caller does not need to wait, `sendAsync` can be used, returning a `CompletableFuture` for asynchronous result handling.

Do not interpret the send method returning as meaning the business workflow has completed at the consumer. It confirms the producer's publish outcome according to broker settings; consumers may process later.

### 5.2. Fluent API and message keys

When setting keys, properties, or metadata, use the fluent API:

~~~java
pulsarTemplate.newMessage(event)
    .withMessageCustomizer(builder -> builder.key(orderId))
    .send();
~~~

Message keys are useful when routing by key and maintaining per-entity ordering in subscriptions that support corresponding ordering. For example, using `orderId` as the key routes events for the same order to the same processing group/appropriate partition.

You can use `TypedMessageBuilderCustomizer` to customize messages and `ProducerBuilderCustomizer` to customize producers. Customizers apply to a single send or the entire factory depending on where they are registered. These APIs allow extending configuration without rewriting the producer lifecycle.

### 5.3. Topic resolution

Topics can be passed directly to the API:

~~~java
pulsarTemplate.send("persistent://acme/orders/order-events", event);
~~~

If no topic is passed, Spring for Apache Pulsar can resolve the destination in order: user-specified topic, default topic mapped to the message type, then global default. If no topic is found, the operation fails.

A full topic name usually takes the form:

~~~text
persistent://tenant/namespace/topic-name
~~~

Manage topic names in application configuration or a controlled topic catalog rather than scattering string literals across services. For partitioned topics or topics with special policies, manage topic creation and configuration through an explicit infrastructure process.

## 6. Receiving messages with @PulsarListener

### 6.1. Basic listener

`@PulsarListener` creates a listener endpoint and lets the container manage the Pulsar consumer:

~~~java
import org.springframework.pulsar.annotation.PulsarListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener {

    @PulsarListener(
        topics = "persistent://acme/orders/order-events",
        subscriptionName = "inventory-service-v1"
    )
    public void handle(String payload) {
        // Delegate to an application use case.
    }
}
~~~

When using the Spring Boot starter, annotation processing and listener infrastructure are auto-configured. Without Spring Boot, you must enable `@EnablePulsar` and provide the appropriate factories/containers yourself.

Always set `subscriptionName` explicitly in production environments. If omitted, the framework may generate a subscription name automatically; this is usually inappropriate when multiple replicas need to share a stable subscription.

### 6.2. Subscription types and concurrency

Pulsar offers multiple subscription types with different semantics:

| Type | Primary behavior | Use case |
|---|---|---|
| `Exclusive` | One active consumer on the subscription | Simple, single-consumer processing |
| `Failover` | One active consumer, others on standby | Needs failover and ordering per Pulsar semantics |
| `Shared` | Messages distributed across multiple consumers | Increasing throughput without global ordering guarantees |
| `Key_Shared` | Distributed by key, preserving order for the same key under appropriate settings | Scaling consumers while still requiring per-entity/key ordering |

`@PulsarListener` defaults to `Exclusive` unless configured otherwise. With multiple replicas processing a single subscription, choose the right subscription type. `Shared` suits workloads that can process in parallel; if per-key ordering is needed, consider `Key_Shared` and send messages with stable keys.

Example listener sharing a subscription:

~~~java
@PulsarListener(
    topics = "persistent://acme/orders/order-events",
    subscriptionName = "inventory-service-v1",
    subscriptionType = SubscriptionType.Shared,
    concurrency = "3"
)
void handle(OrderPlacedV1 event) {
    inventoryService.reserve(event);
}
~~~

Concurrency greater than 1 only makes sense with subscription types supporting multiple consumers such as Failover, Shared, or Key_Shared. For partitioned topics, partition count and consumer count determine actual parallelism. Increasing concurrency on a non-partitioned topic does not automatically create more partitions to increase throughput.

### 6.3. PulsarReader vs. PulsarListener

`@PulsarListener` uses consumer subscriptions, acknowledgements, and redelivery. `@PulsarReader` uses the Pulsar Reader API to read a topic starting from a specified message ID/cursor, such as `earliest` or `latest`.

Use Reader when you need to manage starting read positions yourself or replay data by cursor. Do not replace listeners with readers for standard business consumers that need subscriptions, load balancing, acknowledgements, and retries. Readers have different lifecycles and semantics from consumers.

## 7. Schemas and serialization

### 7.1. Choosing explicit schemas

Spring for Apache Pulsar uses Pulsar Schemas to serialize/deserialize payloads. For primitive types, the framework can infer schemas. For complex types, the default schema is typically JSON if not configured otherwise.

Common schemas:

- `JSON`: human-readable, suitable for DTOs and cross-language integration.
- `AVRO`: explicit schema with writer/reader schema rules and evolution.
- `PROTOBUF`: binary schema with field numbers and code generation.
- `KEY_VALUE`: payload consisting of a key and value per schema.
- `AUTO_CONSUME` or `AUTO_PRODUCE_BYTES`: when handling generic records or bytes according to the topic's schema.

Example declaring JSON schema explicitly on a listener:

~~~java
@PulsarListener(
    topics = "persistent://acme/orders/order-placed-v1",
    subscriptionName = "billing-service-v1",
    schemaType = SchemaType.JSON
)
void handle(OrderPlacedV1 event) {
    billingService.createInvoice(event);
}
~~~

For complex message types, declare schemas or mappings explicitly rather than relying on default inference. Producers and consumers must agree on contracts, fields, null/defaults, enums, timestamps, currency units, and versioning rules.

### 7.2. Contract example

~~~java
public record OrderPlacedV1(
    String eventId,
    String orderId,
    String customerId,
    long occurredAtEpochMillis,
    String currency,
    long totalMinorUnits
) {}
~~~

A contract is an integration DTO, not an ORM entity or domain aggregate. It contains only the data that needs to be published. If the domain model changes, a mapper at the producer keeps the message contract stable.

Pulsar Schema Registry checks topic schemas against a compatibility policy. When evolving contracts, verify whether older consumers can read the new schema. Adding optional fields is usually more compatible than changing types or removing fields; do not reuse retired Protobuf field numbers and do not change a field's meaning while keeping its old name.

### 7.3. Schema mapping and @PulsarMessage

Type-to-schema mappings can be configured via `spring.pulsar.defaults.type-mappings` or `SchemaResolverCustomizer`. The documentation also supports the `@PulsarMessage(schemaType = SchemaType.JSON)` annotation to set a default schema for a message type.

Mapping by Java class helps configure inside an application, but internal Java class names should not become a mandatory contract across services. Wire contracts must be governed via Pulsar schemas and compatibility rules.

If a consumer does not yet know the specific schema, `AUTO_CONSUME` allows reading generic records and accessing fields by schema metadata. This is useful for tooling, routers, or handling multiple record types; for regular business handlers, strongly typed DTOs are usually easier to validate.

## 8. Headers, properties, and message keys

Pulsar does not have a header abstraction identical to Spring Messaging. Pulsar messages provide metadata and a map of user properties. Spring for Apache Pulsar maps them to `MessageHeaders` through `PulsarHeaderMapper`.

Consumers can read metadata with `@Header`:

~~~java
@PulsarListener(topics = "persistent://acme/orders/order-events")
void handle(
        OrderPlacedV1 event,
        @Header(PulsarHeaders.MESSAGE_ID) MessageId messageId,
        @Header("correlationId") String correlationId) {
    // Process the event and include IDs in logs/traces.
}
~~~

Headers are typically used for message IDs, keys, event times, correlation IDs, and technical metadata. The payload remains the place for primary business data.

Some notes:

- Do not put entire domain objects into user properties.
- Only pass headers across the broker that are genuinely needed.
- Do not trust a tenant ID or user ID solely because it appears in a header; authenticate at the security layer.
- If using a JSON header mapper, configure trusted packages and an allowlist of permitted headers.
- Avoid high-cardinality metric tags such as order ID or customer ID.

Message keys affect routing and ordering; header metadata does not automatically create ordering. If per-aggregate ordering is required, choose an appropriate key and subscription type, then test with a partitioned topic.

## 9. Acknowledgement, redelivery, and error handling

### 9.1. Automatic acknowledgement

The listener container coordinates message receiving and acknowledgement. For record listeners, the default `BATCH` mode processes received messages in internal batches and acknowledges the batch when records succeed; failed records are negatively acknowledged according to the container mechanism.

You can select `AckMode.RECORD` to acknowledge or nack each record individually after the listener processes it. For batch listeners, `RECORD` is not supported; if per-message decisions inside a batch are needed, use manual acknowledgement.

### 9.2. Manual acknowledgement

Only use manual ack when the application needs control over when messages are confirmed:

~~~java
@PulsarListener(
    topics = "persistent://acme/orders/order-events",
    subscriptionName = "billing-service-v1",
    ackMode = AckMode.MANUAL
)
void handle(Message<OrderPlacedV1> message, Acknowledgment acknowledgment) {
    billingService.createInvoice(message.getValue());
    acknowledgment.acknowledge();
}
~~~

Only acknowledge after processing has reached a durable state according to the application's guarantees. If you acknowledge before database commit, the process may crash after ack and the message will not be redelivered even though the data was not saved.

Manual ack shifts acknowledgement responsibility to the application. You must clearly define success, retryable failure, permanent failure, and when to nack.

### 9.3. Redelivery and backoff

Pulsar performs redelivery on ack timeout or negative acknowledgement. You can configure `ackTimeoutMillis`, `negativeAckRedeliveryDelay`, or `RedeliveryBackoff` with increasing delays.

Do not retry every exception indefinitely. Categorize:

- Transient errors: dependency timeout, temporary broker/network failure; retry with limits and backoff.
- Data errors: invalid schema, payload missing required fields; usually route to DLT/DLQ or quarantine for investigation.
- Business errors: disallowed state; depending on contract, record a rejection outcome instead of redelivering.
- Code errors: bugs in the handler; limit retries to prevent poison messages from occupying consumers.

### 9.4. Dead Letter Topic

Pulsar's native Dead Letter Policy supports Shared subscriptions; it does not support native DLQ for Exclusive and Failover because redelivery can break ordering semantics. With a Shared subscription, configure `DeadLetterPolicy` and specify an explicit DLT topic:

~~~java
@Bean
DeadLetterPolicy orderDeadLetterPolicy() {
    return DeadLetterPolicy.builder()
        .maxRedeliverCount(10)
        .deadLetterTopic("persistent://acme/orders/order-events-dlt")
        .build();
}
~~~

Then reference the bean in the annotation `@PulsarListener(deadLetterPolicy = "orderDeadLetterPolicy")`. When using partitioned topics, specify the DLT topic explicitly rather than relying on a default name that may include partition suffixes.

Spring for Apache Pulsar also provides `PulsarConsumerErrorHandler` and `PulsarDeadLetterPublishingRecoverer` to implement recovery/DLT for various subscription types. This is a different mechanism from Pulsar's native DLQ; if used for Exclusive/Failover, understand that retries/recovery can alter ordering. Do not configure conflicting acknowledgement/retry mechanisms simultaneously.

## 10. Transaction support

Spring for Apache Pulsar provides:

- `PulsarTransactionManager`.
- Transactional `PulsarTemplate`.
- Transactional `@PulsarListener`.
- Synchronization with other Spring transaction managers as supported by documentation.

Transaction support is disabled by default. It can be enabled via:

~~~yaml
spring:
  pulsar:
    transaction:
      enabled: true
~~~

A consume-process-produce flow can run inside a Pulsar transaction: the listener receives a message, processes it, publishes a new message via the transactional template, and the container enlists the acknowledgement in the same Pulsar transaction. If processing or publishing fails, the transaction rolls back and the input message can be redelivered.

A Pulsar transaction does not automatically turn a database transaction and a broker transaction into a single system-wide atomic transaction. When combining JDBC transactions with Pulsar transactions, understand commit ordering and scenarios where one side commits while the other fails. Design idempotency for DB writes and consider transactional outbox/inbox when guarantees between the database and broker are needed.

Do not enable transactions just because `@Transactional` is available. Choose transaction boundaries by business needs, check timeouts and broker capabilities, and test commit/rollback against a real broker.

## 11. Spring Cloud Stream Pulsar Binder

If an application wants to focus on function-based event processing and minimize direct middleware coupling, the Spring Cloud Stream Pulsar Binder can be used.

Common functional models:

- `Supplier<T>` produces data.
- `Function<T, R>` receives and transforms data.
- `Consumer<T>` consumes data.

Spring Cloud Stream maps input/output bindings to Pulsar topics via destination configuration. The binder manages bindings and connections to Pulsar. When using the binder, application code can have less direct dependency on `PulsarTemplate` or `@PulsarListener`.

Example binding configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: orderProcessor
    stream:
      bindings:
        orderProcessor-in-0:
          destination: orders.raw
        orderProcessor-out-0:
          destination: orders.validated
~~~

In the binder, default message conversion typically uses `application/json` in Spring Messaging and passes bytes via Pulsar `Schema.BYTES`. If you want Pulsar native schema encoding/decoding, enable `use-native-encoding` on the producer and `use-native-decoding` on the consumer, and configure schema type/message type for the binding.

Choose the binder when you need a function/binding model, destination configuration, and middleware neutrality. Choose Spring for Apache Pulsar directly when you need deep control over Pulsar-specific features such as schemas, keys, subscriptions, acknowledgements, readers, producer customizers, or Pulsar transactions. Do not add both a binder and a custom abstraction layer without a concrete need; every extra layer adds configuration and debugging complexity.

## 12. Designing the application's custom integration layer

### 12.1. Where should responsibilities live?

A custom integration layer is useful when it holds system-wide rules:

- Mapping domain events/commands to versioned message contracts.
- Choosing topics by event type, tenant, or bounded context.
- Attaching message keys, event IDs, correlation IDs, and causation IDs.
- Standardizing logging, tracing, and metric tags.
- Applying idempotency, outbox/inbox, and deduplication policies.
- Standardizing retries, DLT routing, and business error classification.
- Providing ports so application services do not depend on Pulsar when transport replacement or isolated testing is genuinely required.

Do not put business logic into a generic messaging framework. The domain decides when an event occurs; the integration adapter decides how that event is published to the broker.

### 12.2. Port and adapter example

The application layer defines a port in business terms:

~~~java
public interface OrderEventPublisher {
    void publish(OrderPlaced event);
}
~~~

The adapter uses Spring for Apache Pulsar:

~~~java
import org.springframework.pulsar.core.PulsarTemplate;
import org.springframework.stereotype.Component;

@Component
public class PulsarOrderEventPublisher implements OrderEventPublisher {

    private final PulsarTemplate<OrderPlacedV1> template;

    public PulsarOrderEventPublisher(PulsarTemplate<OrderPlacedV1> template) {
        this.template = template;
    }

    @Override
    public void publish(OrderPlaced event) {
        OrderPlacedV1 contract = new OrderPlacedV1(
            event.eventId(),
            event.orderId().toString(),
            event.customerId().toString(),
            event.occurredAt().toEpochMilli(),
            event.currency(),
            event.totalMinorUnits()
        );

        template.newMessage(contract)
            .withMessageCustomizer(builder -> builder.key(contract.orderId()))
            .send();
    }
}
~~~

The snippet is an adapter example; the `OrderPlaced` domain type and topic configuration belong to the application. In production, topics should come from configuration properties or a topic catalog rather than being hard-coded.

The consumer adapter receives the DTO and calls the application service:

~~~java
import org.springframework.pulsar.annotation.PulsarListener;
import org.springframework.stereotype.Component;

@Component
public class InventoryPulsarAdapter {

    private final ReserveInventoryUseCase useCase;

    public InventoryPulsarAdapter(ReserveInventoryUseCase useCase) {
        this.useCase = useCase;
    }

    @PulsarListener(
        topics = "persistent://acme/orders/order-placed-v1",
        subscriptionName = "inventory-service-v1",
        schemaType = SchemaType.JSON,
        subscriptionType = SubscriptionType.Shared
    )
    public void onOrderPlaced(OrderPlacedV1 message) {
        useCase.reserve(
            message.orderId(),
            message.eventId()
        );
    }
}
~~~

The application service sees only the use case and domain data. It does not need to import `PulsarTemplate`, `PulsarClient`, `Consumer`, or `MessageId`.

### 12.3. When is a custom wrapper unnecessary?

If an application only has one producer, one listener, and no shared integration rules, injecting `PulsarTemplate` and using `@PulsarListener` directly can be the simplest option.

Do not create a one-to-one wrapper around every Pulsar Client method. An interface like `MessagingService.send(Object)`, `receive()`, or `publish(String, Object)` that fails to express topic, schema, key, acknowledgement, and retry semantics will merely obscure the API without providing a useful abstraction.

If an abstraction hides important Pulsar features, let the concrete adapter use Spring/Pulsar APIs internally and keep only stable business contracts externally.

### 12.4. Do not rewrite what Spring already provides

Avoid reimplementing:

- PulsarClient lifecycle and connection management.
- Producer/consumer caches and factories.
- Listener containers, thread management, and consumer lifecycles.
- Schema serialization/deserialization already provided by the framework.
- Acknowledgement, redelivery, and listener recovery.
- Pulsar transaction manager.
- Micrometer observations for templates/listeners.

When customization is needed, prefer properties, factory customizers, template customizers, schema resolver customizers, or listener-specific customizers. Only use the Pulsar Java Client directly inside a specialized adapter when a required capability is not yet provided by Spring abstractions.

## 13. Observability and operations

Spring for Apache Pulsar integrates Micrometer Observation for `PulsarTemplate` and `@PulsarListener`. When an `ObservationRegistry` is present, send/receive operations are traced and timed. Spring Boot Actuator can auto-configure the registry in Boot applications.

Common observations/metrics include:

- `spring.pulsar.template`: time to send messages.
- `spring.pulsar.template.active`: active publish operations.
- `spring.pulsar.listener`: time to process/receive messages in listeners.
- `spring.pulsar.listener.active`: active listener operations.

Default tags can include template bean name and listener ID. Tags can be added via `PulsarTemplateObservationConvention` or `PulsarListenerObservationConvention`. Only use low-cardinality tags; do not put order IDs or user IDs into metric labels.

Alongside framework metrics, monitor:

- Publish success/failure and latency.
- Consumer backlog, message age, and processing latency.
- Redelivery count, nacks, ack timeouts, and DLT volume.
- Subscription/consumer counts and partition distribution.
- Outbox backlog if present.
- Schema incompatibilities and serialization failures.
- Transaction rollbacks/timeouts.

Logs should include topic, subscription, message ID, key, and correlation ID at an appropriate level. Do not log full sensitive payloads or credentials.

## 14. Testing

A good test suite must verify contracts and semantics against a broker, not just mock `PulsarTemplate`.

**Application-layer unit tests:** test domain events, use cases, validation, and idempotency without Pulsar.

**Adapter tests:** test domain-to-contract mappers, topic routing, keys, and metadata.

**Integration tests:** start a Pulsar test broker/container, send messages, and verify listeners process them properly. Spring for Apache Pulsar provides the `spring-pulsar-test` module with `PulsarConsumerTestUtil` and `PulsarTestContainerSupport` to assist testing.

**Failure tests:** verify schema mismatches, listener exceptions, retries, redelivery, DLT, broker unavailability, and restarts.

**Transaction tests:** verify output messages and acknowledgements commit/rollback properly; if a database is involved, also test cases where the DB commits while the Pulsar transaction fails.

**Compatibility tests:** verify new producers and old/new consumers can read schemas according to policy; check optional fields, expanded enums, and new versions.

Tests must verify actual subscription types and ordering. Mocks cannot prove that a Shared subscription preserves ordering, or that native DLQ works correctly on the broker.

## 15. Common design mistakes

1. **Creating a PulsarClient per request.** This wastes connections and resources. Use auto-configured clients/factories and templates.
2. **Scattering topic names throughout code.** Makes naming, tenant, or version changes hard. Use configuration/topic catalogs.
3. **Not declaring a stable subscription name.** Each instance may create its own subscription, altering load-balancing semantics.
4. **Using Shared while assuming global ordering.** Shared does not guarantee global order; use keys and Key_Shared when per-entity ordering is needed.
5. **Increasing concurrency on an Exclusive subscription.** Does not create extra active consumers; choose an appropriate subscription type and consider partition counts.
6. **Not declaring schemas for complex DTOs.** Producer/consumer may infer differently. Declare schemas explicitly and test compatibility.
7. **Retrying poison messages indefinitely.** Builds up backlog and wastes resources. Limit retries, use backoff, and use a DLT.
8. **Enabling native DLQ on unsupported subscriptions.** Native DLQ only supports Shared; other subscriptions require error handlers and understanding ordering impacts.
9. **Acknowledging before committing data.** Messages can be lost if the application dies. Ack after reaching durability conditions or use Pulsar transactions.
10. **Assuming a Pulsar transaction covers a database transaction.** There is no automatic atomicity across two resources; use idempotency, outbox/inbox, and test failures.
11. **Rewriting listener containers and producer caches.** Increases operational code and makes lifecycle handling hard. Use Spring abstractions and customizers.
12. **Creating meaningless generic wrappers.** Only hides APIs without reducing coupling. Design ports around concrete use cases and contracts.
13. **Ignoring the compatibility matrix.** Spring Boot, Spring Pulsar, and Pulsar Client have separate release cycles. Check the version matrix before upgrading.

## 16. Architecture selection process

You can decide in the following sequence:

1. Does the application only need to send/receive topics via Spring APIs? Start with Spring for Apache Pulsar.
2. Are there multiple listeners and producers? Use auto-configuration, listener containers, and factory customizers.
3. Need a function-based pipeline and middleware-neutral bindings? Evaluate the Spring Cloud Stream Pulsar Binder.
4. Need to keep the domain independent of the broker? Add custom ports/adapters for contracts and business mapping.
5. Need Pulsar-specific features not yet in Spring abstractions? Use the Pulsar Java Client inside a specialized adapter.
6. Have requirements for retries, ordering, DLT, schema evolution, or transactions? Design around Pulsar semantics first, then configure Spring abstractions.
7. Have multiple independent services? Govern schema/contract versions, subscription names, and topics at the platform level.

## 17. Pre-release checklist

- [ ] Selected the right Spring for Apache Pulsar artifacts and compatibility matrix.
- [ ] PulsarClient is managed by Spring, not recreated per operation.
- [ ] Service URL, TLS, and authentication are configured for the environment.
- [ ] Topic and subscription names are stable with clear owners.
- [ ] Subscription type matches throughput and ordering requirements.
- [ ] Schemas are declared/versioned and tested for compatibility.
- [ ] Producer specifies keys, metadata, and appropriate sync/async sends.
- [ ] Consumer specifies ack mode, timeouts, retries, and DLT.
- [ ] DLT policy matches subscription type; partitioned topics have explicit DLT names.
- [ ] Transaction boundaries are defined; DB/Pulsar are not assumed to be one atomic transaction.
- [ ] Custom integration layer contains only application policies and contracts.
- [ ] No reimplementation of existing producer factories, listener containers, or schema/ack lifecycles.
- [ ] Micrometer observations, backlog, retries, and DLT are monitored.
- [ ] Integration tests run against a Pulsar broker/container and include failure scenarios.

## 18. References

- [Spring for Apache Pulsar — Project Overview](https://spring.io/projects/spring-pulsar/): goals, features, and compatibility of the Spring project.
- [Spring Boot Reference — Apache Pulsar Support](https://docs.spring.io/spring-boot/reference/messaging/pulsar.html): starter, auto-configuration, PulsarClient, PulsarTemplate, listeners, and transactions.
- [Spring for Apache Pulsar — Quick Tour](https://docs.spring.io/spring-pulsar/reference/reference/pulsar/quick-tour.html): first Spring Boot publish and consume application.
- [Spring for Apache Pulsar — Message Production](https://docs.spring.io/spring-pulsar/reference/reference/pulsar/message-production.html): PulsarTemplate, send/sendAsync, fluent API, producer customization, and schemas.
- [Spring for Apache Pulsar — Message Consumption](https://docs.spring.io/spring-pulsar/reference/reference/pulsar/message-consumption.html): PulsarListener, subscriptions, schemas, containers, acks, retries, and DLT.
- [Spring for Apache Pulsar — Transactions](https://docs.spring.io/spring-pulsar/reference/reference/pulsar/transactions.html): PulsarTransactionManager, transactional template/listener, and consume-process-produce.
- [Spring for Apache Pulsar — Observability](https://docs.spring.io/spring-pulsar/reference/reference/observability.html): Micrometer observations, metrics, and tracing for producers/listeners.
- [Spring for Apache Pulsar — Testing Applications](https://docs.spring.io/spring-pulsar/reference/reference/testing-applications.html): PulsarConsumerTestUtil and PulsarTestContainerSupport.
- [Spring for Apache Pulsar — Version Compatibility](https://docs.spring.io/spring-pulsar/reference/appendix/version-compatibility.html): matrix for Spring Pulsar, Pulsar Client, Spring Boot, and Java.
- [Spring Cloud Stream — Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/spring-cloud-stream-binder-pulsar.html): function/binding model and Pulsar integration via binder.
- [Apache Pulsar — Spring Integration Project](https://pulsar.apache.org/pulsar-spring/reference/): documentation for the `org.apache.pulsar:pulsar-spring` project, distinct from the Spring-maintained `org.springframework.pulsar` project.
