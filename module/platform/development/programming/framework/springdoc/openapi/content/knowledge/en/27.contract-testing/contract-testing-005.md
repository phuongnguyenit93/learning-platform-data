# Verifying Required Parameters, Defaults, and Serialization Rules

An API contract must answer three questions precisely: whether the client has to send a parameter or request body, how the server behaves when a value is omitted, and how data serializes to JSON. OpenAPI expresses these rules via attributes such as `required`, `default`, `schema`, `style`, `explode`, `readOnly`, and `writeOnly`. Springdoc derives metadata from controllers, DTOs, validation annotations, and Jackson, yet the documentation is only accurate when that metadata reflects runtime behavior.

When contract testing, do not merely assert that an endpoint returns HTTP 200. Verify both the OpenAPI JSON/YAML and live requests/responses—especially missing parameters, default values, array/object parameters, and properties serialized with custom names or formats.

## 1. Three Levels of the `required` Attribute

In OpenAPI, `required` appears in multiple places with distinct meanings:

| Location | Meaning | Example |
| --- | --- | --- |
| `Parameter.required` | Client must send the query, path, header, or cookie parameter | Query parameter `page` is required |
| `RequestBody.required` | Client must send a request body | POST requires a JSON body |
| `Schema.required` | Property must be present inside the object | `CreateBookRequest` requires `title` |

Do not confuse these three levels. A request body may be required while only some properties inside the object are required. Conversely, a parameter may be optional, yet if the client sends it, the value must still satisfy its schema.

Example:

~~~yaml
paths:
  /api/books:
    post:
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - title
              properties:
                title:
                  type: string
                subtitle:
                  type: string
~~~

In this example, the body must be present and the `title` property must appear. The `subtitle` property may be omitted.

## 2. Path Parameters Are Always Required

A path parameter is part of the URL, so OpenAPI requires `required = true`. Example:

~~~java
@GetMapping("/api/books/{id}")
public BookResponse getBook(@PathVariable long id) {
    return bookService.findById(id);
}
~~~

Corresponding OpenAPI:

~~~yaml
paths:
  /api/books/{id}:
    get:
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: integer
            format: int64
~~~

You cannot mark a path parameter as optional while keeping the `{id}` placeholder in the path template. If an endpoint supports two call forms, such as `/api/books` and `/api/books/{id}`, model them as two separate paths/operations.

## 3. Query, Header, and Cookie Parameters Can Be Optional

In Spring MVC, binding annotations determine whether a parameter is required:

~~~java
@GetMapping("/api/books")
public List<BookResponse> search(
        @RequestParam String q,
        @RequestParam(required = false) String language,
        @RequestHeader(name = "X-Client-Version", required = false) String clientVersion,
        @CookieValue(name = "catalog-view", required = false) String viewMode) {
    return bookService.search(q, language);
}
~~~

In this example:

- `q` is required because `@RequestParam` defaults to `required = true`.
- `language` is optional because `required = false`.
- `X-Client-Version` is an optional header.
- `catalog-view` is an optional cookie.

Springdoc typically infers `required` from Spring binding annotations. You can use `@Parameter` to add descriptions or adjust metadata when needed:

~~~java
@GetMapping("/api/books")
public List<BookResponse> search(
        @Parameter(
            description = "Search keyword",
            required = true
        )
        @RequestParam String q,

        @Parameter(
            description = "Book language; defaults to vi",
            required = false
        )
        @RequestParam(required = false) String language) {
    return bookService.search(q, language);
}
~~~

`@Parameter` metadata does not alter Spring binding behavior. If a Spring annotation requires a parameter while OpenAPI is customized as optional, the documentation will contradict runtime behavior. Always verify both the controller and the generated document.

With `Optional<T>`, nullable types, or `@Nullable`, verify that Springdoc and Spring MVC interpret them consistently in your project version. When a contract must be unambiguous, declare `required` explicitly and check `/v3/api-docs`.

## 4. Runtime Defaults with `defaultValue`

Spring MVC lets you declare default values directly on binding annotations:

~~~java
@GetMapping("/api/books")
public List<BookResponse> list(
        @RequestParam(defaultValue = "0") @Min(0) int page,
        @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size) {
    return bookService.findPage(page, size);
}
~~~

When the client omits `page`, Spring MVC uses `0`. When `size` is omitted, Spring MVC uses `20`. A parameter with `defaultValue` is treated as optional; the default also applies when the parameter is present with an empty value under Spring binding rules.

OpenAPI should represent the parameter as optional with the matching `default` on its schema:

~~~yaml
parameters:
  - name: page
    in: query
    required: false
    schema:
      type: integer
      minimum: 0
      default: 0
  - name: size
    in: query
    required: false
    schema:
      type: integer
      minimum: 1
      maximum: 100
      default: 20
~~~

If Springdoc does not infer `default` as expected in your version, supply metadata with `@Parameter` or `@Schema`:

~~~java
@Parameter(
    description = "Page number, zero-based",
    schema = @Schema(defaultValue = "0")
)
@RequestParam(defaultValue = "0") @Min(0) int page
~~~

What matters is that both sides agree: Spring binding actually uses `0`, and OpenAPI also documents `0`.

## 5. Distinguishing `default`, `example`, and Runtime Values

These three concepts serve different purposes:

| Attribute | Purpose | Changes Runtime Request Handling? |
| --- | --- | --- |
| `default` | Documents the parameter or schema default value | No |
| `example` | Provides a sample value for integrators | No |
| Spring binding `defaultValue` | Picks the server value when input is missing/empty per binding rules | Yes |

Example:

~~~java
@Parameter(
    description = "Number of results per page",
    example = "50",
    schema = @Schema(defaultValue = "20")
)
@RequestParam(defaultValue = "20") int size
~~~

Here, the server uses `20` when the client omits `size`. Example `50` is purely a sample value; it does not alter the runtime default.

Setting `default` only in `@Schema` or `@Parameter` does not cause Spring to assign a value automatically. Without `defaultValue` on the controller, DTO initialization logic, or a service fallback, `default` metadata can mislead clients.

Never mark a parameter `required = true` while declaring a `default` that the server applies when the parameter is missing. If the server genuinely accepts missing input, the contract should describe the parameter as optional. If the parameter is required, clients must still send it even when the schema documents a `default` value.

## 6. `required` and `default` Inside Request DTOs

For a DTO request body, `required` in an OpenAPI Schema specifies whether a property must appear in the JSON object. You can use Bean Validation and `@Schema` to express this:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record CreateBookRequest(
    @NotBlank
    @Size(max = 120)
    @Schema(
        description = "Book title",
        requiredMode = Schema.RequiredMode.REQUIRED,
        example = "Spring Boot Fundamentals"
    )
    String title,

    @Schema(
        description = "Language; if omitted, the application uses vi",
        defaultValue = "vi"
    )
    String language,

    @NotNull
    @Schema(
        description = "Whether borrowing is allowed",
        requiredMode = Schema.RequiredMode.REQUIRED
    )
    Boolean borrowable
) {}
~~~

`@NotBlank` and `@NotNull` enable runtime validation to reject invalid payloads when the controller activates validation. `requiredMode` provides explicit metadata to OpenAPI. Which constraints and metadata Springdoc reflects depends on annotation types and versions; inspect the generated schema.

`defaultValue` in `@Schema` only documents the default. For `language`, the application must still assign `"vi"` in a constructor, service, or mapping logic if runtime behavior should apply that default. When a property is omitted without fallback logic, a Java reference type will be `null`.

## 7. Distinguishing `required` from `nullable`

`required` states whether a property must be present. `nullable` states whether its value may be `null`. The two concepts are independent:

| `required` | `nullable` | Meaning |
| --- | --- | --- |
| `true` | `false` | Property must be present and value cannot be null |
| `true` | `true` | Property must be present, though value may be null |
| `false` | `false` | Property may be omitted; if sent, value cannot be null |
| `false` | `true` | Property may be omitted or sent as null |

In OpenAPI 3.0, nullability is typically expressed via `nullable: true`. OpenAPI 3.1 uses the JSON Schema model to express nullable types. How Springdoc emits this metadata depends on the configured OpenAPI version.

In Jackson, omitting a property and sending `null` are not always equivalent. For instance, `@JsonInclude(NON_NULL)` can omit null fields from response JSON; that does not automatically make a property optional in the request schema. Verify deserialization and serialization rules independently.

## 8. Query Parameter Serialization Rules

OpenAPI describes how array and object parameters are encoded in URLs using `style` and `explode`. Defaults depend on parameter location and style:

| Location | Default Style | Default Explode |
| --- | --- | --- |
| `query` | `form` | `true` |
| `path` | `simple` | `false` |
| `header` | `simple` | `false` |
| `cookie` | `form` | `true` |

For an array query parameter, `form` with `explode = true` typically encodes as repeated occurrences of the same parameter name:

~~~text
GET /api/books?tag=java&tag=spring
~~~

With `form` and `explode = false`, values are comma-joined:

~~~text
GET /api/books?tag=java,spring
~~~

Example explicitly documenting an array parameter:

~~~java
@GetMapping("/api/books")
public List<BookResponse> filter(
    @Parameter(
        name = "tag",
        in = ParameterIn.QUERY,
        description = "Tags to filter by",
        array = @ArraySchema(schema = @Schema(type = "string"))
    )
    @RequestParam(required = false) List<String> tag) {
    return bookService.filterByTags(tag);
}
~~~

If using a comma-separated format, declare the matching `style`/`explode` and confirm Spring binding parses that exact format. Never change OpenAPI metadata alone and expect Spring to alter request parsing automatically.

In the array example above, the query parameter uses OpenAPI's defaults (`style: form` and `explode: true`), so values are sent by repeating `tag`. With `swagger-annotations`, when declaring array items via `@Parameter`'s `array` attribute, `style` and `explode` attributes may be ignored; if a different serialization style is required, inspect the output OpenAPI model and customize the parameter after Springdoc generates the document.

## 9. Object Query Parameter Serialization

OpenAPI supports `deepObject` for certain object-typed query parameters. Example filter:

~~~text
GET /api/books?filter%5Bauthor%5D=linh&filter%5Byear%5D=2025
~~~

It can be described as:

~~~java
@Parameter(
    name = "filter",
    in = ParameterIn.QUERY,
    style = ParameterStyle.DEEPOBJECT,
    explode = Explode.TRUE,
    schema = @Schema(implementation = BookFilter.class)
)
~~~

`deepObject` is an OpenAPI serialization rule. Spring MVC does not automatically bind arbitrary nested object graphs under all `deepObject` variations. Verify the actual binding mechanism, such as `@ModelAttribute`, custom converters, or argument resolvers. If runtime expects a different structure, the documentation must reflect how clients actually need to send it.

For complex object or array parameters, verify percent-encoded URLs and inspect live requests in integration tests. Avoid guessing how brackets, commas, or reserved characters get encoded.

## 10. `style`, `explode`, and `allowReserved`

Commonly used serialization attributes:

| Attribute | Role |
| --- | --- |
| `style` | How arrays/objects are formatted inside the parameter |
| `explode` | Whether elements are split into separate name/value pairs |
| `allowReserved` | Permits reserved characters without percent-encoding in query values |

`allowReserved` applies only to query parameters. Enabling it does not mean the server ignores URL encoding rules or accepts arbitrary characters everywhere. Verify that gateways, servlet containers, and the framework handle it identically.

When `style`/`explode` are omitted, clients use OpenAPI defaults based on location and style. You do not need to write every default explicitly in annotations; override only when the contract requires non-default serialization.

## 11. Jackson Determines JSON Property Names

OpenAPI schemas must use the property names clients actually send and receive after Jackson serialization or deserialization. `@JsonProperty` can rename JSON fields:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

public record BookResponse(
    @JsonProperty("book_id")
    Long id,

    @JsonProperty("display_title")
    String title
) {}
~~~

The JSON output uses `book_id` and `display_title`. Springdoc integrates Jackson metadata to describe property names; still inspect `components.schemas` in `/v3/api-docs` to ensure the document matches the application's `ObjectMapper`.

If a naming strategy such as `SNAKE_CASE` is configured on `ObjectMapper`, property names can change globally. Never assume Java field names are always the JSON names.

## 12. `readOnly` and `writeOnly` for Requests/Responses

A property may appear only in responses or only be sent by clients in requests. Jackson provides access modes:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;
import io.swagger.v3.oas.annotations.media.Schema;

public class UserDto {

    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    @Schema(accessMode = Schema.AccessMode.READ_ONLY)
    private Long id;

    @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
    @Schema(accessMode = Schema.AccessMode.WRITE_ONLY)
    private String password;

    private String displayName;
}
~~~

`readOnly` suits server-generated properties such as `id` or `createdAt`. `writeOnly` suits input fields that must never be returned, such as `password`. Use separate request and response DTOs when bidirectional structures differ significantly; this keeps the contract clearer and lowers data-exposure risk.

OpenAPI `readOnly`/`writeOnly` are schema metadata. Jackson access modes control runtime serialization/deserialization behavior. Both must stay in sync.

## 13. `@JsonInclude` and Omitted Properties

Jackson can omit properties from JSON output:

~~~java
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record BookDetailResponse(
    @JsonProperty("book_id")
    Long id,
    String title,
    String subtitle
) {}
~~~

If `subtitle` is `null`, Jackson may omit it from the JSON output. That does not mean the property does not exist in the schema or cannot be sent by clients in requests. `@JsonInclude` controls serialization; `required` and `nullable` govern the schema contract.

Common options:

| Value | Behavior |
| --- | --- |
| `ALWAYS` | Always serialize the property |
| `NON_NULL` | Omit properties with null values |
| `NON_EMPTY` | Omit empty strings, empty collections, or values considered empty |
| `NON_DEFAULT` | Omit values equal to defaults per Jackson rules |

If the API uses `NON_EMPTY` or `NON_DEFAULT`, verify live JSON responses with nulls, empty strings, empty collections, and default values. Do not infer schema `required` status solely from whether a property can be omitted in a response.

## 14. Date/Time Formatting and Data Types

Jackson and its Java Time module determine how dates/times serialize. Example:

~~~java
import com.fasterxml.jackson.annotation.JsonFormat;
import java.time.LocalDate;
import java.time.OffsetDateTime;

public record BookDateResponse(
    @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = "yyyy-MM-dd")
    LocalDate publishedOn,

    OffsetDateTime updatedAt
) {}
~~~

OpenAPI usually documents `LocalDate` as `string` with format `date` and `OffsetDateTime` as `string` with format `date-time`. When using `@JsonFormat` with a custom pattern, inspect generated schemas/examples and runtime JSON; never assume default formats still apply.

For enums, `@JsonValue` or custom serializers can change JSON values. Enum schemas must list the exact strings clients send and receive, not merely Java constant names.

## 15. `@JsonAlias` and Multiple Input Names

Jackson can accept alternative property names during deserialization:

~~~java
import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;

public record CreateBookRequest(
    @JsonProperty("display_title")
    @JsonAlias({"title", "bookTitle"})
    String title
) {}
~~~

Here, runtime accepts `display_title`, `title`, or `bookTitle` when reading JSON, while serializing with the primary name `display_title`. OpenAPI schemas usually document the primary name; aliases are not always represented automatically. If clients depend on legacy aliases, document them in descriptions or maintain appropriate compatible schemas/endpoints.

## 16. Combined Example: Search Endpoint with Defaults and Array Parameters

Controller:

~~~java
@RestController
@RequestMapping("/api/books")
public class BookController {

    @GetMapping
    public List<BookResponse> search(
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size,
            @RequestParam(required = false) String q,
            @RequestParam(required = false) List<String> tag) {
        return bookService.search(page, size, q, tag);
    }
}
~~~

Expected contract:

~~~yaml
paths:
  /api/books:
    get:
      parameters:
        - name: page
          in: query
          required: false
          schema:
            type: integer
            minimum: 0
            default: 0
        - name: size
          in: query
          required: false
          schema:
            type: integer
            minimum: 1
            maximum: 100
            default: 20
        - name: q
          in: query
          required: false
          schema:
            type: string
        - name: tag
          in: query
          required: false
          style: form
          explode: true
          schema:
            type: array
            items:
              type: string
~~~

Requests to verify:

~~~http
GET /api/books
GET /api/books?page=2&size=50
GET /api/books?q=spring
GET /api/books?tag=java&tag=spring
~~~

The first request uses `page = 0` and `size = 20`. The last sends two `tag` values using `form`/`explode`. If your application's Spring binding or custom converters handle arrays differently from this example, update serialization metadata to match.

## 17. Testing OpenAPI Metadata

Use a Spring Boot integration test to fetch OpenAPI JSON and assert `required`/`default`:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OpenApiContractTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void pageParameterIsOptionalAndHasDefault() throws Exception {
        String body = mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();

        JsonNode spec = objectMapper.readTree(body);
        JsonNode parameters = spec.at("/paths/~1api~1books/get/parameters");

        JsonNode page = StreamSupport.stream(parameters.spliterator(), false)
            .filter(parameter -> "page".equals(parameter.path("name").asText()))
            .findFirst()
            .orElseThrow();

        assertThat(page.path("required").asBoolean()).isFalse();
        assertThat(page.at("/schema/default").asInt()).isEqualTo(0);
    }
}
~~~

In a real test, add imports for `MockMvc`, `ObjectMapper`, `JsonNode`, `StreamSupport`, AssertJ, and static matchers. If docs are protected by Spring Security, supply an appropriate test user/authority or dedicated test security configuration.

You can check request body schemas similarly:

~~~java
JsonNode schema = spec.at("/components/schemas/CreateBookRequest");
JsonNode required = schema.path("required");

assertThat(required.toString()).contains("title");
~~~

This test catches cases where annotation or dependency changes cause Springdoc to alter `required` metadata.

## 18. Testing Runtime Behavior and JSON Serialization

Checking documentation alone is not enough. Confirm the server actually applies defaults and Jackson produces expected JSON:

~~~java
@Test
void missingPagingParametersUseRuntimeDefaults() throws Exception {
    // bookService is a mock injected in the test fixture.
    mockMvc.perform(get("/api/books"))
        .andExpect(status().isOk());

    verify(bookService).search(0, 20, null, null);
}
~~~

Checking JSON responses:

~~~java
@Test
void responseUsesJsonNamesAndOmitsNullProperties() throws Exception {
    BookDetailResponse response = new BookDetailResponse(42L, "Spring Boot", null);

    String json = objectMapper.writeValueAsString(response);

    assertThat(json).contains("\"book_id\"");
    assertThat(json).doesNotContain("subtitle");
}
~~~

Property names and null-omission rules in tests must match your application's actual DTOs. For request DTOs, test valid JSON, missing required properties, null values, and aliases if supported.

## 19. Common Pitfalls

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Parameter has default yet OpenAPI marks it required | Binding metadata or customizer out of sync | Check `defaultValue`, `@Parameter.required`, and output document |
| OpenAPI declares default yet server does not use it | Only `@Schema.defaultValue` or `@Parameter` metadata was set | Configure runtime default in binding, DTO, or service |
| Body is required yet property is optional | Confusing `RequestBody.required` with `Schema.required` | Check both `requestBody` and `schema.required` |
| Nullable property wrongly documented as required | Confusing `required` with `nullable` | Define presence and nullability separately |
| Array query parameter parsed improperly | `style`/`explode` does not match how Spring binding reads requests | Inspect actual URLs and serialization configuration |
| Object query parameter fails to bind | `deepObject` was only declared in OpenAPI | Configure `@ModelAttribute`, converter, or resolver |
| JSON uses different property names than schema | Jackson `@JsonProperty` or naming strategy renames fields | Inspect `ObjectMapper` and `components.schemas` |
| Response still includes null fields | `@JsonInclude` not applied in the right scope | Check annotations, mixins, and `ObjectMapper` config |
| Schema allows sending read-only properties | Missing `readOnly`/`writeOnly` or shared request/response DTO | Align Jackson access modes with OpenAPI schema |
| Enum shows Java name instead of JSON value | Custom serializer or `@JsonValue` not reflected | Inspect actual JSON and enum schema |
| Date format in docs differs from runtime | `@JsonFormat` or Java Time module changes format | Test serialization and compare with schema/examples |
| Alias accepted at runtime but absent from docs | `@JsonAlias` not represented automatically | Document aliases or maintain compatible schemas |

## 20. Contract Verification Checklist

- [ ] Path parameters are marked `required`.
- [ ] Query, header, and cookie parameters have `required` matching runtime binding.
- [ ] Parameters with runtime defaults are documented as optional with the matching schema `default`.
- [ ] `default` and `example` are not used interchangeably.
- [ ] `RequestBody.required` matches whether the endpoint accepts a missing body.
- [ ] `Schema.required` reflects required properties in JSON objects.
- [ ] `nullable` is verified independently from `required`.
- [ ] `style` and `explode` match how clients must serialize array/object parameters.
- [ ] Jackson property naming matches schemas and runtime JSON.
- [ ] `readOnly`/`writeOnly` match serialization/deserialization behavior.
- [ ] `@JsonInclude` and `@JsonFormat` are verified with real data.
- [ ] Enums and aliases reflect the exact values clients can send/receive.
- [ ] Integration tests verify OpenAPI JSON/YAML.
- [ ] Runtime tests verify defaults, validation, and JSON serialization.

An accurate contract stays aligned across Spring binding, OpenAPI metadata, and Jackson behavior. `required` governs whether clients must send data; `default` describes the value used when input is missing; `style`/`explode` govern parameter encoding; and Jackson governs JSON names and shape. Checking both the OpenAPI document and runtime requests/responses catches drift early before clients integrate.

## References

- [OpenAPI Specification — Parameter Object and serialization](https://spec.openapis.org/oas/v3.1.0#parameter-object)
- [Swagger Core — @Parameter annotation](https://docs.swagger.io/swagger-core/v2.2.34/apidocs/io/swagger/v3/oas/annotations/Parameter.html)
- [Swagger Core — ParameterStyle enum](https://docs.swagger.io/swagger-core/v2.2.11/apidocs/io/swagger/v3/oas/annotations/enums/ParameterStyle.html)
