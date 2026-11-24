# Skip with output that can miss data

In Spring Batch, skip allows a step to continue processing when encountering certain errors defined as skippable. This mechanism is useful when a few input items fail while the rest of the data can still be processed. However, if the output is expected to contain every single source record, skip can produce incomplete output while the job still finishes with a successful status.

For example, a file has 10,000 orders, and 25 lines fail validation. If the step is configured to skip those errors, the writer may write only 9,975 orders. The job may still have BatchStatus COMPLETED because all errors were handled according to policy. Output consumers looking solely at job status might assume all 10,000 orders were imported.

Therefore, deciding to use skip is not purely a technical decision. You must clearly define which data may be discarded, who receives notice of skipped items, by what criteria output is considered complete, and whether the job is allowed to publish results when skips occur.

## 1. What does skip mean for output?

In chunk-oriented processing, the reader reads items, the processor may transform or filter them, and the writer writes the remaining items. When an exception is classified as skippable and the skip limit has not been exceeded, Spring Batch can discard the failing item and continue processing.

Skip can occur in three stages:

| Stage | Case | Impact on output |
|---|---|---|
| Read | Reader cannot read or parse a record | Record never becomes an item for the writer to write |
| Process | Processor detects an invalid item and throws an exception | Item is not forwarded to the writer |
| Write | Writer cannot write an item | Item is skipped per skip policy; other items may continue to be written |

When an item is skipped, it does not appear in the step's normal successful output. If the output is a list of orders, CSV file, database table, or published messages, the result may lack the corresponding items.

~~~mermaid
flowchart TD
    A[Input records] --> B[Reader]
    B --> C{Readable?}
    C -- No, skippable --> S[Record skipped]
    C -- Yes --> D[Processor]
    D --> E{Valid process?}
    E -- No, skippable --> S
    E -- Yes --> F[Writer]
    F --> G{Write succeeded?}
    G -- No, skippable --> S
    G -- Yes --> O[Output]
    S --> R[SkipListener / reject record]
    O --> V[Reconcile and decide publication]
    R --> V
~~~

Skip does not mean Spring Batch deletes source data. It means the item is not processed through the step's success path. If business rules require reprocessing that item, the application must store enough details to fix and rerun it.

## 2. BatchStatus COMPLETED does not guarantee complete output

If a step is configured with skip and the number of skipped items does not exceed the limit, the step can complete normally. In that case:

- The step's BatchStatus can be COMPLETED.
- The job can continue to subsequent steps and ultimately have BatchStatus COMPLETED.
- The skip count is still greater than 0.
- The output may have fewer items than the input or miss part of the business data.

Example:

| Metric | Value |
|---|---:|
| Source records | 10,000 |
| Records read | 10,000 |
| Records skipped in process | 20 |
| Records skipped in write | 5 |
| Records written successfully | 9,975 |
| BatchStatus | COMPLETED (if all other conditions succeed) |

Do not rely solely on BatchStatus to claim that all data was imported completely. Inspect read/write/skip counts, reject records, business-key reconciliation, and output completeness rules.

If business rules require every record to be processed, even one skip can be a critical error. If business rules allow discarding some records, the job must still clearly report the counts and reasons for skipped items.

## 3. Distinguishing skip from filter

A processor can return null to exclude an item from the pipeline. That is filtering, not skipping:

~~~java
@Bean
ItemProcessor<OrderInput, Order> filterCancelledOrders() {
    return input -> {
        if (input.status().equals("CANCELLED")) {
            return null;
        }
        return mapToOrder(input);
    };
}
~~~

In this case, the item is filtered because a business rule intentionally excludes it, it is not passed to the writer, and the filter count increments. SkipListener is not called for filtered items.

Conversely, if the processor throws an exception configured as skippable, the item counts as a process skip. Both cases result in fewer outputs than inputs, yet their meanings differ:

| Behavior | Meaning | What to record |
|---|---|---|
| Processor returns null | Item intentionally excluded per filter rule | Filter reason if audit is needed |
| Exception is skipped | Item could not be processed along the normal path | Item, exception, and skip reason |

Do not return null to mask bad data if business rules require investigation. Conversely, do not throw an exception for a normal exclusion condition if it is simply a well-defined filter.

## 4. Controlled skip configuration

In Spring Batch 5, you can configure skip for specific exception types and set a total limit:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer,
        ImportSkipListener skipListener) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .skip(InvalidOrderException.class)
            .skip(FlatFileParseException.class)
            .noSkip(FatalConfigurationException.class)
            .skipLimit(25)
            .listener(skipListener)
            .build();
}
~~~

In this example, InvalidOrderException and FlatFileParseException are skippable; FatalConfigurationException is not skippable; the step's total skip count is limited to 25; SkipListener receives item/error info for the application to record.

The skip limit applies jointly across read, process, and write stages, not as a separate limit per stage. When the skip count exceeds the limit, the step fails. Check the API of the Spring Batch version in use when configuring a custom classifier or SkipPolicy.

Declare only exceptions with clear meaning. Do not skip every Exception or RuntimeException because doing so can turn programming bugs, database errors, or configuration mistakes into silently discarded records.

## 5. Choosing which errors may be skipped?

An exception suitable for skipping is usually an isolated item-level error that can be identified and handled independently without breaking the integrity of other items.

Examples often worth considering for skip:

- A malformed CSV line where the raw line can be saved for later fixing.
- A record missing a required field per business rules.
- An item referencing a nonexistent catalog code where business rules allow placing it on a reject list.
- A record violating an isolated constraint, if discarding it is permitted by business rules and output is reconciled.

Errors that generally should not be skipped:

- Database disconnection or connection pool exhaustion.
- Payment API unavailability.
- Configuration errors preventing the entire job from running properly.
- Unexpected programming bugs such as NullPointerException.
- Errors that destroy the ability to determine which items were successfully written.
- Errors indicating input data is out of scope or broadly untrustworthy.

An infrastructure outage generally needs bounded retry or failing the step, not dropping items. If the database temporarily fails to write 100 orders, skipping all 100 orders produces severely incomplete output while potentially masking the incident.

## 6. Recording skipped items with SkipListener

When output can miss data, the application needs to know exactly which items were bypassed and why. Spring Batch provides SkipListener with dedicated callbacks for read, process, and write.

~~~java
public class ImportSkipListener
        implements SkipListener<OrderInput, Order> {

    private final RejectedOrderRepository rejectedOrders;

    public ImportSkipListener(RejectedOrderRepository rejectedOrders) {
        this.rejectedOrders = rejectedOrders;
    }

    @Override
    public void onSkipInRead(Throwable throwable) {
        rejectedOrders.saveReadFailure(
                extractSourceLocation(throwable),
                throwable.getMessage());
    }

    @Override
    public void onSkipInProcess(
            OrderInput item,
            Throwable throwable) {
        rejectedOrders.save(
                item.orderId(),
                item.customerId(),
                "PROCESS",
                throwable.getClass().getSimpleName(),
                throwable.getMessage());
    }

    @Override
    public void onSkipInWrite(
            Order item,
            Throwable throwable) {
        rejectedOrders.save(
                item.orderId(),
                item.customerId(),
                "WRITE",
                throwable.getClass().getSimpleName(),
                throwable.getMessage());
    }
}
~~~

This example uses an illustrative repository. In real applications:

- The read callback has no item because the reader could not construct an item; extract line number, offset, or source location from the exception/reader context.
- The process callback receives the input item.
- The write callback receives the processor's output item.
- Store source ID, batch ID, failure stage, exception type, and sufficient detail to fix or rerun.
- Do not persist full stack traces or sensitive payloads into the reject table without an appropriate security and storage policy.

Spring Batch invokes SkipListener using a mechanism that fires the callback once for a skipped item right before the chunk commits, avoiding duplicate callbacks caused solely by internal rollbacks/retries. Even so, reject persistence still needs to participate in an appropriate transaction and include a deduplication key if the workflow can restart or rerun.

## 7. Creating a reject table instead of losing records

For database output, a common pattern is writing valid items to the target table and skipped items to a reject table. That way, successful output can be consumed while failing records are preserved for investigation.

Example schema:

~~~sql
CREATE TABLE import_reject (
    batch_id       VARCHAR(80) NOT NULL,
    source_id      VARCHAR(100) NOT NULL,
    stage          VARCHAR(20) NOT NULL,
    error_code     VARCHAR(100) NOT NULL,
    error_message  VARCHAR(1000),
    created_at     TIMESTAMP NOT NULL,
    PRIMARY KEY (batch_id, source_id, stage)
);
~~~

A unique key on batch, source ID, and stage helps prevent creating multiple reject records for the same error when the job restarts or reruns. If the same source ID can fail across multiple attempts with different causes, decide explicitly whether to keep per-attempt history or only the final reject outcome.

Do not store only the skip count. When reprocessing is needed, operators must know which records were bypassed and have enough information to locate the source data. If a read skip occurred before an item was constructed, store the source location or raw line for traceability.

## 8. File output: writing valid data and a separate error file

For file import/export batches, you can generate two outputs:

- A primary file containing successfully processed records.
- A reject file containing source ID, source line, error type, and reason.

Example layout:

~~~text
output/
  orders-accepted.csv
  orders-rejected.csv
  orders-summary.json
~~~

The summary file can record:

~~~json
{
  "batchId": "ORDERS-2026-11-14",
  "inputCount": 10000,
  "acceptedCount": 9975,
  "rejectedCount": 25,
  "status": "COMPLETED_WITH_REJECTS"
}
~~~

This is an illustrative format; the application must define a stable summary schema. With FlatFileItemWriter, output files are typically managed according to the writer's lifecycle. If the job is restartable, configure state saving and use a stable batch-scoped filename. Do not write the final file directly into a location read by downstream consumers before the job finishes and reconciles.

A safe pattern is writing into a staging directory keyed by batch ID, finalizing all accepted/rejected/summary files, verifying metrics, and only then renaming or publishing a completion manifest. If the job fails, downstream consumers do not treat staging output as official results.

## 9. Message output or external system integration

If the writer publishes a message per item, skips can prevent some events from ever being emitted. That can leave downstream systems missing data silently.

Options:

- Write failing items to a dead-letter topic or reject store with event ID and reason.
- Write an outbox record in the same transaction as business data and publish after commit.
- Use a consumer inbox/deduplication so redelivered messages do not create duplicate side effects.
- Publish a batch manifest stating expected events, emitted events, and rejected events.
- Provide a replay workflow for corrected items after errors are resolved.

Do not catch broker connection exceptions and skip messages. That is usually an infrastructure error requiring retry or failing the step. Only apply skip to item-specific errors that business rules permit bypassing with proper recording.

## 10. Reconciling to detect missing data in output

When skip is allowed, the job needs clear completeness criteria. Do not merely compare input and output line counts because some items may be legitimately filtered, or one source item may produce multiple outputs.

Useful reconciliation checks:

- Source records within batch scope.
- Items read successfully.
- Items filtered by business rules.
- Items skipped in read/process/write.
- Items successfully written by the writer.
- Reject records stored.
- Unique business keys in the output.
- Totals for amounts, quantities, or checksums by business group.

Example reconciliation table:

| Metric | Result |
|---|---:|
| Input records | 10,000 |
| Filtered by business rule | 100 |
| Skipped | 25 |
| Expected accepted output | 9,875 |
| Actual accepted output | 9,875 |
| Reject records | 25 |
| Reconciliation | MATCH |

The reconciliation equation depends on business rules. In a simple example, every source record is either filtered, skipped, or accepted. When one-to-many mappings, duplicate suppression, or aggregations exist, use appropriate keys and aggregations rather than applying a naive sum.

If figures do not match, the job should not publish the output as complete. You can flag the batch for investigation, fail the reconciliation step, or hold output in staging.

## 11. Setting skip thresholds based on data criticality

Skip limit caps how many items may be skipped in a step, yet a fixed cap does not inherently reflect business severity. 25 errors may be acceptable in a marketing file but unacceptable in a settlement statement.

| Policy | When appropriate | Behavior |
|---|---|---|
| Disallow skip | Data must be 100% complete, e.g. ledger or payments | Declare no skip for business errors; step fails |
| Bounded absolute skip | Isolated bad records can be dropped | Configure low skipLimit and record rejects |
| Ratio-based skip | Data quality scales with batch size | Reconcile reject rate in a separate step before publishing |
| Skip requiring approval | Output may be produced but needs sign-off | Set pending review status; withhold publication |

SkipLimit is an item-count cap inside the fault-tolerant step. If a percentage cap is needed, such as rejects not exceeding 0.1% of inputs, compute the ratio in a reconciliation step after the import step completes. Do not try to cram percentage rules into a fixed skip limit when batch sizes vary widely.

## 12. Setting a custom ExitStatus when skips occur

A step can complete with a skip count greater than 0. If the flow must branch differently when rejects exist, set a custom ExitStatus after the step ends.

~~~java
public class SkipOutcomeListener implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getStatus() == BatchStatus.COMPLETED
                && stepExecution.getSkipCount() > 0) {
            return new ExitStatus(
                    "COMPLETED_WITH_SKIPS",
                    "Step completed with rejected items");
        }

        return null;
    }
}
~~~

The flow can route to a reconciliation or approval step:

~~~java
return new JobBuilder("importJob", jobRepository)
        .start(importStep)
            .on("COMPLETED_WITH_SKIPS").to(reconcileRejectsStep)
        .from(importStep)
            .on("COMPLETED").to(publishStep)
        .from(importStep)
            .on("*").fail()
        .end()
        .build();
~~~

In this example, a step with skips does not jump straight to publishing. It goes through the reject reconciliation step first. Define clearly whether reconcileRejectsStep finishes successfully, waits for approval, or fails the job if a threshold is crossed. A custom ExitStatus code does not replace BatchStatus; the step can still have BatchStatus COMPLETED while its exit code is COMPLETED_WITH_SKIPS.

## 13. Do not publish incomplete output

If downstream systems read output as soon as files or tables are written, they may consume data before the job realizes items were skipped or reconciliation failed.

~~~mermaid
flowchart TD
    A[Import step] --> B[Accepted output in staging]
    A --> C[Reject records]
    B --> D[Reconciliation step]
    C --> D
    D --> E{Completeness rules pass?}
    E -- Yes --> F[Publish output / mark batch ready]
    E -- No --> G[Hold batch for review]
~~~

Implementation techniques:

- Write data into staging tables keyed by batch ID.
- Create files inside a temporary directory keyed by batch ID.
- Track a separate batch status such as PROCESSING, READY, REJECTED, or NEEDS_REVIEW.
- Switch to READY only after reconciliation passes.
- Use unique keys so publishing the same batch does not duplicate data.
- Downstream systems read only batches in READY status.

With databases, moving from staging to main tables can be a single transaction or set-based operation after reconciliation. With files, use an atomic rename on the same filesystem plus a completion manifest. With messaging, use an outbox/manifest and clear consumer rules.

## 14. Retry before deciding to skip

A transient error should not be turned into a skip just because the writer failed on the first try. For example, a database deadlock or API timeout may recover upon retrying. If errors are misclassified, the job may finish with missing output even though the items were completely processable.

| Error type | Usually appropriate behavior |
|---|---|
| Invalid item data, unfixable automatically | Skip with audit or fail per completeness requirements |
| Database deadlock | Bounded retry with backoff |
| Temporary connection timeout | Bounded retry; fail if exhausted |
| API rate limit | Retry per service policy with backoff/jitter |
| Misconfiguration or incompatible schema | Fail early, do not skip |
| Uncertain whether side effect occurred | Reconcile/idempotency; do not skip blindly |

If an exception is configured for both retry and skip, understand the behavior once retries exhaust. Test the specific policy of your Spring Batch version to ensure infrastructure errors are not inadvertently skipped.

## 15. Restart and skip: do skipped items automatically reappear?

Skip is generally a decision within the current step execution. When an item is skipped and the step completes, the checkpoint may advance past that item. Restarting the job later does not automatically reintroduce already skipped items into the success path.

To reprocess skipped items, the application needs a detailed reject source and a dedicated replay workflow, for example:

1. Operators fix source data or supply missing reference data.
2. Create a replay batch with the list of rejected source IDs.
3. Use distinct identifying JobParameters for the replay while referencing the original batch.
4. Persist replay results by business key to avoid duplicates.
5. Reconcile accepted/rejected counts across the original batch and the replay.

Do not edit checkpoints in ExecutionContext via SQL to force the reader back to skipped items. Checkpoint metadata belongs to Spring Batch; replaying from a reject list is clearer and safer.

## 16. How can a write skip drop part of the output?

The writer receives a chunk containing multiple items. If the writer throws an exception for one item, the chunk transaction may roll back. In a fault-tolerant step, Spring Batch can isolate the failing item to apply the skip policy and continue writing the remaining items.

This means the chunk's output may contain only the successfully written items, while the failing item is skipped. If the writer performed non-transactional side effects before throwing, rolling back the database does not undo those side effects. When the framework retries or isolates items, the same or other items in the chunk may be dispatched again depending on the handling mechanism.

Example of a writer writing to the database and publishing messages:

1. Write order A to the database.
2. Emit event for A.
3. Writing order B fails.
4. Chunk transaction rolls back database changes.
5. The message for A may already have been accepted by the broker.

Without an outbox or idempotency, downstream consumers may receive event A even though the database no longer reflects that change, or the event may be sent again on retry. This is why writers with non-transactional side effects need dedicated design, even when the step allows skipping.

## 17. SkipListener and the reject record transaction

SkipListener is typically invoked right before the chunk commits so callbacks do not repeat merely because of an internal rollback. If the listener writes reject records using the step's datasource and transaction manager, reject records can commit with the skip-processed chunk's transaction.

This has the benefit of persisting accepted/rejected state together for the chunk. However, consider:

- If saving the reject record fails, the chunk may fail to commit and the step may retry or fail.
- If the listener writes to a different datasource, the step's transaction may not roll back that reject record.
- If a replay or batch rerun generates the same reject record, a unique key must prevent duplicates or store history according to the chosen model.
- The read skip callback has no item; extract source location from the exception or reader state.
- Do not call external APIs directly in SkipListener without idempotency and recovery mechanisms.

If the reject store must stay independent of the main transaction so errors survive chunk rollbacks, explicitly design a separate transaction, outbox, or durable audit mechanism. Do not casually use REQUIRES_NEW because it can commit reject records even when the business chunk rolls back; that may be right or wrong depending on data semantics.

## 18. Testing output with skips

Tests must prove both that skips occur properly and that incomplete output is not mistaken for complete output.

Cases to include:

1. No errors: all valid items written, skip count equals 0.
2. Process skip: failing item does not reach writer; reject record holds exact source ID and reason.
3. Read skip: unparseable line recorded with line number/raw source reference when possible.
4. Write skip: item unwritable by writer goes to reject store; remaining items produce correct results.
5. Skip limit: skips within limit allow step completion; exceeding limit fails the step.
6. Do not skip infrastructure errors: temporary DB/API errors are retried or fail the step rather than silently dropping items.
7. Reconciliation: accepted, filtered, and rejected counts match input scope per business rules.
8. Staging output: batch is not published when reconciliation fails.
9. Restart: committed chunks create no duplicates; skipped items are saved for separate replay.
10. Idempotency: rerunning listener/replay creates no unintended duplicate reject records or side effects.

Example integration test:

~~~java
JobExecution execution =
        jobLauncherTestUtils.launchJob(jobParameters);

StepExecution importStep = execution.getStepExecutions()
        .stream()
        .filter(step -> step.getStepName().equals("importOrdersStep"))
        .findFirst()
        .orElseThrow();

assertEquals(BatchStatus.COMPLETED, importStep.getStatus());
assertEquals(2, importStep.getSkipCount());
assertEquals(98, importStep.getWriteCount());
assertEquals(2, rejectedOrderRepository.countByBatchId(batchId));
assertEquals(98, acceptedOrderRepository.countByBatchId(batchId));
~~~

The example assumes an input of exactly 100 items, two skipped in the processor, no filters, and 98 items written successfully by the writer. If read skips, write skips, or filters occur, adjust numbers according to the actual pipeline.

Tests must use an appropriate repository/database and verify both accepted and rejected data. Asserting only BatchStatus COMPLETED is insufficient to prove correctness.

## 19. Metrics to monitor in production

When output can miss data, dashboards and alerts should expose:

- Input count per batch.
- Read count, write count, filter count.
- Read skip, process skip, and write skip.
- Total skip count and skip rate.
- Stored reject record count.
- Replayed items and remaining rejected items.
- Reconciliation result.
- Batch publication status.
- Top exception types and error sources.

Set alerts when skip count exceeds 0 on a batch requiring 100% completeness, when skip rate exceeds a business threshold, when skips occur without matching reject records, when accepted + filtered + rejected do not match input scope per defined rules, or when a batch is marked READY despite failed reconciliation.

Logs should contain batch ID, source ID, stage, and error code for tracing. Do not log full sensitive payloads. Metrics should use labels with controlled cardinality; do not put individual order IDs into metric labels.

## 20. Common design mistakes

**Assuming COMPLETED means every record was written.** A step can complete with skips. Check skip counts and reconciliation.

**Skipping database or API errors.** Infrastructure failures can drop massive amounts of output. Use bounded retry or fail the step when dependencies are unavailable.

**Not storing skipped items.** Incrementing a counter alone is insufficient to fix or replay records. Record source ID, source location, and cause.

**Confusing filter with skip.** Filtering is intentional exclusion via null; skip is bypassing due to an exception per policy. Track both separately.

**Setting skipLimit too high.** The job can drop a large percentage of data and still complete. Set limits by criticality and add ratio checks.

**Publishing output immediately after import.** Downstream consumers may ingest incomplete data prior to reconciliation. Use staging and a post-check publish step.

**No replay workflow.** Skipped records usually do not reappear automatically on restart. Maintain a reject store and design a separate replay batch.

**Executing non-transactional side effects in the writer.** Rollback does not undo APIs/messages/files. Use an outbox, idempotency, and reconciliation.

**Checking only BatchStatus in tests.** Verify outputs, reject stores, skip counters, and completeness.

## 21. Decision workflow for allowing skip

Before configuring skip, answer:

1. Can a failing item be handled independently without affecting the correctness of other items?
2. Does the business allow the output to omit that item?
3. If allowed, who must be notified and where must reject data be persisted?
4. Can the item be re-identified from source ID, line number, or event ID?
5. What are the maximum skip limit and skip rate?
6. Is approval required before publishing output?
7. Is retry more suitable than skip because the error may be transient?
8. Does the writer have non-transactional side effects requiring idempotency?
9. Can accepted, filtered, and rejected counts be reconciled before marking the batch complete?
10. Is there a replay workflow once data is corrected?

If output must be 100% complete, disallow skipping errors that drop required records; let the step fail and fix the data before rerunning. If business rules accept partial success, skip must be paired with reject tracking, reconciliation, and output states that clearly reflect incompleteness.

## Conclusion

Skip allows Spring Batch to keep processing when certain items hit skippable errors, yet those very items will not appear in the step's successful output. Consequently, a job can finish with BatchStatus COMPLETED while its output still lacks data. This is a business risk that must be controlled through clear exception classification, skip limits, and completeness rules.

When allowing skip, record each item via SkipListener or a reject store, distinguish read/process/write skips from filtering, reconcile accepted/filtered/rejected counts, and publish output only after completeness checks pass. For data requiring full completeness, fail fast rather than dropping records. Where partial success is acceptable, maintain reject reports and a replay workflow. Tests must verify actual data rather than job status alone, avoiding a batch that succeeds while silently dropping output.
