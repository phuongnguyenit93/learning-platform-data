# Do Not Use Mutable Values as Correlation Keys

In an integration flow, messages belonging to the same business process may arrive from different services, appear at different times, and carry updated data. **Content-based correlation** determines relationships between messages using **values inside the business content**, rather than relying solely on arrival order or an individual message ID. The benefit is that events such as order creation, payment capture, and inventory reservation can converge into a single outcome; the risk is that **picking the wrong value as the correlation key** will silently split or merge message groups.

The lesson **Do Not Use Mutable Values as Correlation Keys** belongs to the **Content-based correlation** chapter of the **SPRING_INTEGRATION_PATTERN** module. This module focuses on implementing Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows—practicing Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation alongside testing and observability across processing branches.

**Core principle:** a correlation key must identify **the exact business unit that needs to converge**, remain **stable throughout the group's lifecycle**, be **unambiguous across distinct groups**, and be **verified at the trust boundary**. Attributes such as email, name, address, status, amount, or update timestamps usually **fail to meet** these conditions.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Define content-based correlation and distinguish it from content-based routing.
2. Explain why an attribute's **presence in the payload** does not make it a suitable correlation key.
3. Recognize the two failure modes: **one business process split across multiple groups** and **multiple business processes merged into one group**.
4. Choose a stable key such as `(tenantId, orderId)` or `(tenantId, orderId, workflowRunId)` according to business scope.
5. Distinguish a correlation key from `eventId`, `MessageHeaders.ID`, `traceId`, `sequenceNumber`, and `sequenceSize`.
6. Separate **validating/normalizing the key at ingress** from **grouping messages** in the Aggregator.
7. Implement a custom correlation strategy using Java 17 and Spring Integration Java DSL.
8. Write a release strategy and output processor that emit results only when all required event types have arrived.
9. Test email/status changes between events, two orders sharing an email, two tenants sharing an order ID, and out-of-order messages.
10. Design duplicate handling, late arrivals, reprocessing, key migration, retention, and idempotency.
11. Explain the impact of unstable keys on `MessageGroupStore`, throughput, timeouts, and operations.
12. Apply these principles to Aggregator, Resequencer, Gateway, and other asynchronous flows.

## 2. When the Wrong Correlation Key Is Chosen

Suppose the application wants to emit `OrderReady` once three pieces of data arrive:

- `OrderRegistered`: order has been created;
- `PaymentCaptured`: payment has been confirmed;
- `InventoryReserved`: stock has been reserved.

Events may arrive seconds or minutes apart.

~~~mermaid
flowchart LR
    O["OrderRegistered"] --> C["Correlation strategy"]
    P["PaymentCaptured"] --> C
    I["InventoryReserved"] --> C
    C --> G[("MessageGroupStore")]
    G --> R{"All 3 types present?"}
    R -->|No| W["Keep group, wait"]
    R -->|Yes| OUT["OrderReady"]
~~~

**Correlation strategy** answers the question: which **group** does this message belong to? Choosing a stable `orderId` lets all three events for the same order meet. Choosing `customerEmail` exposes the system to failure in two directions.

### 2.1. First Failure: One Order Splits into Two Groups

~~~text
10:00 OrderRegistered
  orderId = ORDER-101
  email = alice@old.example.invalid

10:01 Customer updates email

10:02 PaymentCaptured
  orderId = ORDER-101
  email = alice@new.example.invalid

10:03 InventoryReserved
  orderId = ORDER-101
  email = alice@new.example.invalid
~~~

If correlation key = email:

~~~text
Group "alice@old.example.invalid":
  OrderRegistered(ORDER-101)
  -> missing Payment + Inventory

Group "alice@new.example.invalid":
  PaymentCaptured(ORDER-101)
  InventoryReserved(ORDER-101)
  -> missing OrderRegistered
~~~

Both groups can **wait forever** or expire even though all three events were actually sent.

If correlation key = `(tenantId, orderId)`:

~~~text
Group ("tenant-a", "ORDER-101"):
  OrderRegistered
  PaymentCaptured
  InventoryReserved
  -> complete, can produce OrderReady
~~~

### 2.2. Second Failure: Two Orders Merge into One

One customer can place multiple orders:

~~~text
OrderRegistered(ORDER-101, email=alice@example.invalid)
OrderRegistered(ORDER-102, email=alice@example.invalid)
PaymentCaptured(ORDER-102, email=alice@example.invalid)
InventoryReserved(ORDER-101, email=alice@example.invalid)
~~~

If correlated by email, all of them land in the same group despite **different order IDs**. A release strategy that only counts messages can produce payment/inventory outcomes for the **wrong order**.

**Note:** an unchanging key that is **not specific enough** is just as dangerous as a changing key. An email might stay unchanged for a week, yet it still does not identify *one specific order*.

## 3. Correlation Differs from Content-Based Filtering and Routing

All three can inspect the payload, yet their purposes differ:

| Component | Question | Example |
|---|---|---|
| **Content-based Router** | Which channel should the message go to? | `amount >= 1000` → high-value |
| **Filter** | May the message continue? | `status == APPROVED` |
| **Content-based Correlation** | Which business group does the message belong to? | `(tenantId, orderId)` |
| **Aggregator** | When is the group complete, and what is the output? | Order, Payment, and Inventory all present |
| **Resequencer** | In what order should related messages be emitted? | `sequenceNumber=1..N` |

A Router **can use mutable state** to select a branch under current policy; that does not make state a valid correlation key. Correlation must stay **stable for the entire window in which messages need to converge**.

Example:

~~~java
// Routing based on a current business decision:
String route = order.amount().compareTo(limit) >= 0
        ? "orders.highValue"
        : "orders.standard";

// Correlation based on stable identity:
BusinessKey key = new BusinessKey(
        order.tenantId(),
        order.orderId());
~~~

An order whose total increases from 900 to 1,100 may change its **routing policy**, yet it remains **the same order** that must receive its payment/inventory events.

## 4. Criteria for a Good Correlation Key

A value that looks unique right now is not automatically sufficient. A key must satisfy the criteria below.

| Criterion | Check Question | Consequence If Violated |
|---|---|---|
| **Stable** | Can the key change between group open and close? | One business flow splits across multiple groups |
| **Properly scoped** | Does the key identify the exact *unit to gather*? | Multiple orders of one customer mix together |
| **Sufficiently unique** | Can two distinct workflows share a key? | Cross-order/cross-tenant contamination |
| **Present on all events** | Can every producer supply or look up the key? | Messages lack keys and are rejected/misgrouped |
| **Consistent format** | Do producers use the same type and canonical form? | `ord-1` and `ORD-1` become two groups |
| **Verified** | Are tenant and ownership verified? | Clients can inject into unauthorized groups |
| **Appropriate lifetime** | Can the key be reused within group retention? | Reprocessing collides with old groups |
| **Storable** | Does the key work with store/serializer/distributed locks? | Restarts/multi-instance fail |
| **Safely observable** | Can it be traced without leaking PII? | Log/metric leaks or hard-to-debug issues |

For the `OrderReady` flow, `tenantId` and `orderId` are reasonable **candidates** if they are committed, stable internal IDs; always verify the data contract instead of assuming every field named `orderId` is valid.

### 4.1. A Useful Verification Condition

For events `e1` and `e2` belonging to the same business group G:

~~~text
businessGroup(e1) == businessGroup(e2)
     ==> correlationKey(e1) == correlationKey(e2)
~~~

For events belonging to two **different** groups:

~~~text
businessGroup(e1) != businessGroup(e2)
     ==> correlationKey(e1) != correlationKey(e2)
~~~

These two conditions express **within-group consistency** and **cross-group distinction**. They are logical design standards, not an assertion that the real world always offers ideal identifiers. When source data cannot guarantee them, design explicit mappings or reconciliation processes.

### 4.2. Group Scope Must Be Explicit

Things that can define separate groups:

- A specific order.
- A specific payment attempt.
- A specific workflow execution.
- A data batch with a batch ID.
- A document processing session.
- A time window with a fixed ID.

Do not pick `customerId` for order-level grouping if one customer places multiple orders; likewise, do not pick `orderId` for **payment-attempt** grouping if an order has multiple attempts that must stay separate.

## 5. Values That Should **Not** Be Keys by Default

### 5.1. Email, Phone Number, Username

- Customers can update contact details.
- Emails/phone numbers can be recycled or shared.
- Capitalization, Unicode, whitespace, or normalization can differ.
- These can be personal data needing protection from logs/metrics.
- Multiple orders by one customer with the same email are still distinct groups.

Use a **stable internal customer ID** if the group truly is per customer; use **order ID** if the group is per order.

### 5.2. Workflow Status

~~~text
NEW -> VALIDATED -> PAID -> PACKING -> SHIPPED
~~~

Grouping by `status` puts each step into a different group. Status drives **Filter/Router**, not the identity of a single workflow instance.

### 5.3. Amount, Balance, Score, Priority, Tier

~~~text
amount = 900.00 -> order edited -> 1050.00
riskScore = 0.20 -> model recomputed -> 0.84
priority = NORMAL -> VIP
~~~

These are **business attributes** and can be updated. They are also usually **non-unique**, as many orders share the same amount or tier.

### 5.4. Timestamps

`createdAt` may stay fixed if treated as part of a managed ID, yet timestamps alone are not always unique. `updatedAt` **almost certainly changes**. System clocks can also skew across producers.

Never use `System.currentTimeMillis()` or `Instant.now()` when evaluating a correlation strategy: the exact same event replayed 10 seconds later would land in a different group.

### 5.5. Display Name, SKU Label, Address, URL

Display labels, product names, shipping addresses, or external URLs can be updated, normalized, or altered by redirects. If the domain has an **immutable canonical ID**, use that ID; otherwise, define an explicit mapping/version contract.

### 5.6. Per-Message Generated IDs

`MessageHeaders.ID` or `eventId` is typically unique **per individual event**, not **for the group of different events belonging to one order**. Using `eventId` as the key to join Order + Payment + Inventory places the three events into three separate groups.

## 6. Distinguishing Common Identifiers

| Identifier | Identifies | When to Use as Correlation Key? |
|---|---|---|
| `MessageHeaders.ID` | One Spring Message instance | Never for multi-event groups |
| `eventId` | One individual business event | For dedup/replay; usually not for OrderReady groups |
| `traceId` | One execution chain/tracing context | Never instead of business group key |
| `spanId` | One step in a distributed trace | Never |
| `customerId` | One customer | Only if the group is genuinely per customer |
| `orderId` | One order | Suitable when grouping per order and ID is unique in scope |
| `tenantId` | One tenant | Combine with business ID if IDs can repeat across tenants |
| `paymentAttemptId` | One payment attempt | When grouping per payment attempt |
| `workflowRunId` | One workflow execution | When each run requires its own group |
| `sequenceNumber` | Position of one part | Cannot identify the whole group |
| `sequenceSize` | Expected total parts | Cannot identify the whole group |
| `correlationId` header | Metadata supplied by framework or producer | Only when content/origin is verified for the right group |

**Header name is not proof of semantics.** A producer might stamp `correlationId` with a fresh request ID per HTTP call; events for the same order would still carry different correlation IDs. Never use it blindly as a business key.

## 7. Composite Key: tenantId + orderId

If `orderId` is only unique within each tenant, the group key needs both components.

~~~text
Tenant A, ORDER-101 -> Group A/ORDER-101
Tenant B, ORDER-101 -> Group B/ORDER-101
~~~

Using `orderId` alone risks mixing two tenants into the same group despite separate accounts and access boundaries.

### 7.1. Use a Value Object Instead of Naive String Concatenation

~~~java
import java.io.Serializable;

public record BusinessKey(
        String tenantId,
        String orderId
) implements Serializable {

    public BusinessKey {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException(
                    "TENANT_ID_REQUIRED");
        }
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException(
                    "ORDER_ID_REQUIRED");
        }
    }
}
~~~

A `record` automatically provides `equals` and `hashCode` over both fields, comparing group keys properly by **value**.

Arbitrary string concatenation:

~~~java
String key = tenantId + ":" + orderId;
~~~

can collide if values contain the delimiter:

~~~text
tenantId="a:b", orderId="c" -> "a:b:c"
tenantId="a",   orderId="b:c" -> "a:b:c"
~~~

A value object eliminates concatenation collisions and makes component names explicit. With a distributed `MessageGroupStore`, verify **serialization, stable equality, and key mapping** on the actual backend. Never assume every store or serializer accepts arbitrary custom Java objects without configuration.

### 7.2. Should workflowRunId Be Added?

If the same order can undergo multiple workflow runs, `(tenantId, orderId)` alone may not separate the **first processing run** from a **second reprocessing run**.

~~~java
import java.io.Serializable;

public record RunKey(
        String tenantId,
        String orderId,
        String workflowRunId
) implements Serializable {}
~~~

Add `workflowRunId` only if **every producer** participating in the group knows the same fixed run ID throughout the run. If each service generates its own run ID, the composite key will split events apart again.

For a workflow where only one `OrderReady` should ever exist per order, `(tenantId, orderId)` plus idempotency may be the right choice; adding more fields does not automatically make correlation safer.

## 8. Choose the Right Unit to Gather Before Writing Code

Before opening the IDE, fill out this contract table:

| Component | Example |
|---|---|
| Business group | One order waiting for three events to build `OrderReady` |
| Correlation key | `BusinessKey(tenantId, orderId)` |
| Part types | `OrderRegistered`, `PaymentCaptured`, `InventoryReserved` |
| Group release | Exactly one valid part of each type |
| Where the key appears | Inside each event's payload |
| Where canonical ID originates | Verified order service / tenant registry |
| Duplicate policy | Dedup `eventId` or reject duplicate part type |
| Missing part | Timeout/expiry + incomplete group outcome |
| Late part | Reject, correction, or reconciliation per contract |
| Reprocess | Version/run policy and output idempotency |
| Output | `OrderReady(tenantId, orderId, paymentId, reservationId, amount)` |

If you cannot fill in **Where canonical ID originates**, you are not ready to write a correlation strategy using an arbitrary string from the payload.

## 9. Java 17 Event Model: Immutable Identity, Mutable Snapshots Allowed

To demonstrate both **constant identity** and **mutable attributes**, define a sealed event hierarchy sharing `tenantId`, `orderId`, and `eventId`. `customerEmailSnapshot` is included on the events solely to illustrate snapshot data that can change between sources.

~~~java
import java.math.BigDecimal;

public sealed interface OrderPart
        permits OrderRegistered, PaymentCaptured, InventoryReserved {

    String eventId();

    String tenantId();

    String orderId();

    String customerEmailSnapshot();

    default BusinessKey businessKey() {
        return new BusinessKey(tenantId(), orderId());
    }
}

public record OrderRegistered(
        String eventId,
        String tenantId,
        String orderId,
        String customerEmailSnapshot,
        BigDecimal amount
) implements OrderPart {}

public record PaymentCaptured(
        String eventId,
        String tenantId,
        String orderId,
        String customerEmailSnapshot,
        String paymentId
) implements OrderPart {}

public record InventoryReserved(
        String eventId,
        String tenantId,
        String orderId,
        String customerEmailSnapshot,
        String reservationId
) implements OrderPart {}

public record OrderReady(
        BusinessKey businessKey,
        BigDecimal amount,
        String paymentId,
        String reservationId
) {}
~~~

Putting top-level `public` types in one code block is for presentation; in a Java project, **place each type in its own matching source file**. Java 17+ supports records and sealed types; on older Java versions, use equivalent classes.

**Security note:** the email snapshot in this example is unnecessary for real aggregation output. Remove personal data from events/headers when not required by the business; including email on all three events is solely to **illustrate the risk of choosing it as a key**.

### 9.1. Timeline with Changing Email

~~~text
10:00 OrderRegistered(
  tenantId=tenant-a, orderId=ORDER-101,
  customerEmailSnapshot=alice@old.example.invalid)

10:05 PaymentCaptured(
  tenantId=tenant-a, orderId=ORDER-101,
  customerEmailSnapshot=alice@new.example.invalid)

10:06 InventoryReserved(
  tenantId=tenant-a, orderId=ORDER-101,
  customerEmailSnapshot=alice@new.example.invalid)
~~~

All three events share:

~~~java
new BusinessKey("tenant-a", "ORDER-101")
~~~

and therefore belong to the **same group**, regardless of whether the email snapshot changed.

## 10. A Pure, Validated Correlation Strategy

~~~java
import org.springframework.messaging.Message;

public final class StableOrderCorrelation {

    public BusinessKey key(Message<?> message) {
        if (!(message.getPayload() instanceof OrderPart part)) {
            throw new IllegalArgumentException(
                    "UNSUPPORTED_ORDER_PART");
        }

        if (part.eventId() == null
                || part.eventId().isBlank()) {
            throw new IllegalArgumentException(
                    "EVENT_ID_REQUIRED");
        }

        // BusinessKey constructor validates tenantId/orderId.
        return new BusinessKey(
                part.tenantId(),
                part.orderId());
    }
}
~~~

Here the correlation strategy is a **pure mapping** from a message to a stable business identity, without calling external APIs or reading the clock:

~~~text
Message<OrderPart>
  -> validate ID
  -> BusinessKey(tenantId, orderId)
~~~

### 10.1. Do Not Put Status into the Key

~~~java
// Anti-pattern: the same order changing status moves to another group.
String unstable = part.orderId()
        + ":" + currentStatus;
~~~

If `currentStatus` transitions from NEW to PAID, the key changes even though the group is still the same order. Status may be used in release/output logic, **never as group identity**.

### 10.2. Do Not Query a Service for the Latest Email on Every Key Calculation

~~~java
// Anti-pattern: the value can differ between initial receipt and retry.
String unstable = customerService
        .lookupCurrentEmail(customerId);
~~~

Even if each event carries a stable `customerId`, looking up the “current email” over time couples correlation to mutable database state. On a retry after an email update, **the exact same event** would yield a new key and create a different group. Use a contract-defined canonical ID, never a mutable “current” attribute.

### 10.3. Do Not Use Clocks or Random Values

~~~java
// Both cause replays to land in a different group.
String badKey1 = orderId + "-" + System.currentTimeMillis();
String badKey2 = orderId + "-" + java.util.UUID.randomUUID();
~~~

A random UUID is valid when **creating a new group ID once at the producer** and propagating it consistently to every part; it is **invalid when each consumer generates a fresh one** inside the correlation strategy.

## 11. Ingress Validation and Canonicalization

The same logical ID may arrive in multiple representations:

~~~text
ORDER-101
order-101
 ORDER-101
urn:order:ORDER-101
~~~

Should you always trim/lowercase automatically? **Not always.** Some IDs are case-sensitive; blind normalization can merge two genuinely distinct IDs. The canonical form must be **published by the system that owns the ID**.

### 11.1. Principles

- Validate format before sending messages into the Aggregator.
- Convert external IDs to canonical internal IDs at the **adapter boundary**.
- Never let each service invent its own normalization rules.
- If an ID is already canonical and case-sensitive, preserve it unchanged.
- If tenant ID arrives from a client, verify it against the authenticated tenant.
- If aliases/merges exist, use versioned/audited mappings with a consistent procedure.

Example of an adapter accepting only canonical IDs:

~~~java
import java.util.regex.Pattern;

public final class OrderIdentityValidator {

    private static final Pattern ORDER_ID =
            Pattern.compile("ORDER-[A-Z0-9]+");

    public String requireCanonicalOrderId(String value) {
        if (value == null || !ORDER_ID.matcher(value).matches()) {
            throw new IllegalArgumentException(
                    "NON_CANONICAL_ORDER_ID");
        }
        return value;
    }
}
~~~

This is an **illustrative business rule**, not a built-in Spring Integration format. If your system uses UUIDs, Snowflake IDs, or another schema, substitute the corresponding contract.

### 11.2. When Mapping Between External IDs Is Needed

~~~text
Payment provider says: externalOrderRef="X-5002"
Order service says:     orderId="ORDER-101"
~~~

Never correlate `X-5002` directly with `ORDER-101` expecting the framework to guess they match. Explicitly map the external reference to the canonical order ID:

~~~text
Payment adapter
  externalOrderRef="X-5002"
  -> trusted mapping
  -> orderId="ORDER-101"
  -> PaymentCaptured(tenant-a, ORDER-101, ...)
~~~

If the mapping is missing or uncertain, **quarantine or retry reconciliation** rather than guessing by email or amount.

## 12. Correlation in Spring Integration Aggregator

With a typical Splitter, the framework can generate `correlationId`/`sequenceSize` headers so a default Aggregator knows how to collect parts of a split batch. However, with **independent events from Order/Payment/Inventory services**, you cannot assume all three producers emit a matching default `correlationId`.

You need a **custom correlation strategy** returning a stable business key from the payload.

~~~mermaid
flowchart TD
    A["OrderRegistered"] --> N["Validate + canonicalize identity"]
    B["PaymentCaptured"] --> N
    C["InventoryReserved"] --> N
    N --> CORR["StableOrderCorrelation.key(message)"]
    CORR --> GROUP[("MessageGroupStore by BusinessKey")]
    GROUP --> REL{"Release strategy"}
    REL -->|Not ready| WAIT["Wait for more parts"]
    REL -->|Ready| OUT["OrderReady output processor"]
~~~

### 12.1. Correlation and Release Are Two Responsibilities

Correlation strategy must answer **which group**. Release strategy answers **is the group complete**.

If a group under `BusinessKey` has only `OrderRegistered` and `PaymentCaptured`, the key is still right—the group simply **does not have all data yet**. Never append a status field to the key just to “indicate payment arrived.”

### 12.2. Release Strategy Cannot Merely Count Messages

~~~text
OrderRegistered(ORDER-101)
PaymentCaptured(ORDER-101)
PaymentCaptured(ORDER-101)  // redelivery
~~~

Three messages do not mean `InventoryReserved` has arrived. The release policy should verify all **required part types**; upstream needs deduplication by `eventId` and duplicate handling.

## 13. Release Policy and Output Processor

The example focuses on the **happy path with exactly one event of each type**. It intentionally **does not swallow duplicates** so learners see that duplicates must be handled explicitly.

### 13.1. Release When All Three Types Are Present

~~~java
import org.springframework.integration.store.MessageGroup;

public final class OrderGroupReleasePolicy {

    public boolean complete(MessageGroup group) {
        long orders = count(group, OrderRegistered.class);
        long payments = count(group, PaymentCaptured.class);
        long inventory = count(group, InventoryReserved.class);

        return orders == 1
                && payments == 1
                && inventory == 1
                && group.size() == 3;
    }

    private long count(
            MessageGroup group, Class<?> type) {
        return group.getMessages().stream()
                .map(message -> message.getPayload())
                .filter(type::isInstance)
                .count();
    }
}
~~~

If two identical `PaymentCaptured` events are stored, the policy will not release while Inventory is missing. **However**, if a duplicate leaves the group with four parts, this policy also won't release even when all three types are present. In a real system, deduplicate or resolve event versions **before the group stalls**, paired with appropriate group timeouts/expiry.

### 13.2. Domain Assembler Creating OrderReady

~~~java
import java.util.List;
import java.util.Objects;

import org.springframework.integration.store.MessageGroup;

public final class OrderReadyProcessor {

    public OrderReady process(MessageGroup group) {
        OrderGroupReleasePolicy policy =
                new OrderGroupReleasePolicy();

        if (!policy.complete(group)) {
            throw new IllegalArgumentException(
                    "ORDER_GROUP_INCOMPLETE");
        }

        OrderRegistered order =
                exactlyOne(group, OrderRegistered.class);

        PaymentCaptured payment =
                exactlyOne(group, PaymentCaptured.class);

        InventoryReserved inventory =
                exactlyOne(group, InventoryReserved.class);

        BusinessKey key = order.businessKey();

        if (!key.equals(payment.businessKey())
                || !key.equals(inventory.businessKey())) {
            throw new IllegalStateException(
                    "BUSINESS_KEY_MISMATCH");
        }

        Objects.requireNonNull(order.amount(), "amount");
        if (order.amount().signum() < 0) {
            throw new IllegalArgumentException(
                    "ORDER_AMOUNT_INVALID");
        }

        return new OrderReady(
                key,
                order.amount(),
                payment.paymentId(),
                inventory.reservationId());
    }

    private <T extends OrderPart> T exactlyOne(
            MessageGroup group,
            Class<T> type) {

        List<T> matches = group.getMessages().stream()
                .map(message -> message.getPayload())
                .filter(type::isInstance)
                .map(type::cast)
                .toList();

        if (matches.size() != 1) {
            throw new IllegalArgumentException(
                    "MISSING_OR_DUPLICATE_" + type.getSimpleName());
        }

        return matches.get(0);
    }
}
~~~

**Why does the assembler re-verify the key?** The correlation strategy is expected to group events with equal keys, yet payloads can be malformed or mutated along the way. Re-checking the invariant at the output boundary blocks bad results before writing to the DB or emitting events.

In production, add checks for `eventId`, payment status, inventory status, amount/version, authorization, and event origin. The snippet illustrates **choosing a stable key** and joining three events.
## 14. Java DSL: Correlating with a Stable Business Key

With three independent Order/Payment/Inventory sources, you cannot assume they all emit the same `correlationId` header as Splitter-generated parts. Configure the Aggregator with custom strategies:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class StableCorrelationConfiguration {

    @Bean(name = "order.parts.input")
    public MessageChannel input() {
        return new DirectChannel();
    }

    @Bean(name = "orders.ready")
    public PollableChannel output() {
        return new QueueChannel();
    }

    @Bean
    public StableOrderCorrelation correlation() {
        return new StableOrderCorrelation();
    }

    @Bean
    public OrderGroupReleasePolicy releasePolicy() {
        return new OrderGroupReleasePolicy();
    }

    @Bean
    public OrderReadyProcessor outputProcessor() {
        return new OrderReadyProcessor();
    }

    @Bean
    public IntegrationFlow stableOrderFlow(
            StableOrderCorrelation correlation,
            OrderGroupReleasePolicy release,
            OrderReadyProcessor processor) {

        return IntegrationFlow
                .from("order.parts.input")
                .aggregate(spec -> spec
                        .correlationStrategy(correlation::key)
                        .releaseStrategy(release::complete)
                        .outputProcessor(processor::process))
                .channel("orders.ready")
                .get();
    }
}
~~~

Processing flow:

~~~text
Message<OrderPart>
  -> StableOrderCorrelation: BusinessKey(tenantId, orderId)
  -> MessageGroupStore holds group by key
  -> OrderGroupReleasePolicy: all 3 part types present
  -> OrderReadyProcessor: builds OrderReady
  -> orders.ready
~~~

`QueueChannel` in the example is solely an in-JVM test fixture. In real deployments, add timeouts/expiry, duplicate handling, a persistent group store if needed, transactions, and an error channel suited to the topology.

### 14.1. Callbacks Must Not Mix Responsibilities

- **Correlation strategy** must not query a DB for the current email or generate a new UUID.
- **Release strategy** must not send emails, write to DBs, or select output channels.
- **Output processor** should re-verify the business identity of the whole group.
- **Output channel** is the delivery path after release; it does not determine grouping.
- **Downstream handler** needs idempotency because outputs may be redelivered.

`BusinessKey` is an immutable record compared by value. When using a persistent `MessageGroupStore`, verify serialization, equality, and how the backend stores group keys.

## 15. Unit Test: Email Changes Yet Key Stays the Same

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.support.GenericMessage;

class StableOrderCorrelationTest {

    private final StableOrderCorrelation strategy =
            new StableOrderCorrelation();

    @Test
    void changedEmailStillProducesSameGroupKey() {
        OrderRegistered order = new OrderRegistered(
                "evt-o-1", "tenant-a", "ORDER-101",
                "alice@old.example.invalid",
                new BigDecimal("300.00"));

        PaymentCaptured payment = new PaymentCaptured(
                "evt-p-1", "tenant-a", "ORDER-101",
                "alice@new.example.invalid",
                "PAY-101");

        assertEquals(
                strategy.key(new GenericMessage<>(order)),
                strategy.key(new GenericMessage<>(payment)));
    }

    @Test
    void sameEmailDoesNotMergeTwoOrders() {
        OrderRegistered first = new OrderRegistered(
                "evt-o-1", "tenant-a", "ORDER-101",
                "alice@example.invalid",
                new BigDecimal("300.00"));

        OrderRegistered second = new OrderRegistered(
                "evt-o-2", "tenant-a", "ORDER-102",
                "alice@example.invalid",
                new BigDecimal("400.00"));

        assertNotEquals(
                strategy.key(new GenericMessage<>(first)),
                strategy.key(new GenericMessage<>(second)));
    }

    @Test
    void tenantIsPartOfTheGroupIdentity() {
        OrderRegistered a = new OrderRegistered(
                "evt-a", "tenant-a", "ORDER-101",
                "a@example.invalid",
                new BigDecimal("100.00"));

        OrderRegistered b = new OrderRegistered(
                "evt-b", "tenant-b", "ORDER-101",
                "b@example.invalid",
                new BigDecimal("200.00"));

        assertNotEquals(
                strategy.key(new GenericMessage<>(a)),
                strategy.key(new GenericMessage<>(b)));
    }

    @Test
    void blankOrderIdIsRejected() {
        OrderRegistered invalid = new OrderRegistered(
                "evt-invalid", "tenant-a", "",
                "a@example.invalid",
                new BigDecimal("100.00"));

        assertThrows(IllegalArgumentException.class,
                () -> strategy.key(new GenericMessage<>(invalid)));
    }
}
~~~

These tests confirm **within-group stability**, **cross-group separation**, and ID validation. They do not replace tenant authorization tests at ingress.

## 16. Unit Test for Release/Output Using MessageGroup

Use `SimpleMessageStore` to construct a group for policy testing:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.integration.store.MessageGroup;
import org.springframework.integration.store.SimpleMessageStore;
import org.springframework.messaging.support.GenericMessage;

class OrderGroupReleasePolicyTest {

    @Test
    void waitsForAllThreeEventTypes() {
        BusinessKey key =
                new BusinessKey("tenant-a", "ORDER-101");

        SimpleMessageStore store = new SimpleMessageStore();

        store.addMessageToGroup(key, new GenericMessage<>(
                new OrderRegistered(
                        "evt-o", "tenant-a", "ORDER-101",
                        "old@example.invalid",
                        new BigDecimal("300.00"))));

        store.addMessageToGroup(key, new GenericMessage<>(
                new PaymentCaptured(
                        "evt-p", "tenant-a", "ORDER-101",
                        "new@example.invalid", "PAY-101")));

        OrderGroupReleasePolicy policy =
                new OrderGroupReleasePolicy();

        assertFalse(policy.complete(store.getMessageGroup(key)));

        store.addMessageToGroup(key, new GenericMessage<>(
                new InventoryReserved(
                        "evt-i", "tenant-a", "ORDER-101",
                        "new@example.invalid", "RES-101")));

        MessageGroup complete = store.getMessageGroup(key);
        assertTrue(policy.complete(complete));

        OrderReady ready =
                new OrderReadyProcessor().process(complete);

        assertEquals(key, ready.businessKey());
        assertEquals("PAY-101", ready.paymentId());
        assertEquals("RES-101", ready.reservationId());
        assertEquals(
                new BigDecimal("300.00"), ready.amount());
    }
}
~~~

This tests **business policies**; it does not replace an integration test of the Aggregator endpoint itself. If a group receives two duplicate `PaymentCaptured` events while missing Inventory, `group.size()==3` is unsafe. The sample policy counts each type, whereas a real application needs `eventId` deduplication or conflict handling before storing into the group.

## 17. Integration Test Across Spring Integration Channels

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

@SpringJUnitConfig(classes = StableCorrelationConfiguration.class)
class StableCorrelationFlowTest {

    @Autowired
    @Qualifier("order.parts.input")
    MessageChannel input;

    @Autowired
    @Qualifier("orders.ready")
    PollableChannel output;

    @Test
    void joinsEventsAfterEmailUpdate() {
        assertTrue(input.send(MessageBuilder.withPayload(
                new OrderRegistered(
                        "evt-o-101", "tenant-a", "ORDER-101",
                        "alice@old.example.invalid",
                        new BigDecimal("300.00")))
                .build()));

        assertNull(output.receive(0));

        assertTrue(input.send(MessageBuilder.withPayload(
                new PaymentCaptured(
                        "evt-p-101", "tenant-a", "ORDER-101",
                        "alice@new.example.invalid",
                        "PAY-101"))
                .build()));

        assertNull(output.receive(0));

        assertTrue(input.send(MessageBuilder.withPayload(
                new InventoryReserved(
                        "evt-i-101", "tenant-a", "ORDER-101",
                        "alice@new.example.invalid",
                        "RES-101"))
                .build()));

        Message<?> message = output.receive(1000);
        assertNotNull(message);
        assertInstanceOf(OrderReady.class, message.getPayload());

        OrderReady result = (OrderReady) message.getPayload();
        assertEquals(
                new BusinessKey("tenant-a", "ORDER-101"),
                result.businessKey());
        assertEquals("PAY-101", result.paymentId());
        assertEquals("RES-101", result.reservationId());
        assertEquals(
                new BigDecimal("300.00"), result.amount());

        assertNull(output.receive(0));
    }
}
~~~

In this synchronous in-memory flow, the first two events do not trigger release; the third produces an `OrderReady`. The email change does not change the group. This test does not prove exactly-once side effects, timeouts, restart resilience, or multi-instance execution.

### 17.1. Test Interleaving Two Orders Sharing an Email

Send:

~~~text
A: OrderRegistered(ORDER-101, alice@example.invalid)
B: OrderRegistered(ORDER-102, alice@example.invalid)
B: PaymentCaptured(ORDER-102, alice@example.invalid)
A: InventoryReserved(ORDER-101, alice@example.invalid)
~~~

Expect **no output yet** because both A and B are missing one part. Next send A's Payment and B's Inventory, then assert there are **two separate outputs** without mixing payment/inventory across the two orders.

### 17.2. Test Same orderId Across Different Tenants

Send all three events for both `tenant-a/ORDER-101` and `tenant-b/ORDER-101`. The two outputs must carry distinct `BusinessKey`s with no part mixing. Tenant must be verified before messages enter a group.

### 17.3. Test Isolation

If tests share a cached Spring `ApplicationContext`, incomplete groups in `SimpleMessageStore` can bleed into subsequent tests. Use unique group IDs per test, cleanup fixtures, or isolate contexts.
## 18. Mapping External IDs to Canonical Keys

In distributed systems, producers may use different references:

~~~text
Order service:
  tenantId=tenant-a, orderId=ORDER-101

Payment provider:
  externalOrderRef=EXT-5002, merchantAccount=ACCT-X

Inventory service:
  inventoryRequest=REQ-99, orderReference=ORDER-101
~~~

Content-based correlation cannot guess on its own that `EXT-5002` and `ORDER-101` refer to the same order. You need a trusted **identity resolution** step before feeding messages into the Aggregator.

~~~mermaid
flowchart LR
    O["Order event"] --> V["Validate canonical key"]
    P["Payment external ref"] --> M["Trusted identity mapping"]
    M --> V
    I["Inventory reference"] --> V
    V --> C["Canonical OrderPart"]
    C --> A["Aggregator by BusinessKey"]
~~~

Adapter responsibilities:

1. Authenticate the event source, tenant, or merchant account.
2. Look up the mapping external reference → canonical order ID.
3. Verify the mapping is unambiguous and does not belong to another tenant.
4. Convert into an `OrderPart` with the exact `tenantId` and `orderId`.
5. When the mapping is missing, perform bounded retries, quarantine, or reconciliation.
6. Never guess the group by email, amount, or shipping address.

### 18.1. Canonicalization Is Not Arbitrary Lowercasing

If the ID-owning system guarantees `order-101` and `ORDER-101` represent the same order, the adapter can normalize them. If IDs are case-sensitive, doing so can **merge two distinct orders**.

Never call `trim()` or `toLowerCase()` on every ID just to tolerate typos. The canonical ID contract must be defined by the ID authority, with collision tests and migration rules.

### 18.2. Do Not Look Up Current Values When Computing Correlation

A correlation strategy that calls an API to fetch the "current email" on every run will not remain stable after an email change or during event replay. Instead, resolve **business identity** at the adapter, keep a consistent key, and evaluate only pure mappings inside the strategy.

## 19. Replays, Duplicates, and Late Arrivals

### 19.1. Replays Keep the Business Key Unchanged

~~~text
First delivery:
  eventId=evt-pay-101
  MessageHeaders.ID=UUID-A
  BusinessKey=(tenant-a, ORDER-101)

Redelivery:
  eventId=evt-pay-101
  MessageHeaders.ID=UUID-B
  BusinessKey=(tenant-a, ORDER-101)
~~~

An event may be reconstructed into a new Spring Message with a different ID, yet it must still belong to the original group. Never use `MessageHeaders.ID`, `Instant.now()`, or a random UUID **generated at the consumer** to determine correlation.

### 19.2. Use eventId for Deduplication, Not to Join Three Event Types

You can structure the pipeline as:

~~~text
Ingress -> Validate tenant/business ID
        -> Dedup by (sourceId,eventId)
        -> Aggregator by BusinessKey
        -> Output handler with idempotency
~~~

In many systems, `eventId` is unique only within a producer's namespace; pair it with `sourceId`/`tenantId` as needed. If the same `eventId` arrives with a different payload, treat it as a **data integrity conflict**, never silently picking one version.

### 19.3. Late Arrivals After Release

If Inventory is redelivered after `OrderReady` has been processed, a completed group might reopen or be ignored depending on completion/expiry configuration. Your design needs:

- Completed-group metadata/tombstones with a sensible retention window.
- A late-arrival policy: discard, quarantine, or correction.
- Idempotent output handlers and a stable output event ID.
- Metrics for replays, duplicates, and late arrivals.
- Clear rules for when an arrival is a legitimate **business correction** rather than a mere redelivery.

**A correct key guarantees only group identity; it does not by itself solve exactly-once business side effects.**

## 20. Reprocessing and workflowRunId

An order may need reprocessing. Distinguish a **retry of the same workflow** from a **new workflow run with its own outcome**.

### 20.1. Retrying the Same Workflow

If the broker retries `PaymentCaptured`, keep `BusinessKey(tenantId,orderId)`. Never add `retryCount` to the correlation key, or each delivery attempt will land in a separate group.

### 20.2. New Workflow Run

If the business dictates that reprocessing must produce a separate new outcome, you can use `RunKey(tenantId,orderId,workflowRunId)`. However, the run ID must be **allocated once** and every producer in that run must use that exact value. If three services generate random run IDs independently, the three events will never converge.

### 20.3. Payment Attempt Differs from Order

If gathering events belonging to **one payment attempt**, `paymentAttemptId` may be more accurate than `orderId`. If the goal is `OrderReady` for the entire order after one successful payment, business policy must decide which attempt is accepted and link it to the order. **The unit being gathered dictates the key**, rather than picking whichever field happens to look unique.

## 21. When IDs Change: Aliases, Merges, and Migrations

No system completely avoids ID format changes or data merges. For example:

~~~text
10:00 OrderRegistered: oldOrderId=ORD-OLD-101
10:05 ID format changed
10:06 PaymentCaptured: newOrderId=ORDER-101
~~~

If the two events enter the Aggregator with different keys, they split into separate groups. Mitigation steps:

1. Prefer an **immutable canonical internal ID**; external/display IDs can change.
2. Maintain an `old→canonical` alias table with versioning, auditing, and access control.
3. Translate at the adapter before computing correlation.
4. If you truly must change group keys, migrate `MessageGroupStore`, lock keys, and completed-group metadata together.
5. Account for old-format events still sitting in the broker.
6. Design reconciliation for conflicting mappings.

Never rely on email/amount to automatically merge two groups, as they might be two different orders.

### 21.1. Mutable Objects as Map Keys

A `HashMap` or hash-backed store can fail lookups if a key object mutates fields used in `equals/hashCode` **after insertion**. Use immutable records/value objects like `BusinessKey` or frozen canonical strings.

## 22. Content-Based Correlation in Resequencer

A Resequencer also needs group identity to order related messages by `sequenceNumber`. Every batch has parts 1, 2, 3, so sequence numbers **cannot replace the group key**.

~~~text
Batch A:
  key=A
  sequenceNumber=1,2,3

Batch B:
  key=B
  sequenceNumber=1,2,3
~~~

If the same customer runs two batches, never use email as the key. Use `batchId` or `(tenantId,batchId)` with a stable ID for the entire batch. Even with proper correlation, wrong `sequenceSize`, duplicate sequence numbers, or missing parts require separate validation/release/timeout handling.

## 23. Content-Based Correlation in Gateway

A Gateway performs request–reply and may attach a `replyChannel`. Yet a group from Order, Payment, and Inventory services might complete minutes later, after the initial Gateway/HTTP request has timed out.

Keep these separate:

- `replyChannel`: where an active request receives its reply.
- `traceId`: tracks execution paths in distributed tracing.
- `BusinessKey`: business identity so parts converge.
- `eventId`: identifies individual events for deduplication.
- `outputEventId`: identifies outputs for downstream idempotency.

For long-running workflows, return `202 Accepted` with a tracking ID, then emit `OrderReady` asynchronously when all events arrive. Never conflate an HTTP tracking ID with the correlation key when their lifecycles differ.

## 24. MessageGroupStore and Timeouts When Keys Drift

Mutable values can create multiple **nearly complete** groups:

~~~text
Group old-email:
  OrderRegistered
  -> missing Payment and Inventory

Group new-email:
  PaymentCaptured
  InventoryReserved
  -> missing OrderRegistered
~~~

Consequences:

- `open_groups` climbs.
- Group age and expired group counts rise.
- The store consumes extra RAM/DB space.
- Results are delayed or missing.
- Operators assume events were lost in the broker even though all three arrived.

Increasing timeouts will not help, because the two groups still have **two different keys**.

### 24.1. Persistence and Concurrency

In-memory `SimpleMessageStore` suits demos/tests but does not survive restarts. When multiple JVMs handle parts of the same group:

- Partition by the same stable key to a single instance **or** use a shared store with proper locking.
- Keys must have consistent encoding/serialization.
- Prevent duplicate releases across instances.
- Ensure idempotency for outputs and downstream side effects.

### 24.2. Timeouts and Incomplete Outcomes

If a part fails to arrive before the deadline:

1. Safely record the group key and missing part types.
2. Distinguish genuine missing parts from key drift or ID mapping failures.
3. Apply expiry/cleanup and partial policies per contract.
4. Never emit `OrderReady` while `InventoryReserved` is missing.
5. Define handling for late arrivals after group expiry.

## 25. Observability for Correlation Key Quality

| Metric / Log Field | Purpose |
|---|---|
| `correlation_key_invalid_total` | Empty/malformed keys |
| `identity_resolution_failed_total` | Unmappable external IDs |
| `aggregation_open_groups` | Number of waiting groups |
| `aggregation_group_age_seconds` | Groups waiting too long |
| `aggregation_completed_total` | Released groups |
| `aggregation_expired_total` | Incomplete groups |
| `aggregation_duplicate_event_total` | Duplicate events |
| `aggregation_late_arrival_total` | Events arriving after group closure |
| `aggregation_output_key_mismatch_total` | Parts with mismatched business identity |
| `aggregation_idempotent_skip_total` | Blocked duplicate outputs |

A diagnostic log might include:

~~~text
flow=order-ready
eventType=PaymentCaptured
eventId=evt-p-101
businessKeyHash=approved-hash
correlationSource=canonical-order-id
partsPresent=[OrderRegistered,PaymentCaptured]
missing=[InventoryReserved]
release=false
groupAgeMs=38000
~~~

Never use email, phone, `orderId`, `eventId`, or `traceId` as **high-cardinality metric labels**. They can appear in security-controlled logs/traces, or be hashed/redacted appropriately.

### 25.1. Signs of Key Drift

- Same `eventId` after retry carries a different business key.
- Group expirations spike right after changing ID normalization logic.
- Many groups share a customer/email while parts are scattered across them.
- Producers report sending all events yet the Aggregator never releases.
- Only one tenant breaks after an ID migration.
- Single-part group counts climb unusually.

## 26. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Grouping by email | One order splits; two orders sharing email merge | Canonical order ID |
| Grouping by status | Each state creates a different group | Use status for Router/Filter |
| Grouping by amount | Price edits generate a new key | Amount is not identity |
| Grouping by `customerId` | Multiple orders of a customer mix | Key by order unit |
| Grouping by `traceId` | Independent services have different traces | Business correlation |
| Grouping by `eventId` | Each event forms its own group | Use `eventId` for dedup |
| Grouping by Message ID | Retries/new messages change IDs | Stable business ID |
| Grouping by `orderId` without tenant | Cross-tenant collisions | Trusted composite key |
| Including retry count in key | Replays open new groups | Separate retries from run identity |
| Random keys at consumer | Parts never converge | Allocate ID once at coordinator |
| Lowercasing every ID | Can merge case-sensitive IDs | Follow ID authority |
| Counting only `group.size()` | Duplicates mask missing parts | Release by part type, deduplicate |
| No expiry | Orphaned groups never clean up | Timeouts, expiry, metrics |
| Changing key format without migration | Old groups get stranded | Aliases/migration/reconciliation |
| Treating Aggregator as exactly-once | Duplicate side effects on replay | Idempotent handlers/outbox |

## 27. Practice Exercises

**Exercise 1 — Choosing a key:** given email, phone, `updatedAt`, status, amount, `orderId`, `tenantId`, and `eventId`, choose a group key for an `OrderReady` flow and explain why.

**Exercise 2 — Email change:** send `OrderRegistered` with the old email, then `PaymentCaptured` and `InventoryReserved` with the new email; assert one `OrderReady`.

**Exercise 3 — Two orders sharing an email:** send interleaved events for `ORDER-101`/`ORDER-102`; assert two separate outputs with no payment/inventory mixing.

**Exercise 4 — Two tenants sharing an ID:** send `tenant-a/ORDER-101` and `tenant-b/ORDER-101`; assert no cross-tenant merge.

**Exercise 5 — Status change:** write an anti-pattern using `orderId+status`; simulate NEW→PAID to prove the group splits.

**Exercise 6 — Replay:** send the same `eventId` with a different `MessageHeaders.ID`; the key must remain unchanged and deduplication must handle the copy.

**Exercise 7 — Case sensitivity:** test `order-101` and `ORDER-101`; decide whether to normalize or reject based on the ID contract.

**Exercise 8 — External reference:** map Payment's `EXT-5002` to `ORDER-101`; missing mappings must route to an error/reconciliation flow.

**Exercise 9 — Duplicates:** create a group with Order, Payment, and Payment; do not emit `OrderReady` and handle duplicates before the group stalls.

**Exercise 10 — Mutable map key:** use an object whose `equals/hashCode` depends on a mutable field; mutate the field after insertion and explain the lookup failure.

**Exercise 11 — Workflow run:** decide when to add `workflowRunId` and how to distribute the same ID to all producers.

**Exercise 12 — ID migration:** change `ORD-OLD-101` to `ORDER-101` while a group already holds two parts; design aliases and state migration.

**Exercise 13 — Timeout:** simulate a genuine missing part and bogus key drift, then use logs/metrics to tell them apart.

**Exercise 14 — Security:** payload claims `tenant-b` while principal is `tenant-a`; pinpoint where to reject before grouping.

**Exercise 15 — End-to-end:** wire canonicalization → Aggregator custom correlation → Router on `OrderReady`; test keys, release, output, and idempotency.

### Self-Check Questions

1. How does content-based correlation differ from content-based routing?
2. How can an email split one order into two groups?
3. `customerId` is stable, so why is it still wrong for order-level grouping?
4. Can two different groups ever share the same key?
5. How do correlation key, `eventId`, Message ID, and `traceId` differ?
6. When must `tenantId` accompany `orderId`?
7. When should `workflowRunId` be added?
8. Why should you never use a mutable object as a group key?
9. In what cases can lowercasing an ID cause collisions?
10. How should you handle a Payment event that carries only `externalOrderRef`?
11. Should a retry after an email update create a new group?
12. Why can `group.size()==3` still be missing Inventory?
13. Does a correct key automatically guarantee correct release?
14. When is a persistent `MessageGroupStore` required?
15. How should late arrivals after group release be handled?
16. Which states are affected when changing an ID format?
17. Why should raw `orderId` never be used as a metric label?
18. Which test catches cross-tenant group mixing?

## 28. Design Checklist

- [ ] Identify the exact business unit to converge before choosing a key.
- [ ] Key stays stable throughout the entire group lifecycle, including replays.
- [ ] Key distinguishes between two groups, including across tenants.
- [ ] All producers use a consistent canonical business identity.
- [ ] Tenant and ownership are authenticated at ingress.
- [ ] Email, phone, name, status, amount, and `updatedAt` are not used by default.
- [ ] `MessageHeaders.ID`, `traceId`, and `eventId` are not used in place of business group identity.
- [ ] Keys are never generated from clocks or random values during consumer processing.
- [ ] Validation rejects missing, mistyped, or malformed keys.
- [ ] Canonicalization is governed by the ID authority.
- [ ] Composite keys are immutable with collision-free encoding.
- [ ] Store/serializer/locking support the group key and version.
- [ ] External IDs are resolved prior to the Aggregator.
- [ ] Release policy checks all required data types, not raw message count alone.
- [ ] Deduplication by `eventId` and conflict policies are in place.
- [ ] Timeout/expiry and incomplete-group handling are defined.
- [ ] Late-arrival, correction, and retention policies exist.
- [ ] Downstream handlers are idempotent.
- [ ] Reprocessing/`workflowRunId` is designed when required.
- [ ] Migration/alias plan precedes any key-format change.
- [ ] Tests cover email changes, two orders sharing an email, and two tenants sharing an ID.
- [ ] Tests cover out-of-order arrivals, missing parts, duplicates, replays, and restarts as needed.
- [ ] Metrics track key drift, open groups, expiries, and output mismatches.
- [ ] PII/identifiers are not exposed in metrics or insufficiently restricted logs.

## 29. Summary

**Do Not Use Mutable Values as Correlation Keys** is a vital rule of content-based correlation. A field may work well for Filtering, Routing, or calculation while being completely unsuitable for **identifying messages belonging to the same business process**. Emails, phone numbers, statuses, amounts, or `updatedAt` can change; `customerId`, though stable, is still too broad when gathering by **a single order**.

In Spring Integration, choose a **stable canonical business identity**, such as `BusinessKey(tenantId,orderId)`, with IDs validated in the proper namespace. The correlation strategy selects the group; the release strategy decides when the group is complete; the output processor verifies invariants and produces `OrderReady`. Never confuse business keys with `eventId`, `traceId`, or sequence headers; pair them with duplicate handling and idempotency for retries/replays.

To operate reliably in **SPRING_INTEGRATION_PATTERN**, add an appropriate `MessageGroupStore`, expiry handling, migration/aliases, security, observability, and tests covering changing data scenarios. When keys are stable and properly scoped, Router, Filter, Aggregator, Resequencer, Gateway, and error/retry flows coordinate accurately across asynchronous processes.

### References

- Spring Integration Reference — Aggregator: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Integration Reference — Splitter: https://docs.spring.io/spring-integration/reference/splitter.html
- Spring Integration Reference — Resequencer: https://docs.spring.io/spring-integration/reference/resequencer.html
- Spring Integration Reference — Message Store: https://docs.spring.io/spring-integration/reference/message-store.html
- Spring Integration Reference — Router: https://docs.spring.io/spring-integration/reference/router.html
- Spring Integration Reference — Java DSL: https://docs.spring.io/spring-integration/reference/dsl.html
- Spring Integration API — CorrelationStrategy: https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/CorrelationStrategy.html
- Spring Integration API — ReleaseStrategy: https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/ReleaseStrategy.html
- Spring Integration API — MessageGroup: https://docs.spring.io/spring-integration/api/org/springframework/integration/store/MessageGroup.html
- Spring Integration API — SimpleMessageStore: https://docs.spring.io/spring-integration/api/org/springframework/integration/store/SimpleMessageStore.html
- JUnit 5 User Guide: https://junit.org/junit5/docs/current/user-guide/
