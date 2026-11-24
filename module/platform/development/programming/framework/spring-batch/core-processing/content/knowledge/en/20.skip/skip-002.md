# Skip limit

In Spring Batch, a Step can be configured to skip a number of failing items and continue processing the remaining items. `skipLimit` sets the limit on the total number of items allowed to be skipped in a Step. When the skip count exceeds the limit, the Step fails instead of continuing to skip data.

Skip limit balances fault tolerance with data completeness. A few malformed input records may be acceptable in a large import Job, but if thousands of records are skipped, the result may no longer be trustworthy. Therefore, choose the limit based on business rules, data volume, and the acceptable error rate.

## 1. What are skip and skip limit?

In chunk-oriented processing, Spring Batch reads items, processes them via a processor if present, and writes output items using a writer. If an exception occurs, the Step can be configured to retry, skip, or fail.

**Skip** is the decision to bypass an item due to an error classified as skippable. **Skip limit** is the maximum number of skips a Step is allowed to accept during that logical execution.

For example, a Job importing 10,000 customers may allow skipping up to 20 malformed records:

```java
.faultTolerant()
.skip(FlatFileParseException.class)
.skipLimit(20)
```

If 12 lines have parse errors and are skipped, the Step can still complete. If a 21st skip occurs, the limit is exceeded and the Step fails.

Skip limit is not the number of items read, the number of filtered items, or the number of retry attempts. It only counts items that are actually skipped under the skip policy.

## 2. Skip limit applies across all three stages

Spring Batch can skip errors occurring in all three stages of a chunk:

- **Read skip:** the reader cannot read an item, such as an unparseable file line.
- **Process skip:** the processor receives an item but cannot process it, such as data failing a business rule.
- **Write skip:** the writer cannot write an item, such as a record violating a skippable data rule.

`skipLimit` applies to the total number of skips across all three stages, not as a separate limit per stage.

Example Step with `skipLimit(10)`:

| Stage | Items skipped |
|---|---:|
| Read | 3 |
| Process | 4 |
| Write | 3 |
| **Total** | **10** |

The Step has exhausted its limit but can still continue if no further skips occur. If one more item is skipped at any stage, the total becomes 11 and the Step fails.

The corresponding counters are stored in `StepExecution`: `readSkipCount`, `processSkipCount`, and `writeSkipCount`. Total skips can be viewed as the sum of these three counters.

## 3. Default value and limit counting

If no skip limit is configured, the Step allows no skips by default. You can think of the default value as 0: the first time a skippable exception occurs, the limit is exceeded and the Step fails.

With `skipLimit(10)`, Spring Batch allows up to 10 skips. The next skip, the 11th, exceeds the limit.

| Configuration | Maximum accepted skips | Result on one more skip |
|---|---:|---|
| No skip limit configured | 0 | Step fails when a skip occurs |
| `skipLimit(1)` | 1 | 2nd skip causes Step to fail |
| `skipLimit(10)` | 10 | 11th skip causes Step to fail |
| `skipLimit(100)` | 100 | 101st skip causes Step to fail |

The limit applies to the entire Step, accumulating read, process, and write skips. Do not treat `skipLimit(10)` as allowing 10 read errors, plus 10 process errors, plus 10 write errors.

## 4. Configuring skip limit in Spring Batch 5

With Java configuration, use `faultTolerant()`, declare skippable exceptions, and set `skipLimit()`:

```java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> reader,
        ItemProcessor<CustomerInput, Customer> processor,
        ItemWriter<Customer> writer) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<CustomerInput, Customer>chunk(500, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .skip(FlatFileParseException.class)
            .skip(InvalidCustomerException.class)
            .skipLimit(50)
            .build();
}
```

In this example:

- `FlatFileParseException` represents file-line parsing errors.
- `InvalidCustomerException` represents business-level customer data errors.
- `skipLimit(50)` allows at most 50 skipped items in total across read, process, and write.
- Exceptions not classified as skippable can still fail the Step.

Only add exceptions that the business truly permits to be skipped. Do not configure broad skips just to make the Job always run to completion.

## 5. Declaring skippable exception types

`skip(ExceptionType.class)` declares an exception type and its matching subclasses as skippable. Multiple exception types can be declared:

```java
.faultTolerant()
.skip(FlatFileParseException.class)
.skip(InvalidCustomerException.class)
.skip(InvalidAddressException.class)
.skipLimit(100)
```

This example allows skipping file parse errors, customer data errors, and address errors up to a total limit of 100 items.

### Excluding exceptions with `noSkip()`

In some cases, you can declare a broad group of exceptions as skippable and then exclude dangerous ones using `noSkip()`:

```java
.faultTolerant()
.skip(Exception.class)
.noSkip(DeadlockLoserDataAccessException.class)
.noSkip(DataAccessResourceFailureException.class)
.skipLimit(20)
```

The example above only illustrates the declaration syntax. In production, skipping all `Exception` types is usually too broad and easily hides programming or infrastructure errors. Normally, declare the specific business exceptions allowed to be skipped.

When skip and no-skip rules both match due to inheritance, Spring Batch classifies the exception using the most specific type and superclass relationships to decide. Avoid confusing overlapping rules; verify the actual exception types and write tests for edge cases.

## 6. Skip limit vs. retry limit

Skip limit and retry limit often appear together in a fault-tolerant Step, but they govern two different behaviors.

| Criterion | Skip limit | Retry limit |
|---|---|---|
| Purpose | Limits how many items are skipped | Limits how many times a failing operation/item is retried |
| When does it increment? | When an item is actually skipped | When an attempt encounters a retryable exception |
| Final outcome | Item is excluded from the processing pipeline | Item may succeed after retry or ultimately be skipped/fail |
| Example | Record with an invalid date | Transient deadlock or short-lived timeout |

Example configuring both retry and skip:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skipLimit(25)
        .build();
```

In this example, transient data-access errors are retried according to the retry policy; invalid order errors can be skipped up to a limit of 25. Classify exceptions carefully so an error is not retried or skipped unintentionally.

If an exception is both retryable and skippable, Spring Batch can retry first according to the retry policy; if retries fail, the next decision depends on the skip policy and fault-tolerance configuration. Test that exception's behavior instead of relying only on configuration method names.

## 7. Skip limit vs. filter

A processor can return `null` to intentionally exclude an item from output. This is **filtering**, not skipping, because no exception is thrown.

```java
@Bean
ItemProcessor<OrderInput, Order> orderProcessor() {
    return input -> {
        if (input.isCancelled()) {
            return null; // Intentional filter
        }

        return convert(input);
    };
}
```

Filtered items are counted in `filterCount`, do not increment skip count, and do not consume the skip limit.

Conversely, if the processor throws `InvalidOrderException` and that exception is configured as skippable, the item is skipped due to an error. That increments `processSkipCount` and consumes the skip limit.

| Situation | Mechanism | Impact on skip limit |
|---|---|---|
| Processor returns `null` | Filter | None |
| Reader throws skippable exception | Read skip | Yes |
| Processor throws skippable exception | Process skip | Yes |
| Writer throws skippable exception and item is isolated/skipped | Write skip | Yes |
| Exception is retried and succeeds | Retry succeeded | None |
| Exception cannot be retried/skipped | Step fails | Not accepted as a successful skip |

## 8. What happens when the skip limit is exceeded?

When the next skip pushes the total skip count past the limit, Spring Batch throws `SkipLimitExceededException` and the Step fails. The framework does not continue skipping that item.

Example `skipLimit(3)`:

```text
Skip 1 -> accepted
Skip 2 -> accepted
Skip 3 -> accepted
Skip 4 -> limit exceeded
           |
           v
      Step FAILED
```

When a Step fails due to exceeding the limit:

- The Job usually transitions to `FAILED` if the flow has no transition handling that status.
- Previously committed chunks remain intact.
- The current chunk's transaction is handled according to the rollback policy.
- Subsequent items are not processed in that execution.
- StepExecution metadata stores the status and relevant counters for investigation.

Do not treat exceeding the skip limit as an error to ignore automatically. It is a signal that data quality or operating conditions have crossed the acceptable threshold.

## 9. SkipListener and skip limit

`SkipListener` is invoked when an item is actually skipped according to policy. It has three callbacks:

- `onSkipInRead(Throwable t)` when the reader fails and the item is skipped.
- `onSkipInProcess(T item, Throwable t)` when the processor fails to process an item and it is skipped.
- `onSkipInWrite(S item, Throwable t)` when the writer fails to write an item and it is skipped.

Example:

```java
@Component
public class CustomerSkipListener
        implements SkipListener<CustomerInput, Customer> {

    private final SkippedCustomerService skippedCustomerService;

    public CustomerSkipListener(
            SkippedCustomerService skippedCustomerService) {
        this.skippedCustomerService = skippedCustomerService;
    }

    @Override
    public void onSkipInRead(Throwable t) {
        skippedCustomerService.recordReadError(t);
    }

    @Override
    public void onSkipInProcess(CustomerInput item, Throwable t) {
        skippedCustomerService.recordProcessError(item.customerId(), t);
    }

    @Override
    public void onSkipInWrite(Customer item, Throwable t) {
        skippedCustomerService.recordWriteError(item.customerId(), t);
    }
}
```

Register the listener alongside the skip configuration:

```java
return new StepBuilder("importCustomersStep", jobRepository)
        .<CustomerInput, Customer>chunk(500, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(InvalidCustomerException.class)
        .skipLimit(50)
        .listener(customerSkipListener)
        .build();
```

The listener helps store the business key and cause for later reprocessing. However, once the skip limit is exceeded, the next item is not accepted as a valid skip; do not rely on `SkipListener` as if every error had been skipped.

## 10. Tracking skip rate instead of only looking at absolute counts

A fixed skip limit may not fit every data scale. For example, 20 errors out of 100 records is a 20% error rate, whereas 20 errors out of 1,000,000 records is only 0.002%.

Monitor all of the following:

- Total number of skipped items.
- Skips broken down by read, process, and write.
- Total items read or expected item count.
- Skip rate over total items.
- Exception groups and failing data sources.
- Skip trends across runs.

Example:

| Job | Read count | Total skip | Skip rate |
|---|---:|---:|---:|
| Import A | 100 | 20 | 20% |
| Import B | 1,000 | 20 | 2% |
| Import C | 1,000,000 | 20 | 0.002% |

Spring Batch provides count-based skip limits. If business rules require a percentage threshold, you can use a listener or a summary Step to inspect counters and decide the final status. Note that checking the rate at the end of the Step may occur after data has been committed; if you must prevent writing data as soon as the rate exceeds the threshold, design an appropriate policy or per-chunk check.

## 11. Using a custom SkipPolicy

When skip rules cannot be expressed concisely using `.skip()` and `.noSkip()` lists, you can implement `SkipPolicy`.

The interface has the form:

```java
public interface SkipPolicy {
    boolean shouldSkip(Throwable t, long skipCount)
            throws SkipLimitExceededException;
}
```

`shouldSkip()` receives the exception and the current skip count. Return `true` if the exception can be skipped; return `false` if it cannot be skipped. The policy can also throw `SkipLimitExceededException` when the threshold is exceeded.

Example policy with a limit that accepts only specific business errors:

```java
public class CustomerSkipPolicy implements SkipPolicy {

    private final long limit;

    public CustomerSkipPolicy(long limit) {
        this.limit = limit;
    }

    @Override
    public boolean shouldSkip(Throwable t, long skipCount)
            throws SkipLimitExceededException {

        if (t instanceof InvalidCustomerException
                || t instanceof FlatFileParseException) {
            if (skipCount < limit) {
                return true;
            }
            throw new SkipLimitExceededException(
                    "Customer skip limit exceeded", t);
        }

        return false;
    }
}
```

**Note:** How `skipCount` is counted and when the policy is invoked belong to Spring Batch's contract. When writing a custom policy, verify against the exact API version and test limit boundaries, especially the last allowed skip and the subsequent skip.

Register the policy:

```java
.faultTolerant()
.skipPolicy(new CustomerSkipPolicy(50))
```

When using `SkipPolicy`, the policy is responsible for deciding exception types and limits. Avoid declaring overlapping `.skip()`, `.noSkip()`, and custom policy rules in a way that leaves readers unsure which rule makes the final decision.

## 12. Choosing a skip limit according to business requirements

There is no single optimal skip limit for every Job. Consider the following factors:

### Data criticality

For financial, balance, or transaction data, a single skipped item can skew aggregated results. The skip limit should be very low or disallowed, depending on reconciliation processes and dedicated error-handling capabilities.

For reference data or catalog imports, a small rate of invalid records may be acceptable if written to a dead-letter store with a compensating workflow.

### Source size and quality

Stable, pre-validated data sources can use a low limit. External sources with a history of formatting issues may need a more suitable limit, but do not raise the threshold merely so the Job always finishes.

### Reprocessability

If every skipped item is saved with its business key, cause, and source, allowing skips may be safer. If items cannot be recovered or reconstructed, set a strict limit.

### SLO and batch window

If a Job must finish within a time window, allowing a bounded number of errors may be needed so valid items still get processed. However, the output should be flagged as having errors and must not be published as completely clean data.

## 13. Handling a Job when the skip limit is exceeded

When a Step exceeds the skip limit, operational procedures should help identify the root cause and rerun safely:

1. Inspect JobExecution and StepExecution to see which Step failed.
2. Check `readSkipCount`, `processSkipCount`, `writeSkipCount`, and the last exception.
3. Look up dead-letter/audit records to see which items were skipped before the limit was exceeded.
4. Classify whether it is a data error, source error, programming bug, or infrastructure issue.
5. Fix the data or input source, or adjust the policy if business rules genuinely changed.
6. Restart the same JobInstance when the goal is to continue the failed work and the reader supports checkpointing.
7. If a new business run with different data or scope is needed, create appropriate identifying JobParameters.
8. Reconcile committed results and external side effects before rerunning.

Do not manually edit `BATCH_*` metadata tables to raise the skip count or force a Step to `COMPLETED`. Spring Batch uses metadata to control restart; manual alterations can leave execution state inconsistent.

## 14. Restart and skip limit

The skip count is persisted in StepExecution metadata. When a Step fails and is restarted, Spring Batch uses the saved execution state and checkpoint to continue according to the Step's restart mechanism. Previously committed chunks are retained; uncommitted items may be reread or reprocessed depending on the reader and transaction behavior.

Therefore, operations must understand that the skip limit is tied to the Step's execution state and how the framework restores StepExecution. Do not treat a restart as a brand-new Job with skip counters automatically reset to 0. If it must run as a new business unit of work, identify a new JobInstance with appropriate identifying parameters.

Readers supporting `ItemStream` can store checkpoints in StepExecutionContext. However, checkpointing does not make external side effects outside the transaction idempotent. Writers and external services still require deduplication if items can be re-executed.

## 15. Skip limit in the writer and error-isolation behavior

The writer receives a chunk containing multiple items. If a write operation fails, Spring Batch may need to pinpoint the specific failing item to apply skip. Depending on configuration and writer type, the framework may retry writing smaller groups or individual items to isolate the error.

This has several consequences:

- The writer may be invoked multiple times while isolating the failing item.
- Write operations need to participate in a transaction or support safe retry.
- Do not send emails, call transaction-creating APIs, or perform non-idempotent side effects in the writer without protection.
- An exception in the writer does not automatically mean the whole chunk is skipped; the specific item must be identified and the exception must be permitted by policy.

For writers that can write part of a chunk before failing, rollback is usually critical to preserve atomicity. Only use no-rollback for clearly classified exceptions where you are sure there are no partial writes to undo.

## 16. Monitoring and alerting on skip limit

Build dashboards or alerts based on skip counts and skip rates. Useful metrics include:

| Metric | Purpose |
|---|---|
| `readSkipCount` | Monitor source read errors |
| `processSkipCount` | Monitor validation/transformation errors |
| `writeSkipCount` | Monitor target write errors |
| Total skip | Assess skip limit utilization |
| Skip rate | Compare data quality across runs |
| Skip limit exceeded count | Detect Jobs failing due to exceeding the threshold |
| Dead-letter backlog | Track items awaiting reprocessing |

You can alert before hitting the limit, such as when total skips reach 70% or 90% of the threshold. For Jobs with critical data, early warnings help operators investigate before the Step fails.

Do not rely solely on the Job status `COMPLETED`. A Job can complete with a non-zero skip count. The system should publish the number of skipped items and the acceptance policy for results with errors.

## 17. Common mistakes

**Interpreting `skipLimit(10)` as 10 skips per stage:** the limit applies to the total read, process, and write skips of the Step.

**Assuming some errors can be skipped by default:** the default skip limit is 0; you must configure a skip policy and limit.

**Confusing skip limit with retry limit:** retry is the number of retry attempts, while skip limit is the number of skipped items.

**Confusing filter with skip:** returning `null` from a processor increments the filter count and does not consume the skip limit.

**Configuring `skip(Exception.class)` too broadly:** this can bypass infrastructure or programming errors and cause missing data.

**Registering only a SkipListener without declaring skip:** a listener alone does not allow skipping exceptions.

**Raising the skip limit so the Job always succeeds:** the Job may complete, but the output will miss data or violate business rules.

**Not persisting skipped items:** after the Job finishes, it is difficult to investigate or reprocess failing data.

**Assuming exceeding the limit only skips the last item:** when the threshold is exceeded, the Step fails and does not continue skipping normally.

**Not accounting for restart:** verify metadata, checkpoints, and already committed side effects before rerunning.

## Conclusion

`skipLimit` sets the maximum number of items a Step is permitted to skip. This limit is counted across errors in the reader, processor, and writer; it defaults to 0 if unconfigured. With `skipLimit(10)`, at most 10 items are skipped and the 11th skip causes the Step to fail. Declare specific skippable exceptions, use `noSkip()` for errors that must stop execution when truly needed, distinguish skip from retry and filter, and record failing items via `SkipListener` or a dead-letter store. Choose the limit based on data criticality and reprocessability, monitor both counts and skip rates, and test restarts to ensure committed data is not processed twice.
