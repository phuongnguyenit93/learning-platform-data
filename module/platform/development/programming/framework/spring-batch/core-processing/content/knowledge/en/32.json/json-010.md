# Restart JSON Reader

In Spring Batch, `JsonItemReader` reads each object from an array-structured JSON document. The reader can save reading state into `ExecutionContext`, allowing a Step to resume from the committed position when a Job is restarted. For this mechanism to be reliable, keep the input file, Reader name, item order, and identifying `JobParameters` unchanged across runs.

Restarting a JSON reader does not mean the parser automatically repairs broken JSON files. If the document is invalid or the file was modified between runs, old checkpoints may no longer point to the right item. Therefore, combine `saveState`, `JobRepository`, chunk-level transaction boundaries, and immutable source data.

## 1. How Does JsonItemReader Read Data?

`JsonItemReader<T>` is an `ItemReader` for JSON. The reader uses a `JsonObjectReader<T>` to parse each object in the document and convert it into Java type `T`.

The standard input format is a JSON array containing objects of the same type:

```json
[
  {
    "orderId": "ORD-1001",
    "customerId": "CUST-01",
    "amount": 125.50
  },
  {
    "orderId": "ORD-1002",
    "customerId": "CUST-02",
    "amount": 89.90
  },
  {
    "orderId": "ORD-1003",
    "customerId": "CUST-03",
    "amount": 240.00
  }
]
```

The reader returns each object on successive `read()` calls:

```text
orders.json
    |
    v
  JSON array
    |
    +--> object 1 -> Order
    +--> object 2 -> Order
    +--> object 3 -> Order
    |
    v
  ItemProcessor
    |
    v
  ItemWriter
```

The reader uses a streaming JSON reading API rather than creating an in-memory collection of the entire file. This suits large files and chunk processing.

## 2. JsonObjectReader and Its Implementations

`JsonItemReader` separates read-stream and checkpoint management from the JSON parsing library. The `JsonObjectReader<T>` interface handles opening the source, reading the next object, and closing the parser.

Spring Batch provides common implementations:

| Implementation | Parse library | When appropriate |
|---|---|---|
| `JacksonJsonObjectReader<T>` | Jackson | The application already uses Jackson or needs the Jackson ecosystem. |
| `GsonJsonObjectReader<T>` | Gson | The application uses Gson to map JSON to Java objects. |

Example using Jackson:

```java
import org.springframework.batch.item.json.JacksonJsonObjectReader;

JacksonJsonObjectReader<Order> objectReader =
        new JacksonJsonObjectReader<>(Order.class);
```

`Order.class` is the object type that each element in the JSON array maps to. JSON structure and property names must be compatible with the target class or configured using the JSON library's annotations/modules.

## 3. Configuring JsonItemReader with Builder

With Spring Batch 5, you can use `JsonItemReaderBuilder`:

```java
import org.springframework.batch.item.json.JsonItemReader;
import org.springframework.batch.item.json.JacksonJsonObjectReader;
import org.springframework.batch.item.json.builder.JsonItemReaderBuilder;
import org.springframework.core.io.FileSystemResource;

@Bean
public JsonItemReader<Order> orderJsonReader() {
    return new JsonItemReaderBuilder<Order>()
            .name("orderJsonReader")
            .resource(new FileSystemResource("/data/in/orders.json"))
            .jsonObjectReader(new JacksonJsonObjectReader<>(Order.class))
            .saveState(true)
            .build();
}
```

Key settings:

- `name(...)`: stable Reader name, used to identify state in `ExecutionContext`.
- `resource(...)`: JSON resource to read.
- `jsonObjectReader(...)`: strategy converting each JSON object into a Java object.
- `saveState(true)`: enables saving reading state for restart.

The Reader name must remain stable across runs/restarts of the same Step. Renaming it can change the state key and prevent the Reader from restoring the old checkpoint as expected.

## 4. Reading Dynamic Files with JobParameters and @StepScope

In practice, the JSON file is often determined at Job launch time. You can pass the path via `JobParameters` and inject it into the Reader via SpEL:

```java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.json.JsonItemReader;
import org.springframework.batch.item.json.JacksonJsonObjectReader;
import org.springframework.batch.item.json.builder.JsonItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

@Bean
@StepScope
public JsonItemReader<Order> orderJsonReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    if (inputFile == null || inputFile.isBlank()) {
        throw new IllegalArgumentException("inputFile is required");
    }

    return new JsonItemReaderBuilder<Order>()
            .name("orderJsonReader")
            .resource(new FileSystemResource(inputFile))
            .jsonObjectReader(new JacksonJsonObjectReader<>(Order.class))
            .saveState(true)
            .build();
}
```

`@StepScope` defers creating the target Reader until `StepExecution` starts. By then, `jobParameters['inputFile']` holds the current `JobExecution`'s value. This also keeps concurrent Jobs with different files from overwriting the path on a shared singleton Reader.

When launching the Job:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "/data/in/orders-2026-11-15.json", true)
        .toJobParameters();

jobLauncher.run(importOrdersJob, parameters);
```

If restart is needed, reuse the exact same identifying parameter `inputFile` and ensure the file at that path is still the original version.

## 5. Java Types Receiving JSON

The object reader maps JSON tokens to Java class properties. Example:

```java
import java.math.BigDecimal;

public class Order {

    private String orderId;
    private String customerId;
    private BigDecimal amount;

    public String getOrderId() { return orderId; }
    public void setOrderId(String orderId) { this.orderId = orderId; }

    public String getCustomerId() { return customerId; }
    public void setCustomerId(String customerId) { this.customerId = customerId; }

    public BigDecimal getAmount() { return amount; }
    public void setAmount(BigDecimal amount) { this.amount = amount; }
}
```

A JSON object can map directly to this type if property names match. For identifiers like `orderId`, keep type `String` to preserve leading zeros. For currency, use `BigDecimal` instead of `double` to avoid floating-point errors.

If a JSON field name differs from the Java property name, use Jackson annotations like `@JsonProperty`:

```java
@JsonProperty("order_id")
private String orderId;
```

For `LocalDate`, `LocalDateTime`, or Java Time types, configure the appropriate Jackson module (typically `JavaTimeModule`) in the `ObjectMapper` used by `JacksonJsonObjectReader`. Align date/time formats and timezones per the data contract.

## 6. JSON Array vs. NDJSON

`JsonItemReader` is designed to read a JSON array of objects. It is not the default reader for Newline Delimited JSON (NDJSON), where each line is a separate JSON document.

JSON array:

```json
[
  {"id": "A-1", "amount": 10.5},
  {"id": "A-2", "amount": 20.0}
]
```

NDJSON:

```text
{"id":"A-1","amount":10.5}
{"id":"A-2","amount":20.0}
```

For NDJSON, use `FlatFileItemReader` to read line by line and Jackson `ObjectMapper` inside a `LineMapper` or `ItemProcessor` to convert each line into an object. Do not feed NDJSON directly into `JsonItemReader` expecting it to recognize each line's boundary automatically.

If the file has a root object containing a nested array, such as `{ "metadata": ..., "orders": [...] }`, use a suitable reader/adapter to navigate to the `orders` array, or transform the file into the array format `JsonItemReader` expects. Never assume every JSON document is a root array.

## 7. JsonItemReader Checkpoints

`JsonItemReader` supports `ItemStream` and stores reading state in `ExecutionContext` when `saveState(true)` is set. The reader relies on the number of items read to restore its position in the document on restart.

In a chunk-oriented Step, checkpoints are saved alongside metadata at appropriate commit boundaries:

```text
JobExecution #1
  JSON item 1..500    -> Chunk 1 COMMIT
  JSON item 501..1000 -> Chunk 2 COMMIT
  JSON item 1001..1500 -> Chunk 3 FAILED / ROLLBACK

ExecutionContext stores state at the committed checkpoint
```

On restart, the Reader reopens the resource, skips past items already recorded in the checkpoint, and resumes returning subsequent items. This allows processing large JSON without holding the entire array in memory.

Conditions for checkpoints to be meaningful:

- Reader has a stable name.
- `saveState(true)` is enabled.
- `JobRepository` persists metadata durably.
- The same `JobInstance` is restarted with the same identifying `JobParameters`.
- The JSON file is not edited, replaced, or reordered.
- The Step uses the Reader directly or a wrapper forwarding the full `ItemStream` lifecycle.

## 8. Restarting After a Chunk Failure

Suppose a Job reads 10,000 orders with commit interval 500. The first two chunks commit, yet the Writer hits an error in the third chunk:

```text
Chunk 1: items 1-500       -> COMMIT
Chunk 2: items 501-1000    -> COMMIT
Chunk 3: items 1001-1500   -> ROLLBACK
                              |
                              v
                         Job FAILED
                              |
                              v
                    Restart same JobInstance
                              |
                              v
                    Reader restores checkpoint
                              |
                              v
                    Rereads from item 1001
```

Business changes in committed chunks are preserved. The failed chunk can be reread and reprocessed because the checkpoint only reflects the prior committed state.

Therefore, the Writer must be idempotent. For instance, use a unique constraint on `sourceOrderId` and upsert per business rules so retried items do not create duplicate records.

## 9. Restarting via JobLauncher with the Same JobParameters

Restarting the right `JobInstance` requires keeping identifying `JobParameters` unchanged. Example:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "/data/in/orders-2026-11-15.json", true)
        .addString("businessDate", "2026-11-15", true)
        .toJobParameters();

JobExecution execution = jobLauncher.run(importOrdersJob, parameters);
```

If the previous `JobExecution` was `FAILED` or `STOPPED` and the Job/Step permits restart, launching again with the same identifying parameters can create a new `JobExecution` for the same `JobInstance`.

Do not add a new timestamp or UUID as an identifying parameter just to re-invoke the Job. Doing so creates a new `JobInstance`, and the Reader starts a new unit of work instead of restoring the old checkpoint.

## 10. Reader and Step Must Participate in the ItemStream Lifecycle

Spring Batch manages `open`, `update`, and `close` for `ItemStream` components registered in the Step. When `JsonItemReader` is declared directly via `.reader(reader)`, the Step manages its lifecycle.

If the Reader is wrapped by a custom reader/decorator, the wrapper must forward `ItemStream` or the delegate must be registered explicitly:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, ProcessedOrder>chunk(500, transactionManager)
        .reader(customReader)
        .writer(orderWriter)
        .stream(delegateJsonReader)
        .build();
```

This example assumes `customReader` does not forward lifecycle calls to `delegateJsonReader` itself. If the wrapper already implements `ItemStream` and forwards `open`, `update`, and `close`, do not register the delegate a second time. If the lifecycle is not invoked, the JSON reader's checkpoint may fail to save or restore properly.

## 11. JSON File Must Be Immutable Across Restarts

The JSON reader's checkpoint is based on item position in the document. If the file changes between two runs, the same position can point to a different object.

Example:

```text
First run:
  item 1 = ORD-1001
  item 2 = ORD-1002
  item 3 = ORD-1003
  checkpoint = after item 2

File modified:
  item 1 = ORD-1000 (inserted)
  item 2 = ORD-1001
  item 3 = ORD-1002
  item 4 = ORD-1003

Restarting at the old position may skip/reread the wrong record.
```

To prevent this:

1. Producer writes a temporary file, closes it, then publishes the official filename.
2. Job only reads completed files.
3. Store checksum, size, or object version of the file on batch ingestion.
4. Do not modify the input file throughout the `JobInstance` lifecycle.
5. If the producer sends a new version, use a new file version and new identifying parameter to create a new `JobInstance`.

Keeping the same path while swapping contents is insufficient to guarantee accurate restarts. Ensure the resource's actual bytes stay stable.

## 12. Mid-File JSON Errors and the Limits of Skip

JSON syntax errors differ from business errors on an already-parsed object.

| Error type | Example | Appropriate behavior |
|---|---|---|
| Invalid JSON | Missing `]`, missing `}`, trailing comma, unclosed string | Stop processing file, quarantine, and request a valid file. |
| Truncated file | File ends mid-object or before array closing bracket | Treat as incomplete file; re-receive file. |
| Valid object missing business data | `amount` null or `orderId` blank | Validate in Processor; skip/reject if permitted. |
| Value violating business rules | Negative `amount` or unsupported status | Throw business exception and apply matching skip policy. |
| Target write error | Deadlock or constraint violation | Retry/fail per Writer and transaction policy. |

If JSON syntax breaks mid-array, the parser may be unable to locate the next object boundary. Configuring `.skip(...)` on parse exceptions does not restore parser state for safe continuation. Restarting against the same broken file will repeatedly hit the error in the uncommitted region.

If continuing past individual bad records is required, use NDJSON or one object per independent file/message, where record boundaries are explicit. For standard JSON arrays, mid-document syntax errors should generally fail the entire file.

## 13. Nested JSON Arrays and Heterogeneous Schemas

`JsonItemReader` reads objects at the configured array level. When a JSON object has complex structure, the object reader can map the entire nested structure into one DTO:

```json
[
  {
    "orderId": "ORD-2001",
    "customer": {
      "id": "CUST-01",
      "name": "An Nguyen"
    },
    "lines": [
      {"sku": "SKU-01", "quantity": 2},
      {"sku": "SKU-02", "quantity": 1}
    ]
  }
]
```

Each item remains one order; `customer` and `lines` map to a nested object/list inside the DTO. If elements in the array have differing schemas, use a suitable shared type, controlled polymorphic mapping, or a custom `JsonObjectReader`. Do not force every object into one DTO while ignoring unrecognized fields without a schema-versioning policy.

If you only need to read a nested array inside a root object, use a custom reader or transform the input beforehand. `JsonItemReader` does not infer which nested property name should act as the item list.

## 14. Skipping Business Errors After Parsing the JSON Object

A valid JSON object can contain invalid business data. Let the parser convert it into a DTO, then check business rules in the Processor:

```java
import java.math.BigDecimal;

import org.springframework.batch.item.ItemProcessor;

public class OrderProcessor
        implements ItemProcessor<Order, ProcessedOrder> {

    @Override
    public ProcessedOrder process(Order order) {
        if (order.getOrderId() == null || order.getOrderId().isBlank()) {
            throw new InvalidOrderException("orderId is required");
        }

        BigDecimal amount = order.getAmount();
        if (amount == null || amount.signum() < 0) {
            throw new InvalidOrderException("amount must be non-negative");
        }

        return new ProcessedOrder(order.getOrderId(), amount);
    }
}
```

You can configure a fault-tolerant Step:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, ProcessedOrder>chunk(500, transactionManager)
        .reader(orderJsonReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(100)
        .listener(orderSkipListener)
        .build();
```

This skips business errors after the object has been parsed. If the error occurs in JSON syntax or parser state is corrupted, do not use this same policy expecting the Reader to continue reading the rest.

## 15. Testing JSON Reader Restarts

Restart tests should verify both metadata and business data. A test that only checks Job `COMPLETED` is insufficient to catch missing or duplicate records.

Integration test scenario:

1. Create a JSON array with a known object count and save it as an immutable file in a temporary directory.
2. Launch the Job with an identifying parameter pointing to that file.
3. Force the Writer to fail deterministically after several chunks commit.
4. Verify the first `JobExecution` is `FAILED` and target data contains only committed chunks.
5. Clear the Writer failure condition and restart the same `JobInstance` using the exact same identifying parameters.
6. Verify the Reader resumes after the checkpoint, uncommitted objects are processed, and the Job completes.
7. Verify every business key appears exactly once in the target.

With Spring Batch Test, `JobLauncherTestUtils` helps launch Jobs; `JobExplorer`/`JobRepository` look up `JobInstance`, `JobExecution`, and `StepExecution`. You can use a Writer/service test double that fails on a specific chunk and switches to success mode on restart.

Example assertion checking for no duplicate writes:

```java
Integer count = jdbcTemplate.queryForObject(
        "select count(*) from imported_order where source_order_id = ?",
        Integer.class,
        "ORD-1001");

assertEquals(1, count);
```

When verifying restarts, the `JobInstance` ID of the second run must match the first, while the `JobExecution` ID must differ. If a new identifying UUID is generated on the second run, the test creates a new instance and no longer tests the old Reader's checkpoint.

## 16. Common Pitfalls

| Mistake | Consequence | Fix |
|---|---|---|
| Using JsonItemReader for NDJSON | Reader expects a JSON array, not one JSON document per line. | Use FlatFileItemReader and parse line by line. |
| File lacks a root array | Reader cannot read in the expected format. | Convert the file or use a custom reader for nested arrays. |
| Reader name changes on restart | Old checkpoint may not be found. | Keep `name(...)` stable. |
| Disabling `saveState` while expecting restart | Reader does not save standard checkpoints. | Enable `saveState(true)` or manage state manually. |
| JSON file modified after checkpoint | Item count may point to a different object. | Keep files immutable, store checksum/version. |
| Adding an identifying UUID on restart | Creates a new JobInstance and rereads from start. | Reuse the original identifying JobParameters. |
| Skipping JSON parser exceptions to continue | Parser may be unable to resynchronize after syntax errors. | Quarantine the file or switch to an independent-record format. |
| Non-idempotent Writer | Chunk rollback/restart can create duplicate records. | Unique constraints, upserts, and business keys. |
| Wrapper does not forward ItemStream | Checkpoints fail to save/restore properly. | Forward lifecycle or register `.stream(delegate)`. |

## Conclusion

`JsonItemReader` reads each object in a JSON array through a `JsonObjectReader`, such as `JacksonJsonObjectReader`. When `saveState(true)` and the `ItemStream` lifecycle are properly managed, the Reader stores the number of items read in `ExecutionContext` to resume after committed checkpoints. For safe restarts, keep the Reader name, identifying `JobParameters`, and file contents stable; the Writer must also be idempotent since uncommitted chunks may be reprocessed. Use `JsonItemReader` for JSON arrays, choose line-oriented readers for NDJSON, and treat mid-document syntax errors as file failures needing repair or quarantine rather than safely skippable items.
