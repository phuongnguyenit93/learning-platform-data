# Calling FunctionCatalog from IntegrationFlow

## 1. Problem Statement and Goals

**Spring Cloud Function (SCF)** expresses business logic with `Supplier<T>`, `Function<T, R>`, and `Consumer<T>`. Functions are registered and looked up through `FunctionCatalog`; you can **compose** multiple functions into a pipeline while keeping the logic independent of HTTP, event, or serverless invocation.

**Spring Integration** organizes message paths using `IntegrationFlow`: receiving messages from channels or adapters, transforming payloads, filtering, routing, splitting/aggregating, invoking services, and handling errors via **Enterprise Integration Patterns (EIP)**.

In an application using both frameworks, the question is: **How can an `IntegrationFlow` invoke functions already registered in `FunctionCatalog` instead of duplicating logic or coupling tightly to implementation beans?**

There are two main approaches:

1. **Explicit lookup:** inject `FunctionCatalog`, call `catalog.lookup("functionName")` or `catalog.lookup("f1|f2")`, and pass the returned function into `IntegrationFlow` endpoints.
2. **Dedicated DSL:** add the `spring-cloud-function-integration` module and use `FunctionFlowBuilder` with `apply("functionDefinition")`, `accept("consumerDefinition")`, or `fromSupplier("supplierDefinition")`.

This lesson focuses on the flow **from FunctionCatalog into IntegrationFlow**, its execution mechanics, and testing; the running example demonstrates approach 1 and then compares it with approach 2.

After this lesson, you should be able to explain the role of `lookup`, where to use `transform`, `handle`, and `route`, how to use composition, the impact of payloads/headers, lookup failure cases, and error semantics when the flow executes.

## 2. Role of Each Component in the Message Path

~~~mermaid
flowchart LR
    A["HTTP / broker / internal sender"] --> B["Inbound adapter / MessageChannel"]
    B --> C["IntegrationFlow"]
    D["Supplier / Function / Consumer beans"] --> E["FunctionCatalog"]
    E -. lookup or composition .-> F["Wrapped Function"]
    F --> C
    C --> G["Transformer / Filter / Router"]
    G --> H["Handler or outbound adapter"]
~~~

| Component | What It Does | What It Does Not Do Automatically |
| --- | --- | --- |
| `FunctionCatalog` | Looks up and composes functions by name; returns an SCF-wrapped function supporting features such as conversion and composition. | Does not send messages to a broker or create message channels. |
| `IntegrationFlow` | Builds a chain of message-processing endpoints using the Spring Integration DSL. | Does not automatically know which function to invoke unless configured. |
| `transform(...)` | Uses a transformer to produce a new output payload or message. | Does not decide which of multiple downstream channels receives a message. |
| `filter(...)` | Keeps or drops messages based on a condition. | Does not equate to business validation simply by sharing a predicate. |
| `route(...)` | Selects a target channel based on payload, headers, or a routing key. | Does not create business calculation rules inside the catalog. |
| `handle(...)` | Triggers terminal processing or a request/reply handler. | Does not automatically provide retries, transactions, or idempotency. |
| Adapter/binder | Connects HTTP, brokers, files, schedulers, serverless platforms, etc. to the flow. | Does not automatically expose every function over every protocol. |

**Key takeaway:** `FunctionCatalog` provides **data-processing capabilities**, while Spring Integration decides **where and when messages travel**. The same function can be called directly in code, behind an HTTP adapter, or inside an `IntegrationFlow`.

## 3. Minimum Requirements for Calling FunctionCatalog

### 3.1. Dependencies

A Spring Boot application typically needs compatible versions of:

- Spring Cloud Function context to provide `FunctionCatalog`, e.g., `org.springframework.cloud:spring-cloud-function-context`.
- Spring Integration DSL, typically pulled in via `org.springframework.boot:spring-boot-starter-integration`.
- Matching Spring Boot/Spring Cloud dependency management or BOM to avoid mixing incompatible versions.

Maven example (`dependencies` section of `pom.xml`):

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-function-context</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
</dependencies>
~~~

The snippet above assumes the project's `dependencyManagement` already selects compatible Spring Boot and Spring Cloud versions. If the project already includes a starter or adapter that brings these dependencies in, avoid redundant duplicate declarations.

**Explicit lookup via `catalog.lookup(...)` does not require adding `spring-cloud-function-integration`.** That module is for the `FunctionFlowBuilder` syntax covered later.

### 3.2. How Are Functions Registered?

Declare a bean of type `Supplier`, `Function`, or `Consumer` in the Spring context:

~~~java
@Bean
Function<String, String> normalizeCode() {
    return code -> code.strip().toUpperCase(Locale.ROOT);
}
~~~

SCF lets you retrieve it by bean name via `FunctionCatalog`:

~~~java
Function<String, String> normalizer =
        catalog.lookup("normalizeCode");

String result = normalizer.apply("  order-007  ");
// ORDER-007
~~~

The example requires importing `java.util.Locale` and `java.util.function.Function`. Ensure that SCF auto-configuration is enabled in the application and that the bean resides in a scanned Spring context.

**Difference from fetching the bean directly:**

~~~java
Function<String, String> rawBean =
        applicationContext.getBean("normalizeCode", Function.class);

Function<String, String> catalogFunction =
        catalog.lookup("normalizeCode");
~~~

`rawBean` is the exact bean registered by the application; `catalogFunction` is the function returned by the catalog, which SCF may **wrap** to support conversion, composition, and adapter features. The two objects can behave differently at message boundaries. When integrating with SCF, look up functions through the catalog using the exact function contract you intend to invoke.

## 4. Pattern for Calling Functions in the Spring Integration DSL

For `Function<T,R>`, the most natural mapping is a **transformer**:

~~~java
@Bean
IntegrationFlow processingFlow(FunctionCatalog catalog) {
    Function<String, String> normalize =
            Objects.requireNonNull(
                    catalog.lookup("normalizeCode"),
                    "Function normalizeCode not found");

    return IntegrationFlow.from("input")
            .transform(String.class, normalize::apply)
            .channel("output")
            .get();
}
~~~

Key imports: `java.util.Objects`, `java.util.function.Function`, `org.springframework.cloud.function.context.FunctionCatalog`, `org.springframework.integration.dsl.IntegrationFlow`, `org.springframework.context.annotation.Bean`.

In this flow:

1. `from("input")` receives messages from the `input` channel, configured elsewhere.
2. `transform(String.class, normalize::apply)` extracts the **String payload** and calls the catalog function. The return value becomes the payload for the next step.
3. `channel("output")` sends the resulting message to the `output` channel, configured or resolved by Spring Integration.

This `transform(...)` signature operates on the **payload**. You do not have to unwrap `message.getPayload()` inside your business function. `String.class` tells the DSL and invocation step which payload type to expect; it does not mean every arbitrary input type can automatically convert to `String`.

### 4.1. Why Choose transformer Instead of handle?

`transform(...)` fits a `Function<T,R>` whose result continues through the flow. `handle(...)` is typically used for a **Service Activator** or side-effecting handler; for a `Consumer<T>`, you can call `accept(...)` at the terminal step:

~~~java
@Bean
IntegrationFlow consumerFlow(FunctionCatalog catalog) {
    Consumer<String> audit =
            Objects.requireNonNull(
                    catalog.lookup("auditCode"),
                    "Consumer auditCode not found");

    return IntegrationFlow.from("audit.input")
            .handle(String.class, (payload, headers) -> {
                audit.accept(payload);
                return null;  // Do not send a reply
            })
            .get();
}
~~~

This example assumes an `auditCode` function of type `Consumer<String>` and an `audit.input` channel already exist. Returning `null` from a terminal handler means the handler produces no reply; if you want the chain to continue, use an endpoint with a clearly defined output.

### 4.2. When Should You Look Up the Catalog?

For a fixed function name in configuration, look it up **once when constructing the `IntegrationFlow` bean** and reuse that reference for incoming messages:

~~~java
Function<String, String> f = catalog.lookup("normalizeCode");

return IntegrationFlow.from("input")
        .transform(String.class, f::apply)
        .get();
~~~

This catches misconfigurations early and avoids repeating `lookup(...)` on every message. Use `Objects.requireNonNull(...)` or an equivalent check when the function name is required.

If business rules require selecting **different functions at runtime** per message, that is a different requirement: you need name-selection rules, an allowlist of callable functions, error handling, and type management. In many cases, use an EIP **Content-Based Router** to route to preconfigured flows rather than looking up arbitrary sender-supplied names.

## 5. Complete Example: Classifying Orders with Catalog Functions

### 5.1. Requirements

A system receives orders:

~~~json
{"id":" DH-042 ","totalVnd":1750000}
~~~

Rules:

1. Normalize the order ID by trimming leading/trailing whitespace and converting to uppercase.
2. Reject blank IDs or `totalVnd <= 0`.
3. Classify orders with `1_000_000` VND or more as `PRIORITY`, and the rest as `STANDARD`.
4. Spring Integration receives the message, invokes the composition of the two functions, and routes the result to one of two channels.

Here, validation/normalization/classification are **business logic**; the router and channels are **EIP**.

~~~mermaid
flowchart LR
    A["orders.input"] --> B["transform: catalog.lookup(normalizeOrder|classifyOrder)"]
    B --> C{"route by tier"}
    C -->|PRIORITY| D["orders.priority"]
    C -->|STANDARD| E["orders.standard"]
    D --> F["priorityHandler"]
    E --> G["standardHandler"]
~~~

### 5.2. Step 1 — Declare Data Contracts and Functions

Java 17+ example:

~~~java
package example.orders;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderRequest(String id, long totalVnd) {}
record RoutingDecision(String id, long totalVnd, String tier) {}

@Configuration
class OrderFunctions {

    @Bean
    Function<OrderRequest, OrderRequest> normalizeOrder() {
        return order -> {
            if (order == null || order.id() == null
                    || order.id().isBlank() || order.totalVnd() <= 0) {
                throw new IllegalArgumentException("Invalid order");
            }

            String id = order.id().strip().toUpperCase(Locale.ROOT);
            return new OrderRequest(id, order.totalVnd());
        };
    }

    @Bean
    Function<OrderRequest, RoutingDecision> classifyOrder() {
        return order -> new RoutingDecision(
                order.id(),
                order.totalVnd(),
                order.totalVnd() >= 1_000_000
                        ? "PRIORITY" : "STANDARD");
    }
}
~~~

Neither function knows about HTTP, message brokers, channel names, or which flow calls them. Therefore, they can be reused in a REST endpoint or a serverless adapter under the same function definition names.

`normalizeOrder` performs validation and throws `IllegalArgumentException` on invalid data; throwing an exception here is a **business rejection rule**, not an EIP Message Filter.

### 5.3. Step 2 — Create IntegrationFlow and Look Up the Composition

~~~java
package example.orders;

import java.util.Objects;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.function.Function;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
class OrderIntegration {

    @Bean("orders.input")
    MessageChannel inputChannel() {
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

    @Bean("priorityResults")
    BlockingQueue<RoutingDecision> priorityResults() {
        return new LinkedBlockingQueue<>();
    }

    @Bean("standardResults")
    BlockingQueue<RoutingDecision> standardResults() {
        return new LinkedBlockingQueue<>();
    }

    @Bean
    IntegrationFlow classifyFlow(FunctionCatalog catalog) {
        Function<OrderRequest, RoutingDecision> classify =
                Objects.requireNonNull(
                        catalog.lookup("normalizeOrder|classifyOrder"),
                        "Order composition not found");

        return IntegrationFlow.from("orders.input")
                .transform(OrderRequest.class, classify::apply)
                .route(RoutingDecision.class,
                        RoutingDecision::tier,
                        route -> route
                                .channelMapping("PRIORITY", "orders.priority")
                                .channelMapping("STANDARD", "orders.standard"))
                .get();
    }

    @Bean
    IntegrationFlow priorityFlow(
            @Qualifier("priorityResults")
            BlockingQueue<RoutingDecision> results) {
        return IntegrationFlow.from("orders.priority")
                .handle(RoutingDecision.class, (payload, headers) -> {
                    results.add(payload);
                    return null;
                })
                .get();
    }

    @Bean
    IntegrationFlow standardFlow(
            @Qualifier("standardResults")
            BlockingQueue<RoutingDecision> results) {
        return IntegrationFlow.from("orders.standard")
                .handle(RoutingDecision.class, (payload, headers) -> {
                    results.add(payload);
                    return null;
                })
                .get();
    }
}
~~~

Notable points:

- `lookup("normalizeOrder|classifyOrder")` asks the catalog to chain the `OrderRequest` output of the first function into the `OrderRequest` input of the second. The resulting business type is `Function<OrderRequest, RoutingDecision>`.
- `transform(OrderRequest.class, classify::apply)` runs the composition on the **payload**; Spring Integration normally carries message headers across endpoints according to flow message propagation, though important headers should be tested.
- `route(RoutingDecision.class, RoutingDecision::tier, ...)` reads the routing key from the payload and forwards the message to the matching channel. The function only **returns a decision**; it does not send to channels itself.
- `priorityFlow` and `standardFlow` act as terminal handlers, each appending to an in-memory queue for demonstration. In production, these can be replaced with outbound adapters, database writes, or service calls.
- `DirectChannel` is synchronous and does not persist messages. This example provides no broker delivery guarantees or crash recovery.

**Regarding configuration:** the beans in this example must be scanned by Spring Boot in the same package or imported via `@Import` into the application configuration. The demo uses three specifically named channels; if you attach an external inbound adapter, that adapter must feed into `orders.input`.

### 5.4. Step 3 — Send a Message

In application or test code with a Spring context:

~~~java
MessageChannel input =
        context.getBean("orders.input", MessageChannel.class);

boolean sent = input.send(
        new GenericMessage<>(new OrderRequest(" dh-042 ", 1_750_000)));

System.out.println(sent); // true if the message is accepted
~~~

You need to import `org.springframework.messaging.MessageChannel` and `org.springframework.messaging.support.GenericMessage`; `context` is an injected or retrieved `ApplicationContext`.

Expected result: `priorityResults` receives

~~~text
RoutingDecision[id=DH-042, totalVnd=1750000, tier=PRIORITY]
~~~

and `standardResults` does not receive this order.

### 5.5. Why Not Call the Function Bean Directly?

This still executes the business logic normally:

~~~java
Function<OrderRequest, OrderRequest> normalize =
        applicationContext.getBean("normalizeOrder", Function.class);
~~~

However, when a flow intentionally relies on **composition**, SCF-supported conversions, and function-definition abstractions, retrieving via `FunctionCatalog` stays consistent with SCF adapters. Even so, catalog lookup does not remove the need for clear input/output contracts and exception handling.

## 6. Calling Supplier and Consumer from IntegrationFlow

`FunctionCatalog` holds more than just `Function<T,R>`.

### 6.1. Consumer as a Terminal Step

When the catalog contains:

~~~java
@Bean
Consumer<RoutingDecision> dispatchOrder() {
    return decision -> System.out.println("Dispatched: " + decision.id());
}
~~~

you can build an endpoint:

~~~java
@Bean
IntegrationFlow dispatchFlow(FunctionCatalog catalog) {
    Consumer<RoutingDecision> dispatch =
            Objects.requireNonNull(
                    catalog.lookup("dispatchOrder"),
                    "dispatchOrder not found");

    return IntegrationFlow.from("orders.dispatchInput")
            .handle(RoutingDecision.class, (payload, headers) -> {
                dispatch.accept(payload);
                return null;
            })
            .get();
}
~~~

The example assumes the `orders.dispatchInput` channel has been declared separately. With `Consumer<T>`, the action usually performs a side effect and returns no data to a downstream step; place it at the end of the flow or define an explicit reply if needed.

### 6.2. Supplier as a Source

When the catalog contains:

~~~java
@Bean
Supplier<String> nextCode() {
    return () -> "DH-DEMO";
}
~~~

Spring Integration can use the supplier as a source for a polling endpoint:

~~~java
@Bean
IntegrationFlow pollCodes(FunctionCatalog catalog) {
    Supplier<String> supplier =
            Objects.requireNonNull(
                    catalog.lookup("nextCode"),
                    "nextCode not found");

    return IntegrationFlow
            .from(supplier, spec -> spec
                    .poller(Pollers.fixedDelay(1000)))
            .channel("codes.output")
            .get();
}
~~~

Add imports for `java.util.function.Supplier`, `org.springframework.integration.dsl.Pollers`, and the corresponding Spring types; channel `codes.output` is configured elsewhere. This is a **polling-source illustration**, not a flow wired to `orders.input` from the previous example.

Key points to understand:

- `Supplier<T>` is invoked on the poller's schedule, not in response to messages sent to a message channel.
- `Pollers.fixedDelay(1000)` sets a delay of 1,000 milliseconds per the DSL.
- In many polling adapters, a `null` return value means the source has no message for that poll cycle; verify the exact semantics of your supplier and adapter.
- If a supplier reads and deletes data from an external system, design acknowledgement and recovery because downstream failures can lose already-fetched items.
- Do not use a supplier that emits the same value forever if a real application needs termination conditions, unless cadence and lifecycle are bounded.

## 7. Comparing Three Ways to Wire Functions into IntegrationFlow

| Approach | Sample Syntax | Best Suited When | Trade-off |
| --- | --- | --- | --- |
| Direct bean injection | `flow.transform(normalizeOrderBean)` | You only need plain Java functions without SCF features. | Bypasses catalog wrappers, lookup, and composition. |
| Manual lookup | `catalog.lookup("normalizeOrder|classifyOrder")` then `flow.transform(...)` | You want explicit control over transformers, handlers, types, and EIPs in the flow. | Requires lookup code, null checks, and wiring into endpoints. |
| FunctionFlowBuilder | `builder.from("input").apply("normalizeOrder|classifyOrder")` | The project already uses `spring-cloud-function-integration` and wants flows expressed by function name. | Adds a specialized module/DSL and couples to that module's API. |

### 7.1. The Same Idea with FunctionFlowBuilder

When `org.springframework.cloud:spring-cloud-function-integration` (from a compatible release train) is on the classpath, the module auto-configures `FunctionFlowBuilder` with `FunctionCatalog`:

~~~java
@Bean
IntegrationFlow classifyWithBuilder(FunctionFlowBuilder builder) {
    return builder
            .from("orders.builderInput")
            .apply("normalizeOrder|classifyOrder")
            .route(RoutingDecision.class,
                    RoutingDecision::tier,
                    r -> r
                            .channelMapping("PRIORITY", "orders.priority")
                            .channelMapping("STANDARD", "orders.standard"))
            .get();
}
~~~

Import `org.springframework.cloud.function.integration.FunctionFlowBuilder`. The `orders.builderInput` channel is a separate source that must be declared. This snippet shows **an alternative option** to `classifyFlow` and is not meant to register two flows listening on `orders.input` simultaneously in a runnable sample.

The `apply(String functionDefinition)` and `accept(String consumerDefinition)` operators look up function names from the catalog. `fromSupplier("supplierName")` uses a supplier in the catalog as a source. You can still combine them with EIP operators such as `filter`, `route`, `wireTap`, and `channel` provided by Spring Integration.

**Version note:** the integration module was introduced in Spring Cloud Function 4.0.3; verify the documentation for your exact release. Do not assume older Spring Cloud Function releases include `FunctionFlowBuilder`.

### 7.2. When Do You Use `spring.cloud.function.definition`?

The property:

~~~properties
spring.cloud.function.definition=normalizeOrder|classifyOrder
~~~

is normally used by **adapters or binders** to pick which function or composition they invoke. In an explicit `IntegrationFlow` like the ones above, `catalog.lookup("normalizeOrder|classifyOrder")` already specifies the function; it does not rely on that property to choose the function name.

Setting the property does not automatically create `orders.input`, wire a Kafka topic to it, or replace an `IntegrationFlow` definition. When an application uses both Spring Cloud Stream bindings and Spring Integration flows, clearly define the **message entry point** to avoid duplicate processing.

## 8. Payloads, Message Headers, and Type Conversion

### 8.1. What Argument Does the Function Receive?

A Spring Integration message consists of:

~~~text
Message<OrderRequest>
  payload = OrderRequest("DH-042", 1750000)
  headers = {traceId: "trace-123", ...}
~~~

With:

~~~java
.transform(OrderRequest.class, classify::apply)
~~~

`classify::apply` receives **`OrderRequest`**—the payload—not the full `Message<OrderRequest>`. This keeps business functions simple and decoupled from transport details.

If a rule genuinely needs headers, you can define a function typed with `Message<T>`:

~~~java
@Bean
Function<Message<OrderRequest>, Message<OrderRequest>> addProcessingStage() {
    return incoming -> MessageBuilder.fromMessage(incoming)
            .setHeader("processingStage", "VALIDATED")
            .build();
}
~~~

Import `org.springframework.messaging.Message` and `org.springframework.messaging.support.MessageBuilder`. When wiring a `Message`-accepting function to an endpoint, choose the appropriate **whole-message** overload/contract and verify the actual payload and headers after passing through the catalog wrapper. Do not blindly cast `Message<?>` to `Message<OrderRequest>` without verifying the runtime input.

Additional notes:

- `FunctionCatalog` supports data conversion based on function signatures, content types, and available converters. There is no guarantee that an arbitrary object will turn into `OrderRequest` without a matching converter or configuration.
- Spring Integration typically preserves message headers when creating a new message in a transformer, though passing through an SCF wrapper or adapter may affect headers depending on the specific contract. Write integration tests for critical headers such as trace IDs, correlation IDs, or acknowledgement metadata.
- Distinguish business headers from broker metadata. Headers for retries, acknowledgements, or partition keys may be managed by the adapter and should not be mutated arbitrarily.

### 8.2. Example of an Input Type Mismatch

~~~java
Function<OrderRequest, RoutingDecision> classify =
        catalog.lookup("normalizeOrder|classifyOrder");

// Wrong if sending a String without a String -> OrderRequest converter:
input.send(new GenericMessage<>("{\"id\":\"DH-042\",\"totalVnd\":1750000}"));
~~~

The flow in Section 5 expects an **`OrderRequest` payload**. If inbound HTTP or a broker delivers JSON, a deserialization/converter step or explicit content-type configuration is required before the transformer. Test serialization, missing fields, enum/date/number formats, and boundary validation.

## 9. Composition and Type Constraints

When the catalog looks up `"f1|f2"`, logically:

~~~text
input --f1--> intermediate --f2--> output
~~~

For example:

~~~java
Function<OrderRequest, RoutingDecision> composed =
        catalog.lookup("normalizeOrder|classifyOrder");
~~~

For composition to work, `f1`'s output type must be compatible with `f2`'s input type. Some valid conversions can be performed by SCF converters, but you should not rely on undocumented or untested conversions.

Although composition is very useful, it only handles **a chain of functions invoked together**:

- It does not create message channels between two functions.
- It does not retry individual steps via a broker.
- It does not create a Splitter/Aggregator or correlation store.
- It does not turn a returned list into multiple messages with sequence headers.
- It does not expose a `Function<T,R>` as an HTTP endpoint without a corresponding adapter.

If you need an EIP between two steps, place each function in its own transformer:

~~~java
Function<OrderRequest, OrderRequest> normalize =
        catalog.lookup("normalizeOrder");
Function<OrderRequest, RoutingDecision> classify =
        catalog.lookup("classifyOrder");

return IntegrationFlow.from("orders.filteredInput")
        .transform(OrderRequest.class, normalize::apply)
        .filter(OrderRequest.class, order -> order.totalVnd() >= 10_000)
        .transform(OrderRequest.class, classify::apply)
        .channel("orders.filteredOutput")
        .get();
~~~

This snippet assumes `orders.filteredInput` and `orders.filteredOutput` are already configured; it is a flow variant and should not run concurrently on the same source as the Section 5 flow. Note the **policy difference**: this variant filters out orders below 10,000 VND, whereas the Section 5 composition has no such filter.

## 10. Errors, Retries, Transactions, and Asynchronous Flows

Keep four distinct issues separate instead of lumping them together:

| Scenario | Where It Occurs | How to Handle |
| --- | --- | --- |
| Function definition not found | When `catalog.lookup(...)` runs or during flow initialization. | Fail fast, report the missing function name clearly; inspect beans and catalog config. |
| Payload type mismatch or missing converter | Before or while the transformer invokes the function. | Fix the message contract, converter, content type, and boundary validation. |
| Function throws an exception due to invalid business data | Inside `normalizeOrder.apply(...)` or another function. | Return a classified error, drop according to policy, or route to an invalid-data flow. Do not retry indefinitely. |
| External system temporarily unavailable | Inside a handler or outbound adapter. | Retry/backoff, error flow, DLQ, or compensation according to adapter and infrastructure. |

With `DirectChannel`, execution is typically **synchronous on the sender's thread**. If a function inside a transformer throws an exception, it can propagate back to the `send(...)` call. Having an `errorChannel` in the application does not mean every synchronous exception is automatically routed there; error flows depend on how endpoints, pollers, executors, or adapters handle exceptions.

When replacing `DirectChannel` with `ExecutorChannel`, `QueueChannel`, or a broker adapter:

- Where and when errors surface can change.
- The sender may only know the message was enqueued, not that business processing succeeded.
- You may need timeouts, retries, status observability, dead-letter channels, and idempotency.
- Processing order, concurrency, and in-flight message limits must be reconsidered.

**Do not treat composition as a transaction**: `catalog.lookup("f1|f2")` does not guarantee two functions commit or roll back together; if one step performs a side effect before the next step fails, design proper compensation or transaction management.

## 11. Reactive Functions in IntegrationFlow

SCF also supports signatures such as:

~~~java
Function<Flux<OrderRequest>, Flux<RoutingDecision>> reactiveClassify
~~~

Here the input and output are no longer a single `OrderRequest`. You should not pass this function directly into:

~~~java
.transform(OrderRequest.class, reactiveFunction::apply)
~~~

because `reactiveFunction.apply(...)` expects a `Flux<OrderRequest>`, whereas the transformer receives a single `OrderRequest` payload. You need an appropriate reactive boundary (such as a reactive channel, a `Flux` source, or a stream-capable endpoint), along with explicit subscription, backpressure, lifecycle, and error-propagation design.

Spring Cloud Function supports the reactive model, and Spring Integration provides reactive DSL/endpoints, but compatibility depends on exact types, versions, and adapters. Do not force a `Flux` into an ordinary payload just to make the code compile. Test the entire chain under load as well as stream error and completion cases.

## 12. Testing Each Layer of a Catalog Invocation

### 12.1. Unit Testing Functions

Call only the business logic:

~~~java
OrderFunctions functions = new OrderFunctions();

OrderRequest normalized =
        functions.normalizeOrder()
                 .apply(new OrderRequest(" dh-042 ", 1_750_000));

RoutingDecision decision =
        functions.classifyOrder().apply(normalized);

assertEquals("DH-042", decision.id());
assertEquals("PRIORITY", decision.tier());
~~~

Requires JUnit 5 and static import `org.junit.jupiter.api.Assertions.assertEquals`. Additional test cases to add: the `1_000_000` boundary stays `PRIORITY`; `999_999` maps to `STANDARD`; blank IDs or totals less than or equal to 0 are rejected.

### 12.2. Testing the Catalog and Composition

In a test with a Spring context:

~~~java
@Autowired
FunctionCatalog catalog;

@Test
void catalogShouldComposeByName() {
    Function<OrderRequest, RoutingDecision> f =
            catalog.lookup("normalizeOrder|classifyOrder");

    assertNotNull(f);
    assertEquals(
            "STANDARD",
            f.apply(new OrderRequest(" a-1 ", 100_000)).tier());
}
~~~

This test catches beans missing from the catalog, wrong function names, incompatible types, or composition errors.

### 12.3. Integration Testing with Channels and Flows

~~~java
@SpringBootTest
class OrderFlowTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    @Qualifier("priorityResults")
    BlockingQueue<RoutingDecision> priorityResults;

    @Autowired
    @Qualifier("standardResults")
    BlockingQueue<RoutingDecision> standardResults;

    @Test
    void shouldSendPriorityOrderToPriorityChannel() {
        priorityResults.clear();
        standardResults.clear();

        MessageChannel input =
                context.getBean("orders.input", MessageChannel.class);

        assertTrue(input.send(new GenericMessage<>(
                new OrderRequest(" dh-042 ", 1_750_000))));

        RoutingDecision result = priorityResults.poll();

        assertNotNull(result);
        assertEquals("DH-042", result.id());
        assertEquals("PRIORITY", result.tier());
        assertTrue(standardResults.isEmpty());
    }
}
~~~

Key imports: `org.springframework.boot.test.context.SpringBootTest`, `org.springframework.context.ApplicationContext`, `org.springframework.beans.factory.annotation.Autowired`, `org.springframework.beans.factory.annotation.Qualifier`, `org.junit.jupiter.api.Test`, `org.springframework.messaging.MessageChannel`, `org.springframework.messaging.support.GenericMessage`, `java.util.concurrent.BlockingQueue`, and JUnit 5 static assertions.

The test assumes the application includes `spring-boot-starter-test` and scans both `OrderFunctions` and `OrderIntegration`. With `DirectChannel`, the result reaches the handler before `send(...)` returns; if you switch to an asynchronous channel or broker, use a bounded wait instead of an immediate `poll()`. When running multiple tests, isolate queue state per test to prevent cross-test interference.

### 12.4. Common Failure Checklist

| Symptom | Check First |
| --- | --- |
| `catalog` cannot be injected | Is the SCF context dependency present, auto-configuration active, and versions compatible? |
| `catalog.lookup("name")` returns `null` or an unexpected function | Is the bean registered? Is the name right? Is a single-function fallback masking a typo? |
| Incompatible composition types | Check `f1` output and `f2` input; does a converter satisfy the contract? |
| Transformer throws `ClassCastException` | What payload type arrives from the channel? Is a JSON string entering a flow expecting a POJO? |
| Messages never reach the destination | Is the input channel named correctly? Does the router mapping cover all keys? Is there a handler/subscriber on the target channel? |
| Trace/correlation headers lost | Did a transformer or adapter construct a new message and drop headers? |
| Synchronous tests pass but production fails intermittently | Inspect executors/brokers, concurrency, retries, ordering, and idempotency. |

## 13. Design Decisions to Keep Consistent

1. **Keep business logic inside functions.** Let functions know only `OrderRequest`/`RoutingDecision` and avoid sending directly to channels inside them.
2. **Keep orchestration inside flows.** Routers, filters, splitters, aggregators, retry advice, and adapters belong to the EIP/infrastructure layer.
3. **Look up stable function names and fail fast.** For functions used by a fixed flow, looking them up during flow construction is cleaner than per-message lookups.
4. **Match the call site to the interface.** `Function` typically maps to `transform`; `Consumer` maps to a terminal handler; `Supplier` maps to a polling source or adapter-managed source.
5. **Use composition for adjacent transformations.** When an EIP step is needed in between, split into separate transformers.
6. **Control data types at boundaries.** JSON, POJOs, `Message<T>`, headers, and reactive streams all need explicit contracts.
7. **Design errors around the invocation environment.** HTTP request/response errors differ from broker retry/redelivery/DLQ; functions do not enforce uniform error transport across adapters on their own.
8. **Test across three layers.** Pure functions, catalog/composition, and `IntegrationFlow` with real channels and adapters.

### Self-Check Questions

- Why is fetching a `Function` bean from `ApplicationContext` not completely identical to calling `catalog.lookup(...)`?
- When should you choose `transform(...)` versus `handle(...)`?
- If routing is needed based on `tier`, which part is performed by the function and which part by Spring Integration?
- Does setting `spring.cloud.function.definition` make an `IntegrationFlow` automatically receive messages from a broker?
- Why can't a reactive function accepting `Flux<T>` simply be dropped into a transformer expecting `T`?
- If processing is duplicated after a broker redelivery, where should idempotency be enforced?

## 14. Official Documentation

- [Spring Cloud Function — Programming model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): `FunctionCatalog`, lookup, wrappers, conversion, composition, and function types.
- [Spring Cloud Function — Spring Integration Interaction](https://docs.spring.io/spring-cloud-function/reference/spring-integration.html): the `spring-cloud-function-integration` module, `FunctionFlowBuilder`, and `apply`/`accept` operators.
- [Spring Integration — Java DSL](https://docs.spring.io/spring-integration/reference/dsl/java-basics.html): `IntegrationFlow`, `transform`, and endpoints.
- [Spring Integration — Functions Support](https://docs.spring.io/spring-integration/reference/functions-support.html): using `java.util.function` interfaces with Integration Flows.
- [Spring Integration — Router Implementations](https://docs.spring.io/spring-integration/reference/router/implementations.html): examples of payload/channel-based routing.

**Summary:** To invoke reusable Spring Cloud Function beans inside an `IntegrationFlow`, use `FunctionCatalog.lookup(...)` (optionally with composition) and wire the result into `transform`, `handle`, or an appropriate `Supplier` source. With `spring-cloud-function-integration`, `FunctionFlowBuilder` lets you express `apply`/`accept` directly by function name. In both cases, EIPs and transport configuration remain the responsibility of Spring Integration and its adapters, allowing a single business function to be reused across HTTP, events, or serverless.
