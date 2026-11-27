# Combining Functions with Channels, Pollers, Transformers, and Gateways

## 1. Problem Statement: Independent Business Logic, Orchestrated Message Flows

**Spring Cloud Function (SCF)** lets you write business logic with `Supplier<T>`, `Function<T,R>`, and `Consumer<T>`, managed through `FunctionCatalog` and chained via composition. An order normalization or classification function does not need to know whether it is invoked over HTTP, events, or serverless.

**Spring Integration** handles connectivity and orchestration: message channels, polling endpoints, transformers, gateways, routers, filters, error flows, and Enterprise Integration Patterns (EIP). Together, they let us reuse **the exact same function** in multiple ways without duplicating business rules.

Suppose there are two sources requesting order classification:

- A caller invokes the Java method `orderGateway.classify(order)` and expects **an immediate result** via request/reply.
- A scheduled task pulls pending orders from a queue and **pushes results to a consumer**, with no caller waiting for a reply.

Both must share `normalizeOrder|classifyOrder` in `FunctionCatalog`.

~~~mermaid
flowchart LR
    subgraph G["Path 1: Request / Reply"]
      A["OrderGateway.classify(...) call"] --> B["orders.gatewayInput<br/>DirectChannel"]
      B --> C["Transformer:<br/>FunctionCatalog.lookup(...)"]
      C --> D["gateway's<br/>replyChannel"]
      D --> E["OrderDecision returned to caller"]
    end
    subgraph P["Path 2: Polling"]
      Q["pendingOrders queue"] --> S["Supplier: pendingOrderSource"]
      T["Poller 250 ms"] --> S
      S --> F["apply:<br/>normalizeOrder|classifyOrder"]
      F --> H["orders.completed<br/>DirectChannel"]
      H --> I["Consumer: captureDecision"]
    end
~~~

**Learning objectives:** understand each component's responsibility; implement two paths reusing the same function; distinguish `from("channel")`, `fromSupplier("supplier")`, `transform(...)`, and gateways; and know how to test and handle errors in both synchronous and polling models.

## 2. Four Concepts to Distinguish

| Component | Role in Spring Integration | Example | What Is Not Automatically Guaranteed |
| --- | --- | --- | --- |
| **Message Channel** | Connects endpoints and governs delivery traits such as synchronous dispatch, queuing, or executor handoff. | `DirectChannel`, `QueueChannel`, `ExecutorChannel`. | Does not automatically serialize to JSON, persist messages, or provide broker retries. |
| **Poller** | Actively polls a message source or reads from a pollable channel on a schedule. | `Pollers.fixedDelay(250).maxMessagesPerPoll(1)`. | Does not automatically guarantee acknowledgements, transactions, or recovery of fetched items. |
| **Transformer** | Converts a payload/message so the next step receives data in the expected form. | `.transform(OrderRequest.class, pipeline::apply)`. | Does not choose among multiple target branches like a router. |
| **Messaging Gateway** | Creates a proxy for a Java interface, maps method calls to messages, receives replies, and converts back to the return type. | `@MessagingGateway` and `OrderDecision classify(OrderRequest)`. | Is not an HTTP gateway, reverse proxy, or Spring Cloud Gateway. |

An **IntegrationFlow** describes how these endpoints are wired together. The actual endpoints are created and managed by Spring Integration in the application context.

### 2.1. Distinguishing a Channel from a Function

`Function<OrderRequest,OrderDecision>` returns a value, yet does not send that value anywhere on its own. Once `FunctionCatalog` returns the function, Spring Integration can use it as a transformer and forward the output through a `MessageChannel`.

Conversely, a `MessageChannel` primarily carries **`Message<T>`** between endpoints; business rules such as the priority order threshold should live in functions so they remain reusable.

### 2.2. Two Very Different Trigger Styles

~~~text
Push:
caller.send(message) or gateway.method(arg)
    → channel → endpoint → reply/consumer

Pull:
scheduler trigger
    → poller → Supplier.get() / MessageSource.receive()
    → message → endpoint → consumer
~~~

Merely having type `Supplier` does not make an object run on a schedule. Polling semantics come from the endpoint and poller managed by Spring Integration.

## 3. Dependencies and Version Requirements

The examples use Java 17+ and compatible Spring Boot, Spring Cloud, and Spring Integration versions. For Maven, assume the application already declares a Spring Boot parent and an appropriate Spring Cloud BOM:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-function-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Corresponding Gradle configuration:

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-function-integration'
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

The `spring-cloud-function-integration` module was introduced in **Spring Cloud Function 4.0.3**; it provides `FunctionFlowBuilder` and catalog-name function calls directly inside the Integration DSL. Check your actual release train before copying examples; do not arbitrarily mix SCF, Spring Boot, and Spring Integration across incompatible major versions.

This lesson uses two DSL styles:

1. **Core Java DSL**: `IntegrationFlow.from(...).transform(...)` with a function retrieved via `catalog.lookup(...)`.
2. **Function DSL**: `FunctionFlowBuilder.fromSupplier(...).apply(...).accept(...)` using automatically looked-up function names.

Both can coexist in one application. The example places them on **two different sources** to avoid creating two competing subscribers or processing the same message twice.

## 4. Designing the Example: Order Classification

We define:

~~~text
OrderRequest(id, totalVnd)
      │
      ├─ normalizeOrder: Function<OrderRequest, OrderRequest>
      │      validate and normalize order ID
      ▼
clean OrderRequest
      │
      ├─ classifyOrder: Function<OrderRequest, OrderDecision>
      │      orders >= 1,000,000 VND → PRIORITY
      ▼
OrderDecision(id, totalVnd, lane)
~~~

Two ways to consume the same pipeline:

- **Gateway:** Java method `classify(...)` returns `OrderDecision` to the caller.
- **Poller:** `Supplier<OrderRequest>` pops orders from a queue; the flow runs the pipeline and forwards the decision to `Consumer<OrderDecision>` for recording.

Sample dataset:

| Input | Result | Lane |
| --- | --- | --- |
| `("  dh-101 ", 1_500_000)` | `("DH-101", 1_500_000, "PRIORITY")` | Priority |
| `("dh-102", 500_000)` | `("DH-102", 500_000, "STANDARD")` | Standard |
| `(" ", 100_000)` | Rejected with `IllegalArgumentException` | No decision emitted |
| `("dh-103", 0)` | Rejected with `IllegalArgumentException` | No decision emitted |

Values use `long` to illustrate integer VND amounts; real systems should select an appropriate monetary type and rounding policy.

## 5. Functions Reused via FunctionCatalog

Create `src/main/java/example/orders/OrderFunctions.java`:

~~~java
package example.orders;

import java.util.Locale;
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderRequest(String id, long totalVnd) {}
record OrderDecision(String id, long totalVnd, String lane) {}

@Configuration
class OrderFunctions {

    @Bean
    Function<OrderRequest, OrderRequest> normalizeOrder() {
        return order -> {
            if (order == null
                    || order.id() == null
                    || order.id().isBlank()
                    || order.totalVnd() <= 0) {
                throw new IllegalArgumentException("Invalid order");
            }

            return new OrderRequest(
                    order.id().strip().toUpperCase(Locale.ROOT),
                    order.totalVnd());
        };
    }

    @Bean
    Function<OrderRequest, OrderDecision> classifyOrder() {
        return order -> new OrderDecision(
                order.id(),
                order.totalVnd(),
                order.totalVnd() >= 1_000_000 ? "PRIORITY" : "STANDARD");
    }
}
~~~

Both functions contain the business logic:

- `normalizeOrder` validates the input and normalizes the order ID, returning a new record rather than mutating the input.
- `classifyOrder` classifies based on total amount, unaware of channels, pollers, gateways, or brokers.
- Both can be looked up individually or as the composition `normalizeOrder|classifyOrder`.

Calling the catalog directly:

~~~java
Function<OrderRequest, OrderDecision> pipeline =
        catalog.lookup("normalizeOrder|classifyOrder");

OrderDecision result =
        pipeline.apply(new OrderRequest(" dh-101 ", 1_500_000));
// OrderDecision[id=DH-101, totalVnd=1500000, lane=PRIORITY]
~~~

Composition requires the first function's `OrderRequest` output to be compatible with the second function's input. If converters or wrappers change types, test the actual conversion.

## 6. Channels, Supplier, and Consumer

Create `src/main/java/example/orders/OrderFlows.java` to hold the configuration. First part of the file:

~~~java
package example.orders;

import java.util.Objects;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.cloud.function.integration.FunctionFlowBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.messaging.MessageChannel;

@Configuration
class OrderFlows {

    @Bean("orders.gatewayInput")
    MessageChannel gatewayInput() {
        return new DirectChannel();
    }

    @Bean("orders.completed")
    MessageChannel completedChannel() {
        return new DirectChannel();
    }

    @Bean("pendingOrders")
    BlockingQueue<OrderRequest> pendingOrders() {
        return new LinkedBlockingQueue<>();
    }

    @Bean("completedOrders")
    BlockingQueue<OrderDecision> completedOrders() {
        return new LinkedBlockingQueue<>();
    }

    @Bean
    Supplier<OrderRequest> pendingOrderSource(
            @Qualifier("pendingOrders")
            BlockingQueue<OrderRequest> pendingOrders) {
        return pendingOrders::poll;
    }

    @Bean
    Consumer<OrderDecision> captureDecision(
            @Qualifier("completedOrders")
            BlockingQueue<OrderDecision> completedOrders) {
        return completedOrders::add;
    }

    // The two IntegrationFlow beans are added in Sections 7 and 8.
}
~~~

This is the **class skeleton**; add the two `@Bean IntegrationFlow` methods from Sections 7 and 8 **inside `OrderFlows`**, before the closing brace of the class. Do not create a second `OrderFlows` class.

`pendingOrderSource` retrieves an item from the queue without blocking: `Queue.poll()` returns `null` when the queue is empty. `captureDecision` is the terminal consumer and writes to another queue. This enables testing without standing up a broker or database.

### 6.1. Why Are Both Channels DirectChannel?

- `orders.gatewayInput` carries requests for the gateway flow. Because `DirectChannel` invokes its subscriber on the same thread (when no async boundary is present), the caller receives the request/reply result immediately.
- `orders.completed` connects the transformer in the polling path to the terminal consumer. It is purely an internal message boundary—not a Kafka topic, and it provides no durable storage.

The two queues `pendingOrders`/`completedOrders` in the demo are **Java `BlockingQueue` instances used for input and observation**, not Spring Integration `QueueChannel` beans. Distinguishing them prevents confusing collection semantics with framework message channels.

## 7. The Gateway Path: channel → transformer → reply

### 7.1. Defining the Messaging Gateway

Create `src/main/java/example/orders/OrderGateway.java`:

~~~java
package example.orders;

import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(
        defaultRequestChannel = "orders.gatewayInput",
        defaultReplyTimeout = "5000")
public interface OrderGateway {
    OrderDecision classify(OrderRequest request);
}
~~~

`@MessagingGateway` instructs Spring Integration to generate a proxy for the interface. Callers only see a Java method and return type without building `Message<?>` manually. Here, `defaultReplyTimeout` is 5,000 milliseconds if no reply arrives.

Scanning for the gateway interface must be enabled. Create `src/main/java/example/orders/OrderApplication.java`:

~~~java
package example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.integration.annotation.IntegrationComponentScan;

@SpringBootApplication
@IntegrationComponentScan
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Because all files share package `example.orders`, component scanning discovers the `@Configuration` classes and the gateway interface. If you place the gateway in another package, adjust `@IntegrationComponentScan`'s scope accordingly.

### 7.2. Transformer Calling the Composition from FunctionCatalog

Add this bean method inside `OrderFlows` from Section 6:

~~~java
@Bean
IntegrationFlow gatewayReplyFlow(FunctionCatalog catalog) {
    Function<OrderRequest, OrderDecision> pipeline =
            Objects.requireNonNull(
                    catalog.lookup("normalizeOrder|classifyOrder"),
                    "Order-processing composition not found");

    return IntegrationFlow.from("orders.gatewayInput")
            .transform(OrderRequest.class, pipeline::apply)
            .get();
}
~~~

`catalog.lookup(...)` runs when Spring constructs the flow bean, fetching the function once and reusing it for subsequent messages. `Objects.requireNonNull(...)` catches name typos early.

`transform(OrderRequest.class, pipeline::apply)` is a **Spring Integration transformer**. It extracts the **`OrderRequest` payload** from the message and produces an `OrderDecision` payload while the framework manages the message envelope and reply forwarding.

Calling it:

~~~java
OrderDecision result = gateway.classify(
        new OrderRequest(" dh-101 ", 1_500_000));

System.out.println(result);
// OrderDecision[id=DH-101, totalVnd=1500000, lane=PRIORITY]
~~~

### 7.3. How Does the Gateway Receive the Reply?

~~~mermaid
sequenceDiagram
    participant Caller
    participant Gateway
    participant Channel as orders.gatewayInput
    participant Transformer
    participant Catalog as FunctionCatalog
    Caller->>Gateway: classify(OrderRequest)
    Gateway->>Channel: Message<OrderRequest> + replyChannel header
    Channel->>Transformer: synchronous dispatch
    Transformer->>Catalog: pipeline.apply(request)
    Catalog-->>Transformer: OrderDecision
    Transformer-->>Gateway: Message<OrderDecision> on replyChannel
    Gateway-->>Caller: OrderDecision
~~~

The gateway sets up a **temporary reply channel** and attaches the reply destination in the `replyChannel` header. At the end of the request/reply flow, the transformer produces a result, so Spring Integration infrastructure routes the reply message back to that reply channel.

**Critical condition:** do not terminate a gateway flow with a side-effect-only `Consumer` that produces no reply if the gateway expects an `OrderDecision`. If the flow ends with a `handle(...)` returning `null` or with `accept(...)`, the caller receives no result and will block until timeout.

`Gateway` here is a **Spring Integration Messaging Gateway**. It differs from **Spring Cloud Gateway** (HTTP routing) and from an HTTP controller. To expose a REST API, add an HTTP adapter or controller that calls the gateway or the same function; `@MessagingGateway` alone does not create an HTTP endpoint.

## 8. The Poller Path: Supplier → function → channel → Consumer

Add the second method inside `OrderFlows`:

~~~java
@Bean
IntegrationFlow pollingOrderFlow(FunctionFlowBuilder builder) {
    return builder
            .fromSupplier(
                    "pendingOrderSource",
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(250)
                                    .maxMessagesPerPoll(1)))
            .apply("normalizeOrder|classifyOrder")
            .channel("orders.completed")
            .accept("captureDecision");
}
~~~

Here:

1. `fromSupplier("pendingOrderSource", ...)` uses `FunctionCatalog` to locate `Supplier<OrderRequest>` and wraps it into a Spring Integration polling source.
2. `Pollers.fixedDelay(250)` triggers the source with a 250 ms fixed delay.
3. `maxMessagesPerPoll(1)` limits each trigger to at most one message fetched from the source.
4. `apply("normalizeOrder|classifyOrder")` transforms `OrderRequest` into `OrderDecision` using the catalog composition name.
5. `channel("orders.completed")` sends the message onto the defined internal `DirectChannel`.
6. `accept("captureDecision")` ends the flow with `Consumer<OrderDecision>`, appending to `completedOrders`.

Quick trial (e.g., in a bean or test with both queues):

~~~java
pendingOrders.add(new OrderRequest(" dh-102 ", 500_000));

// After the poller triggers, completedOrders will contain:
// OrderDecision[id=DH-102, totalVnd=500000, lane=STANDARD]
~~~

**Timing note:** `add(...)` only inserts the item into the queue; it does not invoke the function immediately. The poller picks up the item on a subsequent trigger and sends it through the endpoints.

### 8.1. Why Doesn't the Polling Path Need a Gateway?

There is no specific caller waiting on an `OrderDecision`. The source emits messages proactively and the consumer is the end of the line. To expose results to users, the system can write to a database, publish an event, or provide a status-lookup API. This is an **asynchronous process** in terms of when data is emitted, even if the steps within a single poll cycle run synchronously on the poller thread.

### 8.2. From apply to transformer

The two snippets below share the same purpose, though lookup happens differently:

~~~java
// FunctionFlowBuilder (looks up composition by name)
.apply("normalizeOrder|classifyOrder")
~~~

~~~java
// Standard IntegrationFlow DSL (explicit lookup first)
Function<OrderRequest, OrderDecision> f =
        catalog.lookup("normalizeOrder|classifyOrder");

// Inside the pipeline:
.transform(OrderRequest.class, f::apply)
~~~

`FunctionFlowBuilder`'s `apply` is convenience DSL syntax integrated with the catalog, whereas `transform` is Spring Integration's standard EIP Transformer. `apply` still carries the semantics of transforming with a function; both require input and output types to honor the contract.

## 9. Poller: Cadence, Fetch Limits, and Stopping Conditions

### 9.1. Fixed Delay and maxMessagesPerPoll

| Configuration | Meaning |
| --- | --- |
| `Pollers.fixedDelay(250)` | Polls with a fixed delay between triggers; actual timing depends on the scheduler and processing duration. |
| `Pollers.fixedRate(250)` | Schedules on a fixed-rate cadence; does not automatically guarantee completion within 250 ms or prevent overlap. |
| `maxMessagesPerPoll(1)` | At most one message is fetched from the source per trigger. |
| `maxMessagesPerPoll(5)` | Up to five messages may be fetched in a single trigger if the source has enough items and downstream steps permit. |

In Spring Integration, `SourcePollingChannelAdapter` commonly defaults to `maxMessagesPerPoll = 1`, whereas `PollingConsumer` has a different default because it reads from a pollable channel. Setting the value explicitly makes execution policy clear and avoids relying on implicit defaults.

### 9.2. Supplier Returning null

With `pendingOrders::poll`, an empty queue returns `null`. In a polling message source, that generally means **no new message** in this poll cycle. It does not mean the framework sends a `Message` with a `null` payload, because Spring Messaging does not accept a `null` payload as normal message data.

The poller can simply trigger again on the next cycle and retry.

### 9.3. Source Item Consumed Before Processing Fails

~~~text
pendingOrders.poll()
     ↓ pops item from queue
normalizeOrder / classifyOrder
     ↓
captureDecision
     ↓
if error: item does NOT automatically return to pendingOrders
~~~

This is crucial: the demo uses an in-RAM queue and therefore **has no transactional acknowledgement or durable delivery**. When downstream fails, you need a proper recovery mechanism, such as:

- Persisting pending/processing state in a database within a transaction.
- Using a broker and adapter with acknowledgements, redelivery, or dead-letter support.
- Maintaining an error store or idempotency key for failures and duplicate deliveries.
- Designing bounded retries for transient failures; invalid business data usually cannot be fixed by infinite retries.

A poller does not turn a `Supplier` into an exactly-once system.

## 10. Channels: DirectChannel, QueueChannel, and ExecutorChannel

This lesson uses `DirectChannel` for both demo channels to keep things clear. In real systems, channel choice changes execution behavior.

| Channel Type | Characteristics | Impact When Wiring Functions |
| --- | --- | --- |
| `DirectChannel` | Dispatches directly to a subscriber, typically on the same thread. | Downstream errors can propagate back to the caller/poller; fits synchronous request/reply. |
| `QueueChannel` | Buffers messages in a channel queue; consumers must actively poll. | Introduces buffering and a time boundary; reading endpoints usually need a poller. |
| `ExecutorChannel` | Hands messages off to an executor for asynchronous processing. | Caller may not wait for business completion; requires managing executors, errors, ordering, and timeouts. |
| `PublishSubscribeChannel` | Broadcasts messages to multiple subscribers per policy. | Fits fan-out, but does not guarantee all branches succeed or produce a single unified reply. |

### 10.1. What Must Change When Switching to QueueChannel?

Merely changing:

~~~java
@Bean("orders.completed")
MessageChannel completedChannel() {
    return new QueueChannel(100);
}
~~~

is not sufficient in all configurations: `QueueChannel` is a **PollableChannel**, so the downstream endpoint reading from it generally needs a **poller**. Depending on the DSL used, you may need a default poller or an endpoint-specific poller. Switching channel types can also alter transaction boundaries and when errors surface.

This snippet illustrates an architectural change, not a drop-in runnable replacement without adding a poller. Import `org.springframework.integration.channel.QueueChannel` when using it.

### 10.2. Why Not Switch gatewayInput to ExecutorChannel Arbitrarily?

The gateway expects a reply within a bounded timeout. Switching to `ExecutorChannel` makes dispatching to another thread possible, but you must manage timeouts, exception propagation, context, cancellation, and reply correlation. For a simple request/reply demo, `DirectChannel` is the straightforward choice.

### 10.3. Channel Selection Guide by Need

- **Synchronous, fast processing, immediate result needed:** start with `DirectChannel`.
- **Need to absorb traffic bursts:** consider `QueueChannel` with a poller, bounded capacity, and backpressure policies.
- **Need to offload work to an executor:** use `ExecutorChannel` once concurrency, ordering, and error handling are designed.
- **Need to broadcast to multiple branches:** use `PublishSubscribeChannel` or an EIP Recipient List/Router matching the contract.

## 11. How Does a Transformer Differ from a Router, Filter, and Gateway?

All of these endpoints can appear in the same `IntegrationFlow`, yet their responsibilities differ.

~~~text
Gateway method
    ↓ request message
Message Channel
    ↓
Transformer: OrderRequest → OrderDecision
    ↓
Filter: keep or drop
    ↓
Router: route by lane
    ↓
Handler/Consumer: perform side effect
~~~

- **Transformer** computes a new output value. In the demo, `normalizeOrder|classifyOrder` returns `OrderDecision`.
- **Filter** keeps or drops messages based on a predicate. Throwing `IllegalArgumentException` on validation failure is not equivalent to an EIP Filter.
- **Router** uses a value such as `lane` to choose a target channel, e.g., `orders.priority` or `orders.standard`.
- **Gateway** translates a Java method call into message exchange and can return a result to the caller.

A routing variant using EIP:

~~~java
// Illustrates replacing the existing gateway or poller flow;
// channels and handlers must be defined for both branches.
return IntegrationFlow.from("orders.routeInput")
        .transform(OrderRequest.class, pipeline::apply)
        .route(OrderDecision.class, OrderDecision::lane,
                spec -> spec
                        .channelMapping("PRIORITY", "orders.priority")
                        .channelMapping("STANDARD", "orders.standard"))
        .get();
~~~

This snippet only illustrates a *Router*; it does not automatically create `orders.routeInput` or the target channels. Do not attach it to the same source as a gateway expecting a reply without defining which branch sends the response.

## 12. Message Headers, replyChannel, and Type Conversion

### 12.1. Messages Carry Both Payload and Headers

~~~text
Message<OrderRequest>
  payload: OrderRequest("DH-101", 1500000)
  headers:
    id: ...
    timestamp: ...
    replyChannel: ...   (if set by gateway)
    traceId: ...        (if provided by application)
~~~

`Function<OrderRequest,OrderDecision>` only needs the payload, keeping it easy to reuse. Spring Integration handles message wrapping and transport. The gateway uses the `replyChannel` header to know where to send the response.

If a function genuinely needs metadata, declare:

~~~java
@Bean
Function<Message<OrderRequest>, Message<OrderRequest>> tagOrder() {
    return incoming -> MessageBuilder.fromMessage(incoming)
            .setHeader("processingStage", "NORMALIZED")
            .build();
}
~~~

Import `org.springframework.messaging.Message` and `org.springframework.messaging.support.MessageBuilder`. When wiring through wrappers or call sites, choose the overload that passes the **whole message**, and test critical headers rather than assuming every API behaves identically.

### 12.2. Converting Payloads from HTTP or Brokers

The demo gateway receives an `OrderRequest` object directly, so no JSON parsing is needed. If the source is HTTP or a broker, the payload may be a JSON string or byte array. In that case:

~~~text
JSON bytes
   → converter/deserializer
   → OrderRequest
   → normalizeOrder|classifyOrder
   → OrderDecision
   → serializer/adapter or gateway reply
~~~

`FunctionCatalog` supports wrappers and conversion, yet **that does not mean any byte array turns into any POJO automatically**. Content types, generic signatures, converters, and adapter settings must align. Unit tests using POJOs do not prove HTTP/broker binding configuration is correct.

### 12.3. Headers Can Change Across Boundaries

Passing through a transformer generally preserves appropriate headers in Spring Integration, while headers related to acknowledgements, partitions, message IDs, or correlation may be handled specially by adapters/wrappers. For request/reply, watch `replyChannel`; for tracing, test propagation across every step.

## 13. A Gateway Is Not an HTTP API

There are four invocation views:

| Invocation Style | Interface for Caller | Connectivity Component | Can Share the Same Functions? |
| --- | --- | --- | --- |
| **Messaging Gateway** | `OrderDecision classify(OrderRequest)` | Spring Integration proxy + request channel + reply channel. | Yes |
| **HTTP REST** | `POST /orders/classify` | Spring MVC/WebFlux controller or SCF Web adapter. | Yes |
| **Event / message broker** | Messages arriving from a destination/topic/queue. | Spring Cloud Stream binder or Spring Integration inbound adapter. | Yes |
| **Serverless** | Function invoked by the platform via events. | Runtime-appropriate adapter. | Yes |

To expose the demo gateway over HTTP, you could add a controller:

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderGateway gateway;

    OrderController(OrderGateway gateway) {
        this.gateway = gateway;
    }

    @PostMapping("/classify")
    OrderDecision classify(@RequestBody OrderRequest request) {
        return gateway.classify(request);
    }
}
~~~

This example is **optional**; it requires `spring-boot-starter-web`, Spring MVC imports, and proper mapping of exceptions to HTTP statuses, timeouts, validation, and authentication. The controller does not alter `normalizeOrder` or `classifyOrder`.

You can also skip the gateway and let an HTTP adapter invoke the catalog function directly. Depending on operational needs, a gateway layer is valuable when the application wants to invoke a flow involving multiple EIPs such as request/reply, channels, transforms, and routing.

## 14. Testing Across Each Boundary

### 14.1. Unit Testing Functions

Call the functions directly, without Spring:

~~~java
OrderFunctions functions = new OrderFunctions();

OrderRequest normalized = functions.normalizeOrder()
        .apply(new OrderRequest(" dh-101 ", 1_500_000));

OrderDecision decision = functions.classifyOrder()
        .apply(normalized);

assertEquals("DH-101", decision.id());
assertEquals("PRIORITY", decision.lane());
~~~

Also test totals equal to `1_000_000` (still `PRIORITY`), below the threshold (`STANDARD`), and blank IDs or invalid totals (rejected).

### 14.2. Testing the Catalog and Composition

In a Spring test context:

~~~java
@Autowired
FunctionCatalog catalog;

@Test
void compositionShouldBeRegistered() {
    Function<OrderRequest, OrderDecision> pipeline =
            catalog.lookup("normalizeOrder|classifyOrder");

    assertNotNull(pipeline);
    OrderDecision result = pipeline.apply(
            new OrderRequest(" dh-102 ", 500_000));
    assertEquals("STANDARD", result.lane());
}
~~~

This verifies **function names**, signatures, and composition; it does not yet verify channels, pollers, or the gateway.

### 14.3. Integration Testing the Gateway

~~~java
package example.orders;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(classes = OrderApplication.class)
class OrderGatewayTest {

    @Autowired
    OrderGateway gateway;

    @Test
    void gatewayShouldReturnClassifiedOrder() {
        OrderDecision decision = gateway.classify(
                new OrderRequest(" dh-101 ", 1_500_000));

        assertEquals("DH-101", decision.id());
        assertEquals("PRIORITY", decision.lane());
    }
}
~~~

With `DirectChannel` and a synchronous transformer, the gateway returns the result right inside the method call. If a flow produces no reply, the test needs a finite timeout to catch the gateway blocking until timeout.

### 14.4. Integration Testing Polling

~~~java
package example.orders;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(classes = OrderApplication.class)
class OrderPollingTest {

    @Autowired
    @Qualifier("pendingOrders")
    BlockingQueue<OrderRequest> pendingOrders;

    @Autowired
    @Qualifier("completedOrders")
    BlockingQueue<OrderDecision> completedOrders;

    @Test
    void pollerShouldProcessPendingOrder() throws InterruptedException {
        pendingOrders.clear();
        completedOrders.clear();

        pendingOrders.add(new OrderRequest(" dh-102 ", 500_000));

        OrderDecision result = completedOrders.poll(
                3, TimeUnit.SECONDS);

        assertNotNull(result, "Poller did not emit a result before timeout");
        assertEquals("DH-102", result.id());
        assertEquals("STANDARD", result.lane());
    }
}
~~~

**Why is `poll(timeout)` needed?** Because the poller fires on a schedule, asynchronously from the test's `pendingOrders.add(...)` call. Calling an un-timed `completedOrders.poll()` right after `add(...)` could miss the result even when the flow works properly.

The queues in the demo are shared beans; when running multiple tests against the same context concurrently, isolate state so one test's data does not bleed into another. When replacing queues with a DB/broker, test idempotency, retries, redelivery, and recovery against the real mechanism.

## 15. Error Handling and Operational Decisions

| Scenario | Gateway Path | Poller Path |
| --- | --- | --- |
| Blank order ID / invalid total | Transformer throws; in a synchronous flow without a dedicated error channel, the error usually propagates to the caller. | Poller/handler processes the exception via its error handler; decide whether to drop, record, or retry. |
| `normalizeOrder|classifyOrder` not found | Likely fails when building `IntegrationFlow` due to explicit lookup. | DSL looks up function names during flow construction/startup; inspect catalog beans. |
| Slow function processing | Caller waits, risking timeout. | Poll cycle slows down or backlog grows. |
| Consumer DB write fails | If inside request/reply, decide whether reply is sent before or after commit. | Item already popped from source risks being lost; ack/recovery and idempotency are needed. |
| Duplicate messages | Caller retries may cause repeated side effects. | Retry/redelivery or a source returning the same item can cause duplicate execution. |
| Broker adapter disconnected | Not applicable to internal channels unless wired to a broker. | Binder/inbound adapter must handle delivery, ack, and reconnection. |

### 15.1. Where Do ErrorChannel and Retries Live?

Spring Integration offers error channels, retry advice, transaction support, and error-handling configuration on pollers and adapters. Which mechanism fires depends on whether the endpoint is **synchronous or asynchronous**:

- With `DirectChannel`, transformer exceptions can propagate back to the sender.
- With a polling endpoint, exceptions can flow through the scheduler/poller's error handler.
- With an executor or broker, errors can occur on another thread, requiring an error channel or adapter-specific policy.
- Simply declaring a bean named `errorChannel` does not mean every error routes there uniformly.

In practice, distinguish **business data errors** from **transient infrastructure errors**. Bad data should usually fail fast or route to an intentional error branch; network errors can use bounded retry with backoff.

### 15.2. Consistency and Idempotency

`FunctionCatalog` only packages and looks up logic; `IntegrationFlow` does not automatically provide distributed transactions. Specifically on the polling path, `pendingOrders.poll()` removes the item from the queue before the consumer completes. To prevent data loss on process crash, use a durable source paired with an ack/transaction/compensation strategy.

If a consumer performs side effects such as sending emails or writing records, use a business key to guard against duplicate execution, especially under retries or redelivery.

## 16. Common Pitfalls

| Symptom | Causes to Investigate |
| --- | --- |
| `NoSuchBeanDefinitionException` for `OrderGateway` | Missing `@IntegrationComponentScan`, gateway outside scanned packages, or Spring Integration not configured. |
| Cannot inject `FunctionFlowBuilder` | Missing `spring-cloud-function-integration`, or incompatible version/auto-configuration. |
| `FunctionCatalog.lookup(...)` finds no function | Wrong bean name, configuration not scanned, or invalid composition/types. |
| Gateway call returns no reply | Flow ends in a non-replying consumer, reply channel was lost, or result did not arrive before timeout. |
| Gateway times out after changing channel | An async boundary was introduced, or a downstream endpoint is unresponsive or stalled. |
| Poller sees no items | Supplier returns `null`, writing to a different queue than the test, endpoint not started, or misconfigured poller schedule. |
| Poller repeatedly processes the same value | Supplier always returns the same value or fails to advance a cursor; review the source contract. |
| `ClassCastException` during transform | Payload is not `OrderRequest`, or converter/input binding is mismatched. |
| `QueueChannel` has data but downstream never runs | Missing poller configuration on the consumer reading from the pollable channel. |
| Results written twice | Duplicate event source, retry/redelivery, or multiple flows/bindings consuming the same input. |
| Data lost when consumer fails | Source queue removed the item without an ack/recovery mechanism. |

### Self-Check Questions

1. Why can `Gateway.classify(...)` return data synchronously while `fromSupplier(...)` usually has no waiting caller?
2. What is the relationship between `transform(OrderRequest.class, pipeline::apply)` and `apply("normalizeOrder|classifyOrder")`?
3. Why is `DirectChannel` often better suited to a simple request/reply gateway example than `QueueChannel`?
4. Why does switching from `DirectChannel` to `QueueChannel` usually require adding a poller on the receiving endpoint?
5. How do you verify that a message finished processing rather than merely being accepted by a channel?
6. If `pendingOrders.poll()` pops an item and the consumer later fails, what architectural change provides recoverability?
7. Why does adding `@MessagingGateway` not create an HTTP endpoint?
8. When adding a broker adapter, what extra aspects of serialization, acknowledgement, and idempotency must be tested?

## 17. Extension Exercises

1. **Add a Message Filter:** Drop orders whose normalized ID starts with `TEST-`. Compare filtering messages against throwing an exception from a function.
2. **Add a Content-Based Router:** Route results by `lane` to `orders.priority` or `orders.standard`, each with its own consumer.
3. **Switch to QueueChannel:** Change `orders.completed` to `QueueChannel(100)`, configure a polling consumer, and verify messages still reach the consumer.
4. **Add a Gateway Header:** Add a `@Header("traceId")` parameter to the gateway method and use a wire tap to inspect the header on the message after the transformer.
5. **Simulate Failures:** Have the consumer throw exceptions intermittently, experiment with bounded retry/backoff strategies, and record items needing redrive.
6. **Expose via HTTP:** Write a `@RestController` calling `OrderGateway` or calling the function directly, and clearly define success, validation error, and timeout responses.

## 18. Official References

- [Spring Cloud Function – Spring Integration Interaction](https://docs.spring.io/spring-cloud-function/reference/spring-integration.html): `spring-cloud-function-integration`, `FunctionFlowBuilder`, `fromSupplier`, `apply`, and `accept`.
- [Spring Cloud Function – Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): `Supplier`, `Function`, `Consumer`, `FunctionCatalog`, and composition.
- [Spring Integration – DSL Basics](https://docs.spring.io/spring-integration/reference/dsl/java-basics.html): `transform`, `filter`, `handle`, `route` endpoints, and message flows.
- [Spring Integration – Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): gateway proxies, request/reply, temporary reply channels, annotations, and timeouts.
- [Spring Integration – Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): channel types and synchronous/asynchronous traits.
- [Spring Integration – Channel Adapter](https://docs.spring.io/spring-integration/reference/channel-adapter.html): polling inbound adapters, `maxMessagesPerPoll`, and operational traits.
- [Spring Integration – Message Endpoints](https://docs.spring.io/spring-integration/reference/endpoint.html): configuring pollers, default pollers, and transactions.

**Conclusion:** `FunctionCatalog` supplies reusable business transformations; Spring Integration places them along message paths using **channels**, **pollers**, **transformers**, and **gateways**. With the same `normalizeOrder|classifyOrder` composition, a gateway provides request/reply for callers while a supplier is polled periodically to push results to a consumer. Clear boundary design lets the same functions serve HTTP, events, or serverless while keeping delivery, scheduling, and error handling in the proper integration layer.
