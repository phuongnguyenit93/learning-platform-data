# Propagating Correlation ID Across Multiple Endpoints

## 1. The Problem: An Order Traverses Many Endpoints, Yet Results Must Return to the Right Group

A system receives `OrderSubmitted` and goes through multiple steps:

1. A Gateway or HTTP inbound adapter receives the message.
2. A Filter validates the input data.
3. A Router branches by order type.
4. A Transformer normalizes the payload into `OrderWork`.
5. A Splitter creates multiple `LineWork` items for parallel processing.
6. Workers invoke Inventory/Pricing and return `LineResult`.
7. An Aggregator gathers the results for **exactly one order processing run**.
8. A Gateway or outbound adapter returns/publishes the final result.

~~~mermaid
flowchart LR
    IN["OrderSubmitted"] --> GW["Gateway / inbound"]
    GW --> V["Filter"]
    V --> R["Router"]
    R --> T["Transformer"]
    T --> S["Splitter"]
    S --> W["Workers"]
    W --> A["Aggregator"]
    A --> OUT["OrderSummary / outbound"]
~~~

For example, two orders are submitted together:

~~~text
Tenant A / Order O-101 / Revision 3 / Event EV-1
Tenant A / Order O-102 / Revision 1 / Event EV-2

Child messages of the two orders may arrive interleaved:
  O-101/L2, O-102/L1, O-101/L1, O-102/L2, ...
~~~

If an endpoint drops the correlation information, or a worker assigns a fresh UUID to each reply, the Aggregator will not know which results belong to the **same group**. If the key is too coarse, like `customerId`, it can **mix two orders together**. If the key is each child message's `MessageHeaders.ID`, every message has a different ID and the group fragments.

**Propagating correlation ID across multiple endpoints** means maintaining an identity with clear semantics, consistent format, and uniform scope—from ingress through branches, derived messages, asynchronous boundaries, replies, and aggregation. This lesson is not only about copying a header: **Content-based correlation** also requires being able to **derive or verify the group key from the business content itself**, especially when headers are altered or stripped by transport layers.

This lesson belongs to the **Content-based correlation** chapter of the **SPRING_INTEGRATION_PATTERN** module, supporting the learning path on implementing Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows. The examples combine **Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation**, along with testing and observability.

**Learning outcomes:** properly identify group identity; distinguish ID types; preserve correlation across endpoints; design payload/header contracts for brokers; write a custom correlation strategy for Aggregator; and test concurrency, retries, duplicates, and error paths.

## 2. Correlation ID Is Not Synonymous with Spring Message ID

A message carries multiple kinds of identifiers, each serving a distinct purpose:

| Identifier | Meaning | Should It Be the Business Group Key Across Endpoints? |
|---|---|---|
| `MessageHeaders.ID` | ID assigned by Spring Messaging to a **message object** | No: new messages/replays can change this ID |
| `MessageHeaders.TIMESTAMP` | Message creation timestamp set by the framework | No: does not identify the same logical work |
| `correlationId` | Correlation header used by flows/endpoints, especially Splitter/Aggregator | Usable when semantics and propagation are controlled |
| `sequenceNumber` | Position of a message within a sequence | No: many groups all have member #1 |
| `sequenceSize` | Expected member count, when known | No: size is not identity |
| `eventId` | Event ID assigned by the producer | May be part of identity, though one event can spawn multiple operations |
| `orderId` | Business order identifier | Insufficient when multiple revisions/operations exist |
| `businessCorrelationId` | ID of the **logical processing group** defined by the application | Suitable when stable and clearly scoped |
| `traceId`/`spanId` | Distributed tracing for observability | No: a trace is not a business group |
| `replyChannel`/`errorChannel` | Channels for replies and errors in messaging | No: these are not business IDs |

In Spring Integration, many components understand standard headers such as `IntegrationMessageHeaderAccessor.CORRELATION_ID`, `SEQUENCE_NUMBER`, and `SEQUENCE_SIZE`. However, an application may also need a separate header like `businessCorrelationId` so it **does not overwrite Splitter sequence/correlation metadata**.

**Rule:** never use an ID whose lifecycle is shorter than the logical work as a long-lived group key. A UUID is stable only if **issued once and preserved**, not because UUID syntax inherently guarantees correlation.

## 3. What Is Content-Based Correlation?

**Content-based correlation** determines relationships between messages based on **business fields in the payload**, optionally combined with trusted metadata, instead of assuming a technical header always survives intact.

Example of two messages:

~~~json
{
  "tenantId": "tenant-a",
  "orderId": "O-101",
  "revision": 3,
  "eventId": "EV-1",
  "lineId": "L-1"
}
~~~

~~~json
{
  "tenantId": "tenant-a",
  "orderId": "O-101",
  "revision": 3,
  "eventId": "EV-1",
  "lineId": "L-2"
}
~~~

The two payloads differ in `lineId`, yet belong to the same **logical processing group** if the business rule defines the group by `tenantId + orderId + revision + operation`.

\[
\operatorname{groupKey}(m) =
\operatorname{canonicalize}(
  m.\text{tenantId},\,
  m.\text{orderId},\,
  m.\text{revision},\,
  \text{operation}
)
\]

Not every piece of content is suitable as a key:

- `customerId` can repeat across many orders.
- `status` changes at each endpoint.
- `totalAmount` changes during calculation.
- `lineId` identifies a **member**, not the whole group.
- Current processing timestamp changes across retries.

A good key must rely on **stable fields defined in the contract**, not on attributes mutated by Transformers or workers.

## 4. Two Invariants to Preserve When Propagating Correlation

A correct system must satisfy both:

**Invariant A — same logical work must produce the same key:**

\[
\operatorname{sameWork}(m_1,m_2)
\Rightarrow
\operatorname{key}(m_1)=\operatorname{key}(m_2)
\]

**Invariant B — different logical work must never share a key:**

\[
\neg\operatorname{sameWork}(m_1,m_2)
\Rightarrow
\operatorname{key}(m_1)\ne\operatorname{key}(m_2)
\]

| Failure | Symptom | Consequence |
|---|---|---|
| Key changes between endpoints | Input uses `EV-1`, worker assigns a new UUID | Aggregator creates multiple incomplete groups |
| Key too coarse | Uses only `orderId` | Two revisions/tenants/operations mix results |
| Key lost across transport | Header stripped by a mapper | Reply cannot find the original group |
| Key type mutation | String `"00123"` turned into integer `123` | Group changes or collides |
| Key derived from mutable field | Uses `PENDING`/`DONE` status | Same work splits into multiple groups |
| Key from untrusted client | Client sets tenant/group header | Data mixing or information leakage |

**The presence of a header does not mean its value is valid.** You must check semantics, origin, and alignment with the payload at every trust boundary.

## 5. Choosing Identity by Business Scope

Suppose the same `orderId=O-101` has multiple processing runs:

~~~text
tenant-a / O-101 / revision=3 / PRICE
tenant-a / O-101 / revision=4 / PRICE
tenant-a / O-101 / revision=3 / INVENTORY
tenant-b / O-101 / revision=3 / PRICE
~~~

If each operation needs its own Aggregator run, these four cases **must not be merged together**. A key contract might be:

~~~text
group = tenantId | orderId | revision | operation
~~~

Or a coordinator issues a unique `processingGroupId` for the logical operation and stores a mapping to tenant/order/revision. Then a key:

~~~text
group = tenantId | processingGroupId
~~~

can suffice if the **`processingGroupId` allocation rule** truly guarantees uniqueness within the tenant and across retries.

There is no one-size-fits-all default. Explicitly write down “**what a group is**” before choosing headers:

| Use Case | Logical Group | Member Identity |
|---|---|---|
| Summing order lines | One order revision/processing run | `lineId` |
| Joining three Scatter-Gather results | One quote evaluation | `branchType` |
| Aggregating payments | One payment batch/window | `transactionId` |
| Waiting for file fragments | One upload/session/version | `partNumber` |
| Reconciling transactions | One reconciliation cycle | `recordId` |

**Group ID** and **member ID** must stay separate. Messages in one group share the same group ID, yet must carry distinct member IDs if the release strategy needs to count distinct members.

## 6. Illustrative Domain Model in Java 17+

This lesson uses these records:

~~~java
enum WorkOperation {
    PRICE, INVENTORY
}

record OrderLine(
    String lineId,
    String sku,
    long unitPriceCents,
    int quantity
) {}

record OrderEvent(
    String tenantId,
    String orderId,
    int revision,
    String eventId,
    WorkOperation operation,
    List<OrderLine> lines
) {}

record LineWork(
    String tenantId,
    String orderId,
    int revision,
    String eventId,
    WorkOperation operation,
    String lineId,
    String sku,
    long unitPriceCents,
    int quantity,
    int expectedLines
) {}

record LineResult(
    String tenantId,
    String orderId,
    int revision,
    String eventId,
    WorkOperation operation,
    String lineId,
    int expectedLines,
    long amountCents,
    boolean success,
    String reasonCode
) {}
~~~

This is an **illustrative model**, not built-in Spring Integration DTOs. Place classes in appropriate packages or files in a real implementation; imports are omitted for brevity.

Design highlights:

- The original event, each child work item, and each reply result **all retain the fields needed to compute the group key**.
- `lineId` differs per child for deduplication.
- `expectedLines` comes from the upstream manifest, never altered independently by workers.
- `eventId` is preserved for tracing and idempotency, though it is **not necessarily** the group key if one event triggers multiple operations.
- `operation` is part of the group identity when PRICE and INVENTORY can produce results concurrently.

Because the key can be computed directly from the payload, a reply returning from a broker can still be grouped even if the framework's `correlationId` header is gone.

## 7. Building a Canonical Key Without Ambiguous String Concatenation

Concatenating IDs directly can collide:

~~~text
tenant="ab", order="c" → "abc"
tenant="a",  order="bc" → "abc"
~~~

A straightforward approach is validating IDs against a character allowlist and using a delimiter disallowed in the IDs:

~~~java
final class BusinessGroupKey {

    static String of(
            String tenantId,
            String orderId,
            int revision,
            WorkOperation operation) {
        if (tenantId == null
                || !tenantId.matches("[a-z0-9-]{1,48}")) {
            throw new IllegalArgumentException("INVALID_TENANT");
        }
        if (orderId == null
                || !orderId.matches("[A-Za-z0-9-]{1,80}")) {
            throw new IllegalArgumentException("INVALID_ORDER");
        }
        if (revision < 1 || operation == null) {
            throw new IllegalArgumentException("INVALID_SCOPE");
        }
        return "t:" + tenantId
            + "|o:" + orderId
            + "|v:" + revision
            + "|op:" + operation.name();
    }

    static String from(OrderEvent e) {
        return of(
            e.tenantId(), e.orderId(),
            e.revision(), e.operation());
    }

    static String from(LineResult r) {
        return of(
            r.tenantId(), r.orderId(),
            r.revision(), r.operation());
    }
}
~~~

Examples:

~~~text
t:tenant-a|o:O-101|v:3|op:PRICE
t:tenant-a|o:O-101|v:4|op:PRICE
t:tenant-b|o:O-101|v:3|op:PRICE
~~~

**Note:** this is a readable illustrative format. If business IDs permit delimiters, Unicode, or escape sequences, you need **explicit field lengths/escaping or a canonical serializer**, not plain concatenation. Do not arbitrarily lowercase fields when the contract treats IDs as case-sensitive.

In a distributed flow, all instances must use the same key format/version. Changing the algorithm while pending groups exist is an **identity migration**, not an ordinary refactor.

## 8. Attaching Business Correlation Right at Ingress

Right at the adapter/gateway, create or verify the business key after authenticating the tenant and validating the payload:

~~~java
OrderEvent event = new OrderEvent(
    "tenant-a",
    "O-101",
    3,
    "EV-101",
    WorkOperation.PRICE,
    orderLines);

Message<OrderEvent> original = MessageBuilder
    .withPayload(event)
    .setHeader(
        "businessCorrelationId",
        BusinessGroupKey.from(event))
    .setHeader("businessEventId", event.eventId())
    .build();
~~~

One message can carry simultaneously:

~~~text
payload.orderId                 = O-101
payload.revision                = 3
headers.businessCorrelationId   = t:tenant-a|o:O-101|v:3|op:PRICE
headers.businessEventId         = EV-101
headers.id                      = <Spring-generated message ID>
~~~

**A dedicated header** lets endpoints inspect and route quickly; **complete identity in the payload** lets you recover/verify correlation across transports or when a Transformer alters the message. Avoid two conflicting sources of truth: before trusting an external header, **recompute the group key from verified fields**.

If an inbound producer is allowed to specify `tenantId`, the adapter must derive the real tenant from credentials/principal or verify access permissions; never trust a self-declared header for authorization or cross-tenant grouping.

## 9. Spring Integration Java DSL: Attaching the Header via Header Enricher

Inside a flow, you can stamp the key from the payload using `enrichHeaders`:

~~~java
@Configuration
@EnableIntegration
class CorrelationIngressFlow {

    @Bean
    IntegrationFlow validateAndStampCorrelation() {
        return IntegrationFlow.from("orders.in")
            .filter(OrderEvent.class, event ->
                    event != null
                        && event.lines() != null
                        && !event.lines().isEmpty()
                        && event.operation() != null,
                spec -> spec.throwExceptionOnRejection(true))
            .enrichHeaders(h -> h.headerFunction(
                "businessCorrelationId",
                message -> BusinessGroupKey.from(
                    (OrderEvent) message.getPayload())))
            .channel("orders.correlated")
            .get();
    }
}
~~~

This snippet illustrates Java DSL with imports omitted. You should add checks for `tenantId`, `orderId`, revision, line IDs, and domain authorization. The contract should distinguish **missing-field inputs** from **forged inputs**; a Filter only stops the flow from proceeding and does not by itself prove every identity is trustworthy.

**Important regarding overwrite:** if `businessCorrelationId` already exists on an inbound message, the policy should be **recompute and compare/reject on mismatch** or **overwrite from an authenticated source**, rather than silently keeping a client-supplied value. Header Enricher's default overwrite semantics when a header already exists depend on configuration; test against the Spring Integration version in use.

**Do not** mechanically call `headerFunction("correlationId", ...)` in flows where a Splitter/Aggregator relies on the standard correlation header. An endpoint may need its own `correlationId` for its sequence; keep the business key separate.

## 10. Passing Through a Filter: Dropped Messages Do Not Produce Replies Automatically

A Filter can be the first place where correlation breaks **business-wise**, even though headers are unchanged:

~~~text
OrderEvent O-101
  → Filter.validate
  → ACCEPT: message proceeds, businessCorrelationId unchanged
  → REJECT: no LineResult unless an error outcome is designed
~~~

If a Filter rejects the entire order before the Splitter, you can emit an `OrderRejected` carrying `businessCorrelationId` and a reason. If a Filter drops **a child message** after the Splitter, the Aggregator can stall waiting for a missing member.

Two policies:

1. **Fail-fast before splitting:** reject the entire request and never open a pending group.
2. **Per-member outcome:** turn the error into a `LineResult(success=false, reasonCode=...)` carrying the **same group key and member ID**, so the Aggregator knows that member has reached a conclusion.

Never decrement `sequenceSize` or `expectedLines` just because a child was discarded by a Filter. Doing so causes a false release: the group is missing a line yet gets reported as complete.

When a rejection happens on a synchronous path, an exception can propagate back to the Gateway. When crossing an ExecutorChannel/broker, the error must be handled at the right **async error boundary** with full correlation context.

## 11. Passing Through a Router: Branching Without Changing Identity

A Content Based Router chooses a destination channel based on payload or headers:

~~~text
operation=PRICE     → price.requests
operation=INVENTORY → inventory.requests
~~~

**Routing key** and **correlation key** have distinct jobs:

- Router chooses **who handles** a message.
- Correlation identifies **which processing run/group** the message belongs to.

If an `OrderEvent` is routed to Pricing, it still belongs to the same logical group as before the Router. Just because the channel is `price.requests` does not mean a new correlation ID should be created.

A common mistake is writing:

~~~text
correlationId = currentChannelName
~~~

Then every order sent through Pricing lands in the same group `price.requests`. That is a **route label**, not a business identity.

If a Router fans out into multiple branches in a scatter-style flow, each branch may need its own `branchId` while still linking to the **parent requestId/businessCorrelationId**. Correlation for a **gather group** differs from correlation for a **line-level Splitter**; maintain an explicit manifest of expected branches.

## 12. Passing Through a Transformer: Payload Changes, Group Identity Must Not Disappear

A Transformer can convert:

~~~text
OrderEvent → OrderWork → LineWork → LineResult
~~~

Each DTO is a different type. If correlation lived only in the old payload and the Transformer omits the identity fields, downstream loses content-based correlation.

Example of a Transformer receiving `LineWork` and returning `LineResult`:

~~~java
@MessageEndpoint
class PriceCalculator {

    @Transformer(
        inputChannel = "price.requests",
        outputChannel = "price.results")
    public LineResult price(LineWork work) {
        long amount = Math.multiplyExact(
            work.unitPriceCents(),
            work.quantity());

        return new LineResult(
            work.tenantId(),
            work.orderId(),
            work.revision(),
            work.eventId(),
            work.operation(),
            work.lineId(),
            work.expectedLines(),
            amount,
            true,
            null);
    }
}
~~~

**Key remains unchanged:** before and after the Transformer, the exact same `BusinessGroupKey` can be computed from the payload, even though computed fields like `amountCents` change.

Spring Integration generally propagates certain request headers when an endpoint builds a reply from a payload, but **never assume all headers are always preserved** across custom MessageBuilders, adapters, reply services, or wire mappers. Test end-to-end and keep essential identity in the **payload contract** whenever it must cross system boundaries.

## 13. Transformer Building a New Message: Copy Selectively

A custom Transformer might construct an entirely new `Message<?>`. Calling only:

~~~java
MessageBuilder.withPayload(converted).build();
~~~

does **not explicitly copy** old business headers at the application level. Some framework components may apply header propagation when sending replies, but do not stake correctness on that assumption, especially when output leaves Spring Integration.

An example that actively sets headers from the target payload:

~~~java
Message<LineResult> buildResultMessage(LineResult result) {
    String key = BusinessGroupKey.from(result);
    return MessageBuilder.withPayload(result)
        .setHeader("businessCorrelationId", key)
        .setHeader("businessEventId", result.eventId())
        .build();
}
~~~

This example **does not copy every header**, because headers like `replyChannel`, `errorChannel`, authentication, or cookies carry their own semantics and trust requirements. Within the JVM, you can use `MessageBuilder` helpers to copy **allowlisted** headers, provided you define an overwrite policy and trust boundary.

In particular, never overwrite `IntegrationMessageHeaderAccessor.CORRELATION_ID` if downstream endpoints rely on it to reassemble Splitter sequences. Keeping `businessCorrelationId` separate keeps responsibilities clear.

## 14. Splitter: One Original Splits into Many Children Within the Same Business Group

A Splitter converts an `OrderEvent` into `LineWork` items:

~~~java
@MessageEndpoint
class OrderLineSplitter {

    @Splitter(
        inputChannel = "orders.correlated",
        outputChannel = "orders.lines")
    public List<LineWork> split(OrderEvent event) {
        if (event.lines() == null || event.lines().isEmpty()) {
            throw new IllegalArgumentException("EMPTY_LINES");
        }

        int expected = event.lines().size();
        return event.lines().stream()
            .map(line -> new LineWork(
                event.tenantId(),
                event.orderId(),
                event.revision(),
                event.eventId(),
                event.operation(),
                line.lineId(),
                line.sku(),
                line.unitPriceCents(),
                line.quantity(),
                expected))
            .toList();
    }
}
~~~

Two layers of metadata can coexist:

~~~text
Child message L1:
  payload.tenantId/orderId/revision/operation → business group identity
  headers.businessCorrelationId              → custom application key
  headers.correlationId                       → framework sequence group
  headers.sequenceNumber                      → 1
  headers.sequenceSize                        → 3

Child message L2:
  same business group identity
  sequenceNumber=2, sequenceSize=3
~~~

Spring Integration's Splitter can attach correlation/sequence headers (for instance from the original message) when configured appropriately. It is **not guaranteed** that every `Iterator` or `Stream` has a known `sequenceSize`, and sequence headers must never be assumed to be durable business IDs across retries/replays.

**Keep keys at two levels:** the payload carries business identity; standard headers serve Splitter/Resequencer/Aggregator within a tested topology. With nested Splitters, also distinguish the **outer batch group** from the **inner line group**.

## 15. Through a Gateway: replyChannel and businessCorrelationId Serve Different Purposes

A Gateway can create a request message and manage a `replyChannel` to route the **reply back to the waiting caller**:

~~~java
@MessagingGateway(defaultRequestChannel = "orders.in")
interface OrderGateway {
    OrderSummary submit(OrderEvent event);
}
~~~

**Do not conflate the two mechanisms:**

- `replyChannel` is the **technical return address** of an active request–reply call.
- `businessCorrelationId` is the **logical work identity** for grouping, retries, tracing, and replays.

When a Splitter emits multiple children and an Aggregator builds one summary, the Gateway typically expects **one aggregated reply**, not each child result. Losing `replyChannel` can cause timeouts/errors even when the business key is intact. Losing the business key can cause misgrouping in the Aggregator even when the Gateway has a valid reply channel.

**Never serialize a temporary in-JVM reply channel object as a business correlation ID** when sending requests over a broker. For cross-process request–reply, use an adapter/gateway with proper reply destinations/correlation mapping, or a coordinator persisting pending state under a durable key.

## 16. Content Enricher: Secondary Lookup Requests Must Link Back to the Original

An `OrderEvent` needs customer enrichment:

~~~text
Original M0:
  orderId=O-101
  businessCorrelationId=t:tenant-a|o:O-101|v:3|op:PRICE

Lookup request Q1:
  customerId=C-01
  lookupRequestId=ER-501
  parentBusinessCorrelationId=<key M0>

Lookup reply R1:
  lookupRequestId=ER-501
  customerProfile=GOLD
~~~

Spring Integration's Content Enricher can use internal request–reply and a temporary `replyChannel` to fetch data and apply it to the original message. However, if the lookup crosses a broker or an independent callback, you need a **separate `lookupRequestId`** per logical enrichment request plus a mapping back to the parent group.

Never use `customerId` to match all replies: many different orders share the same customer. Never replace the original's `businessCorrelationId` with `lookupRequestId`, as that breaks correlation for the main flow.

**Parent correlation** and **child request correlation** are two distinct levels:

~~~mermaid
flowchart TD
    M["Order work group G"] --> Q1["Lookup request ER-501"]
    M --> Q2["Lookup request ER-502"]
    Q1 --> R1["Reply ER-501"]
    Q2 --> R2["Reply ER-502"]
    R1 --> M
    R2 --> M
~~~

A pending store or broker adapter can maintain `ER-501 → G` and `ER-502 → G`; never rely on reply arrival order.

## 17. Content-Based Router, Header Enricher, and Aggregator Are Not the Same Pattern

| Pattern | Question | Impact on Correlation |
|---|---|---|
| Content Based Router | **Where** to route by content? | Must preserve logical identity across branches |
| Header Enricher | **Which metadata** to add/normalize? | Can compute the business key header from payload |
| Transformer | **What type** to convert payload into? | New DTO must keep identity or header must survive |
| Splitter | **How many children** to split into? | Adds sequence metadata without losing parent identity |
| Aggregator | **Which children share a group** and when is it done? | Uses correlation strategy and release strategy |
| Content Enricher | What secondary lookup data to add? | Lookup request uses secondary identity; never overwrites parent group |
| Gateway | Return address of which invocation? | Reply channel does not replace business correlation |
| Resequencer | In what order to emit messages? | Needs valid group key and sequence numbers |

**Content-based correlation** is an **identity strategy**, not a standalone `@ContentBasedCorrelation` annotation in Spring Integration. It is typically implemented using the **correlation strategy/expression of an Aggregator/Resequencer** combined with ingress normalization.

## 18. Aggregator: Prefer a Payload-Based Correlation Strategy When Durability Matters

If workers return `LineResult` carrying full identity, the Aggregator can compute the key directly:

~~~java
@Configuration
@EnableIntegration
class GroupedLineResultFlow {

    @Bean
    IntegrationFlow groupLineResults() {
        return IntegrationFlow.from("orders.line.results")
            .aggregate(a -> a
                .correlationStrategy(message ->
                    BusinessGroupKey.from(
                        (LineResult) message.getPayload()))
                .releaseStrategy(new AllExpectedLinesRelease())
                .outputProcessor(new OrderSummaryProcessor()))
            .channel("orders.completed")
            .get();
    }
}
~~~

This illustrates Java DSL. `AllExpectedLinesRelease` and `OrderSummaryProcessor` are application classes explained below; they are not built-in framework APIs. Add type validation when inbound messages might carry unexpected types, and use an appropriate `MessageGroupStore`/locking setup for multi-instance deployments.

**Why read from the payload instead of a header?** If a wire adapter drops custom headers while the payload retains tenant/order/revision/operation, correlation can still be reconstructed. That is the core of **content-based correlation**. However, payloads can be tampered with or forged, so only rely on validated/trusted fields.

## 19. Release Strategy Must Inspect Members, Not Just Group Size

A naive release strategy:

~~~java
.releaseStrategy(group -> group.size() == 3)
~~~

**breaks** when:

~~~text
Group G:
  L1 success
  L1 duplicate from redelivery
  L2 success
  L3 has not arrived yet

group.size() is already 3 → premature release.
~~~

An illustrative model checking consistency and distinct member IDs:

~~~java
final class AllExpectedLinesRelease implements ReleaseStrategy {

    @Override
    public boolean canRelease(MessageGroup group) {
        List<LineResult> parts = group.getMessages().stream()
            .map(message -> (LineResult) message.getPayload())
            .toList();

        if (parts.isEmpty()) {
            return false;
        }
        LineResult first = parts.get(0);
        int expected = first.expectedLines();
        if (expected <= 0 || expected > 100_000) {
            throw new IllegalStateException("INVALID_EXPECTED_LINES");
        }
        String key = BusinessGroupKey.from(first);
        boolean consistent = parts.stream().allMatch(part ->
            BusinessGroupKey.from(part).equals(key)
                && part.expectedLines() == expected);
        if (!consistent) {
            throw new IllegalStateException("INCONSISTENT_GROUP");
        }
        long distinctLines = parts.stream()
            .map(LineResult::lineId)
            .distinct()
            .count();
        return distinctLines == expected;
    }
}
~~~

**Limitation:** checking `distinctLines == expected` still does not prove the IDs match the **exact manifest**. An unexpected member L99 could take the place of L3. Production should persist the expected `expectedLineIds` set upfront and compare sets, while handling conflicting duplicate outcomes before emitting a summary.

Never accept `expectedLines` from an untrusted worker as the authoritative total; expected counts must be locked in by the coordinator/manifest and cross-checked.

## 20. Output Processor: Summary Must Preserve Parent Correlation

Once the group releases, the new `OrderSummary` message still needs identity if further downstream processing exists:

~~~java
record OrderSummary(
    String tenantId,
    String orderId,
    int revision,
    WorkOperation operation,
    String businessCorrelationId,
    int expectedLines,
    long totalAmountCents,
    int failed
) {}

final class OrderSummaryProcessor implements MessageGroupProcessor {

    @Override
    public Object processMessageGroup(MessageGroup group) {
        Map<String, LineResult> byLine = new LinkedHashMap<>();
        for (Message<?> message : group.getMessages()) {
            LineResult part = (LineResult) message.getPayload();
            LineResult previous =
                byLine.putIfAbsent(part.lineId(), part);
            if (previous != null && !previous.equals(part)) {
                throw new IllegalStateException(
                    "CONFLICTING_DUPLICATE_RESULT");
            }
        }
        if (byLine.isEmpty()) {
            throw new IllegalStateException("EMPTY_GROUP");
        }

        LineResult first = byLine.values().iterator().next();
        long total = 0;
        int failed = 0;
        for (LineResult part : byLine.values()) {
            if (part.success()) {
                total = Math.addExact(total, part.amountCents());
            } else {
                failed++;
            }
        }
        return new OrderSummary(
            first.tenantId(),
            first.orderId(),
            first.revision(),
            first.operation(),
            BusinessGroupKey.from(first),
            first.expectedLines(),
            total,
            failed);
    }
}
~~~

`OrderSummary` preserves the parent identity and failure count. If `failed > 0`, downstream must decide per domain rules whether the summary is `PARTIAL`, `FAILED`, or acceptable; **never treat summing amounts from successful lines as meaning the whole order succeeded**.

The output processor also does not create an exactly-once transaction on its own. If a group releases twice due to redelivery/expiry/restart, you need an idempotent publisher/outbox keyed by the business group key and output version.

## 21. Content Key and Spring Framework Correlation Header Can Coexist

On a message exiting a Splitter, you may see:

~~~text
headers.businessCorrelationId
  = t:tenant-a|o:O-101|v:3|op:PRICE

headers.correlationId
  = <framework sequence-group identity>

headers.sequenceNumber = 2
headers.sequenceSize   = 3
~~~

**You do not need to force these two headers to always be equal.** The Splitter's `correlationId` header serves how the framework gathers child messages of **that specific split**. The `businessCorrelationId` header serves logical work across brokers, retries, replays, and auditing.

If the Aggregator is configured with a **custom correlation strategy from the payload**, it does not have to depend on `headers.correlationId`. However, other components like a Resequencer or nested Aggregator may still rely on sequence headers; never strip them inside the JVM without understanding the topology.

Tests should verify **both**:

- Business group identity remains unchanged across endpoints.
- Sequence metadata is interpreted accurately at sequence-consuming endpoints.

## 22. When to Keep Keys in Headers Only, Payload Only, or Both?

| Strategy | Pros | Risks / Protections Needed |
|---|---|---|
| **Header-only** | Minimal DTO changes, easy for framework routers to read | Easily lost via header mappers, custom messages, or wire layers |
| **Payload-only** | Stable contract across brokers, easy to replay | Prone to collisions/errors if DTO lacks identity or payload is forged |
| **Header + payload** | Easy to route/trace while retaining recovery capability | Two copies can diverge; requires cross-checking |
| **Lookup from pending store** | Useful for callbacks carrying only a request ID | Must protect durability, TTL, and authorization |

For **short in-process** flows, a standard correlation header may suffice when endpoints are controlled. For **distributed or replayable** flows, include group identity in the wire schema or maintain a durable mapping from request ID to group.

When keeping both header and payload, the **validated trusted payload** or pending manifest should be the source of truth. On mismatch, reject/quarantine rather than arbitrarily picking whichever arrived last.

## 23. Across QueueChannel and ExecutorChannel

Within the same JVM, switching from `DirectChannel` to `ExecutorChannel` or `QueueChannel` does not inherently change the business group key. Still, asynchronous boundaries introduce extra challenges:

1. Messages can finish **out of order**.
2. Exceptions occur **after** upstream `send()` returns successfully.
3. The `errorChannel` header and reply semantics can behave differently across an async boundary.
4. Pending groups sit waiting until all members arrive or the deadline expires.
5. Thread pools/queues can saturate when a Splitter fans out heavily.

**Correlation is not ordering.** Sharing a key does not guarantee arrival order. If downstream needs events in sequence, use a Resequencer; if only a summary is needed, the Aggregator can accept out-of-order results and join them by business member IDs.

**Resource bounds:** use bounded executors/queues, max pending groups, and timeouts. Even with flawless business correlation, one permanently lost message will leave the Aggregator waiting forever without an expiry policy.

## 24. Across Kafka/AMQP/HTTP: Headers Are Not an Automatic Wire Contract

When messages cross a broker or HTTP:

- Header mappers decide which headers are serialized, renamed, dropped, or type-converted.
- A new Spring Message may receive a brand-new `MessageHeaders.ID` at the consumer.
- `replyChannel`/`errorChannel` may be internal objects unsafe to transmit as IDs.
- A broker adapter's correlationId may serve **technical request–reply**, not the business group key.
- Messages can be redelivered, delayed, or reordered across multiple partitions/consumers.

**Recommended wire contract** for a member:

~~~json
{
  "schemaVersion": 1,
  "tenantId": "tenant-a",
  "orderId": "O-101",
  "revision": 3,
  "operation": "PRICE",
  "eventId": "EV-101",
  "lineId": "L-2",
  "expectedLines": 3,
  "amountCents": 2500,
  "success": true,
  "reasonCode": null
}
~~~

If the receiver has all fields, it can **recompute** `BusinessGroupKey`. A producer may also send `businessCorrelationId`, but the receiver must compare it against the canonical value and validate tenant/source.

Never dump raw Spring `MessageHeaders` as JSON output without an allowlist. Those headers can contain credentials, routing internals, or non-serializable objects. Never assume two different broker adapters preserve the same header map identically.

## 25. Mapping When Replies Traverse a Different Transport

Example:

~~~mermaid
sequenceDiagram
    participant P as Order processor
    participant K as Broker
    participant W as Worker
    participant A as Aggregator
    P->>K: LineWork L2 + group fields
    K->>W: Deserialize LineWork
    Note over W: A new Message ID may be created
    W->>K: LineResult L2 + group fields
    K->>A: Deserialize LineResult
    Note over A: Compute group key from payload
    A->>A: Group by tenant/order/revision/operation
~~~

**Never group by arrival order** or by an in-JVM temporary reply channel. The receiver must use the contract's identity and stable canonicalization rules.

If a schema evolves from `revision: number` to `revision: string`, or changes how tenant IDs are formatted, use versioned validation. Two visually similar values can produce different keys; conversely, careless casting can cause collisions.

With official Spring Integration request–reply adapters, verify **technical correlation and reply destination mapping** for your specific technology and version; business correlation must never be overwritten simply because an adapter uses the same header name in its own context.

## 26. Retries: Keep Logical Group ID, Separate Attempt ID

A line times out:

~~~text
Logical work:
  groupKey = t:tenant-a|o:O-101|v:3|op:PRICE
  lineId   = L-2

Attempt 1:
  attemptId = A-1
  → timeout at caller

Attempt 2:
  attemptId = A-2
  → LineResult returned
~~~

If this is a **retry of the same logical operation**, the group key must stay unchanged. Never put `attemptId` into the Aggregator's key, or the two attempts will land in separate groups. Attempt ID remains useful for tracing, fencing, and selecting the final valid result.

**A timeout does not prove the worker never executed.** Attempt 1 may have written data or sent a reply that arrives late. Therefore you need:

- Idempotency keys scoped to `(tenant, group, lineId, operation)` or the specific side effect.
- Deduplication/conflict detection for duplicate replies.
- An overall deadline for the logical work, never reset infinitely on retries.
- Conditional completion/publishing so two terminal summaries are never emitted.

Generating a new UUID per attempt makes sense for **attempt tracking**, never as a replacement for **parent business correlation**.

## 27. Duplicates, Late Replies, and Completed Groups

After the Aggregator releases a group, an old reply may arrive:

~~~text
T0  L1, L2, L3 of group G completed
T1  Aggregator emits OrderSummary(G)
T2  Broker redelivers L2 (duplicate)
T3  Old worker attempt returns L1 late
~~~

If the old group was deleted with no durable completion record, late replies **can spawn a new group with the same key**, leading to phantom waiting groups or double publishing.

Mechanisms:

1. **Completion tombstone** keyed by group key with a TTL chosen for the late-arrival window.
2. **Idempotent output** using a uniqueness key on `OrderSummary(groupKey, outputVersion)`.
3. **Expiry/late reply policy**: ignore, quarantine, or emit a versioned correction event.
4. **Reconciliation** when outcomes conflict or side effects already committed.

Spring Integration provides settings around group expiry/completion and `MessageGroupStore`, but **does not automatically guarantee business-level exactly-once**. Evaluate behavior on your target version and backend.

## 28. Error Channel: Failures Need Correlation Too

The success path may preserve the business key, while the error path drops it:

~~~text
LineWork L2 → HTTP client exception
  → ErrorMessage(exception only)
  → error handler does not know tenant/order/revision/lineId
~~~

An effective error handler needs **failure context**:

~~~java
record WorkFailure(
    String businessCorrelationId,
    String lineId,
    String reasonCode,
    boolean retryable
) {}
~~~

When converting a failure into a `LineResult(success=false)` or `WorkFailure`, clarify:

- Which logical group does the failure belong to?
- Which member failed?
- Should this count as a **terminal outcome** for the member, or should it be retried?
- Is it a permanent error like an invalid SKU, or transient like a timeout?
- Is the error returned synchronously to the Gateway or published via an async transport's error channel?

Do not assume every `ErrorMessage` carries the original payload in the same place; depending on exception type and endpoint, extract the failed message/correlation context available from the framework or handler. **Never log or publish raw exceptions containing sensitive data to public brokers.**

If the error flow returns a failure outcome to the Aggregator, that outcome must carry the **exact business key and member ID**, never lumping all errors under a shared key like `UNKNOWN`.

## 29. Multi-Tenant Security: Syntactically Valid Keys Can Still Violate Authorization

An attacker sends:

~~~json
{
  "tenantId": "tenant-b",
  "orderId": "O-101",
  "revision": 3,
  "operation": "PRICE"
}
~~~

If the server builds the group key straight from the raw payload without verifying the sender has access to `tenant-b`, the message can be injected into another tenant's group.

Content-based correlation must be paired with:

- **Authenticated tenant scope** at ingress.
- Verifying `orderId` belongs to the authenticated tenant.
- Validating replies come from authorized services, matching schemas and member identities.
- Access controls on `MessageGroupStore`, logs, and error channels.
- Consistent canonicalization across all instances.
- Rejecting abnormally long or malformed group keys/IDs to prevent memory/storage abuse.

**Correlation ID is an identifier, not proof of authorization.** Knowing the right group key does not grant a party permission to read or mutate the group's contents.

## 30. Nested Splitters and Two Levels of Correlation

A batch splits into 3 chunks, each with 100 lines:

~~~mermaid
flowchart TD
    B["Batch B-1"] --> S1["Splitter: 3 chunks"]
    S1 --> C1["Chunk 1"]
    S1 --> C2["Chunk 2"]
    S1 --> C3["Chunk 3"]
    C1 --> S2["Splitter: per line"]
    C2 --> S2
    C3 --> S2
    S2 --> W["Workers"]
    W --> AG1["Line → Chunk Aggregator"]
    AG1 --> AG2["Chunk → Batch Aggregator"]
~~~

There are at least two identities:

~~~text
parentBatchKey = tenantId + batchId + revision
childChunkKey  = parentBatchKey + chunkIndex
lineMemberId   = lineId
~~~

If a nested Splitter resets `correlationId` for the **innermost level**, relying solely on the standard header can lose the outer layer's grouping ability. Use explicit payload IDs/manifests per level, or a pre-designed parent-correlation carrier.

Never confuse `sequenceNumber=2` of a chunk with `sequenceNumber=2` of a line: the sequences belong to **different spaces**. Group keys must encode scope/level so the batch Aggregator never mistakenly consumes a chunk-level `LineResult`.

## 31. Unit Test: Keys Must Be Stable and Scoped

JUnit 5:

~~~java
@Test
void sameLogicalWorkHasSameKey() {
    String keyA = BusinessGroupKey.of(
        "tenant-a", "O-101", 3, WorkOperation.PRICE);
    String keyRetry = BusinessGroupKey.of(
        "tenant-a", "O-101", 3, WorkOperation.PRICE);

    assertEquals(keyA, keyRetry);
}

@Test
void differentRevisionTenantOrOperationHasDifferentKey() {
    String base = BusinessGroupKey.of(
        "tenant-a", "O-101", 3, WorkOperation.PRICE);

    assertNotEquals(base, BusinessGroupKey.of(
        "tenant-a", "O-101", 4, WorkOperation.PRICE));
    assertNotEquals(base, BusinessGroupKey.of(
        "tenant-b", "O-101", 3, WorkOperation.PRICE));
    assertNotEquals(base, BusinessGroupKey.of(
        "tenant-a", "O-101", 3, WorkOperation.INVENTORY));
}

@Test
void rejectsAmbiguousDelimiterInIdentifier() {
    assertThrows(IllegalArgumentException.class,
        () -> BusinessGroupKey.of(
            "tenant|b", "O-101", 3, WorkOperation.PRICE));
}
~~~

These tests verify only the **key**. They do not verify message headers, broker serialization, or group membership in the Aggregator. For complex canonicalization, add property-based tests covering Unicode characters, leading zeros, casing, and delimiter-containing fields.

## 32. Integration Test: Same Key Across Filter and Header Enricher

Testing a header-stamping flow:

~~~java
@Autowired
ApplicationContext context;

@Test
void stampsBusinessKeyAtIngress() {
    MessageChannel input =
        context.getBean("orders.in", MessageChannel.class);
    PollableChannel output =
        context.getBean("orders.correlated", PollableChannel.class);

    OrderEvent order = new OrderEvent(
        "tenant-a", "O-101", 3, "EV-101",
        WorkOperation.PRICE,
        List.of(new OrderLine("L1", "SKU-1", 500, 2)));

    assertTrue(input.send(new GenericMessage<>(order)));
    Message<?> received = output.receive(1_000);
    assertNotNull(received);

    assertEquals(BusinessGroupKey.from(order),
        received.getHeaders().get("businessCorrelationId"));
}
~~~

This test requires configuring `orders.correlated` as a **test-only QueueChannel** with no competing production consumers. Another test should send an original message with a **wrong** `businessCorrelationId` to verify **rejection/overwriting per explicit policy**; do not test only the empty-header case.

## 33. Integration Test: Splitter → Workers → Aggregator Does Not Mix Two Groups

Create two orders:

~~~text
O-101/rev3/PRICE → [L1, L2, L3]
O-101/rev4/PRICE → [L1, L2, L4]
~~~

Send interleaved replies:

~~~text
rev3/L2
rev4/L1
rev3/L1
rev4/L2
rev4/L4
rev3/L3
~~~

Expect **two independent summaries**. Reference code:

~~~java
@Autowired
ApplicationContext context;

@Test
void separatesTwoRevisionsDuringAggregation() {
    MessageChannel input = context.getBean(
        "orders.line.results", MessageChannel.class);
    PollableChannel output = context.getBean(
        "orders.completed", PollableChannel.class);

    send(input, result(3, "L2"));
    send(input, result(4, "L1"));
    send(input, result(3, "L1"));
    send(input, result(4, "L2"));
    send(input, result(4, "L4"));
    send(input, result(3, "L3"));

    OrderSummary first = (OrderSummary)
        Objects.requireNonNull(output.receive(1_000))
            .getPayload();
    OrderSummary second = (OrderSummary)
        Objects.requireNonNull(output.receive(1_000))
            .getPayload();

    assertEquals(Set.of(3, 4),
        Set.of(first.revision(), second.revision()));
    assertNotEquals(first.businessCorrelationId(),
        second.businessCorrelationId());
}
~~~

`send(...)` and `result(...)` are **application-defined test fixtures**. Add assertions for the **exact set of member IDs and amounts**, not just revisions or output count; two summaries could have the right revisions yet wrong members if a worker or release strategy has a bug.

Never use `Thread.sleep` to force ordering; send messages in a deterministic sequence or use a `CountDownLatch` when testing real concurrency. With brokers, also test serialization, header mappers, and redelivery.

## 34. End-to-End Failure Matrix to Test

| Scenario | Input | Expected Outcome |
|---|---|---|
| Happy path | One order, all line results | One summary in the right group |
| Two orders in same tenant | Different `orderId` | Groups never mix |
| Same order, different revisions | rev3 and rev4 interleaved | Two separate summaries |
| Two operations | PRICE and INVENTORY | Never merged together |
| Cross-tenant | Same order code in tenant A/B | Isolated groups with access checks |
| Header lost across broker | Payload has full business fields | Key recomputed accurately |
| Header mismatches payload | Conflicting payload/key | Reject/quarantine; never pick arbitrarily |
| Transformer builds new message | Different Message ID | Group identity remains intact |
| Retry of same logical work | Attempt ID changes | Business key stays unchanged |
| Duplicate LineResult | Two copies of same `lineId` | Not counted as two members |
| Conflicting duplicate | Success and failure for same member | Conflict detected / reconciled |
| Missing member | Filter drops a line | Timeout/failure result, no fake completion |
| Unknown correlation | No matching group/pending state | Quarantine or reject with metrics |
| Late reply | Arrives after completion | No out-of-contract double publish |
| Nested Splitter | Batch→chunk→line | Accurate two-level correlation |
| Async error | Worker throws exception | Error path preserves group/member identity |
| Restart | Persistent group store | Recovers per designed guarantees |
| Key migration | Old/new canonical format | Versioned/drained/migrated cutover |

**In particular:** include a test that builds a **new Spring Message with the same payload but a different `MessageHeaders.ID`** to prove grouping relies on business content rather than object identity.

## 35. Observing Correlation in Production

Emit structured traces:

~~~text
ingress:
  eventId=EV-101
  businessCorrelationId=t:tenant-a|o:O-101|v:3|op:PRICE
  endpoint=orders.in

filter/router:
  endpoint=orders.correlated
  route=price.requests

split:
  memberId=L2
  sequenceNumber=2
  sequenceSize=3

worker:
  memberId=L2
  attempt=2
  outcome=SUCCESS

aggregate:
  groupKey=t:tenant-a|o:O-101|v:3|op:PRICE
  distinctMembers=3
  expectedMembers=3
  status=COMPLETED
~~~

Suggested metrics:

| Metric | Detects |
|---|---|
| `correlation.key.missing.count` | Missing key in header/payload |
| `correlation.key.mismatch.count` | Header differs from canonical payload |
| `correlation.group.pending.count` | Incomplete groups |
| `correlation.group.age` | Unusually long-waiting groups |
| `correlation.group.duplicate.count` | Redeliveries and duplicates |
| `correlation.group.unknown.count` | Replies without a valid group |
| `correlation.group.expired.count` | Timeouts/expiries |
| `correlation.group.late.count` | Late replies |
| `correlation.group.completed.count` | Succeeded/failed group releases |
| `message.store.bytes` | Storage pressure |

These are **suggested metric names**, not built-in Spring Integration meters. Use low-cardinality tags (`flow`, `endpoint`, `outcome`, `reason`); **never use full `businessCorrelationId`, `orderId`, or `eventId` as metric tags**. Specific IDs belong in tracing/logs with proper access controls and retention.

A trace should answer: **where was the ID issued, was it altered at any endpoint, which message is missing, why hasn't the group released, and which reply arrived late?**

## 36. Runbook When Correlation Is Lost After an Endpoint

When the Aggregator holds thousands of incomplete groups or emits wrong summaries:

1. **Identify the logical work scope:** tenant/order/revision/operation; which members belong in a valid group?
2. **Inspect ingress:** was identity taken from an authenticated source or raw client headers?
3. **Inspect payloads:** do group identity fields survive before and after Transformers?
4. **Inspect custom headers:** was `businessCorrelationId` dropped or overwritten?
5. **Inspect Splitters:** did standard `correlationId` and sequence metadata change at the right group level?
6. **Inspect Routers/Filters:** was a branch dropped or misrouted?
7. **Inspect async boundaries:** do Queues/Executors/brokers preserve headers and contracts as intended?
8. **Inspect worker replies:** do results carry stable event/group/member identities?
9. **Inspect the Aggregator:** which payload/header does the correlation strategy read, and does release check distinct members?
10. **Inspect errors/retries:** were outcomes lost, duplicated, or late, and do completion tombstones exist?
11. **Verify side effects:** was an incorrect summary already committed/published before replaying or correcting?
12. **Remediate:** fix mapping/validation/key versioning, add integration tests, and drain/migrate pending groups in a controlled manner.

**Never assign an `UNKNOWN` key to all messages missing an ID.** Doing so lumps every malformed input into one “super-group,” causing data corruption or cross-tenant leaks. If a trustworthy identity cannot be recovered, reject/quarantine with a clear error.

## 37. Common Misconceptions

**“Every Spring Integration endpoint automatically preserves all headers.”** You cannot assume that, especially with custom MessageBuilders, adapters, and broker mappers. Test your exact topology.

**“Correlation ID is `MessageHeaders.ID`.”** No. One is group identity; the other identifies a single message object at a point in time.

**“Having `traceId` is enough for the Aggregator to group messages.”** No. Tracing context has a different scope and lifecycle from a business group.

**“Using `orderId` alone is always safe.”** Not when multiple revisions, operations, or tenants exist.

**“A fresh UUID in every worker makes correlation stronger.”** Wrong: the same logical work gets fragmented into separate groups.

**“When routing to Pricing, set `correlationId` to the channel name.”** Wrong: a channel name is not a group identity.

**“Splitter `correlationId` and `businessCorrelationId` must always be equal.”** No. Two levels of IDs serve different semantics.

**“If the payload has a group ID, no header check is needed.”** Insufficient if external callers can forge content or if header and payload conflict.

**“Having the header means authorization succeeded.”** Wrong. An ID identifies; it does not authorize.

**“A persistent `MessageGroupStore` fixes key collisions automatically.”** Wrong; it simply stores wrong groups longer.

**“Three messages means all three lines arrived.”** Wrong with duplicates. Check distinct member IDs and the manifest.

**“Retries create a new business group.”** Not when retrying another attempt of the same logical operation.

**“Gateway `replyChannel` can be used as business correlation on Kafka.”** No; an internal return address is not a durable group identity.

**“The error channel automatically sends failure results into the Aggregator.”** No; you must design error-to-outcome mapping carrying the right group and member identity.

**“Once a group releases, no late replies can arrive.”** Wrong; you need idempotency and a late-arrival policy.

## 38. Practice Exercise: Propagating Identity Across Eight Endpoints

Build the **OrderCorrelationPipeline** flow:

1. **Gateway/ingress:** receive authenticated `OrderEvent`, create `businessCorrelationId` from `tenantId/orderId/revision/operation`.
2. **Filter:** reject missing/invalid data, preserving the group ID in error outcomes.
3. **Header Enricher:** compute or verify the custom correlation header from the payload.
4. **Router:** branch PRICE/INVENTORY without altering parent group identity.
5. **Transformer:** convert payload into a new DTO carrying complete identity.
6. **Splitter:** emit each line while keeping the parent key and sequence metadata.
7. **Worker:** return `LineResult` using a durable member ID; test retries producing new Spring Message IDs.
8. **Aggregator:** compute correlation strategy from the payload and release based on expected manifest/member IDs.
9. **Gateway/outbound:** produce `OrderSummary` preserving the parent key and completion status.
10. **Broker:** route one branch over Kafka/AMQP and verify the payload contract and header mapper.
11. **Errors:** test Filter rejection, timeout, duplicate/conflicting replies, late replies, and cross-tenant input.
12. **Observability:** trace keys across every endpoint and measure pending/mismatch/expired groups.

**Completion criteria:** the same logical work keeps the same key across all endpoints; two revisions/tenants/operations never mix; the key can be reconstructed from the payload after a broker strips headers; Splitter correlation is never arbitrarily overwritten; the Aggregator releases only for the exact expected member set; and errors/retries/late replies yield explicit decisions with no out-of-contract duplicate outputs.

## 39. Key Takeaways

**Propagating correlation ID across multiple endpoints** is not merely forwarding an intact header. It is preserving the **semantics of a logical processing group** across Gateway, Filter, Router, Transformer, Splitter, workers, brokers, Aggregator, and error channels.

In **Content-based correlation**, maintain **stable business identity in the payload or a durable contract**, compute a canonical group key from authenticated fields, and optionally carry `businessCorrelationId` in an internal header. Keep this key distinct from `MessageHeaders.ID`, Splitter sequence headers, trace IDs, and Gateway reply channels.

Combine **proper correlation**, **member-verifying release strategies**, **idempotency/late-reply policies**, **timeouts/`MessageGroupStore`**, and **cross-transport testing** to ensure every result joins the right group—even when messages change types, cross processes, arrive out of order, or get redelivered.

### References

- Spring Integration Reference, **Aggregator**: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Integration Reference, **Splitter**: https://docs.spring.io/spring-integration/reference/splitter.html
- Spring Integration Reference, **Header Enricher**: https://docs.spring.io/spring-integration/reference/content-enrichment.html
- Spring Integration Reference, **Message Channels**: https://docs.spring.io/spring-integration/reference/channel.html
- Enterprise Integration Patterns, **Correlation Identifier**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/CorrelationIdentifier.html
- Enterprise Integration Patterns, **Content-Based Router**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/ContentBasedRouter.html
