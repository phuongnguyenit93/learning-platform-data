# Testing Method Validation Through a Real Spring Bean Proxy

## 1. Why calling a service directly in a unit test is not enough

Suppose a Spring service applies constraints directly on its methods:

```java
@Service
@Validated
public class BookingRulesService {

    public String verifyReference(@NotBlank String reference) {
        return reference.trim();
    }

    @NotNull
    public String findReceipt(boolean exists) {
        return exists ? "RCPT-390" : null;
    }
}
```

This snippet illustrates the idea; the complete project follows later. Two rules must be enforced:

- `verifyReference(" ")`: whitespace-only parameter violates `@NotBlank`.
- `findReceipt(false)`: method returns `null`, violating `@NotNull` on the return value.

Yet this test **does not test Spring method validation**:

```java
BookingRulesService service = new BookingRulesService();
String text = service.verifyReference(" ");
```

The plain Java call returns `""` and **does not automatically throw** `ConstraintViolationException`. `@NotBlank` is metadata, while Jakarta Bean Validation must be actively executed by a validator or interceptor. An instance created with `new` bypasses the Spring container and therefore lacks the `MethodValidationPostProcessor` advice.

The same risk arises when:

- Instantiating the service with `new` in JUnit.
- Using Mockito `mock(...)`, where by default neither the method body nor Spring advice runs.
- Using a slice test where the service bean is replaced with a mock.
- Calling a constrained method from another method **inside the same class** (self-invocation).
- Misplacing `@Validated`, missing a Bean Validation provider, or having `final`/`private` methods that prevent a proxy from intercepting calls.

**Goal of this lesson:** write integration tests that obtain a **real bean proxy from the Spring ApplicationContext**, verify a proxy actually exists, invoke methods through that proxy, and check input parameter constraints, cascaded `@Valid`, return-value constraints, validation groups, exception types, and self-invocation. The lesson also includes an illustrative HTTP path to observe requests flowing through a controller into the service proxy, along with how to avoid confusing this with Spring MVC's built-in method validation.

**Scope:** Java 17+, Spring Boot 3.3.6, Spring Framework 6.1.x, Spring AOP proxy-based method validation, and Jakarta Validation. Starting in Spring MVC 6.1, controllers have built-in method validation distinct from AOP service validation. The example is a standalone runnable project given JDK 17, Gradle, and dependencies; test results are stated as **expected**, not claimed as executed while writing the lesson.

## 2. How does Spring-driven method validation work?

### 2.1. Participating components

| Component | Role |
| --- | --- |
| `jakarta.validation.constraints.*` | Declares constraints such as `@NotBlank`, `@Min`, `@NotNull`… |
| `@Valid` | Requests **cascaded object** validation on parameters/return values when validation runs |
| `org.springframework.validation.annotation.Validated` | Marks a **target class** for Spring AOP method validation, optionally specifying groups |
| `MethodValidationPostProcessor` | Bean post-processor that finds eligible beans and applies a validation advisor/proxy |
| `MethodValidationInterceptor` | Advice invoking Jakarta `ExecutableValidator` before/after method execution |
| `jakarta.validation.Validator` / `ExecutableValidator` | Bean Validation provider, typically Hibernate Validator |
| `ConstraintViolationException` | Default exception thrown when method validation finds violations |
| `MethodValidationException` | Alternative exception when Spring's adapter is configured to adapt violations into `MethodValidationResult` |
| Spring AOP proxy | Execution boundary requiring calls to **pass through the proxy** |

Spring Boot can auto-configure method validation when a Bean Validation provider is present (typically via `spring-boot-starter-validation`). For Spring AOP-driven method validation, **the target service class needs `@Validated` at the type level**. In plain Spring setups without Boot auto-configuration, declare `MethodValidationPostProcessor` as a Spring bean. Do not add one manually when Boot already provides it, as duplicate configuration can be hard to debug.

### 2.2. Flow through the proxy

```text
JUnit @SpringBootTest / controller / another bean
              |
              | call public service method
              v
   Spring-managed proxy of service
              |
              v
   MethodValidationInterceptor
              |
              | validateParameters(target, method, args, groups)
              | violations? -> ConstraintViolationException
              v
   Method body of target service
              |
              | execute business logic
              v
   MethodValidationInterceptor
              |
              | validateReturnValue(target, method, result, groups)
              | violations? -> ConstraintViolationException
              v
         Caller receives result
```

These steps represent the conceptual flow. Interaction order with `@Transactional`, caching, or custom advisors depends on configuration/ordering; do not infer from this diagram that transactions commit before return validation or that every exception is thrown before persistence flushes.

### 2.3. Distinguishing @Valid and @Validated

- `@Valid` is a Jakarta Validation annotation: it marks where to **cascade** into a referenced object. **It does not create a Spring AOP proxy on its own**.
- Spring's class-level `@Validated` signals `MethodValidationPostProcessor` to detect and proxy the bean. It can specify groups.
- `@NotBlank`, `@Min`, and `@NotNull` are the actual **constraint annotations**; they determine validity of parameters, return values, and objects.
- Method-level `@Validated(SomeGroup.class)` can **override the group** used for that specific method, but does not replace the need for class-level `@Validated` to create the proxy.

If a class has `@Validated` yet has no method constraints and no cascades to check, a proxy may exist without throwing violations on those methods. Therefore **asserting only that a proxy exists is not enough**: invoke a method with invalid input and prove the interceptor throws the exception.

## 3. Why must @SpringBootTest be used in this testing scenario?

There are two different kinds of tests:

### 3.1. Unit test of a business method

```java
BookingRulesService plain = new BookingRulesService();

assertEquals("", plain.verifyReference(" "));
```

This test may fit checking `String#trim()`. However, it **does not verify** constraints at the AOP boundary.

### 3.2. Integration test of a Spring proxy

```java
@SpringBootTest
class BookingRulesServiceTest {

    @Autowired
    BookingRulesService service;

    @Test
    void mustHaveProxy() {
        assertTrue(AopUtils.isAopProxy(service));
    }
}
```

This is an abbreviated snippet requiring JUnit/Spring imports and a valid context configuration. `@SpringBootTest` builds a near-real ApplicationContext; `@Autowired` receives the bean returned by the container—usually a **proxy**, not the raw target. Tests can call methods normally and catch `ConstraintViolationException`.

Why are both assertions needed?

1. `AopUtils.isAopProxy(service)`: proves the injected object is a Spring AOP proxy.
2. `assertThrows(ConstraintViolationException.class, () -> service.verifyReference(" "))`: proves the validation advice actually runs for the intended method.

With only assertion 1, the bean might be proxied for transactions/caching/security **without** a method-validation advisor; with only assertion 2, an exception might accidentally come from **code inside the method body** rather than Jakarta method validation. In our example, the method body **never throws itself**, so combining both checks gives clear proof.

## 4. Two validation mechanisms often confused in MVC applications

### 4.1. AOP service method validation

```java
@Service
@Validated
public class BookingRulesService {
    public int doubleSeats(@Min(1) int seats) {
        return seats * 2;
    }
}
```

Calling through the bean proxy with `seats=0` normally raises `jakarta.validation.ConstraintViolationException` under `MethodValidationPostProcessor`'s default configuration.

### 4.2. Spring MVC built-in method validation since Framework 6.1

```java
@GetMapping("/quantity")
public int quantity(@RequestParam @Min(1) int value) {
    return value;
}
```

This is a constraint **directly on a controller method parameter**. Spring MVC 6.1+ provides built-in method validation **directly in HandlerMethod** without needing a service proxy. On violation, it can throw `HandlerMethodValidationException`. When only `@Valid @RequestBody` or `@Valid @ModelAttribute` is used for a command object, the typical exception is `MethodArgumentNotValidException`; direct constraints can cause method validation to supersede argument validation.

**Note from Spring docs:** to use Spring MVC 6.1+ built-in method validation, omit `@Validated` at the **controller class level**. Class-level `@Validated` on a **service class** remains the way to activate Spring AOP method validation in this lesson.

In the runnable project, the controller has **no** direct parameter constraints and **no** class-level `@Validated`. It simply calls a `@Validated` service bean. Thus the tests isolate and verify the exact AOP service path under test.

## 5. Conditions for a proxy to intercept a call

1. The object is created by the Spring container and passes through bean post-processing.
2. A Bean Validation provider and method-validation post-processor/advisor are present.
3. The target class has class-level `@Validated`.
4. The caller holds the **proxy** bean, not a self-created `new` target.
5. The method is eligible for proxying—typically `public` and not blocked by `final`/`private`.
6. The call **enters from outside through the proxy**, not via `this.method()` inside the target.
7. Constraints sit on locations supported by Jakarta Bean Validation and obey executable-constraint inheritance rules.
8. Validation groups match; a constraint in another group is legitimately skipped.

### 5.1. JDK dynamic proxies and CGLIB proxies

Spring AOP typically chooses:

- **JDK dynamic proxy** when proxying interfaces. Callers should inject the interface implemented by the proxy; methods absent from the interface may not be exposed on a JDK proxy.
- **CGLIB class-based proxy** when proxying classes. It generates a runtime subclass, so it cannot override `final` methods or subclass `final` classes.

The runnable example uses a **class implementing no interface**, non-final, with public methods, so Spring creates a class-based proxy and tests can inject the concrete class. Setting `spring.aop.proxy-target-class=true` makes the intent explicit. Avoid coupling test sources to JDK vs CGLIB internals when the goal is simply verifying method validation, unless proxy strategy itself is under test.

For interface-based services, declare constraints consistently on the interface contract; Jakarta Validation restricts overriding methods from **strengthening preconditions** relative to interface or superclass declarations, which can throw `ConstraintDeclarationException`. Never move annotations between interface and implementation without testing.

### 5.2. Final, private, and self-invocation

- `final class` prevents CGLIB subclassing.
- `final method` cannot be overridden by CGLIB to weave advice.
- `private method` is not a public proxy boundary.
- `this.someMethod()` from inside the target never re-enters the proxy; advice has no chance to run.
- A bean injecting itself to call its proxy can create circular dependencies and tight coupling; refactoring the validated call into **another bean** is usually cleaner.
- `AopContext.currentProxy()` requires enabling expose-proxy and couples code to Spring AOP; Spring documentation recommends avoiding it when possible.

When a service method truly needs internal validation, two clean options exist: extract the validated step into an injected Spring-managed collaborator called through its proxy, or invoke `Validator`/`ExecutableValidator` explicitly at that boundary. Never rely on self-invocation as a guaranteed validation boundary.

## 6. Runnable Spring Boot 3.3.6, Java 17 project

This project provides:

- `BookingRulesService` with class-level `@Validated`.
- Parameter constraints `@NotBlank` and `@Min`.
- Cascaded request record via `@Valid @NotNull`.
- Return-value constraint `@NotNull`.
- Method-level `@Validated(ReviewChecks.class)` to demonstrate groups.
- `callOwnValidator` demonstrating intentional self-invocation to test the proxy limitation.
- `BookingController` omitting `@Valid` on its body parameter, proving the service proxy handles cascaded validation.
- `@RestControllerAdvice` classifying input vs return violations within the **demo scope**.
- `@SpringBootTest` and `@AutoConfigureMockMvc` to test both the real bean proxy and the HTTP path.

### 6.1. Source layout

```text
method-validation-proxy-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/com/example/proxyvalidation/
        MethodValidationProxyApplication.java
        BookingRequest.java
        BookingReceipt.java
        ApiError.java
        ReviewChecks.java
        BookingRulesService.java
        BookingController.java
        ValidationAdvice.java
      resources/
        application.properties
    test/
      java/com/example/proxyvalidation/
        BookingRulesServiceProxyTest.java
```

This is a standalone project. No database or external service is needed. The entire test suite runs with Spring Test + the embedded servlet environment used by Spring Boot test auto-configuration.

### 6.2. settings.gradle

```groovy
rootProject.name = 'method-validation-proxy-demo'
```

### 6.3. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Explanation:

- `spring-boot-starter-validation` supplies a Bean Validation provider such as Hibernate Validator.
- `spring-boot-starter-aop` supplies the proxy/aspect infrastructure and makes the demo's intent clear.
- `spring-boot-starter-web` provides Spring MVC and Jackson for HTTP request tests.
- `spring-boot-starter-test` provides JUnit Jupiter, Mockito, Spring Test, and MockMvc.
- `-parameters` preserves method parameter names at runtime; useful for inspecting violation paths, though tests avoid hardcoding path strings tied to parameter names.

### 6.4. application.properties

`src/main/resources/application.properties`:

```properties
spring.application.name=method-validation-proxy-demo
spring.aop.proxy-target-class=true
```

`proxy-target-class=true` selects class-based proxies where applicable. This is **not** a substitute switch for `@Validated`: a bean without a validation pointcut/advisor will not be validated merely because this property is enabled.

### 6.5. Main class

`src/main/java/com/example/proxyvalidation/MethodValidationProxyApplication.java`:

```java
package com.example.proxyvalidation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MethodValidationProxyApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                MethodValidationProxyApplication.class, args
        );
    }
}
```

### 6.6. Request record and validation constraints

`src/main/java/com/example/proxyvalidation/BookingRequest.java`:

```java
package com.example.proxyvalidation;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record BookingRequest(
        @NotBlank String reference,
        @NotNull @Min(1) Integer seats
) {}
```

`@NotBlank` rejects null/blank references. `@NotNull` rejects missing seats. `@Min(1)` requires positive seats when non-null; `@Min` alone does not reject null. Avoid `int` in a request record when business logic must distinguish "seats omitted" from "0 sent".

### 6.7. Response DTOs

`src/main/java/com/example/proxyvalidation/BookingReceipt.java`:

```java
package com.example.proxyvalidation;

public record BookingReceipt(String receipt) {}
```

`src/main/java/com/example/proxyvalidation/ApiError.java`:

```java
package com.example.proxyvalidation;

public record ApiError(
        String code,
        String message
) {}
```

Never serialize raw `ConstraintViolation` instances into responses: `getInvalidValue()`, root beans, and provider metadata can leak sensitive data or complicate JSON serialization. In the demo, return only a machine-readable `code` and a generic message without rejected values.

### 6.8. Marker interface for a validation group

`src/main/java/com/example/proxyvalidation/ReviewChecks.java`:

```java
package com.example.proxyvalidation;

public interface ReviewChecks {}
```

A marker interface with no methods. It acts as the `ReviewChecks.class` group token in Jakarta Validation.

### 6.9. Service with method constraints and class-level @Validated

`src/main/java/com/example/proxyvalidation/BookingRulesService.java`:

```java
package com.example.proxyvalidation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class BookingRulesService {

    public String verifyReference(
            @NotBlank String reference) {

        return reference.trim();
    }

    public int doubleSeats(@Min(1) int seats) {
        return seats * 2;
    }

    public String create(
            @Valid @NotNull BookingRequest request) {

        return "BOOKED:" + request.reference();
    }

    @NotNull
    public String findReceipt(boolean exists) {
        return exists ? "RCPT-390" : null;
    }

    @Validated(ReviewChecks.class)
    public String review(
            @NotBlank(groups = ReviewChecks.class) String summary,
            @NotBlank String comment) {

        return summary.trim() + ":" + comment;
    }

    public String callOwnValidator(String reference) {
        // Intentionally call this.verifyReference(reference) internally.
        // This is NOT a call through the Spring proxy!
        return verifyReference(reference);
    }
}
```

How to read the constraints:

- `verifyReference(" ")`: `@NotBlank` on parameter; proxy throws before `trim()` executes.
- `doubleSeats(0)`: `@Min(1)` on parameter; proxy blocks before the method body.
- `create(new BookingRequest(" ",0))`: `@Valid` triggers cascading into the record; catches `@NotBlank(reference)` and `@Min(seats)`.
- `create(null)`: `@NotNull` on parameter catches null; `@Valid` **does not treat null as an error itself**.
- `findReceipt(false)`: method body returns null; interceptor validates the **return value** and throws.
- `review(" ", "text")`: method-level `@Validated(ReviewChecks.class)` selects the ReviewChecks group and enforces its constraint.
- `review("OK", " ")`: `comment` has `@NotBlank` in the `Default` group, while `review` is configured to run only `ReviewChecks`; thus in this setup an empty comment **is not** checked by the Default-group constraint. This group distinction is intentional for learning.
- `callOwnValidator(" ")`: this method has no parameter constraint; when it calls `verifyReference` inside the **same target object**, the call bypasses the proxy. It returns an empty string, showing self-invocation skips advice.

**Do not treat the self-invocation test as a pattern to use in business logic.** It demonstrates a limitation of proxy-based AOP so you understand why internal calls can go unvalidated.

### 6.10. Controller acting purely as caller of the service proxy

`src/main/java/com/example/proxyvalidation/BookingController.java`:

```java
package com.example.proxyvalidation;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/bookings")
public class BookingController {

    private final BookingRulesService rules;

    public BookingController(BookingRulesService rules) {
        this.rules = rules;
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<BookingReceipt> create(
            @RequestBody BookingRequest request) {

        String receipt = rules.create(request);

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new BookingReceipt(receipt));
    }

    @GetMapping("/receipt")
    public BookingReceipt findReceipt(
            @RequestParam(defaultValue = "true")
            boolean exists) {

        return new BookingReceipt(rules.findReceipt(exists));
    }
}
```

The controller **intentionally** omits `@Valid` on `@RequestBody` so that record constraints fire when the controller invokes **`rules.create(request)` through the service proxy**. Placing `@Valid` on the controller parameter would let Spring MVC catch the error before the service runs, preventing HTTP tests from proving service method validation.

In production apps, controller `@Valid` and service method validation can coexist when each boundary needs its own contract. However, tests must clearly separate **which boundary** is being verified.

### 6.11. @RestControllerAdvice separating input violations from return violations

`src/main/java/com/example/proxyvalidation/ValidationAdvice.java`:

```java
package com.example.proxyvalidation;

import jakarta.validation.ConstraintViolationException;
import jakarta.validation.ElementKind;
import jakarta.validation.Path;
import java.util.stream.StreamSupport;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ValidationAdvice {

    @ExceptionHandler(ConstraintViolationException.class)
    public ResponseEntity<ApiError> constraints(
            ConstraintViolationException exception) {

        boolean returnViolation = exception.getConstraintViolations()
                .stream()
                .flatMap(v -> StreamSupport.stream(
                        v.getPropertyPath().spliterator(), false
                ))
                .map(Path.Node::getKind)
                .anyMatch(kind -> kind == ElementKind.RETURN_VALUE);

        if (returnViolation) {
            return ResponseEntity.internalServerError().body(
                    new ApiError(
                            "SERVER_CONTRACT",
                            "The server produced an invalid result"
                    )
            );
        }

        // Demo API mapping solely for service methods
        // explicitly invoked from this controller.
        return ResponseEntity.badRequest().body(
                new ApiError(
                        "INVALID_INPUT",
                        "The request violates an input constraint"
                )
        );
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiError> unreadable(
            HttpMessageNotReadableException exception) {

        return ResponseEntity.badRequest().body(
                new ApiError(
                        "INVALID_JSON",
                        "The request body cannot be read"
                )
        );
    }
}
```

**Why distinguish return violations?**

- A parameter violation caused by the client sending invalid input to this endpoint → HTTP **400**.
- A return-value violation occurs because the service returned a result breaking its contract → **server error**, typically HTTP **500**.
- Malformed JSON prevents Jackson from creating the request object → `HttpMessageNotReadableException`, not a `ConstraintViolationException` from the proxy.

**Limitation:** a `ConstraintViolationException` thrown by an internal service is not always caused by the HTTP client. In production, never catch every `ConstraintViolationException` and blindly return 400. Know the caller and responsibility layer, separate application/domain exceptions from HTTP input validation, and keep error codes safe. The advice above is scoped strictly to illustrating the two endpoints and distinguishing parameter vs return nodes.

If `MethodValidationPostProcessor#setAdaptConstraintViolations(true)` is enabled, the exception can be Spring's `MethodValidationException` instead of Jakarta's `ConstraintViolationException`. This test suite uses the **default configuration** and therefore asserts `ConstraintViolationException`; do not enable adapter mode in this project.

## 7. Real integration tests: @SpringBootTest and AopUtils

File `src/test/java/com/example/proxyvalidation/BookingRulesServiceProxyTest.java`:

```java
package com.example.proxyvalidation;

import jakarta.validation.ConstraintViolationException;
import jakarta.validation.ElementKind;
import jakarta.validation.Path;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.StreamSupport;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BookingRulesServiceProxyTest {

    @Autowired
    BookingRulesService service;

    @Autowired
    MockMvc mvc;

    @Test
    void actualSpringBeanIsAopProxy() {
        assertTrue(AopUtils.isAopProxy(service));
    }

    @Test
    void invalidBlankParameterIsRejectedByProxy() {
        ConstraintViolationException exception = assertThrows(
                ConstraintViolationException.class,
                () -> service.verifyReference(" ")
        );

        assertEquals(
                Set.of("NotBlank"),
                constraintNames(exception)
        );
    }

    @Test
    void invalidNumericParameterIsRejectedByProxy() {
        ConstraintViolationException exception = assertThrows(
                ConstraintViolationException.class,
                () -> service.doubleSeats(0)
        );

        assertEquals(
                Set.of("Min"),
                constraintNames(exception)
        );
    }

    @Test
    void validParametersExecuteMethodBody() {
        assertEquals(
                "BOOK-390",
                service.verifyReference(" BOOK-390 ")
        );
        assertEquals(4, service.doubleSeats(2));
    }

    @Test
    void nestedRecordConstraintsAreValidated() {
        BookingRequest request = new BookingRequest(" ", 0);

        ConstraintViolationException exception = assertThrows(
                ConstraintViolationException.class,
                () -> service.create(request)
        );

        assertEquals(
                Set.of("NotBlank", "Min"),
                constraintNames(exception)
        );

        assertEquals(2, exception.getConstraintViolations().size());
    }

    @Test
    void nullRequestRequiresExplicitNotNull() {
        ConstraintViolationException exception = assertThrows(
                ConstraintViolationException.class,
                () -> service.create(null)
        );

        assertEquals(
                Set.of("NotNull"),
                constraintNames(exception)
        );
    }

    @Test
    void validCascadedRecordIsAccepted() {
        assertEquals(
                "BOOKED:REF-390",
                service.create(
                        new BookingRequest("REF-390", 2)
                )
        );
    }

    @Test
    void invalidReturnValueIsRejectedAfterMethodBody() {
        ConstraintViolationException exception = assertThrows(
                ConstraintViolationException.class,
                () -> service.findReceipt(false)
        );

        assertEquals(
                Set.of("NotNull"),
                constraintNames(exception)
        );
        assertTrue(hasReturnNode(exception));
    }

    @Test
    void validReturnValueIsAccepted() {
        assertEquals("RCPT-390", service.findReceipt(true));
    }

    @Test
    void methodGroupOverridesDefaultGroup() {
        assertEquals(
                "OK: ",
                service.review("OK", " ")
        );
    }

    @Test
    void methodSpecificGroupConstraintIsChecked() {
        ConstraintViolationException exception = assertThrows(
                ConstraintViolationException.class,
                () -> service.review(" ", "comment")
        );

        assertEquals(
                Set.of("NotBlank"),
                constraintNames(exception)
        );
    }

    @Test
    void selfInvocationBypassesMethodValidationAdvice() {
        // callOwnValidator has no direct constraint.
        // The internal call to verifyReference bypasses the proxy.
        assertEquals(
                "",
                service.callOwnValidator(" ")
        );
    }

    @Test
    void newInstanceIsNotSpringProxy() {
        BookingRulesService plain = new BookingRulesService();

        assertFalse(AopUtils.isAopProxy(plain));
        assertEquals("", plain.verifyReference(" "));
        assertEquals(null, plain.findReceipt(false));
    }

    @Test
    void httpEndpointUsesRealServiceProxyForInput() throws Exception {
        mvc.perform(post("/api/bookings")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"reference":" ","seats":0}
                        """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_INPUT"));
    }

    @Test
    void httpEndpointUsesRealServiceProxyForReturn() throws Exception {
        mvc.perform(get("/api/bookings/receipt")
                .param("exists", "false"))
            .andExpect(status().isInternalServerError())
            .andExpect(jsonPath("$.code")
                    .value("SERVER_CONTRACT"));
    }

    @Test
    void validHttpRequestSucceeds() throws Exception {
        mvc.perform(post("/api/bookings")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"reference":"ABC-390","seats":2}
                        """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.receipt")
                    .value("BOOKED:ABC-390"));
    }

    @Test
    void malformedJsonDoesNotReachMethodValidation()
            throws Exception {

        mvc.perform(post("/api/bookings")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"reference\":\"X\",\"seats\":"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_JSON"));
    }

    private static Set<String> constraintNames(
            ConstraintViolationException exception) {

        return exception.getConstraintViolations()
                .stream()
                .map(v -> v.getConstraintDescriptor()
                        .getAnnotation()
                        .annotationType()
                        .getSimpleName())
                .collect(Collectors.toSet());
    }

    private static boolean hasReturnNode(
            ConstraintViolationException exception) {

        return exception.getConstraintViolations()
                .stream()
                .flatMap(v -> StreamSupport.stream(
                        v.getPropertyPath().spliterator(), false
                ))
                .map(Path.Node::getKind)
                .anyMatch(kind -> kind == ElementKind.RETURN_VALUE);
    }
}
```

There are **17 test methods**, with the key tests covering:

- `actualSpringBeanIsAopProxy`: the real Spring context returns a proxy.
- `invalidBlankParameterIsRejectedByProxy`: parameter constraint fires when invoked via the bean.
- `nestedRecordConstraintsAreValidated`: `@Valid` cascades into the record's component constraints.
- `invalidReturnValueIsRejectedAfterMethodBody`: checks the violation path contains a `RETURN_VALUE` node, not just the exception type.
- `selfInvocationBypassesMethodValidationAdvice`: demonstrates the proxy-based AOP limitation.
- `newInstanceIsNotSpringProxy`: control comparison between a plain object and the bean proxy.
- `httpEndpoint...` tests: confirm requests flow through the real controller into the proxied service.
- `methodGroupOverridesDefaultGroup` and `methodSpecificGroupConstraintIsChecked`: confirm method-level group selection works.

### 7.1. Run commands

From the project directory with Gradle wrapper:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

If the project lacks a wrapper yet, use an installed Gradle binary to generate one or run:

```bash
gradle test
```

**Expected:** 17 tests PASS when the project is configured properly for Spring Boot 3.3.6, Java 17, and the stated dependencies. This is the expected behavior of the reference source code, **not** a claim that tests were executed while authoring this lesson.

### 7.2. Why assert annotation names instead of default messages?

A `ConstraintViolation` has `getMessage()`, `getMessageTemplate()`, `getPropertyPath()`, and `getConstraintDescriptor()`. Default messages like "must not be blank" vary by `Locale` and provider; method parameter paths also depend on parameter names/metadata.

The test suite uses annotation types `NotBlank`, `Min`, and `NotNull`—far more stable for the demo—and asserts violation counts. It **does not depend on iteration order** of `Set<ConstraintViolation>`, because Sets do not guarantee iteration order.

For return-value validation, checking `Path.Node#getKind() == ElementKind.RETURN_VALUE` is much safer than comparing a path string that providers may format differently.

### 7.3. Why include passing happy-path tests?

A test that only asserts exceptions on bad input can miss a misconfiguration that rejects **every input**. Pairing valid cases proves the advice does not alter business results when no violation exists:

```java
assertEquals(
        "BOOK-390",
        service.verifyReference(" BOOK-390 ")
);
assertEquals(
        "RCPT-390",
        service.findReceipt(true)
);
```

Test both **valid** and **invalid** paths to prevent false positives from exceptions thrown by unrelated code or another proxy.

### 7.4. When to use MockMvc vs @SpringBootTest alone?

If you only care about service method validation, `@SpringBootTest` + `@Autowired` service suffices to verify the real proxy. `MockMvc` is needed when you must prove the controller uses the injected service bean, HTTP error mapping is sound, and the JSON contract does not leak raw violations.

Conversely, `@WebMvcTest` with a mocked service **does not prove** service method validation works. Slice tests typically create only the controller layer and explicitly declared dependencies; replacing the service with a Mockito mock means the real bean's method-validation advisor never runs.

## 8. Expected HTTP results

### 8.1. Invalid input blocked at the proxy

```bash
curl -i -X POST http://localhost:8080/api/bookings \
  -H 'Content-Type: application/json' \
  -d '{"reference":" ","seats":0}'
```

Expected HTTP **400 Bad Request**:

```json
{
  "code": "INVALID_INPUT",
  "message": "The request violates an input constraint"
}
```

This error comes from `rules.create(request)` via the method-validation proxy, since the controller has no `@Valid` on the body.

### 8.2. Valid request

```bash
curl -i -X POST http://localhost:8080/api/bookings \
  -H 'Content-Type: application/json' \
  -d '{"reference":"ABC-390","seats":2}'
```

Expected HTTP **201 Created**:

```json
{"receipt":"BOOKED:ABC-390"}
```

### 8.3. Return value violating contract

```bash
curl -i 'http://localhost:8080/api/bookings/receipt?exists=false'
```

`findReceipt(false)` runs its method body and returns `null`, but the interceptor checks `@NotNull` on the return value and throws. Expected HTTP **500 Internal Server Error** per the demo advice:

```json
{
  "code": "SERVER_CONTRACT",
  "message": "The server produced an invalid result"
}
```

Never return 400 for this case: the client sent `exists=false` per the endpoint's contract, while the method promised a non-null return and broke that promise. That is a server-side failure.

### 8.4. Malformed JSON never reaches the service

```bash
curl -i -X POST http://localhost:8080/api/bookings \
  -H 'Content-Type: application/json' \
  -d '{"reference":"ABC-390","seats":'
```

Expected HTTP 400 with code `INVALID_JSON`. Jackson cannot construct `BookingRequest`; the method-validation proxy never receives an input object to validate.

## 9. Testing with Mockito mocks: why it does not replace a real proxy

Mockito is great for unit-testing isolated logic. However:

```java
BookingRulesService service =
        org.mockito.Mockito.mock(BookingRulesService.class);

service.verifyReference(" ");
```

calls a **mock**, not a Spring bean wrapped in `MethodValidationInterceptor`. By default Mockito skips the real implementation and never triggers Spring method validation. Unstubbed methods return mock defaults (such as null). Therefore:

- A test verifying `verify(mock).verifyReference(...)` only proves the interaction, not that constraints are enforced.
- A `@WebMvcTest` with a mocked service still adds value for checking HTTP controller mapping, but is no proof of AOP method validation.
- Mockito `spy` requires care too: a standalone spy is not a Spring proxy; `@SpyBean`/bean overriding setups can alter proxy wrapping and must be verified explicitly.
- To unit-test rules on a DTO, invoke `jakarta.validation.Validator#validate` or `ExecutableValidator#validateParameters` in a dedicated test. That is a **provider test**, not a Spring proxy path test.
- When you need confidence that production beans are post-processed, write an integration test injecting the real bean and asserting `AopUtils.isAopProxy` + the expected exception.

### 9.1. Distinguishing manual ExecutableValidator from proxy invocation

A plain Jakarta Validation test can use:

```java
Method method = BookingRulesService.class.getMethod(
        "doubleSeats", int.class
);

BookingRulesService plain = new BookingRulesService();

Set<ConstraintViolation<BookingRulesService>> violations =
        validator.forExecutables().validateParameters(
                plain, method, new Object[]{0}
        );
```

This **snippet** requires imports for `java.lang.reflect.Method`, `java.util.Set`, `jakarta.validation.ConstraintViolation`, and `Validator`, assuming `validator` exists. It detects violations directly via the provider **without a proxy**. Thus it does not prove the Spring container configured `MethodValidationPostProcessor`.

By contrast, calling `service.doubleSeats(0)` on an injected proxy and catching `ConstraintViolationException` proves the AOP path is active.

## 10. Negative example: self-invocation bypasses validation

Recall the service:

```java
public String callOwnValidator(String reference) {
    return verifyReference(reference);
}
```

If an external caller runs:

```java
service.callOwnValidator(" ");
```

then:

```text
Caller -> Spring proxy -> target.callOwnValidator(" ")
                               |
                               v
                     target.verifyReference(" ")
                               |
                               v
                            returns ""
             (does not go back through Spring proxy)
```

`""` is returned even though `verifyReference` has `@NotBlank` on its parameter. That is standard proxy-based Spring AOP behavior, not Bean Validation "randomly ignoring annotations".

**Recommended fix:** move the validated method into a separate collaborator bean:

```java
@Service
@Validated
public class ReferenceRules {

    public String verify(@NotBlank String reference) {
        return reference.trim();
    }
}

@Service
public class BookingWorkflow {

    private final ReferenceRules rules;

    public BookingWorkflow(ReferenceRules rules) {
        this.rules = rules;
    }

    public String process(String reference) {
        return rules.verify(reference);
    }
}
```

This snippet illustrates two classes (in real source code, place them in separate files if both are public). When `BookingWorkflow` calls `rules.verify`, it calls a Spring-managed bean reference, so if that bean is proxied, method validation runs. This lowers coupling compared to self-injection or `AopContext.currentProxy()`.

## 11. Validation groups: class and method levels

In Spring method validation, groups are specified via `@Validated`:

```java
@Service
@Validated
public class OrderApprovalService {

    @Validated(ReviewChecks.class)
    public void approve(
            @NotBlank(groups = ReviewChecks.class) String ticket,
            @NotBlank String note) {
        // business logic
    }
}
```

Here class-level `@Validated` activates the proxy with `Default`. Method-level `@Validated(ReviewChecks.class)` **replaces the group** for `approve`; it does not automatically "append" Default. Therefore:

- `approve(" ", "reason")`: `ticket` belongs to ReviewChecks and is invalid, throwing a violation.
- `approve("A-390", " ")`: `note` belongs to Default, so it is not evaluated when running only ReviewChecks.

Watch this nuance carefully: a constraint meant to be mandatory in Default will no longer run on a method that selects another group. If both must run, configure groups/sequences explicitly rather than assuming the two annotations merge automatically.

### 11.1. @Validated on a method alone is not enough to trigger the pointcut

Misguided setup:

```java
@Service
public class OrderApprovalService {

    @Validated(ReviewChecks.class)
    public void approve(
            @NotBlank(groups = ReviewChecks.class) String ticket) {
    }
}
```

Under default Spring-driven AOP method validation, placing `@Validated` **only on a method** does not replace class-level `@Validated` for selecting the bean for proxying. The Spring `Validated` Javadoc notes that the method-level annotation overrides the group while the class-level marker is required for the pointcut.

## 12. JDK proxies, interfaces, and Jakarta Validation overriding rules

A service interface can be proxied with a JDK dynamic proxy:

```java
public interface ReceiptService {

    String read(@NotBlank String code);
}
```

Implementation:

```java
@Service
@Validated
public class ReceiptServiceImpl implements ReceiptService {

    @Override
    public String read(String code) {
        return code;
    }
}
```

These snippets are illustrative, outside the runnable project. Here the constraint sits on the **interface contract**, and the implementation adds no extra parameter constraints.

Do not leave an interface unconstrained and put `@NotBlank` only on the overriding method expecting it to always be valid. Jakarta Validation enforces "subtypes must not strengthen preconditions" on method parameter constraints; providers can throw `ConstraintDeclarationException`. Return-value constraints follow different rules, so consult the specification when overriding or composing interfaces.

When a bean uses a JDK proxy:

- Injecting via the `ReceiptService` interface is natural.
- Injecting by concrete type `ReceiptServiceImpl` may fail.
- Methods present only on the implementation and not on the interface may be unreachable via the JDK proxy.
- Tests should assert `AopUtils.isAopProxy(...)` and behavior through the interface reference instead of assuming class-based proxies when multiple proxy strategies are allowed.

If class-based proxies are desired, configure them appropriately and keep advised classes/methods non-final. Never flip CGLIB on project-wide just to "fix" a failing test injection without understanding the root cause.

## 13. Exception types and method-validation configuration

### 13.1. Default ConstraintViolationException

Spring's `MethodValidationPostProcessor` creates `MethodValidationInterceptor` in standard setups. On parameter/return violations, it throws `jakarta.validation.ConstraintViolationException`. Tests can inspect:

```java
ConstraintViolationException error = assertThrows(
        ConstraintViolationException.class,
        () -> service.doubleSeats(0)
);

Set<?> violations = error.getConstraintViolations();
```

Do not rely on `Set<ConstraintViolation>` iteration order to pick "the first error". For multiple violations, use `stream().map(...).collect(toSet())` when checking membership; if emitting ordered HTTP errors, map to DTOs and sort with a deterministic comparator.

### 13.2. MethodValidationException when adaptConstraintViolations is enabled

Spring Framework supports:

```java
processor.setAdaptConstraintViolations(true);
```

This illustrative snippet assumes `processor` is a `MethodValidationPostProcessor`. When enabled, Spring adapts raw Jakarta violations into `MethodValidationResult`/`MessageSourceResolvable` and can throw Spring's `MethodValidationException`.

Do not hardcode `assertThrows(ConstraintViolationException.class, ...)` on an app with this mode enabled and wrongly conclude method validation is broken. Inspect the bean configuration and test against the chosen exception contract.

### 13.3. Choosing the right place to catch exceptions

When a service method is called by:

- An HTTP controller: input violations may map to 400 if confirmed to come from client input; return violations are typically 500.
- A scheduler: there is no HTTP 400/500; classify job failures appropriately.
- A Kafka/event consumer: may route to dead-letter, retry, or poison-message handling.
- Another service: the caller decides business recovery rather than assuming "user error".
- A transactional operation: depending on advisor ordering, validation may run before or after partial work; exceptions after the method body have rollback implications. Write integration tests across the transaction boundary if critical.

Never catch every `ConstraintViolationException` and unconditionally return "Invalid request" to the frontend.

## 14. Mistakes that create false-PASS tests

| Test/setup | Why it misleads | Proper verification |
| --- | --- | --- |
| `new Service().method(...)` | No Spring proxy | Inject bean from ApplicationContext |
| `Mockito.mock(Service.class)` | Mock skips method body/advice | Separate real-bean integration test |
| Asserting only `@Validated` on class | Annotation presence does not prove post-processor ran | `AopUtils.isAopProxy` + invalid call |
| Asserting only `isAopProxy == true` | Proxy might come from another AOP feature | Assert actual `ConstraintViolationException` |
| Testing `@Valid` only with valid objects | Does not prove cascading catches errors | Pass invalid record and inspect nested violations |
| Testing only input parameters | Misses return-value contract | Method returning null with `@NotNull` |
| Calling `this.validate(...)` | Does not re-enter proxy | Call via injected collaborator |
| `final` method/class with class proxy | Advice cannot override | Remove final at boundary or choose compatible strategy |
| Missing `spring-boot-starter-validation` | No Bean Validation provider | Verify dependencies and Bean Validation setup |
| Adding duplicate post-processor alongside Boot | Risks double-advice/confusing config | Prefer Boot auto-config when sufficient |
| `@Validated` only on method | Insufficient for class pointcut | Place marker at class level |
| Selecting wrong group | Unexecuted constraint may be intended semantics | Test against selected group |
| Asserting English message text | Text varies by locale/provider | Inspect annotation type/path/error code |
| Asserting first violation | `Set` does not guarantee iteration order | Compare sets or sort |
| Using `@WebMvcTest` with mocked service | Does not test real service bean/proxy | Use `@SpringBootTest` or import real bean into slice |
| Putting `@Valid` on controller during HTTP test | Controller may fail before service runs | Test service directly or separate boundaries |
| Skipping return-value validation | Server contract bugs go undetected | Test null/invalid return through proxy |
| Mapping every method violation to HTTP 400 | Can disguise server bugs | Separate parameter/return and caller context |
| Relying on fixed parameter-name strings | `-parameters`/provider metadata affects paths | Assert annotation types and Node kinds |
| Calling service method internally via `this` | Bypasses advice on internal calls | Extract another bean or validate explicitly |

## 15. Testing alongside @Transactional and @Async

### 15.1. @Transactional with method validation

`@Transactional` also typically uses a Spring AOP proxy. Placing both `@Transactional` and `@Validated` on a service can stack multiple advisors on the same bean. Advisor ordering between validation and transaction management matters if input/output validation affects rollback or if a return-value violation occurs after database writes.

For example, a method writing to the database and then returning null against `@NotNull` is not guaranteed to roll back in every configuration simply because method validation exists. Test the actual setup:

1. Read initial database state.
2. Call through the proxied service.
3. Catch the return-value violation.
4. In a separate transaction, inspect database state after the exception.
5. Document expected rollback vs commit per your architecture and advisor ordering.

Do not run this test with `new Service()` or an H2 setup whose transaction model differs from production and generalize the semantics.

### 15.2. @Async and other threads

When a method runs asynchronously, exceptions surface inside `Future`/`CompletableFuture` or an async exception handler rather than the caller's synchronous stack. Combining `@Async` proxies with method validation can change ordering and return-type validation behavior. The synchronous tests in this lesson **do not prove** an async setup throws the same exception at the call site.

To test async methods, await completion, inspect the cause, and verify input/return rules against your design contract. Never rely on `Thread.sleep` as your sole synchronization mechanism.

## 16. Checklist for writing real bean-proxy tests

1. Does the project include a Jakarta Bean Validation provider and Spring AOP/method-validation support?
2. Is the service bean managed by the Spring container rather than instantiated with `new` in tests?
3. Is class-level `@Validated` placed on the right target class?
4. Do validated methods expose a public proxy boundary (not `final`/`private`)?
5. Do tests inject the real bean reference from the ApplicationContext?
6. Do tests assert `AopUtils.isAopProxy(bean)` and then assert **constraints are actually enforced**?
7. Are invalid `@NotBlank`, invalid `@Min`, and valid happy-path cases tested?
8. Is cascaded `@Valid` tested on invalid objects, plus `@NotNull` on null objects?
9. Is return-value `@NotNull` tested and `ElementKind.RETURN_VALUE` verified?
10. If using groups, is class/method `@Validated` interaction tested?
11. Is self-invocation tested to confirm which internal calls bypass AOP?
12. Is it understood that Mockito mocks/`@WebMvcTest` do not replace full-context proxy tests?
13. Is service AOP `ConstraintViolationException` distinguished from Spring MVC built-in `HandlerMethodValidationException`?
14. Is Spring's `MethodValidationException` handled when adapter mode is enabled?
15. Do assertions avoid Set iteration order and raw default messages?
16. If required by the API, is there an HTTP integration test flowing through the controller into the **real service bean**?
17. Are input violations and return violations classified properly when mapping HTTP status codes?
18. Are responses kept safe, never serializing raw `ConstraintViolation` objects or invalid values?
19. If the service uses `@Transactional`/`@Async`, are advisor/transaction/async semantics tested separately?
20. Is the full integration suite re-run when upgrading Spring Boot/Spring Framework/providers?

**Conclusion:** Spring method validation is **behavior at the AOP proxy boundary**. Annotations in source code alone do not prove it runs. To test properly, obtain the real bean via `@SpringBootTest`, verify `AopUtils.isAopProxy`, invoke constrained methods through the injected bean, and assert exceptions/violations. Control tests using `new` and self-invocation show why non-proxied unit tests miss bugs. When integrating with MVC, keep a crisp boundary between service AOP validation, controller argument validation, and Spring 6.1+ built-in controller method validation.

## Official references

- [Spring Boot 3.3 — Validation](https://docs.spring.io/spring-boot/3.3/reference/io/validation.html): auto-configuring method validation when a Jakarta provider is present, using class-level `@Validated`.
- [Spring Framework 6.2 — Java Bean Validation / Spring-driven Method Validation](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html): `MethodValidationPostProcessor`, proxy-based validation, and exceptions.
- [Spring Framework 6.1 — MethodValidationPostProcessor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/validation/beanvalidation/MethodValidationPostProcessor.html): advisor/pointcut, validation groups, and `setAdaptConstraintViolations`.
- [Spring Framework 6.1 — @Validated Javadoc](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/validation/annotation/Validated.html): class pointcut and method-level group override.
- [Spring Framework — Spring AOP Proxying](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK vs CGLIB proxies, final/private, self-invocation.
- [Spring Framework 6.2 — Spring MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html): `MethodArgumentNotValidException` and `HandlerMethodValidationException`.
- [Jakarta Validation 3.0 Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html): `ExecutableValidator`, parameter/return constraints, cascading, and inheritance rules.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@SpringBootTest` and `@AutoConfigureMockMvc`.
