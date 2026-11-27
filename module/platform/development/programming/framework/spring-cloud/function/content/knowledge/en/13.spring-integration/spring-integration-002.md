# The `spring-cloud-function-integration` Module

## 1. Lesson Goals

**Spring Cloud Function (SCF)** encourages writing business logic through three contracts—`Supplier<T>`, `Function<T,R>`, and `Consumer<T>`—and looking them up or composing them via `FunctionCatalog`. Functions can be reused when invoked over HTTP, events, serverless environments, or directly from a Spring application.

**Spring Integration** provides components for implementing Enterprise Integration Patterns (EIP): message channels, transformers, filters, routers, splitters, aggregators, gateways, polling adapters, and error flows. The Spring Integration Java DSL lets you describe a message's path as an `IntegrationFlow`.

The **`spring-cloud-function-integration`** module serves as the bridge between the two models. The centerpiece of the module is **`FunctionFlowBuilder`**, which is auto-configured with `FunctionCatalog` so that the Spring Integration DSL can reference functions by **definition name** instead of forcing every flow to call `catalog.lookup(...)` manually. This module was introduced in Spring Cloud Function **4.0.3** and continues to be documented in current Spring Cloud Function documentation.

After this lesson, you will be able to:

- Explain the responsibility of the module and distinguish it from `spring-cloud-function-context`, Spring Integration Core, and HTTP/broker adapters.
- Declare compatible dependencies, create functions, and use `FunctionFlowBuilder` to connect them into an `IntegrationFlow`.
- Understand the roles of `fromSupplier(...)`, `from(...)`, `apply(...)`, `accept(...)`, and composition names in `FunctionCatalog`.
- Combine function invocations with EIP operators (filter, wire tap, channel, router), while recognizing issues around type conversion, polling cadence, errors, and testing.

## 2. Why Is a Separate Integration Module Needed?

With SCF alone, an application might declare:

~~~java
@Bean
Function<String, String> normalize() {
    return text -> text.trim().toUpperCase();
}
~~~

This function does not specify where messages arrive from or where they go next. When processing real messages, a flow may need additional steps such as receiving from a channel, recording an audit log, dropping invalid payloads, transforming, branching, and invoking an outbound adapter.

The Spring Integration Java DSL already lets you pass a `Function` instance directly into a transformer. However, when an application has many functions registered in `FunctionCatalog` (including auto-configured functions from external libraries), operating by **function name** lets the flow clearly express what is being composed while the catalog handles lookup and composition. That is the problem `spring-cloud-function-integration` solves.

~~~mermaid
flowchart LR
    A["@Bean Supplier / Function / Consumer"] --> B["FunctionCatalog"]
    D["Auto-configured functions from libraries"] --> B
    B --> C["FunctionFlowBuilder"]
    C --> E["IntegrationFlow"]
    F["Inbound adapter / channel"] --> E
    E --> G["Filter / Router / Wire Tap"]
    G --> H["Consumer / outbound adapter"]
~~~

**Division of responsibilities:**

| Component | Primary Responsibility |
| --- | --- |
| `spring-cloud-function-context` | Registering, looking up, and composing `Supplier`, `Function`, and `Consumer` through `FunctionCatalog`. |
| `spring-cloud-function-integration` | Providing a DSL integrated with `FunctionCatalog` via `FunctionFlowBuilder` and `FunctionFlowDefinition`. |
| Spring Integration | Operating message channels, message endpoints, filters/routers, pollers, message stores, error flows, and other EIPs. |
| `spring-cloud-function-web` | Adapter exposing functions over HTTP in supported configurations. |
| Spring Cloud Stream and its binders | Connecting functions to destinations and brokers such as Kafka or RabbitMQ. |
| Serverless adapters | Mapping serverless platform events and execution lifecycles to functions. |

Adding `spring-cloud-function-integration` must not be interpreted as automatically giving the application REST endpoints, Kafka consumers, distributed transactions, or durable retry systems. Those require separate adapters and deployment-specific configuration.

## 3. Declaring the Dependency

### 3.1. Maven

Add the following dependency to `pom.xml` in a Spring Boot application using Spring Cloud Function:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-function-integration</artifactId>
</dependency>
~~~

This is the **module coordinate**. For the examples to run, the project also needs compatible foundational dependencies for Spring Boot, Spring Cloud Function, and Spring Integration managed by the BOM or dependency management of the Spring Cloud version in use. If `spring-integration-core`/DSL is not yet on the classpath transitively, add the Spring Integration dependencies according to your version's guide; many projects use `spring-boot-starter-integration` to pull in the appropriate starter.

When managed by a compatible Spring Cloud BOM, you typically omit an explicit `<version>` for `spring-cloud-function-integration`. **Do not mix** SCF 4.x/5.x artifacts with incompatible Spring Boot or Spring Integration versions; align with your project's release train.

### 3.2. Gradle

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-function-integration'
}
~~~

The Gradle example likewise assumes the project manages versions through a compatible Spring Cloud BOM.

### 3.3. Verifying After Adding the Library

A minimal application can define a bean:

~~~java
@Bean
IntegrationFlow flow(FunctionFlowBuilder builder) {
    return builder
            .from("inputChannel")
            .apply("someFunction")
            .accept("someConsumer");
}
~~~

If Spring cannot create the `FunctionFlowBuilder` bean, check the classpath, Spring Boot auto-configuration, dependency versions, and whether application configuration has disabled auto-configuration. If the builder is present but `someFunction` or `someConsumer` does not exist in the catalog, the problem lies in the **function definition**, not in a missing message channel.

## 4. Core API: `FunctionFlowBuilder` and `FunctionFlowDefinition`

Spring Cloud Function creates a `FunctionCatalog` containing functions that can be retrieved by name. The integration module provides `FunctionFlowBuilder`, automatically wired to the catalog. Key API points to remember:

| API | Meaning | Example |
| --- | --- | --- |
| `FunctionFlowBuilder.from("channelName")` | Starts a flow from a channel (the familiar Integration DSL style). | `.from("orders.input")` |
| `FunctionFlowBuilder.fromSupplier("supplierName")` | Looks up a `Supplier` in the catalog and uses it as a message-producing source. | `.fromSupplier("orderSource")` |
| `fromSupplier("name", endpointSpec)` | Configures additional endpoint/poller settings for the source. | `.fromSupplier("orderSource", e -> e.poller(...))` |
| `FunctionFlowDefinition.apply("functionName")` | Looks up and applies a `Function` in the flow, continuing to pass output downstream. | `.apply("normalizeOrder")` |
| `FunctionFlowDefinition.accept("consumerName")` | Looks up a `Consumer` and passes data to the terminal processing step. | `.accept("sendNotification")` |
| `apply("f1|f2")` | Invokes a composition of functions with compatible types. | `.apply("trimText|uppercaseText")` |
| `accept("f1|terminalConsumer")` | Chains steps and terminates at a consumer. | `.accept("normalize|save")` |

After `from(...)` or `fromSupplier(...)`, the flow uses `FunctionFlowDefinition`, an extension of the Spring Integration DSL, so standard Spring Integration operators such as `channel(...)`, `filter(...)`, `wireTap(...)`, `route(...)`, or `log(...)` can still be used in appropriate places.

Keep the following limitations in mind:

- Names in `apply(...)` and `accept(...)` must match the names recognized by **`FunctionCatalog`**. They do not arbitrarily reference any Spring bean with that name.
- `apply(...)` requires a function whose output can be used by the next step. `accept(...)` is the terminal step when the flow wants to consume the result.
- Composition `f1|f2` must have compatible output and input types. When chaining `Function<T,R>` into `Consumer<R>`, the composed name can be used in `accept(...)`.
- `FunctionCatalog` may wrap functions to support type/message conversion. You should not assume arbitrary Java objects or headers will convert properly without an appropriate content type, converter, or configuration.
- When a flow involves branching, multiple channels, splitting/aggregating, or side effects, those remain the responsibility of the Spring Integration DSL and its endpoints; `FunctionFlowBuilder` does not add EIP semantics on its own.

### 4.1. From Direct Lookup Calls to Name-Based Syntax

Without the integration module, you might have to perform lookups manually:

~~~java
Function<String, String> normalize =
        functionCatalog.lookup("normalizeTicket");

// Then pass normalize into processing logic or an IntegrationFlow.
~~~

With the integration module:

~~~java
return functionFlowBuilder
        .from("ticket.input")
        .apply("normalizeTicket")
        .accept("recordTicket");
~~~

The second snippet expresses the pipeline using catalog names and can still insert other EIP steps in between. This improves expressiveness and flow assembly; it does **not** turn the functions themselves into brokers or HTTP controllers.

## 5. Hands-On Example: Processing Support Tickets

### 5.1. Requirements

Suppose the system receives support ticket codes as strings:

~~~text
  vip-2026-042
~~~

Processing rules:

1. Trim whitespace and convert to uppercase.
2. Drop messages whose normalized code is empty.
3. If the code starts with `VIP-`, mark it `EXPRESS`; otherwise `STANDARD`.
4. Collect results into an in-memory queue to illustrate the consumer. In production, the consumer can be replaced with database persistence or an outbound adapter call.

We separate business rules into functions for reuse, while filtering and message routing belong to Spring Integration.

~~~mermaid
flowchart LR
    A["tickets.input"] --> B["apply normalizeTicket"]
    B --> C{"filter non-empty code"}
    C -->|Keep| D["apply classifyTicket"]
    C -->|Drop| X["Discard"]
    D --> E["accept captureTicket"]
    E --> F["Result queue"]
~~~

### 5.2. Defining the Functions and Consumer

The example uses Spring Boot 3.x (or a Spring Boot version compatible with your chosen release train) and Java 17+; full imports are shown so the data types are clear.

~~~java
package example.ticket;

import java.util.Locale;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.function.Consumer;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record TicketDecision(String code, String lane) {}

@Configuration
public class TicketFunctions {

    @Bean
    Function<String, String> normalizeTicket() {
        return input -> input.trim().toUpperCase(Locale.ROOT);
    }

    @Bean
    Function<String, TicketDecision> classifyTicket() {
        return code -> new TicketDecision(
                code,
                code.startsWith("VIP-") ? "EXPRESS" : "STANDARD");
    }

    @Bean
    Queue<TicketDecision> capturedTickets() {
        return new ConcurrentLinkedQueue<>();
    }

    @Bean
    Consumer<TicketDecision> captureTicket(
            Queue<TicketDecision> capturedTickets) {
        return capturedTickets::add;
    }
}
~~~

The two functions represent transformations. `captureTicket` is a consumer with a **side effect**, so in production it needs error, idempotency, transaction, or retry policies at the right layer if moved to a database or broker. For instance, `normalizeTicket` currently assumes a non-`null` input; if the system can receive `null`, define the input contract and error reporting clearly.

### 5.3. Defining the IntegrationFlow with FunctionFlowBuilder

~~~java
package example.ticket;

import org.springframework.cloud.function.integration.FunctionFlowBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
public class TicketIntegration {

    @Bean("tickets.input")
    MessageChannel ticketInput() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow ticketFlow(FunctionFlowBuilder builder) {
        return builder
                .from("tickets.input")
                .apply("normalizeTicket")
                .filter(String.class, code -> !code.isBlank())
                .apply("classifyTicket")
                .accept("captureTicket");
    }
}
~~~

Each line in the DSL plays a distinct role:

- `from("tickets.input")`: takes messages from a named Spring Integration channel.
- `apply("normalizeTicket")`: looks up the function in the catalog to normalize the payload.
- `filter(...)`: an EIP **Message Filter** that decides to drop empty messages; this is Spring Integration behavior, distinct from a `Function<Boolean>` that merely returns a boolean value.
- `apply("classifyTicket")`: turns the string into a `TicketDecision`.
- `accept("captureTicket")`: ends the pipeline at the consumer that records results in the queue.

With `DirectChannel`, execution happens synchronously on the sender's thread by default unless an asynchronous boundary is configured. Choosing a different channel type, adapter, or executor can change execution characteristics.

### 5.4. Sending a Test Message

In a Spring context where the beans above have been initialized:

~~~java
MessageChannel input =
        context.getBean("tickets.input", MessageChannel.class);

input.send(new GenericMessage<>("  vip-2026-042  "));

// capturedTickets.poll() returns:
// TicketDecision[code=VIP-2026-042, lane=EXPRESS]
~~~

You need to import `org.springframework.messaging.support.GenericMessage`, `org.springframework.messaging.MessageChannel`, and an `ApplicationContext` named `context`; `capturedTickets` here is the queue bean defined earlier.

The flow does not automatically listen to HTTP or Kafka: receiving external messages requires an inbound adapter or binding that delivers messages into `tickets.input`.

### 5.5. Using Composition for Adjacent Steps

If you do not need an EIP Filter between normalization and classification, you can shorten the flow:

~~~java
@Bean
IntegrationFlow simplerTicketFlow(FunctionFlowBuilder builder) {
    return builder
            .from("tickets.otherInput")
            .accept("normalizeTicket|classifyTicket|captureTicket");
}
~~~

In this example, `tickets.otherInput` is another channel that must be declared or configured appropriately before use. Composition requires `normalizeTicket` to return `String`, `classifyTicket` to accept `String`, and `captureTicket` to accept `TicketDecision`, which are mutually compatible.

**Do not treat the two pipelines as completely equivalent:** the shortened pipeline omits the filter step, so a whitespace-only string will still reach `classifyTicket`. If the "drop empty input" rule is mandatory, keep the filter or move the validation policy to an appropriate component.

## 6. Starting a Flow from a Supplier with `fromSupplier(...)`

When you have a function-backed data source, you can let `FunctionFlowBuilder` look up a `Supplier` by name:

~~~java
@Bean
Supplier<String> scheduledTicket() {
    return () -> "VIP-HEARTBEAT";
}

@Bean
Consumer<String> logTicket() {
    return code -> System.out.println("Received: " + code);
}

@Bean
IntegrationFlow supplierDrivenFlow(FunctionFlowBuilder builder) {
    return builder
            .fromSupplier("scheduledTicket",
                    e -> e.poller(Pollers.fixedDelay(5000)))
            .apply("normalizeTicket")
            .accept("logTicket");
}
~~~

You need to import `java.util.function.Supplier`, `java.util.function.Consumer`, `org.springframework.integration.dsl.Pollers`, and the corresponding Spring annotations/`IntegrationFlow` types. `Pollers.fixedDelay(5000)` configures the delay between polls in this example; the unit is milliseconds per the DSL API.

In a polling-style flow:

- `Supplier<T>` produces data when invoked by the poller, rather than receiving data pushed from a channel.
- Invocation cadence, messages per poll, thread pool, error handling, and lifecycle depend on endpoint/poller configuration.
- For a supplier reading from a queue, understand how `null` is handled when no item is available: in standard polling sources, `null` means no message is emitted during that poll cycle.
- A supplier with side effects (such as removing an item from a queue) needs acknowledgement and recovery strategies if downstream processing fails.

`fromSupplier(...)` is helpful when you want to use sources registered in `FunctionCatalog`, such as source functions provided by libraries or auto-configuration. When the real source is a broker or webhook, a dedicated inbound adapter usually handles acknowledgements, event lifecycles, and transport properties more thoroughly.

## 7. Combining Spring Integration EIPs with Functions

The integration module **does not replace** the core Java DSL. You can place EIP operators directly between functions.

| Requirement | Approach | What Stays in the Function |
| --- | --- | --- |
| Observe messages without altering the processing path | `wireTap(...)` connected to an audit channel. | Payload transformation/validation. |
| Process only a subset of messages | `filter(...)` or `route(...)`. | Condition or routing-key computation if reuse is desired. |
| Switch threads or buffer messages | `channel(...)` with an appropriate channel type. | Schedule-independent business rules. |
| Split child records and recombine them | `split(...)`, `aggregate(...)` with correlation and release strategies. | Per-record processing and result calculation. |
| Send messages to another system | Outbound adapter/handler or boundary consumer. | Computing the content to send. |
| Handle integration errors | Error channel, retry advice, environment-specific binder retry/DLQ. | Defining reportable business errors. |

Example adding a Wire Tap when an audit channel and its consumer are already configured:

~~~java
@Bean
IntegrationFlow auditedFlow(FunctionFlowBuilder builder) {
    return builder
            .from("tickets.auditInput")
            .wireTap("tickets.auditChannel")
            .apply("normalizeTicket")
            .accept("logTicket");
}
~~~

This snippet is **illustrative** and only works once `tickets.auditInput`, `tickets.auditChannel`, and a receiving endpoint on the audit channel exist. Wire Tap is a separate EIP, not a feature of catalog composition names.

### 7.1. Should a Function Process the Payload or a Message?

Pure function:

~~~java
Function<String, String> normalizeTicket = String::trim;
~~~

Function needing metadata:

~~~java
Function<Message<String>, Message<String>> addStepHeader =
        message -> MessageBuilder.fromMessage(message)
                .setHeader("processingStep", "normalized")
                .build();
~~~

You need to import `org.springframework.messaging.Message` and `org.springframework.messaging.support.MessageBuilder`. In the second case, the function intentionally works with message headers. Test which headers are preserved across the functions and adapters in use: headers such as `contentType`, correlation ID, partition key, or acknowledgement may carry environment-specific semantics.

Java generic signatures, actual runtime payloads, and content types all influence data conversion; do not rely on type inference to carry arbitrary payloads across the entire chain.

### 7.2. Relationship to Reactive Flows

Spring Cloud Function supports reactive signatures such as `Function<Flux<T>, Flux<R>>`. Spring Integration can build reactive flows using appropriate operators and channels, but you should **not** blindly turn an imperative `Function<T,R>` into `Function<Flux<T>,Flux<R>>` and assume every blocking operator remains safe.

When integrating with reactive streams, clearly define subscription boundaries, backpressure, timeouts, multi-element emission, and error propagation. The SCF documentation includes an advanced example combining an HTTP source, asynchrony, and a `flux()` channel to illustrate this.

## 8. Distinguishing from `spring.cloud.function.definition`

`spring.cloud.function.definition` is a property commonly used by adapters/binders to select which function or composition to activate:

~~~properties
spring.cloud.function.definition=normalizeTicket|classifyTicket
~~~

Inside an `IntegrationFlow` written with `FunctionFlowBuilder`, names passed **directly** to `apply(...)`/`accept(...)` also instruct catalog lookup:

~~~java
return builder
        .from("tickets.input")
        .apply("normalizeTicket|classifyTicket")
        .accept("captureTicket");
~~~

Both approaches can use `FunctionCatalog`, yet they **do not have the same side effects**:

- The property applies to the component reading it (such as an adapter or binder) and does not define channels in Spring Integration.
- The name passed to the DSL specifies the function invoked by that particular flow; it does not make every inbound adapter automatically point to that flow.
- If you use both Spring Cloud Stream and Spring Integration in the same application, explicitly design which adapter/binding acts as the true entry point so an event is not accidentally processed twice.

## 9. Testing and Diagnostics

### 9.1. Unit Testing Pure Functions

The `normalizeTicket` and `classifyTicket` beans can be tested without a Spring context:

~~~java
TicketFunctions config = new TicketFunctions();

String normalized =
        config.normalizeTicket().apply(" vip-007 ");

TicketDecision result =
        config.classifyTicket().apply(normalized);

assertEquals("VIP-007", result.code());
assertEquals("EXPRESS", result.lane());
~~~

Add cases for `"  "`, `"standard-123"`, and invalid inputs according to your chosen contract. This verifies the **business rules**.

### 9.2. End-to-End Integration Testing of an Internal Flow

In a Spring Boot test, you can obtain the message channel and result queue via injection:

~~~java
@SpringBootTest
class TicketFlowTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    Queue<TicketDecision> capturedTickets;

    @Test
    void routesVipTicketThroughCatalogFunctions() {
        MessageChannel input =
                context.getBean("tickets.input", MessageChannel.class);

        input.send(new GenericMessage<>("  vip-007  "));

        TicketDecision result = capturedTickets.poll();
        assertNotNull(result);
        assertEquals("VIP-007", result.code());
        assertEquals("EXPRESS", result.lane());
    }
}
~~~

Common imports include `org.springframework.boot.test.context.SpringBootTest`, `org.springframework.beans.factory.annotation.Autowired`, `org.springframework.context.ApplicationContext`, `org.springframework.messaging.MessageChannel`, `org.springframework.messaging.support.GenericMessage`, `org.junit.jupiter.api.Test`, and JUnit 5 static assertions. The test assumes application configuration scans both `TicketFunctions` and `TicketIntegration`, and that the project includes `spring-boot-starter-test`.

Because the demo uses `DirectChannel` with a consumer appending results to a queue, you can assert immediately after `send(...)`. If you switch to an asynchronous channel or a broker, use bounded waiting and verify the environment's delivery semantics rather than keeping a synchronous assumption.

### 9.3. Quick Troubleshooting Table

| Symptom | What to Check |
| --- | --- |
| Cannot inject `FunctionFlowBuilder` | Missing integration module, Spring auto-configuration did not run, or incompatible dependency versions. |
| Cannot find `normalizeTicket` | Wrong bean/function name, function not registered in the catalog, or catalog not initialized as expected. |
| `accept(...)` reports no matching consumer | Mismatched type/definition at the end of the chain, or referencing an unregistered consumer. |
| `ClassCastException` or converter error | Mismatch between payload, Java generics, and actual content type; a converter/mapper or explicit contract is needed. |
| No messages enter the flow | Wrong target channel, inbound adapter not wired, `Supplier` not polled, or poller not running. |
| Supplier is called continuously or too slowly | Check poller configuration, delay, scheduler, and max messages per poll. |
| Data is processed more than once | Check for multiple inbound bindings, redelivery, multiple consumers/flows, and idempotency of the terminal step. |
| Exceptions do not go to the error channel as expected | Check synchronous vs. asynchronous execution, error handler/advice, adapter settings, and exception propagation path. |

Policy errors such as invalid input values should be separated from infrastructure errors (timeouts, connection drops) so retries are applied sensibly; endlessly retrying the exact same invalid data can create unnecessary loops.

## 10. Implementation Principles

1. **Keep functions reusable.** Focus on business logic and minimize direct coupling to transport or message channels.
2. **Use catalog names consistently.** With multiple similarly named beans, passing the wrong name into the DSL easily causes failures when building or running the flow.
3. **Choose the DSL based on actual needs.** If you only need `f.andThen(g)`, composition may suffice. If you need EIPs, add `IntegrationFlow` deliberately.
4. **Separate entry and exit points.** `fromSupplier(...)` is a polling source; `from(...)` receives from a channel; `apply(...)` processes and continues; `accept(...)` terminates with a consumer.
5. **Pay attention to message metadata.** Headers may be needed for routing, correlation, tracing, and acknowledgements; verify header preservation for each adapter.
6. **Design retries and idempotency at the right boundaries.** `FunctionFlowBuilder` does not provide exactly-once delivery or distributed transactions simply because you called `apply(...)`.
7. **Keep dependencies on a single release train.** Verify compatibility across Spring Boot, Spring Cloud Function, Spring Integration, and your application's actual adapters.
8. **Test across three layers.** Unit test functions; test catalog/composition; integration test the flow and actual entry/exit points.

### Self-Check Questions

- When should you use `fromSupplier("name")` instead of `from("channelName")`?
- Why does `apply("f1|f2")` not replace an EIP router or aggregator?
- If a function accepts `Message<Order>`, what else do you need to test besides the payload?
- Why is setting `spring.cloud.function.definition` not enough to create a broker consumer?
- If a message is processed twice after a network error, which layer is appropriate for enforcing idempotency?

## 11. References

- [Spring Cloud Function — Spring Integration Interaction](https://docs.spring.io/spring-cloud-function/reference/spring-integration.html): introduces `spring-cloud-function-integration`, `FunctionFlowBuilder`, and official DSL examples.
- [Spring Integration — java.util.function Interfaces Support](https://docs.spring.io/spring-integration/reference/functions-support.html): how Spring Integration uses `Supplier` and `Function` in endpoints and flows.
- [Spring Cloud Function — Programming model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): `FunctionCatalog`, function definitions, composition, data conversion, and related capabilities.

**Summary:** `spring-cloud-function-integration` adds DSL APIs so an `IntegrationFlow` can look up functions in `FunctionCatalog` by name—most notably via `FunctionFlowBuilder.fromSupplier(...)`, `apply(...)`, and `accept(...)`. As a result, logic written with `Supplier`, `Function`, and `Consumer` stays independent of HTTP, event, or serverless invocation, while Spring Integration handles message routing, EIPs, and operational configuration.
