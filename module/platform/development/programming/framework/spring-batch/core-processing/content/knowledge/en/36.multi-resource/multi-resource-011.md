# Managing old output

In Spring Batch, a Step can emit multiple output files using `MultiResourceItemWriter`. For example, each file contains at most 100,000 records, and the writer rotates to the next file once the limit is reached. Across runs, the number of generated files can vary.

Problems arise when an output directory is reused. A previous run might have produced 12 files, whereas a new run produces only 4 files. If old files from the earlier run remain behind, downstream systems may mistakenly read files that do not belong to the new result. Some files might also be partial output from a failed Job or files retained for a restart.

Managing old output requires answering three questions:

- Which `JobInstance` or batch owns a file?
- When is deleting old files allowed?
- How does a consumer recognize that a file set is complete?

The key principle is distinguishing **a fresh run**, **restarting the same `JobInstance`**, and **retention cleanup**. A fresh run may need a clean output set; a restart needs to preserve already-committed files and checkpoints; retention cleanup deletes only expired data no longer needed by any active Job.

## 1. Why does old output cause errors?

Suppose `MultiResourceItemWriter` creates files with a limit of 3 records per file.

The first run has 10 records:

~~~text
orders-000.csv  -> records 1-3
orders-001.csv  -> records 4-6
orders-002.csv  -> records 7-9
orders-003.csv  -> record 10
~~~

The next run has only 5 records:

~~~text
orders-000.csv  -> new output
orders-001.csv  -> new output
~~~

If the writer overwrites only the files it needs without cleaning up the remaining files, the directory still holds:

~~~text
orders-000.csv  -> new output
orders-001.csv  -> new output
orders-002.csv  -> old output
orders-003.csv  -> old output
~~~

A consumer scanning all files matching `orders-*.csv` will read the stale data too. Old files are syntactically valid, so errors may not surface immediately; outcomes can suffer duplicate records, incorrect totals, or reprocessing of an already-completed batch.

Common causes:

- The new run generates fewer files than the prior run.
- Stale files do not appear in the resource set produced by the current writer.
- A Job failed mid-write, leaving behind incomplete files.
- A new Job reuses the exact same output path.
- Two Jobs run concurrently and write to the same prefix.
- A consumer scans the directory while the writer is still creating files.
- Cleanup deletes files too broadly or accidentally deletes files needed by a restarting Job.

`MultiResourceItemWriter` manages splitting items across resources during its own run. Do not treat it as a general retention mechanism responsible for hunting down and deleting leftover suffix files from previous runs.

## 2. Distinguishing three lifecycles

A system must define three situations clearly:

| Scenario | Existing output | Desired behavior |
| --- | --- | --- |
| New `JobInstance` | No output for this batch yet | Create a fresh output set; clean scoped old files if necessary |
| Restart same `JobInstance` | Files and checkpoints exist from prior run | Keep files and resume from checkpoint |
| Retention cleanup | Outputs of old completed or expired batches | Delete or quarantine per retention policy |

Never run an unconditional file-deletion step every time the writer opens. If that step re-runs on restart, it can delete the exact files the writer needs to resume.

### JobInstance and JobExecution

Spring Batch distinguishes `JobInstance` from `JobExecution`:

- `JobInstance` represents a logical run identified by Job name and identifying `JobParameters`.
- `JobExecution` is a concrete execution attempt of that `JobInstance`.
- On restart, Spring Batch creates a new `JobExecution` belonging to the same `JobInstance`.

Therefore, do not base output paths solely on `JobExecution` ID if restarts must resume the same file set. Use a stable batch key tied to `JobInstance`—such as `batchId` or business date plus source code—and keep that key identical on restart.

A new `JobInstance` should have its own batch key if it produces an independent output set. If the business intentionally re-runs the same business batch as a fresh execution, assign a new run key or define an explicit replacement strategy for prior output.

## 3. Using a dedicated directory per batch

A clean way to manage output is isolating it by batch key:

~~~text
batch-output/
  BATCH-2026-11-15-A/
    orders-000.csv
    orders-001.csv
    manifest.json
  BATCH-2026-11-15-B/
    orders-000.csv
    manifest.json
~~~

With this layout:

- Each `JobInstance` writes into its own directory.
- Restarts reuse the exact directory of the active batch key.
- New Jobs create new directories and never overwrite another batch's files.
- Consumers receive a batch key or manifest identifying the file set to read.
- Retention can remove an entire expired batch directory after checking status.

This is generally much simpler than having multiple Jobs write into a single flat directory with overlapping suffixes.

### Choosing a stable batch key

Example Job accepting `JobParameters`:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("batchId", "BATCH-2026-11-15-A")
        .addString("businessDate", "2026-11-15")
        .toJobParameters();
~~~

`batchId` must stay identical when restarting the same `JobInstance`. Never generate a new UUID on every restart if the output path derives from that UUID.

If `batchId` forms a directory name, restrict allowed characters and validate the normalized path. Never construct paths directly from arbitrary unvalidated input strings.

## 4. Configuring MultiResourceItemWriter

`MultiResourceItemWriter` splits output across multiple resources. It requires a base resource, a delegate capable of receiving new resources, a per-resource item limit, and a suffix rule.

Example:

~~~java
@Bean
@StepScope
public MultiResourceItemWriter<Order> multiOrderWriter(
        @Value("#{jobParameters['outputDirectory']}") String outputDirectory,
        FlatFileItemWriter<Order> orderFileDelegate) {

    Resource baseResource = new FileSystemResource(
            Path.of(outputDirectory, "orders").toString());

    return new MultiResourceItemWriterBuilder<Order>()
            .name("multiOrderWriter")
            .resource(baseResource)
            .resourceSuffixCreator(index ->
                    String.format("-%03d.csv", index))
            .itemCountLimitPerResource(100_000)
            .delegate(orderFileDelegate)
            .saveState(true)
            .build();
}
~~~

With base resource `orders`, the suffix creator generates resources such as `orders-000.csv`, `orders-001.csv`, and increments by index. The output directory must exist and the application must have write permissions.

The delegate can be a `FlatFileItemWriter`:

~~~java
@Bean
public FlatFileItemWriter<Order> orderFileDelegate() {
    return new FlatFileItemWriterBuilder<Order>()
            .name("orderFileDelegate")
            .encoding("UTF-8")
            .lineAggregator(order ->
                    order.getOrderId() + ","
                    + order.getCustomerCode() + ","
                    + order.getTotalAmount())
            .saveState(true)
            .build();
}
~~~

`MultiResourceItemWriter` assigns the current resource to the delegate before opening it to write each file. The delegate must implement `ResourceAwareItemWriterItemStream`. Exact builder configuration may vary across Spring Batch versions; use your project version's API and verify the resource is assigned before open.

### Using stable writer names

The names of `MultiResourceItemWriter` and its delegate writer must remain stable across restarts. Spring Batch uses component names and `ExecutionContext` to store state. Renaming a writer or changing suffix generation between the initial run and a restart can prevent state from matching generated resources.

Never share identical writer names across two independent writers in the same Step scope if they save independent state.

## 5. Cleanup before a fresh run

If reusing the same directory is unavoidable, clean old output in a separate Step that runs ahead of the file-writing Step.

Flow:

~~~text
prepareOutputStep
       |
       v
Determine directory for new batch
       |
       v
Delete old files matching batch prefix
       |
       v
processOrdersStep
       |
       v
MultiResourceItemWriter creates new files
       |
       v
finalizeOutputStep
~~~

Separating cleanup into its own Step gives two benefits:

- Cleanup runs strictly before new output creation begins.
- When the processing Step fails and the Job restarts, the already-`COMPLETED` cleanup Step is skipped by default, preserving files and checkpoints from the prior attempt.

Do not configure the cleanup Step to re-run even after completion if it would wipe outputs required for restart. In particular, never place deletion logic inside the writer's `open()` method or delegate constructor.

### Example Tasklet cleaning files by prefix

The following example deletes only CSV files matching the `orders` prefix inside the current batch's directory:

~~~java
@Bean
@StepScope
public Tasklet cleanOldOrderFilesTasklet(
        @Value("#{environment.getProperty('batch.output.root')}") String outputRoot,
        @Value("#{jobParameters['batchId']}") String batchId) {

    return (contribution, chunkContext) -> {
        if (batchId == null || !batchId.matches("[A-Za-z0-9_-]+")) {
            throw new IllegalArgumentException("Invalid batchId");
        }

        Path root = Paths.get(outputRoot)
                .toAbsolutePath()
                .normalize();
        Path batchDirectory = root.resolve(batchId).normalize();

        if (!batchDirectory.startsWith(root)) {
            throw new IllegalArgumentException(
                    "Output directory is outside configured root");
        }

        Files.createDirectories(batchDirectory);

        if (Files.isSymbolicLink(batchDirectory)) {
            throw new IllegalStateException(
                    "Batch output directory must not be a symbolic link");
        }

        try (Stream<Path> paths = Files.list(batchDirectory)) {
            for (Path path : paths.toList()) {
                String name = path.getFileName().toString();
                boolean ownedOutput =
                        name.startsWith("orders-")
                        && name.endsWith(".csv");

                if (ownedOutput
                        && Files.isRegularFile(
                                path, LinkOption.NOFOLLOW_LINKS)) {
                    Files.delete(path);
                }
            }
        }

        return RepeatStatus.FINISHED;
    };
}
~~~

This example requires importing `Path`, `Files`, `LinkOption`, `Stream`, and corresponding Spring Batch types. On Java versions without `Stream.toList()`, use `Collectors.toList()`.

Key safeguards to uphold:

- `outputRoot` comes from trusted application configuration, never arbitrarily from input files.
- `batchId` is validated before constructing directory names.
- Only regular files matching application-owned prefix and extension are deleted.
- Never delete the parent directory or entire output root.
- Never follow symbolic links when inspecting files.
- Never run cleanup concurrently while a writer is creating files in the same batch directory.

If the application creates a brand-new directory for every `batchId` and guarantees `batchId` uniqueness, pre-run file deletion may be unnecessary. Checking whether the directory already exists and failing if unexpected data is present is often safer than auto-deleting.

## 6. Cleanup Step must be restart-safe

Suppose a Job has three Steps:

~~~text
cleanOutputStep
      |
      v
writeMultiResourceStep
      |
      v
publishOutputStep
~~~

Initial run:

1. `cleanOutputStep` removes stale files within batch scope.
2. `writeMultiResourceStep` writes segmented files.
3. Once writing completes, `publishOutputStep` creates a manifest or marks output ready.

If `writeMultiResourceStep` fails after several chunks:

- The `JobInstance` remains restartable.
- `cleanOutputStep` is already `COMPLETED` and does not re-run by default.
- `writeMultiResourceStep` uses saved checkpoints and resources to resume.
- `publishOutputStep` executes only after the write Step finishes.

If the cleanup Step itself fails before the writing Step starts, a restart may re-run cleanup. That remains safe provided cleanup touches only old output of the current batch and no writer has produced new data yet.

Never enable `allowStartIfComplete` on a cleanup Step if doing so would wipe data from a completed run. If custom flows or deciders could re-invoke cleanup, verify `JobInstance` state and allow cleanup only during preparation of a fresh run.

### Do not rely on JobExecution ID for restartable directories

Restarts create a new `JobExecution`. If directories are keyed by `JobExecution` ID, a restart creates a new directory and fails to find existing files to resume.

Use `batchId` or another `JobInstance`-stable key to determine output paths. You can record `JobExecution` ID inside the manifest to trace individual attempts, but never use it as the sole identity of restartable output.

## 7. Deleting old output by suffix or by batch directory?

Two common management approaches exist:

| Approach | Advantages | Risks / caveats |
| --- | --- | --- |
| Delete files by prefix/suffix in shared directory | Easy to fit into existing layouts | Patterns may over-match; concurrent Jobs in one folder conflict |
| Dedicated directory per `batchId` | Isolates output, simplifies restart and retention | Requires managing directories and manifests |

Prefer dedicated directories per batch whenever possible. If a shared directory is required, embed `batchId` in the prefix:

~~~text
orders-BATCH-A-000.csv
orders-BATCH-A-001.csv
orders-BATCH-B-000.csv
orders-BATCH-B-001.csv
~~~

Batch A cleanup must match strictly Batch A's prefix. Never use overly broad patterns like `orders-*.csv` when multiple batches can coexist.

Because suffix indexing may start at 0 or 1 depending on implementation/version, never hardcode index assumptions when deleting files. Use a prefix covering all files owned by the batch and test with your exact `resourceSuffixCreator`.

## 8. Distinguishing overwrite, append, and restart

These three behaviors are distinct:

**Overwrite:** a fresh run creates clean output. Old files with identical names are replaced or deleted per writer configuration.

**Append:** the writer appends to existing files. Use only when the output contract calls for accumulating data.

**Restart:** the same `JobInstance` resumes writing from its saved checkpoint. The writer must preserve files and state properly.

With `MultiResourceItemWriter`, the append policies of both wrapper and delegate must be understood together. If your Spring Batch version supports configuring append on `MultiResourceItemWriter`, set it explicitly, and also inspect the delegate's append behavior (such as `FlatFileItemWriter`). Never rely on defaults when output already exists.

### Why can append be dangerous?

If a new run has fewer records than the prior run and the writer appends into identically named files:

- Earlier files mix old and new records.
- Suffix files not reopened still hold old data.
- Headers may be duplicated.
- Consumers may read records from multiple batches mixed together.
- New checkpoints do not accurately describe content appended by another `JobInstance`.

Append fits only strict accumulation contracts, such as an append-only log file with unique record keys where consumers understand batch boundaries. For batch exports, isolated fresh outputs are far easier to control.

### shouldDeleteIfExists does not replace full cleanup

`FlatFileItemWriter` has policies for handling the current resource on open. Those policies do not automatically search for and delete leftover suffix files that `MultiResourceItemWriter` never opens in the new run.

For example, if the new writer creates only `orders-000.csv` and `orders-001.csv`, configuring deletion on the opened resource does not delete `orders-002.csv` through `orders-010.csv` if those resources are never opened during the current run.

Therefore, clean up old output at the batch directory or prefix level under explicit policies. Never treat `shouldDeleteIfExists` as a retention mechanism.

## 9. Never delete files on restart

On restart, Spring Batch requires:

- The same `JobInstance` and identifying `JobParameters` as the prior run.
- Stable reader/writer names.
- Stable resource paths.
- Stable resource suffix creator.
- Inputs and item ordering unchanged outside allowed rules.
- Matching checkpoints intact in `ExecutionContext`.
- Files written up to the checkpoint still present.

If outputs are deleted before restarting, the writer may restore the old offset and append into a new empty file. The result can miss the beginning, misalign positions, or fail when opening resources.

If files were lost or altered outside the Job, never fabricate empty files and force the old checkpoint to continue. Detect the mismatch and fail clearly, then pick a recovery strategy: restore files from backup, re-run the `JobInstance` from scratch under approved procedures, or create a new `JobInstance` with a new batch key.

Never edit `ExecutionContext` directly in `JobRepository` to force the writer past file errors without reconciling committed data first.

## 10. Handling partial output from a failed Job

A failed Job can leave behind:

- Files with several committed chunks.
- A current file containing only partial records.
- Files created without a footer.
- No manifest yet.
- A manifest in `PREPARING` or `INCOMPLETE` state.

Never treat any existing file as valid for consumer ingestion. Use an explicit publish lifecycle:

~~~text
PREPARING
    |
    v
WRITING
    |
    v
VALIDATING
    |
    v
PUBLISHED
~~~

Consumers read output only when status is `PUBLISHED`. If the Job fails, files can stay in the batch directory for restart or move to quarantine per retention policy.

Do not generate a completed manifest as soon as the writer opens a file. Mark the manifest complete only after all file-writing Steps succeed and output validations pass.

### Should FAILED Job files be deleted?

Not necessarily. Depending on operational requirements:

- Keep them for restarting the same `JobInstance`.
- Keep them briefly for root-cause investigation.
- Move them to quarantine if the `JobInstance` is abandoned and will not restart.
- Delete them once retention expires and no Job is running.

While a Job remains restartable, partial files and checkpoints form a coupled pair that must be preserved together. Deleting files while retaining restart metadata creates inconsistent state.

## 11. Manifests describing output sets

With multi-file outputs, consumers should not guess which files belong to a batch by scanning an entire directory. Generate a manifest after the writer finishes:

~~~json
{
  "batchId": "BATCH-2026-11-15-A",
  "status": "PUBLISHED",
  "files": [
    {
      "name": "orders-000.csv",
      "recordCount": 100000,
      "sizeBytes": 8240000,
      "checksum": "..."
    },
    {
      "name": "orders-001.csv",
      "recordCount": 27500,
      "sizeBytes": 2260000,
      "checksum": "..."
    }
  ],
  "totalRecords": 127500
}
~~~

A manifest can include:

- `batchId` or business key.
- Status: `PREPARING`, `WRITING`, `VALIDATING`, `PUBLISHED`, or `FAILED`.
- List of files belonging to the batch.
- Per-file record counts and total record count.
- File sizes and checksums.
- Encoding, delimiter, and schema version.
- Creation and publish timestamps.
- `JobExecution` ID for traceability, if needed.

Consumers read only files listed in a `PUBLISHED` manifest. Stale files omitted from the manifest are never accidentally ingested.

### Writing the manifest in a dedicated step

A finalize Step can:

1. List files in the current batch directory.
2. Verify files are regular files matching the expected prefix.
3. Count records or collect persisted counters.
4. Compute checksums if required.
5. Write the manifest to a temporary file.
6. Rename the temporary manifest to the official manifest name once writing finishes.
7. Update batch status to `PUBLISHED`.

Never let consumers read a manifest while it is still being written. Temporary naming and publish operations must match the semantics of your filesystem or object storage.

## 12. Atomic publishing with a staging directory

A common pattern writes output into a staging directory and publishes the entire file set upon completion:

~~~text
output/
  staging/
    BATCH-A/
      orders-000.csv
      orders-001.csv
      manifest.json
  published/
    BATCH-A/
      orders-000.csv
      orders-001.csv
      manifest.json
~~~

Flow:

1. The writer writes exclusively inside `staging/BATCH-A`.
2. The Job finishes and validation passes.
3. The finalize Step generates the manifest.
4. The publish Step moves the batch directory to `published`.
5. Consumers scan only `published`.

When directory renames on the same filesystem are atomic, consumers see the complete output set at a single point in time. Atomicity depends on filesystem, mounts, volumes, and source/target paths; never assume cross-filesystem renames are atomic.

On object storage, renames are rarely truly atomic; copy objects, verify them, and then publish a `PUBLISHED` marker or manifest.

## 13. Retention cleanup for old batches

Retention cleanup is a periodic job that removes expired outputs. It differs from pre-run cleanup ahead of a new `JobInstance`.

A retention policy may specify:

- `PUBLISHED` batches retained for 30 days.
- `FAILED` batches retained for 7 days for investigation.
- `STARTED` batches or batches with active `JobExecution` runs never deleted.
- Batches awaiting consumer acknowledgement never deleted.
- Batches with reconciliation discrepancies held until resolved.

Example metadata table:

| batch_id | status | completed_at | retention_until |
| --- | --- | --- | --- |
| BATCH-A | PUBLISHED | 2026-10-01 | 2026-10-31 |
| BATCH-B | FAILED | 2026-11-10 | 2026-11-17 |
| BATCH-C | WRITING | null | null |

Retention jobs should verify status and expiration in metadata before deleting. Never delete every directory older than N days blindly when Jobs might still be restarting or consumers have not finished ingesting.

### Safe cleanup sequence

1. Select batches past retention that are no longer active.
2. Mark the batch `DELETING` using controlled updates.
3. Confirm no `JobExecution` is running or restarting.
4. Verify consumer acknowledgement if required.
5. Delete the exact batch directory or move to trash/quarantine.
6. Confirm deletion succeeded.
7. Update metadata to `DELETED`.

If deletion fails midway, subsequent retention runs must resume idempotently. Never purge metadata before confirming files were disposed of per policy.

## 14. Never delete output of a running Job

Two Jobs can run concurrently. If cleanup scans a shared directory and deletes by an overly broad prefix, it can delete resources another Job is actively writing.

Safeguards:

- Give each `JobInstance` a distinct `batchId`.
- Never reuse output directories across active batches.
- Consult `JobRepository` or a batch control table to check active status.
- Use leases or locks when multiple processes manage the same directory.
- Restrict cleanup to finished batches past a safety grace window.
- Never infer from file timestamps alone that a Job is no longer running.

A file's modification timestamp might not update while a writer buffers data, or a process might pause briefly. Job status and explicit locks are far more reliable than inspecting file timestamps.

## 15. Managing output when multiple partitions write files

In a partitioned Step, each worker can generate one or more files. Prevent partitions from creating colliding resource names:

~~~text
staging/BATCH-A/
  partition-000/
    orders-000.csv
    orders-001.csv
  partition-001/
    orders-000.csv
  partition-002/
    orders-000.csv
~~~

Alternatively, suffixes can embed partition IDs:

~~~text
orders-part-000-000.csv
orders-part-000-001.csv
orders-part-001-000.csv
orders-part-002-000.csv
~~~

Each worker requires its own resource path and writer state. Never let multiple independent `MultiResourceItemWriter` instances share the same base resource and identical suffix sequences.

After all partitions finish, a finalize Step can:

- Confirm every partition reached `COMPLETED`.
- Collect the file lists from every partition.
- Verify total record counts and file counts.
- Write a unified manifest.
- Publish the output.

If one partition fails, do not publish the shared file set. Retain partition outputs and checkpoints for restart; clean up only after the batch is cancelled or retention expires.

## 16. Cleaning up files when resource count shrinks

This is the classic cause of stale output:

~~~text
Run A: produces 8 files
  output-000 ... output-007

Run B: produces only 3 files
  output-000 ... output-002

Leftover files:
  output-003 ... output-007
~~~

If two independent runs must reuse the same prefix:

- Delete all files matching that exact prefix before the new run starts.
- Perform cleanup in a preparation Step, never inside writer open.
- Verify the new run is not a restart of an existing `JobInstance`.
- Never allow two Jobs to use that prefix concurrently.
- Publish only after all new files are verified.

A cleaner alternative is using a unique prefix or directory per batch key, eliminating the need to scrub prior suffixes right before writing.

## 17. Old output and resource suffix misconfiguration

`ResourceSuffixCreator` determines generated filenames. If suffixes are non-unique or unstable, files can overwrite or restarts can target the wrong resource.

Unsafe example:

~~~java
.resourceSuffixCreator(index ->
        "-" + System.currentTimeMillis() + ".csv")
~~~

Each invocation can yield a different name, preventing restarts from locating prior resources.

Stable example:

~~~java
.resourceSuffixCreator(index ->
        String.format("-%03d.csv", index))
~~~

With partitions:

~~~java
String partitionId = "part-001";

.resourceSuffixCreator(index ->
        "-" + partitionId + "-" + String.format("%03d", index) + ".csv")
~~~

`partitionId` must remain stable for that partition across restarts. Never base suffixes on random values or current wall-clock time when resources must be recoverable.

Changing `itemCountLimitPerResource`, input order, or the suffix creator between an initial run and a restart alters file counts and boundaries. Keep these parameters constant within a `JobInstance`.

## 18. Append and multiple files

Appending with `MultiResourceItemWriter` must be considered at two levels:

- The wrapper governs resource sequencing and current resource tracking.
- The delegate governs how each file is opened, appended to, or truncated.

If an application wants to resume the same file across restarts, use the writer's `saveState`/checkpoint mechanism. Do not enable append merely as a hack for restarts when the framework already provides state management.

If an application genuinely needs to append outputs from multiple independent batches into the same files, determine:

- Which files receive appends.
- Record counts and batch boundaries.
- Whether headers are rewritten.
- How each `JobInstance`'s checkpoints are managed.
- Whether two Jobs can append concurrently.
- How consumers distinguish records from different batches.

Concurrent appending by multiple Jobs is rarely safe without explicit locking or serialization. For batch exports, separating files by batch and merging in a dedicated step is much easier to control.

## 19. Verifying output before publishing

After the writer finishes, do not check only the file count. Validate contents:

- All generated files live inside the active batch directory.
- Filenames match the expected prefix and suffix.
- No unexpected empty files exist.
- Total record count equals expected written items, accounting for filtering and skipping.
- Headers/footers match the format contract.
- Encoding and line separators match the contract.
- No files from other batches are present.
- Checksums or hashes match if required.
- The final file parses cleanly with the consumer's parser.

File statistics can be stored in `ExecutionContext` or a batch metadata table. Ensure statistics update aligned with chunk transactions and recover cleanly across restarts.

Never rely on file count or total size alone as proof of correctness. A file can have the expected size while holding duplicate or missing records.

## 20. Managing output files with temporary names

Another strategy writes each file to a temporary name and renames upon completion:

~~~text
orders-000.csv.part
orders-001.csv.part
orders-002.csv.part
~~~

After the writer closes files and validation passes:

~~~text
orders-000.csv
orders-001.csv
orders-002.csv
~~~

Consumers read only files with official extensions or listed in a `PUBLISHED` manifest. `.part` files signify incomplete output.

With `MultiResourceItemWriter`, temporary extensions can be applied via base resource/suffix configuration or a post-close publish step. Keep the mapping from temporary names to official names deterministic across restarts.

Never rename a resource while the writer still has it open. Publish only after the Step closes the writer and verifies all resources are complete.

## 21. Handling old files in multi-node environments

When a Job can run across multiple application instances, one node's local filesystem may not be visible to another node. A cleanup tasklet running on node A cannot delete files on node B if nodes use isolated local disks.

Identify your storage topology:

- Shared filesystem.
- Shared persistent volume.
- Object storage.
- Node-local disks.

On shared filesystems, use locking/ownership so cleanup never collides with running Jobs. On object storage, prefix by `batchId` and use manifests/markers; delete objects by explicit key lists. On node-local disks, route workers and restarts back to the same storage or adopt shared durable storage.

Never assume identical path strings on two different nodes refer to the same physical resource.

## 22. Common pitfalls

### Not cleaning old suffixes when a new run produces fewer files

Consumers read both new and stale files. Isolate per batch directory or clean the exact prefix before a fresh run.

### Deleting files every time the writer opens

Restarts lose already-committed output. Place cleanup in a preparation Step that executes only for fresh runs.

### Using JobExecution ID as output identity

Restarts mint new `JobExecution` IDs and could point to a different directory. Use a `JobInstance`-stable batch key.

### Sharing a prefix across multiple Jobs

Jobs can overwrite or clean up each other's files. Isolate outputs by `batchId`/`partitionId`.

### Relying on shouldDeleteIfExists to clean all old files

Delegate policies affect only resources actually opened, leaving unused higher-index suffix files behind. Clean batch outputs at the directory or prefix level.

### Uncontrolled appending

This can duplicate headers, mix distinct batches, and duplicate records. Append only when explicitly defined by contract.

### Publishing before the writer closes

Consumers may read files still being written. Wait for Step completion, validate output, then publish.

### Deleting FAILED outputs before deciding on restart

Checkpoints still reference the deleted files. Preserve files for restart or transition to a non-restartable state before cleanup.

### Using overly broad globs

Cleanup can delete files outside the batch. Match strictly within application-owned directories and prefixes.

### Basing retention solely on file modification times

Files of an active Job may go unmodified for long intervals. Check Job status and batch metadata.

### Two partitions sharing resource suffixes

Writers overwrite each other's files. Embed partition identity in output paths or prefixes.

### Changing suffix creator or page/chunk settings on restart

Resource sequences and checkpoints fall out of alignment. Keep configuration stable within a `JobInstance`.

## 23. Testing old output management

Test using temporary directories so real files are never affected:

~~~java
@TempDir
Path outputRoot;
~~~

### Testing prefix-scoped cleanup

Setup:

~~~text
batch-A/
  orders-000.csv
  orders-001.csv
  customers-000.csv
  notes.txt
~~~

After cleanup for `orders`:

~~~text
batch-A/
  customers-000.csv
  notes.txt
~~~

Tests must verify files outside the prefix remain untouched. If the directory contains subdirectories or symbolic links, verify cleanup does not recurse unexpectedly.

### Testing shrinking file counts across fresh runs

1. Seed 8 mock files from a previous run.
2. Run cleanup for the new batch on the exact output scope.
3. Generate 3 new files.
4. List outputs and verify only the 3 files belonging to the current batch exist.

### Testing that restarts skip cleanup

1. Run the cleanup Step and verify it reaches `COMPLETED`.
2. Write several output files and save checkpoints.
3. Fail the file-writing Step.
4. Restart the same `JobInstance`.
5. Verify the cleanup Step does not re-run.
6. Verify the writer resumes from checkpoint without losing committed files.

This is an integration test requiring `JobRepository` and Spring Batch infrastructure. Unit testing the cleanup tasklet alone does not prove restart flows skip completed Steps.

### Testing isolation across batches

Create two directories `batch-A` and `batch-B`, run cleanup for `batch-A`, and verify all files in `batch-B` remain intact.

### Testing publish and manifest

Verify the manifest is marked `PUBLISHED` only when:

- Every output file is closed.
- Record counts and checksums are valid.
- All partitions have completed.
- Zero temporary files or partial write states remain.

### Testing failures during cleanup

If a file cannot be deleted due to permissions or an open lock from another process, the cleanup Step must fail clearly. Never proceed to write into a directory still holding stale output if that would cause consumers to read bad data.

## 24. Design checklist for managing old output

When building a multi-resource pipeline, clarify:

1. Which directory or prefix holds a `JobInstance`'s file set?
2. Is the batch key stable across restarts and distinct across independent runs?
3. Does `ResourceSuffixCreator` produce deterministic, unique names?
4. Can the file count shrink between two runs?
5. Is old output cleaned before fresh runs or isolated in dedicated directories?
6. Does the cleanup Step stay skipped on restart?
7. Should `FAILED` Job outputs be retained for restart or quarantined?
8. How are append, overwrite, and restart distinguished?
9. Which manifest or publish status tells consumers a file set is complete?
10. How does the retention job verify Job status, batch state, and consumer acknowledgement?
11. Can multiple Jobs, partitions, or nodes write or delete the same prefix?
12. Is cleanup strictly confined to application-owned directories and patterns?
13. Does validation check record counts, checksums, encoding, and schema?
14. Do integration tests cover shrinking file counts, restarts, and cross-batch cleanup isolation?

Prefer dedicated output directories per batch key, preserve them across restarts, generate manifests after completion, and run retention cleanup independently. If a directory must be reused, clean only the exact prefix in a preparation Step for new `JobInstance` runs and prevent other Jobs from sharing that prefix.

## Conclusion

Managing old output in Spring Batch means managing the lifecycle of the entire file set created by `MultiResourceItemWriter`. The writer splits items across new resources, yet it should not be treated as a cleanup tool for leftover suffixes from prior runs. Use dedicated directories or prefixes keyed by a `JobInstance`-stable `batchId`; if directories are reused, perform scoped cleanup in a preparation Step that runs only for fresh `JobInstance` executions. Preserve files and checkpoints on restarts, distinguish append from overwrite, and never delete outputs of running or restartable Jobs. Once all writers and partitions finish, verify record counts/checksums, write a manifest, and publish the file set; let retention cleanup handle expired batches based on status and retention policies.
