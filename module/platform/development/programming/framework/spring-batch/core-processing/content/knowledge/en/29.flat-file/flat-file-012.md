# Encoding and newlines

In Spring Batch, processing flat files is not just about reading the right columns. The application must also understand content **encoding** and the **newlines** separating records. These two factors determine how bytes in a file are decoded into characters, how the reader identifies line boundaries, and how the writer produces output readable by downstream systems.

A Job may pass on a developer's workstation yet fail in production if a file is produced with a different charset, carries a BOM, uses CRLF instead of LF, or contains multi-line records. Output can also be rejected by consumers if the writer emits newlines that violate the file contract.

When working with flat files, clarify:

- Charset of input and output files.
- Whether the file includes a BOM.
- Newline convention: LF, CRLF, or CR.
- Whether each physical line is one logical record.
- Whether data contains newlines inside quoted fields.
- Which newline and encoding downstream systems expect.
- Whether those settings stay constant across restarts.

Spring Batch exposes encoding and line separator settings on flat-file readers and writers. Configure them according to the data contract rather than relying on host defaults.

## 1. What is encoding?

A file on a filesystem is a sequence of bytes. Encoding—or charset—defines how that byte sequence maps to Unicode characters and vice versa.

For instance, the same character can take different byte counts across charsets:

- UTF-8 uses 1 to 4 bytes per Unicode code point.
- UTF-16 uses 16-bit code units and may use a surrogate pair for characters outside the Basic Multilingual Plane.
- Windows-1252 uses one byte for characters in its code page.
- ISO-8859-1 has a single-byte character set differing from Windows-1252.

If a file is encoded in Windows-1252 while the reader decodes it as UTF-8, accented characters can become corrupted, replaced with replacement characters, or trigger decode errors depending on the decoder and content.

~~~text
File bytes
    |
    v
Charset decoder
    |
    v
Java String / Unicode characters
    |
    v
LineTokenizer / FieldSetMapper
    |
    v
Domain object
~~~

Encoding must match how the file was actually generated. You cannot repair mis-encoded data merely by renaming the file or changing newlines.

## 2. UTF-8 is usually a good choice for data exchange

UTF-8 is widely used for CSV, TSV, JSON, and modern interchange formats. It represents all Unicode characters and interoperates cleanly across systems.

Example reader configured for UTF-8:

~~~java
@Bean
@StepScope
public FlatFileItemReader<CustomerInput> customerReader(
        @Value("#{jobParameters['inputFile']}") Resource inputFile) {

    return new FlatFileItemReaderBuilder<CustomerInput>()
            .name("customerReader")
            .resource(inputFile)
            .encoding("UTF-8")
            .linesToSkip(1)
            .delimited()
            .names("id", "name", "email")
            .targetType(CustomerInput.class)
            .saveState(true)
            .build();
}
~~~

Declaring encoding explicitly ensures the Job behaves identically on Windows, Linux, containers, and machines with differing default charset settings.

If the file contract specifies a legacy charset such as Windows-1252 or ISO-8859-1, declare that exact charset. Do not pick UTF-8 merely because it is popular if source bytes are not UTF-8.

## 3. Do not rely on the platform default charset

Avoid letting readers or custom code fall back to the JVM's default charset.

Avoid:

~~~java
new InputStreamReader(inputStream);
new FileReader(file);
~~~

Constructors that omit a charset may use the runtime's default charset. Behavior varies by Java version and environment configuration; since Java 18, UTF-8 is the default charset under JEP 400 in most environments, yet declaring it explicitly still documents the data contract clearly.

Clearer approach:

~~~java
new InputStreamReader(
        inputStream,
        StandardCharsets.UTF_8);

Files.newBufferedReader(
        path,
        StandardCharsets.UTF_8);
~~~

In Spring Batch, configure encoding directly on FlatFileItemReader or FlatFileItemWriter. In custom readers/writers, use an explicit Charset or StandardCharsets.

## 4. UTF-8, UTF-16, and legacy charsets

Pick the charset matching the data source and consumer:

| Charset | Characteristics | When to use |
|---|---|---|
| UTF-8 | Unicode, 1–4 bytes per code point | Standard modern exchange format |
| UTF-16LE | UTF-16 little-endian | Systems requiring little-endian byte order |
| UTF-16BE | UTF-16 big-endian | Systems requiring big-endian byte order |
| Windows-1252 | Single-byte Western European Windows code page | Legacy system integration |
| ISO-8859-1 | Limited single-byte code page | Legacy systems with an explicit contract |

Avoid vague labels like "ANSI" in technical configuration unless the actual code page is known. On Windows, "ANSI" refers to the machine's locale-specific code page rather than a single universal charset.

When receiving files from partners, ask them to confirm the charset. You can inspect leading bytes or use analysis tools, but never guess encoding solely by visually inspecting a few characters.

## 5. What is a BOM?

A BOM (Byte Order Mark) is a marker at the start of a stream used to indicate encoding or byte order. Some tools emit a BOM when exporting files; some consumers do not expect it.

Common BOM byte sequences:

| Encoding | BOM bytes |
|---|---|
| UTF-8 | EF BB BF |
| UTF-16LE | FF FE |
| UTF-16BE | FE FF |

UTF-8 does not need a BOM to determine byte order, yet some Windows tools still emit UTF-8 files with a BOM.

If a reader decodes UTF-8 without stripping the BOM, the character U+FEFF can appear at the start of the first record. Consequently, the first field may begin with a leading BOM—for example, expected value ORD-001 arrives starting with U+FEFF, causing equality checks or validation to fail.

## 6. Handling BOM when reading files

First confirm the source contract: does the file carry a BOM, and is it mandatory or optional?

Common handling strategies:

- Use a BOM-aware input stream if Apache Commons IO or a similar library is available.
- Strip the BOM at the beginning of the stream before handing it to the reader.
- In a custom LineMapper, strip U+FEFF at the start of the first record.
- Normalize the file during an ingestion step prior to Job processing.

Helper example to strip a leading BOM from a string:

~~~java
static String stripLeadingBom(String value) {
    if (value != null && !value.isEmpty()
            && value.charAt(0) == '\uFEFF') {
        return value.substring(1);
    }
    return value;
}
~~~

If building a custom LineMapper, apply the helper to the first line before parsing:

~~~java
LineMapper<CustomerInput> delegate = createLineMapper();

LineMapper<CustomerInput> bomAwareMapper =
        (line, lineNumber) ->
                delegate.mapLine(
                        stripLeadingBom(line),
                        lineNumber);
~~~

Here you wire bomAwareMapper into the reader instead of the original mapper. If the header is skipped before LineMapper runs, the BOM may sit inside the skipped header line; if the file has no header or the header is parsed, handle the BOM accordingly.

Do not strip U+FEFF characters in the middle of content. A BOM is expected only at the start of the stream; identical characters elsewhere may be legitimate data or require separate validation.

## 7. BOM when writing files

Most modern UTF-8 outputs do not require a BOM. If a consumer requires a UTF-8 BOM, write it exactly once at the beginning of the file.

With FlatFileItemWriter, you can use a header callback or a dedicated output layer to emit the BOM alongside the header in the proper format. Example header content:

~~~java
.headerCallback(writer ->
        writer.write("\uFEFFid,customerName,email"))
~~~

Verify the exact behavior with your Spring Batch version and how the writer reopens files on restart. Never write a BOM on every write(chunk) call, or the BOM will appear mid-file between records.

If there is no header yet a BOM is required, use a custom writer or a controlled file-initialization step to write the BOM before emitting records. Inspect the raw leading bytes of the output rather than only opening the file in an editor, because many editors hide BOMs visually.

## 8. What is a newline?

A newline is a character or character sequence used to separate lines in a text file.

Three common conventions:

| Name | Notation | UTF-8 bytes |
|---|---|---|
| LF | \n | 0A |
| CRLF | \r\n | 0D 0A |
| CR | \r | 0D |

- Modern Linux and Unix typically use LF.
- Windows typically uses CRLF.
- Some legacy formats or systems use CR.

Newlines are part of the file's structure. If a consumer expects CRLF while the writer emits LF, the file may still look readable in many tools yet fail strict integration contracts or exact byte checks.

Do not confuse newlines with encoding. Encoding defines how characters map to bytes; newlines define which sequence terminates records. Both must be configured independently.

## 9. BufferedReader and how Java reads newlines

Standard Java line-reading APIs such as BufferedReader.readLine() recognize LF, CRLF, and CR as line terminators. The line terminator characters are stripped from the returned string.

Example file:

~~~text
A<CR><LF>
B<LF>
C<CR>
~~~

A line reader returns three strings: A, B, and C. However, just because the API accepts mixed terminators does not mean business formats allow mixing them.

For files adhering to a strict standard, validate newlines before launching the Job or normalize files during ingestion. Mixing CRLF and LF can break external tools, checksums, line numbering, or byte-level processing.

## 10. FlatFileItemReader and record separators

FlatFileItemReader reads text record by record and applies a record separation mechanism before passing content to LineMapper.

Simple configuration:

~~~java
@Bean
@StepScope
public FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") Resource resource) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(resource)
            .encoding("UTF-8")
            .linesToSkip(1)
            .delimited()
            .names("id", "orderNumber", "amount")
            .targetType(OrderInput.class)
            .saveState(true)
            .build();
}
~~~

The reader processes physical lines per the configured record separator. For files with one record per line, this model usually fits cleanly.

Distinguish between:

- Physical line: a line separated by a newline in the file.
- Logical record: a business record the application intends to parse.
- Field: a single value within a record.

In standard CSV, one logical record typically fits on one physical line. However, CSV may allow newlines inside quoted fields, causing a single logical record to span multiple physical lines.

## 11. CSV with newlines inside quoted fields

CSV example:

~~~csv
id,comment
1,"First line
Second line"
2,"Normal comment"
~~~

The comment for record 1 contains a newline inside quotes. If the reader defaults to treating every physical line as an independent record, the record will parse incorrectly or throw an error.

When the format permits multi-line fields, configure a RecordSeparatorPolicy aligned with the file's quoting rules or use a full CSV parser. Never blindly merge arbitrary failing lines; you must know precisely where a record starts and ends.

A RecordSeparatorPolicy can:

- Decide whether a record is finished or continues.
- Pre-process line fragments prior to joining.
- Post-process the completed record before passing it to LineMapper.

For complex CSV, consider a dedicated parser supporting RFC 4180 or the partner's exact dialect. DelimitedLineTokenizer does not automatically replace a full CSV parser for arbitrary multiline, escaping, and quoting rules.

## 12. Newlines inside data vs. newlines separating records

These serve two different meanings:

1. Newlines outside records terminate records.
2. Newlines inside field values are preserved as part of the data.

In CSV, newlines inside fields must generally be enclosed in quotes, and internal quotes must be escaped per dialect.

Example:

~~~csv
id,description
10,"Address:
12 Main Street
District 1"
~~~

When a writer generates CSV, the line aggregator must apply proper quoting and escaping for the format. Setting lineSeparator alone is not enough to protect embedded newlines inside fields.

If downstream does not support multi-line fields, replace embedded newlines in data with an agreed representation such as spaces or escape sequences. Never replace them unilaterally if original content must be preserved.

## 13. Configuring newlines on FlatFileItemWriter

FlatFileItemWriter lets you specify the line separator. Declare it explicitly whenever output must conform to an integration standard.

Example creating a UTF-8 file with LF:

~~~java
@Bean
@StepScope
public FlatFileItemWriter<OrderResult> orderWriter(
        @Value("#{jobParameters['outputFile']}") Resource outputFile) {

    return new FlatFileItemWriterBuilder<OrderResult>()
            .name("orderWriter")
            .resource(outputFile)
            .encoding("UTF-8")
            .lineSeparator("\n")
            .delimited()
            .names("id", "orderNumber", "status")
            .headerCallback(writer ->
                    writer.write("id,orderNumber,status"))
            .saveState(true)
            .build();
}
~~~

If the consumer requires CRLF, configure:

~~~java
.lineSeparator("\r\n")
~~~

Using System.lineSeparator() makes output dependent on the host OS running the application. That can break expectations when the same Job runs on Windows in development and Linux in production while downstream expects a fixed format.

The writer appends the line separator between records. Verify exact behavior with headers, footers, restarts, and empty files in your Spring Batch version.

## 14. Trailing newline at end of file

A text file may or may not end with a trailing newline. Many Unix tools and line-oriented systems expect a trailing newline at EOF; some protocols only care that records are separated between each other.

Clarify the contract:

- Every record ends with a newline, including the final record.
- The final record has no trailing newline.
- Whether an empty file includes a header.
- Whether headers and footers count as records.

FlatFileItemWriter normally writes the configured line separator after each record. If a consumer requires no trailing newline at EOF, check writer behavior and consider a separate finalization step if needed. Do not truncate bytes from a file after a Job completes without understanding the impact on restarts and integrity.

For interchange files, ending with a trailing newline is usually more compatible, though you must follow the target system's specification.

## 15. Avoid System.lineSeparator for fixed formats

System.lineSeparator() returns the runtime OS newline:

- Windows typically returns CRLF.
- Linux typically returns LF.

If output goes to a partner requiring CRLF, configure CRLF explicitly. If LF is required, configure LF explicitly.

A Job may run across multiple environments. Relying on defaults can make the exact same JobParameters produce byte-different files purely due to OS differences. That affects checksums, digital signatures, diffs, snapshot tests, and strict parsers.

Keep encoding and lineSeparator configured together in one place, scoped by file type or partner.

## 16. Encoding and newlines in custom readers

If writing a manual reader, open streams with an explicit charset:

~~~java
try (BufferedReader reader = Files.newBufferedReader(
        inputPath,
        StandardCharsets.UTF_8)) {

    String line;
    while ((line = reader.readLine()) != null) {
        // Parse one simple logical record per line.
    }
}
~~~

readLine() strips line terminators, so code cannot tell from the returned string alone whether the source line used LF or CRLF.

If you need to detect original newlines or preserve exact bytes, read at the byte level or use a parser that records delimiters. Never call readLine() and assume you can reconstruct the exact original bytes.

In a custom reader implementing ItemStreamReader, coordinate encoding/newline handling with checkpoints. If the reader restarts from a byte offset, compute offsets in encoded bytes rather than Java character counts.

## 17. Byte offsets vs. character offsets

This is critical for UTF-8 and fixed-width files.

An ASCII character in UTF-8 occupies one byte, whereas accented or non-ASCII characters can occupy multiple bytes. Java String uses UTF-16 code units; String.length() is neither UTF-8 byte length nor always the Unicode code point count.

Example:

~~~java
String value = "café";

int utf16Length = value.length();

int utf8ByteLength =
        value.getBytes(StandardCharsets.UTF_8).length;
~~~

These two lengths can differ.

If a fixed-width specification states a field is 20 bytes wide, never call String.substring(0, 20) assuming you extracted 20 UTF-8 bytes. Parse by bytes before decoding, or follow an unambiguously defined encoding/field-width rule.

If the specification states 20 Unicode characters, define whether "character" means code point or grapheme cluster and slice accordingly. Never use the terms byte and character interchangeably.

## 18. Newlines and fixed-width files

In fixed-width files, records usually have a fixed length, while the newline may sit outside the record length or be accounted for separately per the specification.

Example:

~~~text
Record bytes: 100 bytes
Delimiter: CRLF (2 bytes)
Next record begins after delimiter
~~~

When calculating byte offsets, include the delimiter length. Under LF, the delimiter takes one byte; under CRLF, two bytes in UTF-8.

When using FlatFileItemReader with FixedLengthTokenizer, the tokenizer operates on already-decoded strings. This works when field ranges are defined in terms of the character positions used by the parser. If the source defines columns in bytes—especially with multi-byte encodings—perform byte-aware parsing before converting to String.

Take a real sample file and verify field offsets, byte order, charset, and delimiters. A single accented Vietnamese character can shift all subsequent columns if slicing mixes byte and character units.

## 19. Inspecting encoding and newlines of source files

You can inspect leading bytes and representative slices using OS utilities:

~~~bash
file -bi orders.csv
xxd -l 32 orders.csv
od -An -tx1 -N64 orders.csv
~~~

These tools reveal guessed MIME/charset types and raw bytes. Note that file -bi is a heuristic guess, not absolute proof of encoding.

In PowerShell:

~~~powershell
Format-Hex -Path 'D:\batch\input\orders.csv' -Count 32
~~~

To identify newlines, inspect bytes 0A and 0D 0A. Avoid inspecting files only in a text editor, since editors may silently convert newlines or decode using a guessed charset.

For large files, you do not need to load the entire file into memory just to inspect a BOM or the first few bytes. Read a prefix or use a streaming validator.

## 20. Normalizing newlines before processing

If sources arrive from multiple systems with inconsistent newlines, normalize during ingestion:

~~~text
File received from partner
        |
        v
Check charset and BOM
        |
        v
Check record separator
        |
        v
Normalize to UTF-8 + LF
        |
        v
Store immutable file in staging
        |
        v
Spring Batch reader processes
~~~

Benefits:

- Consistent reader configuration.
- Easy to test and reproduce inputs.
- Checksums can be computed over the normalized file.
- Downstream systems are decoupled from the sender's OS.

However, normalization must preserve data integrity. If newlines appear inside quoted fields, never blindly replace every CRLF with LF if doing so alters field contents or record semantics. Use a format-aware parser or normalize only record-terminating delimiters.

Retain the original file if required for audit or reconciliation. You can store both the original artifact and the normalized artifact alongside checksum, encoding, and conversion rule version.

## 21. How encoding and newlines affect restarts

Readers may store checkpoints by item count, line count, or internal state. On restart, the reader reopens the source and repositions according to saved state.

If the file changes between the initial run and restart, checkpoints may no longer point to the same record:

- The file was converted from LF to CRLF.
- The file was converted from Windows-1252 to UTF-8.
- A BOM was added or removed.
- Lines were inserted or deleted.
- Record contents were replaced.
- The file was overwritten with a new version under the same name.

A change in encoding or newlines can shift line numbers, record boundaries, or byte offsets. The Job may skip or duplicate data.

For consistent restarts:

- Keep input files immutable.
- Record file checksums or versions.
- Store charset and format version as part of input configuration.
- Never alter line separators when restarting the same JobInstance.
- Use JobParameters or ExecutionContext to track required metadata.
- Re-verify the file fingerprint when the reader reopens.

A checkpoint is not a snapshot of file contents. It is valid only as long as the source and reading rules stay compatible.

## 22. Writer restarts and output encoding

FlatFileItemWriter can save state to resume output after a restart. The writer name must stay stable and saveState must be enabled to recover state.

Encoding, line separator, headers, and field formatting must remain identical between the initial run and restart.

For example, writing UTF-8 + LF on the first run and switching to UTF-16LE + CRLF on restart produces a file with mixed encodings and newlines that consumers cannot parse reliably.

For high-reliability outputs:

- Use a distinct output file per JobInstance or execution.
- Prevent consumers from reading temporary files before the Job completes.
- Keep writer name and format settings stable.
- Enable saveState when the writer supports restart.
- Publish the final file only after Step/Job succeeds.
- If format must change, generate a new output rather than resuming a partial file with different settings.

## 23. Headers, footers, and newlines

FlatFileItemWriter can write headers and footers via callbacks. Headers and footers must follow the file's encoding and newline rules too.

Example:

~~~java
.headerCallback(writer ->
        writer.write("id,orderNumber,status"))
.footerCallback(writer ->
        writer.write("END"))
~~~

The writer applies its line separator according to its line-writing lifecycle. Inspect actual output bytes to verify headers, records, and footers are separated cleanly. Do not append CRLF manually inside the callback while also having the writer add CRLF unless blank lines are intended.

If a header carries a BOM, the BOM must precede the very first character of the file, not each chunk. Footers should only be written per the writer's completion lifecycle; test restarts to confirm no duplicate headers or extra footers appear.

## 24. Locale is not encoding

Locale governs how numbers, dates, currencies, and decimal separators are formatted. Encoding governs how characters are encoded into bytes.

For example:

- Locale vi-VN may use a comma or formatter-configured number conventions.
- Locale en-US uses a dot for the decimal point.
- UTF-8 can represent both notations.
- Changing encoding does not change the decimal separator.
- Changing locale does not change newlines.

If a file uses commas as delimiters and locale-specific commas as decimals, define quoting or number formatting explicitly. Never try to fix locale parsing errors by changing encoding.

In Spring Batch, configure formatters, FieldExtractors, or conversion services per the format contract. Treat charset and locale as two separate properties.

## 25. CSV quoting, escaping, and newlines

CSV has many dialects. Systems may vary on:

- Delimiter: comma, semicolon, or tab.
- Quote character: double quote or another character.
- How quotes inside fields are escaped.
- Whether newlines inside quoted fields are allowed.
- Whether CRLF or LF is required.
- Whether a BOM is present.

Example field containing both a comma and quotes:

~~~csv
id,comment
1,"Customer said ""hello, team"""
~~~

The writer must escape quotes per dialect. If a field contains a newline, it must be properly quoted when the format allows it. A naive line aggregator that simply joins fields with commas can produce invalid files.

Document the exact dialect in the data contract and test with the consumer's parser or a compliant parser. Never rely solely on whether a file looks fine when opened in Excel.

## 26. Testing encoding

Build test fixtures containing characters representative of production data:

- ASCII.
- Accented Vietnamese text.
- Non-Latin Unicode characters.
- Supplementary characters if applicable.
- Inputs with and without a BOM.
- Invalid byte sequences for the charset.

Reader tests should verify decoded Java String values, not merely the count of items read.

Example:

~~~java
@Test
void readsUtf8VietnameseText() throws Exception {
    Path file = tempDir.resolve("customers.csv");

    Files.writeString(
            file,
            "id,name\n1,Nguyễn Ánh\n",
            StandardCharsets.UTF_8);

    CustomerInput item = readFirstItem(file);

    assertEquals("Nguyễn Ánh", item.name());
}
~~~

To test files with a BOM, prepend the byte prefix EF BB BF followed by UTF-8 content. Verify the BOM is absent from the first field per application policy.

For legacy charsets, generate fixtures using that exact charset and confirm the reader uses the same encoding. Never generate fixtures using the platform default, or tests may produce different results across machines.

## 27. Testing newlines

Create fixtures for each convention:

~~~text
LF:    record1<LF>record2<LF>
CRLF:  record1<CR><LF>record2<CR><LF>
CR:    record1<CR>record2<CR>
~~~

Verify:

- The reader emits the exact number of logical records.
- No trailing CR leaks into field values.
- Blank lines are handled per policy.
- A final record without a trailing newline is handled properly if allowed by format.
- Newlines inside quoted fields are not split into two records.
- Line numbers in parse errors reflect actual physical lines.
- The writer emits the exact configured delimiter bytes.

For writers, read output back as raw bytes and inspect the delimiter sequences. Do not rely solely on readAllLines, since that API normalizes line endings and can hide raw newline bugs.

## 28. Testing exact output bytes

If downstream requires UTF-8 + CRLF, tests can verify leading bytes and delimiters:

~~~java
byte[] output = Files.readAllBytes(outputPath);

assertEquals(
        (byte) 0x0D,
        output[indexOfFirstRecordSeparator]);

assertEquals(
        (byte) 0x0A,
        output[indexOfFirstRecordSeparator + 1]);
~~~

In real tests, locate delimiter offsets by scanning the byte stream or compare the entire output against expected bytes constructed with StandardCharsets.UTF_8 and explicit CRLF sequences.

If output requires a BOM, assert the first three bytes are EF BB BF. If no BOM is desired, assert the file does not start with that prefix.

Never compare only decoded Strings; byte-level differences can vanish when re-reading and normalizing line endings.

## 29. Common pitfalls

### Reader using the wrong charset

Accented characters become corrupted or the first field contains strange symbols. Declare the exact encoding matching the source.

### Relying on the default charset

Jobs behave differently across machines or Java runtimes. Explicitly configure UTF-8 or the contract's charset.

### BOM leaking into a business key

The reader fails to strip a leading BOM. Use BOM-aware input or strip the BOM at the exact start position.

### Writer emitting OS-dependent newlines

Output changes between Windows and Linux. Configure lineSeparator explicitly per contract.

### Mixing LF and CRLF

Strict consumers or checksums may fail. Normalize inputs or reject non-conforming files.

### Multi-line CSV fields split by physical line

One logical record breaks into multiple items. Use RecordSeparatorPolicy or a multiline-capable CSV parser.

### Slicing fixed-width fields by String.length

UTF-8 contains multi-byte characters. Determine whether field widths are specified in bytes or characters and parse in the exact unit.

### Modifying a file before restart

Checkpoints no longer point to the same data. Keep inputs immutable and verify checksums/versions.

### Writing BOMs repeatedly on restart or per chunk

BOMs appear mid-file. Write the BOM once at the start of output and test restarts.

### Inspecting files only in an editor

Editors may guess encodings or normalize newlines automatically. Inspect raw bytes whenever exact formatting is required.

## 30. Workflow for designing encoding and newlines

When building a flat-file reading/writing Job, determine:

1. What input charset is declared by the partner or source system?
2. Does the file include a BOM?
3. Should the reader strip the BOM before parsing?
4. Is the input newline LF, CRLF, or CR?
5. Can logical records span multiple physical lines?
6. How does the CSV dialect specify quoting and escaping?
7. Are fixed-width columns measured in bytes or characters?
8. Has the reader declared encoding explicitly?
9. Has the writer declared both encoding and lineSeparator explicitly?
10. Do headers and footers follow the same format?
11. Are inputs and outputs immutable or stable across restarts?
12. Do tests verify both Unicode values and raw output bytes?

Encoding determines how bytes become characters; newlines determine how records are separated. Spring Batch requires readers and writers configured to match the file's exact contract, especially for BOMs, multi-line CSV, and fixed-width data. When charsets and line separators are declared explicitly, sources stay stable across restarts, and outputs are verified at the byte level, Jobs produce consistent flat files across environments and remain compatible with consumers.
