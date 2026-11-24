# Resource Comparator

In Spring Batch, `MultiResourceItemReader<T>` allows a Step to sequentially read multiple resources using a single delegate reader. When there are multiple input files, the file reading order directly impacts the order in which items are emitted. A `Comparator<Resource>` determines the order in which `MultiResourceItemReader` iterates through those resources.

For example, a Job imports data from `orders-001.csv`, `orders-002.csv`, and `orders-003.csv`. If the file order carries meaning by date, sequence number, or batch sequence, you must configure a comparator to ensure the reader opens files in the right order. The comparator is also critical for restarts: Spring Batch persists the current resource index, so the resource list and sort order must remain stable between the initial run and restarts.

## 1. How does MultiResourceItemReader read multiple files?

`MultiResourceItemReader<T>` is a reader wrapping a delegate reader. It manages an array of `Resource` objects, selects the current resource, and hands off reading that resource's contents to the delegate.

Suppose there are three files:

```text
inbound/
  orders-001.csv
  orders-002.csv
  orders-003.csv
```

Processing flow:

```text
MultiResourceItemReader<Order>
          |
          +--> resource[0] --> FlatFileItemReader --> Orders in file 001
          |
          +--> resource[1] --> FlatFileItemReader --> Orders in file 002
          |
          +--> resource[2] --> FlatFileItemReader --> Orders in file 003
          |
          +--> no more resources --> null
```

The delegate is responsible for reading each line or item within a single file. `MultiResourceItemReader` is responsible for advancing to the next resource once the delegate has finished reading the current resource.

The comparator does not sort lines inside each file. It only sorts the resource list before the reader iterates over them. Line ordering within each file is determined by the delegate reader and file structure.

## 2. What is the role of Comparator<Resource>?

`Comparator<Resource>` defines the comparison rule between two resources. `MultiResourceItemReader` uses the comparator to sort the resource array before reading begins.

A comparator takes the form:

```java
public interface Comparator<T> {
    int compare(T first, T second);
}
```

Result semantics:

- Negative value: `first` precedes `second`.
- Zero: the two resources are considered equal under the comparison criterion.
- Positive value: `first` follows `second`.

Example sorting by filename:

```java
Comparator<Resource> byFilename =
        Comparator.comparing(Resource::getFilename);
```

In a standard setup, `MultiResourceItemReader` has a default comparator based on filename. However, whenever order has business significance, declare an explicit comparator so the sorting rule is visible in configuration and testable.

## 3. Why does resource order matter?

Resource order can affect:

- The order in which items are emitted by the reader.
- The order in which data groups are written or processed.
- Outcomes when data across files has ordering dependencies.
- Checkpoint position and restartability.
- Reproducibility of results across runs.

For example, suppose files contain daily data:

```text
orders-2026-11-13.csv
orders-2026-11-14.csv
orders-2026-11-15.csv
```

If the Job needs to read in ascending date order, the comparator must sort by the date parsed from the filename or equivalent metadata. Do not rely on the order returned by the filesystem or resource resolver, as file listing order is not always guaranteed.

When a Step is restartable, resource order must remain consistent with the persisted checkpoint. If the initial run read files A, B, C, but a restart sorts them as B, A, C, the current resource index could point to a different file.

## 4. Basic MultiResourceItemReader configuration

You can use `MultiResourceItemReaderBuilder<T>` to configure the resource list, delegate, and comparator:

```java
@Bean
public MultiResourceItemReader<Order> multiOrderReader(
        Resource[] orderResources,
        FlatFileItemReader<Order> orderFileDelegate,
        Comparator<Resource> orderResourceComparator) {

    return new MultiResourceItemReaderBuilder<Order>()
            .name("multiOrderReader")
            .resources(orderResources)
            .delegate(orderFileDelegate)
            .comparator(orderResourceComparator)
            .saveState(true)
            .build();
}
```

Key configuration options:

- `name(...)`: a stable name for the multi-resource reader, used for reader state.
- `resources(...)`: the resources to read.
- `delegate(...)`: the reader that reads each resource.
- `comparator(...)`: the resource sorting rule.
- `saveState(true)`: enables checkpoint saving to support restarts.

The delegate is commonly `FlatFileItemReader<T>` or a reader implementing `ResourceAwareItemReaderItemStream<T>`, allowing `MultiResourceItemReader` to inject the current resource into the delegate before opening it.

## 5. Configuring the FlatFileItemReader delegate

The delegate reads the contents of each file. It needs a line mapper, tokenizer, and field mapping configured just like a regular `FlatFileItemReader`.

```java
@Bean
public FlatFileItemReader<Order> orderFileDelegate() {
    return new FlatFileItemReaderBuilder<Order>()
            .name("orderFileDelegate")
            .delimited()
            .delimiter(",")
            .names("orderId", "customerName", "amount")
            .targetType(Order.class)
            .linesToSkip(1)
            .saveState(true)
            .build();
}
```

In this example, no resource is bound statically in the builder because the resource is supplied by `MultiResourceItemReader` when switching files. `FlatFileItemReader` supports receiving resources through the `ResourceAwareItemReaderItemStream` contract.

The delegate name should also be stable. The multi-resource reader and the delegate may store distinct state entries in the same Step `ExecutionContext`; separate names prevent state key collisions.

## 6. Sorting by filename

If filenames are formatted such that lexicographical order matches the desired order, you can use a filename comparator:

```java
@Bean
public Comparator<Resource> orderResourceComparator() {
    return Comparator.comparing(
            Resource::getFilename,
            Comparator.nullsLast(Comparator.naturalOrder())
    );
}
```

This comparator sorts names in ascending string order. `nullsLast` places resources without a filename at the end; in production applications, you should usually validate resources and reject null filenames rather than silently accepting them.

For example:

```text
orders-001.csv
orders-002.csv
orders-010.csv
```

Because sequence numbers are zero-padded, lexicographical order matches the desired numeric order.

This is straightforward when naming conventions are controlled. If filenames are not zero-padded, you need a comparator that understands the numeric part rather than plain string comparison.

## 7. Lexical ordering pitfalls with sequence numbers

String sorting is not numeric sorting. For example:

```text
orders-1.csv
orders-10.csv
orders-2.csv
```

Lexicographical order produces:

```text
orders-1.csv
orders-10.csv
orders-2.csv
```

Whereas the desired numeric order is:

```text
orders-1.csv
orders-2.csv
orders-10.csv
```

If sequence numbers represent a business sequence, parse the numeric portion and use `Comparator.comparingLong(...)` or `Comparator.comparingInt(...)` rather than relying on raw filename strings.

Another option is requiring zero-padded filenames, such as `orders-0001.csv`. That approach is simple, though only reliable when digit width is fixed and the file producer strictly adheres to the convention.

## 8. Comparator by sequence number in filename

Suppose files follow `orders-<sequence>.csv`. You can parse the sequence using a regex:

```java
private static final Pattern ORDER_FILE_PATTERN =
        Pattern.compile("orders-(\\d+)\\.csv");

private static long sequenceOf(Resource resource) {
    String filename = Objects.requireNonNull(
            resource.getFilename(), "Resource filename must not be null");

    Matcher matcher = ORDER_FILE_PATTERN.matcher(filename);
    if (!matcher.matches()) {
        throw new IllegalArgumentException(
                "Unexpected order file name: " + filename);
    }

    return Long.parseLong(matcher.group(1));
}

@Bean
public Comparator<Resource> orderResourceComparator() {
    return Comparator.comparingLong(MyBatchConfiguration::sequenceOf)
            .thenComparing(Resource::getFilename)
            .thenComparing(Resource::getDescription);
}
```

This comparator:

1. Verifies that a filename exists.
2. Enforces that the filename matches the expected format.
3. Parses the sequence as a number.
4. Compares in ascending sequence order.
5. Uses filename and description as tie-breakers for deterministic ordering if sequences collide.

If sequences can exceed `long` range, use `BigInteger`. Do not parse numbers with `Integer` if sequence scale could grow large.

Failing fast on malformed filenames is generally better than pushing invalid files to the start or end of the list, since an unexpected name may indicate an upstream manifest or batch error.

## 9. Comparator by business date

If filenames contain dates, parse them into date types rather than comparing strings if formats could vary or fail to sort lexicographically.

For example, filename `orders-15-11-2026.csv` using `dd-MM-yyyy`:

```java
private static final Pattern DAILY_FILE_PATTERN =
        Pattern.compile("orders-(\\d{2}-\\d{2}-\\d{4})\\.csv");

private static LocalDate businessDateOf(Resource resource) {
    String filename = Objects.requireNonNull(resource.getFilename());
    Matcher matcher = DAILY_FILE_PATTERN.matcher(filename);

    if (!matcher.matches()) {
        throw new IllegalArgumentException("Invalid daily file name: " + filename);
    }

    return LocalDate.parse(
            matcher.group(1),
            DateTimeFormatter.ofPattern("dd-MM-uuuu")
    );
}

@Bean
public Comparator<Resource> dailyResourceComparator() {
    return Comparator.comparing(MyBatchConfiguration::businessDateOf)
            .thenComparing(Resource::getFilename)
            .thenComparing(Resource::getDescription);
}
```

As a result, files with earlier business dates are read first. If a single day has multiple part files, add the sequence or part number to the comparator:

```java
Comparator<Resource> comparator =
        Comparator.comparing(MyBatchConfiguration::businessDateOf)
                .thenComparingLong(MyBatchConfiguration::partNumberOf)
                .thenComparing(Resource::getDescription);
```

Date and part ordering must reflect the data contract. Never use `lastModified()` as a business date if file modification timestamps can change during copying, restoring, or archiving.

## 10. Multi-criteria comparators

A comparator can combine multiple criteria using `thenComparing(...)`:

```java
Comparator<Resource> comparator =
        Comparator.comparing(MyBatchConfiguration::businessDateOf)
                .thenComparing(MyBatchConfiguration::regionOf)
                .thenComparingLong(MyBatchConfiguration::sequenceOf)
                .thenComparing(Resource::getDescription);
```

The ordering above means:

1. Ascending business date.
2. Within the same date, region in string order.
3. Within the same region, ascending sequence.
4. If business keys still tie, use resource description as a tie-breaker.

Document the priority order clearly in method names or comments so maintainers understand why file A must precede file B. Avoid writing complex comparators with deeply nested `if` branches that are hard to test.

## 11. Comparators must enforce a total and stable order

A comparator must obey Java's contract: comparisons must be consistent, transitive, and invariant during sorting. An unstable comparator can cause resource order to vary between runs.

Practical rules:

- The same pair of resources must yield the same comparison result under the same conditions.
- Do not depend on counters that mutate across invocations.
- Do not read file contents or make API calls inside a comparator.
- Do not use the current wall-clock time as a sorting criterion.
- Define clear handling for null or invalid filenames.
- If two resources share the same business key, add a deterministic tie-breaker.
- Avoid depending on input array order if the resolver can return resources in varying order.

Example of what not to do:

```java
Comparator<Resource> unstable = (left, right) ->
        ThreadLocalRandom.current().nextInt(-1, 2);
```

Results change on every comparison, violating the contract and potentially causing sort failures or non-deterministic order.

## 12. Handling duplicate filenames

Two resources can share the same filename while residing in different directories:

```text
region-a/orders-001.csv
region-b/orders-001.csv
```

If the comparator compares only `getFilename()`, both resources evaluate as equal. Their relative order then depends on the initial input array order.

If both files come from distinct sources and deterministic order is required, include criteria such as region, path, or resource description:

```java
Comparator<Resource> comparator =
        Comparator.comparing(Resource::getFilename)
                .thenComparing(Resource::getDescription);
```

In a filesystem environment, you can use a normalized path as a tie-breaker if the application manages concrete paths. For resources without filesystem paths, pick a stable identifier provided by the resource source.

If two resources match across all comparison keys, decide whether that is an unintended duplicate or two valid copies. Never silently drop a resource just because the comparator returned 0; deduplication is not the comparator's responsibility.

## 13. Combining ResourcePatternResolver and a comparator

`ResourcePatternResolver` is commonly used to locate files by pattern before passing the resource list to `MultiResourceItemReader`:

```java
@Bean
public Resource[] orderResources(ResourcePatternResolver resolver) throws IOException {
    return resolver.getResources("file:/var/batch/inbound/orders-*.csv");
}
```

Do not rely on the order returned by `getResources(...)`. Let `MultiResourceItemReader` apply an explicit comparator.

Combined example:

```java
@Bean
public MultiResourceItemReader<Order> multiOrderReader(
        Resource[] orderResources,
        FlatFileItemReader<Order> orderFileDelegate,
        Comparator<Resource> orderResourceComparator) {

    return new MultiResourceItemReaderBuilder<Order>()
            .name("multiOrderReader")
            .resources(orderResources)
            .delegate(orderFileDelegate)
            .comparator(orderResourceComparator)
            .saveState(true)
            .build();
}
```

If the pattern matches zero files, define an explicit policy: is the Job allowed to complete with zero items, or must it fail for missing input? You can use the reader's strict behavior or a pre-run resource check. Never let an empty list be mistaken for a batch that successfully processed data.

## 14. MultiResourceItemReader and checkpointing

`MultiResourceItemReader` tracks progress at the current resource level and coordinates with the delegate to track progress inside that resource. On restart, the reader needs to know which file it is on, and the delegate needs to know which item inside that file it is on.

For example:

```text
Sorted resource list:
  0 -> orders-001.csv
  1 -> orders-002.csv
  2 -> orders-003.csv

Committed checkpoint:
  current resource index = 1
  delegate state = next line/item in orders-002.csv
```

On restart, the reader reopens the resource at index 1 in the sorted list and restores the delegate's state. Consequently, the comparator is part of the restart contract: the same inputs must produce the exact same list and resource order.

Both the multi-resource reader name and the delegate name should be stable. `saveState(true)` must be enabled on the reader if checkpoints are to be persisted. The delegate must also support `ItemStream` if it holds intra-file state.

## 15. Why changing the comparator can break restarts

Suppose the initial run uses the order:

```text
0 -> file-A.csv
1 -> file-B.csv
2 -> file-C.csv
```

The Job commits halfway through `file-B.csv`, saving resource index 1 and the delegate state in the checkpoint. Before restarting, the comparator is changed so the order becomes:

```text
0 -> file-B.csv
1 -> file-A.csv
2 -> file-C.csv
```

Index 1 now points to `file-A.csv`, while the saved delegate state corresponds to what was already read in `file-B.csv`. This can cause missed records, duplicate reads, or mapping/checkpoint failures.

Dangerous changes include:

- Changing the comparator between runs.
- Adding a new file that sorts ahead of the current resource.
- Deleting an already-read or current file.
- Renaming a file in a way that alters sort order.
- Changing the pattern so the resource list differs.
- Changing how dates/sequences are parsed from filenames.
- Using mutable criteria such as last-modified time.

For restartable Jobs, keep the resource list and comparator unchanged for the lifetime of the `JobInstance`. If the file set changes, treat it as a new batch input or persist a manifest to reconstruct the exact original list.

## 16. Using a manifest to keep the resource set stable

For critical batches, create a manifest before launching the Job. The manifest enumerates the files belonging to the batch in a fixed order:

```text
batchId=20261115-001
files:
  - /var/batch/staging/orders-20261115-001.csv
  - /var/batch/staging/orders-20261115-002.csv
  - /var/batch/staging/orders-20261115-003.csv
```

The Job uses the manifest or batch ID to reconstruct the exact file set on restart. You can store checksums, sizes, and versions for each file to confirm sources were not altered.

A manifest prevents a wildcard like `orders-*.csv` from accidentally picking up newly arrived upstream files while an older Job is mid-execution. A comparator is still valuable for ordering resources by business rules, while the input membership remains locked.

Do not store a massive list of paths inside `ExecutionContext` when the manifest can reside in durable storage referenced by batch ID. `ExecutionContext` should keep checkpoints compact rather than becoming a large file catalog.

## 17. Comparator and delegate reader are distinct responsibilities

The comparator orders resources; the delegate reads each resource's contents. These two parts do not substitute for one another.

| Component | Responsibility |
|---|---|
| `Resource[]` | List of files/resources to read |
| `Comparator<Resource>` | Order in which resources are traversed |
| `MultiResourceItemReader` | Manages the current resource and transitions the delegate to the next |
| `ResourceAwareItemReaderItemStream` delegate | Receives the current resource and reads items inside it |
| `LineMapper`/`RowMapper`/parser | Converts each raw record into an object |

If items inside each file need sorting by `orderId`, a resource comparator will not solve that. Ensure files are pre-sorted properly or have the delegate/query handle item ordering appropriately.

Similarly, if multiple files must be processed in parallel, a comparator only defines sequential order. It does not create partitions or concurrency. Use a partitioned Step where each worker handles a resource or group of resources if higher throughput is required.

## 18. Resource comparators in partitioning

In some designs, each file is assigned to a partition. In that case, distributing resources to partitions is handled by a `Partitioner` or splitting logic, while a comparator can establish order before partitions are created.

For example:

```text
Resource list
   |
   v
Sort by business date / sequence
   |
   +--> partition-0: file A
   +--> partition-1: file B
   +--> partition-2: file C
```

If each file can be processed independently, partitions can run in parallel. However, when data across files has ordering dependencies, do not run them in parallel merely because the resources were sorted. Sort order does not guarantee partitions will finish in that order.

If sequential ordering across files is required, use `MultiResourceItemReader` in a sequential Step or split into Steps/flows with explicit dependencies. If partitioning is required, ensure each partition is independent and outputs can be merged safely.

## 19. Validating resources before sorting

A comparator should not shoulder all resource validation. Before passing resources to the reader, you can verify:

- Filenames exist and conform to the naming convention.
- Resources exist and are readable.
- Resources reside within authorized directories/batches.
- No duplicate files or temporary files such as `.part` or `.tmp` matched the pattern.
- Date/sequence metadata parses cleanly.
- The file set is finalized before the Job begins.

Example filename validation helper:

```java
private static void validateOrderResources(Resource[] resources) {
    for (Resource resource : resources) {
        String filename = resource.getFilename();
        if (filename == null || !ORDER_FILE_PATTERN.matcher(filename).matches()) {
            throw new IllegalArgumentException(
                    "Invalid order resource: " + resource.getDescription());
        }
    }
}
```

When a resource is invalid, failing before opening the reader makes investigation much easier than letting a comparator push the bad file to the end and failing only when reading reaches it.

## 20. Common pitfalls

**Relying on ResourcePatternResolver's return order.** Listing order is not a business contract. Configure an explicit comparator.

**Comparing sequence numbers as strings.** `file-10` may sort before `file-2`. Parse the numeric portion or use zero-padded names.

**Omitting tie-breakers.** Two resources sharing the same date/sequence could be treated as equal, making order input-dependent. Add a stable filename/path/description tie-breaker.

**Using lastModified as the primary criterion.** Timestamps can change during copy, restore, or archive operations; restarts may compute a different order.

**Changing the comparator on a restartable Job.** The resource index can point to a different file. Keep the comparator and resource set stable.

**Confusing a resource comparator with item sorting.** The comparator sorts files, not records within a file.

**Assuming a comparator enables parallel processing.** `MultiResourceItemReader` iterates through resources sequentially. For parallel execution, design partitioning.

**Using a comparator to deduplicate files.** Returning 0 from a comparator does not cause the framework to drop a resource. Implement dedicated validation/deduplication if required.

**Letting malformed filenames slip into the list silently.** Validate before opening the Step and fail explicitly when inputs violate the contract.

## 21. Testing comparators

Test your comparator in isolation using filenames representative of real scenarios:

```java
@Test
void sortsOrderFilesByNumericSequence() {
    List<Resource> resources = new ArrayList<>(List.of(
            new FileSystemResource("/inbound/orders-10.csv"),
            new FileSystemResource("/inbound/orders-2.csv"),
            new FileSystemResource("/inbound/orders-1.csv")
    ));

    resources.sort(orderResourceComparator());

    assertEquals(
            List.of("orders-1.csv", "orders-2.csv", "orders-10.csv"),
            resources.stream().map(Resource::getFilename).toList()
    );
}
```

Scenarios to test:

1. Filenames with single-digit and multi-digit sequence numbers.
2. Two files with the same sequence in different directories.
3. Null filenames or filenames violating the naming convention.
4. Business dates spanning multiple months and years.
5. Two resources sharing all business keys that require a tie-breaker.
6. The same resource list consistently producing the same order.
7. Resource resolver returning inputs in shuffled order while the comparator produces the exact same output order.
8. Empty resource list with strict policy applied properly.

## 22. Testing MultiResourceItemReader and restarts

Unit testing the comparator alone does not prove the reader switches files and restores checkpoints properly. Integration tests with the delegate reader are needed:

1. Create two or three fixture files containing records with easily identifiable IDs.
2. Configure `MultiResourceItemReader` with the comparator and delegate.
3. Read everything and verify records appear in exact file order.
4. Use a chunk/Step test to commit part of the first file and part of the next file.
5. Stop the Job after a checkpoint, then restart the same `JobInstance` with the exact same resource list.
6. Verify the reader resumes on the exact file and exact intra-file position.
7. Try adding, deleting, renaming, or modifying a file before restart to verify manifest/version checks detect the change.
8. Verify the delegate `ItemStream` goes through `open`/`update`/`close` lifecycle calls properly.

Restart integration tests require `JobRepository` to persist metadata across runs. Creating fresh readers/repositories without preserving `ExecutionContext` only tests reading from scratch, not checkpoint restoration.

## 23. How to design a resource comparator

Choose sorting criteria that reflect business order: zero-padded filenames, numeric sequences, business dates, regions, or a key from a manifest. Use an explicit comparator with stable tie-breakers, and reject resources that violate naming conventions. Never depend on filesystem traversal order or mutable properties like modification timestamps.

Pass the comparator into `MultiResourceItemReaderBuilder` alongside the resource list and delegate reader. Give the reader and delegate stable names and enable `saveState` when restartability is needed. Keep the resource list, file contents, and comparator constant throughout the `JobInstance` lifecycle; if the file set can change, generate a manifest or batch snapshot before launching.

The comparator only determines file order. The delegate remains responsible for reading items within each file, while partitioning governs parallel execution. Keeping these responsibilities distinct allows `MultiResourceItemReader` to read multiple files in a reproducible order and restore checkpoints reliably after Job interruptions.
