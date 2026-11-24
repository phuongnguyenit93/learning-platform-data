# ResponseEntity, Optional, and Wrapper Unwrapping Rules When Supported

## 1. Why Are Java Return Types Not Always Identical to JSON Schemas?

A Spring Boot controller can declare return types such as `ProductResponse`, `ResponseEntity<ProductResponse>`, `Optional<ProductResponse>`, or `ResponseEntity<List<ProductResponse>>`. These types help Spring control HTTP responses and help Java express data, but not all of them appear in the JSON that clients receive.

For example, with the method:

~~~java
@GetMapping("/api/products/{id}")
public ResponseEntity<ProductResponse> findById(
    @PathVariable Long id
) {
    return ResponseEntity.ok(productService.getByIdOrThrow(id));
}
~~~

The HTTP response has a status, headers, and a body. The body is a `ProductResponse` object; clients do not receive a JSON object with properties named `body`, `statusCode`, or `headers` mirroring the structure of the `ResponseEntity` class.

Springdoc OpenAPI must distinguish **wrappers used for Java/Spring handling** from **the payload actually transmitted over HTTP**. When it recognizes a supported wrapper, the library can unwrap it during schema generation and describe the inner data type.

This lesson focuses on two common types:

- **ResponseEntity<T>**: a Spring class describing HTTP status, headers, and body.
- **Optional<T>**: a Java class representing a value that may be present or absent.

Unwrapping rules depend on the wrapper type and the type-resolution capabilities of the Springdoc version and bundled OpenAPI libraries. Always inspect the generated JSON/YAML document and actual responses before treating a schema as accurate.

## 2. ResponseEntity<T> Represents an HTTP Response

`ResponseEntity<T>` belongs to Spring Framework and allows a controller to explicitly determine:

- The HTTP status code, such as 200, 201, 204, or 404.
- HTTP response headers, such as `Location`, `ETag`, or `Cache-Control`.
- A body of type `T` or no body at all.

Example returning success:

~~~java
@GetMapping("/api/products/{id}")
public ResponseEntity<ProductResponse> findById(
    @PathVariable Long id
) {
    ProductResponse product = productService.getByIdOrThrow(id);
    return ResponseEntity.ok(product);
}
~~~

Spring uses `ResponseEntity` to construct the HTTP response. The body is serialized to JSON according to the configured message converter. In terms of the OpenAPI contract, the response schema describes **ProductResponse**, while status and headers are described in separate parts of the Response Object.

A corresponding response can be represented as follows:

~~~yaml
responses:
  "200":
    description: Product found
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/ProductResponse'
~~~

Springdoc typically recognizes `ResponseEntity` and resolves the generic type `T` to generate the body schema. It does not need to generate a JSON schema for the internal structure of the `ResponseEntity` class.

## 3. Unwrapping ResponseEntity While Preserving HTTP Information

Unwrapping in the schema does not mean dropping the status or headers of the HTTP response. These belong to two separate layers:

| Component | Where it appears in the contract |
|---|---|
| Body data type `T` | Schema inside response `content` |
| HTTP status code | Response key such as `200`, `201`, `404` |
| HTTP response headers | `headers` property of the Response Object |
| Media type | `content` key such as `application/json` |
| Absent body | Response omits `content` or declares appropriate content |

Example creating a product:

~~~java
@PostMapping("/api/products")
public ResponseEntity<ProductResponse> create(
    @Valid @RequestBody CreateProductRequest request
) {
    ProductResponse created = productService.create(request);
    URI location = URI.create("/api/products/" + created.id());

    return ResponseEntity.created(location).body(created);
}
~~~

The method above returns status 201 Created, a `Location` header, and a `ProductResponse` body. The body schema remains `ProductResponse`; the 201 status and `Location` information must be documented separately in OpenAPI.

You can declare this explicitly:

~~~java
@PostMapping("/api/products")
@Operation(summary = "Create a product")
@ApiResponse(
    responseCode = "201",
    description = "Product created",
    headers = @Header(
        name = "Location",
        description = "URL of the newly created product",
        schema = @Schema(type = "string", format = "uri")
    ),
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = ProductResponse.class)
    )
)
public ResponseEntity<ProductResponse> create(
    @Valid @RequestBody CreateProductRequest request
) {
    ProductResponse created = productService.create(request);
    URI location = URI.create("/api/products/" + created.id());

    return ResponseEntity.created(location).body(created);
}
~~~

OpenAPI annotations publish the contract. `ResponseEntity` still determines the actual runtime response. If you only declare a 201 response in annotations while the code actually returns 200, the documentation will not match the behavior.

## 4. ResponseEntity<Void> and Bodyless Responses

Some operations only need to communicate results via status codes and return no JSON. For example, deleting a resource successfully may return 204 No Content:

~~~java
@DeleteMapping("/api/products/{id}")
public ResponseEntity<Void> delete(
    @PathVariable Long id
) {
    productService.delete(id);
    return ResponseEntity.noContent().build();
}
~~~

The generic type `Void` indicates the response has no payload. OpenAPI should document the 204 response without generating a body schema:

~~~yaml
responses:
  "204":
    description: Product deleted successfully
~~~

Do not declare an empty object schema just because the Java type is `ResponseEntity`. If a response truly has no body, express that via the response code and its corresponding description.

Other situations:

~~~java
return ResponseEntity.notFound().build();
~~~

Returns 404 with no body.

~~~java
return ResponseEntity.status(HttpStatus.ACCEPTED).build();
~~~

Returns 202 with no body.

If the API returns an error body for 404 or 202, use `ResponseEntity` with an appropriate body type and declare the corresponding error schema. A method's generic type only describes one `T`; different status codes can have different content schemas and should be declared with appropriate `@ApiResponse` annotations.

## 5. How Springdoc Infers Response Schemas from Generic Types

With a generic return type, Springdoc can analyze the type parameter to determine the payload.

Examples:

~~~java
ResponseEntity<ProductResponse>
ResponseEntity<List<ProductResponse>>
ResponseEntity<Map<String, ProductResponse>>
~~~

The corresponding schemas are typically:

| Java type | Expected body schema |
|---|---|
| `ResponseEntity<ProductResponse>` | `ProductResponse` object |
| `ResponseEntity<List<ProductResponse>>` | Array with `items` of `ProductResponse` |
| `ResponseEntity<Map<String, ProductResponse>>` | Object with values matching the `ProductResponse` schema |
| `ResponseEntity<Void>` | No body schema |

List example:

~~~java
@GetMapping("/api/products")
public ResponseEntity<List<ProductResponse>> findAll() {
    return ResponseEntity.ok(productService.findAll());
}
~~~

The JSON body is an array:

~~~json
[
  {
    "id": 101,
    "name": "Mechanical keyboard"
  },
  {
    "id": 102,
    "name": "Wireless mouse"
  }
]
~~~

Springdoc must preserve the inner generic type when unwrapping `ResponseEntity`. If the return type is declared raw as `ResponseEntity` or uses an unresolvable generic, the library may fail to infer a concrete schema. In that case, use a complete return type or declare the response schema explicitly.

## 6. Optional<T> Represents a Potentially Absent Value

`Optional<T>` belongs to Java and is commonly used at the service or repository layer to express that a lookup operation may find no data.

Example:

~~~java
public Optional<Product> findById(Long id) {
    return productRepository.findById(id);
}
~~~

`Optional` helps callers explicitly handle two cases:

- Present: `Optional` holds a `Product`.
- Absent: `Optional.empty()`.

`Optional` is a Java wrapper. JSON has no dedicated `Optional` data type. When Springdoc and the OpenAPI model library support resolving this wrapper, the generated schema is usually the schema of `T`, rather than an object with `present`, `empty`, or `value` properties.

For example, if the return type is `Optional<ProductResponse>` and the wrapper is resolved, the body schema describes `ProductResponse`. However, the schema of `T` does not by itself determine what happens when `Optional.empty()` is returned.

**`Optional.empty()` does not automatically mean HTTP 404.** Nor does it define a response code, error body, or resource-not-found rule on its own. The application must explicitly translate the absent state into an HTTP response.

## 7. Converting Service Optional into ResponseEntity in the Controller

A clean implementation lets the service return `Optional`, and then the controller decides the status code:

~~~java
@GetMapping("/api/products/{id}")
@Operation(summary = "Get product by ID")
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Product found",
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = ProductResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "404",
        description = "Product not found",
        content = @Content
    )
})
public ResponseEntity<ProductResponse> findById(
    @PathVariable Long id
) {
    return productService.findById(id)
        .map(ProductResponse::from)
        .map(ResponseEntity::ok)
        .orElseGet(() -> ResponseEntity.notFound().build());
}
~~~

This approach separates responsibilities clearly:

- The service searches for data and returns `Optional`.
- The controller maps a present value to 200 OK with a body.
- The controller maps an absent value to 404 Not Found with no body.
- OpenAPI publishes both response codes and their corresponding schemas.

If the API convention is to return an error body when not found, use an error response DTO and declare a content schema for 404. Do not force clients to infer behavior from a Java `Optional` they cannot see.

## 8. Returning Optional<T> Directly from a Controller

You may encounter controllers declaring:

~~~java
@GetMapping("/api/products/featured")
public Optional<ProductResponse> getFeatured() {
    return productService.findFeatured()
        .map(ProductResponse::from);
}
~~~

At the schema level, Springdoc can unwrap `Optional` if the version and type resolver support it. However, the HTTP behavior when `Optional` is empty also depends on how Spring MVC handles return values and the application's message converter/Jackson configuration.

Do not assume an empty `Optional` always produces 404, 204, or a JSON `null`. Call the endpoint with both present and absent data to verify the actual status, headers, and body.

If the business meaning of an empty result is "resource not found", convert `Optional` into a `ResponseEntity` or throw an exception clearly mapped to 404. If the endpoint always exists and an empty result is a valid state, define the concrete response body clients receive.

For public APIs, using `ResponseEntity` in controllers usually expresses status and body more clearly than letting `Optional` determine HTTP behavior indirectly.

## 9. Why Should You Avoid Nesting ResponseEntity<Optional<T>>?

You could write:

~~~java
public ResponseEntity<Optional<ProductResponse>> findById(
    Long id
) {
    // ...
}
~~~

However, this type places two layers expressing absence next to each other:

- `ResponseEntity` determines the status and body of the HTTP response.
- `Optional` further expresses that the body may have no value.

This makes the contract hard to read. Springdoc may resolve one or more wrappers to produce the schema for `T` depending on support, while runtime may serialize an empty `Optional` differently from client expectations.

Convert `Optional` into an HTTP response before returning:

~~~java
public ResponseEntity<ProductResponse> findById(Long id) {
    return productService.findById(id)
        .map(ProductResponse::from)
        .map(ResponseEntity::ok)
        .orElseGet(() -> ResponseEntity.notFound().build());
}
~~~

That way, the return type directly expresses the success response payload and the controller decides the absent case via status code. OpenAPI is also easier to annotate per response.

## 10. Distinguishing Optional from Nullable and Non-Required Properties

`Optional`, `nullable`, and `required` are distinct concepts:

| Concept | Scope | Meaning |
|---|---|---|
| Java `Optional<T>` | Java type | A value that may be present or absent |
| Schema `nullable` | JSON value | Allows the `null` value |
| Schema `required` | Object property | Whether the property must appear |
| `RequestBody.required` | HTTP request | Whether the entire request body is required |
| Response `content` | HTTP response | Whether a body is returned for that status code |

For example, a response property may be optional to appear, yet when it appears it must be a string. Another property may be required to appear yet accept `null`. Both cases must be described in the schema and cannot be inferred solely from a Java field having type `Optional`.

For DTOs exchanged over an API, use data types and schema annotations that directly express the JSON contract. Avoid putting `Optional` on every field just to express that data may be missing. Review how Jackson serializes/deserializes `Optional` and the active configuration before using this type in public DTOs.

## 11. Are Custom Wrappers Unwrapped?

Not every generic class is a technical wrapper that can be stripped from the schema.

Example:

~~~java
public record ApiEnvelope<T>(
    String traceId,
    T data,
    String message
) {}
~~~

If the controller returns:

~~~java
public ResponseEntity<ApiEnvelope<ProductResponse>> findProduct(
    @PathVariable Long id
) {
    ApiEnvelope<ProductResponse> envelope =
        productService.findEnvelope(id);

    return ResponseEntity.ok(envelope);
}
~~~

The actual JSON response looks like:

~~~json
{
  "traceId": "req-123",
  "data": {
    "id": 101,
    "name": "Mechanical keyboard"
  },
  "message": "Success"
}
~~~

In this case, `ApiEnvelope` is part of the public payload. The schema must keep the envelope object along with its `traceId`, `data`, and `message` properties. Springdoc should not strip this class merely because its type name contains `Response` or `Envelope`.

Unwrap only when the wrapper does not appear in the JSON data sent over the wire and the processing mechanism genuinely unwraps it into the inner payload. For custom wrappers, do not assume Springdoc recognizes them automatically. Inspect the serializer, controller return handler, and OpenAPI document.

If your organization wants to publish a common envelope schema, document it as a normal DTO and use concrete generic types. If using a custom converter or response advice to transform payloads, the OpenAPI document must reflect the final structure clients receive.

## 12. When Do You Need to Declare the Response Schema Explicitly?

Springdoc can usually infer the schema from a concrete return type. Explicit documentation may be needed when:

- The method returns a raw or wildcard `ResponseEntity`.
- The generic type is lost due to an intermediate type or method signature.
- One operation has multiple response codes with different body schemas.
- Success bodies and error bodies use different DTOs.
- Responses include important headers or special content types.
- The actual schema is affected by a custom serializer or `ResponseBodyAdvice`.

Example:

~~~java
@GetMapping("/api/products/{id}")
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Product found",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ProductResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "404",
        description = "Product not found",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ApiError.class)
        )
    )
})
public ResponseEntity<?> findById(@PathVariable Long id) {
    // Return ProductResponse or an error response depending on application logic
}
~~~

In this example, the wildcard type does not disclose a concrete schema. Annotations describe the body for each response code separately. In real applications, consider using a clearer return type where possible so the compiler, readers, and Springdoc all understand the contract.

Do not use `@Schema(implementation = ...)` to force documentation to show a type that does not match the actual body. Annotations only document; they do not convert runtime objects into the declared schema.

## 13. Documenting Status Codes and Response Bodies Separately

`ResponseEntity` can return different status codes depending on logic. The generic type `T` is not enough to document all outcome branches.

For example, an endpoint might return:

| Status | Meaning | Body |
|---|---|---|
| 200 | Product found | `ProductResponse` |
| 404 | Not found | No body or `ApiError` depending on contract |
| 304 | Resource not modified | No body |
| 500 | System error | `ApiError` if published by the application |

Use `@ApiResponse` or `@ApiResponses` to publish important cases. If there are default or shared error responses, you can configure shared descriptions via the appropriate Springdoc mechanism.

You must also distinguish the status code actually returned from the status code documented. `@ApiResponse(responseCode = "404")` does not make the controller automatically return 404. The code must actually return that status via `ResponseEntity`, an exception handler, or an equivalent mechanism.

## 14. Verifying Unwrapping Rules in the Generated Document

After starting the application, download the OpenAPI JSON:

~~~http
GET /v3/api-docs
~~~

For each operation using `ResponseEntity` or `Optional`, check:

1. Whether the response schema is the actual payload type rather than an unnecessary Java wrapper.
2. Whether generic types inside `ResponseEntity` are preserved properly, especially `List`, `Map`, and DTOs.
3. Whether `ResponseEntity<Void>` avoids generating an incorrect body schema.
4. Whether status codes 200, 201, 204, 404, and error branches are published accurately.
5. Whether response headers such as `Location` are documented if clients rely on them.
6. Whether `Optional<T>` is resolved according to the capabilities of the version in use.
7. Whether `Optional.empty()` behaves at runtime in line with the published status and content.
8. Whether custom wrappers are preserved if they are genuinely part of the JSON payload.
9. Whether response examples match the schema and actual JSON.

You can test via integration tests for both data-present and data-absent cases. Check status codes, `Content-Type`, headers, body, and JSON structure. For custom wrappers or special serializers, inspect the serialized response directly.

Some common pitfalls:

| Symptom | Cause to check |
|---|---|
| Swagger UI displays `ResponseEntity` as an object | Type resolver does not recognize wrapper or return type declared raw |
| Body schema is an empty object | Generic type lost or DTO not resolved |
| `Optional` is documented as an unwanted object | Library version or model resolver does not support the wrapper type |
| `Optional.empty()` returns an unexpected status | Absent case not mapped to `ResponseEntity` or an exception |
| Documentation only shows 200 even though code returns 404 | Dynamic response codes not declared with `@ApiResponse` |
| `Location` header does not appear | Response header not documented in OpenAPI |
| Envelope stripped from schema | Custom configuration or annotations misdescribing actual payload |
| Schema declares a body but runtime returns none | `ResponseEntity<Void>`, status 204, or a response-building branch without a body |

## 15. Principles for Using ResponseEntity and Optional

When designing responses with Springdoc OpenAPI, follow these principles:

1. Use `ResponseEntity` to control HTTP status, headers, and body when dynamic decisions are needed.
2. Treat the generic type `T` as the payload for Springdoc to describe; verify unwrapping in your project version.
3. Use `ResponseEntity<Void>` or a response without `content` when an HTTP response has no body.
4. Use `Optional` at the service/repository layer to express results that may not be found.
5. Map `Optional.empty()` to an explicit status and body in the controller.
6. Do not assume `Optional.empty()` automatically means 404 or 204.
7. Avoid nesting `ResponseEntity<Optional<T>>` if the absent case can be expressed via status code.
8. Keep custom wrappers in the schema if they are part of the JSON payload.
9. Use `@ApiResponse` to document the status, schema, and headers of each branch.
10. Inspect OpenAPI JSON/YAML alongside runtime responses after changing return types.

`ResponseEntity` and `Optional` serve two different purposes: one controls HTTP responses, while the other expresses value presence in Java. Springdoc can unwrap supported wrappers to describe payloads, yet the API contract must still clearly publish status codes, headers, content, and behavior when data is absent. When controllers map these cases explicitly, OpenAPI documentation closely matches the responses clients actually receive.

