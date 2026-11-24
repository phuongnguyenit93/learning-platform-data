# Status When Skips Still Complete in Spring Batch

In Spring Batch, a step can skip some failing items and still finish successfully. If the exception is covered by the skip policy, the total number of skipped items does not exceed the limit, and remaining work finishes, the step typically has `BatchStatus.COMPLETED`. The job can also end `COMPLETED` even though `StepExecution` records read skips, process skips, or write skips.

This is intentional behavior: skipping allows a batch to continue processing valid data when individual records cannot be processed. However, `COMPLETED` status does not mean every item was processed successfully. To evaluate result quality, you must inspect status, exit status, and skip counters together.

## 1. Why Can a Step with Skips Still Be COMPLETED?

Skip is a preconfigured error-handling branch. When an item throws an exception and that exception is skippable, Spring Batch excludes that item from the processing stream and continues with the remaining items.

For example, a file has 1,000 lines. Two invalid lines are skipped, and the remaining 998 lines are processed and written successfully. If the skip limit allows at least two errors, no other critical error occurs, and the flow finishes normally, the step can end with:

```text
BatchStatus = COMPLETED
ExitStatus  = COMPLETED
readSkipCount = 2
processSkipCount = 0
writeSkipCount = 0
skipCount = 2
```

Skip count shows that items were skipped; `BatchStatus.COMPLETED` shows the step completed under the configured policy. These two facts do not contradict each other.

Spring Batch does not automatically treat every skip as a failure. The application itself defines which exception types may be skipped and the maximum number of skips. When those conditions are met, continuing and completing the step is a valid outcome.

## 2. Configuring a Skippable Step

To allow a step to skip items, enable fault tolerance and declare the exceptions and skip limit:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, OrderEntity> processor,
        ItemWriter<OrderEntity> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, OrderEntity>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skip(FlatFileParseException.class)
        .skipLimit(20)
        .build();
}
```

With the configuration above:

- `InvalidOrderException` and `FlatFileParseException` are treated as skippable error types.
- `skipLimit(20)` caps the total number of skips in the step.
- If the skip count does not exceed the limit and no other error occurs, the step can complete normally.
- Exceptions outside the policy or exceeding the skip limit can cause the step to fail.

If no skip limit is configured, the default is 0. Therefore, merely declaring exception classes without setting a positive limit does not mean the step will automatically accept skips.

You should not make every exception skippable just so the job ends with a success status. Connection errors, authentication errors, configuration errors, or processor bugs should normally fail the step rather than be skipped.

## 3. BatchStatus and ExitStatus Are Different Concepts

Spring Batch stores both `BatchStatus` and `ExitStatus` for job/step executions. They are related but not synonymous.

| Property | Meaning | Example |
| --- | --- | --- |
| `BatchStatus` | Execution lifecycle status managed by Spring Batch. | `STARTED`, `COMPLETED`, `FAILED`, `STOPPED`. |
| `ExitStatus` | Outcome code used to describe results and drive flow routing. | `COMPLETED`, `FAILED`, `NOOP`, or a custom code. |

When a step skips items within the limit and ends normally, the default state is usually:

```text
StepExecution:
  status     = COMPLETED
  exitStatus = COMPLETED
  skipCount  = 2
```

`skipCount` is an additional metric. It does not automatically change `BatchStatus` to `FAILED`, nor does it automatically change `ExitStatus` to a code like `COMPLETED WITH SKIPS`.

The application can customize `ExitStatus` if the flow needs to distinguish a clean completion from a completion with skips. Customizing the exit code does not necessarily change `BatchStatus`.

## 4. A Job Can Be COMPLETED Even If a Step Had Skips

A job is typically orchestrated across one or more steps. If a step finishes with a positive skip count still within the limit, the flow can proceed to the next step. If the other required steps also complete and no transition fails or stops the job, the job can finish with `BatchStatus.COMPLETED`.

Example:

```text
ImportStep
  BatchStatus = COMPLETED
  ExitStatus  = COMPLETED
  skipCount   = 2
        |
        v
ReportStep
  BatchStatus = COMPLETED
  ExitStatus  = COMPLETED
        |
        v
JobExecution
  BatchStatus = COMPLETED
  ExitStatus  = COMPLETED
```

Job status reflects the overall orchestration outcome. It is not an assertion that every source record was written successfully. To know whether data was skipped, you must check the skip counters of each `StepExecution`.

If a job has multiple steps, an earlier step having skips does not necessarily prevent subsequent steps from running. That depends on the flow and the exit status returned by the step.

## 5. When Does Skipping Still Lead to FAILED?

Skipping is only accepted when the exception matches the skip policy and the limit has not been exceeded. Several situations still cause the step to fail:

- The exception is not of a skippable type.
- Total skips exceed `skipLimit`.
- The reader or writer cannot safely continue after the error.
- A listener or operation persisting skip details throws an unhandled error.
- Another infrastructure error or programming bug occurs in the same step.
- The step is stopped or marked failed by other logic.

For example, a step allows at most 10 skips, but 11 items cause errors:

```text
Skip 1..10  -> accepted
Skip 11     -> exceeds skipLimit
Step        -> FAILED
Job         -> usually FAILED if flow does not handle failure branch
```

When the limit is exceeded, Spring Batch can throw `SkipLimitExceededException`. `noRollback(...)` does not increase the skip limit and does not turn an over-limit exception into a valid skip.

## 6. Skip Limit Is the Sum of Read, Process, and Write

The standard skip limit applies across all three phases—read, process, and write—combined. It is not three separate limits.

Example `skipLimit(5)`:

| Phase | Skipped Items |
| --- | ---: |
| Read | 2 |
| Process | 2 |
| Write | 1 |
| **Total** | **5** |

If one more item needs to be skipped, the total will exceed the limit and the step will fail. To track causes, examine individual counters rather than looking only at the total skip count.

Common properties on `StepExecution`:

- `getReadSkipCount()`
- `getProcessSkipCount()`
- `getWriteSkipCount()`
- `getSkipCount()`

In addition, `readCount`, `writeCount`, and `filterCount` help understand data volume across phases. `filterCount` is the number of items intentionally excluded by the processor returning `null`; it is not a skip and does not increment skip counts.

## 7. Skip vs. Filter and Retry

Not every item absent from output is a skip:

| Mechanism | What happens? | Effect on skip count |
| --- | --- | --- |
| Skip | Exception is accepted by policy and the item is skipped. | Increments the corresponding skip counter. |
| Filter | Processor returns `null` per business rule. | Does not increment skip count; increments `filterCount`. |
| Retry then succeed | Failing operation is retried and eventually succeeds. | Does not count that item as a skip. |
| Fail | Exception is not retried/skipped or limit is exceeded. | Step fails. |

For example, cancelled orders can be filtered because they need no processing. Orders missing required fields can throw `InvalidOrderException` and be skipped. Temporary database errors can be retried. These three cases should be tracked separately because they carry different business meanings.

## 8. Reading Status and Skip Counts from StepExecution

After a step runs, you can read status and counters from `StepExecution`:

```java
public class StepResultLogger implements StepExecutionListener {

    private static final Logger log =
        LoggerFactory.getLogger(StepResultLogger.class);

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        log.info(
            "step={}, batchStatus={}, exitStatus={}, read={}, written={}, " +
            "filtered={}, readSkips={}, processSkips={}, writeSkips={}, totalSkips={}",
            stepExecution.getStepName(),
            stepExecution.getStatus(),
            stepExecution.getExitStatus().getExitCode(),
            stepExecution.getReadCount(),
            stepExecution.getWriteCount(),
            stepExecution.getFilterCount(),
            stepExecution.getReadSkipCount(),
            stepExecution.getProcessSkipCount(),
            stepExecution.getWriteSkipCount(),
            stepExecution.getSkipCount()
        );
        return null;
    }
}
```

The listener can be registered directly on the step:

```java
.listener(new StepResultLogger())
```

Do not log only `BatchStatus`. A log line containing `status`, `exitStatus`, and skip counters helps operators recognize that the step completed while skipping items.

For jobs with multiple steps or partitions, log `jobExecutionId`, `stepExecutionId`, and partition name if present. This makes it possible to pinpoint the exact execution where skips occurred.

## 9. Querying Results After Job Completion

`JobExplorer` can be used to read executions saved in `JobRepository`. This is useful for operational screens or reports after a job finishes:

```java
JobExecution execution = jobExplorer.getJobExecution(jobExecutionId);

if (execution != null) {
    log.info(
        "job={}, status={}, exitStatus={}",
        execution.getJobInstance().getJobName(),
        execution.getStatus(),
        execution.getExitStatus().getExitCode()
    );

    for (StepExecution step : execution.getStepExecutions()) {
        log.info(
            "step={}, status={}, exitStatus={}, skips={}",
            step.getStepName(),
            step.getStatus(),
            step.getExitStatus().getExitCode(),
            step.getSkipCount()
        );
    }
}
```

In production, store `JobExecutionId` alongside batch ID or business date to look up the exact run. Avoid querying only the latest execution by job name if multiple instances run concurrently.

If a step is partitioned, the manager step and worker steps have separate executions. The job's total skips should be aggregated from the appropriate worker executions; do not assume a single number on the manager automatically reflects every partition.

## 10. Displaying the “COMPLETED WITH SKIPS” Status

The default `COMPLETED` status may not give operations enough information. The application can set a custom `ExitStatus` when a step completes with skipped items.

Example:

```java
public class SkipExitStatusListener implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getStatus() == BatchStatus.COMPLETED
                && stepExecution.getSkipCount() > 0) {
            return new ExitStatus("COMPLETED WITH SKIPS");
        }
        return null;
    }
}
```

Register the listener:

```java
return new StepBuilder("importOrdersStep", jobRepository)
    .<Order, OrderEntity>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .skip(InvalidOrderException.class)
    .skipLimit(20)
    .listener(new SkipExitStatusListener())
    .build();
```

After the listener runs, the outcome can be represented as:

```text
BatchStatus = COMPLETED
ExitStatus  = COMPLETED WITH SKIPS
skipCount   = 2
```

This is a custom `ExitStatus` code defined by the application. It is not a new `BatchStatus` value and does not mean the job FAILED. Use a custom exit code when you need to route the flow or display warnings while still treating the step as completed per policy.

## 11. Flow Routing Based on ExitStatus

A job flow commonly uses a step's `ExitStatus` to decide the next step. When a custom listener returns `COMPLETED WITH SKIPS`, the job can branch to a step that reviews invalid data:

```java
@Bean
Job importJob(
        JobRepository jobRepository,
        Step importOrdersStep,
        Step reviewRejectedOrdersStep,
        Step publishReportStep) {

    return new JobBuilder("importJob", jobRepository)
        .start(importOrdersStep)
            .on("COMPLETED WITH SKIPS").to(reviewRejectedOrdersStep)
        .from(importOrdersStep)
            .on("COMPLETED").to(publishReportStep)
        .from(reviewRejectedOrdersStep)
            .on("*").to(publishReportStep)
        .end()
        .build();
}
```

In this flow:

- A step completing with zero skips returns `COMPLETED` and goes straight to `publishReportStep`.
- A step completing with skips returns `COMPLETED WITH SKIPS` and routes through `reviewRejectedOrdersStep`.
- Both branches can still finish the job successfully if subsequent steps succeed.

Transition order and patterns must be designed clearly. `on(...)` matches exit code, not `BatchStatus`. If you want to stop or mark the job failed, configure the corresponding transition/flow; simply changing the exit code to `COMPLETED WITH SKIPS` does not automatically fail the job.

## 12. Using JobExecutionDecider to Decide Based on Skip Count

If the routing condition is more complex than an exit code, you can use a `JobExecutionDecider`. The decider receives `JobExecution` and the current `StepExecution`, then returns `FlowExecutionStatus`.

Example:

```java
public class SkipCountDecider implements JobExecutionDecider {

    @Override
    public FlowExecutionStatus decide(
            JobExecution jobExecution,
            StepExecution stepExecution) {

        if (stepExecution != null && stepExecution.getSkipCount() > 0) {
            return new FlowExecutionStatus("HAS_SKIPS");
        }

        return new FlowExecutionStatus("NO_SKIPS");
    }
}
```

The flow can use the decider's result to pick a branch:

```java
return new JobBuilder("importJob", jobRepository)
    .start(importOrdersStep)
    .next(skipCountDecider)
        .on("HAS_SKIPS").to(reviewRejectedOrdersStep)
    .from(skipCountDecider)
        .on("NO_SKIPS").to(publishReportStep)
    .from(reviewRejectedOrdersStep)
        .on("*").to(publishReportStep)
    .end()
    .build();
```

`FlowExecutionStatus` is a flow routing status. It is also not a `BatchStatus`. A decider should read already updated execution data and avoid performing business side effects while choosing a branch.

## 13. Using SkipListener to Persist Skipped Item Details

Status and skip count indicate errors occurred, but do not tell you which specific items were skipped. `SkipListener` helps record identifiers and causes in each phase:

```java
public class OrderSkipListener
        implements SkipListener<Order, OrderEntity> {

    private final RejectedOrderRepository repository;

    public OrderSkipListener(RejectedOrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public void onSkipInRead(Throwable t) {
        repository.save(RejectedOrder.fromReadError(t));
    }

    @Override
    public void onSkipInProcess(Order item, Throwable t) {
        repository.save(RejectedOrder.fromOrder(item, t));
    }

    @Override
    public void onSkipInWrite(OrderEntity item, Throwable t) {
        repository.save(RejectedOrder.fromEntity(item, t));
    }
}
```

Read skips have no valid item to pass to the callback; the application must extract source details from the exception if available, such as file name and line number. Process skips receive the input item; write skips receive the output item.

The listener can write errors to a quarantine table within the step's database transaction. If writing to a non-transactional resource, idempotency is required because retries, restarts, or redeliveries can cause duplicate effects. Custom exit status or skip count should not be treated as a substitute for a list of failed records needed for reconciliation.

## 14. Data Quality Reporting When the Job Is COMPLETED

A job can complete successfully in terms of orchestration yet still have unacceptable data quality. Therefore, operational reports should combine:

- `BatchStatus` and `ExitStatus` of the job.
- Status and exit code of each step.
- Read, process, and write skip counts.
- Filter count.
- Number of items read and written.
- Skip rate relative to items inspected.
- Exception categories and skip causes.
- List of failed items in quarantine.

For example, a job might display:

```text
Job: importOrders
Status: COMPLETED
Exit status: COMPLETED WITH SKIPS

Step: importOrdersStep
Read: 1000
Written: 990
Filtered: 5
Read skips: 2
Process skips: 3
Write skips: 0
Total skips: 5
```

Numbers in the example illustrate presentation only; do not infer a fixed formula between read, write, filter, and skip because counts across phases can differ. Reports should pull counters directly from `StepExecution` and persisted business data.

Skip rate should be calculated using a denominator appropriate to the business. For example, process skip rate over successfully read items may differ from read skip rate over total source records. Set alert thresholds based on historical data and quality requirements rather than using one universal threshold for every job.

## 15. Testing When Skips Occur Yet the Step Remains COMPLETED

Integration tests should verify both status and skip counters. For example, a processor throws `InvalidOrderException` for one item, the step allows skipping, and the writer persists the remaining items:

```java
JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);

StepExecution step = execution.getStepExecutions()
    .stream()
    .filter(s -> s.getStepName().equals("importOrdersStep"))
    .findFirst()
    .orElseThrow();

assertThat(step.getStatus()).isEqualTo(BatchStatus.COMPLETED);
assertThat(step.getProcessSkipCount()).isEqualTo(1);
assertThat(step.getSkipCount()).isEqualTo(1);
assertThat(orderRepository.count()).isEqualTo(expectedValidOrders);
```

This test proves two facts simultaneously: the step completed per policy and one item was skipped. If a listener sets a custom exit status, you can add an assertion:

```java
assertThat(step.getExitStatus().getExitCode())
    .isEqualTo("COMPLETED WITH SKIPS");
```

Do not assert only that `JobExecution` is `COMPLETED`. Verify the exact step and exact skip counter, because a multi-step job can finish even if an earlier step had skips.

## 16. Testing Skip Limit Exceeded

Write a dedicated test with more failing items than `skipLimit`. For example, the limit is 2 but the processor throws an exception for three items:

```java
.faultTolerant()
.skip(InvalidOrderException.class)
.skipLimit(2)
```

The expected outcome is that the step fails when the next skip exceeds the limit. Verify:

- `StepExecution.getStatus()` is `FAILED`.
- The failure exception reflects `SkipLimitExceededException` or the corresponding cause per version/framework.
- Previously committed chunks retain their data.
- The current chunk follows rollback behavior for the exception and transaction configuration.
- Job status reflects the final flow branch.

This is an essential test to distinguish “skips accepted and completed” from “skips exceeded threshold and failed”.

## 17. Testing Custom ExitStatus

If the application uses `COMPLETED WITH SKIPS`, verify both status and exit code:

```java
assertThat(stepExecution.getStatus())
    .isEqualTo(BatchStatus.COMPLETED);

assertThat(stepExecution.getExitStatus().getExitCode())
    .isEqualTo("COMPLETED WITH SKIPS");
```

Then verify the flow takes the right branch. With a job containing `reviewRejectedOrdersStep`, assert that this step executes when skip count is positive and is bypassed when there are no skips.

If another listener also modifies `ExitStatus`, test how exit statuses are combined. Avoid multiple listeners overwriting exit codes without a clear convention.

## 18. Common Mistakes When Reading Status

**Seeing COMPLETED and concluding every item succeeded:** status reflects step/job outcome, not item success rate. Inspect skip counters and quarantine data.

**Assuming every skip makes the step FAILED:** skips within policy and below limit allow the step to complete normally.

**Confusing BatchStatus with ExitStatus:** a step can have `BatchStatus.COMPLETED` with a custom `ExitStatus` of `COMPLETED WITH SKIPS`.

**Confusing skip count with filter count:** filters are items intentionally dropped by the processor returning `null`; skips are items bypassed due to exceptions.

**Configuring skip class while forgetting skip limit:** default limit is 0; declaring an exception does not automatically skip failing items.

**Not distinguishing read/process/write skips:** each phase has different counters and error data; read skips usually have no item object.

**Changing ExitStatus expecting BatchStatus to change:** custom exit codes are for flows/monitoring and do not automatically turn an execution into FAILED.

**Not checking downstream flow:** a step with skips can trigger a review branch or continue normally depending on exit status.

**Not saving failed item identifiers:** counters only tell how many; you need `SkipListener` or a quarantine store to know which records were skipped.

## 19. Designing Status and Skips in Production

First, clearly define which error types are skippable and set `skipLimit` based on data quality requirements. Keep infrastructure, configuration, and bug errors outside the skip policy so the step stops when continuing is unsafe.

Next, design how operations wants to view results. If `COMPLETED` paired with skip counters is enough, keep the default exit status and display counters on the dashboard. If the flow needs to distinguish clean steps from steps with skips, use `StepExecutionListener.afterStep()` to return a custom `ExitStatus` such as `COMPLETED WITH SKIPS`, or use `JobExecutionDecider` to choose branches based on skip count.

Persist failed item details with `SkipListener` and a quarantine store when reconciliation is needed. Track read/process/write skips, filter count, and total written items separately. Test within-limit skips, over-limit skips, custom exit status, and downstream transitions.

In Spring Batch, a job with skips can still complete successfully because skipping is part of the fault-tolerance policy. `COMPLETED` indicates the flow finished per configuration; skip counters indicate some items were skipped. By reading both pieces of information and designing appropriate exit status and monitoring, the system can report outcomes honestly while still benefiting from batch continuation.
