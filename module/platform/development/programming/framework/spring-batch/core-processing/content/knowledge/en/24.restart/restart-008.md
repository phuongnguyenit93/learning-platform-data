# A JobInstance cannot be restarted once COMPLETED in Spring Batch

In Spring Batch, a Job can be executed multiple times, but not every run is a restart. When a JobInstance has ended in **COMPLETED** status, Spring Batch considers that logical processing run finished. If the same Job is invoked again with the same identifying set of JobParameters, the framework refuses to create a new execution and typically throws JobInstanceAlreadyCompleteException.

This is intentional behavior to prevent duplicate processing of a JobInstance. To resume a failed or stopped Job, you restart that exact JobInstance using its original identifying JobParameters. To run a COMPLETED JobInstance again, you must create a **new JobInstance**, typically by adding an identifying parameter representing the new run.

This lesson explains the relationship among Job, JobInstance, and JobExecution; why COMPLETED cannot be restarted; how to distinguish restart from rerun; the role of identifying and non-identifying JobParameters; how to use RunIdIncrementer, JobParametersIncrementer, and JobOperator; and key considerations around idempotency, output data, and operations.

## 1. Distinguishing Job, JobInstance, and JobExecution

These three concepts are foundational for understanding why a COMPLETED JobInstance cannot be re-run with the same parameters.

- **Job** is the batch workflow definition, including the Job name, Steps, flow, and configuration.
- **JobInstance** represents one logical execution of a Job with a specific set of identifying JobParameters.
- **JobExecution** is a specific execution attempt of a JobInstance. A JobInstance can have multiple JobExecutions if an earlier attempt failed or stopped and was restarted.

You can visualize it as:

~~~text
Job: dailyImportJob
  |
  +-- JobInstance (businessDate=2026-11-15)
        |
        +-- JobExecution #1 -> FAILED
        |
        +-- JobExecution #2 -> COMPLETED
~~~

Both JobExecutions belong to the same JobInstance because they share the same identifying parameters. The second execution is the restart after the first execution failed.

If the application later runs again with the same identifying parameters, Spring Batch will not create JobExecution #3 because the JobInstance is already COMPLETED.

To process a new logical run, you must create a new JobInstance:

~~~text
Job: dailyImportJob
  |
  +-- JobInstance (businessDate=2026-11-15, run.id=1)
  |     +-- JobExecution #1 -> COMPLETED
  |
  +-- JobInstance (businessDate=2026-11-15, run.id=2)
        +-- JobExecution #2 -> STARTED / COMPLETED
~~~

Here the business date is the same, but `run.id` is a different identifying parameter, so these are two distinct JobInstances.

## 2. How is a JobInstance identified?

Spring Batch identifies a JobInstance by:

- Job name.
- The set of JobParameters marked as identifying.

Conceptually:

~~~text
JobInstance identity = Job name + identifying JobParameters
~~~

For example:

~~~java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15")
    .addString("sourceSystem", "CRM")
    .toJobParameters();
~~~

With this default way of adding parameters, values are marked identifying. Thus, the JobInstance is identified by the Job name together with `businessDate` and `sourceSystem`.

Running the Job again with the same name and the same identifying values resolves to the same JobInstance.

### Same parameters mean the same JobInstance

Example of two calls:

~~~java
jobLauncher.run(
    dailyImportJob,
    new JobParametersBuilder()
        .addString("businessDate", "2026-11-15")
        .addString("sourceSystem", "CRM")
        .toJobParameters()
);

jobLauncher.run(
    dailyImportJob,
    new JobParametersBuilder()
        .addString("businessDate", "2026-11-15")
        .addString("sourceSystem", "CRM")
        .toJobParameters()
);
~~~

Both calls use the same Job name and the same identifying parameters. If the JobInstance is already COMPLETED, the second call is not a new run; it is rejected.

If the JobInstance is currently running, the framework may throw JobExecutionAlreadyRunningException. If the previous execution FAILED or STOPPED and the Job is restartable, calling with the same parameters can create a new JobExecution on the existing JobInstance.

## 3. Why can't a COMPLETED JobInstance be restarted?

COMPLETED indicates the JobInstance finished successfully according to the final status recorded by JobRepository. Spring Batch uses this metadata to prevent an already-completed JobInstance from being executed again unintentionally.

Main reasons:

1. **Prevent duplicate processing:** the same data batch will not be written again simply because a scheduler re-sends the same request.
2. **Protect business state:** data already published or reconciled will not be regenerated unexpectedly.
3. **Preserve restart semantics:** restart is meant to resume unfinished work, not to create a fresh processing run after success.
4. **Protect metadata:** JobRepository can distinguish a new JobExecution of the same JobInstance from a new JobInstance.

Example daily file import Job:

- The run for `businessDate=2026-11-15` completes.
- The scheduler accidentally re-sends the exact same JobParameters.
- If the framework allowed running again, that day's data could be inserted, notifications sent, or files published a second time.
- Rejecting it helps detect duplicate run requests.

Common message:

~~~text
JobInstanceAlreadyCompleteException:
A job instance already exists and is complete for parameters ...
~~~

Exact message wording may vary by version, but the meaning is that the corresponding JobInstance is already complete.

### COMPLETED is a terminal state for the JobInstance

A JobInstance can have multiple JobExecutions when restarting after errors, but once the JobInstance reaches COMPLETED, it is no longer eligible to restart with the same identifying parameters.

To run again, determine whether this is a new logical processing run or a data correction action. Then create a new JobInstance with an appropriate identifying parameter.

## 4. Distinguishing restart and rerun

Both actions are often loosely called "re-running," but in Spring Batch they are different.

| Action | JobInstance | JobParameters | When to use |
|---|---|---|---|
| Restart | Unchanged | Keep identifying parameters | Prior execution FAILED or STOPPED and the Job allows restarting |
| Rerun as a new JobInstance | New | At least one identifying parameter differs | Need to reprocess a batch or create a new logical run |
| Call the same COMPLETED instance again | Unchanged | Unchanged | Rejected |
| Change a non-identifying parameter | Unchanged | Identifying set unchanged | Changes only auxiliary metadata, does not create a new instance |

### Example restart after FAILED

~~~text
JobInstance: importJob(businessDate=2026-11-15)

Execution 1:
  validateStep -> COMPLETED
  importStep   -> FAILED
  Job          -> FAILED

Restart with same identifying parameters:

Execution 2:
  validateStep -> skipped per default restart policy
  importStep   -> runs again
  Job          -> COMPLETED
~~~

This is a restart because the JobInstance remains one and the unfinished work is resumed.

### Example rerun after COMPLETED

~~~text
JobInstance 1:
  importJob(businessDate=2026-11-15, run.id=1)
  JobExecution -> COMPLETED

Request to re-run the same business date:

JobInstance 2:
  importJob(businessDate=2026-11-15, run.id=2)
  JobExecution -> runs as a new instance
~~~

This is a rerun. Spring Batch does not resume the first instance's checkpoints; it starts a new JobInstance. Therefore, you must control side effects and output data to avoid duplicate writes.

## 5. Creating a new JobInstance via an identifying JobParameter

The most direct way is adding a new identifying parameter, such as `run.id` or `reprocess.sequence`.

For example:

~~~java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15")
    .addString("sourceSystem", "CRM")
    .addLong("run.id", 2L)
    .toJobParameters();

jobLauncher.run(dailyImportJob, parameters);
~~~

Because `run.id` is an identifying parameter, the new parameter set creates a new JobInstance even though `businessDate` and `sourceSystem` match the previous run.

### Use meaningful parameters

Do not add a random parameter just to bypass an error without an operational policy. Parameter names should express why a new instance is created:

- `run.id`: run sequence number.
- `reprocess.id`: reprocessing request ID.
- `correction.version`: correction version.
- `source.snapshot`: source snapshot identifier.
- `reconciliation.id`: reconciliation run ID.

Choose an identifying parameter that aligns with what defines one logical processing run in the business domain.

### Distinguishing run ID and business key

`run.id` can distinguish run attempts; `businessDate` can be the business key of the data.

| businessDate | run.id | Meaning |
|---|---|---|
| 2026-11-15 | 1 | First processing run |
| 2026-11-15 | 2 | Re-run after adjustment |
| 2026-11-16 | 1 | First processing run of the new day |

Do not use run ID to replace a business key. The two parameter types serve two different purposes.

## 6. Identifying and non-identifying JobParameters

Spring Batch lets you mark whether a JobParameter participates in identifying a JobInstance.

For example:

~~~java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("sourceSystem", "CRM", true)
    .addString("requestedBy", "operator-01", false)
    .addLong("run.id", 2L, true)
    .toJobParameters();
~~~

The third argument of the builder methods is the `identifying` flag:

- `true`: parameter participates in identifying the JobInstance.
- `false`: parameter does not participate in identifying the JobInstance.

In the example:

- `businessDate` and `sourceSystem` are identifying.
- `run.id` is identifying.
- `requestedBy` is non-identifying.

If only `requestedBy` changes while keeping the identifying parameters, the JobInstance remains the same. If that instance is already COMPLETED, changing `requestedBy` does not allow re-running it.

### Non-identifying parameters do not create a new instance

For example:

~~~java
JobParameters first = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("requestedBy", "scheduler", false)
    .toJobParameters();

JobParameters second = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("requestedBy", "operator", false)
    .toJobParameters();
~~~

Both parameter sets have the exact same identifying set. Therefore, they represent the same JobInstance.

Use non-identifying parameters for operational metadata that does not change processing identity, such as requester, correlation ID, or notes. Do not use them as a run ID when a new JobInstance is needed.

## 7. Using RunIdIncrementer

Spring Batch provides `RunIdIncrementer` to increment an identifying parameter named `run.id`.

You can attach an incrementer to a Job:

~~~java
@Bean
Job dailyImportJob(
        JobRepository jobRepository,
        Step importStep,
        Step publishStep) {

    return new JobBuilder("dailyImportJob", jobRepository)
        .start(importStep)
        .next(publishStep)
        .incrementer(new RunIdIncrementer())
        .build();
}
~~~

`RunIdIncrementer` builds the next JobParameters by incrementing `run.id`. If no prior value exists, it initializes the value according to the implementation's rule, typically 1.

For example:

~~~text
Previous run:
  businessDate = 2026-11-15
  run.id        = 1

Next parameter set:
  businessDate = 2026-11-15
  run.id        = 2
~~~

### Incrementers do not run automatically on JobLauncher.run()

This is an easy point to misunderstand. Declaring an incrementer on a Job does not mean Spring Batch automatically increments `run.id` every time `jobLauncher.run(job, sameParameters)` is called.

`JobLauncher.run()` uses the exact JobParameters passed in by the caller. The incrementer is used by mechanisms that obtain the next parameter set, such as `JobOperator.startNextInstance(jobName)`.

If the application calls `JobLauncher` directly, the application must construct the new JobParameters itself or invoke an appropriate next-parameter mechanism.

## 8. Using a custom JobParametersIncrementer

When rules for creating a new instance are more complex than incrementing a single number, you can implement `JobParametersIncrementer`.

The interface has one method:

~~~java
public interface JobParametersIncrementer {
    JobParameters getNext(JobParameters parameters);
}
~~~

Example incrementing `reprocess.sequence`:

~~~java
public class ReprocessIncrementer
        implements JobParametersIncrementer {

    @Override
    public JobParameters getNext(JobParameters parameters) {
        long nextSequence = 1L;

        if (parameters != null
                && parameters.getLong("reprocess.sequence") != null) {
            nextSequence =
                parameters.getLong("reprocess.sequence") + 1L;
        }

        return new JobParametersBuilder(parameters)
            .addLong("reprocess.sequence", nextSequence, true)
            .toJobParameters();
    }
}
~~~

Attach it to the Job:

~~~java
return new JobBuilder("dailyImportJob", jobRepository)
    .start(importStep)
    .incrementer(new ReprocessIncrementer())
    .build();
~~~

A custom incrementer can preserve the business date and source system while incrementing the reprocessing sequence.

Ensure the new parameter is genuinely identifying. Calling `addLong` with `identifying=false` leaves the JobInstance unchanged.

## 9. Using JobOperator.startNextInstance()

If a Job is configured with a `JobParametersIncrementer`, `JobOperator` can create and launch the next JobInstance.

Conceptual example:

~~~java
long executionId = jobOperator.startNextInstance("dailyImportJob");
~~~

This requires:

- The Job name is registered in `JobRegistry` or the corresponding `JobOperator` configuration.
- The Job has a `JobParametersIncrementer`.
- `JobOperator` has required dependencies such as `JobLauncher`, `JobRepository`, and `JobRegistry`.
- The next parameter set yields a valid new JobInstance.

`startNextInstance` is a good fit for schedulers or operational tools that want to launch the next instance according to the Job's incrementer.

### Comparison with JobLauncher.run()

| API | Responsibility |
|---|---|
| `JobLauncher.run(job, parameters)` | Runs the Job with the exact JobParameters supplied by the caller |
| `JobOperator.startNextInstance(jobName)` | Obtains the next parameters from the incrementer and launches a new instance |
| `JobOperator.restart(executionId)` | Restarts a restart-eligible JobExecution |
| `JobExplorer` | Queries JobInstance, JobExecution, and StepExecution metadata |

Do not use `startNextInstance` to restart a specific FAILED execution. It creates the next instance using the incrementer. To restart a failed execution, use the restart mechanism appropriate for that execution and keep the JobInstance's identifying parameters.

## 10. Restarting a FAILED or STOPPED JobInstance

If a JobInstance is not finished and the previous execution is in a restartable status, Spring Batch can create a new JobExecution on the same JobInstance.

For example:

~~~java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15")
    .addString("sourceSystem", "CRM")
    .toJobParameters();

jobLauncher.run(dailyImportJob, parameters);
~~~

If the previous run with the exact same identifying parameters FAILED and the Job is not configured to prevent restarts, the call can create a new execution to continue.

In operations, you can use:

~~~java
long newExecutionId = jobOperator.restart(failedExecutionId);
~~~

`restart` takes the ID of the JobExecution to restart. The execution must be in an appropriate status, such as FAILED or STOPPED, and the Job must be restartable.

Do not pass the execution ID of a COMPLETED JobExecution expecting it to run again. A COMPLETED instance is no longer restartable.

### The Job must allow restarting

A Job can be configured to prevent restarting:

~~~java
return new JobBuilder("oneShotJob", jobRepository)
    .start(oneTimeStep)
    .preventRestart()
    .build();
~~~

If the previous execution failed, this Job cannot be restarted normally. `preventRestart()` is not a way to allow reruns after COMPLETED; it restricts restarting a failed JobInstance.

If a new processing run is needed, create a new JobInstance with new identifying parameters and explicitly assess business impact.

## 11. allowStartIfComplete does not unlock a COMPLETED JobInstance

A Step can be configured with:

~~~java
@Bean
Step refreshReferenceStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet refreshTasklet) {

    return new StepBuilder("refreshReferenceStep", jobRepository)
        .tasklet(refreshTasklet, transactionManager)
        .allowStartIfComplete(true)
        .build();
}
~~~

`allowStartIfComplete(true)` allows an already-COMPLETED Step to run again during a **restart of an unfinished JobInstance** when the flow and restart policy bring the Job back to that Step.

It does not allow relaunching a JobInstance whose final JobExecution is already COMPLETED.

Distinguish clearly:

- FAILED/STOPPED JobInstance: can restart if the Job allows it.
- COMPLETED Step within a restarting JobInstance: can run again if `allowStartIfComplete(true)`.
- COMPLETED JobInstance: cannot restart with the same identifying parameters, even if a Step has `allowStartIfComplete(true)`.

These are two different scopes: Step re-run policy inside a restartable JobInstance versus the rule against re-running an already-completed JobInstance.

## 12. Flows can make a Job COMPLETED even if a Step failed

When reading metadata, examine the final status of the JobExecution, not just an individual Step.

For example, a flow can transition from a failed ExitStatus to a terminal `end()` to treat the error branch as handled:

~~~java
return new JobBuilder("fileValidationJob", jobRepository)
    .start(validateStep)
        .on("COMPLETED").to(importStep)
    .from(validateStep)
        .on("FAILED").to(recordRejectedFileStep)
    .from(validateStep)
        .on("*").fail()
    .from(recordRejectedFileStep)
        .on("COMPLETED").end()
    .from(recordRejectedFileStep)
        .on("*").fail()
    .end()
    .build();
~~~

In the example, a rejected file can cause the validation Step to fail, yet the rejection-handling branch completes and the Job ends COMPLETED under the flow policy.

Once the final JobExecution is COMPLETED, the JobInstance is considered finished. You cannot restart the same instance merely because an internal Step had FAILED status.

If business logic wants the Job to be treated as failed so it can restart after fixing the cause, design an appropriate terminal transition, such as `fail()`, instead of `end()`.

## 13. Do not use non-identifying parameters to force a rerun

A common mistake is adding a new parameter while marking it non-identifying:

~~~java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addLong("rerunSequence", 2L, false)
    .toJobParameters();
~~~

Although `rerunSequence` has a different value, it does not participate in JobInstance identity. If the JobInstance with this `businessDate` is already COMPLETED, the run is still rejected.

The right way when you truly want to create a new instance:

~~~java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addLong("rerunSequence", 2L, true)
    .toJobParameters();
~~~

Only change the identifying flag intentionally for business reasons. Do not turn every operational parameter into an identifying parameter, as that creates excessive JobInstances and complicates history management.

## 14. Designing parameters for controlled reruns

A daily Job might use:

~~~java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("sourceSystem", "CRM", true)
    .addLong("run.id", 2L, true)
    .addString("requestedBy", "operator", false)
    .addString("reason", "Corrected source mapping", false)
    .toJobParameters();
~~~

In this example:

- `businessDate` identifies the business date.
- `sourceSystem` identifies the data source.
- `run.id` creates a new JobInstance for the reprocessing run.
- `requestedBy` and `reason` are operational metadata that do not alter identity.

Decide on the rule for advancing the run ID:

- Automatically increment via an incrementer.
- Obtain a sequence from an orchestration system.
- Use a reprocess request ID created by an operator.
- Use a correction version managed in the database.

Avoid arbitrary timestamps if the system needs to associate re-runs with a specific remediation request. A meaningful reprocess ID is usually easier to audit.

## 15. Rerunning does not automatically make output data safe

Creating a new JobInstance only resolves execution identity in JobRepository. It does not automatically delete old outputs, roll back committed data, or prevent writers from writing duplicates.

Example Job writing to a results table:

~~~sql
INSERT INTO daily_customer_summary
    (business_date, customer_id, total_amount)
VALUES
    (:businessDate, :customerId, :totalAmount)
~~~

If re-run for the same `businessDate` using a new `run.id`, rows may duplicate or violate unique constraints.

Before allowing reruns, define the data policy:

- Delete prior results within an authorized scope and recompute.
- Write results into a staging table keyed by run ID, then publish the selected version.
- Use upsert if business rules allow updating results.
- Use unique business keys and inspect existing content.
- Maintain version history and active status flags.
- Separate technical run IDs from business batch codes.

Do not blindly delete all old data. Scope deletions by business key, batch ID, or version, and ensure downstream consumers understand which version is authoritative.

### Separating run ID from business key

For example, a results table might store:

| Column | Role |
|---|---|
| `business_date` | Business date |
| `customer_id` | Business record key |
| `run_id` | Execution run that produced the result |
| `is_current` | Currently active version |
| `processed_at` | Processing timestamp |

Specific schema design depends on the system. The key point is that reruns can produce new data, yet there must still be a rule for selecting the authoritative result.

## 16. Rerunning files and external resources

If a Job produces output files, re-running with a new JobInstance may overwrite the old file or generate multiple conflicting files.

Several approaches:

- Include business date and run ID in the filename.
- Write into an isolated staging directory per run.
- Publish the file only after all Steps succeed.
- Maintain a manifest recording the output version.
- Use a promotion step to select the approved result.
- Retain old outputs per retention policies.

For example:

~~~java
Path output = outputDirectory.resolve(
    "customer-summary-"
        + businessDate
        + "-run-"
        + runId
        + ".csv"
);
~~~

Distinct filenames prevent overwrites during reruns. A later publish Step can update a manifest or move the file to its official location.

For APIs, message brokers, or payment systems, idempotency keys or versioning mechanisms are required. A new JobInstance does not make target systems forget that a business operation already happened.

## 17. Handling duplicate launch requests from schedulers

A scheduler may submit the same JobParameters multiple times due to timeouts, retries, or schedule configuration. When the JobInstance is already COMPLETED, Spring Batch rejects repeated requests. This is a helpful safeguard.

Applications should distinguish:

- Duplicate request for the same run: keep identical identifying parameters.
- Restart after FAILED/STOPPED: keep the original identifying parameters.
- Intentional rerun after COMPLETED: create a new identifying parameter.
- New business batch: change business keys or identifying parameters accordingly.

Do not generate a new `run.id` on every scheduler retry if the intent is merely resending the same run. Doing so turns duplicate requests into new JobInstances and can process data twice.

### Use a stable request ID

A scheduler can generate a `runRequestId` before invoking the Job and keep that ID unchanged across command-delivery retries. If the request was already accepted or the Job already completed, retries still map to the same JobInstance.

When a fresh rerun is needed, generate a new request ID through the approval or orchestration workflow.

## 18. Querying JobInstance and JobExecution before running

Before deciding between restart and rerun, operational tools should inspect the current state.

You can use `JobExplorer`:

~~~java
List<JobInstance> instances =
    jobExplorer.getJobInstances("dailyImportJob", 0, 20);

for (JobInstance instance : instances) {
    List<JobExecution> executions =
        jobExplorer.getJobExecutions(instance);

    for (JobExecution execution : executions) {
        log.info(
            "instanceId={}, executionId={}, status={}, exitStatus={}",
            instance.getInstanceId(),
            execution.getId(),
            execution.getStatus(),
            execution.getExitStatus()
        );
    }
}
~~~

The snippet illustrates querying. In real applications, filter by business keys or JobParameters to locate the exact instance instead of relying only on a recent list.

Information to check:

- Job name.
- Identifying JobParameters.
- JobInstance ID.
- JobExecutions belonging to the instance.
- Latest execution status.
- Which StepExecution FAILED or STOPPED.
- ExitStatus and failure exceptions.
- Whether the Job is restartable.

Do not create a new instance simply because you do not know the old instance's state. First classify whether this is a duplicate request, a valid restart, or a business rerun.

## 19. Common exceptions when relaunching

Common errors include:

| Exception | Typical meaning | Resolution |
|---|---|---|
| `JobInstanceAlreadyCompleteException` | JobInstance is already COMPLETED for these identifying parameters | If rerun is needed, create a new JobInstance with a different identifying parameter |
| `JobExecutionAlreadyRunningException` | An execution of the same instance is currently running | Inspect current status; do not launch the same instance concurrently |
| `JobRestartException` | Cannot restart execution/instance under current policy | Check `preventRestart`, status, and restartability |
| `JobParametersInvalidException` | JobParameters invalid per validator | Fix input parameters |
| `NoSuchJobException` | Job not found by name | Check `JobRegistry` or configuration |
| `JobParametersNotFoundException` | Required parameter missing in orchestration call | Check incrementer configuration or request |

Do not catch `JobInstanceAlreadyCompleteException` and automatically append a new run ID to re-run. Doing so can mask duplicate scheduler submissions and create duplicate side effects. Let the orchestration layer decide whether a request is a duplicate or an explicitly requested rerun.

## 20. Should you delete metadata to re-run the same JobInstance?

Do not directly delete rows from Spring Batch metadata tables to force a COMPLETED JobInstance to run again.

JobRepository maintains relationships across:

- `BATCH_JOB_INSTANCE`.
- `BATCH_JOB_EXECUTION`.
- `BATCH_JOB_EXECUTION_PARAMS`.
- `BATCH_STEP_EXECUTION`.
- `BATCH_JOB_EXECUTION_CONTEXT`.
- `BATCH_STEP_EXECUTION_CONTEXT`.

These tables have foreign keys and state links. Deleting partial metadata can leave orphaned rows, break audit history, or leave restarts/checkpoints inconsistent.

If reprocessing is needed, create a new JobInstance using an appropriate identifying parameter. If metadata maintenance is required, use a separately designed and tested retention/cleanup procedure, never manual edits while Jobs are active.

## 21. Creating a new JobInstance with JobLauncher

Example service orchestrating reruns:

~~~java
@Service
public class ImportJobLauncher {

    private final JobLauncher jobLauncher;
    private final Job dailyImportJob;

    public ImportJobLauncher(
            JobLauncher jobLauncher,
            Job dailyImportJob) {
        this.jobLauncher = jobLauncher;
        this.dailyImportJob = dailyImportJob;
    }

    public JobExecution rerun(
            LocalDate businessDate,
            long runId,
            String sourceSystem) throws Exception {

        JobParameters parameters = new JobParametersBuilder()
            .addString("businessDate", businessDate.toString(), true)
            .addString("sourceSystem", sourceSystem, true)
            .addLong("run.id", runId, true)
            .toJobParameters();

        return jobLauncher.run(dailyImportJob, parameters);
    }
}
~~~

The caller must supply a new, valid run ID. In real systems, verify permissions and rerun reason, audit the request, and define how the new run's output will be published.

Do not auto-increment the run ID inside an HTTP retry or message retry of the same request. A run ID should be assigned once per logical rerun request and remain stable across retries of that request.

## 22. Testing COMPLETED and rerun behavior

Test both rejection behavior and creating a new instance.

### Test 1: running with the same parameters after COMPLETED

1. Launch the Job with identifying parameters P.
2. Verify the JobExecution finishes COMPLETED.
3. Call the same Job again with the same P.
4. Verify the second call is rejected with `JobInstanceAlreadyCompleteException`.
5. Verify no new JobExecution is created for the same instance.

### Test 2: changing a non-identifying parameter

1. Run the Job with `businessDate` as an identifying parameter.
2. Mark `requestedBy` as non-identifying.
3. Run again with the same `businessDate` but a different `requestedBy`.
4. Verify it resolves to the same JobInstance.
5. If the instance is already COMPLETED, verify the launch is rejected.

### Test 3: adding an identifying run ID

1. Run the Job with `businessDate` and `run.id=1`.
2. Verify COMPLETED.
3. Run with the same `businessDate` and `run.id=2`.
4. Verify a new JobInstance is created.
5. Verify output is not duplicated beyond policy.

### Test 4: restarting a FAILED instance

1. Run the Job with parameters P and make a Step fail.
2. Verify the JobExecution is FAILED.
3. Fix the error condition.
4. Run again with the same P or call `JobOperator.restart(executionId)`.
5. Verify the new JobExecution belongs to the same JobInstance.
6. Verify completed Steps and checkpoints are handled properly.

### Test 5: allowStartIfComplete

Create a JobInstance that fails at a later Step while an earlier Step is COMPLETED with `allowStartIfComplete` enabled. Restart the JobInstance and verify that Step runs again as configured. After the whole JobInstance becomes COMPLETED, calling again with the same parameters must still be rejected.

### Test 6: incrementer

Test `RunIdIncrementer` or a custom incrementer:

- No initial run ID.
- Existing run ID.
- Business key parameters are preserved.
- The incremented parameter is identifying.
- Two calls to `startNextInstance` create two distinct JobInstances.
- Calling `JobLauncher.run` with the same parameters does not auto-increment `run.id`.

## 23. Procedure for deciding between restart and rerun

When receiving a request to "re-run a Job," determine the intent first:

1. **Query JobInstance:** find the exact Job name and identifying parameters.
2. **Check the latest execution:** determine whether it is FAILED, STOPPED, COMPLETED, or currently running.
3. **If FAILED/STOPPED:** check restartability and reuse the original identifying parameters.
4. **If currently running:** do not launch another execution on the same instance; inspect the active execution.
5. **If COMPLETED:** do not restart the same instance; decide whether a new logical run is needed.
6. **If a rerun is needed:** create a meaningful new identifying parameter, such as `run.id` or `reprocess.id`.
7. **Check output data:** decide on upsert, staging, versioning, or controlled cleanup.
8. **Keep request ID stable:** avoid creating new instances when a scheduler simply retries the same request.
9. **Audit:** record requester, reason, and run ID.
10. **Reconcile outcomes:** verify final data reflects the authorized run.

## 24. Common design mistakes

### Calling JobLauncher again with the same parameters after COMPLETED

The same identifying parameters point to the same JobInstance. Spring Batch refuses to create a new execution. If a rerun is needed, create a new instance.

### Changing a non-identifying parameter and expecting a new instance

Non-identifying parameters do not participate in identity. Changing `requestedBy` or correlation ID does not change the JobInstance.

### Expecting RunIdIncrementer to auto-increment during JobLauncher.run()

An incrementer does not automatically modify parameters passed by the caller. It is invoked when requesting the next parameter set through an incrementer-aware mechanism.

### Using restart for an already-completed Job

Restart is for eligible failed or stopped executions. A COMPLETED JobInstance cannot be restarted with the same identifying parameters.

### Using allowStartIfComplete to re-run the entire Job

This option controls a COMPLETED Step inside a restarting JobInstance. It does not unlock a COMPLETED JobInstance.

### Generating a new run ID on every scheduler retry

Duplicate requests can become new JobInstances and process the same data multiple times. Keep request IDs stable for the same logical request.

### Rerunning without handling output data

A new JobInstance does not erase old outputs. Writers may create duplicates, violate unique constraints, or publish the wrong version.

### Deleting metadata tables to force re-execution

This can break JobRepository links, checkpoints, and audit trails. Use new identifying parameters and a controlled rerun workflow.

### Using random timestamps as identity without auditing

Timestamps create new instances without explaining why a rerun occurred. Use a meaningful run request ID or correction version and record the reason.

## 25. Key points to remember

- A JobInstance is identified by Job name and identifying JobParameters.
- A JobInstance can have multiple JobExecutions when restarting after FAILED or STOPPED.
- Once a JobInstance is COMPLETED, relaunching with the same identifying parameters is rejected with `JobInstanceAlreadyCompleteException`.
- Restart resumes an unfinished JobInstance; rerun creates a new JobInstance.
- Add a new identifying parameter like `run.id` or `reprocess.id` to create a new instance.
- Changing non-identifying parameters does not create a new JobInstance.
- `RunIdIncrementer` and `JobParametersIncrementer` generate the next parameter set; `JobLauncher.run` does not call incrementers automatically.
- `JobOperator.startNextInstance` uses the incrementer to launch the next instance; `JobOperator.restart` takes a restart-eligible execution ID.
- `preventRestart` restricts restarting after failure; it is not a rerun mechanism after COMPLETED.
- `allowStartIfComplete` applies to Steps within a restart of an unfinished JobInstance, not restarting a COMPLETED JobInstance.
- Flows using `end()` can end a Job as COMPLETED even if an earlier Step failed; check the JobExecution's final status.
- A new JobInstance does not automatically protect outputs from duplicates; idempotency, versioning, staging, or upserts are required.
- Do not delete JobRepository metadata to force re-execution.
- Inspect status before deciding between restart and rerun, and audit every reprocessing run.

Spring Batch rejects restarting a COMPLETED JobInstance to preserve the meaning of completion and prevent duplicate execution. When resuming unfinished work, restart the failed or stopped JobInstance with the same identifying parameters. When reprocessing an already-completed logical run, create a new JobInstance with a meaningful identifying parameter and control output data so the new run is safe.

