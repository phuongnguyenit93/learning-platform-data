# Flows without branching

In Spring Batch, a flow describes the order in which steps are executed within a job. In a flow without branching, steps run in a fixed sequence: once the first step completes, the next step is executed, continuing in the declared order.

This flow style fits processes whose stages have sequential dependencies, such as file validation, data import, and file archiving. There is no need to decide the next step based on varying business outcomes; the path is already determined from the job configuration.

## 1. What is a sequential flow?

A flow without branching is a linear sequence of steps. Each step has a fixed position in the workflow and only one next step according to configuration.

```text
start
  |
  v
validateInput
  |
  v
importRecords
  |
  v
publishSummary
  |
  v
end
```

For example, a file processing job may consist of three stages:

1. `validateInput`: checks the file and data structure.
2. `importRecords`: reads, transforms, and writes records.
3. `archiveInput`: moves the input file to an archive directory.

Steps run in the configured order. Whether a bean is declared earlier or later in the Java file does not determine execution order; the `start()` and `next()` chain expresses the flow's order.

## 2. Declaring a sequential flow with start() and next()

The simplest approach is to use `JobBuilder.start(step)` to pick the first step and call `next(step)` for each subsequent step.

Example using the Spring Batch 5 API:

```java
@Bean
Job importFileJob(
        JobRepository jobRepository,
        Step validateInputStep,
        Step importRecordsStep,
        Step archiveInputStep) {

    return new JobBuilder("importFileJob", jobRepository)
        .start(validateInputStep)
        .next(importRecordsStep)
        .next(archiveInputStep)
        .build();
}
```

In this example:

- `start(validateInputStep)` defines the starting step.
- `next(importRecordsStep)` chains the data import step after the validation step.
- `next(archiveInputStep)` chains the archiving step after data import completes.
- `build()` creates the job with the declared execution order.

`next()` does not mean running the next step immediately inside the same Java method. It defines the job structure; when the job is launched, Spring Batch orchestrates each step according to that sequence.

## 3. Declaring individual Steps

Each step should be a unit of work with a clear responsibility. Example:

```java
@Bean
Step validateInputStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet validationTasklet) {

    return new StepBuilder("validateInput", jobRepository)
        .tasklet(validationTasklet, transactionManager)
        .build();
}

@Bean
Step importRecordsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<InputRow> reader,
        ItemProcessor<InputRow, Record> processor,
        ItemWriter<Record> writer) {

    return new StepBuilder("importRecords", jobRepository)
        .<InputRow, Record>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
}

@Bean
Step archiveInputStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet archiveTasklet) {

    return new StepBuilder("archiveInput", jobRepository)
        .tasklet(archiveTasklet, transactionManager)
        .build();
}
```

`validateInputStep` and `archiveInputStep` are tasklet steps, while `importRecordsStep` is a chunk-oriented step. A job can mix both step types within the same sequential flow.

## 4. Execution order and default transition conditions

With a sequential step chain, Spring Batch executes the first step and then moves to the next step when the preceding step completes normally according to the defined flow.

```text
validateInput
     |
     +-- completed successfully --> importRecords
                                   |
                                   +-- completed successfully --> archiveInput
                                                                    |
                                                                    v
                                                                   end
```

A linear flow has no declared alternate path for failure outcomes. If a step fails, the job typically stops at that step and downstream steps do not run in that `JobExecution`.

For example, if `importRecords` fails then `archiveInput` does not run. This avoids archiving the file as if the import had completed while data was not fully written.

This is a key characteristic of a non-branching flow: the same sequence of steps is used for every run, while errors are handled via exceptions, retry, skip, or restart mechanisms at the step/job level.

## 5. Extracting a separate Flow for reuse

When a sequential group of steps can be used across multiple jobs, you can define it as a separate `Flow` using `FlowBuilder`.

```java
@Bean
Flow fileImportFlow(
        Step validateInputStep,
        Step importRecordsStep,
        Step archiveInputStep) {

    return new FlowBuilder<SimpleFlow>("fileImportFlow")
        .start(validateInputStep)
        .next(importRecordsStep)
        .next(archiveInputStep)
        .build();
}
```

A job can use this flow as a building block:

```java
@Bean
Job importFileJob(
        JobRepository jobRepository,
        Flow fileImportFlow) {

    return new JobBuilder("importFileJob", jobRepository)
        .start(fileImportFlow)
        .end()
        .build();
}
```

A `Flow` groups a sequence of steps into a named unit. This makes the high-level job easier to read when there are multiple work groups, while also allowing a flow to be reused across different jobs. If there are only a few steps and no reuse is needed, declaring directly with `start()` and `next()` is usually easier to follow.

## 6. Passing data between steps

Steps in a sequential flow may need to share information. Spring Batch provides `ExecutionContext` at the job level and step level to store appropriate state.

- Job `ExecutionContext` is for data that needs to be shared across steps within the same `JobExecution`.
- Step `ExecutionContext` is for a single step's private state, such as reader position or checkpoints.

For example, the validation step saves the confirmed filename into the job context for the import step to use:

```java
@Component
public class ValidateInputTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        String fileName = "orders.csv";
        ExecutionContext jobContext =
            contribution.getStepExecution()
                .getJobExecution()
                .getExecutionContext();

        jobContext.putString("validatedFileName", fileName);
        return RepeatStatus.FINISHED;
    }
}
```

The next step can read the value from the corresponding `JobExecution`, for instance through a `StepExecution` injected via a listener or an appropriately scoped component. Do not use static variables or mutable singletons to pass data between steps because multiple job instances may run concurrently.

Store only small, stable, serializable data in `ExecutionContext`. Do not store streams, connections, service beans, or open runtime resources.

## 7. Sequential flow and restart

When a job fails mid-sequence, Spring Batch persists execution history in `JobRepository`. If the `JobInstance` is restartable, the next run continues according to each step's restart rules.

Example first run:

```text
Execution #1
  validateInput  -> COMPLETED
  importRecords  -> FAILED
  archiveInput   -> not run yet
```

When restarting the same `JobInstance` with the same identifying `JobParameters`, Spring Batch normally skips already completed steps and re-runs the failed step. Once `importRecords` completes, the flow continues to `archiveInput`.

```text
Execution #2 (restart same JobInstance)
  validateInput  -> already completed, skipped by default
  importRecords  -> re-run per checkpoint/restart policy
  archiveInput   -> runs after importRecords completes
```

A completed step can be configured to run again on restart using `allowStartIfComplete(true)`. Use this option only when re-running the step is necessary and safe, especially if the step produces side effects.

Restarting is not the same as creating a new `JobInstance`. When you need to process a new business dataset, use new identifying parameters. When you need to resume unfinished work, keep the same identifying parameters so Spring Batch finds the old `JobInstance`.

## 8. Error handling in non-branching flows

A linear flow does not declare dedicated recovery branches. If a step errors, you can handle the cause at the step level with retry/skip or restart the job after fixing the issue.

Example of a chunk step with retry for transient errors and skip for invalid data:

```java
return new StepBuilder("importRecords", jobRepository)
    .<InputRow, Record>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .retry(TransientDataAccessException.class)
    .retryLimit(3)
    .skip(InvalidInputException.class)
    .skipLimit(20)
    .build();
```

These policies determine whether the step can continue processing within the same execution. If an exception is not retried/skipped or exceeds its limit, the step fails and the sequential flow stops there.

When you need a dedicated error-handling branch—such as moving an invalid file to a reject directory and ending the job with a different status—the flow must be extended with conditional transitions. That is a different design style from a flow without branching.

## 9. Distinguishing sequential flow from conditional flow

Sequential flow fits when the next step is always fixed. Conditional flow fits when a step's outcome or a runtime decision changes the path.

| Requirement | Declaration approach |
|---|---|
| A then B then C on every run | `start(A).next(B).next(C)` |
| If A completes run B; if data is invalid run C | Transitions with `on(...)` and `to(...)` |
| Choose step based on `JobParameters` or runtime data | `JobExecutionDecider` |
| Group a reusable sequence of steps | Define a separate `Flow` |

There is no need to create a conditional flow if every run follows the same order and errors simply need to stop the job. Adding unnecessary branches makes configuration harder to read and test.

## 10. Sequential flow is not a Tasklet loop

`next(step)` moves from one step to the next step in the job flow. `RepeatStatus.CONTINUABLE` instead instructs Spring Batch to invoke `Tasklet.execute()` again within the same tasklet step.

| Mechanism | Loop/transition scope |
|---|---|
| `.next(nextStep)` | Moves to another step in the flow |
| `RepeatStatus.CONTINUABLE` | Re-invokes the same tasklet within the same `StepExecution` |
| Chunk-oriented processing | Loops over chunks until the reader runs out of data |

Do not use `CONTINUABLE` as a replacement for `next()`, and do not create a separate step for each item loop. Choose the mechanism based on the unit of work: a new step, a tasklet iteration, or a chunk of data.

## 11. Naming and organizing steps in a sequence

Step names should describe the stage's responsibility and stay stable across deployments as long as the job definition has not changed.

Examples of meaningful names:

- `validateInput`: validates input.
- `importRecords`: imports records.
- `archiveInput`: archives source files.
- `publishSummary`: publishes results.

Avoid generic names like `step1`, `step2`, or names depending on run dates. Step names are stored in metadata and affect how Spring Batch recognizes step history on restart.

When extracting a sequence of steps into a separate flow, keep step names stable so metadata from older `JobInstance`s can still be matched. If making major changes to flow structure or step responsibilities, plan how to handle in-flight instances.

## 12. Testing non-branching flows

Integration tests should verify execution order and behavior when a step fails.

Key scenarios:

1. All steps complete: verify order is A, B, C and `JobExecution` completes.
2. First step fails: verify the second and third steps do not run.
3. Middle step fails: verify the last step does not run in that execution.
4. Restart after failure: verify completed steps follow the restart policy and the flow resumes at the right position.
5. Multiple concurrent `JobInstance`s: verify state between runs is not unintentionally shared.
6. Step with retry/skip: verify errors are handled per policy before the flow proceeds or stops.

You can use `JobLauncherTestUtils` or the corresponding test support for your project's Spring Batch version to launch the job and inspect `JobExecution`, `StepExecution`, and step order. Tests should use an appropriate `JobRepository` to verify metadata and restarts.

## 13. Common mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Thinking bean order determines execution order | Job may run in an unexpected order | Declare order with `start()` and `next()` |
| Missing start step or wrong `next` declaration | Flow misses stages or deviates from workflow | Clearly define the first step and each subsequent step |
| Expecting later steps to run even if an earlier step failed | Job stops at the failing step | Configure retry/skip or conditional transitions if business requires it |
| Using `CONTINUABLE` to switch steps | Tasklet is re-invoked instead of advancing flow | Use `.next(step)` |
| Using static variables to pass data between steps | Concurrent job runs may overwrite state | Use Job `ExecutionContext` or an appropriate data-passing mechanism |
| Renaming Step names arbitrarily | Old metadata no longer matches on restart | Keep names stable or plan migration |
| Creating a separate Flow for a very short non-reused chain | Configuration is more complex than needed | Declare directly in `JobBuilder` |

## Conclusion

A flow without branching represents a sequence of steps in a fixed order. In Spring Batch 5, use `start(step)` to choose the starting point and `next(step)` to declare each subsequent step. Spring Batch executes that chain when the job is launched; a failed step normally stops the flow at the point of failure.

When a group of steps needs to be reused, you can package them into a separate `Flow`. Keep step responsibilities and names clear, pass data between steps via `ExecutionContext` when needed, and test both the happy path and restarts. Only when the next step depends on outcomes or runtime decisions do you need a conditional flow.
