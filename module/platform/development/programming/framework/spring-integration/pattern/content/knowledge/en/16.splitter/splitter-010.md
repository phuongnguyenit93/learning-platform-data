# Preventing One Bad Element from Accidentally Losing the Entire Batch

## 1. Why Can One Bad Element Affect the Whole Batch?

In the **Splitter** chapter of the **SPRING_INTEGRATION_PATTERN** module, we learn to implement Enterprise Integration Patterns with **Spring Integration** to build loosely coupled, extensible, testable, and observable message flows. A Splitter accepts a large message and produces child messages. Child messages can be processed independently through Transformer, Filter, Router, Service Activator, and then combined by an Aggregator into a shared result.

Suppose an intake system imports **a batch of 5 order lines**:

| Line | Item Code | Input Quantity | Expected Result |
| --- | --- | --- | --- |
| 1 | SKU-A | 3 | Valid |
| 2 | SKU-B | 2 | Valid |
| 3 | SKU-C | abc | Invalid number format |
| 4 | SKU-D | 5 | Valid |
| 5 | SKU-E | 1 | Valid |

If the business policy is **partial success**, line 3 should be flagged with an error for user correction while the four valid lines still get processed. Yet an unguarded design can cause:

- A Transformer on line 3 throwing an exception and **halting the synchronous flow before lines 4 and 5 are dispatched**.
- Line 3 getting dropped by a Filter, leaving the **Aggregator waiting for 5 results while only 4 arrive**.
- An asynchronous branch failing where the error lands only on **`errorChannel`**, with no corresponding outcome reaching the Aggregator.
- Retrying the entire batch after partial success, causing lines already persisted on the first attempt to be written twice.
- Marking the batch **SUCCESS** even though some lines never finished.

~~~mermaid
flowchart LR
    B["5-line Batch"] --> S["Splitter"]
    S --> R1["Line 1 OK"]
    S --> R2["Line 2 OK"]
    S --> R3["Line 3 error"]
    S --> R4["Line 4 OK"]
    S --> R5["Line 5 OK"]
    R1 --> A["Aggregator"]
    R2 --> A
    R3 -->|"Explicit FAILED outcome"| A
    R4 --> A
    R5 --> A
    A --> O["BatchReport: 4 OK, 1 FAILED"]
~~~

**Lesson Objectives**

1. Distinguish **errors before Splitter**, **errors during splitting**, **child message errors**, and **aggregation errors**.
2. Understand correlation, `sequenceNumber`, and `sequenceSize`, especially when an item produces no reply.
3. Design typed outcomes per element: `SUCCESS`, `REJECTED`, or an appropriate recovery status.
4. Explicitly choose **fail-fast**, **partial success**, or **all-or-nothing** instead of letting default framework behavior decide for the business.
5. Configure a Splitter–Transformer–Aggregator flow that isolates data errors to individual items.
6. Organize retries, dead-letter/quarantine, idempotency, transactions, and observability for batches.
7. Test failing items at the start, middle, and end; synchronous and asynchronous failures; duplicates; and timeouts.

## 2. What Is—and Isn't—Splitter's Responsibility?

**Splitter** is the pattern that breaks one message into multiple parts:

~~~text
Message<Batch>
      |
      v
    Splitter
      |
      +--> Message<Item 1>
      +--> Message<Item 2>
      +--> Message<Item 3>
      +--> ...
~~~

Spring Integration supports Splitters from:

- A Collection or array.
- An Iterable or Iterator.
- A Stream and certain reactive sources, depending on version.
- A POJO method returning a collection of elements.
- An `AbstractMessageSplitter` implementation when advanced control is required.

Splitter **does not automatically guarantee** that each element succeeds, that each element is durably stored, or that one business error will not affect other elements. That responsibility belongs to the **pipeline architecture**, error handling, and state persistence layer.

### 2.1. Four Error Boundaries to Distinguish

| Boundary | Example | Potential Blast Radius |
| --- | --- | --- |
| **Before split** | Empty `batchId`, file structural parse error | Entire batch rejected before splitting |
| **During split** | Split function throws reading source | Not all elements may be emitted |
| **Post-split, at item handler** | Line 3 contains `quantity=abc` | Depends on design: only line 3 fails, or fan-out aborts |
| **During aggregation/persistence** | `MessageStore` failure, missing sequence, DB unavailable | Batch summary may never be produced |

If a failure violates the **overall batch contract** (file missing `batchId`, invalid signature, insufficient import permissions), rejecting the **entire batch before splitting** is the right choice. This lesson is about **not accidentally losing an entire batch** due to a **localized single-line error**, not about swallowing every error indiscriminately.

### 2.2. Policy Should Never Be Guessed from an Exception

| Policy | Business Meaning | When an Item Fails |
| --- | --- | --- |
| **Fail-fast** | Even one bad item means processing must not proceed | Stop intentionally, report batch rejected |
| **All-or-nothing** | Either every change commits or none does | Roll back with a real transaction where feasible |
| **Partial success** | Valid items proceed; failed items are reported individually | Emit FAILED outcome for the item; others continue |
| **Best effort** | Process as many as possible; missing items tolerated | Must define explicit status and SLA; never drop silently |
| **Eventual completion** | Transiently failing items retry independently; batch completes later | Persist PENDING/RETRYING state; do not report SUCCESS prematurely |

Policy is a **business decision**, not a default Splitter setting. For the exact same `quantity=abc` error, a bulk catalog importer may allow partial success, whereas a batch bank-transfer app may require rejecting the entire batch before executing any transaction.

## 3. Correlation and Sequence: Why Can an Aggregator Wait Forever?

When Splitter creates child messages, Spring Integration attaches sequencing metadata by default to support splitter–aggregator flows:

| Header | Role |
| --- | --- |
| **correlationId** | Identifies child messages belonging to the same split |
| **sequenceNumber** | Position of the child message in the sequence |
| **sequenceSize** | Number of elements the group expects |

Example after splitting a **5-element** list:

~~~text
line 1: correlationId=group-X, sequenceNumber=1, sequenceSize=5
line 2: correlationId=group-X, sequenceNumber=2, sequenceSize=5
line 3: correlationId=group-X, sequenceNumber=3, sequenceSize=5
line 4: correlationId=group-X, sequenceNumber=4, sequenceSize=5
line 5: correlationId=group-X, sequenceNumber=5, sequenceSize=5
~~~

The **default Aggregator** uses `correlationId` to group messages and `sequenceSize` to tell when the group is full; specifically, **`SequenceSizeReleaseStrategy`** waits for the full sequence indicated by metadata. If only **4 messages** reach the Aggregator because line 3 was dropped, a 5-element group **does not automatically become a complete 4-element batch**.

~~~mermaid
flowchart TD
    S["Splitter: sequenceSize = 5"] --> A["Message 1"]
    S --> B["Message 2"]
    S --> C["Message 3"]
    S --> D["Message 4"]
    S --> E["Message 5"]
    A --> G["Aggregator"]
    B --> G
    C --> F["Filter discard / exception"]
    D --> G
    E --> G
    F -.->|"No reply"| X["Missing item #3"]
    G --> W["Only 4/5: waits for timeout or another policy"]
~~~

### 3.1. Do Not Mutate `sequenceSize` to 4 to Hide Errors

Manually changing `sequenceSize` on the remaining four messages to 4 just to make the Aggregator release can:

- Erase evidence that line 3 ever existed.
- Cause the batch to be misinterpreted as completely successful.
- Create conflicts if item 3 is retried or redelivered late.
- Corrupt correlation in nested Splitter flows.

If partial success is required, send a **typed failure outcome** for item 3 into the group so the group still receives all **5 outcomes**, one of which is `FAILED`.

### 3.2. `sequenceSize` Equal to 0 Does Not Mean an Empty Batch

Spring Integration documentation notes that when a Splitter receives an **Iterator/Iterable** whose element count is unknown upfront, **`sequenceSize`** can be **0**, since total length is unknown. In that situation, you cannot rely on the default `SequenceSizeReleaseStrategy` to detect group completion. You need a different **release policy**, an end marker, timeouts, or materializing a bounded collection before splitting.

For batches with small, strictly bounded item counts, using a **validated `List`** is a simple way to yield a known `sequenceSize`. For huge streams, do not materialize unboundedly into memory just to obtain a count; design an explicit batch-termination protocol and aggregation state instead.

### 3.3. Technical Correlation ID Differs from Business `batchId`

A `batchId` like **batch-2026-11-21-01** may be reused across retries/replays. By contrast, a Splitter-attached `correlationId` belongs to one **specific message-splitting invocation**. Reconstructing the request Message on replay can produce a different technical `correlationId`.

Therefore:

- **`batchId`**: stable logical identifier for status lookup and business deduplication.
- **`lineId`/`lineNo`**: stable element identifier across retries.
- **`correlationId`**: links child messages within one group-processing run.
- **`sequenceNumber`/`sequenceSize`**: serves flow sequencing, not idempotency keys.

If multiple batches share the same `lineNo`, never deduplicate globally by `lineNo` alone.

## 4. Common Mistakes That Interrupt the Entire Batch

### 4.1. Letting Data Exceptions Escape Each Item Transformer

~~~java
// Anti-example under partial-success policy:
.split(ImportBatch.class, ImportBatch::lines)
.transform(ImportLine.class, line ->
        new BigDecimal(line.quantityText())) // "abc" throws.
.channel("validatedLinesChannel")
~~~

When dispatching over a **synchronous `DirectChannel`**, an item exception can propagate back up the Splitter's call stack. If the Splitter has not yet sent subsequent items, those remaining items **may never be dispatched** in the current attempt.

Nor does this prove the Splitter rolls back earlier items: earlier items may already have been processed and committed. A **half-succeeded, half-halted** state is often worse than a clean failure.

### 4.2. Filter Dropping Items While Aggregator Waits for All

~~~java
// Anti-example if Aggregator still expects 5 outcomes:
.split(ImportBatch.class, ImportBatch::lines)
.filter(ImportLine.class, line -> isValid(line))
.aggregate()
~~~

A Filter discard can work when dropped items **do not count as reportable results**. However, if the batch report must account for every input line, silent Filter drops lose error details and stall the group.

### 4.3. Catching Exceptions and Returning `null` in a Transformer

~~~java
// Never turn null into "skip item" inside a Transformer.
.transform(ImportLine.class, line -> {
    try {
        return normalize(line);
    } catch (Exception ex) {
        return null;
    }
})
~~~

**Spring Integration Transformers do not allow returning `null` as a valid transformation result.** Returning `null` is a transformation error. To continue after data errors, return **a non-null outcome object**; to drop messages per policy, use a Filter with an appropriate discard/aggregation branch.

### 4.4. Sending Errors to `errorChannel` Without Emitting an Outcome

An `ErrorMessage` aids observability, yet it is not a `LineOutcome` automatically routed into the Aggregator. If item 3 fails in an async worker and sends only an `ErrorMessage` to `errorChannel`, the Aggregator may still receive only 4/5 replies.

For the Aggregator to finish, a recovery component must **emit a valid failure outcome** carrying the right `batchId`/`lineNo` to the outcome flow (per contract), or the entire batch must be intentionally marked failed/expired. Never silently let a failed message vanish.

### 4.5. Retrying the Whole Batch After One Item Commits

~~~text
Attempt 1:
  line 1 -> COMMITTED
  line 2 -> COMMITTED
  line 3 -> FAIL

Whole-batch retry:
  line 1 -> processed again?
  line 2 -> processed again?
  line 3 -> retried?
~~~

When items have side effects, retries must use **stable idempotency keys** or a transaction boundary matching the business change. A successful `send()` call does not prove side effects committed.

## 5. Designing Individual Outcomes per Element

Under a partial-success policy, an easily testable principle is:

> **Every input item accepted for splitting must yield exactly one terminal outcome within the batch run, even when that item's data is invalid.**

Terminal outcomes can be:

- **SUCCESS**: item passed processing per contract, or side effects were confirmed committed if applicable.
- **REJECTED**: item failed data validation or policy and will not auto-retry.
- **FAILED_FINAL**: a system failure concluded to be unrecoverable automatically.

**PENDING/RETRYING/UNKNOWN** are **non-terminal** states when the system must still retry or reconcile. Never group them under `SUCCESS`; keep the batch `IN_PROGRESS` or emit an interim report explicitly marked incomplete.

A failure outcome is business data, **not an arbitrarily serialized `Throwable`**. It should carry only safe error codes, `lineNo`, `batchId`, and metadata needed for investigation.

~~~mermaid
flowchart TD
    I["ImportLine"] --> P{"Process one line"}
    P -->|"Valid"| S["LineOutcome SUCCESS"]
    P -->|"Invalid data"| F["LineOutcome REJECTED"]
    P -->|"Transient error"| R["Retry item individually<br/>or PENDING in durable store"]
    R -->|"Succeeded"| S
    R -->|"Retries exhausted, terminal"| X["LineOutcome FAILED_FINAL"]
    S --> A["Aggregator"]
    F --> A
    X --> A
    A --> B["Transparent BatchReport<br/>successCount + failureCount"]
~~~

### 5.1. Why Not Catch Every Exception?

Code like **`catch (Exception ex)` → `REJECTED`** turns DB/network outages into permanent data errors. Users cannot fix their input to cure an outage, while a `REJECTED` status stops the system from retrying.

Convert only **expected domain/validation errors** into failure outcomes. Unexpected errors need separate paths: conditional retries, `ErrorMessage`, quarantine, or batch failure status per SLA. For errors where side-effect state is unknowable, record **`UNKNOWN`** and reconcile; never guess `SUCCESS`/`FAILED`.

## 6. Java 17 Example: Batch and Outcome Models

The self-contained example below simulates a data import with **`batchId`**, lines with stable **`lineNo`**, and string-encoded quantities. We start with a **pure** Transformer (no DB writes) to clearly observe how processing continues when one line fails.

### 6.1. Input Model and Batch-Level Validation

~~~java
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

record ImportLine(
        String batchId,
        int lineNo,
        String sku,
        String quantityText) {}

record ImportBatch(String batchId, List<ImportLine> lines) {
    ImportBatch {
        if (batchId == null || !batchId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("INVALID_BATCH_ID");
        }
        Objects.requireNonNull(lines, "lines");
        if (lines.isEmpty() || lines.size() > 1000) {
            throw new IllegalArgumentException("INVALID_BATCH_SIZE");
        }

        lines = List.copyOf(lines);
        Set<Integer> seenLineNumbers = new HashSet<>();
        for (ImportLine line : lines) {
            if (!batchId.equals(line.batchId())
                    || line.lineNo() <= 0
                    || !seenLineNumbers.add(line.lineNo())) {
                throw new IllegalArgumentException(
                        "INVALID_LINE_IDENTITY");
            }
        }
    }
}
~~~

**Why separate these checks?** An invalid `batchId`, empty list, duplicate `lineNo`, or line belonging to another batch are **group structure** errors. If group structure is broken, do not spawn child messages with ambiguous identities. Conversely, `quantityText="abc"` is a **single-line data** error, so it still passes through the Splitter to yield a `REJECTED` outcome.

The 1,000-line cap is an **example application rule**, not a default Spring Integration limit. For larger batches, use chunking/streaming and appropriate completion mechanisms.

### 6.2. Per-Line Outcome

~~~java
import java.util.List;

record LineOutcome(
        String batchId,
        int lineNo,
        String sku,
        String status,
        Integer quantity,
        String errorCode) {

    static LineOutcome success(ImportLine line, int quantity) {
        return new LineOutcome(
                line.batchId(), line.lineNo(), line.sku(),
                "SUCCESS", quantity, null);
    }

    static LineOutcome rejected(ImportLine line, String code) {
        return new LineOutcome(
                line.batchId(), line.lineNo(), line.sku(),
                "REJECTED", null, code);
    }
}

record BatchReport(
        String batchId,
        int total,
        long successCount,
        long failureCount,
        List<LineOutcome> outcomes) {}
~~~

In practice, use **`LineStatus`** and **`ErrorCode`** enums instead of Strings alongside durable processing states. These example records use `String` to keep focus on Splitter–Aggregator mechanics.

### 6.3. Single-Line Transformer Always Returning an Outcome on Data Errors

~~~java
final class ImportLineProcessor {

    LineOutcome process(ImportLine line) {
        String sku = line.sku();
        if (sku == null || !sku.matches("[A-Za-z0-9_-]{1,40}")) {
            return LineOutcome.rejected(line, "INVALID_SKU");
        }

        String raw = line.quantityText();
        if (raw == null || raw.isBlank()) {
            return LineOutcome.rejected(line, "MISSING_QUANTITY");
        }

        int quantity;
        try {
            quantity = Integer.parseInt(raw.trim());
        } catch (NumberFormatException ex) {
            return LineOutcome.rejected(
                    line, "INVALID_QUANTITY_FORMAT");
        }

        if (quantity < 1 || quantity > 10000) {
            return LineOutcome.rejected(
                    line, "INVALID_QUANTITY_RANGE");
        }

        return LineOutcome.success(line, quantity);
    }
}
~~~

**Processor traits:**

1. Same input produces the same output with zero side effects.
2. **Expected** data errors become a **non-null** `REJECTED` outcome.
3. Valid lines yield a `SUCCESS` outcome.
4. Unexpected `RuntimeException` failures are not swallowed.
5. Carries `batchId` and `lineNo` so reports are independent of arrival order.

Because this is a **pure validate/normalize step**, `SUCCESS` here only means **validated**. If the application subsequently writes inventory or ships orders, treat persistence/dispatch as a **distinct business step**—never report committed solely from validation results.

## 7. Aggregating Outcomes into a `BatchReport`

To prevent confusing reports under asynchronous processing, sort results by **`lineNo`** instead of relying on Aggregator arrival order.

~~~java
import java.util.Comparator;
import java.util.List;

import org.springframework.integration.store.MessageGroup;

final class BatchReports {
    private BatchReports() {}

    static BatchReport summarize(MessageGroup group) {
        List<LineOutcome> outcomes = group.getMessages().stream()
                .map(message -> (LineOutcome) message.getPayload())
                .sorted(Comparator.comparingInt(LineOutcome::lineNo))
                .toList();

        if (outcomes.isEmpty()) {
            throw new IllegalStateException("EMPTY_OUTCOME_GROUP");
        }

        String batchId = outcomes.get(0).batchId();
        for (LineOutcome outcome : outcomes) {
            if (!batchId.equals(outcome.batchId())) {
                throw new IllegalStateException(
                        "MIXED_BATCH_IDENTITIES");
            }
        }

        long successful = outcomes.stream()
                .filter(outcome -> "SUCCESS".equals(outcome.status()))
                .count();

        return new BatchReport(
                batchId,
                outcomes.size(),
                successful,
                outcomes.size() - successful,
                List.copyOf(outcomes));
    }
}
~~~

**Important:** grouping messages by `correlationId` is the Aggregator's responsibility. The method above **does not form the group itself**; it only builds the summary once the framework decides to release the group. With default config and a sized `List`, when every child emits an outcome, the Aggregator receives the full sequence. If an outcome is lost to an infrastructure error, the group still needs a timeout/recovery policy.

In applications where a single line can replay twice, also verify **`batchId + lineNo`** identity, duplicate attempts, and group status. Using `List.size()` as total is valid only when the group holds **one final outcome per expected item**.

## 8. Wiring the Steps with Spring Integration Java DSL

Spring Integration supports **`split(Class, function)`** to turn a collection returned from a POJO method into individual child messages. When the Splitter receives a sized collection, the framework attaches default sequencing headers. The Transformer produces one `LineOutcome` per item; the Aggregator uses correlation/sequence to assemble a `BatchReport`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class PartialImportFlowConfig {

    @Bean
    ImportLineProcessor importLineProcessor() {
        return new ImportLineProcessor();
    }

    @Bean
    MessageChannel importBatchInput() {
        return new DirectChannel();
    }

    @Bean
    QueueChannel importBatchReports() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow partialImportFlow(ImportLineProcessor processor) {
        return IntegrationFlow.from("importBatchInput")
                .split(ImportBatch.class, ImportBatch::lines)
                .transform(ImportLine.class, processor::process)
                .aggregate(aggregator -> aggregator
                        .outputProcessor(BatchReports::summarize))
                .channel("importBatchReports")
                .get();
    }
}
~~~

### 8.1. Execution Path When Item 3 Has `quantityText="abc"`

~~~text
ImportBatch (5 lines)
    -> Splitter
        -> ImportLine #1 -> LineOutcome SUCCESS
        -> ImportLine #2 -> LineOutcome SUCCESS
        -> ImportLine #3 -> LineOutcome REJECTED
        -> ImportLine #4 -> LineOutcome SUCCESS
        -> ImportLine #5 -> LineOutcome SUCCESS
    -> Aggregator (correlation from same split; sequenceSize=5)
    -> BatchReport(total=5, successCount=4, failureCount=1)
~~~

**Why does it keep going?** Item 3 does not throw a parse exception out of the endpoint; instead it produces **an outcome message** just like the other items. Thus remaining items are still dispatched by the Splitter in this illustrative synchronous flow, and the Aggregator receives all 5 replies.

**What this example does not guarantee:** survival across restarts, committed side effects, or handling unexpected exceptions inside the processor itself. Those require durable messaging, error flows, retries, and persisted state as covered in the following sections.

### 8.2. Do Not Confuse Aggregated Output with a Whole-Batch Transaction

Receiving a `BatchReport` only proves the outcomes **reached the Aggregator** and were summarized per rule. It does not mean all four `SUCCESS` lines committed in one database transaction. If the business requires **all-or-nothing**, scope transactions around the actual changes—typically validating everything first before committing as a batch.

## 9. Three Operational Policies: Choose Before Writing the Flow

### 9.1. Partial Success

Use when **items are independent** and the domain accepts processing valid parts:

1. Validate batch identity and item count limit before the Splitter.
2. Validate each item independently.
3. Invalid items return a `REJECTED` outcome with `errorCode`, never dropped by a Filter.
4. Valid items advance to downstream business processing if needed.
5. `BatchReport` is marked `COMPLETED` only once a **terminal outcome exists for every item**.

Suited for catalog imports, independent bulk updates, or processing independent events.

### 9.2. All-or-Nothing

Use when **a single error requires canceling the entire request**:

~~~mermaid
flowchart TD
    B["Batch input"] --> V["Validate all items (no side effects)"]
    V -->|"Any invalid item"| R["Reject whole batch, clear error"]
    V -->|"All valid"| T["Start business transaction"]
    T --> S["Apply all changes in same DB"]
    S --> C{"Commit succeeded?"}
    C -->|"Yes"| OK["Batch SUCCESS"]
    C -->|"No"| X["Rollback / error state"]
~~~

When all mutations live in **one database transaction**, everything can roll back on failure. Never claim a database transaction also rolls back emails, payments, or external APIs. Across multiple systems, you may need **Saga/compensation** or rejecting requests before starting side effects.

### 9.3. Eventual Completion for Transient Errors

Use when an item must wait for an external service to recover:

~~~text
Batch 5 items:
  line 1 = COMPLETED
  line 2 = COMPLETED
  line 3 = RETRYING
  line 4 = COMPLETED
  line 5 = COMPLETED

Batch state = IN_PROGRESS (4 terminal, 1 still pending)
~~~

If after controlled attempts line 3 is confirmed unrecoverable, its final status can become `FAILED_FINAL` and the batch report becomes `PARTIAL_SUCCESS`. If line 3 succeeds, the batch completes fully.

**Never let an interim `PENDING` result cause an Aggregator to report the batch complete** if the contract demands final outcomes. You may emit a separate **snapshot** report marked `IN_PROGRESS`, which is distinct from a terminal report.

## 10. When Items Have Side Effects: Per-Line Idempotency

If each valid line writes to a database or calls another system, a replay could reprocess already-succeeded lines. Per-item logic must be **idempotent**.

Common key structure:

~~~text
logicalItemKey = tenantId + ":" + batchId + ":" + lineNo + ":" + revision
~~~

- **`tenantId`** must come from verified identity/context, not solely from an unverified client header.
- **`batchId`** identifies one business batch.
- **`lineNo`** identifies the stable item position within the batch.
- **`revision`** distinguishes a valid resubmission after rejection from a replay of the same request. If editing the same batch is disallowed, fix `revision=1` and assign a new `batchId` for new submissions.

Never use `MessageHeaders.ID` or `sequenceNumber` alone as business keys: message IDs change upon reconstruction, and `sequenceNumber` only applies within one split invocation.

### 10.1. Per-Item State Must Be Persisted Durably

| Status | Meaning | On Redelivery with Same Key |
| --- | --- | --- |
| **PENDING** | No effect yet | Eligible to claim for processing |
| **PROCESSING** | A worker is executing | Check lease/lock; prevent concurrent workers |
| **COMPLETED** | Effect confirmed committed | Skip duplicate side effect; return stored outcome |
| **REJECTED** | Terminal data error for this revision | Return stored errorCode; do not retry endlessly |
| **FAILED_RETRYABLE** | Transient infrastructure failure | Retry with backoff and budget |
| **UNKNOWN** | Unclear if external effect occurred | Reconcile using operation key |
| **FAILED_FINAL** | Automatic retries exhausted | Quarantine; requires intervention |

An implementation can persist `LineOutcome` alongside status in an inbox or processing ledger table. If a worker crashes, another process uses the item key to tell whether to resume or skip.

### 10.2. SQL Example with a Unique Constraint

~~~sql
CREATE TABLE batch_line_execution (
    tenant_id VARCHAR(80) NOT NULL,
    batch_id VARCHAR(80) NOT NULL,
    line_no INTEGER NOT NULL,
    revision INTEGER NOT NULL,
    status VARCHAR(24) NOT NULL,
    error_code VARCHAR(80),
    completed_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, batch_id, line_no, revision)
);

CREATE TABLE import_stock_adjustment (
    tenant_id VARCHAR(80) NOT NULL,
    batch_id VARCHAR(80) NOT NULL,
    line_no INTEGER NOT NULL,
    revision INTEGER NOT NULL,
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, batch_id, line_no, revision)
);
~~~

Assuming a shared database/transaction manager and a method recording items post-validation:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class StockImportService {
    private final JdbcTemplate jdbc;

    StockImportService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void applyOnce(
            String trustedTenantId,
            LineOutcome result,
            int revision) {

        if (!"SUCCESS".equals(result.status())) {
            throw new IllegalArgumentException("Item is not valid");
        }

        int acquired = jdbc.update("""
                INSERT INTO batch_line_execution
                    (tenant_id, batch_id, line_no, revision, status)
                VALUES (?, ?, ?, ?, 'PROCESSING')
                ON CONFLICT DO NOTHING
                """,
                trustedTenantId,
                result.batchId(), result.lineNo(), revision);

        if (acquired == 0) {
            String status = jdbc.queryForObject("""
                    SELECT status FROM batch_line_execution
                     WHERE tenant_id = ? AND batch_id = ?
                       AND line_no = ? AND revision = ?
                    """,
                    String.class,
                    trustedTenantId,
                    result.batchId(), result.lineNo(), revision);
            if ("COMPLETED".equals(status)) {
                return; // Idempotent: effect already recorded previously.
            }
            throw new IllegalStateException(
                    "Item already claimed but not yet completed");
        }

        jdbc.update("""
                INSERT INTO import_stock_adjustment
                    (tenant_id, batch_id, line_no, revision, sku, quantity)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                trustedTenantId,
                result.batchId(), result.lineNo(), revision,
                result.sku(), result.quantity());

        jdbc.update("""
                UPDATE batch_line_execution
                   SET status = 'COMPLETED',
                       completed_at = CURRENT_TIMESTAMP
                 WHERE tenant_id = ? AND batch_id = ?
                   AND line_no = ? AND revision = ?
                """,
                trustedTenantId,
                result.batchId(), result.lineNo(), revision);
    }
}
~~~

This snippet illustrates **recording a single adjustment record**, without yet updating live stock counts or handling all domain errors. To mutate inventory balances, execute appropriately constrained updates **within the same transaction**. `trustedTenantId` must be verified, `revision` validated, and input/quantities checked before calling the service.

Because all DB writes share one transaction, the first run records ledger and adjustment and commits; a retry seeing `COMPLETED` skips writing a second adjustment. If an exception rolls back before commit, both ledger and adjustment roll back, permitting safe retry. If two workers race on the same key, the unique constraint and row lock prevent duplicate effects.

**Limitation:** this does not create exactly-once effects when items call external HTTP APIs or send emails. Those require provider idempotency keys, outboxes, and reconciliation.

### 10.3. Partial Success Does Not Mean Blindly Retrying the Whole Batch

Suppose 4 lines already wrote adjustments while line 3 was `REJECTED` for bad formatting. When the user fixes line 3:

- Keep `batchId + lineNo` identity yet **increment `revision`** or issue a new operation ID per contract.
- Submit only the fixed element; do not re-apply effects for the four `COMPLETED` lines.
- If replaying the whole batch anyway, each item processor must check idempotency to skip completed side effects.
- Batch reports must distinguish the **revision 1 report** from **current post-fix state**, never overwriting history without audit.

## 11. Error Channel and Exception Scope

A Splitter **does not provide fault isolation** merely by splitting messages. How handlers and channels are wired governs how errors propagate.

### 11.1. Synchronous `DirectChannel`

~~~text
Splitter -> DirectChannel -> item handler
                                  |
                                  +-- throws RuntimeException
~~~

The handler runs on the sender's call stack. An unhandled exception can abort dispatching subsequent children after earlier children already ran. The caller may receive an exception from sending the batch, yet **never assume earlier side effects rolled back**.

### 11.2. `ExecutorChannel` / `QueueChannel` / Broker

~~~text
Splitter -> executor/queue -> item worker
                               |
                               +-- success -> LineOutcome -> Aggregator
                               |
                               +-- failure -> ErrorMessage/errorChannel
~~~

Failures in async workers can be routed by Spring Integration as an **`ErrorMessage`** to a configured error channel, rather than returning to the batch-submitting thread. However, an `ErrorMessage` **does not automatically become a `LineOutcome`**, and a failed message does not automatically count toward the Aggregator's group.

To deliver final reports for every item, build a **recovery adapter**:

1. Extract reliable `batchId` and `lineNo` from `failedMessage`/`originalMessage` (may be absent in certain errors).
2. Classify error: permanent data error, transient, or `UNKNOWN`.
3. Retry the individual item or persist state.
4. Only upon reaching a terminal state, emit **one unique `LineOutcome`** with proper correlation/sequence metadata; never emit a duplicate outcome if the worker also succeeded.
5. Route the outcome to the Aggregator or reporting store per contract.

### 11.3. Do Not Treat `ErrorMessage` as a Durable DLQ

A channel named **`batchItemErrors`** does not guarantee failed messages survive application restarts. If items must be replayable, use a durable store/broker, define ack/commit semantics, and configure retry/DLQ policies. If the error flow itself throws, monitor it separately—never loop errors endlessly back into the Splitter.

### 11.4. Classify Errors to Avoid Masking Incidents

| Error Type | Can Return `REJECTED` Immediately? | Rule |
| --- | --- | --- |
| Unparseable quantity | Yes | Clear error code; other items continue |
| Missing SKU | Yes | Validation error; do not blindly retry |
| Item violates tenant permissions | Reject or security-fail batch | Never process unauthorized items |
| DB deadlock | No | Retry transaction per item |
| Database offline | No | Keep PENDING/RETRYING or fail batch recoverably |
| HTTP timeout post side effect | Cannot conclude | UNKNOWN; reconcile/use idempotency key |
| Bug-induced `NullPointerException` | Never label `REJECTED` | Alert, fix bug, maintain replay policy |
| Output channel has no consumers | No | Topology/dispatch error |

**Catch specific exception types at the right boundary.** Never use a blanket `catch(Throwable)` that disguises system or programming failures as neat `REJECTED` statuses.

## 12. Aggregator Timeouts and Partial Results

When a child message never reaches the Aggregator, define a policy **for incomplete groups**:

- **`groupTimeout`**: how long a group may wait for remaining messages.
- **`sendPartialResultOnExpiry`**: whether to emit messages received so far upon expiry.
- **`MessageGroupStore`**: where group state lives; use a persistent store to survive restarts.
- **discard channel**: handles late or policy-dropped messages.
- **group expiration**: manages group lifecycle and prevents unbounded stale groups.

Tune these settings for your **Spring Integration version** and business contract; none of them automatically fabricates failed outcomes for missing items.

### 12.1. Partial Aggregation Is Not Batch Success

~~~text
Expected line numbers: [1, 2, 3, 4, 5]
Arrived outcomes:      [1, 2,    4, 5]
Timeout:               30 seconds

Partial report:
  batchStatus = INCOMPLETE
  expected = 5
  received = 4
  missing = [3]
~~~

If partial results are enabled on timeout, **mark the report `INCOMPLETE`** and surface missing items from a trusted manifest/metadata. Do not use the earlier `BatchReports.summarize()` naively and accept `total=4` as complete, since it cannot know the manifest expected 5 when one item vanished completely.

To pinpoint exactly which items are missing, persist a **manifest with `batchId` + all `lineNo` values**, or store expected item identities in a durable processing store. `sequenceSize` gives expected count, yet cannot replace a full manifest when reconciling by item identity.

### 12.2. Late Arrivals and Group Lifecycle

An item can arrive **after the group has already released or expired**:

- If a tombstone/empty-group marker remains to recognize completion, late messages can be discarded per policy.
- If the group was completely purged, a late message with the same correlation can spawn **a brand-new group**, generating duplicate reports.
- If groups linger too long, the message store can grow unboundedly.

Explicitly specify late-arrival policies, retention, unique batch report keys, and report upsert/update rules. Never assume enabling `expireGroupsUponCompletion` is harmless: it directly impacts late arrivals and duplicates.

### 12.3. You Do Not Always Need an Aggregator for Every Batch

For workflows whose items can take days, a **batch/item status table** and a completion job checking terminal outcome counts can be far more reliable than holding messaging groups open indefinitely.

~~~mermaid
flowchart LR
    B["Batch manifest DB"] --> D["Distribute item tasks"]
    D --> W["Per-item workers"]
    W --> S["Item status DB"]
    S --> C{"All terminal statuses?"}
    C -->|"No"| P["Batch IN_PROGRESS"]
    C -->|"Yes"| R["BatchReport COMPLETED / PARTIAL"]
~~~

This remains the **split, process independently, aggregate outcomes** pattern, except final aggregation reads **durable state** rather than relying solely on an in-memory `MessageGroup`. Choose based on batch size, wait duration, SLAs, and replay requirements.

## 13. Unit Tests: One Bad Line Does Not Affect Other Lines

Before booting a Spring context, test `ImportLineProcessor` as a pure function. The tests below use JUnit 5.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class ImportLineProcessorTest {
    private final ImportLineProcessor processor =
            new ImportLineProcessor();

    @Test
    void validLineProducesSuccessOutcome() {
        ImportLine line = new ImportLine(
                "batch-10", 1, "SKU-A", "3");

        LineOutcome result = processor.process(line);

        assertEquals("SUCCESS", result.status());
        assertEquals(3, result.quantity());
        assertNull(result.errorCode());
        assertEquals("batch-10", result.batchId());
        assertEquals(1, result.lineNo());
    }

    @Test
    void oneMalformedLineProducesRejectedOutcome() {
        ImportLine bad = new ImportLine(
                "batch-10", 3, "SKU-C", "abc");

        LineOutcome outcome = processor.process(bad);

        assertNotNull(outcome);
        assertEquals("REJECTED", outcome.status());
        assertEquals(
                "INVALID_QUANTITY_FORMAT",
                outcome.errorCode());
        assertEquals(3, outcome.lineNo());
    }

    @Test
    void malformedMiddleDoesNotChangeOtherResults() {
        LineOutcome first = processor.process(
                new ImportLine("batch-10", 1, "SKU-A", "3"));
        LineOutcome middle = processor.process(
                new ImportLine("batch-10", 2, "SKU-B", "invalid"));
        LineOutcome last = processor.process(
                new ImportLine("batch-10", 3, "SKU-C", "5"));

        assertEquals("SUCCESS", first.status());
        assertEquals("REJECTED", middle.status());
        assertEquals("SUCCESS", last.status());
    }

    @Test
    void rejectsMissingSkuAndOutOfRangeQuantity() {
        assertEquals("INVALID_SKU", processor.process(
                new ImportLine("batch-10", 1, "", "3"))
                .errorCode());
        assertEquals("INVALID_QUANTITY_RANGE", processor.process(
                new ImportLine("batch-10", 2, "SKU-B", "10001"))
                .errorCode());
    }
}
~~~

### 13.1. Validating Batch Structure Before Splitter

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import org.junit.jupiter.api.Test;

class ImportBatchContractTest {

    @Test
    void duplicateLineNumbersAreRejectedBeforeSplit() {
        assertThrows(IllegalArgumentException.class,
                () -> new ImportBatch("batch-11", List.of(
                        new ImportLine("batch-11", 1, "SKU-A", "2"),
                        new ImportLine("batch-11", 1, "SKU-B", "3"))));
    }

    @Test
    void emptyBatchRequiresExplicitBusinessHandling() {
        assertThrows(IllegalArgumentException.class,
                () -> new ImportBatch("batch-12", List.of()));
    }

    @Test
    void invalidQuantityIsStillPermittedForItemLevelReporting() {
        ImportBatch batch = new ImportBatch("batch-13", List.of(
                new ImportLine("batch-13", 1, "SKU-A", "abc")));
        assertEquals(1, batch.lines().size());
    }
}
~~~

The last test is crucial: **do not validate quantity inside the batch-level constructor** if the goal is per-line reporting. If the constructor throws when item 1 is bad, the user never receives a report for the remaining items.

## 14. Integration Test: Three Outcomes for Three Items

Use `DirectChannel` and `QueueChannel` in tests to read outcomes right after `send()`. No `Thread.sleep` is needed because this example runs synchronously.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(PartialImportFlowConfig.class)
class PartialImportFlowTest {

    @Autowired
    @Qualifier("importBatchInput")
    MessageChannel input;

    @Autowired
    @Qualifier("importBatchReports")
    QueueChannel reports;

    @BeforeEach
    void clearReports() {
        while (reports.receive(0) != null) {
            // Drain queue if Spring context is reused between tests.
        }
    }

    @Test
    void oneBadMiddleItemDoesNotLoseTheBatch() {
        ImportBatch batch = new ImportBatch("batch-201", List.of(
                new ImportLine("batch-201", 1, "SKU-A", "3"),
                new ImportLine("batch-201", 2, "SKU-B", "abc"),
                new ImportLine("batch-201", 3, "SKU-C", "5")));

        assertTrue(input.send(
                MessageBuilder.withPayload(batch).build()));

        Message<?> response = reports.receive(0);
        assertNotNull(response);
        BatchReport report = (BatchReport) response.getPayload();

        assertEquals("batch-201", report.batchId());
        assertEquals(3, report.total());
        assertEquals(2, report.successCount());
        assertEquals(1, report.failureCount());
        assertEquals(
                List.of(1, 2, 3),
                report.outcomes().stream()
                        .map(LineOutcome::lineNo).toList());
        assertEquals(
                "INVALID_QUANTITY_FORMAT",
                report.outcomes().get(1).errorCode());
        assertEquals("SUCCESS", report.outcomes().get(2).status());
        assertNull(reports.receive(0));
    }

    @Test
    void allInvalidItemsStillProduceACompleteReport() {
        ImportBatch batch = new ImportBatch("batch-202", List.of(
                new ImportLine("batch-202", 1, "", "2"),
                new ImportLine("batch-202", 2, "SKU-B", "0")));

        assertTrue(input.send(
                MessageBuilder.withPayload(batch).build()));

        Message<?> response = reports.receive(0);
        assertNotNull(response);
        BatchReport report = (BatchReport) response.getPayload();

        assertEquals(2, report.total());
        assertEquals(0, report.successCount());
        assertEquals(2, report.failureCount());
        assertEquals(
                List.of("REJECTED", "REJECTED"),
                report.outcomes().stream()
                        .map(LineOutcome::status).toList());
    }

    @Test
    void firstAndLastFailuresDoNotHideValidMiddle() {
        ImportBatch batch = new ImportBatch("batch-203", List.of(
                new ImportLine("batch-203", 1, "SKU-A", "abc"),
                new ImportLine("batch-203", 2, "SKU-B", "7"),
                new ImportLine("batch-203", 3, "SKU-C", "-1")));

        assertTrue(input.send(
                MessageBuilder.withPayload(batch).build()));

        BatchReport report = (BatchReport) reports.receive(0).getPayload();
        assertEquals(1, report.successCount());
        assertEquals(2, report.failureCount());
        assertEquals("SUCCESS", report.outcomes().get(1).status());
    }
}
~~~

### 14.1. What Exactly Does the Integration Test Above Prove?

It proves:

- One `ImportBatch` input is split by Splitter into multiple child messages.
- A data error in one child becomes a **non-null `LineOutcome` `REJECTED`**.
- Other children still produce successful outcomes.
- The Aggregator releases one `BatchReport` with accurate counts in the illustrative synchronous flow.

It **does not yet prove**:

- That `errorChannel` automatically converts every unexpected exception into an outcome.
- That batches are persisted durably or survive restarts.
- That side effects run exactly once across retries/redeliveries.
- That synchronous results match `ExecutorChannel`/broker semantics.

Claim only what the test actually observes.

## 15. Testing Missing Items, Retries, and Asynchronous Dispatch

With `ExecutorChannel`, a worker handling line 3 may time out while lines 1, 2, 4, and 5 finish. This case **differs** from a validation error on line 3: no terminal outcome may exist yet for line 3.

### 15.1. Testing an Unexpected Item Failure

Create a test processor that intentionally throws `IllegalStateException` on line 3. Verify:

1. `ErrorMessage` identifies the failing item if error channel configuration supports it.
2. No full success `BatchReport` is emitted while line 3's outcome is missing.
3. Batch state remains `IN_PROGRESS`/`FAILED` per policy, never falsely reporting full completion.
4. If using timeout/partial release, the report shows **`expected=5, received=4, missing=[3]`**.
5. Once recovered via retry, line 3 produces **one** terminal outcome and the batch completes.

### 15.2. Testing Concurrency When the Same Item Is Redelivered

Simulate two workers processing the same key **`tenant-A:batch-204:3:revision-1`**:

- Only one worker may commit the side effect.
- The other worker returns the stored outcome or waits for state to return the accurate result.
- If the first worker crashes before commit, the second worker has a valid retry path.
- If the first worker committed yet the response was lost, redelivery **does not write the side effect twice**.

Verify against a real database with primary keys/unique constraints and transactions rather than inferring multi-instance safety from a local `ConcurrentHashMap`.

### 15.3. Testing Aggregator Timeouts and Late Arrivals

For a group expecting 5 messages, intentionally send only 4 outcomes:

1. Verify no completed `BatchReport` emits by default.
2. Trigger group timeout per test config and observe discard/partial-result behavior.
3. When emitting a partial report, **require an `INCOMPLETE` status** in the result contract.
4. Send the 5th outcome after timeout and verify the late-arrival policy: discard, emit revised report, or reconcile via durable state.
5. Replay using the same `batchId` yet a fresh `correlationId`; verify two terminal reports are not recorded as two independent batches.

### 15.4. Testing Iterators with Unknown `sequenceSize`

Have Splitter emit from an `Iterator` instead of a `List`. Verify `sequenceSize` alone cannot drive default group release. Then configure an explicit completion marker or suitable release strategy. Never arbitrarily set `sequenceSize` to the count seen so far before the source signals completion.

## 16. Preventing Subtle Forms of Data Loss

### 16.1. Empty Input

If Splitter returns an **empty collection**, no child messages reach the Aggregator. Depending on version and config, Splitter supports a **`discardChannel`** to receive requests producing no items; `null` from a split method has different semantics from an empty collection.

For imports, you can:

- **Reject empty batches before splitting** as the `ImportBatch` constructor does.
- Return an **explicit empty `BatchReport`** from a dedicated branch if the domain permits.
- Send the request to a discard channel for logging/reconciliation.

Never wait for an Aggregator to build a report from a group that **received zero messages**.

### 16.2. An Element Containing `null`

A `List` containing `null` elements can hit Java, conversion, or message payload limits (Spring `Message` rejects `null` payloads under standard contracts). If an input can omit a line, represent it as a **typed data-error object with identity** or validate the batch and emit a matching `REJECTED` outcome; never rely on emitting `null` as a child message.

In this example, **`List.copyOf`** rejects `null` items when constructing `ImportBatch`, treating them as batch-structural errors. That is an intentional policy of the example; applications needing per-line blank reporting must model blank lines explicitly (e.g., `RawLine` with an optional field), never by passing `null`.

### 16.3. Failure Mid-Way Reading a File or Stream

When Splitter pulls items from an `Iterator`, an exception reading the 501st element can happen **after the first 500 items have already been dispatched**. For durable replay and reconciliation:

1. Persist input or manifests in checksummed/offset-tracked chunks.
2. Record which items were dispatched and which reached terminal state.
3. Never assume reading to EOF succeeded if the iterator throws.
4. On recovery, use stable offsets/`lineId` values and per-item idempotency.
5. For unsized streams, implement an explicit **end-of-batch marker** or dedicated completion state.

### 16.4. A Branch Dropped by a Filter

A Filter with `discardChannel` can **route dropped messages to another branch**. If the batch report must cover all items, the discard branch can construct a **`REJECTED` outcome** and forward it to the same aggregate input per design; preserve correlation and avoid duplicate terminal outcomes.

However, if a Filter sits **before the Splitter** to reject an entire unauthorized batch, that is a different decision: there is no need to emit per-item outcomes for an unaccepted batch.

### 16.5. Reordering Under Parallel Processing

With `ExecutorChannel`, item 5 can finish before item 1. The Aggregator may receive messages in **arrival order**, not `lineNo` order. Therefore:

- Never assume `MessageGroup` iteration order matches input order.
- Sort reports by **`lineNo`** as `BatchReports.summarize()` does.
- If side effects must execute **in strict order**, design sequencing/resequencers or serial processing separately; sorting a final report does not reorder earlier side effects.

### 16.6. Two Outputs for Two Executions of the Same Item

Redelivery can cause item 3 to emit **two `LineOutcome` messages**. Feeding both into an Aggregator without deduplication can cause:

- More outcomes counted than actual items.
- Premature group release or discarded late messages.
- Two terminal reports for the same batch if group lifecycle is unmanaged.

Never let `sequenceSize` mask duplicates; guard with **item identity + revision**, durable inboxes/ledgers, and the rule of **one unique terminal outcome per logical item**.

## 17. Monitoring at Both Batch and Item Levels

To know whether one line is losing an entire batch, measure both levels:

| Metric/Status | Purpose |
| --- | --- |
| **`batch_received_total`** | Batches ingested |
| **`batch_rejected_total{reason}`** | Batches failing structural/auth checks pre-split |
| **`batch_items_expected`** | Items in manifest, not merely arrived messages |
| **`item_attempts_total{step}`** | Per-item processing attempts |
| **`item_outcomes_total{status,error_code}`** | Terminal outcomes by type |
| **`item_retry_total`** | Retry attempts |
| **`batch_completed_total{status}`** | Terminal batches (success/all-failed/partial) |
| **`batch_incomplete_total`** | Batches missing outcomes past SLA |
| **`aggregator_group_timeout_total`** | Groups exceeding wait timeout |
| **`aggregator_late_arrival_total`** | Outcomes arriving after group close |
| **`duplicate_item_skipped_total`** | Duplicate side effects prevented |
| **`error_channel_delivery_failed_total`** | Failures along error reporting paths |
| **`batch_processing_age_seconds`** | Age of non-terminal batches |

Bound metric label cardinality. **Do not put `batchId`, `lineNo`, `userId`, or `tenantId`** directly as metric labels when cardinality is high; use access-controlled traces/logs to look up details.

### 17.1. Item Error Log Example

~~~json
{
  "batchId": "batch-201",
  "lineNo": 2,
  "stage": "quantity-validation",
  "status": "REJECTED",
  "errorCode": "INVALID_QUANTITY_FORMAT",
  "retryable": false
}
~~~

Never log raw item payloads or secrets to avoid data leaks. If invalid inputs must be saved for user repair, store them in quarantine with proper access control and retention.

### 17.2. Count Reconciliation

A useful invariant:

~~~text
expectedItemCount =
    completedItemCount
  + rejectedItemCount
  + failedFinalItemCount
  + pendingItemCount
~~~

In systems with retries, these counts must represent **unique logical items**, not attempt counts. If an item is attempted 5 times, it is still **one item** in the manifest. Checking this invariant catches lost items and duplicate outcomes.

### 17.3. Alert on Business Signals Instead of Exception Rate Alone

Alert when:

- A batch remains `IN_PROGRESS` past SLA.
- An expected item lacks a terminal outcome and has no active retry job.
- Aggregator holds many waiting groups or hits timeouts.
- `REJECTED` rate spikes abruptly (producer may have changed schema).
- An item retries repeatedly without changing state.
- Multiple terminal outcomes appear for the same `batchId + lineNo + revision`.
- A `BatchReport` reports `SUCCESS` yet counts disagree with the manifest.
- The error flow fails to store/quarantine failed messages.

## 18. Hands-On Exercise: Shipment Reconciliation Batch

Design a pipeline receiving:

~~~java
record RawShipmentRow(
        String batchId,
        int rowNo,
        String shipmentId,
        String declaredWeightGrams) {}

record ShipmentImportBatch(
        String batchId,
        java.util.List<RawShipmentRow> rows) {}
~~~

Input has 6 rows:

| Row | `shipmentId` | `declaredWeightGrams` | Expected |
| --- | --- | --- | --- |
| 1 | SH-101 | 500 | SUCCESS |
| 2 | SH-102 | 250 | SUCCESS |
| 3 | SH-103 | wrong | REJECTED |
| 4 | SH-104 | 1000 | SUCCESS |
| 5 | SH-105 | -10 | REJECTED |
| 6 | SH-106 | 700 | SUCCESS |

**Requirements**

1. Validate `batchId`, maximum row count, and unique `rowNo` before splitting.
2. Split each row into an independent message with proper correlation/sequence.
3. Every row must yield a terminal **`RowOutcome`** containing `rowNo`, `status`, `errorCode`, and normalized data on success.
4. The two invalid rows must not cause the four valid rows to be lost.
5. Aggregator emits one report with **6 outcomes: 4 `SUCCESS` and 2 `REJECTED`**.
6. Report is sorted by `rowNo` despite parallel execution.
7. If the database goes offline on row 4, that row enters an appropriate `RETRYING`/`UNKNOWN` state rather than turning into a validation error.
8. When retrying the same logical item, never record an adjustment twice.
9. If an item never emits an outcome, the batch gets `INCOMPLETE` status with a recovery path.

**Implementation Steps**

1. Write `ShipmentBatchValidator` checking group structure.
2. Write pure `ShipmentRowTransformer` returning a typed `RowOutcome` for data errors.
3. Build an `IntegrationFlow` with Splitter → Transformer → Aggregator → report channel.
4. Test failing items at start, middle, end, and all-invalid inputs.
5. Temporarily replace the Transformer with logic throwing an exception on row 3 to observe how it differs from a failure outcome.
6. Insert a Filter before the Aggregator dropping row 3, then demonstrate the group stalls with missing results and must not report `SUCCESS`.
7. Switch to `ExecutorChannel` with a bounded executor and test out-of-order arrivals.
8. Create a processing ledger keyed by `batchId + rowNo + revision` and test retries after commit and rollback.
9. Design manifest/timeouts to detect non-terminal items and late arrivals.
10. Build a dashboard tracking batch status, item status, open groups, and p95 completion time.

### Self-Check Questions

1. Does Splitter automatically provide per-item fault isolation?
2. When item 3 throws on `DirectChannel`, what can happen to items 4 and 5?
3. Why can a Filter dropping item 3 make an Aggregator wait forever?
4. What roles do `correlationId`, `sequenceNumber`, and `sequenceSize` play?
5. Does `sequenceSize=0` from an `Iterator` mean an empty batch?
6. How does a `REJECTED` `LineOutcome` differ from an `ErrorMessage` on `errorChannel`?
7. When should one item's error reject the entire batch under an all-or-nothing policy?
8. Why should you not catch all `Exception` types and mark every item `REJECTED`?
9. How do you guarantee each item yields exactly one terminal outcome across redeliveries?
10. Does a `BatchReport` emitted by an Aggregator prove the database committed?
11. Should a partial result on timeout ever report the whole batch as `SUCCESS`?
12. When fixing a bad line and replaying, why do you need a new `revision` or operation identity?
13. Why must group timeouts, persistence, and late-arrival policies be designed together?
14. When using `ExecutorChannel`, do outcomes arrive at the Aggregator in original line order?

## 19. Pre-Deployment Checklist

- Explicitly chose **fail-fast, all-or-nothing, partial success, or eventual completion**.
- Separated batch structural validation from item-level validation.
- Input has stable `batchId`/`lineNo` and reliable manifest/count.
- Bounded batch size and resource usage; no unbounded collection materialization.
- Every valid or malformed item produces **one terminal outcome**, never returning `null`.
- System/transient/`UNKNOWN` errors are never mislabeled as `REJECTED`.
- Splitter and downstream preserve correlation/sequence when using an Aggregator.
- Iterators/streams have completion policies; never assume `sequenceSize` is always known upfront.
- Filter discards and `errorChannel` are handled intentionally without dropping outcomes.
- Aggregator timeouts/partial results mark batches `INCOMPLETE` when items are missing.
- `MessageGroupStore`, group expiration, and late-arrival policies align with SLAs.
- Side effects enforce **idempotency by logical item + revision**.
- DB effects use unique constraints/transactions; external effects use keys/reconciliation.
- Data correction and replay rules avoid duplicating already-completed items.
- Error flows/quarantine have real consumers, durability, and retention.
- Tests cover first/middle/last item errors, all-invalid, missing items, async execution, retries, and crashes.
- Monitoring separates attempts, logical items, terminal outcomes, and batch completion.

**Conclusion:** Splitter merely breaks a message into elements; it does not decide on its own whether the whole batch should halt or continue. To **prevent one bad element from accidentally losing the entire batch**, declare a partial-success policy, preserve per-item identity, turn expected data errors into **typed, non-null outcomes**, and use an Aggregator with sound correlation/sequence to build accurate reports. For infrastructure failures, add per-item retries, durable state, timeouts, and idempotency. That way, one bad element never silently erases the rest, while serious failures are still caught rather than hidden.

## References

- [Spring Integration Reference — Splitter](https://docs.spring.io/spring-integration/reference/splitter.html): Splitter role, message headers, Iterator/`sequenceSize`, and discard semantics.
- [Spring Integration Reference — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html): correlation, release strategy, group timeout, partial results, late arrivals, and `MessageGroupStore`.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): configuring split, aggregate, and channels.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): `DirectChannel`, async error messages, and error channels.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): `DirectChannel`, `ExecutorChannel`, `QueueChannel`, and dispatch semantics.
- [Spring Integration Reference — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): deduplication support and limits of pre-side-effect claims.
- [Enterprise Integration Patterns — Splitter](https://www.enterpriseintegrationpatterns.com/patterns/messaging/Sequencer.html): EIP foundation for Splitter and message-splitting rules.
- [Enterprise Integration Patterns — Aggregator](https://www.enterpriseintegrationpatterns.com/patterns/messaging/Aggregator.html): combining related messages into a single result.
