# JsonItemWriter

In Spring Batch, the built-in writer for writing items to a JSON file is named `JsonFileItemWriter<T>`. Many applications informally refer to this capability as JSON item writer or `JsonItemWriter`. `JsonFileItemWriter` receives items from a chunk, uses a `JsonObjectMarshaller<T>` to convert each object into JSON text, and writes the result to the target resource.

This writer fits when a Job needs to export data as a JSON document, such as a list of orders, customers, transactions, or synchronization results. Distinguish a writer that outputs a JSON document from a writer that outputs independent JSON lines (JSON Lines/NDJSON): the output format and how consumers read the file must be agreed upon from the start.

## 1. How Does JsonFileItemWriter Work?

In a chunk-oriented Step, the reader produces items, the processor may transform them, and the writer writes the output items. `JsonFileItemWriter` receives a chunk and marshals each item into JSON.

Processing flow:

```text
ItemReader<Order>
       |
       v
ItemProcessor<Order, OrderExport>
       |
       v
Chunk<OrderExport>
       |
       v
JsonFileItemWriter<OrderExport>
       |
       +--> JsonObjectMarshaller
       |       |
       |       +--> JSON text for each object
       |
       v
Output Resource
```

The writer focuses on converting objects into JSON representations and writing them to a file. Choosing which items are exported, filtering data, normalizing fields, or applying business rules should live in the reader/processor or an appropriate service.

In Spring Batch, the built-in API class name is `JsonFileItemWriter`; if a project has a custom class named `JsonItemWriter`, inspect that class's contract. The examples below use Spring Batch's standard `JsonFileItemWriter` API.

## 2. JSON Array vs. JSON Lines

Before configuring the writer, determine which format the consumer expects.

An **array-based JSON document** contains a JSON array with multiple objects:

```json
[
  {"orderId": 1001, "amount": 250000},
  {"orderId": 1002, "amount": 175000},
  {"orderId": 1003, "amount": 99000}
]
```

This is a standard JSON document: the entire file is a single JSON value, specifically an array. `JsonFileItemWriter` is designed to write object items into a JSON array.

**JSON Lines (NDJSON)** has one JSON value per line with no enclosing array brackets:

```text
{"orderId":1001,"amount":250000}
{"orderId":1002,"amount":175000}
{"orderId":1003,"amount":99000}
```

JSON Lines often fits streaming pipelines or systems that read one record per line. Do not convert a JSON array file into JSON Lines merely by swapping newlines; the writer and consumer must agree on the format. If the destination requires NDJSON, use an appropriate writer or implement a custom `ItemWriter` rather than assuming `JsonFileItemWriter` produces NDJSON.

## 3. JsonObjectMarshaller

`JsonFileItemWriter` does not decide every object-serialization detail itself. It uses `JsonObjectMarshaller<T>` to convert one item into a JSON string.

Basic marshaller contract:

```java
public interface JsonObjectMarshaller<T> {
    String marshal(T object) throws Exception;
}
```

The marshaller determines how objects map to JSON, such as:

- Property names in JSON.
- How dates/times and timezones are represented.
- How enums are represented.
- Handling `null`.
- Decimal number formatting.
- Nested objects and collections.
- Fields excluded from output.
- Custom serializers for special data types.

Separating marshalling from file writing lets the application change JSON libraries or serialization rules without rewriting Spring Batch's file and checkpoint management.

## 4. Using JacksonJsonObjectMarshaller

Spring Batch provides `JacksonJsonObjectMarshaller<T>` to use Jackson for converting objects to JSON. Example:

```java
@Bean
JacksonJsonObjectMarshaller<OrderExport> orderJsonMarshaller() {
    return new JacksonJsonObjectMarshaller<>();
}
```

Output model:

```java
public record OrderExport(
        Long orderId,
        String customerId,
        BigDecimal amount,
        String currency) {
}
```

When marshalling an `OrderExport`, Jackson produces a JSON object with corresponding properties, for example:

```json
{
  "orderId": 1001,
  "customerId": "C001",
  "amount": 250000.00,
  "currency": "VND"
}
```

The exact output depends on the model, Jackson version, and mapper configuration used. If the JSON contract requires exact field names, date/time formats, or null handling, configure and test the marshaller against that contract instead of relying on defaults.

## 5. Configuring JsonFileItemWriterBuilder

With Spring Batch 5, you can build the writer using `JsonFileItemWriterBuilder`:

```java
@Bean
@StepScope
JsonFileItemWriter<OrderExport> orderJsonWriter(
        @Value("#{jobParameters['output.file']}") String outputFile,
        JacksonJsonObjectMarshaller<OrderExport> orderJsonMarshaller) {

    return new JsonFileItemWriterBuilder<OrderExport>()
            .name("orderJsonWriter")
            .resource(new FileSystemResource(outputFile))
            .jsonObjectMarshaller(orderJsonMarshaller)
            .saveState(true)
            .build();
}
```

Important settings:

- `name`: stable writer name, used in metadata/checkpoints.
- `resource`: target file or resource.
- `jsonObjectMarshaller`: component that converts items to JSON.
- `saveState(true)`: enables saving state to support restart.

`@StepScope` allows resolving the resource from the current execution's `JobParameters`. Do not create a singleton writer with a per-run changing output path while sharing saved state across multiple Jobs.

## 6. Attaching the Writer to a Chunk Step

The writer can be used like any standard `ItemWriter`:

```java
@Bean
Step exportOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, OrderExport> orderProcessor,
        JsonFileItemWriter<OrderExport> orderJsonWriter) {

    return new StepBuilder("exportOrdersStep", jobRepository)
            .<Order, OrderExport>chunk(200, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderJsonWriter)
            .build();
}
```

With this configuration:

1. The reader fetches up to the items needed for the chunk.
2. The processor converts each `Order` into `OrderExport`.
3. The writer marshals the output items and writes them to the JSON file.
4. The Step commits the chunk according to the configured transaction manager.

Chunk size is the number of items processed in one transaction; it is not the number of JSON bytes or characters. If each object has large nested collections, a smaller chunk can help control memory.

## 7. Creating a Dedicated DTO for JSON Output

You do not have to serialize database entities directly. A dedicated export DTO helps control the JSON contract and prevents accidentally exposing internal fields.

Example internal entity:

```java
public class Order {
    private Long id;
    private String customerId;
    private BigDecimal amount;
    private String internalStatus;
    private String paymentToken;
    // Other persistence fields
}
```

Export DTO:

```java
public record OrderExport(
        Long orderId,
        String customerId,
        BigDecimal amount,
        String currency,
        LocalDate businessDate) {
}
```

Processor:

```java
@Bean
ItemProcessor<Order, OrderExport> orderExportProcessor() {
    return order -> new OrderExport(
            order.getId(),
            order.getCustomerId(),
            order.getAmount(),
            "VND",
            order.getBusinessDate());
}
```

DTOs strictly bound the exported fields. This is also the right place to rename properties, normalize values, and avoid serializing credentials, tokens, audit fields, or unnecessary ORM relationships.

## 8. Custom JsonObjectMarshaller

If you need a custom JSON format, you can implement `JsonObjectMarshaller<T>` and use the application's chosen JSON library.

Example with Jackson `ObjectMapper`:

```java
public class CustomOrderMarshaller
        implements JsonObjectMarshaller<OrderExport> {

    private final ObjectMapper objectMapper;

    public CustomOrderMarshaller(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public String marshal(OrderExport item) throws JsonProcessingException {
        return objectMapper.writeValueAsString(item);
    }
}
```

Registering mapper and marshaller:

```java
@Bean
ObjectMapper exportObjectMapper() {
    return JsonMapper.builder()
            .findAndAddModules()
            .build();
}

@Bean
JsonObjectMarshaller<OrderExport> orderJsonMarshaller(
        ObjectMapper exportObjectMapper) {
    return new CustomOrderMarshaller(exportObjectMapper);
}
```

`findAndAddModules()` allows Jackson to discover modules on the classpath, such as the Java time module if the corresponding dependency is present. Actual configuration must match the application's Jackson version and dependencies.

Custom marshallers should be stateless or thread-safe if the bean is used across multiple executions. Do not hold mutable buffers shared among concurrent Jobs.

## 9. Date/Time and Timezone Formatting

Dates and times are a common source of mismatch between producer and consumer. For example, `LocalDate` may serialize as an ISO string like `2026-11-15`; `Instant` may serialize with the UTC `Z` suffix.

The JSON contract should clearly specify:

- Business dates use `yyyy-MM-dd`.
- Absolute instants use ISO-8601 with an offset or UTC.
- Timezone is recorded explicitly if consumers must interpret local time.
- Do not serialize `LocalDateTime` and leave consumers guessing the timezone.
- Do not change formats between exports if consumers depend on the old schema.

Example JSON:

```json
{
  "businessDate": "2026-11-15",
  "createdAt": "2026-11-15T02:30:00Z",
  "businessTimeZone": "Asia/Ho_Chi_Minh"
}
```

If custom formatting is needed, you can use Jackson annotations like `@JsonFormat` or a custom serializer. Test with real JSON to confirm types and timezones.

## 10. Nulls, Enums, and Decimal Numbers

Serialization rules should be decided according to the data contract:

| Java type | Question to decide |
|---|---|
| `null` | Write property with `null` value, omit property, or use a fallback value? |
| Enum | Write enum name, business code, or ordinal? |
| `BigDecimal` | Preserve scale/precision and format as a JSON number? |
| `Boolean` | Use `true`/`false` or another business mapping? |
| Empty collection | Write `[]`, `null`, or omit field? |
| Optional | Convert to value, null, or omit field? |

Do not use enum ordinals as a long-term contract because enum order can change when code is updated. Use stable string codes such as `PENDING`, `APPROVED`, `REJECTED`, or an explicitly defined code.

For currency, keep `BigDecimal` instead of `double` to avoid floating-point errors. JSON numbers do not carry currency information, so a separate `currency` field is usually needed.

## 11. Nested Objects and Collections

Jackson can serialize an object graph into nested JSON objects/arrays. Example:

```java
public record OrderExport(
        Long orderId,
        CustomerExport customer,
        List<OrderLineExport> lines) {
}

public record CustomerExport(String customerId, String name) {
}

public record OrderLineExport(String sku, Integer quantity) {
}
```

Corresponding JSON:

```json
{
  "orderId": 1001,
  "customer": {
    "customerId": "C001",
    "name": "Lan"
  },
  "lines": [
    {"sku": "A-01", "quantity": 2},
    {"sku": "B-05", "quantity": 1}
  ]
}
```

Control the size of the object graph. If each item has tens of thousands of nested children, the chunk writer can hold many large objects in memory. You may need to split exports into multiple records or adjust item boundaries per the downstream contract.

Avoid serializing entities with uncontrolled bidirectional relationships. ORM proxies, lazy loading, and circular references can trigger unintended queries, recursive JSON, or serialization failures. Deliberate flat/nested export DTOs are generally easier to manage.

## 12. Resource and Output Directory

`resource` specifies where the writer writes the file. In real applications, pass the output path via `JobParameters` or validated environment configuration.

Example:

```java
@Bean
@StepScope
JsonFileItemWriter<OrderExport> orderJsonWriter(
        @Value("#{jobParameters['output.file']}") String outputFile,
        JsonObjectMarshaller<OrderExport> marshaller) {

    Path outputPath = Path.of(outputFile).toAbsolutePath().normalize();
    return new JsonFileItemWriterBuilder<OrderExport>()
            .name("orderJsonWriter")
            .resource(new FileSystemResource(outputPath))
            .jsonObjectMarshaller(marshaller)
            .saveState(true)
            .build();
}
```

Before running, verify:

- The parent directory exists and the process has write permission.
- The output path lies within the permitted area.
- Whether two concurrent Jobs could write to the same file.
- Whether the file must be kept after `FAILED`/`STOPPED` for restart.
- Whether consumers might read the final file while it is still being written.

Do not concatenate arbitrary path strings from untrusted input. Normalize and validate the path against a configured output root.

## 13. Overwrite and Append

The output file must have a clear policy when it already exists. Builder options related to file lifecycle may include `append(...)` and `shouldDeleteIfExists(...)` depending on the Spring Batch version.

Common decisions:

- Create a new file for a new `JobInstance`.
- Resume the old output when restarting the same `JobInstance` and the writer supports checkpoints.
- Reject writing if the destination file unexpectedly already exists.
- Write to dedicated staging first, then publish as the final file.

Appending does not mean you can arbitrarily concatenate two complete JSON documents. If the existing file is a JSON array already closed with `]`, appending another array produces content that is not a valid JSON document. Only use append when writer semantics and file state are clearly defined; do not concatenate JSON arrays using raw file operations.

`shouldDeleteIfExists` and `append` affect how the writer handles the resource on open. Do not enable deleting the file on restart if the goal is to recover output written in earlier chunks. Check the exact defaults and behavior of your version, and test both initial runs and restarts.

## 14. Restart and saveState

`JsonFileItemWriter` is a stateful writer via the `ItemStream` mechanism. With `saveState(true)`, the writer stores needed information in `ExecutionContext` to resume output after the last committed checkpoint.

Factors to keep stable:

- Writer name (`name`).
- Resource output path.
- Marshaller configuration and JSON schema.
- Append/delete configuration when opening the file.
- `JobInstance` and identifying `JobParameters`.
- How the writer manages delimiters and JSON array state.

For example, suppose a Job has committed two chunks and the process is killed during the third chunk. On restart, the writer needs to restore output to the last committed checkpoint and continue writing unfinished items. If the output file was deleted or replaced between runs, the checkpoint may no longer match file contents.

Do not change the writer name or randomize the output path on each restart. Use a path stable per `JobInstance` or store the chosen path in durable metadata.

## 15. Transactional Writing and Rollback

A file writer is not like a database writer. A JDBC transaction manager does not automatically create atomic transactions with the filesystem. `JsonFileItemWriter` provides chunked writing and transaction-aware buffering to support rollback within the writer's scope, but the filesystem is still not an XA resource automatically participating in JDBC transactions.

Scenarios to distinguish:

- Chunk rollback before contents are flushed/committed per writer mechanics: the writer can discard the uncommitted chunk's data.
- Committed chunk: corresponding output is retained.
- Process killed after file data is written but before metadata commit: file contents and checkpoint may be out of sync, depending on flush/transaction timing.
- File copied/published to an external system: database rollback does not retract that copy.

Test failure/restart with the actual filesystem and writer configuration. Do not assume a JDBC transaction can roll back every byte written to a file.

## 16. Staging Files and Publishing Output

A safe pattern is writing JSON to a staging file, validating the JSON after the writer finishes, and renaming it to the official file.

```text
order-export.json.part
        |
        +--> JsonFileItemWriter writes chunks
        |
        +--> Writer closes and completes JSON document
        |
        +--> Validate JSON + checksum
        |
        +--> Atomic move if filesystem supports it
        v
order-export.json
```

Publish example:

```java
Files.move(
        stagingPath,
        finalPath,
        StandardCopyOption.ATOMIC_MOVE);
```

Atomic move is only guaranteed within a supporting filesystem/provider, usually requiring staging and final to be on the same filesystem. It does not create a shared transaction with `JobRepository`. A process can die after the move succeeds but before the Step records completion; the Publish Step should be idempotent by checking the final file, checksum, or manifest.

If the Job fails before publishing, keep staging when restart needs to resume the writer. If the Job has already published, clean up leftover staging while retaining the final file per retention policy.

## 17. JSON Schema and Versioning

JSON is a data format, yet consumers still need a schema contract. Specify:

- Property names and data types.
- Required fields and optional fields.
- How nulls and empty collections are represented.
- Date/time, timezone, currency, and precision.
- Enum values/business codes.
- Nested objects and collection cardinality.
- Schema version and compatibility rules.

You can include a version in each item:

```json
{
  "schemaVersion": 2,
  "orderId": 1001,
  "amount": 250000.00,
  "currency": "VND"
}
```

Or use a separate manifest for the whole file. When the schema changes, determine whether old consumers can read new fields, whether removed fields break compatibility, and whether a restarting Job of an older `JobInstance` must continue using the old marshaller/schema.

Do not silently change property names or date formats across deployments. A Job restarting after an upgrade could write the first part with the old schema and the rest with the new schema if configuration is not versioned.

## 18. Validating JSON Output

After the Job writes the file, validate the output using a JSON parser or schema validator. Do not merely check that the file exists and has size greater than 0.

Useful checks:

- File is valid JSON and parses as an array if that is the contract.
- Object count matches exported item count, accounting for filters/skips.
- Every object has required fields with the right types.
- Dates/times, decimals, and enums match formats.
- No unintended internal/secret fields are present.
- Nested collections are neither lost nor mis-serialized.
- File is not truncated at the end after an error/kill.
- Checksum and manifest match the published output.

If consumers require JSON Schema, validate the file with a schema validator in a separate Step before publishing. Validation should run on the staging file once completely closed.

## 19. Handling Marshalling and File Write Errors

Exceptions can occur when:

- An object has a type unsupported by the serializer.
- A property getter throws an exception.
- A lazy association unexpectedly accesses the database.
- A circular reference exists in the object graph.
- File writing fails due to permission denied or disk full.
- Output path does not exist or filesystem disconnects.
- A JSON value violates the application's serialization rules.

Do not skip all writer errors. Marshalling errors caused by one item can be handled per data policy if the failing item can be identified and business rules allow. Disk full, permission denied, or filesystem unavailable errors typically affect the entire output and need controlled fail/retry after infrastructure recovery.

If you need to reject unserializable items, validate/convert in the processor before the writer and write a separate reject record. This separates single-item data errors from output-resource errors.

## 20. JSON Data Security

JSON output may contain personal data, financial data, or internal information. Control:

- DTOs export only necessary fields.
- Never serialize passwords, access tokens, secrets, or internal credentials.
- Output directory has appropriate permissions.
- Temporary and staging files have access permissions matching the final file.
- Encrypt files at rest or in transit if required by system policy.
- Do not log full JSON payloads of sensitive items.
- Apply retention and secure deletion per storage requirements.
- Control who can read files and manifests.

Do not rely solely on `@JsonIgnore` when there are multiple export types; separate DTOs per contract are usually easier to control than a shared entity.

## 21. Testing JsonFileItemWriter

Test the marshaller, the writer, and chunk Step integration.

### Unit testing the marshaller

```java
@Test
void marshalsOrderExportToExpectedJson() throws Exception {
    ObjectMapper mapper = JsonMapper.builder()
            .findAndAddModules()
            .build();
    JsonObjectMarshaller<OrderExport> marshaller =
            new CustomOrderMarshaller(mapper);

    String json = marshaller.marshal(new OrderExport(
            1001L, "C001", new BigDecimal("250000.00"),
            "VND", LocalDate.of(2026, 11, 15)));

    JsonNode node = mapper.readTree(json);
    assertThat(node.get("orderId").asLong()).isEqualTo(1001L);
    assertThat(node.get("customerId").asText()).isEqualTo("C001");
    assertThat(node.get("currency").asText()).isEqualTo("VND");
}
```

### Integration testing the writer

```java
@Test
void writesItemsAsJsonArray() throws Exception {
    Path output = tempDirectory.resolve("orders.json");

    JsonFileItemWriter<OrderExport> writer =
            new JsonFileItemWriterBuilder<OrderExport>()
                    .name("testOrderJsonWriter")
                    .resource(new FileSystemResource(output))
                    .jsonObjectMarshaller(new JacksonJsonObjectMarshaller<>())
                    .saveState(true)
                    .build();

    writer.open(new ExecutionContext());
    try {
        writer.write(new Chunk<>(List.of(
                new OrderExport(1001L, "C001",
                        new BigDecimal("250000.00"), "VND", null),
                new OrderExport(1002L, "C002",
                        new BigDecimal("175000.00"), "VND", null))));
    } finally {
        writer.close();
    }

    JsonNode root = objectMapper.readTree(output.toFile());
    assertThat(root.isArray()).isTrue();
    assertThat(root).hasSize(2);
    assertThat(root.get(0).get("orderId").asLong()).isEqualTo(1001L);
}
```

The illustrative test uses `tempDirectory` and `objectMapper` created in the test fixture. Depending on writer lifecycle and direct invocation outside a Step, initialize the writer per the `ItemStream` contract and ensure the resource is closed before reading the file.

### Testing restart and transactions

Scenarios to test:

- Writer writes multiple chunks and Job completes.
- Writer reopens the same resource after restart and resumes from checkpoint.
- Chunk rollback does not leave uncommitted items per configured writer semantics.
- Process killed during write/commit and output reconciled before restart.
- Writer does not unexpectedly delete existing output files.
- Two Jobs do not write to the same output path.
- Final JSON file parses and conforms to schema.
- Re-running the Publish Step does not produce duplicate output.

## 22. Common Pitfalls

### Confusing JsonItemWriter with JSON Lines

`JsonFileItemWriter` produces a JSON array. If consumers need NDJSON, use the right writer/format and test line by line.

### Omitting the marshaller

The writer needs a `JsonObjectMarshaller` to convert items into JSON. Choose Jackson or a custom marshaller matching the output contract.

### Serializing database entities directly

Entities can contain internal fields, lazy proxies, or circular references. Use an export DTO that restricts the schema.

### Not keeping writer name/resource stable on restart

Checkpoints may no longer match the output file. Keep the writer name and path stable for the same `JobInstance`.

### Deleting the file on restart

If the writer deletes old output, data from committed chunks can be lost while metadata retains checkpoints. Verify `append`/`shouldDeleteIfExists` against restart semantics.

### Concatenating two JSON arrays as plain text

The result may no longer be a valid JSON document. Define append semantics clearly or create a new output.

### Assuming JDBC rollback always rolls back files

The filesystem does not automatically participate in JDBC transactions. Use staging, state checks, and idempotent publishing.

### Not validating the file before publishing

The file may be truncated or violate schema. Close the writer, parse/validate JSON, and check checksums before publishing.

### Ignoring disk full or permission errors

The Job may produce incomplete output. Classify resource errors and handle retry/fail in a controlled manner.

### Exposing sensitive fields

Jackson may serialize unintended properties. Use DTOs and test JSON output to verify allowed fields.

## 23. Workflow for Implementing JsonFileItemWriter

When creating a JSON export Job, follow this sequence:

1. Determine whether consumers need a JSON array or JSON Lines.
2. Define the JSON schema: fields, types, nulls, dates/times, enums, and version.
3. Create an export DTO containing only data permitted for publication.
4. Choose `JacksonJsonObjectMarshaller` or a custom `JsonObjectMarshaller`.
5. Configure `JsonFileItemWriterBuilder` with a stable name and resource.
6. Choose `saveState` and file lifecycle matching restart requirements.
7. Attach the writer to a chunk Step and pick a chunk size suited to item size.
8. Validate the output path, permissions, and data access rights.
9. Write to staging if consumers must only read the file after completion.
10. Close the writer, parse/validate JSON, and publish the file.
11. Ensure restarts neither erase committed output nor produce malformed files.
12. Test marshaller, array output, rollback, restart, concurrency, and filesystem failures.

| Need | Suitable mechanism |
|---|---|
| Write objects as a JSON array | `JsonFileItemWriter<T>` |
| Convert object to JSON | `JsonObjectMarshaller<T>` |
| Use Jackson | `JacksonJsonObjectMarshaller<T>` |
| Control output schema | Export DTO and custom marshaller/ObjectMapper |
| Output depends on JobParameters | `@StepScope` and `jobParameters['output.file']` |
| Restart output | `saveState(true)`, stable writer name/path |
| Consumer needs NDJSON | Dedicated JSON Lines writer or custom `ItemWriter` |
| Publish only complete files | Staging, validation, and idempotent publish |

## Conclusion

In Spring Batch, the standard writer API for exporting items to a JSON file is `JsonFileItemWriter<T>`, typically configured with `JsonFileItemWriterBuilder` and a `JsonObjectMarshaller<T>`. The writer marshals each item into a JSON object and builds an array-structured JSON document; if consumers require JSON Lines, pick a dedicated writer/format. Use an export DTO, define a clear schema, configure Jackson or a custom marshaller, keep resource and writer name stable across restarts, and understand file lifecycles and filesystem transaction limits. For critical outputs, write to staging, close and validate the JSON, and publish idempotently so consumers never read partial files or encounter inconsistent data on restart.
