# Testing JSON Input and Output

In Spring Batch, JSON data is commonly used as an import source from APIs/exports or as an interchange format with other systems. A job may read a JSON array, convert each object into a Java item, apply business logic, and write results into a new JSON document. To ensure the pipeline works properly, test reading, mapping, processing, writing, and recovery when a chunk or job fails.

Testing JSON input and output is more than checking whether a file parses. Verify JSON structure, data types, null values, unknown/missing fields, item order and count, post-processor content, output formatting, encoding, behavior on bad data, and correctness across restarts.

Spring Batch provides **JsonItemReader<T>** with **JsonObjectReader<T>** to read objects one by one from a JSON resource, and **JsonFileItemWriter<T>** with **JsonObjectMarshaller<T>** to write items as JSON. Jackson-based implementations such as **JacksonJsonObjectReader** and **JacksonJsonObjectMarshaller** can be used. These components allow testing JSON mapping in isolation, testing the writer in isolation, and running integration tests through a real job.

## 1. Distinguishing Input and Output Testing

A JSON job can follow a flow like this:

~~~mermaid
flowchart LR
    A[JSON input file] --> B[JsonItemReader]
    B --> C[ItemProcessor]
    C --> D[JsonFileItemWriter]
    D --> E[JSON output file]
    E --> F[Parse and assert output]
~~~

Each part requires different assertions:

| Part | What to verify |
|---|---|
| Input resource | Right file, right encoding, resource can be opened |
| JSON parser/object reader | Valid JSON, objects map to the right types |
| JsonItemReader | Returns exact item count, exact order, and ends with null |
| Processor | Transformation rules, filtering, and validation |
| JsonFileItemWriter | Produces valid JSON structure, serializes exact fields and values |
| Job/step | Read/process/write counts, status, exceptions, and transactions |
| Restart | No lost or duplicated committed items |
| Consumer contract | Output parses cleanly and matches downstream schema/contract |

Separate small unit tests for mapping from integration tests for readers/writers and jobs. The closer a test sits to the boundary under verification, the easier it is to pinpoint whether a bug lies in the parser, processor, writer, or orchestration.

## 2. JSON Format Typically Handled by JsonItemReader

**JsonItemReader<T>** is designed to read a JSON array of objects. Example:

~~~json
[
  {
    "orderId": 1001,
    "customerId": "C001",
    "amount": 250.00
  },
  {
    "orderId": 1002,
    "customerId": "C002",
    "amount": 175.50
  }
]
~~~

The reader reads each object element and returns one Java item per object. The outermost array is the container of items. This structure fits chunk-oriented processing.

A single JSON object:

~~~json
{
  "orderId": 1001,
  "customerId": "C001"
}
~~~

is not equivalent to a JSON array in this reader configuration. If the source is a wrapper object such as {"orders": [...]}, handle the wrapper via a transformation step, a custom reader/object reader, or an appropriate input format. Do not assume JsonItemReader automatically finds arrays at arbitrary locations inside an object.

## 3. Java Model Used in Tests

Use a strongly typed DTO to test JSON mapping. Example:

~~~java
public class OrderInput {

    private Long orderId;
    private String customerId;
    private BigDecimal amount;

    public OrderInput() {
    }

    public Long getOrderId() {
        return orderId;
    }

    public void setOrderId(Long orderId) {
        this.orderId = orderId;
    }

    public String getCustomerId() {
        return customerId;
    }

    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public void setAmount(BigDecimal amount) {
        this.amount = amount;
    }
}
~~~

In tests, BigDecimal suits monetary assertions better than double because it avoids binary floating-point errors. A model with a no-arg constructor and conventional accessors lets Jackson binding work in standard configurations.

If the application uses Java records, constructor-based binding, or Jackson annotations, test the real model rather than switching to a POJO just to make testing easier. Fixtures must reflect the JSON contract the system actually receives.

## 4. Configuring JsonItemReader

Spring Batch provides a builder to construct JsonItemReader<T>. With Jackson, use JacksonJsonObjectReader<T> as the delegate reading each object:

~~~java
@Bean
@StepScope
public JsonItemReader<OrderInput> orderJsonReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new JsonItemReaderBuilder<OrderInput>()
            .name("orderJsonReader")
            .resource(new FileSystemResource(inputFile))
            .jsonObjectReader(new JacksonJsonObjectReader<>(OrderInput.class))
            .saveState(true)
            .build();
}
~~~

Key components:

- resource(...): JSON source to read.
- name(...): stable name to save reader state.
- jsonObjectReader(...): converts each JSON object into OrderInput.
- saveState(true): enables saving checkpoints for restart.

For reader unit tests, use a temporary resource or ByteArrayResource instead of job parameters. For production jobs, StepScope allows late-binding the input path per execution.

## 5. Testing JsonItemReader Standalone

Testing the reader independently confirms JSON parses into accurate items without launching the entire job.

Example with a classpath fixture file:

~~~java
class OrderJsonReaderTest {

    private JsonItemReader<OrderInput> reader;

    @BeforeEach
    void setUp() {
        reader = new JsonItemReaderBuilder<OrderInput>()
                .name("testOrderJsonReader")
                .resource(new ClassPathResource("json/orders-valid.json"))
                .jsonObjectReader(new JacksonJsonObjectReader<>(OrderInput.class))
                .saveState(true)
                .build();
    }

    @Test
    void readsEachObjectFromArray() throws Exception {
        reader.open(new ExecutionContext());
        try {
            OrderInput first = reader.read();
            OrderInput second = reader.read();

            assertEquals(1001L, first.getOrderId());
            assertEquals("C001", first.getCustomerId());
            assertEquals(new BigDecimal("250.00"), first.getAmount());

            assertEquals(1002L, second.getOrderId());
            assertEquals("C002", second.getCustomerId());
            assertEquals(new BigDecimal("175.50"), second.getAmount());

            assertNull(reader.read());
        } finally {
            reader.close();
        }
    }
}
~~~

The test opens the reader with an ExecutionContext, calls read() until null is returned, then closes the reader. Always use try/finally to release resources even when assertions fail.

This test checks item count, order, and field-level mapping. Asserting only first != null is insufficient to prove JSON mapped accurately.

## 6. Checking Item Order and Count

JSON arrays are ordered. Readers typically return items in array element order. If input order matters, tests must confirm that sequence is preserved across the reader and related processing steps.

You can read all items in a test:

~~~java
List<OrderInput> items = new ArrayList<>();
OrderInput item;
while ((item = reader.read()) != null) {
    items.add(item);
}

assertEquals(2, items.size());
assertEquals(
        List.of(1001L, 1002L),
        items.stream().map(OrderInput::getOrderId).toList());
~~~

For large fixtures, do not build an in-memory list of everything just to test the reader if the goal is verifying streaming. Inspect the first few items, verify the last item, or count in a loop to keep memory low.

If the processor filters items by returning null, written count may be smaller than read count. Tests should distinguish readCount, filterCount, and writeCount rather than assuming all three are always equal.

## 7. Organizing JSON Fixtures

Store fixtures as separate files by purpose:

~~~text
src/test/resources/json/
  orders-valid.json
  orders-empty.json
  orders-null-fields.json
  orders-missing-field.json
  orders-unknown-field.json
  orders-wrong-type.json
  orders-malformed.json
  orders-wrapper-object.json
  orders-large.json
~~~

Filenames should clearly indicate the scenario. When a test fails, readers can open the exact fixture without hunting through one giant JSON file full of unrelated cases.

Fixtures should be small with concrete, readable data. For example, orders-valid.json only needs two or three objects; keep large fixtures separate for streaming/performance tests. Never use production data containing personal information or secrets as test fixtures.

## 8. Testing an Empty JSON Array

An empty JSON array is:

~~~json
[]
~~~

The reader should finish without returning items. Tests must confirm:

- read() returns null on the very first call.
- No exception is thrown if an empty array is valid input under the contract.
- The step finishes with the expected status.
- Write count is 0 when no items are written.

If business rules require at least one record, an empty array should be rejected via validation/preflight or a business rule. Do not confuse a syntactically valid empty array with business-valid input.

## 9. Testing JSON Nulls and Missing Fields

JSON can represent null values:

~~~json
[
  {
    "orderId": 1001,
    "customerId": null,
    "amount": 250.00
  }
]
~~~

Fields can also be omitted completely:

~~~json
[
  {
    "orderId": 1001,
    "amount": 250.00
  }
]
~~~

Both cases can yield the same Java result if the property is a nullable reference, yet contract meanings may differ. If you must distinguish an unsent field from a field sent as null, a plain DTO with a nullable field may not suffice; use custom deserialization, presence flags, or an appropriate JsonNode/wrapper.

Tests should establish clearly:

- Is a null customerId accepted?
- Does a missing field take a default value?
- Is a required field rejected during parsing or in processor validation?
- Is null written to output as JSON null, omitted, or replaced with a default?

Do not let Jackson's default behavior accidentally decide business rules without tests confirming it.

## 10. Testing Wrong Data Types

For example, JSON where amount is a string:

~~~json
[
  {
    "orderId": 1001,
    "customerId": "C001",
    "amount": "two hundred"
  }
]
~~~

If the model requires BigDecimal, Jackson may throw a mapping error depending on coercion settings. Tests must confirm the job handles the error according to the chosen policy:

- Reject the entire file if the JSON violates schema.
- Stop the step upon encountering an undeserializable object.
- Or use a flexible reading model to record bad records and continue if business rules permit.

Do not assume JSON parse errors will be handled identically to exceptions inside ItemProcessor. When JsonItemReader cannot construct an item, the failure occurs at the reader boundary and requires corresponding configuration and tests.

## 11. Testing Malformed JSON

Malformed examples:

~~~json
[
  {"orderId": 1001, "amount": 250.00},
~~~

or:

~~~json
[
  {"orderId": 1001 "amount": 250.00}
]
~~~

Common defects include missing brackets, missing commas, unclosed quotes, invalid tokens, or mid-stream truncation.

Malformed input tests should verify:

- Reader/step fails as expected.
- Exception chain preserves a useful parse cause.
- No complete output is published.
- Staging artifacts are kept or cleaned up per policy.
- Job metadata reflects the failed status.
- Earlier valid items are not published as a complete file if the contract requires all-or-nothing output.

A JSON array can contain many valid objects before the malformed position. The reader may already have returned several items before the error is hit. If the writer committed earlier chunks, you need a staging/publish strategy so downstream never consumes partial output.

## 12. Unknown Fields and Schema Evolution

An upstream system may add a new field to JSON:

~~~json
[
  {
    "orderId": 1001,
    "customerId": "C001",
    "amount": 250.00,
    "salesChannel": "WEB"
  }
]
~~~

The old OrderInput model does not yet have salesChannel. Depending on Jackson configuration, unknown properties may be ignored or cause deserialization to fail.

Tests must clearly validate the compatibility strategy:

- **Forward-compatible:** accept and ignore unknown fields if they do not affect business logic.
- **Strict schema:** reject the file when unknown fields appear.
- **Versioned schema:** read the version and select the corresponding DTO/mapper.
- **Flexible mapping:** retain dynamic fields in a map or JsonNode for intentional handling.

If choosing to ignore unknown fields, test to verify critical data is not silently lost. If choosing strict mode, errors should identify which property is unsupported.

## 13. Testing Nested Objects and Arrays

A JSON item can contain nested objects or arrays:

~~~json
[
  {
    "orderId": 1001,
    "customer": {
      "id": "C001",
      "name": "An"
    },
    "lines": [
      {"sku": "P01", "quantity": 2},
      {"sku": "P02", "quantity": 1}
    ]
  }
]
~~~

Tests should confirm:

- customer.id maps accurately.
- lines has the exact count and order of elements.
- Quantity type is integer if the model requires it.
- Null or missing customer is handled properly.
- Processor does not accidentally drop nested data.
- Writer serializes nested objects back to the target schema.

For large object graphs, account for item size. Chunk size limits items per transaction, yet a single item containing tens of thousands of nested objects can still consume substantial memory.

## 14. Testing Dates/Times, Decimals, and Enums

Data types prone to cross-environment differences:

- BigDecimal: check numeric value and required scale; JSON numbers have no quotes if the contract specifies numeric.
- Dates: verify format, e.g., yyyy-MM-dd.
- Timestamps: verify timezone/offset, e.g., ISO-8601 with Z or explicit offset.
- Enums: verify whether JSON uses enum names, business codes, or other values.
- UUIDs: verify standard format and invalid-value handling.

Timestamp example:

~~~json
{
  "createdAt": "2026-11-15T10:30:00Z"
}
~~~

Run tests under different JVM default timezones if code risks using the default timezone. Never let the same input yield different outputs merely because servers run in different timezones.

If Jackson uses custom serializers/deserializers, test both directions: input converts accurately to Java, and Java serializes to the exact contract format.

## 15. Configuring JsonFileItemWriter

JsonFileItemWriter<T> writes items as a JSON array. It uses JsonObjectMarshaller<T> to convert each item into a JSON representation.

With Jackson, use JacksonJsonObjectMarshaller<T>:

~~~java
@Bean
@StepScope
public JsonFileItemWriter<OrderOutput> orderJsonWriter(
        @Value("#{jobParameters['outputFile']}") String outputFile) {

    return new JsonFileItemWriterBuilder<OrderOutput>()
            .name("orderJsonWriter")
            .resource(new FileSystemResource(outputFile))
            .jsonObjectMarshaller(new JacksonJsonObjectMarshaller<>())
            .saveState(true)
            .build();
}
~~~

The writer manages creating the JSON array and writing objects item by item. JacksonJsonObjectMarshaller converts one item into a JSON object; the writer assembles objects into the output document.

Exact builder method names and overloads may vary across Spring Batch versions. Use the API from your project's dependency version; do not mix JSON reader/writer classes from different major versions.

## 16. Testing JsonFileItemWriter Standalone

You can test the writer with a temporary file and read the result back using Jackson ObjectMapper or another JSON parser.

Test skeleton example:

~~~java
class OrderJsonWriterTest {

    @TempDir
    Path tempDir;

    @Test
    void writesItemsAsJsonArray() throws Exception {
        Path output = tempDir.resolve("orders.json");

        JsonFileItemWriter<OrderOutput> writer =
                new JsonFileItemWriterBuilder<OrderOutput>()
                        .name("testOrderJsonWriter")
                        .resource(new FileSystemResource(output))
                        .jsonObjectMarshaller(new JacksonJsonObjectMarshaller<>())
                        .saveState(true)
                        .build();

        writer.open(new ExecutionContext());
        try {
            writer.write(new Chunk<>(List.of(
                    new OrderOutput(1001L, "C001", new BigDecimal("250.00")),
                    new OrderOutput(1002L, "C002", new BigDecimal("175.50")))));
            writer.update(new ExecutionContext());
        } finally {
            writer.close();
        }

        JsonNode root = new ObjectMapper().readTree(output.toFile());
        assertTrue(root.isArray());
        assertEquals(2, root.size());
        assertEquals(1001L, root.get(0).get("orderId").asLong());
        assertEquals("C002", root.get(1).get("customerId").asText());
    }
}
~~~

This skeleton illustrates the writer lifecycle; the Chunk constructor and writer calls may need adjustment for your Spring Batch version. In real tests, use try/finally or try-with-resources appropriately to always close the writer. A more reliable way to test transaction/restart behavior is running the writer inside a step integration test.

The key point is parsing the output into a JSON tree and asserting structure and values. Do not merely check that the file exists or that the output string contains a substring.

## 17. Asserting JSON Structurally Instead of String Comparison

JSON objects do not require meaningful key ordering. These two documents can be data-equivalent:

~~~json
{"orderId":1001,"customerId":"C001"}
~~~

~~~json
{"customerId":"C001","orderId":1001}
~~~

Literal string comparison can fail tests merely because the serializer changed property order or whitespace. Instead, parse JSON into JsonNode and assert field by field:

~~~java
JsonNode actual = objectMapper.readTree(outputFile);

assertEquals(1001L, actual.get(0).get("orderId").asLong());
assertEquals("C001", actual.get(0).get("customerId").asText());
assertEquals(new BigDecimal("250.00"),
        actual.get(0).get("amount").decimalValue());
~~~

If array element order is a business requirement, still assert index or sequence. Only key order inside objects is usually not part of the contract.

If whitespace formatting, indentation, or key order is part of an external contract (such as snapshot files compared verbatim), maintain a separate golden-file test. Do not use string snapshots as the sole way to verify JSON correctness.

## 18. Checking Extra Fields, Missing Fields, and Nulls in Output

Output checks must verify both present data and data that must not appear.

Example:

~~~java
JsonNode order = actual.get(0);

assertTrue(order.has("orderId"));
assertFalse(order.has("internalPassword"));
assertTrue(order.has("note"));
assertTrue(order.get("note").isNull());
~~~

has(...) can return true for a field with JSON null; hasNonNull(...) has different semantics. Tests must pick assertions matching the contract.

If the serializer is configured to omit nulls, output may lack the field rather than containing "note": null. Both representations are syntactically valid yet carry different meanings for consumers. Test the specified behavior.

Never let internal fields such as passwords, tokens, database keys, or debug data leak into JSON output. Use a dedicated output DTO and assert sensitive fields do not exist.

## 19. Testing Escaping and Unicode Characters

JSON serializers must escape quotes, backslashes, and control characters per JSON standards. Example customer name containing quotes:

~~~json
[
  {
    "customerName": "An \"The Builder\" Nguyen",
    "note": "Line 1\nLine 2",
    "city": "Thành phố Hồ Chí Minh"
  }
]
~~~

Tests should re-parse output and compare Java values after parsing. That proves both serializer and parser preserve data, rather than merely producing a string that looks valid.

For Vietnamese or non-ASCII characters, verify actual byte encoding. If output requires UTF-8, read the file with StandardCharsets.UTF_8 or a parser using the exact encoding. Never rely on the test machine's default encoding.

## 20. Checking Output Format and Schema Contracts

JSON has no mandatory schema in its base syntax. Systems can use JSON Schema or a custom contract to define:

- Required fields.
- Data types.
- Valid enum values.
- Numeric and string bounds.
- Nested object/array structures.
- Whether additional fields are allowed.
- Schema version.

After the writer closes the file, validate JSON output against a JSON Schema validator. Tests should verify output both parses and satisfies the schema.

Successful parsing proves only JSON syntax validity. For instance, {"amount":"abc"} is valid JSON yet violates the schema above if amount must be a number.

## 21. Testing Empty JSON Output

When zero items are written, the writer may produce an empty JSON array per implementation behavior:

~~~json
[]
~~~

Test the zero-item case and confirm whether consumers expect an empty file, an empty array, or no file created. Those three behaviors differ.

If the job must always produce an artifact, tests must verify the file exists and parses as an empty array. If the job must not publish output when there is no data, the publish step must check counts and apply the appropriate policy.

Do not assume the writer creates the exact expected artifact without an integration test against your Spring Batch version.

## 22. Testing the Processor Between JSON Input and Output

Reader and writer may work properly while the processor corrupts data. For instance, the processor computes totals, normalizes customer codes, or filters cancelled orders.

Processor unit tests should focus on business rules:

~~~java
class OrderProcessorTest {

    private final OrderProcessor processor = new OrderProcessor();

    @Test
    void calculatesNetAmount() {
        OrderInput input = new OrderInput(1001L, "C001",
                new BigDecimal("250.00"));

        OrderOutput output = processor.process(input);

        assertEquals(1001L, output.getOrderId());
        assertEquals(new BigDecimal("225.00"), output.getNetAmount());
    }
}
~~~

In end-to-end tests, feed JSON input fixtures, run the job, and parse JSON output to verify both mapping and business transformations.

If the processor returns null to filter items, tests must verify filterCount and exact output element count. If the processor throws exceptions, tests verify skip/retry policies per error category.

## 23. Integration Testing by Running a Real Job

Testing reader and writer separately does not verify job wiring, transaction manager, step configuration, or job parameters. Use SpringBatchTest with JobLauncherTestUtils to launch the job with fixture files and a temporary output.

Example test structure:

~~~java
@SpringBatchTest
@SpringJUnitConfig(OrderJsonJobTestConfiguration.class)
class OrderJsonJobIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @TempDir
    Path tempDir;

    @Test
    void transformsJsonInputIntoExpectedOutput() throws Exception {
        Path output = tempDir.resolve("orders-output.json");

        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", "src/test/resources/json/orders-valid.json", true)
                .addString("outputFile", output.toString(), false)
                .addString("runKey", "test-001", true)
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        assertTrue(Files.exists(output));

        JsonNode root = new ObjectMapper().readTree(output.toFile());
        assertTrue(root.isArray());
        assertEquals(2, root.size());
    }
}
~~~

This is an illustrative structure. Test configuration must properly wire the job, datasource/repository, and scoped beans. With StepScope, job parameters resolve during execution; do not instantiate target readers/writers directly before the job context is active.

Use a dedicated output path inside TempDir so tests never overwrite other files and clean up easily.

## 24. Checking BatchStatus and StepExecution Metrics

After launching the job, tests can verify:

- JobExecution.getStatus() is COMPLETED or the expected status.
- StepExecution.getReadCount() reflects items returned by the reader.
- getWriteCount() reflects items written successfully by the writer.
- getFilterCount() reflects items filtered by returning null from the processor.
- getSkipCount() reflects items skipped per policy.
- getRollbackCount() reflects rollbacks that occurred.

Example:

~~~java
StepExecution step = execution.getStepExecutions()
        .stream()
        .filter(s -> s.getStepName().equals("transformOrdersStep"))
        .findFirst()
        .orElseThrow();

assertEquals(2, step.getReadCount());
assertEquals(2, step.getWriteCount());
assertEquals(0, step.getSkipCount());
~~~

These counts have distinct semantics. readCount does not necessarily equal writeCount if the processor filters items or the step skips records. With retries, read/write attempts and commit semantics can make in-flight logs/metrics differ from final item counts; assert against contracts and output data rather than relying on a single count.

## 25. Testing Non-Existent or Unreadable Input Files

Jobs must handle missing resources, wrong paths, or denied read permissions cleanly.

Tests should verify:

- Job/step fails with a diagnosable resource error.
- No output is published.
- If a staging file was created before opening the reader, cleanup/retention follows policy.
- Error messages do not expose paths or sensitive data unnecessarily.

You can check file existence in a JobParametersValidator or preflight step, yet the reader must still handle race conditions: a file can vanish after preflight and before opening.

## 26. Testing Chunk Rollback and Partial Output

Suppose a job reads 1,000 objects and writes in chunks of 100. A middle chunk fails. Tests must verify how committed and uncommitted chunk outputs are handled.

Points to verify:

- Items in the rolled-back chunk do not appear as committed data when the writer supports transactional buffering.
- When retry succeeds, each item appears once in the final output.
- If the job fails permanently, staging files are not published as complete results.
- If the writer/destination does not share the same transaction, idempotency or staging handles the crash window.

The filesystem is not a general database transaction. Do not assert only rollbackCount > 0; parse the output and verify business keys and record counts.

## 27. Testing Restart and Checkpoints

JsonItemReader and JsonFileItemWriter support saving state in ExecutionContext when properly configured. Restarts must use the same JobInstance and a stable input source.

A restart integration test can:

1. Launch the job with fixed identifying parameters.
2. Allow some chunks to commit, then fail the step.
3. Verify staging output contains data from committed chunks.
4. Restart with the same identifying parameters.
5. Verify the reader resumes from checkpoint and the writer resumes the exact resource/state.
6. Parse final output and verify each business key appears exactly once.

Do not alter input JSON between initial run and restart. If the file changes, positional checkpoints may point to different content. You can store an input checksum/version and reject restarts if the source no longer matches the original.

Do not add new identifying parameters such as a random timestamp on restart, as doing so creates a new JobInstance and makes the reader read from the beginning again.

## 28. Testing Output Paths and Non-Overwriting

Tests should use separate output paths per JobInstance or output version. When a new job must create a new artifact, verify older files remain untouched.

Useful assertions:

- Output file from the prior run still exists.
- Checksum of the old file is unchanged after the new job finishes.
- New file is created at a distinct path/version.
- Restarting the same instance resumes the previous staging resource.
- A pre-existing destination file with different content fails publishing instead of silently overwriting.
- Manifest transitions to PUBLISHED only when output is complete and verified.

For standalone writer tests, use TempDir and temporary files to avoid touching real outputs. For multi-execution integration tests, use stable output keys with collision guards.

## 29. Testing Schemas with JSON Schema

If systems interchange via JSON Schema, validate output after writing. Abbreviated schema example:

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "array",
  "items": {
    "type": "object",
    "required": ["orderId", "customerId", "amount"],
    "properties": {
      "orderId": {"type": "integer"},
      "customerId": {"type": "string"},
      "amount": {"type": "number", "minimum": 0}
    },
    "additionalProperties": false
  }
}
~~~

The schema verifies document structure and constraints. In tests, use a JSON Schema validator matching the draft in use and store schemas as versioned test resources.

Do not check only that JSON parses. A document with amount as a string is valid JSON yet violates the schema above.

If the schema permits new fields, configure additionalProperties accordingly. Otherwise, tests must confirm the writer outputs no out-of-contract fields.

## 30. Comparing Output Against an Expected Fixture

For small outputs with stable contracts, keep an expected JSON fixture. Parse both actual and expected into JsonNode and compare structures.

Example:

~~~java
JsonNode expected = objectMapper.readTree(
        new ClassPathResource("json/orders-expected.json").getInputStream());
JsonNode actual = objectMapper.readTree(output.toFile());

assertEquals(expected, actual);
~~~

Tree comparison ignores whitespace and object key order while preserving array element order. This is a strong option for small structured outputs.

For large outputs, storing a huge expected file is unnecessary. Verify counts, business keys, representative records, schema, and checksums per rules. If checksums are used, ensure deterministic serialization without unstable timestamps or random values.

## 31. Testing JSON Streaming and Large Files

Batch jobs often handle large inputs. Tests should confirm the reader operates in streaming mode and does not force the application to load the entire file onto the heap.

Verification approaches:

- Use large fixtures generated in tests or dedicated performance tests.
- Read and count items sequentially without keeping the entire list in memory.
- Observe heap/allocation in appropriate benchmarks.
- Test chunk size and processing time with representative sizes.
- Confirm the output writer does not build the entire array in one object graph before writing.

A unit test with three objects does not prove multi-gigabyte file capability. Separate performance/load tests from unit tests so regular suites stay fast and deterministic.

## 32. Testing Encoding and File Bytes

JSON is typically exchanged in UTF-8. Tests should verify output bytes are written in the chosen encoding and the parser reads Unicode characters accurately.

Example:

~~~java
byte[] bytes = Files.readAllBytes(output);
String json = new String(bytes, StandardCharsets.UTF_8);

JsonNode root = objectMapper.readTree(json);
assertEquals("Thành phố Hồ Chí Minh",
        root.get(0).get("city").asText());
~~~

If JSON is read from a resource with a BOM or another encoding, define expected behavior and test separately. Never rely on the OS default charset.

## 33. Testing Unknown Fields and Strict Deserialization

Jackson can be configured strictly or permissively on unknown properties. These two modes serve different contracts.

With strict schemas, test fixtures containing unknown fields must fail the reader. With permissive schemas, tests must confirm unknown fields are intentionally ignored while known fields still map accurately.

Never mutate the test application's global ObjectMapper just to make one test pass. Configure JSON readers/marshallers with the same ObjectMapper or Jackson settings as production so tests reflect real behavior.

## 34. Testing Per-Item Errors and Skip Policies

If a JSON array parses cleanly yet one object violates business rules, the processor may throw an exception. This differs from JSON syntax errors or deserialization errors at the reader.

Examples:

- Malformed JSON: parser cannot read structure.
- Valid JSON, but orderId is a string when the model requires a number: binding error.
- JSON binds cleanly, yet amount < 0: business validation error in processor.

Tests should distinguish these layers. When business validation exceptions are configured as skippable, verify the item is skipped, the skip listener logs the exact business key, and valid items still write. When reader errors cannot be skipped as desired, consider reading objects flexibly and validating in the processor, or using a separate error-recording mechanism.

Do not skip malformed JSON errors broadly, as the parser may fail to safely recover the next object boundary.

## 35. Common Pitfalls

| Scenario | Cause | Fix |
|---|---|---|
| Reader fails on single JSON object | Reader expects a top-level array | Wrap items in an array or use a wrapper-capable reader |
| Java fields always null | JSON keys mismatch properties or binding config is wrong | Check field names, accessors, and Jackson annotations |
| Wrong decimal values | Using double or unwanted coercion | Use BigDecimal and test exact values |
| Unknown field fails job | Strict Jackson unknown-property setting | Specify strict/permissive per contract |
| Malformed JSON fails step | Invalid JSON structure | Validate inputs, log parse errors, and avoid publishing partial output |
| Null and missing fields confused | DTO lacks presence info | Use wrappers/presence flags/JsonNode if distinction is needed |
| Output is not an array | Writer/marshaller or consumer expectation mismatch | Parse output and verify root type |
| Tests fail on whitespace/key order | Verbatim JSON string comparison | Parse to JsonNode and assert structure |
| Output exposes sensitive fields | Serializing internal entities/models directly | Use export DTOs and assert forbidden fields are absent |
| Garbled Unicode | Inconsistent default encoding | Use explicit UTF-8 and test byte output |
| Restart creates duplicates | Desynced reader/writer checkpoints or changed path | Restart same JobInstance with stable resources |
| Old output overwritten | Multiple instances share one output path | Use separate staging paths/versions and controlled publishing |
| Chunk rollback leaves partial output | Files do not join transactions as expected | Use writer transactional support, staging, and idempotency |
| Tests pass but prod differs | Tests use a different ObjectMapper/config | Use production-matching binding configuration |

## 36. Workflow for Building a JSON Test Suite

1. **Lock down JSON contract:** top-level array vs. wrapper, required fields, types, nulls, and schema version.
2. **Create small fixtures:** valid, empty, null/missing, unknown, wrong type, and malformed.
3. **Test object reader:** verify per-field mapping, nested objects, dates/decimals/enums.
4. **Test JsonItemReader:** verify item counts, ordering, end-of-input, and resource errors.
5. **Test processor:** verify business transformations, filtering, and exceptions.
6. **Test marshaller/writer:** write items, re-parse output, and assert structure/values.
7. **Validate schema:** validate output with JSON Schema if the contract requires it.
8. **Test job end-to-end:** launch with fixture inputs and temporary output paths; inspect status/counts/artifacts.
9. **Test failure/restart:** inject mid-chunk failures, restart the same JobInstance, and confirm zero lost or duplicated items.
10. **Test output isolation:** run new instances or versions and confirm prior outputs remain untouched.
11. **Test scale/encoding:** use representative files, UTF-8, and Unicode data.
12. **Keep tests deterministic:** avoid depending on timestamps, default timezones, JSON key ordering, or fixed filesystem paths.

## 37. Key Principles to Remember

- JsonItemReader<T> reads objects one by one from a JSON array; verify the source's top-level shape explicitly.
- JsonObjectReader<T> maps a single JSON object into a Java type; the Jackson implementation is a common choice.
- JsonFileItemWriter<T> writes items to JSON output and uses JsonObjectMarshaller<T> to serialize.
- Test the reader standalone to verify parsing, counts, order, and data types.
- Test the writer by parsing output into a JSON tree; never rely solely on file existence or whitespace-sensitive string matching.
- Distinguish JSON syntax errors, deserialization errors, and business validation errors.
- Explicitly define handling for missing fields, nulls, unknown fields, enums, decimals, dates/times, and nested data.
- Use export DTOs to control published fields and prevent exposing internal data.
- Verify UTF-8, escaping, and Unicode characters by reading files back with explicit encoding.
- Parseable JSON does not guarantee JSON Schema or downstream contract compliance.
- Integration test through a real job to verify wiring, metrics, transactions, and job parameters.
- Test chunk rollback/restart with the same JobInstance and stable input/output resources.
- Use staging/publish to avoid exposing incomplete JSON files.
- Separate performance tests for large files from small, fast, deterministic unit tests.

Testing JSON input and output must cover syntax, mapping, business transformations, and file lifecycles. By testing readers/writers standalone, validating output via parsers/schemas, and running integration tests with rollbacks and restarts, Spring Batch applications catch data defects early and ensure final JSON artifacts match contracts without losing or duplicating records.
