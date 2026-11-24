# Post-processing cleanup Tasklet in Spring Batch

After a Job processes data, the application often has temporary resources left to reclaim: intermediate files, working directories, staging data, unpublished export files, or lock states serving only that batch. If these resources are left around indefinitely, storage space and database size grow, and operating subsequent runs becomes harder to control.

In Spring Batch, a clear way to organize this is to create a **Tasklet Step dedicated to cleanup** and place it after the processing, validation, or output publishing Steps. The Tasklet performs cleanup within the Job-managed lifecycle, has its own execution status, and can be restarted if cleanup fails.

Cleanup must be designed carefully. Deleting files or staging data too early can lose data needed for restart or investigation. A deletion operation on the filesystem also does not automatically roll back when a database transaction fails. This lesson presents how to place cleanup in the right position, implement the Tasklet, manage transactions and restarts, and ensure cleanup is safe and observable.

## 1. Which phase is cleanup in a Job?

A data processing Job usually has several phases:

1. Prepare inputs and the working directory.
2. Read, process, and write data.
3. Validate counts or the validity of the results.
4. Publish outputs to their official location.
5. Clean up temporary resources that are no longer needed.

Cleanup usually sits at the end of the success path, after the results have been durably written and the necessary validation steps have completed.

~~~mermaid
flowchart TD
    A["Prepare input"] --> B["Process data"]
    B --> C["Validate / reconcile"]
    C --> D["Publish output"]
    D --> E["Cleanup Tasklet"]
    E --> F["Job completed"]
    B -. "Failure" .-> G["Job failed; keep resources needed for restart"]
    C -. "Failure" .-> G
    D -. "Failure" .-> G
~~~

For example, a data import Job may create a normalized file in a temporary directory. After the data has been written to the database and successfully reconciled, the cleanup Tasklet deletes the intermediate file. If the import Step fails, cleanup should not automatically delete files needed for restart or investigation.

### Resources that usually need cleanup

| Resource | Example | When it can be cleaned up |
|---|---|---|
| Temporary files | Normalized CSV file, intermediate file | After the official result has been confirmed |
| Working directory | Directory dedicated to a batch | After all Steps needing the directory have completed |
| Staging tables | Staging rows by batch ID | After data has been moved and reconciled |
| Unpublished export files | Temporary file before renaming or uploading | After publishing succeeds or per the recovery process |
| Business locks or leases | State holding the right to process a batch | When the work has ended and the lock is no longer needed |
| External temporary resources | Upload session, temporary object | After the target system confirms the result |

Not every resource is closed by the cleanup Tasklet. Readers, writers, and components supporting ItemStream have their own open, update, and close lifecycle. Let the framework close the resources it manages; the cleanup Tasklet only handles business resources or temporary resources assigned to the final phase.

## 2. Why use a separate Tasklet Step?

A Tasklet suits an operation with a clear scope, such as deleting files, deleting staging data by batch code, releasing state, or marking a batch as finished.

A Tasklet has the contract:

~~~java
public interface Tasklet {
    RepeatStatus execute(
        StepContribution contribution,
        ChunkContext chunkContext
    ) throws Exception;
}
~~~

Each execute call is invoked by the framework within the lifecycle of the Tasklet Step. The Tasklet returns:

- `RepeatStatus.FINISHED` when the work is complete.
- `RepeatStatus.CONTINUABLE` when it needs to be called again to continue the work.

A Tasklet Step has a transaction per Tasklet invocation, based on the transaction manager configured for the Step. With JDBC cleanup, database operations can participate in that transaction. With filesystem operations or external APIs, the database transaction does not automatically undo effects that have already occurred.

### Benefits of a separate cleanup Step

- **Separate status:** know whether cleanup started, completed, or failed.
- **Restartable:** if cleanup fails, the Job can re-run that Step according to metadata.
- **Separate logs and metrics:** easy to distinguish data processing errors from cleanup errors.
- **Clear transaction:** database operations can commit or roll back per Tasklet call.
- **Clear position in the Job flow:** cleanup only runs when control flow reaches that Step.

For important cleanup, this is easier to track than hiding all deletion operations inside a callback without a separate Step.

## 3. Placing cleanup after the necessary Steps

A simple Job can connect the processing Step to the cleanup Step using `next(...)`:

~~~java
@Bean
Job importCustomersJob(
        JobRepository jobRepository,
        Step processCustomersStep,
        Step validateOutputStep,
        Step cleanupStep) {

    return new JobBuilder("importCustomersJob", jobRepository)
        .start(processCustomersStep)
        .next(validateOutputStep)
        .next(cleanupStep)
        .build();
}
~~~

In this flow, cleanup only runs after the processing Step and the validation Step finish along the normal path. If a preceding Step fails and the Job has no transition bringing the flow to cleanup, cleanup will not run.

This is usually the appropriate behavior for resources that must be kept for restart. However, if business rules require cleanup even when the Job fails, design a separate error-handling branch and determine precisely which resources are allowed to be deleted in that branch.

### Clean up only after results are durable

Before deleting input or intermediate resources, confirm that:

- The writer has written the target data successfully.
- The necessary chunks have committed.
- The reconciliation Steps have completed.
- Output files or data have been published in the official location.
- Audit records or information needed for operations have been saved.
- No subsequent Step still needs the temporary resources.

For example, if a Job generates a report file and uploads it to object storage, do not delete the local file immediately after starting the upload. Clean up only after the target system confirms the upload succeeded and the file has been verified as required.

### Conditional flows

For a Job with multiple branches, configure transitions so cleanup only runs on branches that have completed with the right conditions. Do not wire cleanup mechanically if a branch fails or needs to retain data for investigation.

You can use a custom ExitStatus to distinguish outcomes, but you must clearly determine which branch gets cleaned up and which branch must retain resources.

## 4. Writing a Tasklet to delete temporary files

Example of a Tasklet deleting intermediate files after successful processing:

~~~java
@Bean
Tasklet cleanupTemporaryFileTasklet(
        TemporaryFileService temporaryFileService) {

    return (contribution, chunkContext) -> {
        temporaryFileService.deleteProcessedTemporaryFiles();
        return RepeatStatus.FINISHED;
    };
}
~~~

The file deletion logic is placed in a service to separate filesystem access responsibility from Step configuration.

A simple service implementation:

~~~java
@Service
public class TemporaryFileService {

    public void deleteIfExists(Path file) throws IOException {
        Files.deleteIfExists(file);
    }
}
~~~

`Files.deleteIfExists(...)` is idempotent at the operation level: if the file no longer exists, the call still completes without failing merely because the file is absent. This is useful when the Tasklet is re-run after an incomplete cleanup.

In a real application, do not hard-code file paths or delete with broad wildcards. Restrict cleanup to the working directory and the specific batch code.

### Getting paths from JobParameters or JobExecutionContext

Input paths or the working directory are often provided when the Job launches. You can use `@StepScope` to retrieve runtime values:

~~~java
@Bean
@StepScope
Tasklet cleanupWorkDirectoryTasklet(
        @Value("#{jobExecutionContext['workDirectory']}")
        String workDirectory,
        @Value("#{jobParameters['batchId']}")
        String batchId) {

    return (contribution, chunkContext) -> {
        Path root = Path.of(workDirectory)
            .toAbsolutePath()
            .normalize();

        Path marker = root.resolve("work-" + batchId + ".tmp")
            .normalize();

        if (!marker.startsWith(root)) {
            throw new IllegalArgumentException(
                "Cleanup path is outside the working directory."
            );
        }

        Files.deleteIfExists(marker);

        return RepeatStatus.FINISHED;
    };
}
~~~

In the example:

- `workDirectory` is stored in JobExecutionContext by the preparation Step.
- `batchId` is the parameter identifying the batch.
- The path is normalized before deletion.
- Checking `startsWith(root)` prevents the normalized path from escaping outside the allowed directory.
- A non-existent file is treated as already cleaned up.

Validate the batch ID and directory access permissions at the input layer. Do not allow callers to pass an arbitrary path that could let the Tasklet delete files outside the Job's working area.

## 5. Cleaning up an entire working directory

A Job can create multiple intermediate files in a dedicated directory for each batch. When you need to delete the entire directory, use a dedicated function with path validation.

Illustrative example:

~~~java
public void deleteWorkDirectory(Path workRoot, String batchId)
        throws IOException {

    Path root = workRoot.toAbsolutePath().normalize();
    Path target = root.resolve(batchId).normalize();

    if (!target.startsWith(root) || target.equals(root)) {
        throw new IllegalArgumentException(
            "Invalid cleanup directory."
        );
    }

    if (!Files.exists(target)) {
        return;
    }

    try (Stream<Path> paths = Files.walk(target)) {
        paths.sorted(Comparator.reverseOrder())
            .forEach(path -> {
                try {
                    Files.deleteIfExists(path);
                } catch (IOException ex) {
                    throw new UncheckedIOException(ex);
                }
            });
    } catch (UncheckedIOException ex) {
        throw ex.getCause();
    }
}
~~~

The code walks the directory tree and deletes from the deepest entries up to the parent directory. Restrict the target directory by batch ID, check permissions, and avoid following unintended symbolic links. In systems with high security requirements, you can use a dedicated file management service with a directory allowlist instead of letting the Tasklet build paths itself.

Do not delete the application's shared root directory. Only delete the subdirectory created specifically for that processing run or batch.

## 6. Cleaning up staging data in the database

Some Jobs write input data into a staging table before moving it to business tables. After the data is processed and reconciled, a Tasklet can delete the staging rows of that exact batch.

Example:

~~~java
@Bean
@StepScope
Tasklet cleanupStagingTasklet(
        JdbcTemplate jdbcTemplate,
        @Value("#{jobParameters['batchId']}") String batchId) {

    return (contribution, chunkContext) -> {
        int deleted = jdbcTemplate.update(
            "DELETE FROM customer_import_stage WHERE batch_id = ?",
            batchId
        );

        contribution.incrementWriteCount(deleted);

        return RepeatStatus.FINISHED;
    };
}
~~~

The `WHERE batch_id = ?` condition is very important. Do not delete the entire staging table if that table may contain data from other active Jobs or batches.

If JdbcTemplate uses the same DataSource and transaction manager as the Step, the DELETE statement participates in the Tasklet's transaction. If the Tasklet fails before the transaction commits, the deletion can roll back along with the transaction.

### Deleting staging data in batches

A single DELETE statement removing millions of rows can create a large transaction, hold locks for a long time, and bloat the transaction log. For large data, delete in small batches.

Example of a service deleting at most a set number of rows per call:

~~~java
@Service
public class StagingCleanupService {

    private final JdbcTemplate jdbcTemplate;

    public StagingCleanupService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public int deleteNextBatch(String batchId, int limit) {
        return jdbcTemplate.update(
            """
            DELETE FROM customer_import_stage
            WHERE stage_id IN (
                SELECT stage_id
                FROM customer_import_stage
                WHERE batch_id = ?
                ORDER BY stage_id
                FETCH FIRST ? ROWS ONLY
            )
            """,
            batchId,
            limit
        );
    }
}
~~~

The syntax to limit row count in a DELETE depends on the database. The example above only illustrates the idea; replace it with the syntax matching your database engine and check the execution plan.

The Tasklet can continue running batch by batch:

~~~java
@Bean
@StepScope
Tasklet cleanupStagingInBatches(
        StagingCleanupService cleanupService,
        @Value("#{jobParameters['batchId']}") String batchId) {

    return (contribution, chunkContext) -> {
        int deleted = cleanupService.deleteNextBatch(batchId, 1000);

        contribution.incrementWriteCount(deleted);

        return deleted > 0
            ? RepeatStatus.CONTINUABLE
            : RepeatStatus.FINISHED;
    };
}
~~~

With the Tasklet returning `CONTINUABLE`, the framework calls the Tasklet again to process the next batch. Each call has a transaction according to the Tasklet Step configuration. When no rows remain to delete, the Tasklet returns `FINISHED`.

If the database supports a different bounded DELETE syntax, use the appropriate syntax. Do not use unstable ordering or limits if iterations could accidentally delete another batch's data.

## 7. Configuring the cleanup Step in Spring Batch 5

After having the Tasklet, create a separate Step using `StepBuilder`:

~~~java
@Bean
Step cleanupStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet cleanupStagingTasklet) {

    return new StepBuilder("cleanupStep", jobRepository)
        .tasklet(cleanupStagingTasklet, transactionManager)
        .build();
}
~~~

Then wire it into the Job:

~~~java
@Bean
Job customerImportJob(
        JobRepository jobRepository,
        Step importStep,
        Step reconcileStep,
        Step cleanupStep) {

    return new JobBuilder("customerImportJob", jobRepository)
        .start(importStep)
        .next(reconcileStep)
        .next(cleanupStep)
        .build();
}
~~~

This configuration creates a Step with a stable name `cleanupStep`. Spring Batch stores a separate StepExecution for it. If cleanup fails, the failure state can be inspected in JobRepository and the Job can be restarted according to the Job's policy.

The Step name should remain stable across deployments so metadata and restart history are recognized consistently.

## 8. Transaction of the cleanup Tasklet

A Tasklet Step runs within the transaction manager passed to the `tasklet(...)` method. However, rollback capability depends on the resources the cleanup operation uses.

| Cleanup operation | Can it roll back with the database transaction? | Notes |
|---|---|---|
| DELETE staging via JdbcTemplate with same DataSource | Yes | If participating in the Step's transaction manager |
| UPDATE batch status in the same database | Yes | Same transaction conditions |
| Deleting files with Files.delete | No | Filesystem does not participate in JDBC transactions |
| Renaming files | Not automatically | May require compensating actions or retry |
| Deleting objects on object storage | Not automatically | Needs an idempotent API and status tracking |
| Calling an API to release resources | Not automatically | External system manages side effects |

### File deletion cannot be rolled back by a database transaction

Suppose a Tasklet performs:

1. Delete temporary file.
2. Delete staging rows.
3. Update batch status.
4. Database transaction fails at commit.

The database can roll back deleting staging rows and updating status, but the deleted file does not reappear automatically.

Therefore, do not treat all operations in one Tasklet as atomic just because the Step has a transaction. With multiple types of resources, design the operation order and re-runnability.

### Splitting cleanup into Steps by resource when needed

If cleanup includes multiple independent operations, you can split them into separate Steps:

- Confirm the output is published.
- Delete staging data in the database.
- Delete intermediate files.
- Release external resources.
- Record cleanup completion status.

This split creates clearer state when part of cleanup fails. However, each Step must be safe to re-run and the flow must properly handle the case where the preceding Step has already completed.

## 9. Designing idempotent cleanup

Cleanup is often called again when a Job restarts. A good Tasklet needs to tolerate the case where resources were already deleted in the previous run.

**Idempotent** means running the same cleanup operation again does not leave the final state incorrect or create unintended side effects.

Example:

~~~java
Files.deleteIfExists(temporaryFile);
~~~

If the file has already been deleted, the next call still completes.

For staging data:

~~~sql
DELETE FROM customer_import_stage
WHERE batch_id = :batchId;
~~~

If no rows remain for that batch, the statement deletes 0 rows and still succeeds. This is the appropriate behavior for cleanup by batch code.

For external APIs, use a stable request code or idempotency key if the API supports it. Do not generate a new request ID for each restart if you want the target system to recognize it as the same cleanup operation.

### Rules that help make cleanup re-runnable

- Delete by specific batch ID or resource ID.
- Treat a non-existent resource as already cleaned up if business rules allow it.
- Do not use an unbounded DELETE statement without conditions.
- Do not delete data that another Step might still be using.
- Save completion status after the operation actually succeeds.
- If there are multiple operations, define the order and ability to continue after part has completed.
- Use an API that supports idempotency or check status before resending.

## 10. Restart when cleanup fails

Suppose a Job has three Steps:

~~~mermaid
flowchart TD
    A["processStep: COMPLETED"] --> B["publishStep: COMPLETED"]
    B --> C["cleanupStep: FAILED"]
    C -. "Restart JobInstance" .-> D["cleanupStep runs again"]
~~~

When restarting the same JobInstance, Spring Batch can skip Steps that already completed according to the default restart policy and continue at the incomplete Step if that Step allows restart.

In the example:

- Data has been processed and published successfully.
- Cleanup failed while deleting a file.
- A new JobExecution is created on restart.
- Completed Steps usually do not run again.
- cleanupStep is executed again.
- If some files were already deleted before the error, an idempotent Tasklet will skip files that no longer exist and continue cleaning the rest.

This is why cleanup should be separated into its own Step and the cleanup operation must be re-runnable.

### If cleanup has already completed

A Step that is already COMPLETED normally does not run again when restarting the same JobInstance. This is appropriate if cleanup is finished and does not need to repeat.

You can configure `allowStartIfComplete(true)` to allow a completed Step to run again when the JobInstance is restarted:

~~~java
return new StepBuilder("cleanupStep", jobRepository)
    .tasklet(cleanupTasklet, transactionManager)
    .allowStartIfComplete(true)
    .build();
~~~

Only enable this option when explicitly required. Cleanup must be idempotent and must not delete new resources created by a different run. If there is no need to re-run a completed Step, keep the default behavior.

### Do not delete data needed for restart

If cleanup deletes source files before the Job completes, an earlier Step may need that file on restart but will no longer be able to read it.

For example, a Job has an import Step followed by a reconciliation Step that re-reads the original file. Do not delete the file until both Steps complete. If the Job fails before reconciliation, the file must be kept for restart.

## 11. Cleanup when the Job fails

Post-processing cleanup usually only runs on the success path. When a Step fails, retaining temporary resources can be useful for:

- Restarting the Job.
- Investigating faulty data.
- Reconciling input and output.
- Recovering a transformed file.
- Identifying the cause of a writer or target system error.

Do not delete all resources in a callback that always runs when the Job ends without distinguishing success and failure states.

### Is cleanup needed on failure too?

Some resources may need to be released even when a Job fails, such as locks or timed leases. Other resources must be kept, such as input files or reject files.

Categorize them:

| Resource | When Job succeeds | When Job fails |
|---|---|---|
| Temporary lock | Release | Usually needs to be released via a safe mechanism |
| Source file | Archive or delete after retention | Keep for restart or investigation |
| Reject file | Store per policy | Keep for error handling |
| Regenerable intermediate file | Delete after output is published | Keep if restart needs it; otherwise clean up via TTL later |
| Staging rows | Delete after reconciliation | Keep if needed for restart or audit |
| Published output | Keep per business policy | Do not delete just because a later Step failed |

You can create a separate error-handling branch to release locks or record status. Do not share one Tasklet that deletes all resources across both success and failure branches.

### Cleaning up abandoned resources with a maintenance Job

If a Job fails and temporary resources must be kept for a period, you can create a separate maintenance Job to clean up expired directories or staging rows.

The maintenance Job needs to verify:

- The corresponding batch has ended and is no longer running.
- It is no longer eligible for restart per policy.
- The retention period has expired.
- The resource is not being used by another Job.
- There is an audit of what was cleaned up.

A TTL mechanism handles resources left behind due to incidents; it does not replace the cleanup Step on the success path.

## 12. Distinguishing a cleanup Tasklet from a listener

Spring Batch has listeners such as StepExecutionListener and JobExecutionListener. They provide callbacks to run logic before or after a Step or Job.

However, important business cleanup should usually be a separate Tasklet Step.

| Criterion | Cleanup Tasklet Step | Listener |
|---|---|---|
| Has a separate StepExecution | Yes | Does not create a new Step |
| Separate success/failure status | Yes | Tied to the current Step or Job lifecycle |
| Has Step transaction | Yes, per Tasklet configuration | Depends on the callback and active transaction |
| Can be restarted as a Step | Yes | No separate Step to restart |
| Suitable for | Deleting staging, cleaning files, publishing, or releasing critical resources | Logging, metrics, event audits, notifications |

### Using listeners for observation

StepExecutionListener is suitable for recording start and end times, logging counts, or emitting metrics. JobExecutionListener can be suitable for notifications after the Job ends.

Do not rely on an afterJob listener as the sole mechanism for critical cleanup that needs retry and restart. A listener does not create a separate StepExecution so the Job can resume cleanup as an independent phase.

### Do not confuse close() with business cleanup

Readers and writers supporting ItemStream have a close() method to close resources. This is the technical lifecycle of the component, such as closing a file handle or cursor.

Business cleanup has a different goal: deleting intermediate files, deleting staging rows, archiving results, or releasing batch state. Do not place critical data deletion operations in close() because close is a resource-closing step, not a cleanup Step with its own status.

## 13. Cleaning up files and publishing output safely

A data export workflow typically has these files:

- Temporary file currently being written.
- Completed file not yet published.
- Official output file.
- Source file to be archived.

A common order:

1. Writer writes the temporary file.
2. Step checks the file: size, header, line count, or checksum.
3. Step publishes the file to the official location.
4. Record the publish status and reference code.
5. Clean up intermediate files no longer needed.
6. Archive or delete the source file according to the retention policy.

Do not delete the temporary file before publishing completes. If publishing fails, the temporary file may be the input needed to retry without re-running the entire processing.

### Renaming files and atomic move

If the temporary file and the target file are on the same filesystem, you can try using ATOMIC_MOVE:

~~~java
Files.move(
    temporaryPath,
    finalPath,
    StandardCopyOption.ATOMIC_MOVE
);
~~~

Not every filesystem supports atomic move; the operation can fail when the two paths are on different filesystems or the provider does not support it. Exception handling and a recovery procedure are needed.

If the target file already exists, define a policy: overwrite, reject, or use a name based on batch ID. Do not automatically overwrite the official file of another batch.

### Archiving before deleting

If you need to retain source files for audit, move them into an archive directory instead of deleting them immediately. Archive file names should include the batch code or identifying metadata, while avoiding overwriting old archive files.

Archive and cleanup can be two different Steps if separate tracking or different retry requirements are needed.

## 14. Cleaning up staging data and business data

Staging tables usually contain intermediate data, but not every table named staging is allowed to be deleted immediately after processing.

Before cleaning up, determine:

- Is the table used for restart?
- Do rejected rows need to be kept for investigation?
- Does any audit table reference the staging ID?
- Does staging data need reconciliation after the Job completes?
- Is another Job reading or processing the same batch ID?
- Is there a requirement to retain source data for a period of time?

If the data has been moved to business tables, you can delete staging by batch ID. If history needs to be preserved, you can change the status to ARCHIVED or save an audit copy before deleting.

Do not delete JobRepository metadata inside the cleanup Tasklet of a running Job. Metadata for the current JobExecution and StepExecution is needed for status, restart, and audit. Spring Batch metadata retention is a separate maintenance process with its own conditions and deletion order.

## 15. Cleaning up external resources

A Tasklet can call an API to release an upload session, delete a temporary object, or close a resource on another system.

Example:

~~~java
@Bean
@StepScope
Tasklet cleanupRemoteUploadTasklet(
        RemoteStorageClient storageClient,
        @Value("#{jobParameters['uploadSessionId']}")
        String uploadSessionId) {

    return (contribution, chunkContext) -> {
        storageClient.deleteTemporaryUpload(uploadSessionId);
        return RepeatStatus.FINISHED;
    };
}
~~~

An API call does not participate in the Step's database transaction unless a separate supported coordination mechanism exists. If the API has deleted the resource but the response is lost, a retry may call the delete operation again.

A cleanup API should have one of these behaviors:

- Deleting a resource that no longer exists still returns a success result.
- Supports an idempotency key.
- Allows querying status to confirm the result.
- Returns clear error codes for non-retryable cases.
- Has a timeout and bounded retries.

If the API does not support idempotency, the service can check status before deleting, though it still must handle race conditions between the check and the delete call.

## 16. Using ExecutionContext to pass cleanup information

A preparation Step can store the working directory or batch code in the JobExecutionContext for the cleanup Tasklet to use.

Example in a preparation Tasklet:

~~~java
@Bean
Tasklet prepareWorkDirectoryTasklet() {
    return (contribution, chunkContext) -> {
        String batchId = contribution.getStepExecution()
            .getJobParameters()
            .getString("batchId");

        Path workDirectory = Path.of("work", batchId);
        Files.createDirectories(workDirectory);

        contribution.getStepExecution()
            .getJobExecution()
            .getExecutionContext()
            .putString(
                "workDirectory",
                workDirectory.toAbsolutePath().toString()
            );

        return RepeatStatus.FINISHED;
    };
}
~~~

The cleanup Step can read that value back via late binding or through StepExecution.

ExecutionContext is suitable for passing small pieces of information such as:

- Batch ID.
- Working directory path.
- Temporary file name.
- Upload session ID.
- State needed to continue the workflow.

Do not store entire file contents or lists of millions of records in ExecutionContext. Large data should be stored in the filesystem, database, or object storage.

Values in ExecutionContext must be stored at the right scope. JobExecutionContext is suitable for information shared across multiple Steps in the same JobExecution; StepExecutionContext is suitable for state belonging to a single Step.

## 17. Tracking cleanup results

Cleanup is an operational phase, so it needs to be observed separately.

You can record:

- Number of deleted files.
- Number of deleted directories.
- Number of deleted staging rows.
- Number of released external resources.
- Cleanup duration.
- Batch ID and cleanup scope.
- Step name, JobExecution ID, and final status.
- Number of retries or errors.

Example updating StepContribution when deleting data:

~~~java
int deletedRows = jdbcTemplate.update(
    "DELETE FROM customer_import_stage WHERE batch_id = ?",
    batchId
);

contribution.incrementWriteCount(deletedRows);
~~~

Counters in StepExecution help display the processed volume. However, if cleanup involves multiple resource types, have separate metrics to know the exact number of files, objects, or staging rows cleaned up.

Do not write full sensitive paths, tokens, or personal data to logs. You can use the batch ID and sanitized resource names for tracing.

### Cleanup completed partially with some resources remaining

A Tasklet may need to delete multiple resources. If it successfully deletes several files and then fails on the next file, the Step will fail. On restart, the Tasklet runs again and must skip the files that are already gone, then continue cleaning up the rest.

If you need to know precisely which resources have been handled, you can record the status of each resource in a cleanup audit table. The audit table should have a unique key by batch and resource so retries do not create duplicate records.

## 18. Controlling concurrency and avoiding accidental deletion

Cleanup can run concurrently with other Jobs. If two Jobs share a directory or staging table, one Tasklet might delete resources that the other Job still needs.

Measures:

- Create a separate directory for each batch ID.
- Use a batch ID or partition key in every DELETE statement.
- Do not share generic file names across multiple runs.
- Check that the corresponding Job or lease is still active or released before cleaning up.
- Use locks or ownership mechanisms if multiple workers can manipulate the same resource.
- Do not allow multiple cleanup Jobs to overlap on the same scope without synchronization.
- Restrict delete permissions to allowed directories or schemas.

In particular, do not build a path from external parameters and delete directly without normalizing and validating. A batch ID containing path traversal components could make the target path escape the working directory.

## 19. Testing the cleanup Tasklet

A cleanup Tasklet should be tested both independently and within a Job flow.

| Case | Expected result |
|---|---|
| Temporary file exists | File is deleted |
| File was deleted previously | Cleanup still completes if missing file is acceptable |
| Invalid path | Tasklet throws an error and Step fails |
| Path outside allowed directory | Rejected |
| Batch ID has no staging rows | Cleanup completes with 0 rows deleted |
| Batch has multiple staging rows | Only rows belonging to that batch are deleted |
| Database error when deleting staging | Transaction rolls back per configuration |
| Error deleting files midway | Step fails; re-run continues safely |
| Data processing Step fails | Success cleanup only does not run on the success flow |
| Cleanup fails then restarts | Completed operations do not cause errors or duplicate side effects |
| Two Jobs run concurrently | Cleanup of one batch does not delete resources of the other batch |

### Testing file cleanup

You can use a temporary directory in JUnit:

~~~java
@Test
void deletesTemporaryFile() throws Exception {
    Path directory = Files.createTempDirectory("batch-cleanup");
    Path file = Files.createFile(directory.resolve("intermediate.tmp"));

    temporaryFileService.deleteIfExists(file);

    assertFalse(Files.exists(file));
}
~~~

Also add tests for non-existent files and invalid paths.

### Testing database cleanup

Use a test database to verify:

1. Create staging rows for two different batches.
2. Run cleanup for the first batch.
3. Confirm only rows of the first batch are deleted.
4. Confirm rows of the second batch still exist.
5. Induce an error inside the transaction to verify rollback.
6. Re-run cleanup and verify an idempotent result.

### Testing Job restart

Create a scenario where cleanup deletes part of the resources and then encounters an error. Then restart the same JobInstance and verify:

- Completed processing Steps do not re-run unexpectedly.
- Cleanup Step runs again.
- Already-deleted resources do not make cleanup fail.
- Remaining resources are cleaned up.
- Job finishes with the appropriate status.

## 20. Common mistakes

### Cleaning up too early

Deleting source files or staging data right after the writer runs can lose data needed for reconciliation or restart. Clean up only after all dependent Steps have completed.

### Deleting the entire staging table

A DELETE statement without a batch ID condition can wipe data from another Job. Always restrict the cleanup scope.

### Assuming the filesystem rolls back with the database

A database transaction cannot restore deleted files. Design file operations to be idempotent and re-runnable.

### Placing critical cleanup in afterJob

A listener does not create a separate StepExecution to restart and track cleanup as a phase. Use a Tasklet Step for cleanup that needs operational reliability.

### Cleaning up on Job failure without classification

Source files, staging rows, or reject data may be needed for restart and investigation. Release only resources that truly must be released on the error branch; keep the necessary data.

### Using overly broad paths or wildcards

Cleanup might accidentally delete files from another batch or a shared directory. Normalize paths, restrict the root directory, and validate the batch ID.

### Failing to design for idempotency

A Tasklet may have deleted part of the resources before failing. If a re-run cannot tolerate a partial state, cleanup will repeatedly fail.

### Using one huge transaction for very large data volumes

Deleting millions of staging rows at once can cause heavy locks and large transaction logs. Delete in small batches or use a chunk-oriented Step when appropriate.

### Deleting metadata of the currently running Job

Do not use a business cleanup Tasklet to delete JobRepository metadata of the current Job. That metadata is needed for status, restart, and audit; metadata retention must be a separate maintenance process.

## 21. Process for designing a cleanup Tasklet

When building a cleanup Tasklet, you can follow this sequence:

1. **List resources:** identify files, directories, staging rows, or external resources to clean up.
2. **Define conditions:** decide which Steps and which statuses must complete before cleanup runs.
3. **Protect restart data:** keep source files, reject data, and staging needed for retry or investigation.
4. **Restrict scope:** use batch ID, resource ID, and allowed root directories.
5. **Choose transactions:** determine which resources participate in the database transaction and which cannot roll back.
6. **Split Steps:** split cleanup by resource type if independent status and retries are needed.
7. **Design idempotency:** ensure re-running after partial cleanup remains safe.
8. **Store necessary state:** use JobExecutionContext or an audit table for small metadata and cleanup progress.
9. **Monitor:** record cleaned counts, duration, errors, and batch ID.
10. **Test:** verify cleanup success, failure, rollback, restart, and concurrent execution.

## 22. Key points to remember

- Cleanup is usually a separate Tasklet Step at the end of the success processing path.
- Clean up resources only after output data has been written, validated, and published as required.
- A Tasklet Step has its own status and transaction, helping track and restart cleanup.
- Database cleanup can roll back when using the same transaction manager; deleting files or calling external APIs does not automatically roll back.
- Clean up staging by batch ID and delete large data in batches.
- Cleanup must be idempotent because it may run again after part of the operation has completed.
- When a Job fails, keep resources needed for restart and investigation; use a maintenance Job or TTL to clean up abandoned items later.
- Use listeners for logging and metrics; use a Tasklet Step for important business cleanup.
- Normalize paths and restrict delete permissions to avoid deleting the wrong resources.
- Do not delete JobRepository metadata of the running Job inside the cleanup Tasklet.

A well-placed and safely re-runnable cleanup Tasklet helps the Job reclaim resources after processing, retain necessary data on errors, and make the lifecycle of each batch clearer.

