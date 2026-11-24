# Appending or overwriting output

In Spring Batch, `FlatFileItemWriter` writes items as lines in a file. When the target file already exists, the application must define whether the writer should **append** (add to the end of the file), **overwrite** (replace previous contents), or fail to avoid losing data. This choice directly affects repeated job runs, restarts after failures, report generation, and concurrent batch runs.

Append and overwrite are output file policies. They must be designed alongside `JobParameters`, checkpoints, transactions, and step lifecycles. Enabling append alone does not guarantee duplicate-free data; enabling overwrite alone does not guarantee restarts are always safe. Distinguish a fresh run from a restart of the same `JobInstance`.

## 1. What are append and overwrite?

Suppose a writer creates `orders.txt` and writes three lines:

```text
ORD-001,120.00
ORD-002,250.00
ORD-003,80.00
```

If a subsequent run uses **overwrite**, the file's old content is replaced with the new output. For example, a new job processing just two orders produces:

```text
ORD-010,50.00
ORD-011,70.00
```

If a subsequent run uses **append**, new data is written at the end of the existing file:

```text
ORD-001,120.00
ORD-002,250.00
ORD-003,80.00
ORD-010,50.00
ORD-011,70.00
```

The two approaches carry different business meanings:

| Mode | Result when file already has data | Typical use cases |
|---|---|---|
| Overwrite | Deletes/replaces old content and writes the current run's output. | Generating fresh reports, snapshots, or per-run exports. |
| Append | Keeps existing content and adds new lines at the end. | Building file-based logs or accumulating multiple batches into one file by design. |
| Fail if exists | Refuses to write if the target file already exists. | Protecting output files and preventing accidental writes or overwrites. |

`FlatFileItemWriter` supports these policies through append and delete-on-open settings. Choose the mode based on output requirements, not merely on whether a file happens to exist.

## 2. Configuring append and overwrite with FlatFileItemWriterBuilder

Spring Batch provides `FlatFileItemWriterBuilder` to configure the writer. Key options include:

- `append(boolean)`: permits appending to an existing file.
- `shouldDeleteIfExists(boolean)`: decides whether to delete an existing file when opening the writer for a fresh run.
- `shouldDeleteIfEmpty(boolean)`: decides whether to delete the file if the step wrote zero items.
- `saveState(boolean)`: enables/disables persisting writer state in `ExecutionContext` to support restart.
- `transactional(boolean)`: controls how the writer coordinates file writes with transactions.

### Overwriting old files

When every new run should produce a clean output, configure overwrite explicitly:

```java
@Bean
@StepScope
FlatFileItemWriter<Order> orderWriter(
        @Value("#{jobParameters['outputFile']}") String outputFile) {

    return new FlatFileItemWriterBuilder<Order>()
            .name("orderWriter")
            .resource(new FileSystemResource(outputFile))
            .delimited()
            .delimiter(",")
            .names("orderId", "amount")
            .append(false)
            .shouldDeleteIfExists(true)
            .shouldDeleteIfEmpty(false)
            .saveState(true)
            .build();
}
```

With this setup, the writer replaces any old output when opening for a fresh run. `shouldDeleteIfEmpty(false)` keeps an empty file when the step writes zero items; if business rules prefer no file when empty, choose the opposite setting.

Do not point multiple concurrently running jobs at the same fixed path if each job needs its own output. One job can delete the file while another is writing to it.

### Appending to an existing file

If the output is designed as an accumulating file, enable append:

```java
@Bean
@StepScope
FlatFileItemWriter<Order> appendOrderWriter(
        @Value("#{jobParameters['outputFile']}") String outputFile) {

    return new FlatFileItemWriterBuilder<Order>()
            .name("appendOrderWriter")
            .resource(new FileSystemResource(outputFile))
            .delimited()
            .delimiter(",")
            .names("orderId", "amount")
            .append(true)
            .saveState(true)
            .build();
}
```

When the file already exists and this is a fresh open under append policy, new data is appended to the end of the file. The application must ensure appended rows belong to the right batch and are not added twice if the same unit of work is relaunched.

### Failing if the file already exists

If you want neither deletion nor appending on an existing file, configure it not to delete existing files:

```java
return new FlatFileItemWriterBuilder<Order>()
        .name("newOutputOnlyWriter")
        .resource(new FileSystemResource(outputFile))
        .lineAggregator(order -> order.orderId() + "," + order.amount())
        .append(false)
        .shouldDeleteIfExists(false)
        .saveState(true)
        .build();
```

In this mode, if the file already exists and this is not a restart recognized from the writer's state, opening the writer fails rather than silently deleting or appending data. This is useful when each batch must produce a strictly new output file.

## 3. Meaning of shouldDeleteIfExists

`shouldDeleteIfExists` controls how the writer handles an existing target file when starting a fresh write. It is easily confused with append.

| `append` | `shouldDeleteIfExists` | Configuration intent |
|---:|---:|---|
| `false` | `true` | Overwrite: allows deleting the old file and creating a fresh output. |
| `true` | `false` | Append: keeps the old file and appends to it. |
| `false` | `false` | Fail if exists: refuses to open an existing file on a fresh run. |

When `append(true)` is enabled, the writer keeps the old file to append to it. Set these properties explicitly in the builder so anyone reading the configuration understands the output policy.

Do not rely on builder defaults for critical output files. Declare the desired mode explicitly and test both when the file does not exist and when it already exists.

## 4. Appending on a new run vs. resuming on restart

This is the most important distinction when designing batch file outputs.

- **New run:** a user or scheduler launches a new `JobInstance`, targeting either a new output file or an accumulating file. `append` governs how the writer treats an existing file.
- **Restart:** a failed/stopped job is rerun for the same `JobInstance`. The writer must use saved state to resume the previous run's output, avoiding rewriting already-committed data.

`FlatFileItemWriter` is an `ItemStream` and can store state in `ExecutionContext`. With `saveState(true)`, the writer saves the info needed to resume writing. When the step restarts, the writer detects the prior execution's state and handles the file using its restart mechanism.

Therefore, never treat `append(true)` as simply “enabling restart,” nor assume `append(false)` always deletes the file on restart. Append mode for opening an existing file and restarting the same execution are two distinct scenarios. Let the writer restore state from its checkpoint and verify restart behavior on your exact Spring Batch version.

## 5. Role of saveState during restart

`saveState(true)` lets the writer persist needed state into `ExecutionContext`. That state tells the writer how far it wrote when the step restarts.

Example:

```text
Initial run
  chunk 1 -> write 100 lines -> COMMIT
  chunk 2 -> write 100 lines -> COMMIT
  chunk 3 -> error before commit

Restart same JobInstance
  restore saved writer state
  resume from matching checkpoint
  do not re-write committed chunks
```

If `saveState` is disabled, the writer does not persist enough checkpoint data to recover its write position through standard restart mechanics. The application would then have to track exported items itself and resume manually; simply enabling append and restarting can create duplicate lines or inconsistent files.

For restartable jobs, keep `saveState(true)` and use a stable writer name. The writer name helps form keys in `ExecutionContext`; renaming it between the initial run and restart prevents the writer from finding its saved state.

## 6. Why append does not prevent duplicate data automatically

Append merely adds bytes to the end of a file. It has no awareness of whether a line was already written by an earlier batch, nor does it understand business keys.

For instance, running a job twice with the same input produces:

```text
Run 1 append:
ORD-001,120.00
ORD-002,250.00

Run 2 append same input:
ORD-001,120.00
ORD-002,250.00
```

The output will contain two copies of every order unless a deduplication mechanism exists. An append-only file is not synonymous with exactly-once delivery.

Common controls:

- Use a dedicated output file per batch ID or `JobExecution`/`JobInstance` identity.
- Write a batch reference and item key in each row or accompanying metadata.
- Track published batches so the same batch is never appended twice.
- Write to a dedicated staging file and publish once when the job completes.
- Use a data store with unique keys if business-level deduplication is required.
- On restart, rely on the writer's checkpoint instead of re-running all items and appending from scratch.

If the file is an accumulating log, define a deduplication policy or treat duplicate entries as acceptable under the log format.

## 7. Naming outputs using JobParameters

A safe way to avoid multiple runs writing to the same file is parameterizing the output path with business keys. Example:

```text
output/
  orders-2026-11-15.csv
  orders-2026-11-16.csv
  orders-2026-11-17.csv
```

The path can come from `JobParameters`:

```java
@Bean
@StepScope
FlatFileItemWriter<Order> orderWriter(
        @Value("#{jobParameters['outputFile']}") String outputFile) {

    return new FlatFileItemWriterBuilder<Order>()
            .name("orderWriter")
            .resource(new FileSystemResource(outputFile))
            .delimited()
            .delimiter(",")
            .names("orderId", "amount")
            .append(false)
            .shouldDeleteIfExists(true)
            .saveState(true)
            .build();
}
```

With `JobParameters`:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("outputFile", "output/orders-2026-11-15.csv", true)
        .toJobParameters();
```

Whether `outputFile` is marked identifying or non-identifying depends on business rules. If the path identifies a logical output unit, mark it identifying. If it is purely a physical storage location that does not alter batch identity, you may choose non-identifying. Either way, on restart every parameter affecting output must remain unchanged.

## 8. Creating new output safely with temporary files

For important reports or interchange files, consumers must not read a file while the batch is only partially done. A common pattern writes to a temporary file and publishes via move/rename after the step/job completes.

```text
orders-2026-11-15.csv.tmp
          |
          | batch writes and commits chunks
          v
Verify step/job completed
          |
          | move/rename
          v
orders-2026-11-15.csv
```

The writer writes to the `.tmp` path. A subsequent step uses a tasklet to rename the file once all prerequisite steps succeed. Consumers then see the official filename only when the data is complete.

Illustrative tasklet example:

```java
@Bean
@StepScope
Tasklet publishOutputTasklet(
        @Value("#{jobParameters['temporaryFile']}") String temporaryFile,
        @Value("#{jobParameters['finalFile']}") String finalFile) {

    return (contribution, chunkContext) -> {
        Path source = Path.of(temporaryFile);
        Path target = Path.of(finalFile);

        Files.move(source, target,
                StandardCopyOption.REPLACE_EXISTING,
                StandardCopyOption.ATOMIC_MOVE);

        return RepeatStatus.FINISHED;
    };
}
```

`ATOMIC_MOVE` depends on the filesystem and may not work across distinct filesystems/volumes. If unsupported, implement an explicit fallback. Ensure the target directory exists and the replacement policy matches requirements.

Do not treat file publishing outside a transaction as if it could roll back with the database. If the move succeeds yet metadata commit fails, a restart must recognize the already-published file and behave idempotently.

## 9. Headers and footers during append or overwrite

`FlatFileItemWriter` supports `headerCallback` and `footerCallback` for writing leading/trailing lines.

Example:

```java
return new FlatFileItemWriterBuilder<Order>()
        .name("orderWriter")
        .resource(resource)
        .delimited()
        .delimiter(",")
        .names("orderId", "amount")
        .headerCallback(writer -> writer.write("orderId,amount"))
        .footerCallback(writer -> writer.write("END-OF-FILE"))
        .build();
```

When appending, decide whether headers/footers belong to each batch or to the entire file:

- If an accumulating file must have only one header at the very top, do not write a new header on every append.
- If each batch is an independent segment, per-segment headers/footers may be part of the format.
- Aggregate footers (such as total line counts or checksums) may need to be generated after all content is finalized.

Callback behavior depends on how the writer opens the file, whether the file already exists, and whether it is a restart. Verify exact results in your Spring Batch version, especially when combining append, restart, and header/footer callbacks. Never extrapolate append behavior solely from a fresh-file test.

If an accumulating format requires a single leading header and a single final footer, manage them in a dedicated publish step or design explicit segment framing.

## 10. shouldDeleteIfEmpty

`shouldDeleteIfEmpty` determines whether the output file is deleted when a step finishes having written zero items.

```java
.shouldDeleteIfEmpty(true)
```

When enabled, the writer can delete the file if no data was written. This is appropriate when empty files carry no meaning or consumers should not receive empty files.

Conversely:

```java
.shouldDeleteIfEmpty(false)
```

retains empty files, which is useful when the interchange contract always requires a file even with zero records.

Distinguish an empty file from a header-only file. If a header callback writes content, the file may no longer count as empty under the writer's criteria. If the format requires a file with a header and zero records, test that exact case.

## 11. Transactional writing and chunk commits

In a chunk-oriented step, `FlatFileItemWriter` coordinates with transactions by default to avoid exposing uncommitted chunk content as finalized. The writer buffers output while a transaction is open and flushes on commit.

Example:

```text
BEGIN transaction
  read 100 items
  process 100 items
  writer buffer 100 output lines
COMMIT
  flush buffered lines to file
```

If a chunk rolls back, transactionally buffered output is not treated as committed. However, a filesystem is not a standard database transactional resource. I/O failures, process crashes, or special writer settings can still create discrepancies between metadata and the physical file.

`transactional(false)` alters how the writer participates in transactions. Use it only when you accept the trade-offs: output can hit disk even if the database transaction rolls back, leaving uncommitted data in the file.

If a step writes to both a database and a file, no automatic distributed transaction guarantees atomic commits across both in every failure scenario. Design staging, reconciliation, or a publish step to handle out-of-sync states.

## 12. Append and restart of FlatFileItemWriter

A restart is a new `JobExecution` for the same `JobInstance`, not an independent batch run. When the writer implements `ItemStream` and has `saveState(true)`, Spring Batch stores state in `ExecutionContext` so the writer can recover.

Typical scenario:

```text
JobExecution #1
  chunk 1 -> commit, writer state saved
  chunk 2 -> commit, writer state saved
  chunk 3 -> error before commit

JobExecution #2 (restart same JobInstance)
  writer reopens resource and restores state
  reprocess uncommitted portion per checkpoint
  continue writing remainder
```

Do not manually append to a file with a fresh stateless writer assuming restarts will avoid duplicates. Keep the same writer name, keep `saveState(true)`, use the exact same output resource, and keep identifying parameters unchanged. Test reopening the writer on restart against a real `JobRepository`.

If the application changes the output path between the initial run and restart, the writer may write to a new file while the checkpoint still reflects progress in the old one. This is a common cause of missing data or partial outputs. Output paths must remain stable for a given `JobInstance`.

## 13. Overwrite and new JobInstance runs

Launching a job with different identifying parameters creates a new `JobInstance`. If the output path stays fixed and the writer is configured to overwrite, the new run will wipe out the previous run's output.

Example:

```text
JobInstance #1: businessDate=2026-11-15
  outputFile=output/orders.csv

JobInstance #2: businessDate=2026-11-16
  outputFile=output/orders.csv
```

If both runs overwrite the same path, the run for the 16th replaces the file from the 15th. If daily history must be preserved, include the business date or batch reference in the filename.

If the requirement is a multi-day consolidated file, append may fit, provided a tracking mechanism records which batches were already added. Never overload a single path to mean both “daily snapshot” and “accumulated file.”

## 14. Output files in partitioning

In partitioning, multiple workers can run concurrently. If every worker writes to the same file, you risk:

- Interleaved lines or non-deterministic ordering.
- Multiple writers opening/closing the same resource concurrently.
- Duplicated headers/footers.
- Colliding writer checkpoint states.
- Duplicate or lost rows when a single partition restarts.

A safer pattern is giving each partition its own file:

```text
output/batch-20261115/
  part-000.csv
  part-001.csv
  part-002.csv
  part-003.csv
          |
          v
   merge/publish step
          |
          v
   orders-20261115.csv
```

Each worker writes to its own output path derived from the partition name or key. Once all partitions finish, a sequential step merges the files in deterministic order and publishes the final output.

If multiple threads must write to one shared file, use proper synchronization and verify writer thread safety. In-JVM synchronization does not protect a file from other processes or other nodes. Use inter-process locking or a different output architecture if multiple instances could target the same path.

## 15. Never share one output file across concurrent jobs

Two concurrently running `JobExecution` instances targeting one resource can corrupt output even if both configure append. Append is not a file lock and does not guarantee line ordering across processes.

Common solutions:

- Give each `JobInstance` its own output path.
- Include batch ID, tenant, or date in filenames.
- Have a single sequential publisher write to the consolidated file.
- Use a queue or database as an intermediate sink and export sequentially.
- Use a distributed lock if sharing one output resource is truly unavoidable.

Never rely on the assumption that filesystems “usually write whole lines atomically” to prevent interleaving. Actual behavior depends on filesystem, buffers, OS scheduling, and how writers open files.

## 16. Generating dynamic filenames from JobParameters

`@StepScope` is commonly used to inject output paths from `JobParameters`:

```java
@Bean
@StepScope
FlatFileItemWriter<Order> orderWriter(
        @Value("#{jobParameters['businessDate']}") String businessDate,
        @Value("#{jobParameters['runReference']}") String runReference) {

    String fileName = "orders-" + businessDate + "-" + runReference + ".csv";

    return new FlatFileItemWriterBuilder<Order>()
            .name("orderWriter")
            .resource(new FileSystemResource("output/" + fileName))
            .delimited()
            .delimiter(",")
            .names("orderId", "amount")
            .append(false)
            .shouldDeleteIfExists(true)
            .saveState(true)
            .build();
}
```

In this example, `runReference` must be generated and persisted stably for the same `JobInstance`. If it changes on restart, the writer will write to a new file and leave the old incomplete file behind.

Never pass unvalidated external input directly into file paths. Validate parameters, sanitize filenames, and ensure output paths stay inside permitted application directories.

## 17. Output overwrite with a safe publish workflow

A common three-stage export workflow:

1. Write data to a temporary file scoped to the `JobInstance`.
2. Validate line counts, checksums, or business invariants.
3. Rename the temporary file to the official filename after all steps succeed.

Example flow:

```text
prepareOutputStep
       |
       v
writeTemporaryFileStep
       |
       v
validateOutputStep
       |
       v
publishOutputStep
       |
       v
COMPLETED
```

If `writeTemporaryFileStep` fails, the previous official file remains untouched. On restart, the writer resumes the temporary file from its checkpoint. Once validation passes, the publish step replaces the official file per policy.

If the publish step restarts after the move succeeded but before metadata committed, the tasklet must detect the current file state rather than failing or corrupting data. Inspect source/target existence, verify checksums, and persist a publication marker tied to the `JobExecution`.

## 18. Testing append and overwrite

Test using a dedicated temporary directory per test rather than a fixed workspace path. This prevents tests from depending on execution order or clobbering leftovers from earlier tests.

Core test cases:

| Test case | Setup | Expected verification |
|---|---|---|
| File does not exist, overwrite | `append(false)` | File is created containing new output. |
| File exists, overwrite | `append(false)`, deletion allowed | Old content is replaced by new output. |
| File exists, append | `append(true)` | New content is appended after old content. |
| File exists, fail-if-exists | `append(false)`, `shouldDeleteIfExists(false)` | Opening writer fails instead of deleting or appending. |
| Step writes zero items | Check `shouldDeleteIfEmpty` | Empty file is retained or deleted per configuration. |
| Restart after several chunks | `saveState(true)` and same resource | Writer resumes from saved state without repeating committed chunks. |
| New JobInstance with same path | Different identifying parameters | Verify overwrite/append matches the chosen output policy. |

Conceptual append test using `FlatFileItemWriter`:

```java
@Test
void appendsLinesToExistingFile() throws Exception {
    Path output = tempDir.resolve("orders.csv");
    Files.writeString(output, "old-order,10.00\n");

    FlatFileItemWriter<String> writer =
            new FlatFileItemWriterBuilder<String>()
                    .name("appendWriter")
                    .resource(new FileSystemResource(output))
                    .lineAggregator(item -> item)
                    .append(true)
                    .saveState(false)
                    .build();

    writer.open(new ExecutionContext());
    writer.write(Chunk.of("new-order,20.00"));
    writer.close();

    assertThat(Files.readString(output))
            .contains("old-order,10.00")
            .contains("new-order,20.00");
}
```

This example sets `saveState(false)` solely to test basic appending without setting up restart context. Restart tests must use `saveState(true)`, a `JobRepository`, and real transaction boundaries.

## 19. Testing writer restarts

To test real restarts, run the job/step at least twice on the same `JobInstance` and same output path:

1. Launch the job with fixed identifying parameters.
2. Let the writer write and commit several chunks.
3. Induce a controlled failure in the next chunk.
4. Verify the file contains the committed chunks' contents.
5. Clear the failure condition.
6. Restart the same `JobInstance` with the same parameters.
7. Verify the writer restores state and resumes output.
8. Verify the final file has no missing or duplicate lines.

Tests should read back the file and compare expected business keys, not just check file existence or non-zero byte size.

If a test changes the output path on restart, verify whether that is actually intended behavior. Normally, the same `JobInstance` should resume the same logical output. Changing paths without migrating checkpoints can leave two partial files behind.

## 20. Headers/footers and accumulating outputs

If a file is appended across multiple `JobInstance` runs, define the cumulative format explicitly:

**One header for the entire file:** write the header only when creating the file initially. Subsequent batches write only new records. You need a reliable way to know whether the file already has a header and how to handle empty files.

**One header per batch segment:** each batch writes a marker/header with its batch reference followed by that batch's records. Consumers must understand the multi-segment layout.

**One summary footer:** if the footer holds total line count or checksum across the whole file, you cannot simply append a new footer on each run. Recompute or emit the final footer in a separate publish step.

For interchange formats requiring a single header and a single trailer, it is usually safer to write per-batch temporary files and merge/publish via a controlled step rather than having multiple jobs append directly.

## 21. Choosing modes by business requirement

| Requirement | Recommended strategy |
|---|---|
| Daily report always reflects latest data for that day | Date-based filename with controlled overwrite. |
| Retain every run for audit | Filenames with unique batch/run references; never overwrite old files. |
| Log file accumulating across runs | Append, with batch markers and deduplication/retention rules. |
| Must never overwrite a file already picked up by consumers | Fail if exists, or stage and publish with version controls. |
| Restart of same job must continue partial file | Keep output path, `saveState(true)`, and stable checkpoints. |
| Multiple partitions exporting data | Separate file per partition followed by sequential merge. |
| Consumers must never read incomplete files | Write temporary file, then move/rename after validation. |
| Failed batch must not corrupt previously published output | Write to isolated staging output and replace official file only on publish success. |

## 22. Common pitfalls

| Issue | Common cause | Mitigation |
|---|---|---|
| Previous run's data lost | Overwriting the same path on a new `JobInstance`. | Include batch/date in path or use staging. |
| Duplicate lines in file | Appending the same input multiple times or restarting without restoring state. | Use `saveState(true)`, stable writer name/path, and idempotency. |
| Restart writes to a different file | Output path computed from parameters that changed on restart. | Keep path constant for the same `JobInstance`. |
| Empty file disappears | `shouldDeleteIfEmpty(true)`. | Set to false if the contract requires empty files. |
| Step fails when file exists | `shouldDeleteIfExists(false)` with append disabled. | Choose overwrite, append, or unique filenames per business rules. |
| Duplicate headers | Header callback triggers unexpectedly across opens/appends. | Test headers/footers across new files, existing files, and restarts. |
| File contains uncommitted data | Non-transactional writer or out-of-transaction file side effects. | Keep default transaction-aware writer, staging, and reconciliation. |
| Partitions interleave lines | Multiple workers share one output resource. | Separate files per partition and merge afterward. |
| Two jobs overwrite each other's files | Shared output path with no locking or ownership. | Use separate paths or inter-process locking. |
| Official file replaced before batch finishes | Writing directly to the final resource. | Write to staging, validate, then publish. |
| Tests depend on files from prior runs | Fixed paths without cleaning temporary resources. | Use a fresh temporary directory per test. |

## 23. Workflow for choosing append or overwrite

Before configuring the writer, answer these questions:

1. Does the file represent a single-run snapshot or an accumulating log?
2. When launching a new `JobInstance` and the file exists, should it replace, append, or fail?
3. When restarting the same `JobInstance`, do the output path and file contents stay stable?
4. Does the writer save checkpoints via `saveState(true)`?
5. Do headers/footers belong to the whole file or each batch segment?
6. If the step writes zero items, should an empty file be kept?
7. Can multiple jobs, partitions, or processes write to the same resource?
8. Can consumers see the file while the batch is still writing?
9. If file publish succeeds yet metadata commit fails, how does restart handle it?
10. Can output be reconciled or regenerated from the source if a file is corrupted?

Answering these before picking `.append(...)` and `.shouldDeleteIfExists(...)` ensures your output policy reflects the actual data lifecycle.

## 24. Key takeaways

- `FlatFileItemWriter` can overwrite an existing file, append to the end, or fail if the file already exists.
- `.append(true)` enables appending; `.append(false)` paired with `shouldDeleteIfExists(true)` performs overwrite.
- `.append(false)` paired with `shouldDeleteIfExists(false)` fails if the file already exists.
- `shouldDeleteIfEmpty` controls whether zero-item files are kept.
- Appending for a new run is different from restarting the same `JobInstance`.
- `saveState(true)` and `ExecutionContext` let the writer restore state on restart; appending alone does not prevent duplicates.
- Keep writer name, output path, and identifying parameters stable within the same `JobInstance`.
- Never share a file path across concurrently running `JobInstance` executions without synchronization/ownership.
- Header/footer callbacks must be designed around cumulative file structure and tested on append/restart.
- Transactional writing coordinates with chunk transactions, yet the filesystem is not a global transactional database.
- For critical outputs, write staging files, validate, and publish/rename so consumers never read partial data.
- For partitioning, prefer per-worker files followed by sequential merging.
- Test fresh files, existing files, append, overwrite, fail-if-exists, empty outputs, and restarts against a real `JobRepository`.

Choosing append or overwrite is a decision about output lifecycle. Determine whether the file is a snapshot or accumulating data, distinguish new runs from restarts, keep checkpoints and output paths stable, and control concurrent writes to shared resources. Combining file policies with staging, validation, and idempotency lets batches produce reliable outputs without losing or duplicating data.
