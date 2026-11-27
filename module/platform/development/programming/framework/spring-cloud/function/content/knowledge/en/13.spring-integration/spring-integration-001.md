# Relationship Between the Function Model and Enterprise Integration Patterns

## 1. Context and Goals

**Spring Cloud Function (SCF)** allows you to express business logic using three familiar Java interfaces:

- **`Supplier<T>`**: produces data and takes no input parameters; typically serves as an event source.
- **`Function<T, R>`**: accepts `T` and returns `R`; suited for transformation, normalization, calculation, and classification.
- **`Consumer<T>`**: accepts `T` and performs a side effect without returning a result; typically serves as a processing endpoint.

SCF manages functions through **`FunctionCatalog`**, supports **composition** (chaining functions), and allows the same logic to be reused behind different adapters such as HTTP, message brokers, or serverless platforms. The goal is to keep business logic independent of the invocation protocol.

**Enterprise Integration Patterns (EIP)** are a set of design patterns for connecting systems via messages: *Message Channel*, *Message Translator*, *Content-Based Router*, *Message Filter*, *Splitter*, *Aggregator*, *Publish-Subscribe Channel*, *Service Activator*, *Error Channel*, and more. **Spring Integration** implements many EIPs within the Spring ecosystem.

The two approaches complement each other:

> **Functions** answer the question "How should this data be processed?"; **EIP** answers the question "Where do messages come from, which path do they take, how are they split or aggregated, and how are errors handled?".

By the end of this lesson, you will be able to distinguish the roles of SCF and Spring Integration, map function types to relevant EIP patterns, design a routed integration flow, and identify where additional orchestration infrastructure is needed.

## 2. Two Layers of Responsibility in the Same System

An order processing system might receive events from HTTP, Kafka, or an internal system. Regardless of the source, the rule "orders over one million VND are priority" should still live in an independent function.

~~~mermaid
flowchart LR
    A["HTTP / broker / scheduler"] --> B["Inbound adapter"]
    B --> C["Message Channel"]
    C --> D["FunctionCatalog<br/>validateOrder | classifyOrder"]
    D --> E{"Content-Based Router"}
    E -->|PRIORITY| F["Priority channel"]
    E -->|STANDARD| G["Standard channel"]
    F --> H["Consumer / outbound adapter"]
    G --> I["Consumer / outbound adapter"]
    C -. endpoint error .-> J["Error flow / retry / DLQ"]
    D -. function invocation error .-> J
~~~

There are three layers to distinguish:

1. **Business functions:** `validateOrder`, `classifyOrder`, `calculatePrice`, etc., defined using `Function`; the logic should be testable solely via input and output values.
2. **Message orchestration:** channels, filters, routers, splitters, aggregators, error flows, etc., implemented using Spring Integration or equivalent integration components.
3. **Environment connectivity:** inbound/outbound adapters, HTTP endpoints, Spring Cloud Stream binders, or serverless adapters that bring data in and out. SCF provides a general function model, but it does not automatically create full EIP components simply because a `Function` bean exists.

**Note:** Spring Cloud Function can run standalone; Spring Integration is not mandatory. When only a synchronous transformation chain is needed, composition may suffice. When channels, multiple branches, fan-out, message correlation, or infrastructure-level error handling are required, EIP becomes necessary.

## 3. Mapping the Function Model to Enterprise Integration Patterns

| Enterprise Integration Pattern | Relationship to the Function Model | What Must Be Added in Production |
| --- | --- | --- |
| **Message Endpoint / Service Activator** | `Consumer<T>` can act as a receiver that processes a payload; `Function<T,R>` can process and produce a reply. | The adapter/endpoint decides how messages are received, acknowledged, and replied to. |
| **Message Translator / Content Enricher** | `Function<T,R>` naturally expresses structural conversion or data enrichment. | Payload transformation differs from handling metadata/headers and format conversion at communication boundaries. |
| **Pipes and Filters** | Composing `f | g` passes the output of `f` as the input to `g`. | Composition is a function-call chain; the "pipes" here are not inherently independent or asynchronous message channels. |
| **Message Filter** | A `Predicate<T>` or validation logic inside a function describes the keep/drop condition. | An actual filter endpoint is needed to decide whether to drop, send to a discard channel, or raise an error. Throwing an exception on invalid data is not equivalent to an EIP Filter. |
| **Content-Based Router** | `Function<T, RouteDecision>` computes a routing key based on content. | The router reads the key and selects the target channel; a function computing the key does not dispatch messages to channels on its own. |
| **Splitter** | A function can turn one object into a `List<R>` or `Flux<R>`. | An EIP Splitter emits separate messages and typically must manage sequence/correlation headers and downstream flows. |
| **Aggregator** | A function can aggregate an already-assembled list. | An EIP Aggregator must maintain state, determine correlation groups, completion conditions, and timeouts for messages arriving at different times. |
| **Publish-Subscribe Channel / Recipient List** | Multiple `Consumer<T>` beans can share the same input data type. | The channel/broker must handle fan-out and delivery policies; simply registering multiple consumers does not create publish-subscribe behavior. |
| **Wire Tap** | Tracing logic can be added at boundaries. | Use a wire tap/audit flow to observe messages without mixing side effects into calculation functions. |
| **Error Channel / Dead Letter Channel** | A function can throw an exception or return an error result according to a business contract. | Retry, backoff, DLQ, compensation, and channel/binder-level error handling belong to the integration layer. |

This mapping represents a **correlation of responsibilities**, not a one-to-one equivalence between a Java type and an EIP pattern. For example, `Function<Order, Boolean>` only returns true/false; implementing a *Message Filter* requires a component that uses that result to retain or discard the message.

## 4. Composition and FunctionCatalog: How Much Resembles Pipes and Filters?

Suppose we have:

~~~java
Function<A, B> first = ...;
Function<B, C> second = ...;
Function<A, C> pipeline = first.andThen(second);
~~~

SCF composition elevates this same idea to bean names, such as `validateOrder|classifyOrder`. `FunctionCatalog` supports looking up registered functions and composed function chains by name.

Conceptually, common orderings include:

- `Supplier<A> → Function<A,B>`: a source produces data, followed by a transformation.
- `Function<A,B> → Function<B,C>`: a chain of transformations.
- `Function<A,B> → Consumer<B>`: transform and then perform a terminal action.

The output type of each step must be compatible with the input type of the next step. In a standard synchronous chain, a single call flows through all functions within the same execution pass; **no broker, durable queue, retry mechanism, or transaction automatically appears between them**. Imperative/reactive combinations must also follow how SCF handles those function signatures.

**Distinction:**

- Composition solves **the execution order of transformations**.
- EIP *Pipes and Filters* can connect processors into a flow, while the **Message Channel** between steps can also handle transport, thread handoff, asynchrony, or error boundaries.
- `FunctionCatalog` manages and looks up function definitions; it does not act as a router or a message store.

## 5. Example: Reusing Business Functions in an EIP Flow

### 5.1. Problem Statement

A store receives orders with two fields, `id` and `total` (in VND):

~~~json
{"id":"DH-101","total":1250000}
~~~

Requirements:

1. Verify that the order has a valid ID and a total amount greater than 0.
2. Classify as `PRIORITY` if `total >= 1000000`, otherwise `STANDARD`.
3. Send the decision to the corresponding processing channel.

We place steps 1–2 into independent functions and step 3 into an EIP Content-Based Router.

### 5.2. Defining Channel-Independent Functions

The example uses Java 17+, Spring Boot 3+, and Spring Cloud Function. The records are in the same package as the configuration class.

~~~java
package example.orders;

import java.math.BigDecimal;
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record Order(String id, BigDecimal total) {}
record CheckedOrder(String id, BigDecimal total) {}
record ShippingDecision(String id, String tier) {}

@Configuration
class OrderFunctions {

    @Bean
    Function<Order, CheckedOrder> validateOrder() {
        return order -> {
            if (order == null
                    || order.id() == null
                    || order.id().isBlank()
                    || order.total() == null
                    || order.total().signum() <= 0) {
                throw new IllegalArgumentException("Invalid order");
            }
            return new CheckedOrder(order.id(), order.total());
        };
    }

    @Bean
    Function<CheckedOrder, ShippingDecision> classifyOrder() {
        return order -> {
            String tier = order.total()
                    .compareTo(new BigDecimal("1000000")) >= 0
                    ? "PRIORITY" : "STANDARD";
            return new ShippingDecision(order.id(), tier);
        };
    }
}
~~~

These are **business transformations**: they do not know whether an order came from HTTP or a queue, nor do they know where the target channels are located. `validateOrder` applies *validation* rules by throwing an exception, which is not yet an EIP Message Filter.

When `FunctionCatalog` is present in the Spring context, the same pipeline can be retrieved:

~~~java
Function<Order, ShippingDecision> pipeline =
        catalog.lookup("validateOrder|classifyOrder");

ShippingDecision result =
        pipeline.apply(new Order("DH-101", new BigDecimal("1250000")));
// result: ShippingDecision[id=DH-101, tier=PRIORITY]
~~~

If you want an SCF HTTP adapter or binder to select this pipeline as the function definition, you can configure:

~~~properties
spring.cloud.function.definition=validateOrder|classifyOrder
~~~

That property selects the function definition used by supported adapters; **it does not automatically create the `orders.priority` or `orders.standard` channels**.

### 5.3. Using Spring Integration to Route Based on Function Results

Below is an illustrative flow configuration using the Spring Integration Java DSL. It reuses the exact pipeline from `FunctionCatalog`, while the channels and two handlers are defined separately in the integration layer.

~~~java
package example.orders;

import java.util.function.Function;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
class OrderFlow {

    @Bean("orders.input")
    MessageChannel orderInput() {
        return new DirectChannel();
    }

    @Bean("orders.priority")
    MessageChannel priorityChannel() {
        return new DirectChannel();
    }

    @Bean("orders.standard")
    MessageChannel standardChannel() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow orderRouting(FunctionCatalog catalog) {
        Function<Order, ShippingDecision> pipeline =
                catalog.lookup("validateOrder|classifyOrder");

        return IntegrationFlow.from("orders.input")
                .transform((Order order) -> pipeline.apply(order))
                .route("payload.tier()", r -> r
                        .channelMapping("PRIORITY", "orders.priority")
                        .channelMapping("STANDARD", "orders.standard"))
                .get();
    }

    @Bean
    IntegrationFlow priorityHandler() {
        return IntegrationFlow.from("orders.priority")
                .handle(message ->
                        System.out.println("Priority: " + message.getPayload()))
                .get();
    }

    @Bean
    IntegrationFlow standardHandler() {
        return IntegrationFlow.from("orders.standard")
                .handle(message ->
                        System.out.println("Standard: " + message.getPayload()))
                .get();
    }
}
~~~

In this example:

- `orders.input` is the **Message Channel** receiving orders from a source wired into the flow.
- `transform(...)` invokes the **composition** `validateOrder|classifyOrder` like a *Message Translator*.
- `route(...)` is the **Content-Based Router**: it reads `tier` from the payload and sends the message to the appropriate channel.
- The two `handle(...)` blocks are sample **Service Activators**; in a real application, printing to stdout would be replaced by calling a business service or an outbound adapter.

`DirectChannel` runs on the caller's thread and does not persist messages. A request sent to `orders.input` can pass through the transformation, router, and handler before the send call completes. Switching to asynchronous processing or routing through a broker requires changing or adding corresponding channels, adapters, and configuration. The channel names in this example are internal bean names, not Kafka topic or RabbitMQ queue names.

Path of order `DH-101`:

~~~text
Order("DH-101", 1250000)
  → validateOrder  → CheckedOrder("DH-101", 1250000)
  → classifyOrder  → ShippingDecision("DH-101", "PRIORITY")
  → Content-Based Router
  → orders.priority
  → priorityHandler
~~~

You should not put the call to send directly to `orders.priority` inside `classifyOrder`. Doing so couples the classification function to a message channel and makes it harder to reuse when the same logic is exposed via HTTP or serverless.

### 5.4. One Logic, Many Ways to Invoke

| Deployment Approach | Component Handling Connectivity | Reused Logic |
| --- | --- | --- |
| **HTTP** | Spring Cloud Function Web adapter receives the request, converts the payload, and returns a response according to adapter capabilities. | `validateOrder|classifyOrder` |
| **Event/message broker** | Spring Cloud Stream binder connects the destination, performs binding, and processes according to broker semantics. | Same function definition or corresponding function |
| **Spring Integration flow** | Channels, transformers, routers, service activators, inbound/outbound adapters. | Invokes the pipeline via `FunctionCatalog` |
| **Serverless** | Adapter for the serverless environment translates platform events into function invocations. | Same business functions |

Each connectivity option has its own configuration, payload format, lifecycle, and error semantics. You cannot assume that a function exposed over HTTP automatically appears as a broker consumer, or vice versa.

## 6. Payload, Message, and Headers: Where the Function Model Meets EIP

EIP views a message as consisting of a **payload** and **headers** (metadata), for example:

~~~text
Message<Order>
  payload: {id: "DH-101", total: 1250000}
  headers: {traceId: "trace-7", contentType: "application/json", ...}
~~~

A function typed `Function<Order, ShippingDecision>` expresses only business data. When you need to make decisions based on metadata, preserve a trace ID, or assign routing headers, you can use `Function<Message<T>, Message<R>>`:

~~~java
@Bean
Function<Message<Order>, Message<Order>> markReceived() {
    return incoming -> MessageBuilder.fromMessage(incoming)
            .setHeader("processingStage", "received")
            .build();
}
~~~

In this example, `MessageBuilder.fromMessage(...)` creates a new message from the incoming message and updates its headers. You need to import `org.springframework.messaging.Message` and `org.springframework.messaging.support.MessageBuilder`.

Some key principles:

- Use **plain payloads** when the function does not need to care about transport; use **Message** when metadata is an intentional part of the contract.
- Application headers such as `traceId` or `correlationId` must be propagated and inspected wherever needed. System/broker headers such as acknowledgement, delivery attempt, or routing keys have their own rules; do not assume they are preserved unchanged across every adapter.
- Conversion between JSON, Java objects, and `Message<?>` depends on the function signature as well as the active adapter/converter. Define clear contracts and test at HTTP/broker boundaries.
- Headers can help a router decide the path; however, **reading a header for computation** is still distinct from **performing routing to a channel**.

## 7. Why Splitter and Aggregator Cannot Be Replaced by Function Alone

Suppose an order has ten line items. There are two different scenarios:

**Case A — data is already in memory.** A `Function<Order, List<OrderLine>>` returns a list of ten elements. This is just a value transformation. If another function afterward takes the entire `List<OrderLine>` and computes a total, a simple pipeline may be sufficient.

**Case B — the ten lines must be processed independently.** An EIP *Splitter* emits ten **messages**, each of which may go through a different worker. Results arrive out of order or several seconds apart; an *Aggregator* needs to know which order they belong to, when all ten results have arrived, and how to handle a failed line.

~~~mermaid
flowchart LR
    A["Order with 10 lines"] --> S["Splitter"]
    S --> P["Process line 1"]
    S --> Q["Process lines 2...9"]
    S --> R["Process line 10"]
    P --> G["Aggregator<br/>correlation + release condition"]
    Q --> G
    R --> G
    G --> X["OrderSummary"]
~~~

In Case B, aspects such as **correlation key**, **sequence size/number**, **message store**, **timeout**, **release strategy**, and handling incomplete results are EIP orchestration responsibilities. Returning `List<?>`, `Stream<?>`, or `Flux<?>` in a function signature **does not automatically provide** those guarantees. With reactive streams, you also need to pay attention to backpressure, subscription, and where the stream terminates.

## 8. Errors, Retries, Ordering, and Consistency

When placing a function into an integration flow, error policies must be positioned at the **right layer**:

| Scenario | Appropriate Handling Layer | Reason |
| --- | --- | --- |
| Order has `total <= 0` | Validation function returns a business error result or throws a classified exception. | Retrying the exact same data rarely makes an invalid order valid. |
| Partner API hits a transient network error | Adapter/handler combined with retry and backoff. | Recoverable upon retry. |
| Processing fails repeatedly | Error flow, DLQ, or dead-letter event store appropriate for the broker. | Enables observability, classification, and controlled reprocessing. |
| Duplicate event after redelivery | Idempotent consumer/handler, controlled via a business key. | *At-least-once* delivery can deliver the same event multiple times. |
| Multiple results return out of order | Aggregator/correlation or a dedicated ordering mechanism. | Ordering within a single function does not guarantee ordering in a distributed system. |
| Transactions needed across multiple systems | Design transactions/compensation at the integration processing layer. | Composition does not automatically provide distributed transactions. |

An exception thrown from a `Function` follows the **caller's** error-handling mechanism. In a synchronous Spring Integration flow, it may propagate back to the sender; in a binder, retry or DLQ behavior can depend on destination configuration, exception type, and consumption mode. Therefore, do not write documentation or code assuming that "SCF automatically retries three times" across all environments.

To keep functions easy to reuse, limit side effects within pure computation logic. Sending emails, writing to databases, publishing events, or calling external APIs generally belong in a `Consumer`/handler or a service layer invoked at the end of the flow, paired with appropriate idempotency and error policies.

## 9. How to Test at the Right Boundaries

Testing can be divided into three levels:

1. **Unit testing business functions:** call `validateOrder().apply(...)` and `classifyOrder().apply(...)` directly to verify valid orders, invalid orders, the exact one-million threshold, and the output `tier`. Neither a broker nor Spring Integration is needed.
2. **Testing composition/catalog:** boot the Spring context, look up `catalog.lookup("validateOrder|classifyOrder")`, and verify input/output values, data types, and required message conversions.
3. **Integration testing flows/adapters:** send `Message<Order>` into `orders.input`, verify that only the matching branch receives the message, important headers remain intact, and error cases follow the designed error path. When using a real broker, also test acknowledgement, retry, redelivery, ordering, and DLQ behavior against the actual infrastructure.

Example unit test without a Spring context:

~~~java
OrderFunctions functions = new OrderFunctions();

CheckedOrder checked = functions.validateOrder().apply(
        new Order("DH-101", new BigDecimal("1250000")));

ShippingDecision decision =
        functions.classifyOrder().apply(checked);

assertEquals("PRIORITY", decision.tier()); // JUnit 5
~~~

You should also include cases for `total = 1000000` (still `PRIORITY`), `total = 999999` (`STANDARD`), and `total <= 0` (rejected). These cases verify business rules independently of orchestration.

## 10. Design Principles and Common Pitfalls

- **Keep business decisions in functions and transport in flows.** Functions return `ShippingDecision`; routers decide which channel to send to.
- **Use composition for linear transformation chains.** When there are multiple branches, stateful grouping, or fan-out, consider the appropriate EIP pattern.
- **Separate validation from filtering.** Validation may reject an order due to an error; filtering is an orchestration behavior that keeps or drops messages based on a condition.
- **Distinguish a collection from multiple messages.** An in-memory `List<T>` is not a correlated group of messages with timeouts.
- **Do not equate FunctionCatalog with a message broker.** The catalog is for registering, looking up, and composing functions; brokers and adapters handle message delivery.
- **Design idempotency, retries, and observability at boundaries with side effects.** Keep computation pure, but do not ignore real-world delivery semantics.

**Conclusion:** Spring Cloud Function helps encapsulate and reuse logic with `Supplier`, `Function`, `Consumer`, and `FunctionCatalog`; Spring Integration provides EIP patterns to orchestrate messages across channels, routers, splitters, aggregators, and endpoints. When combined properly, a single business function can be invoked via HTTP, events, or serverless, while each environment preserves its own appropriate transport, routing, and error-handling mechanisms.
