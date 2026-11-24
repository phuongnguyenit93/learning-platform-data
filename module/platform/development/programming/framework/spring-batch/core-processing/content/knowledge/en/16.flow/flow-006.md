# Success-conditional flows in Spring Batch

A Spring Batch Job typically consists of multiple Steps. In a simple workflow, Steps run one after another. In practice, however, the next Step should run only when the previous Step meets a specific condition. For example, publish a file only after data import succeeds; reconcile only after data writing completes; or route to an error-handling branch when input validation fails.

Spring Batch supports **conditional flows** to steer a Job's path based on execution outcomes. For success-conditional flows, applications usually check the Step's **ExitStatus**. If the outcome is COMPLETED, the Job moves to the next Step. If the outcome is FAILED or an unacceptable status, the Job can stop or route to an appropriate handling branch.

This lesson explains how to configure flows that proceed only when a Step succeeds, distinguish BatchStatus from ExitStatus, handle custom outcomes, use wildcards and JobExecutionDecider, as well as the impact of flows on restarts and testing.

## 1. What is a Flow?

A Flow describes the order and transition conditions between Steps in a Job. A flow can run sequentially, branch, terminate, or stop depending on Step outcomes and business decisions.

Example of a data import Job:

~~~mermaid
flowchart TD
    A["validateInputStep"] -->|COMPLETED| B["importDataStep"]
    A -->|FAILED or other status| X["Job FAILED"]
    B -->|COMPLETED| C["publishOutputStep"]
    B -->|FAILED or other status| X
    C -->|COMPLETED| D["Job COMPLETED"]
    C -->|FAILED or other status| X
~~~

In this flow:

- Only when input validation succeeds does the data import Step run.
- Only when data import succeeds does the publish Step run.
- If any Step fails to return an accepted success outcome, the Job transitions to a failed state.

Flows place conditions at the boundaries between stages. Each Step remains responsible for executing a specific piece of work; the flow decides which stage runs next.

## 2. Distinguishing BatchStatus and ExitStatus

This is the most important point when configuring conditional flows.

**BatchStatus** represents the execution lifecycle status of a JobExecution or StepExecution. Common values:

| BatchStatus | Meaning |
|---|---|
| STARTING | Preparing to start |
| STARTED | Currently executing |
| STOPPING | In the process of stopping |
| STOPPED | Stopped |
| COMPLETED | Execution completed |
| FAILED | Execution failed |
| ABANDONED | Execution marked not to continue |
| UNKNOWN | Reliable status could not be determined |

**ExitStatus** describes the exit outcome of a Step and is used by the Job flow to match transitions. Common values are COMPLETED, FAILED, STOPPED, NOOP, and custom codes defined by the application.

When writing:

~~~java
.on("COMPLETED").to(nextStep)
~~~

the condition COMPLETED is matched against the **ExitStatus exit code** of the current flow state, usually the Step that just ran. It is not a direct comparison expression against the BatchStatus enum.

In the normal case, a successful Step has BatchStatus COMPLETED and ExitStatus COMPLETED. However, a listener or application logic can produce a custom ExitStatus while BatchStatus remains COMPLETED.

For example, a Step that finishes processing but had some skipped items can be assigned ExitStatus COMPLETED_WITH_SKIPS. The flow can then split out a separate branch to handle outcomes with skips.

### Why understand both statuses?

- BatchStatus tells whether the execution succeeded, failed, stopped, or is in another state.
- ExitStatus provides the outcome code for the Job to select a transition.
- A Step can complete technically yet have a business outcome requiring separate handling.
- Flows behave correctly only when ExitStatus codes are designed consistently.

Do not use the string COMPLETED in a flow and assume all other BatchStatus values are automatically handled as desired. Identify all ExitStatus values that may occur and declare corresponding transitions.

## 3. Sequential flow with next()

If a Job only needs to run Steps one after another when the previous Step completes normally, you can use next():

~~~java
@Bean
Job importJob(
        JobRepository jobRepository,
        Step validateStep,
        Step importStep,
        Step publishStep) {

    return new JobBuilder("importJob", jobRepository)
        .start(validateStep)
        .next(importStep)
        .next(publishStep)
        .build();
}
~~~

This is a concise declaration for a linear flow. The framework orchestrates Steps in the declared order; if a Step fails, the Job normally does not continue along a success path.

However, next() does not explicitly express branches by ExitStatus. When you need to strictly enforce that only COMPLETED advances, or when you need to handle different statuses, use conditional transitions with on(), to(), fail(), end(), or stop().

## 4. Advancing to the next Step only when the outcome is COMPLETED

Success-conditional flow configuration uses on("COMPLETED").to(...). To ensure other outcomes do not accidentally proceed, declare a fallback branch.

Example Job with three Steps: validate, import, and publish:

~~~java
@Bean
Job importJob(
        JobRepository jobRepository,
        Step validateStep,
        Step importStep,
        Step publishStep) {

    return new JobBuilder("importJob", jobRepository)
        .start(validateStep)
            .on("COMPLETED").to(importStep)
        .from(validateStep)
            .on("*").fail()

        .from(importStep)
            .on("COMPLETED").to(publishStep)
        .from(importStep)
            .on("*").fail()

        .from(publishStep)
            .on("COMPLETED").end()
        .from(publishStep)
            .on("*").fail()

        .end()
        .build();
}
~~~

Meaning:

1. The Job starts with validateStep.
2. If the ExitStatus of validateStep is COMPLETED, the flow transitions to importStep.
3. If the outcome does not match the success branch, on("*").fail() ends the Job with a failed status.
4. importStep runs only when validateStep returns an accepted success outcome.
5. publishStep runs only when importStep also returns COMPLETED.
6. When publishStep succeeds, the flow ends normally.

on("*") is a wildcard used as a fallback branch. In this example, any ExitStatus not matching COMPLETED is treated as unsuccessful. This is a fail-closed design: only permitted outcomes are allowed to advance.

If the application has valid custom ExitStatus codes, declare those branches before the fallback instead of letting the wildcard mark them all as failed.

## 5. Syntax of on(), to(), and from()

Conditional flows commonly use these methods:

| Method | Role |
|---|---|
| start(step) | Selects the first Step |
| on(pattern) | Selects a transition by ExitStatus pattern |
| to(step) | Moves to the next Step or state |
| from(step) | Declares an additional transition originating from the specified Step |
| end() | Ends the Job flow with a completed status |
| fail() | Ends the Job with a failed status |
| stop() | Ends the flow with a stopped status |

A Step can have multiple transitions:

~~~java
.start(validateStep)
    .on("COMPLETED").to(importStep)
.from(validateStep)
    .on("FAILED").to(rejectStep)
.from(validateStep)
    .on("*").fail()
~~~

In this example:

- COMPLETED transitions to the data import branch.
- FAILED transitions to the rejected-input handling branch.
- Any remaining ExitStatus hits the fallback and fails the Job.

from(validateStep) indicates that the subsequent transitions still originate from validateStep's outcome. It does not re-run the Step; it adds routing rules for the same state.

### Pattern order and specificity

Declare specific transitions such as COMPLETED, FAILED, or custom codes before the wildcard *. That makes it easy for readers to see that special outcomes are handled first while the wildcard serves as a fallback.

If a Step has multiple valid ExitStatus codes, declare each code explicitly or use intentional patterns. Do not rely on a broad wildcard without understanding what statuses can appear.

## 6. Allowing only accepted success statuses

In production systems, not every outcome meaning "finished" implies permission to run the next Step.

Examples:

- COMPLETED: processed successfully.
- COMPLETED_WITH_SKIPS: finished processing but some items were skipped.
- NO_DATA: no input data.
- VALIDATION_WARNING: input had warnings requiring review.
- FAILED: processing failed.

You can design the flow to accept certain statuses and route other statuses to dedicated branches:

~~~java
return new JobBuilder("customerImportJob", jobRepository)
    .start(importStep)
        .on("COMPLETED").to(publishStep)
    .from(importStep)
        .on("COMPLETED_WITH_SKIPS").to(reviewStep)
    .from(importStep)
        .on("NO_DATA").to(noDataStep)
    .from(importStep)
        .on("FAILED").to(errorStep)
    .from(importStep)
        .on("*").fail()

    .from(publishStep)
        .on("COMPLETED").end()
    .from(publishStep)
        .on("*").fail()

    .from(reviewStep)
        .on("COMPLETED").end()
    .from(reviewStep)
        .on("*").fail()

    .from(noDataStep)
        .on("COMPLETED").end()
    .from(noDataStep)
        .on("*").fail()

    .from(errorStep)
        .on("*").fail()
    .end()
    .build();
~~~

This is an example of flow policy:

- Only completely successful data is published.
- Data with skips must go through a review step.
- No-data cases are routed to a dedicated branch.
- Errors are recorded and the Job ends as failed.

In this example, when reviewStep and noDataStep complete, the Job ends via flow end(). If business rules require the Job to ultimately report FAILED when there are skips or no data, use the appropriate terminal transition instead of end().

## 7. Creating a custom ExitStatus for business conditions

A Step may complete technically yet need to return a specific outcome code to the flow. You can use StepExecutionListener to supply an ExitStatus.

For example, if the Step has skipped items, return the code COMPLETED_WITH_SKIPS:

~~~java
@Bean
StepExecutionListener importResultListener() {
    return new StepExecutionListener() {

        @Override
        public void beforeStep(StepExecution stepExecution) {
            // No pre-step action needed in this example.
        }

        @Override
        public ExitStatus afterStep(StepExecution stepExecution) {
            if (stepExecution.getSkipCount() > 0) {
                return new ExitStatus("COMPLETED_WITH_SKIPS");
            }

            return null;
        }
    };
}
~~~

Registering the listener:

~~~java
@Bean
Step importStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<InputRecord> reader,
        ItemProcessor<InputRecord, OutputRecord> processor,
        ItemWriter<OutputRecord> writer,
        StepExecutionListener importResultListener) {

    return new StepBuilder("importStep", jobRepository)
        .<InputRecord, OutputRecord>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .listener(importResultListener)
        .build();
}
~~~

The flow can branch by the custom code:

~~~java
.start(importStep)
    .on("COMPLETED").to(publishStep)
.from(importStep)
    .on("COMPLETED_WITH_SKIPS").to(reviewStep)
.from(importStep)
    .on("*").fail()
~~~

The listener translates runtime information into an ExitStatus meaningful to the flow. BatchStatus continues to reflect the execution lifecycle; ExitStatus is used to control branching.

### Choosing stable ExitStatus codes

Custom codes should:

- Have clear, meaningful names standardized across the application.
- Not depend on log message wording or exception text.
- Be handled in the Job flow.
- Have documentation describing their meaning and expected terminal state.
- Not change arbitrarily across versions while Job flows and operational tools still depend on them.

Do not use full error messages as an ExitStatus. Use short, stable codes and store error details in logs or appropriate metadata.

## 8. Using wildcards to handle other outcomes

Spring Batch supports patterns when matching ExitStatus. Common examples:

| Pattern | Meaning |
|---|---|
| COMPLETED | Matches code COMPLETED |
| FAILED | Matches code FAILED |
| * | Matches any code |
| COMPLETED* | Matches codes starting with COMPLETED |

Example:

~~~java
.start(importStep)
    .on("COMPLETED*").to(publishStep)
.from(importStep)
    .on("*").fail()
~~~

The COMPLETED* pattern can be useful if the application intentionally uses a family of codes such as COMPLETED_WITH_SKIPS. However, use it only when every code with that prefix is genuinely acceptable for publishing. If COMPLETED_WITH_WARNINGS requires review, declare it explicitly instead of letting a wildcard send it straight to publish.

### Fallback as a safety guardrail

If you declare only:

~~~java
.start(validateStep)
    .on("COMPLETED").to(importStep)
.end()
~~~

other ExitStatus values may lack a matching transition. The flow may end with a missing-transition error instead of the business behavior the application intended.

For critical Jobs, declare an explicit fallback:

~~~java
.start(validateStep)
    .on("COMPLETED").to(importStep)
.from(validateStep)
    .on("*").fail()
.end()
~~~

This makes it explicit that only successful outcomes are permitted to continue.

## 9. Distinguishing end(), fail(), and stop()

The three terminal transitions have different meanings:

| Transition | Job ending status | Meaning |
|---|---|---|
| end() | COMPLETED | Ends the flow successfully |
| fail() | FAILED | Ends the flow with an error |
| stop() | STOPPED | Ends the flow in a stopped state |

### end()

end() ends the Job with BatchStatus COMPLETED. It is normally used when the flow has finished processing and no further Steps need to run.

Be careful: if a Step returns ExitStatus FAILED yet its transition is configured to go to end(), the Job can be marked completed according to the terminal end() state. This should be done only when the application genuinely intends to treat that error as handled and the Job as complete from a business standpoint.

### fail()

fail() ends the Job with BatchStatus FAILED. Use it when the outcome does not satisfy the conditions to consider the Job successful.

This is the right choice for the fallback in a flow that allows only COMPLETED to advance.

### stop()

stop() ends the Job with BatchStatus STOPPED. This status fits a workflow that needs a controlled stop and may be restarted according to Job rules.

Do not use stop() as a substitute for fail() when data is faulty. Intentional stopping and failure are two distinct operational states.

### Builder-closing end() vs transition end()

In the DSL, end() can appear at the bottom of the configuration to finish the flow declaration before build(). Separately, on("...").end() is a transition leading to a completed Job end state.

Distinguish these two positions when reading configuration. One closes the flow builder; the other defines the terminal outcome for a branch.

## 10. When success condition depends on data: JobExecutionDecider

ExitStatus fits when the branching condition is already captured in a Step's outcome. If the decision depends on data or business logic that needs separate evaluation, you can use JobExecutionDecider.

A Decider receives the current JobExecution and StepExecution, then returns a FlowExecutionStatus:

~~~java
public class ImportDecider implements JobExecutionDecider {

    @Override
    public FlowExecutionStatus decide(
            JobExecution jobExecution,
            StepExecution stepExecution) {

        if (stepExecution != null
                && stepExecution.getWriteCount() == 0) {
            return new FlowExecutionStatus("NO_DATA");
        }

        return new FlowExecutionStatus("HAS_DATA");
    }
}
~~~

Registering the decider and using it in a Job:

~~~java
@Bean
Job importJob(
        JobRepository jobRepository,
        Step importStep,
        Step publishStep,
        Step noDataStep,
        JobExecutionDecider importDecider) {

    return new JobBuilder("importJob", jobRepository)
        .start(importStep)
        .next(importDecider)
            .on("HAS_DATA").to(publishStep)
        .from(importDecider)
            .on("NO_DATA").to(noDataStep)
        .from(importDecider)
            .on("*").fail()
        .end()
        .build();
}
~~~

This example illustrates deciding a branch based on the number of records written. In a real application, you can use a business status stored in ExecutionContext or reconciliation data.

### How does Decider differ from ExitStatus?

- ExitStatus is the exit outcome of a Step.
- FlowExecutionStatus is the outcome returned by a decider for the flow to pick a branch.
- A Decider does not directly change the BatchStatus of an already executed Step.
- A Decider fits flow-control decisions that need to read multiple pieces of information or apply business rules.

Do not use a decider for every case. If a Step already returns COMPLETED or FAILED and only simple forwarding is needed, conditional transitions by ExitStatus are easier to read.

## 11. Skip does not necessarily fail a Step

A common misconception is thinking skips fail a Step; in fact, a Step can finish with BatchStatus COMPLETED even when some items were skipped, provided skipping is allowed and the limit is not exceeded.

Example:

~~~java
return new StepBuilder("importStep", jobRepository)
    .<InputRecord, OutputRecord>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .skip(ValidationException.class)
    .skipLimit(20)
    .build();
~~~

If 3 items are skipped and the Step still completes, the default ExitStatus may remain COMPLETED. If the flow only checks COMPLETED, it will proceed to publish.

Whether that is right depends on business rules:

- If skips are acceptable and the output remains valid, publishing may proceed.
- If any skip requires human inspection, use a listener returning a custom ExitStatus and transition to review.
- If any skip is unacceptable, have the Step or flow end as failed according to policy.

Do not assume skip count automatically produces a separate ExitStatus. If you want the flow to distinguish runs with skips, explicitly design and assign the outcome code.

## 12. Success-conditional flows and restart

Spring Batch persists JobInstance, JobExecution, StepExecution, and execution state in JobRepository. When a Job fails and is restarted with the same identifying JobParameters, the flow re-executes according to metadata and restart policies.

Example:

~~~mermaid
flowchart TD
    A["validateStep COMPLETED"] --> B["importStep"]
    B -->|COMPLETED| C["publishStep"]
    B -->|FAILED| D["Job FAILED"]
    C -->|FAILED| D
    C -->|COMPLETED| E["Job COMPLETED"]
    D -. "Restart same JobInstance" .-> B
~~~

If validateStep already completed, it is normally skipped when restarting the same JobInstance under default behavior. A failed Step can be re-run if restarts are allowed. Once that Step succeeds, the flow continues along the matching transition.

Several points to keep in mind:

- A COMPLETED Step normally does not re-run when restarting the same JobInstance.
- A failed Step can be re-executed unless restricted or marked non-restartable.
- Readers and writers need proper checkpoints to resume uncommitted work.
- Identifying JobParameters must remain consistent on restart.
- The flow must have explicit transitions for every ExitStatus a Step may return.

### allowStartIfComplete

If a Step must re-run when the JobInstance restarts even though the Step already completed, you can configure allowStartIfComplete(true):

~~~java
@Bean
Step refreshValidationStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet validationTasklet) {

    return new StepBuilder("refreshValidationStep", jobRepository)
        .tasklet(validationTasklet, transactionManager)
        .allowStartIfComplete(true)
        .build();
}
~~~

Enable this option only when the Step can be safely re-run. If the Step sends notifications, publishes files, or causes side effects, idempotency or duplicate-prevention mechanisms are required.

### Flow does not replace idempotency

A flow determines which Step runs. It does not guarantee on its own that a Step's operations are safe to repeat.

If the publish file Step succeeded but metadata failed or the Job needs a restart, there must be a way to tell whether the file was already published. Use batch-ID filenames, business keys, publish status flags, or confirmation mechanisms from the target system.

## 13. Handling the failure branch

A Job may have a dedicated Step for recording errors, saving reports, or releasing locks. However, you must define the final status of the Job after the error-handling branch.

Example of transitioning to recordFailureStep when data import fails:

~~~java
@Bean
Job importJob(
        JobRepository jobRepository,
        Step importStep,
        Step publishStep,
        Step recordFailureStep) {

    return new JobBuilder("importJob", jobRepository)
        .start(importStep)
            .on("COMPLETED").to(publishStep)
        .from(importStep)
            .on("FAILED").to(recordFailureStep)
        .from(importStep)
            .on("*").fail()

        .from(publishStep)
            .on("COMPLETED").end()
        .from(publishStep)
            .on("*").fail()

        .from(recordFailureStep)
            .on("*").fail()
        .end()
        .build();
}
~~~

In this example, recordFailureStep may finish writing audit records, yet the Job still ends FAILED because that branch's terminal transition is fail().

This keeps a clear distinction:

- The error-handling Step completed.
- The original business Job still failed.

If .on("*").end() is used on the failure branch, the Job can finish COMPLETED. Do that only when business rules define handling the error as a successful Job outcome—for example, a Job that classifies and quarantines invalid input files.

### Never let a failure branch accidentally run publish

In critical flows, explicitly declare transitions for every Step. If only the success branch exists without a fallback, unexpected ExitStatus values can trigger a missing-transition flow error. If a wildcard routes everything to publish, corrupted data can be released.

The safe rule is that only explicitly accepted ExitStatus codes may enter Steps that cause external side effects such as publishing, sending notifications, or updating downstream systems.

## 14. Conditional flow based on data validation status

Another example is a Job that validates a file before importing. The validation Step can return one of three outcomes:

- COMPLETED: valid file.
- NO_DATA: file has no data rows.
- FAILED: malformed or unreadable file.

Flow:

~~~java
return new JobBuilder("fileImportJob", jobRepository)
    .start(validateFileStep)
        .on("COMPLETED").to(importStep)
    .from(validateFileStep)
        .on("NO_DATA").to(noDataStep)
    .from(validateFileStep)
        .on("FAILED").to(rejectFileStep)
    .from(validateFileStep)
        .on("*").fail()

    .from(importStep)
        .on("COMPLETED").to(publishStep)
    .from(importStep)
        .on("*").fail()

    .from(noDataStep)
        .on("COMPLETED").end()
    .from(noDataStep)
        .on("*").fail()

    .from(rejectFileStep)
        .on("*").fail()
    .end()
    .build();
~~~

The flow imports data only when the file is valid and has data. Empty files are handled on a separate branch. Malformed files go to the reject branch, after which the Job still reports FAILED so schedulers or monitoring systems notice the input error.

To produce ExitStatus NO_DATA, the validation Step must actively return a custom code, such as via a StepExecutionListener or appropriate control logic. Do not assume Spring Batch generates this code automatically just because a reader read zero items.

## 15. Success conditions across consecutive Steps

In a multi-stage workflow, each Step needs an explicit success condition before the flow proceeds.

Example:

| Step | Condition to proceed | Next Step |
|---|---|---|
| validateInputStep | COMPLETED | loadReferenceStep |
| loadReferenceStep | COMPLETED | processStep |
| processStep | COMPLETED | reconcileStep |
| reconcileStep | COMPLETED | publishStep |
| publishStep | COMPLETED | End Job |

If any Step returns an ExitStatus other than COMPLETED, the flow transitions to failure or the declared handling branch.

Do not pack too many responsibilities into one Step merely to reduce the number of transitions. Steps with clear boundaries make it easy to pinpoint which stage failed and where to restart.

## 16. Testing conditional flows

Conditional flows should be tested by verifying which Step actually runs for each ExitStatus.

Important cases:

| First Step ExitStatus | Expected result |
|---|---|
| COMPLETED | Next success Step runs |
| FAILED | Publish Step does not run; Job takes fail or error branch |
| STOPPED | Job takes stop branch if configured |
| NO_DATA | Empty-data handling branch runs |
| COMPLETED_WITH_SKIPS | Review branch runs if declared |
| Unsupported code | Fallback handles it, typically fail |

### Testing the success flow

For the success case:

1. Configure the first Step to return ExitStatus COMPLETED.
2. Run the Job.
3. Verify the next Step executed.
4. Verify the publish Step runs only when all preceding Steps return accepted statuses.
5. Verify the Job finishes COMPLETED.

### Testing the failure flow

For the failure case:

1. Configure the first Step to throw an exception or return a failed ExitStatus appropriately.
2. Run the Job.
3. Verify the publish Step did not run.
4. Verify the error branch ran if present.
5. Verify the final Job status matches the declared fail(), end(), or stop().

### Testing custom codes and wildcards

Verify both:

- Explicitly declared custom codes take the right branch.
- Unexpected codes are not misrouted by a wildcard onto the publish branch.
- COMPLETED_WITH_SKIPS is handled according to policy.
- No valid status is omitted leaving the flow without a transition.

### Testing restart

Create a run where the processing Step succeeds but the publish Step fails. Restart the same JobInstance and verify:

- Completed Steps are skipped by default.
- The failed Step re-runs.
- The flow continues along the right transition.
- Publishing does not create duplicate effects if the first run had partial side effects.
- The Job finishes with the right status.

You can use Spring Batch test utilities like JobLauncherTestUtils and JobRepositoryTestUtils to run the Job in a test context. Check JobExecution, StepExecution, and output data rather than checking only exceptions.

## 17. Monitoring flows at runtime

When a Job has multiple branches, record enough information to tell why the flow chose a Step.

Useful information:

- Job name and JobExecution ID.
- Step name and StepExecution ID.
- Step BatchStatus.
- ExitStatus and exit code.
- Start and end timestamps.
- Read, write, filter, and skip counters.
- Transition or branch taken.
- Batch ID and identifying JobParameters with sensitive data sanitized.

You can log ExitStatus inside StepExecutionListener or use operational tooling backed by JobExplorer. Do not log only "Step completed" without recording the ExitStatus code when a flow has multiple branches.

For custom codes, maintain documentation or constant enums to avoid typos between where ExitStatus is created and where transitions are configured.

## 18. Common design mistakes

### Confusing BatchStatus with ExitStatus

Flow transitions match ExitStatus. A Step can have BatchStatus COMPLETED yet a custom ExitStatus. Check the exact code the flow receives.

### Using next() when branching is needed

next() fits sequential flows. When you need success conditions, error branches, or business states, declare explicit transitions.

### Declaring only a COMPLETED branch without a fallback

A custom ExitStatus or unexpected status may lack a matching transition. Add a wildcard fallback to define behavior for all remaining outcomes.

### Using an overly broad wildcard on a publish branch

With on("*").to(publishStep), every ExitStatus can reach publish. Use patterns only for statuses verified to be safe.

### Not handling custom ExitStatus

If a listener returns COMPLETED_WITH_SKIPS while the flow only has COMPLETED, the Step may fail to enter the expected branch. Explicitly declare custom codes.

### Using end() on an error branch without understanding final status

end() ends the Job with a completed status. If used on a FAILED branch, the Job can be marked COMPLETED even though the preceding Step failed. Use it only when the error is handled and business policy considers the Job complete.

### Treating skip as automatic failure

Configured skips can allow a Step to finish normally. If skips require review, produce a custom ExitStatus or use a separate condition.

### Using a Decider for simple conditions

If you only need to check COMPLETED, a transition on ExitStatus is clearer and shorter. Use a Decider when the decision requires additional logic or data.

### Skipping tests for failure branches

Testing only the happy path does not prove the Job will stop properly when validation, import, or publish fails. Test failure branches and fallbacks.

## 19. Process for building success-conditional flows

When designing a Job, follow this sequence:

1. **List Steps:** identify business stages and dependency order.
2. **Define outcomes:** specify default ExitStatus and custom codes for each Step.
3. **Define success:** decide exactly which statuses are permitted to run the next Step.
4. **Configure transitions:** use on("COMPLETED").to(...) or accepted codes.
5. **Add fallback:** handle all other ExitStatus values with failure, stop, or intentional completion.
6. **Separate business branches:** handle NO_DATA, COMPLETED_WITH_SKIPS, or warnings as required.
7. **Pick terminal state:** decide between end(), fail(), and stop() based on desired Job outcome.
8. **Review restart:** ensure Steps and side effects can re-run safely.
9. **Record status:** log ExitStatus and StepExecution so operations can trace runs.
10. **Test every branch:** success, failure, custom codes, wildcards, and restart.

## 20. Key takeaways

- Flows control the execution order and branching of Steps within a Job.
- Conditional transitions typically match **ExitStatus**, not BatchStatus directly.
- on("COMPLETED").to(nextStep) allows forwarding when ExitStatus is COMPLETED.
- from(step) declares additional transitions originating from the same Step.
- Use wildcard on("*") as a fallback for codes not explicitly declared.
- Allow only defined ExitStatus values to reach publish Steps or side-effecting operations.
- Custom ExitStatus separates COMPLETED_WITH_SKIPS, NO_DATA, or warnings into dedicated branches.
- end() ends the Job completed; fail() ends it failed; stop() ends it stopped.
- Skip does not automatically fail a Step; define business policy explicitly.
- JobExecutionDecider fits when branching decisions require extra logic or data.
- Restart depends on JobRepository, identifying JobParameters, Step status, and safe re-execution.
- Test success paths, failure paths, custom statuses, fallbacks, and restarts.

A success-conditional flow ensures a Job proceeds to the next stage only when the prior outcome meets the defined contract. When ExitStatus, fallback branches, and terminal states are clearly configured, Spring Batch workflows become easy to follow, safe to publish, and straightforward to recover on failure.

