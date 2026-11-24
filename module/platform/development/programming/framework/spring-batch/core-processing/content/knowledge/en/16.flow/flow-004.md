# BatchStatus and ExitStatus

In Spring Batch, `BatchStatus` and `ExitStatus` both describe the execution outcome of a job or step, but they serve two different purposes. `BatchStatus` represents the lifecycle state managed by the framework, such as running, completed, failed, or stopped. `ExitStatus` describes the exit code and additional information of an execution; this code is typically used to decide the next path in a job's flow.

For example, a step may finish processing all items while some items were skipped according to policy. The framework can mark `BatchStatus.COMPLETED`, while the application sets `ExitStatus` to `COMPLETED_WITH_SKIPS`. That way, the system still knows the step finished normally in execution terms, while the flow can transition to a step that reviews skipped records.

The two status types share the same default codes such as `COMPLETED` or `FAILED`, so they are easily mistaken for one another. When designing a flow, understand that `on(...)` matches against the step's exit code; it does not match the `BatchStatus` enum directly.

## 1. What is BatchStatus?

`BatchStatus` is an enum defined by Spring Batch to represent the execution state of a `JobExecution` or `StepExecution`. It indicates what stage the framework considers the execution to be in or how it ended.

Common values:

| BatchStatus | Meaning |
|---|---|
| `STARTING` | Execution is being initialized |
| `STARTED` | Job or step is executing |
| `STOPPING` | Processing a stop request |
| `STOPPED` | Execution stopped by request or stop mechanism |
| `COMPLETED` | Execution completed normally from the framework's perspective |
| `FAILED` | Execution failed due to an unhandled error |
| `ABANDONED` | Execution marked not to be restarted in the normal way |
| `UNKNOWN` | Reliable status could not be determined; usually requires investigation |

`BatchStatus` is updated by the framework during the execution lifecycle. Applications typically read it via `JobExecution.getStatus()` or `StepExecution.getStatus()` to see whether an execution is running, completed, or failed.

Example:

```java
BatchStatus jobStatus = jobExecution.getStatus();
BatchStatus stepStatus = stepExecution.getStatus();

if (jobStatus == BatchStatus.COMPLETED) {
    log.info("Job execution completed");
} else if (jobStatus == BatchStatus.FAILED) {
    log.error("Job execution failed");
}
```

Do not arbitrarily set `BatchStatus` to drive business logic. Let the framework manage lifecycle status through execution outcomes, exceptions, stop/abandon operations, and appropriate flow transitions.

## 2. What is ExitStatus?

`ExitStatus` is a value object describing the exit outcome of a job or step. It consists of two main parts:

- `exitCode`: the exit code, usually a string such as `COMPLETED`, `FAILED`, `STOPPED`, or a custom code defined by the application.
- `exitDescription`: an additional description, typically used to record a cause, context, or explanatory details about the outcome.

Some built-in constant values:

| ExitStatus | Common meaning |
|---|---|
| `ExitStatus.EXECUTING` | Execution is in progress |
| `ExitStatus.COMPLETED` | Completed normally |
| `ExitStatus.NOOP` | No actual operation needed to be performed |
| `ExitStatus.FAILED` | Execution failed |
| `ExitStatus.STOPPED` | Execution was stopped |
| `ExitStatus.UNKNOWN` | Unknown outcome |

Applications can create custom codes:

```java
ExitStatus status = new ExitStatus(
        "COMPLETED_WITH_SKIPS",
        "Step completed with skipped records");
```

Custom codes allow the flow to reflect more granular business outcomes than default statuses. For instance, `COMPLETED_WITH_SKIPS`, `COMPLETED_WITH_WARNINGS`, or `NO_DATA` can be used for branching when they carry clear meaning in the workflow.

`ExitStatus` is not an enum; the exit code is a string and can be extended per application. Therefore, code names must be standardized across listeners, flow transitions, dashboards, and tests. Avoid using multiple spellings for the same outcome.

## 3. Core differences between BatchStatus and ExitStatus

| Criterion | BatchStatus | ExitStatus |
|---|---|---|
| Data type | Enum defined by Spring Batch | Value object containing exit code and exit description |
| Purpose | Execution lifecycle status | Exit outcome code and termination details |
| Values | Fixed set of values such as `STARTED`, `COMPLETED`, `FAILED` | Standard values or custom codes such as `COMPLETED_WITH_SKIPS` |
| Managed by | Primarily managed by the framework | Framework sets defaults; application can supply exit codes via listener/flow |
| Use in flow | Not the value matched directly by `on(...)` | Exit code is used to match transitions |
| Access | `execution.getStatus()` | `execution.getExitStatus()` |

For example, a step processes 1,000 records, successfully writes 990 records, and skips 10 records per policy. The step can finish with:

```text
BatchStatus = COMPLETED
ExitStatus  = COMPLETED_WITH_SKIPS
```

This is not a contradiction. `BatchStatus` states that the step completed according to execution mechanics; `ExitStatus` states that the outcome has a characteristic the flow needs to know about.

Conversely, if the writer throws an unhandled error, the step usually has:

```text
BatchStatus = FAILED
ExitStatus  = FAILED
```

Default values often correspond to one another, but not every `ExitStatus` code has to share the name of a `BatchStatus` value.

## 4. Reading both statuses after a job runs

After `JobLauncher` returns a `JobExecution` in synchronous mode, you can read the status of the job and each step:

```java
JobExecution jobExecution =
        jobLauncher.run(importJob, jobParameters);

log.info("Job status={}, exitCode={}, exitDescription={}",
        jobExecution.getStatus(),
        jobExecution.getExitStatus().getExitCode(),
        jobExecution.getExitStatus().getExitDescription());

for (StepExecution stepExecution : jobExecution.getStepExecutions()) {
    log.info("Step {} status={}, exitCode={}",
            stepExecution.getStepName(),
            stepExecution.getStatus(),
            stepExecution.getExitStatus().getExitCode());
}
```

If the job runs asynchronously, `JobLauncher.run()` may return as soon as the job starts or is submitted to an executor. In that case, the status in the returned object is not yet the final status. Use `JobExplorer` with the execution ID to load the latest status afterward.

Example:

```java
JobExecution latest = jobExplorer.getJobExecution(executionId);
if (latest != null) {
    BatchStatus batchStatus = latest.getStatus();
    ExitStatus exitStatus = latest.getExitStatus();
}
```

Do not read only the job's status and ignore individual steps. A multi-step job may have its first step completed, the next step failed, and subsequent steps not yet executed. `StepExecution` helps pinpoint the exact stage where the issue occurred.

## 5. How default ExitStatus is produced

In the normal case, Spring Batch automatically sets an `ExitStatus` matching the step outcome:

- A normally completed step usually has `ExitStatus.COMPLETED`.
- A step failed due to an unhandled exception usually has `ExitStatus.FAILED`.
- A stopped step usually has `ExitStatus.STOPPED`.
- A step with no work to perform may result in `NOOP` in certain situations.

An application does not need to manually return `ExitStatus.COMPLETED` after every successful step. Add custom codes only when the flow or operational systems need to distinguish a specific outcome.

`ExitStatus` also carries a description. You can include explanatory information for investigation, but never put secrets, tokens, or sensitive payloads in the description because metadata may be displayed in dashboards or logs.

## 6. Customizing ExitStatus with StepExecutionListener

A common way to set a custom exit code is via `StepExecutionListener.afterStep()`. The listener can inspect counters or data in `StepExecution` and return a new `ExitStatus`.

For example, if a step has skipped items, set the exit code `COMPLETED_WITH_SKIPS`:

```java
public class SkipAwareStepListener implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getSkipCount() > 0) {
            return new ExitStatus(
                    "COMPLETED_WITH_SKIPS",
                    "One or more items were skipped");
        }

        return null;
    }
}
```

Returning `null` means the listener does not request any change to the existing exit status. When a non-null status is returned, Spring Batch combines it with the step's current exit status. Choose codes with a clear convention and avoid overwriting real failure information with a code that looks like success.

Register the listener on the step:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer,
        SkipAwareStepListener skipAwareStepListener) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .skip(InvalidOrderException.class)
            .skipLimit(50)
            .listener(skipAwareStepListener)
            .build();
}
```

When the step finishes with one or more skipped items, the listener can set the `COMPLETED_WITH_SKIPS` code. `BatchStatus` can still be `COMPLETED`; the custom exit code supplies extra information for the flow.

Do not use `afterStep()` to arbitrarily change the status after a step has failed. If an exception caused the step to fail, the `FAILED` code and error details should be preserved unless a clear flow/exit rule has been explicitly designed and tested.

## 7. Using ExitStatus to drive flow control

In a multi-step job, `.on(...)` is used to declare transitions based on the preceding step's exit code. This is why `ExitStatus` is central to the Flow chapter.

For example, after importing orders:

- If no items were skipped (`COMPLETED`), continue to publish results.
- If items were skipped (`COMPLETED_WITH_SKIPS`), transition to a step to review invalid records.
- If the step failed (`FAILED`), end the job with a failed status.

```java
@Bean
Job importOrdersJob(
        JobRepository jobRepository,
        Step importOrdersStep,
        Step reviewSkippedOrdersStep,
        Step publishOrdersStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .start(importOrdersStep)
                .on("COMPLETED_WITH_SKIPS").to(reviewSkippedOrdersStep)
            .from(importOrdersStep)
                .on("COMPLETED").to(publishOrdersStep)
            .from(importOrdersStep)
                .on("*").fail()
            .end()
            .build();
}
```

In this example, `on("COMPLETED_WITH_SKIPS")` matches the custom exit code. `on("COMPLETED")` matches the normal completion outcome. The `on("*")` transition serves as a fallback branch for other exit codes and ends the flow with a fail outcome.

Transitions should cover all outcomes that the step can return. If an exit code is missed, the flow may fail to find a matching transition and the job may end with a flow control error. For critical flows, define an intentional default branch.

## 8. Wildcards in transitions

`on(...)` supports patterns for matching exit codes. Common patterns:

- `on("COMPLETED")`: matches the exact code `COMPLETED`.
- `on("FAILED")`: matches the exact code `FAILED`.
- `on("COMPLETED_*")`: matches codes starting with `COMPLETED_` according to pattern rules.
- `on("*")`: matches any remaining exit code.

Example:

```java
return new JobBuilder("batchJob", jobRepository)
        .start(processStep)
            .on("COMPLETED_WITH_*").to(reviewStep)
        .from(processStep)
            .on("COMPLETED").to(publishStep)
        .from(processStep)
            .on("*").fail()
        .end()
        .build();
```

Declare specific codes and clear wildcard fallback branches. Avoid using `*` too early when there are custom codes that need dedicated handling. When adding a new exit code, update the flow and corresponding tests.

## 9. Distinguishing ExitStatus from FlowExecutionStatus

When using `JobExecutionDecider`, another status type comes into play: `FlowExecutionStatus`. This is neither `BatchStatus` nor `ExitStatus`.

- `BatchStatus` describes the job/step lifecycle.
- `ExitStatus` describes the exit code of a job/step and is used by `.on(...)` transitions.
- `FlowExecutionStatus` represents the outcome of a flow branch or a decision returned by a decider.

Example decider:

```java
public class OrderVolumeDecider implements JobExecutionDecider {

    @Override
    public FlowExecutionStatus decide(
            JobExecution jobExecution,
            StepExecution stepExecution) {

        if (stepExecution != null && stepExecution.getWriteCount() > 10000) {
            return new FlowExecutionStatus("HIGH_VOLUME");
        }

        return new FlowExecutionStatus("NORMAL_VOLUME");
    }
}
```

The decider returns a `FlowExecutionStatus`, and the flow can then use `.on("HIGH_VOLUME")` or `.on("NORMAL_VOLUME")` to pick a branch. Use a decider when the decision depends on multiple pieces of data or logic more complex than a single step's exit code.

If you only need to distinguish whether a step completed normally or with skips, a custom `ExitStatus` is usually sufficient. There is no need to add a decider if a simple listener and transition can express the rule.

## 10. BatchStatus and ExitStatus at the job level

A job also has `BatchStatus` and `ExitStatus`, similar to a step. `JobExecution.getStatus()` reports the final status of the execution according to the framework; `JobExecution.getExitStatus()` reports the exit code and description of the job.

In a multi-step flow, the job status is aggregated according to the flow result and configured transitions. Therefore, the final status of the job is not necessarily a direct copy from the last step if the flow has branches, conditional terminations, or custom codes.

For example, an import step has `ExitStatus.COMPLETED_WITH_SKIPS`, and the flow then moves to a review step. If the review step completes and the flow finishes normally, the job may end with `BatchStatus.COMPLETED`; the job's final exit status depends on the flow result and termination configuration. If the business requires retaining a trace that "items were skipped", store that information in appropriate data or metadata and define explicitly what final exit code the system should publish.

Do not infer the business status of individual items solely from `JobExecution.getStatus()`. A job can complete even though items were skipped according to policy. If you need to know whether each order was accepted or rejected, store a separate business status.

## 11. Ending a flow: end, fail, and stop

When declaring transitions, distinguish the ways to end a flow:

- `.to(nextStep)`: transitions to the next step or flow.
- `.end()`: ends the flow with the completion status defined for that transition.
- `.fail()`: ends the flow with a failed status.
- `.stop()`: ends the flow with a stopped status; can include restart information such as a restart target depending on the API used.

Example of a flow ending as failed when a step returns `FAILED`:

```java
return new JobBuilder("validateAndImportJob", jobRepository)
        .start(validateStep)
            .on("FAILED").fail()
        .from(validateStep)
            .on("COMPLETED").to(importStep)
        .from(validateStep)
            .on("*").fail()
        .end()
        .build();
```

Here, `.fail()` terminates the flow with a failure result. `.stop()` is appropriate when you want to intentionally pause/stop a job so it can be restarted later. `.end()` terminates the flow as a completed branch; do not use it in place of `.fail()` if the goal is to mark the job failed.

When using `.stopAndRestart(...)` or related stop APIs, clearly specify the restart target step/flow and test the actual `JobExecution` state. Do not set `BatchStatus` directly to simulate a transition.

## 12. When should you use custom ExitStatus codes?

Custom codes are useful when two outcomes are both technically complete yet require different follow-up processing.

Examples:

- `COMPLETED_WITH_SKIPS`: step completed but had skipped items.
- `COMPLETED_WITH_WARNINGS`: step completed and detected warnings that do not fail the job.
- `NO_DATA`: no data in the processing scope.
- `VALIDATION_REJECTED`: input did not meet business rules and requires a separate handling branch.
- `RECONCILIATION_MISMATCH`: reconciliation did not match and requires investigation.

Before adding a code, determine:

1. Which outcome does the code represent and who is responsible for handling it?
2. What should the step's final `BatchStatus` be?
3. Which step should the flow transition to, or in which status should it terminate?
4. Does the code need to be preserved at the job level or only at the step level?
5. Do dashboards, alerts, tests, and runbooks understand that code?

Do not create custom codes just to rename `COMPLETED` or `FAILED` if there is no difference in processing. Too many codes without clear contracts make flows hard to read and operate.

## 13. ExitDescription and diagnostic information

`ExitStatus` can carry an `exitDescription` to provide additional context. Example:

```java
ExitStatus status = new ExitStatus(
        "RECONCILIATION_MISMATCH",
        "Expected total 125000.00 but actual total was 124500.00");
```

The description is suitable for short diagnostic information that helps operators understand the reason for the outcome. Do not use the description as a place to store full reports, lists of failed items, or large payloads. Such data should be stored in business tables, report files, or appropriate logging/observability systems; contexts and exit descriptions should hold only reference keys if needed.

Do not put passwords, access tokens, personal data, or sensitive information into the exit description. Metadata can be read via `JobExplorer` or displayed on dashboards.

## 14. Testing BatchStatus and ExitStatus

Tests should verify both lifecycle status and exit codes. For example, for a step with skipped items:

```java
JobExecution execution =
        jobLauncherTestUtils.launchJob(jobParameters);

assertEquals(BatchStatus.COMPLETED, execution.getStatus());

StepExecution importStep = execution.getStepExecutions()
        .stream()
        .filter(step -> step.getStepName().equals("importOrdersStep"))
        .findFirst()
        .orElseThrow();

assertEquals(BatchStatus.COMPLETED, importStep.getStatus());
assertEquals("COMPLETED_WITH_SKIPS",
        importStep.getExitStatus().getExitCode());
assertTrue(importStep.getSkipCount() > 0);
```

This test assumes the step has `SkipAwareStepListener` and input data that causes at least one item to be skipped. `JobLauncherTestUtils` must be configured to run the right job in the test context.

In addition, you should test these cases:

1. Step succeeds normally: `BatchStatus.COMPLETED`, `ExitStatus.COMPLETED`.
2. Step fails due to an unhandled exception: `BatchStatus.FAILED`, corresponding exit code.
3. Step is stopped: verify `STOPPED` status and appropriate exit code.
4. Step completes with a custom code: status still reflects lifecycle, exit code carries the extra outcome.
5. Transitions by exit code: verify the right next step is executed.
6. Wildcard transition: verify unlisted codes are handled by the fallback branch.
7. Flow ending via `.fail()`, `.stop()`, or `.end()`: verify final job status matches intent.
8. Multi-step job: verify `JobExecution` and each `StepExecution` have expected status/exit status.

Do not check only `JobExecution.getStatus()`. A flow can take the wrong branch even though the job still finishes as completed. Inspect the list of step executions and the side effects of the selected branch.

## 15. Common mistakes

**Confusing `BatchStatus` with `ExitStatus`.** `BatchStatus` is a lifecycle enum; `ExitStatus` is a customizable exit outcome code. When using `.on(...)`, think in terms of exit codes.

**Thinking `COMPLETED_WITH_SKIPS` turns BatchStatus into a new status.** Custom codes belong to `ExitStatus`; `BatchStatus` can still be `COMPLETED`.

**Using `on("FAILED")` to catch every business error.** If a listener sets a custom exit code or the flow returns another outcome, an exact pattern may not match. Inspect the actual exit code and declare an intentional wildcard fallback.

**Forgetting to register the listener.** Writing a class that returns a custom `ExitStatus` without attaching it to the step means the callback is never invoked. Register the listener with the builder and test the exit code.

**Returning a custom code that hides a real error.** Do not turn a failed step into a success-looking code just to keep the flow moving. If errors need handling, define an explicit recovery branch and preserve error details.

**Failing to declare transitions for all possible outcomes.** The flow may fail to find a matching branch. Use specific transitions and an appropriate fallback branch.

**Using ExitDescription as a data store.** The description should contain only short information; detailed data should be stored in an appropriate place.

**Checking only the final job status.** Also check individual step executions and which flow branch actually ran.

## Conclusion

`BatchStatus` indicates the execution lifecycle state of a job or step; `ExitStatus` indicates the exit code and outcome description. In normal cases, they have corresponding values such as `COMPLETED`, `FAILED`, or `STOPPED`, but an application can set a custom `ExitStatus` to distinguish outcomes that require different follow-up handling.

In flows, `.on(...)` matches a step's exit code. You can produce custom codes via `StepExecutionListener`, use transitions to route to the right step, and use `JobExecutionDecider` when more complex decision logic is needed. During operations and testing, inspect `BatchStatus`, `ExitStatus`, each `StepExecution`, and actual business results to know how the job ran and whether the flow selected the right branch.
