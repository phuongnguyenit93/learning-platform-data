# New files arriving while a job is running

In Spring Batch, a Job typically reads a set of input files discovered in a directory or passed via `JobParameters`. A common operational scenario is **new files arriving in the directory after the Job has already started**.

You need to distinguish when a file arrives:

- File published before the reader discovers resources: can be included in the current run's file set.
- File arriving after the reader has captured the resource list: the active reader normally does not auto-detect it.
- File still being written by a producer when the Job scans the directory: the Job could see an incomplete file if the ingestion workflow lacks a safe publishing mechanism.

`MultiResourceItemReader` reads a provided list of `Resource` objects. It is not a continuous directory watcher. To handle files arriving while a Job runs, you must design explicit discovery, publishing, claiming, and manifest creation workflows while keeping the input set stable for restarts.

## 1. How does MultiResourceItemReader read multiple files?

`MultiResourceItemReader` is an `ItemReader` that sequentially reads multiple `Resource` items using a delegate reader. The delegate is typically `FlatFileItemReader` or a reader implementing `ResourceAwareItemReaderItemStream`.

Suppose a directory contains three files:

~~~text
/inbox
    orders-001.csv
    orders-002.csv
    orders-003.csv
~~~

Reading flow:

~~~text
MultiResourceItemReader
       |
       +--> orders-001.csv
       |       |
       |       +--> Delegate reader reads records
       |
       +--> orders-002.csv
       |       |
       |       +--> Delegate reader reads records
       |
       +--> orders-003.csv
               |
               +--> Delegate reader reads records
~~~

When one resource finishes, `MultiResourceItemReader` switches the delegate to the next resource. Each record is returned as a Step item; chunk processing proceeds just like with a standard reader.

This composite lets you reuse the same delegate reader across multiple files sharing a format. It does not manage new-file schedules, queues, file locks, or claim workflows.

## 2. When is the Resource list captured?

Applications usually locate files via `ResourcePatternResolver`, `PathMatchingResourcePatternResolver`, or by constructing a `Resource` array directly. The result is a resource list passed into `MultiResourceItemReader`.

For example:

~~~java
Resource[] resources =
        new PathMatchingResourcePatternResolver()
                .getResources("file:/data/batch/inbox/*.csv");
~~~

Calling `getResources` performs the search at the moment of invocation. `MultiResourceItemReader` receives that list to process.

If the reader is created in `StepScope`, `JobParameters` resolution and resource discovery typically occur when the target bean is instantiated during the Step's lifecycle. Files published before the scan can enter the list. Files appearing after the scan are not automatically appended to the running reader.

There is no default mechanism that keeps re-invoking the glob pattern after every chunk. Changing directory contents does not dynamically alter the `Resource[]` held by the reader.

## 3. Example: files arriving before and after the scan

Suppose a Step starts at 09:00 and the reader scans the directory at 09:01:

~~~text
08:55  orders-A.csv is published
09:00  Job starts
09:01  Reader scans *.csv
       Snapshot = [orders-A.csv]
09:05  orders-B.csv is published
09:10  Reader finishes reading orders-A.csv
09:11  Step ends
~~~

In this run:

- `orders-A.csv` was in the snapshot, so it is read.
- `orders-B.csv` appeared after the snapshot, so it is not automatically added.
- The Step completes even though the inbox now contains `orders-B.csv`.

`orders-B.csv` must be handled in a subsequent scan/`JobExecution` or within a purposefully designed polling loop.

If a file arrives right as the system scans, do not rely on timing luck to determine which run owns it. Ingestion needs a clear publish boundary or deterministic manifest.

## 4. Configuring MultiResourceItemReader

Example reader processing CSV files:

~~~java
@Bean
@StepScope
public MultiResourceItemReader<Order> orderReader(
        @Value("#{jobParameters['inputDirectory']}")
        String inputDirectory) throws IOException {

    Path directory = Paths.get(inputDirectory);
    ResourcePatternResolver resolver =
            new PathMatchingResourcePatternResolver();

    Resource[] resources =
            resolver.getResources(
                    directory.toUri().toString() + "*.csv");

    FlatFileItemReader<Order> delegate =
            new FlatFileItemReaderBuilder<Order>()
                    .name("orderFileDelegate")
                    .delimited()
                    .names("id", "customerId", "amount")
                    .targetType(Order.class)
                    .linesToSkip(1)
                    .saveState(true)
                    .build();

    return new MultiResourceItemReaderBuilder<Order>()
            .name("multiOrderReader")
            .resources(resources)
            .delegate(delegate)
            .saveState(true)
            .strict(true)
            .build();
}
~~~

This example illustrates resolving resources when creating the reader. Production configuration must ensure the delegate accepts resources via the `ResourceAwareItemReaderItemStream` contract; `MultiResourceItemReader` assigns each `Resource` to the delegate before reading that file.

Key properties:

- `name`: a stable name for storing state in `ExecutionContext`.
- `resources`: the list of files read during the `StepExecution`.
- `delegate`: the reader that reads each individual resource.
- `saveState`: persists progress to support restart.
- `strict`: governs behavior when the resource list is empty.
- `comparator`: defines resource ordering if needed.

Builder APIs may differ across Spring Batch versions. Use methods matching your project's dependency.

## 5. strict does not mean waiting for new files

When no files are found, `strict` mode determines whether the reader throws an error.

Typically:

- `strict=true`: an empty resource list is an input/configuration error.
- `strict=false`: the reader can finish immediately without reading any items.

`strict=false` does not make the reader wait until a file arrives. Nor does it enable polling or directory watching.

If the Job runs while the inbox is empty and the reader gets an empty list, the Step may finish with 0 items. Files published later still require another discovery pass.

If files are mandatory, `strict=true` combined with input validation catches problems early. If zero files is a valid state, `strict=false` can work, provided you clearly record the resource count and read item count so an empty run is not mistaken for a successful data load.

## 6. Resource order must remain stable

`MultiResourceItemReader` needs a consistent resource order to save and restore position on restart. If the order changes between the initial run and a restart, the current index could point to a different file.

Example lexicographical ordering:

~~~text
orders-1.csv
orders-10.csv
orders-2.csv
~~~

This is not the numeric order many expect.

You can use zero-padded names:

~~~text
orders-0001.csv
orders-0002.csv
orders-0010.csv
~~~

Or configure an explicit comparator:

~~~java
.comparator(Comparator.comparing(
        resource -> resource.getFilename()))
~~~

If business ordering depends on date, sequence, or partition number, define the comparator on that exact field and ensure it is deterministic.

Never rely on arbitrary ordering returned by a filesystem or an unordered collection. The comparator should also handle null filenames or duplicate filenames if resources can originate from multiple directories.

## 7. Why can new files break restarts?

Suppose on the first run the reader receives:

~~~text
[orders-A.csv, orders-C.csv, orders-D.csv]
~~~

The reader finishes A and C, and checkpoints inside D. The Job fails before D completes.

Before restarting, a new file B is added and the list becomes:

~~~text
[orders-A.csv, orders-B.csv, orders-C.csv, orders-D.csv]
~~~

If the reader restores using resource index while the list has changed, the old index can point to a different resource. Depending on the checkpoint and implementation, this can cause duplicate reads, missed records, or resuming on the wrong file.

Restarts must use the exact same resource set and order as the initial run. Never re-scan the inbox and arbitrarily insert new files into the middle of a restarting `JobInstance`.

## 8. Snapshot manifest per JobInstance

A reliable approach is generating an immutable manifest describing the exact files belonging to a run.

Example manifest:

~~~json
{
  "batchId": "orders-20261115-0900",
  "files": [
    {
      "name": "orders-A.csv",
      "size": 1048576,
      "checksum": "sha256:..."
    },
    {
      "name": "orders-C.csv",
      "size": 2097152,
      "checksum": "sha256:..."
    }
  ]
}
~~~

Workflow:

1. Discovery finds files that are ready.
2. Claim files so a single Job owns them.
3. Build a manifest with a fixed order.
4. Persist the manifest ID/path and checksums as Job metadata.
5. The reader processes only resources listed in the manifest.
6. Restarts reload that exact same manifest.

New files arriving after the manifest is locked belong to the next batch. This establishes a clean boundary between runs and prevents resource list mutation across restarts.

Store the manifest in durable storage with versioning or checksums. Never keep a list of filenames only in a transient Java variable, as a process restart loses that state.

## 9. Locking the manifest before processing

You can use a preparation Step for discovery and manifest creation, followed by a processing Step that reads the manifest.

~~~text
Job
 |
 v
Discovery / Claim Step
 |
 +--> find READY files
 +--> claim files
 +--> create immutable manifest
 +--> save manifest ID
 |
 v
Process Files Step
 |
 +--> read manifest
 +--> build Resource[] in exact order
 +--> MultiResourceItemReader
 |
 v
Finalize / Archive Step
~~~

When the Job restarts:

- If the Discovery Step already completed, do not generate a different manifest for the same run.
- The Process Files Step reuses the persisted manifest.
- Only files in the manifest continue to be read.
- Late-arriving files wait for the next batch.

If the Discovery Step fails before the manifest commits, design claim/manifest operations to be retryable without losing or double-claiming files. A database transaction can persist the manifest and file claims atomically.

## 10. Safe file publishing by the producer

A major risk is a producer creating `.csv` files directly inside the inbox. The Job could scan the directory when the producer has written only part of the contents.

Never treat the existence of a filename as proof that a file is complete.

A common pattern:

~~~text
Producer
   |
   v
orders-001.csv.part
   |
   | finish writing, flush, and close
   v
orders-001.csv.tmp
   |
   | atomic rename if filesystem supports it
   v
orders-001.csv
   |
   v
Batch discovery scans *.csv
~~~

The consumer looks only for files ending with `.csv`. The producer writes to a temporary name outside the scanned pattern and renames it to the ready name only after completion.

Atomic rename is usually guaranteed only within the same filesystem and depends on the filesystem/provider. Moving across volumes or object storage may perform copy/delete and not be atomic.

Do not use the `.csv` extension for files still being written if the reader scans `*.csv`.

## 11. Ready markers and manifest markers

Another option is for the producer to write the data file first and then create a marker:

~~~text
orders-001.csv
orders-001.csv.ready
~~~

The consumer processes a file only when its marker exists.

Create the marker only after the file has been closed and verified complete. Creating the marker too early fails to prevent the race condition.

For multiple files belonging to one batch, use a manifest or a batch-level marker:

~~~text
batch-20261115/
    orders-A.csv
    orders-B.csv
    manifest.json
    _READY
~~~

The consumer accepts the batch only after `_READY` is published. The manifest specifies the file set, order, and metadata. This helps when files must be processed as a logical group.

On object storage, ready markers and manifests are usually more reliable than assuming directory renames are atomic.

## 12. Checking file stability before claiming

If the producer does not support atomic publishing or ready markers, a fallback heuristic is checking that the file stops changing over a time window.

Checks may include:

- File size measured at two separated timestamps.
- Last-modified timestamp unchanged.
- File can be opened for reading.
- Header or trailer is valid.
- Computed checksum matches metadata supplied by the producer.

This approach is only a heuristic. A writer can pause briefly and resume after the check window; timestamp resolution can be coarse; a file handle may still be open.

Prefer explicit publishing contracts. If forced to use a stability window, size the interval to producer behavior and still validate file contents before processing.

## 13. Claiming files to prevent two Jobs from processing simultaneously

If two Jobs scan the same inbox, both may see the same file before it is moved. Both could then duplicate processing.

You need an atomic or coordinated claiming mechanism:

- Rename the file from `inbox` to `processing` on the same filesystem.
- Insert a claim record with a unique key in a database.
- Use a lease with an owner ID and expiration.
- Use a queue or manifest service as the distribution source.
- Use storage-native locking if supported with the right semantics.

Example directory layout:

~~~text
inbox/
    orders-A.csv

processing/
    job-123/
        orders-A.csv
~~~

The Job claims the file before building the manifest. Only the Job owning the files in `processing/job-123` is allowed to read them.

Renames are atomic only where supported by the filesystem and usually require source and destination to reside on the same filesystem. Verify actual semantics on network shares or object storage.

## 14. Do not move files after opening if restarts require the old path

The reader may hold an open stream to the file. On some operating systems, a file remains readable after a rename; on others, move operations are blocked by open file handles or share modes.

Even if an open stream keeps reading, restarts typically reopen the resource using its persisted path. If the file was already moved, the old path may no longer exist.

Therefore, claim files before the processing Step starts and keep paths stable throughout the restartable lifetime of the Job. Move files to archive only after processing succeeds and Job status is properly persisted.

If immediate per-file archiving is required, persist the new location and claim state durably, and design the reader/restart flow around the manifest rather than original inbox paths.

## 15. Scheduled discovery instead of a forever-running Job

For typical file batches, the easiest operational model is having each run process a snapshot:

~~~text
09:00  Scheduler launch Job A
09:01  Job A claim files A, B
09:10  Job A completes
09:15  File C arrives
10:00  Scheduler launch Job B
10:01  Job B claim file C
~~~

Each `JobInstance` owns its own manifest. Late-arriving files are picked up in the next run.

Advantages:

- Jobs have clear start and end boundaries.
- Restarts simply restore the run's snapshot.
- Easy to measure file and record counts per batch.
- Easy to reconcile and archive.
- Avoids holding a Step or transaction open for long periods just waiting for files.

Scheduler frequency depends on SLA: every minute, every 15 minutes, hourly, or on a business schedule. Do not repeatedly launch new `JobInstance` runs with identical identifying parameters when processing separate batches; use a distinct batch ID or window ID.

## 16. Polling while a Job is running

If business rules require a single Job to keep picking up new files for a period of time, implement an explicit polling loop.

For example:

~~~text
Start Job
   |
   v
Discover and claim files
   |
   v
Process current manifest
   |
   v
Wait / backoff
   |
   v
Discover new files
   |
   +--> New files? -- Yes --> Process next manifest
   |
   +--> None and window not expired? -- Yes --> Wait
   |
   +--> Window expired? -- Yes --> Finalize
~~~

Each iteration should create its own snapshot/manifest. Never mutate the `Resource[]` of an open `MultiResourceItemReader`.

Required guardrails:

- Maximum Job runtime.
- Polling/backoff interval.
- Maximum polling iterations.
- Termination condition when no files arrive.
- Handling shutdown or restart between iterations.
- Cap on file count and total bytes per iteration.

Never place an infinite `while` loop inside a chunk transaction. Waiting for files must never hold a database transaction open.

## 17. WatchService and filesystem events

Java NIO `WatchService` can receive directory events for file creation, modification, or deletion:

~~~java
WatchService watchService =
        FileSystems.getDefault().newWatchService();

Path inbox = Paths.get("/data/batch/inbox");

inbox.register(
        watchService,
        StandardWatchEventKinds.ENTRY_CREATE,
        StandardWatchEventKinds.ENTRY_MODIFY);
~~~

`WatchService` helps lower file detection latency. However, filesystem events should never be the sole source of truth:

- Events can overflow or be dropped.
- A single file can emit multiple events.
- Events can fire before the producer finishes writing.
- Network filesystems vary in event support.
- Process restarts miss events that occurred while offline.

A resilient design treats events as wake-up signals for discovery, then rescans the inbox/manifest to confirm which files are actually `READY`. On startup, the service must also rescan to recover unclaimed files.

## 18. Do not update Resource[] on a running reader

A tempting shortcut when new files arrive is calling `setResources()` on an active `MultiResourceItemReader` to append files to the end of the list.

This is not a safe default discovery/restart workflow:

- The reader already stores resource index and delegate state.
- Mutating the list can invalidate the existing index.
- The delegate may hold an active stream for the current resource.
- Updates are not automatically coordinated with `ExecutionContext`.
- Multiple threads could observe inconsistent lists.
- Restarts will not know accurately which resource list was processed.

Create a new reader for a new snapshot/manifest in a separate `StepExecution` or iteration. If you truly require a dynamic reader, build an explicit state machine, manifest persistence, and recovery design rather than just mutating `Resource[]`.

## 19. Using a Tasklet for discovery and claiming

A `Tasklet` can handle discovery, file validation, and manifest creation ahead of the processing Step.

Conceptual example:

~~~java
@Bean
public Step discoverFilesStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        FileDiscoveryTasklet tasklet) {

    return new StepBuilder("discoverFilesStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .build();
}
~~~

The Tasklet can:

1. Locate files with ready markers.
2. Validate filename, size, checksum, and schema.
3. Claim the files.
4. Persist the manifest ID in `JobExecutionContext` or a database.
5. Return `FINISHED`.

The downstream processing Step reads the manifest and constructs `MultiResourceItemReader` from the locked list.

If file claiming uses a filesystem rename while metadata lives in a database, those two actions are not automatically in the same transaction. Define a recovery protocol for cases where the rename succeeds and the database transaction rolls back, or the database claim succeeds and the move fails.

A claim table with unique constraints and leases can be easier to reconcile in multi-node environments.

## 20. Storing the manifest in ExecutionContext

`ExecutionContext` is well suited for small metadata needed to recover with `JobExecution`/`StepExecution`. Do not stuff file contents or entire record payloads into the context.

Suitable metadata to store:

- Manifest ID.
- Manifest path or URI.
- Manifest version/checksum.
- Resource count.
- Batch/window ID.
- Sort rule/version.

For example:

~~~java
jobExecution.getExecutionContext()
        .putString("inputManifestId", manifestId);
~~~

In practice, updates to `JobExecutionContext` must go through proper lifecycle/DAO transactions; do not mutate the object outside the lifecycle and assume it persisted.

If a manifest contains tens of thousands of paths, store the manifest in a file, database, or object storage and keep only its ID/URI/checksum in `ExecutionContext`.

## 21. Restarting after some files have been processed

`MultiResourceItemReader` tracks the current resource and delegate state. On restart, it requires the exact same resource list and order to resume accurately.

For example:

~~~text
Manifest M1:
  A.csv
  B.csv
  C.csv

First run:
  A.csv completes
  B.csv partially read
  Job fails

Restart:
  Reuse M1
  Restore reader state at B.csv
  Resume B.csv
  Then read C.csv
~~~

`D` must not be added to `M1` even if `D` arrived in the inbox before the restart. `D` belongs to the next manifest.

If file `A` was archived after finishing, yet restart state still references `A` or the reader might replay from the beginning, verify reader and checkpoint semantics. It is safer to keep all manifest resources in stable locations until the Job completes, or maintain per-file state to restart individual files independently.

## 22. A new file must not alter JobInstance identity

Identifying `JobParameters` determine the `JobInstance`. If a `JobInstance` fails and needs restarting, do not append new files to its manifest and reuse the same `JobInstance` as if it were the same processing unit.

For example:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("batchId", "orders-20261115-0900", true)
        .addString("manifestId", "manifest-001", true)
        .toJobParameters();
~~~

`manifestId` identifies the input set for that run. On restart, pass the same `batchId` and `manifestId`. A new batch requires a new `batchId`/`manifestId` to establish a distinct `JobInstance`.

If `manifestId` is non-identifying yet alters the query or resource set, restarts could resume over different data. Choose identifying status according to data semantics.

## 23. Idempotency when files can be rediscovered

Discovery may see a file again if a Job stops after reading it but before archiving or marking it complete. Duplicate processing must therefore be prevented.

Techniques include:

- Unique constraints on source file ID and record business key.
- A file-processing table tracking `CLAIMED`/`PROCESSING`/`COMPLETED`/`FAILED` states.
- Checksums to detect identical content resent.
- Idempotent upserts on output targets.
- Controlled updates to archive and manifest statuses.
- Unique event IDs if emitting messages.

Do not use filename as a sole unique identifier if producers can reuse names. Combine producer ID, file sequence, checksum, or batch ID according to contract.

If a file is resent with the same name but different content, the system needs an explicit rule: reject, version, or treat as a new batch.

## 24. Handling malformed or incomplete files

An arriving file can be invalid:

- Empty file.
- Invalid header.
- Missing trailer or record count mismatch.
- Wrong encoding.
- Truncated CSV/XML/JSON.
- Checksum mismatch.
- Unsupported schema version.

The discovery Step should validate metadata and `READY` state. Content validation can occur in the processing Step, while distinguishing global file errors from individual record errors.

When a file is invalid:

- Record `FAILED` status with the root cause.
- Move or copy to quarantine if safe.
- Preserve the manifest and checksum for auditing.
- Do not mark `COMPLETED` merely because the reader opened the file.
- Provide a clear remediation and replay procedure.

If a file is still being written by the producer, do not quarantine it just because of an early scan. Use ready markers or a publish protocol to distinguish in-progress writes from genuinely broken files.

## 25. Handling concurrent discovery across multiple Jobs

In a cluster with multiple schedulers or application instances, two Jobs can scan the same inbox nearly simultaneously.

A naive flow like:

~~~text
if file exists:
    process file
~~~

is unsafe because both processes can see the file before either changes its state.

Atomic claiming is required:

- Database: `INSERT` claim with a unique key; only one process succeeds.
- Filesystem: rename the file into a unique processing path if atomic on that filesystem.
- Object storage: conditional write/lease via storage APIs.
- Queue: consumer groups or visibility timeouts.

Claims must carry an owner ID and claim timestamp. If a worker dies, leases can expire and files can be recovered. Before reclaiming, verify the previous `JobExecution` is no longer running to avoid two workers writing concurrently.

## 26. Large files and long processing times

If a very large file is being read, newly arriving files should not disrupt the active reader. Let the Step finish its current snapshot and process new files in the next cycle.

To reduce latency, large files can be sharded upstream by the producer or in a dedicated ingest step:

~~~text
Large source file
       |
       v
Streaming split at record boundaries
       |
       +--> shard-001.csv
       +--> shard-002.csv
       +--> shard-003.csv
       |
       v
Manifest
       |
       v
Parallel partition workers
~~~

Do not split files at arbitrary byte or line counts if records can be multiline or multibyte-encoded. Split strictly at format-aware record boundaries.

Each shard should be large enough to amortize overhead yet small enough that retries or restarts do not reprocess excessive data.

## 27. Object storage and cloud file arrival

With S3-compatible storage, Azure Blob, or GCS, directories may simply be key prefixes. Renames rarely behave like atomic filesystem renames; many services perform copy followed by delete.

Useful patterns:

- Upload objects under temporary keys, then publish a manifest or ready marker.
- Use immutable object keys containing version or batch ID.
- Record checksums and content lengths in the manifest.
- Discover only finalized manifests.
- Use conditional operations/leases for claiming if supported by the storage.
- Never assume list operations and event notifications share local filesystem semantics.

Event notifications can arrive late or duplicated. Use events to trigger discovery, then verify object metadata and manifests before processing.

## 28. Monitoring file arrival and processing lag

For pipelines continuously receiving files, monitor both discovery and processing.

Useful metrics:

| Metric | Meaning |
|---|---|
| `discovered_file_count` | Number of files found in a scan |
| `ready_file_count` | Number of files meeting `READY` criteria |
| `claimed_file_count` | Number of files owned by a Job |
| `processed_file_count` | Number of files processed successfully |
| `failed_file_count` | Number of files quarantined/`FAILED` |
| `pending_file_count` | Number of files waiting to be processed |
| `oldest_pending_age` | Age of the oldest waiting file |
| `discovery_lag` | Time from publish to discovery |
| `processing_duration` | Processing time per file/batch |
| `input_bytes` | Total input volume |
| `record_count` | Number of records read/written |

Logs should capture file ID, manifest ID, `JobExecution` ID, and `StepExecution` ID. Never log full file contents if they contain sensitive data.

Alert when files remain pending too long, claims stall, `FAILED` files spike, or Jobs unexpectedly complete with zero files.

## 29. Testing files arriving while a Job runs

An integration test can control file creation timing:

1. Populate inbox with `A.csv`.
2. Launch Job; discovery creates a manifest containing only `A.csv`.
3. Pause or block the writer at a test synchronization point.
4. Create `B.csv` and publish `READY`.
5. Resume the Job.
6. Verify the current run processes only `A.csv`.
7. Launch a new Job.
8. Verify `B.csv` is processed in the new manifest.

This test proves snapshot semantics. Avoid arbitrary long sleeps; use latches, barriers, or test hooks to coordinate timing.

Also test producers writing `.part` files and renaming after the scan. `.part` files must not be picked up when the pattern selects only `*.csv`.

## 30. Testing restarts with a fixed manifest

Scenario:

~~~text
Initial manifest:
  A.csv
  C.csv

First execution:
  A.csv completes
  C.csv partially read
  Step fails

Before restart:
  B.csv arrives in inbox

Restart:
  Still use manifest [A.csv, C.csv]
  Resume C.csv
  Do not add B.csv automatically

Next Job:
  Discovery claims B.csv
  New manifest contains B.csv
~~~

Checks:

- Manifest ID stays unchanged on restart.
- Resource list and comparator remain identical.
- Checksums of `A` and `C` remain unchanged.
- Reader state restores accurately.
- `B` is not processed inside the old `JobInstance`.
- `B` is processed inside the new `JobInstance`.
- No duplicate records from retries or restarts.

If a restart must replay a file from the beginning, outputs must be idempotent or track per-file state to avoid duplicate writes.

## 31. Common pitfalls

### Assuming MultiResourceItemReader watches directories

The reader uses the `Resource[]` provided to it. Files arriving after the snapshot require a new discovery pass.

### Setting strict=false expecting the reader to wait for files

`strict=false` only allows an empty list per reader behavior; it does not poll.

### Scanning while the producer is still writing

The Job can read incomplete files. Use temporary extensions, atomic publishing, or ready markers.

### Adding new files to an active Resource[]

This can corrupt state and break restarts. Create a new snapshot/manifest for a new processing cycle.

### Rescanning the inbox on restart

The resource set or sort order may change. Reuse the `JobInstance`'s immutable manifest.

### Not setting a deterministic comparator

Filesystem or lexical ordering may violate expectations. Pick a deterministic comparator and test it.

### Two Jobs processing the same file

Discovery is not claiming. Use unique database claims, atomic moves, or leases.

### Archiving files too early

Restarts may fail to reopen the resource. Keep paths stable until the Job lifecycle completes or maintain explicit per-file state.

### Using WatchService as the sole source of truth

Events can be dropped or duplicated. Rescan inbox/manifests after events and on service startup.

### Running infinite polling inside a transaction

Transactions and resources can be held open far too long. Use bounded iterations, each with its own snapshot and backoff.

### Using filename alone as an idempotency key

Producers may reuse filenames. Combine file ID, batch ID, checksum, or version per contract.

### Not verifying READY state

File existence does not guarantee completion. Verify markers, manifests, size/checksums, or publish protocols.

## 32. File arrival design checklist

When a Job must handle files that can arrive during execution, verify:

1. Does the producer publish files via atomic rename, ready markers, or manifests?
2. At what point does the reader scan the directory?
3. Is the `JobInstance`'s `Resource` set locked?
4. Do files arriving after the snapshot belong to the next batch or a new polling cycle?
5. Does discovery claim files to prevent duplicate processing by two Jobs?
6. Is the comparator deterministic and stable across restarts?
7. Does the manifest record the list, order, checksums, and version?
8. Does a Job restart reuse the exact old manifest?
9. Do input paths remain stable throughout the restart window?
10. Are files archived only after processing state is durably persisted?
11. Does `WatchService`/event notification have fallback rescanning?
12. Is polling bounded in duration and never holding transactions open while waiting?
13. Is idempotency enforced if files are rediscovered or resent?
14. Does monitoring alert on stale pending files, stuck claims, and failed files?
15. Do integration tests inject new files mid-run and verify they run in the proper execution?

`MultiResourceItemReader` sequentially processes a `Resource` list captured when the reader is configured. New files appearing after that moment are not automatically added to the running Step. To process continuously arriving files, implement clear publish/`READY`, discovery, and claim workflows; lock an immutable manifest per `JobInstance`; keep ordering and resources stable across restarts; and handle late-arriving files in the next Job or polling cycle. This avoids reading half-written files, prevents two Jobs from claiming the same file, and preserves meaningful checkpoints when a Job must restart.
