# Inspecting Serialized Paginated Data Instead of Relying on Type Names

## 1. Why Inspect the Actual JSON of a Paginated Response?

In Spring Boot, controllers often return Page, Slice, or List to represent query results. These Java types help the application work with paginated data, yet a return type name is not the JSON contract that clients actually receive.

When Spring MVC writes a response, Jackson and serialization settings determine the final JSON structure. The same Page type can be serialized differently depending on the Spring Data version, configuration, and wrapper type used. Springdoc OpenAPI, meanwhile, generates schemas from controller signatures, generic types, annotations, and model resolvers. Therefore, schemas inferred from Java type names may not accurately reflect the JSON on the wire.

For example, a controller declares a return type of Page<ProductResponse>. Clients need to know whether the actual response contains content, page, totalElements, and totalPages, or a different structure. Clients do not care whether the internal implementation uses PageImpl or another Page implementation.

When designing a paginated API contract, verify both ends:

- **Runtime JSON**: the body actually serialized by Jackson and sent to clients.
- **OpenAPI schema**: the documentation Springdoc publishes for that operation.

Both ends must match in property names, data types, nested structure, defaults, and pagination metadata. This lesson focuses on inspecting serialized responses, options for stable Page representations, and keeping Springdoc schemas aligned with actual payloads.

## 2. Distinguishing Java Return Types from JSON on the Wire

A method may declare:

~~~java
@GetMapping("/api/products")
public Page<ProductResponse> findAll(Pageable pageable) {
    return productService.findAll(pageable);
}
~~~

This signature states that the controller returns a Page object holding ProductResponse items. It does not fully describe the JSON clients receive.

During response generation:

1. Spring invokes the controller and receives the Page object.
2. HttpMessageConverter selects Jackson to write the body according to the media type.
3. Jackson traverses the runtime object along with modules, annotations, and configuration.
4. JSON is written to the HTTP response.
5. Clients see only the JSON, status, headers, and media type.

Consequently, do not infer the payload solely from the names Page, PageImpl, or Slice. Call the endpoint or serialize a sample object with ObjectMapper to see the real structure.

For instance, a JSON response might look like:

~~~json
{
  "content": [
    {
      "id": 101,
      "name": "Mechanical keyboard"
    }
  ],
  "page": {
    "size": 20,
    "number": 0,
    "totalElements": 41,
    "totalPages": 3
  }
}
~~~

This structure nests metadata inside a page object. Another configuration may place pagination fields at the root level. Clients need a stable structure published by the API, without guessing based on internal implementations.

## 3. Page, Slice, and List Carry Different Semantics

Spring Data offers several query result types:

| Java Type | Semantics | Metadata typically needed by clients |
|---|---|---|
| Page<T> | A page of data plus total element/page counts | content, page number, size, totalElements, totalPages |
| Slice<T> | A slice of data plus whether a next page exists | content, number, size, hasNext, hasPrevious |
| List<T> | Data list with no pagination metadata | Array of items |
| Window<T> with scrolling API | A window of data under a scrolling mechanism | Contents and continuation position per specific API |

Page typically requires a total record count query to compute totalElements and totalPages. Slice can avoid the count query and only report whether more data follows. List does not represent pagination metadata itself.

Do not declare a Page schema if the runtime response is only a List. Similarly, if an API returns Slice while docs display totalPages, that indicates the schema is inaccurate or metadata is being added in another layer.

Choosing Page, Slice, or List must be driven by client requirements. UIs showing total page counts usually need Page; infinite scroll streams may need only Slice or cursors; small lists may need only List.

## 4. Problems with Directly Serializing PageImpl

PageImpl is the common implementation of Page. If returned directly, Jackson may serialize properties exposed by the implementation and related interfaces. That JSON shape may include content, pageable, sort, number, size, totalElements, totalPages, first, last, numberOfElements, or empty, depending on version and configuration.

A structure serialized directly from PageImpl should not be treated as a stable JSON contract. Upgrading Spring Data or changing serialization configuration can alter JSON details that clients depend on.

The issue is not that Page is unhelpful in the repository/service layer. Page remains the right abstraction for querying. The issue is exposing an implementation or its raw serialization directly as the public payload without a stable contract layer.

A straightforward rule:

- Use Page<T> internally to query and compute metadata.
- Convert the result into a controlled response representation.
- Document that exact representation in OpenAPI.
- Test actual JSON to ensure the structure does not change unexpectedly.

## 5. Using PagedModel for a More Stable Representation

Spring Data provides **PagedModel** in the spring-data-web package to wrap Page and provide a representation designed for serialization.

Example:

~~~java
@GetMapping("/api/products")
public PagedModel<ProductResponse> findAll(Pageable pageable) {
    Page<ProductResponse> result = productService.findAll(pageable);
    return new PagedModel<>(result);
}
~~~

PagedModel represents page contents and metadata in a more stable structure than directly serializing PageImpl. A JSON response typically looks like:

~~~json
{
  "content": [
    {
      "id": 101,
      "name": "Mechanical keyboard"
    }
  ],
  "page": {
    "size": 20,
    "number": 0,
    "totalElements": 41,
    "totalPages": 3
  }
}
~~~

Clients read the list from content and metadata from page. Exact fields should be verified against your Spring Data version and actual ObjectMapper configuration.

PagedModel is a response representation layer. The service can still return Page<ProductResponse>; the controller or mapper wraps Page into PagedModel before sending it out.

If Springdoc's schema inference from PagedModel does not accurately display the generic item type or desired metadata, declare an explicit response schema and inspect the generated JSON/YAML. Never assume the PagedModel name guarantees every OpenAPI tool produces the right schema across all versions.

## 6. Configuring PageSerializationMode.VIA_DTO

In Spring Data versions supporting page serialization modes, you can configure Spring Data Web to convert Page into a DTO representation when writing JSON instead of serializing PageImpl directly.

Example:

~~~java
@Configuration
@EnableSpringDataWebSupport(
    pageSerializationMode =
        EnableSpringDataWebSupport.PageSerializationMode.VIA_DTO
)
public class WebConfiguration {
}
~~~

VIA_DTO mode uses Spring Data's stable representation for Page during serialization. DIRECT mode retains direct serialization of the Page object. For public APIs, VIA_DTO reduces coupling to PageImpl internals.

Several points to note:

- This option depends on the Spring Data Commons version in use.
- Check the enum and configuration mechanism of your exact dependency version.
- The setting affects Page response serialization within Spring Data Web's scope.
- It does not automatically prove every endpoint's OpenAPI schema is accurate.
- If the API uses custom serializers, ResponseBodyAdvice, or other wrappers, the final JSON still needs inspection.

When enabling VIA_DTO, capture the actual JSON and update OpenAPI schemas to match the new structure. Never change the configuration without updating and running contract tests.

## 7. Creating a Dedicated Response DTO to Control the Contract

For APIs requiring exact control over property names, metadata, and compatibility, a dedicated DTO is usually the clearest option.

Example:

~~~java
public record PageInfoResponse(
    int number,
    int size,
    long totalElements,
    int totalPages
) {}

public record ProductPageResponse(
    List<ProductResponse> content,
    PageInfoResponse page
) {}
~~~

Mapper converting Page to the response DTO:

~~~java
public final class ProductPageMapper {

    private ProductPageMapper() {}

    public static ProductPageResponse from(Page<ProductResponse> source) {
        PageInfoResponse pageInfo = new PageInfoResponse(
            source.getNumber(),
            source.getSize(),
            source.getTotalElements(),
            source.getTotalPages()
        );

        return new ProductPageResponse(
            source.getContent(),
            pageInfo
        );
    }
}
~~~

Controller:

~~~java
@GetMapping("/api/products")
public ProductPageResponse findAll(Pageable pageable) {
    Page<ProductResponse> result = productService.findAll(pageable);
    return ProductPageMapper.from(result);
}
~~~

The JSON is defined by the record DTOs:

~~~json
{
  "content": [
    {
      "id": 101,
      "name": "Mechanical keyboard"
    }
  ],
  "page": {
    "number": 0,
    "size": 20,
    "totalElements": 41,
    "totalPages": 3
  }
}
~~~

Benefits of a dedicated DTO:

- Property names are an explicit part of the contract.
- Metadata can be added or removed without depending on PageImpl.
- Springdoc can infer schemas directly from concrete response types.
- Easy to write JSON tests and contract tests.
- You can preserve the exact same representation even when changing repository querying strategies.

In return, you must write mappers and maintain DTOs. For public APIs or APIs with multiple consumers, this cost is usually worthwhile because the JSON structure stays strictly controlled.

## 8. Choosing Metadata Suited to the Client Experience

Not every client needs all of Page's metadata. Choose fields matching what the UI requires.

For instance, a PageInfo can hold:

| Field | Meaning |
|---|---|
| number | Current page index, typically starting from 0 |
| size | Applied page size |
| totalElements | Total matching records after filtering |
| totalPages | Total number of pages |
| first | Whether this is the first page |
| last | Whether this is the last page |
| numberOfElements | Actual number of items on the page |

If the API uses Slice, metadata can be:

| Field | Meaning |
|---|---|
| number | Index of the slice being read |
| size | Maximum size |
| numberOfElements | Actual number of items |
| hasNext | Whether a next slice exists |
| hasPrevious | Whether a previous slice exists |

If the API uses cursors, expose nextCursor and hasNext. Do not add totalPages to a cursor response if the backend does not compute or guarantee total page counts.

Total element counts must be computed after filters are applied. If the client filters by status=ACTIVE, totalElements must reflect ACTIVE records, not all products in the database.

## 9. How Does Springdoc Infer Schemas from Return Types?

Springdoc inspects the controller's return type, generic parameters, and OpenAPI annotations to build the Response Object. Example:

~~~java
@GetMapping("/api/products")
public Page<ProductResponse> findAll(Pageable pageable) {
    return productService.findAll(pageable);
}
~~~

From this signature, Springdoc can recognize Page and item type ProductResponse. However, the inferred schema does not necessarily match Jackson's output after applying page serialization modes, mixins, custom serializers, or response advice.

In particular, two situations can occur:

- **Runtime serialization changed**: Page is converted into PagedModel or a DTO while Springdoc still infers from a different declared type.
- **Generic type erased**: the method returns a raw type, wildcard, or intermediate wrapper so the item schema is no longer concrete.

With a dedicated response DTO, the controller signature directly reflects the public representation, giving Springdoc a clear basis for schema generation. If needed, use @ApiResponse and @Content to declare a concrete implementation schema.

Example:

~~~java
@GetMapping("/api/products")
@ApiResponse(
    responseCode = "200",
    description = "Page of products",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = ProductPageResponse.class)
    )
)
public ProductPageResponse findAll(Pageable pageable) {
    return ProductPageMapper.from(productService.findAll(pageable));
}
~~~

Here the schema implementation is ProductPageResponse, matching the actual body type. Annotations only describe documentation; they do not transform the runtime response.

## 10. Inspecting Serialized JSON with ObjectMapper

You can use ObjectMapper in tests to inspect the representation Jackson produces from a sample object.

Example with PagedModel:

~~~java
@Test
void serializesPageUsingStableRepresentation() throws Exception {
    Page<ProductResponse> page = new PageImpl<>(
        List.of(new ProductResponse(101L, "Mechanical keyboard")),
        PageRequest.of(0, 20),
        41
    );

    PagedModel<ProductResponse> model = new PagedModel<>(page);
    String json = objectMapper.writeValueAsString(model);

    JsonNode root = objectMapper.readTree(json);

    assertThat(root.has("content")).isTrue();
    assertThat(root.path("content").isArray()).isTrue();
    assertThat(root.path("page").path("number").asInt()).isZero();
    assertThat(root.path("page").path("size").asInt()).isEqualTo(20);
    assertThat(root.path("page").path("totalElements").asLong()).isEqualTo(41);
}
~~~

This test verifies object serialization via ObjectMapper. It helps catch changes when upgrading Jackson or Spring Data.

However, an ObjectMapper test does not replace HTTP testing. Spring MVC may use different converters, configuration, advice, or filters than a manually constructed ObjectMapper in a unit test. Therefore, also test responses through MockMvc or WebTestClient to verify the application's actual configuration.

## 11. Inspecting HTTP JSON with MockMvc

An integration test can invoke the endpoint and verify the real body structure:

~~~java
mockMvc.perform(get("/api/products")
        .param("page", "0")
        .param("size", "20"))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.content").isArray())
    .andExpect(jsonPath("$.page.number").value(0))
    .andExpect(jsonPath("$.page.size").value(20))
    .andExpect(jsonPath("$.page.totalElements").value(41));
~~~

If the API still returns PageImpl directly, assertions must reflect the actual current JSON. When switching to PagedModel or a DTO, update assertions to verify the new contract.

Additional checks to include:

- First page, middle page, and last page.
- Empty page with no results.
- Page beyond range.
- Filters changing totalElements.
- Sorting changing content order.
- Default size and clamped size.
- Ensuring unadvertised internal metadata fields do not appear unexpectedly.

Tests should focus on the contract clients are allowed to depend on. Avoid asserting internal properties outside the public contract unless the API intentionally publishes them.

## 12. Inspecting the OpenAPI Schema Generated by Springdoc

After verifying runtime JSON, fetch the OpenAPI document:

~~~http
GET /v3/api-docs
~~~

Locate the corresponding operation and verify the schema:

- Correct response code, e.g., 200.
- Correct media type, usually application/json.
- Body schema has the right object or array structure.
- content has item type ProductResponse.
- page metadata contains number, size, totalElements, and totalPages per the contract.
- No unadvertised internal properties appear.
- Required, nullable, and format match actual JSON.
- Examples accurately reflect the response structure.

If using a dedicated DTO, OpenAPI should reference the ProductPageResponse component. If using PagedModel, confirm the generated schema accurately shows content and page. If Springdoc produces an overly generic schema or loses the generic item type, add explicit descriptions or use a concrete DTO.

A thorough contract test can read the OpenAPI JSON and compare key properties against response fixtures. This catches cases where Jackson serialization changes while documentation stays stale, or documentation changes while runtime still returns the old shape.

## 13. Distinguishing JSON Serialization from Pageable Query Parameters

Pageable often appears as a controller input:

~~~java
@GetMapping("/api/products")
public ProductPageResponse findAll(
    @ParameterObject Pageable pageable
) {
    return ProductPageMapper.from(productService.findAll(pageable));
}
~~~

`@ParameterObject` helps Springdoc document Pageable as query parameters such as page, size, and sort. It only affects how documentation describes inputs.

Distinguish both sides:

- **Request parameters**: page, size, and sort tell clients how to request a page of data.
- **Response JSON**: content and metadata tell clients which page the server returned and how much data exists.

Documentation showing page/size/sort properly does not prove the response schema is accurate. Likewise, a response with content/page does not mean input query parameters are documented properly.

Verify request and response as two independent halves of the same operation.

## 14. When Using Slice or Cursor, Do Not Publish Page Metadata

If a service returns Slice:

~~~java
@GetMapping("/api/products/recent")
public Slice<ProductResponse> findRecent(Pageable pageable) {
    return productService.findRecent(pageable);
}
~~~

Slice does not provide totalElements and totalPages like Page. If clients need to know whether more data follows, publish hasNext and how to continue querying.

With cursor pagination, the response might be:

~~~java
public record ProductCursorResponse(
    List<ProductResponse> content,
    String nextCursor,
    boolean hasNext
) {}
~~~

The schema must expose nextCursor and hasNext. Cursors should be treated as opaque values; clients send back the value received without interpreting it.

Do not use a Page schema merely because the endpoint path includes "page" or the method accepts Pageable. Base it on the actual payload. An endpoint can accept page/size while returning a custom DTO, Slice, or another representation.

## 15. Versioning When Changing Paginated Response Structure

Switching from raw PageImpl JSON to PagedModel or a DTO can change property names, nesting, and metadata. Even if content items stay identical, clients can break if they read the old fields.

For example, existing clients read `totalElements` at the root level:

~~~json
{
  "content": [],
  "totalElements": 41,
  "totalPages": 3
}
~~~

After the change, metadata is nested under `page`:

~~~json
{
  "content": [],
  "page": {
    "totalElements": 41,
    "totalPages": 3
  }
}
~~~

This is a structural JSON change and can break clients. Evaluate it as an API contract change, bump the version, or provide a transition period per project policy.

When making the change:

1. Record the current schema and JSON.
2. Identify which clients depend on which fields.
3. Design the new representation and update OpenAPI.
4. Write tests for old/new structures per the migration plan.
5. Announce the deprecation date for the legacy representation.
6. Monitor client migration before removing compatibility.

Never upgrade Spring Data or toggle page serialization modes without checking the impact on public JSON.

## 16. Common Issues When Inspecting Paginated Data

| Symptom | Cause to check |
|---|---|
| OpenAPI schema differs from runtime JSON | Springdoc infers from Java types while Jackson serializes via a wrapper or different config |
| JSON contains many internal PageImpl fields | Serializing Page implementation directly |
| Clients cannot find totalElements | Metadata is nested elsewhere or API uses Slice/cursor |
| Item schema is an empty object | Generic ProductResponse lost due to raw type or wrapper |
| Springdoc documents Page while runtime returns DTO | Controller signature, @ApiResponse, or customizer out of sync |
| PagedModel JSON is right but schema is wrong | Model resolver or Springdoc version fails to infer desired representation |
| ObjectMapper test passes yet HTTP response differs | MVC converter or response advice uses different settings |
| totalElements mismatches filters | Count query omits the same filter predicates |
| Dependency upgrade alters JSON | Page serialization depends on Spring Data/Jackson version |
| Clients break after metadata structure change | JSON change is a breaking change without version management |

When investigating, compare three pieces of evidence: the controller return type, runtime JSON, and OpenAPI schema. Only after understanding all three should you decide whether to fix annotations, DTOs, serializers, or configuration.

## 17. Workflow for Verifying Paginated Contracts

A workflow you can apply to every paginated endpoint:

1. Determine whether clients need Page, Slice, cursor, or a plain list.
2. Choose a stable JSON representation: dedicated DTO, PagedModel, or appropriate page serialization config.
3. Call the endpoint and save sample JSON for non-empty, empty, and filtered cases.
4. Check the name, type, and location of every property.
5. Download OpenAPI JSON from Springdoc and compare the response schema with runtime JSON.
6. Write MockMvc/WebTestClient tests for edge cases.
7. Confirm the schema preserves the concrete generic item type and metadata.
8. Re-run contract tests whenever upgrading Spring Data, Jackson, or Springdoc.
9. Treat structural changes as API version changes if clients are impacted.

You can add OpenAPI checks and contract tests to CI to catch discrepancies before release. This is especially valuable for APIs consumed by multiple frontend, mobile, or backend services.

## 18. Principles for Designing Stable Paginated Responses

When using Spring Data and Springdoc, keep in mind:

1. Page, Slice, and List are Java types; JSON is determined by actual serialization.
2. Avoid relying on raw PageImpl serialization structure as a public contract.
3. Use PagedModel or a dedicated DTO when a stable representation is required.
4. Check PageSerializationMode.VIA_DTO for your Spring Data version.
5. Document metadata in its actual location and do not advertise totalPages if runtime does not provide it.
6. Use concrete response DTOs so Springdoc infers clear schemas.
7. Verify JSON with ObjectMapper and HTTP behavior with MockMvc/WebTestClient.
8. Compare the OpenAPI document against runtime JSON.
9. Manage response structure changes as API contract changes.
10. Never rely on type names or the Swagger UI alone to conclude a payload is correct.

A reliable pagination contract starts with the JSON clients actually receive. Page makes data-layer work convenient, while a response DTO or PagedModel controls the public representation. When Springdoc documents that exact representation and tests verify both runtime and OpenAPI, clients can integrate reliably across framework upgrades.

