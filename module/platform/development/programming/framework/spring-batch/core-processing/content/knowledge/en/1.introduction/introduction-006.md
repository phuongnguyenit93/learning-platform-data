# Run Identity and Restartability

In Spring Batch, a job can be launched many times. Some runs process a new data set, and some runs continue work that stopped because of an error. To distinguish these two cases, Spring Batch separates the **JobInstance** (the identity of one logical processing run) from the **JobExecution** (one specific execution of a JobInstance).

That distinction determines when a run is considered new, when Spring Batch allows a restart, and which checkpoint data is used to continue processing.

## 1. JobInstance and JobExecution

A **JobInstance** is determined by the job name together with the JobParameters marked as *identifying*. You can think of it as the identity of the work to be completed, for example importing data for one business date or processing one specific input file.

A **JobExecution** represents one attempt to execute a JobInstance. If the first attempt fails and is restarted, Spring Batch creates a new JobExecution but keeps the same JobInstance. Therefore, a JobInstance can have multiple JobExecutions over time.

| Component | Meaning | Example |
|---|---|---|
| Job | Defines the processing flow | `importOrders` |
| JobInstance | A logical piece of work, determined by the job and the identifying parameters | Importing orders for the date `2026-11-15` |
| JobExecution | One specific execution of a JobInstance | The first run fails, the next run continues |
| StepExecution | One specific execution of a step within a JobExecution | The step that reads and writes orders in the second run |
| ExecutionContext | State data saved to continue processing | The last read position, the number of records processed |

General relationship:

```text
Job: importOrders
        |
        +-- JobInstance (businessDate=2026-11-15)
                |
                +-- JobExecution #1  -> FAILED
                |       +-- StepExecution: loadOrders -> FAILED
                |
                +-- JobExecution #2  -> COMPLETED
                        +-- StepExecution: loadOrders -> COMPLETED
```

The two JobExecutions in the example belong to the same JobInstance because they have the same job name and the same identifying parameters. Each execution has its own identifier and status.

## 2. JobParameters Determine Identity

JobParameters pass input to the job. Each parameter has a name, a data type, a value, and a flag that determines whether it participates in identifying the JobInstance.

- An **identifying parameter** participates in creating the JobInstance identity. Changing the value of this parameter creates a different JobInstance.
- A **non-identifying parameter** is passed to the execution but does not change the JobInstance identity.

For example, the business date determines the data set to import, while the person who requested the run is just operational information:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("requestedBy", "nightly-scheduler", false)
    .toJobParameters();

jobLauncher.run(importOrdersJob, parameters);
```

The third argument of `addString` is the identifying flag. In the example above:

- `businessDate` is identifying. Running with the date `2026-11-16` creates a different JobInstance.
- `requestedBy` is non-identifying. Changing it from `nightly-scheduler` to `manual-user` does not create a new JobInstance.

Overloads that do not pass the identifying flag usually default the parameter to identifying. When designing parameters, you should state this flag explicitly to avoid inadvertently creating a new instance or inadvertently reusing an instance.

### Choosing Identifying Parameters

Choose values that describe the **business unit of work** the job must complete. For example:

| Case | Appropriate identifying parameter |
|---|---|
| Aggregating transactions by day | `businessDate` |
| Importing data from a file | `inputFile` or a stable file batch code |
| Processing data per customer | `tenantId` and `businessDate` |
| Generating a report by period | `reportPeriod` |

Information such as who clicked the run button, the machine name, the request time, or operational notes usually does not need to participate in identity, unless it truly creates a separate business unit of work.

Do not add a new timestamp or UUID to the identifying parameters on every launch just to avoid duplicate-instance errors. Doing so creates a new JobInstance on every attempt and prevents Spring Batch from recognizing that a later run is a restart of the earlier work.

One point to note: a non-identifying parameter can still affect how the job processes data. If its value changes between the failed run and the restart, two executions of the same JobInstance may perform the work with different configurations. Therefore, inputs that affect business results should be stable throughout the lifecycle of a JobInstance; if changing the input means a new piece of work, mark that parameter as identifying.

## 3. What Happens When You Launch with the Same Parameters?

When you call `JobLauncher.run(job, parameters)`, Spring Batch looks up the JobInstance by job name and identifying parameters, and then checks the state of the previous executions.

| Previous state of the JobInstance | Typical result when rerun with the same identifying parameters |
|---|---|
| Never run | Creates a JobInstance and the first JobExecution |
| Running | Rejects the duplicate launch, usually with `JobExecutionAlreadyRunningException` |
| Completed | Rejects rerunning the same instance, usually with `JobInstanceAlreadyCompleteException` |
| Failed or stopped | Can create a new JobExecution to restart, if the job allows restart and the metadata permits |
| Marked abandoned or in an unknown state | Should not be rerun arbitrarily; handle it according to the metadata state and operational rules |

The specific exceptions also depend on the metadata state and how the job is launched. The core point is: **the same identifying parameters mean the same JobInstance**. Spring Batch does not treat a new `run` call as a new piece of work just because it is a different call.

If the job has completed but the business needs to reprocess the data, create a new JobInstance with a new identifying parameter that has a clear meaning, such as a reprocessing run code or a data version. Do not change a business parameter merely to dodge the state check without recording the reason for the reprocessing.

## 4. How Does the Restart Mechanism Work?

A restart continues an unfinished JobInstance after a previous JobExecution failed or stopped. When restarting:

1. Spring Batch finds the JobInstance based on the job name and identifying parameters.
2. The repository checks the execution history and determines whether the instance can be restarted.
3. Spring Batch creates a new JobExecution for the same JobInstance.
4. Steps that have completed are usually skipped.
5. Steps that have not completed are executed again. A step with a checkpoint can continue from the saved state.

Example of a job with three steps:

```text
Execution #1
  validateInput  -> COMPLETED
  importRecords  -> FAILED
  publishReport  -> not run

Restart: Execution #2 (same JobInstance)
  validateInput  -> skipped because it is already COMPLETED
  importRecords  -> rerun from the saved checkpoint (if any)
  publishReport  -> runs for the first time
```

This is the default behavior commonly seen on restart. You can change how a step is rerun through step configuration, but you need to consider the impact on data that has already been written.

### Conditions for Being Restartable

- The job must allow restart. A job configured with `preventRestart()` will not allow restart after an execution fails.
- The JobInstance must be in a state that can be continued. A running execution, a completed instance, or an unsafe metadata state can all cause the request to be rejected.
- The step's rerun limits must still be in effect. For example, `startLimit` limits the number of times a step is allowed to start.
- The repository must still have the metadata of the previous run. If the metadata has been deleted, or the repository stores it only in memory and loses it when the application stops, Spring Batch cannot restore that history and checkpoint.

A restart creates a new JobExecution; it does not turn the failed execution into a successful one. The history of the attempts is still kept for monitoring and investigation.

## 5. Checkpoints and ExecutionContext

To continue from the middle of a step, Spring Batch needs to save the processing state. This state is usually placed in the **ExecutionContext** and saved through the JobRepository.

For example, a step reads a file chunk by chunk. After a chunk is committed successfully, the reader can save the read position or the necessary state. If the execution fails on the next chunk, a restart can continue from the nearest checkpoint instead of re-reading the entire file.

```text
Read chunk 1 -> write and commit -> save checkpoint 1
Read chunk 2 -> write and commit -> save checkpoint 2
Read chunk 3 -> error before commit

Restart:
  restore checkpoint 2
  continue from the data after chunk 2
```

Readers/writers that implement `ItemStream` can open, update, and close state through lifecycle methods such as `open`, `update`, and `close`. Many of the readers/writers that ship with Spring Batch support saving state; for custom components, you need to implement appropriate saving and restoring of state. If you turn off state saving, for example by configuring `saveState=false` on a reader that supports this option, you cannot expect the reader to resume at the correct earlier position on its own.

A checkpoint is usually tied to the chunk's commit boundary. Therefore, when designing for restart you need to understand clearly the transaction boundary and the order in which state is updated. Data committed before the error is usually kept; a chunk that has not committed is reprocessed according to the transaction and reader mechanisms.

### Why Must the JobRepository Be Durable?

The JobRepository stores metadata about the JobInstance, JobExecution, StepExecution, and ExecutionContext. In a real-world runtime environment, the repository usually uses a database so that the metadata persists across application restarts.

If you use a repository that stores data only in memory, the metadata can be lost when the process ends. In that case, the next run no longer has enough information to recognize the old instance or restore the checkpoint. Therefore, the ability to restart across multiple application launches depends on a durable repository configuration and on preserving Spring Batch's metadata tables.

## 6. Rerunning Completed Steps and Limiting the Number of Runs

By default, when restarting a JobInstance, steps that have completed are skipped. Two step configurations are commonly related to this behavior:

- `allowStartIfComplete(true)`: allows a completed step to be rerun when the job is restarted.
- `startLimit(n)`: limits the number of times a step is started.

An example in the Spring Batch 5 builder style:

```java
Step refreshReferenceData = new StepBuilder("refreshReferenceData", jobRepository)
    .tasklet(refreshTasklet, transactionManager)
    .allowStartIfComplete(true)
    .startLimit(3)
    .build();
```

`allowStartIfComplete(true)` is useful when a step needs to be performed again in a restart, for example refreshing reference data. Use it carefully with steps that have side effects such as sending email, making payments, calling external APIs, or writing data without a duplicate-prevention mechanism.

`startLimit(3)` limits the step to being started at most three times within the instance. When the limit is exceeded, Spring Batch refuses to start the step and the job can fail.

If the job has fully completed, launching again with the same identifying parameters is still blocked at the JobInstance level. `allowStartIfComplete` does not turn a completed JobInstance into an instance that can be relaunched from scratch.

## 7. Deliberately Creating a New JobInstance

Sometimes the business requirement is to rerun the whole job as a new piece of work, even though the job name and main input data are the same as the previous time. In that case you need a new identifying parameter, such as `reprocessVersion` or `run.id`.

Spring Batch provides `JobParametersIncrementer`; `RunIdIncrementer` is a common implementation that increments the `run.id` parameter. An incrementer is usually used by operations that request creating the *next instance* (for example `JobOperator.startNextInstance`). If you call `JobLauncher.run` directly, make sure the parameter set you pass in actually contains a new identifying value; merely configuring an incrementer does not mean every `run` call automatically increments `run.id`.

Example of the identity idea:

| Processing run | businessDate | reprocessVersion | Result |
|---|---|---:|---|
| First import | 2026-11-15 | 1 | JobInstance A |
| Restart after failure | 2026-11-15 | 1 | New execution of JobInstance A |
| Reprocessing on request | 2026-11-15 | 2 | JobInstance B |

Only increase the version when you truly want to create a new logical piece of work. If the previous execution failed only because of a transient error, restart the same JobInstance instead of increasing the version.

## 8. Example Lifecycle of an Order Import Job

Suppose the `importOrders` job receives `businessDate` and `inputFile` as identifying parameters. The operator launches the job with a fixed business date and input file.

The first time, the file validation step completes. The data import step processes some chunks and then runs into a database connection error. The first JobExecution ends with the status `FAILED`; the JobInstance still represents the work of importing that file.

After the error is fixed, the system relaunches with the same job name, `businessDate`, and `inputFile`. Spring Batch finds the old JobInstance and creates the next JobExecution. The file validation step, which has completed, is skipped. The data import step continues from the committed checkpoint if the reader and the repository support restoring state. When the remaining steps complete, the JobInstance reaches the completed state.

If the operator relaunches with the same parameters afterward, Spring Batch rejects it because the JobInstance has already completed. If the business requires importing the file again, deliberately create a new reprocessing code to create a different JobInstance, while making sure the data-writing process can handle duplicate records or has an appropriate data-replacement strategy.

## 9. Common Design Mistakes

| Practice | Consequence | Remedy |
|---|---|---|
| Adding a new timestamp to the identifying parameters on every run | Every attempt becomes a new JobInstance; you lose the ability to correctly restart the old instance | Use identifying parameters that are stable per unit of work |
| Mistakenly marking a business parameter as non-identifying | Two different input sets may be treated as the same JobInstance | Put every value that changes the unit of work into the identity |
| Changing a non-identifying parameter between restarts | The same JobInstance may run with different configuration or input | Keep the inputs that affect results stable throughout the instance lifecycle |
| Using only an in-memory repository in an environment that needs recovery after the application stops | Metadata and checkpoints may be lost | Use a durable JobRepository |
| A custom reader that does not save checkpoints | A restart may re-read from the beginning or fail to restore the correct position | Implement `ItemStream` and save the necessary state |
| Sending side effects without a duplicate-prevention mechanism | A restart may send or write repeatedly | Design idempotent operations or use a business key to prevent duplicates |
| Using `allowStartIfComplete` to rerun a completed job | Cannot get past the state rules at the JobInstance level | Create a new JobInstance when the business truly requires reprocessing |

A restart does not by itself guarantee that every external side effect happens only once. Spring Batch's transaction can protect operations within the same configured transaction, but calls to external services or to systems that do not participate in the transaction may have completed before the job records the checkpoint. For such operations, you should use an idempotency key, a unique business key, an outbox, or an appropriate reconciliation mechanism.

## 10. Decision Process When Operating

When a job needs to be rerun, determine the goal first:

1. **The previous execution is running:** check the process and the repository state; do not launch another execution of the same JobInstance.
2. **The previous execution failed or stopped:** check the cause of the error, the job's restartability, the step limit, and the checkpoint; then restart with the same identifying parameters.
3. **The JobInstance has completed but you need to process a new period/file:** pass new identifying parameters corresponding to the new unit of work.
4. **You need to reprocess the same period/file per a business request:** create an identifying parameter such as a new reprocessing code or version, and determine how to handle the data written earlier.
5. **You need to continue after the application or server restarts:** confirm that the JobRepository and the ExecutionContext are stored durably, and only then rely on the checkpoint to continue.

When monitoring operations, check the JobInstance, the JobExecutions belonging to that instance, the StepExecution state, and the ExecutionContext. Looking only at the state of the last execution can overlook the history of earlier attempts.

## Conclusion

JobParameters determine the identity of the work through the identifying flag. The JobInstance represents that logical piece of work, while each execution or restart creates its own JobExecution. When an execution fails or stops, Spring Batch can continue the same JobInstance by creating a new execution and restoring the checkpoint from the JobRepository. When the work has completed or a new business unit needs to be processed, create a new JobInstance with identifying parameters that have a clear meaning.

A good design keeps parameters stable throughout the restart process, stores metadata durably, handles checkpoints correctly, and protects side effects from being performed repeatedly.
