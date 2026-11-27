# Masking Sensitive Payloads in Taps

**Chapter:** Wire tap  
**Lesson:** Masking Sensitive Payloads in Taps  
**Scope:** `SPRING_INTEGRATION_PATTERN` — using Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows; combining Wire Tap with Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, correlation, testing, and branch observation.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why **Wire Tap** is useful for observation yet can accidentally copy confidential data into logs, metrics, traces, queues, or monitoring systems.
2. Distinguish **observing the raw message** from **emitting data-minimized monitoring events**; recognize that Spring Integration's Wire Tap does not mask payloads automatically.
3. Design an **allowlist** for audit fields; avoid copying all headers or calling `Message.toString()`.
4. Implement a Spring Integration flow that builds a **safe audit event** before attaching `.wireTap()`, so the tap sees only selected information.
5. When tapping a raw channel is unavoidable, identify the proper trust zone, synchronous/asynchronous boundary, earliest sanitization point, and remaining risks.
6. Test indirect leak paths through exceptions, `errorChannel`, retries, DLQs, tracing, and serialization; verify that the primary business payload is never mutated.
7. Define retention, access control, metric label limits, and conditions under which dropping monitoring events is acceptable.

## 2. How Wire Tap Helps and Where the Risks Lie

In Enterprise Integration Patterns, **Wire Tap** copies the observable message stream to a secondary branch while the main branch continues doing its job. Spring Integration provides Wire Tap via the `WireTap` channel interceptor and convenient Java DSL declarations like `.wireTap("tapChannel")`.

~~~mermaid
flowchart LR
    A["Inbound adapter"] --> C["businessInput"]
    C --> B["Business handler"]
    B --> D["Business outcome"]
    C -. "Wire Tap" .-> T["tapChannel"]
    T --> O["Logging / metrics / audit"]
~~~

The tap branch helps investigate messages passing through stages, measure errors, compute throughput, and support correlation. The danger is that **the message entering the tap is usually the exact message the channel is handling**; `WireTap` itself does not act as a `Transformer` that strips secrets automatically.

A payment-processing message may contain:

- Payload: customer email, account details, payment tokens, address, notes, amount.
- Headers: `Authorization`, `Cookie`, `apiKey`, tracing metadata, user IDs, routing keys, or the `replyChannel` object.
- Error context: `MessagingException.getFailedMessage()`, exception messages, and stack traces can contain the original message or sensitive fields.

If the tap sends the raw message to a logging handler, that data risks appearing in log stores, observability systems, backups, and accounts with log-read access. A secure business processing flow **does not imply** the tap branch shares the same access controls and data retention rules.

## 3. Choosing Policies by Sensitivity Level

The starting point must be **the observation purpose**, and only then deciding which data fields actually need to travel.

| Data category | Examples | Default tap handling approach |
|---|---|---|
| Authentication secrets | Passwords, session cookies, JWTs, API keys, private keys | **Never forward into the tap branch**, even partially masked, unless explicitly approved for a specific purpose. |
| Payment data | Card numbers, security codes, account tokens, detailed transaction info | Never log raw; emit only minimal business signals compliant with data-protection policies. |
| Identifying data | Email, phone number, address, name, personal identifiers | Omit or use classified references with strict access control and retention. |
| Free-form payloads | JSON bodies, messages, CSV files, errors carrying request bodies | Never call `toString()` or dump full payloads; pick a few defined safe fields. |
| Technical metadata | Event type, schema version, outcome, latency bucket, logical endpoint name | Permissible after evaluating re-identification risk and cardinality. |
| IDs / correlation | `eventId`, `correlationId`, trace ID | **Not harmless by default**; can link back to individuals or transactions; consider surrogate references. |

For example, an observation need like "how many payments were processed, which error types are rising" usually requires only `operation=PAYMENT`, `outcome`, `errorCategory`, `durationBucket`, and timestamp. No copy of the entire `PaymentRequest` is needed.

**An allowlist is safer than a denylist.** If you only list forbidden fields (`password`, `token`), a newly added field such as `accessCredential` can slip into logs after the next schema change. With an allowlist, new fields are excluded from monitoring events by default.

## 4. Two Ways to Tap: Raw Message vs. Safe Event

### 4.1 Tapping the business message directly

~~~mermaid
flowchart LR
    R["PaymentRequest with secret"] --> C["businessChannel"]
    C --> H["Payment handler"]
    C -. "Wire Tap" .-> T["rawTap"]
    T --> X["Redact / mask"]
    X --> L["Audit logger"]
~~~

This is a common pattern when a tap is placed directly on a business channel. **Redacting in a handler after the tap does not undo the fact that the raw payload entered `rawTap`.** The path to that handler, `MessageChannel`, interceptors, thread queues, error flows, or intermediate debug logs can still see the sensitive data. If policy mandates that secrets never leave the primary processing zone, this model falls short.

### 4.2 Creating a safe event first, then tapping

~~~mermaid
flowchart LR
    R["PaymentRequest: sensitive data"] --> P["Business processor inside trust boundary"]
    P --> D["Business DB"]
    P --> M["Build allowlisted SafeAuditEvent"]
    M --> S["safeAuditInput"]
    S --> A["Audit sink"]
    S -. "Wire Tap sees only SafeAuditEvent" .-> T["Metrics / tracing"]
~~~

In this model, a component authorized to view the original data creates **a new, data-minimized object**. Only that new object enters `safeAuditInput`; Wire Tap is attached to the safe-event branch, so the raw payload never passes through the observation branch.

This fits well when log/metric writers or observability vendors have restricted access rights. It also clarifies that emitting an audit event is a **business decision**; Wire Tap merely copies the already-safe audit event to secondary consumers.

## 5. Java DSL: Preventing Leaks by Flow Design

Consider a `CheckoutCommand` request containing `customerEmail` and `accessToken` meant solely for the processing service. The tap branch must observe a separate `SafeAuditEvent`.

### 5.1 Defining data types

~~~java
public record CheckoutCommand(
        String eventId,
        String customerEmail,
        String accessToken,
        long amountInCents) {
}

// No email, token, account number, or free-form payload.
public record SafeAuditEvent(
        String operation,
        String outcome,
        String failureCategory) {
}
~~~

`SafeAuditEvent` uses **a small, predefined set of values**, avoiding placing arbitrary error strings that could echo input data into `failureCategory`. If per-request correlation is needed, use a reference code not directly derived from personal data and manage access/retention as linkable data.

### 5.2 Business flow producing filtered events

The snippet below illustrates Spring Integration Java DSL; standard imports are omitted and a `CheckoutService` is assumed to handle business logic. For simplicity, the example emits `CHECKOUT_COMPLETED` after the processing call succeeds.

~~~java
@Configuration
@EnableIntegration
public class SafeTapConfig {

    @Bean
    MessageChannel checkoutInput() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel safeAuditInput() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel safeTapMetrics(TaskExecutor auditExecutor) {
        return new ExecutorChannel(auditExecutor);
    }

    @Bean
    IntegrationFlow checkoutFlow(
            CheckoutService checkoutService,
            @Qualifier("safeAuditInput") MessageChannel auditInput) {

        return IntegrationFlow.from("checkoutInput")
                .handle(CheckoutCommand.class, (command, headers) -> {
                    checkoutService.process(command);

                    SafeAuditEvent safe = new SafeAuditEvent(
                            "CHECKOUT", "COMPLETED", "NONE");

                    // Send only SafeAuditEvent onto the audit channel.
                    auditInput.send(MessageBuilder.withPayload(safe).build());
                    return null;
                })
                .get();
    }

    @Bean
    IntegrationFlow auditFlow(SafeAuditRepository repository) {
        return IntegrationFlow.from("safeAuditInput")
                .wireTap("safeTapMetrics")
                .handle(SafeAuditEvent.class, (event, headers) -> {
                    repository.append(event);
                    return null;
                })
                .get();
    }

    @Bean
    IntegrationFlow auditMetricsFlow(AuditMetrics metrics) {
        return IntegrationFlow.from("safeTapMetrics")
                .handle(SafeAuditEvent.class, (event, headers) -> {
                    metrics.increment(event.operation(), event.outcome());
                    return null;
                })
                .get();
    }
}
~~~

The interfaces `CheckoutService`, `SafeAuditRepository`, `AuditMetrics`, and bean `auditExecutor` are application components to supply when running the example. `auditExecutor` should have bounded worker count, queue capacity, and an explicit rejection policy.

Checkpoints in this flow:

1. `checkoutInput` receives `CheckoutCommand`; **there is no Wire Tap on this channel**.
2. The handler processes sensitive data inside a component with appropriate privileges.
3. The handler constructs `SafeAuditEvent` containing only approved fields.
4. `.wireTap("safeTapMetrics")` is attached in the flow **whose input is already sanitized**; the metrics branch receives only `SafeAuditEvent`.
5. The main audit branch persists the safe record; the metrics branch uses an executor to offload work from the processing thread, while still needing to handle full queues and rejections.

**Limitation of this example:** the business action and audit write here are not shown as a single atomic transaction. If business processing commits and `auditInput.send()` fails, the state may be "business succeeded, audit missing". For mandatory auditing that cannot lose records, use a **transactional outbox** or a mechanism consistent with the business store. For best-effort telemetry, the error policy may allow metered drops. State this decision clearly before implementation.

### 5.3 Why not just use `WireTap` with a selector?

A `WireTap` can accept a `MessageSelector` to **choose which messages are forwarded to the tap**. A selector reduces message volume, but it does not transform the payload into a masked object.

For instance, a predicate selecting `operation=CHECKOUT` still forwards **the selected message** to the tap. If it holds a token, that token is still exposed. Sanitization must happen **before the observation step receives the message**, or the raw tap must stay strictly within a tightly controlled trust zone.

## 6. When You Must Observe the Raw Business Channel

Some systems require a hook on `businessChannel` to emit message-count metrics even if a downstream handler fails. If the hook cannot be moved, build a **custom `ChannelInterceptor` that creates a filtered monitoring message**, rather than using default `WireTap` to send the raw message.

~~~java
public final class SafeTelemetryInterceptor implements ChannelInterceptor {

    private final MessageChannel safeTelemetryChannel;

    public SafeTelemetryInterceptor(MessageChannel safeTelemetryChannel) {
        this.safeTelemetryChannel = safeTelemetryChannel;
    }

    @Override
    public Message<?> preSend(
            Message<?> original,
            MessageChannel sourceChannel) {

        // Never log original, headers, or original.toString().
        String kind = original.getPayload() instanceof CheckoutCommand
                ? "CHECKOUT"
                : "OTHER";

        SafeAuditEvent safe =
                new SafeAuditEvent(kind, "RECEIVED", "NONE");

        safeTelemetryChannel.send(
                MessageBuilder.withPayload(safe).build());

        return original; // Keep the business message intact.
    }
}
~~~

This is an **interceptor emulating Wire Tap's observation intent**, not standard `WireTap`. Key difference: it **never sends a copy of the raw message** to the telemetry branch; the new message carries only three safe fields.

You can attach this interceptor to the created `DirectChannel`:

~~~java
@Bean
DirectChannel guardedCheckoutChannel(
        @Qualifier("safeTelemetryChannel") MessageChannel telemetry) {

    DirectChannel channel = new DirectChannel();
    channel.addInterceptor(new SafeTelemetryInterceptor(telemetry));
    return channel;
}
~~~

Points to keep in mind:

- `preSend()` runs on the channel's send path; calling `send()` to telemetry can **block**, throw exceptions, or be rejected. For best-effort telemetry, handle failures deliberately without silently altering business state.
- Derive only **fixed event types**; never extract text from `original.toString()`, exception messages, or unverified headers.
- When auditing has legal compliance obligations, swallowing telemetry errors may be unacceptable; prefer durable writes in the same transaction or an outbox.
- Other interceptors on the same channel can still see the original message. **Access to the raw channel must be controlled**; a custom interceptor does not stop another logger configured on that channel.

### 6.1 Anti-patterns to avoid in code

~~~java
// ANTI-PATTERN — never use on messages containing sensitive data.
IntegrationFlow.from("checkoutInput")
        .wireTap("generalLogs") // Sends the original Message to the logs branch.
        .handle(checkoutService)
        .get();

// ANTI-PATTERN — copying all headers from a sensitive message.
Message<SafeAuditEvent> unsafeAudit =
        MessageBuilder.withPayload(new SafeAuditEvent(
                "CHECKOUT", "RECEIVED", "NONE"))
                .copyHeaders(originalMessage.getHeaders())
                .build();
~~~

The second snippet looks like it replaced the payload with a safe one, yet **all headers remain intact**: tokens, cookies, customer IDs, trace baggage, or custom values can enter telemetry. When creating `SafeAuditEvent`, build a **brand-new message without copying headers**, and add only reviewed metadata.

## 7. Data Minimization Differs from Masking a Few Characters

Three handling levels are commonly used, with very different risk profiles.

| Measure | Example | Limitations |
|---|---|---|
| **Omit** (drop field) | Do not emit `customerEmail` | Lowest risk when the field is unnecessary for observation goals. |
| **Redact** (replace with neutral placeholder) | `customerEmail = "[REDACTED]"` | Can still reveal field presence/type; error-prone across schema changes. |
| **Pseudonymize** (replace with linkable token) | Internal code / opaque audit reference | Still potentially linkable data; requires key, mapping, retention, and access management. |

If you only need throughput metrics, choose **omit**. If distinguishing transactions is required for investigations, use an **opaque reference** with restricted access that cannot be derived from emails or phone numbers. Plain hashing (`SHA-256(email)`) is insufficient to anonymize emails: input domains can be guessed and rainbow-matched. When stable pseudonyms are genuinely needed, consider keyed HMAC with securely managed keys or a separate mapping table per organizational policy.

**Masking does not equal absolute safety.** For example, keeping the last four digits of a phone number can be combined with other logs to re-identify individuals. Even `correlationId`, `orderId`, or `traceId` can link back to a customer, so include them in taps only when specifically required and after sensitivity review.

## 8. Headers, Exceptions, and Less Obvious Leak Paths

### 8.1 Headers

Spring Messaging headers can carry very useful metadata such as `MessageHeaders.ID`, `correlationId`, `replyChannel`, `errorChannel`, `contentType`, and custom headers. However:

- Client-supplied headers may hold secrets that the producer forwarded unintentionally.
- Headers like `Authorization` or `Cookie` must be treated as sensitive even when the payload is clean.
- `MessageBuilder.copyHeaders(...)` can reintroduce sensitive data into an audit message.
- `replyChannel`/`errorChannel` can contain internal infrastructure objects/addresses that should never be serialized externally.

Add only **allowlisted headers** to safe audit messages. You do not need to carry original technical headers into logs just to count messages.

### 8.2 Exceptions and failedMessage

Spring Integration can emit an `ErrorMessage` wrapping a `Throwable`. When the exception is a `MessagingException`, it may retain `getFailedMessage()`, the failing message including its payload and headers.

Consequently, the following actions can leak data even if the main tap flow is sanitized:

- Logging `log.error("{}", errorMessage)` or serializing the entire `ErrorMessage`.
- Logging exceptions alongside message objects without controlling how `toString()` renders fields.
- Forwarding the entire `failedMessage` to a shared DLQ/quarantine visible to operators unauthorized to read sensitive data.
- Adding payloads or identifying details to span attributes, trace baggage, or MDC.
- Logging partner responses that echo requests/tokens inside exception messages.

The error path should use an **error classifier** producing a `SafeErrorSignal` record containing only: logical endpoint name, predefined error category, retry state, timestamp, and an approved trace reference. If the raw message must be saved for recovery, store it in a **secure quarantine store with dedicated access control and retention**, never mixed with ordinary logs.

### 8.3 Retries, replay, and DLQ

Retries can cause the same message to be tapped multiple times. Therefore:

- Counting tapped messages is **different** from counting unique business events.
- A retry may recreate a Spring message with a new ID; deduplicating events requires a stable event key.
- DLQs or retry topics may retain copies of sensitive payloads longer than the primary store expects.
- Traces or metrics tagging `eventId` can create high cardinality and increase re-identification risks.

If you need to audit "how many unique transactions were processed", build an idempotent consumer for safe events or count from authorized business data.

## 9. Synchronous, Asynchronous, and Side-Branch Failures

A Wire Tap is a secondary branch by **purpose**; it is not asynchronous by **thread** by default.

| Tap channel | Typical behavior | Must be controlled |
|---|---|---|
| `DirectChannel` | Tap handler may run on the message-sending thread. | Latency, exceptions propagating to main flow, access scope. |
| `ExecutorChannel` | Hands tap processing to an executor. | Executor queue, rejections, worker count, error handler, shutdown. |
| `QueueChannel` | Holds messages for a poller to handle later. | Capacity, in-memory vs. persistent store, sensitive data sitting queued. |
| Outbound adapter/broker | Sends data to another system. | Header mapping, encryption, retention, auth, ACK/confirm, backups. |

Using `ExecutorChannel` for a tap reduces consumer latency impact, yet a full executor causes errors/rejections; an unbounded queue grows memory. Never treat having an async boundary as proof that logging is safe.

**Choosing by data nature:**

- **Best-effort telemetry:** explicitly define tolerable loss; use bounded executors, drop metrics, and control main-flow impact.
- **Mandatory auditing:** requires durable storage and proving completeness, ordering, and consistency per scope; consider transactional outbox or appropriate transactions rather than pure in-memory Wire Tap.
- **Debugging failures with raw payloads:** use an evidence store with restricted access, encryption, TTL, and formal access-grant workflows instead of sending raw payloads to general observability channels.

## 10. How Router, Filter, Transformer, Splitter, and Aggregator Affect Taps

### 10.1 Router and Filter

A Wire Tap before a Router observes messages that a Filter will drop or a Router will send elsewhere; a tap after a Router observes only the selected branch. If the goal is gathering statistics on rejection reasons, emit a **safe signal** with a `reasonCode` from a controlled value set rather than logging the entire rejected message.

### 10.2 Transformer

A Transformer can help create a minimal monitoring message, but verify it **does not inherit sensitive headers** from the input message. Being named "Transformer" does not guarantee sanitization, as transformers may copy existing metadata by default or custom logic.

Place sanitization at the **boundary entering the observation branch** and test actual payloads/headers after transformation. A `rawTap → Transformer → log` path still puts the raw message onto `rawTap`.

### 10.3 Splitter/Aggregator

A Splitter can generate multiple child messages, each with its payload and correlation/sequence headers. Placing a tap after a Splitter can duplicate confidential data across many records. An Aggregator stores message groups in a store, so if child messages hold sensitive data, that store must also be protected; a tap does not replace the group store's retention and access policies.

For branch statistics, use `segmentType`, `sequencePositionBucket`, or predefined outcomes; never emit raw payloads of individual segments.

### 10.4 Gateway and request–reply

A Gateway can set `replyChannel`, `errorChannel`, correlation, and request–reply headers. If tapping request/reply messages, secrets can appear **both outbound and inbound**, especially in error messages. Emit safe audit events from milestones—`REQUEST_STARTED`, `REQUEST_COMPLETED`, `REQUEST_TIMED_OUT`—with controlled reason codes rather than logging raw requests/responses.

## 11. Testing Without Leaking Payloads

A proper test must prove two things: **the tap receives no forbidden data** and **the business flow still receives the exact original message**.

### 11.1 Dedicated fixture for safe tap

Suppose `safeAuditInput` and `safeTapMetrics` are connected by `auditFlow`. In tests, use a `QueueChannel` in place of the metrics tap to actively receive messages, **without another consumer competing to read** in the same test fixture.

~~~java
@Configuration
@EnableIntegration
class SafeAuditTapTestConfig {

    @Bean
    MessageChannel safeAuditInput() {
        return new DirectChannel();
    }

    @Bean
    PollableChannel capturedTap() {
        return new QueueChannel(10);
    }

    @Bean
    IntegrationFlow auditedFlow() {
        return IntegrationFlow.from("safeAuditInput")
                .wireTap("capturedTap")
                .handle(SafeAuditEvent.class, (event, headers) -> null)
                .get();
    }
}
~~~

JUnit 5 test:

~~~java
@SpringJUnitConfig(SafeAuditTapTestConfig.class)
class SafeAuditTapTest {

    @Autowired
    @Qualifier("safeAuditInput")
    MessageChannel input;

    @Autowired
    @Qualifier("capturedTap")
    PollableChannel tap;

    @Test
    void tapOnlySeesAllowlistedAuditPayload() {
        // Sensitive strings used only in the test fixture,
        // never entering audit messages or production logs.
        String forbiddenEmail = "secret@example.invalid";
        String forbiddenToken = "test-token-never-log";

        SafeAuditEvent safe =
                new SafeAuditEvent("CHECKOUT", "COMPLETED", "NONE");

        assertTrue(input.send(
                MessageBuilder.withPayload(safe).build()));

        Message<?> observed = tap.receive(1_000);
        assertNotNull(observed);
        assertInstanceOf(SafeAuditEvent.class, observed.getPayload());

        String visible = observed.toString();
        assertFalse(visible.contains(forbiddenEmail));
        assertFalse(visible.contains(forbiddenToken));
        assertEquals("CHECKOUT",
                ((SafeAuditEvent) observed.getPayload()).operation());
    }
}
~~~

This example verifies payload type and absence of secret strings **inside the tap fixture**. It does not replace full integration testing of `checkoutFlow`, where a real `CheckoutCommand` must be sent and verified to reach the service intact inside the trust boundary while **no tap is attached to the raw channel**.

### 11.2 Other critical assertions

- The tap **does not** contain `Authorization`, `Cookie`, `accessToken`, `customerEmail`, or the raw payload in any field.
- Error flows never write raw `failedMessage` objects to logging sinks.
- After adding a `newSecret` field to a DTO, the safe audit schema **does not automatically include** the new field.
- Transformers and Header Enrichers never accidentally copy all headers from raw messages into `SafeAuditEvent`.
- When the audit sink fails, the business-flow policy is tested: rollback vs. best-effort must match the contract.
- Retries of the same event do not skew unique transaction counts; deduplication works when business rules require it.
- In tracing/metrics, no sensitive content appears in span attributes, log MDC, or high-cardinality labels.
- If storing evidence/quarantine records, access controls and retention on that store are tested separately.

**Testing note:** asserting on `toString()` is only a supplemental check. Stronger testing uses a fixed audit schema, verifies where Wire Tap is attached, audits the allowed header set, and inspects actual downstream sinks receiving data.

## 12. Error and Leakage Test Matrix

| Scenario | Trigger | Outcome to prove |
|---|---|---|
| Message with token | Send payload and headers containing dummy token | No raw token in tap, logs, metrics, or traces outside trust boundary. |
| Schema adds new field | Add a sensitive field to DTO | Audit allowlist does not expand automatically. |
| Transformer creates new message | Transform before tap branch | No secret headers copied; business payload not unintentionally altered. |
| Tap handler fails | Make metrics subscriber throw exception | Error-handling policy observed; no assumption that side branch never impacts main flow. |
| Executor full | Bound queue and apply load | No unbounded memory growth; rejected monitoring signals counted. |
| Business handler throws | Simulate DB or validation failure | `ErrorMessage`/exceptions do not leak `failedMessage` into logs. |
| Message redelivered | Resend the same business event | No double-counting if metrics track unique events. |
| Broker/DLQ receives failure | Induce serialization, timeout, or conversion failure | Raw data stays only in authorized quarantine store, never in general audit sink. |
| Gateway timeout | Drop connection or delay reply | Full request/reply not logged; normalized error category emitted. |
| Audit access control | Query using metrics-only account | Cannot read raw payloads or sensitive evidence. |

For diagnostics, track **audit events emitted**, **accepted by sink**, **rejected**, and **latency**. A system that logs no payloads yet drops critical audit records still fails its audit goals.

## 13. Operations: Retention, Access Control, and Cost

Tap safety does not depend solely on Java code:

- **Access control:** grant raw message access only to authorized responders; general dashboards and logs receive only safe events.
- **Retention:** define retention periods by purpose. Never keep sensitive payloads in logs indefinitely; enforce deletion/TTL and manage backups accordingly.
- **Encryption:** encrypt data in transit and at rest when sensitive data is present; govern keys and access.
- **Data lineage:** document data origins, which fields go to auditing, which sink stores them, who can access them, and when they are deleted.
- **Sampling:** reduces volume only; **does not protect secrets** if sampled messages still carry tokens.
- **Metrics cardinality:** never put `eventId`, email, or full URLs containing user data into metric labels; use bounded operation types and statuses.
- **Change audits:** every new header, interceptor, outbound adapter, or `.log()` on a raw channel must trigger a review of tap placement and safe field allowlists.

A simple policy table to keep alongside the design:

| Sink | Allowed | Not allowed |
|---|---|---|
| Metrics dashboard | Fixed-set operation name, outcome, error category | Email, token, per-transaction ID, arbitrary payload. |
| Standard application logs | Endpoint name, request class, duration bucket, approved trace reference | Raw message, all headers, exceptions containing request body. |
| Dedicated audit store | `SafeAuditEvent` and business-required metadata per policy | Wholesale copying of all fields "just in case". |
| Secure quarantine | Raw data only when truly needed for recovery, separately protected | Broad debug-log-style access; indefinite retention. |

## 14. Common Mistakes

1. **Treating `.wireTap()` as a data-masking function.** Wire Tap forwards messages to a secondary branch; it does not redact automatically.
2. **Redacting after a raw tap and believing data cannot leak.** The raw message already entered the tap channel, crossed interceptors/queues, and could enter error paths.
3. **Masking only the payload while forgetting headers.** Tokens or user data often live in metadata.
4. **Dumping `Message.toString()` or `ErrorMessage`.** Payloads, failed messages, or exceptions can be written to logs.
5. **Using field-name denylists.** New fields easily slip through if omitted from the blocklist.
6. **Hashing emails naively and treating them as anonymous.** Predictable input domains can be brute-forced; pseudonyms still require management as linkable data.
7. **Adding broad global interceptors without reviewing scope.** A `@GlobalChannelInterceptor` or logging handler may touch channels carrying raw data.
8. **Assuming async taps never affect flows.** Full executor queues, rejections, or shutdowns still require policies.
9. **Conflating best-effort telemetry with mandatory auditing.** Legal/compliance records require durability and explicit reconciliation.
10. **Ignoring retries and DLQs.** Sensitive data can be copied repeatedly or retained under a different system's retention schedule.
11. **Asserting only payload safety.** Traces, metrics, log MDC, headers, and error handlers are also leak channels.
12. **Using uncontrolled correlation IDs.** An identifier can still link back to a transaction or person even without names or emails.

## 15. Pre-Deployment Checklist

- [ ] Observability/audit goals are clearly defined; every field in the safe event has a documented purpose.
- [ ] No default `WireTap` sits on a raw channel holding secrets if the tap branch is unauthorized to see them.
- [ ] Safe events are constructed **before entering the tap channel**; payloads contain allowlisted fields only.
- [ ] Safe-event headers are created fresh or allowlisted; all original headers are never copied wholesale.
- [ ] Raw `Message`, `ErrorMessage`, `failedMessage`, or exception payloads are never logged.
- [ ] Error channels, retries, DLQs, Kafka/JMS/AMQP adapters, tracing, and metrics have been reviewed for leak risks.
- [ ] Clear policies selected for best-effort telemetry vs. mandatory auditing, with durable storage where needed.
- [ ] Bounded executor/queue, backpressure, and alerts exist for tap failures or rejections.
- [ ] Audit store has appropriate access controls, encryption, retention, deletion, and backup governance.
- [ ] Unit and integration tests use dummy secrets to catch leaks; real credentials are never used.
- [ ] Adding DTO fields, header mappers, or new interceptors triggers re-running privacy tests.
- [ ] Verified that the business flow still receives accurate payloads untouched by the observability branch.

## 16. Summary

Wire Tap is a valuable observation tool in Spring Integration, but **it has no built-in capability to mask sensitive data**. To prevent secret leaks, the clearest design is constructing an **allowlisted safe audit event before events enter a tapped channel**, sending only necessary metadata to logging/metrics/tracing. When a raw channel must be observed, establish a trust boundary and a custom interceptor that emits only safe signals, while governing any other interceptors capable of seeing raw data.

For production systems, test both payloads **and** headers, exceptions, error channels, retries/DLQs, transactions, async rejections, correlation, and retention. An observation branch is truly effective only when it provides sufficient evidence for investigation while keeping secrets strictly within authorized boundaries.
