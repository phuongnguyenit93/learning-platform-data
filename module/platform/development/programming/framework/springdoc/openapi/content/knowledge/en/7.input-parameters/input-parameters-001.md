# @Parameter and Its Relationship with Spring Binding Annotations

## 1. Two Layers of Responsibility in Parameter Declaration

When building a REST API with Spring Boot, controllers receive data from HTTP requests through binding annotations such as `@PathVariable`, `@RequestParam`, `@RequestHeader`, and `@CookieValue`. These annotations tell Spring where to extract values from, which Java type to convert them to, and whether the parameter is required.

OpenAPI needs to describe those same parameters so that clients know how to send data. Springdoc OpenAPI reads Spring metadata and controller signatures to generate Parameter Objects in the documentation. The **`@Parameter`** annotation adds descriptive information that Spring bindings cannot fully express, such as business meaning, examples, constraints, serialization styles, or display behavior.

The two annotation layers are related but serve different purposes:

- **Spring binding annotations** determine how the application receives and processes values when a request arrives.
- **Swagger/OpenAPI `@Parameter`** describes the parameter in the OpenAPI contract so humans and tools understand how to call the API.

`@Parameter` does not read query strings itself, does not bind values into Java variables, and does not replace validation. Conversely, `@RequestParam` can bind a complete value without necessarily explaining its business meaning clearly to documentation readers.

For example, `@RequestParam(name = "status")` helps Spring retrieve the `status` query parameter; `@Parameter(description = "Product status")` helps Swagger UI explain that field to clients.

## 2. Parameter Object in OpenAPI

In OpenAPI, an operation parameter is described using a **Parameter Object**. Commonly used attributes include:

| Attribute | Meaning |
|---|---|
| `name` | Name of the parameter in the HTTP request |
| `in` | Location: `path`, `query`, `header`, or `cookie` |
| `description` | Explanation of purpose and usage |
| `required` | Whether the parameter is mandatory |
| `deprecated` | Marks the parameter as deprecated |
| `schema` | Data type, format, and constraints |
| `example` / `examples` | Illustrative values |
| `style` / `explode` | How the value is serialized into the URL or header |
| `allowReserved` | Allows reserved characters in query parameters according to OpenAPI rules |

A parameter is identified by the **name + in** pair. Therefore, a query parameter `id` and a header `id` are two distinct parameters.

OpenAPI mandates that a path parameter must always have `required: true`. Query, header, and cookie locations can be required or optional depending on the API contract. Documentation must accurately reflect the controller's behavior.

Example of an operation with a query parameter:

~~~yaml
paths:
  /products:
    get:
      summary: Search products
      parameters:
        - name: keyword
          in: query
          description: Keyword to search in product names
          required: false
          schema:
            type: string
          example: keyboard
      responses:
        "200":
          description: Success
~~~

Springdoc generates the equivalent part from controllers and annotations. When detailed description control is needed, `@Parameter` can be placed directly on the method parameter.

## 3. Which Locations Do Spring Binding Annotations Map To?

Springdoc typically infers the parameter location from Spring MVC binding annotations:

| Spring Annotation | OpenAPI Location | How Clients Pass Data |
|---|---|---|
| `@PathVariable` | `path` | Part of the URL path |
| `@RequestParam` | `query` | Query string after `?` |
| `@RequestHeader` | `header` | HTTP request header |
| `@CookieValue` | `cookie` | Request cookie |
| `@ModelAttribute` | Binds fields from request parameters; add `@ParameterObject` to document each field as a query parameter | Object fields bound from request parameters |
| `@RequestBody` | Request Body Object, not a Parameter Object | Data in the HTTP body |
| `@RequestPart` | Part of the request body, commonly used for multipart | Part of a multipart body |

Example:

~~~java
@GetMapping("/products/{productId}")
public ProductResponse findProduct(
    @PathVariable("productId") Long productId,
    @RequestParam(name = "includeInactive", required = false) boolean includeInactive,
    @RequestHeader(name = "X-Request-Id", required = false) String requestId,
    @CookieValue(name = "locale", required = false) String locale
) {
    return productService.find(productId, includeInactive, requestId, locale);
}
~~~

Springdoc can identify:

- `productId` as a path parameter.
- `includeInactive` as a query parameter.
- `X-Request-Id` as a header parameter.
- `locale` as a cookie parameter.

Explicitly declaring the name via `name` or `value` avoids relying on Java variable names and compiler configuration. If the parameter name in the contract differs from the Java variable name, inspect the generated OpenAPI JSON to ensure clients send the exact expected name.

## 4. Adding Descriptions with @Parameter

The `@Parameter` annotation belongs to the `io.swagger.v3.oas.annotations` package. It is typically placed right before the binding annotation on the same method parameter.

Example:

~~~java
@RestController
@RequestMapping("/api/products")
public class ProductController {

    @GetMapping("/{productId}")
    @Operation(summary = "Get product details")
    public ProductResponse findProduct(
        @Parameter(
            description = "Unique identifier of the product",
            example = "42"
        )
        @PathVariable("productId")
        Long productId,

        @Parameter(
            description = "Whether to include discontinued products",
            example = "false"
        )
        @RequestParam(
            name = "includeInactive",
            required = false,
            defaultValue = "false"
        )
        boolean includeInactive
    ) {
        return productService.find(productId, includeInactive);
    }
}
~~~

Here, the Spring binding annotation determines the location and runtime behavior. `@Parameter` adds the description and example for the documentation. Springdoc combines information from both sources to generate the parameter in OpenAPI.

Some commonly used attributes of `@Parameter`:

~~~java
@Parameter(
    name = "keyword",
    description = "Search in product name and code",
    example = "mechanical keyboard",
    required = false,
    deprecated = false
)
@RequestParam(name = "keyword", required = false)
String keyword
~~~

There is no need to redeclare every attribute if Springdoc already infers it accurately. Add details that genuinely help clients understand usage, and keep the name, location, and required status consistent with the binding annotation.

## 5. Relationship with Each Binding Annotation

### 5.1. @PathVariable: Parameters in the Path

`@PathVariable` binds a variable in the URL path to a Java parameter:

~~~java
@GetMapping("/orders/{orderId}")
public OrderResponse getOrder(
    @Parameter(
        description = "Order identifier",
        example = "ORD-2026-001"
    )
    @PathVariable("orderId")
    String orderId
) {
    return orderService.findById(orderId);
}
~~~

OpenAPI represents this parameter with `in: path` and `required: true`. A path parameter is part of the URL structure, so it cannot arbitrarily be marked as optional in OpenAPI.

If there are two URL forms, such as `/orders` and `/orders/{orderId}`, describe them as separate paths or appropriate operations. Do not use `required = false` in documentation to simulate an optional path segment.

### 5.2. @RequestParam: Query Parameters

`@RequestParam` binds data from the query string:

~~~java
@GetMapping("/products")
public List<ProductResponse> search(
    @Parameter(
        description = "Search keyword",
        example = "keyboard"
    )
    @RequestParam(name = "keyword", required = false)
    String keyword,

    @Parameter(
        description = "Maximum number of records to return",
        example = "20"
    )
    @RequestParam(name = "size", defaultValue = "20")
    @Min(1) @Max(100)
    int size
) {
    return productService.search(keyword, size);
}
~~~

Spring treats `@RequestParam` as required by default if neither `required = false` nor `defaultValue` is specified. When `defaultValue` is present, Spring treats the parameter as optional and applies the default value if the parameter is missing or empty according to binding rules.

Important distinctions:

- Spring's `defaultValue` affects runtime behavior.
- `@Parameter`'s `example` only illustrates a sample value in documentation.
- `description` explains the meaning without changing the bound value.

If the API accepts multiple values, such as `?status=ACTIVE&status=INACTIVE`, you can use `List<String>` or `List<ProductStatus>`. In that case, specify the appropriate serialization with `style` and `explode` if tooling does not infer it correctly.

~~~java
@Parameter(
    description = "Statuses to filter by; parameter can be repeated",
    style = ParameterStyle.FORM,
    explode = Explode.TRUE
)
@RequestParam(name = "status", required = false)
List<ProductStatus> statuses
~~~

With `style = form` and `explode = true`, the standard representation is:

~~~http
GET /api/products?status=ACTIVE&status=INACTIVE
~~~

In the example, `ParameterStyle`, `Explode`, and `ParameterIn` belong to the `io.swagger.v3.oas.annotations.enums` package. If the contract uses a comma-separated string, such as `status=ACTIVE,INACTIVE`, choose the corresponding serialization style and verify the generated documentation.

### 5.3. @RequestHeader: Parameters in HTTP Headers

`@RequestHeader` binds a value from an HTTP header:

~~~java
@GetMapping("/reports")
public ReportResponse getReport(
    @Parameter(
        description = "Correlation ID to trace requests across services",
        example = "req-8f21a6"
    )
    @RequestHeader(name = "X-Request-Id", required = false)
    String requestId
) {
    return reportService.create(requestId);
}
~~~

Springdoc can describe this parameter with `in: header`. The header name in the documentation must match the name sent by the client.

For authentication headers like `Authorization: Bearer ...`, describe them using an OpenAPI **Security Scheme** and **Security Requirement**. Avoid documenting an authentication token as an arbitrary header on individual operations if the API actually uses a shared Bearer authentication mechanism.

### 5.4. @CookieValue: Parameters from Cookies

`@CookieValue` binds a cookie value to a Java parameter:

~~~java
@GetMapping("/preferences")
public PreferenceResponse getPreferences(
    @Parameter(
        description = "UI language code stored in cookie",
        example = "vi"
    )
    @CookieValue(name = "locale", required = false)
    String locale
) {
    return preferenceService.find(locale);
}
~~~

OpenAPI represents a cookie parameter with `in: cookie`. State clearly whether the cookie is required, where it is created, and its expiration or usage if clients need to know. Sensitive cookie data should not be placed in public examples.

## 6. Object Parameters with @ModelAttribute and @ParameterObject

A search form may contain many fields. Instead of declaring all of them as individual parameters, Spring MVC allows binding them into an object using `@ModelAttribute`:

~~~java
public class ProductSearchCriteria {

    private String keyword;
    private ProductStatus status;
    private BigDecimal minPrice;
    private BigDecimal maxPrice;

    // Getters and setters
}
~~~

Controller:

~~~java
@GetMapping("/products")
public List<ProductResponse> search(
    @ModelAttribute ProductSearchCriteria criteria
) {
    return productService.search(criteria);
}
~~~

Spring MVC binds request parameters to the object's properties. For GET endpoints, properties are typically passed via query string. However, a Java object does not automatically clarify how each property should appear in OpenAPI.

Springdoc supports the **`@ParameterObject`** annotation to expand the object into individual query parameters:

~~~java
@GetMapping("/products")
public List<ProductResponse> search(
    @ParameterObject
    @ModelAttribute ProductSearchCriteria criteria
) {
    return productService.search(criteria);
}
~~~

The documentation can display the `keyword`, `status`, `minPrice`, and `maxPrice` fields as separate query parameters. `@Schema` can be used on the criteria properties to describe the type, example, and meaning of each field.

`@ParameterObject` is a hint for Springdoc's documentation generation; `@ModelAttribute` still handles runtime binding. Check the Springdoc version in use and the generated JSON, especially for nested objects, collections, or custom properties.

## 7. Distinguishing @Parameter from @RequestBody and @RequestPart

Not all input data is a Parameter Object. In OpenAPI, path, query, header, and cookie are parameter locations. The request body is described separately using a **Request Body Object**.

Example:

~~~java
@PostMapping("/products")
public ProductResponse create(
    @RequestBody CreateProductRequest request
) {
    return productService.create(request);
}
~~~

Springdoc infers the request body from `@RequestBody` and the DTO type. Additional descriptions can be added with **`@io.swagger.v3.oas.annotations.parameters.RequestBody`**, or the DTO schema can be documented with `@Schema`.

For multipart uploads, `@RequestPart` also describes part of the request body with its appropriate media type, not a query parameter.

Do not use `@Parameter` to describe a JSON body as if clients send it in the query string. Choosing the right OpenAPI object type ensures Swagger UI renders the correct input form and content type.

## 8. When to Explicitly Declare in, name, or parameters?

Normally, Springdoc can infer `name` and `in` from Spring binding annotations. You can declare them explicitly in `@Parameter` when you need to supplement or adjust the documentation:

~~~java
@Parameter(
    name = "X-Tenant-Id",
    in = ParameterIn.HEADER,
    description = "Tenant identifier for the request",
    required = true,
    example = "tenant-01"
)
@RequestHeader(name = "X-Tenant-Id")
String tenantId
~~~

In this example, `@RequestHeader` determines that the value is read from the header; `@Parameter` explicitly describes the name, location, and requirement in OpenAPI. Both declarations must match.

Parameters can also be declared at the operation level via `@Operation(parameters = ...)` when documenting a common parameter or one that does not appear directly in the controller signature:

~~~java
@Operation(
    summary = "Get report",
    parameters = {
        @Parameter(
            name = "X-Client-Version",
            in = ParameterIn.HEADER,
            description = "Client version calling the API",
            required = false,
            example = "2.4.0"
        )
    }
)
@GetMapping("/reports")
public ReportResponse getReport() {
    return reportService.create();
}
~~~

Operation-level declarations only add documentation. They do not automatically create a mechanism to read the header in Spring. If the application actually needs that value, there must be a binding annotation, filter, interceptor, or suitable runtime mechanism. Avoid documenting a parameter that the server neither reads nor processes.

Do not declare the same parameter multiple times with conflicting `name`, `in`, or `required` values. If a parameter is already inferred from the method signature, prefer adding the description directly on that parameter.

## 9. Customizing Schema, Examples, and Constraints

`@Parameter` can be combined with `@Schema` to describe the parameter's data type:

~~~java
@Parameter(
    description = "Number of products to retrieve",
    schema = @Schema(
        type = "integer",
        minimum = "1",
        maximum = "100",
        defaultValue = "20",
        example = "20"
    )
)
@RequestParam(name = "size", defaultValue = "20")
@Min(1) @Max(100)
int size
~~~

In the example:

- `@RequestParam(defaultValue = "20")` sets the runtime value when the client omits `size`.
- `@Min(1)` and `@Max(100)` are backend validation constraints.
- `@Schema` provides the schema and constraint information in OpenAPI.
- `@Parameter.description` explains the purpose of the parameter.

Springdoc can infer some constraints from Bean Validation, though support depends on the version and configuration. Inspect the generated schema to avoid discrepancies between documentation and actual validation.

Examples are purely illustrative data. If `example` is set differently from `defaultValue`, clients need to understand that the example value is not necessarily what the server applies automatically.

## 10. Hiding or Deprecating Parameters

`@Parameter(hidden = true)` can be used to exclude a parameter from the generated OpenAPI documentation when appropriate:

~~~java
@GetMapping("/internal-report")
public ReportResponse getInternalReport(
    @Parameter(hidden = true)
    @RequestParam(name = "legacyMode", required = false)
    boolean legacyMode
) {
    return reportService.create(legacyMode);
}
~~~

Hiding a parameter only affects the generated documentation. Spring can still bind and process that parameter if a client sends it in a request. Hiding is not a security measure or access control mechanism.

If a parameter is still supported but discouraged, mark it with `deprecated = true` and document the replacement:

~~~java
@Parameter(
    description = "Legacy parameter; use responseFormat instead",
    deprecated = true
)
@RequestParam(name = "format", required = false)
String format
~~~

When removing a parameter, consider client compatibility, announce a transition period, and update the API contract according to the project's versioning policy.

## 11. Verifying the Documentation Generated by Springdoc

After declaring the controller, do not assume the documentation is correct just by looking at the annotations. Access the default OpenAPI JSON endpoint:

~~~http
GET /v3/api-docs
~~~

Locate the corresponding operation and verify:

- Path parameters have `in: path` and `required: true`.
- Query parameters have the right name, type, default, and `required` flag.
- Headers and cookies have the right locations.
- Descriptions, examples, and schema constraints are complete.
- Array parameters have the right `style`/`explode`.
- Request bodies appear under `requestBody`, not mistakenly as parameters.
- No duplicate parameters or mismatched locations exist.

Common issues:

| Symptom | Cause to Check |
|---|---|
| Incorrect parameter name | Missing `name`/`value` in Spring annotation or configured name diverges from `@Parameter` |
| Parameter marked with wrong `required` | `required` in binding annotation does not match `@Parameter`; `defaultValue` exists but documentation does not reflect it |
| Invalid path parameter | Missing corresponding variable in path or incorrect `required` description |
| Header appears as query | Wrong Spring binding annotation used or incorrect `in` override |
| Search object not expanded into fields | Missing `@ParameterObject` or object structure unsupported by the Springdoc version |
| Request body appears as parameter | Wrong annotation used or incorrect input data modeling |
| Examples or constraints not displayed | Annotation placed on wrong target or library version does not support the attribute |

Combine checking the OpenAPI document with integration tests that send real requests. A parameter documented as optional while the controller still returns 400 when missing indicates that the contract and runtime are out of sync.

## 12. Guidelines for Using @Parameter in a Project

When describing input parameters with Springdoc, apply these guidelines:

1. Use Spring binding annotations to define the data source and runtime behavior.
2. Use `@Parameter` to add descriptions, examples, schemas, deprecated status, or serialization styles.
3. Keep `name`, `in`, and `required` in OpenAPI consistent with the controller.
4. Use `@ParameterObject` when you want to expand a search object into individual query parameters.
5. Use a Request Body Object to describe `@RequestBody` and `@RequestPart`.
6. Use a security scheme for shared authentication mechanisms instead of declaring tokens as regular parameters.
7. Inspect the OpenAPI JSON/YAML and verify runtime behavior after modifying annotations.

Spring binding annotations tell the application where to receive data; `@Parameter` tells clients how to send that data and what it means. When both layers remain consistent, Springdoc can generate a clear API contract, Swagger UI displays appropriate input forms, and integrating clients encounter fewer errors when calling endpoints.

