# ObjectMapper Configuration

In Spring Batch, when reading or writing JSON, Jackson's ObjectMapper governs how conversions occur between JSON and Java objects. Mapper configuration directly affects data types, dates/times, enums, nulls, field names, unknown properties, numeric precision, and invalid-data handling.

A Job may read JSON successfully on a developer's machine yet fail in production if the two environments use different mapper configurations. For example, one side accepts unknown fields while the other rejects them; one parses timestamps using a default timezone while the other uses another timezone; or one coerces the string "123" to a number while the other requires a JSON number.

In batch processing, these differences also impact restarts. If a Job has committed several chunks and is then restarted with a new ObjectMapper configuration, the same input may be deserialized differently than before.

Design ObjectMapper as part of the data contract:

- Choose modules supporting the required Java types.
- Define naming, date/time, enum, number, and null handling.
- Define unknown-field and type-coercion policies.
- Use parser constraints and safe configuration for untrusted inputs.
- Share the fully configured mapper without mutating it while the Job runs.
- Keep configuration compatible across restarts or version the format.

## 1. What Does ObjectMapper Do?

ObjectMapper is the central component of Jackson Databind. It performs two conversion directions:

- **Deserialization**: JSON bytes/text into Java objects.
- **Serialization**: Java objects into JSON bytes/text.

Example JSON:

~~~json
{
  "order_id": 1001,
  "customer_name": "Nguyễn An",
  "amount": 125.50
}
~~~

ObjectMapper can convert JSON into an object:

~~~java
public record OrderInput(
        Long orderId,
        String customerName,
        BigDecimal amount) {
}
~~~

And convert objects back into JSON. Mapping rules are governed by annotations, naming strategies, registered modules, serializers/deserializers, and enabled/disabled features.

In Spring Batch, ObjectMapper is typically used inside JsonObjectReader or JsonObjectMarshaller. Spring Batch's reader and writer manage item flow, checkpoints, and resources; Jackson handles JSON content mapping.

## 2. Creating a Dedicated ObjectMapper for Batch

A clear approach is creating a dedicated ObjectMapper bean for batch JSON:

~~~java
@Configuration
public class BatchJsonConfiguration {

    @Bean
    public ObjectMapper batchObjectMapper() {
        return JsonMapper.builder()
                .addModule(new JavaTimeModule())
                .addModule(new Jdk8Module())
                .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
                .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES)
                .enable(DeserializationFeature.FAIL_ON_NUMBERS_FOR_ENUMS)
                .build();
    }
}
~~~

The JsonMapper.builder() example requires a Jackson version supporting that builder API. If the project uses an older version, instantiate ObjectMapper and register modules and configure features before use.

Separate batchObjectMapper from the mapper used for REST APIs when the two flows have different contracts. An API might need backward compatibility and accept unknown fields, whereas batch files require strict validation to avoid silently dropping data.

If using Spring Boot, inspect the auto-configured mapper and existing customizers. Do not create an extra mapper arbitrarily and let readers/writers accidentally pick up a different mapper. Inject explicitly named beans and use @Qualifier when needed.

## 3. Configuring the Mapper Before Use

ObjectMapper is designed for concurrent use once configuration is complete. After reading/writing starts, do not mutate modules, mixins, serializers, deserializers, or features on the same mapper.

A good practice:

1. Create the mapper.
2. Register modules and custom mappings.
3. Configure features and parser factory.
4. Test mapping.
5. Share the finalized mapper across readers/writers.

Example of what not to do inside a processor:

~~~java
public Order process(OrderInput input) {
    objectMapper.configure(
            DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES,
            false);
    return convert(input);
}
~~~

If multiple workers share the mapper, runtime mutations can cause inconsistent behavior across threads. Configuration changes should happen at application startup or by creating appropriately scoped beans before the Step runs.

## 4. JavaTimeModule for Dates and Times

Jackson core does not automatically understand all Java Time API date/time types the way an application expects. Register JavaTimeModule to support types such as:

- LocalDate.
- LocalTime.
- LocalDateTime.
- Instant.
- OffsetDateTime.
- ZonedDateTime.
- Duration and several other temporal types.

Example:

~~~java
@Bean
public ObjectMapper batchObjectMapper() {
    return JsonMapper.builder()
            .addModule(new JavaTimeModule())
            .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
            .build();
}
~~~

With this configuration, date/time types are typically represented as ISO-8601 strings rather than numeric timestamps or arrays, depending on the specific type and configuration.

Example:

~~~json
{
  "business_date": "2026-11-15",
  "created_at": "2026-11-15T10:30:00Z"
}
~~~

LocalDate suits business dates without a timezone. Instant or OffsetDateTime suits instants that must be represented consistently across systems. LocalDateTime carries no timezone/offset; do not infer a timezone for it unless the data contract specifies one.

## 5. Specifying Timezones Explicitly

Timezones can change how an instant is interpreted or serialized. A timestamp with offset Z is not the same as a LocalDateTime without an offset.

Example:

~~~java
Instant occurredAt = Instant.parse("2026-11-15T10:30:00Z");
OffsetDateTime businessTime =
        OffsetDateTime.parse("2026-11-15T17:30:00+07:00");
~~~

Both represent the same instant in this example, yet the data types express different semantics.

Do not use the host's default timezone to interpret a date/time string lacking an offset if business logic requires deterministic results. Specify the timezone in the contract, use Instant/OffsetDateTime or configure timezone explicitly, and test across environments.

You can set the serialization timezone on the mapper:

~~~java
mapper.setTimeZone(TimeZone.getTimeZone("UTC"));
~~~

This configuration does not replace choosing the right temporal type. LocalDate is not an instant and should not be converted like a timestamp.

## 6. Naming Strategy: snake_case and camelCase

JSON from another system may use snake_case while the Java model uses camelCase.

JSON:

~~~json
{
  "order_id": 1001,
  "customer_name": "Nguyễn An"
}
~~~

Java:

~~~java
public class OrderInput {
    private Long orderId;
    private String customerName;

    // getters/setters
}
~~~

You can configure a naming strategy:

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
        .build();
~~~

Jackson then maps order_id to orderId and customer_name to customerName.

A global naming strategy affects every model handled by the mapper. If only one DTO uses snake_case, use @JsonNaming on the class:

~~~java
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class OrderInput {
    private Long orderId;
    private String customerName;
}
~~~

Use @JsonProperty when a field has a special name or must preserve an exact JSON name per contract. Avoid changing the global naming strategy just to fix one DTO, as it can mis-map other files.

## 7. Unknown Properties: Strict or Tolerant?

When JSON contains fields not present in the Java model, Jackson can reject or ignore them depending on configuration.

Example input:

~~~json
{
  "order_id": 1001,
  "customer_name": "Nguyễn An",
  "new_partner_field": "value"
}
~~~

If the model does not yet have new_partner_field and the mapper enables FAIL_ON_UNKNOWN_PROPERTIES, deserialization fails.

Strict configuration is a useful default for batch files with fixed schemas:

~~~java
mapper.enable(
        DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
~~~

If compatibility with producers that frequently add fields is needed, you can ignore unknown properties:

~~~java
mapper.disable(
        DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
~~~

Or allow only a specific DTO to ignore unknown fields:

~~~java
@JsonIgnoreProperties(ignoreUnknown = true)
public class PartnerOrderInput {
    // ...
}
~~~

A tolerant policy accommodates additive changes, yet can mask typos in field names. For instance, a producer sends order_amout instead of order_amount; if unknown fields are ignored, amount becomes null and the error only surfaces later.

In batch jobs, decide per contract: strict to catch schema drift; tolerant when producers may add fields without affecting consumers. Whichever you choose, still validate required fields.

## 8. Distinguishing Missing Fields and Null Fields

The following two JSON snippets are not identical:

~~~json
{
  "order_id": 1001
}
~~~

~~~json
{
  "order_id": 1001,
  "customer_name": null
}
~~~

In the first case, the property is not provided. In the second case, the property is present with JSON null.

For ordinary reference fields, both can yield Java null unless special configuration or setters are used. If business logic must distinguish them, use constructor/creator logic, a custom deserializer, wrappers, or inspect the JSON tree before binding.

Jackson supports Nulls policies via @JsonSetter:

~~~java
public class OrderInput {

    private String customerName;

    @JsonSetter(nulls = Nulls.FAIL)
    public void setCustomerName(String customerName) {
        this.customerName = customerName;
    }
}
~~~

Nulls.FAIL rejects explicit null values. Other policies like SKIP or AS_EMPTY have different meanings. Check your Jackson version and specific property type.

Do not replace all nulls with empty strings or 0 by default. Null can mean "unknown", "not provided", "clear value", or "not applicable".

## 9. Primitives, Wrappers, and Null

Java primitives such as int, long, and boolean cannot hold null. Wrappers such as Integer, Long, and Boolean can represent missing state.

Example:

~~~java
public class OrderInput {
    private int quantity;
    private Integer discountPercent;
}
~~~

If JSON contains quantity: null, Jackson may use the primitive default or reject it depending on features. To prevent null from silently turning into 0, enable:

~~~java
mapper.enable(
        DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES);
~~~

For fields that might be absent, use wrappers and validate:

~~~java
if (input.getQuantity() == null || input.getQuantity() <= 0) {
    throw new InvalidOrderException("quantity must be positive");
}
~~~

Do not use 0 to represent missing if 0 is a valid business value. Preserve missing state until validation or business logic decides how to handle it.

## 10. Numbers and BigDecimal

JSON has a `number` type, whereas Java has multiple numeric types with different precisions and ranges.

For currency or values requiring decimal precision, prefer BigDecimal over double:

~~~java
public record PaymentInput(
        String paymentId,
        BigDecimal amount) {
}
~~~

Example JSON:

~~~json
{
  "payment_id": "P-100",
  "amount": 1250.75
}
~~~

BigDecimal preserves decimal representation more accurately for financial calculations than binary floating-point double. However, define scale, rounding mode, and validation per business rules.

If the producer sends amount as a string, such as "1250.75", Jackson may convert it depending on coercion policy. Do not rely on implicit coercion if the contract requires a JSON number. Test the exact input token type.

You can configure USE_BIG_DECIMAL_FOR_FLOATS when mapping JSON into Object, Number, or Map without concrete field types. With DTOs having BigDecimal fields, declaring the field type explicitly is usually enough.

## 11. Type Casting and Coercion

Jackson may support conversions such as numeric strings to integers, numbers to strings, or empty strings to null depending on version and coercion configuration.

In batch jobs, overly broad coercion can mask producer bugs. Example:

~~~json
{
  "quantity": "12"
}
~~~

If the contract requires quantity to be a JSON integer, the string "12" should be treated as a schema violation rather than automatically converted.

Options:

- Use concrete DTO types.
- Configure CoercionConfig appropriate for your Jackson version.
- Write a custom deserializer for fields with special rules.
- Validate token type before accepting data.
- Write tests for empty strings, numeric strings, decimals, and overflow.

Do not apply a single global coercion policy across all data types if each field has different rules.

## 12. Enums and Unrecognized Values

By default, Jackson usually maps enums by Java constant name:

~~~java
public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
~~~

JSON:

~~~json
{
  "status": "PAID"
}
~~~

If the producer sends "IN_PROGRESS" while the Java enum lacks that value, deserialization can fail. This is a form of schema drift requiring a clear policy.

You can define JSON values with @JsonProperty:

~~~java
public enum OrderStatus {
    @JsonProperty("new")
    NEW,

    @JsonProperty("paid")
    PAID,

    @JsonProperty("cancelled")
    CANCELLED
}
~~~

Do not accept numbers as enum indices if the contract requires strings:

~~~java
mapper.enable(
        DeserializationFeature.FAIL_ON_NUMBERS_FOR_ENUMS);
~~~

Do not arbitrarily map unknown enums to a default state if doing so alters business meaning. If UNKNOWN is needed, design the enum and custom mapping intentionally, while recording the original source value.

## 13. Optional and Other JDK Types

To support Optional, certain collection types, and other JDK types, you can register Jdk8Module:

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .addModule(new Jdk8Module())
        .build();
~~~

Example:

~~~java
public record CustomerInput(
        Long id,
        Optional<String> phoneNumber) {
}
~~~

Optional can be useful when a field is genuinely optional. However, Optional does not always preserve the distinction between a missing property and an explicit null property. If those two states carry different meanings, dedicated mapping is needed.

Do not use Optional as a substitute for validation. After deserialization, still check required fields and business rules.

## 14. Constructors, Records, and ParameterNamesModule

Jackson can deserialize Java records and constructor-based models depending on version. For immutable classes using constructors, ensure Jackson knows parameter names and types.

Record example:

~~~java
public record OrderInput(
        Long orderId,
        String customerName,
        BigDecimal amount) {
}
~~~

Records are well supported in modern Jackson versions. For ordinary constructor classes, you can use @JsonCreator and @JsonProperty to declare explicitly:

~~~java
public class CustomerInput {

    private final Long id;
    private final String name;

    @JsonCreator
    public CustomerInput(
            @JsonProperty("id") Long id,
            @JsonProperty("name") String name) {
        this.id = id;
        this.name = name;
    }
}
~~~

ParameterNamesModule can help Jackson use constructor parameter names compiled with appropriate metadata. Even so, explicit annotations are generally clearer and more reliable for integration DTOs.

Test with your project's exact compiler flags, Jackson version, and real models.

## 15. Annotations and MixIns

Mapping can be configured directly on the model:

- @JsonProperty: property name in JSON.
- @JsonIgnore: ignore property.
- @JsonFormat: date/time or specific value format.
- @JsonInclude: control which fields are serialized.
- @JsonAlias: accept multiple names during deserialization.
- @JsonCreator: select constructor/factory to instantiate object.
- @JsonDeserialize: select custom deserializer.
- @JsonSerialize: select custom serializer.

Example alias for old and new names:

~~~java
public class OrderInput {

    @JsonAlias({"orderId", "order_id"})
    private Long id;
}
~~~

If an external library's model cannot be edited, use a Jackson MixIn to add annotations without modifying the original class.

Do not keep too many long-lived aliases without a deprecation plan. Aliases can aid schema migrations, but keeping them indefinitely makes data contracts hard to understand and makes old producers hard to detect.

## 16. Custom Serializers and Deserializers

When a field has a special format, you can write a custom serializer/deserializer.

Example where a producer sends dates in dd/MM/yyyy format:

~~~java
public class LegacyDateDeserializer
        extends JsonDeserializer<LocalDate> {

    private static final DateTimeFormatter FORMAT =
            DateTimeFormatter.ofPattern("dd/MM/yyyy");

    @Override
    public LocalDate deserialize(
            JsonParser parser,
            DeserializationContext context) throws IOException {

        String value = parser.getValueAsString();

        try {
            return LocalDate.parse(value, FORMAT);
        } catch (DateTimeParseException exception) {
            throw InvalidFormatException.from(
                    parser,
                    "Expected date in dd/MM/yyyy format",
                    value,
                    LocalDate.class);
        }
    }
}
~~~

Attach to field:

~~~java
public class LegacyOrderInput {

    @JsonDeserialize(using = LegacyDateDeserializer.class)
    private LocalDate orderDate;
}
~~~

A custom deserializer should:

- Accept only the specified format.
- Report errors with appropriate field and value context.
- Avoid mutable shared state.
- Never swallow exceptions and return meaningless defaults.
- Have unit tests for valid, invalid, blank, and boundary values.

In batch jobs, deserialization errors usually occur before the processor. If per-record skipping is needed, know whether the reader can continue after such errors. A syntactically broken JSON array can desynchronize the parser; not every parse exception is safe to skip.

## 17. Per-Field Date Formatting

You can use @JsonFormat when only specific fields need custom formats:

~~~java
public class PartnerOrderInput {

    @JsonFormat(pattern = "dd/MM/yyyy")
    private LocalDate businessDate;

    @JsonFormat(
            pattern = "yyyy-MM-dd'T'HH:mm:ssXXX",
            timezone = "UTC")
    private OffsetDateTime createdAt;
}
~~~

The format pattern must match the data type. With OffsetDateTime, the pattern should preserve the offset if the contract needs timezone distinction.

Do not use ambiguous date/time patterns such as yyyy-MM-dd HH:mm:ss for a global instant without knowing the timezone. If the source omits an offset, determine the business timezone and convert intentionally.

## 18. Serialization: Null, Empty, and Property Inclusion

When writing JSON, ObjectMapper decides which properties appear.

Example omitting null fields:

~~~java
mapper.setSerializationInclusion(JsonInclude.Include.NON_NULL);
~~~

Or apply on a class:

~~~java
@JsonInclude(JsonInclude.Include.NON_NULL)
public class OrderResult {
    // ...
}
~~~

Common policies:

- ALWAYS: always write the property.
- NON_NULL: omit properties with null values.
- NON_EMPTY: omit nulls and empty values per Jackson rules.
- NON_DEFAULT: omit default values per corresponding rules.

Do not omit nulls just to shrink the file if downstream distinguishes "field absent" from "field present as null". For patch APIs or data sync, this difference can carry business meaning.

Verify actual JSON byte/text output and the consumer's contract.

## 19. Property Order and Reproducible Output

JSON objects by standard do not require property ordering. However, some systems or snapshot tests may require deterministic output.

You can enable property sorting:

~~~java
mapper.enable(
        MapperFeature.SORT_PROPERTIES_ALPHABETICALLY);

mapper.enable(
        SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);
~~~

Enable only if deterministic output is required. It can add overhead and does not replace canonical JSON when standard digital signing or hashing is needed.

If output is digitally signed, use an agreed canonicalization rule rather than assuming property ordering alone produces stable signatures.

## 20. Polymorphic Typing and Data Security

Jackson supports polymorphic deserialization to instantiate subclasses from type metadata. For example, JSON includes a `type` field identifying the concrete type.

This feature must be tightly controlled. Do not enable broad default typing for JSON from untrusted sources because it can permit instantiating unintended types.

If polymorphism is truly needed:

- Use a specific type hierarchy.
- Whitelist allowed subtypes.
- Use @JsonTypeInfo and @JsonSubTypes intentionally.
- If using PolymorphicTypeValidator, restrict accepted packages/types.
- Test payloads with unknown type IDs.

Do not allow type metadata from a producer to let Jackson instantiate arbitrary classes on the classpath.

## 21. Parser Constraints and Untrusted JSON

JSON can contain very long strings, deeply nested structures, or huge token counts. Streaming parsers do not automatically protect against every input causing excessive resource consumption.

Jackson provides StreamReadConstraints in supported versions, allowing limits on characteristics such as nesting depth, string length, and number length.

Conceptual example for a supporting Jackson version:

~~~java
StreamReadConstraints constraints =
        StreamReadConstraints.builder()
                .maxNestingDepth(100)
                .maxStringLength(1_000_000)
                .maxNumberLength(1_000)
                .build();

JsonFactory jsonFactory = JsonFactory.builder()
        .streamReadConstraints(constraints)
        .build();

ObjectMapper mapper = JsonMapper.builder(jsonFactory)
        .build();
~~~

API names and limits may vary across Jackson versions. Choose limits based on real valid data, avoiding thresholds so low they reject valid records.

You can enable strict duplicate detection to reject objects containing the same key multiple times if the contract requires it:

~~~java
JsonFactory factory = JsonFactory.builder()
        .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
        .build();
~~~

JSON objects with duplicate keys can be handled differently across parsers. Rejecting duplicates avoids ambiguity between producer and consumer.

## 22. Streaming JSON in Spring Batch

For array-structured JSON files:

~~~json
[
  {"order_id": 1, "amount": 10.00},
  {"order_id": 2, "amount": 20.00},
  {"order_id": 3, "amount": 30.00}
]
~~~

Do not read the entire file into List<OrderInput> if the file is very large. Spring Batch provides JsonItemReader to read one object at a time from a resource, commonly combined with Jackson2JsonObjectReader.

Example:

~~~java
@Bean
@StepScope
public JsonItemReader<OrderInput> orderJsonReader(
        @Value("#{jobParameters['inputFile']}") Resource resource,
        @Qualifier("batchObjectMapper") ObjectMapper mapper) {

    Jackson2JsonObjectReader<OrderInput> objectReader =
            new Jackson2JsonObjectReader<>(OrderInput.class);

    objectReader.setMapper(mapper);

    return new JsonItemReaderBuilder<OrderInput>()
            .name("orderJsonReader")
            .resource(resource)
            .jsonObjectReader(objectReader)
            .saveState(true)
            .strict(true)
            .build();
}
~~~

JsonItemReader sequentially reads each object in the JSON array instead of requiring the application to hold the entire list in memory. ObjectMapper is injected into Jackson2JsonObjectReader to enforce the batch's exact mapping policy.

Class and method names must match the Spring Batch version in use. Different Spring Batch versions may alter APIs or support different JSON libraries; check your dependencies and corresponding documentation.

## 23. JSON Arrays and NDJSON Are Different Formats

JsonItemReader is typically used for JSON arrays containing multiple objects. Another common format is NDJSON/JSON Lines, where each line is an independent JSON document:

~~~text
{"order_id":1,"amount":10.00}
{"order_id":2,"amount":20.00}
{"order_id":3,"amount":30.00}
~~~

NDJSON has no square brackets wrapping the entire file. You cannot assume JsonItemReader reads NDJSON like a JSON array.

For NDJSON, you can use FlatFileItemReader to read line by line and ObjectMapper.readValue() in a processor, or build a custom streaming ItemReader. Handle blank lines, newlines, encoding, and parse exceptions per record.

Processor example:

~~~java
@Bean
public ItemProcessor<String, OrderInput> ndjsonProcessor(
        @Qualifier("batchObjectMapper") ObjectMapper mapper) {

    return line -> mapper.readValue(line, OrderInput.class);
}
~~~

If each line's JSON can be very long or strings contain newlines, NDJSON requires each record's JSON document to reside on a single physical line. Do not put multiline JSON into NDJSON without custom escaping rules.

## 24. Passing ObjectMapper into JsonFileItemWriter

Spring Batch provides JsonFileItemWriter and JsonObjectMarshaller to write items as JSON. You can use Jackson2JsonObjectMarshaller with a configured ObjectMapper if your library version supports that API.

Example:

~~~java
@Bean
@StepScope
public JsonFileItemWriter<OrderResult> orderJsonWriter(
        @Value("#{jobParameters['outputFile']}") Resource output,
        @Qualifier("batchObjectMapper") ObjectMapper mapper) {

    Jackson2JsonObjectMarshaller<OrderResult> marshaller =
            new Jackson2JsonObjectMarshaller<>();

    marshaller.setObjectMapper(mapper);

    return new JsonFileItemWriterBuilder<OrderResult>()
            .name("orderJsonWriter")
            .resource(output)
            .jsonObjectMarshaller(marshaller)
            .saveState(true)
            .shouldDeleteIfExists(true)
            .build();
}
~~~

Setter/constructor names of Jackson2JsonObjectMarshaller may differ across Spring Batch versions. Use the exact API provided by the installed dependency.

If using a custom ItemWriter, you can call ObjectMapper.writeValueAsBytes() or writeValue() per item, while managing commas, array boundaries, newlines, encoding, and restarts. Avoid concatenating JSON manually as strings because quotes, escapes, or special characters easily produce invalid output.

## 25. Do Not Read Large JSON Entirely into a List

This simple approach does not fit large files:

~~~java
List<OrderInput> orders =
        mapper.readValue(
                inputFile,
                new TypeReference<List<OrderInput>>() {});
~~~

It materializes the entire list in memory before processing. If the file has millions of records, memory grows with total item count.

Instead, use JsonItemReader or the Jackson streaming API to fetch one object at a time. Spring Batch then collects objects by chunk size, processes them, and writes transactionally.

Memory then depends on parser buffers, the current object, the chunk, and processor/writer working sets—not the entire list.

## 26. ObjectMapper and Thread Safety

ObjectMapper can be shared across multiple threads once fully configured. Do not mutate the mapper while threads are serializing/deserializing.

Also watch custom serializers/deserializers:

- Do not keep per-item mutable state in singleton serializers.
- Do not store JsonParser or JsonGenerator in shared fields.
- Do not use mutable SimpleDateFormat as shared state since it is not thread-safe.
- Use immutable DateTimeFormatter.
- If per-item caching is needed, keep caches scoped per execution and bounded.

In multi-threaded Steps or partitioning, multiple workers can share the same ObjectMapper bean. This is normal if the mapper is immutable after configuration and custom components are thread-safe.

Readers and JsonObjectReaders typically maintain per-resource/StepExecution state; do not share the same reader instance across multiple workers just because ObjectMapper is shareable.

## 27. ObjectMapper and Spring Boot

Spring Boot usually auto-configures an ObjectMapper based on Jackson modules, application properties, and customizers. If the application already uses the default mapper for REST, it can be reused when JSON contracts match.

However, batch inputs/outputs often have distinct requirements:

- Input files may require strict unknown-property handling.
- REST APIs may require tolerant behavior for backward compatibility.
- Batch jobs need fixed date/time formats.
- Batch outputs may need deterministic serialization.
- Partner files may use a different naming strategy from APIs.

You can create a dedicated bean:

~~~java
@Bean("batchObjectMapper")
public ObjectMapper batchObjectMapper() {
    return JsonMapper.builder()
            .addModule(new JavaTimeModule())
            .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
            .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
            .build();
}
~~~

Inject with @Qualifier:

~~~java
@Qualifier("batchObjectMapper")
ObjectMapper mapper
~~~

If you want to use Boot's auto-configured mapper, inject it and audit all customizers/modules affecting it. Do not assume the default mapper is identical across every profile or Boot version.

## 28. Validation After Deserialization

ObjectMapper verifies structure and converts types, yet does not replace business validation.

For example, JSON can deserialize successfully:

~~~json
{
  "order_id": 1001,
  "quantity": -5,
  "amount": -10.00
}
~~~

Yet quantity and amount may violate business rules.

You can use Bean Validation:

~~~java
public class OrderInput {

    @NotNull
    private Long orderId;

    @Positive
    private Integer quantity;

    @DecimalMin("0.00")
    private BigDecimal amount;
}
~~~

After the reader creates the object, the processor can invoke Validator and throw a business exception if data is invalid.

Distinguish:

- JSON syntax error: unable to parse the document.
- Binding error: token cannot map to a Java type.
- Bean validation error: object created, but violates constraints.
- Business validation error: requires deeper business-logic checks.

Each category may require different retry/skip policies. A syntax error inside a JSON array can leave the parser unable to continue safely; do not skip every JsonParseException assuming subsequent records can still be read.

## 29. Error Handling in JsonItemReader

When a JSON fragment is invalid, the reader may throw a Jackson exception or one wrapped by Spring Batch in an item-reading exception. The actual exception type depends on the reader and version.

Test and classify:

- Malformed JSON document.
- Object missing a required property.
- Value unconvertible to a Java type.
- Unknown property.
- Invalid date/time.
- Invalid enum.
- Truncated file.

If the file is a JSON array, a syntax error can break the ability to locate the next comma and object boundary. Item-level skipping is not always safe.

If isolating bad records is required, NDJSON can be more convenient because each line is an independent document. The reader can then log the bad line and proceed to the next line if policy permits.

## 30. Restart and ObjectMapper Configuration

JsonItemReader can save state to support restart. The reader needs a stable name and appropriate saveState. The input resource must also keep identical content between run and restart.

Beyond checkpoints, ObjectMapper config must remain compatible:

- Property naming strategy unchanged.
- Date/time format unchanged.
- Enum mapping unchanged.
- Null and unknown-property policies unchanged unexpectedly.
- Custom deserializer semantics unchanged.
- Input file retains the same checksum/version.

For example, suppose the initial run accepts order_id in snake_case, while the restart switches to another naming strategy. The same record may deserialize differently or miss fields.

If changing schema or mapper config is intentional, version the contract, store format version in JobParameters or metadata, and ensure restarts of old JobInstances use the compatible mapping.

Do not store the entire ObjectMapper in ExecutionContext. Only store small metadata such as schema version, input checksum, or format identifier; ObjectMapper is application configuration constructed from code/configuration.

## 31. Reader Name and saveState

Example JsonItemReader needing a stable name:

~~~java
return new JsonItemReaderBuilder<OrderInput>()
        .name("orderJsonReader")
        .resource(resource)
        .jsonObjectReader(objectReader)
        .saveState(true)
        .build();
~~~

The reader name is used to store state in Step ExecutionContext. Renaming the reader while an old JobInstance still needs to restart can prevent locating the checkpoint under the old key.

saveState(true) enables the reader to store read position. If saveState is disabled, restart may re-read from the beginning. The writer must then be idempotent or the application must prevent duplicate processing.

The input file must be immutable. If the file is overwritten with new JSON at the same path, the old checkpoint may no longer point to the same item.

## 32. Schema Evolution and Strictness

JSON schemas can evolve over time. For instance, a producer adds a new field:

~~~json
{
  "order_id": 1001,
  "amount": 125.50,
  "source_channel": "MOBILE"
}
~~~

If an old consumer is strict about unknown properties, the new file will be rejected. If the consumer is tolerant, the new field can be ignored.

To manage schema evolution:

- Version the schema or file format.
- Identify which fields are required and which are optional.
- Define how new fields and removed fields are handled.
- Use @JsonAlias for time-boxed migrations.
- Check type changes and enum expansions.
- Store schema version alongside Job metadata.
- Maintain fixtures from supported producer versions.

Do not leave unknown-property policy as an accidental result of Jackson's defaults. Choose strict or tolerant per contract and test it.

## 33. Testing ObjectMapper Independently

Before attaching the mapper to a Job, test mapping directly:

~~~java
@Test
void mapsSnakeCaseAndJavaTime() throws Exception {
    String json = """
            {
              "order_id": 1001,
              "business_date": "2026-11-15",
              "amount": 125.50
            }
            """;

    OrderInput input =
            batchObjectMapper.readValue(json, OrderInput.class);

    assertEquals(1001L, input.orderId());
    assertEquals(
            LocalDate.of(2026, 11, 15),
            input.businessDate());
    assertEquals(
            new BigDecimal("125.50"),
            input.amount());
}
~~~

Tests should cover:

- Naming strategy and @JsonProperty.
- JavaTimeModule and timezones.
- BigDecimal precision.
- Valid/invalid enums.
- Missing fields and explicit nulls.
- Unknown properties.
- Empty/blank strings and type coercion.
- Custom serializers/deserializers.
- Duplicate JSON keys if policy is enabled.
- Nesting/string constraints.

Mapper unit tests do not replace reader/writer integration tests. They only verify mapping policy at the Jackson level.

## 34. Testing JsonItemReader in a Step

Use a small JSON array fixture file and run the reader through its lifecycle:

~~~java
@Test
void readsJsonArrayAsIndividualItems() throws Exception {
    ExecutionContext context = new ExecutionContext();

    reader.open(context);

    OrderInput first = reader.read();
    OrderInput second = reader.read();
    OrderInput third = reader.read();
    OrderInput end = reader.read();

    assertEquals(1L, first.orderId());
    assertEquals(2L, second.orderId());
    assertEquals(3L, third.orderId());
    assertNull(end);

    reader.close();
}
~~~

In real tests, configure a Resource and reader dedicated to the test. For restarts, run a multi-chunk Step, intentionally fail a later chunk, then restart the same JobInstance and verify committed items are not duplicated.

Also test malformed files, empty files, JSON arrays with invalid root structures, and non-existent resources.

## 35. Testing JSON Output

With JsonFileItemWriter or a custom writer, verify:

- JSON output parses back cleanly using the matching mapper.
- Property names conform to the contract.
- Dates/times have the right format and timezone.
- Null fields are kept or omitted per policy.
- BigDecimal precision is unchanged.
- Enums serialize to the expected strings.
- Headers/array boundaries or NDJSON line formats are valid.
- Restarts do not produce duplicate commas, missing brackets, or duplicate items.

If downstream requires deterministic byte output, compare bytes or canonicalized JSON per contract. Do not rely on property order unless explicitly configured.

## 36. Common Pitfalls

### Creating multiple ObjectMappers with inconsistent configs

Reader, writer, and services may serialize/deserialize differently. Use explicit beans and inject consistently.

### Mutating the mapper after the Job has started

Multiple workers may observe different policies. Complete configuration before sharing the mapper.

### Forgetting JavaTimeModule

LocalDate or Instant fails to map as expected. Register the module and test formats.

### Relying on the machine's default timezone

The same input can produce different instants across environments. Choose temporal types and timezones explicitly.

### Ignoring all unknown properties

Misspelled fields can turn into null without error. Choose strict/tolerant per schema and validate required fields.

### Using double for currency

Binary floating-point errors can affect calculations. Use BigDecimal with explicit scale/rounding.

### Enabling broad default typing

Inputs may request instantiating unintended types. Use subtype whitelists and validators if polymorphism is needed.

### Reading an entire JSON file into a List

Memory grows with the entire file. Use JsonItemReader or a streaming parser.

### Confusing JSON arrays with NDJSON

The reader fails to recognize the structure. Pick the reader matching the actual format.

### Skipping all JsonParseExceptions

Malformed JSON arrays can desynchronize the parser. Only skip record errors when record boundaries are reliable.

### Changing mapper config between restarts

The same checkpoint can produce different objects. Keep configs compatible or version the format.

### Sharing custom deserializers with mutable state

Multi-threaded Steps can suffer race conditions. Keep serializers/deserializers stateless or properly synchronized.

## 37. Workflow for Configuring ObjectMapper in Spring Batch

When building a JSON-reading/writing Job, determine:

1. Is the JSON an array, NDJSON, or a single document?
2. Which fields in the Java model and JSON schema are required vs. optional?
3. Is the naming strategy snake_case or custom mapping?
4. Are there Java Time, Optional, or custom types requiring modules?
5. Which timezone and format do dates/times require?
6. Which numbers require BigDecimal, and with what precision/scale?
7. How are enums and unknown values handled?
8. Are unknown properties rejected or ignored?
9. Do missing properties and explicit nulls differ?
10. Is coercion from strings/numbers allowed?
11. Does the parser enforce limits on nesting, string length, and number length?
12. Is duplicate key detection or polymorphic typing needed?
13. Do readers/writers share the same explicitly configured mapper?
14. Are large JSON files read item by item in streaming mode?
15. Are reader name, saveState, and input checksum stable across restarts?
16. Do integration tests verify mapping, chunks, restarts, and output format?

ObjectMapper is part of the Job's JSON contract. Explicitly configure modules, naming, date/time, numbers, enums, nulls, and unknown-property policies; share the finalized mapper; use JsonItemReader or a streaming parser for large files; and keep mapping compatible across restarts. When every record is deserialized by the exact same rules across all environments, Spring Batch can process JSON data reliably, with clear error control and easy recovery.
