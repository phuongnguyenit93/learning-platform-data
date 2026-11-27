# Aggregator: Combining Multiple Messages into One Result

In **Spring Integration**, **Aggregator** is an endpoint that implements the Enterprise Integration Pattern **Aggregator**: it receives **multiple related messages**, stores them in a *message group*, waits until the group satisfies a completion condition, and then emits **one aggregated result message**. This is the solution for scenarios such as an order with multiple line items, multiple parallel processing results that must converge, or payment – inventory – order events arriving at different times.

This lesson belongs to the **Aggregator** chapter of the **SPRING_INTEGRATION_PATTERN** module. The module teaches how to implement EIP with Spring Integration to build loosely coupled, extensible message flows; practicing Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation, while testing and monitoring processing branches.

The most important part is not just calling the `aggregate()` method, but determining **which messages belong to the same group**, **when the group is considered complete**, **what shape the output must have**, and **how to handle missing, duplicate, late-arriving, or expired groups**.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Explain Aggregator using the **N messages → one result** model and distinguish it from Splitter, Transformer, Content Enricher, Router, and Publish–Subscribe.
2. Describe the lifecycle of a `MessageGroup`: creating the group, receiving elements, evaluating release, emitting output, and completing/expiring the group.
3. Design a **correlation strategy** so that messages belonging to the same business entity go into the right group without mixing groups across tenants/orders.
4. Design a **release strategy** to avoid emitting results when information is missing or duplicate messages arrive.
5. Understand the role of the **aggregation output processor**: building the result payload from the collected messages.
6. Understand `correlationId`, `sequenceNumber`, and `sequenceSize` provided by Splitter and the limitations of using them for independent events.
7. Configure a `Splitter → Transformer → Aggregator` flow using Spring Integration Java DSL and test it via channels.
8. Build a model that converges multiple events: `OrderRegistered`, `PaymentCaptured`, and `InventoryReserved`.
9. Handle timeouts, incomplete groups, duplicates, late arrivals, concurrency, persistence, retry, and idempotency.
10. Write unit tests for grouping/assembly rules and integration tests for the actual flow.

## 2. What Problem Does Aggregator Solve?

Suppose an order has three line items:

~~~text
OrderLines(orderId=ORDER-1001)
  - SKU-A, quantity=2, unitPrice=100.00
  - SKU-B, quantity=1, unitPrice=50.00
  - SKU-C, quantity=3, unitPrice=25.00
~~~

The system uses a Splitter to split the batch into three messages and calculate the total for each line. At some point, downstream needs to receive **one result for the entire order**, for example:

~~~text
OrderPriceResult(
  orderId=ORDER-1001,
  lines=[
    SKU-A: 200.00,
    SKU-B:  50.00,
    SKU-C:  75.00
  ],
  total=325.00
)
~~~

To produce that result, you cannot just use a `MessageFilter` or a `Router`. You need to collect the processed lines into a group, wait until all are present, and then aggregate them:

~~~mermaid
flowchart LR
    B["Order batch"] --> S["Splitter"]
    S --> A["Line A"]
    S --> C["Line B"]
    S --> D["Line C"]
    A --> T["Transformer: priced line"]
    C --> T
    D --> T
    T --> G["Aggregator"]
    G -->|"group complete"| O["One result"]
~~~

With independent sources, the idea is the same, except the wait time is not known in advance:

~~~mermaid
flowchart LR
    O["OrderRegistered"] --> G["Aggregator"]
    P["PaymentCaptured"] --> G
    I["InventoryReserved"] --> G
    G --> M["MessageGroup by orderId"]
    M --> R{"All three types?"}
    R -->|"No"| W["Hold state, wait"]
    R -->|"Yes"| OUT["OrderReady"]
~~~

**Aggregator is not simply joining a List.** It also owns the responsibility of **grouping, accumulating, completing, and managing lifecycle** in an environment where messages may arrive asynchronously.

### 2.1. Defined by Three Questions

An Aggregator must be able to answer:

- **Which group?** `correlationStrategy(message) → groupKey`.
- **When is it complete?** `releaseStrategy(messageGroup) → boolean`.
- **What is the result?** `outputProcessor(messageGroup) → output`.

Without defining these three things, an aggregator can wait forever, release early, mix different orders, or return data that downstream does not understand.

## 3. Comparing Aggregator with Related EIPs

| Pattern | Responsibility | Typical Shape |
|---|---|---|
| **Splitter** | Splits one message into multiple parts | 1 → N |
| **Aggregator** | Collects related messages and emits a result | N → 1 |
| **Content Enricher** | Adds lookup data to an existing message | 1 → 1, with lookup |
| **Transformer** | Transforms payload or message | 1 → 1 or creates a collection depending on contract |
| **Filter** | Lets a message pass or drops it | 1 → 1 or 1 → 0 |
| **Router** | Selects destination channel(s) | 1 → one/several destinations per configuration |
| **Publish–Subscribe** | Sends a message to subscribers | One broadcast → multiple consumers |
| **Gateway** | Bridges request–reply with the application | Request → Reply |
| **Resequencer** | Reorders related messages | N messages → N messages in proper order |

For example, a Transformer that receives a `List<OrderLine>` and computes the sum directly in memory **is not an Aggregator in the messaging sense** if there are no separate messages to collect. A Content Enricher that calls an API to fetch the customer tier for an order **does not need a MessageGroup**. Conversely, three events emitted by three separate producers **need a waiting and correlation mechanism** if the output is only valid once all three have arrived.

**Note:** the N→1 notation describes a **successfully completed** group. Cases involving timeout, rejection, discard, or partial release may produce different output, or no output depending on the contract.

## 4. Three Core Components of Aggregator

### 4.1. Correlation Strategy — Choosing the Right Group

Each message must be assigned a **group key**. For individual line items, the key is usually the batch correlation ID. For order events, the key may be `orderId`.

~~~text
Message A: orderId=ORDER-1001 -> group ORDER-1001
Message B: orderId=ORDER-1002 -> group ORDER-1002
Message C: orderId=ORDER-1001 -> group ORDER-1001
~~~

C must not be placed into group ORDER-1002. In a multi-tenant system, if order IDs are only unique **within each tenant**, the key needs to include the trusted tenant:

~~~java
public record GroupKey(String tenantId, String orderId) {}
~~~

Do not use each message's own `MessageHeaders.ID` as the group key for events that need to be grouped together, because every message has a different ID.

### 4.2. Release Strategy — Is the Group Complete?

When a group receives another message, the Aggregator must decide whether the conditions are met to produce a result. For data after a Splitter, sequence metadata can be used: `sequenceSize` indicates the expected number of elements.

For independent events, a condition like `group.size() == 3` is usually **not safe enough**. Three messages could consist of two duplicate `PaymentCaptured` events and one `OrderRegistered`, while `InventoryReserved` is still missing. The release strategy must check for the **exact components** that the output requires.

### 4.3. Output Processor — Creating the New Result

Once the group is complete, the Aggregator uses the messages in the group to build the output:

~~~text
MessageGroup
  + PricedLine(SKU-A, 200.00)
  + PricedLine(SKU-B,  50.00)
  + PricedLine(SKU-C,  75.00)

Output processor
  -> OrderPriceResult(orderId, lines, total=325.00)
~~~

The result can be a collection of payloads, an aggregated DTO, or a `Message<?>` with appropriate headers. The output processor must define the **schema, data ordering if needed, header handling, and duplicate rules**.

## 5. Lifecycle of a MessageGroup

Spring Integration stores related messages in a `MessageGroup`. Groups are managed through a `MessageGroupStore`; the actual storage mechanism depends on configuration.

~~~mermaid
flowchart TD
    IN["Message arrives at Aggregator"] --> K["Compute correlation key"]
    K --> G{"Group exists?"}
    G -->|No| NEW["Create group"]
    G -->|Yes| ADD["Add to group"]
    NEW --> ADD
    ADD --> R{"Release condition met?"}
    R -->|No| WAIT["Hold group, wait for other messages"]
    R -->|Yes| BUILD["Output processor"]
    BUILD --> SEND["Emit aggregated message"]
    SEND --> COMPLETE["Complete/cleanup group per config"]
    WAIT --> TIME{"Timeout / expiry?"}
    TIME -->|No| IN
    TIME -->|Yes| EXPIRE["Expire / partial / discard / alert"]
~~~

A group can be created when the first message arrives, continue receiving multiple parts, and only emit output after some time. Therefore, Aggregator is **a stateful endpoint** in the sense that it manages open groups.

### 5.1. Where Does State Live?

- In simple examples/tests, an in-memory message store can be used.
- If it must survive restarts, you must design a **persistent MessageGroupStore** compatible with the environment.
- If multiple instances process the same group, you need to consider a shared store, locking, transactions, and concurrent delivery.
- If a group never completes, there must be a **timeout/expiry policy**; otherwise, the store can grow unbounded.
- If a group has already completed and a late message arrives, you need a handling rule instead of arbitrarily reopening it.

**Do not assume Aggregator creates a durable queue on its own.** Message stores, retries, acknowledgements, and brokers each have different roles.

### 5.2. One Group Does Not Mean One System-Wide Transaction

An Aggregator may store enough messages, emit output, and then downstream writes to a database. If an error occurs between steps, messages or results may be reprocessed depending on transaction/ack configuration. Idempotency/outbox is still needed when the business logic must prevent duplicate emissions.

## 6. How Headers Generated by Splitter Help Aggregator

A Splitter typically sends child messages with headers:

| Header | Role |
|---|---|
| `correlationId` | Identifies the group of parts from one split |
| `sequenceNumber` | Position of the child message in the sequence |
| `sequenceSize` | Expected total number of parts |
| `traceId` | Tracing, if propagated from the source |
| `businessCorrelationId` | Links the result to the order |

For example, a Splitter emits three parts:

~~~text
Message 1: correlationId=abc, sequenceNumber=1, sequenceSize=3
Message 2: correlationId=abc, sequenceNumber=2, sequenceSize=3
Message 3: correlationId=abc, sequenceNumber=3, sequenceSize=3
~~~

With a standard topology and proper sequence headers, the **default Aggregator** can use correlation/release strategies based on this metadata to reassemble the parts.

### 6.1. Why Is `sequenceSize` Not Always Present?

When three services emit `OrderRegistered`, `PaymentCaptured`, and `InventoryReserved` independently, there is no shared upstream Splitter. Producers might not send `sequenceSize`; even if they do, the data may not correspond to the expected number of parts. Therefore, **custom correlation/release strategies** aligned with the business logic are needed.

### 6.2. Data Dropped by Filter After Splitter

A classic bug:

~~~mermaid
flowchart LR
    B["Batch 3 parts"] --> S["Splitter"]
    S --> A["Part 1"]
    S --> C["Part 2"]
    S --> D["Part 3"]
    A --> AG["Aggregator"]
    C --> F{"Filter"}
    F -->|Rejected| DROP["Discard"]
    D --> AG
~~~

Each part may carry `sequenceSize=3`, yet the Aggregator only receives **2/3 messages**. It can wait indefinitely if the release strategy requires all three parts. Design options:

- **Filter before Splitter**, so the number of parts is computed after filtering out data.
- Instead of discarding, emit a representative `SkippedPart` result so the group still completes.
- Use a release strategy that handles the actual set of parts with its own completion condition.
- Use timeout/expiry and a policy to emit partial groups when missing parts are acceptable.

Do not arbitrarily mutate `sequenceSize` on already-split messages to "patch" a waiting Aggregator.

## 7. Java 17+ Example: From OrderLine to PricedLine

Let's build a simple, testable flow: a batch containing order lines, a Splitter creates child messages, a Transformer prices each line, and an Aggregator collects them back together.

### 7.1. Input Model

~~~java
import java.math.BigDecimal;
import java.util.List;

public record OrderLine(
        String sku,
        BigDecimal unitPrice,
        int quantity
) {}

public record PricedLine(
        String sku,
        BigDecimal lineTotal
) {}

public record OrderBatch(
        String orderId,
        List<OrderLine> lines
) {
    public OrderBatch {
        lines = List.copyOf(lines);
    }
}
~~~

The top-level `public` declarations in the example should be placed in their corresponding Java source files in real implementations. `List.copyOf` creates a snapshot of the collection, though if individual elements contain mutable objects, deeper defensive copying is still needed.

### 7.2. Single-Line Pricing Policy

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public final class LinePricingPolicy {

    public PricedLine price(OrderLine line) {
        Objects.requireNonNull(line, "line");

        if (line.sku() == null || line.sku().isBlank()) {
            throw new IllegalArgumentException("SKU_REQUIRED");
        }
        if (line.unitPrice() == null
                || line.unitPrice().signum() < 0) {
            throw new IllegalArgumentException("PRICE_INVALID");
        }
        if (line.quantity() <= 0) {
            throw new IllegalArgumentException("QUANTITY_INVALID");
        }

        BigDecimal total = line.unitPrice()
                .multiply(BigDecimal.valueOf(line.quantity()));

        return new PricedLine(line.sku(), total);
    }
}
~~~

Using `BigDecimal` calculates monetary values in decimal, avoiding binary representation errors from `double`. The positive quantity and non-negative price rules are illustrative contracts; a refund or credit note flow may have different rules.

### 7.3. Computing the Total After Aggregator Collects the Parts

~~~java
import java.math.BigDecimal;
import java.util.List;

public record OrderPriceResult(
        String orderId,
        List<PricedLine> lines,
        BigDecimal total
) {}

public final class OrderPricingAssembler {

    public OrderPriceResult assemble(
            String orderId, List<PricedLine> lines) {

        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("ORDER_ID_REQUIRED");
        }
        if (lines == null || lines.isEmpty()) {
            throw new IllegalArgumentException("LINES_REQUIRED");
        }

        List<PricedLine> snapshot = List.copyOf(lines);
        BigDecimal sum = snapshot.stream()
                .map(PricedLine::lineTotal)
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        return new OrderPriceResult(orderId, snapshot, sum);
    }
}
~~~

The assembler here is a **pure function** over a complete collection. By itself, it **is not an Aggregator endpoint** because it does not receive individual messages, create groups, or decide release. It can be used inside an aggregation output processor or a Transformer immediately after `.aggregate()`.

## 8. Spring Integration Java DSL: Splitter → Aggregator

This example uses a message whose payload is `List<OrderLine>`. The input is a **List** so that default `split()` splits the elements; if you want to pass `OrderBatch`, add a step converting `OrderBatch.lines()` to a List before `split()`.

### 8.1. Flow Configuration

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
public class OrderLinesFlowConfiguration {

    @Bean(name = "order.lines.input")
    public MessageChannel input() {
        return new DirectChannel();
    }

    @Bean(name = "order.lines.output")
    public PollableChannel output() {
        return new QueueChannel();
    }

    @Bean
    public LinePricingPolicy linePricingPolicy() {
        return new LinePricingPolicy();
    }

    @Bean
    public IntegrationFlow linePricingFlow(
            LinePricingPolicy policy) {

        return IntegrationFlow
                .from("order.lines.input")
                .split()
                .transform(OrderLine.class, policy::price)
                .aggregate()
                .channel("order.lines.output")
                .get();
    }
}
~~~

How to read the flow:

1. The producer sends **one** `Message<List<OrderLine>>` to `order.lines.input`.
2. Splitter creates each `Message<OrderLine>` and attaches appropriate sequence/correlation metadata.
3. Transformer produces a `PricedLine` for each part.
4. Aggregator collects the `PricedLine`s belonging to the same group.
5. Once enough parts arrive according to the default release strategy, the result message is sent to `order.lines.output`.

The default result is usually a **collection of payloads** from the group. If downstream requires a specific `OrderPriceResult`, add an output transformation that extracts the order ID from valid metadata or use a suitable custom output processor.

**Scope note:** this is an in-memory synchronous example. `QueueChannel` helps observe results in unit/integration tests, not guarantee durable persistence across restarts.

### 8.2. Why Didn't This Example Need a Custom `correlationStrategy`?

Because `split()` provides the sequence/correlation headers and the default Aggregator knows how to use them. For inputs from producers **without a shared Splitter**, you cannot assume the same mechanism will recognize a complete group. In that case, a custom design is required.

### 8.3. Is the Output Element Order Guaranteed to Match Input?

A simple synchronous flow may return the collection in a familiar order, but **you should not rely on arrival order for correctness** when executors, brokers, retries, or fan-out are involved. If the result needs exact line-item ordering, use `sequenceNumber` or an explicit `lineIndex`, then sort in the output processor.

### 8.4. Empty Batch Case

If the input is an empty list, Splitter has no parts to emit. Aggregator receives no messages and therefore does not automatically generate an empty output. The contract must define handling upfront: accept a total of 0, reject, or produce a result directly. Do not leave a Gateway waiting forever for an output that the flow never creates.

## 9. Integration Test: Aggregator Actually Emits One Result

Unit testing `LinePricingPolicy` cannot verify that Spring wiring is correct. We use Spring Test and the `QueueChannel` in the configuration from Section 8.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.Collection;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = OrderLinesFlowConfiguration.class)
class OrderLinesFlowTest {

    @Autowired
    @Qualifier("order.lines.input")
    MessageChannel input;

    @Autowired
    @Qualifier("order.lines.output")
    PollableChannel output;

    @Test
    void splitsPricesAndAggregatesAllParts() {
        List<OrderLine> lines = List.of(
                new OrderLine("SKU-A",
                        new BigDecimal("100.00"), 2),
                new OrderLine("SKU-B",
                        new BigDecimal("50.00"), 1),
                new OrderLine("SKU-C",
                        new BigDecimal("25.00"), 3));

        assertTrue(input.send(
                MessageBuilder.withPayload(lines)
                        .setHeader("traceId", "trace-1001")
                        .build()));

        Message<?> aggregated = output.receive(1000);
        assertNotNull(aggregated);

        assertInstanceOf(
                Collection.class, aggregated.getPayload());

        Collection<?> payload =
                (Collection<?>) aggregated.getPayload();
        assertEquals(3, payload.size());

        Set<PricedLine> actual = payload.stream()
                .map(PricedLine.class::cast)
                .collect(Collectors.toSet());

        assertEquals(Set.of(
                new PricedLine(
                        "SKU-A", new BigDecimal("200.00")),
                new PricedLine(
                        "SKU-B", new BigDecimal("50.00")),
                new PricedLine(
                        "SKU-C", new BigDecimal("75.00"))),
                actual);

        // Only one output for a completed group.
        assertNull(output.receive(0));
    }
}
~~~

The test verifies:

- Three parts were processed.
- The output is **one** message carrying a collection of three `PricedLine`s.
- There are not two or three separate output messages for a completed group.
- Each line's value is correct, without relying on collection ordering.

The test above **does not verify durability**, nor does it test multi-instance processing or asynchronous errors. Those requirements need additional tests based on the deployment topology.

### 9.1. Testing Multiple Batches Without Mixing Groups

You can send two batch messages sequentially, e.g., one batch with 2 lines and another with 3 lines. Expect two separate outputs, each containing its corresponding parts. With concurrent processing, test interleaved sending and confirm correlation does not mix the two batches.

### 9.2. Testing Invalid Input

If an `OrderLine` has `quantity=0`, `LinePricingPolicy` throws an exception. In a synchronous `DirectChannel` flow, the error may be thrown back to the sender; you should not wait for a successful aggregated result. With executors or brokers, test the appropriate error flow/ack/timeout.

## 10. Correlation Strategy for Multiple Event Sources

The Splitter case is a simple example. In practice, services may emit independent events:

~~~text
OrderRegistered(orderId=ORDER-1001)
PaymentCaptured(orderId=ORDER-1001)
InventoryReserved(orderId=ORDER-1001)
~~~

Events may arrive in any order:

~~~text
Payment -> Inventory -> Order
Inventory -> Order -> Payment
Order -> Payment -> Inventory
~~~

The Aggregator must work correctly for **every allowed order**.

### 10.1. Message Contracts

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

The top-level `public` declarations in the code block are placed together for comparison. When moving into a Java project, put each declaration into its own **separate source file** with the matching name.

### 10.2. The Right Key: by `orderId`, Not by `customerId`

If two orders belong to the same `CUST-21`:

~~~text
ORDER-1001 -> customerId CUST-21
ORDER-1002 -> customerId CUST-21
~~~

Grouping by `customerId` could mix ORDER-1001's payment with ORDER-1002's inventory. Therefore, the key is typically `orderId`, or a composite key consisting of a verified `tenantId` and `orderId`.

~~~java
public record OrderCorrelationKey(
        String tenantId, String orderId
) {}
~~~

At the trust boundary, do not accept a client-supplied `tenantId` as proof of access rights. The authentication/authorization layer must verify it before constructing the key.

### 10.3. A Pure Correlation Strategy

~~~java
import org.springframework.messaging.Message;

public final class OrderCorrelationPolicy {

    public String groupKey(Message<?> message) {
        if (!(message.getPayload() instanceof OrderPart part)) {
            throw new IllegalArgumentException(
                    "UNSUPPORTED_ORDER_PART");
        }
        if (part.orderId() == null
                || part.orderId().isBlank()) {
            throw new IllegalArgumentException(
                    "ORDER_ID_REQUIRED");
        }
        return part.orderId();
    }
}
~~~

This code suits a single-tenant model with system-wide unique IDs. In multi-tenant production, return a composite key with a verified tenant. Do not rely on message class names or `MessageHeaders.ID` to correlate messages of the same order.

## 11. Release Strategy Must Check for All Required Message *Types*

Suppose the Aggregator has received:

~~~text
OrderRegistered(ORDER-1001)
PaymentCaptured(ORDER-1001)
PaymentCaptured(ORDER-1001)  // duplicate
~~~

`group.size()==3` does not mean `InventoryReserved` is present. If it releases early, the system can emit an invalid `OrderReady`.

### 11.1. Policy Checking Completeness of Facts

~~~java
import java.util.List;

public final class OrderGroupPolicy {

    public boolean complete(List<OrderPart> parts) {
        return count(parts, OrderRegistered.class) == 1
                && count(parts, PaymentCaptured.class) == 1
                && count(parts, InventoryReserved.class) == 1
                && parts.size() == 3;
    }

    private long count(
            List<OrderPart> parts, Class<? extends OrderPart> type) {
        return parts.stream().filter(type::isInstance).count();
    }
}
~~~

This policy **does not automatically deduplicate**: if there are two `PaymentCaptured` events, the group does not satisfy release. That is a deliberate choice to illustrate duplicate errors, but in production, if duplicates can occur, **the group may never complete** without a deduplication step or an explicit handling/expiry strategy.

Options:

- Deduplicate by `eventId` before the Aggregator.
- Store the latest version by business key, with clear conflict rules.
- Reject duplicates via an error/reject flow.
- Design the group policy to accept a single verified copy while recording duplicates.

### 11.2. Combining Output via an Assembler

~~~java
import java.util.List;

public final class OrderReadyAssembler {

    public OrderReady assemble(List<OrderPart> parts) {
        OrderGroupPolicy policy = new OrderGroupPolicy();
        if (!policy.complete(parts)) {
            throw new IllegalArgumentException(
                    "ORDER_GROUP_INCOMPLETE");
        }

        OrderRegistered order = exactlyOne(
                parts, OrderRegistered.class);
        PaymentCaptured payment = exactlyOne(
                parts, PaymentCaptured.class);
        InventoryReserved inventory = exactlyOne(
                parts, InventoryReserved.class);

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
        List<T> values = parts.stream()
                .filter(type::isInstance)
                .map(type::cast)
                .toList();

        if (values.size() != 1) {
            throw new IllegalArgumentException(
                    "MISSING_OR_DUPLICATED_" + type.getSimpleName());
        }
        return values.get(0);
    }
}
~~~

This is a **result assembly function**. A Spring Integration Aggregator still needs configuration for the correlation strategy, release strategy, `MessageGroupStore`, and output processor to invoke this function at the right time.

### 11.3. Wiring into the Aggregator Endpoint

Architecturally:

~~~text
order.parts.input
  -> Aggregator
       correlationStrategy(message) = orderId
       releaseStrategy(group) =
           OrderGroupPolicy.complete(payloads(group))
       outputProcessor(group) =
           OrderReadyAssembler.assemble(payloads(group))
       messageStore = configured per required durability
       groupTimeout = business wait duration
  -> orders.ready
~~~

This is a **configuration diagram**, not directly compilable Java DSL. Specific configuration APIs can use `AggregatorSpec` with corresponding callback/strategy beans depending on the Spring Integration version. The `.aggregate()` example in Section 8 is a runnable flow for the default Splitter model; this section focuses on **business rules** for event joins to avoid conflating the two cases.

### 11.4. When to Use a Custom Release Strategy?

- Multiple events without `sequenceSize`.
- The required number of parts varies by business type.
- Release conditions depend on event state/type rather than just count.
- There are negative, cancel, or rejection results replacing a part.
- Partial results may be emitted after a deadline.
- Results need to be emitted by a specific version with duplicate prevention.

## 12. Unit Testing Correlation, Release, and Assembly

Pure policies can be tested **without a Spring context**. This is how to catch misgrouping and incomplete-release bugs before testing wiring.

### 12.1. Complete Group Regardless of Order

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;

class OrderReadyAssemblerTest {

    @Test
    void buildsResultRegardlessOfArrivalOrder() {
        List<OrderPart> parts = List.of(
                new InventoryReserved("ORDER-9", "RES-9"),
                new OrderRegistered(
                        "ORDER-9", "CUST-9",
                        new BigDecimal("900.00")),
                new PaymentCaptured("ORDER-9", "PAY-9"));

        OrderGroupPolicy policy = new OrderGroupPolicy();
        assertTrue(policy.complete(parts));

        OrderReady result =
                new OrderReadyAssembler().assemble(parts);

        assertEquals("ORDER-9", result.orderId());
        assertEquals("CUST-9", result.customerId());
        assertEquals(new BigDecimal("900.00"), result.amount());
        assertEquals("PAY-9", result.paymentId());
        assertEquals("RES-9", result.reservationId());
    }
}
~~~

### 12.2. Missing Part Must Wait

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;

class IncompleteOrderGroupTest {

    @Test
    void doesNotReleaseWithoutInventory() {
        List<OrderPart> incomplete = List.of(
                new OrderRegistered(
                        "ORDER-9", "CUST-9",
                        new BigDecimal("900.00")),
                new PaymentCaptured("ORDER-9", "PAY-9"));

        OrderGroupPolicy policy = new OrderGroupPolicy();

        assertFalse(policy.complete(incomplete));

        assertThrows(
                IllegalArgumentException.class,
                () -> new OrderReadyAssembler().assemble(incomplete));
    }
}
~~~

### 12.3. Duplicate Payment Must Not Count as Inventory

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;

class DuplicateOrderPartTest {

    @Test
    void duplicatePaymentDoesNotCompleteTheGroup() {
        List<OrderPart> duplicated = List.of(
                new OrderRegistered(
                        "ORDER-9", "CUST-9",
                        new BigDecimal("900.00")),
                new PaymentCaptured("ORDER-9", "PAY-9"),
                new PaymentCaptured("ORDER-9", "PAY-9-DUP"));

        assertFalse(new OrderGroupPolicy().complete(duplicated));
    }

    @Test
    void assemblerRejectsDuplicateEvenWithInventory() {
        List<OrderPart> duplicated = List.of(
                new OrderRegistered(
                        "ORDER-9", "CUST-9",
                        new BigDecimal("900.00")),
                new PaymentCaptured("ORDER-9", "PAY-9"),
                new PaymentCaptured("ORDER-9", "PAY-9-DUP"),
                new InventoryReserved("ORDER-9", "RES-9"));

        assertThrows(
                IllegalArgumentException.class,
                () -> new OrderReadyAssembler().assemble(duplicated));
    }
}
~~~

These are tests of business policies and **do not replace** real Aggregator integration tests covering group storage, release, timeout, and concurrency. However, they ensure message count is not confused with data-type completeness.

### 12.4. Recommended Additional Tests

| Test Case | What to Verify |
|---|---|
| Parts arriving in any order | Same output |
| Two orders for the same customer | Groups are not mixed |
| Two tenants using the same orderId | Groups are not mixed when key includes tenant |
| Missing Payment | Does not release into OrderReady |
| Duplicate OrderRegistered | Does not produce invalid output |
| Duplicate eventId | Deduplicated or rejected per contract |
| Late Inventory after expiry | Clearly defined behavior |
| Part with invalid schema | Not silently added to group |
| Reversed payment | Not treated as captured successfully if business rules disallow it |
| Output processor failure | Consistent error flow and group cleanup |

## 13. Choosing Output Processor: Collection or DTO?

### 13.1. Default Output

In the basic Splitter → Aggregator example, the output can be a **collection of payloads**. This is useful when downstream still needs to compute over the collection.

### 13.2. Explicit Result DTO

When downstream needs `OrderPriceResult` or `OrderReady`, there should be a dedicated output processor creating a clear data type. It can be structured like:

~~~text
MessageGroup
    -> retrieve messages belonging to the group
    -> check type, version, eventId, orderId
    -> select/compute fields per business rules
    -> create immutable OrderReady
    -> create output message with metadata per contract
~~~

Some messages in the group may contain conflicting headers, such as different `replyChannel`, `traceId`, or `tenantId`. You cannot assume **every header of every part** is copied verbatim to the output. Test and define explicit header mapping.

### 13.3. Output Ordering

Message arrival order can differ from business order due to concurrency/retries. If the DTO contains a `List<PricedLine>` with meaningful order, store a `lineIndex` or reliable `sequenceNumber` and sort before building output. Do not rely on the iterator order of any particular `MessageGroupStore`.

## 14. Timeout, Expiry, and Incomplete Groups

An Aggregator may **never receive enough messages** if a producer fails, a Filter drops a part, a broker loses an event, or correlation is wrong. There must be a policy for incomplete groups.

~~~mermaid
flowchart TD
    A["Waiting MessageGroup"] --> T{"Deadline/timeout?"}
    T -->|No| WAIT["Continue receiving parts"]
    T -->|Reached| P{"Allow partial result?"}
    P -->|Yes| PARTIAL["Emit partial result with status"]
    P -->|No| ERR["Record error/expired group"]
    PARTIAL --> CLEAN["Cleanup per contract"]
    ERR --> CLEAN
~~~

### 14.1. Aggregator Timeout Differs from HTTP Timeout

An Enricher waiting on an HTTP lookup usually has a **single-request** timeout. An Aggregator waiting for **multiple messages** may have a longer deadline, or handle group expiry via a scheduler. Do not blindly apply a 500ms HTTP client timeout to an inventory reservation process that spans several minutes.

### 14.2. When to Emit Partial Results?

Emit partial results only when downstream accepts them. For example, an analytics report may accept 2/3 facts and mark `partial=true`. By contrast, a shipping dispatch system may **not be allowed** to create `OrderReady` without `InventoryReserved`.

Use a dedicated result type if business logic needs to distinguish outcomes:

~~~java
public enum AggregationOutcome {
    COMPLETE,
    PARTIAL,
    EXPIRED
}

public record AggregationResult<T>(
        AggregationOutcome outcome,
        T value,
        String reasonCode
) {}
~~~

These declarations require separate source files when creating a Java project. `AggregationResult` here is an **illustrative** type, not a built-in Spring Integration class.

### 14.3. Expired Groups Must Be Observable

When a group expires, you need to know: group key, number of parts received, missing part types, group age, deadline, and business status. Do not just delete the group and lose all diagnostic information. For personal data, restrict logging raw payloads.

### 14.4. Late Arrival After Group Closure

When Payment arrives after the group has already released, you can:

- Reject and route to dead-letter/quarantine.
- Ignore if it is an already-processed duplicate.
- Reopen the group under a special contract.
- Emit a **compensating event** or correction.
- Hand off to a process manager handling a long-running saga.

Each option brings idempotency and audit requirements. Do not assume Aggregator always reopens a group the way you want; behavior depends on group completion/expiry configuration.

## 15. Duplicates, Redelivery, and Idempotency

Messaging systems often redeliver: producer retries, consumer crashes after commit but before ack, broker redelivery, or a downstream step throwing an exception. Thus, the same **business event** can reach the Aggregator multiple times.

### 15.1. Distinguish Two Types of IDs

- `MessageHeaders.ID`: ID of a single Spring message instance, which can change when creating another message.
- `eventId`: stable business ID of the event, which should be preserved across replay/redelivery.
- `correlationId` or business group key: identifies the **group** containing the event.

Do not use any one of these three IDs as a complete substitute for the other purposes.

### 15.2. Where to Deduplicate?

You can deduplicate by `eventId` before storing in the group, or inside a store/grouper with an appropriate anti-duplicate policy. After the Aggregator, the output also needs idempotency if two releases/replays could send the same result to a DB/email/broker.

~~~text
Producer -> Broker
         -> Validation
         -> Dedup by eventId
         -> Aggregator by (tenantId, orderId)
         -> Output processor
         -> Idempotent handler/outbox
~~~

A repeated `PaymentCaptured` **must not** be counted as an `InventoryReserved` part. If a duplicate arrives with a different payload under the same `eventId`, that is a data integrity violation that must be handled explicitly.

### 15.3. Exactly-Once Does Not Come from Aggregator

Aggregator can emit one output for a completed group in a single run, but this **does not guarantee exactly-once side effects** across brokers, databases, and external systems. You need transactions, acknowledgements, outbox, dedup/idempotency, and testing across failure windows.

## 16. Concurrency and Multiple Instances

When two messages for the same group arrive nearly simultaneously, the Aggregator must handle writing to the group and evaluating release. In Spring Integration, behavior depends on the group store, locking strategy, and transaction topology.

### 16.1. Single JVM with DirectChannel

In simple synchronous examples, processing order is easy to observe. However, two producer threads can still send at the same time. Do not use an application-managed `ArrayList` as a group store without proper synchronization.

### 16.2. ExecutorChannel or Broker

Messages may arrive on multiple workers in non-deterministic order. You need:

- A stable correlation key independent of threads.
- An appropriate store and lock to prevent duplicate release.
- Consistent timeout/reaper behavior.
- Idempotency for the output handler.
- Tracing by group key/eventId rather than relying solely on timestamps.

### 16.3. Multiple Application Instances

If each instance has its own **in-memory MessageGroupStore**, parts of the same order can be split across two different groups and neither will ever complete. You need one of these approaches:

- Partition/route the same key to the same instance.
- Shared/persistent message store with an appropriate locking mechanism.
- A stream processing / stateful aggregation platform supporting key partitioning.
- A process manager suitable for distributed workflows.

Simply adding `@EnableIntegration` does not create automatic cross-instance coordination.

## 17. Aggregator, Gateway, and Request–Reply

A Gateway can send a request and wait for Aggregator to collect the result. However, **the Aggregator might not be ready to emit immediately**.

### 17.1. A Request–Reply Batch

With `Splitter → Aggregator` in a short synchronous flow, the Gateway can receive a collection of results after all parts are processed and aggregated.

### 17.2. Multiple Independent Event Sources

If Payment and Inventory arrive minutes later, holding an HTTP request or Gateway thread waiting for a long time may be inappropriate. You may need to:

- Return `202 Accepted` immediately with `orderId`/`trackingId`.
- Track group status via an API or events.
- Emit `OrderReady` asynchronously when the group completes.
- Have separate SLAs and deadlines for the process.
- Emit error/expired events when the group is incomplete.

### 17.3. `replyChannel` Is Not a Group Key

`replyChannel` specifies where a reply can go in the topology; the group key identifies messages belonging to the same group. Parts from three different sources may have different `replyChannel`s or none at all; the output processor must determine the proper output path per contract rather than blindly picking the first part's `replyChannel`.

## 18. Combining Aggregator with Filter, Router, Transformer, and Publish–Subscribe

### 18.1. Transformer Before Aggregator

A Transformer can normalize parts before storing them in the group:

~~~text
PaymentCapturedRaw -> validate/transform -> PaymentCaptured
InventoryRaw       -> validate/transform -> InventoryReserved
OrderRaw           -> validate/transform -> OrderRegistered
                                         -> Aggregator
~~~

This lets the release strategy operate on **typed payloads** instead of re-parsing JSON or Maps on every evaluation.

### 18.2. Filter Before Aggregator

Filter can drop invalid parts. However, if a group requires all parts, dropping a message can stall the group. You must design error/reject events, timeouts, or placeholder results instead of assuming release will still work on its own.

### 18.3. Router and Aggregator

Router can choose processing branches for each event type before they converge. After Aggregator emits `OrderReady`, another Router can select `priority`/`standard`. When routing across multiple channels, preserve correlation metadata.

### 18.4. Publish–Subscribe and Fan-In

`PublishSubscribeChannel` fans out to multiple subscribers. If branches return independent results, Aggregator can use correlation and sequence metadata to fan in. However, not every subscriber produces a reply. A `void` audit branch cannot be assumed to emit a result for the Aggregator.

### 18.5. Content Enricher and Aggregator

Enricher typically adds lookup data to **one** message; Aggregator collects **multiple messages**. You can enrich `OrderRegistered` with customer tier before feeding it into Aggregator alongside Payment/Inventory. Combining them gives the group normalized input data without requiring the Aggregator itself to call APIs.

### 18.6. Splitter/Aggregator Do Not Automatically Preserve Every Header

When turning one message into multiple parts and reassembling them, you need to verify `traceId`, `businessCorrelationId`, `replyChannel`, and custom headers. Aggregator output can apply a header-combining rule; for data from multiple sources with conflicting values, define an explicit output mapping.

## 19. Error Channel, Retry, and Transaction Boundaries

Different failures have different consequences.

| Error | Nature | Handling Direction |
|---|---|---|
| Part fails schema check | Invalid data | Reject/quarantine, do not retry endlessly |
| Missing correlation key | Cannot determine group | Validate/error before Aggregator |
| Duplicate eventId | Redelivery or data integrity | Dedup/reject, log reason |
| MessageGroupStore unavailable | Infrastructure error | Bounded retry, ensure proper ack/transaction |
| Output processor exception | Domain/code error | Error flow, avoid duplicate release |
| Group waiting too long | Missing part/deadline | Timeout/expiry policy |
| Late arrival | Message arrives after group closed | Correction/reject policy |
| Downstream DB 503 | Handler error after aggregate | Downstream retry/idempotency |

### 19.1. Synchronous and Asynchronous

With `DirectChannel`, exceptions can propagate back to the sender. With executors, adapters, or asynchronous brokers, errors may be sent as `ErrorMessage` to an error channel depending on configuration. Do not assume that merely having an `errorChannel` header causes every exception in every topology to route there automatically.

### 19.2. Retrying Parts Can Cause Repeated Releases

If a part is added to the group but ack fails, the broker may redeliver it. If the group has already released but cleanup is not synchronized with the transaction, output can also be generated again. Placing an **idempotency key on the output handler** is the final line of defense for side effects.

### 19.3. Defining Transaction Boundaries

When using a persistent group store, you must understand the transactions around **adding a part**, **evaluating release**, **emitting output**, **acking the broker**, and **writing to the business DB**. They do not necessarily participate in a single distributed transaction. Practical designs often use outbox and idempotency rather than expecting simultaneous commits across all systems.

## 20. Observing Aggregation Progress

An Aggregator may emit no output for a long time, and that **is not necessarily an error**. Monitoring must distinguish legitimately waiting groups from stuck groups.

| Metric/Trace | Question | Notes |
|---|---|---|
| `aggregation_messages_received_total` | How many parts received? | Break down by flow/type if cardinality is small |
| `aggregation_open_groups` | How many groups are unfinished? | Alert on unbounded growth |
| `aggregation_group_age_seconds` | How long has a group been waiting? | Track percentiles/oldest groups |
| `aggregation_completed_total` | How many groups released? | Differs from input message count |
| `aggregation_expired_total` | How many groups timed out? | Diagnose missing parts |
| `aggregation_duplicates_total` | Are there many duplicate parts? | By reason code |
| `aggregation_late_arrivals_total` | How many events arrive after group closure? | Per producer SLA |
| `aggregation_output_failures_total` | Output processor/downstream errors? | Needs error flow |
| `correlationKey` | Which group is stuck? | Place in controlled logs/traces |

Do not use `orderId`, `eventId`, or `traceId` as unbounded metric labels; they have very high cardinality. Use labels for flow, event type, outcome, and reason code, while keeping specific values in traces/logs subject to security policies.

### 20.1. Structured Logging

~~~text
flow=order-aggregation
eventId=evt-payment-9
groupKey=tenant-a/ORDER-9
partType=PaymentCaptured
groupPartTypes=[OrderRegistered, PaymentCaptured]
release=false
groupAgeMs=18500
traceId=trace-42
~~~

This is an example illustrating operation. Do not log full payment tokens, addresses, customer profiles, or message contents containing sensitive data.

### 20.2. Do Not Conclude Group Completion Solely from `group.size()`

A dashboard showing `group size=3` cannot tell whether the exact three required parts have arrived. Monitoring can include the set of received part types and reason codes for missing parts, while avoiding putting individual ID lists into metric labels.

## 21. Performance and Resources

### 21.1. Memory Grows with the Number of Open Groups

If there are one million orders each waiting for `PaymentCaptured`, the Aggregator may hold one million group states. You must bound wait times, memory usage, and persist state as required. Using a persistent store does not eliminate storage costs; it shifts them to DB/Redis or another backend.

### 21.2. Large Groups

A batch with hundreds of thousands of lines can cause memory pressure if every payload is collected into one collection. If business logic only needs sum/count/min/max, you can design **incremental aggregation** or appropriate stateful stream processing instead of retaining all parts, paired with safe update mechanisms. Do not replace the default Aggregator with an ad-hoc global accumulator variable lacking correlation or transactions.

### 21.3. Hot Keys

If too many events share the same group key, lock contention can cause bottlenecks. Consider partitioning, batching, load limits, backpressure, and downstream throughput. A shared `"unknown"` group key for all messages is a common cause of hot keys and data mixing.

### 21.4. Serialization and Message Stores

When persisting messages to a durable store, payloads/headers must be compatible with the serializer. Avoid storing non-serializable internal objects, tokens, or `MessageChannel` objects outside their proper scope. Test real serialization against the intended store.

## 22. Common Design Mistakes

### Mistake 1 — Using `group.size()` Instead of Checking for All Required Data

**Symptom:** two Payments and one Order cause the system to emit `OrderReady`.

**Fix:** release by **required part types**, add deduplication and validation; test duplicates.

### Mistake 2 — Correlating by an Insufficiently Distinct ID

**Symptom:** orders from the same customer or same `orderId` across two tenants get grouped together.

**Fix:** use a stable business key, including a verified tenant when needed.

### Mistake 3 — No Timeout/Expiry

**Symptom:** groups wait forever, message store grows without bound.

**Fix:** set deadlines, group expiry, alerts, and an incomplete-group policy.

### Mistake 4 — Assuming Splitter/Aggregator Always Receives All Parts

**Symptom:** Filter drops one part, Aggregator never releases.

**Fix:** filter before Splitter, emit a placeholder result, or use custom release/timeout.

### Mistake 5 — Using In-Memory Store When Recovery After Restart Is Needed

**Symptom:** while waiting for two of three events, the process restarts and the group disappears.

**Fix:** persistent `MessageGroupStore` or appropriate workflow/state store, along with recovery tests.

### Mistake 6 — Relying on Arrival Order

**Symptom:** output reverses line-item order when running asynchronously.

**Fix:** use `sequenceNumber`/`lineIndex` and sort explicitly before building output.

### Mistake 7 — Assuming Aggregator Provides Exactly-Once by Itself

**Symptom:** output or side effects are processed twice on broker redelivery.

**Fix:** deduplicate `eventId`, use an idempotent output handler, and apply transaction/outbox patterns.

### Mistake 8 — Using `customerId` as the Group Key for `OrderReady`

**Symptom:** two orders from the same customer mix payment and inventory.

**Fix:** correlate by `orderId` or a composite key.

### Mistake 9 — No Late-Arrival Policy Defined

**Symptom:** an event arriving after group closure creates a stuck new group or a second output.

**Fix:** define closed-group/tombstone/retention handling or a correction mechanism.

### Mistake 10 — Logging Sensitive Group Payloads

**Symptom:** dashboards contain full payment/customer data.

**Fix:** log controlled group keys, event types, outcomes, reasons, group age, and trace IDs; mask/hash identifiers when necessary.

### Mistake 11 — Confusing Content Enricher with Aggregator

**Symptom:** only needing to look up a profile for one order, yet creating a group store and release strategy.

**Fix:** use Content Enricher for lookups; use Aggregator when multiple messages truly need to converge.

### Mistake 12 — Not Checking Transaction/Error Boundaries

**Symptom:** the group releases, DB fails, and retry produces multiple outputs.

**Fix:** model failure windows, write replay/idempotency tests, and configure topology-appropriate error handling.

## 23. Hands-On Exercises

**Context:** an e-commerce platform needs to calculate order totals and only emit `OrderReady` when Order, Payment, and Inventory are all present.

### Exercise 1 — Basic Splitter → Aggregator

Use `OrderLinesFlowConfiguration` from Section 8. Send a List of three `OrderLine`s and verify there is only **one output message** carrying three `PricedLine`s.

### Exercise 2 — Computing Total After Aggregate

Add a Transformer after `aggregate()` to build `OrderPriceResult`. Choose a reliable way to obtain `orderId` from request/correlation metadata and preserve it across Splitter; test that the sum equals `325.00`.

### Exercise 3 — Two Interleaved Batches

Create two batches with different group IDs. Send messages interleaved if the test topology allows, and verify outputs do not mix A/B and each batch releases exactly once.

### Exercise 4 — Filter Drops One Part

Place a Filter after Splitter that rejects one line item. Observe that Aggregator lacks enough parts when using default `sequenceSize`. Redesign by filtering before split or using custom release/partial results.

### Exercise 5 — Custom Correlation

Create `OrderCorrelationKey(tenantId, orderId)` where tenant comes from a verified source. Test that the same `orderId` in two tenants does not enter the same group.

### Exercise 6 — Custom Release

Write `OrderGroupPolicy.complete(...)` requiring exactly one `OrderRegistered`, `PaymentCaptured`, and `InventoryReserved`. Test all arrival orders as well as missing/duplicate cases.

### Exercise 7 — Output Processor

Use `OrderReadyAssembler` to build an immutable DTO. Test `amount`, `paymentId`, `reservationId`, and that `orderId`s are never mixed.

### Exercise 8 — Timeout and Incomplete Group

Simulate an order with only `OrderRegistered` and `PaymentCaptured`. Configure expiry/group timeout according to your Spring Integration version; verify a clear outcome, cleanup, and expired metric.

### Exercise 9 — Replay/Redelivery

Resend `PaymentCaptured` with the same `eventId` before and after group completion. Design dedup/late-arrival policies and an idempotent output handler.

### Exercise 10 — Restart/Recovery

Use a persistent group store suited to the environment. Send two parts, restart the app, send the third part, and verify exactly one release if required by the system.

### Exercise 11 — Gateway or Async Status?

Compare a pricing batch returning results immediately with three independent events taking several minutes. Design the API/`trackingId`, SLA, and output events for the second case.

### Exercise 12 — Observability

Attach metrics for open groups, expired groups, completed groups, duplicates, and latency; produce logs by correlation and `eventId` without sensitive data.

### Self-Check Questions

1. How does Aggregator differ from Transformer and Content Enricher?
2. Why does Aggregator need both a correlation strategy and a release strategy?
3. What is the meaning of Splitter's `sequenceSize`?
4. When is the default Aggregator insufficient for independent event sources?
5. Why can `group.size()==3` release incorrectly?
6. Why should the group key be `orderId` rather than `customerId`?
7. With multiple tenants, how should the correlation key change?
8. What is the output processor responsible for?
9. If a Filter drops a part, what risk does the Aggregator face?
10. Does the default `MessageGroupStore` guarantee survival across restarts?
11. How does a group timeout differ from an HTTP request timeout?
12. How do late arrival and duplicate differ?
13. Why is `MessageHeaders.ID` unsuitable as a business event ID?
14. How do you prevent duplicate output side effects after replay?
15. With a result collection, how do you preserve line-item order?
16. When should partial results be emitted and when should they never be?
17. Why can multiple JVMs each using their own in-memory store cause a group to never complete?
18. Which metrics help detect stuck groups?

## 24. Aggregator Design Checklist

- [ ] Define the N→1 goal and output schema before writing the flow.
- [ ] Document the message source: Splitter or independent producers.
- [ ] Correlation key is unique within the proper business/tenant scope.
- [ ] Release strategy verifies **complete facts**, not blind counting.
- [ ] Output processor creates a typed DTO and explicit header mapping.
- [ ] Parts are validated/normalized before entering the group.
- [ ] Splitter sequence/correlation headers are preserved when needed.
- [ ] Behavior is understood if a Filter drops a part.
- [ ] Policies exist for duplicate/`eventId` and late arrivals.
- [ ] Policies exist for timeout/expiry/incomplete groups.
- [ ] `MessageGroupStore` matches memory/durability/scale needs.
- [ ] Locking/transaction/concurrency strategy exists for multiple workers/instances.
- [ ] Arrival order is not relied upon without guarantees.
- [ ] Handler after aggregate has idempotency for redelivery.
- [ ] Gateway/reply/error/ack are designed around latency and topology.
- [ ] Unit tests exist for correlation/release/assembler and integration tests for real channels.
- [ ] Tests exist for restart, recovery, and concurrency if production requires them.
- [ ] Open groups, group age, completed, expired, and duplicates are monitored.
- [ ] Sensitive payloads are not logged and unverified client headers are not used as group keys.

## 25. Summary

**Aggregator** in Spring Integration is where **multiple related messages converge into one result**. To do it right, it must determine the **correlation key**, maintain the **`MessageGroup`**, evaluate the **release strategy**, run the **output processor**, and manage incomplete, expired, or late-arriving groups. With `Splitter → Aggregator`, the `correlationId`, `sequenceNumber`, and `sequenceSize` headers help group and release parts of the same batch. For independently arriving events, custom correlation/release, duplicate policies, and appropriate storage are required.

Aggregator does not replace Content Enricher (adding data via lookup), Transformer (changing representation), or Router (choosing paths). Nor does it **automatically guarantee persistence or exactly-once delivery**. You must test real flows, handle errors properly for sync/async topologies, preserve tracing/correlation, and apply idempotency to downstream side effects.

When combining Aggregator with Splitter, Filter, Transformer, Router, Gateway, retry, and error channels, the **SPRING_INTEGRATION_PATTERN** module can build parallel or asynchronous processing pipelines while still producing meaningful, scalable, and observable aggregated results.

### References

- Spring Integration Reference — Aggregator: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Integration Reference — Splitter: https://docs.spring.io/spring-integration/reference/splitter.html
- Spring Integration Reference — Correlation & release: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Integration Reference — Message Store: https://docs.spring.io/spring-integration/reference/message-store.html
- Spring Integration Reference — Java DSL: https://docs.spring.io/spring-integration/reference/dsl.html
- Spring Integration API — MessageGroup: https://docs.spring.io/spring-integration/api/org/springframework/integration/store/MessageGroup.html
- Spring Integration API — ReleaseStrategy: https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/ReleaseStrategy.html
- Spring Integration API — CorrelationStrategy: https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/CorrelationStrategy.html
- Spring Integration API — DefaultAggregatingMessageGroupProcessor: https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/DefaultAggregatingMessageGroupProcessor.html
- JUnit 5 User Guide — Parameterized Tests: https://junit.org/junit5/docs/current/user-guide/#writing-tests-parameterized-tests
