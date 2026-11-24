# Reading multiple files in resource order

In Spring Batch, a batch job often receives data split across multiple files rather than a single file. For example, an upstream system exports one file per hour, each branch generates its own file, or a large dataset is split into parts such as `orders-0001.csv`, `orders-0002.csv`, `orders-0003.csv`. The job needs to read these files sequentially as one unified item stream.

`MultiResourceItemReader<T>` is the Spring Batch reader for reading multiple `Resource` items in order. It wraps a delegate reader, typically `FlatFileItemReader<T>`, and assigns each resource to the delegate in turn. When the delegate finishes reading one file, `MultiResourceItemReader` switches to the next resource; items returned to the step form a continuous stream.

The key principle of this topic is that **resource order must be explicitly deterministic**. The file order returned by a filesystem, wildcard resolver, or object storage should not be treated as business order. If processing order affects outcomes, configure a comparator or supply a resource list sorted according to a controlled manifest.

## How does MultiResourceItemReader work?

`MultiResourceItemReader<T>` resides in the `org.springframework.batch.item.file` package. It does not parse CSV or fixed-width data itself. It manages the resource list and delegates reading each resource to a `ResourceAwareItemReaderItemStream`.

Key components:

- `resources`: the list of files/resources to read.
- `delegate`: the reader that actually reads a single resource, such as `FlatFileItemReader`.
- `comparator`: the rule for sorting resources before reading.
- `strict`: specifies behavior when no resources are found.
- `saveState`: enables saving the current resource position and delegate state to support restart.

High-level reading flow:

```text
Resource[]
   |
   v
Sort by comparator
   |
   v
MultiResourceItemReader
   |
   +--> file-0001.csv --> delegate reads full file
   |
   +--> file-0002.csv --> delegate reads full file
   |
   +--> file-0003.csv --> delegate reads full file
   |
   v
One continuous item stream
   |
   v
Processor --> Writer
```

For example, suppose the first file has 100 items, the second has 250 items, and the third has 50 items. The reader returns 400 items in total in the selected resource order, excluding items filtered or skipped by step configuration.

`MultiResourceItemReader` reads sequentially. It does not automatically distribute files across multiple threads or create partitions. If you need parallel processing per file, a separate partitioning design is required.

## What is a Resource?

Spring uses the `Resource` abstraction to represent a data source. A resource can be a local file, a classpath resource, or a resource provided by another implementation.

For example:

```java
Resource first = new FileSystemResource("/batch/in/orders-0001.csv");
Resource second = new FileSystemResource("/batch/in/orders-0002.csv");
Resource template = new ClassPathResource("templates/order-header.csv");
```

For batch jobs reading files from a directory, `FileSystemResource` or `ResourcePatternResolver` is commonly used to find multiple files matching a pattern. `MultiResourceItemReader` accepts a `Resource[]` array.

Do not place an unreadable or non-existent resource into the list expecting the reader to silently skip it in all cases. Clearly define which files are mandatory, which are optional, and how to handle a resource disappearing between discovery and file opening.

## Basic configuration with FlatFileItemReader

A common setup uses `FlatFileItemReader` as the delegate to read each CSV file. Example model:

```java
public record OrderInput(
        String orderId,
        String customerId,
        BigDecimal amount) {
}
```

Declare a `LineMapper` for a single file:

```java
@Bean
LineMapper<OrderInput> orderLineMapper() {
    DefaultLineMapper<OrderInput> mapper = new DefaultLineMapper<>();

    DelimitedLineTokenizer tokenizer = new DelimitedLineTokenizer();
    tokenizer.setNames("orderId", "customerId", "amount");

    mapper.setLineTokenizer(tokenizer);
    mapper.setFieldSetMapper(fields -> new OrderInput(
            fields.readString("orderId"),
            fields.readString("customerId"),
            fields.readBigDecimal("amount")));

    return mapper;
}
```

The `FlatFileItemReader` delegate is created without binding a fixed file. `MultiResourceItemReader` sets the current resource on the delegate before opening it:

```java
@Bean
FlatFileItemReader<OrderInput> orderFileDelegate(
        LineMapper<OrderInput> orderLineMapper) throws Exception {

    FlatFileItemReader<OrderInput> delegate = new FlatFileItemReader<>();
    delegate.setName("orderFileDelegate");
    delegate.setLineMapper(orderLineMapper);
    delegate.setEncoding(StandardCharsets.UTF_8.name());
    delegate.setLinesToSkip(1);
    delegate.setSaveState(true);
    delegate.setStrict(true);
    delegate.afterPropertiesSet();
    return delegate;
}
```

In this example, each file has a header line, so `linesToSkip(1)` is applied when the delegate opens each resource. If only the first file has a header, do not apply this configuration mechanically; use a delegate or policy suited to the actual format.

## Finding resources by pattern

`PathMatchingResourcePatternResolver` can discover files using wildcards:

```java
ResourcePatternResolver resolver = new PathMatchingResourcePatternResolver();
Resource[] resources = resolver.getResources("file:/batch/in/orders-*.csv");
```

The pattern `file:/batch/in/orders-*.csv` locates matching resources in the directory. The result is a list of resources; do not rely on the resolver's return order to determine business ordering.

If the path comes from `JobParameters`, you can create the reader in step scope to resolve the list when the step begins:

```java
@Bean
@StepScope
MultiResourceItemReader<OrderInput> orderMultiReader(
        @Value("#{jobParameters['inputPattern']}") String inputPattern,
        LineMapper<OrderInput> orderLineMapper) throws Exception {

    ResourcePatternResolver resolver = new PathMatchingResourcePatternResolver();
    Resource[] resources = resolver.getResources(inputPattern);

    FlatFileItemReader<OrderInput> delegate = new FlatFileItemReader<>();
    delegate.setName("orderFileDelegate");
    delegate.setLineMapper(orderLineMapper);
    delegate.setEncoding(StandardCharsets.UTF_8.name());
    delegate.setLinesToSkip(1);
    delegate.setSaveState(true);
    delegate.setStrict(true);
    delegate.afterPropertiesSet();

    Comparator<String> filenameOrder =
            Comparator.nullsLast(Comparator.naturalOrder());
    Comparator<Resource> resourceOrder =
            Comparator.comparing(Resource::getFilename, filenameOrder);

    return new MultiResourceItemReaderBuilder<OrderInput>()
            .name("orderMultiReader")
            .resources(resources)
            .delegate(delegate)
            .comparator(resourceOrder)
            .strict(true)
            .saveState(true)
            .build();
}
```

`@StepScope` resolves the pattern when the step runs, which fits cases where the file list varies across launches. `jobParameters['inputPattern']` can be an identifying or non-identifying parameter depending on job design; if it defines the input set of a logical job, include it in the execution identity or persist an immutable manifest so restarts always use the exact same set of files.

Specific builder and API methods should match your Spring Batch version. In some configurations, you can instantiate `MultiResourceItemReader` directly and call `setResources`, `setDelegate`, `setComparator`, `setStrict`, and `setSaveState`; the property semantics remain the same.

## Defining resource order

`MultiResourceItemReader` supports a comparator for sorting resources. This is essential when filenames represent timestamps, sequences, or business ordering.

### Sorting by filename

Example files:

```text
orders-0001.csv
orders-0002.csv
orders-0003.csv
```

Filename comparator:

```java
Comparator<Resource> byFilename =
        Comparator.comparing(Resource::getFilename);
```

Zero-padded sequence numbers make lexicographical order match numeric order. If filenames are `orders-1.csv`, `orders-10.csv`, `orders-2.csv`, lexicographical sorting yields `1`, `10`, `2`, which differs from the desired numeric order.

With unpadded sequences, parse the number from the filename or derive the order from a manifest. Do not use a comparator based solely on `toString()` or description if those strings are not a stable contract.

### Sorting by date or sequence

If filenames look like `orders-20261115-001.csv`, you can extract the date and sequence for comparison. For example:

```java
Comparator<Resource> byBusinessSequence = Comparator.comparing(
        resource -> parseSequence(resource.getFilename()));
```

`parseSequence` is an application method that validates the filename format and returns a comparable type, such as a record containing a `LocalDate` and a sequence number. If a filename fails format validation, raise a clear error instead of returning a default value that misorders the file.

If business order lives in file metadata or a manifest, use that metadata as the source of truth. Filenames should only be used for ordering when the producer guarantees the corresponding naming convention.

### Sorting by manifest

For production pipelines, a manifest is usually more reliable than wildcards. A manifest can contain:

| Sequence | Resource | Checksum | Record count |
| ---: | --- | --- | ---: |
| 1 | `orders-a.csv` | `sha256:...` | 1200 |
| 2 | `orders-b.csv` | `sha256:...` | 950 |
| 3 | `orders-c.csv` | `sha256:...` | 1400 |

The application reads the manifest, validates each resource, and builds `Resource[]` in exact sequence order. This ensures the job knows precisely which files belong to a batch and detects missing, modified, or duplicate files.

Do not generate a new manifest with a different order during a restart of the same `JobInstance`. Keep the manifest ID/version stable and ensure manifest contents remain unchanged while the execution may still restart.

## Resource order vs. item order

`MultiResourceItemReader` reads the current resource completely before moving to the next one. Consequently, emitted item order is:

1. All items from the first resource in line order.
2. All items from the second resource.
3. Continuing through the final resource.

For example:

```text
orders-0001.csv: A-01, A-02, A-03
orders-0002.csv: B-01, B-02
orders-0003.csv: C-01, C-02, C-03

Reader emits:
A-01, A-02, A-03, B-01, B-02, C-01, C-02, C-03
```

The reader does not merge lines by timestamp, sort all items by a field, or interleave files. If global sorting is required after reading, you may need a staging database, external sort, or a dedicated processing step. Do not confuse resource order with global data order.

## One delegate for multiple files

`MultiResourceItemReader` reuses a single delegate to read each resource. Therefore, the files must generally share the same record structure or at least be compatible with the same `LineMapper`/parser.

For example, if all files share the header:

```csv
orderId,customerId,amount
O-1,C-1,100.00
O-2,C-2,250.00
```

the delegate can use a shared tokenizer and mapper. When moving to the next file, the reader reopens the delegate with the new resource.

If files have different schemas—for instance, file A has three columns while file B has five columns with different meanings—do not force a single mapper to read them all. Group resources by format, use separate steps, or implement a custom reader that selects a parser based on per-resource metadata.

## Headers in individual files

Note that the delegate is reopened for each resource. If `FlatFileItemReader` is configured with `linesToSkip(1)`, the header is skipped in every file, not just the first one.

For example:

```text
orders-0001.csv:
  orderId,amount       <- skipped
  O-1,100
  O-2,200

orders-0002.csv:
  orderId,amount       <- skipped when reopening delegate for next resource
  O-3,300
```

This works well when every file carries its own header. If only the first file has a header or headers vary between files, design explicit handling. You can use a custom delegate, a resource-aware reader, or a pre-processing normalization step before reading.

`skippedLinesCallback` can be used to inspect skipped header lines. If you need to verify that all files share the same header, the callback can validate the schema and throw an error when a header differs from expectations.

## Empty files and missing resources

Distinguish these situations:

- **No resources found:** the wildcard matches no files or the manifest is empty.
- **Resource exists but file is empty:** a 0-byte file.
- **File contains only a header:** the resource exists but has zero data records.
- **Resource disappears after discovery:** the file is deleted or moved before the reader opens it.
- **Unreadable resource:** permission denied or I/O error.

`MultiResourceItemReader`'s `strict` setting governs behavior when no resources exist. For jobs requiring mandatory input, enable strict to fail early. If having no files is valid, you can set strict to false and explicitly record that the job processed 0 items; do not let a job finish silently when business rules require data.

An empty file or header-only file is not equivalent to having no resources. The reader can open the file, reach EOF, and move to the next resource. If an empty file is a business error, add dedicated validation.

## MultiResourceItemReader and chunk processing

`MultiResourceItemReader` sits at the front of the pipeline. It delivers items one by one to the chunk step like any other reader:

```java
@Bean
Step importManyFilesStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderMultiReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importManyFilesStep", jobRepository)
            .<OrderInput, Order>chunk(200, transactionManager)
            .reader(orderMultiReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

A chunk can start near the end of one file and continue into the start of the next. For instance, if the first file has 50 items left and the chunk size is 200, the reader pulls 150 more items from the second file to complete the chunk. File boundaries are not automatically transaction or chunk boundaries.

If business requirements demand a separate commit after each file, `MultiResourceItemReader` inside a single chunk step does not enforce that automatically. You may need per-file partitioning/steps or custom orchestration to establish transaction boundaries per resource.

## Restart and ExecutionContext

`MultiResourceItemReader` supports restart via `ItemStream`. When `saveState(true)` is configured, the reader stores the current resource being read and the delegate's state in the step's `ExecutionContext`. On restart, it restores the current resource index and opens the delegate at the checkpointed position.

For reliable restarts, keep the following stable:

- The reader name of `MultiResourceItemReader`.
- The delegate reader name.
- Resource order and count.
- Contents of processed and unprocessed resources.
- Parser configuration, encoding, and header policy.
- Identifying `JobParameters` of the same `JobInstance`.

For example, suppose the first run has the list:

```text
index 0 -> orders-0001.csv
index 1 -> orders-0002.csv
index 2 -> orders-0003.csv
```

The step reads part of `orders-0002.csv` and checkpoints resource index 1 along with the delegate position. On restart, the reader must receive the exact same list and order. If a new file is prepended to the list, index 1 could point to a different resource, causing the reader to read the wrong file or miss data.

### Resource list must remain stable

This is the single most important rule for restarting multi-file jobs. A wildcard can return a different set of files on a subsequent run because:

- A producer added new files.
- Already-processed files were archived or deleted.
- Filenames changed.
- A file was overwritten with new contents.
- The comparator or sequence parsing rule changed.

Because checkpoints usually rely on resource index, an index is only meaningful if the resource list is unchanged. You can ensure this by:

1. Creating an immutable manifest for each batch and reusing the manifest ID on restart.
2. Claiming/moving files into an execution-specific directory before launch.
3. Persisting the resolved resource list in durable metadata and restoring that exact list.
4. Using checksums/versions to verify files were not altered.
5. Archiving or deleting files only after the job completes and no longer needs restartability.

Never re-run a wildcard against an `incoming` directory and feed the new results into a restarting execution if the file set can change.

### Reader and delegate names must be stable

`ItemStreamSupport` uses the component name to build keys in `ExecutionContext`. Keep reader and delegate names consistent across deployments while old executions might still restart. Renaming can prevent components from locating their saved state.

`saveState(true)` should be enabled on both the wrapper and the delegate when you need to restore both the resource index and the position within a file. If delegate state is disabled, the wrapper knows which file it is on, but the delegate does not know which record position inside that file to resume from.

Do not store open `Resource`, `InputStream`, or file handles in the context. State should contain small serializable data; actual resources are re-resolved from a stable manifest/path when the step opens.

## File changes between runs

Suppose `orders-0002.csv` was partially read and the job failed. If the producer appends rows to the file before restart, the delegate may resume over altered contents. The output might no longer reflect a consistent snapshot.

Therefore, batch input files should be immutable once published. Producers can write to a temporary name and rename atomically to the final name; consumers claim files and prevent producer edits. For files in object storage, store the object version ID or checksum.

If the source is unavoidably mutable, snapshot the data or copy files to an isolated staging area before the batch starts. Do not rely on file path alone to identify unchanged content.

## Error handling within a resource

When the delegate encounters an error reading a file, the step normally handles the exception according to its reader/skip/retry policy. `MultiResourceItemReader` does not automatically turn every error into skipping the file and continuing.

Distinguish between:

- Transient errors when opening a resource: may use bounded retries if the root cause is recoverable.
- Missing file or wrong permissions: usually a configuration or ingestion issue requiring investigation.
- Malformed records: handle via validation/skip policies if record boundaries can be determined safely.
- Truncated files or wrong encoding: generally fail/quarantine the file rather than skipping unchecked.

If a file fails midway, continuing to subsequent files can cause the batch to complete with incomplete data. Only implement skip-file behavior when business rules allow partial success and clear auditing of skipped files is recorded.

## Tracking the current resource

When operating multi-file jobs, logs should show which resource is currently being processed. `MultiResourceItemReader` maintains an internal resource index; if you need the filename in logs or audits, use a delegate, listener, or wrapper designed to observe the current resource, or enrich with manifest metadata.

Information worth recording:

- Job name and `JobExecution` ID.
- Step name and `StepExecution` ID.
- Manifest/batch ID.
- Resource path or resource ID.
- Sequence/resource index.
- Per-file record count if measurable.
- Start/end timestamps for each resource.
- Checksum/version and open/read errors.

Do not rely on private fields of `MultiResourceItemReader` to obtain the current resource. If you need a stable observation API, use a wrapper or your application's metadata store.

## Reading multiple files with different schemas

A single `MultiResourceItemReader` typically uses one delegate for all resources. Thus, it fits best when files share the same structure, encoding, header, and record format.

If different file types require different mappers, consider these options:

- Classify files upfront and run a separate step per format.
- Create multiple `MultiResourceItemReader` beans, one per resource group.
- Use a custom reader that selects a parser based on manifest/file metadata.
- Normalize files into a common staging schema before main reading.

Do not inspect the filename and arbitrarily swap `LineMapper` mid-stream while the reader is open without tightly controlling lifecycle and restart state. Format metadata should be determined before the step starts.

## Reading files in parallel

`MultiResourceItemReader` processes resources sequentially on a single reading stream. If you need higher throughput by reading multiple files in parallel, use partitioning: each partition receives a resource and runs its own reader.

```text
                 Master step
                      |
             Partition resources
             /        |        \
            v         v         v
        Worker 1   Worker 2   Worker 3
        file A     file B     file C
```

Spring Batch provides `MultiResourcePartitioner` in supported versions to create execution contexts per resource. The worker step uses a `@StepScope` reader that retrieves its partition's resource from `stepExecutionContext`.

How partitioning differs from `MultiResourceItemReader`:

| Reading approach | Characteristics |
| --- | --- |
| `MultiResourceItemReader` | One step reads multiple resources sequentially as a continuous stream |
| Resource partitioning | Each partition processes its own resource; can execute in parallel |

When partitioning, ensure the writer can accept concurrent writes, outputs do not contend, and final ordering is aggregated if required by business rules. Never share a single mutable reader across workers.

## Performance and memory

`MultiResourceItemReader` reads sequentially and typically holds only the current resource and required state in memory; it does not load the contents of all files into memory at once. However, wildcard resolution can build a large resource list, and metadata/checkpoints still need management.

To preserve performance:

- Use narrow patterns to avoid scanning unrelated files.
- Sort resources with a simple, deterministic comparator.
- Avoid reading entire files into a `List` before passing them to the reader.
- Choose a chunk size suited to the database, transaction duration, and item size.
- Monitor open time per file and processing time per resource.
- If the file count is very large, consider a manifest or partitioning instead of broad wildcards.
- Do not point multiple reader instances at the same resource without explicit claiming or partitioning.

Total processing time generally depends on total record count, file open overhead, parser, processor, writer, and I/O. Increasing the number of tiny files adds open/close overhead; merging files into huge ones can complicate restarts and retries. Choose file granularity based on real operational characteristics.

## Testing MultiResourceItemReader

You should test resource ordering, file boundaries, headers, empty resources, and restarts. Unit testing the comparator alone does not prove the reader switches resources correctly; test the actual reader against temporary files.

### Testing resource ordering

Create three files whose names differ from creation order:

```text
orders-0003.csv
orders-0001.csv
orders-0002.csv
```

Pass them into the reader with a filename comparator and verify items are emitted in `0001`, `0002`, `0003` order. Do not use creation order or filesystem listing order as expected values.

### Testing per-file headers

Create two files containing headers and data. Configure the delegate with `linesToSkip(1)`. Verify neither file's header is returned as an item and all data records appear.

### Testing empty and header-only files

Include an empty file and a header-only file in the list. Verify the reader advances to the next resource and returns valid items. If business rules forbid empty files, test the separate validation check.

### Testing missing resources

Use a pattern matching zero files. With strict mode enabled, verify the step fails with a clear error. With strict disabled, verify the 0-item outcome is recorded as required by business logic.

### Testing restart mid-resource

Create multiple files with many items. Run the step across several chunks, then trigger an error while the reader is partway through the second file. Restart with the same identifying parameters and the exact same resource list. Verify:

- The reader reopens the exact second resource.
- The delegate resumes at the exact record position.
- The first file is not re-read from the start if its checkpoint committed.
- Remaining files are read in proper order.
- Output contains no missing or duplicate items.

### Testing restart when the resource list changes

Simulate an initial run with `A`, `B`, `C`, checkpointed at index 1; before restarting, prepend `A0` or delete `A`. Verify the test detects that the resource set no longer matches the persisted manifest/version and prevents the job from continuing on the mutated list. Do not treat a successful run alone as sufficient; verify exact resource identity.

### Testing malformed resources

Place a file containing an invalid record in the middle of the list. Verify the job fails or skips per policy and auditing identifies the offending file. Do not let the job silently drop a file without metadata.

## Simple integration test example

A test can open the reader directly with an `ExecutionContext` to verify the item stream:

```java
@Test
void readsResourcesInConfiguredOrder() throws Exception {
    Resource[] resources = {
            new FileSystemResource(file3),
            new FileSystemResource(file1),
            new FileSystemResource(file2)
    };

    MultiResourceItemReader<String> reader =
            new MultiResourceItemReaderBuilder<String>()
                    .name("testMultiReader")
                    .resources(resources)
                    .delegate(testDelegate())
                    .comparator(Comparator.comparing(Resource::getFilename))
                    .saveState(true)
                    .build();

    reader.open(new ExecutionContext());
    try {
        assertEquals("A-1", reader.read());
        assertEquals("A-2", reader.read());
        assertEquals("B-1", reader.read());
        assertEquals("C-1", reader.read());
        assertNull(reader.read());
    } finally {
        reader.close();
    }
}
```

`testDelegate()` is a helper returning a reader matching the test fixtures; expected values assume files sort as `file1`, `file2`, `file3`. In production-grade tests, use temporary files and a real `FlatFileItemReader` to verify line mapping, encoding, and headers as well.

## Common pitfalls

### Relying on wildcard return order

Order can vary across filesystems, OSes, or runs. Configure an explicit comparator or use a manifest.

### Lexicographical sorting of numeric names

`file-10` can sort before `file-2`. Use zero-padding or a sequence-parsing comparator.

### Not keeping the resource list stable on restart

The checkpoint resource index may point to a different file if the list changes. Use an immutable manifest/snapshot and retain resources across the restart window.

### Using one delegate for files with different schemas

The mapper may misparse or fail. Group by format, use separate steps, or implement a custom reader.

### Forgetting that headers are skipped per file

The delegate reopens for each resource, so `linesToSkip(1)` applies to every file. Know which files actually have headers.

### Assuming chunks must end at file boundaries

A chunk can hold items from the end of one file and the start of the next. If per-file transactions are required, design separate steps or partitions.

### Assuming MultiResourceItemReader runs in parallel

The reader is sequential by default. Use partitioning if concurrent per-resource processing is needed.

### Confusing no files with empty files

Strict mode handles an empty resource list; an empty file is still a valid resource. Business validation must distinguish the two cases.

### Enabling saveState on the wrapper but disabling it on the delegate

The wrapper can restore the file index, but the delegate cannot restore its position within the file. Enable state saving on both when restartability is needed.

### Archiving files before job completion

A restart may fail to find the checkpointed resource. Archive only after execution finishes and according to retention policies.

### Sharing a reader across multiple threads

The reader holds resource/index state and must not be assumed thread-safe. Use a separate reader per partition or execution.

## Design principles

When reading multiple files in resource order, clarify:

1. Are files selected via wildcard, an explicit list, or a manifest?
2. Is business order based on filename, sequence, timestamp, or other metadata?
3. Is the comparator deterministic, stable, and safe against malformed filenames?
4. Do all files share the same encoding, schema, header, and record format?
5. Is the delegate properly reopened for each resource and skipping headers accurately?
6. How are missing resources, empty files, and unreadable files handled differently?
7. Are the resource list and contents immutable throughout the restart window?
8. Do the wrapper and delegate have stable `saveState` settings and names?
9. Can chunks span file boundaries, or do business rules require per-file commits?
10. Should reading be sequential or partitioned per resource for parallel execution?
11. Do logs and metrics capture the current file, sequence, and errors?
12. Do integration tests cover ordering, headers, empty files, missing resources, restarts, and list mutations?

For files sharing a structure that need sequential processing, `MultiResourceItemReader` paired with a `FlatFileItemReader` delegate is a straightforward choice. Set an explicit comparator, use a manifest or snapshot to keep ordering stable, and enable state on both wrapper and delegate when restart is required. If per-file transactions or parallel processing are needed, consider partitioning. Always keep inputs immutable and archive only after job completion so checkpoints resume on the right resource.

## Remember

`MultiResourceItemReader<T>` reads multiple `Resource` objects sequentially using a delegate reader, typically `FlatFileItemReader`. It produces a continuous item stream: reading one file completely before moving to the next. Configure it using `resources`, `delegate`, `comparator`, `strict`, and `saveState`. Never rely on wildcard/filesystem order; sort explicitly by filename, sequence, or manifest. The delegate is reopened for each file, so `linesToSkip(1)` applies to every file. The reader operates sequentially and does not automatically partition or commit per file; chunks can cross resource boundaries. For restartability, keep reader/delegate names, resource order, and resource contents stable because checkpoints rely on the resource index alongside delegate state. Use immutable manifests and inputs, test restarts thoroughly, and archive files only after job completion.
