# Output cleanup after a job fails

In Spring Batch, a job can process millions of records chunk by chunk. When a chunk fails, the current chunk's transaction is usually rolled back, but previously committed chunks still retain their data. For file outputs, database records in a separate transaction, or calls to external systems, partial results may also remain after the job transitions to FAILED.

Therefore, cleaning up output after a job fails should be tied to the job's retry/restart policy. If the job will be restarted, partial output must usually be kept to match the saved checkpoint. If the run is discarded and will start over from the beginning, the old run's temporary output should be cleaned up in a controlled manner. Mechanically deleting files as soon as a job fails can break the next restart.

## 1. Understand job state before cleaning up output

Spring Batch distinguishes a logical run from individual execution attempts:

- **JobInstance** represents one logical run of a job. It is identified by the job name and the JobParameters marked as identifying.
- **JobExecution** represents a specific execution attempt of a JobInstance. When a JobInstance fails and is restarted, Spring Batch creates a new JobExecution that still belongs to the same JobInstance.
- **ExecutionContext** stores the state needed to resume processing, such as read positions or the state of an ItemStream writer.

For example, a report-export job for 2026-11-15 runs with businessDate as an identifying parameter. The first execution processes three chunks and then fails. When restarted with the same identifying parameters, Spring Batch continues that JobInstance using a new JobExecution. Checkpoints saved from the previous run indicate how far data was processed.

This leads to two very different scenarios:

| Scenario | How to handle output |
|---|---|
| Restarting the same JobInstance | Keep temporary output and the corresponding checkpoint; the writer must support restart. |
| Discarding the old run and starting over from scratch | Clean up the old run's temporary output, then create a new JobInstance with a new temporary output. |

Do not delete a file that a writer uses for restart while keeping the old run's ExecutionContext. The checkpoint could point to a position in a file that was deleted or altered, causing subsequent results to miss data, write at the wrong offset, or fail to open the writer.

## 2. Use temporary output and publish only when the job completes

For file outputs, a safe design is to write to a staging directory. Only after processing and verification steps finish does the job move the staging file to become the official file.

~~~mermaid
flowchart TD
    A[Job starts] --> B[Write to staging file by JobInstance]
    B --> C{Job completed successfully?}
    C -->|Yes| D[Verify output]
    D --> E[Publish staging file]
    C -->|No| F{Planned for restart?}
    F -->|Yes| G[Keep staging file and checkpoint]
    F -->|No| H[Delete staging file for JobInstance]
~~~

For example, the staging file can be named after the JobInstance:

~~~text
output/staging/job-10482.part
output/final/report-2026-11-15.csv
~~~

Using the JobInstance ID keeps the path stable across restarts of the same JobInstance. Do not use the JobExecution ID as the staging file identifier if restarts are meant to resume the old file: each restart gets a new JobExecution ID, while the checkpoint still belongs to the same JobInstance.

A separate publish step can be placed after the processing step:

~~~java
@Bean
Job reportJob(
        JobRepository jobRepository,
        Step processStep,
        Step publishOutputStep) {

    return new JobBuilder("reportJob", jobRepository)
            .start(processStep)
            .next(publishOutputStep)
            .build();
}
~~~

With this flow, publishOutputStep runs only after processStep completes successfully. If the processing step fails, the staging file is not yet published as official output. If the publish step fails, the JobInstance is also not marked complete; on restart, Spring Batch can skip the completed step and resume the failed publish step.

In the publish tasklet, you can use a file rename on the same filesystem:

~~~java
Path stagingFile = stagingDirectory.resolve(stagingFileName);
Path finalFile = finalDirectory.resolve(finalFileName);

if (!Files.exists(stagingFile)) {
    throw new IllegalStateException("Staging output does not exist: " + stagingFile);
}

Files.move(stagingFile, finalFile, StandardCopyOption.ATOMIC_MOVE);
~~~

An atomic move prevents output readers from seeing a newly copied official file that is only partially written. Depending on the filesystem, ATOMIC_MOVE might not be supported; in that case, choose a publication approach suitable for the deployment environment. Staging and final should reside on the same filesystem if you intend to use atomic move. Also define clearly how to handle an existing target file: reject overwrite, create a new versioned name, or replace via a controlled procedure.

## 3. On restart: keep output and restore writer state properly

If you intend to restart the same JobInstance, do not delete the staging file when the job fails. Ensure the writer and resource are configured consistently across executions:

- Use the same staging path for the same JobInstance.
- Use a stable and unique writer name within the step so writer state is stored properly in the ExecutionContext.
- For restartable writers such as FlatFileItemWriter, keep state saving enabled and let the writer restore state from ExecutionContext.
- Do not manually delete, truncate, or replace the staging file before Spring Batch opens the writer for restart.
- If a writer does not support restart, design output for idempotent full rewrite, or use a new staging resource along with a new logical run.

Chunks committed before failure are normally not re-run as uncommitted chunks. Therefore, the writer must coordinate with checkpoints: the output already written corresponds to committed input, and the remainder is appended on restart. If you delete the file without resetting the corresponding state, the two sides become out of sync.

Not every output is automatically recovered by Spring Batch. Checkpoint saving works only when readers/writers properly participate in the ItemStream mechanism and save the necessary state. For custom-built writers, implement open, update, and close appropriately, and test behavior during transaction rollbacks and restarts.

## 4. When discarding an old run: clean up only that run's artifacts

If the business decides not to restart a failed JobInstance, you can clean up the staging file after the job ends in FAILED status. The listener below illustrates a policy that deletes temporary output only when configuration permits discarding failed runs:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;

public class FailedOutputCleanupListener implements JobExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(FailedOutputCleanupListener.class);

    private final Path stagingDirectory;
    private final boolean discardOutputOnFailure;

    public FailedOutputCleanupListener(
            Path stagingDirectory,
            boolean discardOutputOnFailure) {
        this.stagingDirectory = stagingDirectory;
        this.discardOutputOnFailure = discardOutputOnFailure;
    }

    @Override
    public void afterJob(JobExecution jobExecution) {
        if (!discardOutputOnFailure
                || jobExecution.getStatus() != BatchStatus.FAILED) {
            return;
        }

        String fileName = "job-"
                + jobExecution.getJobInstance().getInstanceId()
                + ".part";
        Path stagingFile = stagingDirectory.resolve(fileName);

        try {
            Files.deleteIfExists(stagingFile);
        } catch (IOException exception) {
            log.error(
                    "Could not delete failed job output {}",
                    stagingFile,
                    exception);
        }
    }
}
~~~

Register this listener on the job and enable discardOutputOnFailure only when operational procedures determine that failed runs are discarded. If the job needs restarting, disable this deletion policy. The listener checks BatchStatus.FAILED so it does not delete output after a COMPLETED run. STOPPED status is also not deleted in this example because the job may be resumed under operational procedures.

One point must be handled explicitly: after deleting output while keeping the old JobInstance's metadata and checkpoint, do not restart that JobInstance as if the file were still intact. Create a new JobInstance using a new identifying parameter along with a new staging path. If the business requires re-running with the same identity, use a controlled procedure to reset both output and related JobRepository state; do not arbitrarily delete metadata via raw SQL.

Deletion can fail due to permissions, file locks held by another process, or filesystem errors. Since afterJob runs when the job has finished, file cleanup errors should be logged and monitored to handle leftover artifacts. The deleteIfExists operation is idempotent: calling it again when the file is already gone does not raise an error.

## 5. Cleaning up output in a database

With databases, distinguish each chunk's transaction from the overall job lifecycle. If the writer uses the same transaction manager and transaction as the chunk, data from the failing chunk is rolled back. However, previously committed chunks still persist even though the JobExecution ultimately ends in FAILED status.

A manageable approach is to write data to a staging table tagged with a run identifier:

~~~sql
CREATE TABLE report_output_staging (
    run_id       BIGINT NOT NULL,
    business_key VARCHAR(100) NOT NULL,
    report_value VARCHAR(500),
    PRIMARY KEY (run_id, business_key)
);
~~~

You can use the JobInstance ID as run_id. On restart, chunks continue writing to the same staging region. When the job completes, a publish step moves that run_id's data into the main table within an appropriate transaction. If discarding the run, delete only staging data matching that exact run_id:

~~~sql
DELETE FROM report_output_staging
WHERE run_id = :jobInstanceId;
~~~

Do not truncate the entire staging table if multiple JobInstances can run concurrently. Also do not delete target table data using broad conditions like processing date if another job could process that date. Cleanup scope must be pinpointed using run_id or an equivalent ownership key.

If the job writes directly to the target table, design idempotent writes, such as upserting by business key or storing run_id so rows created by that run can be identified. Deleting committed data from a failed job is a business-level compensating action; it does not happen automatically just because a later chunk rolled back.

## 6. Output sent to external systems

Operations like calling HTTP APIs, sending emails, pushing messages, or writing to object storage generally do not share a transaction with JobRepository. A database rollback cannot retract a request already accepted by another system.

For these side effects:

- Send a business-stable idempotency key so retries do not create duplicate records or transactions.
- Store send requests in an outbox within the same transaction as business data, then let a separate step relay the outbox to the target system.
- Track sent, pending, and failed states so you can retry or compensate.
- Delete messages or staging records only when you know they have not been processed by the target system, or when an approved business compensation workflow exists.

Do not treat deleting local files or resetting ExecutionContext as a way to undo a side effect that already occurred in an external system.

## 7. Choosing a cleanup policy by output type

| Output type | On restart | When discarding the run |
|---|---|---|
| File written by restartable writer | Keep staging file and checkpoint; resume the same resource. | Delete the staging file belonging to that JobInstance, then run a new JobInstance. |
| File recreated entirely from scratch | Use this only if safely rewritable without producing duplicate output. | Delete the old temp file and create a new file for the new run. |
| Database staging table | Keep committed rows, continue by run_id and idempotent keys. | Delete staging rows for the exact run_id. |
| Target table updated directly | Use upserts or processed-record detection to prevent duplicate writes. | Run a compensating operation scoped to that run's data. |
| API, email, or message | Retry with idempotency keys and durably persisted send state. | Execute compensation if the target system supports it; never assume rollback retracts side effects. |

## 8. Common design mistakes

**Deleting files immediately upon seeing FAILED.** This can break restarts because checkpoints still reference the old file state. Delete only after deciding to discard that run.

**Naming files after JobExecution ID.** Every restart gets a new ID, so the writer can create a new file while Spring Batch resumes from the old checkpoint. Use a stable identifier per JobInstance for restartable output.

**Writing directly to the final file during processing.** Consumers may read incomplete output. Write to staging and publish after the job succeeds.

**Assuming a FAILED job rolls back all data.** Chunk transactions protect only the chunk's transaction scope. Earlier committed chunks and external side effects can still exist.

**Deleting shared output across runs.** Concurrent jobs may share a staging directory or table. Every cleanup action must be scoped by JobInstance ID, run_id, or a unique ownership key.

**Ignoring cleanup errors.** Leftover files may be mistaken for fresh output on subsequent runs. Log, alert, and run a stale-artifact cleanup process based on job state and retention period.

## 9. Scenarios to test during implementation

1. Fail a job after committing multiple chunks. Verify earlier committed chunks remain and the failing chunk rolls back with its transaction.
2. Restart with the same identifying JobParameters. Verify JobInstance ID and staging path stay identical, the writer resumes at the right position, and no duplicate lines appear.
3. Discard the failed run and run with a new JobInstance. Verify only artifacts of the old JobInstance are cleaned up and new output is created completely.
4. Make the publish step fail. Verify final output is not partially published and the job is not considered complete.
5. Simulate a permission error during file deletion. Verify cleanup failure is logged/alerted and other jobs' output is not accidentally deleted.
6. Run two JobInstances concurrently. Verify their staging paths, run_ids, and cleanup actions are independent.

A proper output cleanup policy must answer three questions: which JobInstance owns the output, whether the job is permitted to restart, and when the output is considered official. When these three are clearly represented in staging paths, ExecutionContext, and data keys, handling output after a failed job becomes predictable and safe.
