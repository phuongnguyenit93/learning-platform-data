# Experimenting with Parameter and Return-Value Validation via AOP Proxy in Spring Framework

## 1. Objectives of This Hands-On Lesson

A service in a Spring application can be called from a REST controller, message consumer, scheduled job, or another service. Validating data at the HTTP layer **does not guarantee** every call to the service is valid. Jakarta Bean Validation supports constraints on method parameters and return values; Spring can apply them automatically when calls pass through an **AOP proxy**.

Example:

~~~java
@Service
@Validated
public class StockService {

    public String allocate(
            @NotBlank String sku,
            @Min(1) int units) {
        return sku + ":" + units;
    }

    @NotBlank
    public String findReference() {
        return "";
    }
}
~~~

This is an **illustrative class** requiring imports to compile. When `StockService` is managed by Spring and proxied by `MethodValidationPostProcessor`:
- Calling `allocate("PEN", 2)` from another bean: succeeds.
- Calling `allocate("", 0)` **through the proxy**: checks parameters before the method body and throws `ConstraintViolationException`.
- Calling `findReference()` **through the proxy**: the method body executes, then the empty return value violates `@NotBlank` and throws `ConstraintViolationException`.
- Calling `new StockService().allocate("",0)` on a manually instantiated object without a proxy: the method body runs, unless the method itself validates explicitly.
- Inside the service, calling `this.allocate("",0)`: normally **bypasses advice** because it is a self-invocation on the target.

This lesson experiments with and tests:
1. Presence vs absence of a Spring-managed AOP proxy.
2. Parameter constraints before business logic executes.
3. Return-value constraints **after** the method returns.
4. `@Valid` cascading on a request/value object passed as a method parameter.
5. `ConstraintViolation#getPropertyPath()` and `ElementKind.PARAMETER/RETURN_VALUE`.
6. Direct calls on `new`-constructed objects, self-invocation, and calls through another bean.
7. Common issues with JDK/CGLIB proxies, `final`/`private`, validation groups, and transaction advice.
8. Distinguishing service AOP method validation from **built-in MVC method validation** introduced in Spring Framework 6.1.
9. JUnit/`SpringBootTest` and MockMvc tests with safe error mapping.
10. When to use `MethodValidationPostProcessor#setAdaptConstraintViolations(true)` and `MethodValidationException` instead of the default exception.

Example versions: **Java 17, Spring Boot 3.5.7, Spring Framework 6.2, Jakarta Validation, and JUnit Jupiter**. Complete project source files are provided, while other snippets are marked illustrative. Test results stated in this article are **expectations**, not a claim that Maven was actually executed.

## 2. Mechanism: Bean, Proxy, Interceptor, and ExecutableValidator

### 2.1. Execution Path Through Spring AOP

~~~text
Another bean or controller
       |
       v
Spring-managed StockService reference
       |
       v
[AOP Proxy: JDK dynamic proxy or CGLIB]
       |
       v
MethodValidationInterceptor
       |
       +-- ExecutableValidator.validateParameters(...)
       |        |
       |        +-- invalid -> ConstraintViolationException
       |
       v
Target StockService.allocate(...)
       |
       v
MethodValidationInterceptor
       |
       +-- ExecutableValidator.validateReturnValue(...)
       |        |
       |        +-- invalid -> ConstraintViolationException
       |
       v
Caller receives valid return value
~~~

In practice, Spring AOP may have multiple advisors/interceptors (validation, transactions, caching, retry...). Ordering depends on configuration and `order`, so the diagram above mainly illustrates **validation before the target body runs and validation after receiving the return value**. Do not infer from the diagram that transaction commit always occurs before/after return validation in a fixed order across all systems; write integration tests when advices have side effects.

Spring Framework uses `MethodValidationPostProcessor` to apply `MethodValidationInterceptor` to eligible beans. With Spring Boot, method validation is auto-configured when a Bean Validation provider is on the classpath—typically via `spring-boot-starter-validation`. The target class needs `@Validated` at the type level to be picked up by the postprocessor.

### 2.2. Both Sides of a Method Contract

~~~java
public @NotBlank String reserve(
        @NotBlank String sku,
        @Min(1) int units) {
    return sku + ":" + units;
}
~~~

- Constraints **on parameters** are checked before calling the target body.
- Constraints **on the return value** are placed on the method and checked after the target body finishes.
- `@Valid` on a parameter or return value enables *cascaded validation* of the object's properties; `@Valid` itself is not a null-check constraint.
- `@NotNull` on a parameter or return value explicitly forbids null.
- Validation normally applies to *public service methods invoked through a proxy*, not every Java statement inside the class.

### 2.3. More Than Just an Annotation

Adding `@NotBlank` to a method **does not automatically** cause every plain Java call to validate. You need:
- A Jakarta Bean Validation provider, such as Hibernate Validator.
- A Spring context creating Bean Validation infrastructure.
- `MethodValidationPostProcessor` and an appropriate proxy/advice.
- A bean annotated with `@Validated` per Spring-driven method validation configuration.
- Callers obtaining the bean from the context and **calling through the proxy**.

If you manually instantiate `new StockService()`, calling methods on that object bypasses the interceptor. If you obtain `StockService` via `@Autowired` from the Spring context, calls go through the protected proxy.

## 3. Distinguishing Spring `@Validated` and Jakarta `@Valid`

| Annotation | Where used | Meaning |
| --- | --- | --- |
| `org.springframework.validation.annotation.Validated` | Service class | Marks a bean for Spring-driven method validation; can select groups |
| `jakarta.validation.Valid` | Parameter, field, getter, return | Cascades validation into a nested object |
| `jakarta.validation.constraints.NotBlank` | String parameter/return/property | Non-null, non-empty, not whitespace-only |
| `jakarta.validation.constraints.Pattern` | String parameter/property | Matches regular expression |
| `jakarta.validation.constraints.Min` | Numeric parameter/property/return | Greater than or equal to threshold |
| `jakarta.validation.constraints.NotNull` | Parameter/return/property | Must not be null |
| `org.springframework.validation.beanvalidation.MethodValidationPostProcessor` | Spring infrastructure | Creates method-validation advisor/proxy |
| `jakarta.validation.executable.ExecutableValidator` | Jakarta API | Validates method parameters/return values directly |

A common mistake is placing only `@Valid` on a service class; that annotation **does not replace type-level `@Validated`** in Spring AOP method validation. Another mistake is using `@Validated` while putting only `@Valid` on an object parameter and assuming nulls will be rejected: to forbid null, add `@NotNull`.

One distinction to keep clear:
- **Spring MVC 6.1+** has its own built-in method validation for handler methods, e.g., direct `@Min` on `@RequestParam`; it can throw `HandlerMethodValidationException`.
- **Spring service AOP** in this lesson uses `MethodValidationPostProcessor` and, by default, throws `ConstraintViolationException`.
- Do not add class-level `@Validated` to a controller merely to trigger the new MVC validation; Spring docs recommend omitting class-level `@Validated` on controllers when using built-in MVC method validation. For a **service bean**, however, class-level `@Validated` is a prerequisite in this AOP example.

## 4. Exceptions: Parameter and Return Violations Must Be Distinguished

### 4.1. Default: `ConstraintViolationException`

The Spring method-validation interceptor typically throws:

~~~java
jakarta.validation.ConstraintViolationException
~~~

This exception holds `Set<ConstraintViolation<?>>`. Each violation has:
- `getPropertyPath()`: path through method/parameter/property/return value.
- `getConstraintDescriptor()`: constraint annotation and attributes.
- `getMessage()`: interpolated message.
- `getMessageTemplate()`: original template.
- `getInvalidValue()`: **the invalid value, which may be a secret**.
- `getRootBean()`, `getLeafBean()`: related object references.

**Never serialize `ConstraintViolation` or `ex.getMessage()` into public JSON.** The contents can leak inputs, Java method names, return values, regexes, or business data.

### 4.2. Use Path Node Kind Instead of Guessing from Strings

Jakarta Validation provides `jakarta.validation.ElementKind`:
- `ElementKind.PARAMETER` for a parameter.
- `ElementKind.RETURN_VALUE` for a return value.
- `ElementKind.PROPERTY` for a cascaded nested field.
- `ElementKind.METHOD` representing the method.
- `ElementKind.CROSS_PARAMETER` for constraints spanning multiple parameters.

Traversal example:

~~~java
// Snippet inside test or diagnostic code.
boolean isReturnViolation = violation.getPropertyPath()
        .iterator()
        .next()
        .getKind() == ElementKind.RETURN_VALUE;
~~~

**The snippet above only illustrates reading one node, not the right algorithm**: the first node of a method property path is usually `METHOD`, not `RETURN_VALUE`. The proper way is to **iterate all nodes** and check whether `RETURN_VALUE` is present (runnable code is in the tests section).

Do not rely on strings like `".<return value>"` or `"arg0"`, because parameter names can vary with `-parameters`, Hibernate Validator, providers, and method signatures. Rely solely on `Path.Node#getKind()` when classifying.

### 4.3. HTTP Error Mapping Needs Trust-Boundary Context

A `ConstraintViolationException` from a **service** can happen because:
- A client sent invalid input to the service.
- A controller called the service violating its contract due to a bug.
- A message consumer/background job called the service incorrectly.
- The service returned an invalid result, which is a server-side error.

Therefore, **do not write a global handler turning every `ConstraintViolationException` into HTTP 400**. In the project:
- Endpoint `/lab/proxy/allocate` knows for certain that the two parameters came from the client and calls a service method with no return constraint; it catches input errors at **this exact boundary** to return 400 with a generic public code.
- Endpoint `/lab/proxy/broken-return` triggers a service return violation, and the global handler returns a minimal 500.
- For service exceptions without sufficient context at the API boundary, the global handler defaults to 500 without leaking messages.

In production, you can add validation on the REST request side and translate errors intentionally rather than using a catch-all 400 that hides internal bugs.

### 4.4. Option: `MethodValidationException`

Since Spring Framework 6.1, `MethodValidationPostProcessor#setAdaptConstraintViolations(true)` makes the interceptor adapt violations into `MethodValidationResult` and throw `org.springframework.validation.method.MethodValidationException`. The result then carries `ParameterValidationResult`/`MessageSourceResolvable` and supports message localization.

**Optional configuration example, not enabled alongside the default demo:**

~~~java
@Configuration
class AdaptedMethodValidationConfig {

    @Bean
    public static MethodValidationPostProcessor methodValidationPostProcessor() {
        MethodValidationPostProcessor p =
                new MethodValidationPostProcessor();
        p.setAdaptConstraintViolations(true);
        return p;
    }
}
~~~

This is a **snippet** requiring imports for `org.springframework.context.annotation.Bean`, `Configuration`, and `org.springframework.validation.beanvalidation.MethodValidationPostProcessor`. When configuring in Boot, watch auto-configuration back-off so only the intended postprocessor exists; never register two method-validation postprocessor beans and accidentally get nested proxies/advice.

**Important:** when enabling this option, tests in the project expecting `ConstraintViolationException` must be updated to `MethodValidationException`. Never mix the flag inconsistently and claim identical behavior.

## 5. Runnable Hands-On Project (Java 17, Spring Boot 3.5.7)

The goal is **learning AOP proxies on services**, not turning the controller into a production inventory system. The project has a service with direct constraints, a nested DTO, a facade calling the service through a bean reference, and an HTTP adapter to observe results.

### 5.1. Structure

~~~text
pom.xml
src/main/java/com/example/methodaop/
  MethodAopApplication.java
  AllocationCommand.java
  StockService.java
  StockFacade.java
  StockLabController.java
  SafeMethodErrorAdvice.java
src/test/java/com/example/methodaop/
  StockServiceProxyTest.java
  ExecutableValidatorTest.java
  StockLabHttpTest.java
~~~

### 5.2. `pom.xml`

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
    <artifactId>method-validation-aop-lab</artifactId>
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

`spring-boot-starter-validation` provides the Bean Validation provider. Spring Boot 3.5 auto-configures method validation when a provider is present; `spring-boot-starter-aop` explicitly declares proxy infrastructure intent. You do not need to declare a `MethodValidationPostProcessor` manually in the **default demo**; Boot sets it up. If a real project disables auto-configuration or uses Spring Framework without Boot, register the postprocessor per the official guide.

### 5.3. `MethodAopApplication.java`

~~~java
// src/main/java/com/example/methodaop/MethodAopApplication.java
package com.example.methodaop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MethodAopApplication {
    public static void main(String[] args) {
        SpringApplication.run(MethodAopApplication.class, args);
    }
}
~~~

### 5.4. `AllocationCommand.java`: Cascading on a Record

~~~java
// src/main/java/com/example/methodaop/AllocationCommand.java
package com.example.methodaop;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

public record AllocationCommand(
        @NotBlank
        @Pattern(regexp = "[A-Z]{3,8}")
        String sku,

        @Min(1)
        int units) {
}
~~~

- `@NotBlank` rejects null, empty, or whitespace-only strings.
- `@Pattern` allows only 3 to 8 `A–Z` letters, making it easy to verify an input with a canary marker gets blocked. The regex is a demo rule, not a universal SKU policy.
- `@Min(1)` checks the unit count.
- The record is immutable; the service method accepts it with `@Valid` to cascade validation. Add `@NotNull` on the method parameter to forbid null objects.

### 5.5. `StockService.java`: Where AOP Actually Operates

~~~java
// src/main/java/com/example/methodaop/StockService.java
package com.example.methodaop;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

import java.util.concurrent.atomic.AtomicInteger;

@Service
@Validated
public class StockService {

    private final AtomicInteger executions = new AtomicInteger();

    public String allocate(
            @NotBlank @Pattern(regexp = "[A-Z]{3,8}") String sku,
            @Min(1) int units) {

        executions.incrementAndGet();
        return sku + ":" + units;
    }

    public String allocateCommand(
            @NotNull @Valid AllocationCommand input) {

        executions.incrementAndGet();
        return input.sku() + ":" + input.units();
    }

    @NotBlank
    public String brokenReference() {
        // Intentionally return an empty string to test the return constraint.
        return "";
    }

    // Wrapper method with no constraints.
    public String callThroughThis() {
        // Self-invocation on target, does not re-enter the proxy.
        return this.allocate("", 0);
    }

    public int executionCount() {
        return executions.get();
    }
}
~~~

**Key experimental points:**

1. `@Service` so Spring registers the bean.
2. Class-level `@Validated` so Spring's method-validation postprocessor targets it.
3. `@NotBlank`, `@Pattern`, `@Min` directly on `allocate` parameters.
4. `@NotNull @Valid` on `allocateCommand`: null objects and nested fields are checked separately.
5. `@NotBlank` on `brokenReference()` is a constraint **on the method return value**.
6. `AtomicInteger` observes whether the method body actually ran.
7. `callThroughThis()` intentionally calls `this.allocate("",0)` to demonstrate self-invocation bypass. **Never copy this anti-pattern into production business code.**

On a call **through the proxy** with invalid parameters, `executions` does not increment because the interceptor rejects before the target body runs. When `brokenReference()` returns `""`, the target body has already executed; the interceptor then reports the return-value violation.

`StockService` implements no interfaces and is **not final**. With standard class-based proxy configuration, Spring creates a CGLIB subclass; tests only assert an AOP proxy exists, without depending on generated proxy class names or `$$SpringCGLIB$$` markers.

### 5.6. `StockFacade.java`: Call Going Through Another Bean

~~~java
// src/main/java/com/example/methodaop/StockFacade.java
package com.example.methodaop;

import org.springframework.stereotype.Component;

@Component
public class StockFacade {

    private final StockService stock;

    public StockFacade(StockService stock) {
        this.stock = stock;
    }

    public String allocateInvalidThroughDependency() {
        // Injected reference is a Spring-managed bean/proxy.
        return stock.allocate("", 0);
    }

    public String allocateValidThroughDependency() {
        return stock.allocate("PEN", 2);
    }
}
~~~

Execution path:

~~~text
StockFacade.allocateInvalidThroughDependency()
     |
     v
Injected StockService proxy
     |
     v
MethodValidationInterceptor.validateParameters(...)
     |
     v
ConstraintViolationException (target allocate() never runs)
~~~

By contrast, `StockService.callThroughThis()` is already executing on the target and calls `this.allocate("",0)`; that internal call never goes back through the proxy. Do not fix this by calling `AopContext.currentProxy()` if you can refactor into a separate collaborator bean; `AopContext` couples code to AOP proxy exposure.

### 5.7. `StockLabController.java`: HTTP Boundary Separating Input and Internal Bugs

~~~java
// src/main/java/com/example/methodaop/StockLabController.java
package com.example.methodaop;

import jakarta.validation.ConstraintViolationException;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/lab/proxy")
public class StockLabController {

    private final StockService stock;

    public StockLabController(StockService stock) {
        this.stock = stock;
    }

    @GetMapping("/allocate")
    public ResponseEntity<?> allocate(
            @RequestParam String sku,
            @RequestParam int units) {

        // This endpoint passes ONLY these TWO client inputs
        // to allocate, which has NO return constraint.
        try {
            return ResponseEntity.ok(
                    Map.of("receipt", stock.allocate(sku, units)));
        } catch (ConstraintViolationException invalidInput) {
            // Intentional mapping only at this exact trust boundary.
            // Never return invalidInput.getMessage().
            return ResponseEntity.badRequest()
                    .body(Map.of("code", "INVALID_ALLOCATION_INPUT"));
        }
    }

    @GetMapping("/broken-return")
    public String brokenReturn() {
        // A service return-value violation must be 500.
        return stock.brokenReference();
    }
}
~~~

Here `ConstraintViolationException` is caught locally in `allocate` because we know **directly** that the called method takes two request inputs and has no return constraint. In a real service with many operations, never blindly treat every `ConstraintViolationException` as a client error.

If `units=abc`, Spring MVC fails while parsing `@RequestParam int` **before** calling the service. That error is `MethodArgumentTypeMismatchException` from the argument resolver, not an AOP `ConstraintViolationException`. The demo has a dedicated safe handler for that case, while keeping the focus on proxy-based validation.

### 5.8. `SafeMethodErrorAdvice.java`: Never Leak Service Details

~~~java
// src/main/java/com/example/methodaop/SafeMethodErrorAdvice.java
package com.example.methodaop;

import jakarta.validation.ConstraintViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

import java.util.Map;

@RestControllerAdvice
public class SafeMethodErrorAdvice {

    @ExceptionHandler(ConstraintViolationException.class)
    public ResponseEntity<Map<String, String>> internalContractFailure(
            ConstraintViolationException ignored) {

        // Outside the allocate endpoint, do not assume a
        // service exception is a client error: default to 500.
        return ResponseEntity.status(
                HttpStatus.INTERNAL_SERVER_ERROR)
                .body(Map.of("code", "INTERNAL_METHOD_CONTRACT_ERROR"));
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<Map<String, String>> badQueryType(
            MethodArgumentTypeMismatchException ignored) {

        // Do not echo raw query value or converter exception.
        return ResponseEntity.badRequest()
                .body(Map.of("code", "INVALID_QUERY_TYPE"));
    }
}
~~~

Never return `getMessage()`, `getInvalidValue()`, or `getPropertyPath()` verbatim in HTTP responses. In production, standardize error formatting with `ProblemDetail`, define public codes/paths/messages explicitly, keep logs/traces safe, and enforce authorization in the service.

## 6. Spring Context Tests: Proving the Method Interceptor Works

### 6.1. `StockServiceProxyTest.java`

~~~java
// src/test/java/com/example/methodaop/StockServiceProxyTest.java
package com.example.methodaop;

import jakarta.validation.ConstraintViolationException;
import jakarta.validation.ElementKind;
import jakarta.validation.ConstraintViolation;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.validation.beanvalidation.MethodValidationPostProcessor;

import java.util.Set;
import java.util.stream.StreamSupport;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class StockServiceProxyTest {

    @Autowired
    StockService stock;

    @Autowired
    StockFacade facade;

    @Autowired
    ApplicationContext context;

    private static boolean hasNodeKind(
            ConstraintViolation<?> violation, ElementKind expected) {
        return StreamSupport.stream(
                violation.getPropertyPath().spliterator(), false)
                .anyMatch(node -> node.getKind() == expected);
    }

    @Test
    void springBeanIsActuallyAnAopProxy() {
        assertTrue(AopUtils.isAopProxy(stock));

        assertFalse(context.getBeansOfType(
                MethodValidationPostProcessor.class).isEmpty());
    }

    @Test
    void invalidParametersThrowBeforeBusinessBodyRuns() {
        int before = stock.executionCount();

        ConstraintViolationException error =
                assertThrows(ConstraintViolationException.class,
                        () -> stock.allocate(
                                "CANARY_PRIVATE_SKU", 0));

        assertEquals(before, stock.executionCount());
        assertTrue(error.getConstraintViolations().stream()
                .anyMatch(v -> hasNodeKind(
                        v, ElementKind.PARAMETER)));

        // Do not assert exact exception.getMessage(): it may
        // contain input, parameter names, or provider-specific text.
    }

    @Test
    void validParametersRunBodyAndReturnExpectedValue() {
        int before = stock.executionCount();

        String receipt = stock.allocate("PEN", 2);

        assertEquals("PEN:2", receipt);
        assertEquals(before + 1, stock.executionCount());
    }

    @Test
    void returnConstraintIsCheckedAfterMethodBody()
            throws Exception {

        ConstraintViolationException error =
                assertThrows(ConstraintViolationException.class,
                        () -> stock.brokenReference());

        assertTrue(error.getConstraintViolations().stream()
                .anyMatch(v -> hasNodeKind(
                        v, ElementKind.RETURN_VALUE)));
    }

    @Test
    void manuallyConstructedObjectHasNoSpringProxy() {
        StockService plain = new StockService();

        assertFalse(AopUtils.isAopProxy(plain));
        assertEquals(":0", plain.allocate("", 0));
        assertEquals(1, plain.executionCount());
    }

    @Test
    void selfInvocationSkipsMethodValidationAdvice() {
        int before = stock.executionCount();

        // Outer call enters target; this.allocate bypasses proxy.
        String result = stock.callThroughThis();

        assertEquals(":0", result);
        assertEquals(before + 1, stock.executionCount());
    }

    @Test
    void injectedProxyFromAnotherBeanStillRejectsInvalidInput() {
        int before = stock.executionCount();

        assertThrows(ConstraintViolationException.class,
                () -> facade.allocateInvalidThroughDependency());

        assertEquals(before, stock.executionCount());
    }

    @Test
    void facadeCanCallValidServiceMethod() {
        int before = stock.executionCount();

        assertEquals("PEN:2",
                facade.allocateValidThroughDependency());

        assertEquals(before + 1, stock.executionCount());
    }

    @Test
    void cascadeValidationChecksNestedRecordProperties() {
        AllocationCommand invalid =
                new AllocationCommand("", 0);

        ConstraintViolationException error =
                assertThrows(ConstraintViolationException.class,
                        () -> stock.allocateCommand(invalid));

        Set<String> paths = error.getConstraintViolations()
                .stream()
                .map(v -> v.getPropertyPath().toString())
                .collect(java.util.stream.Collectors.toSet());

        assertTrue(paths.stream().anyMatch(
                path -> path.contains("sku")));
        assertTrue(paths.stream().anyMatch(
                path -> path.contains("units")));
    }

    @Test
    void notNullProtectsNullCommand() {
        assertThrows(ConstraintViolationException.class,
                () -> stock.allocateCommand(null));
    }

    @Test
    void validNestedCommandRunsBody() {
        int before = stock.executionCount();

        assertEquals("PEN:2",
                stock.allocateCommand(
                        new AllocationCommand("PEN", 2)));

        assertEquals(before + 1, stock.executionCount());
    }
}
~~~

**11 JUnit methods** in this class. Key points:
- `AopUtils.isAopProxy(stock)` proves the injected object is not a plain POJO.
- `MethodValidationPostProcessor` exists in the context.
- Invalid inputs are blocked **before** incrementing inside the target.
- Invalid returns are identified via `ElementKind.RETURN_VALUE`.
- `new StockService()` and `this.allocate(...)` bypass advice, so method-level target checks **do not run automatically**.
- Calls from `StockFacade` via the injected bean reference pass through the proxy.
- `@NotNull @Valid` checks the nested record, not just primitive/direct scalar constraints.
- Do not rely solely on exact parameter paths like `arg0` or `sku`, as parameter-name discovery and providers can differ.

### 6.2. Why Is the Self-Invocation Test Meaningful?

When a client calls `stock.callThroughThis()`, the **outer** call goes through the proxy. However, `callThroughThis` has no direct parameter/return constraints. The target method runs and executes:

~~~java
return this.allocate("", 0);
~~~

This is a call via `this` on the **target**. The proxy does not intercept `allocate`, so invalid parameters are not checked during that internal call. The demo intentionally returns `":0"` and increments the execution count to expose this blind spot.

Production fixes:
1. Extract the validated logic into a **separate bean** and inject that bean.
2. Ensure all critical business entry points invoke the method through the Spring-managed bean.
3. If a method must be safe under every call including direct ones, enforce invariants inside the domain method itself or validate explicitly.
4. Never rely on proxy advice as the sole security boundary.
5. Use self-injection or `AopContext` only when you truly understand circular-dependency/coupling risks; refactoring into collaborator beans is usually cleaner.

## 7. Jakarta ExecutableValidator: Control Experiment Without a Proxy

AOP is simply Spring's way of invoking Jakarta's `ExecutableValidator` automatically. We can call the validator **directly** to check method parameters/return values, even on objects created with `new`, whenever a `jakarta.validation.Validator` is configured.

### 7.1. How the API Works

~~~java
ExecutableValidator executable =
        validator.forExecutables();

Set<ConstraintViolation<StockService>> parameterErrors =
        executable.validateParameters(
                plainTarget,
                method,
                new Object[]{"CANARY_BAD_SKU", 0});

Set<ConstraintViolation<StockService>> returnErrors =
        executable.validateReturnValue(
                plainTarget,
                returnMethod,
                "");
~~~

This is a snippet inside a test method requiring imports and variables from `ExecutableValidatorTest`. It is not a proxy call. Therefore:
- `ExecutableValidator` can detect constraints on a plain POJO.
- It **does not stop the method body from running** unless the caller stops before invoking it.
- The caller decides whether to throw an exception or handle violations.
- Spring AOP automates pre/post checks and throws exceptions per configuration.

### 7.2. `ExecutableValidatorTest.java`

~~~java
// src/test/java/com/example/methodaop/ExecutableValidatorTest.java
package com.example.methodaop;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.ElementKind;
import jakarta.validation.Validator;
import jakarta.validation.executable.ExecutableValidator;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.lang.reflect.Method;
import java.util.Set;
import java.util.stream.StreamSupport;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class ExecutableValidatorTest {

    @Autowired
    Validator validator;

    @Test
    void directExecutableValidatorFindsParameterViolations()
            throws Exception {

        StockService target = new StockService();
        Method method = StockService.class.getMethod(
                "allocate", String.class, int.class);

        ExecutableValidator executable =
                validator.forExecutables();
        Set<ConstraintViolation<StockService>> errors =
                executable.validateParameters(
                        target, method,
                        new Object[]{"CANARY_INVALID_SKU", 0});

        assertTrue(errors.size() >= 2);
        assertTrue(errors.stream().anyMatch(v ->
                StreamSupport.stream(
                        v.getPropertyPath().spliterator(), false)
                        .anyMatch(n -> n.getKind()
                                == ElementKind.PARAMETER)));

        // Calling validateParameters alone does not run the method body.
        assertEquals(0, target.executionCount());
    }

    @Test
    void directExecutableValidatorChecksReturnValue()
            throws Exception {

        StockService target = new StockService();
        Method method = StockService.class.getMethod(
                "brokenReference");

        Set<ConstraintViolation<StockService>> errors =
                validator.forExecutables().validateReturnValue(
                        target, method, "");

        assertFalse(errors.isEmpty());
        assertTrue(errors.stream().anyMatch(v ->
                StreamSupport.stream(
                        v.getPropertyPath().spliterator(), false)
                        .anyMatch(n -> n.getKind()
                                == ElementKind.RETURN_VALUE)));
    }
}
~~~

**2 JUnit methods**. `validateParameters` takes the target object, `Method`, and argument array in exact reflection order. `validateReturnValue` takes the target, method, and actual return value. For constructors, Jakarta has separate `validateConstructorParameters`/`validateConstructorReturnValue` APIs, which we do not need here.

Never log `getInvalidValue()`. In tests, check constraint annotation types, path node kinds, or minimum counts; **never expose `ConstraintViolation` objects publicly**.

## 8. HTTP Integration: Observing Statuses Without Leaking Internals

### 8.1. `StockLabHttpTest.java`

~~~java
// src/test/java/com/example/methodaop/StockLabHttpTest.java
package com.example.methodaop;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class StockLabHttpTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validInputCrossesProxyAndProducesReceipt()
            throws Exception {

        mvc.perform(get("/lab/proxy/allocate")
                    .param("sku", "PEN")
                    .param("units", "2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.receipt")
                        .value("PEN:2"));
    }

    @Test
    void invalidUserInputMapsToSafe400AtSpecificBoundary()
            throws Exception {

        mvc.perform(get("/lab/proxy/allocate")
                    .param("sku", "CANARY_SECRET_SKU")
                    .param("units", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_ALLOCATION_INPUT"))
                .andExpect(content().string(not(
                        containsString("CANARY_SECRET_SKU"))))
                .andExpect(content().string(not(
                        containsString("ConstraintViolationException"))))
                .andExpect(content().string(not(
                        containsString("allocate.sku"))));
    }

    @Test
    void brokenServiceReturnMapsToSafe500()
            throws Exception {

        mvc.perform(get("/lab/proxy/broken-return"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.code")
                        .value("INTERNAL_METHOD_CONTRACT_ERROR"))
                .andExpect(content().string(not(
                        containsString("brokenReference"))))
                .andExpect(content().string(not(
                        containsString("ConstraintViolationException"))));
    }

    @Test
    void wrongQueryTypeNeverEchoesRawValue()
            throws Exception {

        mvc.perform(get("/lab/proxy/allocate")
                    .param("sku", "PEN")
                    .param("units", "CANARY_NOT_AN_INT"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_QUERY_TYPE"))
                .andExpect(content().string(not(
                        containsString("CANARY_NOT_AN_INT"))));
    }
}
~~~

**4 JUnit methods**. They test three distinct paths:
- Valid query → Spring argument conversion succeeds → service proxy → 200.
- Query with valid integer failing `@Min` or SKU failing `@Pattern` → service AOP rejects and the endpoint maps input safely to 400.
- Unparseable `int` query → fails in MVC resolver before reaching the service, handled via `MethodArgumentTypeMismatchException`.
- Service returning a constraint-violating value → minimal 500 without leaking internals.

These tests do not cover full production authentication, transactions, or database rollback; those are separate topics.

### 8.2. Test Count

| Test class | Methods | Expected |
| --- | ---: | --- |
| `StockServiceProxyTest` | 11 | Proxy, parameter, return, self-invocation, cascade |
| `ExecutableValidatorTest` | 2 | Direct validator |
| `StockLabHttpTest` | 4 | HTTP + trust boundary |
| **Total** | **17** | **17 expected JUnit test runs** |

There are no parameterized tests in this project, so method count equals invocation count. If adding parameterized tests, count invocations rather than just annotations.

### 8.3. Run Commands

~~~bash
mvn test
~~~

Run only service AOP tests:

~~~bash
mvn -Dtest=StockServiceProxyTest test
~~~

Run only executable validation tests:

~~~bash
mvn -Dtest=ExecutableValidatorTest test
~~~

Run only MockMvc tests:

~~~bash
mvn -Dtest=StockLabHttpTest test
~~~

**Expected result:** 17 tests PASS given exact files and dependencies as shown, in Spring Boot 3.5.7/Java 17. This is static analysis, **not a Maven execution report**. When actually running, verify pass/failure counts in Surefire XML and inspect Spring Boot logs if the context fails to create a proxy as expected.

If `isAopProxy(stock)` returns false, do not rush to delete the assertion. Check `spring-boot-starter-validation`, `@Service`, class-level `@Validated`, bean injection from the context, the Bean Validation provider, and the method-validation postprocessor. If the context uses `spring.aop.proxy-target-class` or a custom proxy factory, the proxy class/type may change, yet `AopUtils.isAopProxy` remains the right check.

## 9. Curl: Testing Service Validation from Outside

Start the application:

~~~bash
mvn spring-boot:run
~~~

### 9.1. Valid Input

~~~bash
curl -i "http://localhost:8080/lab/proxy/allocate?sku=PEN&units=2"
~~~

Expected response:

~~~json
{"receipt":"PEN:2"}
~~~

### 9.2. Invalid but Parseable SKU/Quantity

~~~bash
curl -i "http://localhost:8080/lab/proxy/allocate?sku=CANARY_SECRET_SKU&units=0"
~~~

The request reaches the service proxy. SKU violates `@Pattern`, and `units=0` violates `@Min(1)`. The controller returns only:

~~~json
{"code":"INVALID_ALLOCATION_INPUT"}
~~~

with HTTP 400. It omits the `ConstraintViolation` array and raw canary string from the response.

### 9.3. Wrong Query Type — Never Reaches Service

~~~bash
curl -i "http://localhost:8080/lab/proxy/allocate?sku=PEN&units=ABC"
~~~

Spring MVC cannot convert `ABC` to `int`, so `SafeMethodErrorAdvice` returns HTTP 400:

~~~json
{"code":"INVALID_QUERY_TYPE"}
~~~

This is **not** an `@Min` failure in AOP; it happens during MVC argument resolution/type conversion.

### 9.4. Invalid Return Value

~~~bash
curl -i "http://localhost:8080/lab/proxy/broken-return"
~~~

The service's `brokenReference()` method returns an empty string, caught by the interceptor **after the method executes**. Global advice returns 500:

~~~json
{"code":"INTERNAL_METHOD_CONTRACT_ERROR"}
~~~

It never turns into 400 and never prints Java method names or exception messages to the client.

Shell commands use standard `curl`. Query URLs containing spaces or special characters should use `--get --data-urlencode`; in production, **never put credentials/tokens in URLs**, because access logs and proxies can record query strings.

## 10. AOP Proxy Experiment: JDK vs CGLIB

Spring AOP uses proxies, with two main mechanisms:

| Characteristic | JDK dynamic proxy | CGLIB class proxy |
| --- | --- | --- |
| Mechanism | Implements interfaces | Subclasses target class |
| Best suited for | Beans with interfaces, callers inject interface | Bean classes without interfaces or forced class proxy |
| Advisable methods | Primarily methods exposed via interface | Overridable methods |
| `final class` | Interface proxy may work depending on design | Cannot subclass a final class |
| `final method` | Does not rely on subclass override | Cannot advise via subclass override |
| `private method` | Cannot be called via public interface proxy | Cannot override/advise |
| Self-invocation via `this` | Bypasses | Bypasses |
| Stable check | `AopUtils.isAopProxy` | `AopUtils.isAopProxy` |

Because `StockService` implements no interfaces, Spring can use CGLIB. If switched to:

~~~java
public interface StockOperations {
    String allocate(String sku, int units);
}
~~~

and `StockService implements StockOperations`, a JDK proxy may expose only the interface type, making concrete-class injection fail if configured for interface-based proxies. When switching proxy modes, test bean wiring and method annotations. Never put `@Validated`/constraints across interfaces and implementations in ways that violate **Jakarta Bean Validation inheritance rules**: an overriding method must not arbitrarily add parameter constraints that strengthen preconditions.

**Avoid `final` on Spring service classes needing class-based proxies.** Java records are implicitly `final`, making them great immutable input/output DTOs but unsuitable for Spring CGLIB method-validation proxies. Likewise, `private`/`final` methods must not be relied upon as the sole guard for security invariants when depending on proxies.

### 10.1. Proxy Checks in Tests

~~~java
// Snippet in a test where stock is injected:
assertTrue(AopUtils.isAopProxy(stock));

Class<?> visibleClass = stock.getClass();
System.out.println(visibleClass.getName());
~~~

Never hardcode proxy class name strings in assertions; generated names change across versions and configurations. To inspect the target type, Spring provides `AopUtils.getTargetClass(stock)`, though you should never serialize that class info into public APIs either.

Never use `stock.getClass()==StockService.class` as a success condition: when proxied, `getClass()` will be a subclass or JDK proxy type.

## 11. Self-Invocation and Other Blind Spots

### 11.1. Self-Invocation via `this`

~~~text
External caller
   |
   v
Spring proxy
   |
   v
Target.callThroughThis()
   |
   +--> this.allocate("",0)   <-- does not re-enter proxy
             |
             v
          body executes
~~~

A test calling only `stock.allocate("",0)` externally will pass and mislead reviewers into thinking the service is always protected. A later refactoring moving a call inside the same class via `this.allocate` will bypass advice. That is why `selfInvocationSkipsMethodValidationAdvice` serves as a warning test.

### 11.2. Objects Created with `new`

~~~java
StockService plain = new StockService();
String value = plain.allocate("", 0);
~~~

Without manual validation in the method body, this call returns `":0"` because there is no Spring proxy. Never turn direct POJO instantiation into a production pattern for a service relying on AOP method validation. In unit tests, `new` is fine for testing pure method-body behavior; to test **method validation**, use a Spring context or call `ExecutableValidator` explicitly.

### 11.3. `@PostConstruct`, Constructors, and Lifecycle

Proxy-based advice does not apply to all work inside constructors or initialization callbacks. Calling another method on the same bean from `@PostConstruct` is likewise not an external call through the proxy. Do not rely on method-validation AOP to validate a bean itself during initialization; use constructor invariants, explicit Bean Validation, or Spring configuration validation instead.

### 11.4. Scheduled, Async, and Transactional Methods

`@Scheduled`, `@Async`, and `@Transactional` also interact with proxies, lifecycles, and contexts. Methods may run on different threads, through different proxies, or with different advice orders. Never assume a return-validation failure always happens **before transaction commit** in every configuration.

In systems with side effects:
- Parameter validation runs before target invocation when passing through the validation interceptor.
- Return validation runs after the target body completes, yet its order relative to transaction/retry advisors can shift commit/rollback timing.
- If a return violation must trigger rollback, write a real integration test with the transaction manager/database rather than merely asserting `ConstraintViolationException`.
- With `CompletableFuture`, reactive publishers, or suspend functions, “return value” semantics can differ from asynchronously emitted values; check framework support and test specifically.

### 11.5. Unproxied Beans

If `@Validated` is placed on an object not registered as a bean, or outside component scanning, no interceptor is applied. Common causes:
- `StockService` instantiated with `new` in a controller instead of injected.
- `spring-boot-starter-validation` or provider disabled/excluded.
- Bean class is `final` when a CGLIB subclass is required.
- Calling a `private`/`final` method expecting advice.
- Grabbing the raw target object instead of the proxy from the context.
- `@SpringBootTest` using `@MockBean` or custom test config replacing the real service with a mock; Mockito stubs can bypass method interceptors.
- `@Validated` accidentally removed from the service class during refactoring.
- A custom `BeanPostProcessor` altering the proxy chain/order.

## 12. Validation Groups and Method Constraint Inheritance

### 12.1. Groups on `@Validated`

Jakarta constraints support `groups`:

~~~java
public interface StrictChecks {}

@Min(value = 10, groups = StrictChecks.class)
private int minimum;
~~~

This is a **snippet**, not a class in the demo. Spring `@Validated(StrictChecks.class)` can select a validation group for the bean/method. When selecting only `StrictChecks`, constraints belonging to `Default` do not necessarily run; if both are desired, configure group inheritance or a group sequence accordingly.

In production services:
- Use groups only when there is a real use case, such as create/update or tier-specific checks.
- Write tests proving the intended group actually runs through the proxy.
- Never use validation groups as authorization; an unauthorized user cannot simply switch groups to bypass protected data checks.

### 12.2. Parameter Constraints on Inherited Methods

Jakarta Bean Validation enforces a **no strengthening preconditions** rule when overriding/implementing methods: you cannot arbitrarily add parameter constraints in an implementation when the interface/base method does not declare the matching contract under allowed rules. Return constraints follow postcondition rules; there are cases where postconditions can be strengthened without violation.

Example requiring careful review:

~~~java
interface AllocationApi {
    String allocate(String sku, int units);
}

class RestrictedAllocation implements AllocationApi {
    @Override
    public String allocate(@NotBlank String sku, int units) {
        return sku;
    }
}
~~~

This is an **illustrative anti-pattern**, not part of the runnable project. Hibernate Validator can throw `ConstraintDeclarationException` because the implementation adds a parameter constraint on an inherited method illegally. Declare executable constraints consistently on the interface/base contract and test whenever switching between JDK and CGLIB proxies.

## 13. Response Security, Logging, and Data Failure Handling

### 13.1. Never Expose `ConstraintViolationException` Directly

An unsafe handler:

~~~java
// Never use for REST responses:
@ExceptionHandler(ConstraintViolationException.class)
public Object unsafe(ConstraintViolationException ex) {
    return ex.getConstraintViolations();
}
~~~

`ConstraintViolation#getInvalidValue()` can hold passwords, access tokens, emails, or nested domain objects. `getPropertyPath()` can expose internal method/class names. `getMessage()` can contain raw input via custom interpolators/validators. Generic serialization can leak far more metadata than intended.

The demo's safe handler returns only a fixed `code`; larger systems can use `ProblemDetail` with allowlisted public codes/paths/messages and localization from `MessageSource`.

### 13.2. Do Not Automatically Log Raw Exception Messages

~~~java
// Avoid for sensitive inputs:
logger.warn("Method validation failed: {}", ex.getMessage());
~~~

In some providers, `ConstraintViolationException`'s message includes method/parameter names and interpolated messages; custom messages can embed input. Logs/APM outlive HTTP responses and are shared more broadly. Log bounded metadata instead: service name, public error code, server-generated correlation ID, controlled method category, and violation count—never raw rejected values or credentials.

### 13.3. Return Violations Are Typically Internal Errors

If a service promises a non-blank reference yet returns an empty string, clients cannot fix it by changing their input. HTTP 500 with internal monitoring is safer and more appropriate than HTTP 400. When failures happen after side effects, review transaction/retry policies to avoid partial writes.

### 13.4. Distinguish Input Validation from Permission Checks

`@NotBlank`, `@Pattern`, and `@Min` verify syntax/bounds; they do not prove the caller has permission to allocate stock, edit inventory, or access a tenant. Authorization must be enforced separately at the security/service boundary. Constraint-valid values can still represent forbidden actions.

## 14. Comparing Service AOP vs Built-In MVC Method Validation

| Criterion | Service method validation via AOP | MVC handler method validation 6.1+ |
| --- | --- | --- |
| Activation point | `@Validated` service bean, proxy | Controller handler with direct parameter/return constraints |
| Mechanism | `MethodValidationPostProcessor` + advice | MVC handler validation infrastructure |
| Checked parameters | Jakarta executable constraints on service parameters | MVC handler parameters after argument resolution |
| Checked return | Jakarta executable return constraints via proxy | MVC handler return constraints |
| Default exception | `ConstraintViolationException` | `HandlerMethodValidationException` |
| Alternative | `MethodValidationException` if `adapt=true` | Handle `HandlerMethodValidationException` |
| Self-invocation | Bypasses proxy advice | Not the same concept of calling target via service proxy |
| Object `@Valid` | Cascades when method validation runs | Can also use separate object validation `MethodArgumentNotValidException` |
| Use case | Service called from multiple entry points | HTTP request/response boundary |
| Handler | Map errors per trust boundary, not all to 400 | 400 for input; 500 for return violation per MVC semantics |

**Do not collapse both exceptions into a single assumption.** A service with class-level `@Validated` is checked by AOP; controllers do not necessarily need class-level `@Validated`. In MVC 6.1+, putting `@Min` directly on `@RequestParam` produces `HandlerMethodValidationException`, not `ConstraintViolationException`, unless you intentionally route the controller through AOP.

## 15. Troubleshooting When Tests Fail

### 15.1. Why Didn't Calling `allocate("",0)` Throw an Error?

Check in order:
1. Was it called on a Spring-injected bean or `new`?
2. Does `StockService` have `@Service` and sit within component scan?
3. Is `@Validated` on the **class**?
4. Does `spring-boot-starter-validation` include a Bean Validation provider?
5. Was `MethodValidationPostProcessor` created?
6. Is `AopUtils.isAopProxy(stock)` true?
7. Did the call go through the injected proxy or `this`?
8. Is the method public and capable of being proxied/advised?
9. Is any config adapting violations and changing the exception type?
10. Did a test replacement/mock bean strip away advice?

### 15.2. Why Am I Getting `MethodValidationException` Instead of `ConstraintViolationException`?

The system may have configured `MethodValidationPostProcessor#setAdaptConstraintViolations(true)`. That adapts output to Spring's `MethodValidationResult` and corresponding exception, changing APIs/handling. The demo leaves this option off. Inspect bean configuration and keep tests aligned with policy.

### 15.3. Why Isn't a Return-Value Error HTTP 400?

Server-produced return values are part of the service's own contract. When they fail a constraint, clients usually cannot fix their input to resolve it. Separate status 500, limit public details, and log/alert safely for operations teams.

### 15.4. Why Does `getPropertyPath().toString()` Differ from Tutorials?

Parameter-name discovery may yield `arg0`/`arg1` or `-parameters` names, and providers can format paths differently. Use `ElementKind.PARAMETER`/`RETURN_VALUE` and constraint annotation types to test property semantics; avoid hardcoding full path strings when not part of an API contract.

### 15.5. Why Doesn't Direct `new StockService()` Throw an Exception?

Because it bypasses the Spring-managed proxy, not because Jakarta constraints “stopped working”. `ExecutableValidatorTest` proves the provider still finds violations on a plain POJO when you **invoke the validator explicitly**.

### 15.6. Why Does Self-Invocation Slip Past Even Though the Service Is Proxied?

Spring AOP proxies intercept **external method calls entering the proxy**, not internal `this` calls inside the target. Refactor logic into another bean or check invariants directly in the domain method—never disable the warning test.

### 15.7. Why Doesn't `@Valid` on a DTO Check for a Null Object?

`@Valid` is a cascade marker; null references do not cascade to properties. Add `@NotNull` on the parameter to forbid null. For primitive `int`, object null does not apply; use `@Min` for numeric bounds.

### 15.8. Why Might Return Validation Tests Not Roll Back the Database?

Validation advice order relative to the transaction advisor can differ. Return violations occur after the method body, but commit/rollback depends on interceptor nesting and the transaction manager. Write a real integration test with a database instead of asserting only `ConstraintViolationException`.

### 15.9. Why Do CGLIB and JDK Proxies Behave Differently After Refactoring?

Adding an interface or changing `spring.aop.proxy-target-class` can switch proxy modes. JDK proxies expose methods only through interfaces, so caller injections and annotation placement must follow the proxy method contract. Do not force concrete-implementation injection when the application uses interface-based proxies.

## 16. Advanced Exercises

1. Remove `@Validated` from `StockService`, run `StockServiceProxyTest`, and explain why the proxy/violation tests fail.
2. Change `@Min(1)` to `@Min(5)`, verify `allocate("PEN",2)` now fails before incrementing.
3. Add `@NotNull` to the return of a method returning null and verify `ElementKind.RETURN_VALUE`.
4. Add `@Valid` to a new `AllocationCommand` containing a nested object, inspect property paths without needing a controller.
5. Change `callThroughThis()` to call through a collaborator bean and verify invalid input is blocked; avoid `AopContext` unless necessary.
6. Write direct `ExecutableValidator.validateParameters` calls for the same inputs the proxy rejects; compare violation counts and method-body state.
7. Switch exception policy to `setAdaptConstraintViolations(true)` and update tests for `MethodValidationException` and `ParameterValidationResult`.
8. Write a negative test with a `final` method on a class-based proxy, observe whether advice runs, and remove the anti-pattern.
9. Define an interface with executable constraints implemented by a class, comparing JDK vs CGLIB proxies under interface injection.
10. Add real transactions with persistence, deliberately trigger a return violation, and inspect commit/rollback according to advisor ordering.
11. Send `units=ABC` over HTTP and compare against `units=0`: MVC conversion errors differ from AOP method validation errors.
12. Add a custom `ConstraintViolation` message containing a canary string and verify responses and logs never leak the canary.
13. Add a `StrictChecks` group, apply `@Validated(StrictChecks.class)`, and verify the intended group runs.
14. Create a scheduled job calling the bean proxy vs calling an internal method on the same bean; never assume schedulers always bypass or enter proxies—observe the actual wiring.
15. Move the REST layer to WebFlux while keeping service AOP; write `WebTestClient` tests and avoid treating a reactive return publisher as an already-emitted value.

## 17. Checklist for Enabling Method Validation in Real Services

- [ ] Service is a Spring-managed bean, never instantiated with `new` in production wiring.
- [ ] `@Validated` is on the type per Spring AOP method validation policy.
- [ ] Jakarta Bean Validation provider is present and `MethodValidationPostProcessor` is auto-configured or declared once intentionally.
- [ ] Test `AopUtils.isAopProxy` and an invalid invocation through the proxy.
- [ ] Parameter constraints protect inputs; return constraints protect output contracts.
- [ ] `@NotNull` is paired with `@Valid` when null objects must be rejected.
- [ ] Test default `ConstraintViolationException` or `MethodValidationException` if `adapt=true`.
- [ ] Do not assert exact raw provider messages/paths when not part of a contract.
- [ ] Inspect `ElementKind.PARAMETER`/`RETURN_VALUE` instead of guessing from strings.
- [ ] Include negative tests for `new`/self-invocation so coverage is never misread.
- [ ] Avoid relying on `private`/`final` methods as the sole place expecting proxy advice.
- [ ] Be careful with interface constraints and inheritance rules; switching JDK/CGLIB requires regression tests.
- [ ] Never turn every service `ConstraintViolationException` into HTTP 400.
- [ ] Use HTTP 500 for return/internal contract failures with responses revealing neither values nor method details.
- [ ] Never serialize raw `ConstraintViolation`/`getInvalidValue()`/`ex.getMessage()` or log credentials.
- [ ] Validation differs from authorization; operation permissions must have separate checks.
- [ ] With transactions, async, caching, and retries, test advice ordering and side effects.
- [ ] Re-run JUnit and HTTP integration regression suites when upgrading Spring/Boot/validators.

## 18. Visual Summary

~~~text
CALLER ---> AOP PROXY ---> validateParameters()
                               |
                               +-- FAIL -> ConstraintViolationException
                               |
                               v
                          TARGET METHOD
                               |
                               v
                         validateReturnValue()
                               |
                               +-- FAIL -> ConstraintViolationException
                               |
                               v
                        VALID RETURN TO CALLER

this.method(...) / new MyService()
             -> bypasses Spring proxy advice
             -> no automatic AOP method validation

Validator.forExecutables()
             -> explicit validation on any suitable target
             -> separate from proxy interception
~~~

**Final takeaway:** `@Validated` is not magic that checks every Java call. It instructs Spring to wrap **calls passing through a proxy** with advice. Before the target method, validation checks the parameter contract; after the target method, it checks the return contract. To rely on this mechanism safely, test the proxy itself, test self-invocation, and test 400/500 responses at the proper API boundaries rather than merely spotting annotations in source code.

## 19. References

- Spring Framework 6.2 — Java Bean Validation / Spring-driven Method Validation: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Framework 6.2 — Proxying Mechanisms and Self Invocation: https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html
- Spring Framework 6.2 — AOP Proxies: https://docs.spring.io/spring-framework/reference/6.2/core/aop/introduction-proxies.html
- Spring Framework 6.2 — MVC Validation and class-level @Validated distinction: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework 6.2 — MethodValidationPostProcessor Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/beanvalidation/MethodValidationPostProcessor.html
- Spring Framework 6.2 — MethodValidationInterceptor Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/beanvalidation/MethodValidationInterceptor.html
- Spring Framework 6.2 — MethodValidationException Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/method/MethodValidationException.html
- Spring Framework 6.2 — ParameterValidationResult Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/method/ParameterValidationResult.html
- Spring Boot 3.5 — Validation and method validation auto-configuration: https://docs.spring.io/spring-boot/3.5/reference/io/validation.html
- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Jakarta Bean Validation 3.1 — Executable Validation, Path, inheritance and groups: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html
- Jakarta Validation 3.1 — ExecutableValidator API: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/executable/executablevalidator
- OWASP Developer Guide — Handle all Errors and Exceptions: https://devguide.owasp.org/en/04-design/02-web-app-checklist/10-handle-errors-exceptions/
