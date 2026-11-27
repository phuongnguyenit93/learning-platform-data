# Pure and Testable Routing Conditions

In **Spring Integration**, a **Content-Based Router** decides which channel a message goes to based on the content of the message: its payload, headers, or both. The Router is a cornerstone of **Enterprise Integration Patterns (EIP)** because it separates the **routing decision** from the handlers that perform the work. An order-processing system might route high-risk orders to a manual review team, priority orders to a fast track, and the remaining orders to a standard flow.

This lesson belongs to the **Content-based router** chapter in the **SPRING_INTEGRATION_PATTERN** module. The goal of the module is to build loosely coupled and extensible messaging flows with Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channels, and correlation; while knowing how to test, observe, and handle errors in each branch.

The main topic is **pure and testable routing conditions**. Instead of putting database queries, current time lookups, and message sending inside a single router method, we extract a **pure routing policy** into a Java function that accepts input data and returns a **routing decision**, then let Spring Integration forward the message to the corresponding channel.

## 1. What will you learn?

After this lesson, you can:

1. Explain the Content-Based Router and distinguish it from Filter, Transformer, Publish–Subscribe Channel, and Recipient List Router.
2. Write routing conditions as a pure function: same input yields the same result, with no hidden state dependencies and no side effects.
3. Separate the business policy (`RoutingPolicy`) from mapping the result to channel names.
4. Integrate the policy with Spring Integration's `@Router` and properly provision destination channels.
5. Verify edge cases, invalid values, rule priority order, and determinism with JUnit 5.
6. Test the entire flow to confirm messages reach the right channel, metadata is preserved, and other branches do not receive the message.
7. Design error handling, fallbacks, logging, and correlation without putting I/O inside the decision function.

## 2. How does a Content-Based Router work?

A Router receives a message, evaluates its content, and returns one or more channel addresses that the framework can use to forward the message. For a **single-destination** router, the return value is typically the name of a single channel.

~~~mermaid
flowchart LR
    I["Inbound: OrderCreated"] --> V["Validate / Normalize"]
    V --> R{"Content-Based Router"}
    R -->|"riskScore >= 80"| H["orders.review"]
    R -->|"VIP && total >= 500"| P["orders.priority"]
    R -->|"otherwise"| S["orders.standard"]
    H --> HA["Manual review handler"]
    P --> PA["Priority handler"]
    S --> SA["Standard handler"]
~~~

The order in the example above is significant: when an order is both high-risk and VIP, the **manual review** rule must win. Changing the `if` order could send a high-risk order straight to the priority branch.

A message might contain:

~~~text
payload:
  orderId: order-1001
  total: 750.00
  vip: true
  riskScore: 85

headers:
  traceId: trace-1001
  tenantId: shop-a
  businessCorrelationId: order-1001
~~~

In this case, the policy must select `REVIEW` because `riskScore=85`, even though `vip=true` and `total=750`.

### Router decides, channel transports, and handler processes

| Component | Responsibility | What not to do |
|---|---|---|
| **Routing policy** | Compute `REVIEW` / `PRIORITY` / `STANDARD` decision from data | Call DB/API, send emails, send directly to channels |
| **Spring Integration Router** | Convert decision into destination channel name | Contain complex, hard-to-test business rules |
| **MessageChannel** | Transport message to endpoint | Re-infer risk/priority rules |
| **Destination branch handler** | Perform concrete processing | Re-check all routing conditions under the same trust contract |
| **Filter / validator** | Accept, reject, or report contract-violating input | Silently turn invalid data into a valid route |

In EIP design, a router typically follows *content-based routing*, while handlers on downstream branches can be a Service Activator, Transformer, Gateway, or a larger integration flow.

## 3. What does a "pure" routing condition mean?

An ideal routing function has the form:

~~~text
decision = route(payload, trustedContext, immutableRules)
~~~

A function is called **pure** when:

- **Deterministic:** same payload, same context, and same rule set always return the same result.
- **Side-effect free:** does not write to a DB, make HTTP calls, send emails, publish messages, or mutate payloads or headers.
- **No hidden state reads:** does not call `Instant.now()`, `Math.random()`, unpredictably changing config, or mutable caches during decision-making.
- **Clear input contract:** which fields may be absent, which data types are valid, and how anomalies are handled are all well-defined.
- **Closed result set:** prefer an enum (`REVIEW`, `PRIORITY`, `STANDARD`) over channel strings scattered across multiple `if` statements.

A pure function can still **throw an exception deterministically** for data violating the contract. However, if invalid messages need to be routed separately, there should be a Filter/validation step before the router or an explicitly designed `REJECT` decision.

### 3.1. Why does purity help testing?

With a function independent of the Spring context, JUnit can invoke it directly:

~~~java
assertEquals(
    Decision.REVIEW,
    policy.decide(orderWithRiskScore85));
~~~

No need to start a broker, create a mock database, or wait for async tasks. Edge cases are easy to read: score 79 vs. 80, total 499.99 vs. 500.00, VIP vs. regular customer.

**However, policy unit tests alone are not enough:** they verify the *business decision*, not that Spring resolves the right channel and delivers the message to the right handler. We will pair this with an integration test in a later section.

### 3.2. Example of a hard-to-test implementation

~~~java
// ANTI-PATTERN illustration; do not use as a real router.
public String badRoute(OrderCandidate order) {
    int score = riskApi.fetchCurrentScore(order.orderId());
    boolean flashSale = LocalDate.now().getDayOfWeek()
            == DayOfWeek.FRIDAY;
    metrics.increment("router_invoked");

    if (score >= 80) {
        notificationService.sendRiskAlert(order.orderId());
        return "orders.review";
    }
    return flashSale ? "orders.priority" : "orders.standard";
}
~~~

The dependencies here cause issues:

- The API can time out or return different values across two runs for the same order.
- The result changes depending on the day of the week on the host machine.
- A test run might actually send an alert.
- Router retries can duplicate the `sendRiskAlert` side effect.
- Orders cannot be replayed with historical decisions once external state or configuration has changed.

Required external data should be fetched in a **separate step before the router**, packaged into the payload or an immutable context, and passed into the policy. This does not eliminate errors during the enrichment/risk lookup step; it makes **error scope, retries, and responsibilities** clear.

## 4. Designing the routing policy in pure Java

We build a consistent policy for orders. There are three branches:

1. `REVIEW`: risk score of **80** or higher, highest priority.
2. `PRIORITY`: not in review, VIP customer **and** total of **500.00** or higher.
3. `STANDARD`: all remaining valid orders.

The thresholds here are illustrative data for this lesson, not a universal business rule.

### 4.1. Defining an immutable payload

~~~java
import java.math.BigDecimal;

public record OrderCandidate(
        String orderId,
        BigDecimal total,
        boolean vip,
        int riskScore
) {}
~~~

A `record` is convenient because it generates no setters. `String` and `BigDecimal` are immutable value types, while `boolean` and `int` are primitives. Thus, this payload has no mutable fields shared across branches. In a real application, you can add currency, source, authentication metadata, and schema version per contract.

The policy input is assumed to contain complete data after a decode/validation/enrichment step has supplied a trustworthy risk score.

### 4.2. Defining the result with an enum

~~~java
public enum RouteDecision {
    REVIEW,
    PRIORITY,
    STANDARD
}
~~~

An enum makes the compiler enforce handling of all declared decisions. It also separates business vocabulary from actual channel names: `PRIORITY` is the processing intent; `orders.priority` is the current channel address. Renaming a channel does not require changing priority-scoring rules.

### 4.3. Writing a pure policy

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public final class OrderRoutingPolicy {

    private static final int REVIEW_RISK_THRESHOLD = 80;
    private static final BigDecimal PRIORITY_MIN_TOTAL =
            new BigDecimal("500.00");

    public RouteDecision decide(OrderCandidate order) {
        Objects.requireNonNull(order, "order");

        if (order.orderId() == null || order.orderId().isBlank()) {
            throw new IllegalArgumentException(
                    "orderId must not be blank");
        }
        if (order.total() == null || order.total().signum() < 0) {
            throw new IllegalArgumentException(
                    "total must be non-negative");
        }
        if (order.riskScore() < 0 || order.riskScore() > 100) {
            throw new IllegalArgumentException(
                    "riskScore must be between 0 and 100");
        }

        // Priority policy: review wins over all other decisions.
        if (order.riskScore() >= REVIEW_RISK_THRESHOLD) {
            return RouteDecision.REVIEW;
        }

        if (order.vip()
                && order.total().compareTo(PRIORITY_MIN_TOTAL) >= 0) {
            return RouteDecision.PRIORITY;
        }

        return RouteDecision.STANDARD;
    }
}
~~~

This policy has no knowledge of Spring Integration, channels, bean names, or databases. It can be used in JUnit, a console app, or another adapter. Because the class holds no mutable state and all inputs are immutable values, a single instance can be safely called by multiple threads.

**Why use `compareTo` instead of `equals` for `BigDecimal`?** `new BigDecimal("500.0").equals(new BigDecimal("500.00"))` returns `false` because of differing scales; `compareTo` checks numerical ordering. When comparing monetary thresholds, `compareTo(...) >= 0` accurately expresses "500 or more".

**Why validate inside the policy when input validation already exists?** These short checks protect the pure function's contract against any caller. In a real flow, ingress validation is still needed to return friendly errors to callers and protect trust boundaries. They serve two different roles.

### 4.4. Decision table

| Risk score | VIP | Total | Result | Reason |
|---:|---|---:|---|---|
| 85 | Yes | 750.00 | `REVIEW` | High risk takes precedence |
| 80 | No | 10.00 | `REVIEW` | Exact risk threshold |
| 79 | Yes | 500.00 | `PRIORITY` | VIP and meets threshold |
| 79 | Yes | 499.99 | `STANDARD` | Below total threshold |
| 0 | No | 900.00 | `STANDARD` | Not VIP |
| 0 | Yes | 500.0 | `PRIORITY` | Compares numerical value, not scale |
| 101 | Yes | 900.00 | Exception | Violates score contract |
| 50 | Yes | -1.00 | Exception | Negative total |

This table can be translated almost directly into parameterized tests.

## 5. Integrating the policy into a Spring Integration Router

The next step is writing a small adapter for Spring to invoke the policy, then mapping `RouteDecision` to a channel name.

### 5.1. Router only maps the result

~~~java
import org.springframework.integration.annotation.Router;

public final class OrderRouter {

    private final OrderRoutingPolicy policy;

    public OrderRouter(OrderRoutingPolicy policy) {
        this.policy = policy;
    }

    @Router(inputChannel = "orders.toRoute")
    public String select(OrderCandidate order) {
        return switch (policy.decide(order)) {
            case REVIEW   -> "orders.review";
            case PRIORITY -> "orders.priority";
            case STANDARD -> "orders.standard";
        };
    }
}
~~~

Spring Integration passes the message payload to the `OrderCandidate order` parameter via endpoint method invocation. The `select` method returns a `String` representing the **destination channel name**, allowing the framework to resolve the matching channel and send the **inbound message** there.

The Router above does not manually send messages, alter headers, call downstream handlers, or throw errors for valid orders. Business rules remain solely inside `OrderRoutingPolicy`.

### 5.2. Declaring channels and beans

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
public class OrderRoutingConfiguration {

    @Bean(name = "orders.toRoute")
    public MessageChannel ordersToRoute() {
        return new DirectChannel();
    }

    // Use QueueChannel for easy receiving and testing.
    @Bean(name = "orders.review")
    public PollableChannel reviewQueue() {
        return new QueueChannel();
    }

    @Bean(name = "orders.priority")
    public PollableChannel priorityQueue() {
        return new QueueChannel();
    }

    @Bean(name = "orders.standard")
    public PollableChannel standardQueue() {
        return new QueueChannel();
    }

    @Bean
    public OrderRoutingPolicy orderRoutingPolicy() {
        return new OrderRoutingPolicy();
    }

    @Bean
    public OrderRouter orderRouter(OrderRoutingPolicy policy) {
        return new OrderRouter(policy);
    }
}
~~~

In a real application, the three output channels typically connect onward to service activators or subflows for processing; here `QueueChannel` is used to observe routing results. The default queue is in-memory, **not durable across restarts**.

`@EnableIntegration` enables the annotation/endpoint infrastructure needed for pure Spring configuration. With Spring Boot and the appropriate Integration starter, an equivalent auto-configuration may be available; pick one approach consistently per project.

### 5.3. Producer sending a message

~~~java
import java.math.BigDecimal;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

void submit(MessageChannel ordersToRoute) {
    OrderCandidate candidate = new OrderCandidate(
            "order-1001",
            new BigDecimal("750.00"),
            true,
            85);

    Message<OrderCandidate> message = MessageBuilder
            .withPayload(candidate)
            .setHeader("traceId", "trace-1001")
            .setHeader("businessCorrelationId", "order-1001")
            .build();

    boolean accepted = ordersToRoute.send(message);
}
~~~

In this example, the message is routed to `orders.review`. The `traceId` and `businessCorrelationId` headers remain on the **forwarded message**. `accepted=true` indicates the send call was accepted at the messaging layer according to the topology; it does **not** by itself prove the order was reviewed or persisted successfully.

The `OrderCandidate`, `RouteDecision`, `OrderRoutingPolicy`, `OrderRouter`, and `OrderRoutingConfiguration` snippets in sections 4–5 form a single example; place them in an appropriate application package and import from that package.

## 6. Testing the policy completely without Spring

Purity shines brightest in unit tests: instantiate the Java class directly, specify inputs, and assert outputs. No `ApplicationContext`, broker, network, or clock is needed.

### 6.1. Parameterized test for the decision table

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import java.util.stream.Stream;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class OrderRoutingPolicyTest {

    private final OrderRoutingPolicy policy =
            new OrderRoutingPolicy();

    static Stream<Arguments> routes() {
        return Stream.of(
                Arguments.of(85, true, "750.00",
                        RouteDecision.REVIEW),
                Arguments.of(80, false, "10.00",
                        RouteDecision.REVIEW),
                Arguments.of(79, true, "500.00",
                        RouteDecision.PRIORITY),
                Arguments.of(79, true, "499.99",
                        RouteDecision.STANDARD),
                Arguments.of(0, false, "900.00",
                        RouteDecision.STANDARD),
                Arguments.of(0, true, "500.0",
                        RouteDecision.PRIORITY));
    }

    @ParameterizedTest
    @MethodSource("routes")
    void decidesExpectedRoute(
            int riskScore,
            boolean vip,
            String total,
            RouteDecision expected) {

        OrderCandidate order = new OrderCandidate(
                "order-1001",
                new BigDecimal(total),
                vip,
                riskScore);

        assertEquals(expected, policy.decide(order));
    }
}
~~~

This test covers the **79/80** and **499.99/500.00** boundaries while proving that high risk overrides the VIP condition. If the team changes thresholds or priority order, the test catches the impact on the contract.

### 6.2. Testing invalid inputs

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

class RoutingPolicyValidationTest {

    private final OrderRoutingPolicy policy =
            new OrderRoutingPolicy();

    @Test
    void rejectsRiskOutsideAllowedRange() {
        OrderCandidate invalid = new OrderCandidate(
                "order-1001",
                new BigDecimal("100.00"),
                true,
                101);

        assertThrows(IllegalArgumentException.class,
                () -> policy.decide(invalid));
    }

    @Test
    void rejectsNegativeTotal() {
        OrderCandidate invalid = new OrderCandidate(
                "order-1001",
                new BigDecimal("-1.00"),
                false,
                10);

        assertThrows(IllegalArgumentException.class,
                () -> policy.decide(invalid));
    }

    @Test
    void rejectsMissingOrderId() {
        OrderCandidate invalid = new OrderCandidate(
                "  ",
                new BigDecimal("100.00"),
                false,
                10);

        assertThrows(IllegalArgumentException.class,
                () -> policy.decide(invalid));
    }
}
~~~

These tests confirm the policy **does not turn data errors into standard routes**. To return friendly messages to callers, an endpoint before the router should use validation/filtering or a structured error-reporting mechanism.

### 6.3. Verifying the same input always gives the same result

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

class RoutingDeterminismTest {

    @Test
    void repeatsSameDecisionForSameInput() {
        OrderRoutingPolicy policy = new OrderRoutingPolicy();

        OrderCandidate order = new OrderCandidate(
                "order-1001",
                new BigDecimal("700.00"),
                true,
                10);

        RouteDecision expected = policy.decide(order);

        for (int i = 0; i < 100; i++) {
            assertEquals(expected, policy.decide(order));
        }
    }
}
~~~

This is a smoke test for determinism, **not a mathematical proof** that the code is completely side-effect free. Code review and designing without I/O or hidden state remain essential.

## 7. Testing Spring Integration Router through channels

Policy unit tests do not verify operational aspects such as:

- Whether the Router bean is registered by Spring.
- Whether the returned channel name resolves.
- Which destination channel a message is actually routed to.
- Whether the `traceId` header travels with the message through the router.
- That no messages are mistakenly sent to other channels.

To verify these, we can use Spring Test, JUnit 5, and the declared `QueueChannel` beans.

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

@SpringJUnitConfig(classes = OrderRoutingConfiguration.class)
class OrderRoutingFlowTest {

    @Autowired
    @Qualifier("orders.toRoute")
    MessageChannel input;

    @Autowired
    @Qualifier("orders.review")
    PollableChannel review;

    @Autowired
    @Qualifier("orders.priority")
    PollableChannel priority;

    @Autowired
    @Qualifier("orders.standard")
    PollableChannel standard;

    @Test
    void highRiskOrderGoesOnlyToReview() {
        OrderCandidate order = new OrderCandidate(
                "order-1001",
                new BigDecimal("750.00"),
                true,
                85);

        assertTrue(input.send(
                MessageBuilder.withPayload(order)
                        .setHeader("traceId", "trace-1001")
                        .build()));

        Message<?> routed = review.receive(1000);

        assertNotNull(routed);
        assertEquals(order, routed.getPayload());
        assertEquals("trace-1001",
                routed.getHeaders().get("traceId"));

        assertNull(priority.receive(0));
        assertNull(standard.receive(0));
    }

    @Test
    void eligibleVipOrderGoesToPriority() {
        OrderCandidate order = new OrderCandidate(
                "order-1002",
                new BigDecimal("500.00"),
                true,
                79);

        assertTrue(input.send(
                MessageBuilder.withPayload(order).build()));

        Message<?> routed = priority.receive(1000);

        assertNotNull(routed);
        assertEquals(order, routed.getPayload());

        assertNull(review.receive(0));
        assertNull(standard.receive(0));
    }

    @Test
    void nonVipOrderGoesToStandard() {
        OrderCandidate order = new OrderCandidate(
                "order-1003",
                new BigDecimal("900.00"),
                false,
                0);

        assertTrue(input.send(
                MessageBuilder.withPayload(order).build()));

        Message<?> routed = standard.receive(1000);

        assertNotNull(routed);
        assertEquals(order, routed.getPayload());

        assertNull(review.receive(0));
        assertNull(priority.receive(0));
    }
}
~~~

This tests **through message channels**, because the message enters `orders.toRoute` and exits to one of the three output channels chosen by `@Router`.

To prevent inter-test interference when sharing a Spring context, each test must consume its own messages and verify that the other queues are empty; for larger test suites, you can isolate contexts or clear test fixtures in a controlled manner. `receive(1000)` is a test timeout, not a system SLA.

### 7.1. Don't test only the `select(...)` method

~~~java
String channelName = new OrderRouter(new OrderRoutingPolicy())
        .select(order);
~~~

The snippet above tests the `Decision → channel name` mapping, but **does not know** whether `orders.review` actually exists in the Spring container. An integration test like the one above is needed to catch misconfigured channel names or unstarted endpoints.

## 8. Four commonly missed edge-case groups

### 8.1. Overlapping rules

An order can simultaneously have `vip=true`, `total=900`, and `riskScore=95`. If the VIP condition is checked first, the route will violate the review-first policy.

~~~java
// Matches the example contract:
if (order.riskScore() >= 80) {
    return RouteDecision.REVIEW;
}
if (order.vip() && order.total().compareTo(MIN_TOTAL) >= 0) {
    return RouteDecision.PRIORITY;
}
~~~

Use a decision table that makes **precedence** between conditions explicit. Do not write multiple independent `if` statements assigning a route variable, as readers struggle to see which condition wins last.

### 8.2. Boundary values

Test exact thresholds and both sides of each threshold: `79`, `80`; `499.99`, `500.00`. Avoid `double` for monetary amounts when policy accuracy matters, and specify rounding behavior if data comes from another system.

### 8.3. Incomplete or mistyped data

Fields like `total=null`, `orderId="   "`, `riskScore=-1`, and `riskScore=101` should have clearly defined behavior. For external messages, classify errors at ingress:

~~~mermaid
flowchart LR
    IN["Raw input"] --> DEC["Decode / schema"]
    DEC -->|Fail| ERR["Parse error"]
    DEC -->|OK| VAL{"Validate"}
    VAL -->|Fail| REJ["Reject / validation error"]
    VAL -->|Pass| ENR["Enrich trusted data"]
    ENR --> ROUTE{"Pure routing policy"}
    ROUTE --> DEST["Destination channel"]
~~~

If the router also has to parse JSON, validate emails, and call an API for risk scores, responsibility boundaries are mixed. Normalize and enrich in steps before the router, then pass a message with a clear contract into the policy.

### 8.4. Non-existent route destination

If a router returns `"orders.prority"` instead of `"orders.priority"`, or if the channel bean is undeclared, the framework may fail to resolve the destination and raise a dispatch error depending on router configuration. Policy unit tests will not catch a misspelled bean name; integration tests will.

You can use a **default output channel** when business requirements allow an explicit fallback, or configure the router to fail when a destination cannot be resolved. **Never use default output just to hide typos in channel names or configuration errors.** Distinguish between:

- **Business fallback:** valid message that matches no specialized branch → `STANDARD`.
- **Data rejection:** message violates the contract → reject/error flow.
- **Configuration error:** routing to a non-existent channel → fail loudly to fix deployment.

## 9. Route by payload or by header?

A Spring Integration router can evaluate payload, headers, or expressions. Your choice affects the **source of truth** for data.

### 9.1. Routing by normalized payload

This is the approach in `OrderRoutingPolicy`: risk score, VIP status, and total sit in a typed DTO. Before the router, validation and enrichment have established the contract.

Pros: easy to test, easy to audit business decisions, and avoids unsafe casting from `Map<String, Object>`.

### 9.2. Routing by trusted header

For example, selecting a regional processing system normalized by an inbound adapter:

~~~java
import java.util.Locale;

import org.springframework.integration.annotation.Router;
import org.springframework.messaging.handler.annotation.Header;

public class RegionRouter {

    @Router(inputChannel = "orders.byRegion")
    public String route(
            @Header("trustedRegion") String region) {

        String normalized = region.trim()
                .toUpperCase(Locale.ROOT);

        return switch (normalized) {
            case "NORTH" -> "orders.north";
            case "SOUTH" -> "orders.south";
            default -> "orders.regionReview";
        };
    }
}
~~~

This snippet illustrates an **alternative** router to the order policy above, not something to add to the same flow. Channel beans for all three outcomes must exist.

Client-supplied headers like `tenantId`, `priority`, or `trustedRegion` may only be trusted after the ingress/authentication or enrichment layer **verifies and re-attaches them**. Never let clients send a channel name directly and use that value as the router result; doing so allows sending messages to unintended internal channels.

### 9.3. What if conditions depend on both payload and headers?

Create a strongly typed context:

~~~java
public record RoutingContext(
        OrderCandidate order,
        String authenticatedTenant,
        boolean priorityFeatureEnabled
) {}
~~~

Then define:

~~~java
RouteDecision decide(RoutingContext context)
~~~

A Spring Integration adapter can read the payload and verified headers to construct `RoutingContext`, then invoke the pure policy. There is no need to expose `Message<?>` or `MessageHeaders` to the policy if doing so couples domain logic to the framework.

When a policy depends on feature flags or configuration thresholds, pass an **immutable snapshot** as input or construct the policy with immutable configuration. That way, every decision can be reproduced if the rule version is saved.

## 10. Routing with changing configuration while staying testable

In practice, risk or priority thresholds do not have to be hard-coded. You can define an immutable rule set:

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public record RoutingRules(
        int reviewRiskThreshold,
        BigDecimal priorityMinTotal
) {
    public RoutingRules {
        if (reviewRiskThreshold < 0 || reviewRiskThreshold > 100) {
            throw new IllegalArgumentException(
                    "Invalid review threshold");
        }
        Objects.requireNonNull(priorityMinTotal);
        if (priorityMinTotal.signum() < 0) {
            throw new IllegalArgumentException(
                    "Invalid priority minimum");
        }
    }
}
~~~

With this approach, the policy can accept `RoutingRules` via constructor. Benefits:

- Unit tests explicitly construct `RoutingRules(80, new BigDecimal("500.00"))`.
- Configuration changes are controlled, without relying on mutable global state.
- When explaining a historical event's decision, the system can record the **rules version**.
- No race condition where one thread updates a threshold mid-evaluation while the policy is computing a result.

For dynamic rules, create a **new snapshot** and swap configuration at an appropriate boundary. If all routers over a short window must use the same version, include `rulesVersion` in the message or tracking context. Avoid reading mutable configuration between `if` statements during a single routing evaluation.

### 10.1. Time-dependent rules

An example condition like "only route priority during business hours" easily breaks if the policy calls `LocalDateTime.now()` inside the method. Make the **reference timestamp** an input:

~~~java
import java.time.Instant;

public record RoutingEvaluation(
        OrderCandidate order,
        Instant evaluatedAt
) {}
~~~

A step at the call boundary is responsible for recording `evaluatedAt` and applying the proper timezone/business calendar. The policy uses a **fixed input value**, making it testable across timestamps, day boundaries, and timezone transitions without depending on the host clock.

## 11. Router with Filter, Transformer, and Recipient List Router

These patterns can appear together, yet do not replace one another.

### 11.1. Filter before Router

A Filter decides whether a message qualifies to proceed. The Router then picks the right branch for **already-valid** messages.

~~~mermaid
flowchart LR
    IN["Input"] --> FILT{"Filter / validation"}
    FILT -->|Valid| ROUTE{"Router"}
    FILT -->|Invalid| REJECT["Reject"]
    ROUTE --> A["Branch A"]
    ROUTE --> B["Branch B"]
    ROUTE --> C["Branch C"]
~~~

If a missing field causes the policy to throw `IllegalArgumentException`, validation can be placed near the ingress point to route messages to a reject flow with a specific error code. Avoid using the `STANDARD` route as a dumping ground to swallow unverifiable data.

### 11.2. Transformer before Router

If payloads from multiple sources have different field names or units, a Transformer should normalize them before the policy runs:

~~~text
RawOrder JSON / MQ payload
    -> Decode + Validate
    -> Transformer (NormalizedOrder)
    -> Risk enrichment (trusted source)
    -> Pure routing policy
    -> Content-Based Router
    -> Destination channel
~~~

The Transformer handles normalization; the Router handles selection. When a transformer returns a full `Message`, it must preserve `traceId`, `businessCorrelationId`, and metadata needed downstream; do not assume all headers propagate automatically.

### 11.3. When multiple destinations are needed, consider Recipient List Router

**Content-Based Router picks one destination** as the primary business decision in our example. If a message must go simultaneously to audit, analytics, and notification, consider **PublishSubscribeChannel** or **Recipient List Router**.

| Scenario | Suggested pattern |
|---|---|
| Pick exactly one branch by risk score | Content-Based Router |
| Send every message to all subscribers | Publish–Subscribe |
| Select a **set of destinations** varying by condition | Recipient List Router |
| Drop messages failing criteria | Filter |
| Split one order into multiple line items | Splitter |

Do not mix choosing **one primary processing route** with **broadcasting events to multiple observers**. Split them into two steps if you truly need both.

## 12. Correlation, retry, and side effects

A pure routing policy is especially valuable when messages are redelivered or replayed.

### 12.1. Correlation ID vs. Message ID

- `MessageHeaders.ID` identifies a **message instance**; creating a new message can change the ID.
- `businessCorrelationId` links multiple steps of one order, e.g., `order-1001`.
- `traceId` tracks execution across handlers and services.
- Splitter/Aggregator `correlationId` groups parts together and must be preserved if downstream branches depend on it.

A standard Router forwards the inbound message to the destination channel, so metadata travels along. If a branch includes a Transformer returning a new `Message<?>`, verify which headers must be kept. Avoid building policies on message IDs if you need consistent decisions across replays.

### 12.2. Retries should not duplicate router side effects

If a route decides `REVIEW` for an order, retrying with the same input and same rules should continue deciding `REVIEW`. However, sending a message to a handler that performs side effects **can** cause that operation to execute again. Therefore:

- The policy is a pure function, so recomputing it produces no side effects on its own.
- Handlers on destination branches require idempotency if the system supports retries/replays.
- Never send emails or invoke payments inside a route predicate.
- When a replay needs to reproduce a historical decision, persist the relevant rule version/context or the emitted decision according to contract.

### 12.3. Policy errors vs. handler errors

The two error types are handled differently:

| Error | Example | Where to handle |
|---|---|---|
| Input violates contract | `riskScore=101` | Validation/reject at ingress or policy error |
| Non-existent destination | Misspelled channel bean name | Routing configuration and startup/integration tests |
| External API timeout | Downstream handler calls partner | Appropriate retry/error channel on that branch |
| Duplicate message on replay | Consumer sees same event ID | Idempotency in handler or adapter |
| Config change alters result | New rules version | Version management and replay policy |

Error channels in Spring Integration must be configured according to topology. In synchronous flows, exceptions may propagate back to the caller; in asynchronous flows, the system may publish an `ErrorMessage` to an error channel depending on configuration. Do not assume that having an `errorChannel` header means every router exception will automatically flow through that channel in all cases.

## 13. Observing routing decisions while keeping the policy pure

Logging and metrics are essential, but placing them directly inside `decide` introduces side effects. A clean approach is:

1. The policy computes `RouteDecision`.
2. The router adapter or an observation step records metrics/logs **outside** the pure function.
3. The system attaches `traceId`, `businessCorrelationId`, rules version, and destination name to diagnostic events when needed.

Illustrative facade separating the two concerns:

~~~java
public final class ObservedRoutingService {

    private final OrderRoutingPolicy policy;
    private final RoutingObserver observer;

    public ObservedRoutingService(
            OrderRoutingPolicy policy,
            RoutingObserver observer) {
        this.policy = policy;
        this.observer = observer;
    }

    public RouteDecision route(
            OrderCandidate order,
            String correlationId) {
        RouteDecision decision = policy.decide(order);

        // Side effects stay strictly in the coordination/observation layer.
        observer.record(correlationId, decision);

        return decision;
    }
}

// Observability layer abstraction:
interface RoutingObserver {
    void record(String correlationId, RouteDecision decision);
}
~~~

If observability loses connectivity, define whether metric-recording failures are allowed to fail routing. In many cases, business operations should not depend on metric emission, though the final choice should follow the application's SLO and operational policy.

Avoid logging full payloads or customer details just to prove a route; logging the **decision**, **rule version**, **correlation**, **source**, and a few safe diagnostic fields is usually enough.

### 13.1. What should be measured?

| Metric/trace | Meaning | Notes |
|---|---|---|
| `routing_decisions_total{decision=...}` | Message count per route | `decision` label has low cardinality |
| `routing_rejections_total{reason=...}` | Rejected input count | Stable error codes; never put order ID in labels |
| `routing_failures_total{type=...}` | Policy or channel resolution errors | Separate code/config errors from data errors |
| Routing step duration | Track latency as load grows | Measure at endpoint rather than inside business policy |
| Trace span with correlation | Trace path across branches | Never include secrets or PII in tags |

A fast pure policy does not guarantee the whole flow is fast: latency can come from enrichment, async channels, brokers, or downstream handlers.

## 14. Common design mistakes

### Mistake 1 — Router calls an API to decide the route

**Symptom:** slow, flaky routing; unit tests must mock an HTTP client, and retries call the API again.

**Fix:** place an enrichment step before the router, build a typed input, and run a pure policy. If external state must be checked close to the transaction, keep that logic inside the corresponding handler.

### Mistake 2 — Route depends on current time or randomness inside

**Symptom:** the same event takes two different branches in the morning vs. afternoon; tests pass intermittently.

**Fix:** pass `evaluatedAt` or a reproducible rule/context snapshot. These parameters are **inputs** to the decision function.

### Mistake 3 — Not defining condition precedence

**Symptom:** high-risk VIP orders get routed to the fast track.

**Fix:** write a decision table, test inputs satisfying **multiple conditions simultaneously**, and document priority in the policy.

### Mistake 4 — Mixing channel names with business terminology

**Symptom:** renaming a channel bean requires editing logic in multiple places.

**Fix:** have the policy return an enum; a single adapter layer maps enum values to channel beans. Test both unit policy and integration wiring.

### Mistake 5 — Using unverified header data

**Symptom:** a client sends `priority=true` or an internal channel name to self-select the priority flow.

**Fix:** verify principal/tenant and allowed fields at ingress; normalize into a `trustedContext`. Never take an arbitrary client string as a channel name.

### Mistake 6 — Defaulting all invalid data to the STANDARD branch

**Symptom:** a negative or null risk score slips into standard processing.

**Fix:** clearly define valid data and provide a reject/error flow; the `STANDARD` fallback is strictly for **valid orders** that match no specialized rule.

### Mistake 7 — Testing only the policy's return value

**Symptom:** unit tests are green, but deployment is missing the `orders.priority` bean.

**Fix:** write integration tests that send to `orders.toRoute` and receive from the output channels, verifying only the expected branch receives the message.

### Mistake 8 — Mutable payload where policy depends on what another branch modified

**Symptom:** routing changes depending on thread scheduling.

**Fix:** use immutable payload DTOs and defensive copies for collections; never mutate inputs. A read-only `MessageHeaders` map does not automatically make objects nested inside payloads or headers deeply immutable.

### Mistake 9 — Assuming a successful route means business processing succeeded

**Symptom:** `send()` returns `true`, yet downstream fails or is still running asynchronously.

**Fix:** define the contract clearly between routing and business outcomes. For request–reply, use an appropriate Gateway/reply flow; for events, observe per-branch processing status or broker acks as required.

## 15. Practice exercise: routing orders to the right branch

**Context:** an e-commerce platform receives `OrderCandidate` messages containing `orderId`, `total`, `vip`, and `riskScore`. The system needs to process high-risk orders manually, high-value VIP orders quickly, and the rest normally.

### 15.1. Implementation requirements

1. Create an immutable `OrderCandidate` and a `RouteDecision` enum with `REVIEW`, `PRIORITY`, and `STANDARD`.
2. Write a pure Java `OrderRoutingPolicy.decide(...)` method with the stated thresholds and priority order.
3. Use JUnit parameterized tests for the decision table, especially the `79/80` and `499.99/500` boundaries.
4. Write a `@Router` that accepts the payload, invokes the policy, and returns the corresponding channel name.
5. Declare three output channels and send events carrying a `traceId` header into the flow.
6. Test that every message arrives at **exactly one** destination queue, preserving payload and `traceId`, while the other two queues remain empty.
7. Add a validation/reject step before the router so invalid data never slips into `STANDARD`.
8. Temporarily change a channel name in the adapter and verify the integration test catches the misconfiguration.
9. Advanced scenario: turn hard-coded thresholds into a `RoutingRules` snapshot, write tests with two configuration versions, and compare results.
10. Advanced scenario: create a `RoutingObserver` outside the policy to count routes, ensuring pure policy tests remain free of metrics system dependencies.

### 15.2. Completion criteria

- For any valid input, the policy **always returns exactly one** defined decision.
- The review rule takes precedence when VIP conditions are also met.
- The policy makes no network, database, clock, or channel calls.
- Invalid data has well-defined behavior and is never accidentally routed to a business branch.
- Spring Integration resolves channel names accurately and delivers messages to the chosen branch.
- Tracing metadata is preserved across the router.
- Boundary cases and configuration errors are caught by meaningful tests.

### 15.3. Self-check questions

1. Why should `OrderRoutingPolicy` return an enum instead of returning channel names directly?
2. Is the policy still pure if the method calls `Instant.now()` or reads a mutable global variable?
3. Where must a VIP order totaling `900.00` with `riskScore=90` go, and why?
4. Why is `BigDecimal.compareTo` more suitable than `equals` when comparing monetary thresholds?
5. Why do pure JUnit policy tests not prove that the `orders.review` channel exists?
6. Which case is a valid fallback, and which is a validation error?
7. If risk scores are fetched from an external system, at which step should the API be called?
8. Why shouldn't the router send an email immediately when deciding `REVIEW`?
9. In an async setup, what does `send()==true` guarantee and what does it not guarantee?
10. How can an event be replayed in the future while still explaining its historical routing decision?

## 16. Pre-implementation design checklist

- [ ] Policy is written as a pure Java function with a clear, descriptive name.
- [ ] Input data is strongly typed, immutable, or defensively copied where needed.
- [ ] All trusted header sources are verified before the router.
- [ ] Decision table clarifies **precedence** when conditions overlap.
- [ ] Thresholds are tested right at boundaries using parameterized tests.
- [ ] Invalid data has a dedicated reject/error flow; no silent fallback.
- [ ] Policy returns `RouteDecision`; adapter maps decisions to channels.
- [ ] Every destination channel is declared, started, and tested through the flow.
- [ ] Necessary trace/correlation headers are preserved during forwarding and transformation.
- [ ] No side effects, network calls, or DB queries inside `decide`.
- [ ] Retry and idempotency for each handler are designed independently of the routing decision.
- [ ] Logging/metrics sit outside the policy and do not expose sensitive data.
- [ ] If thresholds change over time, a rules snapshot/version exists for diagnostics and replay.

## 17. Summary

A maintainable **Content-Based Router** has two parts: a **pure policy** deciding *where a message should go* and a **Spring Integration adapter** connecting that decision to *actual channels*. When the policy accepts a trusted DTO/metadata and returns an enum, it can be tested quickly, deterministically, and without framework dependencies; integration tests then verify that routing actually works in the live flow.

In the **SPRING_INTEGRATION_PATTERN** module, this provides the foundation for combining Router with Filter, Transformer, Splitter/Aggregator, Gateway, retry, and error channels. Validation near ingress ensures the policy only receives valid messages; enrichment provides verified data; branch handlers own side effects and idempotency; tracing/correlation makes the entire path observable. A clear, pure, well-tested routing decision reduces coupling and prevents hard-to-find bugs in production.

### References

- Spring Integration Reference — Router: https://docs.spring.io/spring-integration/reference/router.html
- Spring Integration Reference — Java DSL: https://docs.spring.io/spring-integration/reference/dsl.html
- Spring Integration API — `@Router`: https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/Router.html
- Spring Integration Reference — Channel implementations: https://docs.spring.io/spring-integration/reference/channel/implementations.html
- JUnit 5 User Guide — Parameterized Tests: https://junit.org/junit5/docs/current/user-guide/#writing-tests-parameterized-tests
