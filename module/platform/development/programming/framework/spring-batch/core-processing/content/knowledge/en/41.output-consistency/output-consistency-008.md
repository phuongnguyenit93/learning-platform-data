# Temporary output and commit markers in Spring Batch

A batch job can write results to files, database tables, or downstream systems. While the job is running, the output usually holds only partial data. If consumers read output too early, they may process incomplete files, observe partially populated tables, or publish reports with missing figures.

Temporary output and commit markers work together to prevent premature publication of incomplete data. The job writes results to a dedicated staging location, completes and validates the output, and only then publishes it. A commit marker is a durable signal indicating that a batch's output is complete and safe for consumers to use. The marker does not replace database transactions or Spring Batch checkpoints; it represents publication state at the business level.

This design is valuable when jobs run for a long time, support restarts, write files for external systems, or must guarantee consumers never read partial data. You must define how temporary output is preserved on restart, when markers are written, and how recovery works if the process stops between publishing and updating the marker.

## 1. Why is temporary output needed?

Suppose a job exports a file of 500,000 orders. If the writer writes directly to the path watched by downstream systems, a consumer may spot the file when it has only a few thousand lines.

~~~text
Batch job
   |
   v
orders.csv
   |
   +--> Consumer detects file
   |
   +--> Reads while writer is still writing
   |
   v
Output missing data or CSV truncated mid-stream
~~~

This is premature publication. File existence does not mean the file is complete. Similarly, a target table may already contain part of a batch's rows before the step completes.

Temporary output creates an isolated area for the run:

~~~text
Input
  |
  v
Spring Batch step
  |
  v
Temporary output
  |
  +--> write chunks
  +--> flush and close
  +--> verify count/checksum/schema
  |
  v
Publish output
  |
  v
Commit marker
  |
  v
Consumer permitted to read
~~~

Consumers read only published outputs with a valid marker. Staging files or unpublished staging rows are never treated as complete data.

## 2. What are temporary output and commit markers?

**Temporary output** is output under construction. It can be a temp file in a staging folder, a staging table keyed by batch ID, an object in a bucket under a run-specific key, or a directory dedicated to a batch/partition.

**Commit marker** is a small record or artifact indicating that output is finished and published. A marker can be:

- A row in a database control table.
- A sidecar file such as orders.csv.done.
- A manifest containing batch ID, path, record count, and checksum.
- A COMMITTED status in a batch management table.

Markers must be created after the final output is ready. Consumers rely on the marker to decide which outputs can be read.

Do not confuse a commit marker with a checkpoint in `ExecutionContext`. Checkpoints tell Spring Batch where a reader/writer should resume on restart. Commit markers tell consumers that a business output is complete and ready for use.

## 3. Distinguishing chunk commit, step completion, and output publication

These three states have different scopes:

| Concept | Meaning | Example |
| --- | --- | --- |
| Chunk commit | A chunk finished the step's transaction | 100 orders written successfully |
| Step completion | The step finished processing all input per its flow | Export step has status COMPLETED |
| Output publication | The artifact is published for consumer use | File is renamed and marker is written |

A chunk commit does not mean the entire file is complete. Step COMPLETED also does not automatically prove the file has reached the path consumers watch. Publication is an action that may need its own step.

JobExecution status is execution-control metadata. A commit marker is the output contract between producer and consumer. You can use both, yet consumers should never guess that output is ready simply because a file exists or a step is running.

## 4. Naming and identifying temporary output

Temporary output must be bound to a stable logical batch identity. Typically you can use batchId or the identifying JobParameters of the JobInstance.

Example:

~~~text
staging/
  orders/
    batch-2026-11-15-001/
      orders.csv.tmp
      manifest.tmp
~~~

When restarting a JobInstance, Spring Batch creates a new JobExecution while continuing the same JobInstance. Therefore, if the goal is resuming partial output, staging paths should derive from the stable logical batch ID rather than per-attempt JobExecution IDs.

If you use JobExecution ID to name files, a restart can write to a new file while the old checkpoint references the earlier file. If each attempt must have its own artifact, an explicit resume/copy or intentional rebuild step is required; never switch paths implicitly across restarts.

A new business batch needs a new batch ID so it does not overwrite already published output. If re-running from scratch under the same batch ID, an explicit reset/replace procedure and consumer coordination are required.

## 5. Output control table structure

For database output or file output tracked via a database, you can create a control table:

~~~sql
create table batch_output_control (
    batch_id varchar(100) primary key,
    output_type varchar(30) not null,
    state varchar(20) not null,
    temporary_location varchar(500),
    final_location varchar(500),
    expected_count bigint,
    actual_count bigint,
    checksum varchar(128),
    created_at timestamp not null,
    committed_at timestamp,
    error_message varchar(1000)
);
~~~

Common states:

| State | Meaning |
| --- | --- |
| PENDING | Batch output registered, writing not started yet |
| WRITING | Job is creating temporary output |
| READY | Output closed and passed verification, awaiting publication |
| COMMITTED | Output published and safe for consumer use |
| FAILED | Processing run ended in failure; output not published |
| ABANDONED | Batch canceled by operational decision |

You do not have to use these exact state names. What matters is transitioning states along an explicit, conditional state machine that can recover from crashes.

## 6. Output state transitions

A typical flow:

~~~text
PENDING
   |
   v
WRITING
   |
   v
READY
   |
   v
COMMITTED
~~~

If an error occurs before publication:

~~~text
WRITING / READY
       |
       v
     FAILED
       |
       +--> restart same batch
       |
       +--> or ABANDONED after operational decision
~~~

Do not transition to COMMITTED just because a temp file was created or a few chunks were written. COMMITTED must mean final output is ready per the consumer contract.

Transitions should be conditional on current state—for example, allowing WRITING -> READY only. Optimistic versioning or conditional UPDATEs prevent two executions from mutating the marker concurrently.

## 7. Writing files to a staging directory

For file outputs, configure FlatFileItemWriter to point to a temporary path:

~~~java
@Bean
@StepScope
FlatFileItemWriter<OrderExportRow> temporaryOrderWriter(
        @Value("#{jobParameters['temporaryPath']}") String path) {

    return new FlatFileItemWriterBuilder<OrderExportRow>()
        .name("temporaryOrderWriter")
        .resource(new FileSystemResource(path))
        .headerCallback(writer ->
            writer.write("orderId,customerId,total"))
        .lineAggregator(row ->
            row.orderId() + "," +
            row.customerId() + "," +
            row.total()
        )
        .saveState(true)
        .build();
}
~~~

The example takes path from JobParameters for illustration. In production, derive paths from a validated batch ID and a configured staging directory; never accept arbitrary paths from untrusted payloads.

Reader/writer names and resource paths must stay stable across restarts of the same JobInstance. FlatFileItemWriter supports saving state to restore write positions; restarts must use the exact resource and execution context of the earlier step.

Do not delete temporary files when a step fails if you plan to restart from checkpoint. If the writer reopens a file that was deleted or overwritten, the checkpoint may no longer match file contents.

## 8. Temporary files must be hidden from consumers

Consumers must not scan every file in staging. Only the published directory or COMMITTED manifests are valid output sources.

~~~text
output/
  staging/
    batch-001/
      orders.csv.tmp
  published/
    batch-000/
      orders.csv
      orders.csv.done
~~~

Consumers watch only published and require the .done marker. If consumers scan staging too, temporary output loses its purpose because incomplete files can still be read.

For object storage, use a separate staging prefix and write the manifest/commit object only after all objects are uploaded and verified. Do not assume object storage renames share filesystem atomic rename semantics.

## 9. Closing the writer before publishing

Before moving a file, verify the writer completed its lifecycle:

- Step finished writing.
- Writer flushed and closed.
- No threads are still writing to the file.
- The file can be reopened for inspection.
- Record count and checksum were computed after the file stabilized.

Do not rename a file while the writer still holds an open handle. On some OSes that fails; on others, the writer may keep writing into the moved file, causing unpredictable behavior.

A finalization step running after the export step is the right place to verify and publish. It makes flow ordering explicit and can be retried/restarted as a separate unit.

## 10. Publishing files with atomic rename

If temporary file and final file sit on the same filesystem, use an atomic move:

~~~java
public void publish(Path temporary, Path target) throws IOException {
    try {
        Files.move(
            temporary,
            target,
            StandardCopyOption.ATOMIC_MOVE
        );
    } catch (AtomicMoveNotSupportedException ex) {
        throw new IllegalStateException(
            "Filesystem does not support atomic publication",
            ex
        );
    }
}
~~~

Atomic rename lets consumers see the final filename only after the file has been moved. Consumers do not observe byte-by-byte copying as they would when writing directly to the final path.

Atomic move is usually guaranteed only within the same filesystem and depends on the filesystem/provider. If staging and published reside on different mounts, the move may not be atomic or supported.

Never silently drop ATOMIC_MOVE and assume a regular move is atomic too. If unsupported, use a copy-to-new-name strategy, verify contents, and create the marker after copying completes; consumers must rely on the marker rather than mere file presence.

## 11. Why is the marker written after publishing the file?

Publication order must avoid two failure windows:

**Write marker first, then move file:** a consumer can see a COMMITTED marker while the final file does not yet exist or is incomplete.

**Move file first, then write marker:** if the process stops between the two steps, the final file may exist without a marker. Consumers still ignore the file because the marker is not COMMITTED yet. Recovery can verify the file and complete the marker.

Thus, with a database marker:

~~~text
1. Close temporary file
2. Verify temporary file
3. Atomic move to final path
4. Commit marker in database
5. Consumer reads only when marker is COMMITTED
~~~

If step 4 fails, the file is published yet not announced per contract. This is a recoverable state: verify batch ID, file path, and checksum, then update the marker idempotently.

## 12. Sidecar file markers

For consumers observing only the filesystem, use a sidecar marker:

~~~text
orders-2026-11-15.csv
orders-2026-11-15.csv.done
~~~

After the output file finishes and is published, the producer writes a temporary marker and renames it:

~~~java
public void createDoneMarker(Path marker, String content)
        throws IOException {

    Path temporaryMarker = marker.resolveSibling(
        marker.getFileName() + ".tmp"
    );

    Files.writeString(
        temporaryMarker,
        content,
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW
    );

    Files.move(
        temporaryMarker,
        marker,
        StandardCopyOption.ATOMIC_MOVE
    );
}
~~~

The marker can carry batch ID, record count, checksum, schema version, and publish timestamp. If only a simple signal is needed, an empty .done file may suffice, though a data-bearing manifest helps consumers verify output.

Consumers must require the marker and verify it corresponds to the exact file. Do not share one marker across multiple batches without a way to tell which artifacts completed.

## 13. Manifest instead of an empty marker

A manifest can accurately describe output:

~~~json
{
  "batchId": "batch-2026-11-15-001",
  "state": "COMMITTED",
  "file": "orders.csv",
  "recordCount": 125000,
  "sha256": "9b1f...example",
  "schemaVersion": 2,
  "committedAt": "2026-11-15T16:00:00Z"
}
~~~

Consumers can verify batch ID, file existence, checksum, schema version, and record count. Manifests also help investigate when a file was published yet a consumer fails to process it.

## 14. Database staging tables

For database outputs, instead of writing directly to tables consumers read, write to a staging table:

~~~sql
create table order_export_stage (
    batch_id varchar(100) not null,
    source_order_id varchar(100) not null,
    customer_id varchar(100) not null,
    total_amount decimal(18, 2) not null,
    constraint uk_order_export_stage
        unique (batch_id, source_order_id)
);
~~~

Each row carries a batch ID. Consumers or views read only data belonging to batches with a COMMITTED marker:

~~~sql
select s.source_order_id, s.customer_id, s.total_amount
from order_export_stage s
join batch_output_control c
  on c.batch_id = s.batch_id
where c.state = 'COMMITTED';
~~~

Chunks can commit incrementally to the staging table. If the job fails, partial staging rows remain yet are invisible to consumers because the marker is not COMMITTED.

When the step finishes, the finalization step verifies row counts and transitions the marker to COMMITTED. If the staging table itself is the output consumers read, copying to another table may not be necessary; the marker acts as the visibility gate.

## 15. Promoting staging rows to a target table

If a target table without staging state is required, the finalization step can transfer the data:

~~~sql
insert into imported_order (
    source_order_id,
    customer_id,
    total_amount
)
select
    source_order_id,
    customer_id,
    total_amount
from order_export_stage
where batch_id = :batchId;
~~~

Then update the marker:

~~~sql
update batch_output_control
set state = 'COMMITTED',
    committed_at = current_timestamp,
    actual_count = :actualCount
where batch_id = :batchId
  and state = 'READY';
~~~

Both operations must execute within the same database transaction if consumers should see target rows only when the marker is COMMITTED. When the transaction commits, both target data and marker become visible together per database isolation semantics.

If inserting into target succeeds yet updating the marker fails in the same transaction, both changes roll back. If two datasources or two independent transactions are used, no such atomic guarantee exists without appropriate distributed transactions.

## 16. Committing markers in the same database transaction

This is an advantage of database outputs. When final output and marker live in the same database under the same transaction manager, both can be published together:

~~~java
@Service
public class OrderOutputFinalizer {

    private final JdbcTemplate jdbc;

    public OrderOutputFinalizer(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void commitBatch(String batchId, long count) {
        jdbc.update("""
            insert into imported_order
                (source_order_id, customer_id, total_amount)
            select source_order_id, customer_id, total_amount
            from order_export_stage
            where batch_id = ?
            """, batchId);

        int changed = jdbc.update("""
            update batch_output_control
            set state = 'COMMITTED',
                actual_count = ?,
                committed_at = current_timestamp
            where batch_id = ?
              and state = 'READY'
            """, count, batchId);

        if (changed != 1) {
            throw new IllegalStateException(
                "Batch output marker was not transitioned"
            );
        }
    }
}
~~~

This is an illustrative example. You must handle unique constraints, upserts, already-committed batch IDs, and finalization re-invocation. If the target table has unique keys, a re-invocation after an earlier commit may need to check marker state before inserting.

The WHERE state = READY guard prevents transitioning the marker from an unexpected state. Check the updated row count to detect a modified batch or concurrent finalization.

## 17. Markers should not be updated after every item

A batch-level commit marker must signify that the entire output is complete. Updating state to COMMITTED after every chunk lets consumers read a batch when only part of the data is written.

You can track progress separately:

~~~text
state = WRITING
last_committed_chunk = 42
rows_written = 4200
~~~

This is progress/checkpoint metadata, not the final commit marker.

Only after all chunks commit, the writer closes, verification passes, and publication succeeds should state transition to COMMITTED.

If consumers must process incrementally per chunk, design a different contract: each chunk gets its own sequence ID and marker, and consumers acknowledge each chunk. Never use batch-level COMMITTED to represent intermediate progress.

## 18. Creating markers in a dedicated finalization step

A clean Spring Batch design splits the job into steps:

~~~text
InitializeOutputStep
       |
       v
WriteTemporaryOutputStep
       |
       v
ValidateTemporaryOutputStep
       |
       v
PublishOutputStep
       |
       v
CommitMarkerStep
       |
       v
Job COMPLETED
~~~

A dedicated finalization step can use a tasklet to check batch status, verify temporary artifacts, confirm the writer closed, move files or promote staging rows, write the marker, and store counts/checksums.

Do not place complex publication logic inside callbacks lacking clear transaction boundaries. JobExecutionListener or StepExecutionListener work well for notifications/metrics, whereas dedicated steps make orchestration and restarts easier to observe.

## 19. Never mark COMMITTED inside afterWrite

afterWrite runs after a single successful chunk write. It does not mean the entire step finished. After that callback, another chunk can still fail.

Likewise, beforeStep cannot confirm final output and onWriteError reports only the current write failure. Commit markers must rely on completion of the entire output.

A finalization step following a writer step should run only when flow allows continuing from a successful status. If the writer step is FAILED, finalization must not run as normal publication.

## 20. Restarting with temporary files

When a job fails mid-file, there are two strategies:

**Resume:** keep the temporary file and checkpoint. When restarting the same JobInstance, the writer reopens the exact file, restores state, and continues from the committed position.

**Rebuild:** delete old staging output under a controlled procedure, then re-run from the beginning with a fresh checkpoint/JobInstance.

Do not mix the two strategies. Deleting the file while keeping the old checkpoint makes the writer try to resume at a non-existent offset. Keeping the file while the reader starts from the beginning can duplicate output.

With resume, keep the same temporary path across restarts, keep writer name and state configuration stable, enable saveState on writers needing checkpoints, and never delete temp files on FAILED executions while restart remains possible.

With rebuild, assign a new logical attempt/batch identity or perform an explicit reset, ensure no consumer reads old artifacts, delete staging data/files by exact batch ID, and start with a fresh checkpoint.

## 21. Restarting with temporary database output

Staging rows committed in previous chunks normally stay intact when a job fails. When restarting the same JobInstance, the reader resumes after the checkpoint and the writer writes remaining chunks.

To avoid duplicate staging rows if a chunk replays, put a unique constraint on batch_id and source_record_id, use upsert/insert-if-absent per contract, and ensure chunk transactions and the staging writer share the same transaction manager where possible.

Do not delete all staging rows in beforeStep on every restart. If a step is designed to rebuild from scratch, clean up staging rows explicitly and use an appropriate new execution/JobInstance. Never wipe staging automatically just because a step starts; the step may be a valid restart.

## 22. Failure window between publish and marker

With file output and a database marker, the two operations do not inherently share one transaction:

~~~text
File rename succeeds
       |
       v
Process stops abruptly
       |
       v
Marker remains READY
~~~

Consumers do not read the file because the marker is not COMMITTED. When recovery runs, it checks whether the batch is READY, whether the final file exists, whether the file matches batch ID/checksum, whether record counts match, and whether a COMMITTED marker already exists.

If the file is valid and the marker is uncommitted, recovery can write the marker. If the file is missing or checksum mismatches, transition to an error state and republish from staging if possible.

This is why final paths should be immutable per batch ID and marker updates must be idempotent. Recovery can run multiple times without creating extra artifacts or mislabeling batches.

## 23. Failure window before publish

If the process stops while the writer is still producing temporary output, the marker is not COMMITTED and consumers still do not read output. On restart, Spring Batch restores writer state and continues if the artifact remains valid.

If the file is corrupted or unresumable, move the batch to a rebuild workflow. Never rename an unverified file to the final path just to mark the job complete.

## 24. Failure window after marker

If the COMMITTED marker was written successfully, consumers may start processing. If the job process stops right afterward before JobExecution metadata updates to COMPLETED, a restart may re-run finalization.

Finalization must be idempotent:

- If the marker is already COMMITTED and the artifact matches, treat publication as complete.
- Never overwrite committed final output with different data.
- Never create a new marker conflicting with the old marker.
- Never promote staging rows a second time if the operation is not idempotent.

JobExecution status and marker state can temporarily diverge. The marker is the output contract; JobRepository is the execution contract. Recovery must reconcile both instead of automatically downgrading a COMMITTED marker merely because the prior execution lacked COMPLETED status.

## 25. What information should a marker contain?

A useful marker typically contains batch ID or JobInstance identity, output type and schema version, final location/object key, record count, file size, checksum/hash, commit timestamp, and source batch/date or tenant if needed.

You do not need to put all data into the marker. Markers should be small, quick to verify, and sufficient for consumers to confirm the artifact belongs to the right batch.

Checksums catch truncated, altered, or mis-copied files. Record counts catch missing-row outputs. The two checks complement each other; a checksum alone does not prove business correctness.

## 26. Consumers must verify markers

Consumers must honor the publication contract:

~~~text
1. Discover candidate batch
2. Read marker/manifest
3. Require state COMMITTED
4. Verify batch ID and schema version
5. Verify artifact exists and checksum/count match
6. Process artifact
7. Record consumer acknowledgement
~~~

If a consumer checks only file existence, it may read a renamed final file before the marker is written. If a consumer reads only the marker without checking batch ID/path, it may pick up the wrong batch's file.

Consumers also need idempotency. They may encounter the same marker again after restarts or repeated polling. Store consumed batch IDs via unique constraints or an inbox table so output is never processed twice.

## 27. Commit markers and consumer acknowledgements are different states

COMMITTED means the producer published the output. It does not mean the consumer processed it successfully.

~~~text
Producer:
  WRITING -> COMMITTED

Consumer:
  PENDING -> PROCESSING -> CONSUMED
                       |
                       +--> FAILED
~~~

Do not mutate the producer marker from COMMITTED to CONSUMED when a consumer finishes reading. Producer and consumer have separate responsibilities; acknowledgements should live in a table or system managed by the consumer.

If multiple consumers exist, each needs its own acknowledgement state. One COMMITTED marker can be read by multiple valid consumers.

## 28. Atomic rename is not a distributed transaction

An atomic rename guarantees a single filename change on a filesystem, not atomic coordination with a database marker, message broker, or remote consumer.

Example:

~~~text
Filesystem: file rename succeeds
Database:   marker update fails
~~~

Two resources on different systems do not automatically roll back together. Using markers to gate visibility and recovery to finish state is a way to handle failure windows, not a distributed atomic commit.

If true atomic commit across multiple resources is mandatory, you need a suitable transaction coordinator and must accept its complexity. For most batch exports, publishing the file first, writing the marker, and relying on recovery is simpler.

## 29. Temporary output on object storage

Object storage such as S3 or blob storage typically lacks filesystem-style atomic rename. Rename may be implemented as copy-then-delete, so consumers might see objects mid-copy depending on how publication works.

A safe pattern:

~~~text
staging/batch-001/orders.csv
       |
       v
Upload completes
       |
       v
Verify size/checksum
       |
       v
Write manifest COMMITTED
       |
       v
Consumer reads only objects referenced by manifest
~~~

The manifest is created after upload and verification complete. For multipart uploads, publish only after completing the multipart upload successfully.

If copying to a final prefix is needed, copy the object to a new key, verify the target object, and write the marker last. Consumers must never assume an object under a final prefix is complete without a manifest.

## 30. Immutable output names and avoiding overwrites

Final paths should include batch ID or version so each committed output is immutable:

~~~text
published/orders/batch-001/orders.csv
published/orders/batch-002/orders.csv
~~~

Do not reuse one shared path orders.csv across all batches if consumers may still be reading the old file while the producer writes a new one. Overwriting creates races between consumers and producers, and old markers can end up pointing to new contents.

If a latest alias is needed, update the alias after the new batch output is COMMITTED. An alias is merely a pointer to an immutable artifact, never where the writer writes directly.

## 31. Partitioned output

If a step runs partitioned, each partition can create its own temporary file:

~~~text
staging/batch-001/
  partition-000.csv.tmp
  partition-001.csv.tmp
  partition-002.csv.tmp
~~~

Once all partitions succeed, verify every partition output, check total record counts, merge files or build a manifest listing all parts, publish all outputs, and write a single batch-level commit marker.

Do not write the COMMITTED marker as soon as the first partition completes. A batch is published only when all required partitions are ready.

If consumers are allowed to process individual partitions independently, use per-partition markers plus a batch-level manifest representing the complete set of partitions. The contract must state explicitly whether consumers may process partial batches.

## 32. Cleaning up temporary output

Temporary output can accumulate when jobs fail or are canceled. Cleanup should be governed by state and retention, not file age alone.

A sample policy:

- Keep WRITING/FAILED outputs during the allowed restart window.
- Never delete artifacts of COMMITTED batches while still within consumer retention.
- Clean up ABANDONED batches only after an operational decision.
- Remove orphaned .tmp files once confirmed no restartable JobExecution exists.
- Log batch ID, path, and cleanup reason.

Do not delete temp files merely because the current JobExecution is FAILED; operators may intend to restart. Likewise, do not delete staging rows of a READY batch whose finalization has not run yet.

Cleanup jobs need locking/claiming or state checks so they never remove outputs actively used by another execution.

## 33. Markers and concurrency

Two executions with the same batch ID must never publish output concurrently. Protect via unique primary keys on batch ID, conditional state transitions, optimistic locking/version columns, database locks/leases for longer ownership, and unique final paths per batch ID.

Example:

~~~sql
update batch_output_control
set state = 'READY'
where batch_id = :batchId
  and state = 'WRITING';
~~~

Check the updated row count. If it is 0, the execution does not own the transition or the batch is already in another state. Never ignore this result.

A short-transaction row lock can protect state transitions, yet never hold a database transaction open while copying large files. Separate state/lease claiming and short finalization transactions work better.

## 34. Versioning outputs and markers

Consumers need to know which output schema is published. When changing CSV columns or JSON formats, include schemaVersion in the marker/manifest:

~~~json
{
  "batchId": "batch-001",
  "state": "COMMITTED",
  "schemaVersion": 3,
  "file": "orders.csv"
}
~~~

Consumers check supported versions before parsing. If incompatible, the consumer errors out and leaves the batch unconsumed for later handling.

Never change output format under the same schema version. Restarting an old batch with new code must preserve the original output version or follow a migration/rebuild plan.

## 35. Example job flow for file output

A job can divide responsibilities as follows:

~~~java
@Bean
Job exportOrdersJob(
        JobRepository jobRepository,
        Step initializeOutputStep,
        Step writeTemporaryFileStep,
        Step validateOutputStep,
        Step publishOutputStep) {

    return new JobBuilder("exportOrdersJob", jobRepository)
        .start(initializeOutputStep)
        .next(writeTemporaryFileStep)
        .next(validateOutputStep)
        .next(publishOutputStep)
        .build();
}
~~~

In this flow, initializeOutputStep creates/claims the batch control record and resolves the staging path; writeTemporaryFileStep uses FlatFileItemWriter to write in chunks and save state; validateOutputStep verifies the closed file, count, and checksum; publishOutputStep moves the file to the final path and writes the commit marker.

The example illustrates orchestration only. Steps must use proper JobParameters/ExecutionContext to share batch ID and paths; finalization must be idempotent on restart.

## 36. Example tasklet for publish and marker

A tasklet can delegate to a finalizer service:

~~~java
@Bean
Step publishOutputStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet publishOutputTasklet) {

    return new StepBuilder("publishOutputStep", jobRepository)
        .tasklet(publishOutputTasklet, transactionManager)
        .build();
}
~~~

The finalizer service should keep filesystem and database parts recoverable:

~~~java
public void finalizeOutput(OutputMetadata metadata) throws IOException {
    verifyTemporaryArtifact(metadata);
    publishFileIfNeeded(metadata);
    markerService.markCommitted(metadata);
}
~~~

Do not wrap large file copies in a long database transaction. Marker updates can run in a short transaction after the file is published. If marker updating fails, restarting and re-invoking the finalizer verifies the final file and retries updating the marker.

## 37. Checking files before committing markers

Checks can include:

- File exists and is non-empty when empty output is forbidden.
- File size falls within reasonable bounds.
- Header/schema matches expected version.
- Data row count equals expected count.
- Checksum is computed and saved.
- File can be opened and parsed through the end.
- No partition files are missing.

Do not check only that file size is greater than zero. A file can have a header while missing all records. If empty output is valid, a count of zero can be legitimate and must be explicitly represented in the manifest.

Expected count must come from a reliable source. Computing expected count solely from the newly written file checks internal consistency, yet cannot detect skipped inputs by the reader.

## 38. Reconciling input and output

For business completeness checks, you can store read count, filter count, process skip count, write count, and rejected count.

Counts must be interpreted according to Spring Batch semantics. For instance, an item processor returning null increments filter count and never reaches the writer; skip count tracks items skipped due to exceptions. Do not arbitrarily sum counters across mismatched units or phases.

You can check a reconciliation equation matching the job design, such as:

~~~text
Read items = Written items + Filtered items + Skipped items
~~~

This is a conceptual example; account for retries, error handling, and 1:n or n:1 item splitting/merging if your pipeline has those behaviors. Write the marker only once batch reconciliation rules pass.

## 39. Securing temporary output

Temporary output can contain data just as sensitive as final output. Apply the same protection:

- Restrict permissions on staging directories.
- Never place temp files inside a web root or public bucket.
- Use encryption at rest if required.
- Never put secrets/tokens in filenames or manifests.
- Apply retention and secure deletion policies.
- Never log full file contents on verification failure.

Renaming from staging to published does not change access controls if both paths share a filesystem. For object storage, verify ACLs/policies on both prefixes and the manifest.

## 40. Common mistakes when using temporary output and commit markers

**Writing directly to the final path:** consumers may read incomplete output. Write to staging first.

**Creating markers after every chunk:** consumers may treat a partial batch as complete. Create batch-level markers only after full output.

**Writing markers before publishing files:** markers may point to missing or incomplete artifacts. Publish first, then commit markers.

**Using JobExecution ID in temp paths when restart is needed:** restarts can use a different path than old checkpoints. Use stable batch identities.

**Deleting temp files on FAILED jobs:** destroys data needed for restart. Clean up only when the batch is no longer restartable.

**Changing writer name or path across restarts:** ExecutionContext no longer matches the resource. Keep configurations stable or rebuild intentionally.

**Assuming atomic rename coordinates with database transactions:** two resources do not commit together automatically. Use markers and recovery.

**Using normal moves when atomic move is unsupported:** creates a window where consumers read partially copied files. Use marker gating or another publication protocol.

**Setting COMMITTED before files are verified:** consumers can receive corrupt or missing-record files. Verify counts/checksums first.

**Failing to make finalization idempotent:** restarts may copy/publish repeatedly or insert staging rows twice. Check marker/path/state before acting.

**Relying on Job status instead of markers:** JobExecution and output publication have separate failure windows. Consumers need a marker contract.

**Not checking markers on the consumer:** temporary output can still be read prematurely. Consumers must process only COMMITTED batches.

**Not tracking consumer acknowledgements:** consumers may reread markers and reprocess output. Persist consumed batch IDs.

**Cleaning up based solely on file age:** can delete artifacts of executions awaiting restart. Check batch state and ownership.

**Not controlling concurrency by batch ID:** two executions can publish to the same final path. Use unique keys and conditional state transitions.

## 41. Process for implementing temporary output and commit markers

First, define where output is written and how consumers recognize completed output. Choose a stable batch ID, create a dedicated staging path/table, and define a state machine such as PENDING, WRITING, READY, COMMITTED, FAILED. Consumers must read only artifacts with a COMMITTED marker.

Next, write chunked output to staging. For files, keep paths and writer identities stable so restarts can resume; for databases, tag each staging row with batch ID and use unique keys against replay. When the writer step finishes, close output, and check schema, record counts, and checksums. Use a finalization step to publish: atomic rename on the same filesystem if supported, or copy/verify/manifest on object storage.

Finally, write the marker after the artifact is published. For database outputs, promote rows and update the marker in the same transaction when sharing the database/transaction manager. For file outputs, handle the failure window between rename and marker via idempotent recovery. Consumers verify markers, versions, and checksums and persist separate acknowledgements. Preserve temporary output while restart remains allowed; clean up only after retention and state checks.

Temporary output and commit markers separate data creation from data publication. Spring Batch can commit chunks incrementally while output remains in WRITING; consumers should see artifacts only after all output is verified and the marker transitions to COMMITTED. With databases, final data and markers can share a transaction; with files/object storage, you need a publication protocol and recovery for the failure window between artifact and marker. When batch identities are stable, finalization is idempotent, and consumers honor markers, jobs can restart safely without exposing incomplete data to downstream systems.
