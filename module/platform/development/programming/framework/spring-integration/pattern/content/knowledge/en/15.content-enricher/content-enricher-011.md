# Distinguishing Enricher from Aggregator

In integration architectures built with **Spring Integration**, a message sometimes **lacks enough information for processing**: an order-placed event contains only `customerId` while the promotion branch needs the customer tier; or a workflow has separate `OrderPlaced`, `PaymentCaptured`, and `InventoryReserved` events that must converge before completion. Both problems look like "combining extra data," yet they do not use the same Enterprise Integration Pattern (EIP).

- **Content Enricher** supplements **an existing single message** with additional data, typically by looking up reference data or calling an auxiliary system.
- **Aggregator** collects **multiple messages belonging to the same group**, maintains group state, waits for a *release condition*, and emits one combined result message.

This article belongs to the **Content enricher** chapter of the **SPRING_INTEGRATION_PATTERN** module. The module focuses on implementing EIP with Spring Integration to build loosely coupled, extensible message flows—practicing Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation, while testing and observing every branch. The focus here is choosing **the right pattern by data source, message cardinality, data arrival timing, and completion mechanics**.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Explain Content Enricher and Aggregator in terms of inputs, outputs, and state.
2. Distinguish two forms of supplementary data: **on-demand lookup** versus **independent messages arriving over time**.
3. Know when Enricher fits, when Aggregator is required, and when to combine both.
4. Design an Enricher with an `OrderPlaced → EnrichedOrder` contract featuring lookup timeouts, missing-data controls, and testability.
5. Understand the dedicated `ContentEnricher` component versus using `@Transformer` to implement the same business intent.
6. Understand `correlationStrategy`, `releaseStrategy`, `MessageGroup`, `MessageGroupStore`, timeouts, and incomplete-group handling.
7. Build a Splitter → Aggregator example in Java DSL and verify sequence headers and aggregated results.
8. Design joins across independent events, handling arbitrary arrival order and preventing duplicates.
9. Explain trace/correlation propagation, enrichment errors, retries, idempotency, sensitive data, and progress observability.
10. Write unit and integration tests confirming **lookups are never confused with message aggregation**.

## 2. Two Problems That Look Similar Yet Differ Fundamentally

### 2.1. Problem A: An Order Missing Customer Information

A producer emits:

~~~text
OrderPlaced
  orderId: ORDER-1001
  customerId: CUST-21
  amount: 350.00
~~~

The promotion engine needs `customerTier` and `active` from the Customer Directory. A lookup request can be issued and answered immediately per contract:

~~~mermaid
flowchart LR
    O["OrderPlaced"] --> E["Content Enricher"]
    E -->|"lookup(CUST-21)"| D["Customer Directory"]
    D -->|"CustomerProfile"| E
    E --> R["EnrichedOrder"]
    R --> F["Filter / Router / Business Handler"]
~~~

From the main flow's perspective, **one** inbound message yields **one** enriched message. Returning an object from the lookup system does not make this an Aggregator; it is the result of a supplementary call to process **the original message**.

### 2.2. Problem B: Three Independent Events Must Converge

Independent producers emit over time:

~~~text
OrderPlaced(orderId=ORDER-1001)
PaymentCaptured(orderId=ORDER-1001)
InventoryReserved(orderId=ORDER-1001)
~~~

We cannot guarantee they arrive together or in order. The system must wait for all three facts for the **same `orderId`** and emit `OrderReady`:

~~~mermaid
flowchart LR
    A["OrderPlaced"] --> AG["Aggregator"]
    P["PaymentCaptured"] --> AG
    I["InventoryReserved"] --> AG
    AG -->|"correlation=orderId"| G["Message Group"]
    G -->|"all 3 types"| O["OrderReady"]
~~~

Here there are **three separate input messages** requiring **per-group state accumulation**. That is the job of an Aggregator, not a typical lookup Enricher.

### 2.3. Summary Comparison

~~~text
ENRICHER
  One message + fetched supplementary information
      → One richer message

AGGREGATOR
  Multiple messages sharing a correlation key
      → Held inside a group
      → When release condition holds
      → One aggregated result message
~~~

The **1→1** and **N→1** shorthand describes the conceptual *happy path*: when lookup fails, Enricher may emit no output; when a group expires or a partial-release policy triggers, Aggregator may emit a different outcome or no complete message. Do not treat them as an exact guarantee of one output in every scenario.

## 3. Enricher vs. Aggregator Comparison Table

| Dimension | Content Enricher | Aggregator |
|---|---|---|
| Purpose | Add missing facts to the message currently in flight | Combine related messages into a shared outcome |
| Primary input message count | Usually 1 | Multiple |
| Source of extra data | Lookup, service, cache, metadata, reference data | Independent messages from a Splitter or multiple producers |
| Group state over time | Usually unnecessary | Yes: `MessageGroup` and group lifecycle |
| Correlation key | Helpful for request–reply / tracing | **Core** for grouping messages accurately |
| Release strategy | No group release needed | **Core** for deciding when the group is complete |
| Arrival order of parts | Usually not the central concern | May be arbitrary and must be handled |
| Timeout | Lookup / request timeout | Group wait timeout or expiry |
| Retry | Retry transient query faults; avoid retrying missing static data | Retry delivery, deduplicate, idempotent group output |
| Storage | Optional cache / lookup | May require durable `MessageGroupStore` |
| Output | Enriched record | Aggregated record / collection / result |
| Spring Integration | `ContentEnricher` (payload enrichment), `HeaderEnricher`, `@Transformer` / Java DSL | Aggregating endpoint, `.aggregate(...)`, correlation/release strategies |
| Characteristic risks | Slow lookup, missing profile, stale cache, N+1 requests | Incomplete groups forever, duplicates, late arrivals, memory growth |
| Pattern selection question | "Where do I fetch extra fields for this message?" | "Which messages belong to the same group and when is the group done?" |

**The decisive distinction:** *how supplementary data relates to the message*. If an explicit request–reply call can fetch the profile for the current order, Enricher usually fits. If data **arrives as separate messages at independent times**, you need a correlation-and-wait mechanism—an Aggregator or a dedicated process manager.

## 4. What Is a Content Enricher?

A Content Enricher receives a message, determines what information is missing, gathers it from an appropriate source, and merges it into the payload or message so downstream endpoints can use it.

A common cycle:

1. Receive `OrderPlaced` carrying `customerId`.
2. Send a lookup request for `CustomerProfile` to an adapter, service, or cache.
3. Verify the result is present, matches the customer, satisfies access permissions, and fits the type contract.
4. Construct `EnrichedOrder` combining original order data and enriched fields.
5. Forward the resulting message to downstream validation, Filter, or Router.

In Spring Integration, the **dedicated Content Enricher** is implemented by `ContentEnricher` for payload enrichment; Java DSL offers `.enrich(...)`. However, if you want to build **a completely new immutable DTO** and only need transformation, a `@Transformer` calling an enrichment service can express the same EIP intent. That is an **implementation choice**—not a claim that `@Transformer` and `ContentEnricher` are the same class.

### 4.1. How Does Enricher Differ from Transformer?

| Goal | Typical Tool |
|---|---|
| Convert entire payload representation, e.g., `RawOrder` → `TypedOrder` | Transformer |
| Populate `customerTier` on order data from a lookup reply | Content Enricher |
| Add verified `traceId`/`tenantId` to headers | Header Enricher |
| Build an immutable `EnrichedOrder` from `OrderPlaced` + profile | Transformer acting in an Enricher role |
| Join three async outcomes outside a single request–reply | Aggregator |

A `ContentEnricher` can operate via expressions/properties on the payload object; with mutable JavaBeans this may mutate properties in place. If the application requires **data immutability**, prefer creating a new DTO per contract and testing that the input object is never mutated.

### 4.2. Inputs, Outputs, and Invariants

Java 17+ domain example:

~~~java
import java.math.BigDecimal;

public record OrderPlaced(
        String eventId,
        String orderId,
        String customerId,
        BigDecimal total
) {}

public record CustomerProfile(
        String customerId,
        String tier,
        boolean active
) {}

public record EnrichedOrder(
        String eventId,
        String orderId,
        String customerId,
        BigDecimal total,
        String tier,
        boolean customerActive
) {}
~~~

These `public record` types are shown in one code block for easy comparison; in a Java project, place each top-level `public` declaration in its **own source file** matching its name.

The three records play distinct roles:

- `OrderPlaced` is the inbound event, knowing only IDs and order details.
- `CustomerProfile` is reference data obtained from lookup.
- `EnrichedOrder` is the output consumed downstream.

Avoid passing around a generic `Map<String, Object>` and calling `put("tier", ...)` arbitrarily across endpoints. Typed DTOs make enriched fields explicit and prevent key typos.

## 5. Writing a Testable Enricher

We separate **fetching the profile** from **combining results**, allowing combination logic to be unit-tested in plain Java without a broker or database.

### 5.1. Lookup Contract

~~~java
import java.util.Optional;

@FunctionalInterface
public interface CustomerDirectory {
    Optional<CustomerProfile> findById(String customerId);
}
~~~

Returning `Optional<CustomerProfile>` signals that a lookup **may find no record**. That does not mean a network failure: "not found" and "lookup failed" must be classified separately.

### 5.2. Meaningful Exception

~~~java
public final class CustomerProfileMissingException
        extends RuntimeException {

    public CustomerProfileMissingException(String customerId) {
        super("CUSTOMER_PROFILE_MISSING: " + customerId);
    }
}
~~~

In production, exception text sent to clients or logs may need **identifier masking/hashing** per personal-data policies. The example above keeps logic clear for learners; large systems should rely on stable error codes rather than concatenating untrusted input into messages.

### 5.3. Enrichment Service

~~~java
import java.util.Objects;

public final class OrderContentEnricher {

    private final CustomerDirectory directory;

    public OrderContentEnricher(CustomerDirectory directory) {
        this.directory =
                Objects.requireNonNull(directory, "directory");
    }

    public EnrichedOrder enrich(OrderPlaced order) {
        Objects.requireNonNull(order, "order");

        if (order.customerId() == null
                || order.customerId().isBlank()) {
            throw new IllegalArgumentException(
                    "customerId is required");
        }

        CustomerProfile profile = directory
                .findById(order.customerId())
                .orElseThrow(() ->
                        new CustomerProfileMissingException(
                                order.customerId()));

        // Guard against lookup returning the wrong profile due to cache/mapping.
        if (!order.customerId().equals(profile.customerId())) {
            throw new IllegalStateException(
                    "CUSTOMER_PROFILE_ID_MISMATCH");
        }

        return new EnrichedOrder(
                order.eventId(),
                order.orderId(),
                order.customerId(),
                order.total(),
                profile.tier(),
                profile.active());
    }
}
~~~

Here `OrderContentEnricher` performs one lookup and builds a **new** DTO. Combining the data leaves the original `OrderPlaced` untouched. In real systems, also enforce that the retrieved profile **belongs to an authorized tenant/customer**. Checking `customerId` equality validates data consistency but cannot replace authorization.

### 5.4. What Happens When Lookup Is Slow or Fails?

If `CustomerDirectory` is backed by REST or a database:

- A request can take hundreds of milliseconds or time out.
- The enrichment endpoint can become the bottleneck of the whole flow.
- Retrying lookup can help on transient network errors.
- Profile not found is a **business outcome**, usually not suited for endless retries.
- The returned profile may be **stale** if a cache has not refreshed yet.
- Across many orders for the same `customerId`, repeated lookups trigger N+1 requests.

Configure timeouts, cache TTLs, circuit breakers, bulkheads, and concurrency limits at the adapter layer. Do not try to fix slow lookups by replacing Enricher with Aggregator when there are no **independent messages** actually needing correlation.

## 6. Integrating Enricher into Spring Integration

A clean option for immutable DTOs is a `@Transformer` endpoint implementing the content-enrichment intent:

~~~java
import org.springframework.integration.annotation.Transformer;

public final class OrderEnrichmentEndpoint {

    private final OrderContentEnricher enricher;

    public OrderEnrichmentEndpoint(OrderContentEnricher enricher) {
        this.enricher = enricher;
    }

    @Transformer(
            inputChannel = "orders.toEnrich",
            outputChannel = "orders.enriched")
    public EnrichedOrder enrich(OrderPlaced order) {
        return enricher.enrich(order);
    }
}
~~~

**Note:** this is a **Transformer acting in the Content Enricher role**, not configuration of the dedicated `ContentEnricher` component. It works well when you want an immutable output record and isolated unit testing.

### 6.1. Configuring a Testable Flow

~~~java
import java.util.Map;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class OrderEnrichmentConfiguration {

    @Bean(name = "orders.toEnrich")
    public MessageChannel input() {
        return new DirectChannel();
    }

    @Bean(name = "orders.enriched")
    public PollableChannel enriched() {
        return new QueueChannel();
    }

    @Bean
    public CustomerDirectory customerDirectory() {
        Map<String, CustomerProfile> fixtures = Map.of(
                "CUST-21",
                new CustomerProfile("CUST-21", "GOLD", true),
                "CUST-22",
                new CustomerProfile("CUST-22", "STANDARD", true));

        // Illustrative only: replace with a REST/DB adapter in production.
        return customerId ->
                Optional.ofNullable(fixtures.get(customerId));
    }

    @Bean
    public OrderContentEnricher contentEnricher(
            CustomerDirectory directory) {
        return new OrderContentEnricher(directory);
    }

    @Bean
    public OrderEnrichmentEndpoint orderEnrichmentEndpoint(
            OrderContentEnricher enricher) {
        return new OrderEnrichmentEndpoint(enricher);
    }
}
~~~

`QueueChannel` in the example exists only to receive results in JUnit; it is not durable across restarts. In real deployments, downstream is typically a Filter, Router, or Service Activator.

### 6.2. Message with Trace/Correlation

~~~java
import java.math.BigDecimal;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

OrderPlaced order = new OrderPlaced(
        "evt-1001",
        "ORDER-1001",
        "CUST-21",
        new BigDecimal("350.00"));

Message<OrderPlaced> input = MessageBuilder
        .withPayload(order)
        .setHeader("traceId", "trace-1001")
        .setHeader("businessCorrelationId", "ORDER-1001")
        .build();
~~~

Sending this message to `orders.toEnrich` produces an `EnrichedOrder` payload with `tier="GOLD"`. When a Transformer returns a payload, the framework builds the output message and normally propagates relevant inbound headers; the test section below verifies `traceId` directly.

### 6.3. Dedicated `ContentEnricher` for Payloads

Spring Integration includes `ContentEnricher` and Java DSL `.enrich(...)`. It can send an **enrichment request** to a request channel, receive a reply, and use property expressions to populate payload properties. Architecturally:

~~~text
orders.input
  -> ContentEnricher
       -> enrichment request
       -> customer.lookup.request
       <- customer.lookup.reply
       -> merge returned data into payload by property mapping
  -> orders.enriched
~~~

Checklist before choosing this component:

1. Select **what data to send** to the lookup source, e.g., only `customerId`.
2. Select **target properties** to update, e.g., `customerTier`.
3. Ensure the reply matches the type/shape expected by expressions.
4. Define timeouts, missing-reply handling, and lookup failures.
5. Control payload copying vs. mutation per your model and configuration.
6. Test results end-to-end across actual channels.

If the payload is an immutable `record` with no setters, do not assume property-enrichment configuration can write extra fields onto the record directly. In that case, **building a new `EnrichedOrder` via a Transformer** is often simpler and safer. What matters is the **pattern** (enriching information), not forcing a single Spring Integration class.

## 7. What Is an Aggregator and Why Does It Need Correlation?

An Aggregator receives multiple messages, groups them by a **correlation key**, maintains state for each group, and decides when to emit an aggregated result.

~~~mermaid
flowchart TB
    O["OrderPlaced(orderId=A)"] --> C{"correlationStrategy"}
    P["PaymentCaptured(orderId=A)"] --> C
    I["InventoryReserved(orderId=A)"] --> C
    C --> G["MessageGroup for A"]
    G --> R{"releaseStrategy"}
    R -->|Not complete| WAIT["Keep waiting"]
    R -->|Complete| M["Output processor"]
    M --> READY["OrderReady(A)"]
~~~

Two **indispensable strategies**:

- **Correlation strategy:** decides **which group** a message belongs to, e.g., `orderId`.
- **Release strategy:** decides whether the group has **enough information to emit a result**.

Also required:

- **Message Group Store:** holds messages and group metadata.
- **Aggregation output processor:** combines the group's payloads into a result.
- **Expiry / timeout:** handles groups waiting too long, missing parts, or late messages.
- **Duplicate / late arrival handling:** avoids premature releases or reprocessing a part multiple times.

### 7.1. Accurate Correlation Is a Data-Safety Prerequisite

Suppose there are two orders:

~~~text
A: OrderPlaced(A), PaymentCaptured(A), InventoryReserved(A)
B: OrderPlaced(B), PaymentCaptured(B), InventoryReserved(B)
~~~

The Aggregator must build **two independent groups**, A and B. If correlation were keyed by `customerId`, separate orders for the same customer would be **merged together by mistake**. Here `orderId` is the right candidate.

In multi-tenant systems, `orderId` alone may still collide across tenants. A safe key can be `(tenantId, orderId)` where `tenantId` was **authenticated** at ingress.

### 7.2. Release Is Not Simply Counting Three Messages

A naive design:

~~~text
release when group.size() == 3
~~~

breaks if a producer emits two `PaymentCaptured` messages and one `OrderPlaced` while `InventoryReserved` is still missing: the group reaches three messages **by count** yet lacks a required part.

For independent events, a better release strategy checks that **all required event types are present**, handles duplicates, picks the latest/valid version, and avoids picking arbitrary messages blindly.

### 7.3. Aggregator Does Not Imply Splitter

A **Splitter** produces multiple messages from one input; an **Aggregator** can recombine them. However, an Aggregator can also gather **multiple independent sources** without any upstream Splitter.

- Splitter typically sets `correlationId`, `sequenceNumber`, and `sequenceSize`.
- Default Aggregators leverage those headers to form groups and know when all parts arrived.
- When events arrive from three independent producers, reliable `sequenceSize` metadata rarely exists—custom correlation and release strategies are required.

## 8. Spring Integration Example: Splitter → Aggregator

A self-contained example distinguishes Aggregator from Enricher without mocking three async systems: a batch containing multiple order lines is split, priced per line, and re-aggregated.

### 8.1. Payload Types

~~~java
import java.math.BigDecimal;

public record OrderLine(
        String sku,
        BigDecimal unitPrice,
        int quantity
) {}

public record PricedLine(
        String sku,
        BigDecimal lineTotal
) {}
~~~

An inbound `List<OrderLine>` is **one message holding a collection**. Splitter creates one message per element, linked by correlation/sequence headers.

### 8.2. Illustrative Java DSL

~~~java
import java.math.BigDecimal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class OrderLinesAggregationConfiguration {

    @Bean
    public IntegrationFlow orderLinesFlow() {
        return IntegrationFlow.from("order.lines.batch")
                .split()
                .transform(OrderLine.class, line ->
                        new PricedLine(
                                line.sku(),
                                line.unitPrice().multiply(
                                        BigDecimal.valueOf(line.quantity()))))
                .aggregate()
                .channel("order.lines.aggregated")
                .get();
    }
}
~~~

How it works:

1. `split()` turns elements in the batch into individual messages.
2. `transform(...)` computes `PricedLine` for each message.
3. `aggregate()` groups messages using the correlation/sequence headers provided by Splitter.
4. Once all elements satisfy the default release strategy, the output is a single combined message. With the default aggregation processor for collections, the payload is typically a **collection of the resulting payloads**.
5. `order.lines.aggregated` receives the result; declare/inspect the output channel in your app or tests.

**This is an Aggregator example**: even though the producer sent a single batch message initially, **after Splitter** multiple independent messages traverse the pipeline and are recombined by an endpoint holding group state.

### 8.3. Inspecting Splitter-Generated Metadata

Messages leaving Splitter typically carry:

~~~text
correlationId: batch group ID
sequenceNumber: 1, 2, 3, ...
sequenceSize: number of elements in the batch
~~~

Spring Integration's default Aggregator relies on these headers; never fabricate fake `sequenceSize` values to merge unrelated messages.

### 8.4. What If a Filter Drops One Item?

~~~mermaid
flowchart LR
    B["Batch 3 lines"] --> S["Splitter"]
    S --> L1["Line 1"]
    S --> L2["Line 2"]
    S --> L3["Line 3"]
    L1 --> A["Aggregator"]
    L2 --> F{"Filter"}
    F -->|Rejected| D["Discard"]
    L3 --> A
~~~

If Splitter sets `sequenceSize=3` yet a Filter drops one message, the default Aggregator waits for **three parts** and never releases under the original rule. You must decide to:

- Emit a placeholder result for the dropped item so the group completes;
- Customize the release strategy per business contract;
- Configure timeouts and partial-group policies;
- Or Filter *before* Splitter to compute the true element count up front.

**Group waiting** issues are characteristic of Aggregators, not Enrichers.

## 9. Aggregator for Multiple Independent Events

When Order, Payment, and Inventory events come from three separate services, design the contract before writing DSL.

### 9.1. Event Types

~~~java
import java.math.BigDecimal;

public sealed interface OrderPart
        permits OrderRegistered, PaymentCaptured, InventoryReserved {
    String orderId();
}

public record OrderRegistered(
        String orderId,
        String customerId,
        BigDecimal amount
) implements OrderPart {}

public record PaymentCaptured(
        String orderId,
        String paymentId
) implements OrderPart {}

public record InventoryReserved(
        String orderId,
        String reservationId
) implements OrderPart {}

public record OrderReady(
        String orderId,
        String customerId,
        BigDecimal amount,
        String paymentId,
        String reservationId
) {}
~~~

Top-level `public` declarations are grouped here for readability; split them into matching Java source files in a real project.

A valid `OrderPart` group requires at least one record of **each type**. For duplicate events, define a rule selecting the right version/ID instead of arbitrarily picking the first item.

### 9.2. Plain Java Assembly Logic

~~~java
import java.util.List;

public final class OrderPartAssembler {

    public boolean hasRequiredParts(List<OrderPart> parts) {
        return parts.stream().anyMatch(OrderRegistered.class::isInstance)
                && parts.stream().anyMatch(PaymentCaptured.class::isInstance)
                && parts.stream().anyMatch(InventoryReserved.class::isInstance);
    }

    public OrderReady assemble(List<OrderPart> parts) {
        if (!hasRequiredParts(parts)) {
            throw new IllegalArgumentException(
                    "ORDER_PARTS_INCOMPLETE");
        }

        OrderRegistered order = exactlyOne(parts, OrderRegistered.class);
        PaymentCaptured payment = exactlyOne(parts, PaymentCaptured.class);
        InventoryReserved inventory =
                exactlyOne(parts, InventoryReserved.class);

        if (!order.orderId().equals(payment.orderId())
                || !order.orderId().equals(inventory.orderId())) {
            throw new IllegalArgumentException(
                    "MISMATCHED_ORDER_ID");
        }

        return new OrderReady(
                order.orderId(),
                order.customerId(),
                order.amount(),
                payment.paymentId(),
                inventory.reservationId());
    }

    private <T extends OrderPart> T exactlyOne(
            List<OrderPart> parts, Class<T> type) {
        List<T> matches = parts.stream()
                .filter(type::isInstance)
                .map(type::cast)
                .toList();

        if (matches.size() != 1) {
            throw new IllegalArgumentException(
                    "DUPLICATE_OR_MISSING_" + type.getSimpleName());
        }
        return matches.get(0);
    }
}
~~~

This function intentionally **rejects duplicates** rather than silently picking the latest one, because tie-breaking is a business rule that must be explicit. In production, deduplicate by `eventId` before the Aggregator, or track trusted versions/timestamps for updates and corrections.

### 9.3. Correlation Strategy

For messages carrying `OrderPart`:

~~~java
import org.springframework.messaging.Message;

public Object correlationKey(Message<?> message) {
    OrderPart part = (OrderPart) message.getPayload();
    return part.orderId();
}
~~~

This is an **illustrative function** for the Aggregator adapter. In multi-tenant systems, build an immutable composite key combining verified `tenantId` and `orderId`. Never treat raw `orderId` from an unauthenticated producer as proof of ownership.

### 9.4. Release Strategy

You can check that the group contains all three types:

~~~java
import java.util.List;
import java.util.stream.Collectors;

import org.springframework.integration.store.MessageGroup;
import org.springframework.messaging.Message;

public boolean shouldRelease(
        MessageGroup group, OrderPartAssembler assembler) {
    List<OrderPart> parts = group.getMessages().stream()
            .map(Message::getPayload)
            .map(OrderPart.class::cast)
            .collect(Collectors.toList());

    return assembler.hasRequiredParts(parts);
}
~~~

This checks only **event-type completeness**; to prevent duplicates, also check per-type counts or deduplicate before storing into the group. A release strategy alone does not guarantee exactly-once.

### 9.5. Mapping to Spring Integration Aggregator

Spring Integration supports `.aggregate(...)` with `correlationStrategy`, `releaseStrategy`, and `outputProcessor`. The proper architecture looks like:

~~~text
order.parts.input
  -> Aggregator
       correlationStrategy(message) = orderId
       releaseStrategy(group) = has all OrderRegistered,
                                PaymentCaptured, InventoryReserved
       outputProcessor(group) = OrderPartAssembler.assemble(...)
       group timeout / expiry / message store / duplicate policy
  -> orders.ready
~~~

This is a **configuration outline**, not copy-pasteable Java DSL. Wire each function into the Aggregator per your Spring Integration version's API, and configure group timeouts and a `MessageGroupStore` if durability is required. Do not confuse these methods with `ContentEnricher`'s API.

### 9.6. Why Is `MessageGroupStore` Needed?

Suppose `PaymentCaptured` arrives at 10:00 and `InventoryReserved` arrives at 10:05. In between, the Aggregator must hold the group's messages somewhere. Spring Integration uses `MessageGroupStore` to persist groups.

- A simple in-memory store fits tests and prototypes.
- If survival across restarts is required, configure a durable backing store and test transactions/recovery.
- When groups never complete, enforce timeouts/expiry/eviction to prevent unbounded memory growth.
- When events arrive late after group release, define late-arrival/reopen/reject policies.
- If two app instances aggregate the same `orderId`, address locking, shared stores, and delivery routing.

A standard Enricher does not need a **group store** waiting on three independent events.

## 10. Why Not Replace Aggregator with Enricher?

It can seem tempting: when `OrderPlaced` arrives, have an Enricher call `paymentStatus(orderId)` and `inventoryStatus(orderId)` to add the data. That **can work**, yet only when those APIs already hold a consistent snapshot and immediate query semantics are acceptable.

Problems appear when:

1. `OrderPlaced` arrives before Payment/Inventory events even exist.
2. Enricher polls APIs repeatedly while state is not yet ready.
3. Messages sit blocked, retrying, or polling wastefully.
4. State changes between two lookups, yielding an inconsistent snapshot.
5. When one API goes down, the entire pipeline stalls.
6. There are no clear rules for completion, expiration, or late arrivals.

When pieces of data **are emitted as independent events**, Aggregator addresses **waiting and correlating** much more directly. Still, **Aggregator does not automatically guarantee consistency or exactly-once** either; it requires contracts, duplicate policies, stores, and error handling.

### 10.1. When Is an Enricher Lookup Still Appropriate?

- Customer profile already exists when `OrderPlaced` is processed.
- Data is stable reference data or has an explicit TTL.
- Enrichment does not have to wait for future events.
- Request–reply timeout fits inside the latency budget.
- **Immediate output** per order is expected.
- Lookup data is authorized for the verified tenant/principal.

### 10.2. When Is an Aggregator More Appropriate?

- Multiple independent messages arrive from different sources.
- Arrival times and ordering are non-deterministic.
- Downstream must wait for complete data before emitting a result.
- Grouping by `orderId` or a business correlation key is needed.
- Timeouts, incomplete groups, duplicates, and late arrivals must be managed.
- Group state persistence and crash recovery may be required.

## 11. When to Combine Both Enricher and Aggregator?

In real systems, the two patterns do not compete—they **complement** each other.

Example workflow:

1. `OrderPlaced` arrives.
2. Enricher queries Customer Directory to add customer tier and status.
3. Payment service emits `PaymentCaptured`.
4. Inventory service emits `InventoryReserved`.
5. Aggregator groups all three messages by `orderId` and emits `OrderReady`.
6. Router selects priority vs. standard based on enriched data.
7. Handler persists the outcome and emits events idempotently.

~~~mermaid
flowchart TB
    OP["OrderPlaced"] --> EN["Content Enricher"]
    REF["Customer Directory"] -.->|"lookup"| EN
    EN --> EO["EnrichedOrderPlaced"]
    EO --> AG["Aggregator: orderId"]
    PAY["PaymentCaptured"] --> AG
    INV["InventoryReserved"] --> AG
    AG --> OK["OrderReady"]
    OK --> ROUTER{"Router"}
    ROUTER --> PRI["Priority handler"]
    ROUTER --> STD["Standard handler"]
~~~

To implement this, align the **schema** entering the Aggregator: either define a sealed hierarchy covering the three inputs after enrichment, or use adapters converting them into a shared format. `EnrichedOrderPlaced` is one part of the group, not the final output message.

## 12. Different Error and Retry Paths

### 12.1. Enricher Failures

Example when Customer Directory lookup times out:

~~~text
OrderPlaced -> Enricher -> Customer Directory timeout
                          -> bounded retry
                          -> intentional error channel / quarantine / fallback
~~~

Classification:

| Failure | Handling Direction |
|---|---|
| Blank customer ID | Validation/rejection, never retry forever |
| Profile not found | Business rule: reject or explicit fallback |
| HTTP 503 / timeout | Bounded retry, backoff, circuit breaker |
| Profile from wrong tenant | Security/contract violation |
| Stale cache | Manage TTL/version, refresh per policy |
| `EnrichedOrder` construction fails | Error flow, never forward half-valid objects |

**Defaulting to `tier="STANDARD"`** is valid only if the contract permits it. Never use it to mask unreachable profiles in flows needing accurate customer entitlements.

### 12.2. Aggregator Failures

Example when `OrderPlaced` and `PaymentCaptured` arrive, yet `InventoryReserved` never arrives:

~~~text
group(orderId=ORDER-1001)
  OrderPlaced        arrived
  PaymentCaptured    arrived
  InventoryReserved  missing
  ---> timeout / expiry / incomplete-group policy
~~~

This is not a simple Enricher request timeout. There is **group state** to hold, evict, alert on, or emit as a partial result per contract.

| Failure / Event | Handling Direction |
|---|---|
| Missing part | Timeout, expiry, alert, partial result if permitted |
| Duplicate `PaymentCaptured` | Deduplicate by event ID or reject |
| Invalid `orderId` | Validate/reject before adding to group |
| Message from another tenant | Correlate with authenticated tenant |
| Late arrival after release | Reopen, reject, or compensate per policy |
| Process restart | Durable group store if required |
| Duplicate processing of aggregated output | Downstream idempotency |

### 12.3. Error Channels in Sync/Async Flows

On a synchronous `DirectChannel`, exceptions from an Enricher may propagate to the caller; in async flows, errors can be published as `ErrorMessage` per error-channel/adapter configuration. Aggregators may trigger on arrivals, timeouts, or expiry; error observability must reference the **group ID** and outcome, not just one request message.

**Never assume setting an `errorChannel` header automatically sends every endpoint error there.** Integration-test against your real topology.

## 13. Correlation: Same Word, Different Jobs

Both Enricher and Aggregator mention "correlation," yet their goals differ.

### Enricher

- `customerId` is used to **look up** the customer profile.
- `traceId` traces the request–reply call.
- `businessCorrelationId` tracks the order's lifecycle.
- Having `customerId` **does not mean** creating a `MessageGroup`.

### Aggregator

- `orderId` or composite `tenantId+orderId` serves as the **correlation key**.
- All parts sharing that key enter the same group.
- `sequenceNumber` and `sequenceSize` (when trustworthy) signal group completeness.
- Individual messages' `MessageHeaders.ID` cannot be used as the correlation key because every message has a distinct ID.

### Contrast Example

~~~text
Order A, customer CUST-21 -> enrichment lookup(CUST-21)
Order B, customer CUST-21 -> enrichment lookup(CUST-21)

Aggregator:
  group A = messages with orderId=A
  group B = messages with orderId=B

Never merge Order A and Order B just because they share customerId.
~~~

Mixing two orders for the same customer into one group is a severe data-design bug leading to corrupted payment or inventory outcomes.

## 14. Synchronous, Asynchronous, and Latency Characteristics

### 14.1. Enricher Can Block Threads

When an Enricher calls a synchronous HTTP service, the processing thread waits for the response. At high message volume:

- Keep timeouts short enough to fit the request budget.
- Bound concurrency and lookup connections.
- Cache profiles within contract freshness rules.
- Consider batch lookups when many messages share keys.
- Never let one failing external API stall the entire system.

An Enricher can sit inside an async channel pipeline; that **does not** turn the lookup itself into an Aggregator.

### 14.2. Aggregator Holds Waiting State

An Aggregator accepts messages arriving at different times and holds the group until complete. Output latency depends on the **slowest part** or the timeout policy.

- Track open group counts and group age metrics.
- Enforce memory/store bounds, expiry, and retention policies.
- Understand locking and concurrency when parts of the same group arrive simultaneously.
- Handle out-of-order events, using versions/dedup when parts are revised.
- Define partial outcomes when deadlines expire.

An Aggregator does not make messages durable simply by holding a group: the `MessageGroupStore` implementation determines durability.

## 15. Preserving Payload, Headers, and Access Control

### 15.1. For Enricher

When constructing a new `EnrichedOrder`, preserve metadata needed downstream:

~~~text
traceId
businessCorrelationId
sourceSystem (verified)
schemaVersion
replyChannel / errorChannel (when internal topology needs it)
~~~

In the `@Transformer` example returning a payload, the framework typically copies eligible headers to the output. If you build `Message<?>` manually, manage header propagation explicitly. When crossing a broker or HTTP API, **never copy blindly** internal reply/error channel objects, tokens, or sensitive headers.

### 15.2. For Aggregator

Messages entering a group can come from different sources with **conflicting headers**. Do not assume the Aggregator's output preserves every header conflict-free. Design explicitly:

- Group correlation ID.
- Trace context spanning the group and its parts.
- Trusted tenant/security context.
- Precedence rules when source headers differ.
- Clear output schema rather than letting one arbitrary part represent the whole group.

With `DefaultAggregatingMessageGroupProcessor`, Spring Integration follows built-in header-merging rules; if business logic requires specific metadata, test it or write a custom output processor. Never assume one part's `replyChannel` automatically serves as the reply channel for a multi-source group.

### 15.3. Preventing Multi-Tenant Data Mixing

Enricher must enforce access permissions when querying Customer Directory. Aggregator must never combine messages from two tenants even if their `orderId`s match. **Both** require security boundaries, applied in different places: reference-data lookup versus message grouping.

## 16. Unit Testing Enricher Without a Spring Context

`OrderContentEnricher` can be tested directly with a stub `CustomerDirectory`.

### 16.1. Successful Enrichment

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.Optional;

import org.junit.jupiter.api.Test;

class OrderContentEnricherTest {

    @Test
    void addsCustomerTierWithoutMutatingOrder() {
        CustomerDirectory directory = id ->
                Optional.of(new CustomerProfile(
                        id, "GOLD", true));

        OrderContentEnricher enricher =
                new OrderContentEnricher(directory);

        OrderPlaced original = new OrderPlaced(
                "evt-1", "ORDER-1001", "CUST-21",
                new BigDecimal("350.00"));

        EnrichedOrder result = enricher.enrich(original);

        assertEquals("ORDER-1001", result.orderId());
        assertEquals("CUST-21", result.customerId());
        assertEquals("GOLD", result.tier());
        assertTrue(result.customerActive());
        assertEquals(
                new BigDecimal("350.00"), result.total());

        // Input record retains original data.
        assertEquals("CUST-21", original.customerId());
        assertEquals(
                new BigDecimal("350.00"), original.total());
    }
}
~~~

This test verifies domain enrichment/conversion; it does not prove Spring routed messages to the right channels.

### 16.2. Missing Profile Fails Intentionally

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.Optional;

import org.junit.jupiter.api.Test;

class MissingCustomerProfileTest {

    @Test
    void doesNotInventTierWhenProfileMissing() {
        CustomerDirectory missing =
                customerId -> Optional.empty();

        OrderContentEnricher enricher =
                new OrderContentEnricher(missing);

        OrderPlaced order = new OrderPlaced(
                "evt-2", "ORDER-1002", "CUST-404",
                new BigDecimal("200.00"));

        assertThrows(CustomerProfileMissingException.class,
                () -> enricher.enrich(order));
    }
}
~~~

No default tier is fabricated here. If the product has a fallback policy, separate it as explicit, tested logic—never turn HTTP/timeout errors into `Optional.empty()` and mask the root cause.

### 16.3. Lookup Returns Wrong `customerId`

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.Optional;

import org.junit.jupiter.api.Test;

class ProfileConsistencyTest {

    @Test
    void rejectsProfileForAnotherCustomer() {
        CustomerDirectory corrupted = id ->
                Optional.of(new CustomerProfile(
                        "OTHER-CUSTOMER", "GOLD", true));

        OrderContentEnricher enricher =
                new OrderContentEnricher(corrupted);

        OrderPlaced order = new OrderPlaced(
                "evt-3", "ORDER-1003", "CUST-21",
                new BigDecimal("300.00"));

        IllegalStateException error =
                assertThrows(IllegalStateException.class,
                        () -> enricher.enrich(order));

        assertEquals(
                "CUSTOMER_PROFILE_ID_MISMATCH",
                error.getMessage());
    }
}
~~~

For multi-tenant data, add access-control and tenant-scope tests at the lookup adapter. Matching IDs alone is insufficient if two systems do not share a namespace.

## 17. Integration Testing Enricher Across Channels

Unit tests do not verify that the `@Transformer` endpoint is registered, output channels exist, or trace headers survive. A Spring Test checks the topology.

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

@SpringJUnitConfig(classes = OrderEnrichmentConfiguration.class)
class OrderEnrichmentFlowTest {

    @Autowired
    @Qualifier("orders.toEnrich")
    MessageChannel input;

    @Autowired
    @Qualifier("orders.enriched")
    PollableChannel output;

    @Test
    void enrichesAndPreservesTracing() {
        OrderPlaced order = new OrderPlaced(
                "evt-1",
                "ORDER-1001",
                "CUST-21",
                new BigDecimal("350.00"));

        assertTrue(input.send(
                MessageBuilder.withPayload(order)
                        .setHeader("traceId", "trace-1001")
                        .setHeader("businessCorrelationId",
                                "ORDER-1001")
                        .build()));

        Message<?> result = output.receive(1000);
        assertNotNull(result);
        assertInstanceOf(
                EnrichedOrder.class, result.getPayload());

        EnrichedOrder enriched =
                (EnrichedOrder) result.getPayload();

        assertEquals("GOLD", enriched.tier());
        assertEquals("ORDER-1001", enriched.orderId());
        assertEquals(
                "trace-1001",
                result.getHeaders().get("traceId"));
        assertEquals(
                "ORDER-1001",
                result.getHeaders().get("businessCorrelationId"));
    }
}
~~~

With `DirectChannel` and an in-memory lookup fixture, the example runs synchronously. When backed by a real HTTP client, use a stub server or fake adapter in tests to avoid network flakiness. `send() == true` does not prove downstream steps completed in asynchronous flows.

## 18. Testing Aggregator and Group Lifecycle

### 18.1. Unit Testing Assembly Under Arbitrary Arrival Order

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;

class OrderPartAssemblerTest {

    private final OrderPartAssembler assembler =
            new OrderPartAssembler();

    @Test
    void assemblesPartsRegardlessOfArrivalOrder() {
        List<OrderPart> parts = List.of(
                new InventoryReserved("ORDER-9", "RES-9"),
                new OrderRegistered(
                        "ORDER-9",
                        "CUST-9",
                        new BigDecimal("900.00")),
                new PaymentCaptured("ORDER-9", "PAY-9"));

        assertTrue(assembler.hasRequiredParts(parts));

        OrderReady result = assembler.assemble(parts);

        assertEquals("ORDER-9", result.orderId());
        assertEquals("CUST-9", result.customerId());
        assertEquals("PAY-9", result.paymentId());
        assertEquals("RES-9", result.reservationId());
    }

    @Test
    void rejectsGroupWithoutInventoryPart() {
        List<OrderPart> incomplete = List.of(
                new OrderRegistered(
                        "ORDER-9",
                        "CUST-9",
                        new BigDecimal("900.00")),
                new PaymentCaptured("ORDER-9", "PAY-9"));

        assertFalse(assembler.hasRequiredParts(incomplete));

        assertThrows(
                IllegalArgumentException.class,
                () -> assembler.assemble(incomplete));
    }

    @Test
    void rejectsDuplicatePaymentPart() {
        List<OrderPart> duplicated = List.of(
                new OrderRegistered(
                        "ORDER-9",
                        "CUST-9",
                        new BigDecimal("900.00")),
                new PaymentCaptured("ORDER-9", "PAY-9"),
                new PaymentCaptured("ORDER-9", "PAY-9-DUP"),
                new InventoryReserved("ORDER-9", "RES-9"));

        assertThrows(
                IllegalArgumentException.class,
                () -> assembler.assemble(duplicated));
    }
}
~~~

These tests verify **output processor correctness**; they do not replace real Aggregator integration tests covering correlation, `MessageGroupStore`, timeouts, and release strategies.

### 18.2. Testing Splitter → Aggregator with Sequence Headers

With `OrderLinesAggregationConfiguration` from Section 8 and appropriate channels, an integration test should:

1. Send a message containing `List<OrderLine>`.
2. Confirm `Splitter` creates elements and `Aggregator` combines them into one output.
3. Verify every `lineTotal` matches quantity times unit price.
4. Confirm a second batch with a different correlation key never mixes across batches.
5. Drop one element before the Aggregator to observe an incomplete group stalling unless release/timeout is configured.

In-memory demos can inspect output on a `QueueChannel`. Production systems must also test group state persistence and deadlines, especially under concurrency.

### 18.3. Testing Multiple Independent Sources

With three independent events, test all notable orderings:

~~~text
Order → Payment → Inventory
Payment → Inventory → Order
Inventory → Order → Payment
Order → Order(duplicate) → Payment → Inventory
Order(A) → Payment(B) → Inventory(A) → Payment(A) → ...
~~~

Invariants to satisfy:

- Never emit `OrderReady(A)` before all parts for A arrive.
- Never use B's Payment to complete A.
- Handle duplicates per policy instead of counting them as a different part type.
- On timeout, incomplete groups have an explicit outcome.
- Late arrivals after release follow defined behavior.

## 19. Decision Tree: Enricher or Aggregator?

~~~mermaid
flowchart TD
    START["Missing data needed for processing?"] --> Q1{"Can extra data be queried on demand right now?"}
    Q1 -->|Yes| Q2{"Only enriching a single current message?"}
    Q2 -->|Yes| E["Content Enricher"]
    Q2 -->|No| MORE["Consider pipeline / fan-out / join"]
    Q1 -->|No: data arrives as events| Q3{"Multiple messages to correlate and wait for?"}
    Q3 -->|Yes| A["Aggregator"]
    Q3 -->|No| OTHER["Router / Filter / Transformer / other workflow"]
    E --> FOLLOW["Can continue to Router / Filter"]
    A --> FOLLOW
~~~

Concrete questions before deciding:

1. **Who owns the supplementary data?** Can Customer Directory return a snapshot right now, or does Payment Service only emit an event when done?
2. **Am I adding fields or waiting for multiple messages?** Adding `tier` from a lookup differs from waiting on payment and inventory events.
3. **Must state be held for long?** If yes, think Aggregator/process manager and persistent storage.
4. **What defines completion?** Enricher finishes when lookup/reply completes; Aggregator finishes when the release condition holds.
5. **What if data is missing?** Enricher: timeout/fallback/reject; Aggregator: incomplete group/expiry/compensation.
6. **Does a Gateway expect an immediate reply?** Enricher typically fits short latencies, while Aggregator may require async results or longer SLAs.
7. **Is extra data coming from multiple sources?** Calling multiple lookup APIs does not automatically make it an Aggregator; holding independent events in a group is the strong signal.
8. **What serves as correlation?** For Aggregator, the key must isolate each group and tenant cleanly.
9. **Can duplicates or replays occur?** Both need downstream idempotency; Aggregator also needs part deduplication.
10. **Is crash recovery needed?** May require group persistence and replay support.

## 20. Performance and Operational Observability

### 20.1. What Metrics Does Enricher Need?

| Metric / Log Field | Purpose |
|---|---|
| `enrichment_requests_total` | Lookup count |
| `enrichment_success_total` | Messages successfully enriched |
| `enrichment_failure_total{code}` | Not found, timeout, contract violation |
| `enrichment_duration_seconds` | Lookup and merge latency |
| `customer_cache_hit_ratio` | Cache effectiveness, if cached |
| `traceId` and `businessCorrelationId` | Diagnosing specific requests |

Avoid high-cardinality `customerId` or `orderId` metric labels; keep them in logs/traces under security controls.

### 20.2. What Metrics Does Aggregator Need?

| Metric / Log Field | Purpose |
|---|---|
| `aggregation_open_groups` | Currently waiting groups |
| `aggregation_group_age_seconds` | Groups waiting too long |
| `aggregation_completed_total` | Groups released successfully |
| `aggregation_expired_total` | Timed-out / expired groups |
| `aggregation_duplicates_total` | Duplicate part messages |
| `aggregation_late_arrivals_total` | Messages arriving after group closed |
| `correlationKey` (log/trace, not arbitrary metric label) | Tracing a specific group |

Both patterns affect throughput, yet their bottlenecks differ sharply: **Enricher is governed by lookup latency**, while **Aggregator is governed by open group count, store size, and part wait duration**.

### 20.3. Alerting on Anomalies

- Sudden spike in enrichment failures: Customer Directory may be down or its schema changed.
- Rising lookup latency: upstream thread pools or channels may be congested.
- Steadily growing open groups: parts are missing, correlation is wrong, or release strategy mismatches reality.
- Rising late arrivals: slow producers, overly tight timeouts, or abnormal duplicates/retries.
- Duplicate aggregation outputs: check idempotency and group lifecycle.

Aggregator health cannot be inferred solely from Enricher HTTP lookup metrics.

## 21. Common Design Mistakes

### Mistake 1 — Using an Aggregator Just to Look Up a Customer Profile

**Symptom:** creating a `MessageGroup` by `customerId` just to add `tier` to an already complete order.

**Problem:** adds needless group state, release/timeout complexity, and risks merging multiple orders for the same customer.

**Fix:** use an Enricher to query the profile; add a contract-governed cache if needed.

### Mistake 2 — Polling with an Enricher Forever Waiting for Future Events

**Symptom:** after `OrderPlaced`, code repeatedly calls payment/inventory APIs waiting for ready state.

**Problem:** wastes resources, inflates latency, complicates deadlines, and risks inconsistent snapshots.

**Fix:** if systems emit independent events, consider an Aggregator or process manager with correlation and timeouts.

### Mistake 3 — Choosing `customerId` as the Aggregator Correlation Key

**Symptom:** two orders from the same customer mix up their payment and inventory info.

**Fix:** key by `orderId` (and `tenantId` where needed) matching the business lifecycle.

### Mistake 4 — Releasing as Soon as a Group Has Three Messages

**Symptom:** duplicate `PaymentCaptured` lets a group of three release while `InventoryReserved` is still missing.

**Fix:** check for all required **part types**; add deduplication/versioning and duplicate policies.

### Mistake 5 — Omitting Group Timeout/Expiry

**Symptom:** incomplete groups linger forever, exhausting memory or storage.

**Fix:** configure deadlines, monitor group age, and define explicit incomplete-group behavior.

### Mistake 6 — Enricher Returning a Default on Every Error

**Symptom:** Customer Directory times out yet `tier` is set to `STANDARD` as if valid.

**Fix:** separate "not found," "infrastructure error," and "unauthorized"; fall back only when the contract permits.

### Mistake 7 — Confusing `correlationId` with `traceId`

**Symptom:** parts are grouped by `traceId` even though payment and inventory services emit different trace IDs.

**Fix:** correlation keys must be a stable **business identity** for the group; `traceId` is for distributed tracing.

### Mistake 8 — Assuming the Default `MessageGroupStore` Is Durable

**Symptom:** restarting wipes in-progress groups.

**Fix:** configure a persistent `MessageGroupStore` when required, with transaction and recovery tests.

### Mistake 9 — Mutating the Original Payload Inside Enricher

**Symptom:** Publish–Subscribe branches share a mutable object, and one branch sees unexpected field changes.

**Fix:** use immutable DTOs and create new outputs; inspect behavior carefully if using `ContentEnricher` property mutation.

### Mistake 10 — Assuming Aggregator Output Always Keeps Every Header

**Symptom:** `replyChannel`, `tenantId`, or trace context vanishes or comes from the wrong part.

**Fix:** write a custom output processor or header mapping and integration-test metadata.

### Mistake 11 — Full-Flow Retries Triggering Duplicate Side Effects

**Symptom:** Enricher re-runs lookups or Aggregator re-releases, causing downstream to send emails or write to the DB multiple times.

**Fix:** keep `eventId` stable, deduplicate parts, and enforce idempotency at side-effecting handlers.

### Mistake 12 — Using Default Aggregation Without `sequenceSize`

**Symptom:** messages wait indefinitely because group completeness can never be determined.

**Fix:** for independent producers, configure explicit correlation and release strategies instead of relying on Splitter metadata.

## 22. Practice Exercises

### Exercise 1 — Enricher Adding Profile Data

Create `OrderPlaced`, `CustomerProfile`, `EnrichedOrder`, and `CustomerDirectory`. Write `OrderContentEnricher` calling lookup and producing an immutable DTO; test a `GOLD` customer and a missing customer.

### Exercise 2 — Testing Header Propagation

Use `@Transformer` to implement Content Enricher on `orders.toEnrich`. Send a message with `traceId` and `businessCorrelationId`, asserting output payload accuracy and preserved headers without calling real APIs.

### Exercise 3 — Dedicated Content Enricher

Try configuring `ContentEnricher` or `.enrich(...)` DSL for a mutable JavaBean with property `customerTier` using request–reply lookup. Compare with `@Transformer` returning an immutable `EnrichedOrder` record; verify whether inputs are mutated.

### Exercise 4 — Splitter → Aggregator

Send a batch of three `OrderLine` items, split into three messages, price each line in a Transformer, and combine in an Aggregator. Test that output appears only when all parts arrive and separate batches never mix.

### Exercise 5 — Filter Dropping One Part

Drop one line after Splitter and observe whether the default Aggregator releases or stalls. Propose flow adjustments or release/timeout rules matching business contracts.

### Exercise 6 — Three Event Sources

Design an Aggregator for `OrderRegistered`, `PaymentCaptured`, and `InventoryReserved`. Correlate by `orderId`, release when all three types arrive, and emit `OrderReady`. Test all three arrival orderings.

### Exercise 7 — Duplicates and Late Arrivals

Send two `PaymentCaptured` messages and have `InventoryReserved` arrive past timeout. Define duplicate and late-arrival handling; verify the system never emits `OrderReady` twice for the same business event.

### Exercise 8 — Combining Enricher and Aggregator

Enrich `OrderRegistered` with `tier` before entering the Aggregator alongside Payment and Inventory. After release, use a Router to choose priority vs. standard. Test that two different orders for the same `customerId` still form two groups.

### Exercise 9 — Infrastructure Errors vs. Missing Data

Simulate Customer Directory returning not found, timing out, and returning a profile with the wrong ID. Compare errors; apply bounded retries only to timeouts. Never default to `STANDARD` across all three cases.

### Exercise 10 — State Recovery

Plan a persistent store for an Aggregator and simulate a restart when a group has only two of three parts. Document recovery, deduplication, and reconciliation rules, and explain why a short Enricher lookup does not need the same group persistence mechanism.

### Self-Check Questions

1. Why is `OrderPlaced + CustomerProfile lookup` usually a Content Enricher, not an Aggregator?
2. How do the two patterns differ in input message count and state-retention needs?
3. When `PaymentCaptured` arrives late, should an Enricher hold `OrderPlaced` waiting for that event?
4. What principle guides choosing an Aggregator correlation key?
5. Why can `group.size() == 3` release prematurely?
6. Why does sharing `customerId` not mean two orders belong in the same group?
7. When can `@Transformer` be used to implement the enrichment intent?
8. How does a dedicated `ContentEnricher` differ from a Header Enricher?
9. Why must you be careful with property enrichment on immutable `record` types?
10. What does `MessageGroupStore` do, and is it durable across restarts by default?
11. If a Filter drops one part after Splitter, what risk does the Aggregator face?
12. In a request–reply flow, how do Enricher timeouts and Aggregator timeouts differ?
13. When an Aggregator output has one `traceId`, can you conclude every part carried that same `traceId`?
14. Do Enricher and Aggregator need idempotency, and where should it live?
15. Which metrics distinguish slow lookups from groups waiting too long?

## 23. Architecture Checklist

- [ ] Determined whether **one message needs extra data** or **multiple messages must converge**.
- [ ] Confirmed whether supplementary data supports request–reply lookup or arrives only as events when ready.
- [ ] For Enricher: configured timeouts, fallback/rejection, and lookup error classification.
- [ ] For Enricher: enriched data is cleanly typed without unintended input mutation.
- [ ] Tenant and authorization checks enforced when reading reference data.
- [ ] For Aggregator: correlation key is stable and never mixes tenants or orders.
- [ ] For Aggregator: release strategy checks **required content completeness**, not blind counts.
- [ ] Defined duplicate, late-arrival, timeout, and incomplete-group policies.
- [ ] Group state uses storage and recovery matching durability requirements.
- [ ] Output processor has a clear schema and handles headers/correlation properly.
- [ ] Filters after Splitter cannot stall the Aggregator indefinitely by accident.
- [ ] Retries target only recoverable errors without masking permanent bad data.
- [ ] Handlers with side effects enforce stable idempotency keys.
- [ ] Unit tests cover enrich/assemble logic and integration tests cover channel/group lifecycle.
- [ ] Separate metrics track enrichment lookups versus aggregation groups.
- [ ] Routing Slip, `traceId`, and message IDs never substitute for business correlation keys.
- [ ] Documentation clearly explains where Content Enricher, Aggregator, and combinations apply.

## 24. Summary

**Content Enricher** and **Aggregator** both produce outputs with more information than any single input, yet they solve **two different problems**. Enricher adds data to the **current message**, usually via a request–reply lookup, and continues processing. Aggregator **receives multiple distinct messages**, groups them by a correlation key, awaits a release condition, and emits a combined result—while also managing state, timeouts, duplicates, and late arrivals.

In Spring Integration, Content Enricher can be implemented using the dedicated `ContentEnricher` component or a `@Transformer` producing an immutable enriched DTO. Aggregator relies on `MessageGroup`, correlation/release strategies, and an output processor, often paired with a Splitter or multiple event sources. Picking the right pattern reduces endpoint coupling, avoids wasteful polling loops or unnecessary group state, and pinpoints exactly where retries, error channels, correlation, and tests belong.

For the **SPRING_INTEGRATION_PATTERN** module, the effective rule is: **enrich reference data when on-demand lookup is viable; aggregate when multiple messages must converge; and combine both when a workflow needs both supplementary attributes and synchronization across independent events**.

### References

- Spring Integration Reference — Content Enricher: https://docs.spring.io/spring-integration/reference/content-enrichment.html
- Spring Integration Reference — Aggregator: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Integration Reference — Splitter: https://docs.spring.io/spring-integration/reference/splitter.html
- Spring Integration Reference — Java DSL: https://docs.spring.io/spring-integration/reference/dsl.html
- Spring Integration Reference — Message Store: https://docs.spring.io/spring-integration/reference/message-store.html
- Spring Integration API — ContentEnricher: https://docs.spring.io/spring-integration/api/org/springframework/integration/transformer/ContentEnricher.html
- Spring Integration API — MessageGroup: https://docs.spring.io/spring-integration/api/org/springframework/integration/store/MessageGroup.html
- Spring Integration API — ReleaseStrategy: https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/ReleaseStrategy.html
- Spring Integration API — CorrelationStrategy: https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/CorrelationStrategy.html
- JUnit 5 User Guide — Parameterized Tests: https://junit.org/junit5/docs/current/user-guide/#writing-tests-parameterized-tests
