# How One Flow's Failure Affects the Job

In Spring Batch, `split()` allows a job to run multiple independent flows in parallel. Each flow can contain one or more steps and perform its own piece of work, such as generating reports, updating a search index, or syncing data to another system.

When one flow in the group errors out, the error status propagates to the parent flow and affects the split result. In the typical case, if one branch ends with `FAILED`, the split flow also has a failed result and the job does not continue along the declared success path. However, other branches may have already completed or may still be running; Spring Batch does not automatically roll back transactions they have already committed.

This is a key point when designing parallel flows: branches run concurrently but do not form a single distributed transaction. You must clearly define how statuses are aggregated, how already-completed work is handled, and how restarts and compensation work when a branch fails.

## 1. How do parallel flows work?

A split flow consists of multiple sub-flows dispatched to a `TaskExecutor` for execution. Each sub-flow can contain one step or a sequence of steps. The manager coordinates parallel execution and waits for the flows' results to determine the overall status.

For example, a job needs to prepare data, then independently generate a report and update a search index:

```text
                 prepareData
                      |
                      v
                    split
                  /       \
                 /         \
        generateReport   updateSearchIndex
                 \         /
                  \       /
                    join
                      |
                      v
                 publishResult
```

When both flows complete normally, the split returns a successful result and the job can move to `publishResult`. If one flow fails, the split result reflects the failure status and the downstream success path is not taken under the default transition.

## 2. Declaring a split flow

You can separate branches into distinct `Flow` beans and combine them with `split(taskExecutor).add(...)`.

```java
@Bean
Flow reportFlow(Step generateReportStep) {
    return new FlowBuilder<SimpleFlow>("reportFlow")
        .start(generateReportStep)
        .build();
}

@Bean
Flow searchIndexFlow(Step updateSearchIndexStep) {
    return new FlowBuilder<SimpleFlow>("searchIndexFlow")
        .start(updateSearchIndexStep)
        .build();
}

@Bean
Flow parallelFlow(
        TaskExecutor taskExecutor,
        Flow reportFlow,
        Flow searchIndexFlow) {

    return new FlowBuilder<SimpleFlow>("parallelFlow")
        .split(taskExecutor)
        .add(reportFlow, searchIndexFlow)
        .build();
}
```

The job uses the split flow as a stage:

```java
@Bean
Job reportingJob(
        JobRepository jobRepository,
        Step prepareDataStep,
        Flow parallelFlow,
        Step publishResultStep) {

    return new JobBuilder("reportingJob", jobRepository)
        .start(prepareDataStep)
        .next(parallelFlow)
        .next(publishResultStep)
        .end()
        .build();
}
```

The example assumes the two flows after `prepareDataStep` do not depend on each other's results. `TaskExecutor` determines parallel execution behavior and maximum thread count. Without an appropriate asynchronous executor, the flows may not run in parallel as expected.

## 3. What happens when one flow fails?

Suppose the split consists of two flows:

- `reportFlow`: generates a report file.
- `searchIndexFlow`: updates the search index.

If `reportFlow` completes while `searchIndexFlow` fails, the typical outcome is:

```text
parallelFlow
  +-- reportFlow       -> COMPLETED
  +-- searchIndexFlow  -> FAILED

Split result           -> FAILED
JobExecution           -> FAILED
publishResultStep      -> does not run along the default success path
```

Steps already completed in the report branch still retain the `COMPLETED` status. Job failure does not mean every step across all branches is marked failed or that their data is deleted.

The split must collect results from its sub-flows to determine the aggregated outcome. Therefore, when one flow errors out, sibling flows already dispatched may continue running until they finish or fail on their own. Do not design around the assumption that an error in one branch will immediately cancel all other branches.

## 4. Split status is aggregated from sub-flows

Each sub-flow returns a `FlowExecutionStatus`. The split aggregates those statuses to return a combined status to the parent flow. Typically, `COMPLETED` from all branches lets the split finish successfully; an unsuccessful status in any branch affects the overall result.

| Sub-flow results | Typical split result | Impact on job |
|---|---|---|
| All `COMPLETED` | `COMPLETED` | Can proceed along the success path |
| One branch `FAILED`, others `COMPLETED` | `FAILED` | Job fails unless a dedicated handling transition is configured |
| Multiple branches `FAILED` | `FAILED` | Job fails; each branch must be investigated |
| One branch `STOPPED`, others completed | Corresponding unsuccessful result propagates up | Job is not considered normally completed |
| Unknown or custom status present | Depends on status rules and transitions | Must declare explicit handling |

Do not look only at the final status of `JobExecution` to conclude which branch caused the failure. Inspect `FlowExecution` statuses, `StepExecution` statuses, and exceptions for each branch in metadata/logs.

## 5. The job does not necessarily stop the instant one branch fails

Flows in a split execute on the executor. One flow can fail while another is still running. The split must collect the execution results of the branches before continuing control flow in the parent flow.

Example:

```text
Time ----->

reportFlow:       RUNNING -------- COMPLETED
searchIndexFlow:  RUNNING -- FAILED
archiveFlow:      RUNNING ---------------- COMPLETED
                                  |
                                  v
                     split aggregates results
                                  |
                                  v
                              FAILED
```

In the diagram, `searchIndexFlow` fails first, yet `reportFlow` and `archiveFlow` can still finish. The job then receives the failed split result. This means partial side effects may have already occurred before the job is marked `FAILED`.

Cancelling running tasks depends on the specific executor, handler, and orchestration mechanism. Do not treat a flow's `FAILED` status as a cancellation or rollback mechanism for other flows.

## 6. Does the step after the split run?

With a standard flow declaration `.next(parallelFlow).next(publishResultStep)`, the subsequent step only runs when the split finishes with a status that allows the transition. If the split returns `FAILED`, the default success transition is not chosen and `publishResultStep` does not run.

This is usually the desired behavior: do not publish aggregated results if part of the parallel work has not succeeded.

If business rules require running an error-recording or compensation step, declare conditional transitions for the split status. Example routing structure:

```java
return new JobBuilder("reportingJob", jobRepository)
    .start(parallelFlow)
        .on("COMPLETED").to(publishResultStep)
    .from(parallelFlow)
        .on("FAILED").to(recordParallelFailureStep)
    .from(parallelFlow)
        .on("*").fail()
    .from(publishResultStep)
        .on("COMPLETED").end()
    .from(publishResultStep)
        .on("*").fail()
    .from(recordParallelFailureStep)
        .on("*").fail()
    .end()
    .build();
```

This example records the incident via `recordParallelFailureStep` and still ends the job in a failed state. That way the system can persist operational info or send alerts without turning a failed split into a successful outcome.

Transitions must match the actual statuses returned by the flow. If using a custom `FlowExecutionStatus`, declare matching patterns and a clear fallback branch.

## 7. Distinguishing FlowExecutionStatus, ExitStatus, and BatchStatus

When investigating parallel flow failures, distinguish three status types:

| Status | Scope | Meaning |
|---|---|---|
| `FlowExecutionStatus` | Result of a flow or split flow | Controls transitions between flows/steps |
| `ExitStatus` | Exit result of a step or job | Result code used in flow transitions and reporting |
| `BatchStatus` | Lifecycle of a JobExecution/StepExecution | Statuses like `STARTED`, `COMPLETED`, `FAILED`, `STOPPED` |

A step inside a branch may end with `BatchStatus.FAILED`; the flow containing that step reflects the failed result. The split aggregates sub-flow statuses and returns a status to the parent flow. The final `JobExecution` is updated according to the orchestration result and related execution statuses.

`FlowExecutionStatus` is not a transaction status. It does not decide whether data from already-executed steps is committed or rolled back.

## 8. Branch transactions are independent

Each worker step in parallel flows has its own transaction managed by that step's transaction manager and chunk/tasklet configuration. There is no automatic transaction enclosing all branches of `split()`.

Example:

```text
reportFlow:
  write report metadata -> COMMIT
  write report file     -> completed

searchIndexFlow:
  update index batch 1  -> COMMIT
  update index batch 2  -> error -> ROLLBACK batch 2

Result:
  report metadata and created file still exist
  already-committed index batch 1 still exists
  index batch 2 is rolled back if using the same transaction resource
  job ends in FAILED
```

Chunks already committed in the failing branch are not automatically rolled back simply because a later step or chunk failed. Likewise, another already-completed flow is not undone.

If the business requires "all branches succeed together or no results are published", design additional staging/publishing or compensation mechanisms. Global atomicity cannot be achieved solely by using `split()`.

## 9. Non-transactional side effects may remain

Database transactions only roll back changes belonging to that transactional resource. If a branch sends an email, calls an HTTP API, creates a file on the filesystem, or publishes a message, those side effects may have already occurred even if a database transaction rolls back.

For example, `reportFlow` already sent a report via email. Then `searchIndexFlow` fails. The overall job is `FAILED`, but the sent email cannot be recalled by Spring Batch rollback.

Safeguards:

- Use idempotency keys for external APIs so re-runs do not create duplicate operations.
- Write events to an outbox inside the transaction and emit only after commit.
- Create temporary files keyed by execution ID, renaming/publishing only when all branches succeed.
- Persist each branch's completion state so a compensation step knows what actually happened.
- Design compensation operations if the business requires reversing partial work.

Do not publish results externally inside a parallel branch if those results are only valid when every branch succeeds. Let branches prepare isolated data, then use a post-split step to publish.

## 10. Handling errors inside individual flows

Not every error needs to fail the entire split. If a step can handle errors on its own via retry or skip, configure fault tolerance directly on that step.

Example:

```java
return new StepBuilder("updateSearchIndex", jobRepository)
    .<IndexRow, IndexDocument>chunk(100, transactionManager)
    .reader(indexReader)
    .processor(indexProcessor)
    .writer(indexWriter)
    .faultTolerant()
    .retry(TransientDataAccessException.class)
    .retryLimit(3)
    .skip(InvalidIndexRowException.class)
    .skipLimit(20)
    .build();
```

With this configuration, transient errors can be retried and skippable invalid items can be skipped. If an error goes unhandled, exceeds the retry/skip limit, or is fatal, the step still fails and that status propagates to the parent flow.

Only skip exceptions representing discardable data. Do not broadly skip connection errors or configuration errors just to make a branch appear successful.

## 11. One flow failing does not roll back other flows

This is an important distinction between parallel orchestration and distributed transactions. Suppose three branches run independently:

| Flow | Result | Data that may have committed |
|---|---|---|
| `generateReportFlow` | `COMPLETED` | Report file and report metadata |
| `updateIndexFlow` | `FAILED` | Index batches committed before the error |
| `refreshCacheFlow` | `COMPLETED` | Refreshed cache |

The job can end in `FAILED`, even though two flows completed. Spring Batch stores the history of each step execution so operators know which work succeeded and which failed.

Therefore, recovery steps should not blindly re-run all side effects. Rely on metadata and business state to decide what needs to resume, what needs checking, or what needs compensating.

## 12. Restarting a job after one flow fails

When restarting the same `JobInstance`, Spring Batch uses `JobRepository` to determine which steps have completed and which need to re-run according to restart policies.

Example first run:

```text
Execution #1
  prepareDataStep          -> COMPLETED
  reportFlow
    generateReportStep     -> COMPLETED
  searchIndexFlow
    updateSearchIndexStep  -> FAILED
```

On restart:

```text
Execution #2 (same JobInstance)
  prepareDataStep          -> skipped if already COMPLETED
  generateReportStep       -> skipped if already COMPLETED
  updateSearchIndexStep    -> restarted from checkpoint if valid
  publishResultStep        -> runs only when split/flow reaches an allowed status
```

This is a general model; exact behavior depends on flow structure, completed steps, restart policy, execution states, and `allowStartIfComplete`/`startLimit` settings. Do not assume every sub-flow always restarts from scratch.

### Conditions for safe restarts

- `JobInstance` must be restartable and the job must not have `preventRestart()` configured.
- Step names and flow structure must stay stable so prior metadata matches properly.
- Readers/Tasklets must persist necessary checkpoints in `ExecutionContext`.
- Completed branches must be safe to skip; side effects must not be regenerated unintentionally.
- Partitions, file names, and request IDs must be stable if they serve as work identifiers.
- Non-transactional operations need idempotency or reconciliation.

Restart does not automatically undo work committed by a successful branch. It resumes from saved metadata and state; if previous work must be reversed, build dedicated compensation.

## 13. JobParameters and shared data across branches

Flows within the same `JobExecution` share the job context and can read the same `JobParameters`. However, do not let multiple branches concurrently write the same keys to `JobExecution`'s `ExecutionContext` without synchronization rules.

Each step has its own `StepExecution` and step `ExecutionContext`. Use the step context for internal branch state. If branches must exchange results, use separate keys, immutable data, or a store with clear synchronization semantics.

Do not use static variables or mutable singletons to share results across flows. Branches can run on different threads and mutate the same object concurrently, causing race conditions or lost updates.

## 14. Using an aggregation step after the split

An operationally friendly design is having branches produce only isolated outputs, then using a post-split step to verify and publish once all required branches complete.

```text
prepareData
    |
    v
   split
   /   \
  /     \
createReport   updateIndex
  \             /
   \           /
    +-- join --+
         |
         v
   verifyOutputs
         |
         v
   publishResults
```

`verifyOutputs` can check that the report file exists, the index has updated to the required watermark, and reconciliation counts match. Only when verification succeeds does `publishResults` run.

If one branch fails, the split does not take the success path so the publish step does not run. Intermediate outputs may still remain; recovery steps can resume the failed branch or clean up temporary data according to policy.

## 15. Compensation when full rollback is impossible

For side effects that cannot be rolled back, a compensation process may be needed. Compensation is a new business operation intended to bring the system to an acceptable state, such as cancelling a created request or marking a report invalid.

Example:

1. `generateReportFlow` creates a temporary file and writes metadata with status `PREPARED`.
2. `updateIndexFlow` updates the index but fails.
3. The job records the split failure.
4. An error-handling step marks the report file `NOT_PUBLISHED` or deletes the temporary file if safe.
5. After fixing the root cause, restart the index branch and re-verify outputs.
6. Only publish the report once all conditions are satisfied.

Compensation is not automatic database rollback. It is part of the business workflow and needs idempotency, auditing, retries, and a policy for when the compensation action itself fails.

## 16. Observing and diagnosing errors per branch

When a job fails at a split, pinpoint the exact failing flow and step instead of looking only at the final `JobExecution` status.

Information to monitor:

- Job name, JobInstance ID, and JobExecution ID.
- Flow names and step names in each branch.
- `BatchStatus` and `ExitStatus` of each `StepExecution`.
- Root exception, start/end timestamps, and retry count.
- Read/write/skip counts and worker checkpoints.
- Side effects committed or emitted to external systems.

Logs should include a correlation ID to link information from manager and workers. Avoid logging entire payloads or secrets in the context. For parallel flows, timestamps and thread names are also useful for understanding event ordering.

## 17. Common design mistakes

| Mistake | Consequence | Solution |
|---|---|---|
| Assuming one failing branch rolls back all branches | Committed data in other branches remains | Design idempotency, staging, or compensation |
| Assuming one branch error immediately cancels remaining branches | Sibling branches may keep running and create side effects | Design branches safe for concurrent execution; do not rely on implicit cancellation |
| Publishing results directly inside each branch | Users may see partial results when another branch fails | Use verify/publish steps after the split |
| Ignoring individual StepExecution statuses | Hard to tell which branch completed | Track metadata for each flow/step |
| Sharing mutable state across branches | Race conditions and inconsistent data | Use isolated step contexts or properly synchronized storage |
| Missing appropriate retry/skip in workers | Item errors can needlessly fail an entire flow | Classify errors and configure step-level fault tolerance |
| Restarting while changing work scope | Old steps may run on different data or duplicate side effects | Keep JobParameters, step names, and output identifiers stable |
| Using wildcard transitions to turn all errors into success | Job may report completion even though a branch failed | Define clear failure and compensation policies |

## 18. Testing failure behavior in parallel flows

Integration tests should simulate at least the following cases:

1. All flows complete: confirm split succeeds and the post-split step runs.
2. One flow fails immediately: confirm split result and `JobExecution` reflect the error.
3. One flow fails while another completes slowly: confirm the other branch can finish and its side effects are recorded.
4. One flow succeeds after retry: confirm split receives only the final post-recovery flow result.
5. One flow skips items yet completes its step: confirm business policy decides whether the flow counts as a success.
6. Restart after one flow fails: confirm completed steps do not re-run unexpectedly and the failed branch resumes at the right checkpoint.
7. Failure inside a compensation or failure-recording step: confirm the job retains clear status and audit trail.
8. Real parallel execution: confirm no race conditions in readers, writers, listeners, and shared context data.

Tests should inspect both metadata statuses and committed data. Simply asserting `JobExecution` is `FAILED` is not enough to prove other branches caused no side effects.

## 19. Procedure for handling a failed flow in production

When alerted to a job failure in a parallel flow, proceed in order:

1. Identify the flow and step with `FAILED` or abnormal status from metadata.
2. Check whether sibling flows completed, are still running, or also failed.
3. Determine which chunks/transactions committed and which external side effects occurred.
4. Fix the root cause in the failing branch and confirm the `JobInstance` is restartable.
5. Inspect checkpoints, input ranges, and produced outputs to prevent duplicate processing.
6. Execute compensation or clean up temporary data if required by the workflow.
7. Restart the same `JobInstance` when the goal is resuming unfinished work.
8. Run the verify/publish step only once all business conditions are satisfied.

Do not create a new `JobInstance` just to avoid the `FAILED` status when the actual goal is continuing the same job. Creating a new instance can cause all branches to re-run and repeat side effects.

## Conclusion

In parallel flows, a failure in one flow is aggregated into the split status and typically fails the job, preventing downstream steps on the success path from running. Sibling flows may still continue or have already completed; their committed transactions and side effects are not automatically rolled back.

To handle failures safely, monitor each branch's status, place retry/skip on the appropriate steps, keep intermediate outputs unpublished, use idempotency for non-transactional side effects, and design compensation when needed. Restart the same `JobInstance` based on each step's metadata and checkpoints, and publish results only after all mandatory branches complete and verification passes.
