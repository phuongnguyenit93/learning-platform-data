# Unstable Correlation Causing Misgrouped Messages

## 1. One Order, Two Processing Runs, and One Wrong Result

A system receives an order with three product lines. A **Splitter** breaks the order into three messages, workers check inventory, and then send results back to an **Aggregator**. In principle, Aggregator must only group results belonging to **the exact same logical processing run of the same order**.

Suppose the customer updates order `O-101` before the first processing run finishes:

~~~text
Run A: orderId=O-101, revision=1, lines=[L1, L2, L3]
Run B: orderId=O-101, revision=2, lines=[L1, L2, L4]

Results return in this order:
  A/L1 succeeded
  B/L1 succeeded
  B/L2 succeeded
  A/L3 succeeded
  A/L2 succeeded
  B/L4 succeeded
~~~

If Aggregator uses only `orderId=O-101` for correlation, **runs A and B can be merged into one message group**. If the release strategy only checks count 3, the group can release right after the first three results even though they belong to **two different revisions**. The output looks like three complete lines yet holds corrupted content.

This is a dangerous bug because it may **throw no exception**: an `OrderSummary` is created, Gateway returns a reply, downstream writes data, yet the aggregated result does not belong to a consistent business set.

**Topic of this lesson:** designing **stable, scoped correlation keys**, ensuring every message enters the exact right group, avoiding misgrouping across tenants, runs, revisions, retries, or broker redeliveries; and combining release strategy with idempotency so completion is never concluded prematurely.

This lesson belongs to the **Aggregator** chapter of the **SPRING_INTEGRATION_PATTERN** module. The module aims to teach implementing **Enterprise Integration Patterns** with Spring Integration to build loosely coupled, extensible message flows; practicing **Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation**, while testing and monitoring processing branches.

After this lesson, you will be able to analyze causes of misgrouping, define the identity of a unit of work, create clear correlation strategies, coordinate with Splitter, handle duplicate/missing/late groups, select an appropriate `MessageGroupStore`, and test concurrency, retries, and restarts.

## 2. Aggregator Does Not Know What "Same Business Unit" Means on Its Own

**Aggregator** in Enterprise Integration Patterns receives multiple related messages, places them into a **message group**, evaluates a **release strategy**, and produces an aggregated output. To do so, it must answer at least:

1. **Correlation:** which **group** should this message be placed in?
2. **Release:** when does that group have **enough information to conclude**?
3. **Aggregation:** **how** should messages in the group be combined into the result payload?
4. **Expiry:** when should incomplete or completed groups be retained/deleted/handled?

~~~mermaid
flowchart LR
    A["LineResult A/L1"] --> COR{"Correlation strategy"}
    B["LineResult B/L1"] --> COR
    C["LineResult A/L2"] --> COR
    COR --> GA["Group: O-101/rev1"]
    COR --> GB["Group: O-101/rev2"]
    GA --> RA{"Release strategy A"}
    GB --> RB{"Release strategy B"}
    RA --> OA["Summary revision 1"]
    RB --> OB["Summary revision 2"]
~~~

A miscomputed correlation key puts a message **into the wrong group from the start**. The release strategy may then execute its counting rule accurately while still producing a **business-wrong outcome**. Conversely, an overly specific or constantly changing key splits messages from the same processing run into **multiple groups**, leaving none with enough results.

**An Aggregator cannot fix bad correlation on its own** merely by waiting longer. You must fix identity definitions, protect inputs, verify group membership, and design retries/expiry.

## 3. What Is Unstable Correlation?

A "stable" correlation key means **every result of the same logical unit of work produces the exact same key**, while two units of work that **must not be merged** produce different keys.

Two opposite failure modes:

| Failure Mode | Example | Consequence |
|---|---|---|
| **Key changes within same group** | Every retry generates a new UUID and uses it as correlation | Same batch splits into multiple incomplete groups |
| **Key collides across different groups** | Using only `orderId`, omitting revision | Two processing runs get mixed |
| **Key lost on message transformation** | Transformer creates new message and drops correlation header | Aggregator creates wrong group or cannot group |
| **Key changes type/format** | `"00123"` turns into number `123` over a broker | Results land in another group or collide |
| **Key uses untrusted source** | Using raw client-supplied `tenantId`/`correlationId` | Risk of cross-tenant data mixing |
| **Time-dependent key** | Computing key from `Instant.now()` inside each handler | Each branch can land in its own group |
| **Key too coarse** | Using `customerId` as correlation | Multiple orders for one customer land in one group |
| **Key too granular** | Using `lineId` to aggregate whole-order results | Each line becomes its own group |

**Key invariant:**

\[
\text{sameLogicalWork}(m_1,m_2)
\Longrightarrow
\operatorname{key}(m_1)=\operatorname{key}(m_2)
\]

\[
\neg\text{sameLogicalWork}(m_1,m_2)
\Longrightarrow
\operatorname{key}(m_1)\ne\operatorname{key}(m_2)
\]

Both conditions must be defined by **business semantics**, not just Java types or header values. In practice, hashes can collide, strings can normalize incorrectly, and business IDs can be intentionally reused across revisions.

## 4. "Same Order" Does Not Necessarily Mean "Same Group"

An `orderId` can outlive a single computation:

~~~text
tenant-A / O-101 / pricing-revision-1
tenant-A / O-101 / pricing-revision-2
tenant-A / O-101 / refund-operation-1
tenant-B / O-101 / pricing-revision-1
~~~

All four records share part of the ID, yet must never share a message group.

A good **aggregation scope** usually needs a combination of:

| Attribute | Why Needed |
|---|---|
| `tenantId` or owner scope | Prevents tenant A's data from mixing into B's |
| `operationType` | Distinguishes pricing, inventory, shipping, refund |
| `workId`/`batchId`/`processId` | Identifies one logical processing run |
| `revision`/`generation` | Distinguishes multiple versions of the same data |
| `expectedMemberSet` or manifest | Knows which results genuinely belong to the group |

**You do not always need to concatenate all attributes.** If a `processingGroupId` is issued uniquely per processing run with clear tenant scoping, it may already represent operation/revision. However, publish and test that ID-issuance contract.

In the examples below, we use a key composed of `tenantId + processingGroupId + revision`. This is a **normalized composite key**, not a raw user-entered string in an unverified header.

## 5. Distinguishing Message ID, `correlationId`, and Business Group ID

| Identifier | Typically Created By | Purpose | Risk When Used as Durable Group Key |
|---|---|---|---|
| `MessageHeaders.ID` | Spring Messaging | Identifies one message instance | Reconstructed messages get new IDs |
| `IntegrationMessageHeaderAccessor.CORRELATION_ID` | Flow/endpoint or application | Links messages in the same group | May be reassigned or stripped across transports |
| `sequenceNumber` | Splitter/sequence producer | Element position in sequence | Not unique per group; every group has item 1 |
| `sequenceSize` | Splitter/sequence producer | Expected element count, when known | Does not identify group; may be missing/wrong |
| `eventId` | Business producer | Event tracing/idempotency | One event can spawn multiple operations |
| `orderId` | Domain | Identifies order | Multiple revisions/runs on the same order |
| `processingGroupId` | Upstream coordinator/Splitter | Identifies one logical processing run | Suitable if stable, unique, and verified |
| `traceId` | Tracing | Observes call chains | Not necessarily aligned with group scope |

**Spring Integration's default correlation strategy** typically uses the `correlationId` header and a release strategy based on sequence headers. They are useful with Splitter/Aggregator inside a controlled topology, yet **are not a durable business correlation contract across every broker/retry/restart**.

In particular, a Splitter may derive correlation from the **ID of the original message at split time**. When replaying the same batch under a **new message**, the original message's ID may differ: children from run 2 do not group with run 1 even when business logic wants to resume the same logical work.

When cross-process or cross-retry semantics are needed, proactively define a **stable business group key** instead of relying on how the framework assigns message IDs per dispatch.

## 6. Group Key Must Be Assigned Before Splitting Messages

A coordinator receives an input batch, identifies the **logical work**, and issues one shared key:

~~~mermaid
flowchart TD
    IN["OrderBatch O-101 revision 7"] --> CO["Coordinator: assign processingGroupId=PG-901"]
    CO --> S["Splitter"]
    S --> L1["LineWork L1 + PG-901"]
    S --> L2["LineWork L2 + PG-901"]
    S --> L3["LineWork L3 + PG-901"]
    L1 --> W1["Worker 1"]
    L2 --> W2["Worker 2"]
    L3 --> W3["Worker 3"]
    W1 --> A["Aggregator by stable group key"]
    W2 --> A
    W3 --> A
~~~

At ID assignment time:

1. Determine tenant from an authenticated source.
2. Select operation and revision from manifest or persisted state.
3. Assign `processingGroupId` **once per logical work**, never regenerating it inside each line handler.
4. Persist the expected-members manifest and deadline if durability is needed.
5. Pass the group ID down to every child and require every result to preserve it.

Never call `UUID.randomUUID()` **inside the correlation strategy**. A method called per message will generate a fresh key for each result, turning every message into its own group.

To retry **the exact same old logical work**, reuse the persisted group ID. If business rules decide a retry is a **new independent processing run**, use a different group ID, explicitly modeled in the state machine—never change it randomly because a worker restarted.

## 7. Child Message Model for Stable Aggregation

Using Java 17+ with immutable records:

~~~java
record OrderLine(
    String lineId,
    String sku,
    int quantity
) {}

record OrderWork(
    String tenantId,
    String orderId,
    String processingGroupId,
    int revision,
    List<OrderLine> lines
) {}

record LineWork(
    String tenantId,
    String orderId,
    String processingGroupId,
    int revision,
    String lineId,
    String sku,
    int quantity,
    int expectedLines
) {}

record LineOutcome(
    String tenantId,
    String orderId,
    String processingGroupId,
    int revision,
    String lineId,
    int expectedLines,
    boolean success,
    String reasonCode
) {
    String stableGroupKey() {
        return StableGroupKey.of(
            tenantId, processingGroupId, revision);
    }
}

record OrderSummary(
    String tenantId,
    String orderId,
    String processingGroupId,
    int revision,
    int expectedLines,
    int succeeded,
    int failed
) {}
~~~

Key points:

- `LineWork` and `LineOutcome` **both carry identity**, rather than relying solely on original Spring headers.
- `lineId` is the identity of **one member** in the group; `processingGroupId` is the identity of the **group**.
- `expectedLines` must be locked from the manifest and consistent across members; never let each worker compute it independently.
- `revision` distinguishes order changes when the same order is processed multiple times.

These types describe the contract. In practice, validate non-null/non-blank fields at ingress and enforce size bounds, tenant scope, and permissions before using them as keys.

## 8. Building Stable Keys Without String-Concatenation Collisions

Naive concatenation like `tenant + orderId` can collide:

~~~text
tenant="AB", orderId="C" → "ABC"
tenant="A",  orderId="BC" → "ABC"
~~~

When using string keys in a `MessageGroupStore`/broker, enforce a **canonical, unambiguous format**:

~~~java
final class StableGroupKey {

    static String of(String tenantId,
                     String processingGroupId,
                     int revision) {
        if (tenantId == null
                || !tenantId.matches("[a-z0-9-]{1,48}")) {
            throw new IllegalArgumentException("INVALID_TENANT");
        }
        if (processingGroupId == null
                || !processingGroupId.matches("[A-Z0-9-]{1,80}")) {
            throw new IllegalArgumentException("INVALID_GROUP_ID");
        }
        if (revision < 1) {
            throw new IllegalArgumentException("INVALID_REVISION");
        }
        // Character | is outside the allowed alphabet of the fields.
        return "t:" + tenantId
            + "|g:" + processingGroupId
            + "|v:" + revision;
    }
}
~~~

Examples:

~~~text
t:tenant-a|g:PG-901|v:7
t:tenant-a|g:PG-901|v:8
t:tenant-b|g:PG-901|v:7
~~~

Three distinct keys correspond to three distinct groups. If IDs allow Unicode, delimiters, or case-insensitive semantics, define encoding/canonicalization and versioning for the format. A **record as group key** can also work within a JVM, though consider serialization/deserialization stability when using a persistent/distributed `MessageGroupStore`.

**Watch out with normalization:** never alter casing of business identifiers if the contract treats `AB` and `ab` as two different IDs. Normalize at the source and apply the **exact same algorithm across every instance**, never transforming differently per branch.

## 9. Splitter Must Preserve Group ID When Emitting Each Item

A simple Splitter can produce `LineWork` items:

~~~java
@MessageEndpoint
class OrderWorkSplitter {

    @Splitter(
        inputChannel = "orders.work",
        outputChannel = "orders.lines")
    public List<LineWork> split(OrderWork work) {
        if (work.lines() == null || work.lines().isEmpty()) {
            throw new IllegalArgumentException("EMPTY_LINES");
        }
        int expected = work.lines().size();
        return work.lines().stream()
            .map(line -> new LineWork(
                work.tenantId(),
                work.orderId(),
                work.processingGroupId(),
                work.revision(),
                line.lineId(),
                line.sku(),
                line.quantity(),
                expected))
            .toList();
    }
}
~~~

Children may carry Splitter-managed sequence headers. Yet **stable group identity lives in the payload contract** and can be retained when workers transform into `LineOutcome`.

If Transformers, Header Enrichers, or broker adapters sit between Splitter and Aggregator, test that they never drop `tenantId`, `processingGroupId`, or `revision`, or remap them to different IDs. A worker returning only `lineId` and `status` while dropping group identity leaves Aggregator unable to correlate reliably.

## 10. Java DSL: Configuring Aggregator with a Custom Correlation Strategy

Spring Integration allows configuring **correlation strategy**, **release strategy**, and **output processor** separately. We do not depend on `MessageHeaders.ID` or implicit assumptions about the source of `correlationId`.

~~~java
@Configuration
@EnableIntegration
class OrderAggregationFlow {

    @Bean
    IntegrationFlow aggregateLineOutcomes() {
        return IntegrationFlow.from("orders.line.results")
            .aggregate(a -> a
                .correlationStrategy(message ->
                    ((LineOutcome) message.getPayload())
                        .stableGroupKey())
                .releaseStrategy(new StableOrderReleaseStrategy())
                .outputProcessor(new OrderSummaryProcessor()))
            .channel("orders.completed")
            .get();
    }
}
~~~

When a `LineOutcome` arrives, the correlation strategy returns a **stable string**, letting Aggregator locate the exact message group. The remaining two strategies are detailed in the following sections.

**Conditions for the example to work:**

- `orders.line.results` receives proper `LineOutcome` objects or has an appropriate type gate.
- Consumers/producers have verified sources and scopes, never blindly trusting client-sent `tenantId`/`processingGroupId`.
- `orders.completed` has a consumer or real test channel.
- This is a Java DSL illustration with imports omitted; real Spring Integration versions may require adjusting certain methods/options.
- Never register another Aggregator simultaneously consuming the same point-to-point input unintentionally.

## 11. Release Strategy Must Not Only Count Messages

A common mistake:

~~~java
.releaseStrategy(group -> group.size() == 3)
~~~

That says "the group currently holds three messages," **not that three messages represent three distinct members**. If L1 is redelivered twice while L3 has not arrived:

~~~text
Group PG-901:
  L1: first result
  L1: duplicate from retry
  L2: valid result

group.size() can equal 3 → wrong release, missing L3
~~~

A stricter release strategy needs the **manifest of expected members** or at minimum checks the **unique member ID count** and consistent metadata. The example below uses `expectedLines` locked upstream:

~~~java
final class StableOrderReleaseStrategy implements ReleaseStrategy {

    @Override
    public boolean canRelease(MessageGroup group) {
        List<LineOutcome> parts = group.getMessages().stream()
            .map(message -> (LineOutcome) message.getPayload())
            .toList();
        if (parts.isEmpty()) {
            return false;
        }

        LineOutcome first = parts.get(0);
        int expected = first.expectedLines();
        if (expected <= 0 || expected > 100_000) {
            throw new IllegalStateException("INVALID_EXPECTED_COUNT");
        }

        boolean consistent = parts.stream().allMatch(part ->
            part.stableGroupKey().equals(first.stableGroupKey())
                && part.orderId().equals(first.orderId())
                && part.expectedLines() == expected);
        if (!consistent) {
            throw new IllegalStateException("GROUP_METADATA_MISMATCH");
        }

        long uniqueMembers = parts.stream()
            .map(LineOutcome::lineId)
            .distinct()
            .count();

        return uniqueMembers == expected;
    }
}
~~~

**Limitation of this example:** comparing `uniqueMembers == expected` only proves there are **enough distinct IDs**, not that those IDs belong to the **manifest's accepted ID set**. A message from a rogue line could take the place of a missing line. In production, check `Set<lineId> == manifest.expectedLineIds` at the coordinator, or use a store/validator capable of verifying membership.

Additionally, duplicates sharing a `lineId` may carry **two conflicting outcomes**; define a policy to classify them before output (e.g., accepting only results from valid attempts/versions). Never silently pick the first or last result in arbitrary order.

## 12. Output Processor: Each Member Contributes Only One Result

Upon release, Aggregator must build an auditable result. Example:

~~~java
final class OrderSummaryProcessor implements MessageGroupProcessor {

    @Override
    public Object processMessageGroup(MessageGroup group) {
        Map<String, LineOutcome> byLine = new LinkedHashMap<>();
        for (Message<?> message : group.getMessages()) {
            LineOutcome part = (LineOutcome) message.getPayload();
            LineOutcome previous =
                byLine.putIfAbsent(part.lineId(), part);
            if (previous != null && !previous.equals(part)) {
                throw new IllegalStateException(
                    "CONFLICTING_DUPLICATE_RESULT");
            }
        }

        if (byLine.isEmpty()) {
            throw new IllegalStateException("EMPTY_GROUP");
        }
        LineOutcome first = byLine.values().iterator().next();

        long successes = byLine.values().stream()
            .filter(LineOutcome::success)
            .count();

        return new OrderSummary(
            first.tenantId(),
            first.orderId(),
            first.processingGroupId(),
            first.revision(),
            first.expectedLines(),
            Math.toIntExact(successes),
            byLine.size() - Math.toIntExact(successes));
    }
}
~~~

The processor here **does not count duplicates as new members**. Still, it does not replace a transactional inbox/dedup store and does not automatically guarantee **only one output is emitted** if the group is recreated after expiry or broker redelivery.

If `LineOutcome.success=false`, that outcome is still a **received result** for the member; it can contribute to "conclusions received for every line," while the summary reports `PARTIAL`/`FAILED`. Not every failure should make Aggregator wait forever; distinguish **structured failure results** from exceptions that drop replies.

## 13. Wrong Key vs. Wrong Release: Two Different Error Classes

| Symptom | Primary Cause | What to Fix |
|---|---|---|
| A/rev1 and B/rev2 mixed | Correlation key too coarse | Add processing group/revision/tenant |
| Each line forms its own group | Key generated anew in each handler | Assign group ID at coordinator before Splitter |
| Group has 3 messages yet misses L3 | Release only counts messages | Unique members + manifest |
| Group still waits despite all lines present | Results use two different key formats | Canonicalization/correlation contract |
| Group releases then emits another summary | Group deleted/recreated, late/duplicate arrives | Completion tombstone and idempotency |
| Summary mixes tenants | Shared ID without tenant scoping | Verified identity + multi-tenant key |
| Only Gateway timeout seen | One member never arrives | Error/timeout/result contract |

**Diagnose in order:** first check **which group each message belongs to**; next check **whether the group has all members**; only then evaluate the output processor. If a group already holds data from two different logical runs, raising timeouts or changing summation logic merely hides the bug.

## 14. Retries and Redeliveries Must Not Alter Group Identity

Suppose a worker processes L2 of group `PG-901` yet times out sending the reply. The broker redelivers L2.

~~~text
Attempt 1: LineWork(PG-901, L2) → LineOutcome(PG-901, L2)
Attempt 2: LineWork(PG-901, L2) → LineOutcome(PG-901, L2)
~~~

For a retry to represent **an attempt of the same logical work**, keep stable:

- `tenantId`;
- `processingGroupId`;
- `revision`;
- `lineId`;
- request/event ID if used for idempotency;
- manifest/expected members.

You can attach `attemptNumber` or `attemptId` to observe retries, yet **never put `attemptId` into the group key** if two attempts must contend for the same member slot in the original group.

If attempt 2 produces a different outcome from attempt 1, never arbitrarily treat them as equivalent. Define:

1. Which outcome is allowed to be the line's **final decision**?
2. Is there a version/fencing token to discard results from stale attempts?
3. When a side effect already committed, does the system enforce line/operation idempotency?
4. Can an already-emitted summary be amended, or must a new correction event be published?

**Spring Integration Aggregator does not provide exactly-once business semantics by itself.** Stable correlation only identifies the right group; transactions, deduplication, and downstream idempotency still require dedicated design.

## 15. Why Can `MessageHeaders.ID` Turn a Retry into a New Group?

In an in-JVM Splitter, sequence/correlation headers may derive from the original message. Yet on redelivery:

~~~text
Original message attempt 1:
  Spring Message ID = m-111
  Splitter → children correlationId = m-111 (illustrative)

Original message attempt 2 (rebuilt):
  Spring Message ID = m-222
  Splitter → children correlationId = m-222
~~~

This is an **illustrative model** depending on how the splitter creates headers and specific configuration. It exposes the risk: same `batchId=PG-901`, yet two splits form **two separate groups** if framework message IDs serve as correlation across retries.

Across external transports, header mappers can also convert `UUID` to `String`, rename headers, or strip them. Two values looking identical in logs might not share the same type/canonical format inside `MessageGroupStore`.

**Recommendation:** keep framework headers for routing **within tested topologies**, while using a stable typed business group key when crossing brokers, restarts, or deployment changes.

## 16. Multi-Tenant: Matching ID Yet Wrong Tenant Is Still Wrong

Two tenants can use the exact same order code:

~~~text
tenant-A / order=O-101 / group=PG-01
tenant-B / order=O-101 / group=PG-01
~~~

If the correlation strategy only returns `PG-01`, data can **mix across tenant boundaries**.

~~~mermaid
flowchart LR
    A["Tenant A / PG-01 / L1"] --> BAD{"Key = PG-01"}
    B["Tenant B / PG-01 / L2"] --> BAD
    BAD --> MIX["Mixed group: wrong"]
~~~

To prevent this:

- Authenticate the tenant at adapters or trust boundaries; never rely solely on client-sent `tenantId` headers.
- Use a **tenant-scoped** correlation key.
- Validate that member messages match the manifest's tenant/order/operation/revision.
- Enforce authorization on `MessageGroupStore`, logs, and error channels; never return tenant A's payloads to a tenant B caller.
- Avoid raw logging of personal data; keep only controlled identifiers needed for tracing.

**Putting tenant into the key is necessary, not sufficient.** If a producer can spoof a tenant ID and inject messages into someone else's group, identity can still be forged. Control assignment sources and permissions.

## 17. A New Revision Must Not Sneak into an Old Group

When an order is modified, two valid models exist:

**Model A — each revision is a new logical work:**

~~~text
PG-901/v1 → separate result
PG-901/v2 → separate result
~~~

Group v1 may finish late, so the system must decide whether old results may still be **published/committed** once v2 is current. Use version checks/fencing downstream.

**Model B — same logical work adjusted before locking:** the coordinator updates the manifest via a state machine; expected members, version, and release policies must then change **in a controlled way**, never mutating group keys on in-flight messages without a migration step.

**Never mix the two models.** Processing a new revision while keeping the old key and old `expectedCount` lets a group release without the new revision's results or with stale data.

A sound audit practice: every `OrderSummary` carries `processingGroupId` and `revision`; consumers accept results only for valid current business versions.

## 18. Late Arrivals and Completed Groups

An often overlooked scenario: Aggregator has already released a group, then an old reply or duplicate arrives.

~~~text
09:00:00  L1, L2, L3 of PG-901 arrive → release Summary #1
09:00:01  duplicate L2 arrives
09:00:02  stale reply L1 from old attempt arrives late
~~~

Aggregator's behavior on post-completion messages depends on **group lifecycle**, expiry config, and `MessageGroupStore`. If the old group was deleted and no completion record exists, late arrivals **can form a new group with the same correlation key**, eventually producing erroneous extra output.

Solutions depending on requirements:

1. **Completion tombstone:** store a marker "group PG-901/v7 completed" for a defined retention period; late arrivals are discarded or quarantined.
2. **Durable dedup:** use business keys and uniqueness constraints/conditional transitions for `SummaryPublished` output.
3. **Reconciliation:** if late results are allowed to amend outcomes, emit a versioned **correction event** instead of silently producing a duplicate summary.
4. **Expiry policy:** define handling for expired groups and post-expiry arrivals.

Spring Integration settings like `expireGroupsUponCompletion`, group timeout, and post-release group handling must be chosen and tested against your version; **never assume group state persists forever or late arrivals are rejected by default**.

## 19. Incomplete Groups: Filters, `void` Handlers, and Resultless Errors

A group can **never complete**, even with a valid correlation key.

~~~mermaid
flowchart TD
    SPLIT["Splitter: L1, L2, L3"] --> F{"Filter / worker"}
    F -->|"L1: OK"| A["Aggregator"]
    F -->|"L2: dropped"| LOST["No result"]
    F -->|"L3: OK"| A
    A --> WAIT["Only 2/3 outcomes: waiting"]
~~~

Scenarios:

- Filter drops a child without producing a substitute result.
- A `void` Service Activator performs side effects without replying.
- An exception occurs before the worker returns `LineOutcome`.
- A Kafka/AMQP message sits in retry/DLQ while Aggregator knows nothing of the outcome.
- A reply routes to the wrong channel or loses its correlation header.

If Aggregator must conclude **every member has an outcome**, turn rejections into **failure results** carrying group key and member ID, or have a coordinator mark the whole group failed. Never shrink `sequenceSize` because a message went missing: doing so can report a broken batch as successful.

**Error paths should not be treated as "some unrelated message".** If group-level status is needed, error handlers must have enough identity to correlate errors back to the original group.

## 20. Group Timeout and Partial Release Must Have Clear Semantics

Not every group can wait forever. A deadline policy is required:

| Policy | When Appropriate | Risk |
|---|---|---|
| **Fail on timeout** | Every member is mandatory | Callers need error/status instead of waiting forever |
| **Partial release** | Partial results are acceptable to business | Easily mistaken for full success |
| **Quarantine group** | Needs manual investigation and replay | Consumes storage, needs ownership |
| **Late-result correction** | Results can update later | Needs versioned output/idempotency |
| **Cancel remaining work** | When one failure invalidates the whole group | Cancellation does not guarantee dispatched tasks didn't cause side effects |

Spring Integration offers capabilities around **group timeout, expiry, and partial results**, though exact configuration depends on `AggregatorSpec`/`MessageGroupStore`/version. When enabling partial release, output must carry status like `PARTIAL`, received member count, and missing list—never return `COMPLETED` merely because time ran out.

A group status record might hold:

~~~text
groupKey        = t:tenant-a|g:PG-901|v:7
expectedLineIds = [L1, L2, L3]
receivedLineIds = [L1, L3]
missingLineIds  = [L2]
deadline        = 2026-11-21T12:00:00Z
state           = WAITING
~~~

**The deadline must be anchored to the logical work**, avoiding recalculation on every retry that would extend the group's allowed wait window indefinitely.

## 21. `MessageGroupStore`: How Long Must Group Data Live?

Aggregator can use `MessageGroupStore` to persist messages per group and group metadata. Distinguish **in-memory** from **persistent**:

| Aspect | In-Memory Store | Persistent/Shared Store |
|---|---|---|
| Simplicity, low latency | Usually good | Depends on backend |
| Survives process restart | Not guaranteed | Possible when configured properly |
| Multiple instances mutating group | Not shared naturally | Needs coordination/locking |
| Memory pressure | Grows with incomplete groups | Uses external storage yet still has cost |
| Dedup/business completion | Not built in | Still needs business-level idempotency |
| Removing group after expiry | Must configure | Must configure and test cleanup |

**A persistent store cannot fix a broken correlation key.** It can make the bug persist **longer** and affect messages after restart. If group names collide across tenants/revisions, data that should never meet will still be stored together.

In multi-node setups, examine how the framework handles **group locking, atomic updates, transactions, and release**; never assume sharing one database automatically makes two Aggregator instances safe when updating the same group concurrently. You may need a lock registry or key-partitioned ownership.

Also control retention: groups waiting forever due to missing members can occupy storage indefinitely without timeouts, expired-group handling, and cleanup.

## 22. Changing Correlation Strategy While Groups Already Exist

This is a schema/state change, not merely a code refactor.

Suppose the old version used:

~~~text
key = orderId
      → O-101
~~~

The new version uses:

~~~text
key = tenantId + processingGroupId + revision
      → t:tenant-a|g:PG-901|v:7
~~~

If `MessageGroupStore` still holds old group `O-101`, post-deploy messages may land in the new group while the old group waits forever. Worse, some nodes running old code and others running new code can place data into **two different groups** simultaneously.

Sensible migration procedure:

1. Inventory running correlation strategy versions.
2. Identify pending legacy groups and their completion/failure rules.
3. Drain or migrate state against manifests verifying tenant/revision; never rewrite keys in bulk by guesswork.
4. Introduce versioned keys and bounded rollout/cutover.
5. Monitor both versions and any mismatches during canary.
6. Delete old data only once safe conditions and audits are complete.

Never change key algorithms mid-flight expecting Aggregator to recognize two different strings as one group. For long-running workflows, you may need **version pinning** for messages emitted prior to cutover.

## 23. Header Mapping Across Brokers and Multiple JVMs

When messages travel across Kafka, AMQP, HTTP, or files:

- Some Spring headers are internal objects and **must not be arbitrarily serialized**, such as `replyChannel`.
- `correlationId` may be UUID or String depending on the mapper; when types change, canonicalize to a single format.
- `sequenceNumber` or `sequenceSize` may be missing or lose accurate semantics after restarts.
- Messages can be **redelivered**, reordered, or consumed across multiple partitions.
- Tracing headers do not replace a business group key.

A wire contract:

~~~json
{
  "tenantId": "tenant-a",
  "orderId": "O-101",
  "processingGroupId": "PG-901",
  "revision": 7,
  "lineId": "L2",
  "expectedLines": 3,
  "success": true,
  "reasonCode": null
}
~~~

This is explicit application data that can be version/schema validated at consumers. Never skip verifying **authenticated source, tenant scope, manifest membership**, and idempotency just because `processingGroupId` is in the payload.

**Never group messages by partition offset or arrival order.** Offsets identify position in a partition's log, not whether two results belong to the same logical batch. Under parallel processing, items from the same group can finish out of order.

## 24. Correlation Strategy Errors Must Route to the Error Path

A strategy may encounter:

- `processingGroupId=null`;
- malformed `tenantId`;
- `revision=0`;
- wrong payload type (`String` instead of `LineOutcome`);
- missing manifest;
- unsupported schema version.

**Never return a shared fallback key like `"UNKNOWN"` for all errored messages.** Doing so lumps unrelated messages into **one super-group**, risking data leaks or spurious releases once count is reached.

~~~mermaid
flowchart TD
    IN["LineOutcome incoming"] --> V{"Validate identity + manifest"}
    V -->|"Invalid"| ERR["Error channel / quarantine"]
    V -->|"Valid"| KEY["Compute stable group key"]
    KEY --> AG["Aggregator"]
    AG --> REL{"Release strategy"}
    REL -->|"Complete"| OUT["OrderSummary"]
    REL -->|"Incomplete"| WAIT["Persist and wait"]
~~~

Distinguish:

| Error | Auto-Retry? | Handling Suggestion |
|---|---|---|
| Missing ID or bad schema | Usually **no** | Reject, DLQ/quarantine with reason |
| Manifest not found due to eventual consistency | Short retry if contract permits | Bounded backoff, deadline |
| Group key wrong tenant | Never retry like network error | Security incident/quarantine |
| Message store temporarily unreachable | Yes | Bounded retry, preserve acks |
| Group contains conflicting metadata | Do not keep counting | Error/corruption alert, reconcile |
| Confirmed duplicate | No need to reprocess | Dedupe/ack per policy |

The error channel depends on the specific **adapter/channel/poller and error handler**. An exception in a synchronous `DirectChannel` can propagate back to the caller; in executors/brokers, it occurs after publisher dispatch and must be handled at async boundaries. Never treat `send() == true` as proof the group was correct.

## 25. Unit Testing: Keys Must Be Stable and Isolated

Test `StableGroupKey` before booting a Spring context:

~~~java
@Test
void sameLogicalWorkUsesSameKeyAcrossRetries() {
    String first = StableGroupKey.of(
        "tenant-a", "PG-901", 7);
    String retry = StableGroupKey.of(
        "tenant-a", "PG-901", 7);

    assertEquals(first, retry);
}

@Test
void revisionAndTenantNeverShareTheSameGroup() {
    String base = StableGroupKey.of(
        "tenant-a", "PG-901", 7);
    String newRevision = StableGroupKey.of(
        "tenant-a", "PG-901", 8);
    String otherTenant = StableGroupKey.of(
        "tenant-b", "PG-901", 7);

    assertNotEquals(base, newRevision);
    assertNotEquals(base, otherTenant);
    assertNotEquals(newRevision, otherTenant);
}

@Test
void rejectsMalformedCorrelationScope() {
    assertThrows(IllegalArgumentException.class,
        () -> StableGroupKey.of("tenant|other", "PG-901", 7));
    assertThrows(IllegalArgumentException.class,
        () -> StableGroupKey.of("tenant-a", null, 7));
}
~~~

Next, test the release strategy using a `SimpleMessageGroup` or a test fixture supported by your framework version. Essential tests:

| Input Group | Expectation |
|---|---|
| L1, L2 | Not released, expected=3 |
| L1, L2, L3 | Releases when identity/manifest match |
| L1, duplicate L1, L2 | Not released despite 3 messages |
| L1, L2, rogue line L99 | Does not release if manifest requires L3 |
| L1 rev7, L2 rev8 | Not same key; never merged |
| L1 tenant A, L2 tenant B | Not same key |
| Two conflicting L1 results | Conflict, never silently pick one |
| `expectedLines=2` and `3` in same group | Metadata error, no release |

If using only the illustrative release strategy in Section 11, the `L99` test exposes a limitation: **three distinct IDs yet wrong manifest**. Add membership validation before production use.

## 26. Integration Test: Interleaving Two Revisions Without Mixing

In a Spring test context, wire the Aggregator from Section 10 to `orders.line.results`, use a `QueueChannel` for `orders.completed` (test-only), and optionally use an isolated in-memory `MessageGroupStore` so state does not leak across tests.

Scenario:

~~~text
Send messages in order:
  rev7/L1
  rev8/L1
  rev7/L2
  rev8/L2
  rev8/L4
  rev7/L3

Expectation:
  Summary rev8 contains exact [L1,L2,L4]
  Summary rev7 contains exact [L1,L2,L3]
  No summary contains members from both revisions
~~~

Example test body:

~~~java
@Autowired
ApplicationContext context;

@Test
void separatesTwoRevisionsOfSameOrder() {
    MessageChannel input = context.getBean(
        "orders.line.results", MessageChannel.class);
    PollableChannel output = context.getBean(
        "orders.completed", PollableChannel.class);

    send(input, outcome("PG-901", 7, "L1", 3));
    send(input, outcome("PG-901", 8, "L1", 3));
    send(input, outcome("PG-901", 7, "L2", 3));
    send(input, outcome("PG-901", 8, "L2", 3));
    send(input, outcome("PG-901", 8, "L4", 3));
    send(input, outcome("PG-901", 7, "L3", 3));

    OrderSummary first =
        (OrderSummary) Objects.requireNonNull(
            output.receive(1_000)).getPayload();
    OrderSummary second =
        (OrderSummary) Objects.requireNonNull(
            output.receive(1_000)).getPayload();

    assertEquals(Set.of(7, 8),
        Set.of(first.revision(), second.revision()));
    assertEquals("PG-901", first.processingGroupId());
    assertEquals("PG-901", second.processingGroupId());
    assertEquals(3, first.expectedLines());
    assertEquals(3, second.expectedLines());
}

private void send(MessageChannel input, LineOutcome result) {
    assertTrue(input.send(new GenericMessage<>(result)));
}

private LineOutcome outcome(
        String groupId, int revision,
        String lineId, int expected) {
    return new LineOutcome(
        "tenant-a", "O-101", groupId,
        revision, lineId, expected, true, null);
}
~~~

**This is directional test code**; place methods inside a test class and add imports/test config. The test only proves two summaries have different revisions and right `expectedCount`; to deeply verify group contents, include the set of line IDs on `OrderSummary` or inspect/spy on `OrderSummaryProcessor`. Never use output count alone as proof groups did not mix.

For asynchronous flows, the order of the two summaries may flip: assert the set of revisions and **exact member sets** rather than assuming rev7 always finishes before rev8.

## 27. End-to-End Test Matrix: Hard-to-Spot Bugs

| Case | How to Simulate | What Must Be Proven |
|---|---|---|
| Happy path | Three lines in same group | One summary with exact member set |
| Interleaved revisions | Two revisions of same order interleaved | Two isolated summaries |
| Cross-tenant collision | Same group ID in two tenants | Never merged |
| Retry same logical work | Redeliver L2 with same group key | No wrong summary from duplicate |
| Retry with new Spring Message ID | Rebuild `GenericMessage` with same payload identity | Still same business group |
| Fresh UUID per child (anti-example) | Generate group ID inside worker | Test catches fragmented groups |
| Missing correlation | Clear `processingGroupId` | Rejected, never `UNKNOWN` key |
| Case/type normalization | Uppercase/lowercase, UUID vs. String | Canonical contract applied consistently |
| Manifest mismatch | L99 arrives instead of L3 | Does not release |
| Conflicting duplicate | L1 success and L1 failure | Conflict/reconciliation reported |
| One child dropped | Filter drops L2 | Timeout/failure result, no fake completion |
| Late reply after completion | Send duplicate after release | No extra summary beyond policy |
| Restart with pending | Persistent store + restart | Group recovers per guarantee |
| Two nodes race to aggregate | Same group hits two instances | No double-release via lock/transaction |
| Router/Transformer alters payload | One branch modifies header | Business group identity stays intact |
| Gateway timeout | One member very slow | Caller timeout does not imply group uncommitted |
| Correlation strategy upgrade | Mixed old/new key formats | Controlled migration/cutover |

**Specifically:** redelivery tests should construct **a fresh Spring `Message` with the same business group identity** to expose bugs from using framework-generated message IDs. Concurrency tests should use latches/barriers and finite timeouts, never `Thread.sleep` to infer ordering.

## 28. Observability: Spotting Signs of Misgrouping

Monitor three layers: **input identity → group state → released output**.

| Signal | What to Watch For |
|---|---|
| `aggregator.group.created.count` | Spike in group count due to keys changing per message |
| `aggregator.group.pending.count` | Many groups never reaching full members |
| `aggregator.group.age` | Groups waiting too long despite workers finishing |
| `aggregator.group.member.count` | Message count in group differs from distinct member count |
| `aggregator.group.duplicate.count` | Retries and duplicates rising |
| `aggregator.group.identity.mismatch.count` | Same group holding inconsistent metadata |
| `aggregator.group.expired.count` | Many groups timing out or getting cleaned up |
| `aggregator.group.late.count` | Replies arriving after completion |
| `aggregator.release.count` by outcome | Success/partial/failed summaries |
| `aggregator.output.duplicate.count` | Groups re-released or downstream redeliveries |
| `message.store.size` | Storage growth from pending groups |

These names are **suggested metrics**, not assertions about Spring Integration's default meters. When using Micrometer/observation, use only low-cardinality labels like `flowName`, `outcome`, and `reasonCode`; **never put dynamic group keys, `orderId`, or `tenantId` into unbounded metric tags**.

To investigate a specific group, structured logs/tracing can record:

~~~text
eventId=EV-201
groupKey=t:tenant-a|g:PG-901|v:7
memberId=L2
originalMessageId=<local messaging id>
attempt=2
expected=3
distinctReceived=2
groupState=WAITING
~~~

These values belong in **access-controlled logs/traces**, not general metric labels. If IDs contain PII or sensitive data, use hashing/aliasing and proper retention.

## 29. Runbook When a Wrong Summary Is Detected

If a customer reports an aggregated result containing data from two different revisions:

1. **Isolate:** identify `tenantId/orderId/operation/processingGroupId/revision` of the bad summary.
2. **Halt untrusted emission:** consider scoped output blocking/canarying; avoid blindly rolling back unrelated flows.
3. **Trace group key:** inspect member messages that entered the group and the key algorithm active at that time.
4. **Compare against manifest:** inspect member IDs, `expectedCount`, tenant, revision, duplicates, and missing outcomes.
5. **Inspect store/expiry:** when was the group created, does it still exist, did late arrivals recreate it?
6. **Check deployment/versions:** were instances running different versions of the correlation strategy?
7. **Assess side effects:** which actions did the wrong summary trigger in Gateway, DB, brokers, or downstream?
8. **Remediate:** fix the correlation strategy, test migration, and compensate/rebuild summaries from verified manifests.
9. **Prevent recurrence:** add tests for interleaved revisions, cross-tenant, retries, late arrivals, and duplicate results.

Never simply "wipe all groups and restart" without knowing committed business states; doing so can reprocess messages and worsen data corruption.

## 30. Hands-On Exercise: Proving Two Groups Can Never Mix

Build the **`OrderOutcomeAggregator`** application:

1. **Input:** create two `OrderWork` instances with the same `orderId=O-101` yet different `revision`s, plus an order from another tenant with the same order code.
2. **Coordinator:** assign `processingGroupId` once per logical work and persist expected line IDs.
3. **Splitter:** emit `LineWork` containing `tenantId/processingGroupId/revision/lineId/expectedLines`.
4. **Workers:** transform into `LineOutcome` with success or failure reason, preserving identity.
5. **Aggregator:** correlation strategy uses `StableGroupKey`, releases when all **member IDs** per manifest arrive, and output processor builds the summary.
6. **Interleave:** send results from both revisions and both tenants interleaved; verify no groups mix.
7. **Retry:** resend one `LineOutcome` under a different Spring message ID; ensure it does not falsely inflate member count.
8. **Error:** have one worker fail before replying; emit a failure result or policy-driven group timeout.
9. **Late arrival:** send a duplicate after completion; verify tombstone/idempotency/no duplicate output.
10. **Persistence:** if using a durable store, test restarting while a group is pending and two nodes updating the same group.
11. **Telemetry:** measure pending groups, group age, duplicates, identity mismatches, expiries, and release outcomes.
12. **Migration:** simulate switching from `orderId`-based correlation to a composite key; verify no legacy groups are abandoned.

**Completion criteria:** each summary contains only members from the right tenant, operation, `processingGroupId`, and revision; retries of the same logical work share group identity; count-based release is never fooled by duplicates; missing/late groups have explicit states; no duplicate outputs arise from expiry/restart; error channels and correlation are traceable end-to-end.

## 31. Common Mistakes

**"Using `orderId` is enough because order IDs are unique."** Not necessarily. One order can have multiple revisions/operations, and multiple tenants can reuse codes.

**"`correlationId` is `MessageHeaders.ID`, so it is always stable."** No. Those are two different concepts; framework message IDs can be regenerated.

**"Having each worker generate a UUID as group ID is even safer."** Wrong. The same logical batch gets fragmented into multiple groups if each worker generates a different key.

**"`sequenceSize=3` and `group.size()=3` mean all three lines arrived."** False when duplicates or rogue members arrive. You need unique member IDs and a manifest.

**"A shared `UNKNOWN` key for all ID-less messages prevents data loss."** Wrong—it can lump unrelated messages into a super-group.

**"A persistent `MessageGroupStore` automatically fixes collisions."** False. It only persists/coordinates state; it neither understands business rules nor repairs bad keys.

**"Changing correlation strategy during deployment doesn't affect existing groups."** False. It is an identity change that may require migration/draining.

**"Once a group releases, no late reply can arrive."** False. Broker redelivery and slow workers can still deliver; a late-arrival policy is needed.

**"If the group key matches, tenant checks aren't needed."** False. Keys can be spoofed or derived from untrusted metadata.

**"Publishing one summary means all side effects happened exactly once."** False. Business idempotency, transactions, outbox, and downstream recovery are separate concerns.

**"Enabling group timeout turns all incomplete cases into successes."** False. Timeouts must produce a business-accepted `FAILED`/`PARTIAL`/`EXPIRED` outcome.

## 32. Key Takeaways

**Unstable correlation causes misgrouped messages** in two ways: **changing keys** split one logical work into multiple incomplete groups; **overly coarse keys or collisions** merge messages from different work units and release invalid results. The second failure is especially insidious because Aggregator still emits a well-typed output carrying corrupted data.

In Spring Integration, assign a **stable group identity at the source**, preserve it through **Splitter → Transformer/Filter/Router → worker → Aggregator**, use a **correlation strategy scoped by tenant/revision/operation**, and pair it with a **release strategy verifying distinct member IDs against a manifest**. Add timeouts, completion tombstones, deduplication, `MessageGroupStore`, transactions, and observability suited to your broker/restart boundaries.

**The right key finds the right group; the right release strategy concludes at the right time; the right output processor and idempotency produce the right result.** You need all three to handle real-world message flows with retries, error channels, concurrency, and correlation.

### References

- Spring Integration Reference, **Aggregator**: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Integration Reference, **Splitter**: https://docs.spring.io/spring-integration/reference/splitter.html
- Spring Integration Reference, **Message Store**: https://docs.spring.io/spring-integration/reference/message-store.html
- Enterprise Integration Patterns, **Correlation Identifier**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/CorrelationIdentifier.html
- Enterprise Integration Patterns, **Aggregator**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/Aggregator.html
