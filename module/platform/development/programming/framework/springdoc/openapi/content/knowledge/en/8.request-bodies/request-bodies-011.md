# Boundaries Between Input Structure Description and Runtime Data Validation

When describing request bodies with `springdoc-openapi`, two responsibilities must be distinguished: **publishing a data contract so clients understand how to send requests** and **validating actual data when the application receives a request**. The OpenAPI Schema describes the structure, data types, and constraints clients should follow. Spring MVC, Jackson, Bean Validation, and the business layer are what actually decide whether a request is accepted at runtime.

These two sides should align, yet they do not automatically substitute for each other. A schema might state a maximum string length of 50 characters while the controller has validation disabled; conversely, an application might reject a request due to a business rule that a schema cannot fully express. This lesson clarifies those layers and explains how to verify input contracts systematically.

## 1. Three layers of input processing

A JSON request passes through several steps before business logic executes:

1. **OpenAPI contract:** describes the request body, media types, schema, required fields, data types, enums, and publishable constraints.
2. **Binding and deserialization:** Spring MVC receives the HTTP request; Jackson converts JSON into a Java object. If JSON is malformed or types cannot be converted, the request may be rejected right here.
3. **Validation and business rules:** Bean Validation checks declared constraints; the service/domain layer checks rules depending on system state, permissions, existing data, or relationships across fields.

For example, a product creation API receives JSON with `name` and `price`:

~~~json
{
  "name": "Wireless Mouse",
  "price": 450000
}
~~~

OpenAPI can describe `name` as a non-empty string and `price` as a number greater than 0. When a request arrives:

- Jackson verifies whether the JSON can be deserialized into `CreateProductRequest`.
- Bean Validation verifies that `name` is not blank and `price` is positive if the controller enables validation.
- The service checks whether the product code is duplicated, whether the category exists, and whether the user has permission to create products.

Each layer answers a different question. The schema helps clients build valid contract-compliant requests; runtime validation protects the application; business logic decides whether the request is valid given the system's live state.

## 2. `RequestBody` and `Schema` in OpenAPI

In OpenAPI, an operation's request body is described by the Request Body Object. The `content` field specifies media types and corresponding schemas.

Condensed example:

~~~yaml
paths:
  /api/products:
    post:
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateProductRequest'
      responses:
        '201':
          description: Product created

components:
  schemas:
    CreateProductRequest:
      type: object
      required:
        - name
        - price
      properties:
        name:
          type: string
          minLength: 1
          maxLength: 120
        price:
          type: number
          minimum: 0
~~~

Two `required` concepts must be distinguished:

- **`requestBody.required`:** indicates whether the entire body must be sent.
- **`schema.required`:** lists the properties that must exist inside the object.

If `requestBody.required` is `true` while the schema lists no properties under `required`, the body must still be present even though individual fields are not marked mandatory. Conversely, properties listed in `schema.required` apply only when a body is sent.

A schema can describe:

| Element | Meaning |
|---|---|
| `type` | Data type such as `object`, `string`, `integer`, `number`, `boolean`, or `array` |
| `required` | List of mandatory properties in an object |
| `properties` | Definition of each object field |
| `enum` | Set of enumerated allowed values |
| `minLength` / `maxLength` | String length limits |
| `minimum` / `maximum` | Numeric value limits |
| `minItems` / `maxItems` | Array element count limits |
| `pattern` | Regular expression for strings |
| `format` | Format hint such as `date`, `date-time`, `email`, or `uuid` |
| `description` / `example` | Explanation and sample for clients |

These constraints describe the contract. Client tools can use them to render forms, generate code, or validate requests before sending. Whether the backend actually enforces all constraints depends on the implementation.

## 3. Using `@Schema` to describe the contract

The `@Schema` annotation belongs to `swagger-annotations` and supplies metadata for the OpenAPI document. It can be placed on a DTO or individual fields:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

import java.math.BigDecimal;

@Schema(
    name = "CreateProductRequest",
    description = "Data to create a new product"
)
public class CreateProductRequest {

    @Schema(
        description = "Product name",
        example = "Wireless Mouse",
        minLength = 1,
        maxLength = 120,
        requiredMode = Schema.RequiredMode.REQUIRED
    )
    private String name;

    @Schema(
        description = "Selling price, must be greater than 0",
        example = "450000",
        minimum = "0.01",
        requiredMode = Schema.RequiredMode.REQUIRED
    )
    private BigDecimal price;

    @Schema(
        description = "Short product description",
        example = "Wireless mouse for office use",
        maxLength = 500
    )
    private String description;

    // Default constructor, getters, and setters.
}
~~~

Attributes like `description`, `example`, `minLength`, `maxLength`, `minimum`, and `requiredMode` make documentation clearer. They do not inject validation logic into the controller.

For instance, declaring `maxLength = 120` on `@Schema` does not cause Spring to reject a 121-character string. If you want the backend to enforce that limit, add a runtime constraint like `@Size(max = 120)` and enable validation.

A DTO can combine `@Schema` and Bean Validation on the same field. This keeps the published contract and actual runtime rules side by side, making the code easier to read and maintain.

## 4. Bean Validation validates data at runtime

Bean Validation defines constraints such as `@NotNull`, `@NotBlank`, `@Size`, `@Min`, `@Max`, `@DecimalMin`, and `@Pattern`. With Spring Boot 3, standard annotations reside in the `jakarta.validation` namespace.

Example:

~~~java
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.math.BigDecimal;

public class CreateProductRequest {

    @NotBlank
    @Size(max = 120)
    private String name;

    @NotNull
    @DecimalMin(value = "0.01")
    private BigDecimal price;

    @Size(max = 500)
    private String description;

    // Default constructor, getters, and setters.
}
~~~

Common constraints:

| Constraint | Runtime condition |
|---|---|
| `@NotNull` | Value must not be null |
| `@NotBlank` | String must not be null and must contain at least one non-whitespace character |
| `@NotEmpty` | String or collection must not be empty |
| `@Size(min, max)` | String length or collection size within bounds |
| `@Min` / `@Max` | Numeric value within integer bounds |
| `@DecimalMin` / `@DecimalMax` | Numeric value within decimal bounds |
| `@Positive` / `@PositiveOrZero` | Value must be positive or non-negative |
| `@Email` | Validates string against provider email rules |
| `@Pattern` | String must match regular expression |
| `@Past` / `@Future` | Date or instant must be before or after current time |

Note that `@NotNull` and `@NotBlank` are not identical. `@NotNull` only forbids `null`; an empty string can still pass. `@NotBlank` is suitable when a field must carry actual non-whitespace content.

Similarly, `@Size(max = 120)` does not require the string to have content. If a field is both required and length-bounded, combine `@NotBlank` and `@Size`.

## 5. Triggering validation with `@Valid`

Having constraints on a DTO is not enough for Spring to validate every request automatically. For request bodies, mark the parameter with `@Valid`:

~~~java
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/products")
class ProductController {

    private final ProductService productService;

    ProductController(ProductService productService) {
        this.productService = productService;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ProductResponse create(
        @Valid @RequestBody CreateProductRequest request
    ) {
        return productService.create(request);
    }
}
~~~

With `@Valid`, Spring triggers Bean Validation on the object after the request body is deserialized. If a constraint fails, Spring MVC normally raises `MethodArgumentNotValidException` and returns HTTP 400 under the default error handling mechanism or the application's exception handler.

The project needs a Bean Validation provider. In Spring Boot, the standard dependency is:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Without a provider, annotations may still compile while runtime checks fail to execute as expected. Verify the validation dependency in your build configuration and test with a constraint-violating request.

`@Valid` and `@Validated` have related but distinct roles. `@Valid` is the standard annotation to trigger cascading validation on an object. `@Validated` is a Spring annotation usable for selecting validation groups or enabling method validation where appropriate. For standard request DTOs, `@Valid` is conventional and clear.

## 6. Comparing OpenAPI constraints with runtime constraints

Several Bean Validation annotations can be translated by `springdoc`/`swagger-core` into OpenAPI Schema constraints. For example, `@Size` can produce `minLength`/`maxLength`; `@DecimalMin` can produce `minimum` or `exclusiveMinimum`; `@NotNull` can affect `required`. Exact mapping behavior depends on library versions, validation namespaces, and project configuration.

| Intent | OpenAPI description | Runtime check |
|---|---|---|
| Field must be present | `required` in schema | `@NotNull` or `@NotBlank` depending on type |
| String up to 120 characters | `maxLength: 120` | `@Size(max = 120)` |
| Price greater than 0 | `minimum` or `exclusiveMinimum` | `@DecimalMin("0.01")` or appropriate constraint |
| Formatted email | `format: email` | `@Email` |
| Alphanumeric code | `pattern` | `@Pattern` |
| Date must be in the future | `format: date` or `date-time` | `@Future` |
| List of at most 10 items | `maxItems: 10` | `@Size(max = 10)` |

Do not assume every constraint translates perfectly. Some constraints are runtime-only, some are documentation-only, and some require custom schemas to express accurately.

After adding or updating annotations, call `/v3/api-docs` and inspect the actual JSON. If an exact contract is required, declare `@Schema` explicitly for metadata while still keeping the matching runtime constraints.

## 7. Required, nullable, and default values

These three concepts are often confused:

- **Required:** the property must appear in the request object.
- **Nullable:** whether the property is allowed to hold a `null` value.
- **Default:** the default value documented or applied when omitted, depending on implementation.

Example:

~~~yaml
CreateProductRequest:
  type: object
  required:
    - name
  properties:
    name:
      type: string
      minLength: 1
    description:
      type: string
      maxLength: 500
~~~

Here `name` is required. `description` may be omitted. Omitting `description` differs from sending `description: null`; how `null` is described depends on the OpenAPI version and generated schema.

OpenAPI 3.0 commonly uses `nullable: true` to permit `null`. OpenAPI 3.1 builds on JSON Schema and represents `null` types via JSON Schema `type` syntax. Read the `openapi` field at the top of your document and verify schemas per that exact version.

In Java, primitive types like `int` or `boolean` cannot hold `null`. If you need to distinguish a missing field from `0` or `false`, use wrapper types like `Integer` or `Boolean`. For creation requests, this lets validation clearly distinguish unsent data from Java default values.

Do not confuse `default` in OpenAPI with automatic backend assignment. A `default` advertised to clients does not necessarily cause Jackson or Spring to populate that value automatically. If the backend should apply a default, implement it in the DTO, binder, or service and test actual behavior.

## 8. Validation for nested objects

Request bodies frequently have nested structures. For example, an order with recipient details and a list of items:

~~~java
public class CreateOrderRequest {

    @NotNull
    @Valid
    private ShippingAddress shippingAddress;

    @NotEmpty
    @Valid
    private List<OrderItemRequest> items;

    // Getters and setters.
}

public class ShippingAddress {

    @NotBlank
    private String recipient;

    @NotBlank
    private String street;

    @NotBlank
    private String city;

    // Getters and setters.
}

public class OrderItemRequest {

    @NotBlank
    private String productId;

    @Min(1)
    private Integer quantity;

    // Getters and setters.
}
~~~

`@Valid` on nested properties instructs Bean Validation to cascade checks into child objects. Without `@Valid`, constraints inside `ShippingAddress` or `OrderItemRequest` may not execute when validating the parent object.

`@Schema` can describe object relationships via `properties` or `$ref` in `components.schemas`. However, showing nested fields in the schema does not mean child constraints are active at runtime. Verify both the OpenAPI structure and runtime validation behavior.

## 9. Cross-field rules and business rules

Many conditions cannot be fully expressed by single-field constraints. For example:

- `createdFrom` must be less than or equal to `createdTo`.
- `discount` must not exceed `subtotal`.
- When `paymentMethod = BANK_TRANSFER`, `bankAccount` must have a value.
- Delivery date must be after order date.
- A user can order at most up to currently available stock.

Class-level constraints or custom validators can handle cross-field rules. Simple example of class-level validation:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = DateRangeValidator.class)
public @interface ValidDateRange {
    String message() default "Start date must be before or equal to end date";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

The validator reads both fields and decides whether the object is valid. You can add `@Schema(description = "...")` to explain the rule in the OpenAPI contract, since OpenAPI Schema does not automatically infer custom Java validator logic.

Rules depending on system state belong in the business layer. For example, inventory changes over time and cannot be guaranteed by a static schema alone. The backend must check inventory at processing time and return an appropriate error response if insufficient.

## 10. Deserialization errors occur before Bean Validation

Not every invalid request triggers a Bean Validation error. Jackson must convert JSON into a Java object first. If deserialization fails, validation may not even be invoked.

JSON example:

~~~json
{
  "name": "Wireless Mouse",
  "price": "not-a-number"
}
~~~

If `price` is `BigDecimal`, Jackson cannot convert `"not-a-number"` into a number. Spring MVC typically returns HTTP 400 via `HttpMessageNotReadableException`.

Some common deserialization errors:

| Submitted data | Issue |
|---|---|
| Malformed JSON | Jackson cannot parse the document |
| `price` is a non-numeric string | Cannot convert to `BigDecimal` |
| `quantity` is an object instead of an integer | JSON type mismatches Java type |
| Date in wrong format | Cannot parse into `LocalDate`/`Instant` |
| Non-existent enum value | Cannot map string to enum |
| Missing primitive field | Java may receive defaults like `0` or `false`, depending on settings |

This is why deserialization errors must be distinguished from validation errors. Both can return HTTP 400, yet their causes and messages differ.

If Jackson is configured to ignore unknown properties, unrecognized fields may be silently skipped rather than failing the request. If configured to fail on unknown properties, the same request is rejected. Exact behavior depends on `ObjectMapper` configuration and Spring Boot version.

## 11. Standardizing validation error responses

Clients need to know why a request was rejected. The OpenAPI contract should describe common error responses such as 400, 401, 403, or 409 depending on the API.

Example error response:

~~~java
@Schema(name = "ValidationError")
public class ValidationErrorResponse {

    @Schema(example = "VALIDATION_FAILED")
    private String code;

    @Schema(example = "Invalid request")
    private String message;

    private List<FieldViolation> violations;

    // Getters and setters.
}

public class FieldViolation {

    @Schema(example = "name")
    private String field;

    @Schema(example = "must not be blank")
    private String message;

    // Getters and setters.
}
~~~

Responses can be documented in the controller:

~~~java
@Operation(summary = "Create product")
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Product created successfully"
    ),
    @ApiResponse(
        responseCode = "400",
        description = "Malformed JSON or data failed validation",
        content = @Content(
            schema = @Schema(implementation = ValidationErrorResponse.class)
        )
    )
})
@PostMapping
@ResponseStatus(HttpStatus.CREATED)
public ProductResponse create(
    @Valid @RequestBody CreateProductRequest request
) {
    return productService.create(request);
}
~~~

`@Schema` and `@ApiResponse` describe the error structure. They do not automatically turn `MethodArgumentNotValidException` into `ValidationErrorResponse`. To return a consistent format, the application must handle exceptions, typically via `@RestControllerAdvice`.

Example handler skeleton:

~~~java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ValidationErrorResponse> handleValidation(
        MethodArgumentNotValidException exception
    ) {
        // Convert field errors into a list of violations.
        ValidationErrorResponse body = buildValidationError(exception);

        return ResponseEntity.badRequest().body(body);
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ResponseEntity<ValidationErrorResponse> handleUnreadable(
        HttpMessageNotReadableException exception
    ) {
        // Return a message for unreadable JSON or data types.
        ValidationErrorResponse body = buildUnreadableError(exception);

        return ResponseEntity.badRequest().body(body);
    }
}
~~~

`buildValidationError` and `buildUnreadableError` are application-specific implementations. Avoid returning stack traces or internal details to clients. Error payloads should be clear enough to fix the request without leaking sensitive internals.

## 12. Validation groups and create/update flows

A single DTO is sometimes shared across multiple operations with different rules. For instance, when creating a product, `name` is required; when partially updating, `name` may be omitted.

Validation groups can be used:

~~~java
public interface Create {}
public interface Update {}

public class ProductRequest {

    @NotBlank(groups = Create.class)
    @Size(max = 120, groups = {Create.class, Update.class})
    private String name;

    @NotNull(groups = Create.class)
    @DecimalMin(value = "0.01", groups = {Create.class, Update.class})
    private BigDecimal price;

    // Getters and setters.
}
~~~

The controller can select a group via `@Validated`:

~~~java
@PostMapping
public ProductResponse create(
    @Validated(Create.class) @RequestBody ProductRequest request
) {
    return productService.create(request);
}

@PutMapping("/{id}")
public ProductResponse update(
    @PathVariable String id,
    @Validated(Update.class) @RequestBody ProductRequest request
) {
    return productService.update(id, request);
}
~~~

This is an illustrative example of validation groups. Check Spring MVC configuration, the `Default` group, and group sequences in real applications. OpenAPI specs usually need operation-appropriate request schemas; sharing one DTO across flows can make schemas struggle to reflect per-field requiredness accurately. When contracts differ substantially, separate DTOs for Create and Update are usually clearer.

## 13. What OpenAPI cannot guarantee

A schema is a structural specification, not a complete request verification program. Several rules cannot be represented or enforced uniformly across all clients:

- Rules depending on database state, inventory, transaction state, or current user data.
- Resource access rights and ownership.
- Complex cross-field conditions or custom logic.
- Rules depending on current time, time zones, or operational configuration.
- Constraints enforced by custom validators without a JSON Schema equivalent.
- Technical limits such as rate limits, quotas, or gateway request size caps.

For example, a schema can specify `quantity` as an integer greater than 0. Yet the schema cannot guarantee the buyer currently has enough credit/quota to order that quantity. The backend must check at processing time.

Nor should formats like `email`, `date`, or `uuid` be treated as proof that every client validates identically. Some tools only use formats for hints or UI rendering; the backend must still validate data according to application rules.

## 14. Verifying consistency between schema and runtime

After adding annotations, verify both sides.

**Inspect OpenAPI JSON:**

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Locate the operation's request body:

~~~bash
jq '.paths["/api/products"].post.requestBody' openapi.json
~~~

Locate the schema:

~~~bash
jq '.components.schemas.CreateProductRequest' openapi.json
~~~

Cross-check:

- Does the request body have the right media type?
- Is `requestBody.required` accurate?
- Does the schema have the right properties and data types?
- Does `required` list the necessary fields?
- Are `minLength`, `maxLength`, `minimum`, `enum`, and `format` accurate?
- Do descriptions and examples match real requests?

**Verify runtime:** send a valid request followed by requests violating each constraint. Example:

~~~powershell
# Valid request
curl.exe -i -X POST http://localhost:8080/api/products -H "Content-Type: application/json" -d '{"name":"Wireless Mouse","price":450000}'

# Blank name and negative price
curl.exe -i -X POST http://localhost:8080/api/products -H "Content-Type: application/json" -d '{"name":"   ","price":-10}'
~~~

Inspect status codes, response bodies, and server logs. If OpenAPI documents `maxLength` 120 yet the backend still accepts longer strings, `@Size` or `@Valid` may be missing. If the backend rejects a request the schema permits, treat it as an additional runtime constraint and consider documenting it in `description` or schema if expressible.

## 15. Common discrepancies

| Symptom | Cause to check |
|---|---|
| Swagger UI marks field required yet backend accepts missing value | OpenAPI `required` is descriptive only; check `@NotNull`/`@NotBlank`, `@Valid`, and DTO defaults |
| Backend rejects request yet schema omits constraint | Missing OpenAPI metadata or constraint is custom logic |
| `@Size` is on DTO yet overly long input is accepted | Validation not enabled, missing provider, or controller lacks `@Valid` |
| Mistyped JSON returns 400 without field errors | Jackson deserialization failed before Bean Validation |
| `null` field accepted unexpectedly | Missing `@NotNull` or wrong schema `required`/`nullable` |
| Missing field turns into `0` or `false` | DTO uses primitives; consider wrappers and validation |
| Schema has an example yet backend rejects or ignores values | Examples are illustrative only and do not configure binding or business logic |
| Child object validation does not run | Missing `@Valid` on nested property |
| Custom validator does not appear in OpenAPI | Add supplementary `@Schema` or `description` |
| Create and Update have different requiredness yet share one schema | Consider separate DTOs or operation-specific schemas |

## 16. Request body checklist

- [ ] Declared accurate media types and schema for the request body.
- [ ] Distinguished `requestBody.required` from `schema.required`.
- [ ] Fields have accurate `type`, `format`, `enum`, and `example`.
- [ ] Publishable limits are documented via `Schema`.
- [ ] Runtime constraints are declared with appropriate Bean Validation annotations.
- [ ] Controller enables validation with `@Valid` or an appropriate mechanism.
- [ ] Nested objects have `@Valid` in the right places.
- [ ] Cross-field and business rules are validated at the appropriate layer.
- [ ] Distinguished deserialization errors from Bean Validation errors.
- [ ] Error responses are documented in OpenAPI with matching implementations.
- [ ] Inspected JSON at `/v3/api-docs`.
- [ ] Tested valid requests, mistyped requests, and constraint-violating requests.

## 17. References

- [OpenAPI Specification – Request Body Object](https://spec.openapis.org/oas/latest.html#request-body-object)
- [OpenAPI Specification – Schema Object](https://spec.openapis.org/oas/latest.html#schema-object)
- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/)
- [Spring Framework – Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Framework – `@RequestBody` and message conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [springdoc-openapi – Official Documentation](https://springdoc.org/)

OpenAPI Schema tells clients the request structure and published constraints. Spring/Jackson/Bean Validation and the business layer are responsible for processing, validating, and deciding actual requests. Whenever you modify DTOs or annotations, verify both the OpenAPI JSON and runtime behavior so both sides continue describing the same contract.
