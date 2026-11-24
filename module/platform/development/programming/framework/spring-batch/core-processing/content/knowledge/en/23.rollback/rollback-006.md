# Rollback Policy for Steps with Classifiers

In Spring Batch, a fault-tolerant chunk step can classify exceptions for multiple purposes: which exceptions are retried, which exceptions are skipped, and which exceptions trigger a transaction rollback. These decisions are related but not identical. A skippable exception does not automatically mean the transaction skips rollback; an exception that does not trigger rollback is not automatically retried or skipped either.

The rollback policy determines whether the current transaction must undo uncommitted changes when an exception occurs. In fault-tolerant step configuration, the builder API typically used to declare exceptions that do not require rollback is noRollback. Spring Batch uses rollback classification rules during chunk processing to determine the corresponding behavior.

This is especially important for per-item error handling. If an exception simply reflects a single invalid item and occurs before any changes requiring rollback, avoiding rollback can prevent rolling back the entire chunk. Conversely, if the writer already wrote partial data or created side effects before throwing an exception, skipping rollback can leave an inconsistent state.

## 1. What Does the Rollback Classifier Do?

In fault-tolerant chunk processing, the rollback classifier categorizes an exception by asking: does this exception require rolling back the chunk's transaction?

By default, errors during chunk processing normally lead to rollback so uncommitted changes are undone. When an exception is configured as noRollback, Spring Batch can continue processing under the corresponding policy without requiring rollback solely for that exception.

Rollback classification is an independent decision axis:

| Decision | Question | Common API/Configuration |
|---|---|---|
| Rollback | Does the exception roll back the current transaction? | noRollback(...) in fault-tolerant step |
| Retry | Should the operation be retried when the exception occurs? | retry(...), noRetry(...), retryLimit(...) |
| Skip | Should the failing item be skipped and processing continue? | skip(...), noSkip(...), skipLimit(...) |
| Backoff | How long to wait before the next retry attempt? | backOffPolicy(...) |

Do not conflate these decisions into a single concept. A validation error may not need retry, may be skippable, and may be considered non-rollback if it happens at a safe stage. A deadlock typically needs rollback and retry. A severe configuration error typically needs rollback and should fail the step.

## 2. Distinguishing Rollback Classification from Retry and Skip Classification

For example, the processor detects an order missing a customer code:

- Retry is usually useless because the same input will keep missing the code.
- Skip may be allowed if business rules permit sending the order to a reject store.
- Rollback depends on when the exception occurs and what changes were already executed in the transaction.

Meanwhile, if the writer encounters a deadlock:

- The exception may be retryable.
- The chunk transaction usually needs to roll back to release uncommitted changes and restart the operation cleanly.
- You should not mark a deadlock as noRollback just to avoid rollback.

Illustrative matrix:

| Scenario | Retry? | Skip? | Rollback? | Handling Approach |
|---|---|---|---|---|
| Validation error in processor, no writes yet | Usually no | Possibly | Possibly unnecessary if transaction stays safe and policy fits | Record reject, continue with other items |
| Deadlock when writer writes to database | Usually bounded | Usually no | Yes | Roll back chunk and then retry |
| Missing required configuration | No | No | Yes if transaction started and changes must be undone | Fail step |
| Writer error after partially writing a chunk | Depends on error type | Only when semantics allow | Usually needed | Roll back partial writes before recovery |
| Error reading an unparseable line | Usually no | Possibly | Depends on reader source and transaction | Record line position and reject |

This is a design guide, not an automatic mapping table for every exception. Final decisions depend on the phase where the error arises, the transaction manager, side effects, and business requirements.

## 3. Default Rollback in a Chunk Step

A chunk step processes multiple items within one transaction. For example, with a commit interval of 100:

1. The reader reads items.
2. The processor transforms or filters items.
3. The writer writes remaining items.
4. Spring Batch updates checkpoints and related metadata.
5. The transaction commits.

If an exception rolls back the chunk, uncommitted changes in resources participating in the transaction are undone. Previously committed chunks remain intact.

~~~mermaid
flowchart TD
    A[Start chunk transaction] --> B[Read and process]
    B --> C[Writer writes data]
    C --> D{Exception?}
    D -- No --> E[Commit chunk]
    D -- Yes --> F[Rollback classification]
    F --> G{Rollback required?}
    G -- Yes --> H[Rollback transaction]
    G -- No --> I[Do not roll back solely for this exception]
    H --> J[Retry / skip / fail per policy]
    I --> J
    E --> K[Next chunk]
~~~

Rollback classification does not replace the transaction manager. It only participates in deciding behavior for exceptions during chunk processing; the transaction manager still performs the actual commit or rollback on enlisted resources.

If the writer uses a datasource or connection outside the step's transaction, the rollback classifier cannot make the transaction manager undo that resource. Therefore, verify that the writer actually participates in the transaction managed by the step.

## 4. Declaring Non-Rollback Exceptions with noRollback

In a fault-tolerant chunk step, the builder provides noRollback to declare exceptions that do not require rolling back the chunk transaction according to the rollback classifier.

Example:

~~~java
@Bean
Step validateAndImportOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer,
        ImportSkipListener skipListener) {

    return new StepBuilder("validateAndImportOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .skip(InvalidOrderException.class)
            .skipLimit(50)
            .noRollback(InvalidOrderException.class)
            .listener(skipListener)
            .build();
}
~~~

In this example, InvalidOrderException is declared as both skippable and noRollback. This configuration is appropriate only if the exception represents an item-specific error occurring before any business changes needing rollback, and continuing the transaction will not leave partial data.

noRollback does not replace skip. If the exception is not configured as skippable or the skip limit has been exceeded, the step can still fail. Similarly, skip does not automatically add noRollback; the two decisions must be designed separately.

Do not apply noRollback to all RuntimeExceptions or Exceptions. An overly broad rule can prevent writer errors, infrastructure failures, or programming bugs from rolling back as intended.

## 5. Exception Classifiers and Rules by Exception Class

Rollback classifiers usually operate on exception types. A rule for an exception class may also affect subclasses depending on how the classifier is configured. Therefore, understand the application's exception inheritance tree.

Example:

~~~java
class InvalidOrderException extends RuntimeException {
    InvalidOrderException(String message) {
        super(message);
    }
}

class MissingCustomerException extends InvalidOrderException {
    MissingCustomerException(String message) {
        super(message);
    }
}
~~~

If noRollback is declared for InvalidOrderException and the classifier applies rules to subclasses, MissingCustomerException may receive the same decision. This helps when an entire group of validation errors shares semantics, but is dangerous if a subclass needs rollback because it executed changes before throwing.

Keep exception hierarchies semantically clear:

- Item-specific validation errors.
- Transient dependency errors.
- Severe configuration or programming errors.
- Writer errors that can occur after partially writing data.

Avoid using one generic exception such as BatchProcessingException for diverse errors with different transaction requirements. If distinction is needed, use specific subtypes or a classifier with tested rules.

## 6. Choosing noRollback for Validation Errors in the Processor

One scenario where noRollback can be considered is a processor validating items before the writer performs writes:

~~~java
@Bean
ItemProcessor<OrderInput, Order> validateOrderProcessor(
        CustomerRepository customers) {

    return input -> {
        if (input.customerId() == null || input.customerId().isBlank()) {
            throw new InvalidOrderException("customerId is required");
        }

        if (!customers.existsById(input.customerId())) {
            throw new InvalidOrderException(
                    "Unknown customer: " + input.customerId());
        }

        return new Order(input.orderId(), input.customerId(), input.amount());
    };
}
~~~

If the error occurs only during validation and no business writes happened for the item, you can design the step to skip the item without rolling back the whole chunk. This can reduce overhead when a chunk has many valid items and only a few invalid ones.

However, the processor should not create side effects such as updating tables, sending emails, or calling APIs before validation finishes. Processors should generally be stateless and focused on transformation/validation. If the processor has modified data inside the transaction, evaluate whether skipping rollback leaves those changes intact.

If the goal is simply excluding items under a normal rule, consider returning null to filter instead of throwing an exception and skipping. Filtering clearly signals intentional item exclusion; skipping signals an error tolerated by policy.

## 7. Why Is noRollback Dangerous in the Writer?

A writer can execute multiple write statements within the same chunk. Suppose a chunk contains three items A, B, and C:

1. The writer inserts A successfully.
2. The writer inserts B successfully.
3. The writer throws an exception when writing C.

If these statements participate in the same transaction and the chunk rolls back, inserts A and B are undone along with C. If the exception is classified as noRollback, you cannot assume partial writes will be automatically recovered or that the writer will only re-write C.

Risks include:

- A and B may already be persisted while C failed.
- The writer may be invoked again and insert A/B a second time.
- Some non-database side effects may have already occurred and will not roll back.
- Application counters or state may no longer reflect the same dataset.

Therefore, do not use noRollback for writer exceptions after partial writes have occurred, unless the writer is specifically designed to continue safely with verified atomicity/idempotency. For normal database write errors, default rollback is usually the right choice.

## 8. Combining noRollback with Retry

Retry and noRollback should not be combined casually. Retry normally aims to re-attempt an operation that can succeed once a transient error clears. If the transaction does not roll back, partial changes from the previous attempt may remain in the transaction or resource.

Deadlock example:

- The database reports a deadlock while the writer writes.
- The transaction needs to roll back to release state and enable a clean retry.
- The retry policy retries after a backoff.

Marking deadlock as noRollback can break recovery semantics. Let rollback happen and retry with bounds/backoff.

Validation example:

- The processor detects a bad item before the writer writes.
- Retrying the error is pointless.
- If business rules permit discarding the item and the transaction stays safe, skip with noRollback may be used.

Do not configure retry on validation errors just to wait for data to fix itself. If data can be enriched from an external system, a synchronization step or batch-level retry workflow is more appropriate.

## 9. Combining noRollback with Skip

A skipped exception can still roll back the chunk under the default rollback classifier. This can be necessary, particularly when the error occurs in the writer or after changes needing rollback.

If the exception is an item-specific processor error without side effects, configuring noRollback can reduce unnecessary rollbacks. Still, examine these factors:

- Did the exception arise in read, process, or write?
- Is the reader a transactional queue source?
- Have the processor or writer modified data yet?
- Does SkipListener write reject records in the same transaction or another resource?
- Can other items in the chunk continue safely?

A good skip policy must record discarded items. Do not merely increment skip counts; store source ID, source position, failing phase, and reason for investigation/replay. If the listener writes reject records in the same transaction, confirm those writes commit as desired.

## 10. noRollback and Transaction Attributes

Two configuration layers must be distinguished:

1. Rollback rules of transaction attributes/transaction manager, governing how the transaction handles exceptions at transaction boundaries.
2. Rollback classification in fault-tolerant chunk processing, governing whether an exception during item/chunk processing requires rollback under chunk policy.

In Spring Batch configuration, transaction attributes can also adjust isolation, propagation, timeout, and rollback rules depending on the step builder/API. These settings should not be confused with retry classifiers or skip classifiers.

Example creating a transaction attribute with a timeout:

~~~java
@Bean
DefaultTransactionAttribute chunkTransactionAttribute() {
    DefaultTransactionAttribute attribute =
            new DefaultTransactionAttribute();
    attribute.setTimeout(60);
    return attribute;
}
~~~

Then, depending on the step builder type and Spring Batch version, the transaction attribute can be attached to the step via the corresponding transactionAttribute API. Check the API available in your version before applying it.

Do not configure rollback rules at multiple layers without testing the combined effect. An exception might be treated as noRollback in the chunk classifier while still being subject to different transaction-attribute behavior, or vice versa. Test with real transactions to verify whether database changes commit or roll back as intended.

## 11. noRollback Does Not Make External Side Effects Safe

Database transactions do not automatically manage HTTP requests, emails, filesystems, or message brokers. Whether an exception is marked noRollback or rollback, external side effects may have already occurred.

For example, a processor calls a quota-check API and an API recording one usage. Then the processor throws InvalidOrderException. noRollback cannot undo that API request. If retry or skip causes the item to be reprocessed, the API may receive the same effect again.

Ways to handle this:

- Keep processors pure transformation/validation, avoiding side effects.
- Move side effects into the writer or a separate step with proper transaction/idempotency handling.
- Use stable idempotency keys for external APIs.
- Use a transactional outbox to record outbound message intent in the same database transaction.
- Use inbox/deduplication on consumers.
- Use reconciliation when external request outcomes are uncertain.

The rollback classifier only governs transaction behavior within Spring Batch; it is not a distributed transaction coordinator.

## 12. Checking the Transaction Manager and Propagation

A rollback policy is meaningful only if the writer and repositories participate in the expected transaction. Verify that:

- JdbcTemplate uses the DataSource managed by the step's transaction manager.
- JPA repositories join the corresponding transaction and do not open independent resources.
- JDBC Connections or EntityManagers are not shared across threads.
- Called services do not unintentionally use REQUIRES_NEW.
- Async tasks are not launched under the assumption that the chunk transaction covers them.
- The writer does not manually commit or open uncontrolled separate transactions.

If a service uses REQUIRES_NEW, the new transaction can commit independently. Rolling back the outer chunk does not undo data committed in that inner transaction. This may be intentional for audit records, but is unsuitable when data must roll back with the chunk.

With multiple datasources, have an explicit transaction design. A standard JDBC transaction manager does not automatically create atomic commits across two independent databases. If multiple resources must stay synchronized, consider outbox/saga patterns or distributed transaction solutions suitable for your infrastructure.

## 13. Reader Scenarios and Buffering

Rollback also affects readers. A file reader cannot ask the filesystem to undo a read the way a transactional queue can. Spring Batch can buffer items in fault-tolerant chunk processing for reuse on rollback, depending on reader type and configuration.

With a transactional queue source, message reception can roll back so the message returns to the queue. In that case, configuring readerIsTransactionalQueue() may be necessary so the framework handles the source's semantics properly. Enable this option only when the reader genuinely uses a queue with transactional message reception.

Do not assume noRollback will automatically keep reader state accurate. Stateful readers must implement ItemStream, save checkpoints, and restore properly on restart. If a reader advances an in-memory position past uncommitted items, ensure the framework or reader can replay items accurately.

## 14. Testing the Rollback Classifier

Tests must prove classifier decisions using data state, not merely method invocation counts.

Important scenarios:

1. **Default rollback exception:** writer writes data then throws an exception; verify chunk data is absent after rollback.
2. **noRollback exception in processor:** item is skipped per config; verify remaining valid items are processed and the transaction leaves no partial changes.
3. **noRollback but non-skippable:** verify the step does not automatically succeed just because the exception does not roll back.
4. **Retryable exception:** simulated deadlock causes rollback then retry; verify the subsequent attempt succeeds without duplicate data.
5. **Writer partial failure:** writer writes partially then throws an error; verify rollback protects chunk atomicity.
6. **Exception inheritance:** test whether rules apply to subclasses as intended.
7. **SkipListener:** verify reject records are written accurately without unintended duplicates.
8. **Transaction propagation:** verify whether changes in REQUIRES_NEW persist after outer transaction rollback.
9. **External side effects:** simulate an API having received a request before the exception; verify idempotency/outbox behavior.
10. **Restart:** after the step fails, restart with the same identifying JobParameters and verify checkpoints and outputs are correct.

Example test writer that can fail after inserting:

~~~java
@Bean
ItemWriter<ImportedOrder> failingWriter(
        JdbcTemplate jdbcTemplate,
        FailureSwitch failureSwitch) {

    return chunk -> {
        for (ImportedOrder item : chunk.getItems()) {
            jdbcTemplate.update(
                    "insert into imported_order(order_id) values (?)",
                    item.orderId());
        }

        if (failureSwitch.shouldFail()) {
            throw new IllegalStateException("Simulated writer failure");
        }
    };
}
~~~

When running the step without configuring noRollback for IllegalStateException, the test verifies that the chunk's inserts roll back. If you change the classifier to mark this exception noRollback, the test must explicitly verify final data and prove that configuration is genuinely safe—do not merely change assertions to accept partial data.

Use database integration tests with a real transaction manager. Mocking JdbcTemplate does not prove rollback. Avoid wrapping the entire test method in an outer transaction when the goal is observing real per-chunk commits and rollbacks.

## 15. Reading Metadata After Rollback

StepExecution provides fields that aid investigation:

| Property | Meaning |
|---|---|
| BatchStatus | Execution status of the step |
| ExitStatus | Exit code and outcome description |
| readCount | Number of items read according to metadata |
| writeCount | Number of items written according to metadata |
| skipCount | Total number of skipped items |
| commitCount | Number of recorded commits |
| rollbackCount | Number of recorded rollbacks |
| readSkipCount | Number of items skipped at the reader |
| processSkipCount | Number of items skipped at the processor |
| writeSkipCount | Number of items skipped at the writer |

Counters are useful for investigation but do not replace checking actual data. For example, writeCount does not prove HTTP side effects were confirmed or that data was not duplicated. Cross-check metadata against business tables, reject stores, and logs carrying correlation IDs.

When using noRollback, observe both rollback counts and data outcomes. If rollback count drops while partial or duplicate records appear, the policy is compromising integrity.

## 16. Common Mistakes

**Confusing noRollback with noSkip.** noRollback governs rollback classification; noSkip forbids skipping an exception. The two APIs resolve different decisions.

**Assuming noRollback ignores the exception.** The exception can still fail the step if no suitable retry/recovery/skip policy exists.

**Marking every validation error noRollback without checking side effects.** A processor or listener may have modified data. Audit the entire transaction before suppressing rollback.

**Using noRollback for writer errors after partial writes.** This can retain part of a chunk. For database write failures, rollback is normally required.

**Combining noRollback with retry for deadlocks.** Deadlocks usually require rollback before retrying. Use retry with rollback and backoff.

**Using an overly broad parent exception.** A rule may apply to multiple subclasses with differing semantics. Separate exceptions or test inheritance.

**Assuming the rollback classifier controls every resource.** Files, HTTP calls, and non-transactional messages do not roll back automatically. Use idempotency/outbox/reconciliation.

**Ignoring transaction propagation.** REQUIRES_NEW can commit independently. Verify the transaction manager and propagation of called services.

**Checking only BatchStatus.** A Job may be COMPLETED while data is partial. Verify databases, reject stores, counters, and side effects.

## 17. Workflow for Choosing a Rollback Policy

Before configuring classifiers for a step, clarify:

1. Does the exception originate in the reader, processor, writer, or a listener?
2. At that point, has the transaction made any business changes yet?
3. Can those changes be undone by the step's transaction manager?
4. Can the exception resolve transiently and should it be retried?
5. Is the item allowed to be skipped under business rules?
6. Without rolling back, can the transaction continue and commit safely?
7. Does the writer have non-database side effects or partial writes?
8. Does the rule affect exception subclasses?
9. Do SkipListener and the reject store participate in the appropriate transaction?
10. Are there integration tests proving data after commit/rollback?

Practical rules:

- Keep default rollback for writer errors and infrastructure errors unless there is a clear reason to change.
- Use bounded retry with backoff for transient errors that require rolling back and retrying.
- Use skip for item-specific errors when business rules permit, while recording rejects.
- Use noRollback only when you have proven the exception leaves no changes needing rollback and continuing the transaction is safe.
- Do not use the rollback classifier to handle non-transactional side effects; design separate idempotency or outbox mechanisms.

## Conclusion

Rollback policy for steps with classifiers is an independent decision from retry and skip. The rollback classifier determines whether an exception requires undoing the chunk transaction; the retry classifier determines whether to retry; the skip policy determines whether to discard the item and continue. In a fault-tolerant step, noRollback declares exceptions that do not require rollback under chunk policy.

Use noRollback selectively—typically only for item-specific errors occurring before business changes needing rollback when the transaction remains safe to continue. Avoid applying it to writer errors after partial writes or infrastructure errors such as deadlocks. Verify transaction managers, propagation, reader state, and non-database side effects; then test with a real database to prove commit/rollback outcomes. A classifier is right only when the final data stays consistent with business requirements.
