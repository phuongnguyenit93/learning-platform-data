# The `apply` and `accept` Operators with Single or Composed Function Names

## 1. Context and Goals

**Spring Cloud Function (SCF)** provides a programming model built around three Java interfaces: `Supplier<T>` produces data, `Function<T,R>` transforms data, and `Consumer<T>` accepts data to perform an action. Functions are managed through **`FunctionCatalog`**, can be composed (*function composition*), and can be reused with HTTP adapters, event streams, or serverless environments. The logic inside these functions does not need to know which protocol is invoking them.

**Spring Integration** provides `IntegrationFlow` and Enterprise Integration Patterns (EIP) such as message channels, transformers, filters, routers, wire taps, splitters, aggregators, and service activators. When combined with Spring Cloud Function, a message flow needs to invoke the right business functions in the catalog while keeping orchestration authority in the Integration layer.

The `spring-cloud-function-integration` module adds **`FunctionFlowBuilder`** and **`FunctionFlowDefinition`**. The two operators covered in this lesson are:

- `apply(String functionDefinition)`: invokes a **`Function`** whose output passes the message to the next step.
- `accept(String consumerDefinition)`: invokes a **`Consumer`** to consume data and terminate the flow; the definition passed in can also be a chain of `Function`s ending with a `Consumer`.

Both accept **names or composed function definitions** understood by `FunctionCatalog`, such as `"normalizeCode"` or `"normalizeCode|classifyCode"`.

After this lesson, you will be able to: distinguish `apply` from `accept`, compose type-compatible functions, interleave EIPs between invocations, build a runnable flow, test according to message semantics, and diagnose common runtime errors.

## 2. Position of apply and accept in the Integration DSL

### 2.1. Flow Diagram

~~~mermaid
flowchart LR
    A["Source: channel / Supplier / adapter"] --> B["FunctionFlowBuilder"]
    C["FunctionCatalog"] -. "lookup name / composition" .-> D["apply: Function"]
    C -. "lookup name / composition" .-> F["accept: Consumer"]
    B --> D
    D --> E["EIP: filter / router / wireTap..."]
    E --> F
    F --> G["Terminal side effect: save / send / record"]
~~~

`FunctionFlowBuilder` is auto-configured with the catalog when a compatible `spring-cloud-function-integration` module is on the classpath. A statement like:

~~~java
return builder
        .from("tickets.input")
        .apply("normalizeCode")
        .accept("archiveCode");
~~~

reads as follows:

1. Receive messages on channel `tickets.input`.
2. Look up `normalizeCode` in the catalog and invoke the `Function` to produce an output.
3. Pass that output to `archiveCode`, a terminal `Consumer`.

Here, `"tickets.input"` is a Spring Integration **channel name**; `"normalizeCode"` and `"archiveCode"` are **catalog function names**. They belong to two different conceptual namespaces, even though both are represented as `String`.

### 2.2. Direct Comparison

| Criterion | `apply("name")` | `accept("name")` |
| --- | --- | --- |
| Looked-up target | `Function<T,R>` | `Consumer<T>` |
| Input | Payload or message depending on function signature and SCF wrappers | Payload or message depending on consumer signature |
| Business output | Produces `R` for the next step to use | `void`; no output payload to continue with |
| Position in flow | Beginning, middle, or before the end of a chain | Typically at the terminal point of the flow |
| Suitable composed definition | `f1|f2` ending in a `Function` | `f1|f2|consumer` ending in a `Consumer` |
| EIP relation | Typically acts as a message/payload transformer | Typically corresponds to a consuming endpoint / service activator |
| Purpose | Process and pass downstream | Process and terminate |

**Key point:** `apply` is not syntactic sugar for `Function.apply(...)` on an arbitrary Java object. Here it is a **DSL operator** that takes a *definition name*, uses the catalog to locate the function, and integrates it into message processing.

## 3. Dependencies and Runtime Requirements

The `spring-cloud-function-integration` module was introduced in **Spring Cloud Function 4.0.3**. Your project needs compatible SCF, Spring Integration, and Spring Boot versions.

### 3.1. Maven

Example snippet in `pom.xml`, assuming a Spring Cloud BOM and Spring Boot dependency management are already configured in the project:

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

Dependencies are declared without explicit versions here because the example assumes proper BOM management in the project. If you specify versions manually, verify compatibility rather than mixing major versions.

### 3.2. Gradle

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-function-integration'
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

### 3.3. Conditions for the DSL to Work

- Beans of type `Supplier`, `Function`, or `Consumer` are discovered by Spring and registered in the catalog.
- Spring can inject `FunctionFlowBuilder`.
- Names passed to `apply`/`accept` exist in the catalog and have matching interface types.
- The source channel exists or is created by Spring Integration configuration.
- Each function's output is compatible with the next function's input, including cases with payload conversion or message wrappers.

You do not need to manually instantiate `new FunctionFlowBuilder(...)` or implement `FunctionCatalog` in a typical Spring Boot application once auto-configuration is active.

## 4. Single Names vs. Composed Function Names

### 4.1. Calling by Single Name

Suppose the catalog contains:

~~~java
@Bean
Function<String, String> normalizeCode() {
    return value -> value.strip().toUpperCase(Locale.ROOT);
}

@Bean
Consumer<String> printCode() {
    return value -> System.out.println("Code: " + value);
}
~~~

Flow:

~~~java
return builder
        .from("codes.input")
        .apply("normalizeCode")
        .accept("printCode");
~~~

This corresponds to the catalog looking up `normalizeCode` and then `printCode` by name. However, the builder wires them into an **IntegrationFlow** and message-endpoint machinery; it does not simply execute two Java calls when Spring creates the bean.

### 4.2. Calling a Composition with `|`

SCF supports **declarative composition**. Given:

~~~text
trimCode     : Function<String, String>
uppercaseCode: Function<String, String>
classifyCode : Function<String, TicketDecision>
~~~

we can write:

~~~java
.apply("trimCode|uppercaseCode|classifyCode")
~~~

The logical flow is:

~~~text
String
  → trimCode → String
  → uppercaseCode → String
  → classifyCode → TicketDecision
~~~

The final output is still a `TicketDecision` value, so the chain fits `apply`. Composition happens inside `FunctionCatalog`; **it does not automatically create three message channels** between the three functions.

### 4.3. Composition Ending at a Consumer

With `Consumer<TicketDecision> captureDecision`:

~~~java
.accept("trimCode|uppercaseCode|classifyCode|captureDecision")
~~~

We get a chain that **takes a String input and returns no value**, because the final step is a consumer. This is the use case for `accept`.

~~~mermaid
flowchart LR
    A["Input String"] --> B["trimCode"]
    B --> C["uppercaseCode"]
    C --> D["classifyCode"]
    D --> E["captureDecision: Consumer"]
    E --> F["End"]
~~~

**Do not arbitrarily reverse composition order:** a `Consumer` has no output data to feed into a subsequent `Function`. A definition like `"captureDecision|uppercaseCode"` is not a valid `Function` chain.

### 4.4. Result Table by Function Type

| Composition | Logical Result | Suitable Operator |
| --- | --- | --- |
| `Function<A,B> | Function<B,C>` | `Function<A,C>` | `apply(...)` |
| `Function<A,B> | Consumer<B>` | `Consumer<A>` | `accept(...)` |
| `Supplier<A> | Function<A,B>` | `Supplier<B>` | Use a `Supplier`/`fromSupplier(...)` source or suitable adapter |
| `Supplier<A> | Consumer<A>` | `Runnable` | Not treated as a message-accepting `Function` for `apply(...)` |
| `Consumer<A> | Function<A,B>` | Cannot be composed in this order | Invalid |

Some data types can be converted by SCF via wrappers/converters, but **you should not rely on undocumented conversions**. In examples, keep input/output Java generic types explicitly compatible.

## 5. End-to-End Example: Classifying Support Ticket Codes

### 5.1. Requirements

An application receives ticket codes as strings through a `DirectChannel`. Rules:

1. Trim leading and trailing whitespace.
2. Convert the code to uppercase using `Locale.ROOT`.
3. Drop messages with an empty code.
4. Classify: codes starting with `VIP-` go to `EXPRESS`; all others go to `STANDARD`.
5. Record the final result into an internal queue for observation and testing.

We use:

- `trimCode`, `uppercaseCode`, and `classifyCode` as reusable `Function` beans.
- `captureDecision` as a `Consumer`.
- `filter(...)` as an EIP **Message Filter** between normalization and classification.
- `FunctionFlowBuilder.apply(...)` and `accept(...)` to invoke catalog names.

~~~mermaid
flowchart LR
    I["tickets.input"] --> A["apply(trimCode|uppercaseCode)"]
    A --> B{"filter: non-empty?"}
    B -->|Yes| C["apply(classifyCode)"]
    B -->|No| X["Drop message"]
    C --> D["accept(captureDecision)"]
    D --> O["Queue<TicketDecision>"]
~~~

### 5.2. Business Beans

Place `TicketFunctions.java` in package `example.ticket` (Java 17+):

~~~java
package example.ticket;

import java.util.Locale;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.function.Consumer;
import java.util.function.Function;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record TicketDecision(String code, String lane) {}

@Configuration
public class TicketFunctions {

    @Bean
    Function<String, String> trimCode() {
        return String::strip;
    }

    @Bean
    Function<String, String> uppercaseCode() {
        return text -> text.toUpperCase(Locale.ROOT);
    }

    @Bean
    Function<String, TicketDecision> classifyCode() {
        return code -> {
            if (code.isBlank()) {
                throw new IllegalArgumentException("Empty ticket code");
            }
            String lane = code.startsWith("VIP-")
                    ? "EXPRESS" : "STANDARD";
            return new TicketDecision(code, lane);
        };
    }

    @Bean("capturedDecisions")
    Queue<TicketDecision> capturedDecisions() {
        return new ConcurrentLinkedQueue<>();
    }

    @Bean
    Consumer<TicketDecision> captureDecision(
            @Qualifier("capturedDecisions")
            Queue<TicketDecision> decisions) {
        return decisions::add;
    }
}
~~~

These functions have no dependency on HTTP controllers, brokers, channel names, or how Spring Integration receives messages. They can also be invoked by an SCF adapter over HTTP, events, or serverless once the corresponding adapter is configured.

`captureDecision` is a consumer with a **side effect** (mutating a queue); in a real application, this step might persist to a database, write an audit log, or send results to another service. In those cases, appropriate error and idempotency policies are required.

### 5.3. Configuring IntegrationFlow

Place `TicketIntegration.java` in the same package:

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
                .apply("trimCode|uppercaseCode")
                .filter(String.class, code -> !code.isBlank())
                .apply("classifyCode")
                .accept("captureDecision");
    }
}
~~~

Reading the DSL in order:

1. `from("tickets.input")` connects the flow to a message channel.
2. `apply("trimCode|uppercaseCode")` looks up a **two-function composition**; the result is a `String`.
3. `filter(String.class, ...)` checks the normalized payload; empty messages are dropped according to filter policy.
4. `apply("classifyCode")` calls the function returning `TicketDecision`.
5. `accept("captureDecision")` sends the result to the consumer and terminates the flow.

In this configuration, `accept(...)` is the terminal operator, so **do not append `.get()` afterward**. The official Spring Cloud Function documentation also uses `.accept("consumerName")` as the terminating call when returning an `IntegrationFlow`.

### 5.4. Booting the Application

A Spring Boot application in the same or parent package to scan the beans:

~~~java
package example.ticket;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TicketApplication {
    public static void main(String[] args) {
        SpringApplication.run(TicketApplication.class, args);
    }
}
~~~

### 5.5. Sending a Test Message

In code with an `ApplicationContext context`:

~~~java
MessageChannel input =
        context.getBean("tickets.input", MessageChannel.class);

input.send(new GenericMessage<>("  vip-005  "));
~~~

Add imports for `org.springframework.messaging.MessageChannel` and `org.springframework.messaging.support.GenericMessage`.

With `DirectChannel` and the synchronous handlers in the example, after `send(...)`, the `capturedDecisions` queue receives:

~~~text
TicketDecision[code=VIP-005, lane=EXPRESS]
~~~

For the message `"   "`, `trimCode` returns an empty string, the filter drops the message, and `captureDecision` is never called. **The return value of `MessageChannel.send(...)` does not indicate "the ticket succeeded in business processing"**: it reflects sending/acceptance under the channel contract, while the message may have been filtered or handled separately downstream.

## 6. Three Ways to Combine apply and accept

Using the same functions from Section 5, you can choose among the structures below.

### 6.1. Each Function as Its Own apply Step

~~~java
@Bean
IntegrationFlow splitStepsFlow(FunctionFlowBuilder builder) {
    return builder
            .from("tickets.splitInput")
            .apply("trimCode")
            .apply("uppercaseCode")
            .filter(String.class, code -> !code.isBlank())
            .apply("classifyCode")
            .accept("captureDecision");
}
~~~

This is an **alternative variant**, requiring `tickets.splitInput` to be declared beforehand. Each function appears as a separate DSL step, allowing EIP operators to be inserted between them.

### 6.2. Composition in apply, Single Consumer at the End

~~~java
@Bean
IntegrationFlow composedApplyFlow(FunctionFlowBuilder builder) {
    return builder
            .from("tickets.composedApplyInput")
            .apply("trimCode|uppercaseCode")
            .filter(String.class, code -> !code.isBlank())
            .apply("classifyCode")
            .accept("captureDecision");
}
~~~

This is the structure of the main example, turning two adjacent transformation steps into a single composition. Functions inside a composition **do not create separate channels between themselves**.

### 6.3. Composition Ending with a Consumer in accept

~~~java
@Bean
IntegrationFlow composedAcceptFlow(FunctionFlowBuilder builder) {
    return builder
            .from("tickets.composedAcceptInput")
            .apply("trimCode|uppercaseCode")
            .filter(String.class, code -> !code.isBlank())
            .accept("classifyCode|captureDecision");
}
~~~

Explanation:

- `apply("trimCode|uppercaseCode")` returns `String`.
- The filter keeps valid strings.
- `accept("classifyCode|captureDecision")` invokes `Function<String,TicketDecision>` and then feeds `TicketDecision` into `Consumer<TicketDecision>`.

This clearly shows that `accept`'s argument **does not have to be just a single consumer name**; it can be a *composition* terminating in a consumer.

> The snippets in Section 6 are **independent implementation alternatives**, not meant to all be registered simultaneously in the same demo. Each option uses its own input channel; if multiple flows write to the same consumer/queue, distinguish event sources and avoid mixing test data.

### 6.4. Why Not Collapse Everything into One accept?

A shorter variant would be:

~~~java
return builder
        .from("tickets.allInOneInput")
        .accept("trimCode|uppercaseCode|classifyCode|captureDecision");
~~~

However, it is **not equivalent** to the demo because **the EIP Filter is gone**. Empty codes will enter `classifyCode` and raise `IllegalArgumentException` instead of being dropped by the filter.

If a check means "drop the message before proceeding," keep `filter(...)` or redesign the business contract intentionally. Do not remove necessary EIPs just to make a composition shorter.

## 7. Type Compatibility and Data Contracts

### 7.1. Checking Compatibility When Composing

Given definitions:

~~~text
f1: Function<A, B>
f2: Function<B, C>
c : Consumer<C>
~~~

we have:

~~~text
apply("f1|f2") → Function<A,C>
accept("f1|f2|c") → Consumer<A>
~~~

`f1`'s output must match or convert in a controlled way to `f2`'s input; `f2`'s output must be compatible with consumer `c`.

Example of a contract mismatch:

~~~java
Function<String, Integer> parseAmount = Integer::parseInt;
Function<OrderRequest, String> formatOrder = OrderRequest::id;

// You cannot expect Integer to automatically turn into OrderRequest:
.apply("parseAmount|formatOrder")
~~~

Adding a converter can resolve certain cases, but do not assume SCF automatically understands every domain data structure. Choose explicit signatures and test actual compositions.

### 7.2. Which Definitions Work with Which Operator?

| Definition Passed In | `apply` | `accept` |
| --- | --- | --- |
| `"uppercaseCode"` (Function) | Suitable | Not suitable without a trailing Consumer |
| `"uppercaseCode|classifyCode"` (Ends in Function) | Suitable | Not suitable while the chain still returns a value |
| `"captureDecision"` (Consumer) | Not suitable | Suitable |
| `"classifyCode|captureDecision"` (Ends in Consumer) | Not suitable | Suitable |
| `"supplierName"` (Supplier) | Not suitable as an input-taking Function | Not suitable as an input-taking Consumer |
| `"consumer|function"` | Invalid | Invalid |

Depending on the version, type mismatches may surface when building the flow, during lookup, or when a real message passes through the endpoint. Therefore, verify names and types in Spring context tests rather than relying solely on compilation.

### 7.3. Difference Between Java `Function.andThen` and SCF Composition

In plain Java:

~~~java
Function<String, String> trim = String::strip;
Function<String, String> upper =
        value -> value.toUpperCase(Locale.ROOT);

Function<String, String> combined = trim.andThen(upper);
~~~

In SCF:

~~~java
Function<String, String> combinedFromCatalog =
        catalog.lookup("trimCode|uppercaseCode");
~~~

The difference is that SCF enables composition by registered **function names**, while catalog wrappers can provide framework-level conversion and message handling. Both remain **transformation pipelines**, not brokers, transactions, or standalone EIPs.

## 8. Interleaving EIPs Between Function Calls

One advantage of `FunctionFlowBuilder` is that you can continue using Spring Integration operators.

| EIP | Typical Position | Example Purpose |
| --- | --- | --- |
| **Message Filter** | After `apply("normalize...")` | Drop empty messages or those failing a predicate. |
| **Content-Based Router** | After `apply("classify...")` | Send messages to channels based on `lane` or `tier`. |
| **Wire Tap** | Before/after a step to observe | Copy messages for audit/debugging without altering the main payload. |
| **Message Channel** | Between steps or at boundaries | Carry messages; channel type governs sync/async/buffering. |
| **Splitter / Aggregator** | When one message must split into many and later recombine | Requires correlation, release strategy, timeout, and state. |
| **Error Channel** | Where an endpoint/adapter supports error flows | Handle failures according to operational contracts. |

Example replacing the terminal consumer with a router:

~~~java
@Bean
IntegrationFlow routingFlow(FunctionFlowBuilder builder) {
    return builder
            .from("tickets.routingInput")
            .apply("trimCode|uppercaseCode")
            .filter(String.class, code -> !code.isBlank())
            .apply("classifyCode")
            .route(TicketDecision.class, TicketDecision::lane,
                    mapping -> mapping
                            .channelMapping("EXPRESS", "tickets.express")
                            .channelMapping("STANDARD", "tickets.standard"))
            .get();
}
~~~

This snippet requires `tickets.routingInput`, `tickets.express`, and `tickets.standard` channels along with downstream handlers. It is a **separate example** illustrating an EIP Router, not a mandatory piece of the Section 5 demo. `classifyCode` only computes `TicketDecision`; the router chooses the destination channel.

**Watch out for where `accept` sits:** once a flow terminates at a consumer, there is no reply payload left to pass to a router. If you need to route on the result, place a value-returning `apply` before the router, and put consumers/handlers at the end of each branch.

## 9. Using apply/accept After fromSupplier

`FunctionFlowBuilder` also supports `fromSupplier("supplierDefinition")`. In this model, the source actively produces data and Spring Integration typically invokes it via a poller:

~~~java
@Bean
Supplier<String> ticketSource() {
    return () -> "VIP-PULSE";
}

@Bean
IntegrationFlow supplierFlow(FunctionFlowBuilder builder) {
    return builder
            .fromSupplier("ticketSource",
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(1000)))
            .apply("trimCode|uppercaseCode")
            .accept("classifyCode|captureDecision");
}
~~~

Import `java.util.function.Supplier` and `org.springframework.integration.dsl.Pollers`. This snippet shows an alternative flow. Because the supplier always returns `"VIP-PULSE"`, the consumer receives the same message on schedule; this intentionally demonstrates a periodic source and is **unsuitable if each ticket must be processed only once**.

Relationships:

- `fromSupplier("ticketSource")` finds the `Supplier` in the catalog to create the source.
- `apply(...)` receives each scheduled payload and produces a result.
- `accept(...)` consumes the result at the end.
- Polling cadence, messages per poll, lifecycle, and error handling belong to the endpoint/poller, not to `Supplier.get()` itself.

If the `Supplier` pops and deletes items from a queue or database, a downstream failure can lose an item before processing finishes. Design acknowledgements/checkpoints, transactions, or redrive mechanisms per production requirements.

## 10. Payloads, Message Headers, and Data Conversion

### 10.1. Payload vs. Message

Spring Integration passes messages conceptually structured as:

~~~text
Message<String>
  payload: "  vip-005  "
  headers:
    id: ...
    timestamp: ...
    traceId: "trace-005"   (if present)
~~~

A `Function<String,String>` such as `trimCode` only needs business content. When using `apply("trimCode")`, the catalog wrapper and integration endpoint coordinate invocation according to the function signature.

When you need access to metadata, explicitly declare a function accepting `Message<T>`:

~~~java
@Bean
Function<Message<String>, Message<String>> markProcessed() {
    return message -> MessageBuilder.fromMessage(message)
            .setHeader("processingStage", "NORMALIZED")
            .build();
}
~~~

Import `org.springframework.messaging.Message` and `org.springframework.messaging.support.MessageBuilder`.

Do not automatically compose `Function<Message<String>, Message<String>>` with `Function<String,TicketDecision>` and assume every header always survives unchanged. **Test the actual results at each adapter and wrapper boundary**; transport headers such as acknowledgement or partition headers follow their own rules.

### 10.2. JSON, byte[], and POJOs

Having `Function<OrderRequest, RoutingDecision>` does not mean any JSON string input can enter the flow without conversion:

~~~text
Kafka/HTTP bytes or JSON string
    → [appropriate deserializer / message converter]
    → OrderRequest
    → apply("validateOrder|classifyOrder")
    → RoutingDecision
~~~

Content type, generic signatures, converters on the classpath, and adapter settings determine how conversion works. A passing `Function.apply(POJO)` unit test does not prove production can ingest JSON properly; test at the message and adapter boundaries.

### 10.3. Reactive Functions

SCF also supports `Function<Flux<T>, Flux<R>>`. Its input is **a publisher**, not a single `T` payload. Do not assume that:

~~~java
.apply("reactiveFunction")
~~~

will automatically turn every `T` message into a `Flux<T>` subscription as expected across every version and flow type.

When using reactive endpoints/channels, understand subscriptions, backpressure, multi-element emission, completion signals, and error propagation. Design an explicit reactive flow and test how `Flux` maps to messages rather than borrowing assumptions from the imperative `String → TicketDecision` example.

## 11. Errors, Retries, and Terminal Semantics

Several errors can occur:

| Scenario | Symptom | Remediation |
| --- | --- | --- |
| No function named `trimCode` | Builder/catalog cannot look up the required definition. | Verify bean name, component scanning, auto-configuration, and version. |
| `apply("captureDecision")` | A consumer does not fit an operator expecting a value-returning Function. | Use `accept("captureDecision")`. |
| `accept("classifyCode")` | A function produces output rather than acting as a terminal consumer. | Use `apply("classifyCode")` followed by `accept("captureDecision")`. |
| `apply("classifyCode|trimCode")` | Output type `TicketDecision` does not match `trimCode`'s `String` input. | Arrange order and types properly. |
| Payload type mismatch or missing converter | `ClassCastException`, conversion error, or validation failure. | Check the input contract and adapter converters. |
| Empty code dropped by filter | No output at the consumer; may be valid behavior. | If auditing is needed, configure a discard channel or tracking. |
| Consumer DB write fails | Exception at the terminal endpoint; item may already be consumed at the source. | Bounded retry, idempotency, and infrastructure-appropriate DLQ/error flow. |
| Message processed twice | Retry/redelivery or multiple bindings/flows. | Inspect flow paths and idempotency keys. |

### 11.1. Exception Propagation Path

With the synchronous `DirectChannel` in the example, an exception from a function or consumer usually propagates along the message sender's call stack. With `ExecutorChannel`, polling endpoints, or broker adapters, when and where errors are handled can differ; configure an error channel, retry advice, binder retry, or DLQ appropriate for your real infrastructure.

**`apply` and `accept` do not automatically guarantee retries, exactly-once delivery, or distributed transactions.** Composition likewise does not guarantee rollback if a consumer already performed a side effect before a later step fails.

### 11.2. Boundary Observability

You can place `.log(...)` or `wireTap(...)` in the flow to trace messages. However, logging business data must avoid exposing sensitive information, and logging inside a composition such as `"f1|f2"` does not appear as a standalone EIP endpoint. If you need per-step latency or error metrics, consider splitting each function into its own `apply` step or instrumenting inside the function with an appropriate observability mechanism.

## 12. Testing: Functions, Catalog, and IntegrationFlow

### 12.1. Unit Testing Business Logic

No need to boot Spring:

~~~java
TicketFunctions functions = new TicketFunctions();

String normalized = functions.uppercaseCode()
        .apply(functions.trimCode().apply(" vip-005 "));

TicketDecision decision =
        functions.classifyCode().apply(normalized);

assertEquals("VIP-005", decision.code());
assertEquals("EXPRESS", decision.lane());
~~~

Requires JUnit 5 and static import `org.junit.jupiter.api.Assertions.assertEquals`. Add cases for `" normal-006 "` → `STANDARD` and `"   "` → empty string after normalization. This unit test does not verify the EIP Filter, because the filter lives in `IntegrationFlow`.

### 12.2. Testing Lookup/Composition

In a Spring context with `FunctionCatalog`:

~~~java
@Autowired
FunctionCatalog catalog;

@Test
void shouldComposeFunctionsByName() {
    Function<String, TicketDecision> pipeline =
            catalog.lookup("trimCode|uppercaseCode|classifyCode");

    assertNotNull(pipeline);

    TicketDecision result = pipeline.apply(" vip-005 ");
    assertEquals("VIP-005", result.code());
    assertEquals("EXPRESS", result.lane());
}
~~~

This test proves the names exist in the catalog and the composed chain is compatible on the chosen sample data. You can also test a composition ending in a consumer:

~~~java
Consumer<String> pipeline =
        catalog.lookup("trimCode|uppercaseCode|classifyCode|captureDecision");

assertNotNull(pipeline);
// When calling pipeline.accept(...), the result ends up in the consumer's queue.
~~~

This verifies the catalog, not that messages passed through channels, filters, routers, or adapters.

### 12.3. Integration Testing a Synchronous Flow

A Spring Boot test matching the demo configuration:

~~~java
package example.ticket;

import java.util.Queue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.GenericMessage;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(classes = TicketApplication.class)
class TicketFlowTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    @Qualifier("capturedDecisions")
    Queue<TicketDecision> capturedDecisions;

    @Test
    void shouldApplyCompositionAndAcceptResult() {
        capturedDecisions.clear();

        MessageChannel input =
                context.getBean("tickets.input", MessageChannel.class);
        input.send(new GenericMessage<>("  vip-005  "));

        TicketDecision result = capturedDecisions.poll();

        assertNotNull(result);
        assertEquals("VIP-005", result.code());
        assertEquals("EXPRESS", result.lane());
    }

    @Test
    void shouldFilterBlankTicket() {
        capturedDecisions.clear();

        MessageChannel input =
                context.getBean("tickets.input", MessageChannel.class);
        input.send(new GenericMessage<>("   "));

        assertTrue(capturedDecisions.isEmpty());
    }
}
~~~

With the demo's synchronous `DirectChannel` and queue consumer, you can read the result immediately after `send(...)`. If you switch to an executor, poller, or broker, tests need bounded waits and must avoid sharing queues/contexts across concurrent tests.

To test **`accept("classifyCode|captureDecision")`**, create the alternative flow from Section 6.3 with its own channel and assert the same output. That directly verifies a consumer-terminated composition rather than testing only a single function.

### 12.4. Properties to Verify When Wiring Real Adapters

- Does the input signature after JSON deserialization match the function's generic type?
- Are trace/correlation headers preserved at the observed output?
- Are business-invalid messages filtered, throwing exceptions, or routed to an error flow?
- When the consumer fails and the broker redelivers, is the side effect idempotent?
- Are multiple flows/bindings accidentally processing the same event?

## 13. Relationship to spring.cloud.function.definition

The familiar property:

~~~properties
spring.cloud.function.definition=trimCode|uppercaseCode|classifyCode
~~~

is typically used by SCF adapters or binders to select which function to invoke. Meanwhile:

~~~java
return builder
        .from("tickets.input")
        .apply("trimCode|uppercaseCode")
        .accept("classifyCode|captureDecision");
~~~

is **the configuration of a specific IntegrationFlow**. Both use the concept of catalog function definitions, yet they control different places:

- `spring.cloud.function.definition`: the component reading the property (such as an HTTP/broker adapter) picks which definition to activate.
- `apply(...)` and `accept(...)`: the Integration DSL itself specifies which functions run inside that flow.
- Channel `tickets.input` must have a sender or inbound adapter wired to it; the property does not create the channel or automatically connect a Kafka topic to it.

Thanks to this boundary separation, the same `trimCode`, `uppercaseCode`, or `classifyCode` beans remain reusable over HTTP, events, serverless, or a Spring Integration flow, while each environment maintains its own delivery and error contracts.

## 14. Common Misconceptions

1. **Using `apply("consumerName")`:** a consumer returns `void` and produces no result for the next step.
2. **Using `accept("functionName")` and expecting a reply:** `accept` is for terminating at a consumer; to return results, use `apply` and configure explicit output/request-reply handling.
3. **Confusing `|` with a Message Channel:** `"f1|f2"` is a catalog composition, not a message channel inserted between two functions.
4. **Composing incompatible generics:** `Function<A,B>` cannot be arbitrarily chained to `Function<C,D>` if `B` cannot convert to `C`.
5. **Collapsing the entire flow into accept and removing EIPs:** filters, routers, wire taps, splitters, and aggregators have independent behavior; keep them when business or operational requirements call for them.
6. **Putting transport logic inside pure functions:** a classification function does not need to know a Kafka topic name; the router/adapter is responsible for sending to the right place.
7. **Assuming FunctionCatalog handles retries automatically:** retries, DLQs, acknowledgements, transactions, and idempotency belong to endpoint/binder configuration and system design.
8. **Assuming every input automatically converts to a POJO:** you need testable serialization contracts, content types, and converters.
9. **Registering multiple experimental flows on the same input uncontrolled:** this can cause duplicate processing, shared writes to one queue, or ambiguity over which flow actually received the message.

## 15. Practice Exercises

1. Update `classifyCode` to a `Function<String, TicketDecision>` that adds a `REVIEW` lane for codes starting with `RISK-`. Use an EIP router to send the three decision types to three channels.
2. Write two independent configurations: one using `apply("trimCode").apply("uppercaseCode")` and one using `apply("trimCode|uppercaseCode")`. Compare the output payloads and where you can insert a `wireTap`.
3. Create a flow using `.accept("classifyCode|captureDecision")`. Write an integration test proving the consumer receives a `TicketDecision` from a `String` input.
4. Remove the demo's filter, send a whitespace-only message, and observe the failure in `classifyCode`. Add an intentional discard/error policy and explain the difference.
5. Replace the input channel with `fromSupplier` backed by a source queue. Test polling cadence, the case where the supplier returns `null`, and explain why unit testing functions directly cannot verify source lifecycle behavior.

## 16. Self-Assessment Questions

- Why is `apply("f1|f2")` appropriate when `f2` returns data, whereas `accept("f1|f2|c")` is appropriate when `c` is a consumer?
- Why is `Consumer|Function` an invalid order?
- Can you insert `filter(...)` between two functions inside the same `"f1|f2"` composition? If you want filtering, how must the flow be structured?
- At which layers are names passed to `from("channel")` and `apply("function")` resolved?
- When a message is dropped by a filter, why can't you rely on `send(...)` returning `true` to conclude the consumer processed it?
- If a consumer fails to write to the database after the source already popped the item, where would you place retry/idempotency logic?

## 17. References

- [Spring Cloud Function — Spring Integration Interaction](https://docs.spring.io/spring-cloud-function/reference/spring-integration.html): describes `FunctionFlowBuilder`, `FunctionFlowDefinition`, `apply`, and `accept`, along with an example composition ending in a consumer.
- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): `FunctionCatalog`, composition, data conversion, `Supplier`, `Function`, and `Consumer`.
- [Spring Integration — Java DSL](https://docs.spring.io/spring-integration/reference/dsl/java-basics.html): `IntegrationFlow` and how endpoints are structured.
- [Spring Integration — java.util.function Interfaces Support](https://docs.spring.io/spring-integration/reference/functions-support.html): interaction between Java functional interfaces and Spring Integration.

**Conclusion:** In `FunctionFlowBuilder`, `apply("name")` invokes a `Function` and keeps its output for the flow; `accept("name")` invokes a `Consumer` to terminate processing. Both understand **composed function definitions joined by `|`** via `FunctionCatalog`, provided data types and the trailing interface type match. Compose adjacent transformations when beneficial, keep needed EIPs in `IntegrationFlow`, and manage conversions, retries, headers, and adapters at the proper boundaries so one business logic implementation can be reused across HTTP, events, or serverless.
