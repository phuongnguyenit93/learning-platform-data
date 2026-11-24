# Describing @RequestParam with Default and Optional Values

In Spring Boot, `@RequestParam` binds a request parameter to a controller method parameter. In REST APIs, this annotation is commonly used to receive values in the query string, such as search keywords, filters, page numbers, or page sizes. When integrating `springdoc-openapi`, these declarations are translated into OpenAPI parameters so clients know the name, location, data type, requirement, and default value.

The key distinction lies among three states: a required parameter, an optional parameter that can be omitted, and a parameter with a fallback value when not sent. `required`, `defaultValue`, and `Optional` help express these three intents in code.

## 1. Syntax and Default Behavior

Basic declaration:

```java
@GetMapping("/search")
List<ProductDto> search(
        @RequestParam(name = "keyword") String keyword) {
    return productService.search(keyword);
}
```

Sample request:

```http
GET /api/products/search?keyword=keyboard
```

Commonly used attributes of `@RequestParam`:

| Attribute | Meaning |
| --- | --- |
| `name` or `value` | Parameter name on the request. Both attributes are aliases of each other. |
| `required` | Whether the parameter is mandatory; defaults to `true`. |
| `defaultValue` | Value used when the parameter is missing or empty; setting this implicitly switches `required` to `false`. |

If neither `required` nor `defaultValue` is provided, the parameter is mandatory. When the client omits the parameter, Spring cannot bind the method argument and typically returns HTTP 400 Bad Request.

Declare `name` explicitly, such as `@RequestParam(name = "keyword")`, so that the name in the HTTP contract does not depend on how the compiler retains Java variable name metadata. Using `value` produces the same result:

```java
@RequestParam(value = "keyword") String keyword
```

## 2. Required Parameters with required=true

`required` defaults to `true`, so this attribute can be omitted when you want a mandatory parameter:

```java
@GetMapping("/search")
List<ProductDto> search(
        @RequestParam(name = "keyword", required = true) String keyword) {
    return productService.search(keyword);
}
```

The client must send `keyword`:

```text
GET /api/products/search?keyword=keyboard
```

Request missing `keyword`:

```text
GET /api/products/search
```

Spring cannot supply a value for the mandatory argument and returns a 400 error. `required=true` only checks whether the parameter is provided; it does not verify that the string has valid business content. For instance, if blank strings are not allowed, add validation such as `@NotBlank` and enable the appropriate validation mechanism.

In OpenAPI, a required parameter is represented by `in: query` and `required: true`:

```yaml
parameters:
  - name: keyword
    in: query
    required: true
    schema:
      type: string
```

## 3. Optional Parameters with required=false

When a parameter may be absent and the application decides how to handle it, use `required = false`:

```java
@GetMapping("/search")
List<ProductDto> search(
        @RequestParam(name = "keyword", required = false) String keyword) {
    if (keyword == null || keyword.isBlank()) {
        return productService.findFeatured();
    }
    return productService.search(keyword);
}
```

Both of the following requests can be handled:

```text
GET /api/products/search?keyword=keyboard
GET /api/products/search
```

When the parameter is absent, Spring binds `null` for reference types like `String`. Therefore, code must handle `null` before invoking methods on that value.

Avoid using primitive types like `int` or `boolean` for optional parameters without a default. Primitive types cannot represent `null`; use `Integer`, `Boolean`, another reference type, or `Optional<T>` depending on the API semantics.

OpenAPI represents an optional parameter with `required: false` or by omitting the `required` field (OpenAPI's default is `false`):

```yaml
parameters:
  - name: keyword
    in: query
    required: false
    schema:
      type: string
```

## 4. Using defaultValue to Provide a Default Value

`defaultValue` is suitable when the API has clear default behavior if the client omits the parameter. For example, the first page has index `0` and each page contains `20` products by default:

```java
@GetMapping
Page<ProductDto> listProducts(
        @RequestParam(name = "page", defaultValue = "0") int page,
        @RequestParam(name = "size", defaultValue = "20") int size) {
    return productService.findPage(page, size);
}
```

Clients can omit both parameters:

```text
GET /api/products
```

Spring binds `page = 0` and `size = 20`. If the client sends different values, the client's values are used:

```text
GET /api/products?page=2&size=50
```

When `defaultValue` is set, `required` automatically becomes `false`. You do not need to write `required = false` simultaneously unless you want to emphasize the intent for code readers.

`defaultValue` is declared as a string, which Spring converts to the argument type via its conversion mechanism. For instance, `"0"` converts to `int` `0`, `"true"` converts to `boolean`, and an enum string converts to its corresponding constant if the name is valid.

`defaultValue` is also used when the parameter is present but empty. This differs from `required = false`: an optional parameter without a default receives `null` when omitted, whereas a parameter with a default receives the fallback value when missing or empty.

OpenAPI can represent the default in the schema:

```yaml
parameters:
  - name: page
    in: query
    required: false
    schema:
      type: integer
      default: 0
  - name: size
    in: query
    required: false
    schema:
      type: integer
      default: 20
```

The default value in the documentation must match the controller's actual behavior. Do not declare a default of `20` in `@Parameter` or the schema if the actual code uses `10`.

## 5. Using Optional<T> to Express Absence

`Optional<T>` explicitly expresses that an argument may not exist:

```java
@GetMapping("/search")
List<ProductDto> search(
        @RequestParam(name = "keyword") Optional<String> keyword) {
    return keyword
        .filter(value -> !value.isBlank())
        .map(productService::search)
        .orElseGet(productService::findFeatured);
}
```

When the request omits `keyword`, Spring supplies `Optional.empty()`. When the parameter is present, the value is wrapped in `Optional`. With an `Optional` argument type, the parameter is treated as optional; there is normally no need to specify `required = false`.

`Optional<T>` can be combined with a default value when the API wants to express a fallback value as well:

```java
@RequestParam(name = "sort", defaultValue = "newest") Optional<String> sort
```

However, if `defaultValue` is already provided, the argument always receives the default value when the parameter is absent or empty, so `Optional` usually adds little value. Choose one simple representation consistent with project conventions.

## 6. Combining @RequestParam with Various Data Types

Spring converts strings in requests into Java types based on the conversion service and converters registered in the application.

### Numeric and Boolean Types

```java
@GetMapping("/filter")
List<ProductDto> filter(
        @RequestParam(name = "minPrice", required = false) BigDecimal minPrice,
        @RequestParam(name = "available", defaultValue = "true") boolean available) {
    return productService.filter(minPrice, available);
}
```

Example request:

```text
GET /api/products/filter?minPrice=100000&available=false
```

If the client sends `minPrice=abc`, Spring cannot convert that string to `BigDecimal` and typically returns HTTP 400. `required=false` only allows omitting the parameter; it does not permit sending an improperly typed value.

### Enum

```java
public enum ProductStatus {
    ACTIVE,
    INACTIVE,
    OUT_OF_STOCK
}

@GetMapping
List<ProductDto> listByStatus(
        @RequestParam(name = "status", required = false) ProductStatus status) {
    return productService.findByStatus(status);
}
```

Request:

```text
GET /api/products?status=ACTIVE
```

Values not matching an enum constant can cause a conversion error and return 400. If you want to accept friendly codes or values different from enum names, register a `Converter<String, ProductStatus>` and document the exact public values in OpenAPI.

### Dates

For date types, explicitly publish the format that clients must send:

```java
@GetMapping("/by-date")
List<ProductDto> findByDate(
        @RequestParam(name = "date")
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate date) {
    return productService.findByDate(date);
}
```

Sample request:

```text
GET /api/products/by-date?date=2026-11-20
```

`@DateTimeFormat` guides Spring in converting the request parameter. To describe it more clearly in the documentation UI, add `@Parameter` with a description and example.

## 7. Describing Query Parameters in OpenAPI with springdoc

Springdoc reads `@RequestParam` on controllers to generate parameters in OpenAPI. For simple cases, the Spring annotation alone is enough for springdoc to infer name, location, type, and requiredness. You can add `@Parameter` to document purpose and examples for integrators:

```java
import io.swagger.v3.oas.annotations.Parameter;
import org.springframework.web.bind.annotation.RequestParam;

@GetMapping
Page<ProductDto> listProducts(
        @Parameter(
            description = "Page number, starting from 0",
            example = "0"
        )
        @RequestParam(name = "page", defaultValue = "0") int page,

        @Parameter(
            description = "Number of items per page",
            example = "20"
        )
        @RequestParam(name = "size", defaultValue = "20") int size) {
    return productService.findPage(page, size);
}
```

`@Parameter` supplements metadata for documentation; it does not replace `@RequestParam` and does not perform value binding itself. Similarly, `@Schema` describes types and constraints for documentation, while Spring and Bean Validation remain responsible for processing requests at runtime.

The generated OpenAPI specification may look like:

```yaml
paths:
  /api/products:
    get:
      parameters:
        - name: page
          in: query
          description: Page number, starting from 0
          required: false
          schema:
            type: integer
            default: 0
          example: 0
        - name: size
          in: query
          description: Number of items per page
          required: false
          schema:
            type: integer
            default: 20
          example: 20
```

This is an illustrative format. The exact structure depends on the OpenAPI version configured for springdoc and the bundled library version. Inspect the actual document at `/v3/api-docs` rather than assuming every annotation attribute is exported identically across all versions.

## 8. Distinguishing defaultValue from example

`defaultValue` and `example` have different meanings:

| Attribute | Meaning | Runtime Impact |
| --- | --- | --- |
| `@RequestParam(defaultValue = "20")` | Value the server uses when the parameter is missing or empty | Yes |
| `@Parameter(example = "20")` | Example displayed to documentation readers | No |
| `@Schema(defaultValue = "20")` | Default value published in the OpenAPI schema | Does not alter controller behavior itself |

For example, if the controller sets `defaultValue = "20"` while the documentation specifies an example of `50`, that is not necessarily wrong: `20` is the value the server uses when the client omits the parameter, while `50` is a sample request value. However, if the schema publishes a default that differs from server behavior, clients may misunderstand the contract.

## 9. Complete Example: Search and Pagination API

The example below combines optional parameters and default values:

```java
@RestController
@RequestMapping("/api/products")
class ProductController {

    private final ProductService productService;

    ProductController(ProductService productService) {
        this.productService = productService;
    }

    @GetMapping
    Page<ProductDto> search(
            @Parameter(description = "Search keyword", example = "keyboard")
            @RequestParam(name = "keyword", required = false)
            Optional<String> keyword,

            @Parameter(description = "Product status")
            @RequestParam(name = "status", required = false)
            Optional<ProductStatus> status,

            @Parameter(description = "Page number, starting from 0", example = "0")
            @RequestParam(name = "page", defaultValue = "0")
            int page,

            @Parameter(description = "Number of items per page", example = "20")
            @RequestParam(name = "size", defaultValue = "20")
            int size) {

        return productService.search(keyword, status, page, size);
    }
}
```

Full request:

```http
GET /api/products?keyword=keyboard&status=ACTIVE&page=0&size=20
```

Request using only default values:

```http
GET /api/products
```

In the second request, `keyword` and `status` are `Optional.empty()`, while `page` is `0` and `size` is `20`. The service implementation must clearly understand the meaning of `Optional.empty()` — for example, not filtering by keyword or status.

## 10. Common Errors and Resolutions

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Missing parameter returns 400 | `required` defaults to `true` | Set `required=false`, use `Optional`, or declare `defaultValue` if appropriate for the API |
| Optional parameter causes null error | Code invokes a method on a possibly `null` value | Check for null or use `Optional<T>` |
| Default value does not appear | `defaultValue` not declared or runtime config differs from documentation | Inspect annotations and generated schema |
| Numeric string fails to convert | Client sends a value incompatible with the Java type | Send the proper format or provide an appropriate converter |
| Swagger UI displays wrong required status | Conflicting annotation metadata or outdated documentation | Check `required`, `defaultValue`, and `/v3/api-docs` JSON |
| Incorrect parameter name in docs | `name` not explicitly declared or duplicate metadata exists | Use `@RequestParam(name = "...")` and check extra OpenAPI annotations |

Do not use `required=false` to mask data errors. An optional parameter still needs rules for handling absence, and any submitted value must still be converted and validated for the proper type.

## 11. Workflow for Designing @RequestParam

When adding a query parameter, decide in order:

1. Define the public parameter name and use `@RequestParam(name = "...")`.
2. Choose whether the parameter is required (`required=true`), optional (`required=false`/`Optional<T>`), or has a default (`defaultValue`).
3. Choose the right Java type; use a wrapper or `Optional` if the value may be absent.
4. Define conversion and validation rules for submitted values.
5. Use `@Parameter` or `@Schema` to add descriptions, examples, and published constraints.
6. Open `/v3/api-docs` or Swagger UI to confirm `in: query`, `required`, `schema`, `default`, and examples match the controller.
7. Test requests with the parameter, without the parameter, with an empty value, and with an invalid type.

By clearly designing the three states—required, optional, and default—clients can build valid requests right away, and Swagger UI accurately displays the API usage enforced by the controller.

## References

- [Spring Framework – `@RequestParam`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html)
- [Spring Framework – Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [OpenAPI Specification – Parameter Object](https://spec.openapis.org/oas/latest.html#parameter-object)
- [springdoc-openapi – Documentation](https://springdoc.org/)
