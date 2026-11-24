# Restarting with multiple output files

In Spring Batch, a Step may need to write data across multiple files rather than a single file. For example, a Job exports customer records into files capped at a fixed number of records, splits reports by group, or produces multiple output files for parallel downstream ingestion. When a Job fails mid-run, restarting must resume at the exact file and exact committed position while preserving already-completed files.

Spring Batch provides **MultiResourceItemWriter** to write items across multiple `Resource` targets. This writer uses a **ResourceAwareItemWriterItemStream** as its delegate, typically `FlatFileItemWriter`. It manages the current resource and rotates to a new resource based on an item limit. For reliable restarts, both the outer writer and delegate must save state, writer names must be stable, filenames must be reproducible, and inputs must stay unchanged across restarts.

## 1. The problem of writing multiple output files

Suppose a Job exports 25,000 customers. Operational requirements dictate that each file contains only a bounded number of records for easier download, transfer, or downstream processing.

An output layout may look like:

~~~text
export/
  customers-0001.csv
  customers-0002.csv
  customers-0003.csv
  ...
~~~

If the Job stops after partially writing the third file, a restart must:

- Preserve already-completed files.
- Reopen the exact file currently being written.
- Restore the most recent committed write position.
- Never overwrite or delete already-committed data.
- Continue creating subsequent files as limits are reached.
- Avoid generating duplicate filenames or dropping records.

With only a standard `FlatFileItemWriter`, the writer manages just one `Resource`. To rotate across multiple files, the application would have to manually manage indexes, filenames, per-resource state, and checkpoints. `MultiResourceItemWriter` encapsulates most of this machinery.

## 2. How does MultiResourceItemWriter work?

`MultiResourceItemWriter` takes a base `Resource`, a delegate writer, and an item limit per `Resource`. When the threshold is reached, it transitions the delegate to the next `Resource`.

~~~text
Chunk items
    |
    v
MultiResourceItemWriter
    |
    +--> Resource 1: delegate writer
    |
    +--> Resource 2: delegate writer
    |
    +--> Resource 3: delegate writer
    |
    v
Output files
~~~

Primary responsibilities:

- Managing the resource index and count of items written to the current resource.
- Creating the next `Resource` from the base `Resource` and `ResourceSuffixCreator`.
- Invoking the delegate's lifecycle when the resource changes.
- Persisting required state in `ExecutionContext` when `saveState` is enabled.
- Restoring the current resource and item count when the Step restarts.

The delegate is responsible for writing the content of each item. For example, `FlatFileItemWriter` formats CSV lines, handles encoding, headers/footers, and byte-offset checkpoints. `MultiResourceItemWriter` does not replace the delegate's file-formatting responsibilities.

## 3. Basic MultiResourceItemWriter configuration

In Spring Batch 5, you can use `MultiResourceItemWriterBuilder`:

~~~java
@Bean
MultiResourceItemWriter<Customer> customerMultiWriter(
        FlatFileItemWriter<Customer> customerFileDelegate) {

    return new MultiResourceItemWriterBuilder<Customer>()
            .name("customerMultiWriter")
            .resource(new FileSystemResource("output/customers"))
            .resourceSuffixCreator(index ->
                    String.format("-%04d.csv", index))
            .itemCountLimitPerResource(5_000)
            .delegate(customerFileDelegate)
            .saveState(true)
            .build();
}
~~~

Key settings:

- `name`: stable name for generating state keys in `ExecutionContext`.
- `resource`: base `Resource` used to construct output `Resource` names.
- `resourceSuffixCreator`: builds suffixes from the resource index.
- `itemCountLimitPerResource`: item threshold per output `Resource`.
- `delegate`: writer performing actual content writes.
- `saveState(true)`: enables saving state to support restarts.

Actual filenames depend on how `MultiResourceItemWriter` combines the base `Resource` with the suffix. Verify starting index conventions and generated filenames in your Spring Batch version using integration tests. Never let suffixes depend on wall-clock time or random values, because restarts must reconstruct the exact prior `Resource` names.

## 4. Configuring FlatFileItemWriter as the delegate

The delegate must implement `ResourceAwareItemWriterItemStream` so `MultiResourceItemWriter` can assign a new `Resource` and invoke `open`/`update`/`close` lifecycle methods. `FlatFileItemWriter` is a common choice:

~~~java
@Bean
FlatFileItemWriter<Customer> customerFileDelegate() {
    return new FlatFileItemWriterBuilder<Customer>()
            .name("customerFileDelegate")
            .encoding("UTF-8")
            .lineAggregator(customer ->
                    String.join(",",
                            csv(customer.getCustomerId()),
                            csv(customer.getFullName()),
                            csv(customer.getEmail())))
            .saveState(true)
            .build();
}

private String csv(String value) {
    if (value == null) {
        return "";
    }
    String escaped = value.replace("\"", "\"\"");
    return "\"" + escaped + "\"";
}
~~~

`MultiResourceItemWriter` assigns the current `Resource` to the delegate before opening the file. Consequently, the delegate does not decide filenames per resource; naming belongs to the outer writer.

The delegate name must also be stable and unique within the Step. `FlatFileItemWriter` uses its name to build its own state keys in `ExecutionContext`. Never rename writers between the initial run and a restart if old checkpoints need to be restored.

The line aggregator above illustrates basic CSV formatting. For data with special delimiters, quotes, newlines, or encodings, use a dedicated CSV formatter/library instead of manual string joining. CSV escaping must conform to downstream format rules.

## 5. ResourceSuffixCreator and stable filenames

`ResourceSuffixCreator` defines the suffix appended to the base `Resource` when creating output files. A lambda can be used:

~~~java
.resourceSuffixCreator(index -> String.format("-%04d.csv", index))
~~~

A filename strategy must guarantee:

- The same index always yields the same suffix.
- Filenames do not depend on thread scheduling.
- Filenames do not depend on when the writer is invoked.
- Zero collisions with files from another `JobExecution`.
- Filenames can be reconstructed after a process restart.

For instance, a base `Resource` can embed a fixed batch ID while the suffix represents the resource sequence. If that batch restarts, both the base path and suffix algorithm must match the initial run.

Avoid expressions like:

~~~java
.resourceSuffixCreator(index ->
        "-" + Instant.now().toEpochMilli() + ".csv")
~~~

because the same index can generate a different name on restart. Likewise, do not generate a fresh UUID for each resource unless UUIDs are durably persisted and restored.

If downstream needs the output file list, write a manifest or metadata after the Step finishes. Never leave consumers guessing files solely from a pattern when stale or incomplete files could sit in the directory.

## 6. itemCountLimitPerResource

`itemCountLimitPerResource` sets the item count threshold used by the writer to rotate to the next `Resource`.

For example:

~~~java
.itemCountLimitPerResource(10_000)
~~~

With 25,000 items, the expected output is multiple sequential resources. Actual file count depends on total items, the limit, how the writer splits chunk boundaries, and whether items are filtered or skipped.

Notes:

- This limit counts items, not bytes or physical file size.
- Varying record lengths can make file sizes vary significantly.
- Items filtered by a processor never reach the writer and do not increment the writer's item counter.
- Items skipped during writes must be accounted for according to actual Step and writer behavior.
- Verify how chunks crossing resource boundaries are split in your framework version.

Never assume a file always has an exact byte size or fixed line count merely because `itemCountLimitPerResource` is set. If byte-size caps are required, use another strategy or a custom writer tracking byte counts.

For predictable outcomes, choose chunk size and item limits carefully. If chunks exceed the per-file threshold, run integration tests to verify how `MultiResourceItemWriter` distributes chunk items and the maximum items per resource.

## 7. Wiring the writer into a chunk-oriented Step

`MultiResourceItemWriter` is wired into the Step like a regular `ItemWriter`:

~~~java
@Bean
Step exportCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Customer> customerReader,
        ItemProcessor<Customer, Customer> customerProcessor,
        MultiResourceItemWriter<Customer> customerMultiWriter) {

    return new StepBuilder("exportCustomersStep", jobRepository)
            .<Customer, Customer>chunk(500, transactionManager)
            .reader(customerReader)
            .processor(customerProcessor)
            .writer(customerMultiWriter)
            .build();
}
~~~

The Step reads and processes items in chunks. The writer outputs each chunk into the current resource and rotates to the next resource once the threshold is hit.

The transaction manager governs chunk transactions. With `FlatFileItemWriter`, transactional buffering helps manage uncommitted data during rollbacks and restarts per saved state. If the delegate is a custom writer or writes outside a database, ensure appropriate rollback/restart semantics yourself.

## 8. What state does MultiResourceItemWriter save?

To restart, the writer needs the current resource and write position. `MultiResourceItemWriter` stores resource management state in `ExecutionContext`, including:

- Current `Resource` index.
- Number of items written to the current `Resource`.
- Delegate writer state, if the delegate supports `ItemStream` and state saving.

The delegate normally stores its own checkpoint. With `FlatFileItemWriter`, state can include line counts written and committed byte offsets to resume the file.

You can picture `ExecutionContext` as:

~~~text
StepExecutionContext
  |
  +-- multiResourceWriter.resourceIndex
  |
  +-- multiResourceWriter.currentResourceItemCount
  |
  +-- customerFileDelegate.current.count
  |
  +-- customerFileDelegate.output.position
~~~

Exact key names are derived from component names and implementation. Avoid coupling directly to internal keys unnecessarily; let writers manage state through the `ItemStream` lifecycle.

If `saveState` is disabled, the writer cannot restore the resource index and checkpoints via standard mechanisms. Restarts may then start over or write at the wrong offset. For restartable Jobs, enable `saveState` on both the outer writer and delegate.

## 9. Why do both the outer writer and delegate need saveState?

The two writers track two distinct kinds of state:

| Component | State needing restoration |
|---|---|
| `MultiResourceItemWriter` | Which resource index is active and how many items have been written to it |
| `FlatFileItemWriter` delegate | Committed byte/line position in the current file and related write state |

If only delegate state is saved, the framework may know the offset inside a file without knowing which resource index to select. If only `MultiResourceItemWriter` state is saved, the wrapper knows the filename, but the delegate lacks the committed offset to resume from.

Therefore, a restartable setup requires:

~~~java
new FlatFileItemWriterBuilder<Customer>()
        .name("customerFileDelegate")
        .lineAggregator(customerLineAggregator)
        .saveState(true)
        .build();

new MultiResourceItemWriterBuilder<Customer>()
        .name("customerMultiWriter")
        .resource(baseResource)
        .itemCountLimitPerResource(5_000)
        .delegate(customerFileDelegate)
        .saveState(true)
        .build();
~~~

Names of both components must be stable. Never generate names with UUIDs or fresh timestamps each time the application context boots.

## 10. Restarting after some files have completed

Suppose each resource is capped at 1,000 items and the Job processes 3,400 items. The Job completes the first and second files, and fails while writing the third file.

High-level flow:

~~~text
First run
  Resource 1: 1,000 items -> completed
  Resource 2: 1,000 items -> completed
  Resource 3: 400 items committed
  Job fails

Restart same JobInstance
  Keep Resource 1 and Resource 2
  Reopen Resource 3
  Restore committed position
  Write remaining items
  When limit reached, create Resource 4
~~~

Already-completed files must not be deleted or rewritten if they belong to the restarting execution. The writer must reconstruct the exact current resource from saved state, and the delegate must restore its checkpoint within that resource.

If the output directory is wiped before restarting, the writer may lack resources to restore or emit incomplete output. Protect committed files until the Job completes and downstream ingests them per workflow.

## 11. Conditions for reliable restarts

Restarting with multiple output files requires keeping more pieces stable than single-file restarts:

1. **Same `JobInstance`:** reuse the exact identifying `JobParameters` from the initial run.
2. **Same inputs:** input resources, contents, and item ordering must match the prior run.
3. **Same base output `Resource`:** root output path does not change.
4. **Same suffix algorithm:** each resource index maps to the exact same filename.
5. **Same item limit:** do not change `itemCountLimitPerResource` between runs and restarts.
6. **Same writer names:** `MultiResourceItemWriter` and delegate names remain stable.
7. **State enabled:** `saveState` enabled on both outer writer and delegate.
8. **Outputs not cleaned up:** preserve committed resources and the active file.
9. **Same mapping/format:** line aggregator, encoding, headers, and output schema remain compatible.
10. **Same processing order:** if item order shifts, file indexes and contents will shift.

If any of these factors change, old checkpoints may no longer match current output. When changing formats or splitting rules, create a new `JobInstance` or design explicit migration rather than restarting with altered configuration.

## 12. JobParameters and output paths

Output paths should usually derive from an identifying `JobParameter` or a stable batch identifier. For example:

~~~text
input.file = /data/in/customers-2026-11-15.json
batch.id   = CUSTOMER-20261115
output.dir = /data/out/CUSTOMER-20261115
~~~

On restart, supply the exact same identifying parameters so Spring Batch locates the existing `JobInstance`. If `output.dir` is computed from current wall-clock time on every launch, a restart writes to a new directory even though `JobRepository` restored the old checkpoint.

A `StepScope` configuration:

~~~java
@Bean
@StepScope
MultiResourceItemWriter<Customer> customerMultiWriter(
        @Value("#{jobParameters['output.dir']}") String outputDir,
        FlatFileItemWriter<Customer> customerFileDelegate) {

    Resource baseResource = new FileSystemResource(
            Path.of(outputDir, "customers").toFile());

    return new MultiResourceItemWriterBuilder<Customer>()
            .name("customerMultiWriter")
            .resource(baseResource)
            .resourceSuffixCreator(index ->
                    String.format("-%04d.csv", index))
            .itemCountLimitPerResource(5_000)
            .delegate(customerFileDelegate)
            .saveState(true)
            .build();
}
~~~

`JobParameters` `output.dir` should be immutable for the `JobInstance`. Do not use non-identifying `JobParameters` to alter the output directory between runs and restarts while writer state still belongs to the same execution.

## 13. Filenames and file collisions across runs

Two different `JobInstance` executions can run concurrently. If both share the same base `Resource` and suffix, they can overwrite or interleave output.

Isolate output namespaces by batch ID or `JobInstance` identity:

~~~text
output/
  CUSTOMER-20261115-A/
    customers-0001.csv
    customers-0002.csv
  CUSTOMER-20261115-B/
    customers-0001.csv
    customers-0002.csv
~~~

Ensure:

- Batch IDs never collide across independent runs.
- Restarts of the same `JobInstance` reuse the exact same batch ID.
- Two distinct executions never share an output directory.
- File write permissions are scoped properly to the application.
- Cleanup jobs never delete directories still in use by another Job.

Even if concurrent launches with identical identifying parameters are guarded by `JobRepository` execution status checks, the system still needs collision protection across distinct `JobInstance` runs and misconfigured launches.

## 14. Rollbacks and output files

Database transactions can roll back database mutations, whereas files sit outside ordinary database transactions. Spring Batch's `FlatFileItemWriter` provides transaction-aware buffering and checkpointing to align file writes with chunks. However, do not generalize those guarantees to arbitrary custom delegates or all filesystems.

Distinguish these cases:

- Data buffered in a chunk that rolls back: a transaction-aware writer can discard uncommitted buffers.
- Data committed in earlier chunks: must be preserved and resumed after the checkpoint.
- Abrupt process kill: a file may hold an uncommitted tail; the delegate must restore/truncate per saved state if supported by the implementation.
- Custom writer calling HTTP or object storage: database transactions do not automatically undo sent requests.
- Filesystem or disk failure: restarts may fail to open or write resources.

If a delegate does not support rollback/restart, `MultiResourceItemWriter` cannot make it transaction-aware automatically. The delegate itself must implement `ItemStream` with an appropriate recovery strategy.

## 15. FlatFileItemWriter and checkpoints on restart

`FlatFileItemWriter` persists state tracking how far it has written. On restart, it uses the saved checkpoint to resume from the corresponding byte offset, handling uncommitted tails according to implementation semantics.

Relevant settings:

- `name`: identifies the delegate's state.
- `saveState(true)`: persists checkpoints.
- `encoding`: keep encoding identical across runs.
- `lineAggregator`: keep line formatting deterministic.
- `header`/`footer` callbacks: keep header/footer logic consistent.
- `append`/`shouldDeleteIfExists`: configure consistently with restart strategy.

Do not toggle `append` or `shouldDeleteIfExists` haphazardly on restartable Jobs. Creating a fresh file and reopening a checkpointed file are distinct scenarios. Verify `FlatFileItemWriter` behavior in your running version and test both fresh executions and restarts.

In particular, never run a script wiping the output directory before every launch if that launch could be a restart. Cleanup should run only when you know for certain it is a new `JobInstance` or an intentional fresh run.

## 16. Headers and footers on individual output files

`FlatFileItemWriter` can write headers and footers. When used as a `MultiResourceItemWriter` delegate, the delegate's lifecycle binds to each `Resource`. Hence, headers/footers can apply to every file depending on writer configuration.

For example:

~~~java
new FlatFileItemWriterBuilder<Customer>()
        .name("customerFileDelegate")
        .headerCallback(writer ->
                writer.write("customerId,fullName,email"))
        .footerCallback(writer ->
                writer.write("# end of file"))
        .lineAggregator(customerLineAggregator)
        .saveState(true)
        .build();
~~~

If each file needs its own header, configuring a header callback on the delegate is appropriate. If only the first or last file needs special metadata, add logic aware of resource indexes or generate a post-Step manifest.

Footers require care on restarts. An incomplete file should not be mistaken for a complete file merely because `close` ran during a cleanup path. For strict file-completeness control, write a completion marker or manifest only after the Step succeeds.

## 17. Completed files vs. files still being written

While a Job runs, the output directory may contain both completed files and files currently being written. Downstream consumers should not blindly read every file appearing in the directory without knowing whether the Job finished.

A safe strategy:

1. Write outputs into a batch-specific staging directory.
2. Mark the batch complete only after the Step/Job succeeds.
3. Generate a manifest listing filenames, record counts, and checksums if needed.
4. Publish the manifest or move the directory into a ready location.
5. Downstream reads only batches marked complete.

Example layout:

~~~text
staging/
  batch-CUSTOMER-20261115/
    customers-0001.csv
    customers-0002.csv
    customers-0003.csv
    manifest.json

ready/
  batch-CUSTOMER-20261115/
~~~

Publishing directories or manifests must match the atomicity guarantees of your filesystem or object storage. If atomic renames are unavailable, rely on manifest status or a final marker file written last.

`MultiResourceItemWriter` does not manage batch-wide publishing itself. That responsibility belongs to a final Step, Job listener, or dedicated publish step.

## 18. Creating a manifest for multiple output files

A manifest tells downstream precisely which files belong to a batch and whether all files finished:

~~~json
{
  "batchId": "CUSTOMER-20261115",
  "status": "COMPLETED",
  "files": [
    {
      "name": "customers-0001.csv",
      "recordCount": 5000
    },
    {
      "name": "customers-0002.csv",
      "recordCount": 5000
    }
  ]
}
~~~

In production applications, a manifest may include:

- Batch ID and `JobExecution` ID.
- Input file ID or checksum.
- Output filenames.
- Per-file record counts.
- Total record count.
- File sizes and checksums.
- Schema/format version.
- Start and completion timestamps.
- `COMPLETED` or `FAILED` status.

Publish a `COMPLETED` manifest only after all outputs are closed and the Step/Job succeeds. If the Job fails, write `FAILED` metadata in an audit area so downstream never treats partial files as a complete batch.

If per-file record counts are needed, collect them via a recoverable mechanism or scan finished files after the writer completes. Do not rely on in-memory counters, because restarts lose in-memory state and retries can increment counters multiple times.

## 19. Restarting when the generated file count changes

File counts depend on total items, item limits, and which items actually reach the writer. If inputs or filtering logic change, an existing checkpoint can produce a mismatched output structure.

For example:

- First run has 12,000 valid items.
- Source later changes to 11,500 items.
- The Job restarts against the modified file using the old checkpoint.

The reader may resume from the old position while earlier output files reflect data from the prior source. Output can end up with missing or mixed records.

To prevent this:

- Keep inputs immutable per batch ID.
- Verify checksums or source versions before restarting.
- Keep processor/filter logic unchanged within a `JobInstance`.
- Never alter `itemCountLimitPerResource` midway.
- If source data or logic changes, launch a new `JobInstance` and reconcile cleanly.

Restarting means resuming an existing checkpointed execution—not re-running the same Job name against arbitrary new data.

## 20. MultiResourceItemWriter in partitioning

With partitioning, multiple worker `StepExecution` instances run concurrently. If workers share the same base `Resource` and suffix algorithm, they can overwrite the same filenames.

Each worker needs an isolated output namespace:

~~~text
output/
  partition-000/
    customers-0001.csv
    customers-0002.csv
  partition-001/
    customers-0001.csv
    customers-0002.csv
  partition-002/
    customers-0001.csv
~~~

You can build output directories from `StepExecutionContext`:

~~~java
@Bean
@StepScope
MultiResourceItemWriter<Customer> partitionCustomerWriter(
        @Value("#{stepExecutionContext['partitionName']}") String partitionName,
        @Value("#{jobParameters['output.dir']}") String outputDir,
        FlatFileItemWriter<Customer> delegate) {

    Resource baseResource = new FileSystemResource(
            Path.of(outputDir, partitionName, "customers").toFile());

    return new MultiResourceItemWriterBuilder<Customer>()
            .name("partitionCustomerWriter")
            .resource(baseResource)
            .resourceSuffixCreator(index ->
                    String.format("-%04d.csv", index))
            .itemCountLimitPerResource(5_000)
            .delegate(delegate)
            .saveState(true)
            .build();
}
~~~

Partition names must remain stable when restarting the same `JobInstance`. Never use thread names as partition identifiers because thread pools may assign different worker threads across runs.

Each worker owns its own `StepExecutionContext`, yet both the delegate writer and outer writer must still be scoped properly. Never share a single stateful `MultiResourceItemWriter` instance across concurrent partitions.

After all workers complete, a manager Step or downstream step can aggregate manifests from each partition's output directory.

## 21. MultiResourceItemWriter and concurrency within one Step

Never assume a stateful `MultiResourceItemWriter` can be invoked concurrently by multiple threads. It tracks resource index, item count, and the delegate's current resource. Concurrent writes cause races across threshold checks, resource rotation, and counter updates.

Risks include:

- Two threads simultaneously deciding to create a new resource.
- Items written to unexpected resources.
- Item counts drifting or exceeding limits unexpectedly.
- Delegate resource swapped while another thread is writing.
- Checkpoints reflecting inconsistent write/commit ordering.

To parallelize output, prefer partitioning with dedicated writers per worker, or a writer explicitly designed with clear concurrent output contracts. Wrapping `MultiResourceItemWriter` in a `synchronized` lock serializes all writes and defeats concurrency benefits.

## 22. Skip, retry, and errors while writing files

Writers can encounter errors:

- Unable to create output directory.
- Permission denied writing files.
- Disk full.
- File locked or deleted mid-run.
- I/O errors during flush/close.
- Delegate unable to restore checkpoint.

Infrastructure failures like these are rarely appropriate for item skipping. If disk space runs out or files are unwritable, skipping items silently loses data. Bounded retries fit only transient errors where re-execution is safe.

When a specific item cannot be serialized to output, exception-specific skipping may be allowed by business rules. Always log skipped items to an audit/quarantine sink and distinguish item failures from whole-resource I/O failures.

When using retries, writers and delegates must be idempotent or use transaction-aware checkpoints so retries do not duplicate committed lines. Never manually retry file writes by calling the delegate while bypassing Spring Batch state and transactions.

## 23. Verifying output after restart

After the Job finishes, verify:

- Generated `Resource` filenames match the expected pattern.
- No duplicate filenames or unexpected empty files exist.
- Every file carries required headers and footers.
- Total record count matches expected valid items.
- No unintended duplicate business keys exist.
- All files are closed and readable.
- Manifest lists only completed files.
- Checksums or file sizes match persisted metadata if tracked.

Do not check only for `COMPLETED` Job status. A Job can complete while producing misnamed files or skewed record counts if suffixes or item limits were misconfigured.

## 24. Multi-file restart testing example

An integration test should execute the Job twice against the same `JobRepository` and identical identifying parameters. The first launch writes several chunks and fails intentionally; the second restarts the same `JobInstance` and verifies outputs.

Test flow:

~~~text
Arrange:
  input has 25 items
  item limit per file = 10
  chunk size = 5
  writer saveState = true
  delegate saveState = true

First launch:
  commit several chunks
  inject intentional failure
  Job FAILED

Restart:
  use same identifying JobParameters
  restore writer state
  resume writing
  Job COMPLETED

Assert:
  all 25 items present exactly once
  resource names stable
  no committed data lost
  no uncommitted tail retained
~~~

Skeleton test:

~~~java
@SpringBatchTest
@SpringJUnitConfig(MultiResourceExportTestConfiguration.class)
class MultiResourceWriterRestartTest {

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void resumesCurrentOutputResourceAfterFailure() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("batchId", "CUSTOMER-TEST-01", true)
                .addString("input.file", "src/test/resources/customers.json", true)
                .addString("output.dir", "target/test-output/CUSTOMER-TEST-01", true)
                .toJobParameters();

        JobExecution first = jobLauncherTestUtils.launchJob(parameters);
        assertEquals(BatchStatus.FAILED, first.getStatus());

        JobExecution restarted = jobLauncherTestUtils.launchJob(parameters);
        assertEquals(BatchStatus.COMPLETED, restarted.getStatus());

        // Read all output files and verify business keys have no gaps or duplicates.
        assertEquals(expectedCustomerIds, readAllCustomerIds(outputDirectory));
    }
}
~~~

This test needs a failure-injection mechanism that fails only the initial run at a deterministic point. `JobRepository` must persist metadata between both launches, and the output directory must not be cleaned before restarting. Never use a fresh test repository or new output directory on the second launch when testing real restarts.

## 25. Testing filenames and resource boundaries

Beyond restarts, verify the suffix creator and item limits:

1. Fewer items than the limit: expected resource count created.
2. Item count equal to the limit: exact resource boundary behavior.
3. Item count one above the limit: next resource created.
4. Chunks spanning the limit boundary: verify item distribution per version API.
5. Resource suffixes stable across two writer instantiations.
6. Two `JobInstance` runs write to distinct output directories.
7. Different partitions never collide.
8. Unwritable resource: Step fails cleanly.
9. Restart while still on the first resource.
10. Restart after rotating across multiple resources.

Read the actual contents of every file in tests rather than merely counting files. Inspect headers, records, order, and business keys to catch duplicate or dropped writes.

## 26. Common pitfalls

**Enabling saveState only on MultiResourceItemWriter:** the delegate does not save its write-position checkpoint, so restarts may fail to resume inside the current file accurately. Enable `saveState` on both outer writer and delegate.

**Omitting stable writer names:** `ExecutionContext` keys can shift and old state will not be found. Assign explicit names to both writers.

**Time- or randomness-dependent suffixes:** restarts generate different filenames. Use deterministic suffixes based on index.

**Changing itemCountLimitPerResource:** saved resource index and current count will no longer match. Keep configuration identical across restarts.

**Changing the base output path:** the writer may open a different file set while state belongs to the old set. Keep output paths fixed per `JobInstance`.

**Wiping the output directory before restart:** already-committed files are lost or the delegate cannot restore offsets. Clean up only for explicitly new executions.

**Assuming chunk transactions roll back all files automatically:** only delegates with proper transactional/restart support offer those semantics. Custom external outputs must design their own recovery.

**Sharing a stateful writer across partitions:** resource index and delegate state get overwritten. Create dedicated writers and output namespaces per worker.

**Treating item limits as byte limits:** varying record lengths change file sizes. Track bytes explicitly if size caps are required.

**Downstream reading files while the Job is running:** consumers may ingest incomplete files. Use staging, manifests, or completion markers.

**Not keeping inputs immutable:** old checkpoints may resume over altered data. Store batch IDs/checksums and validate sources on restart.

**Not testing restarts against a real JobRepository:** unit testing a standalone writer does not prove state restoration across two `JobExecution` runs.

## Conclusion

`MultiResourceItemWriter` allows Spring Batch to write items across multiple `Resource` targets by rotating at `itemCountLimitPerResource` and delegating actual serialization to a `ResourceAwareItemWriterItemStream` delegate. For reliable restarts, enable `saveState` on both the outer writer and delegate, use stable writer names, and preserve base output `Resource`, suffix creator, item limit, inputs, and processing order within the same `JobInstance`. `FlatFileItemWriter` supports file-position checkpoints, whereas custom delegates must implement their own rollback/restart semantics. With partitioning, each worker requires an isolated output namespace and writer state. Retain committed files, avoid pre-restart cleanup, test failure/restart against a durable `JobRepository`, and publish manifests only after all outputs finish so downstream never reads incomplete files.
