# Skipping header lines

CSV or tabular text files commonly have a leading line describing column names, such as `orderId,customerId,amount`. That line helps human readers understand the file structure, but it is usually not business data to send into a processor or writer. If the reader treats the header as a normal record, the application may hit type-parsing errors, insert garbage rows, or fail on the very first item.

In Spring Batch, `FlatFileItemReader` supports skipping leading lines using the **`linesToSkip`** property. You can combine it with `skippedLinesCallback` to read, validate, or log the skipped lines. This setting is helpful for files with fixed headers, provided you understand the skip count, when callbacks run, restart behavior, and multi-file edge cases.

## 1. Why skip the header?

Suppose an input file has the following contents:

```csv
orderId,customerId,amount
1001,C001,250.00
1002,C002,175.50
1003,C003,420.00
```

The first line contains column names. Subsequent lines contain order data. If the reader sends the header into `LineMapper`, `FieldSetMapper` might try to parse the string `orderId` as a `Long`, or construct an object containing invalid data.

Skipping the header helps:

- Convert only data lines into items.
- Prevent the header from being written to a database table or output file as a record.
- Keep mapping logic focused on the actual data structure.
- Allow validating the header before processing data when required.
- Clearly separate file-level metadata from business records.

The header still has validation value. If the application skips it without checking column names and order, a file with a changed schema may be mis-mapped without early detection.

## 2. Configuring linesToSkip

`FlatFileItemReader` provides `setLinesToSkip(int)` to specify how many initial lines to skip when opening the resource. The builder also exposes `.linesToSkip(int)`.

For a file with a single header line, a straightforward configuration is:

```java
@Bean
@StepScope
public FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderFileReader")
            .resource(new FileSystemResource(inputFile))
            .encoding(StandardCharsets.UTF_8.name())
            .linesToSkip(1)
            .delimited()
            .delimiter(",")
            .names("orderId", "customerId", "amount")
            .targetType(OrderInput.class)
            .saveState(true)
            .build();
}
```

With this configuration:

- `linesToSkip(1)` skips the first physical line of the file.
- `delimited()` configures the tokenizer for delimiter-separated data.
- `names(...)` declares the field names used to map data.
- `targetType(...)` tells the builder to instantiate the target type.
- `saveState(true)` lets the reader save state for restart.
- `encoding(...)` specifies the input encoding explicitly.

The header is not returned as an item. The reader begins emitting items from the first data line.

If a file has no header, keep `linesToSkip(0)` or omit the skip configuration. Leaving it at `1` will silently drop the first data record.

## 3. linesToSkip counts lines, not business items

`linesToSkip` is the number of initial file lines read and skipped before item mapping begins. It is not the number of items to skip under `SkipPolicy`, nor the number of records filtered for business rules.

| Mechanism | Purpose | Example |
|---|---|---|
| `linesToSkip(1)` | Skip one leading line when opening the file | CSV header |
| `SkipPolicy` / `.skip(...)` | Skip an item that throws a skippable exception | A record with a malformed date |
| `ItemProcessor` returning `null` | Filter a valid item that needs no output | Dropping a cancelled order per business rules |
| `LineCallbackHandler` | Receive the content of skipped lines | Validating or logging the header |

The header line is not read as an item, so it does not increment `readCount`, `processCount`, or `writeCount` like a regular record. It also never passes through `ItemProcessor` and is not treated as a regular item skip.

If the header is invalid, the callback can throw an exception when the reader opens the file, failing the step. This is a file-structure error, distinct from skipping a data record after the reader has returned an item.

## 4. Skipping multiple leading lines

Some files include descriptive lines or export metadata before the header:

```text
Report: Daily Orders
Business date: 2026-11-15
orderId,customerId,amount
1001,C001,250.00
1002,C002,175.50
```

In this example, two metadata lines and one header line—three lines total—need to be skipped:

```java
reader.setLinesToSkip(3);
```

`linesToSkip` only counts the leading lines to skip. If you want to inspect specifically the header on line three, the callback must track the position of each skipped line or the application should use a separate preflight/parser step.

Do not set `linesToSkip` to an estimated metadata line count if files can vary. If the preamble has variable length, use a specialized reader/parser to locate the header by marker or format rules, and begin reading data from the exact position.

## 5. Using skippedLinesCallback to inspect headers

`FlatFileItemReader` supports `LineCallbackHandler` via `setSkippedLinesCallback(...)`. The callback is invoked with the content of each skipped line.

Example that only logs the header:

```java
FlatFileItemReader<OrderInput> reader = new FlatFileItemReader<>();
reader.setName("orderFileReader");
reader.setResource(new FileSystemResource(inputFile));
reader.setLinesToSkip(1);
reader.setSkippedLinesCallback(line ->
        log.info("Skipped file header: {}", line));
```

The callback receives the raw line read by the reader before data lines are mapped into items. It does not replace `LineMapper` and does not receive a mapped `FieldSet` for data records.

If `linesToSkip(3)`, the callback is called for each of the three skipped lines. Therefore, do not assume the callback receives only the column header if the file also has a preamble.

The callback is suited for:

- Logging headers for audit trails.
- Validating the header against the expected schema.
- Reading simple metadata at the top of the file.
- Preparing mapping metadata if the application supports dynamic schemas.

Do not use the callback to process regular business data. Lines after the header remain the responsibility of the tokenizer, line mapper, and processor.

## 6. Validating that the header matches the expected schema

Skipping the header without verifying it can mask schema errors. For example, the application expects `orderId,customerId,amount`, but the actual file changes to `customerId,orderId,amount`. If mapping relies on column position, values will be assigned to the wrong fields.

You can validate the header inside the callback:

```java
private static final String EXPECTED_HEADER =
        "orderId,customerId,amount";

reader.setLinesToSkip(1);
reader.setSkippedLinesCallback(header -> {
    if (!EXPECTED_HEADER.equals(header)) {
        throw new IllegalStateException(
                "Unexpected CSV header. Expected: " + EXPECTED_HEADER);
    }
});
```

If the header does not match, the reader should not proceed to map data under the old schema. Exceptions thrown in the callback normally fail reader open/step startup; they are not treated as faulty items for `skip(...)` to ignore automatically.

Exact string comparison works when header formatting is strictly standardized. If files may vary in whitespace, BOM, or letter casing, normalize before comparing while preserving meaningful differences.

## 7. Validating column order

When mapping depends on position, check both column names and column order. Example:

```text
Expected: orderId,customerId,amount
Actual:   customerId,orderId,amount
```

Both headers have the same set of names in different order. If the tokenizer still uses `.names("orderId", "customerId", "amount")`, the first value on each data line gets assigned to `orderId` even though it is actually `customerId`.

When comparing headers:

1. Parse the header into a list of column names.
2. Normalize per system conventions, such as trimming whitespace.
3. Check the column count.
4. Check column names and order.
5. Reject the file if there are missing, extra, or duplicate columns unsupported by the application.

Do not merely check whether the header contains the expected names. A file with duplicate columns or reordered columns can still corrupt mappings.

## 8. Headers containing delimiters or quotes

CSV allows header values with quotes and delimiters inside column names, for example:

```csv
"order,id","customer,name",amount
1001,"Smith, John",250.00
```

Do not use `String.split(",")` to parse headers when CSV quoting is involved. `split` does not understand quoting rules and can split a single column name into multiple pieces.

Use the same CSV tokenizer style as the data lines to parse the header. Illustrative example:

```java
DelimitedLineTokenizer headerTokenizer = new DelimitedLineTokenizer();
headerTokenizer.setDelimiter(",");

reader.setLinesToSkip(1);
reader.setSkippedLinesCallback(headerLine -> {
    FieldSet headerFields = headerTokenizer.tokenize(headerLine);
    String[] columnNames = headerFields.getValues();

    if (!Arrays.equals(
            new String[] {"order,id", "customer,name", "amount"},
            columnNames)) {
        throw new IllegalStateException("Unexpected header columns");
    }
});
```

This illustrates using a tokenizer to parse the header. Configure the tokenizer to match the actual CSV dialect, including delimiter, quote character, escape rules, and strictness. If your library/version requires extra settings, keep parsing rules aligned between header and data.

## 9. Header BOM and encoding

Some UTF-8 files generated by spreadsheet tools start with a byte order mark (BOM). When read as text, the BOM character may appear ahead of the first column name, causing header comparisons to fail even though the file looks right visually.

For instance, the actual value of the first column may be `\uFEFForderId` instead of `orderId`.

Things to watch:

- Specify encoding explicitly, typically UTF-8 when the file contract specifies UTF-8.
- Check for a BOM at the start of the file if headers unexpectedly fail to match.
- If stripping a BOM, strip it only at the very start of the file and only when it is actually a BOM; do not trim or alter content indiscriminately.
- Never rely on the machine's default encoding because development and production environments can differ.
- Test files both with and without BOMs if upstream can produce either form.

`linesToSkip` skips lines based on text decoded by the reader; it does not validate encoding or strip BOMs for the application automatically.

## 10. Headers and blank lines

Some files have blank lines before the header or between the preamble and header. `linesToSkip` counts leading lines strictly by position, including blank lines. It does not scan for the first non-empty line to auto-detect the header.

Example:

```text

orderId,customerId,amount
1001,C001,250.00
```

If configured with `linesToSkip(1)`, the reader skips the leading blank line and emits the header as an item. If configured with `linesToSkip(2)`, the reader skips both the blank line and the header.

If a file has a variable number of leading blank lines, use a preflight/parser step to detect structure or normalize the source before running. Do not pick a fixed skip count if input data does not guarantee that structure.

## 11. Multi-line headers and preambles

Some file formats have multiple descriptive lines:

```text
Company: Example Ltd
Report: Orders
Date: 2026-11-15
orderId,customerId,amount
1001,C001,250.00
```

If the first three lines are metadata and the fourth line is the header, you can skip four lines. However, if you need to validate specifically the fourth line, the callback must distinguish line positions. You can use a local counter in the callback:

```java
AtomicInteger skippedLineNumber = new AtomicInteger();

reader.setLinesToSkip(4);
reader.setSkippedLinesCallback(line -> {
    int lineNumber = skippedLineNumber.incrementAndGet();

    if (lineNumber == 4 && !EXPECTED_HEADER.equals(line)) {
        throw new IllegalStateException("Invalid header at line 4");
    }
});
```

This illustrative snippet assumes the callback runs sequentially during reader open for the skipped lines. If the reader is reopened on the same instance or the callback runs multiple times in a specific lifecycle, the counter must be initialized/reset accordingly. For complex formats, a dedicated preflight step is easier to control.

## 12. Skipping headers vs. comment lines

A header is schema metadata usually located at the top of the file. Comments are annotation lines carrying a marker, such as `# generated by system`.

Do not confuse these two cases:

- `linesToSkip` skips a fixed number of leading lines.
- Comment configuration on `FlatFileItemReader` identifies comment lines by configured prefixes during reading.

Example:

```text
# generated at 2026-11-15
orderId,customerId,amount
1001,C001,250.00
```

If a comment always appears on line one and the header on line two, you can use `linesToSkip(2)` and validate each line in the callback. If comments can appear in multiple places, use the comment-prefix mechanism instead of inflating `linesToSkip` to skip leading lines.

Do not configure a character as a comment prefix if valid data lines can also start with that character.

## 13. MultiResourceItemReader and headers across multiple files

When using `MultiResourceItemReader` to read multiple files, each resource may have its own header. The delegate reader is typically reopened for each resource. If the delegate is a `FlatFileItemReader` configured with `linesToSkip(1)`, the first line of every opened file is skipped.

Example:

```text
part-001.csv:
orderId,customerId,amount
1001,C001,250.00

part-002.csv:
orderId,customerId,amount
1002,C002,175.50
```

If both files have headers, skipping one line per resource works properly.

However, if only the first file has a header:

```text
part-001.csv:
orderId,customerId,amount
1001,C001,250.00

part-002.csv:
1002,C002,175.50
```

then a delegate with `linesToSkip(1)` will drop the first data item of `part-002.csv`. You need a different strategy, such as preprocessing the files, using a delegate whose skip setting adapts per resource, or ensuring upstream produces every file in a uniform format.

If headers across files can differ, the callback should validate each resource and include the resource filename in error messages. Never validate only the first file and assume every remaining file shares the same schema.

## 14. Headers changing across schema versions

A system may evolve a file schema over time, such as adding a `currency` column or renaming `customerId` to `clientId`. Skipping a fixed header without inspecting it can keep the job running while mapping data wrongly.

You can handle this via one of these approaches:

- **Fixed schema:** compare the header to the expected column list and reject on mismatch.
- **Versioned schema:** read a metadata/version line and select the corresponding tokenizer and mapper.
- **Flexible schema:** parse the header into a column-name-to-index map and map fields by name.
- **Input normalization:** transform files of different versions into a canonical format before running the main batch job.

If schema changes alter data semantics, do not silently ignore new or missing columns. Explicitly define mandatory columns, optional columns, and default values.

## 15. Dynamic header example by column name

For dynamic schemas, the callback can parse the header and configure the tokenizer for subsequent data lines. The idea is to use one tokenizer to read the header into a list of names, and assign those names to the data tokenizer.

Skeleton example:

```java
DelimitedLineTokenizer headerTokenizer = new DelimitedLineTokenizer();
headerTokenizer.setDelimiter(",");

DelimitedLineTokenizer dataTokenizer = new DelimitedLineTokenizer();
dataTokenizer.setDelimiter(",");

DefaultLineMapper<FieldSet> lineMapper = new DefaultLineMapper<>();
lineMapper.setLineTokenizer(dataTokenizer);
lineMapper.setFieldSetMapper(fieldSet -> fieldSet);

FlatFileItemReader<FieldSet> reader = new FlatFileItemReader<>();
reader.setName("dynamicHeaderReader");
reader.setResource(new FileSystemResource(inputFile));
reader.setLinesToSkip(1);
reader.setLineMapper(lineMapper);
reader.setSkippedLinesCallback(headerLine -> {
    String[] names = headerTokenizer.tokenize(headerLine).getValues();
    validateAllowedColumns(names);
    dataTokenizer.setNames(names);
});
```

This is an illustrative skeleton that needs `validateAllowedColumns` and a business mapper added. In real applications, check for duplicate column names, required columns, unknown columns, and ordering per schema version. If `LineMapper` or the tokenizer is shared across multiple step/job executions, ensure dynamic configuration cannot leak across executions; use dedicated step-scoped beans for stateful readers and tokenizers.

If the header only serves to verify a fixed schema, static `.names(...)` configuration is simpler and safer.

## 16. Restart when the reader skips headers

`FlatFileItemReader` supports saving state via `ItemStream`. On restart, the reader uses the saved checkpoint to resume from the matching position. Skipping the header is part of how the reader opens and positions itself in the file.

For restart to work reliably:

- Keep the reader name stable.
- Keep the exact same input file and contents across restarts.
- Keep `linesToSkip` unchanged across executions of the same instance.
- Enable `saveState(true)` if read position recovery is needed.
- Do not manually skip headers again in custom restart code outside the reader's mechanism.
- Do not alter the number of preamble/header lines in the file after a checkpoint has been saved.

For instance, the initial run uses `linesToSkip(1)` and commits 500 items. If the file is edited to prepend an extra metadata line before restarting, an item-count checkpoint may point to a shifted position. That can cause the reader to skip or duplicate records.

The skipped-lines callback is primarily for handling lines skipped when the reader opens the resource. Do not use the callback as the sole place storing business state that must survive a restart. If a header contains a version or checksum that needs verification, store it in the execution context/manifest after validating and re-verify the source on restart.

## 17. Header callbacks and errors when opening the reader

The callback runs while the reader is skipping leading lines. If the callback detects a bad header and throws an exception, the reader cannot open successfully with that configuration and the step fails.

This is normally the desired behavior because processing should not continue with an invalid schema. However, understand that:

- A callback failure is not an error on an already-returned item.
- `skip(InvalidRecordException.class)` is not a general mechanism for skipping a bad header.
- `SkipListener` does not receive the header as a business item.
- If you want a detailed validation report, use a separate preflight step before importing.

If the callback only logs the header without validating it, the job can keep running even with a wrong schema. Decide explicitly: observe only, or actually enforce validation.

## 18. Encoding, line endings, and header contents

Headers can fail to match due to file formatting differences:

- UTF-8 BOM at the beginning of the file.
- Windows CRLF vs. Unix LF.
- Leading/trailing whitespace in column names.
- Different letter casing.
- CSV quotes around column names.
- Delimiters other than commas, such as tabs or semicolons.

Confirm the file contract and configure the reader/tokenizer accordingly:

```java
reader.setEncoding("UTF-8");
reader.setLinesToSkip(1);
```

For TSV files, configure the delimiter as tab. For semicolon files, configure `;`. Do not auto-switch delimiters based on an arbitrary line without explicit rules.

When normalizing headers, normalize only differences allowed by the contract. For example, trimming whitespace may make sense, whereas lowercasing every column name could mask two distinct columns in a case-sensitive schema.

## 19. Ensuring each resource has a header once

For a single file, `linesToSkip(1)` assumes the header appears only on the first line. If a file has repeated headers across pages or from upstream file concatenation, `linesToSkip` will not automatically skip mid-file headers.

Example file concatenated from two exports:

```csv
orderId,customerId,amount
1001,C001,250.00
1002,C002,175.50
orderId,customerId,amount
1003,C003,420.00
```

The second header will be read as a data row. To prevent this, fix upstream to emit a single header, or use a line mapper/processor with explicit rules to recognize repeated headers. Do not use `linesToSkip(2)`, as that would drop the first real data record.

If data comes from multiple resources, prefer one header per resource and `MultiResourceItemReader` with a delegate skipping one line, or normalize files before import. The input contract must specify whether headers appear at the top of every file or only the first file in a set.

## 20. Headers and comments in MultiResourceItemReader

When reading multiple files, each file may have its own metadata and header. The delegate `FlatFileItemReader` is reopened per resource, so `linesToSkip` and callbacks apply each time the delegate opens.

If every file shares the same structure:

```text
part-001.csv: metadata, header, data...
part-002.csv: metadata, header, data...
part-003.csv: metadata, header, data...
```

the delegate can skip the same number of lines in each file. If the first file has metadata while subsequent files do not, data lines will be skipped by mistake. Standardize the source format or pick a per-resource reader strategy.

With multiple files, include the resource filename in logs/correlation context so a bad header immediately identifies which file failed.

## 21. Testing header skipping

Tests should verify that the reader emits the exact items and no header appears in output.

Basic test cases:

1. File with one header and multiple records: only records are returned.
2. File without a header when skip is set to 1: confirm tests detect the lost first record or validator rejects the setup.
3. Header with wrong column names: callback refuses to open the reader.
4. Header with wrong column order: validation catches the schema change.
5. File with BOM or alternate encoding: verify normalization behavior per contract.
6. Empty file or header-only file: reader finishes cleanly without emitting items.
7. File shorter than `linesToSkip`: confirm the application handles missing header/preamble explicitly.
8. Multi-resource: each file has a header, only headers are skipped, no first record is lost.
9. Restart after several committed chunks: reader resumes at the exact position without treating the header as an item.
10. File modified before restart: validation detects checksum/version mismatch if immutable input is required.

Example unit/integration test using `FlatFileItemReader` directly:

```java
FlatFileItemReader<String> reader = new FlatFileItemReader<>();
reader.setName("testReader");
reader.setResource(new ByteArrayResource(
        ("orderId,amount\n1001,250.00\n1002,175.50\n")
                .getBytes(StandardCharsets.UTF_8)));
reader.setLinesToSkip(1);
reader.setLineMapper((line, lineNumber) -> line);

reader.open(new ExecutionContext());
assertEquals("1001,250.00", reader.read());
assertEquals("1002,175.50", reader.read());
assertNull(reader.read());
reader.close();
```

This tests the basic skip mechanism. In real tests, use `try/finally` to close the reader even if an assertion fails, and use `skippedLinesCallback` to verify the expected header was received.

## 22. Example testing header and data together

A test can confirm the callback receives the header while the reader returns only data rows:

```java
AtomicReference<String> capturedHeader = new AtomicReference<>();

reader.setLinesToSkip(1);
reader.setSkippedLinesCallback(capturedHeader::set);

reader.open(new ExecutionContext());
try {
    assertEquals("orderId,amount", capturedHeader.get());
    assertEquals("1001,250.00", reader.read());
    assertEquals("1002,175.50", reader.read());
    assertNull(reader.read());
} finally {
    reader.close();
}
```

This is a test skeleton; configure the resource and line mapper before opening the reader. If multiple lines are skipped, the callback is invoked multiple times and the test should collect a list of lines instead of a single value.

## 23. Common configuration mistakes

| Situation | Cause | Mitigation |
|---|---|---|
| Header mapped as an item | `linesToSkip` not configured | Use `linesToSkip(1)` when the file has one header |
| First data record lost | Skip configured on headerless file or count too high | Confirm the leading-line contract before running |
| Bad header yet job keeps running | Header skipped without schema validation | Use `skippedLinesCallback` to validate |
| Columns mapped to wrong fields | Header reordered while mapper uses old positions | Compare both column names and order |
| Header with commas inside column names parsed wrong | Using `String.split` instead of a CSV tokenizer | Parse with a quote-aware tokenizer |
| Header mismatches despite looking identical | BOM, encoding, or whitespace | Specify encoding and normalize controllably |
| Repeated header mid-file becomes an item | `linesToSkip` only applies to the top of the file | Normalize source or detect repeated headers explicitly |
| Multi-file drops first data line on later files | Delegate skips header on every file without headers | Standardize structure or vary strategy per resource |
| Callback runs more times than expected | Multiple skipped lines or multiple resources | Track line position and resource name |
| Restart reads wrong data | File or header line count changed after checkpoint | Keep inputs immutable, stabilize `linesToSkip`, store source version |
| Header error treated as item skip | Confusing callback/open exception with item exception | Handle header validation in callback/preflight step |

## 24. Workflow for designing header handling

1. **Identify source format:** CSV, TSV, fixed-width, or text with preamble.
2. **Locate header positions:** start of each file, start of the entire batch, or dynamic position.
3. **Configure `linesToSkip`:** set the exact number of leading physical lines to skip.
4. **Decide on callbacks:** skip only, or log/validate/extract metadata.
5. **Validate schema:** verify column names, count, order, and required columns.
6. **Align encoding/delimiter/quote:** ensure header and data are parsed under the same rules.
7. **Handle multiple resources:** determine whether every file has a header or only the first.
8. **Keep inputs stable across restarts:** never alter headers, line order, or file content after a checkpoint.
9. **Test edge cases:** empty files, header-only files, BOMs, invalid headers, and repeated headers.
10. **Trace errors per resource:** log filename and line details for easier investigation.

## 25. Key principles to remember

- `linesToSkip(n)` skips the first `n` lines of the resource; it is not an item skip policy.
- For files with a single leading header, use `linesToSkip(1)`.
- `skippedLinesCallback` receives each skipped line and is suited for logging or validating headers.
- Skipped headers do not pass through the processor/writer and do not count as normal read items.
- If a header is invalid, the callback can fail the reader/step; this is a file-structure error, not an item skip.
- Check column names, count, and order whenever mapping depends on position.
- Use a proper CSV tokenizer instead of `String.split` when headers use quoting or contain delimiters.
- Specify encoding explicitly and watch for BOMs.
- `linesToSkip` counts a fixed number of physical lines; it does not locate headers past variable blank lines or preambles.
- With `MultiResourceItemReader`, the delegate may skip headers in every resource; ensure all files share the same convention.
- Repeated mid-file headers are not handled by leading `linesToSkip`.
- Keep skip configuration and inputs stable across restarts; the reader must save state to resume at the exact checkpoint.
- Test headers together with output data rather than only checking that the job completes.

Skipping header lines is a small configuration setting that directly affects file import correctness. When `linesToSkip` matches the exact line count, callbacks validate schemas where needed, and source structure stays stable across restarts, `FlatFileItemReader` processes data cleanly without injecting file metadata into business pipelines or accidentally dropping the first record.
