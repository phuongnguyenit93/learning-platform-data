# Why Documentation Annotations Do Not Automatically Enforce Bean Validation

When describing a request in OpenAPI, you may see constraints such as required fields, minimum lengths, maximum numeric values, or enum sets. springdoc-openapi can read annotations on DTOs and use them to build schemas for Swagger UI. However, **a schema only documents the contract**. It does not run data validation inside the Spring Boot application by itself.

For the server to actually reject invalid input, the application needs a Bean Validation provider, appropriate constraints, and a validation trigger in Spring's request processing flow. For example, having `@NotBlank` on a DTO without enabling validation on the controller does not mean requests will be rejected simply because OpenAPI displays that field as required.

This lesson distinguishes three commonly confused concerns: declaring constraints in Bean Validation, representing constraints in OpenAPI, and enforcing checks when requests enter Spring MVC. From there, you will see how to configure, test, and keep documentation aligned with runtime behavior.

## 1. Three Distinct Layers of Responsibility

A request can pass through three processing layers:

1. **Bean Validation metadata**: annotations like `@NotNull`, `@NotBlank`, `@Size`, `@Min`, and `@Pattern` declare conditions data must satisfy.
2. **OpenAPI schema**: springdoc reads part of that metadata and expresses it as `required`, `minLength`, `maximum`, `pattern`, or `enum` so integrators understand the contract.
3. **Runtime validation**: Spring invokes the Bean Validation provider at an enabled checkpoint; the provider evaluates constraints and returns violations if data is invalid.

~~~mermaid
flowchart TD
    A["DTO and Bean Validation annotations"] --> B["springdoc reads metadata"]
    B --> C["OpenAPI Schema"]
    C --> D["Swagger UI / client docs"]
    A --> E["Spring MVC binding"]
    E --> F{"Is validation enabled?"}
    F -->|Yes| G["Bean Validation provider"]
    F -->|No| H["Skip constraint checks"]
    G --> I{"Is data valid?"}
    I -->|Yes| J["Controller processes request"]
    I -->|No| K["Validation error"]
    H --> J
~~~

The diagram shows that springdoc and runtime validation read the same metadata yet perform two separate jobs. Generating a schema does not prove a provider is installed, the controller enables validation, or exceptions are handled properly.

| Component | Question Answered | Example |
|---|---|---|
| Bean Validation annotation | What conditions must the data satisfy? | @NotBlank, @Size(max = 100) |
| OpenAPI Schema | What limits must clients know? | type: string, maxLength: 100 |
| Runtime validation | Does the server reject invalid data? | @Valid and Validator |
| Exception handling | How does the server report validation errors? | HTTP 400 and error body |

## 2. Bean Validation Annotations Only Declare Constraints

Bean Validation provides a standard API to declare conditions on properties, parameters, return values, or entire objects. Example DTO:

~~~java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record CreateUserRequest(
    @NotBlank
    @Size(max = 80)
    String displayName,

    @NotNull
    @Email
    String email,

    @NotBlank
    @Size(min = 12, max = 128)
    String password
) {}
~~~

These annotations attach constraint metadata to data elements:

- `@NotNull` requires a non-null value.
- `@NotBlank` requires a non-null string with at least one non-whitespace character.
- `@Size` bounds the length/size of strings, collections, maps, or arrays.
- `@Email` checks that a value matches email format per the provider's definition.

At this point, the application has only declared conditions. Constraints do not run automatically whenever an object is instantiated or deserialized. A component calling the Bean Validation API—typically Spring MVC or method validation—must ask the provider to validate the object.

### Constraints Are Not Documentation Annotations

The annotations above belong to the Bean Validation package, such as:

- Spring Boot 3 / Jakarta: **jakarta.validation.constraints.NotBlank**.
- Spring Boot 2 / Java EE: **javax.validation.constraints.NotBlank**.

OpenAPI annotations like `@Schema` and `@Parameter` belong to swagger-annotations. They describe documentation. Never use `@Schema` in place of runtime constraints, and never treat the presence of `@NotBlank` as proof that Swagger UI validates requests automatically.

## 3. Installing a Bean Validation Provider

The application needs an implementation of the Bean Validation API. With Spring Boot, the standard dependency is **spring-boot-starter-validation**. This starter places both the API and the corresponding provider on the classpath.

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Gradle:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-validation")
}
~~~

When using Spring Boot dependency management, you normally do not need to specify the starter version manually. Use the version matching your project's Spring Boot line.

In Spring Boot 3, Bean Validation imports belong to the **jakarta.validation** namespace. Spring Boot 2 projects typically use **javax.validation**. Do not mix both namespaces in the same configuration if dependencies are incompatible.

If only the API annotations are present without a provider, metadata may still exist in class files and be read by doc tools, yet the application has no runtime implementation to execute constraints. Always verify the dependency/provider is actually present when checking runtime validation.

## 4. Enabling Request Body Validation with @Valid

In Spring MVC, the common way to trigger validation for a JSON DTO is placing **@Valid** on the **@RequestBody** parameter:

~~~java
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.ResponseStatus;

@RestController
public class UserController {

    @PostMapping("/api/users")
    @ResponseStatus(HttpStatus.CREATED)
    public UserResponse create(
        @Valid @RequestBody CreateUserRequest request
    ) {
        // Only execute business logic after binding and validation succeed
        return userService.create(request);
    }
}
~~~

Typical processing flow:

1. Spring receives the HTTP request.
2. `HttpMessageConverter` parses JSON and creates `CreateUserRequest`.
3. Because the parameter has `@Valid`, Spring asks the validator to check the object.
4. If any constraint fails, controller invocation stops and Spring raises a validation error.
5. If valid, the controller executes business logic.

For a request body with binding or validation errors, Spring MVC normally throws **MethodArgumentNotValidException** during argument validation. Applications can handle this exception to return a consistent error response.

### Omitting @Valid Can Leave Constraints Unenforced

~~~java
@PostMapping("/api/users")
public UserResponse create(
    @RequestBody CreateUserRequest request
) {
    return userService.create(request);
}
~~~

In this example, `@RequestBody` still parses JSON into the DTO, yet does not instruct Spring to run standard argument validation on the DTO. A blank string can reach the controller unless another check exists.

The fact that springdoc still reads `@NotBlank` and generates a schema with `minLength` or `required` does not change this runtime flow.

## 5. @Valid and Nested Validation

`@Valid` is also used to request recursive checks on nested objects. Consider a request with an address:

~~~java
public record AddressRequest(
    @NotBlank
    String city,

    @NotBlank
    @Size(max = 120)
    String street
) {}

public record CreateCustomerRequest(
    @NotBlank
    String name,

    @Valid
    @NotNull
    AddressRequest address
) {}
~~~

`@NotNull` on `address` requires the address object not to be null. `@Valid` on the same property instructs the validator to continue checking constraints inside `AddressRequest`. Without `@Valid`, `@NotNull` still checks `address`, yet `city` and `street` inside it will not cascade automatically through that property.

For lists of objects:

~~~java
public record CreateOrderRequest(
    @NotEmpty
    List<@NotNull @Valid OrderLineRequest> lines
) {}

public record OrderLineRequest(
    @NotBlank String productCode,
    @Min(1) @Max(100) int quantity
) {}
~~~

Container element constraints let you place constraints directly on individual elements. `@Valid` cascades into each element object; `@NotNull` forbids null elements; `@Min` and `@Max` bound `quantity`. Verify your Bean Validation provider version and collection binding behavior when using container element constraints.

## 6. Validation for Query, Path, and Header Parameters

Simple HTTP parameters such as `page`, `size`, IDs, or headers can also carry constraints:

~~~java
@GetMapping("/api/books")
public List<BookResponse> list(
    @RequestParam
    @Min(0)
    int page,

    @RequestParam
    @Min(1)
    @Max(100)
    int size
) {
    return bookService.list(page, size);
}
~~~

For constraints on method parameters to execute, the application needs a **method validation** mechanism appropriate to its Spring version along with a Bean Validation provider. Activation depends on version:

- In Spring versions prior to Spring MVC's built-in method validation support, proxy-based method validation is typically used with `@Validated` on the class or appropriate bean.
- Starting with Spring Framework 6.1, Spring MVC includes built-in method validation support for controllers. When using this built-in support, avoid placing `@Validated` at the controller level if doing so routes methods through AOP method validation instead of MVC's built-in mechanism.

Do not copy `@Validated` configurations from another project without checking the Spring version. Identify which method validation mechanism is active, then test actual errors using out-of-range `page` or `size` values.

### Distinguishing @Valid and @Validated

| Annotation | Typical Role |
|---|---|
| @Valid | Triggers cascaded validation per Jakarta Bean Validation; does not select validation groups |
| @Validated | Spring annotation capable of selecting validation groups and participating in method validation |

`@Valid` does not replace `@Min` or `@Max`. It directs the validator into the object; concrete constraints must still be declared on properties or parameters. Likewise, `@Validated` creates no data limits unless matching constraints exist.

## 7. Validation Groups and OpenAPI Schemas

A DTO sometimes follows different rules for creation versus updates. Bean Validation supports **validation groups**:

~~~java
public interface Create {}
public interface Update {}

public record SaveBookRequest(
    @NotBlank(groups = {Create.class, Update.class})
    String title,

    @NotNull(groups = Create.class)
    UUID catalogId
) {}
~~~

The controller can choose the group at the validation point:

~~~java
@PostMapping("/api/books")
public BookResponse create(
    @Validated(Create.class) @RequestBody SaveBookRequest request
) {
    return bookService.create(request);
}

@PutMapping("/api/books/{bookId}")
public BookResponse update(
    @PathVariable UUID bookId,
    @Validated(Update.class) @RequestBody SaveBookRequest request
) {
    return bookService.update(bookId, request);
}
~~~

Validation groups decide which constraints execute per operation. A standard OpenAPI schema describes one data shape and does not automatically convey all group rules chosen by runtime context. If a property is required on create yet optional on update, a shared schema cannot express both contracts cleanly.

Options to handle this:

- Split `CreateBookRequest` and `UpdateBookRequest` when the two contracts differ in meaning.
- Use separate schemas per operation when differences must be documented explicitly.
- Add descriptions and examples explaining context-dependent rules.
- Inspect the schema generated by springdoc because group handling varies by version and integration; never assume every group automatically becomes a separate schema.

For public APIs, separate DTOs for create and update are usually clearer than asking clients to deduce validation groups from a single shared schema.

## 8. Bean Validation and What OpenAPI Can Express

springdoc can read several constraints and translate them into Schema Object keywords. Exact mapping capabilities depend on springdoc, swagger-core, Jakarta/Javax Validation versions, and configuration.

| Bean Validation | OpenAPI Schema Typically Expressible | Limitations to Understand |
|---|---|---|
| @NotNull | required or non-null constraint per OpenAPI version | required says property must appear; nullability is a separate concept |
| @NotEmpty | required and emptiness bounds matching data type | Differs from @NotBlank for whitespace-only strings |
| @NotBlank | required and/or minLength in certain mappings | minLength cannot reject all whitespace-only strings |
| @Size(min, max) on String | minLength, maxLength | Character-counting details can vary by implementation |
| @Size(min, max) on Collection/Array | minItems, maxItems | Requires accurate `items` schema |
| @Size(min, max) on Map | minProperties, maxProperties | Cannot express all custom key/value constraints |
| @Min / @Max | minimum / maximum | Check numeric type and inclusive bounds |
| @DecimalMin / @DecimalMax | minimum / maximum or exclusive bounds | Inclusivity flag must match |
| @Positive / @PositiveOrZero | minimum or exclusiveMinimum | Depends on version and numeric type |
| @Pattern | pattern | Java regex and JSON Schema regex are not completely identical |
| @Email | format email or equivalent description | Provider rules may be broader than email format |
| @Past / @Future | Some temporal metadata if supported | Current time is dynamic, not a simple static bound |

Mappings in the table show expressible capabilities, not a guarantee that every version generates the exact same schema. Always open `/v3/api-docs` to inspect your project's output.

### `required` Does Not Mean `nullable`

In OpenAPI, **required** indicates whether a property must appear in the object. **Nullable** or null-type representation indicates whether the property can hold a `null` value; syntax depends on the OpenAPI version.

For example:

- A property may be required to appear and disallowed from being null.
- A property may be optional to appear yet disallowed from being null if present.
- A property may be required to appear while allowing null, if the contract permits it.

`@NotNull` validates that the post-binding value is non-null. If JSON omits the property and Jackson leaves the Java value as null, the constraint normally fails when validation runs. Never look at the `required` keyword in OpenAPI alone and assume the server definitely checks it; test at runtime.

### `@NotBlank` Is Not `minLength`

`@NotBlank` rejects null, empty strings, and whitespace-only strings. A string schema with `minLength: 1` still accepts a string containing a single space. Hence, mapping to `minLength` is an approximation, not a substitute for provider semantics.

Likewise, `@Email` and `@Pattern` can enforce stricter or different checks than how a client validator interprets `format` or `pattern`. When a rule matters, explain it in `description`, provide a matching pattern/schema if feasible, and test against the server.

## 9. @Schema Does Not Invoke a Validator

The **@Schema** annotation belongs to OpenAPI. It can add `type`, `format`, `description`, `example`, `allowableValues`, `minimum`, `maximum`, `minLength`, `maxLength`, `pattern`, and `requiredMode`.

~~~java
public record CreateProductRequest(
    @Schema(
        description = "Product name, cannot be blank",
        example = "Mechanical Keyboard",
        minLength = 1,
        maxLength = 120,
        requiredMode = Schema.RequiredMode.REQUIRED
    )
    String name
) {}
~~~

The schema above adds documentation metadata only. If runtime must reject blank names, you need Bean Validation constraints and active validation:

~~~java
public record CreateProductRequest(
    @NotBlank
    @Size(max = 120)
    @Schema(
        description = "Product name, cannot be blank",
        example = "Mechanical Keyboard",
        maxLength = 120,
        requiredMode = Schema.RequiredMode.REQUIRED
    )
    String name
) {}

@PostMapping("/api/products")
public ProductResponse create(
    @Valid @RequestBody CreateProductRequest request
) {
    return productService.create(request);
}
~~~

In this example, `@NotBlank` and `@Size` are runtime constraints; `@Schema` refines how the contract is presented; `@Valid` tells Spring to validate the DTO. All three are related, yet none can replace another.

With `@Schema(minLength = 1)` alone, documentation shows `minLength` while Bean Validation has no constraint for the server to enforce. Conversely, with `@NotBlank` alone, the server checks properly while OpenAPI may not capture the non-whitespace rule fully.

## 10. How Are Validation Errors Turned into HTTP Responses?

When validation fails, Spring MVC does not proceed into normal controller logic. The application must decide how to format error responses for clients.

You can use `@RestControllerAdvice` to map exceptions into a unified structure:

~~~java
public record FieldViolation(
    String field,
    String message
) {}

public record ApiValidationError(
    String code,
    List<FieldViolation> violations
) {}

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public ApiValidationError handleValidation(
        MethodArgumentNotValidException exception
    ) {
        List<FieldViolation> violations =
            exception.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error -> new FieldViolation(
                    error.getField(),
                    error.getDefaultMessage()
                ))
                .toList();

        return new ApiValidationError(
            "VALIDATION_FAILED",
            violations
        );
    }
}
~~~

This is a simple example; real applications must also handle binding errors, method validation errors, and business errors using appropriate structures. Avoid exposing stack traces or internal validator details to clients.

springdoc does not automatically know every error response produced by `@RestControllerAdvice` in all setups. Document error responses with `@ApiResponse`/`@ApiResponses` or a shared customization mechanism:

~~~java
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Product created successfully"
    ),
    @ApiResponse(
        responseCode = "400",
        description = "Invalid request data",
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = ApiValidationError.class)
        )
    )
})
@PostMapping("/api/products")
public ProductResponse create(
    @Valid @RequestBody CreateProductRequest request
) {
    return productService.create(request);
}
~~~

Documenting `400` in OpenAPI shows clients the error shape. It does not activate validation and will not make the controller return `400` unless runtime actually raises and handles the corresponding error.

## 11. Testing to Prove Validation Actually Runs

A schema showing `minLength` or `required` is not enough to prove the server rejects bad requests. Test the endpoint with real requests or MockMvc.

MockMvc example:

~~~java
@WebMvcTest(ProductController.class)
@Import(ApiExceptionHandler.class)
class ProductControllerValidationTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    ProductService productService;

    @Test
    void rejectsBlankName() throws Exception {
        mockMvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"name": "   "}
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("VALIDATION_FAILED"));

        verifyNoInteractions(productService);
    }
}
~~~

This test verifies runtime behavior:

- Request body is parsed into the DTO.
- `@Valid` triggers Bean Validation.
- `@NotBlank` catches a whitespace-only name.
- The server returns HTTP 400 via the exception handler.
- The service is not invoked when input is invalid.

Also include valid-case tests to confirm valid requests reach the service and return expected results. For query/path parameters, test method validation separately because its activation mechanism can differ from request bodies.

### Verifying OpenAPI Documentation Independently

Use integration tests or fetch JSON from `/v3/api-docs` to check:

- Does the schema include the expected `description`, `required`, `minLength`, `maxLength`, or numeric bounds?
- Does the request body point to the right component schema?
- Is the 400 response documented with `ApiValidationError`?
- Do property names match JSON after Jackson serialization?

Two test groups prove two different facts:

| Check | What Is Proven |
|---|---|
| Test `/v3/api-docs` | OpenAPI documentation is generated with the expected schema |
| MockMvc sending invalid input | Server enforces validation and returns errors |
| MockMvc sending valid input | Valid requests proceed through the controller |

Never use the outcome of one group to assume the other holds.

## 12. Custom Constraints and OpenAPI Representation Limits

Bean Validation allows creating custom constraints. For example, a customer code must follow a business rule:

~~~java
@Documented
@Constraint(validatedBy = CustomerCodeValidator.class)
@Target({FIELD, METHOD, PARAMETER, ANNOTATION_TYPE, TYPE_USE, RECORD_COMPONENT})
@Retention(RUNTIME)
public @interface ValidCustomerCode {
    String message() default "Invalid customer code";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

Validator:

~~~java
public class CustomerCodeValidator
        implements ConstraintValidator<ValidCustomerCode, String> {

    private static final Pattern CODE =
        Pattern.compile("CUS-[A-Z0-9]{6}");

    @Override
    public boolean isValid(
            String value,
            ConstraintValidatorContext context) {
        return value == null || CODE.matcher(value).matches();
    }
}
~~~

DTO:

~~~java
public record CreateCustomerRequest(
    @ValidCustomerCode
    @Schema(
        description = "Customer code formatted as CUS- followed by six alphanumeric characters",
        example = "CUS-A1B2C3",
        pattern = "^CUS-[A-Z0-9]{6}$"
    )
    String customerCode
) {}
~~~

The provider executes `ValidCustomerCode` via `CustomerCodeValidator`. springdoc cannot deduce regex rules from arbitrary Java logic inside the validator. `@Schema(pattern = ...)` supplies an approximate documentation description, yet both definitions must be kept aligned through reviews and tests.

The validator above intentionally treats null as valid. If `customerCode` must also have a value, combine `@NotNull` or `@NotBlank`; format checks and presence checks are separate conditions.

For cross-field constraints, such as end date after start date, standard schemas cannot fully express comparisons between two properties. You can use a class-level constraint for enforcement and document the rule in `description` or operation docs.

## 13. Jackson, Binding, and Validation Are Separate Steps

Before Bean Validation checks an object, Spring must construct it from HTTP data. Jackson or `HttpMessageConverter` reads JSON; Bean Validation validates the post-binding object.

Examples:

- Malformed JSON or wrong types can fail during deserialization before constraints ever run.
- Syntactically valid JSON with a blank `name` deserializes into the DTO, after which `@NotBlank` catches the violation.
- An omitted property may receive null or a default depending on Java types, constructors, Jackson, and settings.
- `@JsonProperty`, `@JsonIgnore`, or custom deserializers can alter the data passed to the validator.

Therefore, when a request is rejected, distinguish parse/binding errors from Bean Validation errors. When a request passes validation, that alone does not guarantee it meets every business rule; domain and database checks may still be necessary.

## 14. Common Pitfalls

| Symptom | Common Cause | Resolution |
|---|---|---|
| Swagger UI marks field required yet server accepts blank input | Schema only or validation not enabled | Add provider, constraint, and `@Valid`/`@Validated` properly |
| `@NotBlank` fails to reject whitespace-only strings | Controller does not trigger validation or provider is missing | Check dependency and run runtime request tests |
| `@Valid` on request body yet error format is non-standard | Missing corresponding exception handler | Handle `MethodArgumentNotValidException` and binding errors |
| Nested DTO is not validated | Missing `@Valid` on property/container element | Add cascaded validation |
| Query `@Min` does not run | Method validation not configured for Spring version | Check Spring version and method validation mechanism |
| Schema shows `minLength` yet whitespace can still be sent | `minLength` does not equal `@NotBlank` | Document semantics clearly, use a pattern if suitable, and test server |
| Custom constraint missing from schema | springdoc does not analyze custom validator logic | Add `@Schema` or `OpenApiCustomizer` |
| Create and Update share schema yet differ in requiredness | Validation groups not modeled as two separate contracts | Split DTOs/schemas per operation or document explicitly |
| Runtime error response missing from OpenAPI | Missing `@ApiResponse` or customizer | Declare error responses per operation or globally |
| Wrong JSON type yields parse error instead of validation error | Deserialization failed before Bean Validation | Check `HttpMessageConverter`/Jackson and classify exceptions |

## 15. Workflow for Aligning Bean Validation and OpenAPI

When adding or editing constraints, proceed step by step:

1. **Define business rules:** which fields are required, what bounds apply, and do rules depend on operation or group?
2. **Declare runtime constraints:** use Bean Validation annotations or custom validators.
3. **Enable validation:** apply `@Valid`, `@Validated`, or method validation appropriate to the binding point and Spring version.
4. **Document schemas:** verify springdoc maps constraints properly; add `@Schema` if needed.
5. **Document errors:** declare matching error responses and error body formats.
6. **Test runtime:** send both valid and invalid inputs, verifying status codes and error payloads.
7. **Test docs:** inspect `/v3/api-docs` and reconcile schemas against DTOs, constraints, and real JSON.

Changing a constraint can affect clients, servers, and existing data at the same time. Assess compatibility before tightening bounds, altering enums, or turning optional properties into required ones.

## Conclusion

Bean Validation annotations declare data rules; springdoc can read part of that metadata to build OpenAPI schemas; Spring MVC and the Bean Validation provider actually execute runtime checks. `@Schema` only describes the contract, whereas `@Valid`/`@Validated` paired with a provider and constraints activates validation in the processing pipeline. Independently verify OpenAPI JSON, valid requests, and invalid requests so documentation, server behavior, and error responses stay aligned.
