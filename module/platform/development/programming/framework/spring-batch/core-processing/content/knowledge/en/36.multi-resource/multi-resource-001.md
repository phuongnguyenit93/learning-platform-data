# MultiResourceItemReader

In Spring Batch, `MultiResourceItemReader<T>` is used to read data from multiple resources under a single item contract. Instead of creating a separate step for each file, the reader manages a list of files, passes each file sequentially to a delegate reader, and returns items as if they came from a single continuous data stream.

For example, each day the system receives multiple `customers-*.csv` files. All files share the same column structure and must be imported by one job. `MultiResourceItemReader` can iterate through the resource list, use the same `FlatFileItemReader` to read each file, and pass items continuously to the step's processor and writer.

The critical point is that the reader must maintain a stable resource order and properly manage the delegate's lifecycle. When a job restarts, Spring Batch needs to know which file it is currently on and how far the delegate has read within that file. If the file list changes or file contents are replaced, the checkpoint may point to different data than in the initial run.

## 1. What problem does MultiResourceItemReader solve?

Suppose input is split across multiple files:

```text
input/
  customers-001.csv
  customers-002.csv
  customers-003.csv
```

Each file contains a subset of customer data and shares the same format:

```text
customer_id,name,email
C001,Nguyen An,an@example.com
C002,Tran Binh,binh@example.com
```

Without a multi-resource reader, the application might have to open each file manually, create separate readers, and coordinate file transitions. That increases boilerplate code for resource management, checkpointing, and handling end-of-file transitions.

`MultiResourceItemReader` handles this coordination:

```text
              Resource[]
                  |
                  v
        MultiResourceItemReader
                  |
          +-------+-------+
          |               |
          v               v
     Resource 1       Delegate reader
          |               |
          +--------------> read items
                          |
                    EOF of file 1
                          |
                          v
                    Resource 2
                          |
                          v
                    Delegate reader
                          |
                         ...
                          |
                          v
                 EOF of all resources
                          |
                          v
                    return null
```

For the downstream step, items from the first file and the second file are all read through the same `ItemReader<T>`. The processor and writer do not need to know which resource an item came from, unless the application needs to retain source metadata for auditing.

## 2. Key components

`MultiResourceItemReader<T>` coordinates an array of `Resource` objects with a delegate capable of reading each individual resource.

| Component | Role |
|---|---|
| `Resource[]` | List of files or resources to read. |
| `MultiResourceItemReader<T>` | Coordinates resource order and transitions from one resource to the next. |
| Delegate reader | Reads items from the current resource, for example `FlatFileItemReader<T>`. |
| `ResourceAwareItemReaderItemStream<T>` | Contract for a delegate to receive a resource via `setResource(...)` and support the stream lifecycle. |
| `ExecutionContext` | Stores the current resource index and the delegate's read position for restart. |

The delegate is typically `FlatFileItemReader`, though another reader can be used provided it fulfills the appropriate resource-aware contract. For instance, an XML reader or a custom reader can be used if it can open the assigned resource and save the necessary state.

`MultiResourceItemReader` does not parse CSV, XML, or JSON itself. It only coordinates the resource list; record parsing belongs to the delegate.

## 3. Configuration with MultiResourceItemReaderBuilder

The builder makes reader configuration clear:

```java
@Bean
MultiResourceItemReader<Customer> customerMultiReader(
        Resource[] customerResources,
        FlatFileItemReader<Customer> customerFileDelegate) {

    return new MultiResourceItemReaderBuilder<Customer>()
            .name("customerMultiReader")
            .resources(customerResources)
            .delegate(customerFileDelegate)
            .saveState(true)
            .strict(true)
            .build();
}
```

Key configuration options:

- `name(...)`: a stable name for the multi-resource reader, used to generate keys in `ExecutionContext`.
- `resources(...)`: the list of resources to read.
- `delegate(...)`: the reader that reads one resource at a time.
- `saveState(true)`: saves the reader's state to support restart.
- `strict(true)`: throws an error when no resources are found according to strict configuration.

The builder API may vary slightly across Spring Batch versions. For versions that provide `MultiResourceItemReaderBuilder`, use the builder from your running dependency version.

## 4. Configuring the FlatFileItemReader delegate

The delegate needs to know how to parse a single file. It does not need to know the full list of files because `MultiResourceItemReader` supplies the current resource.

```java
@Bean
FlatFileItemReader<Customer> customerFileDelegate(
        LineMapper<Customer> customerLineMapper) {

    return new FlatFileItemReaderBuilder<Customer>()
            .name("customerFileDelegate")
            .lineMapper(customerLineMapper)
            .linesToSkip(1)
            .saveState(true)
            .build();
}
```

The delegate does not declare `.resource(...)` in this example because the resource is set dynamically via `setResource(...)` when the multi-resource reader moves to the next file. The delegate still requires a stable name and its own state so it can restore the read position within the current resource.

If every file has an identical header line, `linesToSkip(1)` is applied each time the delegate is opened for a resource. If only the first file has a header while subsequent files do not, a different strategy is needed to handle headers per resource; you cannot simply rely on a single `linesToSkip` configuration for both formats.

## 5. Building the Resource list from a file pattern

Spring's `ResourcePatternResolver` can discover files using a wildcard:

```java
@Bean
Resource[] customerResources(
        ResourcePatternResolver resourcePatternResolver) throws IOException {

    return resourcePatternResolver.getResources(
            "file:./input/customers-*.csv");
}
```

The pattern `file:./input/customers-*.csv` finds matching files in the input directory relative to the application's working directory. `classpath*:` can be used when resources reside on the classpath, though for input files that vary per batch run, a filesystem or object storage is usually more appropriate.

If the path comes from `JobParameters`, the resource list can be constructed when the step starts:

```java
@Bean
@StepScope
MultiResourceItemReader<Customer> customerMultiReader(
        @Value("#{jobParameters['inputPattern']}") String inputPattern,
        ResourcePatternResolver resolver,
        FlatFileItemReader<Customer> customerFileDelegate) throws IOException {

    Resource[] resources = resolver.getResources(inputPattern);

    return new MultiResourceItemReaderBuilder<Customer>()
            .name("customerMultiReader")
            .resources(resources)
            .delegate(customerFileDelegate)
            .saveState(true)
            .strict(true)
            .build();
}
```

`@StepScope` allows retrieving the pattern from `JobParameters`. You must validate the pattern and restrict the directories the application is allowed to read. Never accept an arbitrary pattern from an untrusted source and allow it to access any path on the server.

## 6. Resource order must be deterministic

File reading order can affect results if the data has business ordering, if the same entity appears across multiple files, or if a restart needs to return to the exact same resource.

Do not rely on arbitrary ordering returned by the filesystem or resource resolver. Sort explicitly using a comparator:

```java
Comparator<Resource> resourceComparator = Comparator.comparing(
        resource -> resource.getFilename() == null
                ? ""
                : resource.getFilename());

return new MultiResourceItemReaderBuilder<Customer>()
        .name("customerMultiReader")
        .resources(resources)
        .delegate(customerFileDelegate)
        .comparator(resourceComparator)
        .saveState(true)
        .build();
```

A filename comparator works well if filenames contain zero-padded sequence numbers:

```text
customers-0001.csv
customers-0002.csv
customers-0010.csv
```

If filenames are `customers-1.csv`, `customers-2.csv`, `customers-10.csv`, lexicographical ordering puts `10` before `2`. When numeric ordering is required, parse the sequence from the filename or use a zero-padded naming convention.

For example, a comparator based on date or sequence should fail with a clear error on malformed filenames. Do not silently place unparseable files at an arbitrary position.

## 7. Example comparator by sequence

Suppose filenames follow the format `customers-<number>.csv`:

```java
private int sequenceOf(Resource resource) {
    String filename = Objects.requireNonNull(resource.getFilename());
    Matcher matcher = Pattern.compile("customers-(\\d+)\\.csv")
            .matcher(filename);

    if (!matcher.matches()) {
        throw new IllegalArgumentException(
                "Unexpected customer file name: " + filename);
    }

    return Integer.parseInt(matcher.group(1));
}

Comparator<Resource> bySequence = Comparator.comparingInt(this::sequenceOf);
```

Then pass `bySequence` to `.comparator(bySequence)`. The comparator must produce consistent results between the initial run and a restart. If files are renamed or sequences change, the resource list may sort differently and the checkpoint will no longer point to the same logical file.

## 8. Missing resources and strict mode

`MultiResourceItemReader`'s `strict` flag controls behavior when the resource list is empty. When strict is enabled, the reader fails if there are no resources to read. When strict is disabled, the reader can finish with no items if the resource list is empty.

For example:

```java
return new MultiResourceItemReaderBuilder<Customer>()
        .name("customerMultiReader")
        .resources(resources)
        .delegate(customerFileDelegate)
        .strict(true)
        .build();
```

Use strict mode when the job is launched under the assumption that input files must exist. If no files are present, that may indicate an upstream failure or a scheduler running at the wrong time.

If having no files is a valid scenario, you can set `strict(false)` and add business logic to distinguish "no files" from "files exist but contain no records". Both cases produce `readCount == 0`, but their root causes and reporting may differ.

Do not confuse the multi-resource reader's `strict` flag with `FlatFileItemReader`'s `strict` flag. One checks the resource list; the other checks the resource opened by the delegate. Also distinguish a missing-file error from a file that exists but cannot be read due to permissions or I/O issues.

## 9. Delegate is reopened for each resource

When moving to the next resource, the multi-resource reader passes the new resource to the delegate and manages the reading lifecycle for that resource. Therefore, the delegate must be designed to open, read, close, and reopen multiple times within the same step execution.

With `FlatFileItemReader`, each time a new resource is opened:

- The current resource is replaced with the next file.
- The header is skipped according to the delegate's configuration if each file has a header.
- Line numbering and file state start fresh for that resource.
- When the delegate reaches EOF, the multi-resource reader advances to the next resource.

Do not configure the delegate to hold global state unrelated to the current resource, such as a record counter that never resets when opening a new file, unless that behavior is intentional. If you need a batch-wide total record count, use a counter on the step or a listener rather than embedding it into the delegate's internal state.

## 10. Reading multiple CSV files with the same structure

A more complete configuration example:

```java
@Bean
LineMapper<Customer> customerLineMapper() {
    DelimitedLineTokenizer tokenizer = new DelimitedLineTokenizer();
    tokenizer.setDelimiter(",");
    tokenizer.setNames("customerId", "name", "email");

    DefaultLineMapper<Customer> mapper = new DefaultLineMapper<>();
    mapper.setLineTokenizer(tokenizer);
    mapper.setFieldSetMapper(fields -> new Customer(
            fields.readString("customerId"),
            fields.readString("name"),
            fields.readString("email")));
    return mapper;
}

@Bean
FlatFileItemReader<Customer> customerFileDelegate(
        LineMapper<Customer> customerLineMapper) {
    return new FlatFileItemReaderBuilder<Customer>()
            .name("customerFileDelegate")
            .encoding("UTF-8")
            .linesToSkip(1)
            .lineMapper(customerLineMapper)
            .saveState(true)
            .build();
}

@Bean
MultiResourceItemReader<Customer> customerMultiReader(
        ResourcePatternResolver resolver,
        FlatFileItemReader<Customer> customerFileDelegate) throws IOException {

    Resource[] resources = resolver.getResources("file:./input/customers-*.csv");

    return new MultiResourceItemReaderBuilder<Customer>()
            .name("customerMultiReader")
            .resources(resources)
            .delegate(customerFileDelegate)
            .comparator(Comparator.comparing(Resource::getFilename))
            .strict(true)
            .saveState(true)
            .build();
}
```

This example assumes all files share the same delimiter, column order, encoding, and header. If a file has a different structure, do not feed it into the same delegate merely because its filename matches the wildcard. Separate the resource pattern or create distinct readers/steps per format.

## 11. Integrating MultiResourceItemReader into a chunk step

Once the multi-resource reader is defined, the step uses it like a regular `ItemReader`:

```java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        MultiResourceItemReader<Customer> customerMultiReader,
        ItemProcessor<Customer, Customer> customerProcessor,
        ItemWriter<Customer> customerWriter) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<Customer, Customer>chunk(500, transactionManager)
            .reader(customerMultiReader)
            .processor(customerProcessor)
            .writer(customerWriter)
            .build();
}
```

A chunk can start at the end of one file and continue at the beginning of the next file. For example, if the first file has 100 items remaining and the chunk size is 500, the chunk can contain the last 100 items of the first file along with the first 400 items of the second file.

The processor and writer do not need to be aware of file boundaries. If business logic requires the source filename for each item, include that metadata in the item or create a wrapper holding both the payload and the source.

## 12. Preserving the source filename in items

`MultiResourceItemReader` returns the items produced by the delegate. If you need to audit which file a record came from, you can use a wrapper or a source field on the model.

For example:

```java
public record ImportedCustomer(
        Customer customer,
        String sourceFile) {
}
```

One implementation approach is to use a custom delegate or mapper that is aware of the current resource and attaches the filename to the item. With `FlatFileItemReader`, you can use `ResourceAware` on the mapper or a component configured as resource-aware, provided you ensure the resource is updated whenever the delegate switches files.

An illustrative resource-aware mapper example:

```java
public class CustomerLineMapper
        implements LineMapper<ImportedCustomer>, ResourceAware {

    private Resource resource;

    @Override
    public void setResource(Resource resource) {
        this.resource = resource;
    }

    @Override
    public ImportedCustomer mapLine(String line, int lineNumber) throws Exception {
        String[] fields = line.split(",", -1);
        Customer customer = new Customer(fields[0], fields[1], fields[2]);
        return new ImportedCustomer(customer, resource.getFilename());
    }
}
```

The example needs to be adapted to your specific configuration so the mapper receives the resource from the delegate. If you cannot guarantee that the mapper is updated on every resource switch, write a resource-aware delegate or apply `ResourceAware` on a component invoked directly by the framework.

Another approach is to log the source file when starting each resource or write a separate batch manifest. Never infer the filename from an item ID unless a guaranteed business rule enforces it.

## 13. Files with headers and differing headers

If every file has the same single header line, the delegate can use:

```java
.linesToSkip(1)
```

Because the delegate is reopened for each resource, the first line of every file is skipped.

If only the first file has a header or headers differ across files, you must handle headers per resource. Some options include:

- Using `skippedLinesCallback` to validate each file's header.
- Creating a custom delegate that reads and validates the header before parsing records.
- Grouping files by header type and using separate readers/steps.
- Using a normalization step to unify files into the same schema before importing.

Callback example:

```java
reader.setSkippedLinesCallback(header -> {
    if (!header.equals("customer_id,name,email")) {
        throw new IllegalStateException("Unexpected CSV header: " + header);
    }
});
```

The callback must be configured on the `FlatFileItemReader` delegate. If a header is invalid, the step should fail or route the file to a rejected path per your workflow. Do not blindly skip arbitrary headers without verification, because columns might be reordered.

## 14. Resource ordering and order-dependent data

If files contain data partitions with ordering relationships, such as sequential delta files, ensure the comparator reflects the business order.

For example:

```text
delta-0001.csv  -> create customer
delta-0002.csv  -> update customer
delta-0003.csv  -> cancel customer
```

Reading in the wrong order can leave the final state incorrect. The comparator should be tested against a representative set of filenames, including single-digit numbers, multi-digit numbers, dates, and invalid filenames.

Even when there is no ordering dependency, deterministic ordering should still be enforced so restarts, logs, and audits are reproducible. The order does not strictly have to be chronological; it simply needs to remain consistent with data rules.

## 15. Restart and checkpointing in MultiResourceItemReader

`MultiResourceItemReader` is an `ItemStreamReader`. When `saveState(true)` is set, it persists the information needed to resume at the current resource. The delegate must also support `ItemStream` and save its state if you want to restore the position within a file.

For example:

```text
Resources in order:
  0: customers-001.csv
  1: customers-002.csv
  2: customers-003.csv

First run:
  file 0 -> read completely
  file 1 -> read up to record 350
  chunk commit
  file 1 -> error in next chunk

Restart:
  restore resource index = 1
  delegate opens customers-002.csv
  restore appropriate read position
  resume uncommitted portion
```

For restart to work properly:

- `MultiResourceItemReader` has a stable name.
- The delegate has a stable name and `saveState(true)`.
- The exact same resource list is produced in the exact same order.
- Files are not renamed, deleted, or modified between runs.
- Identifying `JobParameters` point to the same `JobInstance`.
- No other execution is concurrently processing the same `JobInstance`.

If `saveState(false)` is used, the reader does not save default checkpoints; a restart may re-read from the beginning or require a custom state management mechanism. Only disable state saving when the job does not need restartability or the application has a tested alternative.

## 16. Why the resource list must be immutable on restart

The multi-resource reader's checkpoint depends on the index in the resource list. Suppose the initial run has:

```text
index 0 -> A.csv
index 1 -> B.csv
index 2 -> C.csv
```

After a failure, if file A is deleted and the new list becomes:

```text
index 0 -> B.csv
index 1 -> C.csv
```

the prior checkpoint `index 1` previously pointed to B, but now points to C. The reader could resume on the wrong resource or fail to restore state as intended.

Similarly, if a new file is added at the beginning of the list, the old index could point to a different file. Therefore, for the same `JobInstance`:

- Create a fixed input manifest.
- Persist the file list or batch reference when the job starts.
- Do not add, remove, or rename files while the job may still be restarted.
- Optionally store checksums, sizes, or last-modified timestamps to detect modified files.
- If the input set changes, create a new `JobInstance` according to business rules.

A good pattern is for the scheduler to move files into an immutable batch directory, generate a manifest, and only then launch the job. Newly arriving files go into a subsequent batch.

## 17. Reader names and ExecutionContext keys

Spring Batch uses stream names to construct keys for storing state in `ExecutionContext`. Therefore, the names of `MultiResourceItemReader` and its delegate must remain stable across the initial run and restarts.

For example:

```java
new MultiResourceItemReaderBuilder<Customer>()
        .name("customerMultiReader")
        .resources(resources)
        .delegate(customerFileDelegate)
        .saveState(true)
        .build();
```

Delegate:

```java
new FlatFileItemReaderBuilder<Customer>()
        .name("customerFileDelegate")
        .lineMapper(customerLineMapper)
        .saveState(true)
        .build();
```

Do not change these names while older `JobInstance` executions might still be restarted. Changing a name prevents old keys from being found, causing the reader to start from a different position.

If there are multiple readers or delegates within the same step, each stream needs a distinct name to avoid key collisions. Do not share the same delegate instance concurrently across two multi-resource readers.

## 18. Multiple file types and multiple delegates

`MultiResourceItemReader` generally assumes resources share the same format because it uses a single delegate reader for all files. If CSV, XML, and JSON files sit in the same directory, do not feed them all into one reader hoping the delegate will auto-detect formats.

Ways to handle this:

- Use a separate pattern per file type with a corresponding step.
- Segregate files by type before launching the job.
- Use a custom resource-aware delegate that determines the format from metadata and routes to the appropriate parser.
- Normalize all files into a common format in an upstream step.

If formats vary by file, a custom delegate must manage separate lifecycles and checkpoints per resource. Complexity is significantly higher compared to using a single uniform delegate.

## 19. MultiResourceItemReader with XML or JSON

The multi-resource reader is not limited to CSV. You can use an appropriate resource-aware XML or JSON delegate reader as long as the delegate accepts dynamic resources and manages state properly.

Conceptual example:

```text
MultiResourceItemReader<Order>
       |
       +--> XML delegate reads orders-001.xml
       |
       +--> XML delegate reads orders-002.xml
       |
       +--> XML delegate reads orders-003.xml
```

An XML delegate can use `StaxEventItemReader` if the API/version supports dynamic resource configuration through the required contract. Likewise, a JSON delegate must support reading items sequentially from the current resource and saving state.

Not every reader implements `ResourceAwareItemReaderItemStream`. If a delegate cannot receive new resources via `setResource`, it cannot be used directly in the standard way. Always check the specific reader's interfaces and lifecycle before configuring it.

## 20. Handling errors in a single resource

If a file fails during reading, the delegate may throw an exception. The step then applies its configured retry or skip policy.

Common scenarios:

| Error | Usually appropriate behavior |
|---|---|
| File missing after manifest creation | Step fails; the input set has changed. |
| Permission denied reading file | Step fails, or retry transient I/O errors if justified. |
| Incorrect header | Reject file or fail step; do not continue parsing with the old mapping. |
| One malformed CSV line | Can skip the record if the parser continues safely and business rules permit. |
| Corrupted encoding or overall structure | Usually fail step and handle the file upstream. |
| Empty file | Can accept or reject depending on the input contract. |

Do not configure overly broad skip rules that allow the job to ignore an entire broken file and still report completion. If a file is rejected, clearly record the filename, reason, and expected affected record count.

## 21. Empty files and resources with zero items

A resource may exist yet contain no records. The delegate will return `null` on the very first read of that resource; the multi-resource reader can close the delegate and move on to the next resource.

This differs from an empty resource list:

- Empty resource list: no files were selected; the multi-resource reader's `strict` setting determines whether an error is raised.
- Resource list containing an empty file: the file exists but has no items; the delegate hits EOF immediately.
- All files are empty: the step may complete with `readCount == 0`.

If every file is required to have at least one record, per-resource validation is necessary. Checking only the aggregate `StepExecution.readCount` cannot identify which file was empty when multiple files are processed together. You can record item counts per resource or run a manifest/metadata check before reading.

## 22. MultiResourceItemReader and headers/footers

Headers and footers normally belong to individual files rather than the combined stream as a whole. If every file has a header, a `FlatFileItemReader` delegate with `linesToSkip(1)` skips the header when opening each resource.

If the output is a single consolidated file, the writer typically writes only one header for that output. Do not confuse per-input-file headers with the output file's header.

If each input file has its own header containing a business date or source system, you may need to read and retain that metadata. `skippedLinesCallback` can inspect the header, though it does not automatically emit headers as items. If header metadata must be attached to every item, use a custom delegate/reader that retains the current resource's metadata and attaches it to wrapper items.

## 23. Multiple files and chunk boundaries

Chunk boundaries do not necessarily align with file boundaries. For example:

```text
File A: 120 records
File B: 180 records
File C: 90 records
Chunk size: 200

Chunk 1: 120 records from A + first 80 records of B
Chunk 2: remaining 100 records of B + 90 records from C
```

This matters when the processor or writer needs to know the source file, or when an entire file must be processed as an atomic unit. `MultiResourceItemReader` does not create a separate transaction per file. Transaction boundaries still follow the step's chunk configuration.

If the business requirement is "each file must commit or rollback in full", consider running each file as a separate partition/step or launching a child job per resource. You cannot assume chunk processing will automatically roll back all records of a file when a chunk near the end of that file fails.

## 24. MultiResourceItemReader vs. partitioning

Both approaches process multiple files, but they serve different purposes:

| Criterion | `MultiResourceItemReader` | Resource-based partitioning |
|---|---|---|
| Reading model | One step reads files sequentially via one delegate. | Multiple worker steps, each receiving one resource or group of resources. |
| Concurrency | Typically sequential within a single reader instance. | Can execute multiple partitions concurrently. |
| Checkpointing | Tracks current resource and delegate state. | Independent state per worker/partition. |
| Ordering | A single deterministic resource order is enforced. | Completion order across partitions may vary. |
| Best suited for | Multiple files of the same format processed sequentially. | Independent files that can run in parallel and require scaling. |
| Complexity | Lower, simpler configuration. | Requires partitioner, worker step, concurrency, and output coordination. |

If files can be processed independently and processing takes a long time, partitioning can increase throughput. If processing order matters or files depend on each other, sequential reading with `MultiResourceItemReader` is usually easier to control.

## 25. MultiResourceItemReader is not thread-safe

A `MultiResourceItemReader` maintains mutable state for the current resource index and current delegate. You should not allow multiple threads to call the same reader instance concurrently unless specifically designed and synchronized for thread safety.

If parallel processing is needed:

- Use partitioning with a dedicated reader instance per worker.
- Split the resource list into independent groups.
- Ensure each worker has its own `ExecutionContext` and output target.
- Do not share a delegate with mutable state across multiple workers.
- Define output ordering and how results will be aggregated.

Simply synchronizing `read()` does not solve every problem. The delegate must also be thread-safe, resources must not suffer concurrent read/write conflicts across workers, and checkpoints must remain isolated.

## 26. Testing resource ordering

Test the comparator independently using representative filenames:

```java
@Test
void sortsResourcesByNumericSequence() {
    Resource file10 = new FileSystemResource("customers-10.csv");
    Resource file2 = new FileSystemResource("customers-2.csv");
    Resource file1 = new FileSystemResource("customers-1.csv");

    List<Resource> resources = new ArrayList<>(
            List.of(file10, file2, file1));
    resources.sort(bySequence);

    assertThat(resources)
            .extracting(Resource::getFilename)
            .containsExactly(
                    "customers-1.csv",
                    "customers-2.csv",
                    "customers-10.csv");
}
```

Tests should include invalid filenames, duplicate sequences, and resources without filenames if the application might encounter them. The comparator must have a clear policy when inputs violate naming conventions.

## 27. Basic MultiResourceItemReader testing

An integration or unit test can create two temporary resources, configure the delegate, and verify items are returned in resource order:

```java
@Test
void readsItemsFromAllResourcesInConfiguredOrder() throws Exception {
    Resource first = new ByteArrayResource(
            "C001,Nguyen An\nC002,Tran Binh\n".getBytes(UTF_8)) {
        @Override
        public String getFilename() {
            return "customers-001.csv";
        }
    };

    Resource second = new ByteArrayResource(
            "C003,Le Chi\n".getBytes(UTF_8)) {
        @Override
        public String getFilename() {
            return "customers-002.csv";
        }
    };

    FlatFileItemReader<Customer> delegate = new FlatFileItemReaderBuilder<Customer>()
            .name("customerDelegate")
            .lineMapper(customerLineMapper)
            .saveState(true)
            .build();

    MultiResourceItemReader<Customer> reader =
            new MultiResourceItemReaderBuilder<Customer>()
                    .name("customerMultiReader")
                    .resources(second, first)
                    .delegate(delegate)
                    .comparator(Comparator.comparing(Resource::getFilename))
                    .saveState(true)
                    .build();

    reader.open(new ExecutionContext());
    try {
        assertThat(reader.read().customerId()).isEqualTo("C001");
        assertThat(reader.read().customerId()).isEqualTo("C002");
        assertThat(reader.read().customerId()).isEqualTo("C003");
        assertThat(reader.read()).isNull();
    } finally {
        reader.close();
    }
}
```

This test demonstrates resource ordering and reading across file boundaries. Adjust constructors/encoding and `LineMapper` for your specific Spring Batch version. If the delegate skips a header, create fixtures with headers and configure `linesToSkip` accordingly.

## 28. Testing strict mode and empty resource lists

Write two distinct tests:

- When the resource list is empty and strict is enabled, the reader fails according to the version's contract.
- When the resource list is empty and strict is disabled, the reader finishes with no items.

In addition, test missing resources, unreadable resources, and existing-but-empty resources. These cases are not identical and may raise exceptions at different stages.

In integration tests, inspect both the status and exit description of the step/job to confirm whether an error came from a missing file, read permissions, or the parser.

## 29. Testing restart across multiple resources

Restartability is the most critical aspect of a multi-resource reader. Tests should create multiple files with enough records that chunk boundaries span files:

1. Create files A, B, and C in deterministic order.
2. Launch the job with fixed identifying parameters.
3. Have the reader read all of A and part of B.
4. Fail the step after several chunks have committed.
5. Verify `ExecutionContext` stores the resource index and delegate state.
6. Restart the same `JobInstance` with the exact same resource list, comparator, reader name, and delegate name.
7. Verify the reader resumes at the exact position in B.
8. Verify committed items are neither skipped nor duplicated.
9. Verify C is read after B finishes.

Do not check only that the job status is `COMPLETED`. Compare the set of output business keys against the expected input set and verify the write count for each key.

## 30. Common pitfalls

| Symptom | Common cause | Remedy |
|---|---|---|
| No files found | Wrong pattern or unexpected working directory. | Log the pattern, validate resource count, and use appropriate strict mode. |
| Files read in wrong order | Resource resolver/filesystem returned a different order or comparator is flawed. | Configure a deterministic comparator and test with real filenames. |
| Restart starts at a different file | Resource list changed order, or files were added/removed/renamed. | Keep the manifest/resource set immutable for the `JobInstance`. |
| Restart re-reads many items | Delegate did not save state or `saveState` was disabled. | Enable state saving for both outer reader and delegate, keeping names stable. |
| Headers read as data | Delegate did not skip headers or only some files have headers. | Configure `linesToSkip`/header callbacks based on each resource's format. |
| One malformed file fails the whole step | Shared delegate mapping applied to a file with a different structure. | Separate resources by format or use specialized delegates. |
| One empty file stops the step early | Custom delegate returns null properly at EOF, but a custom wrapper treats it as global EOF. | Use `MultiResourceItemReader` or handle resource transitions per contract. |
| Step succeeds but files are missing | Strict mode disabled or pattern failed to select all resources. | Validate the manifest and expected resource count before launch. |
| File read twice | Duplicate resources in the list or a new `JobInstance` reused old inputs. | Deduplicate the manifest and define clear batch identity. |
| Delegate fails to reopen | Delegate retains stale state/resource or is not resource-aware. | Use a delegate supporting `ResourceAwareItemReaderItemStream` with proper open/close lifecycle. |
| Duplicate writes on restart | Writer is non-idempotent or writer state was not saved. | Save writer checkpoints and design output around batch/resource identity. |
| Poor performance | Too many small files, frequent open/close overhead, or slow I/O. | Measure per resource, merge small files if appropriate, or partition independently. |

## 31. Designing a multi-resource reading job

When building a job that reads multiple files, determine:

1. **Resource pattern:** which files belong to the current batch, and could the pattern accidentally match unwanted files?
2. **Manifest:** is a fixed resource list persisted for the `JobInstance`?
3. **Format:** do all files share the same schema, encoding, header, and delimiter?
4. **Ordering:** is reading ordered by filename, sequence, or business date?
5. **Delegate:** which reader parses a single resource, and does it support resource-aware/`ItemStream`?
6. **Strictness:** is having zero files an error or a valid case?
7. **Checkpointing:** do the outer reader and delegate have stable names and state enabled?
8. **Restart:** are files immutable, and is the resource list identical to the initial run?
9. **Chunk boundaries:** is it acceptable for a chunk to cross two files?
10. **Source metadata:** do items need source file, line number, or batch reference?
11. **Concurrency:** should reading be sequential via one reader or partitioned per file?
12. **Error handling:** how are broken files, invalid headers, or bad records failed, rejected, or skipped?
13. **Output:** can the writer write records from multiple resources into one target, and must ordering be preserved?
14. **Testing:** cover resource lists, ordering, empty files, headers, restarts, and duplicate/missing data.

An immutable manifest, a deterministic comparator, and a checkpointing delegate are the three foundational pillars for reliable restartability in multi-resource jobs.

## 32. Key takeaways

- `MultiResourceItemReader<T>` reads multiple `Resource` items sequentially through a delegate reader and returns them as a single stream.
- The delegate is usually `FlatFileItemReader<T>` and must receive the current resource via the resource-aware contract.
- `MultiResourceItemReader` coordinates files; the delegate is responsible for parsing contents.
- Use `ResourcePatternResolver` to discover files by pattern and validate the resource set before execution.
- Configure an explicit comparator for stable resource ordering; lexicographical order does not always match numeric or date order.
- The multi-resource reader's `strict` flag checks for an empty resource list; the delegate's strict flag checks the opened resource.
- The delegate is opened and closed per resource; `FlatFileItemReader`'s header skip applies to each file when the delegate reopens.
- Chunks can span file boundaries; `MultiResourceItemReader` does not create per-file transactions.
- Outer reader and delegate need stable names, proper state saving, and an immutable resource list for restart.
- Do not add, delete, rename, or modify files while a `JobInstance` may still be restarted; use a manifest or fixed batch folder.
- If the source filename is needed in output, attach source metadata to items or log/audit separately.
- A shared delegate assumes resources share the same format; files with different schemas should use separate readers/steps or explicit custom routing.
- `MultiResourceItemReader` is not inherently thread-safe; use partitioning with separate reader instances and states for parallel processing.
- Test ordering, empty/missing resources, headers, delegate lifecycle, checkpoint/restart, and zero lost or duplicated items.

`MultiResourceItemReader` lets you process multiple files as a unified data source without manually orchestrating file transitions. To keep jobs reliable in production, use an appropriate delegate, define deterministic resource ordering, keep the input set immutable, enable checkpointing on both reader and delegate, and clearly decide how to handle headers, empty files, and per-resource errors. When files can be processed independently and high throughput is needed, consider partitioning with a dedicated reader per worker.
