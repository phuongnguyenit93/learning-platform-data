# Dependency Injection via SpringConstraintValidatorFactory

When writing a **custom constraint** with Jakarta Validation in Spring Framework, the `ConstraintValidator` class sometimes needs a Spring-managed component: a service, repository, configuration, clock, or business policy. For example, a validator checking whether a customer code exists in an allowed catalog. If the Jakarta Validation provider instantiates the validator via its default mechanism, Spring dependencies may not be injected and the validator fails at runtime.

`SpringConstraintValidatorFactory` bridges this integration point: it is a `jakarta.validation.ConstraintValidatorFactory` implementation using Spring's `AutowireCapableBeanFactory` to **create and prepare `ConstraintValidator` instances** when requested by the Jakarta Validation provider. Thus constructor injection, `@Autowired`, and dependency injection mechanisms can work inside custom validators.

It is important to distinguish:

- `@Constraint` and `ConstraintValidator` define **what to validate**.
- `SpringConstraintValidatorFactory` determines **how the validator is instantiated and receives dependencies**.
- `LocalValidatorFactoryBean` connects the **Spring Validation API** to the **Jakarta Validation provider** and can use Spring's factory.
- `@Valid`, `@Validated`, or `Validator.validate(...)` calls determine **when validation is triggered**.

The factory does not invent validation rules, does not scan HTTP requests on its own, and does not invoke `isValid` automatically whenever a Java value changes.

## 1. Why does a custom validator need dependency injection?

Consider a constraint checking whether a document code belongs to an allowed business catalog. There are two distinct responsibilities:

1. `AllowedCodeCatalog` holds/selects the catalog policy managed by Spring.
2. `RegisteredCodeValidator` applies that policy to each value being validated.

The validator simply asks `catalog.contains(code)`. Thanks to dependency injection, the policy can evolve into a bean reading configuration, a cache, or a repository without changing the constraint's API. This example uses an in-memory catalog to illustrate the mechanism clearly without requiring a database.

**Common mistake:** assuming that merely adding `@Autowired` to a `ConstraintValidator` guarantees the Jakarta Validation provider will inject the bean. That only holds when the validator instantiation path uses a Spring-compatible `ConstraintValidatorFactory`. If code directly calls `Validation.buildDefaultValidatorFactory()` with default settings, the provider does not automatically know about Spring's `ApplicationContext`.

## 2. The path of a validation call

~~~text
Validator.validate(bean)
         |
         v
Spring LocalValidatorFactoryBean
         |
         v
Jakarta Validation provider (e.g. Hibernate Validator)
         |
         | locates constraint descriptor
         | requests ConstraintValidator instance
         v
ConstraintValidatorFactory.getInstance(RegisteredCodeValidator.class)
         |
         v
SpringConstraintValidatorFactory
         |
         v
AutowireCapableBeanFactory.createBean(RegisteredCodeValidator.class)
         |
         | constructor injection / Spring BeanPostProcessors
         v
RegisteredCodeValidator(AllowedCodeCatalog)
         |
         | provider calls initialize(...) when needed
         | provider calls isValid(value, context)
         v
ConstraintViolation (if invalid)
~~~

When the instance is no longer needed, the provider may call `ConstraintValidatorFactory.releaseInstance(...)` to hand lifecycle control back to the factory. In Spring's implementation, `SpringConstraintValidatorFactory` uses the bean factory to instantiate and perform bean destruction on release. **Do not assume every `validate` call creates a new validator**: the provider may cache and reuse instances after initialization.

| Component | API/package | Role |
|---|---|---|
| `ConstraintValidator<A, T>` | `jakarta.validation` | Validation logic for annotation `A` against type `T` |
| `ConstraintValidatorFactory` | `jakarta.validation` | Contract for creating and releasing validator instances |
| `SpringConstraintValidatorFactory` | `org.springframework.validation.beanvalidation` | Factory using Spring to create/autowire validators |
| `AutowireCapableBeanFactory` | `org.springframework.beans.factory.config` | Creates instances, injects dependencies, and runs bean post-processors |
| `LocalValidatorFactoryBean` | `org.springframework.validation.beanvalidation` | Spring/Jakarta `Validator` bean, configures and bootstraps the provider |
| `Validator` | `jakarta.validation` | API calling `validate(...)`, `validateProperty(...)`, `validateValue(...)` |

In Spring Boot with the validation starter and a compatible provider, auto-configuration normally creates a `LocalValidatorFactoryBean` enabling custom validators to be autowired. In non-Boot Spring Framework applications, the app can declare `LocalValidatorFactoryBean` as a bean; when managed by Spring, it uses an appropriate `SpringConstraintValidatorFactory` by default unless overridden by another factory.

## 3. Runnable example: validating codes with a Spring service

The example uses **Java 17+**, Spring Boot 3.x, and the `jakarta.validation` namespace. All Java files sit in package `com.example.validation`. The application uses constructor injection, so `RegisteredCodeValidator` cannot be instantiated with a no-arg constructor alone.

### 3.1. Dependency in Gradle

In a Spring Boot project with the Spring Boot Gradle plugin and dependency management, add:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

The starter provides the Jakarta Validation API, provider implementation, and Boot auto-configuration integration. The `./gradlew bootRun` command at the end of this section assumes the project has a Gradle wrapper, the Spring Boot plugin, and the main class shown below; **you cannot simply run `javac` on standalone files because they depend on Spring/Jakarta libraries**.

If creating a new project, choose Spring Boot 3.x, Java 17+, Gradle build tool, and the **Validation** dependency. In Spring Boot 2.x, the standard Bean Validation package is `javax.validation`; do not mix `javax.validation.*` code from Boot 2 with `jakarta.validation.*` in Boot 3/Spring 6.

### 3.2. Policy provider bean — `AllowedCodeCatalog.java`

~~~java
package com.example.validation;

import java.util.Set;
import org.springframework.stereotype.Service;

@Service
public class AllowedCodeCatalog {

    private final Set<String> allowed = Set.of("SPR-01", "SPR-02");

    public boolean contains(String code) {
        return allowed.contains(code);
    }
}
~~~

`@Service` registers the bean for Spring to manage and inject into other components. The catalog is immutable, so concurrent validation reads are safe; in a real application, it can be replaced by a cache/repository adapter with an appropriate latency strategy.

### 3.3. Constraint definition — `RegisteredCode.java`

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
@Constraint(validatedBy = RegisteredCodeValidator.class)
@Target({
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.PARAMETER,
    ElementType.ANNOTATION_TYPE,
    ElementType.TYPE_USE
})
@Retention(RetentionPolicy.RUNTIME)
public @interface RegisteredCode {

    String message() default "Code is not in the allowed catalog";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
~~~

`@Constraint(validatedBy = ...)` points to the validator implementing the logic. `message`, `groups`, and `payload` are the standard elements of a custom constraint. `RUNTIME` is required for the provider to read the annotation at runtime; `@Target` permits usage at the appropriate sites, though it does not replace validation triggers.

### 3.4. Validator receiving the bean via constructor — `RegisteredCodeValidator.java`

~~~java
package com.example.validation;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public final class RegisteredCodeValidator
        implements ConstraintValidator<RegisteredCode, String> {

    private final AllowedCodeCatalog catalog;

    public RegisteredCodeValidator(AllowedCodeCatalog catalog) {
        this.catalog = catalog;
    }

    @Override
    public boolean isValid(
            String value,
            ConstraintValidatorContext context) {
        return value == null || catalog.contains(value);
    }
}
~~~

Here is the key point: `RegisteredCodeValidator` **does not declare `@Component`**, yet its constructor can still receive `AllowedCodeCatalog` because `SpringConstraintValidatorFactory` creates it via Spring's bean factory. Injecting a single constructor does not strictly require `@Autowired` in modern Spring configurations; you may add `@Autowired` explicitly to emphasize intent if your codebase requires it.

The `isValid` method returns `true` for `null` to separate checking **whether it is in the catalog** from requiring **a value to be present**. If data must not be `null`, add `@NotNull` to the property. Do not call `new RegisteredCodeValidator(...)` from application code to run validation manually: call Jakarta `Validator` and let the provider manage metadata, groups, lifecycle, and error lists.

### 3.5. Bean to validate — `DocumentRequest.java`

~~~java
package com.example.validation;

import jakarta.validation.constraints.NotNull;

public final class DocumentRequest {

    @NotNull
    @RegisteredCode
    private final String code;

    public DocumentRequest(String code) {
        this.code = code;
    }

    public String getCode() {
        return code;
    }
}
~~~

`@NotNull` and `@RegisteredCode` have different responsibilities. A `null` code violates only `@NotNull` since the custom validator allows `null`; `"BAD-01"` is non-null yet absent from the catalog, so it violates `@RegisteredCode`.

### 3.6. Invoking validation in Spring Boot — `DemoApplication.java`

~~~java
package com.example.validation;

import jakarta.validation.Validator;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication implements CommandLineRunner {

    private final Validator validator;

    public DemoApplication(Validator validator) {
        this.validator = validator;
    }

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Override
    public void run(String... args) {
        System.out.println(
            "BAD-01: " + validator.validate(
                new DocumentRequest("BAD-01")).size());

        System.out.println(
            "SPR-01: " + validator.validate(
                new DocumentRequest("SPR-01")).size());

        System.out.println(
            "null: " + validator.validate(
                new DocumentRequest(null)).size());
    }
}
~~~

From a valid Gradle project directory, run:

~~~bash
./gradlew bootRun
~~~

On Windows use `gradlew.bat bootRun`. The console will show Spring Boot startup logs; the **three lines printed by the program** are:

~~~text
BAD-01: 1
SPR-01: 0
null: 1
~~~

Exact explanation:

- `BAD-01` is not in `AllowedCodeCatalog`, resulting in one violation from `@RegisteredCode`.
- `SPR-01` is in the catalog and non-null, so zero violations.
- `null` is allowed by `RegisteredCodeValidator`, yet `@NotNull` produces one violation.
- Without a Spring-aware validator creation mechanism, the `RegisteredCodeValidator(AllowedCodeCatalog)` constructor cannot be instantiated by the default provider as in the example; errors usually surface when validation runs.

The output only counts violations; do not rely on `ConstraintViolation` ordering since the API guarantees no stable order. With a specific provider, error messages or configuration exception types may vary.

## 4. Configuring `LocalValidatorFactoryBean` and the factory

### 4.1. Common case: Spring Boot auto-configuration

With Spring Boot 3.x, when a validation provider and the validation starter are present, the application normally has a pre-configured `LocalValidatorFactoryBean`. When injecting `jakarta.validation.Validator` into a service/controller, you receive the integration wired to Spring's bean factory. **In that case, you do not need to manually wire `SpringConstraintValidatorFactory` inside each validator.**

Application initialization flow:

1. Spring creates the `ApplicationContext`, beans like `AllowedCodeCatalog`, and the bean providing Jakarta `Validator`.
2. `LocalValidatorFactoryBean` bootstraps the Jakarta Validation provider and configures the constraint validator factory.
3. When `Validator.validate(...)` encounters `@RegisteredCode`, the provider requests an instance from the factory.
4. Spring instantiates `RegisteredCodeValidator` and injects `AllowedCodeCatalog`.
5. The provider calls `isValid(...)` and returns the `ConstraintViolation` set.

Whether Spring Boot creates the default bean depends on auto-configuration conditions and any beans you declared yourself. If the application supplies a custom `Validator` or custom factory, inspect the **effective active configuration** rather than assuming Boot's default is always in use.

### 4.2. Plain Spring Framework or declaring the factory explicitly

In a Spring application without Boot, you can register `LocalValidatorFactoryBean`:

~~~java
package com.example.validation;

import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;
import org.springframework.validation.beanvalidation.SpringConstraintValidatorFactory;

@Configuration
@ComponentScan("com.example.validation")
public class ValidationConfiguration {

    @Bean
    public LocalValidatorFactoryBean validator(
            ApplicationContext applicationContext) {

        LocalValidatorFactoryBean result =
            new LocalValidatorFactoryBean();

        result.setConstraintValidatorFactory(
            new SpringConstraintValidatorFactory(
                applicationContext.getAutowireCapableBeanFactory()));

        return result;
    }
}
~~~

This snippet is an **alternative/standalone configuration** to illustrate explicit wiring; do not copy it into the Boot example above if Boot already creates a suitable validator. The bean name and return type let Spring provide `Validator` wherever injected. `LocalValidatorFactoryBean` is initialized via the Spring lifecycle; there is no need to call its `afterPropertiesSet()` or `close()` manually.

In modern Spring Framework, when `LocalValidatorFactoryBean` is managed by Spring and no custom factory is set, it usually chooses `SpringConstraintValidatorFactory` automatically using the application context's bean factory. Therefore calling `setConstraintValidatorFactory(...)` above is a way to **make the mechanism explicit**, not a mandatory step in every application.

### 4.3. Bootstrapping Jakarta Validation manually when genuinely needed

If you need to use Jakarta Validation's bootstrap API directly inside a component that already has an `ApplicationContext`, wire the factory explicitly to retain dependency injection:

~~~java
import jakarta.validation.Validation;
import org.springframework.context.ApplicationContext;
import org.springframework.validation.beanvalidation.SpringConstraintValidatorFactory;

// applicationContext is the active Spring context.
try (var factory = Validation.byDefaultProvider()
        .configure()
        .constraintValidatorFactory(
            new SpringConstraintValidatorFactory(
                applicationContext.getAutowireCapableBeanFactory()))
        .buildValidatorFactory()) {

    var validator = factory.getValidator();
    var violations = validator.validate(
        new DocumentRequest("BAD-01"));
    System.out.println(violations.size()); // 1
}
~~~

This snippet illustrates usage **within a context that already has `applicationContext`**; it is not a standalone Java class. Because `ValidatorFactory` is created manually, the creator must close it to release resources. Do not open and close a new factory on every request: provider bootstrapping is relatively expensive, and applications should reuse the container-managed validator factory.

An easily misleading call:

~~~java
var factory = jakarta.validation.Validation
    .buildDefaultValidatorFactory();
~~~

Without configuring a Spring-compatible constraint validator factory, this call uses the provider's default bootstrap. It does not look up Spring beans by class name and may fail initialization when a custom validator only has a constructor requiring dependencies. Annotating the validator class with `@Component` also does **not** make that default bootstrap Spring-aware.

## 5. Lifecycle details: creation, injection, initialize, reuse, release

`ConstraintValidatorFactory` has two main contracts:

~~~java
<T extends jakarta.validation.ConstraintValidator<?, ?>> T
    getInstance(Class<T> key);

void releaseInstance(
    jakarta.validation.ConstraintValidator<?, ?> instance);
~~~

The declaration above expresses **logical signatures** in the interface, not a standalone runnable class. With `SpringConstraintValidatorFactory`:

- `getInstance(Class<T>)` uses Spring's bean factory to create an instance of `T` and apply dependency injection / corresponding post-processors.
- The Jakarta Validation provider manages calls to `ConstraintValidator.initialize(annotation)` and `isValid(value, context)`.
- `releaseInstance(...)` is called according to the provider's lifecycle; Spring's factory delegates release to the bean factory to run corresponding destruction callbacks.

What to avoid is writing a validator with **mutable state varying per validated value**:

~~~java
// Anti-pattern: unsafe when one instance is used for multiple validations.
private String lastValidatedCode;

@Override
public boolean isValid(
        String value,
        ConstraintValidatorContext context) {
    lastValidatedCode = value; // unnecessary shared state
    return value == null || catalog.contains(value);
}
~~~

The provider may cache/retain instances per constraint descriptor and reuse them across multiple validations, including from multiple threads. Keeping the validator **free of mutable per-call state** is the right choice. `final` fields referencing dependencies or immutable configuration are fine; if `initialize(...)` reads annotation parameters and stores a fixed configuration like a `Pattern`, ensure it remains immutable after initialization.

**Do not manually define a singleton `ConstraintValidator` `@Bean` assuming the provider will use that exact bean.** `SpringConstraintValidatorFactory` creates validators via `AutowireCapableBeanFactory` upon provider request; the resulting instance is not necessarily an existing `@Component` singleton in the container. To use Spring beans inside a validator, inject **collaborating beans** such as `AllowedCodeCatalog`.

### `@Autowired` field injection vs constructor injection

Both can work through Spring's factory:

~~~java
public class AnotherCodeValidator
        implements ConstraintValidator<RegisteredCode, String> {

    @org.springframework.beans.factory.annotation.Autowired
    private AllowedCodeCatalog catalog;

    @Override
    public boolean isValid(
            String value,
            ConstraintValidatorContext context) {
        return value == null || catalog.contains(value);
    }
}
~~~

The snippet above illustrates an **alternative variant** of the validator, not used alongside `RegisteredCodeValidator` in `@Constraint`. Constructor injection is usually clearer: dependencies are explicit/required, fields can be `final`, testing is straightforward, and it avoids the illusion that fields are always ready even when someone instantiates the object with `new`.

## 6. Where is validation triggered in Spring?

Dependency injection only solves **validator instantiation**. For `isValid(...)` to run, there must be a Bean Validation invocation point.

| Trigger point | Example | Key condition |
|---|---|---|
| Programmatic Bean Validation | `jakarta.validation.Validator.validate(bean)` | Properly configured Jakarta Validator/provider available |
| Spring MVC DTO | `@Valid @RequestBody CreateDocumentForm form` | Spring MVC + JSON binding and validator integration present |
| Spring MVC form binding | `@Valid @ModelAttribute CreateDocumentForm form` | Data bound into object and validation requested |
| Service method | `@Validated` bean with constraints on parameters/return values | Method-validation interception configured and calls go through Spring proxy |
| Container element | `List<@RegisteredCode String>` | Annotation allows `TYPE_USE` and provider supports value extractors |

Controller example **illustrating only the trigger point**, additionally requiring Spring MVC/web starter and a JSON-bindable DTO:

~~~java
@PostMapping("/documents")
public void submit(@Valid @RequestBody CreateDocumentForm form) {
    documentService.submit(form.getCode());
}
~~~

Here `@Valid` triggers DTO validation after data binding; the custom validator is instantiated via the configured factory. `@Valid` is not how services are injected; the Spring factory handles that job.

For a business service:

~~~java
@Service
@Validated
public class DocumentService {

    public void submit(@RegisteredCode String code) {
        // Process business logic after input is valid.
    }
}
~~~

This is also a mechanism illustration, not part of the standalone demo project above. With AOP-style method validation, Spring must have an active method-validation interceptor (such as `MethodValidationPostProcessor` in an appropriate setup) and calls must pass through the Spring proxy. Internal calls like `this.submit(...)` can bypass interception. Newer Spring MVC versions also have direct method validation mechanisms for controllers: distinguish that mechanism from service AOP method validation when diagnosing missing errors.

**Successful data binding does not mean validation succeeded**, and conversely HTTP type-conversion errors can occur before any `ConstraintValidator` is ever called. For controllers, verify both binding and error-handling configuration, not just constructor injection.

## 7. Testing to prove dependency injection works

A unit test doing `new RegisteredCodeValidator(new AllowedCodeCatalog())` tests the logic but **does not prove `SpringConstraintValidatorFactory` is being used**. To verify the real wiring, obtain `jakarta.validation.Validator` from the Spring context and validate an annotated bean.

With Spring Boot and `spring-boot-starter-test`, you can use an integration test:

~~~java
package com.example.validation;

import jakarta.validation.Validator;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class RegisteredCodeIntegrationTest {

    @Autowired
    private Validator validator;

    @Test
    void usesSpringManagedCodeCatalog() {
        assertEquals(0, validator.validate(
            new DocumentRequest("SPR-02")).size());
        assertEquals(1, validator.validate(
            new DocumentRequest("UNKNOWN")).size());
        assertEquals(1, validator.validate(
            new DocumentRequest(null)).size());
    }
}
~~~

This test lives at `src/test/java/com/example/validation/RegisteredCodeIntegrationTest.java`. Add the test dependency to the Boot project:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Run `./gradlew test` (or `gradlew.bat test` on Windows). Expected result: the test **PASSES** if the Spring context, provider, and factory are wired together. Because the validator has **only a constructor requiring `AllowedCodeCatalog`**, a provider without a Spring-aware factory typically cannot instantiate it to complete the test.

If you only want to unit-test logic, you can call `isValid` directly with a fake/stub `AllowedCodeCatalog`, though that kind of test does not verify `@Constraint` metadata, `initialize`, group selection, service injection, or factory lifecycle.

## 8. Common errors and diagnostics

| Symptom | Cause to check | How to fix |
|---|---|---|
| `@Autowired` in validator is `null` or constructor injection fails | Provider uses a non-Spring factory, or validator was instantiated with `new` outside context | Check the active `Validator`/`LocalValidatorFactoryBean`, provider bootstrap, and `SpringConstraintValidatorFactory` |
| Message like "unable to instantiate ConstraintValidator" | Provider failed to create validator, often due to parameterized constructor unsupported by default factory | Ensure the Spring factory is configured and dependency beans exist |
| `NoSuchBeanDefinitionException` / `UnsatisfiedDependencyException` | `AllowedCodeCatalog` is not a bean, component scan misses the package, or multiple beans are ambiguous | Check `@Service`, package scanning, and `@Qualifier`/`@Primary` if needed |
| Validator works when called directly yet does not run on DTO | `Validator.validate` was never called or `@Valid` is missing at the trigger point | Inspect controller/service flow and validator integration |
| Calling `Validation.buildDefaultValidatorFactory()` loses injection | Uses the Jakarta Validation provider's default factory | Inject Spring-managed validator or configure an explicit `ConstraintValidatorFactory` |
| Using `javax.validation.*` in a Boot 3 app | Namespace mismatch with Spring 6/Boot 3 Jakarta | Standardize on `jakarta.validation.*` across API, annotations, and provider |
| Validator invoked multiple times or exhibits stale state | Provider caches/reuses instances; code stores per-request mutable state | Keep `isValid` stateless and process all data via method parameters |
| Internal service method call skips method constraints | Self-invocation bypasses Spring AOP proxy in AOP method validation mode | Invoke through a valid bean/proxy and confirm method validation is configured |
| Field constraint has mismatched type | Validator only implements `ConstraintValidator<RegisteredCode, String>` yet is used on another type | Add a validator for the other type or restrict placement |
| Expecting validation on `null` yet no error occurs | Validator returns `true` for `null` | Combine with `@NotNull` or `@NotBlank` per intended semantics |
| Bootstrapping validator factory on every request | Wastes resources and complicates lifecycle/dependency management | Reuse the Spring-provided `LocalValidatorFactoryBean`/`Validator` |

When debugging, follow the order: **annotation present at runtime → provider present → validation trigger point present → which factory the provider uses → Spring has the dependency bean → `isValid` logic is correct**. This order usually finds the root cause faster than blindly adding `@Component` to the validator class.

## 9. Production design considerations

**Keep validation predictable.** `isValid` should return results based on current data and policy, avoiding database writes, message publishing, or mutating business state. If a dependency calls a network/database, account for latency, retries, timeouts, transient failures, and load when validating large collections. A constraint applied repeatedly can trigger multiple calls to the dependency.

**Do not store request state in validator fields.** The provider controls instance caching and lifecycle, and a single validator instance may process many values. A singleton dependency can be injected into a validator instance without implying the validator itself has request scope.

**Separate requiredness from business rules.** `@NotNull`, `@NotBlank`, or standard constraints handle simple checks; `@RegisteredCode` checks the catalog. If a policy depends on the current user, reconsider where validation belongs: constraints need clear rules and should not implicitly depend on hard-to-test request state.

**Do not rely on constraint or validator invocation order.** A bean may carry many constraints. Across configurations, groups, and providers, violation order is not a stable contract. Never write logic whose correctness depends on "constraint A runs before B".

**Control custom configurations.** If replacing `LocalValidatorFactoryBean` with a custom bean or factory, verify which parts of the application actually use that instance. Multiple `Validator`s in the context can cause controllers, services, and manual callers to receive different configurations.

## 10. Knowledge self-check

1. Why can a `ConstraintValidator` with a constructor dependency run in Spring Boot yet fail when instantiated by the default Jakarta provider? — Because `SpringConstraintValidatorFactory` uses Spring to create/autowire instances, whereas the default factory does not automatically know about dependencies in `ApplicationContext`.
2. Is it necessary to annotate every `ConstraintValidator` class with `@Component`? — No. Spring's factory can instantiate and autowire the validator class directly; collaborating beans like `AllowedCodeCatalog` must be Spring-managed.
3. Does `SpringConstraintValidatorFactory` call `isValid` itself? — No. The Jakarta Validation provider manages calling `initialize`/`isValid` after obtaining the instance from the factory.
4. Why did the demo report an error on `null` even though `RegisteredCodeValidator.isValid(null, ...)` returns `true`? — Because `@NotNull` is an independent constraint.
5. Why should `lastValidatedValue` not be stored on a field of `ConstraintValidator`? — The instance may be cached and reused by the provider across multiple validations and threads.
6. When configuring plain Spring Framework without Boot, which component connects everything? — Register `LocalValidatorFactoryBean` in the Spring context and, if configuring explicitly, pass `SpringConstraintValidatorFactory(applicationContext.getAutowireCapableBeanFactory())`.
7. If a controller binds a DTO yet reports no constraint errors, what should you check? — Check the `@Valid`/`@Validated` or `Validator.validate` trigger point, the provider, the factory, and error handling; dependency injection is only one piece.

**Takeaway:** `SpringConstraintValidatorFactory` is the bridge **Jakarta Validation provider → Spring BeanFactory** for instantiating custom `ConstraintValidator`s with Spring dependencies. `LocalValidatorFactoryBean` is usually the integration configuration point; validation calls or trigger annotations are what actually make the logic run.

## References

- [Spring Framework Reference — Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring API — SpringConstraintValidatorFactory](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/beanvalidation/SpringConstraintValidatorFactory.html)
- [Spring API — LocalValidatorFactoryBean](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html)
- [Spring API — AutowireCapableBeanFactory](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/config/AutowireCapableBeanFactory.html)
- [Jakarta Validation API — ConstraintValidatorFactory](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraintvalidatorfactory)
- [Jakarta Validation API — ConstraintValidator](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraintvalidator)
