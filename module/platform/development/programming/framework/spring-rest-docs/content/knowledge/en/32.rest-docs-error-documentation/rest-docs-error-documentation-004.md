# Field-Level and Object-Level Validation Errors

## 1. Lesson Objectives

In the **SPRING_REST_DOCS** module, we generate verifiable REST API documentation through HTTP tests using MockMvc, WebTestClient, or REST Assured. Tests send requests, assert responses, and Spring REST Docs generates snippets for requests, responses, payloads, parameters, and headers. Snippets are compiled with Asciidoctor/Markdown and integrated into the build and CI pipeline.

When an API validates input data, an error can belong to a single field or to multiple fields together. For example, a malformed email is a field-level error; startDate being later than endDate is an object-level error because the rule compares two values. With nested requests and lists of elements, the API also needs to indicate the path to the invalid location.

This lesson guides you through designing and documenting field-level and object-level validation errors with Spring REST Docs. After this lesson, you will be able to:

- Distinguish field-level errors, object-level errors, and general request errors.
- Design an error payload containing field path, code, message, and rejected value under a safe policy.
- Map Bean Validation errors to a stable response.
- Document nested fields, list elements, and object-level errors using Spring REST Docs.
- Write MockMvc tests that verify status, error code, and validation location.
- Organize multiple validation examples in API documentation and CI.

## 2. Field-Level and Object-Level Validation

### 2.1. Field-Level Errors

Field-level validation occurs when an individual value fails a constraint:

~~~json
{
  "email": "not-an-email",
  "quantity": 0
}
~~~

Examples:

- email has an invalid format.
- quantity is below the minimum value.
- shippingAddress.postalCode is blank.

The API can return:

~~~json
{
  "code": "VALIDATION_FAILED",
  "message": "One or more fields are invalid.",
  "errors": [
    {
      "field": "email",
      "code": "EMAIL_INVALID",
      "message": "Email must be a valid address."
    },
    {
      "field": "quantity",
      "code": "QUANTITY_MIN",
      "message": "Quantity must be at least 1."
    }
  ]
}
~~~

Each item identifies a single field along with its corresponding error code and message.

### 2.2. Object-Level Errors

Object-level validation applies to rules that require inspecting multiple fields or overall state:

~~~json
{
  "startDate": "2026-12-20",
  "endDate": "2026-12-10"
}
~~~

The rule that startDate must be on or before endDate cannot be evaluated from a single field alone. The API can return:

~~~json
{
  "code": "VALIDATION_FAILED",
  "message": "The request contains an invalid combination of values.",
  "errors": [
    {
      "object": "bookingRequest",
      "code": "DATE_RANGE_INVALID",
      "message": "Start date must be on or before end date."
    }
  ]
}
~~~

This error is attached to the bookingRequest object and does not necessarily have a single field as its cause. If the API wants to help consumers fix the data, it can add relatedFields: ["startDate", "endDate"].

### 2.3. General Request Errors

Some errors are not tied to a specific field or object, such as an unparseable request body or a payload incompatible with the operation type:

~~~json
{
  "code": "REQUEST_BODY_INVALID",
  "message": "The request body could not be read."
}
~~~

Do not assign a fake field just so every error shares the same shape. Distinguish field paths, object names, and general errors.

## 3. Designing a Validation Error Payload

A single schema can represent all three forms:

~~~json
{
  "code": "VALIDATION_FAILED",
  "message": "One or more values are invalid.",
  "errors": [
    {
      "scope": "FIELD",
      "path": "items[0].quantity",
      "code": "QUANTITY_MIN",
      "message": "Quantity must be at least 1."
    },
    {
      "scope": "OBJECT",
      "path": "bookingRequest",
      "relatedFields": [
        "startDate",
        "endDate"
      ],
      "code": "DATE_RANGE_INVALID",
      "message": "Start date must be on or before end date."
    },
    {
      "scope": "REQUEST",
      "code": "REQUEST_BODY_INVALID",
      "message": "The request body could not be read."
    }
  ],
  "traceId": "req-validation-001"
}
~~~

Meanings:

| Field | Meaning |
| --- | --- |
| code | General or specific error code, stable for clients. |
| message | Response-level or per-error message. |
| errors | List of detected errors. |
| errors[].scope | Error scope: FIELD, OBJECT, or REQUEST. |
| errors[].path | Path to the field/object if applicable. |
| errors[].relatedFields | Fields involved in a cross-field rule. |
| errors[].code | Specific error code for the error item. |
| errors[].message | Specific explanation of the error. |
| traceId | Correlation ID for looking up logs, if provided. |

This is an illustrative schema, not a structure mandated by Spring. A project may use field, object, rejectedValue, or another structure; what matters is that the documentation accurately describes the payload the API returns.

Do not return rejected values by default for all errors. User-submitted values may contain passwords, tokens, personal data, or content unsafe to log. If invalid values must be echoed back, do so only for permitted data types with masking rules in place.

## 4. Declaring Field-Level Constraints with Bean Validation

Example request DTOs:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.util.List;

public record CreateOrderRequest(
    @NotBlank
    String customerName,

    @NotBlank
    @Email
    String email,

    @NotNull
    @Valid
    AddressRequest shippingAddress,

    @NotEmpty
    List<@Valid OrderItemRequest> items
) {
}

public record AddressRequest(
    @NotBlank String street,
    @NotBlank String postalCode
) {
}

public record OrderItemRequest(
    @NotBlank String productId,
    @Min(1) int quantity
) {
}
~~~

Spring MVC triggers Bean Validation for a request body when the controller uses @Valid or @Validated appropriately:

~~~java
@PostMapping("/api/orders")
ResponseEntity<?> createOrder(
        @Valid @RequestBody CreateOrderRequest request) {
    // Create order
    return ResponseEntity.status(HttpStatus.CREATED).build();
}
~~~

@Valid on nested DTOs and collection elements enables validation to traverse into child objects. Without cascading validation, constraints inside shippingAddress or individual items may not be evaluated.

With the example above, field paths can be:

- email
- shippingAddress.postalCode
- items[0].quantity

Actual paths depend on property names, DTO structure, and how the framework constructs binding errors. Tests must verify the paths published by the API.

## 5. Object-Level Constraints with Class-Level Validation

To check a relationship between two fields, create a class-level constraint annotation:

~~~java
import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = DateRangeValidator.class)
public @interface ValidDateRange {
    String message() default "Start date must be on or before end date.";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

Validator:

~~~java
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public class DateRangeValidator
        implements ConstraintValidator<ValidDateRange, BookingRequest> {

    @Override
    public boolean isValid(
            BookingRequest value,
            ConstraintValidatorContext context) {
        if (value == null
                || value.startDate() == null
                || value.endDate() == null) {
            return true;
        }

        return !value.startDate().isAfter(value.endDate());
    }
}
~~~

Request DTO:

~~~java
import jakarta.validation.constraints.NotNull;
import java.time.LocalDate;

@ValidDateRange
public record BookingRequest(
    @NotNull LocalDate startDate,
    @NotNull LocalDate endDate
) {
}
~~~

Class-level constraints typically produce an object error without a specific property path. You can customize ConstraintValidatorContext to attach the violation to a field:

~~~java
context.disableDefaultConstraintViolation();
context.buildConstraintViolationWithTemplate(
        "Start date must be on or before end date.")
    .addPropertyNode("startDate")
    .addConstraintViolation();
~~~

When attached to startDate, the violation is treated as field-level so a UI can highlight a specific input. If the rule genuinely involves both fields, keeping an object-level error and providing explicit relatedFields is usually more accurate.

## 6. Mapping BindingResult to an Error Response

In Spring MVC, validation of @Valid @RequestBody can throw MethodArgumentNotValidException. A @RestControllerAdvice can convert field errors and global errors into the API schema:

~~~java
@RestControllerAdvice
class ValidationExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ValidationErrorResponse> handleValidation(
            MethodArgumentNotValidException exception) {

        List<ValidationErrorItem> errors = new ArrayList<>();

        exception.getBindingResult().getFieldErrors().forEach(error ->
            errors.add(new ValidationErrorItem(
                "FIELD",
                error.getField(),
                error.getCode(),
                error.getDefaultMessage()
            ))
        );

        exception.getBindingResult().getGlobalErrors().forEach(error ->
            errors.add(new ValidationErrorItem(
                "OBJECT",
                null,
                error.getCode(),
                error.getDefaultMessage()
            ))
        );

        return ResponseEntity.badRequest().body(
            new ValidationErrorResponse(
                "VALIDATION_FAILED",
                "One or more values are invalid.",
                errors
            )
        );
    }
}
~~~

Illustrative records:

~~~java
public record ValidationErrorResponse(
    String code,
    String message,
    List<ValidationErrorItem> errors
) {
}

public record ValidationErrorItem(
    String scope,
    String path,
    String code,
    String message
) {
}
~~~

This snippet illustrates how to separate getFieldErrors() and getGlobalErrors(). In a real project, handle null/empty paths, message localization, stable error codes, and non-Bean-Validation binding errors according to your chosen contract.

Do not expose error.getCode() directly as a stable API code without control. Bean Validation codes can be constraint names like NotBlank or Email; the API should map them to public codes with versioning and clear semantics.

## 7. Documenting Nested Field Paths

Spring REST Docs describes response JSON using responseFields(...) and fieldWithPath(...). Example payload:

~~~json
{
  "code": "VALIDATION_FAILED",
  "message": "One or more fields are invalid.",
  "errors": [
    {
      "scope": "FIELD",
      "path": "shippingAddress.postalCode",
      "code": "POSTAL_CODE_REQUIRED",
      "message": "Postal code is required."
    }
  ]
}
~~~

Descriptors:

~~~java
responseFields(
    fieldWithPath("code")
        .description("Overall error code of the validation response."),
    fieldWithPath("message")
        .description("General message."),
    fieldWithPath("errors")
        .description("List of validation errors."),
    fieldWithPath("errors[].scope")
        .description("Error scope: FIELD or OBJECT."),
    fieldWithPath("errors[].path")
        .description("Path of the field or object causing the error."),
    fieldWithPath("errors[].code")
        .description("Stable error code for the specific case."),
    fieldWithPath("errors[].message")
        .description("Message explaining the error.")
)
~~~

The errors[] path targets elements within the array. Child fields are described once and apply to each element. If the path field can be null for object-level errors, descriptors must accurately reflect absence/nullability according to the actual payload.

### 7.1. Optional or Nullable Fields

If an object-level error has no path:

~~~java
fieldWithPath("errors[].path")
    .description("Field/object path; null for errors not tied to a specific path.")
    .optional()
~~~

In REST Docs, optional() indicates a field may be absent. If the JSON always includes the path key with a null value, the field is still present; the description should state clearly that it may be null. Do not confuse an absent field with a present field whose value is null.

## 8. Documenting Errors in Collections and Nested Objects

Nested requests can produce deep paths:

~~~json
{
  "customer": {
    "email": "bad-address"
  },
  "items": [
    {
      "productId": "BOOK-01",
      "quantity": 0
    }
  ]
}
~~~

A validation response can indicate:

~~~json
{
  "errors": [
    {
      "scope": "FIELD",
      "path": "customer.email",
      "code": "EMAIL_INVALID",
      "message": "Email must be a valid address."
    },
    {
      "scope": "FIELD",
      "path": "items[0].quantity",
      "code": "QUANTITY_MIN",
      "message": "Quantity must be at least 1."
    }
  ]
}
~~~

Path conventions should be stable and readable. You can use dot notation for objects and bracket indexing for collections. If the API chooses JSON Pointer, such as /items/0/quantity, use it consistently across all endpoints and document that format.

Do not confuse the path inside the error response with REST Docs descriptor paths. errors[].path is a data value returned by the API; fieldWithPath("errors[].path") is the path to that field in the JSON response documented by REST Docs.

## 9. Documenting Object-Level Errors and Related Fields

Example response:

~~~json
{
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "scope": "OBJECT",
      "path": "bookingRequest",
      "relatedFields": [
        "startDate",
        "endDate"
      ],
      "code": "DATE_RANGE_INVALID",
      "message": "Start date must be on or before end date."
    }
  ]
}
~~~

Descriptors:

~~~java
responseFields(
    fieldWithPath("code").description("Overall error code."),
    fieldWithPath("errors").description("List of validation errors."),
    fieldWithPath("errors[].scope").description("Error scope; OBJECT for cross-field rules."),
    fieldWithPath("errors[].path").description("Object name or path containing the rule."),
    fieldWithPath("errors[].relatedFields").description("Fields participating in the rule."),
    fieldWithPath("errors[].relatedFields[]").description("Name of a related field."),
    fieldWithPath("errors[].code").description("Cross-field rule error code."),
    fieldWithPath("errors[].message").description("Explanation of the unmet condition.")
)
~~~

When the same schema includes a relatedFields field that only appears on object-level errors, you can mark it optional if the response field can genuinely be omitted on field-level errors. If you want to avoid a single schema with many optional fields, the API can separate fieldErrors and objectErrors into two collections with distinct structures.

## 10. MockMvc Test Example for Field-Level Validation

This test example assumes the order creation endpoint returns 400 when email is invalid. REST Docs records the error body and documents each field:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
@Import(ValidationExceptionHandler.class)
class OrderValidationDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void documentsInvalidEmail() throws Exception {
        this.mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "customerName": "An",
                      "email": "bad-address",
                      "shippingAddress": {
                        "street": "1 Main Street",
                        "postalCode": "10000"
                      },
                      "items": [
                        {"productId": "BOOK-01", "quantity": 1}
                      ]
                    }
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
            .andExpect(jsonPath("$.errors[0].path").value("email"))
            .andDo(document("orders/validation-invalid-email",
                responseFields(
                    fieldWithPath("code").description("Overall error code."),
                    fieldWithPath("message").description("General message."),
                    fieldWithPath("errors").description("List of validation errors."),
                    fieldWithPath("errors[].scope").description("Error scope."),
                    fieldWithPath("errors[].path").description("Field or object path."),
                    fieldWithPath("errors[].code").description("Specific error code."),
                    fieldWithPath("errors[].message").description("Error message.")
                )
            ));
    }
}
~~~

In real tests, ensure other fields are valid so that only the email error is triggered. If a request produces multiple errors, assertions should locate the matching item by path/code instead of assuming the error is always at index 0.

## 11. Object-Level Validation Test Example

Suppose a booking request has startDate after endDate and the validator creates a global error:

~~~java
mockMvc.perform(post("/api/bookings")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {
              "startDate": "2026-12-20",
              "endDate": "2026-12-10"
            }
            """))
    .andExpect(status().isBadRequest())
    .andExpect(jsonPath("$.errors[0].scope").value("OBJECT"))
    .andExpect(jsonPath("$.errors[0].code").value("DATE_RANGE_INVALID"))
    .andDo(document("bookings/validation-date-range",
        responseFields(
            fieldWithPath("code").description("Overall error code."),
            fieldWithPath("errors").description("List of validation errors."),
            fieldWithPath("errors[].scope").description("Error scope."),
            fieldWithPath("errors[].path").description("Object containing the rule."),
            fieldWithPath("errors[].code").description("Cross-field error code."),
            fieldWithPath("errors[].message").description("Rule explanation.")
        )
    ));
~~~

This is an object-level error because the condition depends on two dates. If the handler maps the global error to scope=OBJECT, documentation and clients can distinguish it from field-level errors.

## 12. Distinguishing Validation Errors from Binding and Parse Errors

Not every error occurring before a controller runs is Bean Validation:

| Category | Example | How to Distinguish |
| --- | --- | --- |
| Bean Validation | @NotBlank, @Email, @Min fails | Data bound successfully but violated a constraint. |
| Type conversion/binding | String cannot convert to number or date | Request failed to bind to the expected Java type. |
| JSON parse | Malformed JSON syntax or unreadable data type | Message converter could not construct the request object. |
| Object-level rule | startDate > endDate | Rule must evaluate the whole object/multiple fields. |

Spring MVC can throw different exceptions for these categories, such as MethodArgumentNotValidException for request body validation and HttpMessageNotReadableException for body read errors. Even if the API shares a common error envelope, it should still use distinct codes so clients know where to fix the error.

Do not assign EMAIL_INVALID to a malformed JSON request. Error codes must reflect the actual stage and root cause.

## 13. Stability Rules for Field Paths and Error Codes

So clients can handle validation errors reliably over time:

- Use field names from the JSON contract, not internal Java variable names if they differ.
- Keep path formatting consistent: dot notation, bracket indexing, or JSON Pointer.
- Use stable error codes; messages may be localized or reworded.
- Define how object-level errors and related fields are represented.
- Define error ordering if clients/tests require deterministic output; otherwise, tests should look up errors by path/code rather than index.
- Do not return sensitive rejected values.

If you rename a JSON field, treat the corresponding error paths as part of the contract that must be updated, versioned, or announced according to your API compatibility policy.

## 14. Asciidoctor Integration

Documentation can separate field-level and object-level validation examples:

~~~asciidoc
== Validation errors

=== Invalid email

include::{snippets}/orders/validation-invalid-email/http-response.adoc[]
include::{snippets}/orders/validation-invalid-email/response-fields.adoc[]

=== Invalid date range

include::{snippets}/bookings/validation-date-range/http-response.adoc[]
include::{snippets}/bookings/validation-date-range/response-fields.adoc[]
~~~

Snippets show actual tested responses; surrounding prose explains how API consumers fix fields or adjust combinations of values.

## 15. Gradle and CI Integration

Assuming the Asciidoctor plugin is configured, wire the documentation task to tests:

~~~groovy
def snippetsDir = layout.buildDirectory.dir("generated-snippets")

tasks.named("test") {
    outputs.dir(snippetsDir)
}

tasks.named("asciidoctor") {
    dependsOn(tasks.named("test"))
    inputs.dir(snippetsDir)
    attributes "snippets": snippetsDir.get().asFile
}
~~~

Run:

~~~bash
./gradlew clean test asciidoctor
~~~

CI verifies that the validation handler returns the expected status, field path, object scope, and error code before assembling snippets. If constraints or schemas change without updating documentation, assertions or REST Docs descriptors will fail the build.

With plain Markdown, Asciidoctor's include:: syntax is not processed automatically; a separate build step is required to embed snippets or link to generated files.

## 16. Common Pitfalls and Troubleshooting

| Symptom | Cause and Solution |
| --- | --- |
| Nested field produces no errors | Missing @Valid on nested DTO or collection element. |
| Object-level rule does not run | Constraint not placed at class level or validator not registered. |
| Object error documented as field error | Handler only reads getFieldErrors() and ignores getGlobalErrors(). |
| Path in response uses wrong Java property name | Map using public JSON field names and test when using @JsonProperty. |
| Collection errors have unstable indices | Test data or collection order varies; assert by path/code instead of fixed position. |
| REST Docs reports undocumented field | Response contains an undescribed field; add descriptor or handle field per contract. |
| Optional field confused with nullable | Clearly document whether key can be absent or present with null value. |
| Error code changes with constraint name | Map internal constraints to stable API codes. |
| Snippet contains sensitive rejected value | Remove that field from payload or mask via an appropriate policy; use dummy fixtures in tests. |

## 17. Practice Exercise

1. Create DTOs with email, nested shipping address, and list items with constraints.
2. Send a request with an invalid email and quantity equal to 0; inspect the field paths.
3. Create a class-level constraint comparing startDate and endDate.
4. Map FieldError and ObjectError to two different scopes.
5. Write separate MockMvc tests for field-level and object-level validation.
6. Document errors[] using responseFields, including nested paths and relatedFields.
7. Check cases where path can be null/absent and describe the optional semantics accurately.
8. Add a JSON parse error test to distinguish it from Bean Validation.
9. Include snippets in Asciidoctor and run Gradle/CI.

## 18. Key Takeaways

- Field-level errors belong to a single property; object-level errors belong to rules spanning multiple fields or the whole object.
- Nested validation requires cascading with @Valid; collection elements must also be validated.
- Bean Validation errors, binding errors, and JSON parse errors are distinct categories.
- Use FieldError and ObjectError to map appropriate scope/path; do not treat internal constraint codes as API error codes unless standardized.
- Document field paths using public JSON names and keep path formatting consistent.
- Use responseFields(...) and fieldWithPath(...) to describe error arrays and nested fields; mark optional accurately per the contract.
- Test status, error code, and field/object paths before REST Docs generates snippets.

## 19. References

- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): Bean Validation, nested validation, and Spring integration.
- [Spring REST Docs — Payload Snippets](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/payloads.html): field descriptors, nested paths, optional fields, and subsection documentation.
- [Jakarta Bean Validation](https://beanvalidation.org/): constraint annotations and custom class-level validators.
