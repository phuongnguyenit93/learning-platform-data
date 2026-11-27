# Testing Accepted, Rejected, and Malformed Messages

## 1. Why Must Three Distinct Message Groups Be Tested Separately?

In **Enterprise Integration Patterns (EIP)**, a **Message Filter** decides whether a message **proceeds or not** using a condition (predicate). In Spring Integration, filters are often placed before Routers, Transformers, Gateways, Service Activators, or outbound adapters to keep ineligible messages from entering deeper into the system.

A common mistake is writing only two tests: "predicate returns `true`" and "predicate returns `false`". In practice, there is a crucial third case: **messages with structural errors or uninterpretable data**. For example:

- **Accepted:** valid order, total amount meets threshold to enter the processing channel.
- **Rejected:** *properly formatted* order, yet does not satisfy intake policy.
- **Malformed:** order missing its order ID, `null` amount, invalid JSON syntax, or a payload of an unexpected type.

These three outcomes **are not equivalent** and require separate paths and tests. Sending a malformed message down the "business rejected" branch can hide producer bugs, mask schema breaks after deployments, or corrupt system metrics.

~~~mermaid
flowchart TD
    I[Inbound message] --> P{Valid parse / schema / type?}
    P -->|No| M[Malformed / validation error]
    P -->|Yes| F{Message Filter predicate}
    F -->|true| A[(orders.accepted)]
    F -->|false| R[(orders.rejected)]
    A --> AH[Accepted Handler]
    R --> RH[Rejected Handler]
    M --> E[Error / quarantine / response]
~~~

The diagram shows **a suggested design contract**, not three default branches automatically created by every Spring Integration filter. A bare Filter only produces allow or discard; to treat "malformed" as an independent category, the application must define explicit **validation, exceptions, or error flows**.

This lesson belongs to the **Filter** chapter of the `SPRING_INTEGRATION_PATTERN` module, where we practice EIPs with Spring Integration to build loosely coupled, extensible message flows. Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, correlation, and branch observability can all work together in this test flow.

### Learning Objectives

After this lesson, learners will be able to:

1. Distinguish `accepted`, `rejected`, and `malformed` by **business and technical semantics**.
2. Write Message Filter predicates without accidentally turning schema errors into `false`.
3. Configure `IntegrationFlow.filter(...)`, `discardChannel`, and `throwExceptionOnRejection` per chosen contract.
4. Write unit tests for boundary conditions and integration tests for channels, handlers, and errors.
5. Distinguish Filter reject/discard from parse errors in inbound adapters and downstream exceptions.
6. Test sync/async flows, request–reply Gateways, error channels, retries, idempotency, and observability.

## 2. Three Message Groups Must Have Clear Contracts

### 2.1. Accepted Is a Filter Decision

A message is **accepted** when:

1. It crosses the parse/validation boundary successfully.
2. The Filter predicate returns `true`.
3. The Filter forwards the message to the output channel or next endpoint.

**Accepted does not mean "downstream business work succeeded".** On synchronous `DirectChannel`, the handler may run in the same dispatch chain; on `QueueChannel` or `ExecutorChannel`, the message may only have been queued for later handling. If downstream fails, that is a **post-Filter processing error**, not the Filter changing its mind to "reject" the message.

### 2.2. Rejected Is a Valid Message That Fails Policy

A message is **rejected** when its payload/schema is sound enough to evaluate, yet the predicate returns `false`. For example, a valid order totaling 2 million in a flow accepting only orders of 5 million or more for priority handling.

Depending on configuration, the Filter can:

- **Discard** (drop from the main route) without sending to an alternative channel.
- **Send to a configured discard channel** for controlled recording/rejection.
- **Throw an exception on rejection** if `throwExceptionOnRejection(true)` is enabled.

`false` cannot universally be labeled "success" or "error": business policy decides whether rejections need auditing, returning a reason to the caller, or intentional dropping.

### 2.3. Malformed Is an Error When Proper Evaluation Is Impossible

A **malformed** message can appear at multiple layers:

| Detection point | Example | Relationship to Filter |
|---|---|---|
| HTTP/Kafka/JMS inbound conversion | Missing JSON brace, bad encoding, unparseable schema. | Can fail **before `Message<OrderEvent>` is ever built**; Filter is never called. |
| Spring payload type/converter | Handler expects `OrderEvent` yet receives unconvertible `String`. | Can throw conversion/type exception when dispatching to Filter. |
| Pre-Filter validation | Blank `orderId`, `null` or negative `amountVnd`. | Validator blocks before predicate. |
| Self-validating predicate | Has `OrderEvent` payload yet required field is invalid. | Predicate **throws an exception** instead of returning `false`. |
| Custom Transformer after Filter | Already accepted yet transformation fails. | Downstream error; does not alter Filter's classification. |

A message lacking `amountVnd` cannot validly be classified as "below the 5-million threshold". Writing `amount == null || amount < threshold` and returning `false` may still pass rejected tests while masking data bugs.

## 3. Defining Business Rules and Test Criteria

### 3.1. Example Policy

A service accepts `OrderEvent` for a priority order processing pipeline. Model:

~~~java
import java.math.BigDecimal;

record OrderEvent(
        String orderId,
        BigDecimal amountVnd,
        String currency) {}
~~~

Conditions:

1. `orderId` is required, non-empty/non-whitespace.
2. `amountVnd` is required and must be greater than 0.
3. `currency` must be `VND` under **this example's contract**; other currencies must be converted or schema-rejected at the boundary, never compared directly against a VND threshold.
4. For valid data: `amountVnd >= 5_000_000` is **accepted**, lower is **rejected**.
5. For contract-invalid data: emit **malformed error**, reaching neither accepted nor rejected channel.

This is a pedagogical policy for understanding Filter mechanics, not a universal commercial rule.

### 3.2. Full Truth Table

| `orderId` | `amountVnd` | `currency` | Outcome | Explanation |
|---|---:|---|---|---|
| `O-1` | 5,000,000 | VND | **Accepted** | Exact threshold is accepted. |
| `O-2` | 8,500,000 | VND | **Accepted** | Above threshold. |
| `O-3` | 4,999,999 | VND | **Rejected** | Valid, just below threshold. |
| `O-4` | 1 | VND | **Rejected** | Valid positive amount, below threshold. |
| `O-5` | 0 | VND | **Malformed** | Fails valid-data rule; not a valid rejection. |
| `O-6` | -100 | VND | **Malformed** | Negative amounts are disallowed. |
| `O-7` | `null` | VND | **Malformed** | No data to compare. |
| `"   "` | 6,000,000 | VND | **Malformed** | Blank order ID. |
| `O-9` | 6,000,000 | USD | **Malformed** | Violates this flow's currency contract. |
| Non-`OrderEvent` payload | — | — | **Malformed/type error** | Cannot validly evaluate typed predicate. |

**Boundary values** 4,999,999 / 5,000,000 / 5,000,001 are especially important to catch `>` vs. `>=` mistakes. For `BigDecimal`, use `compareTo` when comparing numeric values; `equals` can return false for equal values with different scales (e.g., `5.0` and `5.00`).

## 4. Filter Placement in Integration Flows

### 4.1. Filter Before Router

~~~text
HTTP / Kafka / Gateway
   -> Parse + normalize
   -> Validate required fields
   -> Filter eligibility
       -> accepted -> Router/Transformer/Handler
       -> rejected -> discard / rejection handler
       -> malformed -> exception / error flow
~~~

The Filter's purpose is letting qualifying messages proceed. **Choosing which branch to go to** is the Router's job, while **changing payload representation** is the Transformer's job. Validation can be split into a dedicated endpoint before the Filter when schemas are complex; in the example below, to focus on the three outcomes, validation lives in the policy before checking eligibility.

### 4.2. Do Not Confuse Filtering with Multi-Branch Routing

When a Filter evaluates to `false`, the message **does not continue down the main route**. Never write:

~~~text
Filter(amount >= 5 million)
    -> Filter(amount < 5 million)
    -> rejectedHandler
~~~

and expect an order rejected by the first Filter to reach the second Filter. Those are sequential endpoints, not two independent paths. To handle rejections, use `discardChannel` or a proper Router with mappings/branches.

### 4.3. Different Contracts for Rejection

| Mode | What happens to rejected message? | When appropriate? |
|---|---|---|
| Silent discard | Does not go to main route and has no dedicated receiver. | Only when dropping is intentional and acceptable. |
| `discardChannel` | Routes rejected message to designated channel. | Want metrics, reason storage, quarantine, or separate branch handling. |
| `throwExceptionOnRejection(true)` | Signals rejection via exception in Filter context. | Caller needs synchronous error or separate error flow handles it. |

Do not combine all three configurations into one flow expecting both discard and exception in some assumed order; choose **one primary contract**, then test that exact behavior. Any discard branch also needs a consumer/poller if data must actually be processed.

## 5. Java DSL: Filter with Explicit Accepted/Rejected/Malformed

### 5.1. Validation and Eligibility Policy

The example targets **Java 17+, Spring Boot 3.x, and Spring Integration 6.x** with `spring-boot-starter-integration`. Records/classes share one package in the lesson; in real implementations, place `public` types in separate files per Java conventions.

~~~java
import java.math.BigDecimal;

record OrderEvent(
        String orderId,
        BigDecimal amountVnd,
        String currency) {}

final class OrderEligibilityPolicy {
    private static final BigDecimal MINIMUM =
            new BigDecimal("5000000");

    boolean eligible(OrderEvent order) {
        if (order == null
                || order.orderId() == null
                || order.orderId().isBlank()) {
            throw new IllegalArgumentException(
                    "MALFORMED_ORDER_ID");
        }

        if (order.amountVnd() == null
                || order.amountVnd().signum() <= 0) {
            throw new IllegalArgumentException(
                    "MALFORMED_ORDER_AMOUNT");
        }

        if (!"VND".equals(order.currency())) {
            throw new IllegalArgumentException(
                    "MALFORMED_ORDER_CURRENCY");
        }

        return order.amountVnd().compareTo(MINIMUM) >= 0;
    }
}
~~~

Here `eligible` has three logical outcomes: **return `true`, return `false`, or throw an exception**. An exception is not a third boolean state of the framework, but the application's way of **preventing contract-invalid data from being misread as a valid rejection**.

The reason not to write `return order.amountVnd() != null && order.amountVnd().compareTo(MINIMUM) >= 0;` is that it returns `false` for `null` and erases the distinction between malformed and rejected.

### 5.2. Configuring Two Output Channels and One Filter

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

final class FilterOutcomeProbe {
    final AtomicInteger accepted = new AtomicInteger();
    final AtomicInteger rejected = new AtomicInteger();
}

@Configuration
@EnableIntegration
class OrderFilterConfiguration {

    @Bean(name = "orders.input")
    MessageChannel input() {
        return new DirectChannel();
    }

    @Bean(name = "orders.accepted")
    MessageChannel accepted() {
        return new DirectChannel();
    }

    @Bean(name = "orders.rejected")
    MessageChannel rejected() {
        return new DirectChannel();
    }

    @Bean
    OrderEligibilityPolicy orderEligibilityPolicy() {
        return new OrderEligibilityPolicy();
    }

    @Bean
    FilterOutcomeProbe filterOutcomeProbe() {
        return new FilterOutcomeProbe();
    }

    @Bean
    IntegrationFlow filterOrders(OrderEligibilityPolicy policy) {
        return IntegrationFlow.from("orders.input")
                .filter(OrderEvent.class,
                        policy::eligible,
                        spec -> spec
                                .discardChannel("orders.rejected")
                                .throwExceptionOnRejection(false))
                .channel("orders.accepted")
                .get();
    }

    @Bean
    IntegrationFlow handleAccepted(FilterOutcomeProbe probe) {
        return IntegrationFlow.from("orders.accepted")
                .handle(OrderEvent.class, (order, headers) -> {
                    probe.accepted.incrementAndGet();
                    return null; // One-way terminal handler.
                })
                .get();
    }

    @Bean
    IntegrationFlow handleRejected(FilterOutcomeProbe probe) {
        return IntegrationFlow.from("orders.rejected")
                .handle(OrderEvent.class, (order, headers) -> {
                    probe.rejected.incrementAndGet();
                    return null;
                })
                .get();
    }
}
~~~

**Explanation:**

- `orders.input` is the entry channel.
- `OrderEligibilityPolicy` classifies messages; for malformed data, the policy throws an exception and sends to neither output channel.
- `discardChannel("orders.rejected")` receives messages that are **valid yet predicate returns `false`**.
- `throwExceptionOnRejection(false)` enables exercising the configured discard route; this is not "raise an error to caller on every rejection" mode.
- `orders.accepted` receives only messages passed by the Filter.
- Handlers simply increment counters for testing; in production, handlers must process data, store results, and have dedicated error policies.

**Why use `DirectChannel`?** The test example easily confirms synchronous handlers executed before `send` returns. If switched to an executor, queue, or broker, tests must wait for processing signals and distinguish enqueuing from completion.

### 5.3. Sending a Message to the Filter

~~~java
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

// input is the MessageChannel bean named "orders.input".
boolean sent = input.send(
        MessageBuilder.withPayload(
                new OrderEvent(
                        "ORD-1001",
                        new java.math.BigDecimal("7500000"),
                        "VND"))
                .setHeader("traceId", "trace-ORD-1001")
                .build(),
        1_000);
~~~

`sent` only reflects the send operation per channel and endpoint semantics. It is **not** a business flag meaning "accepted by Filter": in this configuration, a valid rejected message can still be sent successfully to the **discard channel** and counted by the rejection handler. Tests must observe **which channel actually received**, never inferring from `send(...)` alone.

## 6. Predicate Unit Tests: Checking Logic Before Spring Context

### 6.1. Checking Accepted and Rejected at Boundaries

First, test `OrderEligibilityPolicy` as a plain Java object:

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OrderEligibilityPolicyTest {
    private final OrderEligibilityPolicy policy =
            new OrderEligibilityPolicy();

    private static OrderEvent order(String id, String amount) {
        return new OrderEvent(id, new BigDecimal(amount), "VND");
    }

    @Test
    void amountJustBelowThresholdIsRejected() {
        assertFalse(policy.eligible(order("O-1", "4999999")));
    }

    @Test
    void amountExactlyAtThresholdIsAccepted() {
        assertTrue(policy.eligible(order("O-2", "5000000")));
    }

    @Test
    void amountAboveThresholdIsAccepted() {
        assertTrue(policy.eligible(order("O-3", "5000001")));
    }

    @Test
    void decimalScaleDoesNotChangeEligibility() {
        assertTrue(policy.eligible(order("O-4", "5000000.00")));
    }

    @Test
    void tinyButPositiveAmountIsValidAndRejected() {
        assertFalse(policy.eligible(order("O-5", "0.01")));
    }
}
~~~

These tests only verify decision logic. **They do not yet confirm** that `IntegrationFlow` routed messages to the right channels, nor do they test converters, error flows, or consumer lifecycles.

If the threshold can change in production, avoid hardcoding expectations against an unreviewed policy. Inject the threshold into the policy, write tests for configured thresholds, and verify configuration versions/sources. This lesson fixes the threshold to focus on the three message states.

### 6.2. Malformed Must Fail Explicitly

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class OrderEligibilityMalformedTest {
    private final OrderEligibilityPolicy policy =
            new OrderEligibilityPolicy();

    @Test
    void missingAmountIsMalformedNotRejected() {
        IllegalArgumentException error =
                assertThrows(IllegalArgumentException.class, () ->
                        policy.eligible(
                                new OrderEvent("O-1", null, "VND")));

        assertEquals("MALFORMED_ORDER_AMOUNT", error.getMessage());
    }

    @Test
    void zeroAmountIsMalformedNotRejected() {
        IllegalArgumentException error =
                assertThrows(IllegalArgumentException.class, () ->
                        policy.eligible(new OrderEvent(
                                "O-2", BigDecimal.ZERO, "VND")));

        assertEquals("MALFORMED_ORDER_AMOUNT", error.getMessage());
    }

    @Test
    void negativeAmountIsMalformed() {
        assertThrows(IllegalArgumentException.class, () ->
                policy.eligible(new OrderEvent(
                        "O-3", new BigDecimal("-25"), "VND")));
    }

    @Test
    void blankOrderIdIsMalformed() {
        IllegalArgumentException error =
                assertThrows(IllegalArgumentException.class, () ->
                        policy.eligible(new OrderEvent(
                                "   ", new BigDecimal("6000000"), "VND")));

        assertEquals("MALFORMED_ORDER_ID", error.getMessage());
    }

    @Test
    void wrongCurrencyIsMalformed() {
        IllegalArgumentException error =
                assertThrows(IllegalArgumentException.class, () ->
                        policy.eligible(new OrderEvent(
                                "O-5", new BigDecimal("6000000"), "USD")));

        assertEquals("MALFORMED_ORDER_CURRENCY", error.getMessage());
    }

    @Test
    void nullOrderIsMalformed() {
        assertThrows(IllegalArgumentException.class, () ->
                policy.eligible(null));
    }
}
~~~

**Why assert the error code?** When data errors are lumped into `false`, the flow can appear to succeed if discard is configured. Asserting `MALFORMED_ORDER_AMOUNT` proves the policy intentionally **separates schema errors from business rejections**.

In production, exceptions/error objects should carry **stable error codes** rather than relying solely on descriptive strings. In this lesson, string codes make checks easy to read; when designing HTTP/gRPC/broker contracts, map internal codes to permitted statuses or error payloads.

## 7. Integration Testing: Proving the Right Channel Receives Messages

### 7.1. Using Spring Test to Spin Up the Real Flow

From `OrderFilterConfiguration`, write tests with `@SpringJUnitConfig`. Each test gets a fresh Spring context via `@DirtiesContext` so mutable counters from earlier tests cannot affect results.

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(OrderFilterConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class OrderFilterRoutingTest {

    @Autowired
    @Qualifier("orders.input")
    private MessageChannel input;

    @Autowired
    private FilterOutcomeProbe probe;

    private void send(String id, String amount) {
        boolean sent = input.send(
                MessageBuilder.withPayload(new OrderEvent(
                        id, new BigDecimal(amount), "VND"))
                        .build(),
                1_000);
        assertTrue(sent);
    }

    @Test
    void acceptedMessageReachesOnlyAcceptedHandler() {
        send("O-100", "5000000");

        assertEquals(1, probe.accepted.get());
        assertEquals(0, probe.rejected.get());
    }

    @Test
    void validButIneligibleMessageReachesOnlyDiscardHandler() {
        send("O-101", "4999999");

        assertEquals(0, probe.accepted.get());
        assertEquals(1, probe.rejected.get());
    }

    @Test
    void multipleMessagesAreCountedPerOutcome() {
        send("O-1", "6000000");
        send("O-2", "2000000");
        send("O-3", "8000000");

        assertEquals(2, probe.accepted.get());
        assertEquals(1, probe.rejected.get());
    }
}
~~~

In this example configuration, `orders.input`, `orders.accepted`, and `orders.rejected` are all `DirectChannel`s; synchronous terminal handlers update the probe. Thus, tests can inspect counters right after `send` **within the scope of this demo**.

For production tests involving databases, emails, outbound gateways, or async processing, verify actual **business outcome** milestones rather than substituting demo counters for commit proof.

### 7.2. Integration Test: Malformed Reaches Neither Result Channel

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(OrderFilterConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class OrderFilterMalformedFlowTest {

    @Autowired
    @Qualifier("orders.input")
    private MessageChannel input;

    @Autowired
    private FilterOutcomeProbe probe;

    private static boolean hasCauseText(
            Throwable error, String expected) {
        for (Throwable cause = error;
                cause != null; cause = cause.getCause()) {
            if (cause.getMessage() != null
                    && cause.getMessage().contains(expected)) {
                return true;
            }
        }
        return false;
    }

    @Test
    void missingAmountDoesNotBecomeOrdinaryRejection() {
        RuntimeException error = assertThrows(
                RuntimeException.class,
                () -> input.send(MessageBuilder.withPayload(
                        new OrderEvent("O-BAD", null, "VND"))
                        .build(), 1_000));

        assertTrue(hasCauseText(error, "MALFORMED_ORDER_AMOUNT"));
        assertEquals(0, probe.accepted.get());
        assertEquals(0, probe.rejected.get());
    }

    @Test
    void invalidCurrencyDoesNotReachAcceptedOrRejected() {
        RuntimeException error = assertThrows(
                RuntimeException.class,
                () -> input.send(MessageBuilder.withPayload(
                        new OrderEvent(
                                "O-USD", new BigDecimal("6000000"), "USD"))
                        .build(), 1_000));

        assertTrue(hasCauseText(error, "MALFORMED_ORDER_CURRENCY"));
        assertEquals(0, probe.accepted.get());
        assertEquals(0, probe.rejected.get());
    }
}
~~~

**Why not strictly catch `IllegalArgumentException` in the integration test?** When an exception originates inside a Spring Integration endpoint, the framework may wrap it in `MessageHandlingException` or another messaging-level exception. The test inspects the **cause chain** and verifies zero counts on both output channels to prove intent, without coupling tightly to one wrapper class that could differ across versions.

### 7.3. Testing Wrong-Type Payloads

Another case is an inbound channel receiving `Message<String>` instead of `Message<OrderEvent>`:

~~~java
// In a context supporting only OrderEvent,
// send a payload that cannot convert to OrderEvent:
RuntimeException error = assertThrows(
        RuntimeException.class,
        () -> input.send(
                MessageBuilder.withPayload("not-an-OrderEvent")
                        .build(), 1_000));
~~~

Key checkpoint: **never allow a wrong-type message to turn into a valid business rejection**. However, the **exception type and failure point** may depend on registered `MessageConverter`/integration infrastructure. When an application registers an automatic converter from `String` to `OrderEvent`, supply an input guaranteed not to convert and verify at that specific converter boundary; do not claim every `String` always throws.

**Do not call `MessageBuilder.withPayload(null)` to test malformed:** standard Spring message builders forbid `null` payloads, failing immediately when constructing the message before the Filter runs. To test null fields inside a payload, use a record with a `null` field as shown above.

## 8. Malformed at Inbound Adapters May Never Reach the Filter

### 8.1. Invalid JSON Syntax vs. Valid JSON Failing Schema

These two requests fail at different levels:

~~~http
POST /orders
Content-Type: application/json

{"orderId":"O-1","amountVnd":
~~~

This is **unparseable JSON**. The HTTP adapter/controller/Jackson may reject it before a DTO or Spring message for the integration flow is ever created.

Meanwhile:

~~~json
{
  "orderId": "O-2",
  "amountVnd": null,
  "currency": "VND"
}
~~~

This is **syntactically valid JSON** that violates required-field contracts. Depending on binding/validation setup, it may be rejected at bean validation or produce an `OrderEvent` with `null` amount, which the policy rejects with an exception as in section 5.

Both cases belong in the **malformed test matrix**, yet do not assume every error is caught by `MessageFilter`.

### 8.2. Test at the Right Entry Point

| Test level | Where is input sent? | What path is tested? |
|---|---|---|
| Policy unit test | Call `eligible(OrderEvent)` directly. | Rules and validation inside policy. |
| Channel integration test | Send `Message<OrderEvent>` to `orders.input`. | Filter, discard channel, subscribers. |
| Adapter-level test | Send real HTTP/Kafka/JMS payload. | Parsing, schema conversion, header mapping, pre-Filter error handling. |
| End-to-end test | Across real boundaries to downstream. | Delivery, transactions, timeouts, and business outcomes. |

At HTTP ingress, an application may map malformed inputs to **400 Bad Request** for syntax or missing required fields, while a business rejection returns a response with its own domain code/status. Do not force one HTTP status across all cases if the API contract has distinct semantics. With Kafka/brokers, malformed records may need quarantine/DLQ and dedicated offset-commit policies; an HTTP status is no answer for asynchronous consumers.

### 8.3. Containing Malformed Errors from Affecting Other Messages

A consumer reading a batch or event stream may hit one bad record. Never default to infinite batch retries over one permanently malformed JSON record. Consider:

1. Logging a **stable error code** and required source/partition/offset or message reference.
2. Saving/quarantining the payload securely in compliance with sensitive-data rules.
3. Deciding whether to skip the bad record and continue or halt the partition/batch.
4. Configuring retries only for transient errors; permanent schema errors usually need producer or data fixes.
5. Testing replays after schema fixes and checking deduplication.

Never infer from the name `errorChannel` that every adapter automatically sends to a DLQ or prevents data loss: behavior depends on transport, error flow, acknowledgments, and specific configuration.

## 9. Rejected via Discard Channel Differs from Exception Rejection

### 9.1. Choose an Intentional Policy

`OrderFilterConfiguration` uses:

~~~java
.filter(OrderEvent.class,
        policy::eligible,
        spec -> spec
                .discardChannel("orders.rejected")
                .throwExceptionOnRejection(false))
~~~

This is a **rejected message → rejection handler** route, not an infrastructure instruction to throw an exception on every discarded message.

If an API needs to **fail immediately** when a message fails conditions, an **alternative** configuration is:

~~~java
// Alternative Filter fragment in a separate flow; not chained
// after the main example's discard configuration.
.filter(OrderEvent.class,
        policy::eligible,
        spec -> spec.throwExceptionOnRejection(true))
~~~

In this mode, a `false` outcome turns into a **rejection exception** per Filter mechanics; it is no longer a normal message processed on `orders.rejected` as in the demo setup. Write dedicated tests verifying the error type and response path when used with `@MessagingGateway` or HTTP inbound.

### 9.2. Why Can a Gateway Hang When a Filter Discards a Message?

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant G as MessagingGateway
    participant F as Filter
    participant D as Discard Handler
    C->>G: submit(OrderEvent)
    G->>F: Message + replyChannel
    F->>D: predicate=false
    D-->>F: ends one-way
    Note over G: No business reply
    G-->>C: Timeout (if awaiting reply)
~~~

If a caller invokes a **request–reply Gateway** yet the Filter discards and the discard handler **sends no reply**, the Gateway may wait until timeout. That is not necessarily a bug in the predicate; it is a **reply contract** bug.

Design options:

| Caller contract | Suitable implementation |
|---|---|
| **One-way event emission only** | Fire-and-forget with discard handler, metrics, and recovery if needed. |
| **Caller needs immediate accepted/rejected status** | Design replies for **both accepted and rejected branches**; consider Router/handler returning business responses instead of silent Filter discard. |
| **Caller treats rejected as an error** | Configure Filter with `throwExceptionOnRejection(true)` or throw a domain exception mapped to an API error. |
| **Caller wants async processing** | Return an intake acknowledgment and provide status/outcome events later; never pretend the pipeline already finished. |

In particular, **`accepted=true` at the Filter** does not guarantee the Gateway receives a reply: if downstream is strictly a one-way adapter, request–reply still needs another contract.

### 9.3. Does a Successful Discard Guarantee Durable Storage?

No. In the demo, the discard channel is a `DirectChannel` and the handler only increments a counter. If production must persist rejections for investigation or replay:

- Route rejections to a **store/broker** with configured durability and retention.
- Record an application-generated **reason code** or classification metadata; a raw `MessageFilter` only knows the predicate returned `false`, without inferring detailed business reasons.
- Attach business/event IDs to prevent duplicate writes when producers retry.
- Avoid logging/persisting full sensitive payloads unless truly necessary.
- Alert on abnormal rejection rate spikes, as they may signal upstream data or policy changes.

If a business rejection needs no persistence yet must return a business response, design an explicit discard/reply branch rather than adding an unconsumed queue.

## 10. Synchronous and Asynchronous Error Handling

### 10.1. Errors from a Synchronous Filter

With `DirectChannel`, when `OrderEligibilityPolicy.eligible(...)` throws `IllegalArgumentException`, the exception can unwind up the call stack to `MessageChannel.send(...)` or the Gateway via framework wrappers. That is why the malformed integration test in section 7 catches `RuntimeException` and inspects the cause chain.

Never assume that having a global `errorChannel` bean causes all synchronous calls to suppress exceptions and route them solely to that channel. How `ErrorMessage` is sent depends on handler/adapter context and error-handling configuration.

### 10.2. Errors When Filter Runs on Another Thread

When placing an `ExecutorChannel` or `QueueChannel`/poller before the Filter:

~~~text
Publisher
    |
    v
Async Channel / Queue
    |
    v
Filter
    | accepted -> Handler
    | rejected -> Discard
    | malformed -> exception -> Error handling context
~~~

The publisher may already have received **accepted/enqueued** before the Filter actually runs. Malformed exceptions arise on the **worker/poller thread**, not automatically thrown back to the original sending thread.

Testing should be split into two parts:

1. **Producer-level:** was the message enqueued/accepted per contract; how do queue-full, send timeout, and executor rejection behave?
2. **Consumer-level:** what did the Filter evaluate, which handler received it, which error flow recorded malformed, and how do retry/ack behave?

### 10.3. `ErrorMessage` and Failed Message Details

In supporting asynchronous error-handling contexts, Spring Integration can create an `ErrorMessage` wrapping the `Throwable`; when the `Throwable` is a `MessagingException`, `failedMessage` can often be inspected. However:

- Not every exception carries the full original message.
- Not every adapter/poller shares the same `errorChannel`.
- **Ingress JSON decode** errors can occur before `Message<OrderEvent>` exists, so design where transport-level correlation/request IDs are preserved.
- If the malformed error flow itself throws without recovery, the transport may retry/redeliver under its own policy.

Test with **real adapters** when verifying offset acknowledgment, DLQs, broker retries, or transactional behavior. A Filter unit test cannot prove Kafka/JMS/AMQP delivery guarantees.

### 10.4. Error, Retry, and Idempotency Matrix

| Situation | Retry the same message immediately? | Recommended action |
|---|---|---|
| Accepted, temporary downstream timeout | Possibly, if safe. | Bounded retry, backoff, and idempotency. |
| Accepted, downstream committed yet reply lost | Must verify status. | Reconcile; do not repeat side effects. |
| Rejected by business rule | Usually no. | Business response/discard/audit per contract. |
| Permanently malformed JSON | Never retry indefinitely. | Reject/quarantine; fix producer/schema. |
| Malformed due to unsupported currency | Do not retry same payload hoping rules change. | Validation/rejection and proper conversion workflow. |
| Parse failed because schema registry temporarily unavailable | May be a recoverable infra error. | Bounded retry; classify separately from truly malformed data. |
| Filter output channel has no subscriber | Retries may not help if misconfigured. | Fix deployment/lifecycle; test readiness. |
| Executor queue full | Apply backpressure. | Bounded retry/overload response; scale appropriately. |

A message **legitimately rejected** by the Filter should not be re-sent as a technical error, wasting load. When retrying accepted messages after downstream failures, keep event/operation IDs stable so target handlers can deduplicate.

## 11. Layered Test Coverage Table

| ID | Input | Test point | Expected outcome | Negative assertion |
|---|---|---|---|---|
| F-01 | Amount 5,000,000 VND | Unit + Flow | Accepted | Rejected count = 0 |
| F-02 | Amount 5,000,001 VND | Unit | Accepted | No validation throw |
| F-03 | Amount 4,999,999 VND | Unit + Flow | Rejected, goes to discard | Accepted count = 0 |
| F-04 | Amount 1 VND | Unit | Rejected | Not treated as malformed |
| F-05 | Amount 0 VND | Unit + Flow | Malformed error | Both channel counts = 0 |
| F-06 | Amount -1 VND | Unit | Malformed error | Not routed to accepted/rejected |
| F-07 | Amount `null` | Unit + Flow | Malformed amount | Rejected receives nothing |
| F-08 | Blank `orderId` | Unit | Malformed ID | Not confused with business reject |
| F-09 | Currency USD | Unit + Flow | Malformed currency per contract | VND threshold not applied |
| F-10 | Unconvertible `String` payload | Flow/Converter | Conversion/type error | Not accepted as valid `OrderEvent` |
| F-11 | Unparseable JSON | Adapter | Ingress error before Filter | Accepted/rejected counts unchanged |
| F-12 | Valid JSON, missing field | Adapter/Flow | Validation or malformed | Not silently discarded |
| F-13 | Rejected + `discardChannel` | Flow | Discard handler receives | Accepted handler receives nothing |
| F-14 | Rejected + `throwExceptionOnRejection(true)` | Separate flow | Rejection exception | Not tested as successful discard |
| F-15 | Malformed on async consumer | Async integration | Context-specific error/recovery | Producer ack not treated as processed |
| F-16 | Output channel has no consumer | Integration | Channel-specific dispatch error/timeout | Not reported as business success |
| F-17 | Downstream fails after accepted | Integration | Processing error | Not counted as Filter rejected |
| F-18 | Gateway with one-way Filter discard | Gateway integration | Timeout/contract failure observed | No reply assumed |
| F-19 | Redelivery with same event ID | End-to-end | Proper idempotency/recovery | No duplicate side effects |
| F-20 | High message volume | Load test | Metrics, throughput, backpressure | No silent drops |

The test suite does not have to run every scenario through real adapters on every commit. However, **clearly separate unit / integration / end-to-end levels** and ensure critical scenarios are tested at a level capable of catching real bugs.

## 12. Observing Accepted, Rejected, and Malformed Properly

### 12.1. Separate Filter Decision Logs from Downstream Outcomes

A suggested event set:

~~~text
event=FILTER_EVALUATED orderId=O-100 traceId=T-100
  filter=priorityOrderFilter outcome=ACCEPTED
  policyVersion=priority-v1

event=FILTER_EVALUATED orderId=O-101 traceId=T-101
  filter=priorityOrderFilter outcome=REJECTED
  reasonCode=BELOW_THRESHOLD

event=FILTER_VALIDATION_FAILED orderId=O-BAD traceId=T-102
  filter=priorityOrderFilter outcome=MALFORMED
  reasonCode=MALFORMED_ORDER_AMOUNT

event=BRANCH_PROCESSING_FAILED orderId=O-100 traceId=T-100
  branch=orders.accepted reasonCode=OUTBOUND_TIMEOUT
~~~

This is an **application-suggested log schema**, not Spring Integration default logs. `FILTER_EVALUATED=ACCEPTED` does not mean `BRANCH_COMPLETED`. For malformed errors occurring before payload binding, `orderId` may be absent; use a safe request/transport ID for tracing instead of inventing a business ID.

### 12.2. Metrics to Monitor

| Metric | Meaning |
|---|---|
| `filter_accepted_total` | Messages allowed through by Filter. |
| `filter_rejected_total` | Valid messages rejected by policy. |
| `filter_malformed_total` | Schema/validation failures observed at the proper layer. |
| `inbound_decode_failed_total` | Payloads failing before reaching Filter. |
| `discard_handler_failed_total` | Failures in rejected branch consumer/side effects. |
| `accepted_branch_completed_total` | Separates accepted from downstream completion. |
| `accepted_branch_failed_total` | Downstream failures after Filter. |
| `error_channel_messages_total` | Volume of `ErrorMessage`s in configured error flow. |
| `queue_depth` / `oldest_message_age` | Whether async branches are building backlog. |

These names are **illustrative application metrics**. If Spring Integration/Micrometer already provides built-in meters for the corresponding components, check semantics before merging or renaming.

Never use `orderId`, `traceId`, or raw payloads as metric labels: cardinality is far too high and may expose sensitive data. Keep those IDs in logs/tracing with proper access control and retention.

### 12.3. Correlation and Message History

Across Filters, accepted/rejected messages can be observed via Message History when tracking is enabled, though Message History **does not automatically capture business outcomes, rejection reasons, or boundary decode errors**. With Splitter/Aggregator:

- Messages with `correlationId` and sequence metadata must preserve them per contract across Filters/adapters.
- If one part is rejected, the Aggregator may **not receive all expected parts**. Define release/timeout policies aware of dropped parts.
- If a malformed message is quarantined, preserve business/group context safely so affected groups can be found.
- Never increment `sequenceSize` or assign fresh correlations arbitrarily at each Filter: groups may stall or mis-aggregate.

### 12.4. Distinguish Filter Metrics from Consumer Metrics

With asynchronous channels, you might see:

~~~text
filter_accepted_total = 1_000
accepted_branch_completed_total = 950
accepted_branch_failed_total = 20
accepted_branch_pending = 30  (per application-tracked state)
~~~

These numbers **merely illustrate** the difference between "passed by Filter" and "processed". Never blindly deduce `pending = accepted - completed - failed` in every model when retries, duplicates, fan-out, or measurement-window skew exist; define counting rules and correlation first.

## 13. Diagnosing Wrong Results in Tests or Production

### 13.1. Rejected Gets Counted as Accepted

**Symptom:** a message with amount 4,999,999 appears in `orders.accepted`.

**Investigation:**

1. Check `compareTo(MINIMUM) >= 0` and currency units.
2. Check that no other flow publishes straight to `orders.accepted`, bypassing the Filter.
3. Check whether the predicate reads the right payload versus a stale header value.
4. Check routing keys and consumer subscriptions if a Router follows the Filter.
5. With dynamic policies, log policy version at evaluation and test boundary values.

Never "fix" this merely by tweaking counters in tests. Verify **the message dispatch path and actually registered policy**.

### 13.2. Malformed Appears on the Discard Channel

**Symptom:** `amountVnd=null`, yet the rejected handler receives the message.

Common cause—a predicate written as:

~~~java
// Violates contract if null amount is defined as malformed:
return order.amountVnd() != null
        && order.amountVnd().compareTo(MINIMUM) >= 0;
~~~

This expression returns `false` when amount is `null`. Filter cannot guess that it is a schema error, so it treats it as a normal rejection. Fix by validating first:

~~~java
if (order.amountVnd() == null) {
    throw new IllegalArgumentException("MALFORMED_ORDER_AMOUNT");
}
return order.amountVnd().compareTo(MINIMUM) >= 0;
~~~

For external inputs, it is often even better to **validate at the inbound boundary** before the Filter, while keeping tests proving the Filter never receives contract-invalid messages.

### 13.3. Filter Is Never Invoked Even Though Input Was Sent

Distinguish the layers:

~~~mermaid
flowchart TD
    A[Producer / adapter] --> B{Message created?}
    B -->|No| C[Parse / conversion error]
    B -->|Yes| D{Input channel dispatched?}
    D -->|No| E[Channel / lifecycle / subscriber error]
    D -->|Yes| F{Filter evaluated?}
    F -->|true| G[Accepted output]
    F -->|false| H[Discard output / throw policy]
    F -->|exception| I[Malformed / evaluation error]
    G --> J{Downstream handled?}
    H --> K{Discard handler handled?}
    J -->|Error| L[Processing error]
    K -->|Error| M[Discard processing error]
~~~

If the failure happened in the inbound JSON converter, **the Filter never received the message**. If the channel had no subscriber, failure happened before the predicate. If the accepted handler received it and failed, **the predicate completed** and the error lies downstream. Log and test each group separately.

### 13.4. Flaky Test Failures on CI

Typical causes:

- Sharing stateful beans across tests without resetting or isolating Spring contexts.
- Using `Thread.sleep` to guess when async handlers finish.
- Tests not checking whether a message went to **the right channel**, checking only a return value from a possibly mis-mocked handler.
- Sending two messages with the same business ID and counting without separating retries/duplicates.
- Matching exact Spring Integration exception message strings instead of cause-chain codes/domain exceptions.
- Assuming a `String` payload never has a converter to DTO.

**Fixes:** use independent test data, intentional `@DirtiesContext`/resets, latches/await with timeouts for async, cause-code matchers, and explicit stubs for external systems. Never make tests "green" by ignoring exceptions or dropping critical assertions.

## 14. Common Mistakes When Designing Filter Tests

| Mistake | Consequence | Better design |
|---|---|---|
| Testing only accepted messages | Misses wrong-branch rejections or silent drops. | Have positive, negative, and malformed suites. |
| Treating `null` as `false` | Producer bugs counted as business rejections. | Separate validation/errors. |
| Using `BigDecimal.equals` for thresholds | Outcomes vary by scale. | Use `compareTo` for numeric comparisons. |
| Treating `send=true` as accepted | Rejected messages with discard handlers can still send successfully. | Assert the actual channel/counter. |
| Rejecting with no discard consumer | Cannot verify handling branch or recovery. | Configure handler/poller per contract. |
| Expecting both discard and exception without checking config | Failure behavior surprises you. | Pick one explicit mode and test separately. |
| Request–reply Gateway crossing a silently dropping Filter | Caller times out despite valid predicate. | Design business replies/errors for every outcome. |
| Conflating parse errors with Filter rejections | HTTP 400, business rejects, and downstream errors mix. | Classify by originating layer. |
| Testing malformed with `MessageBuilder.withPayload(null)` | Fails building message before Filter; never tests policy. | Use null fields or unparseable adapter payloads. |
| Assuming type conversion always behaves identically | Tests break across versions/converters. | Test converters in real context. |
| Treating Filter accepted as downstream committed | Prematurely declares success. | Track accepted, started, completed, failed separately. |
| Infinite retries on bad JSON | Poison messages clog consumers. | Bounded retries, quarantine/DLQ per transport. |
| Losing correlation when Filter sits between Splitter/Aggregator | Group never releases or mis-aggregates. | Design missing-part policy and metadata propagation. |
| Logging full malformed payloads | Data leaks or bloated logs. | Log error codes + minimal IDs/metadata. |
| One test calls real APIs and real email | Flaky, unwanted side effects. | Mock/stub; isolate controlled E2E tests. |

## 15. Hands-on Exercises

1. **Three output paths:** use `OrderFilterConfiguration`. Send one message at the threshold, one below it, and one with `null` amount. Verify accepted=1, rejected=1, and the malformed message increments neither counter.
2. **Boundary checks:** test 4,999,999, 5,000,000, 5,000,001, and 5,000,000.00. Explain why `compareTo` is used.
3. **Separate validation:** move checks for `orderId`, currency, and amount into a validator endpoint before the Filter; preserve identical results for all three groups in integration tests.
4. **Discard vs. exception:** create two separate test `IntegrationFlow`s — one using `discardChannel`, one using `throwExceptionOnRejection(true)` — then compare caller responses and message counts at the rejection handler.
5. **Gateway request–reply:** build a `@MessagingGateway` returning `FilterResult(orderId, status)`. Ensure accepted and rejected get valid business replies while malformed returns a contract error. Avoid infinite Gateway waits.
6. **Malformed JSON input:** write an HTTP inbound test sending broken JSON and valid JSON with `amountVnd=null`. Document whether the error arises in the converter, validator, or Filter.
7. **Wrong payload type:** send `Message<String>` into a typed flow and observe conversion/type errors. Add converter tests if the application supports DTO binding.
8. **Async:** replace `orders.input` with an executor/queue before the Filter and write a latch test. Prove producer acceptance does not mean the accepted handler finished.
9. **Discard handler failure:** make the rejected handler throw an exception and distinguish it from the Filter predicate returning `false`. Build recovery suited to the execution model.
10. **Downstream timeout:** have the accepted handler call a mock HTTP gateway that times out. Prove the message was still Filter-accepted, yet business processing failed.
11. **Broker poison message:** simulate an unparseable Kafka/JMS record. Design error channel/DLQ and acknowledgment/replay decisions after fixing the producer.
12. **Correlation:** have a Splitter emit three items, Filter reject one, and send two to an Aggregator. Design a release strategy or rejected-item marker so the group does not hang.
13. **Observability:** log `FILTER_EVALUATED` and `FILTER_VALIDATION_FAILED` with business ID/trace ID; log no tokens or sensitive payloads. Build a dashboard counting all three groups by policy version.
14. **Property-based testing:** generate random positive amounts and verify invariants: below threshold always rejected, at or above always accepted; `null`, 0, or negative always malformed.

### Self-Check Questions

**Question 1:** `amountVnd=4,999,999`, currency VND, valid orderId. Which group does the message belong to? **Rejected**, because the data follows the contract yet misses the threshold.

**Question 2:** Is `amountVnd=null` considered a valid rejection? **No** under the example policy. It is malformed and must follow the defined error/validation path.

**Question 3:** Does `discardChannel` mean discarded messages are definitely stored durably? **No.** It only specifies which channel receives rejected messages; durability depends on channel/store/consumer.

**Question 4:** Does `MessageChannel.send(...)` returning `true` prove the Filter sent the message to the accepted channel? **No.** It may have gone to the discard channel, or with async channels merely been enqueued.

**Question 5:** Is unparseable JSON guaranteed to be counted by the Filter as malformed? **No.** Failure can occur before creating the Spring Message; monitor inbound converters/adapters.

**Question 6:** Gateway gets no reply when Filter discards one-way. Is the bug definitely in the predicate? **No.** The request–reply contract may simply lack a response path for rejections.

**Question 7:** An accepted message hits a downstream HTTP timeout. Should the Filter rejected metric increment? **No.** Filter accepted is a separate event; downstream processing failed is a subsequent failure.

**Question 8:** A Filter between Splitter and Aggregator drops a child message. Why can a group timeout occur? **Because** the Aggregator may keep waiting for a part that never arrives; proper release/timeout and correlation policies are needed.

**Question 9:** Why should integration tests assert both accepted and rejected counters? **To** prove not only that the expected handler received the message, but also that **nothing leaked into the opposite branch**.

**Question 10:** Why shouldn't malformed messages be retried infinitely? **Because** fixed schema errors cannot be healed by resending identical payloads; infinite retries can clog queues/consumers.

## 16. Conclusion

**A valuable Filter test suite must properly distinguish three groups: accepted, rejected, and malformed.** In Spring Integration, Filter decides pass or reject based on a predicate; rejections can be discarded, sent to `discardChannel`, or throw exceptions per configuration. Malformed represents an **inability to evaluate validly** and can arise before the Filter in adapters/converters or during validation.

Organize tests in layers: **unit tests for predicates and validation**, **integration tests for channels/consumers**, **adapter tests for parsing/schemas**, and **end-to-end tests** for delivery, error channels, and business outcomes. Always verify both the right path and paths that **must not** receive messages; separate accepted from processed/committed; and intentionally handle Gateway timeouts, retries, idempotency, and correlation.

As a result, flows in `SPRING_INTEGRATION_PATTERN` combining Router, Transformer, Splitter, Aggregator, and Gateway after a Filter become more loosely coupled, retain full traceability of rejection causes, and never disguise a broken message as a routine business rejection.
