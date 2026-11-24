# Self-Invocation Bypassing Method Validation in Spring

## 1. Context: Same Constraint, Different Outcome Depending on Call Path

A notoriously elusive bug in Spring is when a method annotated with `@NotBlank`, `@NotNull`, or `@Min` works when called from another bean, yet **is not checked** when another method in the same class calls it via `this` or directly without `this`.

Example:

~~~java
@Service
@Validated
public class RegistrationService {

    public String register(String code) {
        return checkCode(code);
    }

    @NotBlank
    public String checkCode(@NotBlank String code) {
        return code;
    }
}
~~~

The snippet above is a **fragment**; full imports and project code appear in Section 9. When another Spring bean calls the **proxy** of `RegistrationService.checkCode("")`, Method Validation throws `ConstraintViolationException` for the empty input. Yet `register("")` calls `checkCode("")` internally on **the same target object**, never passing through the proxy a second time, so `checkCode`'s constraints are **not evaluated by AOP**.

This is the **self-invocation bypass** issue. Never conclude "`@NotBlank` only works in controllers" or "Spring ignores empty strings"; the root cause is that **the interceptor has no opportunity to intercept an internal call**.

**Article scope:** Spring-driven method validation on **service beans** via AOP proxies, how to reproduce it with Java 17+/Spring Boot 3.x, how it differs from Spring MVC 6.1+ built-in method validation, fixes, proof tests, and practical limitations.

### Observed Symptoms

| Call path | What happens with a properly configured proxy |
| --- | --- |
| `otherBean -> proxy.checkCode("")` | Parameter constraint on `checkCode` is checked; exception thrown. |
| `otherBean -> proxy.register("") -> this.checkCode("")` | Only `register`'s advice (if any) runs; `checkCode`'s advice is bypassed. |
| `new RegistrationService().checkCode("")` | Plain Java object, no Spring proxy, no AOP validation. |
| `proxy.methodWithInvalidReturn()` | Return-value constraint can be checked. |
| `proxy.outer() -> this.methodWithInvalidReturn()` | Inner return-value constraint is bypassed; outer is checked only per outer's own constraints. |

**Important distinction:** since `register` has no constraints, empty input slips through; however, if `register` **itself** had `@NotBlank` on its parameter, the proxy would check `register`. That **would not prove** `checkCode` was validated. When testing self-invocation, avoid accidentally placing the same constraint on the outer method, which hides the bypass.

## 2. Spring AOP Proxy Mechanism

Spring AOP typically uses **JDK dynamic proxies** or **class-based CGLIB proxies**. A proxy is a separate object wrapping the target bean for interception: external callers enter the proxy, the proxy runs required advice, and only then delegates to the target implementation.

~~~text
Outside Spring bean
        |
        v
    AOP PROXY
        |
        +-- MethodValidationInterceptor
        |     |
        |     +-- Validate method parameters
        |     +-- If invalid: validation exception
        |
        v
 TARGET BEAN.method(...)
        |
        +-- execute business logic
        |
        v
    AOP PROXY
        |
        +-- Validate return value
        |     +-- If invalid: validation exception
        |
        v
 Caller receives result
~~~

With:

~~~java
@NotBlank
public String normalize(@NotBlank String value) {
    return value.trim();
}
~~~

when the method is called via the proxy, the interceptor validates **parameters before the body**, then **return value after the body returns normally**. If input is invalid, the target method does not execute; if output is invalid, the target method has already executed and may even have caused side effects.

### The Self-Invocation Path

~~~text
Caller
   |
   v
Proxy of RegistrationService
   |
   v
Target.register(...)
   |
   +-- this.checkCode(code)
            |
            v
        Target.checkCode(...)
            |
            +-- DOES NOT go through proxy
            +-- MethodValidationInterceptor for checkCode
                does not run
~~~

Once the proxy hands control into `Target.register`, `this` points to the raw target object. Calling `this.checkCode(...)` or `checkCode(...)` continues directly inside the target. Spring docs explicitly note that self-invocation in proxy-based AOP bypasses advice on the internally called method.

**Deleting the keyword `this` does not fix the bug**:

~~~java
public String outer(String code) {
    return checkCode(code); // still implicit this
}
~~~

There is no Java mechanism that automatically "loops back into the AOP proxy" for this call. To run the interceptor, you need a **call path passing through the proxy**, or an explicit validation check.

## 3. Conditions for Service Method Validation to Work

Spring does not automatically intercept every method call merely because an annotation exists. For standard **Spring-driven service method validation**, you need:

1. **A Spring-managed bean**, e.g., `@Service` within component scan. `new Service()` creates no proxy.
2. **A Jakarta Bean Validation provider** such as Hibernate Validator, typically via `spring-boot-starter-validation` in Spring Boot.
3. **Method validation infrastructure** such as `MethodValidationPostProcessor` with Spring AOP. Boot auto-configures it when classpath/context conditions are met.
4. **`org.springframework.validation.annotation.Validated` on the target service type** so Spring-driven method validation selects the bean.
5. **Constraints in the right places** — `@NotBlank` on method parameters or return values; not merely an annotation on an uncascaded DTO.
6. **External calls routed through the proxy**, not self-calls on `this`.
7. **Proxyable methods**: proper class/method visibility, JDK interface coverage, and CGLIB non-final/non-private rules.
8. **Matching validation groups** and properly configured interceptor/exception adaptation.

In plain Spring Framework, official documentation shows:

~~~java
@Configuration
public class ValidationConfig {
    @Bean
    public static MethodValidationPostProcessor methodValidationPostProcessor() {
        return new MethodValidationPostProcessor();
    }
}
~~~

This is a **snippet** requiring Spring `@Configuration`, `@Bean`, and `MethodValidationPostProcessor` imports. When Spring Boot already auto-configures the processor, **do not register a second processor** without checking the context; duplicate auto-proxy mechanisms complicate tests and behavior.

### `@Validated` Differs from `@Valid`

| Annotation/API | Role |
| --- | --- |
| Spring `@Validated` on service class | Marks target for AOP-driven method validation; can specify validation groups. |
| Jakarta `@Valid` on DTO/parameter | Cascades validation onto the annotated object; **not a constraint itself**. |
| Jakarta `@NotBlank` on String parameter/return | Real constraint checking null/empty/whitespace. |
| Jakarta `@NotNull` on reference parameter/return | Real constraint requiring non-null. |
| Jakarta `@Min` on numeric parameter | Real constraint setting minimum value. |
| Jakarta `ExecutableValidator` | API for **explicitly** validating method parameters/returns without needing an AOP proxy. |

Example:

~~~java
@Service
@Validated
class OrderService {
    @NotNull
    public Receipt create(
            @NotNull @Valid OrderInput input) {
        // corresponding implementation
        return null; // illustrative anti-pattern only
    }
}
~~~

This is an **anti-pattern snippet**, not code to run: returning null intentionally violates the contract. `@NotNull` before the return type constrains **the return value**; `@NotNull @Valid` on the input checks non-null reference + cascade. Never return null in production in violation of the contract.

### Validation Groups Are Not Self-Invocation

When using `@Validated(RegistrationGroup.class)`, some constraints may belong only to a group other than `Default`. Testing with the wrong group produces no exception even when the call passes through the proxy. To isolate self-invocation, this demo uses `@NotBlank` in the **Default group** first, before examining groups in real projects.

## 4. Why `private`/`final`/Proxy Types Also Prevent Interception

### Class-Based Proxy (CGLIB)

CGLIB generates a subclass of the target. It **cannot override**:
- `final` methods,
- `private` methods,
- insufficiently visible methods (e.g., certain package-private members from another package).

A `final` class cannot be subclassed by a class-based proxy. Never rely on Spring AOP to enforce a critical constraint placed solely on a private or final helper.

Easy mistake:

~~~java
@Service
@Validated
class ExampleService {

    public String outer(String input) {
        return privateCheck(input);
    }

    @NotBlank
    private String privateCheck(@NotBlank String input) {
        return input;
    }
}
~~~

This **snippet** only illustrates the limitation. `privateCheck` is not an interceptable method under Spring proxy-based AOP. Even when `outer` is called via the proxy, `privateCheck` is an internal call.

### JDK Dynamic Proxy

JDK proxies expose methods declared on the proxied interfaces. If a method exists only on the implementation class and not on the interface, callers injecting the interface cannot invoke it. Do not flip `spring.aop.proxy-target-class=true` thinking it solves self-invocation: **both JDK proxies and CGLIB proxies bypass advice when methods on the target call each other**.

### Bean Initialization Phase

Constructors and calls from `@PostConstruct` do not go through a fully initialized external proxy the way normal callers do. Do not rely on self-calls during initialization to trigger AOP method validation. If startup configuration checks are needed, use explicit validation or a lifecycle component after the context is ready.

## 5. Two Failure Modes: Unchecked Input and Unchecked Return Value

### 5.1. Parameter Check Bypassed

~~~java
public String viaThis(String text) {
    return this.checked(text);
}

@NotBlank
public String checked(@NotBlank String text) {
    return text;
}
~~~

An external call `proxy.checked("")` throws `ConstraintViolationException` before `checked`'s body runs. With `proxy.viaThis("")`, `viaThis` has no constraint and the inner call bypasses the proxy, so it **returns `""` without error**.

This is dangerous when input reaches the service via a **message queue**, **scheduler**, **batch job**, **event consumer**, or internal service rather than an HTTP controller with `@Valid`. Testing only through controllers does not guarantee other callers are protected.

### 5.2. Return-Value Check Bypassed

~~~java
public String viaThisReturn() {
    return invalidReturn();
}

@NotBlank
public String invalidReturn() {
    return "";
}
~~~

`proxy.invalidReturn()` via an external proxy is rejected **after the method returns**. However, `proxy.viaThisReturn()` calls the inner method directly, skipping `invalidReturn`'s return constraint and returning an empty string.

**Side-effect consequence:** a method that already wrote to a database or published an event before a return violation is caught does not automatically guarantee rollback. It may have already committed. Transaction boundaries, idempotency, and reconciliation must be designed independently of method-validation annotations when handling 5xx errors.

### 5.3. Do Not Confuse Inner Constraints with the Outer Method's Contract

If `outer` itself carries a `@NotBlank` return constraint, the proxy checks **outer's return value**, catching an empty string after the self-call. Yet that only protects **outer**, not the bypassed inner method call. If the inner method needed parameter validation *before* starting side effects, adding a return constraint on outer is too late.

## 6. Distinguishing AOP Method Validation from Spring MVC Built-In Method Validation

**Spring Framework 6.1+** includes built-in method validation for **MVC controller handler methods**. Spring docs recommend removing class-level `@Validated` from controllers when using MVC's built-in mechanism instead of an AOP proxy.

Two pipelines:

~~~text
Spring MVC HandlerMethodValidator
    -> Handler method parameters / return value
    -> MethodArgumentNotValidException or
       HandlerMethodValidationException depending on signature

Spring-driven service method validation (AOP)
    -> @Validated service proxy
    -> MethodValidationInterceptor
    -> ConstraintViolationException (default) or
       MethodValidationException (when adaptation enabled)
~~~

In MVC, input method-validation errors normally map to **HTTP 400**, and return-value method-validation errors to **HTTP 500**. In service AOP, `ConstraintViolationException` does not automatically mean a 400 client error: it may come from a **server-generated return value**.

MVC example needing no class-level `@Validated`:

~~~java
@RestController
class SampleController {

    @GetMapping("/pages")
    public String pages(
            @RequestParam @Min(1) int size) {
        return "size=" + size;
    }
}
~~~

This is a snippet; `size=0` is validated by Spring 6.1+ built-in MVC method validation, which does not prove service self-calls are intercepted.

Similarly, `@Valid @RequestBody RequestDto` is validated by MVC after deserialization. Rejecting invalid JSON at the controller **does not mean** an inner service method with `@NotBlank` is intercepted via AOP. Happy-path requests can hide a self-invocation bug for a long time.

**Clear boundary:** this article diagnoses **service AOP proxy self-calls**; it does not claim every Spring/Jakarta validation is bypassed when methods in the same class call one another.

## 7. Practical Verification: Proxy, Advice, and Invalid Calls

Quick diagnostic check:

~~~java
boolean proxyPresent = AopUtils.isAopProxy(service);
boolean cglib = AopUtils.isCglibProxy(service);
boolean jdk = AopUtils.isJdkDynamicProxy(service);
~~~

`AopUtils` belongs to `org.springframework.aop.support.AopUtils`. The `service` variable must be the bean injected from the Spring context, **not `new Service()`**.

If `isAopProxy==false`, check method validation infrastructure, `@Validated`, component scan, provider, and proxy limitations. If `isAopProxy==true`, that only proves **an AOP proxy exists**, not that it carries **method-validation advice** or that self-calls re-enter the proxy.

A minimal test must:
1. Inject the bean from the Spring context.
2. Assert the bean is proxied.
3. Call `bean.checked("")` directly on the injected reference.
4. Expect the validation exception.
5. Call `bean.viaThis("")` with the same input.
6. Observe the self-call is not intercepted.
7. Refactor into a separate bean and re-verify.

Never log entire beans or request bodies while debugging. Data may hold passwords, tokens, or PII. Log safe metadata such as class, method, and error category; avoid serializing `ConstraintViolation#getInvalidValue()` or raw parameters.

## 8. Fixes: Choosing by Clarity and Framework Coupling

### 8.1. Preferred: Split into Two Spring Beans

Avoid:

~~~java
@Service
@Validated
class UnsafeWorkflow {
    public String process(String value) {
        return validateValue(value);
    }

    public String validateValue(@NotBlank String value) {
        return value;
    }
}
~~~

Prefer:

~~~java
@Service
@Validated
class CheckedService {
    public String validateValue(@NotBlank String value) {
        return value;
    }
}

@Service
class Workflow {
    private final CheckedService checkedService;

    Workflow(CheckedService checkedService) {
        this.checkedService = checkedService;
    }

    public String process(String value) {
        return checkedService.validateValue(value);
    }
}
~~~

These are architectural snippets; full code is in Section 9. `checkedService` is a **Spring-injected bean reference**. When it is an advised AOP proxy, the call passes through the interceptor. This improves testability and separation of concerns without circular dependencies or `AopContext`.

### 8.2. Self-Injection

Spring AOP docs mention injecting the bean's own proxy and calling through that reference instead of `this`. Use cautiously:

~~~java
@Service
@Validated
public class SelfInjectedService {

    private final ObjectProvider<SelfInjectedService> self;

    public SelfInjectedService(
            ObjectProvider<SelfInjectedService> self) {
        this.self = self;
    }

    public String process(String value) {
        return self.getObject().check(value);
    }

    public String check(@NotBlank String value) {
        return value;
    }
}
~~~

This **snippet** requires `org.springframework.beans.factory.ObjectProvider`, `@Service`, `@Validated`, and `@NotBlank` imports. `ObjectProvider` defers lookup until invocation; with a compatible proxy, `self.getObject()` obtains the proxy instead of a direct `this` call.

Drawbacks: couples to the Spring container and complicates circular dependencies, proxy types, or lifecycle. **Do not default to self-injection** when splitting beans is simpler and cleaner.

### 8.3. `AopContext.currentProxy()`

Some codebases use:

~~~java
((MyService) AopContext.currentProxy())
        .validatedMethod(value);
~~~

This requires `exposeProxy=true` and an active proxy invocation context, otherwise it throws an exception. It couples domain code to Spring AOP, makes plain-object testing harder, and depends on proxy type. **Spring docs treat this as a last resort**; avoid using it merely to "make annotations run."

### 8.4. Explicit Checks Inside the Method or Boundary

Critical domain invariants can be enforced directly in the method body without relying on AOP:

~~~java
public String requireText(String text) {
    if (text == null || text.isBlank()) {
        throw new IllegalArgumentException(
                "Text must not be blank");
    }
    return text;
}
~~~

This is plain Java logic and executes on every call, including `this` and `new`. In public APIs, map exceptions by **their true error source**—never blindly return 400 if an exception originated from a server-generated value.

When annotation-driven Jakarta Bean Validation is desired, you can call:

~~~java
Set<ConstraintViolation<RequestDto>> violations =
        validator.validate(request);
~~~

This snippet assumes `validator` is `jakarta.validation.Validator` and `request` is `RequestDto`; it checks bean constraints. For constraints on **method parameters or return values**, use `validator.forExecutables().validateParameters(...)` and `validateReturnValue(...)` on the exact method/target—do not assume `validate(request)` checks executable constraints.

### 8.5. AspectJ Weaving

AspectJ compile-time or load-time weaving weaves advice directly into bytecode and does not share Spring AOP proxy's self-invocation limitation. However, build, setup, debugging, and deployment are significantly more complex; do not switch an app just because two methods call each other. **Refactoring to a collaborator bean** is usually far better.

## 9. Runnable Maven Project: Spring Boot 3.5.16, Java 17+

The project deliberately demonstrates **the bug** and **the fix**:

- `SelfCallingService`: self-call bypasses inner parameter and return constraints.
- `CheckedTextService`: validated method placed in a separate Spring bean.
- `DelegatingWorkflow`: calls `CheckedTextService` via a Spring-injected proxy.
- `TextController`: one legacy endpoint intentionally showing the bypass, others showing Spring MVC built-in validation and `@Valid @RequestBody`.
- `SelfInvocationTest`: tests real proxies, direct calls, self-calls, and manual Jakarta `ExecutableValidator`.
- `TextControllerTest`: tests Spring MVC separately from service AOP.

This demo has **no database, no user authentication, and no side effects**. One endpoint is intentionally broken for demonstration and must never be kept in production.

### 9.1. `pom.xml`

Spring Boot `3.5.16` is available on Maven Central, released on 2026-06-25; the publisher notes this is **the final OSS-supported release of the 3.5.x line**. This version is pinned to reproduce Spring Framework 6.x behavior; for new production projects, use an OSS-maintained branch (e.g., Boot 4.x) or commercial support and adapt code/tests accordingly.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
          https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>self-invocation-validation</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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

In this demo, Boot auto-configures method validation when provider/context conditions match, so no manual `MethodValidationPostProcessor` bean is added. `spring-boot-starter-aop` is included explicitly to highlight AOP-based service method validation's dependency.

### 9.2. `SelfInvocationApplication.java`

`src/main/java/com/example/selfcall/SelfInvocationApplication.java`:

~~~java
package com.example.selfcall;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SelfInvocationApplication {

    public static void main(String[] args) {
        SpringApplication.run(SelfInvocationApplication.class, args);
    }
}
~~~

### 9.3. `SelfCallingService.java`

`src/main/java/com/example/selfcall/SelfCallingService.java`:

~~~java
package com.example.selfcall;

import jakarta.validation.constraints.NotBlank;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class SelfCallingService {

    public String viaThis(String text) {
        return this.checked(text);
    }

    public String viaImplicitThis(String text) {
        return checked(text);
    }

    public String viaThisReturn() {
        return invalidReturn();
    }

    @NotBlank
    public String checked(@NotBlank String text) {
        return text;
    }

    @NotBlank
    public String invalidReturn() {
        return "";
    }
}
~~~

Explanation: the class is annotated with `@Validated` and managed by Spring. `checked` has parameter and return constraints. Yet the outer methods **have no direct constraints** and invoke the inner method on the same target, so they do not trigger the inner method's advice. `invalidReturn` is intentionally broken to test return-value validation on direct proxy calls.

### 9.4. `CheckedTextService.java`

`src/main/java/com/example/selfcall/CheckedTextService.java`:

~~~java
package com.example.selfcall;

import jakarta.validation.constraints.NotBlank;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class CheckedTextService {

    @NotBlank
    public String check(@NotBlank String text) {
        return text;
    }

    @NotBlank
    public String invalidReturn() {
        return "";
    }
}
~~~

### 9.5. `DelegatingWorkflow.java`

`src/main/java/com/example/selfcall/DelegatingWorkflow.java`:

~~~java
package com.example.selfcall;

import org.springframework.stereotype.Service;

@Service
public class DelegatingWorkflow {

    private final CheckedTextService checked;

    public DelegatingWorkflow(CheckedTextService checked) {
        this.checked = checked;
    }

    public String submit(String text) {
        return checked.check(text);
    }

    public String brokenReturnForTest() {
        return checked.invalidReturn();
    }
}
~~~

The call `checked.check(text)` invokes **a Spring-injected bean**, rather than `this.check(text)` on `CheckedTextService`. With the proper bean proxy, parameter and return constraints are evaluated.

### 9.6. `TextRequest.java`

`src/main/java/com/example/selfcall/TextRequest.java`:

~~~java
package com.example.selfcall;

import jakarta.validation.constraints.NotBlank;

public record TextRequest(@NotBlank String value) {
}
~~~

A record holding a Bean Validation constraint on its input. MVC validates this record via `@Valid @RequestBody`, independently of whether a service self-calls methods via `this`.

### 9.7. `TextController.java`

`src/main/java/com/example/selfcall/TextController.java`:

~~~java
package com.example.selfcall;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/diagnostics")
public class TextController {

    private final SelfCallingService legacy;
    private final DelegatingWorkflow workflow;

    public TextController(
            SelfCallingService legacy,
            DelegatingWorkflow workflow) {
        this.legacy = legacy;
        this.workflow = workflow;
    }

    // Anti-pattern: service self-call can return 200 with empty text.
    @GetMapping("/legacy")
    public String legacy(@RequestParam("value") String value) {
        return legacy.viaThis(value);
    }

    // Built-in MVC handler method validation (Spring Framework 6.1+).
    @GetMapping("/mvc")
    public String mvc(
            @RequestParam("value") @NotBlank String value) {
        return value;
    }

    // MVC validates the DTO first; the delegated service uses its own proxy.
    @PostMapping(path = "/submit",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<String> submit(
            @Valid @RequestBody TextRequest request) {
        return ResponseEntity.ok(
                workflow.submit(request.value()));
    }
}
~~~

**Do not place class-level `@Validated` on the controller**, so Spring MVC 6.1+ uses built-in handler method validation. Adding that class-level annotation can switch the controller to AOP proxy-based method validation, altering exception types and test behavior.

### Endpoints and Expected Statuses

| Endpoint | Input | Designed result in demo |
| --- | --- | --- |
| `GET /diagnostics/legacy` | `value=` | 200 + empty body — **intentionally demonstrates bypass**, not a safe API. |
| `GET /diagnostics/mvc` | `value=` | 400 due to handler parameter `@NotBlank`. |
| `GET /diagnostics/mvc` | `value=hello` | 200, body `hello`. |
| `POST /diagnostics/submit` | `{"value":""}` | 400 due to `@Valid @RequestBody`. |
| `POST /diagnostics/submit` | `{"value":"hello"}` | 200, body `hello`. |

The legacy endpoint is only a test fixture. Never use it to conclude "200 on invalid data is acceptable"; its purpose is letting a regression test expose the bug so it gets fixed.

## 10. `SelfInvocationTest.java`: 12 Tests Proving AOP Behavior

`src/test/java/com/example/selfcall/SelfInvocationTest.java`:

~~~java
package com.example.selfcall;

import jakarta.validation.ConstraintViolationException;
import jakarta.validation.Validator;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.lang.reflect.Method;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class SelfInvocationTest {

    @Autowired
    SelfCallingService self;

    @Autowired
    CheckedTextService checked;

    @Autowired
    DelegatingWorkflow workflow;

    @Autowired
    Validator validator;

    @Test
    void beanIsProxied() {
        assertTrue(AopUtils.isAopProxy(self));
        assertTrue(AopUtils.isAopProxy(checked));
    }

    @Test
    void externalCallRejectsBlankParameter() {
        assertThrows(ConstraintViolationException.class,
                () -> self.checked(""));
    }

    @Test
    void explicitThisBypassesParameterCheck() {
        assertEquals("", self.viaThis(""));
    }

    @Test
    void implicitThisAlsoBypassesParameterCheck() {
        assertEquals("", self.viaImplicitThis(""));
    }

    @Test
    void externalValidCallWorks() {
        assertEquals("hello", self.checked("hello"));
    }

    @Test
    void externalCallChecksReturnConstraint() {
        assertThrows(ConstraintViolationException.class,
                () -> self.invalidReturn());
    }

    @Test
    void internalCallSkipsReturnConstraint() {
        assertEquals("", self.viaThisReturn());
    }

    @Test
    void delegatedCallRejectsBlankInput() {
        assertThrows(ConstraintViolationException.class,
                () -> workflow.submit(""));
    }

    @Test
    void delegatedCallAcceptsValidInput() {
        assertEquals("hello", workflow.submit("hello"));
    }

    @Test
    void delegatedReturnViolationIsDetected() {
        assertThrows(ConstraintViolationException.class,
                () -> workflow.brokenReturnForTest());
    }

    @Test
    void newObjectIsNotAnAopProxy() {
        SelfCallingService plain = new SelfCallingService();
        assertFalse(AopUtils.isAopProxy(plain));
        assertEquals("", plain.checked(""));
    }

    @Test
    void manualExecutableValidationStillFindsConstraints()
            throws Exception {
        SelfCallingService plain = new SelfCallingService();

        Method inputMethod = SelfCallingService.class
                .getMethod("checked", String.class);

        var inputErrors = validator.forExecutables()
                .validateParameters(
                        plain, inputMethod, new Object[] {""});

        assertFalse(inputErrors.isEmpty());

        Method outputMethod = SelfCallingService.class
                .getMethod("invalidReturn");

        var outputErrors = validator.forExecutables()
                .validateReturnValue(
                        plain, outputMethod, "");

        assertFalse(outputErrors.isEmpty());
    }
}
~~~

**Meaning of the 12 tests:**

1. Beans have Spring AOP proxies.
2. External invalid input is rejected.
3. Explicit `this` bypasses the parameter constraint.
4. Implicit `this` bypasses similarly.
5. External valid input succeeds.
6. External invalid return is rejected.
7. Internal invalid return is not intercepted.
8. Delegating to another bean rejects invalid input.
9. Delegation accepts valid input.
10. Delegation catches invalid return values.
11. Plain `new` instance has no proxy.
12. Manual Jakarta `ExecutableValidator` still sees the constraint metadata.

**Exception nuance:** under default `MethodValidationPostProcessor` configuration, method-validation AOP throws `ConstraintViolationException`. If a project enables `setAdaptConstraintViolations(true)`, Spring throws `MethodValidationException` instead; align tests with your config rather than deleting negative cases.

**Strength of the manual test:** Bean Validation metadata still exists despite the self-call bypass; `ExecutableValidator` catches it because we **call the explicit API**, cleanly separating "missing annotation" from "bypassed proxy."

## 11. `TextControllerTest.java`: 7 MockMvc Tests Separating MVC from AOP

`src/test/java/com/example/selfcall/TextControllerTest.java`:

~~~java
package com.example.selfcall;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class TextControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void legacyCallDemonstratesIncorrect200() throws Exception {
        mvc.perform(get("/diagnostics/legacy")
                    .param("value", ""))
                .andExpect(status().isOk())
                .andExpect(content().string(""));
    }

    @Test
    void mvcMethodValidationRejectsBlankQuery()
            throws Exception {
        mvc.perform(get("/diagnostics/mvc")
                    .param("value", ""))
                .andExpect(status().isBadRequest());
    }

    @Test
    void mvcMethodValidationAcceptsValidQuery()
            throws Exception {
        mvc.perform(get("/diagnostics/mvc")
                    .param("value", "hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("hello"));
    }

    @Test
    void validJsonBodyCallsDelegatedWorkflow()
            throws Exception {
        mvc.perform(post("/diagnostics/submit")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"value":"hello"}
                            """))
                .andExpect(status().isOk())
                .andExpect(content().string("hello"));
    }

    @Test
    void blankJsonBodyFieldIsRejectedByMvc()
            throws Exception {
        mvc.perform(post("/diagnostics/submit")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"value":""}
                            """))
                .andExpect(status().isBadRequest());
    }

    @Test
    void malformedJsonIsRejectedBeforeBeanValidation()
            throws Exception {
        mvc.perform(post("/diagnostics/submit")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"value\":"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void missingRequiredQueryIsBadRequest()
            throws Exception {
        mvc.perform(get("/diagnostics/mvc"))
                .andExpect(status().isBadRequest());
    }
}
~~~

There are **7 MockMvc tests**. The first intentionally asserts **unsafe** behavior to demonstrate the bypass in the demo; once fixed in a real app, update it to assert invalid input is rejected.

For `@Valid @RequestBody`, Spring MVC validates the record during argument resolution; this **differs** from AOP method validation on `CheckedTextService`. Thus the service test suite (12) is necessary alongside HTTP tests (7).

### 11.1. Running the Test Suite

In the directory containing `pom.xml`:

~~~bash
mvn test
mvn spring-boot:run
~~~

If using Maven wrapper:

~~~bash
./mvnw test
./mvnw spring-boot:run
~~~

On Windows:

~~~powershell
mvnw.cmd test
mvnw.cmd spring-boot:run
~~~

Total **19 tests**: 12 service tests + 7 MockMvc tests. They are **designed** for the version and source code above; providing code in the article **does not prove Maven/JUnit was executed**. When integrating into a repository, execute them and inspect reports. Test statuses/bodies may need adjustment if your project adds Spring Security, global `@ControllerAdvice`, or custom web config.

### 11.2. Curl

~~~bash
curl -i "http://localhost:8080/diagnostics/legacy?value="
curl -i "http://localhost:8080/diagnostics/mvc?value="
curl -i "http://localhost:8080/diagnostics/mvc?value=hello"

curl -i -X POST "http://localhost:8080/diagnostics/submit" \
  -H "Content-Type: application/json" \
  -d '{"value":"hello"}'

curl -i -X POST "http://localhost:8080/diagnostics/submit" \
  -H "Content-Type: application/json" \
  -d '{"value":""}'
~~~

Expected statuses for the five requests are **200, 400, 200, 200, 400**. The first request **intentionally demonstrates the bug**; the two valid responses return `hello`. Spring Boot's default error bodies are not hardcoded because they vary by version/`ProblemDetail` config and exception handlers.

## 12. Debugging When Tests or Production Misbehave

### 12.1. `AopUtils.isAopProxy(service) == false`

Check:
- Is the bean container-managed or instantiated via `new`?
- Is `@Validated` on the class or a location recognized by the processor?
- Are `spring-boot-starter-validation`, Jakarta provider, and method-validation post-processor present?
- Is Spring AOP on the classpath and post-processing active?
- Is the class `final`, or affected by method visibility or proxy constraints?
- Was the bean replaced by a mock/spy lacking advice in tests?

**Never register an extra processor immediately** before checking Boot auto-config. Two processors are harder to reason about than one properly configured processor.

### 12.2. Proxy Exists Yet Invalid Input Throws No Exception

Check:
- Are you calling the bean proxy or calling `this`?
- Are constraints placed **on the parameter/return of the exact method**?
- Is `@NotBlank` on a compatible type? `@Min` on a numeric type?
- Is a validation group other than `Default` active?
- Does `MethodValidationPostProcessor` target the `@Validated` annotation?
- Is the call public/interceptable and exposed on the proxied interface?
- Does `adaptConstraintViolations` change the exception class?

**A breakpoint inside the method body is not enough** to prove validation ran; a self-call still enters the method body like normal Java.

### 12.3. Fails Only From Web Requests, Not From Jobs

The web controller may run `@Valid`/built-in method validation while the job hits a service self-call. Write tests **calling the Spring-injected service directly** and verify the job/batch path too. Web DTO constraints do not protect every entry point.

### 12.4. `@Transactional` or `@Async` Also Behave Strangely

Other proxy-based advice suffers the exact same self-invocation bypass. Do not solve it by cramming every method into one service with more annotations; separate clear component boundaries, align transaction boundaries, and test side effects.

### 12.5. Return-Value Violations Mapped to HTTP 400

Never write globally:

~~~java
@ExceptionHandler(ConstraintViolationException.class)
ResponseEntity<?> onViolation(ConstraintViolationException ex) {
    return ResponseEntity.badRequest().build();
}
~~~

This is an **anti-pattern** if the handler can receive service return-value violations. A `ConstraintViolationException` from service AOP does not automatically prove client input was invalid. Distinguish whether the failure happened on a **client-supplied parameter**, a **server-generated return value**, or an internal service call. With MVC 6.1+ built-in validation, `HandlerMethodValidationException#isForReturnValue()`/`getStatusCode()` separates 400 from 500; with service AOP, design matching mappings.

### 12.6. Using `AopContext.currentProxy()` Breaks Plain Java Tests

`AopContext` requires proxy exposure and an active invocation context. Plain unit tests using `new` have no current proxy. Refactoring to an injected collaborator bean is far simpler. Never force domain code to depend on `AopContext` just to avoid refactoring.

## 13. Common Mistakes and Fixes

| Anti-pattern | Consequence | Fix |
| --- | --- | --- |
| `this.validate(value)` with `@NotBlank` on inner method | Inner AOP validation is bypassed. | Extract bean and inject proxy, or validate explicitly. |
| Removing `this` keyword | Still an implicit self-call. | Change the call path, not just syntax. |
| Only putting `@Validated` on the class | Does not guarantee every call is advised. | Check provider, processor, proxy, and call boundary. |
| `new Service().checked(value)` | No Spring-managed proxy. | Obtain bean from context or validate explicitly. |
| Testing only an outer method that has its own constraint | Hides inner self-invocation bugs. | Test inner constraints directly and via outer separately. |
| Expecting AOP on `private`/`final` methods | Standard proxy mechanisms cannot intercept them. | Use public/interceptable collaborator methods. |
| Method missing from JDK proxy interface | Callers injecting interface cannot invoke implementation-only methods. | Design proper interfaces/proxy types. |
| Constructor self-injection | Circular dependencies/lifecycle complexity. | Prefer separate beans, or test lazy lookup if needed. |
| Defaulting to `AopContext.currentProxy()` | Tight coupling, requires `exposeProxy` config. | Refactor to collaborator. |
| Adding duplicate post-processor alongside Boot | Complicates proxies/advice unpredictably. | Inspect context/auto-configuration first. |
| Relying on `@Valid` in MVC to keep services safe | Queues/jobs bypass controller validation. | Add service-level proxy/explicit tests. |
| Catching all `ConstraintViolationException` -> 400 | Hides server return-value bugs. | Classify input vs. return-value violations properly. |
| Checking only `isAopProxy` | Proxy might lack the advisor or still suffer self-calls. | Test invalid arguments/returns through the proxy. |
| Changing `proxy-target-class` to fix self-calls | Both JDK and CGLIB bypass `this` calls. | Split into separate beans. |
| Using AspectJ weaving just to fix one helper | Unnecessary build/deployment complexity. | Refactor first. |

## 14. Regression Test Checklist

- [ ] Test verifies the `@Validated` bean is Spring-managed and has an AOP proxy.
- [ ] Test verifies direct external call with invalid parameter → validation exception.
- [ ] Test verifies `this.inner(invalid)` → reproduces bypass in the broken version.
- [ ] Test verifies `inner(invalid)` without `this` → still bypasses.
- [ ] Test verifies external return-value violation and internal return-value bypass.
- [ ] Test verifies call across **two Spring beans** after refactoring is intercepted.
- [ ] Test verifies valid input through the proxy succeeds.
- [ ] Test verifies plain `new` instance does not run method validation automatically.
- [ ] Test verifies manual `ExecutableValidator` still sees constraint metadata.
- [ ] `@Validated`/provider/AOP/`MethodValidationPostProcessor` configuration verified.
- [ ] No `private`/`final` methods relied upon as AOP security/validation boundaries.
- [ ] Under JDK proxies, interfaces expose all methods needing advice.
- [ ] No unnecessary circular self-injection or default reliance on `AopContext`.
- [ ] Service AOP distinguished from Spring MVC 6.1+ built-in validation.
- [ ] No class-level `@Validated` on controllers when built-in MVC validation is intended without evaluating AOP.
- [ ] Under method-validation exception adaptation, `ConstraintViolationException` vs. `MethodValidationException` tested per configuration.
- [ ] Input validation runs **before side effects**; output validation and transaction boundaries checked.
- [ ] API never returns 400 for server return violations or leaks rejected values.
- [ ] Scheduled jobs/event consumers outside HTTP requests have dedicated tests.
- [ ] Re-run regression tests when changing service injection, proxy mode, groups, or Spring version.

**Conclusion:** In Spring AOP-based method validation, **`this.inner(...)` and `inner(...)` do not pass through the proxy**, so `@NotBlank`/`@NotNull`/`@Min` on the inner method **are skipped** for both parameters and return values. The cleanest fix is usually **extracting the validated inner method into another Spring bean and injecting/calling that bean**, or performing explicit validation. Always verify with tests calling **the real Spring bean proxy**, keeping service AOP distinct from Spring MVC 6.1+ built-in handler validation.

## References

- Spring Framework 6.2 — **Proxying Mechanisms / Understanding AOP Proxies**, self-invocation and solutions: https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html
- Spring Framework 6.2 — **Spring-driven Method Validation**, `MethodValidationPostProcessor` and exception adaptation: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Framework 6.2 Javadoc — `MethodValidationPostProcessor`: https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/validation/beanvalidation/MethodValidationPostProcessor.html
- Spring Framework 6.2 — **MVC Validation**, ``MethodArgumentNotValidException` / `HandlerMethodValidationException`: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — AOP proxy mechanisms on current branch: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Jakarta Bean Validation 3.0 API — `ExecutableValidator`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/executable/executablevalidator
- Spring Boot 3.5.16 released 2026-06-25 (final 3.5.x OSS release): https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
