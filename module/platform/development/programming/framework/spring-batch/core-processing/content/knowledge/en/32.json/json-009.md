# Encoding JSON

In Spring Batch, JSON is commonly used as an interchange format between source systems, batch jobs, and target systems. A job may read a list of objects from a JSON file, transform each item, and write results as JSON for another service to consume. To prevent corrupted characters or parse failures across environments, agree on the file's **character encoding** and how the JSON library converts between bytes, characters, and objects.

JSON is a text format. Ultimately a JSON file is a byte sequence decoded under a charset, typically UTF-8. JSON syntax itself also has escaping rules for double quotes, backslashes, and control characters inside strings. These two concepts are related yet distinct:

- **Encoding** converts Unicode characters to bytes or vice versa, such as UTF-8.
- **JSON escaping** represents certain characters inside a JSON string, such as `\"`, `\\`, `\n`, or `\uXXXX`.
- **Serialization** converts objects into JSON text.
- **Deserialization** parses JSON text into objects.

A file can contain valid JSON yet be written in a charset the consumer does not expect; conversely, a UTF-8 file can contain invalid JSON syntax. Therefore, verify both encoding and JSON structure.

## UTF-8 Is the Standard Choice for JSON Interchange

RFC 8259 specifies that JSON text exchanged between open systems must be encoded in UTF-8. Generators should not add a byte order mark (BOM) to JSON transmitted across systems; parsers may ignore a BOM if encountered. In batch systems, choosing UTF-8 for input/output minimizes differences across Windows, Linux, containers, and downstream services.

Example JSON containing Vietnamese text:

```json
{
  "orderId": "DH-1001",
  "customerName": "Nguyễn Thị Ánh",
  "note": "Giao hàng lúc 8 giờ sáng",
  "city": "Hồ Chí Minh"
}
```

Characters such as `ễ`, `ị`, `Á`, and `ồ` are Unicode characters. In UTF-8, each character is represented by one or more bytes. When writing files, the serializer produces JSON text and the writer encodes that text into UTF-8 bytes. When reading, the parser or reader decodes bytes under the matching encoding before parsing JSON.

Do not rely on the machine's default charset. The default charset can differ across developer machines, Windows servers, Linux containers, or differently configured JVMs. Declare UTF-8 explicitly at file and message boundaries.

## Encoding Differs from Escaping

Example of a string with a newline and quotes:

```java
String note = "Khách nói: \"gọi trước\"\nGiao ở quầy";
```

The JSON serializer escapes special characters inside the JSON string. The resulting JSON text can be:

```json
{
  "note": "Khách nói: \"gọi trước\"\nGiao ở quầy"
}
```

When the file is UTF-8 encoded, Unicode characters become UTF-8 bytes, while quotes and newlines are represented per JSON syntax. A consumer parsing JSON recovers the original string.

Do not manually replace Vietnamese text with `\uXXXX` thinking JSON requires escaping Unicode. JSON allows Unicode characters directly inside strings when encoding is valid. Jackson can write Unicode characters directly or escape certain characters depending on configuration; both ways can represent the same value.

For example, these two JSON texts hold the exact same string value:

```json
{"name":"Hồ Chí Minh"}
```

```json
{"name":"H\u1ed3 Ch\u00ed Minh"}
```

Encoding determines the bytes of the entire JSON text. Escape sequences are part of JSON string syntax. Never double-encode—for example, converting a JSON string into UTF-8 bytes and then feeding a string representation of those bytes back into a serializer as text data.

## Unicode and Escape Sequences

JSON strings use double quotes to enclose text. Characters requiring escaping include:

| Character | JSON representation |
| --- | --- |
| Double quote `"` | `\"` |
| Backslash `\` | `\\` |
| Backspace | `\b` |
| Form feed | `\f` |
| Newline | `\n` |
| Carriage return | `\r` |
| Tab | `\t` |
| Control characters U+0000 to U+001F | Corresponding `\u00XX` |

Some characters outside the Basic Multilingual Plane are represented as UTF-16 surrogate pairs in `\uXXXX` escapes. When using Jackson, let the library handle Unicode and escaping; do not split strings `char` by `char` and assemble escape sequences manually, as doing so can corrupt surrogate pairs.

Do not use manual `String.replace` to escape JSON. That approach frequently misses backslashes, control characters, quotes, or surrogate pairs. Use Jackson or a compliant JSON library to serialize and parse.

## JSON Arrays and JSON Lines Are Different Formats

Spring Batch provides JSON components for reading/writing items. Before picking a reader/writer, determine the file structure.

### JSON array

A JSON document can contain an array of multiple objects:

```json
[
  {"orderId":"O-1","amount":120.50},
  {"orderId":"O-2","amount":90.00},
  {"orderId":"O-3","amount":75.00}
]
```

This is a single JSON document whose root is an array. Spring Batch's `JsonItemReader` is designed to read objects in a JSON array structure via `JsonObjectReader`.

### JSON Lines / NDJSON

JSON Lines stores one JSON value per physical line:

```text
{"orderId":"O-1","amount":120.50}
{"orderId":"O-2","amount":90.00}
{"orderId":"O-3","amount":75.00}
```

This is not a single JSON array document. Each line is an independent JSON document. This format suits streaming and line-by-line processing, yet requires an appropriate reader, such as `FlatFileItemReader` with a Jackson-backed `LineMapper`, or a custom `ItemReader`. Do not feed NDJSON directly into `JsonItemReader` expecting it to treat each line as an array element.

| Characteristic | JSON array | JSON Lines / NDJSON |
| --- | --- | --- |
| Structure | Single JSON document with array root | Each line is an independent JSON value |
| Delimiter | `[` `]` and commas between items | Newlines between items |
| Suitable reader | `JsonItemReader` | `FlatFileItemReader` + Jackson or custom reader |
| Easy item streaming | Streamable via parser | Naturally line by line |
| Multi-line single object | Valid inside array | Violates one-JSON-value-per-line convention |

UTF-8 encoding applies to both formats; record structure determines how the reader splits items.

## Reading JSON Arrays with JsonItemReader

Spring Batch provides `JsonItemReader<T>` and the `JsonObjectReader<T>` abstraction. With Jackson, use `JacksonJsonObjectReader<T>` to parse each object in the JSON array.

Model example:

```java
public record OrderInput(
        String orderId,
        String customerName,
        BigDecimal amount) {
}
```

Reader:

```java
@Bean
@StepScope
JsonItemReader<OrderInput> orderJsonReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new JsonItemReaderBuilder<OrderInput>()
            .name("orderJsonReader")
            .resource(new FileSystemResource(inputFile))
            .jsonObjectReader(new JacksonJsonObjectReader<>(OrderInput.class))
            .strict(true)
            .saveState(true)
            .build();
}
```

This reader reads each object in the JSON array and maps it to `OrderInput`. `strict(true)` requires the resource to exist per the reader's strict resource behavior. `saveState(true)` lets the reader save its position to support restart.

`JacksonJsonObjectReader` uses Jackson to parse JSON. When the parser receives a byte stream, Jackson can auto-detect Unicode encodings supported by the JSON parser; however, the system contract should still specify UTF-8 input. Do not rely on auto-detection to accept files in arbitrary encodings sent by producers.

If the application uses a different Spring Batch/Jackson version, check the corresponding constructors and builder APIs in your actual dependencies. JSON APIs have evolved across framework generations, so examples must match the deployed version.

## Configuring ObjectMapper for JSON

`ObjectMapper` controls how Jackson maps objects and JSON. File encoding is a separate layer; `ObjectMapper` primarily determines JSON structure, naming, dates/times, nulls, enums, and data types.

Example mapper configuration for Java time:

```java
@Bean
ObjectMapper batchObjectMapper() {
    return JsonMapper.builder()
            .addModule(new JavaTimeModule())
            .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
            .build();
}
```

`JavaTimeModule` supports types such as `LocalDate`, `LocalDateTime`, and `Instant`. Disabling `WRITE_DATES_AS_TIMESTAMPS` represents dates/times as text rather than numeric timestamps for supported module types.

When configuring `JacksonJsonObjectReader`, pass the configured mapper using the constructor supported by your Spring Batch version:

```java
@Bean
JacksonJsonObjectReader<OrderInput> orderJsonObjectReader(
        ObjectMapper batchObjectMapper) {
    return new JacksonJsonObjectReader<>(
            OrderInput.class,
            batchObjectMapper);
}
```

Then inject this reader into `JsonItemReaderBuilder`. Do not build a differently configured `ObjectMapper` for the writer if both directions share one JSON contract.

### Settings to align

| Setting | Impact |
| --- | --- |
| Property naming strategy | JSON field names like `orderId` vs. `order_id` |
| `JavaTimeModule` | Parse/serialize Java date-time types |
| Date/time format | Text format, timezone, and precision |
| Null inclusion | Whether null fields are written to JSON |
| Enum handling | Use enum names or business codes |
| Number handling | Decimals, integers, and out-of-range numbers |
| Unknown properties | How the reader handles new fields from producers |
| Polymorphic typing | How subtypes are represented if contract requires |

These settings are part of the data contract. Changing naming strategy or date format can prevent old consumers from parsing new files even when the encoding remains UTF-8.

## Reading JSON with Explicitly Specified Encoding

At file boundaries, require producers to write UTF-8 and consumers to read under the same contract. If constructing a `Reader` manually, specify the charset explicitly:

```java
try (BufferedReader reader = Files.newBufferedReader(
        inputPath,
        StandardCharsets.UTF_8)) {
    // Pass reader to appropriate parser.
}
```

`Files.newBufferedReader(path, StandardCharsets.UTF_8)` does not rely on the JVM's default charset. When a JSON library receives a `Reader`, byte decoding has already happened before the parser processes JSON; thus, the charset chosen when creating the `Reader` is decisive.

If the parser receives an `InputStream` directly, Jackson can detect UTF-8/UTF-16/UTF-32 from leading bytes and BOM. Even so, the file protocol should specify UTF-8 so producer and consumer never guess encodings. If you need to reject malformed UTF-8 byte sequences rather than substituting replacement characters, use a `CharsetDecoder` with `CodingErrorAction.REPORT` before parsing.

Strict decoder example:

```java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try (Reader reader = new InputStreamReader(
        Files.newInputStream(inputPath), decoder)) {
    // Pass reader to JSON parser.
}
```

With a strict decoder, invalid byte sequences raise an error instead of silently turning into `�`. This helps pipelines detect corrupted files or producers using the wrong charset.

## BOM in JSON Files

A UTF-8 BOM is the three bytes `EF BB BF` at the start of a file. A BOM can appear when files are produced by certain Windows tools or editors.

RFC 8259 states generators should not add a BOM to exchanged JSON text; parsers may ignore a BOM if encountered. For good interoperability, output UTF-8 JSON without a BOM. For legacy inputs, clearly define whether consumers accept a BOM and test with your actual parser/version.

A common bug occurs when a BOM is decoded into character `U+FEFF` ahead of `[` or `{`, causing the parser library to reject that character at the start of the document. If stripping a BOM, strip only a single leading BOM at the start of the stream; never run `replace("\uFEFF", "")` across the whole content, as it could remove valid data characters elsewhere.

Example checking leading bytes:

```java
byte[] prefix = new byte[3];
try (InputStream input = Files.newInputStream(path)) {
    int count = input.read(prefix);
    boolean hasUtf8Bom = count == 3
            && (prefix[0] & 0xFF) == 0xEF
            && (prefix[1] & 0xFF) == 0xBB
            && (prefix[2] & 0xFF) == 0xBF;
}
```

This is only a detection snippet; if continuing to read the same stream, buffer the read bytes or reopen the stream after checking. In most cases, requiring producers not to write a BOM is simpler.

## Writing JSON with JsonFileItemWriter

Spring Batch provides `JsonFileItemWriter<T>` to write items to a JSON file via `JsonObjectMarshaller<T>`. With Jackson, use `JacksonJsonObjectMarshaller<T>`.

```java
@Bean
JsonFileItemWriter<Order> orderJsonWriter(
        @Value("${batch.output.orders}") Resource outputResource) {

    return new JsonFileItemWriterBuilder<Order>()
            .name("orderJsonWriter")
            .resource(outputResource)
            .jsonObjectMarshaller(new JacksonJsonObjectMarshaller<>())
            .encoding(StandardCharsets.UTF_8.name())
            .saveState(true)
            .build();
}
```

Builder APIs may vary by Spring Batch version; if your version does not provide `encoding(...)` on that builder, configure encoding via the writer/resource API supported by that version or use a custom writer with `OutputStreamWriter(StandardCharsets.UTF_8)`. Never rely on the default charset.

`JsonFileItemWriter` writes items in the JSON format provided by the implementation, typically a JSON array. `JsonObjectMarshaller` converts each object to JSON text; the writer manages file structure and write lifecycle. Do not add `[` or `]` inside the marshaller when the writer already manages the array wrapper.

### Using a custom ObjectMapper for the marshaller

If you need the same date/time, naming, and null behavior as the reader, initialize `JacksonJsonObjectMarshaller` with a configured `ObjectMapper` using the constructor supported by your version:

```java
@Bean
JacksonJsonObjectMarshaller<Order> orderJsonMarshaller(
        ObjectMapper batchObjectMapper) {
    return new JacksonJsonObjectMarshaller<>(batchObjectMapper);
}
```

Then pass the marshaller to the builder. Sharing the same mapper configuration keeps reader and writer on a consistent data contract. Do not mutate mapper configuration after the job starts or while multiple executions share the mapper.

## Writing JSON Lines with FlatFileItemWriter

If downstream requires NDJSON, each item must be serialized into an independent JSON line. You can use `FlatFileItemWriter` with a `LineAggregator` calling Jackson:

```java
@Bean
FlatFileItemWriter<Order> orderJsonLinesWriter(
        ObjectMapper batchObjectMapper,
        @Value("${batch.output.orders-jsonl}") Resource outputResource) {

    return new FlatFileItemWriterBuilder<Order>()
            .name("orderJsonLinesWriter")
            .resource(outputResource)
            .encoding(StandardCharsets.UTF_8.name())
            .lineAggregator(order -> {
                try {
                    return batchObjectMapper.writeValueAsString(order);
                } catch (JsonProcessingException ex) {
                    throw new IllegalArgumentException(
                            "Cannot serialize order " + order.orderId(), ex);
                }
            })
            .saveState(true)
            .build();
}
```

Each item becomes a single-line JSON object. Any newlines inside JSON strings are escaped by Jackson as `\n`, so physical newlines continue separating NDJSON records. Do not write multi-line pretty-printed JSON into this writer, as that breaks the one-JSON-value-per-line rule.

To read NDJSON, use `FlatFileItemReader` and a `LineMapper` parsing each line:

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderJsonLinesReader(
        @Value("#{jobParameters['inputFile']}") String inputFile,
        ObjectMapper batchObjectMapper) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderJsonLinesReader")
            .resource(new FileSystemResource(inputFile))
            .encoding(StandardCharsets.UTF_8.name())
            .lineMapper((line, lineNumber) ->
                    batchObjectMapper.readValue(line, OrderInput.class))
            .saveState(true)
            .build();
}
```

The example above assumes each JSON value fits on a single line. If an NDJSON producer emits one object across multiple physical lines, the file no longer obeys the line-delimited convention; adjust the format or use a fitting reader/parser.

## Encoding for FlatFileItemReader and FlatFileItemWriter

For JSON Lines, `FlatFileItemReaderBuilder` and `FlatFileItemWriterBuilder` provide encoding settings. Set UTF-8 explicitly:

```java
.encoding(StandardCharsets.UTF_8.name())
```

The reader decodes bytes into text before `LineMapper` parses JSON. The writer encodes text produced by `LineAggregator` into bytes using the configured charset.

For `JsonItemReader`, encoding may be handled inside `JsonObjectReader`/the JSON parser because the reader takes a `Resource` and the parser operates on a stream. Check the API of your Spring Batch/Jackson version for the exact configuration point. If strict UTF-8 enforcement is required, use a custom `JsonObjectReader` or a resource/stream adapter decoding with the specified charset.

Do not assume `.encoding(...)` exists on every JSON reader builder or version. Distinguish the API of `FlatFileItemReader` from that of `JsonItemReader`.

## Dates, Times, and Timezones in JSON

Correct encoding does not guarantee dates/times have the same meaning between producer and consumer. JSON defines no dedicated date/time type; dates/times are usually represented as strings or numbers per application contract.

ISO-8601 example:

```json
{
  "businessDate": "2026-11-15",
  "createdAt": "2026-11-15T08:30:00",
  "createdInstant": "2026-11-15T01:30:00Z"
}
```

These values carry different meanings:

- `LocalDate` is only a date, with no time or timezone.
- `LocalDateTime` has date and time, with no offset/timezone.
- `Instant` is a UTC instant.
- `OffsetDateTime` has an explicit offset.

For cross-system interchange, prefer ISO-8601 with an offset or UTC `Z` when an instant must be identified. Do not write `LocalDateTime` and leave consumers guessing the timezone. If using numeric timestamps, specify epoch, milliseconds/seconds unit, and timezone semantics.

Model example:

```java
public record OrderEvent(
        String orderId,
        LocalDate businessDate,
        Instant createdAt) {
}
```

`ObjectMapper` needs `JavaTimeModule` and an agreed format. Round-trip tests must confirm temporal values neither shift timezones nor lose precision.

## Decimals and Numbers in JSON

JSON numbers carry no precision/scale metadata. If `BigDecimal` is serialized as a number, consumers must parse with decimal semantics rather than passing through `double` and losing precision.

Example:

```json
{
  "amount": 1234567890.123456789
}
```

For currency, use `BigDecimal` in Java and configure/test consumers to preserve decimal precision. Do not use `double` for financial calculations merely because JSON numbers can parse as floating point.

Some systems choose to represent money as strings to preserve scale/formatting per contract:

```json
{
  "amount": "1234567890.123456789",
  "currency": "VND"
}
```

This is an API schema decision, not an encoding requirement. Producer and consumer must agree on whether the field type is number or string.

## Nulls, Missing Fields, and Backward Compatibility

In JSON, a field can be missing, have value `null`, or have a concrete value. These three states can carry different business meanings.

```json
{"orderId":"O-1"}
```

```json
{"orderId":"O-1","note":null}
```

```json
{"orderId":"O-1","note":"Gọi trước"}
```

`ObjectMapper` can be configured to omit null fields or write `null`. Readers need explicit defaults/validation when fields are missing. Changing `Include.NON_NULL` or naming strategies can change the JSON contract even while encoding stays UTF-8.

When producers add new fields, readers should have a suitable unknown-property policy. Failing on unknown properties can cause older batches to fail on a new field. Ignoring unknown fields requires ensuring mandatory fields are still validated.

## Encoding Errors and Mojibake

Mojibake occurs when characters display wrongly because bytes are decoded with a different charset from the one used to encode them. For instance, reading UTF-8 bytes as Windows-1252 or a legacy code page can turn Vietnamese text into garbled character sequences.

Symptoms:

- Vietnamese text appears as `Nguyá»…` or unexpected characters.
- Files look right in one editor yet read wrongly at batch runtime.
- Jobs succeed on Windows yet read differently inside a Linux container.
- Downstream receives `�` (replacement character).
- JSON parser reports malformed input or byte-sequence errors.

Common causes:

- Producer writes using the machine's default charset.
- Reader uses default charset instead of UTF-8.
- A system encodes UTF-8 twice.
- Files are converted through an intermediate tool that alters encoding.
- BOM or invalid byte sequence at the start of the file.
- JSON strings manually escaped incorrectly.

Do not fix mojibake by string-replacing displayed characters without identifying the original bytes. Inspect the byte sequence, producer charset, and consumer decoder, then fix at the encode/decode boundary.

## Do Not Double-Encode JSON

A common mistake is serializing an object into a JSON string and then serializing that string a second time:

```java
String json = objectMapper.writeValueAsString(order);
String wrapped = objectMapper.writeValueAsString(json);
```

`wrapped` is a JSON string containing JSON content, not a JSON object. Example:

```json
"{\"orderId\":\"O-1\",\"amount\":100}"
```

Whereas the consumer expects:

```json
{"orderId":"O-1","amount":100}
```

With `JsonFileItemWriter`, pass the object and marshaller so the writer serializes once. With NDJSON, `LineAggregator` serializes the object once per item. Never call `writeValueAsString` beforehand and let Jackson serialize that string as a JSON value a second time.

## Inspecting Output Bytes Instead of Only Viewing Text

Editors can guess encodings or display already-decoded text. To verify a file is UTF-8, read bytes and decode as UTF-8 in tests:

```java
byte[] bytes = Files.readAllBytes(outputPath);
String decoded = new String(bytes, StandardCharsets.UTF_8);

assertTrue(decoded.contains("Nguyễn Thị Ánh"));
assertFalse(decoded.startsWith("\uFEFF"));
```

For large files, do not use `readAllBytes` in production; this example is only suitable for small test files. Tests should also re-parse JSON with Jackson to confirm valid structure:

```java
JsonNode root = objectMapper.readTree(outputPath.toFile());
assertEquals("Nguyễn Thị Ánh",
        root.get(0).get("customerName").asText());
```

If output is NDJSON, parse each line separately rather than calling `readTree` on the whole file as a single JSON document.

## Restart and JSON Files

JSON readers/writers can participate in restart when implementations support `ItemStream` and save state. `JsonItemReader` and `JsonFileItemWriter` have state mechanisms in supporting versions; use stable names and enable `saveState` when restart is desired.

Principles:

- Keep input files immutable throughout the job lifecycle and restart window.
- Use the same identifying `JobParameters` when restarting the same `JobInstance`.
- Keep reader/writer names and JSON configuration compatible.
- Keep encoding and JSON schema unchanged between initial run and restart.
- Do not replace the input file with different content at the same path.
- Output files from incomplete runs must be retained or handled via staging/restart procedures.

Changing `ObjectMapper` configuration between initial run and restart can serialize the same item in a different format. This is especially important for partially written output files. Version schemas/formats and keep configs compatible while an execution may restart.

### Output files and transactions

File output does not always participate in `JobRepository`'s database transaction. If the process dies after writing bytes but before metadata commits, the file may contain output from a chunk not yet recorded in the checkpoint. Writers supporting transactional/restart semantics can handle some scenarios, yet you should not assume filesystems provide ACID transactions like databases.

For critical outputs, consider writing to an execution-scoped temporary file, saving writer checkpoints, and publishing/renaming the file upon job completion. If restart is needed, retain the temporary file and reuse the same path. On certain filesystems or object storage, rename may not be atomic; use manifests/versions and checksums.

## Validating JSON Before Running Batch Jobs

Encoding and syntax should be verified during ingestion or at the start of the job:

1. Check file existence and reasonable size.
2. Verify the input contract mandates UTF-8.
3. Check BOM per system policy.
4. Parse JSON with a streaming parser if the file is large.
5. Verify root structure matches array or NDJSON.
6. Validate required fields, types, and schema version.
7. Record checksum/version so restarts read the exact resource.

Do not parse an entire large file into a single `JsonNode` or `List` merely for validation if the job requires streaming. Use a streaming parser or `JsonItemReader` to avoid holding the whole dataset in memory.

## Handling Encoding and Parse Errors

Distinguish error types to select appropriate actions:

| Error | Example | Generally appropriate action |
| --- | --- | --- |
| Invalid byte encoding | Malformed UTF-8 sequence | Fail file, quarantine, and request producer resend |
| Wrong charset but valid bytes in another charset | Mojibake | Fix contract/decoder; do not guess in production |
| Invalid JSON syntax | Missing `]`, unclosed quote | Fail or quarantine; retrying will not fix an immutable file |
| JSON schema/data error | Missing `orderId`, wrong amount type | Validate, reject record, or skip per business rules |
| Transient I/O | Network mount disconnected | Retry with bounded count and timeout |
| Resource does not exist | File moved/deleted | Check claim/archive and metadata |

Do not configure broad skip for every exception from a JSON reader. If the byte stream or array structure is corrupted, the reader may be unable to identify the next item boundary. Skipping is only safe when record boundaries can be recovered and business rules allow dropping items.

## Testing JSON Encoding

Test serialization, deserialization, and file I/O. Unit testing `ObjectMapper` does not prove the writer wrote UTF-8; real file tests check byte encoding.

### Unicode round-trip

Create objects with Vietnamese text, special characters, emoji, and multi-line strings; serialize and parse back:

```java
@Test
void roundTripsUnicodeAndEscapedCharacters() throws Exception {
    OrderInput original = new OrderInput(
            "O-1001",
            "Nguyễn Thị Ánh 😀",
            new BigDecimal("123456.78"));

    String json = objectMapper.writeValueAsString(original);
    OrderInput restored = objectMapper.readValue(json, OrderInput.class);

    assertEquals(original, restored);
}
```

This test verifies the mapper preserves Unicode data in memory. Add file tests to verify charset bytes.

### Writing and reading UTF-8 files

For writers, create a temporary output, write items with Vietnamese text, read bytes as UTF-8, and re-parse. Verify the file has no BOM if the contract requires no-BOM.

For readers, create files via `Files.writeString(path, json, StandardCharsets.UTF_8)`, run the reader, and verify objects receive the exact Vietnamese names/notes. Do not generate fixtures with the default charset because tests might only pass on one machine.

### Testing JSON arrays and NDJSON separately

Do not share fixtures across the two formats. JSON arrays must have root `[` ... `]`; NDJSON must have one JSON value per line. Verify the selected reader fits the format and fails clearly when input structure is wrong.

### Testing BOM and malformed bytes

Create a fixture with a UTF-8 BOM and confirm behavior per policy: accept and strip the BOM, or reject with a clear error. Create invalid UTF-8 byte sequences and confirm strict decoders throw an error instead of silently creating replacement characters.

### Testing dates/times and decimals

Round-trip `BigDecimal`, `LocalDate`, `Instant`, and `OffsetDateTime`. Compare exact values, including scale/precision and offset/timezone semantics. Do not compare raw JSON strings alone unless property ordering is part of the contract.

### Testing restart

Run the job across several chunks, fail the step, then restart with the same identifying parameters. Confirm the reader resumes at the right item, the writer resumes output at the right position, and final JSON parses cleanly. If the writer writes a JSON array, confirm there is one pair of brackets and proper commas; if writing NDJSON, confirm each line parses independently.

## Common Pitfalls

### Using the default charset

Files may read properly on one machine yet fail on another. Specify UTF-8 explicitly at writer/reader or parser boundaries.

### Confusing encoding with escaping

`\\uXXXX` is not a charset. Let Jackson handle escaping; let UTF-8 handle byte representation.

### Manually escaping JSON with replace

Can miss backslashes, control characters, or surrogate pairs. Use `ObjectMapper`.

### Reading NDJSON with JsonItemReader

`JsonItemReader` reads JSON array structures via `JsonObjectReader`; NDJSON requires a line-based or custom reader.

### Writing multi-line pretty JSON to NDJSON

A single object can span multiple lines and break record boundaries. Use compact single-line JSON per item.

### Double serializing

Serializing an object to a string and serializing that string again produces a JSON string containing JSON, not a JSON object. Serialize exactly once.

### Ignoring BOMs and malformed files

BOMs or invalid byte sequences can break parsers or produce replacement characters. Define explicit policies and test them.

### Changing ObjectMapper across restarts

Different schemas, naming, or date formats can make output files inconsistent. Keep configuration stable for a logical execution.

### Testing text only in an editor

Editors can guess charsets. Check bytes with a UTF-8 decoder and re-parse JSON.

### Assuming JSON numbers automatically preserve all precision

Consumers may parse numbers as floating point. Use `BigDecimal` and align schemas for currency.

## Implementation Guidelines

When designing JSON input/output for Spring Batch, verify:

1. Does the contract mandate UTF-8, and is a BOM permitted?
2. Is the file a JSON array or JSON Lines/NDJSON?
3. Is the appropriate reader `JsonItemReader`, `FlatFileItemReader`, or a custom streaming reader?
4. Is the appropriate writer `JsonFileItemWriter` or `FlatFileItemWriter` with one JSON object per line?
5. Is the charset set explicitly at the exact byte/text boundary?
6. Does `ObjectMapper` have stable naming, date/time, null, enum, and number policies?
7. Are Unicode, escaping, control characters, and surrogate pairs handled by the library?
8. How are malformed inputs, BOMs, and invalid byte sequences handled?
9. Are reader/writer state, file paths, and mapper configuration compatible on restart?
10. Do tests verify byte output, Unicode round-trip, format structure, precision, and restart?

For most JSON interchange pipelines, use UTF-8 without BOM, Jackson for serialization/deserialization, and an explicit schema per data version. Choose `JsonItemReader`/`JsonFileItemWriter` for JSON arrays; choose line-based readers/writers for NDJSON. Always separate byte encoding from JSON escaping, keep mapper configuration stable, and test actual file bytes to catch errors before data reaches downstream systems.

## Summary

JSON is text; UTF-8 encodes Unicode characters into bytes, while JSON escaping represents quotes, backslashes, newlines, and control characters inside strings. Use UTF-8 explicitly and avoid BOMs in exchanged output; do not rely on default charsets or escape manually with `replace`. `JsonItemReader` fits JSON arrays via `JsonObjectReader`/Jackson; NDJSON requires line-based or custom readers. `JsonFileItemWriter` writes JSON objects according to file structure, while NDJSON uses `FlatFileItemWriter` with one compact JSON object per line. Configure `ObjectMapper` consistently for naming, Java time, nulls, enums, and decimals. Keep input/output resources and mapper contracts stable across restarts, distinguish encoding errors from JSON/schema errors, and test Unicode round-trips along with actual byte output.
