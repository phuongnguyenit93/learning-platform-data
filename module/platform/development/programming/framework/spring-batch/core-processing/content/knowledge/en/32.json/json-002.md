# JsonObject and Jackson Mapping

In Spring Batch, JSON data is typically read into Java objects for the processor to handle and converted back into JSON when the writer outputs results. Jackson is a popular library for parsing JSON, mapping JSON to POJOs or a JSON tree, and serializing objects to JSON.

When working with JSON, distinguish three layers:

- **JSON object in data:** a structure of key/value pairs, such as an object with orderId, amount, and customer.
- **Object model in Java:** a POJO, DTO, record, or JSON tree such as Jackson JsonNode and ObjectNode.
- **Jackson mapping:** conversion rules between JSON and Java types, controlled by ObjectMapper, annotations, modules, and custom serializers/deserializers.

In Spring Batch, the abstractions JsonItemReader, JsonObjectReader, JsonFileItemWriter, and JsonObjectMarshaller bring JSON reading/writing into chunk processing. Jackson provides corresponding implementations to map data into Java types.

## 1. JSON Objects and JsonObject Types in Java

JSON has a few basic structures:

~~~json
{
  "orderId": 1001,
  "customer": {
    "code": "C001",
    "name": "Nguyễn Văn An"
  },
  "items": [
    {
      "sku": "BOOK-01",
      "quantity": 2
    },
    {
      "sku": "PEN-02",
      "quantity": 5
    }
  ],
  "paid": true
}
~~~

The root object has the properties orderId, customer, items, and paid. Among them, customer is a nested object, while items is an array of objects.

The name JsonObject can refer to different types depending on the library:

| Type | Library | Characteristics |
| --- | --- | --- |
| JsonNode / ObjectNode | Jackson | General JSON tree; ObjectNode represents a mutable JSON object |
| JsonObject | Jakarta JSON Processing (JSON-P) | Standard Jakarta JSON object API |
| JsonObject | Gson | JSON object type of the Gson library |
| POJO/DTO | Java | Business data type mapped from JSON by Jackson |

In Jackson, the type commonly used to represent a JSON object is ObjectNode, while the general parent type is JsonNode. Jackson does not name its main tree node JsonObject.

Spring Batch also has interfaces named JsonObjectReader<T> and JsonObjectMarshaller<T>. The word JsonObject in these interface names describes a JSON unit being read or marshalled; it does not mean you must use Gson JsonObject or Jakarta JsonObject.

## 2. Three Ways to Map JSON with Jackson

Jackson supports multiple ways to work with JSON:

1. **Data binding:** map JSON directly to a POJO/DTO.
2. **Tree model:** read JSON into a JsonNode or ObjectNode, then access and modify individual nodes.
3. **Streaming API:** read or write tokens sequentially using JsonParser and JsonGenerator.

| Approach | Typical API | When appropriate |
| --- | --- | --- |
| Data binding | readValue, writeValue, convertValue | Known JSON structure with a DTO |
| Tree model | readTree, treeToValue, valueToTree | Changing structure or need to inspect dynamic fields |
| Streaming | JsonParser, JsonGenerator | Very large payload or need fine-grained token and memory control |

For business batch jobs, data binding to a DTO is usually easier to read, test, and less error-prone. Tree model fits when the schema is not completely fixed or unknown fields need to be preserved. Streaming fits when processing large JSON without building a full object tree in memory.

## 3. Creating a DTO to Receive JSON

Suppose the input file contains orders:

~~~json
{
  "orderId": 1001,
  "customerCode": "C001",
  "totalAmount": 250000.50,
  "currency": "VND"
}
~~~

You can create a DTO:

~~~java
public class OrderJson {

    private Long orderId;
    private String customerCode;
    private BigDecimal totalAmount;
    private String currency;

    public Long getOrderId() {
        return orderId;
    }

    public void setOrderId(Long orderId) {
        this.orderId = orderId;
    }

    public String getCustomerCode() {
        return customerCode;
    }

    public void setCustomerCode(String customerCode) {
        this.customerCode = customerCode;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }

    public void setTotalAmount(BigDecimal totalAmount) {
        this.totalAmount = totalAmount;
    }

    public String getCurrency() {
        return currency;
    }

    public void setCurrency(String currency) {
        this.currency = currency;
    }
}
~~~

Jackson can instantiate the object and assign properties based on field/property names. Use BigDecimal for money instead of double to avoid floating-point errors.

When designing DTOs for batch:

- Use nullable types like Long, Integer if you need to distinguish a missing field from 0.
- Clearly define required fields and optional fields.
- Do not directly use an entity managed by a persistence context when the DTO is an external data boundary.
- Keep the input DTO separate from the database write model if the JSON structure differs from the table structure.
- Define rules for unknown fields, null fields, and invalid data types.

## 4. Using ObjectMapper Directly

ObjectMapper is the core of Jackson data binding. You can use readValue to convert a JSON String into a DTO:

~~~java
ObjectMapper mapper = new ObjectMapper();

String json = """
        {
          "orderId": 1001,
          "customerCode": "C001",
          "totalAmount": 250000.50,
          "currency": "VND"
        }
        """;

OrderJson order = mapper.readValue(json, OrderJson.class);
~~~

In the reverse direction, use writeValueAsString:

~~~java
String output = mapper.writeValueAsString(order);
~~~

Commonly used methods:

| API | Purpose |
| --- | --- |
| readValue(json, Type.class) | JSON to Java type |
| writeValueAsString(value) | Object to JSON String |
| readTree(json) | JSON to JsonNode tree |
| treeToValue(node, Type.class) | Node to Java type |
| valueToTree(value) | Object to JSON tree |
| convertValue(source, Type.class) | Convert between Java/JSON-compatible types |

In a Spring application, configure and reuse a managed ObjectMapper instead of creating a new mapper for each item. A configured ObjectMapper can be used concurrently for standard read/write operations once configuration is complete; avoid mutating mapper configuration while a Job is running.

## 5. Mapping Property Names with Annotations

Field names in JSON may differ from property names in Java. Use JsonProperty to declare the JSON name:

~~~java
public class CustomerJson {

    @JsonProperty("customer_id")
    private Long customerId;

    @JsonProperty("display_name")
    private String displayName;

    // getters and setters
}
~~~

JSON:

~~~json
{
  "customer_id": 501,
  "display_name": "Nguyễn Văn An"
}
~~~

Jackson maps customer_id to customerId and display_name to displayName.

If the source can send multiple different names for the same property, use JsonAlias:

~~~java
public class CustomerJson {

    @JsonProperty("customerCode")
    @JsonAlias({"customer_code", "code"})
    private String customerCode;

    // getters and setters
}
~~~

JsonProperty defines the primary property name when serializing/deserializing. JsonAlias adds alternative names when reading. When writing JSON, Jackson still uses the primary property name.

## 6. Mapping Nested Objects and Arrays

A DTO can reflect a multi-level JSON structure:

~~~java
public class OrderJson {

    private Long orderId;
    private CustomerJson customer;
    private List<OrderLineJson> items;

    // getters and setters
}

public class CustomerJson {

    private String code;
    private String name;

    // getters and setters
}

public class OrderLineJson {

    private String sku;
    private Integer quantity;

    // getters and setters
}
~~~

Jackson automatically maps nested objects and arrays if property types are declared properly. There is no need to parse each node manually for a known structure.

Example:

~~~java
OrderJson order = mapper.readValue(json, OrderJson.class);

String customerName = order.getCustomer().getName();
Integer firstQuantity = order.getItems().get(0).getQuantity();
~~~

If customer or items can be null, check before accessing. Syntactically valid JSON does not mean business-valid data.

## 7. Generic Types and Collections

When reading a JSON array into List<OrderJson>, you cannot simply pass List.class because Java type erasure loses the element type. Use TypeReference:

~~~java
List<OrderJson> orders = mapper.readValue(
        jsonArray,
        new TypeReference<List<OrderJson>>() {});
~~~

Or use JavaType:

~~~java
JavaType listType = mapper.getTypeFactory()
        .constructCollectionType(List.class, OrderJson.class);

List<OrderJson> orders = mapper.readValue(jsonArray, listType);
~~~

In Spring Batch, JsonItemReader<OrderJson> typically reads one object at a time from a JSON array and returns each item to the chunk. Therefore, you do not need to read the entire array into a List before processing.

## 8. Tree Model with JsonNode and ObjectNode

When the schema is not fixed, you can read into JsonNode:

~~~java
JsonNode root = mapper.readTree(json);

long orderId = root.path("orderId").asLong();
String customerCode = root.path("customerCode").asText();
JsonNode items = root.path("items");
~~~

path() returns a MissingNode when a field does not exist, avoiding some NullPointerExceptions. However, asLong() or asText() may return default values if the node is missing or has the wrong type. For required fields, check isMissingNode(), isNull(), and node type before extracting values.

Strict check example:

~~~java
JsonNode idNode = root.get("orderId");
if (idNode == null || !idNode.canConvertToLong()) {
    throw new IllegalArgumentException(
            "orderId is missing or invalid");
}

long orderId = idNode.longValue();
~~~

### Modifying a JSON Object

ObjectNode allows adding, modifying, or removing properties:

~~~java
ObjectNode object = (ObjectNode) mapper.readTree(json);
object.put("source", "BATCH");
object.put("processed", true);
object.remove("temporaryField");

String updatedJson = mapper.writeValueAsString(object);
~~~

Casting to ObjectNode is only safe if root is actually a JSON object. You can check root.isObject() before casting.

### Converting Between JsonNode and DTO

When you need to inspect or transform some fields before mapping to a DTO:

~~~java
JsonNode root = mapper.readTree(json);
JsonNode customerNode = root.path("customer");

CustomerJson customer = mapper.treeToValue(
        customerNode,
        CustomerJson.class);
~~~

In the reverse direction:

~~~java
ObjectNode jsonObject = mapper.valueToTree(order);
jsonObject.put("sourceSystem", "ERP");
~~~

The tree model is useful when schemas evolve, but if the structure is stable, DTOs are generally easier for controlling data types and validation.

## 9. Configuring Jackson ObjectMapper

ObjectMapper has many features that directly affect mapping results. Configure them explicitly instead of relying on all defaults.

Example:

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
        .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        .build();
~~~

Meaning:

- JavaTimeModule supports date/time types in java.time.
- Disabling WRITE_DATES_AS_TIMESTAMPS writes dates/times as strings according to serializer config rather than numeric timestamps.
- Disabling FAIL_ON_UNKNOWN_PROPERTIES ignores fields not present in the DTO when reading.

This is a contract choice. If an unknown field could indicate a wrong version or wrong schema, keep fail mode enabled and handle it explicitly. If partners frequently add backward-compatible fields, you can ignore unknown fields while still validating required ones.

### Naming Strategy

If JSON uses snake_case while Java uses camelCase, you can configure:

~~~java
mapper.setPropertyNamingStrategy(
        PropertyNamingStrategies.SNAKE_CASE);
~~~

Then customer_code can map to customerCode. There is no need to add JsonProperty to every field if the whole schema uses the same rule. Annotations remain useful for exceptional names.

Do not change the naming strategy after the mapper is already in use. Configure the mapper once at application startup.

## 10. Dates/Times and Number Formatting

JSON has no dedicated date or decimal type. Dates/times are usually represented as String or number; decimal numbers are represented as JSON number.

Example:

~~~json
{
  "createdAt": "2026-11-15T10:30:00Z",
  "amount": 123456.78
}
~~~

DTO:

~~~java
public class PaymentJson {

    private Instant createdAt;
    private BigDecimal amount;

    // getters and setters
}
~~~

Register JavaTimeModule so Jackson supports Instant, LocalDate, LocalDateTime, and corresponding java.time types. Align timezone and format with the source system.

Do not use double for monetary amounts if decimal precision is needed. BigDecimal preserves decimal values better and lets you define explicit rounding modes in calculations.

If the source sends amount as a String rather than a JSON number, define the format and use a custom deserializer or controlled conversion. Do not silently accept every data type because that can hide schema changes.

## 11. Nulls, Missing Fields, and Default Values

These three cases are different:

~~~json
{}
~~~

~~~json
{"customerCode": null}
~~~

~~~json
{"customerCode": ""}
~~~

They respectively represent a field not present, a field with null value, and a field as an empty string.

For Java primitive types like long, a missing field may retain the default value 0. If you need to distinguish missing from 0, use wrapper Long.

Validation example:

~~~java
if (order.getOrderId() == null) {
    throw new InvalidOrderException("orderId is required");
}

if (order.getCustomerCode() == null
        || order.getCustomerCode().isBlank()) {
    throw new InvalidOrderException("customerCode is required");
}
~~~

Do not use JsonInclude(NON_NULL) to solve input data errors. This annotation mainly controls how properties are serialized when writing JSON; input validation still needs to be done separately.

## 12. Custom Serializers and Deserializers

When JSON has a special format, you can write a custom deserializer:

~~~java
public class AmountDeserializer
        extends JsonDeserializer<BigDecimal> {

    @Override
    public BigDecimal deserialize(
            JsonParser parser,
            DeserializationContext context) throws IOException {

        String value = parser.getValueAsString();
        if (value == null || value.isBlank()) {
            return null;
        }

        return new BigDecimal(value.replace(",", ""));
    }
}
~~~

Register on the property:

~~~java
public class OrderJson {

    @JsonDeserialize(using = AmountDeserializer.class)
    private BigDecimal totalAmount;

    // getters and setters
}
~~~

The example illustrates a source sending monetary amounts as strings with thousands separators. In practice, you must know the locale and decimal separator convention. The string 1,234 can mean different things depending on locale; do not strip commas if the contract is unclear.

A custom serializer can control formatting when writing:

~~~java
public class AmountSerializer
        extends JsonSerializer<BigDecimal> {

    @Override
    public void serialize(
            BigDecimal value,
            JsonGenerator generator,
            SerializerProvider provider) throws IOException {

        generator.writeNumber(value);
    }
}
~~~

Write custom serializers/deserializers only when default mapping does not satisfy the contract. Complex parsing logic needs unit tests for valid data, boundary data, and invalid data.

## 13. Enums and Unrecognized Values

JSON usually represents enums as Strings:

~~~json
{
  "status": "APPROVED"
}
~~~

DTO:

~~~java
public enum OrderStatus {
    NEW,
    APPROVED,
    REJECTED
}
~~~

Jackson can map Strings to enums by name. If the source sends a value outside the list, mapping may fail depending on configuration.

Do not automatically turn every unknown value into a default enum if doing so loses information. You can:

- Reject the record and log a data error.
- Use String at the boundary DTO and validate in the processor.
- Use an enum with an UNKNOWN value if business rules explicitly define it.
- Write a custom deserializer to preserve the original value and classify errors.

For batch imports, record the invalid enum value and message ID/record key so it can be fixed and replayed.

## 14. Reading JSON with JsonItemReader

Spring Batch provides JsonItemReader<T> to read JSON into items. With Jackson, use JacksonJsonObjectReader<T> to map each JSON object to a Java type.

Example input file as a JSON array:

~~~json
[
  {
    "orderId": 1001,
    "customerCode": "C001",
    "totalAmount": 250000.50
  },
  {
    "orderId": 1002,
    "customerCode": "C002",
    "totalAmount": 180000.00
  }
]
~~~

Reader configuration:

~~~java
@Bean
@StepScope
public JsonItemReader<OrderJson> orderJsonReader(
        @Value("#{jobParameters['inputFile']}") Resource inputFile) {

    JacksonJsonObjectReader<OrderJson> objectReader =
            new JacksonJsonObjectReader<>(OrderJson.class);

    return new JsonItemReaderBuilder<OrderJson>()
            .name("orderJsonReader")
            .resource(inputFile)
            .jsonObjectReader(objectReader)
            .saveState(true)
            .build();
}
~~~

The reader returns each OrderJson to the chunk Step. The application does not need to manually read the whole file into a List before processing.

JsonItemReader is designed for JSON structures supported by JsonObjectReader, typically a JSON array containing objects. If the source uses another structure, such as a root object with an orders property holding an array, check your version's API or write a suitable reader to reach that array.

### Customizing ObjectMapper Configuration

If you need JavaTimeModule, a naming strategy, or custom unknown-field rules, you can create a JacksonJsonObjectReader with a configured ObjectMapper according to the API of the Spring Batch version in use. Example:

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
        .build();

JacksonJsonObjectReader<OrderJson> objectReader =
        new JacksonJsonObjectReader<>(OrderJson.class);
objectReader.setMapper(mapper);
~~~

Constructor or setter names may vary across Spring Batch versions. Check your project's API version; the principle is to use the same configured ObjectMapper rather than letting the reader create a default mapper when special mapping is needed.

## 15. Reading Line-Delimited JSON (NDJSON)

Not every JSON file is an array. Some systems use NDJSON (newline-delimited JSON), where each line is an independent JSON document:

~~~text
{"orderId":1001,"customerCode":"C001","totalAmount":250000.50}
{"orderId":1002,"customerCode":"C002","totalAmount":180000.00}
{"orderId":1003,"customerCode":"C003","totalAmount":99000.00}
~~~

NDJSON differs from a JSON array. If the JsonItemReader in your version requires a root array, you cannot feed NDJSON into it simply by changing the file extension.

You can use FlatFileItemReader<String> to read line by line, then parse with Jackson in the processor:

~~~java
@Bean
public ItemProcessor<String, OrderJson> ndjsonProcessor(
        ObjectMapper objectMapper) {

    return line -> objectMapper.readValue(line, OrderJson.class);
}
~~~

Or write a custom ItemReader using the Jackson streaming parser to read each JSON document. The choice depends on file size, per-line error handling capability, and restart requirements.

Do not use readTree() on the entire NDJSON as if it were a single JSON document. Each line must be parsed separately or processed with a format-aware streaming parser.

## 16. Writing JSON with JsonFileItemWriter

Spring Batch provides JsonFileItemWriter<T> to write items as JSON. With Jackson, use JacksonJsonObjectMarshaller<T>:

~~~java
@Bean
public JsonFileItemWriter<OrderJson> orderJsonWriter(
        Resource outputFile) {

    JacksonJsonObjectMarshaller<OrderJson> marshaller =
            new JacksonJsonObjectMarshaller<>();

    return new JsonFileItemWriterBuilder<OrderJson>()
            .name("orderJsonWriter")
            .resource(outputFile)
            .jsonObjectMarshaller(marshaller)
            .saveState(true)
            .shouldDeleteIfExists(true)
            .build();
}
~~~

The writer converts each OrderJson into a JSON object and manages file structure per Spring Batch's implementation. With this writer, check the output file format required by the receiving system, including root array, pretty printing if any, and behavior when there are no items.

If you need a custom ObjectMapper for the marshaller, use the constructor or setter corresponding to your Spring Batch version. Ensure the reader and writer mappers agree on naming strategy, date format, enums, and custom serializers/deserializers when both directions must be compatible.

### Writing JSON Is Not Always Writing a Single JSON Object

JsonFileItemWriter writes a sequence of items in the format managed by the writer. If you need a JSON document with a root object containing metadata and a nested array, such as:

~~~json
{
  "batchId": "BATCH-2026-11",
  "generatedAt": "2026-11-15T10:30:00Z",
  "orders": [
    {
      "orderId": 1001
    }
  ]
}
~~~

you may need a custom writer or a separate metadata wrapping step. Do not assume JsonFileItemWriter automatically generates any arbitrary root object structure.

## 17. Jackson Mapping in Processor

A useful pattern is having the reader parse JSON into an input DTO, and the processor validate and convert it into the target model:

~~~java
public class OrderProcessor
        implements ItemProcessor<OrderJson, OrderEntity> {

    @Override
    public OrderEntity process(OrderJson input) {
        if (input.getOrderId() == null) {
            throw new InvalidOrderException("orderId is required");
        }

        if (input.getTotalAmount() == null
                || input.getTotalAmount().signum() < 0) {
            throw new InvalidOrderException("totalAmount is invalid");
        }

        return new OrderEntity(
                input.getOrderId(),
                input.getCustomerCode(),
                input.getTotalAmount());
    }
}
~~~

Separating the input DTO from the entity keeps the application decoupled from the external schema. If a partner renames fields or adds metadata, only the mapping layer needs to change.

You can use JsonNode if some fields are dynamic:

~~~java
public OrderEntity map(JsonNode node) {
    JsonNode sourceNode = node.path("source");
    String source = sourceNode.isTextual()
            ? sourceNode.textValue()
            : "UNKNOWN";

    OrderJson order = mapper.convertValue(node, OrderJson.class);
    return toEntity(order, source);
}
~~~

Do not let a default value hide a schema error for a required field. If missing source is a business error, reject instead of assigning UNKNOWN.

## 18. Validation After Mapping

Jackson is responsible for parsing and type mapping. It does not automatically verify all business rules.

For example, JSON can parse into a DTO yet still be invalid:

~~~json
{
  "orderId": -1,
  "customerCode": "",
  "totalAmount": -500
}
~~~

After mapping, you can validate with Jakarta Bean Validation:

~~~java
public class OrderJson {

    @NotNull
    @Positive
    private Long orderId;

    @NotBlank
    private String customerCode;

    @NotNull
    @DecimalMin("0.00")
    private BigDecimal totalAmount;

    // getters and setters
}
~~~

In the processor or a validation service, call Validator to check constraints and convert violations into appropriate business exceptions. If you want Spring Batch to skip invalid records, classify exceptions clearly and configure the corresponding skip policy.

Distinguish:

- JSON syntax error: the JSON document is invalid.
- Mapping error: valid JSON, but cannot be converted to Java types.
- Validation error: object was created, but violates constraints.
- Business error: structurally valid object, but fails business rules.

Proper classification makes retry, skip, reject, and monitoring work accurately.

## 19. Handling Unknown Fields and Schema Versions

Partners may add new fields over time. There are two strategies:

**Strict mapping:** reject unknown fields. Appropriate when the schema must match strictly or new fields could change data semantics.

**Tolerant mapping:** ignore unknown fields. Appropriate when the source guarantees backward-compatible field additions and the consumer only cares about part of the schema.

You can include a version in the JSON:

~~~json
{
  "schemaVersion": 2,
  "orderId": 1001,
  "customerCode": "C001"
}
~~~

The processor or reader can check schemaVersion and select the corresponding DTO/mapper. Do not try to force all versions into the same DTO with many defaults if versions change semantics.

If you need to retain unknown fields to log or forward them, the ObjectNode tree model can help. With DTOs, you can use JsonAnySetter/JsonAnyGetter to store extra properties in a Map, if the contract allows.

## 20. Polymorphic JSON and Subtypes

A JSON array can contain multiple item types:

~~~json
[
  {
    "type": "PAYMENT",
    "paymentId": "P-100",
    "amount": 250000
  },
  {
    "type": "REFUND",
    "refundId": "R-200",
    "amount": 50000
  }
]
~~~

You can model subtypes with JsonTypeInfo and JsonSubTypes:

~~~java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "type")
@JsonSubTypes({
        @JsonSubTypes.Type(
                value = PaymentEvent.class,
                name = "PAYMENT"),
        @JsonSubTypes.Type(
                value = RefundEvent.class,
                name = "REFUND")
})
public abstract class FinancialEvent {
}
~~~

Subtypes:

~~~java
public class PaymentEvent extends FinancialEvent {
    private String paymentId;
    private BigDecimal amount;
    // getters and setters
}

public class RefundEvent extends FinancialEvent {
    private String refundId;
    private BigDecimal amount;
    // getters and setters
}
~~~

Allow only explicitly listed subtypes. Do not enable broad Jackson default typing for untrusted JSON; arbitrary type metadata can create security risks during deserialization. For data from partners or users, use a subtype allowlist and check version/schema.

## 21. Large JSON and Memory Limits

If a JSON file contains millions of objects, do not use ObjectMapper.readTree() on the entire file and hold the whole tree in memory. The JSON tree can be significantly larger than the file size.

For a large JSON array, JsonItemReader helps read object by object under the ItemReader model and pass each item into chunks. When deeper token control is needed, use the Jackson streaming API or a custom JsonObjectReader.

Guidelines:

- Do not load the entire file into a List if it can be read item by item.
- Keep DTOs containing only the fields needed for processing.
- Choose chunk size based on memory and transaction duration.
- Limit String lengths and nested array sizes per contract.
- Avoid logging huge raw payloads.
- Monitor heap and parsing time.

Overly deep JSON nesting or unbounded arrays can create memory pressure. Enforce file/request size limits at the ingestion layer and validate structure before feeding into the Job.

## 22. Restart and Checkpoints with JSON Readers/Writers

JsonItemReader and JsonFileItemWriter are ItemStream components that can save state when saveState is enabled. Set a stable name and keep resource/input stable between the initial run and restart.

Example:

~~~java
return new JsonItemReaderBuilder<OrderJson>()
        .name("orderJsonReader")
        .resource(inputFile)
        .jsonObjectReader(new JacksonJsonObjectReader<>(OrderJson.class))
        .saveState(true)
        .build();
~~~

When the Job restarts the same JobInstance, the reader uses the saved checkpoint to resume the read position as supported by the implementation. The writer must also maintain the proper output resource and state to resume writing.

For safe restarts:

- Keep the Job name and identifying JobParameters unchanged.
- Do not change the input file or its contents between run and restart.
- Keep reader/writer names stable.
- Keep ObjectMapper configuration and schema version unchanged.
- Do not change item order in the input.
- Ensure the writer is idempotent or resumes at the exact output position.

If the input JSON is regenerated or its schema changes, treat it as a new input version rather than applying an old checkpoint to different data.

## 23. JSON Parse Errors, Skip, and Dead-Letter

JSON syntax errors or mapping errors can cause the reader to throw an exception before returning an item. This differs from validation errors arising in the processor after an item has been read successfully.

For data where processing must continue when a record fails:

- If each record is an NDJSON line, you can catch parse errors per line and route failed records to a reject flow.
- If the file is a single JSON array and a syntax error breaks parser structure, it is not always possible to safely skip one object and read the next.
- Log the position, input file ID, record key if available, and failure cause.
- Only skip clearly classified exceptions; do not skip all IOExceptions or system I/O failures.
- Use dead-letter/reject output to preserve the raw record when possible.

With a JSON array, a syntax error at one position can prevent the parser from knowing where the next object starts. If per-record error isolation is required, NDJSON or one message per record is generally easier to recover.

Do not write entire sensitive payloads into unprotected logs or DLQs. Store raw records where proper access control and retention exist.

## 24. Security When Deserializing JSON

JSON is input data and must be treated as untrusted. Necessary measures include:

- Do not enable broad default typing or allow arbitrary class names in payloads.
- Allowlist subtypes when using polymorphic mapping.
- Limit file size, nesting depth, and field lengths.
- Validate required fields, enums, quantities, and ranges.
- Do not deserialize directly into entities whose setters cause side effects.
- Do not use payloads to control which classes or methods are executed.
- Do not log tokens, secrets, or personal information unnecessarily.
- Keep Jackson and Spring Batch updated to supported versions per project policy.

Do not use custom deserializers to evaluate expressions or invoke classes specified in JSON. Deserializers should only convert data according to a known contract.

## 25. Testing Jackson Mapping

Test DTO mapping in isolation before running the full Job.

Example:

~~~java
@Test
void mapsNestedOrderJson() throws Exception {
    String json = """
            {
              "orderId": 1001,
              "customer": {
                "code": "C001",
                "name": "Nguyễn Văn An"
              },
              "items": [
                {"sku": "BOOK-01", "quantity": 2}
              ]
            }
            """;

    OrderJson order = objectMapper.readValue(json, OrderJson.class);

    assertEquals(1001L, order.getOrderId());
    assertEquals("Nguyễn Văn An", order.getCustomer().getName());
    assertEquals(2, order.getItems().get(0).getQuantity());
}
~~~

Cases to test:

- Standard property names and aliases.
- Nested objects and empty arrays.
- Missing fields, nulls, and empty strings.
- Wrong data types, e.g., String instead of number.
- Large decimals and precision.
- Dates/times, timezones, and formats.
- Unrecognized enums.
- Unknown fields and schema versions.
- Vietnamese Unicode and special characters.
- Custom serializers/deserializers.
- JSON root array, root object, and NDJSON.

Then run integration tests:

1. JsonItemReader reads the exact number of items.
2. Processor validates and maps accurately.
3. JsonFileItemWriter produces valid JSON.
4. Restart after several committed chunks neither drops nor duplicates items.
5. Parse errors and validation errors are classified accurately.
6. The output file can be parsed back by the consumer's mapper.

## 26. Common Pitfalls

### Confusing JsonObject across libraries

Jackson uses JsonNode/ObjectNode; Gson and Jakarta JSON-P have their own JsonObject types. Identify the exact package and API in use.

### Using DTOs with wrong property names

JSON uses snake_case while Java uses camelCase. Use JsonProperty, JsonAlias, or an appropriate naming strategy.

### Reading a JSON array into a List using List.class

Type erasure loses element types. Use TypeReference or JavaType; for batch, consider JsonItemReader reading item by item.

### Reading NDJSON with a reader expecting a JSON array

NDJSON is multiple JSON documents by line. Use FlatFileItemReader combined with ObjectMapper or a custom streaming reader.

### Ignoring nulls and missing fields

DTOs may receive null or default primitive values. Validate required fields after mapping.

### Disabling unknown-field errors too broadly

Schema changes can be masked. Choose strict or tolerant mapping per contract and check versions.

### Using double for money

Floating-point errors can affect calculations. Use BigDecimal.

### Creating a new ObjectMapper for each item

Increases overhead and leads to inconsistent mapping configuration. Reuse a configured mapper.

### Parsing an entire large JSON file into JsonNode

Can consume excessive heap. Use JsonItemReader or streaming.

### Enabling default typing for untrusted payloads

Can widen deserializable types unexpectedly. Use a subtype allowlist and safe configuration.

### Assuming valid JSON means valid business data

Mapping only verifies structure/types. Separate validation and business rules are needed.

### Changing ObjectMapper or input file on restart

Checkpoints may no longer match contents or mapping behavior. Keep input, schema, and mapper configuration stable within the same JobInstance.

## 27. Workflow for Designing JSON Mapping in Spring Batch

Before implementing, determine:

1. Is the JSON root an object, array, or NDJSON?
2. Which DTO corresponds to one JSON item?
3. Are there nested objects, arrays, or polymorphic subtypes?
4. Do JSON property names differ from Java names?
5. Which fields are required, nullable, or have defaults?
6. What formats do monetary amounts, dates/times, and timezones use?
7. How are unknown fields and schema versions handled?
8. Use POJO data binding or the JsonNode tree model?
9. Are custom serializers/deserializers needed?
10. Do JsonItemReader/JsonFileItemWriter match the file structure?
11. Is the file large enough to require streaming or NDJSON?
12. Can the reader/writer saveState and restart?
13. How are parse errors, mapping errors, and validation errors classified?
14. Are payload size limits and security controls enforced?
15. Can the output be parsed back by the consumer under the same contract?

For stable schemas, prefer DTOs and Jackson data binding. Use JsonNode/ObjectNode when dynamic structures need handling. Use streaming when size or token-control requirements do not fit building an object tree. In Spring Batch, let the reader return items one by one to chunks and let the writer manage output per the Step lifecycle instead of loading or writing all data manually.

## Conclusion

A JSON object is a data structure; Jackson provides data binding to POJOs, a tree model via JsonNode/ObjectNode, and a streaming API for token-level processing. In Spring Batch, JsonItemReader combined with JacksonJsonObjectReader can read individual objects from a JSON array, while JsonFileItemWriter combined with JacksonJsonObjectMarshaller writes items as JSON. Define clear DTOs and property mappings, configure ObjectMapper consistently for field names, dates/times, decimals, and unknown fields, and apply business validation after parsing. For dynamic schemas, use the tree model; for NDJSON or very large files, choose an appropriate reader/streaming approach. Keep inputs, schemas, mappers, and checkpoints stable on restart, while treating JSON as untrusted data and testing both mapping and the entire read/write flow.
