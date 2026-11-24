# Page Size Limits and Filter Constraints to Document Explicitly

List APIs commonly allow clients to paginate, sort, and filter data. Without limiting page size or filter scope, a single request can force the application to read, sort, or count far too many records. If OpenAPI documentation does not state limits clearly, clients may send requests that the server rejects, clamps, or processes at high resource cost.

In Spring Boot with Spring Data, `Pageable` helps accept `page`, `size`, and `sort` parameters. Springdoc-openapi can represent them alongside DTO filters using `@ParameterObject`. Bean Validation and Spring Data Web configuration enforce limits; OpenAPI needs to publish the same rules so clients know valid values.

## 1. Why Limit Pagination and Filters?

A list endpoint can be called by a browser, mobile app, scheduled report, or automated integration client. If an endpoint allows `size=1000000`, the query can:

- Read and convert too many records.
- Hold many objects in memory and increase response latency.
- Produce huge responses that waste bandwidth and slow down clients.
- Sort large datasets or use unindexed columns.
- Compute total matching records with an expensive `COUNT` query.

Overly broad or unchecked filters can also create heavy queries. For example, searching with empty strings, multi-year date ranges, huge `IN` lists, or sorting by unsupported properties can cause heavy load or runtime errors.

A solid query contract should clearly answer:

1. Does page numbering start at `0` or `1`?
2. What is the default page size?
3. What are the minimum and maximum page sizes?
4. Which fields and directions can clients sort by?
5. Which filters are optional and which are required?
6. What are the limits on string length, value ranges, item counts, and date spans?
7. When a parameter is invalid, does the server return `400`, fall back to a default, or clamp to the maximum?

## 2. Spring Data Pagination Parameters

When a controller receives `Pageable`, Spring Data Web typically maps query parameters by convention:

| Parameter | Meaning | Example |
|---|---|---|
| `page` | Page index | `page=0` is the first page when using zero-based indexing. |
| `size` | Requested number of items in a page | `size=20`. |
| `sort` | Property and sort direction | `sort=createdAt,desc`. |

Example:

```http
GET /api/products?page=0&size=20&sort=createdAt,desc
```

Multiple sort criteria can be passed by repeating the parameter:

```http
GET /api/products?page=0&size=20&sort=status,asc&sort=createdAt,desc
```

The order of sort criteria matters. In the example above, results are sorted by `status` ascending, then by `createdAt` descending.

### 2.1. Zero-Based and One-Based Page Index

Spring Data defaults to page indexing starting at `0`:

- `page=0`: first page.
- `page=1`: second page.
- `page=2`: third page.

If the API wants 1-based numbering, you can enable `one-indexed-parameters`. The resolver then translates request page numbers into the appropriate internal index. Publish this convention explicitly because clients often compute `page + 1` or `page - 1` themselves.

Do not mix both conventions within the same API. Switching from zero-based to one-based after clients have integrated is a contract change that can cause clients to fetch the wrong pages.

## 3. Setting Default and Maximum Page Size

Spring Data Web has a default page size and a resolver maximum limit. Common defaults are 20 items per page, while the default upper limit can be quite large (often 2,000). Do not rely on implicit defaults; configure values suited to your application's load and SLA.

In Spring Boot, you can configure this in `application.yml`:

```yaml
spring:
  data:
    web:
      pageable:
        default-page-size: 20
        max-page-size: 100
        page-parameter: page
        size-parameter: size
        one-indexed-parameters: false
```

In this configuration:

- If the client omits `size`, the resolver uses 20.
- Effective size does not exceed 100.
- Query parameter names are `page` and `size`.
- Page indexing starts at 0.

`max-page-size` is a cap on the `Pageable` resolution mechanism; when a client sends a value above that cap, the resolver may clamp the effective size to the maximum. This behavior does not mean the server automatically returns `400 Bad Request`. If the contract requires rejecting values above the limit, validate the input explicitly rather than relying solely on resolver clamping.

### 3.1. Configuring via Java

You can configure limits on `PageableHandlerMethodArgumentResolver` with a customizer:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.web.config.PageableHandlerMethodArgumentResolverCustomizer;

@Configuration
class PageableConfiguration {

    @Bean
    PageableHandlerMethodArgumentResolverCustomizer pageableCustomizer() {
        return resolver -> resolver.setMaxPageSize(100);
    }
}
```

A customizer is useful when programmatic configuration or custom rules are needed. If `spring.data.web.pageable.max-page-size` is already set, avoid setting a different value in a customizer that makes it unclear to the team where the effective limit comes from.

### 3.2. Endpoint-Specific Defaults

`@PageableDefault` sets defaults for a single method:

```java
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.data.domain.Sort;
import org.springdoc.core.annotations.ParameterObject;

@GetMapping("/api/products")
Page<ProductResponse> findProducts(
        @ParameterObject
        @PageableDefault(size = 20, sort = "createdAt", direction = Sort.Direction.DESC)
        Pageable pageable) {
    return productService.findAll(pageable);
}
```

`@PageableDefault` controls default values when the client omits parameters. Maximum limits should still be configured centrally on the resolver. Never treat `@PageableDefault(size = 20)` as a maximum cap; clients can still request a larger size if the resolver permits it.

You can use `@SortDefault` or `@SortDefault.SortDefaults` when multiple default sort criteria are needed. Check the API documentation to ensure default sorting applied by the server is also described to clients.

## 4. Limiting `page`, `size`, and Behavior for Invalid Values

Limiting page size does not replace validating all pagination parameters. The API must define behavior for these inputs:

| Input | Recommended rule to publish |
|---|---|
| Omitted `page` | Use default page, typically `0`. |
| Negative `page` | Reject with `400` or normalize per a published rule. |
| Omitted `size` | Use default size. |
| `size=0` or negative | Reject or use default; avoid ambiguous behavior. |
| `size` larger than max | Reject or clamp to max; document the behavior explicitly. |
| Very large `page` | Return an empty page or respond per convention; do not assume it is an error unless specified by API. |
| Malformed `sort` | Return a clear validation error. |
| Unsupported sort field | Reject with `400` rather than letting a repository error surface as `500`. |

If you want to return `400` for an oversized `size`, accept separate parameters and construct `PageRequest` after validation:

```java
@GetMapping("/api/products")
Page<ProductResponse> findProducts(
        @RequestParam(defaultValue = "0") @Min(0) int page,
        @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size) {

    Pageable pageable = PageRequest.of(page, size);
    return productService.findAll(pageable);
}
```

For method validation to enforce constraints on scalar parameters, configure Bean Validation appropriately for your Spring Boot/Spring Framework version. Depending on the version, `@Validated` on the controller or Spring MVC's method validation mechanism is needed. Add `spring-boot-starter-validation` if the application lacks a validation provider.

When using separate parameters, OpenAPI documentation can describe limits directly:

```java
@Operation(parameters = {
    @Parameter(
        name = "page",
        in = ParameterIn.QUERY,
        description = "Page index, starting from 0",
        schema = @Schema(type = "integer", minimum = "0", defaultValue = "0")
    ),
    @Parameter(
        name = "size",
        in = ParameterIn.QUERY,
        description = "Items per page, from 1 to 100",
        schema = @Schema(type = "integer", minimum = "1", maximum = "100", defaultValue = "20")
    )
})
```

This example uses `@Operation` and `@Parameter` from Swagger Annotations. If using `Pageable` with `@ParameterObject`, springdoc generates `page`, `size`, and `sort` automatically; do not re-declare parameters of the same name in a way that creates duplicates. Pick one clear publication strategy: let springdoc infer from `Pageable` and verify the output, or declare query parameters explicitly when the controller accepts individual parameters.

## 5. Documenting `Pageable` in OpenAPI with springdoc

For controllers accepting `Pageable`, use `@ParameterObject` so springdoc decomposes the object into query parameters:

```java
import org.springdoc.core.annotations.ParameterObject;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;

@GetMapping("/api/products")
Page<ProductResponse> findProducts(
        @ParameterObject
        @PageableDefault(size = 20)
        Pageable pageable,
        @Valid @ParameterObject @ModelAttribute ProductFilter filter) {
    return productService.search(filter, pageable);
}
```

OpenAPI typically renders individual `page`, `size`, and `sort` parameters. `@ParameterObject` is a springdoc annotation for documenting query properties; `Pageable` is the Spring Data type used to receive and resolve parameters.

Check `/v3/api-docs` to confirm:

- `page` is an integer and documents the starting index.
- `size` is an integer with default and maximum matching the resolver.
- `sort` documents the property/direction syntax accepted by the API.
- The filter DTO is flattened into query parameters, not mistakenly documented as a JSON request body.

Do not assume springdoc always infers `max-page-size` from resolver configuration. If runtime limits do not appear in the schema, add OpenAPI metadata via annotations/customizers or declare parameters explicitly, then re-verify the docs.

### 5.1. Avoid Exposing the Full `Page` Structure Directly If Unnecessary

Spring Data's `Page<T>` contains page data and pagination metadata. Its serialized JSON structure can depend on the Spring Data version and serializer settings. If a stable response contract is needed, create a dedicated DTO:

```java
public record PageResponse<T>(
        List<T> items,
        int page,
        int size,
        long totalElements,
        int totalPages,
        boolean last
) {}
```

Map `Page<T>` to `PageResponse<T>` in the service or controller. This controls field names, schemas, and the exact metadata clients need.

## 6. Restricting Sort and Allowed Field Lists

Spring Data lets clients send sort properties, for example:

```text
?sort=createdAt,desc&sort=name,asc
```

Clients should not be allowed to sort arbitrarily on any entity property. A nonexistent sort field can make the repository throw errors; sorting on an unindexed column or complex relation can trigger very heavy queries.

Publish the list of supported fields, for example:

| Public sort key | Supported directions | Meaning |
|---|---|---|
| `name` | `asc`, `desc` | Product name. |
| `price` | `asc`, `desc` | Product price. |
| `createdAt` | `asc`, `desc` | Creation timestamp. |

You can validate sort before passing it to the repository:

```java
private static final Set<String> ALLOWED_SORTS = Set.of(
        "name",
        "price",
        "createdAt"
);

private void validateSort(Sort sort) {
    for (Sort.Order order : sort) {
        if (!ALLOWED_SORTS.contains(order.getProperty())) {
            throw new InvalidQueryParameterException(
                    "Sorting is not supported by: " + order.getProperty()
            );
        }
    }
}
```

In real applications, map public sort keys to internal properties or query expressions rather than using entity field names directly. This keeps the contract stable when persistence structures evolve.

Never accept raw SQL expressions from query parameters. Use an allowlist and fixed server-side mapping. Also validate sort direction syntax; Spring Data only supports `ASC` and `DESC` for `Sort.Direction`.

## 7. Constraints for Query Filters

The filter DTO should clearly express data types, valid values, and size limits. Example product filter:

```java
public class ProductFilter {

    @Size(max = 80)
    private String keyword;

    private ProductStatus status;

    @DecimalMin("0.00")
    @DecimalMax("1000000.00")
    private BigDecimal minPrice;

    @DecimalMin("0.00")
    @DecimalMax("1000000.00")
    private BigDecimal maxPrice;

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate createdFrom;

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate createdTo;

    // getters and setters
}
```

Controller:

```java
@GetMapping("/api/products")
PageResponse<ProductResponse> search(
        @Valid @ParameterObject @ModelAttribute ProductFilter filter,
        @ParameterObject @PageableDefault(size = 20) Pageable pageable) {
    validateSort(pageable.getSort());
    return productService.search(filter, pageable);
}
```

The annotations help document and validate each field:

- `@Size(max = 80)`: keyword does not exceed 80 characters.
- `ProductStatus`: accepts only defined enum values.
- `@DecimalMin`/`@DecimalMax`: price values fall within published bounds.
- `@DateTimeFormat`: parses query strings in ISO date format `yyyy-MM-dd`.
- `@Valid`: triggers validation on the filter DTO.

`@ParameterObject` helps springdoc emit properties as query parameters. Bean Validation enforces constraints at runtime; OpenAPI schemas should be checked to confirm limits are reflected accurately.

### 7.1. Limiting Search Strings

A `keyword` filter should have a sensible maximum length. Searching on an empty or whitespace-only string rarely yields useful results and can turn queries into full scans.

You can normalize input by trimming whitespace and treating empty strings as an omitted filter. Document this behavior clearly in the description and test these cases:

- Omitting `keyword`.
- Passing an empty `keyword`.
- Passing a whitespace-only string.
- Passing a string exceeding the length limit.
- Passing Unicode or Vietnamese diacritical characters.

When using `@Size(max = 80)`, note that `null` remains valid. For optional filters, this is usually desired; do not add `@NotBlank` if clients are allowed to omit the filter.

### 7.2. Limiting Numeric Ranges

When `minPrice` and `maxPrice` exist, each value must lie within valid bounds. You must also check the relationship between them:

```text
minPrice <= maxPrice
```

Field-level `@DecimalMin` and `@DecimalMax` annotations do not enforce cross-field relationships automatically. Use a class-level Bean Validation constraint or business validator to verify the cross-field condition.

When one bound is omitted, define its meaning clearly:

- Only `minPrice`: fetch products at or above the minimum price.
- Only `maxPrice`: fetch products at or below the maximum price.
- Both present: filter within a closed or open interval per contract.
- Neither present: do not apply a price filter.

### 7.3. Limiting Time Ranges

For time filters, publish format, time zone, and boundary rules. If using `LocalDate`, a query might look like:

```text
GET /api/products?createdFrom=2026-01-01&createdTo=2026-03-31
```

Specify whether `createdTo` is inclusive of the entire day. For timestamp columns, an error-resistant approach is a half-open interval `[from, to)`: `createdAt >= from` and `createdAt < to`. When accepting `OffsetDateTime` or `Instant`, publish accepted time zones/offsets and normalize timestamps to UTC when querying.

Beyond checking `createdFrom <= createdTo`, you can limit the maximum span, such as 90 days, to prevent overly broad queries. A 90-day limit is just a business example; pick a value based on data volume, indexes, and product needs.

### 7.4. Limiting Filter Lists

If the API accepts multiple IDs or statuses in a query, limit the number of elements:

```java
@Size(max = 50)
private List<UUID> ids;
```

In OpenAPI, the corresponding schema can include `maxItems: 50`. Also publish how clients send multiple values—repeated parameters vs. comma-separated—and verify the binder handles the format properly. Never let a single request generate an unbounded `IN` clause with thousands of values.

## 8. Cross-Field Constraints and Business Validation

Some rules cannot be expressed using independent per-parameter limits alone:

- `minPrice` must not exceed `maxPrice`.
- `createdFrom` must not be after `createdTo`.
- Date span must not exceed 90 days.
- If `status=ARCHIVED`, the `archivedAtFrom` filter may be required.
- Two mutually exclusive filter modes are disallowed simultaneously.

You can create a class-level constraint with Jakarta Bean Validation:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = ValidProductFilterValidator.class)
public @interface ValidProductFilter {
    String message() default "Invalid filter range";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
```

The validator reads the whole DTO and checks cross-field relationships:

```java
public class ValidProductFilterValidator
        implements ConstraintValidator<ValidProductFilter, ProductFilter> {

    @Override
    public boolean isValid(ProductFilter value, ConstraintValidatorContext context) {
        if (value == null) {
            return true;
        }

        boolean valid = true;
        if (value.getMinPrice() != null && value.getMaxPrice() != null
                && value.getMinPrice().compareTo(value.getMaxPrice()) > 0) {
            valid = false;
        }

        if (value.getCreatedFrom() != null && value.getCreatedTo() != null
                && value.getCreatedFrom().isAfter(value.getCreatedTo())) {
            valid = false;
        }
        return valid;
    }
}
```

Attach the constraint at the class level:

```java
@ValidProductFilter
public class ProductFilter {
    // Filter properties and getters/setters
}
```

In real applications, attach specific messages per violation using `ConstraintValidatorContext` so clients know which field or relationship failed. If enforcing a maximum date span, also check `ChronoUnit.DAYS.between(from, to)`.

OpenAPI can describe per-parameter limits via schemas and descriptions. Cross-field rules typically need clear descriptions such as "`createdFrom` must be less than or equal to `createdTo`"; do not assume a single parameter schema can express all of that logic.

## 9. Documenting Filter Constraints in OpenAPI

For filter DTOs, use `@Schema` to add descriptions, examples, formats, and bounds where needed:

```java
public class ProductFilter {

    @Schema(
            description = "Keyword to search in product name, maximum 80 characters",
            example = "laptop"
    )
    @Size(max = 80)
    private String keyword;

    @Schema(description = "Product status")
    private ProductStatus status;

    @Schema(description = "Minimum price, must be less than or equal to maxPrice",
            minimum = "0.00", maximum = "1000000.00")
    @DecimalMin("0.00")
    @DecimalMax("1000000.00")
    private BigDecimal minPrice;

    @Schema(description = "Creation start date, format yyyy-MM-dd",
            type = "string", format = "date")
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate createdFrom;
}
```

Bean Validation expresses runtime constraints; `@Schema` clarifies details for documentation. Avoid contradictory values such as `@Size(max=80)` alongside `@Schema(maxLength=120)`. After generating docs, inspect the actual schema and adjust annotations or customizers if springdoc does not map them properly.

Condensed OpenAPI example for several query parameters:

```yaml
parameters:
  - name: keyword
    in: query
    required: false
    description: Keyword to search in product name, maximum 80 characters
    schema:
      type: string
      maxLength: 80
  - name: minPrice
    in: query
    required: false
    description: Minimum price; must not exceed maxPrice
    schema:
      type: number
      minimum: 0
      maximum: 1000000
  - name: createdFrom
    in: query
    required: false
    schema:
      type: string
      format: date
```

With `Pageable`, the documentation also needs to describe `page`, `size`, and `sort`, where `size` reflects the configured maximum limit. `description` is the right place to state whether the server clamps oversized values instead of returning `400`.

## 10. Being Mindful of Query Costs

Limiting values is not just input validation. Several design choices directly impact query cost:

- **`Page` vs. `Slice`**: `Page` typically needs total items/pages, which can trigger a count query; `Slice` only checks whether more data follows and can avoid a count depending on the query.
- **Sort fields**: permit only meaningful fields backed by proper indexing plans.
- **Date ranges**: cap time spans and use index-friendly column predicates.
- **Keyword search**: clearly define prefix, exact match, or contains semantics; `LIKE '%term%'` can be costly without an appropriate search mechanism.
- **ID lists**: cap element counts to avoid oversized `IN` clauses.
- **Optional filters**: avoid generating predicates that unnecessarily defeat index usage.

For very large datasets or deep sequential browsing, consider cursor/keyset pagination. Cursors typically rely on a deterministic order, such as `(createdAt, id)`, to prevent newly inserted rows from shifting offsets between calls. When using cursors, documentation must describe cursor format, opacity, expiration, and how clients pass the next cursor.

## 11. Testing Pagination and Filter Limits

Tests should cover resolver configuration, DTO validation, and OpenAPI schemas.

### 11.1. Testing Maximum Size

With a resolver limit of `max-page-size=100`, send a request with `size=500` and verify behavior matches the contract:

- If the policy is clamping: the service receives `Pageable.getPageSize() == 100`.
- If the policy is rejection: the response is `400` and the error body states the limit.

Do not check only `200` status; verify the actual page size passed down to the service/repository.

### 11.2. Testing the Filter DTO

Recommended test cases:

| Case | Expected outcome |
|---|---|
| Omitting optional filters | Query does not apply those conditions. |
| `keyword` longer than 80 characters | Validation fails. |
| Negative `minPrice` | Validation fails. |
| `minPrice` greater than `maxPrice` | Class-level validation fails. |
| `createdFrom` after `createdTo` | Class-level validation fails. |
| Date span exceeding limit | Validation fails per policy. |
| `ids` exceeding 50 items | Validation fails. |
| Sort field outside allowlist | Returns `400`, never lets repository error surface as `500`. |

### 11.3. Testing OpenAPI

Read `/v3/api-docs` or the corresponding group URL and verify:

- `page` accurately documents zero-based/one-based indexing matching config.
- `size` has default and maximum matching runtime.
- `sort` describes syntax and allowed fields.
- Filter parameters have accurate type, format, enum, min/max, maxLength, or maxItems.
- The filter DTO is documented as query parameters, not a request body.
- Descriptions state cross-field rules that single-field schemas cannot express.

MockMvc example testing filter validation:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ProductSearchValidationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void rejectsKeywordLongerThanLimit() throws Exception {
        String keyword = "x".repeat(81);

        mockMvc.perform(get("/api/products")
                        .param("keyword", keyword))
                .andExpect(status().isBadRequest());
    }
}
```

This test assumes the controller enables Bean Validation for `@ModelAttribute` and an exception handler maps errors to `400`. If your Spring MVC version or validation setup differs, adjust method validation configuration and assertions to match the real application.

## 12. Common Pitfalls

- **Using only `@PageableDefault` to limit size**: the annotation sets a default, not a maximum. Configure the resolver to enforce the maximum size.
- **Not documenting clamping vs. rejection**: clients do not know how an oversized `size` is handled.
- **Limiting at runtime without updating OpenAPI**: Swagger UI may suggest values the server rejects.
- **Allowing sorting on any property**: can trigger expensive queries or property path errors; use an allowlist.
- **Skipping cross-field filter validation**: individual min/max values are valid, yet their combination is invalid.
- **Not capping date spans or ID lists**: requests can issue overly broad queries.
- **Confusing `Page` and `Slice`**: responses and query costs differ.
- **Not testing page indexing**: client and server can drift on zero-based vs. one-based numbering.
- **Letting a filter DTO become a request body**: for query filters, use `@ModelAttribute` and `@ParameterObject` properly.
- **Assuming OpenAPI constraints validate at runtime**: schemas describe contracts; Spring requires Bean Validation or custom logic to enforce them.

## 13. List API Design Workflow

1. **Choose the pagination model**: `Page`, `Slice`, or cursor/keyset based on data needs.
2. **Set default and max page size**: configure Spring Data Web and standardize clamping vs. rejection.
3. **Lock down page indexing**: zero-based or one-based, and keep it consistent.
4. **Allowlist sort fields**: publish supported fields and directions.
5. **Design the filter DTO**: choose types, required/optional flags, defaults, and formats.
6. **Set per-field and cross-field constraints**: lengths, numeric bounds, enums, time spans, item counts.
7. **Generate OpenAPI docs**: use `@ParameterObject`, `@Schema`, and descriptions to publish limits.
8. **Check query costs**: inspect indexes, count queries, sorts, and data ranges.
9. **Test boundaries**: confirm runtime and `/v3/api-docs` reflect the same contract.

## 14. Review Checklist

- [ ] `page` uses a clearly published zero-based or one-based convention.
- [ ] `default-page-size` and `max-page-size` are explicitly configured.
- [ ] Policy for oversized `size` (clamp vs. reject) is documented.
- [ ] `@PageableDefault` is used only for defaults, not mistaken for a maximum.
- [ ] `Pageable` and filter DTO are documented by springdoc using `@ParameterObject`.
- [ ] OpenAPI accurately reflects defaults/maximums of `page` and `size`.
- [ ] Sort fields and directions are restricted to an allowlist.
- [ ] Filters have appropriate type, format, enum, min/max, maxLength, or maxItems.
- [ ] Cross-field rules are validated on the server and described in documentation.
- [ ] Date ranges, ID lists, and keywords have sensible bounds.
- [ ] Choice of `Page`, `Slice`, or cursor fits query cost.
- [ ] Integration tests cover valid, boundary, and invalid values.
- [ ] `/v3/api-docs` matches runtime behavior.

## 15. References

- [Spring Data – Web support and Pageable](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html#core.web)
- [Spring Data Commons – `PageableHandlerMethodArgumentResolver`](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PageableHandlerMethodArgumentResolver.html)
- [Spring Boot – Application Properties: Spring Data Web](https://docs.spring.io/spring-boot/appendix/application-properties/index.html#appendix.application-properties.data)
- [Spring Framework – Data Binding and Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [OpenAPI Specification 3.1.2 – Parameter Object](https://spec.openapis.org/oas/v3.1.2.html#parameter-object)
- [springdoc-openapi FAQ – Pageable support](https://springdoc.org/faq.html)

Pagination and filter limits must be enforced on the server, documented in OpenAPI, and verified with real requests. When defaults, maximums, sort allowlists, and filter constraints are published clearly, clients can build valid queries while the application maintains tighter control over reading, sorting, and returning data.
