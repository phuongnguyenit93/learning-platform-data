# Avoiding Duplicate Deliveries to the Same Recipient

## 1. The Problem: Correct Fan-Out Without Duplicate Processing

In the **Recipient list** chapter of the **SPRING_INTEGRATION_PATTERN** module, we learn to implement Enterprise Integration Patterns with Spring Integration to create loosely coupled, extensible messaging flows. An event can be routed through a Router to multiple branches, then processed by Filters, Transformers, Gateways, or Service Activators. When retries, error channels, and correlation are added, controlling duplicates becomes essential so outcomes remain predictable and testable.

Suppose the system emits a **payment.completed** event to three recipients:

- **auditEventsChannel**: records the transaction in the audit ledger;
- **riskEventsChannel**: reviews high-value transactions;
- **notificationEventsChannel**: sends a customer notification when requested.

A single event reaching all three channels is **valid fan-out**, not duplication. Duplication is when **the same recipient** receives or executes **the same business effect for the same event** multiple times outside the contract.

For example, event **evt-501** must go once to audit and once to risk. If audit writes two records because the flow accidentally sends evt-501 to audit twice, or because the entire router was retried after the audit branch already succeeded, we have a duplication bug to solve.

After this lesson, you will be able to:

1. Distinguish **duplicate destinations in topology**, **duplicate messages during delivery**, and **duplicate business effects**.
2. Design a `RecipientListRouter` without declaring duplicate recipients across multiple conditions.
3. Build idempotency keys scoped accurately to **recipient + eventId** instead of arbitrarily using `MessageHeaders.ID`.
4. Understand why deduplicating before the router fails to recover partially failed branches.
5. Apply Idempotent Receiver, `MetadataStore`, transactions, and unique constraints at the right layers.
6. Test fan-out, retries, concurrency, dropped connections, and per-recipient duplicate handling.

## 2. Defining "Duplicate" Before Choosing a Solution

In Spring Integration, **`RecipientListRouter`** selects the list of channels that receive a message; each recipient can be an unconditional destination or have a selector. A message can be sent to multiple matching recipients. The router **does not replace an idempotent consumer**.

| Scenario | Is it a duplicate bug? | Explanation |
| --- | --- | --- |
| evt-501 goes to audit and risk once each | No | Two recipients with distinct responsibilities |
| evt-501 reaches audit twice because two paths converge | Likely | Same target receives the same event unexpectedly |
| evt-501 is resent after an error though audit already succeeded | Likely | Redelivery must be handled safely |
| evt-501 and evt-502 share paymentId but are two distinct events | Not necessarily | May be two valid state transitions |
| An event is redelivered but the handler skips the duplicate | Duplicate delivery, no duplicate effect | Idempotency mitigates side-effect risk |
| An event sends two emails because the user explicitly clicked resend | Depends on business rules | Distinguish a new operation from an old retry |

We will distinguish three layers:

**Layer 1 — Topology:** how many paths/recipients in the configuration actually lead to the same destination? This is solved by design and wiring tests.

**Layer 2 — Delivery:** can the same event reach a consumer multiple times? This involves retries, broker redeliveries, failovers, and operations.

**Layer 3 — Effect:** does the consumer produce duplicate business effects? This involves idempotency keys, transactions, database constraints, and target system APIs.

A resilient system must handle **all three**, rather than merely putting a `Set` on the router and calling the problem solved.

~~~mermaid
flowchart TD
    E["PaymentCompleted evt-501"] --> R["RecipientListRouter"]
    R --> A["Audit recipient"]
    R --> F["Risk recipient"]
    R --> N["Notification recipient"]
    A --> D1{"Already processed evt-501<br/>for audit?"}
    F --> D2{"Already processed evt-501<br/>for risk?"}
    N --> D3{"Already processed evt-501<br/>for notification?"}
    D1 -->|"No"| H1["Record audit"]
    D2 -->|"No"| H2["Create risk review"]
    D3 -->|"No"| H3["Send notification"]
    D1 -->|"Yes"| SK1["Skip safely"]
    D2 -->|"Yes"| SK2["Skip safely"]
    D3 -->|"Yes"| SK3["Skip safely"]
~~~

## 3. Common Causes of Duplicate Deliveries

### 3.1. Declaring the same destination multiple times

When a topology is generated from config files or multiple modules register recipients, the same channel name can appear more than once.

~~~java
// Illustrates a suspect configuration: audit is listed twice.
IntegrationFlow.from("paymentEventsChannel")
        .routeToRecipients(r -> r
                .recipient("auditEventsChannel")
                .recipient("riskEventsChannel")
                .recipient("auditEventsChannel"))
        .get();
~~~

Do not rely on assuming the framework automatically deduplicates all duplicate entries across every version, recipient type, and configuration style. **The application contract should forbid duplicate destination declarations** and include tests verifying the actual receiving channels.

If two modules both want to audit an event, determine whether they are genuinely **two distinct functions** or one recipient added twice. Two independent functions should have distinct **recipient identities** and channels; if they represent the exact same audit effect, there should be only one direct path.

### 3.2. Two selectors pointing to the same channel

Suppose audit needs the event when **the customer is VIP or the order is international**. Do not configure two separate recipients pointing to the same channel with two conditions and assume only one send will happen:

~~~java
// Prone to duplicate recipient configuration for auditChannel.
.routeToRecipients(r -> r
        .recipientMessageSelector("auditChannel",
                m -> isVip((OrderEvent) m.getPayload()))
        .recipientMessageSelector("auditChannel",
                m -> isInternational((OrderEvent) m.getPayload())))
~~~

Instead, **combine conditions per channel**:

~~~java
.routeToRecipients(r -> r
        .recipientMessageSelector("auditChannel", m -> {
            OrderEvent event = (OrderEvent) m.getPayload();
            return isVip(event) || isInternational(event);
        }))
~~~

Both snippets are **illustrative DSL fragments**, not standalone Java methods. The rule to preserve is: **one recipient identity, one clear condition definition**. If two branches need different side effects despite sharing the label "audit," give them separate names and contracts instead of merging them.

### 3.3. Two branches converging on the same handler

~~~mermaid
flowchart LR
    E["Event"] --> R["RecipientListRouter"]
    R --> A["auditChannel"]
    R --> B["otherChannel"]
    B --> T["Transformer / Router"]
    T --> A
    A --> H["Audit handler"]
~~~

In this topology, audit can receive the message **once directly** and **once indirectly through otherChannel**. Checking the immediate recipient list is not enough: inspect the **entire channel and endpoint graph**, especially with nested Routers, `PublishSubscribeChannel`s, and Gateways.

### 3.4. Retrying the entire fan-out after partial failure

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant R as RecipientListRouter
    participant A as Audit
    participant N as Notification
    P->>R: evt-501, attempt 1
    R->>A: evt-501
    A-->>R: Audit recorded
    R->>N: evt-501
    N--xR: Transient error
    R--xP: Exception
    P->>R: Retry evt-501
    R->>A: evt-501 again
    Note over A: Needs idempotent receiver
~~~

This is the most common cause in multi-destination integration systems. **Retrying the entire router** can repeat branches that already finished before the error occurred.

### 3.5. Redeliveries, multiple producers, and concurrency

Even when each recipient is configured only once, events can be re-emitted because:

- The producer retries after missing an acknowledgement.
- The broker redelivers after a consumer crashes before acking.
- A scheduler re-reads records not yet marked processed.
- Two instances process the same queue due to misconfigured locks/leases.
- Two concurrent requests generate the same business event.

**`DirectChannel`** does not deduplicate events automatically. **`ExecutorChannel`** and **`QueueChannel`** do not automatically guarantee exactly-once effects either. A channel is responsible for transporting messages, not deciding whether a business effect already happened.

## 4. Declaring Each Recipient Once in Java DSL

The following example illustrates routing with three clear targets: **audit** always receives, **risk** receives large transactions, and **notification** receives when the customer allows notifications.

### 4.1. Event Model and Conditions

~~~java
import java.math.BigDecimal;

record PaymentCompleted(
        String eventId,
        String paymentId,
        BigDecimal amountVnd,
        boolean notifyCustomer) {}

final class PaymentRoutingRules {
    private static final BigDecimal RISK_LIMIT =
            new BigDecimal("10000000");

    private PaymentRoutingRules() {}

    static boolean requiresRisk(PaymentCompleted event) {
        return event.amountVnd() != null
                && event.amountVnd().compareTo(RISK_LIMIT) >= 0;
    }
}
~~~

**`eventId`** is the stable identifier of **one logical event**, not a fresh ID on every broker redelivery. A single `paymentId` can have multiple events of different types; never use `paymentId` alone as the deduplication key for the entire payment history.

### 4.2. Flow Configuration

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class PaymentRecipientFlowConfig {

    @Bean
    MessageChannel paymentEventsChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel auditEventsChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel riskEventsChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel notificationEventsChannel() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow paymentRecipientsFlow() {
        return IntegrationFlow.from("paymentEventsChannel")
                .routeToRecipients(r -> r
                        // Each channel is registered exactly once.
                        .recipient("auditEventsChannel")
                        .recipientMessageSelector("riskEventsChannel", m ->
                                PaymentRoutingRules.requiresRisk(
                                        (PaymentCompleted) m.getPayload()))
                        .recipientMessageSelector(
                                "notificationEventsChannel", m ->
                                        ((PaymentCompleted) m.getPayload())
                                                .notifyCustomer()))
                .get();
    }
}
~~~

This flow intentionally **does not enable `applySequence`** because the three recipients process independently and do not need an Aggregator to combine results. **`applySequence=true`** creates metadata for grouping/sequencing, **not** a deduplication switch.

Similarly, **`ignoreSendFailures=true`** does not prevent duplicates; it can let the router continue to remaining branches when a synchronous send fails, yet it neither guarantees the failed branch gets processed nor catches all async errors. For mandatory audit, only use best-effort if corresponding recovery and observability mechanisms exist.

### 4.3. Distinguishing Producer and Recipients

The producer simply sends one event to **paymentEventsChannel**:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

PaymentCompleted completed = new PaymentCompleted(
        "evt-501",
        "payment-501",
        new BigDecimal("12500000"),
        true);

Message<PaymentCompleted> message = MessageBuilder
        .withPayload(completed)
        .setHeader("eventType", "payment.completed")
        .setHeader("businessCorrelationId", completed.paymentId())
        .build();

// paymentEventsChannel is a Spring-injected bean.
paymentEventsChannel.send(message);
~~~

For evt-501, **audit, risk, and notification** are all selected. That is three deliveries to **three different recipients**, not three duplicate records.

In production, validate inputs and `eventId`, never trusting client-supplied identifiers that could suppress someone else's side effects. An event ID must correspond to a real event; duplicate requests from the same source need their own idempotency rules.

## 5. Blocking Duplicates via Configuration and Topology

### 5.1. Normalizing the recipient list before passing it to the router

When channel lists are assembled from multiple configs, verify **each destination appears once** with an explicit check:

~~~java
import java.util.HashSet;
import java.util.List;
import java.util.Set;

final class RecipientConfigValidator {
    private RecipientConfigValidator() {}

    static void requireDistinct(List<String> channelNames) {
        Set<String> seen = new HashSet<>();
        for (String name : channelNames) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Recipient name is blank");
            }
            if (!seen.add(name)) {
                throw new IllegalArgumentException(
                        "Duplicate recipient declared: " + name);
            }
        }
    }
}
~~~

Example:

~~~java
List<String> destinations = List.of(
        "auditEventsChannel",
        "riskEventsChannel",
        "auditEventsChannel");

// Fail fast instead of silently using ambiguous configuration.
RecipientConfigValidator.requireDistinct(destinations);
// Throws IllegalArgumentException for auditEventsChannel.
~~~

**Fail fast** makes sense when duplicate destinations are always configuration bugs. If business rules genuinely need to **merge optional configurations**, use a `LinkedHashMap` keyed by **recipient identity** and combine multiple conditions into **one OR predicate**. Only merge entries when they genuinely represent the exact same business effect.

### 5.2. Overlapping conditions must not become two send commands

A single recipient may qualify for multiple reasons: VIP, international order, high priority. Express those reasons in **one selector** and log the selection reasons if needed:

~~~java
static boolean shouldAudit(OrderEvent event) {
    return isVip(event)
            || isInternational(event)
            || isPriority(event);
}
~~~

If you need to know which conditions matched, return a **`RoutingDecision`** object containing the set of reasons and the recipient identity; never add duplicate recipients just to record reasons.

### 5.3. Controlling dynamic recipient updates

`RecipientListRouter` supports runtime recipient management (e.g., via management APIs / Control Bus when configured). If an automated update process exists, **add recipient** operations must be idempotent by identity or reconciled against a **source of truth**. Re-sending the same update command must not alter the topology unexpectedly.

Never expose recipient modification APIs directly to untrusted sources. The channel list can be part of the security boundary: clients must not be able to add internal channels or remove auditing branches.

### 5.4. Inspect the entire graph, not just the input list

Beyond duplicate recipients in a single router, review:

- Do two different routes feed the same event into `auditChannel`?
- Does an intermediate `PublishSubscribeChannel` also subscribe the audit handler?
- Is a Retry Advice placed outside the entire fan-out rather than on the failing branch?
- Does another producer publish the same `eventId` into the flow again?
- Does a branch use a Gateway looping back into the router's own input?

**Seeing a channel name twice in a diagram is not automatically a bug**, yet if the same event triggers the same side effect multiple times unexpectedly, change the topology or add idempotent consumers.

## 6. What Should an Idempotency Key Represent?

An **Idempotent Receiver** is a consumer that can receive the same request multiple times without multiplying its **business side effects** beyond the contract. The most important requirement is choosing the right **identity for the unit of work**.

With a Recipient List, keys typically take the form:

~~~text
idempotencyKey = recipientId + ":" + eventId
~~~

Examples:

| Recipient | Event ID | Idempotency Key |
| --- | --- | --- |
| audit | evt-501 | audit:evt-501 |
| risk | evt-501 | risk:evt-501 |
| notification | evt-501 | notification:evt-501 |
| audit | evt-502 | audit:evt-502 |

A redelivery of **evt-501** to audit carries the same key **audit:evt-501** and can be skipped if audit already completed. However, **risk:evt-501** is a **separate** unit of work that may still need execution even after audit finished.

### 6.1. Why not deduplicate globally before the router?

Suppose on the first run: audit succeeded, risk failed. If an ingress gate records **`eventId=evt-501` already seen** and drops the entire event when the producer retries, risk will **never receive it again**.

~~~mermaid
flowchart TD
    A["Replay evt-501"] --> G{"Global dedup<br/>already seen evt-501?"}
    G -->|"Seen"| X["Drop everything"]
    X --> L["Risk unprocessed: dropped"]
    A --> D{"Per-recipient dedup"}
    D --> AU["Audit completed: skip"]
    D --> RI["Risk not completed: process"]
~~~

**Design rule:** when multiple recipients have independent processing states, deduplication must also be scoped **per recipient**. Ingress/producer deduplication is only suitable once all related work has been handed off to durable storage or per-branch tracking exists.

### 6.2. Distinguishing ID Types

| Field | Scope | Use for deduplication? |
| --- | --- | --- |
| **`MessageHeaders.ID`** | Technical ID of one Spring Message | Should not be used as the default business idempotency key |
| **`eventId`** | Stable identifier of one logical event | Usually a core component |
| **`paymentId`/`orderId`** | Business entity | Must combine with `eventType`/version if one entity has multiple events |
| **`correlationId`** | Links a message/workflow group | Does not guarantee an effect happens only once |
| **`sequenceNumber`/`sequenceSize`** | Supports grouping in Splitter/Aggregator | Does not prevent duplicate processing |
| **`recipientId`** | One specific processing responsibility | Combine with `eventId` to isolate per-branch state |
| **`attemptId`** | One delivery/processing attempt | Never replaces `eventId` since retries get new attempt IDs |

Never generate a **new `eventId`** when retrying an old event. Conversely, two genuinely distinct business requests must have distinct identities; if they share a key, deduplication can mistakenly drop a valid operation.

### 6.3. Keys must come from a trusted source

If a client can arbitrarily pick an `eventId` matching someone else's ID, it can cause valid requests to be marked as duplicates. Therefore, the producer must authenticate requests, assign durable identifiers from verified domain data, or use contract-managed server event IDs.

Never print keys containing secrets into logs. When sharing one idempotency store across multiple tenants, include a **trusted `tenantId`** in the key scope if `eventId` is not guaranteed globally unique across tenants.

## 7. Simple In-Memory Deduplication Example

The following example shows an **atomic in-JVM** duplicate check using a concurrent `Set`. This is an educational model for understanding per-recipient scoping, **not a production solution guaranteeing zero data loss**.

~~~java
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

final class InMemoryRecipientGate {
    private final Set<String> seen =
            ConcurrentHashMap.newKeySet();

    boolean firstTime(String recipientId, String eventId) {
        Objects.requireNonNull(recipientId, "recipientId");
        Objects.requireNonNull(eventId, "eventId");
        if (recipientId.isBlank() || eventId.isBlank()) {
            throw new IllegalArgumentException("Missing identifier");
        }
        return seen.add(recipientId + ":" + eventId);
    }
}
~~~

~~~java
InMemoryRecipientGate gate = new InMemoryRecipientGate();

assert gate.firstTime("audit", "evt-501");
assert !gate.firstTime("audit", "evt-501");
assert gate.firstTime("risk", "evt-501");
~~~

**Advantage:** `ConcurrentHashMap`'s `Set.add` is atomic within one JVM; if multiple threads contend for the same key, only one call gets `true`.

**Severe limitations:**

1. **Restarts:** the `Set` loses all state, so replays can reprocess.
2. **Multiple instances:** each instance has its own `Set`, providing no cluster-wide deduplication.
3. **Marking too early:** `firstTime()` inserts the key **before the effect finishes**. If the handler throws after inserting the key, retries may be blocked even though the task never succeeded.
4. **No cleanup:** the `Set` grows unboundedly without a retention policy.
5. **No transactions:** the idempotency key and DB/HTTP effects do not commit atomically.

Therefore, use this `Set` only in unit tests or local simulations. Never interpret it as exactly-once delivery.

## 8. Preventing Duplicate Database Effects with Transactions

When a recipient writes to a single database, you can protect it with **unique constraints** and **transactions** so the processed marker and side effect commit together.

PostgreSQL example:

~~~sql
CREATE TABLE recipient_delivery (
    recipient_id VARCHAR(80) NOT NULL,
    event_id VARCHAR(120) NOT NULL,
    status VARCHAR(24) NOT NULL,
    completed_at TIMESTAMPTZ NULL,
    PRIMARY KEY (recipient_id, event_id)
);

CREATE TABLE audit_entry (
    id BIGSERIAL PRIMARY KEY,
    event_id VARCHAR(120) NOT NULL UNIQUE,
    payment_id VARCHAR(120) NOT NULL,
    amount_vnd NUMERIC(18, 2) NOT NULL
);
~~~

Service-layer code:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class TransactionalAuditConsumer {
    private final DeliveryRepository deliveries;
    private final AuditRepository audits;

    TransactionalAuditConsumer(
            DeliveryRepository deliveries,
            AuditRepository audits) {
        this.deliveries = deliveries;
        this.audits = audits;
    }

    @Transactional
    public void onCompleted(PaymentCompleted event) {
        // INSERT ... ON CONFLICT DO NOTHING.
        // Returns 1 if a new key was inserted, 0 if the key already existed.
        int acquired = deliveries.tryInsert(
                "audit", event.eventId(), "PROCESSING");
        if (acquired == 0) {
            return; // Already processed or another attempt holds the key.
        }

        audits.insert(event.eventId(),
                event.paymentId(), event.amountVnd());
        deliveries.markCompleted(
                "audit", event.eventId());
    }
}

interface DeliveryRepository {
    int tryInsert(String recipientId, String eventId, String status);
    void markCompleted(String recipientId, String eventId);
}

interface AuditRepository {
    void insert(String eventId,
                String paymentId,
                java.math.BigDecimal amountVnd);
}
~~~

This is an **application pattern**: the two repositories must be implemented, and the example assumes they share **the same transaction manager and database**. Inside that transaction:

1. The first attempt successfully inserts the `recipient + eventId` key.
2. The audit effect is created and marked completed.
3. If an operation throws and rolls back the transaction, **neither the processing key nor the audit effect** commits.
4. Another attempt with the same key is serialized/blocked by the unique constraint and transaction isolation, preventing duplicate records after a successful commit.

Never use a non-atomic "SELECT if key exists → if not then INSERT" check against two competing threads. Use unique constraints or CAS/`putIfAbsent` with explicit concurrency semantics.

### 8.1. What when the effect is outside the database?

If notification sends an email/HTTP call and then writes `completed` to the database, sending the email **does not roll back** if the DB transaction rolls back. Conversely, marking `completed` before sending the email risks never sending the email if the process crashes.

For external services, consider:

- **Outbox**: write the intent to perform the task into the DB within the business transaction.
- **Worker/consumer**: read the outbox, perform bounded retries, and manage state.
- **Target-side idempotency key** if the API supports it, e.g., `eventId + recipientId`.
- **Reconciliation** when it is impossible to tell whether the effect occurred.
- **DLQ/quarantine** for messages that failed repeatedly.

Never promise exactly-once effects to external systems solely because you have a `recipient_delivery` table. When external APIs lack idempotency support, you may have to accept at-least-once delivery, add reconciliation, or design business logic that tolerates duplicates.

## 9. Idempotent Receiver in Spring Integration

Spring Integration provides **`IdempotentReceiverInterceptor`** to apply the **Idempotent Receiver** pattern on endpoints, and **`MetadataStoreSelector`** to determine whether a message's key already exists in a metadata store.

Important: **`IdempotentReceiverInterceptor` does not automatically drop all duplicates by default**. When the selector rejects a message, the interceptor can attach header **`duplicateMessage=true`** and still pass it to the handler; to drop or divert duplicates, configure a discard channel or the corresponding rejection mode.

### 9.1. Metadata Check Mechanism

~~~mermaid
flowchart TD
    M["Message arrives at a recipient"] --> K["Compute idempotency key"]
    K --> S{"MetadataStoreSelector<br/>key exists?"}
    S -->|"No"| H["Handler processes"]
    S -->|"Yes"| D["Mark duplicate or discard<br/>per configuration"]
    H --> X["Effect / transaction"]
~~~

`MetadataStoreSelector` typically relies on **`putIfAbsent`** on a **`ConcurrentMetadataStore`**. This handles concurrent races at the key-claim step when the store provides atomic semantics.

The default **`SimpleMetadataStore`** is local in-memory and does not survive restarts. With multiple instances or restart durability requirements, consider `JdbcMetadataStore`, `RedisMetadataStore`, or a suitable distributed/persistent store; verify consistency, TTL, and key retention.

### 9.2. Example Using MetadataStoreSelector at an Endpoint

The following example focuses on **per-recipient deduplication**. The key must be scoped to the audit recipient, rather than a global key that accidentally blocks other recipients.

~~~java
import org.springframework.integration.selector.MetadataStoreSelector;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.integration.handler.advice.IdempotentReceiverInterceptor;
import org.springframework.messaging.Message;

// concurrentMetadataStore must be an appropriately configured bean/store.
MetadataStoreSelector selector = new MetadataStoreSelector(
        (Message<?> message) -> {
            PaymentCompleted event =
                    (PaymentCompleted) message.getPayload();
            return "audit:" + event.eventId();
        },
        concurrentMetadataStore);

IdempotentReceiverInterceptor advice =
        new IdempotentReceiverInterceptor(selector);
advice.setDiscardChannel(nullChannel);

// Attach advice to the audit-handling endpoint, not globally
// at the router input if recipients must complete independently.
~~~

This is an **illustrative configuration snippet**, assuming `concurrentMetadataStore` and `nullChannel` exist, and the advice still needs to be attached to the target endpoint per your Spring Integration version's API. It is not a standalone program.

If discard or rejection is not configured, check whether the handler reads **`duplicateMessage`** and decides for itself whether to perform side effects. With **`setDiscardChannel(nullChannel)`**, duplicates are intentionally dropped; add metrics counting discards rather than pretending "the event was never redelivered."

**Business warning:** `MetadataStoreSelector` can claim the key **before the effect succeeds**. If the handler fails after claiming, retries can be treated as duplicates. This is a critical choice between **at-most-once attempt** and **at-least-once recovery**. In flows with mandatory side effects, prefer explicit processing state and transactions, or design contractual claim rollback/release/TTL—never add an interceptor and assume you have exactly-once semantics.

### 9.3. Should deduplication be before or after RecipientListRouter?

| Placement | Benefit | Risk |
| --- | --- | --- |
| Before router | Reduces duplicate message processing across all branches | Can eliminate recovery chances for a previously failed branch |
| After router, at each recipient | Tracks individual task state separately | Must manage keys and stores per recipient |
| At database/side-effect boundary | Protects business effects right where they happen | Requires transactions/constraints or idempotent APIs |
| Both ingress and each recipient | Can optimize cost while staying safe if designed well | Must distinguish "received" from "all branches completed" |

**Usually safer choice:** define deduplication/idempotency **at each recipient** and where side effects occur; optional ingress deduplication should only be used when durable distribution guarantees the event was already handed off to every branch.

## 10. Designing Retries Without Accidental Duplicates

Before adding Retry Advice, ask: **what is being retried?** The entire message sent to the router, just the risk branch, an HTTP call inside one handler, or a database transaction?

| Retry Scope | Impact | Duplication Risk |
| --- | --- | --- |
| Producer resends to router | Router re-selects recipients from scratch | Already-succeeded branches may be invoked again |
| Retry around entire router | Entire fan-out can rerun | Partial successes get repeated |
| Retry on notification handler alone | Only notification task retries | Minimal impact on audit/risk; notification still needs idempotency |
| Broker redelivery to one recipient queue | That recipient may receive the event again | Protected at consumer with proper acking |
| Retry database operation in transaction | Rolls back and retries | Protected by unique constraints and commit boundaries |

### 10.1. One branch succeeds, one branch fails

For mandatory audit and potentially slow notification:

1. Producer writes **payment.completed** and an outbox event in the same transaction if events must survive restarts.
2. A dispatcher creates tasks per recipient or publishes to durable messaging infrastructure per contract.
3. **audit** and **notification** maintain separate progress, idempotency keys, and retry policies.
4. When notification fails, only the notification message/task needs to retry; completed audit does not re-execute its effect.

~~~mermaid
flowchart LR
    O["Transactional outbox"] --> D["Dispatcher"]
    D --> A["Audit queue"]
    D --> N["Notification queue"]
    A --> AC["Audit consumer<br/>dedup audit:evt"]
    N --> NC["Notification consumer<br/>dedup notification:evt"]
    NC -->|"Transient failure"| RT["Retry + backoff"]
    RT --> NC
~~~

This is an **architectural approach**, not a claim that configuring `RecipientListRouter` alone creates an outbox, durable queues, acks, or DLQs. You must implement or configure the underlying infrastructure.

### 10.2. `ignoreSendFailures` does not replace per-recipient retries

In `RecipientListRouter`, **`ignoreSendFailures(true)`** can allow continuing to other recipients when a synchronous send fails. That helps some best-effort flows, yet it **does not** guarantee the failed branch gets retried. On the contrary, it can hide failures in critical branches from callers unless monitored.

With asynchronous channels, `send()` succeeding does not prove downstream processing succeeded. Dedicated error handling is needed on workers, pollers, or adapters.

### 10.3. `applySequence` and Aggregator do not automatically deduplicate

When **`applySequence(true)`** is enabled, the router generates correlation/sequence metadata on messages sent to recipients, useful when a downstream Aggregator gathers results. However:

- Re-sending the same event twice can create **two distribution groups** with different correlations or produce duplicate results, depending on the pipeline.
- The Aggregator still needs an explicit release strategy, message store, timeouts, and duplicate/missing-result policies.
- **`sequenceNumber`** describes position in a set, not a system-wide idempotency key.

Never treat `applySequence` as a deduplication switch. When combining results, design **business correlation**, **recipient identity**, **attempt identity**, and completion conditions.

## 11. Testing Fan-Out: Once per Single Send

A test should prove two things:

1. **One `send()`** with an event selects the **exact recipient set** without selecting extra recipients in the current topology.
2. **Two `send()` calls** with the same event can produce **two deliveries** without deduplication—behavior that consumers must guard against.

The example below uses **`QueueChannel`** targets to pull messages with `receive(0)` without fake Service Activators or thread sleeps. Channels are test-only and provide no durable storage.

### 11.1. Integration Test with Spring Context

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(RecipientDeliveryTest.Config.class)
class RecipientDeliveryTest {

    @Configuration
    @EnableIntegration
    static class Config {
        @Bean
        MessageChannel testInput() {
            return new DirectChannel();
        }

        @Bean
        QueueChannel testAudit() {
            return new QueueChannel();
        }

        @Bean
        QueueChannel testRisk() {
            return new QueueChannel();
        }

        @Bean
        QueueChannel testNotification() {
            return new QueueChannel();
        }

        @Bean
        IntegrationFlow recipientFlow() {
            return IntegrationFlow.from("testInput")
                    .routeToRecipients(r -> r
                            .recipient("testAudit")
                            .recipientMessageSelector("testRisk", m ->
                                    PaymentRoutingRules.requiresRisk(
                                            (PaymentCompleted) m.getPayload()))
                            .recipientMessageSelector("testNotification", m ->
                                    ((PaymentCompleted) m.getPayload())
                                            .notifyCustomer()))
                    .get();
        }
    }

    @Autowired
    @Qualifier("testInput")
    MessageChannel input;

    @Autowired
    @Qualifier("testAudit")
    QueueChannel audit;

    @Autowired
    @Qualifier("testRisk")
    QueueChannel risk;

    @Autowired
    @Qualifier("testNotification")
    QueueChannel notification;

    @Test
    void oneSendReachesEachMatchingRecipientOnce() {
        PaymentCompleted event = new PaymentCompleted(
                "evt-801", "pay-801",
                new BigDecimal("15000000"), true);

        assertTrue(input.send(MessageBuilder
                .withPayload(event).build()));

        assertNotNull(audit.receive(0));
        assertNotNull(risk.receive(0));
        assertNotNull(notification.receive(0));

        // No second message in the same send.
        assertNull(audit.receive(0));
        assertNull(risk.receive(0));
        assertNull(notification.receive(0));
    }

    @Test
    void lowAmountWithoutNotificationOnlyReachesAudit() {
        PaymentCompleted event = new PaymentCompleted(
                "evt-802", "pay-802",
                new BigDecimal("100000"), false);

        assertTrue(input.send(MessageBuilder
                .withPayload(event).build()));

        assertEquals("evt-802",
                ((PaymentCompleted) audit.receive(0)
                        .getPayload()).eventId());
        assertNull(audit.receive(0));
        assertNull(risk.receive(0));
        assertNull(notification.receive(0));
    }

    @Test
    void replayIsNotDeduplicatedByRecipientListRouter() {
        PaymentCompleted event = new PaymentCompleted(
                "evt-803", "pay-803",
                new BigDecimal("100000"), false);
        Message<PaymentCompleted> message =
                MessageBuilder.withPayload(event).build();

        assertTrue(input.send(message));
        assertTrue(input.send(message)); // Redelivery of the same event.

        assertNotNull(audit.receive(0));
        assertNotNull(audit.receive(0));
        assertNull(audit.receive(0));
    }
}
~~~

Each test uses a distinct event and drains all messages from relevant channels. With parallel tests or broader shared Spring contexts, isolate contexts/test fixtures to avoid leftover queue messages from other tests. Do not use this test to draw conclusions about broker acks, restarts, or exactly-once effects.

### 11.2. Unit Test for Duplicate Config Validator

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import org.junit.jupiter.api.Test;

class RecipientConfigValidatorTest {
    @Test
    void rejectsDuplicateChannelNames() {
        assertThrows(IllegalArgumentException.class,
                () -> RecipientConfigValidator.requireDistinct(
                        List.of("audit", "risk", "audit")));
    }

    @Test
    void acceptsUniqueRecipientNames() {
        assertDoesNotThrow(() ->
                RecipientConfigValidator.requireDistinct(
                        List.of("audit", "risk", "notification")));
    }
}
~~~

This test catches duplicate declarations **before** the topology runs. It does not replace integration tests because two differently named channels can still lead to the same handler or business effect.

## 12. Testing Per-Recipient Idempotency

### 12.1. Same event, different recipients

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class RecipientGateTest {
    @Test
    void sameEventIsUniquePerRecipient() {
        InMemoryRecipientGate gate = new InMemoryRecipientGate();

        assertTrue(gate.firstTime("audit", "evt-901"));
        assertFalse(gate.firstTime("audit", "evt-901"));

        // Risk is allowed to process the same event because it is a different recipient.
        assertTrue(gate.firstTime("risk", "evt-901"));
        assertFalse(gate.firstTime("risk", "evt-901"));

        // A different event must also be processed.
        assertTrue(gate.firstTime("audit", "evt-902"));
    }
}
~~~

### 12.2. Two threads claiming the same key

For a concurrent `Set` within **one JVM**, test contention:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import org.junit.jupiter.api.Test;

class ConcurrentRecipientGateTest {

    @Test
    void onlyOneThreadClaimsTheSameKey() throws Exception {
        InMemoryRecipientGate gate = new InMemoryRecipientGate();
        ExecutorService pool = Executors.newFixedThreadPool(8);
        CountDownLatch start = new CountDownLatch(1);

        try {
            List<Future<Boolean>> results = new ArrayList<>();
            Callable<Boolean> work = () -> {
                start.await();
                return gate.firstTime("audit", "evt-903");
            };

            for (int i = 0; i < 8; i++) {
                results.add(pool.submit(work));
            }

            start.countDown();
            int firstClaims = 0;
            for (Future<Boolean> result : results) {
                if (result.get()) {
                    firstClaims++;
                }
            }

            assertEquals(1, firstClaims);
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

This test only proves claiming is atomic within **one JVM**. To verify multi-instance systems, test with a **shared store**, crashes/restarts, and business-effect transactions. Never extrapolate from a simple concurrency test that the whole system achieves exactly-once semantics.

### 12.3. Testing mid-way failures

A valuable test for services with side effects:

1. Send **evt-904** to audit.
2. Intentionally throw an exception **after claiming the key but before committing the audit entry**.
3. Retry the same `evt-904`.
4. **Expectation:** the retry can still complete the audit entry because the first transaction rolled back both the key and the effect.

With `InMemoryRecipientGate` marking `firstTime` before processing, this test **will fail**: the retry gets rejected. That demonstrates why a standalone `Set` or `MetadataStoreSelector` cannot replace business transactions.

### 12.4. Testing failures after external side effects

Simulate the notification service **sending an email but losing the response**. On retry:

- If the target service's API supports idempotency keys, it should receive **the same key** for the same event/recipient and avoid sending again.
- If the target service lacks support, record an **UNKNOWN** state and use reconciliation or an explicit duplicate-tolerant business policy, rather than claiming the email definitely was not sent.
- Monitor retry counts, duplicates detected, and final outcomes.

## 13. Monitoring: Distinguishing Valid Retries from Duplicate Bugs

| Signal | Meaning |
| --- | --- |
| **`recipient_delivery_attempts_total{recipient}`** | Send attempts to recipient |
| **`recipient_delivery_completed_total{recipient}`** | Tasks marked completed |
| **`recipient_duplicate_skipped_total{recipient}`** | Duplicates skipped by consumer |
| **`recipient_delivery_failed_total{recipient,reason}`** | Failures at a recipient |
| **`recipient_retry_total{recipient}`** | Retry rate per branch |
| **`recipient_backlog_age_seconds{recipient}`** | Age of waiting messages |
| **`recipient_unmatched_total`** | Events matching zero recipients |
| **`recipient_config_duplicate_detected_total`** | Signal of duplicate destination configuration |

Never use high-cardinality `eventId`, `paymentId`, or `tenantId` as metric labels. Those IDs belong in redacted logs/traces, whereas metrics should use bounded-cardinality labels like recipient and error reason.

### 13.1. Operational questions to answer

- How many times did event **evt-501** enter the router?
- Which recipients were selected for that event on each attempt?
- Did the audit branch **receive**, **claim**, **commit the effect**, or merely schedule it?
- If the notification branch fails, does the retry reach only the unfinished branch?
- How many duplicates were skipped **per policy** versus how many duplicate effects actually occurred?
- Is any worker repeatedly receiving the same event without advancing to `completed`?

**Received, accepted, processed, committed, and acknowledged** are distinct states. Never log `send()` success and treat the entire business process as done.

## 14. Practice Exercise: Retry-Safe Recipient List

Design a flow receiving:

~~~java
record ShipmentCreated(
        String eventId,
        String shipmentId,
        String tenantId,
        boolean needsFraudReview,
        boolean notifyCustomer) {}
~~~

Requirements:

1. **audit** must receive every event.
2. **fraudReview** receives only when `needsFraudReview=true`.
3. **notification** receives only when `notifyCustomer=true`.
4. The audit recipient must never appear twice if two modules configure the same audit task.
5. A redelivered event may be reprocessed on an unfinished branch without creating duplicate **audit effects**.
6. Restarting the application must not lose deduplication state for mandatory effects.
7. Concurrent attempts with the same `recipient + eventId` must not create two business records.

**Implementation steps:**

1. Write a Java DSL `RecipientListRouter` with each recipient identity declared once.
2. Write pure boolean functions for the two conditional recipients and unit test all combinations.
3. Use `QueueChannel` in an integration test to verify message counts received by each recipient after one send.
4. Send **the same `eventId`** twice, proving the router does **not** automatically eliminate duplicate deliveries.
5. Add **`recipientId + eventId`** keying at consumers, testing that one event can pass through two independent recipients.
6. Use unique constraints/transactions when writing audit to test a crash before commit followed by a successful retry.
7. Simulate notification receiving the request but losing the response; pick a target-side idempotency key and reconciliation strategy.
8. Outline scaling with a transactional outbox and durable queues/brokers when producers/consumers run across multiple instances.

**Advanced:** Enable `applySequence` in a separate scatter-gather flow, have one recipient resend its result, and design an Aggregator handling duplicate groups, missing replies, timeouts, and release strategies. Explain why sequence metadata does not replace idempotency keys.

### Self-Check Questions

1. Is one event sent to both audit and risk a duplicate or valid fan-out?
2. Why can two recipients with different selectors pointing to the same channel create hard-to-control designs?
3. Why can placing a deduplication `Set` before `RecipientListRouter` lose a failed branch?
4. When should you use `recipientId + eventId` instead of `eventId` alone?
5. Is `MessageHeaders.ID` suitable as a business deduplication key?
6. Which operation does `MetadataStoreSelector` rely on to claim keys concurrently?
7. Why is `SimpleMetadataStore` insufficient for deduplication across restarts?
8. If a handler throws an exception after claiming a key but before completing the effect, what must happen?
9. How does retrying the entire router differ from retrying just the notification branch?
10. When is a database unique constraint insufficient to prevent duplicate emails/HTTP calls?

## 15. Pre-Deployment Design Checklist

- **Each recipient identity is declared once** in configuration; selectors targeting the same destination are intentionally merged.
- **The channel graph** does not accidentally route the same event to the same side effect along two paths.
- **Event IDs** remain stable across retries/redeliveries and differ properly across real events.
- **Idempotency keys** are properly scoped by recipient, tenant, and operation type.
- **Per-recipient deduplication** lets each branch recover independently after partial failures.
- **Key claims** and effects have matching transactions/state machines; never mark `completed` prematurely.
- **Concurrent requests** are protected by unique constraints/atomic operations, never check-then-put.
- **`MetadataStore`** has durability and sharing characteristics suited to multi-instance deployments.
- **Retry/backoff and DLQs** are designed per branch wherever possible.
- **External side effects** have idempotency/reconciliation or explicit duplicate tolerance.
- **`applySequence`** is enabled only when grouping is genuinely needed; never treat it as deduplication.
- **Observability** distinguishes received, attempted, completed, duplicate skipped, and failed.
- **Tests** cover single sends, replays, branch failures, concurrent claims, and restarts.

**Conclusion:** To avoid duplicate deliveries to the same recipient, control your Recipient List topology and conditions, then protect **per-recipient business effects** with stable event IDs and proper idempotency mechanisms. You cannot infer "exactly once" from a `RecipientListRouter`, an in-memory `Set`, or a `send()` returning true. Sound design defines the exact meaning of **each recipient**, **each event**, and **each completion state**, then tests both happy paths and retries after partial failures.

## References

- [Spring Integration Reference — Router Implementations](https://docs.spring.io/spring-integration/reference/router/implementations.html): `RecipientListRouter` and recipient selectors.
- [Spring Integration Reference — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): `IdempotentReceiverInterceptor`, `duplicateMessage`, discard channel, and `MetadataStoreSelector`.
- [Spring Integration Reference — Metadata Store](https://docs.spring.io/spring-integration/reference/meta-data-store.html): `SimpleMetadataStore`, concurrent/persistent stores, and deduplication.
- [Spring Integration API — MetadataStoreSelector](https://docs.spring.io/spring-integration/api/org/springframework/integration/selector/MetadataStoreSelector.html): key strategies and `putIfAbsent`.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): `DirectChannel`, `QueueChannel`, `ExecutorChannel`, and async boundary effects.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): configuring `IntegrationFlow` and recipient endpoints.
