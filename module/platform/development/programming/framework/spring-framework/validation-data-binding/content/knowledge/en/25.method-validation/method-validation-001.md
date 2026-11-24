# Parameter and Return Value Constraints in Spring Framework

## 1. The Nature of Method Validation

Constraints on parameters and return values describe **the contract of a method**. Parameters are *preconditions* that the caller must satisfy before execution; the return value is a *postcondition* that the method must fulfill after execution. Jakarta Bean Validation lets you declare these rules using familiar annotations, rather than placing constraints only on DTO properties.

~~~java
public @NotBlank String createCode(
        @NotBlank String prefix,
        @Min(1) int sequence) {
    return prefix + "-" + sequence;
}
~~~

In the example, `prefix` must not be `null`, empty, or whitespace-only; `sequence` must be 1 or greater; and the returned string must not be blank. Constraints are placed on the **parameters** or **method**, so they validate the input/output values of an invocation rather than fields of an already-existing bean.

The easiest mistake to make: **annotations do not cause the JVM to automatically validate every call**. A component must perform the validation, such as a Spring AOP interceptor for services, Spring MVC 6.1+'s built-in method validation mechanism, or a manual `ExecutableValidator` call.

This lesson distinguishes three trigger points:

| Context | How it is triggered | Typical scenario |
| --- | --- | --- |
| Spring service/bean | Class-level `@Validated` and calls going through a Spring proxy | Validating service parameters and return results |
| Spring MVC 6.1+ handler | Constraints directly on handler parameters or return value; built into MVC | Returning HTTP errors for invalid input or invalid return values |
| Plain Jakarta Validation | `validator.forExecutables()` then calling `validateParameters` / `validateReturnValue` | Tests, custom integrations, understanding the underlying mechanism |

`@Valid` is a **cascaded validation** directive for nested objects, not a constraint forbidding `null` and not something that creates an interceptor on its own. With Spring Boot 3.x, the specification package is `jakarta.validation.*`; do not mix it with `javax.validation.*` from the previous generation.

## 2. Types of Executable Constraints

### 2.1. On Individual Parameters

~~~java
public void reserve(
        @NotBlank String sku,
        @Min(1) int quantity,
        @NotNull @Valid Address address) {
    // Business processing after parameters are valid.
}
~~~

`@NotBlank` checks `CharSequence`, `@Min` checks numeric values, `@NotNull` forbids null, and `@Valid` descends into the constraints of `Address` (for example, `@NotBlank city`). `@Valid` alone still treats `null` as valid; it must be combined with `@NotNull` if the object is required.

Be careful with null semantics: constraints like `@Min` and `@Size` typically accept null; this is by design so "requiredness" can be checked independently with `@NotNull`. Do not use `@NotBlank` on non-`CharSequence` types such as `Order` or `List<Order>`. If a value is numeric but sent over HTTP as a string, Spring performs binding/conversion before Jakarta Validation validates the post-conversion type.

### 2.2. On the Return Value

Place constraints on the **method declaration** to validate the result:

~~~java
@NotNull(message = "Return data not found")
public Customer findCustomer(String id) {
    // ...
}

@NotEmpty
public List<@NotNull @Valid Customer> getCustomers() {
    // ...
}
~~~

On the `findCustomer` method, `@NotNull` applies to the **return value**, not the `id` parameter. On the `getCustomers` method:
- `@NotEmpty` constrains the list to be non-null and have at least one element.
- `@NotNull` on the type argument forces each element of the list to be non-null.
- `@Valid` on the type argument requests cascading into each `Customer` object.

To apply constraints to elements of a custom container, Bean Validation also needs an appropriate `ValueExtractor`; for `List`/`Map`/`Optional`, common providers already include default extractors.

Comparison:

| Declaration | Is `null` an error? | Meaning |
| --- | --- | --- |
| `@NotNull Foo find()` | Yes | The result object must not be null |
| `@NotBlank String code()` | Yes | String must be non-null and contain non-whitespace characters |
| `@Size(min=1) List<?> items()` | No, if using only `@Size` | Only checks size when the list is non-null |
| `@NotNull @Size(min=1) List<?> items()` | Yes | List must exist and contain elements |
| `@Valid Foo load()` | No | Cascades when a result object is present |

Return value validation **takes place after the method body has already run**. A postcondition violation does not prove that the business logic caused no side effects, and does not by itself guarantee a transaction rollback.

### 2.3. Cross-Parameter Constraints

A rule such as "`startDate` is not after `endDate`" is not guaranteed merely by placing `@NotNull` on both parameters. That is a **cross-parameter constraint**, validating the `Object[]` representing the entire parameter set in a single invocation. Section 7 (see section 6 below) provides a full example.

### 2.4. Constructors

Jakarta Validation can also validate constructor parameters and the created object:
- `ExecutableValidator.validateConstructorParameters(...)`;
- `ExecutableValidator.validateConstructorReturnValue(...)`.

A regular Java `new` call **does not go through a Spring bean proxy**, so do not expect `@Validated` on a service to automatically trigger validation for all application constructors.

## 3. Runnable Example: Spring Boot 3.5.7, Java 17

The example includes a service that validates both parameters and return values, a controller demonstrating Spring MVC validation, and JUnit tests. It uses Spring Boot 3.5.7 (Spring Framework 6.2), Java 17, and Jakarta Validation.

File structure:

~~~text
pom.xml
src/main/java/com/example/demo/
  DemoApplication.java
  Customer.java
  CodeService.java
  CodeController.java
src/test/java/com/example/demo/
  CodeServiceTest.java
  CodeControllerTest.java
  ExecutableValidationTest.java
~~~

### 3.1. Dependencies

~~~xml
<!-- pom.xml -->
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
    <artifactId>method-validation-demo</artifactId>
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
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

`spring-boot-starter-validation` provides the Jakarta Validation API and provider (typically Hibernate Validator). `spring-boot-starter-aop` supports service-layer interception. `spring-boot-starter-web` is needed for the Spring MVC controller and `MockMvc` in tests.

### 3.2. Bootstrap

~~~java
// src/main/java/com/example/demo/DemoApplication.java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 3.3. Result Object with Nested Constraints

~~~java
// src/main/java/com/example/demo/Customer.java
package com.example.demo;

import jakarta.validation.constraints.NotBlank;

public final class Customer {
    @NotBlank(message = "Customer name must not be blank")
    private final String name;

    public Customer(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
~~~

### 3.4. Service Applying Method Constraints

~~~java
// src/main/java/com/example/demo/CodeService.java
package com.example.demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class CodeService {

    @NotBlank(message = "Returned code must not be blank")
    public String createCode(
            @NotBlank(message = "Prefix must not be blank") String prefix,
            @Min(value = 1, message = "Sequence must be at least 1") int sequence) {
        return prefix + "-" + sequence;
    }

    // Intentionally invalid to observe postcondition.
    @NotBlank(message = "Returned code must not be blank")
    public String brokenCode() {
        return "";
    }

    // @Valid deeply validates the returned object.
    @NotNull(message = "Customer must not be null")
    @Valid
    public Customer brokenCustomer() {
        return new Customer("");
    }
}
~~~

`@Validated` at the **class level** lets Spring recognize the bean as needing method validation. When the application calls `createCode(" ", 0)` through the proxy, both parameters violate constraints, and the interceptor reports errors before invoking the method body. `brokenCode()` runs and returns `""`, and then has its return value validated; `brokenCustomer()` fails because `Customer.name` violates `@NotBlank` after cascaded validation.

There is no need to call `Validator.validate(...)` inside service methods. Spring performs the checks via its integration once the bean and interceptor are configured.

### 3.5. JUnit Verifying Calls Through the Spring Proxy

~~~java
// src/test/java/com/example/demo/CodeServiceTest.java
package com.example.demo;

import jakarta.validation.ConstraintViolationException;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class CodeServiceTest {

    @Autowired
    CodeService service;

    @Test
    void acceptsValidParametersAndReturn() {
        assertEquals("ORD-7", service.createCode("ORD", 7));
    }

    @Test
    void rejectsInvalidParameters() {
        ConstraintViolationException ex = assertThrows(
                ConstraintViolationException.class,
                () -> service.createCode(" ", 0));
        assertEquals(2, ex.getConstraintViolations().size());
    }

    @Test
    void rejectsInvalidReturnValue() {
        ConstraintViolationException ex = assertThrows(
                ConstraintViolationException.class,
                service::brokenCode);
        assertEquals(1, ex.getConstraintViolations().size());
    }

    @Test
    void validatesReturnedObjectRecursively() {
        ConstraintViolationException ex = assertThrows(
                ConstraintViolationException.class,
                service::brokenCustomer);
        assertEquals(1, ex.getConstraintViolations().size());
        assertEquals("Customer name must not be blank",
                ex.getConstraintViolations().iterator().next().getMessage());
    }
}
~~~

**Expected result:** four tests PASS when `CodeService` is obtained from the Spring context. With Spring Boot 3.5's default AOP method validation mechanism, violations are typically wrapped in `jakarta.validation.ConstraintViolationException`. If the application configures `MethodValidationPostProcessor` in `adaptConstraintViolations` mode, it may receive `MethodValidationException` following Spring's error model; error-handling code must match the actual configuration.

If you manually call `new CodeService().createCode(" ", 0)` instead of using the injected bean, there is no proxy performing checks and the method may return `" -0"`. Placing annotations does not cause an ordinary Java object to be validated automatically.

## 4. Spring MVC: Constraints Directly on Handler Parameters and Return Values

Spring Framework 6.1 and later include **built-in method validation** for `@RequestMapping` handlers. When a method has actual constraints on parameters or on the return value, MVC validates the method contract. There is no need to place class-level `@Validated` on the controller in this approach.

### 4.1. Controller

~~~java
// src/main/java/com/example/demo/CodeController.java
package com.example.demo;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/codes")
public class CodeController {

    @GetMapping("/preview")
    @NotBlank(message = "Result must not be blank")
    public String preview(
            @RequestParam @NotBlank String prefix,
            @RequestParam @Min(1) int sequence) {
        return prefix + "-" + sequence;
    }
}
~~~

Do not add `@Validated` on `CodeController`: a class-level annotation will route method validation through an AOP proxy instead of Spring Framework 6.1+'s built-in MVC controller mechanism.

Valid request:

~~~http
GET /api/codes/preview?prefix=INV&sequence=3 HTTP/1.1
Host: localhost:8080
~~~

Response body:

~~~text
INV-3
~~~

If `prefix` is blank or `sequence=0`, Spring MVC method validation reports parameter errors. By default it throws `HandlerMethodValidationException`, corresponding to HTTP **400 Bad Request**. When the **return value** violates a constraint on the method, the same exception type corresponds to HTTP **500 Internal Server Error**, because it is a server-side output contract error.

### 4.2. MockMvc Test

~~~java
// src/test/java/com/example/demo/CodeControllerTest.java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CodeControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validRequest() throws Exception {
        mvc.perform(get("/api/codes/preview")
                .param("prefix", "INV")
                .param("sequence", "3"))
            .andExpect(status().isOk())
            .andExpect(content().string("INV-3"));
    }

    @Test
    void invalidParameter() throws Exception {
        mvc.perform(get("/api/codes/preview")
                .param("prefix", "")
                .param("sequence", "0"))
            .andExpect(status().isBadRequest());
    }
}
~~~

Expected result: a valid request receives HTTP 200 with body `INV-3`; an invalid request receives HTTP 400. The error body can be customized with `@ControllerAdvice`/`ProblemDetail`, so general tests should not assume a fixed error body format.

### 4.3. Is `@Valid @RequestBody` the Same as Method Validation?

Consider a handler that only has `@Valid` on the request object:

~~~java
@PostMapping("/orders")
public void submit(@Valid @RequestBody OrderForm form) {
    // ...
}
~~~

This is an **illustrative handler snippet**, assuming `OrderForm` is a DTO with field constraints. If there are no other direct method constraints, MVC typically applies validation to the individual argument and reports errors via `MethodArgumentNotValidException`.

If you add a constraint directly on a parameter:

~~~java
@PostMapping("/orders")
public void submit(
        @RequestParam @Min(1) int retries,
        @Valid @RequestBody OrderForm form) {
    // ...
}
~~~

`@Min(1)` activates method validation for the handler, and this mechanism includes nested validation for `OrderForm`. When there are violations, Spring MVC typically uses `HandlerMethodValidationException`. Cases with `Errors` or `BindingResult` immediately following a parameter have specific handling rules: the handler can still be invoked when all errors belong to parameters immediately followed by `Errors` and there are no errors on other parameters.

**Both exception types must be handled** when building an API with multiple handler styles: `MethodArgumentNotValidException` for standalone request object validation, and `HandlerMethodValidationException` for method validation.

## 5. Manual Validation with `ExecutableValidator`

The standard `jakarta.validation.executable.ExecutableValidator` interface defines these operations:
- `validateParameters(object, method, values, groups...)`: validates parameters and cross-parameter constraints.
- `validateReturnValue(object, method, returnValue, groups...)`: validates the return value, including cascades.
- `validateConstructorParameters(constructor, values, groups...)`.
- `validateConstructorReturnValue(constructor, createdObject, groups...)`.

These methods **do not invoke the business method**; they only evaluate the supplied values. This helps determine whether a bug lies in the constraint definition or in the Spring integration configuration.

~~~java
// src/test/java/com/example/demo/ExecutableValidationTest.java
package com.example.demo;

import jakarta.validation.Validation;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.executable.ExecutableValidator;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Method;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ExecutableValidationTest {

    @Test
    void manuallyChecksParametersAndResult() throws Exception {
        CodeService target = new CodeService();

        Method create = CodeService.class.getMethod(
                "createCode", String.class, int.class);
        Method broken = CodeService.class.getMethod("brokenCode");

        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {

            ExecutableValidator executable =
                    factory.getValidator().forExecutables();

            var invalidInput = executable.validateParameters(
                    target, create, new Object[]{" ", 0});

            var invalidResult = executable.validateReturnValue(
                    target, broken, "");

            assertEquals(2, invalidInput.size());
            assertEquals(1, invalidResult.size());
        }
    }
}
~~~

Run all tests:

~~~bash
mvn test
~~~

With the project and code above, **7 tests are expected to PASS**: 4 service, 2 MVC, and 1 Jakarta executable. If you only want to run the plain API test:

~~~bash
mvn -Dtest=ExecutableValidationTest test
~~~

Verbatim Maven logs cannot be asserted because logs depend on the runtime. This manual test invokes `ExecutableValidator` on a `new CodeService()`; thus it demonstrates that constraints can be validated **without a Spring proxy** when you call the API explicitly.

### 5.1. Property Path of a Method Violation

`ConstraintViolation#getPropertyPath()` contains common node kinds:
- `ElementKind.METHOD`: the method being validated.
- `ElementKind.PARAMETER`: the offending parameter.
- `ElementKind.CROSS_PARAMETER`: relationship across multiple parameters.
- `ElementKind.RETURN_VALUE`: the returned result.
- `ElementKind.PROPERTY`: nested property during cascading.

The path string may look like `createCode.arg0`, `createCode.prefix`, or `brokenCode.<return value>`. Parameter names can vary depending on the `-parameters` compiler flag and `ParameterNameProvider`, so error-handling code should prefer inspecting nodes and `Path.Node#getKind()` rather than hardcoding inferences from string names.

An illustrative node-traversal snippet, used inside a test where `invalidInput` already exists:

~~~java
for (var violation : invalidInput) {
    for (var node : violation.getPropertyPath()) {
        System.out.println(node.getKind() + ": " + node.getName());
    }
}
~~~

Do not assert fixed parameter names in stdout because provider/metadata may differ.

## 6. Cross-Parameter Constraints for Multiple Parameters

When a method has `start` and `end` both of type `LocalDate`, `@NotNull` ensures they exist but does not guarantee `start <= end`. You can declare an annotation targeting the parameter array and a validator with `ValidationTarget.PARAMETERS`.

### 6.1. Annotation

~~~java
// src/main/java/com/example/demo/ChronologicalDates.java
package com.example.demo;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target({ElementType.METHOD, ElementType.CONSTRUCTOR,
         ElementType.ANNOTATION_TYPE})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = ChronologicalDatesValidator.class)
public @interface ChronologicalDates {
    String message() default "Start date must be before or equal to end date";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

### 6.2. Validator

~~~java
// src/main/java/com/example/demo/ChronologicalDatesValidator.java
package com.example.demo;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import jakarta.validation.constraintvalidation.SupportedValidationTarget;
import jakarta.validation.constraintvalidation.ValidationTarget;
import java.time.LocalDate;

@SupportedValidationTarget(ValidationTarget.PARAMETERS)
public final class ChronologicalDatesValidator
        implements ConstraintValidator<ChronologicalDates, Object[]> {

    @Override
    public boolean isValid(Object[] args,
                           ConstraintValidatorContext context) {
        if (args == null || args.length != 2) {
            throw new IllegalArgumentException(
                    "ChronologicalDates requires exactly two parameters");
        }
        if (args[0] == null || args[1] == null) {
            return true; // Let @NotNull handle each individual parameter.
        }
        LocalDate start = (LocalDate) args[0];
        LocalDate end = (LocalDate) args[1];
        return !start.isAfter(end);
    }
}
~~~

`@SupportedValidationTarget(ValidationTarget.PARAMETERS)` clarifies that this constraint applies to **all parameters**, not the return value. The validator is suitable only for executables with exactly two `LocalDate` parameters. On a method, it looks like this:

~~~java
// Illustrative snippet inside a @Service @Validated class.
// Required imports: LocalDate, NotNull, and ChronologicalDates.
@ChronologicalDates
public void schedule(@NotNull LocalDate start,
                     @NotNull LocalDate end) {
    // ...
}
~~~

If `start` is after `end`, the custom constraint violation is a **cross-parameter** violation. By default, it does not automatically map to an `end` field in the UI. If you want a specific field path, you must build a custom violation on the right node and inspect `ConstraintViolation#getPropertyPath()` metadata.

When a constraint can target both return values and parameters, the specification requires disambiguating the target (for example, `validationAppliesTo` with `ConstraintTarget.PARAMETERS`). Do not write a `ConstraintValidator<..., Object[]>` as a return-value validator if the real intent is to validate relationships between parameters.

## 7. Groups, Inheritance, and Design Limitations

### 7.1. Validation Groups

The default group is `jakarta.validation.groups.Default`. You can define a custom group:

~~~java
public interface FinalSubmission {}

public void confirm(
        @NotBlank(groups = FinalSubmission.class) String token) {
    // ...
}
~~~

These are **two illustrative declarations**; the interface and method must be placed in appropriate classes. The `@NotBlank` constraint in the example belongs to `FinalSubmission`, so it does not run automatically when only the Default group is validated. You can choose `@Validated(FinalSubmission.class)` at the appropriate bean/method level for Spring integration, or call:

~~~java
// Illustrative snippet when executable, target, method, and args are available:
executable.validateParameters(
        target, method, args, FinalSubmission.class);
~~~

Combining groups with `@Valid` and `@ConvertGroup` requires careful design so the active group matches the business intent. Do not expect every group to run automatically in a single pass.

### 7.2. Inheritance / Interfaces

Jakarta Bean Validation requires method contracts to obey the substitution principle:

- **Do not strengthen preconditions** in a subtype: adding new parameter constraints in an overridden method that has no corresponding constraints in the base class/interface generally violates the specification.
- **Postconditions may be strengthened** in a subtype: adding a valid return constraint can be acceptable.
- Do not declare cascaded return `@Valid` repeatedly along the same inheritance branch where the specification forbids double cascading.

Example that is **invalid according to the specification rules**:

~~~java
interface Lookup {
    String find(String code);
}

class StrictLookup implements Lookup {
    @Override
    public String find(@NotBlank String code) {
        return code;
    }
}
~~~

`StrictLookup` adds a constraint for callers that were allowed to invoke `Lookup.find` with a blank string, so a provider may throw `ConstraintDeclarationException` when analyzing constraints. The right approach is to place the constraint on the contract:

~~~java
interface Lookup {
    String find(@NotBlank String code);
}

class NormalLookup implements Lookup {
    @Override
    public String find(String code) {
        return code;
    }
}
~~~

The two blocks are **two independent alternatives**; do not declare two `Lookup` interfaces in the same source file. When an interface is proxied, you should also test method validation from outside the bean, because proxy type and metadata can affect how the framework discovers annotations.

### 7.3. Not Every Method Is Proxied

Spring AOP uses proxies, so keep in mind:
- Self-invocation `this.otherMethod(...)` does not go through the proxy.
- `private` methods cannot normally be intercepted by Spring AOP proxies.
- `final` methods cannot be overridden by subclass proxies to attach interceptors; JDK dynamic proxy vs. class proxy configuration affects scope.
- `static` method constraints are not portable under Jakarta Bean Validation.
- Objects created with `new` outside the Spring context do not receive Spring interceptors.

For ordinary services, start with **public non-final methods on a Spring bean** called from another bean. Only consider weaving/AspectJ or manual validation if you have a specific requirement.

### 7.4. Return Validation and Asynchrony

With `CompletionStage<T>`, `CompletableFuture<T>`, or reactive publishers, constraints on the return type itself may only validate **the wrapper returned when the method completes**, without automatically waiting for future items. If you need to validate items emitted later, use integration designed for asynchronous pipelines. Do not mechanically attach `@Valid` and assume every future element has been evaluated.

## 8. Handling Exceptions at the Right Layer

There are three common forms:

| Exception | Where it typically occurs | Meaning |
| --- | --- | --- |
| `ConstraintViolationException` | Service method validation via proxy (common default) | Parameter or return violation |
| `MethodArgumentNotValidException` | Spring MVC validating a standalone `@Valid @RequestBody`/`@ModelAttribute` object | Invalid input object |
| `HandlerMethodValidationException` | Spring MVC 6.1+ built-in method validation | Method input (usually 400) or method return (usually 500) |

Spring AOP also has an optional `MethodValidationException` mode when adapting violations to `MethodValidationResult` via `MethodValidationPostProcessor`. Therefore, exception-handling code must account for the **Spring version** and active configuration.

For APIs, use `@ControllerAdvice`/`ResponseEntityExceptionHandler` to standardize error messages and HTTP status codes. Input errors should identify the parameter/field so the user can fix them; return errors are generally server-side errors and must not be masked as HTTP 400. Avoid directly returning rejected values containing tokens, passwords, or sensitive data.

In a controller, a `BindingResult` immediately after a form-style argument lets you handle errors inside the handler itself. However, with multiple parameters and direct method constraints, Spring MVC invokes the handler only if all validation errors belong to parameters immediately followed by `Errors`; errors on other parameters trigger `HandlerMethodValidationException`.

## 9. Common Pitfalls

1. **Confusing `@Valid` with `@Validated`:** `@Valid` cascades into objects; Spring's `@Validated` is tied to method validation and groups depending on context.
2. **Adding constraints without enabling validation:** you need a Spring proxy, MVC integration, or `ExecutableValidator`.
3. **Calling a service via `new` or `this`:** bypasses the Spring AOP interceptor.
4. **Adding class-level `@Validated` on a controller in Spring MVC 6.1+** while expecting built-in method validation; choose a consistent integration path.
5. **Catching only `MethodArgumentNotValidException`:** you must also account for `HandlerMethodValidationException` for direct method constraints.
6. **Mapping every violation to HTTP 400:** server return violations are different from invalid client input.
7. **Forgetting `@NotNull`:** constraints such as `@Min`/`@Size` do not necessarily treat null as invalid.
8. **Using the wrong constraint for the data type:** `@NotBlank` is only for `CharSequence`, `@Min` is for numbers.
9. **Adding parameter constraints in an override:** can violate inheritance rules and cause the provider to throw `ConstraintDeclarationException`.
10. **Relying on `arg0` names in paths:** parameter names can depend on `-parameters`/`ParameterNameProvider`.
11. **Assuming a return violation reverts side effects:** validation runs after the method body; transaction interceptor ordering can affect rollback behavior.
12. **Skipping nested/cross-parameter tests:** test valid values, invalid parameters, invalid return values, null, and cascading separately.

## 10. Implementation Checklist

- List preconditions for each parameter, cross-parameter rules, and return postconditions.
- Choose constraints matching the types; combine `@NotNull` and `@Valid` where needed.
- For services: `@Service @Validated`, a validation provider and AOP, and calls going through the Spring bean.
- For Spring MVC 6.1+ controllers: use direct constraints and the built-in MVC mechanism; handle HTTP 400/500 appropriately.
- Use `ExecutableValidator` to test contracts independently of Spring; inspect property paths by node kind.
- Handle inheritance, groups, proxy boundaries, and container/async return validation with proper semantics.
- Verify behavior with integration tests before using on business flows with side effects.

## References

- Spring Framework 6.2 — MVC Validation: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Boot 3.5 — Validation: https://docs.spring.io/spring-boot/3.5/reference/io/validation.html
- Jakarta Bean Validation — Method and constructor constraints, ExecutableValidator: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Jakarta Validation — ExecutableValidator API: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/executable/executablevalidator
- Hibernate Validator Reference Guide — Method constraints: https://docs.hibernate.org/stable/validator/reference/en-US/html_single/#chapter-method-constraints
