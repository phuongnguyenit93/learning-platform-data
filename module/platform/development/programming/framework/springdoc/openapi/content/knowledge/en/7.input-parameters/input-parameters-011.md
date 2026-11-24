# Limits of Flattening Nested Properties

Springdoc-openapi can turn a Spring MVC parameter object into multiple individual query parameters. This technique is commonly called object flattening. It works well for search DTOs with simple properties such as `status`, `customerId`, `fromDate`, or `page`. However, when a DTO contains another object, complex collections, or multi-level structures, do not assume springdoc will recursively convert the entire property tree into query parameters.

Springdoc's `@ParameterObject` annotation supports decomposing a parameter object into parameters in OpenAPI documentation. Support for nested objects is limited; springdoc documentation explicitly states that nested parameter objects are not supported as independent nested parameter objects. Meanwhile, Spring MVC has its own model attribute binding mechanism. Consequently, a structure may bind in Spring at runtime without necessarily being fully and accurately represented by springdoc in the OpenAPI contract.

## 1. What Is Parameter Object Flattening?

In Spring MVC, an object-typed parameter is commonly bound from query parameters or form data via model attribute binding. Springdoc can inspect the object's properties to create individual parameters in OpenAPI instead of describing the entire object as a request body.

Example of a simple search DTO:

```java
public class OrderSearchCriteria {
    private String status;
    private UUID customerId;
    private LocalDate fromDate;
    private LocalDate toDate;

    // getters and setters
}
```

Controller using `@ParameterObject`:

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping
    List<OrderResponse> search(
            @ParameterObject @ModelAttribute OrderSearchCriteria criteria) {
        return orderService.search(criteria);
    }
}
```

Instead of a single query parameter representing the entire `OrderSearchCriteria`, OpenAPI documentation can express the properties as separate parameters:

```yaml
paths:
  /api/orders:
    get:
      parameters:
        - name: status
          in: query
          required: false
          schema:
            type: string
        - name: customerId
          in: query
          required: false
          schema:
            type: string
            format: uuid
        - name: fromDate
          in: query
          required: false
          schema:
            type: string
            format: date
        - name: toDate
          in: query
          required: false
          schema:
            type: string
            format: date
      responses:
        '200':
          description: Matching list of orders
```

Clients can call:

```text
GET /api/orders?status=PAID&customerId=550e8400-e29b-41d4-a716-446655440000&fromDate=2026-01-01
```

Each property is an independent query parameter. Data types, descriptions, examples, and constraints for each field can be expressed individually in the contract.

## 2. Boundary Between Flat Properties and Nested Properties

A flat object has direct properties that are simple types or types tooling can describe as a single parameter. Example:

```java
public class ProductFilter {
    private String keyword;
    private String category;
    private BigDecimal minPrice;
    private BigDecimal maxPrice;
    private Boolean available;

    // getters and setters
}
```

These properties can be represented as query parameters such as `keyword`, `category`, `minPrice`, `maxPrice`, and `available`.

A nested object contains a property that is itself another object:

```java
public class OrderSearchCriteria {
    private String status;
    private CustomerFilter customer;
    private DateRange dateRange;

    // getters and setters
}

public class CustomerFilter {
    private String email;
    private String tier;

    // getters and setters
}

public class DateRange {
    private LocalDate from;
    private LocalDate to;

    // getters and setters
}
```

Here, `customer` and `dateRange` are not regular scalar fields. They contain child properties requiring an additional representation convention. `@ParameterObject` should not be treated as an arbitrary recursive converter for every level of an object graph. Specifically, you cannot assume placing `@ParameterObject` on `OrderSearchCriteria` will automatically generate parameters `customer.email`, `customer.tier`, `dateRange.from`, and `dateRange.to` across all springdoc versions.

This limitation affects the generated contract: some nested properties may not appear as separate query parameters, or may not be documented in the format clients expect. Exact results also depend on property types, binding methods, annotations, and library versions. Always inspect the actual generated documentation.

## 3. Spring MVC Binding and OpenAPI Generation Are Two Separate Things

Spring MVC can bind model attributes via property paths. With a nested DTO having proper getters/setters, a request can pass child properties using dotted names:

```text
GET /api/orders?status=PAID&customer.email=buyer@example.com&dateRange.from=2026-01-01
```

Spring's `WebDataBinder` handles binding request parameters to object properties using property binding rules. Binding capability also depends on bean structure, setters, converters, binder configuration, and application security restrictions.

That does not mean springdoc automatically publishes dotted names as accurate OpenAPI parameters. `@ParameterObject` focuses on decomposing parameter objects within springdoc's supported scope; it does not alter Spring's binding mechanics and does not invent a recursive query string convention for arbitrary structures.

Separate two questions when designing an endpoint:

1. Can Spring receive and bind the query string into this DTO when the request runs?
2. Does the generated OpenAPI document accurately describe parameter names, data types, formats, and bounds that clients must send?

Both must be verified. Seeing the endpoint appear in Swagger UI is not enough; inspect `parameters` in JSON/YAML and send real requests to verify binding.

## 4. Structures Requiring Caution When Flattening

Not every property is suited for turning into a simple query parameter.

| Structure in DTO | Issue When Flattening | Design Approach to Consider |
|---|---|---|
| Scalar fields like `String`, `UUID`, `LocalDate` | Usually map cleanly to parameters | Use `@ParameterObject` for flat DTOs |
| Nested POJOs like `CustomerFilter` | Requires naming and documentation conventions for child fields; nested parameter objects are not fully supported | Flatten the DTO or document parameters explicitly |
| Deeply nested objects | Naming, schemas, and serialization are hard to align; no general recursive flattening | Switch to a request body for complex search operations |
| Collections or arrays | Must define key repetition, delimiters, or serialization styles | Explicitly declare `array`, `style`, `explode` and test clients |
| Maps with dynamic keys | No fixed parameter list to generate from properties | Use a request body or a clearly defined query format |
| Generic/complex-typed objects | Actual type may not be fully inferred from Java signatures | Add schema/parameter metadata or a customizer |
| Persistence entities | Can expose internal properties and create a hard-to-control API | Use dedicated search DTOs with explicitly allowed fields |

In particular, a search DTO should not directly reuse a JPA entity just because the entity's fields already exist. Entities often contain relationships, internal details, and fields that should never become part of the public API.

## 5. Approach 1: Designing a Flat DTO for Query Parameters

If a filter only needs a handful of simple fields, the clearest approach is placing those fields on the same DTO.

```java
public class OrderSearchCriteria {
    private String status;
    private UUID customerId;
    private LocalDate createdFrom;
    private LocalDate createdTo;
    private BigDecimal minTotal;
    private BigDecimal maxTotal;

    // getters and setters
}
```

```java
@GetMapping
List<OrderResponse> search(
        @ParameterObject @ModelAttribute OrderSearchCriteria criteria) {
    return orderService.search(criteria);
}
```

The query string has a clean structure:

```text
GET /api/orders?status=PAID&customerId=...&createdFrom=2026-01-01&minTotal=100000
```

Advantages of flat DTOs:

- Each property has a stable query parameter name.
- Springdoc generates parameters and schemas more reliably.
- Swagger UI displays each field separately for users to fill in.
- Client generators produce clean, usable method signatures.
- It is easy to control which fields are public and which are internal only.

Do not let a flat DTO grow too large. If a filter has dozens of fields across multiple business groups, consider splitting endpoints or using a search request body to keep the contract understandable.

## 6. Approach 2: Declaring Query Parameters Explicitly

For endpoints with a small number of parameters, declaring individual `@RequestParam` arguments is often clearer than passing a nested object to `@ParameterObject`.

```java
@GetMapping
List<OrderResponse> search(
        @RequestParam(required = false) String status,
        @RequestParam(required = false) UUID customerId,
        @RequestParam(required = false) LocalDate createdFrom,
        @RequestParam(required = false) LocalDate createdTo) {
    return orderService.search(status, customerId, createdFrom, createdTo);
}
```

Metadata can be added to each parameter with OpenAPI annotations:

```java
@GetMapping
List<OrderResponse> search(
        @Parameter(description = "Order status", example = "PAID")
        @RequestParam(required = false) String status,
        @Parameter(description = "Customer identifier")
        @RequestParam(required = false) UUID customerId) {
    return orderService.search(status, customerId, null, null);
}
```

This creates a direct contract without relying on springdoc discovering properties of a nested object. The tradeoff is a longer controller signature if there are too many parameters.

If you need to group parameters into an internal object, you can use a model attribute and supply OpenAPI descriptions via `@Parameters` or a customizer. Avoid letting springdoc auto-generate a second set of parameters duplicating the explicitly declared ones.

## 7. Approach 3: Using Dotted Query Names and Documenting the Contract Clearly

In some applications, teams want to keep a nested DTO at runtime while publishing query parameters as property paths, such as `customer.email` or `dateRange.from`. Spring MVC can bind this naming format if the model attribute and bean properties are configured properly.

```text
GET /api/orders?customer.email=buyer@example.com&dateRange.from=2026-01-01
```

If choosing this convention, the OpenAPI contract must document the exact parameter names clients must send. Explicit metadata can be declared on the operation, for example:

```java
@Operation(summary = "Search orders")
@Parameters({
    @Parameter(
        name = "customer.email",
        in = ParameterIn.QUERY,
        description = "Customer email address",
        schema = @Schema(type = "string", format = "email")
    ),
    @Parameter(
        name = "dateRange.from",
        in = ParameterIn.QUERY,
        description = "Filter start date",
        schema = @Schema(type = "string", format = "date")
    )
})
@GetMapping
List<OrderResponse> search(@ModelAttribute OrderSearchCriteria criteria) {
    return orderService.search(criteria);
}
```

This is an explicit contract declaration; verify against your springdoc version to avoid duplicate parameters auto-generated from the model attribute. If auto-generation causes duplicates or wrong types, use an `OperationCustomizer` to adjust the operation or switch to individual `@RequestParam` declarations.

Do not use dots merely because they resemble object structure. Query parameter names are part of the public contract; clearly define how clients encode them, URL-encode when needed, and how Spring's binder receives values.

## 8. Approach 4: Documenting Query Objects with `deepObject` When Appropriate

OpenAPI supports `style: deepObject` for certain object-shaped query parameters. This representation groups properties under a single parameter name:

```yaml
parameters:
  - name: filter
    in: query
    style: deepObject
    explode: true
    schema:
      type: object
      properties:
        status:
          type: string
        customerId:
          type: string
          format: uuid
```

The corresponding query string typically looks like:

```text
GET /api/orders?filter[status]=PAID&filter[customerId]=550e8400-e29b-41d4-a716-446655440000
```

`deepObject` can fit flat objects with scalar properties. Serialization rules for deeply nested objects or arrays inside objects are not uniformly supported across tools, and you should not assume all client generators interpret them identically. Furthermore, Spring MVC does not automatically bind `filter[status]` syntax into a DTO following this convention without extra configuration or handling.

Choose `deepObject` only when client, server, and validators agree on the serialization format. Inspect actual URLs, binding configuration, and generated documentation. Do not use `deepObject` as a workaround for nested `@ParameterObject` limitations without verifying compatibility.

## 9. Approach 5: Moving Complex Filters to a Request Body

If a filter has multiple levels, lists of criteria, `AND`/`OR` groups, value ranges, or deep nesting, a request body is usually more suitable than query parameters.

Search DTO example:

```java
public class OrderSearchRequest {
    private String status;
    private CustomerFilter customer;
    private DateRange dateRange;
    private List<String> channels;

    // getters and setters
}
```

Controller:

```java
@PostMapping("/search")
List<OrderResponse> search(@Valid @RequestBody OrderSearchRequest request) {
    return orderService.search(request);
}
```

OpenAPI contract:

```yaml
paths:
  /api/orders/search:
    post:
      summary: Search orders by criteria
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/OrderSearchRequest'
      responses:
        '200':
          description: Matching list of orders
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/OrderResponse'
```

Request bodies preserve object structures, nested objects, and collections. Schemas can naturally describe nested fields while supporting validation and examples at every level.

POST search endpoints must be designed deliberately. Do not move every filter to POST if a simple GET query suffices; weigh caching, safety semantics, request size limits, and the system's API conventions.

## 10. Customizing the OpenAPI Model with Customizers

When runtime architecture requires keeping nested objects while the contract needs a representation beyond what springdoc infers automatically, you can customize the OpenAPI model.

Springdoc provides extension points such as `OperationCustomizer` for Spring MVC operations and `OpenApiCustomizer` for the overall document. They allow adding, removing, or adjusting parameters, schemas, and metadata per application rules.

Skeleton `OperationCustomizer` example:

```java
@Bean
OperationCustomizer searchParameterCustomizer() {
    return (operation, handlerMethod) -> {
        if (handlerMethod.getMethod().getName().equals("search")) {
            // Add or adjust operation parameters here.
        }
        return operation;
    };
}
```

Write customizers with explicit conditions to avoid applying them to every operation or creating duplicate parameter names. Match based on dedicated annotations, controller plus method name, or other stable metadata rather than relying solely on method names that might collide across controllers.

After customizing, inspect the generated JSON/YAML and run an OpenAPI validator. A customizer only alters documentation; it does not change how Spring MVC binds query strings. If the contract publishes `customer.email`, the controller must still actually accept that name.

## 11. Common Errors and Diagnostics

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Nested fields do not appear in Swagger UI | `@ParameterObject` does not recursively flatten nested parameter objects | Use a flat DTO or declare parameters explicitly |
| Spring receives queries but docs lack matching parameters | Spring model binding and springdoc generation have separate scopes | Cross-check YAML against real query strings, add metadata |
| Docs show only an opaque object parameter with unclear usage | Property is a nested POJO or complex type | Choose an explicit query convention or switch to a request body |
| Duplicate parameters | Relying on springdoc auto-generation while also declaring `@Parameter`/customizer | Maintain a single metadata source for each name and location pair |
| Client generator builds malformed requests | Query object structure or `deepObject` not supported by tooling as expected | Use explicit scalar queries or a request body |
| Spring fails to bind `customer.email` | DTO lacks getters/setters, invalid property path, or binder restrictions | Inspect bean and `WebDataBinder` configuration |
| Inconsistent query collections | Array serialization and `style`/`explode` rules undefined | Document format clearly and test with real clients |
| DTO changes expose extra fields | Automatically flattening shared objects or entities | Use dedicated public DTOs and control exposed fields |

When investigating, inspect three layers separately:

1. **Binding:** send real requests and confirm Spring receives accurate values in the DTO.
2. **Generation:** fetch `/v3/api-docs` or `/v3/api-docs.yaml`, inspect `paths`, `parameters`, schemas, and published query names.
3. **Client:** use Swagger UI or client generators to verify how tools build URLs against server conventions.

## 12. Design Principles

- Use `@ParameterObject` for flat query DTOs with an explicit set of public properties and simple data types.
- Do not assume `@ParameterObject` automatically flattens arbitrary nested POJOs or multi-level object graphs.
- Clearly distinguish Spring MVC binding capabilities from springdoc's automatic documentation capabilities.
- If using property paths like `customer.email`, publish the exact query names and verify actual binding.
- Use `deepObject` only for structures supported by both client and server; avoid deep nesting or complex arrays without clear conventions.
- Use `@RequestParam` and `@Parameter` metadata when field count is small and a direct contract is needed.
- Use a request body for complex filters with nested objects, collections, or multi-level conditional logic.
- Use customizers when programmatic documentation control is needed, while ensuring no duplicate parameters are generated.
- Never use persistence entities as public parameter objects; create dedicated DTOs with an allowlist of fields.
- After modifying DTO structures or annotations, inspect the OpenAPI document and send real requests to verify.

## Conclusion

Flattening properties turns simple search DTOs into readable, easy-to-use query parameters. Limitations arise when DTOs contain nested objects, collections, or multi-level structures: Spring MVC may bind some property paths at runtime, yet `@ParameterObject` is not a general recursive OpenAPI flattening mechanism. Choose flat DTOs for simple queries, declare parameters explicitly when exact name control is needed, or use request bodies for deeply structured filters. Whichever approach you take, verify actual binding, springdoc-generated documentation, and how clients send requests.
