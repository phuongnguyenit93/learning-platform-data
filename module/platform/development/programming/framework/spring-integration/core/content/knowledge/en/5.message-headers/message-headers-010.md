# routingSlip

## Objectives and scope

In the **Message headers** chapter of the **SPRING_INTEGRATION_CORE** module, this lesson explains how to use the `routingSlip` header to guide a message through multiple processing steps. Learners will configure routes using Java DSL, track progress, add conditional processing steps, and diagnose why a message fails to reach its destination.

The running example is an order going through data validation, enrichment, and audit recording. Business components communicate via `Message` and `MessageChannel`; a gateway can provide a calling interface from the application. The content focuses on routing slips; transformers, filters, aggregators, and error handling are discussed where they directly affect continuing along the route.

Java examples use Java 17 syntax and the Spring Integration 6.5.x API, with libraries managed consistently via a BOM or project dependency configuration. `spring-integration-core` is required; test examples use JUnit Jupiter. This is a standalone configuration for reading and hands-on practice and does not assume your current project already declares the corresponding beans.

## 1. What problem does a routing slip solve?

Suppose an application receives two kinds of requests:

- Standard order: validate → enrich → audit.
- Order requiring review: validate → enrich → review → audit.

You could connect endpoints with fixed channels and insert routers at branching points. When multiple workflows reuse the same steps in different sequences, repeating channel wiring makes the structure hard to follow.

The **Routing Slip** pattern attaches the processing itinerary to the message itself. Each step completes its work and uses that itinerary to determine where to forward next. The route can be chosen upon receiving the request while business steps remain reusable. This is the core idea of the [Routing Slip pattern in Enterprise Integration Patterns](https://www.enterpriseintegrationpatterns.com/patterns/messaging/RoutingTable.html).

You can picture an order carrying a routing ticket:

```text
payload:
  id = ORD-41

headers:
  businessKey = ORD-41
  routingSlip = itinerary along with current position
  replyChannel = final result destination
```

In the example, the payload describes the order, while headers control how the message travels through the system. Separating the two roles keeps the validation step from needing to know whether the next step is audit or review.

A routing slip is useful when the processing sequence must travel with each request. If every request always follows a fixed chain, a directly wired `IntegrationFlow` is usually easier to understand.

## 2. When is the `routingSlip` header used?

The header name is `routingSlip`; in Java reference it via:

```java
IntegrationMessageHeaderAccessor.ROUTING_SLIP
```

Spring Integration uses this header in the output-channel selection mechanism of reply-producing handlers in the `AbstractMessageProducingHandler` family. When the endpoint already has an `outputChannel`, that channel takes precedence. When there is no output channel, the framework inspects the routing slip; once the slip runs out of entries, it falls back to `replyChannel`. See [Spring Integration Routing Slip](https://docs.spring.io/spring-integration/reference/6.5/router/routing-slip.html).

For an order-processing endpoint, we need to answer three questions:

1. Does the endpoint produce a result to send onward?
2. Is the endpoint already wired to an output channel?
3. If the routing slip is needed, does the message still retain the slip state?

For instance, a service activator that only logs and returns `void` produces no downstream result. The routing header does not turn that method into a request-reply step. Similarly, a filter dropping a message can end that processing branch right there.

Distinguishing the control components:

| Component | Role in the order example |
| --- | --- |
| `outputChannel` | Output channel attached to the endpoint |
| `routingSlip` | Itinerary and position for selecting the next step |
| `replyChannel` | Destination receiving the result after the itinerary finishes |
| `errorChannel` | Destination for error messages when the corresponding error-handling mechanism uses it |
| Router | Endpoint performing its own routing decision |
| `correlationId` or business key | Links messages belonging to the same request |

These headers do not substitute for one another. For example, setting an order correlation key does not help the framework automatically find the audit step.

## 3. The header value holds both the path and the position

Do not treat the runtime value of `routingSlip` as a string like `"validateOrders;enrichOrders"`.

`RoutingSlipHeaderValueMessageProcessor` creates a value of type `Map<List<Object>, Integer>` with a single entry: the key is the list of path items, and the value is the initial index `0`. This structural detail is shown in [Spring Integration's processor source](https://github.com/spring-projects/spring-integration/blob/6.5.x/spring-integration-core/src/main/java/org/springframework/integration/transformer/support/RoutingSlipHeaderValueMessageProcessor.java).

Illustrative representation:

```text
{
  ["validateOrders", "enrichOrders", "auditOrders"] -> 0
}
```

After selecting the validation channel:

```text
{
  ["validateOrders", "enrichOrders", "auditOrders"] -> 1
}
```

The index indicates **the next item to inspect when selecting a channel**, not proof that the previous business step committed successfully. In an asynchronous flow, a message already carrying the updated index may still sit in a queue waiting to be processed.

If an entry is a channel name, selecting that channel advances the index. If an entry is a strategy, the framework keeps the index so the strategy can decide again on the next hop; only when the strategy returns `null` or an empty string does it advance to the next entry. See the route selection logic in [`AbstractMessageProducingHandler` source](https://github.com/spring-projects/spring-integration/blob/6.5.x/spring-integration-core/src/main/java/org/springframework/integration/handler/AbstractMessageProducingHandler.java).

When all entries are channel names, the progression in the example is:

| Channel selection point | Index before selection | Selected destination | Index sent onward |
| --- | ---: | --- | ---: |
| After enriching header | 0 | `validateOrders` | 1 |
| After validation | 1 | `enrichOrders` | 2 |
| After enrichment | 2 | `auditOrders` | 3 |
| After audit | 3 | Destination from `replyChannel` | Slip exhausted |

Do not mutate the map or list obtained from the header directly. Let the framework manage progression; if you want to start a new workflow, reconfigure the header at an explicit boundary.

## 4. Declaring paths properly with Java DSL

Java DSL provides `HeaderEnricherSpec.routingSlip(...)`. Separate arguments represent the entries in the itinerary:

```java
.enrichHeaders(headers -> headers.routingSlip(
        "validateOrders",
        "enrichOrders",
        "auditOrders"))
```

The API also has overloads taking an `overwrite` parameter. When overwrite is not requested and the default is unchanged, an existing header is kept. Details are documented in [`HeaderEnricherSpec` API](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/HeaderEnricherSpec.html) and [the 6.5.x branch implementation](https://github.com/spring-projects/spring-integration/blob/6.5.x/spring-integration-core/src/main/java/org/springframework/integration/dsl/HeaderEnricherSpec.java).

The following three forms have different meanings:

```java
// Correct: three entries in the path.
headers.routingSlip("validateOrders", "enrichOrders", "auditOrders");

// Avoid: passes only a single string to Java DSL,
// does not express three separate entries as above.
headers.routingSlip("validateOrders;enrichOrders;auditOrders");

// Wrong for the runtime value the routing slip mechanism expects:
// creates only a plain string header.
headers.header("routingSlip", "validateOrders;enrichOrders;auditOrders");
```

Semicolons appear in the XML configuration syntax for routing slips. Do not pass that XML string directly to the Java DSL varargs parameter.

In the examples below, every slip entry uses a channel bean name or strategy bean name defined by the application. Intentional naming such as `validateOrders` distinguishes the processing channel from the `validationFlow` flow name.

### Choosing whether to keep an existing slip

If a message halfway through its itinerary returns to a header-enrichment point, decide explicitly:

- Continue the current itinerary: keep the existing header.
- Start a new itinerary at an application-managed entry point: overwrite intentionally.
- Detect an invalid request: reject and record the reason.

Example of re-initializing the slip:

```java
.enrichHeaders(headers -> headers.routingSlip(
        true,
        "validateOrders",
        "enrichOrders",
        "auditOrders"))
```

In this example, `true` is the overwrite parameter. Do not place re-initialization at every step: a looping message could be sent back to the start of the slip repeatedly.

## 5. Complete example: an order passing through three steps

The following configuration declares the channels and each independent processing flow. The business flows end right after the reply-producing endpoint so next-channel selection relies on the routing slip.

Save as `OrderRoutingConfiguration.java` when practicing in a project with the dependencies listed at the start of the lesson:

```java
package com.example.routingslip;

import java.util.ArrayList;
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class OrderRoutingConfiguration {

    public record Order(
            String id,
            boolean reviewRequired,
            boolean reviewed,
            List<String> steps) {

        public Order {
            steps = List.copyOf(steps);
        }

        public Order recordStep(String step) {
            List<String> nextSteps = new ArrayList<>(steps);
            nextSteps.add(step);
            return new Order(id, reviewRequired, reviewed, nextSteps);
        }

        public Order markReviewed() {
            return new Order(id, reviewRequired, true, steps)
                    .recordStep("review");
        }
    }

    @Bean
    public MessageChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel validateOrders() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel enrichOrders() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel auditOrders() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow orderEntryFlow() {
        return IntegrationFlow.from("ordersInput")
                .enrichHeaders(headers -> headers.routingSlip(
                        "validateOrders",
                        "enrichOrders",
                        "auditOrders"))
                .get();
    }

    @Bean
    public IntegrationFlow validationFlow() {
        return IntegrationFlow.from("validateOrders")
                .<Order, Order>transform(order -> {
                    if (order.id() == null || order.id().isBlank()) {
                        throw new IllegalArgumentException(
                                "Order ID must not be blank");
                    }
                    return order.recordStep("validate");
                })
                .get();
    }

    @Bean
    public IntegrationFlow enrichmentFlow() {
        return IntegrationFlow.from("enrichOrders")
                .handle(Order.class, (order, headers) ->
                        order.recordStep("enrich"))
                .get();
    }

    @Bean
    public IntegrationFlow auditFlow() {
        return IntegrationFlow.from("auditOrders")
                .handle(Order.class, (order, headers) ->
                        order.recordStep("audit"))
                .get();
    }
}
```

The `steps` list helps observe execution order during the lesson. In a real application, the latter two handlers might look up customer details and record audit entries; tasks with side effects require separate design for transactions and deduplication.

Points to trace in the configuration:

- The header enricher is the final endpoint of the entry flow. After building the message with the slip, it can select `validateOrders`.
- The validation transformer returns a new `Order`.
- Both service activators return an `Order` to produce a reply.
- No fixed channel follows those endpoints.
- Names in the slip match channel bean names, not `IntegrationFlow` bean names.

`DirectChannel` executes consumers on the sending thread in the example's normal usage. If replaced with `QueueChannel`, configure a poller on the queue-consuming endpoint. Execution semantics are determined by channel type; see [MessageChannel implementations](https://docs.spring.io/spring-integration/reference/6.5/channel/implementations.html).

### Why not chain everything into one long flow?

Consider another configuration snippet:

```java
return IntegrationFlow.from("ordersInput")
        .enrichHeaders(headers -> headers.routingSlip(
                "validateOrders",
                "auditOrders"))
        .handle(Order.class, (order, headers) ->
                order.recordStep("fixed-stage"))
        .channel("fixedOutput")
        .get();
```

Here the DSL wires the header enricher to the next handler and wires that handler to `fixedOutput`. These links create outbound channels for the corresponding endpoints. Simply attaching a routing slip does not make them jump to the validation channel automatically.

You can combine a fixed processing segment with a segment using a routing slip, provided you identify which endpoint actually hands next-step selection over to the header. Splitting short flows in the main example makes this clear.

## 6. Sending a request and receiving the final reply

When sending directly to `ordersInput`, the sender must provide a place to receive the result. The snippet below runs inside code that already has an `ApplicationContext`:

```java
import java.util.List;

import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

import com.example.routingslip.OrderRoutingConfiguration.Order;

// context is the ApplicationContext that loaded OrderRoutingConfiguration.
MessageChannel input =
        context.getBean("ordersInput", MessageChannel.class);

QueueChannel replies = new QueueChannel(1);

Message<Order> request = MessageBuilder
        .withPayload(new Order("ORD-41", false, false, List.of()))
        .setHeader("businessKey", "ORD-41")
        .setHeader(MessageHeaders.REPLY_CHANNEL, replies)
        .build();

if (!input.send(request, 1_000)) {
    throw new IllegalStateException("Failed to send request");
}

Message<?> response = replies.receive(1_000);
if (response == null) {
    throw new IllegalStateException("No result received yet");
}

Order result = (Order) response.getPayload();
// result.steps() = ["validate", "enrich", "audit"]
```

When the audit step completes, the list has no remaining channel entries to select, so the result follows `replyChannel`.

The reply queue has capacity one because each call in the example uses its own queue. When sharing a reply channel across multiple concurrent requests, there must be a mechanism to match replies to requests.

### If the application calls through a gateway

You can let a gateway manage the request-reply mechanism instead of manually creating a queue:

```java
package com.example.routingslip;

import org.springframework.integration.annotation.MessagingGateway;

import com.example.routingslip.OrderRoutingConfiguration.Order;

@MessagingGateway(
        defaultRequestChannel = "ordersInput",
        defaultReplyTimeout = "2000")
public interface OrderGateway {

    Order process(Order order);
}
```

Register the interface with an appropriate gateway scanning mechanism, such as `@IntegrationComponentScan` on a configuration class in the corresponding package. The gateway creates a temporary reply channel for the request-reply call; see [Messaging Gateways](https://docs.spring.io/spring-integration/reference/6.5/gateway.html).

Do not add a shared `replyChannel` at the entry point just to make the routing slip work if the gateway already manages replies per call. Changing the reply destination should come from flow design.

The reply wait timeout does not imply the ability to cancel running work. Especially in the synchronous example, business processing happens right inside the send call; the reply timeout is not an execution-time cap on each service.

## 7. Adding a review step with `RoutingSlipRouteStrategy`

An entry in the itinerary can be the bean name of a `RoutingSlipRouteStrategy` implementation. The key method is:

```java
Object getNextPath(Message<?> requestMessage, Object reply);
```

The strategy is queried repeatedly until it returns `null` or an empty string. `requestMessage` is the input message to the endpoint producing the reply. `reply` can be a domain object, a `Message<?>`, or an `AbstractIntegrationMessageBuilder<?>`; do not always cast it to `Message`. See [`RoutingSlipRouteStrategy` contract](https://docs.spring.io/spring-integration/api/org/springframework/integration/routingslip/RoutingSlipRouteStrategy.html).

In this lesson, the strategy returns either a channel name or `null`. The business rule is:

```text
Order requires review and has not been reviewed yet:
    send to reviewOrders

All other cases:
    finish the strategy entry, move to the audit step
```

Create the additional configuration:

```java
package com.example.routingslip;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.routingslip.RoutingSlipRouteStrategy;
import org.springframework.integration.support.AbstractIntegrationMessageBuilder;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;

import com.example.routingslip.OrderRoutingConfiguration.Order;

@Configuration
public class ReviewRoutingConfiguration {

    @Bean
    public MessageChannel reviewOrders() {
        return new DirectChannel();
    }

    @Bean
    public RoutingSlipRouteStrategy optionalReviewRoute() {
        return (requestMessage, reply) -> {
            Object candidate = reply;

            if (candidate instanceof Message<?> message) {
                candidate = message.getPayload();
            }
            else if (candidate
                    instanceof AbstractIntegrationMessageBuilder<?> builder) {
                candidate = builder.getPayload();
            }

            if (!(candidate instanceof Order order)) {
                throw new IllegalArgumentException(
                        "Strategy requires an Order result");
            }

            return order.reviewRequired() && !order.reviewed()
                    ? "reviewOrders"
                    : null;
        };
    }

    @Bean
    public IntegrationFlow reviewFlow() {
        return IntegrationFlow.from("reviewOrders")
                .<Order, Order>transform(Order::markReviewed)
                .get();
    }
}
```

Then **replace the slip list in `orderEntryFlow()`**, without adding a second entry flow:

```java
.enrichHeaders(headers -> headers.routingSlip(
        "validateOrders",
        "enrichOrders",
        "optionalReviewRoute",
        "auditOrders"))
```

Load both configuration classes. When an order has `reviewRequired = true`, the progression around the strategy is:

| Moment | Current index | Strategy result | Progression |
| --- | ---: | --- | --- |
| After enrichment | 2 | `"reviewOrders"` | Sent to review step, stays at index 2 |
| After review | 2 | `null` | Advances to audit entry |
| After audit | Slip exhausted | Strategy no longer called | Returns result to caller |

For an order that does not require review, the strategy returns `null` on the first call and the audit step receives the order directly.

### The termination condition must accompany business state

If a strategy always returns `"reviewOrders"`, every time the review step produces a reply, the strategy picks the same channel again. In a synchronous configuration, such a cycle can continue until a deep nested-call failure occurs.

`markReviewed()` in the example flips `reviewed` to `true` before returning the result. This condition makes the strategy terminate for that specific order.

Do not use a field like `private int nextStep` in a singleton strategy bean to track shared progress. Two interleaved orders would mutate the same variable. Prefer deciding from the current message and processing result; if long-lived state must be stored, key state by workflow identifier and handle concurrency deliberately.

Also distinguish two cases:

- Reading `requestMessage`: observes data before the current endpoint.
- Reading `reply`: observes the result the endpoint just produced.

If the review step updated the state yet the strategy still inspects the old payload on `requestMessage`, it may decide to review again. The sample strategy checks the new result because that is the data containing `reviewed = true`.

## 8. Using SpEL and understanding the expression context

Short rules can be expressed with `ExpressionEvaluatingRoutingSlipRouteStrategy`. The expression root provides two properties, `request` and `reply`; details are in [the expression strategy implementation](https://github.com/spring-projects/spring-integration/blob/6.5.x/spring-integration-core/src/main/java/org/springframework/integration/routingslip/ExpressionEvaluatingRoutingSlipRouteStrategy.java).

Because endpoints in the example return `Order` directly, you can replace the Java strategy bean above with the following bean, keeping the same name:

```java
@Bean
public ExpressionEvaluatingRoutingSlipRouteStrategy optionalReviewRoute() {
    return new ExpressionEvaluatingRoutingSlipRouteStrategy(
            "reply.reviewRequired() && !reply.reviewed() "
                    + "? 'reviewOrders' : null");
}
```

The import for this type is:

```java
import org.springframework.integration.routingslip
        .ExpressionEvaluatingRoutingSlipRouteStrategy;
```

This is a replacement for the `optionalReviewRoute` bean; do not declare both beans with the same name.

If an endpoint later returns a `Message<Order>`, the expression needs to read the message's payload, such as `reply.payload.reviewRequired()`. When reply types vary or rules grow long, a typed Java strategy like the previous section is easier to maintain.

Do not confuse this context with an expression evaluated directly against a message in a header enricher. In the expression strategy, `request.headers['businessKey']` accesses the request's header; `reply` is the result currently used to choose the next step.

### Avoid letting expressions become external control input

If the system receives HTTP requests, broker events, or partner data, accept a finite business value such as `STANDARD` or `REQUIRES_REVIEW`, and map it to an application-managed route.

Do not feed raw strings supplied by a sender into SpEL configuration or treat them as arbitrary bean names. In this example, channel names and strategy names are internal configuration; customer data only affects the `reviewRequired` condition.

## 9. Headers across endpoints and persistence boundaries

### 9.1. Preserving the information needed to continue

Header enrichers add metadata without writing a custom transformer just to set headers; see [Header Enricher](https://docs.spring.io/spring-integration/reference/6.5/content-enrichment.html).

Along the processing chain, track at least the current slip, the reply address, and the business correlation key. A payload transformation can be completely valid in business terms yet subsequent header-filtering configuration still causes the result to lose where to go next.

Specifically check:

- Whether a header filter is dropping `routingSlip` or `replyChannel`.
- Whether a handler is configured to block header propagation.
- Whether an adapter maps the required headers across its protocol.
- Whether code manually constructing a new message preserves metadata per the flow contract.

Header copying depends on handler type and configuration; the API allows specifying header patterns not to propagate onward. See [`AbstractMessageProducingHandler` API](https://docs.spring.io/spring-integration/docs/6.5.x/api/org/springframework/integration/handler/AbstractMessageProducingHandler.html).

Do not assume every `MessageBuilder.withPayload(...)` loses headers: a handler can copy headers from the request. Inspect the actual message at the boundary where an issue occurs.

### 9.2. Crossing a broker or `MessageStore`

Inline expressions can be converted into strategy objects stored inside the header. Expression strategies depend on Spring infrastructure and are unsuitable for passing directly via Java serialization. Registering the strategy as a bean and placing the **bean name** in the slip is the approach recommended by the [Routing Slip documentation](https://docs.spring.io/spring-integration/reference/6.5/router/routing-slip.html) for this case.

Choosing bean names solves only part of the design. For a flow crossing a broker, determine:

| Aspect | Decision required |
| --- | --- |
| Wire representation | Does the serializer support the chosen slip structure? |
| Header mapping | Does the adapter forward that header as configured? |
| Target names | Does the consumer have the corresponding channels and strategies? |
| Configuration upgrades | Which workflow version handles older in-flight messages? |
| Reply destination | Can it be used validly across process boundaries? |
| Re-execution | Which steps can run again without duplicate side effects? |

A temporary reply channel inside one JVM does not automatically become a meaningful address in another JVM. A long-lived order workflow stored on disk typically needs an explicit workflow ID, version, and business state rather than relying solely on runtime bean names.

A routing slip helps determine the next step; delivery, persistence, transaction, and deduplication policies must still be designed for participating systems.

## 10. Error handling and stopping points on the slip

### 10.1. Errors in a synchronous configuration

The main example uses `DirectChannel`. If the validation step throws an error, the caller sending the request can receive the exception on the same call stack. Setting an `errorChannel` header alone does not automatically turn every synchronous exception into an error message.

In asynchronous processing, pollers and components with error-publishing mechanisms can emit an `ErrorMessage`, selecting the channel from the `errorChannel` header or the default error channel. Gateways also have their own error-handling settings. See [Error Handling](https://docs.spring.io/spring-integration/reference/6.5/error-handling.html).

For an order with a blank code, the business expectation in this lesson is:

1. Data validation fails.
2. No enrichment occurs and no audit entry is recorded as a successful order.
3. The caller or error-handling branch receives the cause per configuration.

### 10.2. The slip index is not a completion log

A message sent into the audit step may already carry an index pointing past the audit entry while the audit write operation has not yet succeeded.

Therefore, when designing retries, determine where retry happens: re-invoking the current endpoint's task, resending the message to the current channel, or restarting the request from the beginning. Each choice has a different risk of repeating side effects.

For example, suppose an order was recorded in the payment system and then failed while recording audit: restarting from the beginning could charge twice if the payment step is not idempotent. Use business keys like `orderId` and an idempotency policy tailored to each system.

### 10.3. Endpoints that produce no reply

Several stopping points must be distinguished:

| Situation | Consequence to consider |
| --- | --- |
| Service activator returns `void` or no result | No reply to continue; may throw if reply is required |
| Filter rejects message | Main route stops; design discard or error per business rules |
| Aggregator has not met release condition | No aggregated result produced yet to proceed |
| Routing slip exhausted but missing reply address | Reply-producing endpoint may fail to find an outbound channel |
| Target channel lacks an appropriate consumer | Sending may fail or the message waits in a queue, depending on channel type |

If using a splitter/aggregator, explicitly design which headers appear on the post-aggregation result. One aggregated result can represent multiple child messages; the itinerary of one child message does not automatically become the right business itinerary for the entire group.

## 11. Testing order, replies, and termination conditions

A useful test should verify observable output. For a static slip, check step ordering, business keys, and receiving exactly one result.

The example below uses the Spring context and JUnit Jupiter directly, loading the three-step configuration from section 5:

```java
package com.example.routingslip;

import java.util.List;

import org.junit.jupiter.api.Test;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

import com.example.routingslip.OrderRoutingConfiguration.Order;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OrderRoutingTest {

    @Test
    void shouldFollowTheSlipAndReturnOneReply() {
        try (var context = new AnnotationConfigApplicationContext(
                OrderRoutingConfiguration.class)) {

            MessageChannel input = context.getBean(
                    "ordersInput", MessageChannel.class);
            QueueChannel replies = new QueueChannel(2);

            Message<Order> request = MessageBuilder
                    .withPayload(new Order(
                            "ORD-41", false, false, List.of()))
                    .setHeader("businessKey", "ORD-41")
                    .setHeader(MessageHeaders.REPLY_CHANNEL, replies)
                    .build();

            assertTrue(input.send(request, 1_000));

            Message<?> reply = replies.receive(1_000);
            assertNotNull(reply);

            Order result = (Order) reply.getPayload();
            assertEquals("ORD-41", result.id());
            assertEquals(
                    List.of("validate", "enrich", "audit"),
                    result.steps());
            assertEquals("ORD-41",
                    reply.getHeaders().get("businessKey"));
            assertNull(replies.receive(0));
        }
    }
}
```

Mocks are unnecessary when sample handlers only transform data in memory. For tasks calling external systems, you can replace or mock the relevant components using tools from [Spring Integration Test](https://docs.spring.io/spring-integration/reference/6.5/testing.html).

After switching to a slip with a strategy, add the following scenarios in your practice project:

| Scenario | Observable expectation |
| --- | --- |
| Order does not require review | `validate`, `enrich`, `audit` |
| Order requires review and has not been reviewed | `validate`, `enrich`, `review`, `audit`; result has `reviewed = true` |
| Order is already reviewed | Does not invoke `review` step again |
| Blank order ID | Throws error; no success result |
| Two orders with different review needs running concurrently | Each order follows its own slip, without sharing progress |
| Input already carries a routing slip header | Keep or overwrite behavior matches design choice |
| Endpoint gets a fixed channel attached | Test outcome reflects the impact of the new wiring |

With a strategy, test directly against every `reply` shape the system can actually produce: domain object, `Message`, and builder if used. What matters is that post-processing state makes the strategy stop at the right time.

Use finite timeouts for receive operations in tests so a process never hangs indefinitely. However, a receive timeout does not interrupt a synchronous loop occurring inside `send()`; verify a strategy's termination condition with unit tests before running the whole slip.

## 12. Quick diagnosis when a slip behaves unexpectedly

| Symptom | First thing to check | How to fix |
| --- | --- | --- |
| Header has a slip, yet the message still enters a fixed channel | Outbound channel configured by DSL or annotation | Identify the endpoint that should pick its destination from the routing slip |
| Header data-type error | Is the `routingSlip` value a manually attached string or list? | Use the dedicated API to construct the header |
| Expression error right when initializing the slip | Is a bean name in the slip misspelled? | Check channel/strategy names; a string matching no bean may be evaluated as SpEL |
| A step repeats in a loop | Does the strategy have a termination condition and read the new result? | Update business state and the `null`-returning branch |
| Caller receives no result | Does the final endpoint reply and is the reply address valid? | Trace the final step, headers, and gateway mechanism |
| Message sits idle after changing channel type | Is there a consumer and poller for the queue channel? | Configure an appropriate consumption mechanism |
| Error when persisting message or sending across a broker | Does the header contain runtime strategy/channel objects? | Use bean names and define a serialization contract |
| Orders affect each other's itinerary | Does the strategy have a shared state field? | Isolate state per request/workflow |

When logging, include the order ID or correlation key, the active step name, and the routing decision. The routing slip index helps inspect control flow; business logs show which tasks actually completed.

## 13. Criteria for choosing a routing slip in a design

Use a routing slip when the itinerary needs to travel with each message and you can clearly specify how each step returns a result. The order chain in this lesson allows reusing the same validation and audit steps while inserting a conditional review step.

When evaluating a specific design, lock down:

- Where the slip is created and where modifying the slip is permitted.
- Which endpoints have fixed output channels and which select channels from headers.
- How each step produces a reply and maintains metadata.
- What condition guarantees the strategy terminates for every message.
- Where results are received, where errors are handled, and what re-execution means.

A workflow that waits for days, involves human interaction, compensates across multiple transactions, and recovers across multiple deployments needs an additional workflow-state management mechanism. A routing slip can participate as a step-selection mechanism, while those operational requirements must be met with a dedicated design.

After practicing, learners should be able to trace an order's path from `ordersInput` to the caller, point out which endpoint reads the routing slip, and predict the impact of adding a fixed channel, omitting a reply, or using a strategy with no stopping condition.
