# Bounding skip limits to avoid masking mass failures

Spring Batch allows a Step to skip a number of failing items to continue processing the remaining data. This mechanism is useful when a source contains a few malformed records or some items violate business rules that can be isolated. However, if skip is configured too broadly or the limit is set too high, a systemic failure or widespread data corruption can be mistaken for many isolated errors, and the Job runs through nearly all data in an unreliable state.

Skip limits act as a guardrail so the Step stops when the number of allowed skips crosses a threshold. To avoid masking mass failures, classify exceptions clearly, set thresholds based on data scale, monitor error rates, and test scenarios where a small initial error turns into a widespread failure.

## 1. What does skip mean in Spring Batch?

In a chunk-oriented Step, an item may fail during reading, processing, or writing. If the Step is configured as fault-tolerant and the exception is classified as skippable, Spring Batch can bypass that item and move on to the next item.

Three stages can produce skips:

- **Read skip:** the reader fails while fetching an item, such as an unparseable file line.
- **Process skip:** the reader reads the item, but the processor throws an exception due to invalid data.
- **Write skip:** the writer fails to write one or more items in the chunk, and the framework isolates the failing item to skip per configuration.

Skip does not mean every exception can be ignored. The Step must explicitly configure which error types are skippable and bound the count. Unclassified exceptions or errors exceeding the limit fail the Step.

## 2. skipLimit bounds the total number of skipped errors

With skipLimit(n), the Step is permitted to skip at most n errors under the skip policy. When a subsequent skippable error pushes the skip count past the limit, the Step fails instead of continuing to skip.

For example, skipLimit(10) permits at most 10 skips. The 11th skippable error fails the Step. This limit applies to the Step's total skips across read, process, and write stages; it is not 10 errors per stage or per chunk.

~~~text
skipLimit = 5

Read skips:     2
Process skips:  2
Write skips:    1
                -
Total skips:    5  -> still within limit

Next skippable error
Total skips:    6  -> limit exceeded, Step FAILED
~~~

This is critical when sizing thresholds. Setting skipLimit(10) does not mean the reader gets 10 skips, the processor gets 10 more, and the writer gets 10 more. All three draw from a single Step skip budget.

Absolute limits prevent a Job from skipping infinitely. However, the same number may suit a 1,000-line file while being too low for a 10-million-line file, or too high for a Job processing only a few dozen items. Choose thresholds based on scale and business error tolerance.

## 3. Selective skip configuration

Example of an order-import Step allowing file parse errors and business validation errors to be skipped, while refusing to skip database connection failures:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, Order> processor,
        ItemWriter<Order> writer,
        OrderSkipAuditListener skipAuditListener) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .skip(FlatFileParseException.class)
            .skip(InvalidOrderException.class)
            .noSkip(DataAccessResourceFailureException.class)
            .skipLimit(50)
            .listener(skipAuditListener)
            .build();
}
~~~

In this example:

- FlatFileParseException can represent a single malformed input line.
- InvalidOrderException represents a validation error that business rules permit isolating.
- DataAccessResourceFailureException represents a database access outage that must stop the Step.
- Total allowed skips are 50 across the entire Step.

Exceptions in the example are illustrative; use the actual exception types thrown by your reader, processor, and writer. Set noSkip for errors that must halt processing, such as database unavailability, configuration errors, missing required resources, or system authentication failures.

Avoid using skip(Exception.class) or skip(Throwable.class) for a normal Job. Overly broad classification can treat programming bugs, infrastructure failures, or critical data corruption as bad records safe to discard.

## 4. Distinguishing data errors from system errors

A skip limit is only useful if exceptions are classified accurately. Determine which errors belong to an individual item and which indicate the entire process cannot continue safely.

| Error category | Example | Usually appropriate handling |
|---|---|---|
| Malformed data | A CSV line missing a required column | Can skip and record the bad line |
| Isolated business-rule violation | Order has an unsupported status | Can skip if business rules permit |
| Missing reference data | Customer ID on an order is invalid | Decide per business rules |
| Database unreachable | Connection refused, database unavailable | Bounded retry or fail Step |
| Lost target system permissions | Expired credentials or revoked permission | Fail fast and fix configuration/permissions |
| Programming bug | NullPointerException due to processor bug | Usually must fail to fix code |
| Input file missing | Misconfigured path or file not yet delivered | Fail Step, do not treat as a bad line |

A file with a few malformed lines is completely different from an entire file using the wrong delimiter or schema. The latter can make nearly every line fail parsing; raising skipLimit so the Job continues only masks an incompatible data source.

Similarly, if the writer cannot connect to the database, individual items are not bad data. Skipping mass write errors leaves the output severely incomplete.

## 5. Do not use skip to replace retry

Retry and skip solve two different problems:

- **Retry** re-attempts an operation likely to succeed later, typically due to transient errors such as timeouts or deadlocks.
- **Skip** bypasses an item that business rules allow excluding, typically due to invalid data or errors unfixable by trying again.

Example configuring retry for deadlocks and skip for validation errors:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(DeadlockLoserDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skipLimit(50)
        .build();
~~~

This is an illustrative configuration using Spring Batch 5's API; exact exceptions depend on Spring and database versions. If a transient error persists after retry attempts, the Step can skip only if the final exception is also classified as skippable and skip budget remains. Otherwise, the Step fails.

Do not skip mass timeouts or deadlocks just so the Job reports completion. If the database is overloaded, bounded retry and stopping the Job usually protect data better.

## 6. Skip is not the same as filter

A processor can return null to exclude an item from the write pipeline without throwing an exception. That is filtering, not skipping.

~~~java
@Bean
ItemProcessor<Order, Order> activeOrderProcessor() {
    return order -> {
        if (order.isCancelled()) {
            return null;
        }

        return order;
    };
}
~~~

In this example, cancelled orders are filtered under business rules. The item does not reach the writer and is reflected in the Step's filter count. It does not consume skipLimit.

Conversely, if the processor throws InvalidOrderException and that exception is configured as skippable, the item counts toward the skip count.

| Behavior | Exception thrown? | Increments skip count? | Meaning |
|---|---|---|---|
| Processor returns null | No | No | Intentional filter |
| Processor throws skippable exception | Yes | Yes | Skip failing item |
| Reader returns null | No | No | End of data |
| Non-skippable exception | Yes | Not skipped | Step fails |

Do not use exceptions to represent normal filter conditions. Conversely, do not return null on parse or system errors, because the framework treats that as filter or EOF depending on stage and may finish without reporting errors.

## 7. SkipLimitExceededException and Step outcome

When the skip count exceeds the limit, Spring Batch throws SkipLimitExceededException while evaluating the skip policy. The Step stops skipping items past the threshold and typically ends in the FAILED status.

Example with a limit of 20:

~~~text
Items 1..100:
  8 read skips
  5 process skips
  7 write skips
  ----------------
  20 skips: still within limit

Next item hits skippable error:
  skip count would exceed 20
  -> SkipLimitExceededException
  -> Step FAILED
~~~

Do not catch SkipLimitExceededException inside the reader, processor, or writer and continue processing. It is the Step's protective circuit breaker; swallowing it defeats the limit.

If operations need a clearer failure reason, you can enrich ExitStatus or audit inside a listener while preserving BatchStatus FAILED. Do not switch the status to COMPLETED merely because the error list was recorded.

## 8. Monitoring skip counts per stage

StepExecution stores separate counters for read, process, and write skips. After the Step finishes, query these values to see which stage concentrates errors.

~~~java
long readSkips = stepExecution.getReadSkipCount();
long processSkips = stepExecution.getProcessSkipCount();
long writeSkips = stepExecution.getWriteSkipCount();

long totalSkips = readSkips + processSkips + writeSkips;
~~~

Counters assist diagnosis:

- Sharp rise in read skips: check file format, encoding, delimiter, or input source.
- Sharp rise in process skips: check business data, mapping, and validation.
- Sharp rise in write skips: check constraints, schema, write permissions, and target data uniqueness.

Emit these counters into metrics and audits to alert when one stage exceeds normal levels. Do not monitor only total skips because a total does not show where errors occur.

## 9. Recording skipped items with SkipListener

SkipListener lets you record skip events by stage:

- onSkipInRead(Throwable): skippable read error; usually no valid item is available to supply.
- onSkipInProcess(item, Throwable): item was read, but processing failed.
- onSkipInWrite(item, Throwable): item failed during writing.

~~~java
public class OrderSkipAuditListener
        implements SkipListener<Order, Order> {

    private final SkipAuditService auditService;

    public OrderSkipAuditListener(SkipAuditService auditService) {
        this.auditService = auditService;
    }

    @Override
    public void onSkipInRead(Throwable exception) {
        auditService.recordReadFailure(
                exception.getClass().getSimpleName());
    }

    @Override
    public void onSkipInProcess(
            Order item,
            Throwable exception) {
        auditService.recordItemFailure(
                item.getId(),
                "PROCESS",
                exception.getClass().getSimpleName());
    }

    @Override
    public void onSkipInWrite(
            Order item,
            Throwable exception) {
        auditService.recordItemFailure(
                item.getId(),
                "WRITE",
                exception.getClass().getSimpleName());
    }
}
~~~

Audits should store JobExecution ID, StepExecution ID, business key, failure stage, and normalized exception type. Avoid storing whole items or raw exception messages if they might contain personal data, SQL parameters, or secrets.

SkipListener shows which items were bypassed, but it does not replace skipLimit. The listener records events; the skip policy decides whether an error is permitted to be skipped and whether the limit has been exceeded.

## 10. Using SkipPolicy for complex rules

When skip, noSkip, and skipLimit cannot express the rule sufficiently, use a custom SkipPolicy.

The policy receives the exception and current skip count, then decides whether skipping is permitted. If disallowed, the policy returns false or throws SkipLimitExceededException by design. Pay attention to the Spring Batch version contract: the framework may invoke the policy with a special skipCount value when merely probing whether an exception is skippable.

Illustrative example of a policy allowing only parse and validation errors within an absolute limit:

~~~java
public class OrderSkipPolicy implements SkipPolicy {

    private final long maxSkips;

    public OrderSkipPolicy(long maxSkips) {
        this.maxSkips = maxSkips;
    }

    @Override
    public boolean shouldSkip(Throwable exception, long skipCount)
            throws SkipLimitExceededException {

        boolean skippable =
                exception instanceof FlatFileParseException
                || exception instanceof InvalidOrderException;

        if (!skippable) {
            return false;
        }

        // Some skip-capability checks pass skipCount = -1.
        if (skipCount < 0) {
            return true;
        }

        if (skipCount >= maxSkips) {
            throw new SkipLimitExceededException(
                    "Order skip limit exceeded", exception);
        }

        return true;
    }
}
~~~

Registering the policy:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skipPolicy(new OrderSkipPolicy(50))
        .build();
~~~

Policy examples must be adapted and tested against your Spring Batch API version. Do not arbitrarily mix skip, noSkip, skipLimit, and skipPolicy; when using a custom policy, let that policy express the full classification and limit logic to avoid overlapping rules.

## 11. skipLimit is an absolute threshold, not a percentage

skipLimit(50) caps the absolute skip count. It does not mean skipping 50 percent, 5 percent, or another fraction of the data.

Example:

| Total items | Skips | Error rate |
|---:|---:|---:|
| 100 | 10 | 10% |
| 10,000 | 10 | 0.1% |
| 10,000 | 100 | 1% |
| 1,000,000 | 100 | 0.01% |

The same 100 skips can be a severe failure rate for a small Job while negligible for a huge Job. Therefore, choose absolute thresholds based on typical volume and acceptable business error levels.

If a ratio-based threshold is required, clearly define the denominator as items read, items processed, or expected total items. These numbers can differ due to EOF, filtering, retries, and skips across stages.

You can use listeners/metrics to compute the ratio after the Step and alert or flag results for review. To stop early when the error rate crosses a threshold, design a policy tracking state via StepExecution or a dedicated control step; do not assume skipLimit natively understands percentages. Ratio state must be handled carefully across rollbacks, retries, partitioning, and restarts so item counts are not miscalculated.

## 12. Detecting mass failures early

An absolute skipLimit is the first line of defense. To detect mass failures, combine multiple signals:

- Absolute skip count across the Step.
- Skip rate relative to items read or processed.
- Consecutive skips within a window of records.
- Error rates broken down by source, tenant, or record type.
- Sudden shifts compared to historical runs.
- Errors concentrated in a single stage: read, process, or write.
- System errors such as database timeouts, authentication failures, or resource exhaustion.

For example, if the first 20 lines have 2 parse errors, it may be within tolerance. If 500 consecutive lines fail parsing, the file format or source schema likely changed. Error rates and consecutive error streaks detect this situation earlier than waiting for a high absolute limit.

You can add a pre-validation step to verify headers, encoding, schema, or checksums before importing the entire file. If source structure is incompatible, the Job should stop before generating numerous skip records.

## 13. Designing thresholds by scale and risk level

No single skipLimit suits every Job. Base your choice on real data and the consequences of dropping items.

Illustrative policy examples:

| Job | Expected scale | Suggested starting skip limit for testing |
|---|---:|---:|
| Small file import | 1,000 lines | 5 |
| Daily data import | 100,000 lines | 100 |
| Non-critical log processing | 5,000,000 lines | Based on acceptable rate and data loss tolerance |
| Payments or financial reconciliation | Varies by batch | Very low or disallow skips on critical errors |

These numbers are only illustrative starting points, not Spring Batch defaults or universal recommendations. For financial, medical, or reconcilable data, a single skipped item can create major discrepancies; policy may require failing immediately on any critical error type.

When volume fluctuates daily, monitor both absolute counts and rates. A high threshold sized for peak days can conceal serious failures on low-volume days.

## 14. Handling write errors and the risk of overly broad skips

Skip during the write stage requires special care. The writer receives an entire chunk; a write error can roll back the chunk transaction. Spring Batch may need to pinpoint which item failed through fault-tolerant handling, so the writer can be re-invoked while classifying the error.

If the database loses connectivity, every item in the chunk can fail. Configuring skip on too general an exception can cause the Step to skip item after item rather than stopping immediately.

Recommendations:

- Distinguish a single-record constraint violation from database connection/resource errors.
- Only skip write errors attributable to a specific item and permitted by business rules.
- Retry transient errors such as deadlocks or timeouts when the operation can be safely repeated.
- Fail fast when the database is unavailable, credentials are wrong, or schema is incompatible.
- Use unique keys or upserts so the writer is safe under retry/restart.
- Record audits for every write-skipped item and reconcile counts post-Job.

Do not catch exceptions inside the writer and silently ignore them. When the framework does not see the exception, skip policy, counters, and SkipListener cannot reflect the errors accurately.

## 15. Skip in a partitioned Step

In partitioning, each worker StepExecution has its own counters and lifecycle. Understand that skip limits apply to each worker's StepExecution scope; do not assume a single number automatically caps total errors across the entire manager Step as business rules might expect.

For example, if 8 workers are each allowed to skip up to 20 items, total skips across the Job can exceed 20. If business rules require a batch-wide total limit, you need cross-partition aggregation control or manager-level verification after workers complete.

Principles:

- Set per-worker skipLimit based on partition size.
- Aggregate skip counts across all workers.
- Check error rates per partition to spot an anomalous data slice.
- If a global limit is required, use a safe coordination mechanism rather than static variables or mutable Job context written concurrently by workers.
- Ensure retry/restart does not double-count audits or metrics.

One partition with a high error rate can be hidden if you only inspect the Job total. Dashboards should show both totals and per-partition figures.

## 16. Observing and alerting on abnormal skip spikes

You can use StepExecution counters or listeners to emit metrics:

~~~java
public class SkipMetricsListener implements StepExecutionListener {

    private final MeterRegistry registry;

    public SkipMetricsListener(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public ExitStatus afterStep(StepExecution execution) {
        String job = execution.getJobExecution()
                .getJobInstance().getJobName();
        String step = execution.getStepName();

        registry.counter(
                "batch.step.skip.read",
                "job", job,
                "step", step)
                .increment(execution.getReadSkipCount());

        registry.counter(
                "batch.step.skip.process",
                "job", job,
                "step", step)
                .increment(execution.getProcessSkipCount());

        registry.counter(
                "batch.step.skip.write",
                "job", job,
                "step", step)
                .increment(execution.getWriteSkipCount());

        return execution.getExitStatus();
    }
}
~~~

Set alerts when total skips exceed an operational threshold, skip rate rises abnormally, or write skips appear in a Job that should tolerate no write errors.

Do not put Order ID, Customer ID, JobExecution ID, or file path into metric tags because cardinality can explode. Put detailed identifiers into audit logs with appropriate access control.

If using a post-Step metric listener, alerts fire after the Step completes. To detect issues early while processing, update metrics in an item/skip listener or track progress per chunk, while avoiding excessive overhead.

## 17. Testing skip limits

Skip policy must be tested for both limits and exception types.

| Scenario | Expected outcome |
|---|---|
| No errors | Step completes, skip count equals 0 |
| Fewer skippable errors than limit | Step continues, failing items are recorded |
| Skips equal exact limit | Step can still complete |
| One more skippable error past limit | Step fails due to exceeding skip limit |
| Non-skippable exception | Step fails immediately per policy |
| Transient error with retry | Retried within limit before deciding final outcome |
| Processor returns null | Increments filter count, does not increment skip count |
| Read error | Increments read skip count if skippable |
| Process error | Increments process skip count if skippable |
| Write error | Increments write skip count if skippable |
| Partitioning | Limit and skip totals are evaluated at the right scope |
| Restart | Counters and audits reflect execution accurately without duplicating side effects |

A useful integration test builds a file with some valid lines, a few bad lines, and a section of mass schema-invalid lines. Verify the Job stops when hitting the threshold, previously committed items remain intact, failing items are recorded in audit, and no remaining portion of data is silently treated as processed.

## 18. Common configuration mistakes

**Setting skipLimit too high.** The Job can complete even when most data goes unprocessed. Pick thresholds based on volume and business impact.

**Skipping Exception.class.** Can mask programming bugs or infrastructure failures. Only skip specific exceptions.

**Using skip instead of retry.** Transient timeouts or deadlocks usually need bounded retry; skipping causes missing data.

**Watching only total skip count.** You will not know whether errors occur in read, process, or write. Track each counter.

**Confusing filter with skip.** Returning null from a processor does not consume skipLimit.

**Not auditing skipped items.** The Job may complete with no list of records requiring fixing or reprocessing.

**Treating skipLimit as a percentage.** It is an absolute count limit on the Step. Rates must be calculated separately.

**Ignoring partition scope.** Multiple workers can accumulate skips past the desired business limit if limits are only set per worker.

**Catching and swallowing exceptions.** The framework cannot apply the skip policy or update counters accurately.

## 19. Workflow for setting safe skip limits

When designing a Step with skip, follow this order:

1. Identify which data errors can genuinely be bypassed under business rules.
2. Separate system errors, configuration errors, and programming bugs that must stop the Step.
3. Configure skip for specific exceptions; use noSkip when critical errors must be excluded.
4. Set an absolute skipLimit based on batch scale and risk level.
5. If volume varies, monitor both skip count and skip ratio.
6. Use retry for recoverable transient errors with explicit retry limits.
7. Audit skipped items via SkipListener and protect side effects from duplication.
8. Monitor read/process/write skips separately.
9. With partitioning, clearly define per-worker limits and batch-wide limits.
10. Test mass failures, limit exceedance, retries, restarts, and committed data.

Skip lets a Job continue when isolated failing items can be safely bypassed. skipLimit sets a guardrail so errors cannot grow unchecked; exception classification prevents infrastructure outages from being treated as bad data; metrics and audits reveal abnormal trends. Combining these layers allows the Job to handle imperfect data while stopping promptly when the source or system suffers widespread failure.

