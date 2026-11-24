# Setting Default Values vs. Enforcing API Behavior

When reading documentation in Swagger UI, clients may see a parameter pre-populated with a value, such as `pageSize = 20` or `includeArchived = false`. That value helps users understand how to call the endpoint and can be used by tools as a hint when testing requests. However, declaring `default` in OpenAPI does not automatically cause Spring Boot to apply that value when a client omits the field.

For the API to genuinely use a default value, the application must implement runtime behavior via Spring MVC binding, DTO initialization, Jackson, or business logic. To restrict valid values, corresponding validation or processing rules are required. With springdoc-openapi, keep `default`/`example` metadata in documentation synchronized with runtime behavior so clients are not misled.

## 1. Three layers to distinguish

Default values can appear at three distinct layers:

| Layer | Example | Effect |
|---|---|---|
| OpenAPI contract | `schema.default: 20` | Describes the default value of data according to the contract |
| Swagger UI | Displays `20` in the try-it-out form | Suggests or pre-fills a value for user convenience |
| API runtime | `@RequestParam(defaultValue = "20")` | Spring actually uses `20` when the request omits the parameter per binding rules |

The three layers are related but do not stay synchronized automatically in every scenario. For instance, if OpenAPI declares `default: 20` while the controller accepts `Integer pageSize` without a runtime default, a request omitting `pageSize` can leave the Java value as `null`. Swagger UI displaying `20` does not change how Spring processes requests sent from curl, Postman, or another application.

## 2. Distinguishing `default`, `example`, `required`, and `enum`

OpenAPI attributes answer different questions:

| Attribute | Question | Example |
|---|---|---|
| `default` | What default value is documented when no value is provided? | `default: 20` |
| `example` | What illustrative value can be used? | `example: 20` |
| `examples` | What named examples are provided? | `basic`, `largePage` |
| `required` | Is the parameter or property required to be present? | `required: true` |
| `enum` | What values are permitted by the schema? | `enum: [small, medium, large]` |
| `minimum`, `maximum` | Within what range is the numeric value constrained? | `minimum: 1`, `maximum: 100` |

`default` does not make a parameter optional, does not force clients to send that value, and does not prevent clients from choosing other values. If a parameter is both required and has a default, re-examine the contract semantics: the client must supply a value, so a default may not help when the parameter is missing.

Schema example:

```yaml
type: object
properties:
  pageSize:
    type: integer
    default: 20
    example: 20
    minimum: 1
    maximum: 100
```

The schema states that `pageSize` has a documented default of 20, an example of 20, and valid values constrained between 1 and 100. It does not execute logic assigning 20 inside the application.

## 3. `default` in OpenAPI is contract metadata

In a Schema Object, `default` describes the value assumed when data is omitted. This is metadata for human readers and schema consumers. OpenAPI does not require servers to auto-populate values into request bodies or query parameters.

Parameter example:

```yaml
paths:
  /api/orders:
    get:
      parameters:
        - name: pageSize
          in: query
          required: false
          description: Maximum number of orders returned per page
          schema:
            type: integer
            default: 20
            minimum: 1
            maximum: 100
```

Clients can understand that if `pageSize` is omitted, the assumed value under the contract is 20. Yet for the server to actually apply 20, the controller or processing layer must implement the corresponding logic.

In both OpenAPI 3.0 and 3.1, `default` remains descriptive information in the schema. Upgrading the OpenAPI version does not turn `default` into a server-side execution mechanism.

## 4. How Swagger UI uses default and example

Swagger UI reads the OpenAPI document to render parameters, schemas, and examples. Depending on the data type, Swagger UI version, and how the schema is declared, `default` or `example` values may be shown as hints in the UI or used when constructing test request inputs.

Users can still edit values before clicking **Try it out** and sending a request. Once sent, the server receives only the data actually present in the HTTP request. The UI cannot impose default values on other clients.

Example parameter with both default and example:

```yaml
- name: pageSize
  in: query
  required: false
  schema:
    type: integer
    default: 20
    minimum: 1
    maximum: 100
  example: 20
```

`default` describes the schema's default value; `example` provides an illustrative value for the parameter. If the example represents a specific scenario, `examples` can be used to name and describe each case. Do not treat an example as if it were an enforced runtime value.

## 5. Declaring default/example with `@Schema` and `@Parameter`

Springdoc can read metadata from Swagger Annotations. For a query parameter, you can explicitly declare description, example, and schema default:

```java
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@GetMapping("/api/orders")
OrderPage listOrders(
        @Parameter(
            description = "Maximum number of orders per page",
            example = "20",
            schema = @Schema(
                defaultValue = "20",
                minimum = "1",
                maximum = "100"
            )
        )
        @RequestParam(required = false) @Min(1) @Max(100) Integer pageSize) {
    // Runtime handling is covered in the next section.
    return orderService.list(pageSize);
}
```

`@Schema(defaultValue = "20")` adds default metadata to the generated schema. `@Parameter(example = "20")` describes an illustrative value for the parameter. These annotations do not assign a value to `pageSize` automatically.

If your springdoc version already infers defaults from Spring MVC annotations, inspect `/v3/api-docs` before declaring redundant metadata. When declaring them explicitly with Swagger Annotations, keep `@Schema` values synchronized with runtime values.

## 6. Enforcing runtime defaults for query parameters in Spring MVC

To make Spring actually use a value when a query parameter is missing, use `@RequestParam(defaultValue = "...")`:

```java
@GetMapping("/api/orders")
OrderPage listOrders(
        @RequestParam(defaultValue = "20")
        @Min(1) @Max(100) int pageSize) {
    return orderService.list(pageSize);
}
```

When a client calls:

```http
GET /api/orders
```

Spring MVC binds `pageSize` to 20. When a client calls:

```http
GET /api/orders?pageSize=50
```

the bound value is 50. With `@RequestParam`, declaring `defaultValue` also makes the parameter non-required under Spring's binding mechanism.

Spring MVC applies `defaultValue` when the parameter is absent or empty according to binding rules. If you need to distinguish strictly between omitted, empty string, and an explicit value, test those cases against your Spring version.

`@RequestParam(required = false) Integer pageSize` is not equivalent to `@RequestParam(defaultValue = "20") int pageSize`. The former can receive null when omitted; the latter receives a runtime value of 20.

## 7. Declaring defaults for request headers

Spring MVC also supports defaults for request headers:

```java
@GetMapping("/api/profile")
ProfileResponse getProfile(
        @RequestHeader(name = "X-Client-Locale", defaultValue = "vi-VN")
        String locale) {
    return profileService.getProfile(locale);
}
```

If the header is not sent, Spring binds `locale` to `vi-VN`. You can document the header in OpenAPI using `@Parameter` or let springdoc infer it from the mapping, then check the generated document.

Do not use dummy defaults for security headers such as `Authorization`. If an authentication header is missing, the security layer must reject the request per policy rather than substituting a default value.

## 8. Default values in request body DTOs

For JSON request bodies, default values can be applied via DTO field initializers or constructors. Example:

```java
public class SearchRequest {

    @Schema(
        description = "Whether to include archived orders",
        defaultValue = "false",
        example = "false"
    )
    private boolean includeArchived = false;

    @Schema(
        description = "Maximum number of items",
        defaultValue = "20",
        example = "20"
    )
    @Min(1)
    @Max(100)
    private Integer pageSize = 20;

    // getters and setters
}
```

For a mutable bean instantiated by Jackson via its no-arg constructor, if the JSON omits the property, the field initializer is normally preserved. If JSON sends `"pageSize": 50`, the setter assigns 50. If JSON sends `"pageSize": null`, the `Integer` wrapper may be assigned null under default settings despite the field initializer of 20.

This shows three states that can behave differently:

| JSON body | Typical result with illustrative DTO |
|---|---|
| `pageSize` omitted | Keeps initializer 20 |
| `"pageSize": null` | Wrapper may become null |
| `"pageSize": 50` | Value 50 |

Actual behavior also depends on constructors/records, Jackson annotations, custom deserializers, and `ObjectMapper` configuration. Test the specific DTO in use instead of assuming every object style applies initializers identically.

## 9. Schema default does not auto-fill request bodies

Suppose OpenAPI declares:

```yaml
SearchRequest:
  type: object
  properties:
    pageSize:
      type: integer
      default: 20
```

If a client sends the body:

```json
{}
```

OpenAPI does not automatically rewrite the JSON into:

```json
{
  "pageSize": 20
}
```

Assigning 20 must be handled by a DTO initializer, constructor, Jackson deserializer, controller, or service. Without such logic, `pageSize` can be null or the Java type's default value.

Swagger UI also cannot guarantee that every request body gets populated with defaults. Some schema shapes and UI widgets may show defaults/examples as reference, but clients can remove fields or send alternative payloads. The server must still handle missing fields according to the runtime contract.

## 10. Distinguishing default from validation and valid bounds

Default only describes or supplies a value when absent. Validation determines which values are accepted.

Example:

```java
@RequestParam(defaultValue = "20")
@Min(1)
@Max(100)
int pageSize
```

Meaning:

- Omitting `pageSize`: Spring binds 20.
- Sending `pageSize=50`: Spring binds 50.
- Sending `pageSize=0`: validation rejects if method validation is enabled and error handling is configured.
- Sending `pageSize=500`: validation rejects for exceeding the maximum.

`default: 20` does not restrict users to sending only 20. `maximum: 100` and `minimum: 1` describe the schema limits; `@Min` and `@Max` along with the validation mechanism enforce the limits in the application.

For constraints placed directly on controller method parameters, ensure method validation is activated according to your Spring Boot/Spring Framework version (typically via `@Validated` and corresponding validation configuration). Do not assume constraint annotations execute automatically without validation enabled.

## 11. Defaults in the service layer and application configuration

Not every default belongs in the controller. When multiple endpoints share a rule, the service or application configuration may be a better place.

Example service applying a fallback:

```java
public OrderPage list(Integer requestedPageSize) {
    int pageSize = requestedPageSize == null ? 20 : requestedPageSize;

    if (pageSize < 1 || pageSize > 100) {
        throw new InvalidPageSizeException(pageSize);
    }

    return orderRepository.findPage(pageSize);
}
```

In this case, the controller can accept a nullable `Integer` while the service decides the fallback. This is useful when multiple callers invoke the service without passing through the same controller. Still, keep the default published in OpenAPI aligned with the value applied by the service.

If the default varies by environment or operations, it can be loaded from `application.yml`:

```yaml
app:
  orders:
    default-page-size: 20
    max-page-size: 100
```

```java
@ConfigurationProperties(prefix = "app.orders")
public record OrderQueryProperties(
        int defaultPageSize,
        int maxPageSize
) {}
```

When configuring defaults from properties, use the same configuration source for runtime initialization and OpenAPI metadata generation if needed. Avoid documentation stating 20 while production is configured with 50.

## 12. Response defaults differ from request defaults

Defaults in a request schema typically inform clients which value the server uses if a field is omitted. For a response schema, `default` does not mean the server automatically injects missing properties into response JSON.

Response DTO example:

```java
public class OrderResponse {
    private String status;
    private boolean archived;

    // getters and setters
}
```

If the serializer skips the `archived` property or the DTO is not initialized with the expected value, `default: false` in OpenAPI will not automatically add `"archived": false` to the response. To guarantee a value in responses, assign it in the mapper, constructor, or service and configure serialization appropriately.

Only declare default in a response schema when it is genuinely a meaningful contract default. If the server always returns the field with a specific value, such as `false`, `example` may be more appropriate for illustrating the payload.

## 13. Using `examples` for multiple request scenarios

When an endpoint supports different usage scenarios, a single example may not suffice. OpenAPI supports `examples` to describe multiple named cases.

Request body example:

```yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        $ref: '#/components/schemas/SearchRequest'
      examples:
        defaultSearch:
          summary: Search with default page size
          value:
            keyword: laptop
            pageSize: 20
        largePage:
          summary: Search with a larger page
          value:
            keyword: laptop
            pageSize: 50
```

Named examples help Swagger UI users select test scenarios. `examples` neither replaces runtime defaults nor restricts requests to only those payloads.

In Java, `@ExampleObject` can be used inside `@Content` of `@RequestBody` or `@ApiResponse`, depending on where you need to document it. Verify that the annotation generates the expected media type and schema.

## 14. Verifying defaults in documentation and runtime behavior

After declaring defaults, verify both the OpenAPI document and real requests:

1. Open `/v3/api-docs` or `/v3/api-docs.yaml`.
2. Locate the parameter or schema and inspect `default`, `example`, `required`, `minimum`, and `maximum`.
3. Open Swagger UI and check the value displayed in the request test form.
4. Clear the value from the form and send the request to verify whether the server applies the runtime default.
5. Send a value different from the default to confirm clients can still supply other valid values.
6. Send out-of-bounds values to verify validation actually works.
7. For JSON bodies, test omitted property, explicit null, and provided value separately.
8. Inspect the error response and status code when validation fails.
9. Compare OpenAPI defaults against actual environment properties/profiles.
10. Check client generators or SDKs if those tools derive defaults from the schema.

Example test matrix for `pageSize`:

| Request | Expected runtime result |
|---|---|
| No `pageSize` query param | Uses 20 if controller has `defaultValue = "20"` |
| `?pageSize=50` | Uses 50 |
| `?pageSize=0` | Rejected by validation if `@Min(1)` is active |
| `?pageSize=101` | Rejected by validation if `@Max(100)` is active |
| `?pageSize=abc` | Binding type conversion error, typically `400 Bad Request` |

For body DTOs with initializers, test missing properties and explicit nulls separately because those two requests can produce different Java states.

## 15. Common errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| Swagger UI shows default but API receives null | Only `@Schema(defaultValue)` or `schema.default` was declared | Add runtime defaults in Spring MVC, DTO, or service |
| API applies default but docs do not show it | Springdoc does not infer metadata from the setup used | Add `@Schema(defaultValue)` or `@Parameter` and check output |
| Users can edit the value in Swagger UI | Default is only a hint, not a restriction | Use validation if values must be constrained |
| Missing parameter still fails | No runtime default or parameter is marked required | Configure `@RequestParam(defaultValue = ...)` or appropriate rules |
| `default` leads readers to think field is required | Confusion between default and required | Document presence separately via `required` |
| Body missing a field does not get default | Default was only declared in OpenAPI schema | Initialize in DTO or handle fallback in the application |
| Body explicit null overrides initializer | Jackson assigns null to wrapper field | Define null handling via `@JsonSetter`, validation, or suitable field types |
| Default value violates bounds | Default was not validated alongside constraints or config diverged | Ensure defaults lie within valid bounds and test |
| Default in docs differs from production | Hardcoded metadata while runtime reads another property | Share a single config source or derive metadata from config |
| Using example as a default value | Confusing `example` and `default` | Declare the right metadata for each purpose |

## 16. Design principles

- Use `default` to document contract defaults; never treat it as a server execution directive.
- Use `example` or `examples` to guide calling patterns and illustrate scenarios.
- Use `required` to document whether a parameter or property must be present.
- Use `enum`, `minimum`, `maximum`, Bean Validation, or business logic to constrain values.
- Use `@RequestParam(defaultValue = ...)` or `@RequestHeader(defaultValue = ...)` when Spring MVC should apply a default during binding.
- Use field initializers, constructors, or service fallbacks for request body defaults according to chosen semantics.
- Distinguish missing properties from explicit nulls, especially in partial-update DTOs.
- Keep OpenAPI defaults synchronized with runtime and environment configurations.
- Never use fake defaults for security headers or sensitive data.
- Test JSON/YAML docs, Swagger UI, and direct requests outside Swagger UI.

## Conclusion

The `default` value in OpenAPI and the value displayed in Swagger UI primarily describe or suggest values to API consumers. They do not mutate requests, restrict client choices, or cause Spring Boot to fill in missing data automatically. To achieve real default behavior, implement it in Spring MVC binding, DTO/Jackson, or the service layer; to constrain values, use validation and runtime rules. Springdoc-openapi helps publish `default`, `example`, `required`, and constraints in the contract. Keep that metadata aligned with real behavior and test missing, null, valid, and invalid inputs separately.
