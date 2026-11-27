# Is Sequence Size Known in Advance or Inferred?

In the **Advanced Resequencer** chapter of **SPRING_INTEGRATION_PATTERN**, a question that shapes how you design a message flow is: **does the system know in advance how many elements are in a group, or must it determine when the group ends in another way?**

In Spring Integration, the `sequenceSize` header describes **the total expected number of messages in a sequence**. It is especially useful when a Splitter breaks a job into multiple parts and Routers, Filters, Transformers, Gateways, or workers process those parts at different speeds. Aggregator and Resequencer can rely on sequence metadata to decide when a group is eligible for release; however, **you cannot treat the number of messages received so far as conclusive proof that it is the entire group**.

This article distinguishes three cases: *known accurately in advance*, *computed by the sequence producer*, and *unknowable without an explicit completion signal*. That distinction forms the foundation for designing retries, error channels, correlation, and flow testing without losing messages or waiting indefinitely.

## 1. Understanding the exact meaning of `sequenceSize`

Three headers should be viewed as a single set:

| Header | Question it answers | Example |
| --- | --- | --- |
| `correlationId` | Which messages belong to the same group? | `order-2026-42` |
| `sequenceNumber` | What is this message's position within the group? | `2` |
| `sequenceSize` | **How many messages in total** is the group expected to have? | `4` |

Suppose an order has four line items. If the source produces four messages with the same `correlationId=order-2026-42`, having `sequenceNumber=1, 2, 3, 4` respectively and `sequenceSize=4`, the Resequencer has the basis to detect missing positions and sort by the assigned numbers.

```text
Source: group G, sequenceSize = 4

Actual arrival:     #3  →  #1  →  #4  →  #2
Required positions:  1      2      3      4
Once group is full: #1  →  #2  →  #3  →  #4
```

Several principles to maintain:

- `sequenceSize` is the **expected total**, not the count received so far, the count missing, or the highest number observed.
- This value is meaningful **within the scope of a single `correlationId`**. Two different groups can both use `sequenceNumber=1`.
- When the total is known in advance, messages in the same group should carry **a consistent `sequenceSize`**, and valid positions are typically `1..sequenceSize`.
- `sequenceSize=0` may be used by some sources/Splitters to indicate **an unknown total**; an absent header should also be treated as insufficient metadata. Always check the behavior of the specific endpoint and version in use, and do not assume `0` represents a completed empty group.
- A message with `sequenceNumber=4` **does not prove** that the group has exactly four parts if `sequenceSize` is unknown: part `5` could still arrive later.

This header describes **the producer's expectation**. If the metadata is wrong, the receiving processor cannot automatically make that expectation right.

## 2. When can `sequenceSize` be known in advance?

### 2.1. The input payload is a finite collection with a known size

The simplest case is a Splitter receiving an already materialized list or array. For example:

```java
List<String> items = List.of("A", "B", "C", "D");
// The source knows items.size() == 4 accurately before splitting.
```

When a Splitter is configured to **apply sequence information** (`applySequence`), it can number the parts and attach `sequenceSize=4` to the emitted messages. This is the element count of **the actual split result**, not the number of messages that happen to arrive first downstream.

An illustrative flow using Java DSL:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
class SplitKnownBatchFlow {

    @Bean
    IntegrationFlow splitKnownBatch() {
        return IntegrationFlow.from("batchInput")
                .split()
                .channel("partsToProcess")
                .get();
    }
}
```

The example above uses a Splitter in a flow; to rely on `sequenceSize` as a contract across multiple stages, you must **verify `applySequence` and the headers at `partsToProcess`** in your actual version and configuration. When the input is a four-element list and sequencing is enabled, expect four messages in the same group with corresponding sequence numbers.

**Important limitation:** if the input data is generated dynamically, can mutate during traversal, or gets trimmed by other logic, the size of the initial structure may not equal the number of messages actually emitted.

### 2.2. A business contract provides the total upfront

An external source can also provide the exact total via a manifest, batch metadata, API, or opening record:

```json
{
  "batchId": "shipment-42",
  "partNo": 2,
  "totalParts": 4,
  "payload": "package-B"
}
```

The adapter maps `batchId → correlationId`, `partNo → sequenceNumber`, `totalParts → sequenceSize`. This approach works well for parts delivered over Kafka, RabbitMQ, HTTP, or job queues, **provided the producer guarantees `totalParts` is the total for that exact batch**.

A mapping example with input validation:

```java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public final class BatchPartMapper {

    private BatchPartMapper() { }

    public static Message<String> toMessage(
            String batchId,
            int partNo,
            int totalParts,
            String payload) {

        if (batchId == null || batchId.isBlank()) {
            throw new IllegalArgumentException("batchId is required");
        }
        if (totalParts < 1 || partNo < 1 || partNo > totalParts) {
            throw new IllegalArgumentException("Invalid sequence metadata");
        }

        return MessageBuilder.withPayload(payload)
                .setHeader(
                        IntegrationMessageHeaderAccessor.CORRELATION_ID,
                        batchId)
                .setHeader(
                        IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                        partNo)
                .setHeader(
                        IntegrationMessageHeaderAccessor.SEQUENCE_SIZE,
                        totalParts)
                .build();
    }
}
```

The receiver is simply **translating trusted metadata into Spring Integration headers**. If a source numbers from `0`, you must consistently convert to `1`-based ordering before feeding messages into the resequencing flow. If `totalParts` can be wrong or change across messages, treat that as a data-contract violation.

### 2.3. Fan-out with a deterministic branch count

A broadcasting component such as `PublishSubscribeChannel` can apply sequence metadata if `applySequence` is enabled. In that case, the sequence size can be determined from the actual number of copies/subscribers in that broadcast. You must check the exact endpoint behavior, especially when the subscriber list or acceptance conditions can change dynamically.

**Warning:** the number of registered branches, the number of branches receiving a message, and the number of final results may differ. Do not use the fan-out configuration as `sequenceSize` for final results if downstream includes Filters, processing failures, or branches that produce no output.

## 3. When is it impossible to know in advance?

Many real-world flows do not have a fixed total at the start:

| Source or operation | Why `sequenceSize` may be unknown | Appropriate design approach |
| --- | --- | --- |
| Lazily generated iterator/stream | Cannot know how many parts exist until reaching the end | Send an end signal or materialize a complete list before splitting if feasible |
| Paginated API without `totalCount` | Total number of remaining pages is unknown | Rely on last-page flag, end cursor, or a batch manifest |
| Session-based device messages | Events arrive until the session closes | Define a session-end event and a policy for waiting on late messages |
| Condition-dependent dynamic fan-out | Actual selected branches may vary | Determine the branch list before broadcasting or use a dedicated completion rule |
| Filter drops messages after Splitter | The total assigned earlier by Splitter no longer matches incoming message count | Preserve placeholders for dropped positions or explicitly re-number a new sequence |
| Retries, timeouts, transport errors | Source **knows** the total, but receiver has not gotten all parts yet | Keep the original `sequenceSize` and use retry/error handling; never shrink the total to "make it complete" |

Distinguishing the last two cases is critical: **unknown total** is different from **known total with missing elements**. If a group is declared with `sequenceSize=5` and the receiver has only seen four parts, the true total is still `5`. Changing it to `4` on the receiving side can silently lose data.

## 4. What does "inferred" mean, and where can it actually be inferred?

Three approaches are often loosely called "inferred", but their reliability varies greatly.

### Approach A — Compute the total before emitting: reliable if data is stable

The source finishes selecting elements, counts the parts, and only then assigns sequence numbers and emits them.

```mermaid
flowchart LR
    A["Read/collect data"] --> B["Finalize element list"]
    B --> C["Compute size = N"]
    C --> D["Assign correlationId, seq=1..N, size=N"]
    D --> E["Emit messages"]
    E --> F["Resequencer"]
```

This works well when the number of parts is moderate, can be materialized in memory, or has an exact count query. If data can change between counting and fetching, use a snapshot/transaction or version-locking mechanism to ensure both steps see the same set. Pre-counting can add cost, latency, and memory overhead.

### Approach B — Source learns the group ended and publishes the total: requires a completion protocol

The source can stream `#1, #2, #3` while **not yet knowing the total**, then reach the end of the stream and send a control message, such as `BatchCompleted(batchId, finalCount=3)`. The receiver must store group state and apply a **custom release strategy** based on both the completion signal and the positions received.

In this design, `finalCount=3` is **a count confirmed by the source after completion**, not a number guessed by the Resequencer from three messages on hand. The completion message must stay logically consistent with the group's parts; if it arrives before a data part due to network reordering, the system must still wait for the missing part or handle a timeout.

You can attach a trailing manifest or an "end marker", but you must specify clearly whether the marker participates in the data sequence or only marks completion, and how retried markers are handled. Do not arbitrarily include the marker in the payload `sequenceSize` unless all parties agree.

### Approach C — Receiver treats what it has seen so far as the total: unreliable

Suppose the Resequencer has only received `#1, #2, #3`. Both hypotheses—"the group has three parts" and "the group has five parts, and `#4, #5` have not arrived yet"—are consistent with current observations. Therefore:

- `group.size() = 3` only tells you **three messages are currently present**, not that `sequenceSize=3`.
- `max(sequenceNumber) = 3` only tells you **the highest position seen so far**, not that no higher position exists.
- A period of inactivity without receiving messages is only a **timeout policy**, not proof that the group is complete.
- Contiguous positions `1, 2, 3` may be enough to **release an ordered prefix** if the design allows it, but they do not confirm the entire batch is complete.

Key takeaway: to know **it is complete**, you need a commitment from the source (size/manifest/end marker) or a well-defined business completion rule.

## 5. How does this affect Resequencer and Aggregator?

**Resequencer** collects messages by correlation key to restore order before emitting them downstream as individual messages. **Aggregator** collects a group and produces an aggregated result. Both must solve the problem of **when a group is eligible for release**, even though their outputs differ.

### When `sequenceSize` is accurate

For group `G` with size `4`, if `4, 1, 3` have arrived, position `2` is missing. A strategy waiting for **the full group** should not treat the sequence as complete yet. Once `#2` arrives, it can release/complete according to configuration.

If releasing by count, watch out for **duplicate messages**: four stored messages do not necessarily mean four distinct positions. An identification and deduplication policy is still required. Sequence metadata is only useful when sequence numbers and correlation stay consistent.

### When `sequenceSize` is unknown

You cannot rely on "received all N parts" because there is no trusted N. You must explicitly choose one of the following mechanisms:

1. **Wait for a group-closing signal:** an end marker or manifest confirming the total/final part; then check for missing positions.
2. **Gradually release contiguous segments:** if business rules allow, release the ordered prefix by `sequenceNumber` and keep waiting for subsequent parts. This requires appropriate release configuration/strategy and does not by itself prove the batch is finished.
3. **Close groups by time window/watermark:** suitable for event streams with window semantics, but requires a clear policy for late-arriving data. This is a time-based business rule, not an inference of actual size.
4. **Timeout and incomplete handling:** send missing-part details to an error channel, persist the group for retry, or mark the batch incomplete per business requirements.

Never assume that an arbitrary `.resequence()` or `.aggregate()` configuration will automatically infer the total when `sequenceSize` is absent or unknown. **Release strategy, partial sequence, timeout, expiry, and `MessageGroupStore`** must be chosen and tested on the exact Spring Integration version and real runtime flow.

### Important example: Filter after Splitter

A five-part list is numbered by a Splitter:

```text
Before Filter:
#1/5    #2/5    #3/5    #4/5    #5/5

Filter intentionally drops #2:
#1/5            #3/5    #4/5    #5/5
```

If downstream still expects all `1..5`, it may wait forever for `#2`, even though no network failure occurred.

There are three sound design options, depending on requirements:

- **Keep the original sequence and emit a notice for the dropped part** (for example, a tombstone/skip event carrying the same position): suitable when position preservation and full traceability of all parts are required.
- **Filter before creating the sequence, then renumber** `1..4` with `sequenceSize=4`: suitable when only valid parts belong to the resulting batch. Use the new numbering consistently across the entire sequence.
- **Define a release rule allowing intentionally dropped positions**: only suitable if the receiver has reliable proof that the position was dropped deliberately, backed by a clear business rule.

Lowering `sequenceSize` on a few messages after the Filter while keeping numbers `1,3,4,5` creates contradictory metadata; changing `size` alone does not solve the problem.

## 6. Building a data contract and error handling

Before implementation, align the producer, broker, and receiver on:

| Clause | Details to finalize |
| --- | --- |
| Group key | `correlationId` present and unique per batch/session; do not reuse while an old group might still have late messages |
| Numbering rule | Starts at `1`, increments in business order, one position represents at most one valid part |
| Expected total | `sequenceSize > 0` if known; if unknown, specify representation and dedicated group-closing mechanism |
| When total is finalized | Before sending the first part, or via a trusted end marker/manifest |
| Drops/duplicates/losses | Filter, retry, and idempotency rules; do not renumber a retry as a new element |
| Completion and cleanup | Timeouts, expired group handling, late messages, group state persistence, and routing errors to the right channel |

Validate the following invariants at the ingestion boundary:

- A message has a valid `correlationId`; if total is known, `1 ≤ sequenceNumber ≤ sequenceSize`.
- Messages in the same group do not carry conflicting `sequenceSize` values.
- Duplicate `sequenceNumber` values must be checked against business ID/payload to prevent duplicate side effects.
- If a closing manifest exists, the count of distinct positions actually received must match the total with no gaps per sequence convention.
- Sequence headers are not stripped or unexpectedly type-converted by adapters or serialization when crossing a broker.

For sources with unknown size, you must **distinguish the states "open", "end-signaled", "complete", and "expired"**. A group with three parts in the "open" state is not equivalent to a group with three parts in the "complete" state.

## 7. Essential test cases

To test all branches, you need not only in-order arrivals, but also simulations of missing, delayed, and malformed metadata:

| Case | Inputs sharing `correlationId` | Expected behavior to verify |
| --- | --- | --- |
| Known size, out-of-order arrival | `3/3, 1/3, 2/3` | Once group is complete, output is ordered `1, 2, 3` per chosen release strategy |
| Known size, missing part | `1/4, 3/4, 4/4` | Group is not treated as complete; position `2` is tracked as missing and hits timeout |
| Unknown size | `1, 2, 3`, no end marker | Do not conclude total is `3` merely because three parts were seen |
| End marker arrives before data | `end(count=3), 2, 1, 3` | System still waits for all data per contract before completing |
| Duplicate from retry | `1/3, 2/3, 2/3, 3/3` | No duplicate business side effects; duplicate handled per policy |
| Filtered part | Splitter `1..5` then drop `2` | Apply one of the three defined Filter strategies; do not retain inconsistent metadata |
| Inconsistent size | `1/3, 2/4, 3/3` | Detect metadata conflict and route to error-handling channel |
| Two interleaved groups | `A:2/2, B:1/3, A:1/2, B:3/3, B:2/3` | Correct order within each group; do not apply one size across all groups |

In logs and metrics, track `correlationId`, `sequenceNumber`, `sequenceSize`/unknown state, distinct positions received, gaps, wait time, timeouts, retry counts, completed groups, and expired groups. These metrics help pinpoint whether a failure lies in source counting, a Filter branch, transport, or the release policy.

## 8. Checklist for choosing how to determine size

1. **Is the exact part count known before emitting?** If yes, finalize the list/batch, assign a consistent `sequenceSize`, and verify with tests.
2. **Can the source iterate to the end before knowing?** Consider counting/materializing upfront; if streaming is required, define an end marker/manifest and wait strategy.
3. **Is there a Filter or dynamic fan-out?** Determine sequence size at **the exact boundary** the Resequencer consumes, or preserve information about dropped positions.
4. **Can parts be lost/duplicated/delayed due to retries and brokers?** Keep the published total intact, count distinct positions, and enforce timeout/idempotency policies.
5. **Is partial release acceptable before knowing the group has ended?** Configure and test contiguous-segment release; never treat "released a segment" as "completed the batch".
6. **Can completion be confirmed reliably?** If not, you can only adopt a risk-accepting policy (such as a time window), not claim to have inferred the exact total.

**Conclusion:** `sequenceSize` **is known in advance** when the source has a finite list or a trusted contract publishing the total; it **can be computed** when the sequence producer finalizes the element set before emitting; and on the Resequencer side, **the exact total cannot be inferred solely from messages received so far**. For sequences of unknown size, design explicit completion signals, release strategies, timeouts, and error handling to preserve order while still detecting missing data.
