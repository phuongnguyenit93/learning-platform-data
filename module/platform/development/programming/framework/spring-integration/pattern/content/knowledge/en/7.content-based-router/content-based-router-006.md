# Default Route and Dead-End Route

## 1. Why does a Content-Based Router need a default route?

In the **Content-based router** chapter of the **SPRING_INTEGRATION_PATTERN** module, we implement Enterprise Integration Patterns with Spring Integration to create loosely coupled, extensible, testable, and observable messaging flows. The Router routes messages by content, while Filter, Transformer, Splitter, Aggregator, and Gateway handle related steps; retry, error channels, and correlation help track branches and handle errors.

A Content-Based Router makes one decision: **which channel should this message go to?** When an unknown data type arrives, a mapping is missing, or configuration is wrong, a message may fail to find a path.

For example, an API receives events:

- **payment.completed** → update the order as paid;
- **payment.failed** → send to failed payment handling flow;
- **payment.refunded** → process refund;
- a new event value **payment.chargeback** → has no handler in the current deployed version.

If the router defines no behavior for **payment.chargeback**, the event may cause an exception or be misprocessed. Having an explicit **default route** lets the system recognize unsupported cases. However, a default route can also be abused, masking mapping bugs.

**Lesson objectives**

1. Distinguish default routes from dead-end routes and intentional message discarding paths.
2. Understand when Spring Integration routes a message to the default output channel vs. throwing an error.
3. Design options: fail fast, quarantine/unmatched channel, or nullChannel when dropping is valid.
4. Configure Content-Based Router with channel mapping, defaultOutputChannel, resolutionRequired, and channelKeyFallback.
5. Distinguish **no route found** errors from **arrived at channel but unhandled** errors.
6. Test routing, error handling, correlation, and observe stuck or dropped messages.

## 2. Three situations often grouped together as dead-end

The term **dead-end route** is commonly used in system design: a message has reached a point with **no remaining useful processing path**. It is **not** the name of a special router class in Spring Integration. At least three cases must be distinguished:

| Case | Example | Consequence |
| --- | --- | --- |
| **No route found** | Routing key has no channel mapping and no fallback | Router throws a routing error under default configuration |
| **Routed, but no handler consumes it** | Message enters a DirectChannel with no subscriber, or a QueueChannel with no poller | Send may fail, or messages accumulate in a backlog |
| **Sent to an intentional dead end** | Router sends an unneeded event type to nullChannel | Message is discarded by design |

These cases need different policies and monitoring. Increasing retry counts when a message lacks a valid route will not magically create a new handler. Conversely, a QueueChannel with queued messages while its consumer is temporarily down is an operational incident requiring consumer recovery.

~~~mermaid
flowchart TD
    A["Incoming Message"] --> R{"Content-Based Router"}
    R -->|"Mapped key"| C["Valid destination"]
    R -->|"Unmapped key"| D{"Has default route?"}
    D -->|"Yes"| U["Unmatched channel"]
    D -->|"No"| E["Routing exception"]
    C --> H{"Has consumer and processable?"}
    H -->|"Yes"| S["Processed"]
    H -->|"No"| X["Delivery error or backlog"]
    U --> Q["Inspect / quarantine / policy"]
~~~

The diagram shows **conceptual decisions**. In practice, keys may be interpreted as channel names and routers have resolution options; the next sections explain those details.

### 2.1. Default route

A **default route** is a fallback processing path when the router cannot determine a valid destination channel from the data or mapping configuration. Spring Integration supports **defaultOutputChannel** to specify this destination.

A default route can be used to:

- Route unsupported events to **unmatchedEventsChannel** for classification and investigation.
- Route data not permitted to proceed into a **quarantine** inspection branch, combined with persistence or alerting as needed.
- Forward **safely ignorable** events to **nullChannel**.

Configuring a default route does not mean business processing succeeded. It only decides **where a message goes when no primary destination is found**.

### 2.2. Dead-end from routing failure

An unmapped key should usually be treated as an **unsupported event** or **configuration error**. Without a default output channel and when no destination can be resolved, the router throws an exception by default.

This is often helpful: if an event producer bumped schemaVersion or renamed eventType before the consumer upgraded, failing fast catches contract drift instead of silently ignoring it.

### 2.3. Dead-end after routing

Suppose the router picks **invoiceCommandsChannel**, yet no endpoint is subscribed to receive messages. With DirectChannel, send() may fail to complete normally due to having no subscriber. With QueueChannel, send() may succeed while the message sits in the queue because no poller exists.

**The router's default output channel does not rescue these two cases.** It handles the **destination selection** stage, and does not replace retry, DLQ, error channel, or monitoring on the receiving channel.

## 3. Distinguishing fallback, discard, and dead-letter

The following paths serve distinct purposes:

| Path | Meaning | Must clarify |
| --- | --- | --- |
| **Default output channel** | Receiver when routing cannot determine a primary channel | Who inspects or continues processing? |
| **nullChannel** | Receiver that drops messages | Which types may be dropped? Are metrics needed? |
| **Quarantine / unmatched channel** | Stores or separately handles unrouted data | Where stored, retention period, who reviews? |
| **errorChannel** | Receives ErrorMessages per endpoint/adapter error handling | Which errors are routed here? |
| **Dead-letter queue (DLQ)** | Holds messages that failed processing after retry/redelivery policy | Root cause, attempt count, recovery procedure |

Simply naming a MessageChannel **deadLetterChannel** does not automatically provide durable storage, retry limits, or dead-letter semantics. To guarantee message recovery after restarts, use a durable MessageStore, broker, or appropriate persistence mechanism.

**Principle:** unrouted messages are **unmatched**, messages failing during processing are **failed**, and messages designed to be ignored are **discarded**. Tracking these three groups separately prevents miscounting system health.

## 4. Channel mapping mechanism of Content-Based Router

A Content-Based Router typically derives a **routing key** from the payload or headers, then maps the key to a **MessageChannel name**. Spring Integration offers several ways:

- **HeaderValueRouter**: takes the key from a header.
- **PayloadTypeRouter**: takes the key from the payload type.
- **SpEL-based router**: computes the key via expression.
- **Custom/POJO router**: runs a Java method to decide key or destination.
- **IntegrationFlow DSL**: declares a key selector function and **channelMapping** entries.

Payment domain example:

| Routing key | Channel | Meaning |
| --- | --- | --- |
| COMPLETED | completedPaymentsChannel | Handle successful payment |
| FAILED | failedPaymentsChannel | Handle failed payment |
| REFUNDED | refundedPaymentsChannel | Handle refund |
| CHARGEBACK | Unmapped | Event not yet supported in current version |

### 4.1. Mapping key differs from channel name

The key **COMPLETED** is just a **business label**. The actual channel is declared as **completedPaymentsChannel**. Keeping these two concepts separate lets you:

- Keep routing rules independent of technical bean names.
- Rename channels without forcing producers to change eventType.
- Restrict allowed destinations using an **allowlist mapping**.

Never allow external clients to send raw channel bean names and let the router resolve them arbitrarily: that risks routing into unintended channels or even creating loops. Validate values, map explicitly to permitted destinations, and avoid letting untrusted input steer topology.

## 5. Java DSL example: default route to unmatched channel

This example uses Java 17+ with Spring Integration Java DSL. We build a **pure routing function** and three permitted processing branches, while new events go to **unmatchedPaymentsChannel**.

### 5.1. Model and route decision

~~~java
import java.math.BigDecimal;
import java.util.Locale;

record PaymentEvent(
        String eventId,
        String paymentId,
        String eventType,
        BigDecimal amountVnd) {}

final class PaymentRoutingRules {
    private PaymentRoutingRules() {}

    static String routeKey(PaymentEvent event) {
        if (event == null || event.eventType() == null) {
            return "UNKNOWN";
        }

        return switch (event.eventType().trim()
                .toUpperCase(Locale.ROOT)) {
            case "PAYMENT.COMPLETED" -> "COMPLETED";
            case "PAYMENT.FAILED" -> "FAILED";
            case "PAYMENT.REFUNDED" -> "REFUNDED";
            default -> "UNKNOWN";
        };
    }
}
~~~

The **routeKey** function only classifies the event type; it calls no database, sends no messages, and knows no channel beans. For inputs missing eventType, it returns **UNKNOWN** so the router can handle it via the unmatched path. This is an illustrative policy; if the system must reject messages missing required fields, validate at the boundary before the router and emit an appropriate error.

### 5.2. Defining channels and flows

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class PaymentRouterConfig {

    @Bean
    MessageChannel paymentInputChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel completedPaymentsChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel failedPaymentsChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel refundedPaymentsChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel unmatchedPaymentsChannel() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow paymentRouterFlow() {
        return IntegrationFlow.from("paymentInputChannel")
                .<PaymentEvent, String>route(
                        PaymentRoutingRules::routeKey,
                        mapping -> mapping
                                .channelMapping(
                                        "COMPLETED", "completedPaymentsChannel")
                                .channelMapping(
                                        "FAILED", "failedPaymentsChannel")
                                .channelMapping(
                                        "REFUNDED", "refundedPaymentsChannel")
                                .defaultOutputChannel(
                                        "unmatchedPaymentsChannel"))
                .get();
    }
}
~~~

In Spring Integration **6.0 and later**, configuring a default output channel on a mapping router automatically disables **channelKeyFallback** by default. Thus the **UNKNOWN** key is not tried as a channel bean name; it goes to **unmatchedPaymentsChannel**. On older versions or custom setups, explicitly verify **channelKeyFallback** and **resolutionRequired** as detailed in section 7.

The Router only wires paths. For messages to be processed, register an **endpoint/subscriber** for each channel. Example:

~~~java
interface PaymentEventService {
    void onCompleted(PaymentEvent event);
    void onFailed(PaymentEvent event);
    void onRefunded(PaymentEvent event);
}

interface UnmatchedPaymentService {
    void quarantine(PaymentEvent event);
}
~~~

The IntegrationFlow beans handling each branch can live in the same PaymentRouterConfig class:

~~~java
@Bean
IntegrationFlow completedFlow(PaymentEventService service) {
    return IntegrationFlow.from("completedPaymentsChannel")
            .handle(PaymentEvent.class, (event, headers) -> {
                service.onCompleted(event);
                return null;
            })
            .get();
}

@Bean
IntegrationFlow failedFlow(PaymentEventService service) {
    return IntegrationFlow.from("failedPaymentsChannel")
            .handle(PaymentEvent.class, (event, headers) -> {
                service.onFailed(event);
                return null;
            })
            .get();
}

@Bean
IntegrationFlow refundedFlow(PaymentEventService service) {
    return IntegrationFlow.from("refundedPaymentsChannel")
            .handle(PaymentEvent.class, (event, headers) -> {
                service.onRefunded(event);
                return null;
            })
            .get();
}

@Bean
IntegrationFlow unmatchedFlow(UnmatchedPaymentService service) {
    return IntegrationFlow.from("unmatchedPaymentsChannel")
            .handle(PaymentEvent.class, (event, headers) -> {
                service.quarantine(event);
                return null;
            })
            .get();
}
~~~

**UnmatchedPaymentService** can persist the message and minimal metadata for investigation, trigger alerts if unmatched events spike, or return an explicit error if the event came from a synchronous Gateway. If restart recovery is needed, merely logging or holding messages in RAM will **not suffice**.

### 5.3. Sending a message

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

// paymentInputChannel is a bean injected from the Spring context.
PaymentEvent event = new PaymentEvent(
        "evt-710", "pay-710",
        "payment.chargeback",
        new BigDecimal("1500000"));

Message<PaymentEvent> message = MessageBuilder.withPayload(event)
        .setHeader("businessCorrelationId", event.paymentId())
        .setHeader("schemaVersion", 1)
        .build();

boolean accepted = paymentInputChannel.send(message);
~~~

The payment.chargeback event takes the **unmatched** branch due to key **UNKNOWN**. **accepted == true** only proves that sending into the flow succeeded per channel semantics; it does not by itself guarantee quarantine was durably persisted if the branch turns async or external storage fails.

### 5.4. Expected behavior

| eventType | routeKey | Destination |
| --- | --- | --- |
| payment.completed | COMPLETED | completedPaymentsChannel |
| payment.failed | FAILED | failedPaymentsChannel |
| payment.refunded | REFUNDED | refundedPaymentsChannel |
| payment.chargeback | UNKNOWN | unmatchedPaymentsChannel |
| empty/null | UNKNOWN | unmatchedPaymentsChannel or pre-router validation |

Important design point: **unmatched does not mean invalid**. A new eventType may be completely valid from the producer yet unsupported by the consumer. The quarantine flow should record enough context to add mappings or replay the message after upgrading the consumer.

## 6. No default route configured: fail fast

Some cases should not have a silent fallback. For instance, a payment system only accepts three statuses agreed upon in an internal contract; any other key indicates a broken producer or incompatible version.

~~~java
@Bean
IntegrationFlow strictPaymentRouterFlow() {
    return IntegrationFlow.from("strictPaymentInputChannel")
            .<PaymentEvent, String>route(
                    PaymentRoutingRules::routeKey,
                    mapping -> mapping
                            .channelMapping("COMPLETED",
                                    "completedPaymentsChannel")
                            .channelMapping("FAILED",
                                    "failedPaymentsChannel")
                            .channelMapping("REFUNDED",
                                    "refundedPaymentsChannel")
                            .channelKeyFallback(false))
            .get();
}
~~~

This example requires declaring strictPaymentInputChannel and the three destination channels. **channelKeyFallback(false)** prevents the router from attempting to find a bean named after an unmapped routing key. When **UNKNOWN** maps to no channel and no default exists, the router throws **MessagingException/MessageDeliveryException** depending on endpoint and version, rather than dropping the message.

**Fail fast fits when:**

- The eventType contract is closed and changes must deploy synchronously;
- Dropping a message could cause financial loss or missing audit data;
- No safe manual handling mechanism exists for unknown event types;
- Configuration errors should fail builds/deployments or runtime handling loudly.

With synchronous **DirectChannel**, exceptions from the router can typically propagate back to the caller of send(). With inbound adapters/ExecutorChannel/pollers, errors may follow that component's error channel mechanism; never assume the original HTTP caller always receives the same exception.

## 7. resolutionRequired and channelKeyFallback: two distinct decisions

This is the most confusing part of configuring default routes. Both relate to **resolving a MessageChannel from a routing key**, yet they act at two different steps.

### 7.1. channelKeyFallback: try the key as a channel name?

Suppose routeKey returns **SPECIAL** and **no channelMapping("SPECIAL", "...") exists**.

- When **channelKeyFallback=true**, the router may try looking up a channel bean named **SPECIAL** directly.
- When **channelKeyFallback=false**, the router does not infer a channel from the string **SPECIAL**; the result uses the default output channel or fails according to contract.

In Spring Integration, mapping routers historically defaulted to **channelKeyFallback=true**. **Starting in version 6.0, setting a default output channel automatically sets channelKeyFallback=false**, unless the application explicitly overrides it. This makes the fallback behave like the **default** branch of a Java switch and avoids accidentally routing to beans matching key names.

For systems receiving external eventTypes, prefer **allowlist mapping**; never rely on resolving unvalidated keys as channel names for access control.

### 7.2. resolutionRequired: must the channel resolve?

Suppose key **COMPLETED** maps to **completedPaymentsChannel**, yet that channel does not exist in the ApplicationContext:

- **resolutionRequired=true** (default): the router throws an error when it cannot resolve the destination.
- **resolutionRequired=false**: the router may skip unresolvable destinations; if a default output channel is set, the message may go there per router rules.

Because this is usually a **deployment bug** rather than a new eventType, disabling resolutionRequired can mask misspelled channel names. Only allow fallback when it is **explicitly intended** that an optional channel may be absent.

### 7.3. Decision matrix

| Scenario | Expected handling | Should monitor |
| --- | --- | --- |
| Key mapped and channel exists | Send to mapped channel | Message count and handler errors |
| Key unmapped, default exists, channelKeyFallback=false | Send to default | Unmatched event count |
| Key unmapped, no default, key fallback disabled | Throw routing error | Unknown route exception |
| Key unmapped, channelKeyFallback=true, bean matching key exists | May route directly to that bean | Risk of routing outside allowlist |
| Key mapped, channel bean missing, resolutionRequired=true | Throw destination resolution error | Config/deployment error |
| Key mapped, channel bean missing, resolutionRequired=false, default exists | May route to default | Missing channel anomaly |
| Channel found, send fails or handler throws | Dispatch/processing error; default is not necessarily used | Send failure / ErrorMessage |
| QueueChannel found, no poller | Messages accumulate | Queue depth, message age |

**Version note:** router configuration combinations and APIs have evolved over time. For example, starting in Spring Integration 6.0, combining **defaultOutputChannel** while forcing both **channelKeyFallback=true** and **resolutionRequired=true** is considered contradictory and rejected at router initialization. Always verify against your application's actual version when migrating from Spring Integration 5.x to 6.x/7.x.

### 7.4. Optional configuration when a channel may be absent

~~~java
@Bean
IntegrationFlow optionalRouteFlow() {
    return IntegrationFlow.from("optionalEventsChannel")
            .<PaymentEvent, String>route(
                    PaymentRoutingRules::routeKey,
                    spec -> spec
                            .channelMapping("COMPLETED",
                                    "optionalCompletedChannel")
                            .defaultOutputChannel("unmatchedPaymentsChannel")
                            .resolutionRequired(false))
            .get();
}
~~~

This snippet only illustrates the option; real optionalEventsChannel and unmatchedPaymentsChannel beans are needed. On the **COMPLETED** branch, if the mapped channel does not exist, resolutionRequired(false) lets the router fall back to the default path per configured semantics. Choose this only when **a channel's absence is an acceptable state**, not to cover up bean typos.

## 8. Intentionally discarding messages with nullChannel

Sometimes a Router receives a message that **needs no further processing** per business requirements. For example, analytics only tracks a subset of eventTypes, and all other events may be ignored.

Spring Integration provides a special channel named **nullChannel**: it accepts messages and discards them. It can be used as a default output channel:

~~~java
@Bean
IntegrationFlow optionalAnalyticsFlow() {
    return IntegrationFlow.from("analyticsInputChannel")
            .<PaymentEvent, String>route(
                    PaymentRoutingRules::routeKey,
                    mapping -> mapping
                            .channelMapping("COMPLETED",
                                    "analyticsCompletedChannel")
                            .defaultOutputChannel("nullChannel"))
            .get();
}
~~~

The example assumes analyticsInputChannel and analyticsCompletedChannel are declared and the analytics branch has a real consumer. COMPLETED events go to analyticsCompletedChannel; unmapped events go to nullChannel and end.

**Do not use nullChannel when replay, investigation, or reconciliation is needed.** Because the message is dropped, no payload remains to recover afterward. If counts are needed, measure/record before the discard point or use a dedicated endpoint before sending to nullChannel.

### NullChannel vs. dead-letter queue

| Comparison point | nullChannel | Dead-letter queue / error store |
| --- | --- | --- |
| Purpose | Drop messages by design | Retain messages that failed processing |
| Replayable? | No, unless stored elsewhere | Possible if storage and replay tooling support it |
| Needs durable storage? | No | Usually yes if recovery is required |
| Use for important unsupported eventTypes? | No | Should quarantine / send for inspection |
| Automatically retries? | No | No; requires separate retry/redelivery config |

**Never use default nullChannel to hide mapping mistakes** in payment, inventory, or accounting flows. Where audit obligations exist, a message with an unrecognized business key must normally **error out or be held for classification**.

## 9. Post-router dead-ends: right channel, no useful downstream

A route with a valid name that resolves to a bean is not guaranteed to be a **successful path**.

~~~mermaid
flowchart TD
    R["Router selected channel"] --> C{"Channel type"}
    C -->|"DirectChannel"| D{"Has subscriber?"}
    D -->|"No"| E["Dispatch failure"]
    D -->|"Yes"| H["Handler executes"]
    C -->|"QueueChannel"| Q{"Has poller/consumer?"}
    Q -->|"No"| B["Backlog grows / queue full"]
    Q -->|"Yes"| W["Consumer processes"]
    C -->|"ExecutorChannel"| X{"Executor accepts?"}
    X -->|"No"| F["Rejection / overload"]
    X -->|"Yes"| A["Worker processes later"]
~~~

### 9.1. DirectChannel without subscriber

DirectChannel dispatches directly to **one selected subscriber**. With no subscriber, a send failure can occur immediately on the call stack. This is a **wiring** bug, distinct from an unmapped routing key; setting default output channel on the router does not redirect this error to the unmatched channel.

If a channel has multiple subscribers, they are candidates for **a single dispatch**, not an automatic A → B → C chain. If multiple steps are required, link endpoints through sequential channels or IntegrationFlow.

### 9.2. QueueChannel without poller

QueueChannel is a PollableChannel: send may accept messages into the queue, yet **no one receives them** without a consumer calling receive() or a poller endpoint. Once full, producers may block or send returns false on timeout.

By default QueueChannel is in-memory; across restarts, backlogs are lost. To process messages later and survive restarts, use a persistent MessageStore or durable broker, plus ack, retry, and idempotency policies.

### 9.3. ExecutorChannel and post-send errors

ExecutorChannel hands work off to an Executor. The send call may return before the handler runs, so an exception occurring afterward does not automatically return to the caller. Failures also depend on the executor rejection policy, error handler, and endpoint configuration. A default route only handles **destination not found**; it does not replace asynchronous error handling.

### 9.4. Routing loops

A bad mapping can send messages **back to inputChannel**, causing an immediate loop on a synchronous thread or unbounded backlog in an async flow. When channelKeyFallback is enabled and routing keys come from untrusted input, this is a notable risk.

Mitigations: manage channel allowlists, review topology, use safe default routes, enforce hop limits in multi-router designs, and test unknown keys. Do not rely on automatic loop detection if the application lacks one; actively guard configurations.

## 10. Error channels, retries, and operational dead-ends

### 10.1. When do exceptions return to the caller?

In a synchronous DirectChannel chain, exceptions from the router or downstream can usually propagate back to send(). That helps when a Gateway/API must immediately report that a message was not routed.

In async flows with ExecutorChannel, QueueChannel/poller, or inbound adapters, exceptions occurring **after** send() typically must be handled on the consumer side. ErrorMessages can be routed to an **errorChannel** per configuration, though not every exception automatically goes to one global channel.

### 10.2. Do not unconditionally retry missing-route errors

| Error type | Does retry help? | Preferred handling |
| --- | --- | --- |
| Unknown eventType | No, until mapping is updated | Quarantine, alert, add handler |
| Missing channel bean due to misconfig | No, until topology is fixed | Fail fast, fix config/deployment |
| DirectChannel without subscriber | No, until endpoint is wired | Fix wiring / start endpoint |
| QueueChannel with slow consumer | Can clear once consumer recovers | Monitor backlog, capacity, health |
| Downstream REST timeout | Yes, if operation is idempotent | Bounded retries with backoff |
| Handler committed side effect then lost response | Retry may duplicate | Idempotency key, deduplication |

Retrying an **UNKNOWN** routing key thousands of times will not teach the system a new eventType. Contract mismatches need **manual handling or a version-upgrade workflow**.

### 10.3. Quarantine and replay

An unmatched service must decide which fields suffice to process events later:

1. **eventId** or a stable business key to avoid duplicate replay.
2. **Original eventType**, schemaVersion, received timestamp, and routing reason.
3. **Required payload** for recovery, protected under data-security policies.
4. **Processing status**: received, pending review, ready to replay, replayed, rejected.
5. **Replay count** and last failure reason.

Do not cram everything into message headers; audit details usually belong in a dedicated storage schema. A MessageChannel alone is not a database, so **unmatchedPaymentsChannel** only provides the path; the downstream endpoint must persist durably if the contract requires it.

### 10.4. When replay meets a new schema version

A previously unknown message may become supported after deploying a new router. Before replaying, verify:

- Consumers understand the schemaVersion and payload.
- The event has not already been handled by another branch or idempotency protects it.
- Business ordering remains valid (e.g., refund cannot process before payment completed if the state machine forbids it).
- Tracing distinguishes **initial receipt** from **replay**.

Do not replace the original eventId if consumers use eventId as a deduplication key. Add replayAttempt or replayReason metadata in storage instead of mutating eventId.

## 11. Observing default routes and dead-ends

Dropped or unmatched messages can climb silently while healthy branches keep answering. Default routes therefore need baseline metrics and dashboards:

| Signal | Meaning |
| --- | --- |
| **route_selected_total{route}** | Messages per route; spots inactive branches |
| **route_unmatched_total{eventType}** | Unmapped events; keep label cardinality bounded |
| **route_resolution_failed_total** | Unresolvable channel errors |
| **route_send_failed_total{channel}** | Destination dispatch failures |
| **dead_end_backlog_age** | Age of oldest waiting message in queue |
| **quarantine_pending_total** | Messages awaiting classification/replay |
| **replay_failed_total** | Errors when replaying events |

Be careful not to use eventId/orderId as metric labels, which explodes cardinality. Use normalized eventType or bounded route names; use access-controlled traces/logs to look up individual eventIds when needed.

### Business correlation

Headers like **businessCorrelationId** link multiple events of the same payment/order; **traceId/spanId** track each processing branch. These two mechanisms are not synonymous; correlation alone does not guarantee safe delivery or retries.

When a message takes the default route, preserve businessCorrelationId for investigation, logging only necessary fields. Card data, tokens, and sensitive fields should never enter ordinary headers or logs.

## 12. Testing default routes and dead-ends

Tests covering only the happy path miss new eventTypes, misspelled mappings, or consumerless channels. Combine **rule unit tests**, **router integration tests**, and real-infrastructure tests when durability matters.

### 12.1. Unit test: determining routing keys

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

class PaymentRoutingRulesTest {

    @Test
    void returnsMappedKeysForSupportedEvents() {
        PaymentEvent completed = new PaymentEvent(
                "evt-1", "pay-1",
                "payment.completed", BigDecimal.TEN);
        PaymentEvent refunded = new PaymentEvent(
                "evt-2", "pay-2",
                "payment.refunded", BigDecimal.TEN);

        assertEquals("COMPLETED",
                PaymentRoutingRules.routeKey(completed));
        assertEquals("REFUNDED",
                PaymentRoutingRules.routeKey(refunded));
    }

    @Test
    void usesUnknownKeyForNewOrMissingEventTypes() {
        PaymentEvent unknown = new PaymentEvent(
                "evt-3", "pay-3",
                "payment.chargeback", BigDecimal.TEN);
        PaymentEvent missingType = new PaymentEvent(
                "evt-4", "pay-4",
                null, BigDecimal.TEN);

        assertEquals("UNKNOWN", PaymentRoutingRules.routeKey(unknown));
        assertEquals("UNKNOWN", PaymentRoutingRules.routeKey(missingType));
    }
}
~~~

Unit tests verify classification logic, yet do not prove Spring creates the right channels and endpoints.

### 12.2. Integration test: unknown goes to fallback, valid key skips fallback

Example building a minimal Spring context with two DirectChannel destinations and a router. Tests subscribe handlers per test and unsubscribe in finally to prevent cross-test interference.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.SubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(DefaultRouteIntegrationTest.TestConfig.class)
class DefaultRouteIntegrationTest {

    @Configuration
    @EnableIntegration
    static class TestConfig {
        @Bean
        MessageChannel input() {
            return new DirectChannel();
        }

        @Bean
        MessageChannel completed() {
            return new DirectChannel();
        }

        @Bean
        MessageChannel unmatched() {
            return new DirectChannel();
        }

        @Bean
        IntegrationFlow routeEvents() {
            return IntegrationFlow.from("input")
                    .<PaymentEvent, String>route(
                            PaymentRoutingRules::routeKey,
                            r -> r.channelMapping("COMPLETED", "completed")
                                  .defaultOutputChannel("unmatched"))
                    .get();
        }
    }

    @Autowired
    @Qualifier("input")
    MessageChannel input;

    @Autowired
    @Qualifier("completed")
    SubscribableChannel completed;

    @Autowired
    @Qualifier("unmatched")
    SubscribableChannel unmatched;

    @Test
    void unknownEventGoesOnlyToDefaultChannel() {
        AtomicInteger completedCount = new AtomicInteger();
        AtomicInteger unmatchedCount = new AtomicInteger();
        MessageHandler completedHandler =
                message -> completedCount.incrementAndGet();
        MessageHandler unmatchedHandler =
                message -> unmatchedCount.incrementAndGet();
        completed.subscribe(completedHandler);
        unmatched.subscribe(unmatchedHandler);

        try {
            PaymentEvent event = new PaymentEvent(
                    "evt-10", "pay-10",
                    "payment.chargeback", new BigDecimal("10000"));

            assertTrue(input.send(MessageBuilder.withPayload(event).build()));
            assertEquals(0, completedCount.get());
            assertEquals(1, unmatchedCount.get());
        } finally {
            completed.unsubscribe(completedHandler);
            unmatched.unsubscribe(unmatchedHandler);
        }
    }

    @Test
    void supportedEventDoesNotGoToDefaultChannel() {
        AtomicInteger completedCount = new AtomicInteger();
        AtomicInteger unmatchedCount = new AtomicInteger();
        MessageHandler completedHandler =
                message -> completedCount.incrementAndGet();
        MessageHandler unmatchedHandler =
                message -> unmatchedCount.incrementAndGet();
        completed.subscribe(completedHandler);
        unmatched.subscribe(unmatchedHandler);

        try {
            PaymentEvent event = new PaymentEvent(
                    "evt-11", "pay-11",
                    "payment.completed", new BigDecimal("50000"));

            assertTrue(input.send(MessageBuilder.withPayload(event).build()));
            assertEquals(1, completedCount.get());
            assertEquals(0, unmatchedCount.get());
        } finally {
            completed.unsubscribe(completedHandler);
            unmatched.unsubscribe(unmatchedHandler);
        }
    }
}
~~~

In this test, synchronous DirectChannels let us assert results immediately after send(). If destinations are replaced with ExecutorChannel, wait for handler completion using CountDownLatch or another test synchronization primitive. Never rely on arbitrary sleeps to guess timing.

### 12.3. Testing a routed dead-end

Another useful integration test creates a DirectChannel **with no subscriber**, maps a key to it, and verifies send() fails per contract. An analogous test with QueueChannel should verify messages remain in the queue or report full when no poller exists, rather than expecting the router to redirect to the default channel.

To avoid confusion, name tests clearly:

- **unknownKeyUsesDefaultRoute**
- **mappedKeyUsesMappedChannel**
- **unknownKeyWithoutDefaultFailsFast**
- **mappedKeyWithMissingChannelFailsResolution**
- **mappedDirectChannelWithoutSubscriberFailsDelivery**
- **queueWithoutConsumerAccumulatesBacklog**
- **nullChannelDropsOnlyWhitelistedIgnoredEvents**

Additionally, test deployment mapping mistakes via bean/channel checks and startup verification; when durability is required, test process or broker restarts rather than only mocking MessageStore.

## 13. Practice exercise: building a safe fallback

Design a Content-Based Router for an order system with these events:

| eventType | Intended route |
| --- | --- |
| order.created | orderCreatedChannel |
| order.cancelled | orderCancelledChannel |
| order.fulfilled | orderFulfilledChannel |
| order.returned | Unsupported yet, needs quarantine |
| missing/unknown | Per validation or quarantine policy |

**Implementation requirements**

1. Create record **OrderEvent(eventId, orderId, eventType, schemaVersion)**.
2. Write a pure Java function choosing the routing key; avoid returning bean names directly from user input.
3. Use IntegrationFlow Java DSL to declare **channelMapping** entries and **defaultOutputChannel("unmatchedOrdersChannel")**.
4. Create an endpoint on the unmatched channel to record eventId, routing key, schemaVersion, and unsupported reason.
5. Write tests ensuring **order.returned** enters unmatched and **order.created** goes only to orderCreatedChannel.
6. Add a strict version without a default route, disable channelKeyFallback, and verify unknown keys fail.
7. Try replacing one destination DirectChannel with a QueueChannel **without** configuring a poller; describe how to monitor backlog rather than concluding routing failed.
8. Propose a durable persistence and replay solution once a new consumer supports order.returned; require an idempotent consumer.

### Extension: choose default or fail fast?

For each scenario below, state a **decision and rationale**:

| Scenario | A reasonable policy |
| --- | --- |
| Payment service receives an eventType absent from contract | Fail fast, alert, or durable quarantine |
| Analytics collector sees a new event under a policy to track only three types | Drop with metrics or quarantine per requirements |
| Router maps COMPLETED yet completedPaymentsChannel is missing | Fail fast to fix configuration |
| Slow consumer fills QueueChannel | Backpressure, timeouts, bounded retries, load monitoring |
| Email notification hits transient network error | Local retry with backoff; avoid whole-flow retry if it duplicates |

There is no single right answer; choices depend on data criticality, retention obligations, replay capability, and duplicate-processing impact.

### Self-check questions

1. At which step of the router is the default output channel used?
2. Why can a validly named channel still be a dead-end route?
3. When is using nullChannel reasonable, and when is it dangerous?
4. How does channelKeyFallback differ from resolutionRequired?
5. In Spring Integration 6+, how does setting default output channel affect channelKeyFallback?
6. Why shouldn't a missing mapped channel be treated as an unknown eventType?
7. Does retrying a message missing a routing key solve the problem?
8. If a QueueChannel receives messages while its consumer is inactive, which signal do you monitor?
9. Why might replaying from quarantine require idempotency?

## 14. Pre-release checklist for Content-Based Router

- Valid routing keys and mappings are documented and tested.
- Each route has an existing channel and matching downstream handler/poller.
- New unsupported keys are distinguished from missing beans/channels in configuration.
- One of the three policies—**fail fast, quarantine, discard**—is chosen explicitly.
- Default output channel has a consumer or appropriate persistence/observation mechanism.
- nullChannel is used only when message dropping is explicitly agreed in the contract.
- channelKeyFallback and resolutionRequired are controlled per Spring Integration version.
- Send failures and async handler errors are handled by proper error flows and retries.
- Replays are protected by stable eventIds and idempotent consumers.
- Metrics exist for unmatched events, resolution failures, downstream failures, and queue backlog.
- Integration tests cover valid routes, default routes, consumerless routes, and invalid eventTypes.

**Practical principle:** Content-Based Router makes the **routing decision**, default route handles **no matching destination**, and dead-end route is the condition where **messages no longer advance to useful processing**. Defining these states clearly helps Spring Integration systems catch bugs early, avoid accidentally losing important messages, and maintain observability across branches.

## References

- [Spring Integration Reference — Router Implementations](https://docs.spring.io/spring-integration/reference/router/implementations.html): Content-Based Router, payload/header routers, and Java DSL.
- [Spring Integration Reference — Common Router Parameters](https://docs.spring.io/spring-integration/reference/router/common-parameters.html): default output channel, resolution required, channel key fallback, and send failures.
- [Spring Integration API — AbstractMappingMessageRouter](https://docs.spring.io/spring-integration/api/org/springframework/integration/router/AbstractMappingMessageRouter.html): channelKeyFallback and default channel in current versions.
- [Spring Integration API — RouterSpec](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/dsl/RouterSpec.html): declaring channelMapping and mapping router options.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): DirectChannel, QueueChannel, ExecutorChannel, and nullChannel.
