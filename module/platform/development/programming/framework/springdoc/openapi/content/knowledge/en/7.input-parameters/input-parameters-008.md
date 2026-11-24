# Value Lists, Repeated Parameters, and Passing Arrays

An API often needs to accept multiple values for a single parameter: a list of product codes, multiple order statuses, search tags, or several IDs to query. In Spring MVC, these values are commonly bound into a `List<T>`, a Java array, or a `MultiValueMap`. In OpenAPI, they are described using a schema with `type: array` and serialization rules specifying how clients send the list in URLs, headers, or cookies.

The critical point is that Java data types and HTTP transmission format are two separate concerns. `List<String>` tells the server to expect a collection of strings; `style` and `explode` in OpenAPI tell clients how to encode that collection into a request. If documentation and application binding disagree, Swagger UI, generated SDKs, and hand-written clients may send incompatible requests.

## 1. Distinguishing Single Parameters, Multiple Parameters, and Arrays

Suppose a product search endpoint needs to accept multiple tags (`tag`). Several transmission forms are common:

| Request | Meaning |
| --- | --- |
| `?tag=java` | A single `tag` value |
| `?tag=java&tag=spring` | Two values for the same parameter name `tag` |
| `?tag=java,spring` | A single value containing a comma-separated list |
| `?tag=java%20spring` | A single value containing a space-separated list |
| `?tag=java%7Cspring` | A single value containing a pipe-separated `\|` list |

These requests do not automatically mean the same thing. The server must know which delimiter is accepted, and OpenAPI must document that same rule. Unless special compatibility is required, the repeated form `?tag=java&tag=spring` is generally readable, extensible, and matches OpenAPI's default for query arrays.

An array in an OpenAPI schema is described using `type: array` and `items`:

```yaml
schema:
  type: array
  items:
    type: string
```

`items` describes the type of each element. For example, `type: array` with `items.type: integer` is a list of integers; `items.$ref` can reference a shared schema for each element.

## 2. Binding Query Arrays with Spring MVC

Spring MVC can bind multiple values of the same query parameter name into a `List<T>` or Java array via `@RequestParam`.

```java
@RestController
@RequestMapping("/api/products")
public class ProductController {

    @GetMapping
    public List<ProductResponse> search(
            @RequestParam(name = "tag", required = false) List<String> tags) {
        return productService.searchByTags(tags);
    }
}
```

Clients can call:

```text
GET /api/products?tag=java&tag=spring
```

Spring binds this to a list equivalent to `List.of("java", "spring")`. If using an array, you can declare `String[] tags` instead of `List<String> tags`:

```java
@GetMapping("/by-ids")
public List<ProductResponse> findByIds(
        @RequestParam(name = "id") Long[] ids) {
    return productService.findByIds(Arrays.asList(ids));
}
```

Corresponding request:

```text
GET /api/products/by-ids?id=10&id=20&id=30
```

Specify `name` explicitly in `@RequestParam` so HTTP parameter names do not rely on how the compiler preserves Java parameter names. `required = false` allows omitting the parameter; in that case, the application must clearly define how to handle `null` or an empty list. Distinguish between omitting `tag`, passing `tag` with an empty value (`?tag=`), and passing multiple values (`?tag=java&tag=spring`).

If you need to receive all query parameters without knowing names in advance, Spring supports `MultiValueMap<String, String>`:

```java
@GetMapping("/search/raw")
public SearchResponse searchRaw(
        @RequestParam MultiValueMap<String, String> parameters) {
    List<String> tags = parameters.get("tag");
    return productService.search(tags);
}
```

`MultiValueMap` preserves multiple values for the same key, making it suitable for generic search endpoints or dynamic filters. For public APIs with stable contracts, parameters explicitly declared via `@RequestParam` are easier to understand and document.

## 3. OpenAPI Defaults: form and explode

OpenAPI uses two attributes to describe parameter serialization:

- `style`: representation style and delimiter of values.
- `explode`: when enabled, each element of an array or each key/value pair of an object is expanded into a separate parameter according to `style` rules.

For query parameters, the defaults are `style: form` and `explode: true`. Therefore, an array `tag = ["java", "spring"]` is represented as repeated parameters:

```yaml
parameters:
  - name: tag
    in: query
    required: false
    description: List of tags to filter by
    style: form
    explode: true
    schema:
      type: array
      items:
        type: string
```

Sample request:

```text
GET /api/products?tag=java&tag=spring
```

Because this is OpenAPI's default for query parameters, `style` and `explode` can be omitted in documentation. However, declaring them explicitly helps readers see the transmission format when an API has varied parameter styles.

## 4. Passing an Array in a Single Comma-Separated Parameter

To send the entire list in a single query parameter, set `style: form` and `explode: false`:

```yaml
parameters:
  - name: tag
    in: query
    required: false
    description: List of tags, separated by commas
    style: form
    explode: false
    schema:
      type: array
      items:
        type: string
```

With `tag = ["java", "spring"]`, the request is serialized as:

```text
GET /api/products?tag=java,spring
```

Spring MVC can convert a query string into a collection via `ConversionService`; default converters typically support comma-separated strings. However, test with your specific Spring version and data type to guarantee binding behavior matches the contract. If elements themselves can contain commas, the delimiter creates ambiguity; specify percent-encoding rules or choose repeated parameters.

You can declare `style` and `explode` rules on Java parameters using `@Parameter`. When the Java type is `List<T>` or an array, springdoc can infer the array schema from the parameter type:

```java
@GetMapping
public List<ProductResponse> search(
        @Parameter(
            name = "tag",
            description = "List of tags, separated by commas",
            style = ParameterStyle.FORM,
            explode = Explode.FALSE
        )
        @RequestParam(name = "tag", required = false) List<String> tags) {
    return productService.searchByTags(tags);
}
```

To keep the default repeated form, use `ParameterStyle.FORM` and `Explode.TRUE`, or let springdoc infer the default. Do not declare a string schema for a `List<T>` if the goal is to publish an array.

OpenAPI imports used in the example:

```java
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.enums.Explode;
import io.swagger.v3.oas.annotations.enums.ParameterStyle;
```

## 5. Common Array Serialization Styles

OpenAPI supports several `style` options depending on parameter location. For query arrays, the main options are:

| `style` | `explode` | Example with `tag = ["java", "spring"]` | Location |
| --- | --- | --- | --- |
| `form` | `true` | `?tag=java&tag=spring` | Query; default |
| `form` | `false` | `?tag=java,spring` | Query |
| `spaceDelimited` | `false` | `?tag=java%20spring` | Query |
| `pipeDelimited` | `false` | `?tag=java%7Cspring` | Query |
| `simple` | `false` | `X-Tags: java,spring` or `/items/java,spring` | Header or path |

`spaceDelimited` and `pipeDelimited` only apply to arrays or objects in queries. For these styles, `explode` must be `false`. Delimiter characters may appear percent-encoded in URLs: spaces as `%20`, pipes `|` as `%7C`. Browsers, proxies, or client tools may display encoded or decoded URLs, though bytes on the wire must follow URI rules.

`simple` is the default style for path and header parameters. For arrays, `explode: false` joins elements with commas. Path parameter example:

```yaml
parameters:
  - name: ids
    in: path
    required: true
    style: simple
    explode: false
    schema:
      type: array
      items:
        type: integer
        format: int64
```

Corresponding URL:

```text
GET /api/orders/10,20,30
```

Not every delimiter is automatically converted into `List<T>` by Spring MVC. Comma-delimited style can use default conversion; pipe-delimited or space-delimited typically require custom parsers/converters. If you choose a non-default style, implement server-side parsing and test actual requests rather than only changing `style` in annotations.

## 6. Documenting Enum Arrays and List Constraints

A query array can hold enum values. Example API filtering orders by multiple statuses:

```java
public enum OrderStatus {
    NEW,
    CONFIRMED,
    SHIPPED,
    CANCELLED
}

@GetMapping("/api/orders")
public List<OrderResponse> findOrders(
        @RequestParam(name = "status", required = false)
        List<OrderStatus> statuses) {
    return orderService.findByStatuses(statuses);
}
```

Sample request:

```text
GET /api/orders?status=NEW&status=SHIPPED
```

Spring converts each value to the corresponding enum if names or converters match. springdoc can infer the allowed value list from the enum type. If you need control over how enums appear in documentation, use `@Schema` on the enum or align serialization configuration with how Jackson converts enums to JSON.

Array schemas can also publish element count bounds, uniqueness, or item types:

```yaml
schema:
  type: array
  minItems: 1
  maxItems: 10
  uniqueItems: true
  items:
    type: string
    enum: [NEW, CONFIRMED, SHIPPED, CANCELLED]
```

For collection properties in DTOs, use `@ArraySchema` to describe the element schema and array constraints:

```java
public class ProductFilter {

    @ArraySchema(
        schema = @Schema(type = "string"),
        minItems = 1,
        maxItems = 10,
        uniqueItems = true
    )
    private List<String> tags;
}
```

The corresponding imports are `io.swagger.v3.oas.annotations.media.ArraySchema` and `io.swagger.v3.oas.annotations.media.Schema`.

In DTOs, you can use Bean Validation such as `@Size` to limit element count, `@NotEmpty` to require at least one element, and element-type constraints to validate each value. Example:

```java
public List<ProductResponse> search(
        @RequestParam(name = "tag", required = false)
        @Size(max = 10) List<@NotBlank String> tags) {
    return productService.searchByTags(tags);
}
```

Validation annotations only take effect when validation is enabled and properly configured. OpenAPI documents constraints so clients know beforehand; the server must still enforce input checks.

## 7. Using `@ParameterObject` for Multi-Field Filters

When an endpoint has many related query parameters, you can group them into a POJO instead of declaring a long parameter list:

```java
public class ProductSearchCriteria {

    private List<String> tag;
    private List<ProductStatus> status;
    private Integer page;
    private Integer size;

    public List<String> getTag() { return tag; }
    public void setTag(List<String> tag) { this.tag = tag; }

    public List<ProductStatus> getStatus() { return status; }
    public void setStatus(List<ProductStatus> status) { this.status = status; }

    public Integer getPage() { return page; }
    public void setPage(Integer page) { this.page = page; }

    public Integer getSize() { return size; }
    public void setSize(Integer size) { this.size = size; }
}
```

Controller:

```java
import org.springdoc.core.annotations.ParameterObject;
import org.springframework.web.bind.annotation.ModelAttribute;

@GetMapping("/api/products/search")
public Page<ProductResponse> search(
        @ParameterObject @ModelAttribute ProductSearchCriteria criteria) {
    return productService.search(criteria);
}
```

springdoc can expand the parameter object's fields into separate query parameters. For example, a client sends `?tag=java&tag=spring&status=ACTIVE&page=0&size=20`. Fields need JavaBean-compliant getters for springdoc to recognize them. According to springdoc's FAQ, `@ParameterObject` supports Spring MVC request parameter POJOs but does not support nested parameter objects; for complex structures, document parameters explicitly or design simpler queries.

## 8. Distinguishing Arrays from Object Queries and deepObject

`deepObject` is meant for query objects with scalar properties, not general array transmission. Example of an object filter:

```yaml
parameters:
  - name: filter
    in: query
    style: deepObject
    explode: true
    schema:
      type: object
      properties:
        active:
          type: boolean
        region:
          type: string
```

Sample request:

```text
GET /api/products?filter[active]=true&filter[region]=north
```

OpenAPI defines `deepObject` representation for objects with scalar properties. Representation of array properties or nested objects is not clearly standardized in the specification. To send lists, use a separate array parameter such as `tag=java&tag=spring`, or use a JSON request body for complex filters.

## 9. Naming Conventions and Client Compatibility

When designing array parameters, maintain consistent naming. Use `tag` if each value represents a single tag in the filter; use `tagIds` if the API takes a list of IDs. Avoid switching between singular and plural inconsistently across endpoints, as code generators may produce inconsistent models or methods.

Practical guidelines:

- Choose the repeated form for query arrays unless compatibility dictates otherwise: `?id=1&id=2`.
- Only use commas, spaces, or `|` when the contract requires that serialization and the server supports it.
- Publish `minItems`, `maxItems`, `uniqueItems`, item type, and enums when constraints exist.
- Define behavior for missing values, empty values, duplicate elements, or exceeding item limits.
- Test percent-encoding for commas, `|`, `+`, `&`, `#`, square brackets, and Unicode characters.
- Preserve element order if order is meaningful; otherwise, clarify that the list is treated as a set.

In OpenAPI 2.0/Swagger 2.0, collection transmission was typically described via `collectionFormat` with values such as `csv`, `ssv`, `tsv`, `pipes`, and `multi`. OpenAPI 3 replaced that mechanism with the `style` and `explode` pair. When migrating documentation from Swagger 2 to OpenAPI 3, translate meanings accurately: `multi` typically corresponds to `style: form, explode: true`; `csv` typically corresponds to `style: form, explode: false`; `ssv` corresponds to `spaceDelimited`; `pipes` corresponds to `pipeDelimited`. `tsv` has no direct `style` equivalent in OpenAPI 3, so choose another convention or describe it with an appropriate content mechanism.

## 10. Verifying Documentation and Runtime Behavior

After the application starts, open `/v3/api-docs` or the configured endpoint and inspect the target operation. For each array parameter, verify:

1. `schema.type` is `array` and `items` describes the right element type.
2. `name` and `in` match the query, path, header, or cookie name accepted by the controller.
3. `style` and `explode` produce the request format supported by the server.
4. `required`, `minItems`, `maxItems`, `uniqueItems`, enums, and examples reflect actual validation.
5. Swagger UI sends the right request format when entering multiple values.
6. The server binds sent requests and handles missing, empty, duplicate, or invalid cases properly.

Example testing default query arrays with `curl`:

```bash
curl -i "http://localhost:8080/api/products?tag=java&tag=spring"
```

Example testing comma-delimited:

```bash
curl -i "http://localhost:8080/api/products?tag=java,spring"
```

For special characters, URI-encode them before sending. For example, `|` can be passed as `%7C`; do not assume every proxy or server supports unencoded characters just because a particular client accepts them.

An integration test suite should cover at least: one value, multiple repeated values, a delimiter-separated list if supported, omitted parameter, empty value, invalid element, and exceeding the item limit. If multiple serialization styles are supported, test each style as a separate case.

## 11. Common Issues and Fixes

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Server receives only the first element | Handler declares a scalar type like `String` instead of `List<String>` or an array | Use `List<T>`, `T[]`, or `MultiValueMap` |
| Swagger UI sends `tag=java&tag=spring` while API expects `tag=java,spring` | OpenAPI uses `form` with `explode=true` while server requires `explode=false` | Align `style`, `explode`, and Spring binding |
| Documentation shows string type instead of array | Java type or schema annotation does not reflect collection | Declare `List<T>`/array and inspect `schema.type` and `items` |
| `|` or spaces are not split | Default Spring conversion does not use that delimiter | Write a custom converter/parser and test percent-encoding |
| `@ParameterObject` does not expand fields | POJO lacks standard getters, or uses nested objects | Add getters/setters and use flat objects or document parameters manually |
| Empty value and omitted parameter behave identically | Conventions for `null`, empty string, and empty list undefined | Define contract explicitly and write tests for each case |
| Generated SDK sends malformed query string | `style`/`explode` mismatch server or client tool lacks full support | Inspect OpenAPI JSON and actual SDK requests |

## 12. Official References

- [OpenAPI Specification 3.1.2 — Parameter Object](https://spec.openapis.org/oas/v3.1.2.html#parameter-object) — schema, `style`, `explode`, `allowReserved`, and serialization rules.
- [OpenAPI Specification 3.1.2 — Style Examples](https://spec.openapis.org/oas/v3.1.2.html#style-examples) — serialization examples for primitives, arrays, and objects.
- [springdoc-openapi — FAQ](https://springdoc.org/faq.html) — `@ParameterObject`, POJO query fields, and nested object limitations.
- [Swagger Annotations — Parameter](https://javadoc.io/doc/io.swagger.core.v3/swagger-annotations/latest/io/swagger/v3/oas/annotations/Parameter.html) — `style`, `explode`, `schema`, and `array` attributes of `@Parameter`.

When value lists are documented accurately, clients can construct consistent query strings and Spring Boot can bind them into collections as expected. Treat `type: array`, `style`, and `explode` as part of the API contract; changing delimiters or parameter repetition affects existing clients and must be tested as a contract change.
