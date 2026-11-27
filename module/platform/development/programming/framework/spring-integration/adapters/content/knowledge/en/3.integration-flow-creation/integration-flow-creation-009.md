# Routing Flows Across Multiple Endpoints

## 1. Problem and Learning Objectives

In Spring Integration, not every message follows the exact same processing path. Express delivery orders must go to a priority handling service; standard orders go to a different handler; malformed records must route to a review branch. An inbound adapter may ingest data from files, SFTP, HTTP, JMS, AMQP, Kafka, or databases into **one shared channel**, while the next step must select an endpoint based on the message content.

**Routing flows across multiple endpoints** uses a *message router* to choose the destination channel. Each channel can lead to a service activator, transformer, outbound adapter/gateway, or standalone `IntegrationFlow`. The router's job is to **decide the route**, while downstream endpoints perform business processing.

This lesson belongs to the **Integration Flow Creation** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module covers connecting external systems using inbound/outbound adapters, gateways, pollers, and `MessageChannel`, along with practicing message contracts, error handling, and connection lifecycles. A router is a crucial junction whenever multiple systems, protocols, or business workflows coexist in one application.

After this lesson, learners will be able to:

- Explain a *Content-Based Router* and distinguish it from filters, transformers, bridges, splitters, and publish–subscribe channels.
- Declare a router using `IntegrationFlow.route(...)`, mapping routing keys to channel names.
- Write multiple `IntegrationFlow` branches or `@ServiceActivator` endpoints consuming from different channels.
- Configure routers based on payload or headers and handle unsupported keys cleanly.
- Choose among **single branch**, **multiple branches**, **default branch**, and **error branch**.
- Understand reply paths when a router sits inside a request–reply flow and the impact of Direct/Queue/Executor channels.
- Test every routing path, unmatched keys, invalid payloads, and key metadata.

**Scope:** a router operates on `Message<?>` within Spring Integration. It does not read from SFTP, write to databases, publish to Kafka, or execute retries itself; those responsibilities belong to adapters, gateways, handlers, and source/target configuration.

## 2. Where Does a Router Sit in a System?

Consider an application that receives messages from multiple sources, normalizes them into `OrderEvent`, and selects either an express or standard shipping lane.

~~~mermaid
flowchart LR
    A["File / SFTP inbound<br/>or HTTP/JMS/Kafka"]
    B["orders.input<br/>MessageChannel"]
    C["Validate / Normalize"]
    R{"Content-Based Router<br/>priority?"}
    E["orders.express"]
    S["orders.standard"]
    H1["Express Flow<br/>Transformer → Handler"]
    H2["Standard Flow<br/>Transformer → Handler"]
    D1[("Express service")]
    D2[("Standard service")]
    A --> B --> C --> R
    R -->|"EXPRESS"| E --> H1 --> D1
    R -->|"STANDARD"| S --> H2 --> D2
~~~

A router is a **message-handling endpoint**: it extracts a routing key from the payload or headers, resolves the matching channel, and sends the message to that channel. Some router types can resolve multiple channels, yet in standard *content-based routing* each message enters **one chosen branch**.

| Component | Purpose | Do Not Confuse With |
| --- | --- | --- |
| Filter | Decides whether a message continues or is rejected. | Router, since filters do not typically select among multiple business targets. |
| Transformer | Changes payload structure or type. | Router, since routing does not parse or alter schemas. |
| Router | Uses a key to select a target channel and downstream endpoint. | Outbound adapter, since routers do not talk to external systems directly. |
| Bridge | Forwards between two known channels. | Router, since bridges do not choose paths by content. |
| Publish–subscribe | Broadcasts the same message to multiple subscribers. | A router picking one branch. |
| Splitter | Splits one message into multiple child messages. | A router redirecting messages without decomposing collections. |
| Gateway | Provides request–reply exchange or a Java API. | Router, since gateways govern request/response boundaries. |

**Important rule:** every channel a router might select must have an appropriate consumer. If a router sends to a `DirectChannel` with no subscriber, dispatching fails. If it sends to a `QueueChannel`, a polling endpoint must consume from it. Declaring channel mappings alone is never enough for a complete pipeline.

## 3. Routing Keys, Channel Mappings, and Default Branches

A router relies on a **routing key**: a simple value used to select a branch. The key can come from the payload or message headers.

Example message contract:

~~~text
payload = OrderEvent(
    orderId = "ORD-1001",
    priority = "EXPRESS",
    amount = 250000
)

headers = {
    correlationId: "trace-ord-1001",
    sourceSystem: "sftp-import"
}
~~~

The routing key is `priority = "EXPRESS"`. Routing policy:

| Routing Key | Target Channel | Downstream Endpoint |
| --- | --- | --- |
| `EXPRESS` | `orders.express` | Express shipping flow and dedicated service. |
| `STANDARD` | `orders.standard` | Standard shipping flow. |
| `null` or any other value | Follows error or default route policy. | Never silently lose messages. |

Never let external input specify arbitrary bean names for a router to target. For keys coming from HTTP requests or partner headers, **validate and constrain allowed values**, then map them explicitly to internal channels. This also prevents bugs from casing mismatches, extra whitespace, or newly added codes not yet implemented.

Three common policies when no branch matches:

1. **Fail fast:** throw an exception so the upstream caller knows the value is unsupported.
2. **Default route:** send the message to a fallback channel whose consumer persists/quarantines it or applies standard handling.
3. **Deliberate discard:** use only when business rules truly permit dropping it, paired with metrics/auditing.

A default channel does not necessarily mean "success": it can be a **dead-letter or quarantine channel** for messages the system does not yet know how to handle.

## 4. Complete Example: Java DSL Routing Between Two Independent Flows

Let's build an application that receives `OrderEvent`, validates the order, and routes to **EXPRESS** or **STANDARD**. After the router, each branch has its own transformer and handler. A `@MessagingGateway` lets Java callers submit orders into the flow. Results are recorded in memory for clear observation; the example **does not perform real shipping**.

### 4.1. Dependency

The example uses Java 17+, Spring Boot, and Spring Integration managed by Boot's BOM:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
~~~

You can place all sample code in `RoutingApplication.java` under package `demo.routing`. Package-private `record` types and interfaces keep the example self-contained in one file.

### 4.2. Defining Channels, Router, and Branches

~~~java
package demo.routing;

import java.math.BigDecimal;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableIntegration
@IntegrationComponentScan
public class RoutingApplication {

    public static void main(String[] args) {
        SpringApplication.run(RoutingApplication.class, args);
    }

    @Bean(name = "orders.input")
    MessageChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean(name = "orders.express")
    MessageChannel expressOrders() {
        return new DirectChannel();
    }

    @Bean(name = "orders.standard")
    MessageChannel standardOrders() {
        return new DirectChannel();
    }

    // Flow 1: validate, then choose channel by priority.
    @Bean
    IntegrationFlow orderRouterFlow() {
        return IntegrationFlow.from("orders.input")
                .filter(OrderEvent.class,
                        order -> order.orderId() != null
                                && !order.orderId().isBlank()
                                && order.amount() != null
                                && order.amount().signum() > 0
                                && order.priority() != null,
                        endpoint -> endpoint.throwExceptionOnRejection(true))
                .route(OrderEvent.class, OrderEvent::priority,
                        router -> router
                                .channelMapping(
                                        "EXPRESS", "orders.express")
                                .channelMapping(
                                        "STANDARD", "orders.standard")
                                .resolutionRequired(true))
                .get();
    }

    // Flow 2: dedicated to EXPRESS orders.
    @Bean
    IntegrationFlow expressFlow(RouteRecorder recorder) {
        return IntegrationFlow.from("orders.express")
                .transform(OrderEvent.class,
                        order -> new DispatchCommand(
                                order.orderId(),
                                "EXPRESS",
                                order.amount()))
                .handle(DispatchCommand.class, (command, headers) -> {
                    recorder.record(new RoutedOrder(
                            command.orderId(),
                            command.lane(),
                            (String) headers.get("correlationId")));
                    return null; // one-way outbound branch
                })
                .get();
    }

    // Flow 3: dedicated to STANDARD orders.
    @Bean
    IntegrationFlow standardFlow(RouteRecorder recorder) {
        return IntegrationFlow.from("orders.standard")
                .transform(OrderEvent.class,
                        order -> new DispatchCommand(
                                order.orderId(),
                                "STANDARD",
                                order.amount()))
                .handle(DispatchCommand.class, (command, headers) -> {
                    recorder.record(new RoutedOrder(
                            command.orderId(),
                            command.lane(),
                            (String) headers.get("correlationId")));
                    return null; // one-way outbound branch
                })
                .get();
    }
}

@MessagingGateway(defaultRequestChannel = "orders.input")
interface OrderGateway {
    void submit(
            @Payload OrderEvent event,
            @Header("correlationId") String correlationId);
}

record OrderEvent(String orderId, String priority, BigDecimal amount) {}

record DispatchCommand(String orderId, String lane, BigDecimal amount) {}

record RoutedOrder(String orderId, String lane, String correlationId) {}

@Component
class RouteRecorder {
    private final List<RoutedOrder> received =
            new CopyOnWriteArrayList<>();

    void record(RoutedOrder order) {
        received.add(order);
        System.out.println("Routed: " + order);
    }

    List<RoutedOrder> snapshot() {
        return List.copyOf(received);
    }

    void clear() {
        received.clear();
    }
}
~~~

### 4.3. Tracing the Path

Each `IntegrationFlow` bean owns a single responsibility:

- `orderRouterFlow` receives `Message<OrderEvent>` from `orders.input`, enforces the contract, and extracts `priority` as the routing key.
- Mapping `EXPRESS → orders.express` sends the order to `expressFlow`'s input.
- Mapping `STANDARD → orders.standard` sends the order to `standardFlow`'s input.
- Each branch transforms `OrderEvent` into `DispatchCommand`; the handler records a `RoutedOrder` containing the selected lane and `correlationId`.
- The handler returns `null`: the branch ends one-way with no business reply to the caller.

Spring Integration registers `OrderGateway` as a proxy via `@IntegrationComponentScan`. When a caller invokes:

~~~java
gateway.submit(
        new OrderEvent(
                "ORD-1001", "EXPRESS", new BigDecimal("250000")),
        "trace-ord-1001");
~~~

`RouteRecorder` records one entry:

~~~text
RoutedOrder[
    orderId=ORD-1001,
    lane=EXPRESS,
    correlationId=trace-ord-1001
]
~~~

Both branches are never invoked simultaneously for a single `EXPRESS` message. In this example, the channels are `DirectChannel` beans, so the router, transformer, and handler usually run on the sending thread. Even a `void` gateway method still blocks until synchronous processing finishes.

### 4.4. Why Split Branches into Separate Flow Beans?

When each branch adds endpoints such as an HTTP outbound gateway, JMS publisher, SFTP writer, or JDBC handler, splitting into separate `IntegrationFlow` beans makes independent changes and contract testing much easier. The router only needs the names of **target channels**, not which protocols downstream endpoints speak.

When branches share downstream processing, you can create a **converging channel** that both branches forward to after normalizing payloads. In that case, decide whether ordering matters, whether aggregation is needed, and whether the shared channel's consumer accepts a uniform payload type.

## 5. Testing Individual Branches and Unsupported Keys

To prove the router and branch endpoints are truly wired by Spring, call through `OrderGateway` in an integration test instead of calling bean factory methods directly.

Add the test dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Create `RoutingApplicationTest.java` in package `demo.routing`:

~~~java
package demo.routing;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.messaging.MessagingException;

@SpringBootTest
class RoutingApplicationTest {

    @Autowired
    OrderGateway gateway;

    @Autowired
    RouteRecorder recorder;

    @BeforeEach
    void reset() {
        recorder.clear();
    }

    @Test
    void expressGoesOnlyToExpressEndpoint() {
        gateway.submit(
                new OrderEvent(
                        "ORD-E1", "EXPRESS", new BigDecimal("100")),
                "trace-express");

        assertEquals(
                List.of(new RoutedOrder(
                        "ORD-E1", "EXPRESS", "trace-express")),
                recorder.snapshot());
    }

    @Test
    void standardGoesOnlyToStandardEndpoint() {
        gateway.submit(
                new OrderEvent(
                        "ORD-S1", "STANDARD", new BigDecimal("200")),
                "trace-standard");

        assertEquals(
                List.of(new RoutedOrder(
                        "ORD-S1", "STANDARD", "trace-standard")),
                recorder.snapshot());
    }

    @Test
    void rejectsUnsupportedPriority() {
        assertThrows(MessagingException.class,
                () -> gateway.submit(
                        new OrderEvent(
                                "ORD-X1", "SAME_DAY",
                                new BigDecimal("300")),
                        "trace-unknown"));

        assertTrue(recorder.snapshot().isEmpty());
    }

    @Test
    void rejectsInvalidAmount() {
        assertThrows(MessagingException.class,
                () -> gateway.submit(
                        new OrderEvent(
                                "ORD-X2", "EXPRESS", BigDecimal.ZERO),
                        "trace-invalid"));

        assertTrue(recorder.snapshot().isEmpty());
    }
}
~~~

The two happy-path tests verify routing keys, channel mappings, and per-branch handlers. The two negative tests verify **invalid inputs never reach business endpoints**. With filter/router configurations over `DirectChannel`, errors typically propagate back to the caller as `MessagingException` or a subtype/exception whose root cause indicates routing failure or message rejection.

If a real project wraps exceptions in additional proxy layers, inspect the cause chain per contract rather than coupling unconditionally to one outer exception class. Note that this example test does not prove external delivery since `RouteRecorder` is an in-memory bean.

## 6. Routing by Header Instead of Payload

Besides `priority` in the payload, a router can inspect metadata such as `tenantId`, `sourceSystem`, `eventType`, or a target system code. This is useful when payloads are already standardized yet the route depends on source or protocol context.

Conceptual logic example:

~~~text
Message<UnifiedEvent>
    payload = UnifiedEvent(...)
    headers.routeCode = "billing"

routeCode="billing"  -> events.billing
routeCode="shipping" -> events.shipping
routeCode=other      -> events.unsupported
~~~

One option is declaring `@Router` on a Spring bean method:

~~~java
@Component
class OrderDestinationRouter {

    @Router(inputChannel = "orders.ready")
    public String selectDestination(OrderEvent order) {
        return switch (order.priority()) {
            case "EXPRESS" -> "orders.express";
            case "STANDARD" -> "orders.standard";
            default -> "orders.unsupported";
        };
    }
}
~~~

This snippet assumes imports for `org.springframework.integration.annotation.Router`, `OrderEvent` from section 4, a channel bean for `orders.ready`, and consumers for all three target channels. It is an **alternative approach** to the Java DSL router—do not register both concurrently on the same channel unless competing consumers are intended.

The method above returns the **target channel name**. If you only want to return a routing key, pair it with the router's channel mapping support; never confuse the key `"EXPRESS"` with the bean name `"orders.express"`.

### 6.1. Externally Supplied Headers Must Be Validated

Using headers avoids touching the payload, yet it introduces the risk of letting external input dictate internal routing. For instance, never allow an arbitrary HTTP header to be interpreted directly as an internal admin channel bean name.

Best practices:

1. Parse and normalize the header against a fixed allowlist.
2. Verify authorization or tenant ownership if routing touches sensitive data.
3. Map business keys to internal channels through static configuration.
4. Log correlation IDs and routing decisions without logging secrets or entire payloads.
5. Define fallback behavior for missing, null, or invalid headers.

## 7. Default Branches and Unmatched Message Strategies

The opening example sets `resolutionRequired(true)`: when the router finds no matching channel, it raises an error. In multi-partner integrations, another option is routing unmatched messages to an **unsupported channel**.

Illustrative Java DSL configuration:

~~~java
.route(OrderEvent.class, OrderEvent::priority,
        router -> router
                .channelMapping("EXPRESS", "orders.express")
                .channelMapping("STANDARD", "orders.standard")
                .defaultOutputChannel("orders.unsupported"))
~~~

This snippet **replaces** the `.route(...)` call in section 4 and requires an `orders.unsupported` channel bean with a consumer.

The topology becomes:

~~~mermaid
flowchart TD
    R{"priority"}
    E["orders.express"]
    S["orders.standard"]
    U["orders.unsupported<br/>quarantine / audit"]
    R -->|"EXPRESS"| E
    R -->|"STANDARD"| S
    R -->|"Other / unmatched"| U
~~~

A handler on `orders.unsupported` can persist the message to an error table, dead-letter queue, or quarantine file for inspection. **Never return a success response** just because the message landed on the fallback channel if the fallback's purpose is recording failures.

Distinguish two distinct failure cases:

- **Unmapped key:** the router does not know where to send it, so fail or fall back.
- **Mapped channel fails to deliver:** e.g. stopped subscriber, full queue, or failing target adapter. This is a **dispatch/delivery failure**, which a default channel alone does not necessarily catch. Handle it with endpoint error policies, retries/advice, and error channels.

Specifically with `QueueChannel`, succeeding on send only confirms the message entered the queue at that instant; it does not confirm a consumer or external system processed it.

## 8. Routing Across Multiple Endpoints with XML Namespaces

XML namespaces express the same behavior when a project already uses Spring Integration XML configuration.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:int="http://www.springframework.org/schema/integration"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           http://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/integration
           http://www.springframework.org/schema/integration/spring-integration.xsd">

    <int:channel id="orders.input"/>
    <int:channel id="orders.express"/>
    <int:channel id="orders.standard"/>

    <int:router input-channel="orders.input"
                expression="payload.priority">
        <int:mapping value="EXPRESS" channel="orders.express"/>
        <int:mapping value="STANDARD" channel="orders.standard"/>
    </int:router>

    <!-- Service activator or flow consumer for each branch
         is configured separately. -->
</beans>
~~~

The router uses an expression to extract the key from the payload. For a Java `record` like `OrderEvent`, SpEL property access can depend on introspection support and framework version; in real projects, provide explicit getter methods or bean accessors if the parser does not resolve record components as expected. Each mapping also requires the target channel to exist with a consumer.

Example of a **header-based** router:

~~~xml
<int:header-value-router input-channel="events.input"
                         header-name="routeCode">
    <int:mapping value="billing" channel="events.billing"/>
    <int:mapping value="shipping" channel="events.shipping"/>
</int:header-value-router>
~~~

This is a standalone snippet; `events.input`, `events.billing`, and `events.shipping` require corresponding channel beans and consumers.

In Spring Boot, XML can be loaded via `@ImportResource("classpath:integration/routing.xml")`. Avoid accidentally registering **both an XML router and a Java DSL router reading the same `DirectChannel`** when only one routing path is intended.

## 9. How Routers Differ from PublishSubscribeChannel and Recipient List Routers

The requirement **"route across multiple endpoints"** can mean two very different things:

1. One message selects **one** endpoint out of many.
2. One message must be delivered to **multiple** endpoints simultaneously.

The Content-Based Router in our example picks one branch by `priority`. If the requirement is sending the same event to both an audit system **and** an analytics system, use a fan-out mechanism such as `PublishSubscribeChannel` or a **Recipient List Router** with per-recipient conditions.

~~~mermaid
flowchart LR
    A["Message<OrderEvent>"]
    R{"Content-Based Router"}
    E["Express endpoint"]
    S["Standard endpoint"]
    P["PublishSubscribeChannel"]
    AUD["Audit endpoint"]
    MET["Metrics endpoint"]
    A --> R
    R -->|"EXPRESS"| E
    R -->|"STANDARD"| S
    A --> P
    P --> AUD
    P --> MET
~~~

| Need | Suitable Component | What to Watch |
| --- | --- | --- |
| Pick one branch by `priority` | Payload/router mapping. | Unknown keys, branch failures, target channels. |
| Pick a branch by source header | Header value router. | Validation and header provenance. |
| Broadcast same message to all subscribers | `PublishSubscribeChannel`. | Single-subscriber errors, threading, dispatch order. |
| Send to a dynamic subset of recipients | Recipient List Router. | Mandatory vs. optional recipients, per-recipient errors, duplicates. |
| Split a list of orders into individual messages | Splitter. | Correlation/sequence headers and group completion. |
| Combine results from multiple branches into one reply | Aggregator or conditional join. | Correlation, timeouts, release strategy, persistent state. |

If multiple branches return replies for **a single** gateway call, design explicit aggregation or pick one final reply. Never register two response-producing handlers on the same reply path assuming the framework merges them automatically.

## 10. Routing Inside Request–Reply Flows

A router does not have to end one-way. With a messaging gateway or HTTP inbound gateway, a request can pass through a router, get handled on the matching branch, and return a reply to the original caller.

~~~mermaid
sequenceDiagram
    participant C as Java caller
    participant G as @MessagingGateway
    participant R as Router
    participant S as Branch handler
    C->>G: query(OrderRequest)
    G->>R: Message + replyChannel
    R->>S: route by request type
    S-->>G: OrderResponse via replyChannel
    G-->>C: OrderResponse
~~~

Branch handlers can return the same DTO type:

~~~java
@ServiceActivator(inputChannel = "quotes.domestic")
public QuoteResult domesticQuote(QuoteRequest request) {
    return new QuoteResult(request.id(), "DOMESTIC", 12000);
}

@ServiceActivator(inputChannel = "quotes.international")
public QuoteResult internationalQuote(QuoteRequest request) {
    return new QuoteResult(request.id(), "INTERNATIONAL", 55000);
}
~~~

This snippet assumes `QuoteRequest`, `QuoteResult`, and the channels are defined elsewhere, with each method inside a Spring bean. The request–reply gateway must send into the channel feeding the router and return `QuoteResult`.

For the reply to reach the caller, keep a valid return path: headers carrying `replyChannel` and correlation info must not be stripped by transformers or routers, and the terminal endpoint must actually emit a response. If one branch ends in a one-way outbound adapter or `void` method, a gateway awaiting a DTO can wait until timeout.

**Output channels and reply channels serve different roles:** the router sends the request to the selected branch channel; `replyChannel` belongs to **the specific request**. When sharing a reply channel across concurrent callers, implement strict correlation and timeouts so responses never leak between requests.

## 11. How Channel Types Affect Performance and Routing Errors

The router decides **which channel**, while the channel and endpoints decide **how the message is delivered**.

| Branch Channel | Typical Execution | When to Consider |
| --- | --- | --- |
| `DirectChannel` | Invokes subscriber on the sending thread. | Fast handlers needing synchronous error propagation. |
| `QueueChannel` | Enqueues message for later polling. | When bounded buffering is needed with a designed polling consumer. |
| `ExecutorChannel` | Hands processing off to an executor thread. | Isolating latency with bounded executors and explicit error handling. |
| `PublishSubscribeChannel` | Broadcasts to multiple subscribers. | Intentional fan-out; not for single-branch selection. |

Suppose `orders.express` uses `DirectChannel` and its handler calls a shipping API taking 8 seconds. When a caller sends an `EXPRESS` order through a `void` gateway, the Java call can still block for 8 seconds due to synchronous execution. A router **never turns endpoints asynchronous on its own**.

If `orders.express` is a `QueueChannel`, messages wait in the queue. You then need a poller on the receiving endpoint plus capacity, backlog, and retry management. `QueueChannel` buffers in memory by default; if survival across restarts is required, add a persistent message store or use a broker with suitable delivery semantics.

### 11.1. Ordering and Transactions Across a Router

A route using `DirectChannel` keeps processing on the same thread, yet ordering between **two different branches** is never guaranteed if they use independent workers or pollers. In particular, crossing into queues, executors, or brokers changes observed ordering and transaction boundaries.

For payments or inventory updates, never assume "the earlier message always finishes first" when branches run concurrently. If ordering matters, enforce keys/partitions, serialization, locking, or transactional processing as needed.

A router does not create a distributed transaction spanning JMS, HTTP, and databases. When consistency across DB writes and broker events is required, consider transactional outboxes, sagas/compensation, or reconciliation.

## 12. Errors, Retries, and Idempotency in Branched Flows

A flow with a router has multiple failure points:

~~~mermaid
flowchart TD
    S["Inbound adapter"]
    V{"Validate"}
    R{"Router selects key"}
    E["Express branch"]
    N["Standard branch"]
    U["Unsupported / quarantine"]
    O["External endpoint"]
    ERR["Retry / Error flow / DLQ"]
    S --> V
    V -->|"Valid"| R
    V -->|"Invalid"| ERR
    R -->|"EXPRESS"| E --> O
    R -->|"STANDARD"| N --> O
    R -->|"Unmatched"| U
    E -. "timeout" .-> ERR
    N -. "timeout" .-> ERR
~~~

| Error Type | Location | Handling Strategy |
| --- | --- | --- |
| Schema-invalid payload | Before router. | Validate and reject/quarantine; do not retry malformed payloads infinitely. |
| Unsupported routing key | At router. | Fail fast or route to default channel; emit metrics and source info. |
| Target channel has no consumer | Dispatch to branch. | Check topology/startup, alert, and define retry conditions. |
| HTTP/JMS/Kafka/SFTP/DB endpoint error | Inside branch. | Client retries/backoff, dead-letter handling, protocol confirmations. |
| Uncertain outcome after timeout | External side effect. | Reconcile via business key; enforce idempotency at target. |
| One branch lags | Branch queue/executor. | Bound backlog, manage threads, and set timeouts. |

### 12.1. Why Can Retries Route to the Wrong Branch?

Suppose order `ORD-1001` already went down the `EXPRESS` branch and the partner created a shipment. The response was lost, so upstream retries the same message. If the router inspects mutable state (for example, an updated priority field), the retry may travel down **the other branch**, producing two side effects.

Decide up front:

- Is the routing key immutable per event/command?
- Should the **routing decision** be stored in durable metadata so replays hit the same branch?
- How does each branch enforce idempotency by `eventId`/`orderId`?
- Which states count as "received", "dispatched", and "business-completed"?

For replayable events, store the normalized routing key, correlation ID, and routing-rule version alongside the record. That lets you reproduce decisions accurately when investigating incidents after config updates.

### 12.2. Error Channels in Asynchronous Processing

When the router and handlers use `DirectChannel`, handler exceptions can unwind up the call stack to the sender or gateway. When a branch switches to `QueueChannel`, `ExecutorChannel`, or a broker listener, exceptions happen on another thread and may be published as an `ErrorMessage` to `errorChannel` per endpoint configuration.

No single error channel automatically solves errors across every layer. Separate source errors, routing errors, dispatch failures, and external adapter errors; each group needs tailored retry and alerting policies.

## 13. Routing Across Multiple Sources and Protocols

In the **SPRING_INTEGRATION_ADAPTERS** module, a router often sits right after a unified normalization step for multiple adapters:

| Source | Initial Payload | Normalization Step | Routing Key / Target |
| --- | --- | --- | --- |
| CSV file or SFTP | `File` or `byte[]` | Parse CSV into `OrderEvent`. | `priority` → express/standard. |
| HTTP inbound gateway | JSON/DTO request | Validate, map DTO and metadata. | `tenantId` or `requestType` → service. |
| JMS/AMQP listener | Broker message payload | Convert and validate event. | `eventType` → order/payment handler. |
| Kafka inbound | Record with topic, partition, key | Deserialize, check schema. | Business key → matching flow. |
| JDBC polling | `Map` / data record | Map to domain DTO. | `status` or business type → handler. |

Example of multiple sources converging on one contract:

~~~mermaid
flowchart LR
    F["File/SFTP"]
    J["JMS/AMQP"]
    K["Kafka"]
    H["HTTP"]
    N["Normalize → OrderEvent"]
    C["orders.input"]
    R{"Router"}
    EX["Express flow"]
    ST["Standard flow"]
    F --> N
    J --> N
    K --> N
    H --> N
    N --> C --> R
    R --> EX
    R --> ST
~~~

Each adapter remains responsible for connections, acknowledgements, offsets/polling, source retries, and resource cleanup. The router only sees messages conforming to the shared contract. **Never use a router to paper over schema differences between sources:** parse and normalize before routing.

### 13.1. Technical Headers vs. Business Headers

Framework headers like `replyChannel`, `errorChannel`, or Kafka/JMS-specific headers do not always survive across HTTP/broker boundaries unchanged. When routing by a header such as `tenantId`, verify that converters and mappers actually populate and preserve that header.

Use stable, business-meaningful routing keys and test header mapping explicitly. Avoid coupling to legacy connector header names, as protocol modules can change header-mapping behavior across versions.

## 14. Design Recommendations as Branch Count Grows

A two-mapping router is trivial to follow. As integrations grow to dozens of partners and workflows, keep the topology disciplined:

1. **Normalize keys first:** prevent one branch using `"Express"`, another `"EXPRESS"`, and another `" express "`.
2. **Name channels by intent:** `orders.express`, `orders.standard`, or `payments.review` are far clearer to observe than `channel1`.
3. **Keep routing logic pure:** if rules grow complex, extract them to a unit-testable service and let the router simply map results to channels.
4. **Never leave a downstream channel without a consumer:** every mapping should have an active endpoint at context startup.
5. **Define an unknown-key policy:** fail fast, fall back, or quarantine with clear error codes and metrics.
6. **Instrument every branch separately:** throughput, latency, failure rate, queue depth, retries, and target acks.
7. **Version your contracts:** when introducing new routing keys, account for instances still running older versions.
8. **Bound fan-out cost:** if sending to multiple recipients, measure and handle per-branch failures rather than confusing it with single-branch routing.

In large systems, routing rules may live in config stores or databases; that requires change management, pre-apply validation, and caching/versioning. Never query a remote config database synchronously on every message without timeouts or fallbacks, or the router itself becomes a bottleneck.

## 15. Common Design Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Messages enter router, yet no handler runs. | Unmapped routing key, target channel has no subscriber, or stopped endpoint. | Log normalized key; verify mappings, channel beans, and consumers. |
| All orders go to the `STANDARD` branch. | Expression/mapper reads the wrong field; default route is overly broad. | Test each key explicitly; monitor fallback counts and alert on anomalies. |
| Message reaches only one of two handlers when both were wanted. | Used content router or `DirectChannel` instead of multicast. | Use `PublishSubscribeChannel` or `RecipientListRouter` with clear semantics. |
| Message unexpectedly enters both branches. | Accidental fan-out config or two inbound sources emitting the same event. | Audit topology, deduplication, and routing rules. |
| Caller times out after routing to a branch. | Branch ends one-way while gateway awaits reply, or `replyChannel` was lost. | Align one-way vs. request–reply contracts, preserve headers, and emit replies. |
| Queue holds messages, yet handler receives nothing. | Branch uses `QueueChannel` without a poller. | Register a polling consumer and monitor queue depth. |
| Source slows down unexpectedly. | `DirectChannel` branch performs blocking HTTP/DB calls. | Enforce client timeouts, backpressure, or bounded async channels. |
| Retries create duplicate records at partner. | Side effect succeeded, yet response was lost. | Use idempotency keys, unique constraints, and reconciliation. |
| Messages route differently after restart or replay. | Routing key or rules changed mid-flight. | Persist rule version/route decision and freeze keys where needed. |
| Both XML and Java DSL routers subscribe to one input channel. | Two competing endpoints registered unintentionally. | Keep one router or design explicit dispatch/fan-out. |
| Errors never reach the caller. | Branch runs on an executor or broker thread. | Implement error flows, DLQ, retries, and async error contracts. |

## 16. Practice Exercise: Routing Orders to Three Endpoints

**Context:** an application receives orders from SFTP CSV files and an HTTP API. After normalizing into `OrderEvent`, route by `priority` and `currency`:

- `EXPRESS` + `VND`: route to domestic express delivery service.
- `EXPRESS` + other currency: route to international delivery service.
- `STANDARD`: route to standard processing.
- Missing/unsupported values: send to a review channel.

**Tasks:**

1. Design `OrderEvent(id, priority, currency, amount)` and headers `sourceSystem`, `correlationId`, and `idempotencyKey`.
2. Create inbound channel `orders.input`, a validation step, and a router selecting channels per the rules above.
3. Register three branch endpoints as separate `IntegrationFlow` beans, each with a transformer and simulated outbound handler.
4. Add fallback channel `orders.review` with a consumer storing the rejection reason and payload metadata for inspection.
5. Write tests for all three valid branches, invalid data, and unknown keys, verifying messages never cross into unintended branches.
6. Switch the international branch to a `QueueChannel` with a polling consumer; measure changes in gateway return timing and processing duration.
7. Simulate an outbound timeout after the partner received the order, then implement idempotency so replays never create a second shipment.
8. Add a separate `PublishSubscribeChannel` to send a copy of successful events to auditing while ensuring only one fulfillment branch executes side effects.

**Completion criteria:** mappings are explicit, target channels have consumers, errors are never swallowed, correlation headers stay intact, tests verify exact branch delivery, and you explain reliability across queues and external adapters.

## 17. Self-Check Questions

1. What information does a Content-Based Router use to select a destination channel?
2. How does `.route(...)` differ from `.transform(...)` and `.filter(...)`?
3. Why must every channel selected by a router have an active consumer?
4. When a routing key has no match, what policies are available?
5. How does a header-based router differ from a payload-based router?
6. If two endpoints must both receive the same message, which channel type or pattern should you use?
7. If one branch uses a `QueueChannel`, what must be configured so messages do not sit idle forever?
8. When routing inside a request–reply flow, why must `replyChannel` be preserved?
9. Why does a `void` gateway method not guarantee asynchronous execution?
10. Does a router automatically guarantee transactional consistency between a database and HTTP?
11. How does a channel dispatch error differ from an HTTP client error inside a branch?
12. When replaying events after a routing-rule change, how do you preserve consistency?
13. How do you test that each key reaches only its intended endpoint?
14. What payload/header contract should a shared channel receiving from both SFTP and Kafka enforce?

**Hints:** a router decides the path, while channels, consumers, and adapters govern execution timing, error paths, acknowledgements, and side effects. Normalize data before routing; test each branch and recovery path afterward.

## 18. Key Takeaways

**Routing flows across multiple endpoints** is how Spring Integration directs messages to the right branch based on payload or headers. In the Java DSL, `IntegrationFlow.route(...)` maps business keys to channels, each starting its own flow or endpoint. `@Router` annotations and XML namespaces provide equivalent configurations.

In the **SPRING_INTEGRATION_ADAPTERS** module, routers often follow file/SFTP, HTTP, JMS, AMQP, Kafka, or JDBC adapters, yet flow quality hinges on **message contracts, channel mappings, default branches, reply/error handling, threading/transactions, and idempotency**. A sound routing design clearly shows where every message goes, who consumes it, how failures recover, and when an outbound operation truly counts as complete.
