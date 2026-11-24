# @RabbitListener and Listener Container Factories

## Purpose and Context

In the **SPRING_BOOT_INTEGRATION** module, Spring Boot connects multiple systems via HTTP clients, databases, caches, message brokers, and Spring Integration adapters. With RabbitMQ/AMQP, a producer typically uses `RabbitTemplate` to emit events/commands; on the receiving side, consumers use **`@RabbitListener`** to process messages. Yet the annotation does not simply spawn a background worker thread on its own: Spring AMQP relies on a **listener container** to manage connections, AMQP channels, consumers, concurrency, acknowledgments, payload conversion, retries, errors, and lifecycle.

Suppose Order Service emits `OrderConfirmed` to exchange `orders.events`, and Inventory Service consumes from queue `inventory.order-confirmed` to reserve stock in its database. A consumer might receive a message before its SQL transaction commits; a process might crash after COMMIT yet before ACK; or a malformed-schema event might redeliver endlessly. How `@RabbitListener` and the container factory are configured determines **when the broker gets ACKed, how many messages run concurrently, and where errors go**.

This lesson belongs to the **RabbitMQ and AMQP** chapter, topic **`@RabbitListener` and listener container factories**. It focuses on Spring AMQP architecture in Spring Boot and how to build listeners to production contracts with accurate RabbitMQ semantics—preventing pools, threads, or retries from losing data or duplicating side effects.

After this lesson, you will be able to:

1. Trace the path broker queue → consumer channel → listener container → `@RabbitListener` method.
2. Distinguish annotations, endpoint registries, containers, container factories, `RabbitTemplate`, and `ConnectionFactory`.
3. Configure default and named factories; contrast `SimpleRabbitListenerContainerFactory` with `DirectRabbitListenerContainerFactory`.
4. Use `queues`, `bindings`, `id`, `containerFactory`, arguments, payload converters, and method parameters.
5. Choose concurrency, prefetch, consumer acknowledgment modes, transaction boundaries, and retry/DLQ policies.
6. Design idempotent consumers handling duplicates/redeliveries, poison messages, and unknown downstream outcomes.
7. Clearly separate broker publisher confirms from consumer ACKs.
8. Test with RabbitMQ Testcontainers and monitor listener lifecycle, queue depth, unacked counts, and errors.
9. Operate credentials/TLS, schema evolution, backpressure, graceful shutdown, and rolling deployments.

> **Core point:** `@RabbitListener` only describes a consumption endpoint. The **container factory** configures how listeners run, while the **listener container** executes the receive/ACK/retry lifecycle. Consumer ACK does not prove external transactions outside RabbitMQ committed if execution order is wrong.

## 1. Overall Architecture

~~~mermaid
flowchart LR
    P["Order Service / RabbitTemplate"] --> X["Exchange: orders.events"]
    X -->|"order.confirmed"| Q["Queue: inventory.order-confirmed"]
    Q --> B["RabbitMQ consumer deliveries"]
    B --> C["Listener Container"]
    C --> M["Message Converter / Argument Resolver"]
    M --> L["@RabbitListener method"]
    L --> S["Inventory application service"]
    S --> D["PostgreSQL + Inbox"]
    C -. "ACK / NACK / reject" .-> Q
    C -. "Retry / error handler" .-> E["DLQ or retry topology"]
~~~

Components and roles:

| Component | Spring Type | Responsibility |
| --- | --- | --- |
| Publisher | `RabbitTemplate` | Sends messages to exchange/routing key |
| Connection resource | AMQP `ConnectionFactory`, typically `CachingConnectionFactory` | Creates/caches connections and channels |
| Listener declaration | `@RabbitListener` | Specifies queue/binding, method, listener ID, container factory |
| Factory | `RabbitListenerContainerFactory` | Builds containers with shared settings |
| Container runtime | `SimpleMessageListenerContainer` or `DirectMessageListenerContainer` | Manages consumer threads/channels/ACK/lifecycle |
| Argument conversion | `MessageConverter` and message handler adapters | Converts AMQP messages into DTOs/method arguments |
| Business logic | `OrderProjectionService` | Validation, transactions, side effects, idempotency |
| Registry | `RabbitListenerEndpointRegistry` | Looks up and starts/stops annotation-registered listener containers |
| Error/retry | Error handlers, advice, retry policies, DLX/DLQ | Classifies errors and preserves recoverability |

**A factory is not a connection pool.** `SimpleRabbitListenerContainerFactory` creates and configures containers; `CachingConnectionFactory` is the infrastructure layer managing AMQP connections and channels. A single container can open multiple AMQP consumers and channels depending on concurrency.

### 1.1. Distinguishing Publish and Consume

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant B as RabbitMQ
    participant C as Listener Container
    participant D as Database
    P->>B: Publish event E-100
    B-->>P: Publisher confirm ACK (if enabled)
    B->>C: Deliver event E-100
    C->>D: Business transaction + inbox
    D-->>C: COMMIT
    C-->>B: Consumer ACK
    Note over P,C: Publisher confirm != Consumer ACK
~~~

A `RabbitTemplate.convertAndSend(...)` returning normally or receiving a publisher confirm ACK **tells nothing about whether `@RabbitListener` has executed**. Likewise, a consumer receiving a delivery **does not mean the DB committed**. Dashboards must separate producer confirmed, consumer delivered, business applied, and consumer acknowledged.

## 2. Dependencies and Initial Configuration

### 2.1. Spring AMQP Starter

For Spring Boot 3.x / Java 17+:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-amqp'

    // If the consumer writes to PostgreSQL:
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'

    // If using Actuator:
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:rabbitmq'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
}
~~~

Some retry configurations require `spring-retry` on the dependency graph; verify your actual starter/version. Spring Boot 4 / newer Spring AMQP versions may change packages, starters, test support, or converter APIs: rely on your project's BOM instead of mixing libraries from older articles.

### 2.2. Connection Properties

~~~yaml
spring:
  rabbitmq:
    host: ${RABBITMQ_HOST:localhost}
    port: ${RABBITMQ_PORT:5672}
    username: ${RABBITMQ_USERNAME}
    password: ${RABBITMQ_PASSWORD}
    virtual-host: ${RABBITMQ_VHOST:/}
    connection-timeout: 5s

app:
  messaging:
    orders:
      queue: inventory.order-confirmed
~~~

This uses environment variables for credentials. In production with TLS, configure SSL/trust/client certificates per your Spring Boot/AMQP version with hostname and CA verification; never assume port 5672 uses TLS by default. Never log credentials or connection URIs containing passwords.

### 2.3. Boot Auto-Configuration and @EnableRabbit

With Spring Boot and the AMQP starter, `@RabbitListener` infrastructure, `ConnectionFactory`, and the default listener container factory are typically auto-configured conditionally. In **plain Spring Framework**, `@EnableRabbit` is usually required to enable annotation processing.

When customizing configuration, verify:

- `RabbitListenerAnnotationBeanPostProcessor` is processing annotations.
- A suitable `RabbitListenerContainerFactory` bean exists.
- Queues/bindings exist or have a clear declaration owner.
- Converters and error handling match the contract.
- Containers are started and broker ACLs permit consumption.

Do not sprinkle extra factory beans or `@EnableRabbit` blindly and unintentionally bypass Boot's auto-configuration. If you define a factory manually, `spring.rabbitmq.listener.*` properties **are not automatically applied to it** unless you invoke Boot's configurer or bind them yourself.

## 3. Minimal Listener: @RabbitListener(queues=...)

A JSON DTO for the command/event:

~~~java
// OrderConfirmedEvent.java
import java.time.Instant;

public record OrderConfirmedEvent(
        String eventId,
        String orderId,
        long aggregateVersion,
        Instant occurredAt) {
}
~~~

Listener:

~~~java
// OrderConfirmedListener.java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderConfirmedListener {

    private final InventoryReservationService service;

    public OrderConfirmedListener(
            InventoryReservationService service) {
        this.service = service;
    }

    @RabbitListener(
            id = "inventory-order-consumer",
            queues = "${app.messaging.orders.queue}")
    public void onOrderConfirmed(OrderConfirmedEvent event) {
        service.reserveIdempotently(event);
    }
}
~~~

`InventoryReservationService` is an application service to implement—for instance, persisting reservations + inbox inside a SQL transaction. To convert JSON into the record, a compatible `MessageConverter` must be configured or auto-configured.

**`queues` only subscribes to the named queue.** It does not mean Spring automatically declares the queue: if topology is provisioned by IaC or `RabbitAdmin`, the listener consumes it; if the queue is missing, container startup may fail or retry declarations depending on configuration.

### 3.1. Listener Endpoint ID

`id = "inventory-order-consumer"` identifies the container for monitoring and control via `RabbitListenerEndpointRegistry`. It is not a mandatory RabbitMQ consumer tag and not an idempotency key. Use stable, descriptive IDs so logs, metrics, and operations remain clear.

### 3.2. Selecting Queues via Configuration

Using placeholders:

~~~java
@RabbitListener(
        queues = "${app.messaging.orders.queue}",
        id = "inventory-order-consumer")
public void handle(OrderConfirmedEvent event) {
    service.reserveIdempotently(event);
}
~~~

Environment-driven queue names allow environment flexibility. However, **never let end users supply arbitrary queue names** in requests: queues represent topology and permission boundaries governed by the application and ops.

### 3.3. Existing Queue Differs from Declared Queue

Choose between two strategies:

1. **Infrastructure-managed topology:** Terraform/Helm/operators/management APIs create exchanges, queues, and bindings prior to deploy; listeners only consume.
2. **Application-managed topology:** declare `Queue`, `Exchange`, and `Binding` beans so `RabbitAdmin` creates them where appropriate.

Choose ownership explicitly. Never let two apps declare the same queue name with differing arguments (`durable`, queue type, DLX, TTL), as RabbitMQ returns `PRECONDITION_FAILED` on incompatible properties.

## 4. Declaring Topology with Beans

~~~java
// OrdersRabbitTopology.java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrdersRabbitTopology {

    @Bean
    TopicExchange ordersExchange() {
        return new TopicExchange(
                "orders.events", true, false);
    }

    @Bean
    Queue inventoryOrdersQueue() {
        return QueueBuilder
                .durable("inventory.order-confirmed")
                .deadLetterExchange("orders.dlx")
                .deadLetterRoutingKey("inventory.order.failed")
                .build();
    }

    @Bean
    Binding inventoryOrdersBinding(
            Queue inventoryOrdersQueue,
            TopicExchange ordersExchange) {
        return BindingBuilder.bind(inventoryOrdersQueue)
                .to(ordersExchange)
                .with("order.confirmed");
    }
}
~~~

This code only declares the primary queue with DLX arguments; **to actually retain rejected messages**, you also need `orders.dlx`, a dead-letter queue, and a matching binding. If the DLX exchange is missing or unroutable, rejected messages can be lost per broker policy. Production must verify DLX, queue type, and persistence.

In Spring AMQP, `RabbitAdmin` can declare `Queue`/`Exchange`/`Binding` beans when a connection opens if present and auto-declaration is enabled. Defining beans does not guarantee declarations succeed: `configure` permissions, broker availability, pre-existing topology, and policies can still fail declarations.

### 4.1. Alternative: Declaring Bindings via Annotations

Alternative to `@Bean` topology:

~~~java
import org.springframework.amqp.rabbit.annotation.Queue;
import org.springframework.amqp.rabbit.annotation.Exchange;
import org.springframework.amqp.rabbit.annotation.QueueBinding;
import org.springframework.amqp.rabbit.annotation.RabbitListener;

@RabbitListener(
        id = "inventory-order-consumer",
        bindings = @QueueBinding(
                value = @Queue(
                        value = "inventory.order-confirmed",
                        durable = "true"),
                exchange = @Exchange(
                        value = "orders.events",
                        type = "topic",
                        durable = "true"),
                key = "order.confirmed"))
public void consume(OrderConfirmedEvent event) {
    service.reserveIdempotently(event);
}
~~~

This is an **alternative** to topological beans—do not copy both simultaneously and have two sources manage the same queue with differing arguments. Spring AMQP annotations support inline binding declarations; exact attributes and limits vary by version.

### 4.2. Exchanges, Queues, Routing Keys, and Consumer Groups

RabbitMQ does not work like Kafka consumer groups and offsets:

- Producers send to an **exchange**.
- The exchange routes to queues per binding key/type.
- Multiple consumers on **the same queue** compete for deliveries.
- If two applications must each receive the same event, each needs its own queue bound to the exchange.
- Consumer acknowledgments apply to deliveries in a queue, not committing offsets in a Kafka consumer group.

For instance, `inventory.order-confirmed` and `billing.order-confirmed` are two separate queues bound to `order.confirmed` so each service gets its own copy of the logical event.

## 5. What Is a Listener Container Factory?

`RabbitListenerContainerFactory` builds the container for a `@RabbitListener` endpoint. One application can define multiple factories with tailored policies:

- High-throughput inventory events: higher concurrent consumers, bounded prefetch, auto ack post-processing.
- Sequential/high-reliability payment commands: low concurrency, manual ack, strict idempotency.
- Telemetry batching: batching enabled, dedicated converter/handler.
- Dead-letter repair queue: isolated consumer, separate retry and rate limits.

A container factory is a **configuration blueprint**, not directly an AMQP consumer.

### 5.1. Separating Three Layers

~~~text
@RabbitListener method (endpoint definition)
            |
            v
RabbitListenerContainerFactory (configuration)
            |
            v
MessageListenerContainer (runtime consumer(s))
            |
            v
AMQP ConnectionFactory → Connection / Channel(s)
            |
            v
RabbitMQ Queue
~~~

Never set `AcknowledgeMode.MANUAL` on `RabbitTemplate` expecting listeners to change modes; publisher templates and consumer containers have separate responsibilities.

### 5.2. The Default Factory

Spring Boot typically supplies a factory named `rabbitListenerContainerFactory` when auto-configured. A `@RabbitListener` that **omits** `containerFactory` uses this default factory during endpoint registration.

Example:

~~~java
@RabbitListener(queues = "inventory.order-confirmed")
public void consume(OrderConfirmedEvent event) {
    service.reserveIdempotently(event);
}
~~~

The queue must still exist or be declared. If you define your own bean with the same name while skipping `SimpleRabbitListenerContainerFactoryConfigurer`, Boot's properties may not apply.

## 6. SimpleRabbitListenerContainerFactory: The Common Default

`SimpleRabbitListenerContainerFactory` builds `SimpleMessageListenerContainer` (SMLC), a mature, flexible implementation. SMLC processes deliveries via container consumer/worker threads and supports tuning consumer count, prefetch, acknowledgments, and related options.

### 6.1. Configuring via application.yml

~~~yaml
spring:
  rabbitmq:
    listener:
      simple:
        acknowledge-mode: auto
        concurrency: 3
        max-concurrency: 8
        prefetch: 20
        default-requeue-rejected: false

app:
  messaging:
    orders:
      queue: inventory.order-confirmed
~~~

Meaning:

| Property | Role | Notes |
| --- | --- | --- |
| `acknowledge-mode: auto` | Container automatically ACKs after handler succeeds | Not RabbitMQ auto-ack-on-delivery |
| `concurrency: 3` | Minimum/initial concurrent consumers | Increases DB/CPU load proportionally |
| `max-concurrency: 8` | Upper bound when SMLC scales dynamically | Does not guarantee 8 threads are always active |
| `prefetch: 20` | Unacked deliveries pre-fetched per consumer/channel semantics | Total in-flight scales with concurrency |
| `default-requeue-rejected: false` | Rejects without requeue by default on listener error | Requires DLX/DLQ if messages must be retained |
| Retry settings | Application/container retry policy | Infinite retries are not enabled by default |

**Common pitfall:** Spring container `AUTO` means **the client library/container sends consumer ACK after the handler method succeeds**. RabbitMQ broker auto-ack-on-delivery corresponds to `AcknowledgeMode.NONE` in Spring AMQP. Picking the wrong mode can lose messages if a handler crashes.

### 6.2. Customizing a Factory While Keeping Boot Defaults

~~~java
// OrdersListenerConfig.java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.boot.autoconfigure.amqp.SimpleRabbitListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrdersListenerConfig {

    @Bean("ordersListenerContainerFactory")
    SimpleRabbitListenerContainerFactory ordersFactory(
            SimpleRabbitListenerContainerFactoryConfigurer configurer,
            ConnectionFactory connectionFactory) {

        var factory =
                new SimpleRabbitListenerContainerFactory();

        // Apply settings from spring.rabbitmq.listener.simple.*
        configurer.configure(factory, connectionFactory);

        // Endpoint-specific policy:
        factory.setConcurrentConsumers(3);
        factory.setMaxConcurrentConsumers(8);
        factory.setPrefetchCount(20);
        factory.setAcknowledgeMode(AcknowledgeMode.AUTO);
        factory.setDefaultRequeueRejected(false);

        return factory;
    }
}
~~~

`SimpleRabbitListenerContainerFactoryConfigurer` is a Spring Boot helper; its package may shift in Boot 4, so verify Javadoc/BOM for your version. For Boot 3.x, the imports shown are standard.

**Intentional pattern:** invoke `configurer.configure(...)` **before** applying local overrides so Boot-configured connection, converter, retry, and observation settings are preserved. Instantiating `new SimpleRabbitListenerContainerFactory()` and calling only `setConnectionFactory` drops important defaults.

### 6.3. Assigning a Factory per Listener

~~~java
@RabbitListener(
        id = "inventory-order-consumer",
        queues = "${app.messaging.orders.queue}",
        containerFactory = "ordersListenerContainerFactory")
public void onMessage(OrderConfirmedEvent event) {
    service.reserveIdempotently(event);
}
~~~

`containerFactory` must match the factory's **bean name**, not its class name. If no matching bean exists, endpoint registration/startup fails.

### 6.4. Overriding Concurrency on the Annotation

Supported versions allow:

~~~java
@RabbitListener(
        id = "order-consumer",
        queues = "inventory.order-confirmed",
        concurrency = "2-6")
public void receive(OrderConfirmedEvent event) {
    service.reserveIdempotently(event);
}
~~~

For SMLC, expressions like `2-6` set min/max concurrency in supported versions. For DMLC, semantics map to consumers-per-queue and may require an integer; check your implementation/version. Avoid configuring conflicting concurrency across multiple sources without understanding precedence.

## 7. DirectRabbitListenerContainerFactory: When to Choose It

`DirectRabbitListenerContainerFactory` builds `DirectMessageListenerContainer` (DMLC). It dispatches deliveries differently from SMLC, executing closer to RabbitMQ client consumer threads and exposing `consumersPerQueue` instead of adaptive min/max concurrent consumers.

| Aspect | Simple (SMLC) | Direct (DMLC) |
| --- | --- | --- |
| Factory | `SimpleRabbitListenerContainerFactory` | `DirectRabbitListenerContainerFactory` |
| Container | `SimpleMessageListenerContainer` | `DirectMessageListenerContainer` |
| Concurrency | `concurrentConsumers`, `maxConcurrentConsumers` | `consumersPerQueue` |
| Dynamic scaling | Scales consumers up/down per SMLC policy | Fixed consumers per queue managed by container |
| Thread model | Container/worker execution model | Tighter tie to client consumer execution |
| Queue additions/removals | Supported via container lifecycle | DMLC has its own management model |
| Tuning | Prefetch, ack, executor, batch, backoff | Prefetch, ack, consumer count, monitor settings |
| When to choose | Familiar default with rich tuning options | When workload/latency/consumer dynamics fit and benchmarks confirm |

Never assume DMLC is universally faster or uses fewer threads without measuring. Actual gains depend on broker, consumer runtime, payloads, DB bottlenecks, and Spring AMQP release.

### 7.1. Defining a Named Direct Factory

~~~java
import org.springframework.amqp.rabbit.config.DirectRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.boot.autoconfigure.amqp.DirectRabbitListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;

@Bean("directInventoryListenerFactory")
DirectRabbitListenerContainerFactory directInventoryFactory(
        DirectRabbitListenerContainerFactoryConfigurer configurer,
        ConnectionFactory connectionFactory) {

    var factory =
            new DirectRabbitListenerContainerFactory();
    configurer.configure(factory, connectionFactory);
    factory.setConsumersPerQueue(2);
    factory.setPrefetchCount(25);

    return factory;
}
~~~

This `@Bean` snippet must live inside a `@Configuration` class. Use `DirectRabbitListenerContainerFactoryConfigurer` on Boot versions providing it. Unlike SMLC's `setMaxConcurrentConsumers`, DMLC sets consumer count per queue via `setConsumersPerQueue`.

### 7.2. Listener Using DMLC

~~~java
@RabbitListener(
        id = "inventory-direct-consumer",
        queues = "inventory.order-confirmed",
        containerFactory = "directInventoryListenerFactory")
public void consume(OrderConfirmedEvent event) {
    service.reserveIdempotently(event);
}
~~~

Never **attach two listeners to the same queue simultaneously** in production just to "A/B test which factory is faster": they act as competing consumers, altering message distribution, throughput, and ordering. Compare factories in test environments or on separate queues.

## 8. ConnectionFactory, Channels, and Listener Containers

RabbitMQ AMQP 0-9-1 multiplexes multiple channels over TCP connections. A listener container typically opens consumers on channels obtained from `ConnectionFactory`. Spring AMQP commonly uses `CachingConnectionFactory` to cache and reuse connections and channels.

~~~mermaid
flowchart TD
    F["SimpleRabbitListenerContainerFactory"] --> C["SimpleMessageListenerContainer"]
    C --> CF["CachingConnectionFactory"]
    CF --> CON["AMQP TCP/TLS Connection"]
    CON --> CH1["Consumer 1 channel"]
    CON --> CH2["Consumer 2 channel"]
    CH1 --> Q["Queue"]
    CH2 --> Q
~~~

### 8.1. Never Store a Singleton Channel Across Listeners

An AMQP `Channel` carries stateful lifecycle, delivery tags, confirms, transactions, and thread-safety rules. Under manual ACK, a delivery tag is bound to the **exact channel that delivered the message**; ACKing on another channel or after channel closure triggers protocol errors.

**Never store a `Channel` in a static field and reuse it across worker threads.** The listener container manages channels, concurrency, and recovery; handlers must only use the `Channel` passed for the current delivery when performing manual ACKs.

### 8.2. Connection/Channel Cache Is Different from Concurrency

`spring.rabbitmq.cache.channel.size` configures **channel caching**, not an absolute ceiling on active consumers. If listener concurrency is 12, RabbitMQ will need at least the corresponding channels; a small channel cache can increase churn as consumers/tasks cycle, without capping concurrency the way you might expect.

Cluster-wide, connections and channels scale as `replicas × listeners × concurrency`. Plan total budgets against broker memory, file-descriptor limits, and max consumer thresholds.

### 8.3. Reconnect and Auto-Recovery

Spring AMQP connection factories and containers have their own recovery/redeclaration mechanisms. Avoid enabling conflicting RabbitMQ Java Client automatic recovery features on top of Spring's management when the framework already coordinates recovery. When the broker disconnects:

- In-flight/unacked messages may be redelivered.
- Listener containers may recreate consumers.
- Queue/binding declarations may rerun per `RabbitAdmin` policy.
- Consumers must be idempotent because replay is normal behavior.

Recovery does not prevent message loss if queues are non-durable, publishers lack confirms, or messages are ACKed before business commits.

## 9. Message Converters and Method Arguments

A `@RabbitListener` method does not have to take raw bytes. Spring AMQP provides **AMQP `MessageConverter`** and method argument resolvers to map body and headers into DTOs, `Message`, `Channel`, or `@Header` parameters.

### 9.1. JSON Converter

Example for Spring AMQP 3.x:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.amqp.support.converter.MessageConverter;
import org.springframework.context.annotation.Bean;

@Bean
MessageConverter rabbitJsonConverter(ObjectMapper objectMapper) {
    return new Jackson2JsonMessageConverter(objectMapper);
}
~~~

Place this inside a configuration class. In Spring AMQP 4.x / Spring Boot 4, Jackson converter classes may be renamed or reorganized; check the replacement class (e.g., Jackson 3–based converters) and runtime Jackson version.

For listeners using custom factories, you may need `factory.setMessageConverter(rabbitJsonConverter)` or rely on Boot's configurer to wire the converter bean per version and config. **Producers and consumers must agree on Content-Type, schema, and JSON field names**, not merely on both using Jackson.

### 9.2. Headers and Raw AMQP Message

~~~java
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.support.AmqpHeaders;
import org.springframework.messaging.handler.annotation.Header;

@RabbitListener(queues = "inventory.order-confirmed")
public void handle(
        OrderConfirmedEvent payload,
        @Header(AmqpHeaders.RECEIVED_ROUTING_KEY)
        String routingKey,
        Message raw) {

    validateRoutingKey(routingKey);
    service.reserveIdempotently(payload);
}
~~~

`validateRoutingKey(...)` represents domain-specific validation. Supported listener method signatures depend on the converter and argument resolver version; if you do not need raw bytes, prefer typed payloads for testability. **Never log raw bodies** containing PII or credentials.

### 9.3. @Payload, @Header, and MessageHeaders

You can annotate parameters explicitly:

~~~java
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.handler.annotation.Header;

@RabbitListener(queues = "inventory.order-confirmed")
public void handle(
        @Payload OrderConfirmedEvent event,
        @Header(name = "schema-version", required = false)
        Integer schemaVersion) {

    checkCompatibleSchema(schemaVersion);
    service.reserveIdempotently(event);
}
~~~

Header `schema-version` is an application contract that producers must populate. If missing, implement explicit backward-compatibility rules rather than blindly defaulting to the latest version.

### 9.4. JSON TypeId Headers and Security

During JSON conversion, Spring AMQP converters can consult type headers (such as `__TypeId__`), inferred method parameter types, and class mappers. Never trust an arbitrary class name from an untrusted producer to instantiate arbitrary Java types. Restrict trusted packages/class mappings or rely on explicit target DTO types, validate schemas, and enforce payload size limits.

Avoid Java native serialization for messages from untrusted systems. Ensure secrets and tokens never appear in JSON payloads or DLQ logs.

### 9.5. Method Overloading and @RabbitHandler

A class can place `@RabbitListener` at class level and define multiple `@RabbitHandler` methods to dispatch by payload type when converters/type mappings support it:

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitHandler;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
@RabbitListener(queues = "inventory.events")
public class InventoryEventHandlers {

    @RabbitHandler
    public void onConfirmed(OrderConfirmedEvent event) {
        // Process OrderConfirmedEvent.
    }

    @RabbitHandler
    public void onCancelled(OrderCancelledEvent event) {
        // Process OrderCancelledEvent.
    }
}
~~~

`OrderCancelledEvent` is an illustrative DTO. Runtime Java payload dispatch requires the converter to resolve the exact type. For multi-version public event contracts, a single envelope record with `eventType` and explicit version dispatch is usually easier to govern than relying solely on Java class headers.

## 10. AcknowledgeMode.AUTO, MANUAL, and NONE

Consumer acknowledgment is one of the most consequential container settings.

| Spring Mode | Broker Semantics | When Is ACK Sent? | Risk |
| --- | --- | --- | --- |
| `AUTO` | Container-controlled consumer **manual ACK** | After handler returns normally (per lifecycle/error policy) | Returning before async work finishes ACKs prematurely |
| `MANUAL` | Application calls `basicAck`/`basicNack`/`basicReject` | When business logic explicitly decides | Forgetting ACK piles up unacked messages; ACKing wrong channel/tag |
| `NONE` | RabbitMQ auto-ack-on-delivery | Immediately when broker delivers message | Crash during handler loses the message |

**AUTO does not mean RabbitMQ auto-ack.** In Spring, `AUTO` means the container handles ACKs for you; the broker still awaits a consumer ACK after the listener finishes.

### 10.1. AUTO Fits Synchronous Handlers

~~~java
@RabbitListener(
        id = "order-consumer",
        queues = "inventory.order-confirmed",
        containerFactory = "ordersListenerContainerFactory")
public void consume(OrderConfirmedEvent event) {
    service.reserveIdempotently(event);
}
~~~

If `service.reserveIdempotently` is a synchronous `@Transactional` method invoked through a Spring proxy, the transaction commits before the method returns. Once the listener returns cleanly, the container ACKs. If the DB commits yet the ACK is lost, the broker redelivers—which is why the service must be idempotent.

### 10.2. MANUAL with ACK After DB Commit

Define a dedicated factory:

~~~java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.boot.autoconfigure.amqp.SimpleRabbitListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;

@Bean("manualOrderListenerFactory")
SimpleRabbitListenerContainerFactory manualFactory(
        ConnectionFactory connectionFactory,
        SimpleRabbitListenerContainerFactoryConfigurer configurer) {

    var factory = new SimpleRabbitListenerContainerFactory();
    configurer.configure(factory, connectionFactory);
    factory.setAcknowledgeMode(AcknowledgeMode.MANUAL);
    factory.setPrefetchCount(10);
    factory.setDefaultRequeueRejected(false);
    return factory;
}
~~~

Listener method:

~~~java
import com.rabbitmq.client.Channel;
import java.io.IOException;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.support.AmqpHeaders;
import org.springframework.messaging.handler.annotation.Header;

@RabbitListener(
        id = "order-manual-consumer",
        queues = "inventory.order-confirmed",
        containerFactory = "manualOrderListenerFactory")
public void consume(
        OrderConfirmedEvent event,
        Channel channel,
        @Header(AmqpHeaders.DELIVERY_TAG) long deliveryTag)
        throws IOException {

    // Synchronous @Transactional service: COMMITS before returning.
    service.reserveIdempotently(event);

    // ACK the exact delivery on the exact channel after success.
    channel.basicAck(deliveryTag, false);
}
~~~

**This snippet shows only the happy path.** With `MANUAL`, you must design explicit **error paths** for exceptions thrown before ACK, message conversion failures before method invocation, shutdown, and nack/reject. Never assume an uncaught exception in a manual handler will automatically ACK/NACK as desired across versions/error handlers.

### 10.3. Manual NACK/Reject and DLX

~~~java
try {
    service.reserveIdempotently(event);
    channel.basicAck(deliveryTag, false);
} catch (PermanentBusinessValidationException ex) {
    // Do not requeue; goes to DLX if queue is configured.
    channel.basicReject(deliveryTag, false);
} catch (TransientDatabaseException ex) {
    // Avoid immediate hot-loop requeue;
    // route to designed retry topology with durable backoff.
    channel.basicNack(deliveryTag, false, false);
}
~~~

`PermanentBusinessValidationException` and `TransientDatabaseException` are illustrative application exceptions. This pattern is valid only when a retry/DLX topology exists and failures are persisted/parked per policy. Without a valid DLX route, `requeue=false` discards the message.

If `channel.basicAck` fails after DB COMMIT, you may not know whether the broker received the ACK. Never retry ACK on another channel; rely on idempotency and accept redelivery.

### 10.4. NONE Only for Expendable Data

`AcknowledgeMode.NONE` lets the broker auto-confirm on delivery. It may suit fire-and-forget telemetry that can tolerate loss, yet is unsuitable for orders, payments, inventory updates, or outbox processing.

## 11. Transaction Boundaries with SQL and AMQP

Two distinct transaction types are frequently confused:

- **Local SQL transaction** managed by `@Transactional` and a JDBC/JPA transaction manager.
- **AMQP channel transaction** when `channelTransacted=true`, committing/rolling back separately on the broker.

Annotating a DataSource-backed service with `@Transactional` **does not create a distributed ACID transaction** spanning PostgreSQL and RabbitMQ. Spring AMQP can synchronize with transaction managers in certain configs, yet a failure window still remains; never treat it as XA/global exactly-once without genuine distributed transaction infrastructure.

### 11.1. @Transactional Service + AUTO Ack

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryReservationService {

    private final InventoryRepository inventory;
    private final ProcessedEventRepository inbox;

    public InventoryReservationService(
            InventoryRepository inventory,
            ProcessedEventRepository inbox) {
        this.inventory = inventory;
        this.inbox = inbox;
    }

    @Transactional
    public void reserveIdempotently(OrderConfirmedEvent event) {
        if (!inbox.tryInsert("inventory", event.eventId())) {
            return;
        }

        inventory.reserve(
                event.orderId(),
                event.aggregateVersion());
    }
}
~~~

`InventoryRepository` and `ProcessedEventRepository` are application-specific; `tryInsert` must execute an atomic insert backed by a unique constraint inside **the same SQL transaction** as `inventory.reserve`. Never perform `SELECT exists` followed by `INSERT` without a unique constraint, as concurrent deliveries race.

With AUTO ACK: the listener invokes the service synchronously; the service returns only after the Spring proxy commits the transaction; then the container ACKs. If COMMIT fails, the handler throws and the message is not ACKed as successful.

### 11.2. Crash After SQL Commit Before Consumer ACK

~~~mermaid
sequenceDiagram
    participant B as RabbitMQ
    participant C as Listener
    participant D as PostgreSQL
    B->>C: Deliver eventId=E-123
    C->>D: INSERT inbox + business update
    D-->>C: COMMIT OK
    C--xB: ACK lost / process crash
    B->>C: Redelivery E-123
    C->>D: Inbox sees E-123 already processed
    C-->>B: ACK duplicate safely
~~~

This is **at-least-once**. It is not a broker bug—it is a normal failure window; unique event IDs and an inbox prevent duplicate business side effects.

### 11.3. ACK Before COMMIT Causes Lost Business Updates

~~~text
Delivery received
    ↓
ACK sent to broker
    ↓
SQL INSERT/UPDATE
    ↓
Process crash or transaction rollback
    ↓
Broker no longer has message to redeliver
~~~

Avoid premature ACKs. If a handler merely submits work to an in-memory executor and returns, `AUTO` may ACK before work runs. To hand off to async workers, **persist a durable work item/outbox** before ACKing the source message.

### 11.4. HTTP Partner Side Effects

If a consumer updates SQL and also calls a Payment API, remote HTTP lies outside the SQL transaction. If Payment succeeds yet the response times out, retries can double-charge. Split into a local SQL inbox + outbox intent, then have a post-commit worker call Payment with an idempotency key and status lookup.

## 12. Prefetch, Concurrency, and Capacity Planning

Prefetch bounds how many **unacked** deliveries RabbitMQ pushes per consumer/channel under QoS semantics. Concurrency controls how many consumers run actively.

Example:

~~~text
concurrency = 4
prefetch = 20
=> up to roughly 80 deliveries in-flight
   (depending on topology, channel/QoS, and runtime)
~~~

This does not mean 80 Java handlers execute in parallel simultaneously. Many deliveries sit buffered in client/container queues awaiting a handler thread.

### 12.1. Sizing Against Downstream Databases

Suppose Inventory Service has:

| Resource | Illustrative Limit |
| --- | ---: |
| Hikari JDBC pool per pod | 12 connections |
| Rabbit listener concurrent consumers | 6 |
| Rabbit prefetch per consumer | 20 |
| Pod replicas | 4 |
| DB max usable connections across service | 60 |

Four pods × 6 consumers = 24 concurrent handlers hitting the DB, aside from HTTP requests/background jobs. A pool of 12 per pod is fine for brief transactions yet exhausts quickly if locks or external calls hold connections open. Four pods × 6 × 20 ≈ 480 theoretical in-flight deliveries, all eligible for redelivery after crashes.

### 12.2. Oversized Prefetch

Risks:

- One consumer hoards deliveries, skewing work distribution.
- Crashes trigger large bursts of redeliveries.
- Increased memory pressure.
- Poison messages stall progress when ordering/retries interact poorly.
- Harder backlog visibility as `ready` drops while `unacked` spikes.

For slow/expensive processing, start with modest prefetch and measure; for fast workloads, raise it only when broker/client round-trips become a measured bottleneck.

### 12.3. Concurrency Does Not Mean Global Ordering

Multiple competing consumers on one queue mean **completion order** will not strictly match publish order. Even when a queue preserves FIFO under narrow conditions, concurrency, priorities, requeues, redeliveries, and retries alter completion order.

If events for the same `orderId` must process versions 1 → 2 → 3 cleanly, enforce aggregate version guards, consistent routing/sharding, or sequential processing strategies. Setting `concurrency=1` reduces single-queue contention yet does not prevent out-of-order replays or multi-instance/multi-queue races.

### 12.4. Exclusive Consumers

RabbitMQ supports an exclusive-consumer flag on a queue; never pair it arbitrarily with `concurrency > 1`. An exclusive consumer grants one connection delivery access per broker rules, yet is not a distributed business lock or an exactly-once guarantee.

## 13. Container Retry vs. Broker Redelivery

A listener failure can be retried **in-process before NACK**, or redelivered by the broker **after requeue**. These are two separate loops.

~~~mermaid
flowchart TD
    D["RabbitMQ delivery"] --> L["Listener invocation"]
    L --> O{"Outcome"}
    O -->|"Success"| A["ACK"]
    O -->|"Transient failure"| R["Bounded local retry / delayed queue"]
    O -->|"Permanent failure"| P["Reject and park/DLQ"]
    R --> L
    R -->|"Budget exhausted"| P
~~~

Never layer unbounded retries at every tier: Spring Retry advice × RabbitMQ requeue × scheduler replay × downstream HTTP retry multiplies attempts, triggering retry storms and duplicates.

### 13.1. Retries Inside the Listener Container

Spring Boot provides properties to enable retry on simple/direct listeners (exact support varies by version):

~~~yaml
spring:
  rabbitmq:
    listener:
      simple:
        retry:
          enabled: true
          max-attempts: 3
          initial-interval: 500ms
          multiplier: 2
          max-interval: 5s
        default-requeue-rejected: false
~~~

This configures **bounded retries** before handing errors to final rejection policy. Ensure an active DLX/DLQ/parking topology exists, because `requeue=false` drops messages when no dead-letter route applies.

Spring Retry executes **local retries** on the consumer thread: during backoff sleeps, that thread/slot remains occupied. For multi-minute delays or frequent poison messages, use a **delayed retry topology** so consumer threads stay free.

### 13.2. Configuring Retry Advice in Code

Example for supporting Spring AMQP / Spring Retry versions:

~~~java
import org.springframework.amqp.rabbit.config.RetryInterceptorBuilder;
import org.springframework.amqp.rabbit.retry.RejectAndDontRequeueRecoverer;
import org.aopalliance.aop.Advice;

Advice retryAdvice =
        RetryInterceptorBuilder.stateless()
                .maxAttempts(3)
                .backOffOptions(500, 2.0, 5000)
                .recoverer(new RejectAndDontRequeueRecoverer())
                .build();

// Inside a named SimpleRabbitListenerContainerFactory bean:
factory.setAdviceChain(retryAdvice);
~~~

This assumes `factory` is already constructed and wired to a connection factory; it is an **alternative** to Boot's retry properties—do not accidentally enable both and multiply attempt counts.

**Stateless retry** suits many simple handlers; with transactional semantics, stateful retry and rollback interactions are trickier. Pick based on contract, test against real DB rollbacks/requeues, and never hold long-running transactions across retry backoffs.

### 13.3. Error Classification

| Error | Retry? | Recommendation |
| --- | --- | --- |
| Invalid JSON / broken schema | Do not hot-retry | DLQ/parking and contract remediation |
| Invalid business state | Usually no | Business rejection/audit |
| Missing authorization / tenant mismatch | No | Security incident |
| SQL deadlock | Yes | Bounded retry of full transaction, idempotent |
| DB temporarily unavailable | Yes | Backoff; monitor pool/availability |
| Downstream HTTP 429/503 | Yes | Backoff, bulkhead, circuit breaker |
| HTTP timeout after side effect | Only if idempotent | Unknown outcome; status lookup |
| Broker channel closed | Container recovery | Never ACK a delivery on a lost channel |
| Duplicate `eventId` already processed | Do not re-apply | ACK cleanly after dedup |

### 13.4. Default Requeue and Poison Messages

If a handler fails and the container continuously requeues, the broker immediately redelivers:

~~~text
Receive invalid JSON
  -> listener/converter throws
  -> requeue
  -> receive same invalid JSON
  -> requeue forever
~~~

Prevent infinite loops by failing fast on permanent errors, capping retry attempts, and routing to DLX/DLQ or delayed retry queues. Spring AMQP provides `ConditionalRejectingErrorHandler` and exceptions like `AmqpRejectAndDontRequeueException`; exact behavior varies across conversion errors, listener exceptions, and configured error handlers/recoverers.

## 14. Dead-Letter Exchanges, DLQs, and Delayed Retries

### 14.1. Illustrative DLX/DLQ

~~~mermaid
flowchart LR
    X["orders.events exchange"] --> Q["inventory.order-confirmed queue"]
    Q -->|"NACK/reject requeue=false"| DLX["orders.dlx"]
    DLX --> DLQ["inventory.order-failed"]
    DLQ --> OPS["Review / replay worker"]
~~~

Example DLX and binding declarations (when application-managed):

~~~java
import org.springframework.amqp.core.*;

@Bean
DirectExchange ordersDlx() {
    return new DirectExchange("orders.dlx", true, false);
}

@Bean
Queue inventoryDeadQueue() {
    return QueueBuilder.durable("inventory.order-failed").build();
}

@Bean
Binding inventoryDeadBinding(
        Queue inventoryDeadQueue,
        DirectExchange ordersDlx) {
    return BindingBuilder.bind(inventoryDeadQueue)
            .to(ordersDlx)
            .with("inventory.order.failed");
}
~~~

Place inside a `@Configuration` class. The primary queue in Section 4 already set `deadLetterExchange("orders.dlx")` and `deadLetterRoutingKey("inventory.order.failed")`; when combining both snippets, keep these names identical.

**A DLQ is never business success.** A dead-lettered message failed required processing and demands alerting, retention, access controls, and replay/reconciliation workflows.

### 14.2. Dead-Letter Durability Considerations

Publisher confirms cover publisher → broker; consumer NACK/Reject and broker dead-lettering have separate semantics depending on queue type and broker version. Never assume every DLX handoff is universally atomic/lossless.

RabbitMQ quorum queues differ from classic queues in dead-lettering options and delivery limits; consult your RabbitMQ version and deployment policies. Without a properly configured DLX on the broker/queue, `requeue=false` can discard messages.

### 14.3. Delayed Retry Topology

You can route to retry queues with TTL + DLX pointing back to the main exchange/queue, or use a delayed-message exchange plugin if supported by the broker. Example:

~~~text
inventory.order-confirmed
   |
   +-- temporary failure → inventory.retry.30s
           (TTL 30s, DLX routes back to main exchange)
   |
   +-- max attempts → inventory.order-failed DLQ
~~~

Maintain a **durable attempt count**, cycle cap, idempotency, and anti-starvation safeguards rather than relying blindly on unverified `x-death` headers. A custom retry publisher must await broker confirmation of publishing to the retry queue before ACKing the source message, or events can be lost in between.

### 14.4. DLQ Replay

When replaying a message after fixing a mapping bug:

1. Verify root cause and schema version.
2. Check whether prior side effects already committed.
3. Preserve the **stable `eventId`**.
4. Republish into approved topology with replay audit metadata.
5. Monitor inbox deduplication and business outcomes.
6. Never purge queues or bulk-modify routing before reconciliation.

## 15. Error Handling Before and After Method Invocation

Not every error reaches a `try/catch` inside `@RabbitListener`:

- **Broker delivery/connection errors:** occur in the container/channel.
- **Message conversion errors:** occur before the method is invoked.
- **Argument resolution/validation errors:** occur while Spring builds method arguments.
- **Business exceptions:** thrown by the method/service.
- **ACK/NACK failures:** occur during or after method completion.
- **Downstream side-effect uncertainty:** HTTP timeouts or unknown transaction commit outcomes.

Therefore, a `try/catch(Exception)` inside the listener **cannot handle full** failure classification. Configure container `ErrorHandler`, retry advice, AMQP recoverers, and DLX policies.

### 15.1. Never Swallow Exceptions and Return Normally

~~~java
@RabbitListener(queues = "inventory.order-confirmed")
public void antiPattern(OrderConfirmedEvent event) {
    try {
        service.reserveIdempotently(event);
    } catch (Exception ex) {
        log.warn("Reservation failed", ex);
        // Wrong: normal return in AUTO mode can ACK the message.
    }
}
~~~

This is an **anti-pattern**. Under `AUTO` mode, returning normally typically causes the container to ACK. When business processing fails, throw so error handling triggers retry/NACK/parking—or **durably** persist the failure to another workflow before allowing ACK.

### 15.2. ErrorHandler and Conversion Errors

Spring AMQP includes `ConditionalRejectingErrorHandler` to identify fatal exceptions (such as conversion failures) in common setups. You can customize fatality detection, though test carefully so transient exceptions are not accidentally rejected nor poison messages requeued forever.

When JSON fails to parse, the listener method may **never run**; unit tests invoking the method directly miss production behavior. Test with invalid Content-Type headers, untrusted TypeId headers, and payloads missing schema fields.

### 15.3. Protocol Errors Differ from Domain Errors

If a queue is missing, connections are refused, or the consumer lacks `read` rights, fix topology/ACLs/credentials. Never retry individual messages at the business layer to overcome an AMQP connection failure.

When domain validation fails, record rejections/parking per contract; never relax queue permissions to "fix" bad data.

## 16. Idempotency and the Transactional Inbox

At-least-once delivery means **duplicates are normal**:

~~~mermaid
sequenceDiagram
    participant B as RabbitMQ
    participant C as Listener
    participant D as PostgreSQL
    B->>C: Deliver E-100
    C->>D: INSERT processed_event + business mutation
    D-->>C: COMMIT
    C--xB: ACK lost
    B->>C: Redeliver E-100
    C->>D: INSERT eventId conflict → already processed
    C-->>B: ACK duplicate
~~~

### 16.1. Database Inbox Table

~~~sql
CREATE TABLE processed_integration_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Each logical consumer independently processes the same event; keying by `(consumer_name, event_id)` lets Inventory and Billing both handle the same event safely.

### 16.2. Sharing the SQL Transaction with Business Updates

~~~java
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryReservationService {

    private final JdbcTemplate jdbc;

    public InventoryReservationService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void reserveIdempotently(OrderConfirmedEvent event) {
        int inserted = jdbc.update(
                """
                INSERT INTO processed_integration_events(
                    consumer_name, event_id, processed_at)
                VALUES ('inventory', ?, CURRENT_TIMESTAMP)
                ON CONFLICT (consumer_name, event_id) DO NOTHING
                """,
                UUID.fromString(event.eventId()));

        if (inserted == 0) {
            return; // Duplicate: business update already committed earlier.
        }

        jdbc.update(
                """
                INSERT INTO inventory_reservations(
                    order_id, source_version, state)
                VALUES (?, ?, 'RESERVED')
                ON CONFLICT (order_id)
                DO UPDATE
                   SET source_version = EXCLUDED.source_version,
                       state = EXCLUDED.state
                 WHERE inventory_reservations.source_version
                       < EXCLUDED.source_version
                """,
                event.orderId(),
                event.aggregateVersion());
    }
}
~~~

This PostgreSQL example assumes `inventory_reservations` was migrated with a unique `order_id` and appropriate `source_version`. Production systems need full domain rules for quantities and stock, not merely a `RESERVED` state.

**Crucial:** `INSERT inbox` and the reservation update must share **the same transaction**. If the SQL update fails, the inbox insert must roll back too; otherwise, redeliveries would skip processing even though the business change never took effect.

### 16.3. Out-of-Order Is Different from Duplicate

Two distinct events with `eventId=E-1` and `eventId=E-2` can share the same `orderId` with different versions. The inbox blocks E-1 from applying twice, yet **does not stop** E-1 from arriving after E-2. Enforce `aggregateVersion`/conditional updates and domain ordering rules.

### 16.4. EventId Is Not Delivery Tag

`AmqpHeaders.DELIVERY_TAG` is a channel-scoped delivery counter that changes on redelivery; **never** use it as a business dedup key. Likewise, `traceId` can change across attempts; require a stable upstream `eventId`/`operationId` in the data contract.

## 17. Message Schemas, Versioning, and Security

An event contract should carry:

~~~java
public record OrderConfirmedEvent(
        String eventId,
        String orderId,
        long aggregateVersion,
        java.time.Instant occurredAt) {
}
~~~

Preferably include explicit `eventType` and `schemaVersion` in an envelope or header when one queue carries multiple event types. Consumers may run mixed versions during rollouts, requiring compatibility discipline:

- New optional fields: older consumers ignore unknown fields per forward-compatibility policy.
- Breaking changes: introduce a new schema version instead of silently altering old fields.
- Unknown enums: reject/park with a clear reason or use controlled fallbacks.
- Decimals/Instants/timezones: specify exact formats.
- Idempotency key: immutable across replays.
- JSON size/depth and field validation: enforce bounds before business logic.

### 17.1. Never Trust Untrusted Producers

Broker ACLs restrict who can publish, yet event headers and payloads still cross trust boundaries and must be validated. Never trust `tenantId`/`role`/`permissions` from raw JSON as credentials bypassing authorization. Restrict trusted converter type mappings, enforce MIME/content types, and disable unsafe deserialization.

### 17.2. TLS, SASL/Credentials, and Vhost Permissions

RabbitMQ enforces virtual hosts, permissions, and TLS. Consumers typically need:

- `read` permission on queues, plus declaration/binding permissions only if app-managed topology is used.
- Exact connection URI and vhost.
- TLS trust, hostname verification, and client certificates for mTLS.
- Secret manager integration for usernames, passwords, and private keys.
- Network egress policies; never expose management ports publicly on the internet.

Never log full `amqp://user:password@host/vhost` URIs; never disable TLS verification to bypass certificate errors.

## 18. Listener Lifecycle and RabbitListenerEndpointRegistry

Listener containers normally start on application context refresh when auto-startup is enabled. Control lifecycle programmatically via `RabbitListenerEndpointRegistry`:

~~~java
import org.springframework.amqp.rabbit.listener.RabbitListenerEndpointRegistry;
import org.springframework.amqp.rabbit.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@Component
public class RabbitListenerOperations {

    private final RabbitListenerEndpointRegistry registry;

    public RabbitListenerOperations(
            RabbitListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public boolean isRunning(String id) {
        MessageListenerContainer container =
                registry.getListenerContainer(id);
        return container != null && container.isRunning();
    }

    public void stop(String id) {
        MessageListenerContainer container =
                registry.getListenerContainer(id);
        if (container != null) {
            container.stop();
        }
    }

    public void start(String id) {
        MessageListenerContainer container =
                registry.getListenerContainer(id);
        if (container != null) {
            container.start();
        }
    }
}
~~~

`getListenerContainer(id)` takes the `@RabbitListener` ID, not the queue name. The registry primarily manages containers registered through endpoint annotation infrastructure; manually registered custom container beans may follow separate lifecycle management.

### 18.1. Pause/Stop and Graceful Shutdown

During rolling deployments:

1. Stop accepting new deliveries or stop listener containers via lifecycle hooks.
2. Let in-flight handlers finish within the shutdown grace period.
3. ACK only messages whose business work committed; never ACK pending in-memory work.
4. If shutdown interrupts before ACK, the broker redelivers safely thanks to idempotency.
5. Verify consumer counts and unacked counts after rollout.
6. Never purge queues as a routine deployment step.

Container shutdown timeouts and cancellation semantics vary by implementation/version. For handlers running several minutes, align Kubernetes `terminationGracePeriodSeconds`, JVM shutdown timeouts, and RabbitMQ consumer cancellation accordingly.

### 18.2. Dynamic Scaling

SMLC can scale concurrent consumers dynamically per configuration; DMLC adjusts consumers per queue. Never raise concurrency without bounds in production to "clear a backlog": broker, JDBC pools, CPU, and downstream HTTP services all have capacity ceilings.

## 19. Batch Listeners and Synchronous/Asynchronous Processing

Spring AMQP supports batch-oriented consumption via matching factory settings and method signatures. However, batch semantics **differ from per-message processing**:

- If one record in a batch fails, specify ACK/NACK scope clearly.
- Enforce per-event idempotency, not just per-batch ID.
- Keep authorization/context isolated if a batch spans multiple tenants.
- Commit transactions per batch or per item according to domain semantics.
- Balance prefetch and batch size carefully.

### 19.1. Async Listener Trap

~~~java
@RabbitListener(queues = "inventory.order-confirmed")
public void unsafeAsync(OrderConfirmedEvent event) {
    executor.submit(() -> service.reserveIdempotently(event));
    // Method returns immediately -> AUTO may ACK before the task even runs.
}
~~~

This is an **anti-pattern** when `executor` is an in-memory queue and at-least-once processing is required. For non-blocking execution, use async return types/ack modes explicitly supported by your Spring AMQP version **and** verify ACKs wait for async completion—or persist a durable work item before ACKing.

### 19.2. Async Return Types and Manual Ack Are Version-Sensitive

Certain Spring AMQP versions support async listener methods returning `CompletableFuture` or Reactor types and adjust ack behavior automatically; semantics vary by version and container config. Never copy a `@RabbitListener public Mono<Void> ...` snippet assuming MVC controller behavior—test ACK timing, exception propagation, requeue, and shutdown explicitly.

## 20. Request/Reply with @RabbitListener

`@RabbitListener` can return a value and use `@SendTo` or `replyTo` to send an AMQP response. However, broker-based request/reply still incurs timeouts, correlation IDs, and duplicate risks, and does not automatically replace synchronous HTTP APIs.

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.messaging.handler.annotation.SendTo;

@RabbitListener(queues = "pricing.calculate")
@SendTo("pricing.responses")
public PriceResult calculate(PriceRequest request) {
    return pricingService.calculate(request);
}
~~~

`PriceResult`, `PriceRequest`, and `pricingService` are application-specific. Reply routing and correlation depend on `replyTo` headers and `RabbitTemplate` RPC configuration; `@SendTo` addresses must match the exchange/routing contract. Never treat a reply as a distributed transaction ACK or proof of exactly-once execution.

### 20.1. Drawbacks of RPC Over a Broker

- Consumers may be slow or temporarily unavailable.
- Callers may time out after the handler already committed.
- Reply messages may be lost or misrouted if topology is wrong.
- Tightly couples caller latency to downstream processing.
- Retries risk duplicating side effects.

Unless synchronous semantics are strictly required, event-driven messaging paired with completion events or status APIs is usually more resilient.

## 21. Multi-Layer Testing

### 21.1. Unit Testing the Business Service

Unit tests for `InventoryReservationService` should verify:

- New events create reservations.
- Duplicate `eventId` does not create a second reservation.
- Lower versions never overwrite higher versions.
- Invalid domain states are rejected.
- DB exceptions roll back both inbox and business updates.

Unit tests can mock dependencies, yet **cannot verify RabbitMQ ACK timing**, converters, or actual SQL unique constraints.

### 21.2. Mocking/Calling the Listener Method Directly Is Not Enough

Calling directly:

~~~java
listener.onOrderConfirmed(
        new OrderConfirmedEvent(
                "E-1", "ORD-1", 1, Instant.now()));
~~~

only exercises a Java method. It bypasses exchanges/routing, containers, message conversion, prefetch, ACK/NACK, retries, and DLX. Use it only for simple orchestration checks, never as a substitute for RabbitMQ integration tests.

### 21.3. RabbitMQ Testcontainers

Boot 3.1+ Testcontainers example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.springframework.amqp.rabbit.core.RabbitTemplate;

@SpringBootTest
@Testcontainers
class OrderRabbitIntegrationTest {

    @Container
    @ServiceConnection
    static RabbitMQContainer rabbit =
            new RabbitMQContainer("rabbitmq:3-management");

    @Autowired
    RabbitTemplate rabbitTemplate;

    @Test
    void publishesToOrdersExchange() {
        rabbitTemplate.convertAndSend(
                "orders.events",
                "order.confirmed",
                new OrderConfirmedEvent(
                        "TEST-E-1", "TEST-O-1", 1,
                        java.time.Instant.now()));

        // Assert business side effects by polling DB/inbox
        // (never rely on fixed Thread.sleep as proof).
    }
}
~~~

This is an **integration-test skeleton**: wire in real converters, topology, a SQL test database, and real assertions so tests fail when broken. Never consider a publish-only test with no consumer business-state assertions complete.

### 21.4. Test Matrix

| Test Case | What Must Be Verified |
| --- | --- |
| Valid queue/binding | Routing key delivers message to intended listener |
| Missing queue | Container startup/retry/errors behave observably |
| Valid JSON body | Typed DTO converts accurately |
| Invalid JSON schema | Rejected/parked per policy without infinite requeue |
| AUTO ack + DB commit | Message ACKed after handler succeeds |
| DB rollback | Not ACKed as success; retry/DLQ triggers properly |
| DB commit + lost ACK | Redelivery deduplicated by inbox |
| MANUAL ack | `basicAck` on matching channel/tag after commit |
| MANUAL nack | DLX routing works without unintended message loss |
| Prefetch/concurrency | Active handlers and unacked counts stay within budget |
| Duplicate `eventId` | Side effect applied only once |
| Out-of-order `aggregateVersion` | Projection never regresses to older version |
| Rabbit broker disconnect | Container recovers and redelivers safely |
| DLQ replay | `eventId` remains stable; audit/reconciliation accurate |
| Graceful shutdown | In-flight messages finish or redeliver safely |
| TLS/credentials/ACLs | Negative tests for CA, vhost, and read permissions |

### 21.5. Never Run Chaos/Load Tests Against Live Production Queues

Load/chaos suites create backlogs, consume resources, and push synthetic data into DLQs. Use isolated test environments, dedicated permissions, synthetic events, and automated cleanup.

### 21.6. RabbitListenerTestHarness

Spring AMQP offers test harnesses for listener annotations in supporting versions. They help verify invocations and spy on listeners, yet still do not replace broker/transport/DB integration tests for transactions, ACK timing, or DLX.

## 22. Listener Observability and Metrics

In production, track **when messages enter queues, get delivered, get processed, get ACKed, or get stuck** across layers.

| Signal | Layer | Meaning |
| --- | --- | --- |
| Queue messages ready | RabbitMQ | Deliveries waiting to be dispatched |
| Queue messages unacked | RabbitMQ | Dispatched deliveries awaiting ACK |
| Consumer count | RabbitMQ | Active subscribed consumers |
| Channel/connection count | RabbitMQ | AMQP resource footprint |
| Listener invocation latency p95/p99 | Spring AMQP/app | Handler duration |
| Listener errors by type | Application | Schema, business, SQL, downstream errors |
| Retry attempt count | Container/retry | Recovery activity |
| DLQ depth/age | RabbitMQ | Events needing investigation |
| Inbox duplicate count | SQL/application | Redeliveries caught by dedup |
| End-to-end confirmation lag | Business | Publish intent to business state applied |

A queue showing `messages_ready=0` with `messages_unacked=1000` does not mean processing is caught up; consumers may be hoarding deliveries, blocked on an exhausted DB pool, or hung.

### 22.1. Micrometer and Observations

Recent Spring AMQP versions can publish listener timers/observations via Micrometer/Observation. `observationEnabled`, Micrometer, and Actuator behavior depend on Spring AMQP/Boot versions and factory implementations; when customizing factories, ensure the configurer applies observation settings.

Do not assume every business metric appears automatically just by adding `spring-boot-starter-actuator`. To track business application, instrument services right after SQL commit or via durable event audits.

### 22.2. Cardinality and Sensitive Data

Keep tags low-cardinality: `listener=inventory-order-consumer`, `queue=inventory.order-confirmed`, `outcome=applied/duplicate/retry/dlq`. Never put `eventId`, `orderId`, emails, tokens, or raw XML/JSON into Prometheus labels. Logs may carry redacted correlation IDs under strict access control and retention—never dump raw bodies arbitrarily.

### 22.3. Broker ACK Differs from Business Success

A consumer-ACKed message might be a deduplicated replay, a permanently invalid message parked successfully, or a genuine business update. Separate metrics accordingly:

~~~text
consumer.delivered
consumer.business_applied
consumer.duplicate
consumer.rejected
consumer.dlq_parked
consumer.ack_failed
~~~

Only `consumer.business_applied` or reliable completion events belong on a business dashboard reporting "inventory synchronized."

## 23. Runbook for Diagnosing @RabbitListener Not Receiving Messages

| Symptom | Common Cause | Check |
| --- | --- | --- |
| No listener logs | Annotation infrastructure inactive, wrong queue/bean | `@RabbitListener`, registry ID, Boot config |
| Listener fails to start | Broker down, wrong vhost/ACL, missing queue | Container startup/recovery logs |
| `PRECONDITION_FAILED` | Queue declaration mismatches existing topology | Durable/queue type/DLX/TTL arguments |
| Queue ready climbing | Absent/slow consumers, stopped listener | Consumer count, container state |
| Queue unacked climbing | Slow handler, missing ACK, excessive prefetch | DB pool, thread dumps, ACK mode |
| Messages never reach queue | Wrong exchange/routing key/binding | Publisher returns, exchange bindings |
| Payload conversion failure | Wrong Content-Type, TypeId, or JSON schema | Converter/class mapper, DLQ |
| Requeue loop | `default-requeue-rejected` or `nack requeue=true` | Retry/DLX config |
| One message processed multiple times | Crash after DB COMMIT before ACK | Inbox `eventId` dedup |
| Out-of-order events | Competing consumers or requeues | Aggregate version guard |
| Rabbit channel error | ACK on wrong tag/channel, shutdown race | Manual ACK code, channel lifecycle |
| Consumer fails to scale | Concurrency/prefetch/broker capacity | SMLC vs. DMLC settings |
| DLQ empty despite rejections | Missing DLX or broken binding | Topology and broker policies |
| Cache/DB not updated | Listener ACKed before async task ran | Durable handoff, business completion |
| Downstream HTTP timeout | Unknown side-effect outcome | Idempotency / status lookup |
| TLS handshake fails | Wrong CA/SAN/client certificate | TLS config, trust, hostname |
| Consumer 403 / access refused | Broker vhost permissions/ACL issue | Service credentials, read/configure rights |

### 23.1. Investigation Order

1. Confirm the publisher actually sent to the right exchange/routing key with confirms/returns enabled.
2. Inspect RabbitMQ queue ready/unacked counts, consumer count, and bindings.
3. Verify application config, `@RabbitListener` ID, queue name, and factory bean names.
4. Inspect factory type, concurrency, prefetch, and ack mode.
5. Check converter, content-type, and schema version.
6. Verify SQL transactions, inbox, idempotency, and business state.
7. Inspect retries, DLX/DLQ, and poison-message handling.
8. Inspect network, TLS, ACL, and channel errors.
9. Trace a single intent via redacted `eventId`/`traceId`.
10. Replay safely only after identifying the exact failure window.

**Never clear backlogs via purge/force-ack** before reconciling business effects; doing so destroys recovery evidence.

## 24. Common Anti-Patterns

| Anti-Pattern | Why It Is Wrong | Better Approach |
| --- | --- | --- |
| Treating `@RabbitListener` as just a method callback | Ignores containers/ACK/lifecycle | Govern via factories and registry |
| Creating a custom factory without Boot's configurer | Drops converter/retry/metrics setup | Configure via Boot first, then override |
| Applying SMLC `maxConcurrency` to DMLC | Wrong concurrency model | Use DMLC `consumersPerQueue` |
| Reading `AUTO` as broker auto-ack | Causes data loss / broken error paths | Understand `AUTO` vs. `NONE` |
| ACKing inside the method before SQL COMMIT | Crash loses business updates | ACK after commit / durable handoff |
| Returning normally after catching exceptions | `AUTO` ACKs as success | Throw or park durably |
| Submitting to an in-memory executor and returning | ACKs before task execution | Durable queue/outbox |
| Infinitely requeuing poison messages | Retry storms and high CPU | DLQ, backoff, retry limits |
| NACK `requeue=false` with no DLX | Silently drops messages | Verify DLX routing |
| Sharing one queue between two services needing both copies | Competing consumers split messages | Dedicated queue per service |
| Using `deliveryTag` as an idempotency key | Tag changes on redelivery | Stable `eventId` |
| Omitting version guards | Stale events overwrite newer state | `AggregateVersion`/conditional update |
| Raising prefetch/concurrency unboundedly | Overloads DB and broker | Capacity budget / bulkheads |
| Storing a global `Channel` across threads | Breaks channel lifecycle / ACK tags | Let the container manage channels |
| Only testing direct listener method calls | Misses converters/ACK/DLX | RabbitMQ Testcontainers |
| Treating publisher confirm as consumer processed | Wrong delivery semantics | Business completion metrics |
| Exposing broker credentials in logs/metrics | Security leak | Secret manager / redaction |

## 25. Pre-Operations Checklist

- [ ] `@RabbitListener` specifies exact queue/binding and a stable listener ID.
- [ ] Queue/exchange/binding ownership is clear (IaC or app) without conflicting declarations.
- [ ] Default/named factories use accurate bean names and the intended Simple/Direct type.
- [ ] Custom factories apply Boot's configurer or explicitly map all required settings.
- [ ] `ConnectionFactory`, TLS, vhost, credentials, and permissions are properly configured.
- [ ] Converters enforce safe schema/type mappings without trusting arbitrary `TypeId` headers.
- [ ] `AUTO`/`MANUAL`/`NONE` match intended broker ACK semantics.
- [ ] Synchronous listeners finish business transactions before ACK.
- [ ] Manual ACK handlers cover both success and error paths cleanly, including shutdown.
- [ ] `Prefetch × concurrency × replicas` fits within DB and broker capacity budgets.
- [ ] Inbox/unique `eventId` and version guards protect against replays and out-of-order events.
- [ ] Permanent errors never requeue forever; transient errors obey retry budgets.
- [ ] DLX/DLQ/retry topology exists and is verified against a real broker.
- [ ] Messages parked in DLQ are never counted as business success.
- [ ] Never ACK prior to durable async handoff.
- [ ] Avoid non-rollbackable HTTP side effects inside DB transactions wherever possible.
- [ ] Testcontainers tests cover routing, converters, ACK/NACK, recovery, redelivery, and DLQ.
- [ ] Graceful shutdown configured and unacked counts verified after rolling deploys.
- [ ] Metrics track queue ready/unacked, consumers, business applied, retries, DLQ, and duplicates.
- [ ] Logs and metrics exclude credentials, PII, and raw sensitive payloads.

**Key takeaway:** `@RabbitListener` defines the **message-receiving endpoint**; `RabbitListenerContainerFactory` defines **how the runtime is built and configured**; and `MessageListenerContainer` manages **consumers, channels, lifecycle, and ACK/NACK**. `SimpleRabbitListenerContainerFactory` fits common min/max concurrency setups, whereas `DirectRabbitListenerContainerFactory` offers its own consumers-per-queue and thread model. Whichever you choose, Spring Boot integration reliability rests on **clean transaction boundaries, inbox/idempotency, bounded retries/DLQ, testing failure windows, and observability from broker to business state**.

## References

- [Spring AMQP — @RabbitListener Annotation](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven.html): method signatures, endpoint registration, `@RabbitHandler`.
- [Spring AMQP — Listener Containers](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-consumer.html): Simple/Direct containers, concurrency, ack modes.
- [Spring AMQP — Listener Concurrency](https://docs.spring.io/spring-amqp/reference/amqp/listener-concurrency.html): SMLC concurrency and DMLC consumers per queue.
- [Spring AMQP — Message Converters](https://docs.spring.io/spring-amqp/reference/amqp/message-converters.html): JSON conversion, type inference, and trusted types.
- [Spring AMQP — Resilience and Recoverer](https://docs.spring.io/spring-amqp/reference/amqp/resilience-recovering-from-errors-and-broker-failures.html): retries, errors, recoverers, container recovery.
- [Spring AMQP — Acknowledgement and Transactions](https://docs.spring.io/spring-amqp/reference/amqp/transactions.html): channel transactions and Spring transaction integration.
- [Spring AMQP — Connections](https://docs.spring.io/spring-amqp/reference/amqp/connections.html): `CachingConnectionFactory` and `RabbitAdmin`.
- [Spring Boot — RabbitMQ](https://docs.spring.io/spring-boot/reference/messaging/amqp.html): starter, listener factory auto-configuration, and properties.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): publisher vs. consumer ACK/NACK.
- [RabbitMQ — Consumer Prefetch](https://www.rabbitmq.com/docs/consumer-prefetch): QoS, unacked windows, and throughput.
- [RabbitMQ — Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx): reject, TTL, DLX routing, and broker policies.
- [RabbitMQ — Queues](https://www.rabbitmq.com/docs/queues): durable/queue type/topology declarations.
- [Testcontainers — RabbitMQ](https://java.testcontainers.org/modules/rabbitmq/): integration tests with RabbitMQ.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): local transactions, rollback semantics.
- [Enterprise Integration Patterns — Idempotent Receiver](https://www.enterpriseintegrationpatterns.com/patterns/messaging/IdempotentReceiver.html): event deduplication and at-least-once processing.
