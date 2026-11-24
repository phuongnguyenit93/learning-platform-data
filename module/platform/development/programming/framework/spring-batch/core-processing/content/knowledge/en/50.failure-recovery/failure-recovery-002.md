# Processor Failures in Spring Batch: Detection, Handling, and Recovery

## 1. What Is a Processor Failure?

In a Spring Batch **chunk-oriented step**, `ItemProcessor<I, O>` receives an item from `ItemReader`, validates or transforms it, and returns the output item to `ItemWriter`. A processor failure occurs when `process(...)` **throws an exception** during this step.

Common causes:

- **Invalid input data:** missing order ID, negative amount, invalid date format, required business code not found.
- **Transient dependency errors:** lookup service timeout, brief connection drop, service returning 503, cache/backend temporarily unavailable.
- **Application logic bugs:** unexpected `NullPointerException`, wrong calculation, mis-mapped fields, incorrect assumptions about data.
- **State and concurrency bugs:** processor holds mutable fields in the wrong scope, shared state across threads, or output depends on item ordering.
- **Resource exhaustion:** out-of-memory errors, exhausted connection pools, inappropriate timeout/retry settings.

Example of a processor validating orders:

```java
public ValidatedOrder process(OrderInput item) {
    if (item.amount().signum() <= 0) {
        throw new InvalidOrderRowException("amount must be positive");
    }
    return new ValidatedOrder(item.id(), item.amount());
}
```

For a record with `amount=-10`, the processor throws an exception. Spring Batch decides whether to **fail the step, retry, or skip** depending on step configuration and exception type.

One distinction to establish up front:

| `process(...)` Outcome | How Spring Batch Interprets It | What Happens to the Item? |
| --- | --- | --- |
| Returns an object `O` | Processing succeeded | Output item is passed to the writer |
| Returns `null` | **Intentional filter** | Item is not passed to the writer; increments `filterCount` |
| Throws an unhandled exception | **Failure** | Step can transition to `FAILED` and the transaction/chunk is affected |
| Throws an exception covered by retry policy | **Retry** | Framework retries according to policy and limits |
| Throws an exception covered by skip policy | **Skip** | Item is skipped within limits and processing can continue |

**`null` is neither a failure nor a skip.** If all exceptions are caught and turned into `null`, dashboards may show the job as `COMPLETED` while bad data silently disappears. Only use filtering for items that business rules explicitly allow dropping.

## 2. Where Do Failures Occur in the Chunk Lifecycle?

A chunk step typically follows this flow:

```text
               Chunk transaction
                       |
      +----------------+----------------+
      |                                 |
      v                                 |
 ItemReader<I>                          |
      |                                 |
      v                                 |
 ItemProcessor<I,O>                     |
      |                                 |
      +---- return O ----------------+  |
      |                              |  |
      +---- return null -> FILTER    |  |
      |                              |  |
      +---- throw exception          |  |
                   |                 |  |
                   v                 |  |
             Fault-tolerance         |  |
             configuration           |  |
             /      |       \        |  |
           retry   skip     fail     |  |
                    |                |  |
                    +-- continue ----+  |
                                     v  |
                                ItemWriter<O>
                                     |
                                 COMMIT or
                                 ROLLBACK
```

Example with `chunk(3)`, input:

```text
ORD-001 valid
ORD-002 valid
ORD-003 validation error in processor
ORD-004 valid
ORD-005 valid
```

If the step has **no fault tolerance**, the error on `ORD-003` typically prevents the current chunk from completing and the step ends as `FAILED`. Previously committed chunks may retain their data. If the step is configured with `skip(InvalidOrderRowException.class)` and skip budget remains, the framework can skip `ORD-003`, continue processing the remaining items, and complete the step.

Rollback details, re-invocation of reader/processor, and attempt counts depend on the exception type, retry/skip policies, reader type, transaction manager, and Spring Batch configuration. Do not assert that "the processor is invoked exactly once per row" when retry is enabled or chunk rollback occurs.

### A Chunk Transaction Does Not Mean Every Side Effect Is Transactional

With JDBC readers/writers in the same transaction, a rollback can undo uncommitted database changes in the chunk. However, if the processor calls an HTTP API, sends a message, or writes a file outside the transaction, that effect may **not roll back** when the chunk fails.

Example:

```text
processor calls charge API -> API succeeds
writer writes database     -> timeout error
Spring Batch rolls back chunk
processor is called again  -> API risks charging again
```

Therefore, processors should favor **side-effect-free validation/transformation**. If calling external systems is necessary, design idempotency keys, bounded retries, explicit timeouts, and proper outcome recording. Do not rely on JDBC rollback to protect a remote API.

## 3. Classifying Errors Before Choosing a Recovery Strategy

Effective failure recovery starts by classifying errors by **recoverability** and **data validity**.

| Error Category | Example | Typically Appropriate Policy |
| --- | --- | --- |
| Permanent single-item validation error | Negative amount, missing required field, invalid code | Controlled skip or fail/quarantine per business rules |
| Transient dependency error | HTTP 503, network timeout, resource temporarily unavailable | Bounded retry with backoff |
| Configuration/system-wide error | Missing bean, wrong schema, invalid credentials | Fail fast, alert, and fix configuration |
| Unexpected logic bug | `NullPointerException` from a bug, broken invariant | Fail and investigate; do not configure broad skips |
| Business data conflict | Same transaction ID with conflicting content | Fail or store conflict/quarantine; do not auto-skip |
| Valid item out of processing scope | Order not yet due, transaction type excluded by policy | Return `null` to filter |

Do not apply a blanket rule like `retry(Exception.class)` or `skip(Exception.class)` everywhere. It can wastefully retry deterministically bad data, hide bugs, and lose business records.

One design pattern is creating **meaningful business-level exceptions**:

```java
public final class InvalidOrderRowException extends RuntimeException {
    public InvalidOrderRowException(String message) {
        super(message);
    }
}

public final class CatalogTemporarilyUnavailableException
        extends RuntimeException {
    public CatalogTemporarilyUnavailableException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
```

The exception classes above are application examples, not built-in Spring Batch exceptions. External system adapters should translate genuinely transient failures into `CatalogTemporarilyUnavailableException`, while letting authentication errors, bad requests, or mapping bugs surface under appropriate error types.

## 4. Example Processor for Order Validation

Suppose a job reads data:

```csv
order_id,customer_code,amount
ORD-001,C001,100.00
ORD-002,C002,-20.00
ORD-003,C003,75.50
ORD-004,C004,180.00
```

Rules:

1. `order_id` must not be blank.
2. `amount` must be greater than 0.
3. `customer_code` must reference a valid customer.
4. If the catalog service fails transiently, it may be retried.
5. Validation-invalid lines are skipped **only if ingestion policy permits**, and reconciliation details must be recorded.

Model:

```java
import java.math.BigDecimal;

public record OrderInput(
        String orderId,
        String customerCode,
        BigDecimal amount
) {}

public record ValidatedOrder(
        String orderId,
        String customerId,
        BigDecimal amount
) {}

public record CustomerRef(String customerId) {}

public interface CustomerCatalog {
    CustomerRef findCustomer(String customerCode);
}
```

Processor:

```java
import java.math.BigDecimal;
import java.util.Objects;
import org.springframework.batch.item.ItemProcessor;

public final class ValidatingOrderProcessor
        implements ItemProcessor<OrderInput, ValidatedOrder> {

    private final CustomerCatalog customerCatalog;

    public ValidatingOrderProcessor(CustomerCatalog customerCatalog) {
        this.customerCatalog = Objects.requireNonNull(customerCatalog);
    }

    @Override
    public ValidatedOrder process(OrderInput item) {
        if (item.orderId() == null || item.orderId().isBlank()) {
            throw new InvalidOrderRowException(
                    "order_id is required");
        }

        if (item.customerCode() == null
                || item.customerCode().isBlank()) {
            throw new InvalidOrderRowException(
                    "customer_code is required for " + item.orderId());
        }

        if (item.amount() == null
                || item.amount().compareTo(BigDecimal.ZERO) <= 0) {
            throw new InvalidOrderRowException(
                    "amount must be positive for " + item.orderId());
        }

        // Adapter may throw CatalogTemporarilyUnavailableException.
        CustomerRef customer =
                customerCatalog.findCustomer(item.customerCode());

        if (customer == null) {
            throw new InvalidOrderRowException(
                    "unknown customer for " + item.orderId());
        }

        return new ValidatedOrder(
                item.orderId(),
                customer.customerId(),
                item.amount()
        );
    }
}
```

The processor keeps the transformation relatively simple: invalid inputs produce classifiable errors; transient dependencies raise retryable exceptions; valid results pass to the writer. If `CustomerCatalog` makes an HTTP request, the lookup should be read-only and have a timeout. Avoid calling order-creation, payment, or email-sending APIs inside a processor because the logic may be re-executed.

## 5. Spring Batch Configuration: Fail, Retry, and Skip

Examples use **Spring Batch 5.x, Java 17+**, with `JobRepository` and `PlatformTransactionManager` already configured. The reader and writer are supplied by the application.

### 5.1. Default Behavior: Exceptions Fail the Step

Without fault tolerance enabled:

```java
@Bean
Step validateOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, ValidatedOrder> orderProcessor,
        ItemWriter<ValidatedOrder> orderWriter) {

    return new StepBuilder("validateOrdersStep", jobRepository)
            .<OrderInput, ValidatedOrder>chunk(50, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

If `process(...)` throws an unhandled `InvalidOrderRowException`, the step typically ends as `FAILED`. The goal of this approach is **fail fast**: a single bad row halts the job for operator intervention, suitable when data must be strictly accurate.

Not every system should skip: if a settlement job cannot tolerate missing transactions, skipping one row can cause serious monetary discrepancies even while the job reports success.

### 5.2. Enabling Retry for Transient Errors and Skip for Data Errors

```java
@Bean
Step validateOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, ValidatedOrder> orderProcessor,
        ItemWriter<ValidatedOrder> orderWriter,
        OrderSkipAuditListener skipAuditListener) {

    return new StepBuilder("validateOrdersStep", jobRepository)
            .<OrderInput, ValidatedOrder>chunk(50, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .faultTolerant()
            .retry(CatalogTemporarilyUnavailableException.class)
            .retryLimit(3)
            .skip(InvalidOrderRowException.class)
            .skipLimit(10)
            .listener(skipAuditListener)
            .build();
}
```

Mechanism:

- `retry(CatalogTemporarilyUnavailableException.class)`: retries only dependency failures classified as transient.
- `retryLimit(3)`: caps attempts under Spring Batch/Retry semantics; do not misread it as always making three **additional** attempts after the first.
- `skip(InvalidOrderRowException.class)`: allows skipping items with validation errors.
- `skipLimit(10)`: sets the step's total skip threshold per policy, including errors that may originate from reader/processor/writer. Exceeding the limit fails the step.
- Exceptions not configured for retry/skip continue to trigger failure by default.

In real code, if an exception is configured for both retry and skip, behavior after retries are exhausted may fall through to skip depending on configuration. Decide clearly whether **exhausted retries should fail or be allowed to skip** according to business rules.

Main imports in Spring Batch 5.x:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;
```

Classes with the same names in Spring Batch 6 may move packages or change APIs. Check the documentation for the version in use before copying imports.

### 5.3. Backoff for Retries

Retrying without pauses can worsen an already overloaded dependency. With Spring Batch 5.x, you can supply a `BackOffPolicy` from Spring Retry:

```java
import org.springframework.retry.backoff.FixedBackOffPolicy;

FixedBackOffPolicy backOff = new FixedBackOffPolicy();
backOff.setBackOffPeriod(250L); // 250 ms

// In FaultTolerantStepBuilder:
.retry(CatalogTemporarilyUnavailableException.class)
.retryLimit(3)
.backOffPolicy(backOff)
```

This illustrates the syntax inside the builder chain, not a standalone Java statement. In production, choose fixed or exponential backoff based on SLAs and service recovery characteristics. For logic tests, use a short pause or a test policy to avoid slowing down the test suite.

**Retry limits must consider total execution time:** many failing items can generate thousands of retry requests. Beyond retry limits, include HTTP client/database timeouts, circuit breakers, or load limits where appropriate for the architecture.

## 6. How Retry, Skip, and Rollback Interact

This is the easiest part of failure recovery to misunderstand.

### 6.1. Processor Errors Can Cause Chunk Reprocessing

Example chunk with three items:

```text
Input: [A, B, C]
Processor:
  A -> OK
  B -> transient error
  C -> not yet processed
```

If `B` is covered by the retry policy, Spring Batch can retry the error using its chunk/fault-tolerance mechanism. When a rollback occurs, some previously read or processed items may be processed again. This depends on reader buffering and transaction configuration.

**Do not design a processor assuming each item is invoked exactly once.** If a processor increments a global counter, sends notifications, or calls a write API, a retry/rollback can create duplicate side effects.

### 6.2. Skip Does Not Mean Every Invocation Rolls Back

For exceptions configured as skippable in the processor, Spring Batch can skip the item and complete the chunk via the fault-tolerant step algorithm. Exact rollback details depend on error type, error timing, rollback policy, and reader/writer components.

Therefore:

- Do not infer from `processSkipCount=1` that exactly one transaction rolled back.
- Do not infer from `rollbackCount=1` that exactly one item failed.
- Do not assume all items before the exception were already committed.
- Inspect final status and committed data to verify behavior.

### 6.3. Counters to Observe

`StepExecution` provides key counters:

| Counter/Status | Primary Meaning |
| --- | --- |
| `readCount` | Number of items successfully read per step metadata |
| `writeCount` | Number of items written via the writer per step semantics |
| `filterCount` | Number of items for which the processor intentionally returned `null` |
| `readSkipCount` | Number of items skipped in the reader |
| `processSkipCount` | Number of items skipped due to the processor |
| `writeSkipCount` | Number of items skipped in the writer |
| `skipCount` | Total skips (read + process + write) |
| `rollbackCount` | Number of recorded rollbacks |
| `commitCount` | Number of step commits per metadata |
| `status` | `COMPLETED`, `FAILED`, `STOPPED`, ... |
| `exitStatus` | Result/exit code, customizable |

Counters reflect **state recorded by Spring Batch**, not necessarily the exact number of newly inserted SQL rows if the writer performs upserts/deduplication or external non-transactional effects. With retries/rollbacks, method invocation counts can also exceed final counter values.

### 6.4. Do Not Use `noRollback(...)` Casually

A fault-tolerant step allows configuring exceptions that do not trigger rollback. However, enable this only when you fully understand where the error occurs and its impact on transaction consistency. Avoid adding:

```java
.noRollback(Exception.class)
```

just to lower `rollbackCount`. Doing so can leave commits in an unexpected state and mask processing failures. Identify the exact exception, transaction boundaries, and data strategy before customizing rollback policies.

## 7. Building a SkipListener to Record Failed Data

If policy permits skipping, **skipped data must be observable and reconcilable**. Do not just record skip counts: capture the source, record identifier, cause, and how to fix or reprocess it.

Spring Batch provides `SkipListener<I,O>`:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.SkipListener;

public final class OrderSkipAuditListener
        implements SkipListener<OrderInput, ValidatedOrder> {

    private static final Logger log =
            LoggerFactory.getLogger(OrderSkipAuditListener.class);

    @Override
    public void onSkipInProcess(OrderInput item, Throwable t) {
        log.warn(
                "Skipped invalid order in processor: orderId={}, type={}, reason={}",
                item.orderId(),
                t.getClass().getSimpleName(),
                t.getMessage()
        );
    }
}
```

In this example, register the listener on the step via `.listener(skipAuditListener)` as shown earlier.

Notes:

- `onSkipInProcess` is for items **skipped in the processor**, not every time the processor throws an exception. An error that is retried and succeeds is not a skip.
- Only log business fields safe to expose; do not log tokens, passwords, or full payloads containing sensitive data.
- For systems needing reprocessing, write failed items to a quarantine table or an audit stream with dedicated transaction/idempotency handling.
- Listeners do not turn external operations into exactly-once. If writing audits to a different system than the chunk database, handle potential duplicates on crash/retry.

**Distinguish skip from filter:** when a processor returns `null`, `onSkipInProcess` is not called because no skippable exception occurred. If business-filtered items must be audited, use a dedicated mechanism.

## 8. When Does the Step Fail Completely?

A step can end as `FAILED` if:

1. The processor throws an exception **not configured for retry/skip**.
2. Retry is allowed but eventually fails and the policy does not permit skip.
3. Skips exceed `skipLimit`.
4. A fatal error occurs in the reader/writer/transaction manager/listener or infrastructure.
5. An exception prevents processing from completing under the current configuration.

Example: a step allows skipping at most two validation errors, but the file contains three bad rows.

```text
ORD-001  OK
ORD-002  INVALID -> skip #1
ORD-003  OK
ORD-004  INVALID -> skip #2
ORD-005  INVALID -> exceeds skip limit -> FAILED
```

Chunks **already committed** before the failure may have persisted their output. A `FAILED` step **does not mean the database always reverts to an empty pre-job state**. That is why restart, checkpoints, and idempotent writers matter.

When a failure happens, record `jobExecutionId`, `stepExecutionId`, step name, status, exception class, and relevant business parameters so the incident can be traced.

## 9. Recovery by Restarting After a Processor Error

### 9.1. Restart vs. Running a New Job

In Spring Batch, a `JobInstance` is identified by the job name and identifying `JobParameters`. One instance can have multiple `JobExecution`s if a prior run failed and is restarted.

```text
JobInstance: importOrdersJob, businessDate=2026-11-16
    |
    +-- JobExecution #301: FAILED
    |       |
    |       +-- StepExecution #700: FAILED at ORD-150
    |
    +-- JobExecution #302: COMPLETED (restart)
            |
            +-- StepExecution #701: COMPLETED
```

If you launch the second run with **new identifying parameters**, that is **a different JobInstance**, which does not prove restart logic works. For a restart, preserve identity and repository metadata.

### 9.2. Why Checkpoints Affect Results

A chunk-oriented step stores read progress and related state in `ExecutionContext` (if the reader/components are configured to save state appropriately). On restart, Spring Batch can resume from the last committed chunk checkpoint instead of re-reading the entire file.

Conditions to consider:

- Stateful restartable readers must be configured with `saveState` and stable component names.
- Do not delete `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION`, or execution context records before restarting.
- Input sources should be stable or clearly versioned. If the file changes between runs, checkpoints can point to different data.
- Writers must ensure replayed items do not duplicate effects.
- In-memory state inside a processor is not automatically recovered. If state affects logic, plan to persist/restore it via `ExecutionContext` or design the processor to be stateless.

### 9.3. Fixing Data Before Restarting

Suppose a job failed because `ORD-150` had a negative amount and policy required failing. Two recovery options:

**Option A — fix input with version management:** correct the source per operational procedures, verify whether the checkpoint remains valid, and then restart or rerun in a controlled way. If file structure or ordering changed, do not assume an in-place restart is safe.

**Option B — approved quarantine / skip:** when business rules allow processing remaining rows, configure explicit skips, record traces of excluded items, and establish a follow-up handling workflow. Raising `skipLimit` is not an automatic "fix" for bad data.

Never delete metadata and relaunch just to hide a failure. If a fresh run is truly needed, make that an explicit decision and account for previously committed data.

## 10. Idempotency and Processor Side Effects

An important principle: **Spring Batch can re-execute operations during retry, rollback, or restart.** Consequently, a processor should be designed so that reprocessing the same input produces no unintended side effects.

### Preferred Design

```java
public ValidatedOrder process(OrderInput item) {
    // Pure validation and calculation:
    BigDecimal normalizedAmount =
            item.amount().setScale(2, RoundingMode.HALF_UP);
    return new ValidatedOrder(
            item.orderId(),
            item.customerCode(),
            normalizedAmount
    );
}
```

The snippet requires importing `java.math.BigDecimal` and `java.math.RoundingMode`. Calling it again with the same input produces the same result, making retries straightforward to control.

### Risky Design

```java
public ValidatedOrder process(OrderInput item) {
    paymentApi.charge(item.customerCode(), item.amount());
    return toValidatedOrder(item);
}
```

If the processor is re-invoked due to a chunk rollback, the payment API may be called again. To execute such business operations safely, you need:

- A stable business idempotency key derived from the source transaction—never `stepExecutionId` as a business uniqueness key.
- Receiver support for handling repeated requests without executing twice.
- Clear distinction between timeouts with **unknown outcome** and definitive business rejections.
- Consideration of outbox, staging, or event-driven orchestration instead of side effects inside a processor.

**"Retry succeeded" does not mean "the side effect happened exactly once."** Recovery tests must verify both transaction state and actual impacts on connected systems.

## 11. Test Fixtures for Processor Failures

A good test suite needs reproducible cases:

| Test ID | Input / Condition | Expected Result |
| --- | --- | --- |
| P01 | All items valid | `COMPLETED`, zero process skips |
| P02 | One item with negative amount, skip disabled | Step `FAILED` |
| P03 | One item with negative amount, skip enabled | Item skipped, `processSkipCount=1` if within limit |
| P04 | Processor returns `null` for out-of-scope item | `filterCount=1`, not counted as process skip |
| P05 | Catalog times out once then succeeds | Bounded retry, accurate final output |
| P06 | Catalog always returns transient error | Retries exhausted, step `FAILED` if skip disallowed |
| P07 | Invalid items exceed `skipLimit` | Step `FAILED`; previously committed chunks still verified |
| P08 | Failure after at least one committed chunk | Restart resumes accurately without duplicate output |
| P09 | Processor has mutable state and retries | Exposes incorrect processing due to unrolled-back state |
| P10 | Two workers running in parallel | No cross-talk state, no duplicate side effects |
| P11 | Exception is a programming bug | Not swallowed by overly broad skip policy |
| P12 | Audit/quarantine of skipped item | Error record has sufficient detail without leaking sensitive data |

For each fixture, define **input, fault injection, policy, and expected output**. Do not assert only `BatchStatus`; verify record counts and actual business data values.

## 12. Unit Testing the Processor and Error Policies

### 12.1. Unit Testing Validation

Processor unit tests do not require booting a Spring context or database; they verify the exact exceptions thrown on bad inputs.

```java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class ValidatingOrderProcessorTest {

    private final CustomerCatalog catalog = mock(CustomerCatalog.class);
    private final ValidatingOrderProcessor processor =
            new ValidatingOrderProcessor(catalog);

    @Test
    void invalidAmountThrowsValidationException() {
        OrderInput item = new OrderInput(
                "ORD-BAD", "C001", new BigDecimal("-10.00"));

        assertThrows(InvalidOrderRowException.class,
                () -> processor.process(item));

        verifyNoInteractions(catalog);
    }

    @Test
    void validOrderIsMappedToValidatedOrder() {
        when(catalog.findCustomer("C001"))
                .thenReturn(new CustomerRef("CUSTOMER-1"));

        OrderInput item = new OrderInput(
                "ORD-OK", "C001", new BigDecimal("100.00"));

        ValidatedOrder actual = processor.process(item);

        assertEquals("ORD-OK", actual.orderId());
        assertEquals("CUSTOMER-1", actual.customerId());
        assertEquals(new BigDecimal("100.00"), actual.amount());
    }

    @Test
    void transientCatalogFailureIsNotSilentlyFiltered() {
        when(catalog.findCustomer("C001"))
                .thenThrow(new CatalogTemporarilyUnavailableException(
                        "catalog temporarily unavailable",
                        new java.io.IOException("timeout")));

        OrderInput item = new OrderInput(
                "ORD-RETRY", "C001", new BigDecimal("20.00"));

        assertThrows(
                CatalogTemporarilyUnavailableException.class,
                () -> processor.process(item));
    }
}
```

These tests verify **processor logic and exception types**, not yet whether the framework retries or skips according to policy. That part requires testing an actual running step.

### 12.2. Testing Retry with a Controllable Fake Dependency

To simulate transient failures in integration tests, use a fake catalog that counts invocations:

```java
import java.util.concurrent.atomic.AtomicInteger;

public final class FlakyCatalog implements CustomerCatalog {
    private final AtomicInteger attempts = new AtomicInteger();

    @Override
    public CustomerRef findCustomer(String customerCode) {
        if (attempts.incrementAndGet() < 3) {
            throw new CatalogTemporarilyUnavailableException(
                    "simulated transient failure", null);
        }
        return new CustomerRef("CUSTOMER-1");
    }

    public int attempts() {
        return attempts.get();
    }
}
```

This fake throws on the first two calls and succeeds on the third. It works well for sequential step tests processing one item that calls the catalog. If a step has multiple items or runs in parallel, a shared counter can shift failure conditions unexpectedly; key the fake by business key or use a dedicated test scope to pin down exact per-item failures.

In an integration test with `retryLimit(3)`, if the policy applies properly to the exception, the step can overcome the transient failure without producing duplicate output. Assert **the final output** alongside the fake's call count. Do not use `Thread.sleep(...)` to simulate transient failures.

## 13. Integration Testing with Spring Batch Test

In **Spring Batch 5.x**, the `spring-batch-test` module provides `@SpringBatchTest` and `JobLauncherTestUtils`. You can write an integration test using a dedicated test job, a reader over fixed fixtures, and a writer persisting to a test database.

Structural example:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class OrderProcessorRecoveryIT {

    @Autowired
    private JobLauncherTestUtils launcher;

    @Test
    void skipsOneInvalidOrderAndCompletes() throws Exception {
        // Assuming the test context already has the right job to run,
        // the reader contains a fixture with 5 lines, 1 validation error line,
        // and the writer writes output to a dedicated test database.
        var params = new JobParametersBuilder()
                .addString("testRun", java.util.UUID.randomUUID().toString())
                .toJobParameters();

        JobExecution execution = launcher.launchJob(params);
        assertEquals(BatchStatus.COMPLETED, execution.getStatus());

        StepExecution step = execution.getStepExecutions()
                .iterator().next();
        assertEquals(5, step.getReadCount());
        assertEquals(1, step.getProcessSkipCount());
        assertEquals(4, step.getWriteCount());

        // Also query output: verify exactly four valid orders.
    }
}
```

This is an **illustrative test skeleton**. To run it, the application must provide a matching job for `launcher`, configured `JobRepository`, test database/schema, fixture reader/writer, and the skip policy described. If the context has multiple `Job` beans, set the target job on `JobLauncherTestUtils` before launching. If the processor filters items or the writer drops records, adjust expected counters to match actual policy.

For Spring Batch 6.x, test utilities and some packages changed; `JobOperatorTestUtils` takes over job-launching duties in Spring Batch 6 testing examples. Cross-check APIs against the framework version used in your project.

### Testing Exceeding the Skip Limit

With `skipLimit(1)`, provide a fixture containing two items that throw `InvalidOrderRowException`. A test should verify:

1. The step/job finishes as `FAILED`.
2. No invalid items are written as valid business data.
3. Chunks committed prior to the failure remain clearly identified.
4. Logs/audits include `jobExecutionId` and `stepExecutionId` for investigation.

Do not only assert an exception thrown from `launchJob(...)`: Spring Batch normally records the error on `JobExecution` and returns an execution with status `FAILED`, depending on the error/infrastructure. Inspect `execution.getStatus()` and `execution.getAllFailureExceptions()`.

### Testing Restarts

With a multi-chunk fixture:

- Let the first chunk commit successfully.
- Inject a processor failure in a later chunk so the job becomes `FAILED`.
- Preserve `JobRepository` and output, then fix the failure condition on the fake dependency.
- Restart the exact `JobInstance` via the framework API without changing identifying parameters.
- Assert that the step completes and final output contains no duplicate records.

To test checkpoint restarts, the reader must be configured to save progress appropriately; do not reset metadata tables between the two executions. To repeat tests cleanly across methods, use isolated test databases/schemas or intentionally clean up **after** the entire restart scenario concludes.

## 14. Monitoring and Logging Processor Failures

When investigating a failure, collect:

```text
jobName
jobInstanceId
jobExecutionId
stepName
stepExecutionId
businessDate
itemKey (if non-sensitive)
exceptionType
errorCategory
retryAttempt (if instrumented)
batchStatus
processSkipCount
rollbackCount
```

**Do not log sensitive raw payloads** or place them in metric labels. If many items fail, log an error code/field name, a safe-to-display business key, and a lookup reference to securely stored data.

Spring Batch supports `JobExecution` and `StepExecution` for tracing status. On a standard JDBC repository:

```sql
SELECT
    se.STEP_EXECUTION_ID,
    se.STEP_NAME,
    se.STATUS,
    se.READ_COUNT,
    se.PROCESS_SKIP_COUNT,
    se.WRITE_COUNT,
    se.ROLLBACK_COUNT,
    se.EXIT_CODE,
    se.EXIT_MESSAGE,
    je.JOB_EXECUTION_ID,
    ji.JOB_NAME
FROM BATCH_STEP_EXECUTION se
JOIN BATCH_JOB_EXECUTION je
  ON se.JOB_EXECUTION_ID = je.JOB_EXECUTION_ID
JOIN BATCH_JOB_INSTANCE ji
  ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE se.STEP_EXECUTION_ID = :stepExecutionId;
```

This query retrieves step metadata and cannot by itself prove whether an exception came from the reader, processor, or writer. Error attribution requires additionally checking exception classes, contextual logs, `SkipListener`, or application instrumentation.

### Useful Metrics to Add

| Metric | Purpose |
| --- | --- |
| `job_execution_failed_total{jobName}` | Total failed job executions |
| `step_execution_failed_total{jobName,stepName}` | Detects frequently failing steps |
| `batch_process_skipped_total{jobName,stepName,errorCategory}` | Tracks processor-skipped items |
| Retry attempts by dependency/category | Indicates external service instability |
| Job/step duration | Detects retries slowing down batch runs |
| Quarantine backlog | Tracks unresolved invalid data |
| Last successful completion | Detects jobs no longer completing on schedule |

These are **suggested custom metric names**, not guaranteed default Spring Batch/Micrometer metric names. When using a specific exporter, verify actual metrics and label conventions. Never put `itemId`, `stepExecutionId`, or exception messages in metric labels because time-series cardinality will explode.

## 15. Common Recovery Implementation Mistakes

### Catching Every Exception and Returning null

```java
public Output process(Input item) {
    try {
        return convert(item);
    } catch (Exception ex) {
        return null;
    }
}
```

This turns every error into a filter. The job can finish `COMPLETED` with `filterCount` incremented, while no process skip or failure triggers alerts. Only filter when the business contract permits it.

### Retrying Validation Errors Endlessly

Negative amounts, malformed customer codes, or null required fields will not be "cured" by retrying. Retrying wastes time and increases load. For deterministic errors, choose skip/quarantine or fail per policy.

### Overly Broad Skips

`.skip(Exception.class)` can swallow bugs like `NullPointerException`, mapping errors, or resource access failures. Data disappears while dashboards report `COMPLETED`. Use specific exceptions and appropriate skip limits.

### Non-Idempotent Side Effects in the Processor

If a processor sends emails, creates payments, or publishes messages, retries can replay the side effect. Move those operations out of the processor when possible; for external systems, use idempotency keys and outcome verification.

### Misunderstanding skipLimit

`skipLimit(10)` does not mean "allow 10 errors per chunk"; the limit applies per step and total skips per framework semantics. For batches with millions of records, base skip limits on data-quality requirements rather than picking a large number just to force completion.

### Checking Only Job Status While Ignoring Output Data

A `COMPLETED` job may still lack data due to skips/filters, or the writer may have written wrong results. Reconcile `readCount`, `processSkipCount`, `writeCount`, actual row counts, and business values.

### Resetting the Repository Before Restarting

Deleting `BATCH_*` metadata destroys checkpoints, making the run no longer a true restart. Clean up only after the scenario finishes or inside a fresh test database.

### Ignoring Transaction Boundaries

A failing chunk can roll back while earlier chunks have already committed. Never assume `FAILED` automatically reverts the entire job's output. Writers should be idempotent, and tests must verify output after both failure and restart.

### Mutable State in a Singleton Processor

State such as a `HashSet`, counter, or cache mutated inside a processor can drift on rollback or leak across concurrent executions. Keep processors stateless whenever possible; if state is unavoidable, define lifecycle, transaction, and checkpoint handling clearly.

## 16. Practice Exercises

**Exercise 1 – Default failure.** Create an `ItemProcessor` that throws `InvalidOrderRowException` on negative amounts. Run a chunk step without fault tolerance. Verify `JobExecution`/`StepExecution` reach `FAILED` and inspect already committed chunks.

**Exercise 2 – Skipping invalid data.** Enable `.skip(InvalidOrderRowException.class).skipLimit(2)`. Feed 6 items where 1 has a negative amount. Verify `processSkipCount=1`, output has only the 5 valid items, and the skip listener logs the reason.

**Exercise 3 – Exceeding the limit.** With the same policy, feed 3 invalid items. Verify the step fails upon exceeding the skip limit, check committed records, and identify which data must be reprocessed.

**Exercise 4 – Retrying transient errors.** Use a fake `CustomerCatalog` returning a timeout on the first two attempts and succeeding on the third. Enable retry for the specific exception and verify the final item is written exactly once.

**Exercise 5 – Exhausted retries.** Make the fake always throw the transient exception. Do not configure skip for this error type. Verify the job ends as `FAILED`, logs contain the error code, and retry duration does not grow unboundedly.

**Exercise 6 – Restart after failure.** Let the first chunk commit, then trigger a processor failure in a later chunk. Fix the failure condition and restart the exact `JobInstance` without deleting metadata. Verify there is no duplicate output and remaining items are processed.

**Exercise 7 – Side effects.** Build a processor that simulates sending a notification each time `process` is called. Trigger a retry/rollback to observe duplicate-send risk. Then replace it with an idempotent design or move sending to a safer pipeline and verify the result.

**Exercise 8 – Monitoring.** Log with `jobExecutionId`/`stepExecutionId`, query `PROCESS_SKIP_COUNT` and `ROLLBACK_COUNT`, and reconcile with the quarantine table. Design an alert for abnormal skip spikes even when the job stays `COMPLETED`.

## 17. Conclusion

**Processor failure** is an integral part of Spring Batch recovery design, not merely an exception to catch. For invalid items, decide among **fail**, **skip/quarantine**, or **filter** according to the business contract; for transient dependencies, apply **bounded retry**; for programming bugs, fail and investigate. These policies must work alongside transaction/rollback semantics, checkpoints, idempotency, and job restartability.

A reliable solution does not stop at `BatchStatus.COMPLETED`: it verifies **committed data**, **skipped item counts**, **retry counts**, **accurate recovery of logical work**, and **non-duplicated side effects**. The purer and less stateful the processor design, the easier retry and restart scenarios are to test and operate.

### References

- [Spring Batch Reference – Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html)
- [Spring Batch Reference – Configuring Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html)
- [Spring Batch Reference – Configuring Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html)
- [Spring Batch Reference – Controlling Rollback](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/controlling-rollback.html)
- [Spring Batch Reference – Intercepting Step Execution](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/intercepting-execution.html)
- [Spring Batch Reference – Testing](https://docs.spring.io/spring-batch/reference/testing.html)
