# LineMapper and FieldSetMapper

In Spring Batch, when reading a text file with FlatFileItemReader, each line is converted into an object for subsequent steps to process. LineMapper is responsible for mapping a line of text into an item. In the most common implementation, DefaultLineMapper coordinates two components: LineTokenizer splits the line into fields, and FieldSetMapper converts those fields into a Java object.

These two interfaces have distinct responsibilities:

- LineMapper<T> takes the full line along with the line number and returns an item of type T.
- FieldSetMapper<T> takes the FieldSet produced by the tokenizer and maps the fields into an object of type T.

The typical pipeline is:

FlatFileItemReader → LineMapper → LineTokenizer → FieldSet → FieldSetMapper → domain/input object.

Separating these responsibilities helps handle multiple file formats, control column names, convert data types, report line-level errors, and reuse mapping logic. When the boundaries of each component are well understood, you can pick a built-in tokenizer or write a custom mapper without building an entire reader from scratch.

## 1. Role in the file-reading pipeline

FlatFileItemReader reads a file line by line. For each data line, the reader calls LineMapper.mapLine(line, lineNumber). The mapper returns an object for the reader to place into the chunk.

Processing diagram:

~~~mermaid
flowchart TD
    A[FlatFileItemReader] --> B[Read a line]
    B --> C[LineMapper.mapLine]
    C --> D[LineTokenizer]
    D --> E[FieldSet]
    E --> F[FieldSetMapper.mapFieldSet]
    F --> G[Input object]
    G --> H[ItemProcessor]
    H --> I[ItemWriter]
~~~

Example CSV file:

~~~text
orderId,customerId,amount,orderDate
ORD-1001,CUS-01,125.50,2026-11-14
ORD-1002,CUS-02,89.90,2026-11-14
~~~

For the second data line, the tokenizer splits it into four fields. FieldSetMapper reads the fields by name and constructs an OrderInput. The processor can then perform business validation, transform into an entity, or filter the item; the writer is responsible for persisting the result.

Do not place all business logic inside LineMapper. Its job is to turn a text representation into structured data. Business decisions such as whether an order is eligible for import, whether a customer is active, or whether a credit limit is valid usually belong in the processor or a business service.

## 2. LineMapper<T>

LineMapper<T> is an interface that receives a line and its line number in the file:

~~~java
public interface LineMapper<T> {
    T mapLine(String line, int lineNumber) throws Exception;
}
~~~

The line number helps the mapper or an exception provide context when data is invalid. FlatFileItemReader uses the mapper to create an item from each line that the reader treats as data.

Spring Batch provides DefaultLineMapper<T> to combine a tokenizer with a field set mapper. When the line format is straightforward, this is usually the right choice. When a file has multiple record types, special parsing rules, or a structure unsuitable for built-in tokenizers, you can implement a custom LineMapper<T>.

Minimal custom mapper example:

~~~java
public class OrderLineMapper implements LineMapper<OrderInput> {

    @Override
    public OrderInput mapLine(String line, int lineNumber) {
        String[] parts = line.split(",", -1);
        if (parts.length != 4) {
            throw new IllegalArgumentException(
                    "Expected 4 columns at line " + lineNumber);
        }

        return new OrderInput(
                parts[0].trim(),
                parts[1].trim(),
                new BigDecimal(parts[2].trim()),
                LocalDate.parse(parts[3].trim()));
    }
}
~~~

This is just an example showing that the mapper receives the line number. A simple String.split is not a full CSV parser: it does not properly handle commas inside double quotes, quote escaping, or multiline fields. For real-world CSV, use DelimitedLineTokenizer or a parser with proper semantics instead of splitting strings manually.

## 3. DefaultLineMapper<T>

DefaultLineMapper<T> is the standard implementation that combines a LineTokenizer and a FieldSetMapper<T>. It performs two steps:

1. Call the tokenizer to convert the line into a FieldSet.
2. Call the field set mapper to convert the FieldSet into an object.

Configuration example:

~~~java
@Bean
LineMapper<OrderInput> orderLineMapper(
        LineTokenizer orderLineTokenizer,
        FieldSetMapper<OrderInput> orderFieldSetMapper) throws Exception {

    DefaultLineMapper<OrderInput> mapper = new DefaultLineMapper<>();
    mapper.setLineTokenizer(orderLineTokenizer);
    mapper.setFieldSetMapper(orderFieldSetMapper);
    mapper.afterPropertiesSet();
    return mapper;
}
~~~

afterPropertiesSet() verifies that the mapper's required dependencies have been configured. When declared as a Spring bean, you can let the container manage the lifecycle or invoke the initialization method as appropriate for your configuration style.

Separating the tokenizer and field set mapper makes it possible to change the input format without rewriting object construction logic as long as the field contract remains compatible. Conversely, you can swap the mapper to change type conversion or object structure without rewriting tokenization rules.

## 4. LineTokenizer and FieldSet

LineTokenizer parses a line into a FieldSet. FieldSet is an abstraction similar to a data row with field names and extracted values. It provides methods to read by position or by name, including conversions to numeric types, booleans, and dates.

Commonly used methods:

| Method | Result |
|---|---|
| readString("orderId") | String |
| readInt("quantity") | Integer |
| readLong("customerNumber") | Long integer |
| readBigDecimal("amount") | Exact decimal number |
| readBoolean("active") | Boolean |
| readDate("orderDate", "yyyy-MM-dd") | java.util.Date using pattern |

Reading by name is usually easier to maintain than reading by index:

~~~java
String orderId = fieldSet.readString("orderId");
BigDecimal amount = fieldSet.readBigDecimal("amount");
~~~

When reading by position, the code depends on column order in the file. If the file changes column order but the tokenizer still builds the FieldSet with the same name mappings, code that reads by name is much less affected.

The tokenizer is also responsible for detecting mismatched token counts based on its strictness setting. When a line's structure is incorrect, it can throw an exception rather than creating a FieldSet with missing fields. Decide explicitly how to handle lines with missing or extra columns; do not silently treat an empty string as valid data if business rules require a mandatory field.

## 5. DelimitedLineTokenizer for CSV or delimited files

DelimitedLineTokenizer splits a line by a delimiter, typically a comma. You can declare column names so the FieldSet carries clear field names.

Configuration example:

~~~java
@Bean
LineTokenizer orderLineTokenizer() {
    DelimitedLineTokenizer tokenizer = new DelimitedLineTokenizer();
    tokenizer.setDelimiter(",");
    tokenizer.setNames(
            "orderId",
            "customerId",
            "amount",
            "orderDate");
    tokenizer.setQuoteCharacter('"');
    tokenizer.setStrict(true);
    return tokenizer;
}
~~~

With the line:

~~~text
ORD-1003,CUS-03,125.50,2026-11-14
~~~

FieldSet will contain the fields orderId, customerId, amount, and orderDate.

If a value contains the delimiter, such as customer name Nguyen, An, quoting rules are needed:

~~~text
ORD-1004,CUS-04,"Nguyen, An",125.50
~~~

In this example, the tokenizer must be configured to match the file format so the comma inside the quoted field is not treated as a separator. For CSV files with escape rules, newlines inside quoted fields, or special dialects, verify that the parser in use supports the exact format produced by the source system.

setNames(...) assigns names to tokens in sequence. If the file has a header, skipping the header is the reader's responsibility—the tokenizer does not automatically infer column names from the first line.

## 6. FixedLengthTokenizer for fixed-width files

Not all files are separated by commas. Some systems export fixed-width files, where each field occupies a defined range of characters.

Example:

~~~text
ORD0000123CUS0000450000012550
~~~

Assume the format is:

- Characters 1–10: order ID.
- Characters 11–20: customer ID.
- Characters 21–30: amount in cents.

FixedLengthTokenizer can be used:

~~~java
@Bean
LineTokenizer fixedWidthOrderTokenizer() {
    FixedLengthTokenizer tokenizer = new FixedLengthTokenizer();
    tokenizer.setColumns(
            new Range(1, 10),
            new Range(11, 20),
            new Range(21, 30));
    tokenizer.setNames("orderId", "customerId", "amountInCents");
    tokenizer.setStrict(true);
    return tokenizer;
}
~~~

Range intervals are numbered according to character positions in the line. Confirm the source file's position conventions and the actual length of each record. If the file has blank padding, optional fields, or variable-length records, configure ranges and strictness according to the exact specification.

After tokenization, FieldSetMapper can convert amountInCents into a BigDecimal by dividing by 100. Unit conversion belongs in the mapper when it converts a file representation into a standard data type; business rules about valid monetary limits belong in the subsequent validation step.

## 7. FieldSetMapper<T>

FieldSetMapper<T> is an interface that converts a FieldSet into an object:

~~~java
public interface FieldSetMapper<T> {
    T mapFieldSet(FieldSet fieldSet) throws BindException;
}
~~~

It does not need to know whether the original line was comma-delimited or fixed-width. It works with the fields named by the tokenizer. Therefore, the same mapper can be reused across multiple file formats if they produce the same field names and data semantics.

A custom mapper typically performs:

1. Reading values by field name.
2. Converting data types.
3. Normalizing representations, such as trimming strings or mapping status codes.
4. Constructing the input object.
5. Reporting a binding error if a value cannot be converted.

Example:

~~~java
@Bean
FieldSetMapper<OrderInput> orderFieldSetMapper() {
    DateTimeFormatter dateFormat =
            DateTimeFormatter.ofPattern("yyyy-MM-dd");

    return fieldSet -> {
        String orderId = fieldSet.readString("orderId").trim();
        String customerId = fieldSet.readString("customerId").trim();
        BigDecimal amount = fieldSet.readBigDecimal("amount");
        LocalDate orderDate = LocalDate.parse(
                fieldSet.readString("orderDate").trim(),
                dateFormat);

        if (orderId.isEmpty()) {
            throw new IllegalArgumentException("orderId is required");
        }

        return new OrderInput(
                orderId,
                customerId,
                amount,
                orderDate);
    };
}
~~~

In real applications, use an appropriate binding exception to report which field failed and why. Avoid using a single generic exception for all cases if errors need to be classified for retry, skip, or reject handling.

## 8. BeanWrapperFieldSetMapper

If the target object is a JavaBean with a no-arg constructor and setters, Spring Batch provides BeanWrapperFieldSetMapper<T> to bind FieldSet values to properties by name.

JavaBean example:

~~~java
public class CustomerInput {

    private String customerId;
    private String customerName;
    private Integer age;

    public CustomerInput() {
    }

    public String getCustomerId() {
        return customerId;
    }

    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public String getCustomerName() {
        return customerName;
    }

    public void setCustomerName(String customerName) {
        this.customerName = customerName;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
~~~

Mapper configuration:

~~~java
@Bean
FieldSetMapper<CustomerInput> customerFieldSetMapper() throws Exception {
    BeanWrapperFieldSetMapper<CustomerInput> mapper =
            new BeanWrapperFieldSetMapper<>();
    mapper.setTargetType(CustomerInput.class);
    mapper.setStrict(true);
    mapper.afterPropertiesSet();
    return mapper;
}
~~~

Field names in FieldSet must match JavaBean property names, such as customerId and customerName. The mapper uses bean property binding to convert values to the property types when compatible converters/editors are registered.

BeanWrapperFieldSetMapper is convenient for simple objects. For immutable Java records, multi-argument constructors, complex nested mappings, or specialized conversion rules, a custom FieldSetMapper is usually clearer and easier to control.

## 9. Type conversion and date formatting

Files typically store all values as text, whereas Java objects require specific data types. Define the format of each field explicitly rather than relying on the host locale or configuration.

| File field | Representation | Object type |
|---|---|---|
| orderId | ORD-1001 | String |
| quantity | 12 | int or Integer |
| amount | 1250.75 | BigDecimal |
| orderDate | 2026-11-14 | LocalDate |
| active | Y or N | boolean |

For dates, use a formatter with an explicit pattern:

~~~java
private static final DateTimeFormatter ORDER_DATE_FORMAT =
        DateTimeFormatter.ofPattern("uuuu-MM-dd");

LocalDate orderDate = LocalDate.parse(
        fieldSet.readString("orderDate").trim(),
        ORDER_DATE_FORMAT);
~~~

For monetary amounts, use BigDecimal instead of double to avoid binary floating-point rounding errors. If the file uses a comma as the decimal separator and a dot as the thousands separator, configure the appropriate locale/NumberFormat or parse explicitly according to the file contract. Do not rely on the server's default locale.

For Y/N boolean values, convert explicitly:

~~~java
private boolean parseYesNo(String value) {
    return switch (value.trim().toUpperCase(Locale.ROOT)) {
        case "Y" -> true;
        case "N" -> false;
        default -> throw new IllegalArgumentException(
                "Expected Y or N but got: " + value);
    };
}
~~~

The mapper should distinguish between empty fields, null, default values, and invalid values. If a required field is empty, fail clearly instead of silently defaulting to 0 or an empty string and letting bad data travel deeper into the pipeline.

## 10. Mapping nested objects and complex structures

A flat file line can represent multiple attributes of nested objects. Example:

~~~text
orderId,customerId,customerName,shippingCity,shippingPostalCode
ORD-1001,CUS-01,An Nguyen,Da Nang,550000
~~~

A custom mapper can build nested objects:

~~~java
return fieldSet -> {
    Customer customer = new Customer(
            fieldSet.readString("customerId"),
            fieldSet.readString("customerName"));

    Address address = new Address(
            fieldSet.readString("shippingCity"),
            fieldSet.readString("shippingPostalCode"));

    return new OrderInput(
            fieldSet.readString("orderId"),
            customer,
            address);
};
~~~

This is structural mapping from file to object. Rules such as whether the address is within a delivery zone or whether the customer is permitted to place orders should still be handled in the processor or a business service.

If a file contains repeating sublists within one line or a multi-record hierarchical structure, a simple FieldSetMapper may not suffice. In those cases, you may need a custom LineMapper, a specialized reader, or a pre-parsing step to construct canonical records.

## 11. Files with multiple record types

A file can contain multiple line types, for example:

~~~text
HDR,ORDERS,2026-11-14
CUS,CUS-01,An Nguyen
ORD,ORD-1001,CUS-01,125.50
TRL,1,125.50
~~~

The leading characters on each line identify the record type. You can use PatternMatchingCompositeLineTokenizer to choose a tokenizer by pattern and then apply a matching mapper; or PatternMatchingCompositeLineMapper to combine both the tokenizer and FieldSetMapper per record type.

Example configuring a composite mapper for a common output type:

~~~java
@Bean
LineMapper<ImportRecord> importRecordLineMapper() throws Exception {
    PatternMatchingCompositeLineMapper<ImportRecord> mapper =
            new PatternMatchingCompositeLineMapper<>();

    Map<String, LineTokenizer> tokenizers = new HashMap<>();
    tokenizers.put("HDR*", headerTokenizer());
    tokenizers.put("CUS*", customerTokenizer());
    tokenizers.put("ORD*", orderTokenizer());
    tokenizers.put("TRL*", trailerTokenizer());
    mapper.setTokenizers(tokenizers);

    Map<String, FieldSetMapper<ImportRecord>> fieldSetMappers =
            new HashMap<>();
    fieldSetMappers.put("HDR*", headerFieldSetMapper());
    fieldSetMappers.put("CUS*", customerFieldSetMapper());
    fieldSetMappers.put("ORD*", orderFieldSetMapper());
    fieldSetMappers.put("TRL*", trailerFieldSetMapper());
    mapper.setFieldSetMappers(fieldSetMappers);

    return mapper;
}
~~~

ImportRecord is a common interface or supertype for the record types. Specific mappers create HeaderRecord, CustomerRecord, OrderRecord, or TrailerRecord.

When using patterns, ensure more specific patterns take precedence properly and every valid record type has a matching tokenizer/mapper. Lines matching no pattern should become traceable data errors rather than falling back to a default mapper if that would hide invalid record types.

## 12. Wiring LineMapper into FlatFileItemReader

After configuring the mapper, attach it to the reader:

~~~java
@Bean
FlatFileItemReader<OrderInput> orderFileReader(
        Resource inputFile,
        LineMapper<OrderInput> orderLineMapper) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderFileReader")
            .resource(inputFile)
            .linesToSkip(1)
            .skippedLinesCallback(line ->
                    log.info("Skipped header: {}", line))
            .lineMapper(orderLineMapper)
            .strict(true)
            .saveState(true)
            .build();
}
~~~

linesToSkip(1) skips the first line, typically the header. skippedLinesCallback allows logging or inspecting skipped lines. lineMapper converts each data line into an OrderInput. saveState(true) allows the reader to store its read position to support restart when the source and configuration are stable.

In jobs that pass the file path via JobParameters, the reader is usually declared as @StepScope with values bound from jobParameters. Do not store a mutable resource or file path in a singleton field if multiple executions can run concurrently.

## 13. Headers, blank lines, and comments

Headers do not necessarily have to go through LineMapper. If the file has a fixed header line, the reader can skip it with linesToSkip. If the header needs validation, use skippedLinesCallback to verify column names or file version.

Blank lines and comments require explicit rules:

- Skip blank lines if the file specification allows them.
- Handle comments according to defined prefixes.
- Do not skip malformed lines simply because the mapper failed to parse them.
- If the header has the wrong version, fail early instead of continuing to map with incorrect column positions.

If lines must be skipped based on complex conditions, use RecordSeparatorPolicy, LineCallbackHandler for headers, or an appropriate custom reader/mapper. Distinguish intentionally excluded lines from malformed data records.

## 14. Mapping errors and line information

Errors in the tokenizer or FieldSetMapper usually occur before the item reaches the processor. The reader can report parse errors, incorrect token counts, or type conversion failures.

A parse error should include sufficient context:

- File name or data source.
- Line number.
- Line content or a reference to the raw record.
- Name of the failing field.
- Input value and expected format.
- Error type and root cause.

Spring Batch provides FlatFileParseException to carry line numbers and input text during file parsing. When handling errors at the operational layer, avoid logging only Invalid input; keep the line number and source reference so the record can be traced.

Do not catch all exceptions inside LineMapper and return null. Returning null typically makes the reader treat it as end-of-data or missing item behavior, causing data to vanish without skip counts or reject tracking reflecting the error. Throw a meaningful exception so the step applies the configured retry/skip/fail policy.

## 15. LineMapper and skip policy

Tokenizer or FieldSetMapper failures occur during the read phase. If the application permits skipping a certain number of malformed lines, configure the appropriate skip exception:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderFileReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(FlatFileParseException.class)
        .skipLimit(10)
        .listener(importSkipListener)
        .build();
~~~

Only skip parse errors when business rules allow output to omit those records and the application records the rejected lines. For reconciliation, payment, or ledger files requiring absolute completeness, a single unparseable line may need to fail the step to avoid publishing incomplete results.

File connection errors, missing files, or configuration errors must not be treated as skippable item errors. Classify exceptions by nature: per-line data error, infrastructure error, or file-wide format error.

## 16. Reusing tokenizers and mappers

A tokenizer can typically be configured as a shared bean if, once initialized, it is read-only and holds no per-line state. Likewise, a stateless FieldSetMapper can be shared.

Do not store currentLine, currentFieldSet, record sequence numbers, or the current item in mutable fields of a singleton mapper. If multiple readers or steps run concurrently, that state can get mixed up.

Stateless mapper example:

~~~java
public class CustomerFieldSetMapper
        implements FieldSetMapper<CustomerInput> {

    @Override
    public CustomerInput mapFieldSet(FieldSet fieldSet) {
        return new CustomerInput(
                fieldSet.readString("customerId").trim(),
                fieldSet.readString("customerName").trim(),
                fieldSet.readInt("age"));
    }
}
~~~

The mapper only reads from the passed FieldSet and instantiates a new object. If different configurations are needed per file or step, use appropriate bean scoping/late binding instead of mutating fields on a singleton mapper while a job is running.

## 17. Testing LineMapper and FieldSetMapper

Tokenizers, mappers, and readers should be tested at different levels:

1. Tokenizer test: delimiter, quotes, field names, fixed ranges, and column counts.
2. FieldSetMapper test: type conversions, trimming, empty fields, dates, enums, and binding errors.
3. LineMapper test: combining tokenizer and mapper, verifying line mapping for a valid record.
4. Reader integration test: reading a small file, skipping the header, verifying item count and data order.
5. Malformed input test: lines with missing/extra columns, invalid numbers, invalid date formats, and unrecognized record types.
6. Line number test: verifying errors contain accurate line numbers and source locations.
7. Skip test: parse errors are skipped according to policy and stored in the reject store when business rules permit.
8. Restart test: the reader resumes from checkpoint without missing or duplicating committed lines.
9. Concurrent execution test: multiple steps reading different files do not share mutable mapper state.
10. Header/version test: incompatible headers are detected before mapping data incorrectly.

Example testing a mapper on a single line:

~~~java
@Test
void mapsDelimitedOrderLine() throws Exception {
    LineTokenizer tokenizer = orderLineTokenizer();
    FieldSetMapper<OrderInput> fieldSetMapper =
            orderFieldSetMapper();

    DefaultLineMapper<OrderInput> mapper = new DefaultLineMapper<>();
    mapper.setLineTokenizer(tokenizer);
    mapper.setFieldSetMapper(fieldSetMapper);
    mapper.afterPropertiesSet();

    OrderInput result = mapper.mapLine(
            "ORD-1001,CUS-01,125.50,2026-11-14",
            2);

    assertEquals("ORD-1001", result.orderId());
    assertEquals("CUS-01", result.customerId());
    assertEquals(new BigDecimal("125.50"), result.amount());
    assertEquals(LocalDate.of(2026, 11, 14), result.orderDate());
}
~~~

This example assumes OrderInput is a record with matching accessors and the mapper is configured with the date format. This test verifies single-line mapping; additional reader integration tests are needed to verify headers, file resources, line numbers, and restart behavior.

## 18. Common pitfalls

**Confusing LineMapper with FieldSetMapper.** LineMapper receives the text line and line number; FieldSetMapper receives the tokenized fields. Keep each component focused on its own responsibility.

**Splitting CSV manually with String.split.** This fails to handle quoted delimiters and escaping properly. Use DelimitedLineTokenizer or an appropriate parser.

**Reading FieldSet by index everywhere.** Code breaks easily when column order changes. Name the fields and read by name whenever possible.

**Not declaring column names or ranges explicitly.** Position-dependent mappings are hard to maintain. Declare names/columns according to the file specification.

**Letting BeanWrapperFieldSetMapper bind the wrong properties.** Token names fail to match JavaBean properties or data types cannot be converted. Verify target types, setters, and converters.

**Using the default locale to parse currency or dates.** Results can differ across environments. Define formats explicitly.

**Catching exceptions and returning null.** Faulty records disappear without being recorded. Throw contextual exceptions so skip/reject/fail policies handle them.

**Putting business validation into the mapper.** The mapper becomes hard to reuse. Keep mapping in the reader and business rules in the processor/service.

**Using a singleton mapper with mutable state.** Concurrent steps can mix data. Keep mappers stateless or create per-execution instances.

**Skipping headers without checking the version.** Files with changed columns can be mapped silently into wrong fields without raising errors. Validate the header before reading data.

## 19. Workflow for building file mapping

When integrating a new file format, you can follow this sequence:

1. Read the file specification: delimiter, quote, encoding, header, line ending, fixed ranges, and record types.
2. Define the canonical input object that the processor expects to receive.
3. Choose the appropriate tokenizer: delimited, fixed-length, or composite.
4. Name fields so mapping does not depend on index where possible.
5. Write a FieldSetMapper or use BeanWrapperFieldSetMapper for simple JavaBeans.
6. Convert types with explicit formats and handle empty values safely.
7. Combine using DefaultLineMapper or a composite mapper.
8. Attach LineMapper to FlatFileItemReader and configure header, resource, and state.
9. Classify parse errors under read/skip/fail policies and record source locations.
10. Test valid data, malformed input, restart, and different file versions.

## Conclusion

LineMapper converts a line of text into an item; FieldSetMapper converts the FieldSet created by the tokenizer into a Java object. With DefaultLineMapper, LineTokenizer splits the line into fields while FieldSetMapper handles type conversion and object creation. DelimitedLineTokenizer fits delimited files; FixedLengthTokenizer fits fixed-width files; composite mappers handle multiple record types within the same file.

Name fields clearly, parse dates and numbers with explicit formats, keep mappers stateless, and ensure parse errors carry line numbers and source references. Wire the mapper into FlatFileItemReader, define how headers and malformed lines are handled, and test from single-line mapping up to reader/restart integration. When parsing, mapping, and business validation are cleanly separated, flat-file pipelines are easier to maintain and faulty data can be traced accurately.
