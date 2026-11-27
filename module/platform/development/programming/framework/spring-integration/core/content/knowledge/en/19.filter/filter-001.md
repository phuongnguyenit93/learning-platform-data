# What is a Message Filter

This lesson belongs to the **Filter** chapter of the **Spring Integration Core (`SPRING_INTEGRATION_CORE`)** module. The goal is to understand how an endpoint decides which messages proceed, and then place that decision into a flow consisting of `Message`, `MessageChannel`, a gateway, and Java DSL. The example uses orders to connect filters with transformers, routers, error handling, and testing enterprise integration patterns.

After this lesson, you can:

- Explain the meaning of `true`, `false`, and exceptions in a message selector.
- Configure the accepted branch and the discarded branch using Java DSL or `@Filter`.
- Choose an appropriate policy for discarded messages.
- Test outcomes on channels instead of inferring them from the return value of `send()`.

## 1. The problem a Message Filter solves

Suppose a service receives all order events from the sales system, but the inventory reservation stage only processes confirmed orders. `DRAFT`, `CANCELLED`, or incomplete events can still appear on the input stream.

If every downstream component checks this condition on its own, the rule gets duplicated. A **Message Filter** placed at the boundary of the stage can evaluate the check once and only let matching messages continue.

In Enterprise Integration Patterns, a Message Filter selects messages based on a criterion; non-matching messages do not reach the protected output. In this problem, the criterion is "whether the order is eligible for inventory reservation". [Source: Enterprise Integration Patterns — Message Filter](https://www.enterpriseintegrationpatterns.com/patterns/messaging/Filter.html).

~~~mermaid
flowchart LR
    A["orders.input"] --> F{"Eligible?"}
    F -->|"true"| B["orders.accepted"]
    F -->|"false"| C["orders.rejected if configured"]
    B --> D["Inventory reservation stage"]
~~~

The name "filter" here refers to **selecting the entire message**. For example, dropping a `DRAFT` order event is message filtering; removing a phone number field from JSON is modifying content and should be represented by a data transformation step.

A filter does not automatically delay a flow until the condition becomes true. A `DRAFT` order today is not held automatically to wait for it to transition to `CONFIRMED` tomorrow. To handle such changes, the system needs a new event or a dedicated storage and reprocessing mechanism.

## 2. Where does a Filter sit in Spring Integration?

A `Message<T>` consists of a payload and headers. The payload carries data such as an order; headers carry context such as the sender source or correlation ID. A message's header structure cannot be modified directly, though the payload object may still be mutable depending on application design. Therefore, a predicate should only read data. [Source: Spring Integration — Message](https://docs.spring.io/spring-integration/reference/message.html).

Roles in the flow:

| Component | Responsibility in the example |
| --- | --- |
| `Message<Order>` | Carries the order and processing context. |
| Input channel | Delivers the message to the filter endpoint. |
| Filter endpoint | Receives the message and performs selection, forwarding, or discard branch handling. |
| Selector | Holds the acceptance condition and returns a boolean. |
| Output channel | Receives accepted messages. |
| Discard channel | Receives rejected messages when configured. |
| Gateway | Provides a Java interface for callers to interact with the flow; requires defining the response contract. |

In a typical configuration, `MessageFilter` is the handler that performs filtering inside the endpoint. The selector only decides; it is neither a channel nor does it send messages to a destination on its own. [Source: MessageFilter API](https://docs.spring.io/spring-integration/api/org/springframework/integration/filter/MessageFilter.html).

Java DSL describes how channels and endpoints are wired together; the framework registers the components that execute the flow in the application context. The `.filter(...)` call represents the filtering step in that description. [Source: Spring Integration 6.5 — DSL Basics](https://docs.spring.io/spring-integration/reference/6.5/dsl/java-basics.html).

### Comparison with closely related steps

| Component | Design question | Example |
| --- | --- | --- |
| Filter | May this message pass through to this stage? | Accept only confirmed orders. |
| Router | Which destination should this message go to? | International orders to customs flow, domestic orders to domestic delivery flow. |
| Transformer | What form should the data be converted into? | Convert order JSON into an `Order`. |
| Service activator | What action needs to be performed? | Call the inventory reservation service. |
| Aggregator | When is a group of messages ready to be combined? | Combine inventory check results for an order. |

Read more about the corresponding roles at [Router](https://docs.spring.io/spring-integration/reference/router.html), [Transformer](https://docs.spring.io/spring-integration/reference/transformer.html), and [Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html).

A filter with a discard channel can express a two-way choice. When the business domain already has multiple outcome categories such as "eligible", "needs approval", "cancelled", and "missing data", a router usually makes that structure easier to read than a nested chain of filters.

## 3. The selector contract: accept, reject, and error

`MessageSelector` is a functional interface with the method `boolean accept(Message<?> message)`. You can write a dedicated implementation, a lambda, or a method reference. [Source: MessageSelector API](https://docs.spring.io/spring-integration/api/org/springframework/integration/core/MessageSelector.html).

Example selecting only messages whose `trusted` header is boolean `true`:

~~~java
import org.springframework.integration.core.MessageSelector;

MessageSelector trustedSource = message ->
        Boolean.TRUE.equals(message.getHeaders().get("trusted"));
~~~

Under this example's convention, a missing header or a string value `"true"` is not accepted. Data type conventions must be agreed upon with the message producer; the selector does not automatically coerce values that merely look equivalent.

Three outcomes to distinguish:

| Evaluation outcome | Meaning |
| --- | --- |
| `true` | Accept the message and pass it to the next step. |
| `false` | Reject according to the selection rule; apply the rejection policy. |
| Throws an exception | Cannot evaluate normally; the flow encounters an execution error. |

For example, a `DRAFT` status can be a valid business outcome leading to `false`. By contrast, an unreachable lookup service does not prove that the order is ineligible.

The following snippet blurs that distinction:

~~~java
// Avoid turning every failure into a valid rejection outcome.
try {
    return eligibilityService.isEligible(order);
} catch (Exception exception) {
    return false;
}
~~~

If a rule must call an external service, explicitly decide how transient failures are retried, routed to an error flow, or reported back. Do not mask failures with `false` just to keep the flow running.

An easily testable selector typically has these characteristics:

- A business-meaningful name for the condition.
- Same data and same context yield the same result.
- Does not mutate payload, reserve inventory, or send emails.
- Explicitly handles missing data instead of accidentally throwing a `NullPointerException`.

## 4. What happens when the selector returns false?

Spring Integration provides two key options:

- `discardChannel`: where rejected messages are sent.
- `throwExceptionOnRejection`: whether to throw `MessageRejectedException` on rejection.

The behavior table below assumes the selector returns `false` and sending to the discard channel, if present, completes normally:

| Discard channel | `throwExceptionOnRejection` | Behavior |
| --- | --- | --- |
| Not configured | `false` | Not sent to the output channel; message is dropped from the main branch. |
| Configured | `false` | Sent to the discard channel; no exception is raised solely for rejection. |
| Not configured | `true` | Throws `MessageRejectedException`. |
| Configured | `true` | Sent to the discard channel and then throws `MessageRejectedException`. |

The default value of `throwExceptionOnRejection` is `false`. Configuring a discard channel does not disable this option. [Source: FilterEndpointSpec API](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/FilterEndpointSpec.html).

Since Spring Integration 6.1, rejecting a message with neither a discard channel nor exception throwing enabled logs a warning. To intentionally drop messages without this default warning, you can point the discard channel to `nullChannel`. This is an explicit choice to drop the message. [Source: Spring Integration — Filter](https://docs.spring.io/spring-integration/reference/filter.html).

Example of a DSL snippet using that policy:

~~~java
.filter(Order.class,
        OrderFilterConfiguration::eligible,
        endpoint -> endpoint
                .discardChannel("nullChannel")
                .throwExceptionOnRejection(false))
~~~

For important messages, an audit branch or explicit response is usually more useful than dropping immediately. In the order example below, we keep rejected messages in a queue for observation.

Additional notes:

- The discard channel receives the rejected message, not an `ErrorMessage` by default.
- A predicate returning `false` does not automatically route the message to the global `errorChannel`.
- If sending to the discard channel itself fails, that is an error in the rejection-handling branch.
- The name "discard" does not guarantee that the data has been persisted or placed into a broker dead-letter queue.

## 5. Complete example: accepting only eligible orders

### 5.1. Rules for the hands-on exercise

In this example, valid messages for the next stage must have:

1. A payload of exact type `Order`.
2. A non-blank order ID.
3. A status equal to `CONFIRMED`.
4. A total greater than `0` and not exceeding `10,000,000` currency units.

Currency units are assumed consistent across the exercise. The upper limit is an illustrative rule for the automated stage; orders exceeding the limit are routed to the rejection branch for separate handling.

| Input data | Expected outcome |
| --- | --- |
| `O-101`, `CONFIRMED`, `250000` | Accepted. |
| `O-102`, `DRAFT`, `250000` | Rejected. |
| `O-103`, `CONFIRMED`, `0` | Rejected. |
| `O-104`, `CONFIRMED`, `10000000` | Accepted at upper boundary. |
| `O-105`, `CONFIRMED`, `10000000.01` | Rejected. |
| Blank order ID | Rejected. |
| String payload instead of `Order` | Rejected by type check. |

### 5.2. Requirements for running the example

The configuration below uses Java 17 syntax and Spring Integration 6.x Java DSL. The project needs the `org.springframework.integration:spring-integration-core` dependency along with compatible Spring dependencies; if using Spring Boot, let Boot's BOM manage versions and you can use `spring-boot-starter-integration`.

The example uses a plain application context to keep endpoints and channels clear. No external broker or service is required. Tests use JUnit Jupiter.

The entire following class can be placed in `OrderFilterConfiguration.java` in the practice project:

~~~java
package example.integration.filter;

import java.math.BigDecimal;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.core.MessageSelector;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class OrderFilterConfiguration {

    private static final BigDecimal MAX_TOTAL =
            new BigDecimal("10000000");

    public record Order(
            String id,
            String status,
            BigDecimal total) {
    }

    public static boolean eligible(Order order) {
        return order != null
                && order.id() != null
                && !order.id().isBlank()
                && "CONFIRMED".equals(order.status())
                && order.total() != null
                && order.total().compareTo(BigDecimal.ZERO) > 0
                && order.total().compareTo(MAX_TOTAL) <= 0;
    }

    @Bean(name = "orders.input")
    public MessageChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean(name = "orders.accepted")
    public QueueChannel ordersAccepted() {
        return new QueueChannel();
    }

    @Bean(name = "orders.rejected")
    public QueueChannel ordersRejected() {
        return new QueueChannel();
    }

    @Bean
    public MessageSelector eligibleOrderSelector() {
        return message ->
                message.getPayload() instanceof Order order
                        && eligible(order);
    }

    @Bean
    public IntegrationFlow orderEligibilityFlow(
            @Qualifier("eligibleOrderSelector")
            MessageSelector selector) {

        return IntegrationFlow.from("orders.input")
                .filter(Message.class, selector::accept,
                        endpoint -> endpoint
                                .id("orderEligibilityFilter")
                                .discardChannel("orders.rejected")
                                .throwExceptionOnRejection(false))
                .channel("orders.accepted")
                .get();
    }
}
~~~

In this example, `Message.class` is passed to the `filter` overload so the selector receives the entire message. If a payload class such as `Order.class` is passed, the lambda argument is the payload of that type; the framework may attempt type conversion when needed. Therefore, a typed overload should not be assumed to automatically return `false` for any mismatched payload type. [Source: BaseIntegrationFlowDefinition API — filter](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/BaseIntegrationFlowDefinition.html).

### 5.3. Explaining the design choices

`eligible(Order)` contains only business rules so it can be unit tested independently. `eligibleOrderSelector` adds the payload type check at the messaging boundary. In this lesson, a wrong type is treated as a case to route to `orders.rejected`; a real-world application might choose to raise an error if it represents a serious contract violation.

`BigDecimal.compareTo(...)` is appropriate for comparing monetary amounts in rules. Do not use `equals` for greater-than/less-than comparisons, and do not construct monetary values from `double` literals.

`orders.input` is a `DirectChannel`: with this configuration, the filter endpoint is invoked on the sender's thread. The two output channels are `QueueChannel` instances so the exercise can actively retrieve results using `receive(...)`. Queues here store messages in memory by default; they are not durable storage. [Source: Spring Integration — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

The flow ends at the two queues for easy observation. No downstream stage automatically pulls orders to reserve inventory yet. If you change an output to a `DirectChannel`, there must be a suitable subscriber for it; when using a queue as the input to a subsequent endpoint, a polling mechanism must be configured.

### 5.4. Sending messages and observing outcomes

The snippet below is code inside a test method using the configuration class above:

~~~java
try (var context =
        new org.springframework.context.annotation
                .AnnotationConfigApplicationContext(
                        OrderFilterConfiguration.class)) {

    var input = context.getBean(
            "orders.input",
            org.springframework.messaging.MessageChannel.class);

    var accepted = context.getBean(
            "orders.accepted",
            org.springframework.integration.channel.QueueChannel.class);

    var rejected = context.getBean(
            "orders.rejected",
            org.springframework.integration.channel.QueueChannel.class);

    var order = new OrderFilterConfiguration.Order(
            "O-101",
            "CONFIRMED",
            new java.math.BigDecimal("250000"));

    var message = org.springframework.messaging.support.MessageBuilder
            .withPayload(order)
            .setHeader("correlationId", "checkout-101")
            .build();

    boolean sent = input.send(message);

    System.out.println("send = " + sent);
    System.out.println("accepted = " + accepted.receive(0));
    System.out.println("rejected = " + rejected.receive(0));
}
~~~

With the data above, the accepted queue contains one message and the rejected queue is empty. If you change the status to `DRAFT`, the result is reversed.

`send` can still be `true` in both cases: the message was delivered and the endpoint processed it normally, even when the decision was to reject the message. This value is not the result of `selector.accept(...)`. Concluding that "the order was accepted" must be based on the reply contract or the result at the business output.

`receive(0)` retrieves a message immediately if available; an empty queue returns `null`. In the synchronous example, once `send` finishes, filtering and queuing have completed. When moving to an asynchronous flow, tests must use an appropriate timeout.

## 6. Ways to express filtering conditions

The snippets in this section are **alternatives**—do not register all of them onto the same `orders.input`. Multiple consumers on a point-to-point channel change how messages are dispatched.

### 6.1. Payload-only lambda

When the input contract already guarantees the payload is an `Order`, the filtering step can be shortened:

~~~java
return IntegrationFlow.from("orders.input")
        .filter(OrderFilterConfiguration.Order.class,
                OrderFilterConfiguration::eligible,
                endpoint -> endpoint
                        .discardChannel("orders.rejected")
                        .throwExceptionOnRejection(false))
        .channel("orders.accepted")
        .get();
~~~

This style expresses the order rule clearly. If you need to inspect headers or handle different payload types yourself, use the full `Message` as in the main configuration.

### 6.2. Header-based condition

An ingestion gateway might allow only events from an authenticated source to proceed:

~~~java
return IntegrationFlow.from("trusted.input")
        .filter(Message.class,
                message -> Boolean.TRUE.equals(
                        message.getHeaders().get("trusted")),
                endpoint -> endpoint
                        .discardChannel("trusted.rejected"))
        .channel("trusted.accepted")
        .get();
~~~

The `trusted.*` channels must be declared in the corresponding configuration. The `trusted` header must be set at a trusted boundary, such as after verifying sender identity; data arbitrarily attached by the caller is not sufficient proof.

If filtering by both header and payload simultaneously, name the rule such as `eligibleTrustedOrder` or split it into two named steps, depending on observability needs. Two consecutive filters mean both conditions must pass; a message rejected at the first step does not reach the second step.

### 6.3. Short SpEL expression

Example accepting only sources with a boolean header:

~~~java
return IntegrationFlow.from("trusted.input")
        .filter("headers['trusted'] == true",
                endpoint -> endpoint
                        .discardChannel("trusted.rejected"))
        .channel("trusted.accepted")
        .get();
~~~

This expression is static configuration managed by the application. For conditions with many fields, multiple branches, or needing explanation, a named Java method is usually easier to test and maintain than a long expression. Spring Integration supports configuring filters with expressions. [Source: Spring Integration — Filter](https://docs.spring.io/spring-integration/reference/filter.html).

### 6.4. @Filter annotation

Another option is to register a bean with a boolean method annotated with `@Filter`:

~~~java
package example.integration.filter;

import org.springframework.integration.annotation.Filter;

public class OrderPolicy {

    @Filter(
            inputChannel = "orders.input",
            outputChannel = "orders.accepted",
            discardChannel = "orders.rejected",
            throwExceptionOnRejection = "false")
    public boolean accept(OrderFilterConfiguration.Order order) {
        return OrderFilterConfiguration.eligible(order);
    }
}
~~~

For this option to work, register `OrderPolicy` as a Spring bean, keep the channel beans and `@EnableIntegration`, and remove the Java DSL `orderEligibilityFlow` bean. Do not register both endpoints simultaneously for the same test run.

The `throwExceptionOnRejection` attribute on the annotation takes a string, whereas in Java DSL it takes a boolean. The annotated method in the example accepts an `Order` payload, so it does not preserve the policy for handling arbitrary payload types like the selector in the main configuration. [Source: @Filter API](https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/Filter.html).

## 7. Rejection, error handling, and gateway

### 7.1. Business rejection is not necessarily a technical error

In an order system, you can choose:

| Situation | Illustrative policy |
| --- | --- |
| `DRAFT` event not belonging to the current stage | Route to an audited discard branch. |
| Total exceeds automated limit | Route to a manual approval stage. |
| Missing order ID | Respond or record a data contract violation. |
| Lookup service unreachable | Technical error flow, with a retry policy if appropriate. |

This is an application design decision. There is no universal rule that every filtered-out message must be retried or can simply be dropped.

If `throwExceptionOnRejection(true)` is enabled, an exception is used to signal that the selector rejected the message. `MessageRejectedException` belongs to Spring Messaging's exception hierarchy. [Source: MessageRejectedException API](https://docs.spring.io/spring-integration/api/org/springframework/integration/MessageRejectedException.html).

With a pure condition and unchanged data, immediately retrying the same `DRAFT` message will keep rejecting it. Retrying is only useful when the cause is likely to change and system policy permits it.

### 7.2. Where exceptions go depends on how the flow is executed

In a synchronous flow over a `DirectChannel`, errors can propagate back to the sender. Do not assume that merely having an `errorChannel` bean causes all synchronous exceptions to be routed there.

In a flow executed by a poller or framework asynchronous mechanisms, an error handler can create an `ErrorMessage` and send it to the `errorChannel` header or the default error channel. Exact behavior depends on the initiating component and error handler configuration. [Source: Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

In particular, if you both send the rejected message to a discard channel and throw an exception, external retry mechanisms may cause the discard branch to run repeatedly. Branches that write audit logs, send emails, or create approval requests need to account for duplicates.

### 7.3. A gateway needs a complete response contract

Suppose a gateway has the method:

~~~java
OrderResult submit(Order order);
~~~

If the flow filters out the message without producing a reply or throwing an exception, the caller is still waiting for `OrderResult`. Having no reply can lead to a timeout, returning `null`, or error-reporting behavior depending on configuration; do not use it as an implicit business signal. [Source: Spring Integration — Messaging Gateways, No Response section](https://docs.spring.io/spring-integration/reference/gateway.html#gateway-no-response).

For an API that must return a result for every request, you can choose one of these approaches:

- Use a router so both the accepted branch and the rejected branch produce an explicit `OrderResult`.
- Have rejection throw an exception and map errors appropriately at the call boundary.
- Use a one-way send contract when the caller genuinely does not need a business processing result.

Simply setting the discard channel to a queue does not automatically reply to the gateway. If you choose a rejection branch that responds, you must connect that branch to a step that produces a reply and verify the reply return path.

The configuration in section 5 is an exercise in sending messages directly and reading queues; it is not yet a complete request–reply flow.

## 8. Misleading interactions

### 8.1. Point-to-point is not broadcast

Suppose two filters are registered on the same `DirectChannel`:

- Filter A selects domestic orders.
- Filter B selects international orders.

Do not assume every message will be evaluated by both A and B. `DirectChannel` has point-to-point semantics and dispatching may involve load balancing/failover. If you need to branch by order type, use a router; if every subscriber must see the event, consider `PublishSubscribeChannel` and its error-handling rules. [Source: Spring Integration — Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

Having A return `false` and complete normally is also not equivalent to an exception that causes the dispatcher to automatically try B. Configuring a selective consumer based on failover is a different mechanism and is unnecessary for this exercise.

### 8.2. A filter after a splitter can leave an aggregator short of items

For example, a splitter produces three messages with `sequenceSize = 3`. If a filter drops one message before the aggregator, an aggregator using the default sequence-size release condition may receive only two messages and never release the group.

This is a consequence of changing the number of messages mid-stream. You must design the release condition, timeout, or representation of rejected outcomes accordingly; do not arbitrarily modify sequence headers just to force the group out of waiting. [Source: Spring Integration — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html).

### 8.3. A boolean does not carry a rejection reason

`false` does not distinguish between "missing ID", "unconfirmed", or "over limit". Nor does the discard channel automatically receive a corresponding reason field.

If the system needs detailed reasons, compute a structured evaluation result, for example:

~~~java
public record EligibilityDecision(
        boolean accepted,
        String reasonCode) {
}
~~~

An evaluation step can produce that result before a router chooses the branch. Avoid re-evaluating the same condition that calls an external service in both the filter and the discard handler, because two evaluations can be expensive and return different results.

### 8.4. A filter does not provide durability or broker acknowledgment

Filtering in an application flow does not determine the entire message lifecycle in Kafka, AMQP, or JMS. Offset commits, acknowledgements, rollbacks, and redeliveries also depend on the adapter, transaction, and protocol error-handling configuration.

Therefore, clearly distinguish "rejected from this stage" from "acknowledged at the source" or "stored for reprocessing". In this exercise, there are only in-memory channels and no broker.

## 9. Testing filters by observable outcomes

Two layers should be tested:

1. **Rule**: `eligible(Order)` returns the expected results at boundary values.
2. **Flow wiring**: messages go to the right channel, the other branch receives nothing, and necessary headers are preserved.

Spring Integration provides testing support modules for complex flows. The example below uses a real application context and in-memory queues, so only JUnit Jupiter is needed for tests; endpoint mocking is not needed yet. [Source: Spring Integration — Testing Support](https://docs.spring.io/spring-integration/reference/testing.html).

Test class corresponding to the Java DSL configuration in section 5:

~~~java
package example.integration.filter;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class OrderFilterFlowTest {

    @Test
    void acceptedOrderGoesOnlyToAcceptedChannel() {
        try (var context = new AnnotationConfigApplicationContext(
                OrderFilterConfiguration.class)) {

            MessageChannel input = context.getBean(
                    "orders.input", MessageChannel.class);
            QueueChannel accepted = context.getBean(
                    "orders.accepted", QueueChannel.class);
            QueueChannel rejected = context.getBean(
                    "orders.rejected", QueueChannel.class);

            var order = new OrderFilterConfiguration.Order(
                    "O-101", "CONFIRMED", new BigDecimal("250000"));

            Message<?> original = MessageBuilder.withPayload(order)
                    .setHeader("correlationId", "checkout-101")
                    .build();

            assertTrue(input.send(original));

            Message<?> result = accepted.receive(0);
            assertNotNull(result);
            assertEquals(order, result.getPayload());
            assertEquals("checkout-101",
                    result.getHeaders().get("correlationId"));
            assertNull(rejected.receive(0));
        }
    }

    @Test
    void draftOrderGoesOnlyToRejectedChannelEvenWhenSendSucceeds() {
        try (var context = new AnnotationConfigApplicationContext(
                OrderFilterConfiguration.class)) {

            MessageChannel input = context.getBean(
                    "orders.input", MessageChannel.class);
            QueueChannel accepted = context.getBean(
                    "orders.accepted", QueueChannel.class);
            QueueChannel rejected = context.getBean(
                    "orders.rejected", QueueChannel.class);

            var order = new OrderFilterConfiguration.Order(
                    "O-102", "DRAFT", new BigDecimal("250000"));

            Message<?> original = MessageBuilder.withPayload(order)
                    .setHeader("correlationId", "checkout-102")
                    .build();

            assertTrue(input.send(original));
            assertNull(accepted.receive(0));

            Message<?> result = rejected.receive(0);
            assertNotNull(result);
            assertEquals(order, result.getPayload());
            assertEquals("checkout-102",
                    result.getHeaders().get("correlationId"));
        }
    }

    @Test
    void unexpectedPayloadTypeIsRejectedByTheMessageSelector() {
        try (var context = new AnnotationConfigApplicationContext(
                OrderFilterConfiguration.class)) {

            MessageChannel input = context.getBean(
                    "orders.input", MessageChannel.class);
            QueueChannel accepted = context.getBean(
                    "orders.accepted", QueueChannel.class);
            QueueChannel rejected = context.getBean(
                    "orders.rejected", QueueChannel.class);

            input.send(MessageBuilder.withPayload("not-an-order").build());

            assertNull(accepted.receive(0));
            Message<?> result = rejected.receive(0);
            assertNotNull(result);
            assertEquals("not-an-order", result.getPayload());
        }
    }
}
~~~

Each test opens its own context to prevent messages from previous tests from remaining in queues. The first test verifies business data and headers; it does not assert that the output message shares the same object identity as the input message.

To extend rule coverage, use the following inputs when testing `eligible(Order)` directly:

| Variation from valid order | Result |
| --- | --- |
| `total = 0` | `false` |
| `total < 0` | `false` |
| `total = 10000000` | `true` |
| `total = 10000000.01` | `false` |
| `total = null` | `false` |
| `id = null` or blank string | `false` |
| `status = null` or `"confirmed"` | `false` |
| Parameter `order = null` | `false` |

The `order = null` case belongs to pure function testing; do not construct a message with a null payload to simulate it.

When changing rejection policies, add corresponding tests:

- Enable exceptions and use a single subscriber on `DirectChannel`: check the error observed by the sender.
- Use both a discard channel and an exception: verify the message enters the discard channel before the error is raised.
- Have the selector intentionally throw a technical error: verify it is not treated as a normal rejection.
- Switch to async: wait for results within a bounded timeout rather than relying on arbitrary `Thread.sleep`.
- Attach a request–reply gateway: verify both accepted and rejected outcomes complete according to contract.

The test snippets in this lesson are practice code to run in a project with suitable dependencies; this article does not substitute for running your project's test suite.

## 10. Choosing a filter and placing it properly

One way to make decisions for an order flow:

1. Identify the protected stage, such as inventory reservation.
2. Normalize required data before evaluation if the input is JSON or an external format.
3. Name the condition such as `eligibleForReservation`.
4. Specify unsuitable data and non-evaluatable errors separately.
5. Choose the destination for rejected messages, along with auditing or response needs.
6. Check impacts on gateways, sequences, and transactions.
7. Observe acceptance rates, rejection rates, and technical errors with separate metrics.

Do not use order IDs as metric labels with unbounded cardinality. When looking up individual cases, use logs with a correlation ID and an appropriate reason code, avoiding blindly logging entire payloads.

Some concrete choices:

| Need | Implementation approach |
| --- | --- |
| Skip events not belonging to the stage, with a clear policy | Filter with an appropriate discard policy. |
| Choose one of several business stages | Router. |
| Change schema or mask fields | Transformer or content-processing step. |
| Need an evaluation result containing multiple errors | Dedicated evaluation step returning structured data. |
| Prevent duplicate processing across multiple message deliveries | Design idempotency with clear state and processing boundaries. |
| Wait for a condition that may become true in the future | Storage, scheduling, or reprocessing mechanism. |

## 11. Extended practice

Start with the Java DSL configuration and tests in section 9, then perform these steps in order:

1. Change `O-101`'s status to `DRAFT`; verify only the rejected branch receives data.
2. Test the exact boundary value `10000000` and the out-of-bounds value `10000000.01`.
3. Add a boolean `trusted` header condition, testing both missing headers and string-typed headers.
4. In a separate test configuration, enable `throwExceptionOnRejection(true)` and observe both the sender and the rejected queue.
5. Design an `OrderResult` contract if you want to turn the exercise into a gateway that responds for every request.

The key takeaway throughout is: **the selector decides acceptance or rejection; the endpoint configuration and flow branches decide what happens next**. A complete filter in an application requires both an accurate rule and a clear policy for messages that do not proceed.
