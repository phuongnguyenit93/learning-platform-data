# @Min, @Max, @Pattern, and Value-Range Constraints

APIs frequently need to constrain input data according to business rules: quantities must fall within a range, prices must exceed a threshold, product codes must match a pattern, or tag lists must not exceed a maximum count. In Spring Boot, **Jakarta Bean Validation** annotations declare these constraints directly on DTOs and controller parameters. **springdoc-openapi** can read many of these constraints to populate the corresponding bounds in the OpenAPI schema.

For an accurate API contract, three parts must stay aligned:

1. **Runtime constraints:** Bean Validation actually rejects invalid input.
2. **OpenAPI schema:** the documentation accurately states numeric bounds, lengths, string patterns, and required fields.
3. **Error responses:** clients receive an understandable status code and error payload when a constraint is violated.

Adding annotations to a DTO alone is not enough if the application never triggers validation. Likewise, documenting limits in OpenAPI does not make the server validate inputs automatically.

## 1. Categories of Value-Range Constraints

Bean Validation provides standard constraints for numbers, strings, and collections. Common constraints include:

| Annotation | Meaning | Example |
| --- | --- | --- |
| **@Min(value)** | Value must be greater than or equal to threshold | Minimum quantity is 1 |
| **@Max(value)** | Value must be less than or equal to threshold | Maximum page number is 100 |
| **@DecimalMin(value)** | Decimal value must be greater than or equal to threshold; supports inclusive = false | Price must be greater than 0 |
| **@DecimalMax(value)** | Decimal value must be less than or equal to threshold; supports inclusive = false | Percentage must not exceed 100 |
| **@Positive** | Value must be strictly greater than 0 | Order quantity |
| **@PositiveOrZero** | Value must be greater than or equal to 0 | Non-negative balance |
| **@Negative**, **@NegativeOrZero** | Value must be negative or non-positive | Downward adjustment |
| **@Digits(integer, fraction)** | Limits integer digits and fractional digits | Price with up to 8 integer digits and 2 decimals |
| **@Size(min, max)** | Limits string length or collection/map/array element count | Name 3–80 characters long |
| **@Pattern(regexp)** | String must match regular expression | Code formatted as ABC-123456 |
| **@NotNull**, **@NotBlank**, **@NotEmpty** | Checks presence or non-empty content | Required field |

**@Min** and **@Max** support integral types plus **BigInteger** and **BigDecimal**; they do not support **float** or **double**. For decimal thresholds, use **@DecimalMin** and **@DecimalMax** for exact representation. Avoid float or double for monetary amounts; **BigDecimal** is normally preferred.

**@Size** applies to **CharSequence**, collections, maps, and arrays; it does not constrain numeric values. To bound product quantities, use **@Min**/**@Max**; to bound the character count of a product code, use **@Size** or **@Pattern**.

The three presence constraints differ in scope: **@NotNull** rejects only null; **@NotBlank** targets strings and rejects null, empty strings, or whitespace-only strings; **@NotEmpty** rejects null and empty values on strings, collections, maps, or arrays. Choose the constraint matching the data type and business intent.

Some providers such as Hibernate Validator offer extended constraints like **@Range**. That constraint is not part of standard Jakarta Bean Validation. If using an extension, check your installed provider and verify whether springdoc reflects it in the schema; for contracts shared across providers, prefer standard constraints.

## 2. @Min and @Max for Numeric Bounds

**@Min** and **@Max** define inclusive bounds including the threshold values. Example:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

public record InventoryRequest(
    @NotNull
    @Min(1)
    @Max(5000)
    Integer quantity
) {}
~~~

Valid values include 1 and 5000. Values such as 0, negative numbers, or 5001 are rejected. **@Min** and **@Max** allow null by themselves; combine **@NotNull** if the field is required.

When bounding a query parameter:

~~~java
import java.util.List;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@GetMapping("/api/products")
List<ProductView> findProducts(
    @RequestParam(defaultValue = "1")
    @Min(1) @Max(100)
    int page,

    @RequestParam(defaultValue = "20")
    @Min(1) @Max(100)
    int size
) {
    return productService.find(page, size);
}
~~~

This example allows page from 1 to 100 and size from 1 to 100. Default values are provided by **@RequestParam(defaultValue = ...)** when clients omit the parameter. Bean Validation checks the value after Spring converts the query string to the Java type.

## 3. @DecimalMin, @DecimalMax, and @Digits for Decimals

For currency, rates, or fractional quantities, use **BigDecimal** and decimal constraints:

~~~java
import java.math.BigDecimal;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotNull;

public record PriceRequest(
    @NotNull
    @DecimalMin(value = "0.01")
    @DecimalMax(value = "999999.99")
    @Digits(integer = 6, fraction = 2)
    BigDecimal price
) {}
~~~

In this example:

- Minimum price is 0.01 and maximum is 999999.99.
- **@DecimalMin** and **@DecimalMax** are inclusive by default.
- **@Digits(integer = 6, fraction = 2)** allows at most 6 integer digits and 2 fractional digits.
- **@NotNull** requires clients to supply a value.

To exclude the boundary itself, set **inclusive = false**:

~~~java
@DecimalMin(value = "0", inclusive = false)
BigDecimal balance
~~~

This requires balance to be strictly greater than 0. **@DecimalMin** and **@DecimalMax** express fractional thresholds that **@Min** and **@Max** cannot clearly represent.

## 4. @Positive and Sign Constraints

When business rules simply require positive or non-negative values, sign constraints express intent more clearly:

~~~java
import java.math.BigDecimal;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.PositiveOrZero;

public record ShippingRequest(
    @NotNull
    @Positive
    BigDecimal weightKg,

    @NotNull
    @PositiveOrZero
    BigDecimal insuranceFee
) {}
~~~

**weightKg** must be greater than 0; **insuranceFee** can be 0 but not negative. Similarly, **@Negative** requires a value below 0 and **@NegativeOrZero** also permits 0.

These constraints do not replace **@NotNull**: most value-range constraints treat null as valid so they can compose cleanly with presence constraints. For required fields, add **@NotNull**.

## 5. @Pattern for Codes and Formatted Strings

**@Pattern** validates string content using a regular expression. For example, an SKU consisting of three uppercase letters, a hyphen, and six digits:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

public record ProductCodeRequest(
    @NotBlank
    @Pattern(
        regexp = "^[A-Z]{3}-[0-9]{6}$",
        message = "Product code must match ABC-123456"
    )
    String sku
) {}
~~~

Some examples:

| Input | Result |
| --- | --- |
| ABC-123456 | Valid |
| XYZ-000001 | Valid |
| abc-123456 | Invalid due to lowercase letters |
| AB-123456 | Invalid due to missing letter |
| ABC-12345 | Invalid due to missing digit |
| ABC-123456-extra | Invalid due to trailing suffix |

Bean Validation uses Java regex matching against the entire string. Meanwhile, JSON Schema/OpenAPI `pattern` has substring-search semantics; therefore, use **^** and **$** when you want to express whole-string matching as above. Stick to regex syntax compatible with OpenAPI tools and client generators; some Java-specific regex features may not be supported by other tools.

**@Pattern** applies only to **CharSequence** and accepts null. If the field is required, combine it with **@NotBlank** or **@NotNull**. **@NotBlank** also rejects empty strings and whitespace-only strings.

Avoid overly complex regexes for data like phone numbers, addresses, or personal names when real formats vary widely. Pick practical business rules, document them clearly, and test boundary values.

## 6. Combining Multiple Constraints on a DTO

A single field often needs several conditions together. Example product creation DTO:

~~~java
import java.math.BigDecimal;
import java.util.List;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record CreateProductRequest(
    @NotBlank
    @Size(min = 3, max = 80)
    String name,

    @NotBlank
    @Pattern(regexp = "^[A-Z]{3}-[0-9]{6}$")
    String sku,

    @NotNull
    @DecimalMin("0.01")
    @DecimalMax("999999.99")
    @Digits(integer = 6, fraction = 2)
    BigDecimal price,

    @NotNull
    @Min(0)
    @Max(100000)
    Integer stock,

    @Size(max = 10)
    List<
        @NotBlank
        @Pattern(regexp = "^[A-Z0-9_-]{2,20}$")
        String
    > tags
) {}
~~~

This DTO specifies:

- Name is non-blank and 3 to 80 characters long.
- SKU matches the pattern.
- Price is a decimal between 0.01 and 999999.99 with up to 6 integer digits and 2 decimal digits.
- Stock is between 0 and 100000.
- The tag list has at most 10 items; each item is non-blank and follows its own format.

A constraint placed on a generic type argument such as **List<@Pattern(...) String>** is a container element constraint. It checks each item in the list, whereas **@Size(max = 10)** checks the number of items.

If tags may be omitted, **@Size** still accepts null. If the API requires at least one item, add **@NotNull** and **@Size(min = 1, max = 10)**. If an empty list is allowed while blank items are forbidden, keep **@Size(max = 10)** alongside the element constraint.

## 7. Enabling Validation in Spring Boot

### Validating Request Bodies with @Valid

For DTOs parsed from JSON, place **@Valid** on **@RequestBody** so Spring runs Bean Validation:

~~~java
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProductController {

    private final ProductService productService;

    ProductController(ProductService productService) {
        this.productService = productService;
    }

    @PostMapping("/api/products")
    ResponseEntity<ProductView> create(
        @Valid @RequestBody CreateProductRequest request
    ) {
        ProductView result = productService.create(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(result);
    }
}
~~~

The application needs a Bean Validation implementation. In Spring Boot, the standard dependency is:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

On Spring Boot 3 and later, import constraints from the **jakarta.validation** namespace. Legacy Spring Boot 2 apps use the **javax.validation** namespace; never mix both namespaces in the same configuration.

### Validating Method Parameters

Constraints placed directly on **@RequestParam**, **@PathVariable**, or controller method parameters require method validation:

~~~java
@GetMapping("/api/products")
List<ProductView> find(
    @RequestParam(defaultValue = "1") @Min(1) @Max(100) int page,
    @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size
) {
    return productService.find(page, size);
}
~~~

Starting with Spring Framework 6.1, Spring MVC includes built-in method validation support. When using this built-in mechanism, avoid placing **@Validated** at the controller level, as doing so can trigger AOP-based method validation instead of MVC's built-in support. On older Spring Framework versions, **@Validated** on the controller or bean and matching method-validation setup are typically required. Follow the guidance for your project's Spring Boot/Spring Framework version.

### Nested Validation

**@Valid** triggers validation for nested objects:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record AddressRequest(
    @NotBlank
    @Size(max = 120)
    String street,

    @NotBlank
    @Pattern(regexp = "^[0-9]{5,10}$")
    String postalCode
) {}

public record CreateCustomerRequest(
    @NotBlank
    String name,

    @NotNull
    @Valid
    AddressRequest address
) {}
~~~

Without **@Valid** on the address property, constraints inside **AddressRequest** may not run when validating the parent object. For collections of objects, use **List<@Valid AddressRequest>** to cascade to each item.

## 8. Cross-Field Constraints and Domain Rules

Not every rule can be checked by a single annotation on one field. For instance, an end date must be after a start date, or allocation percentages must sum to 100. These are cross-field or class-level constraints.

Example class-level annotation:

~~~java
import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.Documented;
import java.lang.annotation.Retention;
import java.lang.annotation.Target;

import static java.lang.annotation.ElementType.TYPE;
import static java.lang.annotation.RetentionPolicy.RUNTIME;

@Target(TYPE)
@Retention(RUNTIME)
@Constraint(validatedBy = DateRangeValidator.class)
@Documented
public @interface ValidDateRange {
    String message() default "End date must be on or after start date";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

Validator:

~~~java
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public class DateRangeValidator
        implements ConstraintValidator<ValidDateRange, DateRangeRequest> {

    @Override
    public boolean isValid(
            DateRangeRequest value,
            ConstraintValidatorContext context
    ) {
        if (value == null
                || value.startDate() == null
                || value.endDate() == null) {
            return true;
        }

        return !value.endDate().isBefore(value.startDate());
    }
}
~~~

DTO:

~~~java
import java.time.LocalDate;

import jakarta.validation.constraints.NotNull;

@ValidDateRange
public record DateRangeRequest(
    @NotNull LocalDate startDate,
    @NotNull LocalDate endDate
) {}
~~~

The validator returns true when either date is null because presence checking belongs to **@NotNull**. Separating concerns lets the class-level constraint focus solely on the relationship between the two values.

Cross-field rules generally cannot be expressed completely through simple single-property schema keywords. Add documentation on the DTO or operation using **@Schema(description = ...)**, document appropriate error responses, and test at runtime. OpenAPI 3.1/JSON Schema can express certain complex conditions, but you should not assume springdoc automatically infers rules from custom validators.

## 9. Validation Groups for Different Contexts

A DTO may be reused across multiple actions where required rules for creation differ from updates. Bean Validation supports groups to select which constraint set runs.

~~~java
public interface OnCreate {}
public interface OnUpdate {}

public record ProductInput(
    @NotBlank(groups = OnCreate.class)
    String name,

    @NotNull(groups = OnCreate.class)
    @Min(value = 0, groups = {OnCreate.class, OnUpdate.class})
    Integer stock
) {}
~~~

You can select a group when triggering validation with **@Validated(OnCreate.class)** or **@Validated(OnUpdate.class)** at the appropriate point for your Spring version's validation mechanism. With plain **@Valid**, the active group is **Default**; constraints assigned solely to custom groups will not run automatically.

When the same DTO is used across multiple operations, OpenAPI typically has a single schema for that type. A shared schema cannot fully express differences across groups. If create and update request contracts differ noticeably, consider splitting DTOs so springdoc generates separate schemas and clients understand each operation's exact requirements.

## 10. How Bean Validation Maps to OpenAPI

Springdoc can inspect standard constraint metadata and write bounds into the schema. Common mappings include:

| Bean Validation | Typical OpenAPI/JSON Schema property |
| --- | --- |
| **@Min(1)** | **minimum: 1** |
| **@Max(100)** | **maximum: 100** |
| **@DecimalMin("0.01")** | **minimum** or **exclusiveMinimum** depending on inclusivity and OpenAPI version |
| **@DecimalMax("99.99")** | **maximum** or **exclusiveMaximum** depending on inclusivity and OpenAPI version |
| **@Size(min = 3, max = 80)** on string | **minLength**, **maxLength** |
| **@Size(max = 10)** on array | **maxItems** |
| **@Pattern(regexp = "...")** | **pattern** |
| **@Digits(integer = 6, fraction = 2)** | Digit/precision constraints if supported by version and converter |

Example schema for SKU:

~~~yaml
sku:
  type: string
  pattern: '^[A-Z]{3}-[0-9]{6}$'
  minLength: 10
  maxLength: 10
  example: ABC-123456
~~~

Example schema for quantity:

~~~yaml
quantity:
  type: integer
  format: int32
  minimum: 1
  maximum: 5000
~~~

Example schema for price:

~~~yaml
price:
  type: number
  minimum: 0.01
  maximum: 999999.99
~~~

These snippets illustrate schema meaning. Actual generated schemas may emit **number** without format or reference components depending on Java types and configuration. For exclusive bounds, **exclusiveMinimum**/**exclusiveMaximum** representation differs between OpenAPI 3.0 and 3.1; verify the document's **openapi** version field and schema semantics rather than matching one specific YAML shape mechanically.

Springdoc may need appropriate dependencies or configuration to read Jakarta Bean Validation. If constraints are missing from the docs, check springdoc version, Jakarta Validation version, validation dependencies, and whether annotations are on fields/getters/record components.

## 11. Distinguishing Runtime Constraints from @Schema Metadata

**@Schema** enriches OpenAPI documentation; it does not replace runtime validators. Example:

~~~java
@Schema(
    description = "Order quantity",
    minimum = "1",
    maximum = "5000",
    example = "12"
)
@Min(1)
@Max(5000)
Integer quantity
~~~

Here **@Min** and **@Max** are runtime constraints enforced by Bean Validation when validation runs. **@Schema** provides documentation metadata. If the two conflict, clients may submit data the documentation claims is valid only for the server to reject it, or vice versa.

To minimize drift:

- Prefer standard Bean Validation constraints for runtime limits.
- Let springdoc infer schema bounds from constraints where supported.
- Use **@Schema** for descriptions, examples, or details not automatically inferred.
- If bounds must be declared in both places, add tests ensuring their values match.
- Do not annotate response DTOs with constraints expecting Spring to validate outgoing responses automatically; annotations on a DTO do not validate every serialized response object by default.

## 12. Error Responses When Data Violates Constraints

When **@Valid @RequestBody** detects invalid data, Spring MVC typically raises **MethodArgumentNotValidException**. With Spring Framework 6.1's built-in method validation, method parameter errors may be represented by **HandlerMethodValidationException**. AOP-based method validation in other versions or setups may throw **ConstraintViolationException**.

Applications should standardize error responses via **@RestControllerAdvice**, for instance returning **400 Bad Request** with a list of fields and messages:

~~~json
{
  "type": "VALIDATION_ERROR",
  "message": "Invalid input data",
  "violations": [
    {
      "field": "price",
      "message": "must be greater than or equal to 0.01"
    },
    {
      "field": "sku",
      "message": "Product code format is invalid"
    }
  ]
}
~~~

Documenting the error response in OpenAPI:

~~~java
@ApiResponse(
    responseCode = "400",
    description = "Input data violates constraints",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = ValidationErrorView.class)
    )
)
~~~

Exception names and how Spring converts them into responses depend on version and configuration. Whichever exception is used, clients should receive a stable error structure to identify the field, violated rule, and how to fix the input.

## 13. Testing Validation and the Generated Schema

### Testing Valid and Invalid Requests

Example with MockMvc:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ProductController.class)
class ProductValidationTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    ProductService productService;

    @Test
    void rejectsInvalidSku() throws Exception {
        mockMvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "name": "Laptop",
                      "sku": "bad-code",
                      "price": 120.00,
                      "stock": 5,
                      "tags": []
                    }
                    """))
            .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsPriceBelowMinimum() throws Exception {
        mockMvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "name": "Laptop",
                      "sku": "ABC-123456",
                      "price": 0.00,
                      "stock": 5,
                      "tags": []
                    }
                    """))
            .andExpect(status().isBadRequest());
    }
}
~~~

Slice tests need validation configuration and mocked controller dependencies. Depending on Spring Security setup, tests may need authentication or appropriate filter configuration. Tests should assert not just status codes but also field names and error structures when those are part of the contract.

### Inspecting the OpenAPI Schema

Fetch the specification after the application starts:

~~~bash
curl -sS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Inspect the component:

~~~bash
jq '.components.schemas.CreateProductRequest' openapi.json
~~~

Verify:

1. Does **price** have a numeric type and the expected price range?
2. Does **stock** have the right minimum and maximum?
3. Does **sku** have the right pattern, length, and example?
4. Does **tags** have item count bounds and a schema for individual items?
5. Are required fields documented accurately per the contract?
6. Does the **400** response document the error schema actually returned by the server?

Open Swagger UI to inspect the limits and try entering out-of-range values. Swagger UI may display bounds or perform basic client-side checks, yet the server remains the final authority enforcing validation.

## 14. Common Pitfalls

**Invalid data is still accepted.** Check the **spring-boot-starter-validation** dependency, the **@Valid** annotation on the request body, and method validation setup for direct parameters. Verify that requests actually pass through the validation provider.

**Null fields are not rejected despite @Min or @Pattern.** That is normal behavior for many constraints: null is considered valid. Add **@NotNull** or **@NotBlank** if the field is required.

**Boundary values are rejected.** Check **inclusive** on **@DecimalMin**/**@DecimalMax**, as well as **@Digits** limits. **@Min** and **@Max** are inclusive.

**OpenAPI has minimum but lacks maximum.** Check annotation placement on fields/getters/record components, dependencies, and springdoc version. Inspect the generated JSON schema to see which constraint was skipped.

**Regex appears in OpenAPI yet client inputs behave differently from server checks.** Check **^** and **$** anchors, differences between Java regex and regex dialects supported by OpenAPI/client tools, and any flags in use.

**@Valid does not validate nested objects.** Add **@Valid** on the nested property or collection element where cascading is needed.

**Schema says field is required yet runtime accepts null.** Combine **@NotNull**/**@NotBlank** properly, check **requiredMode** or schema settings, and test actual requests.

**Response DTO has constraints yet invalid responses are still sent.** Bean Validation does not validate response objects automatically just because annotations exist on the DTO. Add explicit validation in service/controller or test serialization and responses if business rules require it.

## 15. Value-Range Constraint Checklist

- [ ] Choose constraints matching the data type: integer, decimal, string, or collection.
- [ ] Use **@Min**/**@Max** for inclusive integer bounds and **@DecimalMin**/**@DecimalMax** for decimal thresholds.
- [ ] Use **@Positive** and **@PositiveOrZero** when sign rules express intent more clearly.
- [ ] Use **@Pattern** for formatted strings and anchor regexes when full-string matching is needed.
- [ ] Combine **@NotNull**, **@NotBlank**, or **@NotEmpty** when the field must have a value.
- [ ] Use **@Size** for string length or element count, never to bound numeric values.
- [ ] Enable validation with **@Valid** or method validation suitable for your Spring version.
- [ ] Cascade validation into nested objects and collections.
- [ ] Use custom class-level constraints for cross-field rules.
- [ ] Keep runtime constraints aligned with OpenAPI schemas and error responses.
- [ ] Test valid requests, invalid requests, and **/v3/api-docs**.

## 16. Conclusion

**@Min**, **@Max**, **@DecimalMin**, **@DecimalMax**, **@Pattern**, and related constraints turn value-range rules into enforceable checks in Spring Boot. springdoc can reflect many of these bounds in the OpenAPI schema so clients know valid input ranges upfront. Enable validation properly, handle requiredness and nullability separately, document cross-field rules, and verify error responses alongside generated schemas. When runtime and documentation express the same contract, clients can prepare accurate payloads and avoid integration failures.

## 17. References

- [Jakarta Bean Validation 3.0 Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html): standard constraint semantics, groups, cascading, and custom validators.
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): Bean Validation integration in Spring.
- [Spring Framework — Validation in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): validating request bodies and method parameters in Spring MVC.
- [Springdoc OpenAPI](https://springdoc.org/): generating OpenAPI schemas from Spring controllers, DTOs, and annotations.
