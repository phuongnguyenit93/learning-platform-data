# Skipping steps and stopping jobs

In Spring Batch, a Job's flow can branch to skip an unnecessary Step, end the Job successfully, end the Job in failure, or stop the Job so it can be resumed later. These decisions are expressed as transitions in the Job flow, typically based on a Step's `ExitStatus` or the result from a `JobExecutionDecider`.

Two concepts must be clearly distinguished:

- **Skipping a Step in the flow:** the Job takes another branch and does not execute that Step. This is a way of structuring conditional workflows.
- **Stopping a Job:** the Job finishes in the `STOPPED` status due to a transition or receives a stop request while running. The stop is persisted in metadata and can be resumed according to restart policies.

This is not the same mechanism as skipping an item in chunk processing. Item skip handles a faulty record in a reader, processor, or writer; skipping a Step means bypassing a node in the flow graph. Spring Batch does not have a `BatchStatus.SKIPPED` for a Step bypassed in a flow.

## 1. Job flows and transitions

A Job can consist of multiple Steps chained sequentially or branching based on the outcome of the previous Step. With Java configuration, flows are usually declared using `JobBuilder`:

```java
@Bean
Job importJob(
        JobRepository jobRepository,
        Step validateStep,
        Step importStep,
        Step archiveStep) {

    return new JobBuilder("importJob", jobRepository)
            .start(validateStep)
                .on("COMPLETED").to(importStep)
            .from(importStep)
                .on("COMPLETED").to(archiveStep)
            .from(archiveStep)
                .on("*").end()
            .end()
            .build();
}
```

Key components:

- `start(step)` specifies the first Step of the flow.
- `on(pattern)` selects a transition based on the outcome code.
- `to(step)` moves to the next Step or state.
- `from(step)` declares an additional transition starting from the specified Step.
- `end()` closes the flow declaration; when used as a transition target, it also means ending the Job with a completed status.

In a transition from a Step, the pattern is matched against the Step's `ExitStatus`. Therefore, distinguish exit codes from `BatchStatus`: a Step can have `BatchStatus.COMPLETED` while carrying a custom exit code such as `NO_DATA` so the Job can branch.

## 2. Skipping a Step by routing around it

To skip a Step, design the flow so that one branch routes directly to a later Step, bypassing the Step you want to skip.

For example, a Job has three stages: validate data, enrich data, and load data. If the input data has already been enriched beforehand, the Job can go straight from validation to loading:

```text
                 +--> NEEDS_ENRICHMENT --> Enrich Step --+
                 |                                      |
Validate Step ---+                                      +--> Load Step
                 |                                      |
                 +--> ALREADY_ENRICHED -----------------+
```

A custom exit code can be used to create the branch:

```java
@Bean
Step validateInputStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        InputValidationService validationService) {

    return new StepBuilder("validateInputStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                ValidationResult result = validationService.validate();

                if (result.alreadyEnriched()) {
                    contribution.setExitStatus(
                            new ExitStatus("ALREADY_ENRICHED"));
                } else {
                    contribution.setExitStatus(
                            new ExitStatus("NEEDS_ENRICHMENT"));
                }

                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
```

The flow using that outcome:

```java
@Bean
Job importJob(
        JobRepository jobRepository,
        Step validateInputStep,
        Step enrichStep,
        Step loadStep) {

    return new JobBuilder("importJob", jobRepository)
            .start(validateInputStep)
                .on("NEEDS_ENRICHMENT").to(enrichStep)
            .from(validateInputStep)
                .on("ALREADY_ENRICHED").to(loadStep)
            .from(enrichStep)
                .on("COMPLETED").to(loadStep)
            .from(loadStep)
                .on("*").end()
            .end()
            .build();
}
```

When `validateInputStep` returns `ALREADY_ENRICHED`, `enrichStep` is not invoked. There is no `StepExecution` for `enrichStep` in that run because the Step was bypassed entirely. This is the normal outcome of a conditional flow, not a failed Step or a skipped item.

## 3. Using JobExecutionDecider to decide whether a Step runs

When the branching condition should not live inside a Step or needs to rely on aggregated Job state, you can use `JobExecutionDecider`. The Decider returns a `FlowExecutionStatus` so the flow can select a transition.

For example, the Job decides whether data enrichment is needed based on `JobParameters`:

```java
@Bean
JobExecutionDecider enrichmentDecider() {
    return (jobExecution, stepExecution) -> {
        String mode = jobExecution.getJobParameters().getString("mode");

        if ("ALREADY_ENRICHED".equals(mode)) {
            return new FlowExecutionStatus("SKIP_ENRICHMENT");
        }

        return new FlowExecutionStatus("RUN_ENRICHMENT");
    };
}
```

Flow declaration:

```java
@Bean
Job importJob(
        JobRepository jobRepository,
        Step prepareStep,
        JobExecutionDecider enrichmentDecider,
        Step enrichStep,
        Step loadStep) {

    return new JobBuilder("importJob", jobRepository)
            .start(prepareStep)
            .next(enrichmentDecider)
                .on("RUN_ENRICHMENT").to(enrichStep)
            .from(enrichmentDecider)
                .on("SKIP_ENRICHMENT").to(loadStep)
            .from(enrichStep)
                .on("COMPLETED").to(loadStep)
            .from(loadStep)
                .on("*").end()
            .end()
            .build();
}
```

`JobExecutionDecider` is not a Step and does not create a `StepExecution`. It returns a flow-control outcome. Transitions from a Step normally match `ExitStatus`; transitions from a Decider match the `FlowExecutionStatus` returned by the Decider.

## 4. Creating custom ExitStatus codes to bypass a Step

A common approach is using `StepExecutionListener.afterStep` to set a custom exit code. For example, if a Step reads data and finds zero records, the Job can bypass the next processing Step and go straight to a summary step.

```java
@Bean
StepExecutionListener noDataListener() {
    return new StepExecutionListener() {
        @Override
        public void beforeStep(StepExecution stepExecution) {
            // No pre-step processing needed.
        }

        @Override
        public ExitStatus afterStep(StepExecution stepExecution) {
            if (stepExecution.getStatus() == BatchStatus.COMPLETED
                    && stepExecution.getReadCount() == 0) {
                return new ExitStatus("NO_DATA");
            }
            return null;
        }
    };
}
```

Then configure the flow:

```java
.start(readInputStep)
    .on("NO_DATA").to(createEmptyReportStep)
.from(readInputStep)
    .on("COMPLETED").to(processDataStep)
.from(processDataStep)
    .on("COMPLETED").to(createReportStep)
```

The listener changes `ExitStatus` only when the Step has completed and has no data. `BatchStatus` remains `COMPLETED`. This fits when the technical Step succeeded, yet the business result requires steering the flow onto a separate branch.

Do not set `BatchStatus.FAILED` merely to skip a Step. If the work actually succeeded with no data, a custom exit code expresses the intent much more accurately.

## 5. Ways to end a flow: end, fail, and stop

Spring Batch provides different transition targets to determine the Job's outcome when the flow reaches a terminal branch.

| Transition | Job BatchStatus | Meaning |
|---|---|---|
| `.end()` | `COMPLETED` | Ends the Job successfully according to the flow. |
| `.fail()` | `FAILED` | Ends the Job with a failed status. |
| `.stop()` | `STOPPED` | Stops the Job via the flow; can be restarted per policy. |
| `.stopAndRestart(step)` | `STOPPED` | Stops the Job and specifies a Step as the resumption point on restart. |

These transitions differ from `.to(nextStep)`, which transfers the flow to another Step.

### end(): ending the Job successfully

`.end()` ends the Job with `BatchStatus.COMPLETED`. For example, if there is no data to process and business rules treat that as a valid outcome, the Job can finish successfully:

```java
return new JobBuilder("optionalImportJob", jobRepository)
        .start(checkInputStep)
            .on("NO_DATA").end()
        .from(checkInputStep)
            .on("COMPLETED").to(importStep)
        .end()
        .build();
```

Once a Job is `COMPLETED`, the same `JobInstance` normally cannot be launched again as a new run. If you want to process a new business batch, new identifying parameters are needed by design. `.end()` is not a pause command.

### fail(): ending the Job as failed

`.fail()` terminates the flow with `BatchStatus.FAILED`. Use it when business rules or a Step outcome mean the Job cannot be considered successful:

```java
return new JobBuilder("controlledImportJob", jobRepository)
        .start(validateStep)
            .on("INVALID_DATA").fail()
        .from(validateStep)
            .on("COMPLETED").to(importStep)
        .end()
        .build();
```

A failed Job can be restarted if the Job and execution state permit it. On restart, Spring Batch uses metadata and the flow to determine which work needs to resume. If the Job is configured with `preventRestart()`, restarting will be prevented.

### stop(): stopping the Job via the flow

`.stop()` terminates the flow with `BatchStatus.STOPPED`. Use it when an intentional pause is needed, such as after a validation step to await approval:

```java
return new JobBuilder("approvalJob", jobRepository)
        .start(prepareApprovalStep)
            .on("COMPLETED").to(approvalCheckStep)
        .from(approvalCheckStep)
            .on("WAITING_FOR_APPROVAL").stop()
        .from(approvalCheckStep)
            .on("APPROVED").to(processPaymentStep)
        .end()
        .build();
```

When the flow reaches `stop()`, the Job finishes in `STOPPED`, not `COMPLETED`. The `JobInstance` can be restarted after the waiting condition is resolved, depending on metadata and Step configuration.

### stopAndRestart(step): specifying the resumption point

If you want to stop the Job and explicitly specify the Step to run upon restart, use `.stopAndRestart(step)`:

```java
return new JobBuilder("approvalJob", jobRepository)
        .start(prepareApprovalStep)
            .on("COMPLETED").to(approvalCheckStep)
        .from(approvalCheckStep)
            .on("WAITING_FOR_APPROVAL").stopAndRestart(processPaymentStep)
        .from(approvalCheckStep)
            .on("APPROVED").to(processPaymentStep)
        .from(processPaymentStep)
            .on("COMPLETED").to(archiveStep)
        .end()
        .build();
```

The flow stops in `STOPPED`. When the `JobInstance` is validly restarted, the flow resumes at `processPaymentStep` as the specified restart point. This is useful when the approval step only checks the waiting state and does not need to run again once approval is granted.

Ensure the Step designated as the restart point can run safely with the data prepared in prior Steps. If an earlier Step created side effects, do not delete or alter metadata to force the flow to start from an arbitrary location.

## 6. Distinguishing stop in a flow from stopping a running Job

`.stop()` is a predefined transition in the Job flow. When the Job reaches that branch, the framework terminates the Job in the `STOPPED` state.

In operations, you may need to stop an actively running Job due to an operator request, system maintenance, or changing external conditions. That is a different action: the application sends a stop request through `JobOperator`.

```java
@Service
public class BatchControlService {

    private final JobOperator jobOperator;

    public BatchControlService(JobOperator jobOperator) {
        this.jobOperator = jobOperator;
    }

    public void requestStop(long jobExecutionId) throws Exception {
        jobOperator.stop(jobExecutionId);
    }
}
```

`JobOperator.stop(executionId)` asks Spring Batch to stop the running execution. This is a graceful stop request, not an immediate thread-kill or process termination.

For a chunk Step, the framework normally stops at a safe processing boundary, such as after the current chunk finishes its transaction. Thus, it may take some time for the Job to transition from `STOPPING` to `STOPPED`. If a reader, processor, or writer is blocked on an I/O call, separate timeouts are needed to prevent indefinite waiting.

Before sending a stop request, identify the exact `JobExecutionId`. Do not stop solely by Job name if multiple executions of that Job exist.

## 7. BatchStatus and ExitStatus when skipping a Step or stopping a Job

`BatchStatus` and `ExitStatus` play different roles:

- `BatchStatus` reflects the lifecycle state of a `JobExecution` or `StepExecution`, such as `COMPLETED`, `FAILED`, `STOPPED`.
- `ExitStatus` holds the exit code and outcome description; the flow uses the exit code to choose transitions.

A Step can complete successfully technically (`BatchStatus.COMPLETED`) yet carry an exit code like `NO_DATA` or `ALREADY_ENRICHED`. The flow uses this exit code to bypass another Step.

A Job can end with `BatchStatus.STOPPED` due to `.stop()` or a stop request from `JobOperator`. This is a Job state and does not mean the most recent Step was skipped.

| Situation | Step BatchStatus | Step ExitStatus | Job BatchStatus |
|---|---|---|---|
| Check Step succeeds, need to run next Step | `COMPLETED` | `COMPLETED` | Not finished yet |
| Check Step succeeds, bypass optional Step | `COMPLETED` | `ALREADY_ENRICHED` | Flow continues |
| Flow calls `.end()` | Last Step may be `COMPLETED` | Per last transition | `COMPLETED` |
| Flow calls `.fail()` | Previous Step may be `COMPLETED` | Per transition | `FAILED` |
| Flow calls `.stop()` | Previous Step may be `COMPLETED` | Per transition | `STOPPED` |
| Operator requests stopping a running Job | Current Step ends at safe stop point | May be `STOPPED` depending on stop path | `STOPPED` once stopped |

Do not rely solely on a Step's `ExitStatus` to conclude that the Job finished. Inspect both `JobExecution` status and flow transitions.

## 8. Transition patterns and default branches

`on(pattern)` uses a pattern to match exit codes. You can use exact codes or a wildcard such as `*` as a default branch.

Example:

```java
.start(validateStep)
    .on("NO_DATA").end()
.from(validateStep)
    .on("COMPLETED").to(importStep)
.from(validateStep)
    .on("*").fail()
```

In this example, `NO_DATA` and `COMPLETED` are handled individually; other outcomes go to the fail branch. Declare all expected outcomes along with a clear fallback branch so the flow has no unhandled outcomes.

Avoid placing a wildcard too early where it renders specific branches meaningless or sends unexpected errors onto a success path. Read the flow as a graph: from each Step/Decider, identify all possible outcomes and the target for each.

## 9. Bypassing a Step vs skipping an item

Two concepts with similar names have different scopes:

| Aspect | Item skip | Bypass Step |
|---|---|---|
| Scope | One item inside a chunk | One Step in a Job flow |
| Mechanism | Exception + skip policy/skip limit | Conditional transition or Decider |
| Involved components | Reader, processor, writer, `SkipListener` | `JobBuilder`, Flow, `JobExecutionDecider`, ExitStatus |
| Metadata | Increments skip counters in `StepExecution` | Bypassed Step has no `StepExecution` in that run |
| Purpose | Continue processing remaining items when one item errors | Avoid running an unnecessary stage |

For example, a file with 1,000 rows where 5 rows have formatting errors is a candidate for item skip. If the file was already cleaned beforehand and does not need `cleanFileStep`, the flow can bypass that entire Step.

Do not use `.skip(...)` to bypass a Step. Skip configuration applies to item-level exceptions inside a fault-tolerant Step.

## 10. Restarting after a Job stops

A Job in `STOPPED` status can be restarted if the `JobInstance`, Job, and Steps permit it. On restart:

- Spring Batch creates a new `JobExecution` for the same `JobInstance`.
- Already completed Steps are normally skipped.
- Incomplete Steps can resume based on metadata and checkpoints.
- With `.stopAndRestart(step)`, the flow uses the designated restart point.
- If a Step is configured with `allowStartIfComplete(true)`, a completed Step can re-run during an appropriate restart.

For example, the Job stops after preparing data to await approval. Once approval is granted, the application restarts the same `JobInstance` to continue to the processing Step. If you want to create a new business batch, new identifying parameters are required instead of restarting the old execution.

### Do not confuse restart with launching a new JobInstance

Restarting preserves the `JobInstance` identity and execution history so Spring Batch can continue. Creating a new `JobInstance` with different identifying parameters starts a new business run, usually from the beginning of the flow.

Do not add timestamps or UUIDs to identifying parameters just to evade `COMPLETED` or `STOPPED` states. Clarify whether the user wants to resume old work or launch a new batch.

## 11. Designing a Step that can be safely bypassed

A Step can be bypassed when business conditions allow. Before skipping it, verify:

- Whether the Step is truly optional.
- Whether the next Step has all required data and state.
- Whether side effects normally created by the bypassed Step need to be substituted.
- Whether `JobParameters` or `JobExecutionContext` hold sufficient info for downstream branches to continue.
- Whether on restart the flow could take a different branch because conditions changed.

For example, if `enrichStep` is bypassed because data was already enriched, `loadStep` must receive the same data structure it expects after `enrichStep` runs. Otherwise, bypassing will cause errors in the downstream Step.

The bypass condition should be determined from verifiable data, such as batch state or an explicit attribute, rather than relying solely on a volatile runtime flag.

## 12. Stopping Jobs and external side effects

Requesting a Job stop does not automatically undo already executed side effects. In chunk processing, the current chunk may finish and commit before the Step stops. Earlier chunks have also already committed and are retained.

If a Step sends emails, calls APIs, or moves files, those operations do not automatically roll back with the database transaction. When the Job is restarted, they may be executed again if the flow re-runs that Step.

Therefore:

- Design tasks to be idempotent whenever possible.
- Use business keys or idempotency keys to prevent duplicate processing.
- Check file or request state before re-executing.
- Use outbox/inbox patterns when coordinating database changes and event emission.
- Before restarting after a stop, reconcile actual business state.

## 13. Common mistakes

### Thinking a bypassed Step gets a SKIPPED status

A Step not invoked in the flow usually has no `StepExecution` for that run. There is no standard `BatchStatus.SKIPPED` for Step bypass.

### Using skip policy to bypass an entire Step

Skip policy handles item exceptions within a chunk. To bypass a Step, use conditional flows or `JobExecutionDecider`.

### Confusing `.end()` with `.stop()`

`.end()` ends the Job as `COMPLETED`; `.stop()` ends the Job as `STOPPED` so it can be restarted. Choose based on business meaning.

### Using `.fail()` for a no-data branch

Having no data can be a valid outcome. If so, use an exit code like `NO_DATA` and route to a summary Step or complete successfully.

### Thinking JobOperator.stop() kills threads immediately

It is a graceful stop request. A Step normally needs to reach a safe point to finish its transaction and update metadata. Configure I/O timeouts to avoid hung tasks.

### Omitting a fallback branch

If an exit code has no matching transition, the flow can terminate unexpectedly. Define all expected exit codes and a default branch.

### Bypassing a Step whose output a later Step still needs

This leaves the downstream Step missing data or state. Ensure the bypass branch provides adequate input conditions or routes through an alternative Step.

### Manually editing metadata to restart from an arbitrary Step

Directly editing Job/Step execution status or context can break consistency. Use flow transitions, `stopAndRestart`, and proper operational APIs.

## 14. Workflow for designing Step skipping and Job stopping

When designing a flow with Step-skipping or Job-stopping branches, follow this sequence:

1. Map out Steps and business conditions governing the paths.
2. Decide whether conditions are expressed via a Step's `ExitStatus` or `JobExecutionDecider`.
3. Create meaningful exit codes/`FlowExecutionStatus` values for each branch.
4. Use `.to(nextStep)` to bypass optional Steps.
5. Use `.end()` if the Job completed successfully; `.fail()` if the outcome must fail.
6. Use `.stop()` if stopping via flow; use `.stopAndRestart(step)` if a resumption point must be designated.
7. Use `JobOperator.stop(executionId)` when a running Job needs an external stop request.
8. Add a fallback branch for unexpected outcomes.
9. Verify downstream Steps after a bypass branch have all necessary data and state.
10. Test Job completion, Job failure, Job stop, restart, and stop requests while chunks are running.

| Requirement | Mechanism to use |
|---|---|
| Skip enrichment Step if data is already ready | Conditional transition or `JobExecutionDecider` to jump straight to the next Step. |
| Skip a faulty record inside a chunk | `.skip(...)` and `.skipLimit(...)`. |
| Complete Job successfully when there is no data | Custom `ExitStatus` then `.end()` or route to summary Step. |
| Mark Job failed on a business condition | `.fail()`. |
| Stop Job via flow to wait for approval | `.stop()` or `.stopAndRestart(step)`. |
| Operator requests stopping a running Job | `JobOperator.stop(jobExecutionId)`. |

## Conclusion

To skip a Step, design conditional transitions or use `JobExecutionDecider` so the flow jumps directly to the appropriate Step; a bypassed Step creates no `StepExecution` and has no dedicated `SKIPPED` status. To control the Job's final outcome, use `.end()` for `COMPLETED`, `.fail()` for `FAILED`, `.stop()` for `STOPPED`, or `.stopAndRestart(step)` when a resumption point must be specified. When an actively running Job must be stopped externally, use `JobOperator.stop(executionId)` and let the framework stop at a safe boundary. Always distinguish bypassing a Step from skipping an item, verify restart behavior, and ensure side effects remain safe when the Job resumes.
