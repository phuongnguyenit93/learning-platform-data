# Schema Missing Fields Due to Jackson, Generics, or Overly Generic Return Types

When a property appears in runtime JSON yet disappears from the OpenAPI schema, or vice versa, check Jackson, Java types, and the controller method signature. Springdoc does not inspect an arbitrary JSON response to guess every possible structure; the library analyzes controller metadata, return types, DTOs, annotations, and Jackson's model to construct the OpenAPI document.

Three common groups of causes:

1. Jackson does not treat the field as a serializable/deserializable property, or annotations rename/hide the property.
2. Generic types are lost due to raw types, wildcards, `Object`, or overly generic return types.
3. The controller declares `ResponseEntity<?>` or `Object`, or response annotations override the schema with a different type.

This lesson uses a Book API example to pinpoint where fields are lost, fix the exact layer causing the discrepancy, and write tests to prevent the issue from returning.

## 1. Distinguishing Runtime JSON from OpenAPI Schema

Runtime JSON is the data the server actually sends to clients. The OpenAPI schema is the contract describing that data structure. The two are related yet produced by two different pipelines:

~~~text
Controller return type + DTO + annotations
                 |
                 v
       Springdoc / Swagger Core
                 |
                 v
          OpenAPI schema
                 |
                 v
       /v3/api-docs JSON/YAML

Controller result + Spring ObjectMapper
                 |
                 v
          Jackson serialize
                 |
                 v
          HTTP response JSON
~~~

A field can be absent on one side while present on the other. For example:

- `@Schema(hidden = true)` can hide a field in documentation while Jackson still serializes the field.
- `@JsonIgnore` can cause Jackson to omit the field and Springdoc also omits it from the description.
- `@JsonInclude(NON_NULL)` can omit a property from a specific response when its value is null, yet the property still exists in the schema.
- `ResponseEntity<?>` loses the concrete type in the controller signature, even though runtime happens to return a DTO with many fields.

Therefore, do not start by adding `@Schema` to every missing field. First determine exactly where runtime JSON and the OpenAPI schema diverge.

## 2. Quick Isolation Procedure

When a schema is missing fields, follow this sequence:

1. Call the real endpoint and save the JSON response.
2. Use the exact `ObjectMapper` injected by Spring to serialize a sample DTO.
3. Download `/v3/api-docs` and locate the operation and response content.
4. Inspect the referenced schema inside `components.schemas`.
5. Compare property names, data types, and Jackson annotations on the DTO.
6. Check whether the controller's return type signature preserves concrete generic types.
7. Check whether `@ApiResponse`, `@Content`, or `@Schema(implementation = ...)` overrides the inferred schema.
8. If the DTO uses serializers, mixins, `JsonView`, or `JsonUnwrapped`, write a minimal test for that specific configuration.

Results from steps 3 and 4 distinguish two situations:

| Observation in /v3/api-docs | Investigation direction |
| --- | --- |
| Field missing from `components.schemas` | Jackson visibility/annotations, model converters, property types, or DTO |
| Field present in `components.schemas` but response does not reference that schema | Return type, generic wrapper, `@ApiResponse`, or `@Content` |
| Response has `$ref` pointing to a different schema | Lost generic type, duplicate schema name, or implementation override |
| OpenAPI JSON has field but Swagger UI does not show it | Check `$ref`, whether the document is valid, and whether UI loads the right URL |
| Runtime JSON has field but schema does not | Jackson/runtime mapper and Springdoc model introspection are out of sync |
| Schema has field but runtime JSON does not | Null values, `@JsonInclude`, `@JsonView`, `@JsonIgnore`, or runtime serializer |

## 3. Checking Runtime JSON with Spring's ObjectMapper

Do not instantiate a new `ObjectMapper` in tests to inspect a DTO. A manually constructed `ObjectMapper` may lack the Java Time module, Kotlin module, naming strategy, mixins, or settings used by the real application.

Inject the mapper managed by Spring:

~~~java
import java.math.BigDecimal;

@SpringBootTest
class BookSerializationTest {

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void serializesBookUsingPublicJsonNames() throws Exception {
        BookResponse response = new BookResponse();
        response.setId(42L);
        response.setTitle("Spring Boot");
        response.setPrice(new BigDecimal("250000"));

        String json = objectMapper.writeValueAsString(response);

        assertThat(json).contains("\"book_code\"");
        assertThat(json).contains("\"title\"");
        assertThat(json).doesNotContain("internalNote");
    }
}
~~~

The example above assumes `BookResponse` renames the `id` property to `book_code` and `internalNote` is not published. Use the real DTO and application configuration for meaningful results.

If runtime JSON already lacks the field, focus on Jackson first. If runtime JSON has the field while OpenAPI omits it, move on to model introspection, generics, and response mappings.

## 4. How Jackson Decides Which Properties Are Visible

Jackson builds logical properties from fields, getters, setters, constructor parameters, and annotations. Depending on visibility/configuration, a Java field does not necessarily become a JSON property.

Example DTO:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonIgnore;
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;

@Schema(name = "BookResponse")
public class BookResponse {

    @JsonProperty("book_code")
    private Long id;

    private String title;

    private BigDecimal price;

    @JsonIgnore
    private String internalNote;

    public BookResponse() {}

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }

    public BigDecimal getPrice() { return price; }
    public void setPrice(BigDecimal price) { this.price = price; }

    public String getInternalNote() { return internalNote; }
    public void setInternalNote(String internalNote) {
        this.internalNote = internalNote;
    }
}
~~~

By default, Jackson typically recognizes getters/setters following JavaBean naming conventions. If the project alters visibility or uses different accessor styles, properties may not be discovered as expected.

## 5. `@JsonProperty` Renames Properties

`@JsonProperty` specifies a JSON name different from the Java field name:

~~~java
public class CustomerResponse {

    @JsonProperty("customer_id")
    private Long id;

    @JsonProperty("display_name")
    private String name;
}
~~~

Runtime JSON will use `customer_id` and `display_name`. The OpenAPI schema must also describe the exact names seen by clients.

If the schema still shows `id` while JSON returns `customer_id`, check:

- Which field, getter, or constructor parameter carries `@JsonProperty`.
- Whether another getter/setter has conflicting annotations.
- Whether a Jackson mixin or `ObjectMapper`-level naming strategy overrides it.
- Whether `@Schema(name = ...)` specifies a different name from the JSON property.

Do not use `@Schema(name = "customer_id")` to mask an incorrect Jackson setup. `@Schema` only adjusts documentation; Jackson governs the runtime JSON names.

## 6. `@JsonIgnore` and `@JsonIgnoreProperties`

`@JsonIgnore` marks a logical property for exclusion from serialization/deserialization introspection:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnore;

public class UserResponse {

    private Long id;
    private String username;

    @JsonIgnore
    private String passwordHash;
}
~~~

`passwordHash` should not appear in public JSON and should also be omitted from the response schema.

`@JsonIgnoreProperties` can exclude one or more properties:

~~~java
@JsonIgnoreProperties({"internalNote", "legacyCode"})
public class BookResponse {
    @JsonProperty
    private Long id;
    @JsonProperty
    private String title;
    @JsonProperty
    private String internalNote;
    @JsonProperty
    private String legacyCode;
}
~~~

Distinguish:

| Annotation | Primary effect |
| --- | --- |
| `@JsonIgnore` | Excludes the logical property from Jackson serialization/deserialization |
| `@JsonIgnoreProperties(value = ...)` | Excludes the specified properties from Jackson introspection |
| `@Schema(hidden = true)` | Hides the property in OpenAPI documentation |

If you only want to hide a field from documentation while keeping runtime JSON intact, use `@Schema(hidden = true)`. If a field contains secret data, ensure Jackson does not serialize it; hiding it from Swagger UI alone is insufficient.

## 7. `@JsonInclude` Does Not Mean Removing a Field from the Schema

`@JsonInclude` controls when Jackson includes a property in JSON:

~~~java
@JsonInclude(JsonInclude.Include.NON_NULL)
public class BookResponse {
    @JsonProperty
    private Long id;
    @JsonProperty
    private String title;
    @JsonProperty
    private String subtitle;
}
~~~

If `subtitle` is null, the JSON response may omit the `subtitle` property. When `subtitle` has a value, the property still appears.

Common modes:

| Mode | Behavior |
| --- | --- |
| ALWAYS | Always serialize the property |
| NON_NULL | Omit properties with null values |
| NON_EMPTY | Omit empty strings, empty collections, or empty values per Jackson |
| NON_DEFAULT | Omit values equal to defaults per Jackson rules |

If the schema completely lacks `subtitle` while runtime sometimes includes `subtitle`, check `@Schema(hidden)`, `@JsonIgnore`, and visibility. If only one response lacks `subtitle` because its value is null, `@JsonInclude` is the expected cause.

## 8. `readOnly` and `writeOnly` for Requests/Responses

A property may be accepted in requests yet omitted from responses, or vice versa. Jackson and OpenAPI provide dedicated metadata to describe this:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;
import io.swagger.v3.oas.annotations.media.Schema;

public class AccountDto {

    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    @Schema(accessMode = Schema.AccessMode.READ_ONLY)
    private Long id;

    @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
    @Schema(accessMode = Schema.AccessMode.WRITE_ONLY)
    private String password;

    private String displayName;
}
~~~

`READ_ONLY` fits server-generated `id` or `createdAt` fields. `WRITE_ONLY` fits input `password` or secret fields. OpenAPI uses `readOnly`/`writeOnly` to describe usage direction; Jackson access modes govern runtime serialization/deserialization behavior.

If the same DTO is used for both requests and responses, inspect schemas for both operations. For large APIs, separate request and response DTOs are usually easier to control than a shared model with many read-only/write-only properties.

## 9. ObjectMapper Naming Strategy and Visibility

Spring Boot can configure a naming strategy to rename properties globally, such as `SNAKE_CASE`:

~~~yaml
spring:
  jackson:
    property-naming-strategy: SNAKE_CASE
~~~

Then Java field `displayName` can be serialized as `display_name`. OpenAPI must reflect the name after applying the naming strategy.

Also review these settings:

- Field/getter/setter visibility via `@JsonAutoDetect` or `ObjectMapper` configuration.
- Jackson mixins registered through application configuration.
- Custom `PropertyNamingStrategy`.
- Modules adding serializers/deserializers.
- Lombok getters and annotation processing.
- Fluent accessors like `getName()` versus `name()`.

If Lombok generates getters but annotation processing is disabled in one module, Jackson and Springdoc may see a different model than expected. For non-JavaBean fluent accessors, use explicit `@JsonProperty` or explicit visibility settings.

Do not create a separate `ObjectMapper` just to fix schemas. Configure the application mapper via Spring beans or uniformly registered Jackson modules so serialization and schema introspection share the same metadata.

## 10. Records, Kotlin Data Classes, and Accessors

Modern Jackson supports Java records and Kotlin data classes via their corresponding modules. However, Jackson version, Kotlin module, and visibility settings must be compatible.

Java record:

~~~java
public record BookRecord(
    @JsonProperty("book_code") Long id,
    String title,
    BigDecimal price
) {}
~~~

Kotlin data class:

~~~kotlin
data class BookResponse(
    @JsonProperty("book_code")
    val id: Long,
    val title: String,
    val price: BigDecimal
)
~~~

If record or Kotlin properties are missing:

1. Confirm the application uses the Jackson version managed by Spring Boot.
2. Check `jackson-module-kotlin` if using Kotlin.
3. Check that annotations are placed on the proper component/property target.
4. Serialize an instance using Spring's `ObjectMapper`.
5. Inspect the OpenAPI component schema separately.

Do not add a different Jackson version just to make one record work without checking dependency management. Mismatched Jackson modules can cause linkage errors or divergent introspection behavior.

## 11. `@JsonUnwrapped` Can Alter the JSON Structure

`@JsonUnwrapped` instructs Jackson to lift properties of a nested object up onto the parent object:

~~~java
public class Address {
    @JsonProperty
    private String city;
    @JsonProperty
    private String country;
}

public class CustomerResponse {
    @JsonProperty
    private Long id;

    @JsonProperty
    @JsonUnwrapped
    private Address address;
}
~~~

JSON can become:

~~~json
{
  "id": 7,
  "city": "Da Nang",
  "country": "VN"
}
~~~

Instead of an `address` property containing a nested object, JSON has `city` and `country` at the outer level. This is a different structure from the original Java object graph.

When using `@JsonUnwrapped`, compare runtime JSON against the schema. If the Springdoc/Swagger Core version does not describe the flattened structure as desired, consider:

- Creating a flat response DTO with `city`/`country` properties.
- Declaring a specialized schema via `@Schema(implementation = ...)`.
- Writing a `ModelConverter`/customizer for shared types if multiple endpoints follow the same rule.

Do not use `@Schema(implementation = Address.class)` on an unwrapped property if that makes documentation revert to a nested `address` structure while runtime JSON has no `address` object.

## 12. `@JsonView` Creates Different Schema Views

A DTO can serialize differently depending on `JsonView`:

~~~java
public class Views {
    public interface Public {}
    public interface Internal extends Public {}
}

public class UserResponse {

    @JsonProperty
    @JsonView(Views.Public.class)
    private Long id;

    @JsonProperty
    @JsonView(Views.Public.class)
    private String displayName;

    @JsonProperty
    @JsonView(Views.Internal.class)
    private String riskScore;
}
~~~

Public and internal endpoints can return the same class with different property sets. When using `JsonView`, inspect annotations on controllers and how Springdoc handles views per operation.

If two views produce substantially different contracts, separate DTOs are usually clearer. If keeping `JsonView`, write separate integration tests for each endpoint to ensure the schema does not accidentally publish internal properties.

## 13. Custom Serializers and Deserializers

When using custom `JsonSerializer`/`JsonDeserializer`, JSON structure may no longer mirror Java fields:

~~~java
public class MoneySerializer extends JsonSerializer<Money> {

    @Override
    public void serialize(
            Money value,
            JsonGenerator generator,
            SerializerProvider provider) throws IOException {
        generator.writeStartObject();
        generator.writeNumberField("amount", value.amount());
        generator.writeStringField("currency", value.currency());
        generator.writeEndObject();
    }
}
~~~

The serializer above turns `Money` into an object with `amount` and `currency`. If Springdoc only sees the `Money` type without understanding the serializer, the schema may omit properties or describe them inaccurately.

There are three ways to handle this:

1. Use a concrete DTO for public JSON instead of exposing a domain value object with a special serializer.
2. Declare `@Schema(implementation = MoneyDto.class)` on the appropriate property/response.
3. Write a `ModelConverter` or schema customizer when the special type is widely used.

Example overriding schema on a property:

~~~java
@Schema(implementation = MoneyDto.class)
@JsonProperty
private Money price;
~~~

Example overriding response:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Book details",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = BookResponse.class)
    )
)
~~~

`@Schema(implementation = ...)` only changes the OpenAPI description. It does not make Jackson serialize the object as the specified implementation class. Ensure the schema class accurately describes the real JSON.

## 14. `@JsonValue` and Enums

An enum can serialize to a value other than its Java constant name:

~~~java
public enum BookStatus {
    AVAILABLE("available"),
    OUT_OF_STOCK("out-of-stock");

    private final String value;

    BookStatus(String value) {
        this.value = value;
    }

    @JsonValue
    public String getValue() {
        return value;
    }
}
~~~

Runtime JSON uses `available` or `out-of-stock`, not `AVAILABLE` or `OUT_OF_STOCK`. The enum schema must reflect the values clients actually observe and send.

If the enum in Swagger UI displays Java constant names, check `@JsonValue`, custom serializers, and OpenAPI component schemas. Do not hand-write examples using internal constant names when runtime uses different values.

## 15. Generic Types Lost When Using Raw Types

Java generics only help Springdoc infer schemas when method signatures preserve concrete types. Good example:

~~~java
@GetMapping("/api/books")
public List<BookResponse> listBooks() {
    return service.findAll();
}
~~~

Springdoc can determine that list elements are `BookResponse`.

Overly generic signatures lose type information:

~~~java
public List listBooks() { ... }

public Object listBooks() { ... }

public ResponseEntity<?> listBooks() { ... }

public ResponseEntity<Object> listBooks() { ... }
~~~

With these types, the compiler does not provide enough concrete generic type information for Springdoc to determine element properties. Runtime may return `BookResponse`, yet documentation should not rely on the runtime value of a single request to guess the entire return type.

Keep concrete types:

~~~java
public ResponseEntity<List<BookResponse>> listBooks() { ... }
~~~

If an endpoint genuinely returns multiple payload types conditionally, describe the union with `oneOf`/`anyOf` or separate response codes/media types rather than using unschematized `Object`.

## 16. Generic Wrappers Must Preserve Type Parameters

A common response wrapper:

~~~java
public record ApiEnvelope<T>(
    T data,
    String traceId
) {}
~~~

Controller preserving concrete generics:

~~~java
@GetMapping("/api/books/{id}")
public ApiEnvelope<BookResponse> getBook(@PathVariable Long id) {
    return new ApiEnvelope<>(service.findById(id), traceIdProvider.current());
}
~~~

The signature `ApiEnvelope<BookResponse>` indicates `data` has type `BookResponse`. Changing it to `ApiEnvelope<?>` or raw `ApiEnvelope` can turn the `data` schema into a generic object and lose its properties.

With collections:

~~~java
public ApiEnvelope<List<BookResponse>> listBooks() { ... }
~~~

Nested types still need to be preserved completely. Avoid declaring raw `ApiEnvelope` in a service interface or base controller and only returning subtypes in implementations; Springdoc analyzes exposed method signatures rather than inferring every runtime implementation.

## 17. `ResponseEntity<?>` and `Object` Make Response Schemas Too Generic

`ResponseEntity` is not itself the direct cause of lost schemas; the issue is the generic type inside:

~~~java
// Preserves concrete schema
public ResponseEntity<BookResponse> getBook() { ... }

// Loses concrete type
public ResponseEntity<?> getBook() { ... }

// Loses concrete type
public ResponseEntity<Object> getBook() { ... }
~~~

If the method signature cannot be changed, declare the response schema explicitly:

~~~java
@GetMapping("/api/books/{id}")
@ApiResponse(
    responseCode = "200",
    description = "Book information",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = BookResponse.class)
    )
)
public ResponseEntity<?> getBook(@PathVariable Long id) {
    return ResponseEntity.ok(service.findById(id));
}
~~~

Only use this approach when every 200 response actually has the `BookResponse` structure. If the method returns multiple data types, describe them with `oneOf` or separate endpoints/response codes cleanly.

## 18. `Map<String, Object>` and Dynamic JSON

`Map<String, Object>` typically generates an object schema with `additionalProperties` of type object because keys and values can vary:

~~~java
public Map<String, Object> getStatistics() {
    return Map.of(
        "totalBooks", 120,
        "available", true
    );
}
~~~

Springdoc cannot know every possible key when the declared type does not define them. If the response has a stable structure, create a DTO:

~~~java
public record BookStatistics(
    long totalBooks,
    boolean available
) {}
~~~

If the JSON is truly dynamic, document `additionalProperties` and clear examples. Do not force a fixed schema onto a payload with arbitrary keys because clients will misinterpret the contract.

## 19. Specializing Generic Wrappers with Concrete DTOs

If generic wrappers cause documentation difficulties or you need readable component names, create specialized DTOs:

~~~java
public record BookEnvelope(
    BookResponse data,
    String traceId
) {}

public record BookListEnvelope(
    List<BookResponse> data,
    String traceId
) {}
~~~

Controllers can return `BookEnvelope` or `BookListEnvelope` directly. This duplicates a small amount of structure while yielding explicit, stable schemas.

If keeping the generic wrapper, you can specify the response implementation:

~~~java
@ApiResponse(
    responseCode = "200",
    content = @Content(
        schema = @Schema(implementation = BookEnvelope.class)
    )
)
~~~

The schema implementation must be a concrete class accurately describing `data` and `traceId` in JSON. Do not use raw `ApiEnvelope.class` if the goal is describing `BookResponse` inside `data`.

## 20. Array Responses Need an Item Schema

For list responses, you can declare an explicit array schema:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "List of books",
    content = @Content(
        mediaType = "application/json",
        array = @ArraySchema(
            schema = @Schema(implementation = BookResponse.class)
        )
    )
)
~~~

Do not set `BookResponse` directly as the response schema if runtime JSON is an array. OpenAPI must describe `type: array` and the corresponding item schema.

If the controller returns `Page<BookResponse>`, that is an object containing `content` and metadata, not a plain array. Only use an array schema for `List<BookResponse>` or actual JSON arrays.

## 21. Example: When Adding Examples Drops the Schema

A response may need both a schema and examples. If only `examples` is declared while omitting `schema`, some annotation styles can leave the response content with only the example:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Book details",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = BookResponse.class),
        examples = @ExampleObject(
            name = "book",
            value = """
                {
                  "book_code": 42,
                  "title": "Spring Boot"
                }
                """
        )
    )
)
~~~

When an example is needed, keep both `schema` and `examples` inside the same `@Content`. After changing annotations, inspect response content in `/v3/api-docs` to verify the schema was not lost.

## 22. `@Schema(implementation)` Does Not Fix Runtime JSON

`@Schema(implementation = SomeClass.class)` instructs Springdoc to describe a schema using the specified class. It does not:

- Change the controller's return value.
- Change Jackson serializers/deserializers.
- Automatically add properties to runtime JSON.
- Guarantee the chosen class matches every response branch.

For example, if runtime JSON contains `{ "id": 1, "title": "A" }` while the implementation class has an extra `internalNote`, OpenAPI will misdocument the API if that class is used directly. Create a schema DTO matching the actual payload.

## 23. Inheritance and Polymorphism

If a response has multiple subtypes, an overly general base class may only expose common properties. Use polymorphism metadata to describe variants:

~~~java
@Schema(
    oneOf = {PhysicalBookResponse.class, EbookResponse.class},
    discriminatorProperty = "kind"
)
public interface BookItemResponse {}
~~~

Subtypes:

~~~java
public record PhysicalBookResponse(
    String kind,
    Long id,
    int stockQuantity
) implements BookItemResponse {}

public record EbookResponse(
    String kind,
    Long id,
    String downloadUrl
) implements BookItemResponse {}
~~~

If using Jackson `@JsonTypeInfo`/`@JsonSubTypes`, ensure the discriminator and subtypes in OpenAPI match runtime JSON values. Declaring `oneOf` alone while Jackson fails to serialize the corresponding discriminator prevents clients from distinguishing variants.

## 24. Checking Component Schemas and Response References

When downloading `/v3/api-docs`, inspect:

- `paths` of the failing operation.
- `responses` by status code.
- `content` by media type.
- `schema` or `$ref` inside the response.
- `components.schemas` containing component definitions.

Example response reference:

~~~yaml
paths:
  /api/books/{id}:
    get:
      responses:
        "200":
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/BookResponse"
components:
  schemas:
    BookResponse:
      type: object
      properties:
        book_code:
          type: integer
          format: int64
        title:
          type: string
~~~

If `$ref` points to the right component yet properties are missing, investigate the DTO/Jackson. If the component is complete yet the operation uses a different component, investigate return type signatures and `@ApiResponse` overrides. If `$ref` fails to resolve, inspect component names, customizers, and dependency versions.

## 25. Checking for Duplicate Schema Names

Two classes in different packages may share the same simple name, for example:

~~~text
com.example.customer.UserResponse
com.example.admin.UserResponse
~~~

If both appear in one document, the simple component name can cause confusion or collisions depending on configuration/version. You can set explicit schema names:

~~~java
@Schema(name = "CustomerUserResponse")
public class UserResponse { ... }

@Schema(name = "AdminUserResponse")
public class UserResponse { ... }
~~~

Only change schema names after inspecting all `$ref` entries and client code generation. Renaming a component in OpenAPI can affect generated client models even when runtime JSON stays identical.

## 26. Checking ObjectMapper, Modules, and Mixins

If a DTO serializes properly in unit tests yet OpenAPI still lacks fields, inspect the mapper configuration used by Springdoc:

1. Are there multiple `ObjectMapper` beans in the context?
2. Are Java Time/Kotlin/custom modules registered?
3. Are naming strategies or visibility configured via `application.yml`?
4. Are mixins registered for the DTO class?
5. Are there custom `ModelConverter` or `SpringDocUtils` replacements?
6. Is a Jackson dependency overridden to a mismatched version?

Do not register a mixin solely on a local `ObjectMapper` expecting Springdoc to pick it up automatically. Register configurations at the Spring application level and verify both runtime mapper and document output.

## 27. Testing Schema and JSON for the Same DTO

A thorough test verifies both ends:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class BookSchemaContractTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void jacksonAndOpenApiExposeSameBookProperties() throws Exception {
        BookResponse dto = new BookResponse();
        dto.setId(42L);
        dto.setTitle("Spring Boot");

        String json = objectMapper.writeValueAsString(dto);
        JsonNode runtime = objectMapper.readTree(json);

        assertThat(runtime.has("book_code")).isTrue();
        assertThat(runtime.has("title")).isTrue();
        assertThat(runtime.has("internalNote")).isFalse();

        String specJson = mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();

        JsonNode spec = objectMapper.readTree(specJson);
        JsonNode properties = spec.at(
            "/components/schemas/BookResponse/properties"
        );

        assertThat(properties.has("book_code")).isTrue();
        assertThat(properties.has("title")).isTrue();
        assertThat(properties.has("internalNote")).isFalse();
    }
}
~~~

The test above assumes `BookResponse` has getters/setters, schema name `BookResponse`, and no extra properties. If Springdoc generates a different component name, follow `$ref` in the response to locate the exact component rather than hard-coding the name.

## 28. Testing That Response Schemas Preserve Generic Types

For generic wrappers, check the schema of `data`:

~~~java
JsonNode dataSchema = spec.at(
    "/components/schemas/ApiEnvelopeBookResponse/properties/data"
);

assertThat(dataSchema.path("$ref").asText())
    .contains("BookResponse");
~~~

Generic component names generated by Swagger Core/Springdoc can vary by version and resolution strategy. Read `$ref` from the response schema before writing fixed assertions.

If the wrapper is `ApiEnvelope<?>` or raw `ApiEnvelope`, the test should catch that the `data` schema no longer references `BookResponse`. Then fix the return type signature or use a concrete response DTO.

## 29. Flowchart for Diagnosing Missing Schema Fields

~~~mermaid
flowchart TD
    A["Field missing in Swagger UI"] --> B["Read /v3/api-docs"]
    B --> C{"Is field in components.schemas?"}
    C -->|No| D["Check Jackson visibility and annotations"]
    C -->|Yes| E{"Does response reference the right schema?"}
    E -->|No| F["Check generic return type and @ApiResponse"]
    E -->|Yes| G["Check $ref, media type, and Swagger UI"]
    D --> H["Serialize DTO with Spring ObjectMapper"]
    H --> I{"Does runtime JSON have the field?"}
    I -->|No| J["Fix Jackson/DTO/serializer"]
    I -->|Yes| K["Check ModelConverter, mixin, and version"]
    F --> L["Keep concrete generic or schema implementation"]
~~~

This flowchart helps avoid changing annotations randomly. Each branch is determined by observable evidence in runtime JSON or the OpenAPI document.

## 30. Common Errors

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| Field exists in Java class but not in JSON | Jackson cannot see field/getter or `@JsonIgnore` excludes it | Check visibility, getters, annotations, and `ObjectMapper` |
| JSON has field but OpenAPI lacks it | Jackson model introspection, mixin, or converter differs from runtime | Compare Spring's mapper with `/v3/api-docs`; check `ModelConverter` |
| Property name in schema differs from JSON | `@JsonProperty`, naming strategy, or `@Schema(name)` conflict | Use one consistent public name and verify real JSON |
| Null field disappears from response | `@JsonInclude(NON_NULL)` or `NON_EMPTY` | Check runtime values; do not confuse with hidden schema |
| Internal property appears in docs | Missing `@JsonIgnore` or `@Schema(hidden)` | Remove from JSON and schema per security requirements |
| `ResponseEntity<?>` produces empty object schema | Generic type lost | Use `ResponseEntity<ConcreteDto>` or `@Schema(implementation)` |
| Raw `ApiEnvelope` loses data fields | Type parameter erased | Declare `ApiEnvelope<BookResponse>` or a specialized DTO |
| `Map<String,Object>` lacks concrete properties | Dynamic schema, unknown keys | Use a DTO or describe `additionalProperties` |
| List response only shows generic object | Raw `List` or wildcard | Use `List<BookResponse>` or `@ArraySchema` |
| Generic wrapper displays wrong nested type | Method signature loses concrete generic | Use full generics or concrete envelope |
| Flattened field differs from JSON | `@JsonUnwrapped` or custom serializer | Compare payload; use dedicated DTO/schema |
| Enum schema shows Java constant names | `@JsonValue` or serializer alters value | Align enum schema with JSON values |
| One view has field, another does not | `@JsonView` or endpoints use different views | Check controller views and per-operation schemas |
| Example appears but schema disappears | `@Content` only declares `examples` | Declare both `schema` and `examples` together |
| `$ref` points to wrong component | Duplicate schema name or customizer override | Set distinct `@Schema(name)` and check all `$ref`s |
| Swagger UI hides property despite JSON schema having it | UI loads stale document or `$ref` resolution fails | Check Network tab, docs URL, and validate OpenAPI JSON |

## 31. Checklist Before Editing Annotations

- [ ] Saved the endpoint's real JSON response.
- [ ] Serialized the DTO using Spring's injected `ObjectMapper`.
- [ ] Inspected the operation and response schema in `/v3/api-docs`.
- [ ] Located the corresponding component schema in `components.schemas`.
- [ ] Distinguished a field missing from the component vs a response referencing the wrong component.
- [ ] Reviewed `@JsonProperty`, `@JsonIgnore`, `@JsonIgnoreProperties`, and `@JsonInclude`.
- [ ] Checked `readOnly`/`writeOnly`, `@JsonView`, and `@JsonUnwrapped` if used.
- [ ] Checked getters/setters, Lombok, record/Kotlin modules, and visibility.
- [ ] Checked custom serializers/deserializers, mixins, and naming strategies.
- [ ] Return type preserves concrete generics without raw types/Object/wildcards where avoidable.
- [ ] Generic wrappers retain type parameters in controller signatures.
- [ ] `@ApiResponse`/`@Content`/`@Schema(implementation)` accurately describes runtime JSON.
- [ ] Array responses use item schemas; object wrappers use object schemas.
- [ ] Examples are declared alongside schemas when both are needed.
- [ ] `$ref` points to an existing component of the right type.
- [ ] Tests compare runtime JSON against the OpenAPI component schema.
- [ ] Verified Jackson/Swagger Core dependencies have no version mismatches.

Missing schema fields are rarely an isolated Swagger UI bug. Jackson determines properties and JSON shape; generic types and controller signatures determine how concretely Springdoc can infer responses; `@ApiResponse`/`@Schema` can alter the final schema. Compare runtime JSON, `components.schemas`, and response `$ref` entries in order, then fix the right annotation, DTO, or return type. Testing both serialization and the OpenAPI document catches missing fields early during development.

## References

- [Springdoc OpenAPI FAQ — Jackson, schema, and response customization](https://springdoc.org/faq.html)
- [Springdoc OpenAPI v2 FAQ](https://springdoc.org/v2/faq.html)
- [Jackson Annotations — JsonIgnore](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonIgnore.html)
- [Jackson Annotations — JsonUnwrapped](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonUnwrapped.html)
- [Swagger Core — @Schema annotation](https://docs.swagger.io/swagger-core/v2.2.34/apidocs/io/swagger/v3/oas/annotations/media/Schema.html)
