# LineAggregator

`LineAggregator<T>` is the Spring Batch component that converts a Java item into a line of text for `FlatFileItemWriter` to write to a file. The reader performs the reverse transformation: reading records and mapping them into objects; the writer uses an aggregator to format objects into output records.

The aggregator defines how an item is represented in the file: field order, delimiter, number/date formatting, padding, or escaping rules. Choosing the right aggregator ensures the output file conforms to the receiving system's contract and can be read back reliably.

## 1. Where does LineAggregator fit in FlatFileItemWriter?

In a chunk-oriented step, the writer receives a chunk of processed items. `FlatFileItemWriter` iterates through the items and calls `LineAggregator.aggregate(item)` to produce each line's content. The writer appends the line separator and writes the result to the resource.

```text
ItemWriter.write(chunk)
        |
        v
FlatFileItemWriter
        |
        +--> item 1 -> LineAggregator.aggregate(item 1) -> line 1
        +--> item 2 -> LineAggregator.aggregate(item 2) -> line 2
        +--> item 3 -> LineAggregator.aggregate(item 3) -> line 3
        |
        v
   Output file
```

The interface has a simple contract:

```java
public interface LineAggregator<T> {
    String aggregate(T item);
}
```

Each call returns the content of a single record, excluding file management or writing the newline itself. `FlatFileItemWriter` manages the resource, encoding, line separator, headers/footers, checkpoints, and transaction-aware output.

## 2. Configuring LineAggregator in Spring Batch 5

`FlatFileItemWriter`'s builder takes a `LineAggregator` to convert objects into lines. Example exporting a customer list:

```java
@Bean
@StepScope
FlatFileItemWriter<Customer> customerWriter(
        @Value("#{jobParameters['output.file']}") String outputFile,
        LineAggregator<Customer> customerLineAggregator) {

    return new FlatFileItemWriterBuilder<Customer>()
        .name("customerWriter")
        .resource(new FileSystemResource(outputFile))
        .encoding(StandardCharsets.UTF_8.name())
        .lineAggregator(customerLineAggregator)
        .lineSeparator(System.lineSeparator())
        .saveState(true)
        .build();
}
```

`output.file` is late-bound when the Step-scoped target is created. The writer receives a configured aggregator; every item is formatted under the same contract. A stable `name` and `saveState(true)` support saving write position for restart.

In production, explicitly choose the existing-file policy, append/overwrite behavior, encoding, and restart strategy. Those choices belong to writer/resource configuration, not `LineAggregator`.

## 3. DelimitedLineAggregator for delimited files

`DelimitedLineAggregator<T>` joins values supplied by a `FieldExtractor<T>` using a delimiter. It suits simple formats such as pipe-separated or comma-separated files when data rules do not require complex escaping.

```java
@Bean
LineAggregator<Customer> customerLineAggregator() {
    DelimitedLineAggregator<Customer> aggregator =
        new DelimitedLineAggregator<>();

    aggregator.setDelimiter("|");
    aggregator.setFieldExtractor(customer -> new Object[] {
        customer.getCustomerId(),
        customer.getName(),
        customer.getEmail()
    });

    return aggregator;
}
```

For a `Customer`, the aggregator can produce the line:

```text
C001|An Nguyen|an@example.test
```

The order of values in `Object[]` dictates column order. The header, if present, must use that exact order. If you change extractor order without updating the file schema, consumers may read the wrong columns even though the writer completes without error.

## 4. FieldExtractor separates data extraction from formatting

`FieldExtractor<T>` turns an object into an ordered array of values. The aggregator uses that array to build the line. Separating these two responsibilities lets you change formatting without rewriting field extraction logic.

```text
Customer object
      |
      v
FieldExtractor<Customer>
      |
      v
[customerId, name, email]
      |
      v
LineAggregator
      |
      v
"C001","An Nguyen","an@example.test"
```

You can use `BeanWrapperFieldExtractor` for classes following JavaBean conventions:

```java
BeanWrapperFieldExtractor<Customer> extractor =
    new BeanWrapperFieldExtractor<>();
extractor.setNames(new String[] {
    "customerId", "name", "email"
});
extractor.afterPropertiesSet();

DelimitedLineAggregator<Customer> aggregator =
    new DelimitedLineAggregator<>();
aggregator.setDelimiter(",");
aggregator.setFieldExtractor(extractor);
```

`BeanWrapperFieldExtractor` reads properties by declared name, so the class must expose matching properties. For records, non-standard objects, or complex extraction rules, use a lambda or custom `FieldExtractor` for clear control.

Lambda example:

```java
FieldExtractor<Invoice> invoiceExtractor = invoice -> new Object[] {
    invoice.getInvoiceNumber(),
    invoice.getInvoiceDate(),
    invoice.getTotalAmount()
};
```

Do not put business rules or database queries inside an extractor. It should only extract values from items already prepared by the processor.

## 5. DelimitedLineAggregator does not replace a CSV contract

Do not assume that joining fields with commas automatically produces a safe CSV file. A field may contain commas, quotes, or newline characters. Simply concatenating strings can cause records to split incorrectly when read back by consumers.

Example data:

```text
customerId = C001
name       = Nguyen, An
email      = an@example.test
```

Plain comma-joining produces:

```text
C001,Nguyen, An,an@example.test
```

Consumers will interpret this as four fields instead of three. A quote-compliant CSV must format the name as `"Nguyen, An"` and escape internal quotes by doubling them.

`DelimitedLineAggregator` works for simple delimiters, yet always check quoting/escaping capabilities in your version and configuration. Quote settings on `DelimitedLineTokenizer` on the reader side do not automatically configure escaping for the writer's aggregator.

## 6. Building a custom LineAggregator for CSV escaping

When strict CSV quoting rules are required, implement `LineAggregator<T>` directly. The escaping function should handle nulls, quotes, delimiters, and newlines according to the consumer's dialect.

```java
public class CustomerCsvLineAggregator
        implements LineAggregator<Customer> {

    @Override
    public String aggregate(Customer customer) {
        return String.join(",",
            csv(customer.getCustomerId()),
            csv(customer.getName()),
            csv(customer.getEmail())
        );
    }

    private String csv(String value) {
        if (value == null) {
            return "";
        }

        boolean mustQuote = value.contains(",")
            || value.contains("\"")
            || value.contains("\r")
            || value.contains("\n");

        String escaped = value.replace("\"", "\"\"");
        return mustQuote ? "\"" + escaped + "\"" : escaped;
    }
}
```

Example output:

```text
C001,"Nguyen, An",an@example.test
```

This is a basic CSV example using comma delimiter and double-quote quoting. If the consumer requires quoting every field, escaping tabs, handling control characters, or a specialized dialect, extend the rules accordingly or use a dedicated CSV library. Do not invent an approximate dialect and assume every system reads it the same way.

## 7. FormatterLineAggregator for patterned formatting

`FormatterLineAggregator<T>` builds lines from a format string and a `FieldExtractor<T>`. It is useful for fixed-width output or formats where each field has a specific width, alignment, and display pattern.

Example producing a record with an 8-character order ID, 30-character customer name, and 12-character amount with two decimal digits:

```java
FormatterLineAggregator<Order> aggregator =
    new FormatterLineAggregator<>();

aggregator.setFormat("%-8s%-30s%012.2f");
aggregator.setFieldExtractor(order -> new Object[] {
    order.getOrderId(),
    order.getCustomerName(),
    order.getTotalAmount()
});
```

With this format:

- `%-8s`: string at least 8 characters wide, left-aligned.
- `%-30s`: string at least 30 characters wide, left-aligned.
- `%012.2f`: floating-point number 12 characters wide, zero-padded on the left, two decimal digits.

Widths in formatters are typically minimum widths; longer strings can overflow the width unless explicitly validated. If a fixed-width contract requires truncation or rejection of oversized values, validate explicitly before formatting. Never silently truncate identifiers or monetary amounts.

Locale also affects numeric formatting. If the file requires a dot as the decimal separator, configure a formatter with an explicit locale or format numbers before building the line. Do not rely on the host's default locale.

## 8. Custom formatter for fixed-width files

For fixed-width files, field lengths and positions are part of the contract. You can use `FormatterLineAggregator` when the format string is clear enough; when there are multiple length-validation rules, a custom `LineAggregator` can be easier to maintain.

Example:

```java
public class AccountFixedWidthAggregator
        implements LineAggregator<Account> {

    @Override
    public String aggregate(Account account) {
        String accountNo = requireLength(
            account.getAccountNumber(), 10, "accountNumber");
        String name = padRight(
            account.getName(), 30);
        String balance = String.format(
            Locale.ROOT, "%012.2f", account.getBalance());

        return accountNo + name + balance;
    }

    private String requireLength(String value, int length, String field) {
        if (value == null || value.length() != length) {
            throw new IllegalArgumentException(
                field + " must contain exactly " + length + " characters");
        }
        return value;
    }

    private String padRight(String value, int width) {
        String text = value == null ? "" : value;
        if (text.length() > width) {
            throw new IllegalArgumentException("name is too long");
        }
        return text + " ".repeat(width - text.length());
    }
}
```

This example illustrates validation and padding; adjust widths, encoding, and character counting to match the target file specification. Some legacy systems define positions in bytes rather than character counts, especially with multi-byte charsets. In those cases, padding by `String.length()` is insufficient; measure byte length in the actual charset.

## 9. Using PassThroughLineAggregator when the item is already a line

If an item already holds a complete formatted line of text, use `PassThroughLineAggregator<String>` to emit the string without splitting fields.

```java
@Bean
FlatFileItemWriter<String> rawLineWriter(Resource outputResource) {
    return new FlatFileItemWriterBuilder<String>()
        .name("rawLineWriter")
        .resource(outputResource)
        .lineAggregator(new PassThroughLineAggregator<>())
        .saveState(true)
        .build();
}
```

This fits when the processor already formats records per schema. However, when line-building logic sits inside the processor, test formatting there and keep the output contract explicit. Never use pass-through to bypass data validation or field escaping.

## 10. Headers and footers belong to the writer

`LineAggregator` formats individual items. Headers and footers are non-item content managed by `FlatFileItemWriter` via separate callbacks.

```java
@Bean
FlatFileItemWriter<Customer> customerWriter(
        Resource outputResource,
        LineAggregator<Customer> customerLineAggregator) {

    return new FlatFileItemWriterBuilder<Customer>()
        .name("customerWriter")
        .resource(outputResource)
        .encoding(StandardCharsets.UTF_8.name())
        .headerCallback(writer ->
            writer.write("customerId,name,email"))
        .footerCallback(writer ->
            writer.write("# end of customer export"))
        .lineAggregator(customerLineAggregator)
        .saveState(true)
        .build();
}
```

The header must match the field order emitted by the aggregator. The footer can carry counts, checksums, or an end marker if the consumer requires it, but never treat the presence of a footer as proof the job succeeded in every scenario. When files must be published only after the entire job succeeds, write to a temporary file and verify/publish in a final step.

## 11. Consistent date, number, and null formatting

Output files are read by other systems, so formatting must stay consistent across hosts and deployments.

For dates, use an explicit formatter:

```java
DateTimeFormatter dateFormat = DateTimeFormatter.ISO_LOCAL_DATE;
String date = order.getOrderDate().format(dateFormat);
```

For monetary values, use `BigDecimal` and format with explicit decimal separator, scale, and rounding rules. Never pass money through `double` when decimal precision is required.

For nulls, confirm whether the consumer expects an empty string, a marker like `\N`, or a default value. Do not let `String.valueOf(null)` emit the literal text `null` if the schema expects an empty field.

A custom aggregator can centralize these rules in one place:

```java
private String formatAmount(BigDecimal amount) {
    if (amount == null) {
        return "";
    }
    return amount.setScale(2, RoundingMode.HALF_UP)
        .toPlainString();
}
```

Rounding rules must come from the business contract, not convenience during formatting.

## 12. Configuring line separator and encoding

`LineAggregator` returns the content of a single record. `FlatFileItemWriter` appends the configured line separator between records. You can choose `\n` or `\r\n` depending on the receiving system.

```java
return new FlatFileItemWriterBuilder<Customer>()
    .name("customerWriter")
    .resource(outputResource)
    .encoding(StandardCharsets.UTF_8.name())
    .lineSeparator("\r\n")
    .lineAggregator(customerLineAggregator)
    .build();
```

Do not manually append `\n` inside `aggregate()` when the writer also appends a line separator, as that inserts blank lines between records. Encoding belongs to the writer as well; the aggregator only builds a Java `String` and does not encode bytes.

If the consumer requires Windows CRLF, a UTF-8 BOM, or a specific code page, configure and test directly on output bytes rather than comparing strings in unit tests alone.

## 13. Error handling in LineAggregator

`LineAggregator.aggregate(item)` declares no checked exceptions. If an item cannot be formatted, the implementation can throw a runtime exception. The writer call then fails and the chunk can roll back under the step's transaction policy.

Example when a required field is missing:

```java
@Override
public String aggregate(Customer customer) {
    if (customer.getCustomerId() == null) {
        throw new IllegalArgumentException(
            "customerId is required for export");
    }
    return customer.getCustomerId() + "," + csv(customer.getName());
}
```

Validate output data before or inside the processor when an error reflects an item-level business issue. The aggregator should focus on formatting; stuffing validation and lookups into the aggregator makes its responsibilities harder to test.

If formatting errors are skippable, configure a skip policy for the appropriate exception in a fault-tolerant step and use a `SkipListener` to log excluded items. Ensure re-invoking the writer during recovery does not produce duplicate output or corrupted files.

## 14. LineAggregator and file writer transactions

`FlatFileItemWriter` is an `ItemStreamWriter` participating in chunk transaction lifecycles. With the writer's default transactional configuration, written data is managed through a transaction-bound buffer so uncommitted output is not finalized prematurely. `transactional(false)` can be configured in special cases, but content may then be flushed immediately and cannot roll back cleanly alongside a database transaction.

```text
Chunk transaction begins
       |
       v
Writer calls LineAggregator for each item
       |
       v
Output is buffered per writer transaction policy
       |
       +-- COMMIT --> flush chunk content
       |
       +-- ROLLBACK -> discard uncommitted output if writer is transactional
```

Do not assume files and databases always commit atomically together. When a file writer and a database use distinct resources, a transaction manager may not coordinate them as a distributed transaction. For consistent publishing, write to a temporary file, finalize data, verify, and rename/publish in an appropriate final step.

## 15. Restart and FlatFileItemWriter state

The writer needs a stable name and `saveState(true)` if the step must be restartable. Spring Batch persists state needed to know the write position and resume output for the same execution.

```java
new FlatFileItemWriterBuilder<Order>()
    .name("ordersOutputWriter")
    .resource(new FileSystemResource(outputFile))
    .lineAggregator(orderLineAggregator)
    .saveState(true)
    .build();
```

When restarting the same `JobInstance`, use the same output resource and identifying parameters. Do not replace the output file or wipe already-committed content between executions if you expect recovery at the exact position.

With `saveState(false)`, the writer does not persist checkpoints. That fits only when the step does not need restart or the application handles recovery differently. Never disable state while still expecting the writer to know where it left off.

## 16. Append, overwrite, and existing files

The policy when an output file already exists must be chosen explicitly. Common options include:

- Creating/overwriting a fresh file for a new run.
- Appending to an existing file under a well-designed workflow.
- Restarting the same execution and resuming from the saved checkpoint.

`append(true)` is not equivalent to safe restart. Blindly appending to an old file can create duplicate headers, duplicate records, or mixed data from two separate business runs in one file. Restarts should rely on `JobRepository` and writer state, not on enabling append to tack lines onto the end.

Example configuring overwrite for a fresh run:

```java
return new FlatFileItemWriterBuilder<Order>()
    .name("ordersOutputWriter")
    .resource(new FileSystemResource(outputFile))
    .shouldDeleteIfExists(true)
    .append(false)
    .lineAggregator(orderLineAggregator)
    .saveState(true)
    .build();
```

Verify writer behavior when opening the resource on both fresh runs and restarts. Delete/append options must coordinate with saved state; never toggle them arbitrarily between executions of the same `JobInstance`.

## 17. Guaranteeing output order and schema

Output files are integration contracts. Document clearly:

1. Column order.
2. Column names and meanings.
3. Delimiter, quoting, and escaping.
4. Date format, timezone, and decimal separator.
5. Null/empty conventions.
6. Encoding and line separator.
7. Header/footer and schema version.
8. Handling of oversized fields or invalid values.

Never rely on incidental reflection or map iteration order. Declare exact ordering in `FieldExtractor` or a custom aggregator. When schemas change, consider file versioning or new output filenames so consumers do not misread data.

## 18. Testing LineAggregator

Aggregators are straightforward to unit-test in isolation because they take one item and return a string. Tests should verify exact output, including edge cases.

Example:

```java
@Test
void shouldQuoteCommaAndEscapeQuoteInCsvField() {
    Customer customer = new Customer(
        "C001", "An, \"Annie\" Nguyen", "an@example.test");

    String line = new CustomerCsvLineAggregator().aggregate(customer);

    assertThat(line).isEqualTo(
        "C001,\"An, \"\"Annie\"\" Nguyen\",an@example.test");
}
```

Cases to test:

- Normal values and field order.
- Nulls, empty strings, and whitespace.
- Delimiters inside fields.
- Quotes requiring escaping.
- Embedded CR/LF inside fields if dialect permits.
- Monetary amounts, scale, and rounding.
- Dates, timezones, and locales.
- Fields exceeding fixed-width limits.
- Unicode characters and output encoding.

Integration tests with `FlatFileItemWriter` should verify headers/footers, line separators, existing files, restart/checkpoints, and transaction rollbacks. Unit testing the aggregator alone does not prove the writer manages resources and transactions properly.

## 19. Common pitfalls

| Pitfall | Consequence | Mitigation |
|---|---|---|
| Joining fields with a delimiter without escaping | Fields containing delimiters shift column counts | Use a custom aggregator or CSV library matching the dialect |
| Confusing tokenizer quoting with writer escaping | Output is incompatible with file readers | Configure formatting rules on a dedicated aggregator |
| Changing FieldExtractor order without updating the header | Consumers read columns incorrectly | Keep schema and header order synchronized |
| Putting business validation in the aggregator | Logic is hard to reuse and test | Validate/transform in the processor; keep the aggregator focused on formatting |
| Appending newlines inside `aggregate()` | Writer may emit blank lines | Let the writer manage `lineSeparator` |
| Relying on default locale | Decimal/date formats vary across hosts | Specify locale and formatters explicitly |
| Silently truncating fixed-width fields | Data loss or corrupted identifiers | Validate lengths and fail informatively |
| Using append to simulate restart | Headers/records can be duplicated | Use writer state and `JobRepository` |
| Disabling saveState while expecting restart | Cannot recover output position | Enable state and use a stable writer name |
| Treating file and database as one atomic transaction | File retains side effects when DB rolls back | Use temporary staging files, verify, and publish in a final step |

## 20. Production LineAggregator design checklist

When exporting files from Spring Batch, confirm:

1. Does the consumer expect CSV/delimited, fixed-width, or a custom format?
2. Are field order and schema unambiguously defined?
3. Do delimiters, quotes, and newlines need quoting/escaping?
4. How are nulls, dates, numbers, and decimal separators represented?
5. Are field lengths measured in characters or bytes?
6. Are headers/footers or schema versions required?
7. Which encoding, line separator, and resource policy does the writer use?
8. Does output require restartability and transaction-aware buffering?
9. Is the file published only after the entire job succeeds?
10. Do unit and integration tests verify output bytes, restarts, and rollbacks?

## Conclusion

`LineAggregator<T>` converts a Java item into a line of text for `FlatFileItemWriter`. `DelimitedLineAggregator` joins fields by delimiter; `FormatterLineAggregator` formats by pattern; `FieldExtractor` defines value ordering; custom aggregators control CSV escaping, fixed-width padding, and specialized rules.

Separate field extraction from formatting, never assume delimiter joining makes valid CSV, and let the writer manage headers/footers, encoding, line separators, resources, checkpoints, and transaction-aware output. Keep schemas stable, test exact output records, and use temporary staging files with a publish step whenever incomplete outputs must not be exposed.
