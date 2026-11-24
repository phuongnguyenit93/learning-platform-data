# JsonItemReader

In Spring Batch, `JsonItemReader<T>` is an `ItemReader` used to read JSON data item by item. The reader processes a JSON array containing objects, converts each object into a Java object via `JsonObjectReader<T>`, and returns each item to the chunk-oriented Step.

For example, an `orders.json` file may contain hundreds of thousands of orders in a JSON array. `JsonItemReader<Order>` reads each `Order` object for the processor to validate and the writer to persist to the database. Reading item by item enables processing large files in chunks, instead of having the application load and process the entire list in one go.

`JsonItemReader` decouples item-reading control from the specific JSON library. You can use `JacksonJsonObjectReader` or `GsonJsonObjectReader`, or implement a custom `JsonObjectReader` if the application needs a different library or parsing rules.

## 1. JSON Structure That JsonItemReader Reads

`JsonItemReader` is designed for documents that have a top-level JSON array, where each element is a JSON object representing an item.

Example `orders.json` file:

```json
[
  {
    "orderId": 1001,
    "customerName": "Lan",
    "amount": 125.50
  },
  {
    "orderId": 1002,
    "customerName": "Minh",
    "amount": 89.00
  },
  {
    "orderId": 1003,
    "customerName": "An",
    "amount": 240.75
  }
]
```

Each object inside the array is an item. Successive calls to `read()` return `Order` for IDs 1001, 1002, and 1003 in turn. When the array is exhausted, the reader returns `null` to signal end of data.

Flow diagram:

```text
orders.json
    |
    v
JsonItemReader<Order>
    |
    v
JsonObjectReader<Order>
    |
    +--> First JSON object   --> Order 1001
    |
    +--> Second JSON object  --> Order 1002
    |
    +--> Third JSON object   --> Order 1003
    |
    +--> End of array        --> null
```

A single top-level JSON object, such as `{ "orders": [...] }`, or JSON Lines/NDJSON (where each line is an independent object) does not have the same array structure that this reader expects. For those formats, you need to normalize the source into an array, write a custom reader, or use a reader suited to line-based formats.

## 2. What Does JsonObjectReader Do?

`JsonItemReader` manages reading items in the JSON array. Converting a JSON object into a Java object is delegated to `JsonObjectReader<T>`.

Commonly used implementations:

| Implementation | Library | When to use? |
|---|---|---|
| `JacksonJsonObjectReader<T>` | Jackson | The application already uses Jackson or needs to customize `ObjectMapper` |
| `GsonJsonObjectReader<T>` | Gson | The application uses Gson for JSON mapping |
| Custom `JsonObjectReader<T>` | Custom library or parser | Special parsing rules or integration with another library is needed |

`JsonObjectReader` is responsible for opening the JSON source, reading the next object, and closing resources when the reader finishes. `JsonItemReader` invokes those operations within the `ItemStreamReader` lifecycle.

Separating the two components allows the same batch configuration to swap JSON libraries without rewriting the chunk Step. However, type conversion and handling of unknown fields, dates/times, and nulls still depend on the chosen implementation.

## 3. Basic JsonItemReader Configuration with Jackson

Example using `JacksonJsonObjectReader`:

```java
@Bean
public JsonItemReader<Order> orderJsonReader() {
    return new JsonItemReaderBuilder<Order>()
            .name("orderJsonReader")
            .resource(new ClassPathResource("data/orders.json"))
            .jsonObjectReader(new JacksonJsonObjectReader<>(Order.class))
            .strict(true)
            .saveState(true)
            .build();
}
```

Key settings:

- `name("orderJsonReader")`: stable reader name, used when saving state in `ExecutionContext`.
- `resource(...)`: the JSON source to read, here a file on the classpath.
- `jsonObjectReader(...)`: the component that converts each JSON object into an `Order`.
- `strict(true)`: requires the resource to exist when opening the reader according to the reader's strict behavior.
- `saveState(true)`: enables saving checkpoints to support restart.

The builder and JSON reader classes belong to the Spring Batch infrastructure. You need the appropriate Spring Batch dependency and the JSON library used by the implementation, such as Jackson or Gson. The API may differ across Spring Batch versions; use the builder and constructors corresponding to your project's dependency.

## 4. Java Model to Receive JSON Data

Jackson or Gson needs to know how to map a JSON object to the target Java type. For a simple JavaBean, the model can look like this:

```java
public class Order {

    private Long orderId;
    private String customerName;
    private BigDecimal amount;

    public Order() {
    }

    public Long getOrderId() {
        return orderId;
    }

    public void setOrderId(Long orderId) {
        this.orderId = orderId;
    }

    public String getCustomerName() {
        return customerName;
    }

    public void setCustomerName(String customerName) {
        this.customerName = customerName;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public void setAmount(BigDecimal amount) {
        this.amount = amount;
    }
}
```

The JSON field `orderId` is mapped to property `orderId`, `customerName` to `customerName`, and `amount` to `BigDecimal amount` according to the JSON library's rules.

For monetary data, `BigDecimal` is usually more suitable than `double` because it preserves decimal precision. Do not use floating-point if calculations require exact amounts.

## 5. Integrating JsonItemReader into a Chunk Step

After configuring the reader, register it in the Step like a normal `ItemReader`:

```java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JsonItemReader<Order> orderJsonReader,
        ItemProcessor<Order, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(orderJsonReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

With `chunk(100, transactionManager)`, the Step processes up to 100 items in a transactional chunk. The reader continues reading the next object in the JSON array across chunks until EOF.

Chunk size is not the number of objects the parser loads from the entire file. `JsonItemReader` reads objects sequentially one by one, while Spring Batch holds the items of the current chunk until the transaction completes. Choose the chunk size based on object size, transaction duration, heap, and writer performance.

## 6. Reading a JSON File from JobParameters

In real batch environments, the input file often changes on each run. You can use `@StepScope` to inject the path from `JobParameters`:

```java
@Bean
@StepScope
public JsonItemReader<Order> orderJsonReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new JsonItemReaderBuilder<Order>()
            .name("orderJsonReader")
            .resource(new FileSystemResource(inputFile))
            .jsonObjectReader(new JacksonJsonObjectReader<>(Order.class))
            .strict(true)
            .saveState(true)
            .build();
}
```

`@StepScope` allows reading `JobParameters` once the current `StepExecution` exists. Each run can use a different file without keeping a mutable path in a singleton reader.

If `inputFile` is required, validate it before opening the reader. If there is a default, consider materializing that value into `JobParameters` at launch time so restarts always use the exact original file. Do not let a dynamic default change by date or deployment while an old `JobInstance` still needs to restart.

## 7. Reading Resources from Classpath or Filesystem

`JsonItemReader` accepts a `Resource`, so it can read JSON packaged with the application or an external file.

Classpath resource:

```java
.resource(new ClassPathResource("data/orders.json"))
```

Filesystem resource:

```java
.resource(new FileSystemResource("/var/batch/inbound/orders.json"))
```

Classpath is suited for fixtures, sample data, or immutable default files packaged in the artifact. Filesystem is suited for files delivered by upstream on a schedule or changing per `JobExecution`.

Do not assume every classpath resource can be converted to a `File`; when a resource resides inside an executable JAR, it may only be readable via a stream. The `Resource` abstraction lets the reader handle the source without application code calling `getFile()`.

For filesystem paths obtained from `JobParameters`, verify that the path is allowed to be read, check access permissions, and ensure file stability. Do not allow an arbitrary parameter to point to any location on the host if the Job only needs an inbound directory.

## 8. Customizing Jackson ObjectMapper

`JacksonJsonObjectReader` uses Jackson to map JSON objects. When data contains date/time types, different naming conventions, or special field rules, you can configure an `ObjectMapper` and pass it to the reader.

Example registering the Java Time module:

```java
@Bean
public JsonObjectReader<Trade> tradeJsonObjectReader() {
    ObjectMapper objectMapper = new ObjectMapper();
    objectMapper.registerModule(new JavaTimeModule());

    return new JacksonJsonObjectReader<>(objectMapper, Trade.class);
}
```

The model can contain `LocalDate`:

```java
public class Trade {

    private String symbol;
    private LocalDate tradeDate;
    private BigDecimal price;

    public Trade() {
    }

    // getters and setters
}
```

JSON:

```json
{
  "symbol": "ACME",
  "tradeDate": "2026-11-15",
  "price": 125.75
}
```

`JavaTimeModule` helps Jackson handle Java date/time types when the data format matches. If the source uses a non-ISO format, configure the appropriate formatter/annotation and test with real data.

The constructor accepting `ObjectMapper` and parameter order should be checked against the Spring Batch version in use. If another version's API differs, configure `JacksonJsonObjectReader` using the constructor or factory method provided by that dependency.

## 9. Using GsonJsonObjectReader

If the application uses Gson, you can replace the Jackson reader with `GsonJsonObjectReader`:

```java
@Bean
public JsonItemReader<Order> orderJsonReader() {
    return new JsonItemReaderBuilder<Order>()
            .name("orderJsonReader")
            .resource(new ClassPathResource("data/orders.json"))
            .jsonObjectReader(new GsonJsonObjectReader<>(Order.class))
            .saveState(true)
            .build();
}
```

The `JsonItemReader` configuration stays the same: resource, reader name, and state. The change is in the implementation used to convert a JSON object into an `Order`.

Choose a JSON library that fits the existing system. Do not bring in both Jackson and Gson just to use two mapping approaches for the same file without a clear need. Check how the library handles nulls, unknown fields, enums, dates/times, large numbers, and model constructors.

## 10. Field Names Differing from Java Properties

JSON may use snake_case while the Java model uses camelCase:

```json
{
  "order_id": 1001,
  "customer_name": "Lan",
  "total_amount": 125.50
}
```

Model:

```java
public class Order {
    private Long orderId;
    private String customerName;
    private BigDecimal totalAmount;

    // getters and setters
}
```

With Jackson, you can use `@JsonProperty`:

```java
public class Order {

    @JsonProperty("order_id")
    private Long orderId;

    @JsonProperty("customer_name")
    private String customerName;

    @JsonProperty("total_amount")
    private BigDecimal totalAmount;
}
```

Or configure a naming strategy on `ObjectMapper` if the entire file follows the same convention. Use annotations when mapping needs to be explicit per field; use a naming strategy when the rule is uniform and applied intentionally.

## 11. Nested Objects and Arrays Within Each Item

An element of a JSON array may contain nested objects or arrays. `JsonItemReader` still treats the entire outer object as one item; the JSON library maps the nested parts into the model.

Example:

```json
[
  {
    "orderId": 1001,
    "customer": {
      "customerId": 501,
      "name": "Lan"
    },
    "lines": [
      { "sku": "A-10", "quantity": 2 },
      { "sku": "B-20", "quantity": 1 }
    ]
  }
]
```

The model can represent the nested structure:

```java
public class Order {
    private Long orderId;
    private Customer customer;
    private List<OrderLine> lines;

    // getters and setters
}

public class Customer {
    private Long customerId;
    private String name;

    // getters and setters
}

public class OrderLine {
    private String sku;
    private int quantity;

    // getters and setters
}
```

One `read()` call returns a complete `Order` along with its `Customer` and list of `OrderLine`. The reader does not return each line as a separate item unless the source design or a custom reader requires it.

## 12. JSON Nulls, Missing Fields, and Unknown Fields

JSON may have missing fields, fields with `null` values, or new fields that the model does not yet know about.

```json
[
  { "orderId": 1001, "amount": 125.50 },
  { "orderId": 1002, "customerName": null, "amount": 89.00 },
  { "orderId": 1003, "customerName": "An", "amount": 240.75, "newField": "extra" }
]
```

Cases to decide on:

- Missing field: keep the Java property's default value or apply configured mapping rules.
- Field with `null`: the property can receive `null` if its type allows it; primitives such as `int` cannot hold null.
- Unknown field: behavior depends on the JSON library configuration; Jackson by default often rejects unknown properties in many configurations, whereas Gson behaves differently.
- Required field: validate explicitly after mapping or use an appropriate validation mechanism.

Do not let a default value in the model accidentally mask an upstream omission of a required field. Define the JSON contract and validate the data after parsing.

## 13. Numeric Types and Precision

JSON represents numbers as `number`, but the Java model can choose `Integer`, `Long`, `BigDecimal`, or other types. For large IDs, use a sufficiently wide type. For currency or decimal numbers requiring precision, prefer `BigDecimal`.

Example:

```json
{
  "orderId": 922337203685,
  "quantity": 3,
  "unitPrice": 19.99
}
```

Model:

```java
public class OrderLine {
    private Long orderId;
    private Integer quantity;
    private BigDecimal unitPrice;
}
```

Do not parse currency as `double` and convert to `BigDecimal` afterward because binary floating-point error may already have been introduced. Configure and test the JSON library to confirm decimal numbers map to the exact target type.

## 14. Checkpoints and Restart

`JsonItemReader` is a stateful reader that supports saving reading progress into the Step `ExecutionContext`. Enable `saveState(true)` and give the reader a stable name:

```java
return new JsonItemReaderBuilder<Order>()
        .name("orderJsonReader")
        .resource(resource)
        .jsonObjectReader(new JacksonJsonObjectReader<>(Order.class))
        .saveState(true)
        .build();
```

When a Job restarts the same `JobInstance`:

1. Spring Batch creates a new `StepExecution` for the rerun.
2. The reader reopens the resource and initializes a new JSON parser.
3. The reader reads the item count saved in `ExecutionContext`.
4. The reader restores its logical position to the next item to process.
5. The Step continues reading the remaining objects.

The reader does not keep the old parser or stream across a process restart. It reopens the file and reconstructs the read position based on the checkpoint. For item-count-based readers, recovery may need to read past previous items to reach the saved position; restarting a very large file can take longer than resuming an open cursor.

To restart properly:

- Keep the identifying `JobParameters` unchanged to continue the same `JobInstance`.
- Use the same input file and the same JSON content.
- Keep the reader name stable.
- Enable `saveState` if checkpointing is needed.
- Do not reorder, insert, or delete objects before the checkpoint position.
- Store a checksum, version, or manifest if you need to verify the file is still the original version.

Item-count checkpointing is only safe when the data source does not change in a way that shifts item order.

## 15. Resource Changes Between Runs and Restarts

Suppose a JSON file has 10,000 objects and the Step has committed 5,000 items before failing. If upstream overwrites the file before restart, item count 5,000 may point to a different object than in the initial run.

To avoid reading the wrong data:

- Copy the file to an immutable staging directory before launching the Job.
- Use a unique filename or batch ID for each import.
- Store the file's checksum or version metadata.
- Archive the file after the Job completes.
- Do not reuse the same identifying `JobParameters` for different file contents.
- When file content changes, decide whether it is a new `JobInstance` or a restart of the old job.

If the file is a classpath resource packaged inside a JAR, the artifact version is also part of stability. Deploying a new artifact can change the classpath resource content while an old Job still needs to restart.

## 16. Strict Mode and Resource Checking

`strict(true)` instructs the reader to verify that the resource exists when opening. It helps detect missing files or wrong paths early.

Strict mode does not validate the entire JSON. An existing resource can still contain malformed JSON, an invalid root structure, or objects that fail to map to the target class.

Distinguish between:

| Check | Purpose |
|---|---|
| Resource strictness | Whether the file exists and can be opened |
| JSON syntax | Whether the content is valid JSON |
| Root structure | Whether the document is an array of objects matching what the reader expects |
| Object mapping | Whether fields can be converted to Java types |
| Business validation | Whether the object is valid according to business rules |

These steps can fail for different reasons and need appropriate error messages.

## 17. Handling Parse and Mapping Errors

Some common errors:

| Stage | Example | How to handle |
|---|---|---|
| Opening resource | File does not exist, no read permission | Check path and permissions; fail early if file is required |
| Parsing JSON | Missing comma, mismatched bracket, invalid token | Fix source file; usually fail because the parser cannot recover safely |
| Root structure | Root is an object instead of an array | Normalize input or use another reader |
| Mapping | String cannot be converted to number/date | Check field and conversion configuration |
| Schema drift | Required field missing or new field appears | Update contract/mapping and validation |
| Business validation | Negative quantity, non-existent business code | Handle in processor/validator |

Do not broadly skip all JSON exceptions. When document syntax is broken, a streaming parser may not be able to identify the next object boundary to continue safely. A mapping error on a single object may be handleable differently depending on the JSON library; check the actual exception and the parser's ability to continue before applying skip.

An often easier-to-control design is to let the JSON parser map structurally valid objects, then use `ItemProcessor` to check business rules and throw a dedicated exception such as `InvalidOrderException` if the item is allowed to be skipped.

## 18. Combining Retry and Skip

`JsonItemReader` can participate in a fault-tolerant Step like other readers. However, retry and skip should be applied according to root cause:

- Transient I/O errors when accessing the source can be retried if the reader can safely reopen the source.
- A JSON parse/mapping error on a single object should only be skipped when the parser can still continue and business rules allow dropping the item.
- JSON syntax errors in the middle of the document should generally fail the Step.
- Business validation errors can be skipped by policy if the item does not affect the integrity of the whole batch.

Example skipping business errors in the processor:

```java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JsonItemReader<Order> orderJsonReader,
        ItemProcessor<Order, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(orderJsonReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .faultTolerant()
            .skip(InvalidOrderException.class)
            .skipLimit(20)
            .build();
}
```

This is an example for business exceptions thrown by the processor, not a recommendation to skip every exception raised by Jackson/Gson.

## 19. Streaming and Memory

`JsonItemReader` reads objects in the array one by one, making it better suited to large files than deserializing the entire JSON array into a `List<Order>` before processing. Even so, memory still depends on:

- Size of each JSON object.
- Number of objects held in a chunk.
- Depth and count of nested objects/arrays.
- Internal buffers of the parser.
- State/caching in the processor and writer.
- Number of concurrently running Steps or Jobs.

To control memory:

- Keep the chunk size appropriate for the object size.
- Do not accumulate all items into a collection inside the processor/writer.
- Map only the needed fields if the model can be designed more concisely.
- Measure heap and GC with files close to production size.
- Avoid a single JSON object containing a huge nested array if each sub-element is the unit that needs processing.

If the source structure is a large object containing an `items` array, the built-in `JsonItemReader` does not automatically turn that nested array into the root array of items. You can normalize the file or write a custom reader to iterate the nested array in a streaming manner.

## 20. JsonItemReader and JSON Lines/NDJSON

JSON array:

```json
[
  {"orderId": 1001, "amount": 10.5},
  {"orderId": 1002, "amount": 20.0}
]
```

JSON Lines/NDJSON:

```text
{"orderId": 1001, "amount": 10.5}
{"orderId": 1002, "amount": 20.0}
```

The two formats have different structures. `JsonItemReader` is designed to read objects inside a JSON array. NDJSON has one independent object per line and no enclosing `[`/`]`; do not feed it directly into the reader and expect it to behave like a JSON array.

For NDJSON, you can use `FlatFileItemReader` to read line by line and map each line with Jackson/Gson, or write a custom `ItemReader`. That approach enables line-based checkpointing and processes each record according to its actual format.

## 21. Custom JsonObjectReader

If you need a different JSON library or custom mapping rules, you can implement `JsonObjectReader<T>` and pass it to `JsonItemReaderBuilder`.

In terms of responsibilities, a custom reader needs to:

- Open the `Resource` and prepare the parser.
- Read the next object in the JSON array.
- Convert the object into type `T`.
- Return `null` when items are exhausted according to the contract expected by `JsonItemReader`.
- Close the parser and stream when `close()` is called.
- Release resources even when parsing or mapping throws an exception.

Illustrative structural example:

```java
public class CustomTradeJsonObjectReader implements JsonObjectReader<Trade> {

    @Override
    public void open(Resource resource) throws Exception {
        // Open resource and initialize streaming parser.
    }

    @Override
    public Trade read() throws Exception {
        // Read next object and map to Trade; return null at EOF.
        return null;
    }

    @Override
    public void close() throws Exception {
        // Close parser and stream.
    }
}
```

This is a skeleton illustrating responsibilities, not a complete implementation. Follow the exact interface of the Spring Batch version in use and handle array start/end state, nested structures, exceptions, and resource lifecycle.

If you only need to change how objects map to Java classes, prefer an existing `JsonObjectReader` implementation and configure Jackson/Gson before writing your own parser.

## 22. Limiting Item Count and Reader Configuration

Spring Batch versions provide item-counting reader properties such as maximum item limit or initial item position via the builder/reader API. These options are useful for testing or running a defined data range.

Basic configuration examples should still focus on the core properties:

```java
return new JsonItemReaderBuilder<Order>()
        .name("orderJsonReader")
        .resource(resource)
        .jsonObjectReader(new JacksonJsonObjectReader<>(Order.class))
        .saveState(true)
        .strict(true)
        .build();
```

If using `maxItemCount` or `currentItemCount`, clearly verify their exact meaning in your specific version and their interaction with checkpoint/restart. Do not use `currentItemCount` to arbitrarily skip business data; processing scope should be expressed through explicit `JobParameters` or a query/manifest.

## 23. Security When Reading Untrusted JSON

JSON does not have an external entity mechanism like XML, yet untrusted data still needs control. Risks include:

- Overly large JSON objects or excessively deep nesting causing CPU/heap exhaustion.
- Input strings containing malicious payloads forwarded to SQL, logs, or other systems.
- Overly permissive polymorphic deserialization configuration creating a risk of instantiating unintended types.
- File paths obtained from `JobParameters` pointing to resources outside the allowed directory.
- Sensitive data written in full to logs upon parse failure.

With Jackson, do not enable broad default typing for external JSON without clear requirements and security design. Consider limiting input size, parser depth, and string/number sizes according to your Jackson version's capabilities. Validate data before using it in SQL or service calls.

Do not log the entire raw JSON in exception logs if the file contains personal information, tokens, or financial data. Log the record ID, filename, item position, and error code sufficient for investigation.

## 24. Common Pitfalls When Using JsonItemReader

### Root JSON is not an array

The reader expects an array of objects at the top level. If the source is a wrapper object or NDJSON, normalize it or use a different reader.

### Missing JsonObjectReader

The reader needs an implementation to map each object. Configure `JacksonJsonObjectReader`, `GsonJsonObjectReader`, or an appropriate custom reader.

### Model does not match JSON

Mismatched field names, data types, constructors, or annotations can cause mapping failures. Check the model and JSON library.

### Dates/times or decimal numbers do not parse properly

The source format differs from the mapper configuration. Register the appropriate module/formatter and use `BigDecimal` for values requiring precision.

### Enabling skip for all parse errors

The parser may be unable to recover after malformed JSON. Only skip item-level errors when continuation is safe and business rules permit.

### Restarting on a modified file

The item-count checkpoint may point to a different record. Keep the file immutable or verify its checksum/version.

### Renaming the reader between runs

The reader name is used to build state keys. Renaming it can prevent the reader from finding the old checkpoint.

### Disabling saveState while expecting restart

Without saving state, the reader cannot resume progress through the normal checkpoint mechanism. Enable `saveState` when restart is required.

## 25. Testing JsonItemReader

Test the reader both standalone and in a Job integration test:

1. A JSON array with one object.
2. A JSON array with multiple objects, verifying the reader returns them in order.
3. An empty JSON array, verifying the reader returns `null` immediately when data is exhausted.
4. Root JSON as a wrapper object or NDJSON to confirm unsupported formats directly.
5. Missing fields, null fields, unknown fields, and wrong data types.
6. Nested objects and nested arrays mapped accurately.
7. Dates/times, enums, and decimal numbers converted accurately.
8. Non-existent resource when strict mode is enabled.
9. Malformed JSON at the beginning, middle, and end of the file.
10. Job restart after several committed chunks with the same `JobInstance` and an unchanged file.
11. File modified between initial run and restart to verify checksum/version checks if needed.
12. Large files to measure heap, GC, and throughput.

When testing `ItemStreamReader` directly, invoke the `open(ExecutionContext)`, `read()`, `update(ExecutionContext)`, and `close()` lifecycle per contract. In a Job integration test, Spring Batch manages the reader lifecycle.

Restart tests must use a `JobRepository` that retains metadata across runs. If the repository or `ExecutionContext` is recreated fresh, the test does not prove checkpoint recovery capability.

## 26. JsonItemReader Design Rules

Use `JsonItemReader` when the source is a JSON array containing well-structured objects and each object is a batch item. Configure a `JsonObjectReader` matching the application's JSON library, and define the Java model and mapping rules for fields, nested objects, dates/times, and decimal numbers. Plug the reader into a chunk Step to process items one by one.

For per-run files, use `@StepScope` to inject `JobParameters` and keep the file unchanged across restarts. Give the reader a stable name, enable `saveState` when checkpointing is needed, and do not modify array contents or ordering while the Job may still restart. Distinguish JSON syntax errors from business validation errors; only skip items when the parser continues safely and business rules accept it.

If the source is NDJSON or a wrapper object containing a nested array, choose an appropriate reader or write a custom reader rather than assuming all JSON shares the same structure. Combining the right resource, mapping, chunk, checkpoint, and validation enables `JsonItemReader` to process JSON item by item in a controlled and restartable manner.
