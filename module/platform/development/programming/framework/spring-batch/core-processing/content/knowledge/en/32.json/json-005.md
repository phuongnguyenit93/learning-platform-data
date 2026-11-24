# Root Array and Item Separator

In Spring Batch, `JsonItemReader<T>` reads items from a JSON document that has an array structure at the root level. Each element of the array is a JSON object converted into a Java object via `JsonObjectReader`, such as `JacksonJsonObjectReader`.

A key point to understand clearly is that the comma between elements is not a custom delimiter like in CSV. It is a separator defined by JSON syntax. The JSON parser understands object, array, string, and escape-sequence structure, so commas inside strings or nested structures will not mistakenly split items.

Therefore, `JsonItemReader` suits documents of the form `[ { ... }, { ... } ]`. It does not treat each line as an item, nor does it automatically read JSON Lines, multiple consecutive JSON objects, or an array nested inside a root object's property.

## 1. What Is a Root Array?

JSON can represent a single object, an array, a string, a number, a boolean, or null at the root level. `JsonItemReader` is designed to read a list of items from a root array.

Example `trades.json` file:

```json
[
  {
    "tradeId": "T1001",
    "symbol": "ACME",
    "quantity": 10,
    "price": 125.50
  },
  {
    "tradeId": "T1002",
    "symbol": "NOVA",
    "quantity": 5,
    "price": 82.25
  },
  {
    "tradeId": "T1003",
    "symbol": "ACME",
    "quantity": 7,
    "price": 126.00
  }
]
```

The root of the document is the square brackets `[` and `]`. Each object inside the array is one item. The reader returns each `Trade` when Spring Batch calls `read()`; once the last element has been read, the next call returns `null`.

```text
trades.json
    |
    v
Root array [ ... ]
    |
    +--> first object  -> Trade T1001
    |
    +--> second object -> Trade T1002
    |
    +--> third object  -> Trade T1003
    |
    v
EOF -> read() returns null
```

Each object in the array must have a structure compatible with the Java type that `JsonObjectReader` is configured to create. If objects have differing fields, clearly define mapping, optional fields, and validation.

## 2. The Item Separator Is the Comma per JSON Syntax

In a JSON array, values at the same level are separated by commas. With `JsonItemReader`, that comma is part of JSON syntax and is handled by the parser.

```json
[
  { "tradeId": "T1001", "quantity": 10 },
  { "tradeId": "T1002", "quantity": 5 },
  { "tradeId": "T1003", "quantity": 7 }
]
```

There is no property like `delimiter(',')` to customize the item separator for `JsonItemReader`. If you want to use another separator character, the data is no longer a standard JSON array and requires a different format or reader.

JSON allows spaces, tabs, and newlines around tokens. Thus, the following forms have the exact same meaning:

```json
[{"tradeId":"T1"},{"tradeId":"T2"}]
```

```json
[
  { "tradeId": "T1" },
  { "tradeId": "T2" }
]
```

Newlines only make reading easier for humans. They are not item separators; the comma is what separates two values in an array.

## 3. Commas Inside an Object Do Not Split Items

A JSON object can have multiple properties, each separated by a comma. The parser distinguishes commas between properties from commas between objects thanks to curly-brace and square-bracket structure.

```json
[
  {
    "tradeId": "T1001",
    "customer": {
      "id": "C01",
      "name": "An Nguyen"
    },
    "tags": ["priority", "online"],
    "quantity": 10
  },
  {
    "tradeId": "T1002",
    "customer": {
      "id": "C02",
      "name": "Binh Tran"
    },
    "tags": ["retail"],
    "quantity": 5
  }
]
```

The first object has commas between `tradeId`, `customer`, `tags`, and `quantity`; the nested `customer` object also has its own comma; the `tags` array has its own comma. None of the commas inside those structures terminates an item in the root array.

The reader relies on the JSON parser to recognize structure rather than splitting strings by commas.

## 4. Commas Inside Strings Are Not Separators

String values can contain commas. The JSON parser keeps those commas as part of the string's content.

```json
[
  {
    "tradeId": "T1001",
    "customerName": "Nguyen, An",
    "note": "Bought shares, then transferred them"
  },
  {
    "tradeId": "T1002",
    "customerName": "Tran, Binh",
    "note": "Reviewed, approved"
  }
]
```

There is no need to quote fields under CSV rules. JSON strings are always enclosed in double quotes and special characters must be escaped per JSON grammar. The parser knows a comma is inside a string via its string-reading state.

For example, a double quote inside a string must be escaped:

```json
{ "note": "Customer said: \"please review\"" }
```

If you write custom code to split items with `String.split(",")`, data containing strings with commas or nested objects/arrays will be split incorrectly. Let the JSON parser handle tokens and structure.

## 5. No Trailing Commas in Standard JSON

A JSON array requires a comma between two elements, but must not have a comma after the last element.

Correct:

```json
[
  { "tradeId": "T1" },
  { "tradeId": "T2" }
]
```

Incorrect:

```json
[
  { "tradeId": "T1" },
  { "tradeId": "T2" },
]
```

A trailing comma may be accepted by some parsers in extended mode, but it is not part of standard JSON. Do not rely on permissive configuration because the file may fail to parse in other environments or parsers.

It is also invalid if the separator is missing:

```json
[
  { "tradeId": "T1" }
  { "tradeId": "T2" }
]
```

If two objects sit adjacent without a comma, the document is invalid. The reader will report a parse error rather than guessing item boundaries.

## 6. Empty Root Array

An empty root array is valid JSON:

```json
[]
```

In this case, the reader returns no items and `read()` returns `null` immediately upon reaching the end of the array. The Step can complete with a read count of 0 if business rules allow empty inputs.

Distinguish an empty root array from an empty resource or a file containing only whitespace. `[]` is a valid JSON document with zero items; a file containing no JSON document may be malformed input. Clearly define whether the job accepts empty files and verify with appropriate validation.

## 7. Root Must Be an Array, Not an Object Containing an Array

The following format is a JSON object whose `trades` property holds an array:

```json
{
  "batchId": "B20261115",
  "trades": [
    { "tradeId": "T1", "quantity": 10 },
    { "tradeId": "T2", "quantity": 5 }
  ]
}
```

This is not a root array. Standard `JsonItemReader` expects an array at the root level, so it does not automatically step into the `trades` property to emit objects.

If the source has an envelope object like above, there are several options:

- Use a custom `ItemReader` with a Jackson streaming parser to open the root object, locate the `trades` property, and read each element.
- Use a preprocessing step to convert the envelope into a root array in an immutable resource.
- If the envelope structure is small with a well-bounded size, read the document with a dedicated component and build a reader over the list; avoid loading large datasets completely into memory.

Do not strip the wrapper using simple string slicing. Use a parser to preserve escaping, nested objects, Unicode, and valid structure.

## 8. Configuring JsonItemReader in Spring Batch 5

`JsonItemReader<T>` uses the `JsonObjectReader<T>` abstraction to read each object. You can use `JacksonJsonObjectReader` when the application uses Jackson.

```java
@Bean
@StepScope
JsonItemReader<Trade> tradeJsonReader(
        @Value("#{jobParameters['input.file']}") String inputFile) {

    return new JsonItemReaderBuilder<Trade>()
        .name("tradeJsonReader")
        .resource(new FileSystemResource(inputFile))
        .jsonObjectReader(new JacksonJsonObjectReader<>(Trade.class))
        .strict(true)
        .saveState(true)
        .build();
}
```

Key parts:

- `name`: stable reader name, used to save/restore state.
- `resource`: JSON file containing a root array.
- `jsonObjectReader`: parser/mapping implementation to convert each object into `Trade`.
- `strict(true)`: requires the resource to exist per the reader's strict policy.
- `saveState(true)`: saves reading progress to `ExecutionContext` to support restart.
- `@StepScope`: allows resolving the input file from `JobParameters` when the step starts.

Ensure the Jackson dependency is compatible with the application's Spring Batch and Spring Boot versions. If the project uses Gson, use the corresponding `GsonJsonObjectReader` implementation instead of Jackson.

## 9. Declaring a Chunk Step Using JsonItemReader

The reader can be wired to a processor and writer like other readers:

```java
@Bean
Step importTradesStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Trade> tradeJsonReader,
        ItemProcessor<Trade, Trade> tradeProcessor,
        ItemWriter<Trade> tradeWriter) {

    return new StepBuilder("importTrades", jobRepository)
        .<Trade, Trade>chunk(100, transactionManager)
        .reader(tradeJsonReader)
        .processor(tradeProcessor)
        .writer(tradeWriter)
        .build();
}
```

Chunk size 100 means the step processes up to 100 items in a chunk transaction as configured. The reader returns each object; the processor can validate/transform; the writer writes the processed chunk.

There is no need to pass commas into the processor or writer to split items. The separator has already been handled at the JSON parser layer before the object is returned.

## 10. Configuring Object Mapping

The Jackson reader maps each JSON object into a Java class or record. Example:

```java
public record Trade(
        String tradeId,
        String symbol,
        int quantity,
        BigDecimal price) {
}
```

JSON object:

```json
{
  "tradeId": "T1001",
  "symbol": "ACME",
  "quantity": 10,
  "price": 125.50
}
```

JSON properties must be compatible with Java mapping. If field names differ, you can use Jackson annotations such as `@JsonProperty`; if date/number formats are special, configure appropriate serializers/deserializers or Jackson modules.

Successful deserialization does not mean business-valid data. For instance, `quantity` could be negative or `price` null; validate these rules in a processor or validator.

## 11. Data Types and Null Values

JSON distinguishes string, number, boolean, null, object, and array. Do not assume every value is a string.

| JSON value | Commonly used Java type |
|---|---|
| `"T1001"` | `String` |
| `10` | `int`, `long`, or corresponding wrapper |
| `125.50` | `BigDecimal` for decimal values requiring precision |
| `true` | `boolean` or `Boolean` |
| `null` | `null` with reference types |
| `{ ... }` | Nested class/record |
| `[ ... ]` | `List<T>` or appropriate collection |

For currency or decimals requiring precision, use `BigDecimal` instead of `double`. For fields that may be missing or null, use wrapper/nullable types and define explicit defaults in the processor.

JSON numbers carry no metadata about business scale. If `125.50` and `125.5` must be distinguished in input formatting, store the raw representation or apply separate validation; deserializing into `BigDecimal` can normalize numeric representation.

## 12. Nested Arrays and Nested Objects

A root item can contain nested structures:

```json
[
  {
    "tradeId": "T1",
    "customer": {
      "customerId": "C1",
      "name": "An Nguyen"
    },
    "allocations": [
      { "account": "A1", "quantity": 4 },
      { "account": "A2", "quantity": 6 }
    ]
  }
]
```

The entire object inside the root array remains a single item. The `allocations` array does not create extra items for `JsonItemReader`; it maps to a collection inside the `Trade` object.

This is the difference between the root item separator and commas at nested levels. Only direct values in the root array are separate items.

## 13. JSON Lines Is Not the Same as a Root Array

JSON Lines (NDJSON) typically stores one JSON object per line, without root array square brackets and without commas between lines:

```text
{"tradeId":"T1","quantity":10}
{"tradeId":"T2","quantity":5}
{"tradeId":"T3","quantity":7}
```

This is not a root-array JSON document. Newline is the record boundary under the JSON Lines convention, whereas in standard JSON newline is merely whitespace and does not separate two root values.

`JsonItemReader` is designed for root arrays; do not use it on JSON Lines files expecting newlines to become item separators.

For JSON Lines, you can use `FlatFileItemReader` to read line by line and Jackson `ObjectMapper` to parse each line:

```java
@Bean
@StepScope
FlatFileItemReader<Trade> tradeJsonLinesReader(
        @Value("#{jobParameters['input.file']}") String inputFile,
        ObjectMapper objectMapper) {

    return new FlatFileItemReaderBuilder<Trade>()
        .name("tradeJsonLinesReader")
        .resource(new FileSystemResource(inputFile))
        .lineMapper((line, lineNumber) ->
            objectMapper.readValue(line, Trade.class))
        .strict(true)
        .saveState(true)
        .build();
}
```

This example assumes each line contains exactly one complete JSON object. If blank lines, comments, or multi-line records appear, define an explicit handling policy. With JSON Lines, do not add commas between lines.

## 14. Multiple Consecutive JSON Objects Without a Root Array

A file like this is not a standard JSON document:

```text
{"tradeId":"T1"}
{"tradeId":"T2"}
```

This can be NDJSON if each line is independent, but it is not a JSON array. If objects simply follow one another with no clear record convention, the reader cannot rely on JSON grammar to determine item boundaries.

Do not add or strip `[` `]` and commas using string manipulation if content may contain nested structures or escaped characters. Use a parser or transform the source under a controlled process.

## 15. A Single Root Object

The following JSON is a single root object:

```json
{
  "tradeId": "T1001",
  "symbol": "ACME",
  "quantity": 10
}
```

If the job only needs to read a single object, you can use a tasklet or custom reader that reads one document and returns the object once. If you want to use `JsonItemReader`, represent the input as a root array containing one object:

```json
[
  {
    "tradeId": "T1001",
    "symbol": "ACME",
    "quantity": 10
  }
]
```

The root-array representation keeps the same reader contract for both single-item and multi-item files.

## 16. Strict Resource Handling and Empty Files

A missing resource, a zero-byte file, and a file containing `[]` are three distinct cases.

| Input | Meaning | Behavior to define |
|---|---|---|
| File does not exist | Wrong path or file has not arrived | Typically fail if input is required |
| Zero-byte file | No JSON document | Typically malformed input or missing data |
| File with only whitespace | No JSON value | Treat as invalid input if schema requires a root array |
| `[]` | Valid JSON root array with no items | Reader finishes with zero items |

Do not use `strict(false)` to turn a missing required file into a successful job with zero items. Validate resources and empty-input policies before processing.

## 17. Syntax Errors and Mapping Errors

Two groups of errors can be distinguished:

- **JSON structural errors:** missing comma, missing bracket, trailing comma, unclosed string, or invalid token.
- **Mapping/data-type errors:** valid JSON, but field cannot convert to the Java type or mismatches the class.

Structural error example:

```json
[
  { "tradeId": "T1" },
  { "tradeId": "T2" },
]
```

Example of valid JSON that may fail mapping if `quantity` is an integer in the class:

```json
[
  { "tradeId": "T1", "quantity": "many" }
]
```

Do not broadly skip all parse exceptions. An error mid-array may leave the parser unable to locate the continuation point; whole-document structural errors typically need to fail the file. Single-object mapping errors may be handled differently if the parser can continue safely and business rules permit.

## 18. Checkpoint and Restart of JsonItemReader

`JsonItemReader` supports `ItemStream` and saves reading progress in `ExecutionContext` when `saveState` is enabled. When a chunk commits, reader state is updated so restart continues from the next item after the checkpoint.

```java
return new JsonItemReaderBuilder<Trade>()
    .name("tradeJsonReader")
    .resource(new FileSystemResource(inputFile))
    .jsonObjectReader(new JacksonJsonObjectReader<>(Trade.class))
    .saveState(true)
    .build();
```

To restart accurately:

- Keep the reader name stable between run and restart.
- Keep the same identifying `JobParameters` to restart the same `JobInstance`.
- Keep the file's contents and object order unchanged.
- Use a durable `JobRepository` to store `ExecutionContext`.
- Ensure the writer and side effects are safe when uncommitted items are reread.

The reader's checkpoint tracks item progress, not an arbitrary byte offset in the file. The reader may need to reopen the resource and step past checkpointed items to restore its position. For large files, restart time can depend on how many items must be skipped.

## 19. Do Not Replace the JSON File Between Run and Restart

Suppose the initial run reads 1,000 items and checkpoints after committing 600 items. If the file is replaced by a new file with a different object order, the reader may skip the first 600 objects of the new file and continue from an object unrelated to the original run.

Measures:

- Place files in immutable storage keyed by batch ID or source ID.
- Record the file checksum or version before launch.
- Include source ID/version/checksum in identifying `JobParameters` if they identify business data.
- Do not overwrite the resource while the `JobInstance` can still restart.
- Keep a stable manifest if the job reads multiple files.

Do not rely solely on filename if the provider may reuse the same name for different contents.

## 20. Multiple JSON Files

If there are multiple root-array JSON files, you can use `MultiResourceItemReader` with `JsonItemReader` as delegate. The resource list must have a stable order so restarts restore the right file and item.

```java
@Bean
@StepScope
MultiResourceItemReader<Trade> allTradeFilesReader(
        @Value("#{jobParameters['input.directory']}") String directory,
        JsonItemReader<Trade> tradeJsonReader) throws IOException {

    Resource[] resources = new PathMatchingResourcePatternResolver()
        .getResources("file:" + directory + "/*.json");
    Arrays.sort(resources, Comparator.comparing(Resource::getFilename));

    return new MultiResourceItemReaderBuilder<Trade>()
        .name("allTradeFilesReader")
        .resources(resources)
        .delegate(tradeJsonReader)
        .saveState(true)
        .build();
}
```

This is an overview configuration; ensure the delegate reader has a scope and lifecycle compatible with the wrapper in the version in use. The file list must be immutable or snapshotted in a manifest. Adding a file that sorts ahead of older files can shift the resource index stored in the checkpoint.

## 21. JSON Root Arrays and Item Separators in XML Namespaces

JSON does not have namespaces in the way XML uses namespace URIs/prefixes. Property names like `tradeId` are mapped according to the JSON mapper's rules. If upstream APIs use differing property names, use annotations or mapper config rather than trying to handle them with delimiters.

Example:

```java
public record Trade(
        @JsonProperty("trade_id") String tradeId,
        @JsonProperty("qty") int quantity) {
}
```

JSON:

```json
[
  { "trade_id": "T1", "qty": 10 },
  { "trade_id": "T2", "qty": 5 }
]
```

The separator between two objects is still the root array's comma; `@JsonProperty` only controls property name mapping.

## 22. Keeping Item Separators Valid When Generating Input Files

If an upstream system generates JSON files for Spring Batch, the file must be serialized using a JSON generator or JSON library rather than concatenating object strings manually.

Avoid creating files via:

```java
writer.write("[" + object1 + "," + object2 + "]");
```

String concatenation easily creates invalid JSON when objects contain quotes, newlines, Unicode characters, or commas. Use `ObjectMapper` or a JSON generator:

```java
ObjectMapper objectMapper = new ObjectMapper();
objectMapper.writeValue(outputFile, trades);
```

The JSON library handles escaping and commas between array elements automatically. For very large outputs, consider a streaming generator so the entire collection does not need to stay in memory.

## 23. Common Pitfalls

| Mistake | Consequence | Fix |
|---|---|---|
| Using root object instead of root array | `JsonItemReader` does not read under the expected item contract | Wrap items in a root array or use a custom reader for envelopes |
| Expecting newlines to separate items | Multiple objects do not form a valid JSON array | Use a root array or a dedicated JSON Lines reader |
| Calling `split(',')` to separate objects | Commas in strings/nested objects corrupt records | Use a JSON parser |
| Missing comma between two items | Malformed JSON | Serialize with a JSON library |
| Trailing comma after last item | Not standard JSON | Remove trailing separator |
| Using `JsonItemReader` for NDJSON | Reader expects a root array | Use `FlatFileItemReader` with a JSON mapper per line |
| Confusing nested arrays as separate items | Child collections split incorrectly | Map the entire root object as one item |
| Treating empty files as `[]` | Masks invalid sources | Distinguish zero-byte files from empty root arrays |
| Replacing file before restart | Item-count checkpoint points to wrong data | Keep input immutable and store source version |
| Skipping whole-file JSON structural errors | Parser cannot resume at the right position | Fail the input and fix source/schema |

## 24. Testing Root Arrays and Item Separators

Integration tests should confirm the parser handles array structure accurately and each item is returned exactly once.

Cases to test:

1. Root array with one object: reader returns one item then EOF.
2. Root array with multiple objects: each object becomes an item in exact order.
3. Empty root array `[]`: reader returns EOF and read count is zero.
4. Whitespace and newlines between items: results remain unchanged.
5. Strings containing commas: string values are not split.
6. Nested objects and arrays containing commas: entire root object remains one item.
7. Missing comma or trailing comma: parser reports a JSON error.
8. Root object containing an array property: verify standard reader does not auto-select the nested array.
9. JSON Lines: verify appropriate reader is used, not root-array `JsonItemReader`.
10. Missing/null/wrong-type fields: mapping and validation reflect policy accurately.
11. Restart after a committed chunk: reader resumes from the item after checkpoint.
12. File modified between runs: verify source version/checksum protects restarts.

Tests should verify item count, item order, object contents, `ExecutionContext`, step status, and writer output. Checking only that the job finished is insufficient to prove item separators were handled properly.

## 25. Workflow for Determining JSON Format Before Configuring a Reader

Before selecting a reader, check:

1. Is the JSON root an array or an object?
2. Is each item an object directly inside the root array or inside a child property?
3. Is the separator between items a standard JSON comma?
4. Is the source actually JSON Lines or multiple concatenated documents?
5. Are there nested objects/arrays or strings containing commas?
6. Do objects share the same schema and data types?
7. Can files be empty, or is an empty root array permitted?
8. Does the job need restart, and is the input immutable?
9. Are there multiple resources requiring a stable manifest/ordering?
10. Should invalid records be skipped, or must structural errors fail the whole file?

Choose the reader based on the source's actual format. Do not force JSON Lines into a root array merely by adding brackets if you cannot control escaping and document integrity.

## Conclusion

Spring Batch's `JsonItemReader<T>` reads items from a JSON root array. Each direct object in the array is one item; the comma between objects is the item separator per JSON grammar and is handled by the parser. Commas inside strings, nested objects, or nested arrays do not split items. Standard JSON does not permit trailing commas, and whitespace/newlines do not substitute for commas between array elements.

Use a suitable `JsonObjectReader` such as `JacksonJsonObjectReader`, declare a stable resource and reader name, enable `saveState` when restart is required, and keep inputs and identifying `JobParameters` unchanged. If the source is JSON Lines, an envelope root object, or concatenated documents, pick `FlatFileItemReader` or an appropriate custom reader instead of assuming `JsonItemReader` can locate line-based item separators automatically.
