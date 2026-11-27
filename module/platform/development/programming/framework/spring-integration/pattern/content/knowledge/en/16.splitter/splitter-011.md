# Reconciling Outputs Against the Original Input

## 1. Problem Statement: What Does Splitter Produce and How Do We Spot Missing Parts?

In an order-processing system, a single message may contain multiple order lines. **Splitter** is an Enterprise Integration Patterns (EIP) pattern that breaks a large message into smaller messages so each part can be processed independently.

For example, the input is an order with three lines:

~~~text
BatchRequest(batchId=BAT-10, processingId=RUN-10)
  L-01: SKU-A × 2
  L-02: SKU-B × 1
  L-03: SKU-C × 5
~~~

After the Splitter, we expect three child messages:

~~~text
WorkItem(BAT-10, RUN-10, L-01, SKU-A, 2)
WorkItem(BAT-10, RUN-10, L-02, SKU-B, 1)
WorkItem(BAT-10, RUN-10, L-03, SKU-C, 5)
~~~

Yet once messages pass through Filters, Routers, outbound adapters, or asynchronous handlers, the system may observe:

~~~text
Result(RUN-10, L-01, SUCCESS)
Result(RUN-10, L-02, REJECTED)
Result(RUN-10, L-02, REJECTED)  // duplicate
Result(RUN-10, L-99, SUCCESS)   // not from input
// L-03: no outcome yet
~~~

**Simply counting "three or four results arrived" is not enough.** Outputs must be reconciled against the original input by **each part's identity, processing run, count, business status, and time boundary**. Two duplicate outcomes for `L-02` must never stand in for a missing outcome for `L-03`.

~~~mermaid
flowchart TD
    I["Input: L-01, L-02, L-03"] --> S[Splitter]
    S --> A[WorkItem L-01]
    S --> B[WorkItem L-02]
    S --> C[WorkItem L-03]
    A --> OA["Outcome L-01: SUCCESS"]
    B --> OB["Outcome L-02: REJECTED"]
    B -. redelivery .-> OB2["Outcome L-02: REJECTED"]
    C -. timeout .-> MISS["Outcome not yet seen"]
    OA --> R[Reconciler]
    OB --> R
    OB2 --> R
    R --> V["Missing: L-03 | Duplicate: L-02"]
~~~

Key distinction: **Splitter splits messages**, while a downstream **Reconciler/Aggregator** or business logic determines whether every part completed fully. A successful `send(...)` call does not automatically confirm business completion for every part.

This lesson belongs to the **Splitter** chapter of the `SPRING_INTEGRATION_PATTERN` module: implementing Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows combining Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation, while testing and observing each processing branch.

### Objectives

After this lesson, you will be able to:

1. Define the Splitter's **input/output contract** before writing assertions.
2. Distinguish **child messages**, **processing outcomes**, and **aggregated results**.
3. Choose stable reconciliation keys: `processingId`, `batchId`, `lineId`, instead of relying solely on position or Spring message IDs.
4. Detect missing parts, unexpected parts, duplicate outcomes, wrong runs, out-of-order arrivals, and late results.
5. Write unit tests for reconciliation logic and integration tests for Spring Integration Splitters with Java DSL/JUnit 5.
6. Combine Filter, Aggregator, Gateway, retry, error channel, and observability to avoid false completion reports.

## 2. Clarify Which Stage You Are Reconciling At

### 2.1. Three Distinct Output Layers

A Splitter produces child messages, which are then processed and eventually gathered:

~~~mermaid
flowchart LR
    I["BatchRequest: 3 items"] --> S[Splitter]
    S --> C["3 WorkItem messages"]
    C --> H[Handlers / Router / Filter]
    H --> O["0–n WorkOutcome messages"]
    O --> A[Aggregator / Reconciler]
    A --> R[BatchReport]
~~~

| Layer | What Is the "Output"? | What Can Be Asserted? |
|---|---|---|
| **A. Splitter output** | Child `Message<WorkItem>` instances. | Which parts the Splitter emitted per its splitting contract. |
| **B. Downstream outcome** | `WorkOutcome` for processed or rejected parts. | What result handlers reported for each part. |
| **C. Aggregate/report output** | `BatchReport` after combining outcomes. | Which release/reconciliation criteria the group met. |

A test intercepting messages **right after the Splitter** proves three parts were created, not that external APIs succeeded. Conversely, testing only `BatchReport` with `status=COMPLETED` can miss an Aggregator bug counting duplicates toward the target count if part identities aren't checked.

### 2.2. Splitter Contracts Can Be 1→N, 1→0, or Conditional 1→N

| Contract | Example | How to Reconcile |
|---|---|---|
| **1 input element → 1 child** | Each order line becomes one `WorkItem`. | Compare per-line IDs/fields and expected count. |
| **1 input element → multiple children** | One file split into sized windows. | Reconcile via `parentId + chunkIndex`, coverage/boundaries, not count alone. |
| **N elements → fewer elements intentionally** | Stripping blank lines before splitting. | Record filtering rule and normalized `expected` set. |
| **Potentially empty input** | Batch with zero lines. | Explicitly define empty return, rejection, or zero-child path; never stall Aggregator forever. |
| **Streaming Splitter** | Iterator/Flux instead of sized List. | Do not assume `sequenceSize` is always known; use end-of-stream/group closing or time policies. |
| **Message dropped by Filter post-split** | An item fails eligibility. | Emit `REJECTED` outcome or adjust release strategy; never treat data loss as success. |

This lesson adopts the contract **one valid order line creates exactly one `WorkItem`**, with a finite, non-empty input list. To support empty batches, streaming, one-to-many, or complex splitters, adapt the invariants accordingly.

### 2.3. "Dispatched" Differs from "Finished Processing"

With `DirectChannel` and synchronous handlers, sending can encompass the handler's execution time. With `ExecutorChannel`, `QueueChannel`/poller, or a broker, sending may only confirm **acceptance**; handlers can run later, retry, or fail.

Therefore, name metrics and events distinctly:

~~~text
SPLIT_CHILD_CREATED   // child created by Splitter
CHILD_DISPATCHED      // sent per channel contract
CHILD_PROCESSING_DONE // processed by handler
CHILD_OUTCOME_STORED  // outcome persisted per contract
BATCH_RECONCILED      // reconciled against completion criteria
~~~

Never share one generic `processedCount` across all these milestones.

## 3. Per-Part Identity: The Key to Reconciliation

### 3.1. Do Not Use Position as the Sole Identity

Suppose the input is:

~~~text
index 0: L-01, SKU-A
index 1: L-02, SKU-B
index 2: L-03, SKU-C
~~~

Under parallel execution, outcomes may arrive as `L-03, L-01, L-02`. Comparing `output[0]` to `input[0]` reports mismatches even when all three are valid. **Outcome arrival order does not necessarily match input order.**

Recommended separation:

- `batchId`: business batch identifier.
- `processingId`: identity of **one processing run** of the batch; distinguishes replays, whole-batch retries, or concurrent workflows.
- `lineId`: identity of **one original line in the batch**.
- `item/attemptId`: ID of a specific execution attempt when per-line retries/redeliveries occur.
- `correlationId`: infrastructure header used to group related messages; must propagate across steps if Aggregator relies on it.
- `MessageHeaders.ID`: Spring message identifier; changes when building new messages and never replaces `lineId`.

### 3.2. Example Lineage Across Components

~~~text
BatchRequest:
  batchId=BAT-10
  processingId=RUN-10
  lineId=L-02

Child WorkItem:
  batchId=BAT-10
  processingId=RUN-10
  lineId=L-02

WorkOutcome:
  batchId=BAT-10
  processingId=RUN-10
  lineId=L-02
  status=REJECTED
~~~

If an outbound adapter reconstructs a message, `MessageHeaders.ID` may be fresh. Yet business lineage must still prove the outcome belongs to the right **batch/processing/line**. Do not rely solely on correlation headers if transports can strip them without verified mapping.

### 3.3. Common Identity Mistakes

| Mistake | Example | Consequence |
|---|---|---|
| Duplicate `lineId` in input | Two lines both carry `L-02`. | Unclear which line an outcome represents. |
| Duplicate outcome | `L-02` has two outcomes due to redelivery. | Can falsely reach count `N`. |
| Unexpected outcome | `L-99` absent from input. | Can contaminate the wrong batch. |
| Wrong `processingId` | Outcome from `RUN-09` arrives in `RUN-10`. | Stale replay counted as fresh result. |
| Mutating `lineId` in Transformer | Input `L-02`, output `L02`. | Reconciliation fails without stable mapping. |
| Returning outcomes without `batchId` | Only SKU and quantity remain. | Cannot trace origin when multiple batches share SKUs. |
| Using `sequenceNumber` as business ID | Sequence 1 across multiple batches. | Mixes messages between groups. |

When inbound lines lack upstream IDs, generate a stable ID from **batch + input index** at the trusted boundary, persist the mapping, and guard against input reordering. Never use an incidental `HashMap` iteration order as a business identity.

## 4. Essential Reconciliation Invariants

Define `I` as the expected line ID set of a valid input, and `O` as the multiset of observed outcomes matching `batchId` and `processingId`.

| Invariant | Meaning |
|---|---|
| **Completeness** | Every ID in `I` has an outcome per contract. |
| **No unexpected ID** | No line ID in `O` falls outside `I`. |
| **No duplicates** | One line does not have multiple final outcomes when the contract specifies 1 outcome/line. |
| **Correct lineage** | Every outcome matches the exact batch and processing ID. |
| **Payload integrity** | Child preserves `sku`/`quantity` from input, barring intentional mapped transformations. |
| **Business success** | All eligible outcomes reached success — distinct from completeness. |
| **Stable correlation** | Results assemble into the right group even across adapters/threads. |
| **Order** | Enforced only if contract requires; when needed, verify via `lineId` or input index. |

### 4.1. Complete Is Not the Same as Successful

Example:

~~~text
Input:      {L-01, L-02, L-03}
Output IDs: {L-01, L-02, L-03}
Statuses:   SUCCESS, REJECTED, SUCCESS

structurallyComplete = true
allSucceeded        = false
~~~

Conversely:

~~~text
Input:      {L-01, L-02, L-03}
Output IDs: {L-01, L-01, L-02}

structurallyComplete = false
allSucceeded        = false
missing            = {L-03}
duplicates         = {L-01}
~~~

An Aggregator counting only `sequenceSize=3` and receiving three messages can **release erroneously** if duplicates and missing items aren't caught by group rules. Sequence headers are helpful, yet **you must verify the contract and outcome identities**.

### 4.2. Is "Zero Output" Allowed?

With a Filter after Splitter, a part may be dropped per policy. Decide explicitly:

1. **Emit `WorkOutcome(REJECTED)`:** reconciliation sees the line was evaluated and rejected; structurally complete even though not all succeeded.
2. **Allow intentional drops:** snapshot dropped IDs and update expected sets/release policies under verification.
3. **Disallow drops:** every part requires a success/failure outcome; silence means missing and triggers timeout/recovery.

Never assume "fewer outputs than inputs" is always an error, nor assume a missing message always means a business rejection. **The input–output contract defines the interpretation.**

## 5. Java Model: Preserving Original Input and Per-Part Lineage

Examples target **Java 17+, Spring Boot 3.x, Spring Integration 6.x**. Types shared across snippets are assumed to be in the same package; `public` types belong in their own files in a real project.

### 5.1. Immutable Input

~~~java
import java.util.List;
import java.util.Objects;

record OrderLine(String lineId, String sku, int quantity) {
    OrderLine {
        if (lineId == null || lineId.isBlank()
                || sku == null || sku.isBlank()
                || quantity <= 0) {
            throw new IllegalArgumentException("INVALID_ORDER_LINE");
        }
    }
}

record BatchRequest(
        String batchId,
        String processingId,
        List<OrderLine> lines) {
    BatchRequest {
        if (batchId == null || batchId.isBlank()
                || processingId == null || processingId.isBlank()) {
            throw new IllegalArgumentException("INVALID_BATCH_ID");
        }
        Objects.requireNonNull(lines, "lines");
        lines = List.copyOf(lines);
        if (lines.isEmpty()) {
            throw new IllegalArgumentException("EMPTY_BATCH");
        }
        long uniqueLines = lines.stream()
                .map(OrderLine::lineId)
                .distinct()
                .count();
        if (uniqueLines != lines.size()) {
            throw new IllegalArgumentException("DUPLICATE_INPUT_LINE_ID");
        }
    }
}
~~~

**Why copy `lines`?** If a caller mutates an `ArrayList` after submitting the batch, the reconciliation expected set could drift while child messages are in flight. `List.copyOf` snapshots the **container** immutably; here `OrderLine` is a record of immutable fields. If nested components are mutable POJOs/Lists/arrays, make deeper defensive copies per contract.

Empty batches are **intentionally rejected** in this lesson. Another application might allow zero-child batches and return an empty success report; if so, add Aggregator/reply semantics for that case instead of leaving Gateways hanging.

### 5.2. Child Message Carrying Original Lineage

~~~java
record WorkItem(
        String batchId,
        String processingId,
        String lineId,
        String sku,
        int quantity) {}

final class BatchSplitterPolicy {
    List<WorkItem> split(BatchRequest input) {
        return input.lines().stream()
                .map(line -> new WorkItem(
                        input.batchId(),
                        input.processingId(),
                        line.lineId(),
                        line.sku(),
                        line.quantity()))
                .toList();
    }
}
~~~

Each `WorkItem` carries **business lineage** for post-processing reconciliation. Replicating key ID fields does not replace Splitter-created `correlationId`/`sequenceNumber` metadata, yet keeps downstream able to reconcile even across adapters with custom header mapping.

### 5.3. Outcome with Explicit Status

~~~java
enum WorkStatus {
    SUCCESS,
    REJECTED,
    FAILED
}

record WorkOutcome(
        String batchId,
        String processingId,
        String lineId,
        WorkStatus status) {
    WorkOutcome {
        Objects.requireNonNull(batchId, "batchId");
        Objects.requireNonNull(processingId, "processingId");
        Objects.requireNonNull(lineId, "lineId");
        Objects.requireNonNull(status, "status");
    }
}
~~~

A `FAILED` outcome **is still an outcome with an ID**, letting reconciliation see which part terminated in failure. If a handler throws **without emitting an outcome**, that part stays missing until an error/recovery policy creates an outcome or the deadline expires.

### 5.4. Do Not Conclude Completeness from Output Count Alone

~~~java
// Insufficient to prove completeness:
boolean complete = outcomes.size() == input.lines().size();
~~~

A sound check verifies **IDs, group membership, duplicates, missing items, and statuses**, not just list length. Subsequent sections implement reconciliation and test each case.

## 6. Algorithm to Reconcile One Input Batch with Multiple Outcomes

### 6.1. Report Separating Completeness and Success

We need two distinct flags:

- `structurallyComplete`: every input line ID has **exactly one** outcome, no unexpected IDs exist, and no outcomes belong to another batch/processing run.
- `allSucceeded`: structurally complete **and** every status is `SUCCESS`.

Beyond those flags, the report pinpoints **which lines are missing, unexpected, duplicated, or foreign**.

~~~java
import java.util.List;
import java.util.Map;

record BatchReconciliation(
        String batchId,
        String processingId,
        List<String> missingLineIds,
        List<String> unexpectedLineIds,
        List<String> duplicateLineIds,
        List<String> foreignResults,
        Map<String, WorkStatus> firstStatusByLine,
        boolean structurallyComplete,
        boolean allSucceeded) {}
~~~

In production, you might add `observedAt`, deadline, retry count, authoritative final result, and pending status. This illustrative report reconciles **the set of outcomes received at invocation time**; it does not block waiting for unarrived replies.

### 6.2. Reconciler Independent of Spring Integration

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

final class BatchReconciler {

    BatchReconciliation reconcile(
            BatchRequest original,
            Collection<WorkOutcome> observed) {

        Objects.requireNonNull(original, "original");
        Objects.requireNonNull(observed, "observed");

        Set<String> expected = new LinkedHashSet<>();
        for (OrderLine line : original.lines()) {
            expected.add(line.lineId());
        }

        Map<String, Integer> counts = new LinkedHashMap<>();
        Map<String, WorkStatus> firstStatus = new LinkedHashMap<>();
        List<String> foreign = new ArrayList<>();

        for (WorkOutcome outcome : observed) {
            Objects.requireNonNull(outcome, "outcome");

            boolean sameBatch =
                    original.batchId().equals(outcome.batchId());
            boolean sameProcessing =
                    original.processingId().equals(
                            outcome.processingId());

            if (!sameBatch || !sameProcessing) {
                foreign.add(
                        outcome.batchId() + "/"
                        + outcome.processingId() + "/"
                        + outcome.lineId());
                continue;
            }

            counts.merge(outcome.lineId(), 1, Integer::sum);
            firstStatus.putIfAbsent(
                    outcome.lineId(), outcome.status());
        }

        List<String> missing = expected.stream()
                .filter(id -> !counts.containsKey(id))
                .toList();

        List<String> unexpected = counts.keySet().stream()
                .filter(id -> !expected.contains(id))
                .toList();

        List<String> duplicates = counts.entrySet().stream()
                .filter(entry -> entry.getValue() > 1)
                .map(Map.Entry::getKey)
                .toList();

        boolean complete = missing.isEmpty()
                && unexpected.isEmpty()
                && duplicates.isEmpty()
                && foreign.isEmpty();

        boolean successful = complete
                && expected.stream().allMatch(id ->
                        firstStatus.get(id) == WorkStatus.SUCCESS);

        return new BatchReconciliation(
                original.batchId(),
                original.processingId(),
                missing,
                unexpected,
                duplicates,
                List.copyOf(foreign),
                Map.copyOf(firstStatus),
                complete,
                successful);
    }
}
~~~

### 6.3. Step-by-Step Walkthrough of the Algorithm

1. The `expected` set comes from the **validated input**. Never reconstruct expected inputs from arrived outputs, or missing outputs can never be detected.
2. Outcomes with mismatched `batchId` or `processingId` go to `foreign`; never count them as valid outcomes for this input.
3. For each run-matching line, track **occurrence counts**; a multiset is required, not a plain `Set`, because a `Set` hides duplicates.
4. `missing` contains expected IDs with zero outcomes.
5. `unexpected` contains observed IDs absent from the input.
6. `duplicates` contains IDs occurring more than once. Because this lesson requires **exactly one final outcome per line**, duplicates render the report incomplete.
7. Only when structure matches completely do we evaluate `allSucceeded`. A `REJECTED` or `FAILED` outcome is **received**, yet not a successful business outcome.

**Intentional limitation:** `firstStatusByLine` records the first status solely for concise reporting; when two outcomes appear for the same line, the whole group is flagged as having duplicates. Production code must not silently pick first or last as the "final result" without explicit rules on `attemptId`, `resultVersion`, and authoritative source. To merge intentional retries cleanly, add an attempt/deduplication layer before this reconciler.

### 6.4. Sample Run on a Batch

~~~java
import java.util.List;

BatchRequest original = new BatchRequest(
        "BAT-10", "RUN-10", List.of(
                new OrderLine("L-01", "SKU-A", 2),
                new OrderLine("L-02", "SKU-B", 1),
                new OrderLine("L-03", "SKU-C", 5)));

List<WorkOutcome> received = List.of(
        new WorkOutcome("BAT-10", "RUN-10",
                "L-01", WorkStatus.SUCCESS),
        new WorkOutcome("BAT-10", "RUN-10",
                "L-02", WorkStatus.REJECTED),
        new WorkOutcome("BAT-10", "RUN-10",
                "L-02", WorkStatus.REJECTED),
        new WorkOutcome("BAT-10", "RUN-10",
                "L-99", WorkStatus.SUCCESS));

BatchReconciliation report =
        new BatchReconciler().reconcile(original, received);

// report.missingLineIds()     == [L-03]
// report.unexpectedLineIds()  == [L-99]
// report.duplicateLineIds()   == [L-02]
// report.structurallyComplete()== false
// report.allSucceeded()       == false
~~~

**Takeaway:** having three inputs and four outputs never lets you conclude the batch finished processing. This case exhibits **three independent discrepancies**: one missing line, one unexpected ID, and one duplicate ID.

## 7. JUnit 5 Unit Tests for the Reconciliation Algorithm

### 7.1. Shared Fixtures

~~~java
import java.util.List;

final class BatchFixtures {
    static BatchRequest threeLines() {
        return new BatchRequest(
                "BAT-1", "RUN-1", List.of(
                        new OrderLine("L-1", "SKU-A", 1),
                        new OrderLine("L-2", "SKU-B", 2),
                        new OrderLine("L-3", "SKU-C", 3)));
    }

    static WorkOutcome success(String lineId) {
        return new WorkOutcome(
                "BAT-1", "RUN-1", lineId, WorkStatus.SUCCESS);
    }
}
~~~

### 7.2. All Three Parts Present, Even Out of Order

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class BatchReconcilerSuccessTest {
    private final BatchReconciler reconciler =
            new BatchReconciler();

    @Test
    void outOfOrderResultsStillMatchTheirOriginalLines() {
        BatchReconciliation report = reconciler.reconcile(
                BatchFixtures.threeLines(),
                List.of(
                        BatchFixtures.success("L-3"),
                        BatchFixtures.success("L-1"),
                        BatchFixtures.success("L-2")));

        assertTrue(report.structurallyComplete());
        assertTrue(report.allSucceeded());
        assertTrue(report.missingLineIds().isEmpty());
        assertTrue(report.unexpectedLineIds().isEmpty());
        assertTrue(report.duplicateLineIds().isEmpty());
        assertEquals(3, report.firstStatusByLine().size());
    }
}
~~~

Under a contract that **does not require outputs to preserve order**, this test should PASS. If the business requires restoring input order in the report, build the result list following **`original.lines()` order** after matching by ID. Never sort results by arrival time and pretend that is the original order.

### 7.3. Missing, Duplicate, Unexpected, and Foreign Outcomes

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class BatchReconcilerFailureTest {
    private final BatchReconciler reconciler =
            new BatchReconciler();

    @Test
    void missingOneLineDoesNotCompleteTheBatch() {
        BatchReconciliation report = reconciler.reconcile(
                BatchFixtures.threeLines(),
                List.of(
                        BatchFixtures.success("L-1"),
                        BatchFixtures.success("L-2")));

        assertEquals(List.of("L-3"), report.missingLineIds());
        assertFalse(report.structurallyComplete());
        assertFalse(report.allSucceeded());
    }

    @Test
    void duplicateCannotCompensateForMissingLine() {
        BatchReconciliation report = reconciler.reconcile(
                BatchFixtures.threeLines(),
                List.of(
                        BatchFixtures.success("L-1"),
                        BatchFixtures.success("L-1"),
                        BatchFixtures.success("L-2")));

        assertEquals(List.of("L-3"), report.missingLineIds());
        assertEquals(List.of("L-1"), report.duplicateLineIds());
        assertFalse(report.structurallyComplete());
    }

    @Test
    void unexpectedLineIsReported() {
        BatchReconciliation report = reconciler.reconcile(
                BatchFixtures.threeLines(),
                List.of(
                        BatchFixtures.success("L-1"),
                        BatchFixtures.success("L-2"),
                        BatchFixtures.success("L-3"),
                        BatchFixtures.success("L-99")));

        assertEquals(List.of("L-99"),
                report.unexpectedLineIds());
        assertFalse(report.structurallyComplete());
    }

    @Test
    void aForeignProcessingAttemptIsNotAccepted() {
        BatchReconciliation report = reconciler.reconcile(
                BatchFixtures.threeLines(),
                List.of(
                        BatchFixtures.success("L-1"),
                        BatchFixtures.success("L-2"),
                        new WorkOutcome("BAT-1", "OLD-RUN",
                                "L-3", WorkStatus.SUCCESS)));

        assertEquals(List.of("L-3"), report.missingLineIds());
        assertEquals(List.of("BAT-1/OLD-RUN/L-3"),
                report.foreignResults());
        assertFalse(report.structurallyComplete());
    }

    @Test
    void allOutcomesPresentButOneRejectedIsNotAllSucceeded() {
        BatchReconciliation report = reconciler.reconcile(
                BatchFixtures.threeLines(),
                List.of(
                        BatchFixtures.success("L-1"),
                        new WorkOutcome("BAT-1", "RUN-1",
                                "L-2", WorkStatus.REJECTED),
                        BatchFixtures.success("L-3")));

        assertTrue(report.structurallyComplete());
        assertFalse(report.allSucceeded());
    }
}
~~~

The last test is vital: **complete outcomes** does not mean all order lines succeeded. If the business accepts rejection as a valid terminal outcome, mark the batch `COMPLETED_WITH_REJECTIONS` rather than `SUCCESS` or `PENDING`.

### 7.4. Validating Input Quality Before Splitting

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertThrows;

class BatchInputValidationTest {
    @Test
    void duplicateInputLineIdIsRejected() {
        assertThrows(IllegalArgumentException.class, () ->
                new BatchRequest("BAT-1", "RUN-1", List.of(
                        new OrderLine("L-1", "SKU-A", 1),
                        new OrderLine("L-1", "SKU-B", 2))));
    }

    @Test
    void emptyBatchHasAnExplicitValidationOutcome() {
        assertThrows(IllegalArgumentException.class, () ->
                new BatchRequest("BAT-1", "RUN-1", List.of()));
    }

    @Test
    void invalidQuantityCannotBecomeAChild() {
        assertThrows(IllegalArgumentException.class, () ->
                new OrderLine("L-1", "SKU-A", 0));
    }
}
~~~

If invalid input has duplicate lines silently filtered out before the Splitter runs, emitted child counts may match *cleaned input* yet fail to match **the original request**. Whenever normalization alters cardinality, record `originalCount`, `normalizedCount`, dropped IDs, and reasons explicitly.

## 8. Reconciling Child Contents, Not Just Identities

### 8.1. Matching Identities Do Not Guarantee Correct Payloads

Suppose input line `L-2` is `SKU-B × 2`, yet the child was built as `SKU-B × 20`. Section 6's algorithm checks only **outcome identity**, so it could report `structurallyComplete=true` if statuses and IDs match.

To test **Split output** accuracy, add data comparisons:

~~~java
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

final class SplitPayloadAssertions {
    static Map<String, WorkItem> indexChildren(
            List<WorkItem> children) {
        return children.stream().collect(Collectors.toMap(
                WorkItem::lineId,
                Function.identity(),
                (left, right) -> {
                    throw new IllegalArgumentException(
                            "Duplicate child lineId: " + left.lineId());
                }));
    }
}
~~~

For each child, compare `sku` and `quantity` against the input by `lineId`:

~~~java
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class BatchSplitterPolicyTest {
    @Test
    void splitPreservesEveryInputLineAndBusinessLineage() {
        BatchRequest input = BatchFixtures.threeLines();
        List<WorkItem> children =
                new BatchSplitterPolicy().split(input);

        Map<String, WorkItem> byId =
                SplitPayloadAssertions.indexChildren(children);
        assertEquals(input.lines().size(), byId.size());

        for (OrderLine original : input.lines()) {
            WorkItem child = byId.get(original.lineId());
            assertEquals(input.batchId(), child.batchId());
            assertEquals(input.processingId(), child.processingId());
            assertEquals(original.sku(), child.sku());
            assertEquals(original.quantity(), child.quantity());
        }
    }
}
~~~

With a Transformer after the Splitter, fields may be **intentionally** altered (such as normalizing SKUs). Do not assert byte-for-byte equality on transformed fields; instead, define the expected mapping function and verify both **before** and **after** values. Reconciliation must follow the contract, not assume every output stays identical to the input.

### 8.2. One Input Element Creating Multiple Outputs

If line `L-1` is split into three chunks, child keys must capture both **parent line ID** and **chunk index/ID**:

~~~text
Input parent: L-1, bytes=12

Output:
  L-1/chunk-0: bytes [0..3]
  L-1/chunk-1: bytes [4..7]
  L-1/chunk-2: bytes [8..11]
~~~

Verify **full coverage, no overlap, no gaps**, checksums where appropriate, and reassemble strictly by declared positions. `count=3` does not prove all three ranges are covered if all three chunks contain `[0..3]`.

## 9. When to Use Checksums or Input Fingerprints?

For precision-sensitive data (files, financial batches, shipping manifests), you can store a **digest of a canonical representation** before the Splitter and verify after reassembly. Distinguish:

- **Byte-level equivalence:** exact recovery of the original byte stream.
- **Semantic equivalence:** equivalent business data even if JSON key ordering, whitespace, or number formatting changes.

Byte-level checksums break if a serializer changes whitespace or field order without changing meaning. Semantic digests require a **canonicalization contract**: schema version, Unicode normalization, timestamp formatting, line ordering, number representation, and ignorable fields.

Never use a checksum as the **sole proof** that all downstream handlers succeeded. It proves reassembled data matches, not that side effects committed or no external duplicates occurred.

## 10. Splitter in Spring Integration Java DSL

### 10.1. Wiring a Flow Splitting a Batch into Parts

We implement:

~~~mermaid
flowchart LR
    P[Batch Publisher] --> I[(batch.input)]
    I --> S[Splitter BatchRequest → WorkItem]
    S --> C[(work.items)]
    C --> H[Probe handler]
    H --> O["Captured children + headers"]
~~~

Children here are **recorded by a one-way test probe handler**; the flow has no `WorkOutcome` or Aggregator yet. That lets us test **Split output** without mixing in business-processing errors.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

record CapturedChild(
        WorkItem item,
        Object correlationId,
        Integer sequenceNumber,
        Integer sequenceSize) {}

final class ChildProbe {
    final List<CapturedChild> captured =
            new CopyOnWriteArrayList<>();

    void capture(WorkItem item, Map<String, Object> headers) {
        Integer sequenceNumber = numberAsInteger(
                headers.get("sequenceNumber"));
        Integer sequenceSize = numberAsInteger(
                headers.get("sequenceSize"));

        captured.add(new CapturedChild(
                item,
                headers.get("correlationId"),
                sequenceNumber,
                sequenceSize));
    }

    private static Integer numberAsInteger(Object number) {
        return number instanceof Number value
                ? value.intValue() : null;
    }
}

@Configuration
@EnableIntegration
class SplitBatchConfiguration {

    @Bean(name = "batch.input")
    MessageChannel batchInput() {
        return new DirectChannel();
    }

    @Bean(name = "work.items")
    MessageChannel workItems() {
        return new DirectChannel();
    }

    @Bean
    BatchSplitterPolicy splitterPolicy() {
        return new BatchSplitterPolicy();
    }

    @Bean
    ChildProbe childProbe() {
        return new ChildProbe();
    }

    @Bean
    IntegrationFlow splitBatch(BatchSplitterPolicy policy) {
        return IntegrationFlow.from("batch.input")
                .split(BatchRequest.class, policy::split)
                .channel("work.items")
                .get();
    }

    @Bean
    IntegrationFlow captureWorkItems(ChildProbe probe) {
        return IntegrationFlow.from("work.items")
                .handle(WorkItem.class, (item, headers) -> {
                    probe.capture(item, headers);
                    return null; // Terminal handler, produces no reply.
                })
                .get();
    }
}
~~~

**Design choices explained:**

- `.split(BatchRequest.class, policy::split)` passes input to a method returning `List<WorkItem>`; Splitter creates one child message per element.
- `BatchSplitterPolicy` keeps mapping logic infrastructure-free, already unit-tested for child contents.
- `work.items` is a `DirectChannel`, so the probe handler executes synchronously in the demo. When switching to queues/executors, tests must await completion signals.
- `ChildProbe` captures payloads and message metadata **immediately after the Splitter**; it does not yet measure business-processing outcomes.
- `correlationId`, `sequenceNumber`, and `sequenceSize` are common Spring Integration sequencing/grouping headers. When changing Splitter types, return types, or sequence configs, check **actual headers** and version semantics.

### 10.2. What Do Sequence and Correlation Headers Mean?

For a Splitter returning a known-size collection, Spring Integration typically attaches group metadata for aggregation:

| Header | Purpose | Do Not Infer |
|---|---|---|
| `correlationId` | Links messages split from a single source message. | That it equals business `batchId` in every case. |
| `sequenceNumber` | Position of one part in the sequence. | That it is a stable business `lineId` across replays. |
| `sequenceSize` | Group/sequence size per Splitter config and type. | That every streaming Splitter knows exact size. |
| `MessageHeaders.ID` | Unique ID of each Spring message. | That it is shared across children or durable across brokers. |

Sequence headers are meaningful only when **applied and preserved** per Splitter and adapter configuration. With `Iterator`/streaming or producers unaware of part counts upfront, `sequenceSize` may not reflect the final total like a finite `List`. In some flows, sequence headers can also be altered by nested splits or other correlating components.

**Best practice:** use `batchId`/`processingId`/`lineId` for business reconciliation, and use Spring Integration correlation/sequence for their intended infrastructure role. Never substitute one for the other without verification.

### 10.3. Do Not Rely Solely on Headers in Unit/Integration Tests

We want to verify two layers:

1. **Payload:** exact set of line IDs, right SKUs/quantities, right batch/processing IDs.
2. **Message metadata:** children carry sound correlation and sequence per the concrete Splitter contract.

If an adapter downstream of Splitter drops `correlationId`, payloads may still arrive intact at workers while an Aggregator relying on that header fails to group them. Conversely, having `correlationId` does not prove payloads were not corrupted.

## 11. JUnit Integration Tests for Splitter

### 11.1. Testing All Three Parts Emitted with Accurate Contents

~~~java
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(SplitBatchConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class SplitBatchIntegrationTest {

    @Autowired
    @Qualifier("batch.input")
    private MessageChannel input;

    @Autowired
    private ChildProbe probe;

    @Test
    void splitterProducesOneChildPerOriginalLine() {
        BatchRequest batch = BatchFixtures.threeLines();
        boolean sent = input.send(
                MessageBuilder.withPayload(batch).build(), 1_000);

        assertTrue(sent);
        assertEquals(batch.lines().size(), probe.captured.size());

        Map<String, WorkItem> byLineId = probe.captured.stream()
                .map(CapturedChild::item)
                .collect(Collectors.toMap(
                        WorkItem::lineId,
                        Function.identity()));

        for (OrderLine original : batch.lines()) {
            WorkItem child = byLineId.get(original.lineId());
            assertEquals(batch.batchId(), child.batchId());
            assertEquals(batch.processingId(), child.processingId());
            assertEquals(original.sku(), child.sku());
            assertEquals(original.quantity(), child.quantity());
        }
    }

    @Test
    void singleLineProducesExactlyOneChild() {
        BatchRequest batch = new BatchRequest(
                "BAT-ONE", "RUN-ONE",
                List.of(new OrderLine("L-ONLY", "SKU-ONE", 1)));

        assertTrue(input.send(
                MessageBuilder.withPayload(batch).build(), 1_000));
        assertEquals(1, probe.captured.size());
        assertEquals("L-ONLY",
                probe.captured.get(0).item().lineId());
    }
}
~~~

**Why `@DirtiesContext`?** `ChildProbe` is a stateful bean; each test needs isolated state or controlled reset. Tests must never depend on execution order. When running tests in parallel, avoid sharing stateful probes/contexts without proper isolation.

### 11.2. Testing Correlation and Sequence

In a configuration where **Splitter returns a `List` with sequence metadata enabled**, children should share one group and carry valid sequence ordinals.

~~~java
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(SplitBatchConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class SplitSequenceMetadataTest {

    @Autowired
    @Qualifier("batch.input")
    private MessageChannel input;

    @Autowired
    private ChildProbe probe;

    @Test
    void finiteListCarriesSequenceInformation() {
        assertTrue(input.send(
                MessageBuilder.withPayload(
                        BatchFixtures.threeLines()).build(), 1_000));

        assertEquals(3, probe.captured.size());

        Set<Object> groups = probe.captured.stream()
                .map(CapturedChild::correlationId)
                .collect(Collectors.toSet());

        assertEquals(1, groups.size());
        assertNotNull(probe.captured.get(0).correlationId());
        assertEquals(Set.of(1, 2, 3),
                probe.captured.stream()
                        .map(CapturedChild::sequenceNumber)
                        .collect(Collectors.toSet()));
        assertTrue(probe.captured.stream().allMatch(
                child -> Integer.valueOf(3)
                        .equals(child.sequenceSize())));
    }
}
~~~

This is an **expectation test** for the active flow. If `applySequence` or the splitter type changes, update the test to match the approved contract. Never "fix to green" by deleting metadata assertions when a downstream Aggregator depends on those exact headers.

### 11.3. Testing Two Batches Do Not Mix Outcomes

Some correlation bugs only surface when multiple batches exist:

~~~text
BAT-A / RUN-A: L-1, L-2
BAT-B / RUN-B: L-1, L-2
~~~

Two batches may **share local line IDs**, yet differ in `batchId` and `processingId`. In tests, send both inputs through the Splitter and assert:

- Each child keeps the right `batchId` and `processingId` from its input.
- Metadata never bleeds from batch A into batch B.
- The Reconciler seeing outcomes from batch B inside group A reports **`foreignResults`**, never counting them toward A's `expected` set.
- If an Aggregator keys off correlation headers, the two batches receive distinct group keys or matching grouping configuration.

This is especially critical when multiple producers generate `lineId=1` or reuse identical `1,2,3` sequence numbers.

### 11.4. When Output Traverses an Executor

Section 10's example uses `DirectChannel`, so the probe runs before `send` returns on the happy path. When switching to `ExecutorChannel`/`QueueChannel`, **never** assert counters immediately after `send` as a general rule.

Use `CountDownLatch`/timeout awaits or a `BlockingQueue<CapturedChild>` in the test handler, wait for items to arrive, and then assert; always clean up executors/pollers and avoid `Thread.sleep`-based tests. Still test negative paths: consumer failures, full queues, retry duplicates, timeouts, and late messages.

## 12. Do Not Treat the Default Aggregator as Full Reconciliation

### 12.1. Aggregator Is a Gathering Mechanism; Reconciliation Is a Business Contract

A flow might connect:

~~~mermaid
flowchart LR
    I[BatchRequest] --> S[Splitter]
    S --> W[Process each WorkItem]
    W --> A[Aggregator]
    A --> R[BatchResult]
    R --> V[Business Reconciler]
~~~

Spring Integration's Aggregator can use correlation and sequence headers to gather messages of the same group per its release strategy and message group store. However:

- **A released group** does not automatically prove every business line ID appeared once.
- **Sequence metadata** can change or disappear across Transformers/adapters or nested splits.
- **A failing handler** may emit no reply, stalling the group until timeout.
- **A Filter drop** can leave initial `sequenceSize` mismatched with arrived messages.
- **Redeliveries/duplicates** require explicit deduplication policies, not just `messageCount` checks.

Reconciling outputs against the original input still needs **an input snapshot or expected IDs** persisted/attached to the valid group.

### 12.2. Do Not Use `correlationId` as a Business Line ID

Children in the same group share `correlationId`; if a Reconciler uses that header as the unique per-part key, it thinks all parts are **one single line**. Conversely, grouping solely by `lineId` fails to bind three distinct lines into one batch.

Separate responsibilities:

~~~text
correlationId / processingId: "Which messages belong to the same group?"
lineId:                     "Which element of the group is this?"
sequenceNumber:             "What is this element's position per sequencing?"
attemptId / deliveryId:     "Which delivery/processing attempt is this?"
~~~

With `MessageGroupStore`, check **group keys, release strategies, group expiration, and state cleanup**. If the same business batch replays while an old group still lingers, new messages can cross-contaminate if correlation keys are reused without clear rules.

### 12.3. Output Order After Aggregator

Messages may process concurrently and arrive in any order. If the result report must match original input order:

1. Keep `lineId` or `originalIndex` inside `WorkItem`.
2. Verify completeness, zero duplicates, and zero unexpected items.
3. Sort outcomes by **original order** after reconciliation.
4. Never treat random `HashMap` order, arrival timestamps, or handler completion order as business order.

### 12.4. When One Part Is `REJECTED`

If `WorkOutcome(L-2, REJECTED)` is recorded, the business question is: must we wait for `L-2` to succeed, or only confirm it was evaluated and rejected?

- Under a "every line has a **final outcome**" contract, `REJECTED` fills a group slot; the batch finishes as `COMPLETED_WITH_REJECTIONS`.
- Under an "every line must **succeed**" contract, `allSucceeded=true` cannot hold; the whole batch may need compensation/rejection.
- If a Filter **silently drops `L-2`**, the group needs a way to learn it was dropped; otherwise it only sees a missing message and waits until timeout.

Never apply a count-only release strategy when success criteria require inspecting detailed business statuses.

## 13. Timeouts, Retries, Duplicates, and Late Arrivals

### 13.1. Classifying Per-Part Statuses

A realistic model may distinguish:

| Status | Meaning | Should Count as Final Outcome? |
|---|---|---|
| `PENDING` | Child dispatched/queued, no outcome yet. | Not yet. |
| `IN_PROGRESS` | Worker started processing. | Not yet. |
| `SUCCESS` | Completed per worker contract. | Yes. |
| `REJECTED` | Data valid yet rejected by business policy. | Yes if contract defines it so. |
| `FAILED_RETRYABLE` | Transient error, still eligible for retry. | Not while retries remain. |
| `FAILED_FINAL` | No retries left; terminal failure outcome. | Yes, though not successful. |
| `TIMED_OUT` | Deadline passed, result missing or uncertain. | Needs explicit handling contract. |

`WorkStatus` in section 5 kept only three values to focus on reconciliation. Richer operational states belong in the **processing/retry layer**, rather than forcing every transient state into a final `WorkOutcome` prematurely.

### 13.2. Do Not Count Every Delivery as an Independent Result

Suppose a broker redelivers the same part:

~~~text
eventId=EVENT-1, processingId=RUN-1, lineId=L-1

delivery #1 -> Worker processes, commits successfully
             -> ack is lost
delivery #2 -> Worker receives same message again
~~~

If both deliveries emit outcomes and the Aggregator simply counts two messages, the group can release prematurely. You need:

- A stable **business processing key**, such as `processingId + ":" + lineId`.
- A separate **delivery/attempt ID** to trace each delivery.
- Idempotency or deduplication wherever side effects occur.
- A policy when multiple outcomes arrive for the same business key.
- Tests for duplicate outcomes, including when two outcomes carry different statuses.

**Never use `MessageHeaders.ID` as the sole idempotency key:** redelivery/message reconstruction can change IDs, and matching IDs do not prove a side effect hasn't run. Tie keys to the **business operation**.

### 13.3. Timeouts Do Not Prove a Child Was Not Processed

~~~mermaid
sequenceDiagram
    participant A as Aggregator
    participant W as Worker L-3
    participant D as Database
    A->>W: Wait for outcome L-3
    W->>D: Write result
    D-->>W: Commit succeeded
    Note over W,A: Slow network / lost reply
    A--xA: Deadline passes, mark missing/timeout
    W-->>A: Outcome L-3 arrives late
~~~

In the diagram, **`L-3` is not necessarily unprocessed** even though the Reconciler sees a missing outcome at deadline. Depending on contract:

1. Mark batch `TIMED_OUT / PARTIALLY_OBSERVED` and permit re-reconciliation.
2. Query target system state before retrying to prevent duplicate side effects.
3. Route late outcomes to a dedicated path: emit a versioned report update, discard per policy, or create an adjustment event.
4. Clean up message group stores after expiry; never hold groups forever.
5. Enforce both **batch-level deadlines** and **per-worker deadlines**.

### 13.4. Retry Only Failed Parts or Retry the Whole Batch?

Suppose three lines have:

~~~text
L-1 SUCCESS
L-2 FAILED_RETRYABLE
L-3 SUCCESS
~~~

**Retrying the whole batch** risks re-running `L-1` and `L-3` despite prior success. **Per-part retry** keeps `processingId`/`lineId` or creates a new attempt ID for `L-2`, per contract.

When retrying:

- To keep **the same logical run**, preserve `processingId` and use `attemptId`/`deliveryId` for the retry; deduplicate final outcomes.
- To start **a brand-new batch run**, mint a new `processingId` and exclude outcomes from the old run.
- Never let a late reply from an old attempt silently overwrite fresh state.
- Never assume a retryable exception means it is safe to re-call a side-effecting HTTP API blindly.

### 13.5. When the Gateway Times Out

If a client submits a batch via a request–reply Gateway while the full batch takes seconds or minutes, the Gateway may time out before the Reconciler gathers all outcomes.

~~~text
HTTP/Gateway request -> Splitter -> async workers -> Aggregator
Client timeout 5s          worker L-3 completes at 7s
~~~

**A caller timeout does not automatically cancel downstream work.** If the client retries with the same `batchId`, decide whether to keep the old `processingId`/operation ID or start a new run, enforce idempotency, and handle late outcomes. For long-running batches, a `202 Accepted + status endpoint` API often fits better than holding a Gateway thread open for everything.

## 14. Messages Dropped by Filters or Failing Across Routers/Transformers

### 14.1. Filter After Splitter Changes Aggregator Arrival Count

~~~mermaid
flowchart LR
    B["3-line Batch"] --> S[Splitter]
    S --> L1[L-1]
    S --> L2[L-2]
    S --> L3[L-3]
    L1 --> F{Filter}
    L2 --> F
    L3 --> F
    F -->|true| H[Process]
    F -->|false| D[Discard / rejection flow]
    H --> A[Aggregator]
    D -. REJECTED outcome if designed .-> A
~~~

If a Filter drops `L-2` without emitting an outcome, an Aggregator waiting for three may **never see the third message**. Do not work around this by arbitrarily setting `sequenceSize=2` after children were emitted. Pick one contract:

- Filter emits `WorkOutcome(REJECTED)` for dropped lines.
- A planner computes the eligible subset upfront and splits only that, recording rejected IDs to reconcile with the original input.
- Release strategy/timeout explicitly accounts for drops and partial-success rules.

**Never declare all three lines complete just because the Aggregator received both lines that passed the Filter.** You must record that the third line was intentionally rejected.

### 14.2. Transformers Can Strip Lineage

A Transformer after the Splitter might return only:

~~~java
// Wrong if downstream needs lineId to reconcile:
String normalizeSku(WorkItem item) {
    return item.sku().trim().toUpperCase();
}
~~~

The output is just a `String`, stripping `batchId`/`processingId`/`lineId` from the payload. Even if the framework propagates headers, correlation may survive while **per-part business identity becomes obscured**.

A new DTO preserving lineage:

~~~java
record NormalizedWorkItem(
        String batchId,
        String processingId,
        String lineId,
        String normalizedSku,
        int quantity) {}

NormalizedWorkItem normalize(WorkItem item) {
    return new NormalizedWorkItem(
            item.batchId(),
            item.processingId(),
            item.lineId(),
            item.sku().trim().toUpperCase(),
            item.quantity());
}
~~~

With intentional validation/normalization, tests must verify data against transformation rules instead of demanding byte-for-byte identical SKU outputs.

### 14.3. Routers Can Send Parts to Different Branches

A Router by SKU/region may send `L-1` to a domestic handler, `L-2` to manual review, and `L-3` to a partner system. Reconciliation must gather outcomes from **all required branches**, not only the fastest branch.

~~~text
RUN-1 / L-1 -> domestic  -> SUCCESS
RUN-1 / L-2 -> review    -> PENDING
RUN-1 / L-3 -> partner   -> SUCCESS
~~~

At this point, reconciliation reports **`L-2` lacks a final outcome**. Never assume the review branch failed merely because it takes longer; define deadlines, SLAs, and valid states per route.

### 14.4. Content Enricher Making Children Larger Than the Original

A child `WorkItem` after a Content Enricher may gain `ProductInfo`, pricing, inventory, or metadata. If you need to verify **original input preservation**, wrap it:

~~~text
EnrichedWorkItem:
  original: WorkItem
  productInfo: ...
  enrichmentMetadata: ...
~~~

After this step, **whole-object payload equality** no longer holds between input and output since enrichment is intentional. Compare `enriched.original` to the original `WorkItem` by identity and business fields, and validate enriched data separately per contract.

### 14.5. Nested Splits

If Splitter A splits a batch into orders, and Splitter B splits each order into lines, there are **two tiers of correlation/sequence**:

~~~text
Batch
  -> Order 1
       -> Line 1.1
       -> Line 1.2
  -> Order 2
       -> Line 2.1
~~~

Never assume a single flat `correlationId`/`sequenceNumber` suffices to represent the entire source tree. You may need `batchId`, `orderId`, `lineId`, and tier mappings, or rules storing original hierarchy. When an inner Splitter mints a new sequence, verify which headers are preserved/replaced and that each Aggregator groups by the **right parent**.

## 15. Crossing Adapters or Brokers

### 15.1. Headers Are Not Payloads

Between two JVMs, HTTP/Kafka/JMS/AMQP adapters map headers onto transport protocols differently:

| Data | Location | Risk |
|---|---|---|
| `batchId`, `processingId`, `lineId` | Business payload envelope | Can be lost if serializer omits fields or converter version mismatches. |
| `correlationId`/`sequenceSize` | Spring `MessageHeaders` | Can be filtered, type-changed, or dropped by mappers across transports. |
| `replyChannel`/`errorChannel` | Internal headers | May be JVM channel object references; cannot cross processes intact. |
| `MessageHeaders.ID` | Per-message header | May be regenerated when reconstructing messages. |
| `trace context` | Instrumentation headers | Requires explicit propagation across threads/transports. |

If the sender sets `sequenceSize=3` while the receiver gets only a plain line `String` payload, you cannot assume the receiving Aggregator knows the original group. Across transports that strip headers, enforce an **explicit schema** or header mapper and run round-trip tests.

### 15.2. Round-Trip Testing

An end-to-end test should traverse:

~~~text
BatchRequest
  -> Splitter (Spring Integration)
  -> Serializer / Outbound Adapter
  -> Broker / HTTP
  -> Inbound Adapter / Deserializer
  -> WorkItem
  -> Worker
  -> WorkOutcome
  -> Reconciler
~~~

Verify:

1. Every `WorkItem` retains exact `batchId`/`processingId`/`lineId`.
2. Expected size/set is transmitted or stored where the Reconciler can read it.
3. Correlation/sequence headers **actually** restore properly if the Aggregator relies on them.
4. No unintended mutations occur to `quantity` values or formats.
5. Outcomes from other batches or old runs never bleed in.
6. Broker redeliveries create no extra business successes.
7. When a consumer fails, retry/DLQ/quarantine and timeout/release policies operate clearly.

Never treat a pure-Java serializer test as proof that every adapter/broker preserves metadata. Run at least one test across the **actual boundary** used in production.

## 16. Observability: Clearly Seeing Inputs, Outputs, and Discrepancies

### 16.1. Suggested Structured Events

~~~text
event=BATCH_RECEIVED
  batchId=BAT-10 processingId=RUN-10 inputCount=3

event=SPLIT_COMPLETED
  batchId=BAT-10 processingId=RUN-10 producedCount=3

event=CHILD_PROCESSING_STARTED
  processingId=RUN-10 lineId=L-02 attempt=1

event=CHILD_OUTCOME_RECORDED
  processingId=RUN-10 lineId=L-02 status=REJECTED

event=BATCH_RECONCILED
  processingId=RUN-10 expectedCount=3
  observedUnique=2 duplicateCount=1
  missingCount=1 unexpectedCount=1
  structurallyComplete=false allSucceeded=false
~~~

This is an **application-defined suggested schema**, not default Spring Integration output. For root-cause tracing, logs can add trace ID, channel/endpoint, and reason codes, while avoiding raw payloads, tokens, or personal data.

### 16.2. Do Not Watch Total Message Counts Alone

Counts can diverge for valid or abnormal reasons:

| Metric | Meaning |
|---|---|
| `input_batch_total` | Inbound batches. |
| `input_line_total` | Total valid expected lines post-validation. |
| `split_child_created_total` | Children created by Splitter. |
| `child_dispatched_total` | Children sent per channel contract. |
| `child_outcome_total{status}` | Outcomes received by status. |
| `child_duplicate_total` | Duplicate outcomes/deliveries detected. |
| `child_missing_after_deadline_total` | Lines still lacking outcomes past deadline. |
| `batch_reconciled_total{outcome}` | Complete/partial/failed batches. |
| `batch_group_pending` | Open Aggregator groups still waiting. |
| `batch_group_expired_total` | Groups expired/released per policy. |

The names above are **illustrative metrics**. Never use high-cardinality `batchId`, `lineId`, `processingId`, or `traceId` as metric labels; keep those IDs in access-controlled logs/traces or stores. Restrict labels to status, component, destination, or bounded categories.

### 16.3. Message History and Lineage Are Different

Spring Integration's **Message History** shows which components a message traversed when tracking is enabled. It is not by itself:

- The original input snapshot with all line IDs.
- Each worker's business outcome.
- Proof that database side effects committed.
- Durable distributed tracing across every broker/adapter.
- The expected set for spotting missing/duplicate parts.

To investigate accurately, combine **Message History, correlation/trace headers, input snapshots, outcome stores, and reconciliation reports**. A "Splitter succeeded" log cannot explain why the batch report is missing `L-03`.

### 16.4. Finding Why a Batch Is Missing Outcomes

If the report shows `missingLineIds=[L-03]`, inspect in order:

1. **Input snapshot:** did `L-03` truly exist in the original input?
2. **Splitter output:** was child `L-03` emitted?
3. **Channel/adapter:** was the child dispatched/serialized/acked per contract?
4. **Router/Filter:** was the child dropped or routed to another branch?
5. **Worker:** are there `STARTED`, `COMPLETED`, `FAILED`, or timeout records?
6. **Outcome transport:** was a response sent yet lost, delayed, or had its ID changed?
7. **Aggregator/Reconciler:** were group key, release strategy, dedupe, and timeouts configured right?
8. **Retry/late reply:** is another attempt running, or did the outcome arrive post-deadline?

Only after pinpointing **the exact first hop where the line vanished** should you fix the offending component. Never randomly tweak `sequenceSize` or inflate timeouts indefinitely to mask the bug.

## 17. Input–Output Test Matrix

| ID | Case | Expected | Negative Assertion |
|---|---|---|---|
| SP-01 | Single-line input | Exactly one `WorkItem` | No extra children created. |
| SP-02 | Three distinct lines | Exactly three children, all IDs intact | None missing, none duplicated. |
| SP-03 | Caller mutates original list post-creation | Input snapshot unchanged | Expected set never silently drifts. |
| SP-04 | Duplicate input `lineId` | Validation exception | Never silently picks one line. |
| SP-05 | Input with 0/negative quantity | Validation exception | Never spawns bad-data child. |
| SP-06 | Empty batch | Per lesson contract: reject `EMPTY_BATCH` | Never leaves Gateway/Aggregator hanging. |
| SP-07 | Child processed out of order | Reconciliation still complete when IDs match | Never compares by arrival index. |
| SP-08 | Missing `L-3` | `missing=[L-3]` | Never reports complete. |
| SP-09 | `L-1` arrives twice, `L-3` missing | Reports duplicate and missing | Count=3 does not fool check. |
| SP-10 | `L-99` absent from input | Reports unexpected | Never accepts stray output. |
| SP-11 | Outcome carries stale `processingId` | Placed in foreign | Never merges into active run. |
| SP-12 | Wrong `batchId` despite matching processing ID | Foreign/mismatch | Never merges wrong batch. |
| SP-13 | All IDs present, all `SUCCESS` | Complete and `allSucceeded` | No false negatives. |
| SP-14 | All IDs present, one `REJECTED` | Complete yet not `allSucceeded` | Never conflates completeness with success. |
| SP-15 | All IDs present, one `FAILED` | Complete yet not `allSucceeded` | Never reports business success. |
| SP-16 | Child keeps `lineId` yet wrong SKU/quantity | Payload integrity test fails | Never checks IDs only. |
| SP-17 | Finite List Splitter with sequence metadata | Sequence/correlation verified | Never skips header tests when Aggregator relies on them. |
| SP-18 | Child passes through Transformer | Lineage remains readable | Not reduced to bare SKU String. |
| SP-19 | Filter drops a child | Rejected outcome or missing/timeout per policy | Never falsely releases as "complete". |
| SP-20 | Handler throws synchronously | Explicit error path | Never claims all children ran. |
| SP-21 | Async handler replies late | Deadline/late-reply policy works | Never infers completion from `send=true`. |
| SP-22 | Broker redelivers same child | Deduplicates by operation key | Never doubles side effects. |
| SP-23 | Gateway times out while workers run | Pending/late outcome state explicit | Never treats timeout as canceling work. |
| SP-24 | Two batches share local `lineId` | Isolated via batch/processing IDs | Never groups solely by line ID. |
| SP-25 | Nested Splitters | Parent hierarchy and correlation preserved | Never mixes Order/Line levels. |
| SP-26 | Child crosses HTTP/Kafka/JMS | Payload + metadata round-trip per contract | Never silently drops headers. |
| SP-27 | Retry single failed child | Does not pointlessly retry whole batch | Never repeats succeeded side effects. |
| SP-28 | One-to-many chunks | Full coverage, accurate offsets/lengths | Count matches yet chunks duplicate range. |
| SP-29 | Streaming with unknown item count | End-of-stream/expiration policy works | Never waits on wrong fixed `sequenceSize`. |
| SP-30 | Process restarts while pending | Recovers from store/broker if contract demands | Never relies on in-memory queues for durability. |

### 17.1. Testing Layers to Implement

| Layer | Where to Assert | What It Cannot Prove Alone |
|---|---|---|
| **Splitter policy unit test** | Child count, IDs, original payload fields. | Whether dispatchers/channels work. |
| **Reconciler unit test** | Missing/duplicate/unexpected/foreign, success vs. complete. | Broker redeliveries and real consumers. |
| **Spring Integration test** | Splitter creates child messages, headers, right channels, endpoint lifecycle. | Cross-process serialization without adapters. |
| **Adapter integration test** | Header mapping, encoding, transport retry/ack, data round-trip. | Committed business side effects if using mocks. |
| **System/end-to-end test** | From batch input through outcomes/reports, timeouts, retries, recovery. | Every production failure mode at all times. |

Avoid treating a "green" unit test as proof that every downstream component works. This lesson emphasizes standalone reconciliation, followed by tests crossing **the exact boundaries where messages risk getting lost**.

## 18. Common Mistakes

| Misconception | Consequence | Right Approach |
|---|---|---|
| "Output count equals input count, so nothing is missing." | Duplicates mask missing items. | Compare multisets by identity. |
| "Outputs arrive in exact input order." | False failures under concurrency. | Match by line ID; restore order if needed. |
| "Message ID is the order line ID." | Unstable across reconstructions/adapters. | Use business `lineId` + `processingId`. |
| "A `REJECTED` outcome means missing." | False missing alerts despite terminal result. | Separate completeness from `allSucceeded`. |
| "Aggregator released, so the whole batch succeeded." | Count-based release may include `FAILED` or duplicates. | Run business reconciliation post-gather. |
| "If Filter drops a part, Aggregator knows automatically." | Group stalls or releases wrongly. | Emit rejection outcome or define explicit release/expected policy. |
| "`correlationId` replaces `lineId`." | All children in a group look like one line. | Group key and item key have separate roles. |
| "`sequenceNumber` never changes." | Nested splits/adapters alter metadata. | Verify propagation and sequence tiers. |
| "`List.copyOf` deep-copies every child." | Mutable elements can still change. | Make proper defensive copies. |
| "Matching `lineId` means payload is intact." | Quantity/SKU silently corrupted. | Compare data fields per contract. |
| "Async `send` returning true means processing finished." | Reports batch complete prematurely. | Track processing outcomes independently. |
| "Timeout proves the worker never committed." | Retries cause duplicate side effects. | Reconcile/requery state and enforce idempotency. |
| "Retrying the whole batch is always simple and safe." | Re-executes already-succeeded parts. | Retry per part or use explicit replay policies. |
| "Empty batch automatically produces an empty reply." | Gateway hangs or flow emits nothing. | Define zero-child semantics explicitly. |
| "Message History is a reconciliation report." | Lacks original snapshot and business outcomes. | Persist expected input IDs and result statuses. |
| "All Spring headers survive every broker intact." | Aggregator loses correlation/sequence. | Define header mapper/serializer contracts and integration-test them. |
| "Just ignore unexpected results." | Can hide cross-tenant or cross-batch leaks. | Report foreign/unexpected, audit, and handle securely. |
| "Just increase timeouts to stop missing items." | Hides queue backlogs, retry storms, or broken wiring. | Locate the first hop losing items and fix root cause. |

## 19. Hands-On Exercises

1. **1→N Reconciliation:** create a three-line `BatchRequest`, run `BatchSplitterPolicy`, and verify three `WorkItem` instances with exact IDs/SKUs/quantities.
2. **Duplicate input:** intentionally construct two lines sharing `lineId`, verify the constructor rejects it, and explain why silently deduping via a `Map` hides bad input.
3. **Out-of-order outcomes:** supply outcomes ordered `L-3, L-1, L-2` and verify reconciliation still reports complete/`allSucceeded`.
4. **Misleading count:** supply `L-1, L-1, L-2` for input `L-1, L-2, L-3`; prove `L-3` is missing and `L-1` is duplicated.
5. **Unexpected:** add `L-99` to outcomes; test that the report denies completion even when all input IDs are present.
6. **Foreign result:** deliver an outcome from `RUN-OLD` into `RUN-NEW`; prove stale outcomes never fill a missing line.
7. **Business rejection:** supply all outcomes with one `REJECTED`; produce business status `COMPLETED_WITH_REJECTIONS` distinct from `SUCCESS`.
8. **Spring Integration DSL:** wire `SplitBatchConfiguration`, send a batch, and verify captured message counts at `work.items`.
9. **Sequence headers:** inspect `correlationId`, `sequenceNumber`, and `sequenceSize` for a finite Splitter; switch config/streaming and explain the differences.
10. **Transformer:** uppercase SKUs while retaining `lineId`/`processingId`; verify the input snapshot stays intact and outputs match transformation rules.
11. **Filter:** drop child `L-2`; compare silent discard against emitting `WorkOutcome(REJECTED)` to the Aggregator.
12. **Aggregation:** connect child workers to an Aggregator, inject a duplicate and a branch failure, and design release and group-expiration strategies before calling the Reconciler.
13. **Retry:** simulate `L-2` failing twice then succeeding; use attempt IDs to deduplicate rather than counting three separate final outcomes.
14. **Timeout:** have `L-3` arrive after the deadline. Define batch status at timeout and handling for the late outcome.
15. **Two concurrent batches:** create two `BatchRequest` objects sharing local line IDs yet differing in processing IDs. Prove outcomes never mix.
16. **Nested split:** split batch into orders, then orders into lines; use batch/order/line IDs to reconstruct the exact tree.
17. **One-to-many:** split a binary payload into chunk offsets; verify every byte is covered once with no gaps or overlaps.
18. **Kafka/HTTP round-trip:** send `WorkItem` across a real serializer/adapter and verify required IDs and sequence headers survive.
19. **Observability:** emit `BATCH_RECEIVED`, `SPLIT_COMPLETED`, `CHILD_OUTCOME_RECORDED`, and `BATCH_RECONCILED` events; trace a missing line.
20. **Durability:** simulate a crash while a child is queued; compare in-memory queues against durable stores/brokers and build idempotent replay.

### Exercise Completion Checklist

A reliable implementation should be able to answer:

- Do we have an **immutable input snapshot** and expected ID set?
- Do we distinguish output **right after Splitter** from post-processing outcomes?
- When outcomes arrive out of order, can we reconcile them accurately?
- Do we detect missing, duplicate, unexpected, and foreign results?
- Do we separate structural completeness from business success?
- On timeout/retry, do we know which parts truly finished vs. remain uncertain?
- Can we trace from any `lineId` in the report back to the exact original `OrderLine`?
- Do we have sufficient data to debug a message across Router, Filter, Transformer, and adapters?

## 20. Self-Check Questions

**Q1:** Input has three line IDs `A, B, C`; outputs are `A, A, B`. Output count equals input count—is it complete?  
**No.** `C` is missing and `A` is duplicated. Compare multisets by ID, not raw counts.

**Q2:** Input is `A, B, C`; outcomes `C, A, B` arrive in reverse/scrambled order. Is a message missing?  
**No**, provided identities and statuses are intact. Arrival order carries no inherent business meaning.

**Q3:** A batch receives all three outcomes, yet `B=REJECTED`. Is it complete, and is it `allSucceeded`?  
**It can be structurally complete yet not `allSucceeded`**, under a contract requiring one terminal outcome per line.

**Q4:** Can `MessageHeaders.ID` identify an order line across all adapters and retries?  
**No.** Message IDs can change when messages are rebuilt; use stable business keys such as `processingId + lineId`.

**Q5:** Do `correlationId` and `sequenceNumber` mean the same thing?  
**No.** Correlation groups related messages; sequence number gives position within a sequence per its semantics.

**Q6:** If Splitter emits three children, have all three downstream HTTP calls succeeded?  
**Not yet.** That only marks child creation/dispatch, not each handler's execution outcome.

**Q7:** A Filter drops the second child message. Does a default Aggregator automatically know to wait for two instead of three?  
**No.** You need an explicit release/expected-set policy or a separate rejection outcome.

**Q8:** Why is `processingId` needed when `batchId` already exists?  
**Because** the same business batch can be replayed/rerun; outcomes from an old run must not automatically merge into a new run.

**Q9:** Does an outcome timing out and arriving late prove the worker never committed?  
**No.** A timeout may simply reflect a slow or lost reply; check downstream state and apply a late-reply policy.

**Q10:** If an output has the right `lineId` yet a wrong `quantity`, is reconciliation considered successful?  
**No**, if the contract requires preserving quantity. ID reconciliation must be paired with payload integrity tests.

**Q11:** When a Splitter processes a finite `List`, should tests check sequence metadata?  
**Yes**, if the flow relies on that metadata, especially for an Aggregator; verify the concrete semantics/configuration of your Spring Integration version.

**Q12:** Does switching `QueueChannel` to `DirectChannel` change the meaning of `send`?  
**Potentially yes.** Synchronous and asynchronous channels differ in accepted vs. processed boundaries; match assertions to the execution model.

**Q13:** Should a child retried three times count as three business outcomes?  
**Not by default.** Separate attempts/deliveries from final outcomes and apply deduplication/idempotency.

**Q14:** Can Message History replace the original `BatchRequest` for computing missing IDs?  
**No.** History only records traversed tracked components; the expected set must come from the original input or an equivalent snapshot.

**Q15:** If one input line intentionally spawns three chunks, should input line count equal output count?  
**No.** For one-to-many splits, validate against each parent's expected child count, offsets, and coverage contract.

## 21. Conclusion

**Reconciling outputs against the original input** is essential whenever using **Splitter**. When a batch splits into multiple messages, retain an **input snapshot**, identify every part with **stable business lineage**, and verify outputs by **ID and contents** rather than count or arrival order alone.

In Spring Integration, Splitter creates and dispatches child messages; sequence/correlation headers assist grouping, while Routers, Filters, Transformers, Gateways, and outbound adapters can alter each part's path or outcome. **Aggregator release does not automatically mean the batch succeeded.** Distinguish completeness, business success, retries, duplicates, timeouts, and late arrivals.

Within the `SPRING_INTEGRATION_PATTERN` module, the right practice workflow is: **unit-test Splitter policy → unit-test Reconciler → integration-test channels/headers → adapter/end-to-end tests**. Combine structured logging, error channels, correlation, message group expiration, and idempotency to answer accurately: **"Which parts existed in the original input, where did each part go, and what final outcome was reached — and are any parts missing, unexpected, or duplicated?"**
