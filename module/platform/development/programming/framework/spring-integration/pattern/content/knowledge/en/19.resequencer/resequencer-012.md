# Comparing Resequencer with Aggregator

## 1. One Problem, Two Completely Different Needs

A system receives an order with three product lines. A **Splitter** emits three child messages so workers can check inventory and calculate pricing. Because one worker queries data slowly, results return in order **3 → 1 → 2** instead of **1 → 2 → 3**.

There are two business requirements:

- **Requirement A:** deliver **each individual result** to the consumer in line order 1, 2, 3 so the consumer processes sequentially.
- **Requirement B:** wait for all results, then produce **one `OrderSummary`** containing total amount and order status.

**Resequencer** solves Requirement A; **Aggregator** solves Requirement B. Both hold message-group state by correlation and have release mechanics, yet their **output contracts differ**: Resequencer re-emits **multiple separate messages in order**, whereas Aggregator produces **one combined result** from collected members.

~~~mermaid
flowchart TD
    IN["Receive results #3, #1, #2"] --> C{"What does downstream need?"}
    C -->|"Three messages in order"| R["Resequencer"]
    C -->|"One combined result"| A["Aggregator"]
    R --> M1["Message #1"]
    R --> M2["Message #2"]
    R --> M3["Message #3"]
    A --> S["OrderSummary"]
~~~

**Point to remember immediately:** a Resequencer may **wait for the complete sequence**, yet it **never turns messages into a `List` or sums them**. An Aggregator can hold an entire group in memory, yet that **does not guarantee the consumer receives individual messages in order** because Aggregator's job is not emitting individual members.

This lesson belongs to the **Resequencer** chapter of the **SPRING_INTEGRATION_PATTERN** module. It is part of learning to implement **Enterprise Integration Patterns** with Spring Integration to create loosely coupled, scalable message flows combining **Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channels, and correlation**, while testing and observing branches.

After this lesson, you will be able to pick the right pattern, understand `CORRELATION_ID`/`SEQUENCE_NUMBER`/`SEQUENCE_SIZE` headers, configure Java DSL `resequence()` and `aggregate()`, analyze partial release, timeouts, `MessageGroupStore`, duplicates, and retries, and test both output ordering and output count.

## 2. Comparison Table: Resequencer vs. Aggregator

| Criterion | Resequencer | Aggregator |
|---|---|---|
| Goal | Restore **order** of messages in a sequence | **Combine** contents/results of messages in a group |
| Input | Multiple messages with correlation and sequence | Multiple messages with correlation and completion criteria |
| Typical output | **N messages** in valid order | **One combined message** per release |
| Payload | Preserves member payloads without summing/merging | Defaults to collection of payloads; customizable via output processor |
| Ordering contract | By sequence number within group | If order matters inside summary, you must specify it |
| Grouping mechanism | Correlation strategy and `MessageGroupStore` | Correlation strategy and `MessageGroupStore` |
| Release mechanism | Wait for completion or emit contiguous prefixes if partial allowed | Release when business/sequence/group criteria are met |
| Common pitfalls | Gap `#2` stalls `#3`, wrong sequence numbers | Group mix-ups, duplicates faking group size |
| Use with Gateway expecting one reply | Usually insufficient alone | Fits if producing one reply |
| Is it a deduplicator? | No | No |
| Is it a transaction manager? | No | No |

Spring Integration documentation states directly: both endpoints use correlated groups, yet **Resequencer passes messages along ordered by `SEQUENCE_NUMBER` without transforming them**, while Aggregator combines messages.

Never interpret "Resequencer is just Aggregator plus sorting": **emitting N separate messages** vs. **emitting one summary** has completely different impacts on Gateways, backpressure, failures, and downstream side effects.

## 3. Same Three Inputs, Different Output Cardinality

Suppose we have:

~~~text
Group G-501, sequenceSize=3:

Arrival #1: M3, sequenceNumber=3, payload=LineResult(L3, 30)
Arrival #2: M1, sequenceNumber=1, payload=LineResult(L1, 10)
Arrival #3: M2, sequenceNumber=2, payload=LineResult(L2, 20)
~~~

**Resequencer** emits:

~~~text
Output 1: M1 = LineResult(L1, 10)
Output 2: M2 = LineResult(L2, 20)
Output 3: M3 = LineResult(L3, 30)

Total: 3 messages
~~~

**Aggregator** can emit:

~~~text
Output: OrderSummary(
    groupId=G-501,
    itemCount=3,
    totalAmount=60
)

Total: 1 message
~~~

The total amount **60** illustrates **application-written** logic, not a value Spring Integration computes automatically when calling `aggregate()`. With a default Aggregator, output is typically a collection of payloads; producing `OrderSummary` with `totalAmount` and business status requires an output processor or a suitable Transformer.

## 4. Correlation Identifies the Group; Sequence Identifies Position

Headers commonly appearing in both patterns:

| Header/field | Meaning | Interchangeable? |
|---|---|---|
| `correlationId` | Which messages belong to **the same group** | Can use a custom correlation strategy |
| `sequenceNumber` | **Position** in sequence, usually 1-based | Not a group key |
| `sequenceSize` | Expected total elements **if known upfront** | Not member identity |
| `MessageHeaders.ID` | ID of a specific Java/Spring message | Should not serve as logical batch ID across retries |
| `batchId`/`processingId` | A stable business execution run | Useful for brokers/replays |
| `lineId` | Identity of a single member | Useful for idempotency |

Example of two interleaved groups:

~~~text
Batch A: A1, A2, A3
Batch B: B1, B2, B3

Arrival: B2, A3, A1, B1, A2, B3

Correct per group:
  Batch A: A1, A2, A3
  Batch B: B1, B2, B3
~~~

It does not mean every A result **must emit before** every B result. Resequencer guarantees order per **properly configured correlation group**, without automatically providing **system-wide total ordering**.

If you used `sequenceNumber=1` alone as the correlation key, A1 and B1 would be grouped together. If you used `customerId` or `tenantId` alone as the key, multiple orders for the same customer/tenant would mix. Use a properly scoped group identity that remains invariant across processing steps.

## 5. Resequencer Differs from Sorting in Java

`List.sort()` requires the whole collection in the current call. A Resequencer must handle harder scenarios:

1. Messages arrive at **different times** from multiple workers.
2. Many groups exist concurrently and must remain isolated.
3. Some sequence numbers may **not have arrived yet** or may be lost.
4. Retries/broker redeliveries can produce **duplicates**.
5. `MessageGroupStore` requires timeouts, expiry, cleanup, and observability.
6. Correlation headers can be altered across Transformers/transports.

It is a **stateful correlating endpoint with an output ordering policy**, not a pure sort function. Conversely, if your data is already a complete `List` in one method and just needs sorting to sum values, Java Streams/sorting is simpler than a Resequencer endpoint.

## 6. Resequencer Flow: Wait, Then Emit Each Message

~~~mermaid
sequenceDiagram
    participant W as Workers
    participant R as Resequencer
    participant S as MessageGroupStore
    participant D as Downstream
    W->>R: M3, correlation=G, seq=3
    R->>S: Store #3, wait
    W->>R: M1, correlation=G, seq=1
    R->>S: Store #1, wait
    W->>R: M2, correlation=G, seq=2
    R->>S: Store #2, sequence complete
    R->>D: M1
    R->>D: M2
    R->>D: M3
~~~

In wait-for-complete mode (typically default `releasePartialSequences=false`), Resequencer holds the group until the release strategy is satisfied, then emits messages in sequence order. When partial release is allowed, **contiguous prefixes** can emit earlier; see section 13.

The Spring Integration Reference emphasizes Resequencer fits **relatively short sequences with few gaps**. A system with tens of thousands of groups each missing multiple positions can consume substantial memory/storage and keep waiting state open for a long time.

## 7. Aggregator Flow: Wait, Then Produce One Result

~~~mermaid
sequenceDiagram
    participant W as Workers
    participant A as Aggregator
    participant S as MessageGroupStore
    participant D as Downstream
    W->>A: M3, correlation=G, seq=3
    A->>S: Add L3
    W->>A: M1, correlation=G, seq=1
    A->>S: Add L1
    W->>A: M2, correlation=G, seq=2
    A->>S: Add L2
    Note over A: Group complete per release strategy
    A->>A: Output processor combines data
    A->>D: One OrderSummary
~~~

Aggregator must define:

- **Correlation strategy:** which group does a message belong to?
- **Release strategy:** when is enough data present to build a result?
- **Output processor:** how is the result computed or constructed from the messages?

An Aggregator can have partial aggregation/release and expiry settings; therefore "each group produces strictly one output forever" is an assumption to design and test, **not an automatic business exactly-once guarantee**.

## 8. Java Model: Same Data, Two Output Contracts

Java 17+ example:

~~~java
record LineResult(
    String batchId,
    String lineId,
    int position,
    long amountCents,
    boolean success
) {}

record BatchSummary(
    String batchId,
    int totalLines,
    long amountCents,
    int succeeded,
    int failed
) {}
~~~

- `batchId`: logical work identity; never changes on redelivery.
- `lineId`: member identity for deduplication.
- `position`: business sequence number, 1-based in this example.
- `amountCents`: illustrates money in minor units; production needs currency/scale/overflow policies.
- `success`: a structured failure outcome still counts as a **concluded** member, not a lost message.

If deterministic replays are needed, distinguish `batchId` from `revision`, `operation`, `tenantId`, and `attemptId`. Never generate a fresh ID inside each worker as the group key when multiple workers must belong to the same group.

## 9. Java DSL: Splitter → Executor → Resequencer

Spring Integration Java DSL supports `.resequence()`:

~~~java
@Configuration
@EnableIntegration
class ResequencerFlow {

    @Bean
    IntegrationFlow orderedLines(TaskExecutor lineExecutor) {
        return IntegrationFlow.from("lines.input")
            .split()
            .channel(MessageChannels.executor(lineExecutor))
            .resequence()
            .channel("lines.ordered")
            .get();
    }
}
~~~

This follows the official **Aggregators and Resequencers** documentation pattern. Input `lines.input` carries a collection/`List`; `split()` emits child messages. The executor may scramble arrival order at Resequencer. Resequencer uses sequence headers to re-emit each message to `lines.ordered` in proper order.

To run in an application:

1. Provide a suitable `TaskExecutor` bean, preferably a bounded executor.
2. Attach a real consumer to `lines.ordered` or a test `QueueChannel`.
3. Splitter must supply valid correlation/sequence metadata.
4. Define timeout/store policies if a child gets lost.

**Never assume Resequencer turns output into a `List`.** The `lines.ordered` consumer receives **multiple messages**, even though Resequencer buffered the whole group before emitting.

## 10. Java DSL: Splitter → Executor → Aggregator

If downstream only needs one combined collection result, replace Resequencer with Aggregator:

~~~java
@Configuration
@EnableIntegration
class AggregationFlow {

    @Bean
    IntegrationFlow collectedLines(TaskExecutor lineExecutor) {
        return IntegrationFlow.from("lines.input")
            .split()
            .channel(MessageChannels.executor(lineExecutor))
            .aggregate()
            .channel("lines.collected")
            .get();
    }
}
~~~

This is an **alternative** to the flow in section 9; do not register both consuming from `lines.input` unless competing consumers are explicitly intended. Default Aggregator creates one message holding a **collection of payloads**, not `BatchSummary(amountCents=...)` automatically.

When totals are needed, a subsequent step can convert the collection into a domain result, or configure Aggregator's output processor. If order inside the collection matters, sort by `position` or use matching release/processor rules; **never treat executor arrival order as business order**.

## 11. What If You Need Both Ordering and Aggregation?

You can place Resequencer before Aggregator:

~~~java
@Bean
IntegrationFlow orderedThenAggregated(TaskExecutor lineExecutor) {
    return IntegrationFlow.from("lines.input")
        .split()
        .channel(MessageChannels.executor(lineExecutor))
        .resequence()
        .aggregate()
        .channel("lines.summary.input")
        .get();
}
~~~

~~~mermaid
flowchart LR
    IN["List line items"] --> SPLIT["Splitter"]
    SPLIT --> WORK["Concurrent workers"]
    WORK --> RS["Resequencer: N ordered messages"]
    RS --> AG["Aggregator: one grouped output"]
    AG --> OUT["Batch summary"]
~~~

This topology makes sense when **an intermediate step after Resequencer must process each message in order** and a combined summary is still needed at the end. However, if you only need **one summary sorted by position**, Aggregator + sorting in the output processor is simpler, holds less state, and has lower latency.

**Crucial note:** placing Resequencer **after** workers cannot reverse the order of side effects already committed **before** it. If worker #3 wrote to the DB before worker #1, emitting 1→2→3 does not erase commit history 3→1→2.

## 12. Decision Table: Which Pattern Fits?

| Need | Use | Why |
|---|---|---|
| Send each event to a writer in exact order | Resequencer before writer | Keeps messages individual; orders emission |
| Sum totals across N lines | Aggregator | Needs one result payload |
| Return JSON containing sorted lines | Aggregator + sort in processor | No need to emit N separate messages |
| Emit audit events sequentially | Resequencer | Downstream reads each event individually |
| Gateway expects one response | Aggregator/Gather | Single-reply contract |
| Complete `List` already in one Java method | Java sort/collect | No `MessageGroupStore` needed |
| Kafka gives right per-key ordering, processed sequentially | Partition/consumer policy | Resequencer often unnecessary |
| Parallel processing then print ordered report | Resequencer → print or Aggregator + sort | Depends on whether output is per-line or full report |

**Rule:** choose based on **downstream's contract**, not merely because messages arrive out of order. If the consumer expects one summary object, sorting is an aggregation detail; if the consumer genuinely must see every event in sequence, that is Resequencer's job.

## 13. Releasing Partial Sequences: Wait for All or Emit Prefixes Early?

Resequencer provides `releasePartialSequences`, defaulting to `false` per Spring Integration reference.

Suppose a sequence has 4 messages arriving in order 3,1,4,2:

| Time | Arriving Message | `false`: wait for complete | `true`: emit contiguous prefix |
|---|---|---|---|
| T1 | `#3` | Wait | Wait because `#1` is missing |
| T2 | `#1` | Wait | Can emit **`#1`** |
| T3 | `#4` | Wait | Wait because `#2` is still missing |
| T4 | `#2` | Emit **`#1,#2,#3,#4`** | Emit **`#2,#3,#4`** |

Java DSL:

~~~java
@Bean
IntegrationFlow partialSequenceFlow() {
    return IntegrationFlow.from("parts.in")
        .resequence(r -> r.releasePartialSequences(true))
        .channel("parts.ordered")
        .get();
}
~~~

This example illustrates **contiguous prefix** behavior, not a license for Resequencer to skip gaps and emit `#3` while `#1`/`#2` are absent. Exact behavior can vary with custom release strategies, expiry, and versions; integration test against your real topology.

**Partial release does not mean business completion.** Consumers must understand emitted messages are only a prefix of the sequence; final conclusions still require a completion signal or matching sequence size/manifest.

## 14. Aggregator Also Has a Release Strategy, With Different Meaning

Example of a simple release strategy:

~~~java
.aggregate(a -> a
    .releaseStrategy(group -> group.size() == 3))
~~~

With a group receiving `#3,#1,#2`, it releases once three messages arrive and produces **one aggregate output**, rather than emitting individual messages 1, 2, 3.

Furthermore, `group.size()==3` can fail in production when broker redeliveries create:

~~~text
Group G:
  L1: attempt 1
  L1: duplicate
  L2: attempt 1

group.size()==3, yet L3 is still missing!
~~~

Therefore production must check **unique member IDs and a membership manifest**, not raw message count. Resequencer also needs duplicate/gap policies, yet its release role centers on **ordering**, whereas Aggregator centers on **business completion and combining**.

## 15. Splitter's Role in Sequence Metadata

Splitter usually assigns sequence headers to children when the source has known size:

~~~text
Original: OrderBatch(batchId=B-501, lines=[L1,L2,L3])

After Splitter (illustrating applySequence):
  L1: correlationId=G, sequenceNumber=1, sequenceSize=3
  L2: correlationId=G, sequenceNumber=2, sequenceSize=3
  L3: correlationId=G, sequenceNumber=3, sequenceSize=3
~~~

This lets Resequencer and Aggregator recognize the same group. However, never assume an unknown-size `Iterator`/`Stream` always carries `sequenceSize=3`, or that a Transformer building a new `Message<?>` manually will preserve all metadata.

With nested splits—such as Batch → Chunk → Item—there are **two logical sequence levels**. Never rely on a single pair of `correlationId`/`sequenceNumber` headers to represent both chunk sequence and item sequence if an inner endpoint overwrote metadata. Keep explicit business IDs/manifests at every level.

## 16. A Wrong Correlation Key Breaks Both Patterns

Suppose:

~~~text
Batch A: seq1, seq2, seq3
Batch B: seq1, seq2, seq3

Wrong: correlationKey = tenantId
Result can get mixed together:
  A1, B1, A2, B2, B3, A3
~~~

Resequencer cannot produce a clean 1→3 sequence if each position holds two messages from two different batches. Aggregator may mix six results or release prematurely on the first three messages.

A properly scoped key:

~~~text
groupKey = tenantId + processingGroupId + revision
~~~

Rules:

- Mint `processingGroupId` once before Splitter.
- Keep it unchanged across every child and result of the same logical work.
- Never call `UUID.randomUUID()` inside individual workers or correlation strategies.
- Include tenant/revision/operation whenever business IDs can overlap across those scopes.
- Authenticate tenant at the trust boundary rather than trusting client-supplied raw headers.
- With a persistent `MessageGroupStore`, keep key generation deterministic across retries and deployments, or plan explicit migrations.

Resequencer **is not a correlation-repair tool**. A group with mixed data does not become valid merely by sorting on sequence numbers.

## 17. Java: Creating Test Messages with Correlation and Sequence

A Java test fixture using Spring Integration headers directly:

~~~java
Message<LineResult> resultMessage(
        String groupId, int position, int size) {
    LineResult result = new LineResult(
        "B-501",
        "L-" + position,
        position,
        position * 10L,
        true);

    return MessageBuilder.withPayload(result)
        .setHeader(
            IntegrationMessageHeaderAccessor.CORRELATION_ID,
            groupId)
        .setHeader(
            IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
            position)
        .setHeader(
            IntegrationMessageHeaderAccessor.SEQUENCE_SIZE,
            size)
        .build();
}
~~~

This is a **test fixture** omitting imports. The same logical batch must share **the same correlation ID**, valid sequence numbers, and consistent `sequenceSize` when known upfront. On broker redelivery, the Spring message ID may change, yet the logical group key **must not**.

**Never use `MessageHeaders.ID` as the group key** when the goal is gathering results of the same logical work across retries/rebuilds.

## 18. Filter Drops a Child: Resequencer and Aggregator React Differently

Suppose Splitter emits `#1,#2,#3`, and a Filter drops `#2`:

~~~mermaid
flowchart LR
    S["Splitter #1,#2,#3"] --> F{"Filter"}
    F -->|"#1"| R["Resequencer / Aggregator"]
    F -->|"#2 rejected"| E["Error / reject flow"]
    F -->|"#3"| R
~~~

With **Resequencer**, if full ordering is required, `#3` cannot emit after `#1` while `#2` is missing under normal policy; partial release can emit `#1`, yet `#3` remains blocked by the gap.

With **Aggregator**, the group holds two results out of three expected members. If release requires all three outcomes, the group waits until a deadline or recovery event.

Solutions:

1. Fail the whole batch before Splitter if one invalid item cancels everything.
2. Feed a **failure outcome** for `#2` into the same sequence so the group gets an explicit conclusion.
3. Design group timeout/partial-result policies carrying `FAILED/PARTIAL` status.
4. If business rules allow skipping, define how missing positions/manifests are handled; never silently decrement `sequenceSize` on surviving messages.

**Never use `return null` from a Transformer as a placeholder**: null output is not a valid result message for Resequencer/Aggregator and can raise transformation exceptions.

## 19. Failure Result vs. Exception Producing No Reply

Define a structured outcome:

~~~java
record LineOutcome(
    String batchId,
    String lineId,
    int position,
    boolean success,
    String reasonCode
) {}
~~~

A sequence:

~~~text
LineOutcome(L1, seq=1, success=true)
LineOutcome(L2, seq=2, success=false, INVALID_SKU)
LineOutcome(L3, seq=3, success=true)
~~~

Resequencer emits **three outcomes in order**, letting the consumer decide whether to continue or halt at `#2`. Aggregator can produce **`BatchSummary(status=PARTIAL, failed=1)`** once all three have concluded.

Conversely, if a worker throws an exception without emitting a `LineOutcome`, the group can **miss a member forever**. Error channels/callers see the failure per config, yet Aggregator will not receive a reply from the error channel unless you wire an error-to-outcome flow carrying the right correlation.

## 20. Timeout and Expiry: Missing Sequence vs. Missing Group Member

| Situation | Resequencer | Aggregator |
|---|---|---|
| Missing `#2`, has `#1` and `#3` | `#3` blocked by gap if order must hold | Group missing a member |
| Deadline elapsed | Can expire, discard, or emit partial per policy | Can fail, expire, or produce partial summary |
| Reply after expiry | May discard or spawn new group depending on lifecycle | May spawn new group / duplicate output depending on lifecycle |
| Oversized group | Many buffered messages | Many payloads / uncomputed summary |
| Audit needs | Missing sequence positions | Missing business member IDs |

Spring Integration provides settings like `groupTimeout`, `sendPartialResultOnExpiry`, `expireGroupsUponCompletion`, `discardChannel`, and `MessageGroupStore`. Verify exact semantics for your actual version and endpoint. **Timeouts never conjure missing messages** and do not force remote workers to stop immediately.

For Resequencer, **partial release on expiry** can behave differently from normal contiguous-prefix release; an incomplete sequence needs status/diagnostics so downstream does not mistake it for "complete N."

## 21. `MessageGroupStore`: Both Are Stateful

Resequencer is not stateless merely because it leaves payloads unchanged:

| Issue | In-Memory Store | Persistent / Shared Store |
|---|---|---|
| Restart | Pending groups lost | Recoverable if configured properly |
| Group missing member | Held in RAM, can grow | Held in backend, needs cleanup |
| Multi-node | Not shared automatically | Needs proper locking/transactions |
| Late reply | Needs expiry/completion policy | Still needs expiry/completion policy |
| Duplicate/dedup | Not solved automatically | Not solved automatically |
| Group ID collision | Mixes immediately in RAM | Can persistently mis-group across restarts |

Resequencer holds messages waiting to emit in sequence; Aggregator holds messages or group state to build a combined result. Both require caps on pending groups, timeouts, retention, and memory/store monitoring.

**Persistent storage cannot fix wrong correlation strategies, sequence gaps, or business idempotency.** In distributed deployments, a shared store without proper locking/atomic state still risks double release.

## 22. Duplicates and Sequence Conflicts

A group receives:

~~~text
G-501:
  seq1 → L1, attempt 1
  seq1 → L1, duplicate attempt 1
  seq2 → L2
  seq3 → L3
~~~

Resequencer **is not a deduplication endpoint**; Aggregator **does not automatically enforce business-level deduplication** merely by grouping. Place idempotency where appropriate.

Key example:

~~~text
memberKey = (tenantId, batchId, revision, lineId, operation)

If identical final result exists → duplicate: ignore/ack
If conflicting result exists     → conflict: quarantine/reconcile
If none exists                   → validate then accept
~~~

Checks must use atomic persistence where side effects occur; comparing Spring message IDs alone fails when brokers reconstruct messages. Decide what happens when two results share the **same `sequenceNumber` with different `lineId`s**, or one `lineId` is assigned two positions.

If Aggregator's output requires **the exact member set**, the release strategy must compare against a manifest, not just `group.size()==expected`.

## 23. Reordering Messages Cannot Reorder Already-Committed Side Effects

Suppose worker `#3` writes to the DB before `#1` and `#2`:

~~~text
Worker #3 → DB COMMIT
Worker #1 → DB COMMIT
Worker #2 → DB COMMIT
           ↓
      Resequencer
Output:    #1, #2, #3
~~~

Output is properly ordered, yet **the DB already committed in order 3,1,2**. To guarantee ordered business transactions:

- Place Resequencer **before** order-sensitive handlers/side effects.
- Ensure channels and consumers **after Resequencer** do not scramble order again.
- Or partition/order by business key and process on a single sequential lane.
- Use versioning/fencing/idempotency so stale updates never overwrite newer ones.

If a multi-threaded `ExecutorChannel` sits **after** Resequencer, tasks can still complete out of order. Explicitly define **the boundary over which the ordering contract holds**, rather than treating ordering as an automatic property of every downstream handler.

## 24. Broker Partition Ordering vs. Resequencer

Kafka preserves ordering **within a single partition** in log order, yet provides no total order across partitions. When producers partition by entity key and consumers process sequentially, you may **not need a Resequencer**.

Resequencer adds value when:

- Branch results scramble after parallel processing.
- Messages of the same logical sequence arrive staggered across multiple transport paths.
- Downstream consumers strictly require the published business sequence order.

However, for an unbounded stream with chronic long-lived gaps, never use an unbounded `MessageGroupStore` to "patch" every gap. Spring Integration Reference recommends **short sequences with small gaps**. Consider partitioning, offsets/checkpoints, windows/epochs, or stream processing with explicit state policies.

## 25. Gateway Expecting One Reply: Aggregator Fits Better

A typical Gateway:

~~~java
@MessagingGateway(defaultRequestChannel = "order.request")
interface OrderGateway {
    BatchSummary submit(List<LineResult> lines);
}
~~~

If the flow is only **Splitter → Resequencer**, it emits **multiple messages**, not one `BatchSummary`. Gateways usually await a single reply, so lacking a gather step causes timeouts or contract-violating payloads depending on topology.

To return one summary:

~~~text
Gateway request
   → Splitter
   → Branch handlers
   → Aggregator
   → (Transformer to BatchSummary if needed)
   → one Gateway reply
~~~

If consumers genuinely want each event in order, use channels or streaming APIs rather than expecting a synchronous request–reply method to turn N Resequencer outputs into a collection.

When chaining `Gateway → Resequencer → Aggregator`, ensure reply/error headers and correlation traverse every endpoint; if a Filter drops a child, the Gateway may hang until timeout.

## 26. Java DSL or XML; There Is No `@Resequencer` Annotation

Spring Integration supports Resequencer via Java DSL `resequence()` or XML:

~~~xml
<int:channel id="parts.in"/>
<int:channel id="parts.ordered"/>

<int:resequencer
    input-channel="parts.in"
    output-channel="parts.ordered"
    release-partial-sequences="false"/>
~~~

The XML example requires the Spring Integration namespace/context and a real consumer on the output channel. Official docs note **there is no dedicated annotation support for Resequencer**: the endpoint needs no custom POJO method to process or merge payloads.

Never write `@Resequencer` assuming a built-in annotation exists analogous to `@Aggregator`. To run business logic on each message, place a Service Activator or Transformer **after** Resequencer.

## 27. Capacity and Backpressure of Both Endpoints

A group has 1,000 messages; `#1` arrives very late while `#2–#1000` have already arrived. Resequencer holds many messages before having a prefix to emit. Across thousands of such groups, buffers/stores surge.

| Limit to Design | Resequencer | Aggregator |
|---|---|---|
| Max group/sequence size | Protects buffer from long gaps | Protects aggregate memory |
| Max pending groups | Prevents too many waiting sequences | Prevents too many waiting batches |
| Deadline/group timeout | Never waits forever for missing numbers | Never waits forever for lost members |
| Bounded ingress queue | Throttles inbound rate | Throttles inbound rate |
| Per-tenant quota | Stops one tenant from monopolizing store | Stops one tenant from monopolizing store |
| Retry budget | Prevents retry storms on missing sequences | Prevents duplicate/failure amplification |
| Cleanup/tombstone | Handles late messages | Prevents double aggregation |

`releasePartialSequences(true)` shrinks buffers once contiguous prefixes exist, yet **cannot help** if `#1` stays missing long-term. Raising heap does not replace timeout/expiry/ownership strategies for groups that never complete.

Aggregator can use an accumulating output processor instead of buffering every raw payload depending on the domain, yet still must verify transactions/restarts and result accuracy. Never run an Aggregator with unbounded groups without explicit release criteria or windows.

## 28. Integration Test: Resequencer Receives 3,1,2 and Emits 1,2,3

A standalone Spring test context:

~~~java
@Configuration
@EnableIntegration
class ResequencerTestConfig {
    @Bean
    IntegrationFlow resequenceOnly() {
        return IntegrationFlow.from("test.resequence.in")
            .resequence()
            .channel("test.resequence.out")
            .get();
    }

    @Bean("test.resequence.out")
    PollableChannel resequencedOutput() {
        return new QueueChannel();
    }
}
~~~

Test using the `resultMessage()` fixture:

~~~java
@Autowired
ApplicationContext context;

@Test
void emitsThreeMessagesInSequenceOrder() {
    MessageChannel input = context.getBean(
        "test.resequence.in", MessageChannel.class);
    PollableChannel output = context.getBean(
        "test.resequence.out", PollableChannel.class);

    assertTrue(input.send(resultMessage("G-501", 3, 3)));
    assertTrue(input.send(resultMessage("G-501", 1, 3)));
    assertNull(output.receive(0));  // Sequence incomplete

    assertTrue(input.send(resultMessage("G-501", 2, 3)));
    for (int expected = 1; expected <= 3; expected++) {
        Message<?> actual = output.receive(1_000);
        assertNotNull(actual);
        LineResult part = (LineResult) actual.getPayload();
        assertEquals(expected, part.position());
        assertEquals("G-501",
            actual.getHeaders().get(
                IntegrationMessageHeaderAccessor.CORRELATION_ID));
    }
    assertNull(output.receive(0));
}
~~~

These are illustrative test snippets omitting imports and test runner boilerplate. With a `DirectChannel` into Resequencer and a `QueueChannel` at output, `receive` verifies order directly. If the real app places an executor after Resequencer, verify the **real consumer** rather than just a test queue.

## 29. Integration Test: Aggregator Produces One Collection

A **separate** test context:

~~~java
@Configuration
@EnableIntegration
class AggregatorTestConfig {
    @Bean
    IntegrationFlow aggregateOnly() {
        return IntegrationFlow.from("test.aggregate.in")
            .aggregate()
            .channel("test.aggregate.out")
            .get();
    }

    @Bean("test.aggregate.out")
    PollableChannel aggregatedOutput() {
        return new QueueChannel();
    }
}
~~~

Test:

~~~java
@Autowired
ApplicationContext context;

@Test
void emitsOneCollectionWhenGroupComplete() {
    MessageChannel input = context.getBean(
        "test.aggregate.in", MessageChannel.class);
    PollableChannel output = context.getBean(
        "test.aggregate.out", PollableChannel.class);

    input.send(resultMessage("G-502", 3, 3));
    input.send(resultMessage("G-502", 1, 3));
    assertNull(output.receive(0));

    input.send(resultMessage("G-502", 2, 3));
    Message<?> result = output.receive(1_000);
    assertNotNull(result);
    assertInstanceOf(Collection.class, result.getPayload());
    assertEquals(3, ((Collection<?>) result.getPayload()).size());
    assertNull(output.receive(0));
}
~~~

The test verifies **cardinality and payload shape**, not monetary totals or exact member contents. Add tests for custom aggregation processors verifying `batchId`, member IDs, amounts, and failures, especially with duplicates.

## 30. Testing Partial Release, Missing Messages, and Concurrency

With Resequencer in partial mode:

~~~text
Input: #3, #1, #4, #2 (sequenceSize=4)

Expected prefix progression:
  after #3 → no output yet
  after #1 → output #1
  after #4 → do not emit #4 yet
  after #2 → output #2, #3, #4
~~~

A comprehensive test matrix:

| Case | Resequencer Must Prove | Aggregator Must Prove |
|---|---|---|
| Out of order | Emits in sequence | Combines exact members |
| Missing `#2` | `#3` does not jump gap without skip policy | Does not report full success |
| Duplicate `#1` | No duplicate side effects per business policy | Does not count duplicate as new member |
| Two groups interleaved | Never mixes groups | Never builds cross-group summary |
| Inconsistent `sequenceSize` | Explicit error/expiry policy | Never releases wrongly |
| Timeout | Explicit partial/discard/expiry contract | Explicit partial/fail result contract |
| Late reply | Never spawns duplicate completed sequence | Never publishes second summary |
| Retry with new `MessageHeaders.ID` | Business group key preserved | Idempotency still holds |
| Parallel workers | Ordering holds at output boundary | Summary independent of arrival order |

Use `CountDownLatch`/barriers and bounded timeouts to control ordering rather than arbitrary `Thread.sleep`. Across brokers, test header mappers, acks/redeliveries, durable stores, and per-consumer lane ordering.

## 31. When You Need One Sorted Summary: Resequencer Is Not Always Needed

If the sole goal is one output containing ordered lines, you can sort in the processor after Aggregator:

~~~java
record OrderedBatch(
    String batchId,
    List<LineResult> orderedLines,
    long totalAmountCents
) {}

OrderedBatch summarize(Collection<LineResult> results) {
    if (results.isEmpty()) {
        throw new IllegalArgumentException("EMPTY_GROUP");
    }
    List<LineResult> ordered = results.stream()
        .sorted(Comparator.comparingInt(LineResult::position))
        .toList();

    long total = ordered.stream()
        .mapToLong(LineResult::amountCents)
        .reduce(0L, Math::addExact);

    return new OrderedBatch(
        ordered.get(0).batchId(), ordered, total);
}
~~~

This is an illustrative pure Java function; in production validate **matching tenant/batch/revision, valid positions, complete member sets, duplicate conflicts**, currency, and overflow. Unless business logic requires emitting each individual message in order, **Aggregator + sort** usually holds less state and is simpler than **Resequencer → Aggregator**.

## 32. Observability: Measuring Ordering vs. Aggregation Completion

| Suggested Metric | Resequencer | Aggregator |
|---|---|---|
| `group.pending.count` | Groups waiting on gaps | Groups waiting on members |
| `sequence.out.of.order.count` | Out-of-order inputs | Often less critical |
| `sequence.gap.count` | Unreceived positions | Check member manifest |
| `sequence.buffered.count` | Messages awaiting emission | Messages awaiting conclusion |
| `group.release.latency` | Wait time until emission | Wait time until combined result |
| `aggregation.completed.count` | Not primary output | Released summaries |
| `group.timeout.count` | Unfilled gaps | Members without outcomes |
| `group.duplicate.count` | Duplicate sequences/members | Duplicate business results |
| `group.late.count` | Messages arriving after expiry | Replies arriving after completion |
| `message.store.bytes` | Buffer/resource pressure | Aggregate state pressure |

These are **suggested metric names**, not claims about default Spring Integration meters. Use low-cardinality tags (`flow, status, reasonCode`); never put unbounded `batchId`/`correlationId` into metric tags. Specific IDs belong in structured logs/traces with appropriate retention and access controls.

When a consumer reports "message #3 never processed," determine whether `#3` is waiting on `#1`/`#2` in Resequencer, blocked in a downstream queue, or sitting in Aggregator waiting on a missing member.

## 33. Runbook When Order Is Wrong or Groups Never Complete

1. **Clarify the output contract:** need N ordered messages or one summary?
2. **Verify group keys:** do all results share the same logical batch/tenant/revision?
3. **Check sequences:** starting index, sequence size, gaps, duplicates, header types/formats.
4. **Inspect Splitter/Transformer:** were correlation headers dropped or overwritten?
5. **Inspect Filter/error channels:** was a child dropped or did an error skip emitting a failure result?
6. **Inspect GroupStore:** how long has the group existed; what are deadline and expiry settings?
7. **Inspect broker/executor:** did reordering happen before or after Resequencer?
8. **Inspect Aggregator:** did duplicates fool a count-based release strategy?
9. **Check side effects:** did commits happen before the ordering boundary?
10. **Recovery:** replay exact missing members or emit corrections per policy—never wipe whole groups and replay without verifying idempotency.

A Resequencer buffer growing continuously due to gaps is not solved merely by adding RAM. Re-examine sequence provenance, message emission/acking, and whether ordered partitions or windows fit better than long-lived groups.

## 34. Common Misconceptions

**"Resequencer is just an Aggregator with sorting."** False. It emits **individual messages**; Aggregator produces **a combined result**.

**"Waiting for the complete sequence means outputting a `List`."** False for Resequencer. Release and aggregation are two separate decisions.

**"Aggregator returns collections in business order by default."** Do not assume that with parallel workers; sort/process explicitly per contract.

**"`sequenceNumber` is a group ID."** False. Sequence numbers only have meaning inside a correlation group.

**"`MessageHeaders.ID` is durable enough across retries."** False. Messages may be reconstructed.

**"Partial release allows skipping every gap."** False. It mainly allows emitting contiguous prefixes; skipping gaps requires explicit expiry/skip policies.

**"Resequencer fixes DB commit order upstream of it."** False. It only orders messages exiting **after where it is placed**.

**"A Gateway automatically collapses N Resequencer outputs into one reply."** Not automatically; you need an Aggregator or a different streaming contract.

**"A persistent `MessageGroupStore` guarantees exactly-once."** False. You still need idempotency, locking, transactions, and late-reply policies.

**"Filter dropped message #2, so Resequencer will fill `#2` automatically."** False. You need a failure outcome or recovery/timeout.

**"Resequencer fits every infinite stream with huge gaps."** Not the recommended use case; reference docs warn about performance with many gapped sequences.

## 35. Practice Lab: Comparing Three Architectures on the Same Data

Build **`OrderLineOutcomeFlow`**:

1. **Resequencer:** send 3,1,2 and assert **3 outputs** in 1,2,3 order.
2. **Aggregator:** send the same three messages and assert **1 output** (collection/summary).
3. **Combined:** use Resequencer → Aggregator and compare against Aggregator + sorting inside the processor.
4. **Partial sequence:** enable `releasePartialSequences(true)`, send 3,1,4,2; verify prefixes.
5. **Missing member:** omit `#2`; test group timeout and policy.
6. **Filter rejection:** emit a `#2` failure result carrying valid sequence/correlation.
7. **Correlation:** send two batches A/B interleaved without mixing.
8. **Retry:** rebuild a Spring `Message` with a fresh ID yet the same logical group ID; test deduplication.
9. **Broker/Executor:** measure ordering before and after every async boundary.
10. **Gateway:** test a method returning `BatchSummary` completing only once Aggregator produces a result.
11. **Storage:** monitor memory against pending groups, gaps, and group expiry.
12. **Incident drill:** diagnose missing sequences, duplicates, wrong keys, and wrong release strategies.

**Completion criteria:** distinguish via assertions **N messages vs. one message**, never use `sequenceNumber` as correlation key, keep groups isolated, partial release never jumps gaps automatically, retries produce no duplicate side effects, and errors/expiry follow explicit policies.

## 36. Key Takeaways

**Resequencer and Aggregator both use message groups, yet pursue different goals.** Resequencer re-emits individual messages ordered by `SEQUENCE_NUMBER` within `CORRELATION_ID`; Aggregator gathers messages to produce a combined result via a release strategy and output processor.

Choose **Resequencer** when downstream must **receive each event in exact order**. Choose **Aggregator** when you need **one response, one batch result, a total sum, or a Scatter-Gather conclusion**. Combine the two endpoints only when both ordering and aggregation are genuine requirements.

A reliable Spring Integration flow must preserve **correlation/sequence metadata**, define policies for **missing gaps, duplicates, retries, timeouts, `MessageGroupStore`, idempotency, and ordering boundaries**. Proper ordering does not undo earlier side effects; reaching the expected message count does not guarantee **the right distinct members**. Always test **ordering, output cardinality, and business completion** independently.

### References

- Spring Integration Reference, **Resequencer**: https://docs.spring.io/spring-integration/reference/resequencer.html
- Spring Integration Reference, **Aggregator**: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Integration Reference, **Aggregators and Resequencers (Java DSL)**: https://docs.spring.io/spring-integration/reference/dsl/java-aggregators.html
- Spring Integration Reference, **Splitter**: https://docs.spring.io/spring-integration/reference/splitter.html
- Enterprise Integration Patterns, **Resequencer**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/Resequencer.html
- Enterprise Integration Patterns, **Aggregator**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/Aggregator.html
