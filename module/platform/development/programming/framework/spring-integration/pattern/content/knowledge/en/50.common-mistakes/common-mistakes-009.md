# Wire Tap Slowing Down Flows or Leaking Data

## 1. Context: Observing a Flow While Accidentally Impacting the Main System

In the **SPRING_INTEGRATION_PATTERN** module, we learn Spring Integration's *Enterprise Integration Patterns* to build loosely coupled, extensible, and testable message flows. When combining Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation into a flow, the need to **see where messages are going** is very real.

Spring Integration provides **Wire Tap** to observe messages passing through a channel without altering the primary consumer's business logic. Teams often add Wire Taps for debugging, logging, metrics, or inspecting branches. However, an uncontrolled tap configuration can cause **two independent categories of incidents**:

1. **Slowing down the main flow:** the tap passes messages through synchronous handlers, queries databases, serializes large payloads, or writes slow logs. The sending thread has to perform extra work before the main flow proceeds.
2. **Leaking data:** the tap sends raw payloads/headers into logs, tracing, queues, analytics services, or third-party systems; these may contain tokens, personal information, account numbers, order contents, or other sensitive data.

For example, a `PaymentRequested` flow may carry `commandId`, payment details, and partner authentication tokens. A tap meant to count requests does not need to inspect the entire payload. If a logger is configured to print `message.toString()` or `headers` at INFO level, unnecessary data is copied into log stores with different retention periods and access scopes than the business application.

> **Principle:** Wire Tap is an **observation branching mechanism**, not a promise of "zero cost", "always asynchronous", or "allowed to record every message". Using it safely requires designing **the target channel, performance budget, data scope, error handling, and storage purpose**.

### Lesson Objectives

After this lesson, you will be able to:

- Explain how Wire Tap works as a `ChannelInterceptor` and why a synchronous tap can increase latency.
- Distinguish taps for debugging, metrics collection, and mandatory auditing systems.
- Choose `DirectChannel`, `ExecutorChannel`, queues, or brokers suited to observation and delivery goals.
- Design allowlists/redaction to prevent leaking payloads, headers, secrets, and personal data.
- Detect backpressure, executor rejections, tap handler failures, oversized logs, and overly broad global tap configs.
- Test business and observation paths independently, including when the tap is slow or down.

## 2. What Is a Wire Tap in Spring Integration?

A Wire Tap is a **`ChannelInterceptor`** registered on a channel to send messages passing through it to an additional **tap channel**. The main flow keeps its own destination. In Java DSL, you can use the `wireTap(...)` operator; the `log(...)` operator is also implemented via a Wire Tap connected to a `LoggingHandler`.

```mermaid
flowchart LR
    A[Inbound event] --> C[Business input channel]
    C --> W[WireTap interceptor]
    W --> T[Tap channel]
    T --> L[Metrics / safe log / diagnostic]
    W --> B[Business handler]
    B --> N[Next business step]
```

**Note:** The diagram shows two processing paths; it does **not** imply the tap always runs concurrently with the business handler. Synchronicity or asynchronicity comes from **the target channel type and executor**.

| Component | Role | Misconception to Avoid |
| --- | --- | --- |
| `WireTap` | Intercepts messages and sends an extra copy to a tap channel | Does not create threads or persistence on its own. |
| Target `DirectChannel` | Invokes tap handler on the sending thread via synchronous dispatch | A slow tap can increase main-flow latency. |
| Target `ExecutorChannel` | Dispatches tap handler on an executor | Does not guarantee tasks won't be rejected, data is persisted, or loggers won't bottleneck. |
| Target `QueueChannel` | Buffers messages for a consumer/poller | In-RAM queues are not durable; full queues can cause backpressure or send failures. |
| `LoggingHandler` / DSL `log()` | Logs messages by level/category/expression | May log payloads by default; not a sensitive-data filter. |
| `MessageStore` / broker | Stores messages per configured mechanism | Does not replace audit transactions or data protection policies. |

A Wire Tap must not be assumed to create an independently **deep-copied** message: Spring messages typically have immutable headers once created, but **the payload may be a mutable Java object**. If a tap handler or business handler mutates the payload object directly, both branches may observe altered data or race when running concurrently. Use immutable DTOs, never mutate shared payloads, or project a **separate diagnostic DTO** before passing to observation systems.

### 2.1. Wire Tap Is Not the Same as Publish-Subscribe Channel

`PublishSubscribeChannel` distributes messages to multiple subscribers as the primary function of the channel. Wire Tap is **an observation branch attached to a channel that has a main flow**. Both can forward messages to multiple components and both require evaluating synchronicity, backpressure, errors, and durability. Using Wire Tap does not automatically solve "every business consumer must receive all events even when offline".

### 2.2. A Tap Only Sees Messages at the Attachment Point

A tap placed **after a Filter** does not see messages the Filter dropped; a tap before a Transformer sees the raw payload; a tap after a Transformer sees the transformed payload. If a global Wire Tap is attached to multiple channels, **the same event can be observed multiple times** along its journey. Do not treat the number of tap handler invocations as the count of completed transactions without verifying placement.

## 3. Why Does a Synchronous Tap Slow Down the Main Flow?

Suppose a request travels through a `DirectChannel` and a Wire Tap sends the message to a tap channel that is also a `DirectChannel`. Upon interception, the tap path invokes the observer handler **synchronously** before the message continues to the primary consumer.

```mermaid
sequenceDiagram
    autonumber
    participant R as Request thread
    participant C as Channel + WireTap
    participant L as Tap handler (DirectChannel)
    participant B as Business handler
    R->>C: send(message)
    C->>L: tap.send(message)
    Note over R,L: Synchronous serialize/log/IO holds the request thread
    L-->>C: Tap handler finishes
    C->>B: Deliver message to business handler
    B-->>R: Continue processing
```

Request duration can grow roughly by the extra tap work; actual latency also depends on dispatch mechanics, loggers, contention, and measurement points. If the tap calls an external service with a 2-second timeout, a business flow that normally takes 50 ms can be stretched dramatically even though business logic does not need tap data to finish.

### 3.1. Common Latency Sources

| Slowness Source | Why It Impacts Latency | Remedy |
| --- | --- | --- |
| Serializing whole object graphs | Large payloads, nested objects, lazy-loading, or heavy `toString()` | Extract only a small allowlist of fields in a fixed format. |
| Synchronous logging to disk/network | Slow appender or collector I/O, internal locks | Consider bounded async logging; do not treat async appenders as durable. |
| Tap calling HTTP/database | Main thread waits on network/transactions | Move best-effort observation to a bounded executor or separate durable event architecture. |
| Too many global taps | Same message serialized/logged repeatedly across channels | Narrow channel patterns, sample, and avoid duplicate measurement points. |
| Tap blocking on full channel | Buffer runs out of space or executor stops accepting tasks | Set capacities, explicit timeout/rejection policies, and monitor queue depth. |
| Locks/CPU/GC | Allocating excessive log strings, JSON, stack traces | Reduce event volume and size; measure CPU/heap/GC and latency. |

**Measure accurately:** compare p50/p95/p99 latency and throughput of the business flow **before and after** enabling the tap under the same load profile. Separately measure projection/serialization time and enqueue time into the tap channel; looking only at averages hides tail latency.

### 3.2. Async Does Not Automatically Mean "Zero Impact"

If the tap channel uses an executor, the caller typically only dispatches the task and moves on, yet **the cost of task creation, queue checks, handler selection, and error management still occurs**. When the executor saturates, policies may:

- **Reject tasks** (e.g., `AbortPolicy`), raising errors at dispatch time.
- **Run on the caller thread** (e.g., `CallerRunsPolicy`), pushing tap latency straight back onto the main path.
- **Wait or buffer** depending on configuration, increasing latency or heap usage.
- **Discard tasks** under specific policies, losing observation data without metrics/alerts.

Thus choosing async only **shifts the load point**—it neither eliminates cost nor guarantees delivery. Document explicitly whether observation is allowed to drop data (*best effort*) or not.

## 4. Why Can a Wire Tap Leak Data?

A `Message<?>` can hold sensitive information in both **payload** and **headers**. For example:

| Location | Examples That May Appear | Risk If Logged in Full |
| --- | --- | --- |
| Payload | Shipping addresses, customer info, payment fields, document contents | PII or business data sent to log systems outside intended access boundaries. |
| Headers | `Authorization`, cookies, API keys, session IDs, JWTs, partner metadata | Exposes credentials or session identifiers. |
| Exceptions | URLs with tokens, SQL errors containing parameters, raw response strings | Sensitive data surfaces in stack traces or error messages. |
| Serialized `toString()` | Nested objects, newly added DTO fields | Accidentally expands logged fields after a model change. |
| Trace/baggage | Correlation IDs, customer names, addresses, upstream-injected metadata | Trace metadata spreads across many systems with long retention. |

You do not need to log the entire payload to tell which channel a flow traversed. **Minimum necessary data** for observation usually consists only of event name, message ID, branch code, processing outcome, latency, and a correlation ID evaluated for sensitivity.

### 4.1. Logging Anti-Patterns

```java
// ANTI-PATTERN: includes full payload/headers, potentially containing secrets.
logger.info("message={}", message);

// ANTI-PATTERN: serializes all fields to the log collector.
logger.debug("payload={}", objectMapper.writeValueAsString(message.getPayload()));

// ANTI-PATTERN: logs all HTTP/message headers.
logger.info("headers={}", message.getHeaders());
```

Raising log level from DEBUG to INFO to debug production can trigger a sudden surge of sensitive data written to logs. `LoggingHandler` with full-message mode is especially dangerous when headers carry credentials. Never assume log collectors, tracing backends, or everyone with log read access is authorized to view all business data.

### 4.2. "Regex Masking" Is Not Enough

Regexes masking card numbers or tokens in log strings do not prove every nested object, encoded payload, new field, or exception message is masked. For high-risk data, **allowlist the fields eligible for emission**, classify and validate schemas before serialization, and apply additional redaction as a second line of defense. Test actual emitted output rather than just eyeballing masking code.

### 4.3. Operational Consequences of Data Leaks

Once a payload enters a logging system, it can be replicated to dashboards, backups, alerts, search indices, or downloadable exports, each with different retention and access permissions. Tap design must account for **data classification, retention, encryption, access control, access auditing, staging/production environments, and data deletion workflows**.

## 5. Architectural Boundary: Diagnostics, Tracing, and Auditing Are Not the Same

| Need | Required Guarantee | Mechanism to Consider |
| --- | --- | --- |
| Temporary message flow debugging | Best effort, sampled, quick toggle-off | Wire Tap with safe logging or bounded observation channel. |
| Operational metrics | Aggregatable, no full payloads needed | Low-cardinality counters/timers recorded at appropriate endpoints. |
| Distributed tracing | Span relationships, correlation, latency | Instrumentation/observation and trace sampling; do not log payloads by default. |
| Mandatory business auditing | Must not lose critical decisions/effects per contract | Write audit in same transaction or transactional outbox + durable consumer. |
| Business recovery after restart | Durable data and state | Durably configured broker, inbox/outbox, idempotent state machine. |

**Audits are different from diagnostic logs.** If payment settlement requires a `PaymentSettledAudit`, merely Wire Tapping into a logger/`ExecutorChannel` is insufficient to guarantee audit persistence. If the business transaction commits and the application crashes before the tap publishes, the audit event can be lost. Durable persistence with transaction boundaries and proper redelivery policies is required.

An audit log may hold sensitive fields if genuinely required, but it must have a **minimal data model and independent access controls**, rather than copying whole messages to "avoid designing a schema".

## 6. Java DSL Example: Wire Tap Observing Only One Channel

The following example creates a main flow and a separate tap. `businessIngress` and `businessRequests` are `DirectChannel`s, while `diagnosticTapInput` uses an `ExecutorChannel` to isolate most log-processing time from the main flow's thread. Use a **bounded** executor and explicit rejection policy.

```java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableIntegration
public class BoundedDiagnosticTapConfig {

    @Bean
    public MessageChannel businessIngress() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel businessRequests() {
        return new DirectChannel();
    }

    @Bean
    public ThreadPoolTaskExecutor diagnosticExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("diagnostic-tap-");
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(200);
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        // Spring manages lifecycle and initialize() for this bean.
        return executor;
    }

    @Bean
    public MessageChannel diagnosticTapInput(
            @Qualifier("diagnosticExecutor") ThreadPoolTaskExecutor executor) {
        return new ExecutorChannel(executor);
    }

    @Bean
    public IntegrationFlow businessFlowWithTap() {
        return IntegrationFlow.from("businessIngress")
                .wireTap("diagnosticTapInput")
                .channel("businessRequests")
                .get();
    }
}
```

This configuration only makes sense when **target channels have real consumers**. Add a `ServiceActivator` on `businessRequests` for business logic, and a handler on `diagnosticTapInput` to record safe telemetry. Without a subscriber on the target `DirectChannel`, sending messages can fail due to **flow configuration**, not Wire Tap itself.

**Limitations to understand:**

- `AbortPolicy` does not persist diagnostic messages: when the executor saturates, tasks can be rejected and impact the main flow's send operation. Do not treat the setup above as "absolute fire-and-forget".
- If the observation path is allowed to drop data, the application needs a deliberately designed and tested rejection policy instead of letting unexpected errors propagate back; always count rejected tasks.
- If auditing is mandatory, do **not** solve it by switching to a silent task-drop policy; use an outbox or durable broker.
- Even with `ExecutorChannel`, the message/payload is referenced across different threads; avoid mutating payload objects and avoid holding unnecessarily large objects in the queue.

### 6.1. Observer Handler Using Only Allowlisted Fields

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class DiagnosticTapObserver {
    private static final Logger log =
            LoggerFactory.getLogger(DiagnosticTapObserver.class);

    @ServiceActivator(inputChannel = "diagnosticTapInput")
    public void observe(Message<?> message) {
        // Do not log payload; do not print headers.toString().
        // Map header values into an allowlisted set of event names.
        Object rawType = message.getHeaders().get("eventType");
        String type = switch (rawType instanceof String text ? text : "") {
            case "PAYMENT_REQUESTED" -> "PAYMENT_REQUESTED";
            case "PAYMENT_SETTLED" -> "PAYMENT_SETTLED";
            default -> "OTHER";
        };

        log.info("tap_event={} message_id={}",
                 type, message.getHeaders().getId());
    }
}
```

`MessageHeaders.ID` is a Spring-generated message ID, not necessarily the business ID used to correlate ACKs. If `commandId` is needed, evaluate its sensitivity and logging policy first; never log tokens or customer info simply because they live in headers.

In production, slow logging, failing log appenders, or long-term trace storage should never become a hard dependency of the payment path. Separate **best-effort diagnostics** from **business audits**.

## 7. Java DSL `log()` Also Carries Cost and Leak Risks

In Spring Integration DSL, the `log()` operator is built on top of a Wire Tap paired with `LoggingHandler`. Therefore, it **does not offload to another thread by default**.

```java
import org.springframework.integration.handler.LoggingHandler;

// Snippet inside an IntegrationFlow: logs only the message ID.
.filter(...)
.log(LoggingHandler.Level.DEBUG,
     "app.integration.safe",
     message -> message.getHeaders().getId())
.route(...)
```

This snippet is only **a DSL fragment inside an existing flow with `filter(...)` and `route(...)`**, not a standalone compilable Java file. Choose an expression that logs only a non-sensitive ID instead of dumping `payload` or all `headers`.

### 7.1. `log()` at the End of a Flow

`log()` is an observation operator. **Since Spring Integration 6.0**, `log()` at the end of a flow was adjusted so it does not alter flow behavior compared to omitting the operator; if the end of the flow **does not need a reply**, the documentation recommends appending `nullChannel()` after `log()`. For flows **needing a reply**, design a handler/channel returning the contracted result rather than assuming adding `log()` creates a reply to keep the Gateway from timing out. Older Java DSL versions had different terminal `log()`/`logAndReply()` rules, so check documentation for your exact version.

For a genuinely one-way flow needing no result, terminate the flow after logging per corresponding configuration. For a flow returning financial outcomes, logging must never substitute for producing the output message.

### 7.2. Global Wire Taps Require Extra Caution

`@GlobalChannelInterceptor` and global wire taps can attach to many channels by pattern. This is a powerful debugging tool, yet it easily:

- Logs the same message repeatedly at 5–10 spots, inflating CPU/I/O and storage cost.
- Captures payloads **before** redaction/Transformer steps run.
- Observes channels carrying tokens, customer data, callback credentials, and errors.
- Accidentally applies to new flows when channel names match an overly broad pattern.

When a global tap is needed, specify explicit channel names, restrict environments and active duration, test patterns against an allowlist of channels, and control log levels and config permissions. Avoid overly broad patterns like `*` in production.

## 8. Emit a Dedicated Diagnostic Event Instead of Forwarding Raw Messages Outward

Even if a logger prints only two fields, the tap handler **still receives the entire original message**. If the tap path goes to a broker, APM agent, or third-party service, convert the message into a **minimal diagnostic event** before crossing the trust boundary.

A simple data model:

```java
import java.util.UUID;
import org.springframework.messaging.Message;

record TapObservation(
        UUID messageId,
        String eventType,
        boolean hasCorrelation) {
}

final class TapObservationProjector {
    private TapObservationProjector() {}

    static TapObservation from(Message<?> original) {
        Object rawType = original.getHeaders().get("eventType");
        String safeType = switch (rawType instanceof String text ? text : "") {
            case "PAYMENT_REQUESTED" -> "PAYMENT_REQUESTED";
            case "PAYMENT_SETTLED" -> "PAYMENT_SETTLED";
            default -> "OTHER";
        };

        boolean hasCorrelation =
                original.getHeaders().containsKey("correlationId");

        return new TapObservation(
                original.getHeaders().getId(),
                safeType,
                hasCorrelation);
    }
}
```

The projector class **does not** read payload, `Authorization`, cookies, or non-allowlisted headers. It emits only three fields approved for observation. When persisting or transmitting events outward, serialize **`TapObservation`**, never the original `Message<?>`.

If you want to add `commandId`, `customerId`, `errorMessage`, or URLs, review them as a data schema change: they may contain sensitive info or high cardinality. For many statistical needs, a boolean `hasCorrelation` or outcome category is enough without storing raw ID values.

**Note:** a projector inside a tap handler still runs in a component privileged to see the original message; architectures with very strict security requirements may emit the diagnostic DTO **directly at the producer or after sanitization** so generic observation components never receive raw data.

## 9. Conditional Wire Tap and Sampling

Spring Integration supports **conditional wire taps** using a `MessageSelector` or `selector-expression`. This is useful to observe only permitted message types or only events needed for debugging.

Example rules you might apply:

```text
Allowed to observe:
  - eventType=PAYMENT_REQUESTED
  - environment=staging
  - diagnosticEnabled=true

Forbidden to observe:
  - eventType=SECRET_ROTATED
  - eventType=CUSTOMER_DOCUMENT_UPLOADED
  - payload lacking sensitivity classification
```

These are **illustrative rules**, not full configuration syntax. When using a selector, ensure:

- The selector **never** calls external services, serializes full payloads, or triggers side effects.
- Default policy is **do not tap** when data classification is unknown.
- Sampling is bounded and its sample rate is explicitly recorded to prevent statistical misinterpretation.
- Never treat sampling as a way to record mandatory audits: audits require every event per contract.
- Never turn on dynamic debugging for an entire payment/personal-data flow just to hunt down one small bug.

### 9.1. Avoiding Double-Counting

If an `OrderCreated` passes through `inboundChannel`, `normalizedChannel`, and `dispatchedChannel`, a global tap can record three "observations" for the same event. To measure **number of orders created**, increment a metric when the business transaction commits; to measure **channel message transfers**, name it distinctly and tag `channel` from a low-cardinality set.

## 10. Backpressure, Tap Failures, and Error Channels

Wire Tap does not replace error handling architecture. Scenarios to examine by channel type:

| Tap Channel | When Tap Handler Is Slow | When Tap Handler Throws | Control Strategy |
| --- | --- | --- | --- |
| `DirectChannel` | Can block the sender thread | Exception can affect sender and main flow | Do not use slow-I/O handlers, or move observation off the main path. |
| `ExecutorChannel` | Tasks/queue build up; rejects once full | Worker exceptions follow async error handling | Bounded executor, queue/reject metrics, error flow, clear degradation policy. |
| In-RAM `QueueChannel` | Buffer grows, consuming heap | Consumer/poller reports errors per config | Capacity, poller, retries, alerts; never mistake for persistence. |
| Broker adapter | Depends on publish confirm/ACK and network | May hit transport errors and retries | If audit must be durable, use outbox and proper delivery contract. |

### 10.1. Do Not Accidentally Turn Observation Failures Into Business Failures

A synchronous tap handler can throw an exception when a logger, serializer, or database slows down. If the exception propagates back to the sending thread, the application might mark **the entire payment** as failed merely because a diagnostic log could not be written. That is inappropriate coupling for best-effort observability.

Conversely, if a tap genuinely performs a **mandatory audit step**, ignoring all exceptions is also wrong. Audits belong in a transaction or durable event pipeline with a policy consistent with business requirements. Every tap must have an explicit goal:

- **Best effort:** keep only minimal metrics/logs; may reduce sampling or drop observations under overload while counting and alerting.
- **Must deliver:** place minimal event safely into durable state/outbox; consumers have retries, DLQ, idempotency, and reconciliation.

You cannot guarantee both "audits are never lost" and "taps never affect latency" merely by switching to an in-RAM `ExecutorChannel`.

### 10.2. Error Channel Does Not Equal Redelivery

In asynchronous flows, `ErrorMessage` may go to `errorChannel` for error observation/orchestration. Having an error channel does **not** guarantee the original event still exists in the broker, was not ACKed, or will automatically retry. With `MessageSource`/adapters/brokers, inspect transactions, acknowledgements, offsets, retry advice, and DLQs separately.

### 10.3. Do Not "Fix" Backpressure With Unbounded Buffers

When a tap handler processes slower than incoming message rates, queues grow. An unbounded buffer merely shifts the outage from latency into **memory growth, GC pauses, and OOM**. Specify capacity limits, backlog timeouts, rejection policies, and alert thresholds. If durable backlogs are needed, use storage/brokers with appropriate retention and operational capacity.

## 11. Securing Logs and Observability Across the Data Lifecycle

A checklist before enabling Wire Tap in production:

| Control Item | Question to Answer |
| --- | --- |
| Data classification | Does the flow contain PII, financial info, tokens, cookies, records, or third-party data? |
| Purpose | Is the tap for debugging, metrics, tracing, or mandatory auditing? |
| Allowlist | Which exact fields are permitted to cross the business boundary? |
| Retention | How long are logs retained, and how does that differ from primary business data? |
| Access control | Who can read logs, dashboards, traces, exports, and backups? |
| Encryption | Are transport to collectors and stored data protected per policy? |
| Errors/exceptions | Could stack traces or exception messages contain sensitive data? |
| Schema changes | If a DTO adds a new field, will the tap automatically start logging it? |
| Environments | Do staging, production, and incident modes have different logging policies? |
| Incident response | Can the tap be disabled quickly, exported logs searched, and leaks remediated? |

Never log tokens/credentials even in shared test environments. If you must store an identifier for tracing, consider non-sensitive internal identifiers or policy-compliant tokenization/HMAC; never log raw emails, phone numbers, or customer IDs when the goal is only counting messages.

A safer log block:

```text
event=wiretap_observed
flow=payments
channel=normalizedPayments
messageType=PAYMENT_REQUESTED
hasCorrelation=true
observationSize=SMALL
```

These lines are an **illustrative application-emitted format**, not a default logger configuration. Fields must be populated from controlled or normalized value sets to prevent log injection and high cardinality.

## 12. Testing: Proving the Main Flow Does Not Depend on Observation Copies

Testing must cover **correct message routing**, **correct data scope**, and **behavior when the tap fails**. First, test fan-out using test-only `QueueChannel`s to receive messages from both branches.

### 12.1. An Isolated Test Configuration

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class TapFanOutTestConfig {
    @Bean
    public MessageChannel testIngress() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel businessProbe() {
        return new QueueChannel(10);
    }

    @Bean
    public QueueChannel tapProbe() {
        return new QueueChannel(10);
    }

    @Bean
    public IntegrationFlow testTapFlow() {
        return IntegrationFlow.from("testIngress")
                .wireTap("tapProbe")
                .channel("businessProbe")
                .get();
    }
}
```

The two `QueueChannel`s in the test are **bounded test probes for verification**, not a production design and not proof of durability.

### 12.2. Spring Integration Test for Both Branches

```java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TapFanOutTestConfig.class)
class TapFanOutTest {

    @Autowired @Qualifier("testIngress")
    MessageChannel ingress;

    @Autowired @Qualifier("businessProbe")
    QueueChannel business;

    @Autowired @Qualifier("tapProbe")
    QueueChannel diagnostic;

    @Test
    void observesMessageWithoutRemovingItFromBusinessPath() {
        Message<String> input = MessageBuilder.withPayload("event")
                .setHeader("eventType", "PAYMENT_REQUESTED")
                .build();

        assertTrue(ingress.send(input));

        Message<?> businessReceived = business.receive(1_000);
        Message<?> tapReceived = diagnostic.receive(1_000);

        assertNotNull(businessReceived);
        assertNotNull(tapReceived);
        assertEquals(input.getHeaders().getId(),
                     businessReceived.getHeaders().getId());
        assertEquals(input.getHeaders().getId(),
                     tapReceived.getHeaders().getId());
    }
}
```

This test verifies a message is sent to both paths in **the test configuration**. It does not yet prove an async tap causes no slowdown, does not measure latency, and does not prove data is redacted.

### 12.3. Unit Test for the Allowlist Projector

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;

class TapObservationProjectorTest {

    @Test
    void doesNotExportSensitivePayloadOrHeaders() {
        Message<Map<String, String>> sensitiveMessage =
                MessageBuilder.withPayload(Map.of(
                        "personalDocument", "synthetic-private-value",
                        "paymentToken", "synthetic-token-value"))
                .setHeader("Authorization", "Bearer synthetic-credential")
                .setHeader("eventType", "PAYMENT_REQUESTED")
                .setHeader("correlationId", "operation-42")
                .build();

        TapObservation observation =
                TapObservationProjector.from(sensitiveMessage);

        assertEquals("PAYMENT_REQUESTED", observation.eventType());
        assertTrue(observation.hasCorrelation());
        assertEquals(sensitiveMessage.getHeaders().getId(),
                     observation.messageId());

        String emitted = observation.toString();
        assertFalse(emitted.contains("synthetic-private-value"));
        assertFalse(emitted.contains("synthetic-token-value"));
        assertFalse(emitted.contains("synthetic-credential"));
        assertFalse(emitted.contains("operation-42"));
    }
}
```

The test uses **synthetic values**, never real credentials. To verify actual data leaving the system, test at the serializer/logger/collector boundary: inspect final JSON/log output, appender configs, and exception paths.

### 12.4. Additional Scenarios to Cover

| Test Case | How to Test | Expected Result |
| --- | --- | --- |
| Slow synchronous tap | Place a latch in the tap handler and measure send path | Understand blocking and latency; avoid assuming taps are always async. |
| Overloaded async tap | Small executor, bounded queue, controlled burst | Rejection/backpressure follows policy, emits metrics, and never becomes an unexpected business error. |
| Logging handler throws | Break tap handler in test | Error path matches synchronous/asynchronous channel behavior. |
| PII in payload | Synthetic data containing emails/tokens | Sensitive data is absent from serialized events/logs. |
| Secrets in headers | Synthetic `Authorization`, cookies, tokens | Never serialized or logged by the tap. |
| Flow with multiple taps | Attach taps across sequential channels | Metrics are not mistaken for business transaction counts. |
| Schema change | Add a new sensitive field to DTO | Allowlist does not automatically export the new field. |
| Broker/audit outage | Pause sink, inspect outbox/backlog | If auditing is mandatory, events persist and recover properly. |
| Restart mid-publish | Fault injection before/after commit | Do not infer from Wire Tap that observation is durably guaranteed. |

Performance tests should run against the same build version, workload, payload size, and log level. Concurrency tests must use observable synchronization points instead of `Thread.sleep()` to guess ordering.

## 13. Observability and Signs That a Tap Is Causing Harm

A useful dashboard tracks not only message counts, but also **the tap path's impact on the business flow**:

| Metric | Why Needed |
| --- | --- |
| Business p95/p99 latency | Detect latency increases after enabling Wire Tap or logging. |
| Tap enqueue/dispatch duration | Detect sender blocking when dispatching to observation channels. |
| Tap handler duration | Check whether serializers, formatters, loggers, or network calls are slow. |
| Tap queue depth / oldest age | Detect backlogs and OOM risk. |
| Executor active threads / rejected tasks | Detect saturation and active rejection policies. |
| Tap error / dropped observation count | Identify incomplete observation data. |
| Log bytes per second / ingestion errors | Measure cost and risk of overloading log collectors. |
| Redaction policy violations | Detect unauthorized fields leaking into events/logs. |
| Audit outbox lag | For mandatory audits, track durable event persistence and emission. |

Do not use `traceId`, `commandId`, email, or raw URLs with query parameters as labels for every metric: cardinality explodes and data can leak. They may appear in logs/traces **after approval and safe handling**; metrics should use controlled flow/channel/event-type names.

### 13.1. Warning Signs to Investigate

- p99 latency spikes right after raising log levels.
- CPU/GC climbs and log volume surges after adding `toString()` or JSON serialization.
- Diagnostic executor queue fills up and rejected counts climb.
- A logger or collector outage causes business requests to fail.
- Dashboards report more "payments processed" than committed transactions due to tapping multiple channels.
- A new event introduces a token field and the log schema automatically prints the full payload.
- `ErrorMessage` contains raw exception text exposing URLs, tokens, or customer info.

Have a way to **quickly disable/throttle taps** during incidents, while defining beforehand which data may be dropped (diagnostics) and which mandatory audits must never be dropped.

## 14. Roadmap for Fixing a Misbehaving Wire Tap

If production is already experiencing high latency or data leaks from a tap, address them in order:

1. **Identify scope:** list tapped flows/channels, global patterns, `log()` operators, and active logging adapters.
2. **Inventory data types:** flag payloads/headers containing PII, payment data, credentials, tokens, or partner info.
3. **Assess impact:** measure latency and log volume before/after enabling taps; inspect thread dumps, executors, queues, and collectors.
4. **Stop leaks:** disable unauthorized full-message logging; enforce allowlists and restrict access to already-exported logs per incident response procedures.
5. **Separate responsibilities:** best-effort debug/metrics go through bounded observation paths; mandatory audits use transactions/outboxes.
6. **Bound load:** configure bounded executors/buffers and tested overload policies; never hide errors by swallowing all exceptions.
7. **Reduce volume:** restrict taps to necessary channels, use controlled selectors/sampling, and avoid duplicate measurement points.
8. **Run regression tests:** synthetic sensitive data, schema changes, failing taps, restarts, and p95/p99 benchmarks.
9. **Monitor post-rollout:** watch queues, rejections, log ingestion, policy violations, and business latency.

Do not move every tap to async just because it "seems faster" while ignoring data-protection costs. Async is a load-dispatch choice; **data minimization** is the principle that controls what data leaves the boundary.

## 15. Lab Exercise: Diagnosing and Replacing a Tap in a Payment Flow

A payment API has this flow:

```text
paymentInput
  -> validate
  -> log(fullMessage)
  -> route(provider)
  -> call payment adapter
  -> reply Gateway
```

Under higher traffic, p99 increases; meanwhile logs contain `Authorization` and a payload token field. Perform the following:

1. Diagram the tap location and identify which handler/log appender can block the request thread.
2. Explain why `log(fullMessage)` is dangerous even when messages travel through the right channels.
3. Rewrite the `log` operator to record only the message ID or an allowlisted `TapObservation`.
4. Create a bounded `ExecutorChannel` for diagnostics; explicitly define behavior when the executor rejects tasks.
5. If payment auditing is mandatory, design a separate outbox and prove it does not depend on the diagnostic tap.
6. Use immutable DTOs for messages so tap handlers cannot mutate payloads used by the main Router/Transformer.
7. Test with synthetic `Authorization` headers and tokens; verify final serializer/logger output contains none of those values.
8. Benchmark with tap on vs. off, comparing business p95/p99 and tap queue depth.
9. Make the logger/collector slow and then fail; verify business and error flows follow chosen policies.
10. Add metrics for diagnostic drops/rejections, audit backlog, and alerts when logging policies change.

**Self-Assessment Questions**

- Why doesn't a Wire Tap run asynchronously by default just because it's called a "tap"?
- If the tap channel is a `DirectChannel` and its handler makes a slow HTTP call, which thread is blocked?
- Why doesn't an `ExecutorChannel` prove audit messages are durably stored?
- How should tap failures vs. business failures be represented distinctly?
- Why can logging just `message.toString()` expose more fields than expected?
- Why doesn't regex redaction replace allowlists and schema reviews?
- Why can a mutable payload cause races when two branches process in parallel?
- If a tap is attached to three channels, how can message-count metrics be misinterpreted?
- When an audit event is mandatory, which message-loss window does an outbox close?

## 16. References

- [Spring Integration Reference — Configuring Message Channels: Wire Tap](https://docs.spring.io/spring-integration/reference/channel/configuration.html): `ChannelInterceptor` mechanics, channel synchronicity, conditional/global wire taps, and target channel configuration.
- [Spring Integration Reference — Java DSL: Wire Tap](https://docs.spring.io/spring-integration/reference/dsl/java-wiretap.html): `wireTap()` operator and interceptor placement in flows.
- [Spring Integration Reference — Java DSL: Operator log()](https://docs.spring.io/spring-integration/reference/dsl/java-log.html): `log()`, `LoggingHandler`, and end-of-flow behavior since version 6.0.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): exception behavior in sync/async channels and `errorChannel`.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): channel types, dispatch, buffering, and sync boundaries.
- [Spring Framework Reference — Task Execution](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `ThreadPoolTaskExecutor`, queue limits, and thread pool management.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): practices to avoid logging secrets, sensitive data, and log controls.

> **Takeaway:** **A Wire Tap observes a flow; it must never silently slow down or copy all data from that flow.** Choose tap channels according to latency and reliability budgets; narrow attachment points and subjects, emit only allowlisted fields, bound executors/backpressure, and isolate mandatory audits into a durable mechanism. Finally, test both performance and the actual data leaving the application.
