# Filtering by Payload

In **Spring Integration**, a **Message Filter** is an endpoint that implements the **Message Filter** Enterprise Integration Pattern: it receives a message, evaluates a condition (*predicate*), and decides whether to **let the message proceed** or **reject the message**. When **filtering by payload**, the condition focuses on business data inside `Message.getPayload()`, such as event kind, order amount, payment status, or customer notification preference.

This lesson belongs to the **Filter** chapter of the **SPRING_INTEGRATION_PATTERN** module. The goal of the module is to implement Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows; practice Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation while testing and observing processing branches. This lesson focuses on creating pure predicates, attaching predicates to endpoints using `@Filter` or Java DSL, handling discarded messages, preserving headers, and verifying behavior through tests.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the difference between **filtering by payload**, filtering by header, and message routing.
2. Design predicates with clear inputs and outputs, free of side effects, and easy to test independently of Spring.
3. Use `@Filter` and Java DSL `IntegrationFlow.filter(...)` to filter typed payload objects.
4. Understand the two exact branches of a Filter: **accepted** and **rejected**.
5. Configure `discardChannel` and explain the option to report errors with `throwExceptionOnRejection`.
6. Distinguish a `false` result from an exception thrown while evaluating the predicate.
7. Verify that messages preserve their payload/headers along accepted/rejected paths and are not mistakenly processed downstream.
8. Write unit tests for predicates and integration tests with `DirectChannel` / `QueueChannel`.
9. Combine Filter with Transformer, Router, Publish–Subscribe, Splitter/Aggregator, Gateway, retry, and error channels.
10. Identify security, immutability, performance, and observability risks of filtering by payload.

## 2. How Does Filtering by Payload Work?

A message can be described as:

~~~text
Message<OrderEvent>
  payload:
    eventId = "evt-1001"
    orderId = "order-1001"
    kind = CREATED
    amount = 750.00
    customerOptIn = true
  headers:
    traceId = "trace-1001"
    businessCorrelationId = "order-1001"
~~~

Suppose the notification-sending branch only processes events that satisfy **all** conditions:

- Event kind is `CREATED`.
- The customer has opted in to notifications (`customerOptIn=true`).
- Total order amount is **100.00 or higher**.

The Filter evaluates the payload and chooses:

~~~mermaid
flowchart LR
    P["Producer: OrderEvent"] --> C["orders.events"]
    C --> F{"Payload Filter"}
    F -->|"true: eligible"| A["orders.notify"]
    F -->|"false: not eligible"| D["orders.skipped"]
    A --> H["Notification handler"]
    D --> M["Skip metrics / audit"]
~~~

**Filter does not transform the payload.** If accepted, the message goes to the output channel for the next handler to process. If not, the message can go to the discard channel or be dropped depending on configuration. The payload/header structure does not turn into a different object merely because the predicate returns `true` or `false`.

### 2.1. A Filter Answers One Single Question

> **Is this message allowed to continue along this branch?**

A Filter's predicate should yield a clear decision: `true` or `false`. If you have to choose among `orders.priority`, `orders.review`, and `orders.standard`, that is a **Router** problem, not a reason to chain multiple Filters in a hard-to-follow way.

### 2.2. Component Comparison

| Component | Responsibility | Typical result |
|---|---|---|
| **Filter** | Decide accept/reject for a message | Original message proceeds or is discarded |
| **Transformer** | Change payload/message representation | New payload or new `Message<?>` |
| **Router** | Select destination channel by content/metadata | One or more channels as designed |
| **Header Enricher** | Add/recompute metadata | Message with updated headers |
| **Splitter** | Split a message into multiple parts | Multiple child messages |
| **Aggregator** | Combine related messages | One aggregated result |
| **Service Activator** | Invoke application logic/side effect | May produce a reply or handle one-way |

Do not use a Transformer returning `null` as a substitute for a Filter; in Spring Integration, a Transformer returning null is treated as a transformation error condition, not an intentional way to discard a message.

## 3. Designing the Payload Contract Before Filtering

A Filter should operate on a **well-defined payload type**, after an inbound adapter or decoder has decoded and validated the minimal fields.

Java 17+ example:

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public enum OrderEventKind {
    CREATED,
    PAID,
    CANCELLED
}

public record OrderEvent(
        String eventId,
        String orderId,
        OrderEventKind kind,
        BigDecimal amount,
        boolean customerOptIn
) {
    public OrderEvent {
        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException(
                    "eventId must not be blank");
        }
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException(
                    "orderId must not be blank");
        }
        Objects.requireNonNull(kind, "kind");
        Objects.requireNonNull(amount, "amount");
        if (amount.signum() < 0) {
            throw new IllegalArgumentException(
                    "amount must be non-negative");
        }
    }
}
~~~

A `record` has no setters; the fields in this example are immutable values. In a real project, these types typically live in **two separate source files**, or the enum is placed according to Java's visibility/package conventions. This article presents them together for readability.

**Distinguish two layers of responsibility:**

- **Validation:** ensures the payload contains valid data for the system to process, such as non-blank `eventId` and `amount >= 0`.
- **Filtering:** the payload is valid, but determines whether it **matches the target scope of the branch**, such as whether the customer opted in and the event is `CREATED`.

A valid `CANCELLED` event is not an error; it simply does not need to pass through the order-creation notification branch.

### 3.1. Why Should You Avoid Filtering Raw JSON Strings Directly?

If a Filter contains:

~~~java
// Anti-pattern: fragile dependence on string formatting.
boolean accepted = json.contains("\"customerOptIn\":true");
~~~

then merely changing whitespace, field order, or encoding can make the result wrong. Let a JSON decoder/converter produce a typed `OrderEvent`, validate the schema, and then filter by properties. When the data source is untrusted, remember to enforce size and structural limits at the adapter before parsing.

## 4. Writing Pure Predicates for Easy Testing

A good design separates **message selection policy** from message channel infrastructure. The predicate takes the form:

~~~text
boolean shouldNotify(OrderEvent event)
~~~

No DB, HTTP, email, or clock calls; the same `OrderEvent` always yields the same result.

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public final class OrderNotificationPolicy {

    private static final BigDecimal MIN_AMOUNT =
            new BigDecimal("100.00");

    public boolean shouldNotify(OrderEvent event) {
        Objects.requireNonNull(event, "event");

        return event.kind() == OrderEventKind.CREATED
                && event.customerOptIn()
                && event.amount().compareTo(MIN_AMOUNT) >= 0;
    }
}
~~~

The predicate is concise enough for code review and direct testing. Larger thresholds in production should be defined via versioned immutable configuration if replays must reproduce historical decisions.

### 4.1. Why Use BigDecimal.compareTo?

`BigDecimal.equals` also checks scale: `new BigDecimal("100.0")` and `new BigDecimal("100.00")` have equal numeric values, yet `equals` returns `false`. For an "at least 100" condition, `compareTo(...) >= 0` accurately reflects numeric ordering.

### 4.2. Decision Table

| Kind | Opt-in | Amount | Result | Reason |
|---|---|---:|---|---|
| CREATED | true | 750.00 | Accept | Meets conditions |
| CREATED | true | 100.00 | Accept | Exact threshold |
| CREATED | true | 99.99 | Reject | Below threshold |
| CREATED | false | 200.00 | Reject | Customer did not opt in |
| PAID | true | 500.00 | Reject | Not the required event kind |
| CANCELLED | true | 800.00 | Reject | Do not send creation notification |
| CREATED | true | 100.0 | Accept | Compares numeric value, not scale |

This table is a business contract that can be turned into a `@ParameterizedTest`. Negative amounts do not appear in the table because `OrderEvent` rejects them in its constructor; that is a **data error**, not a normal Filter rejection branch.

### 4.3. Signs a Predicate Is No Longer Pure

~~~java
// Do not put this directly inside a filter:
boolean accept(OrderEvent event) {
    boolean allowed = customerApi.isSubscribed(event.orderId());
    emailService.sendConfirmation(event.orderId());
    return allowed && LocalDate.now().getDayOfWeek()
            != DayOfWeek.SUNDAY;
}
~~~

Problems:

- An API timeout causes the filter to fail, even though the message should not necessarily be rejected.
- Sending the email happens **before** the Filter makes its decision.
- Retries can send the email multiple times.
- The outcome depends on the host machine's current time and external state.
- Unit tests have to mock many dependencies unrelated to the Filter's essence.

Instead, fetch the required information via an **enrichment endpoint** with its own retry/timeout settings, produce a reliable snapshot, and then apply a pure predicate. Side effects should only happen **after the accepted branch** in a dedicated handler.

## 5. Filtering Payloads with the @Filter Annotation

Spring Integration supports the `org.springframework.integration.annotation.Filter` annotation. We use a thin adapter that calls the policy:

~~~java
import org.springframework.integration.annotation.Filter;

public final class OrderNotificationFilter {

    private final OrderNotificationPolicy policy;

    public OrderNotificationFilter(OrderNotificationPolicy policy) {
        this.policy = policy;
    }

    @Filter(
            inputChannel = "orders.events",
            outputChannel = "orders.notify",
            discardChannel = "orders.skipped")
    public boolean accept(OrderEvent event) {
        return policy.shouldNotify(event);
    }
}
~~~

Explanation:

- `inputChannel` is where the endpoint receives messages.
- The `OrderEvent event` parameter is bound from the **payload** using Spring Integration's method invocation mechanism.
- The method returns `boolean`; the framework uses the result as the Filter decision.
- `true`: the message is forwarded to `orders.notify`.
- `false`: the message is forwarded to `orders.skipped` via `discardChannel`.
- `@Filter` does not create another `OrderEvent` or `Message` to pass downstream.

**Important:** the class must be registered as a Spring bean and Spring Integration annotation infrastructure must be enabled. Simply adding the annotation to an object created with `new` outside Spring is not enough to create a message-receiving endpoint.

### 5.1. Configuring Channels and Beans

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class OrderFilterConfiguration {

    @Bean(name = "orders.events")
    public MessageChannel input() {
        return new DirectChannel();
    }

    @Bean(name = "orders.notify")
    public PollableChannel accepted() {
        return new QueueChannel();
    }

    @Bean(name = "orders.skipped")
    public PollableChannel rejected() {
        return new QueueChannel();
    }

    @Bean
    public OrderNotificationPolicy notificationPolicy() {
        return new OrderNotificationPolicy();
    }

    @Bean
    public OrderNotificationFilter notificationFilter(
            OrderNotificationPolicy policy) {
        return new OrderNotificationFilter(policy);
    }
}
~~~

`DirectChannel` executes the call on a single thread for the test example. The two `QueueChannel` instances are for **observing outputs in tests**; they are in-memory channels, not durable storage across restarts. In a real application, `orders.notify` is typically wired to a Service Activator, while `orders.skipped` can be wired to a metrics/audit handler.

### 5.2. Sending Messages with Headers

~~~java
import java.math.BigDecimal;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

void publish(MessageChannel input) {
    OrderEvent event = new OrderEvent(
            "evt-1001",
            "order-1001",
            OrderEventKind.CREATED,
            new BigDecimal("750.00"),
            true);

    Message<OrderEvent> message = MessageBuilder
            .withPayload(event)
            .setHeader("traceId", "trace-1001")
            .setHeader("businessCorrelationId", "order-1001")
            .build();

    input.send(message);
}
~~~

The message above will travel to `orders.notify` if there are no configuration errors. Important headers remain attached to the message forwarded by the Filter. `send()==true` at the channel layer is **not** proof that a notification was successfully sent by a downstream handler, especially when asynchronous processing is involved.

## 6. Filtering by Payload with Java DSL

Spring Integration Java DSL allows declaring the flow directly inside configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class OrderNotificationDslConfiguration {

    @Bean
    public IntegrationFlow notificationFilterFlow(
            OrderNotificationPolicy policy) {

        return IntegrationFlow.from("orders.dsl.input")
                .filter(OrderEvent.class,
                        event -> policy.shouldNotify(event),
                        spec -> spec.discardChannel("orders.dsl.skipped"))
                .channel("orders.dsl.notify")
                .get();
    }
}
~~~

Here, `filter(OrderEvent.class, ...)` binds the predicate to the **payload type**, instead of accepting `Message<?>` and casting manually. If the predicate returns `true`, the message proceeds to `orders.dsl.notify`; if `false`, it goes to `orders.dsl.skipped`. Declare the channels or let Java DSL create appropriate channels as configured by the project; when testing, explicitly declare bean names for all three channels.

**This is an alternative** to the `@Filter` configuration in section 5; do not register two competing filters on the same `DirectChannel` if a single route is intended.

### 6.1. Simple Predicate Written Inline in DSL

~~~java
@Bean
IntegrationFlow paidEventFlow() {
    return IntegrationFlow.from("payment.events")
            .filter(OrderEvent.class,
                    event -> event.kind() == OrderEventKind.PAID)
            .channel("payment.paidOnly")
            .get();
}
~~~

This example intentionally **omits a discard channel**: non-PAID events are dropped from this branch by default configuration. Only use silent filtering when it is an accepted behavior in the contract. If the producer needs to know why a message was not processed, configure a reject branch or a meaningful response.

### 6.2. When Should You Extract a Predicate into a Bean?

Use a separate bean when:

- There is more than one condition.
- The rule needs to be reused across multiple flows.
- There is a decision table and many tests.
- Rule versioning is required.
- You want to run unit tests without starting a Spring context.

There is no need to create a multi-layered service for a trivial condition like `kind == PAID`; clarity matters more than the number of code classes.

## 7. Accepted and Rejected Branches

This is the core of Message Filter. A condition does not always lead to an error path.

### 7.1. Accepted: The Message Proceeds

When the predicate returns `true`, the Filter forwards the message to the output channel. It does not alter the business payload on its own. In typical designs, headers such as `traceId`, `businessCorrelationId`, and `tenantId` continue traveling with the message.

~~~mermaid
flowchart LR
    I["Input Message<OrderEvent>"] --> F{"Filter"}
    F -->|"true"| A["Accepted: Message<OrderEvent>"]
    A --> H["Notification handler"]
~~~

The Filter **does not verify** that the Notification actually sent the email or that the side effect succeeded. To track business outcomes, use metrics/acks/replies in downstream handlers.

### 7.2. Rejected: Discard Channel or Dropping the Message

When the predicate returns `false`, by default the message can be **dropped from the main route**. If `discardChannel` is declared, the Filter forwards the rejected message to that channel:

~~~java
@Filter(
        inputChannel = "orders.events",
        outputChannel = "orders.notify",
        discardChannel = "orders.skipped")
public boolean accept(OrderEvent event) {
    return policy.shouldNotify(event);
}
~~~

`orders.skipped` **is not automatically an errorChannel or a dead-letter queue**. It is just a configured channel; you must attach an appropriate handler, audit logger, or adapter if you want to process the reject branch durably.

### 7.3. Rejected Does Not Mean Exception

There are two distinct cases:

~~~java
// A normal filtering decision:
return false;

// A failure while evaluating the condition:
throw new IllegalStateException("Subscriber lookup unavailable");
~~~

The first case is a **policy rejection**. The second case is an **execution failure**, which may surface to the sender in a synchronous flow or go through asynchronous error handling depending on topology.

If the business requires turning a rejection into an exception, Spring Integration supports configuring `throwExceptionOnRejection`. With this setting, a rejection can raise `MessageRejectedException`. Test the exact interaction between the exception configuration and `discardChannel` on the version you are using to avoid handling the same message as two separate failures.

**Do not configure unbounded retries for a predicate returning `false`.** Filtering out an ineligible message is a normal decision, not an infrastructure error to retry.

## 8. Distinguishing Filter from Validation

A common mistake is using a Filter to "swallow" all invalid inputs. For example:

~~~text
Malformed JSON syntax
  -> decoder / adapter error

OrderEvent missing eventId or negative amount
  -> schema/validation error

Valid OrderEvent with kind=CANCELLED
  -> Notification branch Filter returns false
~~~

The three situations have different meanings.

| Situation | Meaning | Suggested handling |
|---|---|---|
| JSON fails to parse | Malformed input | Return decode error or error flow |
| Missing required field | Data contract violation | Validation/rejection with reason |
| Unauthorized for tenant | Authorization violation | Reject at trust boundary |
| `kind=CANCELLED` | Valid event but outside notification branch | Filter returns `false` |
| `customerOptIn=false` | Valid event but must not send notification | Filter returns `false` |
| Customer profile API times out | Transient error at enrichment step | Bounded retry/error flow |
| Notification API returns 503 | Downstream handler failure | Downstream retry/idempotency |

Placing validation near ingress ensures subsequent steps receive a valid `OrderEvent`. Then predicates can assume `amount` is non-negative and `kind` is present, avoiding cluttering every branch with contract checks.

### 8.1. Filter Is Not a Standalone Security Control

A payload might contain `isAdmin=true` or `tenantId="shop-a"`, but that does not prove the caller has permission. Authorization must rely on a trusted principal/context at the security boundary. Payload filtering can be used **after** permission info is authenticated, but it never replaces authentication and access control.

## 9. How Does Payload Type Affect a Filter?

### 9.1. String Payload

~~~java
import org.springframework.integration.annotation.Filter;

@Filter(
        inputChannel = "text.input",
        outputChannel = "text.nonBlank")
public boolean nonBlank(String text) {
    return !text.isBlank();
}
~~~

This simple condition discards empty/whitespace-only strings. It does not mutate the text; for instance, `"  OK  "` is accepted with its whitespace intact. If trimming is desired, use a Transformer before or after the Filter per the contract.

### 9.2. DTO/Record Payload

~~~java
@Filter(
        inputChannel = "orders.events",
        outputChannel = "orders.highValue")
public boolean highValue(OrderEvent event) {
    return event.amount().compareTo(
            new java.math.BigDecimal("1000.00")) >= 0;
}
~~~

This is an order-value condition; it does not imply the order has been paid or that the customer qualifies for a promotion. Interpret its business meaning accurately.

### 9.3. Collection Payload

~~~java
import java.util.List;

@Filter(
        inputChannel = "batches.input",
        outputChannel = "batches.nonEmpty")
public boolean hasElements(List<?> items) {
    return !items.isEmpty();
}
~~~

A batch-level Filter accepts or rejects **the entire message carrying the List**, not individual elements inside the List. If you want to drop individual items, use a Transformer to create a new collection or Splitter → per-item Filter → Aggregator, depending on process semantics.

### 9.4. Dynamic Map Payload

~~~java
@Filter(
        inputChannel = "legacy.input",
        outputChannel = "legacy.active")
public boolean isActive(java.util.Map<String, Object> value) {
    return Boolean.TRUE.equals(value.get("active"));
}
~~~

Filtering a `Map` directly is helpful in legacy integrations but weak on type safety: the string `"true"` is not equal to `Boolean.TRUE`. For complex payloads, decode and validate into a DTO first to reduce casting errors and strengthen data constraints.

### 9.5. Wrong Payload Type Does Not Necessarily Become a Reject

If an endpoint is declared for `OrderEvent` but a producer sends a different type, the framework may fail to bind/convert the parameter and throw an exception. Do not assume it becomes `false` and goes to the discard channel. Check converters, validation, and error handling on the inbound adapter.

## 10. Ordering Filter and Transformer

There is no single right order for every case. The decision depends on how data is normalized and what the condition means.

### 10.1. Filter Before Transformer

~~~mermaid
flowchart LR
    IN["Decoded OrderEvent"] --> F{"Filter: notification needed?"}
    F -->|Yes| T["Transformer: build email request"]
    T --> OUT["Email adapter"]
    F -->|No| SKIP["Skip"]
~~~

Advantage: only messages likely to be processed pay the cost of building templates, calling enrichment, or preparing emails. Fits well when the predicate uses simple, already-valid fields.

### 10.2. Transformer Before Filter

~~~mermaid
flowchart LR
    IN["RawOrder"] --> T["Transformer: normalize"]
    T --> F{"Filter: condition on NormalizedOrder"}
    F -->|Yes| OUT["Downstream"]
    F -->|No| SKIP["Discard"]
~~~

Fits well when the condition depends on **normalized** data—for example, region `" north "` must be treated as `"NORTH"`, or amounts arrive as strings and must be parsed before comparison.

### 10.3. Do Not Lose Headers When Creating a New Message

A Transformer returning a **payload** usually lets Spring Integration create a new message and propagate input headers per framework rules. A Transformer returning a full **`Message<?>`** must actively preserve required metadata. If `traceId` or correlation is lost during transformation, the Filter may still decide correctly, but downstream loses traceability.

## 11. Filter with Router and Publish–Subscribe

### 11.1. Filter Before Router

~~~mermaid
flowchart LR
    IN["Input"] --> F{"Filter: eligible?"}
    F -->|Yes| R{"Router: region"}
    R --> N["NORTH"]
    R --> S["SOUTH"]
    F -->|No| D["Discard"]
~~~

Filter reduces the number of messages that must be routed, while Router picks the **processing destination** for accepted messages.

### 11.2. Filter in a Publish–Subscribe Branch

~~~mermaid
flowchart TB
    IN["OrderEvent"] --> PUB(("PublishSubscribeChannel"))
    PUB --> AUD["Audit subscriber"]
    PUB --> NTF{"Notification Filter"}
    PUB --> ANA["Analytics subscriber"]
    NTF -->|Yes| EMAIL["Email sender"]
    NTF -->|No| SKIP["No notification"]
~~~

Here, a Filter returning `false` in the notification branch **does not automatically drop the message from the Audit/Analytics subscribers**. Each branch has its own responsibility; if you want to drop the message before fan-out, place the Filter **upstream** of `PublishSubscribeChannel`.

### 11.3. Filter After Splitter, Before Aggregator

After a Splitter, individual items can be filtered. However, an Aggregator typically uses `correlationId`, `sequenceNumber`, and `sequenceSize` to know when a group is complete.

If a Splitter produces 5 parts and a Filter discards 2 parts, the Aggregator may still wait for 5 parts under its default release strategy. You must explicitly choose a release strategy, timeout, or representation for discarded results. **Do not simply add a Filter and assume the Aggregator automatically knows only 3 parts remain.**

## 12. Filter in Synchronous and Asynchronous Flows

In a synchronous topology with `DirectChannel`, a `send()` call can execute the filter directly on the producer thread. If the predicate throws an exception, the error can bubble back to the sender. When using `ExecutorChannel` or an asynchronous message-driven inbound adapter, predicate evaluation runs on the worker thread; exceptions can flow through `errorChannel`/error handling depending on configuration.

| Behavior | Synchronous | Asynchronous |
|---|---|---|
| Predicate returns `true` | Message forwarded in same call chain | May be forwarded on worker thread |
| Predicate returns `false` | Discard/reject per configuration | Discard/reject per configuration |
| Predicate throws exception | May propagate to sender | Usually handled by worker error handling |
| `send()==true` | Not proof the entire business flow succeeded | May return before downstream finishes |
| Processing order | Follows synchronous topology | Must consider concurrency and ordering |
| Retry | Configured by advice/adapter/flow | Configured by worker/consumer retry and error handling |

A pure predicate with no side effects is easier to retry and reproduce. However, **retrying the whole message** after a downstream error can re-run upstream handlers; side effects require their own idempotency.

## 13. Testing Predicates with JUnit 5

Unit testing should start at the policy class **without depending on a Spring context**.

### 13.1. Parameterized Tests for the Decision Table

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import java.util.stream.Stream;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class OrderNotificationPolicyTest {

    private final OrderNotificationPolicy policy =
            new OrderNotificationPolicy();

    static Stream<Arguments> cases() {
        return Stream.of(
                Arguments.of(OrderEventKind.CREATED, true,
                        "750.00", true),
                Arguments.of(OrderEventKind.CREATED, true,
                        "100.00", true),
                Arguments.of(OrderEventKind.CREATED, true,
                        "99.99", false),
                Arguments.of(OrderEventKind.CREATED, false,
                        "200.00", false),
                Arguments.of(OrderEventKind.PAID, true,
                        "500.00", false),
                Arguments.of(OrderEventKind.CANCELLED, true,
                        "800.00", false),
                Arguments.of(OrderEventKind.CREATED, true,
                        "100.0", true));
    }

    @ParameterizedTest
    @MethodSource("cases")
    void filtersPayloadAsExpected(
            OrderEventKind kind,
            boolean optIn,
            String amount,
            boolean expected) {

        OrderEvent event = new OrderEvent(
                "evt-1001", "order-1001",
                kind, new BigDecimal(amount), optIn);

        assertEquals(expected, policy.shouldNotify(event));
    }
}
~~~

This test precisely verifies the threshold, opt-in, and event-kind contract. Because the method does not load a Spring context, the test runs fast and can easily expand to dozens of cases.

### 13.2. Testing Invalid Data Separately

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

class OrderEventContractTest {

    @Test
    void negativeAmountIsInvalidPayload() {
        assertThrows(IllegalArgumentException.class,
                () -> new OrderEvent(
                        "evt-1002", "order-1002",
                        OrderEventKind.CREATED,
                        new BigDecimal("-1.00"),
                        true));
    }

    @Test
    void missingOrderIdIsInvalidPayload() {
        assertThrows(IllegalArgumentException.class,
                () -> new OrderEvent(
                        "evt-1003", "  ",
                        OrderEventKind.CREATED,
                        new BigDecimal("150.00"),
                        true));
    }
}
~~~

These two tests verify **payload invariants**, not a Filter rejecting a valid event. Keeping the right test at the right layer makes failure analysis clearer.

### 13.3. Testing Determinism

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

class NotificationDeterminismTest {

    @Test
    void samePayloadAlwaysProducesSameDecision() {
        OrderNotificationPolicy policy =
                new OrderNotificationPolicy();

        OrderEvent event = new OrderEvent(
                "evt-1", "order-1",
                OrderEventKind.CREATED,
                new BigDecimal("250.00"),
                true);

        boolean first = policy.shouldNotify(event);
        for (int i = 0; i < 100; i++) {
            assertEquals(first, policy.shouldNotify(event));
        }
    }
}
~~~

This is a smoke test; it does not replace reviewing that the method has no side effects, time dependencies, or mutable state.

## 14. Integration Testing Filter Through Real Channels

To verify that `@Filter` is registered by Spring and output channels are named properly, you need a test that sends a **Message<OrderEvent>** through the input channel and reads from the expected branch.

Java 17+, JUnit Jupiter 5, Spring Test, and Spring Integration example:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = OrderFilterConfiguration.class)
class OrderFilterFlowTest {

    @Autowired
    @Qualifier("orders.events")
    MessageChannel input;

    @Autowired
    @Qualifier("orders.notify")
    PollableChannel accepted;

    @Autowired
    @Qualifier("orders.skipped")
    PollableChannel rejected;

    @Test
    void eligibleEventGoesOnlyToNotifyChannel() {
        OrderEvent event = new OrderEvent(
                "evt-1001", "order-1001",
                OrderEventKind.CREATED,
                new BigDecimal("500.00"),
                true);

        Message<OrderEvent> message = MessageBuilder
                .withPayload(event)
                .setHeader("traceId", "trace-1001")
                .setHeader("businessCorrelationId", "order-1001")
                .build();

        assertTrue(input.send(message));

        Message<?> output = accepted.receive(1000);

        assertNotNull(output);
        assertEquals(event, output.getPayload());
        assertEquals("trace-1001",
                output.getHeaders().get("traceId"));
        assertEquals("order-1001",
                output.getHeaders().get("businessCorrelationId"));

        assertNull(rejected.receive(0));
    }

    @Test
    void nonEligibleEventGoesOnlyToDiscardChannel() {
        OrderEvent event = new OrderEvent(
                "evt-1002", "order-1002",
                OrderEventKind.CREATED,
                new BigDecimal("200.00"),
                false);

        Message<OrderEvent> message = MessageBuilder
                .withPayload(event)
                .setHeader("traceId", "trace-1002")
                .build();

        assertTrue(input.send(message));

        Message<?> discarded = rejected.receive(1000);

        assertNotNull(discarded);
        assertEquals(event, discarded.getPayload());
        assertEquals("trace-1002",
                discarded.getHeaders().get("traceId"));

        assertNull(accepted.receive(0));
    }

    @Test
    void paidEventDoesNotReachNotification() {
        OrderEvent event = new OrderEvent(
                "evt-1003", "order-1003",
                OrderEventKind.PAID,
                new BigDecimal("1000.00"),
                true);

        assertTrue(input.send(
                MessageBuilder.withPayload(event).build()));

        assertNotNull(rejected.receive(1000));
        assertNull(accepted.receive(0));
    }
}
~~~

What this test proves:

- `@Filter` is actually triggered by messages on `orders.events`.
- Qualifying payloads go to `orders.notify`.
- Non-qualifying payloads go to `orders.skipped` and do **not** leak into the notification branch.
- Headers for correlation/tracing travel with the forwarded message.
- Other event kinds are handled properly even when the amount meets the threshold.

**Note:** tests may share a cached Spring test context. Each test above drains the message it sent, but in large suites or parallel execution, create isolated fixtures/contexts or drain queues in a controlled manner to avoid cross-test interference.

### 14.1. Testing No Side Effects After Rejection

If `orders.notify` is wired to a real `NotificationService`, the most critical check is proving **rejected messages never invoke the sender**. You can use a fake sender with an `AtomicInteger` or a Mockito mock instead of the adapter:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

class FakeNotificationSender {
    private final AtomicInteger deliveries = new AtomicInteger();

    void deliver(OrderEvent event) {
        deliveries.incrementAndGet();
    }

    int deliveryCount() {
        return deliveries.get();
    }
}
~~~

In an extended integration test, wire the fake sender to the accepted channel via `@ServiceActivator`, send an event with opt-in false, and assert `deliveryCount()==0`. You do not need to send real emails to prove Filter semantics.

### 14.2. Unit Tests and Integration Tests Complement Each Other

| Policy unit test | Channel integration test |
|---|---|
| Tests domain logic | Tests Spring Integration wiring |
| No Spring context required | Requires context + endpoints/channels |
| Fast, easy to cover many edge cases | Catches mismatched channel or bean names |
| Does not prove headers are preserved | Observes the message after the Filter |
| Unaware whether `discardChannel` exists | Verifies accept/reject arrive at the right destination |

## 15. Preserving Headers and Correlation

A Filter typically forwards the **original message** to the accepted or discard branch; this preserves metadata on the message.

Example:

~~~java
Message<OrderEvent> input = MessageBuilder
        .withPayload(event)
        .setHeader("traceId", "trace-1001")
        .setHeader("tenantId", "shop-a")
        .setHeader("businessCorrelationId", "order-1001")
        .build();
~~~

In the notification flow, `traceId` links logs together and `businessCorrelationId` ties order steps together. `tenantId` should only be used for authorization decisions when it comes from a **verified source**; a client self-reporting `tenantId` does not prove permission.

### 15.1. Payload Filter Should Not Mutate the Message

~~~java
// Anti-pattern: predicate mutates a shared payload.
public boolean accept(MutableOrder payload) {
    payload.setStatus("PROCESSED");
    return payload.getAmount() > 100;
}
~~~

A message can be shared across multiple subscribers or flow asynchronously. If a Filter mutates the payload, other consumers may see unexpected state changes. Use immutable DTOs and a Transformer when you truly need to create a new payload.

### 15.2. Filter Does Not Automatically Set a Rejection Reason Header

A `boolean` does not indicate **why** a message was discarded. If specific reasons are needed, you can:

- Record metrics at a controlled observability step based on the same decision.
- Produce a `ValidationResult` or `EligibilityDecision` in a step before the Filter.
- Use a Router by reason code instead of a Filter if there are multiple reject branches.
- Use a meaningful exception if it is a contract violation and the caller must receive an error.

Do not attach headers onto the input message inside a predicate by mutating `MessageHeaders`; Spring message header maps do not permit direct mutation, and creating new messages is the responsibility of a Transformer/Header Enricher.

## 16. Designing Multi-Condition Filters

### 16.1. One Predicate with Multiple Conditions

~~~java
return event.kind() == OrderEventKind.CREATED
        && event.customerOptIn()
        && event.amount().compareTo(MIN_AMOUNT) >= 0;
~~~

Pros: one consistent decision, one place to review, and one test table. Cons: when there are too many branches or reason codes, it becomes harder to tell which condition triggered the rejection.

### 16.2. Chained Filters

~~~mermaid
flowchart LR
    I["OrderEvent"] --> K{"Filter: CREATED?"}
    K -->|Yes| O{"Filter: opt-in?"}
    O -->|Yes| A{"Filter: amount >= 100?"}
    A -->|Yes| N["Notification"]
    K -->|No| D["Skip"]
    O -->|No| D
    A -->|No| D
~~~

Pros: easy to measure rejection reasons at each branch and change conditions independently. Cons: more endpoints, must define the discard channel for each stage; context can be lost if one Filter drops messages silently.

Choose a single predicate or a Filter chain depending on complexity, need for reason codes, and observability. Avoid creating dozens of tiny Filters where nobody manages ordering or where rejected messages go.

### 16.3. Time-Dependent Rules

If the notification branch only operates during business hours, do not let the predicate call `LocalTime.now()` directly and make outcomes hard to reproduce. Pass the **event timestamp** or a reliable business-calendar snapshot as input data. For rules requiring runtime state, be explicit about whether filtering happens at receipt time or processing time.

## 17. Errors, Retry, and Error Channels

A `false` condition is not an exception. When a predicate throws an exception, the system must know the **cause**:

| Situation | Category | Appropriate handling |
|---|---|---|
| CREATED but opt-in false | Normal rejection | Discard/skip, do not retry |
| PAID in CREATED notification branch | Normal rejection | Skip |
| Payload missing required field | Validation failure | Reject per contract, with reason |
| Wrong payload type | Binding/conversion failure | Error handling at adapter/endpoint |
| Enrich API timeout | Infrastructure error before Filter | Bounded retry |
| Filter code NPE due to bug | Program bug | Error flow, investigate |
| Notification handler fails with 503 | Downstream failure | Separate retry/idempotency |

### 17.1. Error Channel Differs from Discard Channel

- **discardChannel** receives messages that the Filter **intentionally rejects** per policy.
- **errorChannel** handles errors via the topology's messaging/error handling mechanism, typically critical in asynchronous flows.
- On a synchronous **DirectChannel**, exceptions may propagate back to the thread calling `send()`; do not assume declaring an errorChannel sends every exception there.
- If a Filter is configured with `throwExceptionOnRejection`, a rejection may take the exception path; design carefully to avoid double-handling alongside discard.

### 17.2. Retries Can Cause Duplicate Side Effects

Pure, side-effect-free filtering is a solid foundation for retries. However, if a message already passed the Filter and `NotificationService` sent an email before a later step failed, replaying the entire event could send the email again. Use a stable `eventId` and idempotency in downstream handlers, rather than relying solely on `MessageHeaders.ID` as a business key across replays.

## 18. Observing Filters in Operations

In systems with multiple data sources, measure accept/reject rates and reasons safely.

| Metric | Question | Suggestion |
|---|---|---|
| `filter_accepted_total{flow}` | How many messages passed the filter? | Low-cardinality flow label |
| `filter_rejected_total{flow,reason}` | Which cases were rejected? | Stable reason codes |
| `filter_errors_total{flow,type}` | Did the filter hit exceptions? | Separate exceptions from rejections |
| `filter_duration_seconds{flow}` | Is the predicate abnormally slow? | Pure predicates should be cheap |
| `notification_deliveries_total` | How many did the handler deliver? | Not identical to accepted |
| `traceId` / `businessCorrelationId` | Which message was affected? | Log/trace only, avoid metric labels |

### 18.1. Do Not Log Sensitive Payloads

Payloads may contain emails, addresses, or payment details. Do not log the entire object on every Filter rejection just for diagnostics. Log `eventId`, flow, outcome, reason code, and correlation ID under an appropriate security policy.

### 18.2. Sudden Rejection Spikes Can Signal Upstream Bugs

If the rejection rate jumps from 5% to 80%, the predicate is not necessarily wrong: the producer may have changed its schema, a converter may map enums differently, or opt-in may now default to false. Set ratio alerts and inspect input data; a "code-correct" Filter can still drop messages unexpectedly when an upstream contract shifts.

## 19. Common Mistakes

### Mistake 1 — Using Filter as a Substitute for Transformer

**Symptom:** the predicate both normalizes amount/region and returns a boolean. Other handlers see a mutated payload.

**Fix:** create a Transformer for normalization; let Filter only make the accept/reject decision.

### Mistake 2 — Not Configuring a Discard Channel for Important Messages

**Symptom:** some orders disappear downstream with no logged reason.

**Fix:** configure `discardChannel`, audit/metrics, or rejection replies per contract. For events meant only to select items of interest, silent dropping can be acceptable but must be an intentional decision.

### Mistake 3 — Treating `send()==true` as Notification Success

**Symptom:** the producer reports email sent successfully simply because sending to the input channel succeeded.

**Fix:** measure outcomes at `NotificationService`/adapter, do not infer from message channel return values.

### Mistake 4 — Predicate Calling APIs/DB

**Symptom:** timeouts make the Filter slow, hard to test, and retry ownership unclear.

**Fix:** separate enrichment before the Filter, pass a verified data snapshot, and configure timeout/retry on the external-system endpoint.

### Mistake 5 — Unchecked Payload Casting

**Symptom:** messages with a String or Map payload arrive at a handler expecting `OrderEvent`, causing conversion errors.

**Fix:** use decoders/validation at ingress and clear payload contracts; test with real data sources.

### Mistake 6 — Mistaking a Publish–Subscribe Branch Filter for Filtering the Whole Event

**Symptom:** the designer assumes a notification rejection also stops audit/analytics from receiving the event.

**Fix:** clarify whether the Filter sits before or after fan-out; with multiple subscribers, each branch decides independently.

### Mistake 7 — Dropping Splitter Parts Without Updating the Release Strategy

**Symptom:** the Aggregator waits endlessly because it never receives all parts.

**Fix:** explicitly define behavior for discarded parts, sequence size, timeouts, and partial groups.

### Mistake 8 — Changing Filter Rules Without Boundary Tests

**Symptom:** orders of exactly 100.00 get dropped after changing `>=` to `>`.

**Fix:** write parameterized tests around boundaries 99.99, 100.00, and 100.01; verify opt-in, event kind, and overlapping conditions.

### Mistake 9 — Unbounded Retries on Rejections

**Symptom:** events with opt-in false are retried hundreds of times.

**Fix:** do not retry `false` policy decisions; only retry recoverable errors with backoff and bounded attempts.

### Mistake 10 — Relying on Untrusted Fields for Business Conditions

**Symptom:** clients self-declare `isPremium=true` to enter the priority branch.

**Fix:** perform authentication/authorization and trusted enrichment at the ingress boundary; never treat client-supplied data as proof of privilege.

## 20. Hands-on Exercises

**Exercise 1 — Pure Java Predicate.** Write `OrderNotificationPolicy` for `CREATED` events with amount >= 100 and opt-in. Use `@ParameterizedTest` with at least 8 inputs; verify boundaries and other event kinds.

**Exercise 2 — @Filter.** Create input `orders.events`, accepted `orders.notify`, and rejected `orders.skipped`. Send messages with `traceId` and assert each message reaches exactly one channel.

**Exercise 3 — Java DSL.** Rewrite the flow above using `IntegrationFlow.filter(OrderEvent.class, ...)`. Keep the same policy and JUnit assertions; make sure not to declare two competing consumers on the same `DirectChannel` simultaneously.

**Exercise 4 — Handling Rejections.** Attach a handler receiving from `orders.skipped` that logs `eventId` and a safe reason code. Distinguish opt-in false from `PAID`/`CANCELLED` events. Do not log the entire payload.

**Exercise 5 — Combining with Transformer.** Accept a `RawOrderEvent` from JSON with string amounts, decode/normalize into `OrderEvent`, and then filter. Test that formatting differences do not cause valid events to be wrongly rejected.

**Exercise 6 — Publish–Subscribe.** Make Audit and Analytics always receive messages while the Notification Filter only accepts a subset. Verify that events filtered out at Notification are still received by Audit.

**Exercise 7 — Splitter/Aggregator.** Split an order into multiple lines, filter out zero-amount or invalid lines, then aggregate them back. Design a release strategy/timeout so the Aggregator does not wait forever for discarded lines.

**Exercise 8 — Error Flow.** Have the predicate intentionally throw an exception on a special input. Compare outcomes through a `DirectChannel` versus an asynchronous flow with an error channel. Do not treat exceptions as normal discards.

**Exercise 9 — Idempotency.** Simulate a `NotificationService` sending an email successfully before a downstream step fails and the message is replayed. Use `eventId` to prevent duplicate sends; explain why a pure Filter cannot solve downstream side effects.

### Self-Check Questions

1. How does filtering by payload differ from a Header-Based Router?
2. Is a predicate returning `false` automatically a system error?
3. When no discard channel is configured, what can happen to a rejected message?
4. Why can't a boolean-returning `@Filter` generate rejection reason details on its own?
5. Should a valid payload with opt-in false take the rejection path or throw an exception?
6. Why is `BigDecimal.compareTo` suitable for monetary thresholds?
7. Does a Filter mutate the message payload or headers?
8. When do you need a Transformer before a Filter?
9. Why isn't testing a pure policy sufficient to prove the output channel exists?
10. If a Filter sits inside one Publish–Subscribe branch, are other branches affected?
11. If a Filter drops items after a Splitter, what must the Aggregator account for?
12. Why shouldn't messages with opt-in false be retried indefinitely?
13. How do you distinguish a message channel result from actual email delivery?
14. What metadata should be preserved to trace accepted and rejected messages?

## 21. Pre-Deployment Checklist

- [ ] Payload type and ingress validation are defined.
- [ ] Predicate only performs accept/reject, without mutating payload/headers or causing side effects.
- [ ] Decision table covers thresholds, boundary values, and overlapping conditions.
- [ ] `@Filter` or Java DSL is declared properly without creating unintended competing consumers.
- [ ] Both output channel and discard channel (if needed) exist and have handlers per contract.
- [ ] Normal rejections are distinguished from exceptions/error flows.
- [ ] `send()==true` is not assumed to mean business processing completed.
- [ ] Required trace/correlation/headers are preserved across accepted/rejected paths.
- [ ] For Filters after a Splitter, sequence/correlation and release strategy have been addressed.
- [ ] For Publish–Subscribe, it is clear whether the Filter applies before fan-out or on a single branch.
- [ ] Handlers with side effects enforce idempotency when messages may replay.
- [ ] Client-supplied payload fields are not trusted for security decisions.
- [ ] Both predicate unit tests and channel send/receive integration tests exist.
- [ ] Metrics for accepted/rejected/error and safe payload logging rules are in place.
- [ ] Retry, timeout, and infrastructure error handling are separated from deterministic rejections.

## 22. Summary

**Filtering by payload** is a selection step in Spring Integration: when **the predicate returns `true`**, the message is allowed to proceed; when it **returns `false`**, the message is discarded or sent to `discardChannel` per configuration. A Filter's job is neither to alter payloads like a Transformer nor to select among multiple business routes like a Router. Expressing policies as **pure functions** keeps them easy to understand, fast to test, and free of unexpected side effects during retries.

In **SPRING_INTEGRATION_PATTERN**, a reliable Filter belongs after appropriate decoding/validation, runs before expensive handlers when conditions can be evaluated early, and provides clear rejection and observability paths. When combined with Publish–Subscribe, Splitter/Aggregator, Gateway, Router, retry, and error channels, understand the Filter's scope, preserve metadata, and test the real topology. Doing these well yields message systems that are loosely coupled, extensible, and easier to operate.

### References

- Spring Integration Reference — Filter: https://docs.spring.io/spring-integration/reference/filter.html
- Spring Integration Reference — Java DSL: https://docs.spring.io/spring-integration/reference/dsl.html
- Spring Integration Reference — Message Channel Implementations: https://docs.spring.io/spring-integration/reference/channel/implementations.html
- Spring Integration API — Filter annotation: https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/Filter.html
- Spring Integration API — MessageFilter: https://docs.spring.io/spring-integration/api/org/springframework/integration/filter/MessageFilter.html
- JUnit 5 User Guide — Parameterized Tests: https://junit.org/junit5/docs/current/user-guide/#writing-tests-parameterized-tests
