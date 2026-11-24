# Inspecting State After a Run

After a Spring Batch job finishes running, the application often needs to read back the state to see how the job ended, which steps ran, where the last checkpoint was, and what values were stored in `ExecutionContext`. This inspection is useful for testing, operational dashboards, reconciliation, and deciding whether a restart is needed.

Spring Batch persists execution metadata and execution contexts in `JobRepository`. Once you have a `JobExecution`, you can read `JobExecution.getExecutionContext()` to inspect job-scoped state, or retrieve each `StepExecution` and read `StepExecution.getExecutionContext()` to inspect step-private state. When you need to read back durably saved data after the job completes, `JobExplorer` is the appropriate API because it queries metadata from the repository.

It is important to identify the exact run to inspect. A `JobInstance` can have multiple `JobExecution`s due to restarts or separate execution attempts under the same business identity. Use the `JobExecution` ID to query the exact execution, then read contexts in the proper scope.

## 1. What Does State After a Run Consist Of?

After a run, there are several kinds of state that commonly need inspection:

- **Job status:** `BatchStatus`, `ExitStatus`, start/end timestamps, duration, and errors if any.
- **Individual step status:** which steps completed, failed, or were stopped; which steps were executed within that job execution.
- **Job ExecutionContext:** small values saved to share between steps within the same `JobExecution`.
- **Step ExecutionContext:** checkpoints and internal state of each `StepExecution`, such as reader position or tasklet progress.
- **Execution counters:** counts of items read, written, filtered, skipped, and commit and rollback counts.
- **Business data:** actual results written to the database, files, or external systems.

The groups above are related but do not replace one another. `ExecutionContext` stores key-value entries that the application or Spring Batch components need to restore. Counters such as `readCount` and `writeCount` are metadata properties of `StepExecution`. Invoice, order, or payment data still resides in business data stores.

## 2. Distinguishing JobExecution, StepExecution, and JobInstance

Before reading state, you need to know what the execution objects represent:

| Object | Meaning | Used when inspecting |
|---|---|---|
| `JobInstance` | A business processing run identified by job name and identifying `JobParameters` | Grouping execution attempts of the same batch |
| `JobExecution` | A specific execution attempt of a `JobInstance` | Reading status and Job ExecutionContext of a single run |
| `StepExecution` | A specific execution attempt of a step within a `JobExecution` | Reading status, counters, and Step ExecutionContext of the step |

For example, a file-import job might run the first time and fail on the second step. On restart, Spring Batch creates a new `JobExecution` for the same `JobInstance`. Each execution has its own ID and its own status history. Therefore, if you need to inspect the just-completed restart, use that execution's ID rather than looking up solely by job name or `JobInstance`.

## 3. Reading State Directly from JobExecution After a Synchronous Run

When `JobLauncher` runs synchronously, the `run()` call returns only after the job finishes. You can read status from the returned `JobExecution` object:

```java
JobExecution execution = jobLauncher.run(importOrdersJob, jobParameters);

BatchStatus status = execution.getStatus();
ExitStatus exitStatus = execution.getExitStatus();
Long executionId = execution.getId();

log.info("Job execution {} finished with status {} and exit code {}",
        executionId,
        status,
        exitStatus.getExitCode());
```

This object reflects the outcome of the execution just launched. We can also read the Job ExecutionContext and the `StepExecution`s attached to the execution:

```java
ExecutionContext jobContext = execution.getExecutionContext();

if (jobContext.containsKey("summary.reference")) {
    String summaryReference =
            jobContext.getString("summary.reference");
    log.info("Summary reference: {}", summaryReference);
}

for (StepExecution stepExecution : execution.getStepExecutions()) {
    log.info("Step {}: status={}, read={}, write={}, commits={}, rollbacks={}",
            stepExecution.getStepName(),
            stepExecution.getStatus(),
            stepExecution.getReadCount(),
            stepExecution.getWriteCount(),
            stepExecution.getCommitCount(),
            stepExecution.getRollbackCount());
}
```

This is convenient when the job is invoked synchronously in a test or an orchestrating process. If the application needs to inspect state persisted in the repository after the job ends, reload the execution using `JobExplorer`.

## 4. Reading Saved State Back Using JobExplorer

`JobExplorer` provides a read-only API to look up job instances, job executions, and step executions from `JobRepository`. It is suitable for operational dashboards, status APIs, and post-run inspection.

Example service taking `executionId` and reloading the execution:

```java
@Service
public class BatchStateReader {

    private final JobExplorer jobExplorer;

    public BatchStateReader(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public JobExecution loadExecution(Long executionId) {
        JobExecution execution =
                jobExplorer.getJobExecution(executionId);

        if (execution == null) {
            throw new NoSuchElementException(
                    "Job execution not found: " + executionId);
        }

        return execution;
    }
}
```

Then the context can be read:

```java
JobExecution storedExecution =
        batchStateReader.loadExecution(executionId);

ExecutionContext jobContext = storedExecution.getExecutionContext();

if (jobContext.containsKey("summary.reference")) {
    String reference = jobContext.getString("summary.reference");
}

for (StepExecution stepExecution : storedExecution.getStepExecutions()) {
    ExecutionContext stepContext = stepExecution.getExecutionContext();

    if (stepContext.containsKey("orders.lastProcessedId")) {
        long lastId = stepContext.getLong("orders.lastProcessedId");
    }
}
```

`JobExplorer` helps read back persisted metadata, even when the original `JobExecution` object is no longer in request memory or the application has restarted. It is a query API; do not modify a context loaded via `JobExplorer` and expect the repository to automatically save that change.

## 5. Reading Job ExecutionContext and Step ExecutionContext in the Right Scope

The two contexts serve different purposes:

| Context | Access API | Common data |
|---|---|---|
| Job ExecutionContext | `jobExecution.getExecutionContext()` | Report reference, artifact code, small results shared between steps |
| Step ExecutionContext | `stepExecution.getExecutionContext()` | File offset, next page, reader's last key, tasklet state |

For example, `importOrdersStep` can save a checkpoint:

```java
ExecutionContext stepContext =
        contribution.getStepExecution().getExecutionContext();

stepContext.putLong("orders.lastProcessedId", lastCommittedOrderId);
```

After the job runs, read the value from the exact step execution:

```java
for (StepExecution stepExecution : storedExecution.getStepExecutions()) {
    if ("importOrdersStep".equals(stepExecution.getStepName())) {
        ExecutionContext context = stepExecution.getExecutionContext();

        if (context.containsKey("orders.lastProcessedId")) {
            long lastId = context.getLong("orders.lastProcessedId");
            log.info("Last checkpointed order ID: {}", lastId);
        }
    }
}
```

Do not assume keys in Step ExecutionContext automatically appear in Job ExecutionContext. If a subsequent step or post-job code needs to use a step's value, promote that key or store an appropriate reference in Job ExecutionContext.

## 6. Writing a Value Inspectable After the Job Runs

To inspect context, you first need to know where and when a value is written.

Example of a tasklet saving a result reference code in Step ExecutionContext:

```java
@Bean
Step createSummaryStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        SummaryService summaryService) {

    return new StepBuilder("createSummaryStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                String reference = summaryService.createSummary();

                contribution.getStepExecution()
                        .getExecutionContext()
                        .putString("summary.reference", reference);

                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
```

After the step finishes, the value is persisted in Step ExecutionContext and can be read via the corresponding execution's `StepExecution`.

If that value is needed at the job level, `ExecutionContextPromotionListener` can be used to promote the key when the step finishes:

```java
@Bean
ExecutionContextPromotionListener promoteSummaryReference() {
    ExecutionContextPromotionListener listener =
            new ExecutionContextPromotionListener();
    listener.setKeys(new String[] {"summary.reference"});
    return listener;
}
```

Register the listener with the step that creates the value:

```java
return new StepBuilder("createSummaryStep", jobRepository)
        .tasklet(createSummaryTasklet, transactionManager)
        .listener(promoteSummaryReference)
        .build();
```

When the step finishes with a status accepted by the listener, the key is promoted to Job ExecutionContext. After the job runs, it can be read via:

```java
String reference = storedExecution.getExecutionContext()
        .getString("summary.reference");
```

The promotion listener usually promotes only when the step status matches configured exit statuses (default is `COMPLETED`). If the step fails, do not assume the key was moved to the job context. Read the Step ExecutionContext to inspect the saved state of that step itself.

## 7. Reading State After an Asynchronous Job

If `JobLauncher` uses an asynchronous executor, `run()` may return as soon as the job is submitted or starting. In that case, the returned `JobExecution` is not guaranteed to hold the final state.

Do not do the following:

```java
JobExecution execution = jobLauncher.run(job, parameters);
// Do not assume execution is already COMPLETED if launcher runs async.
return execution.getExecutionContext();
```

Instead, take `executionId` from the response and look it up again via `JobExplorer` after the job completes. A status API may return `STARTING` or `STARTED` while the job is running, then return final statuses such as `COMPLETED`, `FAILED`, or `STOPPED`.

A common pattern:

1. The API receives a request and launches the job asynchronously.
2. The API returns `202 Accepted` along with `executionId`.
3. The client queries a status endpoint using that ID.
4. The endpoint uses `JobExplorer` to read the latest status.
5. Once the execution has ended, the endpoint may additionally return context values allowed to be exposed.

If internal polling is needed, use bounded wait intervals and timeouts or an event notification mechanism. Do not loop queries continuously without limit. When reading final state, reload the execution from the repository instead of using an old object that may be stale.

## 8. Inspecting State in Listeners

If you need to log or trigger an action right after a step/job finishes in the same process, listeners can be used.

Example `StepExecutionListener`:

```java
@Component
public class ImportStepListener implements StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(ImportStepListener.class);

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        ExecutionContext context = stepExecution.getExecutionContext();

        if (context.containsKey("orders.lastProcessedId")) {
            log.info("Step {} checkpoint={}",
                    stepExecution.getStepName(),
                    context.getLong("orders.lastProcessedId"));
        }

        return null;
    }
}
```

`afterStep()` is useful for observing step state when the callback is invoked. However, if you need to confirm metadata was durably persisted and read it from another component after the job finishes, query it again with `JobExplorer`.

Similarly, `JobExecutionListener.afterJob()` can observe `JobExecution` and Job ExecutionContext after steps have ended. Listeners are suitable for logging, metrics, or notifications within the same process. Do not use a listener as a substitute for the metadata lookup API from the repository.

## 9. Inspecting State in Tests

In integration tests, `JobLauncherTestUtils` can launch a job and return a `JobExecution`. After the job runs synchronously, you can assert status, step context, and job context.

Example:

```java
@SpringBatchTest
@SpringJUnitConfig(BatchTestConfiguration.class)
class ExecutionContextStateTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private JobExplorer jobExplorer;

    @Test
    void storesCheckpointAfterSuccessfulRun() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("batchId", "STATE-TEST-001")
                .toJobParameters();

        JobExecution launched =
                jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, launched.getStatus());

        JobExecution stored =
                jobExplorer.getJobExecution(launched.getId());
        assertNotNull(stored);

        StepExecution importStep = stored.getStepExecutions()
                .stream()
                .filter(step -> step.getStepName().equals("importOrdersStep"))
                .findFirst()
                .orElseThrow();

        assertEquals(BatchStatus.COMPLETED, importStep.getStatus());
        assertTrue(importStep.getExecutionContext()
                .containsKey("orders.lastProcessedId"));
    }
}
```

`BatchTestConfiguration` must provide a job with a step named `importOrdersStep` and a reader/tasklet that writes the context key during execution. Tests should use a repository and datasource matching the test objective. If testing only reading back saved metadata, ensure `JobExplorer` and `JobRepository` use the same metadata store.

Specific values can be verified:

```java
long lastId = importStep.getExecutionContext()
        .getLong("orders.lastProcessedId");

assertEquals(8450L, lastId);
```

Do not assert only that the key exists if business logic expects a specific value. Verify the value and reconcile it with actual data written by the writer.

## 10. Inspecting State When a Job Fails

A failed job can still hold useful state. For example, a step committed 10 chunks and then failed on the 11th chunk. Step ExecutionContext may contain the 10th chunk's checkpoint; that is the most recent durable state, not necessarily the last item the reader read in memory.

When inspecting a failed execution, check:

- `JobExecution.getStatus()` and `getExitStatus()`.
- `StepExecution.getStatus()` and `getExitStatus()` of the failed step.
- `StepExecution.getExecutionContext()` to see the saved checkpoint.
- `rollbackCount`, `commitCount`, `readCount`, `writeCount`, and skip counters.
- `FailureExceptions` or error information suitable for investigation.
- Business data committed before the failure occurred.

Do not infer that an empty context means the job did nothing. A step might not save custom keys, a reader might use internal keys, or the execution might have failed before the first checkpoint. Conversely, a non-empty context does not prove all corresponding data committed if the application manually updated state at the wrong time.

## 11. Distinguishing Context from Framework Counters and Statuses

When reading state after a run, do not confuse values in `ExecutionContext` with built-in metadata:

| Information needed | Where to read |
|---|---|
| Whether job completed or failed | `JobExecution.getStatus()` |
| Job exit code | `JobExecution.getExitStatus()` |
| Whether step completed | `StepExecution.getStatus()` |
| Number of items read by reader | `StepExecution.getReadCount()` |
| Number of items written by writer | `StepExecution.getWriteCount()` |
| Commit/rollback counts | `StepExecution.getCommitCount()` / `getRollbackCount()` |
| Reader checkpoint or custom state | `StepExecution.getExecutionContext()` |
| Values shared between steps | `JobExecution.getExecutionContext()` |
| Invoice/order/payment state | Business repository or database |

Counters are managed by the framework; there is no need to copy them into the context without a specific business purpose. If you need to display the status of a business object, read the business data model instead of inferring from `writeCount`.

## 12. Checking Whether a Context Has a Key

Do not assume a key always exists after every run. A value might not have been written if the step took another branch, stopped before a checkpoint, or had not reached the code creating the key.

Use `containsKey()` before reading an optional key:

```java
ExecutionContext context = stepExecution.getExecutionContext();

if (context.containsKey("report.reference")) {
    String reference = context.getString("report.reference");
} else {
    log.info("Step did not produce a report reference");
}
```

For a key required by the step's contract, validate and report a clear error if missing. Avoid reading a value with a default such as `0` and blindly treating it as a valid checkpoint; a default value can mask the fact that the step never wrote state.

Built-in readers may store internal keys based on the reader name. Do not depend on internal key names unless the API documentation guarantees stability. If the application needs a state value for display or reconciliation, save a clearly named custom key and manage its lifecycle.

## 13. Reading Multiple Runs of the Same JobInstance

A `JobInstance` can have multiple `JobExecution`s, for example a failed first run and a successful restart. When you need to view history, use `JobExplorer` to fetch the instance and then read the executions of that instance:

```java
JobInstance instance = jobExplorer.getJobInstance(instanceId);
if (instance == null) {
    throw new NoSuchElementException("Job instance not found");
}

List<JobExecution> executions = jobExplorer.getJobExecutions(instance);

for (JobExecution execution : executions) {
    log.info("Execution {} status={} start={} end={}",
            execution.getId(),
            execution.getStatus(),
            execution.getStartTime(),
            execution.getEndTime());
}
```

Each execution has its own Job ExecutionContext and `StepExecution`s for that execution attempt. If you need to see the checkpoint of the failed run, read the exact failed execution; if you need to see the state of the restart, read the newer execution. Do not merge contexts into a single state without explicit business rules.

## 14. Notes on Serialized Execution Contexts

ExecutionContext is saved in the repository using the configured serializer. Values should be small, serializable data types that remain compatible when a job is restarted after the application deploys a new version.

When reading state after a run:

- Read only keys owned by the application or keys with a clear contract.
- Avoid assuming custom objects can always deserialize after class changes.
- Keep key names and data types stable while old executions still need restart capability.
- Do not store passwords, tokens, or secrets in the context.
- Do not put large item lists or file payloads into metadata.
- Do not write the entire context to logs or return the raw context to API clients.

If the context contains a value that cannot be deserialized due to version changes, loading the execution may fail. For long-running jobs that may restart across deployments, manage schema/serializer compatibility and context data types.

## 15. JobExplorer Is a Read API, Not a Place to Mutate State

`JobExplorer` is designed for metadata lookup. When loading a `JobExecution` or `StepExecution`, do not modify the context on the fetched object and expect the change to persist to the repository.

If a step needs to record state, update the context within the step's execution lifecycle, where Spring Batch can save it at checkpoints or when the step completes. If a value needs to be shared, use Job ExecutionContext or a promotion listener. If business data needs updating after the job, use business services/repositories and appropriate transactions.

Do not manually update the `BATCH_JOB_EXECUTION_CONTEXT` or `BATCH_STEP_EXECUTION_CONTEXT` tables via SQL. These tables belong to the metadata schema managed by Spring Batch; manual edits can corrupt restart state or break metadata readability.

## 16. Security When Exposing State

ExecutionContext can contain file paths, batch codes, artifact names, or other technical details. Even though contexts should not contain secrets, exposure still needs control:

- Return only keys permitted to be public instead of serializing the entire `ExecutionContext`.
- Verify caller permissions before allowing access to an execution ID.
- Do not expose internal paths, personal info, or sensitive exception content to end users.
- Do not write tokens, passwords, or sensitive payloads to logs.
- Separate operational status APIs from business data query APIs when access permissions differ.

A status DTO can include just `executionId`, `jobName`, `batchStatus`, start/end timestamps, and selected progress fields. This keeps the API contract stable even if internal context structure changes.

## 17. Common Mistakes When Inspecting State

**Reading Job ExecutionContext when the key is in Step ExecutionContext.** Contexts do not automatically share keys between the two scopes. Read the exact `StepExecution` or promote the value if sharing is needed.

**Using JobInstance ID instead of JobExecution ID.** The two IDs represent two different types of objects. When querying a specific run, use the execution ID.

**Reading a stale object after an asynchronous launch.** The object returned from `run()` might not have the final status yet. Reload via `JobExplorer` after the execution finishes.

**Assuming every key exists.** A step might not write a key if the processing branch did not run or failed before a checkpoint. Check `containsKey()`.

**Treating context as item counters.** Use `StepExecution` fields for `readCount`, `writeCount`, commits, and skips; context holds only needed key-value state.

**Assuming `COMPLETED` proves business correctness.** Check expected context and actual business data.

**Editing context via JobExplorer.** JobExplorer is a read API. Write state within the step lifecycle or through appropriate Spring Batch mechanisms.

**Logging or returning the entire context.** Context may contain technical information or data that should not be public. Select specific keys and control access permissions.

## Conclusion

To inspect state after a run, first obtain the exact `JobExecution` ID, then read `JobExecution.getExecutionContext()` for job scope and `StepExecution.getExecutionContext()` for each step. `JobExplorer` reloads persisted metadata from `JobRepository`, which is especially useful when jobs run asynchronously or when looking up state after the application has restarted.

Distinguish execution context from `BatchStatus`, `ExitStatus`, step counters, and business data. Read the right keys, check existence before accessing, keep contexts small and serializable, and never modify metadata through read-only APIs. By checking both context and actual business data, you can confirm the job saved accurate checkpoints, steps transitioned through expected states, and post-run outcomes can be used or restarted in a controlled manner.
