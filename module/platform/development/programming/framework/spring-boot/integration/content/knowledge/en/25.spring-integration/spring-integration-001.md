# Spring Integration and Enterprise Integration Patterns

## Objectives and Context

When a Spring Boot system receives HTTP requests, reads from a database, calls external services, updates a cache, and publishes messages through a broker, the processing code can easily become a tightly coupled chain of calls. A small change in data format, retry mechanism, or processing order can affect multiple adapters.

**Spring Integration** provides a model for connecting components using **messages**, **channels**, and **endpoints**, implementing many *Enterprise Integration Patterns* (EIP). Instead of writing all forwarding, filtering, transformation, and routing logic by hand, the application configures an **integration flow** composed of steps with clear responsibilities.

This lesson belongs to the **SPRING_BOOT_INTEGRATION** module and the **Spring Integration** chapter. The goal of the module is to organize integrations across HTTP clients, databases, caches, message brokers, and adapters, with a focus on configuration, data contracts, transactions, errors, duplicate handling, testing, and observing real flows.

After this lesson, you will be able to:

- Explain how `Message`, `MessageChannel`, endpoints, and an integration flow relate to one another.
- Recognize core EIP patterns: Gateway, Transformer, Filter, Router, Splitter, Aggregator, Service Activator, and Channel Adapter.
- Create a flow using the Spring Integration Java DSL in Spring Boot.
- Choose synchronous, asynchronous, or queued channels based on business requirements.
- Design error boundaries, transactions, idempotency, retries, security, and tests.

> **Scope:** Spring Integration helps connect and orchestrate integration steps. An in-JVM channel **does not automatically become a durable message broker**, and a flow **does not automatically guarantee exactly-once delivery, distributed transactions, or ordered processing**.

## 1. The Enterprise Integration Problem and EIP Thinking

Consider a system that receives an `OrderReceived` event from an internal API:

1. Ingest the event with `eventId`, `orderId`, and order amount.
2. Validate and normalize the data.
3. Route the order by type or amount threshold.
4. Persist the order state to the database and publish an event for the shipping system.
5. Handle connection errors, retry safely, and avoid re-applying already processed events.
6. Monitor processing duration, failure counts, and event backlogs.

If all of this is placed into a single HTTP controller, the controller code will have to know about data schemas, the broker, error policies, and transactions. EIP defines distinct roles along the path of a message.

~~~mermaid
flowchart LR
    A["HTTP / broker / file"] --> B["Inbound adapter / Gateway"]
    B --> C["Message channel"]
    C --> D["Filter & Transformer"]
    D --> E{"Router"}
    E -->|"Standard order"| F["Order handler"]
    E -->|"Priority order"| G["Priority handler"]
    F --> H["DB + outbox"]
    G --> H
    H --> I["Broker outbound adapter"]
    D -.-> J["Error handling / observability"]
    E -.-> J
~~~

The diagram above is a **reference architecture**; it does not mean the components automatically provide retries, outbox, or transactions. Those policies must be configured and verified separately.

Key concepts:

| Concept | Role | Example |
| --- | --- | --- |
| **Message** | Carries a payload along with headers | `OrderReceived` + `eventId`, `correlationId` |
| **Channel** | Connects steps and defines how messages are handed off | `DirectChannel`, `QueueChannel` |
| **Endpoint** | Receives messages and invokes processing, transformation, routing, or I/O logic | Service Activator, Transformer |
| **Gateway** | Lets business code invoke a flow through an interface | `orderGateway.submit(order)` |
| **Channel Adapter** | Connects external sources/destinations to the message flow | HTTP, file, JDBC, Kafka |
| **IntegrationFlow** | Declares channels/endpoints and the paths between them | Java DSL `IntegrationFlow.from(...)` |

**Distinguishing from a broker:** Spring Integration can work with RabbitMQ, Kafka, JMS, and many other transports through adapters. By default, a `DirectChannel` or `QueueChannel` operates only inside the application. Never assume that a message successfully passed to `send()` on an internal channel is safely persisted on disk or delivered to an external system.

## 2. Messages, Headers, and Data Contracts

In Spring Messaging, a message takes the form `Message<T>`, consisting of:

- **Payload:** strongly typed business content, such as `OrderReceived`.
- **Headers:** metadata used for routing, request/reply correlation, error handling, transport, or observability.

Example of creating a message:

~~~java
import java.math.BigDecimal;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<OrderReceived> message =
        MessageBuilder.withPayload(
                new OrderReceived(
                        "evt-1001",
                        "ORD-42",
                        new BigDecimal("129.00")))
                .setHeader("tenantId", "tenant-a")
                .setHeader("correlationId", "corr-42")
                .build();
~~~

The `OrderReceived` type will be defined in the Java DSL example section. The `id` and `timestamp` headers are generated by the messaging infrastructure to identify a message **during processing**; they do not replace the `eventId` provided by the source system to prevent duplicate processing across redeliveries.

Some headers with infrastructure semantics:

| Header | Meaning | Things to remember |
| --- | --- | --- |
| `id`, `timestamp` | Message metadata | Do not use as an idempotency key across transports if the message is recreated |
| `replyChannel` | Destination for a request-reply flow's response | May be a temporary channel reference |
| `errorChannel` | Destination for error routing in supported contexts | Synchronous and asynchronous errors must be tested differently |
| `correlationId` | Groups related messages together | Trust the value only when the source is controlled |
| `sequenceNumber`, `sequenceSize` | Supports message grouping during split/aggregate | Does not replace broker ordering contracts |
| Application headers such as `tenantId` | Passes context needed for processing | Authenticate/authorize before trusting; avoid leaking to external destinations |

Spring Messaging provides an immutable `Message` model in the sense that payload and headers are not replaced directly in place, though the object inside the payload can still be mutable. Prefer immutable DTOs/records. When you need to change a payload or header, use `MessageBuilder.fromMessage(...)` or a Transformer/Header Enricher step; do not mutate data directly when multiple branches may be sharing it.

A good integration contract should specify: schema and version, required fields, currency units, timezone, acceptance conditions, backward-compatibility strategy, duplicate detection mechanism, failure semantics, and redelivery capability.

## 3. Setup and Integration with Spring Boot

In a Spring Boot application using Gradle (Groovy DSL):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
}
~~~

The starter provides the core components needed to build an integration flow. **Protocol-specific adapters** may require separate dependencies, such as `spring-integration-http`, `spring-integration-jdbc`, `spring-integration-amqp`, or `spring-integration-kafka`, in addition to the corresponding client/broker libraries and connection configuration. There is no need to add every adapter if the flow only processes internal messages.

Spring Boot provides auto-configuration for Spring Integration and initializes the infrastructure when the appropriate dependencies are on the classpath. In a plain Spring Framework application without Boot, configuration typically requires an explicit `@EnableIntegration`.

For Spring to discover interfaces annotated with `@MessagingGateway` in the same package or subpackages, add `@IntegrationComponentScan` to a configuration class:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;

@Configuration(proxyBeanMethods = false)
@IntegrationComponentScan
public class IntegrationGatewayScanConfiguration {
}
~~~

Standard `@ComponentScan` does not register proxies for `@MessagingGateway` interfaces through class scanning alone. If an interface is outside the scanned packages, specify the appropriate `basePackageClasses`/`basePackages` or import the interface using the mechanism supported by your Spring Integration version.

**API note:** the Java DSL examples use `IntegrationFlow.from(...)` from modern Spring Integration (6.x/7.x). Older documentation may use `IntegrationFlows.from(...)`. When copying snippets from older articles, check them against the Spring Integration version managed by your Spring Boot release; avoid overriding the library version manually.

## 4. End-to-End Example: Building an Order Event Processing Flow

Suppose the system has a gateway receiving `OrderReceived` and a business handler `OrderHandler`. This example uses only the core Spring Integration module and can run synchronously in a single process. Persistence to a DB or broker belongs to actual adapters and is not included in the snippet.

### 4.1. Defining the Data Types

~~~java
// OrderReceived.java
import java.math.BigDecimal;

public record OrderReceived(
        String eventId,
        String orderId,
        BigDecimal amount) {
}
~~~

~~~java
// NormalizedOrder.java
import java.math.BigDecimal;

public record NormalizedOrder(
        String eventId,
        String orderId,
        BigDecimal amount) {
}
~~~

These two DTOs illustrate an **input contract** and **normalized data**. A real system should include schema/versioning, currency specification, and stricter validation rules.

### 4.2. Creating a Messaging Gateway

~~~java
// OrderEventGateway.java
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(defaultRequestChannel = "orders.input")
public interface OrderEventGateway {
    void submit(OrderReceived event);
}
~~~

Spring Integration generates a proxy implementation for the gateway interface. Business code simply calls:

~~~java
orderEventGateway.submit(
        new OrderReceived(
                "evt-1001", " ORD-42 ",
                new java.math.BigDecimal("129.00")));
~~~

With a synchronous `DirectChannel` flow as shown below, the call typically returns only after the handlers finish; exceptions from a handler can propagate back to the caller. **A `void` method does not mean the message was durably persisted or processed asynchronously.**

### 4.3. Creating a Transformer and Business Handler

~~~java
// OrderNormalizer.java
import org.springframework.stereotype.Component;

@Component
public class OrderNormalizer {

    public NormalizedOrder normalize(OrderReceived source) {
        return new NormalizedOrder(
                source.eventId().trim(),
                source.orderId().trim(),
                source.amount());
    }
}
~~~

~~~java
// OrderHandler.java
import org.springframework.stereotype.Component;

@Component
public class OrderHandler {

    public void handle(NormalizedOrder order) {
        // Example: call an application service to apply the business command.
        // A real implementation needs persistence/idempotency and error handling.
        System.out.println("Order received: " + order.orderId());
    }
}
~~~

`System.out.println` is only used to make the flow visible in this lesson. Production systems require real business logic and structured logging without indiscriminately logging sensitive payloads.

### 4.4. Declaring the Flow with the Java DSL

~~~java
// OrderIntegrationConfiguration.java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration(proxyBeanMethods = false)
public class OrderIntegrationConfiguration {

    @Bean
    IntegrationFlow orderIntegrationFlow(
            OrderNormalizer normalizer,
            OrderHandler handler) {

        return IntegrationFlow.from("orders.input")
                .<OrderReceived>filter(
                        order -> order.eventId() != null
                                && !order.eventId().isBlank()
                                && order.orderId() != null
                                && !order.orderId().isBlank()
                                && order.amount() != null
                                && order.amount().signum() > 0,
                        spec -> spec.throwExceptionOnRejection(true))
                .handle(normalizer, "normalize")
                .handle(handler, "handle")
                .get();
    }
}
~~~

How it works:

1. The gateway sends `OrderReceived` to the channel named `orders.input`.
2. The **Filter** checks basic conditions; because `throwExceptionOnRejection(true)` is set, invalid records throw an error instead of being silently dropped.
3. The **Transformer** invokes `OrderNormalizer.normalize(...)`, producing `NormalizedOrder`.
4. The **Service Activator** invokes `OrderHandler.handle(...)` to perform final processing.
5. `get()` completes the flow definition. Spring registers the required endpoints and channels in the application context.

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant G as OrderEventGateway
    participant F as Filter
    participant T as OrderNormalizer
    participant H as OrderHandler
    C->>G: submit(OrderReceived)
    G->>F: Message<OrderReceived>
    alt Valid
        F->>T: OrderReceived
        T->>H: NormalizedOrder
        H-->>G: Processing complete
        G-->>C: return
    else Invalid
        F-->>G: Exception
        G-->>C: Exception
    end
~~~

Key takeaway: the flow uses `DirectChannel` instances between endpoints by default in the Java DSL, so this path runs **synchronously on the caller's thread**. It demonstrates EIP without hiding when work actually begins and completes.

### 4.5. Connecting HTTP to the Gateway When Needed

If `spring-boot-starter-web` is present, an MVC controller can receive an HTTP request and call the gateway:

~~~java
// OrderEventController.java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderEventController {

    private final OrderEventGateway gateway;

    public OrderEventController(OrderEventGateway gateway) {
        this.gateway = gateway;
    }

    @PostMapping("/internal/order-events")
    public ResponseEntity<Void> receive(
            @RequestBody OrderReceived event) {
        gateway.submit(event);
        return ResponseEntity.noContent().build();
    }
}
~~~

This snippet represents **HTTP inbound → Gateway → flow**. It does not use Spring Integration's HTTP inbound channel adapter and does not make the call asynchronous. Validation errors, business errors, and downstream failures must be mapped intentionally to HTTP statuses using the application's exception handling mechanism. Only return `202 Accepted` when there is a reliable asynchronous acceptance mechanism matching the API contract.

## 5. Commonly Used Enterprise Integration Patterns

| EIP | Design question | Spring Integration mechanism | Notes |
| --- | --- | --- | --- |
| **Message Channel** | How are messages passed between steps? | `MessageChannel`, `DirectChannel`, `QueueChannel` | Synchronicity, durability, and buffering depend on the channel |
| **Messaging Gateway** | How does business logic invoke the flow? | `@MessagingGateway` / `@Gateway` | Can be request-reply or one-way |
| **Transformer** | How are DTOs/schemas normalized? | `transform(...)`, `@Transformer` | Needs a contract across version transitions |
| **Filter** | Should this message be accepted? | `filter(...)`, `@Filter` | Explicitly define discard vs. exception |
| **Content-Based Router** | Which branch should the message take? | `route(...)`, `@Router` | Include a default route to avoid losing messages |
| **Service Activator** | Where is business logic invoked? | `handle(...)`, `@ServiceActivator` | Side effects need transactions/idempotency |
| **Splitter** | How to split one payload into multiple parts? | `split(...)`, `@Splitter` | Track correlation/sequence |
| **Aggregator** | When are enough results gathered? | `aggregate(...)`, `@Aggregator` | `MessageStore`, release/expiry, and late arrivals |
| **Publish-Subscribe** | Does one event have multiple consumers? | `PublishSubscribeChannel` | Not a durable broker topic |
| **Wire Tap** | Observe/copy messages to another branch? | `wireTap(...)` | Sensitive data risk, added load |
| **Channel Adapter** | Connect external transports? | HTTP, JDBC, Kafka, AMQP, file... | Define ack/commit/error at the transport layer |
| **Idempotent Receiver** | Will redelivery apply the work again? | `IdempotentReceiverInterceptor` and an appropriate store | Must choose a stable key and proper atomicity |

### How Does Filter Differ from Router?

A **Filter** makes a *keep or reject* decision on a message. A **Router** chooses one or more forwarding paths depending on content or headers. For example:

- Filter: only process `amount > 0`.
- Router: `currency == "VND"` goes to one branch, `currency == "USD"` goes to another.
- Transformer: normalize `orderId` and convert an external DTO to an internal DTO.

If a filter does not declare a discard channel or throw an exception, a rejected message may simply stop proceeding; Spring Integration may log a warning depending on the version. For important business events, you must specify where rejected messages go, whether they are stored for inspection, and whether a response is sent to the caller.

### Splitter and Aggregator

Suppose a batch contains 100 order lines:

~~~text
BatchReceived
     |
  Splitter
     |
Item-1 ... Item-100
     |
Validate / Enrich each item
     |
 Aggregator
     |
BatchValidated
~~~

A splitter typically adds correlation/sequence metadata when generating the message group. An aggregator needs to define:

- **Correlation strategy:** which messages belong to the same group.
- **Release strategy:** when the group is ready to emit the combined result.
- **Message store:** where group state is held; in-memory state is lost if the process dies.
- **Timeout and expiry:** what to do when an item never arrives.
- **Duplicate/late messages:** avoid double-counting or unintentionally reopening completed groups.

Especially in clustered or broker-backed processing, do not assume all items arrive completely, in order, or only once. Default aggregator settings must be evaluated against the real flow's contract.

### Request-Reply, One-Way, and Publish-Subscribe

| Flow style | Example | Expected outcome |
| --- | --- | --- |
| **Request-reply** | Query inventory status | Caller receives a response, or a timeout/error |
| **One-way** | Ingest an order event | Caller knows up to which boundary the message was accepted |
| **Publish-subscribe** | Notify multiple internal processors of catalog updates | Each subscriber receives a copy; no durable replay by default |

When a reply is needed, the gateway can declare a method with a return type:

~~~java
@MessagingGateway(defaultRequestChannel = "inventory.requests")
public interface InventoryQueryGateway {
    InventoryResult check(InventoryQuery query);
}
~~~

The end of the flow needs to return an `InventoryResult` so the gateway can forward the response back to the caller; a service activator with a return value or a Transformer step can do this. Gateway `requestTimeout` and `replyTimeout` thresholds are not the same as a downstream adapter's HTTP connection timeout. If the flow returns a result late, design timeout and late-reply handling according to the contract.

## 6. Choosing a MessageChannel: Synchronous, Executor, and Queue

The channel type determines more runtime characteristics than the name of the flow.

| Channel | Execution model | Advantages | Limitations to remember |
| --- | --- | --- | --- |
| `DirectChannel` | Handler typically runs on the sender's thread, point-to-point | Easy to trace; synchronous exceptions; can share transaction context | Slow handlers block the caller's thread |
| `ExecutorChannel` | Hands work off to a `TaskExecutor` | Decouples execution timing between sender and receiver | Thread boundary breaks transaction context and may reorder messages |
| `QueueChannel` | Stores messages in a queue; poller/consumer fetches later | Buffers and regulates processing pace | In-memory by default, risks message loss; must bound capacity |
| `PublishSubscribeChannel` | Delivers messages to multiple subscribers | Internal event broadcasting | Not equivalent to a broker with storage/replay |
| `PriorityChannel` | Prioritizes delivery by comparator/priority | Fits certain priority queues | Must evaluate starvation and durability |

In `DirectChannel`, if multiple subscribers are registered on the same point-to-point channel, a message is normally dispatched to one consumer by the dispatcher—**it is not broadcast**. If every consumer needs to receive the same event, choose an appropriate publish-subscribe model.

### Example of a Bounded Queue

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.PollableChannel;

@Configuration(proxyBeanMethods = false)
public class QueueConfiguration {

    @Bean("orders.buffered")
    PollableChannel ordersBuffered() {
        return new QueueChannel(500);
    }
}
~~~

Consumer in a Spring-managed component:

~~~java
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class BufferedOrderConsumer {

    @ServiceActivator(
            inputChannel = "orders.buffered",
            poller = @Poller(
                    fixedDelay = "1000",
                    maxMessagesPerPoll = "20"))
    public void consume(NormalizedOrder order) {
        // Process from queue; additional logic is needed to ensure durability.
    }
}
~~~

To connect the flow from Section 4 to the queue, you can replace the final processing step with `.channel("orders.buffered")` after the transformer and use the consumer above. In that setup, the gateway only confirms delivery to an in-memory queue. **Do not treat this as a guarantee of survival across crashes or delivery to a broker.**

A full queue can block the sender or cause the send operation to fail depending on timeout and policy, so monitor queue depth, consumption rate, saturation, and memory limits. If losing messages on restart is unacceptable, choose a durable broker or configure a persistent `MessageStore` for the appropriate channel (for example, JDBC-backed) and verify the associated transactions.

For pollers, default settings can be configured via Spring Boot's `spring.integration.poller.*` properties; however, a poller declared directly on an endpoint uses its own configuration. Do not confuse one poll cycle with one message: `maxMessagesPerPoll` limits the number of receives attempted per polling cycle.

## 7. Inbound/Outbound Channel Adapters and Protocols

Spring Integration includes adapters for many sources and destinations. Distinguish between an **inbound adapter**, **outbound adapter**, and **outbound gateway**:

- **Inbound adapter:** pulls or receives external data into the flow, such as polling a file directory or reading from a message source.
- **Outbound adapter:** sends messages out in a one-way model, such as publishing an event.
- **Outbound gateway:** calls an external system and waits for a response, such as HTTP request-reply.

| Protocol/source | Illustrative scenario | Contract considerations |
| --- | --- | --- |
| HTTP | Call a pricing API or receive a webhook | Timeouts, status codes, authentication, schema |
| JDBC | Poll work records or persist results | Transactions, locking/claiming, pagination |
| Kafka/AMQP/JMS | Consume or publish events | Consumer acknowledgement, offsets, redelivery, dead-letter |
| File/SFTP | Poll scheduled files and upload results | Partially written files, atomic rename, checksums, checkpoints |
| Mail/MQTT/TCP | Integrate protocol-specific systems | Reconnection, sessions, message framing |

For instance, a JDBC polling endpoint reading 10 rows does not mean those rows have already been marked "processed". You must define when claiming/committing occurs, how concurrent instances behave, retry conditions, and failures between reading and writing. Similarly, a successful outbound HTTP call does not automatically combine a local DB transaction and the HTTP request into a single ACID transaction.

**Adapter principle:** translate and communicate with infrastructure; keep business decisions, data contracts, and retry policies in the appropriate layers so they can be tested without connecting to live external systems.

## 8. Error Handling: Synchronous vs. Asynchronous Paths

The fundamental difference:

**Over a DirectChannel:** handlers execute synchronously, so errors typically propagate back to the gateway/caller. The controller or application service must decide whether to return an error, roll back the local transaction, or retry.

**Over an ExecutorChannel or poller:** the caller may already have moved on, and the error occurs on another thread. Spring Integration provides a mechanism to build an `ErrorMessage` (whose payload is a `Throwable`) and send it to the appropriate error channel. The `errorChannel` header is checked first; if absent, the infrastructure may use the global `errorChannel` according to the configured error handler mechanism.

~~~mermaid
flowchart TD
    A["Message from source"] --> B{"Execution boundary"}
    B -->|"DirectChannel / same thread"| C["Handler throws exception"]
    C --> D["Caller / Gateway handles it"]
    B -->|"Poller / Executor"| E["Handler throws exception"]
    E --> F["ErrorMessage"]
    F --> G["errorChannel"]
    G --> H["Alert / DLQ / recovery per policy"]
~~~

Example of registering a subscriber to observe the error channel:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.stereotype.Component;

@Component
public class IntegrationErrorObserver {

    @ServiceActivator(inputChannel = "errorChannel")
    public void record(ErrorMessage message) {
        Throwable cause = message.getPayload();
        // Log with sensitive fields masked, increment metrics, and raise alerts.
        // Recovery/retry should be designed in the appropriate layer.
    }
}
~~~

This is an **error observation pattern**, not a complete dead-letter or compensation implementation. Do not expect the error channel handler above to catch synchronous exceptions running on a `DirectChannel`. If the error-handling code itself throws an exception, you must also consider the propagation and logging behavior of the error path itself.

Classify errors to decide how to handle them:

| Error category | Example | Recommendation |
| --- | --- | --- |
| Invalid contract | Missing `orderId`, bad schema, unsupported currency | Reject with reason; store audit record if needed |
| Transient failure | Connection drop, broker unavailable, HTTP 503 | Bounded retry + backoff/jitter, protect downstream |
| Authorization/configuration error | Invalid token, forbidden endpoint | Alert and fix configuration; avoid continuous retries |
| Permanent business error | Order locked, invalid state transition | Return error / route to manual handling per contract |
| Unknown outcome error | Timeout after sending a write request | Query state and use an idempotency key before retrying |

A timeout error **does not prove** that the downstream system failed to apply the operation. Therefore, retrying a write must be paired with idempotency and reconciliation.

## 9. Transactions, Duplicate Handling, and Delivery Guarantees

### 9.1. Transaction Boundaries

When an entire flow runs on a `DirectChannel` in the same thread, a transaction started by the caller **can** cover database operations executed within the same context and resource manager, provided the methods are properly managed by transaction boundaries. Crossing to an `ExecutorChannel` or `QueueChannel` switches to a different execution context; you cannot assume the sender thread's transaction carries across.

Guarantees that must be explicitly stated:

- **At-most-once:** a message may be lost; no redelivery is attempted.
- **At-least-once:** a message may be redelivered; consumers must tolerate duplicates.
- **Exactly-once in business effect:** requires proper contract design, state, and atomic boundaries; it cannot be inferred from a single annotation or channel.

### 9.2. Idempotent Receiver

Suppose a broker redelivers the same event with `eventId = evt-1001` after the consumer updated the DB but before acknowledging. Re-running the full logic could decrement inventory or charge payment twice.

Spring Integration provides `IdempotentReceiverInterceptor` to detect duplicate messages using a selector and metadata store, but **the application itself** must choose a stable key and processing rule. With in-memory state, restarts or multiple instances can lose duplicate-detection history. Even with a centralized store, you must verify the atomicity of the check/mark step alongside business side effects.

One database-level defense is an **inbox table** with a unique constraint on `eventId`:

~~~java
// Illustrative code; inboxRepository must provide an atomic
// INSERT ... ON CONFLICT/IGNORE equivalent.
// Both DB operations participate in the same transaction.
@Transactional
public void apply(NormalizedOrder event) {
    boolean firstTime =
            inboxRepository.insertIfAbsent(event.eventId());

    if (!firstTime) {
        return; // Event already applied
    }

    orderRepository.applyBusinessChange(event);
}
~~~

In this example, `insertIfAbsent` must use a real unique constraint in a transaction consistent with `applyBusinessChange`. If the business operation fails, the transaction must roll back the inbox mark as well; otherwise, the event would be marked "done" even though the change never happened. Do not replace a unique constraint with a non-atomic `existsById()` followed by `save()` when multiple consumers can run concurrently.

### 9.3. Outbox for DB and Broker

When you need to "persist an order and then publish `OrderCreated`", a local database transaction does not automatically commit a broker publish. The **Transactional Outbox** pattern solves this by writing the business change and the outbox record **in the same DB transaction**, and having an independent publisher send outbox entries to the broker.

~~~mermaid
flowchart LR
    A["Order handler"] --> B["DB transaction"]
    B --> C["Order row"]
    B --> D["Outbox row"]
    D --> E["Publisher / CDC"]
    E --> F["Message broker"]
    F --> G["Consumer + inbox/idempotency"]
~~~

The publisher may send duplicates if it crashes right after the broker receives the message but before marking the outbox entry complete; consumers still need idempotency. Likewise, state transition rules and reconciliation must be defined when an external system does not support shared transactions.

## 10. Retries, Backpressure, and Load Control

A sound retry pattern for integrations requires four elements: **error classification**, **attempt limit**, **backoff/jitter delay**, and a **destination when retries are exhausted**.

Spring Integration can work with Spring Retry via endpoint advice, or leverage adapter/transport retry mechanisms. Avoid stacking retries across multiple layers without controlling total attempts: if the HTTP client retries 3 times, the handler retries 3 times, and the broker redelivers 3 times, the system can generate a huge number of calls for a single event.

Overload protection measures:

1. **Bounded queues:** finite capacity for `QueueChannel` or executor queues.
2. **Concurrency limits:** keep handlers/consumers within DB and downstream capacity.
3. **Timeouts:** separate limits for sending to a channel, waiting for a reply, and transport timeouts.
4. **Rate limiting/circuit breakers:** protect external services during cascading failures.
5. **Dead-letter/recovery:** messages that exhaust retries retain enough context for inspection and controlled replay.
6. **Backlog monitoring:** queue depth, oldest message age, ingress/egress rates, and error counts.

Do not treat `ExecutorChannel` as "unlimited async": bounded thread pools or queues trigger backpressure, task rejection, or sender blocking depending on executor configuration. Do not enable unbounded buffers just to mask a persistently overloaded downstream system.

## 11. Configuration Management and Data Safety

A flow should separate configuration by environment:

~~~yaml
# application.yml - example application properties
integrations:
  orders:
    destination: ${ORDER_DESTINATION:orders.received}
    max-attempts: 3
    enabled: true
~~~

These `integrations.orders.*` keys are **custom application properties**, not properties Spring Integration natively understands. They must be bound via `@ConfigurationProperties` or injected into the adapter/flow configuration.

Never hardcode credentials, API keys, passwords, or tokens in source code. Use a secret manager or environment variables following standardized mechanisms. For messages carrying customer or tenant data, verify:

- Do not forward all headers to external adapters unnecessarily.
- Tenant identity must derive from authenticated context, not an arbitrary HTTP header.
- Schemas and deserializers must enforce size limits, allowed types, and versions.
- Logs, traces, metrics, and error messages should avoid leaking tokens or PII.
- Manage access permissions for broker topics, queues, databases, and management endpoints.

When working with multiple adapters, separate **properties per downstream** and validate configuration at startup (required URLs/topics, positive timeouts, bounded retries). Avoid scattering official channel or destination names across untraceable string literals.

## 12. Behavior-Driven Flow Testing

Testing should cover from input contract to output effect, not merely checking that an `IntegrationFlow` bean exists.

| Scenario | What to verify |
| --- | --- |
| Valid message | Gateway flows through filter/transform and invokes the expected handler |
| Rejected message | Throws an error or routes to the discard channel as designed |
| Malformed DTO/schema | Produces no unintended side effects |
| Duplicate `eventId` | Business state changes only once per contract |
| Downstream unavailable | Bounded timeout/retry, final failure recorded |
| Queue full | Triggers backpressure or timeout without unbounded RAM growth |
| Crash/restart | Accepted messages recover according to design guarantees |
| Split/aggregate missing items | Release/expiry handles incomplete groups |
| Transaction rollback | Does not mark the event processed when business changes fail to commit |
| Multi-tenant | No cross-tenant leakage of data, headers, or routes |

An integration test example for a synchronous path:

~~~java
// Illustrates assertions inside @SpringBootTest;
// OrderHandler in the test fixture is replaced by a fake/spy capturing results.
@Test
void acceptsAndNormalizesValidOrder() {
    gateway.submit(new OrderReceived(
            "evt-1",
            "  ORD-1  ",
            new BigDecimal("15.50")));

    assertEquals("ORD-1", fakeHandler.lastOrder().orderId());
}
~~~

This test must run against a **Spring context with the gateway and flow registered**, with the fake handler wired before invoking the gateway; instantiating `new OrderNormalizer()`/`new OrderHandler()` directly does not verify integration wiring. Additionally, separately test how errors return to the gateway on a `DirectChannel` versus entering error handling on pollers/executors.

Spring Integration provides the `spring-integration-test` module, the `@SpringIntegrationTest` annotation, and support for substituting handlers/sources with mocks in certain contexts. Use them to isolate I/O when needed; for real Kafka, Redis, JDBC, or HTTP, use real brokers, databases, Testcontainers, or faithful stubs to verify delivery contracts rather than mocking everything.

## 13. Observability and Operating Integration Flows

A flow running on a developer laptop is not enough for production. You need logs, metrics, and traces capable of answering:

- Which step is an event at; has it been processed or is it waiting?
- Which step has high latency, rising error rates, or a backlog?
- How many retries/duplicates are occurring; is the DLQ growing?
- Which schema version did a failing message have; which endpoints did it traverse?
- Was any data lost or delayed after a rollout/restart?

Spring Integration offers endpoint management/observation, message history, metrics, and Micrometer/Actuator integration depending on dependencies, versions, and configuration. When enabling observation or message history, weigh the overhead and cardinality; avoid placing raw payloads, `orderId`, `eventId`, or `tenantId` in metric tags. Propagate `correlationId`/trace context across transport boundaries using controlled conventions.

Practical metrics:

| Metric | Decision it supports |
| --- | --- |
| Messages received/handled/failed | Is any step continuously rejecting or failing? |
| Endpoint processing duration p95/p99 | Which step is inflating end-to-end latency? |
| Queue depth and oldest-message age | Are consumers keeping up with producers? |
| Retry count, DLQ count | Are failures transient or persistent contract issues? |
| Duplicate rate by event type | High redeliveries or upstream producing duplicates? |
| Downstream error/timeout rate | Need a circuit breaker or extra capacity? |
| Outbox backlog and publish lag | Is DB→broker publishing slowing down or stuck? |

Ensure metrics, alerts, and logs match the **actual boundary where processing responsibility is accepted**. An HTTP gateway returning success after writing to an in-memory queue cannot be measured as an event durably persisted in a broker.

## 14. When Should You Use Spring Integration?

**Suitable** when a Spring application needs to connect multiple transports, orchestrate transformation/routing chains, poll data sources, perform request-reply over messages, or decouple adapters from business logic using built-in EIP building blocks.

**Unnecessary** if an API only needs a few direct calls where `RestClient`/`WebClient`, repositories, or broker clients are simpler and clearer. Spring Integration also does not replace:

- **Brokers:** used for durable cross-process delivery, topic/queue distribution, or replay according to broker capabilities.
- **Spring Batch:** used for finite step-based batch jobs, checkpoint/restart, and chunk processing.
- **Workflow/saga orchestration:** used for long-running, stateful multi-step processes with compensation and business timeouts.
- **Transactions and business idempotency:** require storage design, unique constraints, outbox/inbox tables, and external side-effect contracts.

A real application can combine Spring Integration with all of those tools. What matters is that each tool keeps its proper responsibility.

## 15. Integration Flow Design Checklist

- [ ] Diagrammed source → channel → endpoint → sink, explicitly marking synchronous and asynchronous boundaries.
- [ ] Defined message contract including schema/version, business keys, correlation, and header rules.
- [ ] Selected channels according to latency, durability, throughput, and transaction requirements.
- [ ] Filter/Router explicitly defines paths for rejected or unroutable messages.
- [ ] I/O adapters configure timeouts, retries, and appropriate fallbacks/error destinations.
- [ ] Side effects are protected by idempotency keys, local transactions, and outbox/inbox where required.
- [ ] Queues/pollers/executors enforce load bounds and backlog observability.
- [ ] Tested happy paths, invalid data, duplicates, timeouts, crash/restart, and commit boundaries.
- [ ] Configured metrics, trace/logs with sensitive data masked, and a controlled error replay procedure.

**Remember:** Spring Integration turns integration pipelines into components with clear boundaries: messages express data, channels express handoff semantics, endpoints express operations, and adapters talk to external systems. Real reliability comes from **data contracts, transactions, idempotency, retries, recovery, and observability** designed across the entire flow.

## References

- [Spring Boot — Spring Integration](https://docs.spring.io/spring-boot/reference/messaging/spring-integration.html): starter, auto-configuration, scheduler, and pollers.
- [Spring Integration — Overview](https://docs.spring.io/spring-integration/reference/overview.html): messaging model, channels, and endpoints.
- [Spring Integration — Java DSL Basics](https://docs.spring.io/spring-integration/reference/dsl/java-basics.html): `IntegrationFlow` and EIP operators.
- [Spring Integration — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): `@MessagingGateway` and proxy registration.
- [Spring Integration — Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html): `DirectChannel`, `ExecutorChannel`, `QueueChannel`, and durable configuration.
- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): `ErrorMessage`, `errorChannel`, and asynchronous errors.
- [Spring Integration — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): advice and metadata store for duplicate detection.
