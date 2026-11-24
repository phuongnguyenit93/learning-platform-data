# Documenting Query DTO Filters

When an API requires many search conditions, declaring each `@RequestParam` directly on the controller can make the method signature long and hard to maintain. Spring MVC allows grouping query parameters into a DTO using `@ModelAttribute`; springdoc-openapi can expand the DTO's properties into separate query parameters in the documentation using `@ParameterObject`. This keeps validation, default values, and filter descriptions in a clear model while preserving the proper HTTP semantics: clients still send key-value pairs in the URL.

## 1. What Is a Query Filter DTO?

Suppose a product search API needs the following conditions:

- Keyword `keyword`.
- List of statuses `status`.
- Category ID `categoryId`.
- Price range `minPrice` and `maxPrice`.
- Creation date range `createdFrom` and `createdTo`.
- Page number and page size.

If each parameter is declared individually, the controller can become verbose:

```java
@GetMapping("/api/products")
Page<ProductResponse> search(
    @RequestParam(required = false) String keyword,
    @RequestParam(required = false) List<ProductStatus> status,
    @RequestParam(required = false) Long categoryId,
    @RequestParam(required = false) BigDecimal minPrice,
    @RequestParam(required = false) BigDecimal maxPrice,
    @RequestParam(required = false) LocalDate createdFrom,
    @RequestParam(required = false) LocalDate createdTo,
    @RequestParam(defaultValue = "0") int page,
    @RequestParam(defaultValue = "20") int size
) {
    // ...
}
```

You can group the filter conditions into a class:

```java
public class ProductFilter {
    private String keyword;
    private List<ProductStatus> status;
    private Long categoryId;
    private BigDecimal minPrice;
    private BigDecimal maxPrice;
    private LocalDate createdFrom;
    private LocalDate createdTo;

    // getters and setters
}
```

Clients still call the endpoint with a query string:

```http
GET /api/products?keyword=pen&status=ACTIVE&status=DRAFT&categoryId=5&minPrice=10000&maxPrice=50000&createdFrom=2026-01-01&createdTo=2026-12-31&page=0&size=20
```

The DTO only groups input data on the Java side. It does not turn the query string into a JSON body and does not change how the HTTP request is sent.

## 2. Distinguishing @ModelAttribute and @ParameterObject

These two annotations are often used together but belong to two different layers:

| Annotation | Package | Role |
|---|---|---|
| Spring `@ModelAttribute` | `org.springframework.web.bind.annotation` | Binds query parameters/form fields into an object at runtime |
| springdoc `@ParameterObject` | `org.springdoc.core.annotations` in springdoc 2.x | Instructs springdoc to expand object properties into individual parameters in OpenAPI |
| Swagger `@Parameter` | `io.swagger.v3.oas.annotations` | Adds metadata for a specific parameter |
| Swagger `@Schema` | `io.swagger.v3.oas.annotations.media` | Describes type, format, constraints, example, and property details |

`@ModelAttribute` affects how Spring processes the request. `@ParameterObject` only affects how springdoc generates documentation; it performs no binding and does not replace `@ModelAttribute`.

The package of `@ParameterObject` changed between springdoc major versions: springdoc 2.x uses `org.springdoc.core.annotations.ParameterObject`; 1.x versions use `org.springdoc.api.annotations.ParameterObject`. Use the import matching the major version in your project's dependencies.

Example:

```java
@GetMapping("/api/products")
Page<ProductResponse> search(
    @Valid
    @ModelAttribute
    @ParameterObject
    ProductFilter filter,
    @ParameterObject Pageable pageable
) {
    return productService.search(filter, pageable);
}
```

At runtime, Spring binds query parameters into `ProductFilter` and `Pageable`. In OpenAPI, springdoc renders properties such as `keyword`, `status`, `categoryId`, and `minPrice` as independent `in: query` parameters.

For POJOs used as query objects, explicitly include `@ModelAttribute` so readers recognize the data source and do not confuse it with `@RequestBody`. `@ParameterObject` is a springdoc annotation; it does not automatically make an arbitrary class a runtime query parameter source.

## 3. Designing the Filter DTO

The DTO should represent only the conditions clients are permitted to use. Never place persistence entities or repository objects directly into a query DTO.

Complete example:

```java
import io.swagger.v3.oas.annotations.media.Schema;
import org.springframework.format.annotation.DateTimeFormat;

public class ProductFilter {

    @Schema(description = "Keyword to search in product name or code", example = "pen")
    private String keyword;

    @Schema(description = "Statuses to include")
    private List<ProductStatus> status;

    @Schema(description = "Category ID", example = "5", minimum = "1")
    private Long categoryId;

    @Schema(description = "Minimum selling price", example = "10000", minimum = "0")
    private BigDecimal minPrice;

    @Schema(description = "Maximum selling price", example = "50000", minimum = "0")
    private BigDecimal maxPrice;

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    @Schema(description = "Creation start date (inclusive)", type = "string", format = "date", example = "2026-01-01")
    private LocalDate createdFrom;

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    @Schema(description = "Creation end date (inclusive)", type = "string", format = "date", example = "2026-12-31")
    private LocalDate createdTo;

    // getters and setters
}
```

`@Schema` provides metadata for OpenAPI, while `@DateTimeFormat` instructs Spring to convert query strings into `LocalDate`. Numeric types, enums, and collections are converted by Spring through `ConversionService` and appropriate converters.

### Why Use a JavaBean DTO for Query Binding?

Spring MVC supports binding model attributes via constructor or property access depending on class type and version. A JavaBean with a no-arg constructor and getters/setters is easy to understand and broadly compatible for query DTO examples. If using records or constructor binding, verify your Spring Framework version and the binding rules applied in your project.

Do not let clients send technical fields such as database column names, JPQL fragments, arbitrary entity property names, or unvalidated sort expressions. The DTO should hold well-defined API options.

## 4. Integrating the DTO with Controller and springdoc

The controller can declare both a filter DTO and `Pageable`:

```java
import jakarta.validation.Valid;
import org.springdoc.core.annotations.ParameterObject;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
class ProductQueryController {

    private final ProductService productService;

    ProductQueryController(ProductService productService) {
        this.productService = productService;
    }

    @GetMapping
    Page<ProductResponse> search(
        @Valid @ModelAttribute @ParameterObject ProductFilter filter,
        @ParameterObject @PageableDefault(size = 20, sort = "name") Pageable pageable
    ) {
        return productService.search(filter, pageable);
    }
}
```

In this example, `@PageableDefault` sets runtime pagination defaults. Springdoc can document `Pageable`'s `page`, `size`, and `sort` parameters; `@ParameterObject` ensures they are rendered as query parameters. Inspect the generated documentation for your specific springdoc version and Spring Data Web configuration.

If not using Spring Data `Pageable`, `page` and `size` can be placed directly inside the filter DTO. In that case, clearly specify whether page indexing starts from 0 or 1 and enforce a maximum page size.

## 5. How OpenAPI Represents a DTO as Query Parameters

OpenAPI does not use a request body in place of a query string for a standard GET. A Parameter Object can still describe an object schema with appropriate serialization, but springdoc's `@ParameterObject` typically expands POJO properties into separate Parameter Objects:

```yaml
paths:
  /api/products:
    get:
      parameters:
        - name: keyword
          in: query
          description: Keyword to search in product name or code
          schema:
            type: string
          example: pen
        - name: status
          in: query
          description: Statuses to include
          schema:
            type: array
            items:
              $ref: '#/components/schemas/ProductStatus'
          style: form
          explode: true
        - name: categoryId
          in: query
          schema:
            type: integer
            format: int64
        - name: minPrice
          in: query
          schema:
            type: number
        - name: maxPrice
          in: query
          schema:
            type: number
        - name: createdFrom
          in: query
          schema:
            type: string
            format: date
        - name: createdTo
          in: query
          schema:
            type: string
            format: date
      responses:
        '200':
          description: Page of search results
```

This is an illustrative structural example. Springdoc may add `page`, `size`, and `sort` parameters along with the `Page` response schema based on actual configuration. Final names, descriptions, required flags, and schemas must be verified at `/v3/api-docs`.

The key point is that the filter DTO is rendered as multiple `in: query` parameters, not as a single parameter with an object schema and not as a `requestBody`.

## 6. Data Types and Query String Conversion Rules

Query strings always transmit data as text. Spring converts strings to Java types using converters and formatters.

| DTO Type | Query Example | Notes |
|---|---|---|
| `String` | `keyword=pen` | Can be trimmed or normalized in the service if required by contract |
| `Long` | `categoryId=5` | Non-numeric values typically trigger a 400 binding error |
| `BigDecimal` | `minPrice=12500.50` | Decimal separator conventions depend on converter/locale; APIs should typically use standard dot notation |
| `Boolean` | `available=true` | Standardize true/false values |
| `Enum` | `status=ACTIVE` | Usually converted by enum name; check converters if using custom codes |
| `LocalDate` | `createdFrom=2026-01-01` | Use `@DateTimeFormat(iso = ISO.DATE)` or an explicit pattern |
| `LocalDateTime` | `createdAt=2026-01-01T10:30:00` | Does not carry an offset/time zone |
| `List<Long>` | `categoryId=5&categoryId=8` | Standardize list serialization style |

Jackson's `@JsonFormat` mainly controls JSON serialization/deserialization; it does not replace Spring MVC formatters when binding query parameters. For query date/time values, use `@DateTimeFormat` or Spring converters/formatters. This is a critical distinction when the same DTO is mistakenly reused for both JSON bodies and query strings.

### Enum Filters

Example:

```java
public enum ProductStatus {
    DRAFT,
    ACTIVE,
    ARCHIVED
}
```

Clients send `status=ACTIVE`. If the API uses custom codes such as `active` or `archived`, register a `String -> ProductStatus` converter and document the accepted values accurately in OpenAPI. Do not rely solely on `@JsonValue` assuming Spring MVC query binding uses Jackson's serializer; query conversion and JSON serialization are separate mechanisms.

## 7. Lists and Multi-Value Serialization

A filter can accept multiple values, such as multiple statuses or multiple category IDs. OpenAPI describes array serialization using `style` and `explode`.

### Repeating the Same Key

With `style: form` and `explode: true`, clients send:

```http
GET /api/products?status=ACTIVE&status=DRAFT
```

OpenAPI:

```yaml
- name: status
  in: query
  style: form
  explode: true
  schema:
    type: array
    items:
      type: string
      enum: [DRAFT, ACTIVE, ARCHIVED]
```

### Comma-Separated Format

With `style: form` and `explode: false`, clients can send:

```http
GET /api/products?status=ACTIVE,DRAFT
```

These two forms are not automatically equivalent across every stack. Spring MVC can convert comma-separated strings into collections via default converters in many cases, though behavior must be checked carefully with custom converters, enums, or values containing commas. Pick a single convention for the API, declare `style`/`explode` accurately, and test real requests.

For `List<String>`, if values might contain commas or special characters, repeated keys are usually clearer and less ambiguous. Characters in URLs still require proper percent-encoding.

## 8. Price Ranges, Date Ranges, and Filter Combination Rules

The DTO only holds values; the service must define how those values combine.

Price range example:

- Only `minPrice`: price must be greater than or equal to the minimum.
- Only `maxPrice`: price must be less than or equal to the maximum.
- Both present: price lies in the closed interval `[minPrice, maxPrice]`.
- `minPrice > maxPrice`: invalid request.

Date ranges also need clear rules. If `createdFrom` and `createdTo` are inclusive dates, timestamp queries usually need to convert them into an interval from the start of `createdFrom` to before the start of the day after `createdTo`, in the chosen business time zone. Avoid using the start of `createdTo` as an inclusive upper bound, because that can omit records from the rest of the end date.

To validate relationships across multiple fields, create a class-level constraint such as `@ValidProductFilter` and write a `ConstraintValidator<ValidProductFilter, ProductFilter>` to compare `minPrice` with `maxPrice` and `createdFrom` with `createdTo`. This keeps cross-field rules in one place and avoids adding public boolean getters like `isPriceRangeValid()` just for `@AssertTrue`; such getters can be treated by introspection as extra properties when springdoc analyzes the query DTO.

`@Schema(minimum = ...)` or `maximum` only describes constraints in OpenAPI; it does not replace Bean Validation. Conversely, `@Min`, `@DecimalMin`, or custom validators enforce checks at runtime. Combine both so the schema and runtime stay consistent.

## 9. Default Values, Optional, and Required

Query filters are typically optional: clients send only the conditions they want to apply. Distinguish between:

- Omitted parameter: do not apply that condition or use a default value.
- Empty parameter: e.g., `keyword=`; behavior must be clearly defined, either treated as an empty string or ignored.
- Malformed value: Spring cannot convert it and typically returns 400.
- Out-of-range value: validation returns a 400 error.

Example DTO with defaults:

```java
public class ProductFilter {
    private String keyword;
    private Integer page = 0;
    private Integer size = 20;

    // getters and setters
}
```

However, if the controller uses `Pageable` with `@PageableDefault`, keep pagination defaults in one place so `page`/`size` in the DTO do not conflict with `Pageable`.

OpenAPI parameters have `required: false` when clients are not required to send them. Standard query parameters are optional unless marked required. For DTOs, springdoc infers from metadata and configuration; check `required` in the generated documentation instead of assuming every non-null Java field becomes required.

## 10. Validation and Error Handling for Query DTOs

Constraints can be applied directly to fields:

```java
public class ProductFilter {

    @Size(max = 100)
    private String keyword;

    @Min(1)
    private Long categoryId;

    @DecimalMin("0.0")
    private BigDecimal minPrice;

    @DecimalMin("0.0")
    private BigDecimal maxPrice;

    @Min(0)
    private Integer page = 0;

    @Min(1)
    @Max(100)
    private Integer size = 20;

    // getters and setters
}
```

The controller marks the parameter with `@Valid` to trigger validation on the model attribute. If errors need to be handled directly in the method, place `BindingResult` immediately after the DTO parameter:

```java
@GetMapping
Page<ProductResponse> search(
    @Valid @ModelAttribute @ParameterObject ProductFilter filter,
    BindingResult bindingResult,
    @ParameterObject Pageable pageable
) {
    if (bindingResult.hasErrors()) {
        throw new InvalidProductFilterException(bindingResult.getAllErrors());
    }
    return productService.search(filter, pageable);
}
```

If `BindingResult` is not declared immediately after the model attribute, Spring throws a binding/validation exception for the exception handler to process. Check the exact exception types for your Spring MVC version and method signature. Type conversion errors, such as `categoryId=abc`, can also appear in `BindingResult` or binding exceptions.

In OpenAPI, constraints like `maximum`, `minLength`, and `format` help clients understand valid value ranges. However, cross-field rules like `minPrice <= maxPrice` generally require descriptions/examples or more complex schemas; not every custom validator translates automatically into OpenAPI constraints.

## 11. Describing Parameters in Detail with Swagger Annotations

`@Schema` is suited for describing DTO properties. When you need control over Parameter Object-level metadata such as name, `in`, `style`, `explode`, `allowEmptyValue`, `deprecated`, or `example`, use `@Parameter` where supported by Swagger Core or declare it via an OpenAPI customizer.

Example documenting a standalone query parameter:

```java
@GetMapping("/api/products")
List<ProductResponse> search(
    @Parameter(
        name = "keyword",
        description = "Keyword to search by product name or code",
        example = "pen",
        in = ParameterIn.QUERY
    )
    @RequestParam(required = false) String keyword
) {
    return productService.search(keyword);
}
```

When using `@ParameterObject`, property metadata is usually taken from `@Schema` and supported annotations on the DTO. If a property needs specific array serialization rules, verify which annotations springdoc recognizes in your version. You can refine generated parameters afterward with an `OpenApiCustomizer` if DTO annotations are not expressive enough.

Do not declare the same query parameter twice—once via `@ParameterObject` and again via a separate `@RequestParam`—as documentation may produce duplicate parameters or runtime may read from two different sources.

## 12. Limitations with Nested DTOs

Spring MVC supports binding nested properties via property path conventions in certain model attributes, for example:

```http
GET /api/products?priceRange.min=10000&priceRange.max=50000
```

However, springdoc's `@ParameterObject` has limitations with nested parameter objects; do not assume a nested DTO will automatically expand into query parameters with the exact desired structure across all versions.

There are three ways to handle this:

1. **Flatten the DTO:** use top-level `minPrice`, `maxPrice`, `categoryId`. This is usually the simplest approach for filter APIs.
2. **Declare parameters explicitly:** use `@RequestParam`/`@Parameter` for each key when names like `priceRange.min` must be preserved.
3. **Customize OpenAPI:** use an `OpenApiCustomizer` to add parameters with the exact names, schemas, style, and explode, then verify Spring MVC actually binds those keys.

Example flat DTO:

```java
public class ProductFilter {
    private BigDecimal minPrice;
    private BigDecimal maxPrice;
    private Long categoryId;
}
```

A flat DTO keeps URLs short, schemas readable, and client model generation straightforward. If the contract requires deeply structured query objects, verify both client serialization and Spring binding rather than adjusting OpenAPI alone.

## 13. Safe Sorting and Pagination

`Pageable` typically supports `page`, `size`, and `sort` query parameters. Example:

```http
GET /api/products?page=0&size=20&sort=name,asc&sort=createdAt,desc
```

Spring Data can accept multiple sort conditions. However, clients should not be allowed to pass arbitrary SQL column names or query expressions. Only allow sorting on a published list of API properties, then map them to the corresponding persistence properties.

Allowlist example:

```java
private static final Set<String> ALLOWED_SORTS = Set.of(
    "name",
    "sellingPrice",
    "createdAt"
);

private Sort validateSort(Sort requestedSort) {
    for (Sort.Order order : requestedSort) {
        if (!ALLOWED_SORTS.contains(order.getProperty())) {
            throw new InvalidSortFieldException(order.getProperty());
        }
    }
    return requestedSort;
}
```

In practice, you can map an API name like `price` to the entity property `sellingPrice` instead of exposing persistence field names to clients. Also cap `size` to prevent clients from requesting hundreds of thousands of records in a single call.

When using both a filter DTO and `Pageable`, the documentation must avoid declaring `page`, `size`, and `sort` twice. Choose a single owner for pagination parameters.

## 14. Complete OpenAPI Example for Filters

A search operation can be described as follows:

```yaml
paths:
  /api/products:
    get:
      summary: Search products
      description: Applies only the filter conditions provided in the query string.
      parameters:
        - name: keyword
          in: query
          required: false
          description: Keyword to search in product name or code
          schema:
            type: string
            maxLength: 100
        - name: status
          in: query
          required: false
          description: Filter by one or more statuses
          style: form
          explode: true
          schema:
            type: array
            items:
              type: string
              enum: [DRAFT, ACTIVE, ARCHIVED]
        - name: categoryId
          in: query
          schema:
            type: integer
            format: int64
            minimum: 1
        - name: minPrice
          in: query
          schema:
            type: number
            minimum: 0
        - name: maxPrice
          in: query
          schema:
            type: number
            minimum: 0
        - name: createdFrom
          in: query
          description: Start date, inclusive
          schema:
            type: string
            format: date
        - name: createdTo
          in: query
          description: End date, inclusive
          schema:
            type: string
            format: date
        - name: page
          in: query
          schema:
            type: integer
            minimum: 0
            default: 0
        - name: size
          in: query
          schema:
            type: integer
            minimum: 1
            maximum: 100
            default: 20
        - name: sort
          in: query
          description: Property and sort direction; only API-published fields are supported
          schema:
            type: array
            items:
              type: string
          style: form
          explode: true
      responses:
        '200':
          description: Page of products matching the filters
        '400':
          description: Malformed query parameter or validation error
```

This example illustrates the desired contract. Spring Data's `Pageable` may generate a different page response schema and sort description depending on springdoc configuration. If a stable paginated response format is needed across versions, use a dedicated response DTO rather than depending directly on `Page`'s internal structure.

## 15. Verifying Documentation and Runtime Binding

After starting the application, open `/v3/api-docs` or `/v3/api-docs.yaml`. Locate `GET /api/products` and check:

1. Each filter property appears as an `in: query` parameter.
2. Parameter names match what clients must send.
3. `required`, `description`, `example`, `format`, `enum`, `minimum`, and `maximum` are accurate.
4. Arrays have `style` and `explode` matching how clients send them.
5. There are no duplicate query parameters.
6. `page`, `size`, and `sort` have proper defaults and limits.
7. No internal entity or non-contract DTO properties leak into the spec.

Then test with real requests:

```bash
curl -G 'http://localhost:8080/api/products' \
  --data-urlencode 'keyword=blue pen' \
  --data-urlencode 'status=ACTIVE' \
  --data-urlencode 'status=DRAFT' \
  --data-urlencode 'minPrice=10000' \
  --data-urlencode 'maxPrice=50000' \
  --data-urlencode 'createdFrom=2026-01-01' \
  --data-urlencode 'createdTo=2026-12-31' \
  --data-urlencode 'page=0' \
  --data-urlencode 'size=20'
```

Verify these scenarios:

- Sending no filters: API returns the default list.
- Sending one condition: only that condition is applied.
- Sending multiple conditions: conditions combine per published logic, typically AND across filter groups and OR across values within the same filter.
- Sending a nonexistent enum, invalid number, or malformed date: returns a 400 error matching the standard error schema.
- Sending `minPrice > maxPrice` or `createdFrom > createdTo`: cross-field validation rejects the request.
- Sending an oversized `size` or unsupported sort field: server rejects per API policy.

Swagger UI only reflects parameters described in the spec. Call the endpoint from the UI or curl to confirm Spring binds values properly, the service applies the right logic, and the response paginates accurately.

## 16. Testing Query DTOs with MockMvc

Example testing multi-parameter query binding:

```java
@WebMvcTest(ProductQueryController.class)
class ProductQueryControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    ProductService productService;

    @Test
    void bindsRepeatedStatusAndDateFilters() throws Exception {
        given(productService.search(any(ProductFilter.class), any(Pageable.class)))
            .willReturn(Page.empty());

        mockMvc.perform(get("/api/products")
                .param("status", "ACTIVE", "DRAFT")
                .param("createdFrom", "2026-01-01")
                .param("createdTo", "2026-12-31")
                .param("page", "0")
                .param("size", "20"))
            .andExpect(status().isOk());

        then(productService).should().search(
            argThat(filter -> filter.getStatus().equals(
                List.of(ProductStatus.ACTIVE, ProductStatus.DRAFT)
            ) && filter.getCreatedFrom().equals(LocalDate.of(2026, 1, 1))),
            any(Pageable.class)
        );
    }
}
```

This is a guiding test example; configure mocks, page responses, and matchers to fit your actual service. On older Spring Boot versions, replace `@MockitoBean` with the mock bean annotation supported by that version.

Testing invalid query types:

```java
mockMvc.perform(get("/api/products").param("categoryId", "not-a-number"))
    .andExpect(status().isBadRequest());
```

Testing OpenAPI parameters:

```java
mockMvc.perform(get("/v3/api-docs"))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$.paths['/api/products'].get.parameters[?(@.name == 'keyword' && @.in == 'query')]"
    ).exists())
    .andExpect(jsonPath(
        "$.paths['/api/products'].get.parameters[?(@.name == 'createdFrom')]"
    ).exists());
```

JSONPath filter expressions can vary across implementations and test library versions. If the matcher does not support that expression, read the `parameters` array and assert on `name` and `in`. What matters is verifying the generated spec contains separate parameters with the right names and schemas.

## 17. Common Pitfalls and Fixes

| Symptom | Cause | Fix |
|---|---|---|
| DTO is not bound from query string | Missing `@ModelAttribute`, property lacks setter/constructor binding, or wrong query name | Check binding mechanism and JavaBean properties |
| Swagger UI shows an object instead of separate query parameters | Missing `@ParameterObject` or springdoc version does not recognize the DTO | Add the annotation, check `/v3/api-docs` and version compatibility |
| DTO binds properly but docs omit a field | Property visibility/annotations or model converter does not recognize it | Check getters, `@Schema`, and springdoc config |
| Date is valid in JSON but fails in query | Used `@JsonFormat` instead of Spring formatter | Use `@DateTimeFormat` or a Converter/Formatter |
| Enum code fails to bind | Query conversion does not use Jackson's `@JsonValue` | Register a `Converter<String, Enum>` and document enum values |
| List does not receive all values | Client sends CSV while server expects repeated keys, or vice versa | Align `style`, `explode`, and query format |
| Nested DTO does not render properly in OpenAPI | `@ParameterObject` has limitations with nested parameter objects | Flatten the DTO or use explicit parameters/customizer |
| Query parameter is duplicated in docs | Same field declared through both DTO and a separate `@RequestParam` | Choose only one declaration source |
| Clients sort by internal fields | Sort parameter exposes entity property names directly | Use an allowlist and map API names to persistence |
| Docs state limits but runtime does not reject | Only `@Schema` present without validation | Add Bean Validation or explicit validation logic |

## 18. Workflow for Designing a Filter DTO

When adding a search endpoint, follow this sequence:

1. List the filter conditions clients actually need; avoid exposing entity fields directly.
2. Create a query DTO with appropriate Java types, stable property names, and clear getters/setters.
3. Use `@ModelAttribute` for Spring query-string binding and `@ParameterObject` for springdoc to emit individual parameters.
4. Add `@DateTimeFormat`, enum converters, or formatters for special query types.
5. Apply Bean Validation to individual fields and cross-field rules.
6. Document properties with `@Schema`; control `style`/`explode` for arrays.
7. Separate pagination/sorting with `Pageable` or a dedicated DTO, avoiding duplicate declarations.
8. Restrict sort fields and page sizes via allowlists and API policies.
9. Inspect `/v3/api-docs`, Swagger UI, and real HTTP requests.
10. Test empty filters, single conditions, combined conditions, and malformed input.

A filter DTO keeps controllers concise, centralizes validation, and keeps OpenAPI descriptions consistent. Spring MVC handles binding the query string into the object; `@ParameterObject` lets springdoc render each property as a query parameter; `@Schema` documents the data domain. When all three parts are configured and verified together, clients can filter accurately without knowing server-side entity or query structures.

## 19. References

- [Spring Framework – Model Attributes](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): binding request parameters into model attributes.
- [Spring Framework – Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/format.html): `ConversionService`, Formatters, and web type conversion.
- [Spring Data – Web Support](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html): `Pageable`, `Sort`, and web binding integration.
- [Springdoc OpenAPI – FAQ](https://springdoc.org/#faq): using `@ParameterObject` for POJOs and Pageable.
- [OpenAPI Specification – Parameter Object](https://spec.openapis.org/oas/latest.html#parameter-object): `in`, `style`, `explode`, `schema`, and query parameter examples.
- [Swagger Core Annotations](https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations): `@Parameter`, `@Schema`, and OpenAPI metadata.
