# ValidatorFactory, Validator, and Resource Lifecycle

> **Context:** Jakarta Bean Validation (with Hibernate Validator as a popular provider) in Java and Spring Framework applications. This lesson distinguishes the roles of `ValidatorFactory`, `Validator`, `ConstraintValidatorFactory`, and `ConstraintValidator`, resource management, thread safety under concurrency, and differences between manual bootstrapping and Spring management. Examples use Java 17+ and Spring Boot 3.3.x / Spring Framework 6.x.

## 1. Why Distinguish Factory and Validator?

Bean Validation allows declaring constraints on models with annotations such as `@NotNull`, `@NotBlank`, `@Min`, `@Size`, and custom constraints. Annotations are merely **metadata**; an implementation of the Jakarta Validation API (called a *provider*, e.g., Hibernate Validator) is needed to read metadata, select checking logic, and produce results.

In the `jakarta.validation` API:

- **`ValidatorFactory`** is the object created when **bootstrapping** the provider. It holds global configuration, can prepare/cache metadata, and creates or supplies `Validator` instances. Creating a factory is typically more expensive than obtaining a validator. A factory is designed to be shared and must be closed at the end of its lifecycle.
- **`Validator`** is the business invocation point, executing `validate(...)`, `validateProperty(...)`, and `validateValue(...)`, returning `Set<ConstraintViolation<T>>`. A validator is lightweight, *thread-safe* per the API contract, and **has no `close()`**.
- **`ConstraintValidatorFactory`** is used by the provider to instantiate and release **each constraint's implementation**, such as the class checking `@ValidSku`. It is **not synonymous** with `ValidatorFactory`.
- **`ConstraintValidator<A,T>`** contains `initialize(A)` (if needed) and `isValid(T, ConstraintValidatorContext)` logic to validate a value. Instance creation, caching, and release belong to the provider together with `ConstraintValidatorFactory`.

Relationship diagram:

```text
Application / Spring container
          │
          ▼
  ValidatorFactory  ────── configuration, metadata, cache (provider-dependent)
          │
          ├──── getValidator() ────► Validator
          │                              │
          │                              └── validate(order) ───► Set<ConstraintViolation>
          │
          └──── ConstraintValidatorFactory ──► ConstraintValidator instances
                      create / release               initialize / isValid

  Factory owner ──────────► close() at end of lifecycle
```

**Core principle:** **create the factory for the application or deployment unit lifecycle, obtain/reuse the validator across checks, and close only the factory you own**.

## 2. Detailed Object Comparison

| Object | Where Created | Purpose | Recommended Scope/Lifecycle | Closing Responsibility |
| --- | --- | --- | --- | --- |
| `jakarta.validation.ValidatorFactory` | `Validation.buildDefaultValidatorFactory()`, provider builder, or initialized by Spring | Initializes/provides `Validator`, global config, shared metadata | One reused instance per deployment unit or dedicated configuration | **The creator/container owning the factory** calls `close()` at the right time |
| `jakarta.validation.Validator` | `factory.getValidator()` or `factory.usingContext().getValidator()`; can also be injected by Spring | Validates beans/properties/values, inspects metadata, returns violations | Reused across multiple requests and threads per the API | Has no `close()`; do not continue using after parent factory closes |
| `jakarta.validation.ValidatorContext` | `factory.usingContext()` | Customizes configuration for a specific validator (e.g., clock, interpolator) | Context to build a validator from the current factory | Not closed separately; the factory remains the resource owner |
| `jakarta.validation.ConstraintValidatorFactory` | Configured by provider or integration/container | Creates and releases constraint validator instances | Depends on provider configuration and DI | Provider calls `releaseInstance` per contract; do not manually release provider-managed instances |
| `jakarta.validation.ConstraintValidator` | Provider asks `ConstraintValidatorFactory` to create | Implements constraint logic | Caching/reuse decided by the provider | Do not create/close per request; write `isValid` to be thread-safe |

**Do not confuse identically named APIs:** Spring also has `org.springframework.validation.Validator` with `supports(Class<?>)` and `validate(Object, Errors)`. That is Spring's interface for the `Errors`/`BindingResult` mechanism, distinct from `jakarta.validation.Validator` returning `ConstraintViolation`. Spring's `LocalValidatorFactoryBean` is the bridge capable of serving both interfaces.

## 3. Proper Lifecycle When Using Jakarta Validation Directly

### 3.1. Bootstrap once, use many times, close once

```text
Startup / open a long-lived unit of work
    │
    ▼
Validation.buildDefaultValidatorFactory()
    │
    ├─► getValidator() ─► validate(bean A)
    │                  ├► validate(bean B)
    │                  └► validate(bean C)
    │
    └─► usingContext() ─► getValidator() ─► validate(bean D)
    │
End of the lifecycle you own
    ▼
factory.close()
    └─► stop using the factory or any Validator it created
```

According to the Jakarta Validation specification, both `ValidatorFactory` and `Validator` are **thread-safe**; one factory can serve multiple threads and validators can be shared. The provider can cache metadata and validators. There is no requirement to create a factory per request, per `validate` call, or per DTO type.

`ValidatorFactory` extends `AutoCloseable`; in self-managed code, use `try-with-resources` when the factory's lifetime has a clear start and end. For a long-running application, create the factory at startup and close it at shutdown. Calling `close()` renders the factory unusable; **any validator created from that factory must also no longer be used**. Continued use is non-portable and not guaranteed by the specification.

### 3.2. Runnable Java 17+ Example

Create a Maven project:

```text
validation-lifecycle/
├── pom.xml
└── src/main/java/demo/ValidatorLifecycleDemo.java
```

**`pom.xml`** — `spring-boot-starter-validation` brings Jakarta Validation API and Hibernate Validator onto the classpath. The program is a standalone Java `main` and **does not start a Spring ApplicationContext**:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>validation-lifecycle</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/demo/ValidatorLifecycleDemo.java`**:

```java
package demo;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import java.util.List;

public class ValidatorLifecycleDemo {

    static final class Order {
        @NotBlank
        private final String customer;

        @Min(1)
        private final int quantity;

        Order(String customer, int quantity) {
            this.customer = customer;
            this.quantity = quantity;
        }
    }

    public static void main(String[] args) {
        // Factory created by main(), so main() is responsible for closing it.
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();

            List<String> errors = validator
                    .validate(new Order("", 0))
                    .stream()
                    .map(ValidatorLifecycleDemo::describe)
                    .sorted()
                    .toList();

            System.out.println("violations=" + errors.size());
            errors.forEach(System.out::println);

            boolean valid = validator
                    .validate(new Order("Mai", 2))
                    .isEmpty();
            System.out.println("valid=" + valid);

        } // Calls factory.close(), even if an exception occurs.
    }

    private static String describe(ConstraintViolation<?> violation) {
        String field = violation.getPropertyPath().toString();
        String constraint = violation.getConstraintDescriptor()
                .getAnnotation()
                .annotationType()
                .getSimpleName();
        return field + ":" + constraint;
    }
}
```

Using JDK 17+ and Maven, run from the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ValidatorLifecycleDemo
```

Lines **printed by the program**, excluding any logs from Maven/provider:

```text
violations=2
customer:NotBlank
quantity:Min
valid=true
```

Explanation: `@NotBlank` fails on the empty string; `@Min(1)` fails on `0`. `ConstraintViolation` is formatted as `field:ConstraintName` and **sorted** so output does not depend on `Set` iteration order; translated messages are not printed so results do not depend on locale either. With `Order("Mai", 2)`, there are no violations. `Validator` instances do not independently allocate/close resources; `try-with-resources` ensures the factory created by `main()` is closed.

**Why not use `try (Validator v = ...)`?** `Validator` is not an `AutoCloseable` resource. Only `ValidatorFactory` in this example requires `close()`. Do not close the factory right after `getValidator()` and return the validator to external code: that validator would have an invalid lifecycle.

### 3.3. When custom validator configuration is needed

A factory can build a validator with custom settings without bootstrapping a new factory. The snippet below is **illustrative code placed inside the scope of an open factory** (requires importing `java.time.Clock`):

```java
Validator utcValidator = factory.usingContext()
        .clockProvider(Clock::systemUTC)
        .getValidator();
```

`ClockProvider` is the component allowing temporal constraints like `@Future`/`@Past` to obtain the reference time. `utcValidator` belongs to the same factory and is subject to that factory's close lifecycle. Use `usingContext()` for local differences in clock, interpolator, or other supporting components; if an application-wide configuration is needed, configure it when building the factory (or through Spring).

## 4. How Does Spring Manage `ValidatorFactory` and `Validator`?

In a Spring application with a Jakarta Validation provider on the classpath, Spring can initialize `LocalValidatorFactoryBean`. This class:

1. Bootstraps the provider when Spring initializes the bean (via bean lifecycle and `afterPropertiesSet()`).
2. Acts as an adapter for both `jakarta.validation.ValidatorFactory` and `jakarta.validation.Validator`.
3. Also supports `org.springframework.validation.Validator` and `SmartValidator` to integrate with `DataBinder`, `BindingResult`, `@Valid`, and `@Validated`.
4. Integrates `SpringConstraintValidatorFactory` so custom constraint validators can receive Spring dependency injection.
5. Executes `destroy()`/`close()` when the bean is destroyed, closing the validator factory it owns.

With **Spring Boot 3.x** having `spring-boot-starter-validation` and proper auto-configuration, you usually only need to **inject `jakarta.validation.Validator`**; Boot manages the bean and its lifecycle. Do not create extra `Validation.buildDefaultValidatorFactory()` calls inside services/controllers and do not call `close()` on an injected bean.

Example **service snippet inside a running Spring Boot project** (not a standalone program):

```java
package demo;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import jakarta.validation.constraints.NotBlank;
import org.springframework.stereotype.Service;

import java.util.Set;

@Service
public class RegistrationService {
    private final Validator validator;

    public RegistrationService(Validator validator) {
        this.validator = validator; // owned by the Spring container
    }

    public Set<ConstraintViolation<Registration>> check(Registration item) {
        return validator.validate(item);
    }

    public record Registration(@NotBlank String username) { }
}
```

`RegistrationService` can be used by Spring across multiple requests; the injected validator is thread-safe per contract. The `Registration` object holds request-specific data and **need not and should not** be reused across requests. If you want to return HTTP errors, design a clear `ConstraintViolation` handling layer; calling `validate(...)` only **returns violations** and does not automatically throw HTTP errors.

**Creating a bean in manual Spring Framework configuration:** When no equivalent validator bean exists yet, configure the following so Spring owns the factory:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration
public class ValidationConfiguration {
    @Bean
    public LocalValidatorFactoryBean validator() {
        return new LocalValidatorFactoryBean();
    }
}
```

Spring invokes lifecycle callbacks to initialize and destroy the bean. **In Spring Boot where the validator is already auto-configured, do not add this configuration mechanically**: it may create a second bean or interfere with validator selection. Only define it explicitly when overriding/customizing and after checking existing beans.

### 4.1. Ownership boundary: whoever creates it closes it

| Situation | Owner | How to End |
| --- | --- | --- |
| Java `main` manually calls `Validation.buildDefaultValidatorFactory()` | That application/code itself | `try-with-resources` or call `close()` at shutdown |
| Spring Boot supplies `jakarta.validation.Validator` via DI | Spring application context | Let the context destroy the bean/factory via lifecycle; **never manually close** in a service |
| Custom `@Bean LocalValidatorFactoryBean` configuration | Spring context managing the bean | Spring calls `destroy()`/`close()` on destruction |
| Test creating a separate factory outside Spring | That test or shared fixture | Close in `@AfterAll` or `try-with-resources` matching scope |
| Validator obtained from an already-closed factory | Factory is no longer valid | **Do not keep using it**; create/obtain a validator from a live factory |

If code manually creates a `ValidatorFactory`, passes its `Validator` into a Spring singleton, and immediately closes the factory after startup, the singleton holds a validator whose lifecycle is no longer valid. Conversely, creating an unclosed factory on every API call risks retaining metadata/caches and provider resources until the process exits.

### 4.2. `jakarta.validation.Validator` vs Spring `Validator`

| Jakarta Validation | Spring Validation |
| --- | --- |
| `jakarta.validation.Validator#validate(bean, groups...)` | `org.springframework.validation.Validator#validate(target, Errors)` |
| Returns `Set<ConstraintViolation<T>>` | Records `FieldError`/`ObjectError` into `Errors`/`BindingResult` |
| Used directly when validating DTOs/domains, services, batch jobs | Used in data binding, Spring MVC validation, custom validators |
| No `supports(Class<?>)` | Has `supports(Class<?>)` |
| Typically invoked by the Jakarta provider | Can be bridged by `LocalValidatorFactoryBean` |

When importing `Validator` in Java, specify the package if there is any risk of confusion. `@Valid` on a controller parameter with MVC configuration can trigger Bean Validation when Spring binds and validates data; calling `validator.validate(bean)` directly in a service only returns results unless the code explicitly throws an exception.

## 5. Lifecycle Details of `ConstraintValidator`

For a custom constraint, e.g., `@ValidSku` pointing to `SkuValidator implements ConstraintValidator<ValidSku,String>`, the typical cycle is:

```text
Provider selects constraint descriptor
      │
      ▼
ConstraintValidatorFactory.getInstance(SkuValidator.class)
      │
      ▼
SkuValidator.initialize(annotation)   (if annotation parameters exist)
      │
      ▼
SkuValidator.isValid(value, context)   (may be called many times / across threads)
      │
      ▼
Provider retains or releases per implementation strategy
      │
      ▼
ConstraintValidatorFactory.releaseInstance(instance)
```

The specification requires the provider to release instances supplied by the factory. An instance must be **released by the exact `ConstraintValidatorFactory` that created it**. For instances created in `ValidatorFactory` scope, release may happen when `ValidatorFactory` closes. Therefore, **do not assume a new instance is created per `validate` call**, or that an instance is destroyed immediately after one request.

This impacts custom constraint design:

- `initialize(...)` can load **annotation-level configuration** into fields. That configuration should remain immutable after initialization.
- `isValid(...)` **must be thread-safe** per Jakarta Validation. Do not store "value currently being validated", "current request", or "previous call result" in mutable instance fields that concurrent threads might write.
- Use local variables for per-validation state. Dependencies injected into constraint validators (e.g., lookup repositories/services) must also meet appropriate lifecycle and thread-safety requirements.
- A custom `ConstraintValidatorFactory` **should not arbitrarily cache instances**: the provider may initialize/configure validators via `initialize`; improper caching can leak state from one constraint into another.
- In Spring integration, `SpringConstraintValidatorFactory` instantiates objects via `AutowireCapableBeanFactory` and releases them per contract. Avoid manually creating instances with `new` while expecting Spring to manage/inject dependencies for them.
- Do not confuse `ConstraintValidator` cleanup with `ValidatorFactory` cleanup. The provider decides when to call `releaseInstance`; **the factory owner** decides when to call `close()`.

Illustrative **custom constraint implementation snippet** (`ValidSku` annotation is assumed defined separately; not a standalone program):

```java
public final class SkuValidator
        implements ConstraintValidator<ValidSku, String> {

    private String prefix;

    @Override
    public void initialize(ValidSku rule) {
        this.prefix = rule.prefix(); // fixed configuration for this instance
    }

    @Override
    public boolean isValid(String sku,
                           ConstraintValidatorContext context) {
        return sku == null || sku.startsWith(prefix);
        // sku is a per-call argument, not stored in a field.
    }
}
```

How `null` is handled is a choice per the constraint's contract: many constraints treat `null` as valid and pair with `@NotNull` if the field is required, as in the example above. Do not use a field counter incremented on each request inside `isValid` unless synchronization is designed for a clear reason.

## 6. Thread Safety and Performance Cost

### 6.1. What the API guarantees

- `ValidatorFactory` implementations must be thread-safe.
- `Validator` implementations must be thread-safe.
- `ConstraintValidator#isValid(...)` implementations must be thread-safe.
- Providers may share/cache metadata, `Validator`s, and certain `ConstraintValidator`s. **Do not rely on instance identity or constructor call counts** as business logic.
- Obtaining a `Validator` from a factory is normally cheaper than bootstrapping a new factory. Reusing a factory avoids repeatedly initializing metadata/configuration.

### 6.2. What must **not** be inferred from thread safety

- `@NotNull` on an object does not make the validated object thread-safe. Concurrent requests must still use separate DTOs or state.
- A `ConstraintValidator` with mutable fields modified during `isValid` can cause data races, even though the overlying `Validator` is thread-safe.
- The returned `Set<ConstraintViolation<T>>` belongs to each invocation; do not share and mutate results across requests as shared state.
- Using the same `Validator` does not mean every underlying collaborator is thread-safe; custom providers, message interpolators, resolvers, and collaborators must uphold their respective contracts.
- Not every annotation is checked automatically everywhere: an object must pass through a trigger mechanism, such as calling `validate(...)`, Spring MVC `@Valid`, or configured method validation.

**Example performance/cleanup bug:** Creating a new factory via `buildDefaultValidatorFactory()` on every request in a controller, calling validate, and forgetting to close it. This can create many unnecessary factories/caches and make lifecycle management difficult. Fix it by injecting a Spring-managed `Validator` or using one application-owned factory closed on shutdown.

## 7. When Does Validation Happen in Spring?

A `Validator` does not passively watch every setter or every object instantiation. Validation occurs at **trigger points**:

1. **Manual call** `validator.validate(obj)`: returns a `Set<ConstraintViolation>`; the caller decides how to handle errors.
2. **Spring MVC data binding + `@Valid` / `@Validated`**: MVC validates arguments per configuration; for suitable controller methods, binding/validation errors can be routed to `BindingResult` or handled as Spring exceptions.
3. **Method validation in services**: when method validation is configured and the bean is properly proxied/intercepted (typically using `@Validated` on the class in Spring Boot 3.x), parameter/return value constraints can be checked. **Self-invocation** within the same object normally bypasses the proxy.
4. **Batch/job/tests**: calling the validator directly in code, without HTTP or Spring MVC.

Having `@Valid` in a DTO **does not mean** calling `new MyDto(...)` automatically runs validation. `@Valid` primarily marks *cascaded validation* or a check point when requested by an integration framework; a trigger is still required.

## 8. Common Mistakes and Fixes

| Mistake | Consequence | Correct Approach |
| --- | --- | --- |
| `Validation.buildDefaultValidatorFactory()` per request | Expensive bootstrap and risk of retaining resources longer than needed | Bootstrap once per owner lifecycle, or inject Spring-managed validator |
| Not calling `close()` on a self-created factory | Provider resources/caches are not intentionally released | `try-with-resources` or shutdown cleanup |
| Closing a Spring/container-provided factory inside a service | Other components holding the validator can be affected | Only the container closes factories it manages |
| Keeping a `Validator` after the factory closes | Out-of-lifecycle usage, behavior not guaranteed | Keep the factory alive throughout usage |
| Calling `validator.close()` | `Validator` API has no such method | Close `ValidatorFactory` when needed |
| Instantiating `ConstraintValidator` with `new` expecting Spring DI | Instance bypasses Spring's factory | Use the provider and Spring's `ConstraintValidatorFactory` |
| `isValid` mutates per-request state fields | Race conditions or wrong results under concurrency | Use local variables, immutable config, thread-safe collaborators |
| Custom `ConstraintValidatorFactory` caches every instance | State from `initialize` can be misused | Follow get/release and let the provider manage caching |
| Confusing the two `Validator` classes | Wrong API and error-handling model | Check package `jakarta.validation` vs `org.springframework.validation` |
| Thinking `@Valid` runs automatically on constructor calls | No trigger, errors are silently skipped | Call `validate` or use boundary integration |
| Using `javax.validation.*` with Spring Boot 3.x | Mixing Jakarta API with legacy library | Use `jakarta.validation.*` and a compatible provider |
| Relying on `Set<ConstraintViolation>` order for standard output | Returned order is not a stable contract | Sort by property/violation before printing or comparing |

## 9. Application Review Checklist

**Initialization and ownership**

- [ ] Is a real provider on the classpath (e.g., `spring-boot-starter-validation`) rather than only the annotation API?
- [ ] Is the factory bootstrapped per application/fixture lifecycle, not on the hot path of every request?
- [ ] Are the factory owner and `close()` timing clearly defined?
- [ ] Are self-created factories kept distinct from Spring-managed factories/validators?

**Usage and concurrency**

- [ ] Is `Validator` reused appropriately without trying to close it individually?
- [ ] Is no validator used after its parent factory has closed?
- [ ] Is custom `ConstraintValidator#isValid` safe under concurrent calls?
- [ ] Does any custom `ConstraintValidatorFactory` respect the create/release contract?

**Behavior and testing**

- [ ] Are validation triggers present at HTTP/service/batch/test boundaries where needed?
- [ ] Are both valid and invalid DTOs tested, including expected violations?
- [ ] Are there lifecycle tests for application-owned factories, at least verifying cleanup runs on stop or failure?
- [ ] Do assertions avoid depending on `Set` order, localized messages, or how many times the provider instantiates `ConstraintValidator`?

## 10. Design Summary

`ValidatorFactory` is **a configuration and initialization resource** with a bounded lifecycle. `Validator` is **the API used for validation**, lightweight and thread-safe to share per contract; it has no `close()` method of its own. `ConstraintValidatorFactory` manages constraint logic instances as requested by the provider. In Spring, `LocalValidatorFactoryBean` connects these APIs to dependency injection and the application context lifecycle. Let the party that **creates/owns the factory** be responsible for closing it, and keep validators alive strictly while their factory remains active.

### Official References

- [Jakarta Bean Validation 3.0 Specification — ValidatorFactory, Validator, and ConstraintValidatorFactory](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Jakarta Validation 3.1 Specification — Bootstrap, lifecycle, and thread safety](https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html)
- [Jakarta ValidatorFactory API — AutoCloseable and close()](https://jakarta.ee/specifications/platform/10/apidocs/jakarta/validation/validatorfactory)
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Boot — Validation](https://docs.spring.io/spring-boot/reference/io/validation.html)
