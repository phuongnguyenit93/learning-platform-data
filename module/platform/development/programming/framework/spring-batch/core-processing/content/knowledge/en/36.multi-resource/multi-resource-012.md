# Testing resource lists

In Spring Batch, `MultiResourceItemReader` coordinates reading across a `Resource[]` array and passes each resource to a delegate reader, such as `FlatFileItemReader`. Testing must verify not only that items are parsed accurately, but also that the resource list is discovered, sorted, filtered, and kept stable between the initial run and restarts.

A valid list with unstable ordering can cause a restart to read the wrong file. A missing resource can fail the step. An empty list may be valid input or a business error depending on configuration. Therefore, tests should cover resource discovery, processing order, delegate lifecycle, file errors, checkpointing, and integration tests against `JobRepository`.

## 1. How does a multi-resource reader work?

`MultiResourceItemReader` is a reader wrapper. It does not parse file contents itself; it holds the resource list and delegates reading each resource to a `ResourceAwareItemReaderItemStream`.

~~~text
Resource resolver / manifest
          |
          v
       Resource[]
          |
          v
 MultiResourceItemReader
          |
          +--> Resource A --> delegate reader --> items A1, A2
          |
          +--> Resource B --> delegate reader --> items B1, B2
          |
          +--> Resource C --> delegate reader --> items C1, C2
          |
          v
         EOF
~~~

| Component | Responsibility |
|---|---|
| `ResourcePatternResolver` or manifest | Discovers and constructs the resource list |
| `Resource[]` | Defines the input file set |
| `MultiResourceItemReader` | Iterates sequentially through each resource |
| Delegate reader | Opens and parses contents of one resource |
| `ExecutionContext` | Persists current resource and delegate state for restarts |

`MultiResourceItemReader` reads in the order of the resource list after applying its comparator/configuration. Never rely on incidental ordering returned by a filesystem or resolver.

## 2. Treat the resource list explicitly as part of the input

Before writing tests, clarify where the list originates:

- A pattern such as `file:/data/inbound/*.csv`.
- A directory passed via `JobParameters`.
- A manifest enumerating files belonging to a batch.
- A resource list queried from a database or service.
- A resource set produced by an upstream step.

The resource list determines what data the step processes. Thus, tests should verify both the list contents and key metadata such as filenames, URIs, versions, or checksums.

If a job must be restartable, the list must stay unchanged across executions of the same `JobInstance`. Preserving the directory name alone is insufficient if files can be added, deleted, or renamed while the job runs.

## 3. Finding resources with ResourcePatternResolver

A common scenario is collecting all CSV files in a directory. `PathMatchingResourcePatternResolver` expands a pattern into `Resource[]`.

~~~java
ResourcePatternResolver resolver =
    new PathMatchingResourcePatternResolver();

Resource[] resources = resolver.getResources(
    "file:/data/inbound/*.csv"
);
~~~

In real applications, the directory may come from `JobParameters`. Extract resource discovery into an independently testable factory or resolver:

~~~java
@Component
public class InputResourceResolver {

    private final ResourcePatternResolver resolver =
        new PathMatchingResourcePatternResolver();

    public Resource[] findCsvFiles(String directory) throws IOException {
        String pattern = Path.of(directory)
            .toAbsolutePath()
            .normalize()
            .toUri()
            .toString() + "*.csv";

        Resource[] resources = resolver.getResources(pattern);

        Arrays.sort(
            resources,
            Comparator.comparing(Resource::getDescription)
        );

        return resources;
    }
}
~~~

This example derives a URI from `Path` to avoid manually concatenating filesystem separators. Verify final pattern behavior on your target OS, especially on Windows or when directories come from external configuration.

Resolver tests should assert:

- Only files with expected extensions are selected.
- Subdirectory files are included or excluded strictly per pattern.
- Temporary files, archive files, or marker files are not picked up by mistake.
- Zero results are returned when nothing matches.
- Results are deterministically sorted.
- Directory access errors surface with actionable diagnostics.

## 4. Resource order must be deterministic

Filesystems do not guarantee identical listing order across environments or invocations. If `Resource[]` order shifts, item emission order from the reader shifts too.

Suppose the directory contains:

~~~text
orders-03.csv
orders-01.csv
orders-02.csv
~~~

If desired order follows the numeric sequence in filenames, sort before passing to the reader:

~~~java
Arrays.sort(
    resources,
    Comparator.comparing(Resource::getFilename)
);
~~~

If filenames can collide across directories or do not reflect business order, use an ordered manifest or a comparator keyed on business attributes.

A test should verify item ordering across files:

~~~java
@Test
void readsResourcesInDeterministicOrder() throws Exception {
    Resource[] resources = {
        new FileSystemResource(fileB),
        new FileSystemResource(fileA)
    };

    Arrays.sort(
        resources,
        Comparator.comparing(Resource::getDescription)
    );

    MultiResourceItemReader<String> reader = newReader(resources);

    assertThat(readAll(reader))
        .containsExactly("A-1", "A-2", "B-1", "B-2");
}
~~~

In this test, `fileA` and `fileB` each hold two records after a header. Placing resources in reverse order initially proves sorting actually takes effect.

## 5. Creating test files with JUnit 5 @TempDir

JUnit 5 provides `@TempDir` to create temporary test directories. This lets you test resource resolvers and readers against a real filesystem without relying on fixed local folders.

~~~java
class MultiResourceReaderTests {

    @TempDir
    Path tempDir;

    private Path writeCsv(String fileName, String... lines)
            throws IOException {
        Path file = tempDir.resolve(fileName);
        Files.write(
            file,
            List.of(lines),
            StandardCharsets.UTF_8
        );
        return file;
    }
}
~~~

Each test receives an isolated directory that JUnit cleans up afterward. Use clear filenames so assertions clearly express expected order.

Avoid shared static fixture files outside the test directory if tests run concurrently or multiple developers share a workspace.

## 6. Creating a FlatFileItemReader delegate for tests

For simple CSV fixtures, you can use `FlatFileItemReader<String>` as the delegate and return raw lines after the header. `MultiResourceItemReader` calls `setResource(...)` on the delegate for each file.

~~~java
private FlatFileItemReader<String> csvDelegate() {
    FlatFileItemReader<String> delegate =
        new FlatFileItemReader<>();

    delegate.setName("csvDelegate");
    delegate.setEncoding(StandardCharsets.UTF_8.name());
    delegate.setLinesToSkip(1);
    delegate.setLineMapper((line, lineNumber) -> line);

    return delegate;
}
~~~

The delegate is configured without binding a fixed resource because the wrapper assigns each resource before opening the file. `linesToSkip(1)` illustrates files having a single header line.

For multi-column files, use your application's real tokenizer and field mapper in integration tests. Resource-list tests should not mock out all mapping when the goal is verifying multiple files read properly.

## 7. Creating a reusable MultiResourceItemReader helper for tests

You can extract reader creation into a helper so tests stay focused on resource lists and outcomes:

~~~java
private MultiResourceItemReader<String> newReader(
        Resource[] resources) {

    return new MultiResourceItemReaderBuilder<String>()
        .name("multiCsvReader")
        .resources(resources)
        .delegate(csvDelegate())
        .saveState(true)
        .strict(true)
        .build();
}
~~~

The name must be stable for the reader to save and restore state. `saveState(true)` enables checkpointing. `strict(true)` requires input resources; with an empty list, the reader raises an error rather than treating it as zero data.

To test allowed empty inputs, create a separate reader with `strict(false)` to verify that policy explicitly.

## 8. Helper to read all items and close the reader

Unit tests can open the reader with an `ExecutionContext`, read until EOF, and close in a `finally` block:

~~~java
private List<String> readAll(
        MultiResourceItemReader<String> reader) throws Exception {

    List<String> items = new ArrayList<>();
    reader.open(new ExecutionContext());

    try {
        String item;
        while ((item = reader.read()) != null) {
            items.add(item);
        }
        return items;
    } finally {
        reader.close();
    }
}
~~~

Never omit `close()` in tests. Delegates may hold file handles or parsers; failing to close resources can prevent subsequent tests from deleting files on some operating systems.

If a test checks checkpointing, do not use this helper because it creates a fresh context and reads to EOF. Manage the context and reader lifecycle manually so you can call `update()` at the desired checkpoint.

## 9. Testing multiple files and item order

Create two files with distinct contents:

~~~java
@Test
void readsEveryRecordFromEveryResource() throws Exception {
    Path fileA = writeCsv(
        "orders-a.csv",
        "orderId,amount",
        "A-1,10",
        "A-2,20"
    );

    Path fileB = writeCsv(
        "orders-b.csv",
        "orderId,amount",
        "B-1,30",
        "B-2,40"
    );

    Resource[] resources = {
        new FileSystemResource(fileB),
        new FileSystemResource(fileA)
    };

    Arrays.sort(
        resources,
        Comparator.comparing(Resource::getDescription)
    );

    MultiResourceItemReader<String> reader = newReader(resources);

    assertThat(readAll(reader))
        .containsExactly(
            "A-1,10",
            "A-2,20",
            "B-1,30",
            "B-2,40"
        );
}
~~~

This test verifies three behaviors at once:

1. Every resource is opened.
2. Headers are skipped in each file.
3. Items are emitted in the configured resource order and intra-file record order.

If your application orders files by date or numeric sequence, write tests whose filenames exercise those exact rules rather than relying solely on alphabetical order.

## 10. Testing that patterns select only intended files

When lists come from wildcards, test both matching and non-matching files:

~~~java
@Test
void patternSelectsOnlyCsvFiles() throws Exception {
    writeCsv("orders-a.csv", "id", "A-1");
    writeCsv("orders-b.csv", "id", "B-1");
    writeCsv("orders-a.done", "marker");
    writeCsv("readme.txt", "not an input");

    ResourcePatternResolver resolver =
        new PathMatchingResourcePatternResolver();

    Resource[] resources = resolver.getResources(
        tempDir.toUri().toString() + "*.csv"
    );

    assertThat(resources)
        .extracting(Resource::getFilename)
        .containsExactlyInAnyOrder(
            "orders-a.csv",
            "orders-b.csv"
        );
}
~~~

The assertion uses `containsExactlyInAnyOrder` to verify only file selection. Ordering must be asserted separately after sorting. Never use an order-insensitive assertion and assume the reader will read in any particular order.

## 11. Testing empty resource lists

Having zero resources can mean two things:

- Zero files arriving is valid—for instance, no activity occurred that day.
- Zero files is an operational error—for instance, upstream failed to deliver a mandatory batch.

`strict` determines how `MultiResourceItemReader` handles an empty list. In strict mode, the reader refuses to open; with strict disabled, the reader finishes immediately without emitting items.

Testing strict mode:

~~~java
@Test
void rejectsEmptyResourceListWhenStrict() {
    MultiResourceItemReader<String> reader =
        new MultiResourceItemReaderBuilder<String>()
            .name("emptyReader")
            .resources(new Resource[0])
            .delegate(csvDelegate())
            .strict(true)
            .saveState(true)
            .build();

    assertThatThrownBy(
        () -> reader.open(new ExecutionContext())
    ).isInstanceOf(IllegalStateException.class);
}
~~~

Testing valid empty input:

~~~java
@Test
void returnsNoItemsWhenEmptyListIsAllowed() throws Exception {
    MultiResourceItemReader<String> reader =
        new MultiResourceItemReaderBuilder<String>()
            .name("optionalReader")
            .resources(new Resource[0])
            .delegate(csvDelegate())
            .strict(false)
            .saveState(true)
            .build();

    ExecutionContext context = new ExecutionContext();
    reader.open(context);

    try {
        assertThat(reader.read()).isNull();
    } finally {
        reader.close();
    }
}
~~~

Never disable strict merely to suppress job failures. Policy must mirror business rules; if input is mandatory, zero files must fail the step cleanly.

## 12. Distinguishing no files found from non-existent resources

These two scenarios differ:

| Scenario | Example | Where to test |
|---|---|---|
| Pattern matches no files | `*.csv` when directory holds only `.txt` | Resource resolver and strict list policy |
| List contains a resource, but file was deleted | Resolver returned resource, then file disappeared | Delegate reader when opening resource |
| Unreadable resource | Missing permissions or storage error | Resource opening and I/O error handling |
| File exists, invalid contents | Malformed CSV or wrong encoding | Delegate reader and mapping |

A `Resource` object can be instantiated even when the underlying file does not exist. Hence, checking `resources.length > 0` alone does not prove every file can be opened.

You can pre-validate before running:

~~~java
for (Resource resource : resources) {
    if (!resource.exists() || !resource.isReadable()) {
        throw new IllegalStateException(
            "Input resource is missing or unreadable: "
                + resource.getDescription()
        );
    }
}
~~~

This provides early detection, though a race condition remains possible if files are deleted or permissions change after validation. The delegate must still handle real resource-open failures.

## 13. Testing that headers are skipped per file

If every CSV carries a header, the delegate must apply `linesToSkip` for each resource. This matters because the wrapper reopens the delegate when advancing to the next file.

Tests should use differing headers to prove the second file's header is not read as data:

~~~java
@Test
void skipsHeaderForEveryResource() throws Exception {
    Path fileA = writeCsv(
        "a.csv",
        "id,name",
        "A-1,An"
    );

    Path fileB = writeCsv(
        "b.csv",
        "order_id,customer",
        "B-1,Binh"
    );

    Resource[] resources = {
        new FileSystemResource(fileA),
        new FileSystemResource(fileB)
    };

    MultiResourceItemReader<String> reader = newReader(resources);

    assertThat(readAll(reader))
        .containsExactly("A-1,An", "B-1,Binh");
}
~~~

In production applications, headers may need validation. Use `skippedLinesCallback` or a dedicated validation step to verify each file's schema. If all files must share the same schema, tests should prove invalid headers fail the step.

## 14. Testing missing or unreadable resources

When a resource sits in the list yet the file does not exist when the reader opens it, a strict `FlatFileItemReader` delegate fails. Tests can create a resource pointing to a non-existent path:

~~~java
@Test
void failsWhenListedResourceDoesNotExist() {
    Resource missing = new FileSystemResource(
        tempDir.resolve("missing.csv").toFile()
    );

    MultiResourceItemReader<String> reader =
        newReader(new Resource[] { missing });

    assertThatThrownBy(
        () -> reader.open(new ExecutionContext())
    ).isInstanceOf(RuntimeException.class);
}
~~~

In production tests, assert the concrete exception type matching your Spring Batch version and how the delegate opens resources. What matters is proving the step does not silently treat a missing mandatory file as an empty resource.

Avoid relying on OS file permission tests on Windows/Linux because permissions vary depending on the user running tests. To test I/O failures reliably, use a custom `Resource` test double whose `getInputStream()` fails deterministically.

## 15. Testing delegate read failures in one file

A resource list may be valid while one file contains a malformed record. Verify that exceptions surface properly and earlier files are not re-read outside policy.

For example, a delegate `LineMapper` parses amounts and throws on invalid values:

~~~java
delegate.setLineMapper((line, lineNumber) -> {
    String[] fields = line.split(",");
    if (fields.length != 2) {
        throw new IllegalArgumentException(
            "Invalid record at line " + lineNumber
        );
    }
    return fields[0] + ":" + new BigDecimal(fields[1]);
});
~~~

For fixed-schema inputs in production code, use a real tokenizer/mapper rather than `split`. The snippet above simply demonstrates a controllable test mapper.

If the step allows skipping bad records, test the skip policy at step level and verify `SkipListener` receives the right error. Do not confuse single-record parse errors with resource-open errors or whole-file read failures.

## 16. Testing checkpointing when restarting mid-resource

`MultiResourceItemReader` persists state for the current resource and its delegate. On restart, it must open the right resource and restore the position within that resource.

Direct reader tests can share one `ExecutionContext`:

~~~java
@Test
void resumesWithinCurrentResourceFromSavedContext() throws Exception {
    Resource[] resources = sortedResources(fileA, fileB);

    ExecutionContext context = new ExecutionContext();
    MultiResourceItemReader<String> firstRun = newReader(resources);

    firstRun.open(context);
    try {
        assertThat(firstRun.read()).isEqualTo("A-1");
        firstRun.update(context);
    } finally {
        firstRun.close();
    }

    MultiResourceItemReader<String> restarted = newReader(resources);
    restarted.open(context);
    try {
        assertThat(restarted.read()).isEqualTo("A-2");
        assertThat(restarted.read()).isEqualTo("B-1");
    } finally {
        restarted.close();
    }
}
~~~

This test verifies reader restoration from context after `update` is called. It does not prove transaction commits or `JobRepository` integration; that requires an integration test with a real step.

`sortedResources(...)` is a helper constructing `Resource[]` in deterministic order using the same rules as the production job.

## 17. Testing checkpointing after switching to the next resource

Another key scenario is checkpointing after finishing one file and starting the next. On restart, the wrapper must select the right active resource and the delegate must resume at the right position.

Example with two files:

~~~text
a.csv: A-1, A-2
b.csv: B-1, B-2

Run:
  read A-1
  read A-2
  switch to b.csv
  read B-1
  update checkpoint

Restart:
  open b.csv
  restore delegate state
  continue reading B-2
~~~

Write a dedicated test for resource boundaries because bugs often surface when wrapper resource index updates and delegate state fall out of sync. Use the exact same reader name, resource order, and context across both opens.

If tests show the first item of the active file being duplicated or skipped, verify that the delegate is properly registered in the lifecycle and that the resource list kept its exact order.

## 18. The resource list must stay unchanged on restart

A multi-resource reader's checkpoint can store the index of the current resource. If the resource list changes, the old index may point to a different file.

For example:

~~~text
First run:
  [a.csv, b.csv, c.csv]
  resourceIndex = 1  -> b.csv

Before restart:
  [0-new.csv, a.csv, b.csv, c.csv]

Restart:
  resourceIndex = 1  -> a.csv
~~~

The reader could resume on a file mismatched with the old checkpoint. Therefore, restart tests should simulate resource list mutations and verify the application detects or rejects the situation.

Ways to preserve stability:

- Generate an immutable manifest before launch.
- Store the manifest ID or source batch ID in identifying `JobParameters`.
- Keep the file list and order intact until the `JobInstance` finishes.
- Store checksums/versions if file contents could be replaced.
- Never prepend new files into a restarting batch's list.

Do not simply re-sort the list on every run and assume restarts are safe. If the underlying file set changed, deterministic sorting still fails to guarantee the same inputs.

## 19. Testing manifests instead of dynamic wildcards

For critical batches, manifests are clearer than wildcards. A manifest records the batch's files and their order.

~~~text
batchId: B-2026-11-15
files:
  - orders-001.csv
  - orders-002.csv
  - orders-003.csv
~~~

The resolver reads the manifest and creates resources in the exact persisted order. Tests should assert:

- A manifest referencing a missing file fails naming that specific file.
- A manifest with duplicate entries enforces deduplication or fails clearly.
- Files outside the manifest are ignored.
- Manifest ordering is preserved verbatim.
- Restarts reuse the exact same manifest version.

This prevents a new file dropped into the directory between runs from accidentally becoming part of the same `JobInstance`.

## 20. Testing duplicate resources

If the list contains the same file twice, `MultiResourceItemReader` may read that file twice. Causes include overlapping patterns, duplicate manifest entries, or resolvers merging multiple sources.

For example:

~~~java
Resource resource = new FileSystemResource(fileA);

Resource[] resources = {
    resource,
    resource,
    new FileSystemResource(fileB)
};
~~~

Define the application's policy:

- Reject duplicate lists to prevent duplicate imports.
- Deduplicate by normalized URI or file identity.
- Allow duplicates only if repeated entries carry distinct business meaning.

Do not deduplicate solely by `getFilename()` if two directories can contain identically named files. Use URIs/canonical paths or a stable source ID.

Tests should construct two distinct `Resource` objects pointing to the same file and verify the resolver applies the chosen policy.

## 21. Testing multiple resources with differing schemas

If each file carries a different header or schema version, a single static delegate may not suffice. You may need an upfront validation step or a reader/mapping strategy routed by resource metadata.

Do not allow arbitrary per-file schemas hoping a single `LineMapper` will cope. Clarify:

- Do all files share the same schema version?
- Can files have differing headers with identical column mappings?
- Must mappings dispatch by per-file version?
- Should an invalid file fail the whole step or simply be excluded from the manifest?

Tests should cover at least one file per supported schema version plus one unsupported version. Unsupported schemas should fail early before writing data.

## 22. Testing the ResourceAware delegate lifecycle

The delegate reader must receive the current resource before opening. For custom delegates, tests can verify `setResource`, `open`, `read`, `update`, and `close` are invoked in proper order.

If mocking to inspect interactions, mock the delegate only when specifically verifying wrapper orchestration. Never mock everything in every test, as that skips real file I/O, headers, encoding, and checkpoints.

For custom delegates, verify:

- A new resource is assigned before every `open`.
- The prior resource is closed when advancing to the next file.
- `update` saves state for the current resource.
- `close` releases the delegate when the step ends.
- Exceptions from the delegate propagate to the step with proper resource cleanup.

## 23. Testing through Spring Batch steps and JobRepository

Unit tests calling `open`/`read`/`update`/`close` are useful, but they do not validate transactions, checkpoints, or job-level restarts. Include at least one integration test running a real step with `JobRepository` and a transaction manager.

You can use `@SpringBatchTest` and `JobLauncherTestUtils` if Spring Batch Test is on the classpath:

~~~java
@SpringBatchTest
@SpringBootTest
class MultiResourceJobRestartTests {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void restartsFromCommittedMultiResourceCheckpoint() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
            .addString("manifestId", "batch-001", true)
            .toJobParameters();

        JobExecution first =
            jobLauncherTestUtils.launchJob(parameters);

        assertThat(first.getStatus())
            .isEqualTo(BatchStatus.FAILED);

        JobExecution restarted =
            jobLauncherTestUtils.launchJob(parameters);

        assertThat(restarted.getStatus())
            .isEqualTo(BatchStatus.COMPLETED);
    }
}
~~~

This example assumes the test job is configured to fail intentionally once after at least one chunk commits, allowing the restart to resume. Keep fail-once triggers isolated inside test fixtures so other tests stay unaffected.

Both launches use identical identifying `JobParameters` to resume the same `JobInstance`. Changing `manifestId` to a new identifying value creates a different instance and fails to test restart.

Integration tests must also verify output data, not just status:

- Records from committed chunks are not rewritten outside policy.
- Records from the uncommitted chunk are reprocessed.
- Resource index and delegate checkpoint are restored.
- Initial and restarted step executions belong to the same `JobInstance`.
- Source files and manifest remain identical between runs.

## 24. Testing JobParameters and resource manifests

If the resource directory or manifest comes from `JobParameters`, test both resource selection and job identity.

~~~java
JobParameters parameters = new JobParametersBuilder()
    .addString("manifestId", "batch-001", true)
    .addString("requestedBy", "scheduler", false)
    .toJobParameters();
~~~

`manifestId` is marked identifying because it defines the processing run's file set. `requestedBy` is purely audit metadata and should not create a new `JobInstance` when changed.

Tests should verify:

- Same manifest ID and job name resolve back to the same `JobInstance` on restart.
- Different manifest IDs create new `JobInstance` runs.
- Non-existent manifests fail the job before writing data.
- Manifests containing missing files are never silently ignored.
- Manifest versions stay unchanged while the `JobInstance` remains restartable.

## 25. Testing encoding and file contents

Having the right resource list is not enough; each file must be read with the right encoding and parser. Create test fixtures with Unicode characters, Vietnamese diacritics, and delimiter-containing values.

~~~java
Files.writeString(
    file,
    "id,name\nA-1,Nguyễn An\n",
    StandardCharsets.UTF_8
);
~~~

Verify the delegate configures the matching encoding:

~~~java
delegate.setEncoding(StandardCharsets.UTF_8.name());
~~~

If source files contain BOMs, CRLF endings, multi-line headers, or custom delimiters, build realistic fixtures to verify every file is read identically. Do not inspect only the first file, since the delegate reopens for every resource.

## 26. Testing performance and resource counts

With hundreds or thousands of files, measure discovery, sorting, open/close overhead, and restart latency. You do not need millions of records in unit tests; benchmark separately using production-like resource counts.

Useful metrics:

- Time taken by the resolver to build the resource list.
- Counts of selected vs. excluded resources.
- Open/close time per resource.
- Total items and per-file item counts.
- Restart duration when checkpointed near the end of the file list.
- Connection/thread counts if combined with partitioning.
- Memory footprint when manifests or resource lists are large.

For huge lists, avoid logging every path on every run. Log counts, manifest ID, checksum, and sample entries for triage; keep the full manifest in queryable storage.

## 27. MultiResourceItemReader does not run in parallel automatically

`MultiResourceItemReader` coordinates sequential reads across the resource list. It does not spawn a thread per file.

To process files in parallel, partition by resource or resource group so each worker step gets its own reader. Then test:

- Each resource is assigned to workers strictly per policy.
- Each worker owns an isolated `StepExecution` and `ExecutionContext`.
- Two workers never write to the same output unless explicitly designed.
- Each partition maintains independent transactions and checkpoints.
- Failure in one partition does not discard committed work from another partition.
- Resource lists and partition assignments remain stable across restarts.

Never share one stateful delegate reader across workers. `FlatFileItemReader` and similar readers are not designed for concurrent `read()` calls on the same instance.

## 28. Testing errors and cleanup during resource transitions

When the delegate finishes file A and moves to file B, the reader must close resource A before opening B. If opening B fails, the step must report the failure and clean up open resources cleanly.

Tests should simulate:

1. First file reads cleanly, second file does not exist.
2. First file reads cleanly, second file denies read access.
3. Delegate throws a parse error on a file midway through the list.
4. Step is stopped while the delegate holds an open resource.
5. Reader closes cleanly after normal EOF.
6. Restart inside the second file and open failure on the second file.

Use a custom `Resource` test double to inject deterministic `getInputStream()` failures. For real filesystem failures, avoid depending on permission bits because behavior varies across OSes and test runner accounts.

## 29. Recommended test case matrix

| Category | Scenario | What to verify |
|---|---|---|
| Discovery | Pattern matches multiple valid files | All matching resources selected |
| Filtering | Directory contains `.txt`, `.done`, `.tmp` | Non-policy files excluded |
| Ordering | Resolver returns unstable order | Reader emits items in sorted order |
| Empty | Empty list, strict enabled | Reader fails on open |
| Empty | Empty list, strict disabled | Reader returns EOF |
| Missing | Resource in list was deleted | Delegate fails on file open |
| Header | Each file has a header | Header skipped on every resource |
| Parsing | File contains malformed record | Exception/skip follows policy |
| Duplicate | Same file listed twice | Resolver enforces duplicate policy |
| Restart | Checkpoint mid-file | Resumes from item after checkpoint |
| Restart | Checkpoint after switching files | Restores right resource and delegate state |
| Manifest | List mutated between executions | Detects or rejects unsafe restart |
| Integration | First chunk commits, next fails | Restart keeps committed chunk and retries uncommitted chunk |
| Parallel | Partitioned per resource | Each worker keeps isolated state and resources |

## 30. Common mistakes

| Mistake | Consequence | Remedy |
|---|---|---|
| Relying on resolver return order | Results vary across environments | Sort by stable key or use a manifest |
| Testing only the first resource | Bugs in later files go undetected | Build fixtures with multiple resources |
| Asserting only resource count | Fails to catch wrong contents or unreadable files | Actually read through the delegate |
| Using `strict(false)` for mandatory inputs | Missing files let the job finish empty | Align strict policy with business rules |
| Assuming a `Resource` object means the file exists | File may vanish before open | Test and handle resource-open failures |
| Mutating the file list before restart | Resource index points to a different file | Keep manifests and inputs immutable |
| Not sorting resources | Item emission order is non-deterministic | Configure an explicit comparator |
| Not verifying per-file headers | Later files' headers leak into data | Configure header skipping/validation per resource |
| Mocking the entire delegate | Skips testing real file I/O and parsing | Combine unit tests with real file fixtures |
| Sharing a reader across workers | Race conditions and corrupted checkpoints | Give each partition its own reader |
| Asserting only job `COMPLETED` | Misses duplicates or dropped records | Assert output data and final checkpoints |

## 31. Workflow for building resource list tests

When adding a multi-resource step, implement tests in this order:

1. Create a helper to generate fixture files in `@TempDir`.
2. Test the resolver/pattern to confirm exact resource selection.
3. Test sorting and item order across multiple files.
4. Test headers, encoding, and parser behavior per resource.
5. Test empty lists under both strict and non-strict policies.
6. Test missing resources, unreadable resources, and bad records.
7. Test duplicate resources and manifest validation.
8. Test `ExecutionContext` restarts within a file and across file boundaries.
9. Add an integration test with `JobRepository`, chunk commits, and restarts.
10. If using partitioning, test worker assignments and isolated state.

Keep resource resolver, comparator, delegate reader name, and manifest semantics identical between tests and production. If tests build lists differently from how the production job builds resources, test results may not reflect production behavior.

## Conclusion

Testing resource lists in Spring Batch requires verifying the resource set, processing order, ability to open/read each file, and checkpointing on restart. `MultiResourceItemReader` iterates across `Resource[]`, while the delegate reader parses the contents of each resource. Use `@TempDir` and real file fixtures to test resolvers, headers, encoding, strict mode, missing resources, and item ordering.

For restarts, keep the resource list and order immutable, reuse identifying `JobParameters`, enable `saveState`, and assert both the resource index and delegate state through `ExecutionContext`. Unit tests verify reader behavior; integration tests backed by `JobRepository` verify step transactions, checkpoints, and restarts. When processing in parallel, give every partition its own reader and state.
