# Choosing Skip vs. Fail Fast — Design Decisions in Spring Batch

## 1. The Design Question: Should One Bad Record Stop the Whole Job?

A batch job receives 100,000 orders from a partner. After reading 20,000 rows, the processor encounters an order with a negative amount. There are at least two ways to handle this:

- **Skip**: bypass this invalid record, log/record the error for later remediation, and continue processing the remaining rows.
- **Fail fast**: treat the error as unacceptable, terminating the step/job in `FAILED` status instead of continuing to process further data.

Neither option is right for every job. If a job imports a product catalog for search indexing, skipping a few malformed rows may be acceptable. If a job builds an accounting balance sheet or generates payment transfer instructions, dropping even a single record can render the entire result unusable.

In **Spring Batch Core Processing**, this decision directly affects:

1. **Completeness and accuracy** of the output.
2. **`JobExecution`/`StepExecution` status** and monitoring.
3. **Transactions, rollbacks, and restartability**.
4. **Processing cost and recoverability** when the data source contains many errors.
5. **Explainability and auditability** of which records were excluded and why.
6. **Downstream pipeline trust**: consumers may mistakenly interpret a `COMPLETED` job as meaning 100% of the input was valid.

This lesson belongs to the **Design Decisions** group and focuses on choosing **skip vs. fail fast** for errors in `ItemReader`, `ItemProcessor`, and `ItemWriter`. Examples target **Java 17+, Spring Boot 3.x, Spring Batch 5.x, JUnit 5, and a JDBC `JobRepository`**. For other framework versions, check the corresponding APIs and configuration.

### Objectives

After this lesson, you will be able to:

- Distinguish `skip`, `filter`, `retry`, `fail fast`, and `quarantine`.
- Formulate a handling policy based on error type, severity, volume, and business impact.
- Use `.faultTolerant().skip(...).skipLimit(...)` alongside `.noSkip(...)` and `.retry(...)` appropriately.
- Understand `readSkipCount`, `processSkipCount`, and `writeSkipCount`.
- Design auditing for skipped records without duplicating side effects on rollback/restart.
- Test skip thresholds, job statuses, checkpoints, output completeness, and quality gates.
- Recognize situations where you **should not continue** even though Spring Batch can skip an exception.

---

## 2. First: Skip, Filter, Retry, and Fail Fast Are Not the Same

### 2.1. Four Core Behaviors

```text
        ItemReader.read()
                |
                v
        ItemProcessor.process(item)
                |
          +-----+--------------------+
          |                          |
      returns output O           returns null
          |                          |
          v                          v
   ItemWriter.write(chunk)       FILTERED
          |
          +---------- exception ---------+
                                        |
                              Fault-tolerant policy
                                        |
                    +-------------------+----------------+
                    |                   |                |
                  RETRY                SKIP            FAIL
             bounded retry         bounded skip     terminate failed
                    |                   |                |
                    v                   v                v
                success?          keep processing   Step FAILED
                    |              other items
                    v
                continue
```

**Filter** is a business decision inside the processor: returning `null` so an item does not reach the writer. It requires no exception and does not consume `skipLimit`.

**Skip** is a fault-tolerance mechanism when a reader, processor, or writer throws an exception configured as *skippable*. Spring Batch can bypass the failing item and continue within a configured limit.

**Retry** re-attempts an operation after a recoverable error, such as a deadlock or transient resource failure. Retrying may succeed, or exhaust the retry budget and fail the step / trigger another recovery policy.

**Fail fast** means stopping as soon as an unacceptable error is detected or continuing would be unsafe. In practice, "fail fast" can mean configuring neither skip nor retry for that error type; the framework handles rollback and transitions the step to `FAILED` on an unrecovered exception.

### 2.2. Input Feed Examples

| Input | Scenario | Candidate Policy | Explanation |
| --- | --- | --- | --- |
| `CANCELLED` order | Valid data, outside import scope | **Filter** | Not a data quality error |
| Date `2026-99-99` | Single-row formatting error | **Skip + quarantine**, if allowed | Row can be isolated |
| Amount equals 0 | Item-level business rule violation | Skip or fail fast, per contract | Depends on severity |
| Entire input file missing | No data to complete the job | **Fail fast** | Not a single-row error |
| Cannot connect to database | Broad infrastructure failure | **Bounded retry, then fail** | Skipping could drop the whole feed |
| Invalid destination account in payout instruction | Critical business violation | **Fail fast / manual review** | Cannot silently drop a financial transfer |
| Order belongs to wrong tenant | Scope mismatch or data leak | Usually **fail fast and investigate** | Potential security boundary breach |
| Few products missing optional description | Fails display enrichment | Filter/skip or assign default per policy | Must decide whether products may be published |
| PostgreSQL deadlock | Transient transaction conflict | **Retry transaction** | Not a permanent data defect |
| Wrong SQL column name after deploy | Code/schema bug | **Fail fast** | Retry/skip cannot fix it |

This table is directional and does not replace business policy. The same `amount=0` might be a data error for an invoice yet valid for a voucher or free event.

### 2.3. The Most Important Question

**If this record is dropped and the job still reports `COMPLETED`, will output consumers accept its absence?**

If the answer is "no," default to **fail fast** or **hold data in staging/quarantine and block publishing**. Enabling skip merely because Spring Batch supports it creates pipelines that appear successful while silently shedding data.

---

## 3. Choosing Skip vs. Fail Fast with a Decision Framework

### 3.1. Five Criteria to Evaluate

1. **Error scope:** a single isolated item, an entire file, a partition, or the whole system?
2. **Independence:** can other items be processed without depending on the failing item?
3. **Business impact:** does dropping an item break balances, totals, settlement results, sequences, or inter-record relationships?
4. **Recoverability:** does the error resolve on retry, require data remediation, or is it unrecoverable?
5. **Auditability:** must you persist the failing record, rule code, source, and remediation status?

If an error cannot be isolated, skipping is usually inappropriate.

### 3.2. Decision Table by Error Category

| Error Category | Characteristics | Preferred Approach |
| --- | --- | --- |
| Permanent, isolated record defect allowed by contract | Single malformed row; other rows unaffected | Bounded skip + persist reject |
| Valid record outside scope | Status outside reporting period | Intentional filter |
| Transient resource unavailability | DB timeout, HTTP 503, deadlock | Retry with backoff; on exhaustion, fail/recover |
| Misconfiguration / system bug | Missing schema, bad credentials, whole-file mapping bug | Fail fast; fix and restart |
| Mandatory business invariant | Totals mismatch, missing critical transaction | Fail fast or quality gate blocking publish |
| Security / tenant boundary error | Wrong data ownership, cross-tenant leak | Fail fast and investigate |
| Isolated errors so numerous output is meaningless | 30% of feed is invalid | Block via skip threshold / quality gate |
| Uncertain side-effect commit | Timeout near commit, unknown external API outcome | Reconcile before replay; never blind-skip |
| Full input audit required | Must account for every record as accepted/rejected/review | Decision routing + quarantine; not skip alone |

### 3.3. Decision Flow

```text
Error occurred?
     |
     v
Is the item out of scope per policy?
     | yes
     +----> FILTER, record appropriate metric
     |
     v
Is it recoverable via safe retry?
     | yes
     +----> Bounded RETRY + backoff
     |          |
     |          +-- success -> continue
     |          +-- exhausted -> evaluate severity / fail
     |
     v
Can exactly one item be isolated?
     | no
     +----> FAIL FAST or pause/recover infrastructure
     |
     v
Does dropping the item break a business invariant?
     | yes
     +----> FAIL FAST / QUARANTINE + BLOCK PUBLISH
     |
     v
Are auditing and an approved error budget in place?
     | no
     +----> FAIL FAST
     |
     v
SKIP + persist reject + quality gate
     |
     +-- exceeds threshold --> FAIL or BLOCK PUBLISH
```

This is a tool to align policy, not Spring Batch's built-in internal execution flow.

---

## 4. Skip States and Counters in Spring Batch

### 4.1. `StepExecution` Counter Definitions

Spring Batch tracks each skip type separately:

- `getReadSkipCount()`: items not fully read due to a skipped error in the reader.
- `getProcessSkipCount()`: items that errored in the processor and were skipped.
- `getWriteSkipCount()`: items that errored in the writer and were skipped.
- `getSkipCount()`: total skips per step semantics.
- `getFilterCount()`: items where the processor returned `null` (distinct from skips).
- `getReadCount()` and `getWriteCount()`: read/written item counts per Spring Batch counters.
- `getRollbackCount()` / `getCommitCount()`: rollback and commit counts; useful for assessing error impact.

Example:

```java
StepExecution step = ...;

long readSkips = step.getReadSkipCount();
long processSkips = step.getProcessSkipCount();
long writeSkips = step.getWriteSkipCount();
long totalSkips = step.getSkipCount();
long filtered = step.getFilterCount();
long commits = step.getCommitCount();
long rollbacks = step.getRollbackCount();
```

Keep in mind: `readCount` does not necessarily equal the total number of Java `read()` calls when the reader encounters EOF, retries, or rollbacks. Nor does `writeCount` replace authoritative target counts if the writer updates multiple tables or external systems.

### 4.2. `skipLimit` Is a Combined Budget

Example:

```java
.faultTolerant()
.skip(InvalidOrderException.class)
.skipLimit(10)
```

Within a single step execution, at most **10 skips** are tolerated under the policy. Upon the **11th** eligible skip, the step exceeds the limit and fails. This cap applies across all framework-tracked skip types combined; it is not "10 read errors + 10 process errors + 10 write errors."

With `skipLimit(0)`, zero items may be skipped for skippable exceptions. In many cases, a clearer expression is simply not configuring skip for errors that must fail fast.

### 4.3. A `COMPLETED` Job Can Still Have Skips

```text
JobExecution status: COMPLETED
StepExecution:
  readCount:        10,000
  filterCount:         100
  readSkipCount:         3
  processSkipCount:     10
  writeSkipCount:        2
  writeCount:        9,885
  skipCount:            15
```

These numbers illustrate a scenario with no special additional semantics. **`COMPLETED` only indicates that the step finished under the current error policy and flow**, not that output contains 100% of raw input. Dashboards should therefore display **completed with skips/rejects** distinctly from completed with zero data-quality issues.

### 4.4. `BatchStatus` and `ExitStatus`

`BatchStatus` reflects lifecycle state (`COMPLETED`, `FAILED`, `STOPPED`, ...), whereas `ExitStatus` can carry custom business or flow meaning, such as `"COMPLETED_WITH_SKIPS"`.

If you want to flag results with warnings, you can set a custom `ExitStatus` from a `StepExecutionListener` and define explicit transitions in the job flow. However, **do not equate a custom `ExitStatus` with changing `BatchStatus`**: a job can have `BatchStatus.COMPLETED` alongside a custom exit code. Downstream consumers must understand both.

---

## 5. Configuring a Fault-Tolerant Step with a Skip Limit

### 5.1. Data Model

Suppose a job reads CSV orders, filters out `CANCELLED` rows, rejects invalid amounts, and writes accepted orders.

```java
import java.math.BigDecimal;

public record RawOrder(
    String externalId,
    BigDecimal amount,
    String status
) {}

public record AcceptedOrder(
    String externalId,
    BigDecimal amount
) {}
```

Exception for per-item data errors:

```java
public class InvalidOrderException extends RuntimeException {

    private final String ruleCode;
    private final String externalId;

    public InvalidOrderException(
            String ruleCode,
            String externalId,
            String message) {

        super(message);
        this.ruleCode = ruleCode;
        this.externalId = externalId;
    }

    public String ruleCode() {
        return ruleCode;
    }

    public String externalId() {
        return externalId;
    }
}
```

Exception for critical non-skippable errors:

```java
public class CriticalOrderException extends RuntimeException {

    public CriticalOrderException(String message) {
        super(message);
    }
}
```

### 5.2. Processor Distinguishing Filter, Invalid, and Critical

```java
import org.springframework.batch.item.ItemProcessor;

public class OrderValidationProcessor
        implements ItemProcessor<RawOrder, AcceptedOrder> {

    @Override
    public AcceptedOrder process(RawOrder item) {
        if (item == null) {
            throw new CriticalOrderException(
                "Reader returned an unexpected null item");
        }

        if ("CANCELLED".equals(item.status())) {
            // Valid, but outside the target dataset to write.
            return null;
        }

        if (item.externalId() == null ||
            item.externalId().isBlank()) {

            throw new InvalidOrderException(
                "ORDER_ID_REQUIRED",
                item.externalId(),
                "Order ID is missing");
        }

        if (item.amount() == null ||
            item.amount().signum() <= 0) {

            throw new InvalidOrderException(
                "AMOUNT_MUST_BE_POSITIVE",
                item.externalId(),
                "Amount must be positive");
        }

        if ("CROSS_TENANT".equals(item.status())) {
            // Potential access-control boundary violation.
            throw new CriticalOrderException(
                "Cross-tenant data detected");
        }

        if (!"READY".equals(item.status())) {
            throw new InvalidOrderException(
                "STATUS_UNSUPPORTED",
                item.externalId(),
                "Unsupported order status");
        }

        return new AcceptedOrder(
            item.externalId().trim(),
            item.amount());
    }
}
```

In this example, `CANCELLED` is filtered before validating `amount`. That is a business choice: canceled orders do not enter the dataset whose amounts this job validates. If requirements call for quality statistics across **the entire raw source**, validate before filtering or use a separate evaluation stream.

To keep retries and restarts safe, the processor should be a pure function: given the same input and rule snapshot, it yields the same result without sending emails or writing outside-transaction DB flags just to mark "processed."

### 5.3. Configuring `StepBuilder`

Assuming reader, processor, writer, and transaction manager beans already exist:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.SkipListener;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.file.FlatFileParseException;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.transaction.PlatformTransactionManager;

public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<RawOrder> reader,
        ItemProcessor<RawOrder, AcceptedOrder> processor,
        ItemWriter<AcceptedOrder> writer,
        SkipListener<RawOrder, AcceptedOrder> skipListener) {

    ExponentialBackOffPolicy backoff =
        new ExponentialBackOffPolicy();
    backoff.setInitialInterval(250L);
    backoff.setMultiplier(2.0);
    backoff.setMaxInterval(2_000L);

    return new StepBuilder("importOrdersStep", jobRepository)
        .<RawOrder, AcceptedOrder>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        // Only isolated record errors are treated as skippable.
        .skip(FlatFileParseException.class)
        .skip(InvalidOrderException.class)
        .skipLimit(10)
        // CriticalOrderException MUST NOT be skipped.
        .noSkip(CriticalOrderException.class)
        // Retry transient resource errors; never skip DB outages.
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .backOffPolicy(backoff)
        .listener(skipListener)
        .build();
}
```

**Meaning:**

- `.faultTolerant()` switches to the builder supporting skip/retry.
- `.skip(FlatFileParseException.class)` can fit when parse errors are known to be **single-line** errors; it does not mean every file read error is skippable.
- `.skip(InvalidOrderException.class)` permits skipping items with business-approved violations.
- `.skipLimit(10)` is the total skip cap across the step execution, not a per-exception limit.
- `.noSkip(CriticalOrderException.class)` explicitly enforces stopping on critical errors, especially useful when a superclass skip policy is configured elsewhere.
- `.retry(TransientDataAccessException.class)` retries classified transient errors. Actual DB connection drops may wrap into exceptions outside this hierarchy; inspect your exception translator and driver before choosing classifiers.
- `.retryLimit(3)` limits attempts per Spring Batch retry semantics.
- `.listener(skipListener)` observes skipped records; audit persistence still requires transactional/idempotent design.

Never configure `skip(Exception.class)` just to let a job "finish the file," as it can mask logic bugs, connection drops, misconfigurations, or critical data errors.

### 5.4. `noSkip` Does Not Replace Impact Analysis

A system might declare additional exclusions:

```java
.noSkip(CriticalOrderException.class)
.noSkip(SecurityException.class)
```

However, infrastructure errors like `DataAccessException` can surface across layers and be wrapped differently. Never rely purely on a class list while ignoring root causes; test real failures in the reader, processor, writer, and commit phases.

---

## 6. Skip Rules Differ Across Reader, Processor, and Writer

### 6.1. Skip in the Reader

With `FlatFileItemReader`, a malformed line can throw `FlatFileParseException`, carrying details about the offending line. If the reader advances past that line per its contract and skipping it does not affect other lines, skipping can be reasonable.

Example:

```text
file.csv
1: ORDER-1,100,READY
2: ORDER-2,abc,READY     <- failed to parse amount
3: ORDER-3,200,READY

Policy:
  line 2 -> read skip, write reject
  line 1 + line 3 -> continue processing
```

Do not skip every exception in the reader. Missing files, wrong schema headers, broken database cursors, or I/O errors affect the entire stream. If a reader fails to advance past an error, blind retry/skip risks infinite loops or data loss.

**Technical note:** on a read skip, the listener receives the exception and line details from `FlatFileParseException`, but **not necessarily a complete `RawOrder` object** because parsing failed.

### 6.2. Skip in the Processor

The processor has already received an item, but business rules reject it. A dedicated exception works well:

```java
if (item.amount().signum() <= 0) {
    throw new InvalidOrderException(
        "AMOUNT_MUST_BE_POSITIVE",
        item.externalId(),
        "Invalid amount");
}
```

If policy allows skipping, the item does not go to the writer and `processSkipCount` increments per the framework. If the contract requires saving rejected records, use a listener or a decision-routing writer with controlled persistence.

The processor is the right place to classify **per-item** data defects; rules spanning totals, record counts, cross-partition duplicate keys, or batch-wide integrity typically require staging, DB constraints, or a separate quality gate.

### 6.3. Skip in the Writer Is Riskier

A writer in a chunk-oriented step receives **an entire chunk**:

```java
void write(Chunk<? extends AcceptedOrder> items)
    throws Exception;
```

An error in `write(chunk)` can involve:

- A single item violating target constraints.
- Batch-wide or multi-item constraint conflicts.
- Connection loss, timeout, or lock contention.
- Ambiguous transaction commit outcomes.
- External APIs not participating in the transaction.
- A bug in a serializer or SQL writer.

Spring Batch fault-tolerant processing can roll back, retry, and attempt to isolate the failing item during write-skip handling. **Do not assume every writer supports safely isolating a single item.** If the writer produced out-of-transaction side effects before throwing, re-invoking it can duplicate operations.

Example:

```text
Chunk: [A, B, C, D]
Writer:
  insert A -> succeeds
  insert B -> succeeds
  insert C -> DuplicateKeyException
  throw
```

If A and B auto-committed or were sent over an external API, write retries may re-issue them. If a JDBC writer participates in the **chunk transaction** and the entire transaction rolls back cleanly, item isolation rests on a much safer foundation.

### 6.4. Why You Should Not Skip Every `DuplicateKeyException`

A duplicate key can represent:

- An item already imported in a previous run when writer idempotency wasn't handled.
- An isolated source data defect allowed into rejects.
- A violation of an important business invariant.
- A sign that the job was launched twice concurrently.
- An ambiguous outcome after a commit timeout.
- A flawed unique constraint design.

Skipping all duplicate keys lets the job "complete" while hiding data anomalies and breaking reconciliation. Handle duplicates based on **business keys** and explicit update/ignore/reject/fail policies; for idempotency, consider `UPSERT` or proper unique-key handling rather than treating database constraints as routine skippable errors.

---

## 7. Which Exceptions Should Be Skipped and Which Should Not?

### 7.1. Organizing an Exception Hierarchy by Business Semantics

Instead of throwing generic `RuntimeException` everywhere, build specific exceptions:

```java
public abstract class ImportException extends RuntimeException {
    protected ImportException(String message) {
        super(message);
    }
}

public final class SkippableRecordException
        extends ImportException {

    private final String ruleCode;
    private final String recordId;

    public SkippableRecordException(
            String ruleCode,
            String recordId,
            String message) {
        super(message);
        this.ruleCode = ruleCode;
        this.recordId = recordId;
    }

    public String getRuleCode() {
        return ruleCode;
    }

    public String getRecordId() {
        return recordId;
    }
}

public final class FatalBatchException
        extends ImportException {

    public FatalBatchException(String message) {
        super(message);
    }
}
```

The step can configure:

```java
.skip(SkippableRecordException.class)
.noSkip(FatalBatchException.class)
.skipLimit(10)
```

Benefits of dedicated classes: clear skip policy, easy rule-code tagging in tests and logs, and lower risk of accidentally catching technical errors.

### 7.2. Avoid One Exception Being Both Skippable and Fatal

If a processor throws `BusinessRuleViolationException` for both "missing description" and "invalid payment amount," configuring `skip(BusinessRuleViolationException.class)` accidentally skips critical errors too.

Two common solutions:

1. Create clear subclasses: `SkippableRecordException` and `CriticalBusinessViolationException`.
2. Use a custom `SkipPolicy` inspecting rule code, severity tier, and skip count.

Use option 2 only when classification depends on multiple attributes; dedicated classes are generally easier to read and test.

### 7.3. Errors by Processing Stage

| Stage | Potentially Skippable | Usually Fail Fast / Recover |
| --- | --- | --- |
| Read file | Single malformed CSV line can be isolated and reader advances | Missing file, file-wide encoding error, invalid header/schema |
| Read JDBC | Single row explicitly identifiable as malformed with safe reader advancement | Dropped connection/cursor, invalid SQL, unavailable transaction |
| Process | Independent rule violation acceptable to omit from output | Tenant boundary breach, critical totals mismatch, bugs, missing reference data |
| Write JDBC | Rejectable individual item when transaction isolates cleanly | DB outage, ambiguous commit, global constraint, SQL syntax error |
| Write API | Only when API/writer supports item isolation and explicit idempotency | Payments, non-idempotent emails, network timeouts with unknown outcome |
| Metadata | Never treat `JobRepository` errors as skippable items | Failure to persist checkpoints or execution status |

**Decision order:** analyze isolation feasibility and business impact first, then choose exception classes in `StepBuilder`. Never work backward from the builder.

---

## 8. When Do You Need a Custom `SkipPolicy`?

`.skip(MyException.class).skipLimit(n)` suffices for simple rules. When you must classify by rule code, error category, and multiple thresholds, you can define a `SkipPolicy`.

### 8.1. Example Evaluating Exception Type and Total Skips

```java
import org.springframework.batch.core.step.skip.SkipPolicy;

public final class BusinessRecordSkipPolicy
        implements SkipPolicy {

    private final long maxSkippedRecords;

    public BusinessRecordSkipPolicy(long maxSkippedRecords) {
        this.maxSkippedRecords = maxSkippedRecords;
    }

    @Override
    public boolean shouldSkip(
            Throwable throwable,
            long skipCount) {

        // Spring Batch may invoke the policy with special values
        // to probe skippability; avoid relying on a positive
        // skipCount in probe scenarios.
        if (!(throwable instanceof SkippableRecordException)) {
            return false;
        }

        return skipCount >= 0
            ? skipCount < maxSkippedRecords
            : true;
    }
}
```

In Spring Batch 5.x, `SkipPolicy.shouldSkip(Throwable, long)` receives the current skip count; the framework may pass a negative value (for instance, to probe capability) depending on context. Custom policies must evaluate exception type independently of probe state.

Configuration:

```java
.faultTolerant()
.skipPolicy(new BusinessRecordSkipPolicy(10))
```

With this policy, the 11th skippable error is rejected. In a real project, test read/process/write paths as well as probe invocations.

**Never use a singleton `SkipPolicy` holding mutable counters to enforce skip limits.** When multiple executions run concurrently, state gets mixed up. The framework-supplied `skipCount` parameter fits basic limits. If you need separate quotas per tenant/file/rule, store them in execution context or durable data stores.

### 8.2. Per-Rule-Code Limits

Requirement: allow up to 10 optional-description errors, but **never skip any `PAYMENT_ACCOUNT_MISMATCH` error**.

A policy can check:

```java
if (throwable instanceof SkippableRecordException ex) {
    if ("PAYMENT_ACCOUNT_MISMATCH".equals(ex.getRuleCode())) {
        return false;
    }
    return skipCount < 10;
}
return false;
```

If you need **separate quotas per rule**, a single aggregate `skipCount` cannot track per-code counts. In that case, maintain a decision/quarantine ledger or a pre-validation step computing quality metrics, and enforce an explicit quality gate instead of keeping multiple mutable counters in the processor.

### 8.3. A Skip Policy Does Not Replace Full Business Error Handling

Some datasets require retaining rejected records for operations to fix later. Simply returning `true` from `SkipPolicy` excludes the item from output; the policy does not automatically persist the reject payload or open a remediation ticket. Persistence and auditing must be designed separately.

---

## 9. When Is Fail Fast the Better Choice?

### 9.1. Errors Breaking Batch-Wide Invariants

For example, a financial posting job must enforce:

\[
\sum \mathrm{debit} = \sum \mathrm{credit}
\]

If one debit transaction is skipped while its offsetting credit is still written, the ledger goes out of balance. An individual defective record whose **impact cascades to other items** is unfit for simple skipping.

Similarly:

- Data requiring an unbroken sequence.
- A snapshot whose record count must match a manifest.
- A reference table that must load completely before processors run.
- Invoices and line items requiring atomic publication scope.
- Partner exports governed by an "all records or none" contract.

In these cases, fail fast or staging + gate prevents publishing corrupt results.

### 9.2. Configuration or Code Bugs

If every row throws `NullPointerException` due to a bug or `BadSqlGrammarException` due to an unapplied schema migration, continuing to skip just burns time and loses data. Fail fast forces immediate root-cause resolution.

Never configure:

```java
.skip(Exception.class)
.skipLimit(Integer.MAX_VALUE)
```

This hides code and infrastructure errors and produces a `COMPLETED` execution with nearly empty output.

### 9.3. Security Violations

A record belonging to another tenant appearing in the active feed can signal broken access boundaries or upstream misrouting. Depending on your system, this is a security incident requiring immediate job termination and investigation—not "skip one record and carry on."

### 9.4. Unreliable Infrastructure Resources

If the DB loses connections in the writer, skipping chunks/items just to keep going is dangerous: the outage can corrupt output, leave commits ambiguous, or prevent `JobRepository` from saving checkpoints. The sound approach is bounded retries followed by job failure, restarting only after infrastructure recovers and reconciliation is done.

### 9.5. Fail Fast Does Not Automatically Roll Back the Entire Job

A common misconception:

```text
Chunk size = 100

Chunk 1: COMMIT
Chunk 2: COMMIT
Chunk 3: COMMIT
Chunk 4: critical error detected -> ROLLBACK / FAILED
```

A `FAILED` job **does not roll back the three already-committed chunks**. Fail fast stops further processing, yet previously written output still needs management. If business rules require publishing all or nothing, design **staging → quality gate → publish** or appropriate transaction/versioning—do not expect a single job-wide transaction.

---

## 10. The Middle Ground: Quarantine and Quality Gate

Many systems should not choose between "silently drop records" and "halt everything." A third option is **processing valid items while preserving invalid traces, publishing only when quality thresholds pass**.

### 10.1. Pipeline Model

```text
Raw input
    |
    v
Parse + normalize
    |
    v
Validate / business rules
    |
    +----------------+------------------+
    |                |                  |
    v                v                  v
 ACCEPTED         REJECTED         NEEDS_REVIEW
    |                |                  |
    v                v                  v
 staging_ok      staging_reject     review_queue
    |                |                  |
    +----------------+------------------+
                     |
                     v
              Data Quality Gate
                  |
              +---+----+
              |        |
            PASS      FAIL
              |        |
              v        v
         Publish     Hold output,
         accepted    remediate input
```

Here, a rejected record does not vanish; it retains its rule code, source identity, rule version, and downstream remediation status.

### 10.2. Decision Objects Instead of Exceptions

Java 17 can model decisions cleanly with sealed types:

```java
public sealed interface OrderDecision
        permits AcceptedDecision, RejectedDecision { }

public record AcceptedDecision(AcceptedOrder order)
        implements OrderDecision { }

public record RejectedDecision(
        String externalId,
        String ruleCode,
        String ruleVersion)
        implements OrderDecision { }
```

Processor:

```java
import org.springframework.batch.item.ItemProcessor;

public final class OrderDecisionProcessor
        implements ItemProcessor<RawOrder, OrderDecision> {

    @Override
    public OrderDecision process(RawOrder row) {
        if (row.amount() == null ||
            row.amount().signum() <= 0) {
            return new RejectedDecision(
                row.externalId(),
                "AMOUNT_MUST_BE_POSITIVE",
                "rules-2026-11");
        }

        return new AcceptedDecision(new AcceptedOrder(
            row.externalId(), row.amount()));
    }
}
```

The writer can split the chunk by decision and write accepted/rejected rows to staging tables. When sharing **the same datasource and transaction manager**, both writes can join the same chunk transaction. If writing to separate systems, implement idempotency and reconciliation rather than assuming atomicity.

With this approach, rejected items **do not consume `skipLimit`** because the processor returns an object. Consequently, the quality gate must compute reject counts and rates explicitly per contract.

### 10.3. Percentage-Based Data Quality Gates

Suppose a day has 20,000 eligible records, of which 130 are rejected. Policy caps the reject rate at **0.5%**:

\[
\text{rejectRate} = \frac{130}{20\,000} \times 100\% = 0.65\%
\]

The rate exceeds the threshold, so the gate must fail or hold in `HOLD_FOR_REVIEW`, blocking publication into downstream serving tables.

If raw input has 22,000 records where 2,000 valid records are out of scope, the denominator **eligible=20,000** differs from total raw input. Contracts must specify the denominator explicitly so KPIs are never misinterpreted.

### 10.4. Absolute Limits vs. Percentage Limits

| Policy | Example | Pros | Cons |
| --- | --- | --- | --- |
| `skipLimit(20)` | Max 20 failing records | Easy to configure, fails fast | Inconsistent between 100-row and 1M-row files |
| Reject rate ≤ 0.5% | Max 0.5% of eligible | Scales with varying volume | Must count unique records and define denominator |
| Critical rules = 0 | Zero critical violations allowed | Protects invariants | One defect can fail the whole feed |
| Combined thresholds | ≤20 errors, ≤0.5%, critical=0 | Flexible | Needs gate/ledger and thorough tests |
| Manual approval | Sensitive periods | Strong governance | Operational overhead |

The framework's `skipLimit` only provides an **aggregate skip budget**, not per-rule or per-tenant error rates. When requirements exceed that, build an explicit quality gate.

---

## 11. Auditing Skipped Records: `SkipListener` and Its Limits

### 11.1. Callbacks

Spring Batch defines `SkipListener<I,O>` with three event hooks:

```java
import org.springframework.batch.core.SkipListener;

public final class ImportSkipListener
        implements SkipListener<RawOrder, AcceptedOrder> {

    @Override
    public void onSkipInRead(Throwable throwable) {
        // Reader parse failure; RawOrder may not have been constructed.
    }

    @Override
    public void onSkipInProcess(
            RawOrder item,
            Throwable throwable) {
        // Item was read; processor produced no output.
    }

    @Override
    public void onSkipInWrite(
            AcceptedOrder item,
            Throwable throwable) {
        // Writer excluded an item under fault-tolerance policy.
    }
}
```

For read errors, raw line info may reside in `FlatFileParseException`. For process errors, you receive the input item; for write errors, you receive the output item the writer attempted to write.

### 11.2. Pattern for Capturing Rule Codes

```java
@Override
public void onSkipInProcess(
        RawOrder item, Throwable throwable) {

    if (throwable instanceof InvalidOrderException invalid) {
        // Write structured log or route record into
        // a transaction-appropriate reject/audit mechanism.
        String code = invalid.ruleCode();
        String key = invalid.externalId();
    }
}
```

Never dump raw customer data, tokens, or payment details into logs. Protect rule codes and source record identifiers according to data-handling policies.

### 11.3. Does a Listener Guarantee Exactly-Once?

Spring Batch invokes skip callbacks to avoid duplicate calls in normal flows and aligns them around commit points. However, **never infer** that an HTTP request, email, or message sent inside a listener becomes atomic/exactly-once with the JDBC chunk transaction.

Example:

```text
onSkipInProcess(item A):
  send HTTP "reject A" -> succeeds

Chunk transaction later rolls back:
  database has not committed accepted records

Retry/restart:
  may need to reprocess A
```

An already-sent HTTP call does not automatically roll back. For durable, deduplicated auditing, use:

- A reject table with a unique key on `sourceRecordId + ruleCode + businessPeriod`.
- Writing to the same datasource inside the chunk transaction when feasible.
- Transactional outbox if events must be published after commit.
- Reconciliation when metadata and business data use separate datasources.

A listener that simply increments an in-memory counter may also count *retry attempts* rather than unique rejected records.

---

## 12. Combining Retry and Skip: Establishing Precedence via Policy

### 12.1. Some Errors Should Retry Before Failing

For example, a database deadlock can be transient. The goal is retrying the transaction, not dropping an order:

```java
.faultTolerant()
.retry(TransientDataAccessException.class)
.retryLimit(3)
.skip(InvalidOrderException.class)
.skipLimit(10)
```

Keep exception classes tight. Certain connection drops do not map to `TransientDataAccessException` under real wrappers; verify driver exceptions across read, write, and commit contexts.

### 12.2. Do Not Retry Deterministic Business Rule Failures

An order with a negative amount will not become valid on an immediate retry with the same input and rule snapshot. Adding `retry(InvalidOrderException.class)` wastes cycles re-evaluating the same failure before eventually skipping or failing anyway.

If business reference data can change dynamically, base retry decisions on **the nature of the reference lookup failure** (service unavailable) rather than retrying deterministic validation errors.

### 12.3. Errors Belonging to Both Retry and Skip

Avoid configuring overly broad overlapping exception hierarchies for both retry and skip without clear post-exhaustion rules. Exact semantics depend on retry/skip policies and read/process/write phases; test concrete scenarios, especially writer rollbacks and nested exception classifiers.

If the requirement is "retry 3 times, and if it still fails, stop the whole job," **do not configure skip for that exception**. If the requirement is "retry up to 3 times, then quarantine the individual item," prove that the item can be isolated and recorded as rejected safely.

### 12.4. Backoff Prevents Retry Storms

If 20 batch jobs hit an outage simultaneously, immediate retries can unleash thousands of connection attempts. Use exponential backoff, jitter where needed, capped attempts, and transition to `FAILED` once budget expires; let the orchestrator restart only after infrastructure recovers.

A job that failed due to a database outage must be handled via recovery/restart, not by adding `.skip(DataAccessException.class)` to keep running without writing data.

---

## 13. Transaction Boundaries Determine the Value of Fail Fast

### 13.1. Chunk-Oriented Processing Commits Incrementally

```text
Chunk size = 100

Chunk #1: items 1..100   -> COMMIT
Chunk #2: items 101..200 -> COMMIT
Chunk #3: items 201..300 -> critical violation
                             |
                             v
                          ROLLBACK
                          Step FAILED
```

Prior chunks may already be committed. On restart, the reader uses saved checkpoints to resume from the uncommitted portion, provided `ItemStream` and the metadata repository are properly configured.

### 13.2. Skipping Can Trigger Rollbacks

When an error occurs in the processor or writer, a fault-tolerant step may roll back a chunk and reprocess it to isolate which item can be skipped. Consequently:

- `process()` or `write()` may be invoked more times than the final written item count.
- Out-of-transaction side effects may execute multiple times.
- A counter inside a processor may increment repeatedly for the same item.
- `StepExecution.getRollbackCount()` can rise even if the job ends `COMPLETED`.
- "Skipping 1 item" does not necessarily mean only one Java invocation threw.

Design deterministic processors and idempotent writers, especially across networks or multiple databases.

### 13.3. Ambiguous Commit Outcomes

A database connection can drop while the client awaits the `COMMIT` acknowledgment:

```text
Writer sent SQL
    |
    v
Database may have committed
    |
    X  response lost
    |
Client sees timeout
```

You cannot assume the entire chunk rolled back. If the writer is invoked again after skip, retry, or restart, output can duplicate. For high-correctness workloads, use unique business keys, idempotency, reconciliation, and fail fast on ambiguous transaction outcomes.

### 13.4. Separate Metadata DB and Business DB

If `JobRepository` resides in DB A while the writer writes to DB B, two local transaction managers do not form a distributed transaction:

```text
DB B: business rows COMMITTED
DB A: checkpoint update FAILED
```

Upon restart, the reader may reprocess records already written to DB B. Skip cannot fix this; you need idempotent writers and reconciliation. Likewise, a fail-fast step will not automatically delete business rows already committed.

---

## 14. Restartability and Skipped Data

### 14.1. Restart After Failure Is Not a Fresh Run

```text
JobInstance #501:
  JobExecution #900 FAILED
      importStep checkpoint persisted

  JobExecution #901 COMPLETED (restart)
      resumes from checkpoint
```

In Spring Batch 5.x, when configured, an operator can call:

```java
Long newId = jobOperator.restart(900L);
```

The operator creates a new `JobExecution` for **the same `JobInstance`**. Preconditions: metadata is intact, the job is restartable, status is valid, and no other execution is running nor has the instance already completed.

### 14.2. Do Previously Skipped Items Automatically Re-Appear on Restart?

Do not assume an item skipped in a prior execution will automatically flow to the writer on restart. Behavior depends on checkpoint state, transactions, failure location, and reader design. If a chunk committed and a record was skipped, the reader's checkpoint typically advanced past it; editing the source afterward does not force a restart to re-read already-skipped records.

If business rules require reprocessing rejects, build a **remediation/reprocess workflow** reading from the quarantine table or corrected source. Never abuse restarts as an uncontracted way to "rescan every dropped item."

### 14.3. Do Not Mint New `JobInstance`s with Timestamps to Bypass Skip Limits

If a step fails for exceeding `skipLimit(10)`, adding an identifying `runAt=now` parameter to launch a new instance will:

- Start from a fresh checkpoint or the beginning depending on the data source.
- Potentially duplicate side effects.
- Mask the signal that data quality breached thresholds.
- Obscure the lineage of the prior failed instance.

The proper procedure is halting publication, remediating source/policy per approval, evaluating checkpoint compatibility, and executing an explicit restart or reprocess.

### 14.4. Recovery When Stale Metadata Shows `STARTED`

If a process crashes before writing a terminal status, the repository may still show `STARTED`. Never blindly edit `BATCH_JOB_EXECUTION` with ad-hoc SQL just to force a restart. Verify the worker is dead, inspect committed outputs and checkpoints, and follow recovery procedures suited to your Spring Batch version.

---

## 15. Do Not Turn Error Budgets into Untraceable Missing Data

### 15.1. Data Quality Metrics Set

A job with 10,000 records:

```text
raw rows:            10,000
read skips:               4
successfully read:     9,996
filtered (out of scope): 196
process skips:            8
write skips:              2
accepted written:     9,790  (example)
```

Illustrative counters must be verified against actual flow behavior: filtering, retries, rollbacks, and writer logic can shift counts. Operational reports should explicitly state **item unit**, **denominator**, and **acceptance criteria**.

### 15.2. Tracking Both Absolute Counts and Rates

Example:

\[
\text{invalidRate}
=
\frac{\text{unique rejected records}}
{\text{eligible source records}}
\times 100\%
\]

If a small 5,000-row file has 10 errors (0.2%) while a 1M-row file has 10 errors (0.001%), the same `skipLimit(10)` does not represent the same quality level.

A policy might require all of the following simultaneously:

- Zero critical errors.
- At most 100 unique rejected records.
- Reject rate not exceeding 0.25%.
- Every rejected record has a quarantine audit entry.
- Accepted total amount reconciles with the source within tolerance.

If any condition fails, do not publish even if the import step technically completed.

### 15.3. `skipCount` Is Not Automatically Job-Wide Unique Rejected Count

An item may be processed multiple times across restarts or retries; a source file may be re-imported by revision; multiple `StepExecution`s may exist. If final reporting needs **unique source records rejected in a business period**, query a quarantine table keyed by unique business keys instead of mechanically summing skip counts across all executions.

### 15.4. Post-Ingestion Quality Gate

A common flow:

```text
importToStagingStep
       |
       v
aggregateDataQualityStep
       |
       +-- PASS -> publishStep
       |
       +-- FAIL -> stop/fail job, hold staging
```

Note: `importToStagingStep` may be `COMPLETED` while publishing is blocked by the gate, leaving committed staging data behind. That is **intentional** for investigation and reprocessing, not a job-wide transaction rollback.

---

## 16. Unit Testing Decisions and Processors

### 16.1. No Spring Context Needed for Pure Rule Tests

```java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class OrderValidationProcessorTest {

    private final OrderValidationProcessor processor =
        new OrderValidationProcessor();

    @Test
    void filtersCancelledOrder() throws Exception {
        RawOrder input = new RawOrder(
            "ORDER-C", new BigDecimal("100.00"), "CANCELLED");

        assertNull(processor.process(input));
    }

    @Test
    void acceptsValidOrder() throws Exception {
        RawOrder input = new RawOrder(
            "ORDER-A", new BigDecimal("125.00"), "READY");

        AcceptedOrder output = processor.process(input);

        assertNotNull(output);
        assertEquals("ORDER-A", output.externalId());
        assertEquals(new BigDecimal("125.00"), output.amount());
    }

    @Test
    void classifiesAmountViolation() {
        RawOrder input = new RawOrder(
            "ORDER-X", BigDecimal.ZERO, "READY");

        InvalidOrderException ex = assertThrows(
            InvalidOrderException.class,
            () -> processor.process(input));

        assertEquals(
            "AMOUNT_MUST_BE_POSITIVE",
            ex.ruleCode());
    }

    @Test
    void criticalCrossTenantViolationCannotBeTreatedAsDataSkip() {
        RawOrder input = new RawOrder(
            "ORDER-S", new BigDecimal("90.00"),
            "CROSS_TENANT");

        assertThrows(
            CriticalOrderException.class,
            () -> processor.process(input));
    }
}
```

Unit tests verify that the processor classifies inputs correctly, but **do not prove Spring Batch actually skips or fails per policy**. You need integration tests combining `JobRepository`, `StepBuilder`, readers, and writers or test fixtures.

---

## 17. Integration Test: Filter One Item, Skip Two Items, Write Three Items

### 17.1. Fixture

Input has six records:

| ID | Amount | Status | Outcome |
| --- | ---: | --- | --- |
| A | 10 | READY | Written |
| B | 5 | CANCELLED | Filtered |
| C | 0 | READY | Process skip |
| D | 30 | READY | Written |
| E | -1 | READY | Process skip |
| F | 50 | READY | Written |

Policy `skipLimit(2)`. Expected outcome:

```text
JobExecution:     COMPLETED
readCount:        6
filterCount:      1
processSkipCount: 2
writeCount:       3
skipCount:        2
```

### 17.2. H2 Test Configuration

Gradle Groovy DSL in a Spring Boot 3.x project:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

Example `src/test/resources/application-skip-test.yml`:

```yaml
spring:
  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: always

  datasource:
    generate-unique-name: true
```

Uses an in-JVM metadata repository for testing. To test restarts after process or container crashes, use a persistent metadata database.

### 17.3. Full-Context Integration Test

```java
import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.support.ListItemReader;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.PlatformTransactionManager;

import static org.junit.jupiter.api.Assertions.*;

@SpringBatchTest
@SpringBootTest(classes = SkipOrFailFastIT.TestApp.class)
@ActiveProfiles("skip-test")
class SkipOrFailFastIT {

    @Autowired
    JobLauncherTestUtils launcher;

    @Autowired
    AtomicInteger acceptedWrites;

    @Test
    void completesWhenExactlyTwoRecordsCanBeSkipped()
            throws Exception {

        JobParameters parameters = new JobParametersBuilder()
            .addString("testCaseId",
                UUID.randomUUID().toString(), true)
            .toJobParameters();

        JobExecution execution = launcher.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());

        StepExecution step = execution.getStepExecutions().stream()
            .filter(s -> "importOrdersStep".equals(s.getStepName()))
            .findFirst()
            .orElseThrow();

        assertEquals(6L, step.getReadCount());
        assertEquals(1L, step.getFilterCount());
        assertEquals(2L, step.getProcessSkipCount());
        assertEquals(0L, step.getReadSkipCount());
        assertEquals(0L, step.getWriteSkipCount());
        assertEquals(2L, step.getSkipCount());
        assertEquals(3L, step.getWriteCount());

        // In-memory sink used for this test,
        // not a production transactional writer.
        assertEquals(3, acceptedWrites.get());
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import(SkipTestJobs.class)
    static class TestApp {
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class SkipTestJobs {

        @Bean
        AtomicInteger acceptedWrites() {
            return new AtomicInteger();
        }

        @Bean
        ItemReader<RawOrder> testReader() {
            return new ListItemReader<>(List.of(
                new RawOrder("A", new BigDecimal("10"), "READY"),
                new RawOrder("B", new BigDecimal("5"), "CANCELLED"),
                new RawOrder("C", BigDecimal.ZERO, "READY"),
                new RawOrder("D", new BigDecimal("30"), "READY"),
                new RawOrder("E", new BigDecimal("-1"), "READY"),
                new RawOrder("F", new BigDecimal("50"), "READY")
            ));
        }

        @Bean
        OrderValidationProcessor testProcessor() {
            return new OrderValidationProcessor();
        }

        @Bean
        ItemWriter<AcceptedOrder> testWriter(
                AtomicInteger acceptedWrites) {

            return chunk ->
                acceptedWrites.addAndGet(chunk.size());
        }

        @Bean
        Step importOrdersStep(
                JobRepository repository,
                PlatformTransactionManager transactionManager,
                ItemReader<RawOrder> testReader,
                OrderValidationProcessor testProcessor,
                ItemWriter<AcceptedOrder> testWriter) {

            return new StepBuilder("importOrdersStep", repository)
                .<RawOrder, AcceptedOrder>chunk(
                    3, transactionManager)
                .reader(testReader)
                .processor(testProcessor)
                .writer(testWriter)
                .faultTolerant()
                .skip(InvalidOrderException.class)
                .skipLimit(2)
                .build();
        }

        @Bean
        Job importOrdersJob(
                JobRepository repository,
                Step importOrdersStep) {

            return new JobBuilder("importOrdersJob", repository)
                .start(importOrdersStep)
                .build();
        }
    }
}
```

In this test example, `ListItemReader` and `AtomicInteger` only serve **a single synchronous scenario**. They do not prove checkpointing across process restarts or transaction rollback of an external writer. When expanding to multiple test methods, reset fixtures/context or supply fresh reader state so tests do not interfere with each other.

### 17.4. Testing Limit Breach

Add an input `G` with `amount = 0` while keeping `skipLimit(2)`. Create an independent fixture and assert:

- `JobExecution` finishes `FAILED` when the third skippable violation occurs.
- `processSkipCount`/exception reflects the exceeded limit per the framework.
- Chunks committed prior to the failure may still have output persisted.
- Incomplete output is not published if the contract demands completeness.
- After fixing the source, decide restart/reprocess based on metadata and output state.

### 17.5. Testing Fail Fast Even With Remaining Skip Budget

Add a `CROSS_TENANT` record to the input while configuring skip only for `InvalidOrderException`. Assert the step enters `FAILED` upon hitting `CriticalOrderException`, even when only 0 or 1 record has been skipped.

Tests should also verify error codes and origin so the system never surfaces an opaque generic failure.

### 17.6. Testing Read and Write Skips Independently

- **Read skip:** use `FlatFileItemReader` with a malformed line and assert `readSkipCount`. Verify raw line/source position is audited as required.
- **Write skip:** use a transactional writer that isolates one invalid item and rolls back safely; assert `writeSkipCount`. Also verify no duplicate writes occur for sibling items in the chunk after retry.
- **Infrastructure failure:** make the writer throw a transient DB error and assert it is not skipped by `skip(InvalidOrderException.class)`. Retries may occur per config; once budget is exhausted, the step fails.

---

## 18. Data- and SLA-Driven Decision Process

### 18.1. Defining an Error Budget from Business Requirements

Before enabling `skipLimit`, fill out a policy table:

| Attribute | Question |
| --- | --- |
| Dataset | Which feed, tenant, and business period? |
| Required completeness | Are 100% of records mandatory? |
| Allowed reject types | Which rule codes may be skipped? |
| Critical violations | Which rules must halt execution immediately? |
| Max rejects | What are the absolute and/or percentage limits? |
| Audit evidence | Where are failing records persisted? |
| Remediation | Who fixes them and when are they reprocessed? |
| Publication | Can output publish immediately after `COMPLETED`? |
| Side effects | Is the writer idempotent? |
| Restart | If failure happens at chunk N, how are committed chunks handled? |

Example policy for catalog import:

```text
dataset: product_catalog
critical errors: schema invalid, cross-tenant, DB unavailable
skippable errors: malformed optional attribute, invalid image URL
absolute reject limit: 100 records
reject-rate limit: 0.5% eligible records
audit: quarantine table
publish condition: import completed AND quality gate passed
```

Store the policy version alongside `JobInstance`/request metadata if rules can change across deployments.

### 18.2. Designing Error Budgets by Tier

You can define:

- `CRITICAL`: never skip, never publish.
- `RECOVERABLE_TECHNICAL`: bounded retry; fail when budget exhausted.
- `REJECTABLE_DATA`: skip/quarantine within thresholds.
- `OUT_OF_SCOPE`: filter, do not count as invalid.
- `MANUAL_REVIEW`: route to an approval queue; may block partial publication.
- `WARNING`: accept while recording a warning if policy allows.

If a single exception class carries all these meanings, configuring skip accurately becomes hard. Separating exception types or rule decisions keeps the policy readable and testable.

### 18.3. Measure Total Impact, Not Just Record Percentages

A feed losing 0.1% of records can still breach SLAs if the lost record is a high-value payment instruction. Thresholds should combine **counts**, **risk weights**, **rule severity**, and **aggregate invariants**. Never decide solely on percentage of failing rows.

---

## 19. Monitoring and Runbooks When Skips Occur

### 19.1. Metrics to Track

| Signal | Meaning | Note |
| --- | --- | --- |
| `readSkipCount` | Errors during reading | Parsed input item may not exist |
| `processSkipCount` | Skipped processor errors | Should cross-reference rule codes |
| `writeSkipCount` | Skipped writer errors | Monitor rollbacks and side effects |
| `filterCount` | Validly filtered items | Do not lump into reject rate |
| `rollbackCount` | Transaction rollbacks occurred | Can rise due to skips/retries |
| `JobExecution.BatchStatus` | Job completed/failed/stopped | `COMPLETED` can still have skips |
| `dataquality.reject_rate` | Rejected ratio over defined denominator | Not a default built-in metric |
| `quarantine.backlog` | Unresolved rejected records | May need its own remediation SLA |

Custom metrics are suggestions; choose bounded-cardinality labels such as `job.name`, `step.name`, `rule.code`, and `rule.version`. Never use raw customer IDs, `externalOrderId`, or `jobExecutionId` as per-item metric tags.

### 19.2. Structured Log for a Rejection

```text
event=batch_record_rejected
jobName=importOrdersJob
stepName=importOrdersStep
ruleCode=AMOUNT_MUST_BE_POSITIVE
ruleVersion=rules-2026-11
sourceFileId=file-418
sourceRecordId=ORDER-8821
decision=REJECTED
```

Log only necessary fields; never put secrets, PII, or unclassified payloads in logs. Maintain a durable audit store if downstream teams must remediate records rather than just reading logs.

### 19.3. Runbook When Skip Counts Spike

1. Identify the exact job, business period, tenant, source, and rule version.
2. Compare read/process/write skips, filters, retries, and rollback counts.
3. Check distributions by rule code, source, and onset timestamp.
4. Distinguish localized data defects from widespread infrastructure failures.
5. Verify quarantine captured all records with unique keys.
6. If approaching `skipLimit`, evaluate halting the batch and investigating before losing too much output.
7. If the job is `COMPLETED` with rejects, determine gate/publish status independently.
8. Remediate data/policy with approval, execute controlled reprocessing, and reconcile output.

Never bump `skipLimit` repeatedly just to make dashboards green. Doing so silently alters the data quality contract without approval.

---

## 20. Common Mistakes When Choosing Skip or Fail Fast

| Mistake | Risk | Remediation |
| --- | --- | --- |
| `skip(Exception.class)` | Hides bugs and DB disconnects | Only skip explicitly classified exceptions |
| Using `return null` for every violation | Loses audit trail; confuses filter with reject | Use decision/reject or exception + skip listener |
| Raising `skipLimit` after every failure | Uncontrolled output quality degradation | Define business-approved error budgets |
| Skipping DB connection errors | Missing output due to unavailable resource | Bounded retry, then fail/restart |
| Skipping cross-record errors | Breaks aggregate invariants | Fail fast or staging/quality gate |
| Skipping in a non-transactional writer | Partial side effects may repeat | Transactions, idempotency, reconciliation |
| Sending HTTP audit in `SkipListener` | Does not roll back with chunk | Outbox or reject table with unique key |
| Checking only `BatchStatus.COMPLETED` | Overlooks dropped invalid data | Check counters and business outputs |
| Summing skip counts across restarts as unique rejects | Double-counting | Ledger deduplicated by source record |
| Quarantine without source identity | Cannot tell which record to fix | Store key, rule code, and rule version |
| Assuming fail fast rolls back all output | Earlier chunks already committed | Staging + publish gate |
| Retrying deterministic validation errors | Wastes resources, risks loops | Skip/fail per policy; do not retry |
| Skipping parser errors when parser doesn't advance | Infinite loop or lost position | Verify reader contract |
| Using a new timestamp to bypass skip limit | Masks failure, duplicates writes, loses checkpoint | Approved restart/reprocess |
| Testing only happy path | Misses the (N+1)th error | Test exact limit, over limit, and critical errors |
| Changing rule config mid-restart | Same record gets different decisions | Freeze rule version/snapshot or migrate |

---

## 21. Practice Exercises

### Exercise 1 — Build a Decision Matrix

Classify each error as FILTER, SKIP, RETRY, FAIL FAST, or QUARANTINE + GATE:

1. A CSV row has an unparseable amount.
2. A `CANCELLED` order in a job importing only `READY` orders.
3. A payment transaction has a mismatched destination account.
4. Database loses connection for 30 seconds.
5. JDBC deadlock in the writer.
6. Tens of thousands of records share the same external order ID.
7. An optional product image URL is invalid.
8. Debit and credit totals do not balance.

For each choice, note what condition would make you pick differently and the remediation action.

### Exercise 2 — Exact Skip Limit

Create a step with `skipLimit(2)` and a processor throwing `InvalidOrderException` for items with `amount <= 0`. Test:

- Zero errors: `COMPLETED`.
- Exactly two errors: `COMPLETED` with `processSkipCount=2`.
- Three errors: `FAILED`.
- One critical error: `FAILED` immediately, even with remaining skip budget.

### Exercise 3 — Filter vs. Skip

Create a 10-item source containing 2 `CANCELLED` and 2 invalid items. The processor filters canceled items and throws an exception on invalid ones.

Verify `filterCount=2`, `processSkipCount=2`, that the writer receives only accepted items, and that canceled items do not consume skip budget.

### Exercise 4 — Reader Parse Failure

Use `FlatFileItemReader` to read a CSV with a row containing text instead of a numeric amount. Configure skipping `FlatFileParseException` and a listener to log the source line.

Test that the job continues past the bad row; inspect the listener, `readSkipCount`, and verify the output file omits the bad row.

### Exercise 5 — Writer Skip and Rollback

Use a `JdbcBatchItemWriter` writing to a constrained table and craft one isolatable violating item. Configure a fault-tolerant step and verify transaction rollback and data isolation.

Add a simulated out-of-transaction side-effect writer to observe why retry/write-skip can repeat operations without an idempotency key.

### Exercise 6 — Quality Gate After Staging

Given a feed of 50,000 eligible records, 160 rejected, and a maximum 0.25% reject rate policy, compute the rate and design a gate deciding whether to publish.

Ensure an import step finishing `COMPLETED` does not automatically publish when the threshold is breached.

### Exercise 7 — Restart After Skips

Create a chunk job with valid and invalid items. Force the writer to fail after some chunks commit; restart the exact `JobInstance`.

Check checkpoints, unique accepted output, reject ledger, and explain why summing counts across two `StepExecution`s may not equal unique rejects.

### Exercise 8 — Operational Runbook

Write a runbook for a product import job encountering 2% malformed rows when policy allows only 0.5%. Detail how to halt publication, investigate the source, fix data, and rerun without minting a new `JobInstance` via an identifying timestamp.

---

## 22. Production Skip Readiness Checklist

- [ ] Skippable errors affect only isolated records without breaking batch-wide invariants.
- [ ] Business-approved table of rule codes and severities exists.
- [ ] Clear skip limit exists, paired with percentage/quality gates if volume varies widely.
- [ ] Database connection, metadata repository, or widespread infra failures are never skipped.
- [ ] Valid out-of-scope items use filter without becoming silent rejects.
- [ ] `SkipListener`/quarantine captures source audits and prevents duplicates.
- [ ] Reader handles skips safely and advances past failing items.
- [ ] Writer has proper transaction/idempotency guarantees across retries and rollbacks.
- [ ] Fail fast has a strategy for handling already-committed chunks.
- [ ] Staging/publish gate is used if batch-wide all-or-nothing output is required.
- [ ] Unit and integration tests cover exact limit, over limit, and critical errors.
- [ ] Restart, checkpoints, rule version pinning, and output reconciliation are tested.
- [ ] Dashboards distinguish `COMPLETED` with skips, `FAILED`, and `HOLD_FOR_REVIEW`.
- [ ] Remediation owner, SLA, and reject reprocessing flow are defined.

## 23. Conclusion

**Skip** is a strong tool when an error can be isolated to a single item, business rules allow omitting it within bounds, and rejected records are tracked and managed. **Fail fast** fits system errors, critical violations, security risks, or cases where dropping a record corrupts the entire result. **Retry** targets recoverable glitches, **filter** handles valid out-of-scope items, and **quarantine + quality gate** is the choice to consider when you want to process good data while guaranteeing published output meets quality standards.

Do not decide merely because an exception can be passed to `.skip(...)`. Decide based on **data correctness, auditability, and restart consequences**, then use Spring Batch to enforce that policy consistently.

## 24. References

- [Spring Batch Reference — Configuring Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html): `skip`, `skipLimit`, `noSkip`.
- [Spring Batch Reference — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): chunk and transaction boundaries.
- [Spring Batch Reference — Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html): fault-tolerant retry.
- [Spring Batch Reference — Intercepting Step Execution](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/intercepting-execution.html): listeners and skip callbacks.
- [Spring Batch Reference — Item Processing](https://docs.spring.io/spring-batch/reference/processor.html): filtering and transformation.
- [Spring Batch Reference — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): checkpointing and restart.
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html): `@SpringBatchTest` and integration testing.
- [Spring Batch 5.2 API — SkipPolicy](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/step/skip/SkipPolicy.html): `shouldSkip` interface.
- [Spring Batch 5.2 API — SkipListener](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/SkipListener.html): read/process/write skip notifications.
