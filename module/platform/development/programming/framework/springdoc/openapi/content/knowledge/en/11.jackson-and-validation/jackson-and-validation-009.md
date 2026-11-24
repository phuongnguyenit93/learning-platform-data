# Validation Groups and Limits of Automatic Documentation Inference

Spring Boot can validate request data with Bean Validation, while springdoc-openapi reads metadata from controllers, DTOs, Jackson, and related annotations to build schemas. These two mechanisms work together so documentation describes many constraints, yet they hold different responsibilities: Bean Validation enforces conditions at runtime; OpenAPI publishes the contract for clients and integration tools.

When a DTO uses multiple validation groups, cross-field checks, custom validators, or Jackson serialization alterations, automatically generated documentation may not reflect full runtime behavior. This lesson explains how to structure validation groups, how springdoc infers common constraints, and when intentional schema descriptions are necessary.

## 1. Bean Validation and OpenAPI Schemas Solve Two Different Problems

Bean Validation checks objects after data has been bound into Java. OpenAPI Schemas describe the public shape and constraints of data exchanged over HTTP.

| Component | Role | Example |
| --- | --- | --- |
| Jackson | Reads JSON into Java objects or serializes objects to JSON | Renaming properties, ignoring fields, formatting dates |
| Bean Validation | Checks objects against declared constraints | @NotBlank, @Size, @Positive |
| Validation group | Selects the subset of constraints to run in a validation pass | OnCreate, OnUpdate |
| springdoc-openapi | Reads metadata and generates OpenAPI Schemas/Operations | type, required, minLength, pattern |
| OpenAPI validator/client | Interprets the published contract | Validating payloads or generating clients |

For example, a DTO has a `name` field with `@NotBlank`. When the controller triggers validation, Bean Validation rejects empty or whitespace-only strings. Springdoc can reflect that constraint in the schema, yet the generated schema is merely a description for clients; it does not run Bean Validation on behalf of the server.

Conversely, metadata in `@Schema` such as `description` or `example` does not create validation by itself. If the documentation states a value must exceed 0 while the DTO lacks constraints and the service performs no checks, the server can still accept negative numbers.

## 2. Common Bean Validation Constraints

Popular constraint annotations can be read by springdoc and swagger-core to add bounds to schemas. Exact mapping depends on version and configuration; always verify the generated JSON/YAML.

| Constraint | Runtime Meaning | Typically Representable in Schema |
| --- | --- | --- |
| @NotNull | Value must not be null | Required property or non-null constraint |
| @NotBlank | String must contain a non-whitespace character | required and/or minLength; whitespace-only may not be fully expressed |
| @NotEmpty | String, collection, map, or array must not be empty | minLength: 1 or minItems: 1 depending on type |
| @Size(min, max) | Bounds string/collection/map/array size | minLength/maxLength or minItems/maxItems |
| @Min, @Max | Integer bounds | minimum/maximum |
| @DecimalMin, @DecimalMax | Decimal bounds | minimum/maximum and exclusivity where applicable |
| @Positive, @PositiveOrZero | Number must be positive or non-negative | minimum/exclusiveMinimum |
| @Negative, @NegativeOrZero | Number must be negative or non-positive | maximum/exclusiveMaximum |
| @Pattern | String must match regular expression | pattern |
| @Email | Value has email format per validator | format: email or equivalent description |
| @Past, @Future | Date/instant must be before or after current time | May require description; schemas do not evaluate runtime clock |

Example DTO:

~~~java
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;

public record CreateProductRequest(
    @NotBlank
    @Size(max = 80)
    String name,

    @NotNull
    @DecimalMin("0.01")
    BigDecimal price,

    @NotBlank
    @Pattern(regexp = "^[A-Z]{3}$")
    String currency
) {}
~~~

On Spring Boot 3 and later, Bean Validation uses the `jakarta.validation` package. Applications need a provider, typically included via the `spring-boot-starter-validation` dependency. On Spring Boot 2, the corresponding annotations live under `javax.validation`.

When a controller receives the DTO, enable validation:

~~~java
@PostMapping
ProductView create(@Valid @RequestBody CreateProductRequest request) {
    return productService.create(request);
}
~~~

Without `@Valid` or an equivalent validation trigger, constraints on the DTO may not execute at the request entry point as expected. Check both the validation dependency and how the controller enables validation.

## 3. Understanding `required`, `nullable`, and Omitted Values

`required` in OpenAPI and `@NotNull` are related but not strictly synonymous.

- `required` in an object schema states that the property must appear in the JSON.
- `nullable` states whether the property value may be `null`; representation depends on the OpenAPI version.
- `@NotNull` checks that the post-binding Java value is not null. When a JSON property is omitted, a reference field typically receives null and the constraint can fail.
- `@JsonInclude` can cause Jackson to omit a property when serializing responses; this affects whether the property appears in returned JSON.

Example:

~~~java
public record ProfileRequest(
    @NotNull String displayName,
    String nickname
) {}
~~~

`displayName` must have a value; `nickname` may be absent. However, distinguishing an omitted property from a property with `null` depends on Jackson binding, Java types, constructors, and configuration. If an API requires three separate states (omitted, null, value), model that explicitly rather than relying solely on a nullable `String`.

Do not assume every property with `@NotNull` is always listed under `required` in every springdoc version. Open `/v3/api-docs`, inspect `components.schemas`, and compare against actual payloads. When an explicit contract is needed, use `@Schema(requiredMode = Schema.RequiredMode.REQUIRED)` or split request/response models appropriately.

Example explicit metadata declaration:

~~~java
@Schema(
    description = "Display name, required when creating a profile",
    requiredMode = Schema.RequiredMode.REQUIRED
)
@NotBlank
String displayName
~~~

`requiredMode` controls only OpenAPI documentation. `@NotBlank` is what enforces runtime data validation.

## 4. What Is a Validation Group?

Validation groups let you apply different constraint sets depending on the operation. A single DTO might be used for both creation and updates, while certain fields are required in only one scenario.

When no `groups` are specified on a constraint, it belongs to the `Default` group. Custom groups can be declared using interfaces:

~~~java
public interface OnCreate {}
public interface OnUpdate {}
~~~

Assign groups to individual constraints:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Null;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

public class ProductCommand {

    @Null(groups = OnCreate.class)
    @NotNull(groups = OnUpdate.class)
    private Long id;

    @NotBlank(groups = {OnCreate.class, OnUpdate.class})
    @Size(max = 80, groups = {OnCreate.class, OnUpdate.class})
    private String name;

    @NotNull(groups = OnCreate.class)
    @Positive(groups = {OnCreate.class, OnUpdate.class})
    private Integer quantity;

    // Getters and setters
}
~~~

Meaning:

- On creation, `id` must be null, `name` must be non-blank, and `quantity` must be positive.
- On update, `id` must be present; `name` remains required; if `quantity` is sent, it must be positive per the active constraint.
- Constraints without an explicit group belong to `Default` and run only when `Default` is selected or included in an active group sequence.

Groups do not activate automatically just by being declared on a DTO. The controller or validator caller must specify which group to execute.

## 5. Activating Groups with @Validated

In Spring MVC, you can place `@Validated` on a request body parameter to specify a group:

~~~java
@RestController
@RequestMapping("/api/products")
class ProductController {

    @PostMapping
    ProductView create(
            @RequestBody @Validated(OnCreate.class) ProductCommand command) {
        return productService.create(command);
    }

    @PutMapping("/{id}")
    ProductView update(
            @PathVariable Long id,
            @RequestBody @Validated(OnUpdate.class) ProductCommand command) {
        return productService.update(id, command);
    }
}
~~~

`@Validated` is a Spring annotation that can specify validation hints/groups. Jakarta Validation's `@Valid` normally triggers the `Default` group when used on a request body. When specific groups are needed, use `@Validated` with the matching group and test on your running Spring version.

Do not confuse `@Validated` on a parameter with `@Validated` on a class/service. When placed on a class, the annotation can also enable method validation through Spring proxies. Method validation and request-body validation are two different integration points; place annotations where validation needs to run.

For method validation, groups can be declared on methods or types per Spring's validation mechanism. If your project uses Spring Framework 6.1 or later, read that version's method validation guide because MVC's built-in validation support behaves differently from traditional AOP proxies.

## 6. Group Sequences and Validation Order

`@GroupSequence` lets you enforce an order across groups. If an earlier group reports errors, subsequent groups in the sequence do not execute.

~~~java
public interface BasicChecks {}
public interface BusinessChecks {}

@GroupSequence({
    ProductCommand.class,
    BasicChecks.class,
    BusinessChecks.class
})
public class ProductCommand {
    @NotBlank(groups = BasicChecks.class)
    private String name;

    @Positive(groups = BusinessChecks.class)
    private Integer quantity;

    // Getters and setters
}
~~~

When redefining the `Default` group sequence on a class, the sequence must include the class itself to represent the class's `Default` constraints. Do not put `Default.class` in the sequence in place of the class. Groups in the sequence are evaluated sequentially; if one group fails, later groups are skipped.

Group sequences are useful when basic structural checks should run before expensive or conditional checks. However, a sequence does not become an OpenAPI condition. springdoc cannot infer a separate schema solely from validation execution ordering.

## 7. Nested Validation and Group Conversion

DTOs can contain nested objects. `@Valid` triggers cascaded validation to check child objects:

~~~java
public class AddressCommand {
    @NotBlank
    private String city;

    @NotBlank
    private String street;

    // Getters and setters
}

public class CustomerCommand {
    @NotBlank
    private String name;

    @Valid
    @NotNull
    private AddressCommand address;

    // Getters and setters
}
~~~

To switch groups when descending into a nested object, use `@ConvertGroup`:

~~~java
public class CustomerCommand {
    @Valid
    @ConvertGroup(from = OnCreate.class, to = AddressCreateChecks.class)
    private AddressCommand address;
}
~~~

`@ConvertGroup` takes effect only at cascaded validation sites marked with `@Valid`. Group conversion helps when a child object has a different validation lifecycle from its parent.

OpenAPI schemas typically represent nested structures via `properties` and `$ref`. They can reflect static constraints on child objects, yet they do not necessarily know that a controller switched groups with `@ConvertGroup`. Therefore, do not assume documentation automatically produces distinct schema variants for each nested group.

## 8. Class-Level Constraints and Cross-Field Rules

Some conditions do not belong to a single field. For example, an end date must follow a start date, or either email or phone must be provided. You can build a class-level constraint with `ConstraintValidator`:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = ValidDateRangeValidator.class)
public @interface ValidDateRange {
    String message() default "End date must be after start date";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}

public class BookingRequest {
    @NotNull
    private LocalDate startDate;

    @NotNull
    private LocalDate endDate;

    // Getters and setters
}

public class ValidDateRangeValidator
        implements ConstraintValidator<ValidDateRange, BookingRequest> {

    @Override
    public boolean isValid(
            BookingRequest value,
            ConstraintValidatorContext context) {
        if (value == null
                || value.getStartDate() == null
                || value.getEndDate() == null) {
            return true;
        }
        return value.getEndDate().isAfter(value.getStartDate());
    }
}
~~~

The validator returns true when insufficient data is present to compare because `@NotNull` is responsible for reporting missing fields. If you want errors tied to a specific property, configure `ConstraintValidatorContext` to build a property node.

springdoc can read common field-level constraint annotations, but it cannot infer arbitrary algorithms inside a custom `ConstraintValidator`. In the example above, the schema sees two required dates yet cannot deduce the relationship that `endDate` must be after `startDate` merely from the validator class name.

Publish cross-field rules in descriptions or business documentation, and test them at runtime. With OpenAPI 3.1, certain rules can be expressed using JSON Schema `if`/`then`/`else`, `dependentRequired`, or composition. Even then, value comparisons between two dates may still require prose descriptions or external validation beyond standard schema keywords.

## 9. Limits of Automatic Inference in springdoc

Springdoc builds OpenAPI by analyzing controllers, Java types, generics, OpenAPI annotations, validation metadata, and parts of Jackson annotations. This is static metadata inference; it does not run the whole application to trace every data path.

The following cases usually need manual review:

| Case | Why Automatic Inference Is Limited | How to Handle |
| --- | --- | --- |
| Different validation groups per operation | One DTO has multiple constraint sets; component schemas may be shared | Split request DTOs per action or customize schemas per operation |
| @GroupSequence | Expresses validation execution order rather than a new data structure | Document runtime rules clearly; test each group |
| Custom ConstraintValidator | Logic may query databases, clocks, or services | Add descriptions, custom schemas if expressible, and server tests |
| Class-level/cross-field constraints | Rule spans multiple properties | Document relationships on operations/schemas; consider JSON Schema composition |
| User- or state-dependent conditions | Requires runtime context and data outside the payload | Document business errors and responses; do not assume schemas suffice |
| Jackson custom serializer/deserializer | Wire format may differ from Java type | Declare explicit schemas or register a ModelConverter |
| @JsonView or per-endpoint views | One DTO may yield multiple JSON shapes depending on view | Use separate DTOs or configure schemas per operation |
| @JsonInclude | Properties may be omitted when null/empty | Verify actual JSON responses and required/nullable |
| Computed getter values | JSON values may not match stored fields | Document public properties and verify output |
| Custom converters for enums/dates/value objects | Parse/serialize rules may follow custom conventions | Use @Schema type/format/example and test converters |

The OpenAPI specification must describe the observable HTTP contract, not all internal Java details. Whenever Java types or metadata fail to mirror the wire format, adjust the model or add explicit OpenAPI metadata.

## 10. Jackson Can Alter JSON Shape

Jackson controls how objects are read and written. Several annotations directly affect schemas:

| Annotation/Setting | JSON Impact | What to Check in OpenAPI |
| --- | --- | --- |
| @JsonProperty | Renames properties or sets read/write access | Property names and readOnly/writeOnly |
| @JsonIgnore | Skips properties when reading/writing per configuration | Whether property should appear in schema |
| @JsonInclude | Omits null/empty values on serialization | Property may be absent in responses |
| @JsonFormat | Formats dates, times, or numbers | type/format/example match actual strings |
| @JsonUnwrapped | Flattens nested properties onto parent | Schema matches flattened JSON structure |
| @JsonView | Selects property subsets per operation view | Each operation may need a distinct schema |
| @JsonTypeInfo | Adds discriminator or selects subtype | oneOf/discriminator and actual payloads |
| Custom serializer/deserializer | Fully customizes wire representation | Needs explicit schema or custom converter |

For example, a password accepted only on account creation and never returned:

~~~java
public record CreateAccountRequest(
    String username,
    @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
    String password
) {}
~~~

A write-only property differs from a field completely ignored with `@JsonIgnore`. It can appear in requests yet never appears in responses. If sharing a single DTO for both requests and responses, confirm springdoc marks `writeOnly` properly; splitting `CreateAccountRequest` and `AccountResponse` is usually clearer.

Example `@JsonInclude`:

~~~java
public class AccountResponse {
    private String id;

    @JsonInclude(JsonInclude.Include.NON_NULL)
    private String nickname;
}
~~~

When `nickname` is null, Jackson can omit the property from the JSON response. This differs from a property always present with a `null` value. For clarity, mark the property optional and verify how nullability is represented for your OpenAPI version.

## 11. Using One DTO for Multiple Operations Can Create Ambiguous Docs

Sharing one DTO across create and update seems to reduce code, yet can produce an ambiguous contract:

- Create requires `name` and `quantity`.
- Update requires `id`; some fields may be optional.
- Validation groups pick different constraints.
- Responses may hide passwords or include read-only fields.

If both operations reference the same `ProductCommand` component, OpenAPI usually has one shared schema component. One component cannot simultaneously require `name` in one operation and make it optional in another without special composition.

Cleaner design using two DTOs:

~~~java
public record CreateProductRequest(
    @NotBlank
    @Size(max = 80)
    String name,

    @NotNull
    @Positive
    Integer quantity
) {}

public record UpdateProductRequest(
    @NotBlank
    @Size(max = 80)
    String name,

    @Positive
    Integer quantity
) {}
~~~

The controller publishes two separate request schemas:

~~~java
@PostMapping
ProductView create(@Valid @RequestBody CreateProductRequest request) {
    return productService.create(request);
}

@PatchMapping("/{id}")
ProductView update(
        @PathVariable Long id,
        @Valid @RequestBody UpdateProductRequest request) {
    return productService.update(id, request);
}
~~~

When create and update contracts differ, dedicated DTOs help clients understand requirements clearly and avoid relying on whether tools interpret validation groups identically. Validation groups remain useful for domain objects or deliberate reuse, yet are not always ideal for every public request model.

## 12. When You Need Per-Operation Schema Customization

If a DTO must be shared for internal reasons while each operation needs a different schema, use `@Parameter`/`@Schema` or an OpenAPI customizer to publish separate request bodies. Example configuring `requestBody` via annotations:

~~~java
@Operation(
    summary = "Create product",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        content = @Content(
            schema = @Schema(implementation = CreateProductRequest.class)
        )
    )
)
~~~

With customizers, you can target operations by path/method and swap the referenced schema. Be careful not to mutate a shared component unexpectedly. When schemas differ across operations, create separate components per contract or use inline schemas where appropriate.

`@Schema(requiredMode = ...)`, `description`, `example`, `allowableValues`, and composition keywords only add OpenAPI metadata. They never replace Bean Validation, Jackson, or business logic. Every schema adjustment must be verified at `/v3/api-docs` after starting the application.

## 13. Testing Validation and Documentation per Operation

When adding or editing constraints, verify all three layers:

1. Runtime: send valid and invalid payloads to confirm the intended group's constraints run.
2. Serialization: inspect actual JSON before and after Jackson processing.
3. Contract: verify schemas in `/v3/api-docs` and Swagger UI match fields, types, required flags, formats, and bounds.

Example integration test with MockMvc:

~~~java
@WebMvcTest(ProductController.class)
class ProductControllerValidationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void rejectsBlankName() throws Exception {
        mockMvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"name":"   ","price":100}
                    """))
            .andExpect(status().isBadRequest());
    }
}
~~~

This example illustrates runtime verification for default constraints; add dedicated tests for every validation group and operation. Schema tests can fetch the OpenAPI JSON and assert that expected properties and keywords are present.

When using groups, maintain a test matrix:

| Operation | Group | Test Payload |
| --- | --- | --- |
| POST create | OnCreate | null id, valid name, positive quantity |
| POST create | OnCreate | non-null id or missing quantity |
| PUT update | OnUpdate | non-null id, valid name |
| PUT update | OnUpdate | missing id or invalid name |

Do not test only the happy path. Selecting the wrong group can prevent constraints from running or cause unintended ones to run.

## 14. Checklist for Limits of Automatic Inference

Before publishing documentation, ask yourself:

- Does the controller trigger validation on the right parameter?
- Which group is selected for each operation?
- Do constraints belong to `Default` or a custom group?
- Are group sequences or group conversions in use?
- Are there custom validators or cross-field conditions?
- Does Jackson rename, ignore, format, or transform any properties?
- Is the DTO shared between requests and responses?
- Does the generated schema match actual JSON?
- Are there rules depending on databases, users, time, or business state?
- Are rules that cannot be expressed in schema documented on the operation or in supplementary docs?

If the answer shows the schema cannot capture all logic, publish the structurally verifiable parts in OpenAPI and describe the rest in prose, error codes, or business docs. Never ship a schema that looks exact yet contradicts runtime behavior.

## 15. Validation and OpenAPI Design Workflow

When designing DTOs and documentation:

1. Define request/response models and the actual wire format produced by Jackson.
2. Place baseline constraints on fields and assign validation groups per operation if needed.
3. Use `@Valid` for cascading; use `@Validated` to select the right group.
4. Use `@GroupSequence` only when execution order matters and short-circuiting on error is understood.
5. Place custom/cross-field validation at the class or service level and explain the rule to clients.
6. Verify springdoc reflects static constraints accurately; do not assume it understands custom logic.
7. If a DTO serves multiple differing contracts, consider splitting request/response DTOs or defining per-operation schemas.
8. Reconcile OpenAPI JSON/YAML against runtime tests and real payloads.

Springdoc reduces manual documentation work by inferring metadata from code, yet contract quality still relies on the metadata provided by the application. Validation groups, custom validators, and Jackson customizations are areas to verify proactively so clients see the exact data shapes and limits enforced by the server.

## References

- [Jakarta Bean Validation – Specification](https://jakarta.ee/specifications/bean-validation/)
- [Spring Framework – Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Framework – Validation Groups](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Jackson Annotations – GitHub](https://github.com/FasterXML/jackson-annotations)
- [OpenAPI Specification – Schema Object](https://spec.openapis.org/oas/latest.html#schema-object)
- [springdoc-openapi – Documentation](https://springdoc.org/)
