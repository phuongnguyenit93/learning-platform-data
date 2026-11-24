# Describing `@PathVariable` and the Mandatory Requirement for Path Parameters

In REST APIs, a path parameter is a value embedded directly in the URL path, typically used to identify a specific resource. For example, `/api/orders/8f...` can represent an order with its corresponding identifier. In Spring MVC, the `@PathVariable` annotation binds a variable segment in the URL to a controller method parameter. Springdoc-openapi reads the mapping and method signature to describe that variable as a path parameter in the OpenAPI contract.

The key rule is that a path parameter is always required in OpenAPI. If a URL has the form `/orders/{orderId}`, the client must provide a value for `orderId` to match the path. This is mandated by the path structure and the OpenAPI specification, and aligns with Spring's default `required = true` for `@PathVariable`.

## 1. What Is a Path Parameter?

A path parameter is a variable part of a path template. The variable is enclosed in curly braces `{}` and replaced with an actual value when a client sends a request.

Example:

```text
GET /api/orders/{orderId}
GET /api/customers/{customerId}/orders/{orderId}
GET /api/products/{productId}/reviews/{reviewId}
```

When calling the API, the client substitutes the variables with concrete values:

```text
GET /api/orders/125
GET /api/customers/cus-42/orders/125
GET /api/products/sku-900/reviews/rv-17
```

Path parameters are commonly used to identify a resource or a sub-resource in a hierarchical relationship. For example:

- `/orders/{orderId}` identifies a single order.
- `/customers/{customerId}/orders` identifies a customer's list of orders.
- `/customers/{customerId}/orders/{orderId}` identifies a specific order belonging to that customer.

Path parameters differ from query parameters. `/orders/125` uses a path parameter to designate order 125; `/orders?status=PAID` uses the `status` query parameter to filter the list of orders. The two types have different locations, semantics, and declarations in OpenAPI.

## 2. Declaring Path Variables in Spring MVC

Spring MVC uses mapping annotations to declare path templates. `@PathVariable` extracts the variable's value from the path and binds it to the controller method parameter.

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{orderId}")
    OrderResponse getById(
            @PathVariable("orderId") Long id) {
        return orderService.findById(id);
    }
}
```

In the example:

1. `@RequestMapping("/api/orders")` declares the common controller prefix.
2. `@GetMapping("/{orderId}")` declares a path with the `orderId` variable and HTTP method `GET`.
3. `@PathVariable("orderId")` instructs Spring to retrieve the value from the exact `orderId` variable in the URL.
4. Spring converts the string value in the URL to type `Long` before invoking the controller method.

When a client calls `GET /api/orders/125`, the `id` parameter in the method receives the numeric value `125`. The Java variable name `id` can differ from the URL variable name because it is explicitly linked using `@PathVariable("orderId")`.

### Path Variable Name

`@PathVariable` has `value` and `name` attributes as aliases for each other. You can write:

```java
@PathVariable("orderId") Long id
```

or:

```java
@PathVariable(name = "orderId") Long id
```

If you omit the name in the annotation, Spring must infer the parameter name from compiled bytecode metadata. This inference depends on build configuration, such as the `-parameters` compiler flag. To avoid failures when build settings or Java variable names change, always specify the path variable name explicitly in the annotation.

```java
@GetMapping("/{orderId}")
OrderResponse getById(@PathVariable("orderId") UUID id) {
    return orderService.findById(id);
}
```

The name `orderId` must match the placeholder in the mapping. If the URL declares `{orderId}` but the annotation points to `id` without a matching placeholder, Spring cannot bind the variable properly and requests may fail during processing.

## 3. Multiple Path Variables in One Endpoint

An endpoint can contain multiple path variables. Each variable needs a corresponding `@PathVariable` parameter.

```java
@GetMapping("/customers/{customerId}/orders/{orderId}")
OrderResponse getCustomerOrder(
        @PathVariable("customerId") UUID customerId,
        @PathVariable("orderId") UUID orderId) {
    return orderService.findCustomerOrder(customerId, orderId);
}
```

This mapping has two placeholders: `customerId` and `orderId`. Spring binds each value to the right parameter based on the declared name. The OpenAPI contract must also describe both path parameters.

```yaml
paths:
  /customers/{customerId}/orders/{orderId}:
    get:
      parameters:
        - name: customerId
          in: path
          required: true
          schema:
            type: string
            format: uuid
        - name: orderId
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        '200':
          description: Order found
```

Do not merge two variables into one parameter if the application needs to process them separately. Explicit declaration ensures accurate Spring binding and helps client generators produce proper method signatures.

## 4. Data Types and Value Conversion

Values in a URL are transmitted over HTTP as text. Spring MVC uses its conversion mechanism to transform that text into the parameter type declared by the controller.

| Java Parameter Type | Path Segment Example | Common OpenAPI Schema Type |
|---|---|---|
| `String` | `ORD-001` | `type: string` |
| `Long` or `Integer` | `125` | `type: integer`, appropriate format such as `int64` or `int32` |
| `UUID` | `550e8400-e29b-41d4-a716-446655440000` | `type: string`, `format: uuid` |
| `BigDecimal` | `1250.50` | `type: number` |
| `Boolean` | `true` or `false` | `type: boolean` |
| `Enum` | `PENDING` | `type: string` with `enum` set if recognized |

Example using UUID:

```java
@GetMapping("/{orderId}")
OrderResponse getById(@PathVariable("orderId") UUID orderId) {
    return orderService.findById(orderId);
}
```

Spring converts the UUID string in the path into a `UUID` object. Springdoc can infer a string schema with `format: uuid` from the parameter type.

If a client sends a value that cannot be converted, such as `/api/orders/abc` when the parameter is `Long`, Spring typically returns a binding/conversion error before invoking the controller method. The exact status code and error payload depend on the application's exception handler and error-handling configuration. Document the corresponding error responses if the public API commits to that behavior.

For custom types, enums, or custom converters, verify that the generated YAML accurately reflects the URL format accepted by the API. Additional OpenAPI metadata can be added when Java types alone cannot express public rules.

## 5. Why Is a Path Parameter Always Required?

In OpenAPI, a parameter with `in: path` must have `required: true`. A path template defines the URL structure; if the placeholder `{orderId}` is present, the client must supply a replacement value to form a valid URL.

Example:

```yaml
paths:
  /api/orders/{orderId}:
    get:
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: integer
            format: int64
      responses:
        '200':
          description: Order found
```

`required: true` is not a decorative option. It is an OpenAPI requirement for path parameters. A specification that sets `required: false` for a parameter with `in: path` is invalid according to the specification.

In Spring, `@PathVariable` has a `required` attribute with a default value of `true`:

```java
@GetMapping("/{orderId}")
OrderResponse getById(
        @PathVariable(value = "orderId", required = true) Long id) {
    return orderService.findById(id);
}
```

Usually you do not need to write `required = true` since it is already the default:

```java
@PathVariable("orderId") Long id
```

Springdoc resolves the path variable from the mapping and `@PathVariable`, then documents it as a required path parameter in OpenAPI. Even if some configuration or extra metadata attempts to mark a path parameter as optional, OpenAPI still requires `required: true`.

## 6. `required = false` Does Not Remove the Placeholder from the URL

Do not use `@PathVariable(required = false)` expecting the `/orders/{orderId}` endpoint to automatically match both `/orders` and `/orders/125`. Route matching is determined by the path mapping. When the placeholder is absent from the URL, the `/orders/{orderId}` mapping normally does not match the `/orders` request.

If the API needs to support both URL forms, declare two separate mappings or design the endpoint so that truly optional values are passed via query parameters.

Example declaring two separate mappings with two controller methods:

```java
@GetMapping
List<OrderResponse> findAll() {
    return orderService.findAll();
}

@GetMapping("/{orderId}")
OrderResponse findById(@PathVariable("orderId") Long orderId) {
    return orderService.findById(orderId);
}
```

In the OpenAPI document, these two methods become two distinct paths: `/api/orders` with no path parameter and `/api/orders/{orderId}` with a required `orderId` path parameter. This approach clarifies both behaviors without creating an optional path parameter.

If the goal is to filter a list by a value that may be omitted, a query parameter is usually more suitable:

```java
@GetMapping
List<OrderResponse> findOrders(
        @RequestParam(name = "customerId", required = false) UUID customerId) {
    return orderService.findByCustomer(customerId);
}
```

The contract then describes `customerId` as an optional query parameter:

```yaml
parameters:
  - name: customerId
    in: query
    required: false
    schema:
      type: string
      format: uuid
```

Selection rules:

- Use a path parameter when the value is a structural part used to identify a resource or sub-resource.
- Use a query parameter when the value is a filter or option that can be omitted.
- If there are two distinct URL structures, document them with appropriate separate paths/operations instead of making a path parameter optional in OpenAPI.

## 7. Describing Path Parameters with springdoc-openapi

Springdoc typically infers the name, location, and data type from `@PathVariable` and the path mapping. To make the contract more helpful for clients, you can add descriptions, examples, and metadata using Swagger/OpenAPI's `@Parameter` annotation.

```java
@Operation(summary = "Get order details")
@GetMapping("/{orderId}")
OrderResponse getById(
        @PathVariable("orderId")
        @Parameter(
            description = "Order UUID",
            example = "550e8400-e29b-41d4-a716-446655440000"
        )
        UUID orderId) {
    return orderService.findById(orderId);
}
```

The Spring annotation controls request binding; `@Parameter` adds information for the contract. Do not confuse `@Parameter` with `@PathVariable`: the OpenAPI annotation does not create routes and does not replace Spring's value-binding mechanism.

Since a path parameter is mandatory in OpenAPI, do not declare `required = false` in `@Parameter`. If the `required` attribute is specified, its value must match the mandatory rule for path parameters.

A portion of the generated YAML might look like:

```yaml
paths:
  /api/orders/{orderId}:
    get:
      summary: Get order details
      parameters:
        - name: orderId
          in: path
          description: Order UUID
          required: true
          example: 550e8400-e29b-41d4-a716-446655440000
          schema:
            type: string
            format: uuid
      responses:
        '200':
          description: Order found
```

Field names and the placement of `example` in the output may vary depending on the library version or schema configuration, but `name`, `in: path`, and `required: true` are the key attributes to verify.

## 8. Validation on Path Variables

Path parameters not only need the right type, they sometimes also have a specific value range. For example, an order ID must be positive, or a string must have a bounded length. Bean Validation can be used to check values after Spring converts them.

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{orderId}")
    OrderResponse getById(
            @PathVariable("orderId") @Positive Long orderId) {
        return orderService.findById(orderId);
    }
}
```

Whether method validation executes depends on the Spring version, validation configuration, and applied annotations. Verify at runtime to confirm constraints are actually enforced. Springdoc can reflect some supported constraints as schema restrictions, though not every business rule or custom validator converts completely into OpenAPI.

If `orderId` must be greater than 0, the contract can describe the corresponding constraint:

```yaml
parameters:
  - name: orderId
    in: path
    required: true
    schema:
      type: integer
      format: int64
      minimum: 1
```

Responses for invalid formats or validation failures must match how the application handles errors. For example, a string that cannot be converted to `Long` may trigger a binding error; a negative number may be rejected by validation. These two cases may produce different status codes or error bodies.

## 9. Common Issues

| Symptom | Cause | Resolution |
|---|---|---|
| Cannot retrieve path variable value | Name in `@PathVariable` does not match placeholder | Use the same name or declare the name explicitly |
| Error resolving parameter name | Relying on parameter name while build omits name metadata | Declare `@PathVariable("orderId")` |
| Request `/orders` does not match `/orders/{orderId}` | Placeholder is a mandatory part of the route | Declare a separate route or use a query parameter |
| Invalid UUID/Long value | URL string cannot be converted to the Java type | Validate input format and document error responses |
| Documentation marks path parameter as optional | OpenAPI metadata customized incorrectly or documentation manually edited | Ensure `required: true` |
| Swagger UI displays wrong parameter name | Path placeholder name and parameter metadata out of sync | Inspect mapping, annotations, and generated YAML |
| Parameter missing format or constraints | Custom type or constraint not fully inferred | Add `@Parameter`/`@Schema` or a customizer |

## 10. Path Parameter Review Checklist

- [ ] Every placeholder in the path template has a parameter with the same name.
- [ ] The parameter is documented with `in: path`.
- [ ] `required` is always `true`.
- [ ] `@PathVariable` references the exact placeholder name.
- [ ] Name is declared explicitly when not relying on compile-time parameter name metadata.
- [ ] Java type is compatible with the value format clients send in the URL.
- [ ] OpenAPI schema includes `type`, `format`, constraints, and examples where needed.
- [ ] Runtime validation and error responses have been tested in practice.
- [ ] If the value can be omitted, consider a query parameter or separate path instead of an optional path parameter.
- [ ] OpenAPI documentation is regenerated and verified after changing the controller.

## Conclusion

`@PathVariable` links placeholders in Spring path mappings to controller method parameters. Spring converts URL values into corresponding Java types, while springdoc-openapi describes those variables as path parameters in the contract. According to OpenAPI, path parameters are always mandatory because they are structural components of the URL. Keep placeholders and annotations consistent, verify type conversions and validation, and use query parameters or separate routes whenever values are genuinely optional.
