# Recipient List Router

## 1. Context: One Event Can Have Multiple Recipients

In the **Message router** chapter of the **SPRING_INTEGRATION_PATTERN** module, we implement Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible, and testable message flows. The Router decides a message's path; Filter, Transformer, Splitter, Aggregator, and Gateway coordinate business processing, while retries, error channels, and correlation help trace and recover branches on failure.

Suppose a system receives an **order.accepted** event:

- **Audit** must record every order.
- **Risk review** inspects only orders with a value of 10 million VND or more.
- **International fulfillment** handles only orders shipped outside Vietnam.

A high-value order shipped abroad must go to **all three** recipients. A small domestic order goes only to audit. A single-branch router cannot satisfy this requirement.

**Recipient List** is a pattern that routes a message to a **set of recipients**. In Spring Integration, **RecipientListRouter** manages a list of destination channels. Each recipient can have a **selector** returning true/false based on message content; the router sends to every matching recipient.

After this lesson, you will be able to:

1. Distinguish Recipient List from a single-branch Router, Message Filter, PublishSubscribeChannel, and Splitter.
2. Define static recipients and conditional recipients based on payload or headers.
3. Configure RecipientListRouter using Java DSL and implement outbound flows.
4. Decide behavior when no recipient matches or when sending to a destination fails.
5. Understand the meaning of `applySequence` with Aggregator, along with limits around ordering, transactions, and durability.
6. Test the exact set of recipients that received a message, error branches, and correlation context.

## 2. How Does Recipient List Work?

Whenever a message arrives, RecipientListRouter evaluates each recipient condition in turn and selects **the matching set of channels**. Registering a recipient without a selector means that recipient is always selected. Selectors are independent; matching one condition does not stop the router from evaluating the remaining conditions.

~~~mermaid
flowchart LR
    P["Order producer"] --> I["orderEventsChannel"]
    I --> R{"RecipientListRouter"}
    R -->|"Always receives"| A["Audit"]
    R -->|"totalVnd >= 10 million"| F["Risk review"]
    R -->|"country != VN"| S["International fulfillment"]
~~~

| Event | Total Amount | Destination Country | Matching Recipients |
| --- | ---: | --- | --- |
| ORD-101 | 800,000 VND | VN | audit |
| ORD-102 | 12,000,000 VND | VN | audit, risk |
| ORD-103 | 15,000,000 VND | SG | audit, risk, international |
| ORD-104 | 500,000 VND | SG | audit, international |

In this table, audit is an unconditional recipient. With a router **consisting solely of conditional recipients**, a case with **no matching recipients** can occur; define an explicit policy for handling that case.

### Comparison with Related Patterns

| Mechanism | Behavior | When to Use |
| --- | --- | --- |
| Single-branch Router (e.g., typical Header Value Router) | Picks a channel based on a single key or expression | One message follows one workflow type |
| **RecipientListRouter** | Sends to every independently selected recipient | One event requires multiple conditional processing branches |
| PublishSubscribeChannel | Broadcasts messages to multiple subscribed consumers on the channel | Broadcast an event to all subscribers |
| Message Filter | Keeps or drops a message per a predicate | One branch needs its own acceptance condition |
| Splitter | Splits one payload into multiple child messages | Process parts of a dataset |
| Aggregator | Combines messages belonging to the same group | Wait for child results to produce one combined result |

**RecipientListRouter** chooses **who receives the same event**; **Splitter** chooses **how to split data**. When sending the same event to multiple recipients, those recipients can process independently. When fan-out must be followed by result reassembly, RecipientListRouter must be paired with an Aggregator and proper correlation.

Do not confuse a recipient with an email address or URL: the recipients declared on the router are **MessageChannel** beans. Sending email, HTTP, or Kafka requires adapters/endpoints behind those channels.

## 3. Designing Independent, Testable Rules

Start with the payload contract:

~~~java
import java.math.BigDecimal;

record OrderAccepted(
        String orderId,
        BigDecimal totalVnd,
        String destinationCountry) {}
~~~

Then extract recipient selection conditions into pure functions:

~~~java
import java.math.BigDecimal;
import java.util.Locale;

final class OrderRoutingRules {
    static final BigDecimal RISK_THRESHOLD =
            new BigDecimal("10000000");

    private OrderRoutingRules() {}

    static boolean requiresRiskReview(OrderAccepted order) {
        return order.totalVnd() != null
                && order.totalVnd().compareTo(RISK_THRESHOLD) >= 0;
    }

    static boolean isInternational(OrderAccepted order) {
        return order.destinationCountry() != null
                && !"VN".equals(order.destinationCountry()
                        .trim().toUpperCase(Locale.ROOT));
    }
}
~~~

Inputs must pass validation before routing: non-empty `orderId`, non-negative amounts, valid country codes. A selector returning false on missing data does not replace validation. In real systems, `BigDecimal` compares money more accurately than `double`; country codes should use normalized codes and an accepted catalog.

**Rules should be independent of infrastructure.** A method like `requiresRiskReview` does not need to know channel names or call a risk service. When rules change, you can unit test that function while keeping the overall topology intact.

If rules rely on headers like `tenantId` or `priority`, explicitly define the header's type, origin, and trust level. Do not use information supplied by external clients to open privileged branches before authentication.

## 4. Java DSL Configuration: Three Recipients, Two Selectors

Spring Integration provides **routeToRecipients** and **RecipientListRouterSpec** in the IntegrationFlow DSL. The example below uses Java 17+; each recipient has a `DirectChannel` to make synchronous branches easy to trace.

### 4.1. Creating Channels and the Router

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class OrderRecipientRoutingConfig {

    @Bean
    MessageChannel orderEventsChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel auditChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel riskReviewChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel internationalFulfillmentChannel() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow routeAcceptedOrders() {
        return IntegrationFlow.from("orderEventsChannel")
                .routeToRecipients(r -> r
                        .recipient("auditChannel")
                        .recipientMessageSelector("riskReviewChannel", message ->
                                OrderRoutingRules.requiresRiskReview(
                                        (OrderAccepted) message.getPayload()))
                        .recipientMessageSelector(
                                "internationalFulfillmentChannel", message ->
                                        OrderRoutingRules.isInternational(
                                                (OrderAccepted) message.getPayload())))
                .get();
    }
}
~~~

**Reading the configuration:**

1. **orderEventsChannel** receives events from the producer.
2. **routeToRecipients** creates a recipient-list router.
3. **recipient("auditChannel")** has no selector and therefore always receives.
4. **recipientMessageSelector** evaluates `Message<?>` for each conditional channel.
5. The same message can be selected for multiple destinations. Each destination needs an actual subscriber/endpoint to receive it.

The list of recipients is defined when configuring the flow; **selector predicates** are evaluated per message at runtime. Having three recipients does not mean every send hits all three.

### 4.2. Attaching Handlers to Branches

Define ports to decouple routing from concrete services:

~~~java
interface AuditPort {
    void record(OrderAccepted order);
}

interface RiskReviewPort {
    void review(OrderAccepted order);
}

interface InternationalFulfillmentPort {
    void dispatch(OrderAccepted order);
}
~~~

The following configuration methods can be placed in `OrderRecipientRoutingConfig` above:

~~~java
@Bean
IntegrationFlow auditFlow(AuditPort auditPort) {
    return IntegrationFlow.from("auditChannel")
            .handle(OrderAccepted.class, (order, headers) -> {
                auditPort.record(order);
                return null;
            })
            .get();
}

@Bean
IntegrationFlow riskReviewFlow(RiskReviewPort port) {
    return IntegrationFlow.from("riskReviewChannel")
            .handle(OrderAccepted.class, (order, headers) -> {
                port.review(order);
                return null;
            })
            .get();
}

@Bean
IntegrationFlow internationalFlow(InternationalFulfillmentPort port) {
    return IntegrationFlow.from("internationalFulfillmentChannel")
            .handle(OrderAccepted.class, (order, headers) -> {
                port.dispatch(order);
                return null;
            })
            .get();
}
~~~

The application must provide beans implementing the three ports. Each flow knows only the port it needs, allowing you to swap the audit adapter or shipping dispatch mechanism without touching routing rules.

### 4.3. Producer Publishing a Message

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

OrderAccepted order = new OrderAccepted(
        "ORD-103", new BigDecimal("15000000"), "SG");

Message<OrderAccepted> event = MessageBuilder.withPayload(order)
        .setHeader("eventType", "order.accepted")
        .setHeader("businessCorrelationId", order.orderId())
        .setHeader("schemaVersion", 1)
        .build();

// orderEventsChannel is injected from the Spring context.
boolean accepted = orderEventsChannel.send(event);
~~~

For `ORD-103`, all three recipients are selected. However, **`send()` returning `true` does not prove all target systems recorded it successfully**. If a branch later uses `ExecutorChannel`, `QueueChannel`, or a broker, processing may finish after `send()` returns.

In a real producer, attach a stable `eventId` to detect duplicates on retry, and propagate trace context from the observability system. Do not put sensitive data into headers that might be logged or forwarded across adapters.

## 5. Static Recipients, SpEL Selectors, and Subflows

### 5.1. SpEL Selectors

Besides Java lambdas, Java DSL supports **Spring Expression Language (SpEL) expressions**:

~~~java
@Bean
IntegrationFlow routeTextEvents() {
    return IntegrationFlow.from("textEventsChannel")
            .routeToRecipients(r -> r
                    .recipient("allTextChannel")
                    .recipient("priorityTextChannel",
                            "headers['priority'] == 'HIGH'")
                    .recipient("paymentTextChannel",
                            "payload.startsWith('PAYMENT:')"))
            .get();
}
~~~

The example assumes `textEventsChannel` and the three destination channels are defined with matching subscribers. A message with `priority` `HIGH` goes to `priorityTextChannel`, and a message whose payload starts with `PAYMENT:` goes to `paymentTextChannel`. If both conditions match, it is **sent to both**, as well as to `allTextChannel`.

| API | Characteristics |
| --- | --- |
| **recipient(name)** | Always selects the recipient |
| **recipient(name, expression)** | Selects only when SpEL returns true |
| **recipientMessageSelector(name, predicate)** | Selects via a function taking `Message<?>`; easy to unit test Java rules |
| **recipientFlow(...)** | Recipient is a subflow declared inline in the DSL |

For critical data, selectors written in pure Java are usually easier to refactor and unit test than long expressions. SpEL can be concise for simple header-based rules; verify field existence and types to avoid runtime errors.

### 5.2. Using Subflows When Each Destination Needs Extra Processing Steps

Instead of cramming all logic into one handler, a recipient can be a subflow consisting of a Transformer followed by a Service Activator. In the DSL you can use **recipientFlow** with a selector expression; when declared this way, the router itself manages the subflow's entry point.

~~~java
@Bean
IntegrationFlow routeWithRecipientFlow() {
    return IntegrationFlow.from("routingInputChannel")
            .routeToRecipients(r -> r
                    .recipient("auditChannel")
                    .recipientFlow(
                            "headers['eventType'] == 'order.accepted'",
                            flow -> flow
                                    .transform(String.class, String::trim)
                                    .channel("normalizedOrdersChannel")))
            .get();
}
~~~

This snippet assumes the payload is `String` and the channels exist; typed business events like `OrderAccepted` should use corresponding Transformers. The key point is that **a recipient can carry its own processing pipeline**. Each branch needs an explicit contract to avoid mixing incompatible payload types.

## 6. When No Recipient Matches

A recipient list composed entirely of selectors may pick zero destinations. For example, a message is neither `payment.completed` nor `HIGH` severity.

By default configuration, the router **does not silently drop** a message when no valid destination is found, and throws an exception instead. When unmatched cases are valid in the business domain, configure a **default output channel**:

~~~java
@Bean
IntegrationFlow routeWithFallback() {
    return IntegrationFlow.from("eventInputChannel")
            .routeToRecipients(r -> r
                    .recipient("paymentEventsChannel",
                            "headers['eventType'] == 'payment.completed'")
                    .recipient("criticalEventsChannel",
                            "headers['severity'] == 'HIGH'")
                    .defaultOutputChannel("unmatchedEventsChannel"))
            .get();
}
~~~

To run the example, create channel beans and handlers for `eventInputChannel`, `paymentEventsChannel`, `criticalEventsChannel`, and `unmatchedEventsChannel`. A message matching two selectors goes to both recipients; a message matching none goes to `unmatchedEventsChannel`.

**Not matching any selector** differs from **failing to send to a selected recipient**:

- **Unmatched:** no recipient is selected. Default output channel handles this case.
- **Unresolved channel:** a recipient name is selected, but the channel bean does not exist. By default this is a destination resolution error.
- **Send failure:** the channel exists but rejects the send, is overloaded, or a downstream handler throws an exception.
- **Async handling failure:** the channel accepts the task, but the handler running later fails.

A default output channel does not mean downstream failures automatically route to fallback. Verify each scenario with tests and appropriate logging. If the business intentionally discards unmatched messages, you can use **nullChannel** as the default route, but record metrics before discarding.

## 7. Important Router Options

| Option | Meaning | Behavior to Remember |
| --- | --- | --- |
| **applySequence** | Creates correlation/sequence metadata for dispatched copies | Default false; enable when reassembly is needed |
| **ignoreSendFailures** | Whether to ignore send failures and continue to remaining recipients | Default false; enabling true risks masking errors |
| **sendTimeout** | Wait time when sending to a channel | Not the timeout for all downstream work |
| **defaultOutputChannel** | Destination when no recipient is selected | Helps handle unmatched messages |
| **resolutionRequired** | Requires resolving selected channel names | Default true; invalid names should be caught |

### 7.1. ignoreSendFailures and Single-Branch Failure

Suppose the router sends to audit, notification, and analytics, and the **synchronous audit handler** throws an exception. With **ignoreSendFailures=false** (default), the error can propagate out and the remaining recipients **are not invoked**. With **ignoreSendFailures=true**, the router can ignore a send failure on one recipient and keep sending to subsequent recipients.

~~~java
@Bean
IntegrationFlow bestEffortNotifications() {
    return IntegrationFlow.from("notifyInputChannel")
            .routeToRecipients(r -> r
                    .recipient("emailChannel")
                    .recipient("smsChannel")
                    .recipient("analyticsChannel")
                    .ignoreSendFailures(true))
            .get();
}
~~~

This example is suitable only if the branches are acceptable as **best effort**, monitored separately, and one failure does not need to halt the entire flow. Do not enable ignoring failures for mandatory audit, payment, or persistence paths without independent recovery mechanisms.

With asynchronous channels, a successful send **does not prove the downstream handler succeeded**. Thus `ignoreSendFailures` does not replace error channels, retries, or per-branch completion confirmation.

### 7.2. sendTimeout: Bounding the Send Operation

~~~java
// Inside routeToRecipients configuration:
.recipient("billingChannel")
.recipient("auditChannel")
.sendTimeout(2_000L)
~~~

Send timeout bounds how long the router waits when sending to a channel that can block or become full. It **does not automatically bound** the duration of a REST call, DB transaction, or long-running synchronous handler. When an end-to-end request deadline is needed, design timeouts at each appropriate layer.

### 7.3. resolutionRequired: Catching Misspelled Channel Names

If a selector picks a nonexistent channel name, the default configuration requires resolution to succeed and throws an error. Only consider ignoring unresolved channels when a deliberate fallback policy exists; in production systems, misspelled channel names should usually **fail fast** so configuration errors are caught early.

## 8. applySequence and Combining Results from Multiple Branches

When Recipient List sends events to independent audit, notification, and analytics flows, you usually **do not need sequencing**. However, in scatter-gather scenarios—such as concurrently querying **pricing**, **tax**, and **shipping** services—results from the branches must be gathered by an **Aggregator** before returning to the caller.

~~~mermaid
flowchart LR
    P["Quote request"] --> R["RecipientListRouter<br/>applySequence=true"]
    R --> A["Price calculation"]
    R --> B["Tax calculation"]
    R --> C["Shipping calculation"]
    A --> G["Aggregator"]
    B --> G
    C --> G
    G --> O["Combined quote"]
~~~

~~~java
@Bean
IntegrationFlow quoteRoutingFlow() {
    return IntegrationFlow.from("quoteRequestsChannel")
            .routeToRecipients(r -> r
                    .applySequence(true)
                    .recipient("priceCalculationChannel")
                    .recipient("taxCalculationChannel")
                    .recipient("shippingCalculationChannel"))
            .get();
}
~~~

This routing configuration is only **part** of a scatter-gather example. You must create the three consumers, each sending a **reply** to the Aggregator's channel, and configure an appropriate release strategy, message store, and timeout.

When **applySequence(true)** is enabled, the router generates metadata helping the system group emitted messages:

| Header | Purpose |
| --- | --- |
| **correlationId** | Links messages belonging to the same distribution batch |
| **sequenceNumber** | Index of the child message within the set |
| **sequenceSize** | Expected size of the message set |

Spring Integration does **not** enable `applySequence` by default on RecipientListRouter. Enable it only when downstream genuinely needs correlation/sequence, such as an Aggregator. Enabling sequencing does not make branches run sequentially in time, nor does it guarantee which branch finishes first.

### Aggregator Completion Conditions

If all three recipients must emit a reply, the Aggregator needs all three results before releasing. If one branch fails or never replies, the message group can linger; therefore define timeouts, incomplete-group handling, and state persistence when needed.

If recipients use **selectors**, the number of matched recipients can vary per message. The Aggregator design must match **the actual set of selected recipients**, rather than hardcoding that every message goes to three branches.

### Business Correlation Differs from Single Fan-Out Correlation

One order may emit multiple events: **order.accepted**, **order.paid**, and **order.shipped**. The **`orderId`** field is a business key spanning multiple flows, whereas correlation/sequence for branch aggregation may apply only within **a single** Recipient List dispatch.

If both must be preserved, store the business key separately in the payload or in a header like **businessCorrelationId**. Do not rely on `MessageHeaders.ID` as a long-lived business key; each derived message can have its own ID.

## 9. Ordering, Synchronicity, Transactions, and Side Effects

**RecipientListRouter does not automatically run branches in parallel.** Actual dispatch semantics depend on the destination channels.

| Destination Channel | Typical Behavior | Impact on Recipients |
| --- | --- | --- |
| **DirectChannel** | Handler runs synchronously on sender thread | A slow or failing handler impacts the sender and subsequent sends |
| **ExecutorChannel** | Dispatch is scheduled via an Executor | Handler may run after send; errors need async handling |
| **QueueChannel** | Message waits for consumer/poller | Successful send differs from completed processing |
| **PublishSubscribeChannel** | Fans out further to multiple subscribers | Must consider failures, latency, and ordering of nested fan-out |

### 9.1. Sending to Multiple Destinations Does Not Mean an Atomic Transaction

Consider this sequence:

1. Audit writes a record to database A.
2. Notification sends an email.
3. Analytics fails while writing to database B.

Even when all channels are synchronous, the router does not automatically roll back the sent email or results in a non-transactional external system. Spring transactions cover only resources actually enlisted in that transaction.

If the business requires **reliable processing across all targets**, you may need:

- **Transactional outbox** to guarantee events are recorded in the same transaction as the primary data update.
- **Broker/persistent storage** if messages must survive restarts.
- **Retry/backoff**, dead-letter queues, or error channels per branch.
- **Idempotency keys** and deduplication so duplicate side effects are prevented.
- **Monitoring** per recipient and alerts if backlogs grow too old.

RecipientListRouter solves **selecting and delivering to destinations**; it does not promise end-to-end exactly-once delivery.

### 9.2. Retrying the Entire Router Can Repeat Already-Succeeded Branches

Suppose audit succeeded, risk review failed, and the caller retries the whole message. Audit may receive the message a second time.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant R as RecipientListRouter
    participant A as Audit
    participant F as Risk
    P->>R: event E attempt 1
    R->>A: E
    A-->>R: Success
    R->>F: E
    F--xR: Exception
    R--xP: Error
    P->>R: Retry E
    R->>A: E once more
    Note over A: Needs idempotent consumer
~~~

Generate a **stable `eventId`** per event and record processed events at each consumer via a unique constraint or idempotency store. Whenever possible, retry **only the failed branch** rather than replaying the whole flow after other branches succeeded.

### 9.3. Sharing Mutable Payloads Introduces Risk

Messages sent to multiple recipients can share the same payload reference, especially when sequence headers are not generated. If one handler mutates a mutable object, other branches may observe altered data or hit race conditions under asynchronous execution.

Prefer **records and immutable types**, or defensively copy mutable objects. `MessageHeaders` prevents modifying the header map structure, yet does not make mutable objects stored inside it immutable.

## 10. Error Channels and Error Paths

Distinguish three points where failures arise:

1. **Selector evaluation**: a selector accesses the wrong payload type or invalid SpEL.
2. **Dispatch**: a channel name fails resolution, a channel is overloaded, or no handler exists.
3. **Processing**: a downstream handler throws an exception, sometimes after the router has already returned.

With synchronous `DirectChannel` branches, exceptions can propagate straight up the call stack and prevent remaining recipients from being sent to. With `ExecutorChannel` or `QueueChannel`, failures may surface later; whether an **`ErrorMessage`** is created and sent to **`errorChannel`** depends on endpoints, adapters, pollers, executors, and error-handler configuration.

**Do not assume `ignoreSendFailures(true)` is a complete error-handling mechanism.** It only affects how the router handles certain send failures. It does not ensure all branches run, does not retry automatically, and does not capture business failures occurring later in worker threads.

### Policy Selection Table

| Requirement | Configuration / Approach to Consider |
| --- | --- |
| Audit must succeed before replying | Synchronous or durable commit; never ignore critical failures |
| Notifications may be best effort | Can continue to remaining recipients; add separate metrics and error flow |
| Notifications must be resent after a crash | Broker/outbox or durable message store, retries/acks |
| Async processing needed without data loss | Durable messaging boundary, idempotent consumers |
| Router selects zero recipients | Default output channel, fail fast, or intentional discard |

## 11. Improving Observability and Managing Recipients

One event can reach multiple branches, so logging only **event entered router** is insufficient. The system should track:

| Data | Helps Answer |
| --- | --- |
| **eventId / businessCorrelationId** | Which event is this? Is it retried or duplicated? |
| **traceId / spanId** | Where did each branch of a dispatch run, and how long did it take? |
| **recipientName** | Which recipients were selected and received it? |
| **sendFailures / downstreamFailures** | Did the error occur during dispatch or processing? |
| **retryCount** | Is a branch retrying excessively? |
| **queueDepth / age** | Is an async recipient backing up? |
| **unmatchedCount** | Are any events matching zero selectors? |

When logging, keep only diagnostic information; avoid logging full payloads or headers containing tokens, personal data, or sensitive fields.

### Can Recipients Be Changed at Runtime?

Spring Integration supports managing `RecipientListRouter`—such as adding or removing recipients via management APIs / Control Bus / JMX when configured. However, altering topology in a live system requires access control, configuration versioning, and observability. In stable systems, treat recipient changes as tested changes following a proper deployment workflow.

## 12. Testing the Exact Set of Recipients

Unit testing selectors only checks **conditions**. Integration testing verifies **the router wires to the right channels** and recipients receive the right messages.

### 12.1. Unit Testing the Rules

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class OrderRoutingRulesTest {

    @Test
    void identifiesHighValueAndInternational() {
        OrderAccepted domestic = new OrderAccepted(
                "ORD-101", new BigDecimal("800000"), "VN");
        OrderAccepted high = new OrderAccepted(
                "ORD-102", new BigDecimal("12000000"), "VN");
        OrderAccepted abroad = new OrderAccepted(
                "ORD-103", new BigDecimal("15000000"), "SG");

        assertFalse(OrderRoutingRules.requiresRiskReview(domestic));
        assertFalse(OrderRoutingRules.isInternational(domestic));
        assertTrue(OrderRoutingRules.requiresRiskReview(high));
        assertFalse(OrderRoutingRules.isInternational(high));
        assertTrue(OrderRoutingRules.requiresRiskReview(abroad));
        assertTrue(OrderRoutingRules.isInternational(abroad));
    }
}
~~~

### 12.2. Integration Testing Conditional Routing

The test below creates a minimal Spring context, three destination `DirectChannel` beans, and a Recipient List, then registers subscribers to record which recipients were called. It needs neither a database nor REST.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.SubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(RecipientListRoutingTest.TestConfig.class)
class RecipientListRoutingTest {

    @Configuration
    @EnableIntegration
    static class TestConfig {
        @Bean
        MessageChannel eventInput() {
            return new DirectChannel();
        }

        @Bean
        MessageChannel auditOutput() {
            return new DirectChannel();
        }

        @Bean
        MessageChannel riskOutput() {
            return new DirectChannel();
        }

        @Bean
        MessageChannel crossBorderOutput() {
            return new DirectChannel();
        }

        @Bean
        IntegrationFlow recipientFlow() {
            return IntegrationFlow.from("eventInput")
                    .routeToRecipients(r -> r
                            .recipient("auditOutput")
                            .recipientMessageSelector("riskOutput", m ->
                                    OrderRoutingRules.requiresRiskReview(
                                            (OrderAccepted) m.getPayload()))
                            .recipientMessageSelector("crossBorderOutput", m ->
                                    OrderRoutingRules.isInternational(
                                            (OrderAccepted) m.getPayload())))
                    .get();
        }
    }

    @Autowired
    @Qualifier("eventInput")
    MessageChannel input;

    @Autowired
    @Qualifier("auditOutput")
    SubscribableChannel audit;

    @Autowired
    @Qualifier("riskOutput")
    SubscribableChannel risk;

    @Autowired
    @Qualifier("crossBorderOutput")
    SubscribableChannel crossBorder;

    @Test
    void dispatchesOneMessageToAllMatchingRecipients() {
        List<String> receivedBy = new ArrayList<>();
        audit.subscribe(m -> receivedBy.add("audit"));
        risk.subscribe(m -> receivedBy.add("risk"));
        crossBorder.subscribe(m -> receivedBy.add("crossBorder"));

        OrderAccepted event = new OrderAccepted(
                "ORD-103", new BigDecimal("15000000"), "SG");

        assertTrue(input.send(
                MessageBuilder.withPayload(event).build()));
        assertEquals(3, receivedBy.size());
        assertTrue(receivedBy.containsAll(
                List.of("audit", "risk", "crossBorder")));
    }
}
~~~

With synchronous `DirectChannel`, the test can verify the recipient set right after `send()`. When replacing with `ExecutorChannel`, use test synchronization such as `CountDownLatch` with an appropriate timeout. When multiple tests share the same Spring context, clean up temporary subscribers to avoid cross-test interference.

### 12.3. Recommended Test Matrix

| Input | Expected Result |
| --- | --- |
| Domestic order, low value | Audit only |
| Domestic order, high value | Audit and risk |
| International order, low value | Audit and international |
| International order, high value | All three |
| Zero recipients matched, no unconditional audit | Fallback or exception |
| Misspelled channel name | Resolution error observed |
| Synchronous handler throws exception | `ignoreSendFailures` policy applied |
| Async handler throws exception | Dedicated error flow/metrics triggered |
| Retry after one branch already succeeded | Consumer produces no duplicate business side effects |
| With `applySequence` and Aggregator | Group, `sequenceSize`, timeout, and release behave properly |

## 13. Common Design Mistakes

| Mistake | Consequence | How to Avoid |
| --- | --- | --- |
| Using a single-branch router when an event needs multiple recipients | One or more tasks missed | Use RecipientListRouter |
| Assuming recipients are evaluated as mutually exclusive | Misses fan-out to all matching selectors | Build a condition combination matrix |
| Confusing recipient with URL/email | Router lacks valid channels | Create MessageChannels and adapters |
| Forgetting fallback when no recipient matches | Unexpected routing failure | Explicit default channel or intentional fail fast |
| Enabling `ignoreSendFailures` for mandatory audit | Masks failures on critical data | Durable mechanism and proper error reporting |
| Assuming fan-out means parallel execution | `DirectChannel` branches remain synchronous | Choose explicit async boundaries |
| Sharing a mutable payload | Race conditions, cross-branch interference | Immutable models or defensive copies |
| Retrying whole router without idempotency | Duplicate audit/notifications | Stable `eventId`, per-branch retry |
| Setting `applySequence` without an Aggregator | Purposeless metadata, misunderstood correlation | Enable only when reassembly is truly needed |
| Testing only selectors, not channel wiring | Wrong recipient names, missing handlers | Write integration tests with a real context |

## 14. Practice Exercise: Dispatching Payment Events

Design a flow receiving **PaymentCompleted(paymentId, amountVnd, riskScore, notifyCustomer)** with these requirements:

1. **Audit** receives every completed payment event.
2. **Fraud inspection** receives when `riskScore` is 80 or above **or** `amountVnd` is 20,000,000 or above.
3. **Notification** receives when `notifyCustomer=true`.
4. **Analytics** receives every event but can process asynchronously.
5. Every branch preserves `eventId` and a `businessCorrelationId` for tracing.

Steps:

- Write the `PaymentCompleted` record and pure Java selectors.
- Use `routeToRecipients` to declare two unconditional recipients and two conditional recipients.
- Create a separate `IntegrationFlow` for each recipient; analytics can use an `ExecutorChannel` with a bounded executor.
- Test the four main combinations of the two conditions plus a message where both conditions hold.
- Simulate one `DirectChannel` branch failing; compare fail-fast vs. `ignoreSendFailures(true)`.
- Propose upgrades when audit persistence must survive restarts: transactional outbox, durable broker/message store, retries, deduplication, and monitoring.

### Advanced: Aggregating Two Results

Suppose from `PaymentCompleted` you need to compute **fee** and **tax**, then combine both results. Use a recipient list with `applySequence=true`, two recipients sending replies into an Aggregator, and configure a release strategy and timeout. Answer for yourself:

- If a selector skips the tax branch, what `sequenceSize` makes sense?
- If the fee branch finishes but the tax branch never replies, how long is the group retained?
- If retrying the whole message causes one branch to return a result twice, how does the Aggregator detect it?

### Self-Check Questions

1. How does Recipient List differ from a header-based Router that chooses one branch?
2. How many recipients receive a message matching three selectors?
3. How does Recipient List differ from Splitter?
4. What case does `defaultOutputChannel` handle; does it rescue every downstream error?
5. Why does `ignoreSendFailures(true)` not replace an error channel?
6. When is `applySequence=true` needed, and what must be configured on the Aggregator?
7. Why do three `DirectChannel` beans not create an atomic fan-out across three external systems?
8. When an event is retried, what prevents audit from recording duplicates?

## 15. Recipient List Design Checklist

- Identify **mandatory** recipients and **conditional** recipients.
- Normalize payload/headers before evaluating selectors.
- Extract business rules into unit-testable functions.
- Ensure every recipient channel exists and has a matching endpoint.
- Explicitly define fallback for messages matching no recipient.
- Define per-branch error policies, especially around `ignoreSendFailures`.
- Enable `applySequence` only when downstream needs grouping/correlation.
- Evaluate ordering, threading, transactions, durability, and backpressure per channel.
- Include `eventId` and idempotency if retries can emit duplicate events.
- Test the full recipient set, error cases, and per-branch observability.

**Conclusion:** `RecipientListRouter` answers the question **"which recipients should receive this message?"**. It does not itself guarantee branch success, atomicity, or durability. By cleanly separating **recipient selection rules** from **each branch's processing and recovery contract**, we build Spring Integration flows that are flexible, extensible, and verifiable.

## References

- [Spring Integration Reference — Router Implementations](https://docs.spring.io/spring-integration/reference/router/implementations.html): RecipientListRouter, recipient lists, and selectors.
- [Spring Integration Reference — Java DSL Routers](https://docs.spring.io/spring-integration/reference/dsl/java-routers.html): `routeToRecipients`, `recipientMessageSelector`, and `recipientFlow`.
- [Spring Integration Reference — Common Router Parameters](https://docs.spring.io/spring-integration/reference/router/common-parameters.html): `applySequence`, `defaultOutputChannel`, `resolutionRequired`, `sendTimeout`, `ignoreSendFailures`.
- [Spring Integration Reference — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html): correlation, sequencing, and release conditions when combining results.
