# MethodValidationPostProcessor and @Validated Beans in Spring Framework

## 1. Why Validate at Method Boundaries?

Bean Validation does not only validate properties of a DTO/entity. It also offers **executable validation**: validating the parameters a method receives and the value it returns. This is especially useful in the service layer, where many different callers can invoke the same business logic: an HTTP controller, a message consumer, a scheduled job, or another service.

For example, a method's contract might be:

```java
@NotBlank
public String reserve(@NotBlank String productCode, @Min(1) int quantity) {
    return "reserved:" + productCode + ":" + quantity;
}
```

The three independent constraints here are: `productCode` must contain non-whitespace text, `quantity` must be at least 1, and the returned result must not be empty/blank. These annotations describe the contract, but **they do not automatically cause every Java call to be validated**.

In a Spring-managed bean, `org.springframework.validation.beanvalidation.MethodValidationPostProcessor` is the infrastructure component connecting Jakarta Bean Validation to a **Spring AOP proxy**. A bean annotated with `org.springframework.validation.annotation.Validated` at the class level becomes eligible for Spring to apply advice that validates inputs/outputs when calls go through the proxy.

This is the focus of this lesson: **how the post-processor selects `@Validated` beans, creates proxies, and executes method validation, along with the limits of that mechanism**.

## 2. Roles to Distinguish

| Component | Responsibility |
| --- | --- |
| Spring's `@Validated` | At the class level, marks a bean eligible for method-validation advice; can specify validation groups. |
| `MethodValidationPostProcessor` | Infrastructure BeanPostProcessor that detects matching beans, attaches the advisor/interceptor, and enables AOP proxy creation. |
| `MethodValidationInterceptor` | Runs parameter validation before invocation, and return-value validation after invocation, via Bean Validation. |
| `jakarta.validation.Validator`/`ExecutableValidator` | Engine/provider that actually evaluates constraints (typically Hibernate Validator). |
| `@NotNull`, `@Min`, `@NotBlank`, ... | Direct constraints on parameters or return values. |
| Jakarta's `@Valid` | Marks cascading into properties inside parameter/return-value objects. |
| Method-level `@Validated` | Can override validation groups for a method on an already-eligible bean; **does not itself create a pointcut for a bean lacking class-level `@Validated`**. |

In Spring Framework 6.x/Spring Boot 3.x, the corresponding imports are `jakarta.validation.*`. Avoid mixing with the `javax.validation.*` namespace from older versions.

A standalone `@Validated` is also **not** a constraint; it does not forbid `null` and does not check string length. Specific constraints or cascade metadata define what gets validated.

## 3. Conditions for a Bean to Be Validated

For AOP-based method validation to work properly, all of the following must hold:

1. A **Jakarta Bean Validation provider** is on the classpath, such as Hibernate Validator; having only the annotation API without a provider is insufficient.
2. `MethodValidationPostProcessor` is registered and initialized in the Spring ApplicationContext. In typical Spring Boot applications, `spring-boot-starter-validation` supplies the provider and Boot auto-configures method validation. In plain Spring Framework applications, you can declare the post-processor yourself.
3. The target bean belongs to the Spring container, is annotated with `@Validated` at the type level (or an equivalent annotation configured as the pointcut), and has valid constraints.
4. Methods are called **through the Spring AOP proxy** and are interceptable by the proxy. Calling `new MyService()`, calling directly on the target, or calling `this.otherMethod()` bypasses the proxy.
5. Public/method visibility allows proxying and the proxy type matches how the method is invoked.

General flow diagram:

```text
Another bean / controller / runner
        │
        ▼
Spring bean reference (AOP proxy)
        │
        ├── validateParameters(...)  ── error: throw exception, do not invoke target
        │
        ▼
Target.method(arguments)
        │
        ├── method throws exception? propagate original exception along call flow
        │
        ▼
validateReturnValue(...) ── error: throw exception after target has run
        │
        ▼
Return result to caller
```

**Key point:** parameter constraints are checked **before** entering the method body. Result constraints are checked **after** the method has already run. Therefore, if a return postcondition is violated, side effects inside the method body may already have happened. Whether a transaction rolls back depends on advice ordering, rollback rules, and exception type; do not assume automatic undo in all cases.

## 4. Registering MethodValidationPostProcessor

### 4.1. Using Spring Boot

In a Spring Boot application with a Bean Validation provider, method validation support is typically **enabled automatically**. With `spring-boot-starter-validation` present, you do not need to declare an extra `MethodValidationPostProcessor` just to use `@Validated` on services.

For applications needing full AOP support, adding `spring-boot-starter-aop` provides the relevant proxy/advice dependencies. Avoid defining a duplicate post-processor alongside Boot's auto-configuration unless you have a specific customization need.

### 4.2. Using Spring Framework Without Boot Auto-Configuration

In standard Spring configuration, you can register the infrastructure as shown in the Spring documentation:

```java
@Configuration
public class ValidationConfiguration {

    @Bean
    public static MethodValidationPostProcessor methodValidationPostProcessor() {
        return new MethodValidationPostProcessor();
    }
}
```

*This is an integration configuration snippet, not a standalone program:* it requires importing `@Configuration`, `@Bean`, `MethodValidationPostProcessor`, and a Jakarta Bean Validation provider. A `@Bean static` method is appropriate because the bean is a BeanPostProcessor; Spring can register it early in the lifecycle before creating other beans.

By default, the post-processor uses the `@Validated` annotation type as its pointcut and relies on the default validator if none is explicitly configured. Notable customization points:

- `setValidator(jakarta.validation.Validator)` or `setValidatorFactory(...)` to choose the validation engine.
- `setAdaptConstraintViolations(true)` to adapt violations into Spring's `MethodValidationResult` and throw `MethodValidationException` instead of `ConstraintViolationException`.
- `setValidatedAnnotationType(...)` if the application intentionally replaces the default marker annotation.
- `setProxyTargetClass(true)` in related configuration if class-based proxies are required; keep `final` class/method limitations in mind.

Customize only when specifically needed. The runnable Java example in the next section uses Boot's auto-configuration and default exception behavior without declaring a custom post-processor.

## 5. Complete Runnable Example with Java 17 and Spring Boot 3.5.x

The example uses **Spring Boot 3.5.6, Java 17, and Maven 3.x**. It does not start an HTTP server, because the topic being demonstrated is method validation on a **Spring service bean**. Four cases illustrate valid parameters, invalid parameters, an invalid return value, and cascading into a DTO via `@Valid`.

Create these files:

```text
method-validation-demo/
├── pom.xml
└── src/main/java/demo/
    ├── ValidationApp.java
    ├── CheckoutService.java
    └── DeliveryAddress.java
```

### `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>method-validation-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
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
```

### `DeliveryAddress.java`

```java
package demo;

import jakarta.validation.constraints.NotBlank;

public record DeliveryAddress(@NotBlank String street) {
}
```

This record has a constraint on the `street` component. When a method parameter is marked `@Valid`, the provider cascades into the record and detects a violation if `street` is blank.

### `CheckoutService.java`

```java
package demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class CheckoutService {

    @NotBlank
    public String confirm(@NotBlank String sku, @Min(1) int quantity) {
        return "receipt:" + sku + ":" + quantity;
    }

    @NotBlank
    public String badReceipt(@NotBlank String sku) {
        return ""; // Intentionally violates the constraint on the return value
    }

    public String ship(@Valid DeliveryAddress address) {
        return "shipping:" + address.street();
    }
}
```

`@Service` makes the class a Spring bean. `@Validated` at the **class level** allows the method validation infrastructure to select this bean. `confirm` has both parameter and return constraints; `badReceipt` always returns an invalid result as a demo; `ship` uses cascading validation via `@Valid`.

### `ValidationApp.java`

```java
package demo;

import java.util.List;
import java.util.function.Supplier;

import jakarta.validation.ConstraintViolationException;

import org.springframework.boot.Banner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ValidationApp {

    public static void main(String[] args) {
        SpringApplication application = new SpringApplication(ValidationApp.class);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = application.run(args)) {
            // CommandLineRunner was invoked during context startup.
        }
    }

    @Bean
    CommandLineRunner demo(CheckoutService service) {
        // service is injected by Spring, so it is a proxy if advised.
        return args -> {
            check("VALID", () -> service.confirm("SKU-100", 2));
            check("INVALID_INPUT", () -> service.confirm("", 0));
            check("INVALID_RETURN", () -> service.badReceipt("SKU-100"));
            check("INVALID_NESTED",
                  () -> service.ship(new DeliveryAddress("")));
        };
    }

    private static void check(String label, Supplier<String> action) {
        try {
            System.out.println(label + " => " + action.get());
        } catch (ConstraintViolationException ex) {
            List<String> violated = ex.getConstraintViolations().stream()
                .map(v -> v.getConstraintDescriptor()
                    .getAnnotation().annotationType().getSimpleName())
                .sorted()
                .toList();

            System.out.println(label + " => " + String.join(", ", violated));
        }
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn -q clean package
mvn -q spring-boot:run
```

Lines **printed by the application itself** in order, excluding separate Spring Boot/Maven/provider logs if the environment outputs logs:

```text
VALID => receipt:SKU-100:2
INVALID_INPUT => Min, NotBlank
INVALID_RETURN => NotBlank
INVALID_NESTED => NotBlank
```

Explanation:

- `VALID`: valid parameters; `confirm` body executes; return value is also non-blank.
- `INVALID_INPUT`: `sku=""` violates `@NotBlank`, `quantity=0` violates `@Min(1)`. The proxy throws `ConstraintViolationException` **before** calling `confirm`'s body.
- `INVALID_RETURN`: input `"SKU-100"` is valid, but `badReceipt` returns `""`, violating `@NotBlank` on the return value. The error is caught **after** the method body executes.
- `INVALID_NESTED`: the `DeliveryAddress` object is passed to `ship`; `@Valid` triggers cascading into the record's `@NotBlank` constraint. `street=""` is rejected before `ship`'s body uses `address.street()`.

The example prints annotation type names and sorts strings so the output does not depend on violation set ordering or locale-specific error text. If you remove `@Validated` from `CheckoutService` or instantiate `new CheckoutService()` directly, AOP method validation **no longer automatically intercepts** calls as shown. Declaring annotations on a method does not turn every Java object into a Spring proxy.

## 6. How Proxies Work and Common Limitations

Spring AOP typically creates one of two proxy types:

- **JDK dynamic proxy:** interface-based, exposing only methods on the proxied interfaces. Callers should inject/call through the interface.
- **Class-based proxy (CGLIB):** generates a subclass of the target. It cannot advise `final` methods, `private` methods, or subclass a `final` class. Do not expect non-overridable methods to be validated via this proxy type.

Proxy selection also depends on Spring/Boot configuration and other advisors; do not infer proxy type solely from whether a class implements an interface.

### 6.1. Self-Invocation Bypasses Advice

```java
@Service
@Validated
public class OrderService {

    public void outer() {
        inner(""); // this.inner("") does not go through the proxy
    }

    public void inner(@NotBlank String code) {
        // When called directly on target, the constraint is not evaluated by AOP.
    }
}
```

This is an **independent illustrative snippet on self-invocation**, not part of the sample application. Calling `orderService.outer()` from another bean goes through the proxy, whereas calling `inner("")` within the same target bypasses the proxy and is not handled by `inner`'s own method-validation advice. To validate at that boundary, move the logic to **another bean** and inject it, or design the API so callers go through the proxy.

### 6.2. Instantiating Objects with `new` Bypasses Spring

```java
CheckoutService direct = new CheckoutService();
direct.confirm("", 0); // method body runs normally; no AOP proxy
```

In the example above, the Java code still compiles; the two parameter annotations do not automatically invoke `ExecutableValidator`. If you genuinely need validation outside the container, explicitly use `jakarta.validation.executable.ExecutableValidator` instead of expecting a proxy to work.

### 6.3. Private/Final, Factory Lifecycle, and Circular Dependencies

A BeanPostProcessor takes effect when Spring creates beans and attaches advisors; beans instantiated outside the container or too early relative to the post-processor infrastructure may not be proxied as expected. Avoid testing via `this.method()`, making `@Validated` classes `final` when relying on class-based proxies, or placing critical constraints on private methods. For non-public methods, advisability depends on proxy type and invocation path; public service methods are the least surprising choice.

## 7. Class-Level @Validated, Method-Level @Validated, and Validation Groups

`@Validated` supports validation groups. If no group is specified, Bean Validation normally evaluates `jakarta.validation.groups.Default`.

- `@Validated` on a **class** is the marker for `MethodValidationPostProcessor` to select the bean for method validation; it may include default groups for that bean.
- `@Validated(SpecialChecks.class)` on **a method of an already-eligible bean** can change the active group for that specific method.
- Placing `@Validated` only on a method of a class without a type-level marker **does not** cause `MethodValidationPostProcessor` to select that class.
- Constraints belonging to a different group will not run automatically when only the `Default` group is validated, and vice versa. Design groups to match business rules.

Group example (illustrative snippet, not part of the runnable app above):

```java
interface ApprovalChecks {}

@Validated
public class ApprovalService {

    @Validated(ApprovalChecks.class)
    public void approve(
            @NotNull(groups = ApprovalChecks.class) String approvalCode) {
        // ...
    }
}
```

During a method validation pass using group `ApprovalChecks`, constraints assigned to that group are evaluated. If you add a default-group constraint without including it in the active group, it may not run as expected.

Also note that method constraints are subject to Jakarta Bean Validation inheritance rules: when overriding or implementing an interface, **do not arbitrarily strengthen parameter preconditions** in the overriding method compared to the parent/interface contract. Providers may report an invalid constraint declaration error (such as `ConstraintDeclarationException`). Place parameter constraints at the proper contract level and keep interfaces and implementations consistent.

## 8. Distinguishing AOP Method Validation from Spring MVC

This is a frequent source of confusion when a project has both `@Validated` services and `@RestController` controllers.

### 8.1. On Service/Component Beans

The mechanism in this lesson is:

```text
@Validated on type + MethodValidationPostProcessor
    → Spring AOP proxy → validate method parameter/return
    → defaults to ConstraintViolationException
```

Suitable for input/output contracts on services, message handlers, and scheduled jobs invoked through Spring bean proxies.

### 8.2. On Spring MVC Controllers Since Spring Framework 6.1

Spring MVC has **built-in method validation directly** in its handler invocation infrastructure, without necessarily using `MethodValidationPostProcessor`. When a controller has direct constraints such as `@Min` on `@RequestParam` or constraints on the return value, MVC can perform method validation and raise `HandlerMethodValidationException`.

```java
// Illustrative snippet inside @RestController, not a standalone program:
@GetMapping("/items")
public List<ItemDto> list(@RequestParam @Min(1) int page) {
    return service.find(page);
}
```

Also distinguish `@Valid @RequestBody MyDto` when the DTO has internal constraints. If only validating an individual command object on a parameter without method validation, Spring MVC typically throws `MethodArgumentNotValidException`. If there are direct constraints on a method parameter/return value, method validation covers both direct constraints and `@Valid` cascades, typically with `HandlerMethodValidationException`.

**Specifically:** Spring MVC documentation from 6.1 onward recommends **removing `@Validated` at the controller class level** if you want to use Spring MVC's built-in mechanism. Keeping class-level `@Validated` can route validation through an AOP proxy, bringing different exception types and interception characteristics. Therefore, do not mechanically copy the "services need `@Validated`" rule onto all controllers.

Jakarta's `@Valid` **is not a direct constraint**. It marks cascading; `@Valid` alone does not cause Spring MVC to turn on whole-method validation as direct constraints do. `@NotNull @Valid`, by contrast, includes a direct constraint, so method validation behavior can differ.

When writing `@ControllerAdvice`, design error handling around the actual validation path. Do not assume every error from `@Valid` is a `ConstraintViolationException` or always maps to the same HTTP 400 status in every context.

## 9. Exception Types and Where Errors Are Observed

### Default Mode of MethodValidationPostProcessor

When `setAdaptConstraintViolations(false)` (default), executable validation errors cause the interceptor to throw:

```java
jakarta.validation.ConstraintViolationException
```

The exception holds `getConstraintViolations()` with paths to the parameter/return value, messages, and constraint metadata. Parameter names in paths may depend on compile/parameter-name provider metadata; for stable logging/testing, avoid relying solely on the string representation of paths.

### Adapting to Spring MethodValidationResult

If enabled:

```java
@Bean
public static MethodValidationPostProcessor methodValidationPostProcessor() {
    MethodValidationPostProcessor postProcessor =
        new MethodValidationPostProcessor();
    postProcessor.setAdaptConstraintViolations(true);
    return postProcessor;
}
```

This configuration snippet is for applications **explicitly providing** their own post-processor; do not casually add it alongside another auto-configured bean. When `true`, Spring can throw `org.springframework.validation.method.MethodValidationException`, carrying `ParameterValidationResult` entries and error details convenient for `MessageSource` integration; errors on nested beans can be represented via `ParameterErrors`.

Do not write `catch (ConstraintViolationException)` as in the example and then turn on `setAdaptConstraintViolations(true)` without updating exception handling. Those exception types represent two different contracts.

### Understanding Before/After Execution Order

| Violation location | Has method body run yet? | Meaning |
| --- | --- | --- |
| Parameter with invalid `@NotBlank`/`@Min` | No | Rejects call before execution |
| Parameter DTO with `@Valid` and invalid child field | No, if cascading is triggered | Rejects based on nested constraint |
| Return value violates `@NotNull`/`@NotBlank` | Already ran | Detects postcondition failure after execution |
| Method itself throws business exception | May have partially run | No successful return value to post-validate normally |

In applications using `@Transactional`, advice ordering and transaction rollback rules must be checked separately; method validation is not a transaction management mechanism.

## 10. Testing Real Behavior Through the Spring Proxy

When testing service logic, use two types of tests with distinct goals:

1. **Direct unit tests** on `new CheckoutService()` to test pure business logic; do not treat them as proof that AOP method validation works.
2. **Integration tests via the Spring context**, injecting the real `@Validated` bean and asserting exceptions on calls through the proxy. Only this verifies the marker, BeanPostProcessor, provider, advice, and method signatures in a real environment.

Illustrative test example assuming `spring-boot-starter-test` is present (code must be placed in a test project with matching configuration/annotations):

```java
@SpringBootTest
class CheckoutServiceMethodValidationTest {

    @Autowired
    CheckoutService service;

    @Test
    void rejectsInvalidParametersThroughProxy() {
        assertThrows(
            ConstraintViolationException.class,
            () -> service.confirm("", 0)
        );
    }

    @Test
    void rejectsInvalidReturnValue() {
        assertThrows(
            ConstraintViolationException.class,
            () -> service.badReceipt("SKU-100")
        );
    }
}
```

The test snippet above only illustrates the testing approach and omits dependency/import files; the runnable example in section 5 is already enough to observe AOP in action. Another diagnostic step is using `AopUtils.isAopProxy(service)` in a Spring AOP environment to confirm the reference is proxied. That proves a proxy exists, though you should still assert validation outcomes to verify the right advice is applied.

### Checklist When "@Validated Is Present but No Errors Occur"

- Are a Bean Validation provider and post-processor both present?
- Is `@Validated` actually on a type matched by the pointcut?
- Are you injecting the Spring bean or calling `new` directly?
- Does the call go through the proxy, or is it `this.method()`?
- Is the method advisable (interface/JDK proxy, class-based proxy, `final`/`private`)?
- Is the constraint on a parameter, return value, or child object via `@Valid`?
- Does the active group match the constraint's `groups=...`?
- Do annotations on interfaces and implementations form an invalid Bean Validation contract?
- Which exception type is being caught/handled? Is `setAdaptConstraintViolations(true)` enabled?
- Is this a service bean via AOP or a Spring MVC controller using built-in validation?

## 11. Common Misconceptions

- **"Putting `@NotNull` on a parameter is enough":** Annotations only declare constraints; you need a mechanism to invoke the validator, such as an interceptor via a Spring proxy or an explicit `ExecutableValidator` call.
- **"`@Validated` on a single method turns it on for the whole class":** In default AOP method validation, the pointcut is type-based; marking the class is the required step.
- **"`@Valid` and `@Validated` are always the same":** Jakarta's `@Valid` is primarily for cascading, whereas Spring's `@Validated` selects groups and marks beans for method validation.
- **"Every call to a bean goes through the proxy":** Self-invocation, manually instantiated objects, and non-advisable methods can bypass the interceptor.
- **"Return-value validation guarantees no side effects":** Postcondition checks happen after the method body runs.
- **"Controllers always need class-level `@Validated`":** Spring MVC 6.1+ has built-in method validation; class-level `@Validated` can alter the processing path.
- **"Enabling `setAdaptConstraintViolations(true)` changes nothing":** It changes the exception type and error data structure that callers must handle.

## 12. Summary

`MethodValidationPostProcessor` registers advice that validates **parameters before** and **results after** method calls on Spring beans annotated with `@Validated` at the type level. It is a **proxy-based** mechanism: correctness depends on the bean being Spring-managed, calls going through the proxy, methods being advisable, and a Bean Validation provider being present.

When building service APIs, declare constraints on signatures, mark eligible beans, invoke through injected beans, and test with the Spring context. When working with MVC controllers, distinguish Spring Framework 6.1's built-in mechanism from the AOP mechanism to choose the right annotations and exception handlers.

## References

- Spring Framework — Java Bean Validation, section *Spring-driven Method Validation*: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring Boot — Validation and method validation auto-configuration: https://docs.spring.io/spring-boot/reference/io/validation.html
- Spring Framework — `MethodValidationPostProcessor` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/validation/beanvalidation/MethodValidationPostProcessor.html
- Spring Framework — Spring MVC validation and `@Validated` on controllers: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — AOP proxying, self-invocation, and final methods: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — `@Validated` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/validation/annotation/Validated.html