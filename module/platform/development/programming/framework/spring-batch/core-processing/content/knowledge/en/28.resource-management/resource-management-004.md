# Temporary Files and Cleanup

In Spring Batch, a Job often works with many file resources: input files downloaded from external systems, unpacked files, intermediate data, in-progress output files, or staging files waiting to be published. These files may need to persist across multiple Steps, across restarts, or only briefly for a single operation. Therefore, temporary file management must be tied to the Job/Step execution lifecycle and restart policy.

Cleanup is not simply deleting every file ending in `.tmp` when a Step ends. If input or staging files needed for restart are deleted, the Job may fail to resume. If all files are kept indefinitely, the working directory will fill up with disk space and expose old data. A good design clearly identifies who creates a file, who owns it, when it expires, whether it is needed for restart, and whether deletion is safe on re-run.

## 1. Types of temporary files in a Batch Job

A Batch workflow can create several file types with different lifecycles:

| File Type | Example | Typical Lifecycle |
|---|---|---|
| Input copy | File downloaded from SFTP or object storage to local disk | Keep until the Job completes and restart is no longer needed. |
| Unpacked file | CSV extracted from a ZIP archive | Keep during the reading Steps, then it can be deleted. |
| Intermediate file | Sort, merge, normalize, or spill data file | Keep only during the Steps that use it. |
| Output staging | `orders.csv.part` being written by the writer | Keep when the Step needs restart; publish only when output is complete. |
| Reject/error file | Invalid lines requiring reprocessing | Keep according to business and retention policy. |
| Log/manifest file | Checksums, metadata, export status | Keep long enough for auditing or reconciliation. |

The first thing to do is classify files by purpose. A file ending in `.tmp` is not necessarily safe to delete immediately; it could be a checkpoint or output staging file needed on the next restart.

## 2. Separating deletable temporary files from files needed for restart

Distinguish at least three groups:

- **Scratch file:** intermediate data that can be regenerated from input and does not need to be kept after the operation ends. Can be deleted when the resource closes or when the Step succeeds.
- **Restartable staging:** intermediate or in-progress output files that the Job must reopen to resume after a failure. Must be preserved across `FAILED`/`STOPPED` and deleted only after restart is no longer needed.
- **Published artifact:** output files verified as complete and published to downstream systems/users. Must not be deleted in normal Job cleanup; separate retention applies.

For example, an unpacked file may be scratch if the Job can always re-download and re-extract it. However, if the original input file was deleted from SFTP after download, the local copy may be a restartable input and must be kept until the Job completes.

For output, a `.part` file is usually restartable staging. The final `.csv` file is the published artifact. Post-success cleanup may delete leftover `.part` files and scratch directories, while preserving the final output file.

## 3. Setting up working directories and file naming conventions

Do not create temporary files arbitrarily in the process's current working directory. Configure a dedicated working directory for the application, for example:

```text
/var/lib/my-batch/
  work/
    order-import/
      instance-8124/
        input/
        scratch/
        staging/
  published/
    orders/
  rejected/
  archive/
```

Organizing by Job and JobInstance helps isolate resources across business runs. A directory may include:

- `input/`: input copies retained for restart.
- `scratch/`: regenerable intermediate files.
- `staging/`: unpublished outputs.
- `published/`: completed artifacts.
- `rejected/`: error files or records requiring reconciliation.

Filenames should include stable, traceable identifiers, for example:

```text
orders-2026-11-15-instance-8124.input.csv
orders-2026-11-15-instance-8124.output.part
orders-2026-11-15-instance-8124.output.csv
orders-2026-11-15-instance-8124.manifest.json
```

Do not use a generic name like `temp.csv` across all executions. Two concurrent Jobs could overwrite or delete each other's files.

### Using JobInstance identity instead of JobExecution ID for restartable files

A JobInstance can have multiple JobExecutions due to restarts. If a file must be reopened on restart, its path must remain stable across JobExecutions belonging to the same JobInstance.

Do not generate restartable staging filenames solely from `jobExecution.getId()`, because restarting creates a new JobExecution. You can use the JobInstance ID or a stable business key derived from identifying JobParameters to build the directory. If a file only exists for a single attempt and does not need restart, a name containing the JobExecution ID may be appropriate.

For example, `business.date` and `tenant.id` can form a stable operation key if they truly identify a single business run. Ensure two different Jobs do not accidentally share the same namespace.

## 4. Creating temporary files with Java NIO

For scratch files used only within a single operation, `Files.createTempFile` generates a unique name and avoids collisions with other executions:

```java
Path scratchFile = Files.createTempFile(
        configuredScratchDirectory,
        "orders-",
        ".tmp");

try {
    transformInput(scratchFile);
    consumeIntermediateFile(scratchFile);
} finally {
    Files.deleteIfExists(scratchFile);
}
```

`deleteIfExists` is idempotent at the deletion level: if the file is already gone, a subsequent call does not throw an error merely because it no longer exists. However, access permission errors, open file locks, or unavailable filesystems must still be handled.

For files needed on restart, do not generate a new random name each time the Step opens. Create a stable path keyed by JobInstance or store the generated path in the `ExecutionContext`, then reopen that exact file on restart.

### Creating a dedicated directory for an execution

```java
Path workDirectory = configuredWorkRoot
        .resolve("order-import")
        .resolve("instance-" + jobInstanceId)
        .normalize();

Files.createDirectories(workDirectory.resolve("scratch"));
Files.createDirectories(workDirectory.resolve("staging"));
```

`createDirectories` can be called multiple times for the same path. `jobInstanceId` must come from trusted metadata rather than concatenating arbitrary user-supplied strings into paths.

## 5. Keeping input files stable across restarts

If a Job reads files from SFTP, HTTP, or object storage, define when downloading occurs and how the local copy is retained.

A safe workflow typically looks like:

1. Download the input to a `.download.part` file inside the JobInstance's dedicated directory.
2. Verify size, checksum, or manifest per the source contract.
3. Close the file and rename it to the complete input staging file.
4. Store the input path/checksum in metadata or a durable manifest.
5. Subsequent Steps read only the verified input copy.
6. Delete the input copy only when the Job finishes and restart/retention policies allow it.

If the process is killed mid-download, the `.download.part` file may be incomplete. On restart, check the manifest/checksum and re-download or resume downloading depending on source capabilities. Never read a partial file as complete input.

For immutable inputs, a checksum can verify that the restarted file matches the file from the original business run. Do not rely solely on filename, as the source might replace content at the same path.

## 6. Using Resource in Spring Batch

Spring Batch uses Spring's `Resource` abstraction to work with files and other data sources. Some common implementations:

| Resource | Source |
|---|---|
| `FileSystemResource` | File on the filesystem. |
| `ClassPathResource` | Resource on the classpath. |
| `UrlResource` | Resource accessed via URL. |
| `ByteArrayResource` | Byte data in memory. |
| `InputStreamResource` | A pre-supplied InputStream. |

Example of a reader reading a local file:

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['input.file']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("orderId", "customerId", "amount")
            .targetType(OrderInput.class)
            .saveState(true)
            .build();
}
```

The reader can open the resource during the Step lifecycle and save read state for restart. Deleting the input file must happen after all Steps requiring it have completed, not while the reader is still using it.

With `InputStreamResource`, keep in mind that a stream can typically only be read once. If the Job must restart, use a re-openable resource such as a local file or a URL/resource with stable reopen semantics, instead of holding onto an already-consumed InputStream.

## 7. ItemStream lifecycle and closing resources

Readers/writers can implement `ItemStream`. Spring Batch manages the callbacks:

```java
public interface ItemStream {
    void open(ExecutionContext executionContext)
            throws ItemStreamException;

    void update(ExecutionContext executionContext)
            throws ItemStreamException;

    void close() throws ItemStreamException;
}
```

- `open`: opens the file, stream, or cursor and restores state.
- `update`: saves state needed for restart into `ExecutionContext`.
- `close`: closes handles, streams, cursors, or resources.

`close()` is the place to release open resources, such as closing a stream or deleting a scratch file scoped solely to the reader's lifecycle. However, input or staging files needed for restart should not be deleted here. `close()` is also not guaranteed to run if the JVM is killed abruptly.

If implementing a custom reader/writer holding file handles, close them in `close()` and ensure closing is safe across different exit paths. For resources created outside the stream, clearly define the owning component and the component responsible for deletion.

## 8. Using FlatFileItemWriter with output staging

For output files, a common pattern is writing to a staging file first, then publishing when the Step/Job completes. Example writer:

```java
@Bean
@StepScope
FlatFileItemWriter<OrderOutput> orderWriter(
        @Value("#{jobParameters['output.staging.file']}") String stagingFile) {

    return new FlatFileItemWriterBuilder<OrderOutput>()
            .name("orderWriter")
            .resource(new FileSystemResource(stagingFile))
            .delimited()
            .names("orderId", "amount", "tax")
            .saveState(true)
            .shouldDeleteIfExists(false)
            .build();
}
```

The `output.staging.file` path must remain stable for the same JobInstance if restarts are to resume already-written output. `saveState(true)` lets the writer store the necessary position/progress in the ExecutionContext. Do not enable deleting the file on reopen if the goal is to continue previous output; specific configuration must align with restart semantics and the Spring Batch version in use.

After the writer closes successfully and the Step/Job is confirmed complete, a publish step can rename the staging file to the target file. Do not publish the file while the writer is still open or before all required validation has completed.

## 9. Publishing completed files with atomic move

If staging and final output reside on the same filesystem and the filesystem supports atomic renames, `Files.move` with `ATOMIC_MOVE` can be used:

```java
Files.move(
        stagingPath,
        finalPath,
        StandardCopyOption.ATOMIC_MOVE);
```

Atomic renaming ensures consumers see the final file only after its contents are complete, rather than reading an in-progress file. This is why writing to `.part` or staging first is recommended.

However, atomic move has limitations:

- Source and destination must be on the same filesystem/volume depending on provider capabilities.
- The filesystem/provider may not support `ATOMIC_MOVE`.
- Behavior when the target file already exists depends on the provider and options.
- Atomic rename does not share a transaction with JobRepository or the business database.

If `ATOMIC_MOVE` is not supported, explicitly decide whether to allow falling back to a regular move or fail for operations handling. Do not silently copy a large file and delete the source if consumers can read the target file mid-copy.

### Publishing must be idempotent

The process can die after the move succeeds but before JobRepository records the publish Step as complete. On restart, the Step may be re-invoked and the staging file no longer exists because it was already moved.

The Publish Tasklet must check state:

- If staging exists and final does not exist: perform the move.
- If staging does not exist but final exists and checksum matches: consider the output already published.
- If both exist: compare checksums/manifest and handle per policy; do not overwrite arbitrarily.
- If neither exists: fail because the output was never created or was unexpectedly deleted.

Do not rely solely on the target file existing; that file might belong to another run or contain incomplete data.

## 10. Creating a Publish Step and Cleanup Step

Separate writing output, publishing, and cleanup into distinct stages. Example flow:

```text
Download Input
      |
      v
Process Orders (write staging)
      |
      v
Validate Output
      |
      v
Publish Output
      |
      v
Cleanup Scratch
```

Publish runs only when processing and validation succeed. Scratch cleanup can run after publish. If the Job fails before publish, staging must be preserved if restart will resume the writer.

Example publish Tasklet:

```java
@Bean
@StepScope
Tasklet publishOutputTasklet(
        @Value("#{jobParameters['output.staging.file']}") String stagingName,
        @Value("#{jobParameters['output.final.file']}") String finalName) {

    return (contribution, chunkContext) -> {
        Path staging = Path.of(stagingName).toAbsolutePath().normalize();
        Path target = Path.of(finalName).toAbsolutePath().normalize();

        if (Files.exists(staging)) {
            verifyOutput(staging);
            Files.createDirectories(target.getParent());
            Files.move(staging, target, StandardCopyOption.ATOMIC_MOVE);
        } else if (Files.exists(target)) {
            verifyPublishedOutput(target);
        } else {
            throw new FileNotFoundException(
                    "Neither staging nor final output exists");
        }

        return RepeatStatus.FINISHED;
    };
}
```

This is an illustrative skeleton; add checks for allowed root paths, handling pre-existing target files, checksum verification, and behavior when atomic move is unsupported. Do not accept arbitrary paths from users and move/delete them without validating scope.

The Cleanup Step should only delete files identified as scratch that are no longer used by subsequent Steps or restarts. A dedicated Tasklet can delete a list of resources registered in the Job/Step context.

## 11. Cleanup after Job success

When the Job completes successfully, you can delete:

- Unpacked files that can be regenerated.
- Intermediate sort/merge files.
- The JobInstance's dedicated scratch directory.
- Leftover `.part` files after successful publishing.
- Input copies if retention policy permits and they are no longer needed for auditing/reprocessing.

Do not delete:

- Published output files still within retention.
- Reject files requiring user handling.
- Manifests/checksums needed for reconciliation.
- Input or staging files still required by restart/recovery policies.

`JobExecutionListener.afterJob` can be used to perform cleanup only when the Job is `COMPLETED`:

```java
public class SuccessfulJobCleanupListener implements JobExecutionListener {

    private final Path allowedWorkRoot;

    public SuccessfulJobCleanupListener(Path allowedWorkRoot) {
        this.allowedWorkRoot = allowedWorkRoot.toAbsolutePath().normalize();
    }

    @Override
    public void afterJob(JobExecution jobExecution) {
        if (jobExecution.getStatus() != BatchStatus.COMPLETED) {
            return;
        }

        ExecutionContext context = jobExecution.getExecutionContext();
        if (!context.containsKey("batch.scratch.directory")) {
            return;
        }

        Path scratchDirectory = Path.of(
                context.getString("batch.scratch.directory"))
                .toAbsolutePath()
                .normalize();

        if (scratchDirectory.equals(allowedWorkRoot)
                || !scratchDirectory.startsWith(allowedWorkRoot)) {
            throw new IllegalStateException(
                    "Scratch directory is outside the allowed work root");
        }

        deleteDirectoryTree(scratchDirectory);
    }
}
```

`batch.scratch.directory` must be written to the Job ExecutionContext by trusted code during Job preparation. The listener may only delete subdirectories of the configured root. Do not take paths from payloads or untrusted parameters and delete them directly.

`afterJob` does not run if the process is killed abruptly. Furthermore, if cleanup throws an exception after the Job has already finished, decide how to represent cleanup failures and retry cleanup; do not let a file deletion error obscure already-committed business processing results.

## 12. Safe recursive directory deletion

Java NIO can walk a directory tree and delete files before parent directories:

```java
static void deleteDirectoryTree(Path directory) {
    if (!Files.exists(directory)) {
        return;
    }

    try (Stream<Path> paths = Files.walk(directory)) {
        paths.sorted(Comparator.reverseOrder())
                .forEach(path -> {
                    try {
                        Files.deleteIfExists(path);
                    } catch (IOException exception) {
                        throw new UncheckedIOException(exception);
                    }
                });
    } catch (IOException | UncheckedIOException exception) {
        throw new IllegalStateException(
                "Could not clean directory " + directory,
                exception);
    }
}
```

This example demonstrates deletion order; production implementations should decide how to handle symlinks, in-use files, and per-file errors. `Files.walk` does not follow symbolic links by default, but deleting symlinks and validating root paths still require careful design.

Do not call this recursive method on shared roots like `/tmp`, the data directory, or directories shared by multiple Jobs. Delete only the specific directory owned by a single JobInstance after verifying it resides under the configured work root.

## 13. Cleanup when a Job fails or is stopped

Do not apply the same deletion policy across all terminal statuses.

| Status | Regenerable Scratch | Input Needed for Restart | Output Staging Needed for Restart |
|---|---|---|---|
| `COMPLETED` | Can delete | Delete/archive per retention | Delete leftovers after publish. |
| `FAILED` | Can delete if no longer needed for diagnostics | Keep | Keep if restart resumes the writer. |
| `STOPPED` | Depends on checkpoint and flow | Usually keep | Usually keep if the Job will restart. |
| `ABANDONED` | Delete per termination procedure | Can archive then delete | Delete only after confirming no restart. |
| Process killed | No cleanup callback | Keep until recovery decision | Keep until commit/restart status is determined. |

For failed Jobs, pure scratch can be deleted if certain it can be regenerated and is not needed for investigation. However, retain logs, manifests, reject files, or intermediate files needed for recovery. A safe option is marking the execution directory as `FAILED` and letting a retention sweeper handle it after a grace period.

Do not delete input or output staging immediately inside `afterStep` when a Step fails if the Job may be restarted. The restart may need those exact files.

## 14. Cleanup in close() vs post-Job cleanup

`ItemStream.close()` releases resources held open by the reader/writer. This is component-level cleanup:

```java
@Override
public void close() {
    if (reader != null) {
        reader.close();
    }
}
```

`JobExecutionListener.afterJob()` or a Cleanup Step manages Job-level resources: deleting scratch directories, temporary input files, or staging files no longer needed.

Do not mix the two responsibilities:

- `close()` closes open handles, streams, cursors, and resources.
- Cleanup Step/listener deletes files or directories whose lifecycle has ended.
- Retention sweeper handles orphaned resources after crashes or expiration.

A reader can be closed when a Step finishes while the input file is still needed for subsequent Steps or restarts. Closing a file does not mean deleting the file.

## 15. Cleanup on process kill: orphaned temporary files

If the JVM is killed, `finally`, `close()`, `afterStep()`, and `afterJob()` may not run. Scratch or staging files may remain after JobRepository marks an execution stale or after the process restarts.

Therefore, production typically needs a separate orphan-file cleanup mechanism, such as:

- A scheduled cleanup Job running periodically.
- An operational task checking expired execution directories.
- A startup recovery task inspecting files of terminated executions.
- A retention service reading manifests and JobRepository to identify unreferenced resources.

Do not simply delete every file with a modification time older than N days. A long-running Job or one awaiting approval might still need older files. The sweeper should combine file age with execution status, owner/lease, and resource type.

### Manifest for temporary directories

Each JobInstance directory can include a manifest describing files and their purpose:

```json
{
  "jobName": "orderImportJob",
  "jobInstanceId": 8124,
  "businessKey": "tenant-42-2026-11-15",
  "resources": [
    {
      "path": "input/orders.csv",
      "kind": "RESTARTABLE_INPUT",
      "checksum": "sha256:..."
    },
    {
      "path": "scratch/unpacked.csv",
      "kind": "SCRATCH",
      "checksum": "sha256:..."
    },
    {
      "path": "staging/orders.csv.part",
      "kind": "RESTARTABLE_OUTPUT",
      "checksum": null
    }
  ]
}
```

The manifest should be updated consistently and contain only relative paths under the owned directory. It helps the sweeper distinguish files to keep from files safe to delete.

## 16. Retention and periodic cleanup Jobs

Periodic cleanup should have retention policies per resource type:

| Resource | Example Retention Policy |
|---|---|
| Scratch file | Delete after Job completes; orphans may be kept a few days for investigation. |
| Incomplete download staging | Delete after confirming the execution is inactive and past deadline. |
| Restartable input | Keep until Job is terminal and past the restart/reprocess window. |
| Output staging | Keep while Job is `FAILED`/`STOPPED`; delete after successful publish or controlled abandon. |
| Published output | Per business requirements, auditing, and retention period. |
| Reject file | Per error-handling SLA and storage policy. |
| Manifest/checksum | Keep long enough for auditing, verification, and reconciliation. |

A cleanup Job should:

1. List execution directories under the work root.
2. Read manifests and identify associated JobInstance/JobExecution records.
3. Check whether the execution is running, stopped, or holds an active lease.
4. Select only resources past their lifecycle and retention period.
5. Audit deleted files.
6. Delete files before directories.
7. Record metrics for file count, total size, and cleanup failures.
8. Be safe to re-run if interrupted midway on a previous attempt.

A cleanup Job is also a Batch Job; it must be idempotent and strictly scoped.

## 17. Path safety and access permissions

Cleanup can delete critical data if paths are constructed or validated incorrectly. Key principles:

- Configure the work root on the application side; do not accept arbitrary root paths from JobParameters.
- Normalize paths using `toAbsolutePath().normalize()`.
- Verify the path to delete is a subdirectory of the allowed root and not equal to the root itself.
- Use dedicated directories per JobInstance to avoid deleting another Job's resources.
- Do not follow symlinks when walking trees unless explicitly required.
- Do not use wildcard deletes on shared directories.
- Restrict filesystem permissions for the Batch process user.
- Do not store secrets in filenames or manifests.
- Audit deletions of important data.

Example path validation:

```java
static Path requireChildOf(Path allowedRoot, Path candidate) {
    Path root = allowedRoot.toAbsolutePath().normalize();
    Path target = candidate.toAbsolutePath().normalize();

    if (target.equals(root) || !target.startsWith(root)) {
        throw new IllegalArgumentException(
                "Path is outside the allowed work directory");
    }

    return target;
}
```

Lexical path checks with `normalize()` are one layer of protection, but if symbolic links or directories modifiable by other users exist, verify the actual filesystem and access permissions appropriately. Do not rely on `startsWith` alone in environments with untrusted filesystem writers.

## 18. Cleaning up files when multiple Jobs run concurrently

Multiple Jobs or replicas may share a single work root. Cleanup must know resource ownership.

Measures:

- Create separate directories per Job name and JobInstance ID.
- Do not share fixed-name temporary files.
- Record owner metadata including JobExecution ID, JobInstance ID, host/container, and creation time.
- Use leases/locks if multiple processes may manage the same directory.
- Sweeper deletes only when the owner is inactive and the lease has expired.
- Avoid cleaning up based solely on modification time because a file in use may not change continuously.

With restarts, JobExecution ID changes while JobInstance ID stays the same. Thus, the manifest can record both JobInstance ID and the list of JobExecution IDs that used the directory for auditing.

## 19. Handling cleanup errors

Cleanup can fail due to open files, permission denied, disk I/O errors, or an unavailable network filesystem. Decide whether cleanup is a mandatory requirement or retryable post-processing.

Two common models:

### Cleanup as a mandatory part of the flow

If the Job is considered complete only after resources are cleaned up, use an explicit Cleanup Step before the Job finishes. The Cleanup Step can retry transient errors and fail if required deletions cannot succeed.

### Cleanup as post-processing

If business data is complete and file deletion can be deferred, record a cleanup request or let a sweeper handle it. The main Job reflects the business outcome; cleanup failures are logged via metrics/auditing and can be retried.

Do not swallow every `IOException` without recording it. Doing so causes disk usage to grow silently without alerts. Conversely, do not fail the business Job solely because deleting an unimportant scratch file failed if a durable separate cleanup mechanism exists.

## 20. Do not use deleteOnExit as the primary cleanup mechanism

`File.deleteOnExit()` only asks the JVM to delete the file when the JVM exits normally. It is unsuitable as the main cleanup mechanism for long-running Batch services:

- Files are not deleted immediately after the Step finishes.
- The JVM may run for days, causing files to accumulate.
- Killed processes or machine crashes may skip shutdown hooks.
- The delete-on-exit registry can grow with the number of files.
- It does not support retention per JobInstance or restart.

Use `try/finally`, `ItemStream.close`, a Cleanup Step, conditional listeners, or a retention sweeper depending on resource lifecycle.

## 21. Testing temporary file lifecycles

Tests should verify that files are created, retained when needed for restart, and deleted at the proper time.

Scenarios to test:

- Job succeeds: scratch is deleted, final output remains.
- Job fails: input and staging needed for restart remain intact.
- Job is stopped: resources needed for restart are not deleted.
- Process is killed: orphan files are detected by the sweeper after verifying the execution is inactive.
- Publish Step re-runs: already-published file is verified and not duplicated.
- Cleanup runs twice: the second run does not fail merely because files are already gone.
- Path traversal: paths outside the work root are rejected.
- Symlink: cleanup does not accidentally delete data outside the owned directory.
- Two concurrent Jobs: one Job's cleanup does not affect the other Job's files.
- Open file: cleanup reports an error or defers per policy, rather than performing uncontrolled partial deletion.
- Disk full/permission denied: errors are recorded with retry or alerting mechanisms.

Example unit test for idempotent deletion:

```java
@Test
void cleanupCanRunMoreThanOnce() throws IOException {
    Path directory = Files.createTempDirectory("batch-cleanup-test-");
    Path file = Files.writeString(directory.resolve("scratch.tmp"), "data");

    deleteDirectoryTree(directory);
    deleteDirectoryTree(directory);

    assertThat(Files.exists(file)).isFalse();
    assertThat(Files.exists(directory)).isFalse();
}
```

This test verifies the delete operation can be called again on an already-deleted directory. Integration tests should additionally check Job metadata, restarts, and actual staging files.

## 22. Common Pitfalls

### Deleting input as soon as the reader closes

The reader may close after a Step while the Job has not finished or still needs the file for restart. Delete input only when all consumers are done and restart policy permits.

### Deleting staging when a Job fails

The writer may need to reopen the file to resume. Keep staging across `FAILED`/`STOPPED` if it belongs to the restart contract.

### Using fixed temporary filenames

Concurrent Jobs can overwrite or delete each other's files. Namespace by JobInstance/operation.

### Generating new names by JobExecution ID for restartable files

Restart creates a new JobExecution, so it may not find the old file. Use a stable path per JobInstance or store the path in metadata.

### Publishing while the writer is still open

The file may lack the final buffer or still be written to. Close the writer, flush, and validate before moving.

### Thinking atomic move shares a transaction with JobRepository

Filesystem renames do not commit together with database metadata. The process can die between the move and status update; the publish Step must be idempotent and checksum-verified.

### Cleanup only in finally/close

Process kills skip cleanup callbacks. A sweeper/retention mechanism is needed for orphaned files.

### Deleting every file older than a few days

Long-running Jobs or those awaiting restart may still need older files. Check JobRepository, owner, manifest, and per-resource retention.

### Using deleteOnExit in long-running servers

Files are only requested for deletion on JVM exit and can accumulate while the application runs. Use lifecycle-based cleanup.

### Swallowing file deletion errors

Disk usage can grow unnoticed. Log/emit metrics and provide retry or alerts.

## 23. Process for designing temporary files and cleanup

When adding a file to a Batch Job, define its lifecycle before writing code:

1. Classify the file as input, scratch, restartable staging, reject, or published output.
2. Identify the component that creates the file and the component that owns closing/deleting it.
3. Choose a dedicated work root and namespace by JobInstance/operation.
4. Use stable names for restartable files; use unique names for scratch.
5. Persist path/checksum/manifest if needed for recovery or reconciliation.
6. Use Resource/ItemStream to open, update checkpoints, and close files per lifecycle.
7. Write output to staging, close, and validate before publishing.
8. Publish via atomic move when the filesystem supports it; make the publish Step idempotent.
9. Delete scratch only when certain no subsequent Step or restart needs it.
10. Keep input/staging when the Job is `FAILED` or `STOPPED` if restart requires them.
11. Use Cleanup Step/listener for normal Job completion and a sweeper for process crashes.
12. Verify paths reside under the allowed root and do not delete symlinks/resources outside scope.
13. Apply retention by resource type and execution status.
14. Record audits, metrics, and handle retryable cleanup errors.
15. Test success, failure, stop, restart, process kill, concurrent Jobs, and repeated cleanup.

| Need | Suitable Mechanism |
|---|---|
| File used in a single operation | `Files.createTempFile` and `try/finally`. |
| Reader/writer holding file handles | `ItemStream.open/close`. |
| File needing to resume after restart | Stable path by JobInstance and checkpoint/manifest. |
| Output published only when complete | Staging file, validate, then atomic move if supported. |
| Deleting scratch after Job success | Cleanup Step or conditional `JobExecutionListener`. |
| Cleaning up files after process crash | Retention sweeper cross-checking JobRepository and owner metadata. |
| Multiple Jobs sharing a work root | Separate directories, ownership/lease, and path validation. |

## Conclusion

Temporary file management in Spring Batch must align with resource lifecycles, transactions, and restartability. Classify scratch files, restartable input/staging, and published artifacts; use dedicated directories with stable JobInstance-based names for recoverable files; let `ItemStream` close handles properly; write output to staging, validate, and publish; clean up only when certain no Step or restart still needs the resource. `close`, `finally`, and `afterJob` do not run when a process is killed, so production needs a retention sweeper that cross-checks JobRepository, manifests, and owners before deleting orphan files. Cleanup must be idempotent, confined to the allowed work root, and backed by audits/metrics to avoid accidental deletion or data accumulation.
