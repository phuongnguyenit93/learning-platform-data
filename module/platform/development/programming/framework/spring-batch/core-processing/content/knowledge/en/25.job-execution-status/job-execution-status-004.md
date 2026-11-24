# Custom ExitStatus

In Spring Batch, `ExitStatus` describes the exit outcome of a Step or Job using an outcome code and an optional description. Standard codes such as `COMPLETED`, `FAILED`, and `STOPPED` cover common cases. However, business requirements sometimes need finer distinctions: a Step completes with skipped items, has no input data, requires manual review, or detects data that was already processed.

Spring Batch allows creating a **custom `ExitStatus`** to represent these outcomes. A Job flow can use a custom exit code to select the next Step. For example, `COMPLETED_WITH_SKIPS` can route to an error reporting Step, while `NO_DATA` can end the Job normally without running the import step.

Custom ExitStatus helps describe business outcomes and orchestrate the Job flow. It does not automatically alter `BatchStatus`: a Step can still have `BatchStatus.COMPLETED` while its `ExitStatus` is `COMPLETED_WITH_SKIPS`.

## 1. ExitStatus Consists of Exit Code and Exit Description

`ExitStatus` is a value object Spring Batch uses to describe the outcome of an execution. Two main parts:

- **Exit code:** a string identifying the outcome, typically used by the Job flow to match transitions.
- **Exit description:** supplemental information helping operators understand why the Step ended with that code.

Example:

```java
ExitStatus status = new ExitStatus(
        "COMPLETED_WITH_SKIPS",
        "Import completed with 7 skipped records"
);
```

In this example, `COMPLETED_WITH_SKIPS` is the code used by the Job flow for routing. The description records the number of skipped items for logging or investigation.

Spring Batch provides common standard codes:

| ExitStatus | Common Meaning |
|---|---|
| `COMPLETED` | Step/Job completed normally |
| `EXECUTING` | Currently executing in certain contexts |
| `FAILED` | Execution failed |
| `STOPPED` | Execution stopped |
| `NOOP` | No operation needed in certain situations |
| `UNKNOWN` | Outcome could not be determined |

Applications can create business-specific exit codes, such as `NO_DATA`, `COMPLETED_WITH_SKIPS`, `NEEDS_REVIEW`, `ALREADY_PROCESSED`, or `SOURCE_NOT_READY`.

## 2. Distinguishing ExitStatus from BatchStatus

`BatchStatus` and `ExitStatus` often have similar values in simple cases, but they describe two different aspects.

| Criterion | `BatchStatus` | `ExitStatus` |
|---|---|---|
| Purpose | Execution lifecycle status | Exit outcome and result code |
| Values | Standard enum such as `STARTED`, `COMPLETED`, `FAILED`, `STOPPED` | String exit code and exit description |
| Who uses it? | Spring Batch and operational tools | Job flow, logs, integrations, and outcome reporting |
| Custom codes? | Not by creating new enum values | Can create custom exit codes |

For example, a Step reads 1,000 records, skips 7 invalid records, and successfully writes the rest. The Step may end with:

```text
BatchStatus = COMPLETED
ExitStatus  = COMPLETED_WITH_SKIPS
```

The Step completed according to Spring Batch's lifecycle, but the business outcome needs review. Custom ExitStatus expresses that extra information.

Custom ExitStatus should not be used to hide execution errors. If the writer throws an exception that is not retried or skipped, the Step must reflect the failure via appropriate status and exception. Setting exit code `COMPLETED` in a listener does not turn a failed transaction into a success.

## 3. Creating a Custom ExitStatus in StepExecutionListener

A common approach is implementing `StepExecutionListener` and returning a custom ExitStatus in `afterStep()`. This callback runs after Step processing finishes, so it can read final counters such as `skipCount`, `readCount`, or `writeCount`.

For example, if the Step completes but at least one item was skipped, set exit code `COMPLETED_WITH_SKIPS`:

```java
public class ImportResultListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        // No pre-step processing needed.
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getStatus() != BatchStatus.COMPLETED) {
            return stepExecution.getExitStatus();
        }

        int skipped = stepExecution.getSkipCount();
        if (skipped > 0) {
            return new ExitStatus(
                    "COMPLETED_WITH_SKIPS",
                    "Import completed with " + skipped + " skipped items"
            );
        }

        return stepExecution.getExitStatus();
    }
}
```

The `BatchStatus.COMPLETED` check ensures the listener only classifies a completed Step. If the Step is `FAILED` or `STOPPED`, the listener keeps the current ExitStatus instead of changing it to a success outcome.

Register the listener on the Step:

```java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, Order> processor,
        ItemWriter<Order> writer,
        ImportResultListener listener) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .listener(listener)
            .build();
}
```

`.listener(listener)` registers the callback for the Step. `afterStep()` does not run after each chunk; it runs at the StepExecution level after the Step finishes.

## 4. Creating a Custom ExitStatus in a Tasklet

If the business outcome is determined directly within Tasklet logic, you can set ExitStatus via `StepContribution` before returning.

For example, a Tasklet checks the data source and finishes with `NO_DATA` if there are no records:

```java
public class CheckInputTasklet implements Tasklet {

    private final InputRepository inputRepository;

    public CheckInputTasklet(InputRepository inputRepository) {
        this.inputRepository = inputRepository;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        if (!inputRepository.hasRecords()) {
            contribution.setExitStatus(
                    new ExitStatus("NO_DATA", "No input records were found")
            );
            return RepeatStatus.FINISHED;
        }

        return RepeatStatus.FINISHED;
    }
}
```

The Tasklet returns `RepeatStatus.FINISHED` to end the Step. `StepContribution.setExitStatus()` supplies the outcome to StepExecution when the contribution is applied.

This approach is suitable when the Tasklet itself knows the outcome. If the outcome can only be determined after aggregating counters across the entire Step, `StepExecutionListener.afterStep()` is usually clearer.

Do not set a success ExitStatus before the work is actually complete. If the Tasklet continues processing and throws an exception afterward, the final status must reflect the execution failure.

## 5. Using Custom ExitStatus to Drive Job Flow

A Job flow can match exit codes using `.on(...)`. When a Step returns a custom code, the corresponding transition determines the next Step.

For example, an import Step can end in three cases:

- `COMPLETED`: all items processed normally.
- `COMPLETED_WITH_SKIPS`: Step completed, but some items were skipped.
- `FAILED`: Step failed.

Flow:

```text
importOrdersStep
       |
       +-- COMPLETED --------------------> publishReportStep
       |
       +-- COMPLETED_WITH_SKIPS ---------> reviewSkippedOrdersStep
       |
       +-- FAILED -----------------------> Job failed
       |
       +-- other ------------------------> fallback / fail
```

Java configuration:

```java
@Bean
public Job importJob(
        JobRepository jobRepository,
        Step importOrdersStep,
        Step reviewSkippedOrdersStep,
        Step publishReportStep) {

    return new JobBuilder("importJob", jobRepository)
            .start(importOrdersStep)
                .on("COMPLETED_WITH_SKIPS").to(reviewSkippedOrdersStep)
            .from(importOrdersStep)
                .on("COMPLETED").to(publishReportStep)
            .from(importOrdersStep)
                .on("FAILED").fail()
            .from(importOrdersStep)
                .on("*").fail()
            .from(reviewSkippedOrdersStep)
                .on("*").to(publishReportStep)
            .from(publishReportStep)
                .on("*").end()
            .end()
            .build();
}
```

`on()` matches against the Step's exit code. Therefore, when the listener returns `COMPLETED_WITH_SKIPS`, transition `.on("COMPLETED")` will not be selected for that Step. Declare the exact custom code that the Step actually returns.

The `*` wildcard acts as a fallback branch for remaining exit codes. Always define an explicit fallback so the Job does not fail due to missing transitions when a new outcome code appears.

## 6. Exit Description Is Not Used for Routing

In `ExitStatus`, exit code and exit description play different roles:

```java
new ExitStatus(
        "COMPLETED_WITH_SKIPS",
        "Skipped 7 records because their order dates were invalid"
);
```

Flow transitions use the code:

```java
.on("COMPLETED_WITH_SKIPS").to(reviewStep)
```

The description is explanatory info. You should not embed variable details such as item IDs, long exception messages, or timestamps into the exit code, because the flow must match a stable set of codes.

Bad example:

```java
return new ExitStatus("SKIPPED_7_RECORDS_AT_2026-11-15");
```

This code produces different values on every run and makes the flow hard to route. Use a stable code like `COMPLETED_WITH_SKIPS`, and record counts and causes in the exit description or logs.

## 7. Naming Conventions for Custom Exit Codes

Custom exit codes form a contract between Steps and the Job flow. Names must be stable, describe a clear outcome, and be used consistently across listeners, Tasklets, flow builders, and monitoring systems.

Some guidelines:

- Use uppercase and underscores following a consistent convention.
- Name after the business outcome, e.g., `NO_DATA`, `COMPLETED_WITH_SKIPS`, `NEEDS_REVIEW`.
- Avoid overly generic codes like `OK` or `ERROR` if the Job needs to distinguish multiple situations.
- Do not put dynamic data into the exit code; put it in the exit description or logs.
- Do not use a custom success code to mask technical failures.
- When renaming a code, update all dependent transitions and dashboards/alerts reading that code.
- Keep codes concise and stable enough for long-term metadata storage.

You can define constants to prevent typos:

```java
public final class StepExitCodes {

    public static final String NO_DATA = "NO_DATA";
    public static final String COMPLETED_WITH_SKIPS = "COMPLETED_WITH_SKIPS";
    public static final String NEEDS_REVIEW = "NEEDS_REVIEW";
    public static final String ALREADY_PROCESSED = "ALREADY_PROCESSED";

    private StepExitCodes() {
    }
}
```

Use the same constant in the listener:

```java
return new ExitStatus(
        StepExitCodes.COMPLETED_WITH_SKIPS,
        "Skipped " + stepExecution.getSkipCount() + " items"
);
```

And in the flow:

```java
.from(importOrdersStep)
    .on(StepExitCodes.COMPLETED_WITH_SKIPS).to(reviewSkippedOrdersStep)
```

## 8. Multiple Listeners Modifying ExitStatus

A Step can have multiple registered listeners. ExitStatus values returned by listeners are combined with the Step's current ExitStatus according to `ExitStatus.and()` rules. Therefore, do not assume a later listener will always completely overwrite an earlier listener's result.

If multiple listeners return custom codes, the combined outcome may not be the code the flow author intended. This becomes especially confusing when one listener classifies `COMPLETED_WITH_SKIPS` while another returns `NEEDS_REVIEW`.

More controllable design approaches:

- Centralize final outcome classification logic into a single listener.
- If multiple conditions exist, define a clear business precedence order within one method.
- Listeners that only write logs/metrics should not return a new custom ExitStatus unless flow routing needs to change.
- Log `stepExecution.getExitStatus()` after the Step finishes to confirm the actual persisted code.

For example, if skip count exceeds a threshold the outcome should be `NEEDS_REVIEW`; if skips are below the threshold it is `COMPLETED_WITH_SKIPS`. Both conditions should be handled in one place:

```java
@Override
public ExitStatus afterStep(StepExecution stepExecution) {
    if (stepExecution.getStatus() != BatchStatus.COMPLETED) {
        return stepExecution.getExitStatus();
    }

    int skipped = stepExecution.getSkipCount();
    if (skipped > 20) {
        return new ExitStatus("NEEDS_REVIEW", "Skip count exceeded 20");
    }
    if (skipped > 0) {
        return new ExitStatus("COMPLETED_WITH_SKIPS", "Some items were skipped");
    }

    return stepExecution.getExitStatus();
}
```

## 9. Custom ExitStatus Does Not Change BatchStatus

This is essential to remember when reading metadata:

```text
StepExecution
  BatchStatus = COMPLETED
  ExitStatus  = COMPLETED_WITH_SKIPS
```

Custom ExitStatus provides information for the Job flow and operators. It does not automatically turn `BatchStatus` into `FAILED`, `STOPPED`, or a new enum value.

If a Job needs to fail due to a business condition, you can design the flow to terminate with `.fail()` when receiving a code such as `VALIDATION_REJECTED`. Or let the Step actually throw an exception if it is an execution error. Choose the approach matching the condition's meaning:

- Step finished running, but the Job must fail per orchestration rules: you can use a custom exit code and a `.fail()` transition.
- Step encountered a technical error during execution: let the exception and BatchStatus reflect `FAILED`.
- Step completed but needs review: keep BatchStatus `COMPLETED`, return a custom code, and route to a review Step.

Do not confuse returning a custom ExitStatus containing the word `FAILED` with StepExecution automatically having `BatchStatus.FAILED`. If the flow needs to end in failure, transitions and terminal states must be configured accordingly.

## 10. Distinguishing Step ExitStatus and Decider FlowExecutionStatus

`ExitStatus` belongs to StepExecution. When a Step completes, the Job flow can read its exit code to select a transition.

`FlowExecutionStatus` is the status returned by `JobExecutionDecider` at a point in the flow. A decider is not a Step and does not alter the preceding Step's ExitStatus.

| Criterion | Custom ExitStatus | JobExecutionDecider |
|---|---|---|
| Source | Step/StepExecution or listener | `decide()` method |
| Return value | `ExitStatus` | `FlowExecutionStatus` |
| Scope | Exit outcome of a Step | Decision at a point in the flow |
| Use when | The Step wants to publish its own outcome | Condition needs to read multiple pieces of info to pick a branch |

If the Step already knows an outcome such as `NO_DATA` or `COMPLETED_WITH_SKIPS`, custom ExitStatus is usually the most direct approach. If you need to combine JobParameters, JobExecutionContext, and metadata from previous Steps, a decider may be more suitable.

## 11. Inspecting Custom ExitStatus in Metadata

After a Step finishes, you can read ExitStatus from `StepExecution`:

```java
ExitStatus exitStatus = stepExecution.getExitStatus();

log.info(
        "step={}, batchStatus={}, exitCode={}, exitDescription={}",
        stepExecution.getStepName(),
        stepExecution.getStatus(),
        exitStatus.getExitCode(),
        exitStatus.getExitDescription()
);
```

`JobExplorer` can be used to read JobExecution and StepExecutions from JobRepository. This is useful when a dashboard needs to display both lifecycle status and business outcome for each Step.

With a standard JDBC JobRepository, StepExecution information is usually stored in the `BATCH_STEP_EXECUTION` table, in columns `STATUS`, `EXIT_CODE`, and `EXIT_MESSAGE`. Table/column names may differ if schema or table prefixes are customized.

Example query:

```sql
SELECT
    STEP_EXECUTION_ID,
    STEP_NAME,
    STATUS,
    EXIT_CODE,
    EXIT_MESSAGE,
    START_TIME,
    END_TIME
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :jobExecutionId
ORDER BY STEP_EXECUTION_ID;
```

`STATUS` is the lifecycle status, `EXIT_CODE` is the outcome code, and `EXIT_MESSAGE` is the description. Do not merge these three fields into a single concept.

The final JobExecution also has `BatchStatus` and `ExitStatus`. Job-level ExitStatus is determined through flow orchestration and Step outcomes. To know accurately why a Job chose a branch, inspect the StepExecution that triggered the transition alongside the final JobExecution, rather than looking only at a job-level field.

## 12. Restart and Custom ExitStatus

Custom ExitStatus is persisted with StepExecution metadata. When a Job restarts, Spring Batch relies on the previous execution's status and metadata to decide which Steps need to run again.

Points to note:

- Steps already `COMPLETED` are usually skipped when restarting the same JobInstance, unless configured with options such as `allowStartIfComplete(true)`.
- Custom ExitStatus does not create a new JobInstance and does not change identifying JobParameters.
- If the Job flow uses a custom exit code to transition to a review Step, the review Step's status is also saved separately.
- If a completed Step needs to re-run, clarify the impact of `allowStartIfComplete` and idempotency of side effects.
- When renaming a custom exit code, consider in-flight JobExecutions and transitions stored against the new code version.

Custom codes should stay stable across deployments. If an older execution saved `COMPLETED_WITH_SKIPS` while the new version only declares a transition for `NEEDS_REVIEW`, the restart flow may no longer have a matching branch for the old outcome.

## 13. Common Misconceptions

**Thinking custom ExitStatus creates a new BatchStatus.** `BatchStatus` is a lifecycle enum; custom codes belong to ExitStatus.

**Using exit description for routing.** Job flows match exit code via `.on(...)`. Description is for explanatory info only.

**Assuming `.on("COMPLETED")` still matches when a Step returns `COMPLETED_WITH_SKIPS`.** These are two different exit codes. Transitions must be declared for custom codes.

**Returning a success code when the Step actually failed.** This can send the flow down the wrong branch and mask errors. Check BatchStatus before classifying a success outcome.

**Assuming the last listener overwrites earlier ExitStatus.** The framework combines ExitStatus from listeners with the current status using its own rules. Avoid multiple listeners competing to set outcome codes.

**Using dynamic codes containing IDs or timestamps.** Flows are hard to match and metadata hard to operate on. Use stable codes and put details in descriptions/logs.

**Thinking custom ExitStatus automatically fails the Job.** If terminal failure is needed, declare a `.fail()` transition or let the Step actually fail in processing logic.

## 14. Testing Custom ExitStatus

A test suite should verify both the generated outcome code and the chosen Job flow branch:

1. When the Step completes with no skips, ExitStatus remains `COMPLETED`.
2. When the Step completes with skips, ExitStatus is `COMPLETED_WITH_SKIPS`.
3. When the Step is `FAILED`, the listener does not change the result to a success code.
4. Exit description contains useful info without affecting transitions.
5. Job flow routes to the review Step when receiving `COMPLETED_WITH_SKIPS`.
6. Job flow routes to the normal next Step when receiving `COMPLETED`.
7. Unexpected codes follow the wildcard fallback.
8. Final JobExecution has a status matching the terminal transition.

Example unit test for a listener:

```java
@Test
void returnsCompletedWithSkipsWhenStepCompletedWithSkippedItems() {
    StepExecution stepExecution = new StepExecution("importOrdersStep", null);
    stepExecution.setStatus(BatchStatus.COMPLETED);
    stepExecution.setExitStatus(ExitStatus.COMPLETED);
    stepExecution.setReadSkipCount(2);

    ImportResultListener listener = new ImportResultListener();
    ExitStatus result = listener.afterStep(stepExecution);

    assertEquals("COMPLETED_WITH_SKIPS", result.getExitCode());
    assertTrue(result.getExitDescription().contains("2 skipped items"));
}
```

This is an illustrative test for the listener. Integration tests with JobRepository and the Job flow are needed to verify actual transitions and final metadata.

## 15. Designing Custom ExitStatus

Create a custom ExitStatus when a Step needs to publish a specific business outcome for the Job flow or operational tools to distinguish. Choose stable, concise, convention-following exit codes; use exit descriptions to explain counts, causes, or relevant data.

Set the code in `StepExecutionListener.afterStep()` when the outcome depends on final counters, or in a `Tasklet` via `StepContribution` when the Tasklet's logic already knows the outcome. Declare `.on(...)` transitions for every code and include a wildcard fallback. Keep BatchStatus accurately reflecting the execution lifecycle, and never use custom ExitStatus to hide errors. Inspect both Step and Job metadata to verify the flow took the intended branch.

When designed as an explicit contract between Steps and the Job flow, custom ExitStatus lets batch workflows express rich business outcomes while maintaining consistent execution state and orchestration.
