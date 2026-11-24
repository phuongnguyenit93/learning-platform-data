# FlatFileItemReader

`FlatFileItemReader<T>` is a Spring Batch reader used to read data from a text file record by record and convert each record into a Java object. It is commonly used for CSV, tab- or semicolon-delimited files, and fixed-width files where fields are located at fixed positions.

The reader is responsible for managing the resource, reading records, handling headers/comments, passing lines through a `LineMapper`, and saving checkpoints to support restart. Validating business rules for each record usually belongs in `ItemProcessor`; the reader should focus on reading and mapping the file format deterministically.

## 1. Position of FlatFileItemReader in chunk processing

In a chunk-oriented step, Spring Batch calls the reader repeatedly to obtain items. The reader returns one object per read call; when data is exhausted, `read()` returns `null`. Items are passed through the processor and then sent as a chunk to the writer.

```text
Input file
    |
    v
FlatFileItemReader
    |
    +--> read logical record
    |
    +--> LineMapper
             |
             +--> LineTokenizer
             |       split fields
             |
             +--> FieldSetMapper
                     map fields to object
    |
    v
ItemProcessor
    |
    v
ItemWriter
    |
    v
Chunk transaction commit
```

`FlatFileItemReader` implements `ItemStreamReader`, so in addition to `read()` it also participates in the `open()`, `update()`, and `close()` lifecycle. These callbacks allow the reader to open the file, save reading state into `ExecutionContext`, and release resources.

## 2. Basic configuration in Spring Batch 5

The reader is typically created using `FlatFileItemReaderBuilder`. A basic configuration requires the reader name, the input resource, and how each line is mapped.

```java
@Bean
@StepScope
FlatFileItemReader<Customer> customerReader(
        @Value("#{jobParameters['input.file']}") String inputFile,
        LineMapper<Customer> customerLineMapper) {

    return new FlatFileItemReaderBuilder<Customer>()
        .name("customerReader")
        .resource(new FileSystemResource(inputFile))
        .encoding(StandardCharsets.UTF_8.name())
        .linesToSkip(1)
        .skippedLinesCallback(line ->
            log.debug("Skipped header: {}", line))
        .lineMapper(customerLineMapper)
        .strict(true)
        .saveState(true)
        .build();
}
```

In this example:

- `name` is the stable identifier of the reader, used when storing state in `ExecutionContext`.
- `resource` specifies the file to read.
- `encoding` explicitly defines the charset, avoiding dependence on the host machine's default encoding.
- `linesToSkip(1)` skips the first line, typically the header.
- `skippedLinesCallback` receives skipped lines at the beginning of the file so they can be logged or used to validate the header.
- `lineMapper` converts each record into a `Customer`.
- `strict(true)` requires the resource to exist; strict configuration should be chosen deliberately.
- `saveState(true)` enables the reader to save state for restart.

`@StepScope` allows resolving `input.file` from `JobParameters` at the time the step runs. Each `StepExecution` can receive its own file without creating a singleton reader holding a mutable path.

## 3. Input resources

`FlatFileItemReader` accepts a Spring `Resource`. Depending on the implementation, the resource can be a file on the filesystem, a file on the classpath, or a resource provided by the application.

| Resource | Example | When appropriate |
|---|---|---|
| `FileSystemResource` | `new FileSystemResource("/data/orders.csv")` | File on local machine or mounted volume |
| `ClassPathResource` | `new ClassPathResource("samples/orders.csv")` | Sample file or data packaged inside the application |
| `UrlResource` | `new UrlResource(uri)` | URL source readable as a resource; consider network/restart implications |

Example using a classpath resource:

```java
@Bean
FlatFileItemReader<Country> countryReader() {
    return new FlatFileItemReaderBuilder<Country>()
        .name("countryReader")
        .resource(new ClassPathResource("data/countries.csv"))
        .encoding(StandardCharsets.UTF_8.name())
        .linesToSkip(1)
        .lineMapper(countryLineMapper())
        .build();
}
```

In production, the input file is usually passed via `JobParameters` so the same job can process multiple files. Use a stable source identifier such as a file ID, batch ID, or checksum if the file contents could be replaced at the same path.

## 4. LineMapper: converting a record into an object

`LineMapper<T>` receives the contents of a logical record and the line number, then returns an object of type `T`. `DefaultLineMapper<T>` combines two components:

1. `LineTokenizer`: splits the record into fields.
2. `FieldSetMapper<T>`: maps the field set into a Java object.

```text
"C001","An Nguyen","an@example.test"
                  |
                  v
          DelimitedLineTokenizer
                  |
                  v
       FieldSet: customerId, name, email
                  |
                  v
          FieldSetMapper<Customer>
                  |
                  v
          Customer object
```

Example configuring `DefaultLineMapper`:

```java
@Bean
LineMapper<Customer> customerLineMapper() {
    DelimitedLineTokenizer tokenizer = new DelimitedLineTokenizer();
    tokenizer.setDelimiter(",");
    tokenizer.setQuoteCharacter('"');
    tokenizer.setNames("customerId", "name", "email");
    tokenizer.setStrict(true);

    DefaultLineMapper<Customer> mapper = new DefaultLineMapper<>();
    mapper.setLineTokenizer(tokenizer);
    mapper.setFieldSetMapper(fieldSet -> new Customer(
        fieldSet.readString("customerId"),
        fieldSet.readString("name"),
        fieldSet.readString("email")
    ));
    return mapper;
}
```

The example assumes `Customer` is a record or class with a matching constructor. `FieldSet` provides methods to read values by name or position, such as `readString`, `readInt`, `readLong`, `readBigDecimal`, and date/time conversion methods.

## 5. DelimitedLineTokenizer for CSV and delimited files

`DelimitedLineTokenizer` splits a record by a delimiter. Common delimiters include comma, semicolon, tab, or pipe characters.

```java
DelimitedLineTokenizer tokenizer = new DelimitedLineTokenizer();
tokenizer.setDelimiter(";");
tokenizer.setQuoteCharacter('"');
tokenizer.setNames("orderId", "customerId", "amount", "currency");
tokenizer.setStrict(true);
```

With the line:

```text
1001;C008;125000.50;VND
```

`FieldSet` can read fields by name:

```java
FieldSetMapper<Order> orderMapper = fieldSet -> new Order(
    fieldSet.readLong("orderId"),
    fieldSet.readString("customerId"),
    fieldSet.readBigDecimal("amount"),
    fieldSet.readString("currency")
);
```

The tokenizer can handle values enclosed in quotes as configured. This is important when a field contains the delimiter, such as `"Nguyen, An"` in CSV. Verify the quote/escape rules of the source file; a custom-built CSV file may not follow the same dialect as the tokenizer.

`strict(true)` requires the number of fields to match the number of declared names. If a file has a variable number of columns, explicitly decide whether missing or extra fields are allowed; do not disable strict mode merely to hide malformed data.

## 6. FixedLengthTokenizer for fixed-width files

Not all text files are separated by a delimiter. Some systems export files with a fixed width for each field. `FixedLengthTokenizer` uses `Range` instances to specify the character positions of each column.

For example, a record has:

- Customer ID at characters 1–8.
- Name at characters 9–38.
- Balance at characters 39–50.

```java
FixedLengthTokenizer tokenizer = new FixedLengthTokenizer();
tokenizer.setColumns(
    new Range(1, 8),
    new Range(9, 38),
    new Range(39, 50)
);
tokenizer.setNames("customerId", "customerName", "balance");
tokenizer.setStrict(true);

DefaultLineMapper<CustomerBalance> mapper = new DefaultLineMapper<>();
mapper.setLineTokenizer(tokenizer);
mapper.setFieldSetMapper(fieldSet -> new CustomerBalance(
    fieldSet.readString("customerId").trim(),
    fieldSet.readString("customerName").trim(),
    fieldSet.readBigDecimal("balance")
));
```

`Range` uses start/end character positions according to Spring Batch conventions. Confirm the record width and position calculation against the source file specification; fixed-width data may contain meaningful leading or trailing spaces in a field.

## 7. FieldSetMapper and data type conversion

`FieldSetMapper<T>` is responsible for converting tokenized fields into a domain object. You can use `BeanWrapperFieldSetMapper` when the class has a default constructor and matching setters, or write a custom mapper to control conversion.

Example of an explicit mapper:

```java
FieldSetMapper<Invoice> invoiceMapper = fieldSet -> new Invoice(
    fieldSet.readString("invoiceNumber"),
    LocalDate.parse(fieldSet.readString("invoiceDate")),
    fieldSet.readBigDecimal("totalAmount")
);
```

A custom mapper is useful when the file uses specific date formats, decimal separators, or enum codes. For example, if the source uses `dd/MM/yyyy` dates, parse with an explicit formatter rather than relying on the default locale:

```java
DateTimeFormatter dateFormat = DateTimeFormatter.ofPattern("dd/MM/uuuu");

FieldSetMapper<Invoice> invoiceMapper = fieldSet -> new Invoice(
    fieldSet.readString("invoiceNumber"),
    LocalDate.parse(fieldSet.readString("invoiceDate"), dateFormat),
    fieldSet.readBigDecimal("totalAmount")
);
```

Do not put too many business rules into the mapper. The mapper should convert the file representation into Java types; the processor can validate business relationships between fields, look up reference data, or decide whether to filter or transform.

## 8. Headers and initial lines of a file

Many files have one or more header lines before the data. `linesToSkip(n)` allows the reader to skip the first `n` physical lines.

```java
return new FlatFileItemReaderBuilder<Customer>()
    .name("customerReader")
    .resource(resource)
    .linesToSkip(2)
    .skippedLinesCallback(line -> log.debug("Header: {}", line))
    .lineMapper(customerLineMapper)
    .build();
```

`skippedLinesCallback` can be used to confirm the header matches the expected version or to log source metadata. If column names in the header need to be checked, the callback should compare the content against the expected schema and throw an error if the header is invalid.

`linesToSkip` skips a fixed number of initial lines. If a file has a variable header, multiple metadata lines, or a schema that changes by version, use a callback or a separate file validation step instead of assuming every file has the same number of lines.

## 9. Comments and non-data lines

`FlatFileItemReader` can skip comment lines based on configured prefixes. This is useful when a file contains annotation lines such as `# generated at ...`.

```java
return new FlatFileItemReaderBuilder<OrderRow>()
    .name("orderReader")
    .resource(resource)
    .comments("#", "//")
    .lineMapper(orderLineMapper)
    .build();
```

Only use a comment prefix if the file format specifies that lines starting with that character are not data. If a valid value in the first column can start with `#`, configuring it as a comment prefix could drop records. Blank lines must also be handled according to the file contract; do not assume every blank line is a comment or a valid item.

## 10. Encoding and special characters

Encoding defines how bytes in a file are converted into characters. If not specified, the application may rely on the JVM default charset or environment configuration, causing corruption in Vietnamese, accented characters, or multilingual data.

For UTF-8 files, configure it explicitly:

```java
.encoding(StandardCharsets.UTF_8.name())
```

If the source uses UTF-16 or a legacy code page, you must choose the exact charset specified by the source contract. The wrong encoding can produce garbled characters, corrupt delimiters, or cause mapping to fail.

You also need to determine whether the file has a UTF-8 BOM. A BOM at the start of the file may appear as a character in the first field depending on how it is read and processed. If the source includes a BOM, normalize it during controlled reading/preprocessing and test with actual files.

## 11. Multi-line records and RecordSeparatorPolicy

A logical record does not always correspond to a single physical line. CSV can allow a quoted field to contain newline characters. In that case, the reader needs to know when a record ends.

`RecordSeparatorPolicy` determines how physical lines are joined into a logical record. Spring Batch provides a default policy and allows configuring a custom policy if the file format has special rules.

```java
return new FlatFileItemReaderBuilder<CustomerNote>()
    .name("customerNoteReader")
    .resource(resource)
    .recordSeparatorPolicy(new DefaultRecordSeparatorPolicy())
    .lineMapper(customerNoteLineMapper)
    .build();
```

The tokenizer must be compatible with the record separator rules. For files with an opening quote on one line and a closing quote on a subsequent line, test multi-line records to ensure the tokenizer receives a complete logical record.

If the source uses a continuation marker or has a special record structure, a custom `RecordSeparatorPolicy` may be needed. Do not manually concatenate lines in the processor, because by the time the processor runs, the reader must have already produced a single item representing the record.

## 12. Handling parse errors and malformed data

When `LineMapper` or the tokenizer cannot map a record, the reader may throw `FlatFileParseException`. This exception provides useful information such as the line number and the offending record input.

In a fault-tolerant step, you can configure skip for parse errors if the business requirements allow it:

```java
return new StepBuilder("importCustomers", jobRepository)
    .<Customer, Customer>chunk(100, transactionManager)
    .reader(customerReader)
    .writer(customerWriter)
    .faultTolerant()
    .skip(FlatFileParseException.class)
    .skipLimit(100)
    .listener(customerSkipListener)
    .build();
```

Only skip parse errors when faulty items can be discarded without breaking business requirements. If the header is wrong, the encoding is wrong, or the entire file uses an incompatible schema, skipping line by line can mask a source-wide error; fail early instead.

For structured data errors where rejected records need to be recorded, use `SkipListener` to log the item or exception that was actually skipped. `onSkipInRead` has no Java item because the reader could not create the object; you can extract the line number and input from `FlatFileParseException` to store investigation details.

## 13. Strict mode and missing resources

The builder supports `strict(boolean)` to control how missing resources are handled. With strict mode enabled, a missing file is treated as a configuration/input error and the reader does not silently treat the source as empty.

```java
.resource(new FileSystemResource(inputFile))
.strict(true)
```

Set `strict(false)` only when a missing resource is a valid scenario according to business requirements and the job is designed to handle an empty source. For example, a partition might not have a corresponding file. However, if the file is mandatory, disabling strict mode makes operational failures harder to detect.

Do not use `strict(false)` to bypass file validation. Validate `JobParameters`, resource paths, and access permissions before starting processing.

## 14. Restart and ExecutionContext

`FlatFileItemReader` can store its reading position in `ExecutionContext` so a step can resume after a job failure. When a chunk commits, Spring Batch calls the `update()` lifecycle method so the reader saves its current state. On restart, the reader restores state in `open()` and resumes from the appropriate position.

```text
Initial execution
  read records 1..100
  write chunk and COMMIT
  reader checkpoint saved
  read records 101..200
  error before commit

Restart same JobInstance
  reader reopens file
  restore committed checkpoint
  resume from uncommitted record
```

For restart to work properly:

- Set a stable `.name("customerReader")` that is unique within the step.
- Keep `.saveState(true)` (the builder default typically enables state; configure it explicitly when restart is required).
- Use the same input file and the same identifying `JobParameters` when restarting the same `JobInstance`.
- Do not modify the file contents at the same path between the initial run and the restart.
- Ensure `ExecutionContext` and `JobRepository` are persisted durably.

If the file may be replaced, use a file ID/checksum/version as an identifying parameter and store an immutable snapshot or copy so restart reads the exact original data.

## 15. Name and saveState

`name` is not just a display label. The reader uses its name to construct keys for saving state in `ExecutionContext`. When there are multiple readers in a single step, each reader must have a distinct name to avoid overwriting checkpoints.

```java
new FlatFileItemReaderBuilder<OrderRow>()
    .name("ordersInputReader")
    .resource(resource)
    .lineMapper(orderLineMapper)
    .saveState(true)
    .build();
```

If `saveState(false)` is set, the reader does not save checkpoints. That may be suitable for a source that can be re-read from the start or a step that does not require restart, but a restart may re-read data from the beginning or fail to restore progress as expected.

Do not disable state just to work around duplicate key errors. Give readers stable, unique names. When using a reader in a parallel execution environment, remember that reader checkpointing and thread safety are two separate concerns.

## 16. Reader is not thread-safe

`FlatFileItemReader` maintains internal state such as the open reader, current read position, and line count. It is not designed for multiple threads to call `read()` concurrently on the same instance without proper synchronization.

Do not share a singleton `FlatFileItemReader` across multiple workers or multiple `JobExecution` instances. When using partitioning, declare the reader with `@StepScope` so each worker `StepExecution` receives its own reader target and its own file/record range.

```java
@Bean
@StepScope
FlatFileItemReader<OrderRow> partitionReader(
        @Value("#{stepExecutionContext['file']}") String file) {
    return new FlatFileItemReaderBuilder<OrderRow>()
        .name("partitionOrderReader")
        .resource(new FileSystemResource(file))
        .lineMapper(orderLineMapper())
        .saveState(true)
        .build();
}
```

For a step that needs to read multiple files sequentially, consider `MultiResourceItemReader`. For workloads requiring parallel processing, partition by file or by data range so each worker has its own reader. Do not treat `@StepScope` as a guarantee of thread safety if multiple threads still share the same `StepExecution` and target instance.

## 17. FlatFileItemReader and MultiResourceItemReader

`FlatFileItemReader` reads a single resource. If the input consists of a set of multiple files, `MultiResourceItemReader` can iterate through the resource list and use a delegate `FlatFileItemReader` to read each file.

```java
@Bean
@StepScope
MultiResourceItemReader<OrderRow> orderFilesReader(
        @Value("#{jobParameters['input.directory']}") String directory,
        FlatFileItemReader<OrderRow> orderFileReader) {

    Resource[] resources = new PathMatchingResourcePatternResolver()
        .getResources("file:" + directory + "/*.csv");
    Arrays.sort(resources, Comparator.comparing(Resource::getFilename));

    return new MultiResourceItemReaderBuilder<OrderRow>()
        .name("orderFilesReader")
        .resources(resources)
        .delegate(orderFileReader)
        .saveState(true)
        .build();
}
```

This example illustrates the concept; in real configurations, ensure the delegate reader has a scope/lifecycle compatible with the wrapper and does not create a delegate target shared improperly across executions. The resource list should be sorted deterministically so restart resumes at the right file.

`MultiResourceItemReader` manages file switching; each individual file is still read by the delegate. If there is only a single file, using `FlatFileItemReader` directly is simpler.

## 18. Header and file schema validation

`linesToSkip` only skips the header; it does not automatically verify that the header is correct. If a provider might change column names or order, validate the header before reading data.

Example callback validating the header:

```java
.linesToSkip(1)
.skippedLinesCallback(header -> {
    String expected = "customerId,name,email";
    if (!expected.equals(header)) {
        throw new IllegalStateException("Unexpected input header");
    }
})
```

If the file has a BOM, quotes, or whitespace normalization rules, the header comparison must account for those characteristics before matching. For complex or multi-version schemas, you can create a separate file inspection step to determine the version and configure the corresponding mapper.

## 19. Testing FlatFileItemReader

A reader should be tested with sample files representing both valid data and edge cases. Tests should verify not only the item count, but also field mapping and restart positioning.

Useful test cases:

1. Normal CSV file: each record is mapped to the right fields and data types.
2. Header: the exact number of lines is skipped and the callback receives the expected content.
3. Comments: lines with configured prefixes do not become items.
4. Fields containing delimiters inside quotes: values are preserved intact.
5. Fixed-width files: ranges and field mappings align to the exact positions.
6. Encoding: Vietnamese, accented characters, and non-ASCII characters are read correctly.
7. Multi-line records: the record separator assembles logical records properly.
8. Malformed data: exceptions contain sufficient line number/input details for investigation.
9. Missing resource: strict mode behaves according to requirements.
10. Restart: after a chunk commit, the reader resumes from the appropriate checkpoint.
11. Mutated source file: the job detects changes or the workflow ensures the snapshot is immutable.
12. Parallel execution: each worker has its own reader target and data range.

For restart tests, use a compatible `JobRepository` and transaction manager to confirm checkpoints are saved at commit boundaries. Simply calling `read()` in a loop inside a unit test does not prove restart metadata works.

## 20. Common pitfalls

| Pitfall | Consequence | Mitigation |
|---|---|---|
| Not setting a stable `name` | Checkpoints cannot be saved/restored reliably | Give each reader a unique name within the step |
| Using the default encoding | Vietnamese or multilingual characters become corrupted | Specify the charset explicitly per the file contract |
| Treating `linesToSkip` as header validation | Files with the wrong schema are still read | Use a callback or a header validation step |
| Using a tokenizer with the wrong delimiter or range | Fields are misaligned and data maps incorrectly | Verify the file dialect/widths and write tests |
| Disabling strict mode for required files | Missing files may be silently treated as empty sources | Keep strict enabled and validate resources |
| Skipping all parse errors | Files with the wrong schema may skip too many lines | Only skip record-level errors that can be safely discarded |
| Sharing a stateful reader across threads | Cursor/line count may become corrupted | Use a separate reader per `StepExecution` or partition |
| Replacing a file before restart | Old checkpoint is applied to new content | Use immutable inputs, checksums, or versions |
| Disabling `saveState` while expecting restart | Reader does not restore its checkpoint | Enable state and use a persistent `ExecutionContext` |
| Using a single-file reader for multiple resources | Does not coordinate switching between files | Use `MultiResourceItemReader` when needed |

## 21. Production reader design checklist

When building a file-reading step, determine:

1. Is the file CSV/delimited, fixed-width, or a multi-line structured record?
2. What charset, delimiter, quote, escape, comment prefix, and header does the contract define?
3. Is the resource required to exist?
4. What Java type does each record map to, and which parse errors are skippable?
5. Does the reader need `@StepScope` to receive `JobParameters` or partition context?
6. Does the reader save state and have a stable name for restart?
7. Is the source file immutable throughout the run and any restart?
8. Does the workload run in parallel; does each worker have its own reader?
9. Do skip/reject records capture sufficient audit details without exposing sensitive payloads?
10. Do integration tests verify headers, encoding, parse errors, and restart against a real `JobRepository`?

## Conclusion

`FlatFileItemReader<T>` reads a text resource by logical record and converts each record into a Java object. `LineMapper` combines `LineTokenizer` with `FieldSetMapper` to split fields and map data; `linesToSkip`, comment prefixes, encoding, and the record separator control how the reader interprets the file.

Declare the resource and encoding explicitly, use `@StepScope` when late binding is needed, assign a stable reader name, and enable `saveState` when restart is required. Validate headers/schemas rather than merely skipping headers, classify parse errors carefully, and never share a stateful reader across multiple threads. For multiple files, use `MultiResourceItemReader`; for business rules, let the processor handle validation and transformation.
