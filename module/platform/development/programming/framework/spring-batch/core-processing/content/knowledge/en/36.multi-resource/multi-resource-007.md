# Splitting output by item count

In Spring Batch, `MultiResourceItemWriter` enables a Step to write output across multiple resources instead of dumping everything into a single file. The writer wraps a delegate capable of receiving a `Resource`, tracks how many items have been written to the current resource, and transitions to the next resource once the configured limit is reached.

This mechanism fits requirements where a receiving system caps the maximum number of records per file—for instance, splitting an export into chunks of 100,000 lines for downstream transfer. `MultiResourceItemWriter` splits by the number of items received by the writer, not by byte file size. Safe usage requires consistent configuration of the delegate, file naming rules, checkpoint/restart state, transactions, and resource lifecycle.

## 1. Why split output into multiple resources?

A batch job may process millions of records. Writing everything into a single file can create difficulties downstream:

- Receiving systems impose line-count or file-size limits.
- Huge files are hard to transfer over networks or archive.
- Multiple consumers need to process independent data partitions.
- Operations need file-level batching for verification, retries, or retention.
- A massive file is difficult to inspect manually and hard to recover on transfer failures.

For example, a Job exports 1,000,000 orders with at most 100,000 items per file:

~~~text
Input: 1,000,000 Orders
             |
             v
    MultiResourceItemWriter
             |
      +------+------+------+
      |      |      |      |
      v      v      v      v
   File 1 File 2 File 3 ... File 10
   100k   100k   100k       100k
~~~

Instead of manually counting lines, closing files, generating next filenames, and instantiating new writers, the application delegates resource coordination to `MultiResourceItemWriter`.

## 2. How does MultiResourceItemWriter work?

`MultiResourceItemWriter` is a writer wrapper around a delegate writer. The delegate must support receiving new resources via the `ResourceAwareItemWriterItemStream` contract, with `FlatFileItemWriter` being a common example.

Responsibilities are cleanly separated:

- `MultiResourceItemWriter` tracks the resource index and item count written to the current resource.
- The delegate writer serializes items and writes contents to the currently assigned resource.
- `ResourceSuffixCreator` generates suffixes to distinguish each file.
- The Step and `JobRepository` manage checkpoints to support restarts.

High-level flow:

~~~text
Chunk items
    |
    v
MultiResourceItemWriter
    |
    +--> Check item count in current resource
    |
    +--> Space left: write to current resource
    |
    +--> Limit reached: rotate to next resource
    |                     |
    |                     v
    |               Delegate.setResource(...)
    |
    v
Delegate writer writes items
~~~

The writer continues reusing the delegate across subsequent resources. The application does not need to construct a new `FlatFileItemWriter` per file.

## 3. Splitting by item count, not file size

The `itemCountLimitPerResource` property sets the maximum number of items a single resource receives under the writer's counting mechanism.

For example, with a limit of 3:

~~~text
Input: A, B, C, D, E, F, G, H

orders-00001.csv: A, B, C
orders-00002.csv: D, E, F
orders-00003.csv: G, H
~~~

Each item counts as one unit regardless of its payload size. Whether a record serializes to 2 KB or 30 bytes, each increments the counter by one item.

Therefore:
- If the requirement is at most 100,000 records per file, `MultiResourceItemWriter` fits.
- If the requirement is files not exceeding 50 MB, an item count limit does not guarantee that.
- If individual item sizes vary widely, files with identical item counts can differ drastically in byte size.
- If splitting by bytes is required, use a custom writer or downstream splitting step that measures actual serialized byte sizes.

Never use `itemCountLimitPerResource` as a file-size cap.

## 4. Distinguishing chunk size and item count limit

Chunk size and item count limit govern two distinct things:

| Parameter | Meaning |
|---|---|
| Chunk size | Number of items read/processed in one chunk before committing |
| `itemCountLimitPerResource` | Maximum items written to a single output resource before rotating files |

For example:
- Chunk size = 200.
- Item count limit = 1,000.

Each resource receives roughly 5 chunks if each chunk has 200 items. However, the two limits do not need to divide evenly.

If the current resource already holds 900 items and the next chunk contains 200 items, the writer must split the chunk across the resource boundary:

~~~text
Resource 1 has capacity for 100
New chunk has 200 items

First 100 items -> Resource 1
Next 100 items  -> Resource 2
~~~

Thus, chunk size does not have to equal the item count limit. Choose chunk size for transaction, memory, and throughput performance; choose item count limit based on downstream file requirements.

## 5. Delegate must accept a Resource

`MultiResourceItemWriter` does not format data itself. It requires a delegate implementing `ResourceAwareItemWriterItemStream` so it can swap resources before opening and writing.

Commonly used delegates:
- `FlatFileItemWriter` for CSV, TSV, or plain text.
- `StaxEventItemWriter` to produce separate XML resources per item group when XML configuration is compatible.
- Custom writers implementing `ResourceAwareItemWriterItemStream`.

A plain `ItemWriter` that only exposes `write` without accepting a `Resource` does not satisfy the contract required by `MultiResourceItemWriter`.

A delegate typically needs:
- `setResource(Resource)` to receive the current file.
- `open(ExecutionContext)` to open the resource.
- `write(...)` to write items.
- `update(ExecutionContext)` to save state.
- `close()` to flush and close the resource.

`MultiResourceItemWriter` manages resource rotation and the delegate's lifecycle per file.

## 6. Configuring FlatFileItemWriter as the delegate

Example delegate writing `Order` records as CSV:

~~~java
@Bean
@StepScope
FlatFileItemWriter<Order> orderFileDelegate() {
    return new FlatFileItemWriterBuilder<Order>()
            .name("orderFileDelegate")
            // Actual resource will be assigned by MultiResourceItemWriter.
            .resource(new FileSystemResource(
                    "target/delegate-placeholder.csv"))
            .lineAggregator(order ->
                    order.getId() + ","
                    + order.getCustomerId() + ","
                    + order.getAmount())
            .saveState(true)
            .build();
}
~~~

The resource in the delegate definition acts as an initial value to complete bean initialization. When `MultiResourceItemWriter` creates a file, it injects the corresponding resource into the delegate before opening the file.

In production applications, apply proper CSV escaping for commas, double quotes, and newlines inside fields. Configure `DelimitedLineAggregator` and a `FieldExtractor` rather than manual string concatenation.

The delegate name must be stable because the writer may store its own state in `ExecutionContext`. Never reuse the same delegate instance across concurrent streams if it holds mutable resource and stream state.

## 7. Configuring MultiResourceItemWriter with the Builder

Spring Batch provides `MultiResourceItemWriterBuilder` to construct the writer:

~~~java
@Bean
@StepScope
MultiResourceItemWriter<Order> ordersMultiWriter(
        @Value("#{jobParameters['outputDirectory']}")
        String outputDirectory,
        FlatFileItemWriter<Order> orderFileDelegate) {

    return new MultiResourceItemWriterBuilder<Order>()
            .name("ordersMultiWriter")
            .resource(new FileSystemResource(
                    outputDirectory + "/orders"))
            .delegate(orderFileDelegate)
            .itemCountLimitPerResource(100_000)
            .resourceSuffixCreator(index ->
                    String.format("-%05d.csv", index))
            .saveState(true)
            .build();
}
~~~

Key configuration properties:

- `name(...)`: stable name of `MultiResourceItemWriter` in `ExecutionContext`.
- `resource(...)`: base resource used to form output filenames.
- `delegate(...)`: writer performing actual content serialization and writes.
- `itemCountLimitPerResource(...)`: maximum items per resource.
- `resourceSuffixCreator(...)`: rule generating suffixes from the resource index.
- `saveState(...)`: enables checkpoint persistence on the wrapper.

With the suffix creator above, filenames follow the writer-provided index, such as `orders-00001.csv`, `orders-00002.csv`. Zero-padded numbers make filenames easier to sort lexicographically.

Signatures and packages should match your project's Spring Batch version. The builder provides a clear declaration and avoids omitting required properties.

## 8. File naming and ResourceSuffixCreator

The base resource supplies the root filename. `ResourceSuffixCreator` receives the index and returns the suffix distinguishing each file.

For example:

~~~java
.resource(new FileSystemResource("/batch/output/orders"))
.resourceSuffixCreator(index ->
        String.format("-%05d.csv", index))
~~~

Expected outputs by index:

~~~text
/batch/output/orders-00001.csv
/batch/output/orders-00002.csv
/batch/output/orders-00003.csv
~~~

Naming principles:

- Filenames must be unique within the scope of a Job/`JobInstance`.
- Suffixes must derive deterministically from the index, never randomly.
- Do not inject fresh timestamps on restarts if you want to resume the same file set.
- Use zero-padding if consumers rely on lexicographical filename sorting.
- Ensure the output directory exists and the process has write permissions.
- Avoid suffixes containing path separators or unvalidated user input.

If using the framework's default suffix, check its exact format in your running version. When downstream contracts require a fixed naming scheme, declare an explicit `ResourceSuffixCreator` and test generated filenames directly.

## 9. Registering the writer in a Step

`MultiResourceItemWriter` is registered as the primary writer on the Step:

~~~java
@Bean
Step exportOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, Order> orderProcessor,
        MultiResourceItemWriter<Order> ordersMultiWriter) {

    return new StepBuilder("exportOrdersStep", jobRepository)
            .<Order, Order>chunk(500, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(ordersMultiWriter)
            .build();
}
~~~

`MultiResourceItemWriter` implements `ItemStream` and manages the lifecycle of its wrapped delegate. In standard configuration, register the wrapper via `.writer(ordersMultiWriter)` so the Step invokes the wrapper's lifecycle; the wrapper coordinates opening and closing the delegate for each resource.

Do not open the delegate manually outside the wrapper or share the same delegate concurrently with another Step. Any additional independent streams not owned by the wrapper must be registered separately with the Step.

## 10. What happens when a chunk exceeds the limit?

Suppose the per-file limit is 5 items, the current file already holds 4 items, and the next chunk has 3 items:

~~~text
Before chunk:
  file-1: A, B, C, D
  1 slot remaining

New chunk:
  E, F, G

After writing:
  file-1: A, B, C, D, E
  file-2: F, G
~~~

The writer rotates to the next resource once the current limit is reached. Hence, a single chunk can be split across two or more files if the chunk is larger than the remaining item capacity of the current file.

Design downstream consumers around file and item order rather than assuming each chunk stays inside a single file.

Exact numbers of `write` calls to the delegate and sub-chunk slicing are implementation details that can vary across versions. Rely on the output contract and test against your actual Spring Batch version.

## 11. Item ordering across resources

`MultiResourceItemWriter` writes items in the exact order delivered by the Step. When the current resource hits its limit, subsequent items go into the new resource.

For example:

~~~text
Input order:
  101, 102, 103, 104, 105, 106, 107

Limit = 3

File 1:
  101, 102, 103

File 2:
  104, 105, 106

File 3:
  107
~~~

The writer does not sort data itself. If the source lacks a deterministic order, files may contain records in different orders across runs or restarts.

When ordering is a business requirement:
- Use a stable `ORDER BY` in the reader.
- Include a unique tie-breaker sort key whenever possible.
- Never rely on natural database return order.
- Keep queries and source data consistent across restarts.
- Verify item order within each file and across files.

Indexed filenames reflect only the order in which the writer created resources; they do not guarantee business ordering if inputs are unsorted.

## 12. Which items count toward the limit?

The limit applies to items received by `MultiResourceItemWriter` on the write path. Therefore, items filtered out by a processor and never passed to the writer do not increment the output counter.

For example:
- Reader reads 1,000 rows.
- Processor filters 100 items by returning `null`.
- Writer receives 900 items.
- With a limit of 300, output produces 3 resources containing 300 items each.

If skip or retry policies are active on the writer, test how your framework version updates counts and checkpoints during error scenarios. Never infer source record counts from total output items because processors may filter or transform items.

Reconcile across:
- Read count.
- Process skip count.
- Write count.
- Per-resource item counts.
- Total records across final output files.

## 13. Checkpointing and restarts

`MultiResourceItemWriter` supports saving state to resume at the exact resource when a Step restarts. The wrapper's state typically records the current resource index and the number of items written to that resource; the delegate may hold its own state.

For reliable restarts:
- Give the wrapper a stable name.
- Give the delegate a stable name.
- Enable `saveState(true)` on the wrapper and any checkpointing delegate.
- Keep the base resource unchanged.
- Keep `ResourceSuffixCreator` and suffix generation rules unchanged.
- Keep the item count limit unchanged.
- Keep queries, sort order, and source data affecting item order consistent.
- Never modify or delete already-checkpointed files.

Example initial run:
~~~text
JobInstance = 52
current resource index = 3
item count in current resource = 40
~~~

After restarting the same `JobInstance`, the writer reopens the corresponding resource and resumes after the 40 checkpointed items per saved state.

Do not reset the index back to 1 on restart. Do not generate fresh timestamp-based suffixes. If the output path changes, checkpoints may point to missing or mismatched resources.

## 14. Keeping output paths stable per JobInstance

If a Job must restart and continue writing to its prior file set, the output base path should remain stable per `JobInstance`. You can build the directory or prefix from the `JobInstance` ID inside a `JobExecutionListener`, then inject it via the Job `ExecutionContext`.

Example listener:

~~~java
public class MultiOutputPathListener
        implements JobExecutionListener {

    @Override
    public void beforeJob(JobExecution execution) {
        long instanceId =
                execution.getJobInstance().getInstanceId();

        String outputDirectory =
                "/batch/output/orders-" + instanceId;

        execution.getExecutionContext().putString(
                "orders.output.directory",
                outputDirectory);
    }
}
~~~

The step-scoped writer receives the path:

~~~java
@Value("#{jobExecutionContext['orders.output.directory']}")
String outputDirectory
~~~

The `JobInstance` ID stays constant across restarts of the same instance, whereas the `JobExecution` ID increments. Using the instance ID or a stable identifying business key ensures all files of one logical processing unit share the same prefix.

In systems with multiple `JobRepository` databases or environments, include the job name, tenant, or environment in the path to avoid ID collisions across independent repositories.

## 15. Overwriting and pre-existing files

Overwrite policies must be evaluated alongside restarts.

Three distinct scenarios exist:

1. New `JobInstance`: creates a fresh output set with a new prefix or directory.
2. Restarting the same `JobInstance`: resumes existing resources and checkpoints.
3. Re-running new business logic: launches a new `JobInstance`, typically with a distinct prefix.

Delegates like `FlatFileItemWriter` expose properties controlling how existing resources are handled. Configure them properly for creating new outputs versus resuming prior outputs. Never enable unconditional overwrite blindly if it could wipe files containing previously committed chunks.

If files exist without matching checkpoint metadata, they may be orphaned artifacts from a process crash or operational mistake. Reconcile `JobRepository` and output directories before deleting, renaming, or appending.

## 16. Headers and footers apply to each file

The delegate is opened and closed per resource. Consequently, the delegate's header/footer callbacks normally execute per file lifecycle, not once for the entire set of files.

For example, if the delegate is a `FlatFileItemWriter` with a header callback:

~~~text
orders-00001.csv
  header
  item 1
  item 2
  ...
  item 100000

orders-00002.csv
  header
  item 100001
  item 100002
  ...
  footer
~~~

Every file should be self-contained and valid per contract. If CSV files require column headers, each resource should carry its own header so consumers can read files individually.

If the delegate is an XML writer, each resource must be a well-formed XML document with its own XML declaration and root element. Never concatenate multiple XML files at the byte level into one document; parse and merge structurally if a single combined document is needed.

Verify headers and footers are written accurately in the first file, middle files, the last file, and across restarts.

## 17. Empty input and partial trailing files

If the total item count is not divisible by the limit, the final file will contain fewer items than preceding files.

For example, 10 items with a limit of 4:

~~~text
File 1: 4 items
File 2: 4 items
File 3: 2 items
~~~

Do not pad out empty files just to reach a fixed file count. For completely empty input, resource creation behavior depends on writer lifecycle and version; never assume an empty file is always created.

If downstream expects a file even when zero records exist, explicitly define the behavior:
- Create an empty file containing a header.
- Create a file with only header and footer.
- Create a manifest reporting zero records.
- Create no files and mark the batch as empty.

A separate step may be required to handle the zero-item case rather than forcing the writer to emit empty resources.

## 18. Writing by item count vs. splitting by file size

When item payloads vary in size, item count does not correlate linearly with byte size.

For example:
~~~text
File A: 10,000 items x avg 100 bytes ~= 1 MB
File B: 10,000 items x avg 5 KB     ~= 50 MB
~~~

Both files hit the exact same item count limit yet differ dramatically in byte size.

If the requirement is a file-size cap:
- Measure serialized size before writing.
- Implement a custom `ResourceAwareItemWriterItemStream` tracking byte counts.
- Rotate resources before the next item exceeds the limit.
- Handle edge cases where a single item exceeds the limit.
- Ensure checkpoints persist both resource index and byte offset.
- Account for encoding, newlines, and headers/footers because they also consume bytes.

Never substitute an estimated `itemCountLimitPerResource` to fake a byte limit when contracts enforce hard size caps.

## 19. Resource lifecycle and the delegate

`MultiResourceItemWriter` manages the current resource and delegate writer. When rotating files, the wrapper closes the delegate on the old resource, assigns the new resource, and opens the delegate for the new file.

This implies:
- The delegate must support resource reassignment.
- The delegate must open and close cleanly multiple times within a single Step.
- The delegate must not retain references to old resources after rotation.
- Headers/footers or delegate initialization may re-run on every file.
- Wrapper and delegate state must persist properly for restarts.

Never manually call `open` or `close` on the delegate from a processor or listener. Let the wrapper manage its lifecycle.

If a custom delegate manages multiple related resources, ensure `setResource` updates all of them and repeated `open`/`close` calls remain safe.

## 20. Transactions and failures during resource rotation

Chunk transactions wrap item processing, but filesystems do not automatically enlist in JDBC transactions. When a chunk spans a file boundary, the wrapper may write part of the chunk to the old resource and the rest to the new resource.

If a failure occurs mid-rotation:
- The old resource may already be flushed or closed.
- The new resource may already be created or opened.
- The chunk's database transaction may roll back.
- File output must recover consistently with the writer's checkpoint.

Never assume multiple files and `JobRepository` commit atomically together. Test rollbacks right at rollover boundaries, especially when delegates write to local files or external storage.

For critical exports, write to a `JobInstance`-scoped staging directory, verify total record counts and checksums, and publish the file set only after the Job succeeds. A manifest can tell downstream which files belong to the batch and confirm completeness.

## 21. Partitioning and multiple concurrent writers

`MultiResourceItemWriter` maintains a single index and current resource per instance. Do not share one writer instance across multiple concurrent threads or workers without explicit thread-safety guarantees.

When using partitioning:
- Each worker `StepExecution` should own a dedicated writer target.
- Resource prefixes should include both `JobInstance` ID and partition key.
- Workers must never overwrite each other's filenames.
- Once workers finish, an aggregation step or manifest can publish the combined file set.

For example:

~~~text
orders-instance-52/
  partition-0/
    orders-00001.csv
    orders-00002.csv
  partition-1/
    orders-00001.csv
    orders-00002.csv
~~~

Each partition's resource index can start fresh within its own namespace because directories or prefixes isolate workers. If multiple workers write to the same directory with identical index suffixes, files will collide and overwrite.

If the goal is capping file items per partition, set the limit on the worker writer. If the goal is capping items globally across the entire Job, design a merge or job-level output coordination strategy.

## 22. Filenames and consumption ordering

Downstream systems typically ingest multiple files via wildcards or manifests. Clearly specify file ordering and how a complete batch is detected.

Options:
- Zero-padded numeric suffixes for accurate lexicographical sorting.
- A manifest enumerating filenames in order.
- A dedicated directory per `JobInstance`.
- A marker file or `PUBLISHED` status written after all resources finish.

Never allow downstream consumers to read files while the Job is still writing. The last file may lack its footer or remain unclosed. A standard pattern is writing in a staging directory and moving/publishing the manifest only on completion.

If consumers rely on wildcards, guarantee the wildcard cannot match temporary files, stale files, or files from other `JobInstance` runs.

## 23. Controlling resource count and storage overhead

Splitting by item count can generate huge numbers of resources if the limit is too small. This impacts:
- File counts within a directory.
- Filesystem metadata overhead.
- Directory listing and scanning latency.
- Open/close operation counts.
- Transfer and storage operations.
- Downstream scheduling overhead per file.

Conversely, setting the limit too high makes files hard to transfer or exceeds consumer limits. Choose item counts based on:
- Receiving system constraints.
- Average and variance of item sizes.
- Throughput and per-file processing times.
- Number of parallel downstream workers/consumers.
- Storage file-count quotas.
- Retention policies.

Benchmark with production-like data. Do not pick limits based solely on average item size if outlier records carry unusually large payloads.

## 24. Testing MultiResourceItemWriter

Test both file splitting behavior and restartability.

Test scenarios:

| Scenario | What to verify |
|---|---|
| Small item count | Files roll over at the exact threshold |
| Item count divisible by limit | Exact number of resources created |
| Item count not divisible by limit | Final file holds the remainder |
| Chunk crossing a boundary | Items route to the right files |
| Chunk larger than limit | Multiple resources created within one write |
| Processor filters items | Only items reaching the writer count |
| Empty input | Zero-resource behavior matches contract |
| Headers/footers | Every file has proper framing |
| Suffix creator | Filenames are unique and sort cleanly |
| Resource directory | Created or validated per policy |
| Restart mid-resource | Resumes at exact index and item count |
| Restart after rollover | No duplicate or dropped items |
| Failure at rollover | Old and new resources recover cleanly |
| Pre-existing files | Overwrite and restart follow policy |
| Partitioning | Workers do not overwrite each other's files |
| Unicode and special characters | File contents encoded and escaped accurately |
| Disk full or I/O failure | Step fails cleanly with clear cleanup |

A useful restart integration test:
1. Launch the Job with fixed `JobParameters` and output directory.
2. Write across at least two resources.
3. Intentionally fail the Step after several committed chunks.
4. Capture `JobInstance` ID, resource index, and output files.
5. Restart the same `JobInstance`.
6. Verify the writer resumes the exact resource without generating random suffixes.
7. Read all files in order and assert total items, ordering, and business keys.
8. Verify zero missing or duplicated items.
9. Publish the file set only after validation succeeds.

Unit testing builders and suffix creators cannot replace integration tests backed by a real `JobRepository`.

## 25. Common pitfalls

**Confusing item count limits with file size limits.** A file can exceed byte caps even when its item count meets the limit.

**Confusing chunk size with item count limits.** Chunks can be smaller than, larger than, or span across resource boundaries.

**Delegate not implementing ResourceAwareItemWriterItemStream.** The wrapper cannot inject resources or manage lifecycle properly.

**Omitting a stable writer name.** State in `ExecutionContext` may fail to restore properly.

**Changing base resource or suffix creator on restart.** The writer may open a different file than the checkpointed one.

**Disabling saveState.** The wrapper does not save enough metadata to resume from the current resource.

**Not saving delegate state.** The delegate may fail to restore its write position within the current file.

**Sharing one writer instance across workers.** Index and current resource can race or overwrite.

**Assuming a chunk always fits inside one file.** A chunk can split right at the item count threshold.

**Assuming files and database commit atomically.** Filesystems do not automatically participate in JDBC transactions.

**Using non-unique suffixes.** Files may overwrite each other or become impossible to sort.

**Consumers reading files before closing.** Downstream may ingest incomplete files.

**Ignoring empty input.** Consumers might wait forever for a file the writer never created.

**Underestimating file counts.** Overly small limits can overwhelm directories and storage systems.

## 26. Workflow for splitting output by item count

When splitting output by record count, follow these steps:

1. Clarify whether the cap is item count or byte size.
2. Choose `MultiResourceItemWriter` if the requirement is per-resource item limits.
3. Select a delegate implementing `ResourceAwareItemWriterItemStream`.
4. Assign stable names to both wrapper and delegate.
5. Configure a deterministic base `Resource` and `ResourceSuffixCreator`.
6. Set `itemCountLimitPerResource` per downstream contract.
7. Enable `saveState` on wrapper and delegate when restarts are needed.
8. Wire the wrapper into the Step's `writer(...)` so it manages delegate lifecycle.
9. Keep output path, suffix, limit, and input order stable across restarts.
10. Never share a single writer instance across concurrent workers.
11. Use staging and manifests/publishing so consumers see only complete file sets.
12. Test mid-chunk rollover, trailing files, empty input, rollbacks, restarts, and partitioning.
13. Monitor file counts, items per file, byte sizes, and I/O errors in operations.

`MultiResourceItemWriter` separates multi-resource orchestration from per-item writing logic. `itemCountLimitPerResource` governs when files rotate; the delegate governs serialization; the suffix creator governs resource naming; and `ExecutionContext` enables restarts. By keeping these configurations stable and testing chunk/resource boundaries carefully, Spring Batch can export data across multiple files by item count while preserving order, checkpoints, and recoverability.

