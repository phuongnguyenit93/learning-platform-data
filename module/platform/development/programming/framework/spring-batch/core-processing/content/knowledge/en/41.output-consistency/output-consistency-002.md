# File output and restart safety

In Spring Batch, chunk-based file writing may succeed initially yet fail midway due to a killed process, lost database connection, full disk, or an invalid item. When the Job is restarted, the writer must resume from the committed checkpoint and produce output without unintended missing or duplicate records.

Restart safety for file output depends on multiple factors simultaneously: the writer must save state, the writer name and output path must stay stable, the file must remain intact between runs, chunk transactions must be understood properly, and publish/cleanup procedures must respect Job status. `FlatFileItemWriter` supports checkpointing via `ItemStream` and `ExecutionContext`, but the filesystem does not automatically join an atomic transaction with `JobRepository`. Therefore, a production design typically writes to a staging file owned by the `JobInstance`, verifies the complete file, and only then publishes it as the official file.

## 1. Why does file output need restart safety?

Suppose a Step reads 1 million orders and writes CSV. Chunk size is 1,000. After writing and committing 300 chunks, the process stops while processing the next chunk.

On restart, the system needs to:

- Resume from the last committed checkpoint.
- Preserve the contents of committed chunks.
- Avoid rewriting lines belonging to committed chunks.
- Rewrite lines of uncommitted chunks if those chunks must be reprocessed.
- Avoid misplaced headers/footers or corrupted file structure.
- Ensure downstream reads the file only after the Job confirms output completeness.

If the writer always truncates the file on every open, restart erases committed output. If the writer always appends manually without restoring the checkpoint, restart can write duplicate data. Restart safety requires synchronizing state in `JobRepository` with the actual state of the file.

## 2. File writers participate in the ItemStream lifecycle

Built-in Spring Batch file writers such as `FlatFileItemWriter` implement `ItemStreamWriter<T>`. This interface combines `write` operations with the `ItemStream` lifecycle:

- `open(ExecutionContext)`: opens the file and restores state if this is a restart.
- `write(Chunk<? extends T>)`: writes the chunk's items.
- `update(ExecutionContext)`: saves writer state to checkpoint with the chunk.
- `close()`: flushes/closes resources when the Step ends.

Conceptual flow:

```text
Step starts
    |
    v
writer.open(ExecutionContext)
    |
    v
Reader -> Processor -> Writer.write(chunk)
    |
    v
writer.update(ExecutionContext)
    |
    v
Chunk transaction commit
    |
    +--> Repeat for next chunk
    |
    v
writer.close()
```

Spring Batch invokes the lifecycle for streams registered with the Step. When using a built-in writer directly in `.writer(...)`, the framework detects the stream per Step configuration rules. If you wrap the writer with a decorator or custom component, the wrapper must implement/delegate `ItemStream` or the delegate must be registered as a Step stream. Otherwise, `open`, `update`, and `close` may not be invoked properly, preventing restart state from being saved.

## 3. Basic FlatFileItemWriter

`FlatFileItemWriter<T>` writes each item as one line via a `LineAggregator<T>`. For CSV, you can use the `.delimited()` builder to map fields:

```java
@Bean
@StepScope
FlatFileItemWriter<OrderExport> orderFileWriter(
        @Value("#{jobParameters['output.file']}") String outputFile) {

    return new FlatFileItemWriterBuilder<OrderExport>()
            .name("orderFileWriter")
            .resource(new FileSystemResource(outputFile))
            .encoding(StandardCharsets.UTF_8.name())
            .lineSeparator("\n")
            .saveState(true)
            .transactional(true)
            .forceSync(true)
            .delimited()
            .delimiter(",")
            .names("orderId", "customerName", "amount", "currency")
            .build();
}
```

Notable configuration options:

- `name`: a stable, unique stream name within the Step; used to namespace state in `ExecutionContext`.
- `resource`: the writer's target file.
- `encoding`: the file's charset; UTF-8 is typically appropriate for multilingual data.
- `lineSeparator`: enforces a consistent newline across runs and environments.
- `saveState(true)`: instructs the writer to persist state for restarts.
- `transactional(true)`: uses chunk-transaction-aware writing as supported by the writer.
- `forceSync(true)`: requests syncing file contents to storage where supported by the OS/provider; may reduce throughput.

The `.delimited()` builder creates a line aggregator from field names. For custom formats, use `.lineAggregator(...)` to control serialization.

## 4. What state does the writer save?

A file writer must know how much output has been checkpointed so that on restart it can open the existing file and continue. `FlatFileItemWriter` manages internal state such as the number of lines written and information needed to distinguish a fresh open from a restart.

Do not depend directly on internal key names in `ExecutionContext`. Specific keys are implementation details based on the writer name and Spring Batch version. Set a stable `.name(...)` and let the writer invoke `update`/`open` to persist/restore state.

Two sources of truth must remain consistent:

| Source | Information |
|---|---|
| JobRepository / `ExecutionContext` | The last checkpoint committed by Spring Batch. |
| File on filesystem | The actual output contents currently on disk. |

If metadata says the writer wrote up to chunk 300 while the file was deleted or replaced with another file, the writer cannot reconstruct lost bytes solely from a line count. Therefore, the file used for restart must be kept intact and protected from unintended cleanup.

## 5. Writer name must be stable

The writer name is not just for logging. `ItemStreamSupport` uses the component name to construct keys in `ExecutionContext`.

Example:

```java
.name("orderFileWriter")
```

The name must be:

- Non-empty when the writer saves state.
- Stable across restarts of the same Step.
- Unique among streams within the same `StepExecution`.
- Never randomly generated from timestamps or `JobExecution` IDs.

If you rename the writer between two runs, the writer may fail to find the old checkpoint and treat the file as a fresh open. When upgrading an application while a restartable Job exists, preserve stream name compatibility or plan to complete/migrate old executions first.

## 6. Output path must be stable across restarts

The file path should represent the output of a `JobInstance` or logical business run, not an individual `JobExecution`.

Example using business date and run key:

```text
/data/staging/orders-2026-11-15-run-42.csv.part
```

`JobParameters` can supply the path:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("business.date", "2026-11-15", true)
        .addString("run.id", "42", true)
        .addString("output.file",
                "/data/staging/orders-2026-11-15-run-42.csv.part", true)
        .toJobParameters();
```

Identifying parameters must remain identical when restarting the same `JobInstance`. If the output path is passed as a non-identifying parameter, ensure the launcher passes the exact original value; even better, tie output identity to an identifying run key and derive/control the path inside the Job.

Do not build the path from the timestamp of each `JobExecution`. A restart is a new execution of the same `JobInstance`; if the path changes with the restart time, the writer may open an empty file while checkpoint metadata belongs to the old file.

## 7. Distinguishing JobInstance, JobExecution, and a new run

Spring Batch distinguishes `JobInstance` from `JobExecution`:

- `JobInstance` represents one logical business run identified by identifying `JobParameters`.
- `JobExecution` is one concrete execution attempt of a `JobInstance`.
- A restart creates a new `JobExecution` while continuing the same `JobInstance` and reusing appropriate state/checkpoints.
- A new business run requires different identifying parameters to create a new `JobInstance`.

Example:

```text
JobInstance: export-orders / businessDate=2026-11-15 / runId=42
    |
    +--> JobExecution 1: FAILED after chunk 300
    |
    +--> JobExecution 2: RESTARTED, continues same staging output file
    |
    +--> JobExecution 2: COMPLETED

New JobInstance: export-orders / businessDate=2026-11-16 / runId=43
    |
    +--> Uses separate output path
```

Do not share the same output path across two independent `JobInstance`s if they can run concurrently or if historical output must be preserved. Separate paths per run key prevent overwrites and file mix-ups.

## 8. Restart and file-opening behavior

When a writer opens for the first time in a new `StepExecution`, it applies its configured policy toward existing files. When restarting the same `StepExecution`/`JobInstance`, the writer uses saved state to recognize this as a continuation and opens the existing file according to the implementation's restart mechanism.

This means:

- Keep the staging output file intact when the Job fails if you intend to restart.
- Keep the writer name and resource path unchanged.
- Do not truncate the file manually before Spring Batch opens the writer on restart.
- Do not manually append content outside the writer between executions.
- Do not edit or remove part of the checkpointed file.

`shouldDeleteIfExists` and `append` are options affecting how existing files are handled on a fresh open. Choose them according to your fresh-run policy; do not use them as a substitute for checkpointing. Built-in writers distinguish restart state using `ExecutionContext`.

## 9. shouldDeleteIfExists and append

These two options are frequently confused with restart:

- `shouldDeleteIfExists(true)`: when starting a fresh write, the writer can delete an existing target file according to builder/implementation semantics.
- `append(true)`: enables appending to an existing file when configured for append mode; suitable for intentional append workflows.

For a staging file dedicated to one `JobInstance`, choose an explicit fresh-run policy and let the writer manage restarts via checkpoints. Do not set `append(true)` merely to achieve restarts; blind appending does not know which chunks committed and can produce duplicates.

Example fresh-output configuration:

```java
new FlatFileItemWriterBuilder<OrderExport>()
        .name("orderFileWriter")
        .resource(stagingResource)
        .shouldDeleteIfExists(true)
        .saveState(true)
        .lineAggregator(orderLineAggregator)
        .build();
```

Use a dedicated path per `JobInstance` and ensure restarts are recognized via saved state. If multiple `JobInstance`s must append into a single shared file, you need a different design with explicit record boundaries, locking, deduplication, and custom recovery; do not reuse standard restartable-file settings for that case.

## 10. saveState and non-restartable writers

`saveState(true)` lets the writer persist checkpoints in `ExecutionContext`. For stateful writers, this is typically required for safe restarts.

If configured with `saveState(false)`:

- The writer does not save progress checkpoints.
- On restart, the writer lacks state to know which contents belonged to committed chunks.
- If the file is kept and appended to, data may be written twice.
- If the file is truncated, previously committed output may be lost.
- Do not expect the Step to automatically recover the exact file position.

`saveState(false)` fits only when the application accepts re-reading/re-writing everything, uses disposable temporary output that can be deleted and recreated, or implements a separate custom checkpoint/idempotency mechanism. If mid-file restart is required, enable state on the writer and test it.

## 11. Chunk transactions and transactional writers

`FlatFileItemWriter` supports transactional buffering. With `transactional(true)`, the writer coordinates file writes with the chunk transaction so data is buffered and finalized via transaction synchronization. When a chunk rolls back before its buffer commits, that chunk's buffered writes can be discarded per writer mechanics.

Example:

```text
Chunk 1: write 1,000 lines -> commit -> output is kept
Chunk 2: write 1,000 lines -> rollback -> chunk 2 buffer is discarded
Restart: resume from checkpoint after chunk 1
```

This is helpful, yet it does not turn the filesystem into an XA-enlisted transactional resource like a database. The writer cannot guarantee a single atomic transaction across both the file and `JobRepository` under all process crashes, filesystem errors, or power losses.

If the writer writes directly (`transactional(false)`), partial chunk contents may already hit the file before the transaction fails. A restart can produce duplicates or output misaligned with the checkpoint. Only disable transactional buffering when you have a clear reason and recovery strategy.

## 12. File and JobRepository do not share one atomic commit

Even when a writer supports transaction-aware buffering, the file and `JobRepository` metadata typically reside on two separate resources. Do not claim "exactly once" solely because the writer has `saveState(true)`.

Several failure windows must be considered:

- The process stops after the file received bytes but before checkpoint metadata committed.
- Checkpoint metadata committed, yet the filesystem failed to persist bytes due to storage/disk cache errors.
- The writer flushes partial data and hits an I/O error.
- The file is cleaned up or replaced after chunks committed.
- The process restarts with a different output path or a file that no longer matches the checkpoint.

Spring Batch provides checkpointing and transaction integration for writers, but ultimate durability also depends on the filesystem, mount options, storage hardware, and publication design. For critical outputs, write to staging, verify integrity, and publish only when the Step succeeds.

## 13. Staging file and final file

A safe pattern separates the file being written from the file downstream is allowed to read:

```text
JobInstance starts
      |
      v
orders-run-42.csv.part
      |
      +--> Writer writes by chunk and checkpoint
      |
      +--> Job fails: keep .part file for restart
      |
      +--> Restart: continue same .part file
      |
      v
File-writing Step COMPLETED
      |
      v
Validate count/schema/checksum
      |
      v
Atomic rename/move
      |
      v
orders-run-42.csv
      |
      v
Downstream permitted to read
```

Downstream watches only the final extension/path or a `READY` status manifest. It never scans `.part` files as completed output.

Staging prevents downstream from reading a file still being populated or left by a failed Job. It also preserves failed files for investigation and restart.

## 14. Publishing with an atomic move

After the file-writing Step succeeds and validation finishes, you can rename the staging file to the final file. If source and target live on the same filesystem, `Files.move` with `ATOMIC_MOVE` can provide an atomic rename depending on filesystem support:

```java
@Bean
@StepScope
Tasklet publishOrdersFileTasklet(
        @Value("#{jobParameters['staging.file']}") String stagingFile,
        @Value("#{jobParameters['final.file']}") String finalFile) {

    return (contribution, chunkContext) -> {
        Path source = Path.of(stagingFile);
        Path target = Path.of(finalFile);

        if (Files.exists(target)) {
            throw new FileAlreadyExistsException(target.toString());
        }

        Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
        return RepeatStatus.FINISHED;
    };
}

@Bean
Step publishOrdersFileStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet publishOrdersFileTasklet) {

    return new StepBuilder("publishOrdersFileStep", jobRepository)
            .tasklet(publishOrdersFileTasklet, transactionManager)
            .build();
}
```

This is an illustrative example; add imports, exception handling, and an appropriate target-exists policy. `ATOMIC_MOVE` may be unsupported on some filesystems/providers or when source and target span different filesystems. If an atomic move is required, fail explicitly when unsupported rather than silently treating copy-delete as equivalent.

The snippet above applies a fail-closed policy when the target already exists; by itself it does not handle the case where a previous move succeeded yet Step metadata had not committed. Production code should add a branch that verifies the target via the run's manifest/checksum and treats publication as complete if the source is gone. Do not ignore target-exists merely based on file presence.

The publish tasklet runs inside a Spring Batch metadata transaction, yet the filesystem operation still does not share an atomic transaction with `JobRepository`. Thus, publication must be idempotent to handle a move succeeding before Step metadata commits.

## 15. The publish step must be idempotent

Suppose the file has already been moved to the final path, but the process stops before the publish Step records `COMPLETED` in `JobRepository`. On restart, the publish tasklet is invoked again. The staging source is gone, while the final target already exists.

A safe publish step must distinguish:

- Target exists and is verified as the exact output of the same run: treat publication as already complete.
- Target exists but belongs to another run or has a different checksum: fail, do not overwrite.
- Source exists and target does not exist: perform the move.
- Neither source nor target exists: fail and require recovery.

You can store the run ID, record count, and checksum in a manifest alongside the file. When restarting publish, the tasklet checks the manifest before deciding the next action. Never assume a target file is valid solely because it exists.

## 16. Validate output before publishing

After the writer Step completes, you can check:

- The file exists and exceeds the expected minimum size.
- The record count equals committed writer items or reconciliation figures.
- The header is correct and appears only once.
- The footer/trailer contains the checksum or total amount if required by format.
- Encoding and line separator match the downstream contract.
- No malformed lines or records missing mandatory fields exist.
- The file parses cleanly using a parser for the target format.
- The file checksum is computed and recorded in the manifest.

Do not check only that the Job is `COMPLETED`; a writer can produce a technically valid empty file if all input was filtered out, whereas business rules may require at least one record. Validation must understand business constraints.

If empty output can be valid, define clearly whether an empty file should be published and how it is represented in the manifest.

## 17. Headers and footers on restart

CSV or fixed-width files often have headers; some formats have summary footers/trailers. Built-in writers manage callbacks according to lifecycle and restart state. Never write headers manually in a processor or on every writer open.

Example:

```java
new FlatFileItemWriterBuilder<OrderExport>()
        .name("orderFileWriter")
        .resource(stagingResource)
        .headerCallback(writer ->
                writer.write("orderId,customerName,amount,currency"))
        .footerCallback(writer ->
                writer.write("# END OF EXPORT"))
        .lineAggregator(orderLineAggregator)
        .saveState(true)
        .build();
```

The header should only be written when creating a new file; a restart must append to existing content without adding a second header. The footer is meaningful only when the writer finishes through a normal successful lifecycle. Verify the exact behavior of your writer/version when a Step fails and restarts; downstream should not rely solely on whether a `.part` file contains a footer as the indicator of completion.

For JSON array formats, opening/closing brackets and commas between records make restart more complex than record-per-line formats. Use a writer supporting restart for that format, or write NDJSON/staging and convert/wrap in a separate publish step.

## 18. Consistent charset, line separator, and serialization

Because restarts append to the same file, serialization rules must stay consistent:

- Keep the same encoding, typically UTF-8.
- Keep the same line separator (`\n` or `\r\n`).
- Keep the same delimiter, quoting/escaping, and null representation.
- Keep locale, timezone, and number/date formatting stable.
- Keep field order and schema version unchanged.
- Never change the line aggregator between the initial run and a restart of the same `JobInstance`.

If you deploy a new version while a Job still needs restarting, changing the serializer can leave the first half of the file in the old schema and the second half in the new schema. Maintain backward compatibility with old executions, or complete/re-initialize the Job under controlled procedures.

Do not rely on the machine's default locale to format monetary amounts or dates in exchange files. Specify format and timezone explicitly.

## 19. Record formatting and newlines

`FlatFileItemWriter` uses a line aggregator to convert objects to text. For CSV, escape delimiters, quotes, newlines, and special characters according to downstream standards. Never concatenate strings naively if fields can contain commas or quotation marks.

Example using `DelimitedLineAggregator`:

```java
DelimitedLineAggregator<OrderExport> aggregator =
        new DelimitedLineAggregator<>();
aggregator.setDelimiter(",");

BeanWrapperFieldExtractor<OrderExport> extractor =
        new BeanWrapperFieldExtractor<>();
extractor.setNames(new String[] {
        "orderId", "customerName", "amount", "currency"
});
aggregator.setFieldExtractor(extractor);
```

If RFC-compliant CSV is required or fields can contain embedded newlines, use an appropriate serializer/library or custom aggregator tested for quoting/escaping. The writer's `lineSeparator` defines the record terminator; it does not replace escaping newlines inside fields.

## 20. MultiResourceItemWriter

For large outputs, you can split output across multiple files by item count using `MultiResourceItemWriter`. This writer coordinates a delegate writer and creates a new resource whenever the per-file item limit is reached.

Conceptual example:

```java
@Bean
@StepScope
MultiResourceItemWriter<OrderExport> multiOrderWriter(
        @Value("#{jobParameters['output.directory']}") String directory,
        LineAggregator<OrderExport> orderLineAggregator) {

    FlatFileItemWriter<OrderExport> delegate =
            new FlatFileItemWriterBuilder<OrderExport>()
                    .name("orderFileDelegate")
                    .encoding(StandardCharsets.UTF_8.name())
                    .lineAggregator(orderLineAggregator)
                    .saveState(true)
                    .build();

    return new MultiResourceItemWriterBuilder<OrderExport>()
            .name("multiOrderWriter")
            .resource(new FileSystemResource(
                    Path.of(directory, "orders").toString()))
            .itemCountLimitPerResource(100_000)
            .resourceSuffixCreator(index ->
                    String.format("-%03d.csv", index))
            .delegate(delegate)
            .saveState(true)
            .build();
}
```

This snippet illustrates the idea; delegate configuration must use the line aggregator/format matching actual output. `MultiResourceItemWriter` tracks the resource index and items in the current resource; the delegate tracks the current file's state. Both wrapper and delegate names must be stable, and `saveState` must be enabled on both when restarts are required.

Suffixes/resource names must be deterministically reproduced on restart. Do not change `itemCountLimitPerResource`, prefix, or suffix creator between executions of the same `JobInstance`. If files were already published/cleaned up before the Job completed, a restart may fail to open the required resource.

## 21. Custom writers must implement ItemStreamWriter if restart is needed

If a writer outputs a custom format or wraps another file library, implementing `ItemWriter<T>` alone is not enough when checkpointing is required. Implement `ItemStreamWriter<T>` and persist needed state in `ExecutionContext`.

Skeleton example:

```java
public class CheckpointedRecordWriter
        implements ItemStreamWriter<ExportRecord> {

    private static final String RECORD_COUNT_KEY =
            "checkpointedRecordWriter.recordCount";

    private final Resource resource;
    private long recordCount;
    private Writer writer;

    public CheckpointedRecordWriter(Resource resource) {
        this.resource = resource;
    }

    @Override
    public void open(ExecutionContext context) throws ItemStreamException {
        recordCount = context.containsKey(RECORD_COUNT_KEY)
                ? context.getLong(RECORD_COUNT_KEY)
                : 0L;
        // Open the resource using a restart-aware strategy.
        // Verify existing file state before appending after a restart.
    }

    @Override
    public void write(Chunk<? extends ExportRecord> chunk) throws Exception {
        for (ExportRecord record : chunk.getItems()) {
            writer.write(serialize(record));
            writer.write("\n");
            recordCount++;
        }
    }

    @Override
    public void update(ExecutionContext context) throws ItemStreamException {
        context.putLong(RECORD_COUNT_KEY, recordCount);
    }

    @Override
    public void close() throws ItemStreamException {
        // Flush and close the owned resource.
    }
}
```

This is an illustrative skeleton, not a production implementation: a real writer must define how byte/record offsets are saved, how chunk buffers roll back, how fresh opens are distinguished from restarts, and how partial writes and transaction synchronization are handled. Saving `recordCount` alone is insufficient if the file might be altered or truncated. Prefer built-in writers whenever the format fits.

When a custom writer is wrapped by a delegate, the outer wrapper must forward `open`, `update`, and `close` and ensure wrapper/delegate state is saved under consistent rules.

## 22. Output paths per JobInstance and avoiding collisions

An output file should have clear ownership. You can construct the path from business date, tenant, export type, and run ID:

```text
/exports/staging/tenant-17/orders-2026-11-15-run-42.csv.part
```

Avoid:

- All Jobs writing to `/exports/orders.csv`.
- Filenames containing only the date when multiple runs can occur on the same day.
- Using `JobExecution` ID in the path if restarts get new execution IDs.
- Using the current timestamp in a bean factory on every writer open.
- Allowing two distinct `JobInstance`s to write to the same resource.

If tenant-scoped output is required, ensure tenant ID is part of the identifying input or output key. If Jobs can run concurrently for the same business date, include a run key/partition ID so paths never collide.

## 23. Restarting after the writer Step has completed

A Job may consist of these Steps:

```text
prepareOutputStep
        |
        v
writeOrdersFileStep
        |
        v
validateOutputStep
        |
        v
publishOutputStep
```

If `writeOrdersFileStep` is already `COMPLETED` while `publishOutputStep` fails, restarting the Job normally resumes from the incomplete Step according to flow/restart rules. Do not re-run the writer just to republish the file if the writer Step finished and the staging output is intact.

If publish already moved the file yet `JobRepository` failed to record Step completion, the publish tasklet must be idempotent as described earlier. If validation fails, preserve the staging file for investigation or clean it up under explicit policy; never publish an invalid file.

## 24. File cleanup when a Job fails or restarts

Do not delete the staging file immediately when a Step fails if the Job is still eligible to restart. The file may hold data from committed chunks and is needed for continuation.

Cleanup policies should distinguish:

- Job is `FAILED` and restartable: preserve staging file and manifest.
- Job is `COMPLETED` and published successfully: archive/clean up staging per retention.
- Job is abandoned or the restart window expired: quarantine/delete per operational procedures.
- File mismatches checkpoint/checksum: preserve for investigation; do not append automatically.
- New `JobInstance`: use a new path to avoid overwriting old files.

Cleanup should run only after confirming terminal status and no active executions. A scheduled cleanup job must not delete a file merely because a `.part` extension has existed for a short time.

## 25. Testing restart for FlatFileItemWriter

An integration test should prove the writer resumes the same file without duplicating or dropping lines.

Scenario:

1. Create input with 5 items and chunk size 2.
2. Run the Job the first time with a staging writer and a test hook that fails the Step after two committed chunks.
3. Verify the staging file contains the exact committed lines.
4. Verify the Step's `ExecutionContext` holds writer state.
5. Restart the same `JobInstance` with identical output path and reader/writer names.
6. Verify the writer resumes from checkpoint without truncating the existing file.
7. Verify the final file contains all 5 records, each appearing once.
8. Verify the header appears once and the footer/trailer is valid.

Do not assert line counts alone; parse the output and compare the set/order of business keys to detect duplicates or missing items.

## 26. Testing mid-chunk rollback

Create a test writer or collaborator that throws an exception while processing a chunk:

- Previously committed chunks must remain in the output.
- The failed chunk must not partially appear when transactional buffering is enabled and the writer conforms to its contract.
- After restart, the failed chunk is reprocessed.
- Final output contains no duplicates.

Test both processor exceptions before the writer and writer I/O errors. The two scenarios can behave differently because one occurs before the writer writes, while the other can occur after partial bytes hit the file.

For real process crashes, use a dedicated test harness or simulate restarts at synchronization points; do not rely solely on writer unit tests to assert that the filesystem and `JobRepository` always commit atomically.

## 27. Testing modified or missing files before restart

Create a checkpoint after several chunks, then deliberately:

- Delete the staging file.
- Truncate the file.
- Replace the file with different content at the same path.
- Change encoding/line separator/serializer.
- Change the output path in `JobParameters`.

The Job must fail explicitly or the recovery procedure must verify and intentionally rebuild the output. Never silently append to a file that does not match the checkpoint.

If using a manifest, test that checksum/size mismatches are detected before resuming the writer. For very large files, use streaming checksums to avoid loading the entire file into memory.

## 28. Testing headers, footers, and empty output

Cases to include:

- File with items: single header, complete records, valid footer.
- Mid-file restart: no extra header inserted.
- Restart after last chunk before publish: output remains valid.
- Zero items: `shouldDeleteIfEmpty`/empty-file policy applied properly.
- Job fails: staging file is not treated as complete by downstream.
- Writer closes: buffers flushed and resources closed.

Footers may be written during the close lifecycle depending on writer/configuration. If the process is killed abruptly, the close callback does not necessarily execute. Therefore, completion markers should be created in the publish step after Job/validation success rather than relying on the footer alone.

## 29. Testing MultiResourceItemWriter

If a Step creates multiple files, also test:

- Item count per resource respects the limit.
- Deterministic suffixes and file ordering.
- Restart between resources does not produce duplicate suffixes or skip files.
- Both wrapper and delegate save state.
- Resource list/prefix/suffix do not change across restarts.
- Headers are written properly in each file per format.
- Downstream sees only fully published files.

On restart, preserve `itemCountLimitPerResource`, resource prefix, suffix creator, and delegate name. Changing them can make old state point to the wrong resource.

## 30. Common mistakes

### Truncating the file on every restart

The writer opens as a fresh run and erases committed output. Keep the same `JobInstance`, output path, writer name, and checkpoint so the writer recognizes restart.

### Using append(true) instead of checkpoints

Appending does not know which chunks committed. Restarts can write duplicates. Use writer state and append manually only under a dedicated custom protocol.

### Disabling saveState

The writer lacks checkpoints to resume. Enable `saveState(true)` for restartable writers.

### Renaming the writer

The `ExecutionContext` key changes and old state is not restored. Keep names stable.

### Changing the output path on restart

The checkpoint belongs to the old file while the writer opens a new file. Use stable identifying run keys/paths.

### Deleting staging files on Job failure

Data from committed chunks is lost. Retain files within the restart window.

### Letting downstream read files still being written

Downstream may read incomplete files. Use staging extensions/paths and publish after validation.

### Assuming file and JobRepository commit atomically

Filesystem and metadata do not share one atomic transaction by default. Use staging, manifests, checksums, and idempotent publication.

### Using a custom ItemWriter without ItemStream

The writer does not save/restore state. Implement `ItemStreamWriter` and manage the full lifecycle.

### Forgetting to register streams when wrapping a delegate

The delegate misses `open/update/close` callbacks. Forward the lifecycle or register the stream with the Step.

### Changing format between runs

The file may contain records in two different schemas/encodings. Keep serializers compatible within the same `JobInstance`.

### Relying on the footer to detect a complete file

Process crashes may skip close callbacks. Only publish/mark READY after validation succeeds.

## 31. Designing restart-safe file output

When building a restartable file-writing Step, follow this sequence:

1. Choose a built-in writer such as `FlatFileItemWriter` when the format fits.
2. Assign a stable, unique writer name within the Step.
3. Enable `saveState(true)` and appropriate transactional buffering.
4. Derive a dedicated output path per `JobInstance` from identifying parameters.
5. Keep path, encoding, line separator, serializer, and schema identical across restarts.
6. Preserve the staging file after failure while the Job remains restartable.
7. Never truncate or append outside the writer on restart.
8. Ensure wrappers/custom writers forward the `ItemStream` lifecycle.
9. Write output to a staging path; downstream never reads files still being written.
10. After the Step succeeds, validate record count, schema, checksum, and trailer.
11. Publish via atomic move on the same filesystem if supported.
12. Make the publish step idempotent so restarting after a move does not overwrite wrong output.
13. Clean up/archive based on Job status and retention, without deleting files needed for restart.
14. Test failure/restart, rollback, file mismatch, headers/footers, and duplicate/missing output.

| Need | Mechanism |
|---|---|
| Resume writing the same file after restart | `ItemStreamWriter`, `saveState(true)`, stable writer name |
| Avoid duplicates on chunk rollback | Writer transaction-aware buffering and chunk rollback testing |
| Isolate output across JobInstances | Dedicated path per identifying run key |
| Prevent downstream from reading partial files | Staging file and post-validation publication |
| Restartable publication | Idempotent move tasklet, manifest/checksum |
| Split into multiple files by threshold | `MultiResourceItemWriter` + stateful delegate stream |
| Custom format | Custom `ItemStreamWriter` with explicit checkpoint/lifecycle |

## Conclusion

Restart-safe file output requires synchronizing checkpoints in `ExecutionContext` with the physical file. Use `FlatFileItemWriter` or an `ItemStream`-capable writer, assign a stable name, enable `saveState(true)`, keep output path and serializer unchanged across restarts of the same `JobInstance`, and protect files holding committed chunks from premature cleanup or modification. Transaction-aware buffering assists with chunk rollbacks, yet does not create a single atomic transaction between the filesystem and `JobRepository`. For important outputs, write to a dedicated staging file, validate record counts/schema/checksum, and publish via an appropriate move operation; the publish step must be idempotent to handle restarts after the file has already been moved. Test restarts, rollbacks, crash windows, altered files, headers/footers, and multi-resource outputs to ensure data is never missing, duplicated, or read by downstream before completion.
