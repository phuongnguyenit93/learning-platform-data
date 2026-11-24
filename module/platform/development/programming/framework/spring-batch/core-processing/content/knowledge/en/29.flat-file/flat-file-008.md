# RecordSeparatorPolicy

In Spring Batch, input files are typically read one physical line at a time. However, a **business record** does not always fit neatly on a single line. For example, a quoted CSV field may contain a newline; a fixed-width file may use a continuation marker across multiple lines; or an interchange format may define its own rules for when a record is complete.

`RecordSeparatorPolicy` allows `FlatFileItemReader` to determine which physical lines belong to the same logical record. The policy decides when a record has ended and can transform content before or after joining lines. Once a record is complete, the reader passes it to `LineMapper` for tokenization and object mapping.

Crucially, `RecordSeparatorPolicy` solves **record boundaries**, not full parsing of CSV, JSON, or fixed-width formats. Identifying fields, converting types, and validating data still belong to `LineTokenizer`, `FieldSetMapper`, `LineMapper`, or application logic.

## Physical lines and logical records

A physical line is a segment of text terminated by the file's line separator, such as LF or CRLF. A logical record is the unit of data the application wants to process as a single item.

In simple files, one physical line corresponds to one record:

```text
O-1001,An,120.50
O-1002,Binh,90.00
O-1003,Chi,75.00
```

However, CSV can contain newlines inside quoted fields:

```csv
orderId,customerName,note
O-1001,An,"Deliver at gate A"
O-1002,Binh,"Customer requested call
before delivery"
O-1003,Chi,"Leave at reception desk"
```

In this example, record `O-1002` spans two physical lines yet remains a single logical record. If the reader treated every physical line as an independent record, the line `before delivery"` would be parsed as a separate item and cause column-count errors or corrupted data.

```text
Physical lines:
  line 1: orderId,customerName,note
  line 2: O-1001,An,"Deliver at gate A"
  line 3: O-1002,Binh,"Customer requested call
  line 4: before delivery"
  line 5: O-1003,Chi,"Leave at reception desk"

Logical records:
  record 1 = line 1
  record 2 = line 2
  record 3 = line 3 + line 4
  record 4 = line 5
```

`RecordSeparatorPolicy` is where you express the rule that joins line 3 and line 4 into a single record before the mapper parses the data.

## What does RecordSeparatorPolicy do?

`RecordSeparatorPolicy` resides in the `org.springframework.batch.item.file.separator` package. The interface defines three methods:

```java
public interface RecordSeparatorPolicy {

    String preProcess(String record);

    boolean isEndOfRecord(String record);

    String postProcess(String record);
}
```

General meaning:

| Method | Role |
| --- | --- |
| `preProcess(record)` | Transforms the accumulated record content before the reader continues checking boundaries |
| `isEndOfRecord(record)` | Returns `true` when the current content forms a complete logical record |
| `postProcess(record)` | Transforms the record after the policy decides it has ended, before passing it to mapping |

`isEndOfRecord` is the primary decision. If it returns `false`, the reader keeps reading the next physical line and appending it to the record being built. When it returns `true`, the reader finalizes the record and passes the processed content to `LineMapper`.

`preProcess` and `postProcess` can simply return the input unchanged if no transformation is required. A policy that only determines record boundaries can leave both methods as pass-throughs.

## RecordSeparatorPolicy in FlatFileItemReader

`FlatFileItemReader` reads the resource line by line, using `RecordSeparatorPolicy` to group lines into a record. Once a complete record is assembled, the reader calls `LineMapper` to turn the string into an item.

```text
Resource / file
      |
      v
Read physical line
      |
      v
RecordSeparatorPolicy
      |
      +-- isEndOfRecord = false
      |        |
      |        +--> read next line and append to record
      |
      +-- isEndOfRecord = true
               |
               v
        postProcess(record)
               |
               v
          LineMapper
               |
               v
          ItemReader returns item
```

The policy is configured directly on the reader. Example with Spring Batch 5:

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile,
        RecordSeparatorPolicy orderRecordSeparatorPolicy) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .recordSeparatorPolicy(orderRecordSeparatorPolicy)
            .lineMapper(orderLineMapper())
            .saveState(true)
            .build();
}
```

In this example, the reader uses the policy to determine record boundaries, then `orderLineMapper()` maps the completed record into an `OrderInput`. `RecordSeparatorPolicy` does not replace `LineMapper`.

If multi-line records do not need special handling, you can use a simple policy matching a one-line-per-record format. Spring Batch provides default implementations in the `separator` package; choose an implementation based on your version's semantics and the actual file format.

## Distinguishing RecordSeparatorPolicy and LineMapper

These two components operate at different layers:

| Component | Responsibility | Example |
| --- | --- | --- |
| `RecordSeparatorPolicy` | Determines which physical lines make up one record | Joining two CSV lines while a quoted field remains open |
| `LineMapper` | Converts a logical record into an object | Mapping `O-1002,Binh,"..."` into `OrderInput` |
| `LineTokenizer` | Splits a record into fields | Separating CSV or fixed-width columns |
| `FieldSetMapper` | Converts fields into a typed object | Constructing `OrderInput` and parsing amount to `BigDecimal` |

If `LineMapper` receives a string cut off mid-record, the mapper cannot know on its own whether the next line belongs to the previous record or starts a new one unless the application builds custom logic. Boundary detection should be solved upfront in `RecordSeparatorPolicy`.

Conversely, if record boundaries are accurate but column counts or data types are wrong, the error belongs to the tokenizer/mapper or validation. Do not complicate the policy to mask field-level data errors.

## Default and simple policies

Spring Batch includes `RecordSeparatorPolicy` implementations in `org.springframework.batch.item.file.separator`. A simple policy treats each line read as a complete record; a continuation-aware policy treats a line as incomplete when it ends with a continuation symbol. Depending on the version, the reader builder may supply a default policy if the application does not specify one.

Do not rely on assumptions about defaults without checking your Spring Batch version and input format. If a file has specific multi-line rules, configure the policy explicitly and test with real sample files, including malformed records and escape characters.

### When to use a simple policy?

A policy treating each physical line as one record fits when:

- Every line contains exactly one record.
- Fields cannot contain newlines.
- The producer guarantees a record is never split across lines.
- Continuation lines do not exist in the format.

For such files, no custom policy is needed. Using a simple policy keeps the reader easy to reason about and prevents accidentally merging unrelated lines when a file is corrupted.

### When is a custom policy needed?

A custom policy is appropriate when:

- A field may contain newlines.
- Records use quotes or escape characters to indicate continuation.
- A marker at the end of a line signals the record is incomplete.
- Records have a custom terminator instead of standard line separators.
- Legacy formats have special line-joining rules.

Only implement a custom policy when the source format has explicit rules. Do not guess record boundaries from line counts or string lengths unless the format guarantees them.

## Example: CSV with multi-line quoted fields

Suppose a CSV format uses `"` to enclose fields and escapes internal quotes as two consecutive quotes (`""`). A record ends once all quoted fields are closed.

Example:

```csv
id,description,amount
1,"Deliver to floor 2",100.00
2,"Customer note: ""call ahead""
and deliver after 17:00",250.00
3,"No note",80.00
```

The second record spans two physical lines. The doubled quotes inside the field represent a literal quote character in data, not closing/opening the field.

### Illustrative custom policy

A policy can scan the accumulated record to track quote state. The following example assumes a simple RFC 4180-like CSV format: comma delimiter, quotes only open a field at the start of a field, and internal quotes are escaped as `""`.

```java
public class QuotedCsvRecordSeparatorPolicy
        implements RecordSeparatorPolicy {

    @Override
    public String preProcess(String record) {
        return record;
    }

    @Override
    public boolean isEndOfRecord(String record) {
        return !hasOpenQuotedField(record);
    }

    @Override
    public String postProcess(String record) {
        return record;
    }

    private boolean hasOpenQuotedField(String record) {
        boolean inQuotes = false;
        boolean atFieldStart = true;

        for (int i = 0; i < record.length(); i++) {
            char current = record.charAt(i);

            if (inQuotes) {
                if (current == '"') {
                    if (i + 1 < record.length()
                            && record.charAt(i + 1) == '"') {
                        i++; // escaped quote: ""
                    } else {
                        inQuotes = false;
                    }
                }
            } else if (current == ',') {
                atFieldStart = true;
            } else if (current == '"' && atFieldStart) {
                inQuotes = true;
                atFieldStart = false;
            } else if (current != '\r' && current != '\n') {
                atFieldStart = false;
            }
        }

        return inQuotes;
    }
}
```

This policy returns `false` while inside an unclosed quoted field; the reader continues appending the next physical line. Once the quote closes, the policy returns `true` and the record is handed to the mapper.

This is an illustrative example for one specific CSV dialect, not a complete CSV parser. It assumes quotes appear only at the beginning of a field and use `""` for escaping. If the producer permits whitespace before quotes, uses a different delimiter or escape character, or produces non-standard quotes, adjust the algorithm to match the actual format. For complex CSV, consider using a dedicated parser with multi-line support rather than writing an incomplete custom parser.

### Configuring the policy on the reader

```java
@Bean
RecordSeparatorPolicy quotedCsvRecordSeparatorPolicy() {
    return new QuotedCsvRecordSeparatorPolicy();
}

@Bean
@StepScope
FlatFileItemReader<OrderInput> multilineOrderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile,
        RecordSeparatorPolicy quotedCsvRecordSeparatorPolicy,
        LineMapper<OrderInput> orderLineMapper) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("multilineOrderReader")
            .resource(new FileSystemResource(inputFile))
            .recordSeparatorPolicy(quotedCsvRecordSeparatorPolicy)
            .lineMapper(orderLineMapper)
            .saveState(true)
            .build();
}
```

The reader still needs a `LineMapper`/tokenizer configured with the exact same quoting and escaping rules. The policy only ensures the full record content is assembled before mapping.

## Example: continuation marker at end of line

Some legacy formats use a trailing `\` character at the end of a line to indicate the record continues. Example:

```text
CUSTOMER|1001|Nguyen Van A|Ha Noi\
|10000000|ACTIVE
CUSTOMER|1002|Tran Thi B|Da Nang\
|8000000|ACTIVE
```

Under this format, a line ending with a backslash is not yet a complete record. The next line is joined into the record, and the continuation marker may need to be stripped before the mapper parses it.

A policy can check for the continuation character at the end of the record and strip the marker along with the line break according to how your version's reader joins lines. Because physical line joining and line separator characters depend on the implementation, verify with tests against actual inputs before deploying. If a built-in Spring Batch continuation policy matches the semantics, prefer reusing it over reimplementing it.

Core logic example for a simple format:

```java
public class BackslashContinuationPolicy implements RecordSeparatorPolicy {

    @Override
    public String preProcess(String record) {
        return record;
    }

    @Override
    public boolean isEndOfRecord(String record) {
        return !endsWithContinuationMarker(record);
    }

    @Override
    public String postProcess(String record) {
        return removeContinuationSeparators(record);
    }

    private boolean endsWithContinuationMarker(String record) {
        int last = record.length() - 1;
        return last >= 0 && record.charAt(last) == '\\';
    }

    private String removeContinuationSeparators(String record) {
        return record.replace("\\\r\n", "")
                .replace("\\\n", "");
    }
}
```

This is a skeleton for a format with very specific line-continuation rules. If the accumulated record does not retain `\n` or `\r\n` separators in that form, adjust `postProcess`. You must also distinguish a true trailing continuation backslash from an escaped double backslash at the end of data; the example above does not handle every possible escape rule.

## What should preProcess and postProcess do?

These two methods let the policy normalize record content during line assembly.

### preProcess

`preProcess` can process content before boundary checking continues—for example, when a legacy format has a marker to strip or line fragments to normalize before joining. Transformations must preserve the information needed by `isEndOfRecord`.

Do not strip quote characters or delimiters too early if those very characters determine whether the record has ended. Removing quotes before checking quote state could cause the policy to conclude prematurely that the record is complete.

### isEndOfRecord

This method decides whether the reader must read additional physical lines. Its logic should:

- Be deterministic for the same record content.
- Not depend on global mutable state shared across items.
- Handle escaping/quoting/continuation properly according to the format.
- Behave predictably when a record is malformed or overly long.
- Perform no I/O or external service calls.

Because the method may be called multiple times while the reader assembles a record, never increment business counters or write to a database here.

### postProcess

`postProcess` can remove continuation markers or normalize separators once the record is complete. The returned content is passed to the mapping stage.

Do not use `postProcess` to silently mask data errors by auto-fixing a malformed record without clear business rules. If a record is invalid, let the mapper/validator report an appropriate error or record a reject under a dedicated policy.

## Records that never end

If a file has an opening quote without a closing quote, `isEndOfRecord` may keep returning `false` all the way to EOF. This is a data error that must be handled explicitly.

Example:

```csv
id,description
1,"Content starts here without closing quote
2,Next record
```

If the policy only waits for a closing quote, the second line gets absorbed into the first record and the reader keeps reading until EOF. Depending on the implementation and version, the reader may throw an error when EOF is reached with an incomplete record. Do not automatically treat EOF as a valid record terminator if the format requires closing quotes.

Handling strategies:

- Fail the step with a clear parse error so operators can fix the file.
- Move the file to a quarantine/error area for investigation.
- Log file identity, record/line position, and failure cause.
- Apply recovery rules only if business requirements explicitly define how to recover malformed records.

Do not impose an arbitrary line limit and silently truncate the record without raising an error; doing so can produce corrupted data that looks valid.

## Limiting record length

Multi-line records can grow very large if the source is corrupted or a producer omits a closing quote. A policy needs a bounding strategy to avoid unbounded string growth in memory.

You can design a policy wrapper around a character count or accumulated line limit and throw a dedicated exception when exceeded. Note that the `RecordSeparatorPolicy` interface does not provide a dedicated callback for physical line count; if you need to bound line count, you may need to track it within the policy or implement a reader/wrapper suited to your version and lifecycle. If a mutable counter is stored in the policy, ensure the policy instance is not shared concurrently across multiple readers or steps.

Bounds should be based on the file contract, such as a maximum of 20 lines per record or 1 MB of content. When exceeded, fail early with enough context to locate the offending record; do not let one record consume the rest of the file and exhaust memory.

## RecordSeparatorPolicy and parse errors

Errors can occur at two layers:

| Layer | Examples | Responsible component |
| --- | --- | --- |
| Record boundary | Unclosed quote, invalid continuation marker, unterminated record | `RecordSeparatorPolicy` / reader |
| Record content | Missing columns, non-numeric amount, invalid date format | `LineMapper`, tokenizer, `FieldSetMapper`, or processor |

Not every parse error belongs in the policy. Once a record is split cleanly, if field values are wrong, keep validation in the mapping/processing layer so error messages remain specific.

You can define a dedicated exception for record boundary errors:

```java
public class InvalidRecordBoundaryException extends RuntimeException {
    public InvalidRecordBoundaryException(String message) {
        super(message);
    }
}
```

Depending on how the policy is invoked and how the reader wraps exceptions in your Spring Batch version, the exception may be wrapped in a file-read exception. Tests should inspect the cause chain and record/file identity instead of relying on fixed message strings.

## Skip and retry when RecordSeparatorPolicy detects an error

`RecordSeparatorPolicy` participates in file reading, so errors at this layer are usually surfaced as read errors. If you want to skip a malformed record, determine whether the reader can reliably recover the boundary of the next record.

If a quote is left unclosed, the reader cannot know which line starts the next valid record. Skipping the current string could mean dropping many valid records along with it. Therefore, do not configure broad skips for all separator errors just to keep the job running.

Retry does not fix an immutable malformed file either; re-reading the same content typically produces the same failure. Retry only makes sense for potentially transient failures, such as an unavailable resource or interrupted I/O. For permanent format errors, failing and quarantining the file is usually safer.

## Checkpoints and restart with multi-line records

`FlatFileItemReader` can persist state for restart, but multi-line records make the distinction between physical lines and logical items critical. Checkpoints must represent records processed/committed according to the reader's lifecycle.

Key principles:

- Use a reader supporting `ItemStream` with `saveState(true)` when restart is needed.
- Assign a stable reader name so `ExecutionContext` keys do not change.
- Keep the file path and source contents identical across restarts; ideally use immutable files or verify version/checksum.
- Do not change `RecordSeparatorPolicy` between the initial run and a restart if format/semantics could differ.
- If changing the record-splitting algorithm, evaluate compatibility with existing checkpoints.
- Never modify or truncate the source file while the job is running or still restartable.

Reader example:

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile,
        RecordSeparatorPolicy recordSeparatorPolicy,
        LineMapper<OrderInput> lineMapper) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .recordSeparatorPolicy(recordSeparatorPolicy)
            .lineMapper(lineMapper)
            .saveState(true)
            .build();
}
```

If the file is replaced after a checkpoint is saved, the reader may resume at the old position while the underlying data has changed. Use immutable inputs or verify checksums/versions before restarting.

## Physical line numbers vs. logical record numbers

When a record spans multiple lines, the physical line number differs from the logical record number. For instance, the 10th record might begin at physical line 14 and end at line 16.

This affects logging and error handling:

- Reporting “record 10 failed” helps business troubleshooting.
- Reporting “physical line 16” helps when opening the file in an editor.
- Logging only one number without clarifying which it is can send operators to the wrong place.

Log file identity, record index, and physical line range whenever the reader/mapper can provide them. `RecordSeparatorPolicy` only decides boundaries; it does not necessarily supply full line metadata to the application. If exact line ranges are needed, use a custom wrapper/reader or add tracking compatible with your version's APIs.

## Headers, comments, and blank lines

`RecordSeparatorPolicy` does not replace reader settings for headers, comments, or blank lines.

- `linesToSkip(...)` skips initial lines, typically headers.
- `skippedLinesCallback(...)` receives the content of skipped lines.
- `setComments(...)` configures comment prefixes per the reader API.
- Blank lines can be handled according to reader/mapper rules.

If a file has a multi-line header, check whether header skipping interacts compatibly with the record separator. Do not assume `linesToSkip(1)` always skips one logical record if the header itself spans multiple physical lines. Test with real files and use an appropriate reader/callback setup.

## Thread safety and policy scope

A policy typically performs only string inspection, so it can be stateless and safe to share if the implementation holds no mutable state. However, if a policy keeps counters, buffers, or state across calls, do not share the same instance across concurrent readers or steps.

Key principles:

- Prefer stateless policies whose decisions depend solely on the passed record string.
- If state is required, create instances per reader/step scope or enforce explicit synchronization.
- Never store data from the previous record in a singleton field if multiple jobs can run concurrently.
- Never query databases or call APIs inside `isEndOfRecord`.
- Never use `ThreadLocal` to pass record state across callbacks without guaranteed lifecycle cleanup.

In a partitioned step, each partition may read a different file or file slice. Sharing a single stateful policy can scramble state across partitions. Use a stateless policy or dedicated instance per reader.

## Performance when assembling multi-line records

`FlatFileItemReader` must hold the current record in memory until the policy confirms the record is complete. Multi-line or very large records increase allocations and string scanning cost.

To maintain performance:

- Use algorithms linear in record length; avoid redundant re-scanning.
- Avoid complex regexes that risk backtracking on long strings.
- Enforce record size limits based on the file contract.
- Avoid logging entire offending records when records may be large or contain sensitive data.
- Use a dedicated parser when formats have complex quoting/escaping rules.
- Measure throughput with normal records as well as multi-line records near the size limit.

If a policy re-scans the entire accumulated string after every physical line, a record of N lines gets scanned repeatedly. For very long records, total work can grow significantly. If optimization is needed, consider a parser/reader that tracks incremental state while still honoring the `RecordSeparatorPolicy` contract and reader lifecycle.

## Testing RecordSeparatorPolicy

Test the policy independently with unit tests, and then integration-test it with `FlatFileItemReader`. Unit tests verify quoting/continuation rules; integration tests prove the reader actually joins physical lines before invoking the mapper.

### Unit testing boundary cases

For a quote-aware policy, test at least:

| Accumulated input record | Expected `isEndOfRecord` | Reason |
| --- | --- | --- |
| `1,An,100` | `true` | No open quoted field |
| `2,Binh,"note` | `false` | Quote not closed |
| `2,Binh,"note\npart 2"` | `true` | Quote closed |
| `3,Chi,"said ""hello"""` | `true` | Valid escaped quotes |
| `4,Du,"open quote` | `false` | Record incomplete |

JUnit example:

```java
class QuotedCsvRecordSeparatorPolicyTest {

    private final QuotedCsvRecordSeparatorPolicy policy =
            new QuotedCsvRecordSeparatorPolicy();

    @Test
    void completesSingleLineRecord() {
        assertTrue(policy.isEndOfRecord("1,An,100"));
    }

    @Test
    void waitsForClosingQuote() {
        assertFalse(policy.isEndOfRecord("2,Binh,\"note"));
        assertTrue(policy.isEndOfRecord(
                "2,Binh,\"note\npart 2\""));
    }

    @Test
    void acceptsEscapedQuoteInsideQuotedField() {
        assertTrue(policy.isEndOfRecord(
                "3,Chi,\"said \"\"hello\"\"\""));
    }
}
```

These tests reflect the dialect described in the example. If delimiters or escapes differ, adjust fixtures accordingly.

### Testing preProcess and postProcess

If the policy transforms records, verify:

- `preProcess` does not strip characters needed for boundary detection.
- `postProcess` removes only valid markers.
- Field data is not lost or unintentionally altered.
- Repeated calls with the same input return identical output if the policy is stateless.

### Integration testing with FlatFileItemReader

Create a temporary file with a multi-line record, configure the reader with the custom policy and a test `LineMapper` that captures received strings. Verify the reader emits the expected item count and the second record contains the expected internal newline.

Example test structure:

```java
@Test
void readerMapsMultilineCsvAsOneItem() throws Exception {
    Path file = tempDir.resolve("orders.csv");
    Files.writeString(file, """
            1,An,"Deliver at gate A"
            2,Binh,"Call before
            delivery"
            3,Chi,"Leave at desk"
            """);

    FlatFileItemReader<String> reader =
            new FlatFileItemReaderBuilder<String>()
                    .name("multilineTestReader")
                    .resource(new FileSystemResource(file))
                    .recordSeparatorPolicy(
                            new QuotedCsvRecordSeparatorPolicy())
                    .lineMapper((line, lineNumber) -> line)
                    .build();

    reader.open(new ExecutionContext());
    try {
        assertEquals("1,An,\"Deliver at gate A\"", reader.read());
        assertEquals(
                "2,Binh,\"Call before\ndelivery\"",
                reader.read());
        assertEquals("3,Chi,\"Leave at desk\"", reader.read());
        assertNull(reader.read());
    } finally {
        reader.close();
    }
}
```

This example assumes the reader preserves newlines between physical lines in the manner verified in your version. If the implementation normalizes line separators differently, adjust expected values to match the actual contract. Integration tests matter more than calling `isEndOfRecord` directly because they prove the reader and policy collaborate correctly.

### Testing EOF with unclosed quotes

Create a file that ends while a record still has an unclosed quote. Verify the reader raises an error according to defined behavior rather than returning a truncated fake item. If the application has a quarantine workflow, confirm the file is moved to the error area and metadata records the cause.

### Testing restart

Let the reader process several records, stop the step, and restart the same `JobInstance`. Verify:

- The reader name stays the same.
- `saveState(true)` is enabled.
- The input file is unmodified between the two runs.
- Policy and line mapping preserve identical semantics.
- The reader resumes at the right logical record, even when earlier records spanned multiple physical lines.
- No committed records are skipped or duplicated.

### Testing performance and limits

Generate a multi-line record near the permitted limit and verify processing time and memory remain acceptable. Generate an unterminated record to ensure the policy does not buffer data indefinitely and reports a clear error.

## Common pitfalls

### Treating every physical line as one record

Multi-line records split into separate items, breaking field counts or causing parse exceptions. Use a policy matching the format.

### Using RecordSeparatorPolicy to parse fields

The policy only determines record boundaries. Splitting columns and converting types belong to `LineMapper`, tokenizers, and mappers.

### Overly naive quote counting

Simply counting quote characters fails with escaped quotes, quotes inside unquoted data, or custom dialects. Define exact quoting rules and test edge cases.

### Stripping quotes too early in preProcess

The policy loses the signal telling it whether a field has closed. Keep delimiters and quotes intact until `isEndOfRecord` finishes deciding.

### Not handling unclosed quotes at EOF

The reader may swallow the rest of the file into one giant record or fail late. Define malformed-record handling and size bounds.

### Retrying immutable format errors

Re-reading the same file will not fix a missing quote or bad continuation marker. Failing/quarantining is usually better than endless retries.

### Sharing a stateful policy across readers

Mutable state can get mixed across jobs or partitions. Prefer stateless policies or per-reader instances.

### Changing policy across restarts

Old checkpoints may be incompatible with the new record-joining behavior. Keep semantics stable or start a distinct logical job deliberately.

### Unit testing only the policy without the reader

The reader may join lines, handle EOF, or normalize separators in ways that change results. Write integration tests with temporary files and `FlatFileItemReader`.

## Design guidelines

When using `RecordSeparatorPolicy`, clarify:

1. How does the source format define physical lines and logical records?
2. How many lines can a record span, and what is its termination condition?
3. How are quotes, escapes, continuation markers, and delimiters specified?
4. Do `preProcess` and `postProcess` need to transform content?
5. Is the policy stateless and deterministic when invoked repeatedly?
6. What happens when a record is malformed or a quote remains open at EOF?
7. Are record length/line count limits enforced to prevent unbounded memory consumption?
8. Do `LineMapper` and the tokenizer share the same dialect as the policy?
9. Does the reader save state and restart on the exact same input version?
10. Do tests cover multi-line records, escaped quotes, EOF errors, restarts, and large records?

For one-line-per-record files, use a simple policy. For multi-line files, write a policy matching the documented format and keep mapping logic in a separate layer. Prefer standard parsers when formats are complex rather than guessing boundaries with heuristics. Ensure the reader, policy, mapper, and checkpoints share the same definition of a record so restarts never drop or duplicate data.

## Summary

`RecordSeparatorPolicy` tells `FlatFileItemReader` when physical lines form a complete logical record. `isEndOfRecord` decides whether more lines must be read; `preProcess` and `postProcess` allow normalizing content before/after boundary detection. The policy does not parse fields and does not replace `LineMapper` or tokenizers. Use a simple policy when one line equals one record; use a custom policy for multi-line quotes or continuation markers per a specific format. Explicitly handle unclosed quotes at EOF, oversized records, escapes, and line endings. Keep policy semantics stable across restarts, enable appropriate reader state, and test end-to-end with `FlatFileItemReader` to guarantee records are never split, misjoined, or duplicated.
