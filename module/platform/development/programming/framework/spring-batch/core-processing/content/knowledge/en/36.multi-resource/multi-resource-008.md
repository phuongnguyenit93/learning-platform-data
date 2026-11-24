# Output filename suffixes

When a Spring Batch job exports a large dataset across multiple files, **MultiResourceItemWriter** can split output into smaller resources bounded by an item limit. Each resource needs a distinct filename so earlier files are not overwritten and downstream consumers can locate every data segment accurately. Spring Batch provides **ResourceSuffixCreator** to determine the suffix appended to the base resource name when the writer creates each new file.

A suffix is a string appended to the base resource name. By default, the writer typically generates names such as **orders.csv.1**, **orders.csv.2**, and so on. If the receiving system expects the file extension at the very end, such as **orders-001.csv**, supply a custom suffix creator. Naming should be consistent, deterministically sortable, safe across restarts, and isolated from outputs of other runs.

## 1. MultiResourceItemWriter and suffixes

**MultiResourceItemWriter<T>** is a writer wrapper around another writer. It forwards items to the delegate writer while deciding which resource is currently open for writing. When the item count of the current resource hits the configured limit, the writer closes that resource, creates the next resource by appending a suffix to the base resource, and continues writing.

For example, an export of 10,000 items with a 3,000-item limit per file:

~~~text
orders.csv.1
orders.csv.2
orders.csv.3
orders.csv.4
~~~

With a different naming convention, you might generate:

~~~text
orders-part-001.csv
orders-part-002.csv
orders-part-003.csv
orders-part-004.csv
~~~

**MultiResourceItemWriter** manages rollover between resources. A delegate such as **FlatFileItemWriter** handles writing item contents into the currently assigned resource. **ResourceSuffixCreator** only determines the appended name segment; it does not format file contents, split chunks, or govern how many items go into each resource.

## 2. How are the base resource and suffix combined?

The writer takes a base resource, such as **orders.csv**. When creating the next resource, it takes the base resource name and appends the string returned by the suffix creator. With default sequential numeric suffixes, the result is:

| Base resource | Suffix | Generated filename |
|---|---|---|
| orders.csv | .1 | orders.csv.1 |
| orders.csv | .2 | orders.csv.2 |
| orders.csv | .3 | orders.csv.3 |

The key detail is that the suffix is appended directly onto the base resource. The writer does not recognize **.csv** as an extension to keep at the end. Therefore, if consumers expect **orders-001.csv**, design the base resource and suffix creator so concatenation yields that exact name.

A straightforward approach is using a base resource without an extension:

| Base resource | Custom suffix | Result |
|---|---|---|
| orders | -part-001.csv | orders-part-001.csv |
| orders | -part-002.csv | orders-part-002.csv |

Do not include **.csv** in both the base resource and the suffix if you only want one extension. For example, base **orders.csv** plus suffix **-part-001.csv** produces a filename with two **.csv** segments.

## 3. What is ResourceSuffixCreator?

**ResourceSuffixCreator** is a Spring Batch extension point for generating the suffix of each subsequent resource. The interface takes a resource index and returns a suffix string:

~~~java
public interface ResourceSuffixCreator {

    String getSuffix(int index);
}
~~~

**MultiResourceItemWriter** calls the creator whenever it needs a new resource. The suffix creator does not need to know which items are being written or record contents; it simply receives the index and constructs the next filename portion.

Spring Batch includes a default implementation, **SimpleResourceSuffixCreator**. This implementation appends a dot and the index to the resource name, producing conventions like **.1**, **.2**, **.3**. If that convention suits your receiving system, you can rely on the default. If you need trailing extensions, zero-padding, or custom conventions, provide your own implementation.

## 4. Basic MultiResourceItemWriter configuration

Example using **FlatFileItemWriter** as the delegate:

~~~java
@Bean
public FlatFileItemWriter<Order> orderFileDelegate() {
    return new FlatFileItemWriterBuilder<Order>()
            .name("orderFileDelegate")
            .delimited()
            .delimiter(",")
            .names("orderId", "customerId", "amount")
            .build();
}

@Bean
public MultiResourceItemWriter<Order> multiOrderWriter(
        FlatFileItemWriter<Order> orderFileDelegate) {

    return new MultiResourceItemWriterBuilder<Order>()
            .name("multiOrderWriter")
            .resource(new FileSystemResource("output/orders.csv"))
            .delegate(orderFileDelegate)
            .itemCountLimitPerResource(3000)
            .saveState(true)
            .build();
}
~~~

In this example, the writer splits data into resources of up to 3,000 items each per the configured limit. Without an explicit suffix creator, the writer uses the default behavior of its Spring Batch version.

The resource name here is illustrative. Before deploying to production, verify the output directory, write permissions, output identity per job instance, and pre-existing file policies.

## 5. Using the default suffix

If there are no special naming requirements, the default suffix is the simplest choice:

~~~java
MultiResourceItemWriter<Order> writer =
        new MultiResourceItemWriterBuilder<Order>()
                .name("multiOrderWriter")
                .resource(new FileSystemResource("output/orders.csv"))
                .delegate(orderFileDelegate)
                .itemCountLimitPerResource(3000)
                .saveState(true)
                .build();
~~~

With base resource **orders.csv**, subsequent resources are named by index. This is simple to configure and works well when downstream reads file lists by prefix or manifest.

Treat the default suffix as part of the filename contract. If downstream searches for **orders-001.csv**, switching to the default will cause consumers to miss files even though contents are written properly.

## 6. Customizing the suffix to keep the extension at the end

If the receiving system expects names like **orders-1.csv**, supply a lambda or class implementing **ResourceSuffixCreator**:

~~~java
ResourceSuffixCreator suffixCreator =
        index -> "-" + index + ".csv";

MultiResourceItemWriter<Order> writer =
        new MultiResourceItemWriterBuilder<Order>()
                .name("multiOrderWriter")
                .resource(new FileSystemResource("output/orders"))
                .delegate(orderFileDelegate)
                .itemCountLimitPerResource(3000)
                .resourceSuffixCreator(suffixCreator)
                .saveState(true)
                .build();
~~~

The base resource is **output/orders**, and the suffix creator returns **-1.csv**, **-2.csv**, and so on, leaving **.csv** as the final extension.

If your project's builder API does not accept a lambda directly or uses a different method name, implement **ResourceSuffixCreator** as a class and pass an instance to the appropriate builder/setter. Always match the API of your application's Spring Batch version.

## 7. Using zero-padded sequence numbers

Many systems expect files to appear in order when listed alphabetically by name. Unpadded sequence numbers sort lexicographically as **part-1**, **part-10**, **part-2**. Zero-padding yields consistent sorting:

~~~java
ResourceSuffixCreator suffixCreator =
        index -> String.format("-part-%03d.csv", index);
~~~

Example output:

~~~text
orders-part-001.csv
orders-part-002.csv
orders-part-003.csv
...
orders-part-010.csv
~~~

Width **03** specifies at least three digits. If resource counts can exceed 999, choose a wider pad or accept longer filenames once the index grows.

Zero-padding affects only name formatting. It does not alter item processing order, item count per file, or writer checkpoints.

## 8. Writing a dedicated suffix creator class

When naming conventions involve multiple rules, a dedicated class improves readability and testability:

~~~java
public class PaddedCsvSuffixCreator implements ResourceSuffixCreator {

    private final String prefix;
    private final int width;

    public PaddedCsvSuffixCreator(String prefix, int width) {
        this.prefix = prefix;
        this.width = width;
    }

    @Override
    public String getSuffix(int index) {
        return String.format(
                "%s%0" + width + "d.csv",
                prefix,
                index);
    }
}
~~~

Configuration:

~~~java
.resourceSuffixCreator(new PaddedCsvSuffixCreator("-part-", 4))
~~~

With base resource **orders**, this creator generates **orders-part-0001.csv**, **orders-part-0002.csv**, and so on. Keep class configuration immutable and ensure the same index always yields the same suffix.

If prefix or width comes from job parameters, validate values before opening the writer. Never allow raw inputs containing path separators or sequences that could create files outside the intended output directory.

## 9. Suffix creators must be deterministic and stable

In batch processing, a job can stop and restart. The writer must reconstruct the exact resource name matching the saved index. Therefore, the suffix creator must be deterministic:

~~~java
index -> "-part-" + index + ".csv"
~~~

Given the same index, the result is always identical. Never embed values that vary per invocation into the suffix:

~~~java
// Bad: generates a different name on every call.
index -> "-" + UUID.randomUUID() + ".csv"
~~~

If a suffix creator generates random names, a restart may look for or create a different resource from the file holding already-committed data. This leads to fragmented files, duplicated items, or incomplete outputs.

Current timestamps, random numbers, and mutable state inside the creator carry the same risk. To distinguish business runs, embed an output version or business identity in the base resource stably across the entire **JobInstance**, keeping the suffix strictly for the resource index within that instance.

## 10. Suffix index and resource ordering

The index passed to the suffix creator is used to name each subsequent resource. It represents the sequence of resources created by **MultiResourceItemWriter**, not a global item index or chunk count.

For example:

- `itemCountLimitPerResource = 1000`.
- The first resource holds up to 1,000 items.
- When the next resource is needed, the writer requests the suffix for the next index.
- The new resource receives subsequent items in chunk order.

Do not infer total job item counts solely from the suffix when the final chunk is partial. For example, 2,250 items with a limit of 1,000 creates three resources, yet the final file contains only 250 items.

If downstream needs per-file item counts, emit a manifest or count records in a post-write verification step. Filenames provide sequence/identity, not guaranteed record counts.

## 11. itemCountLimitPerResource and rollover

The suffix is applied when the writer rolls over to a new resource. The rollover trigger is controlled by **itemCountLimitPerResource**:

~~~java
.itemCountLimitPerResource(5000)
~~~

This limit caps the maximum items written to each resource per writer tracking. It is distinct from chunk size:

| Setting | Meaning |
|---|---|
| `chunk(500, transactionManager)` | Items processed within one chunk transaction |
| `itemCountLimitPerResource(5000)` | Item limit for a single output resource |
| `resourceSuffixCreator(...)` | Naming rule for the next resource |

For example, with chunk size 500 and resource limit 5,000, a single file accepts multiple chunks. When the limit is reached, the writer rolls over to a new file. The suffix creator is invoked only when naming a new resource, not after every chunk.

Item limits do not enforce byte limits. If records vary dramatically in length, one 5,000-item file may be vastly larger or smaller than another. If downstream imposes byte-size limits, design a custom writer or byte-based rollover mechanism.

## 12. Delegate writer and new resources

**MultiResourceItemWriter** requires a delegate capable of writing to a resource reassigned per file. For text files, **FlatFileItemWriter** is commonly used because it supports resource-aware writing and the **ItemStream** lifecycle.

For example:

~~~java
FlatFileItemWriter<Order> delegate =
        new FlatFileItemWriterBuilder<Order>()
                .name("orderDelegate")
                .delimited()
                .names("orderId", "customerId", "amount")
                .build();
~~~

Do not bind the delegate to a separate fixed resource if the wrapper manages resources. **MultiResourceItemWriter** assigns resources to the delegate on rollover. If the delegate writes to its own hardcoded path or clings to an old file handle, wrapper suffix names will no longer match actual output.

When using a custom delegate, confirm it implements **ResourceAwareItemWriterItemStream** or the contract required by the wrapper in your Spring Batch version. The delegate must also manage `open`/`update`/`close` and state cleanly.

## 13. Headers and footers in individual files

When the writer rolls over, each resource is an independent file. If the **FlatFileItemWriter** delegate defines header/footer callbacks, verify they apply to each resource according to the delegate's open/close lifecycle.

For example, if every CSV file must carry a header:

~~~text
orders-part-001.csv:
orderId,customerId,amount
1001,C001,250.00
...

orders-part-002.csv:
orderId,customerId,amount
6001,C006,100.00
...
~~~

Headers must appear in every file when each file is an independent document. Do not assume only the first file receives a header. Test rollover behavior on your active Spring Batch version.

Footers can likewise be written per resource when the delegate closes each file. If a footer requires a per-file record count or checksum, compute it per resource and ensure the value is finalized before closing.

## 14. Suffix naming does not alter file contents

The suffix creator only generates resource names. It never alters:

- CSV delimiters.
- Character encoding.
- Headers/footers.
- Field mappings.
- Item ordering.
- Chunk size.
- Transaction boundaries.
- Skip/retry rules.

If formatting must change by file index, the suffix creator is the wrong place. Configure the delegate or design separate writers for distinct output formats. Keeping naming and serialization decoupled makes testing much easier.

## 15. Building filenames with business dates

You can place a business date in the base resource and reserve the suffix for the part index:

~~~java
String baseName = "orders-" + businessDate + "-tenant-" + tenantId;
Resource baseResource = new FileSystemResource(
        outputDirectory.resolve(baseName).toFile());

ResourceSuffixCreator suffixCreator =
        index -> String.format("-part-%03d.csv", index);
~~~

Example output:

~~~text
orders-2026-11-15-tenant-42-part-001.csv
orders-2026-11-15-tenant-42-part-002.csv
~~~

Derive the date and tenant from identifying job parameters or a validated output key so restarts of the same instance reconstruct the exact base name. Never read the current system date inside the creator on every call, because jobs crossing midnight or restarting on a later day would generate unexpected new resources.

If business dates could contain filename-unsafe characters, format them strictly using a fixed standard like ISO dates. Normalize and validate tenant identifiers as well.

## 16. Combining base resource and suffix cleanly

Compute the final expected filename before configuring the writer. Examples:

| Desired name | Base resource | Suffix creator |
|---|---|---|
| orders.csv.1 | orders.csv | Default .1 |
| orders-1.csv | orders | -1.csv |
| orders-part-001.csv | orders | -part-001.csv |
| orders-20261115-001.csv | orders-20261115 | -001.csv |
| tenant-42/orders-001.json | tenant-42/orders | -001.json |

Avoid injecting arbitrary path separators inside the suffix creator. Suffixes should normally modify only the filename. Directories should be established in the base resource or a controlled output directory.

## 17. Preventing path traversal and invalid filenames

If prefixes or suffixes come from job parameters or external data, restrict allowed characters. Never interpolate raw user input into file paths:

~~~java
String suffix = request.getFileSuffix();
Path output = outputDirectory.resolve("orders" + suffix + ".csv");
~~~

If `suffix` contains **../**, path separators, or special characters, files could be written outside the target directory or overwrite unrelated files.

Best practices:

- Accept only validated filename patterns.
- Reject suffixes containing **/**, **\\**, **:**, or path traversal segments.
- Normalize paths and assert they remain inside the output directory.
- Isolate each job instance in its own directory.
- Detect collisions via atomic file creation operations rather than prior existence checks alone.

Even though a suffix creator is an internal component, its configuration inputs still require validation.

## 18. Do not use random timestamps per part

Timestamped filenames can be useful for output versioning, but distinguish the job's timestamp from part creation timestamps:

- A job launch timestamp/identity can be resolved once and placed in the base resource.
- Part indexes must remain stable across resource order.
- Never generate a fresh timestamp inside `getSuffix(index)` on every call.

Bad example:

~~~java
index -> "-" + Instant.now() + "-" + index + ".csv"
~~~

If the writer invokes the creator again on restart, the same index produces a different filename. A better pattern is computing `runKey` once from identifying parameters, embedding it in the base resource, and keeping the suffix simply **-part-001.csv**.

## 19. Restarts and the suffix creator

**MultiResourceItemWriter** persists state via **ItemStream**. When restarting the same **JobInstance**, the writer needs the current resource index and item count written to that resource. The suffix creator must reproduce the exact resource name corresponding to the checkpointed index.

For safe restarts:

- Assign a stable wrapper writer name via `name(...)`.
- Enable `saveState(true)` when checkpoints are needed.
- Keep the exact same base resource on restart.
- Keep the exact same suffix creator and configuration.
- Keep the item count limit identical.
- Keep the delegate name and mapping configuration identical.
- Never delete or rename already-written and committed resources.
- Keep input data stable so checkpoints point to the right items.

Changing suffix format between an initial run and a restart prevents the writer from locating prior resources or causes it to create mismatched names. Never switch from **.1** to **-part-001.csv** mid-way through a restartable **JobInstance**.

When naming conventions must change, create a new output version or job instance, or implement explicit migration for legacy output. Never mutate writer configuration arbitrarily on an interrupted job.

## 20. JobInstance identity and base filenames

The base resource should typically reflect the business identity of the output:

- Job name or export type.
- Business date.
- Tenant or partition key.
- Input snapshot/version.
- Output version or reprocess ID if needed.

For example:

~~~text
orders-2026-11-15-tenant-42-v1-part-001.csv
orders-2026-11-15-tenant-42-v1-part-002.csv
~~~

The segments **2026-11-15**, **tenant-42**, and **v1** stay fixed for one output identity. Only the part suffix increments by resource index.

If the base resource is simply **orders**, multiple `JobInstance` executions can all create **orders-part-001.csv**, causing collisions. Construct unique base resources from identifying parameters or a reserved output key.

Do not use **JobExecution** ID as the output identity when restarts mint a new execution ID yet must continue writing to the same resources. Execution IDs can go into a manifest for auditing, while filenames rely on stable **JobInstance** identity.

## 21. Preventing overwrites of existing files

A suffix creator produces deterministic names, but it does not automatically protect existing files from overwrites. If a new job reuses the same base resource and starting index, filenames can collide with prior outputs.

Safeguards:

- Include output version or business key in the base resource.
- Write into a `JobInstance`-isolated staging directory.
- Configure delegates/writers not to clobber existing files unintentionally.
- Use reservations/manifests or create-new semantics to catch collisions.
- Publish only after all resources are written and verified.
- Prevent downstream from reading incomplete staging files.

On filesystems, use atomic create-if-not-exists operations during preparation/reservation. On object storage, use conditional creates if supported by the provider. Checking `Files.exists()` followed by opening still leaves a race condition when two jobs run concurrently.

## 22. Multi-resource output and manifests

When one job emits multiple files, downstream needs to know which files belong to the export and whether all parts finished. A manifest can describe the resource set:

~~~json
{
  "jobKey": "orders:2026-11-15:tenant-42:v1",
  "status": "PUBLISHED",
  "files": [
    {"name": "orders-2026-11-15-tenant-42-v1-part-001.csv", "records": 3000},
    {"name": "orders-2026-11-15-tenant-42-v1-part-002.csv", "records": 3000},
    {"name": "orders-2026-11-15-tenant-42-v1-part-003.csv", "records": 450}
  ]
}
~~~

Generate the manifest only after the writer closes all resources and files pass validation. It can include record counts, byte sizes, and checksums so consumers detect missing or corrupted files.

Suffix indexes help consumers order parts, though they cannot replace a manifest. If the last file is partial or the job failed midway, consumers cannot verify completeness from an individual filename alone.

## 23. Headers/footers and manifests serve different roles

Headers and footers belong to individual file contents. Manifests describe the entire file set and export status.

For example, each CSV has a header:

~~~text
orderId,customerId,amount
1001,C001,250.00
~~~

While a manifest describes:

~~~json
{
  "jobKey": "orders:2026-11-15:v1",
  "status": "PUBLISHED",
  "parts": 3
}
~~~

Do not cram global export metadata into filename suffixes. Filenames should stay concise, stable, and parseable; manifests are the right place for per-part details.

## 24. ResourceSuffixCreator and multi-threading

Suffix creators should be stateless and thread-safe. In many setups, writers execute sequentially per chunk; nevertheless, never rely on a mutable counter inside the suffix creator to determine indexes.

Bad example:

~~~java
public class StatefulSuffixCreator implements ResourceSuffixCreator {

    private int counter;

    @Override
    public String getSuffix(int ignored) {
        return "-" + (++counter) + ".csv";
    }
}
~~~

An independent counter can drift out of sync with the resource index persisted in checkpoints. On restart, the counter resets to 0 or resumes at the wrong value, causing colliding or unexpected filenames.

Always use the index supplied by the writer:

~~~java
public class IndexedSuffixCreator implements ResourceSuffixCreator {

    @Override
    public String getSuffix(int index) {
        return String.format("-part-%03d.csv", index);
    }
}
~~~

The same index always produces the same suffix. Never store mutable state inside a suffix creator unless an explicit application contract requires it and persists that state synchronized with the writer.

## 25. Unit testing suffix creators independently

Suffix creators contain small, self-contained logic ideal for direct unit tests:

~~~java
class PaddedCsvSuffixCreatorTest {

    private final ResourceSuffixCreator creator =
            index -> String.format("-part-%03d.csv", index);

    @Test
    void createsPaddedSuffix() {
        assertEquals("-part-001.csv", creator.getSuffix(1));
        assertEquals("-part-009.csv", creator.getSuffix(9));
        assertEquals("-part-010.csv", creator.getSuffix(10));
        assertEquals("-part-125.csv", creator.getSuffix(125));
    }
}
~~~

Tests should cover:

- Starting index per writer convention.
- Rollover from 9 to 10 to verify zero-padding.
- Indexes exceeding the minimum pad width.
- Empty prefix/suffix or invalid configuration if configurable.
- Repeated calls with the same index returning identical results.
- Zero path separators or forbidden characters produced.

When using the default creator, tests can verify the naming convention downstream depends on. Avoid coupling tests to internal implementation details not guaranteed by contract.

## 26. Testing real filenames via MultiResourceItemWriter

Unit testing the creator alone does not prove the wrapper concatenates suffixes with the base resource as expected. Test the writer with temporary resources and a small item count limit.

Illustrative test skeleton:

~~~java
@TempDir
Path tempDir;

@Test
void createsExpectedPartNames() throws Exception {
    FlatFileItemWriter<Order> delegate =
            new FlatFileItemWriterBuilder<Order>()
                    .name("testOrderDelegate")
                    .delimited()
                    .names("orderId", "customerId")
                    .build();

    MultiResourceItemWriter<Order> writer =
            new MultiResourceItemWriterBuilder<Order>()
                    .name("testMultiWriter")
                    .resource(new FileSystemResource(
                            tempDir.resolve("orders").toFile()))
                    .delegate(delegate)
                    .itemCountLimitPerResource(2)
                    .resourceSuffixCreator(
                            index -> String.format("-part-%02d.csv", index))
                    .saveState(true)
                    .build();

    // Open the writer, write enough items to create multiple resources, update state, and close.
    // Then list tempDir and assert the expected filenames.
}
~~~

This is an illustrative skeleton; supply items and drive the writer lifecycle or run through a step test matching your project's API version. With a limit of 2 and 5 items, expect three resources: two full files of two items and one final file with one item. Verify actual filenames and per-file item counts by reading the outputs back.

## 27. Testing file extensions and contents

Tests should verify:

- The extension sits at the very end of the filename.
- No doubled extensions such as **.csv.csv** appear.
- Every resource follows the same naming convention.
- Resource indexes increase sequentially.
- Each file carries a header if required by contract.
- The final file contains the exact remaining item count.
- Item contents are neither lost nor duplicated during rollover.

Do not assert only the filename list. Read back all files, collect business keys, and confirm total items match inputs with every key appearing the expected number of times.

## 28. Testing restarts with suffix creators

Restart tests must use the exact same base resource, suffix creator, delegate name, and item count limit as the initial run:

1. Launch the job and let several chunks commit.
2. Intentionally fail the job after one or more resources are created.
3. Capture the committed resource list and contents.
4. Restart the same **JobInstance**.
5. Verify the writer resumes at the checkpointed resource/index.
6. Verify no random filenames are generated for the same part.
7. Read back all parts and confirm zero missing or duplicated items.

If the suffix creator or base resource changes between the first run and restart, tests should verify the application rejects incompatible configurations or starts a new output version. Never silently continue partial output under a different naming convention.

## 29. Testing two concurrent jobs generating output

Two distinct **JobInstance** executions can run simultaneously. If they share a base resource, both may attempt to create identical part names:

~~~text
orders-part-001.csv
orders-part-002.csv
~~~

Concurrency tests should verify either:

- Each instance owns a distinct base path/output key, or
- One instance holds a reservation and the other is cleanly rejected.

Suffix indexes are unique only within a single writer/instance; they do not provide a global namespace. Never treat **part-001** as unique across all jobs.

## 30. Suffixes for JSON, XML, or other formats

Because the suffix creator changes only resource names, it applies equally to delegates writing other formats, provided the delegate satisfies the wrapper's resource-aware contract.

Example naming:

~~~text
orders-part-001.json
orders-part-002.json
orders-part-003.json
~~~

or:

~~~text
orders-part-001.xml
orders-part-002.xml
~~~

However, each resource must be a complete, valid document. For JSON, each file may need to be a valid JSON array; for XML, each file requires its own root element. Test the delegate's header/footer/document framing across every rollover.

## 31. When to use suffixes vs. other naming strategies

**ResourceSuffixCreator** fits when:

- All files share a single base name.
- Parts are numbered sequentially.
- You only need to append a suffix from the resource index.
- Naming rules are simple and deterministic.

A custom wrapper or different writer may be needed when:

- Filenames depend on data from the first item in each resource.
- Rollover must happen by byte size rather than item count.
- Each resource uses a different schema or format.
- Subdirectories must be created dynamically per tenant or partition.
- Names depend on timestamps of individual data windows.

Do not try to cram complex business logic into a suffix creator. It receives only an index and returns a suffix string; if naming depends on information outside that interface, prepare the base resource from job context or choose a better-suited abstraction.

## 32. Common pitfalls

| Situation | Cause | Remedy |
|---|---|---|
| Files named orders.csv.1 instead of orders-1.csv | Default suffix appended after full base filename | Use an extensionless base and custom suffix |
| Files contain .csv.csv | Extension present in both base and suffix | Compute final filenames before configuring |
| Part names unstable on restart | Suffix creator uses UUID/timestamp/mutable counter | Derive purely from writer-supplied index |
| New resource written to wrong folder | Suffix contains path separators or unchecked base path | Keep suffix as filename fragment and validate paths |
| Two jobs write the same part file | Base resource does not distinguish `JobInstance` | Embed business identity/version in base path |
| Part file lacks header | Delegate/header callback not configured per-resource lifecycle | Test individual files after rollover |
| Final file has missing/extra items | Confused chunk size with item count limit | Check `itemCountLimitPerResource` and read back each part |
| Restart creates duplicate or wrong parts | Suffix creator or item limit changed across restart | Keep naming/config stable per `JobInstance` |
| Downstream reads incomplete file set | Scanning by pattern without a manifest | Publish a manifest after validating all resources |
| Tests check only suffix creator | Did not verify wrapper combining suffix with base resource | Integration-test `MultiResourceItemWriter` |
| Files sort out of order | Index lacks zero-padding | Format with sufficient pad width |
| Old files get overwritten | Same base/index reused | Use output versioning, reservations, and staging |

## 33. Output suffix design checklist

1. **Define the filename contract:** what extension, prefix, part numbering, and sort order do consumers expect?
2. **Choose the base resource:** include directory, job/business identity, and common root name.
3. **Select the suffix creator:** use the default if `.1`, `.2` work; otherwise implement `ResourceSuffixCreator`.
4. **Standardize index formatting:** keep zero-padding, prefix, and extension consistent.
5. **Keep the creator deterministic:** the same index always returns the same suffix.
6. **Configure rollover separately:** set `itemCountLimitPerResource` without confusing it with chunk size.
7. **Configure the delegate:** ensure it accepts new resources and handles headers/footers properly.
8. **Plan for restarts:** keep base resource, creator, writer name, and item limit stable.
9. **Protect outputs:** use unique base identities, staging, and collision detection.
10. **Produce a manifest:** record filenames, record counts, checksums, and publish status.
11. **Test the real writer:** assert actual filenames, extensions, item counts, contents, and restarts.
12. **Test concurrency:** verify distinct `JobInstance` runs never share output namespaces accidentally.

## 34. Principles to remember

- **MultiResourceItemWriter** splits output across multiple resources and calls the suffix creator when opening each next resource.
- **ResourceSuffixCreator** accepts a resource index and returns the suffix appended to the base resource.
- **SimpleResourceSuffixCreator** by default creates numeric suffixes like `.1`, `.2` per Spring Batch conventions.
- The suffix is appended to the base resource name; the writer does not automatically move extensions to the end.
- To produce **orders-part-001.csv**, use base **orders** and suffix **-part-001.csv**.
- Use zero-padding if downstream needs to sort files alphabetically by name.
- Suffix creators must be deterministic and stateless; never use UUIDs, current timestamps, or mutable counters across calls.
- **itemCountLimitPerResource** triggers rollover; chunk size controls transaction batches.
- Delegates must support resource-aware writing and compatible lifecycle/state management.
- Headers/footers normally need per-file generation; verify with rollover tests.
- Keep base resource, suffix creator, writer name, and item limit stable across restarts.
- Suffix indexes are unique only within one writer; base resources must distinguish outputs of different `JobInstance` executions.
- Suffix creators do not prevent overwrites; use staging, output versioning, reservations, or conditional creates.
- Manifests tell downstream when all parts are complete and verifiable.
- Test actual filenames, file contents, record counts, restarts, and concurrency.

Output filename suffixes are part of a batch job's output contract. When the base resource properly encodes output identity, the suffix creator deterministically formats indexes, and the writer is tested across rollovers and restarts, every part file carries a stable, sortable name ready for safe downstream consumption.
