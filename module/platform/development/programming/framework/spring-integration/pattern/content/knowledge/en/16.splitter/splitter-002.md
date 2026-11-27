# Splitter by List or Collection

> **Chapter:** Splitter  
> **Module:** `SPRING_INTEGRATION_PATTERN` — learn how to implement Enterprise Integration Patterns (EIP) with Spring Integration to build loosely coupled and extensible message flows. Practice Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation while testing and observing processing branches. This lesson focuses on **splitting a message containing a list/collection into child messages**, then coordinating, testing, and aggregating results when needed.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Explain why a **Splitter** separates a *multi-element payload* into multiple independently processable messages, without confusing it with a **Recipient List** that sends the same content to multiple destinations.
2. Choose an appropriate contract for inbound payloads of type `List<T>`, `Collection<T>`, or a DTO containing a list; clearly define how to handle `null`, empty lists, and invalid items.
3. Use **Spring Integration Java DSL** with `.split()` for collection payloads and `.split(OrderBatch.class, OrderBatch::lines)` when extracting a list from a business object.
4. Understand **correlation ID, sequence number, and sequence size**, and their role in Aggregator, retries, and per-item tracking.
5. Analyze how **processing order can change** after an executor/queue/broker, along with backpressure, mutable data, and very large element counts.
6. Write **unit tests and integration tests** to prove the number of split messages, each message's payload, preserved metadata, absence of duplicate sends, and behavior with empty collections or invalid data.

## 2. Scenario: One Order, Multiple Product Lines

Suppose a service receives an order with three line items:

~~~json
{
  "orderId": "ORD-701",
  "lines": [
    {"sku": "BOOK-1", "quantity": 2},
    {"sku": "PEN-5", "quantity": 4},
    {"sku": "BAG-2", "quantity": 1}
  ]
}
~~~

The system needs to check inventory for **each line** because each SKU may belong to a different warehouse or policy. If the entire order goes to a single handler, that handler has to loop over the list itself, track partial errors, and handle multiple business rules. A **Splitter endpoint** sets a clear boundary:

~~~mermaid
flowchart LR
    A["OrderBatch: 3 lines"] --> S{"Splitter"}
    S --> M1["Message: BOOK-1 × 2"]
    S --> M2["Message: PEN-5 × 4"]
    S --> M3["Message: BAG-2 × 1"]
    M1 --> C["Per-item processing"]
    M2 --> C
    M3 --> C
    C --> G["Aggregator if combined result needed"]
~~~

The inbound message is **one order message**; the Splitter output is **three child messages**, each carrying a payload representing one line. Each child message can pass through a Router by SKU, a Filter checking warehouse conditions, a Gateway calling the inventory service, or a Transformer building an external API request.

**Do not assume the three child messages are processed in parallel by default.** Concurrency depends on the output channel and downstream endpoints. Splitter describes **message splitting**, without committing to threading, persistence, or completion order.

## 3. EIP Splitter: Turning One Message into Many

In Enterprise Integration Patterns, a **Splitter** breaks a composite message into parts that can be processed individually. With a list/collection, the basic idea is:

~~~text
Input Message<List<Item>>
    payload = [itemA, itemB, itemC]
               |
               v
            Splitter
               |
               +--> Message<Item>(itemA)
               +--> Message<Item>(itemB)
               +--> Message<Item>(itemC)
~~~

With a DTO containing a list:

~~~text
Message<OrderBatch>
  payload = OrderBatch(orderId="ORD-701", lines=[A,B,C])
               |
               v
        Extract lines + Splitter
               |
               +--> Message<OrderLine>(A)
               +--> Message<OrderLine>(B)
               +--> Message<OrderLine>(C)
~~~

A Splitter can use a method/expression to produce a collection, array, or an item source conforming to the contract. Behavior with lazy sources or collections of unknown size should be verified on the Spring Integration version in use — especially if the workflow depends on sequence metadata.

### 3.1. Comparison with Related EIPs

| Pattern | Core Question | Message or Recipient Count | Example |
| --- | --- | --- | --- |
| **Splitter** | Which **parts** of a payload need separate processing? | One inbound message → multiple messages with child payloads | One order → three line items |
| **Recipient List** | Which **destinations** need to receive this message? | One message → multiple recipients, typically same business content | `OrderPlaced` → audit and analytics |
| **Content-Based Router** | Which **branch** does the current message take? | Selects output per policy | Cold-chain line → cold warehouse |
| **Aggregator** | Which group do child messages belong to and **when is it complete**? | Multiple messages → group result | Three inventory results → one order result |
| **Transformer** | How should the payload **representation** change? | Typically one type-converted output | `OrderLine` → `ReserveStockCommand` |
| **Filter** | Should this message **proceed**? | Keep or drop message | Drop line with invalid quantity |

If you only need to convert `List<PartnerLine>` into `List<WarehouseLine>` **within a single payload**, that may be a Transformer. If you actually emit **one message per item**, that is a Splitter.

### 3.2. What Is Split and What Is Preserved?

In a simple design, the **payload changes from a collection to each individual element**, while relevant headers can be forwarded or added for group processing. For example:

- `businessCorrelationId`: business identifier used by the application for tracing.
- `correlationId`: Spring Integration grouping/sequence metadata when configured and applied.
- `sequenceNumber`: item position per the Splitter sequence.
- `sequenceSize`: expected item count, when known and sequence is applied.
- `replyChannel` / `errorChannel`: supports reply/error mechanisms where appropriate.

**Do not assume every header is preserved across every Transformer, Gateway, or broker**, nor treat `MessageHeaders.id` of child messages as the business ID of the original order.

## 4. Choosing Collection Types and Ordering Semantics

At the Java level, `List`, `Set`, `Collection`, and `Iterable` can all represent multiple items, but **their ordering semantics and countability differ**.

| Data Source | Characteristics | Splitting Considerations |
| --- | --- | --- |
| `List<OrderLine>` | Index-ordered | Appropriate when line-item position must be preserved |
| `ArrayList<T>` | Mutable list | Producer may mutate during processing if not snapshotted |
| `List.copyOf(source)` | Structurally unmodifiable outer list | **Mutable elements** inside can still change |
| `LinkedHashSet<T>` | Deduplicated with insertion iteration order | Easy to accidentally drop duplicate-value line items |
| `HashSet<T>` | No stable encounter order guaranteed | Do not use sequence index to infer business order |
| `Collection<T>` | Not every implementation guarantees order | Must know the concrete contract before expecting ordering |
| `Iterable<T>` / iterator | May evaluate lazily, size unknown | Do not assume `sequenceSize` always has a useful value |
| `Stream<T>` | Single-use, potentially infinite | Check API support and bound data; do not treat casually as a finite list |
| `Map<K,V>` | Key–value structure | Explicitly define whether to split `entrySet`, `values`, or another DTO |

**Recommendation:** For standard orders with a finite number of lines where order must be preserved, use an immutable `List<OrderLine>`. If the business processes an **unordered** set, do not attach business meaning to `sequenceNumber`.

### 4.1. Emission Order Does Not Equal Completion Order

Suppose the source List is `[A,B,C]`. In a synchronous internal flow, messages are usually emitted in encounter order. However, if an executor or broker sits downstream of the Splitter, processing times can turn out as:

~~~text
Dispatch:  A -> B -> C
Complete:  B -> C -> A
~~~

Therefore, tests should clearly distinguish between **the order in which Splitter creates messages** and **the order in which downstream finishes**. An Aggregator should not require results to arrive strictly as `1,2,3` if the infrastructure allows out-of-order delivery.

### 4.2. Why `Set` Can Cause Business Data Loss

If two line items happen to have the same SKU and quantity yet represent two distinct order positions, coercing `List` into `Set` can **drop one line** based on `equals/hashCode`. Splitter only emits from the **collection provided**, with no way to know data was dropped earlier.

When value-identical lines must be processed separately, preserve a stable **lineId/lineIndex** and use a List or a model that preserves multiplicity.

## 5. Data Contract: What Does a Batch Contain?

For illustration, we define two Java records (Java 17+). `OrderLine` is a business item; `OrderBatch` represents an order containing multiple items.

~~~java
import java.util.List;
import java.util.Objects;

record OrderLine(String sku, int quantity) {
    OrderLine {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku is required");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
    }
}

record OrderBatch(String orderId, List<OrderLine> lines) {
    OrderBatch {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }
        lines = List.copyOf(
            Objects.requireNonNull(lines, "lines"));
    }
}
~~~

We **allow an empty list** in the model to intentionally discuss its semantics. That does not mean every order domain must accept 0-line orders. A sales system may reject them in validation before the Splitter; a state-sync event might treat an empty list as a valid outcome.

### 5.1. Snapshot on Ingestion

~~~java
import java.util.ArrayList;
import java.util.List;

List<OrderLine> original = new ArrayList<>();
original.add(new OrderLine("BOOK-1", 2));
original.add(new OrderLine("PEN-5", 4));

OrderBatch batch = new OrderBatch("ORD-701", original);
original.clear();

System.out.println(batch.lines().size()); // 2
~~~

`List.copyOf` prevents mutating the **outer list** after creating the batch. However, if `OrderLine` holds a `List<MutableAdjustment>` field or a `byte[]` array, the record can still share mutable elements. When distributing messages across threads, use an **entirely immutable object graph** or make intentional defensive copies.

### 5.2. Do Not Keep the Whole Batch Inside Every Item's Payload

In the default design, the child message payload is `OrderLine`. If a warehouse handler needs `orderId`, there are three common options:

1. Put business correlation in a reliable header, such as `businessOrderId`.
2. Create an `OrderLineTask(orderId, lineIndex, line)` DTO at the mapping/splitting step.
3. Store metadata in a workflow state store and look it up by business key when explicitly needed.

Do not force every handler to re-read the entire `OrderBatch` just to obtain the ID or find the item's index, as that defeats the benefit of splitting.

## 6. Spring Integration Java DSL: Splitter for a Direct List Payload

When the inbound payload itself is a `List<OrderLine>`, you can use **DefaultMessageSplitter** via `.split()`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
class ListSplitterConfiguration {

    @Bean("items.list.in")
    DirectChannel listInput() {
        return new DirectChannel();
    }

    @Bean("items.list.out")
    QueueChannel listOutput() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow splitListPayload() {
        return IntegrationFlow.from("items.list.in")
            .split()
            .channel("items.list.out")
            .get();
    }
}
~~~

The `.split()` line here relies on the collection payload type. With a valid finite List, elements are emitted as **messages with corresponding payloads**. The destination `QueueChannel` serves only as a collection point for this lesson and testing; it does **not** represent a business consumer having succeeded.

Example sending to the injected input channel:

~~~java
import java.util.List;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

List<OrderLine> lines = List.of(
    new OrderLine("BOOK-1", 2),
    new OrderLine("PEN-5", 4),
    new OrderLine("BAG-2", 1));

Message<List<OrderLine>> request = MessageBuilder.withPayload(lines)
    .setHeader("businessCorrelationId", "ORD-701")
    .build();

listInputChannel.send(request);
~~~

Expected **payload** results at `items.list.out`:

~~~text
Message<OrderLine>(sku="BOOK-1", quantity=2)
Message<OrderLine>(sku="PEN-5",  quantity=4)
Message<OrderLine>(sku="BAG-2",  quantity=1)
~~~

### 6.1. When Not to Use the Default List Splitter?

If the payload is not a List but an `OrderBatch` DTO containing `lines`, `.split()` does not know which business contract to extract. Use an **expression/method splitter** or an explicit extraction step to obtain the list. Furthermore, if you need to create a per-line task carrying `orderId` and `lineIndex`, use a **typed method splitter** instead of expecting the framework to invent business metadata.

## 7. Spring Integration Java DSL: Splitting a List Inside a DTO

A more common scenario is a message carrying `OrderBatch`. Java DSL can invoke a method returning a collection:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
class BatchSplitterConfiguration {

    @Bean("orders.batch.in")
    DirectChannel batchInput() {
        return new DirectChannel();
    }

    @Bean("orders.items.out")
    QueueChannel itemOutput() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow splitBatchLines() {
        return IntegrationFlow.from("orders.batch.in")
            .split(OrderBatch.class, OrderBatch::lines)
            .channel("orders.items.out")
            .get();
    }
}
~~~

Here, the `OrderBatch::lines` method takes the batch object and returns `List<OrderLine>`. Spring Integration uses that result to create child messages. These are two distinct actions:

1. **Extract the list from the aggregate payload** using a typed function.
2. **Split the list into individual messages** via the Splitter endpoint.

Do not confuse this with a plain Transformer:

~~~java
// Only converts payload OrderBatch -> List<OrderLine>.
// Without a subsequent Splitter, there is still only one message with a List.
.transform(OrderBatch.class, OrderBatch::lines)
~~~

If the target handler needs to know which line number in the order it is processing, add a `lineIndex` or `lineId` field **in the child DTO contract**. `sequenceNumber` (when present) describes the position during the split; it is not necessarily an invariant business index across retries, reordering, or line-set edits.

### 7.1. Designing Tasks Rich in Business Metadata

A clean approach is converting each line into an immutable task before splitting:

~~~java
import java.util.ArrayList;
import java.util.List;

record OrderLineTask(String orderId, int lineNumber, OrderLine line) {}

final class LineTaskFactory {

    List<OrderLineTask> tasks(OrderBatch batch) {
        List<OrderLineTask> result = new ArrayList<>();
        for (int i = 0; i < batch.lines().size(); i++) {
            result.add(new OrderLineTask(
                batch.orderId(), i + 1, batch.lines().get(i)));
        }
        return List.copyOf(result);
    }
}
~~~

You can use a method splitter extracting `LineTaskFactory.tasks(batch)`, returning `List<OrderLineTask>`. Then business identity travels inside the payload rather than relying entirely on sequence headers. This is a useful choice when each task is persisted to a broker, replayed independently, or handled by external consumers that do not preserve Spring Integration headers.

## 8. Correlation, Sequence Number, and Sequence Size

Splitter often pairs with **Aggregator**. To gather results accurately, the system must know which child messages originate from the same source message and **when a group has enough parts**.

~~~text
Parent: OrderBatch("ORD-701") -> split into 3 items
          |
          +-> Item 1: correlation group G, sequenceNumber=1, sequenceSize=3
          +-> Item 2: correlation group G, sequenceNumber=2, sequenceSize=3
          +-> Item 3: correlation group G, sequenceNumber=3, sequenceSize=3
~~~

This is an **illustration when sequence metadata is applied**. In Spring Integration, whether headers such as `correlationId`, `sequenceNumber`, and `sequenceSize` are attached depends on the Splitter type, `applySequence` configuration, and data source characteristics. When downstream requires a sequence-based Aggregator, **enable/verify sequence application per your running version's API** and write an integration test confirming the actual headers; do not assume based solely on diagrams.

| Metadata | Role | What to Avoid |
| --- | --- | --- |
| `correlationId` | Groups child messages from the same split session | Do not assume it equals `orderId` |
| `sequenceNumber` | Position of the child message in the sequence | Do not use as a stable business line ID |
| `sequenceSize` | Total expected parts when known upfront | Do not assume always known for lazy/infinite sources |
| `businessCorrelationId` | Application-added business trace | Does not replace duplicate detection by itself |
| `MessageHeaders.id` | Envelope ID of each individual message | Do not use as the idempotency key for a business operation |

**Example:** An order `ORD-701` may be processed twice at different times due to reprocessing. The two splits can generate **two distinct correlation groups**. Using only `orderId` to aggregate risks mixing results from the two runs; using only the framework-generated correlation group to prevent duplicate side effects risks creating duplicate shipments/reservations across replays. Both **grouping** and **idempotency** must be designed separately.

### 8.1. Item Count Must Match the Contract

With a three-item List, the group expects three child messages. If a Filter drops child #2 before the Aggregator, the group only gets 2/3 and may **never release** under a wait-for-all strategy.

In that case, decide between:

- Sending a **rejected result for item 2** to the aggregator, carrying the same correlation group.
- Or using a release strategy/timeout with a clearly defined `PARTIAL` outcome.
- Or terminating the workflow with an error/compensation instead of pretending all three items succeeded.

Never let a Filter silently drop a child message if downstream expects results for every element.

## 9. Splitting Empty Lists and Invalid Items

### 9.1. Empty Collection

~~~text
Input: OrderBatch(orderId="ORD-EMPTY", lines=[])
Splitter -> zero item messages
~~~

For a valid empty list, Splitter may emit no child messages. If downstream only has an Aggregator waiting for child messages, **no new group will exist** to release or emit a "zero items" result.

Therefore, handle it **before the Splitter** if the business requires an ACK or terminal state:

~~~mermaid
flowchart LR
    IN["OrderBatch"] --> V{"lines.isEmpty()?"}
    V -->|Yes| E["Emit EMPTY_RESULT / reject per contract"]
    V -->|No| S["Splitter"]
    S --> P["Process each item"]
    P --> A["Aggregate results"]
~~~

You can use a Router or a Filter with an appropriate `discardChannel` **and a reply-producing handler**. With a synchronous Gateway waiting for a result, **never** silently produce zero output and assume the caller will receive a completed response.

### 9.2. Null Collection

`Message<?>` does not allow a null payload under the normal messaging contract. However, an `OrderBatch` object with `lines=null`, or a splitter method returning null, is another issue. Define a **validation failure** policy before splitting instead of implicitly treating null as empty or letting an uncoded `NullPointerException` surface.

In our example, the `OrderBatch` constructor already rejects `lines=null`. If an external API allows that field, the inbound mapper must clarify whether it is valid data or a schema error.

### 9.3. Null Elements

`List.copyOf` rejects null elements; many mutable collections can hold nulls. A splitter should not create messages with null payloads and hope downstream figures it out. For untrusted inputs, validation must define a policy for null elements, wrong types, or missing fields; depending on the domain, **reject the whole batch** or emit an **ItemRejected** with an explicit index.

### 9.4. Does One Bad Item Fail the Entire Batch?

There is no universal answer. Two common policies:

1. **All-or-nothing:** if one item is invalid, reject the entire batch before splitting; suitable for operations requiring strict consistency.
2. **Partial processing:** valid items proceed, each invalid item produces a rejected result, and the Aggregator summarizes `SUCCESS/PARTIAL/FAILED`.

Choose the policy **before writing the Splitter**, because it determines the Filter, Aggregator release strategy, reply/error contract, and audit logging.

## 10. Processing Each Child Message: Router, Transformer, Handler

After the Splitter, each item can follow different branches:

~~~mermaid
flowchart LR
    S["Splitter<OrderLine>"] --> R{"Router by SKU group"}
    R -->|Books| B["Book inventory handler"]
    R -->|Stationery| O["Office inventory handler"]
    R -->|Other| X["Review / unsupported"]
    B --> A["Aggregator"]
    O --> A
    X --> A
~~~

Example chain of responsibility:

~~~text
Batch input
 → Validate whole batch
 → Split into OrderLineTask
 → Filter/Router each task
 → Transformer task → ReserveStockCommand
 → Outbound Gateway to inventory
 → Convert response to ItemResult
 → Aggregator by correlation group
 → Final OrderReservationResult
~~~

**Note:** Routing **a child** to a warehouse does not guarantee inventory was reserved. A successful `send()` on a channel only indicates delivery to that boundary per channel semantics, not that the warehouse transaction committed.

### 10.1. Why Not Call the Inventory API Inside the Splitter Function?

A splitter method like `OrderBatch::lines` should stay simple: return the elements to process. If the split method itself loops, calls the inventory API, updates the database, and then returns a list, retries can hardly separate **splitting** failures from **business execution** failures, and can cause duplicate side effects.

Keep the Splitter **pure and repeatable**; place I/O, retries, and transactions in the responsible downstream endpoints.

## 11. Aggregator: Grouping Results, Not Just Counting Three Items

If the workflow only needs to notify/stream each child to an independent consumer, an Aggregator is **not mandatory**. However, if a Gateway needs to answer "has the order reserved all required stock?", an explicit fan-in mechanism is needed.

~~~text
Order ORD-701
   |
   +-> Line 1 -> Reserved
   +-> Line 2 -> OutOfStock
   +-> Line 3 -> Reserved
   |
   v
Aggregator
   |
   v
OrderReservationResult(
  orderId="ORD-701",
  outcome="PARTIAL",
  itemResults=[Reserved, OutOfStock, Reserved])
~~~

For the Aggregator to work reliably, decide on:

| Concern | Implementation Question |
| --- | --- |
| **Correlation strategy** | Group children by a split execution ID or which business key? |
| **Release strategy** | Wait for `sequenceSize`, a known result count, or timeout? |
| **Order of results** | Must results be sorted by `lineIndex`, or is arrival order sufficient? |
| **Group timeout** | If a child is lost, emit partial, retry, or keep waiting? |
| **Group expiration** | How are groups purged/stored upon completion or expiration? |
| **Duplicate handling** | Could a redelivered result be counted twice? |
| **Persistent state** | If restarting mid-flight, is a durable `MessageStore` required? |

### 11.1. Do Not Treat `sequenceSize` as a Delivery Guarantee

`sequenceSize=3` is **metadata about expected count**, not proof that three children were delivered successfully or that three handlers completed. A child may fail, be retried, or arrive late; the release strategy and error handling must account for that.

### 11.2. Technical and Business Correlation Differ

If two orders share the same `orderId` but represent two different business attempts, aggregating solely on `orderId` can mix them. You can use a **splitExecutionId** to group children of one run while keeping `orderId` as business context. Downstream idempotency relies on a stable operation ID, such as `(commandId, lineId, operation)`.

### 11.3. What If There Is No Aggregator?

When a batch only exists to emit a `PriceChanged` event per SKU to other systems, each child can be processed independently. No Aggregator is needed if upstream is not waiting for an aggregated result. Still, clarify the parent message's ACK semantics: **finished splitting** is different from **all children finished processing**.

## 12. Synchronous, Asynchronous, and Resource Bounds

A simple 3-element List creates minimal load. However, a 100,000-element batch can turn one inbound message into 100,000 child messages, straining CPU, heap, queues, brokers, databases, tracing, and downstream rate limits.

| Channel/transport | Impact When Splitter Emits Many Children | What to Control |
| --- | --- | --- |
| `DirectChannel` + synchronous handler | Can hold the sending thread across the entire chain | Latency, propagated exceptions, request bounds |
| In-memory `QueueChannel` | Messages are enqueued | Queue capacity, consumer poll rate, memory/backpressure |
| `ExecutorChannel` | Hands work off to an executor | Bounded pool/queue, rejection policy, concurrency |
| Kafka/AMQP/JMS outbound | Publishes each child to a broker | Batch size, ack, transaction boundary, redelivery |
| Per-child HTTP outbound Gateway | One API call per line | Rate limit, timeout, retry, circuit breaker if appropriate |

**Do not assume an in-memory `QueueChannel` is durable** across restarts. If replay, auditing, or group recovery after crashes is required, design persistence/broker support to match actual requirements.

### 12.1. Large Batches: Check Before Splitting

Useful controls include:

- Cap `lines.size()` before creating child messages.
- Use contract-based chunking if downstream accepts **small sub-batches** instead of single items.
- Configure appropriately **bounded** queues/executors and overload signaling.
- Do not copy the whole batch into **every** child header; that multiplies memory by N.
- Reduce repeated queries by enriching shared data **before** the Splitter when all items need the same verified metadata.
- Monitor processing lag, queue age, throughput, and per-item error rates.

### 12.2. Streaming vs. Finite Lists

If the data source is a database cursor or a very large stream, calling `toList()` before the Splitter can cause heap spikes. Yet using a lazy Iterator/Stream changes how total child count is determined and how the Aggregator waits for completion. That is an **architectural decision**, not merely swapping a Java type.

When data is very large, consider **pagination/chunked messages**, checkpoints, independent consumers, and a batch/page-ID-based group completion policy rather than relying on an uncertain `sequenceSize`.

## 13. Per-Child Errors, Retries, and Idempotency

Suppose three line items are split properly. The handler for `PEN-5` times out calling inventory after the warehouse system might already have reserved stock. Retrying the entire `OrderBatch` message from the start would re-emit all three children, potentially reserving `BOOK-1` and `BAG-2` a second time.

~~~mermaid
flowchart TD
    A["Splitter creates 3 children"] --> B["Item handler"]
    B --> C{"Business result?"}
    C -->|Success| S["ItemResult: SUCCESS"]
    C -->|Transient error| R["Bounded per-item retry"]
    C -->|Permanent reject| F["ItemResult: REJECTED"]
    R -->|Success| S
    R -->|Exhausted / uncertain| E["Error / reconcile / manual review"]
    S --> G["Aggregator"]
    F --> G
    E --> G
~~~

In practice, branch `E` can produce an `ItemResult(UNKNOWN)` for the Aggregator or terminate the group per the error contract. Never assume every technical error yields a success response or that the Aggregator always releases.

### 13.1. Idempotency by Item and Operation

A suitable key might be:

~~~text
(commandId, lineId, "RESERVE_STOCK")
~~~

Do not use `MessageHeaders.id` as the sole key: when a message is reconstructed across a broker/retry, the message ID can change even though the business operation is identical. Do not use `sku` alone because two different orders can share the same SKU.

### 13.2. `send()` Succeeding Is Not Item Success

Distinguish at least three milestones:

1. **Splitter emitted:** child message created.
2. **Channel accepted:** target channel/queue/broker accepted the message per its semantics.
3. **Item processed:** consumer returned the business outcome and persisted required side effects.

Only the third milestone, or an equivalent business acknowledgment, can serve as the basis for marking an item complete.

### 13.3. Error Channel and Rejected Items

In synchronous flows, exceptions can propagate to the caller; with pollers or executors, exceptions can route to a configured error channel. An **ItemRejected due to insufficient stock** is a different business outcome from a **TimeoutException calling the warehouse**. Design distinct status codes, retries, dead-letter handling, and intervention rules for each.

## 14. Unit Testing: Data and Task Identity

A Splitter lesson should first test **whether the batch is constructed with the right list**. Unit tests help catch bugs from mutable models, invalid quantities, and line indices.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class OrderBatchTest {

    @Test
    void batchKeepsStableListSnapshot() {
        List<OrderLine> source = new ArrayList<>();
        source.add(new OrderLine("BOOK-1", 2));

        OrderBatch batch = new OrderBatch("ORD-701", source);
        source.add(new OrderLine("PEN-5", 4));

        assertEquals(1, batch.lines().size());
        assertEquals("BOOK-1", batch.lines().get(0).sku());
    }

    @Test
    void lineTaskFactoryKeepsBusinessLineNumbers() {
        OrderBatch batch = new OrderBatch("ORD-702", List.of(
            new OrderLine("BOOK-1", 2),
            new OrderLine("PEN-5", 4)));

        List<OrderLineTask> tasks =
            new LineTaskFactory().tasks(batch);

        assertEquals(2, tasks.size());
        assertEquals(1, tasks.get(0).lineNumber());
        assertEquals(2, tasks.get(1).lineNumber());
        assertEquals("ORD-702", tasks.get(0).orderId());
    }

    @Test
    void rejectsNonPositiveQuantity() {
        assertThrows(IllegalArgumentException.class,
            () -> new OrderLine("PEN-5", 0));
    }

    @Test
    void allowsEmptyListOnlyAtTheModelLevel() {
        OrderBatch batch = new OrderBatch("ORD-EMPTY", List.of());
        assertTrue(batch.lines().isEmpty());

        // Ingress business validation can reject empty batches
        // depending on the contract; this record does not decide that itself.
    }
}
~~~

These are model/mapper tests; they **do not prove** Spring Integration emits the right number of child messages. The next step is an integration test with `IntegrationFlow` and real channels.

## 15. Integration Testing: Counting and Inspecting Each Child Message

With `BatchSplitterConfiguration` from section 7, you can use Spring Test to send `OrderBatch` to `orders.batch.in` and read each `OrderLine` from `orders.items.out`.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(BatchSplitterConfiguration.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class BatchSplitterIntegrationTest {

    @Autowired @Qualifier("orders.batch.in")
    MessageChannel input;

    @Autowired @Qualifier("orders.items.out")
    PollableChannel output;

    @Test
    void splitsThreeLinesAndRetainsBusinessCorrelation() {
        OrderBatch batch = new OrderBatch("ORD-701", List.of(
            new OrderLine("BOOK-1", 2),
            new OrderLine("PEN-5", 4),
            new OrderLine("BAG-2", 1)));

        Message<OrderBatch> source = MessageBuilder
            .withPayload(batch)
            .setHeader("businessCorrelationId", "ORD-701")
            .build();

        assertTrue(input.send(source));

        Message<?> first = output.receive(1000);
        Message<?> second = output.receive(1000);
        Message<?> third = output.receive(1000);

        assertNotNull(first);
        assertNotNull(second);
        assertNotNull(third);

        // The demo topology is synchronous with an output QueueChannel
        // to observe each split item sequentially.
        assertEquals(new OrderLine("BOOK-1", 2), first.getPayload());
        assertEquals(new OrderLine("PEN-5", 4), second.getPayload());
        assertEquals(new OrderLine("BAG-2", 1), third.getPayload());

        for (Message<?> child : List.of(first, second, third)) {
            assertEquals("ORD-701",
                child.getHeaders().get("businessCorrelationId"));
        }

        assertNull(output.receive(0), "No fourth child");
    }

    @Test
    void emptyCollectionProducesNoChildMessage() {
        OrderBatch empty = new OrderBatch("ORD-EMPTY", List.of());
        assertTrue(input.send(MessageBuilder.withPayload(empty).build()));

        assertNull(output.receive(0),
            "Empty batch does not automatically create an ItemResult");
    }
}
~~~

**Test scope:** verifies the Splitter, output channel mapping, and per-item payloads **within a single JVM**. It does not test real inventory processing, does not prove the Aggregator released, and does not guarantee the same completion order if switched to asynchronous processing later.

### 15.1. Testing a Direct List Payload

With the `ListSplitterConfiguration` flow from section 6, a similar test can send `List.of(A,B)` to `items.list.in` and assert exactly two `OrderLine` messages on `items.list.out`, with no third message. To avoid code duplication, write a helper that reads N messages and compares payloads against an expected list.

### 15.2. Testing Sequence Metadata Requires Actual Configuration

If the business requires a sequence-based Aggregator, add an integration test with **`applySequence` explicitly configured on the Splitter** per the API of your running Spring Integration version. The test must verify:

- All children share the same correlation group.
- `sequenceNumber` is numbered 1..N matching the source List.
- `sequenceSize` equals N when the list is finite and sequence applies.
- The business correlation header remains intact.
- Separate groups from two batches are not mixed.

**Do not** write tests asserting this metadata exists for every `Iterator/Stream` source or every configuration option; that behavior must be verified on the actual topology.

## 16. Practical Test Matrix

| Group | Input | Expectation |
| --- | --- | --- |
| Single item | 1-element List | Emits exactly 1 child |
| Multiple items | 3-element List | Emits exactly 3 children with matching payloads |
| Empty list | `[]` | Emits no children; upstream has an EMPTY response path if contract requires |
| Null list | DTO with `lines=null` | Explicit rejection/validation before Splitter |
| Null item | List containing null | Does not create null payloads; handled per policy |
| Rule-violating item | Quantity 0 | Rejects entire batch or produces designed `ItemRejected` |
| Duplicate-value lines | Two identical items with different line IDs | Not mistakenly deduplicated by a Set |
| Mutable list | Producer mutates list after publish | Snapshot/immutability preserves data |
| HashSet | Unordered data | Do not assert business ordering |
| Sequence | N items with appropriate applySequence | Accurate correlation/number/size |
| Two concurrent batches | ORD-701 and ORD-702 | Correlation groups stay isolated |
| Child via Router | SKU items in group A/B | Correct branch, no misrouting |
| One child dropped by Filter | 2 accepted, 1 rejected | Aggregator reaches complete/timeout outcome per contract |
| Handler exception | One child times out | Per-item retry/error, no false success |
| Redelivery | Same command redelivered | No duplicate side effects at consumer |
| Queue backlog | Many children into bounded queue | Proper backpressure and monitoring |
| Out-of-order consumers | Child 3 finishes before child 1 | Aggregator does not confuse result ordering |
| Synchronous Gateway | Batch needing final response | Does not time out due to empty/missing group |
| Restart | In-flight group | Persistence/recovery decision matches requirements |

### 16.1. Asserting Unchosen Branches

When a Splitter feeds a Router by SKU, a test asserting only that `books.out` received the book item is insufficient: the item might also have been misrouted to `office.out`. If the domain requires **a single owner per child**, assert:

~~~text
Input Item BOOK-1
expected:
    books.out   = 1
    office.out  = 0
    review.out  = 0
~~~

Unlike Recipient List, where the same event is **intentionally sent to multiple recipients**, Splitter + Content-Based Router typically requires each item to go to **one business processing branch**.

## 17. Observing Child Counts and Processing Journeys

After a Splitter, the `message count` metric can rise sharply. If one input contains 10 lines, the output can produce 10 children. Never interpret `outboundMessageCount=10` as 10 new orders.

| Measurement Point | Suggested Signal | Question |
| --- | --- | --- |
| Ingress | Batch count, average item count | How many orders and how many lines? |
| Splitter | Child count/batch, split latency, empty batches | Was each batch split into the right number of parts? |
| Child Router | Channel/lane chosen, item outcomes | Which warehouse did each SKU reach? |
| Queue/executor | Queue depth, wait age, rejected tasks | Is fan-out causing a bottleneck? |
| Item handler | Success/error, retry attempts, duration | Which items are still incomplete? |
| Aggregator | Open groups, age, incomplete/expired groups | Are any batches waiting on missing children? |
| Final response | FULL/PARTIAL/FAILED | Is the order complete in business terms? |

**Avoid high cardinality:** `orderId`, `lineId`, and `correlationId` belong in access-controlled logs/traces; do not use them as routine metric tags. Tags like `endpoint`, `outcome`, `errorClass`, and `warehouseRegion` keep cardinality manageable.

### 17.1. Tracing When One Span Splits into Multiple Branches

A batch trace can contain multiple spans processing individual items. Trace context can be propagated through message headers at configured boundaries; across brokers/HTTP, verify propagation explicitly. Do not assume having an Aggregator `correlationId` means distributed tracing works end-to-end.

### 17.2. Auditing Per-Item Outcomes

For workflows with side effects, record trails by **operation ID + line ID + attempt/outcome**, distinguishing `DISPATCHED` from `SUCCEEDED`. This enables reconciliation when a child succeeds at the warehouse but the response is lost to a timeout.

## 18. Common Anti-Patterns

| Anti-pattern | Consequence | Improvement |
| --- | --- | --- |
| Confusing Splitter with Recipient List | Each target wrongly receives whole batch or duplicate commands | Pick the right EIP for payload vs. recipients |
| Using Transformer only to convert `OrderBatch` to `List<OrderLine>` | Still a single message carrying a List | Use Splitter when individual child messages are needed |
| Converting List to Set to "deduplicate" | May drop valid duplicate line items | Keep List, use business line ID and explicit dedup policy |
| Using `HashSet` while expecting stable order | Sequence does not reflect original order | Use List/ordered collection per contract |
| Putting the whole batch in every child's header | Multiplies memory/serialization cost by N | Send minimal metadata or a business task DTO |
| Not handling empty collections | Gateway/Aggregator waits for a response that never arrives | Add EMPTY branch/validation before splitting |
| Filter silently drops a child | Aggregator hangs or times out ambiguously | Emit `ItemRejected` or use release/expiry policy |
| Using `orderId` alone to aggregate all replays | Results from two runs mix together | Separate split execution ID and business context |
| Using `MessageHeaders.id` as idempotency key | Redelivery generates new ID, duplicating side effects | Use stable command/line/operation key |
| Retrying whole batch from start when 1 item times out | Resends already-succeeded items | Per-child retry, idempotent handler |
| Performing network I/O inside Splitter | Hard to test, hard to isolate errors, retries mix with side effects | Keep Splitter pure; separate Gateways/handlers |
| Assuming `QueueChannel` is always durable across restarts | Data loss when application stops | Use broker/MessageStore matching durability needs |
| Unbounded splitting of 100,000 items | Heap/queue/consumer overload | Quotas, chunking, bounded executors, monitoring |
| Tests only count messages without checking payloads | Line mis-mapping bugs slip through | Assert payloads, metadata, counts, and negative paths |

## 19. Pre-Deployment Checklist

- [ ] Clarify whether the input is a direct `List` or a DTO wrapping a collection.
- [ ] Explicitly document contracts for empty collections, null collections, null items, and invalid items.
- [ ] Know whether the collection is ordered; do not use `HashSet` when order matters.
- [ ] Avoid accidentally dropping valid duplicates by converting a List to a Set.
- [ ] Snapshot or design items/DTOs as immutable before asynchronous splitting.
- [ ] Splitter returns the required collection without network I/O or side effects.
- [ ] Every child carries a stable business key, correlation, and tracing per contract.
- [ ] When using an Aggregator, `applySequence` / correlation / release strategy are verified in practice.
- [ ] When using a Filter, rejected items still produce an outcome or the group has a timeout.
- [ ] Distinguish child dispatch, channel accepted, and business completion.
- [ ] Provide per-item retry, idempotency keys, and handling for uncertain outcomes.
- [ ] Configure bounded queues/executors, item quotas, backpressure, and monitoring.
- [ ] Include unit tests for DTOs/task factories and real integration tests across message channels.
- [ ] Include tests for out-of-order, duplicates, empty batches, and group expiry when using fan-in.
- [ ] Avoid logging full sensitive payloads/headers on every child.

## 20. Hands-On Exercise

An e-commerce marketplace receives `ImportProductBatch` containing `batchId`, `tenantId`, and `List<ProductRow>`. Each row has `sku`, `priceMinor`, `currency`, and `warehouseCode`. Data may arrive from a CSV upload parsed into a List or from a JSON API.

**Requirements:**

1. Create two records, `ProductRow` and `ImportProductBatch`; use an immutable list, validate line counts, and define whether an empty batch is valid.
2. Write Spring Integration Java DSL splitting `batch.rows()` with a Splitter; each child preserves `batchId`/`tenantId` from a **verified** source.
3. Create `ProductImportTask(batchId, rowNumber, row)` to keep business row identity independent of sequence headers.
4. After the Splitter, use a Router by `warehouseCode` and a Filter checking currency/price; ensure rejected items still yield a `RowRejected` result.
5. Design an Aggregator returning `ImportResult(total, imported, rejected)`; describe correlation/release/timeout and how children can complete out of order.
6. Write an integration test with three rows: one valid for warehouse A, one valid for warehouse B, and one rejected. Assert child count, receiving branches, final result, and no duplicate sends.
7. When child messages traverse Kafka or another queue, which idempotency key would you choose so a row is imported business-wise exactly once?
8. For a 200,000-row batch, specify quotas, chunking, backpressure, progress tracking, and a recovery plan on application restart.
9. If a row contains PII or tokens, design how to **avoid** copying unnecessary fields to every downstream consumer.

**Hint:** `Gateway/Adapter → Validate batch → Splitter → (Per-row Filter/Router) → Transformer → Handler → Aggregator`. When an aggregated result is not needed, an Aggregator is not strictly required; however, you must define when an upload is marked received, processing, and completed.

## 21. Summary

**Splitting by list or collection** is the EIP pattern that turns one message carrying multiple elements into **independently processable child messages**. With Spring Integration, you can use `.split()` when the payload is a direct List or a typed splitter to extract a list from a business DTO. Item counts, ordering semantics, and data immutability must be clearly decided before scaling fan-out.

For a resilient flow, distinguish **Split** from **Recipient List**, separate **business identity** from sequence headers, define policies for **empty/null/invalid items**, and when using an Aggregator specify **correlation, release, timeout, and duplicate/out-of-order** handling. Combine Router, Filter, Transformer, Gateway, retries, error channels, idempotency, backpressure, and child-message testing so every item takes **the right branch, the exact number of times, and remains traceable back to the original batch**.

**References:** Gregor Hohpe & Bobby Woolf, *Enterprise Integration Patterns* (Splitter, Aggregator, Correlation Identifier, Message Sequence, Pipes and Filters); Spring Integration documentation on Splitter, Java DSL, Message Channels, Aggregator, Error Handling, and Testing; Java SE documentation on `List`, `Collection`, and immutable records.
