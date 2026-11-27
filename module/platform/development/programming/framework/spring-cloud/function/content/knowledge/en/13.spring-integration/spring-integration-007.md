# Error Handling and Metadata at the Integration Flow Boundary

## 1. Why Care About Errors and Metadata?

**Spring Cloud Function (SCF)** encapsulates business logic with `Supplier<T>`, `Function<T,R>`, and `Consumer<T>`. Functions are looked up and composed through `FunctionCatalog` and can be reused across HTTP, event streams, serverless, or plain Java code. A signature like `Function<OrderSubmitted,OrderDecision>` expresses business computation, yet does not specify the data source, where outputs go, or how failures are handled.

**Spring Integration** connects those functions into an `IntegrationFlow` via Message Channels, Transformers, Routers, Pollers, Gateways, and other Enterprise Integration Patterns (EIP). At the **integration boundary**, the system needs not only valid payloads, but also knowledge of which request a message belongs to, who gets notified on failure, and whether data can be replayed.

Two themes run throughout this lesson:

1. **Metadata:** managing and propagating `traceId`, correlation IDs, `replyChannel`, `errorChannel`, `contentType`, and adapter/broker headers without polluting business logic.
2. **Error handling:** distinguishing exceptions propagated back to the caller during synchronous execution from failures turned into `ErrorMessage` instances when running through a poller, executor, or asynchronous integration mechanism.

After this lesson, you will be able to design a flow invoking `FunctionCatalog`, verify header preservation across transformers, inspect `ErrorMessage` payloads, classify business vs. infrastructure errors, and write boundary-appropriate tests.

~~~mermaid
flowchart LR
    A["HTTP / broker / serverless"] --> B["Adapter"]
    B --> C["Message: payload + headers"]
    C --> D["IntegrationFlow"]
    E["FunctionCatalog"] -. lookup .-> F["Business function"]
    D --> F
    F --> G["Consumer / outbound adapter"]
    F -. "synchronous error" .-> H["Caller / Gateway"]
    D -. "async or poller error" .-> I["ErrorMessage"]
    I --> J["errorChannel"]
    J --> K["Error handler / error store / DLQ"]
~~~

## 2. Distinguishing the Payload from the Message Envelope

A Spring Messaging `Message<T>` consists of a **payload** and **headers**. For example:

~~~text
Message<OrderSubmitted>
  payload:
    orderId = "DH-107"
    totalVnd = 1500000
  headers:
    id = ...
    timestamp = ...
    traceId = "trace-9a1"
    businessCorrelationId = "order-DH-107"
    replyChannel = ... (if using a request/reply gateway)
    errorChannel = ... (if an error destination is configured)
~~~

`Message<T>` is the contract in `org.springframework.messaging.Message`, and `MessageHeaders` holds metadata. A domain function accepting only `OrderSubmitted` sees the payload; a function accepting `Message<OrderSubmitted>` can inspect headers as well.

| Component | Responsibility | Examples |
| --- | --- | --- |
| Payload | Business data to process. | `OrderSubmitted(orderId,totalVnd)` |
| Business headers | Values used for correlation, event versioning, classification, etc. | `businessCorrelationId`, `schemaVersion` |
| Observability headers | Link traces/logs across services. | `traceId` or standard trace context |
| Spring Messaging headers | Message identity and reply/error destinations. | `MessageHeaders.ID`, `TIMESTAMP`, `REPLY_CHANNEL`, `ERROR_CHANNEL` |
| EIP metadata | Supports splitting/aggregating and message orchestration. | Correlation key, sequence number/size |
| Transport headers | Specific to HTTP, Kafka, RabbitMQ, or serverless runtime. | Partition, delivery attempt, acknowledgement |

**Do not use Spring Messaging's `id` header as a business idempotency key.** When a message is reconstructed, its ID can change even though it represents the same business transaction. Use a stable `eventId`, `orderId` plus event version, or an appropriate business key.

### 2.1. Creating a Message with Application Metadata

~~~java
Message<OrderSubmitted> message = MessageBuilder
        .withPayload(new OrderSubmitted(" dh-107 ", 1_500_000))
        .setHeader("traceId", "trace-9a1")
        .setHeader("businessCorrelationId", "order-DH-107")
        .build();
~~~

Required imports:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
~~~

Metadata can live in the envelope instead of adding `traceId` to every domain record. However, if a correlation ID is part of the domain itself and must be durably persisted, consider placing it in the payload or an appropriate storage model.

### 2.2. Which Headers Belong to the Framework?

Spring Integration uses `replyChannel` and `errorChannel` to coordinate replies and errors in supported contexts. Splitters/Aggregators may generate correlation and sequence headers. Broker adapters may carry acknowledgement handles, delivery tags, or partition metadata. Do not overwrite system metadata or forward all headers externally without understanding what they mean.

Metadata can be transformed or filtered when crossing adapters. An application-set header like `traceId` does not automatically enable full distributed tracing; tracing also depends on instrumentation and propagation configuration.

## 3. Preserving Metadata When Calling FunctionCatalog

Suppose the catalog manages:

~~~java
@Bean
Function<OrderSubmitted, OrderDecision> classifyOrder() {
    return order -> {
        // Validation and classification based on payload.
        return new OrderDecision(order.orderId(), "PRIORITY");
    };
}
~~~

You can look up and use the function as a transformer:

~~~java
Function<OrderSubmitted, OrderDecision> classify =
        catalog.lookup("classifyOrder");

return IntegrationFlow.from("orders.input")
        .transform(OrderSubmitted.class, classify::apply)
        .channel("orders.output")
        .get();
~~~

`transform(OrderSubmitted.class, ...)` receives the **payload**, produces a new output, and Spring Integration forwards an appropriate message downstream. Standard headers are normally carried across the transformer by framework mechanics. Even so, **do not assume every header is immutable** across all transformers, wrappers, message converters, and outbound adapters.

When a business function does not need metadata, keeping it payload-only makes it easy to reuse across HTTP, events, or serverless, while headers remain managed at the integration layer.

### 3.1. When a Function Needs the Full Message<T>

If you need to add a `processingStage` header:

~~~java
@Bean
Function<Message<OrderSubmitted>, Message<OrderSubmitted>> markStage() {
    return incoming -> MessageBuilder.fromMessage(incoming)
            .setHeader("processingStage", "VALIDATED")
            .build();
}
~~~

`MessageBuilder.fromMessage(...)` creates a new message from the incoming message with updated headers. For a function expecting the whole message, the invoking endpoint must pass the **envelope**, not just `message.getPayload()`. The Java DSL provides the `transform(Message.class, ...)` overload for whole-message processing.

Example of building a message-aware processor:

~~~java
Function<Message<OrderSubmitted>, Message<OrderSubmitted>> stage =
        catalog.lookup("markStage");

return IntegrationFlow.from("orders.markInput")
        .transform(Message.class, incoming -> {
            // Determine the exact payload type at the boundary.
            OrderSubmitted payload =
                    (OrderSubmitted) incoming.getPayload();

            Message<OrderSubmitted> typed = MessageBuilder
                    .withPayload(payload)
                    .copyHeaders(incoming.getHeaders())
                    .build();

            return stage.apply(typed);
        })
        .channel("orders.markOutput")
        .get();
~~~

This is an independent illustrative variant; its input and output channels must be configured. Rebuilding a message can change `id`/`timestamp`, so tests should assert headers **meaningful to the contract** rather than assuming all framework-generated metadata stays identical.

### 3.2. Controlling Headers Before Leaving the System

| Scenario | Approach |
| --- | --- |
| Internal transformer changes payload | Preserve trace/correlation headers required by the contract. |
| Sending requests to another service | Map only permitted headers, preferring an allowlist. |
| Splitter/Aggregator | Preserve or generate correlation/sequence headers per EIP rules. |
| Gateway request/reply | Ensure the reply path does not drop reply routing metadata. |
| Sending through a broker | Inspect header mappers, serializers, and exclude internal transport metadata. |
| Logging/auditing | Never log tokens, cookies, credentials, or sensitive payloads. |

Spring Integration offers `headerFilter(...)` to strip specific headers. However, dropping `replyChannel` or correlation metadata while downstream still relies on them can break replies or group aggregation.

## 4. Two Paths for Exceptions

There is no single `errorChannel` mechanism that applies uniformly to every endpoint type.

### 4.1. Synchronous DirectChannel

~~~mermaid
sequenceDiagram
    participant Caller
    participant Channel as DirectChannel
    participant Flow as IntegrationFlow
    participant Function
    Caller->>Channel: send(message)
    Channel->>Flow: synchronous dispatch
    Flow->>Function: apply(payload)
    Function--xFlow: throw exception
    Flow--xCaller: exception propagates up call stack
~~~

When a handler runs on the caller's thread via `DirectChannel`, exceptions usually propagate back to `send(...)` or the messaging gateway. They may be wrapped in `MessagingException` or a transformer-specific exception; gateways may unwrap the root cause per contract.

**Merely setting an `errorChannel` header or registering a global error channel does not automatically route all synchronous exceptions there.** If an HTTP endpoint or gateway needs an error response, the caller/adapter layer must map the exception or use an explicitly designed error flow policy.

### 4.2. Pollers and Asynchronous Processing

~~~mermaid
sequenceDiagram
    participant Scheduler as Poller / Executor
    participant Handler as Function / Handler
    participant Errors as MessagePublishingErrorHandler
    participant Channel as errorChannel
    participant Sink as Error subscriber
    Scheduler->>Handler: process message
    Handler--xScheduler: exception
    Scheduler->>Errors: pass to error handler
    Errors->>Channel: ErrorMessage(Throwable)
    Channel->>Sink: handle and observe
~~~

Spring Integration supports publishing failures as `ErrorMessage` instances. In contexts using `MessagePublishingErrorHandler`, the error destination is resolved similarly to replies: prioritizing the `MessageHeaders.ERROR_CHANNEL` header on the failing message when applicable, and falling back to the global channel named `errorChannel`.

Standard poller tasks use Spring Integration scheduler error publishing per framework configuration. If a project uses a custom scheduler or error handler, verify that error publishing remains wired properly. Some adapters and binders have their own error-handling pipelines.

| Context | Typical Behavior | Where Policy Belongs |
| --- | --- | --- |
| Synchronous `DirectChannel` | Exception propagates to caller. | Caller, gateway, HTTP exception handler. |
| Standard Poller | `ErrorMessage` may be published to an error channel. | Poller/error handler and error flow. |
| `ExecutorChannel` or async task | Sender may have moved on; an async error path is needed. | Channel/executor `errorChannel` and handler. |
| Kafka/RabbitMQ inbound | Ack, redelivery, retry, and dead-letter per binder/adapter. | Broker binding and consumer error policy. |
| Serverless event | Runtime/adapter governs timeout, retry, and error response. | Adapter and event-source configuration. |

## 5. Inside an ErrorMessage

`ErrorMessage` is a `Message<Throwable>` from `org.springframework.messaging.support.ErrorMessage`. Its payload holds a `Throwable`, which may be a `MessagingException` wrapping the root cause. When context is available, the exception has `failedMessage` or the `ErrorMessage` has `originalMessage`.

~~~text
ErrorMessage
  payload: MessagingException or Throwable
    cause: IllegalArgumentException / IOException / ...
    failedMessage: Message<?> (may be null)
  originalMessage: Message<?> (may be null)
  headers: ...
~~~

Example reading error details safely:

~~~java
void inspect(ErrorMessage error) {
    Throwable failure = error.getPayload();
    Message<?> failed = null;

    if (failure instanceof MessagingException messaging) {
        failed = messaging.getFailedMessage();
    }
    if (failed == null) {
        failed = error.getOriginalMessage();
    }

    Object correlation = failed == null ? null
            : failed.getHeaders().get("businessCorrelationId");

    System.out.println(failure.getClass().getSimpleName());
    System.out.println("Correlation: " + correlation);
}
~~~

Import `org.springframework.messaging.MessagingException`. Do not assume `getOriginalMessage()` or `getFailedMessage()` is always non-null: for instance, a failure may happen before a message is constructed, or a wrapper may omit the original message when creating the error message.

The default global `errorChannel` is typically a `PublishSubscribeChannel` with a framework logging subscriber. You can attach additional subscribers to collect errors; in production, control error policies per flow and avoid duplicate handling or logging sensitive data.

## 6. Runnable Example: Same Function in Synchronous and Polling Flows

We build an order-classification app using **a single function**:

~~~text
Path A:
Message<OrderSubmitted> with traceId/correlation
  → orders.syncInput
  → FunctionCatalog.lookup("classifyOrder")
  → Transformer
  → TrackedDecision in syncResults

Path B:
Queue<OrderSubmitted> pendingOrders
  → Supplier<OrderSubmitted> pendingOrderSource
  → Poller every 250ms
  → FunctionFlowBuilder.apply("classifyOrder")
  → Consumer<OrderDecision> capturePolledDecision

Error path:
polling task hits exception
  → ErrorMessage
  → errorChannel
  → errorAudit
  → observedErrors
~~~

The queues below are for illustration only and have no persistence or transactions.

### 6.1. Dependencies

With Java 17+ and compatible Spring Boot/Spring Cloud versions, this Maven snippet assumes the project configures a Spring Boot parent and Spring Cloud BOM:

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

`spring-cloud-function-integration` provides `FunctionFlowBuilder` to invoke `fromSupplier`, `apply`, and `accept` by catalog name. Projects that only perform manual lookups via `FunctionCatalog` do not strictly require this DSL module.

### 6.2. Contract and Function

Create `src/main/java/example/ordering/OrderFunctions.java`:

~~~java
package example.ordering;

import java.util.Locale;
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderSubmitted(String orderId, long totalVnd) {}

record OrderDecision(String orderId, String lane) {}

record TrackedDecision(
        OrderDecision decision,
        String traceId,
        String businessCorrelationId) {}

@Configuration
class OrderFunctions {

    @Bean
    Function<OrderSubmitted, OrderDecision> classifyOrder() {
        return order -> {
            if (order == null
                    || order.orderId() == null
                    || order.orderId().isBlank()
                    || order.totalVnd() <= 0) {
                throw new IllegalArgumentException(
                        "Invalid order");
            }

            String normalized = order.orderId().strip()
                    .toUpperCase(Locale.ROOT);
            String lane = order.totalVnd() >= 1_000_000
                    ? "PRIORITY" : "STANDARD";

            return new OrderDecision(normalized, lane);
        };
    }
}
~~~

The function knows nothing about channels, headers, retries, REST endpoints, or brokers. Both flows below look up `classifyOrder` in `FunctionCatalog`; the same business result is used differently on each path.

### 6.3. Spring Integration Configuration

Create `src/main/java/example/ordering/OrderIntegration.java`:

~~~java
package example.ordering;

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
import org.springframework.messaging.support.ErrorMessage;

@Configuration
class OrderIntegration {

    @Bean("orders.syncInput")
    MessageChannel syncInput() {
        return new DirectChannel();
    }

    @Bean("syncResults")
    BlockingQueue<TrackedDecision> syncResults() {
        return new LinkedBlockingQueue<>();
    }

    @Bean("pendingOrders")
    BlockingQueue<OrderSubmitted> pendingOrders() {
        return new LinkedBlockingQueue<>();
    }

    @Bean("polledResults")
    BlockingQueue<OrderDecision> polledResults() {
        return new LinkedBlockingQueue<>();
    }

    @Bean("observedErrors")
    BlockingQueue<ErrorMessage> observedErrors() {
        return new LinkedBlockingQueue<>();
    }

    @Bean
    Supplier<OrderSubmitted> pendingOrderSource(
            @Qualifier("pendingOrders")
            BlockingQueue<OrderSubmitted> queue) {
        return queue::poll;
    }

    @Bean
    Consumer<OrderDecision> capturePolledDecision(
            @Qualifier("polledResults")
            BlockingQueue<OrderDecision> results) {
        return results::add;
    }

    @Bean
    IntegrationFlow synchronousOrders(
            FunctionCatalog catalog,
            @Qualifier("syncResults")
            BlockingQueue<TrackedDecision> results) {

        Function<OrderSubmitted, OrderDecision> classify =
                Objects.requireNonNull(
                        catalog.lookup("classifyOrder"),
                        "classifyOrder not found");

        return IntegrationFlow.from("orders.syncInput")
                .transform(OrderSubmitted.class, classify::apply)
                .handle(OrderDecision.class, (decision, headers) -> {
                    results.add(new TrackedDecision(
                            decision,
                            (String) headers.get("traceId"),
                            (String) headers.get("businessCorrelationId")));
                    return null;
                })
                .get();
    }

    @Bean
    IntegrationFlow polledOrders(FunctionFlowBuilder builder) {
        return builder
                .fromSupplier("pendingOrderSource",
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(250)
                                        .maxMessagesPerPoll(1)))
                .apply("classifyOrder")
                .accept("capturePolledDecision");
    }

    @Bean
    IntegrationFlow errorAudit(
            @Qualifier("observedErrors")
            BlockingQueue<ErrorMessage> errors) {
        return IntegrationFlow.from("errorChannel")
                .handle(message -> {
                    errors.add((ErrorMessage) message);
                })
                .get();
    }
}
~~~

Create `src/main/java/example/ordering/OrderApplication.java`:

~~~java
package example.ordering;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

**Explanation:** `synchronousOrders` calls `FunctionCatalog.lookup("classifyOrder")` and passes the function into a Spring Integration transformer. It receives messages from `DirectChannel` and preserves `traceId` and `businessCorrelationId` for the downstream handler. `polledOrders` uses `FunctionFlowBuilder` to look up the supplier by name, invoke the same business function, and finish with a consumer.

`errorAudit` only captures error messages **published** to the global `errorChannel`. Do not infer that exceptions from `orders.syncInput` also appear in `observedErrors`.

## 7. Testing Metadata Propagation Through the Synchronous Flow

~~~java
MessageChannel input =
        context.getBean("orders.syncInput", MessageChannel.class);

Message<OrderSubmitted> request = MessageBuilder
        .withPayload(new OrderSubmitted(" dh-107 ", 1_500_000))
        .setHeader("traceId", "trace-9a1")
        .setHeader("businessCorrelationId", "order-DH-107")
        .build();

input.send(request);
~~~

`context` is an `ApplicationContext` injected or fetched from the Spring context. With `DirectChannel`, the endpoints in the example run synchronously, so `syncResults` receives:

~~~text
TrackedDecision(
    decision = OrderDecision("DH-107", "PRIORITY"),
    traceId = "trace-9a1",
    businessCorrelationId = "order-DH-107"
)
~~~

Metadata travels across the transformer without the function needing to read it directly. If an adapter drops headers at ingress, downstream cannot accurately reconstruct `traceId` from the payload alone.

### 7.1. A Validation Failure on DirectChannel

~~~java
Message<OrderSubmitted> invalid = MessageBuilder
        .withPayload(new OrderSubmitted(" ", 100_000))
        .setHeader("traceId", "trace-invalid")
        .build();

input.send(invalid); // expected to throw RuntimeException
~~~

The function throws `IllegalArgumentException`. Spring Integration may wrap this exception in `MessageTransformationException` or `MessagingException`; the caller should inspect the cause per contract. Relying on a specific wrapper type should be verified for your exact version.

This differs from `errorChannel`: the sender is still on the same call stack when the error occurs, so it receives the exception directly.

## 8. Testing Errors via Poller and errorChannel

Add an invalid order to the polling source:

~~~java
pendingOrders.add(new OrderSubmitted(" ", 500_000));
~~~

`pendingOrderSource` returns that value on the next poll; `classifyOrder` throws an exception. With Spring Integration's default task scheduler/error publisher, an `ErrorMessage` is sent to `errorChannel`. The `errorAudit` subscriber appends the failure to `observedErrors` for inspection.

~~~text
pendingOrders.poll()
    → classifyOrder
    → exception
    → MessagePublishingErrorHandler
    → ErrorMessage
    → errorChannel
    → errorAudit / observedErrors
~~~

Do not call `observedErrors.poll()` immediately after adding the order: the poll schedule may not have triggered yet. Use `poll(timeout)` in tests.

### 8.1. Inspecting Cause and Original Message

~~~java
ErrorMessage error =
        observedErrors.poll(3, TimeUnit.SECONDS);

assertNotNull(error);
Throwable failure = error.getPayload();

Message<?> failedMessage = null;
if (failure instanceof MessagingException messaging) {
    failedMessage = messaging.getFailedMessage();
}
if (failedMessage == null) {
    failedMessage = error.getOriginalMessage();
}
~~~

In tests or production code, import `TimeUnit`, `MessagingException`, and `Message`. Some failures occur before a message is created or a wrapper drops the original message, so `failedMessage` can be `null`. Do not rely solely on this field to investigate failures; record correlation/event IDs in durable observability storage.

### 8.2. Items Already Removed from the Source

`pendingOrders::poll` **removes the item from the queue** before the consumer finishes. If the function throws or the process exits, the item does not automatically return. `errorChannel` only propagates/observes errors; it is not a durable acknowledgement/redelivery mechanism.

In production, use a source with checkpoints, acknowledgements, or transactions, or a redrive mechanism. For brokers, rely on the adapter/binder contract rather than treating in-RAM queue behavior as a delivery guarantee.

## 9. Error Classification and Recovery Policies

| Error Category | Examples | Recommended Policy |
| --- | --- | --- |
| Validation/business | Blank order ID, invalid total amount. | Return a business error, reject, or route to quarantine; do not retry infinitely. |
| Schema/conversion | Wrong JSON type, missing field, invalid content type. | Report error at the boundary, capture context safely, and fix the contract/converter. |
| Transient infrastructure | Brief DB outage, partner API timeout. | Bounded retries with backoff, timeouts, and metrics. |
| Permanent | Access denied, unknown partner identifier. | Do not retry endlessly; route to manual handling or DLQ if appropriate. |
| Configuration/programming | Wrong `FunctionCatalog.lookup(...)` name, unexpected null. | Fail fast, fix code/config, and add tests. |
| Duplicate delivery | Broker redelivery or client retries request. | Idempotency via a durable business key. |

For expected business errors, you can model an explicit outcome instead of throwing exceptions for every case:

~~~java
sealed interface OrderOutcome
        permits Accepted, Rejected {}

record Accepted(OrderDecision decision) implements OrderOutcome {}

record Rejected(String code, String reason) implements OrderOutcome {}
~~~

This is an **alternative design** to the `Function<OrderSubmitted,OrderDecision>` signature in the example. Choosing `OrderOutcome` requires updating downstream handlers and optionally using an EIP Router to split `Accepted`/`Rejected` branches.

### 9.1. Where Do Retries Belong?

- **Handler/advice:** retry external system calls on transient failures.
- **Polling adapter:** decide whether to continue or reschedule after errors; account for items already popped from the source.
- **Broker binder:** redelivery, retries, and DLQ per broker semantics.
- **Serverless runtime:** retries per event-source/runtime configuration.

Multiple retry layers can stack on top of one another. Define an overarching policy covering deadlines, attempt limits, backoff/jitter, circuit breakers, and idempotency. Retrying the same `orderId` can cause consumers to write to a database or send emails twice if deduplication is missing.

### 9.2. ErrorChannel vs. Dead-Letter Queue

**`errorChannel`** is an in-application Spring Integration message channel, typically carrying `ErrorMessage`. A **DLQ** is generally a broker-managed destination for failed messages that supports retention and replay via broker tooling. The two concepts are related but not interchangeable: subscribing to `errorChannel` does not persist messages durably or create a Kafka DLQ.

### 9.3. Idempotency and Transactions

Never use `MessageHeaders.ID` as a deduplication key. Suitable keys are usually `eventId` or `orderId + eventVersion`. Across multiple instances, persist processing state in a durable store with a unique constraint/transaction or an equivalent atomic strategy.

~~~text
When receiving an event:
    key = eventId (stable across redelivery)
    if key is COMPLETED → return cached result or ack
    if key is PROCESSING → handle concurrency/recovery
    if absent → claim atomically and execute business logic
    after success → mark COMPLETED
~~~

This is a conceptual pattern, not a complete distributed exactly-once algorithm. When multiple systems participate, design appropriate transactions or compensation.

## 10. Metadata at HTTP, Broker, and Serverless Boundaries

### 10.1. HTTP

An HTTP request carries a body (JSON) and its own headers. The adapter must deserialize the body to `OrderSubmitted`, map standard trace context, and translate errors into HTTP status codes and error schemas. Do not assume that throwing `IllegalArgumentException` makes every HTTP adapter return the same status code. Client timeouts and retries must also be designed explicitly.

### 10.2. Broker

Kafka and RabbitMQ have message keys, offsets/partitions, or delivery tags/acks. The binder or inbound adapter decides which headers appear in Spring Messaging. A consumer must tolerate redelivery and must not try to pass raw acknowledgement objects directly into HTTP or serverless flows. Test header mapping, serialization, DLQ routing, and idempotency against the real adapter.

### 10.3. Serverless

Serverless runtimes provide their own request/event IDs, deadlines, retries, and logging. The adapter converts platform events into function calls. To keep logic reusable, functions only need domain objects; runtime metadata is handled in a wrapper layer or via `Message<T>` when an explicit contract exists.

### 10.4. Header-Based Routing in SCF

Spring Cloud Function includes `RoutingFunction` and supports routing via headers `spring.cloud.function.definition` or `spring.cloud.function.routing-expression` in supported contexts. This is **function routing**, distinct from Spring Integration's EIP Content-Based Router (which chooses a **message channel**). When untrusted callers influence routing, restrict the set of callable functions, avoid evaluating arbitrary expressions, and validate inputs.

## 11. Testing at the Right Boundaries

### 11.1. Unit Testing Business Functions

~~~java
OrderFunctions functions = new OrderFunctions();

OrderDecision decision = functions.classifyOrder()
        .apply(new OrderSubmitted(" dh-107 ", 1_500_000));

assertEquals("DH-107", decision.orderId());
assertEquals("PRIORITY", decision.lane());

assertThrows(IllegalArgumentException.class, () ->
        functions.classifyOrder()
                .apply(new OrderSubmitted(" ", 100)));
~~~

Also test the exact `1_000_000` boundary, amounts below the threshold, `null`, and invalid totals. This unit test does not verify message headers or error publishing.

### 11.2. Integration Testing Headers Through a Transformer

~~~java
@SpringBootTest(classes = OrderApplication.class)
class OrderMetadataTest {

    @Autowired ApplicationContext context;

    @Autowired
    @Qualifier("syncResults")
    BlockingQueue<TrackedDecision> results;

    @Test
    void preservesBusinessHeaders() {
        results.clear();

        MessageChannel input =
                context.getBean("orders.syncInput", MessageChannel.class);

        input.send(MessageBuilder
                .withPayload(new OrderSubmitted(" dh-107 ", 1_500_000))
                .setHeader("traceId", "trace-9a1")
                .setHeader("businessCorrelationId", "order-DH-107")
                .build());

        TrackedDecision actual = results.poll();
        assertNotNull(actual);
        assertEquals("DH-107", actual.decision().orderId());
        assertEquals("trace-9a1", actual.traceId());
        assertEquals("order-DH-107",
                actual.businessCorrelationId());
    }

    @Test
    void synchronousErrorReachesCaller() {
        MessageChannel input =
                context.getBean("orders.syncInput", MessageChannel.class);

        assertThrows(RuntimeException.class, () ->
                input.send(MessageBuilder.withPayload(
                        new OrderSubmitted(" ", 100))
                        .build()));
    }
}
~~~

Requires JUnit 5, Spring Boot Test, `@Autowired`, `@Qualifier`, `ApplicationContext`, `BlockingQueue`, `MessageChannel`, `MessageBuilder`, and static imports from `Assertions`. With `DirectChannel`, the handler has already executed when `send` returns, so results can be polled immediately. If you switch to an executor, use a bounded wait.

### 11.3. Integration Testing Polling + ErrorMessage

~~~java
@SpringBootTest(classes = OrderApplication.class)
class OrderPollingErrorTest {

    @Autowired
    @Qualifier("pendingOrders")
    BlockingQueue<OrderSubmitted> pending;

    @Autowired
    @Qualifier("observedErrors")
    BlockingQueue<ErrorMessage> errors;

    @Test
    void polledInvalidOrderIsReported() throws InterruptedException {
        pending.clear();
        errors.clear();

        pending.add(new OrderSubmitted(" ", 100));

        ErrorMessage failure = errors.poll(3, TimeUnit.SECONDS);
        assertNotNull(failure, "No error observed before timeout");
        assertNotNull(failure.getPayload());
    }
}
~~~

This test depends on the active standard scheduler/poller and error publisher. With a custom error handler that does not publish to the global `errorChannel`, update the test to match your actual configuration. Use `poll(timeout)` instead of `Thread.sleep(...)` to avoid guessing when the scheduler runs.

### 11.4. Tests When Deploying Real Adapters

| Test Area | What to Assert |
| --- | --- |
| JSON/body conversion | Payload reaches the function with the expected type; schema errors produce structured failures. |
| Trace/correlation headers | Metadata survives across all designed hops. |
| HTTP exception mapping | Validation errors and timeouts map to status codes and error schemas matching the contract. |
| Broker retry/redelivery | Consumer is idempotent and produces no duplicate side effects. |
| DLQ/error store | Unrecoverable failures are stored and observable in the right place. |
| Errors without failedMessage | Error handler tolerates a missing original message. |
| Mid-stream polling source failure | Item recovery exists or item loss is explicitly accepted by requirements. |
| Gateway request/reply | Reply contract holds; void consumers are not wired as missing replies. |

## 12. Diagnosing Common Failures

| Symptom | Possible Explanation | Remediation |
| --- | --- | --- |
| Function does not see `traceId` | Function only accepts payload `T`. | Let the integration layer manage headers, or accept `Message<T>` if needed. |
| `businessCorrelationId` lost across adapter | Header mapper/converter stripped the header. | Configure an allowlist and test at boundaries. |
| `DirectChannel` throws but `errorChannel` receives nothing | Synchronous exception propagates to the sender. | Handle at caller/gateway or configure an appropriate error policy. |
| Poller fails without emitting `ErrorMessage` | Custom scheduler does not publish, endpoint not started, or no item arrived. | Inspect the poller and `MessagePublishingErrorHandler`. |
| `getOriginalMessage()` returns null | `ErrorMessage` did not capture the original message at the failure point. | Also check `MessagingException.failedMessage` and correlation stores. |
| Retries cause duplicate side effects | Stacked retry layers and missing idempotency. | Bound retries and persist idempotency keys. |
| Gateway times out | Reply lost, flow terminates in a consumer, or async execution is too slow. | Check `replyChannel`, endpoints, and timeouts. |
| Sensitive headers appear in logs | Logging full messages/headers. | Filter/mask via allowlist and configure log retention. |
| Function type-cast failure | JSON/converter/generic signature mismatch. | Verify deserialization and input contracts. |

## 13. Implementation Checklist

1. Define **payload** and **metadata** contracts at ingress/egress.
2. Keep domain logic in `Supplier`, `Function`, `Consumer`; keep transport and orchestration in `IntegrationFlow` and adapters.
3. Specify where headers are created, which hops must preserve them, and whether they may leave the system.
4. Distinguish exceptions returned to callers from failures published as `ErrorMessage`.
5. Maintain separate retry policies for validation, transient infrastructure, and permanent errors.
6. Use an idempotency key stable across redelivery; never use generated message IDs as business keys.
7. Verify polling/broker sources have appropriate acknowledgements, retries, dead-lettering, and recovery.
8. Include enough correlation in logs, metrics, and traces without leaking sensitive data.
9. Unit test functions, synchronous flows, polling flows, and real adapters/binders.

### Extension Exercises

- Add a `markStage` function accepting `Message<OrderSubmitted>` to set the `processingStage` header; test trace and correlation headers before and after.
- Configure an error flow separating validation failures from infrastructure errors and writing them to two different error stores.
- Replace `DirectChannel` with `ExecutorChannel` and compare exception paths and message acknowledgement timing.
- Simulate a consumer database write failure; implement bounded retries and idempotency using a business key.
- Try a Spring Integration Messaging Gateway, preserve `replyChannel`, and map errors returned to the caller.

## 14. References

- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): `ErrorMessage`, `errorChannel`, synchronous/asynchronous handling, and polling.
- [Spring Integration — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): request/reply, error propagation, and gateway error channels.
- [Spring Integration — Transformers](https://docs.spring.io/spring-integration/reference/transformer.html): payload/message transformation, null output, and header filters.
- [Spring Integration — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): `DirectChannel` and channel types.
- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): `FunctionCatalog`, composition, messages, and function routing.
- [Spring Cloud Function — Spring Integration Interaction](https://docs.spring.io/spring-cloud-function/reference/spring-integration.html): `FunctionFlowBuilder`, `fromSupplier`, `apply`, and `accept`.

**Conclusion:** At the boundary between Spring Cloud Function and Spring Integration, payloads carry business logic while message headers carry trace, correlation, reply, and error metadata. `DirectChannel` typically returns exceptions to the caller, whereas polling and asynchronous components can publish `ErrorMessage` instances via `errorChannel`. Clear metadata contracts, error classification, retries, idempotency, and adapter-level testing enable a single function to serve HTTP, events, and serverless with proper observability and recovery.
