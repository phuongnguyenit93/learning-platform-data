# Context When a Step Fails in Spring Batch

In Spring Batch, `ExecutionContext` stores the state needed so a job or step can resume after stopping or failing. When a step processes successfully, the context may contain the reader's checkpoint, the last processed key, or information that needs to be passed to the next step. When a step fails partway through, it is important to know which values have been durably saved, which values belong to an uncommitted chunk, and which data can be restored on restart.

`ExecutionContext` is not a memory area that automatically persists every application change. Spring Batch manages context persistence at points in the job/step lifecycle, typically tied to chunk commit boundaries and execution update flows. Therefore, when investigating failures, distinguish **step context**, **job context**, committed checkpoints, and changes that exist only in memory.

## 1. What Is ExecutionContext?

`ExecutionContext` is a key-value storage area bound to a job or step execution. Batch components use it to store values that must survive across invocations or be restored on restart.

For example, a file reader can store the number of lines read; a data-processing step can store the current batch code; a summary step can store the path of the generated report file.

```java
ExecutionContext context = stepExecution.getExecutionContext();
context.putLong("lastProcessedId", 12500L);
context.putString("inputFile", "orders-2026-11-15.csv");
```

`ExecutionContext` supports primitive values and objects compatible with the serializer in use. Data is persisted in the repository according to execution scope. With the default JDBC repository, context metadata is stored in tables such as `BATCH_STEP_EXECUTION_CONTEXT` and `BATCH_JOB_EXECUTION_CONTEXT`.

The context should hold small state needed for recovery. Do not use it as a place to store full business data, large object graphs, connections, streams, service beans, or non-serializable resources.

## 2. Distinguishing StepExecutionContext and JobExecutionContext

Spring Batch has two main context scopes:

| Context | Bound to | Purpose |
| --- | --- | --- |
| `StepExecution.getExecutionContext()` | A specific `StepExecution` | Stores checkpoints and private state of that step. |
| `JobExecution.getExecutionContext()` | A specific `JobExecution` | Stores job-scoped state, usable between steps within the same execution. |

For example, a job with three steps:

```text
JobExecution
  JobExecutionContext
       |
       +-- ValidateStep / StepExecution
       |       StepExecutionContext
       |
       +-- ImportStep / StepExecution
       |       StepExecutionContext
       |
       +-- ReportStep / StepExecution
               StepExecutionContext
```

Each step has its own context. `ImportStep` does not automatically see every key in `ValidateStep`'s context. If you need to move certain values from a previous step to the job context for a later step to read, use `ExecutionContextPromotionListener` or update the job context through an appropriate mechanism.

The job context belongs to a single `JobExecution`, not a permanent shared store across all runs of a `JobInstance`. On restart, Spring Batch can initialize a new execution from the saved state of the previous execution per the repository's restart mechanism. Therefore, understand clearly what data is inherited in the same restart stream and do not treat the context as a long-term business repository.

## 3. When Is the Context Saved?

With a chunk-oriented step, Spring Batch updates step state and execution context at chunk processing boundaries. Readers/writers implementing `ItemStream` can write checkpoints via the `update(ExecutionContext)` callback. The step saves the context to `JobRepository` along with execution metadata according to the step's transaction mechanism.

General lifecycle of a chunk:

```text
BEGIN CHUNK TRANSACTION
        |
        v
READ -> PROCESS -> WRITE
        |
        v
ItemStream.update(step ExecutionContext)
        |
        v
JobRepository updates execution/context
        |
        v
COMMIT
```

If the transaction commits successfully, that chunk's checkpoint is durably saved. If the transaction rolls back and metadata participates in the corresponding transaction, the metadata updates of the uncommitted chunk are also rolled back. In that case, the previously committed checkpoint is the reliable mark for restart.

With a tasklet step, each tasklet execution is also coordinated in a transaction per step configuration. The context is saved according to the step's update lifecycle; do not assume every in-memory change is automatically written to the repository the moment a line of code calls `putString()`.

The job context is usually updated and saved at job execution management points, such as when a step ends or when a component explicitly updates the repository. If a step fails, check the exact timing of the context update and which transaction committed before concluding that a key can be used on restart.

## 4. What Happens to StepExecutionContext When a Step Fails?

Suppose a step reads data in chunks of 100 items. The first two chunks commit, but the third chunk encounters an error:

```text
Chunk 1: items 1..100   -> write data + checkpoint 100 -> COMMIT
Chunk 2: items 101..200 -> write data + checkpoint 200 -> COMMIT
Chunk 3: items 201..300 -> error at item 260 -> ROLLBACK
```

If the reader saves checkpoints at chunk boundaries, the durable `StepExecutionContext` will reflect the most recently committed checkpoint, for example item 200. Uncommitted context changes of the third chunk will not become a durable checkpoint. On restart, the reader can restore from the checkpoint after item 200 and re-read the work of the third chunk.

This depends on the reader actually implementing and using checkpointing properly. A reader that only keeps a pointer in memory without writing state to `ExecutionContext` cannot automatically restore its exact position solely through Spring Batch.

A failed step still has a `StepExecution` and a context attached to it. The context can be used for diagnostics, viewing the last checkpoint, or serving as input for restart. However, do not treat values just written to an in-memory object before the error occurred as durably saved data.

## 5. JobExecutionContext When a Step Fails

The job context spans the entire job execution. It can hold data that steps need to share, such as a batch code, input file name, or output path. When a step fails, the job context may still hold values that were saved earlier.

Example:

```text
JobExecutionContext
  batchId = BATCH-20261115
  inputFile = orders.csv

ValidateStep: COMPLETED
  StepExecutionContext
    validRecordCount = 1200

ImportStep: FAILED
  StepExecutionContext
    lastProcessedId = 800

ReportStep: not yet run
```

In this example, the job context may keep `batchId` and `inputFile` that were set earlier. `ImportStep` has its own context with the last saved checkpoint. `ReportStep` has not run yet, so there are no results from that step.

Do not assume that every key written to the job context right before the step failed was saved. If the job context was modified inside a callback or running logic, verify when `JobRepository` updates the context and the transaction state. When passing data from step to step, use promotion and verify the step status before relying on the key.

## 6. Example of a Reader Saving Checkpoints Using ItemStream

A restartable reader typically implements `ItemStreamReader<T>`. The following example illustrates a reader reading a list of records by position and saving the read position in the step context:

```java
public class CheckpointingOrderReader
        implements ItemStreamReader<Order> {

    private static final String INDEX_KEY = "orderReader.currentIndex";

    private final List<Order> orders;
    private int currentIndex;

    public CheckpointingOrderReader(List<Order> orders) {
        this.orders = orders;
    }

    @Override
    public void open(ExecutionContext executionContext) {
        if (executionContext.containsKey(INDEX_KEY)) {
            currentIndex = executionContext.getInt(INDEX_KEY);
        } else {
            currentIndex = 0;
        }
    }

    @Override
    public Order read() {
        if (currentIndex >= orders.size()) {
            return null;
        }
        return orders.get(currentIndex++);
    }

    @Override
    public void update(ExecutionContext executionContext) {
        executionContext.putInt(INDEX_KEY, currentIndex);
    }

    @Override
    public void close() {
        // Release resources if the reader opens files/connections.
    }
}
```

`open()` restores the index from the saved context; `read()` returns the next item; `update()` writes the current index to checkpoint. The example uses a fixed list to focus on the `ItemStream` API. In production, the reader must read from a source with a stable order and save a checkpoint meaningful to that source, such as a file line position or the last read key.

If the chunk containing items 1 through 100 commits successfully, the context can save index 100. If the next chunk fails before commit, the restart will use the most recent durable checkpoint. Do not increment a durable checkpoint in an external system before the chunk transaction confirms the corresponding data.

## 7. How to Read Context After a Step Fails

After a job ends with status `FAILED`, the application can query the execution via `JobExplorer` or obtain the execution object from the launch flow. For example:

```java
JobExecution execution = jobExplorer.getJobExecution(jobExecutionId);

if (execution != null) {
    ExecutionContext jobContext = execution.getExecutionContext();

    for (StepExecution stepExecution : execution.getStepExecutions()) {
        ExecutionContext stepContext = stepExecution.getExecutionContext();

        System.out.println("step=" + stepExecution.getStepName());
        System.out.println("status=" + stepExecution.getStatus());

        if (stepContext.containsKey("lastProcessedId")) {
            System.out.println(
                "lastProcessedId=" + stepContext.getLong("lastProcessedId")
            );
        }
    }

    if (jobContext.containsKey("batchId")) {
        System.out.println("batchId=" + jobContext.getString("batchId"));
    }
}
```

This is an example of reading context for diagnostics. In real systems, do not print the entire context to logs if it contains sensitive data. Read only necessary keys and protect access permissions to the metadata repository.

When re-querying with `JobExplorer`, the result reflects data saved by the repository. It is more reliable than simply reading a `StepExecution` object left in memory on the failed thread, because the in-memory object may hold uncommitted changes.

## 8. Moving Data from Step Context to Job Context

A step may produce a value needed in the next step. For example, `ValidateStep` counts valid records, while `ImportStep` needs to read that count for logging or condition checks. You can use `ExecutionContextPromotionListener` to promote selected keys from the step context to the job context.

```java
@Bean
ExecutionContextPromotionListener validationContextPromotionListener() {
    ExecutionContextPromotionListener listener =
        new ExecutionContextPromotionListener();
    listener.setKeys(new String[] {"validRecordCount", "validationReport"});
    listener.setStatuses(new String[] {"COMPLETED"});
    return listener;
}
```

Attach the listener to the step:

```java
@Bean
Step validateStep(JobRepository jobRepository,
                  PlatformTransactionManager transactionManager,
                  ItemReader<Record> reader,
                  ItemWriter<Record> writer,
                  ExecutionContextPromotionListener validationContextPromotionListener) {
    return new StepBuilder("validateStep", jobRepository)
        .<Record, Record>chunk(100, transactionManager)
        .reader(reader)
        .writer(writer)
        .listener(validationContextPromotionListener)
        .build();
}
```

Per the configuration above, the specified keys are promoted only when the step's exit status matches `COMPLETED`. This is a commonly used safe default: data is promoted to the job context only when the step finishes in an accepted status.

If the step fails, the default listener does not promote the keys because the `FAILED` status does not match `COMPLETED`. Other statuses can be configured, but only do so when promoted data has clear meaning even if the step failed. Avoid accidentally promoting an incomplete checkpoint as a business result trusted by the next step.

## 9. What Happens When Restarting a Job?

Restarting creates a new `JobExecution` for the same `JobInstance` if the job and prior status allow restarting. Spring Batch uses previous execution metadata to restore necessary state, including job context and step context per restart rules.

Example:

```text
JobInstance: importOrders (businessDate=2026-11-15)
    |
    +-- JobExecution 1: FAILED
    |      JobExecutionContext: batchId=B-15
    |      ImportStep StepExecution:
    |        StepExecutionContext: lastProcessedId=200
    |
    +-- JobExecution 2: restart
           Context restored from restart metadata
           ImportStep continues from the appropriate checkpoint
```

Restart does not mean every step runs again from the beginning. Completed steps can be skipped per flow/restart rules; failed steps or steps needing re-execution are coordinated based on status and metadata. If a completed step needs to be re-executed, design the corresponding flow and restart behavior rather than editing the context manually to force the framework.

Restored context values must remain compatible with the current code. If key names, data types, or serialized object structures change, old executions may be unreadable. When upgrading the application, keep backward compatibility or have a migration process for saved contexts.

## 10. Context in Failed Chunks and Retries Within the Same Execution

Restarting after a `JobExecution` finishes and retrying while the execution is still running are two different scenarios.

- **Retry within the same execution:** the framework re-processes the operation/chunk per the fault-tolerance policy. Uncommitted transactional updates must be rolled back or recovered according to the step's mechanism.
- **Restart after execution fails:** the framework creates a new execution and restores state from the previous execution's durable metadata.

Do not rely on mutable values in an in-memory `ExecutionContext` object after a rollback. Transaction rollback protects repository data when updates participate in the same transaction, but a modified Java object does not automatically revert to an old snapshot merely because the database rolled back. The framework's retry mechanism and `ItemStream` manage read state according to the step lifecycle; custom readers must follow this contract and avoid maintaining inaccurate checkpoints.

If a processor or listener writes a key into the step context itself and immediately throws an exception afterward, do not assume that key was saved. Inspect the repository after the execution finishes and design logic based on committed checkpoints.

## 11. Context Does Not Replace Business Data

`ExecutionContext` is suitable for checkpoints and coordination state. It should not become the sole place storing business results that users need to query long term.

For example, storing `lastProcessedOrderId` in the step context is reasonable for the reader to continue. However, storing full payment info, order contents, or report results in the context is unsuitable. That data belongs in business tables, output files, or separately managed data stores.

Reasons:

- Context is tied to an execution and may be copied on restart; it is not a stable business data model.
- Large payloads bloat metadata and increase serialization/deserialization costs.
- Data may contain sensitive information and be difficult to apply appropriate retention policies to.
- Schema/class changes may make old contexts unable to deserialize.
- Deleting metadata to clean history can lose checkpoints or contexts needed for restart.

Store a small identifier or checkpoint in the context, then query business data from the official store.

## 12. Key Naming and Data Type Rules

Context keys need clear, stable names that avoid collisions across readers/listeners/steps. Prefixes by component can be used:

```java
private static final String LAST_ID_KEY = "orderReader.lastId";
private static final String FILE_NAME_KEY = "orderReader.fileName";
private static final String VALID_COUNT_KEY = "validation.validCount";
```

Prefer simple data types such as strings, numbers, booleans, stably represented dates/times, or small objects with a compatible serializer. With custom objects, consider the serializer, versioning, and readability after deploying a new version.

Do not store:

- `DataSource`, `Connection`, `EntityManager`, or repositories.
- `InputStream`, `Reader`, cursors, or open file handles.
- Spring beans, services, proxies, or objects referencing the application context.
- Very large collections or all data of a chunk.
- Objects with changing structures without a compatibility strategy.

Store identifiers and state needed for recovery, then recreate resources in `open()` or when the step initializes.

## 13. Common Mistakes When a Step Fails

**Assuming every key in context is already saved:** only updates durably written by the repository are reliable checkpoints. Changes in uncommitted chunks may be rolled back.

**Confusing step context with job context:** the two scopes are different. A later step does not automatically receive every key of an earlier step; use a promotion listener or an explicit sharing mechanism.

**Promoting data of a failed step:** the default listener promotes only when the exit status matches `COMPLETED`. If expanding statuses, determine whether the keys remain valid when the step fails.

**Using context as a business database:** context should be small and serve restart/coordination. Business data must be stored in official repositories.

**Storing non-serializable objects:** connections, streams, or Spring beans are unsuitable for storing in context. Store identifiers and restore resources when opening the step.

**Changing key types or names on deployment:** old executions may fail to read. Maintain compatibility or perform controlled conversion.

**Trusting in-memory objects after rollback:** the context object may still hold recently modified values even though the database transaction rolled back. Re-read from the repository to determine the durable checkpoint.

**Not testing context on restart:** the job may resume from the wrong position if the reader saves checkpoints incorrectly. Test mid-chunk failures and restarts with real data or deterministic fixtures.

## 14. Testing Context When a Step Fails

Have tests simulating a step that commits one or more chunks and then fails on the next chunk. The test should verify:

1. The step has status `FAILED` and the execution is saved in the repository.
2. The step context contains the most recently committed checkpoint.
3. Values written during the failed chunk are not treated as durable checkpoints.
4. The job context contains only keys saved per the proper lifecycle.
5. On restarting the same `JobInstance`, the reader restores from the saved checkpoint.
6. Already completed steps are handled per expected restart behavior.

Example assertions after retrieving the execution from the repository:

```java
JobExecution failedExecution = jobExplorer.getJobExecution(executionId);
assertThat(failedExecution).isNotNull();
assertThat(failedExecution.getStatus()).isEqualTo(BatchStatus.FAILED);

StepExecution failedStep = failedExecution.getStepExecutions().stream()
    .filter(step -> step.getStepName().equals("importStep"))
    .findFirst()
    .orElseThrow();

assertThat(failedStep.getStatus()).isEqualTo(BatchStatus.FAILED);
assertThat(failedStep.getExecutionContext().getLong("lastProcessedId"))
    .isEqualTo(200L);
```

The value `200` is merely the fixture expectation: the first two chunks committed and the third chunk failed. An actual test must configure the reader and writer so that checkpoints are updated properly at commit boundaries.

To test promotion, create one completing step and one failing step, then verify the listener promotes keys to the job context only for configured exit statuses. Use `JobExplorer` to read back the persisted execution instead of asserting only on in-memory objects.

## 15. Context Investigation Process After an Incident

When a step fails, identify `JobExecutionId`, step name, status, failure time, and execution node. Then query `JobExecution` and its `StepExecution`s via `JobExplorer` to inspect the saved context.

Cross-check the following information:

- Does the checkpoint in the step context match the number of committed items?
- Does the job context contain keys promoted from the previous step?
- Did the previous step finish `COMPLETED` or also fail?
- Can the reader restore from the checkpoint with the current source?
- Were the file, cursor, page token, or source data modified after the previous run?
- Does the written business data match the checkpoint?
- Can the current code version deserialize contexts created by the old version?

Do not directly edit `BATCH_STEP_EXECUTION_CONTEXT` or `BATCH_JOB_EXECUTION_CONTEXT` tables to force the job to continue. If a context is corrupted or incompatible, determine the recoverable checkpoint from backups, source data, or reprocessing procedures; all changes must follow controlled operational procedures.

## 16. Designing Contexts So Failed Steps Can Recover

When building a step, clearly identify the minimal state needed to continue after an incident. Readers should implement `ItemStream` if checkpointing is needed; `update()` must write state reflecting progress confirmed at commit boundaries. Use step context for step-private state and job context for data shared between steps.

If a later step needs values from a previous step, use `ExecutionContextPromotionListener` with the list of keys and accepted exit statuses. Do not promote incomplete data unless there is a clear business rule. Keep contexts small, keys stable, and data types compatible across deployments.

Finally, test mid-chunk failures, rollbacks, and restarts. Read the context back from the repository to confirm the durable checkpoint, then confirm the reader resumes at the exact position and the writer does not create duplicate data. When distinguishing committed context from uncommitted changes, applications can use `ExecutionContext` properly and recover failed steps in a controlled way.
