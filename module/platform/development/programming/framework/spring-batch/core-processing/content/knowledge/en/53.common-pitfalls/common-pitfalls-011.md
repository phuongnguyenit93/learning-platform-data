# Not Cleaning Up Temporary Files After Failure in Spring Batch

## 1. Problem: Job FAILED, Yet Temporary Files Remain

In Spring Batch Core Processing, Steps can create intermediate files for downloading data, decompressing, sorting, transforming, or exporting results. If a Job fails, those files do not vanish automatically just because **BatchStatus** transitioned to **FAILED**. Without a management policy, temporary directories grow steadily and can fill up disks, cause another Job to accidentally read stale data, or expose sensitive data.

Example of an order-export Job:

~~~text
01:00 importOrdersJob starts
          |
          +-- downloadStep
          |     work/batch-A/input.csv
          |
          +-- transformStep
          |     work/batch-A/orders.csv.part
          |       Chunk 1: commit
          |       Chunk 2: commit
          |       Chunk 3: FAILED
          |
          +-- publishStep does not run
          |
          v
      Job FAILED

After failure:
  input.csv       still exists
  orders.csv.part still exists
  scratch/*.tmp   may still exist
~~~

After dozens of failures, not only is disk space consumed, but stale directories also complicate operations. However, **deleting all files immediately when a Job fails is also dangerous**: input snapshots and staging outputs may be required for a **restart**.

Therefore, the problem is not "delete temp files as fast as possible", but **cleaning up the right files, at the right time, within the right ownership scope, while preserving data recoverability**.

This lesson covers classifying files, structuring directories, understanding Spring Batch checkpoints, lifecycle-based cleanup, building a post-crash orphan sweeper, avoiding accidental deletions, testing failure/restart, and monitoring storage.

## 2. Classify Files Before Deciding Cleanup

Extensions like **.tmp** or **.part** are not enough to know whether a file can be deleted. Consider its actual role:

| Type | Example | Policy on FAILED |
| --- | --- | --- |
| Reproducible scratch | Intermediate sort files, decompression cache, temp buffers | Can clean once no worker is using it |
| Input snapshot | Immutable copy of input CSV/JSON | Keep if restart needs the exact same input |
| Output staging | `orders.csv.part` with several committed chunks | Keep if writer restart relies on file/checkpoint |
| Incomplete download | `input.download.part` | Depends on resume vs. re-download strategy |
| Rejected records | `rejected-records.csv` | Keep per error-handling and audit workflow |
| Checksum/manifest | `manifest.json`, `sha256.txt` | Keep to verify recovery/publishing |
| Published artifact | `published/orders.csv` | Not treated as scratch; apply dedicated retention |
| Log/audit artifact | `failure-report.json` | Follow security and retention requirements |

Three categories to remember:

**Scratch:** auxiliary files reproducible from durable data. Eligible for cleanup once the owning execution has stopped and no worker still uses them.

**Staging:** unpublished files holding valuable work. For instance, `FlatFileItemWriter` has written and checkpointed several chunks. Never delete unconditionally after failure.

**Artifact:** results verified and published downstream. It has its own business lifecycle outside scratch cleanup rules.

A sound design places these categories in separate directories to reduce accidental deletion.

## 3. Why Does Skipping Cleanup Cause Real Failures?

### Running Out of Disk Space or Inodes

One failure leaves behind 2 GB of temp files; 30 failures leave roughly 60 GB. With millions of small files, the filesystem can even exhaust inodes before running out of bytes. New Jobs hit `IOException` or fail to write outputs.

### Accidentally Reading Stale Data

Two runs share the name **/tmp/output.csv**. The second run may read or append to the old file, mixing data from two business periods even though the Job finishes normally.

### Accidentally Publishing Incomplete Files

A downstream task scans an entire directory with a wildcard, sees **orders.csv.part**, and treats it as a finished export. As a result, the receiving system processes partial transactions.

### Deleting Another Job's Files

Conversely, an overly broad cleanup triggered when Job A fails can delete files Job B is actively writing if both share a work root.

### Lingering Sensitive Data

Input or output files can hold personal data, transactions, customer names, or accidentally written tokens. Temporary directories must never be treated as "safe by default".

### Losing Recovery Data

If cleanup deletes staging output while `JobRepository` still holds an `ExecutionContext` pointing to a checkpoint position, restart can fail or produce inconsistent output.

Solutions must prevent both **never cleaning** and **over-cleaning**.

## 4. Distinguish JobInstance and JobExecution When Naming Directories

Spring Batch identifies a **JobInstance** by Job name and identifying `JobParameters`. A restart reuses the same identifying parameters while creating a new `JobExecution`.

Structure directories accordingly:

~~~text
/data/batch/
  inbound/
    batch-A/
      input.csv

  work/
    batch-A/
      orders.csv.part
      attempts/
        1001/
          scratch/
        1002/
          scratch/

  published/
    batch-A/
      orders.csv
      manifest.json
~~~

Where:

- **batch-A** is the stable identifier of a batch/JobInstance.
- **orders.csv.part** is staging that must remain reopenable on restart.
- **1001** and **1002** are distinct `JobExecution` IDs.
- **scratch/** belongs to an individual attempt and can be cleaned after that attempt ends.
- **published/** is strictly for verified artifacts.

Example identifying `JobParameters`:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("batchId", "orders-20261115", true)
        .addString("businessDate", "2026-11-15", true)
        .toJobParameters();
~~~

Do not generate a new identifying `batchId` just to restart the same period, as that creates a different `JobInstance` and bypasses the failed run's checkpoints.

Keying staging by **batchId** and scratch by **executionId** separates the lifecycles of restart-critical files and reproducible temp files.

## 5. Checkpoints and FlatFileItemWriter

In a chunk-oriented Step, Spring Batch normally persists state at commit boundaries via **ExecutionContext**. Readers/writers implementing **ItemStream** contribute state for restart.

Example staging output writer:

~~~java
@Bean
@StepScope
FlatFileItemWriter<ExportRow> exportWriter(
        @Value("#{jobParameters['batchId']}") String batchId,
        WorkspacePaths paths) {

    Path staging = paths.stagingOutput(batchId);

    return new FlatFileItemWriterBuilder<ExportRow>()
            .name("ordersExportWriter")
            .resource(new FileSystemResource(staging.toFile()))
            .lineAggregator(row ->
                    row.orderId() + "," + row.amount().toPlainString())
            .saveState(true)
            .build();
}
~~~

Assuming **ExportRow** is a domain record and **WorkspacePaths** governs paths. Parent directories must exist before the writer opens the file; input must also stay immutable across restarts.

**saveState(true)** lets the writer save restart state in `ExecutionContext`; it does not make the filesystem part of the database transaction. If the file is deleted, moved, or mutated by another process, checkpoint metadata may no longer align with file contents.

A failure can happen after writing to the file yet before the checkpoint commits. Therefore, restart must rely on tested reader/writer recovery logic rather than blindly opening the file in append mode and continuing.

Specifically:

- Never delete staging merely because of **BatchStatus.FAILED**.
- Never assume **commitCount** equals published file line count.
- Never manually edit `ExecutionContext` to skip failing lines.
- Never share the same output resource across two concurrent independent `JobInstance`s.
- If restart can move to another pod, staging must sit on appropriate shared storage or have a proven deterministic rebuild mechanism.

## 6. States Governing Cleanup Decisions

| Status | Execution-scoped scratch | Restart-required staging | Published output |
| --- | --- | --- | --- |
| COMPLETED, publish confirmed | Safe to clean | Clean once no dependencies remain | Retain per retention policy |
| FAILED, restartable | Clean once worker stopped | Keep | Do not publish failed output |
| STOPPED, to be resumed | Clean reproducible scratch | Keep | Leave unchanged |
| STARTED / STARTING | Do not clean while active | Do not clean | Do not touch |
| UNKNOWN or repository unreachable | Do not auto-delete | Keep and alert | Keep |
| ABANDONED | Follow operational runbook | Delete only after confirming no restart | Follow retention policy |
| Process crashed before listener | Sweeper handles after safety check | Keep until determined | Do not publish |

**FAILED does not authorize deleting all data.** Operators may restart a batch hours or days later. Retention must align with the allowed recovery window.

**Even COMPLETED may not allow deleting staging immediately** if reconciliation or downstream publishing runs asynchronously after the Job.

## 7. Safe Path Management

Another hazard is passing raw user parameters directly as file paths, causing path traversal bugs or accidentally deleting parent directories.

Example path-management class:

~~~java
import java.nio.file.Path;
import java.util.regex.Pattern;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public final class WorkspacePaths {

    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9_-]{1,80}");

    private final Path root;

    public WorkspacePaths(
            @Value("#{environment.getProperty('app.batch.work-root')}")
            String configuredRoot) {

        this.root = Path.of(configuredRoot)
                .toAbsolutePath()
                .normalize();
    }

    public Path batchDirectory(String batchId) {
        if (batchId == null
                || !SAFE_ID.matcher(batchId).matches()) {
            throw new IllegalArgumentException("Invalid batchId");
        }

        Path path = root.resolve(batchId).normalize();

        if (!path.startsWith(root)) {
            throw new SecurityException("Outside workspace");
        }

        return path;
    }

    public Path stagingOutput(String batchId) {
        return batchDirectory(batchId)
                .resolve("orders.csv.part");
    }

    public Path scratchDirectory(String batchId, long executionId) {
        if (executionId <= 0) {
            throw new IllegalArgumentException("Invalid executionId");
        }

        return batchDirectory(batchId)
                .resolve("attempts")
                .resolve(Long.toString(executionId))
                .resolve("scratch");
    }
}
~~~

Configuration:

~~~properties
app.batch.work-root=/var/lib/my-batch/work
~~~

This is **lexical path** validation. It does not by itself prevent all symlink/junction attacks if untrusted actors can modify directories. In production, place workspaces where only trusted service accounts can write, restrict filesystem permissions, and use environment-appropriate secure directory operations.

Never use a single fixed filename shared across all batches. Never accept an arbitrary path from an admin API and invoke recursive delete on it.

## 8. Cleaning Only One JobExecution's Scratch

You can use Java NIO to delete the scratch directory of a specific attempt once that attempt is no longer active:

~~~java
import java.io.IOException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;

import org.springframework.stereotype.Component;

@Component
public class ScratchCleaner {

    private final WorkspacePaths paths;

    public ScratchCleaner(WorkspacePaths paths) {
        this.paths = paths;
    }

    public void clean(String batchId, long executionId)
            throws IOException {

        Path scratch = paths.scratchDirectory(batchId, executionId);

        if (!Files.exists(scratch)) {
            return;
        }

        Files.walkFileTree(scratch, new SimpleFileVisitor<>() {

            @Override
            public FileVisitResult visitFile(
                    Path file, BasicFileAttributes attrs)
                    throws IOException {

                Files.delete(file);
                return FileVisitResult.CONTINUE;
            }

            @Override
            public FileVisitResult postVisitDirectory(
                    Path dir, IOException error)
                    throws IOException {

                if (error != null) {
                    throw error;
                }
                Files.delete(dir);
                return FileVisitResult.CONTINUE;
            }
        });
    }
}
~~~

**Files.walkFileTree** does not follow symbolic links within the tree by default, yet you must ensure roots and parents cannot be swapped with symlinks or junctions by an untrusted process during deletion. Where that cannot be guaranteed, use a safer directory/handle-based mechanism rather than relying on this simple example.

The cleaner's scope intentionally excludes:

- input snapshots;
- the JobInstance's `orders.csv.part` file;
- published outputs;
- another execution's scratch.

Never silently swallow **IOException**. On Windows, open files may be locked and fail deletion; on Linux, an unlinked file still consumes disk space while a process holds an open file descriptor.

## 9. Using JobExecutionListener for Normal Cleanup

**JobExecutionListener.afterJob** is a useful place to clean scratch after a Job ends normally or through framework-managed failure paths:

~~~java
import java.io.IOException;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;
import org.springframework.stereotype.Component;

@Component
public class FileCleanupListener implements JobExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(FileCleanupListener.class);

    private final ScratchCleaner cleaner;

    public FileCleanupListener(ScratchCleaner cleaner) {
        this.cleaner = cleaner;
    }

    @Override
    public void afterJob(JobExecution execution) {
        String batchId =
                execution.getJobParameters().getString("batchId");
        Long executionId = execution.getId();

        if (batchId == null || executionId == null) {
            log.warn("Cannot resolve scratch cleanup ownership");
            return;
        }

        try {
            cleaner.clean(batchId, executionId);
        } catch (IOException ex) {
            log.error(
                    "Scratch cleanup failed for batchId={}, executionId={}",
                    batchId, executionId, ex);
            // Emit a retry-cleanup event if needed.
        }

        if (execution.getStatus() != BatchStatus.COMPLETED) {
            log.info(
                    "Keep restartable staging after status={}, batchId={}",
                    execution.getStatus(), batchId);
        }
    }
}
~~~

Attach the listener to the Job:

~~~java
@Bean
Job exportJob(
        JobRepository repository,
        Step prepareStep,
        Step exportStep,
        Step publishStep,
        FileCleanupListener cleanupListener) {

    return new JobBuilder("exportJob", repository)
            .start(prepareStep)
            .next(exportStep)
            .next(publishStep)
            .listener(cleanupListener)
            .build();
}
~~~

This has clear intent: **clean only reproducible scratch of the current attempt**, keeping staging files if the Job is `FAILED`.

However, listeners are not an absolute cleanup guarantee. If the process is killed, power drops, a severe OOM strikes, or the container is terminated before callbacks run, **afterJob may never execute**. Therefore, a periodic orphan-sweeper task is still needed.

Do not throw exceptions from **afterJob** hoping Spring Batch will automatically flip a `COMPLETED` Job to `FAILED`. If cleanup is a mandatory business condition for Job success, model it as a controlled Step/flow outcome rather than relying on listener side effects.

## 10. Cleaning Up After Success: Publish First, Clean Up After

For file-export Jobs, add a **publishStep** after the writer Step finishes and resources are closed:

~~~text
Writer produces orders.csv.part
             |
             v
Verify line count, checksum, business rules
             |
             v
Publish/promote to orders.csv
             |
             v
Record durable manifest / publish status
             |
             v
Clean up staging per retention
~~~

If the filesystem supports atomic rename on the same volume, you can use:

~~~java
try {
    Files.move(
            stagingPath,
            publishedPath,
            StandardCopyOption.ATOMIC_MOVE);
} catch (AtomicMoveNotSupportedException ex) {
    throw new IllegalStateException(
            "Atomic publication required by the workflow", ex);
}
~~~

Paths and directories must be prepared properly. Not every filesystem or network mount supports **ATOMIC_MOVE**. On object storage like S3, rename is usually not an atomic filesystem operation; you may need copy, verify, and commit marker/manifest steps.

**Do not automatically fall back to copy-then-delete** if downstream consumers can read a half-copied file. One alternative is copying to a dedicated staging key/path at the destination, verifying checksums, and only then marking it published.

### Crash Between Publish and Updating JobRepository

What can happen:

~~~text
1. Move orders.csv.part -> orders.csv succeeds
2. JVM crashes before Spring Batch records Step COMPLETED
3. Restart publishStep
4. orders.csv already exists, .part is gone
~~~

The filesystem and `JobRepository` database do not inherently share an atomic transaction. Therefore, **publishStep must be idempotent**: when the target already exists, verify that it belongs to the right batch and matches the checksum/manifest, then treat it as published or escalate for investigation. Never unconditionally delete the target and republish.

A matching filename does not prove matching content; verification requires a trusted source.

## 11. Orphan Sweeper When Listeners Do Not Run

An **orphan sweeper** is a periodic task that finds files no longer belonging to an active execution and cleans them per policy. Do not rely on file age alone:

~~~bash
# Dangerous when run without metadata/ownership checks:
find /data/batch/work -type f -mtime +1 -delete
~~~

Files from a `FAILED` Job yesterday may still be needed for a restart today. Conversely, a scratch file created ten minutes ago may belong to a crashed process. File age is only part of the condition.

Safe algorithm:

~~~text
For each candidate:
  1. Resolve batchId, executionId, and file category.
  2. Verify the path resides inside the managed workspace.
  3. Query JobRepository / JobExplorer.
  4. If metadata cannot be queried: DO NOT DELETE.
  5. If Job is STARTING / STARTED / UNKNOWN: DO NOT DELETE.
  6. If execution finished and grace period elapsed:
        clean only reproducible scratch.
  7. If cleaning staging:
        require proof of completed publish or
        confirmed expiration of restart retention.
  8. Audit file count, bytes, and cleanup outcome.
~~~

Example using `JobExplorer`:

~~~java
JobExecution execution =
        jobExplorer.getJobExecution(jobExecutionId);

if (execution == null) {
    // Missing metadata: do not guess the file is orphaned.
    return;
}

BatchStatus status = execution.getStatus();

if (status == BatchStatus.STARTED
        || status == BatchStatus.STARTING
        || status == BatchStatus.UNKNOWN) {
    return;
}

// Still must check file type, safety grace period,
// ownership, and restart eligibility.
~~~

`JobRepository` can still show **STARTED** after a process actually died. Coordinate heartbeats/leases, node health, and operational procedures to confirm the execution has safely stopped. When uncertain, **keep the file and alert**.

If multiple scheduler instances run the sweeper, use a distributed lock or claim mechanism to prevent racing on the same candidate. Between checking status and deleting the file, a Job might restart; coordinate lifecycle/ownership to avoid **time-of-check/time-of-use races**.

## 12. Retention Should Not Be One Blanket TTL

Example retention table:

| Category | Clock start | Notes |
| --- | --- | --- |
| Scratch per attempt | Execution reached terminal state | Clean soon after grace period |
| Input snapshot of FAILED batch | Job failed / incident opened | Retain long enough for restart and investigation |
| Output staging `.part` | Verified publish or restart window formally closed | Do not delete while checkpoints depend on it |
| Reject/quarantine report | Per data quality workflow | May be required for audit |
| Published artifact | After publish date | Per downstream SLA and archival policy |
| Manifest/checksum | Per reconciliation requirements | Often kept longer than scratch |
| JobRepository metadata | Per dedicated repository retention | Never delete metadata needed for restart |

A 7-day TTL for staging is reasonable only if no Job is restarted past 7 days and the organization accepts that limit. Never deploy automated timestamp-based staging deletion without a business decision.

Metadata and files also have distinct lifecycles. Never delete `BATCH_*` rows arbitrarily alongside temp files: doing so destroys checkpoints and investigation history.

## 13. Filesystem Permissions and Sensitive Data

A temp directory can still contain personal data, transactions, system keys, or error logs. Security policy should require:

- Least-privilege service accounts on the work root.
- Never leaving directories world-readable when holding internal data.
- Never writing tokens/passwords into filenames, temp contents, or logs.
- Protecting volumes, snapshots, and backups with appropriate encryption.
- Reviewing retention for files holding sensitive data.
- Never letting an API accept arbitrary paths for recursive deletion.
- Auditing delete events, permission errors, and unauthorized access attempts.
- Keeping manifests/checksums for audit while minimizing payload exposure.

**`Files.delete` does not guarantee unrecoverable byte erasure** on all SSDs/filesystems. For secure-deletion requirements, rely on encryption policies, key lifecycles, and storage standards.

## 14. Differences Across Storage Environments

### Linux/POSIX

An unlinked file can still occupy disk space while a process holds an open descriptor. Calling delete does not guarantee immediate free space recovery. Inspect processes holding open files and check permissions.

### Windows

Open files may be locked and fail deletion/rename. Cleanup must catch `IOException`, record metrics, and retry once handles close.

### NFS or Shared Volumes

Cache, lock, and atomic rename semantics depend on the backend. Never assume an operation that works on local ext4 behaves identically across every NFS mount.

### Kubernetes

Using **emptyDir** for reproducible scratch is sensible in many cases; however, data needed for restarts across pod rescheduling may require a `PersistentVolume` or an independent durable source. **emptyDir** is not reliable for staging once a pod is evicted or deleted.

### Object Storage

On S3/GCS or similar stores, rename is usually emulated via copy/delete rather than an atomic move. Use staged object keys, checksums, manifests, and explicit publish states. Automated lifecycle rules must avoid deleting objects required for restart.

## 15. Failures Across Tasklets, Chunks, and Partitions

### Download Tasklets

A Tasklet can download into **download.part** and rename to **input.csv** only after complete download and checksum verification. If download fails:

- Keep `download.part` if safe resume exists.
- Delete and re-download if no resume exists and the source remains immutable.
- Never treat `download.part` as complete input.

### Chunk-Oriented Steps

The writer may have checkpointed several chunks. Never delete resources tied to **ItemStream** and `ExecutionContext` before deciding on restart. If the writer writes to the filesystem outside `JobRepository`'s transaction, test crashes at commit boundaries.

### Multi-Threaded Steps

Scratch paths should include partition ID/worker ID so one worker never deletes another worker's files. If one partition is `FAILED` while another is still `STARTED`, do not wipe the entire batch directory.

### Remote Partitioning

Workers may run on different pods, use separate storage, or still be active after the manager sees an error. Cleanup must verify workers have stopped, leases expired, and true resource ownership.

### Files Already Opened Downstream

If downstream consumers take time to read, cleanup must not delete artifacts based on producer publish time alone. Use acknowledgments or agreed retention windows.

## 16. Testing Failure and Restart

A good test must create temporary files **before the failure**. If an exception fires before files are written, the test fails to prove cleanup works.

Fixture:

~~~text
Input: 7 records
Chunk size: 3
Controlled failure at record #5

Execution 1:
  Chunk 1 (1,2,3) commits
  Chunk 2 hits failure
  Job FAILED

Execution 2:
  Restart with same identifying JobParameters
  Job COMPLETED
~~~

Required assertions:

1. First run reaches `BatchStatus.FAILED`.
2. Scratch for `JobExecution` #1 is cleaned or handled by the sweeper per SLA.
3. Output staging and input snapshots needed for restart remain intact.
4. No published output is marked complete while the Job is `FAILED`.
5. Second run uses the **same identifying parameters**, creating a new execution on the same `JobInstance`.
6. Final output contains all seven accurate records with no duplicates.
7. Files of other batches and running executions are untouched by cleanup.
8. Cleanup under locked files/permission denied logs properly and supports retry.

Illustrative integration test skeleton using Spring Batch Test and AssertJ:

~~~java
@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class TemporaryFileRecoveryTest {

    @Autowired
    private JobLauncherTestUtils launcher;

    @Autowired
    private WorkspacePaths paths;

    @Test
    void preservesStagingForRestart() throws Exception {
        String batchId = UUID.randomUUID().toString();

        // Input fixture and failure injection prepared beforehand.
        JobParameters params = new JobParametersBuilder()
                .addString("batchId", batchId, true)
                .toJobParameters();

        JobExecution first = launcher.launchJob(params);

        assertThat(first.getStatus())
                .isEqualTo(BatchStatus.FAILED);

        assertThat(Files.exists(paths.stagingOutput(batchId)))
                .isTrue();

        assertThat(Files.exists(
                paths.scratchDirectory(batchId, first.getId())))
                .isFalse();

        // Disable failure trigger before restarting.
        JobExecution restarted = launcher.launchJob(params);

        assertThat(restarted.getStatus())
                .isEqualTo(BatchStatus.COMPLETED);

        // Reconcile published output by business key/checksum.
    }
}
~~~

This example requires configuring the corresponding Job and fixtures; **`JobLauncherTestUtils`** must target the right Job and a synchronous launcher. Tests should use isolated workspaces, e.g., via **`@TempDir`** wired into test configuration—never production paths.

### Dedicated Cleaner Test

Create a layout:

~~~text
work/
  batch-A/
    orders.csv.part
    attempts/1001/scratch/a.tmp
  batch-B/
    attempts/1002/scratch/b.tmp
~~~

Calling **clean("batch-A", 1001)** must remove only `a.tmp` and execution 1001's scratch directory. `orders.csv.part` and `b.tmp` must remain untouched.

Add tests for invalid `batchId`s, non-existent directories, symlinks, file locks, insufficient permissions, and unreachable metadata backends.

## 17. Monitoring Cleanup

Cleanup should expose metrics like any other operational component:

| Metric | Purpose |
| --- | --- |
| `batch_temp_files_count` | Temp file counts by category |
| `batch_temp_bytes` | Total scratch/staging disk usage |
| `batch_orphan_candidates` | Candidates awaiting handling |
| `batch_cleanup_success_total` | Successful cleanup count |
| `batch_cleanup_failure_total` | Failed cleanup count |
| `batch_cleanup_bytes_freed_total` | Total space reclaimed |
| `oldest_temp_age_seconds` | Age of oldest temp file needing attention |
| `filesystem_free_bytes` | Remaining disk space |
| `filesystem_free_inodes` | Remaining inodes where filesystem supports them |

Do not classify `FAILED` staging still eligible for restart as an orphaned-scratch leak. Tag metrics by `file_type`, `job`, and `outcome`.

Avoid using `batchId`, `executionId`, or unique paths as Prometheus labels due to high cardinality. Those IDs belong in access-controlled logs/audits.

Alert when `work-root` grows continuously, cleanup errors exceed thresholds, the sweeper stops running, expired files lack remediation, or volume free space drops too low. Alerts **must never automatically trigger wiping the entire `work-root`**.

## 18. Common Mistakes

### Deleting an Entire Directory in `catch`

~~~java
try {
    runJob();
} catch (Exception ex) {
    deleteEverything(workRoot);
    throw ex;
}
~~~

This destroys restarts and deletes other Jobs' data. Classify files and scope ownership.

### Cleaning Up Only in `finally` or `afterJob`

`SIGKILL`, container crashes, or power loss can bypass callbacks. A periodic sweeper is essential.

### Picking a TTL Without Checking Status

Old files may still be needed for restart. Age is only one part of deletion criteria.

### Sharing `/tmp/output.csv`

Multiple executions can overwrite or delete each other's files. Scope paths by batch and attempt.

### Publishing `.part` Files

Downstream may read incomplete output. Only published artifacts count as complete.

### Deleting Target and Republishing on Restart

If the file already published before the crash, overwriting can corrupt valid data. Verify via manifest/checksum and idempotency.

### Swallowing `IOException` on Delete

Files keep piling up undetected. Log, record metrics, and retry.

### Deleting When `JobRepository` Is Unreachable

Unavailable metadata does not mean files are safe to delete. Fail closed and alert.

## 19. Production Adoption Workflow

1. Inventory all files produced by each Step: input, scratch, staging, rejected, manifest, and published.
2. Define ownership by **batchId**, **JobExecution ID**, partition, or worker.
3. Separate reproducible scratch from restart-critical staging.
4. Normalize paths and restrict filesystem permissions.
5. Configure lifecycle cleanup for scratch; never wipe staging purely on `FAILED`.
6. Build a post-crash sweeper that queries `JobRepository` and confirms no active owner remains.
7. Design a verified, idempotent publish step.
8. Set distinct retention policies for input, staging, reject reports, and published artifacts.
9. Test crashes mid-chunk, between publish and metadata updates, restarts, and concurrent cleanup.
10. Monitor disk space, overdue files, bytes freed, and cleanup errors.

### Quick Checklist

- [ ] No shared filenames across independent batches.
- [ ] Staging paths remain stable across restarts.
- [ ] Scratch is owned per attempt/partition.
- [ ] `FAILED`/`STOPPED` does not delete checkpoint-required files.
- [ ] Downstream reads only `published`, never scanning `staging`.
- [ ] Cleanup listeners handle `IOException`.
- [ ] Sweeper never deletes when status is running/`UNKNOWN` or metadata is unreachable.
- [ ] Protections against path traversal, symlinks, bad permissions, and sensitive data leaks.
- [ ] Retention- and workflow-driven cleanup policy exists.
- [ ] Tests cover failure, restart, idempotency, and output correctness.

## 20. Conclusion

**Not cleaning up temporary files after failure** is an operational bug that accumulates silently until disks fill up, stale data is misread, or sensitive data leaks. Yet **deleting everything immediately on failure** can wipe checkpoint resources and break restartability.

A proper design separates three lifecycles: **scratch can be cleaned once its execution stops; input snapshots and staging stay intact while restart remains possible; published artifacts follow dedicated business retention**. Combining normal lifecycle cleanup, a post-crash orphan sweeper, safe path handling, idempotent publishing, and failure/restart tests keeps Spring Batch clean without sacrificing recovery accuracy.

