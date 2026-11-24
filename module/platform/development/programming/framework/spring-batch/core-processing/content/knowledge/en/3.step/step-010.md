# Step Flow and Transition Conditions in Spring Batch

A Spring Batch job usually consists of multiple steps. The steps can run one after another in a fixed order, but in practice the processing flow also depends on the result of each step, the input data, or a business condition. Spring Batch represents how steps are linked together with a **flow** and uses **transitions** to decide the next step.

Understanding step flow helps you design jobs that have branches for success, failure, empty data, or special situations. Instead of writing all the orchestration logic inside one large step, an application can divide the workflow into small steps and declare the paths between them explicitly.

## 1. What Is a Step Flow?

A `Step` is a unit of processing in a job, such as reading and writing data by chunk, running a tasklet, or performing a distinct piece of business work. A **flow** describes the order and the branches the job can take when executing those steps.

You can picture a flow as a directed graph:

- Each step is a processing state.
- Each transition is an edge connecting the current step to the next step or to an ending state.
- The transition's condition decides which edge is chosen based on the step's result or on a decision from an orchestration component.

A simple job can run in sequence:

```text
Start
  |
  v
ValidateStep
  |
  v
ImportStep
  |
  v
ReportStep
  |
  v
End
```

If every step always runs in a fixed order, you can declare it with `start()` and `next()`:

```java
@Bean
Job importJob(JobRepository jobRepository,
              Step validateStep,
              Step importStep,
              Step reportStep) {
    return new JobBuilder("importJob", jobRepository)
        .start(validateStep)
        .next(importStep)
        .next(reportStep)
        .build();
}
```

`start()` chooses the first step of the job. Each call to `next()` adds the next step to the chain. This style suits a linear flow, is easy to read, and does not require declaring each branch. When you need to branch based on results, you should declare explicit transitions.

## 2. ExitStatus and Transition Conditions

Spring Batch uses a step's `ExitStatus` to match transition conditions. `ExitStatus` contains an exit code and a description of the ending result. The common exit codes are `COMPLETED` and `FAILED`, but an application can create its own exit codes to represent business results.

The condition in `.on("...")` is matched against the **exit code of the `ExitStatus`**, not directly against `BatchStatus`. The two concepts are related but different:

| Concept | Role |
| --- | --- |
| `BatchStatus` | The lifecycle status managed by the framework, for example `COMPLETED`, `FAILED`, `STOPPED`. |
| `ExitStatus` | The code and description used to express the ending result of a step or job; can carry a custom code. |
| Transition pattern | The pattern used to match against the exit code in order to choose the next path. |

For example, a step has `BatchStatus.COMPLETED` but its `ExitStatus` is `COMPLETED WITH SKIPS`. The transition `.on("COMPLETED*")` can match this exit code, while `.on("FAILED")` does not match.

Normally, if a step ends successfully, the default exit code is `COMPLETED`; if the step fails because of an unhandled exception, the exit code is usually `FAILED`. However, a listener or processing logic can change the `ExitStatus`, so you need to understand the actual value the step returns when designing transitions.

## 3. Declaring Transitions with on() and to()

In the flow builder, `.on(pattern)` specifies the exit code pattern to match; `.to(target)` specifies the next step or state. You can use `.from(step)` to declare additional transitions originating from a step that already appears in the flow.

For example, after the data validation step:

- If validation succeeds, continue importing the data.
- If validation fails, move to a step that records the error.

```java
@Bean
Job importJob(JobRepository jobRepository,
              Step validateStep,
              Step importStep,
              Step validationErrorStep) {
    return new JobBuilder("importJob", jobRepository)
        .start(validateStep)
            .on("COMPLETED").to(importStep)
        .from(validateStep)
            .on("FAILED").to(validationErrorStep)
        .from(importStep)
            .on("*").end()
        .from(validationErrorStep)
            .on("*").fail()
        .end()
        .build();
}
```

The flow can be pictured as follows:

```text
                 +--------------------+
                 |                    |
                 v                    v
          COMPLETED                 FAILED
                 |                    |
                 v                    v
           ImportStep        ValidationErrorStep
                 |                    |
                 v                    v
                End                  Fail
```

Here:

- `.start(validateStep)` determines the first step.
- `.on("COMPLETED").to(importStep)` moves to `importStep` when the exit code of `validateStep` matches `COMPLETED`.
- `.from(validateStep)` declares another branch that also originates from `validateStep`.
- `.on("FAILED").to(validationErrorStep)` moves to the error-handling step if the validation step fails.
- `.end()` and `.fail()` determine the ending state of the job, explained in a later section.

In the flow configuration, you need to ensure that every result that can occur has an appropriate path. If no transition matches the exit code of the current state, the flow cannot determine the next step and the job may end with an orchestration error.

## 4. Patterns That Match Exit Codes

A transition can use a specific pattern or a wildcard. Spring Batch supports these common patterns:

| Pattern | Meaning |
| --- | --- |
| `COMPLETED` | Matches the exit code `COMPLETED` exactly. |
| `FAILED` | Matches the exit code `FAILED` exactly. |
| `COMPLETED*` | Matches exit codes that start with `COMPLETED`, such as `COMPLETED WITH SKIPS`. |
| `*` | Matches every exit code. |

For example, if a step can end with `COMPLETED`, `COMPLETED WITH SKIPS`, or `FAILED`, you can declare:

```java
.start(importStep)
    .on("COMPLETED WITH SKIPS").to(reviewStep)
.from(importStep)
    .on("COMPLETED").to(reportStep)
.from(importStep)
    .on("FAILED").to(errorStep)
```

When you use a broad pattern such as `*`, place it after the more specific conditions so that the general branch does not shadow a branch that needs its own handling. For example, if you declare `*` for `importStep` before the `FAILED` and `COMPLETED` patterns, the general branch may capture results that were meant to follow their own path. Read and order the transitions so that special cases are handled explicitly before the fallback.

A fallback transition is usually useful when you want every unclassified result to go to a common handling step:

```java
.from(importStep)
    .on("FAILED").to(errorStep)
.from(importStep)
    .on("*").to(reviewStep)
```

A fallback should not be used to hide design mistakes. If a new exit code appears, you need to determine whether it is a valid result and where it should go.

## 5. Ending the Flow: end(), fail(), and stop()

A transition can lead to another step or to a job ending state. The common ending operations have different meanings:

| Operation | Job result | Operational meaning |
| --- | --- | --- |
| `.end()` | `BatchStatus.COMPLETED` | Marks the job as completed. The instance is considered complete and cannot be restarted like an unfinished job. |
| `.fail()` | `BatchStatus.FAILED` | Marks the job as failed. If the job is configured as restartable and meets the restart conditions, the same instance can be run again. |
| `.stop()` | `BatchStatus.STOPPED` | Stops the job in a controlled state; continuing is done according to the flow's restart rules. |
| `.stopAndRestart(step)` | `BatchStatus.STOPPED` | Stops the job and designates a step as the starting point on restart. |

For example, a step detects that there is no new data. This can be a valid business result, so the job should still be marked as completed:

```java
.start(checkDataStep)
    .on("NO_DATA").end()
.from(checkDataStep)
    .on("DATA_FOUND").to(processStep)
```

Conversely, if the data-processing step fails and needs to be re-run after the cause is fixed, you can move to `.fail()`:

```java
.start(processStep)
    .on("FAILED").fail()
.from(processStep)
    .on("COMPLETED").end()
```

`end()` is a decision about the job's completed status, not simply meaning “there is no next step.” For example, a step can return the business exit code `NO_DATA`; if the job's transition leads to `.end()`, the job still ends with a completed status. Because the job instance has completed, processing a new business unit requires appropriate identifying parameters to create a new `JobInstance`.

When you need to stop in order to continue from a defined position, you can use `.stopAndRestart(restartStep)`. Choose the restart point based on the committed data and on how the steps save their checkpoints. Restart also depends on the metadata, the execution state, and the recoverability of the data reading/writing components.

## 6. Creating Custom Exit Codes for a Step

Flow branches are not limited to `COMPLETED` and `FAILED`. An application can set its own exit codes to express results such as `COMPLETED WITH SKIPS`, `NO_DATA`, `VALIDATION_ERROR`, or `REQUIRES_REVIEW`.

A commonly used approach is to implement a `StepExecutionListener` and return a custom `ExitStatus` in `afterStep()`:

```java
public class SkipStatusListener implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getSkipCount() > 0) {
            return new ExitStatus("COMPLETED WITH SKIPS");
        }
        return null;
    }
}
```

The flow can then route the runs that have skips to a review step:

```java
.start(importStep)
    .on("COMPLETED WITH SKIPS").to(reviewStep)
.from(importStep)
    .on("COMPLETED").to(reportStep)
```

In the listener example, it returns `null` when there is no need to change the existing exit status. When there are skips, the listener returns a custom code so the flow can recognize it and choose the appropriate branch.

Choose exit codes with stable meanings, agree on conventions across steps, and avoid strings that are hard to tell apart. Exit codes are part of the job orchestration contract; when you change their names or meanings, review the transitions that depend on those codes.

## 7. Using JobExecutionDecider for Business Conditions

A transition based on `ExitStatus` is suitable when the decision depends on the result of the step that just ran. However, some decisions need to consider other information, for example job parameters, data stored in the `ExecutionContext`, the number of records, or a separately computed business condition. In that case, you can use `JobExecutionDecider`.

`JobExecutionDecider` receives the `JobExecution` and the `StepExecution` (if any), and then returns a `FlowExecutionStatus`. The flow uses this value to choose a transition.

For example, a job receives a `mode` parameter to decide whether to run normal processing or a re-run:

```java
@Bean
JobExecutionDecider modeDecider() {
    return (jobExecution, stepExecution) -> {
        String mode = jobExecution.getJobParameters().getString("mode");
        if ("REPROCESS".equals(mode)) {
            return new FlowExecutionStatus("REPROCESS");
        }
        return new FlowExecutionStatus("NORMAL");
    };
}
```

You can use the decider in the job flow:

```java
@Bean
Job conditionalJob(JobRepository jobRepository,
                   Step prepareStep,
                   Step reprocessStep,
                   Step normalStep,
                   JobExecutionDecider modeDecider) {
    return new JobBuilder("conditionalJob", jobRepository)
        .start(prepareStep)
        .next(modeDecider)
            .on("REPROCESS").to(reprocessStep)
        .from(modeDecider)
            .on("NORMAL").to(normalStep)
        .from(reprocessStep)
            .on("*").end()
        .from(normalStep)
            .on("*").end()
        .end()
        .build();
}
```

In this example, `modeDecider` produces an independent orchestration result. When it returns `REPROCESS`, the flow moves to `reprocessStep`; when it returns `NORMAL`, the flow moves to `normalStep`.

The decider's `FlowExecutionStatus` and the step's `ExitStatus` both provide codes for the flow to match against, but they come from two different sources. A decider is not a data-processing step; it is a component that decides the path. Use a decider when the condition truly needs its own orchestration logic, instead of stuffing many business branches into one step.

## 8. Organizing a Flow into Reusable Components

When a job has many steps, or many jobs share the same processing chain, you can extract the flow into a separate bean. A `Flow` groups steps and transitions into a named unit, which is then used as part of a job.

An example of creating an order-processing flow:

```java
@Bean
Flow orderProcessingFlow(Step validateStep,
                        Step importStep,
                        Step reportStep) {
    return new FlowBuilder<SimpleFlow>("orderProcessingFlow")
        .start(validateStep)
        .next(importStep)
        .next(reportStep)
        .build();
}
```

A job can start from this flow:

```java
@Bean
Job orderJob(JobRepository jobRepository,
             Flow orderProcessingFlow) {
    return new JobBuilder("orderJob", jobRepository)
        .start(orderProcessingFlow)
        .end()
        .build();
}
```

Extracting a flow makes the job configuration easier to read, allows reuse of a processing chain, and reduces duplication when multiple jobs share a common sub-process. For a flow with branches, the transitions are declared in the flow bean; the job only needs to combine the flow with other components.

## 9. Restart and the Impact of Transitions

The flow decides the next step within a single run, but it also affects how the job can be restarted. Spring Batch stores the `JobExecution`, `StepExecution`, status, and `ExecutionContext` in the `JobRepository`. When a job fails or stops, the next run with the same `JobInstance` relies on the metadata and the flow configuration to determine which part of the work to continue.

Some points to note:

- If a transition ends with `.end()`, the job is marked as completed. The same instance cannot be restarted like a failed job.
- If a transition ends with `.fail()`, the job has a failed status and can be restarted if the job allows restart, the related step meets the conditions, and the metadata is valid.
- If the job stops with `.stop()` or `.stopAndRestart(...)`, you need to understand clearly the flow's resume point and the committed data.
- A completed step can be skipped on restart by default, unless the flow or configuration allows it to be executed again in that situation.
- Readers, writers, and external operations must be designed to recover safely; correct transitions do not by themselves guarantee that side effects are not repeated.

For example, if `importStep` committed some chunks and then failed, a restart can continue from the checkpoint if the reader supports saving and restoring state. If the writer calls an external API, you need an idempotency mechanism or a way to recognize records that have already been written to avoid producing duplicate results when a chunk is executed again.

Do not use `.end()` merely to make a job appear successful when there are unhandled technical errors. End successfully only when that branch represents an accepted business result, such as no new data or having moved the error records to a review queue through the proper process.

## 10. Common Mistakes When Declaring a Flow

**Using the wrong code to match:** `.on("COMPLETED")` matches the exit code, not a Java status name or a `BatchStatus` passed directly. If a listener changes the exit code, the transition needs to match the new code or use an appropriate pattern.

**Missing a branch for an exit code:** if a step can return multiple exit codes but the flow declares only one case, another result may not find a transition. List the results that can occur and decide on the fallback branch explicitly.

**A wildcard shadowing a specific branch:** a `*` transition that is too broad can capture results that need their own handling. Declare the specific patterns before the fallback and keep the general branch's purpose clear.

**Confusing `.end()` with `.fail()`:** the two operations produce different job statuses and affect restartability. Choose the ending status based on the business meaning and the operations plan.

**Putting too much logic in one step:** if a step both processes data and decides the entire business flow itself, the job is hard to observe and test. You can split it into small steps and use exit codes or a decider to express the decisions.

**Not testing the restart flow:** a flow that runs correctly from the start does not necessarily restart correctly after an error. Test an error scenario in the middle of the job, and confirm the metadata, the checkpoint, and that the steps are executed again as expected.

## 11. How to Design Step Flow in a Real Job

When designing a flow, first list the business steps and the possible results of each step. For each result, decide whether the job should continue, move to another processing step, end successfully, fail, or stop to wait for a next action.

Then choose the mechanism for expressing the conditions:

- Use `next()` for a linear chain of steps.
- Use `.on(...).to(...)` when you need to branch by the step's exit code.
- Use custom exit codes when a step needs to report a specific business result to the flow.
- Use `JobExecutionDecider` when the decision depends on data or conditions outside the step's status.
- Extract into a `Flow` when you need to encapsulate and reuse a sub-process.

Finally, define the ending states and restart behavior clearly. Verify that every exit code that can appear has an appropriate transition, that the ending branches carry the right operational meaning, and that the checkpoints are sufficient to continue after an incident. For branches that affect external systems, design write operations that can be handled safely when executed again.

Step flow helps a Spring Batch job express its processing workflow as steps and paths that can be observed. When you combine `ExitStatus`, transition patterns, `JobExecutionDecider`, and ending states correctly, an application can orchestrate both linear flows and multi-branch business flows clearly and with good operability.
