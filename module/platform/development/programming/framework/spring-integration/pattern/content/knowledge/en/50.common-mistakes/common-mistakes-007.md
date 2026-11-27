# Discarding Messages Without an Audit

## 1. Common Mistake: Messages Disappear and Nobody Knows Why

In the **SPRING_INTEGRATION_PATTERN** module, Spring Integration helps structure message flows using Enterprise Integration Patterns (EIP): **Gateway** accepts requests, **Filter** evaluates conditions, **Transformer** transforms payloads, **Router** selects branches, **Splitter** splits work, **Aggregator** combines results, and **Service Activator** calls external systems. Components connect via channels so they can scale independently, yet a message being dropped mid-flow is often hard to notice without a recording policy.

For example, an order is submitted through a Gateway with a negative quantity. A Filter returns **false** to reject the message. If the flow does not define a **discard** path, the message can end right there with no business response or proper audit record. The user only sees the request time out; the operations team cannot tell whether the request was dropped by validation, a routing bug, or a dependency exception.

**Discard** is the decision not to continue processing a message on the main path. That can be completely legitimate, yet **discarding without an audit** robs the system of its ability to explain decisions, reconcile work counts, and investigate incidents.

Questions that must be answered:

1. Which message was dropped and at **which processing point**?
2. Was it dropped due to a **business rule**, no matching route, or **expiration**?
3. Was a legitimate duplicate message skipped?
4. Did the sender or parent workflow receive a **REJECTED / DROPPED / EXPIRED** outcome?
5. Are there sufficient **correlation IDs** and audit data to trace without exposing sensitive information?
6. If the audit system fails, is the business allowed to confirm the action as processed?

This lesson distinguishes **discard**, **error**, **fallback**, and **dead-letter**; designs a safe audit path; and illustrates Spring Integration Java DSL and testing methods.

~~~mermaid
flowchart TD
    A[Gateway / Inbound Adapter] --> B[Filter]
    B -->|Pass| C[Router / Service Activator]
    B -->|Reject| D[Discard branch]
    D --> E[Record audit with reason code]
    E --> F[Return REJECTED or handle per policy]
    C --> G[Main outcome]
    E -.-> H[Metrics / Trace]
    G -.-> H
~~~

**Not every discarded message is an incident.** For example, a Filter dropping an event outside a subscription is a normal decision. However, dropping a business command, an anomalous message, invalid data, or an expired Aggregator branch may require a durable audit trail. The level of recording must be governed by data policies and reconciliation requirements.

## 2. Distinguishing Discard, Exception, Dead-Letter, and Business Outcomes

| Situation | Meaning | Path to Consider |
| --- | --- | --- |
| Filter returns false | Message fails predicate | Discard channel, clear outcome, and audit if business-significant |
| Router finds no matching route | No valid branch determined | Default route, structured rejection, or fail fast |
| Valid data, duplicate | Not executed again due to idempotency | Record duplicate outcome if reconciliation needs it; no side effects |
| Aggregator group expires | Did not receive all parts | Expiry/timeout policy, partial/failed outcome, and group audit |
| Handler throws exception | Technical processing failure | Exception or `ErrorMessage`/error channel depending on boundary |
| Message unprocessable after retries | Exhausted attempt budget or unrecoverable | Dead-letter / parking lot with reason and replay capability |
| Message processed successfully | Completed under contract | Success outcome; not recorded as discard |

**Error channel is not the same as discard channel.** A Filter returning false is usually a normal branch and does not necessarily throw an exception; therefore, never assume a global error channel will capture every discarded message.

Conversely, an exception in a Service Activator is not an "intentional discard". Turning every technical failure into a rejected business outcome can mask dependency outages and cause circuit breakers, retries, and alerts to misbehave.

### When Is a Durable Audit Needed?

- Commands mutating business state such as placing an order, canceling an order, or recording a transaction.
- Messages not processed due to validation, authorization, invalid route, or expiration.
- Splitter/Aggregator branches losing results that require reconciliation.
- Events dropped as duplicates that still require proof of receipt and skip.
- Processes subject to traceability, auditing, or decision-explainability requirements.

For high-volume telemetry, such as an irrelevant event dropped per subscription contract, a **sampled counter/log** may suffice instead of a long-term record per event. Policy must state explicitly which categories are stored and for how long.

## 3. Common Silent Discard Points in Spring Integration

### 3.1. Filter Without a Discard Branch

A Filter only returns true/false; false cases are blocked from the main output path. Without configuring a discard channel or exception behavior, the caller may have no clear result indicating where the message went.

~~~java
// Anti-pattern: no branch recording rejected messages.
@Bean
public IntegrationFlow incomingOrders() {
    return IntegrationFlow.from("orders.requests")
            .filter(OrderCommand.class, command -> command.quantity() > 0)
            .handle(OrderCommand.class,
                    (command, headers) -> orderService.accept(command))
            .get();
}
~~~

If a synchronous Gateway expects a reply and the Filter rejects the message, the caller may wait for a reply until timeout. Depending on endpoint and channel configuration, rejection can be converted into an exception by setting **throwExceptionOnRejection**; however, throwing an exception is not automatically equivalent to a durable audit record.

### 3.2. Router With No Matching Branch

A Router receiving an event type with no mapping or fallback branch behaves according to settings such as **resolutionRequired** and **defaultOutputChannel**. If policy allows ignoring unroutable messages, a misrouted event becomes hard-to-investigate data loss.

A better approach is an **unknown-route outcome** or dedicated channel for unroutable messages, with a reason such as **NO_MATCHING_ROUTE**. Never enable ignoring routing errors just to quiet logs.

### 3.3. Expired Aggregator Groups

An Aggregator may hold messages by **correlation ID** until enough parts arrive or a completion strategy is satisfied. When a group expires, expiry/discard configuration can stop waiting messages from progressing.

Distinguish **completed groups**, **expired groups**, **partial results**, and **late-arriving messages**. Do not just inspect the Gateway's reply count and guess which group was lost.

### 3.4. Channels and Subscribers

A Publish-Subscribe Channel or endpoint configured without subscribers/handlers, or a flow ending with no remaining consumer, can leave messages failing to reach their intended destination; actual behavior depends on channel type and settings such as requiring subscribers, send timeouts, and error handling.

Do not treat every unreceived message as a Filter discard. Measure and classify **delivery/routing** errors separately. For critical messages, detect paths lacking consumers or send failures rather than silently dropping them.

### 3.5. Idempotent Receiver Dropping Duplicate Messages

Some flows intentionally drop duplicates to avoid repeating side effects. That is correct business behavior, yet enough audit info is still needed to answer: which event was accepted earlier, which key matched the duplicate, and what outcome was stored.

**Do not record full payloads for every duplicate**; record only the event key, reason code, timestamp, and a reference to the first processing record if policy allows.

## 4. An Inspectable and Traceable Discard Path

A simple design splits into two branches: the main branch handles only accepted messages, while the discard branch records the decision and returns a clear outcome to the caller.

~~~mermaid
flowchart LR
    A[Gateway: orders.requests] --> B{Filter quantity > 0}
    B -->|True| C[Order Service]
    B -->|False| D[orders.invalid]
    D --> E[Audit appendOnce]
    E --> F[REJECTED + reason code]
    C --> G[ACCEPTED / business outcome]
~~~

For a Filter validating **quantity > 0**, the **orders.invalid** branch can attach a fixed reason code **INVALID_QUANTITY**. If multiple distinct rules send to the same discard channel, identify the specific reason via a validation result, a header set in a trusted step, or separate channels by category. **A Filter does not automatically attach a business reason code** merely because its predicate returned false.

### Minimum Audit Contract

| Field | Purpose |
| --- | --- |
| **auditEventKey** | Unique decision key to prevent duplicate writes on redelivery |
| **correlationId** | Links the message to the original request/workflow |
| **originalMessageId** | Reference to the Spring Message if still available |
| **flowName / endpointName** | Identifies where the message was discarded |
| **reasonCode** | Structured value such as `INVALID_QUANTITY`, `NO_ROUTE`, `EXPIRED_GROUP` |
| **outcome** | `REJECTED`, `DROPPED_DUPLICATE`, `EXPIRED`, or contracted statuses |
| **occurredAt** | Timestamp when the decision was recorded |
| **tenantScope / operation** | Authenticated context with proper access scope |
| **schemaVersion** | Keeps audits readable as data models evolve |

**Payloads may contain personal data or secrets**, so never blindly dump entire messages into audits. Store minimal fields, apply masking/redaction, access control, retention periods, and deletion policies. If you must prove a payload was unaltered, use a digest or reference to a protected object, without replacing access control on raw data.

## 5. Spring Integration Java DSL Example: Audited Discard

The example shows a synchronous Gateway sending **OrderCommand**; a Filter routes invalid quantities to a dedicated channel; the handler on that channel **writes the audit before returning REJECTED**. The passing branch returns the outcome from **OrderService**.

### 5.1. Application Data Types

~~~java
public record OrderCommand(
        String commandId,
        String tenantId,
        int quantity
) {}

public record OrderDecision(
        String commandId,
        String outcome,
        String reasonCode
) {}

public record DiscardAuditEvent(
        String auditEventKey,
        String correlationId,
        String tenantScope,
        String flowName,
        String reasonCode,
        String outcome,
        Instant occurredAt
) {}

public interface OrderService {
    OrderDecision accept(OrderCommand command);
}

public interface DiscardAuditStore {
    // Persist durably and idempotently by auditEventKey.
    void appendOnce(DiscardAuditEvent event);
}
~~~

These records/interfaces are **application-defined types**, not provided out-of-the-box by Spring Integration. In the example, **tenantId** is assumed to be **authenticated at ingress** and propagated via a trusted context. In production, never take tenant directly from unverified client input as an audit or authorization key.

### 5.2. Gateway, Filter, and Discard Channel

~~~java
@MessagingGateway(defaultRequestChannel = "orders.requests")
public interface OrderGateway {
    OrderDecision submit(OrderCommand command);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
public class OrderFlowConfiguration {

    @Bean
    public IntegrationFlow ordersFlow(OrderService orderService) {
        return IntegrationFlow.from("orders.requests")
                .filter(
                        OrderCommand.class,
                        command -> command.quantity() > 0,
                        endpoint -> endpoint.discardChannel("orders.invalid")
                )
                .handle(
                        OrderCommand.class,
                        (command, headers) -> orderService.accept(command)
                )
                .get();
    }

    @Bean
    public IntegrationFlow invalidOrdersFlow(
            DiscardAuditStore auditStore,
            Clock clock
    ) {
        return IntegrationFlow.from("orders.invalid")
                .handle(OrderCommand.class, (command, headers) -> {
                    String correlation = String.valueOf(
                            headers.getOrDefault(
                                    "correlationId", command.commandId()));

                    String auditKey = command.tenantId()
                            + ":" + command.commandId()
                            + ":quantity-validation";

                    auditStore.appendOnce(new DiscardAuditEvent(
                            auditKey,
                            correlation,
                            command.tenantId(),
                            "orders.quantity-filter",
                            "INVALID_QUANTITY",
                            "REJECTED",
                            clock.instant()
                    ));

                    return new OrderDecision(
                            command.commandId(),
                            "REJECTED",
                            "INVALID_QUANTITY"
                    );
                })
                .get();
    }
}
~~~

Key points in the example:

1. **Filter passes**: the message goes to `OrderService`. This branch does not write a discard audit.
2. **Filter rejects**: the original message goes to **orders.invalid**; the handler receives it and creates an audit event with a fixed reason.
3. **appendOnce** must persist durably and deduplicate by business key. That is the storage adapter's contract, not an automatic feature from the method name alone.
4. Only after `appendOnce` completes does the handler return **OrderDecision(REJECTED)**; the synchronous Gateway receives the reply from the discard branch thanks to reply headers carried on the message.
5. If `auditStore` fails, the handler **does not return REJECTED as if the audit succeeded**. Exceptions must be handled according to failure policy.
6. In a real application, **OrderService** must also return valid outcomes; if multi-condition validation is needed, use a validator producing distinct reason codes rather than forcing all failures into `INVALID_QUANTITY`.

The example omits database and HTTP gateway implementations to focus on the discard and audit flow. Standard imports are omitted. When deploying in a real application, test end-to-end **request–reply**, transaction boundaries, and `auditStore` failure behavior against your Spring Integration version.

### Be Careful With Deduplication Keys

In the example, **auditEventKey** is bound to **commandId + tenant + validation step**, implicitly assuming the same `commandId` represents one logical command. If the application allows reusing `commandId` or has multiple independent processing attempts, include **workflowAttempt** or an appropriate decision identifier. Using only the **Spring Message ID** as a deduplication key is not sufficient in all cases, because broker redelivery or reconstructing a `Message` can generate a new Message ID.

## 6. When Auditing Fails: Fail Closed or Best Effort?

The audit path itself is a dependency that can fail. Decide upfront how mandatory each discard type is.

| Requirement Level | Behavior When Audit Fails | Example |
| --- | --- | --- |
| **Mandatory (compliance / reconciliation)** | Do not confirm decision was recorded; return technical error or write outbox inside transaction | Cancellation commands, critical financial requests |
| **Durable eventual audit** | Write durable outbox/queue then ACK; publisher writes to audit store later | Business event trail needing loss prevention |
| **Best effort** | Log/metric only; do not block main path when telemetry drops | Filtering technical events with no business impact |

If auditing is **mandatory**, never catch exceptions and stay silent:

~~~java
// Anti-pattern: reporting REJECTED even though the audit may not have been saved.
try {
    auditStore.appendOnce(event);
} catch (Exception ignored) {
    // Silent.
}
return new OrderDecision(commandId, "REJECTED", "INVALID_QUANTITY");
~~~

A reliable option is executing the business decision and **writing the audit/outbox within an appropriate transaction**. When writing to two independent systems without a cross-system atomic transaction, a crash window still exists; an outbox, eventual delivery, and idempotent consumer are needed.

**Wire Tap** can copy messages to an independent observation channel, which is very useful for diagnostics. However, an asynchronous wire tap alone cannot be treated as durable audit proof: it still depends on message delivery, consumers, queues, transactions, and storage writes succeeding.

## 7. Do Not Use Error Channel Instead of Discard Channel

In Spring Integration, a normal Filter rejection is not an exception. Therefore, creating a global error channel does not guarantee capturing messages dropped by a Filter.

~~~mermaid
flowchart TD
    A[Message arrives at Filter] --> B{Predicate}
    B -->|True| C[Main path]
    B -->|False| D[Discard channel]
    E[Handler throws exception] --> F[Error path]
    F --> G[ErrorMessage if boundary supports]
    D --> H[Discard audit]
    G --> I[Error audit / retry policy]
~~~

- **Discard audit** explains the decision to stop processing: at which step and by which rule the message was rejected.
- **Error handling** explains an unexpected processing failure or an explicitly thrown exception.
- **Dead-letter handling** explains a message unprocessable after retries, deadline expiration, or unrecoverable errors.

With a synchronous Gateway over a **DirectChannel**, exceptions can propagate to the caller. With asynchronous endpoints/pollers/adapters, exceptions can be wrapped into an **ErrorMessage** per error channel configuration. Do not assume all exceptions and discards travel through the same error flow.

If a Filter is configured with **throwExceptionOnRejection(true)**, a rejection becomes an exception; this can suit certain error contracts, yet **you still must ensure auditing if mandatory**, rather than relying solely on exception logs.

## 8. Router: Unmatched Routes Also Need an Explicit Decision

Suppose a Router handles **PAYMENT**, **STOCK**, and **SHIPPING** message types. When an unsupported event type arrives, a permissive configuration may drop it or fall back to a default output; a strict configuration may throw an exception. Decide based on contract rather than silence.

~~~mermaid
flowchart LR
    A[Router] -->|PAYMENT| B[Payment channel]
    A -->|STOCK| C[Stock channel]
    A -->|SHIPPING| D[Shipping channel]
    A -->|Unknown| E[Unroutable branch]
    E --> F[Audit: NO_MATCHING_ROUTE]
    F --> G[REJECTED / DLQ per policy]
~~~

The **Unroutable** path can handle:

- New event types where the consumer has not been upgraded yet.
- Invalid routing keys from a buggy Transformer or mapping.
- Tenants/regions lacking route configuration.
- Messages violating domain contracts.

Never automatically send all Unknown events into an arbitrary main branch. Audits should store **router name**, **normalized route key**, **message correlation**, and **reason code**, while avoiding logging entire sensitive payloads.

Additionally, measure **unroutable_total** per operation/flow; logging without alerting when the rate spikes lets misconfigurations persist unnoticed.

## 9. Aggregator: Discards Due to Timeouts, Duplicates, and Late Arrivals

An Aggregator typically gathers messages of the same **correlation group**. For instance, a Splitter splits an order into three branches: **stock**, **pricing**, and **shipping**. The Aggregator completes only when all three results arrive or a completion strategy permits a partial result.

If the stock branch does not reply because a circuit breaker is OPEN, the group may wait until its deadline. When the group expires, existing or late-arriving messages must be handled per **expiry policy**.

| Case | Audit Trail to Record |
| --- | --- |
| Group incomplete before deadline | `AGGREGATION_TIMEOUT`, correlation/group key, and missing branches |
| Group released partially | `PARTIAL_RELEASE`, list of present and missing branches |
| Late message after group expiry | `LATE_ARRIVAL`, expiry timestamp, and message branch |
| Duplicate branch reply | `DUPLICATE_PART`, duplicate event/branch key |
| Group completed normally | `COMPLETED` (not a discard), total valid branches |

In Spring Integration, an Aggregator can configure **group timeout, group expiry, discard channel**, and handling of messages arriving after group expiration; exact behavior depends on configuration and version. Do not assume setting a group timeout automatically produces audit records for every discarded message.

### Correlation and Sequence Headers

Splitters typically add correlation headers such as **CORRELATION_ID**, **SEQUENCE_NUMBER**, and **SEQUENCE_SIZE**. If a Transformer or fallback constructs a new `Message` without preserving required headers, the Aggregator may fail to group properly or time out.

An audit event for a discarded branch should include **correlation/group key, step name, sequence number, source event ID**, and outcome. In multi-tenant flows, prevent two messages with the same correlation string from different tenants from colliding.

**Never keep a synchronous Gateway waiting indefinitely** just because one branch failed to reply. Define partial/timeout/failure outcomes and a clear group cleanup policy.

## 10. Retries, Idempotency, and Non-Duplicate Audits

Messages may be re-sent by a broker, retry advice, or caller. A message rejected by a Filter on the first attempt may return and be rejected multiple times.

Distinguish two kinds of data:

- **Discard decision for one logical command:** you likely want **one audit decision** with a stable `auditEventKey`.
- **Each delivery/attempt:** you may need separate metrics/logs to investigate broker redelivery or retry loops.

Do not record every redelivery as a new business decision if it is the same logical command. At the same time, do not hide infinite retry loops: measure **delivery_attempts** or use sampled operational logging.

### Idempotency and Outbox Example

~~~text
Within the same transaction:

1. Check whether the message already has a decision by logical key.
2. If not, record business outcome = REJECTED.
3. Write discard audit or outbox event with a unique eventId.
4. Commit.

Publisher:
5. Emit outbox event to audit consumer.
6. If broker ACK is lost, may re-emit with the same eventId.
7. Audit consumer uses eventId for idempotent append.
~~~

This is a conceptual design, not SQL syntax. Only a **unique constraint** / idempotent write in storage guarantees a key does not record multiple decisions. A `ConcurrentHashMap` only protects inside a single live JVM and is insufficient across multiple pods or restarts.

For write operations with side effects, commands already processed before a lost reply must be reconciled; never re-execute business logic merely because the audit saw the message again.

## 11. Data Security in Audits

Auditing is not a license to copy whole messages into a long-lived log store. Especially in multi-tenant systems, messages may carry customer names, addresses, tokens, payment details, or private information.

Practical rules:

1. **Data minimization:** store only fields needed to explain the decision, such as reason code and authorized business references.
2. **Redaction:** never record secrets, access tokens, API keys, or payloads containing sensitive data unless covered by explicit policy.
3. **Access control:** personnel and applications may read audits only for tenants and workflows they are authorized for.
4. **Retention:** enforce TTLs, archival rules, and deletion per legal/business obligations.
5. **Integrity:** use tamper-resistant storage and audit access/changes when required.
6. **Cardinality:** never put order IDs, detailed tenant IDs, correlation IDs, or emails into metric tags.
7. **Separation of duties:** audit events are structured independently of business payloads; never rely on a single console log line as compliance evidence.

When storing security-sensitive or critical transaction data, coordinate with security/legal processes rather than inventing arbitrary retention rules.

## 12. Testing: Filter Rejection With Audit and Clear Reply

A discard test must not merely assert that the main handler was never called. It must verify **why the message was dropped**, **that the audit was recorded**, and **that the caller did not wait for a timeout**.

JUnit 5 + Mockito example in an integration test wired with **OrderGateway**, **OrderService**, and **DiscardAuditStore**. Assuming dependencies are injected as fakes/mocks, `appendOnce` is verified via mock:

~~~java
@Test
void invalidOrderIsAuditedAndReturnsRejected() {
    OrderCommand command =
            new OrderCommand("cmd-17", "tenant-a", -5);

    OrderDecision result = gateway.submit(command);

    assertEquals("REJECTED", result.outcome());
    assertEquals("INVALID_QUANTITY", result.reasonCode());
    assertEquals("cmd-17", result.commandId());

    verify(auditStore).appendOnce(argThat(event ->
            event.reasonCode().equals("INVALID_QUANTITY")
            && event.outcome().equals("REJECTED")
            && event.auditEventKey().contains("cmd-17")
    ));
    verifyNoInteractions(orderService);
}
~~~

This test requires a test fixture configuring the Gateway/`IntegrationFlow` and mock beans; it is not a standalone JUnit class runnable outside a Spring context.

### Essential Test Matrix

| Scenario | Expectation |
| --- | --- |
| Valid quantity | Runs main handler; no `INVALID_QUANTITY` audit written |
| Negative quantity | Filter rejects, writes exactly one decision, and returns `REJECTED` |
| Zero quantity | Matches validation contract; not silently dropped |
| Event type with no route | Produces `NO_MATCHING_ROUTE` outcome/audit |
| Audit store temporarily unavailable | Does not report audit written when write failed |
| Message redelivered by broker | Does not create duplicate decisions for the same `auditEventKey` |
| Same command ID but genuinely different attempt | Audit key properly distinguishes `workflowAttempt` |
| Router/Filter throws due to bug | Goes to error path; not disguised as a rejected business event |
| Aggregator missing branch | Timeout/partial outcome and group/branch audit |
| Late arrival after Aggregator expiry | Does not resurrect invalid group; late event trail recorded |
| Splitter emits multiple branches | Preserves correlation and sequence metadata on outcomes/discards |
| Synchronous Gateway receives discard | Clear reply or explicit exception; does not hang indefinitely |
| Asynchronous flow | `ErrorMessage` and discard paths are classified distinctly |
| Multiple pods writing same decision | Unique constraint / idempotent write prevents duplicates |
| Audit receives sensitive payload | Raw secrets/PII are not logged outside policy |

### Testing Audit Failures

Configure a fake `auditStore` to throw an exception on `appendOnce` and verify the Gateway receives a technical error or triggers a durable fallback per policy. Never write tests that only verify `REJECTED` is returned even when mandatory auditing failed; that encourages losing audit records.

### Testing Counter Observability

A metric **discard_total{flow,reason}** increments when a message is discarded. The metric may count every delivery, whereas the **audit decision store** may contain only one record per logical key. Tests should distinguish these two units instead of assuming metric counts always equal audit row counts.

## 13. Monitoring Discards in Production

| Signal | Purpose |
| --- | --- |
| **discard_total** by flow and reason | Detect abnormal spikes in rejections |
| **discard_to_input_ratio** | Proportion of incoming messages discarded |
| **audit_write_success/failure** | Know whether the audit system is healthy |
| **audit_queue_depth / oldest_age** | Detect backlogs when using an outbox |
| **unknown_route_total** | Spot version mismatches or missing router mappings |
| **aggregation_expired_total** | Groups missing replies or timing out |
| **duplicate_discard_total** | Detect excessive retries/redeliveries |
| **Gateway rejected/timeout rate** | Are callers getting clear outcomes or just timing out? |
| **ErrorMessage rate** | Distinguish technical exceptions from business discards |
| **correlation/trace ID in logs** | Trace a message across EIP components |

Alerts should be based on each flow's baseline. For example, a sudden spike in **INVALID_QUANTITY** may mean a new client is sending bad payloads; **NO_MATCHING_ROUTE** rising after deployment may indicate a version mismatch; **audit_write_failure** on a mandatory path requires urgent alerting because it affects reconciliation.

For metrics, use controlled-cardinality labels like **flow**, **stage**, **reasonCode**, **outcome**, and **tenant_group**. Never use individual `orderId` or `correlationId` values as tags, as that creates millions of time series. Detailed IDs belong in access-controlled logs and traces.

### Do Not Confuse Success Levels

A system may return HTTP 200 when skipping an unneeded event; that is **not** an error if it matches the contract. Conversely, a Gateway timing out because a Filter silently discarded a message is a symptom that the workflow lacks a proper response, even if no handler threw an exception.

Audit quality is measured by **explainability** and **reconcilability**: where a message entered, what decision was made, why, what outcome was returned, and whether it can be traced across components.

## 14. Mistakes to Avoid

1. **Filter returns false with no discard channel:** message is dropped and the caller never learns why.
2. **Enabling only an error channel expecting to catch all discards:** a normal rejection is not an exception.
3. **Sending messages to a discard channel with no handler:** moves where the message is lost without creating an audit.
4. **Auditing by logging verbatim payloads:** leaks data and lacks durability.
5. **Writing audits after returning a successful ACK:** crashes can lose the audit event.
6. **Lacking a stable audit key:** redelivery creates multiple business decision records.
7. **Using only each delivery's new `messageId` as the audit key:** fails to deduplicate logical commands.
8. **Using the same `reasonCode` for every validation:** hides which rule was actually violated.
9. **Confusing duplicate discards with upstream errors:** triggers unnecessary Retries or Circuit Breakers.
10. **Ignoring Aggregator group timeouts:** groups expire without outcomes or history.
11. **Dropping correlation when a Transformer builds a new message:** makes discarded branches hard to trace.
12. **Using best-effort wire taps for mandatory audits:** events can still be lost.
13. **Catching and swallowing audit failures:** callers falsely believe a trail was recorded.
14. **Retaining audits indefinitely:** storage, security, and retention policy risks.

## 15. Implementation Checklist

- [ ] Inventory all potential discard points: Filters, Routers, Aggregator expiry, duplicate handling, and unsubscribed channels.
- [ ] Every discard has a **reasonCode, flow/stage, correlation**, and clear outcome when required by business rules.
- [ ] Distinguish normal discards, technical errors, dead-letters, and fallbacks.
- [ ] On Filters, configure **discardChannel** or an exception policy; never leave Gateways hanging for ambiguous replies.
- [ ] Return a contracted rejection result or error; do not treat every discard as success.
- [ ] Record minimal audit fields; avoid unnecessary raw secrets/PII.
- [ ] When auditing is mandatory, use durable storage or a transactional outbox—never catch and ignore errors.
- [ ] Use a stable `auditEventKey` and idempotent writes to withstand redelivery.
- [ ] Enforce retention, access control, and lookup by correlation ID.
- [ ] With Splitter/Aggregator, preserve sequence headers and audit timeouts/late arrivals.
- [ ] Test main path, discard path, audit failures, duplicates, and Gateway request–reply.
- [ ] Monitor discard rates, audit write failures, unknown routes, and expired groups.
- [ ] Never let an important message be dropped without explainability and reconcilability.

**Discarding messages without an audit** is a design flaw that lets a system "run successfully" technically while losing the ability to prove what happened to a message. In Spring Integration, turn every rejection branch into **a decision with a reason, correlation, outcome, and appropriate audit level**. By combining Filter/Router/Aggregator with discard channels, durable storage, idempotency, error handling, and EIP observability, you can drop messages according to business rules while keeping full traceability, testability, and reconcilability.
