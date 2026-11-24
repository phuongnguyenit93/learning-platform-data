# Missing or renamed resources

In Spring Batch, `MultiResourceItemReader<T>` is commonly used to read a group of files matching a pattern or an explicit resource list. Over a Job's lifecycle, a file may arrive late, be deleted, be moved, or be renamed. Such changes affect resource opening and are especially dangerous when a Job needs to restart from a checkpoint.

A critical detail is that `MultiResourceItemReader` tracks progress by resource position within the sorted list, while the delegate reader tracks progress inside the current resource. If the file list changes between the initial run and a restart, the resource index may point to a different file. Therefore, establish explicit policies for mandatory files, optional files, late arrivals, and renamed files, while keeping the resource set immutable throughout a `JobInstance`.

## 1. Scenarios where resources can be missing or renamed

In a multi-file ingestion batch, common scenarios include:

- The file pattern matches nothing because upstream has not delivered data yet.
- A file listed during Job preparation is deleted before the reader opens it.
- A file is still being written by upstream and is incomplete when the Job starts.
- A file is renamed after a manifest or pattern already resolved resources.
- A file is moved to an archive or processing directory by another process.
- A file is overwritten with new contents while keeping the old name.
- The checkpoint's active file disappears before a Job restart.
- A new file arrives matching the pattern and shifts resource ordering.

These situations are not equivalent. "No files in the batch" might be a valid empty batch or an input failure. "A mandatory file disappeared" is usually a critical error. "A late file" may belong to an orchestration wait condition. "A renamed file" must be distinguished between normal atomic publishing and post-launch input mutation.

## 2. MultiResourceItemReader and the resource list

`MultiResourceItemReader<T>` receives a `Resource` array, sorts it with a comparator, and passes each resource in turn to a delegate reader. The delegate reads the contents of the active resource.

```text
ResourcePatternResolver / Manifest
              |
              v
       Input Resource[]
              |
              v
     MultiResourceItemReader
              |
       +------+------+
       |             |
       v             v
  Resource A     Resource B ...
       |             |
       v             v
  Delegate       Delegate
  FlatFile       FlatFile
  ItemReader     ItemReader
```

Two distinct moments must be separated:

1. **Resolve resources:** the application discovers files via pattern or reads a manifest to construct `Resource[]`.
2. **Open resource:** when the reader advances to a resource, the delegate opens that resource to read its contents.

A resource can exist at resolution time yet vanish before the delegate opens it. Consequently, checking the result of `getResources(...)` alone does not guarantee the file will still exist when read.

## 3. Distinguishing strict on MultiResourceItemReader vs. delegate

`MultiResourceItemReader` and its delegate reader can have separate `strict` settings serving different purposes.

**`MultiResourceItemReader`'s `strict`** controls an empty resource list. When `strict` is enabled, the reader fails if there are zero resources to read. When non-strict, an empty list can be treated as zero items and the reader finishes.

**The delegate's `strict`**, such as on `FlatFileItemReader`, checks whether an individual resource exists when the delegate opens it. If a file was resolved earlier but later deleted, delegate strict mode fails when opening that file.

For example:

```java
@Bean
public FlatFileItemReader<Order> orderFileDelegate() {
    return new FlatFileItemReaderBuilder<Order>()
            .name("orderFileDelegate")
            .delimited()
            .names("orderId", "amount")
            .targetType(Order.class)
            .strict(true)
            .saveState(true)
            .build();
}

@Bean
public MultiResourceItemReader<Order> multiOrderReader(
        Resource[] orderResources,
        FlatFileItemReader<Order> orderFileDelegate,
        Comparator<Resource> resourceComparator) {

    return new MultiResourceItemReaderBuilder<Order>()
            .name("multiOrderReader")
            .resources(orderResources)
            .delegate(orderFileDelegate)
            .comparator(resourceComparator)
            .strict(true)
            .saveState(true)
            .build();
}
```

In this example, the multi-resource reader's `strict` requires at least one resource. `FlatFileItemReader`'s `strict` requires the active file to exist when opened. These two settings do not replace each other.

Builder/setter names may vary across Spring Batch versions. Check the exact API for your application's dependency, while keeping both checks distinct: empty list vs. specific missing file.

## 4. When is an empty resource list valid?

Not every Job requires at least one file. Some batches are allowed to finish when no data exists, such as holidays with zero transactions. Other batches must receive files from upstream and zero files constitutes a contract violation.

| Business rule | Appropriate policy |
|---|---|
| Every run must have at least one file | Enable `strict` on `MultiResourceItemReader` or validate inputs before the Step |
| Zero files may occur on some days | Allow empty lists and record a zero-data outcome |
| Files have not arrived yet but will arrive later | Wait in scheduler/orchestration before launching the Job |
| A mandatory file in the manifest is missing | Fail before processing or fail when opening the delegate |
| A secondary file is optional | Apply an explicit optional policy and log/emit metrics if absent |

Do not set `strict(false)` merely to keep Jobs green. If an empty list is abnormal, ignoring it hides upstream failures and creates the illusion that a batch processed data successfully.

When an empty batch is valid, explicitly record resource count 0, item count 0, and an appropriate business status. You can use a custom `ExitStatus` like `NO_INPUT` if flows or dashboards need to distinguish this case from a run that read a file containing zero records.

## 5. Pattern matches zero files

`ResourcePatternResolver` can return an empty array when a pattern matches no resources:

```java
Resource[] resources = resolver.getResources(
        "file:/var/batch/inbound/orders-*.csv"
);
```

Do not assume `getResources(...)` always throws an exception when no files are found. Inspect the resource count and apply an explicit policy:

```java
if (resources.length == 0) {
    throw new IllegalStateException(
            "No order files found for the requested batch"
    );
}
```

If zero files is valid, you can pass the empty list while explicitly recording zero input. If files arrive late, do not launch the Job expecting `MultiResourceItemReader` to wait for them; the reader is not an input-waiting scheduler.

## 6. File deleted after resolution

A common race condition:

1. The Job resolves a pattern and gets `orders-001.csv` and `orders-002.csv`.
2. Another process moves `orders-002.csv` to archive.
3. `MultiResourceItemReader` finishes reading the first file and moves to the second.
4. The delegate tries to open the old resource, but the file is no longer at that path.

When the delegate is strict, the Step fails on file open. This is the right behavior when the file belongs to a mandatory manifest. Never silently drop a file merely because it disappeared by open time.

To prevent race conditions, enforce file ownership rules. Once a Job claims a batch, upstream must not delete, rename, or overwrite files until the Job completes or the batch is released through a controlled workflow.

## 7. Late-arriving files: wait before launching the Job

If files can arrive late, handle waiting in the scheduler, orchestration service, or an input check step ahead of the data-reading Step.

A typical workflow:

```text
Scheduler receives trigger
        |
        v
Check manifest / ready marker
        |
        +---- Missing files ----> Wait / bounded retry
        |                            |
        |                            +--> Re-check
        |
        +---- All files ready ----> Lock input list
                                     |
                                     v
                               Launch Job
                                     |
                                     v
                          MultiResourceItemReader
```

Never place an infinite wait loop inside `read()` to poll the filesystem continuously. Doing so holds the Step and resources open indefinitely, complicating timeouts, operations, and restarts.

If waiting is necessary, define explicit timeouts, retry counts, retry intervals, logs, and terminal states. When the timeout expires with files still missing, fail or transition the batch to an intervention state per business rules.

## 8. Ready markers and partially written files

A common pattern is having upstream write to a temporary name and rename upon completion:

```text
orders-20261115.csv.part   # currently writing
orders-20261115.csv        # completed
```

The Job matches only `orders-*.csv`, ignoring `*.part`. Renaming within the same filesystem can generally be atomic under filesystem semantics, preventing consumers from seeing partially written target files. Verify actual behavior against your real filesystem or network storage.

Another option is having upstream write a marker:

```text
orders-20261115.csv
orders-20261115.csv.ready
```

The Job picks up only files accompanied by a `.ready` marker, or relies on a manifest marking completed files. Create the marker only after file data is flushed and closed. If markers and files can be published asynchronously, verify sizes/checksums or upstream completion protocols.

Never use a few seconds of unchanged modification time as the sole proof that a file is finished if upstream writers can pause mid-stream. A ready marker or upstream-committed manifest is far clearer.

## 9. Renamed files

Renaming a file changes the resource location configured for the reader. A `Resource` generally holds the path/URL it represents; it cannot automatically track down identical content under a new filename.

For example:

```text
Resolved name: /var/batch/inbound/orders-001.csv
Current name:  /var/batch/inbound/orders-001-final.csv
```

If a file is renamed before the Job opens the resource, the old path no longer exists and the delegate fails. If renamed after the reader opens the stream, behavior depends on filesystem semantics and stream handling; never rely on open handles surviving renames as an operational contract.

When a file is legitimately renamed before Job launch, update the manifest or input configuration so the Job receives the new name. Once the Job has started, never rename files inside the active resource list. If claiming requires renaming, rename before locking the manifest and store the final path/identity used by the Job.

## 10. Files renamed between a run and its restart

This is a far more dangerous case. `MultiResourceItemReader` persists the current resource index and the delegate persists intra-resource checkpoints. It has no way of knowing that `orders-001-old.csv` and `orders-001-new.csv` are the same file just because their contents match.

Example initial run:

```text
index 0 -> orders-A.csv
index 1 -> orders-B.csv
index 2 -> orders-C.csv

Checkpoint: index 1, partway through orders-B.csv
```

Before restart, a file is renamed or the pattern list shifts:

```text
index 0 -> orders-A.csv
index 1 -> orders-C.csv
```

Index 1 now points to file C while the saved delegate state came from file B. The reader can open the wrong file and apply the old checkpoint to different contents, skipping or duplicating records.

Do not attempt to handle renames across restarts merely by keeping the resource count equal. Keep the exact list, order, and identity of every resource unchanged across the `JobInstance`.

## 11. Checkpointing in MultiResourceItemReader

With `saveState(true)`, the multi-resource reader persists progress at the resource-list level, while the delegate persists position within the current resource if it implements `ItemStream`.

```text
Step ExecutionContext
   |
   +--> MultiResourceItemReader state
   |       +--> current resource index
   |
   +--> Delegate reader state
           +--> lines/items read in current resource
```

On restart, the reader expects the exact same sorted resource list. It then restores the index, reopens the delegate on that resource, and the delegate restores its read position inside the file.

This means:

- Adding a new file ahead of the current file shifts the resource index.
- Deleting an already-read file shifts the index of the current file.
- Renaming a file makes the old resource path disappear.
- Modifying contents at the same path causes checkpoints to point to different data.
- Changing the comparator alters resource order.

Checkpoints are reliable only when the resource set, ordering, and source contents remain stable. Reader and delegate names must also stay stable so keys in `ExecutionContext` restore properly.

## 12. Locking the resource list with a manifest

For critical batches, do not re-resolve a broad glob on every restart hoping the list matches the initial run. Instead, generate a manifest for the batch before launching the Job.

Example manifest:

```json
{
  "batchId": "20261115-001",
  "files": [
    {
      "path": "/var/batch/staging/orders-001.csv",
      "sequence": 1,
      "size": 125000,
      "sha256": "..."
    },
    {
      "path": "/var/batch/staging/orders-002.csv",
      "sequence": 2,
      "size": 98000,
      "sha256": "..."
    }
  ]
}
```

The manifest defines:

- Which files belong to the batch.
- Business ordering of the files.
- Final locked paths after claiming/staging.
- Metadata to confirm files were not altered.
- Batch ID used as an identifying `JobParameter` or manifest lookup key.

On restart, the Job reloads the exact manifest by batch ID rather than scanning all files currently in the directory. You can verify sizes/checksums before opening the reader to catch edited or replaced files.

If a manifest is huge, do not stuff the entire manifest payload into `ExecutionContext`. Persist the manifest in durable storage and keep only the batch ID, version, or reference checksum in `JobParameters`/metadata.

## 13. Claiming files and a processing directory

One way to keep upstream from altering files while a Job runs is moving files from `inbound` to a `processing` directory before launch.

```text
inbound/
  orders-001.csv
  orders-002.csv

       | claim batch
       v

processing/batch-20261115-001/
  orders-001.csv
  orders-002.csv
  manifest.json
```

A claim workflow may follow these steps:

1. Confirm files are complete via ready markers or manifests.
2. Select the files belonging to the batch.
3. Move files into a dedicated `processing` directory if supported appropriately by the filesystem.
4. Generate a manifest storing final paths and file metadata.
5. Launch the Job with the batch ID/manifest ID.
6. Retain files in `processing` until the Job completes or recovery finishes.
7. On success, move files to `archive`; on failure, retain them for restart or investigation.

Claiming must prevent two Jobs from grabbing the same file. Use locks/leases, a batch state database table, or atomic filesystem renames. On network shares or object storage, use provider-appropriate claiming mechanisms because rename semantics differ from local filesystems.

## 14. Preflight checks across all resources before reading

Before the Step starts, you can validate the entire resource list to detect missing files early rather than failing on the last file after reading earlier ones.

For example:

```java
public void validateResources(Resource[] resources) {
    if (resources.length == 0) {
        throw new IllegalStateException("No input resources were supplied");
    }

    for (Resource resource : resources) {
        try {
            if (!resource.exists() || !resource.isReadable()) {
                throw new IllegalStateException(
                        "Input resource is missing or unreadable: "
                                + resource.getDescription());
            }
        } catch (IOException ex) {
            throw new IllegalStateException(
                    "Cannot inspect input resource: " + resource.getDescription(), ex);
        }
    }
}
```

Preflight validation can run in a validation service or a `Tasklet` ahead of the file-reading Step. It surfaces input problems immediately with clear diagnostics.

However, `exists()` and `isReadable()` are point-in-time checks. A file can still disappear after preflight. Pair preflight checks with file ownership, a `processing` directory, manifests, and strict delegate settings. This is a time-of-check/time-of-use race condition; checking upfront does not replace keeping sources immutable.

## 15. Never silently skip missing files

A tempting shortcut is setting delegate `strict(false)` so missing files are skipped automatically. This is valid only when business rules explicitly define those files as optional and absences are recorded.

Risks of silent skipping:

- Part of the batch data is lost while the Job still reports completion.
- Reconciliation reports fail to match the manifest.
- Dependent files are left partially processed.
- Restarts produce different results if the file appears later.
- Operations remains unaware that upstream violated the delivery contract.

For optional files, maintain an explicit optional list, log/emit metrics for missing files, and decide whether the Job finishes `COMPLETED`, `COMPLETED_WITH_WARNINGS`, or needs review. For mandatory files, fail loudly so upstream can re-deliver or operations can intervene.

Never use `strict(false)` as a polling fallback for late files. The delegate treats a missing file as having no data and moves straight to the next resource, skipping data that might arrive later.

## 16. Retrying when a resource is temporarily unavailable

Transient errors can happen, such as temporary file locks, brief storage mount drops, or delayed permission propagation. Classify failures carefully:

| Scenario | Handling |
|---|---|
| File late relative to schedule | Wait in scheduler/orchestration before launch |
| File temporarily locked | Bounded retry or wait per storage policy |
| File permanently deleted | Fail and request upstream re-delivery |
| Malformed filename | Fail validation; never retry indefinitely |
| Checksum mismatches manifest | Quarantine batch and investigate |
| Temporary storage outage | Retry per infrastructure error policy with timeout |

Not every `FileNotFoundException` is transient. If a path is wrong or a file was deleted, repeated retries only delay failure. Retries require bounded limits, backoff, and accurate error classification.

For late files, it is usually better not to launch the Job until a manifest or ready marker confirms the batch is complete. If a Job already launched and failed over a missing file, restarting makes sense only after restoring the exact file at the exact locked path with its original contents.

## 17. Optional vs. mandatory files

A manifest can explicitly distinguish required and optional files:

```json
{
  "batchId": "20261115-001",
  "files": [
    { "path": "orders.csv", "required": true },
    { "path": "customer-notes.csv", "required": false }
  ]
}
```

Before constructing `Resource[]`, a validation service can:

- Fail if a `required=true` file is missing.
- Record a warning if a `required=false` file is missing.
- Pass only present and authorized resources to the reader.
- Persist validation results in batch metadata.

Do not rely on a single `MultiResourceItemReader` to encode complex per-file optionality rules when files follow differing contracts. The manifest/preflight layer is the proper place to decide which resources enter the list.

## 18. Files legitimately renamed before the Job starts

If upstream renames files from temporary names to final names before the Job runs, resolve files only after publishing completes.

For example:

```text
orders-20261115.csv.uploading
             |
             | upload complete and file closed
             v
orders-20261115.csv
             |
             | create manifest / ready marker
             v
Job receives official resource
```

The Job must receive the final path in the manifest or `JobParameters`. Never save temporary paths in metadata expecting the reader to hunt down renamed paths. To preserve traceability between temporary and final names, store both `originalName` and `stagedPath` in the manifest for auditing.

## 19. Files renamed after the Job finishes

After the Job finishes, files can move from `processing` to `archive` or be renamed to reflect processed status. Perform this in a dedicated completion/publish step after confirming `JobExecution` succeeded and outputs committed.

Never move a file right when the reader finishes reading the last file but before the Step commits the final chunk. If the writer fails or the transaction rolls back, the Job may need to restart, yet the resource is gone from its old path.

Safer sequence:

1. Data-reading and writing Step finishes.
2. `JobExecution`/`StepExecution` is confirmed successful.
3. Archive step moves files from `processing` to `archive`.
4. Archive status is recorded in the manifest or batch table.

If archiving fails, retry the archive step independently without re-reading business data. Make archiving idempotent: if a file is already in the right archive location, re-running recognizes that state cleanly.

## 20. Old vs. new paths: never guess by similar filename

When an expected file is missing, never scan the directory and substitute a similarly named or newest file. Another file may belong to a completely different batch or hold different data.

Unsafe example:

```java
// Bad: pick the newest file automatically as a replacement for missing input.
File candidate = findNewestFile("orders-*.csv");
```

Instead, rely on batch/file identifiers supplied by upstream:

- Batch ID.
- File ID or sequence.
- Manifest version.
- Checksum or content hash.
- Recorded original path and staged path.

If upstream announces a rename, update the manifest under controlled procedures before launching a new Job. For an already-checkpointed Job, allow a path update only if you can prove the new file carries the exact same content/identity and resource order stays intact; otherwise, create a new batch execution per business rules.

## 21. Impact of the comparator and resource list

Even when no files are deleted, a newly arriving file matching the pattern can alter resource order. For example:

```text
First run:
  0 -> orders-002.csv
  1 -> orders-003.csv

Restart:
  0 -> orders-001.csv  # newly arrived file
  1 -> orders-002.csv
  2 -> orders-003.csv
```

Checkpoint index 1 originally pointed to `orders-003.csv`, but after the list shifted, index 1 now points to `orders-002.csv`. Keep all of the following stable:

- The resource list.
- The comparator and tie-breaker criteria.
- Filenames/paths or resource identifiers.
- File contents.
- Reader and delegate names.

If lists come from a glob, never re-resolve globs against a live inbound directory receiving continuous files on restart. Use a manifest or a batch-isolated staging directory.

## 22. Distinguishing missing resources from empty files

A non-existent file and an existing file with zero records are different conditions:

| Condition | Meaning |
|---|---|
| No resources in list | Pattern/manifest supplied zero files |
| Resource listed but file missing | Input mutated or storage failure |
| File exists at 0 bytes | File present with empty contents |
| Header-only file | Schema present with zero data records |
| File has records, all filtered | Input data existed, zero output items |

Do not lump all cases under "zero items". For a mandatory file, a 0-byte file may be an error. For an optional file, an empty file may be valid. For CSV files with headers, a header-only file may signify zero transactions. Policies must follow the data contract.

Preflight checks can inspect file sizes, headers, and checksums. The delegate reader still must handle EOF and parse errors cleanly during reads.

## 23. Observability and error reporting

When a resource is missing or renamed, logs should provide enough context for operations to see which batch is affected:

- Job name and `JobExecution` ID.
- Batch ID/manifest ID.
- Resource path or resource description.
- File sequence or business date.
- Current resource index if available.
- Expected checksum/size versus actual metadata if checked.
- Stage where the failure occurred: resolve, preflight, open, read, or archive.
- Retry count and final outcome.

Never log sensitive file contents. You can log filenames, file IDs, and checksums for reconciliation without exposing payload records.

Useful metrics include expected resource count, discovered resource count, missing resource count, quarantined file count, open retry counts, and batches waiting for input. These metrics distinguish upstream non-delivery from reader failures.

## 24. Testing missing or renamed resources

Test each stage explicitly rather than checking only whether the Job ended `FAILED`:

1. Pattern matches zero files with `MultiResourceItemReader` strict mode enabled.
2. Pattern matches zero files when the batch allows empty input.
3. Resource resolves successfully but is deleted before the delegate opens it.
4. Delegate strict mode enabled and throws an error when a specific file is missing.
5. Delegate strict mode disabled per optional policy with absences logged clearly.
6. In-progress `.part` files are excluded by the official pattern.
7. Files renamed to final names before manifest locking.
8. File renamed after the Job started and restart behavior tested.
9. New file added ahead of the checkpointed resource index to verify the manifest prevents list mutation.
10. File contents modified at the same path to verify checksum/version checks detect the change.
11. Job fails midway through the second resource, then restarts with the exact same resource list and order.
12. Post-success file archiving can be retried without altering data results.

Restart integration tests must preserve `JobRepository` and `ExecutionContext` across runs. Use fixture files in temporary directories to simulate deletions, renames, and content edits under controlled conditions.

## 25. Common design mistakes

**Assuming MultiResourceItemReader strict checks every file.** The multi-resource reader's `strict` primarily covers an empty list; the delegate's `strict` checks individual resources on open.

**Setting strict=false and treating missing mandatory files as normal.** The Job can finish with missing data. Use non-strict mode only when optional inputs are explicitly defined.

**Waiting for files with an infinite loop inside read().** This holds the Step and resources open. Wait in the scheduler/orchestration layer with bounded timeouts and retries.

**Re-resolving globs against a changing directory on restart.** Lists and resource indexes can drift. Lock a manifest or staging directory.

**Auto-selecting similarly named files when old paths vanish.** This risks reading the wrong batch. Use file IDs, manifests, and checksums.

**Moving files before the Step finishes committing.** Restarts may fail to reopen resources. Archive only after the Job/Step succeeds.

**Checking exists() only once.** Files can still disappear after preflight. Pair checks with ownership and claiming protocols.

**Treating 0-byte files the same as missing files.** The two cases have distinct business meanings; define separate policies.

## 26. How to design handling for missing or renamed resources

Before launching the Job, define which files are mandatory and which are optional. Wait for upstream to finish writing, verify ready markers/manifests, claim files into a `processing` directory, and lock the resource list under a batch ID. Validate paths, existence, read permissions, naming conventions, sizes, and checksums as needed.

When configuring readers, enable `strict` on `MultiResourceItemReader` if an empty list is an error, and enable `strict` on the delegate if every file is mandatory. Allow skipping a resource only when optional policies are explicit and absences are audited. Keep the comparator, reader name, and delegate name stable.

On restart, reload the exact manifest and resource order used on the initial run. Never guess replacement files by similar names, never inject new files into an old `JobInstance`'s list, and never rename or move files still being processed. Once the Job completes, archive files in a separate retryable step.

`MultiResourceItemReader` manages multiple files and their checkpoints, yet it cannot protect itself against external filesystem mutations. Explicit workflows for manifests, claiming, preflight checks, strictness policies, and archiving enable Jobs to distinguish missing inputs, late arrivals, and renamed files—while ensuring restarts resume on the exact right resource and data.
