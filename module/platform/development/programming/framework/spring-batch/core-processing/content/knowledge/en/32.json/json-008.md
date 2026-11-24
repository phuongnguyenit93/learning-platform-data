# Null Fields and Default Mapping in Spring Batch

When Spring Batch reads JSON, a field can be missing, explicitly sent with value null, an empty string, an empty collection, or contain a concrete value. These cases do not carry the same data meaning. If the mapper automatically turns all of them into one default value, the batch job may write wrong data, miss input errors, or lose information the source system intended to convey.

With JSON readers using Jackson, how null fields and default mappings are handled is primarily governed by ObjectMapper configuration, DTO annotations, and conversion logic into the domain model. Spring Batch manages reading items, transactions, skips, and restarts; it does not infer default rules for individual business fields on its own.

The crucial step is defining a clear data contract: which fields are required, which may be omitted, when defaults apply, and when data must be rejected. Then implement those rules consistently at the right mapping layer.

## 1. Distinguishing Missing, Null, Empty, and Value

A JSON property can appear in several ways:

| JSON input | Common meaning | Example |
| --- | --- | --- |
| Property missing | Producer did not send field | { "id": 10 } |
| Property with null | Producer sent field with no value | { "id": 10, "note": null } |
| Empty string | String present with zero characters | { "id": 10, "note": "" } |
| Empty collection | Collection present with zero elements | { "id": 10, "tags": [] } |
| Empty object | Object present with no child properties | { "id": 10, "address": {} } |
| Concrete value | Producer sent data | { "id": 10, "note": "urgent" } |

Do not automatically treat these cases as equivalent. For example:

- Missing note may mean the producer did not provide a note.
- note: null may mean the producer wants to clear an old note.
- note: "" may mean the note is intentionally set to empty.
- tags: [] may mean the producer confirms there are no tags.

Default rules must follow the data contract. If the batch job turns every case into an empty string, 0, or an empty collection, information about the producer's intent can be lost.

## 2. JSON Reader and Jackson Mapping in Spring Batch

Spring Batch provides JsonItemReader to read a JSON document structured as an array of objects and return each object as an item. JsonObjectReader is responsible for converting each JSON object into a Java type. JacksonJsonObjectReader is the implementation using Jackson.

Example input:

~~~json
[
  {
    "id": 101,
    "customerId": "C-10",
    "quantity": 2,
    "note": "priority"
  },
  {
    "id": 102,
    "customerId": "C-11",
    "note": null
  }
]
~~~

The reader can be configured as follows:

~~~java
@Bean
@StepScope
JsonItemReader<OrderInput> orderJsonReader(
        @Value("#{jobParameters['inputFile']}") String inputFile,
        ObjectMapper objectMapper) {

    JacksonJsonObjectReader<OrderInput> objectReader =
        new JacksonJsonObjectReader<>(OrderInput.class, objectMapper);

    return new JsonItemReaderBuilder<OrderInput>()
        .name("orderJsonReader")
        .resource(new FileSystemResource(inputFile))
        .jsonObjectReader(objectReader)
        .saveState(true)
        .build();
}
~~~

JsonItemReader manages reading each object from the JSON document; Jackson mapping determines which fields are assigned and how nulls are handled. saveState(true) relates to the reader's restart checkpoint, not property default configuration.

If the source is NDJSON (each line is an independent JSON object), do not assume JsonItemReader reads line by line like an array. Use FlatFileItemReader paired with a LineMapper calling Jackson ObjectMapper.readValue() per line, or a dedicated reader matching the source format.

## 3. How Does Jackson Handle Missing Properties?

With a mutable Java bean having a default constructor and field initializers, Jackson typically assigns only properties present in the JSON. If a property is missing, the initializer may be preserved.

Example:

~~~java
public class OrderInput {

    private Long id;
    private Integer quantity = 1;
    private String currency = "VND";

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }

    public String getCurrency() {
        return currency;
    }

    public void setCurrency(String currency) {
        this.currency = currency;
    }
}
~~~

With JSON:

~~~json
{ "id": 101 }
~~~

quantity can keep its initialized value 1, and currency keeps VND because Jackson received no property to assign. This default comes from Java object initialization, not from Spring Batch itself.

This behavior depends on how the DTO is constructed. With constructor-based mapping, records, or immutable objects, Jackson may pass null or default values for missing constructor parameters rather than keeping field initializers like a mutable bean. Therefore, test the exact DTO style in use.

## 4. Missing Properties Differ from Explicit JSON Null

If JSON includes a property with value null, Jackson by default can assign null to reference-type properties. This differs from a missing property.

With the DTO from the previous example:

~~~json
{ "id": 101, "quantity": null, "currency": null }
~~~

quantity and currency can be overwritten with null, even though their field initializers were 1 and VND. Field initializers only take effect when no assignment overwrites them.

The table below describes common behavior for mutable beans:

| Property | Common result |
| --- | --- |
| Absent from JSON | Keeps initializer or initial value |
| Present with null | Assigns null to reference property |
| Present with value | Assigns deserialized value |

This is why you cannot simply declare field initializers and assume all JSON nulls receive defaults. If explicit nulls must also retain defaults, declare null handling explicitly.

## 5. Using @JsonSetter to Specify Explicit Null Handling

Jackson provides @JsonSetter with the nulls attribute. You can choose how to handle a property that is present with JSON null.

Common Nulls options:

| Value | Behavior |
| --- | --- |
| Nulls.SET | Assigns null by default to reference properties |
| Nulls.SKIP | Skips assignment when JSON value is null |
| Nulls.FAIL | Throws mapping error when property has null value |
| Nulls.AS_EMPTY | Uses empty value provided by the type's deserializer |
| Nulls.DEFAULT | Uses Jackson's default configuration for the property |

Example preserving default when field is missing or explicit null:

~~~java
public class OrderInput {

    private String currency = "VND";

    public String getCurrency() {
        return currency;
    }

    @JsonSetter(value = "currency", nulls = Nulls.SKIP)
    public void setCurrency(String currency) {
        this.currency = currency;
    }
}
~~~

With this DTO:

- JSON without currency: setter is not called, initializer VND is kept.
- JSON with currency: null: Jackson skips assignment per Nulls.SKIP, initializer stays intact.
- JSON with currency: USD: setter is called and value becomes USD.

Only use this when missing and explicit null truly carry the same business meaning. If null means clear value while missing means no update, preserve that distinction.

## 6. Using Nulls.FAIL for Fields Rejecting Null

If a property sent explicitly with null is invalid data, configure Nulls.FAIL:

~~~java
public class OrderInput {

    private String customerId;

    @JsonSetter(value = "customerId", nulls = Nulls.FAIL)
    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }
}
~~~

The following JSON will trigger a mapping error:

~~~json
{ "customerId": null }
~~~

However, Nulls.FAIL handles explicit nulls. It does not necessarily make a missing property an error across all DTO styles. If customerId is absent, the setter may never be called and the field remains null.

To enforce required properties, use post-deserialization validation or appropriate strict constructor/creator handling. Example:

~~~java
public void validate() {
    if (customerId == null || customerId.isBlank()) {
        throw new InvalidOrderException("customerId is required");
    }
}
~~~

If you need to distinguish missing properties from explicit nulls, use JsonNode or a representation with a presence flag before converting to domain objects.

## 7. Using Nulls.AS_EMPTY for Collections and Strings

Nulls.AS_EMPTY instructs Jackson to use the empty value provided by the data type's deserializer. For example, for some collection types, null can convert to an empty collection; for String, the empty value is typically an empty string.

~~~java
public class OrderInput {

    private List<String> tags = new ArrayList<>();

    @JsonSetter(value = "tags", nulls = Nulls.AS_EMPTY)
    public void setTags(List<String> tags) {
        this.tags = tags;
    }
}
~~~

With JSON:

~~~json
{ "tags": null }
~~~

Jackson can assign an empty list. This is only valid if the data contract treats null and an empty list as equivalent.

If you need to distinguish:

- property missing: keep existing tags unchanged;
- tags: null: clear or reject;
- tags: []: confirm zero tags;

then do not use AS_EMPTY to merge them. Preserve presence/null state and handle it in domain mapping.

## 8. Handling Nulls Inside Collections with contentNulls

nulls applies to the collection property itself. contentNulls applies to each element inside the collection.

Example rejecting null elements in a list:

~~~java
public class OrderInput {

    private List<String> tags;

    @JsonSetter(
        value = "tags",
        nulls = Nulls.AS_EMPTY,
        contentNulls = Nulls.FAIL
    )
    public void setTags(List<String> tags) {
        this.tags = tags;
    }
}
~~~

With JSON:

~~~json
{ "tags": null }
~~~

the property can convert to an empty list. However:

~~~json
{ "tags": ["priority", null] }
~~~

will be rejected because one collection element is null.

This is useful when a collection field may be absent or null, yet every element must have a value. Define separate policies for the container and for its content.

## 9. Avoiding Primitives When Null Must Be Distinguished

Java primitives such as int, long, and boolean cannot hold null. If JSON lacks the property, primitives usually retain Java's default such as 0 or false. If JSON sends explicit null, Jackson may convert it to the default value or throw an error depending on configuration.

Example:

~~~java
public class OrderInput {
    private int quantity;
    private boolean expedited;
}
~~~

With JSON:

~~~json
{ "id": 101 }
~~~

quantity can be 0 and expedited false. The application cannot tell whether the producer sent 0/false or omitted the property by inspecting only primitives after deserialization.

When presence carries meaning, use wrappers:

~~~java
public class OrderInput {
    private Integer quantity;
    private Boolean expedited;
}
~~~

Wrappers preserve null to distinguish it from 0 and false. Validation or the domain mapper then decides whether to apply a default or reject.

Jackson can enable DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES so explicit nulls into primitives throw an error instead of silently becoming defaults:

~~~java
objectMapper.enable(
    DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES
);
~~~

This option does not turn missing properties into errors in all cases. Missing properties and explicit nulls are two distinct cases requiring separate configuration/checks.

## 10. Defaults for Constructors and Java Records

With constructor-based DTOs or Java records, Jackson constructs objects by invoking the constructor. Mutable-bean field initializers are not a reliable default model for constructor parameters.

Record example:

~~~java
public record OrderInput(
    Long id,
    Integer quantity,
    String currency
) {}
~~~

If a property is missing, reference components may receive null. For primitive components, values may become primitive defaults if configuration permits. If explicit null is passed to a component, behavior also depends on Jackson's null handling and features.

One way to express defaults explicitly is via a dedicated constructor/factory:

~~~java
public record OrderInput(
    Long id,
    Integer quantity,
    String currency
) {
    public Order toDomain() {
        int effectiveQuantity =
            quantity == null ? 1 : quantity;
        String effectiveCurrency =
            currency == null ? "VND" : currency;

        return Order.create(
            Objects.requireNonNull(id, "id is required"),
            effectiveQuantity,
            effectiveCurrency
        );
    }
}
~~~

The example above collapses missing and explicit null into the same default. If the two cases need different meanings, relying solely on record values after deserialization is insufficient; retain presence information as well.

## 11. Jackson Creator Properties and Strict Deserialization

For constructors or factories annotated with JsonCreator, Jackson provides features to enforce required properties:

- FAIL_ON_MISSING_CREATOR_PROPERTIES: fails when a required creator property is absent.
- FAIL_ON_NULL_CREATOR_PROPERTIES: fails when a creator property receives null.
- FAIL_ON_NULL_FOR_PRIMITIVES: fails when explicit null is assigned to a primitive.

Strict configuration example:

~~~java
ObjectMapper strictMapper = JsonMapper.builder()
    .enable(DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES)
    .enable(DeserializationFeature.FAIL_ON_NULL_CREATOR_PROPERTIES)
    .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES)
    .build();
~~~

Creator features have broad scope and affect all constructors/creators processed by the mapper. Enable them only on mappers matching that input contract; if some creator properties may be absent, use separate mappers or DTOs and purposeful validation.

JsonProperty(required = true) is also often used to describe required properties, especially with creator properties. Do not rely on this annotation as general validation across all mutable beans. Check the behavior of your exact Jackson version and DTO type.

## 12. @JsonProperty(defaultValue) Does Not Automatically Apply Defaults

Jackson has a defaultValue attribute on JsonProperty, but this value is primarily metadata for modules/frameworks or introspection tools. Jackson databind does not automatically assign a runtime default merely from declaring:

~~~java
@JsonProperty(value = "quantity", defaultValue = "1")
private Integer quantity;
~~~

Do not assume a missing property will automatically receive 1. Use one of the approaches with clear runtime behavior:

- Field initializers/setter defaults on mutable beans.
- JsonSetter(nulls = ...) for explicit nulls.
- Constructors/factories applying defaults themselves.
- Domain mappers or normalizers.
- Custom deserializers when presence and null must be distinguished.

If using JSON Schema, the `default` keyword is likewise often an annotation describing a suggested value, rather than automatically mutating input JSON unless the validator/processor is configured to materialize defaults. Verify the exact tool in use.

## 13. Distinguishing Technical Defaults and Business Defaults

Not every default belongs in a Jackson DTO. They can be divided into groups:

| Default type | Example | Appropriate place |
| --- | --- | --- |
| Format/input default | Missing optional property means empty list per JSON contract | DTO/deserialization layer |
| Business default | Order without currency uses tenant's currency | Domain mapper/domain service |
| Operational default | Input file comes from job parameter or deployment config | JobParameters/configuration |
| Persistence default | Database column has default value on insert | Database schema/SQL writer |

For instance, VND can be a JSON contract default if all producers share the same currency. Yet if currency depends on tenant or market, the default should be decided by a domain service with full context, not hardcoded in a Jackson DTO.

Similarly, default quantity 1 may be a business rule. Placing it in a domain factory lets other entry points (REST, batch, messaging) apply the exact same rule.

## 14. Normalizing Data After Deserialization

An easy-to-control pattern is deserializing into an input DTO, then running validation/normalization before creating the domain object:

~~~java
public class OrderInputNormalizer {

    public NormalizedOrder normalize(OrderInput input) {
        if (input.getId() == null) {
            throw new InvalidOrderException("id is required");
        }

        Integer quantity = input.getQuantity();
        if (quantity == null) {
            quantity = 1;
        }
        if (quantity <= 0) {
            throw new InvalidOrderException(
                "quantity must be greater than zero"
            );
        }

        String currency = input.getCurrency();
        if (currency == null || currency.isBlank()) {
            currency = "VND";
        }

        return new NormalizedOrder(
            input.getId(),
            quantity,
            currency,
            input.getNote()
        );
    }
}
~~~

The normalizer illustrates when the contract specifies both null/blank quantity and currency receive defaults. If explicit null means clear or reject, adjust the corresponding rule instead of applying a uniform default.

Do not mutate the input DTO directly if it is logged, audited, or used to reconcile against the raw payload. Creating a separate normalized object preserves both raw input and normalized output.

## 15. Distinguishing Missing and Null with JsonNode

If business logic needs to distinguish an absent property from an explicit null property, JsonNode provides suitable APIs:

- has("field"): whether the property exists.
- hasNonNull("field"): property exists and is not JSON null.
- get("field"): returns node, or null if property does not exist.
- isNull(): checks for JSON null.

Example:

~~~java
public OrderInput map(JsonNode node) {
    boolean noteWasProvided = node.has("note");
    JsonNode noteNode = node.get("note");

    String note;
    if (!noteWasProvided) {
        note = null; // not sent
    } else if (noteNode == null || noteNode.isNull()) {
        note = null; // explicit null
    } else {
        note = noteNode.asText();
    }

    return new OrderInput(
        node.path("id").asLong(),
        noteWasProvided,
        note
    );
}
~~~

The DTO can retain a presence flag:

~~~java
public record OrderInput(
    long id,
    boolean noteProvided,
    String note
) {}
~~~

Then the domain mapper can apply patch semantics:

- noteProvided == false: keep existing note.
- noteProvided == true and note == null: delete note.
- noteProvided == true and note non-null: update note.

This is useful when batch jobs process update/patch JSON where missing and null have different meanings.

## 16. Custom Deserializers for Complex Rules

When a field has complex parsing rules, you can use JsonDeserializer:

~~~java
public class QuantityDeserializer
        extends JsonDeserializer<Integer> {

    @Override
    public Integer deserialize(
            JsonParser parser,
            DeserializationContext context) throws IOException {

        JsonNode node = parser.getCodec().readTree(parser);
        if (node.isInt()) {
            return node.intValue();
        }
        if (node.isTextual() && node.asText().isBlank()) {
            return null;
        }
        throw JsonMappingException.from(
            parser,
            "quantity must be an integer"
        );
    }
}
~~~

Register on the property:

~~~java
public class OrderInput {

    @JsonDeserialize(using = QuantityDeserializer.class)
    private Integer quantity;
}
~~~

Deserializers are typically invoked when the property is present. If the property is completely missing, there is no token to deserialize, so missing defaults still need separate handling. For explicit nulls, Jackson uses null providers and Nulls config to decide whether to invoke the deserializer. Do not assume a custom deserializer always receives both missing and null.

Do not create a custom deserializer just to turn null into 0 when JsonSetter, field initializers, or a normalizer expresses it clearly. Custom deserializers fit when input formatting genuinely requires custom parsing.

## 17. Nested Objects and Default Mapping

Nested objects also have missing, null, and empty-object states:

~~~json
{ "id": 101 }
~~~

~~~json
{ "id": 101, "shippingAddress": null }
~~~

~~~json
{ "id": 101, "shippingAddress": {} }
~~~

They can represent:

- No address provided.
- Explicitly clearing the address.
- Address provided but missing components.

With mutable DTOs, a field initializer can supply a default object when the property is missing:

~~~java
public class OrderInput {

    private AddressInput shippingAddress = new AddressInput();

    @JsonSetter(
        value = "shippingAddress",
        nulls = Nulls.SKIP
    )
    public void setShippingAddress(AddressInput address) {
        this.shippingAddress = address;
    }
}
~~~

When the property is null, the setter is skipped and the default object is preserved. However, an empty object {} still deserializes into a new AddressInput whose child fields may be null. Validate nested objects independently rather than assuming an empty object is a valid address.

## 18. Collection Defaults and Null Elements

For collections, decide separately:

- Does a missing property become an empty list or stay unprovided?
- Is explicit null treated as an empty list or an error?
- Does an empty list mean delete all elements or no change?
- Are null elements inside the list permitted?

Example DTO using an empty list when missing:

~~~java
public class OrderInput {

    private List<String> tags = new ArrayList<>();

    public List<String> getTags() {
        return tags;
    }

    public void setTags(List<String> tags) {
        this.tags = tags;
    }
}
~~~

For JSON without tags, the initializer preserves an empty list. If tags: null, Jackson by default may assign null; if that is unwanted, add JsonSetter(nulls = Nulls.SKIP) or AS_EMPTY per contract.

Avoid using Collections.emptyList() and later mutating the list directly. If the processor needs to append tags, use a mutable collection or create a new collection.

## 19. Configuring ObjectMapper for Batch Use

You can configure a shared ObjectMapper bean for readers:

~~~java
@Bean
ObjectMapper batchObjectMapper() {
    return JsonMapper.builder()
        .findAndAddModules()
        .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES)
        .build();
}
~~~

findAndAddModules() can register modules present on the classpath, such as Java Time. Enabling FAIL_ON_UNKNOWN_PROPERTIES causes JSON with unknown fields to be rejected; this is useful when schemas must be strict, though it can fail when producers add compatible fields. Pick strictness according to your contract's versioning policy.

Do not alter ObjectMapper configuration after starting to use it in readers or across multiple threads. Finish configuration before injecting. If a group of jobs has different null policies, use separate mappers per contract rather than mutating a global mapper at runtime.

## 20. Default Mapping and Database Writers

After JSON is deserialized and normalized, writers may persist null values to a database. Distinguish SQL NULL from database defaults.

SQL example:

~~~sql
insert into imported_order (order_id, note, quantity)
values (:orderId, :note, :quantity)
~~~

If note is bound with null, the database typically writes SQL NULL. A column's DEFAULT constraint is usually applied only when the column is omitted from the insert list or the statement uses the DEFAULT keyword, depending on the database.

Therefore:

- Missing JSON properties do not automatically trigger database defaults.
- Explicit JSON nulls can become SQL NULL.
- Java DTO field initializers can supply values for the writer to bind.
- Database defaults are a separate rule layer and must be invoked explicitly in SQL when desired.

With JdbcBatchItemWriter and BeanPropertyItemSqlParameterSourceProvider, null properties are typically bound as SQL NULL. If you need the database itself to apply its default, write SQL omitting that column or use database-appropriate DEFAULT syntax. Do not expect a null parameter to equal an omitted parameter.

## 21. Default Mapping from JobParameters and Job Configuration

Some default values belong to the job run rather than the JSON payload, such as default tenant, business date, or source name. These values should come from JobParameters or application configuration.

Example:

~~~java
@Bean
@StepScope
JsonItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile,
        @Value("#{jobParameters['tenantId'] ?: 'DEFAULT'}") String tenantId,
        ObjectMapper objectMapper) {

    // Reader uses inputFile; tenantId is passed to processor
    // or mapper per the job contract.
    return new JsonItemReaderBuilder<OrderInput>()
        .name("orderJsonReader")
        .resource(new FileSystemResource(inputFile))
        .jsonObjectReader(
            new JacksonJsonObjectReader<>(OrderInput.class, objectMapper)
        )
        .saveState(true)
        .build();
}
~~~

The SpEL default example merely illustrates fetching configuration values. If tenant is a critical data identifier, usually require an explicit job parameter rather than silently falling back to DEFAULT, avoiding reading/writing the wrong tenant.

Job parameters define execution scope; JSON fields describe individual items. Do not mix the two value sources when they have different ownership.

## 22. Validation After JSON Mapping

Successful deserialization does not mean business-valid data. JSON may be syntactically valid yet lack an ID, have negative quantity, or specify an unsupported currency.

You can use Bean Validation:

~~~java
public class OrderInput {

    @NotNull
    private Long id;

    @NotNull
    @Positive
    private Integer quantity;

    @NotBlank
    private String currency;
}
~~~

Processor performs validation:

~~~java
public class ValidatingOrderProcessor
        implements ItemProcessor<OrderInput, Order> {

    private final Validator validator;
    private final OrderDomainMapper mapper;

    @Override
    public Order process(OrderInput input) {
        Set<ConstraintViolation<OrderInput>> violations =
            validator.validate(input);

        if (!violations.isEmpty()) {
            throw new InvalidOrderException(
                violations.toString()
            );
        }

        return mapper.toDomain(input);
    }
}
~~~

If validation exceptions are configured as skippable, invalid items can be dropped per skip policy. JSON parse errors or type mismatches happen inside the reader and follow read-phase exceptions/policies. Not every mapping error should be skipped.

## 23. Skip and Retry When JSON Has Nulls or Missing Fields

Classify errors by recoverability:

| Scenario | Generally appropriate handling |
| --- | --- |
| Optional field missing with valid default | Apply default per contract |
| Disallowed explicit null | Fail mapping or validation |
| Single record has invalid business data | Skip if business rules permit |
| Broken JSON syntax or incompatible schema | Generally fail or quarantine source per policy |
| Transient file/storage read error | Retry per appropriate exception |
| Null value means delete data | Preserve presence semantics and process as an update command |

Do not retry a JSON record with negative quantity or bad currency hoping the data fixes itself next time. Retries fit transient resource failures; invalid data needs validation, skip, or failure.

When using JsonItemReader, a deserialization error can occur before the processor receives the item. To skip parse errors, configure skip exceptions matching the reader's actual exception types and test with your Spring Batch/Jackson version.

## 24. Testing Null/Default Mapping at ObjectMapper Level

Unit testing DTOs with ObjectMapper clarifies missing, null, and value behavior. Example:

~~~java
@Test
void keepsDefaultWhenCurrencyIsMissing() throws Exception {
    OrderInput input =
        objectMapper.readValue("{\"id\":101}", OrderInput.class);

    assertThat(input.getCurrency()).isEqualTo("VND");
}

@Test
void keepsDefaultWhenCurrencyIsExplicitNull() throws Exception {
    OrderInput input = objectMapper.readValue(
        "{\"id\":101,\"currency\":null}",
        OrderInput.class
    );

    assertThat(input.getCurrency()).isEqualTo("VND");
}

@Test
void acceptsExplicitCurrency() throws Exception {
    OrderInput input = objectMapper.readValue(
        "{\"id\":101,\"currency\":\"USD\"}",
        OrderInput.class
    );

    assertThat(input.getCurrency()).isEqualTo("USD");
}
~~~

The first two tests only pass if the DTO uses an initializer paired with JsonSetter(nulls = Nulls.SKIP) as in the earlier example. Without the annotation, explicit null can overwrite the initializer. Tests should use the same mapper and DTO configuration as production.

With Nulls.FAIL, verify explicit null throws JsonMappingException or the corresponding exception. For missing properties, write dedicated tests to avoid mistakenly assuming Nulls.FAIL also enforces required fields.

## 25. Test Matrix for JSON Shapes

For every critical field, maintain tests covering all states:

| Input | Result to verify |
| --- | --- |
| Property absent | Default, absent flag, or validation error |
| Property is null | Skip, set null, empty, or error |
| Property is empty string | Keep empty, normalize, or error |
| Property is 0/false | Valid value or business rule violation |
| Property is [] | Empty collection or clear operation |
| Property is {} | Is an empty object valid |
| Property has wrong type | Mapping error, no silent default |
| Collection has null element | Accept, skip, or fail |
| Unknown field | Ignore or reject per schema policy |

In particular, test missing and explicit null separately. These two cases are easily conflated when using primitives, constructor-based DTOs, or custom deserializers.

## 26. Integration Testing with JsonItemReader

ObjectMapper unit tests do not prove JsonItemReader reads the full file and applies the mapper properly inside a step. Add integration tests with real JSON files:

1. Create a JSON file with multiple objects, including missing fields, explicit nulls, empty strings, and concrete values.
2. Configure JsonItemReader with JacksonJsonObjectReader and the exact production ObjectMapper.
3. Run the step with a normalizing/validating processor and a writer collecting or persisting results.
4. Verify each item exhibits the expected default/null semantics.
5. Include an invalid record and verify skip/fail per policy.
6. Rerun/restart if the reader needs checkpoints and confirm mapping does not change.

Example fixture file:

~~~json
[
  { "id": 1, "quantity": 3, "currency": "USD" },
  { "id": 2 },
  { "id": 3, "quantity": null, "currency": null },
  { "id": 4, "quantity": 0, "currency": "" }
]
~~~

Expected results must be defined in tests per contract. Do not assert that every case uses defaults before business rules decide whether missing, null, zero, and empty mean the same thing.

## 27. Testing Mapping When JSON Schema Evolves

Producers may add fields, change types, or alter null representation. Define a compatibility policy:

- Adding optional properties: may be accepted if FAIL_ON_UNKNOWN_PROPERTIES is disabled.
- Adding unsupported properties: strict mapper may fail, surfacing contract drift.
- Changing number to string: decide whether coercion is allowed.
- Changing field to nullable: test Nulls policy.
- Changing defaults: may alter results for older files on restart/reprocessing.
- Changing nested object to null: test null handling and domain invariants explicitly.

For batches needing to reprocess old files, record schema version or batch version in metadata. Mappers can select conversions by version rather than altering global defaults so the same payload yields different outputs across deployments.

## 28. Common Pitfalls with Null and Default Mapping

**Treating missing and null as identical:** producers may use null to delete a field and missing to leave it untouched. Retain presence information if the contract requires distinguishing them.

**Relying solely on field initializers:** initializers do not stop explicit nulls from overwriting fields. Add an appropriate null policy or normalizer.

**Using primitives for nullable fields:** cannot distinguish missing/null from 0 or false. Use wrappers when presence matters.

**Assuming JsonProperty(defaultValue) assigns defaults:** this attribute does not apply runtime defaults in Jackson databind. Use initializers, setters, creators, or mappers.

**Assuming Nulls.FAIL catches missing properties:** the annotation handles explicit nulls; validate missing fields separately.

**Using AS_EMPTY for every field:** empty strings/lists can differ from null in business terms. Combine only when the contract permits.

**Omitting contentNulls:** a list property may pass while null elements inside slip through. Set policies for collection elements.

**Putting business defaults in DTOs:** defaults depending on tenant, currency, or business date belong in context-aware domain/configuration layers.

**Catching all mapping exceptions and returning a default object:** turns corrupt data into seemingly valid items. Classify parse, validation, and infrastructure errors.

**Confusing JSON null with SQL NULL and database defaults:** null parameters usually write SQL NULL; database defaults do not apply automatically when a column is bound to null.

**Using custom deserializers for missing properties:** deserializers are usually not invoked if a property is absent. Handle missing in creators, normalizers, or presence-flagged representations.

**Not testing the actual production mapper:** testing with a default ObjectMapper can differ from the batch-configured mapper. Inject the exact bean and test the reader too.

## 29. Workflow for Designing Production Null/Default Mapping

First, define the meaning of every field in the JSON contract. For each property, document whether it is required, whether missing differs from explicit null, whether empty strings/collections are valid, and whether defaults come from the producer contract or business rules. Do not apply a single blanket policy to every field.

Next, pick the matching mapping mechanism. Use wrapper types when null must be distinguished from primitive defaults; use field initializers and JsonSetter on mutable DTOs when missing/null have clear defaults; use Nulls.FAIL for disallowed explicit nulls; use contentNulls for collection elements; use constructors/factories or JsonNode when presence control is required. Place business-dependent defaults in normalizers/domain mappers, never hidden inside Jackson config.

Finally, configure ObjectMapper before use and inject that exact mapper into JacksonJsonObjectReader. Test each JSON state at the unit level, then test the complete JsonItemReader/step with real fixture files. Verify parse errors, validation, skip/fail policies, and how writers bind nulls to the database. If the batch needs restart or reprocessing of legacy files, manage schema versions and keep default semantics compatible.

Null fields and default mapping are part of the data contract between producer and batch job. Missing properties, explicit nulls, empty values, and concrete values must be handled intentionally. Jackson provides tools such as JsonSetter, Nulls, creator features, and custom deserializers; Spring Batch feeds mapped objects into the pipeline for validation, skip, retry, and persistence. When defaults live at the right layer and tests cover every input shape, batch jobs avoid silently turning missing or invalid data into wrong business values.
