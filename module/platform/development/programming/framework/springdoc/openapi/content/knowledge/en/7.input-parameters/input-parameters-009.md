# `style`, `explode`, and Compatibility with Actual Binding Mechanics

OpenAPI describes not only the name and type of a parameter, but also how it is serialized in the URL, header, or cookie. The two attributes `style` and `explode` define how arrays and objects are formatted when a client sends a request. However, Spring MVC or WebFlux has its own binding mechanism to convert HTTP data into Java parameters.

Therefore, declaring `style` and `explode` in OpenAPI does not automatically change how Spring reads requests. The specification must accurately describe the format that the handler actually accepts. If documentation tells clients to send `tag=java&tag=spring` while code only reads a single value, or documentation specifies `filter[status]=ACTIVE` while the binder expects `status=ACTIVE`, the contract and runtime will diverge.

## 1. What Problems Do `style` and `explode` Solve?

A single string parameter is usually straightforward to represent:

```text
GET /products?status=ACTIVE
```

For arrays or objects, however, the same Java value can be serialized in multiple ways. For example, the list `java`, `spring` can be sent as:

```text
?tag=java&tag=spring
```

or:

```text
?tag=java,spring
```

Both represent the same data semantics but use different serialization formats.

- **`style`** determines the serialization rule: using commas, dots, semicolons, key/value pairs, square brackets, or other delimiters.
- **`explode`** determines whether an array or object is expanded into multiple parameters or combined into a single value according to the chosen style.

Example with the `tag` query parameter:

| `style` | `explode` | Array representation of `java`, `spring` |
|---|---:|---|
| `form` | `true` | `?tag=java&tag=spring` |
| `form` | `false` | `?tag=java,spring` |

`style` and `explode` are metadata of the OpenAPI Parameter Object. They help Swagger UI, SDK generators, and clients understand how to construct requests. The server must still perform binding that matches the documented format.

## 2. Default Values by Parameter Location

OpenAPI defines default styles based on the parameter's location (`in`):

| Location `in` | Default `style` | Default `explode` |
|---|---|---:|
| `query` | `form` | `true` |
| `path` | `simple` | `false` |
| `header` | `simple` | `false` |
| `cookie` | `form` | `true` |

If `style` or `explode` is omitted, consumers apply the defaults from the OpenAPI specification. Even so, for important array or object parameters, declare them explicitly to avoid discrepancies across tools or to guarantee generated clients use the exact expected format.

Not every style is valid in every location. Common choices:

| Style | Valid Locations | Brief Description |
|---|---|---|
| `form` | Query, cookie | Name/value form; can repeat parameter names. |
| `simple` | Path, header | Simple comma-separated format. |
| `matrix` | Path | `;name=value` format attached to path segments. |
| `label` | Path | Value prefixed with a dot `.`. |
| `spaceDelimited` | Query | Array using spaces as delimiters. |
| `pipeDelimited` | Query | Array using `|` characters as delimiters. |
| `deepObject` | Query | Object using `filter[property]=value` keys. |

`allowReserved` is a related query parameter attribute. Its default is `false`, meaning reserved characters are percent-encoded per URI rules. Enable `allowReserved` only when the contract genuinely requires preserving reserved characters in query values and both client and server have been tested with that encoding.

## 3. How Arrays and Objects Are Serialized

### 3.1. Query `form`: The Most Common Style

With `style: form`, `explode: true`, an array is represented by repeating the query parameter name:

```text
GET /products?tag=java&tag=spring&tag=api
```

When `explode: false`, elements are joined into a single comma-separated value:

```text
GET /products?tag=java,spring,api
```

For an object with `role=admin` and `active=true`:

```text
# style=form, explode=true
GET /users?role=admin&active=true

# style=form, explode=false
GET /users?filter=role,admin,active,true
```

In the `explode=true` form, the object's property names become query parameter names. If an endpoint has multiple objects with overlapping property names, design parameter names or request structures carefully to avoid ambiguity.

### 3.2. Query `spaceDelimited` and `pipeDelimited`

These two styles are mainly used for query arrays:

```text
# style=spaceDelimited, explode=false
GET /products?tag=java%20spring%20api

# style=pipeDelimited, explode=false
GET /products?tag=java|spring|api
```

Spaces in URLs are typically encoded as `%20`. The `|` character may also be percent-encoded depending on the client. Do not assume raw strings seen in logs always match what the client sent on the wire; inspect both the decoded URL and the value Spring actually receives.

### 3.3. Query `deepObject` for Objects

With `style: deepObject`, `explode: true`, object properties are represented using bracket notation:

```text
GET /products?filter[status]=ACTIVE&filter[minPrice]=100&filter[maxPrice]=500
```

This is a readable way for a single query parameter to represent an object with multiple properties. However, Spring does not automatically turn query parameters like `filter[status]` into a nested DTO merely because OpenAPI declares `deepObject`. You must choose a matching binding mechanism or read keys directly from the request parameter map.

### 3.4. Path `simple`, `label`, and `matrix`

For path parameters, `simple` is the default:

```text
# simple
/products/java,spring
```

`label` prefixes the value with a dot:

```text
# label
/products/.java,spring
```

`matrix` uses semicolons and parameter names:

```text
# matrix
/products/42;color=blue;size=large
```

For `simple` or `label`, arrays and objects have delimiter rules depending on `explode`. `matrix` can repeat property names when `explode=true`. These are OpenAPI serialization rules; Spring must receive the exact path string and convert it according to the parameter type or appropriate annotation.

Spring MVC provides `@MatrixVariable` to bind matrix variables. Example:

```java
@GetMapping("/products/{segment}")
ProductResponse findProduct(
        @PathVariable String segment,
        @MatrixVariable(pathVar = "segment", required = false)
        Map<String, String> filters) {
    return productService.find(segment, filters);
}
```

With matrix variables, confirm the application's path matching configuration allows semicolon content. Using only `@PathVariable String` causes Spring to read the path variable per path matching rules; it does not automatically parse all `matrix` structures into a map.

### 3.5. Header `simple` and Cookie `form`

Header parameters use `simple` by default. An array is typically represented using commas:

```http
X-Scopes: read,write,admin
```

Cookie parameters use `form` by default. However, cookies in HTTP requests follow their own structural rules; do not assume a cookie object can be bound by Spring into a DTO solely from `style=form`. For a single cookie, `@CookieValue` is the standard direct binding mechanism. Complex structures require explicit encoding conventions and custom conversion.

## 4. Declaring `style` and `explode` in springdoc

Springdoc uses Swagger annotations to add OpenAPI metadata. For a query parameter list, you can declare it as follows:

```java
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.enums.Explode;
import io.swagger.v3.oas.annotations.enums.ParameterIn;
import io.swagger.v3.oas.annotations.enums.ParameterStyle;

@GetMapping("/products")
List<ProductResponse> findProducts(
        @Parameter(
                name = "tag",
                in = ParameterIn.QUERY,
                description = "List of product tags",
                style = ParameterStyle.FORM,
                explode = Explode.TRUE
        )
        @RequestParam(name = "tag", required = false)
        List<String> tags) {
    return productService.findByTags(tags);
}
```

The metadata above documents the query array using repeated parameter names:

```text
GET /products?tag=java&tag=spring
```

Spring MVC can bind multiple values with the same name into `List<String>`. With certain data types and default converters, a comma-separated string can also be converted into a collection. If you want to publish a single canonical format, test real requests and declare `style`/`explode` to match that format.

For the comma-separated form, you can declare:

```java
@Parameter(
        name = "tag",
        in = ParameterIn.QUERY,
        style = ParameterStyle.FORM,
        explode = Explode.FALSE
)
@RequestParam(name = "tag", required = false)
List<String> tags
```

The resulting description represents:

```text
GET /products?tag=java,spring
```

OpenAPI annotations only describe how clients should serialize the parameter. If Spring binding does not accept that exact form, update the parameter type, converter, or parsing logic so the contract is properly enforced.

## 5. Binding Query Arrays in Spring MVC

### 5.1. `@RequestParam List<T>` with Repeated Names

This is the natural form for a `form` query parameter with `explode=true`:

```java
@GetMapping("/products")
List<ProductResponse> findProducts(
        @RequestParam(name = "tag", required = false)
        List<String> tags) {
    return productService.findByTags(tags);
}
```

Request:

```text
GET /products?tag=java&tag=spring
```

Spring MVC collects values of the same parameter name and converts them into `List<String>`. For `Long`, `UUID`, enums, or custom types, conversion depends on built-in converters or converters registered by the application.

### 5.2. Using `MultiValueMap` When Preserving All Values

If an endpoint needs to read multiple values across multiple parameters while preserving lists, use `MultiValueMap`:

```java
@GetMapping("/products")
List<ProductResponse> findProducts(
        @RequestParam MultiValueMap<String, String> params) {
    List<String> tags = params.get("tag");
    return productService.findByTags(tags);
}
```

`MultiValueMap` retains multiple values per key, fitting `?tag=java&tag=spring`. A plain `Map<String, String>` only works when each key expects a single value; if the contract allows repeated keys, choose a type that holds multiple values.

### 5.3. Comma-Separated Values and Converters

Spring has mechanisms to convert strings into collections. In common cases, a value like `tag=java,spring` can be split into two elements when bound to `List<String>`. However, this behavior depends on the target type, converters, and conversion configuration.

If exact control is required, accept a `String` and parse it according to API rules:

```java
@GetMapping("/products")
List<ProductResponse> findProducts(
        @RequestParam(name = "tag", required = false) String tagValue) {
    List<String> tags = tagValue == null || tagValue.isBlank()
            ? List.of()
            : Arrays.stream(tagValue.split(",", -1))
                    .map(String::trim)
                    .toList();
    return productService.findByTags(tags);
}
```

If elements can contain commas, a simple comma-separated convention cannot distinguish data commas from delimiter commas. In that case, use repeated parameters, an explicit encoding, or an appropriate request body.

## 6. Binding Query Objects in Spring

### 6.1. `@ModelAttribute` and `@ParameterObject`

For search filters with simple fields, a query DTO is usually easy to use and test:

```java
public class ProductFilter {
    private String status;
    private BigDecimal minPrice;
    private BigDecimal maxPrice;

    // getters and setters
}
```

Controller:

```java
@GetMapping("/products")
List<ProductResponse> search(
        @ParameterObject @ModelAttribute ProductFilter filter) {
    return productService.search(filter);
}
```

Spring MVC binds query parameters to DTO properties by property name:

```text
GET /products?status=ACTIVE&minPrice=100&maxPrice=500
```

`@ParameterObject` tells springdoc to decompose the object's properties into query parameters in OpenAPI. This annotation is for documentation; `@ModelAttribute` is the mechanism Spring uses to bind request parameters to the object. Both annotations have distinct roles and do not replace each other.

### 6.2. `deepObject` and Bracketed Keys

If the contract requires this exact format:

```text
GET /products?filter[status]=ACTIVE&filter[minPrice]=100
```

Spring MVC can read all query parameters via `MultiValueMap`, and the application parses `filter[...]` keys manually:

```java
@GetMapping("/products")
List<ProductResponse> search(
        @RequestParam MultiValueMap<String, String> params) {
    String status = params.getFirst("filter[status]");
    String minPriceValue = params.getFirst("filter[minPrice]");

    ProductFilter filter = new ProductFilter();
    filter.setStatus(status);
    if (minPriceValue != null) {
        filter.setMinPrice(new BigDecimal(minPriceValue));
    }
    return productService.search(filter);
}
```

OpenAPI metadata can document the `filter` parameter with `deepObject`:

```java
@Parameter(
        name = "filter",
        in = ParameterIn.QUERY,
        style = ParameterStyle.DEEPOBJECT,
        explode = Explode.TRUE,
        schema = @Schema(implementation = ProductFilter.class)
)
```

Place this metadata on the corresponding parameter or operation according to project structure. Confirm that the springdoc and Swagger Annotations versions in use support the desired schema representation.

Do not confuse `deepObject` with a flat `@ModelAttribute` DTO. `@ModelAttribute ProductFilter` typically binds keys like `status` and `minPrice`, whereas `deepObject` uses prefixed bracketed keys like `filter[status]`. To use `deepObject`, code must read those exact keys or configure a custom binder/converter.

## 7. Binding Path, Header, and Cookie Parameters

| Location | Common Spring Mechanism | Points to Verify |
|---|---|---|
| Path | `@PathVariable` | Does the Java type have a matching converter; does array delimiter match `style`? |
| Matrix path | `@MatrixVariable` | Does path matching preserve semicolon content and map to the right path segment? |
| Header | `@RequestHeader` | Are single, repeated, or comma-separated header values converted as expected? |
| Cookie | `@CookieValue` | Is the cookie bound by name; do complex objects have dedicated encoding and parsing? |

Header example:

```java
@GetMapping("/reports")
List<ReportResponse> reports(
        @RequestHeader(name = "X-Scopes", required = false)
        List<String> scopes) {
    return reportService.findByScopes(scopes);
}
```

If OpenAPI specifies `style=simple` and comma-separated header arrays, test requests with `X-Scopes: read,write`. If proxies or clients send multiple headers with the same name, verify how the servlet container and Spring merge or read values.

Single cookie example:

```java
@GetMapping("/preferences")
PreferencesResponse preferences(
        @CookieValue(name = "locale", required = false) String locale) {
    return preferenceService.get(locale);
}
```

Here the `locale` cookie is a single string. Do not document it as an exploded object merely because OpenAPI supports `form` for cookies; `@CookieValue` does not automatically bind a group of cookies into a DTO.

## 8. Inspecting Generated OpenAPI Metadata

After declaring `@Parameter`, open `/v3/api-docs` or the configured documentation endpoint and inspect the operation's parameters. For a repeated query array, the document should look similar to:

```yaml
parameters:
  - name: tag
    in: query
    style: form
    explode: true
    schema:
      type: array
      items:
        type: string
```

If `style` and `explode` are omitted, consumers apply OpenAPI defaults based on location and style. If the document shows unexpected values, inspect annotations, Java parameter types, and the Swagger Annotations version used by springdoc.

Do not inspect only source code annotations. Always read the actual generated JSON document because springdoc infers metadata from mappings, Java types, annotations, and various settings.

## 9. Testing Compatibility Between OpenAPI and Spring Binding

A good test sends requests matching the exact serialization published by OpenAPI, then verifies that the handler receives the expected values.

Example with MockMvc and repeated query parameters:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ProductParameterBindingTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void bindsRepeatedTagParameters() throws Exception {
        mockMvc.perform(get("/products")
                        .param("tag", "java", "spring"))
                .andExpect(status().isOk());
    }
}
```

If the endpoint uses comma-separated values, add a separate test with `.param("tag", "java,spring")`. If using `deepObject`, send the exact keys `filter[status]` and `filter[minPrice]` and verify the object/service receives the right data. Checking status `200` alone is insufficient when verifying elements; assert on the response or use a mock service to verify bound arguments.

An applicable test matrix:

| OpenAPI Format | Sample Request | Spring Type/Annotation | What to Verify |
|---|---|---|---|
| `form`, `explode=true` | `?tag=a&tag=b` | `@RequestParam List<String>` | List contains both elements. |
| `form`, `explode=false` | `?tag=a,b` | `String`, `List<String>`, or converter | Comma-splitting rules are consistent. |
| `deepObject`, `explode=true` | `?filter[status]=ACTIVE` | `MultiValueMap` or custom binder | Prefixed bracketed keys are parsed properly. |
| `simple` path | `/items/a,b` | `@PathVariable` | Converter receives right value/collection. |
| `simple` header | `X-Scopes: a,b` | `@RequestHeader` | Header is split and converted properly. |

## 10. Common Pitfalls

- **Declaring `explode=true` and expecting Spring to change binding automatically**: annotations only describe OpenAPI; the handler must accept that exact format.
- **Documenting repeated queries while using a single `String`**: switch to `List`, `MultiValueMap`, or handle lists explicitly.
- **Documenting comma-separated values when parsers treat commas as data**: define delimiters clearly and test elements containing special characters.
- **Using `@ParameterObject` expecting `deepObject`**: `@ParameterObject` mainly flattens query properties; `filter[field]` requires matching binding.
- **Using `matrix` style while reading only `@PathVariable`**: check `@MatrixVariable` and path matching configuration.
- **Enabling `allowReserved` without checking URL encoding**: reserved characters like `&` or `=` can break query parsing.
- **Relying solely on Swagger UI Try it out as proof**: test real runtime requests directly and inspect generated OpenAPI JSON.
- **Assuming all generators serialize identically**: inspect requests produced by real SDKs/clients, especially for objects, arrays, or characters needing percent-encoding.

## 11. Workflow for Choosing style/explode for a Parameter

1. **Identify parameter location**: query, path, header, or cookie.
2. **Identify data type**: scalar, array, or object; specify name, item type, and value rules.
3. **Choose client transmission format**: repeated keys, comma-separated, matrix, label, deepObject, or another OpenAPI-supported style.
4. **Declare `style` and `explode`**: rely on defaults when suitable; declare explicitly when requiring a specific serialization.
5. **Choose Spring binding mechanism**: `@RequestParam`, `MultiValueMap`, `@ModelAttribute`, `@PathVariable`, `@MatrixVariable`, `@RequestHeader`, or `@CookieValue`.
6. **Test real requests**: confirm values bind properly with published sample requests.
7. **Review `/v3/api-docs`**: ensure documentation shows expected `style`/`explode` and schema.
8. **Verify consumers**: test Swagger UI or SDK generators to confirm clients produce valid requests.

## 12. Review Checklist

- [ ] Location `in` and `style` comply with the OpenAPI Specification.
- [ ] Default values of `style` and `explode` are properly understood.
- [ ] Arrays/objects have clear illustrative request examples.
- [ ] `explode` accurately reflects repeated keys vs. a combined value.
- [ ] `allowReserved` is enabled only when needed and tested with URL encoding.
- [ ] Spring binding accepts the published request format.
- [ ] `@ParameterObject` is not confused with `deepObject`.
- [ ] Matrix variables have matching path matching configuration.
- [ ] Inspected `/v3/api-docs` after configuring annotations.
- [ ] Integration tests cover all important request formats.

## 13. References

- [OpenAPI Specification 3.1.2 – Parameter Object](https://spec.openapis.org/oas/v3.1.2.html#parameter-object)
- [OpenAPI Specification 3.0.4 – Parameter Object](https://spec.openapis.org/oas/v3.0.4.html#parameter-object)
- [OpenAPI Initiative – Parameter serialization](https://learn.openapis.org/specification/parameters.html)
- [Spring Framework – `@RequestParam`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html)
- [Spring Framework – `@ModelAttribute`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework – Matrix Variables](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/matrix-variables.html)
- [springdoc-openapi FAQ – Parameter objects](https://springdoc.org/faq.html)

`style` and `explode` describe how clients serialize parameters under the OpenAPI contract. For the API to work reliably, cross-check that metadata against Spring's actual binding mechanics and converters, then verify with request integration tests. Good documentation accurately describes the data the server receives, not merely valid syntax in Swagger UI.
