# Mapping an input model to an output model

In Spring Batch, `ItemProcessor` is commonly used to convert an item that was just read into an item whose structure fits the write step. This is where an application can **map an input model to an output model**: receive data in the source's format, validate and normalize it, and then produce an output model that fits the business or the target system.

For example, a CSV file contains `customer_code`, `first_name`, `last_name`, `birth_date`, and `status`. The reader maps each line to `CustomerInput`. The processor converts it into a `CustomerRecord` with a full name, a birth date of type `LocalDate`, an enum status, and normalized fields. The writer then writes the `CustomerRecord` to the database.

Mapping is not just copying field names. It must also define the type-conversion rules, handle missing values, normalize data, check business conditions, and decide which items are passed on.

## 1. The input model and the output model play different roles

The two models represent two different boundaries in the pipeline:

- The **input model** describes the data the reader receives from the source. Its structure usually depends on CSV, JSON, XML, a database, or an API.
- The **output model** describes the data the processor provides to the writer. Its structure usually depends on business rules or the schema of the target system.

For example:

| Input model (`CustomerInput`) | Output model (`CustomerRecord`) |
|---|---|
| `customer_code: String` | `customerId: Long` |
| `first_name: String` | `fullName: String` |
| `last_name: String` | `fullName: String` |
| `birth_date: String` | `birthDate: LocalDate` |
| `status: String` | `status: CustomerStatus` |
| `country_code: String` | `country: Country` or a normalized country code |

The input model may contain raw data such as date strings or status codes. The output model should represent the data after conversion to the types and rules the target system expects.

Keeping the two models separate helps the application avoid depending directly on the structure of the input file. If a partner changes the column names or the date format, you can adjust the reader or the mapping without necessarily changing the entire business model and the writer.

## 2. ItemProcessor is the natural place for mapping

Spring Batch defines `ItemProcessor<I, O>` with an input type `I` and an output type `O`:

```java
public interface ItemProcessor<I, O> {
    O process(I item) throws Exception;
}
```

The two type parameters can differ. For example:

```java
ItemProcessor<CustomerInput, CustomerRecord> processor;
```

This means the reader supplies `CustomerInput`, the processor creates `CustomerRecord`, and the writer receives the `CustomerRecord`s.

Data flow:

```mermaid
flowchart LR
    A[CSV / JSON / Database] --> B[ItemReader]
    B --> C[CustomerInput]
    C --> D[ItemProcessor]
    D --> E[Validate and map]
    E --> F[CustomerRecord]
    F --> G[ItemWriter]
    G --> H[Database / Output file]
```

The processor is called for each item. It can return the mapped output, return `null` to filter the item, or throw an exception to signal an error. Whichever decision is used must reflect the business meaning accurately.

## 3. Example input model and output model

You can use Java records to represent immutable data models if the application's Java version supports them:

```java
public record CustomerInput(
        String customerCode,
        String firstName,
        String lastName,
        String birthDate,
        String status,
        String countryCode) {
}

public record CustomerRecord(
        Long customerId,
        String fullName,
        LocalDate birthDate,
        CustomerStatus status,
        String countryCode) {
}

public enum CustomerStatus {
    ACTIVE,
    INACTIVE,
    SUSPENDED
}
```

`CustomerInput` keeps the data close to the source format. `CustomerRecord` uses more specific types to represent the data after conversion. If the project uses an older Java version, you can replace the record with a class that has a constructor, getters, and the necessary methods.

## 4. Manual mapping in ItemProcessor

For simple mapping, you can write it directly in the processor. This approach is easy to read and suitable when the conversion rules involve few fields.

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

import org.springframework.batch.item.ItemProcessor;
import org.springframework.stereotype.Component;

@Component
public class CustomerProcessor
        implements ItemProcessor<CustomerInput, CustomerRecord> {

    private static final DateTimeFormatter DATE_FORMAT =
            DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT);

    @Override
    public CustomerRecord process(CustomerInput input) {
        if (input == null) {
            throw new IllegalArgumentException("Customer input is required");
        }

        String customerCode = requireText(input.customerCode(), "customerCode");
        Long customerId = Long.valueOf(customerCode);

        String fullName = normalizeName(input.firstName(), input.lastName());
        LocalDate birthDate = LocalDate.parse(input.birthDate(), DATE_FORMAT);
        CustomerStatus status = CustomerStatus.valueOf(
                input.status().trim().toUpperCase(Locale.ROOT));

        return new CustomerRecord(
                customerId,
                fullName,
                birthDate,
                status,
                normalizeCountryCode(input.countryCode())
        );
    }

    private String requireText(String value, String fieldName) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(fieldName + " is required");
        }
        return value.trim();
    }

    private String normalizeName(String firstName, String lastName) {
        String first = firstName == null ? "" : firstName.trim();
        String last = lastName == null ? "" : lastName.trim();
        return (first + " " + last).trim().replaceAll("\\s+", " ");
    }

    private String normalizeCountryCode(String countryCode) {
        return countryCode == null
                ? null
                : countryCode.trim().toUpperCase(Locale.ROOT);
    }
}
```

The code snippet illustrates converting a string to a number, joining names, parsing a date, and converting a status to an enum. In a real application, you need to clearly define the input data format and the business rules. For example, only convert `customerCode` to `Long` if the customer code is truly numeric and there is no need to preserve leading zeros.

The advantage of manual mapping is clear control and no extra library. However, if the model has many nested fields or many shared mappings, the processor can become long and hard to maintain. In that case you should extract the mapping into a separate mapper.

## 5. Extracting the mapping into a separate mapper

A processor should orchestrate the processing steps for an item. The conversion logic can be extracted into a mapper component to make it easier to test and reuse.

```java
public interface CustomerMapper {
    CustomerRecord toRecord(CustomerInput input);
}
```

A manual implementation:

```java
@Component
public class DefaultCustomerMapper implements CustomerMapper {

    @Override
    public CustomerRecord toRecord(CustomerInput input) {
        Long customerId = Long.valueOf(input.customerCode().trim());
        String fullName = (input.firstName() + " " + input.lastName()).trim();
        LocalDate birthDate = LocalDate.parse(input.birthDate());
        CustomerStatus status = CustomerStatus.valueOf(
                input.status().trim().toUpperCase(Locale.ROOT));

        return new CustomerRecord(
                customerId,
                fullName,
                birthDate,
                status,
                input.countryCode());
    }
}
```

A processor that uses the mapper:

```java
@Component
public class CustomerProcessor
        implements ItemProcessor<CustomerInput, CustomerRecord> {

    private final CustomerMapper mapper;

    public CustomerProcessor(CustomerMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public CustomerRecord process(CustomerInput input) {
        validate(input);
        return mapper.toRecord(input);
    }

    private void validate(CustomerInput input) {
        if (input == null || input.customerCode() == null
                || input.customerCode().isBlank()) {
            throw new IllegalArgumentException("Missing customer code");
        }
    }
}
```

In this structure, the processor decides the processing flow and calls the mapper to convert. The mapper focuses on creating the output model. You can swap the mapper implementation without rewriting the whole processor.

## 6. Using MapStruct for mapping many fields

For a large model or many repeated mappings, you can use a mapping library such as MapStruct. MapStruct generates mapping code at compile time, which avoids having to write many manual assignment statements.

For example:

```java
import org.mapstruct.Mapper;
import org.mapstruct.Mapping;

@Mapper(componentModel = "spring")
public interface CustomerMapStructMapper {

    @Mapping(target = "customerId", source = "customerCode")
    @Mapping(target = "fullName", expression = "java(joinName(input))")
    @Mapping(target = "birthDate", source = "birthDate", dateFormat = "dd/MM/yyyy")
    @Mapping(target = "status", source = "status")
    @Mapping(target = "countryCode", source = "countryCode")
    CustomerRecord toRecord(CustomerInput input);

    default String joinName(CustomerInput input) {
        String first = input.firstName() == null ? "" : input.firstName().trim();
        String last = input.lastName() == null ? "" : input.lastName().trim();
        return (first + " " + last).trim().replaceAll("\\s+", " ");
    }
}
```

The example above illustrates how to declare a mapping. When using MapStruct with enums, numeric types, dates, or records, you need to configure conversions that suit the model and the library version. If there is a complex business rule, put that rule in its own method instead of trying to cram it into an annotation.

Advantages of MapStruct:

- The mapping code is generated at compile time.
- Many type mismatches are detected at build time.
- It supports mapping nested objects, collections, and differing field names.
- It reduces the amount of repetitive assignment code in an application with many models.

The trade-off is that the project needs to configure an annotation processor and manage an additional dependency. For small mappings, writing a manual mapper may be simpler.

## 7. Mapping data types and normalizing values

The hard part of mapping is usually converting raw data into the correct, consistent target type.

### String to number

If the input contains a number as a string, you need to check the format before parsing. For example, `"00125"` may be an identifier that must be preserved, while `"125"` may be a quantity to be computed with.

Do not parse all numeric fields into `Long` or `Double` out of habit. Determine the meaning of the field before choosing the type.

### String to date

The input date needs a clear format. `15/11/2026` and `11/15/2026` can be interpreted differently. Use `DateTimeFormatter` with a defined pattern and locale, and avoid depending on the JVM's default locale.

If the output model stores a calendar date, `LocalDate` is usually more suitable than `Date`. If the data represents a point in time, you need to parse the offset or timezone according to the data contract.

### String to enum

Status values should be normalized before calling `Enum.valueOf`, for example trimmed and converted to uppercase using `Locale.ROOT`. You need to specify how to handle an unrecognized value: a data error, a default status, or a record to be quarantined.

### Decimal numbers and currency

Do not use `Double` for monetary calculations that need decimal precision. Use `BigDecimal` and define the scale and rounding mode according to business rules. If the input uses a comma as the decimal separator, you need to parse by locale or by the specified format, not replace characters arbitrarily.

### Null and default values

Do not automatically convert every `null` to an empty string or 0. `null`, an empty string, and the value 0 can carry different meanings. The output model needs to express clearly which fields are required, which can be absent, and which have default values permitted by the business.

## 8. Validation before and during mapping

Mapping usually goes together with validation, but the two have different goals:

- **Validation** determines whether the input satisfies the necessary conditions.
- **Mapping** converts valid input into the output model.

For example, `customerCode` must have a value, `birthDate` must be in the correct format, `status` must be in the allowed list, and `countryCode` must follow a standard that the target system accepts.

You can use Bean Validation (`jakarta.validation`) on the input model or write a dedicated validator. If validation fails, the application needs to decide:

1. Throw an exception so the step fails.
2. Configure that exception as skippable so the item is ignored and processing continues.
3. Create a separate output/rejection record to record the bad data in a clearly designed flow.

You should not return `null` just because the data is invalid. In Spring Batch, a processor returning `null` means **filter the item**, not report an error. If you want to ignore it because of an exception, use the skip policy; if you want to store the error, build a dedicated error-recording mechanism.

## 9. Filtering items during mapping

`ItemProcessor` can return `null` when the input is valid but falls outside the scope to be processed.

For example, a job exports only active customers:

```java
@Override
public CustomerRecord process(CustomerInput input) {
    if ("INACTIVE".equalsIgnoreCase(input.status())) {
        return null;
    }

    return mapper.toRecord(input);
}
```

A filtered item:

- Has been read by the reader.
- Is not passed to the writer.
- Is reflected in the `filterCount` of `StepExecution`.
- Does not increase the skip count merely because the processor returned `null`.

If the reason for dropping an item needs to be audited, record the identifier and the filter reason through an appropriate logging or audit mechanism. You should not use an exception for an ordinary data-dropping condition unless necessary.

## 10. Configuring the processor in a chunk-oriented step

In Spring Batch 5, a step can declare the input and output types explicitly:

```java
@Bean
public Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> customerReader,
        ItemProcessor<CustomerInput, CustomerRecord> customerProcessor,
        ItemWriter<CustomerRecord> customerWriter) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<CustomerInput, CustomerRecord>chunk(500, transactionManager)
            .reader(customerReader)
            .processor(customerProcessor)
            .writer(customerWriter)
            .build();
}
```

The generic types at `.<CustomerInput, CustomerRecord>chunk(...)` determine the reader's input type and the processor/writer's output type. If the reader, processor, or writer does not match in type, the error is usually detected at compile time or when the bean is configured.

A processor is not needed if the input data already has the exact type and structure the writer needs. However, if you need mapping, validation, or enrichment, the processor is the appropriate place to do it before writing.

## 11. Multi-step mapping with CompositeItemProcessor

When processing has multiple stages, you can split it into small processors and chain them with `CompositeItemProcessor`.

An example pipeline:

1. Normalize strings and input codes.
2. Check business rules.
3. Map to the output model.
4. Enrich the output with reference data.

Chained processors need the output type of the previous step to match the input type of the next step.

```java
ItemProcessor<CustomerInput, CustomerInput> normalizer;
ItemProcessor<CustomerInput, CustomerInput> validator;
ItemProcessor<CustomerInput, CustomerRecord> mapper;

CompositeItemProcessor<CustomerInput, CustomerRecord> processor =
        new CompositeItemProcessor<>();
processor.setDelegates(List.of(normalizer, validator, mapper));
```

This is an example of the type relationships between delegates. In a real Spring configuration, you should declare the composite processor as a bean and configure the delegate list according to the Spring Batch version in use.

Splitting processors gives each component a small responsibility and makes it easy to test. However, you should not divide into too many classes just to turn every field assignment into its own component. Split along meaningful processing boundaries.

## 12. How does enrichment differ from mapping?

Mapping converts structure or data types from input to output. Enrichment adds data from another source so the output is more complete.

For example:

- The input has `productCode`; the processor looks up the product name and group from a reference table.
- The input has `branchId`; the processor adds the branch's region information.
- The input has `countryCode`; the processor converts the code into the standard country name.

Enrichment may need to call a database or service. Take care to avoid N+1 queries: if each item creates its own query, the job can be slow with large data. You can use a bounded cache, preload reference data in groups, join directly in the reader, or use batch lookups.

If enrichment depends on data that can change while the job runs, you need to determine which snapshot the job uses. The same input processed again after a restart should not unexpectedly receive a different set of reference data if that changes the business result.

## 13. Keeping the processor stateless and safe under parallel execution

A processor should usually be a stateless component: it does not hold per-item changing state in fields of a singleton bean. Spring may reuse the same processor for multiple items, step executions, or processing threads depending on the configuration.

You should:

- Use local variables for the current item's data.
- Inject a mapper or service whose behavior is safe for the chosen execution mode.
- Avoid holding `currentCustomer`, a mutable counter, or a shared result list in a processor field.
- If you need a cache, choose a thread-safe cache that is bounded and has an appropriate expiration policy.
- Do not write side effects that cannot be safely repeated in the processor if the step may retry the item.

When the step runs with multiple threads, the processor can be called concurrently. Pure mapping from input to output is usually easier to make thread-safe. If the processor accesses external resources, you need to control concurrency, timeouts, and idempotency.

## 14. Testing the mapping independently of the job

A mapper and a processor can be tested with unit tests without launching the whole job.

An example of testing a mapper:

```java
@Test
void mapsInputToCustomerRecord() {
    CustomerInput input = new CustomerInput(
            "1205", "An", "Nguyen", "15/11/1995", "active", "vn");

    CustomerRecord result = mapper.toRecord(input);

    assertEquals(1205L, result.customerId());
    assertEquals("An Nguyen", result.fullName());
    assertEquals(LocalDate.of(1995, 11, 15), result.birthDate());
    assertEquals(CustomerStatus.ACTIVE, result.status());
    assertEquals("VN", result.countryCode());
}
```

Cases that should be tested:

- Valid values and normal mapping.
- A required field that is missing or contains only whitespace.
- A badly formatted date string or a nonexistent date.
- An unrecognized enum.
- A code with leading zeros or one that exceeds the numeric type's range.
- Decimal values in different locales.
- The filter rule returns `null` in the right cases.
- Mapping of nested objects or collections if the output has a nested structure.

Unit tests help detect conversion errors early. A step integration test is still necessary when you want to confirm that the reader, processor, writer, and transaction work together correctly, but that testing responsibility lies outside the pure mapping logic.

## 15. Common mistakes when mapping input to output

| Situation | Cause | How to handle it |
|---|---|---|
| Output is missing a field | The mapper forgot to map it or the source has no value | Determine the required fields and write the mapping explicitly |
| Date parsing fails | The input format is inconsistent | Use an explicit formatter and validate before parsing |
| Leading zeros in a code are lost | An identifier was converted to a numeric type | Keep the code as a `String` |
| Wrong monetary amount | `Double` was used for financial calculations | Use `BigDecimal` with an explicit scale and rounding mode |
| An item does not reach the writer but there is no exception | The processor returned `null` | Check the filter rules and `filterCount` |
| The job stops because of one bad record | The exception is not in the skip policy | Decide which errors must fail and which can be skipped or quarantined |
| Results differ between runs | Enrichment reads changing reference data or the mapping depends on the environment | Pin the snapshot and the normalization rules |
| Errors when running with multiple threads | The processor or mapper uses shared mutable state | Design it to be stateless or synchronize resources appropriately |
| Mapping is too hard to maintain | Parse, validate, filter, and enrichment logic is crammed into one method | Split responsibilities into meaningful steps |

## 16. End-to-end example: converting customer data

A CSV file has these columns:

```csv
customer_code,first_name,last_name,birth_date,status,country_code
00125,An,Nguyen,15/11/1995,ACTIVE,VN
00126,Binh,Tran,02/03/1990,INACTIVE,VN
00127,Chi,Le,31/02/1998,ACTIVE,VN
```

The reader maps each line to `CustomerInput`. The processor performs these tasks:

1. Normalize whitespace and the country code.
2. Validate required fields.
3. Convert the birth date to `LocalDate`.
4. Convert the status to an enum.
5. Create a `CustomerRecord` with the fields the writer needs.
6. Filter out `INACTIVE` customers if the business requirement is to import only active customers.

In this example, `customer_code` has leading zeros, so it must be kept as a `String` if the zeros are part of the code. The date `31/02/1998` is invalid; the processor can throw an exception so the step applies the skip policy or fails as required. An `INACTIVE` record can be filtered by returning `null`.

The output model could be:

```java
public record CustomerRecord(
        String customerCode,
        String fullName,
        LocalDate birthDate,
        CustomerStatus status,
        String countryCode) {
}
```

The writer receives only the `CustomerRecord`s that the processor returns. As a result, the writer does not need to understand the CSV structure, how names are joined, or the raw date format.

## 17. Principles to remember

- The input model represents the data the reader receives; the output model represents the data the writer needs.
- `ItemProcessor<I, O>` allows the input and output to have different types.
- Mapping can include renaming fields, changing types, normalizing, validating, and creating nested structures.
- Extract a separate mapper when the conversion logic needs reuse or involves many fields.
- Use MapStruct or a similar tool for large mappings; write it manually when the mapping is simple and you need direct control.
- `null` from the processor means filtering the item; data errors need an exception/skip or a separate recording flow.
- Choose data types by meaning: keep identifiers with leading zeros as strings, use `LocalDate` for calendar dates, and `BigDecimal` for currency.
- Enrichment needs control over queries, caching, snapshots, and re-runnability.
- A processor should be stateless or thread-safe when the step runs in parallel; avoid holding per-item changing state in shared fields.
- Test the mapper and processor independently to detect conversion errors before running a large job.

Mapping an input model to an output model separates the source format from the model the target system needs. When mapping is placed in `ItemProcessor`, the application has a clear point to normalize, validate, and convert each item before writing, while keeping the reader and writer focused on reading and writing data.
