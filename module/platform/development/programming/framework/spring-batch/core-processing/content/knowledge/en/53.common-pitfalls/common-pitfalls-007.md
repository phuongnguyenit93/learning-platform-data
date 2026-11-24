# Retrying Permanent Errors in Spring Batch: Identifying and Handling Them Properly

In a batch job, retry is a helpful tool when an error **has a realistic chance of clearing on its own**: a transient network blip, a partner service temporarily returning an overload error, or a database transaction deadlock. Yet when data is invalid, a required field is missing, an identifier is wrong, or authentication is misconfigured, re-running the exact same operation with the exact same input usually just produces **the exact same error**. This is a very common pitfall in Spring Batch: **retrying permanent errors**.

The consequence is not just wasting a few attempts. When hundreds of thousands of items share the same error, retrying the wrong category slows the job down severalfold, adds load to databases and APIs, misses SLAs, floods logs, and can cause duplicate side effects if the operation is not idempotent.

This lesson belongs to **Spring Batch Core Processing → Common Pitfalls**, explaining how to distinguish permanent from transient errors; how to configure retry/skip/fail in a chunk step; how to avoid multi-layer retry amplification; how to control backoff, budgets, and timeouts; how to guard side effects; and how to observe errors and test so invalid data **is never retried pointlessly**. Examples use **Java 17, Spring Boot 3.x, Spring Batch 5.x, and JUnit 5**.

## 1. What Does Retrying a Permanent Error Mean?

**Retry** means re-executing an operation after it fails, expecting the failing condition to change. An error is **permanent for the current processing run** if retrying the exact same data and environment without changing anything cannot succeed.

Example of an order import batch:

```text
Item A: amount = "120.00"    -> valid
Item B: amount = "abc"       -> unparseable amount
Item C: amount = "-10.00"    -> amount violates business rule
Item D: Partner API timeout  -> potentially recoverable
Item E: DB deadlock          -> potentially recoverable
```

If every exception is configured to retry three times:

```text
Item B: parse("abc") -> FAIL
        parse("abc") -> FAIL
        parse("abc") -> FAIL

Item C: validate(-10) -> FAIL
        validate(-10) -> FAIL
        validate(-10) -> FAIL
```

Nothing about the data or conditions changes between attempts, so those two items **never become valid**. They must be classified as data errors, then **controlled-skipped/quarantined** or cause the job to become **FAILED** depending on business rules.

Conversely:

```text
Item D: POST partner request -> HTTP 503
        wait 500 ms
        POST partner request -> success
```

Here, retry can help. However, even for transient errors, retry is safe only when the action is repeatable, bounded, and does not emit duplicate side effects.

## 2. Three Error Categories and Handling Decisions

| Category | Signal | Examples | Preferred action |
| --- | --- | --- | --- |
| **Permanent item error** | Item data violates contract and will not self-heal | Bad date, negative amount, missing ID, unsupported enum value | Skip/quarantine if allowed; otherwise fail |
| **Transient operational error** | Infrastructure conditions may change after a short delay | Timeouts, bounded 503s, deadlocks, brief connection blips | Bounded retry with backoff; fail or follow policy when exhausted |
| **Permanent system/config error** | Entire job cannot succeed without intervention | Wrong credentials, incompatible DB schema, missing table, broken API contract | Fail fast and alert; do not skip every item |

A common trap is thinking **permanent always means skip**. A bad data item might be routed to a reject store; an authentication configuration error is a **system-wide problem** that must stop the job—never turn it into thousands of skipped items.

### 2.1. Do Not Classify Solely by Generic Exception Class Names

| Situation | How it should usually be interpreted | Note |
| --- | --- | --- |
| `NumberFormatException` from input field `"abc"` | Invalid data | Translate into a deterministic business exception |
| `IllegalArgumentException` | Insufficient context | Could be bad input or a bug; never skip this entire class |
| HTTP `400 Bad Request` | Usually invalid request | If payload is valid but API changed contract, fail the system |
| HTTP `401`/`403` | Usually permissions/configuration | Fail fast and fix auth; never mass-retry items |
| HTTP `404` | Contract-dependent | Could be missing item or routing incident |
| HTTP `409` | Domain-dependent | Could be idempotent duplicate or genuine conflict |
| HTTP `429` | Temporary rate limit | Retry per `Retry-After`/backoff and shared budget |
| HTTP `503` | Service temporarily unavailable | Bounded retry; fail/circuit-break on prolonged outage |
| SQL duplicate key | Usually data or idempotency error | Do not retry blindly; determine prior write vs. conflict |
| SQL deadlock/serialization failure | Potentially transient | Retry transaction appropriately if operation is safe |
| Connection timeout | Potentially transient | Never retry infinitely when pool/DB is already overloaded |
| Unexpected `NullPointerException` | Likely a bug | Fail and investigate; never auto-skip all NPEs |

A specific exception can also be **wrapped** in `RuntimeException`, `CompletionException`, or an HTTP client exception class. Therefore, error translation at integration boundaries must classify accurately and preserve retryable/non-retryable semantics instead of catching every `Exception` and throwing a generic `TemporaryException` or `RuntimeException`.

### 2.2. "Permanent" Can Depend on Timing

An order referencing a not-yet-synced customer may be invalid **in the current snapshot**, while upstream data may update an hour later. Retrying after a few milliseconds inside the same chunk will not resolve it; it may be a **deferred record** that needs to wait for reference data and replay later.

Thus separate:

- Retry **within the execution** for short-lived blips.
- **Scheduled defer/replay** for dependent data that may arrive later.
- **Quarantine for data correction** for rule validation errors.
- **Fail the job** for broken system configuration or contracts.

## 3. Why Is Overly Broad Retry Configuration Dangerous?

Example configuration that should not be applied indiscriminately:

```java
.faultTolerant()
.retry(Exception.class)
.retryLimit(10)
```

If a file has 50,000 malformed items, ten attempts per item can generate **hundreds of thousands of error-handling passes**, before even counting rollbacks and framework re-invocations depending on transactions. The outcome still ends in failure or skip, yet resources and time were burned.

Even worse:

```java
.retry(RuntimeException.class)
.skip(Exception.class)
.skipLimit(1_000_000)
```

With this overly broad policy, programming bugs, JDBC errors, auth errors, and invalid items risk being masked or handled with the wrong semantics. A massive `skipLimit` makes it easy for the job to finish `COMPLETED` even though nearly all input was lost. A batch **completing technically** does not mean output data is complete and right.

### 3.1. Impact on Throughput and Deadlines

Suppose each attempt of an item takes 80 ms, with 20,000 permanently failing items:

| Configuration | Theoretical attempts | Attempt processing time |
| --- | ---: | ---: |
| No retry on permanent errors | 20,000 | 1,600 seconds |
| `retryLimit(3)` on permanent errors | 60,000 | 4,800 seconds |
| `retryLimit(5)` on permanent errors | 100,000 | 8,000 seconds |

This is an **illustrative calculation assuming every attempt takes exactly 80 ms, runs sequentially, and ignores overhead**; Spring Batch may perform extra work due to rollbacks and fault-tolerance rules. Still, the trend is clear: retrying the wrong category raises latency, dependency load, and deadline-miss risk without increasing valid item throughput.

## 4. Designing Exceptions Around Business Semantics

A maintainable design classifies errors at processor/gateway boundaries and **retries only exceptions explicitly marked as transient**.

Example models:

```java
package com.example.batch;

import java.math.BigDecimal;

public record IncomingOrder(
        String orderId,
        String amountText) {}

public record AcceptedOrder(
        String orderId,
        BigDecimal amount,
        String partnerReference) {}
```

In a Java project, each `public record` belongs in its own file of the same name. The classes below should likewise live in separate files.

### 4.1. Permanent Data Error Exception

```java
package com.example.batch;

public class InvalidOrderException extends RuntimeException {

    private final String reasonCode;

    public InvalidOrderException(String reasonCode) {
        super(reasonCode);
        this.reasonCode = reasonCode;
    }

    public String reasonCode() {
        return reasonCode;
    }
}
```

`reasonCode` should be a fixed code from an allowed set, such as `MISSING_ORDER_ID`, `INVALID_AMOUNT`, or `NON_POSITIVE_AMOUNT`. Do not embed raw payloads, emails, or account numbers in exception messages because they may be written to error logs/metadata.

### 4.2. Transient and Configuration Exceptions

```java
package com.example.batch;

public class TransientPartnerException extends RuntimeException {

    public TransientPartnerException(String safeCode) {
        super(safeCode);
    }
}
```

```java
package com.example.batch;

public class PartnerConfigurationException
        extends RuntimeException {

    public PartnerConfigurationException(String safeCode) {
        super(safeCode);
    }
}
```

`TransientPartnerException` is used for retryable errors like `PARTNER_TIMEOUT` or `PARTNER_UNAVAILABLE`. `PartnerConfigurationException` represents errors requiring configuration fixes like `INVALID_CREDENTIALS`; this category must fail fast. Never treat an arbitrary HTTP error message as transient merely because it came over the network.

### 4.3. Translating Errors at the Partner Boundary

Suppose the application defines an interface:

```java
package com.example.batch;

public interface PartnerGateway {
    String registerOrder(String orderId);
}
```

The concrete implementation translates HTTP/DB exceptions into classified exceptions, for example:

```text
Recoverable HTTP timeout / 503 / 429
    -> TransientPartnerException

HTTP 401 / 403 due to invalid credentials
    -> PartnerConfigurationException

HTTP 400 confirmed due to invalid item input
    -> InvalidOrderException

HTTP 409 handled per idempotency contract
    -> success or clearly classified conflict error
```

Some statuses must follow the **API's specific contract**. For HTTP 429, respect `Retry-After` and rate limits; for 409, verify whether the same idempotency key represents an already completed successful outcome. Never infer that from status code alone.

If gateway code currently uses `catch (Exception ex) { throw new TransientPartnerException(...); }`, every validation error, bug, and configuration failure gets converted into a retryable error. That is an anti-pattern to eliminate. Catch **specific client exceptions** in an adapter layer and let unknown/unexpected exceptions fail the job for investigation.

## 5. Validate Before Invoking Operations with Side Effects

Placing validation early avoids calling an API or writing to a DB only to discover the record was unmistakably invalid.

```java
package com.example.batch;

import java.math.BigDecimal;
import org.springframework.batch.item.ItemProcessor;

public class OrderProcessor
        implements ItemProcessor<IncomingOrder, AcceptedOrder> {

    private final PartnerGateway partnerGateway;

    public OrderProcessor(PartnerGateway partnerGateway) {
        this.partnerGateway = partnerGateway;
    }

    @Override
    public AcceptedOrder process(IncomingOrder order) {
        if (order.orderId() == null || order.orderId().isBlank()) {
            throw new InvalidOrderException("MISSING_ORDER_ID");
        }

        BigDecimal amount;
        try {
            amount = new BigDecimal(order.amountText());
        } catch (NumberFormatException | NullPointerException ex) {
            throw new InvalidOrderException("INVALID_AMOUNT");
        }

        if (amount.signum() <= 0) {
            throw new InvalidOrderException("NON_POSITIVE_AMOUNT");
        }

        // Call partner only after local validation succeeds.
        String partnerReference =
                partnerGateway.registerOrder(order.orderId());

        return new AcceptedOrder(
                order.orderId(), amount, partnerReference);
    }
}
```

The code separates two paths:

```text
amount="invalid"
    |
    v
InvalidOrderException
    |
    +--> skip/quarantine if policy permits
    +--> PartnerGateway is not called

amount="120.00"
    |
    v
PartnerGateway
    |
    +--> TransientPartnerException -> eligible for retry
    +--> PartnerConfigurationException -> fail immediately
    +--> success -> AcceptedOrder
```

**Limitation to remember:** a processor in a chunk-oriented step may be re-invoked upon retry or rollback. If `registerOrder(...)` creates an external transaction without an idempotency key, retrying a network error can create **duplicate partner orders** even though Spring Batch writes only one output. Section 8 explains how to guard against this.

## 6. Configuring `retry`, `noRetry`, and `skip` in Spring Batch 5

For a fault-tolerant chunk step, a clear policy looks like:

- `InvalidOrderException`: **no retry**, skip only when permitted and reject budget remains.
- `TransientPartnerException`: bounded retry with backoff.
- `PartnerConfigurationException`: no retry, no skip; fail the step/job.
- Other unclassified errors: fail so bugs or unhandled system failures surface.

Configuration example:

```java
package com.example.batch;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.backoff.FixedBackOffPolicy;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class ImportOrdersBatchConfig {

    @Bean
    FixedBackOffPolicy partnerBackOffPolicy() {
        FixedBackOffPolicy policy = new FixedBackOffPolicy();
        policy.setBackOffPeriod(500L);
        return policy;
    }

    @Bean
    OrderProcessor orderProcessor(PartnerGateway gateway) {
        return new OrderProcessor(gateway);
    }

    @Bean
    Step importOrdersStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            ItemReader<IncomingOrder> reader,
            OrderProcessor processor,
            ItemWriter<AcceptedOrder> writer,
            FixedBackOffPolicy partnerBackOffPolicy) {

        return new StepBuilder("importOrdersStep", repository)
                .<IncomingOrder, AcceptedOrder>chunk(
                        100, transactionManager)
                .reader(reader)
                .processor(processor)
                .writer(writer)
                .faultTolerant()
                .retry(TransientPartnerException.class)
                .retryLimit(3)
                .noRetry(InvalidOrderException.class)
                .noRetry(PartnerConfigurationException.class)
                .backOffPolicy(partnerBackOffPolicy)
                .skip(InvalidOrderException.class)
                .skipLimit(20)
                .build();
    }

    @Bean
    Job importOrdersJob(
            JobRepository repository, Step importOrdersStep) {
        return new JobBuilder("importOrdersJob", repository)
                .start(importOrdersStep)
                .build();
    }
}
```

The reader and writer in this example are application-supplied beans; configure JDBC/file readers, writers, schemas, and transactions per your project. `org.springframework.retry.backoff.FixedBackOffPolicy` belongs to the Spring Retry library used by Spring Batch for retry policies.

### 6.1. Reading the Configuration Accurately

| Line | Effect |
| --- | --- |
| `.retry(TransientPartnerException.class)` | Specifies the retryable exception |
| `.retryLimit(3)` | Allows at most **three total attempts**, including the initial attempt, under the retry policy |
| `.noRetry(InvalidOrderException.class)` | Ensures data errors are marked non-retryable |
| `.noRetry(PartnerConfigurationException.class)` | Prevents repeated retries on configuration errors |
| `.backOffPolicy(...)` | Inserts a wait period between retries per policy |
| `.skip(InvalidOrderException.class)` | Allows skipping this data error type |
| `.skipLimit(20)` | Caps skipped items within one `StepExecution` |

For an `InvalidOrderException` in the processor, no retry occurs under the retry policy; the framework then handles it under the skip policy. If total skips exceed 20, the step fails on the next item needing a skip. **Skip and retry are two distinct policies**; adding `.skip(...)` does not make a permanent error retryable.

For `TransientPartnerException`, Spring Batch retries up to three attempts per policy. If it still fails and no matching skip policy applies, the step becomes `FAILED`. That is normally the right outcome for an external outage: never silently discard every order just because a partner is down.

### 6.2. Why Configure Both a Retry Allowlist and `noRetry`?

If you only configure `.retry(TransientPartnerException.class)`, other exceptions are already outside the retry allowlist. `noRetry(...)` **makes intent explicit** and is especially helpful when shared configuration elsewhere adds a retryable superclass. Even so, with custom policies, check classification order and precedence against your specific API/version.

Do not simultaneously configure an overly broad retry superclass like `.retry(RuntimeException.class)` and rely on a few `.noRetry(...)` calls to protect everything else. When new exceptions are added, they easily become unintentionally retryable. A **narrow allowlist** is safer to operate.

### 6.3. Backoff Does Not Turn a Permanent Error into a Transient One

`FixedBackOffPolicy` in the example waits 500 ms between retries; for transient errors against large services, bounded exponential backoff with jitter can be used. Yet for `INVALID_AMOUNT`, waiting 500 ms or 50 seconds still will not fix the input.

Backoff must align with:

- HTTP/JDBC timeouts so individual attempts do not hang indefinitely.
- The batch run window and finish deadline.
- Partner rate limits or `Retry-After`.
- Total retry budget when many items fail together.
- Retry policies of the API client, message broker, and orchestrator.

## 7. Permanent Errors in Reader, Processor, and Writer

### 7.1. Errors in the Reader

For instance, a malformed CSV line makes `FlatFileItemReader` throw `FlatFileParseException`. If the reader **can move past a broken line** and the business allows dropping some records, you can add the parse exception to the skip allowlist with an explicit limit:

```java
.skip(org.springframework.batch.item.file.FlatFileParseException.class)
.skipLimit(20)
```

However, if the header changed, the file has the wrong schema, or the checksum mismatches, skipping line-by-line can cause mass data loss. **File-wide errors** should be caught in a `validateSourceStep` and fail before importing.

Retrying a CSV line with the wrong column count without fixing the file **helps nothing**. Moreover, `SkipListener.onSkipInRead(Throwable)` receives no successfully parsed item, so record a verified source location instead of printing the raw line that may hold sensitive data.

### 7.2. Errors in the Processor

This is the most common case: validation spots invalid data. If the error is `InvalidOrderException`, it can be skipped and routed to quarantine. If the input lacks a critical identifier or violates a severe business rule, policy may force **failing the job**, even if that error appears only once.

If processor code does `catch (Exception e) { return null; }`, the framework treats it as a **filtered item**, not a skipped item. Then `filterCount` rises while `skipCount` stays zero, erasing error visibility. Thus `return null` belongs strictly to **intentional filtering**, not general exception handling.

### 7.3. Errors in the Writer

Writers typically process a `Chunk` containing multiple items. `DuplicateKeyException` must be evaluated against the contract:

- If the record was already written earlier with the same business/idempotency key, you may need to **recognize the existing outcome** rather than treating it as an error.
- If the data conflicts with a different record, reject/fail per policy and route the conflict to a resolution workflow.
- If the writer throws an infrastructure error, do not automatically label items as invalid. A chunk-wide failure does not immediately pinpoint a single offending item.

A fault-tolerant Spring Batch step can retry/roll back and in some cases isolate items to locate write-failing items when skip is configured. Therefore, design writers with proper transactions and idempotency; never infer a specific row in the chunk as the culprit solely from a single writer error callback.

Do not apply `.skip(DataAccessException.class)` or `.retry(DataAccessException.class)` across all JDBC errors without classifying, since that parent type covers transient errors, duplicate keys, and unrecoverable structural failures alike.

## 8. Retry Is Safe Only When the Operation Is Repeatable

Suppose `registerOrder(orderId)` sends a create-order request to a partner. The server succeeds, but the response times out:

```text
Batch Processor       Partner API
      | POST order-1       |
      |------------------->|
      |                    | CREATE SUCCESS
      |<-- response lost --X
      |
      | retry POST order-1 |
      |------------------->|
      |                    | CREATE AGAIN?
```

If the API lacks idempotency, a retry that is right on **error type** can still create duplicates. Determine:

1. Can `orderId` or another key serve as a **stable idempotency key**?
2. Does the API guarantee that the same key returns the same outcome?
3. On timeout, is there a way to query transaction status before resending?
4. Can external calls sit in a separate step after staging/outbox so they do not hold database locks during network waits?
5. If connectivity drops after sending a request, actual state is **unknown**, not necessarily `FAILED`.

Example expanded gateway contract:

```java
package com.example.batch;

public interface PartnerGateway {
    String registerOrder(
            String orderId,
            String idempotencyKey);
}
```

The processor can derive an idempotency key from an **immutable business identity**, such as `"import-order:" + orderId`, provided the partner agrees on key format, uniqueness scope, and retention. **Never use a random timestamp or retry attempt number as the idempotency key**, because they give each retry a different identifier.

In Spring Batch, a chunk's internal transaction **cannot automatically roll back side effects in external systems**. A more reliable design in many systems is:

```text
Chunk transaction:
    validate item
    write staging + outbox event
    COMMIT

Outbox worker:
    send partner request with stable idempotency key
    record confirmed result
    retry transient errors with bounded budget
```

An outbox still needs duplicate handling and uncertain-outcome tracking, yet it prevents chunk retries from accidentally firing external side effects repeatedly before commit.

## 9. Multi-Layer Retry Amplification Produces Unexpectedly High Attempt Counts

A common misconfiguration is the HTTP client retrying three times, Spring Batch retrying three times, and the orchestrator restarting the job three times:

```text
HTTP client attempts: 3
Spring Batch attempts: 3
Orchestrator executions: 3

Worst-case nominal attempts: 3 x 3 x 3 = 27
```

The figure 27 is **illustrative when every layer uses its maximum attempts**, before even counting rollbacks, writer isolation splits, or other systems. If the item has a permanent error, all 27 attempts still fail. With 10,000 items sharing that error, load can surge dramatically.

Decide **which layer owns retries** for each error category:

| Layer | Suggested role | What to avoid |
| --- | --- | --- |
| HTTP/database client | Very short retries for pre-send connection errors or appropriate transients | Retrying every HTTP status |
| Spring Batch fault-tolerant step | Item/transaction retries with clear policy and batch metadata | Retrying validation/configuration errors |
| Scheduler/orchestrator | Restart execution after dependency recovers | Creating new instances endlessly, retrying without backoff |
| Manual replay/backfill | Reprocess fixed sources or quarantined items | Mixing replay with checkpointed restarts |

Beyond attempt counts, bound **total retry duration** against business deadlines. If the batch must finish before 04:00, do not let each item hold 30 seconds × 3 attempts when tens of thousands of items hit a systemic failure.

## 10. Deciding Skip, Quarantine, or Fail on Permanent Errors

Not retrying is the **first step**, not the whole recovery strategy. A permanently failing item still needs an explicit outcome:

```text
Permanent failure
      |
      v
Error classifier
      |
      +-- minor item error, permitted to exclude?
      |        |
      |        +--> YES: SkipListener -> Quarantine -> Reconciliation
      |
      +-- critical item / source-wide error?
      |        |
      |        +--> YES: Step FAILED / no publish
      |
      +-- permanent configuration/system error?
               |
               +--> YES: Fail fast + alert / fix config
```

### 10.1. Skip Must Have a Budget

Example:

```text
Expected source rows: 20,000
Maximum invalid items: 25
Maximum invalid ratio: 0.1%
Critical error: MISSING_ORDER_ID
```

With 20,000 records, 0.1% corresponds to **20** items. With 21 invalid items, the quality gate must reject publishing even though `skipLimit(25)` was not breached. With a single critical `MISSING_ORDER_ID`, the batch can still fail even when total rejects equal 1.

**Spring Batch's `skipLimit` does not replace a quality gate** enforcing error rates, manifest checks, critical rules, and output reconciliation.

### 10.2. Quarantine Instead of Losing Track of Records

A reject record can store:

| Field | Meaning |
| --- | --- |
| `source_batch_id` | Identifies the source version |
| `record_locator` | Stable source ID/offset to locate the record again |
| `stage` | READ / PROCESS / WRITE |
| `reason_code` | Safe error code such as `INVALID_AMOUNT` |
| `job_execution_id` | Run that detected the error |
| `payload_pointer` | Path to original data with access control |
| `review_status` | NEW / CORRECTED / REPLAYED / DISMISSED |

Do not print raw payloads or full exception messages in general logs. Some parse exceptions include the entire CSV line; use a protected source/quarantine store for investigation.

Persisting quarantine must also be reliable: if the reject store fails, the job must not silently report that output passed quality checks. Use transactions/outbox, unique keys on source/version/record, and reconciliation to control duplicate writes on restart.

### 10.3. Never Silently Publish Incomplete Output

Pipeline design:

```text
validateSourceStep
        |
        v
importToStagingStep
      /   \
     /     \--> skipped item --> quarantine
    v
reconcileAndQualityGateStep
        |
        +-- fails threshold --> FAILED / NOT_PUBLISHED
        |
        v
publishStep
        |
        v
Downstream reads approved dataset
```

A job can finish the import step with skipped items inside the technical budget, yet the gate step still blocks publishing if error rates, business totals, or source completeness fail. Chunks already committed to staging do not automatically roll back when the gate fails; isolate them by `source_batch_id` and keep them invisible downstream.

## 11. Notes on Retry State, Rollback, and Checkpoints

In Spring Batch, **retrying an item** is not the same concept as **restarting a job**:

- Retry occurs inside a single step execution's processing under `RetryPolicy`.
- Rollback can cause the framework to re-read/re-process/re-write several items; actual callback counts do not necessarily equal failing item counts.
- Restart creates a new `JobExecution` for the same `JobInstance` if the prior execution is restartable and identifying `JobParameters` remain unchanged.
- Replaying corrected source data should be managed with a new source version and a dedicated idempotency strategy.

If a job fails due to `PartnerConfigurationException` (such as invalid credentials), the right workflow can be:

1. **Stop retrying**, report `FAILED`.
2. Operations fixes configuration/secrets.
3. Verify dependencies are healthy.
4. **Restart** with the same identifying parameters if job and source allow, using a durable `JobRepository`.
5. Reconcile output and side effects that occurred before the failure.

Do not swap an identifying `run.id` just to "retry" a failed job: changing identifying parameters creates a new instance, breaks checkpoint semantics, and risks duplicates. Conversely, if the source file changed from v1 to v2, do not restart against v1's checkpoint assuming offsets remain unchanged.

### 11.1. `noRollback` Does Not Mean No Retry

In some validation-error setups, a `noRollback` policy may be considered to reduce unnecessary rollbacks in the processor. However, `noRollback(...)`, `noRetry(...)`, and `skip(...)` are **three distinct controls**:

- `noRetry`: do not retry errors of the specified type.
- `skip`: allow the item to be skipped if budget remains.
- `noRollback`: affects transaction rollback behavior for the specified exception type, depending on failure stage and step configuration.

Do not add `noRollback` purely for speed without verifying transactional consistency, especially with writers having side effects. Most of the "retrying permanent errors" problem should be solved first through **exception classification** and a narrow retry allowlist.

## 12. Logging and Metrics: Making Misrouted Retries Visible

An operations team needs answers to: how many retry attempts occurred? Which error category dominates? How many items were ultimately rejected? Did the job fail for data or infrastructure reasons?

| Metric | What it reveals |
| --- | --- |
| `retry_attempts_total` by job/step/error code | Which error types are driving retry spikes |
| `retry_exhausted_total` | How many operations exhausted retry budgets |
| `readSkipCount` | Skipped read errors |
| `processSkipCount` | Items skipped in processor |
| `writeSkipCount` | Items skipped in writer |
| `filterCount` | Items filtered by processor, not skipped |
| `rollbackCount` | Number of step rollbacks |
| `job_duration` | Whether retries are threatening run windows/deadlines |
| `quarantine_pending` | Rejects awaiting remediation |
| `quality_gate_status` | Whether output is approved to publish |

While `StepExecution` provides built-in counters such as `getSkipCount()`, `getProcessSkipCount()`, and `getRollbackCount()`, **the framework does not automatically expose a universal "per-item retry attempt count" across all retry modes**. To measure exact retry attempts, observe through listeners or metrics integrated with the retry mechanism. Never treat exception log counts as final failed item counts.

A structured log entry should include safe fields:

```text
event=batch_item_retry
job=importOrdersJob
step=importOrdersStep
job_execution_id=8521
stage=process
error_code=PARTNER_UNAVAILABLE
attempt=2
```

When an item is genuinely skipped:

```text
event=batch_item_skipped
job=importOrdersJob
stage=process
item_ref=b99c60d44e81a247
reason_code=INVALID_AMOUNT
```

Avoid `log.error("failed item {}", item, exception)` if records contain sensitive data; `toString()` and exception messages/stack traces can leak payloads, SQL parameters, or API responses. Use a protected `item_ref` and an allowlisted error code; avoid high-cardinality item IDs as metric labels.

### 12.1. Alerting on Retry Storms

Illustrative operational rules:

```text
WARN:
  retry attempts / minute rises 5x above baseline

CRITICAL:
  error_code=INVALID_AMOUNT appears in retry metrics
  OR retry_exhausted climbs continuously for several minutes
  OR Partner API 503 hits > 50% of items in window
```

These thresholds are illustrative. What matters is catching **permanent errors being retried**, since that usually signals a misconfigured retry policy or exception mapping. For widespread outages, fail/stop under control rather than letting thousands of items retry in lockstep.

## 13. Testing That Permanent Errors Are Not Retried

Do not just write a test asserting "job `COMPLETED`" while ignoring processor/gateway call counts. Goals to prove:

1. Invalid data items **never call the API** and never retry.
2. Transient errors retry within limits and succeed.
3. Configuration errors are neither skipped nor mass-retried.
4. When retry budget is exhausted, the step/job fails per policy.
5. Skip and quarantine never turn bad data into silent data loss.

### 13.1. Unit Test: Invalid Validation Never Calls Gateway

```java
package com.example.batch;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

class OrderProcessorTest {

    @Test
    void invalidAmountFailsBeforeGatewayCall() {
        PartnerGateway gateway = Mockito.mock(PartnerGateway.class);
        OrderProcessor processor = new OrderProcessor(gateway);

        IncomingOrder invalid = new IncomingOrder("o-001", "not-a-number");

        assertThatThrownBy(() -> processor.process(invalid))
                .isInstanceOf(InvalidOrderException.class)
                .hasMessage("INVALID_AMOUNT");

        verifyNoInteractions(gateway);
    }
}
```

This is a **processor unit test** verifying pre-gateway validation only. It does not test Spring Batch's retry policy, because retries reside in the fault-tolerant step rather than firing on a direct call to `processor.process(...)`.

### 13.2. Testing a Gateway with Deterministic Transient Failures

A counter-based stub simulating two failures followed by success:

```java
package com.example.batch;

import java.util.concurrent.atomic.AtomicInteger;

public class ScriptedPartnerGateway implements PartnerGateway {

    private final AtomicInteger calls = new AtomicInteger();

    @Override
    public String registerOrder(String orderId) {
        int current = calls.incrementAndGet();
        if (current <= 2) {
            throw new TransientPartnerException("PARTNER_UNAVAILABLE");
        }
        return "partner-ref-ok";
    }

    public int callCount() {
        return calls.get();
    }
}
```

When using this stub bean inside an **integration test running a real Spring Batch step**, with `retryLimit(3)` and no extra rollbacks/restarts inflating attempts outside the scenario, the item can succeed on the third attempt. Because complex transaction scenarios can trigger additional callbacks, tests must isolate data sources, transactions, steps, and policies—never treat a pure `OrderProcessor` unit test as proof that retries are properly configured.

### 13.3. Integration Test with `@SpringBatchTest`

In a Gradle project using Spring Boot, test dependencies typically include:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

A Spring Batch test suite can use `JobLauncherTestUtils` and `JobRepositoryTestUtils` against an isolated test database:

```java
@SpringBatchTest
@SpringBootTest(properties = {
    "spring.batch.job.enabled=false",
    "spring.batch.jdbc.initialize-schema=always"
})
class RetryClassificationIT {

    @Autowired
    JobLauncherTestUtils launcher;

    @Test
    void invalidInputIsSkippedWithoutRetries() throws Exception {
        // Arrange:
        // - Reader returns an IncomingOrder(amountText="bad").
        // - Processor and gateway are instrumented to count attempts.
        // - Step uses retry allowlist and skipLimit from section 6.
        // - Writer/quarantine run against isolated test database.

        JobExecution execution = launcher.launchJob(testParameters());

        // Assert:
        // - Job/step have status matching the test contract.
        // - processSkipCount == 1.
        // - gatewayCallCount == 0.
        // - Reject record is written exactly once.
        // - No retry event emitted for INVALID_AMOUNT.
    }
}
```

This is an **illustrative test skeleton**: test fields, configuration beans, and `testParameters()` must be defined by the project to run. The aim is to highlight required assertions rather than present a snippet pretending all dependencies and fixtures are already wired.

You can expand this into a matrix:

| Scenario | Expected retries | Final outcome |
| --- | --- | --- |
| `INVALID_AMOUNT` in processor | 0 retries | Skip/quarantine if policy allows |
| Critical `MISSING_ORDER_ID` | 0 retries | Fail or quality gate blocks publish |
| Partner times out twice, 3rd succeeds | Retries within limit | Item is written |
| Partner 503 continuously | Bounded retries | Step `FAILED` when exhausted without skipping |
| Partner 401 bad credentials | 0 retries | Fail fast, report configuration error |
| HTTP 409 from pre-existing order | Per idempotency contract, no blind retry | Verify status and avoid duplicates |
| Whole-file bad CSV header | No line-by-line retries | Preflight `FAILED` |
| DB duplicate key from prior write | No blind retry | Reconcile/upsert or classified error |
| Writer failure rolling back chunk | Per transaction/retry policy | Incomplete snapshot is not published |
| Job restart after config fix | Same identifying params | No duplicates, verify checkpoint |

### 13.4. Testing Wrapped Exceptions

In real applications, a client may throw a `CompletionException` wrapping `InvalidOrderException` or `TransientPartnerException`. If an adapter wraps **all errors** into `RuntimeException`, the fault-tolerance classifier may misroute them. Test that the adapter emits the exact exception types handled by the step, or test the classifier explicitly against the specific exception chain.

Never assume Spring Batch automatically unwraps every nested cause the way your application intends. Design an explicit error-translation boundary and test the path from HTTP/JDBC responses to the exception received by the step.

## 14. Real-World Incidents and Remedies

| Symptom | Common cause | Fix |
| --- | --- | --- |
| A malformed item is processed repeatedly | `.retry(Exception.class)` or `.retry(RuntimeException.class)` | Retry allowlist for transient exceptions; validate and skip/fail permanent ones |
| Job suddenly slows down, error logs spike | Retry storm from bad file schema | Preflight headers/manifest, bound skips, and fail fast |
| HTTP 401 retried for every item | Adapter maps all HTTP errors to transient | Classify auth/config errors as permanent and fail |
| Valid items skipped during partner 503 | Overly broad `.skip(Exception.class)` or `.skip(TransientPartnerException.class)` | Do not skip outages; bounded retry then fail/stop |
| Job `COMPLETED` yet output misses many items | Huge skip limit, no quality gate | Quarantine, count reconciliation, publish gate |
| API receives multiple create calls for same order | Non-idempotent external call | Stable idempotency key, status lookup, or outbox |
| Retry 3 times yet API receives 9 requests | Both HTTP client and batch retry | Pick one retry-owning layer and a shared budget |
| Item logged ERROR three times yet still succeeded | Attempt logging does not distinguish final outcome | Emit distinct `retry_attempt`, `skipped`, and `failed` events |
| Retrying after config fix still fails | Job did not reload config/secrets, or invalid source | Stop execution, fix config, controlled restart |
| Restart reprocesses entire file | Changed `run.id` or lost `JobRepository` | Keep identifying params and durable metadata |
| Unclassified exception gets skipped | Policy uses overly broad superclass | Fail unknown errors and extend classifier after investigation |
| Retries exhausted yet scheduler reports success | JVM exit code does not reflect job status | Map `JobExecution`/`ExitStatus` to proper process exit code |

## 15. Operational Procedure When Permanent-Error Retries Are Detected

When dashboards report abnormal retry volume, follow a sequence:

1. **Identify the dominant error** by `job`, `step`, `error_code`, time, error rate, and attempt count; do not read raw sensitive payloads from general logs.
2. **Classify the root cause**: item input, whole-file source, configuration, API, database, or code bug.
3. **Assess side effects** already committed by the writer/API and duplicate risk on retry.
4. **Stop the retry storm** via controlled fail/stop policies, reducing concurrency, or opening a circuit breaker during dependency outages.
5. **Fix the right place**: fix source/schema/config or exception mapping rather than merely raising `retryLimit`.
6. **Choose a recovery path**: restart the same instance when source and checkpoints remain valid; replay a new source version if items were corrected; quarantine approved rejectable items.
7. **Reconcile outputs** against inputs, accepted/rejected/filtered counts, and external systems before publishing.
8. **Add regression tests** ensuring that permanent error category is never retried in future deployments.

Do not manually delete `BATCH_*` metadata, edit `JobExecution` status via SQL, or randomize identifying parameters just to "make the job run". Those shortcuts easily break checkpoints and destroy auditability of processing history.

## 16. Practice Exercises

Build `importOrdersJob` with the following fixture:

```csv
order_id,amount
o-001,150.00
o-002,not-a-number
o-003,-10.00
o-004,25.00
o-005,80.00
```

`o-002` and `o-003` are permanent data errors. The partner gateway is configured so `o-004` times out twice then succeeds, while `o-005` returns `PARTNER_UNAVAILABLE` continuously. Goals:

1. Write a processor validating `amount` before calling the gateway; permanent errors throw `InvalidOrderException` with a fixed reason code.
2. Configure the step with `.retry(TransientPartnerException.class)`, `.retryLimit(3)`, and `.skip(InvalidOrderException.class)` with an appropriate limit.
3. Use a stub/counter to prove `o-002` and `o-003` never call the gateway and incur zero retry attempts.
4. Prove `o-004` recovers from transient errors within budget; distinguish retry counts from skipped item counts.
5. Have `o-005` fail continuously and verify the job/step fails when retries are exhausted instead of silently skipping.
6. Switch the gateway to return `PartnerConfigurationException` (invalid auth) and verify fail-fast with no per-item retries.
7. Use a `SkipListener` to write rejects to quarantine, then reconcile accepted, rejected, and filtered counts against the manifest.
8. Simulate the writer/partner losing a response after succeeding, and verify idempotency keys or an outbox prevent duplicate processing.
9. Simulate many permanent-error items at once. Compare attempt counts and duration between a retry allowlist and an overly broad test config; never deploy the overly broad config to production.
10. Trigger a configuration failure causing the job to be `FAILED`, fix the config, then restart with the same identifying parameters; verify zero duplicates and that data is published only when the quality gate passes.

**Core takeaway:** retry is a response to **conditions likely to change**, not a cure for bad data or broken configuration. With Spring Batch, **classify errors at clear boundaries**, retry only transient exceptions within a bounded budget, **never retry permanent errors**, decide skip/quarantine vs. fail according to the data contract, and ensure retries/restarts produce no duplicate side effects. Only then is a batch truly fault-tolerant without hiding errors or eroding output trustworthiness.
