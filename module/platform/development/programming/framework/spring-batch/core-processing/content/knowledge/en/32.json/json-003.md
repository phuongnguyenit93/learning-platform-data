# Large JSON Arrays and Streaming

When processing a JSON file containing hundreds of thousands or millions of objects, reading the entire document into a `List` can make memory grow with file size. If the file exceeds available heap, the application may encounter `OutOfMemoryError`, prolonged GC pauses, or severely degraded throughput.

In Spring Batch, the appropriate approach for large JSON arrays is to read object by object in a streaming manner, feed each item into chunk processing, and write results chunk by chunk. `JsonItemReader` combined with `JacksonJsonObjectReader` supports this model: the reader traverses the JSON array and creates one Java object per read call, instead of deserializing the entire array into an in-memory collection.

Streaming does not mean memory is strictly constant. Memory still depends on the size of the largest object, chunk size, buffers, processor, writer, and data retained by the application. Therefore, you must design the JSON format, reader, chunk size, and checkpoints together.

## 1. Why Do Large JSON Arrays Need Streaming?

A typical JSON array file looks like this:

```json
[
  {"id":"C001","name":"Nguyen An","active":true},
  {"id":"C002","name":"Tran Binh","active":false},
  {"id":"C003","name":"Le Chi","active":true}
]
```

Each element in the array is an independent item. If you read the whole file at once:

```java
List<Customer> customers = objectMapper.readValue(
        inputFile,
        new TypeReference<List<Customer>>() {});
```

Jackson has to create the collection and hold every `Customer` in memory at the same time. With one million items, memory holds not only the file's bytes, but also object headers, Strings, collection entries, field objects, and temporary data during parsing.

With streaming, the parser reads one object at a time:

```text
JSON array on disk
       |
       v
Parser reads next object
       |
       v
One Java item
       |
       v
Spring Batch collects up to chunk-size items
       |
       v
Processor / Writer
       |
       v
Commit chunk and release processed items
       |
       v
Read next object
```

Instead of holding the whole list, the application holds parser state, the item currently being read, items in the active chunk, and necessary buffers. This makes processing large files have more predictable and controllable memory usage.

## 2. Streaming vs. Full Deserialization

The two approaches have different memory characteristics:

| Reading approach | How it works | Memory profile |
|---|---|---|
| Full array deserialization | `ObjectMapper.readValue(... List<T>)` builds a list containing every object. | Grows with total item count and the entire file's data. |
| Item-by-item streaming | Parser reads one object, returns it to the reader, then continues. | Mainly depends on current object, chunk, buffers, and state. |
| Manual streaming | Use Jackson `JsonParser` or StAX-like token processing to read tokens and manage item boundaries yourself. | Allows finer control, but you must manage lifecycle, errors, and checkpoints yourself. |

Example to avoid for very large files:

```java
List<Customer> allCustomers = objectMapper.readValue(
        resource.getInputStream(),
        new TypeReference<List<Customer>>() {});

for (Customer customer : allCustomers) {
    customerService.process(customer);
}
```

This snippet may suit small files, but does not leverage Spring Batch's chunk processing and checkpoints. If the job fails mid-loop, the application must also design its own continuation and duplicate-prevention logic.

## 3. JSON Structures Supported by JsonItemReader

Spring Batch's `JsonItemReader<T>` is designed to read a JSON resource whose root is an array of objects. Example:

```json
[
  {"customerId":"C001","name":"Nguyen An"},
  {"customerId":"C002","name":"Tran Binh"}
]
```

Each object in the array becomes one item of type `T`. The reader does not need to construct a `List<T>` holding the whole array.

This format differs from several other JSON styles:

**An object wrapping the entire collection:**

```json
{
  "batchDate": "2026-11-15",
  "customers": [
    {"customerId":"C001"},
    {"customerId":"C002"}
  ]
}
```

If the reader is designed to read an array at the root, this wrapper object structure does not match directly. You need a custom reader, input normalization, or a parser designed to navigate to the `customers` array.

**JSON Lines / NDJSON:**

```text
{"customerId":"C001","name":"Nguyen An"}
{"customerId":"C002","name":"Tran Binh"}
{"customerId":"C003","name":"Le Chi"}
```

Each line is a separate JSON document with no enclosing array brackets. `JsonItemReader` for JSON arrays should not be assumed to be an NDJSON reader. For JSON Lines, you can use a custom `ItemStreamReader` reading line by line and deserializing each line, or use a format-appropriate reader.

## 4. Spring Batch JSON Components

Spring Batch provides abstractions to read and write JSON item by item:

| Component | Responsibility |
|---|---|
| `JsonItemReader<T>` | Reads a JSON array item by item. |
| `JsonObjectReader<T>` | Converts a single JSON object into a Java object. |
| `JacksonJsonObjectReader<T>` | `JsonObjectReader` implementation using Jackson. |
| `GsonJsonObjectReader<T>` | Implementation using Gson. |
| `JsonFileItemWriter<T>` | Writes items as a JSON array. |
| `JsonObjectMarshaller<T>` | Converts a single Java object into a JSON representation. |
| `JacksonJsonObjectMarshaller<T>` | Marshaller implementation using Jackson. |
| `GsonJsonObjectMarshaller<T>` | Marshaller implementation using Gson. |

Spring Batch manages invoking the reader/writer per chunk. Jackson or Gson handles converting one object at a time.

## 5. Configuring JsonItemReader with Jackson

Suppose each item is a customer:

```java
public record Customer(
        String customerId,
        String name,
        String email,
        boolean active) {
}
```

Reader configuration:

```java
@Bean
@StepScope
JsonItemReader<Customer> customerJsonReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new JsonItemReaderBuilder<Customer>()
            .name("customerJsonReader")
            .resource(new FileSystemResource(inputFile))
            .jsonObjectReader(new JacksonJsonObjectReader<>(Customer.class))
            .saveState(true)
            .build();
}
```

Key parts:

- `name(...)` sets a stable name for the reader; this name is used in metadata/checkpoints.
- `resource(...)` specifies the input JSON file.
- `jsonObjectReader(...)` selects how each object is deserialized.
- `saveState(true)` lets the reader store its read position in `ExecutionContext` to support restart.
- `@StepScope` allows obtaining the input path from the run's `JobParameters`.

`JsonItemReader` reads elements from the root array and returns one `Customer` per `read()` call. There is no need to call `ObjectMapper.readValue` with `List<Customer>`.

## 6. Integrating the Reader into a Chunk-Oriented Step

Once configured, the reader can be used like any other `ItemReader`:

```java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JsonItemReader<Customer> customerJsonReader,
        ItemProcessor<Customer, Customer> customerProcessor,
        ItemWriter<Customer> customerWriter) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<Customer, Customer>chunk(500, transactionManager)
            .reader(customerJsonReader)
            .processor(customerProcessor)
            .writer(customerWriter)
            .build();
}
```

With chunk size 500, the step reads up to 500 items for a chunk, processes them, and calls the writer. When the transaction commits, the framework updates checkpoints according to the reader/step lifecycle.

Chunk size is a parameter that requires measurement:

- Too small a chunk increases commit count and metadata overhead.
- Too large a chunk increases the number of objects coexisting on the heap and lengthens transactions.
- Objects with nested collections or large payloads need smaller chunks.
- Writers calling databases or external services may have their own batch limits.

There is no single right chunk size for every file. Benchmark with item sizes and infrastructure close to production.

## 7. Reading an Object with a Nested Array

A JSON item can contain nested collections inside:

```json
[
  {
    "orderId": "O-100",
    "customerId": "C001",
    "lines": [
      {"sku":"SKU-01","quantity":2},
      {"sku":"SKU-02","quantity":1}
    ]
  },
  {
    "orderId": "O-101",
    "customerId": "C002",
    "lines": [
      {"sku":"SKU-03","quantity":4}
    ]
  }
]
```

The model can be:

```java
public record OrderLine(String sku, int quantity) {
}

public record Order(
        String orderId,
        String customerId,
        List<OrderLine> lines) {
}
```

`JsonItemReader<Order>` reads one order at a time. However, all `lines` of the current order are still deserialized into a `List<OrderLine>`.

This means item-level streaming does not automatically break down nested arrays. If one order contains millions of lines, a single item can still be very large. In that case, consider:

- Changing the item unit to individual lines if business rules allow.
- Using a custom streaming reader to read the nested array element by element.
- Splitting the input into multiple smaller files/partitions.
- Limiting element count or payload size per object.
- Reading only needed fields if a custom streaming parser can be used.

## 8. Streaming with Jackson JsonParser

At a lower level, Jackson provides a streaming API via `JsonFactory` and `JsonParser`. The parser traverses tokens one by one without building a JSON tree (`JsonNode`) for the entire document.

Conceptual example reading a root array:

```java
try (InputStream input = resource.getInputStream();
     JsonParser parser = jsonFactory.createParser(input)) {

    JsonToken first = parser.nextToken();
    if (first != JsonToken.START_ARRAY) {
        throw new IllegalArgumentException("Expected a JSON array");
    }

    while (parser.nextToken() != JsonToken.END_ARRAY) {
        Customer customer = objectMapper.readValue(parser, Customer.class);
        process(customer);
    }
}
```

This snippet illustrates the principle: the parser advances to the start of each object and Jackson binds that object. `JsonItemReader` already wraps array-reading management and integration with Spring Batch, so prefer the built-in reader when the input format fits.

A custom parser is suitable when the structure is not a simple root array, special token handling is needed, a large nested array must be read as smaller items, or fine-grained per-token control is required.

Do not use `ObjectMapper.readTree(input)` for a huge JSON document if the goal is bounding memory. `readTree` constructs a node tree representing the document; it can still hold the entire structure in RAM.

## 9. When Do You Need a Custom ItemStreamReader?

`JsonItemReader` fits a root array of objects. You may need a custom reader in cases such as:

- JSON has an outer wrapper object before the target array.
- Input is NDJSON/JSON Lines.
- Nested arrays must be split into independent items.
- Metadata must be skipped or multiple object types handled via a discriminator.
- Exact checkpointing by byte offset, token, or record key is needed.
- Per-object size limits must be enforced before deserialization.

A custom reader must properly manage the `ItemStream` lifecycle:

| Method | Responsibility |
|---|---|
| `open(ExecutionContext)` | Opens resource/parser and restores checkpoint. |
| `read()` | Returns next item or `null` at end of data. |
| `update(ExecutionContext)` | Saves position/state for restart. |
| `close()` | Closes parser and resource. |

If the reader does not implement `ItemStream` or does not save state, restart may reread from the beginning or fail to recover position. For custom readers, define checkpoints so that only committed items count as processed.

## 10. Simple NDJSON Reader Example

NDJSON has one JSON object per line. A simple approach is reading line by line with `BufferedReader` and deserializing each line. The reader below illustrates storing the number of lines read; in real applications, consider file immutability and the cost of skipping to the checkpoint on restart.

```java
public class CustomerNdjsonReader implements ItemStreamReader<Customer> {

    private static final String LINE_KEY = "customerNdjsonReader.line";

    private final Resource resource;
    private final ObjectMapper objectMapper;
    private BufferedReader reader;
    private long lineNumber;

    public CustomerNdjsonReader(Resource resource, ObjectMapper objectMapper) {
        this.resource = resource;
        this.objectMapper = objectMapper;
    }

    @Override
    public void open(ExecutionContext context) throws ItemStreamException {
        try {
            reader = new BufferedReader(new InputStreamReader(
                    resource.getInputStream(), StandardCharsets.UTF_8));
            lineNumber = context.getLong(LINE_KEY, 0L);

            for (long i = 0; i < lineNumber; i++) {
                if (reader.readLine() == null) {
                    break;
                }
            }
        } catch (IOException exception) {
            throw new ItemStreamException("Cannot open NDJSON resource", exception);
        }
    }

    @Override
    public Customer read() throws Exception {
        String line = reader.readLine();
        if (line == null) {
            return null;
        }
        lineNumber++;
        if (line.isBlank()) {
            return read();
        }
        return objectMapper.readValue(line, Customer.class);
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong(LINE_KEY, lineNumber);
    }

    @Override
    public void close() throws ItemStreamException {
        try {
            if (reader != null) {
                reader.close();
            }
        } catch (IOException exception) {
            throw new ItemStreamException("Cannot close NDJSON resource", exception);
        }
    }
}
```

This is a simple example to explain line-based checkpointing, not an optimal implementation for every large file. On restart, the reader must read and skip checkpointed lines, so reopening time grows with position in the file. For very large files, byte offsets, indices, or splitting files into independent parts may be needed. If a single line can be huge, `readLine()` still creates a large String in memory; enforce line size limits or use a streaming parser over a byte stream.

A production reader also needs to handle blank lines, malformed lines, BOM, encoding, size limits, transactional checkpointing, and the case where the file changes between runs. Inputs must remain immutable throughout the lifecycle of the `JobInstance`.

## 11. JsonItemReader and Checkpoint/Restart

`JsonItemReader` supports saving read state through `ExecutionContext` when `saveState(true)` is set. When a chunk commits, Spring Batch updates reader state via the `ItemStream` mechanism.

Example:

```text
JSON array: [item1, item2, item3, item4, item5, ...]

Chunk 1: item1-item500 -> commit -> checkpoint
Chunk 2: item501-item1000 -> commit -> checkpoint
Chunk 3: item1001-item1500 -> failure before commit

Restart:
  restore committed checkpoint
  reread uncommitted portion
  continue with subsequent items
```

When designing for restart:

- Keep the reader name stable.
- Keep identifying `JobParameters` and the input resource unchanged.
- Keep `saveState(true)`.
- Do not modify file contents while the `JobInstance` may still restart.
- The writer must be idempotent or transactionally consistent so side effects are not duplicated.

If `saveState` is disabled, the reader cannot rely on default checkpointing to resume at the exact position. The Job may have to reread from the beginning or require another custom mechanism.

## 12. Input JSON Must Be Immutable Across Restarts

Checkpoints typically describe position/progress in the resource, not a snapshot of file contents. If the file changes between the initial run and restart, the same position may point to a different object.

Example:

```text
Initial run:
  item 1 = C001
  item 2 = C002
  item 3 = C003

Checkpoint after item 2

File replaced:
  item 1 = C100
  item 2 = C200
  item 3 = C300

Restarting from the position after item 2 may continue on a different dataset.
```

Store input files by batch ID, checksum, or immutable version. If data needs fixing, create a new `JobInstance`/batch according to business rules rather than silently swapping the file under an already-checkpointed `JobInstance`.

## 13. Streaming Writer for JSON Output

Spring Batch provides `JsonFileItemWriter<T>` to write items into a JSON array. You can use `JacksonJsonObjectMarshaller` to serialize each item.

Example:

```java
@Bean
@StepScope
JsonFileItemWriter<Customer> customerJsonWriter(
        @Value("#{jobParameters['outputFile']}") String outputFile) {

    return new JsonFileItemWriterBuilder<Customer>()
            .name("customerJsonWriter")
            .resource(new FileSystemResource(outputFile))
            .jsonObjectMarshaller(new JacksonJsonObjectMarshaller<>())
            .saveState(true)
            .shouldDeleteIfExists(true)
            .build();
}
```

The writer creates a JSON array and writes items chunk by chunk. This avoids collecting all results into a `List<Customer>` and serializing all at once.

When writing large output files, note:

- `saveState(true)` to support restart.
- Stable writer name and resource within the same `JobInstance`.
- Choose overwrite/append semantics according to the output lifecycle.
- Do not let multiple jobs/partitions write to the same file concurrently without synchronization.
- Verify the output JSON is valid after the job finishes.

## 14. JSON Writer and Transaction Boundaries

Chunk writers coordinate with the transaction manager to manage commits and state. However, the filesystem is not a typical database transaction resource. If the process dies right when writing/flushing the file, metadata and the physical file may need reconciliation.

For critical outputs, a safe pattern is:

1. Write JSON to a staging file dedicated to the `JobInstance`.
2. Complete the step and verify the JSON parses, item count, and checksum.
3. Publish via move/rename to the official filename.
4. Expose the file only after the publish step finishes.

If publishing succeeded but metadata commit failed, the restart must recognize the file was already published so the operation is idempotent. Do not assume a database transaction will automatically roll back a file rename.

## 15. Choosing Chunk Size for Large JSON

Chunk size directly impacts memory, throughput, and transaction duration.

Example for the same 2-million-item file:

| Chunk size | Approximate chunks | Characteristics |
|---:|---:|---|
| 50 | 40,000 | Short transactions, high commit overhead. |
| 500 | 4,000 | Can be a starting point for benchmarking. |
| 5,000 | 400 | Fewer commits, but more coexisting objects and longer transactions. |

These numbers are illustrative by division, not fixed chunk-size recommendations. Choose based on:

- Average and maximum object size.
- Number of fields and nested collections.
- Heap memory allocated to the batch worker.
- Processor and writer costs.
- Database batch insert/update capability.
- Transaction timeout and lock duration.
- Number of concurrent workers/partitions.

If items contain large payloads, a chunk size of 500 may still be too high. Start low, measure heap/GC/throughput, and tune upward. Do not optimize solely for items/second if doing so pushes heap close to OOM.

## 16. Streaming Does Not Eliminate All Memory Issues

Streaming bounds the number of objects materialized simultaneously, but memory pressure can still occur in cases such as:

- A single object has a very large nested array.
- The processor keeps objects in a cache or shared collection.
- The writer buffers the entire output before writing.
- The application stores every processed item in a `List` for statistics.
- Chunk size is too large.
- Many partitions run in parallel, each holding its own chunk.
- Jackson builds a `JsonNode` tree for huge objects instead of streaming-binding into the required model.

To keep memory bounded:

- Choose sensible item boundaries.
- Do not retain references to items after the chunk has been written.
- Use aggregate counters instead of accumulating all items.
- Limit field/nested collection sizes per data contract.
- Choose chunk size based on actual byte size, not just item count.
- Limit concurrency if each worker needs significant heap.
- Monitor heap, allocation rate, GC pauses, and processing time.

## 17. JSON Schema and Per-Item Validation

The JSON parser verifies JSON syntax and Jackson binding converts fields to Java types. That does not guarantee the data satisfies schema or business rules.

Example syntactically valid object:

```json
{"customerId":"","age":-5,"active":"yes"}
```

The object might partially parse or cause conversion errors depending on the model, while empty/negative data can violate business rules.

Separate the layers:

- JSON syntax: valid JSON structure.
- Object mapping: fields convertible to Java types.
- Schema validation: required fields, types, ranges, and structure matching JSON Schema.
- Business validation: business rules such as customer exists, valid age, or allowed status.

Per-item validation can run in `ItemProcessor`. If validation fails, throw a specific business exception and decide to skip or fail per policy.

For very large files, avoid parsing the entire document solely to pre-validate with a library that builds a large tree. Validate item by item while streaming, or use a streaming-capable validator if complex schema rules are required.

## 18. Handling JSON Errors and Skip Policy

JSON errors can occur at the document level or at a single-object level:

| Error type | Example | Generally appropriate handling |
|---|---|---|
| Whole-file JSON syntax | Missing `]`, unbalanced brackets. | Fail the Step; the file is not a valid array. |
| Unmappable object | String cannot be converted to number or date. | Can skip the item if the parser recovers boundaries and business rules allow. |
| Missing business field | Empty `customerId`. | Processor validates and rejects/skips per rules. |
| File I/O | File vanishes mid-read, permission denied. | Fail the Step or retry appropriate infrastructure errors. |
| Unsupported schema version | Fields/structure differ from deployed version. | Reject file or route to the matching versioned mapper. |

Do not configure skip for every parse exception. When a JSON array has broken structure, the parser may not know where the next object begins. Trying to swallow the exception can desynchronize the parser and skip the remainder of the file.

If you need to continue after a malformed object, verify the reader/parser can recover to the next object boundary. A custom reader capturing raw fragments or lines may be needed to record rejected data.

## 19. Size Limits and Parser Protection

JSON input may come from external systems and is not always trustworthy. Control:

- Maximum file size.
- Maximum size of a single JSON object or a single NDJSON line.
- Maximum nesting depth.
- Maximum length of String/number tokens if supported by the library.
- Number of elements in nested collections.
- Polymorphic deserialization features.

Do not broadly enable Jackson default typing for untrusted JSON data. Polymorphic type metadata can cause Jackson to instantiate unexpected types if configured too permissively. If polymorphism is needed, use a type allowlist or a controlled discriminator.

Specific parser limits depend on the Jackson version. You can configure `StreamReadConstraints` in supported versions; verify the API available in your actual dependency. Beyond parser limits, check file sizes at the ingestion layer and enforce resource limits at the process/container level.

## 20. JSON Arrays with Metadata and Multiple Record Types

Some sources use a structure like:

```json
{
  "version": "2",
  "generatedAt": "2026-11-15T10:00:00Z",
  "records": [
    {"type":"CUSTOMER","customerId":"C001"},
    {"type":"ORDER","orderId":"O001"}
  ]
}
```

This is not a simple root array. It can be handled along these lines:

- Use a custom Jackson streaming reader to locate the `records` field and read each object.
- Separate metadata/header checks from reading the array via a dedicated reader.
- Normalize the source into a root array or NDJSON before feeding into batch.
- Use the `type` discriminator to route each object to the matching mapper.

Do not deserialize the entire wrapper into an object containing `List<Object>` if `records` has millions of elements. That loads the whole collection onto the heap and defeats streaming.

If there are multiple record types, define a clear classification method. You can use a lightweight envelope DTO to read the discriminator and map the corresponding payload, or a custom parser to choose the class by `type`.

## 21. Large JSON Arrays and Partitioning

Batch jobs can be partitioned when data splits into independent sources or ranges. However, a single JSON array is not easy to split at arbitrary byte offsets because brackets, escaped strings, and nested structures can cut across tokens.

More suitable strategies:

- Split the input file into multiple valid JSON arrays before running partitions.
- Use NDJSON so each line is a record that can be partitioned by line range if byte offsets/encoding are preserved carefully.
- Partition by key/range from a database instead of splitting a JSON file arbitrarily.
- Use a custom parser/index to identify safe object boundaries if partitioning one large file is truly required.

If each partition processes its own file, each worker has its own reader state and output. Keep the mapping between partition ID and resource stable across restarts. Do not let multiple workers write to the same JSON output file if the writer is not designed for concurrent access.

## 22. Testing a Streaming Reader

Tests should verify the reader returns objects in exact order and ends with `null` when the array finishes.

Example:

```java
@Test
void readsItemsOneAtATimeFromJsonArray() throws Exception {
    JsonItemReader<Customer> reader = new JsonItemReaderBuilder<Customer>()
            .name("customerReader")
            .resource(new ClassPathResource("customers.json"))
            .jsonObjectReader(new JacksonJsonObjectReader<>(Customer.class))
            .saveState(true)
            .build();

    reader.open(new ExecutionContext());
    try {
        Customer first = reader.read();
        Customer second = reader.read();
        Customer end = reader.read();

        assertThat(first.customerId()).isEqualTo("C001");
        assertThat(second.customerId()).isEqualTo("C002");
        assertThat(end).isNull();
    } finally {
        reader.close();
    }
}
```

Tests should include fixtures for:

- Empty array.
- Single item and multiple items.
- Objects with nested objects/arrays.
- Missing fields, nulls, or wrong types.
- Malformed JSON syntax.
- Invalid file encoding.
- A file large enough to verify the reader does not build an in-application collection of the whole file.

A unit test with a few items only verifies mapping and order. To verify memory behavior, run benchmarks/load tests with representative data and observe heap/GC.

## 23. Testing Checkpoints and Restart

To confirm the reader restores the right position, run integration tests with `JobRepository` and a transaction manager:

1. Launch the job with immutable JSON input and fixed identifying parameters.
2. Let several chunks commit successfully.
3. Fail the step in a subsequent chunk.
4. Verify the reader's checkpoint was saved.
5. Restart the same `JobInstance` with the same resource and reader name.
6. Verify committed items are not reprocessed beyond expected semantics.
7. Verify uncommitted items are reread.
8. Verify the writer does not create duplicate data.

Do not swap the JSON file between the initial run and restart. If the file changes, the checkpoint may no longer correspond to the contents. Also do not change the reader name or turn off `saveState` between runs.

## 24. Monitoring Performance and Memory

For large JSON arrays, monitor at least:

- Counts of items read, processed, and written.
- Average and percentile parse times if appropriate metrics exist.
- Throughput in items/second and bytes/second.
- Heap used, allocation rate, and GC pauses.
- Chunk duration and commit duration.
- Mapping/validation error rate and skipped item count.
- Reader reopen duration on restart.
- Number of concurrent partitions/workers.

If heap grows steadily with the number of items read despite streaming, look for where the application retains references. Common culprits are unbounded caches, lists used for aggregation, metrics holding per-ID tags, or processors accumulating items.

When throughput is low, inspect parsing, processor, writer, and downstream systems. Jackson streaming helps little if each item makes a slow sequential API call or the writer commits individual records one by one.

## 25. Common Issues When Processing Large JSON

| Issue | Common cause | Mitigation |
|---|---|---|
| `OutOfMemoryError` | Deserializing the entire array into a `List`, or retaining items in a collection. | Use `JsonItemReader`/streaming parser and drop references after processing. |
| Reader fails to read JSON wrapper | Reader expects root array, but file has a root object containing an array. | Use a custom reader or normalize the input. |
| NDJSON fails to parse | Using a JSON array reader on a file with one document per line. | Use a line-based reader or custom `ItemStreamReader`. |
| Single item still consumes excessive heap | Huge nested array inside one object. | Change item boundary, limit payloads, or stream nested data. |
| Restart rereads too much | `saveState` disabled or checkpoint not restored. | Enable save state, keep reader name and input stable. |
| Restart reads wrong records | File modified after checkpoint was saved. | Use immutable inputs keyed by batch ID/checksum. |
| Malformed JSON skips the rest of the file | Parser cannot recover object boundaries. | Fail the job or use a format with clear record boundaries like NDJSON. |
| Large chunks cause GC pauses | Too many objects coexisting in one chunk. | Reduce chunk size and benchmark. |
| Invalid JSON output after failure | File writer/metadata out of sync or output read by consumer before completion. | Use save state, staging, validation, and a publish step. |
| Multiple workers corrupt output file | Concurrent writers sharing one resource. | Write separate files per partition then merge. |
| JSON field has wrong type | Jackson conversion mismatches source data. | Use suitable DTO/serializer, validate, and classify errors. |
| Parser instantiates unexpected types | Overly broad polymorphic typing or untrusted payloads. | Use allowlists/discriminators and parser limits. |

## 26. Workflow for Implementing Large JSON Arrays

When building a job to process a large JSON array, follow this sequence:

1. **Identify format:** root array, wrapper object, or NDJSON; define the item boundary.
2. **Determine scale:** record count, average/max object size, and nested collections.
3. **Create DTO:** model fields and types; do not put the entire array into a model collection.
4. **Choose reader:** use `JsonItemReader` for root arrays; custom reader for wrappers, NDJSON, or nested streaming.
5. **Enable checkpoints:** set a stable reader name and `saveState(true)` if restart is needed.
6. **Configure chunks:** pick an initial value based on heap and item size, then benchmark.
7. **Process item by item:** validate/map in the processor; do not accumulate all items.
8. **Write output:** use a streaming writer or database batch writer; protect output with idempotency.
9. **Control errors:** distinguish whole-file syntax errors, object errors, and business errors; skip only when safe recovery is possible.
10. **Control resources:** limit file/object/depth sizes, concurrency, and parser features.
11. **Test restart:** use `JobRepository` and immutable inputs to verify checkpoints.
12. **Measure in operations:** monitor heap, GC, throughput, chunk time, and error counts.

## 27. Key Takeaways

- Do not deserialize a very large JSON array into `List<T>` if the goal is bounded memory.
- `JsonItemReader<T>` reads a root array object by object; `JacksonJsonObjectReader<T>` binds each object to a Java type.
- `JsonItemReader` fits root arrays; wrapper objects and NDJSON require other reading approaches or custom readers.
- Item-level streaming does not split nested arrays inside an object.
- `JsonItemReaderBuilder` needs a stable reader name, resource, object reader, and `saveState(true)` when restart is needed.
- Chunk size affects coexisting object count, transaction duration, and throughput.
- Jackson `JsonParser` is a low-level streaming API; `readTree` or deserializing into collections can materialize the entire structure.
- Custom readers must implement the `open`, `read`, `update`, `close` lifecycle and save consistent checkpoints.
- Input must remain immutable between initial run and restart; keep `JobParameters`, reader name, and resource stable.
- `JsonFileItemWriter` with `JacksonJsonObjectMarshaller` can write items into a JSON array chunk by chunk.
- Streaming does not guarantee low memory if processors/caches/writers retain data or single objects are huge.
- JSON syntax, object mapping, schema validation, and business validation are separate layers.
- Do not skip all parser errors; whole-file structural errors generally require failing the step.
- For partitioning, split files on valid record boundaries or use separate resources; do not split bytes arbitrarily inside a JSON array.
- Monitor heap, allocation, GC, throughput, chunk duration, and errors to verify streaming is truly effective.

Streaming a JSON array in Spring Batch combines an object-by-object parser, chunk processing, and checkpoints. `JsonItemReader` makes it possible to process large root arrays without keeping the whole list in the heap. To keep the system stable, pick the right item boundary, bound object sizes, control chunks/concurrency, keep inputs immutable across restarts, and prevent downstream components from accumulating unbounded data.
