# LineCallbackHandler

In Spring Batch, `LineCallbackHandler` is a callback used by `FlatFileItemReader` to handle lines configured to be skipped at the beginning of a file. The most common case is a CSV file with one or more header lines containing column names, version information, or export metadata. The reader does not convert these lines into items, yet the application may still need to read them for logging, format validation, or preparing metadata for the mapping step.

`LineCallbackHandler` receives a line's content as a `String` and performs a side action. It does not return an item, does not replace `LineMapper`, and is not the exception-skipping mechanism of chunk processing. In `FlatFileItemReader`, the callback is registered alongside `linesToSkip` to process each skipped initial line.

## 1. What problem does LineCallbackHandler solve?

An input file may contain a header before the data section:

```text
orderId,customerId,amount,currency
1001,C001,250000,VND
1002,C002,175000,VND
1003,C003,99000,VND
```

If the reader uses `LineMapper` to parse each line into an `OrderInput`, the first line is not an order. You can configure the reader to skip the first line and invoke a callback to record the header.

```text
FlatFileItemReader opens file
          |
          v
Read the number of lines configured in linesToSkip
          |
          +--> Invoke LineCallbackHandler for each skipped line
          |
          v
Read remaining data lines
          |
          v
LineMapper.mapLine(...)
          |
          v
OrderInput
```

This keeps the header out of the regular item pipeline. The callback lets the application inspect or extract information from the header before the reader begins returning data items.

## 2. The LineCallbackHandler interface

The interface lives in the `org.springframework.batch.item.file` package and has a single method:

```java
package org.springframework.batch.item.file;

@FunctionalInterface
public interface LineCallbackHandler {
    void handleLine(String line);
}
```

The `handleLine` method receives the content of the skipped line. It does not receive `StepExecution`, line number, or `ExecutionContext`; if those are needed, the callback can use an injected collaborator or Step-scoped state.

Because the interface has a single method, it can be implemented via a separate class, a method reference, or a lambda:

```java
LineCallbackHandler callback = line ->
        log.info("Skipped header line: {}", line);
```

The callback is suited for small, synchronous, fast operations such as logging, validating headers, or storing metadata in a Step-scoped object. Do not perform long-running work, call external systems, or write non-idempotent business records inside this callback.

## 3. Configuring with FlatFileItemReaderBuilder

In Spring Batch 5, `FlatFileItemReaderBuilder` provides two related settings:

- `linesToSkip(int)`: the number of lines at the beginning of the file to skip.
- `skippedLinesCallback(LineCallbackHandler)`: callback invoked for each skipped line.

Example reader skipping a single header line:

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['input.file']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .linesToSkip(1)
            .skippedLinesCallback(line ->
                    log.info("Input header: {}", line))
            .delimited()
            .names("orderId", "customerId", "amount", "currency")
            .targetType(OrderInput.class)
            .saveState(true)
            .build();
}
```

In this example:

- The reader opens the file passed through the `input.file` JobParameter.
- The first line is skipped due to `linesToSkip(1)`.
- `skippedLinesCallback` receives the raw header line for logging.
- Remaining lines are converted into `OrderInput` by the tokenizer and mapper.
- `saveState(true)` lets the reader store reading state to support restart.

If `skippedLinesCallback` is not configured, the specified initial lines are still skipped; the application simply receives no callback to inspect them.

## 4. Skipping multiple header lines

Some files contain multiple metadata lines before the column header line:

```text
Exported by: Order Management System
Export version: 3
Business date: 2026-11-15
orderId,customerId,amount,currency
1001,C001,250000,VND
1002,C002,175000,VND
```

You can skip the first four lines and handle each one via the callback:

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['input.file']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .linesToSkip(4)
            .skippedLinesCallback(line ->
                    log.debug("Skipped file metadata: {}", line))
            .delimited()
            .names("orderId", "customerId", "amount", "currency")
            .targetType(OrderInput.class)
            .build();
}
```

`linesToSkip` is the number of lines skipped at the start of the resource. The callback is invoked once per line in that group when the reader opens the resource. If the header line count varies across file formats, determine how to detect headers before configuring the reader; avoid hardcoding a fixed count when files lack a stable format contract.

## 5. Using the callback to capture headers

Beyond logging, the callback can extract metadata from headers. For example, an export file contains a line with business date and tenant ID:

```text
# businessDate=2026-11-15;tenantId=42
orderId,customerId,amount
1001,C001,250000
```

You can use a collaborator that holds metadata at Step scope:

```java
public class InputFileMetadata {

    private LocalDate businessDate;
    private Long tenantId;

    public void capture(String line) {
        if (!line.startsWith("#")) {
            return;
        }

        for (String token : line.substring(1).split(";")) {
            String[] pair = token.split("=", 2);
            if (pair.length != 2) {
                throw new IllegalArgumentException(
                        "Invalid metadata header: " + line);
            }

            switch (pair[0].trim()) {
                case "businessDate" ->
                        businessDate = LocalDate.parse(pair[1].trim());
                case "tenantId" ->
                        tenantId = Long.valueOf(pair[1].trim());
                default -> throw new IllegalArgumentException(
                        "Unknown header field: " + pair[0]);
            }
        }
    }

    public LocalDate getBusinessDate() {
        return businessDate;
    }

    public Long getTenantId() {
        return tenantId;
    }
}
```

Register the object as Step-scoped and pass a method reference to the callback:

```java
@Bean
@StepScope
InputFileMetadata inputFileMetadata() {
    return new InputFileMetadata();
}

@Bean
@StepScope
FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['input.file']}") String inputFile,
        InputFileMetadata metadata) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .linesToSkip(2)
            .skippedLinesCallback(metadata::capture)
            .delimited()
            .names("orderId", "customerId", "amount")
            .targetType(OrderInput.class)
            .saveState(true)
            .build();
}
```

Here, `InputFileMetadata` exists only for the corresponding `StepExecution`. Another component in the Step can inject the same `@StepScope` proxy bean to read the metadata captured during that reader open. If the data must be used after the Step ends or survive restarts, store the needed values in the Job/Step `ExecutionContext` or persistent storage; fields on an in-memory object are not checkpoints.

### Validating the header before processing items

If the header is part of the file contract, the callback should validate the format and reject invalid files as soon as the reader opens. Example:

```java
private void validateColumnHeader(String line) {
    List<String> columns = Arrays.stream(line.split(",", -1))
            .map(String::trim)
            .toList();

    List<String> expected = List.of(
            "orderId", "customerId", "amount", "currency");

    if (!columns.equals(expected)) {
        throw new IllegalArgumentException(
                "Unexpected CSV columns: " + line);
    }
}
```

If the callback throws a runtime exception, opening the reader can fail and the Step will not proceed to read items. This is a file contract/format error during reader initialization, not an item that was read and skipped. Produce a clear failure message so operators can identify the offending file and header.

## 6. Callback does not replace LineMapper

`LineCallbackHandler` and `LineMapper` both work with text lines, but they serve different roles:

| Component | When used | Input | Result |
|---|---|---|---|
| `LineCallbackHandler` | For initial lines configured to be skipped | A `String` | `void`; can log or store metadata. |
| `LineMapper<T>` | For data lines the reader actually turns into items | Text line and line number | Returns an object `T`. |
| `FieldSetMapper<T>` | Inside mapping when using tokenization | Tokenized `FieldSet` | Returns an object `T`. |
| `ItemReadListener<T>` | Around item read operations | Item or exception | Read lifecycle observation callback. |

Example `LineMapper` processing data lines:

```java
public class OrderLineMapper implements LineMapper<OrderInput> {

    @Override
    public OrderInput mapLine(String line, int lineNumber) {
        String[] fields = line.split(",", -1);
        if (fields.length != 3) {
            throw new IllegalArgumentException(
                    "Invalid order row at line " + lineNumber);
        }

        return new OrderInput(
                fields[0].trim(),
                fields[1].trim(),
                new BigDecimal(fields[2].trim()));
    }
}
```

`LineMapper` processes each data line to construct an item. The header callback does not create an `OrderInput`, does not alter subsequent lines, and does not participate in regular record mapping.

## 7. Callback is not SkipListener

The name “skipped line” is easily confused with fault-tolerant skipping. These two concepts are different:

- `LineCallbackHandler` handles lines at the beginning of a file that the application intentionally skips via `linesToSkip`.
- `SkipListener` is invoked when an item is skipped due to an exception permitted by the chunk Step's skip policy.

Examples:

| Situation | Mechanism |
|---|---|
| Skipping column-name line at start of CSV | `linesToSkip` + `LineCallbackHandler`. |
| Skipping export metadata line at start of file | `linesToSkip` + `LineCallbackHandler`. |
| Data line 50 fails to parse and is skippable | `.skip(...)` + `SkipListener.onSkipInRead(...)` if the reader throws the matching exception. |
| Processor throws `InvalidOrderException` and item is skipped | `SkipListener.onSkipInProcess(...)`. |
| Writer fails to write an item and item is skipped | `SkipListener.onSkipInWrite(...)`. |

`LineCallbackHandler` does not consume `skipLimit`, does not increment `readSkipCount`, and does not represent an item error. Header lines skipped by configuration are not items skipped due to exceptions.

## 8. Callback does not replace ItemReadListener

`ItemReadListener` observes the item reading lifecycle—before reading, after a successful read, or when the reader throws an exception. `LineCallbackHandler` only handles initial lines configured to be skipped.

| Callback | Purpose |
|---|---|
| `LineCallbackHandler.handleLine(line)` | Read/inspect a skipped header line. |
| `ItemReadListener.beforeRead()` | Observe before reading an item. |
| `ItemReadListener.afterRead(item)` | Observe an item read successfully. |
| `ItemReadListener.onReadError(exception)` | Observe an error during an item read. |

If you need metrics on items read, use `ItemReadListener` or `StepExecution` counters. Do not use the header callback to count data records.

## 9. When is the callback invoked?

In the `FlatFileItemReader` lifecycle, the reader opens the resource and then processes the configured number of initial lines to skip. For each line in that group, if a callback is registered, `handleLine` is invoked. Only after that does the reader proceed to read the remaining records through `LineMapper`.

Points to keep in mind:

- `linesToSkip(0)` is the default when unconfigured; no header lines are passed to the callback.
- `linesToSkip(1)` skips the first line; `linesToSkip(3)` skips the first three lines.
- The callback is only called if a callback is configured and the reader actually reads those lines.
- If the resource does not exist and the reader is in strict mode, the reader fails on open; the callback cannot process unreadable lines.
- The callback receives the line text, not the line number or resource path.
- The callback runs while opening the reader, before the reader returns data items.

If you need to track the index of header lines, use a counter inside a Step-scoped collaborator and increment it in each callback invocation. If you need the file name when using multiple resources, pass resource info through an appropriate collaborator or reader wrapper; the callback only receives the line string and does not provide the file name itself.

## 10. Restart and callback idempotency

`FlatFileItemReader` is a stateful reader. When a Step restarts, the reader reopens the resource, restores its checkpoint, and resumes from the saved position. Lines configured in `linesToSkip` are processed during the reader open phase; consequently, the header callback can be invoked again when the reader reopens during a restart or whenever the resource is reopened.

This has an important consequence: do not treat the callback as an event that “runs only once per JobInstance.” Design the callback so it can be invoked multiple times without creating duplicate side effects.

Generally safe actions:

- Logging with `JobExecution`/`StepExecution` context.
- Parsing headers into a fresh Step-scoped object for that reader open.
- Validating file version and rejecting invalid headers.
- Recording file format metrics if the metrics tolerate repeated callbacks.

Actions requiring caution:

- Sending an email or message every time the callback runs.
- Creating a new business record without a unique key.
- Incrementing an external counter without deduplication.
- Moving or deleting the input file inside the callback.

If header metadata must be persisted durably, use a stable key tied to `JobInstance`/Step and perform an upsert or existence check. If header values must be shared with a later Step, place them into `ExecutionContext` via an appropriate listener or coordinator instead of relying on an in-memory object after its scope ends.

## 11. Multiple files with MultiResourceItemReader

When using `MultiResourceItemReader` to read multiple files, the delegate reader is typically opened for each resource. If the delegate is a `FlatFileItemReader` with `linesToSkip` and `skippedLinesCallback`, the header callback can run for every file opened.

Conceptual configuration example:

```java
@Bean
@StepScope
MultiResourceItemReader<OrderInput> multiFileReader(
        @Value("#{jobParameters['input.pattern']}") Resource[] resources,
        FlatFileItemReader<OrderInput> orderFileDelegate) {

    return new MultiResourceItemReaderBuilder<OrderInput>()
            .name("multiFileReader")
            .resources(resources)
            .delegate(orderFileDelegate)
            .saveState(true)
            .build();
}
```

With multiple files, each file may have its own header or different format details. If the callback only logs, include the file name context at an appropriate layer. If the callback extracts metadata, decide which metadata applies per file and which applies job-wide.

Do not assume the first file's header represents every file. You may need to validate schema/version for each resource before processing that file's items.

## 12. Handling invalid header lines

The callback can validate:

- Column count.
- Column names and column order.
- Encoding or BOM markers if the source system defines a convention.
- File format version.
- Business date or tenant ID in metadata.
- Whether the file matches the given `JobParameters`.

Example validating column headers:

```java
private static final List<String> EXPECTED_COLUMNS = List.of(
        "orderId", "customerId", "amount");

private void validateHeader(String line) {
    List<String> actual = Arrays.stream(line.split(",", -1))
            .map(String::trim)
            .toList();

    if (!EXPECTED_COLUMNS.equals(actual)) {
        throw new IllegalArgumentException(
                "Unsupported input header: " + line);
    }
}
```

If a UTF-8 file begins with a BOM, the BOM character may appear before the first column name depending on how the reader/encoding handles it. In that situation, normalize the BOM deliberately before comparing headers. Do not strip arbitrary control characters or blindly trim data, as that can mask format errors.

If a header is invalid, it is usually best to fail the Step/Job early rather than treating the header as a skippable item. The header defines how the entire file is interpreted; ignoring a bad header can cause every subsequent record to be parsed under the wrong schema.

## 13. Encoding and line content

`LineCallbackHandler` receives strings already read and decoded using the configured encoding. If the file uses UTF-8, configure the encoding explicitly to avoid misreading accented column names or metadata:

```java
return new FlatFileItemReaderBuilder<OrderInput>()
        .name("orderReader")
        .resource(new FileSystemResource(inputFile))
        .encoding(StandardCharsets.UTF_8.name())
        .linesToSkip(1)
        .skippedLinesCallback(this::validateHeader)
        .delimited()
        .names("orderId", "customerId", "amount")
        .targetType(OrderInput.class)
        .build();
```

The encoding must match the source file. If the actual file is Windows-1258, UTF-16, or another encoding, configuring UTF-8 can produce garbled characters and cause header validation callbacks to fail.

The callback receives line text, not raw bytes. If you need to verify a byte-level signature or whole-file checksum, perform that in a resource check step before opening the reader.

## 14. XML configuration

In XML configuration, `FlatFileItemReader` can accept `linesToSkip` and a `LineCallbackHandler` bean via properties:

```xml
<bean id="headerCallback"
      class="com.example.batch.HeaderLineCallback"/>

<bean id="orderReader"
      class="org.springframework.batch.item.file.FlatFileItemReader">
    <property name="resource" value="file:/data/orders.csv"/>
    <property name="linesToSkip" value="1"/>
    <property name="skippedLinesCallback" ref="headerCallback"/>
    <property name="lineMapper" ref="orderLineMapper"/>
</bean>
```

Callback class:

```java
public class HeaderLineCallback implements LineCallbackHandler {

    @Override
    public void handleLine(String line) {
        if (!line.equals("orderId,customerId,amount")) {
            throw new IllegalArgumentException("Unexpected header: " + line);
        }
    }
}
```

The XML example illustrates property wiring. In real applications, resources are usually injected via placeholders/configuration or `JobParameters` using an appropriate scope; avoid hardcoding environment-specific paths in deployment configs.

## 15. Testing LineCallbackHandler

You can test the reader in isolation with a small in-memory resource. The test should confirm the callback receives the exact header line and the reader returns only data lines.

```java
@Test
void callbackReceivesSkippedHeaderAndReaderReturnsDataLines() throws Exception {
    List<String> headers = new ArrayList<>();

    String content = "orderId,amount\n1001,250000\n1002,175000\n";
    Resource resource = new ByteArrayResource(
            content.getBytes(StandardCharsets.UTF_8));

    FlatFileItemReader<String> reader =
            new FlatFileItemReaderBuilder<String>()
                    .name("testReader")
                    .resource(resource)
                    .linesToSkip(1)
                    .skippedLinesCallback(headers::add)
                    .lineMapper((line, lineNumber) -> line)
                    .build();

    reader.open(new ExecutionContext());
    try {
        assertThat(reader.read()).isEqualTo("1001,250000");
        assertThat(reader.read()).isEqualTo("1002,175000");
        assertThat(reader.read()).isNull();
    } finally {
        reader.close();
    }

    assertThat(headers).containsExactly("orderId,amount");
}
```

Main imports include `FlatFileItemReader`, `FlatFileItemReaderBuilder`, `LineCallbackHandler`, `ExecutionContext`, `ByteArrayResource`, `Resource`, `StandardCharsets`, and test library assertions. Depending on version and how the reader is instantiated, you may need to call `afterPropertiesSet()` before `open()` when configuring the reader manually outside a Spring container.

### Cases to test

- `linesToSkip(0)`: the callback is not called.
- `linesToSkip(1)`: the callback receives the first line.
- `linesToSkip(2)`: the callback receives the first two lines in order.
- Malformed header: the callback throws an error and the reader stops before returning items.
- Empty resource or missing header line: confirm behavior per reader strict/resource policy.
- Restart/reopen: the callback may run again; verify no duplicate side effects occur.
- Multi-resource: confirm the callback runs for each file and metadata is not mixed.
- Encoding: accented headers or BOMs are handled properly per source format.

## 16. Common mistakes

### Configuring a callback but forgetting linesToSkip

The callback only runs for lines the reader is configured to skip. If `linesToSkip` is 0, the callback never receives the header. Configure the line count matching the file contract.

### Thinking the callback handles every faulty line

The callback does not handle data lines that fail parsing mid-file. Use `LineMapper`, exception classification, and skip policies for those cases.

### Using the callback to emit items

`handleLine` returns `void`. If a header needs to become an item or separate input data, use a dedicated reader/Tasklet or store metadata in an appropriate collaborator.

### Confusing it with SkipListener

Headers skipped by configuration do not consume the skip limit. `SkipListener` handles items skipped due to exceptions under fault tolerance.

### Triggering side effects inside the callback

The callback may execute again when the reader reopens after a restart. Do not send emails, publish messages, or insert non-idempotent business records inside the callback.

### Storing metadata only in a singleton field

Multiple Steps or Jobs may share a singleton, mixing headers across executions. Use a `@StepScope` collaborator or save values needed for restart into `ExecutionContext`.

### Assuming the callback executes exactly once

The reader may reopen on restart; the header callback may run again. Design the callback to be idempotent.

### Deleting or moving the file inside the callback

The reader still needs the file to read the remaining data. Manage file lifecycle only in an appropriate step after the resource is no longer in use.

### Ignoring invalid headers

The header defines the schema for the whole file. If a header is invalid, fail early rather than continuing to parse with the wrong mapping.

## 17. Workflow for using LineCallbackHandler

When processing files with headers or leading metadata, follow this sequence:

1. Determine the exact number of leading lines to skip.
2. Decide whether the callback should log, validate, or extract metadata.
3. Configure encoding and `linesToSkip` on `FlatFileItemReader`.
4. Register the callback via `.skippedLinesCallback(...)`.
5. Use `@StepScope` for collaborators holding per-execution state.
6. Use `LineMapper`/`FieldSetMapper` to convert remaining data lines into items.
7. Fail early if the header violates the format contract.
8. Keep the callback fast, synchronous, and free of non-repeatable side effects.
9. Verify the callback can safely run again on reader reopen/restart.
10. If metadata is needed across Steps or restarts, persist it in `ExecutionContext` or durable storage.
11. Test multi-line headers, empty files, encoding, restart, and multiple resources.

| Need | Suitable mechanism |
|---|---|
| Skip a single column-name line | `linesToSkip(1)` |
| Log skipped header lines | `skippedLinesCallback(line -> ...)` |
| Validate column names/order | `LineCallbackHandler` |
| Store header metadata per Step | Callback + `@StepScope` collaborator |
| Convert data lines into objects | `LineMapper`/`FieldSetMapper` |
| Handle malformed data lines mid-file | Exception policy and `SkipListener` if skippable |
| Observe item read success/failure | `ItemReadListener` |

## Conclusion

`LineCallbackHandler` is a `FlatFileItemReader` callback for handling each leading line skipped via `linesToSkip`. It is suited for logging, validating headers, or extracting metadata before data lines are passed to `LineMapper`. The callback receives a string and returns `void`; it does not produce items, replace `ItemReadListener`, or act as a fault-tolerant `SkipListener`. Use an appropriate scope for Step-level state, keep the callback fast and idempotent since it can run again when the reader reopens on restart, and persist any metadata needed for recovery in `ExecutionContext` or durable storage.
