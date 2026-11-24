# FieldSet and data types

In Spring Batch, `FieldSet` is the object representing the fields extracted from a line in a file. It provides ways to read values by position or by name, and also supports converting text data into Java types such as `int`, `long`, `BigDecimal`, `Date`, and `boolean`.

In flat-file processing, the typical flow is: `LineTokenizer` splits a line into a `FieldSet`, and then `FieldSetMapper` maps the `FieldSet` into a business object. Understanding these two components helps control data types, date formats, empty values, and input data errors.

## 1. What is FieldSet?

`FieldSet` is a Spring Batch abstraction similar to a row in a data table: each field has a value and can be accessed by index or by column name.

Example `orders.csv` file:

```csv
order_id,customer_id,amount,quantity,business_date
00001234,CUST-18,1250.75,2,2026-11-15
00001235,CUST-21,89.90,1,2026-11-15
```

After the tokenizer splits the second line, the `FieldSet` can be visualized as follows:

| Index | Field name | Text value |
|---:|---|---|
| 0 | `order_id` | `00001234` |
| 1 | `customer_id` | `CUST-18` |
| 2 | `amount` | `1250.75` |
| 3 | `quantity` | `2` |
| 4 | `business_date` | `2026-11-15` |

`FieldSet` is not the final business object. It holds the values extracted from the file line; the mapping step converts them into the data types the application needs.

## 2. LineTokenizer and FieldSetMapper flow

In a flat-file reader, `LineMapper` coordinates two steps:

1. `LineTokenizer` parses a line and produces a `FieldSet`.
2. `FieldSetMapper` reads the `FieldSet` and constructs the target object.

```text
A line in the file
        |
        v
   LineTokenizer
        |
        v
     FieldSet
        |
        v
   FieldSetMapper
        |
        v
  Order / business DTO
        |
        v
   ItemProcessor
```

Spring Batch provides several common tokenizers:

| Tokenizer | How it splits | Use case |
|---|---|---|
| `DelimitedLineTokenizer` | Splits by a delimiter such as comma or tab | CSV, TSV, and delimited files. |
| `FixedLengthTokenizer` | Splits by fixed character position ranges | Files with a fixed-width layout. |

`DefaultLineMapper` is commonly used to combine a tokenizer and a mapper:

```java
DefaultLineMapper<Order> lineMapper = new DefaultLineMapper<>();
lineMapper.setLineTokenizer(tokenizer);
lineMapper.setFieldSetMapper(fieldSetMapper);
```

The reader calls `LineMapper` for each data line and receives an `Order` object.

## 3. Reading FieldSet by name or index

`FieldSet` allows reading values by index:

```java
String orderId = fieldSet.readString(0);
String customerId = fieldSet.readString(1);
BigDecimal amount = fieldSet.readBigDecimal(2);
int quantity = fieldSet.readInt(3);
```

Or reading by name:

```java
String orderId = fieldSet.readString("order_id");
String customerId = fieldSet.readString("customer_id");
BigDecimal amount = fieldSet.readBigDecimal("amount");
int quantity = fieldSet.readInt("quantity");
```

Reading by name is usually easier to maintain because it does not couple the code directly to column ordering. However, the field names must be declared accurately on the tokenizer. If names are missing or misspelled, access by name will not work as expected.

Commonly used typed read methods include:

| Method | Result type |
|---|---|
| `readString(...)` | `String` |
| `readInt(...)` | `int` |
| `readLong(...)` | `long` |
| `readShort(...)` | `short` |
| `readFloat(...)` | `float` |
| `readDouble(...)` | `double` |
| `readBigDecimal(...)` | `BigDecimal` |
| `readBoolean(...)` | `boolean` |
| `readDate(...)` | `java.util.Date` |

Several methods have overloads accepting either an index or a field name. For dates and data requiring specific formatting, read the string and parse it with an explicit formatter to control format and errors.

## 4. FieldSetMapper maps data into objects

`FieldSetMapper<T>` is the interface that converts a `FieldSet` into an object of type `T`:

```java
public interface FieldSetMapper<T> {
    T mapFieldSet(FieldSet fieldSet) throws BindException;
}
```

Example DTO:

```java
import java.math.BigDecimal;
import java.time.LocalDate;

public record Order(
        String orderId,
        String customerId,
        BigDecimal amount,
        int quantity,
        LocalDate businessDate) {
}
```

Custom mapper:

```java
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

import org.springframework.batch.item.file.mapping.FieldSetMapper;
import org.springframework.batch.item.file.transform.FieldSet;

public class OrderFieldSetMapper implements FieldSetMapper<Order> {

    private static final DateTimeFormatter DATE_FORMAT =
            DateTimeFormatter.ISO_LOCAL_DATE;

    @Override
    public Order mapFieldSet(FieldSet fieldSet) {
        String orderId = fieldSet.readString("order_id");
        String customerId = fieldSet.readString("customer_id");
        BigDecimal amount = fieldSet.readBigDecimal("amount");
        int quantity = fieldSet.readInt("quantity");
        LocalDate businessDate = LocalDate.parse(
                fieldSet.readString("business_date"), DATE_FORMAT);

        return new Order(
                orderId,
                customerId,
                amount,
                quantity,
                businessDate);
    }
}
```

A custom mapper is suitable when you need to parse `LocalDate`, normalize strings, apply defaults, or validate data before constructing the object. For example, keeping `orderId` as a `String` prevents losing leading zeros.

## 5. Using BeanWrapperFieldSetMapper

If field names in the file match the properties of a JavaBean, you can use `BeanWrapperFieldSetMapper` instead of writing a manual mapper.

JavaBean example:

```java
import java.math.BigDecimal;
import java.time.LocalDate;

public class OrderRecord {

    private String orderId;
    private String customerId;
    private BigDecimal amount;
    private Integer quantity;
    private LocalDate businessDate;

    public String getOrderId() { return orderId; }
    public void setOrderId(String orderId) { this.orderId = orderId; }

    public String getCustomerId() { return customerId; }
    public void setCustomerId(String customerId) { this.customerId = customerId; }

    public BigDecimal getAmount() { return amount; }
    public void setAmount(BigDecimal amount) { this.amount = amount; }

    public Integer getQuantity() { return quantity; }
    public void setQuantity(Integer quantity) { this.quantity = quantity; }

    public LocalDate getBusinessDate() { return businessDate; }
    public void setBusinessDate(LocalDate businessDate) {
        this.businessDate = businessDate;
    }
}
```

Mapper configuration:

```java
import org.springframework.batch.item.file.mapping.BeanWrapperFieldSetMapper;

BeanWrapperFieldSetMapper<OrderRecord> mapper =
        new BeanWrapperFieldSetMapper<>();
mapper.setTargetType(OrderRecord.class);
mapper.setStrict(true);
```

`BeanWrapperFieldSetMapper` uses Spring bean property binding to map fields to matching properties. The JavaBean needs an appropriate way to instantiate and setters for properties. Tokenizer/field names should correspond to property names; for example, `orderId` maps to property `orderId`.

For special types such as `LocalDate`, enums, or locale-dependent number formats, ensure appropriate converters/editors are registered. If mapping requires complex rules or detailed error handling, a custom `FieldSetMapper` is usually easier to control.

## 6. Declaring the tokenizer and field names

Example using `DelimitedLineTokenizer` for CSV:

```java
import org.springframework.batch.item.file.transform.DelimitedLineTokenizer;

DelimitedLineTokenizer tokenizer = new DelimitedLineTokenizer();
tokenizer.setDelimiter(",");
tokenizer.setNames(
        "order_id",
        "customer_id",
        "amount",
        "quantity",
        "business_date");
tokenizer.setStrict(true);
```

Field names form the contract between the source file and the mapper. When column order changes, if the tokenizer still assigns names in the old order, the mapper may receive the wrong data without necessarily causing a type error.

`strict(true)` requires the number of fields in a line to match the configured names. When a file has the wrong column count, the tokenizer reports an error instead of silently creating a `FieldSet` with missing or extra fields under strict settings. For files with variable formats, define an explicit policy for each line type.

When working with CSV values that contain commas, handle quoting properly. Example:

```csv
order_id,customer_name,amount
1001,"Nguyen Van A, Branch 2",125.50
```

Do not call `String.split(",")` manually to parse CSV because it does not understand commas inside quoted fields. Use a quote-aware tokenizer or a dedicated CSV library.

## 7. FieldSet with fixed-length files

Not every flat file uses delimiters. Some legacy systems export files with fixed column widths:

```text
00001234CUST-18     000012507520261115
```

You can use `FixedLengthTokenizer` to declare the character intervals:

```java
import org.springframework.batch.item.file.transform.FixedLengthTokenizer;
import org.springframework.batch.item.file.transform.Range;

FixedLengthTokenizer tokenizer = new FixedLengthTokenizer();
tokenizer.setNames("order_id", "customer_id", "amount", "date_text");
tokenizer.setColumns(
        new Range(1, 8),
        new Range(9, 18),
        new Range(19, 28),
        new Range(29, 36));
tokenizer.setStrict(true);
```

The ranges in the example are start/end character positions according to the `Range` API numbering. Confirm the file layout against the source specification, especially when the file uses padding, negative signs, implied decimals, or multi-byte encodings. For fixed-length records, length may be defined by characters or bytes by the source system; never assume the two measurements are identical for every charset.

Once the tokenizer produces a `FieldSet`, the same `FieldSetMapper` can be used for type conversion just as with CSV.

## 8. Converting Strings to numeric types

Values read from a file start as text. `FieldSet` supports numeric read methods:

```java
int quantity = fieldSet.readInt("quantity");
long accountNumber = fieldSet.readLong("account_number");
BigDecimal amount = fieldSet.readBigDecimal("amount");
```

### Use BigDecimal for currency

Do not use `float` or `double` to store monetary values when decimal precision is required. Use `BigDecimal`:

```java
BigDecimal amount = new BigDecimal(fieldSet.readString("amount"));
```

`BigDecimal` preserves exact decimal precision from the input string. If scale normalization is needed, use `setScale()` with a `RoundingMode` defined by business rules.

```java
BigDecimal normalized = amount.setScale(2, RoundingMode.UNNECESSARY);
```

`UNNECESSARY` throws an exception if rounding would be required. If business rules allow rounding, explicitly select `HALF_UP`, `HALF_EVEN`, or the appropriate rule; do not let rounding happen implicitly.

### Decimal separators and locale

The source file must use a consistent number convention. For example, `1250.75` and `1.250,75` are two different representations. `readBigDecimal()` generally expects standard numeric strings with a dot as the decimal separator. If the source uses a different locale, parse with `DecimalFormat` using an explicit locale or normalize the input before creating `BigDecimal`.

Do not blindly strip all commas, as that could turn `1,25` into `125` instead of `1.25`.

## 9. Converting dates and times

Files commonly represent dates as strings. Declare the format explicitly and parse into the appropriate Java type:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

DateTimeFormatter formatter = DateTimeFormatter.ofPattern("dd/MM/uuuu");
LocalDate date = LocalDate.parse("15/11/2026", formatter);
```

For ISO formats such as `2026-11-15`, use `DateTimeFormatter.ISO_LOCAL_DATE`. For timestamps with a timezone, consider `OffsetDateTime` or `Instant`; for local times without a timezone, use `LocalDateTime` per the data contract.

Do not use `LocalDateTime` for global timestamps if the source actually has a timezone but omits the offset. Determine the source's timezone and convert consistently.

When parsing fails, `DateTimeParseException` contains information about the invalid value. Depending on business requirements, you can let the Step fail, skip the record per policy, or log a reject record.

## 10. Booleans and enums

Not every file represents booleans as `true`/`false`. A source may use `Y/N`, `1/0`, or `ACTIVE/INACTIVE`. Normalize accepted values explicitly:

```java
private boolean parseActive(String value) {
    return switch (value.trim().toUpperCase(Locale.ROOT)) {
        case "Y", "YES", "1", "TRUE" -> true;
        case "N", "NO", "0", "FALSE" -> false;
        default -> throw new IllegalArgumentException(
                "Unsupported active flag: " + value);
    };
}
```

Enums should also be parsed in a controlled way:

```java
OrderStatus status;
try {
    status = OrderStatus.valueOf(
            fieldSet.readString("status").trim().toUpperCase(Locale.ROOT));
} catch (IllegalArgumentException ex) {
    throw new InvalidOrderException("Unknown order status", ex);
}
```

Do not let unrecognized values silently fall back to `false` or a default enum if that alters business meaning. Unrecognized values should be logged or handled according to the error policy.

## 11. Null, empty strings, and default values

In a text file, the following cases do not necessarily mean the same thing:

```text
1001,,125.50
1002,"",125.50
1003,NULL,125.50
```

- A field with no characters between two delimiters may be returned as an empty string by the tokenizer.
- A quoted empty field may also represent an empty string depending on the tokenizer.
- The string `NULL` is just text unless the source explicitly defines it as a null marker.

For optional fields, read as a `String` first and then normalize:

```java
String note = fieldSet.readString("note");
String normalizedNote = note == null || note.isBlank()
        ? null
        : note.trim();
```

For optional numbers, do not call `readInt()` directly when the field might be empty. Check the text first:

```java
String quantityText = fieldSet.readString("quantity").trim();
Integer quantity = quantityText.isEmpty()
        ? null
        : Integer.valueOf(quantityText);
```

Only use defaults when business rules explicitly define them. For example, an empty quantity might default to 1 in some formats, whereas in others it must be treated as an error. Do not automatically replace missing data with 0 because that can distort reports or monetary totals.

## 12. Validating and normalizing data in the mapper

`FieldSetMapper` is an appropriate place for syntactic conversion and basic per-line checks. Example:

```java
public class OrderFieldSetMapper implements FieldSetMapper<Order> {

    @Override
    public Order mapFieldSet(FieldSet fieldSet) {
        String orderId = fieldSet.readString("order_id").trim();
        String customerId = fieldSet.readString("customer_id").trim();
        String amountText = fieldSet.readString("amount").trim();

        if (orderId.isEmpty()) {
            throw new InvalidOrderException("order_id is required");
        }
        if (customerId.isEmpty()) {
            throw new InvalidOrderException("customer_id is required");
        }

        BigDecimal amount = new BigDecimal(amountText);
        if (amount.signum() < 0) {
            throw new InvalidOrderException("amount cannot be negative");
        }

        return new Order(
                orderId,
                customerId,
                amount,
                fieldSet.readInt("quantity"),
                LocalDate.parse(fieldSet.readString("business_date")));
    }
}
```

The mapper should focus on transforming a line into an object and validating local data. Business rules that query multiple systems, update databases, or depend on job-wide state usually fit better in an `ItemProcessor` or business service.

## 13. Configuring FlatFileItemReader with FieldSetMapper

You can connect the tokenizer and mapper using `DefaultLineMapper` and pass it into `FlatFileItemReader`:

```java
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.mapping.DefaultLineMapper;
import org.springframework.batch.item.file.transform.DelimitedLineTokenizer;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.core.io.FileSystemResource;

DelimitedLineTokenizer tokenizer = new DelimitedLineTokenizer();
tokenizer.setDelimiter(",");
tokenizer.setNames(
        "order_id",
        "customer_id",
        "amount",
        "quantity",
        "business_date");
tokenizer.setStrict(true);

DefaultLineMapper<Order> lineMapper = new DefaultLineMapper<>();
lineMapper.setLineTokenizer(tokenizer);
lineMapper.setFieldSetMapper(new OrderFieldSetMapper());

FlatFileItemReader<Order> reader =
        new FlatFileItemReaderBuilder<Order>()
                .name("orderReader")
                .resource(new FileSystemResource("/data/in/orders.csv"))
                .encoding("UTF-8")
                .linesToSkip(1)
                .lineMapper(lineMapper)
                .saveState(true)
                .build();
```

In a Spring application, declare the reader as a `@StepScope` bean if the resource or tokenizer settings depend on `JobParameters`. The example above uses a fixed path to illustrate how `LineTokenizer` and `FieldSetMapper` connect.

## 14. Handling mapping errors and invalid data

Common errors when mapping a `FieldSet`:

- Field count does not match the layout.
- Field name is wrong or missing.
- Numeric string contains invalid characters.
- Date does not match the expected format.
- Enum contains an unsupported value.
- Required field is empty.
- Value exceeds the representable range of the target type.

Errors can be handled by:

1. Failing the Step if bad data compromises the integrity of the entire file.
2. Skipping faulty lines if business rules allow omitting some records within a limit.
3. Writing a reject record with line number, source file, offending value, and reason.
4. Using a validation Step to verify headers/schema before importing.

When configuring skip, choose specific exceptions. For example, `InvalidOrderException` for line-level business errors; file configuration errors or missing headers may need to fail the Job rather than skipping rows en masse.

`FlatFileParseException` can provide line information and source content when line mapping fails. Consider sensitive data policies before writing entire raw file lines into logs or reject tables.

## 15. Common pitfalls

| Pitfall | Cause | Mitigation |
|---|---|---|
| Using indices when column order changes | Mapper reads the wrong field without necessarily throwing an error. | Name fields in the tokenizer and read by name. |
| Converting order codes to numbers | Loses leading zeros or alphanumeric formatting. | Keep identifiers as `String`. |
| Using `double` for currency | Floating-point precision rounding errors. | Use `BigDecimal`. |
| Using default date formats | Behavior depends on environment locale or defaults. | Parse with an explicit `DateTimeFormatter`. |
| Using `split(",")` for CSV | Fails on quoted fields containing commas or quotes. | Use `DelimitedLineTokenizer` or a CSV library. |
| Treating the string `NULL` as null by default | Source convention is not verified. | Agree on null markers and normalize in the mapper. |
| Converting empty fields directly to primitives | Can cause parse failures or lose null vs. 0 distinction. | Read `String`, check emptiness, and convert to wrapper types if needed. |
| BeanWrapper fails to map properties | Field names mismatch or JavaBean lacks matching setters/constructor. | Check property names or use a custom `FieldSetMapper`. |
| Ignoring all mapping errors | Bad data can be silently hidden. | Classify exceptions, bound skip limits, and log rejects. |

## Conclusion

`FieldSet` represents the values split from a file line by `LineTokenizer`; `FieldSetMapper` converts them into a business object. You can read by name or index, use `readInt`, `readLong`, `readBigDecimal`, and corresponding typed methods, or parse manually when specific formats are required. `BeanWrapperFieldSetMapper` works well for JavaBeans with matching properties, while custom mappers give full control over dates, locales, enums, nulls, and validation. Keep identifiers as `String` when leading zeros matter, use `BigDecimal` for currency, declare formats explicitly, and classify mapping errors under clear fail/skip policies so file data is converted accurately.
