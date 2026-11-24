# Filesystem Full: Recovering Spring Batch When Storage Space Runs Out

## 1. Scenario and Goal

A Spring Batch Job runs at 02:00 to read data from a database and export a CSV file. While processing the 700,000th item, the writer throws:

~~~text
java.io.IOException: No space left on device
~~~

Part of the file has already been written. Earlier chunks may have committed; the chunk in flight may roll back; the metadata database might still be healthy or might also be out of disk space. Simply expanding the disk and launching a new JobInstance risks duplicate exports, dropped rows, or losing restartability.

In **Spring Batch Core Processing**, handling a **full filesystem** belongs to **Failure recovery**. The goal is to restore storage capacity, preserve validly processed data, resume the exact JobInstance, and detect future disk-full conditions early.

This lesson covers:

- Causes of storage exhaustion and distinguishing them from inode, quota, and permission errors.
- Which storage areas in a batch pipeline can be affected.
- Diagnostic steps on Linux, Windows, and Kubernetes.
- The state of JobRepository, StepExecution, and ExecutionContext after failure.
- Behavior of FlatFileItemReader/FlatFileItemWriter when file writes are interrupted.
- Staging/publishing design, idempotency, and safe restarts.
- Writer configuration examples, IOException injection, and testing strategies.
- Monitoring, capacity planning, and a recovery runbook.

## 2. Distinguishing Storage Errors

Not every file-write failure happens because free GB reached zero.

| Cause | Symptom | How to Check |
| --- | --- | --- |
| Physical blocks exhausted | `No space left on device`, typically ENOSPC | `df -h`, available space on the mountpoint. |
| Inodes exhausted | Cannot create new files despite free GB | `df -i`, count of small files on the filesystem. |
| Disk quota | `Disk quota exceeded`, typically EDQUOT | User/project/container/volume quotas. |
| Temporary directory full | Sorting, unzipping, compression, upload, or temp file creation fails | `java.io.tmpdir` and scratch directories. |
| Container volume full | Pod evicted or writer fails | Ephemeral-storage limits, `emptyDir`, writable layer. |
| PVC/PV full | Persistent data can no longer grow | Capacity, quota, and storage backend. |
| Read-only filesystem | `Read-only file system`/EROFS | Mount status, kernel/device errors. |
| File descriptors exhausted | `Too many open files`/EMFILE | Ulimit and file handle leaks. |
| Insufficient permissions | `Permission denied`/EACCES | Ownership, ACLs, user running the Job. |
| Database WAL/tablespace full | JDBC writer or JobRepository throws SQL errors | Database server volumes and logs. |

**First rule:** trace the exact **path and mountpoint** of the failing write operation. The root filesystem may have plenty of space while the output volume or `/tmp` is full. Conversely, output storage may have room while the database holding `BATCH_*` tables cannot write metadata.

## 3. Where Does the Filesystem Sit in the Batch Pipeline?

~~~text
                   Scheduler
                       |
                       v
                  Spring Batch Job
                       |
         +-------------+------------------+
         |             |                  |
         v             v                  v
      Input file     Temporary files     Output file
       / reader      sort / unzip        / writer
         |             |                  |
         +-------------+------------------+
                       |
                       v
                  JobRepository
                       |
                       v
                 JDBC metadata
             JobInstance / Execution
                ExecutionContext
                       |
                       v
                 Database storage
~~~

Impact depends on which area fills up:

| Affected Area | Potential Damage | What Must Be Verified |
| --- | --- | --- |
| Input directory | Job cannot download/stage more input; incomplete snapshot | Is the input file intact and immutable? |
| Output directory | Writer wrote only a partial file or partial CSV line | Do the current file and checkpoint match? |
| Temp/scratch | Truncated temp files; failed sort/compression | Is there enough space to recreate temp files? |
| Log directory | Lost diagnostic logs; logging blocked | Are OS metrics and JobRepository state available? |
| Metadata database | Cannot persist `FAILED` or latest ExecutionContext | Do persisted status and process state conflict? |
| Business database | Business commit or rollback fails | Which data actually committed? |

Filesystems and database transactions are usually **two separate resources**. There is no guarantee a JDBC rollback removes bytes already written to disk or undoes HTTP calls.

## 4. What Happens When Failure Strikes Mid-Chunk?

Suppose a Step uses `chunk(100)` and the writer is exporting items 1–1,000:

~~~text
Execution #120
  items 1..100    -> write, COMMIT
  items 101..200  -> write, COMMIT
  items 201..300  -> write, COMMIT
  items 301..350  -> filesystem ENOSPC
                            |
                            v
                    in-flight chunk fails
                            |
                            v
              JobExecution may become FAILED
~~~

With readers and writers implementing ItemStream, checkpoints are typically updated at chunk boundaries. Earlier chunks may have committed while the current chunk failed. However, **a file write error can happen mid-write**, leaving partial bytes on disk before the exception is thrown.

Never assume a CSV file holds exactly 300 complete lines. Distinguish:

- Committed item counts in Step metadata.
- The file position saved by the writer in `ExecutionContext`.
- Actual bytes and lines on disk after failure.
- The writer's transaction buffering and rollback/restart mechanics.
- Whether any external process modified or moved the file after the Job failed.

Specifically, never manually edit internal writer keys in ExecutionContext just because the file looks longer than the checkpoint. Key names and state interpretation belong to the specific implementation and version.

## 5. First-Response Procedure

1. **Pause new triggers** writing to the same volume so the situation does not worsen. For running Jobs, use controlled stop mechanisms when appropriate.
2. Record Job name, JobInstance ID, JobExecution ID, identifying JobParameters, failed Step, exception, file path, host/pod, and timestamp.
3. Confirm whether the old worker is still alive or dead so two executions do not write to the same file during recovery.
4. Inspect free bytes, inodes, quotas, and actual mountpoints.
5. Restore headroom by expanding the volume or cleaning/moving **confirmed safe-to-delete** data. Keep metadata and staging files needed for restart intact.
6. Inspect the `BATCH_*` metadata database, input/output files, and checkpoints.
7. Decide whether to restart the same JobInstance, recover a stuck execution, retry publishing, or run a dedicated file-recreation workflow.
8. Monitor the new execution to completion; reconcile row counts, checksums, business keys, and downstream outcomes.

Avoid actions like wiping the entire working directory, truncating staging files, or clearing `BATCH_*` tables just to free space. Those actions can destroy checkpoints and processing history.

## 6. Diagnosing on Linux

Read-only inspection commands:

~~~bash
# Capacity of all mounted filesystems.
df -h

# Available inodes.
df -i

# Check the exact directory holding output files.
df -h /var/lib/batch/output
df -i /var/lib/batch/output

# Inspect space distribution in the batch area.
du -h -d 1 /var/lib/batch

# Deleted files still held open by a process handle.
lsof +L1

# Actual filesystem of output.
findmnt /var/lib/batch/output
~~~

`df` and `du` can report different numbers: deleted files held open by a running process still occupy blocks; filesystem metadata, reserved space, and nested mounts also affect totals.

**Watch log rotation:** deleting a large log file while the JVM or log appender still holds the file handle does not free disk space. Use proper log rotation/reopen/service restart once safe. Never delete a file a writer has open while the Job is running.

Before running `du` across a huge volume, scope it to suspect directories because it can generate heavy metadata I/O.

### Temporary Directories Can Fill Up Too

Many libraries rely on `java.io.tmpdir`, `TMPDIR`, or application-configured scratch paths. Processing a 2 GB ZIP file may need many GB of free space to decompress, sort/merge, and package output. Having 20 GB free in the output directory will not help if `/tmp` has only a few MB left.

## 7. Diagnosing on Kubernetes

For batch workloads running in Pods:

~~~bash
kubectl get pods -n batch
kubectl describe pod batch-worker-abc -n batch
kubectl get events -n batch --sort-by=.lastTimestamp
kubectl get pvc -n batch

# While the pod is still running:
kubectl exec -n batch batch-worker-abc -- df -h
kubectl exec -n batch batch-worker-abc -- df -i
~~~

Distinguish storage types:

- **Container writable layer**: data can vanish when a new Pod is scheduled.
- **emptyDir**: backed by node ephemeral storage or RAM depending on config; can trigger pod eviction when limits are exceeded.
- **PVC**: persistent storage, yet still bounded by capacity, quotas, and expansion limits.
- **Metadata database**: may live on a separate service; inspect the JDBC JobRepository's storage independently.
- **Stdout/stderr logs**: also consume node ephemeral storage.

Kubernetes recreating a Pod **does not mean** Spring Batch restarted the JobInstance. Kubernetes controllers manage Pods/Jobs at their own layer, whereas Spring Batch uses JobRepository and JobParameters to identify JobInstances.

If a staging file on a writable layer disappears while JDBC metadata retains checkpoints, restarts may fail to rebuild the file properly. Output files requiring restarts should sit on durable storage or have a safe rebuild workflow.

## 8. Diagnosing on Windows

In PowerShell, inspect storage with:

~~~powershell
Get-PSDrive -PSProvider FileSystem
Get-Volume

Get-CimInstance Win32_LogicalDisk |
    Select-Object DeviceID, Size, FreeSpace
~~~

Inspect the exact drives holding output, logs, and the TEMP directory of **the service account** running the application. Windows may report "There is not enough space on the disk" instead of the Linux ENOSPC wording.

## 9. What If JobRepository Cannot Write Metadata?

Under normal conditions, a Step throwing IOException is transitioned to an error state by Spring Batch and metadata persists:

~~~text
StepExecution: FAILED
JobExecution:  FAILED
ExitStatus:    FAILED
~~~

However, if the database volume also filled up or the JVM was killed mid-failure, metadata tables may still show:

~~~text
StepExecution: STARTED
JobExecution:  STARTED
~~~

`STARTED` in the database **neither proves the process is still running nor can it be assumed to mean FAILED**.

Steps to follow:

1. Verify the owning process, Pod, or worker has genuinely stopped.
2. Identify which transactions, file writes, and side effects completed.
3. Restore storage space and confirm JobRepository is operational.
4. Apply the metadata recovery mechanism matching your Spring Batch version.
5. Restart only when checkpoints and data can safely resume.

Spring Batch 6.x provides `JobOperator.recover(JobExecution)` to handle executions stuck `STARTED` after abrupt shutdowns, to be called only after verifying the old worker is dead. In Spring Batch 5.2.x, use a version-appropriate procedure; never manually edit the `STATUS` column on `BATCH_JOB_EXECUTION` just to bypass checks.

## 10. FlatFileItemWriter and Restartability

To export text/CSV files, `FlatFileItemWriter` implements `ItemStream` and saves state in `StepExecution.ExecutionContext`. Example for **Spring Batch 5.2.x**, Java 17:

~~~java
import java.nio.file.Path;
import java.time.LocalDate;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemWriter;
import org.springframework.batch.item.file.builder.FlatFileItemWriterBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

@Bean
@StepScope
FlatFileItemWriter<ExportRow> ordersWriter(
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    // Block non-date input before using it as a filename.
    LocalDate.parse(businessDate);

    Path output = Path.of(
        "/var/lib/batch/output",
        "orders-" + businessDate + ".csv.part");

    return new FlatFileItemWriterBuilder<ExportRow>()
        .name("ordersWriter")
        .resource(new FileSystemResource(output))
        .lineAggregator(row -> row.id() + "," + row.amount())
        .saveState(true)
        .transactional(true)
        .build();
}
~~~

`ExportRow` is an application domain model, such as a Java record with `id()` and `amount()`. The output directory in this example should be configured per environment.

| Setting | Effect |
| --- | --- |
| `@StepScope` | Creates a dedicated writer per StepExecution, reducing cross-run state sharing risks. |
| `name("ordersWriter")` | Supplies a stable name for keys in ExecutionContext. |
| `saveState(true)` | Enables the writer to persist state for restarts. |
| `transactional(true)` | Buffers writes transactionally along the standard path; **does not turn filesystem + JDBC into one distributed transaction**. |
| Filename keyed by businessDate | Keeps the same staging artifact across executions of the same JobInstance. |
| `.part` suffix | Signals the file is still in progress and downstream should not read it yet. |

The writer has options like `appendAllowed` and `shouldDeleteIfExists` controlling existing files and restarts. Do not casually toggle append when a file was partially written; keep state/settings aligned with the writer's restart contract and inspect outputs after failures.

**Never rename the staging file per JobExecution ID on each restart**, unless implementing a dedicated multi-file export protocol with reconciliation. Writer checkpoints may expect the previously used resource.

## 11. Input Files Must Also Stay Unchanged

If the Job uses `FlatFileItemReader` or `MultiResourceItemReader`, reader checkpoints remain trustworthy only when:

- The input resource still exists and has not been overwritten.
- Content, encoding, line order, and input file lists stay identical.
- The reader saves state with `saveState(true)` and is registered in the proper Step scope.
- Input filename patterns do not unexpectedly pick up new files during restart.
- No cleanup job deletes input after the first portion is processed.

Store input snapshot checksums, sizes, and versions in business audits to verify before restarting. For continuously mutating sources, use business-key checkpoints or snapshots rather than relying solely on line offsets.

## 12. Staging and Publishing After Job Success

A safer export pattern writes to an intermediate artifact and publishes only the completed file:

~~~text
Job starts
    |
    v
orders-2026-11-16.csv.part
    |
    +-- FAILED --> keep staging for inspection/restart
    |
    +-- COMPLETED
           |
           v
   Verify row count, checksum, schema
           |
           v
   Ensure file is closed
           |
           v
      Atomic rename
           |
           v
orders-2026-11-16.csv
    |
    v
Downstream is now allowed to read
~~~

Java NIO example:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

Path staging = Path.of(
    "/var/lib/batch/output/orders-2026-11-16.csv.part");
Path published = Path.of(
    "/var/lib/batch/output/orders-2026-11-16.csv");

Files.move(
    staging,
    published,
    StandardCopyOption.ATOMIC_MOVE);
~~~

Limitations:

- Atomic rename generally requires both paths to reside on **the same filesystem** supporting `ATOMIC_MOVE`.
- If `AtomicMoveNotSupportedException` occurs, never silently fall back to copying and claim atomic publishing.
- Rename alone does not guarantee `fsync` of file data to storage hardware before a power loss.
- Publishing a file while updating a separate database resource requires a dedicated protocol, such as a manifest/version marker or outbox.

If the Job reached `COMPLETED` yet the subsequent publish step failed from disk full, design **a standalone publish retry**. A completed JobInstance normally cannot be restarted with the same identifying JobParameters.

## 13. Restart Decisions After Space Is Restored

| Current State | Action |
| --- | --- |
| `FAILED` with valid checkpoints/files/input | Restart the same JobInstance. |
| `STOPPED` after controlled stop | Verify policy then restart. |
| `STARTING`/`STARTED`/`STOPPING` | Check whether the worker is still running; do not launch a new execution blindly. |
| `STARTED` yet process died | Apply version-appropriate metadata recovery procedure. |
| `COMPLETED` | Do not restart the completed batch; if publishing failed, retry publish. |
| `ABANDONED` | Cannot restart via standard flow; follow alternative operational procedure. |
| Output corrupted/lost while checkpoint exists | Not eligible for clean restart; reconcile or rebuild via dedicated workflow. |

In Spring Batch **5.2.x**, use `JobOperator.restart(long executionId)` after verifying preconditions:

~~~java
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.launch.JobOperator;

public class SafeRestartService {

    private final JobExplorer jobExplorer;
    private final JobOperator jobOperator;

    public SafeRestartService(
            JobExplorer jobExplorer,
            JobOperator jobOperator) {
        this.jobExplorer = jobExplorer;
        this.jobOperator = jobOperator;
    }

    public long restartFailed(long failedExecutionId) throws Exception {
        JobExecution previous =
                jobExplorer.getJobExecution(failedExecutionId);

        if (previous == null) {
            throw new IllegalArgumentException(
                    "Unknown execution: " + failedExecutionId);
        }

        if (previous.getStatus() != BatchStatus.FAILED) {
            throw new IllegalStateException(
                    "Execution is not FAILED: " + previous.getStatus());
        }

        // Disk, input, output, and worker checks must be performed
        // by the operations layer before reaching here.
        return jobOperator.restart(failedExecutionId);
    }
}
~~~

`restart` creates a new JobExecution for **the same JobInstance**. Generating a new identifying timestamp or `run.id` causes Spring Batch to create a brand-new JobInstance, re-read from the start, and produce duplicates.

In Spring Batch **6.x**, the operator API takes `jobOperator.restart(previousJobExecution)`, where the execution can be loaded via `jobRepository.getJobExecution(id)`. Syntax differences do not change identity/checkpoint principles.

### Restart Does Not Guarantee System-Wide Exactly-Once

If a writer writes files, updates a database, and calls an HTTP endpoint, each resource can commit or fail independently. Rerunning can resend already-succeeded requests. Use stable business idempotency keys, unique constraints, outboxes, or reconciliation.

## 14. Does Retrying IOException Help?

Immediate in-Step retry can help brief I/O glitches; however, **a genuinely full filesystem** rarely clears in milliseconds.

| Mechanism | When to Use |
| --- | --- |
| In-Step retry | Brief glitch, writer is safe to re-invoke, small retry limit and backoff. |
| Job restart | Space has been restored and metadata/file state remain valid. |
| Retry publish | Job completed yet the rename/publish operation failed. |
| Rebuild artifact via separate workflow | Output lost or corrupted; checkpoints no longer compatible. |
| Recover metadata | Stale `STARTED` execution after crash with worker confirmed dead. |

Avoid configuring large `retry(IOException.class)` counts for persistent ENOSPC. It holds transactions open, floods logs, and adds pressure to an already full volume.

## 15. Testing via Controlled Fault Injection

Never intentionally fill up a shared developer machine or CI runner disk. Split testing into two tiers:

**Tier 1 — Fault injection:** deliberately throw `IOException` inside an ItemWriter to test `FAILED` transitions, checkpoints, restarts, and final data.

**Tier 2 — Isolated storage tests:** use a small test-only volume/quota to simulate genuine ENOSPC, verifying partial-byte writes, flush, close, and filesystem behavior. Isolate test storage so other workloads are unaffected.

Example `ItemStreamWriter` wrapper in Spring Batch 5.2.x:

~~~java
import java.io.IOException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.ItemStreamException;
import org.springframework.batch.item.ItemStreamWriter;

public final class DiskFullFaultWriter<T>
        implements ItemStreamWriter<T> {

    private final ItemStreamWriter<T> delegate;
    private final AtomicBoolean faultEnabled;
    private final AtomicInteger chunkCalls = new AtomicInteger();

    public DiskFullFaultWriter(
            ItemStreamWriter<T> delegate,
            AtomicBoolean faultEnabled) {
        this.delegate = delegate;
        this.faultEnabled = faultEnabled;
    }

    @Override
    public void write(Chunk<? extends T> chunk) throws Exception {
        int call = chunkCalls.incrementAndGet();

        if (faultEnabled.get() && call == 3) {
            throw new IOException(
                "Simulated ENOSPC: No space left on device");
        }

        delegate.write(chunk);
    }

    @Override
    public void open(ExecutionContext context)
            throws ItemStreamException {
        delegate.open(context);
    }

    @Override
    public void update(ExecutionContext context)
            throws ItemStreamException {
        delegate.update(context);
    }

    @Override
    public void close() throws ItemStreamException {
        delegate.close();
    }
}
~~~

The wrapper must be registered as the Step-managed writer so ItemStream callbacks forward to the delegate. If both reader and writer require checkpoints, both must be registered and keep compatible state. In integration tests, set the fault flag `true` on the first execution, then set it `false` after the Job becomes `FAILED` and restart.

**Limitation:** the exception fires **before** the third chunk write, so it does not simulate the kernel writing half a line before raising ENOSPC. Use isolated storage tests whenever partial-write behavior must be verified.

### Testing Failure Followed by Restart

Suppose there are 10 items, chunk size 2, a stably ordered reader, and the writer above:

~~~java
// Assertion skeleton in Spring Batch 5.x:
// - Test JDBC JobRepository contains full BATCH_* tables.
// - Reader/writer save state and write output inside a test directory.
// - Do not delete metadata between the two executions.

JobParameters params = new JobParametersBuilder()
        .addString("businessDate", "2026-11-16")
        .toJobParameters();

faultEnabled.set(true);
JobExecution first = launcherTestUtils.launchJob(params);
assertEquals(BatchStatus.FAILED, first.getStatus());

// Restore simulated storage, using the same JobInstance:
faultEnabled.set(false);
long resumedId = jobOperator.restart(first.getId());

JobExecution resumed = jobExplorer.getJobExecution(resumedId);
assertEquals(first.getJobInstance().getInstanceId(),
             resumed.getJobInstance().getInstanceId());

// If running asynchronously, wait for terminal status:
// assert COMPLETED; read file and verify all 10 unique keys.
~~~

Across independent test methods, clean metadata **before** each test, never between failure and restart. With an asynchronous JobOperator, wait until the execution reaches terminal status rather than asserting right when `restart` returns.

### Test Matrix

| Fault Point | What Must Be Proven |
| --- | --- |
| Before opening file | Job fails safely; input is not lost. |
| After at least one committed chunk | Restart preserves committed work without duplicates. |
| Mid-line in output file | Partial file is not published; recovery respects writer/state. |
| During ExecutionContext update | Metadata and output are reconciled; no blind assumptions of alignment. |
| During flush/close | File state and Job outcome handled properly. |
| After COMPLETED, before publish | Publish retries independently. |
| Metadata DB cannot write | Execution may become stale; recovery is controlled. |
| Pod evicted | Staging on persistent storage survives, or rebuild workflow exists. |

## 16. Monitoring to Prevent Storage Exhaustion

Common signals:

| Metric | Source | Meaning |
| --- | --- | --- |
| `node_filesystem_avail_bytes` | Node exporter | Available bytes on the mountpoint. |
| `node_filesystem_size_bytes` | Node exporter | Total filesystem capacity. |
| `node_filesystem_files_free` | Node exporter | Free inodes remaining. |
| `kubelet_volume_stats_available_bytes` | Kubelet when supported | Available space on Kubernetes volumes. |
| Active output/staging size | Custom metric | Detects batches growing larger than expected. |
| Job FAILED by failure category | Batch logs/metrics | Early detection of storage incidents. |
| Age of unpublished `.part` files | Scanner/audit | Finds orphaned artifacts left after failures. |

Example PromQL for remaining percentage on a mountpoint:

~~~promql
100 *
node_filesystem_avail_bytes{
  mountpoint="/var/lib/batch/output"
}
/
node_filesystem_size_bytes{
  mountpoint="/var/lib/batch/output"
}
~~~

Thresholds below 15% for early warning and below 5% for critical are illustrative only. For very large volumes, combine **remaining bytes** with **projected bytes needed to finish the Job**.

A pipeline creating an intermediate file and copying across volumes may need space for both copies. Atomic renames on the same filesystem usually avoid a full duplicate copy, yet still require headroom for logs, metadata, and concurrent Jobs.

Rough capacity estimation formula:

~~~text
expected_output_bytes
    ~= expected_record_count * average_bytes_per_record

required_available_bytes
    >= expected_output_bytes
     + temp_or_copy_overhead
     + concurrent_job_headroom
     + operational_safety_margin
~~~

Account for unusually large records and peak concurrent Jobs rather than sizing solely for an average day.

## 17. Sample Recovery Runbook

| Step | Action | Expected Result |
| --- | --- | --- |
| 1 | Receive ENOSPC/EDQUOT or Job FAILED alert | Have execution ID, Step, volume, and timestamp. |
| 2 | Pause triggers writing to the volume | No additional output worsens the outage. |
| 3 | Check old worker, mountpoint, bytes/inodes/quotas | Identify real error and whether any process is still running. |
| 4 | Expand volume or reclaim verified safe space | Sufficient headroom for the remaining batch. |
| 5 | Inspect input, staging output, checkpoints, and `BATCH_*` | Know whether restarting is safe. |
| 6 | If metadata stuck STARTED after crash, recover per procedure | No concurrent execution runs alongside the old worker. |
| 7 | Restart exact JobInstance or recover publish | Avoid unintended new batch instances. |
| 8 | Verify Job COMPLETED and final data | Row count, checksum, and business keys complete with zero duplicates. |
| 9 | Publish file once closed/validated | Downstream receives a complete artifact. |
| 10 | Record incident, tune alerts/capacity plan | Reduce likelihood of recurrence. |

Incident record template:

~~~text
Job: exportOrdersJob
Identity: businessDate=2026-11-16
Failed JobExecution: 120
Step: exportCsvStep
Storage: /var/lib/batch/output (PVC)
Cause: ENOSPC
Action: volume expanded; old writer process confirmed stopped
Metadata: FAILED, checkpoint persisted
Recovery: restart same JobInstance -> JobExecution 121
Validation: COMPLETED, row count and checksum matched
Publish: .part renamed after validation
~~~

Record only verified facts. If staging files vanished or checkpoints are untrustworthy, record the blocker and switch to reconciliation/rebuild instead of forcing a restart just to get a green status.

## 18. Common Mistakes

**Checking only the root filesystem.** Output may reside on a separate mount; always inspect the failing path.

**Deleting `.part` files to free space.** Checkpoints may reference that file; deleting it destroys resumability.

**Deleting `BATCH_*` metadata.** Corrupts JobInstance history, ExecutionContext, and duplicate protection.

**Retrying IOException unboundedly.** While the disk remains full, retries achieve nothing and add load.

**Treating JDBC rollback as file rollback.** Files and databases do not automatically share one ACID transaction.

**Letting downstream read in-progress files.** Exposes incomplete/truncated data; use staging and atomic publishing.

**Naming output files by execution ID on restart.** Misaligns checkpoints and the artifact being recovered.

**Ignoring stale `STARTED` states.** When the DB cannot persist metadata or the process dies, stored status may lag behind reality.

**Skipping inode/quota checks.** Free bytes may remain while new files cannot be created.

**Putting output on a container writable layer while expecting restarts after Pod eviction.** Files disappear while JDBC metadata persists.

**Simulating ENOSPC on a shared CI disk.** Breaks unrelated workflows; use fault injection or isolated test storage.

## 19. Practice Exercises

### Exercise 1 — Storage Diagnostics

In a test environment, use `df -h`, `df -i`, `findmnt`, and `du` to locate the mountpoints holding output, logs, and temp files. Explain why free space on `/` does not guarantee space on the output volume.

### Exercise 2 — Per-Chunk Fault Injection

Create a Job reading 10 items with chunk size 2 and exporting CSV. Use `DiskFullFaultWriter` to fail before the third chunk write. Verify Job `FAILED`, disable the fault, and restart the same JobInstance; confirm the final file has all 10 unique IDs.

### Exercise 3 — Partial Writes on an Isolated Volume

Use a small quota-limited test volume to trigger genuine ENOSPC while writing a large file. Compare file size, complete lines, and persisted checkpoints; test recovery per writer mechanics. Perform this only on **isolated test storage**.

### Exercise 4 — Separating Metadata and Output Volumes

Place JDBC JobRepository on a different volume from output. Fail the output volume and inspect `JobExecution` and `ExecutionContext`; then test filling the metadata volume in an isolated environment to observe stale states.

### Exercise 5 — Atomic Publishing

Write `.part` files and rename to `.csv` only after Job COMPLETED and checksum/row-count validation. Simulate a failure right before publishing and demonstrate publish retry without rerunning the completed JobInstance.

### Exercise 6 — Kubernetes Storage

Use a dedicated PVC for output and `emptyDir` for temp in a test cluster. Observe what happens when the Pod is recreated, verify which staging files survive, and handle checkpoints accordingly.

### Exercise 7 — Pre-Exhaustion Alerting

Build a dashboard tracking available bytes, free inodes, Job FAILED by cause, and staging file sizes. Define thresholds based on **the largest expected batch run** rather than fixed percentages alone.

## 20. References

- [Spring Batch — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html)
- [Spring Batch — Flat File Item Writer](https://docs.spring.io/spring-batch/reference/readers-and-writers/flat-files/file-item-writer.html)
- [Spring Batch — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html)
- [Spring Batch — JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html)
- [Spring Batch — Advanced Metadata Usage](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html)
- [Spring Batch 5.2 — FlatFileItemWriter Javadoc](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/item/file/FlatFileItemWriter.html)
- [Java NIO — Files.move](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html)
- [Kubernetes — Local Ephemeral Storage](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/#local-ephemeral-storage)
- [Kubernetes — Persistent Volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/)

