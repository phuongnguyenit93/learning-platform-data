# Pipes and Filters Composed of Independent Processing Steps

## 1. Context and Objectives

In the **SPRING_INTEGRATION_PATTERN** module, we learn to implement **Enterprise Integration Patterns** with **Spring Integration** to build loosely coupled, extensible, and testable message flows. One of the most important foundations of integration architecture is **Pipes and Filters**: dividing a process into processing steps with distinct responsibilities and connecting them via data transfer channels.

For example, when an e-commerce system receives an order, it may need to **validate data → normalize → compute shipping information → persist the processing command**. If all this work sits inside one giant method, every change affects the same block of code. With Pipes and Filters, each step handles a clear responsibility and only needs to know the **input/output message contract**.

After this lesson, you will be able to:

1. Explain why Pipes and Filters consists of processing steps that can be developed, tested, and replaced relatively independently.
2. Distinguish the **architectural pattern's filter** from the specific **Message Filter** endpoint in Spring Integration.
3. Model a flow consisting of **Message**, **Channel**, **Endpoint**, and data transformation steps.
4. Implement a pipeline using **IntegrationFlow Java DSL**, understanding execution order and the synchronous/asynchronous nature of channels.
5. Design error handling, correlation, retry, idempotency, and observability for a multi-step pipeline.

## 2. What Is Pipes and Filters?

Pipes and Filters is an architectural pattern that organizes data processing along a path consisting of multiple steps:

- **Filter**: a component that receives input data, performs a clearly scoped task, and then produces output, discards data, or emits an error according to a contract.
- **Pipe**: a channel linking steps together, carrying data from the output of one step to the input of the next step.
- **Pipeline**: a path composed of multiple filters and pipes to achieve a business outcome.

~~~mermaid
flowchart LR
    S["Source: new order"] --> P1["Pipe 1"]
    P1 --> F1["Filter A<br/>Validate"]
    F1 --> P2["Pipe 2"]
    P2 --> F2["Filter B<br/>Normalize"]
    F2 --> P3["Pipe 3"]
    P3 --> F3["Filter C<br/>Create command"]
    F3 --> P4["Pipe 4"]
    P4 --> D["Target: processing system"]
~~~

**Independence** here does not mean the steps have no relationship. They have a **data relationship through a contract**, while avoiding direct dependencies on each other's internal structure and implementation. A step only needs to know **what message it receives**, **what result it produces**, and **what happens when it cannot process**.

For instance, the address normalization step does not need to know whether the persistence step uses JDBC, JPA, or calls REST. It only needs to output a valid payload for the next step to consume.

### 2.1. Two Meanings of “Filter” to Distinguish

In the **Pipes and Filters pattern**, the word *filter* has the broad meaning of a processing stage; a filter can **transform**, **validate**, **enrich**, or **forward** data.

In **Spring Integration**, **Message Filter** is a specific endpoint: it evaluates a condition and decides **whether to let the message proceed or discard it**; typically it does not transform the payload. Endpoints such as **Transformer**, **Service Activator**, and **Enricher** can all serve as a “step” in a Pipes and Filters architecture.

| Concept | Meaning | Example |
| --- | --- | --- |
| Architectural pattern filter | Any independent processing step in a pipeline | Normalize shipping address |
| Spring Integration Message Filter | Evaluates a predicate to pass through or reject | Drop orders with an invalid total amount |
| Transformer | Creates new message content/type from existing data | OrderReceived → DispatchCommand |
| Enricher | Supplements information into the payload or headers | Attach regional fulfillment warehouse name |
| Service Activator | Invokes business/application logic at an endpoint | Persist shipping command |
| MessageChannel | Transmits messages between endpoints | DirectChannel, QueueChannel |

Do not confuse **message filtering** with the **entire architectural pattern**. A pipeline consisting solely of Transformers and Service Activators can still be an implementation of Pipes and Filters.

## 3. Principles That Keep Steps Independent

### 3.1. A Step Should Have One Clear Responsibility

Separate actions that are likely to change for different reasons. For example:

| Step | Input | Responsibility | Output |
| --- | --- | --- | --- |
| Validate | OrderReceived | Check order ID, amount, required address | Valid OrderReceived or error/rejection |
| Normalize | Valid OrderReceived | Normalize province name and formatted data | NormalizedOrder |
| Map | NormalizedOrder | Create shipping command | DispatchCommand |
| Dispatch | DispatchCommand | Call adapter to persist command to target system | Completion or business error |

The **Normalize** step does not need to know about errors from the target database; the **Dispatch** step should not duplicate string normalization rules. Clear boundaries allow changing one step while minimizing edits to others.

### 3.2. Depend on Data Contracts, Not Directly on Each Other

Compare two approaches:

~~~java
// Tightly coupled: each step instantiates and calls the next step directly.
class CoupledOrderProcessor {
    void process(OrderReceived input) {
        NormalizedOrder order = new AddressNormalizer().normalize(input);
        DispatchCommand command = new DispatchMapper().map(order);
        new RemoteDispatchClient().send(command);
    }
}
~~~

In the example above, the processor class knows exactly how to instantiate and invoke each component. To swap the client, add a step, or run asynchronously, we have to modify the orchestration logic.

With Pipes and Filters, components only need to know the **input/output contract**. Spring Integration handles connecting the endpoints via channels and flow configuration:

~~~mermaid
flowchart LR
    A["OrderReceived"] --> F1["Validate"]
    F1 -->|"Message<OrderReceived>"| F2["Normalize"]
    F2 -->|"Message<NormalizedOrder>"| F3["Map"]
    F3 -->|"Message<DispatchCommand>"| F4["Dispatch"]
~~~

When changing normalization logic, we can modify and test Normalize independently as long as its output contract still matches Map.

### 3.3. Prefer Pure Transformations and Immutable Data

Transformation steps are easiest to test when **the output depends only on the input**, avoiding reading global state or mutating input objects. In Java, a **record** is useful for small data models; however, a record only makes the reference fields immutable, not any mutable objects nested inside.

~~~java
import java.util.Locale;

record OrderReceived(String orderId, String province) {}
record NormalizedOrder(String orderId, String provinceCode) {}

final class ProvinceNormalizer {
    NormalizedOrder normalize(OrderReceived input) {
        if (input == null || input.orderId() == null
                || input.province() == null) {
            throw new IllegalArgumentException("Missing required data");
        }
        return new NormalizedOrder(
                input.orderId().trim(),
                input.province().trim().toUpperCase(Locale.ROOT));
    }
}
~~~

This transformation does not depend on channels, databases, or networks. You can instantiate `ProvinceNormalizer` directly in a unit test and test many inputs without starting Spring.

Note: **uppercasing is not equivalent to an actual administrative province code**. This example only illustrates a string transformation. If business requirements need a valid province code table, use a lookup/mapping step with its own contract.

### 3.4. Error Contracts Are Part of the Step Contract

Each filter needs to clearly specify:

- When input is valid: does it return a payload of the same type, a new type, or nothing?
- When input is invalid: does it drop the message, send it to a discard channel, or throw an exception?
- When a transient error occurs: can the error be safely retried?
- Have any side effects already taken place before the error?

Without clear definitions, two steps that are independent in code can still integrate incorrectly from a business perspective.

## 4. Mapping the Architectural Pattern to Spring Integration

Spring Integration provides the building blocks to implement Pipes and Filters:

| Spring Integration Component | Role in the Pipeline |
| --- | --- |
| **Message<T>** | Wraps the payload and headers of data moving between steps |
| **MessageChannel** | Pipe carrying messages from the preceding endpoint to the next endpoint |
| **MessageHandler / endpoint** | Component that receives and processes messages |
| **Message Filter** | Lets a message proceed or rejects it based on a predicate |
| **Transformer** | Transforms the payload, and sometimes headers and message structure |
| **Header Enricher / Content Enricher** | Supplements metadata or data from another source |
| **Service Activator** | Invokes business services and may produce a result or terminate a branch |
| **Router** | Chooses the next path based on content/headers |
| **Splitter / Aggregator** | Splits and reassembles parts of a group of data |
| **Gateway** | Creates a call boundary from application code into a flow and receives replies when needed |
| **IntegrationFlow** | Declares the topology of steps and channels using the Java DSL |

With these abstractions, each endpoint can focus on handling a single step. The **message forwarding** rules reside in the flow configuration, making adding or removing a step clearer than a hardcoded call chain.

### Message and Headers

Messages passing through multiple steps carry:

1. **Payload**: business data; its type may change after a Transformer.
2. **Headers**: metadata such as `eventType`, `traceId`, `tenantId`, `correlationId`.

Each step must decide which headers to propagate forward. For example, a Transformer converting **OrderReceived** into **DispatchCommand** should keep `correlationId` for tracing, but may need to change `eventType` from **order.received** to **dispatch.requested**. Do not blindly propagate a routing hint that was only valid in a previous stage into the next stage.

**Message** is structurally immutable (there are no setters to change payload/headers), but if the payload contains a mutable object, that object can still be modified via another reference. Immutable data types or defensive copies keep steps more independent in asynchronous flows.

### “Pipe” Does Not Imply a Thread or a Queue

MessageChannel has different semantics:

| Channel | Characteristics | Consequences for the Pipeline |
| --- | --- | --- |
| **DirectChannel** | Dispatches synchronously to one selected handler, on the sender thread | Convenient for fast pipelines sharing the same call stack |
| **ExecutorChannel** | Delegates dispatching via an Executor | Decouples scheduling/thread; requires async error handling and resource limits |
| **QueueChannel** | PollableChannel backed by a queue | Decouples producer and consumer in time; requires a poller/receive |
| **PublishSubscribeChannel** | Broadcasts to multiple subscribers | Useful for fan-out branching; not a sequential chain |

If a DirectChannel has **three subscribers**, each message is normally delivered **to one subscriber selected by the dispatcher**, rather than running A then B then C. To build a pipeline A → B → C, you must **connect endpoints with channels in sequence**, or define the route using **IntegrationFlow**.

## 5. End-to-End Example: Order to Dispatch Command

Suppose an API receives an order placement event; the system needs to:

1. **Validate**: order ID must be non-empty, amount must be greater than 0, destination province must have a value.
2. **Normalize**: normalize the destination province string.
3. **Map**: convert the `OrderReceived` model to `DispatchCommand`.
4. **Dispatch**: persist the shipping command via a dedicated service.

~~~mermaid
flowchart LR
    API["Checkout API"] --> I["orderInputChannel"]
    I --> V{"Validate"}
    V -->|"Valid"| C1["validatedOrdersChannel"]
    V -->|"Invalid"| X["Exception / discard policy"]
    C1 --> N["Normalize"]
    N --> M["Map to DispatchCommand"]
    M --> C2["dispatchCommandsChannel"]
    C2 --> D["Dispatch service"]
~~~

### 5.1. Defining Models and Ports

Records represent the data contracts. A port for the final step decouples message processing from how data is actually persisted or sent.

~~~java
import java.math.BigDecimal;

record OrderReceived(
        String orderId,
        BigDecimal total,
        String destinationProvince) {}

record NormalizedOrder(
        String orderId,
        BigDecimal total,
        String destinationProvince) {}

record DispatchCommand(
        String orderId,
        BigDecimal declaredValue,
        String destinationProvince) {}

interface DispatchPort {
    void createDispatch(DispatchCommand command);
}
~~~

### 5.2. Independent Transformations

We group pure logic into small methods for easy unit testing. Each method has explicit input/output types and conditions.

~~~java
import java.util.Locale;

final class OrderSteps {
    private OrderSteps() {}

    static boolean isValid(OrderReceived order) {
        return order != null
                && order.orderId() != null
                && !order.orderId().isBlank()
                && order.total() != null
                && order.total().signum() > 0
                && order.destinationProvince() != null
                && !order.destinationProvince().isBlank();
    }

    static NormalizedOrder normalize(OrderReceived order) {
        if (!isValid(order)) {
            throw new IllegalArgumentException("Invalid order");
        }
        return new NormalizedOrder(
                order.orderId().trim(),
                order.total(),
                order.destinationProvince().trim()
                        .toUpperCase(Locale.ROOT));
    }

    static DispatchCommand toCommand(NormalizedOrder order) {
        return new DispatchCommand(
                order.orderId(),
                order.total(),
                order.destinationProvince());
    }
}
~~~

**Code-level independence**: `toCommand` does not call `normalize`, `normalize` does not call `DispatchPort`, and `isValid` does not depend on any database or channel. The flow decides the orchestration order of these steps.

### 5.3. Composing Steps with IntegrationFlow Java DSL

The following example uses Spring Integration Java DSL and Java 17+. The records, `OrderSteps`, and `DispatchPort` above reside in the same package as the flow configuration.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class OrderPipelineConfiguration {

    @Bean
    MessageChannel orderInputChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel validatedOrdersChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel dispatchCommandsChannel() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow orderToDispatchFlow(DispatchPort dispatchPort) {
        return IntegrationFlow.from("orderInputChannel")
                // Step 1: allow only valid orders to proceed.
                .filter(OrderReceived.class, OrderSteps::isValid,
                        filter -> filter.throwExceptionOnRejection(true))
                .channel("validatedOrdersChannel")
                // Step 2: normalize input data representation.
                .transform(OrderReceived.class, OrderSteps::normalize)
                // Step 3: convert to the shipping system's contract.
                .transform(NormalizedOrder.class, OrderSteps::toCommand)
                .channel("dispatchCommandsChannel")
                // Step 4: perform side effect at the application boundary.
                .handle(DispatchCommand.class, (command, headers) -> {
                    dispatchPort.createDispatch(command);
                    return null; // Terminal endpoint, emits no further message.
                })
                .get();
    }
}
~~~

In this example:

- **Filter** blocks invalid data; configuring **throwExceptionOnRejection(true)** causes rejections to raise an error instead of silently dropping the message.
- Two **Transformers** convert the payload across types **OrderReceived → NormalizedOrder → DispatchCommand**.
- **Service Activator** calls `DispatchPort` to perform the side effect.
- **DirectChannels** transfer messages synchronously between endpoints, making execution order observable through the call stack.
- A step can be added or replaced as long as it preserves the input/output types and semantics expected by the next step.

Explicit channel names help trace the flow. When named channel boundaries are not needed, the DSL can manage intermediate channels automatically. More important than naming are the **message contract** and the error path.

### 5.4. Sending Messages from a Producer

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;

@Component
class OrderPublisher {
    private final MessageChannel orderInput;

    OrderPublisher(
            @Qualifier("orderInputChannel") MessageChannel orderInput) {
        this.orderInput = orderInput;
    }

    void publish(OrderReceived order, String traceId) {
        if (order == null) {
            throw new IllegalArgumentException("Missing order");
        }

        Message<OrderReceived> message = MessageBuilder.withPayload(order)
                .setHeader("eventType", "order.received")
                .setHeader("correlationId", order.orderId())
                .setHeader("traceId", traceId)
                .build();

        boolean accepted = orderInput.send(message);
        if (!accepted) {
            throw new IllegalStateException("Failed to send order message");
        }
    }
}
~~~

**MessageBuilder** attaches metadata so a Router, error handler, or observability system can identify the event. In a production system, `traceId` and tenant context should come from authenticated context rather than being blindly accepted from untrusted input.

Because this flow runs over synchronous DirectChannels, the producer normally waits until the handlers finish processing. If `DispatchPort` throws an exception, the error can propagate back up the call stack; do not interpret **`send()` returning `true`** as a guarantee that all external side effects have been durably committed.

## 6. Independent Steps and Pipeline Ordering

Independence does **not** mean steps can be ordered arbitrarily. A pipeline has **data dependencies**:

~~~mermaid
flowchart LR
    A["Validate<br/>OrderReceived"] --> B["Normalize<br/>NormalizedOrder"]
    B --> C["Map<br/>DispatchCommand"]
    C --> D["Dispatch<br/>Side effect"]
~~~

If you swap Map and Normalize, Map will receive the wrong input type. If you place Dispatch before Validate, an invalid shipping command could be emitted before an error is detected.

Three types of dependencies can be distinguished:

| Type | Description | How to Reduce Coupling |
| --- | --- | --- |
| **Data dependency** | Output of the preceding step is input to the next step | Use explicit types/contracts and validation |
| **Technical dependency** | Step A directly instantiates/calls class B | Connect via channels or ports/interfaces |
| **Temporal dependency** | B must complete before C or can run later | Choose DirectChannel/ExecutorChannel/QueueChannel per requirements |

Independent steps generally make **development, logic deployment, and testing easier**, but if the entire flow runs inside the same application, they still share the process lifecycle and may share a transaction. Splitting into independently deployable services also requires network boundaries, serialization, versioned contracts, and reliable message delivery mechanisms.

### Naming by Behavior

A name like **normalizeProvince** or **convertOrderToDispatchCommand** clarifies function. Overly broad names like **processData** or **handleSomething** obscure responsibility and make error analysis harder.

### One Step, One Failure Mode

Validation errors differ from REST call errors. One way to distinguish them:

- **Invalid data:** do not retry indefinitely; return an error or route to an invalid-data handling flow.
- **External system temporarily unavailable:** can be retried with backoff and a retry limit.
- **Programming or message contract bugs:** must be logged, alerted on, and fixed in logic; continuous retries can cause overload.

## 7. Extending the Pipeline: Router, Splitter, and Aggregator

Pipes and Filters is often not just a single straight line. Spring Integration lets you branch or combine flows using other patterns:

~~~mermaid
flowchart LR
    IN["OrderReceived"] --> V["Filter: valid"]
    V --> R{"Router by region"}
    R -->|"Intra-city"| L["Local dispatch"]
    R -->|"Inter-province"| X["Remote dispatch"]
    L --> AUD["Audit event"]
    X --> AUD
~~~

**Router** decides which branch a message takes based on its payload or headers. With a Router, define a **default route** or an explicit policy when no branch matches. Do not assume a message is sent to multiple branches just because there are multiple output channels.

**Splitter** breaks a message containing a collection of items into multiple child messages; **Aggregator** reassembles them when a completion condition is met. When using these, pay attention to:

1. **Correlation ID**: identifies child messages belonging to the same group.
2. **Sequence number/size**: helps describe ordering and group size when used.
3. **Release strategy**: the condition for the Aggregator to emit a result.
4. **Timeout/message store**: manages incomplete groups and recovery after errors.

Correlation and sequence headers **do not by themselves guarantee** that messages are processed in order or never lost. That requires coordination across channels, endpoints, message stores, producers, and consumers.

**Gateway** can provide a method-call interface for application code outside the flow. For request/reply, you must define the reply path and timeout; a pipeline ending with a terminal endpoint that returns no result will not automatically satisfy a reply expectation.

## 8. Synchronous, Asynchronous, and Implications for Filters

Each pipe has its own semantics; changing a channel can significantly alter behavior without modifying the business logic inside each filter.

### 8.1. Synchronous Chain via DirectChannel

~~~mermaid
sequenceDiagram
    participant P as Producer / Thread T1
    participant C as DirectChannel
    participant F1 as Validate
    participant F2 as Normalize
    participant F3 as Dispatch
    P->>C: send(order)
    C->>F1: handleMessage
    F1->>F2: forward via next channel
    F2->>F3: forward via next channel
    F3-->>F2: return
    F2-->>F1: return
    F1-->>C: return
    C-->>P: send() completes
~~~

Advantages:

- Easy to reason about execution order for **a single send**.
- Synchronous exceptions can propagate to the caller.
- Can preserve thread-bound transactions if components share the same transaction manager.

Limitations:

- The caller must wait for all steps to finish.
- Slow handlers block the producer thread.
- Multiple producers can still run **concurrently**; DirectChannel does not guarantee global ordering across messages arriving from different threads.

### 8.2. Introducing an Asynchronous Boundary

Suppose the Dispatch step must call a slow API. You can place an **ExecutorChannel** or **QueueChannel** before this step:

~~~mermaid
flowchart LR
    P["Producer"] --> V["Validate"]
    V --> N["Normalize"]
    N --> Q["Async boundary<br/>Executor / Queue"]
    Q --> D["Dispatch"]
    D --> E["External API"]
~~~

What changes:

| Property | Synchronous via DirectChannel | Split via ExecutorChannel/QueueChannel |
| --- | --- | --- |
| Thread | Usually same sender thread | Can decouple thread or execution time |
| When `send()` returns | Usually after handlers complete | Can return before processing completes |
| Exception propagation to sender | Possible via call stack | Downstream errors need a separate handling path |
| Thread-bound transaction | Can continue within one call stack | Does not automatically propagate to worker/poller |
| Burst load resilience | No intermediate queue by default | Depends on capacity and configuration |
| Durability across restarts | Not provided automatically | ExecutorChannel is not durable; in-memory QueueChannel is also not durable |

**ExecutorChannel** delegates dispatching to an executor; any task queue belongs to the executor, so you need a bounded queue and a rejection policy. **QueueChannel** buffers messages and requires a consumer/poller to continue processing. Neither **automatically** guarantees exactly-once or durable delivery.

## 9. When a Filter Fails: Where Do Errors Go?

A good pipeline does not only have a happy path.

~~~mermaid
flowchart TD
    A["Input"] --> V{"Validate"}
    V -->|"Pass"| N["Normalize"]
    V -->|"Reject"| Q["Discard / business error"]
    N --> D["Dispatch"]
    D -->|"Success"| S["Completed"]
    D -->|"Transient failure"| R["Bounded retry"]
    R --> D
    D -->|"Persistent failure"| E["Error channel / DLQ per config"]
~~~

### 9.1. Filter Rejecting Data

A Message Filter can:

- **Drop the message** under the default policy in certain configurations, meaning downstream steps do not run.
- **Send to a discard channel** if you want to log or handle rejected cases.
- **Throw an exception** when configured with **throwExceptionOnRejection(true)**.

Choose based on business semantics. For example, dropping a duplicate event that was already successfully processed may be normal behavior; rejecting an order missing required fields usually requires a diagnosable error response.

### 9.2. Synchronous and Asynchronous Exceptions

In a DirectChannel chain, an exception from a handler usually propagates back up the call stack (possibly wrapped in a messaging exception). When crossing to an executor, poller, or asynchronous inbound adapter, exceptions may be routed via **ErrorMessage/errorChannel** depending on the endpoint type and error handler configuration. Never assume all errors automatically appear on the same error channel.

### 9.3. Retry and Idempotency

Suppose `DispatchPort` sent a shipping command to another system but lost the connection before receiving the response. Retrying could issue the command a second time.

Therefore, **retry does not equal safety**. Use an **idempotency key** (for example `orderId` combined with the operation type), unique constraints, or consumer-side deduplication. Bound the number of retries, add backoff, record the final failure, and provide a path for unprocessable messages.

### 9.4. Transactions Do Not Automatically Span Every Pipe

DirectChannel on the same thread can retain Spring's transaction context. However, HTTP calls, emails, or publishing to a broker do not automatically roll back when the application's database transaction rolls back.

When you need consistency between data updates and event emission, consider the **transactional outbox** pattern; when you need message recovery after a restart, consider a persistent message store or a broker with appropriate guarantees.

## 10. Observability: Knowing Which Steps a Message Passed Through

Pipes and Filters breaks large tasks into small steps, allowing you to monitor latency and errors **per endpoint**.

| Observability Data | Value |
| --- | --- |
| `correlationId` / business key | Links messages belonging to the same order |
| `traceId` | Connects logs and traces across steps/systems |
| Endpoint and channel names | Identifies which steps executed |
| Messages in/out/rejected counts | Tracks Filter drops and detects anomalies |
| Per-step processing duration | Pinpoints bottlenecks |
| Retry count and final error | Identifies recurring failure risks or stuck messages |
| Queue depth / message age | Monitors backlogs at asynchronous boundaries |

Note that **header values are not inherently trustworthy** if sent by an external system. `tenantId` must be authenticated; `traceId` should be propagated through proper observability mechanisms. Avoid logging full payloads and headers containing personal data, tokens, or sensitive information.

When observing a multi-branch pipeline, `correlationId` links items at the business level, while traces/spans identify execution timing and location. They complement each other rather than replacing processing confirmation mechanisms.

## 11. Testing Individual Steps and Testing the Whole Pipeline

Separating responsibilities creates two clear levels of testing:

**Unit tests** verify the logic of each filter/transformer using input-output assertions, with minimal Spring dependencies.

**Integration tests** verify that endpoints are actually wired properly: messages reach the right handlers, ordering holds for synchronous flows, required headers are preserved, and discard/error paths behave according to contract.

### 11.1. Unit Testing Normalization and Mapping Steps

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

class OrderStepsTest {
    @Test
    void normalizeAndMapWithoutStartingSpring() {
        OrderReceived input = new OrderReceived(
                " ORD-7 ", new BigDecimal("120000"), "  ha noi  ");

        assertTrue(OrderSteps.isValid(input));

        NormalizedOrder normalized = OrderSteps.normalize(input);
        assertEquals("ORD-7", normalized.orderId());
        assertEquals("HA NOI", normalized.destinationProvince());

        DispatchCommand command = OrderSteps.toCommand(normalized);
        assertEquals("ORD-7", command.orderId());
        assertEquals(new BigDecimal("120000"), command.declaredValue());
    }

    @Test
    void invalidAmountIsRejected() {
        OrderReceived input =
                new OrderReceived("ORD-8", BigDecimal.ZERO, "Ha Noi");

        assertFalse(OrderSteps.isValid(input));
        assertThrows(IllegalArgumentException.class,
                () -> OrderSteps.normalize(input));
    }
}
~~~

This test verifies the exact **single-step contract**, without needing channels or a database. If the normalization algorithm changes, we know which data types are affected.

### 11.2. Testing How Steps Connect via DirectChannel

The following example sets up three independent in-memory channels to verify dispatch order, header propagation, and that steps run on the sender thread. This is a **chaining mechanism test**, while production `IntegrationFlow` configurations still need to be tested in a dedicated Spring context.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class PipeChainTest {
    @Test
    void runsIndependentStepsInDeclaredOrder() {
        DirectChannel input = new DirectChannel();
        DirectChannel checked = new DirectChannel();
        DirectChannel output = new DirectChannel();

        List<String> visited = new ArrayList<>();
        AtomicReference<Message<?>> finalMessage = new AtomicReference<>();
        AtomicReference<Thread> consumerThread = new AtomicReference<>();
        Thread senderThread = Thread.currentThread();

        input.subscribe(message -> {
            visited.add("validate");
            String payload = (String) message.getPayload();
            if (payload.isBlank()) {
                throw new IllegalArgumentException("Empty");
            }
            checked.send(message);
        });

        checked.subscribe(message -> {
            visited.add("normalize");
            String normalized =
                    ((String) message.getPayload()).trim().toUpperCase();
            output.send(MessageBuilder.withPayload(normalized)
                    .copyHeaders(message.getHeaders())
                    .build());
        });

        output.subscribe(message -> {
            visited.add("handle");
            finalMessage.set(message);
            consumerThread.set(Thread.currentThread());
        });

        Message<String> sent = MessageBuilder.withPayload("  order-7  ")
                .setHeader("correlationId", "order-7")
                .build();

        assertTrue(input.send(sent));
        assertEquals(List.of("validate", "normalize", "handle"), visited);
        assertEquals("ORDER-7", finalMessage.get().getPayload());
        assertEquals("order-7",
                finalMessage.get().getHeaders().get("correlationId"));
        assertSame(senderThread, consumerThread.get());
    }

    @Test
    void aFailureStopsTheNextStep() {
        DirectChannel input = new DirectChannel();
        DirectChannel next = new DirectChannel();
        List<String> visited = new ArrayList<>();

        input.subscribe(message -> {
            visited.add("validate");
            throw new IllegalArgumentException("Invalid payload");
        });
        next.subscribe(message -> visited.add("should-not-run"));

        assertThrows(RuntimeException.class,
                () -> input.send(
                        MessageBuilder.withPayload("bad").build()));
        assertEquals(List.of("validate"), visited);
    }
}
~~~

Additional points to verify with a complete **IntegrationFlow**:

1. The Filter is configured to throw or discard as required.
2. Payloads and headers between Transformers have the right types and values.
3. The final service is not invoked if an early step rejects the message.
4. Retries do not create duplicate side effects when handlers call external systems.
5. When replacing a pipe with `ExecutorChannel`/`QueueChannel`, thread, timeout, backpressure, and error-handling tests are adjusted accordingly.

### Do Not Confuse Unit Tests with Operational Guarantees

Passing unit tests do not prove messages will survive a restart, do not prove distributed transactions, and do not prove exactly-once guarantees. Those requirements require integration testing with storage infrastructure, brokers, transactions, process restarts, and real failure scenarios.

## 12. When Is Pipes and Filters Appropriate?

This pattern fits well when:

- The work consists of a clear sequence of **transformation/validation steps**.
- Each step can be described by **input, output, and error states**.
- You need to change one step or add a new step with minimal impact on other parts.
- You want to observe or test results at each stage.
- You want to combine Enterprise Integration Patterns such as Filter, Transformer, Router, and Splitter/Aggregator.

This pattern has limitations when:

- A business process requires extensive shared global state or complex interactive coordination across many branches.
- Each step performs side effects without transaction, retry, and idempotency controls.
- Too many tiny steps increase topology, serialization, or logging complexity beyond the value gained.
- Long-running processes must wait for external events and manage state across restarts; in those cases a saga/process manager or workflow engine may also be needed.

**Independent steps** is a design principle, not a promise that every system can process steps in parallel or swap steps without considering data contracts.

## 13. Common Mistakes

| Mistake | Consequence | How to Avoid |
| --- | --- | --- |
| Treating Message Filter as the whole Pipes and Filters pattern | Ignores Transformer, Service Activator, and channel roles | Distinguish the architectural pattern from the endpoint |
| Registering all handlers on one DirectChannel expecting sequential execution | DirectChannel unicasts to a single selected subscriber | Use IntegrationFlow or chained channels |
| Letting one step directly invoke all remaining steps | Tight coupling, hard to swap and test | Separate stages; let flows/channels orchestrate |
| Letting each step arbitrarily alter headers | Broken correlation/routing downstream | Define a header contract and propagation rules |
| Sharing mutable payloads across multiple branches | Race conditions, unpredictable results | Immutable models or defensive copies |
| Letting Filter silently drop invalid data that needs feedback | Hard to diagnose rejection reasons | Configure intentional discard or exception handling |
| Inserting ExecutorChannel without reviewing transactions | Changes thread and error propagation paths | Design async boundaries, retries, and re-test |
| Retrying an entire flow with non-idempotent side effects | Duplicate orders, notifications, or shipments | Use idempotency keys and per-step retries |
| Treating in-memory QueueChannel as durable | Backlog can be lost on restart | Use a persistent message store or appropriate broker |
| Not measuring per-step latency and rejections | Blind to bottlenecks and message loss causes | Add metrics, tracing, and correlationId |

## 14. Practice Exercise: Building a Data Ingestion Pipeline

Design a flow that receives **ProductImported(productId, rawPrice, category)** data and produces a **CatalogCommand**.

**Requirements:**

1. **Validate:** `productId` and `category` must have values; `rawPrice` must be parseable as a positive number.
2. **Normalize:** normalize `category` according to a deterministic convention, e.g., trim and uppercase.
3. **Map:** create `CatalogCommand` with price typed as **BigDecimal**.
4. **Persist:** call `CatalogPort` to write to the target system.
5. **Observability:** preserve `correlationId` across the entire flow, recording each executed step.
6. **Error handling:** define behavior for malformed prices and for transient database errors.

Suggested architecture:

~~~mermaid
flowchart LR
    A["ProductImported"] --> V{"Validate"}
    V -->|"OK"| N["Normalize"]
    V -->|"Invalid"| E["Business error"]
    N --> M["Map to CatalogCommand"]
    M --> P["CatalogPort"]
    P -->|"Transient error"| R["Retry / DLQ per policy"]
~~~

**Extension**: suppose a product needs to update both the **search index** and the **audit log**. Decide whether to use a Router, PublishSubscribeChannel, or two sequential steps. The answer depends on whether **both branches must run**, whether they can **fail independently**, or whether they must **succeed within the same transaction**. If recovery after restarts is required, merely adding an internal PublishSubscribeChannel is not enough.

### Self-Check Questions

1. Under what contracts are “independent filters” defined in a Pipes and Filters architecture?
2. Why can a Spring Integration Transformer still be considered a filter in the architectural sense?
3. What is the difference between a data dependency and a direct implementation dependency?
4. What changes when adding an ExecutorChannel before the Persist step?
5. When should a rejecting Filter throw an error versus discard the message?
6. Why do `correlationId` and an idempotency key serve different roles?
7. Is a flow with many small steps always easier to maintain than a short flow? State the conditions.

## 15. Checklist for Designing an Extensible Pipeline

- Each step has **one primary responsibility** and a concrete input/output contract.
- Payload types and required headers are clearly documented.
- Relationships between filters are not hardcoded through unnecessary direct instantiation or calls.
- Paths for valid messages, discarded messages, and error messages are explicitly configured.
- DirectChannel/ExecutorChannel/QueueChannel are chosen based on the semantics of each boundary.
- Ordering, concurrency, transaction, durability, and backpressure requirements are defined.
- Any side effects subject to retry are reviewed for idempotency.
- Unit tests cover pure steps and integration tests cover flow topology.
- Traces/correlation, latency, retries, and rejection rates are monitored per endpoint.

**Conclusion:** Pipes and Filters enables building processes from processing steps that are **independent in responsibility and implementation**, connected through **message and channel contracts**. Spring Integration provides the tools to compose those steps with `IntegrationFlow`, from simple synchronous pipelines to branching, splitting/aggregating, or asynchronous flows. The overall reliability of the flow further depends on channel selection, error mechanisms, transactions, retries, and testing.

## References

- [Spring Integration Reference](https://docs.spring.io/spring-integration/reference/): Enterprise Integration Patterns components and flow building guides.
- [Spring Integration — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): IntegrationFlow, Transformer, Filter, and Service Activator in Java configuration.
- [Spring Integration — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): behavior of DirectChannel, ExecutorChannel, QueueChannel, and PublishSubscribeChannel.
- [Spring Framework — Integration](https://docs.spring.io/spring-framework/reference/integration.html): Spring's messaging and integration foundation.
