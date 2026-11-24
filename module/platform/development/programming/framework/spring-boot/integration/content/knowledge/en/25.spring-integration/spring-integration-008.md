# IntegrationFlow and Declaring Flows with the Java DSL

## 1. What Problem Does IntegrationFlow Solve?

In a **Spring Boot Integration** module, an application often receives HTTP requests, validates data, accesses a database, calls external services, pushes messages to a broker, or sends emails. Writing all of those steps inside one large service quickly turns messy: business logic gets tangled with data conversion, routing, retries, concurrency, and external communication details.

**Spring Integration** implements **Enterprise Integration Patterns (EIP)**. Instead of tightly coupling components together, you connect them using **messages**, **channels**, and **endpoints**. With the **Java DSL**, the `IntegrationFlow` interface lets you declare endpoint chains directly in type-checked Java configuration with full IDE support and Spring-managed lifecycle.

Consider an order-intake requirement:

1. A controller or ingress component submits an `OrderCommand`.
2. The flow validates quantity and normalizes product codes.
3. The flow invokes a business service to reserve inventory.
4. An `OrderResult` is returned to the caller.
5. A confirmed event may be forwarded to an email or asynchronous read-model flow.

~~~mermaid
flowchart LR
    A["HTTP controller / Gateway"] --> B["orders.submit"]
    B --> C["Filter"]
    C --> D["Transformer"]
    D --> E["Service Activator"]
    E --> F["OrderResult"]
    F --> A
    E -. "Post-commit event" .-> G["Broker / notification flow"]
~~~

The steps in this diagram do not automatically create threads, queues, or transactions. **Channel and endpoint configuration controls execution behavior**; writing an `IntegrationFlow` alone does not make a flow asynchronous or durable.

## 2. Components and Responsibilities

| Component | Role | Example |
| --- | --- | --- |
| `Message<T>` | Wraps a `payload` with `headers` for transfer between endpoints. | `OrderCommand` payload, `correlationId` header. |
| `MessageChannel` | Connection boundary between producers and consumers. | `orders.submit` or `notifications.in`. |
| `MessageHandler` / `Service Activator` | Executes business actions, optionally returning a reply. | Calling `OrderService.reserve(...)`. |
| `Transformer` | Converts payload representations. | Trimming SKUs, mapping DTOs to internal commands. |
| `Filter` | Accepts or rejects messages based on a predicate. | Rejecting commands with invalid quantities. |
| `Router` | Selects target channels based on content or headers. | `CREATED` event to email, `CANCELLED` to cancellation notice. |
| `Splitter` and `Aggregator` | Splits collections then recombines results using correlation/release strategies. | Splitting order lines and aggregating line results. |
| `Gateway` | Bridges Java/HTTP calls into the messaging system; supports request/reply. | `OrderGateway.submit(...)`. |
| `IntegrationFlow` | Declares a Spring-registered chain of endpoints and channels. | `orderSubmissionFlow`. |
| Channel adapter / gateway adapter | Connects flows to Kafka, RabbitMQ, JDBC, HTTP, files, mail, etc. | Inbound message adapters and outbound gateways. |

A message can carry `id`, `timestamp`, `replyChannel`, `errorChannel`, and business headers. **A `Message` is an envelope**, which does not guarantee the inner payload object is immutable; across multiple threads, avoid mutating shared objects or relying on execution order.

EIP building blocks can be composed freely, provided each step has a clear **data contract**: expected input payload, whether payloads/headers change, whether it replies or performs side effects, and where failures are handled.

## 3. Preparing a Spring Boot Application

Examples use **Java 17+, Spring Boot 3.x, and Spring Integration 6.x**. With Maven, the minimal dependency is:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
~~~

The starter provides core Spring Integration and integrates with Spring Boot configuration. Adapters for HTTP, JDBC, AMQP, Kafka, mail, and others have **separate dependencies and configuration**; add them only when a flow talks to those systems. For JUnit testing, add `spring-boot-starter-test` and Spring Integration's test module when using specialized integration test helpers.

Sample source layout:

~~~text
src/main/java/com/example/integration/
├── IntegrationApplication.java
├── order/
│   ├── OrderCommand.java
│   ├── ValidatedOrder.java
│   ├── OrderResult.java
│   ├── OrderGateway.java
│   ├── OrderHandler.java
│   └── OrderFlowConfiguration.java
└── notification/
    ├── OrderEvent.java
    └── NotificationFlowConfiguration.java
~~~

When exposing gateways via interfaces annotated with `@MessagingGateway`, enable scanning for those interfaces:

~~~java
package com.example.integration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.integration.annotation.IntegrationComponentScan;

@SpringBootApplication
@IntegrationComponentScan
public class IntegrationApplication {
    public static void main(String[] args) {
        SpringApplication.run(IntegrationApplication.class, args);
    }
}
~~~

`@IntegrationComponentScan` locates gateway interfaces within scanned packages and creates proxies so regular Java code can invoke the flow. Without gateway interfaces, applications can also send messages via `MessagingTemplate` or enter through inbound adapters. In Spring Boot, `IntegrationFlow` beans are automatically detected and registered by Spring Integration infrastructure.

## 4. Complete Example: Receiving Commands via Gateway, Processing with Java DSL

### 4.1. Defining the Data Contracts

Each type below belongs in its own Java file; `record` works well for immutable boundary DTOs/commands:

~~~java
package com.example.integration.order;

public record OrderCommand(String orderId, String sku, int quantity) {}
~~~

~~~java
package com.example.integration.order;

public record ValidatedOrder(String orderId, String sku, int quantity) {}
~~~

~~~java
package com.example.integration.order;

public record OrderResult(String orderId, String status) {}
~~~

A gateway declares its target input channel:

~~~java
package com.example.integration.order;

import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway
public interface OrderGateway {
    @Gateway(requestChannel = "orders.submit")
    OrderResult submit(OrderCommand command);
}
~~~

Each call to `submit` causes the proxy to build a message, send the payload to `orders.submit`, and wait for a reply mapped to `OrderResult`. On a synchronous channel like `DirectChannel`, the call normally runs on the caller's thread. When switching channels or endpoints to asynchronous execution, configure and enforce response timeouts aligned with caller expectations.

### 4.2. Extracting Business Logic into a Handler

~~~java
package com.example.integration.order;

import org.springframework.stereotype.Service;

@Service
public class OrderHandler {
    public OrderResult reserve(ValidatedOrder order) {
        // Illustrative example: a real app calls domain services,
        // persists state, or coordinates an external adapter.
        return new OrderResult(order.orderId(), "ACCEPTED");
    }
}
~~~

`ACCEPTED` here is merely a simulated return value, not proof that a database committed or a payment gateway confirmed. In production systems, status names should reflect true commitment (`RECEIVED`, `PENDING`, `RESERVED`, etc.).

### 4.3. Declaring the IntegrationFlow

~~~java
package com.example.integration.order;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration(proxyBeanMethods = false)
public class OrderFlowConfiguration {

    @Bean
    IntegrationFlow orderSubmissionFlow(OrderHandler handler) {
        return IntegrationFlow.from("orders.submit")
                .filter(
                        OrderCommand.class,
                        command -> command.quantity() > 0,
                        spec -> spec.throwExceptionOnRejection(true))
                .transform(
                        OrderCommand.class,
                        command -> new ValidatedOrder(
                                command.orderId(),
                                command.sku().trim(),
                                command.quantity()))
                .handle(
                        ValidatedOrder.class,
                        (payload, headers) -> handler.reserve(payload))
                .get();
    }
}
~~~

Step-by-step explanation:

1. `IntegrationFlow.from("orders.submit")` defines an **entry point** bound to the channel named `orders.submit`. If no channel with that name exists yet, the DSL infrastructure creates an appropriate channel; verify the actual channel type rather than guessing.
2. `filter(OrderCommand.class, ...)` validates quantity. `throwExceptionOnRejection(true)` turns rejection into an exception so the caller clearly knows input was rejected. Without it, the filter silently stops rejected messages with no reply—causing request/reply gateways to hang until timeout.
3. `transform(OrderCommand.class, ...)` replaces the payload with a `ValidatedOrder` containing a trimmed SKU. In this snippet `sku` must be non-null; real apps should validate inputs before calling `trim()` to return clean validation errors rather than `NullPointerException`.
4. `handle(ValidatedOrder.class, (payload, headers) -> ...)` acts as a **Service Activator**, calling the business handler with the transformed payload.
5. `get()` finalizes the DSL definition and returns an `IntegrationFlow`. When Spring registers the flow, intermediate endpoints and required channels are registered as infrastructure beans.
6. The `OrderResult` returned by the handler becomes the reply. Request/reply gateways use the message's `replyChannel` header to route the result back to the caller without manual response-channel wiring here.

The flow looks linear yet can expand into branching topologies or external adapters. Never stuff SQL queries, transactions, HTTP loops, or large business rules directly into DSL lambdas: keep lambdas thin so flows remain easy to test and observe.

### 4.4. Calling the Flow from an External API

A controller injects `OrderGateway` like any normal service:

~~~java
package com.example.integration.order;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {
    private final OrderGateway gateway;

    public OrderController(OrderGateway gateway) {
        this.gateway = gateway;
    }

    @PostMapping
    public ResponseEntity<OrderResult> submit(@RequestBody OrderCommand command) {
        return ResponseEntity.ok(gateway.submit(command));
    }
}
~~~

Real HTTP endpoints need Bean Validation/input checks, mapping exceptions to `400` or domain error codes, user authentication, and timeouts. This snippet only demonstrates the boundary between an HTTP controller and a flow; `ResponseEntity.ok(...)` is not a universal contract for every order operation.

## 5. Common Java DSL Operators

The DSL composes EIP operators via fluent method chaining on `IntegrationFlowDefinition`:

| DSL | Meaning | Things to keep in mind |
| --- | --- | --- |
| `from(...)` | Specifies an input channel, adapter, or message source. | Pollable sources may require configuring a poller. |
| `channel(...)` | Names an intermediate channel or changes dispatch/concurrency. | Channel type governs threading and transactions. |
| `filter(...)` | Drops messages failing a predicate. | Choose rejection handling: drop, throw, or discard channel. |
| `transform(...)` | Converts payload (and optionally headers when returning a `Message`). | Keep contracts explicit; watch nulls and serialization. |
| `route(...)` | Selects one or more branches based on values or conditions. | Always handle unknown/unmapped values. |
| `split(...)` | Splits a collection/stream into child messages. | Manage correlation and sequence if aggregating later. |
| `aggregate(...)` | Combines related messages into one result. | Needs release strategy, timeout, and persistent message store when stateful. |
| `enrichHeaders(...)` | Adds metadata to headers. | Avoid putting PII, tokens, or oversized values in headers. |
| `publishSubscribeChannel(...)` | Broadcasts one message to multiple subscribers. | Does not provide durable storage or delivery to offline subscribers. |
| `handle(...)` | Invokes a service, message handler, or outbound adapter. | Distinguish reply-producing handlers from one-way side effects. |
| `bridge()` | Connects channels when splitting a pipeline into segments. | Leaves payload unchanged; useful for wiring topologies. |
| `get()` | Finalizes the `IntegrationFlow` definition. | Spring creates endpoints when the bean is registered. |

For longer pipelines, give channels domain-meaningful names: `orders.submit`, `orders.validated`, `orders.confirmed`. When breaking a flow into segments, connect them via named channels. Clear channel names also improve logging, tracing, and testing.

## 6. Router: Branching by Event Type

A system may receive multiple order event types and route each to a different workflow. Example:

~~~java
package com.example.integration.notification;

public record OrderEvent(String eventId, String type, String orderId) {}
~~~

~~~java
package com.example.integration.notification;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration(proxyBeanMethods = false)
public class NotificationFlowConfiguration {

    @Bean
    IntegrationFlow routeOrderEvents() {
        return IntegrationFlow.from("order.events.in")
                .route(
                        OrderEvent.class,
                        OrderEvent::type,
                        mapping -> mapping
                                .channelMapping("CREATED", "order.events.created")
                                .channelMapping("CANCELLED", "order.events.cancelled"))
                .get();
    }

    @Bean
    IntegrationFlow createdEventFlow(NotificationHandler handler) {
        return IntegrationFlow.from("order.events.created")
                .handle(handler, "notifyCreated")
                .get();
    }

    @Bean
    IntegrationFlow cancelledEventFlow(NotificationHandler handler) {
        return IntegrationFlow.from("order.events.cancelled")
                .handle(handler, "notifyCancelled")
                .get();
    }
}
~~~

Here `NotificationHandler` is an application bean exposing `notifyCreated(OrderEvent)` and `notifyCancelled(OrderEvent)`. Those handlers can perform side effects without returning replies. `CREATED` events route to the created channel, while `CANCELLED` events follow the other branch.

**Mandatory decision when using a router:** what happens when an event arrives with an unsupported `type`? Explicitly define a default route, error channel, or rejection per contract. Never let unknown event types silently vanish in critical business flows. When the same event must go to **multiple** independent consumers, use `publishSubscribeChannel` or broker pub/sub rather than expecting a router to broadcast.

## 7. Channels Determine Synchronicity, Asynchronicity, and Durability

Identical DSL syntax behaves very differently at runtime depending on how channels are configured.

| Channel | Execution characteristics | Best for | Notes |
| --- | --- | --- | --- |
| `DirectChannel` | Dispatcher calls handler on sender's thread synchronously. | Short request/reply pipelines that should join the current transaction when applicable. | Slow handlers directly stall the caller; errors propagate back. |
| `ExecutorChannel` | Hands handler execution to an executor on another thread. | Processing steps that need not block the caller upon send. | Not durable; does not carry thread-local transactions; must bound queue size. |
| `QueueChannel` | Buffers messages in a queue for consumers to poll. | Decoupling producer and consumer rates. | In-memory by default; surviving restarts requires a persistent message store. |
| `PublishSubscribeChannel` | Delivers to multiple subscribers, synchronous by default without an executor. | In-process fan-out. | Offline subscribers miss messages; one failing handler can affect dispatch. |
| Broker channel adapter | Sends/receives via an external broker. | Cross-service communication needing durability/acks/retries. | Guarantees depend on broker, transactions, acks, and idempotency. |

Configuring a Spring-managed executor:

~~~java
import java.util.concurrent.Executor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class AuditFlowConfiguration {

    @Bean
    ThreadPoolTaskExecutor auditExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("audit-flow-");
        return executor;
    }

    @Bean
    IntegrationFlow auditFlow(
            ThreadPoolTaskExecutor auditExecutor,
            AuditHandler handler) {
        return IntegrationFlow.from("audit.in")
                .channel(spec -> spec.executor(auditExecutor))
                .handle(handler, "store")
                .get();
    }
}
~~~

`AuditHandler` is an application service with a `store(AuditEvent)` method. With `ExecutorChannel`, steps after the channel run on an executor worker thread once dispatched. `send(...)` completing does not mean the database write or notification succeeded. If pool and queue saturate, define a rejection/backpressure policy and monitor `active threads` and `queue depth`. The numbers 2/4/100 are purely illustrative; size them from measured latency and load.

**Transaction boundary:** a transaction from the request thread does not carry over to an `ExecutorChannel` thread. If an async handler writes via JPA, open a transaction on the service/listener behind the channel. Never treat submitting a critical update to an in-process executor as durable persistence.

## 8. Input/Output Adapters and Gateways

An `IntegrationFlow` can start or end at many integration technologies:

- **HTTP**: inbound gateways accept requests, outbound gateways call external APIs and receive responses. Enforce timeouts, status code mappings, and authentication.
- **JDBC/JPA**: polling adapters or message-driven components work with databases; transactions belong to the managed resource and poller/handler scope.
- **AMQP/Kafka**: inbound adapters consume from brokers, outbound adapters publish events/commands. Understand acks, retries, partitions/ordering, and schemas for your chosen broker.
- **File/SFTP**: fetch files, parse, split records, save outputs. Design markers/checkpoints and idempotency to avoid reprocessing files.
- **Mail**: outbound mail adapters send notifications; handle SMTP errors separately from business success.

Key distinction between adapters and gateways:

| Component | Expected behavior |
| --- | --- |
| **Inbound channel adapter** | Creates messages entering the flow, typically one-way; source can be polling or event-driven. |
| **Outbound channel adapter** | Receives messages and sends them out, typically one-way with no business reply. |
| **Inbound gateway** | Turns external requests into messages and waits for a flow reply to send back. |
| **Outbound gateway** | Sends requests to external systems and feeds responses back into the flow. |

For instance, if a flow must call Inventory over HTTP to check reservation status before continuing, an **outbound gateway** fits better than a one-way **outbound channel adapter**. If simply notifying a broker of `OrderConfirmed` after commit with no immediate reply needed, an outbound adapter suffices.

Adapters do not change cross-system transaction semantics. Calling an HTTP endpoint inside a JPA transaction does not enlist the remote service in that transaction. When a DB commit succeeds yet broker publishing fails or the process crashes, use a **transactional outbox** rather than assuming two operations are atomic.

## 9. Headers, Correlation, and Splitting/Aggregating Messages

In pipelines, headers carry metadata separately from the payload. Examples:

| Header | Usage | Pitfalls to avoid |
| --- | --- | --- |
| `replyChannel` | Return address for request/reply gateways. | Not a durable place to store results. |
| `errorChannel` | Channel receiving certain processing failures via error flows. | Not every exception routes here on every channel type. |
| `correlationId` | Groups messages belonging to one split/aggregate operation. | Does not replace trace IDs, operation IDs, or idempotency keys. |
| `sequenceNumber`, `sequenceSize` | Item position and group size during split/aggregate. | Insufficient alone if messages can be lost or arrive late. |
| `eventId`, `schemaVersion` (app headers) | Deduplication, contract compatibility, message versioning. | Distinct from framework-generated `MessageHeaders.ID`. |

A flow splitting order lines and aggregating results:

~~~mermaid
flowchart LR
    A["Order: 3 lines"] --> S["Splitter"]
    S --> L1["Line 1"]
    S --> L2["Line 2"]
    S --> L3["Line 3"]
    L1 --> V["Validate/Enrich"]
    L2 --> V
    L3 --> V
    V --> G["Aggregator"]
    G --> R["Aggregated result"]
~~~

`Splitter` can attach correlation and sequence headers so `Aggregator` recognizes group members. However, with concurrent threads, uneven arrivals, mid-stream errors, or unknown counts, an aggregator needs a **release strategy**, **group timeout**, **message store**, and an incomplete-group policy. Relying on defaults does not ensure groups release cleanly in every failure mode.

When messages cross brokers, verify which headers map onto wire protocols and survive serialization. Avoid non-serializable Java objects in headers; use stable IDs, clear timestamp formats, explicit schema versions, and message size limits.

## 10. Error Handling, Retries, and Asynchronous Flows

Spring Integration provides error-handling infrastructure, advice, and error channels, yet **exception paths depend on endpoints and channels**:

1. **Synchronous `DirectChannel` flow:** exceptions in filters or handlers typically propagate back to the sender; HTTP controllers or gateways can convert them into error responses.
2. **Asynchronous executor/poller flow:** exceptions occur on another thread; depending on configuration, infrastructure may publish an `ErrorMessage` to an error channel. The original sender does not directly catch downstream exceptions.
3. **Inbound broker adapter:** retries, acks, redelivery, and DLQs must align with the adapter and broker; throwing an exception does not automatically route to a DLQ.
4. **Outbound HTTP/SMTP:** distinguish transient errors from permanent errors; cap retries/backoff and avoid duplicating side effects when outcomes are unknown.

### 10.1. Designing Retries by Error Nature

| Error type | Appropriate policy |
| --- | --- |
| Missing required fields, bad schema version | Reject with clear reason, send to error/investigation channel; blind retries rarely help. |
| HTTP 429, network timeout, broker unavailable | Bounded retries with backoff/jitter, timeouts, and circuit breakers. |
| Unique constraint from duplicate message | Deduplicate by `eventId`/idempotency key; acknowledge as already processed when valid duplicate. |
| Handler bug or incompatible schema | DLQ/quarantine, fix the bug, then replay under control. |
| Error after external commit but before reply | Query status/idempotency; blind retries risk duplicate side effects. |

When adding `RequestHandlerRetryAdvice` or adapter retries, verify **where retries sit**: which handler they wrap, which exceptions trigger retries, max attempts, and where exhausted failures go. Retrying a handler with side effects requires a stable operation ID to remain safe on redelivery.

### 10.2. Error Channels and Error Messages

An `ErrorMessage` carries a payload representing the failure (commonly a `MessagingException`) and can retain the failed/original message for diagnosis. Build dedicated error-handling flows or per-endpoint error channels. Never mistake the global `errorChannel` for a durable "dead-letter queue": an internal channel and a broker DLQ are completely different things.

Error handlers should record **error type, endpoint, message ID, correlation ID, and timestamp**. Log only essential metadata—never tokens, credentials, or sensitive payloads. If replay is needed, persist failed payloads under a durable contract with bounded attempt tracking rather than relying on logs.

## 11. Transactions and Duplicate Handling in IntegrationFlow

A flow can invoke JPA repositories inside a service's `@Transactional`, yet that **does not extend the transaction** across HTTP, Redis, or external brokers. Example:

~~~mermaid
sequenceDiagram
    participant Producer as Order Service
    participant DB as Orders DB
    participant Broker as Message Broker
    participant Consumer as Email Consumer
    Producer->>DB: Transaction updates Order + writes Outbox
    DB-->>Producer: Commit
    Producer->>Broker: Outbox relay publishes event
    Broker-->>Producer: Ack
    Broker->>Consumer: OrderConfirmed
    Consumer->>Consumer: Check eventId, send email
~~~

When an event must be emitted after an Order commits, a common choice is the **transactional outbox**:

1. Persist business changes and an outbox row in the **same database transaction**.
2. Have a relay read outbox entries and publish via broker adapter, marking completion only upon proper acknowledgement.
3. Have consumers process idempotently; if the relay crashes after publishing before marking done, the event may be resent.
4. Monitor outbox age, retry counts, backlogs, DLQs, and run reconciliation when needed.

This preserves clean boundaries: Spring Integration connects channels and endpoints; transaction managers/JPA protect local DB transactions; brokers deliver per configuration; **idempotency and reconciliation** protect business state against duplicates and uncertain states.

With `ExecutorChannel` or polling adapters, place transaction boundaries on the consuming thread. When controlling Kafka or RabbitMQ offsets/acks, coordinate with container/adapter policies so messages are never acked before business state commits durably.

## 12. Testing Java DSL and Integration Flows

Separate testing into three levels:

| Level | What it verifies | Approach |
| --- | --- | --- |
| **Unit** | Lambdas/filters/transformers and domain rules return expected outputs. | Test functions/domain services directly. |
| **ApplicationContext integration** | `IntegrationFlow` beans register; gateways/channels/routing/replies/errors work. | `@SpringBootTest`, invoke gateway, assert outputs and routed branches. |
| **End-to-end with external systems** | DB/broker/HTTP adapters, transactions, acks, retries, replay, and schemas. | Testcontainers, mock HTTP servers, or dedicated sandboxes. |

For `orderSubmissionFlow` above, a basic request/reply test:

~~~java
package com.example.integration.order;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class OrderFlowIntegrationTest {
    @Autowired
    OrderGateway gateway;

    @Test
    void submitValidOrderReturnsReply() {
        OrderResult result = gateway.submit(
                new OrderCommand("order-101", " SKU-01 ", 2));
        assertEquals("order-101", result.orderId());
        assertEquals("ACCEPTED", result.status());
    }

    @Test
    void invalidQuantityIsRejected() {
        assertThrows(
                RuntimeException.class,
                () -> gateway.submit(new OrderCommand("order-102", "SKU-02", 0)));
    }
}
~~~

In real projects, assert **specific exception types and error semantics** once error mapping is standardized, rather than broad `RuntimeException` assertions. Additional cases to cover:

- **Filter:** invalid input never invokes the handler; replies/exceptions match the gateway contract.
- **Transformer:** SKUs normalize properly; null/blank values, encodings, and required fields produce clean errors.
- **Router:** `CREATED`/`CANCELLED` hit the right branches; unknown events follow the defined policy.
- **Thread boundary:** executor-backed flows do not depend on request transactions/thread-locals; timeouts and queue saturation behave predictably.
- **Retries:** transient failures retry up to the limit; permanent failures go to discard/DLQ without duplicating side effects.
- **Transactional outbox:** crashes before/after commit and before/after publish never lose committed events; consumers stay idempotent.
- **Contracts:** events carry schema versions and correlation/event IDs; older consumers survive backward-compatible evolutions.

When testing async channels, wait on observable state with deadlines (such as Awaitility) rather than fixed `Thread.sleep(...)` calls. Tests using only mock handlers do not prove real broker acks or DB transactions; test adapters and databases with real integration tests.

## 13. Observability, Performance, and Deployment

To operate multi-endpoint flows, collect:

- **Per-endpoint and end-to-end latency:** time from ingress to response; track p95/p99 against deadlines.
- **Throughput and errors:** counts of messages sent/received/handled, failure rates, retries, rejections, drops, and timeouts.
- **Backpressure:** queue lengths, active threads, pending requests, consumer lag, and oldest message age.
- **Reliability:** DLQ depth, duplicate rates, unpublished outbox rows, and items awaiting reconciliation.
- **Traceability:** correlation ID, trace ID, event ID, origin, and destination channel; never overload one ID for everything.

Spring Integration supports message tracking and observation/metrics when configured with Micrometer and Actuator. Consult your Spring Integration and Boot versions when selecting observations, message history, channel interceptors, or tracing—and avoid logging full payloads in production.

Recurring design pitfalls:

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Assuming every `IntegrationFlow` is async | Gateways block or time out unexpectedly. | Choose channels/threading explicitly and set latency budgets. |
| Using `ExecutorChannel` as a durable queue | Tasks vanish on app crash. | Use a broker or persistent message store when durability is required. |
| Filtering out a gateway message with no reply | Caller stalls until timeout. | Throw a controlled error or return an explicit rejection reply. |
| Router missing unknown-value handling | New event types are mishandled or lost. | Define default route, error handling, and contract tests. |
| Retrying side effects without idempotency | Duplicate emails, charges, or DB inserts. | Stabilize operation keys, inbox/outbox, and reconciliation. |
| Packing complex business mapping into DSL lambdas | Hard to test, debug, and version. | Extract handlers/services/DTOs; keep DSL focused on topology. |
| Placing async mid-transaction expecting full rollback | DB commits diverge or handlers run without transactions. | Manage transactions at consumers and design eventual consistency. |

## 14. Structuring Flows in Real Projects

When designing a new `IntegrationFlow`, follow this sequence:

1. **Define the message contract:** payloads, versions, required headers, sensitive fields, and channel names.
2. **Map EIP steps:** ingress, filter/validate, transform, route, handle, and egress; separate business logic from adapters.
3. **Choose sync vs. async per boundary:** does the caller need an immediate result, is `PENDING` acceptable, and must messages persist durably?
4. **Define transactions and idempotency:** data ownership, commit points, retries, deduplication, and timeout recovery after partner commits.
5. **Design error paths:** validation rejections, transient retries, retry exhaustion, DLQs, alerts, and replay.
6. **Test and observe:** run context and real-adapter integration tests, and monitor per-channel/endpoint metrics to spot backlogs early.

**`IntegrationFlow` and the Java DSL** express Spring Boot integration pipelines as modular, reusable, observable components. A flow's correctness still rests on data contracts, transaction boundaries, delivery guarantees, duplicate handling, and failure recovery. Select channels, gateways, routers, and adapters from those requirements so the DSL faithfully reflects real production behavior.
