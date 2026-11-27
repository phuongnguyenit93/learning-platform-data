# The Map<String, Object> Data Type and Input/Output Compatibility

In the **Single-Step Jobs** chapter of the **SPRING_CLOUD_TASK** module, we explore the data contract when a Spring Cloud Task application runs a **Spring Batch Job with a single Step**. With the **Single Step Batch Job Starter** described in the Spring Cloud Task documentation, each record (item) passing through the processing step has the type `Map<String, Object>`. This makes it possible to connect sources such as CSV, JDBC, queues, or Kafka with write destinations without necessarily defining a separate Java class for every record structure.

However, using `Map<String, Object>` **does not mean every input and output is automatically compatible**. Java can only check the generic type; each reader, processor, and writer must still agree on **key names, value types, required fields, number/date representations, and business semantics**. A record can pass generic type checking yet fail at runtime because the writer expects `BigDecimal` while the reader provides `String`.

This lesson focuses on compatibility at the **`ItemReader<Map<String, Object>>` → `ItemProcessor<Map<String, Object>, Map<String, Object>>` → `ItemWriter<Map<String, Object>>`** boundary, while distinguishing item data from Job parameters, `ExecutionContext`, and `TaskRepository` metadata.

## 1. Learning objectives

After this lesson, you will be able to:

- Explain why the Single Step Batch Job Starter uses `Map<String, Object>` and that it represents **a single item**, not the entire job.
- Align the generic types of `ItemReader`, `ItemProcessor`, and `ItemWriter` within a Step.
- Distinguish **compile-time** type compatibility from **runtime** schema and value compatibility.
- Normalize values coming from CSV, JDBC, and JSON into a consistent output contract.
- Write an `ItemProcessor<Map<String, Object>, Map<String, Object>>` that validates data without blind casting or arbitrarily mutating the input Map.
- Build a single-Step Spring Batch example running inside a Spring Cloud Task application, and understand the difference between starter configuration and manual Job/Step configuration.
- Determine how to manage schema versioning, handle errors, test restarts, persist results, and monitor via Spring Batch/Task.

## 2. What is Map<String, Object> in the Single Step Batch Job Starter?

A `Map<String, Object>` is a structure mapping **String keys** to **Object values**:

~~~java
Map<String, Object> item = new LinkedHashMap<>();
item.put("orderId", "ORD-1001");                // String
item.put("quantity", 2);                       // Integer
item.put("unitPrice", new BigDecimal("19.90")); // BigDecimal
~~~

Here, `item` corresponds to **one order** in the data stream. A Step may process thousands of items; it does not hold the entire list of orders inside a single Map.

| Type component | Meaning | Example |
| --- | --- | --- |
| `Map` | Collection of key–value pairs | A CSV line parsed into an item |
| `String` | Type of field names | `"orderId"`, `"quantity"` |
| `Object` | Common declared type for values | `String`, `Integer`, `BigDecimal`, `LocalDate` |
| `Map<String, Object>` | Type of **one item** in the Step | `{"orderId": "ORD-1001", "quantity": 2}` |

The Spring Cloud Task documentation, in the **Single Step Batch Job Starter** section, describes a single-Step Job whose inputs/outputs are items of type `Map<String, Object>`. The starter supports configuring readers/writers and will pick up a matching generic processor if one is present in the `ApplicationContext`.

Crucially, **this Map convention belongs to the Single Step Batch Job Starter**, not as a mandatory rule for every Spring Cloud Task application or every Spring Batch Job. When building a Step manually with Spring Batch, you are completely free to choose `Order`, `PaymentRecord`, or `Map<String, Object>` as the item type.

## 3. Flow of an item in a single-step Job

A chunk-oriented Step typically has three components:

~~~mermaid
flowchart LR
    A["CSV / JDBC / JSON"] --> B["ItemReader<Map<String, Object>>"]
    B --> C["ItemProcessor<Map<String, Object>, Map<String, Object>>"]
    C --> D["ItemWriter<Map<String, Object>>"]
    D --> E["Database / File / Message broker"]
    C -. "Processor can be omitted" .-> D
    F["JobRepository / StepExecution"] -. "Manages Batch state" .-> C
    G["TaskRepository / TaskExecution"] -. "Tracks finite application" .-> C
~~~

- **Reader** fetches items one by one and returns a `Map`. In Spring Batch, returning `null` from `ItemReader.read()` signals **end of data**.
- **Processor** receives one item, validates/transforms it, and returns an item of the same or different type. Returning `null` from `ItemProcessor.process()` means **filtering out that item**, so it is not passed to the writer.
- **Writer** receives **a chunk of multiple items** to write to the destination. In Spring Batch 5, the typical writer signature is `write(Chunk<? extends T>)`, not receiving a single Map.

If the processor is omitted, the writer receives items directly from the reader. Therefore, if a reader returns raw values from CSV, the writer must handle those raw types, or a normalizing processor must be added.

### Three kinds of data not to confuse with the item Map

| Data type | Purpose | Is it the item Map being processed? |
| --- | --- | --- |
| `Map<String, Object>` of reader/processor/writer | One business record flowing through the Step | **Yes** |
| `JobParameters` | Identifying and control parameters for a `JobInstance`/`JobExecution` | **No** |
| `ExecutionContext` | Checkpoint state saved by Spring Batch to support restarts | **No**, even though internally it resembles a Map |
| `TaskExecution` in Spring Cloud Task | Application lifecycle metadata, timestamps, exit code | **No** |

In particular, `ExecutionContext` is a key/value structure for the state of a `JobExecution` or `StepExecution`. It has its own persistence/serialization mechanism; do not stuff entire item Maps or lists of thousands of records into it. Any non-transient value stored there must be compatible with the repository's serializer.

## 4. Compile-time generic compatibility

A processing chain that preserves the Map type has these declarations:

~~~java
ItemReader<Map<String, Object>> reader;
ItemProcessor<Map<String, Object>, Map<String, Object>> processor;
ItemWriter<Map<String, Object>> writer;
~~~

This compatibility is two-way:

1. **The reader's output** must be **the processor's input**.
2. **The processor's output** must be **the writer's input**.

If there is no processor, **the reader's output** must match **the writer's input**.

### 4.1. Valid declarations

~~~java
ItemReader<Map<String, Object>> reader = /* data-reading bean */;
ItemProcessor<Map<String, Object>, Map<String, Object>> processor =
        item -> new LinkedHashMap<>(item);
ItemWriter<Map<String, Object>> writer = /* data-writing bean */;
~~~

The `reader`, `processor`, and `writer` variables here illustrate the signatures; concrete instantiation is shown in the complete example below.

### 4.2. Error-prone declarations

~~~java
// Not a direct substitute for ItemReader<Map<String, Object>>:
ItemReader<Map<String, String>> textReader;

// Processor changes output type to DTO while writer still expects Map:
ItemProcessor<Map<String, Object>, OrderDto> dtoProcessor;
ItemWriter<Map<String, Object>> mapWriter;
~~~

Even though `String` extends `Object`, **`Map<String, String>` is not a subtype of `Map<String, Object>`**. Java generics are *invariant*. If arbitrary assignment were permitted, a caller could insert a `BigDecimal` into a Map that the producer assumed held only Strings.

Similarly, when a processor returns `OrderDto`, the writer must accept `OrderDto` (if configuring the Step manually) or an adapter must convert the DTO back to a Map before reaching a starter writer that expects a Map.

| Reader output | Processor input → output | Writer input | Conclusion |
| --- | --- | --- | --- |
| `Map<String,Object>` | `Map<String,Object> → Map<String,Object>` | `Map<String,Object>` | Matches the starter contract |
| `Map<String,Object>` | None | `Map<String,Object>` | Matches if fields required by the writer are already present |
| `Map<String,String>` | `Map<String,Object> → Map<String,Object>` | `Map<String,Object>` | Direct generic mismatch |
| `Map<String,Object>` | `Map<String,Object> → OrderDto` | `Map<String,Object>` | Processor output is incompatible |
| `OrderDto` | `OrderDto → OrderSummary` | `OrderSummary` | Valid in a manually configured DTO-typed Step; does not follow the starter Map contract |

Do not use raw `ItemReader` types, `(ItemReader)` casts, or `@SuppressWarnings("unchecked")` just to hide a mismatch. The code might compile, only to fail with `ClassCastException` or writer errors at runtime.

## 5. Runtime compatibility: the same Map type can still fail

Java only knows that values inside the Map are `Object`. It does not automatically verify that every Map has the exact keys, value types, and business constraints the writer requires.

Consider three items:

~~~java
Map<String, Object> a = Map.of(
        "orderId", "ORD-1001",
        "quantity", "2",
        "unitPrice", "19.90");

Map<String, Object> b = Map.of(
        "orderId", "ORD-1002",
        "quantity", 2,
        "unitPrice", new BigDecimal("19.90"));

Map<String, Object> c = new LinkedHashMap<>();
c.put("ORDER_ID", "ORD-1003");
c.put("quantity", null);
~~~

`Map.of` rejects `null` keys or values, so case `c` uses `LinkedHashMap` to illustrate a record with a `null` value and a different key name.

Both `a` and `b` are `Map<String, Object>`, yet their runtime types differ. Item `c` even uses the key name `ORDER_ID` instead of `orderId`. A writer calling `(BigDecimal) item.get("unitPrice")` will fail on `a`; a writer calling `item.get("orderId")` will get `null` on `c`.

**Therefore, you must verify two contracts:**

- **Java contract:** the generics connecting Reader → Processor → Writer.
- **Data contract:** which keys exist, whether they are required, their runtime types, units, and valid value ranges.

### 5.1. Typical data sources table

| Source | Possible value types | Risks |
| --- | --- | --- |
| CSV | Usually `String` after tokenization | `"2"` is not yet an `Integer`; decimal separators / date formats |
| JDBC | `Integer`, `Long`, `BigDecimal`, `Timestamp`, `Date`, or driver-specific types | SQL types and JDBC drivers dictate the Java types |
| JSON from AMQP/Kafka | `Integer`, `Long`, `Double`, `String`, `LinkedHashMap`... | Depending on converter settings, numeric values lose precision if decoded as floating-point |
| Application-built Map | Any `Object` | Bugs from missing keys, wrong key names, or unsupported object types |

Even with the same JSON format, two producers might send `"quantity": "2"` and `"quantity": 2`. If the writer does not normalize, errors surface late after many items have already been read.

### 5.2. Establishing a logical schema for an item

An explicit contract might specify:

| Key | Raw input | Output after processor | Required | Rules |
| --- | --- | --- | --- | --- |
| `orderId` | `String` | `String` | Yes | Non-empty, unique identifier within the appropriate scope |
| `quantity` | `String` or normalized integer | `Integer` | Yes | Greater than 0 |
| `unitPrice` | `String`/decimal number | `BigDecimal` | Yes | Non-negative, defined currency unit |
| `lineTotal` | Not necessarily present | `BigDecimal` | Yes at writer | `quantity × unitPrice` |
| `schemaVersion` | Optional | `Integer` | Recommended | Helps detect data version |

At read time, `lineTotal` may not exist yet. The processor is responsible for computing and adding it before the writer uses it. If the writer outputs CSV, `BigDecimal` can be formatted as a string at the **write boundary**, without ever using `Double` for monetary calculations.

## 6. How the Single Step Batch Job Starter uses Map

The official Spring Cloud Task documentation describes the dependency:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-single-step-batch-job</artifactId>
    <!-- Choose a version actually compatible with the project's Spring Boot/Batch -->
</dependency>
~~~

The reference docs include an example with starter version `2.3.0`. That is an **example tied to the documented release line**, not a recommendation to copy that exact version into a modern Spring Boot project. Check compatible artifacts and release trains before use.

The starter provides properties to define a single-Step Job as documented:

~~~yaml
spring:
  batch:
    job:
      jobName: importOrders
      stepName: normalizeOrders
      chunkSize: 100
~~~

The three properties above belong to the **Single Step Batch Job Starter** as documented; do not assume they create a Step in an application that only has `spring-boot-starter-batch` without the corresponding starter.

When you provide an `ItemProcessor<Map<String, Object>, Map<String, Object>>` bean along with appropriate reader/writer beans, the starter can wire this processor into the Step through its auto-configuration mechanism. The built-in readers/writers listed in the documentation include options for CSV/flat files, JDBC, and messaging systems.

Example of declaring a generically compatible processor:

~~~java
@Bean
ItemProcessor<Map<String, Object>, Map<String, Object>> normalizeOrders() {
    return item -> {
        Map<String, Object> result = new LinkedHashMap<>(item);
        // Validate and normalize fields before emitting.
        return result;
    };
}
~~~

**Version note:** properties, bean creation conditions, reader/writer support, and exact `ItemWriter` types can change across Spring Cloud Task/Spring Batch versions. Consult the documentation for your exact starter version. If you need strict type control and want to avoid depending on starter-specific auto-configuration, you can **declare the Job/Step manually** with Spring Batch, as in the next example.

## 7. Self-contained example: single-Step Job using Map<String, Object>

This example uses **Spring Batch 5.x** with Spring Boot 3.x and a compatible Spring Cloud Task version. We build the Job/Step manually to make the generics explicit, independent of which specific auto-configuration features a given Single Step Batch Job Starter version provides.

The application processes two sample orders. The reader returns Maps with quantity/unit price as **strings**; the processor validates and normalizes them into `Integer`/`BigDecimal`; the writer prints the normalized data. The console writer is for learning purposes only. For production workloads, replace it with an appropriate database or file writer.

### 7.1. Dependencies

In a Maven project with a compatible Spring Boot parent/BOM and Spring Cloud BOM:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-batch</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-task</artifactId>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

The project also needs `spring-boot-maven-plugin` to build an executable JAR. With Spring Boot 3.x + Spring Batch 5.x, the packages and builders below match the documented APIs. For Spring Batch 6 or other versions, check for package/builder changes before applying.

### 7.2. Java code: Reader → Processor → Writer

Create `src/main/java/com/example/task/MapSingleStepApplication.java`:

~~~java
package com.example.task;

import java.math.BigDecimal;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.support.ListItemReader;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBootApplication
@EnableTask
public class MapSingleStepApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(MapSingleStepApplication.class, args);
        int exitCode = SpringApplication.exit(context);
        System.exit(exitCode);
    }

    @Bean
    Job orderJob(JobRepository jobRepository, Step orderStep) {
        return new JobBuilder("orderJob", jobRepository)
                .start(orderStep)
                .build();
    }

    @Bean
    Step orderStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<Map<String, Object>> orderReader,
            ItemProcessor<Map<String, Object>,
                          Map<String, Object>> orderProcessor,
            ItemWriter<Map<String, Object>> orderWriter) {

        return new StepBuilder("orderStep", jobRepository)
                .<Map<String, Object>, Map<String, Object>>
                        chunk(2, transactionManager)
                .reader(orderReader)
                .processor(orderProcessor)
                .writer(orderWriter)
                .build();
    }

    @Bean
    ItemReader<Map<String, Object>> orderReader() {
        Map<String, Object> first = new LinkedHashMap<>();
        first.put("orderId", "ORD-1001");
        first.put("quantity", "2");
        first.put("unitPrice", "19.90");

        Map<String, Object> second = new LinkedHashMap<>();
        second.put("orderId", "ORD-1002");
        second.put("quantity", "3");
        second.put("unitPrice", "5.25");

        return new ListItemReader<>(List.of(first, second));
    }

    @Bean
    ItemProcessor<Map<String, Object>, Map<String, Object>>
            orderProcessor() {
        return input -> {
            String orderId = requiredText(input, "orderId");

            int quantity;
            BigDecimal unitPrice;
            try {
                quantity = Integer.parseInt(
                        requiredText(input, "quantity"));
                unitPrice = new BigDecimal(
                        requiredText(input, "unitPrice"));
            } catch (NumberFormatException ex) {
                throw new IllegalArgumentException(
                        "Invalid quantity or unitPrice", ex);
            }

            if (quantity <= 0 || unitPrice.signum() < 0) {
                throw new IllegalArgumentException(
                        "quantity must be > 0 and unitPrice non-negative");
            }

            Map<String, Object> output = new LinkedHashMap<>();
            output.put("orderId", orderId);
            output.put("quantity", quantity);
            output.put("unitPrice", unitPrice);
            output.put("lineTotal",
                    unitPrice.multiply(BigDecimal.valueOf(quantity)));
            return output;
        };
    }

    @Bean
    ItemWriter<Map<String, Object>> orderWriter() {
        return chunk -> {
            for (Map<String, Object> item : chunk) {
                String orderId = (String) item.get("orderId");
                BigDecimal lineTotal =
                        (BigDecimal) item.get("lineTotal");

                System.out.println(
                        orderId + " => " + lineTotal.toPlainString());
            }
        };
    }

    private static String requiredText(
            Map<String, Object> input, String key) {
        Object value = input.get(key);
        if (!(value instanceof String text)
                || text.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing or invalid type for field: " + key);
        }
        return text.trim();
    }
}
~~~

In this example, `orderProcessor` expects the reader's input to contain three `String` fields. The reader intentionally supplies data matching that exact contract. If you swap in a `JdbcCursorItemReader` returning `BigDecimal` for `unitPrice`, you **must update the normalization rules**; blindly calling `toString()` on arbitrary types can mask schema bugs.

### 7.3. Application config

Create `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: map-single-step
  main:
    web-application-type: none
  datasource:
    url: jdbc:h2:mem:mapstep
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  batch:
    jdbc:
      initialize-schema: always
    job:
      enabled: true
  cloud:
    task:
      name: map-single-step
      initialize-enabled: true
      batch:
        fail-on-job-failure: true
~~~

This configuration illustrates initializing both Batch and Spring Cloud Task metadata infrastructure in **in-memory** H2. Tables and history do not survive across JVM restarts; production needs a persistent database and version-matched migrations.

In a Spring Boot app with one Job and active Batch auto-configuration, Boot can launch the Job at startup. The example already defines `Job`/`Step` manually; **do not also add the Single Step Batch Job Starter generating a second Job** without controlling how Jobs are selected.

The `spring.cloud.task.batch.fail-on-job-failure=true` property maps a failed Batch Job to the Task exit code according to your Spring Cloud Task version's capabilities. Always test failure scenarios and verify the actual exit code; do not assume success just because the runner/Job was invoked.

### 7.4. Run and observe

~~~bash
./mvnw clean package
java -jar target/map-single-step-0.0.1-SNAPSHOT.jar
~~~

On Windows, use `mvnw.cmd clean package` and replace the JAR path with your actual build artifact.

Expected business output in the log:

~~~text
ORD-1001 => 39.80
ORD-1002 => 15.75
~~~

This is output from the console writer, **not persistently stored business data**. We use it to observe types: `unitPrice`/`lineTotal` are `BigDecimal` after the processor, so the writer does not need to re-parse strings.

### 7.5. Why does the processor return a new Map?

`new LinkedHashMap<>()` in the processor prevents accidentally mutating a Map that the reader might reuse or share. In systems with multiple callbacks, caches, or parallel writes, mutating the input Map can create hard-to-diagnose bugs.

Returning a fresh Map also enforces the **target contract**: the writer only receives normalized items. For larger applications, define strongly typed DTO/record classes at business boundaries once the schema stabilizes; use `Map` when you genuinely need the flexibility.

## 8. Connecting with FlatFileItemReader and FlatFileItemWriter

The Single Step Batch Job Starter documentation states that `FlatFileItemReader` can use the `names` property to assign key names in the item Map. Example CSV:

~~~csv
orderId,quantity,unitPrice
ORD-1001,2,19.90
ORD-1002,3,5.25
~~~

According to starter-supported configuration, you can specify:

~~~yaml
spring:
  batch:
    job:
      flatfileitemreader:
        names: orderId,quantity,unitPrice
      flatfileitemwriter:
        names: orderId,quantity,unitPrice,lineTotal
~~~

This is an **excerpt of field name declarations**, not a complete runnable YAML file. You must add `resource`, delimited settings, appropriate reader/writer configuration, Job/Step settings, and verify property names/autoconfiguration conditions for your starter version. The example clarifies the data flow:

- The reader creates keys `orderId`, `quantity`, `unitPrice`.
- The processor can add `lineTotal`.
- The writer can extract keys according to its configured `names` list.

If the writer requires `lineTotal` but the processor did not populate it, output fields will be missing. If the reader changes `orderId` to `order_id`, a processor calling `input.get("orderId")` will fail. This is a **data contract error**, even though the Java generic remains `Map<String, Object>`.

Do not assume a plain Spring Batch `FlatFileItemReader` returns a Map by default: that depends on its `LineMapper` and `FieldSetMapper`. The Map behavior here comes from the starter or your own mapping code.

## 9. Compatibility with JDBC and JSON

### 9.1. JDBC RowMapper

When data comes from a database, a `RowMapper<Map<String, Object>>` can standardize column names:

~~~java
RowMapper<Map<String, Object>> mapper = (rs, rowNum) -> {
    Map<String, Object> item = new LinkedHashMap<>();
    item.put("orderId", rs.getString("order_id"));
    item.put("quantity", rs.getInt("quantity"));
    item.put("unitPrice", rs.getBigDecimal("unit_price"));
    return item;
};
~~~

This mapper returns `Integer`/`BigDecimal`, which **differs** from the `String` inputs expected by the processor in section 7. To reuse processing logic, choose one of two approaches:

1. **Define a standard reader contract**: every reader must return `quantity: Integer`, `unitPrice: BigDecimal`; update the CSV reader to parse types early.
2. **Define a processor that accepts permitted types**: check with `instanceof` and convert explicitly, rejecting unexpected types.

The first approach is usually easier to test across multiple sources; the second is useful at integration boundaries, provided allowed types are strictly bounded. Avoid `(BigDecimal) value` casts when the runtime value might actually be a `String`.

`ResultSet.getInt(...)` returns `0` for SQL `NULL`, so on nullable schemas you must check `rs.wasNull()` or use an object getter. Never confuse SQL `NULL` with a valid zero.

### 9.2. JSON from queues

Example payload:

~~~json
{
  "orderId": "ORD-1001",
  "quantity": 2,
  "unitPrice": "19.90"
}
~~~

A JSON converter might represent `quantity` as `Integer`, `unitPrice` as `String`, and nested objects as `Map`. When receiving JSON from external systems, validate:

- The root is an object, not an array or string.
- Required fields are present and have valid types.
- The schema version is supported.
- Monetary values use exact decimal representation; never convert `Double` carelessly to `BigDecimal`.
- Payload size is bounded and sensitive fields are kept out of logs.

When reading and writing messages via Kafka/AMQP, compatibility also depends on **serializers/deserializers, message converters, and producer/consumer formats**, not just `ItemReader<Map<String, Object>>`.

## 10. Handling missing keys, nulls, wrong types, and dirty data

A common set of rules:

| Situation | Example | Handling |
| --- | --- | --- |
| Missing required key | No `orderId` | Fail with an error code; do not forward broken item to writer |
| Key has `null` | `quantity=null` | Reject or apply a **business-approved** default |
| Wrong type | `quantity=["2"]` | Do not cast/`toString()` arbitrarily; report a schema error |
| Blank string | `orderId="  "` | Reject after trimming |
| Out-of-range number | `quantity=-1` | Reject |
| Inconsistent units | `price` mixes VND and USD | Include `currency` and normalize; never add mixed currencies |
| Wrong field name | `order_id` instead of `orderId` | Map at the reader/adapter |
| Extension fields | New `sourceSystem` | Can be allowed if writer ignores extra keys and schema version permits |
| Same key, conflicting content | Duplicate `orderId` with different price | Apply conflict/versioning policy; do not silently overwrite |

When an item is invalid, deciding whether to **fail the Step**, **skip**, or **filter the item** must follow data requirements:

- `throw exception` when a required field is missing or an invariant is violated.
- `ItemProcessor.process(...)` returns `null` when intentionally **filtering an item** per explicit rules, such as skipping records marked cancelled.
- Spring Batch offers skip/retry via fault-tolerance configuration; not all exceptions are skipped automatically.
- Report read/process/write/skip counts so records are not silently lost when input files have issues.

Never "catch every exception and return `null`" without metrics/reporting. That turns data conversion failures into silent record loss.

## 11. Evolving input/output schemas over time

Maps are flexible but lack compile-time type enforcement, so manage the **data contract like an API**.

Example across two versions:

| Field | v1 | v2 | Assessment |
| --- | --- | --- | --- |
| `orderId` | Required `String` | Unchanged | Compatible |
| `quantity` | Positive integer | Unchanged | Compatible |
| `unitPrice` | Decimal `String` | `BigDecimal` | Can break consumers using old casts |
| `lineTotal` | Absent | Added after processor | Compatible if old writer ignores new fields |
| `currency` | Absent | Added as required field | Breaks old producers without a default/migration |
| `orderId` renamed to `order_id` | Old name | New name | Breaks old consumers |

A safe schema upgrade workflow should include:

1. Document v1/v2 schemas clearly specifying keys, types, nullability, and semantics.
2. Add an adapter converting v1 → v2 at the read boundary, or support both versions in parallel during migration.
3. Use `schemaVersion` and validate before processing.
4. Test readers from every source and writers for every destination against sample datasets of both versions.
5. Remove v1 support only after producers/consumers have been upgraded on schedule.

Do not treat `Map<String, Object>` as a stable storage format. When exporting to CSV, JSON, or JDBC, field ordering, SQL/JSON types, encoding, and serialization all require explicit specification.

## 12. Restarts and preserving consistency

In a finite task, Spring Cloud Task can store a `TaskExecution` per launch; Spring Batch stores `JobExecution`, `StepExecution`, and `ExecutionContext` to track state and restarts. These are **two distinct metadata layers**.

If the writer already wrote some items when the process crashes, the outcome depends on:

- Whether the chunk had committed yet.
- How the writer and Batch repository participate in transactions.
- Whether the target is a database, file, broker, or external API.
- Whether the reader supports saving restart state.
- Whether the writer is idempotent when receiving the same item again.

| Write destination | Risk after crash | Mitigation |
| --- | --- | --- |
| JDBC in same transaction | Current chunk rolls back; earlier chunks already committed | Proper transactions, unique keys, controlled restarts |
| CSV/file | File may be partially written or overwritten | Temp files, proper checkpoints, atomic publish where possible |
| Message broker | Messages may be redelivered after crash | Message IDs and idempotent consumers |
| External API | Timeout does not prove the API failed to process | Idempotency keys and state reconciliation |
| Console | Output may print duplicates | Use for demonstration or logging only |

Using a Map does not automatically enable restartability. Batch metadata can store reader/writer state, yet **item Maps are not automatically persisted in full inside `ExecutionContext`**. Each component must configure appropriate state-saving behavior.

If an error occurs in the reader/processor/writer, `BatchStatus` may become `FAILED`. For a scheduler to observe the proper Spring Cloud Task exit code, configure Batch failure → Task exit code mapping supported by your version, such as `spring.cloud.task.batch.fail-on-job-failure=true` when available. Always verify actual exit codes and metadata; do not infer them from a few log lines.

## 13. Layered compatibility testing

A meaningful test suite should verify across layers:

### 13.1. Compile-time generics

- Reader declares `ItemReader<Map<String, Object>>`.
- Processor declares `ItemProcessor<Map<String, Object>, Map<String, Object>>`.
- Writer declares `ItemWriter<Map<String, Object>>`.
- No raw generics, arbitrary casts, or `Map<String, String>` workarounds bypassing the contract.

### 13.2. Runtime item schema

Test representative items:

~~~text
VALID:    orderId="ORD-1001", quantity="2", unitPrice="19.90"
INVALID:  orderId=null,       quantity="2", unitPrice="19.90"
INVALID:  orderId="ORD-1002", quantity="-5", unitPrice="19.90"
INVALID:  orderId="ORD-1003", quantity="2", unitPrice="unknown"
~~~

Verify the processor returns the expected output types and clear error messages rather than trying to "fix" dirty data with silent defaults.

### 13.3. Destination and restart

- For JDBC writers, check SQL schemas, `NUMERIC/DECIMAL` types, unique constraints, and transactions.
- For CSV writers, check encoding, field order, decimal formatting, headers, and quoting.
- For JSON writers, check serializer/consumer behavior, numeric types, and handling of extra fields.
- Trigger a failure after one chunk commits and restart; verify no records are lost or duplicated.
- Reconcile `JobExecution`/`StepExecution` with `TaskExecution` and business outcomes.

## 14. Checklist for wiring Reader, Processor, and Writer

- [ ] One item corresponds to exactly one business unit, not confused with the entire Job.
- [ ] Reader output generic matches processor input; processor output matches writer input.
- [ ] The Map contract explicitly defines key names, value types, units, nullability, and valid ranges.
- [ ] Readers normalize field names from CSV/JDBC/JSON to a single convention.
- [ ] The processor validates data and returns a consistent output Map without blind casts.
- [ ] The writer knows the exact keys and types it expects; tested against missing, duplicate, and cross-version data.
- [ ] `BigDecimal` is used for monetary math, with currency and rounding rules defined.
- [ ] Sensitive data is not dumped into logs, `TaskExecution`, or `ExecutionContext` indiscriminately.
- [ ] Failure restarts are designed safely with transactions, business keys, and retry mechanisms.
- [ ] Spring Cloud Task, Spring Batch, starter versions, and auto-configuration properties have been verified.

## 15. Exercises and self-check questions

**Question 1.** Why cannot `Map<String, String>` be passed directly where `Map<String, Object>` is required, even though every `String` is an `Object`?

**Question 2.** A CSV reader produces `quantity="2"`, while a JDBC reader produces `quantity=2`. Since both are `Map<String, Object>`, why can the writer still fail?

**Question 3.** What is the difference between `ItemProcessor.process()` returning `null` and `ItemReader.read()` returning `null`?

**Question 4.** Spring Batch's `ExecutionContext` uses a Map-like structure, but is it the same as the item Map? Should you store an entire list of 1 million items in `ExecutionContext`?

**Question 5.** With the Single Step Batch Job Starter, is an `ItemProcessor<Map<String, Object>, OrderDto>` bean compatible with the built-in Map writers? If not, how can this be resolved?

**Exercise A — Multi-source normalization.** Update the processor to accept `quantity` as either `String` or `Integer`, and `unitPrice` as either `String` or `BigDecimal`. Allow only these types; reject `Double` or collections.

**Exercise B — Versioning.** Add `schemaVersion` and `currency` to items. For v1 records missing `currency`, apply a conditional compatibility policy; for v2, require `currency`. Explain why defaulting every record to a single currency is risky.

**Exercise C — Persistent writer.** Replace the console writer with a JDBC writer backed by a unique `order_id` key on the target table. Run the Job twice and inspect duplicates, transactions, `JobExecution`, and `TaskExecution`.

**Exercise D — Swapping data sources.** Switch from `ListItemReader` to `FlatFileItemReader` and then to `JdbcCursorItemReader`. Preserve the normalized output contract and write tests confirming the writer still receives the expected types.

**Exercise E — Starter compatibility.** If a project uses `spring-cloud-starter-single-step-batch-job`, verify the artifact version, `jobName`/`stepName`/`chunkSize` properties, processor generics, and reader/writer creation conditions. Compare against a manually declared Job/Step.

## 16. Takeaways

- Spring Cloud Task's Single Step Batch Job Starter specifies **input/output items as `Map<String, Object>`** and only auto-wires a processor with matching generics per the documented mechanism.
- Java type compatibility **is not enough**: reader, processor, and writer must also agree on **key names, runtime types, nullability, business semantics, and schema versions**.
- `Map<String, String>` is **not** `Map<String, Object>`; avoid raw types and casts that bypass type checking.
- When readers emit raw data from CSV/JDBC/JSON, normalize at the boundary or in the processor. Writers should receive only a validated contract.
- Item Maps, `JobParameters`, `ExecutionContext`, and `TaskExecution` have distinct responsibilities. An item Map **is not checkpoint state** and is not Task metadata.
- For safe scheduled or on-demand execution, persist business results, enforce validation, design idempotency/restarts, and reconcile both Spring Batch and Spring Cloud Task.

## References

- [Spring Cloud Task Reference — Single Step Batch Job Starter](https://docs.spring.io/spring-cloud-task/reference/batch-starter.html), sections *Defining a Job*, *ItemProcessor Configuration*, and Map readers/writers.
- [Spring Batch Reference — Configuring a Step](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring.html), wiring reader, processor, and writer in a Step.
- [Spring Batch Reference — Domain Language of Batch](https://docs.spring.io/spring-batch/reference/domain.html), `JobParameters`, `StepExecution`, `ExecutionContext`, and restart rules.
- [Spring Batch Reference — TaskletStep](https://docs.spring.io/spring-batch/reference/step/tasklet.html), for comparison when a Step is not chunk-oriented.
- [Spring Batch 5 API — ExecutionContext](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/item/ExecutionContext.html), map-backed context and serialization requirements.

When applying this to a concrete project, check the Spring Cloud Task/Single Step Starter and Spring Batch versions, as the starter examples in the documentation may target an older release line than newer Spring Batch APIs.
