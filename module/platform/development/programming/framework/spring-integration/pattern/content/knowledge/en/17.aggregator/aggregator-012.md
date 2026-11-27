# Choosing the Output Channel After Aggregation

In **Spring Integration**, Aggregator collects multiple related messages into one result. However, once a group is **released**, the system still has to decide **which channel the result will be sent to**: a fixed processing channel, a Router choosing branches dynamically, an event-publishing adapter, or a reply path back to a Gateway.

The lesson **Choosing the Output Channel After Aggregation** belongs to the **Aggregator** chapter of the **SPRING_INTEGRATION_PATTERN** module. The module aims to build loosely coupled, extensible message flows using Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, correlation, and per-branch testing and monitoring techniques.

The core focus of this lesson is separating **conditions for producing output** from **where output goes**. An Aggregator may collect data accurately yet still leave a Gateway timing out, send results to the wrong channel, or fail to reach consumers if routing and headers are not properly designed.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Describe the processing chain **correlation → release → output processor → output channel**.
2. Distinguish Aggregator's output channel from `replyChannel`, `errorChannel`, `discardChannel`, and `MessageGroupStore`.
3. Configure a fixed output channel using Java DSL `.aggregate().channel(...)`.
4. Use a Transformer and Router **after aggregation** to choose destinations based on the aggregated result.
5. Understand the requirements for returning replies to a Gateway, especially when the output message combines headers from multiple parts.
6. Choose between `DirectChannel`, `QueueChannel`, `ExecutorChannel`, `PublishSubscribeChannel`, or outbound adapters based on requirements.
7. Design separate handling for partial results, expiries, errored messages, and late arrivals.
8. Test that only one output is emitted when a group completes, that it routes to the right branch without early release, and that required metadata is preserved.
9. Identify channel configuration mistakes, missing consumers, wrong correlation, lost reply headers, duplicate processing, and retries.
10. Combine Aggregator with Splitter, Filter, Transformer, Router, Gateway, and error flows observably.

## 2. At What Stage Does Aggregator Produce Output?

An Aggregator executes three main responsibilities before looking up a destination channel:

- **Correlation strategy**: which messages belong to the same group?
- **Release strategy**: does the group have enough data to emit a result?
- **Output processor**: what payload/message are the group's messages aggregated into?

Only after the output processor builds the result does the framework dispatch the message via the corresponding output routing.

~~~mermaid
flowchart LR
    P["Message parts"] --> C["Correlation strategy"]
    C --> S[("MessageGroupStore")]
    S --> R{"Release strategy"}
    R -->|"Incomplete"| W["Hold group, wait for more"]
    R -->|"Complete"| O["Output processor"]
    O --> CH["Output channel"]
    CH --> D["Downstream"]
~~~

| Question | Component | Example |
|---|---|---|
| Are the messages related? | Correlation | Same `orderId=ORDER-1001` |
| Is it complete? | Release | All 3 parts with `sequenceSize=3` |
| What result is created? | Output processor | `Collection<PricedLine>` |
| Where does the result go? | Output channel/Router/reply | `orders.aggregated` |
| Did the downstream handler finish? | Downstream/ack/metric | DB commit, broker ack |

**Never treat release as a completed downstream business operation.** A released group and an output sent into a queue still do not prove a consumer saved to the database.

### 2.1. An Order Example

~~~text
ORDER-1001
SKU-A: 2 x 100.00 = 200.00
SKU-B: 1 x  50.00 =  50.00
SKU-C: 3 x  25.00 =  75.00
--------------------------
Total               325.00
~~~

If every order goes through reconciliation, output can go to a fixed channel `orders.aggregated`. If only orders of **1,000.00** or more require high-value handling, a Router after aggregation selects `orders.highValue` or `orders.standard` based on the **aggregated total**, not an individual line.

## 3. Rules for Choosing Output Channels in Spring Integration

In a Spring Integration message-producing endpoint, the general rule is:

1. If the endpoint has an **explicitly configured output channel**, use that destination for reply/output.
2. If there is no fixed output channel, the framework can use **`replyChannel` from the result message** per messaging contract.
3. If no valid destination is found, output may fail to dispatch and cause an error or Gateway timeout depending on topology.

~~~mermaid
flowchart TD
    A["Group release succeeded"] --> B["Build aggregated output"]
    B --> C{"Fixed output channel?"}
    C -->|Yes| D["Dispatch to configured channel"]
    C -->|No| E{"Output message has valid replyChannel?"}
    E -->|Yes| F["Dispatch to reply channel"]
    E -->|No| G["Missing destination: handle error per topology"]
~~~

With Aggregator, the key nuance is that **the output message is built from multiple parts**, so headers on the output do not automatically match every header on individual parts. Never take `replyChannel` from the last message and assume it is the `replyChannel` for the entire group.

### 3.1. Distinguishing Channels and Metadata

| Component | Function | Is It the Default Success Output Path? |
|---|---|---|
| `outputChannel` | Destination for aggregated results | Yes, when configured |
| `replyChannel` | Destination for replying to a request | Possibly, when no fixed output exists and header remains valid |
| `errorChannel` | Path for handling exceptions per topology | No |
| `discardChannel` | Path for messages/groups discarded per config | No |
| `MessageGroupStore` | Persists group state | No |
| `correlationId` | Key linking group messages | No |
| `sequenceNumber`, `sequenceSize` | Metadata about parts | No |
| `businessCorrelationId` | Business linkage marker | No |

**A fixed output channel takes precedence over header-based reply addressing** at that endpoint. To both publish an event and reply to a Gateway, design two deliberate paths; never expect Spring to send two copies automatically from one reply.

## 4. Which Channel Type Should You Choose?

| Channel | Characteristics | Suitable For | Main Risk |
|---|---|---|---|
| `DirectChannel` | Invokes one consumer synchronously on sender thread | Next fast processing step | Slow/failing consumer blocks flow |
| `QueueChannel` | Consumers poll/receive messages | Decoupling pace or testing | In-memory by default, requires poller |
| `ExecutorChannel` | Dispatches via thread pool | Async processing within one JVM | Backlogs, rejections, worker errors |
| `PublishSubscribeChannel` | Broadcasts to subscribers | Audit + analytics + notification | Branches have differing errors/latencies |
| Channel wired to outbound adapter | Forwards events to broker/API | Integrating external systems | Delivery/ack depends on adapter/broker |
| Channel followed by a Router | Hands result to routing policy | Destination by amount/status/region | Requires exact output schema |

Never pick `QueueChannel` merely because "output needs a queue" and then forget to configure a poller/consumer. Similarly, sending output into `PublishSubscribeChannel` **does not turn the result into a durable event** replayable after a restart.

## 5. Java 17 Example: Input Model and Per-Line Processing

We build an integration-testable flow: receives `List<OrderLine>`, Splitter creates individual messages, Transformer prices lines, and Aggregator collects them into one output message.

### 5.1. Payload Types

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

Both `public` records must be placed in separate Java source files with matching names in a real project. Payloads use `BigDecimal` for monetary calculations instead of `double`.

### 5.2. Per-Line Transformation Policy

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

        return new PricedLine(
                line.sku(),
                line.unitPrice().multiply(
                        BigDecimal.valueOf(line.quantity())));
    }
}
~~~

The policy is a pure function with no DB or HTTP calls. If a part is invalid, it throws an error so the flow does not treat a bad part as a priced result. Never silently swallow errors and leave Aggregator waiting short of `sequenceSize`.

## 6. Fixed Output Channel in Java DSL

This is the simplest case to implement: every completed group goes to the same `orders.aggregated` channel.

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
public class FixedOutputAggregationConfig {

    @Bean(name = "orders.lines.input")
    public MessageChannel inputChannel() {
        return new DirectChannel();
    }

    @Bean(name = "orders.aggregated")
    public PollableChannel outputChannel() {
        return new QueueChannel();
    }

    @Bean
    public LinePricingPolicy linePricingPolicy() {
        return new LinePricingPolicy();
    }

    @Bean
    public IntegrationFlow aggregateOrderLines(
            LinePricingPolicy policy) {

        return IntegrationFlow.from("orders.lines.input")
                .split()
                .transform(OrderLine.class, policy::price)
                .aggregate()
                .channel("orders.aggregated")
                .get();
    }
}
~~~

Two key lines:

~~~java
.aggregate()
.channel("orders.aggregated")
~~~

`aggregate()` collects parts per correlation/release strategies. `channel("orders.aggregated")` sets the **fixed destination** for the result emitted by this endpoint. It does not determine which group a message belongs to, nor does it force incomplete groups to release.

### 6.1. Why Isn't the Output Just the Final Line?

~~~text
Producer:
  Message<List<OrderLine>>

Splitter:
  Message<OrderLine> A (1/3)
  Message<OrderLine> B (2/3)
  Message<OrderLine> C (3/3)

Transformer:
  Message<PricedLine> A
  Message<PricedLine> B
  Message<PricedLine> C

Aggregator:
  One Message<Collection<PricedLine>>

Output:
  orders.aggregated
~~~

With the default aggregation processor in this basic example, the output payload is typically a **collection of payloads**. It does not automatically compute a single monetary total. If downstream needs an `OrderSummary`, add an output processor or a Transformer after Aggregator.

### 6.2. Timing of Message Emission

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant S as Splitter
    participant T as Transformer
    participant G as Aggregator
    participant O as orders.aggregated

    P->>S: 3 OrderLines
    S->>T: Part A, sequence 1/3
    T->>G: PricedLine A
    Note over G: Not yet released
    S->>T: Part B, sequence 2/3
    T->>G: PricedLine B
    Note over G: Not yet released
    S->>T: Part C, sequence 3/3
    T->>G: PricedLine C
    Note over G: Group releases
    G->>O: One aggregated message
~~~

Never embed success-event emission inside `releaseStrategy`; that policy can be called multiple times during a group's lifecycle. Sending output is the responsibility of Aggregator and downstream endpoints.

## 7. Testing Fixed Output via `MessageChannel`

Unit testing `LinePricingPolicy` cannot prove Aggregator sent output to the right channel. Use Spring Test, JUnit 5, and `QueueChannel` to verify wiring.

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

@SpringJUnitConfig(classes = FixedOutputAggregationConfig.class)
class FixedOutputAggregationTest {

    @Autowired
    @Qualifier("orders.lines.input")
    MessageChannel input;

    @Autowired
    @Qualifier("orders.aggregated")
    PollableChannel output;

    @Test
    void oneGroupProducesOneOutputOnChosenChannel() {
        List<OrderLine> lines = List.of(
                new OrderLine(
                        "SKU-A", new BigDecimal("100.00"), 2),
                new OrderLine(
                        "SKU-B", new BigDecimal("50.00"), 1),
                new OrderLine(
                        "SKU-C", new BigDecimal("25.00"), 3));

        assertTrue(input.send(
                MessageBuilder.withPayload(lines)
                        .setHeader("traceId", "trace-1001")
                        .build()));

        Message<?> aggregate = output.receive(1000);

        assertNotNull(aggregate);
        assertInstanceOf(
                Collection.class, aggregate.getPayload());

        Collection<?> values =
                (Collection<?>) aggregate.getPayload();
        assertEquals(3, values.size());

        Set<PricedLine> actual = values.stream()
                .map(PricedLine.class::cast)
                .collect(Collectors.toSet());

        assertEquals(Set.of(
                new PricedLine("SKU-A",
                        new BigDecimal("200.00")),
                new PricedLine("SKU-B",
                        new BigDecimal("50.00")),
                new PricedLine("SKU-C",
                        new BigDecimal("75.00"))), actual);

        assertNull(output.receive(0));
    }
}
~~~

The test verifies one message containing three results arrives at `orders.aggregated`. It **does not** prove the DB committed, a broker acked, or output survives restarts. The test fixture uses an in-memory `QueueChannel`, not a persistent broker.

### 7.1. Incomplete Parts Case

The synchronous Splitter flow in the example processes all parts within a single send call. To test "incomplete group," set up an Aggregator accepting individual `Message<PricedLine>` messages with valid `correlationId`/`sequenceNumber`/`sequenceSize`, or use independent message sources with custom correlation/release. Before all parts arrive, `receive(0)` on output must return no message.

### 7.2. Multiple Batches

Send two batches A/B and assert **two** separate output messages without mixed contents. If concurrent processing is enabled, also test interleaved parts across two groups to verify the correlation strategy is sound.

## 8. When Is Dynamic Output Channel Selection Needed?

Suppose the whole order is evaluated by **total amount**:

- Total `1000.00` or higher: `orders.highValue`.
- Total under `1000.00`: `orders.standard`.

Every individual order line may be under 1000, yet the **group's sum** can cross the threshold. Placing a Router **before** aggregation classifies by individual line rather than by whole order.

~~~mermaid
flowchart LR
    L["PricedLines"] --> A["Aggregator"]
    A --> T["Transformer: OrderSummary"]
    T --> R{"Router by total"}
    R -->|"total >= 1000"| H["orders.highValue"]
    R -->|"total < 1000"| S["orders.standard"]
~~~

**Principle:** when destination selection depends on the entire group's data, have Aggregator emit a **clearly typed result**, then place the Router afterward.

## 9. Building the Summary DTO Before Routing

### 9.1. `OrderSummary`

~~~java
import java.math.BigDecimal;
import java.util.List;

public record OrderSummary(
        List<PricedLine> lines,
        BigDecimal total
) {
    public OrderSummary {
        lines = List.copyOf(lines);
    }
}
~~~

To stay focused on output channel selection, the sample DTO does not yet include `orderId`. For production, output should carry a trusted business group key for tracing/idempotency: e.g., `orderId` or composite `tenantId+orderId`.

### 9.2. `SummaryAssembler`

~~~java
import java.math.BigDecimal;
import java.util.Collection;
import java.util.Comparator;
import java.util.List;

public final class OrderSummaryAssembler {

    public OrderSummary assemble(Collection<?> parts) {
        if (parts == null || parts.isEmpty()) {
            throw new IllegalArgumentException(
                    "EMPTY_AGGREGATION_RESULT");
        }

        List<PricedLine> lines = parts.stream()
                .map(PricedLine.class::cast)
                .sorted(Comparator.comparing(PricedLine::sku))
                .toList();

        BigDecimal total = lines.stream()
                .map(PricedLine::lineTotal)
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        return new OrderSummary(lines, total);
    }
}
~~~

This function purely converts the **collection output** into a summary. It **is not an Aggregator endpoint** because it does not hold messages in a `MessageGroup` or decide release. It can be used in a Transformer step after Aggregator.

Sorting by SKU is only for deterministic display. If business rules require the original line order, retain a trusted `lineIndex` or `sequenceNumber` and sort by that key; never assume arrival order is preserved under asynchronous execution.

## 10. Router Selecting Channel from Aggregated Data

### 10.1. Router Annotation

~~~java
import java.math.BigDecimal;

import org.springframework.integration.annotation.Router;

public final class OrderSummaryRouter {

    private static final BigDecimal HIGH_VALUE =
            new BigDecimal("1000.00");

    @Router(inputChannel = "orders.summary")
    public String destination(OrderSummary summary) {
        return summary.total().compareTo(HIGH_VALUE) >= 0
                ? "orders.highValue"
                : "orders.standard";
    }
}
~~~

`@Router` returns the channel name for the aggregated output message. Never pull channel names from unverified client headers, as that could allow routing to unauthorized internal channels.

### 10.2. Configuring an Independent Dynamic Flow

~~~java
import java.util.Collection;

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
public class DynamicOutputAggregationConfig {

    @Bean(name = "orders.dynamic.input")
    MessageChannel input() {
        return new DirectChannel();
    }

    @Bean(name = "orders.summary")
    MessageChannel summary() {
        return new DirectChannel();
    }

    @Bean(name = "orders.highValue")
    PollableChannel highValue() {
        return new QueueChannel();
    }

    @Bean(name = "orders.standard")
    PollableChannel standard() {
        return new QueueChannel();
    }

    @Bean
    LinePricingPolicy pricingPolicy() {
        return new LinePricingPolicy();
    }

    @Bean
    OrderSummaryAssembler summaryAssembler() {
        return new OrderSummaryAssembler();
    }

    @Bean
    OrderSummaryRouter router() {
        return new OrderSummaryRouter();
    }

    @Bean
    IntegrationFlow aggregateAndRoute(
            LinePricingPolicy pricing,
            OrderSummaryAssembler assembler) {

        return IntegrationFlow.from("orders.dynamic.input")
                .split()
                .transform(OrderLine.class, pricing::price)
                .aggregate()
                .transform(Collection.class, assembler::assemble)
                .channel("orders.summary")
                .get();
    }
}
~~~

How it works:

1. `orders.dynamic.input` receives the List of order lines.
2. Splitter creates individual messages, Transformer creates `PricedLine`s.
3. Aggregator releases a collection.
4. Transformer `OrderSummaryAssembler` creates `OrderSummary`.
5. Result goes to `orders.summary`.
6. Router subscribes to `orders.summary` and selects `orders.highValue` or `orders.standard`.

`orders.summary` here is a **fixed intermediate channel**, while the **final business destination is dynamic**. There is no contradiction: each endpoint has one responsibility, and Router is where branching happens.

**This is a separate demo configuration** from `FixedOutputAggregationConfig`; do not register both on the same input channel or with duplicate bean names expecting them to form a single pipeline.

## 11. Integration Test for Dynamic Routing

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = DynamicOutputAggregationConfig.class)
class DynamicOutputAggregationTest {

    @Autowired
    @Qualifier("orders.dynamic.input")
    MessageChannel input;

    @Autowired
    @Qualifier("orders.highValue")
    PollableChannel high;

    @Autowired
    @Qualifier("orders.standard")
    PollableChannel normal;

    @Test
    void routesHighValueOnlyToHighChannel() {
        List<OrderLine> lines = List.of(
                new OrderLine(
                        "SKU-A", new BigDecimal("500.00"), 2),
                new OrderLine(
                        "SKU-B", new BigDecimal("50.00"), 1));

        assertTrue(input.send(
                MessageBuilder.withPayload(lines).build()));

        Message<?> routed = high.receive(1000);
        assertNotNull(routed);
        assertInstanceOf(OrderSummary.class, routed.getPayload());
        OrderSummary summary =
                (OrderSummary) routed.getPayload();

        assertEquals(
                new BigDecimal("1050.00"), summary.total());
        assertEquals(2, summary.lines().size());

        assertNull(normal.receive(0));
        assertNull(high.receive(0));
    }

    @Test
    void routesStandardOnlyToStandardChannel() {
        List<OrderLine> lines = List.of(
                new OrderLine(
                        "SKU-C", new BigDecimal("100.00"), 2));

        assertTrue(input.send(
                MessageBuilder.withPayload(lines).build()));

        Message<?> routed = normal.receive(1000);
        assertNotNull(routed);
        assertInstanceOf(OrderSummary.class, routed.getPayload());

        OrderSummary summary =
                (OrderSummary) routed.getPayload();

        assertEquals(
                new BigDecimal("200.00"), summary.total());

        assertNull(high.receive(0));
        assertNull(normal.receive(0));
    }
}
~~~

You should also test boundary values **999.99**, **1000.00**, and **1000.01**. With `BigDecimal.compareTo(...) >= 0`, exactly 1000.00 goes to the `highValue` branch. Using `double`, monetary calculations could suffer precision drift, misclassifying values near the threshold.

### 11.1. Test Layering

| Layer | Content |
|---|---|
| Unit test `OrderSummaryAssembler` | Computes sum properly, handles empty collections |
| Unit test routing policy | Returns channel name by threshold |
| Spring integration test | Bean/channel wiring correct and result enters only one branch |
| Failure test | No output on missing part, processor error, wrong channel name |
| End-to-end test | Downstream processing/ack/DB idempotency work properly |

The two integration tests above only verify behavior within a synchronous `ApplicationContext`. Do not infer they prove broker durability or multi-JVM behavior.

## 12. One Shared Channel Before Splitting Branches

Some systems want **every result** to pass through a common verification step before the Router:

~~~mermaid
flowchart LR
    A["Aggregator"] --> C["orders.aggregated"]
    C --> V["OrderSummaryValidator"]
    V --> R{"Router"}
    R --> H["High value"]
    R --> S["Standard"]
    V -->|Invalid| E["Reject / error"]
~~~

This pattern helps when:

- All outputs must pass group-level validation.
- A shared metric/audit record must be emitted.
- Output schema must be normalized before branching.
- A shared enrichment or idempotency policy applies.
- You want to change the Router without altering Aggregator correlation/release logic.

**Never put business routing logic into the release strategy.** The release strategy can be called every time a group changes and must not contain side effects or pick destinations at a point where no complete output payload exists yet.

## 13. Output Channel and Gateway `replyChannel`

A Gateway sends a request and typically awaits a reply within a timeout. If `Splitter → Aggregator` sits inside, the final reply can return to the Gateway when the topology is designed appropriately.

~~~mermaid
sequenceDiagram
    participant G as Gateway
    participant S as Splitter
    participant A as Aggregator
    participant R as ReplyChannel

    G->>S: Request + replyChannel
    S->>A: Part 1
    S->>A: Part 2
    S->>A: Part 3
    Note over A: Group releases
    A-->>R: Aggregated result if reply routing is valid
    R-->>G: Reply
~~~

Things to verify:

- Does Aggregator have a **fixed `outputChannel`**?
- Does the post-aggregate output message still carry a valid **`replyChannel`**?
- Did the output processor construct a fresh `Message<?>` and strip headers?
- When a group holds parts from multiple sources, do reply headers conflict?
- Does the Gateway timeout fit the time required for the group to complete?

### 13.1. Why Can a Fixed Output Cause a Gateway Timeout?

Suppose the Gateway sends a request with a temporary `replyChannel`, yet the flow configures:

~~~java
.aggregate()
.channel("orders.aggregated")
~~~

The result is dispatched to `orders.aggregated`. The Gateway **does not automatically receive a copy** simply because the original request had a `replyChannel`. If that channel only has consumers that do not return a result to the Gateway, the Gateway can time out. Choose an **explicit reply path**, or design the result to emit to another event/queue while callers poll status.

### 13.2. When Should You Not Wait for a Synchronous Reply?

A batch of a few lines can aggregate quickly and reply in short order. When a group waits for `PaymentCaptured` and `InventoryReserved` from independent producers, however, it may take several minutes or longer. Never hold an HTTP request or Gateway thread waiting indefinitely.

A more suitable model:

~~~text
POST /orders/ORDER-1001/complete
  -> 202 Accepted + trackingId

OrderRegistered / PaymentCaptured / InventoryReserved
  -> Aggregator by orderId
  -> OrderReady event
  -> Status store / outbound adapter

Client:
  GET /orders/ORDER-1001/status
~~~

In this model, the output channel after Aggregator usually connects to a broker/event handler, **not a temporary `replyChannel`** from an already-finished HTTP request.

### 13.3. Headers Across Multiple Parts Are Not Identical

A group may contain parts from three producers, each with different `replyChannel`, `traceId`, and `errorChannel` values. Aggregator cannot guess which Gateway is the right target for the **whole group** if metadata lacks a unified contract.

In multi-source independent models, it is usually best to configure a **fixed output channel** with explicit business correlation/tracking IDs instead of picking one part's `replyChannel` at random.

## 14. Controlling Headers After Aggregation

An aggregated output message is not "the last arriving part forwarded onward." The framework must handle metadata from **multiple input messages**. Inconsistent header values may be dropped or processed according to header-aggregation policies; therefore, never assume every part's headers stay intact.

| Header | Meaning | Post-Aggregation Principle |
|---|---|---|
| `correlationId` | Links group or split batch | Check group/result contract |
| `sequenceNumber` | Order of one part | Do not treat as output message order |
| `sequenceSize` | Expected part count | Do not assume it describes the new output |
| `traceId` | Traces span/flow | Choose consistent trace context |
| `businessCorrelationId` | Business ID of group | Build from trusted business key |
| `replyChannel` | Reply destination | Use only if output carries valid header |
| `errorChannel` | Error notification path | Never forward blindly across boundaries |
| `tenantId` | Access scope | Validate consistently across whole group |
| `MessageHeaders.ID` | Message instance identifier | Never use instead of event ID |
| `routingHint` | Processing destination hint | Trust only computed/verified values |

### 14.1. Never Route by the Last Part's Header

Suppose Order and Payment have different metadata, and the Inventory part arrives last. Using `priority` from Inventory to decide routing for `OrderReady` can send output to the wrong branch.

Safe approach:

1. Correlation strategy groups parts of the same business group accurately.
2. Release strategy ensures all mandatory facts are present.
3. Output processor builds the result DTO from the **entire group**.
4. Router uses the verified DTO to choose the destination.

### 14.2. Custom Output `Message`

An output processor can return an explicitly constructed `Message<?>`:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

// Illustrative snippet inside a processing method:
Message<OrderSummary> output = MessageBuilder
        .withPayload(summary)
        .setHeader("businessCorrelationId", trustedGroupKey)
        .setHeader("schemaVersion", 1)
        .build();
~~~

`summary` and `trustedGroupKey` are variables computed per contract outside the snippet. When creating a new `Message`, **explicitly retain necessary headers**. Never blindly copy all headers from one part, especially across broker/cross-JVM boundaries with `replyChannel` or non-serializable Java objects.

## 15. Output to Multiple Subscribers

If an aggregated result must go to Audit, Analytics, and Notification, use a `PublishSubscribeChannel` after Aggregator:

~~~mermaid
flowchart LR
    G["Aggregator"] --> P(("PublishSubscribeChannel"))
    P --> A["Audit"]
    P --> N["Notification"]
    P --> M["Analytics"]
~~~

Notes:

- Publish–Subscribe dispatches to currently registered subscribers without persisting history.
- Without an executor, dispatch is usually synchronous; one failing subscriber can affect other branches depending on config.
- With an executor, channel-level send success does not mean every handler finished.
- Branches with side effects must be idempotent if output can be redelivered.
- If output requires durable delivery, a reliable broker/outbox is usually required.

Never replace a Router with Publish–Subscribe when business logic needs to **pick exactly one destination**, and never use a Router when business logic needs to **broadcast to every subscriber**.

## 16. Output via `QueueChannel` or `ExecutorChannel`

### 16.1. `QueueChannel`

`QueueChannel` receives output and waits for a poller/consumer to pull it. It is useful for decoupling pace or test fixtures, yet is an in-memory queue by default. Without a poller, messages sit in the queue with no handler executing.

### 16.2. `ExecutorChannel`

`ExecutorChannel` dispatches to consumers via a thread pool. You must manage:

- Bounded pool size and queue capacity.
- Backpressure/rejection policy.
- Worker timeouts and error handling.
- Ordering when multiple group outputs process concurrently.
- Tracing/correlation across thread boundaries.

Never treat `send()==true` as proof the worker committed to the DB. Measure processing outcomes at the handler or broker ack.

### 16.3. Adapter to Broker

Placing an outbound adapter after the channel emits aggregated outputs to external systems. However, an internal channel is not a transactional outbox. If the broker acks while the DB fails, or vice versa, an outbox/idempotency may be required per business rules.

## 17. Incomplete Groups, Timeouts, and Partial Results

If the release strategy returns `false`, Aggregator **has not yet emitted a successful result**. Choosing an output channel only applies when there is a result to send.

~~~mermaid
flowchart TD
    G["MessageGroup"] --> R{"Release?"}
    R -->|Complete| O["Complete result"]
    O --> C["orders.completed"]
    R -->|Incomplete| W["Wait for next part"]
    W --> T{"Timeout/expiry?"}
    T -->|No| W
    T -->|Yes| P{"Partial allowed?"}
    P -->|Yes, configured| I["Partial result"]
    I --> IC["orders.incomplete"]
    P -->|No| E["Expiry/discard/monitor"]
~~~

Partial results should only be sent if **downstream knows they are partial**. An analytics report may tolerate missing data, whereas a shipping order must never be marked "ready" without `InventoryReserved`.

### 17.1. Results with Explicit Status

~~~java
public enum CompletionStatus {
    COMPLETE,
    PARTIAL
}

public record AggregationOutcome<T>(
        CompletionStatus status,
        T value,
        String reasonCode
) {}
~~~

The top-level `public` types in the snippet need separate source files in a project. These are illustrative domain types, not built-in Spring Integration classes.

If a group can emit partial results, a Router after Aggregator should inspect `status`:

~~~text
AggregationOutcome(COMPLETE) -> orders.completed
AggregationOutcome(PARTIAL)  -> orders.incomplete
~~~

Do not rely only on message count and send everything to the same success channel. Exact timeout, expiry, and send-partial configurations depend on business rules and your Spring Integration version, requiring integration tests.

### 17.2. Error Channel Is Not the Partial Path

- **Error**: output processor/handler throws an exception or dispatch fails.
- **Incomplete**: group lacks full data when reaching deadline.
- **Partial result**: intentional business result from an incomplete group.
- **Discard**: rejection branch per configuration.

These four cases must not be mixed onto one success channel leaving consumers to guess.

## 18. Late Arrivals, Duplicates, and Corrections

If Aggregator already emitted `OrderReady` and a part arrives late or replays, depending on group lifecycle it may spawn a new group, discard the part, or produce another result. That directly impacts the output channel and side effects.

~~~text
Complete OrderReady  -> orders.ready.events
Subsequent amendment -> orders.corrections
Known duplicate      -> dedup / reject
~~~

A correction event must have its own contract; never re-emit it as a brand-new complete result without marking version/correction.

### 18.1. Idempotency

- Use a stable `eventId` to deduplicate input parts.
- Use `(tenantId, orderId)` or an appropriate business key for correlation.
- Use a stable output event ID/version so downstream handles outputs idempotently.
- Define group completion/tombstone/retention policies for late arrivals.
- Separate broker and DB transactions/acks, adding an outbox if needed.

**Aggregator does not automatically guarantee exactly-once side effects.** An output sent twice to the same handler can trigger two emails or two transactions if downstream does not protect itself.

## 19. Case of Three Independent Event Sources

An order is only ready to ship once all three arrive:

- `OrderRegistered(orderId)`.
- `PaymentCaptured(orderId)`.
- `InventoryReserved(orderId)`.

~~~mermaid
flowchart LR
    A["OrderRegistered"] --> G["Aggregator by orderId"]
    B["PaymentCaptured"] --> G
    C["InventoryReserved"] --> G
    G -->|"all required types"| O["OrderReady"]
    O --> CH["orders.ready.events"]
    CH --> PUB["Broker adapter / consumer"]
~~~

In this case, you should:

1. Correlate by `orderId` or a composite key with a trusted tenant.
2. Release when all **required data types** arrive, not just when `group.size()==3`, because a duplicate Payment cannot substitute for Inventory.
3. Have the output processor construct `OrderReady` with a stable schema.
4. Pick a fixed output channel `orders.ready.events` if all completed results emit the same event type.
5. Build a separate **timeout/partial/correction** path.
6. Use a persistent `MessageGroupStore` if groups must survive restarts.
7. Apply idempotency when inputs/outputs can redeliver.

**Never choose the destination by whichever part arrived last.** The same group might receive Payment last or Inventory last; the business outcome is still `OrderReady`, not the last producer's individual result.

## 20. Troubleshooting: Group Released, So Where Is the Output?

~~~mermaid
flowchart TD
    A["No output seen"] --> B{"Did group release?"}
    B -->|No| C["Check correlation/release/missing part"]
    B -->|Yes| D{"Output processor succeeded?"}
    D -->|No| E["Check exception/error flow"]
    D -->|Yes| F{"Valid destination?"}
    F -->|No| H["Channel name/replyChannel"]
    F -->|Yes| I{"Consumer/poller present?"}
    I -->|No| J["Check lifecycle, poller"]
    I -->|Yes| K["Check executor/broker/downstream"]
~~~

### 20.1. Wrong Channel Bean Name

**Symptom:** Router returns `orders.complete` while configuration defined `orders.completed`. Test all branches, not only the default branch.

### 20.2. `QueueChannel` Without a Poller

**Symptom:** Aggregator sends into the queue, yet downstream never runs. You need a real poller or `receive()` consumer; `QueueChannel` is not `DirectChannel`.

### 20.3. `DirectChannel` Without a Subscriber

**Symptom:** message dispatch failure because no consuming endpoint is subscribed. Check bean wiring and lifecycle.

### 20.4. Gateway Times Out Despite Result in Queue

**Symptom:** result sits in a fixed channel while Gateway never receives a reply. Check output channel precedence and reply flow design.

### 20.5. No Result Because Group Is Incomplete

**Symptom:** output queue empty, group store still holds messages. Check `sequenceSize`, Filter-dropped parts, wrong correlation, timeouts, and release strategy.

### 20.6. Output Processor Creates New `Message` and Drops Metadata

**Symptom:** lost business correlation/trace or `replyChannel`. Test headers on the **aggregated output**, not only on input parts.

### 20.7. Executor/Broker Fails on Another Thread

**Symptom:** producer sees `send()==true`, yet DB has not written. Monitor error channels, consumer errors, retries, backlogs, and handler outcomes.

### 20.8. Output Appears Twice

**Symptom:** duplicate email sent after retry/redelivery. Inspect duplicate/late-arrival policies and output handler idempotency.

## 21. Testing the Entire Topology

Do not test only the output policy. Key scenarios:

| Test Case | What to Prove |
|---|---|
| One group with all parts | One properly typed output reaches expected channel |
| Incomplete parts | No success output |
| Two interleaved groups | Never mixed |
| Exact threshold 1000.00 | Routes to `highValue` |
| Below threshold 999.99 | Routes to `standard` |
| Router returns nonexistent channel | Error is observed |
| Output processor fails | Never emits bogus success output |
| One part dropped by Filter | Group waits/times out per policy |
| Conflicting headers | Never replies/routes by arbitrary metadata |
| Gateway expects reply | Output actually reaches reply path |
| Group expires | Partial/expired goes to separate branch |
| Late message | Correction/rejection per contract |
| Broker redelivery | Idempotency prevents duplicate side effects |
| Executor overloaded | Backpressure/rejection policy works |

### 21.1. Unit Testing the Routing Policy

To keep the policy independent of annotations, extract it:

~~~java
import java.math.BigDecimal;

public final class OrderOutputPolicy {

    private static final BigDecimal HIGH_VALUE =
            new BigDecimal("1000.00");

    public String choose(OrderSummary summary) {
        return summary.total().compareTo(HIGH_VALUE) >= 0
                ? "orders.highValue"
                : "orders.standard";
    }
}
~~~

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;

class OrderOutputPolicyTest {

    private final OrderOutputPolicy policy =
            new OrderOutputPolicy();

    @Test
    void handlesBoundary() {
        assertEquals("orders.highValue",
                policy.choose(new OrderSummary(
                        List.of(),
                        new BigDecimal("1000.00"))));
        assertEquals("orders.standard",
                policy.choose(new OrderSummary(
                        List.of(),
                        new BigDecimal("999.99"))));
    }
}
~~~

Unit testing the policy is fast, yet **does not verify** those channel names actually have beans and consumers. Integration tests must cover wiring.

## 22. Observing Aggregator Output

A metric/log set should clearly separate group state from dispatch:

| Metric | Meaning |
|---|---|
| `aggregation_groups_open` | Waiting groups |
| `aggregation_groups_released_total` | Groups satisfying release condition |
| `aggregation_output_created_total` | Result messages created |
| `aggregation_output_sent_total{channel}` | Outputs dispatched per channel |
| `aggregation_output_failed_total{channel,type}` | Dispatch/output processor failures |
| `aggregation_group_expired_total` | Groups timed out/expired |
| `aggregation_partial_total` | Partial results |
| `aggregation_late_arrival_total` | Parts arriving after group closed |
| `downstream_completed_total{consumer}` | Business handlers completed |

Metrics should use low-cardinality labels such as channel type, reason code, and outcome. Never put `orderId`, `eventId`, or `traceId` as arbitrary metric labels; to trace specific messages, use logs/traces with appropriate data policies.

Example log:

~~~text
flow=order-aggregation
groupKey=tenant-a/ORDER-1001
release=true
outputType=OrderSummary
destination=orders.highValue
dispatch=SUCCESS
downstreamOutcome=PENDING
traceId=trace-1001
~~~

This log line only says **the message dispatched**; it does not prove downstream committed successfully. Record the actual outcome at the handler once work finishes.

## 23. Hands-On Exercises

**Exercise 1 — Fixed channel.** Build `FixedOutputAggregationConfig`, send a three-line batch. Assert one message on `orders.aggregated`, with payload containing all three `PricedLine`s.

**Exercise 2 — DTO after aggregation.** Use `OrderSummaryAssembler` to compute total. Explain clearly why a Transformer after Aggregator does not replace `MessageGroup`/release mechanics.

**Exercise 3 — Threshold routing.** Build `DynamicOutputAggregationConfig` and Router. Test totals 999.99, 1000.00, 1000.01.

**Exercise 4 — Router in the wrong place.** Place Router before Aggregator, send multiple small lines whose total is large. Explain the difference between routing per part and routing the whole group.

**Exercise 5 — Gateway.** Build a request–reply flow with Aggregator. Verify valid `replyChannel` conditions; then set a fixed output channel and explain why the Gateway can time out.

**Exercise 6 — Header mapping.** Send parts carrying `traceId`, `businessCorrelationId`, and `replyChannel`. Verify output headers match contract, especially when the output processor builds a new `Message`.

**Exercise 7 — Queue/poller.** Switch output to `QueueChannel`, add a poller, and track output emission time vs. consumer completion time.

**Exercise 8 — Publish–Subscribe.** Send one aggregate output to Audit and Analytics; handle a failure in one subscriber without confusing send success with side-effect success.

**Exercise 9 — Partial/expired.** Configure group timeout, allow partial per business case, and route to `orders.incomplete`. Never route incomplete data to `orders.completed`.

**Exercise 10 — Two groups.** Send parts of A/B interleaved; ensure each group produces one output with the right business key and right channel.

**Exercise 11 — Late arrival.** Send a late part after group closure; design correction/dedup instead of re-emitting a complete order as brand new.

**Exercise 12 — Durable output.** Wire an outbound adapter to a broker and design idempotency/outbox as required. Simulate a crash between emitting the event and writing to the database.

### Self-Check Questions

1. At what stage does Aggregator select output?
2. How do correlation strategy and output channel answer two different questions?
3. What does `.aggregate().channel("orders.aggregated")` mean?
4. After Splitter, what payload type does Aggregator's default output usually produce?
5. When is a Transformer needed after Aggregator?
6. When is a Router needed after Aggregator?
7. Why can placing a total-amount Router before Aggregator be wrong?
8. How do `outputChannel` and `replyChannel` differ?
9. Why can a Gateway time out even when output entered a queue?
10. Why is the `replyChannel` on individual parts not necessarily the output's `replyChannel`?
11. Does `QueueChannel` invoke downstream handlers automatically?
12. When a group has not released, does the success channel receive output?
13. How must partial results be tagged and routed?
14. Why must `OrderReady` never be sent without `InventoryReserved`?
15. What consequences can late arrivals and duplicates cause?
16. Does `send()==true` prove a DB commit?
17. Which headers should be controlled when the output processor creates a new `Message`?
18. What test distinguishes a missing part from a missing consumer?

## 24. Pre-Deployment Checklist

- [ ] Clearly distinguish correlation, release, output processing, and output channel.
- [ ] Output payload has a schema and trusted business group key.
- [ ] Use a fixed channel when all results follow the same processing stage.
- [ ] Use a Router after Aggregator if destination depends on the entire group.
- [ ] Never place side effects inside `releaseStrategy`.
- [ ] Never send success output when a group is incomplete.
- [ ] Partial, expired, error, and correction outcomes have separate contracts.
- [ ] Output channel, `replyChannel`, `errorChannel`, and `discardChannel` are never conflated.
- [ ] Gateway has valid timeout, reply path, and header propagation.
- [ ] Never use the last part's headers to automatically represent the group.
- [ ] Appropriate consumer/poller exists for the output channel type.
- [ ] Backpressure, retries, queue depth, and worker errors are defined.
- [ ] Broker/outbox considered if durable delivery is needed.
- [ ] Downstream idempotency handles retries/redeliveries.
- [ ] Unit tests cover output policy and integration tests cover fixed/dynamic/Gateway flows.
- [ ] Tests cover duplicates, missing parts, timeouts, late arrivals, and multiple groups.
- [ ] Metrics track groups released, outputs sent, dispatch errors, and downstream completions.
- [ ] No sensitive data or high-cardinality IDs in metric labels.

## 25. Summary

**Choosing the output channel after aggregation** decides **where a `MessageGroup`'s result goes**. That decision happens after Aggregator identifies the group via correlation, evaluates the release condition, and builds the aggregated output. When results share one route, Java DSL `.aggregate().channel("orders.aggregated")` sets a fixed destination. When business logic needs to branch on the **combined result**, construct an explicit DTO and place a **Router** after aggregation.

If replying to a Gateway, the output message must carry a **valid `replyChannel`** and the topology must not unintentionally divert fixed output elsewhere. Incomplete groups have no success output; partial/expired/errored outcomes must never go to the complete branch without a contract. The chosen channel type also shapes sync/async execution, consumer lifecycle, durability, and retries.

By preserving correlation/headers, testing actual paths, and designing downstream idempotency, Aggregator coordinates safely with Splitter, Filter, Transformer, Router, Gateway, and error channels in the **SPRING_INTEGRATION_PATTERN** module to create extensible and diagnosable flows.

### References

- Spring Integration Reference — Aggregator: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Integration Reference — Splitter: https://docs.spring.io/spring-integration/reference/splitter.html
- Spring Integration Reference — Java DSL: https://docs.spring.io/spring-integration/reference/dsl.html
- Spring Integration Reference — Router: https://docs.spring.io/spring-integration/reference/router.html
- Spring Integration Reference — Message Channels: https://docs.spring.io/spring-integration/reference/channel/implementations.html
- Spring Integration Reference — Gateway: https://docs.spring.io/spring-integration/reference/gateway.html
- Spring Integration Reference — Message Store: https://docs.spring.io/spring-integration/reference/message-store.html
- Spring Integration API — AbstractCorrelatingMessageHandler: https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/AbstractCorrelatingMessageHandler.html
- Spring Integration API — DefaultAggregatingMessageGroupProcessor: https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/DefaultAggregatingMessageGroupProcessor.html
