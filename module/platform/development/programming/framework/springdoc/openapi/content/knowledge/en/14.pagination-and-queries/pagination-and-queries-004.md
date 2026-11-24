# Zero-Based vs. One-Based Page Indexing and Real-World Contracts

Paginating with a `page` query parameter seems simple, but systems can interpret page numbering using two different conventions. With zero-based indexing, `page=0` is the first page. With one-based indexing, `page=1` is the first page.

Spring Data uses zero-based page indexing in `Pageable`, `PageRequest`, and `Page.getNumber()`. A public API can still choose to accept `page=1` for the first page, but it must translate explicitly between the client's convention and the internal index. Spring Boot has an option to support one-based query parameters when binding into `Pageable`; that option does not change the zero-based nature of `PageRequest` and `Page` metadata.

With Springdoc, OpenAPI documentation must describe the exact convention that clients send and receive. Never leave users to guess from the `page` parameter name or `Pageable` type whether the first page is 0 or 1.

## 1. Distinguishing Zero-Based and One-Based

The two conventions differ in the value of the first page:

| Convention | First page | Second page | Third page | Offset formula |
|---|---:|---:|---:|---|
| Zero-based | `page=0` | `page=1` | `page=2` | `offset = page × size` |
| One-based | `page=1` | `page=2` | `page=3` | `offset = (page - 1) × size` |

Example with `size=20`:

- Zero-based `page=0` fetches items from offset 0 to 19.
- One-based `page=1` also fetches items from offset 0 to 19.
- Zero-based `page=2` and one-based `page=3` both start at offset 40.

Both conventions access the exact same data if the server translates properly. The difference lies in the request contract clients must send.

## 2. Why Does Spring Data Use Zero-Based Indexing?

Spring Data's foundational APIs are designed around internal zero-based indexing:

```java
PageRequest firstPage = PageRequest.of(0, 20);
PageRequest secondPage = PageRequest.of(1, 20);
PageRequest thirdPage = PageRequest.of(2, 20);
```

The first parameter of `PageRequest.of(page, size)` is a zero-based page index. `Page.getNumber()` also returns a zero-based page index. `Page.getTotalPages()` returns the total number of pages; `Page.getNumberOfElements()` returns the actual number of items on the current page.

Repository query example:

```java
Page<Product> products = productRepository.findAll(
    PageRequest.of(0, 20, Sort.by("name").ascending())
);

int internalPageIndex = products.getNumber(); // 0
```

Even when an API accepts one-based queries, once a `PageRequest` is created, the internal index for the first page is still 0. Never pass `page=1` from a one-based client directly into `PageRequest.of(1, size)`, because the server would return the second page.

## 3. Zero-Based Contract for Public APIs

If zero-based is chosen, the query parameters can be documented as follows:

```http
GET /api/products?page=0&size=20
```

Meaning:

- `page`: page index starting from 0; defaults to `0`.
- `size`: maximum number of items per page; e.g., defaults to `20`.
- `sort`: sorting criteria, if supported by the API.

Example controller accepting `Pageable`:

```java
import org.springdoc.core.annotations.ParameterObject;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
class ProductController {

    @GetMapping
    Page<ProductResponse> list(
        @ParameterObject
        @PageableDefault(page = 0, size = 20, sort = "name")
        Pageable pageable
    ) {
        return productService.findAll(pageable).map(ProductResponse::from);
    }
}
```

`@ParameterObject` asks Springdoc to decompose `Pageable` into query parameters, typically `page`, `size`, and `sort`. `@PageableDefault` sets defaults for the Pageable object when the request omits the corresponding values. To keep the contract clear, the `page` description should explicitly state that `0` is the first page, `size` is the item count, and specify any maximum limit.

## 4. One-Based Contract for Public APIs

Many user-facing APIs choose one-based numbering because "page 1, page 2" is more intuitive. In that case, the first request is:

```http
GET /api/products?page=1&size=20
```

The server must convert from the public page number to the Spring Data index:

```java
int pageIndex = pageNumber - 1;
Pageable pageable = PageRequest.of(pageIndex, size);
```

With manual handling, validate `pageNumber >= 1` before subtracting 1. Do not silently convert `page=0` into the first page when the contract specifies one-based numbering; returning a 400 error helps clients catch convention mismatches.

### Example Controller Explicitly Accepting One-Based Input

```java
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.validation.annotation.Validated;

@RestController
@Validated
@RequestMapping("/api/products")
class ProductController {

    @GetMapping
    ResponseEntity<ProductPageResponse> list(
        @Parameter(
            description = "Page number, starting from 1. The first page is page=1.",
            example = "1",
            schema = @Schema(defaultValue = "1", minimum = "1")
        )
        @RequestParam(defaultValue = "1")
        @Min(1) int page,

        @Parameter(
            description = "Maximum number of products per page.",
            example = "20",
            schema = @Schema(defaultValue = "20", minimum = "1", maximum = "100")
        )
        @RequestParam(defaultValue = "20")
        @Min(1) @Max(100) int size
    ) {
        Page<Product> result = productService.findAll(
            PageRequest.of(page - 1, size, Sort.by("name").ascending())
        );
        return ResponseEntity.ok(ProductPageResponse.fromOneBased(result));
    }
}
```

In this example, the client sends a one-based page; the controller converts it to `page - 1` before calling Spring Data. `@Parameter` supplies description and example so OpenAPI documentation accurately reflects the convention. `@Min` and `@Max` validate values at runtime when Bean Validation is enabled for method parameters according to application configuration; the project needs the corresponding validation dependency, typically `spring-boot-starter-validation`.

This example uses `jakarta.validation`, matching modern Jakarta-based Spring Boot lines. Older projects using `javax.validation` will have different imports.

## 5. Enabling One-Based Query Parameters for `Pageable` in Spring Boot

If a controller accepts `Pageable` directly, Spring Boot allows configuring the resolver so the `page` query parameter is interpreted as one-based:

```yaml
spring:
  data:
    web:
      pageable:
        one-indexed-parameters: true
```

Or in `application.properties`:

```properties
spring.data.web.pageable.one-indexed-parameters=true
```

When enabled, a request `?page=1&size=20` is converted by the Pageable argument resolver into a `Pageable` with `getPageNumber() == 0`. A request `?page=2&size=20` translates to internal page index `1`.

Key points:

- This option affects how the Spring Data web resolver binds query parameters into `Pageable`.
- It does not change `PageRequest.of(...)`; that API still takes a zero-based index.
- It does not change `Page.getNumber()`; the value remains the internal zero-based index.
- It does not automatically turn response metadata into one-based.
- It does not automatically ensure OpenAPI documentation clearly states that page starts at 1.
- If a controller accepts `@RequestParam int page` and constructs `PageRequest` manually, this resolver property does not perform conversion on that int variable.

The standard one-indexed resolver usually subtracts 1 when page is greater than 0; `page=0` may still map to index 0 rather than being rejected automatically. Therefore, if the contract strictly requires `page >= 1`, enabling this property alone is insufficient for validation. Add validation at the request layer or use a suitable custom resolver. By contrast, when using `@RequestParam int page` as in the earlier example, `@Min(1)` with method validation rejects page 0.

Consequently, only enable this property when controllers actually receive `Pageable` bound by Spring. If endpoints mix `Pageable` and manual `@RequestParam page`, apply clear rules per endpoint.

## 6. Do Not Confuse One-Based Queries with Zero-Based `Page` Metadata

This is a common source of bugs. When `one-indexed-parameters=true`, clients send `page=1` for the first page, while the internal `Pageable` has page number 0. The `Page` returned by the repository still has:

```java
page.getNumber() == 0
```

If the API returns `Page<T>` directly or a metadata structure built directly on `Page.getNumber()`, the response may contain `number: 0` while the request used `page=1`.

This is not necessarily wrong: the metadata represents the internal zero-based index. However, if the public contract expects both request and response to be one-based, you must convert the metadata when building the response.

### One-Based Metadata DTO

```java
public record PageMetadata(
    int page,
    int size,
    long totalElements,
    int totalPages,
    boolean first,
    boolean last
) {
    static PageMetadata fromOneBased(Page<?> result) {
        return new PageMetadata(
            result.getNumber() + 1,
            result.getSize(),
            result.getTotalElements(),
            result.getTotalPages(),
            result.isFirst(),
            result.isLast()
        );
    }
}

public record ProductPageResponse(
    List<ProductResponse> content,
    PageMetadata page
) {
    static ProductPageResponse fromOneBased(Page<Product> result) {
        return new ProductPageResponse(
            result.getContent().stream().map(ProductResponse::from).toList(),
            PageMetadata.fromOneBased(result)
        );
    }
}
```

With this response, the first page has `page: 1`. `totalPages` remains the total count of pages, without adding 1. `first` and `last` come from the Page result; do not recompute them from the public index.

JSON example:

```json
{
  "content": [
    { "id": 42, "name": "Keyboard" }
  ],
  "page": {
    "page": 1,
    "size": 20,
    "totalElements": 45,
    "totalPages": 3,
    "first": true,
    "last": false
  }
}
```

If the API chooses zero-based for requests, response metadata should keep `page: 0` for the first page. What matters is documenting the semantics clearly in the schema and response descriptions.

## 7. Using `Pageable` with Springdoc

Springdoc supports documenting `Pageable` as query parameters via `@ParameterObject`:

```java
@GetMapping
Page<ProductResponse> list(@ParameterObject Pageable pageable) {
    return productService.findAll(pageable).map(ProductResponse::from);
}
```

The documentation typically displays:

| Parameter | Meaning |
|---|---|
| `page` | Page index |
| `size` | Items per page |
| `sort` | One or more sorting criteria |

However, Springdoc recognizing `Pageable` does not mean it automatically knows whether your application's contract is zero-based or one-based across all configurations. Add clear descriptions, examples, and defaults for `page`. You can use `@Parameter` or a parameter customization mechanism appropriate for your Springdoc version.

When exact control over OpenAPI content is needed, you can declare query parameters explicitly with `@RequestParam` as in the one-based example above. This approach is more verbose but makes it straightforward to guarantee description, minimum, default, and example match the conversion logic.

### `@PageableDefault` Does Not Change the Index Convention

Example:

```java
@PageableDefault(page = 0, size = 20)
Pageable pageable
```

`page = 0` is the internal default value of Pageable. When the resolver is configured as one-based, external queries can still start at 1 while the default Pageable is constructed with page index 0. Do not change it to `@PageableDefault(page = 1)` just because the public API accepts `page=1`; doing so can shift the internal default to the second page.

## 8. Documenting a Zero-Based Contract in OpenAPI

If the public API uses zero-based numbering, parameters should state that clearly:

```yaml
parameters:
  - name: page
    in: query
    required: false
    description: Zero-based page index; the first page is page=0.
    schema:
      type: integer
      minimum: 0
      default: 0
      example: 0
  - name: size
    in: query
    required: false
    description: Maximum number of items per page.
    schema:
      type: integer
      minimum: 1
      maximum: 100
      default: 20
```

## 9. Documenting a One-Based Contract in OpenAPI

If the public API uses one-based numbering, the schema should reflect minimum 1 and example 1:

```yaml
parameters:
  - name: page
    in: query
    required: false
    description: One-based page number; the first page is page=1.
    schema:
      type: integer
      minimum: 1
      default: 1
      example: 1
  - name: size
    in: query
    required: false
    description: Maximum number of items per page.
    schema:
      type: integer
      minimum: 1
      maximum: 100
      default: 20
```

In OpenAPI 3.0, `example` is typically placed on the Parameter Object or Schema Object according to the supported structure; if your project's validator enforces one, choose a valid placement for the spec version in use. What matters most is that descriptions and bounds accurately represent the contract.

## 10. Controlling `size`, Negative Values, and Out-of-Range Pages

Index convention is not the only pagination rule. The API also needs to publish:

- What the default `size` is.
- The maximum allowed size.
- How negative or zero `page` values are handled.
- Whether a page beyond `totalPages` returns an empty list, 404, or a validation error.
- Default sort order and allowed sort fields.

Clients should not be allowed to send unbounded `size` values, as they can produce heavy queries and huge responses. With one-based numbering, `page=0` should usually be rejected with 400; with zero-based numbering, `page=-1` should be rejected. `size` must be greater than 0 and capped at a maximum.

Out-of-range pages usually return an empty content array along with total element metadata, though this is an API contract decision. Pick one behavior and document it consistently.

When computing offsets manually, watch out for integer overflow with very large page or size values. Use `Pageable`/`PageRequest` and validate inputs rather than multiplying two unvalidated integers yourself.

## 11. `sort` Is Part of the Pagination Contract

Spring Data typically accepts sorting via the `sort` query parameter. Example:

```http
GET /api/products?page=1&size=20&sort=name,asc&sort=createdAt,desc
```

Each value can include a property name and a sort direction. Publish the allowed sort properties; do not let clients pass arbitrary database column names. The API can map public sort names to corresponding domain/repository properties.

Example documentation:

```yaml
- name: sort
  in: query
  required: false
  description: Sort criteria; can be repeated, e.g., sort=name,asc.
  schema:
    type: array
    items:
      type: string
  style: form
  explode: true
```

If the controller uses `Pageable`, verify how Springdoc represents the sort parameter in your current version. If the API has custom sorting rules, describe them clearly via annotations or explicit parameter declarations.

## 12. Impact on Response Links and Page Navigation

If the API returns `next`, `previous`, `first`, or `last` links, page numbers in those URLs must follow the public convention.

One-based example:

```json
{
  "page": 1,
  "size": 20,
  "totalPages": 3,
  "links": {
    "self": "/api/products?page=1&size=20",
    "next": "/api/products?page=2&size=20",
    "last": "/api/products?page=3&size=20"
  }
}
```

A zero-based example would use `page=0`, `page=1`, and `page=2` for those same three pages. Do not take the internal page number directly to build one-based URLs without adding 1; equally, do not add 1 twice if a converting resolver and a URL helper already return the public number.

If using OpenAPI Link Objects for relationships between the current and next page, runtime expressions must reference the right cursor/page value in the response. A Link Object does not automatically generate pagination URLs or a `Link` header; the server must return real links if clients navigate from the response.

## 13. Testing to Catch Off-by-One Errors

The most common bug is skipping the first page or duplicating the first two pages due to an off-by-one conversion error. Test at least these cases:

| Request | Zero-based contract | One-based contract |
|---|---|---|
| First value | `page=0` | `page=1` |
| Second value | `page=1` | `page=2` |
| Invalid value under strict contract | `page=-1` | `page=0` |
| Omitted page | Defaults to first page | Defaults to first page |

Example test for one-based to Pageable mapping:

```java
import org.junit.jupiter.api.Test;
import org.springframework.data.domain.PageRequest;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class PageIndexMapperTest {

    @Test
    void convertsOneBasedPageToZeroBasedIndex() {
        int publicPage = 1;
        int internalPage = publicPage - 1;

        assertThat(PageRequest.of(internalPage, 20).getPageNumber()).isZero();
    }

    @Test
    void rejectsZeroForOneBasedContract() {
        int publicPage = 0;

        assertThatThrownBy(() -> toZeroBasedPage(publicPage))
            .isInstanceOf(IllegalArgumentException.class);
    }

    private int toZeroBasedPage(int publicPage) {
        if (publicPage < 1) {
            throw new IllegalArgumentException("page must start from 1");
        }
        return publicPage - 1;
    }
}
```

For endpoints using Spring `Pageable`, include an integration test confirming the resolver configuration actually converts `page=1` into page index 0. If the contract requires rejecting `page=0`, add a test for that condition because the default one-indexed resolver may still map it to the first page. Also inspect the JSON response metadata to verify the returned `page` follows the published convention.

## 14. Verifying Generated Springdoc Documentation

After running the application, open `/v3/api-docs` and check the paginated operation. For zero-based, description/example/default should state `page=0` is the first page. For one-based, minimum/default/example should correspond to `1`.

You can use `curl` and `jq` to inspect parameters:

```bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '.paths["/api/products"].get.parameters'
```

Inspect the response schema:

```bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '.components.schemas.ProductPageResponse'
```

If returning `Page<T>` directly, inspect the schema structure generated by Springdoc and do not assume response metadata has been converted to one-based. If the contract needs custom metadata, create a dedicated response DTO and document `page` clearly.

## 15. Migrating a Released API from Zero-Based to One-Based

Changing `page=0` to `page=1` is a breaking change to the request contract. Existing clients may already send `page=0` for the first page; if the server suddenly switches to one-based, those requests could be rejected or return wrong data.

A migration plan should include:

1. Identifying which clients use the API and the current convention.
2. Not silently changing semantics on the same route while old clients are still supported.
3. Considering a new API version or a transition period with a clear compatibility mechanism.
4. Updating OpenAPI descriptions, defaults, minimums, examples, and response metadata.
5. Updating SDKs, guides, pagination links, and tests.
6. Monitoring legacy requests during the transition before retiring support.

If both conventions must be supported simultaneously, avoid using the same `page` parameter with ambiguous semantics. Create a separate endpoint version or a distinctly named parameter during the migration window. The approach must be unambiguous so a valid request never has two interpretations.

## 16. Common Pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| `page=1` returns the second page | Passed one-based value directly into `PageRequest.of` | Subtract 1 before creating PageRequest or use the one-indexed resolver |
| `page=0` returns 400 when previously valid | API switched to one-based | Update clients or maintain compatibility per plan |
| Request uses `page=1` but response reports `number=0` | `Page.getNumber()` is still zero-based | Convert metadata to one-based if required by contract |
| `@PageableDefault(page = 1)` makes default the second page | Confusing internal page index with public page number | Keep Pageable default at 0; resolver handles one-based queries |
| Enabled `one-indexed-parameters` yet controller binds wrongly | Controller uses `@RequestParam int` or builds PageRequest manually | Adapt conversion for the actual parameter type received |
| OpenAPI does not state whether first page is 0 or 1 | Used `@ParameterObject Pageable` without adding descriptions | Add description, default, minimum, and example |
| Next/previous links repeat or skip pages | URL uses wrong convention or adds/subtracts 1 twice | Check conversion formula and response metadata |
| Query results are too large | Unbounded `size` | Configure default, maximum, and validation |

## 17. Checklist for Designing a Pagination Contract

- [ ] Clearly chose zero-based or one-based for the `page` query parameter.
- [ ] Default value matches the first page of the chosen convention.
- [ ] When using Spring Data, understood that `PageRequest` and `Page.getNumber()` are always zero-based.
- [ ] If `spring.data.web.pageable.one-indexed-parameters` is enabled, the controller actually receives `Pageable` via the resolver.
- [ ] If accepting `@RequestParam` manually, custom conversion and validation logic is in place.
- [ ] `@PageableDefault` uses the appropriate internal page index, not confused with public page number.
- [ ] OpenAPI description, minimum, default, and example accurately reflect the contract.
- [ ] Response metadata uses the same convention as the request or clearly notes it is internal zero-based.
- [ ] `size` has a default value and a maximum limit.
- [ ] Sort parameter and allowed sort fields are clearly documented.
- [ ] Pagination links use page numbers matching the public convention.
- [ ] Tests cover first page, next page, boundary values, and out-of-range pages.
- [ ] Checked `/v3/api-docs` after changing configuration or annotations.
- [ ] A compatibility plan exists if changing the convention of a released API.

Spring Data uses zero-based page indexing internally, while an API can expose either zero-based or one-based numbering to clients. When using `Pageable`, `spring.data.web.pageable.one-indexed-parameters` converts one-based queries to the internal index; when accepting `page` manually, the controller must convert it itself. Springdoc must document both request and response conventions accurately, and tests must verify that the first page actually returns the right data to avoid off-by-one bugs.
