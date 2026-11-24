# Default Values vs. Illustrative Examples

In OpenAPI documentation, **default values** (`default`) and **illustrative examples** (`example`) both help readers understand the data, yet they mean different things. A default value describes the value assumed or used when the client does not provide data. An illustrative example merely provides a valid sample value so readers can picture how to send or receive data.

Springdoc can include both types of metadata in the specification from OpenAPI annotations. However, documentation annotations do not automatically alter controller behavior. If the API needs to apply a value when a parameter or field is omitted, Spring code must implement that behavior—for instance via `@RequestParam(defaultValue = ...)`, `@RequestHeader(defaultValue = ...)`, or DTO initialization logic.

## 1. Distinguishing `default` and `example` in OpenAPI

Suppose a pagination API has a `size` parameter with a default value of `20`. Clients often send `size=10` in a specific request. These two values serve different purposes:

- `default: 20` states the default value of the parameter when the client provides no value.
- `example: 10` illustrates a concrete value that the client might send.

In OpenAPI, a schema can express both:

```yaml
name: size
in: query
required: false
schema:
  type: integer
  default: 20
  example: 10
```

`default` and `example` do not replace each other. If only `example: 10` is declared, clients cannot infer that the server will use `10` when the parameter is absent. If `default: 20` is declared, the documentation clearly states the default is `20`, while the example `10` shows that the client can choose a different value.

| Criterion | `default` | `example` |
| --- | --- | --- |
| Purpose | Describes the default value when data is omitted | Illustrates a sample value |
| Contract significance | May affect how clients understand behavior when data is not passed | Helps understand formatting and usage |
| Changes server behavior automatically? | No | No |
| May differ from actual sent values? | Yes, if overridden by client | Yes, because it is just an example |
| Location in OpenAPI | `default` in Schema Object | `example` or `examples` on schema/parameter/media type depending on context |

OpenAPI describes the meaning of default values in the contract. The application must still implement the same behavior so documentation does not mislead.

## 2. Declaring default and example with `@Schema`

`@Schema` belongs to `io.swagger.v3.oas.annotations.media`. You can place the annotation on fields, properties, or record components to describe schemas. The `defaultValue` attribute represents the default value; `example` provides a sample value.

```java
import io.swagger.v3.oas.annotations.media.Schema;

public record SearchRequest(
    @Schema(
        description = "Page number starting from 0",
        defaultValue = "0",
        example = "2"
    )
    Integer page,

    @Schema(
        description = "Number of records per page",
        defaultValue = "20",
        example = "10"
    )
    Integer size
) {}
```

In this example, the schema states that `page` defaults to `0` and `size` defaults to `20`; the request example illustrates a client requesting page `2` with `10` records. The strings `"0"` and `"20"` are how values are passed to annotation attributes; Springdoc generates schemas according to the Java data types and should be verified in the output document.

`@Schema(defaultValue = ...)` only describes OpenAPI metadata. It does not initialize Java fields, fix `null` values, or replace business logic. If the controller receives JSON and needs to apply defaults, implement that inside the DTO or service.

## 3. Applying Actual Default Values for JSON DTOs

For JSON request bodies, clients can omit optional fields. If the application wants to use default values, the DTO needs corresponding logic.

Example using a class with field initializers:

```java
import io.swagger.v3.oas.annotations.media.Schema;

public class SearchRequest {

    @Schema(
        description = "Page number starting from 0",
        defaultValue = "0",
        example = "2"
    )
    private Integer page = 0;

    @Schema(
        description = "Number of records per page",
        defaultValue = "20",
        example = "10"
    )
    private Integer size = 20;

    public Integer getPage() {
        return page;
    }

    public void setPage(Integer page) {
        this.page = page;
    }

    public Integer getSize() {
        return size;
    }

    public void setSize(Integer size) {
        this.size = size;
    }
}
```

When Jackson creates the object via its default constructor, field initializers run. If JSON omits `page` or `size`, the initial values can be retained. If JSON explicitly sends `"size": null`, the setter may overwrite `20` with `null`. Therefore, decide separately how to handle omitted fields versus fields explicitly sent with `null`.

Another approach is normalizing values in a record's compact constructor or in the service:

```java
public record SearchRequest(Integer page, Integer size) {
    public SearchRequest {
        page = page == null ? 0 : page;
        size = size == null ? 20 : size;
    }
}
```

With this approach, both omitted fields and fields sent as `null` receive default values. Only choose this approach if the business contract treats those two cases as equivalent. If explicit `null` must be rejected, use validation or handle field presence appropriately.

Do not rely on implicit defaults of primitive types such as `int` being `0` or `boolean` being `false` unless that is the business rule. Use wrapper types such as `Integer` or `Boolean` when you need to distinguish unprovided data from a valid value of `0` or `false`.

## 4. Defaults for Query Parameters Using `@RequestParam`

For query parameters, Spring MVC provides the `defaultValue` attribute directly on `@RequestParam`. This attribute both creates a runtime fallback and makes the parameter optional.

```java
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Schema;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@GetMapping("/api/products")
public String listProducts(
        @Parameter(
            description = "Zero-based page",
            example = "2",
            schema = @Schema(defaultValue = "0")
        )
        @RequestParam(name = "page", defaultValue = "0") int page,

        @Parameter(
            description = "Number of products per page",
            example = "10",
            schema = @Schema(defaultValue = "20")
        )
        @RequestParam(name = "size", defaultValue = "20") int size) {

    return "page=" + page + ", size=" + size;
}
```

When a client calls `/api/products` without query parameters, Spring passes `page = 0` and `size = 20` into the method. If the client sends `?page=2&size=10`, the values passed are `2` and `10`.

`@Parameter(example = ...)` provides a sample value at the parameter level; `@Schema(defaultValue = ...)` documents the schema's default. `@RequestParam(defaultValue = ...)` controls runtime behavior. Springdoc can automatically infer part of the metadata from Spring annotations, but check `/v3/api-docs` to be sure defaults and examples are represented as intended.

### Declaring default only in documentation

If using `@RequestParam(required = false)` without setting `defaultValue`, adding `@Schema(defaultValue = "20")` does not make Spring automatically pass `20` into the method:

```java
@GetMapping("/api/products")
public String listProducts(
        @Parameter(
            description = "Number of products per page",
            example = "10",
            schema = @Schema(defaultValue = "20")
        )
        @RequestParam(name = "size", required = false) Integer size) {

    int effectiveSize = size == null ? 20 : size;
    return "size=" + effectiveSize;
}
```

Here, code explicitly applies `20` when `size` is `null`. If you remove `effectiveSize` and use `size` directly, the parameter can still be `null` even though documentation lists `default: 20`. This is why metadata must be distinguished from actual behavior.

## 5. Defaults for Headers and Cookies

Spring MVC also supports `defaultValue` with `@RequestHeader` and `@CookieValue`. The rule is similar to query parameters: the value is used when the header/cookie is absent or empty, and the parameter becomes optional.

```java
@GetMapping("/api/preferences")
public String getPreferences(
        @RequestHeader(name = "Accept-Language", defaultValue = "vi")
        String language,

        @CookieValue(name = "theme", defaultValue = "light")
        String theme) {

    return "language=" + language + ", theme=" + theme;
}
```

To show metadata clearly in OpenAPI, you can add `@Parameter`:

```java
@Parameter(
    description = "Client's preferred language",
    example = "en",
    schema = @Schema(defaultValue = "vi")
)
@RequestHeader(name = "Accept-Language", defaultValue = "vi")
String language
```

Similarly, the `theme` cookie can be described with `defaultValue = "light"` and example `"dark"`. Check OpenAPI to confirm parameters have `in: header` or `in: cookie`, `required: false`, and an appropriate default.

Do not use header/cookie defaults to replace authentication mechanisms. For instance, never put a default token in `Authorization`; credentials must be handled via security schemes and runtime security.

## 6. `@ExampleObject` for Request Bodies

`@ExampleObject` is well suited when you need to provide one or more complete sample payloads for a request body. Example:

```java
@Operation(
    summary = "Search products",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = SearchRequest.class),
            examples = {
                @ExampleObject(
                    name = "DefaultPage",
                    summary = "Client specifies first page and default size",
                    value = "{\"page\":0,\"size\":20}"
                ),
                @ExampleObject(
                    name = "CustomPage",
                    summary = "Client requests page 2 with 10 records",
                    value = "{\"page\":2,\"size\":10}"
                )
            }
        )
    )
)
```

These examples show concrete payloads. They do not determine DTO fallback values. To tell readers that `size` defaults to `20` when omitted, document `defaultValue` on the schema and ensure code enforces the same rule.

An example may match the default, though it does not have to. Examples should usually illustrate a useful use case; defaults should reflect the value actually applied when data is omitted.

## 7. Defaults in Response Schemas

`default` can also appear in response schemas, but must be interpreted correctly. It describes the schema's default value if a value is not provided; it does not mean the server will automatically insert that value into the JSON response.

Schema example:

```java
public record ProductSettings(
    @Schema(
        description = "Display theme",
        defaultValue = "light",
        example = "dark"
    )
    String theme
) {}
```

If the API really always returns `theme`, the service must construct the response with the chosen value. If the server omits the field, documentation cannot substitute for serializing that value. When a field may be absent or `null`, clearly describe optionality/nullability according to the OpenAPI version and application response policy.

For responses, examples should reflect an observable response. Do not set a hypothetical default that leads clients to think the server always returns that value when the field can actually be missing.

## 8. Choosing Sensible Default Values

Defaults are part of the API contract and can affect business outcomes. Before choosing a default, consider:

1. **Is the value safe?** For example, `page = 0` or `size = 20` is easy to understand; defaulting to an overly broad access filter can introduce risk.
2. **Is it within schema bounds?** `default` must fit the data type, `minimum`, `maximum`, `enum`, `pattern`, and other constraints.
3. **Is it consistent between runtime and documentation?** `@RequestParam(defaultValue = "20")`, service logic, and `@Schema(defaultValue = "20")` should not contradict each other.
4. **Do missing and null need to be distinguished?** JSON can omit a property or send explicit `null`; the application must decide whether both cases mean the same thing.
5. **Will changing the default affect clients?** Clients omitting the parameter may receive different results when a default changes, so treat this as an API behavior change.

Example where the default must lie within the valid range:

```java
@Schema(
    description = "Number of records per page, from 1 to 100",
    defaultValue = "20",
    example = "50",
    minimum = "1",
    maximum = "100"
)
Integer size
```

The default value `20` is valid; the example `50` is also within bounds. A default of `200` would contradict `maximum = 100` and mislead clients.

## 9. Inspecting Defaults and Examples in Generated Documentation

After launching the application, open `/v3/api-docs` or `/v3/api-docs.yaml`. Locate the parameter or schema to inspect. A condensed result might look like:

```yaml
parameters:
  - name: size
    in: query
    required: false
    description: Number of products per page
    schema:
      type: integer
      default: 20
      example: 10
```

For request bodies, locate the schema in `components.schemas`:

```yaml
SearchRequest:
  type: object
  properties:
    page:
      type: integer
      default: 0
      example: 2
    size:
      type: integer
      default: 20
      example: 10
```

This is an illustrative structure. The placement of `example` can be on parameter, schema, or media type depending on annotations and library versions. What matters is confirming that defaults and examples appear in the right context, data type, and expected values.

In Swagger UI, observe the values initially shown for parameters or request bodies. The UI may use example/default to prefill payloads depending on version; do not rely on UI prefilling to conclude the server enforces defaults. Send an actual request without the parameter/field and verify runtime results.

## 10. Testing Present, Missing, and Null Cases

To verify defaults, test different cases. For query parameters:

```bash
# Omit size: server applies default 20
curl "http://localhost:8080/api/products"

# Send non-default size: server uses 10
curl "http://localhost:8080/api/products?size=10"
```

For JSON bodies:

```json
{
  "page": 2,
  "size": 10
}
```

Compare with a payload omitting `size`:

```json
{
  "page": 2
}
```

And a payload sending explicit `null`:

```json
{
  "page": 2,
  "size": null
}
```

The result of the last two payloads depends on how the DTO/Jackson and service logic are implemented. Clearly define the contract: does omitting the field use the default, is `null` accepted, or must `null` return a validation error? Do not infer that behavior solely from `@Schema(defaultValue = ...)`.

## 11. Common Pitfalls

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Swagger UI displays example, but server does not use it | Confusing `example` with runtime default | Add default logic in Spring or use `defaultValue` on Spring annotations |
| Docs show default, but method receives `null` | Declared only `@Schema(defaultValue = ...)` | Apply fallback in controller/service or Spring annotation |
| Query parameter is not marked optional | Missing `defaultValue` or mismatched `required` metadata | Check `@RequestParam` and OpenAPI `required` |
| Default does not appear in OpenAPI | Annotation placed in wrong spot or Springdoc did not infer runtime value | Declare `@Schema(defaultValue = ...)` explicitly and check JSON |
| Default is invalid against schema | Default falls outside minimum/maximum or not in enum | Align default with constraints |
| JSON field becomes `null` despite initializer | JSON sends `null` and Jackson overwrites the field | Define null behavior separately or normalize data |
| `0`/`false` is mistaken for missing | Using primitives without distinguishing implicit defaults | Use wrappers when unprovided state must be distinguished |
| Clients rely on old default | Team changed default without assessing impact | Manage default changes like API contract changes |

## 12. Checklist for Describing Defaults and Examples

- [ ] `defaultValue` is used only for values actually applied when data is omitted.
- [ ] `example` is a useful sample value valid against the schema.
- [ ] `@Schema(defaultValue = ...)` and runtime logic do not contradict each other.
- [ ] `@RequestParam`, `@RequestHeader`, or `@CookieValue` uses `defaultValue` when Spring needs to apply fallbacks directly.
- [ ] DTO has initialization or normalization logic when request body needs defaults for omitted fields.
- [ ] Handling of missing fields vs. explicit `null` fields is defined.
- [ ] Default lies within the schema's data type bounds and constraints.
- [ ] Examples contain no sensitive data and are not mistaken for fallback values.
- [ ] Verified `default` and `example` in `/v3/api-docs`.
- [ ] Tested requests omitting the parameter/field, sending non-default values, and sending `null` where applicable.

`default` describes the behavior expected when a client omits data; `example` illustrates a concrete value. Springdoc publishes both in OpenAPI, while Spring MVC and DTO/service code are responsible for applying actual values. Keeping these three parts consistent helps clients understand the contract accurately and avoids relying on an example value as if it were a runtime rule.
