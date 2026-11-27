# FunctionFlowBuilder and fromSupplier

## 1. Why Do We Need FunctionFlowBuilder?

In the **Spring Cloud Function (SCF)** model, business logic is encapsulated in three Java function types:

- `Supplier<T>`: provides a value without taking any input arguments.
- `Function<T, R>`: transforms data from `T` to `R`.
- `Consumer<T>`: accepts `T` and performs a terminal action without returning a business result.

Functions are registered and looked up via `FunctionCatalog`. As a result, the same function can be reused across HTTP, message broker events, or serverless environments, provided the corresponding adapter is configured. SCF also supports *composition*: chaining functions by name, such as `normalize|classify`.

**Spring Integration** solves a different problem: connecting message sources and targets through channels, transformers, filters, routers, splitters, aggregators, polling adapters, and error flows. Those components implement **Enterprise Integration Patterns (EIP)** within an `IntegrationFlow`.

Since Spring Cloud Function **4.0.3**, the `spring-cloud-function-integration` module adds **`FunctionFlowBuilder`**: an entry point for the Spring Integration Java DSL already wired to `FunctionCatalog`. Instead of writing boilerplate code to look up each function and connect it to endpoints manually, a flow can reference functions **by name**.

In particular, `fromSupplier(...)` turns a `Supplier` in the catalog into a **message-producing source** for an `IntegrationFlow`.

~~~mermaid
flowchart LR
    A["FunctionCatalog"] -. "lookup by name" .-> B["FunctionFlowBuilder"]
    S["Supplier&lt;T&gt;"] --> A
    F["Function&lt;T,R&gt;"] --> A
    C["Consumer&lt;R&gt;"] --> A
    P["Poller"] --> E["SourcePollingChannelAdapter"]
    B --> E
    E --> I["Message in IntegrationFlow"]
    I --> X["apply(...): Function"]
    X --> Y["EIP: filter / router / wireTap"]
    Y --> Z["accept(...): Consumer"]
~~~

This lesson focuses on **`FunctionFlowBuilder` and `fromSupplier`**: configuration, polling cadence, data flow, composition, testing, and common pitfalls. It is part of the **Spring Integration** chapter within Spring Cloud Function and does not require a broker or serverless runtime.

### After This Lesson, You Will Be Able To

1. Explain the difference between `fromSupplier("name")` and `from("channel")`.
2. Distinguish `FunctionFlowBuilder` from `FunctionFlowDefinition` and explain the role of `FunctionCatalog`.
3. Build a flow with a `Supplier` source, `Function` steps, an EIP Filter, and a `Consumer`.
4. Configure `Pollers.fixedDelay(...)`, understand `maxMessagesPerPoll`, and explain what a `null` return from the source means.
5. Test an asynchronous poller-driven flow, identify data-loss points, and choose error-handling strategies.

## 2. Layers of Responsibility

To understand `fromSupplier`, first separate **a function that produces data** from **the mechanism that decides when to invoke that function**.

~~~text
Data source or internal queue
            │
            ▼
Supplier<T> registered in FunctionCatalog
            ▲
            │ get() invoked on schedule
            │
SourcePollingChannelAdapter + Poller
            │
            ▼
    Spring Integration Message
            │
            ▼
     apply("transformName")
            │
            ▼
  filter / route / channel / ...
            │
            ▼
     accept("consumerName")
~~~

| Component | Responsibility | What Not to Infer |
| --- | --- | --- |
| `Supplier<T>` | Returns the next element, such as an order to process. | Does not define scheduling, retries, transactions, or acknowledgements. |
| `FunctionCatalog` | Manages functions, suppliers, and consumers; supports name-based lookup and composition. | Is not a message broker or a message store. |
| `FunctionFlowBuilder` | Builds a DSL flow referencing catalog functions, including `fromSupplier`. | Does not automatically enable HTTP/Kafka/serverless adapters. |
| `FunctionFlowDefinition` | The DSL continuation after declaring a source; adds `apply` and `accept` alongside Integration DSL operators. | Does not replace Spring Integration filters, routers, or aggregators. |
| `SourcePollingChannelAdapter` and `Poller` | Periodically polls the source and emits messages into the pipeline as configured. | Does not inherently guarantee exactly-once delivery or source data recovery. |
| `Consumer<T>` | Terminal processing step that may store or dispatch data. | Does not return a payload to continue a chain like `Function<T,R>`. |

**Key distinction:** a `Supplier` in SCF only describes *how to create or fetch data*. When placed into `fromSupplier(...)`, **Spring Integration** supplies the lifecycle of a polling message source.

## 3. Dependencies and Version Scope

### 3.1. Maven

In a Spring Boot application managing versions via a compatible Spring Cloud BOM:

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

The snippet above assumes the project already configures a Spring Boot parent/BOM and Spring Cloud dependency management. Do not arbitrarily pin a `spring-cloud-function-integration` version separate from your SCF release train. If an existing starter or adapter already pulls Spring Integration onto the classpath, inspect your actual dependencies before adding duplicates.

### 3.2. Gradle

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-function-integration'
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Like Maven, this requires matching Spring Boot and Spring Cloud version management.

### 3.3. Key Imports

~~~java
import java.util.function.Supplier;
import java.util.function.Function;
import java.util.function.Consumer;

import org.springframework.cloud.function.integration.FunctionFlowBuilder;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
~~~

`FunctionFlowBuilder` comes from the **`spring-cloud-function-integration`** module. If an application only has `spring-cloud-function-context` and basic Spring Integration, you can look up `FunctionCatalog` manually, but this dedicated builder will not be available.

## 4. How Do FunctionFlowBuilder and FunctionFlowDefinition Work?

### 4.1. Function-Name-Based DSL

Minimal structural example:

~~~java
@Bean
IntegrationFlow exampleFlow(FunctionFlowBuilder builder) {
    return builder
            .fromSupplier("eventSource",
                    e -> e.poller(Pollers.fixedDelay(1000)))
            .apply("normalizeEvent")
            .accept("saveEvent");
}
~~~

Assume `FunctionCatalog` contains:

~~~text
eventSource   : Supplier<Event>
normalizeEvent: Function<Event, NormalizedEvent>
saveEvent     : Consumer<NormalizedEvent>
~~~

This DSL reads as:

1. `fromSupplier("eventSource", ...)`: looks up the supplier by name in the catalog and uses it as a polling source.
2. `apply("normalizeEvent")`: invokes the function on data emitted from the source.
3. `accept("saveEvent")`: passes the result to the terminal consumer.

This is an API illustration; running it requires declaring the corresponding beans. Function names are **definition names resolvable by the catalog**, not topic, queue, or message channel names.

### 4.2. Path of the Builder Object

Following the DSL structure:

~~~text
FunctionFlowBuilder
   └─ fromSupplier("eventSource", endpointConfigurer)
        └─ FunctionFlowDefinition
             ├─ apply("normalizeEvent")
             ├─ Spring Integration operators: filter, route, wireTap...
             └─ accept("saveEvent")  → IntegrationFlow
~~~

`FunctionFlowDefinition` extends `IntegrationFlowDefinition`/`IntegrationFlowExtension` to support function names. Therefore, you can interleave Spring Integration operators between function calls.

### 4.3. Commonly Used APIs

| API | Role | Example |
| --- | --- | --- |
| `fromSupplier("supplierName")` | Starts a flow using a catalog supplier and the configured default poller. | `.fromSupplier("pendingOrders")` |
| `fromSupplier("supplierName", e -> e.poller(...))` | Starts from a supplier and configures its endpoint/poller inline. | `.fromSupplier("pendingOrders", e -> e.poller(Pollers.fixedDelay(500)))` |
| `from("inputChannel")` | Starts a flow from a channel receiving messages sent externally or from another flow. | `.from("orders.in")` |
| `apply("functionName")` | Transforms the payload/message using a function fetched from the catalog. | `.apply("normalizeOrder")` |
| `apply("f1|f2")` | Composes compatible functions in the catalog. | `.apply("validate|classify")` |
| `accept("consumerName")` | Invokes a consumer to terminate the flow. | `.accept("storeOrder")` |
| `accept("f1|consumer")` | Composes a function with a terminal consumer using catalog composition. | `.accept("normalize|archive")` |

**Note on `fromSupplier("name")` without an endpoint configurer:** Spring Integration versions support this factory with the application context's **default poller**, and a default poller must be configured if you use that overload. When writing exercises or services with explicit data-fetch schedules, prefer the `e -> e.poller(...)` variant so the source has an explicit schedule.

**Do not confuse `from("channel")` with `fromSupplier("supplier")`:** a channel name is a destination that receives *pushed messages*, whereas a supplier name is a function *actively invoked by a poller*. Passing the same string into both methods means completely different things.

## 5. Hands-On: Polling Support Tickets from a Queue

### 5.1. Problem Statement

An application receives support ticket codes through an internal queue. Rather than building an entry flow directly from HTTP or Kafka, we simulate a pollable source:

~~~text
Queue<String> pendingCodes
  [" vip-101 ", "normal-202", "   "]
          │
          ▼
Supplier<String> pendingTicketSource
          │  invoked periodically by poller
          ▼
apply("normalizeTicket") → "VIP-101"
          │
          ▼
filter(non-empty code)
          │
          ▼
apply("classifyTicket")
          │
          ▼
TicketResult("VIP-101", "EXPRESS")
          │
          ▼
accept("captureTicket")
          │
          ▼
Queue<TicketResult> processedTickets
~~~

Business requirements:

- Normalize the ticket code by trimming whitespace and converting to uppercase.
- Drop codes that are empty after normalization.
- Codes starting with `VIP-` go to the `EXPRESS` lane; all others go to `STANDARD`.
- Record results in a queue for testing.
- Poll elements every 250 ms, at most one message per trigger.

### 5.2. Complete Example Code

Place the following code in `src/main/java/example/ticket/TicketFlowConfig.java`. This is a self-contained configuration example; it runs purely in memory and requires neither Kafka nor a database.

~~~java
package example.ticket;

import java.util.Locale;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.function.integration.FunctionFlowBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;

record TicketResult(String code, String lane) {}

@Configuration
public class TicketFlowConfig {

    @Bean("pendingCodes")
    BlockingQueue<String> pendingCodes() {
        return new LinkedBlockingQueue<>();
    }

    @Bean("processedTickets")
    BlockingQueue<TicketResult> processedTickets() {
        return new LinkedBlockingQueue<>();
    }

    @Bean
    Supplier<String> pendingTicketSource(
            @Qualifier("pendingCodes") BlockingQueue<String> pendingCodes) {
        // poll() is non-blocking; returns null when no item is available.
        return pendingCodes::poll;
    }

    @Bean
    Function<String, String> normalizeTicket() {
        return code -> code.strip().toUpperCase(Locale.ROOT);
    }

    @Bean
    Function<String, TicketResult> classifyTicket() {
        return code -> {
            if (code.isBlank()) {
                throw new IllegalArgumentException("Empty ticket code");
            }
            String lane = code.startsWith("VIP-")
                    ? "EXPRESS" : "STANDARD";
            return new TicketResult(code, lane);
        };
    }

    @Bean
    Consumer<TicketResult> captureTicket(
            @Qualifier("processedTickets")
            BlockingQueue<TicketResult> processedTickets) {
        return processedTickets::add;
    }

    @Bean
    IntegrationFlow ticketPollingFlow(FunctionFlowBuilder builder) {
        return builder
                .fromSupplier(
                        "pendingTicketSource",
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(250)
                                        .maxMessagesPerPoll(1)))
                .apply("normalizeTicket")
                .filter(String.class, code -> !code.isBlank())
                .apply("classifyTicket")
                .accept("captureTicket");
    }
}
~~~

Assume the Spring Boot application has an entry point in a parent package or `example.ticket` so Spring scans `TicketFlowConfig`:

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

You do not need to declare `@Bean FunctionCatalog` manually when compatible module auto-configuration is active. Spring injects `FunctionFlowBuilder` into `ticketPollingFlow` backed by the configured catalog.

### 5.3. Step-by-Step Analysis

**Data source**

~~~java
@Bean
Supplier<String> pendingTicketSource(
        @Qualifier("pendingCodes") BlockingQueue<String> source) {
    return source::poll;
}
~~~

`Supplier<String>` only states *how to obtain the next ticket code*. It does not create a scheduled task on its own. `BlockingQueue.poll()` removes and returns one item from the queue; when the queue is empty, it returns `null` immediately without blocking the thread.

**Source polling**

~~~java
.fromSupplier("pendingTicketSource",
        endpoint -> endpoint.poller(
                Pollers.fixedDelay(250).maxMessagesPerPoll(1)))
~~~

- `"pendingTicketSource"` is the supplier name in `FunctionCatalog`.
- `fixedDelay(250)` configures a 250 ms fixed delay between triggers.
- `maxMessagesPerPoll(1)` caps each poll cycle to at most one message from the source.
- For Spring Integration's polling source in this example, returning `null` from the supplier means that poll cycle has no message to pass downstream.

**Business processing**

~~~java
.apply("normalizeTicket")
.filter(String.class, code -> !code.isBlank())
.apply("classifyTicket")
~~~

The two `apply` calls invoke functions looked up by name. `filter` is Spring Integration's **EIP Message Filter**, deciding to drop empty messages after normalization. The filter condition is not a function that creates broker routes; it is a flow routing/filtering operator.

**Processing destination**

~~~java
.accept("captureTicket");
~~~

`captureTicket` is a `Consumer<TicketResult>` invoked after classification succeeds. A consumer emits no reply message to continue a pipeline. If you later need to return a result to an HTTP caller, design an appropriate request/reply flow or use a data-returning `Function` instead of a terminal `Consumer`.

### 5.4. An Illustrative Trace

~~~text
pendingCodes.add(" vip-101 ")
    ↓
[When the poller triggers]
pendingTicketSource.get()
    → " vip-101 "
    ↓
normalizeTicket.apply(...)
    → "VIP-101"
    ↓
filter: !code.isBlank() = true
    ↓
classifyTicket.apply(...)
    → TicketResult("VIP-101", "EXPRESS")
    ↓
captureTicket.accept(...)
    ↓
processedTickets contains 1 result
~~~

For a whitespace-only string, the normalization function returns an empty string and the filter drops the message. Because `pendingCodes.poll()` already removed the item from the queue, the filtered message is no longer in the source queue either. This is intentional for the exercise; production systems need a discard policy, audit storage, or dead-letter handling if dropped data must be tracked.

## 6. How the Poller Governs fromSupplier Behavior

### 6.1. Fixed Delay, Fixed Rate, and Max Messages Per Poll

Key options:

| Option | Meaning | When to Use |
| --- | --- | --- |
| `Pollers.fixedDelay(250)` | Waits a fixed delay between invocations; does not aim to stay aligned to fixed wall-clock ticks. | Steady data arrival where you want to pace load. |
| `Pollers.fixedRate(250)` | Schedules on a fixed-rate cadence; actual execution still depends on the scheduler and processing time. | Relatively regular cadence needed; must account for load/concurrency. |
| `maxMessagesPerPoll(1)` | Limits how many messages are fetched/processed in one poll cycle. | Prevent draining many consecutive items in a single trigger. |
| `Pollers.trigger(customTrigger)` | Uses a custom `Trigger` to determine poll times. | One-shot polling, business calendars, or complex conditions. |
| `taskExecutor(...)` / appropriate scheduler | Affects which thread executes depending on endpoint configuration. | Controlled concurrent processing. |

**Do not infer from `fixedRate` or `fixedDelay` that a supplier invocation is guaranteed to finish on schedule**. If downstream processing takes 5 seconds, the system must consider scheduler saturation, overlapping tasks, backlogs, timeouts, and ordering.

### 6.2. Why Shouldn't `get()` Return the Same Data Forever?

Example:

~~~java
@Bean
Supplier<String> staticTicket() {
    return () -> "VIP-ALWAYS";
}
~~~

When polled periodically, every `get()` call returns `"VIP-ALWAYS"`, so downstream steps receive **repeated identical messages**. That makes sense for a heartbeat or a quick demo, but causes duplicate processing if the data represents a one-time transaction.

A source needs clear semantics, such as:

- A queue: returns the next element and removes it from the queue.
- A database table: reads by cursor, checkpoint, or processing state.
- An external API: uses an ETag/offset/cursor or timestamp with rate limiting.
- A periodic emitter: intentionally generates a fresh event with a new identifier on each call.

### 6.3. When There Is No Data

A supplier returning `null` in a standard polling source indicates **no message is emitted in this cycle**. That is different from trying to send a message whose payload is `null`: Spring Messaging does not allow arbitrary `null` message payloads.

Example with a queue:

~~~java
Supplier<String> source = queue::poll;
String item = source.get();

if (item == null) {
    // Queue is empty, no new item in this cycle.
}
~~~

The flow remains active and the poller tries again on schedule until the endpoint is stopped. Do not let a supplier block indefinitely inside `get()`, as that can tie up a poller thread and complicate application shutdown. If using timed polling, design timeouts and cancellation properly.

### 6.4. Default Poller vs. Per-Endpoint Poller

The two forms below differ in configuration visibility:

~~~java
.fromSupplier("pendingTicketSource")
~~~

~~~java
.fromSupplier("pendingTicketSource",
        e -> e.poller(Pollers.fixedDelay(250).maxMessagesPerPoll(1)))
~~~

The first relies on Spring Integration's **default poller** in the application context according to the version/API in use. If no suitable default poller is configured, building the flow may fail or behave unexpectedly. The second places configuration directly on the endpoint and is usually clearer for tutorials or sources with custom schedules.

## 7. Composition: Applying Multiple Functions After fromSupplier

`FunctionCatalog` can compose functions using `functionA|functionB` syntax. In our example:

~~~text
normalizeTicket : Function<String, String>
classifyTicket  : Function<String, TicketResult>
captureTicket   : Consumer<TicketResult>
~~~

If no EIP operator is needed between the steps, you could write:

~~~java
@Bean
IntegrationFlow shortFlow(FunctionFlowBuilder builder) {
    return builder
            .fromSupplier("pendingTicketSource",
                    e -> e.poller(Pollers.fixedDelay(250)))
            .accept("normalizeTicket|classifyTicket|captureTicket");
}
~~~

**This is an alternative configuration for illustration** and should not be registered at the same time as `ticketPollingFlow` against the same supplier/queue in the demo, because two polling endpoints would compete for items. The trailing `Consumer` makes the entire chain a terminal consumption step, fitting `accept(...)`.

However, **the two versions are not functionally equivalent**: the original version has a `filter` that drops empty codes; the shortened version has no filter, so `classifyTicket` will throw an exception on empty strings. If the filtering policy must be preserved, keep a dedicated EIP Filter or intentionally adjust the function contract.

### 7.1. Do Not Confuse Composition with EIP

| Component | Result | What It Does Not Provide Automatically |
| --- | --- | --- |
| `apply("normalizeTicket|classifyTicket")` | A chain of functions with compatible input/output types. | Durable channels, per-step retries, Splitter/Aggregator. |
| `filter(...)` | Lets only messages matching a predicate continue. | Full business validation unless explicitly coded. |
| `route(...)` | Sends to an appropriate channel based on a routing key. | Automatically creating business rules in the catalog. |
| `wireTap(...)` | Copies messages to an observation/audit flow. | Persistent audit storage without a handler/store. |
| `fromSupplier(...)` | A poller-driven message source. | Broker acknowledgements, retries, or transactions. |

To add observation, for example:

~~~java
return builder
        .fromSupplier("pendingTicketSource",
                e -> e.poller(Pollers.fixedDelay(250)))
        .wireTap("tickets.auditChannel")
        .apply("normalizeTicket")
        .accept("captureText");
~~~

This **illustrates a different flow**: `tickets.auditChannel` must be configured with its own consumer, and `captureText` must be a registered `Consumer<String>`. Do not drop this directly into the demo without declaring the referenced components.

## 8. Distinguishing Imperative Suppliers from Reactive Suppliers

Spring Cloud Function supports both:

~~~java
Supplier<TicketResult> imperativeSupplier;
Supplier<Flux<TicketResult>> reactiveSupplier;
~~~

For an imperative `Supplier<T>`, each `get()` call can yield **one item** per poll cycle (depending on the source contract). `Supplier<Flux<T>>` provides a **Publisher**, which may represent a long-lived stream or multiple elements.

This affects how integration works:

1. A `Flux<T>` is a stream object, **not automatically one separate message per element**.
2. If you want each element fed individually into the flow, you need an appropriate reactive boundary or splitter, accounting for subscription, backpressure, and lifecycle.
3. A reactive supplier may be designed to emit one long-lived stream or finite streams per invocation. Choosing the right polling cadence depends on the source type.
4. Spring Cloud Function provides the `@PollableSupplier` annotation to indicate that a finite reactive source can be re-invoked; **this annotation does not create a scheduler on its own**. In an `IntegrationFlow`, polling/adapter settings must still be configured appropriately.

The Spring Cloud Function documentation shows an advanced example:

~~~java
return builder
        .fromSupplier("httpSupplier",
                e -> e.poller(Pollers.trigger(new OnlyOnceTrigger())))
        .<Flux<?>>handle((fluxPayload, headers) -> fluxPayload,
                e -> e.async(true))
        .channel(c -> c.flux())
        .apply("spelFunction")
        .<String, String>transform(String::toUpperCase)
        .accept("fileConsumer");
~~~

This is a **structural excerpt** for reading comprehension, not a standalone compilable sample: it requires `httpSupplier`/`spelFunction`/`fileConsumer` functions, imports, reactive components, and Spring Functions Catalog configuration. The key takeaway is how a *one-time polling source*, *async handler*, *flux channel*, and *functions* must work together. Do not take a `Supplier<Flux<T>>` and assume `apply("imperativeFunction")` will automatically split and process each element properly.

## 9. Message Payloads, Headers, and Type Conversion

A Spring Integration message consists of a **payload** and **headers**:

~~~text
Message<String>
  payload: " vip-101 "
  headers:
    id: ...
    timestamp: ...
    traceId: ... (if provided)
~~~

In the demo, `Supplier<String>` returns a string value. The source adapter wraps it into a message for the flow. `apply("normalizeTicket")` processes the payload according to its declared type. If you switch to `Supplier<Message<T>>` to attach headers, test which metadata is preserved across catalog wrappers, endpoints, and adapters.

Conceptual example creating a message at the source:

~~~java
@Bean
Supplier<Message<String>> sourceWithTrace() {
    return () -> MessageBuilder.withPayload("VIP-101")
            .setHeader("traceId", "run-042")
            .build();
}
~~~

Import `org.springframework.messaging.Message` and `org.springframework.messaging.support.MessageBuilder`. This configuration only illustrates a header-carrying contract; do not register an additional flow using this source without defining emission timing and idempotency.

**Important points:**

- `Supplier<String>` → `Function<String, TicketResult>` is a strongly typed chain; switching to JSON, byte arrays, or another POJO may require converters.
- `Function<Message<T>, Message<R>>` is allowed to read and create headers; a function taking only `T` should not depend on transport details.
- Headers for acknowledgements, partition keys, delivery attempts, or correlation IDs may be managed by the adapter/broker. Do not assume they stay untouched across every boundary.
- `FunctionCatalog` may apply conversions and wrappers; verify actual input/output types at the **IntegrationFlow boundary** instead of relying on unchecked casts.
- A `null` payload is not a valid message to send downstream; represent "no data yet" using the source's contract.

## 10. Testing Flows with Polling Sources

Unlike flows starting with `from("channelName")`, a `fromSupplier(...)` flow is **triggered by a scheduler**, so tests must wait for events with a clear timeout.

### 10.1. Unit Testing Functions

No Spring context is needed to test business logic:

~~~java
TicketFlowConfig config = new TicketFlowConfig();

String code = config.normalizeTicket().apply(" vip-101 ");
TicketResult result = config.classifyTicket().apply(code);

assertEquals("VIP-101", result.code());
assertEquals("EXPRESS", result.lane());
~~~

Add cases for `normal-202` → `STANDARD`; empty strings rejected by validation; whitespace strings dropped by the flow filter. Unit testing the functions does not verify polling schedules or the EIP Filter.

### 10.2. Bounded Integration Testing

Assuming `TicketApplication` is in the same package as `TicketFlowConfig` and the test uses JUnit 5:

~~~java
package example.ticket;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(classes = TicketApplication.class)
class TicketPollingFlowTest {

    @Autowired
    @Qualifier("pendingCodes")
    BlockingQueue<String> pendingCodes;

    @Autowired
    @Qualifier("processedTickets")
    BlockingQueue<TicketResult> processedTickets;

    @Test
    void shouldPollNormalizeAndClassify() throws InterruptedException {
        pendingCodes.clear();
        processedTickets.clear();

        pendingCodes.add("  vip-101  ");

        TicketResult result = processedTickets.poll(3, TimeUnit.SECONDS);

        assertNotNull(result, "No result received before timeout");
        assertEquals("VIP-101", result.code());
        assertEquals("EXPRESS", result.lane());
    }
}
~~~

**Why not call `processedTickets.poll()` immediately after `pendingCodes.add(...)`?** The poller runs on a schedule and may not have invoked the supplier yet. `poll(3, TimeUnit.SECONDS)` gives the test a bounded wait, avoiding timing flakiness in normal runs.

If multiple tests run concurrently or share the same Spring context/queues, isolate per-test state or start/stop endpoints per test. The queues in this example are shared beans—convenient for a demo, not a replacement for an isolated test harness.

### 10.3. Testing the Empty-Source Case

You can inspect counts before and after a short interval, but avoid writing `Thread.sleep(...)` tests solely to prove a scheduling policy. To test source logic, call `pendingTicketSource(...).get()` directly on an empty queue; to test the polling adapter, use metrics/spies or an integration test harness that controls the clock/scheduler to the level of determinism required.

### 10.4. Additional Test Cases to Cover

| Case | Expectation |
| --- | --- |
| Empty queue | No message reaches the consumer during the poll cycle. |
| `" vip-101 "` | One `TicketResult("VIP-101", "EXPRESS")` result. |
| `"normal-202"` | One `STANDARD` result. |
| `"   "` | Dropped by the filter; no `TicketResult` emitted. |
| Multiple consecutive items | Polled according to `maxMessagesPerPoll` and the configured cadence, without assuming concurrent processing. |
| `classifyTicket` throws an exception | Verify the poller's error path; ensure critical data is not silently lost. |
| Consumer fails to write data | Verify appropriate retry, idempotency, dead-letter, or compensation behavior. |

## 11. Errors, Retries, and Data Safety

In the demo, `pendingCodes.poll()` **removes the item from the queue before** normalize/classify/capture run. If the consumer later throws an error, the item is **not automatically put back into the queue**. Do not confuse having a poller with having durable delivery.

~~~mermaid
flowchart TD
    A["Supplier takes item from queue"] --> B["Function processes"]
    B --> C{"Succeeded?"}
    C -->|Yes| D["Consumer receives result"]
    C -->|Error| E["Error handler / retry policy"]
    E --> F{"Item recovery mechanism?"}
    F -->|Yes| G["Retry / store error / compensate"]
    F -->|No| H["Risk of data loss"]
~~~

| Failure | Handling Strategy to Consider |
| --- | --- |
| Wrong supplier/function/consumer name | Fail fast during flow startup; verify catalog names and dependencies. |
| Invalid input | Validate or filter; optionally route to a discard/audit channel and avoid infinite retries. |
| Dependent API temporarily failing | Bounded retry with backoff at the handler/adapter; avoid stalling the poller. |
| Source already removed item but downstream fails | Requires a transactional source, acknowledgements, or an appropriate recovery/redrive mechanism. |
| Duplicate events after retry/redelivery | Design an idempotent consumer keyed by a business identifier. |
| Incoming load exceeds processing capacity | Tune poller cadence, batch size, queue capacity, concurrency, and monitor backlogs. |
| Shutdown mid-processing | Define poller stop hooks, draining, checkpointing, and handling of in-flight items. |

**`fromSupplier(...)` alone provides no exactly-once guarantee.** With an in-memory queue, the application also loses queued data on process restart. In production, a durable stateful/acknowledged source or suitable broker solves this far better.

### 11.1. Where Do Retries Live?

Depending on the endpoint type, you can configure advice/error handlers on the polling adapter or downstream handlers. Spring Integration provides error channels and exception-handling mechanisms, yet **not every exception follows the same path**: synchronous sources, executors, reactive flows, and external adapters have different semantics.

A practical rule of thumb:

- **Data errors** (invalid ticket code) usually should not be retried endlessly.
- **Transient errors** (network blips or dependent API outages) can be retried with limits and backoff.
- **Unrecoverable errors** should be logged with context, stored in an error store, or routed to a dead-letter channel as required.
- For any retry or redelivery, consumers must prevent duplicate side effects using an idempotency key or appropriate transaction.

## 12. When Is fromSupplier Appropriate and When Should You Use Another Adapter?

| Scenario | Appropriate Choice | Reason |
| --- | --- | --- |
| Periodically reading jobs from an internal repository/queue | `fromSupplier("source", poller)` | The supplier encapsulates item retrieval while the flow runs on a clear cadence. |
| Emitting scheduled heartbeat or snapshot events | `fromSupplier` | The supplier actively generates data per call; define what duplicate events mean. |
| An inbound channel already receives messages from another flow | `builder.from("channelName")` | Messages are already pushed in; no need to poll a supplier. |
| Receiving HTTP requests and returning responses | An HTTP adapter or gateway | Requires request/reply semantics, status codes, serialization, and HTTP timeouts. |
| Consuming Kafka/RabbitMQ with ack/redelivery | Spring Cloud Stream binder or corresponding Spring Integration inbound adapter | Broker adapters handle protocol specifics, partitions, acknowledgements, and retries. |
| Using `Supplier<Flux<T>>` as a long-lived stream | A reactive flow/adapter with explicit subscription design | You should not poll repeatedly to spawn new streams if a single long-lived stream is intended. |
| Calling a plain function inside Java code | `FunctionCatalog.lookup(...)` then `apply(...)` | No need for an `IntegrationFlow` when there is no message-integration problem. |

Integrating with HTTP, events, and serverless is a benefit of **protocol-independent functions**, yet each environment still needs its own adapter. `fromSupplier` is **one message-source strategy for Spring Integration**, not a replacement for all those adapters.

## 13. Symptom-Based Troubleshooting

| Symptom | Cause to Check | Remediation |
| --- | --- | --- |
| Cannot inject `FunctionFlowBuilder` | Missing `spring-cloud-function-integration` or mismatched auto-configuration/versions. | Inspect dependency tree, release train, and auto-configuration beans. |
| Error saying `pendingTicketSource` is not found | Bean name mismatch, bean not scanned or not registered in the catalog. | Check `@Configuration`, `@Bean` method, and function name. |
| Flow bean exists but does not run | Missing poller or endpoint not started. | Use the `e.poller(...)` overload and check integration endpoint lifecycle. |
| Supplier is called repeatedly with no items | Queue is empty and supplier returns `null`. | Check producers writing to the queue and monitor backlog. |
| Supplier emits the exact same code continuously | Supplier always returns a constant or the same record. | Update source contract, cursor, or one-time emission condition. |
| Processing is slower than expected | Blocking downstream, busy scheduler, or suboptimal poller cadence. | Inspect latency, poll interval, max messages per poll, and executor. |
| `ClassCastException` or conversion error | Payload type differs from function signature, missing converter/content type. | Use explicit types and test conversion at flow entry. |
| `apply` finds the function but throws at runtime | Function throws an exception or receives invalid input. | Unit test the function and test catalog lookup separately. |
| Data disappears after an exception | Source removed the item from the queue before the consumer succeeded. | Design ack/retry/error-store or transactional retrieval. |
| Process shutdown loses backlog | Queue is purely in memory. | Move to a durable source if recovery guarantees are needed. |
| Trace header disappears | Wrapper/adapter/transformer builds a new message. | Use `Message<T>` when truly needed and test header preservation. |

### Extension Exercises

1. Replace `Supplier<String>` with `Supplier<OrderRequest>` and two functions that classify orders by total amount, keeping the same polling mechanism.
2. Add a **discard channel** for empty ticket codes instead of silently dropping them.
3. Try `maxMessagesPerPoll(3)` with ten items and measure supplier invocation counts when downstream processing is fast vs. slow.
4. Add a consumer that intentionally throws an exception for `VIP-FAIL`, observe queue behavior, and design a recovery mechanism.
5. Write a variant using `from("tickets.input")` to compare active polling against pushed messages.

## 14. Self-Assessment Checklist

- [ ] I can distinguish a data-producing supplier from a poller that decides when `get()` is invoked.
- [ ] I know `fromSupplier("name")` looks up a name **in the catalog**, whereas `from("name")` starts from a **channel**.
- [ ] I can explain why `FunctionFlowDefinition` adds `apply`/`accept` to the Integration DSL.
- [ ] I know when an explicit poller is needed and what `maxMessagesPerPoll` means.
- [ ] I do not confuse a `null` return from an empty supplier with a message carrying a `null` payload.
- [ ] I know composition only chains functions and does not automatically perform EIP filtering/routing/aggregation.
- [ ] I write bounded-wait tests because pollers run on a schedule rather than at send time.
- [ ] I have considered idempotency and recovery when the source consumes items before downstream succeeds.

## 15. Official References

- [Spring Cloud Function — Spring Integration Interaction](https://docs.spring.io/spring-cloud-function/reference/spring-integration.html): introduces the `spring-cloud-function-integration` module, `FunctionFlowBuilder`, `fromSupplier`, `apply`, `accept`, and reactive patterns.
- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): `Supplier`, `Function`, `Consumer`, `FunctionCatalog`, composition, and the `@PollableSupplier` annotation.
- [Spring Integration — java.util.function Interfaces Support](https://docs.spring.io/spring-integration/reference/functions-support.html): `Supplier`/`Function` support in `IntegrationFlow` and endpoints.
- [Spring Integration — IntegrationFlow Javadoc](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/dsl/IntegrationFlow.html): `fromSupplier` factory accepting a `Supplier` and polling configuration.

**Conclusion:** `FunctionFlowBuilder` enables Spring Integration to invoke business functions in `FunctionCatalog` by name. `fromSupplier(...)` is an especially important bridge: it turns a `Supplier<T>` into a poller-triggered message source that can then be chained with `apply`, EIP operators, and `accept`. This separation keeps Spring Cloud Function beans reusable across HTTP, events, or serverless, while leaving orchestration, scheduling, and error handling in the appropriate integration layer.
