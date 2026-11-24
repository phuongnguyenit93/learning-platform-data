# FixedLengthTokenizer

In Spring Batch, `FixedLengthTokenizer` is used to split a line of text whose fields lie at fixed positions. Unlike comma- or tab-delimited files, fixed-width files do not require a delimiter character between columns. The start and end positions of each field are described using `Range` instances.

The tokenizer converts a line into a `FieldSet`. Afterward, `FieldSetMapper` converts the extracted values into a business object. This component is commonly used with `FlatFileItemReader` and `DefaultLineMapper` to read legacy files, banking interchange files, mainframe exports, or systems using fixed-width record formats.

## 1. What is a fixed-width file?

A fixed-width file (fixed-length record) is a file where each field occupies a predefined range of positions within a data line. For example, a 60-character employee record:

| Field | Start position | End position | Length |
|---|---:|---:|---:|
| `employeeId` | 1 | 8 | 8 |
| `lastName` | 9 | 28 | 20 |
| `firstName` | 29 | 43 | 15 |
| `hireDate` | 44 | 51 | 8 |
| `salary` | 52 | 60 | 9 |

Illustration of how a line is split:

```text
12345678NGUYEN VAN A        ANH            20261115000012500
|------|--------------------|---------------|--------|---------|
   ID          Last name        First name     Date     Salary
  1-8             9-28             29-43       44-51    52-60
```

In this example, there are no commas or tabs separating fields. The reader must know the exact position of every field. If a single position is misconfigured, the remainder of the record may be parsed incorrectly even though the line still appears valid.

## 2. Role of FixedLengthTokenizer

`FixedLengthTokenizer` implements `LineTokenizer`. It receives a `String` line, slices the line according to the configured ranges, and returns a `FieldSet` containing the fields in matching order.

The typical processing flow looks like this:

```text
FlatFileItemReader
       |
       | read a line
       v
DefaultLineMapper
       |
       v
FixedLengthTokenizer
       |
       | slice by Range
       v
FieldSet
       |
       v
FieldSetMapper
       |
       | convert types and map
       v
Domain object
```

The components have distinct responsibilities:

| Component | Responsibility |
|---|---|
| `FlatFileItemReader` | Reads lines from the resource, manages encoding, headers, comments, and reader state. |
| `DefaultLineMapper` | Combines the tokenizer with the mapper to convert a line into an object. |
| `FixedLengthTokenizer` | Splits a line into fields by fixed positions. |
| `Range` | Describes the start and end position of a field. |
| `FieldSet` | Provides APIs to read values by name or index and perform type conversion. |
| `FieldSetMapper` | Converts a `FieldSet` into a business object. |

The tokenizer is only responsible for slicing fields. It does not inherently know whether `employeeId` exists in the system, whether a date is valid under business rules, or whether salary falls within an allowed range. Those checks belong to the mapper, processor, or validator.

## 3. Declaring Ranges

`Range` represents the position of a field in a line. `Range` positions are 1-based and the end bound is inclusive.

Examples:

```java
new Range(1, 8)   // characters from position 1 to 8
new Range(9, 28)  // characters from position 9 to 28
new Range(29, 43) // characters from position 29 to 43
```

Field length is calculated as:

\[
\text{length} = \text{end} - \text{start} + 1
\]

Thus `new Range(1, 8)` has length 8, not 7. This is a common configuration mistake when translating 1-based position specifications into Java's 0-based index arithmetic.

A `Range` can also be declared with only a start position without an end position, such as `new Range(21)`, to represent a field extending from position 21 to the end of the line. Only use an open range when the source format genuinely defines a variable-length trailing field.

## 4. Basic FixedLengthTokenizer configuration

A basic tokenizer needs two primary settings:

- `setColumns(...)`: list of ranges in the order the fields appear on the line.
- `setNames(...)`: corresponding field names in the `FieldSet`.

Example:

```java
FixedLengthTokenizer tokenizer = new FixedLengthTokenizer();
tokenizer.setNames("employeeId", "lastName", "firstName", "hireDate", "salary");
tokenizer.setColumns(
        new Range(1, 8),
        new Range(9, 28),
        new Range(29, 43),
        new Range(44, 51),
        new Range(52, 60));
tokenizer.setStrict(true);
```

The order in `setNames` must match the order in `setColumns`. The first field is sliced from the first range and assigned the first name, the second field gets the second name, and so on.

When defining ranges, verify:

- The number of field names equals the number of ranges.
- Start and end positions match the file specification.
- Ranges are ordered as they appear in the record.
- Ranges do not accidentally overlap.
- No required positions are omitted.
- Skipped gaps are strictly padding or unused fields according to the specification.

If a file contains a reserved/padding segment that does not need mapping, you can omit declaring a range for it as long as subsequent field positions are still calculated using the file's original offsets.

## 5. Complete example with FlatFileItemReader

Assume an employee file has the fields `employeeId`, `lastName`, `firstName`, `hireDate`, and `salary`, with lengths 8, 20, 15, 8, and 9 characters respectively.

Define the domain object:

```java
public record Employee(
        String employeeId,
        String lastName,
        String firstName,
        LocalDate hireDate,
        BigDecimal salary) {
}
```

Declare the `LineMapper`:

```java
@Bean
LineMapper<Employee> employeeLineMapper() {
    FixedLengthTokenizer tokenizer = new FixedLengthTokenizer();
    tokenizer.setNames(
            "employeeId", "lastName", "firstName", "hireDate", "salary");
    tokenizer.setColumns(
            new Range(1, 8),
            new Range(9, 28),
            new Range(29, 43),
            new Range(44, 51),
            new Range(52, 60));
    tokenizer.setStrict(true);

    DefaultLineMapper<Employee> lineMapper = new DefaultLineMapper<>();
    lineMapper.setLineTokenizer(tokenizer);
    lineMapper.setFieldSetMapper(fieldSet -> new Employee(
            fieldSet.readString("employeeId").trim(),
            fieldSet.readString("lastName").trim(),
            fieldSet.readString("firstName").trim(),
            LocalDate.parse(
                    fieldSet.readString("hireDate").trim(),
                    DateTimeFormatter.BASIC_ISO_DATE),
            new BigDecimal(fieldSet.readString("salary").trim())));
    return lineMapper;
}
```

Declare the reader:

```java
@Bean
@StepScope
FlatFileItemReader<Employee> employeeReader(
        @Value("#{jobParameters['inputFile']}") String inputFile,
        LineMapper<Employee> employeeLineMapper) {

    return new FlatFileItemReaderBuilder<Employee>()
            .name("employeeReader")
            .resource(new FileSystemResource(inputFile))
            .encoding("UTF-8")
            .linesToSkip(1)
            .lineMapper(employeeLineMapper)
            .saveState(true)
            .build();
}
```

The reader skips the first line if the file has a header. If the file has no header, remove `.linesToSkip(1)`. `@StepScope` allows resolving `inputFile` from `JobParameters` when the step begins.

The example above assumes salary is stored as digits and dates as `yyyyMMdd`. If the file includes signs, decimal points, grouping separators, or another date convention, the mapper must parse according to the source format.

## 6. FixedLengthTokenizer and FieldSetMapper

The tokenizer only slices strings. Converting strings into data types and constructing the domain object belongs to `FieldSetMapper`.

Example extracting the mapper into a separate class:

```java
public class EmployeeFieldSetMapper implements FieldSetMapper<Employee> {

    private static final DateTimeFormatter DATE_FORMAT =
            DateTimeFormatter.BASIC_ISO_DATE;

    @Override
    public Employee mapFieldSet(FieldSet fieldSet) {
        String employeeId = fieldSet.readString("employeeId").trim();
        String lastName = fieldSet.readString("lastName").trim();
        String firstName = fieldSet.readString("firstName").trim();

        LocalDate hireDate = LocalDate.parse(
                fieldSet.readString("hireDate").trim(), DATE_FORMAT);
        BigDecimal salary = new BigDecimal(
                fieldSet.readString("salary").trim());

        return new Employee(employeeId, lastName, firstName, hireDate, salary);
    }
}
```

Then configure it:

```java
lineMapper.setFieldSetMapper(new EmployeeFieldSetMapper());
```

Separating the mapper is beneficial when conversion rules are complex, require independent testing, or are shared across multiple readers. For simple mappings, a lambda can be more concise.

### Handling whitespace

Fixed-width fields are usually padded with spaces. For example, a full name field might contain `"NGUYEN VAN A        "`. Explicitly determine whether leading/trailing whitespace should be preserved or stripped.

- Use `.trim()` if whitespace is purely padding and carries no data meaning.
- Use `strip()` when you also want to handle additional Unicode whitespace characters in modern Java.
- Do not trim automatically if whitespace is a valid part of the source data.
- For zero-padded code fields, do not strip leading zeros if they are part of the identifier.

Do not rely on the tokenizer to normalize every field. Perform normalization in the mapper so the rules are explicit and testable.

## 7. Strict mode and record length

`FixedLengthTokenizer` has a strict property. When strict is enabled, the tokenizer checks record length against the declared ranges and raises a format error if a line does not meet the expected length.

```java
tokenizer.setStrict(true);
```

For instance, if the final range ends at position 60, a record shorter than required cannot supply enough data for the defined fields. `IncorrectLineLengthException` is the type of error encountered when line length violates strict configuration.

When `strict` is disabled:

```java
tokenizer.setStrict(false);
```

The tokenizer relaxes length checking. Trailing fields may be short or lack the expected number of characters, depending on the range and the specific version's implementation. Therefore, the mapper must check for missing data before parsing or writing to the database.

Keep strict mode enabled for files with a clear length specification. Only disable strict mode when the source genuinely permits short records or variable lengths and the application has rules to handle missing parts.

### Distinguishing the two strict properties

There are two settings that are easy to confuse:

| Setting | Meaning |
|---|---|
| `FixedLengthTokenizer.setStrict(...)` | Checks line length against the tokenizer's ranges. |
| `FlatFileItemReaderBuilder.strict(...)` | Checks whether the input resource exists/is readable according to the reader's rules. |

Example:

```java
tokenizer.setStrict(true); // Validate fixed-width structure of each line.

return new FlatFileItemReaderBuilder<Employee>()
        .name("employeeReader")
        .resource(resource)
        .strict(true) // Validate resource per reader strict mode.
        .lineMapper(lineMapper)
        .build();
```

These two properties check different things. An existing resource does not guarantee every line has a valid length; conversely, a properly configured tokenizer still cannot read if the file does not exist.

## 8. Ranges with gaps and unused fields

A record may contain reserved or padding fields that the application does not need to map. Example:

| Field | Positions |
|---|---:|
| `accountId` | 1-10 |
| reserved | 11-15 |
| `accountName` | 16-40 |
| `status` | 41-41 |

You can declare only the ranges you need to read:

```java
tokenizer.setNames("accountId", "accountName", "status");
tokenizer.setColumns(
        new Range(1, 10),
        new Range(16, 40),
        new Range(41, 41));
```

The tokenizer extracts the exact specified positions. The reserved span 11-15 is omitted from the FieldSet. Positions of subsequent fields must still be calculated from the original record positions, never compacted as if the reserved section did not exist.

If there are multiple skipped spans, document them clearly against the file specification. Avoid altering ranges just to make code look contiguous, as that will shift the offsets of subsequent fields.

## 9. Open ranges for the trailing field

If the last field occupies the entire remainder of the line, you can use a range with only a start position:

```java
tokenizer.setNames("recordType", "recordId", "description");
tokenizer.setColumns(
        new Range(1, 2),
        new Range(3, 12),
        new Range(13));
```

Here `description` starts at position 13 and runs to the end of the line. Open ranges are useful when the description varies in length while preceding fields stay at fixed positions.

When using an open range, verify minimum record length to ensure the trailing field is not unintentionally empty. Strict validation should also be verified against open-range semantics and your specific Spring Batch version.

## 10. Encoding and the meaning of width

This is an important consideration when reading fixed-width files from legacy systems. `FixedLengthTokenizer` operates on the `String` line already decoded by the reader, then slices by character positions of the Java string. It does not slice directly by file bytes.

If the source specification defines widths in characters, this usually aligns well. However, if the specification defines widths in bytes—especially with multi-byte encodings—byte offsets can differ from character positions after decoding.

For example:

- ASCII or certain single-byte encodings: one character typically maps to one byte.
- UTF-8: a character may occupy multiple bytes.
- Legacy encodings such as EBCDIC: the correct charset must be chosen when reading.

Configure `.encoding(...)` to match the file's charset. If the file defines fixed widths in bytes, verify the encoding and decoding strategy before using a character-position tokenizer. You may need to read/decode along byte boundaries or convert the file to a canonical format before tokenizing.

With Unicode, Java `String` uses UTF-16; a character outside the Basic Multilingual Plane can take two code units. If the specification counts Unicode code points or bytes, you cannot assume `String.substring` indices match the specification's positions. Test with real data containing multi-byte/non-BMP characters if the source permits them.

## 11. Negative signs, decimals, and date formats

The tokenizer returns fields as text. Conventions such as negative signs, decimal points, implied decimals, grouping separators, or dates must be handled in the mapper.

For example, a file has a 9-character amount where the last two digits represent an implied decimal fraction:

```text
000012345
```

If the specification defines the value as 123.45, the mapper must convert according to that rule:

```java
String raw = fieldSet.readString("amount").trim();
BigDecimal amount = new BigDecimal(raw).movePointLeft(2);
```

If the file places a `-` sign at the start or end of the field, parse with a custom format and check for empty fields. Do not call `new BigDecimal(...)` directly if the source includes grouping characters or non-standard formats.

For `yyyyMMdd` dates, you can use:

```java
LocalDate date = LocalDate.parse(
        fieldSet.readString("hireDate").trim(),
        DateTimeFormatter.BASIC_ISO_DATE);
```

If a date has an invalid format, the mapper can throw an exception. In a chunk step, the application can configure skip for specific data errors if business rules allow; configuration or file-wide errors should not be skipped indiscriminately.

## 12. Handling headers, comments, and blank lines

`FixedLengthTokenizer` only processes lines forwarded to it. Skipping headers, comments, or blank lines belongs to `FlatFileItemReader` configuration.

Example:

```java
return new FlatFileItemReaderBuilder<Employee>()
        .name("employeeReader")
        .resource(resource)
        .linesToSkip(1)
        .comments("#")
        .lineMapper(lineMapper)
        .build();
```

- `linesToSkip(1)` skips the first line, typically used for the header.
- `comments("#")` marks comment prefixes per reader configuration.
- Blank lines must be handled according to file requirements and appropriate reader/mapper settings.

Do not use ranges to try to skip headers or comments. Handle them in the reader so the tokenizer receives only business records.

## 13. Combining FixedLengthTokenizer with BeanWrapperFieldSetMapper

If field names in `FieldSet` match properties of a Java bean, `BeanWrapperFieldSetMapper` can be used for automatic binding.

Example:

```java
@Bean
FieldSetMapper<EmployeeInput> employeeFieldSetMapper() {
    BeanWrapperFieldSetMapper<EmployeeInput> mapper =
            new BeanWrapperFieldSetMapper<>();
    mapper.setTargetType(EmployeeInput.class);
    return mapper;
}
```

The tokenizer must assign field names matching the writable properties of the target object:

```java
tokenizer.setNames("employeeId", "lastName", "firstName", "hireDate", "salary");
```

The bean must fit the property binding mechanism—typically having a default constructor and setters for properties, or a compatible mapper configuration. A conversion service can be configured if Strings need conversion to `LocalDate`, `BigDecimal`, or enums in custom formats.

If the target is a Java record or requires complex mapping, a hand-written `FieldSetMapper` is usually easier to control. Do not assume BeanWrapper automatically understands every custom date or number format in the file.

## 14. Testing the tokenizer in isolation

You can test `FixedLengthTokenizer` without creating a Job or database. Test sample lines directly and assert each field:

```java
class EmployeeTokenizerTest {

    private FixedLengthTokenizer createTokenizer() {
        FixedLengthTokenizer tokenizer = new FixedLengthTokenizer();
        tokenizer.setNames(
                "employeeId", "lastName", "firstName", "hireDate", "salary");
        tokenizer.setColumns(
                new Range(1, 8),
                new Range(9, 28),
                new Range(29, 43),
                new Range(44, 51),
                new Range(52, 60));
        tokenizer.setStrict(true);
        return tokenizer;
    }

    @Test
    void extractsFieldsByPosition() {
        String line = "12345678NGUYEN VAN A        ANH            20261115000012500";

        FieldSet fields = createTokenizer().tokenize(line);

        assertThat(fields.readString("employeeId")).isEqualTo("12345678");
        assertThat(fields.readString("lastName").trim()).isEqualTo("NGUYEN VAN A");
        assertThat(fields.readString("firstName").trim()).isEqualTo("ANH");
        assertThat(fields.readString("hireDate")).isEqualTo("20261115");
        assertThat(fields.readString("salary")).isEqualTo("000012500");
    }
}
```

In real tests, ensure sample lines have the exact character count defined by the specification. You can build strings from padded fields to avoid counting spaces by eye.

## 15. Testing invalid lengths

With strict mode, test lines shorter or longer than the declared structure to verify the tokenizer rejects invalid records as configured.

Example testing a line that is too short:

```java
@Test
void rejectsLineShorterThanConfiguredRanges() {
    FixedLengthTokenizer tokenizer = createTokenizer();

    assertThatThrownBy(() -> tokenizer.tokenize("12345678SHORT"))
            .isInstanceOf(IncorrectLineLengthException.class);
}
```

Also test:

- Exact-length lines.
- Lines shorter than the final range.
- Lines longer than specified if the format demands exact length.
- Trailing fields using an open range.
- Fields containing only spaces.
- Fields containing accented or multi-byte characters per source encoding.
- Invalid numeric/date values after the tokenizer has sliced the right positions.

With `strict=false`, tests must explicitly verify what the application expects when characters are missing. Do not disable strict mode without tests for short records.

## 16. Testing FieldSetMapper separately

The tokenizer and mapper should be tested separately to isolate which stage owns any failure.

Example mapper test:

```java
@Test
void mapsFieldSetToEmployee() {
    DefaultFieldSet fieldSet = new DefaultFieldSet(
            new String[]{
                    "12345678",
                    "NGUYEN VAN A        ",
                    "ANH            ",
                    "20261115",
                    "000012500"
            },
            new String[]{
                    "employeeId", "lastName", "firstName", "hireDate", "salary"
            });

    Employee employee = new EmployeeFieldSetMapper().mapFieldSet(fieldSet);

    assertThat(employee.employeeId()).isEqualTo("12345678");
    assertThat(employee.lastName()).isEqualTo("NGUYEN VAN A");
    assertThat(employee.hireDate()).isEqualTo(LocalDate.of(2026, 11, 15));
    assertThat(employee.salary()).isEqualByComparingTo("12500");
}
```

Mapper tests should cover empty fields, malformed dates, negative numbers, implied decimals, and padding. If the mapper performs data validation, verify the specific exceptions thrown so the step can apply its skip policy properly.

## 17. Integration testing FlatFileItemReader

Tokenizer tests do not verify that the reader opens the file, applies encoding, skips headers, and restores checkpoints. For those requirements, integration tests for `FlatFileItemReader` are needed.

Tests can use files in `src/test/resources`, create a reader with a test `Resource`, and read items sequentially. Verify:

- The file opens and encoding is correct.
- Headers are skipped as configured.
- Comment lines are handled properly.
- Each line is converted into an object with the right values.
- Malformed lines throw the expected exception.
- The reader closes the resource after the test.
- `saveState` and checkpoints work if the job requires restart.

When testing restart, the source file must remain unchanged between the initial run and the restart. If file contents change while the name/path stays the same, the checkpoint may point to a different line than the original data.

## 18. FixedLengthTokenizer and skip policy

In a chunk-oriented step, line-length errors can occur in the reader when the tokenizer cannot slice a record. If business rules allow skipping isolated faulty lines, configure skip for the appropriate exception.

Example:

```java
return new StepBuilder("importEmployeesStep", jobRepository)
        .<Employee, Employee>chunk(200, transactionManager)
        .reader(employeeReader)
        .writer(employeeWriter)
        .faultTolerant()
        .skip(IncorrectLineLengthException.class)
        .skipLimit(20)
        .listener(employeeSkipListener)
        .build();
```

This is appropriate only when isolated malformed lines can be excluded and a process records the errors. If the entire file is misaligned due to wrong range configuration or the wrong encoding, skipping line by line can drop massive numbers of records. In that scenario, let the step fail so the configuration or source file can be fixed.

`SkipListener.onSkipInRead` receives only the exception because the reader could not construct an item. For errors from `FlatFileParseException` or `IncorrectLineLengthException`, line/source information can be retrieved from the exception if provided by the version and exception type, but check the exact API before using it.

## 19. Common configuration mistakes

| Issue | Common cause | Mitigation |
|---|---|---|
| Fields shifted from a certain column onward | Using 0-based positions or miscalculating the inclusive end bound. | Use 1-based, inclusive ranges and check against the spec. |
| Field names do not match values | `setNames` order differs from `setColumns` order. | Keep both lists in the same order with the same element count. |
| Final field truncated | Final range ends too early or file length differs from spec. | Check ranges and actual lengths; use an open range if allowed. |
| Reader fails on short lines | Strict mode detects invalid length. | Fix source/ranges or disable strict only when allowed and mapper handles missing data. |
| Reader fails to catch malformed files | Tokenizer strict mode was disabled. | Enable strict mode and test invalid line lengths. |
| Missing resource mistaken for tokenizer error | Reader strict and tokenizer strict confused. | Distinguish resource existence checks from record length checks. |
| Date or number parsing fails | Tokenizer slices properly, but data format mismatches mapper. | Use formatter/parser matching the spec and validate values. |
| Leading zeros lost from codes | Mapper converts codes to numbers instead of keeping Strings. | Keep identifiers as Strings. |
| Accented characters shift columns | Wrong encoding or spec counts bytes while tokenizer slices characters. | Configure the right charset and confirm width units. |
| Header parsed as a record | Missing `linesToSkip` or appropriate header callback. | Handle headers in the reader before the tokenizer. |
| Mass skipping of records | Wrong ranges or wrong file format with overly broad skip policy. | Halt the job, verify the layout, and narrow the skip policy. |

## 20. Workflow for building a tokenizer from a file spec

When onboarding a new fixed-width file, implement in this order:

1. **Obtain the record specification:** identify field names, start/end positions, lengths, and data types.
2. **Determine the width unit:** bytes, characters, or code units; check charset and Unicode data.
3. **Draft the Range table:** use 1-based, inclusive positions; recalculate each field's length.
4. **Identify skipped regions:** reserved, filler, header, comment, or trailer lines.
5. **Configure the tokenizer:** declare `setNames`, `setColumns`, and strict mode.
6. **Write FieldSetMapper:** trim/preserve padding, parse dates/numbers, and validate data.
7. **Integrate the reader:** configure resource, encoding, headers, line mapper, and checkpoints.
8. **Test standard lines:** verify every field slices at the exact position.
9. **Test boundary lines:** short, long, blank, invalid formats, special characters, and open ranges.
10. **Choose fault tolerance:** decide which record errors are skippable and which file/layout errors must stop.

In particular, save several verified sample lines from the source system as test fixtures. Tests based on hand-crafted strings are only valuable if the author is certain the positions and padding of those strings match the specification.

## 21. Key takeaways

- `FixedLengthTokenizer` splits a line by fixed position ranges and returns a `FieldSet`.
- `Range` uses 1-based positions with an inclusive end; length is `end - start + 1`.
- `setNames` and `setColumns` must have the same number of elements and the same order.
- `DefaultLineMapper` combines the tokenizer with `FieldSetMapper` to create domain objects.
- The tokenizer only slices text; the mapper handles trimming, type parsing, and data validation.
- `setStrict(true)` validates line length against ranges; `strict` on `FlatFileItemReader` validates the resource—the two settings have different meanings.
- Ranges can skip reserved regions or use an open range for the trailing field when the format permits.
- The tokenizer slices on the decoded `String` line; if the specification is fixed-width by bytes, verify encoding and byte boundaries.
- Headers, comments, and blank lines are handled in the reader, not by altering ranges.
- `BeanWrapperFieldSetMapper` can be used for suitable JavaBeans, or a custom `FieldSetMapper` can be written to control conversion.
- Test the tokenizer, mapper, and reader at separate levels; test standard lines, invalid lengths, and invalid values.
- Only skip faulty records when business rules permit; misaligned layouts or widespread encoding errors should usually fail the step.

`FixedLengthTokenizer` is the right choice when file structure is defined by field positions. Translate the specification into accurate `Range` definitions, preserve field name ordering, keep tokenization separate from conversion, and verify width units and encoding. Combined with `FlatFileItemReader`, `DefaultLineMapper`, and a controlled `FieldSetMapper`, your application can read fixed-width files cleanly and detect non-conforming records early.
