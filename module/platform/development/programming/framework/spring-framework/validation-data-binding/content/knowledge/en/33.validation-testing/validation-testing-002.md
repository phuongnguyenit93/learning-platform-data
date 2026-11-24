# Testing Single-Field, Object-Wide, and Nested-Path Errors in Spring Framework

## Learning Objectives

Spring MVC and Spring Validation can detect multiple error types on the same request: a field missing data, an invalid relationship between two fields, or a field nested deep inside an object or list failing a constraint. If you only write a test like `status().isBadRequest()`, you do not yet know **which rule actually ran**, whether the error was recorded at **the right level**, or whether the client received the **exact path** to highlight the input control.

This lesson belongs to the **Testing** section of the Spring Framework — validation-data-binding module, focusing on three cases:

1. **Single-field error:** e.g., `customerName=""` violates `@NotBlank`, represented by Spring as a `FieldError` for `customerName`.
2. **Object-wide error:** e.g., `endDate` earlier than `startDate`, violating a two-property relationship rule, represented as an `ObjectError` in `getGlobalErrors()`.
3. **Nested-path error:** e.g., `shippingAddress.city=""` or `lines[0].sku=""`, still a `FieldError` but with paths `shippingAddress.city` and `lines[0].sku`.

After completing this lesson, you will be able to:

- Distinguish `Errors`, `BindingResult`, `FieldError`, `ObjectError`, and `ConstraintViolation`.
- Understand the role of `@Valid` when cascading into objects, collections, and container elements.
- Write a custom Jakarta class-level constraint that produces a **global error**, instead of always pushing the error onto a single field.
- Use `getFieldErrors()`, `getGlobalErrors()`, `getAllErrors()`, `hasFieldErrors(...)`, `getFieldError(...)`, and `getErrorCount()`.
- Test plain validation with `jakarta.validation.Validator`, Spring `Errors` with `MapBindingResult`, and HTTP endpoints with `MockMvc`.
- Recognize `MethodArgumentNotValidException` for `@Valid @RequestBody` as distinct from `HttpMessageNotReadableException` caused by malformed JSON, and `HandlerMethodValidationException` from method validation (Spring 6.1+).
- Build a Spring Boot 3.5 / Java 17+ application with nested JSON DTOs and element lists, testing the three error levels separately as well as mixed cases.
- Avoid brittle tests caused by constraint violation ordering, locale-dependent message text, or unnormalized paths.

## 1. Three error levels are not three HTTP status types

Consider an order creation request:

~~~json
{
  "customerName": "Lan",
  "shippingAddress": {
    "street": "12 Main St",
    "city": "Ha Noi",
    "postalCode": "12345"
  },
  "lines": [
    {"sku": "BOOK-1", "quantity": 2}
  ],
  "startDate": "2026-11-01",
  "endDate": "2026-11-03"
}
~~~

Example rules:

- `customerName` must contain non-whitespace text: `@NotBlank`.
- `shippingAddress.city` must contain non-whitespace text: `@NotBlank` on the nested record, paired with `@Valid` on the edge from request to address.
- `lines[0].sku` must contain non-whitespace text, `lines[0].quantity` must be at least 1: nested list + `@Valid`.
- `endDate` must not be before `startDate`: class-level constraint `@ValidPeriod` on the whole request.

When changing values:

| Modified request | Rule type | Spring error | Path / target |
| --- | --- | --- | --- |
| `customerName=""` | Property constraint | `FieldError` | `customerName` |
| `endDate="2026-10-31"` | Class-level constraint | `ObjectError` (global) | `createOrderRequest` |
| `shippingAddress.city=""` | Nested bean constraint | `FieldError` | `shippingAddress.city` |
| `lines[0].sku=""` | Nested list element | `FieldError` | `lines[0].sku` |
| `lines[0].quantity=0` | Nested numeric constraint | `FieldError` | `lines[0].quantity` |
| JSON missing closing brace | JSON parse/deserialize | Does not necessarily have `BindingResult` | `HttpMessageNotReadableException` |

**All of these input validation errors can typically lead to HTTP 400**, but the key focus of this lesson is the error structure on the Spring side. HTTP 400 alone does not prove that object-wide errors or nested paths were handled properly.

### Flow diagram

~~~text
HTTP JSON / form
        |
        v
Deserialize / Bind
        |
        +-- Malformed JSON syntax → HttpMessageNotReadableException
        +-- Form property conversion fails → typeMismatch FieldError
        |
        v
@Valid / @Validated
        |
        +-- @NotBlank(customerName)
        |         → FieldError("customerName")
        |
        +-- @ValidPeriod(CreateOrderRequest)
        |         → ObjectError("createOrderRequest")
        |
        +-- @Valid shippingAddress
        |         → FieldError("shippingAddress.city")
        |
        '-- @Valid lines element [0]
                  → FieldError("lines[0].sku")
        |
        v
BindingResult
        |
        +-- getFieldErrors()
        +-- getGlobalErrors()
        '-- getAllErrors()
~~~

`@Valid` on a nested property **is not a replacement constraint for `@NotNull`**. It instructs the provider to descend into the object when the object is present; if the nested object is null, cascading typically does not check child properties. When an address is required, add `@NotNull` separately on that property.

## 2. How do FieldError and ObjectError differ?

### 2.1. ObjectError

`org.springframework.validation.ObjectError` describes an error attached to the entire target object or a bound object, without pointing to a specific property. Notable accessors:

~~~java
String objectName = error.getObjectName();
String code = error.getCode();
String defaultMessage = error.getDefaultMessage();
String[] codes = error.getCodes();
Object[] arguments = error.getArguments();
~~~

This snippet assumes `error` has type `ObjectError`. `objectName` is typically the binding target name assigned by Spring, e.g., `createOrderRequest`. `getCode()` is the base error code such as `ValidPeriod`; `getCodes()` can contain more specific codes used for MessageSource resolution.

### 2.2. FieldError extends ObjectError

`org.springframework.validation.FieldError` is a subclass of `ObjectError`. It carries additional information:

~~~java
String field = fieldError.getField();
Object rejected = fieldError.getRejectedValue();
boolean bindingFailure = fieldError.isBindingFailure();
~~~

A `@NotBlank` error after successful binding typically has `isBindingFailure() == false`. Conversely, when a form sends `quantity=abc` while Java expects `Integer`, the Spring binder fails to convert the type and can create a FieldError with `typeMismatch`, `isBindingFailure() == true`.

**Do not log or return raw `rejectedValue` to clients**: that field could contain passwords, tokens, or personal data. In tests, only inspect rejected values for non-sensitive dummy data.

### 2.3. BindingResult is a collection, not just one error

`BindingResult` extends `Errors`:

~~~java
int total = errors.getErrorCount();
int fieldCount = errors.getFieldErrorCount();
int globalCount = errors.getGlobalErrorCount();

boolean hasAny = errors.hasErrors();
boolean hasName = errors.hasFieldErrors("customerName");
boolean hasGlobal = errors.hasGlobalErrors();

List<FieldError> fieldErrors = errors.getFieldErrors();
List<ObjectError> globalErrors = errors.getGlobalErrors();
List<ObjectError> allErrors = errors.getAllErrors();
~~~

The snippet assumes `errors` has type `BindingResult`. `getAllErrors()` contains **field + global**. Because `FieldError extends ObjectError`, the return type is `List<ObjectError>`, which **does not** mean every element is a global error.

Common mistake:

~~~java
for (ObjectError error : errors.getAllErrors()) {
    // Treat every error as object-level and ignore field path!
}
~~~

To separate them properly, use `getFieldErrors()` and `getGlobalErrors()` or check `instanceof FieldError` intentionally.

### 2.4. A nested path is still a FieldError

When `shippingAddress.city` is invalid, Spring does not create a separate `NestedError` type. The nested path is typically represented in `FieldError.getField()`:

~~~text
customerName
shippingAddress.city
lines[0].sku
lines[1].quantity
~~~

`getFieldErrors("shippingAddress.city")` selects errors for that field. When matching in tests, use **the model's actual path** rather than stripping every nested error down to `city`. If frameworks/adapters differ in how they represent container elements, observe the actual paths before locking down the contract; the runnable example below uses Spring MVC/Jakarta Validator on Boot 3.5.

## 3. Jakarta Bean Validation and ConstraintViolation paths

Before reaching Spring MVC, Jakarta Validation lets you validate Java objects directly:

~~~java
Set<ConstraintViolation<CreateOrderRequest>> violations =
        validator.validate(request);
~~~

`jakarta.validation.Validator.validate(...)` returns a `Set`; it **does not automatically throw `MethodArgumentNotValidException`**. Each violation provides:

~~~java
String message = violation.getMessage();
String path = violation.getPropertyPath().toString();
Object invalid = violation.getInvalidValue();
Class<?> annotationType = violation
        .getConstraintDescriptor()
        .getAnnotation()
        .annotationType();
~~~

The code above is a snippet; `getInvalidValue()` should only be used internally under control, not returned raw to the frontend.

Typically:

- Field-level `@NotBlank` on `customerName` produces path `customerName`.
- Class-level `@ValidPeriod` placed on the root bean produces an **empty** path `""` as the default violation.
- A constraint on a nested bean produces a path like `shippingAddress.city`.
- A constraint on a list element can produce a path like `lines[0].sku`, carrying container/index node metadata depending on the provider.

Spring uses an adapter (such as `LocalValidatorFactoryBean` / Spring Validator adapter) to convert `ConstraintViolation` instances into `FieldError` or `ObjectError` inside `BindingResult`. **Do not** compare the `ConstraintViolation` count directly with the `FieldError` count if there are also binding failures, additional Spring Validators, or different validation groups.

### Violation order is not fixed

Jakarta Bean Validation returns a `Set`, so avoid writing tests like:

~~~java
assertEquals("customerName",
        violations.iterator().next().getPropertyPath().toString());
~~~

Use `anyMatch`, `contains` on the path set, or sort before comparing. Likewise, if a JSON error response contains an array of errors, the API should sort it if the contract requires stable ordering; otherwise, tests must not depend on array positions.

## 4. Creating an object-wide error with a class-level constraint

The rule "`endDate` must not be earlier than `startDate`" involves **two properties**. Placing `@PastOrPresent` or `@Future` on each property individually cannot describe this relationship.

Example annotation:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = ValidPeriodValidator.class)
@Documented
public @interface ValidPeriod {
    String message() default "End date must not be before start date";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

Paired with the validator:

~~~java
public final class ValidPeriodValidator
        implements ConstraintValidator<ValidPeriod, CreateOrderRequest> {

    @Override
    public boolean isValid(CreateOrderRequest value,
                           ConstraintValidatorContext context) {
        if (value == null
                || value.startDate() == null
                || value.endDate() == null) {
            return true;
        }
        return !value.endDate().isBefore(value.startDate());
    }
}
~~~

These are snippets; complete files with imports are in section 7. Note:

1. `@Target(TYPE)` attaches the constraint to the **class/record**, not to a field.
2. When `isValid` returns false without altering the violation builder, Jakarta creates a violation on the root object. Spring converts it into a **global ObjectError**.
3. If one or both dates are null, the class-level validator returns true and lets each field's `@NotNull` report the error. This avoids NPEs and prevents two redundant messages with the same meaning.
4. If you want to display the relational error on `endDate` specifically, you can call `ConstraintValidatorContext.disableDefaultConstraintViolation()` and then `buildConstraintViolationWithTemplate(...).addPropertyNode("endDate").addConstraintViolation()`. The error then becomes a **FieldError**, no longer a global error. That is a UI design choice, not a mandatory requirement.

Why test global errors separately? If the author of a custom constraint accidentally calls `addPropertyNode("endDate")`, the rule still fails and HTTP still returns 400, yet `getGlobalErrors()` no longer contains this error. Testing status alone fails to catch the contract change.

## 5. Nested-path errors: @Valid and collections

### 5.1. Nested bean

~~~java
public record ShippingAddress(
        @NotBlank String street,
        @NotBlank String city,
        @NotBlank String postalCode) {
}
~~~

When the root DTO has:

~~~java
@NotNull @Valid ShippingAddress shippingAddress
~~~

then `shippingAddress.city=""` produces an error at path `shippingAddress.city`. If `@Valid` is removed, constraints inside `ShippingAddress` **are not checked automatically** when validating the root, even though the root property has `@NotNull`.

### 5.2. Nested collection

~~~java
public record OrderLine(
        @NotBlank String sku,
        @NotNull @Min(1) Integer quantity) {
}
~~~

When the root DTO has:

~~~java
@NotEmpty
List<@Valid OrderLine> lines
~~~

a `sku` violation on the first element can appear under path `lines[0].sku`. A violation on the second element is `lines[1].sku`. Note:

- `@NotEmpty` alone on a List checks that the collection has at least one element; it **does not** cascade into each element.
- `@Valid` on the element/collection is what triggers cascading.
- A `null` element is not cascaded into; if null elements are disallowed, use a type-use constraint like `List<@NotNull @Valid OrderLine>`.
- For a Map, paths may represent keys like `entries[sku-1].amount`; inspect the actual path produced by your provider.
- Do not construct paths using display JSON names if the model uses `@JsonProperty` renaming; Jakarta/Spring paths generally follow Java property names unless a `PropertyNodeNameProvider` or custom mapping is configured.

### 5.3. Null object differs from blank nested field

These two cases are not the same:

~~~json
{"shippingAddress": null}
~~~

and:

~~~json
{"shippingAddress": {"street":"12 Main","city":"","postalCode":"12345"}}
~~~

The first case produces field error `shippingAddress` due to `@NotNull`, without necessarily producing `shippingAddress.city`. In the second case, `@NotNull` passes and `@Valid` descends, producing field error `shippingAddress.city` due to `@NotBlank`.

### 5.4. Nested path with Spring Validator

Outside Jakarta, plain Spring allows `Errors.pushNestedPath("shippingAddress")`, followed by `rejectValue("city",...)`:

~~~java
errors.pushNestedPath("shippingAddress");
try {
    errors.rejectValue("city", "city.required");
} finally {
    errors.popNestedPath();
}
~~~

The field path is recorded as `shippingAddress.city`. `pushNestedPath` and `popNestedPath` should remain balanced even if the validator throws an exception. Failing to pop can cause subsequent field errors to receive the wrong prefix.

## 6. When does MethodArgumentNotValidException appear?

On Spring MVC 6.2, with a controller:

~~~java
@PostMapping("/api/orders")
ResponseEntity<?> create(
        @Valid @RequestBody CreateOrderRequest request) {
    // ...
}
~~~

and no `Errors`/`BindingResult` immediately following the argument, when **object Bean Validation** fails, Spring typically throws `org.springframework.web.bind.MethodArgumentNotValidException`. This exception exposes `BindingResult` via `getBindingResult()`.

If you want the controller to handle errors itself (e.g., an HTML form), it can accept `BindingResult` right after `@ModelAttribute`:

~~~java
@PostMapping("/form")
String submit(
        @Valid @ModelAttribute("createOrderRequest")
        CreateOrderRequest request,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return "order-form";
    }
    return "redirect:/success";
}
~~~

This is a form-flow snippet, not part of the runnable JSON demo. Immutable DTOs with constructor binding should be tested with the exact Spring version and parameter names when used with forms; complex forms with collection indexes are often more convenient with a dedicated input bean. The key rule to remember is that `BindingResult` **must immediately follow** the validated argument.

### 6.1. Native handler method validation is a different mechanism

Spring Framework 6.1+ supports native method validation for direct constraints on method parameters, for example:

~~~java
@GetMapping("/api/orders/limits")
String limits(@RequestParam @Min(1) int count) {
    return "ok";
}
~~~

On failure, MVC can throw `HandlerMethodValidationException`, grouping results by method parameters. It is **not** the same as `MethodArgumentNotValidException` for an individually validated DTO. Adding a direct `@NotNull` onto `@Valid @RequestBody` can cause method validation to be selected instead of argument-level validation, depending on the method signature structure.

The runnable test suite in this lesson **does not** place direct constraints on controller method arguments so that all three error types follow the `MethodArgumentNotValidException` path.

### 6.2. Undecodable JSON fails before validation

Requests like:

~~~text
{"customerName":
~~~

or sending `"quantity":"abc"` to an `Integer` field in a DTO can prevent Jackson from constructing the Java object. Spring then typically throws `HttpMessageNotReadableException`; **there is no guarantee that Bean Validation or BindingResult ran**. Testing status 400 alone does not distinguish a JSON parse failure from a `@NotBlank` failure.

With `application/x-www-form-urlencoded`, Spring `WebDataBinder` can usually collect conversion failures into `BindingResult` as `typeMismatch`. With JSON, Jackson deserialization happens before validation and usually reports a different exception. Writing tests that separate the two paths is important.

## 7. Runnable Java 17+ / Spring Boot 3.5.7 Project

We will build a `POST /api/orders` endpoint demonstrating the three error levels. Spring Boot 3.5.7 manages Spring Framework 6.2.x and the Jakarta Bean Validation provider (typically Hibernate Validator). Any errors after the body is deserialized into `CreateOrderRequest` will have a `BindingResult` inside `MethodArgumentNotValidException` and be transformed by a `@RestControllerAdvice` into stable JSON.

### 7.1. File structure

~~~text
spring-validation-tests/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/validation/
    │   │   ├── Application.java
    │   │   ├── ShippingAddress.java
    │   │   ├── OrderLine.java
    │   │   ├── CreateOrderRequest.java
    │   │   ├── ValidPeriod.java
    │   │   ├── ValidPeriodValidator.java
    │   │   ├── OrderController.java
    │   │   └── ValidationAdvice.java
    │   └── resources/application.properties
    └── test/java/com/example/validation/
        ├── OrderValidationHttpTest.java
        ├── JakartaValidationTest.java
        └── SpringErrorsTest.java
~~~

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>spring-validation-tests</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter-aop` is not needed for this example; this is **argument-level validation**, not service AOP method validation. `spring-boot-starter-web` includes Jackson (including Java Time support via managed dependencies) for ISO date JSON; the validation starter provides the Jakarta provider.

### 7.3. Application.java

~~~java
package com.example.validation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

### 7.4. ShippingAddress.java

~~~java
package com.example.validation;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

public record ShippingAddress(
        @NotBlank String street,
        @NotBlank String city,
        @NotBlank
        @Pattern(regexp = "[0-9]{5}")
        String postalCode) {
}
~~~

`city=""` violates `@NotBlank`. `postalCode="XYZ"` violates `@Pattern`. For a `null` postalCode, `@NotBlank` fails while `@Pattern` treats null as valid by default, so the two constraints have distinct responsibilities.

### 7.5. OrderLine.java

~~~java
package com.example.validation;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record OrderLine(
        @NotBlank String sku,
        @NotNull @Min(1) Integer quantity) {
}
~~~

With `quantity=0`, a `Min` error occurs on `lines[0].quantity`. With `quantity=null`, a `NotNull` error occurs. `@NotBlank` on `sku` does not run automatically unless the root cascades into the elements.

### 7.6. CreateOrderRequest.java

~~~java
package com.example.validation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import java.time.LocalDate;
import java.util.List;

@ValidPeriod
public record CreateOrderRequest(
        @NotBlank String customerName,
        @NotNull @Valid ShippingAddress shippingAddress,
        @NotEmpty List<@NotNull @Valid OrderLine> lines,
        @NotNull LocalDate startDate,
        @NotNull LocalDate endDate) {
}
~~~

This structure intentionally covers all three levels:

- `@NotBlank customerName` produces a single-field error.
- `@ValidPeriod` on the root record produces an object-wide error.
- `@Valid ShippingAddress` and `List<@Valid OrderLine>` cascade to produce nested-path errors.
- `@NotNull` on address, dates, and collection elements avoids confusing "absent" with "invalid child field".
- `@NotEmpty` on the list ensures at least one element exists.

In Spring 6.2/Hibernate Validator 8, Jakarta annotations can be placed on record components as shown above. Do not use the legacy `javax.validation.*` package from Spring Boot 2.

### 7.7. ValidPeriod.java — custom class-level constraint

~~~java
package com.example.validation;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = ValidPeriodValidator.class)
public @interface ValidPeriod {

    String message()
            default "End date must not be before start date";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
~~~

This is a class-level constraint. Do not declare `@Target(FIELD)` if you want to test a true global ObjectError as in the example.

### 7.8. ValidPeriodValidator.java

~~~java
package com.example.validation;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public final class ValidPeriodValidator
        implements ConstraintValidator<ValidPeriod, CreateOrderRequest> {

    @Override
    public boolean isValid(
            CreateOrderRequest request,
            ConstraintValidatorContext context) {

        if (request == null
                || request.startDate() == null
                || request.endDate() == null) {
            return true;
        }

        return !request.endDate().isBefore(
                request.startDate());
    }
}
~~~

If `startDate="2026-11-01"` and `endDate="2026-10-31"`, it returns false. Because neither `disableDefaultConstraintViolation()` nor `addPropertyNode(...)` is called, the violation sits on the **root object**. `LocalValidatorFactoryBean` translates it into an `ObjectError` in Spring MVC.

If either date is null, this validator skips validation; the respective field's `@NotNull` will report the error. Test this separately to prevent NPEs and to prevent a request missing both dates from receiving a misleading `ValidPeriod` message.

### 7.9. OrderController.java

~~~java
package com.example.validation;

import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    public record OrderAccepted(
            String result,
            String customerName,
            int lineCount) {
    }

    @PostMapping
    public ResponseEntity<OrderAccepted> create(
            @Valid @RequestBody CreateOrderRequest request) {

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new OrderAccepted(
                        "created",
                        request.customerName(),
                        request.lines().size()));
    }
}
~~~

The controller does not take a `BindingResult` after `@RequestBody` and has no direct constraints on other method arguments. Therefore in Spring MVC, an invalid DTO after deserialization goes through `MethodArgumentNotValidException`. A valid request returns HTTP 201. Domain persistence is outside the scope of validation testing.

### 7.10. ValidationAdvice.java — grouping field/global by type

~~~java
package com.example.validation;

import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Objects;

@RestControllerAdvice
public class ValidationAdvice {

    public record FieldIssue(
            String path,
            String code,
            boolean bindingFailure) {
    }

    public record ValidationReport(
            String code,
            List<FieldIssue> fieldErrors,
            List<String> globalErrors) {
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ValidationReport> invalid(
            MethodArgumentNotValidException ex) {

        BindingResult result = ex.getBindingResult();

        List<FieldIssue> fields = result.getFieldErrors()
                .stream()
                .map(error -> new FieldIssue(
                        error.getField(),
                        Objects.toString(
                                error.getCode(), "invalid"),
                        error.isBindingFailure()))
                .sorted(Comparator
                        .comparing(FieldIssue::path)
                        .thenComparing(FieldIssue::code))
                .toList();

        List<String> global = result.getGlobalErrors()
                .stream()
                .map(error -> Objects.toString(
                        error.getCode(), "invalid"))
                .sorted()
                .toList();

        return ResponseEntity.badRequest().body(
                new ValidationReport(
                        "VALIDATION_FAILED",
                        fields,
                        global));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<Map<String, String>> unreadable(
            HttpMessageNotReadableException ex) {

        return ResponseEntity.badRequest().body(
                Map.of("code", "INVALID_JSON"));
    }
}
~~~

Because `FieldError extends ObjectError`, you should not map `result.getAllErrors()` to `globalErrors`. This code reads **the two sets separately**; it keeps `path` only for field errors, and includes only `code` for global errors without fabricating a field path.

Sorting errors by `path` then `code` keeps the JSON contract and tests deterministic regardless of the order in which the provider returns violations. The response **omits** `error.getRejectedValue()`, stack traces, and raw invalid input, reducing the risk of exposing sensitive data.

`HttpMessageNotReadableException` is handled with its own `INVALID_JSON` code rather than being "faked" as a FieldError. Production apps can standardize all errors into ProblemDetail/RFC 9457, but this lesson uses a small JSON response to visualize the field and global groups clearly.

### 7.11. application.properties

~~~properties
server.port=8080
spring.mvc.problemdetails.enabled=false
server.error.include-message=never
~~~

The advice handles both exception types itself to test a stable error structure. `spring.mvc.problemdetails.enabled=false` does not prevent the app from using `ProblemDetail` later; it simply avoids relying on Boot Problem Details auto-configuration within the example scope.

### 7.12. Running the application and sending requests

~~~bash
mvn spring-boot:run
~~~

Valid request:

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{
    "customerName":"Lan",
    "shippingAddress":{
      "street":"12 Main",
      "city":"Ha Noi",
      "postalCode":"12345"
    },
    "lines":[{"sku":"BOOK-1","quantity":2}],
    "startDate":"2026-11-01",
    "endDate":"2026-11-03"
  }'
~~~

Expected HTTP status **201 Created**, JSON body:

~~~json
{
  "result": "created",
  "customerName": "Lan",
  "lineCount": 1
}
~~~

Request with all three error types simultaneously:

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{
    "customerName":"",
    "shippingAddress":{
      "street":"12 Main",
      "city":"",
      "postalCode":"12345"
    },
    "lines":[{"sku":"","quantity":2}],
    "startDate":"2026-11-01",
    "endDate":"2026-10-31"
  }'
~~~

Expected HTTP status **400 Bad Request**. Fields will be sorted by path. Expected body:

~~~json
{
  "code": "VALIDATION_FAILED",
  "fieldErrors": [
    {
      "path": "customerName",
      "code": "NotBlank",
      "bindingFailure": false
    },
    {
      "path": "lines[0].sku",
      "code": "NotBlank",
      "bindingFailure": false
    },
    {
      "path": "shippingAddress.city",
      "code": "NotBlank",
      "bindingFailure": false
    }
  ],
  "globalErrors": ["ValidPeriod"]
}
~~~

This is the expected output according to the contract built by `ValidationAdvice`; because default messages are not serialized, the content does not depend on locale. Field paths follow the Java DTO. A client can use `fieldErrors[].path` to map onto form fields and `globalErrors` to display a top-level error banner.

## 8. MockMvc tests separating the three error types

Create `src/test/java/com/example/validation/OrderValidationHttpTest.java`:

~~~java
package com.example.validation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class OrderValidationHttpTest {

    @Autowired
    MockMvc mvc;

    private static String validJson() {
        return """
                {
                  "customerName":"Lan",
                  "shippingAddress":{
                    "street":"12 Main",
                    "city":"Ha Noi",
                    "postalCode":"12345"
                  },
                  "lines":[
                    {"sku":"BOOK-1","quantity":2}
                  ],
                  "startDate":"2026-11-01",
                  "endDate":"2026-11-03"
                }
                """;
    }

    private org.springframework.test.web.servlet.ResultActions
    postJson(String body) throws Exception {
        return mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body));
    }

    @Test
    void validPayloadReturnsCreated() throws Exception {
        postJson(validJson())
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.result").value("created"))
                .andExpect(jsonPath("$.lineCount").value(1));
    }

    @Test
    void singleFieldErrorIsNotGlobal() throws Exception {
        String body = validJson().replace(
                "\"customerName\":\"Lan\"",
                "\"customerName\":\"\"");

        postJson(body)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(
                        "VALIDATION_FAILED"))
                .andExpect(jsonPath("$.fieldErrors", hasSize(1)))
                .andExpect(jsonPath(
                        "$.fieldErrors[0].path")
                        .value("customerName"))
                .andExpect(jsonPath(
                        "$.fieldErrors[0].code")
                        .value("NotBlank"))
                .andExpect(jsonPath(
                        "$.fieldErrors[0].bindingFailure")
                        .value(false))
                .andExpect(jsonPath("$.globalErrors", hasSize(0)));
    }

    @Test
    void classLevelErrorIsGlobalNotField()
            throws Exception {

        String body = validJson().replace(
                "\"endDate\":\"2026-11-03\"",
                "\"endDate\":\"2026-10-31\"");

        postJson(body)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fieldErrors", hasSize(0)))
                .andExpect(jsonPath("$.globalErrors", hasSize(1)))
                .andExpect(jsonPath("$.globalErrors[0]")
                        .value("ValidPeriod"));
    }

    @Test
    void nestedBeanFieldErrorContainsFullPath()
            throws Exception {

        String body = validJson().replace(
                "\"city\":\"Ha Noi\"",
                "\"city\":\"\"");

        postJson(body)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fieldErrors", hasSize(1)))
                .andExpect(jsonPath("$.fieldErrors[0].path")
                        .value("shippingAddress.city"))
                .andExpect(jsonPath("$.fieldErrors[0].code")
                        .value("NotBlank"))
                .andExpect(jsonPath("$.globalErrors", hasSize(0)));
    }

    @Test
    void listElementErrorContainsIndex()
            throws Exception {

        String body = validJson().replace(
                "\"sku\":\"BOOK-1\"",
                "\"sku\":\"\"");

        postJson(body)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fieldErrors", hasSize(1)))
                .andExpect(jsonPath("$.fieldErrors[0].path")
                        .value("lines[0].sku"))
                .andExpect(jsonPath("$.fieldErrors[0].code")
                        .value("NotBlank"));
    }

    @Test
    void quantityRuleIsNestedFieldError()
            throws Exception {

        String body = validJson().replace(
                "\"quantity\":2", "\"quantity\":0");

        postJson(body)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fieldErrors[0].path")
                        .value("lines[0].quantity"))
                .andExpect(jsonPath("$.fieldErrors[0].code")
                        .value("Min"));
    }

    @Test
    void missingNestedObjectIsItsOwnFieldError()
            throws Exception {

        String body = validJson().replace(
                """
                    "shippingAddress":{
                    "street":"12 Main",
                    "city":"Ha Noi",
                    "postalCode":"12345"
                  }
                """.trim(),
                "\"shippingAddress\":null");

        // Verify the body changed; if formatting differs,
        // use a full JSON literal instead of replace.
        postJson(body)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fieldErrors[0].path")
                        .value("shippingAddress"))
                .andExpect(jsonPath("$.fieldErrors[0].code")
                        .value("NotNull"));
    }

    @Test
    void missingDateDoesNotTriggerClassLevelRule()
            throws Exception {

        String body = validJson().replace(
                "\"endDate\":\"2026-11-03\"",
                "\"endDate\":null");

        postJson(body)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fieldErrors[0].path")
                        .value("endDate"))
                .andExpect(jsonPath("$.fieldErrors[0].code")
                        .value("NotNull"))
                .andExpect(jsonPath("$.globalErrors", hasSize(0)));
    }

    @Test
    void mixedErrorsStayInSeparateArrays()
            throws Exception {

        String body = validJson()
                .replace("\"customerName\":\"Lan\"",
                        "\"customerName\":\"\"")
                .replace("\"city\":\"Ha Noi\"",
                        "\"city\":\"\"")
                .replace("\"sku\":\"BOOK-1\"",
                        "\"sku\":\"\"")
                .replace("\"endDate\":\"2026-11-03\"",
                        "\"endDate\":\"2026-10-31\"");

        postJson(body)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fieldErrors", hasSize(3)))
                .andExpect(jsonPath("$.globalErrors", hasSize(1)))
                .andExpect(jsonPath("$.fieldErrors[0].path")
                        .value("customerName"))
                .andExpect(jsonPath("$.fieldErrors[1].path")
                        .value("lines[0].sku"))
                .andExpect(jsonPath("$.fieldErrors[2].path")
                        .value("shippingAddress.city"))
                .andExpect(jsonPath("$.globalErrors[0]")
                        .value("ValidPeriod"));
    }

    @Test
    void malformedJsonIsNotBeanValidation()
            throws Exception {

        postJson("{")
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_JSON"))
                .andExpect(jsonPath("$.fieldErrors")
                        .doesNotExist());
    }

    @Test
    void invalidDateTextIsDeserializationFailure()
            throws Exception {

        String body = validJson().replace(
                "\"startDate\":\"2026-11-01\"",
                "\"startDate\":\"not-a-date\"");

        postJson(body)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_JSON"));
    }
}
~~~

**Note on editing the `missingNestedObject...` test:** the `String.replace` approach depends on the exact string/whitespace of the Java text block; for durable tests, it is best to use `ObjectMapper` and `ObjectNode` or a full JSON literal. Replacing a multiline JSON block above only serves to illustrate the difference between `shippingAddress=null` and `shippingAddress.city=""`; if you adjust the formatting of `validJson()`, update or remove the whitespace-dependent replace accordingly. The remaining tests replace stable short tokens.

### 8.1. Why compare paths/codes instead of defaultMessage?

If a test depends on `"must not be blank"`, switching the locale to Vietnamese or upgrading Hibernate Validator can break the test even though the rule and contract remain intact. `FieldError.getCode()` (such as `NotBlank`, `Min`) and the `getField()` path are generally better suited for structural tests.

You still need a **separate test** for MessageSource/i18n if the product requires exact Vietnamese error phrasing. Do not mix error-code tests with translation tests.

### 8.2. Why assert that global is empty?

If you only assert:

~~~java
.andExpect(status().isBadRequest())
~~~

then accidentally attaching `@ValidPeriod` to `endDate` would still return 400. Asserting:

~~~java
.andExpect(jsonPath("$.fieldErrors", hasSize(0)))
.andExpect(jsonPath("$.globalErrors[0]")
        .value("ValidPeriod"))
~~~

verifies the **right error level**. In a UI-backed product, global errors may appear at the top of a form while field errors appear next to their corresponding inputs.

## 9. Testing Jakarta Validation directly, without HTTP

Create `src/test/java/com/example/validation/JakartaValidationTest.java`:

~~~java
package com.example.validation;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.time.LocalDate;
import java.util.List;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class JakartaValidationTest {

    @Autowired
    Validator validator;

    private static CreateOrderRequest request(
            String name,
            String city,
            String sku,
            LocalDate start,
            LocalDate end) {

        return new CreateOrderRequest(
                name,
                new ShippingAddress(
                        "12 Main", city, "12345"),
                List.of(new OrderLine(sku, 2)),
                start,
                end);
    }

    @Test
    void validatesOneField() {
        var input = request(
                "", "Ha Noi", "BOOK-1",
                LocalDate.parse("2026-11-01"),
                LocalDate.parse("2026-11-03"));

        Set<ConstraintViolation<CreateOrderRequest>>
                result = validator.validate(input);

        assertEquals(1, result.size());
        assertTrue(result.stream().anyMatch(v ->
                v.getPropertyPath().toString()
                        .equals("customerName")));
    }

    @Test
    void classLevelViolationHasEmptyRootPath() {
        var input = request(
                "Lan", "Ha Noi", "BOOK-1",
                LocalDate.parse("2026-11-01"),
                LocalDate.parse("2026-10-31"));

        var result = validator.validate(input);

        assertEquals(1, result.size());
        assertTrue(result.stream().anyMatch(v ->
                v.getPropertyPath().toString().isEmpty()
                && v.getConstraintDescriptor()
                        .getAnnotation()
                        .annotationType()
                        .equals(ValidPeriod.class)));
    }

    @Test
    void nestedBeanPathIncludesParent() {
        var input = request(
                "Lan", "", "BOOK-1",
                LocalDate.parse("2026-11-01"),
                LocalDate.parse("2026-11-03"));

        var result = validator.validate(input);

        assertEquals(1, result.size());
        assertTrue(result.stream().anyMatch(v ->
                v.getPropertyPath().toString()
                        .equals("shippingAddress.city")));
    }

    @Test
    void nestedListPathIncludesIndex() {
        var input = request(
                "Lan", "Ha Noi", "",
                LocalDate.parse("2026-11-01"),
                LocalDate.parse("2026-11-03"));

        var result = validator.validate(input);

        assertEquals(1, result.size());
        assertTrue(result.stream().anyMatch(v ->
                v.getPropertyPath().toString()
                        .equals("lines[0].sku")));
    }

    @Test
    void absentDateLeavesCrossFieldValidatorSilent() {
        var input = request(
                "Lan", "Ha Noi", "BOOK-1",
                LocalDate.parse("2026-11-01"),
                null);

        var result = validator.validate(input);

        assertEquals(1, result.size());
        assertTrue(result.stream().allMatch(v ->
                v.getPropertyPath().toString()
                        .equals("endDate")));
    }
}
~~~

This test suite isolates the Bean Validation provider from the HTTP argument resolver, Jackson, and advice. It returns `Set<ConstraintViolation<?>>`; it **does not** directly inspect Spring's `BindingResult.getGlobalErrors()`. Run alongside MockMvc to distinguish whether an issue lies in the rule engine or in MVC integration.

## 10. Testing Spring Errors / BindingResult directly

Create `src/test/java/com/example/validation/SpringErrorsTest.java`:

~~~java
package com.example.validation;

import org.junit.jupiter.api.Test;
import org.springframework.validation.MapBindingResult;

import java.util.HashMap;

import static org.junit.jupiter.api.Assertions.*;

class SpringErrorsTest {

    @Test
    void rejectAndRejectValueAreDifferent() {
        var result = new MapBindingResult(
                new HashMap<String, Object>(),
                "createOrderRequest");

        result.rejectValue(
                "customerName",
                "name.required");

        result.reject(
                "period.invalid");

        assertEquals(2, result.getErrorCount());
        assertEquals(1, result.getFieldErrorCount());
        assertEquals(1, result.getGlobalErrorCount());

        assertTrue(result.hasFieldErrors("customerName"));
        assertEquals("name.required",
                result.getFieldError("customerName")
                        .getCode());

        assertTrue(result.hasGlobalErrors());
        assertEquals("period.invalid",
                result.getGlobalError().getCode());

        assertEquals(2, result.getAllErrors().size());
    }

    @Test
    void nestedPathIsPrefixedAndRestored() {
        var result = new MapBindingResult(
                new HashMap<String, Object>(),
                "createOrderRequest");

        result.pushNestedPath("shippingAddress");
        try {
            result.rejectValue("city", "city.required");
        } finally {
            result.popNestedPath();
        }

        result.rejectValue(
                "lines[0].sku", "sku.required");

        assertEquals(2, result.getFieldErrorCount());

        assertEquals("shippingAddress.city",
                result.getFieldError(
                        "shippingAddress.city")
                        .getField());

        assertEquals("lines[0].sku",
                result.getFieldError(
                        "lines[0].sku")
                        .getField());

        assertEquals(0, result.getGlobalErrorCount());
    }
}
~~~

`MapBindingResult` lets you test Spring's error-recording mechanism directly on a map, without an MVC context or Hibernate Validator. `reject(...)` adds a global error; `rejectValue("field",...)` adds a field error while respecting the nested path.

The full project contains **18 test methods**: 11 HTTP tests, 5 Jakarta tests, and 2 Spring Errors tests. Do not assert arbitrary violation counts on a case with multiple constraints unless the fixture is designed so that only one rule fails.

Run all:

~~~bash
mvn test
~~~

Or run each class:

~~~bash
mvn -Dtest=OrderValidationHttpTest test
mvn -Dtest=JakartaValidationTest test
mvn -Dtest=SpringErrorsTest test
~~~

The example is written to compile with Java 17+ and Spring Boot 3.5.7; **Maven was not executed in the README authoring environment**. In real deployments, use maintained patch releases, especially for security advisories related to Jackson, Spring MVC, and data binding.

## 11. Test improvement: using ObjectMapper instead of String.replace

`String.replace` is a readable choice for small fixtures and fixed token strings. For larger test suites, it can fail to modify JSON if whitespace or serialization changes. Prefer Jackson `ObjectMapper` and `ObjectNode` to mutate structured fixtures:

~~~java
ObjectMapper mapper = new ObjectMapper();
ObjectNode root = (ObjectNode) mapper.readTree(
        validJson());

root.put("customerName", "");
((ObjectNode) root.path("shippingAddress"))
        .put("city", "");

ArrayNode lines = (ArrayNode) root.path("lines");
((ObjectNode) lines.get(0)).put("sku", "");

String body = mapper.writeValueAsString(root);
~~~

This is a **standalone JSON manipulation snippet** (requires Jackson imports and calling inside a test class with a `validJson()` method). When tests need Jackson to deserialize `LocalDate` directly into a Java object, remember the Java Time module; however, this snippet only manipulates `JsonNode` and does not need to deserialize dates into `LocalDate`.

To test `shippingAddress=null` reliably, you can do:

~~~java
ObjectNode root = (ObjectNode) mapper.readTree(
        validJson());

root.putNull("shippingAddress");

String body = mapper.writeValueAsString(root);
~~~

This avoids "false PASS" tests caused by `replace` failing to match a multiline block exactly.

### When to use separate fixtures?

- When each test needs an easily readable variant: create `src/test/resources/json/valid-order.json`, `blank-name.json`, `invalid-period.json`, `nested-city.json`.
- When only changing one value from a baseline: use `ObjectMapper`/`ObjectNode` to clone/mutate JSON.
- When testing decode errors: send a **raw malformed string**; do not use `ObjectMapper` to build the body because the mapper prevents invalid JSON.
- When asserting errors in order: sort at the API layer or use order-independent matchers instead of calling `violations.iterator().next()` arbitrarily.

## 12. Testing multiple simultaneous errors and exact paths

### 12.1. One field can have multiple errors

A field with both `@NotBlank` and `@Pattern` can produce multiple constraint violations when input violates both simultaneously. In that case:

~~~java
errors.getFieldErrors("postalCode")
~~~

can contain more than one `FieldError`. Do not call `getFieldError("postalCode")` alone and assume it represents all errors. Check the **set of codes** or an explicit "display first error" policy.

### 12.2. Global and field errors can fail simultaneously

For an input with both `customerName=""` and `endDate < startDate`, BindingResult holds both `FieldError("customerName")` and `ObjectError("createOrderRequest")`. A response that only serializes `getFieldErrors()` loses the class-level rule; a response that only serializes `getAllErrors()` without preserving the type makes it hard for the client to place errors accurately in the UI.

### 12.3. Nested collections with multiple elements

A list:

~~~json
{
  "lines": [
    {"sku":"OK-1","quantity":2},
    {"sku":"","quantity":0}
  ]
}
~~~

can produce:

~~~text
lines[1].sku       → NotBlank
lines[1].quantity  → Min
~~~

If the list order changes, the indexes change accordingly. These are **input-shape-dependent paths**, and indexes should not be treated as permanent business IDs. For batch edits, a client may need an item key/UUID in the DTO to match errors after reordering.

### 12.4. Nested property paths differ between Form and JSON

URL-encoded forms typically use parameter names:

~~~text
shippingAddress.city=
lines[0].sku=
lines[0].quantity=0
~~~

Spring `WebDataBinder` uses property paths. Conversion errors like `typeMismatch` can occur when formatting fails. With JSON, Jackson builds the object graph before Spring Bean Validation runs. Thus even when two requests represent the same data, the exception class and failure point can differ.

## 13. Testing validation groups

`@Validated(Group.class)` lets you select constraint groups per use case. A test running under the Default group does not necessarily execute constraints belonging only to another group.

Marker example:

~~~java
public interface FinalSubmission {
}
~~~

A field:

~~~java
@NotBlank(groups = FinalSubmission.class)
private String approvalReason;
~~~

With direct validation:

~~~java
validator.validate(
        request,
        FinalSubmission.class);
~~~

These are standalone snippets, not part of the demo DTO. If a test uses the default group while expecting to assert a `FinalSubmission` error, you will see no error; that is the intended behavior, not Spring skipping validation.

When using Spring MVC `@Validated(FinalSubmission.class)` on an argument, check method-level vs argument-level validation and default groups. If you want both `Default` and a custom group to run, select both or design an appropriate group sequence, then write tests for that exact contract.

## 14. Testing message codes and localization

A `FieldError` has:

~~~text
NotBlank.createOrderRequest.customerName
NotBlank.customerName
NotBlank.java.lang.String
NotBlank
~~~

These are example codes under `DefaultMessageCodesResolver`; the actual list may differ if objectName/type/MessageCodesResolver is configured differently. A global error can have:

~~~text
ValidPeriod.createOrderRequest
ValidPeriod
~~~

If the application uses `messages_vi.properties`, you can define:

~~~properties
NotBlank.createOrderRequest.customerName=Cần nhập tên người mua
NotBlank.createOrderRequest.shippingAddress.city=Cần nhập thành phố
ValidPeriod.createOrderRequest=Ngày kết thúc không được trước ngày bắt đầu
~~~

To test translations, resolve `ObjectError`/`FieldError` using `MessageSource.getMessage(error, locale)`:

~~~java
String localized = messageSource.getMessage(
        error, Locale.forLanguageTag("vi"));
~~~

The snippet requires importing `MessageSource`, `ObjectError`, and `Locale`, with `error` being the corresponding instance. Note that Jakarta `ValidationMessages*.properties` (constraint message interpolation) differs from Spring `messages*.properties` (FieldError/ObjectError MessageSource), though they can be intentionally integrated via `LocalValidatorFactoryBean`.

Separate tests into:

1. **Structure:** path, code, global/field group, HTTP status.
2. **Language:** messages for `vi`/`en`, fallback, and placeholder replacement.

Do not hardcode English sentences from Hibernate Validator in tests that verify validation logic.

## 15. Security and error stability

### 15.1. Do not echo rejected values

`FieldError.getRejectedValue()` can contain sensitive data. Do not return bodies like:

~~~json
{
  "path": "password",
  "rejectedValue": "secret-user-input"
}
~~~

This lesson only returns `path`, `code`, and `bindingFailure`. In production, messages can be translated on the server or client; either approach needs a defined contract and proper escaping.

### 15.2. Preventing mass assignment in forms

A test for `@ModelAttribute` should not only check validation. If a form DTO exposes sensitive setters like `role`/`status`, the binder can populate them from the request. Use DTOs containing only editable fields, `WebDataBinder.setAllowedFields`, and where appropriate `setDeclarativeBinding(true)` (Spring 6.1+). This is **binding security testing**, distinct from `@NotBlank` testing.

### 15.3. Limiting nested collection indexes

A form request can try sending `lines[1000000].sku` to trigger auto-grow or exhaust resources. For binders, configure collection auto-grow limits per policy, limit request size/line counts, and stay current on Spring patches. For JSON, restrict body size, element count, nesting depth, and perform business checks before heavy processing. Do not let nested-path testing leave an API vulnerable to DoS via oversized payloads.

### 15.4. Do not expose class names and SQL

Standardized error responses must not include `ex.toString()` or stack traces in `detail`. Test client codes/statuses instead of internal exception messages, while ensuring logs capture correlation IDs and necessary diagnostics without leaking secrets.

## 16. Common pitfalls

| Symptom | Cause | Fix |
| --- | --- | --- |
| HTTP 400 test PASSES, but global error is missing | Only asserting status | Assert `getGlobalErrors` or JSON `globalErrors` |
| Class-level rule appears as a FieldError | Custom validator used `addPropertyNode` | Keep default class-level violation if global is desired |
| `shippingAddress.city` reports no error | Missing `@Valid` on root → address edge | Add cascade and test nested |
| `shippingAddress=null` reports no error | Has `@Valid` only, no `@NotNull` | Add `@NotNull` on the property |
| `lines[0].sku` reports no error | Not cascading into list elements | `List<@Valid OrderLine>` and test path |
| Null list element reports no error | Cascade skips null | Use `@NotNull` type-use for element |
| Test only reads `getFieldError()` | Ignores remaining errors | Use `getFieldErrors()` and inspect code set |
| Test depends on violation order | Set does not guarantee order | Sort or use order-independent assertions |
| English message test fails under another locale | Used defaultMessage to test logic | Assert `code`/`path`, test i18n separately |
| `@Valid` on root controller, yet controller still runs | `BindingResult` immediately follows argument or validation not enabled | Check signature and Spring setup |
| Occasionally hits `HandlerMethodValidationException` | Added direct constraint on method | Recognize Spring 6.1+ native validation |
| Malformed JSON has no FieldError | Jackson fails before Bean Validation | Test `HttpMessageNotReadableException` |
| Form `quantity=abc` differs from JSON `quantity="abc"` | Binder and Jackson are two different pipelines | Test each content type independently |
| Nested field reports `city` while test expects prefix | Test used path missing parent | Assert `shippingAddress.city` |
| `getAllErrors()` holds only ObjectError so distinction is lost | `FieldError extends ObjectError` | Separate `getFieldErrors()` and `getGlobalErrors()` |
| Global rule throws NPE when date is null | Cross-field validator lacks null guard | Add null guard, let `@NotNull` report field error |
| `@Validated` group does not trigger rule | Test group does not match | Select the right groups |
| JSON parses LocalDate incorrectly | Date string not ISO/configured format | Check Jackson Java Time and date format |
| Translation does not find error code | objectName/field path changed | Print `getCodes()` in test and update bundle |
| Unexpected list index path in another provider | Container element metadata differs | Verify exact paths in Jakarta vs Spring MVC |
| Invalid password leaked in error JSON | Serialized rejectedValue | Return only code/path, never echo input |

## 17. Testing strategy in real projects

To stay both fast and reliable, split tests into layers:

| Test layer | What to use | Asserts |
| --- | --- | --- |
| Spring error holder unit | `MapBindingResult` / `BeanPropertyBindingResult` | `reject` vs `rejectValue`, nested prefixes, counts |
| Jakarta constraint test | `jakarta.validation.Validator` | Rule logic, default/root path, cascade, groups |
| Spring MVC integration | `MockMvc` with validation provider | Deserialization, annotation resolution, HTTP status, BindingResult adaptation |
| API contract | MockMvc or integration HTTP client | Field/global JSON shape, stable code/path, localization |
| Security & robustness | MockMvc/full app | No leaked rejected values, size limits, no data mutation on invalid input |

**Write one test per error type**, then add a "mixed" test to prove Spring does not drop errors when multiple constraints fail in the same request. In systems with services/persistence, invalid-request tests must verify **no side effects** (no records created, no events published, no orders placed).

### Quick checklist when a test fails

1. Print `BindingResult.getObjectName()` and `getAllErrors()` in the test environment, while avoiding logging sensitive `rejectedValue` data.
2. Verify `@Valid` is on both the controller argument and the nested edge.
3. Verify the Jakarta provider is on the classpath (Spring Boot validation starter).
4. Check that the class-level constraint has `@Target(TYPE)` and the validator does not accidentally call `addPropertyNode`.
5. Distinguish JSON parse exceptions from validation exceptions.
6. Check the root object name and actual field paths.
7. Check null guards, group selection, and collection element constraints.
8. If tests use JSON string replacement, verify the string actually changed; prefer `ObjectNode` for larger fixtures.
9. Do not rely on default message wording or unguaranteed ordering.
10. If auditing the API, test both the response schema and resulting persisted state.

## 18. Practice exercises

**1. Field vs global.** Send `customerName=""` and `endDate < startDate` separately. Inspect the field/global error counts in each case and explain why their HTTP statuses can be identical.

**2. Class-level error.** In `ValidPeriodValidator`, use `addPropertyNode("endDate")` to move the error onto a field. Update the test and explain the impact on UI/contract.

**3. Nested bean.** Remove `@Valid` from `shippingAddress` and run the empty-city test. Which error disappears? Does `@NotNull` on address help validate city?

**4. List element.** Send two lines where the second element has `sku=""`. Assert path `lines[1].sku` without relying on the order of other violations.

**5. Missing nested object.** Compare the errors for `shippingAddress=null` vs `shippingAddress.city=""`. When is the path `shippingAddress`, and when is it `shippingAddress.city`?

**6. JSON vs form.** Try sending `quantity="abc"` via JSON and `quantity=abc` via a form with a binder. Why can the exception and error metadata differ?

**7. Spring Errors.** Write a Spring `Validator` that calls `errors.reject("order.invalid")` and `errors.rejectValue("customerName","name.required")`; verify `getAllErrors()`, `getFieldErrorCount()`, and `getGlobalErrorCount()`.

**8. Localization.** Create `messages_vi.properties` entries for `ValidPeriod.createOrderRequest` and `NotBlank.createOrderRequest.customerName`; verify that the code stays stable while the wording changes by Locale.

**9. Groups.** Assign the postalCode constraint to a custom group. Prove the Default group does not run this constraint, then use `@Validated(...)` or direct Jakarta Validator groups to activate it.

**10. Security.** Add a password field to the nested input, try exposing `rejectedValue` in the response, and write a test detecting sensitive strings; update the mapper to return only code/path.

## Conclusion

Three lines to remember:

~~~text
Single-field error  → FieldError("customerName")
Object-wide error   → ObjectError("createOrderRequest")
Nested-path error   → FieldError("shippingAddress.city")
                       FieldError("lines[0].sku")

BindingResult.getFieldErrors()
BindingResult.getGlobalErrors()
BindingResult.getAllErrors()
~~~

**Testing status 400 is not enough**. Verify the exact **type**, **code**, **path**, **count**, **error level**, and that no errors are lost when multiple violations occur. Separating Jakarta constraint tests, Spring Errors tests, and MockMvc integration tests helps pinpoint quickly whether an issue lies in rules, cascading, error adaptation, JSON deserialization, or HTTP rendering.

## References

- [Spring Framework 6.2 — MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework — Bean Validation integration](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Framework — Error Code Resolution](https://docs.spring.io/spring-framework/reference/core/validation/error-code-resolution.html)
- [Spring Framework — Errors API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/Errors.html)
- [Spring Framework — BindingResult API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework — FieldError API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/FieldError.html)
- [Spring Framework — ObjectError API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/ObjectError.html)
- [Spring Framework — MethodArgumentNotValidException](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/bind/MethodArgumentNotValidException.html)
- [Spring Framework — ResponseEntityExceptionHandler](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html)
- [Jakarta Bean Validation 3.0 specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Hibernate Validator — Reference Guide](https://docs.jboss.org/hibernate/validator/8.0/reference/en-US/html_single/)
