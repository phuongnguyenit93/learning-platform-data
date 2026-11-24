# File Encoding

In Spring Batch, file readers and writers work with two different forms of data: files store **bytes**, while most record-processing APIs work with **characters** and Strings. Encoding defines how bytes and characters are converted back and forth. If the wrong encoding is chosen, a file may still open and be read, yet Vietnamese content, special characters, or multilingual data will be corrupted.

In the Resource Management chapter, encoding is part of configuring input and output resources. You must determine the source file's charset, explicitly configure the charset on the reader/writer, handle BOM if present, and test the data after conversion. Never rely on the host machine's default charset because development, container, and production environments may differ.

## 1. What is encoding?

Text files store bytes. An application needs to know the rule for mapping bytes to characters to understand the content. That rule is the character encoding, often shortened to encoding or charset.

For example, the same Vietnamese character can be represented by a different byte sequence depending on the encoding. If a file was created in UTF-8 but the reader decodes it using Windows-1252, accented characters may render as garbled character sequences.

~~~text
File bytes
    |
    v
Charset decoder
    |
    v
Java characters / String
    |
    v
FlatFileItemReader parser
    |
    v
Item object
~~~

When writing files, the conversion direction is reversed:

~~~text
Item object
    |
    v
LineAggregator
    |
    v
Java String
    |
    v
Charset encoder
    |
    v
File bytes
~~~

Encoding is not the record format. CSV, fixed-width, delimiters, quotes, and line separators describe how records/fields are split. UTF-8, UTF-16, and Windows-1252 describe how characters are encoded into bytes.

## 2. Common charsets

Some charsets encountered during system integration:

| Charset | Characteristics | Common Use Cases |
| --- | --- | --- |
| UTF-8 | Unicode, variable byte length from 1 to 4 bytes per code point | Modern file exchange, APIs, and multilingual systems |
| UTF-16LE / UTF-16BE | Unicode using 16-bit code units with little-endian or big-endian byte order | Some Windows systems, exports, or legacy applications |
| ISO-8859-1 | Limited 8-bit character set, does not fully cover Vietnamese | Older systems mainly using Western European characters |
| Windows-1252 | 8-bit character set common on Windows in some legacy applications | Legacy CSV files generated from Windows software |
| Shift_JIS | Legacy encoding commonly used for Japanese | Data exchange with legacy Japanese systems |

For new files, UTF-8 is usually the right choice because it supports many languages and is widely used. However, never assume a legacy file is UTF-8. Confirm the contract of the file-producing system.

The charset name must be recognized by the JVM. You can check in Java:

~~~java
Charset charset = Charset.forName("UTF-8");
boolean supported = Charset.isSupported("Windows-1252");
~~~

Prefer standard charset names or constants in StandardCharsets when available. For example:

~~~java
StandardCharsets.UTF_8
StandardCharsets.UTF_16LE
StandardCharsets.ISO_8859_1
~~~

## 3. Why must encoding be declared explicitly?

If unconfigured, the reader/writer may use the JVM's default charset or the implementation's default. The default charset can depend on operating system, locale, runtime, and environment configuration.

A file that works on a laptop may fail when moved to a Linux container or another server:

~~~text
Developer workstation
  default charset = Windows-1252
  -> reads legacy file correctly

Production container
  default charset = UTF-8
  -> the same file may be decoded differently
~~~

Declare encoding according to the data contract, not the host machine:

- The reader must decode with the exact charset used by the source system.
- The writer must encode with the exact charset required by the receiving system.
- Configuration must match across local, test, staging, and production.
- Charsets should be managed in application configuration or file metadata if multiple sources use different encodings.

Do not use a single global charset for every file if partners have different contracts.

## 4. Configuring encoding for FlatFileItemReader

Spring Batch provides FlatFileItemReader to read line by line and map to items. Encoding can be declared via the builder:

~~~java
@Bean
@StepScope
public FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") Resource inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(inputFile)
            .encoding("UTF-8")
            .delimited()
            .names("orderId", "customerName", "amount")
            .targetType(OrderInput.class)
            .linesToSkip(1)
            .saveState(true)
            .build();
}
~~~

In this example:

- Resource specifies the input file.
- encoding("UTF-8") specifies how to decode bytes into characters.
- delimited() configures how fields are split.
- linesToSkip(1) skips the header line.
- saveState(true) allows the reader to save state for restart.

Encoding is applied before the parser processes each line. If the charset is wrong, LineTokenizer or FieldSetMapper may receive a corrupted String from the start. Fixing field mapping will not recover characters that were decoded incorrectly.

### Configuring via setters

If creating the reader directly instead of using the builder, you can configure:

~~~java
FlatFileItemReader<OrderInput> reader = new FlatFileItemReader<>();
reader.setName("orderReader");
reader.setResource(inputFile);
reader.setEncoding("UTF-8");
reader.setLineMapper(orderLineMapper);
reader.setSaveState(true);
~~~

Do not configure encoding after the reader has already opened the resource. Set it completely before the Step starts.

## 5. Configuring encoding for FlatFileItemWriter

When writing files, FlatFileItemWriter converts items into String lines and encodes Strings into bytes. Configure output encoding according to the receiving system's requirements:

~~~java
@Bean
public FlatFileItemWriter<Order> orderWriter(
        Resource outputFile) {

    return new FlatFileItemWriterBuilder<Order>()
            .name("orderWriter")
            .resource(outputFile)
            .encoding("UTF-8")
            .lineAggregator(order ->
                    order.getOrderId() + ","
                    + order.getCustomerName() + ","
                    + order.getAmount())
            .headerCallback(writer ->
                    writer.write("orderId,customerName,amount"))
            .shouldDeleteIfExists(true)
            .build();
}
~~~

In this example, lineAggregator creates a String line. The writer encodes that line into bytes as UTF-8. The header is also written using the same encoding.

If the target system requires Windows-1252 or another legacy charset, configure that exact charset and verify whether output characters can be represented.

### Encoding does not replace CSV escaping

Encoding only determines how characters are encoded. It does not automatically handle commas, double quotes, or newlines inside fields.

Example of a customer name containing a comma:

~~~text
orderId,customerName,amount
1001,"Nguyen, An",250000
~~~

LineAggregator must produce valid CSV according to quoting/escaping rules. A valid UTF-8 line that fails to escape commas can still be misparsed into the wrong columns by the receiver's parser.

## 6. Encoding, delimiters, and line endings are three separate concerns

When integrating files, distinguish:

| Attribute | Example | Role |
| --- | --- | --- |
| Encoding | UTF-8 | Converts bytes to characters |
| Delimiter | Comma, tab, semicolon | Separates fields within a record |
| Quote/escape | Double quote | Protects delimiters or special characters inside a field |
| Line separator | LF or CRLF | Separates records |
| Record layout | CSV or fixed-width | Defines the structure of a record |

A file can use UTF-8 while having CRLF line endings. Another file can use Windows-1252 with LF line endings. Never infer encoding from line endings or delimiters.

FlatFileItemReader processes lines using Java/Spring Batch's text reading mechanism. If a file has multi-line records quoted per CSV rules, configure an appropriate RecordSeparatorPolicy so the reader does not treat every newline as the end of a record.

## 7. UTF-8 and Vietnamese characters

UTF-8 fully supports accented Vietnamese characters. Example strings:

~~~text
Nguyễn Văn An
Đơn hàng mới
Thành phố Hồ Chí Minh
~~~

When reading a UTF-8 file with a UTF-8-configured reader, the parser receives the corresponding Unicode String. When writing a UTF-8 file, the writer converts the String into UTF-8 bytes.

Do not convert a String to bytes using the default charset in another part of the application and then decode it as UTF-8. The following example can cause data loss:

~~~java
byte[] bytes = value.getBytes();
String restored = new String(bytes, StandardCharsets.UTF_8);
~~~

getBytes() without specifying a charset uses the JVM's default charset. Specify the same charset in both directions if byte conversion is truly necessary:

~~~java
byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
String restored = new String(bytes, StandardCharsets.UTF_8);
~~~

In a FlatFileItemReader/Writer flow, let Spring Batch perform the conversion through encoding configuration rather than manually converting bytes/Strings inside each processor.

## 8. Handling UTF-8 BOM

Some tools exporting UTF-8 files add a byte order mark (BOM) at the start of the file. A UTF-8 BOM is typically represented by three bytes EF BB BF and may be decoded into character U+FEFF at the beginning of the string.

If the reader does not strip the BOM, the first field may receive an invisible character. Example:

~~~text
Expected header: orderId,customerName,amount
Actual first field may begin with: U+FEFF + orderId
~~~

This can cause header mapping, column name comparisons, or validation to fail even though the file looks normal in a text editor.

The BOM can be handled at the line-reading layer. For example, wrapping the main LineMapper:

~~~java
DefaultLineMapper<OrderInput> delegate = new DefaultLineMapper<>();
delegate.setLineTokenizer(orderTokenizer);
delegate.setFieldSetMapper(orderFieldSetMapper);

LineMapper<OrderInput> bomAwareMapper = (line, lineNumber) -> {
    String normalizedLine = line;
    if (lineNumber == 1 && line.startsWith("\uFEFF")) {
        normalizedLine = line.substring(1);
    }
    return delegate.mapLine(normalizedLine, lineNumber);
};
~~~

This handles it at the line layer if the BOM was already decoded into U+FEFF. Another option is using a resource/input stream wrapper or a BOM-aware library to strip the BOM before decoding.

Only strip the BOM at the beginning of the file. Do not remove every U+FEFF character at arbitrary positions because that character can appear in real data. Test both files with BOM and without BOM.

## 9. UTF-16 and byte order

UTF-16 uses 16-bit code units and has little-endian or big-endian variants. A UTF-16 file may contain a BOM to indicate byte order. If the contract is known, declare the corresponding charset, such as UTF-16LE or UTF-16BE.

Do not pick generic UTF-16 when a system requires a specific byte order without checking the BOM and decoder behavior. If a file has a BOM while the reader configuration does not handle it as expected, BOM characters may appear in the data or content may be decoded incorrectly.

Example:

~~~java
return new FlatFileItemReaderBuilder<CustomerInput>()
        .name("customerReader")
        .resource(inputFile)
        .encoding("UTF-16LE")
        .delimited()
        .names("customerId", "customerName")
        .targetType(CustomerInput.class)
        .build();
~~~

The charset must match how the system produced the file. Do not use UTF-16LE simply because the file was generated on Windows; verify the actual format.

## 10. Incompatible encodings and corrupted characters

A charset may not be able to represent every character in a String. For example, Windows-1252 cannot represent all Vietnamese characters or characters from many other scripts.

When writing an unrepresentable character, an encoder may replace it with a replacement character depending on configuration. When reading invalid bytes, a decoder may replace them or throw an error depending on how it is initialized. If undetected, the output file may contain question marks or replacement characters while the Job still completes.

Common symptoms:

- Vietnamese characters turn into question marks.
- A character displays as a mojibake sequence.
- The first field has a strange character due to BOM.
- The parser fails because of control characters or invalid bytes.
- The output file cannot be decoded by the receiving system.

### Checking whether a charset supports a character

Java can check encoding capability:

~~~java
CharsetEncoder encoder =
        Charset.forName("Windows-1252").newEncoder();

boolean canEncode = encoder.canEncode("Nguyen Van An");
boolean canEncodeVietnamese =
        encoder.canEncode("Nguyễn Văn An");
~~~

If canEncode returns false, that charset cannot fully represent the string. Do not silently replace characters if business data must be preserved verbatim.

### Strictly handling malformed data

When invalid bytes must be detected instead of silently replaced, use CharsetDecoder with CodingErrorAction.REPORT in a custom input layer:

~~~java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

Reader reader = new InputStreamReader(
        inputStream,
        decoder);
~~~

With FlatFileItemReader, a custom BufferedReaderFactory can be supplied to control how the Reader is created. Properly manage closing the stream in the lifecycle and translate IOException into appropriate read errors. Standard builder encoding configuration does not expose all CodingErrorAction options.

Do not use default replacement mode if data requirements demand detecting and rejecting invalid bytes. Conversely, for legacy sources whose contract permits replacing certain characters, document the rule clearly and test it.

## 11. Unicode normalization

Two strings can look identical while having different Unicode representations. For example, an accented character can be represented by:

- A precomposed code point.
- A base character plus a combining mark.

UTF-8 can encode both representations. Encoding does not perform Unicode normalization itself.

If a system compares strings, searches, or uses names as keys, two different representations may not be equal despite looking identical. Unicode NFC normalization can be applied when the business contract requires it:

~~~java
String normalized = Normalizer.normalize(
        input,
        Normalizer.Form.NFC);
~~~

Do not normalize arbitrarily if data must preserve exact bytes or requires exact reconciliation with the source. Normalization is a content-processing step, distinct from encoding decoding.

## 12. Encoding and restart

A reader can save checkpoints for restart. However, a checkpoint is only meaningful while the resource and decoding remain consistent.

If the initial run read the file as UTF-8 but the restart switches to Windows-1252, the same byte position may produce a different String. If the file is replaced or encoding changes, the reader may resume on wrong data.

Keep stable:

- Resource or input file ID.
- Charset.
- BOM rules.
- Delimiters, quotes, and line separators.
- Record layout and field mapping.
- Data filtering parameters.

The charset can be stored as an identifying JobParameter or metadata attached to the input file if the same Job can read multiple encodings. On restart, reuse the same value to ensure consistent decoding.

If a new file has a different encoding, treat it as a new input/version per business rules rather than reusing an old checkpoint.

## 13. Encoding with MultiResourceItemReader

When reading multiple files, MultiResourceItemReader typically uses a delegate reader to read each resource. Encoding must be configured on the delegate reader:

~~~java
@Bean
@StepScope
public FlatFileItemReader<OrderInput> orderDelegateReader() {
    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderDelegateReader")
            .encoding("UTF-8")
            .delimited()
            .names("orderId", "customerName", "amount")
            .targetType(OrderInput.class)
            .saveState(true)
            .build();
}

@Bean
public MultiResourceItemReader<OrderInput> multiOrderReader(
        Resource[] inputResources,
        FlatFileItemReader<OrderInput> orderDelegateReader) {

    return new MultiResourceItemReaderBuilder<OrderInput>()
            .name("multiOrderReader")
            .resources(inputResources)
            .delegate(orderDelegateReader)
            .saveState(true)
            .build();
}
~~~

The example assumes all resources use UTF-8. If files have different encodings, a single delegate reader with a fixed charset is not sufficient. Group files by encoding or use a reader/decorator that selects the charset based on validated metadata for each resource.

On restart, resource order and file contents must remain stable so the resource index state and delegate state are not applied to the wrong file.

## 14. Testing input encoding

Create fixture files with exact byte encodings rather than simply saving text using an IDE's default encoding.

Scenarios to test:

- UTF-8 with Vietnamese diacritics.
- UTF-8 without BOM.
- UTF-8 with BOM.
- UTF-16LE or UTF-16BE if the system accepts these file types.
- Legacy charsets required by partners.
- Invalid byte sequences.
- Characters unrepresentable in the chosen charset.
- CRLF and LF.
- Fields containing delimiters, quotes, or Unicode characters.

Example creating a UTF-8 file in a test:

~~~java
Path input = tempDir.resolve("orders.csv");
Files.writeString(
        input,
        "orderId,customerName,amount\n"
                + "1001,Nguyễn Văn An,250000\n",
        StandardCharsets.UTF_8);
~~~

Read the file with a UTF-8-configured reader and assert that the customerName field retains its exact content:

~~~java
assertEquals("Nguyễn Văn An", item.getCustomerName());
~~~

For BOM, the fixture can write the BOM bytes before UTF-8 content or use a sample file from the source system. Check the first field after parsing to ensure no unintended U+FEFF character remains.

## 15. Testing output encoding

For writers, do not only check the String before writing. Read back the file's bytes using the exact charset the receiving system will use:

~~~java
String content = Files.readString(
        output,
        StandardCharsets.UTF_8);

assertTrue(content.contains("Nguyễn Văn An"));
~~~

If the contract requires Windows-1252 or UTF-16, read it back using that exact charset. You can compare byte fixtures or check that the charset encoder can represent all content.

A useful round-trip test:

1. Create an item containing representative Unicode characters.
2. Write the item using FlatFileItemWriter with the selected encoding.
3. Read the file back using the same encoding.
4. Compare parsed fields with the original item.
5. Verify header, delimiter, quotes, and line endings.

A round-trip with the same charset is not enough by itself to prove compatibility with a partner. When possible, test the file with the receiving system's tool or parser.

## 16. Managing encoding via configuration

Do not hard-code encodings scattered across multiple readers/writers if the application serves many partners. Centralize configuration using a properties class:

~~~java
@ConfigurationProperties(prefix = "batch.files")
public class BatchFileProperties {

    private String inputEncoding = "UTF-8";
    private String outputEncoding = "UTF-8";

    public String getInputEncoding() {
        return inputEncoding;
    }

    public void setInputEncoding(String inputEncoding) {
        this.inputEncoding = inputEncoding;
    }

    public String getOutputEncoding() {
        return outputEncoding;
    }

    public void setOutputEncoding(String outputEncoding) {
        this.outputEncoding = outputEncoding;
    }
}
~~~

Inject the properties into the reader:

~~~java
@Bean
@StepScope
public FlatFileItemReader<OrderInput> orderReader(
        Resource inputFile,
        BatchFileProperties properties) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(inputFile)
            .encoding(properties.getInputEncoding())
            .delimited()
            .names("orderId", "customerName", "amount")
            .targetType(OrderInput.class)
            .build();
}
~~~

The application must register BatchFileProperties via the appropriate configuration properties mechanism, such as configuration properties scanning or enabling configuration properties. If encoding depends on a partner or individual file, validate the value before creating the reader. Never accept an arbitrary charset name from an input file and use it without an allowlist, because configuration must belong to a trusted system contract.

Log the selected charset name along with the input ID for troubleshooting, without logging full payloads or personal data.

## 17. Common Pitfalls

### Using the JVM default charset

Results may differ between local and production. Declare encoding explicitly on readers and writers.

### Configuring encoding right on the reader but wrong on the writer

Reading a file successfully does not guarantee the exported file matches the contract. Configure input encoding and output encoding separately.

### Confusing encoding with delimiter

UTF-8 does not fix a CSV error where a field contains a comma without quotes. Verify both charset and record format.

### Ignoring the BOM

The BOM can become the first character of a field or header. Check whether files have a BOM and handle it properly at the start of input.

### Decoding a UTF-8 file with a legacy charset

Accented characters can turn into mojibake. Confirm the source's actual charset and configure the reader to match.

### Writing unrepresentable characters

A limited output charset may replace unsupported characters. Check encoding capability and decide to reject, transliterate, or substitute per contract.

### Assuming encoding automatically normalizes Unicode

Two identical-looking strings can have different code point representations. Normalize to NFC/NFD only when business requirements specify it.

### Changing encoding on restart

Old checkpoints may no longer match the decoded content. Keep charset and resource stable within the same JobInstance.

### Using one charset for multiple files with different contracts

The MultiResourceItemReader delegate may misread some files. Group files by charset or select an appropriate reader per resource.

### Checking files only in a text editor

Editors may guess the encoding or substitute invalid characters. Test bytes, charsets, and round-trips in Java.

## 18. Process for configuring encoding in Spring Batch

When building a file pipeline, determine:

1. Which charset does the source system use to generate the file?
2. Which charset does the target system require?
3. Does the file have a BOM, and does the reader need to strip it?
4. Might data contain characters outside a legacy charset's repertoire?
5. Should malformed or unmappable input fail instead of replacing characters?
6. How are delimiters, quotes, escapes, and line endings specified?
7. Does a multi-resource reader have to handle files with different charsets?
8. Is the encoding kept stable across restarts?
9. Do tests include byte fixtures with exact charsets and representative characters?
10. Is the output file read back using the partner's exact charset?

Test on the same JDK and runtime configuration intended for deployment. Document encoding explicitly in file exchange contracts and place charsets under controlled configuration.

## Conclusion

Encoding defines how file bytes are converted to characters and back. In Spring Batch, configure encoding explicitly on FlatFileItemReader and FlatFileItemWriter according to source and target contracts; UTF-8 is typically suitable for new files, while legacy files must use the confirmed charset. Handle BOMs, distinguish encoding from delimiters and line endings, detect invalid or unrepresentable characters, keep charsets stable across restarts, and perform round-trip tests with real bytes. Do not rely on the JVM default charset because it can cause the same Job to produce different results across environments.
