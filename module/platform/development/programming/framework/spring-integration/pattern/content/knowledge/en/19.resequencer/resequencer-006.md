# Timeout When a Sequence Part Is Missing

> **Chapter:** Resequencer  
> **Module:** `SPRING_INTEGRATION_PATTERN` — practicing Enterprise Integration Patterns (EIP) with Spring Integration to build loosely coupled and extensible messaging flows; practicing Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channels, correlation, plus testing and monitoring branches. This lesson focuses on **what happens when Resequencer waits for a sequence number that never arrives**, how to set timeouts, choose termination policies, and avoid silently breaking business order.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain **Resequencer**'s role: grouping messages by correlation group and emitting them **by sequence number**, unlike Aggregator which merges contents into one result.
2. Identify **gaps**, **contiguous prefixes**, **sequence size**, **emitted/waiting items**, **late arrivals**, and **duplicates**.
3. Distinguish `releasePartialSequences(true)`, `sendPartialResultOnExpiry(true)`, `groupTimeout`, `discardChannel`, and Gateway or broker timeouts.
4. Choose among **waiting longer**, **failing/routing to reconciliation**, **emitting safe prefixes**, or **marked gap skipping** based on business risk.
5. Write a Spring Integration Java DSL `.resequence(...)` flow and understand the guarantee boundaries of `MessageGroupStore`, `TaskScheduler`, error handling, and correlation.
6. Test **out-of-order, missing head/middle/tail, timeouts, duplicates, late replies, restarts, and races near deadlines**; never confuse successful emission with business completion.
7. Design observability, backpressure, and idempotency so an incomplete sequence neither stalls the system nor executes commands out of order.

## 2. Real-World Scenario: Part #2 Has Not Arrived

A system processes shipment state-change events in order. The producer emits four events for a single workflow `shipment-901`:

~~~text
Sequence 1: CREATED
Sequence 2: VERIFIED
Sequence 3: LABEL_ISSUED
Sequence 4: HANDED_TO_CARRIER
~~~

Due to brokers, retries, or asynchronous processing, Resequencer receives them in this actual order:

~~~text
Arrival time:    t0    t1    t2       ? 
Sequence no:      3     1     4      2 missing
Expected size:    4     4     4
~~~

If the consumer applies `LABEL_ISSUED` before receiving `VERIFIED`, it may transition state without prerequisites. Resequencer restores order, yet eventually a question must be answered: **what happens if #2 never arrives?**

~~~mermaid
flowchart LR
    A["Receive #3"] --> B["Buffer #3"]
    C["Receive #1"] --> D["Emit #1 if contiguous release allowed"]
    D --> E["Waiting for #2"]
    F["Receive #4"] --> G["Buffer #3, #4"]
    G --> T{"Deadline/timeout?"}
    T -->|"No"| E
    T -->|"Yes"| P["Fail / reconcile / partial policy"]
    H["#2 arrives on time"] --> I["Emit #2 → #3 → #4"]
~~~

**There is no one-size-fits-all answer**: for a flow only displaying independent statistics, partial arriving items may still be useful; for **order-dependent state transitions**, never treat `3` as valid after `1` when `2` was lost.

## 3. What Does Resequencer Do, and How Does It Differ from Aggregator?

Both Resequencer and Aggregator require **correlation** and can use `MessageGroupStore` to buffer messages. However:

| Criterion | Resequencer | Aggregator |
| --- | --- | --- |
| Goal | **Reorder** output messages | **Combine** multiple messages into one result |
| Typical output shape | Individual messages, in sequence order | One aggregated message or group result |
| Ordering basis | `sequenceNumber` or ordering strategy | Release strategy and output processor |
| Missing-part handling | Wait for missing parts; timeout/expiry per policy | Wait for enough data to aggregate; partial aggregation per policy |
| Risk | Skipping numbers causes consumer to apply out of order | Aggregating incomplete parts while treating as complete |
| Example | Events `1,3,2` → `1,2,3` | Three inventory results → one `BatchResult` |

**Resequencer does not recreate lost parts**, does not guarantee broker once-only delivery, does not execute transactions, and does not turn an out-of-order sequence into valid business data. It only orders/buffers/emits messages **that were received** according to configured conditions.

In Spring Integration, Resequencer uses messaging `CORRELATION_ID` and `SEQUENCE_NUMBER` metadata via default and custom strategies, and can either **wait for the complete sequence** or **emit a contiguous prefix as soon as available**.

### 3.1. "Same Group" Must Have an Exact Meaning

An event for `shipment-901` in sync run `RUN-001` does not necessarily belong to the same group as a new event for the same shipment in `RUN-002`. Do not use `shipmentId` alone as the correlation key if sync/replay runs can overlap.

~~~text
businessKey = shipment-901      // business entity
executionId = RUN-001           // one sequence processing run
correlationId = RUN-001         // group key at Resequencer
operationId = cmd-991          // idempotency key when side effects exist
~~~

Correlation for **grouping parts** and idempotency for **preventing duplicate execution** serve two distinct purposes.

## 4. Sequence Metadata and Input Contract

A message may carry headers such as:

~~~text
payload: ShipmentEvent(type=LABEL_ISSUED, shipmentId=shipment-901)
headers:
  correlationId: RUN-001
  sequenceNumber: 3
  sequenceSize: 4
  businessCorrelationId: shipment-901
  schemaVersion: v1
~~~

| Metadata | Meaning | Rules to Check |
| --- | --- | --- |
| `correlationId` | Identifies the group to reorder | Non-null, never mixes executions |
| `sequenceNumber` | Position of part in sequence | Per `1..N` contract, never <= 0 or > N |
| `sequenceSize` | Expected total parts | Consistent within group, known if completion is required |
| `businessCorrelationId` | Business/log/tracing linkage | Never replaces group key or idempotency |
| `eventId` | Source event identifier | Useful for dedup across redeliveries |
| `schemaVersion` | Element representation/type | Use matching Transformer to interpret payload |
| `createdAt/deadlineAt` | Execution timestamps, if present | Generated by trusted source |

In a `Splitter`-driven flow, sequence headers can be generated by **applySequence**. Crossing HTTP, Kafka, AMQP, JMS, or custom Transformers can alter serialization/mapping. Test **the actual headers entering Resequencer**; never assume `sequenceSize` is present simply because the payload once held a list.

### 4.1. Different from Business Event Ordering

`sequenceNumber=2` is only trustworthy if it genuinely expresses business order confirmed by the producer. If a broker has three independent partitions, each using its own offsets, combining offsets from three partitions into a global sequence number **has no basis**.

To order events of an entity, use a proper numbering/version source—such as monotonically increasing `shipmentVersion` per shipment—paired with explicit gap and replay policies.

### 4.2. Never Trust Sensitive Client-Supplied Headers

If an external party can attach `sequenceSize=1` to an actual four-part sequence, the application could release prematurely. At ingress, authenticate sender permissions, verify schema/contract consistency, and map metadata from trusted sources. When needed, keep expected sequence sizes in an application-owned **execution registry**.

## 5. What Is a Gap? Distinguishing Missing Head, Middle, and Tail

Suppose `sequenceSize=5` and sequences start at 1:

| Received | Missing Pattern | Contiguous Prefix Emissible from Start | Blocked Under Strict Order |
| --- | --- | --- | --- |
| `[1,2,3,4,5]` | None | 1–5 | None |
| `[1,3,4,5]` | Missing middle: 2 | 1 | 3,4,5 |
| `[2,3,4,5]` | Missing head: 1 | None | 2,3,4,5 |
| `[1,2,3,4]` | Missing tail: 5 | 1–4 | Cannot declare complete yet |
| `[1,2,4]` | Missing middle and tail | 1–2 | 4 |
| `[]` | Nothing received | None | Everything; **group may not exist yet** |
| `[1,1,2]` | Duplicate #1 | 1–2 if duplicate handled | Needs dedup; do not count as 3 parts |

A **contiguous prefix** is a gap-free increasing sequence starting from the next expected number. If nothing has emitted yet, it must start at `1`; if emitted up to `k`, the next range must start at `k+1`.

### 5.1. Difference Between "Having Data" and "Allowed to Emit"

If `1,3,4` arrived, parts `3` and `4` exist in the buffer. Yet if downstream requires **never skipping #2**, those two messages **must not emit**. Timeouts do not alter that constraint.

### 5.2. Two Very Different Forms of "Partial"

1. **Early contiguous-prefix release:** can emit `1` before the full sequence arrives, while holding `3,4` until `2` appears. This option preserves order.
2. **Emitting buffered parts on group expiry:** if configured, can emit whatever messages are present **in numerical order** despite gaps. That means "sorted available parts," **not a complete or contiguous sequence**.

This distinction is why **releasePartialSequences** and **sendPartialResultOnExpiry** must never be used interchangeably.

## 6. Decision Table for Timeouts on Missing Parts

Business assumption: events of a shipment must apply **in exact order**, never skipping mandatory events.

| Condition | Recommended Strict Policy | Tolerant Policy (Only When Permitted) |
| --- | --- | --- |
| Full `1..N` before deadline | Emit in order, finish `COMPLETE` | Same |
| Received `1,3,4`; time left | May emit `1`, hold 3/4, demand `2` | May display "pending gap" info |
| Deadline hit, still missing `2` | **FAIL/RECONCILE**, do not emit 3/4 as complete | May emit permitted parts and **flag gap**, skip dependent side effects |
| Missing `1` from start | Wait/replay; do not apply 2/3/4 | Show raw events only with head-missing warning |
| Missing final part `N` | Earlier parts may have emitted; batch not `COMPLETE` | Report `PARTIAL/WAITING` per contract |
| Duplicate with same number | Do not count as extra part | Deduplicate with payload check |
| Same number, different payload | Quarantine/conflict; do not pick randomly | Use version/attempt only if contract specifies |
| No parts arrived | Execution-level deadline watcher emits `NO_PARTS` | Do not expect Resequencer to expire a nonexistent group |
| Missing part arrives after timeout | Late path/reconciliation; never silently scramble committed order | May emit versioned update event, not stale final |

A policy to "skip part #2 after 5 seconds" **must be a business decision**, backed by auditing, compensating/placeholder data if needed, and confirmation that consumers tolerate gaps. Never pick it merely because it is easy to implement.

## 7. Distinguishing Four Types of Timeouts

There is more than one "timeout" in a messaging system:

| Timeout | When It Starts and What It Measures | Consequence |
| --- | --- | --- |
| **Group timeout** at Resequencer | Expiry schedule of a group that already has messages | Handles buffered parts in that group |
| **`MessageGroupStoreReaper`** | Periodic scan/cleanup of groups by age/store policy | Expiry/cleanup may lag behind scan interval |
| **Request/business deadline** | From when an execution/command is created by trusted source | Enforces SLA even when **zero parts arrive** |
| **Gateway reply timeout** | Caller waiting synchronously for reply | Caller may stop waiting while sequence continues processing |
| **Channel send timeout** | Waiting to send into a bounded-capacity channel | Not a timeout waiting for missing sequence numbers |
| **External provider timeout** | Waiting on broker/HTTP/individual handler | Does not prove the receiver did not process the message |

### 7.1. Group Timeout Does Not Necessarily Start at T0

~~~text
T0    Batch RUN-001 created, deadline=T0+30s
T+10  Message #3 arrives: group created
T+20  Message #1 arrives: group updated
T+30  Business deadline must be evaluated
T+35  Message #2 arrives late
~~~

Depending on configuration/version, group timeouts may be scheduled or rescheduled when new messages arrive in the group. Therefore, **`groupTimeout(30_000L)` is not a guarantee of "exactly 30 seconds after batch creation."**

For absolute deadlines, store `deadlineAt` at execution creation, evaluate via a dedicated watcher/scheduler, and check both existing groups and executions with **zero messages**.

### 7.2. Without the First Message, No Group Exists Yet

If a source intends to produce sequence `1..4` but zero parts ever reach Resequencer, the group store **knows nothing about that execution**. Per-group timeouts cannot emit `NO_PARTS` for a group that does not exist.

An execution registry should record:

~~~text
ExecutionStarted(
  executionId="RUN-001",
  expectedSize=4,
  deadlineAt="...",
  status=OPEN
)

DeadlineWatcher at deadlineAt:
  if no parts -> SequenceTimedOut(NO_PARTS)
  if gaps -> SequenceTimedOut(MISSING_NUMBERS)
  if complete -> no-op
~~~

Watcher and Resequencer must coordinate **exactly one final decision** per execution.

## 8. Resequencer in Spring Integration: Key Properties

| Configuration | Effect | Watch Out For |
| --- | --- | --- |
| `.resequence()` | Creates Resequencer in Java DSL | Requires valid sequence headers and correlation |
| `releasePartialSequences(true)` | Allows emitting **valid contiguous prefixes** before full completion | Does **not** allow skipping gaps arbitrarily |
| `releasePartialSequences(false)` | Waits for complete condition per default sequence release | Holds groups long if one number is missing |
| `groupTimeout(...)` | Schedules framework group expiry | Not necessarily equal to ingress business deadline |
| `sendPartialResultOnExpiry(true)` | On group expiry, emits buffered parts per resequencing mechanism | May contain **gaps**; consumer must know |
| `sendPartialResultOnExpiry(false)` | Does not emit incomplete parts when group expires | Must have discard/error/notification per contract |
| `discardChannel(...)` | Receives discarded messages per configuration | Does not auto-generate a `GapReport` listing missing numbers |
| `expireGroupsUponTimeout(...)` | Controls keeping/removing group metadata after timeout | Removing too early lets late arrivals spawn new groups |
| `messageStore(...)` | Sets group storage backend | In-memory does not survive restarts |
| `taskScheduler(...)` | Scheduler for timeouts/lifecycle | Check shutdown, drift, and failures |
| `MessageGroupStoreReaper` | Periodically sweeps old groups | Must coordinate with timeouts and retention |

**Note:** method names, defaults, and lifecycle behavior may vary across Spring Integration versions. Java DSL examples below target modern Spring Integration APIs with `ResequencerSpec`; verify against your specific version before implementation. This lesson focuses on **getting missing-sequence policies right**, without running builds or deep Content QA at STEP 4 NEW.

### 8.1. Two Most Easily Confused Flags

~~~text
releasePartialSequences(true)
    -> when contiguous prefix exists (e.g., #1), allows emitting #1
    -> still holds #3, #4 because #2 is missing

sendPartialResultOnExpiry(true)
    -> upon expiry, allows emitting remaining parts in the group
    -> those parts may not form a gap-free sequence
    -> requires policy/notification so downstream does not treat it as COMPLETE
~~~

Using both flags without an explicit contract produces unpredictable behavior: output may include an early-emitted prefix plus leftover fragments on expiry, with **no guarantee all data was ever present**.

### 8.2. Resequencer Does Not Auto-Generate a "Gap Marker"

Spring Integration's Resequencer manages sequences and emits messages; it **does not automatically synthesize a business message** like:

~~~json
{
  "executionId": "RUN-001",
  "missingSequenceNumbers": [2],
  "status": "EXPIRED_WITH_GAP"
}
~~~

If such notifications are needed, build a **gap detector/deadline watcher** driven by the execution contract and observed state, then emit `SequenceGapDetected` or `SequenceFailed` on a dedicated error/reconciliation flow.

## 9. Java DSL: Flow That Does Not Emit Past Gaps

This example uses `DirectChannel` to accept messages with valid sequence headers, Resequencer configured for **contiguous partial sequence release**, and `QueueChannel` to observe output. On timeout, it does not emit messages past a gap.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
class ResequencerGapConfiguration {

    @Bean("events.resequence.in")
    DirectChannel resequenceInput() {
        return new DirectChannel();
    }

    @Bean("events.ordered.out")
    QueueChannel orderedOutput() {
        // Demo/test output: no business consumer yet.
        return new QueueChannel();
    }

    @Bean("events.expired")
    QueueChannel expiredMessages() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow reorderEvents() {
        return IntegrationFlow.from("events.resequence.in")
            .resequence(r -> r
                .releasePartialSequences(true)
                .groupTimeout(30_000L)
                .sendPartialResultOnExpiry(false)
                .discardChannel("events.expired")
                .expireGroupsUponTimeout(false))
            .channel("events.ordered.out")
            .get();
    }
}
~~~

**Intent of the illustrative configuration:** emit contiguous parts when available and **never push a gapped segment to an order-sensitive consumer** just because time ran out. Expired/discarded items must be observed and handled by a dedicated policy. `expireGroupsUponTimeout(false)` illustrates retaining metadata after timeout to help reject late replies; real retention and cleanup still need proper configuration.

Do not treat `events.expired` as an error-report channel pre-populated with `missingNumbers`: it is a **framework discard channel**. For a full gap report, use an execution registry/gap watcher as in section 12.

### 9.1. Building Messages with Sequence Headers

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

record ShipmentEvent(String shipmentId, String eventType) {}

Message<ShipmentEvent> event(int index, int total,
                             String executionId, String type) {
    return MessageBuilder
        .withPayload(new ShipmentEvent("shipment-901", type))
        .setHeader(IntegrationMessageHeaderAccessor.CORRELATION_ID,
            executionId)
        .setHeader(IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER, index)
        .setHeader(IntegrationMessageHeaderAccessor.SEQUENCE_SIZE, total)
        .setHeader("businessCorrelationId", "shipment-901")
        .build();
}
~~~

The `event(...)` method is a helper for examples/tests in its enclosing class, **not** a standalone bean. These headers are built manually for demonstration; in a production flow, producer/Splitter/adapters must align on metadata generation and trust boundaries.

### 9.2. Illustrative Timeline

~~~text
send #3 -> output empty
send #1 -> output #1 (if contiguous release is enabled)
send #4 -> output empty; #3/#4 still wait for #2
send #2 -> output #2, #3, #4 in order

If #2 does not arrive and group times out:
  already emitted #1 -> side effect of #1 cannot be rolled back automatically
  #3/#4 -> unsafe to emit in strict flow
  deadline watcher -> SequenceFailed(missing=[2]) / reconcile
~~~

**Especially important:** the output `QueueChannel` may receive emitted messages in order, yet if replaced by an `ExecutorChannel`, multi-partition broker, or multiple consumers, **business completion order** is not automatically guaranteed merely because Resequencer emitted in order.

## 10. Java DSL: When Business Rules Allow Missing Data

A reporting display that does not apply state transitions may want received messages emitted upon expiry, **in the order of available parts**.

~~~java
@Bean
IntegrationFlow reorderForBestEffortReporting() {
    return IntegrationFlow.from("reports.raw.in")
        .resequence(r -> r
            .releasePartialSequences(false)
            .groupTimeout(5_000L)
            .sendPartialResultOnExpiry(true))
        .channel("reports.bestEffort.out")
        .get();
}
~~~

This is a **separate illustrative configuration snippet**, assuming input/output channels and beans are declared elsewhere. Because `releasePartialSequences(false)`, group messages are buffered until complete or expired; `sendPartialResultOnExpiry(true)` allows **emitting currently buffered messages upon expiry**.

### 10.1. Risk of "Sorted but Incomplete"

Suppose only `2,4` arrive. Upon expiry, output may be `2,4` in ascending order. Yet `1,3` are absent; downstream **must never infer `2,4` is a complete sequence**.

To support best-effort safely, emit a **separate gap notification** from the watcher, attach `completeness=PARTIAL` to aggregated results, or let the consumer handle missing slots per contract. Resequencer does not automatically convert `SequenceGapDetected` into a business message attached to each output.

### 10.2. "Skip Gap" Must Be Explicit and Bounded

If after 5 seconds you want to skip `2` and process `3,4`, clarify:

- Is `2` a **mandatory command**?
- If `2` arrives at second 6, what happens?
- Can the consumer execute `3` without knowing `2`'s outcome?
- Is `GapSkipped(from=2,to=2)` emitted for auditing?
- Is an alert or reconciliation required before marking `COMPLETE`?

If the answers are unclear, **never enable partial release on expiry for order-dependent state workflows**.

## 11. Pure Java Model to Understand Gaps and Timeouts

Framework configurations carry scheduling and group store details. Let us isolate a small Java model to test **sequence invariants** without a Spring context.

Here, `GapBuffer` models:

- A sequence with fixed, known `total`.
- Emits only messages **contiguous from `nextExpected`**.
- Resending the same position and identical content while buffered is treated as a duplicate.
- Same position with different content → `CONFLICT` error.
- On timeout, the buffer **closes** and returns diagnostics; it **does not emit items past a gap**.
- The buffer lives in single-JVM RAM; it does not simulate multi-node storage or retries.

### 11.1. DTOs and Buffer

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

record SequencedPart(
    String executionId,
    int position,
    int total,
    String eventId,
    String value
) {
    SequencedPart {
        if (executionId == null || executionId.isBlank()
                || eventId == null || eventId.isBlank()
                || value == null || value.isBlank()
                || total < 1 || position < 1 || position > total) {
            throw new IllegalArgumentException("INVALID_PART");
        }
    }
}

record GapReport(
    int nextExpected,
    int total,
    List<Integer> buffered,
    List<Integer> missing,
    boolean complete
) {
    GapReport {
        buffered = List.copyOf(buffered);
        missing = List.copyOf(missing);
    }
}

final class GapBuffer {
    private final String executionId;
    private final int total;
    private final Map<Integer, SequencedPart> pending = new TreeMap<>();

    private int nextExpected = 1;
    private boolean closed;

    GapBuffer(String executionId, int total) {
        if (executionId == null || executionId.isBlank() || total < 1) {
            throw new IllegalArgumentException("INVALID_SEQUENCE");
        }
        this.executionId = executionId;
        this.total = total;
    }

    synchronized List<SequencedPart> accept(SequencedPart part) {
        if (closed) {
            throw new IllegalStateException("LATE_PART_AFTER_CLOSE");
        }
        if (!executionId.equals(part.executionId())
                || total != part.total()) {
            throw new IllegalArgumentException("CORRELATION_OR_SIZE_MISMATCH");
        }
        if (part.position() < nextExpected) {
            // Already emitted earlier: true eventId/idempotency must be
            // enforced by consumer or a durable store.
            return List.of();
        }

        SequencedPart old = pending.putIfAbsent(part.position(), part);
        if (old != null && !old.equals(part)) {
            throw new IllegalArgumentException("CONFLICTING_SEQUENCE_PART");
        }

        List<SequencedPart> ready = new ArrayList<>();
        while (pending.containsKey(nextExpected)) {
            ready.add(pending.remove(nextExpected));
            nextExpected++;
        }
        return List.copyOf(ready);
    }

    synchronized GapReport report() {
        List<Integer> buffered = new ArrayList<>(pending.keySet());
        List<Integer> missing = new ArrayList<>();
        for (int i = nextExpected; i <= total; i++) {
            if (!pending.containsKey(i)) {
                missing.add(i);
            }
        }
        return new GapReport(
            nextExpected, total, buffered, missing,
            nextExpected > total);
    }

    synchronized GapReport closeOnTimeout() {
        GapReport result = report();
        closed = true;
        return result;
    }
}
~~~

`GapBuffer` is a **model explaining contiguous emission and timeouts**, not a replacement for Spring Integration's `ResequencingMessageHandler` and **not** a production component. A production buffer must handle storage, locks/distributed coordination, bounded capacity, upstream acknowledgments, post-restart duplicates, monitoring, and error emission policies.

### 11.2. Simulated Scenarios

~~~java
GapBuffer buffer = new GapBuffer("RUN-001", 4);

buffer.accept(new SequencedPart("RUN-001", 3, 4, "ev-3", "LABEL"));
List<SequencedPart> first = buffer.accept(
    new SequencedPart("RUN-001", 1, 4, "ev-1", "CREATED"));
// first contains position=1

buffer.accept(new SequencedPart("RUN-001", 4, 4, "ev-4", "HANDED"));
GapReport report = buffer.report();
// report.nextExpected() == 2
// report.buffered() == [3,4]
// report.missing() == [2]

List<SequencedPart> ready = buffer.accept(
    new SequencedPart("RUN-001", 2, 4, "ev-2", "VERIFIED"));
// ready contains position=[2,3,4] in order
~~~

A timeout occurring while still waiting for `2`:

~~~java
GapBuffer waiting = new GapBuffer("RUN-GAP", 4);
waiting.accept(new SequencedPart("RUN-GAP", 1, 4, "ev-1", "CREATED"));
waiting.accept(new SequencedPart("RUN-GAP", 3, 4, "ev-3", "LABEL"));
waiting.accept(new SequencedPart("RUN-GAP", 4, 4, "ev-4", "HANDED"));

GapReport timedOut = waiting.closeOnTimeout();
// missing=[2], buffered=[3,4], complete=false
// #1 was emitted earlier; do not emit #3/#4 under strict policy.
~~~

**Distinguish "closing state" from "emitting timeout event":** `closeOnTimeout` only returns an in-JVM report. The caller must send that report to logs/metrics, reconciliation/error channels, and **atomically finalize** the execution. Do not mistake this code for a self-running scheduler.

## 12. Choosing Action on Group Expiry

Design a **strongly typed timeout outcome**, not just a logged exception.

~~~text
SequenceGapDetected
  executionId = RUN-001
  expectedSize = 4
  emittedUpTo = 1
  missingNumbers = [2]
  blockedNumbers = [3,4]
  reasonCode = GAP_TIMEOUT
  decision = RECONCILE_REQUIRED
  policyVersion = strict-sequence-v2
~~~

### 12.1. Policies with Distinct Meanings

| Policy | On Expiration | When to Use |
| --- | --- | --- |
| **STRICT_FAIL** | Do not emit parts past gap; close or suspend execution, report error/reconcile | State transitions, ledgers, prerequisite workflows |
| **CONTIGUOUS_PREFIX_ONLY** | Keep already-emitted contiguous parts; do not apply remaining; return partial diagnostic | Partial progress acceptable, yet cannot mark complete |
| **SKIP_GAP_WITH_MARKER** | Can emit post-gap messages **with missing notice** and explicit policy | Best-effort reporting independent of prerequisites |
| **REPLAY_THEN_FAIL** | Request replay of missing numbers; fail/reconcile once attempts exhaust | Source supports replay by position/event ID |

Policies can be composed: wait briefly → request replay → fail at deadline; or wait briefly → emit safe prefix → wait longer window → finally reconcile.

### 12.2. Completion Policy Must Be Pinned Per Execution

If gap skipping is allowed today and strict mode is turned on tomorrow, an already-started execution must not change semantics mid-flight without a migration rule. Store `policyVersion`, `deadlineAt`, and expected sequence size alongside the execution.

### 12.3. Retrying from Source Differs from Re-Running Handlers

To ask for `#2` again, send `ReplayRequested(executionId, missing=[2])` to the producer or an event store. However, replaying a business **command with side effects** must not mean "re-execute the command from scratch." The replay source should return the **recorded event/output**, or consumers must use idempotency keys and state lookups to avoid repeated side effects.

## 13. Late Arrivals After Timeout

Suppose a group expires at T0+30 and emits `SequenceGapDetected(missing=[2])`. At T0+31, `#2` finally arrives.

**Do not** by default:

- Put `#2` into a fresh group with the same key and emit `#2` after `#3/#4` already ran.
- Roll back committed side effects to "fix" ordering.
- Declare the sequence complete if the execution already closed as failed.
- Emit a second unversioned final outcome.

### 13.1. Closed-Group Registry / Tombstone

~~~text
Message arrives with executionId
             |
             v
    Execution state registry
             |
       +-----+------+
       |            |
      OPEN         CLOSED / EXPIRED
       |            |
    Resequencer   Late/reconcile path
       |
     Ordered flow
~~~

The state registry should define:

- `OPEN`: accept and buffer valid parts.
- `COMPLETE`: sequence fully processed per contract.
- `EXPIRED`: deadline elapsed with gaps.
- `RECONCILING`: fetching missing parts or verifying side effects.
- `UNKNOWN`: no valid execution; quarantine/reject.

Tombstones must be retained for at least the **late-arrival/replay window**, not just a single process lifetime. Purging metadata too early lets late messages recreate an empty group.

### 13.2. Race Conditions at the Timeout Boundary

~~~text
Thread A: #2 just arrived, releasing #2,#3,#4
Thread B: deadline watcher already saw missing #2
~~~

Inside one JVM, `synchronized` can protect a simple structure, yet it **does not solve multi-node coordination** or two-step non-atomic broker/DB writes.

Require a **single atomic transition** on the execution—such as `OPEN → COMPLETE` or `OPEN → EXPIRED` via transaction/CAS—plus an outbox/idempotent finalizer if exactly-once *business effects* are needed. At the messaging layer, still design for at-least-once/redelivery.

## 14. MessageGroupStore, Scheduler, and Unfinished Groups

Resequencer may hold many waiting messages in `MessageGroupStore`. A single gap can cause all trailing parts to pile up:

~~~text
Expected 1..100
Received 1,3,4,5,...,100
Missing #2
=> Buffer holds 98 parts even though only one number is missing.
~~~

This is especially dangerous with thousands of concurrent executions. In practice, Resequencer fits **relatively short sequences with few gaps**; for huge sequences with frequent gaps, consider checkpointed/partition-aware stream processing or another workflow mechanism.

| Item | Required Design |
| --- | --- |
| `MessageGroupStore` | In-memory or persistent? Must it survive restarts? |
| Task scheduler | Runs reliably and detects missed deadlines? |
| Locking | Can concurrent threads/nodes updating the same group race? |
| Group cleanup | When is completed/expired group metadata deleted? |
| Retention | How long are late replies/replays still recognized? |
| Memory quota | Max parts/bytes per group and system-wide? |
| Backpressure | How do producer/broker/consumer react under overload? |
| Replay | Is there a durable event source to request missing parts? |

### 14.1. `MessageGroupStoreReaper`

A reaper can sweep/expire groups by age and interval. However, it does not replace **deadlines measured from execution start**, and must coordinate with `groupTimeout` so two completion notices are not emitted and state is not deleted while late-reply handling runs.

Retaining completed group metadata may be necessary to **block late arrivals**; keeping it forever leaks memory/storage. Set explicit retention and monitor `oldestGroupAge`, `closedStateCount`, and `cleanupFailures`.

### 14.2. Persistence Does Not Guarantee Final Consumer Ordering

Even when Resequencer reorders accurately and uses a durable store, if output enters a multi-threaded executor where three handlers run concurrently, `#3` can still commit before `#2`.

If business logic requires ordered state transitions, downstream must **serialize by entity key**, use version checks/optimistic locking, or enforce another ordering mechanism. Resequencer only governs its **message emission** boundary.

## 15. Unit Tests for the Gap Model

Using JUnit 5 with `GapBuffer` from section 11. Tests require no Spring context and do not wait in real time.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import org.junit.jupiter.api.Test;

class GapBufferTest {

    private static SequencedPart part(int index) {
        return new SequencedPart(
            "RUN-TEST", index, 4, "event-" + index, "value-" + index);
    }

    @Test
    void releasesOnlyTheContiguousPrefix() {
        GapBuffer buffer = new GapBuffer("RUN-TEST", 4);

        assertTrue(buffer.accept(part(3)).isEmpty());

        List<SequencedPart> first = buffer.accept(part(1));
        assertEquals(List.of(1),
            first.stream().map(SequencedPart::position).toList());

        assertTrue(buffer.accept(part(4)).isEmpty());
        assertEquals(List.of(2), buffer.report().missing());
        assertEquals(List.of(3, 4), buffer.report().buffered());

        List<SequencedPart> rest = buffer.accept(part(2));
        assertEquals(List.of(2, 3, 4),
            rest.stream().map(SequencedPart::position).toList());

        assertTrue(buffer.report().complete());
        assertTrue(buffer.report().missing().isEmpty());
    }

    @Test
    void missingFirstElementBlocksAllLaterOnes() {
        GapBuffer buffer = new GapBuffer("RUN-TEST", 4);

        assertTrue(buffer.accept(part(2)).isEmpty());
        assertTrue(buffer.accept(part(3)).isEmpty());
        assertEquals(1, buffer.report().nextExpected());
        assertEquals(List.of(1, 4), buffer.report().missing());
    }

    @Test
    void timeoutPreservesEvidenceOfGapAndRejectsLatePart() {
        GapBuffer buffer = new GapBuffer("RUN-TEST", 4);
        buffer.accept(part(1));
        buffer.accept(part(3));

        GapReport timedOut = buffer.closeOnTimeout();
        assertEquals(List.of(2, 4), timedOut.missing());
        assertEquals(List.of(3), timedOut.buffered());
        assertFalse(timedOut.complete());

        assertThrows(IllegalStateException.class,
            () -> buffer.accept(part(2)));
    }

    @Test
    void duplicatePendingPartDoesNotCountTwice() {
        GapBuffer buffer = new GapBuffer("RUN-TEST", 4);
        assertTrue(buffer.accept(part(3)).isEmpty());
        assertTrue(buffer.accept(part(3)).isEmpty());

        assertEquals(List.of(3), buffer.report().buffered());
    }

    @Test
    void conflictingDuplicateIsRejected() {
        GapBuffer buffer = new GapBuffer("RUN-TEST", 4);
        buffer.accept(part(3));

        SequencedPart changed = new SequencedPart(
            "RUN-TEST", 3, 4, "different-id", "other-value");

        assertThrows(IllegalArgumentException.class,
            () -> buffer.accept(changed));
    }

    @Test
    void foreignExecutionCannotJoinThisSequence() {
        GapBuffer buffer = new GapBuffer("RUN-TEST", 4);

        assertThrows(IllegalArgumentException.class,
            () -> buffer.accept(new SequencedPart(
                "OTHER-RUN", 1, 4, "event-1", "value-1")));
    }
}
~~~

**Scope:** unit tests prove invariants of a synchronous in-JVM `GapBuffer` model. They do **not** prove Spring Integration Resequencer shares the exact lifecycle across versions, exact group timeouts, or consumer idempotency.

## 16. Spring Integration Test: Out-of-Order and Gaps

With `ResequencerGapConfiguration` from section 9, you can send messages with Splitter-like headers and observe the output queue.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(ResequencerGapConfiguration.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class ResequencerGapIntegrationTest {

    @Autowired @Qualifier("events.resequence.in")
    MessageChannel input;

    @Autowired @Qualifier("events.ordered.out")
    PollableChannel ordered;

    @Test
    void buffersOutOfOrderMessagesUntilGapIsFilled() {
        String group = "RUN-SEQ-TEST";

        assertTrue(send(group, 3));
        assertNull(ordered.receive(0));

        assertTrue(send(group, 1));
        assertEquals(1, number(ordered.receive(1000)));

        assertTrue(send(group, 4));
        assertNull(ordered.receive(0),
            "Seq 3/4 must wait while seq 2 is missing");

        assertTrue(send(group, 2));
        assertEquals(2, number(ordered.receive(1000)));
        assertEquals(3, number(ordered.receive(1000)));
        assertEquals(4, number(ordered.receive(1000)));

        assertNull(ordered.receive(0), "No extra output");
    }

    private boolean send(String group, int number) {
        return input.send(MessageBuilder
            .withPayload(new ShipmentEvent(
                "shipment-901", "EVENT-" + number))
            .setHeader(
                IntegrationMessageHeaderAccessor.CORRELATION_ID, group)
            .setHeader(
                IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER, number)
            .setHeader(
                IntegrationMessageHeaderAccessor.SEQUENCE_SIZE, 4)
            .setHeader("businessCorrelationId", "shipment-901")
            .build());
    }

    private int number(Message<?> message) {
        assertNotNull(message);
        Object raw = message.getHeaders().get(
            IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER);
        assertInstanceOf(Number.class, raw);
        return ((Number) raw).intValue();
    }
}
~~~

This tests **resequencing by message sequence headers**, not a real transport broker. If a Spring Integration version or `popSequence` setting modifies/strips sequence headers on emission, define an output contract and use a **business position** in the payload to assert order without relying on popped metadata.

### 16.1. Testing Timeouts with Dedicated Test Configuration

To test missing `#2` on group timeout, create a **test profile/config** with a short yet stable timeout and appropriate `TaskScheduler`. Do not use production 30-second timeouts in unit suites.

~~~text
Given:
  group=RUN-TIMEOUT, expected 1..4
  releasePartialSequences=true
  sendPartialResultOnExpiry=false
  configured short groupTimeout
  discard/error path observed

When:
  send #3
  send #1   -> #1 may be released
  send #4
  do not send #2
  await group expiry with bounded timeout

Then:
  #3 and #4 never appear on ordered output
  Expiry/discard behavior matches configuration/version
  Gap watchdog emits SequenceGapDetected(missing=[2])
  One execution final outcome only
~~~

This is a **test scenario**, not a claim that a scheduler was executed at STEP 4 NEW. Run integration tests on your exact Spring Integration version to verify group timing, headers, and discard semantics, especially with a persistent `MessageGroupStore`.

### 16.2. When `sendPartialResultOnExpiry(true)` Is Enabled

Use a **separate topology test**: send `#2,#4`, omit `#1,#3`, and let the group expire. Results must be handled as **best-effort partial**; the test should prove the consumer **does not mark `COMPLETE`** and the watcher reports the corresponding missing list. Never use this flow for state transitions if business rules forbid skipping.

## 17. Comprehensive Test Matrix

| Scenario | Input / Progression | What to Assert |
| --- | --- | --- |
| Happy path | `1,2,3,4` | Output 1–4, complete |
| Out-of-order | `3,1,4,2` | Output 1–4, never emit 3 before 2 |
| Missing head | `2,3,4` | Strict output never skips 1; expiry reports gap |
| Missing middle | `1,3,4` | May emit 1, yet 3/4 remain blocked |
| Missing tail | `1,2,3` | May emit prefix, never mark complete |
| Zero parts arrive | `[]` | Watcher emits `NO_PARTS`; group timer is not sole source |
| Duplicate pending | `3,3` | Never counted as two positions |
| Duplicate after release | Resend `1` | Never apply business effect a second time |
| Conflicting duplicate | Two different payloads at same position | Quarantine/error, never pick arbitrarily |
| Mismatched `sequenceSize` | One message has 5, others have 4 | Reject/alert, never release wrongly |
| Wrong correlation | Part of RUN-B enters RUN-A | Never mix executions |
| Out-of-range | position=0 or > N | Reject at ingress |
| Strict timeout | Missing 2 at deadline | Never emit 3/4 past gap |
| Partial timeout | Received 2/4, incomplete | If policy allows, receive partial and notify missing |
| Late arrival | `2` arrives after expiry | Never spawn new group or second final outcome |
| Timeout/reply race | `#2` arrives right at expiry | Exactly one finalization |
| Mid-group restart | In-memory vs. persistent store | Recovery matches contract |
| Multi-instance | Two nodes handle same group | Locking/store/ownership and dedup work |
| Output executor | Dispatched in order, consumer finishes out of order | Side-effect order preserved per key |
| Queue full | Bounded output queue | Proper send timeout/error/backpressure |
| Gateway waiting reply | Only prefix present, suffix missing | Clear reply/error, never hangs forever |
| Resequencer + Aggregator | One part dropped | Aggregator neither hangs forever nor sees false completion |
| Header mapping | Across Kafka/HTTP | Sequence metadata present with right types |

### 17.1. Also Assert Outputs That **Must Not** Emit

For Resequencer, a test checking only that `#1` came out **is not enough**. If `#2` is missing, verify `#3,#4` **do not** enter the strict consumer. Absence on the output over an appropriate test window is a vital part of the contract.

### 17.2. Testing Races Without Arbitrary `Thread.sleep`

Timeout events are notoriously flaky to test. Prefer controllable clocks/schedulers, state-machine unit tests, or bounded awaits with generous timeouts. In multi-node setups, test the real system for **exactly one final outcome**, rather than relying solely on an in-JVM buffer unit test.

## 18. Error Handling, Retry, and Idempotency

A sequence part may go missing because:

1. Producer never sent `#2`.
2. Producer sent it, but broker has not delivered it.
3. Consumer received it and failed before reaching Resequencer.
4. Adapter stripped `sequenceNumber` or `correlationId`.
5. Filter dropped the part due to bad data without emitting an error outcome.
6. Duplicates/out-of-order load exceeded buffer or message store capacity.

You cannot infer the root cause merely from `gap=[2]`.

### 18.1. Place Retries at the Right Step

- On **transient publish failure**, retry publishing with a stable event ID.
- If the **missing part exists in an event log**, request replay by position.
- If a **part has an invalid schema**, quarantine and fix the source; do not retry the same bytes forever.
- If a **downstream side effect may have committed**, check state and use idempotency; do not blindly re-send commands.
- If Resequencer times out, emit a contract **`GapDetected`/`SequenceExpired`** and route to reconciliation; do not reopen the group automatically without explicit rules.

### 18.2. Error Channels Do Not Fill Gaps Automatically

An `ErrorMessage` on an error channel carrying failure details does not magically transform into `sequenceNumber=2`. For Aggregator/Resequencer to know a part failed, the system must **actively model the outcome** within the sequence, or terminate the execution with a clear reason.

### 18.3. Splitter and Aggregator Can Depend on Sequences

~~~text
Batch -> Splitter (sequence 1..4)
      -> Async handlers
      -> Resequencer (ordered child results)
      -> Aggregator (optional: combined result)
~~~

An Aggregator waiting for all 4 parts will not release if Resequencer holds `#3,#4` due to missing `#2`, unless an appropriate timeout/release policy exists. The system may need a strongly typed **Error/Partial Result** to finish the group or return an error to the Gateway instead of waiting forever.

If results only need combining **without order dependence**, inserting Resequencer before Aggregator may be unnecessary. Avoid adding buffers and timeouts when the application does not require ordering.

## 19. Observing Gaps and Controlling Resources

A system can look healthy while silently accumulating thousands of incomplete groups. Monitor **waiting group state**, not just outbound message counts.

| Measurement Point | Information | Purpose |
| --- | --- | --- |
| Ingress | Sequence parts/second, invalid metadata | Detect faulty producers |
| Resequencer | Open groups, buffered parts, next expected | See which number is awaited |
| Gap detector | Missing positions, gap age, count by reason | Separate transient lag from lost messages |
| Timeout/expiry | Expired groups, discarded parts, partial releases | Track active policy behavior |
| `MessageGroupStore` | Size, oldest group age, cleanup lag | Enforce resource bounds |
| Replay service | Replay requests, success/failure | Verify gap recovery |
| Late path | Late parts, tombstone hits, reconciliation | Prevent reopening closed groups |
| Output consumer | Commit order, retries, idempotent dedup | Prove business validity |
| Scheduler | Deadline/check success, misfires | Prevent silent missed timeouts |

### 19.1. Logging Enough Context to Investigate a Gap

~~~json
{
  "event": "sequence_gap_timeout",
  "executionId": "RUN-001",
  "businessId": "shipment-901",
  "expectedSize": 4,
  "emittedUpTo": 1,
  "missingPositions": [2],
  "bufferedPositions": [3,4],
  "policy": "STRICT_FAIL",
  "decision": "RECONCILE_REQUIRED"
}
~~~

**Note:** Resequencer does not generate all of these fields automatically; they come from an application-designed gap detector/registry. Restrict log access; business IDs and trace IDs have high cardinality and should not be put directly into metric tags.

### 19.2. Metric Cardinality

Tags like `policyName`, `endpoint`, `outcome`, and `sourceType` have bounded value sets. `executionId`, `shipmentId`, and `messageId` usually differ per message; place them in access-controlled logs/traces rather than time-series metric tags.

### 19.3. Backpressure Is Not a Business Error

If a group misses `#2` while subsequent parts keep arriving, the buffer grows. Set quotas (`maxPendingPartsPerGroup`, `maxOpenGroups`, `maxBufferedBytes`) and explicit overload responses: pause consumers, route to dead-letter, request replay, or fail the execution. Never default to dropping the oldest part silently while accepting newer ones; that creates unrecoverable gaps.

## 20. Common Anti-Patterns

| Anti-Pattern | Consequence | How to Avoid |
| --- | --- | --- |
| Enabling `sendPartialResultOnExpiry(true)` expecting contiguous sequences | Emits gapped parts to strict consumers | Distinguish contiguous prefix from partial-on-expiry |
| Treating `groupTimeout` as a deadline from request creation | Wrong SLA calculations, especially when first part arrives late | Deadline watcher at ingress |
| Relying only on group timeout for the 0-parts case | No group exists to expire | Execution registry with deadline |
| Counting messages instead of unique sequence numbers | Duplicates fake completeness | Validate, deduplicate, check range |
| Mixing `shipmentId` with `executionId` | Two replay runs collide | Correlate per execution |
| Using `sequenceNumber` as sole business idempotency key | Step 2 of two different orders collides | Use business operation ID + entity/part ID |
| Using `HashSet` as an ordering source | Unstable, non-contractual order | Assign sequences from an authoritative source |
| Resequencer emits in order, yet parallel executors have no lock | Downstream commits out of order | Serialize per entity / version guards |
| Expiring/deleting groups and ignoring late arrivals | Spawns new group or second final outcome | Tombstones, late/reconciliation flow |
| Retrying whole batch because one part is missing | Repeats side effects on already-processed parts | Replay only missing part, idempotency |
| A Filter drops a part without recording why | Resequencer waits forever with no clue | Emit error/reject event and metrics |
| No buffer quotas | Heap/store exhaustion during prolonged gaps | Bounded state, backpressure, and timeouts |
| Treating `send()` success as handler completion | Wrong conclusions about business order | Track commits / business outcomes |
| Failing to test missing head/middle/tail | Misses critical edge cases | Full gap test matrix |
| Fixed-sleep timeout tests | Flaky CI, missed rare races | Bounded await / test scheduler |

## 21. Implementation Checklist

- [ ] Explicit sequence contract: starting index, `sequenceSize`, and execution identifier.
- [ ] `correlationId`, `sequenceNumber`, and `sequenceSize` created/validated from trusted sources.
- [ ] Resequencer used only when **ordering** is genuinely needed, not merely for "grouping."
- [ ] Clear understanding of where **contiguous prefixes release**, where **wait-all** applies, and downstream impact.
- [ ] Explicit timeout policy chosen: strict fail, prefix-only, replay, or best-effort with gap markers.
- [ ] Never assume partial-on-expiry produces a complete, gap-free sequence.
- [ ] Deadline watcher exists from execution creation, especially when zero parts arrive.
- [ ] Error/quarantine/replay path exists for missing or invalid metadata.
- [ ] Policies exist for duplicates, conflicting duplicates, out-of-range numbers, and late arrivals.
- [ ] Single atomic state transition closes execution with appropriate tombstones/retention.
- [ ] Group store/scheduler/locking/multi-node behavior designed for SLA and restarts.
- [ ] Downstream guarantees matching **execution ordering** if business rules demand it.
- [ ] Group and buffer quotas, backpressure, and `oldestGapAge` monitoring in place.
- [ ] Invariant unit tests and real Spring Integration tests verify both ordered outputs and withheld outputs.
- [ ] Never use `MessageHeaders.id` in place of business identity or idempotency keys.
- [ ] Observability avoids leaking payloads/PII and avoids high-cardinality metric tags.

## 22. Practice Exercise

An invoicing platform receives `InvoiceEvent` items with `invoiceVersion` increasing from 1 to 5:

~~~text
1: DRAFT_CREATED
2: LINE_ITEMS_CONFIRMED
3: TAX_CALCULATED
4: INVOICE_ISSUED
5: CUSTOMER_NOTIFIED
~~~

Events may suffer out-of-order delivery or redelivery; `INVOICE_ISSUED` must **not** apply before `TAX_CALCULATED` has been processed. The SLA for receiving the full sequence is 20 seconds from execution creation.

**Tasks:**

1. Design separate `executionId` and `invoiceId`; identify the source generating `sequenceNumber` and `sequenceSize`.
2. Diagram the flow `Inbound → Validate headers → Resequencer → Invoice state handler` with gap/error/replay paths.
3. Simulate arrival `[4,1,5,3]`, missing `2`; indicate which number(s) can emit in strict contiguous mode.
4. Choose `releasePartialSequences` and `sendPartialResultOnExpiry` so `#3/#4/#5` can never apply before `#2`.
5. After 20 seconds, emit `InvoiceSequenceExpired(missing=[2])` and decide whether to issue a replay request for `#2`.
6. If `#2` arrives at second 21, show how the late path/closed state handles it without producing two final outcomes.
7. Write `GapBuffer` unit tests for missing first/middle/last, duplicates, conflicting duplicates, out-of-range values, and timeouts.
8. Write `.resequence(...)` integration tests asserting both emitted order and messages **forbidden from emitting** during a gap.
9. Suppose downstream uses 4 threads and `#4` commits before `#3` despite ordered emission from Resequencer: design handler serialization/version validation.
10. At 500,000 invoice executions/day, propose quotas, persistent `MessageGroupStore`, cleanup, reaper, backpressure, and gap-age metrics.
11. If the invoice engine already issued the invoice in a prior run and the event replays, propose an idempotency key to prevent issuing twice.

**Hint:** For states with prerequisites, **waiting/replaying/failing** on missing events is safer than "skipping the gap." If late data must be displayed, use a separate **read model/projection** flagged `PARTIAL` rather than feeding it into a state-mutating handler.

## 23. Summary

**Timeout when a sequence part is missing** is more than configuring a number. It is a decision about **completeness, ordering, acceptable data loss, and behavior when a part never arrives**. Spring Integration Resequencer uses correlation and sequence metadata to emit messages in order; it can wait for completeness, emit contiguous prefixes, or handle buffered parts when a group expires per configuration. **Emitting numerically sorted messages upon expiry does not mean the sequence is complete or gap-free.**

A solid design distinguishes `releasePartialSequences` from `sendPartialResultOnExpiry`, includes a **deadline watcher** for when zero messages arrive, validates metadata, retains state/tombstones for late replies, bounds memory, uses idempotent retries/replays, and tests both expected output order *and* outputs that must stay withheld. Combine Filter/Transformer for input normalization, Router/Gateway for business branches, Splitter/Aggregator for multi-part processing, error channels, and observability so the system handles disorder **without silently misapplying dependent steps**.

**References:** Gregor Hohpe & Bobby Woolf, *Enterprise Integration Patterns* (Resequencer, Message Sequence, Correlation Identifier, Aggregator); Spring Integration Reference — [Resequencer](https://docs.spring.io/spring-integration/reference/resequencer.html), [Aggregators and Resequencers (Java DSL)](https://docs.spring.io/spring-integration/reference/dsl/java-aggregators.html), [Aggregator / Expiring Groups](https://docs.spring.io/spring-integration/reference/aggregator.html); Spring Integration Javadoc `ResequencerSpec`, `CorrelationHandlerSpec`, and `AbstractCorrelatingMessageHandler`.
