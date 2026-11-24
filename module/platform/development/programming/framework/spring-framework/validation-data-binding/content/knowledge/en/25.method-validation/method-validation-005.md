# How AOP Proxies Trigger Method Validation in Spring Framework

In Spring, Jakarta Validation annotations such as `@NotBlank`, `@Min`, and `@Valid` can appear on **method parameters or return values**. However, Java does not automatically validate a method call just because annotations appear in source code. For an ordinary Spring bean (especially in the service layer), Spring can trigger **method validation** using an **AOP proxy**: an intermediary object that intercepts the call, asks Jakarta Validation to check the parameters, invokes the real method if valid, and then validates the return value.

The goal of this lesson is to understand **why a method is validated**, the conditions required for the mechanism to work, which calls it **cannot intercept**, and how to diagnose a constraint that is declared but never runs.

In these examples, we use Spring Framework 6.x / Spring Boot 3.x, Java 17+, and annotations from the `jakarta.validation.*` package. Spring Framework 6.1+ also includes **built-in method validation directly inside Spring MVC**, which must be clearly distinguished from service methods proxied by AOP.

## 1. Distinguishing Bean Validation, Method Validation, and AOP Proxies

| Concept | What is validated | Trigger point |
|---|---|---|
| Standard Bean Validation | Fields/properties of an object and class-level constraints | `jakarta.validation.Validator.validate(object)` or Spring invoking the validator for a DTO |
| Method validation | Constraints on **parameters**, **return values**, cross-parameter rules, and objects cascaded via `@Valid` | `ExecutableValidator`, Spring AOP, or MVC's built-in method validation mechanism |
| AOP proxy | **Method calls passing through a bean proxy** | Framework creates a proxy/advisor and runs interceptors around method calls |
| Data binding | Converts requests/strings/forms into Java objects and matching types | Spring MVC `WebDataBinder`, argument resolvers |

Three similar-looking names with distinct roles:

- `@Validated` is a Spring annotation (`org.springframework.validation.annotation.Validated`). In **AOP-based method validation**, placing it on a **Spring bean class** lets the default mechanism recognize the bean to intercept; this annotation also selects validation groups.
- `@Valid` is a Jakarta Validation annotation (`jakarta.validation.Valid`). It instructs the validator to **cascade** into properties of the annotated object; by itself it is not a constraint like `@NotBlank` or `@NotNull`.
- `@NotBlank`, `@Size`, `@Min`, `@NotNull`, etc. are the actual constraints evaluated by the Jakarta Validation provider when validation is invoked.

For example, given:

~~~java
@Service
@Validated
public class AccountService {
    public void register(@NotBlank String accountCode) {
        // business logic
    }
}
~~~

Spring must have a method-validation post-processor bean and a Jakarta Validation provider; callers must use the **Spring-managed proxy** of `AccountService`. Calling `new AccountService().register("")` does not automatically trigger method validation.

## 2. Execution Flow: From `@Validated` to `ExecutableValidator`

Two notable Spring components:

1. `MethodValidationPostProcessor` — a BeanPostProcessor that registers an advisor for target beans annotated with `@Validated`; Spring can return a proxy instead of the raw target object.
2. `MethodValidationInterceptor` — an **around-interception** AOP advice that uses Jakarta Validation's `ExecutableValidator` to validate parameters and return values.

Typical flow for a synchronous method:

~~~text
Client / Controller / another Spring bean
                   |
                   | calls service.execute(argument)
                   v
         Spring AOP proxy of service
                   |
                   v
         MethodValidationInterceptor
                   |
                   | 1. validateParameters(...)
                   |    If violations exist: throw exception
                   |    Do not run method body
                   |
                   v
          invocation.proceed()
                   |
                   v
         Real method on target
                   |
                   | produces/returns result
                   v
         MethodValidationInterceptor
                   |
                   | 2. validateReturnValue(...)
                   |    If violations exist: throw exception
                   v
           Client receives result
~~~

`ExecutableValidator` is the **standard Jakarta Validation API**, obtained via `Validator.forExecutables()`. The Spring interceptor delegates to a provider such as Hibernate Validator to evaluate constraints rather than re-implementing `@NotBlank` or `@Size` algorithms itself.

Important details:

- **Invalid parameters**: the interceptor can throw an exception **before** business logic runs.
- **Invalid return value**: the method body **has already run**; the interceptor detects the error afterward and prevents returning the invalid result to the caller. Side effects that occurred inside the method are not automatically undone. If a transaction is active, whether it rolls back depends on transaction configuration and advisor ordering.
- **Method throws a business exception**: this is not a normal return value for return-value constraint validation.
- **Call does not go through the proxy**: the interceptor never gets a chance to run, even though the annotations still exist.
- **Other advisors** such as transaction, cache, and async can have different orderings depending on configuration; do not assume method validation always runs before or after every other advisor.

This is why method validation at the **service boundary** is helpful for catching invalid inputs before executing business logic, yet it should not be treated as a substitute for transactions, access control, or DTO validation at the HTTP boundary.

## 3. Minimum Requirements for AOP Method Validation to Work

### 3.1. Jakarta Validation API and Provider Present

`@NotBlank` is just metadata. An implementation such as Hibernate Validator is required to enforce it.

In a Spring Boot 3.x project already configured with Java 17+ and the Spring Boot Gradle plugin, the common dependency is:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

The starter integrates the Jakarta Validation provider with Spring Boot and typically enables auto-configuration of `MethodValidationPostProcessor`. In plain Spring Framework, you must configure the provider, `Validator`/`LocalValidatorFactoryBean`, and `MethodValidationPostProcessor` yourself.

Do not mix `javax.validation.*` from the Spring 5 / Boot 2 ecosystem with `jakarta.validation.*` from Spring 6 / Boot 3.

### 3.2. Target Is a Spring-Managed Bean with `@Validated`

~~~java
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class ReportService {
    // Public methods with constraints on parameters / return value.
}
~~~

In the common proxy method-validation model, `@Validated` at the **class level** is detected by `MethodValidationPostProcessor` to apply the advisor. This differs from merely writing `@Valid` or `@NotBlank` on an arbitrary method. When using `@Validated(SomeGroup.class)`, the selected group also affects which constraints are evaluated.

A service method should be **invoked via a Spring-injected bean** from another bean. Annotations do not work magic on manually instantiated objects.

### 3.3. The Method Must Be Interceptable by the Proxy

In the simplest scenario, use **public, non-final methods** on a **non-final Spring bean class**, called through the Spring-provided reference. With JDK dynamic proxies, the method must be exposed by the corresponding interface; with CGLIB/class-based proxies, the target class/method must be overridable.

`private` methods cannot be intercepted by standard proxy-based Spring AOP. `final` methods cannot be overridden by CGLIB and therefore cannot be advised by CGLIB. Constructors, field accesses, and code executing directly inside the object are not method-call join points intercepted by this proxy.

## 4. Complete Spring Boot Example: Demonstrating Both Success and Failures

The example uses two Java classes in the same `com.example.methodvalidation` package. The Spring Boot context automatically creates the service bean, proxy, and Jakarta Validation integration. The program intentionally invokes a method with invalid input, a method returning invalid data, and an internal self-call to highlight the differences.

### 4.1. `CodeService.java`

Save at `src/main/java/com/example/methodvalidation/CodeService.java`:

~~~java
package com.example.methodvalidation;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.util.Locale;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class CodeService {

    @NotBlank
    public String normalize(
            @NotBlank
            @Size(min = 3, max = 8)
            String code) {
        return code.strip().toUpperCase(Locale.ROOT);
    }

    // Intentionally invokes a method on the same instance to illustrate proxy bypass.
    public String callInternally(String code) {
        return this.normalize(code);
    }

    @NotBlank
    public String returnBlank() {
        return "";
    }
}
~~~

Each annotation in its specific role:

- `@Validated` on the class causes the Spring AOP method-validation processor to pick up the service.
- `@NotBlank` and `@Size` on the `code` parameter are checked **before** `normalize` runs when called through the proxy.
- `@NotBlank` on the `normalize` method is a **return-value constraint**, used to validate the returned string after the method executes.
- `@NotBlank` on `returnBlank` intentionally triggers a **return-value** violation.
- `callInternally` calls `this.normalize(code)` **directly on the target**, so there is no second interception for `normalize`. The `callInternally` method itself has no direct constraints.

Using `Locale.ROOT` makes uppercase conversion deterministic, avoiding variation across machine default locales. All methods in the example are public and the class is non-`final`, satisfying typical CGLIB proxy requirements.

### 4.2. `DemoApplication.java`

Save at `src/main/java/com/example/methodvalidation/DemoApplication.java`:

~~~java
package com.example.methodvalidation;

import jakarta.validation.ConstraintViolationException;
import org.springframework.aop.support.AopUtils;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication implements CommandLineRunner {

    private final CodeService codeService;

    public DemoApplication(CodeService codeService) {
        this.codeService = codeService;
    }

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Override
    public void run(String... args) {
        System.out.println(
            "AOP proxy: " + AopUtils.isAopProxy(codeService));

        System.out.println(
            "Valid: " + codeService.normalize("abc"));

        System.out.println(
            "Invalid parameter: " + countViolations(
                () -> codeService.normalize("xy")));

        System.out.println(
            "Self-invocation: " + codeService.callInternally("xy"));

        System.out.println(
            "Invalid result: " + countViolations(
                () -> codeService.returnBlank()));
    }

    private static int countViolations(Runnable action) {
        try {
            action.run();
            return 0;
        } catch (ConstraintViolationException ex) {
            return ex.getConstraintViolations().size();
        }
    }
}
~~~

The code above uses `jakarta.validation.ConstraintViolationException`, the default from Spring's method-validation interceptor (when exception adaptation to `MethodValidationException` is not enabled). `countViolations` catches only the specific exception type being demonstrated, so other configuration errors surface instead of being hidden.

In a Spring Boot 3.x project with the Gradle plugin and Validation dependency, run:

~~~bash
./gradlew bootRun
~~~

On Windows, use:

~~~powershell
.\gradlew.bat bootRun
~~~

Aside from Spring Boot startup logs, the program prints:

~~~text
AOP proxy: true
Valid: ABC
Invalid parameter: 1
Self-invocation: XY
Invalid result: 1
~~~

Why are these results deterministic in the sample configuration?

1. `CodeService` is a `@Validated` Spring bean with constraints, so Boot's method-validation auto-configuration creates an AOP proxy: `AopUtils.isAopProxy(...)` returns `true`.
2. `normalize("abc")` is valid: the string is non-blank and 3 characters long. The body returns `"ABC"`, which also satisfies `@NotBlank`.
3. `normalize("xy")` violates `@Size(min=3,max=8)`; `@NotBlank` still passes, so the violation set has exactly **one** element; the method body is not executed.
4. `callInternally("xy")` is called through the proxy, but inside the target it calls `this.normalize("xy")`. The internal call goes straight to the method body and returns `"XY"`, showing that `@Size` on `normalize` was **not checked** on that call.
5. `returnBlank()` executes and returns an empty string; the interceptor validates `@NotBlank` on the **return value**, detects one violation, and throws an exception instead of returning the string to the caller.

This entire demo uses no database, no HTTP endpoint, and no manual interceptor coding. Proxy/advisor creation and provider invocation are managed by Spring/Boot.

If `AOP proxy: false` or the application fails to behave as expected, verify the provider, Boot configuration, `@Validated`, the actual injected bean, and the status of the method-validation post-processor before concluding Jakarta Validation does not work.

## 5. Proving the Mechanism with an Integration Test

A test that merely calls `new CodeService().normalize("xy")` is **not** an integration test of Spring method validation: a manually created object carries no Spring proxy.

To properly test the integration, use `@SpringBootTest` and inject the service. With the Spring Boot test starter:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Save at `src/test/java/com/example/methodvalidation/CodeServiceValidationTest.java`:

~~~java
package com.example.methodvalidation;

import jakarta.validation.ConstraintViolationException;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class CodeServiceValidationTest {

    @Autowired
    private CodeService service;

    @Test
    void proxyChecksParameterBeforeMethodBody() {
        assertTrue(AopUtils.isAopProxy(service));
        assertEquals("ABC", service.normalize("abc"));

        var error = assertThrows(
            ConstraintViolationException.class,
            () -> service.normalize("xy"));

        assertEquals(1, error.getConstraintViolations().size());
    }

    @Test
    void selfInvocationBypassesValidationAdvice() {
        assertEquals("XY", service.callInternally("xy"));
    }

    @Test
    void proxyChecksReturnedValue() {
        var error = assertThrows(
            ConstraintViolationException.class,
            () -> service.returnBlank());

        assertEquals(1, error.getConstraintViolations().size());
    }
}
~~~

Run `./gradlew test` or `.\gradlew.bat test`. Expected: all three tests **PASS** in a Spring Boot 3.x project with a validation provider and default AOP method validation configuration. This verifies the runtime contract: the object is Spring-managed, a proxy exists, parameters are validated, return values are validated, and self-invocation is bypassed.

For applications enabling `setAdaptConstraintViolations(true)`, the exception type changes to `MethodValidationException`; tests must adjust expectations accordingly. In non-Boot Spring Framework projects, `MethodValidationPostProcessor` also needs to be registered.

## 6. `MethodValidationPostProcessor` and `MethodValidationInterceptor`

### 6.1. Why Is a BeanPostProcessor Needed?

`MethodValidationPostProcessor` inspects beans created by Spring and registers an advisor to apply validation to matching methods. The advisor pairs:

- **Pointcut** identifying eligible beans, usually based on `@Validated`.
- **Advice**, which is `MethodValidationInterceptor`, running around matched invocations.
- **Proxy**, the object clients receive from the Spring ApplicationContext.

A Java object previously instantiated with `new` outside the container never passes through bean post-processing and never receives the advisor. That is a **lifecycle and ownership** boundary, not a failure of `@Size`.

### 6.2. Plain Spring Framework Without Boot: Explicit Configuration

In a plain Spring application with a compatible Jakarta Validation provider, you can register:

~~~java
package com.example.methodvalidation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;
import org.springframework.validation.beanvalidation.MethodValidationPostProcessor;

@Configuration
public class ValidationConfiguration {

    @Bean
    public LocalValidatorFactoryBean validator() {
        return new LocalValidatorFactoryBean();
    }

    @Bean
    public static MethodValidationPostProcessor
            methodValidationPostProcessor() {
        return new MethodValidationPostProcessor();
    }
}
~~~

This configuration is an **alternative for Spring Framework applications without Boot auto-configuration**, placed in a context with component scanning for services and a provider. `LocalValidatorFactoryBean` bridges Spring and Jakarta Validation; `MethodValidationPostProcessor` enables method interception.

Making the post-processor `@Bean static` ensures early initialization, avoiding lifecycle issues caused by configuring a BeanPostProcessor with an instance method. Do not copy this configuration into a Boot application that already has a matching post-processor and accidentally create duplicate advisors.

### 6.3. Steps Executed by the Interceptor

`MethodValidationInterceptor` extracts the invoked method, arguments, target, and active groups. It uses Jakarta Validation's `ExecutableValidator`:

~~~java
// Conceptual, not Spring's actual full source code:
executableValidator.validateParameters(
    target, method, arguments, groups);

// Only when there are no input violations:
Object returnValue = invocation.proceed();

executableValidator.validateReturnValue(
    target, method, returnValue, groups);
~~~

This is **pseudocode illustrating the sequence**, not code to copy verbatim and compile; internal implementation also handles bridge/proxy methods, cascading, configuration errors, and diverse return types. `validateParameters(...)` returns a `Set<ConstraintViolation<T>>`; the caller/framework decides how to report errors per configuration. A new `ConstraintValidator` instance is not necessarily created per call because providers may cache instances.

This mechanism does not use the Java compiler to inject `if` statements into methods. It is runtime interception based on proxy objects.

## 7. `@Validated`, `@Valid`, Constraints, and Validation Groups

### 7.1. Why Is `@Valid` Alone Insufficient for Every Method?

Consider a DTO:

~~~java
public record RegistrationRequest(
        @NotBlank String userId,
        @Min(1) int quantity) {
}
~~~

And a service:

~~~java
@Service
@Validated
public class RegistrationService {

    public void register(
            @NotNull @Valid RegistrationRequest request) {
        // Run business logic after validation.
    }
}
~~~

These are **illustrative snippets**, separate from the earlier Boot example. `@Valid` tells the provider to descend into `RegistrationRequest` and validate `userId`/`quantity`; `@NotNull` on the parameter ensures the root object itself is not null. If only `@Valid` is present, under Jakarta Validation `null` does not trigger a cascade validation failure on its own.

In Spring service AOP, class-level `@Validated` is needed and the method invocation must go through the proxy. A call with `@Valid` that occurs via `this.register(...)` still bypasses validation advice under normal proxy rules.

### 7.2. `@Validated` Selecting Groups

By default, constraints without `groups` belong to `Default`. When multiple phases are needed, define marker groups:

~~~java
public interface PublishChecks {
}
~~~

~~~java
@Service
@Validated(PublishChecks.class)
public class PublishingService {

    public void publish(
            @NotBlank(groups = PublishChecks.class)
            String title) {
        // Process after parameter satisfies the PublishChecks group.
    }
}
~~~

This snippet illustrates configuring a **group on the class**, separate from the `CodeService` demo. When a class has `@Validated(PublishChecks.class)`, the mechanism selects constraints from that group; constraints belonging only to `Default` are not automatically included without matching group inheritance or a group sequence.

To avoid missing rules, design groups with clear purposes and test both valid and invalid inputs for each group.

## 8. What Limitations Do AOP Proxies Have?

### 8.1. Self-Invocation: Calling via `this` Bypasses the Proxy

This is the most common mistake:

~~~java
@Service
@Validated
public class PaymentService {

    public void placeOrder(String reference) {
        this.checkReference(reference); // bypasses the AOP proxy
    }

    public void checkReference(
            @NotBlank String reference) {
        // Execution runs directly on self-invocation.
    }
}
~~~

If `paymentService.placeOrder("")` is called through the proxy, Spring can advise the `placeOrder` call, yet inside the target `this.checkReference("")` **does not trigger a new round of advice**. Because `placeOrder` has no constraints, an empty string can enter `checkReference` unchecked.

This is inherent to Spring AOP proxies, appearing equally with `@Transactional`, `@Cacheable`, and other proxy-based advice. It does not mean Java erased `@NotBlank`; the annotation remains in metadata, yet the invocation never passes through the interceptor.

**Architecturally sound solution:** place the boundary to validate into another bean and inject that bean:

~~~java
@Service
@Validated
public class ReferencePolicyService {

    public void checkReference(
            @NotBlank String reference) {
        // Validation / business code at the boundary.
    }
}

@Service
public class PaymentFacade {

    private final ReferencePolicyService policy;

    public PaymentFacade(ReferencePolicyService policy) {
        this.policy = policy;
    }

    public void placeOrder(String reference) {
        policy.checkReference(reference); // through the Spring proxy
    }
}
~~~

In a real project, ensure both classes reside in packages scanned by Spring. These two classes are separate illustrative examples, normally placed in `ReferencePolicyService.java` and `PaymentFacade.java`. When `ReferencePolicyService` is a `@Validated` bean and the post-processor is active, calls from `PaymentFacade` go through the policy service proxy.

Other techniques such as self-injecting the proxy or `AopContext.currentProxy()` exist, but they increase coupling to AOP infrastructure; extracting the boundary into a separate bean is usually clearer and easier to test.

### 8.2. JDK Dynamic Proxies vs. CGLIB Proxies

Spring AOP can create two kinds of proxies:

| Proxy type | Mechanism | Key limitations |
|---|---|---|
| JDK dynamic proxy | Proxy implements the target's **interfaces** | Clients can only invoke methods exposed on the interfaces; injecting by concrete class can fail |
| CGLIB class-based proxy | Proxy is a **subclass** of the target | `final` classes cannot be subclassed; `final` and `private` methods cannot be overridden/advised |

Do not rely on assumptions like "Spring always uses JDK proxies" or "Spring always uses CGLIB." `proxyTargetClass` configuration, AOP infrastructure, and Spring Boot settings influence the choice. Diagnose with:

~~~java
System.out.println(
    org.springframework.aop.support.AopUtils.isAopProxy(service));

System.out.println(
    org.springframework.aop.support.AopUtils.isJdkDynamicProxy(
        service));

System.out.println(
    org.springframework.aop.support.AopUtils.isCglibProxy(
        service));
~~~

This is an **illustrative snippet placed inside a method that holds a Spring bean `service`**; not a standalone Java class. For the `CodeService` demo, checking `isAopProxy(...) == true` suffices to confirm the reference is proxied.

If method validation must apply to a concrete method not present on an interface, check which proxy type is active; under JDK proxy configuration, that method might not be exposed. If a class/method is `final`, CGLIB cannot advise every method.

### 8.3. Private Methods, Constructors, and Manually Created Objects

~~~java
CodeService manuallyCreated = new CodeService();
manuallyCreated.normalize("xy"); // no Spring proxy
~~~

In this example, `normalize("xy")` still returns `"XY"` because there is no method interceptor. Nor is there any interceptor for calling a `private` helper inside the target. Do not try to use `@Validated` on objects outside the Spring container as a replacement for calling `Validator` directly.

Methods invoked inside a constructor or during early bean initialization should also not be assumed to pass through a fully initialized proxy. If validation is needed during object construction, use programmatic validation at a controlled point or defer the operation to a post-initialization lifecycle phase.

### 8.4. Inheritance, Overriding, and Interface Annotations

Bean Validation defines **method inheritance** rules to prevent an implementation from strengthening preconditions promised by an interface/superclass. For instance, an implementation can trigger `ConstraintDeclarationException` if it adds parameter constraints to an overridden method in violation of Jakarta Validation rules.

Do not fix issues by arbitrarily duplicating `@NotNull`, `@Size` on both interfaces and implementations. Declare the contract in one consistent place following method constraint inheritance rules, and verify it with the provider.

### 8.5. Threads, Async, and Reactive: Identifying the Real Boundary

Proxy calls only inspect data visible at the moment the interceptor runs. With `@Async`, `@Transactional`, or returning `CompletableFuture`/`Mono`/`Flux`, advisor ordering and when data actually materializes matter greatly. A constraint on a wrapper object does not automatically prove that **asynchronously emitted contents** were validated.

For reactive applications, use contracts and validators suited for reactive flows; do not infer that default Jakarta Validation method interception waits for all emitted elements to run `@NotBlank` on each one. To validate asynchronous payloads, define explicitly where data is collected and where rules are enforced.

## 9. How Does Service AOP Method Validation Differ from Spring MVC Method Validation?

### 9.1. Spring MVC 6.1+ Has Built-In Direct Method Validation

This is an easy point of confusion when reading older Spring documentation. Since **Spring Framework 6.1**, Spring MVC supports controller-layer method validation **without requiring an AOP proxy on the controller**. When a `@RequestMapping` handler has direct constraints on parameters or the return value, MVC uses its own mechanism to perform validation.

Spring MVC 6.1+ controller example:

~~~java
@RestController
public class LookupController {

    @GetMapping("/lookup")
    public String lookup(
            @RequestParam
            @NotBlank
            @Size(min = 3)
            String code) {
        return code;
    }
}
~~~

This is an **illustrative** snippet requiring Spring MVC/web starter and imports for `@RestController`, `@GetMapping`, `@RequestParam`, `@NotBlank`, and `@Size`. In MVC 6.1+, direct constraints on arguments trigger MVC's method validation and can raise `HandlerMethodValidationException` on invalid input.

**Do not place class-level `@Validated` on a controller if you want the new built-in MVC mechanism to handle method validation.** Spring documentation recommends removing class-level `@Validated` from controllers to use built-in MVC method validation. Leaving `@Validated` on the class can switch method validation to an AOP proxy, changing exception types and handling paths.

This does not change the `@Validated` requirement for **service-level AOP method validation** covered in earlier sections.

### 9.2. Distinguishing DTO Errors and Method Errors

Spring MVC can report different exceptions depending on handler signature:

| Case | Trigger point | Typical exception |
|---|---|---|
| `@Valid @RequestBody SomeDto dto`, no other direct constraints requiring method validation | Single-object validation after argument binding | `MethodArgumentNotValidException` |
| Handler with `@NotBlank`, `@Min`, `@Size` directly on parameters, or constraint on method return | MVC 6.1+ built-in method validation | `HandlerMethodValidationException` |
| `@Validated` service bean, method call via AOP proxy | Spring AOP + `MethodValidationInterceptor` | Defaults to `ConstraintViolationException` |
| Service AOP configured with `setAdaptConstraintViolations(true)` | Spring adapter converting Jakarta errors to Spring results | `MethodValidationException` |

`@Valid` **is not a constraint**; used alone on a DTO, it requests nested object validation without automatically switching the handler to method validation. Adding `@NotNull` directly on the parameter can cause MVC to select the method validation path covering nested constraints as well.

Do not write a handler catching only `ConstraintViolationException` and assume all MVC errors pass through it. In MVC 6.1+ controllers, you may need to handle both `MethodArgumentNotValidException` and `HandlerMethodValidationException`, such as inside `@ControllerAdvice`.

### 9.3. Applying Validation Appropriately by Layer

- At the **HTTP boundary**, let Spring MVC bind and validate request DTOs with its native mechanisms and return structured HTTP errors.
- At the **service boundary**, `@Validated` + AOP method validation protects calls arriving from multiple callers: controllers, schedulers, message consumers, CLIs, and other services.
- For **domain invariants** or objects created outside Spring, use explicit invariant checks or invoke Jakarta `Validator` directly; do not rely on proxies if objects bypass the container.

Service method validation does not replace authorization checks or guarantee that side effects are rolled back when return-value validation fails.

## 10. Spring Method Validation Exceptions and Handling

### 10.1. Default: `ConstraintViolationException`

In the classic AOP path, if `ExecutableValidator` detects violations, the interceptor throws `jakarta.validation.ConstraintViolationException` by default. The exception provides `getConstraintViolations()` to inspect:

~~~java
try {
    codeService.normalize("xy");
} catch (jakarta.validation.ConstraintViolationException ex) {
    for (var violation : ex.getConstraintViolations()) {
        System.out.println(violation.getPropertyPath());
        System.out.println(violation.getMessage());
    }
}
~~~

This code sits inside a component with `codeService` injected and using the default AOP path. `getPropertyPath()` in method validation can include method names and parameter/return-value nodes, unlike plain property errors. Do not hardcode `arg0` names or violation set ordering as a public contract; providers may use different parameter name providers and metadata.

### 10.2. Option: Adapting to `MethodValidationException`

Since Spring Framework 6.1, `MethodValidationPostProcessor` has an option:

~~~java
@Configuration
public class CustomMethodValidationConfiguration {

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

This is an **alternative** configuration; do not use it alongside a duplicate post-processor. Import `org.springframework.validation.beanvalidation.MethodValidationPostProcessor`, `org.springframework.context.annotation.Bean`, and `Configuration` when placing it in a standalone project.

When enabled, Spring can convert errors into `MethodValidationException` with results modeled by `MethodValidationResult`, `ParameterValidationResult`, and `MessageSourceResolvable`, aligning well with Spring message resolution mechanisms. The `catch (ConstraintViolationException)` examples in sections 4 and 5 are written for **default mode**; if you change this option, update tests and exception handling.

Service AOP's `MethodValidationException` is distinct from built-in MVC handler validation's `HandlerMethodValidationException`.

## 11. Validation Groups, Advisor Ordering, and Transactions

A single bean may carry `@Validated`, `@Transactional`, `@Async`, and `@Cacheable`. Multiple interceptors/advisors then exist:

~~~text
Caller
  |
  v
AOP proxy (advisor chain)
  |-- Method validation advisor
  |-- Transaction advisor
  |-- Caching / other advisors
  v
Target method
~~~

The order illustrated in the diagram **is not a guarantee of actual execution order**. Ordering configuration alters crucial outcomes:

- If parameter validation runs **outside** the transaction, invalid data can be rejected before a transaction opens.
- If return-value validation occurs **outside** the transaction, the transaction may already have committed before the validation exception is thrown.
- If return-value validation occurs **inside** the transaction and the exception triggers a rollback, the outcome may differ.
- If a call is served by a cache advisor without running the target, whether the result is validated depends on the validation advisor's position in the chain.

Therefore, never promise that "return validation always rolls back transactions" or "method validation always runs before every business advice." For data-mutating operations, design explicit transaction boundaries and test the **actual AOP advisor configuration**.

Parameter constraints typically express *preconditions*, while return-value constraints express *postconditions*. Postconditions are valuable for contract checking and observability, yet they do not automatically undo executed business operations.

## 12. Diagnosing When Annotations Exist but Methods Still Run with Bad Data

Check in the following order:

1. **Is a Jakarta Validation provider present?** `spring-boot-starter-validation` or an equivalent provider must be present; the annotation API alone is not enough.
2. **Is the bean actually managed by Spring?** Does it have `@Service`/`@Component` and component scanning or a bean declaration? Avoid `new`.
3. **Is `@Validated` on the target class?** For default Spring AOP method validation on services, this is the activation marker. Verify the Spring package import.
4. **Does the method have real constraints?** Valid `@NotBlank`/`@Size` on parameters/return values or valid `@Valid` cascades; do not use an annotation on an incompatible data type.
5. **Is there a method-validation post-processor?** Boot auto-config or a `MethodValidationPostProcessor` bean in plain Spring; check whether custom config replaced it.
6. **Is the caller going through the proxy?** Check `AopUtils.isAopProxy(bean)`; check for self-invocation, manually instantiated objects, and non-Spring references.
7. **Does the proxy type allow intercepting the method?** Check interfaces for JDK proxies, `final`/`private` for class-based proxies, and class visibility.
8. **Which group is being evaluated?** `@Validated(SomeGroup.class)` may exclude `Default` constraints; `@NotBlank`'s group does not automatically match everywhere.
9. **Are you in Spring MVC 6.1+?** Controllers have their own built-in method validation; placing class-level `@Validated` may divert to an AOP proxy.
10. **Where is the exception handled?** If an outer layer catches/swallows or translates exceptions, inspect both the service method contract and HTTP exception handlers.
11. **Are multiple advisors present?** Verify transaction/cache/async interactions and post-processors instead of assuming order.
12. **Is there actually a violation?** `@NotNull` accepts empty strings while `@NotBlank` does not; `@Size(min=3)` measures the incoming string length before the method logic alters it.

Quick troubleshooting table:

| Symptom | Common cause | Resolution |
|---|---|---|
| `normalize("xy")` throws no error on injected bean | Missing/misconfigured provider, `@Validated`, or post-processor, or bean is not proxied | Inspect dependencies, context, and `AopUtils` |
| Calling from another bean fails validation, calling `this.normalize` does not | Self-invocation bypasses advice | Extract boundary into an injected bean and call through its proxy |
| Calling via `new CodeService()` does not validate | Object not created by Spring | Use the Spring bean or invoke Jakarta `Validator` programmatically |
| `private`/`final` method is not intercepted | Proxy/advice capabilities limitation | Design public, interceptable boundaries |
| Runtime cast/injection error with JDK proxy | Bean exposed by interface, not concrete subtype | Inject the appropriate interface or configure proxy type intentionally |
| Seeing `ConstraintViolationException` instead of MVC error | Validation ran via service AOP, not built-in MVC | Handle exceptions per boundary and actual mechanism |
| Seeing `HandlerMethodValidationException` in controller | Spring MVC 6.1+ built-in method validation | Handle the corresponding MVC exception type |
| Valid input succeeds, invalid return causes exception | Constraint on return value | Fix return logic; review side effects/transaction ordering |
| Only some constraints run | Group selection or constraint type | Check `groups`, `@Validated(...)`, and annotation targets |
| App has two method validation post-processors | Manual config duplicates Boot auto-config | Simplify configuration to one intentional mechanism |
| Subclass method override constraint error | Jakarta Validation inheritance rules violated | Fix the method contract on the interface/superclass |
| Direct test passes while integration fails | Test does not use the Spring proxy/provider properly | Test the bean obtained from ApplicationContext |

## 13. When to Use AOP Method Validation and When Not To

**Use it** for public methods at service boundaries invoked by other Spring beans, where input/output contracts are expressible with Jakarta Validation and you want consistent enforcement across multiple callers without repeating `validator.validate(...)` statements.

**Consider alternatives** when objects are not Spring-managed, checks happen inside constructors/private helpers, self-invocation is a regular pattern, or you must verify business conditions tied to transaction/database state at a specific point. In those cases, use programmatic validation or domain/service methods with explicit boundaries.

AOP method validation catches declarative contract violations. It does not replace complex business rule checks, does not provide transaction/authorization enforcement, and does not guarantee internal calls are validated.

## 14. Practice Questions

**Question 1.** Why can Spring see `@NotBlank` on a method parameter yet a normal Java call still accepts an empty string?

Because annotations are metadata. `ExecutableValidator` must be invoked by an interceptor or explicit code. AOP only intervenes when the call **goes through the Spring proxy**.

**Question 2.** How do `@Validated` and `@Valid` differ in service AOP?

Class-level `@Validated` lets Spring's method-validation post-processor select the target and can specify groups. `@Valid` tells Jakarta Validation to cascade into objects on parameters/return values/properties; it does not create a Spring AOP proxy on its own.

**Question 3.** In the demo, why was `codeService.normalize("xy")` blocked while `codeService.callInternally("xy")` returned `XY`?

The first call went through the proxy and was blocked by `@Size(min=3)`. The second entered `callInternally` via the proxy, then called `this.normalize` directly on the target, bypassing `normalize`'s interceptor.

**Question 4.** For a method annotated with `@NotBlank` on its return value, does Spring validate before or after running the body?

After the method returns normally. If the constraint fails, the caller receives an exception; prior side effects are not automatically undone by AOP validation.

**Question 5.** Why might a Spring MVC 6.1+ controller throw `HandlerMethodValidationException` while a `@Validated` service typically throws `ConstraintViolationException`?

Controllers have MVC's built-in method validation, whereas services use AOP `MethodValidationInterceptor`; these are two distinct triggering and error-conversion mechanisms.

**Question 6.** Does adding `@NotBlank` to a `private` helper guarantee validation when called from a public service method?

No, because proxy-based Spring AOP does not intercept private methods. Use a public boundary on another bean or invoke validation programmatically at the appropriate spot.

**Question 7.** Is seeing `@Validated` on a bean enough to confirm method validation is active?

No. You need a provider, post-processor, proxy/advisor, suitable method signature, and invocations actually passing through the proxy; prove it with an integration test.

## 15. Implementation and Verification Checklist

- [ ] Choose the Jakarta Validation API/provider matching Spring Framework 6 / Spring Boot 3.
- [ ] Service is a Spring-managed bean; declare Spring `@Validated` at the class level for standard AOP method validation.
- [ ] Constraints are placed properly on parameters/return values; pair `@Valid` for cascading and `@NotNull` to disallow null.
- [ ] `MethodValidationPostProcessor` is active, via Boot auto-configuration or explicit Spring configuration.
- [ ] Callers inject the bean and invoke through the proxy; do not rely on `new` or self-invocation.
- [ ] Methods are interceptable under JDK/CGLIB proxies, avoiding `private`/`final` at validation boundaries.
- [ ] Understand default `ConstraintViolationException` and the `MethodValidationException` option.
- [ ] Separate Spring MVC 6.1+ built-in method validation from service AOP, handling the appropriate exception types.
- [ ] Test invalid input, valid input, invalid return values, self-invocation, and relevant groups.
- [ ] When combining transaction/cache/async, inspect advisor ordering and side effects instead of guessing from annotation order.

**Key takeaway:** `@Validated` helps Spring **select the bean**, `MethodValidationPostProcessor` creates the **advisor/proxy**, `MethodValidationInterceptor` runs **Jakarta `ExecutableValidator` before and after the method**, and **callers must pass through the proxy** for advice to take effect. Self-invocation is the central limitation; meanwhile, Spring MVC 6.1+ has its own method validation mechanism for controllers.

## Official References

- [Spring Framework — Java Bean Validation: Spring-driven Method Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Framework — Proxying Mechanisms and self-invocation](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework 6.2 — Spring MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Boot — Validation](https://docs.spring.io/spring-boot/reference/io/validation.html)
- [Spring API — MethodValidationPostProcessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/beanvalidation/MethodValidationPostProcessor.html)
- [Spring API — MethodValidationInterceptor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/beanvalidation/MethodValidationInterceptor.html)
- [Jakarta Validation — Method and Constructor Validation](https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html#methodandconstructorvalidation)
