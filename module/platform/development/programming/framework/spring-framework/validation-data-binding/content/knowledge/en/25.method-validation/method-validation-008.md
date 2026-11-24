# ConstraintViolationException and MethodValidationException in Method Validation

## Objectives

When a method parameter violates `@NotNull`, `@Min`, or a `@Valid` parameter object contains an invalid field, Spring can reject the call with an exception. Two names are easily confused:

- `jakarta.validation.ConstraintViolationException`: the standard Jakarta Validation exception carrying a set of `ConstraintViolation<?>`.
- `org.springframework.validation.method.MethodValidationException`: a Spring Framework 6.1+ exception carrying method validation results adapted into `MethodValidationResult`.

**In Spring AOP method validation**, the same invalid data can produce either exception depending on `MethodValidationPostProcessor.setAdaptConstraintViolations(boolean)`. However, Spring MVC has its own exceptions for controller validation; you should not lump everything into a single type.

This lesson explains how to inspect error data, enable adaptation mode, handle input versus return value errors separately, integrate with Spring MVC/services, and test actual runtime behavior using Java 17+.

## 1. Scenario: One Invocation, Two Ways to Represent Violations

Suppose we have a service:

~~~java
@Validated
public class BookingService {
    public String reserve(
            @Valid @NotNull BookingRequest request,
            @Min(1) int seats) {
        return "BOOKED";
    }
}
~~~

`BookingRequest` has a `code` field with `@NotBlank`. The call:

~~~java
service.reserve(new BookingRequest(""), 0);
~~~

is invalid in two places:

1. `request.code` is an empty string, violating `@NotBlank` via `@Valid` cascading.
2. `seats` is `0`, violating `@Min(1)` directly on the parameter.

If the call passes through the Spring method-validation interceptor:

~~~text
caller
  -> Spring AOP proxy of BookingService
      -> validates method arguments via Jakarta Validation
          -> two ConstraintViolations
              |
              +-- adaptConstraintViolations = false (default)
              |      -> ConstraintViolationException
              |         holds Set<ConstraintViolation<?>>
              |
              +-- adaptConstraintViolations = true
                     -> MethodValidationException
                        holds MethodValidationResult
                        and ParameterValidationResult/ParameterErrors
~~~

As far as constraints go, there is no difference: both branches report the exact same invalid data. The difference lies in **the exception type and error-reporting API**, which affects how controllers/services, loggers, tests, and message resolvers inspect the results.

**Important prerequisite:** annotations on a method do not create AOP validation by themselves; a method validation integration is required, such as a Spring bean with `@Validated` and `MethodValidationPostProcessor`, invoked through the proxy. Calling `new BookingService().reserve(...)` directly produces neither exception.

## 2. Comparing the Two Exceptions

| Aspect | ConstraintViolationException | MethodValidationException |
| --- | --- | --- |
| Package | `jakarta.validation` | `org.springframework.validation.method` |
| Ecosystem | Jakarta Bean Validation | Spring Framework 6.1+ |
| Superclass | `ValidationException` | `RuntimeException` |
| Primary payload | `Set<ConstraintViolation<?>>` | `MethodValidationResult` grouped by parameter |
| How to read | `getConstraintViolations()` | `getParameterValidationResults()` (Spring 6.2+) |
| Single error details | `getPropertyPath()`, `getMessage()`, `getConstraintDescriptor()`, `getInvalidValue()` | `MessageSourceResolvable` and, for nested bean errors, `ParameterErrors` / `FieldError` |
| Method location | Inspect violation's `Path` | `getMethod()`, `getTarget()`, `getMethodParameter()` |
| Input vs. return value | Identified from `Path.Node.getKind()` | `isForReturnValue()` |
| Thrown by default in Spring AOP method validation | Yes | No; requires enabling adaptation |
| Spring-style i18n capability | Has Jakarta-interpolated message; mapping Spring message codes requires custom code | Error codes/arguments as `MessageSourceResolvable` for `MessageSource` |
| Error ordering | `Set` does not guarantee order | List grouped by parameter results; you should still sort API responses intentionally |

**Version note:** Spring Framework 6.1 introduced `MethodValidationException` and `MethodValidationResult`. Starting in Spring **6.2**, use `getParameterValidationResults()`; the older `getAllValidationResults()` method was deprecated in 6.2. If a project is still on 6.1, check that version's API; on 6.0 or earlier, `MethodValidationException` does not exist.

The two exception types do not share a parent-child relationship. Catching `ConstraintViolationException` **will not** catch `MethodValidationException`, and vice versa.

## 3. ConstraintViolationException: Jakarta-Style Violation Reporting

Jakarta Validation provides the exception:

~~~java
public class ConstraintViolationException
        extends ValidationException {

    // Constructor takes Set<? extends ConstraintViolation<?>>
    // Read API:
    public Set<ConstraintViolation<?>> getConstraintViolations();
}
~~~

This is an API sketch for explanation, not standalone source code to compile; do not redefine the library class.

Each `ConstraintViolation<?>` carries information about one failed constraint:

- `getPropertyPath()`: structured `Path` from root to error site; may contain `METHOD`, `PARAMETER`, `RETURN_VALUE`, `PROPERTY`, and `CONTAINER_ELEMENT` nodes.
- `getMessage()`: message already interpolated by Jakarta Validation.
- `getMessageTemplate()`: template before interpolation, such as `"{jakarta.validation.constraints.Min.message}"`.
- `getConstraintDescriptor()`: constraint annotation metadata and attributes.
- `getInvalidValue()`: the specific failing value; avoid echoing into logs/APIs if sensitive data may be present.
- `getExecutableParameters()` / `getExecutableReturnValue()`: argument/result context during executable validation where applicable.

Reading errors safely:

~~~java
catch (ConstraintViolationException ex) {
    var entries = ex.getConstraintViolations().stream()
            .map(v -> v.getPropertyPath()
                    + " : " + v.getMessage())
            .sorted()
            .toList();

    entries.forEach(System.out::println);
}
~~~

This is an excerpt placed inside exception-handling code, not a standalone file. Calling `sorted()` keeps output deterministic because `Set` iteration order should not be relied upon. In real systems, if you need to distinguish parameters from multi-level properties, traverse each `Path.Node` and inspect `ElementKind` instead of splitting path strings manually.

### 3.1. Does Validator Throw This Exception Itself?

**No.** Jakarta APIs such as:

~~~java
Set<ConstraintViolation<BookingRequest>> errors =
        validator.validate(request);
~~~

return a `Set` containing violations; likewise, `validator.forExecutables().validateParameters(...)` returns `Set<ConstraintViolation<T>>`. If violations need to be turned into an exception, the framework, interceptor, or application code decides to throw it.

Manual example:

~~~java
Set<ConstraintViolation<BookingRequest>> errors =
        validator.validate(request);

if (!errors.isEmpty()) {
    throw new ConstraintViolationException(errors);
}
~~~

The two snippets above illustrate working with existing `validator` and `request` variables. The Jakarta Validation specification emphasizes `ConstraintViolationException` as the standard way to **report** violations; calling `validate()` itself does not automatically convert data errors into this exception.

Distinguish normal user/data errors (`ConstraintViolationException` thrown by an interceptor with violations) from **configuration/constraint declaration errors** (`ConstraintDefinitionException`, `UnexpectedTypeException`, `ConstraintDeclarationException`, etc.). Never treat every `ValidationException` as an HTTP 400 input error.

## 4. MethodValidationException: Errors Grouped by Spring

In Spring 6.1+, `MethodValidationException` is a `RuntimeException` implementing `MethodValidationResult`. Rather than working directly with `Set<ConstraintViolation<?>>`, the application reads results already adapted by Spring.

Useful APIs in Spring 6.2:

~~~java
catch (MethodValidationException ex) {
    boolean returnValueProblem = ex.isForReturnValue();

    var method = ex.getMethod();
    var target = ex.getTarget();

    for (var result : ex.getParameterValidationResults()) {
        var parameter = result.getMethodParameter();
        int position = parameter.getParameterIndex();

        for (var error : result.getResolvableErrors()) {
            String defaultText = error.getDefaultMessage();
            // Record position, method, defaultText...
        }
    }
}
~~~

This is a snippet inside a handler that caught the exception, not a standalone program. For a **return value** error, Spring represents the return value with a `MethodParameter` for the return type, conventionally using index `-1`; to determine the method-level error kind, use `isForReturnValue()` rather than inferring from the index alone.

### 4.1. ParameterValidationResult and ParameterErrors

Spring converts the violation set into results matching each parameter:

- **Direct constraint on an argument** (such as `@Min(1) int seats`): typically produces a `ParameterValidationResult` with `getResolvableErrors()`; errors are `MessageSourceResolvable` instances with codes, arguments, and a default message.
- **Constraint inside a `@Valid` object** (such as `BookingRequest.code`): Spring creates `ParameterErrors` (a `ParameterValidationResult` subtype implementing `Errors`). It provides `getFieldErrors()`, `getFieldError(...)`, and standard `Errors` APIs.
- **Constraint on a container element** can produce multiple results per element; `ParameterValidationResult` exposes `getContainer()`, `getContainerIndex()`, and `getContainerKey()`.
- **Cross-parameter constraints:** starting in Spring 6.2, `getCrossParameterValidationResults()` supplies a separate error list; do not assume every error lives in `getParameterValidationResults()`.

Illustrative code handling both groups:

~~~java
for (var result : ex.getParameterValidationResults()) {
    int parameterIndex =
            result.getMethodParameter().getParameterIndex();

    if (result instanceof
            org.springframework.validation.method.ParameterErrors nested) {
        for (var field : nested.getFieldErrors()) {
            System.out.println(
                    parameterIndex + "." + field.getField()
                    + " => " + field.getDefaultMessage());
        }
    } else {
        for (var error : result.getResolvableErrors()) {
            System.out.println(
                    parameterIndex + " => "
                    + error.getDefaultMessage());
        }
    }
}
~~~

This snippet assumes a variable `ex` of type `MethodValidationException` exists; it cannot run standalone. Specific methods on `ParameterValidationResult` are useful when building a consistent HTTP error schema keyed by parameter index and nested fields.

In Spring 6.2, `MethodValidationResult` also provides:

| Method | Purpose |
| --- | --- |
| `getParameterValidationResults()` | All results grouped by parameter or return value |
| `getValueResults()` | Direct constraint errors on argument/return values |
| `getBeanResults()` | Nested errors inside `@Valid` beans, as `ParameterErrors` |
| `getAllErrors()` | Flattened list of errors adapted as `MessageSourceResolvable` |
| `getCrossParameterValidationResults()` | Errors from constraints spanning multiple parameters |
| `getMethod()`, `getTarget()` | The validated method and target bean |
| `isForReturnValue()` | Whether validation ran after the method returned a value |

### 4.2. Error Codes and Message Localization

Spring produces `MessageSourceResolvable` instances so messages can be looked up via `MessageSource`. For `@Min(1)` on a `seats` parameter, error codes can include object/method/parameter-specific forms followed by general forms such as `"Min.seats"`, `"Min.int"`, and `"Min"`.

Message-handling snippet:

~~~java
String localized = messageSource.getMessage(
        error, locale);
~~~

`messageSource` is a configured Spring `MessageSource`, `error` is a `MessageSourceResolvable` from `getResolvableErrors()`, and `locale` is a `java.util.Locale`. This is not a standalone class.

For `@Valid` nested beans, `ParameterErrors` enables `FieldError` and Spring validation's familiar message resolution. Spring error codes have multiple priority levels so messages can be defined in resource bundles, for example:

~~~properties
NotBlank.bookingRequest.code=Booking code must not be blank
Min.seats=Seats must be at least {1}
~~~

These keys are **illustrative examples**; actual error codes depend on object name, method, parameter naming, and constraint metadata. Print `error.getCodes()` in your real environment and write resource bundles to match actual codes before assuming which key matches. Using `{1}` follows Spring `MessageFormat` argument conventions; verify the argument order produced by Spring's adapter.

## 5. Configuring Exception Selection in Spring AOP

Spring Framework provides `MethodValidationPostProcessor` to detect `@Validated` beans and attach AOP advice that validates method constraints. In essence:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.MethodValidationPostProcessor;

@Configuration
public class ValidationConfiguration {

    @Bean
    public static MethodValidationPostProcessor
    methodValidationPostProcessor() {

        MethodValidationPostProcessor processor =
                new MethodValidationPostProcessor();

        processor.setAdaptConstraintViolations(true);
        return processor;
    }
}
~~~

This Spring configuration is syntactically standalone, yet only works in an application with a Jakarta Validation provider and suitable service beans. Setting `true` makes the interceptor adapt `ConstraintViolation` instances into `MethodValidationResult` and throw `MethodValidationException`; `false` is the default mode throwing `ConstraintViolationException`.

**Important in Spring Boot:** projects usually already have method validation infrastructure. Do not add a second `MethodValidationPostProcessor` casually; inspect the active bean/auto-configuration and customize that bean to avoid duplicate proxies or confusing behavior.

Conditions when using Spring AOP method validation:

1. The bean is Spring-managed and annotated with `@Validated` at the class level (for default `MethodValidationPostProcessor`).
2. A Jakarta Validation provider such as Hibernate Validator is present; Spring Boot 3 typically uses `spring-boot-starter-validation`.
3. Callers invoke through the **Spring proxy**, not bypassing it with `this.method(...)`.
4. The method/parameter/return value has appropriate constraints such as `@NotBlank`, `@Min`, `@NotNull`, and `@Valid` on cascade edges.
5. `setAdaptConstraintViolations(...)` is configured before the post-processor creates advice/proxies.

Both modes perform **precondition validation** on parameters and **postcondition validation** on return values. The exception mode only governs how violations are reported.

## 6. Executable Java 17+ Example: Direct Side-by-Side Comparison of Both Modes

The following example uses a Jakarta Validation provider alongside Spring AOP's `ProxyFactory` + `MethodValidationInterceptor`. We attach the advice **manually to the proxy** to run both configurations in one process and compare outputs. This is the same advice mechanism `MethodValidationPostProcessor` uses for Spring beans, without needing to boot a Spring application context.

Create `src/main/java/com/example/validation/Demo.java`:

~~~java
package com.example.validation;

import jakarta.validation.ConstraintViolationException;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.aop.framework.ProxyFactory;
import org.springframework.validation.annotation.Validated;
import org.springframework.validation.beanvalidation.MethodValidationInterceptor;
import org.springframework.validation.method.MethodValidationException;

public final class Demo {

    public record BookingRequest(
            @NotBlank String code) {
    }

    @Validated
    public static class BookingService {

        public String reserve(
                @NotNull @Valid BookingRequest request,
                @Min(1) int seats) {
            return "BOOKED";
        }

        @NotBlank
        public String makeEmptyReceipt() {
            return "";
        }
    }

    private static BookingService proxy(
            Validator validator,
            boolean adaptViolations) {

        ProxyFactory factory =
                new ProxyFactory(new BookingService());

        factory.setProxyTargetClass(true);

        factory.addAdvice(
                new MethodValidationInterceptor(
                        () -> validator, adaptViolations));

        return (BookingService) factory.getProxy();
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();

            BookingService raw = proxy(validator, false);
            BookingService adapted = proxy(validator, true);

            try {
                raw.reserve(new BookingRequest(""), 0);
            } catch (ConstraintViolationException ex) {
                System.out.println(
                        "raw input violations="
                        + ex.getConstraintViolations().size());
            }

            try {
                raw.makeEmptyReceipt();
            } catch (ConstraintViolationException ex) {
                System.out.println(
                        "raw output violations="
                        + ex.getConstraintViolations().size());
            }

            try {
                adapted.reserve(new BookingRequest(""), 0);
            } catch (MethodValidationException ex) {
                System.out.println(
                        "adapted input errors="
                        + ex.getAllErrors().size()
                        + ", return=" + ex.isForReturnValue());
            }

            try {
                adapted.makeEmptyReceipt();
            } catch (MethodValidationException ex) {
                System.out.println(
                        "adapted output errors="
                        + ex.getAllErrors().size()
                        + ", return=" + ex.isForReturnValue());
            }
        }
    }
}
~~~

To test the logic cleanly, note:

- `BookingService` is non-`final`, and its methods are `public` and non-`final` so Spring AOP can create a class proxy.
- `@NotBlank` on record component `code` validates the nested value via `@Valid` on the `request` parameter.
- `@Min(1)` validates `seats`. Two independent input errors occur when `reserve(new BookingRequest(""), 0)` passes through the proxy.
- `@NotBlank` on `makeEmptyReceipt()` is a **return-value constraint**; since the method returns an empty string, post-invocation validation finds one error.
- `ProxyFactory` explicitly attaches `MethodValidationInterceptor` with `adaptViolations` set to `false` and `true`. With a manual proxy, `@Validated` is not what decides whether advice is attached; we keep the annotation to resemble real Spring bean configuration.
- Do not rely on iteration order of `Set<ConstraintViolation<?>>`; the program only prints error **counts**, giving deterministic stdout.

### 6.1. Maven Dependencies and Run Command

Create `pom.xml` next to the `src` directory:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>method-exception-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.16</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.16</version>
        </dependency>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.3.Final</version>
        </dependency>
        <dependency>
            <groupId>org.glassfish</groupId>
            <artifactId>jakarta.el</artifactId>
            <version>4.0.2</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                    <parameters>true</parameters>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Run with JDK 17+ and Maven:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=com.example.validation.Demo
~~~

**Four stdout lines produced by `Demo`** (excluding Maven or Hibernate Validator messages/logs):

~~~text
raw input violations=2
raw output violations=1
adapted input errors=2, return=false
adapted output errors=1, return=true
~~~

Without the Jakarta provider dependency, `Validation.buildDefaultValidatorFactory()` cannot build a validator. If you remove the proxy or call `new BookingService()` directly, the method bodies run without throwing either example exception: this demonstrates the difference between validation metadata and validation triggers.

In a real Spring Boot project, use Spring Boot's BOM/dependency management and `spring-boot-starter-validation`; `pom.xml` here pins Spring Framework 6.2.16, Hibernate Validator 8, and Jakarta EL to illustrate a standalone environment.

### 6.2. Inspecting Both Branches in Depth

With `raw.reserve(...)`, one violation has a path like `reserve.request.code`, and the other has `reserve.seats` when the compiler preserves Java parameter names. Without `-parameters`, parameter names may appear as `arg0`, `arg1`. Actual output can vary by provider and metadata, so in portable code inspect `Path.Node` with `ElementKind.PARAMETER` and `getParameterIndex()`.

With `adapted.reserve(...)`, one `ParameterErrors` represents `request.code` and one `ParameterValidationResult` represents the direct constraint on `seats`. In Spring 6.2, you can inspect them as follows:

~~~java
catch (MethodValidationException ex) {
    System.out.println(
            "bean groups=" + ex.getBeanResults().size());
    System.out.println(
            "direct groups=" + ex.getValueResults().size());

    for (var group : ex.getParameterValidationResults()) {
        int index =
                group.getMethodParameter().getParameterIndex();
        System.out.println("index=" + index);

        for (var error : group.getResolvableErrors()) {
            System.out.println(
                    error.getDefaultMessage());
        }
    }
}
~~~

This snippet **replaces** the catch block of the adapted branch in `Demo`; it is not a standalone class. Grouped data typically has one group for the nested `request` bean and one group for the direct `seats` constraint. When returning to a UI, establish deterministic field/error ordering and use `MessageSource` for localization rather than exposing raw `Throwable` objects in the API.

## 7. Spring MVC: Do Not Confuse MethodValidationException with HandlerMethodValidationException

Common question: "If a controller uses `@Valid`, will it throw `MethodValidationException`?" — **Not necessarily**.

Spring MVC can perform validation when resolving HTTP arguments, or use the controller's own method validation infrastructure.

### 7.1. Validating Only a `@RequestBody` DTO

~~~java
@RestController
class BookingController {

    @PostMapping("/bookings")
    String create(
            @Valid @RequestBody BookingRequest request) {
        return "ok";
    }
}
~~~

In Spring MVC, when validating an individual bound `@RequestBody` object and finding errors, the exception is typically `MethodArgumentNotValidException` (when no `BindingResult` immediately follows the parameter). `@Valid` **is not a direct constraint**, so `@Valid` alone on an object does not trigger native method validation for the whole method.

The snippet above assumes Spring MVC annotations are imported and the DTO is already defined; it is not a standalone Java program.

### 7.2. Direct Constraints on a Controller Method

~~~java
@RestController
class BookingController {

    @GetMapping("/bookings/search")
    String search(@RequestParam @Min(1) int seats) {
        return "ok";
    }
}
~~~

With Spring Framework 6.1+, native controller method validation can be used because `@Min` is a direct constraint on the argument. When method validation fails, Spring MVC's exception is **`org.springframework.web.method.annotation.HandlerMethodValidationException`**.

This is a **different class** from service/AOP's `org.springframework.validation.method.MethodValidationException`. Although both implement `MethodValidationResult`, they are thrown at different integration points.

| Common scenario | Typical exception |
| --- | --- |
| `@Validated` Spring service via AOP, default adaptation `false` | `ConstraintViolationException` |
| `@Validated` Spring service via AOP, adaptation `true` | `MethodValidationException` |
| Spring MVC validating standalone `@Valid @RequestBody` DTO | `MethodArgumentNotValidException` |
| Spring MVC 6.1+ native method validation when controller has direct constraints | `HandlerMethodValidationException` |
| Code explicitly calling `jakarta.validation.Validator.validate(bean)` | Returns `Set<ConstraintViolation<T>>`; throws no exception itself |

For `HandlerMethodValidationException`, Spring MVC follows status conventions: input/parameter errors typically produce HTTP **400**; return-value errors typically produce HTTP **500**. When `MethodValidationException` bubbles up from a service beneath a controller, Spring MVC treats it as a server issue by default with HTTP **500**; do not blindly map every service exception to 400.

Note that class-level `@Validated` on a controller can route validation through an AOP proxy instead of native support. Spring 6.1+ documentation recommends removing class-level `@Validated` if you want Spring MVC's native method validation. Identify the actual application boundary instead of guessing exceptions from annotation names.

## 8. Input and Return Values Must Have Different Handling Policies

Constraints on parameters express **preconditions**: data supplied by the caller must meet requirements before the service runs. Constraints on return values express **postconditions**: data returned by the service must satisfy the method's promise.

Example:

~~~java
@Validated
class PriceService {

    @NotNull
    public String quote(@NotBlank String sku) {
        return null; // Violates postcondition.
    }
}
~~~

If a caller invokes `quote("")` through the Spring proxy, the error occurs **before the body executes**. Calling `quote("ABC")` runs the body, returns `null`, and then triggers a return-value error. The exception mode may be raw or adapted, yet the **origin of the error** differs.

With `MethodValidationException`:

~~~java
if (ex.isForReturnValue()) {
    // Postcondition failure: handle as a bug or server-side data issue.
} else {
    // Precondition failure: identify the caller and originating layer.
}
~~~

This snippet illustrates handling an existing `ex` variable. Do not assume every precondition error from a service is an HTTP client error: services can also be called by schedulers, message consumers, background jobs, or other services passing invalid data. Choosing HTTP 400/422 versus 500 depends on **trust boundaries and the API contract**, not solely on the exception class.

With `ConstraintViolationException`, to classify the origin, inspect `getPropertyPath()` for `PARAMETER` or `RETURN_VALUE` nodes. Do not rely on a message like `"must not be blank"` because the same constraint can apply to both inputs and outputs.

## 9. Designing Clear and Safe Error Responses

When exposing validation errors over HTTP, frontends usually need stable fields like:

~~~json
{
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "location": "request.code",
      "message": "Code must not be blank"
    },
    {
      "location": "seats",
      "message": "Seats must be at least 1"
    }
  ]
}
~~~

This is an illustrative schema only, not output generated automatically by Spring. In practice:

1. Distinguish the origin: HTTP parameter/body paths differ from service/method paths; do not leak `reserve.request.code` to clients if your public API exposes field `code`.
2. Choose deterministic error ordering: sort by parameter index, field path, or domain rules; `Set` does not guarantee order.
3. Expose only necessary field/constraint names and messages. Avoid serializing raw `ConstraintViolation`, `Throwable`, `getInvalidValue()`, target beans, or arguments, as they may contain passwords, tokens, and personal data.
4. Use Spring's `MessageSource` when localizing from `MessageSourceResolvable`; avoid hardcoding every message.
5. For **return value** errors or internal service failures, never reflect the invalid server object to clients; log safely and return an appropriate server error response.
6. At the API boundary, handle controller exceptions explicitly and define a clear policy for service-originated exceptions. Avoid catching and turning every `RuntimeException` into a validation error.

Example mapping `MethodValidationException` in a handling layer (**illustrative snippet** only, must be wired into a concrete handler/framework):

~~~java
List<String> messages = ex.getParameterValidationResults()
        .stream()
        .flatMap(r -> r.getResolvableErrors().stream())
        .map(org.springframework.context.MessageSourceResolvable::
                getDefaultMessage)
        .filter(java.util.Objects::nonNull)
        .sorted()
        .toList();
~~~

At the HTTP layer, you can use `@ControllerAdvice` with dedicated handlers for `MethodArgumentNotValidException`, `HandlerMethodValidationException`, and service errors if the application intentionally maps them. `MethodValidationException` in particular should not default to 400; evaluate its source.

## 10. Relationship to @Valid, Validation Groups, and MessageSource

### 10.1. @Valid Can Produce Nested Errors and ParameterErrors

~~~java
record BookingRequest(@NotBlank String code) {}

public void reserve(@Valid BookingRequest request) {
    // ...
}
~~~

When method validation runs and `request.code` is empty, raw mode produces a violation whose path passes through the parameter and then property `code`. Adapted mode uses `ParameterErrors` and `FieldError` to represent the nested field. Declare cascading properly on the parameter; `@NotBlank` inside the DTO alone is not enough for the interceptor to descend into the DTO through a method parameter without `@Valid`.

**Null:** `@Valid` allows a null reference through; if required, write `@NotNull @Valid BookingRequest request`. Similarly, on a return value, combine `@NotNull` and `@Valid` when both object presence and nested validation are required.

### 10.2. Groups Determine Which Constraints Are Checked

Spring `@Validated(Group.class)` can select validation groups for method validation. If a field only has a constraint in the `Detailed` group, validating under `Default` produces no violation for that field. That is not a bug in exception adaptation.

When invalid data produces no errors, verify first: a trigger exists, the right bean/proxy is called, constraints are in the active group, `@Valid` is on nested edges, and the provider discovered the metadata.

### 10.3. Jakarta and Spring Messages Are Two Separate Layers

Raw `ConstraintViolation.getMessage()` is already interpolated by the Jakarta provider's message interpolator. Adapted `MessageSourceResolvable` carries **a list of codes, arguments, and a default message** so Spring's `MessageSource` can further pick a locale-appropriate message. This does not mean every English Jakarta sentence is translated automatically: you still need resource bundles and accurate mappings.

Example using a `MessageSource`:

~~~java
for (var result : ex.getParameterValidationResults()) {
    for (var error : result.getResolvableErrors()) {
        String text = messageSource.getMessage(
                error, java.util.Locale.forLanguageTag("vi"));
    }
}
~~~

This snippet assumes `ex` and `messageSource` are already provided. If the application needs to display nested field errors, `FieldError` entries inside `ParameterErrors` are also `MessageSourceResolvable` instances and can be resolved the same way.

## 11. Common Pitfalls and Root Causes

| Symptom | Cause to check | Solution |
| --- | --- | --- |
| `catch (ConstraintViolationException)` never triggers | Post-processor enabled `adaptConstraintViolations=true` or error came from native Spring MVC validation | Verify the runtime exception and catch the right type |
| `catch (MethodValidationException)` never triggers | Adaptation is `false` (default), Spring is below 6.1, or another integration ran | Check Spring version, BeanPostProcessor, and call mechanism |
| `getAllValidationResults()` marked deprecated | Project uses Spring 6.2 | Switch to `getParameterValidationResults()` |
| Nested errors missing from adapted result | Missing `@Valid` on parameter/association or group mismatch | Add cascading at the right spot and check groups |
| `validator.validate(bean)` throws no exception | Jakarta API returns a Set by design | Handle the Set explicitly or use an interceptor/framework |
| Annotated method is not blocked on call | Bean bypasses Spring proxy, self-invocation, missing provider/post-processor | Call through the managed bean and inspect bean configuration |
| Two errors appear in different orders | `ConstraintViolation` lives in a `Set` | Convert to an ordered structure before asserting/returning |
| Localized message not found | `MessageSource` lacks matching code or errors were not resolved | Inspect `getCodes()`, message bundles, and locale |
| HTTP returns 500 when expecting 400 input | Error originated in a service or return value | Distinguish error origin and API policy |
| Controller throws `HandlerMethodValidationException` | Spring MVC 6.1+ native controller method validation | Handle the MVC exception type; do not change AOP flags by mistake |
| Adapter cannot map nested field | Complex container/nested path or unexpected metadata | Inspect `ParameterErrors`, `containerIndex`/`containerKey`, and raw path |
| Catching all `ValidationException` as 400 | Conflates metadata/config/provider errors with data errors | Handle only appropriate error types and origins |
| Mixing `javax.validation` and `jakarta.validation` | Incompatible Spring Boot/Spring Framework dependencies | Spring 6/Boot 3 uses `jakarta.validation`; check dependency tree |

## 12. Practical Testing Checklist

You can implement the following tests, each verifying a meaningful contract:

**Test 1 — Raw precondition:** call a `@Validated` bean through its proxy with `BookingRequest.code=""` and `seats=0` when adaptation is `false`. Assert `ConstraintViolationException` with two violations. Do not depend on iteration order.

**Test 2 — Adapted precondition:** run the same input with adaptation `true`. Assert `MethodValidationException` with `isForReturnValue()==false`, results for both the direct parameter error and nested field error, and `getBeanResults()` containing field error `code`.

**Test 3 — Raw postcondition:** call a method with `@NotBlank` on its return value that returns `""`. Assert the raw exception's path contains `RETURN_VALUE`, rather than checking the message alone.

**Test 4 — Adapted postcondition:** assert `MethodValidationException.isForReturnValue()==true`; check that the return value error is grouped correctly.

**Test 5 — Non-proxied behavior:** invoke the method directly on an instance created with `new`. No AOP validation intercepts it; this distinguishes "annotations declared" from "runtime validation executed."

**Test 6 — Spring Boot integration:** use a real Spring context, verify only one `MethodValidationPostProcessor` is active, and confirm the exception matches the adaptation setting. Separate methods across two beans to avoid self-invocation.

**Test 7 — Controller:** separately test `@Valid @RequestBody` and direct constraints (such as `@Min` on `@RequestParam`), asserting the exception type, HTTP status, and body per Spring MVC version. Also test a return-value violation so server errors are not conflated with client input.

**Test 8 — Messages:** supply a `MessageSource` for the Vietnamese locale, verify `getResolvableErrors()` carries expected codes, and resolve the appropriate message. Keep the default message as fallback.

Tests on Spring-managed `@Validated` services can use JUnit and `assertThrows(...)`, provided calls pass through the real proxy. Tests catching `MethodValidationException` are valid only when the Spring version and adaptation configuration are active.

## 13. Self-Check Questions

**1. Why can the same `@Min(1)` violation produce two different exceptions?**  
Because Spring's AOP method validation has two reporting modes: raw `ConstraintViolationException` and adapted `MethodValidationException`. Configuration determines error representation, not the `@Min` rule itself.

**2. Do `ConstraintViolationException` and `MethodValidationException` share an inheritance relationship?**  
No. One belongs to Jakarta Validation and the other to Spring; both are runtime exceptions, yet they expose different data APIs.

**3. Does `validator.validate(bean)` throw `ConstraintViolationException` automatically?**  
No. It returns `Set<ConstraintViolation<T>>`. An interceptor, framework, or application code decides to throw if desired.

**4. Why is `MethodValidationException` convenient when reporting nested field errors?**  
Because the adapted result provides `ParameterErrors`, `FieldError`, and `MessageSourceResolvable`, fitting Spring message codes, i18n, and per-parameter mapping.

**5. When a controller returns HTTP 400 due to a direct constraint on `@RequestParam`, is it guaranteed to be `MethodValidationException`?**  
No. Spring MVC 6.1+ uses `HandlerMethodValidationException` for native controller method validation; handle it separately from service AOP exceptions.

**6. When a return-value constraint on a service is violated, what should be returned to the client?**  
Treat it as an unmet postcondition; the application should handle it as a server error or internal contract failure, not automatically blame client input.

**7. Which APIs inspect the method and distinguish input vs. return when using the adapted exception?**  
`ex.getMethod()`, `ex.getTarget()`, and `ex.isForReturnValue()`; read grouped results via `ex.getParameterValidationResults()` (Spring 6.2+).

## References

- [Jakarta Validation 3.0 specification — Error report: ConstraintViolationException](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html#constraintviolationexception)
- [Jakarta ConstraintViolationException API](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/ConstraintViolationException.html)
- [Jakarta ConstraintViolation API](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/ConstraintViolation.html)
- [Spring Framework 6.2 — Spring-driven method validation and exception adaptation](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html)
- [Spring Framework 6.2 — MethodValidationException API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/validation/method/MethodValidationException.html)
- [Spring Framework 6.2 — MethodValidationResult API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/validation/method/MethodValidationResult.html)
- [Spring Framework 6.2 — ParameterValidationResult API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/validation/method/ParameterValidationResult.html)
- [Spring Framework 6.2 — MethodValidationPostProcessor API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/validation/beanvalidation/MethodValidationPostProcessor.html)
- [Spring MVC — Validation and related exception types](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
