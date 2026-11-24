# Conditional transitions by ExitStatus

In Spring Batch, a Job can choose the next Step based on the outcome of the Step that just ran. This mechanism is called a *conditional transition*. Instead of always running a fixed sequence of Steps, the Job flow inspects the `ExitStatus` of the current Step and follows the matching branch.

For example, an input-validation Step may produce three outcomes: valid data, no data, or skipped records. The Job can continue importing data when valid, end normally when there is no data, or transition to a manual-review Step when records are skipped.

Conditional transitions separate Step execution logic from Job orchestration logic. The Step reports its outcome; the Job flow decides the next step.

## 1. What is ExitStatus?

`ExitStatus` describes the exit outcome of a Step execution. It consists of an exit code and a description, where the exit code is typically used by the Job flow to select a transition.

Some common standard exit codes:

| Exit code | Common meaning |
|---|---|
| `COMPLETED` | Step completed normally |
| `FAILED` | Step failed |
| `STOPPED` | Step was stopped |
| `EXECUTING` | Step is executing in certain contexts |
| `UNKNOWN` | Outcome could not be determined |

An application can create custom business exit codes, such as `NO_DATA`, `COMPLETED_WITH_SKIPS`, or `NEEDS_REVIEW`. These codes are not `BatchStatus`; they are outcomes used to describe the Step and route the flow.

## 2. Distinguishing BatchStatus and ExitStatus

Two concepts are often confused:

- `BatchStatus` reflects the lifecycle status managed by Spring Batch, such as `STARTED`, `COMPLETED`, `FAILED`, or `STOPPED`.
- `ExitStatus` describes the exit code and additional information after a Step finishes. Job flows typically match against this field's exit code.

A Step can have `BatchStatus.COMPLETED` while its `ExitStatus` is `COMPLETED_WITH_SKIPS`. In terms of execution, the Step finished successfully according to the framework; in business terms, it has a warning that needs to be handled on a different branch.

Conversely, you should not merely change `ExitStatus` to `COMPLETED` to hide an execution failure. If the Step truly failed, `BatchStatus` and the exception must accurately reflect that state.

## 3. Job flow uses on() to select a branch

The Java flow builder allows declaring transitions by exit code using `.on(pattern)`:

```java
@Bean
public Job importOrdersJob(
        JobRepository jobRepository,
        Step validateOrdersStep,
        Step importOrdersStep,
        Step reviewSkippedOrdersStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .start(validateOrdersStep)
                .on("COMPLETED_WITH_SKIPS").to(reviewSkippedOrdersStep)
            .from(validateOrdersStep)
                .on("COMPLETED").to(importOrdersStep)
            .from(validateOrdersStep)
                .on("NO_DATA").end()
            .from(validateOrdersStep)
                .on("FAILED").fail()
            .from(validateOrdersStep)
                .on("*").fail()
            .end()
            .build();
}
```

In this example:

- `COMPLETED_WITH_SKIPS`: transitions to `reviewSkippedOrdersStep`.
- `COMPLETED`: transitions to `importOrdersStep`.
- `NO_DATA`: ends the Job with a completed status.
- `FAILED`: ends the Job with a failed status.
- `*`: fallback branch for exit codes not explicitly declared.

`.start(step)` specifies the first Step. `.from(step)` continues declaring transitions originating from the same Step. `.on(...)` selects the pattern to match the exit code, and `.to(...)` moves to the next Step.

## 4. Standard exit codes and custom exit codes

Without customization, a Step usually finishes with a standard exit code such as `COMPLETED` or `FAILED`. When business logic needs to distinguish additional outcomes, you can create a custom `ExitStatus`.

For example, a listener checking skipped item counts and read item counts:

```java
public class ValidationResultListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        // No pre-step processing needed.
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getStatus() != BatchStatus.COMPLETED) {
            return stepExecution.getExitStatus();
        }

        if (stepExecution.getReadCount() == 0) {
            return new ExitStatus("NO_DATA", "Input contained no records");
        }

        if (stepExecution.getSkipCount() > 0) {
            return new ExitStatus(
                    "COMPLETED_WITH_SKIPS",
                    "Some records were skipped"
            );
        }

        return stepExecution.getExitStatus();
    }
}
```

Registering the listener on the Step:

```java
@Bean
public Step validateOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, Order> processor,
        ItemWriter<Order> writer,
        ValidationResultListener listener) {

    return new StepBuilder("validateOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .listener(listener)
            .build();
}
```

`afterStep()` returns a custom exit code only when `BatchStatus` is `COMPLETED`. If the Step has `FAILED`, the listener preserves the current `ExitStatus` so the Job flow can handle the failure branch.

## 5. Transition matching rules

Transitions are declared using patterns matched against the exit code. Specific codes should be placed before general patterns or wildcards so that routing intent is easy to read and is not shadowed by a fallback branch.

Example:

```java
.start(validateStep)
    .on("COMPLETED_WITH_SKIPS").to(reviewStep)
.from(validateStep)
    .on("COMPLETED").to(importStep)
.from(validateStep)
    .on("*").fail()
```

`*` is a wildcard matching remaining exit codes. You can use patterns with wildcards to group codes by convention, but make patterns specific enough and verify precedence when multiple patterns could match.

A flow should have a branch for every possible outcome. If a Step returns a custom exit code without a matching transition, the Job may end with a flow definition error instead of taking the branch the author expected. A final wildcard is a clear way to provide a fallback branch.

## 6. Distinguishing to(), end(), fail(), and stop()

After `.on(...)`, the flow builder can transition to another Step or end the flow in a specific state.

| Method | Routing meaning |
|---|---|
| `.to(nextStep)` | Transitions to the specified Step |
| `.end()` | Ends the Job flow with a completed outcome |
| `.fail()` | Ends the Job flow with a failed status |
| `.stop()` | Stops the Job flow with a stopped status |

For example, when there is no data, the Job can finish normally without running the data import Step:

```java
.from(validateStep)
    .on("NO_DATA").end()
```

If the outcome requires error handling and the Job must be marked failed:

```java
.from(validateStep)
    .on("FAILED").fail()
```

If it needs to stop to wait for external action or an operational condition, `.stop()` can be used; a stopped status can be restarted according to Job and Step rules.

Do not confuse `.end()` with `.to(nextStep)`. `.end()` finishes the Job flow; `.to(nextStep)` continues to run another Step. Choosing the terminal state should accurately reflect business outcomes and operational requirements.

## 7. Complete flow example with multiple business branches

Suppose an order import Job has the following Steps:

1. `validateInputStep`: validates input data.
2. `importOrdersStep`: imports valid data.
3. `reviewSkippedStep`: builds a list of records needing review.
4. `sendNoDataNoticeStep`: records the case where the file has no data.

The flow can be configured as follows:

```java
@Bean
public Job importOrdersJob(
        JobRepository jobRepository,
        Step validateInputStep,
        Step importOrdersStep,
        Step reviewSkippedStep,
        Step sendNoDataNoticeStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .start(validateInputStep)
                .on("COMPLETED").to(importOrdersStep)
            .from(validateInputStep)
                .on("COMPLETED_WITH_SKIPS").to(reviewSkippedStep)
            .from(validateInputStep)
                .on("NO_DATA").to(sendNoDataNoticeStep)
            .from(validateInputStep)
                .on("FAILED").fail()
            .from(validateInputStep)
                .on("*").fail()
            .from(importOrdersStep)
                .on("*").end()
            .from(reviewSkippedStep)
                .on("*").end()
            .from(sendNoDataNoticeStep)
                .on("*").end()
            .end()
            .build();
}
```

The flow above illustrates routing based on validation results. The import, review, and no-data branches all end the Job after their respective Step finishes. In a production system, you can add dedicated failure transitions for each Step instead of using `*` to end generically.

## 8. Transitions by ExitStatus are not direct conditions on BatchStatus

A common mistake is thinking `.on("COMPLETED")` checks `BatchStatus.COMPLETED`. In reality, the transition pattern matches the exit code of `ExitStatus`.

In the normal case, a successful Step has `ExitStatus` `COMPLETED`, so the two concepts look alike. However, when a listener returns `COMPLETED_WITH_SKIPS`, `BatchStatus` can still be `COMPLETED`; the transition `.on("COMPLETED")` will not match that custom exit code.

Check the exact code the Step actually returns:

```java
ExitStatus exitStatus = stepExecution.getExitStatus();
String exitCode = exitStatus.getExitCode();
```

Then use that exact string in `.on(...)`. If you want to route on multiple states or more complex conditions, you can use `JobExecutionDecider`; a decider returns `FlowExecutionStatus`, which is a different mechanism from a Step's `ExitStatus`.

## 9. Using JobExecutionDecider when the condition is not just an exit code

Conditional transitions by `ExitStatus` fit when a Step has finished executing and the outcome can be represented by an exit code. If the routing condition needs to query data, inspect `JobParameters`, read `JobExecutionContext`, or evaluate multiple values, `JobExecutionDecider` may be a better fit.

Example decider checking a mode parameter:

```java
public class ImportModeDecider implements JobExecutionDecider {

    @Override
    public FlowExecutionStatus decide(
            JobExecution jobExecution,
            StepExecution stepExecution) {

        String mode = jobExecution.getJobParameters().getString("mode");

        if ("FULL".equalsIgnoreCase(mode)) {
            return new FlowExecutionStatus("FULL_IMPORT");
        }

        return new FlowExecutionStatus("DELTA_IMPORT");
    }
}
```

The flow builder can route based on the status returned by the decider:

```java
return new JobBuilder("importOrdersJob", jobRepository)
        .start(importModeDecider)
            .on("FULL_IMPORT").to(fullImportStep)
        .from(importModeDecider)
            .on("DELTA_IMPORT").to(deltaImportStep)
        .end()
        .build();
```

A decider does not alter a Step's `ExitStatus`. It returns a `FlowExecutionStatus` to control the flow at the decider's position. If the outcome is already clearly represented by a Step's `ExitStatus`, a direct transition is usually simpler and easier to observe.

## 10. Where is ExitStatus produced?

A Step can receive its `ExitStatus` from execution and from listeners. Common approaches include:

- `StepExecutionListener.afterStep()` returns a custom `ExitStatus`.
- Logic inside a Tasklet or chunk can set the exit status via `StepContribution` where appropriate for the framework version's API.
- The framework sets standard exit codes based on execution results.

For example, inside a Tasklet, you can set a business outcome before returning:

```java
public class CheckInputTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        if (inputHasNoRecords()) {
            contribution.setExitStatus(
                    new ExitStatus("NO_DATA", "No input records found")
            );
        }

        return RepeatStatus.FINISHED;
    }
}
```

This is a way for a Step to publish its outcome directly inside Tasklet logic. If using a listener, keep in mind that `afterStep()` runs after Step processing and can summarize status based on final counters.

## 11. Designing exit codes by convention

Custom exit codes form the interface between Steps and the Job flow. If named arbitrarily or changed inconsistently, the flow may fail to match or become hard to maintain.

Some helpful guidelines:

- Use names describing business outcomes, such as `NO_DATA`, `COMPLETED_WITH_SKIPS`, `NEEDS_REVIEW`.
- Keep casing consistent by convention; transitions must use the exact code returned by the Step.
- Distinguish successful outcomes with warnings from genuine failures.
- Avoid using the same code with two different meanings across Steps.
- Include a wildcard fallback to handle unanticipated codes.
- Log `stepName`, `BatchStatus`, `ExitStatus.exitCode`, and description for easier investigation.
- When changing a code, update all dependent transitions and check affected Job flows.

If multiple Steps share a common set of outcome codes, you can define constants to avoid typos:

```java
public final class StepExitCodes {
    public static final String NO_DATA = "NO_DATA";
    public static final String COMPLETED_WITH_SKIPS = "COMPLETED_WITH_SKIPS";
    public static final String NEEDS_REVIEW = "NEEDS_REVIEW";

    private StepExitCodes() {
    }
}
```

Then use the same constants in listeners and the flow builder:

```java
.from(validateStep)
    .on(StepExitCodes.NEEDS_REVIEW).to(reviewStep)
```

## 12. Restart and terminal transitions

Conditional transitions not only select the next Step, they also affect the Job's ending status. `.end()`, `.fail()`, and `.stop()` produce different terminal states.

- Ending with `.end()` marks the flow completed. A completed `JobInstance` normally cannot be run again with the same identifying `JobParameters` as a new run; processing new work requires a new `JobInstance`.
- Ending with `.fail()` makes the Job fail. If the Job and Step allow restart, a subsequent run can resume from persisted metadata.
- Ending with `.stop()` marks the Job stopped. The Job can be restarted according to configuration and persisted state.

Choose the terminal transition according to business semantics. For example, `NO_DATA` might be a normal completed outcome if having no data is valid. If data is mandatory, the same outcome might require `.fail()` to prompt operational handling.

## 13. Common misconceptions

**Assuming `.on("COMPLETED")` checks BatchStatus.** Transitions match the exit code of `ExitStatus`. When a code is customized, the exact new string must be used.

**Omitting a transition for a custom exit code.** If a Step returns `NO_DATA` but the flow only has `COMPLETED` and `FAILED`, the Job has no matching branch. Declare specific codes and a fallback.

**Placing a wildcard too early or without clear intent.** A wildcard can catch outcomes that the author intended to handle separately. Prioritize specific patterns and leave the general branch as a fallback.

**Using `.end()` when intending to run the next Step.** `.end()` finishes the Job flow; use `.to(nextStep)` to move to another Step.

**Changing ExitStatus to hide errors.** `ExitStatus` does not replace `BatchStatus`. Let execution errors reflect the true status and use custom codes for appropriate business outcomes.

**Using ExitStatus for overly complex conditions.** If you need to compute or inspect multiple data sources at the routing point, consider `JobExecutionDecider`.

## 14. How to design conditional transitions

First, identify the outcomes a Step can return. Use standard exit codes when the outcome is simply success/failure; create a custom `ExitStatus` when the Job needs to distinguish business outcomes such as no data or review required. Register a listener or set the exit status in Step logic, then declare specific transitions for each code and a wildcard fallback last.

Check three aspects separately: whether `BatchStatus` accurately reflects the execution lifecycle, whether `ExitStatus.exitCode` matches the business outcome, and whether the terminal transition puts the Job into the appropriate status. When these three parts align, conditional transitions keep Job flow orchestration clear, extensible, and easy to monitor.
