# LocalValidatorFactoryBean: Integrating a Bean Validation Provider with Spring

## 1. Purpose: Connecting the Jakarta Bean Validation Standard to Spring Infrastructure

`LocalValidatorFactoryBean` in the `org.springframework.validation.beanvalidation` package is the bridge between **Jakarta Bean Validation** and the **Spring Framework** ecosystem. It initializes a `jakarta.validation.ValidatorFactory` through an execution provider (such as **Hibernate Validator**), exposes a default `Validator` for the application, and adapts validation results into error structures understood by Spring Data Binding and Spring MVC.

Distinguish three roles:

- **Jakarta Validation API** (`jakarta.validation.*`): defines `@Valid`, `Validator`, `ConstraintValidator`, `ConstraintViolation`, and standard annotations like `@NotNull`, `@NotBlank`, `@Size`.
- **Bean Validation provider** (typically `org.hibernate.validator:hibernate-validator`): discovers constraint metadata, executes checks, interpolates error messages, and manages validator lifecycles.
- **Spring `LocalValidatorFactoryBean`**: bootstraps and configures the provider, exposes it as a Spring bean, supports dependency injection inside custom `ConstraintValidator`s, and converts `ConstraintViolation`s into Spring `Errors`/`FieldError`s.

Flow diagram:

```text
DTO/bean with @NotBlank, @Size, @Valid, @Constraint ...
                       |
                @Valid / Validator
                       |
          LocalValidatorFactoryBean (Spring bean)
                       |
       jakarta.validation.ValidatorFactory
                       |
       Execution provider (e.g., Hibernate Validator)
                       |
           ConstraintViolation<?> 
                       |
       +---------------+----------------+
       |                                |
 Jakarta Validator               Spring Validator
 Set<ConstraintViolation>        Errors / FieldError
       |                                |
 Service, direct testing         WebDataBinder, Spring MVC
```

**Core point:** `LocalValidatorFactoryBean` **does not become a validation engine itself**; it delegates to the actual provider on the classpath. Adding only `jakarta.validation-api` to a project is not enough to perform validation without a provider.

## 2. Two Interface Hierarchies on the Same Bean

`LocalValidatorFactoryBean` simultaneously implements the main contracts:

| Interface | Purpose | Usage |
| --- | --- | --- |
| `jakarta.validation.ValidatorFactory` | Create/retrieve validators, configure context | `factory.getValidator()`, `factory.usingContext()` |
| `jakarta.validation.Validator` | Validate beans using Bean Validation | `validator.validate(command)` |
| `org.springframework.validation.Validator` | Validate beans via `Errors` | `springValidator.validate(command, errors)` |
| `org.springframework.validation.SmartValidator` | Spring validator supporting validation hints/groups | `smartValidator.validate(command, errors, Create.class)` |

Because **both Jakarta and Spring define the name `Validator`**, use explicit imports or fully qualified names in real code:

```java
private final jakarta.validation.Validator jakartaValidator;
private final org.springframework.validation.Validator springValidator;
```

Difference in results:

```java
// Jakarta style: set of constraint violations.
Set<ConstraintViolation<UserInput>> violations =
        jakartaValidator.validate(userInput);

// Spring style: record errors into BindingResult/Errors.
BindingResult errors =
        new BeanPropertyBindingResult(userInput, "userInput");
springValidator.validate(userInput, errors);
```

The two snippets above only illustrate how to invoke them, assuming `UserInput` is an existing model and `jakartaValidator`, `springValidator` are already injected; appropriate imports are needed. The Spring adapter translates the provider's `ConstraintViolation`s into `FieldError` or `ObjectError` instances and records them in `Errors`. This is why standard constraints work seamlessly with Spring MVC's `BindingResult`.

**Do not confuse:** `@Valid` (Jakarta) is a marker requesting validation/cascading at an integration context; it **does not automatically run simply because an object was instantiated with `new`**. If you construct objects manually in regular code, you must explicitly call `Validator.validate(...)` or go through an entry point where Spring supports validation.

## 3. Dependencies, Versions, and Bootstrap Mechanism

With **Spring Framework 6+/Spring Boot 3+**, use `jakarta.validation.*`. Older Spring 5/Boot 2 projects use `javax.validation.*`; mixing legacy `javax` annotations with `jakarta` infrastructure easily causes constraints to go unrecognized. Choose dependencies matching *the same API generation*.

### Spring Boot

In a Maven Spring Boot project:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

The starter normally provides the API and Hibernate Validator provider, along with required runtime dependencies per the BOM. **You do not need to manually define `LocalValidatorFactoryBean` in most Boot applications**: Boot's auto-configuration registers a default validator when a Bean Validation provider is present. If you define the bean manually, verify how auto-configuration behaves and which bean MVC actually uses.

### Direct Spring Framework Configuration

In a Spring Framework application without Boot, declare:

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

This is a **Spring configuration class**, requiring Spring Context, Jakarta Validation API, and a compatible provider on the classpath. When ApplicationContext creates the bean, Spring calls `afterPropertiesSet()`: Spring prepares provider configuration, invokes the standard Bean Validation bootstrap, retrieves the default `Validator`, and prepares the adapter. When the context closes, `destroy()` closes the `ValidatorFactory` owned by the bean.

**How is the provider discovered?** Following the standard Jakarta Validation bootstrap mechanism, the provider is discovered via service discovery/metadata on the classpath (or explicitly selected if configured). If no suitable provider is found, bootstrapping typically fails; `OptionalValidatorFactoryBean` is a variant that silently ignores a missing provider, so avoid using it to mask missing dependencies in applications that genuinely require validation.

## 4. Runnable Spring Boot 3.5 and Java 17 Example

This example demonstrates **a single Boot-configured `LocalValidatorFactoryBean`** serving both APIs, and allows a custom `ConstraintValidator` to receive a Spring dependency via `@Autowired`.

File structure:

```text
validation-demo/
├── pom.xml
└── src/main/java/example/validation/ValidationBridgeApplication.java
```

**`pom.xml`** — using the released Spring Boot 3.5.8 version, Java 17:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.8</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>validation-demo</artifactId>
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
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/example/validation/ValidationBridgeApplication.java`** — complete program:

```java
package example.validation;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import jakarta.validation.Constraint;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import jakarta.validation.Payload;
import jakarta.validation.constraints.NotBlank;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.validation.BeanPropertyBindingResult;

@SpringBootApplication
public class ValidationBridgeApplication {

    public static void main(String[] args) {
        SpringApplication.run(ValidationBridgeApplication.class, args);
    }

    @Bean
    AllowedPrefixes allowedPrefixes() {
        return new AllowedPrefixes();
    }

    @Bean
    CommandLineRunner demo(
            jakarta.validation.Validator jakartaValidator,
            org.springframework.validation.Validator springValidator) {
        return args -> {
            Registration invalid = new Registration("", "US-42");

            long jakartaErrors =
                    jakartaValidator.validate(invalid).size();
            System.out.println("Jakarta violations: " + jakartaErrors);

            BeanPropertyBindingResult errors =
                    new BeanPropertyBindingResult(
                            invalid, "registration");
            springValidator.validate(invalid, errors);
            System.out.println("Spring field errors: "
                    + errors.getFieldErrorCount());
            System.out.println("Code message: "
                    + errors.getFieldError("code").getDefaultMessage());
        };
    }

    // Immutable dependency; the provider does not need to instantiate it manually.
    public static final class AllowedPrefixes {
        boolean accepts(String code) {
            return code.startsWith("VN-");
        }
    }

    @Target(ElementType.FIELD)
    @Retention(RetentionPolicy.RUNTIME)
    @Constraint(validatedBy = AllowedPrefixValidator.class)
    public @interface AllowedPrefix {
        String message() default "code must start with VN-";
        Class<?>[] groups() default {};
        Class<? extends Payload>[] payload() default {};
    }

    // SpringConstraintValidatorFactory creates and injects this instance.
    public static final class AllowedPrefixValidator
            implements ConstraintValidator<AllowedPrefix, String> {

        @Autowired
        private AllowedPrefixes prefixes;

        @Override
        public boolean isValid(
                String value, ConstraintValidatorContext context) {
            return value == null || prefixes.accepts(value);
        }
    }

    public static final class Registration {
        @NotBlank(message = "name required")
        private final String name;

        @AllowedPrefix
        private final String code;

        public Registration(String name, String code) {
            this.name = name;
            this.code = code;
        }

        public String getName() {
            return name;
        }

        public String getCode() {
            return code;
        }
    }
}
```

Run in the directory containing `pom.xml` with JDK 17+ and Maven:

```bash
mvn spring-boot:run
```

In the Spring Boot startup log, **these exact lines printed by the example** will appear:

```text
Jakarta violations: 2
Spring field errors: 2
Code message: code must start with VN-
```

**Step-by-step explanation:**

1. Boot finds the provider on the classpath via `spring-boot-starter-validation` and provides the validator through built-in configuration.
2. `@NotBlank` on `name` rejects the empty string; custom `@AllowedPrefix` on `code` rejects `US-42`.
3. The provider invokes `AllowedPrefixValidator.isValid`. Because Spring creates constraint validators via `SpringConstraintValidatorFactory`, the `prefixes` field is injected from the `AllowedPrefixes` bean.
4. The Jakarta API returns two `ConstraintViolation`s. The Spring API runs the same constraints and records two `FieldError`s into `BeanPropertyBindingResult`.
5. `getFieldError("code")` returns the annotation's custom message; we do not depend on the ordering of elements in the `ConstraintViolation` set.

The `isValid` method treats `null` as valid here because **the prefix rule** only applies when a value is present. If `code` is required, pair it with `@NotBlank` or `@NotNull`. Do not assume a format-checking constraint also checks requiredness.

## 5. Why Can a Custom `ConstraintValidator` Inject Spring Beans?

Jakarta Bean Validation instantiates constraint validators through `ConstraintValidatorFactory`. `LocalValidatorFactoryBean` **uses `SpringConstraintValidatorFactory` by default**, connecting to the ApplicationContext's `AutowireCapableBeanFactory` to instantiate and inject `ConstraintValidator` classes. Thus a constraint can call policy-lookup services, repositories, or configuration beans:

```java
public final class CustomerCodeValidator
        implements ConstraintValidator<ValidCustomerCode, String> {

    @Autowired
    private CustomerCodePolicy policy;

    @Override
    public boolean isValid(
            String value, ConstraintValidatorContext context) {
        return value == null || policy.isAllowed(value);
    }
}
```

This is an **illustrative snippet**, assuming the `ValidCustomerCode` annotation, `CustomerCodePolicy` interface/class, and corresponding imports already exist. **Field injection is used here to make the mechanism clear**, not to imply every validator must use field injection. Constructor injection can be used when Spring creates the object and dependencies are properly managed.

**Prerequisites:**

- The validator class must have a compatible type/signature for `@Constraint(validatedBy = ...)`; the constraint annotation must define `message`, `groups`, and `payload` per Jakarta Validation.
- The injected bean must exist in the same Spring context and not introduce a circular dependency.
- If the application manually calls `Validation.buildDefaultValidatorFactory()` and uses that factory independently, constraint validator creation **does not go through Spring's default `SpringConstraintValidatorFactory`**. In that case `@Autowired` may not be processed as expected.
- The provider may cache/reuse `ConstraintValidator` instances. `initialize(...)` is used to prepare annotation metadata; `isValid(...)` should avoid writing request data into shared fields. Avoid letting a mutable instance retain state from a previous validation; ensure thread safety for state and dependencies.
- It is not strictly necessary to put `@Component` on every constraint validator class; by default the factory can create and autowire them on demand. If you do add a stereotype annotation, understand that the provider may still create separate instances rather than using the singleton bean you might expect.

Spring's injection support only addresses **object instantiation and dependency wiring**; it does not replace concurrency contracts, API limits, or provider validation logic.

## 6. Integration with Spring MVC and `WebDataBinder`

When a request is bound:

1. Spring reads JSON via `HttpMessageConverter` or binds form/query parameters via the corresponding binding mechanism.
2. Spring checks conversion/binding and detects `@Valid`/`@Validated` markers at supported locations.
3. MVC invokes the validator configured for the request/model; typically a `LocalValidatorFactoryBean` (if a provider is present).
4. The provider checks constraints, and Spring translates violations into errors on `BindingResult`.
5. The controller can handle `BindingResult` directly in the method or let exception handling return an error response.

Example **controller snippet** in Spring MVC (assuming `RegistrationRequest` has Bean Validation annotations on fields/getters):

```java
@PostMapping("/registrations")
public ResponseEntity<?> create(
        @Valid @RequestBody RegistrationRequest body,
        BindingResult errors) {

    if (errors.hasErrors()) {
        var messages = errors.getFieldErrors().stream()
                .map(e -> e.getField() + ": " + e.getDefaultMessage())
                .toList();
        return ResponseEntity.badRequest().body(messages);
    }
    return ResponseEntity.ok().build();
}
```

This is a **non-standalone illustrative method**, requiring a controller class, model, imports for `jakarta.validation.Valid`, `org.springframework.validation.BindingResult`, `org.springframework.http.ResponseEntity`, and matching Spring MVC annotations. When using this error-handling pattern, place `BindingResult` **immediately after the validated argument**. If there is no adjacent `Errors`/`BindingResult` argument and validation fails, Spring MVC typically throws an invalid-argument exception (e.g., `MethodArgumentNotValidException`). For **method validation** with constraints directly on parameters or return values, the mechanism/exception type may vary by version and method signature (e.g., `HandlerMethodValidationException` in modern MVC).

Spring's `@Validated` allows specifying **validation groups** when needed. In modern Spring MVC, method-level validation has built-in support; placing `@Validated` at the controller class level can trigger proxy/AOP mechanisms instead of the newer built-in mechanism. Therefore, only add class-level `@Validated` when you genuinely know which method validation mode you need.

### Which Validator Does Spring MVC Choose?

In standard MVC configuration, if a Bean Validation provider is on the classpath, Spring may register `LocalValidatorFactoryBean` as the **global validator**; Spring Boot also has its own auto-configuration. To use a customized validator, you can declare it via `WebMvcConfigurer#getValidator()`:

```java
@Configuration
public class MvcValidatorConfiguration implements WebMvcConfigurer {
    private final LocalValidatorFactoryBean validator;

    public MvcValidatorConfiguration(LocalValidatorFactoryBean validator) {
        this.validator = validator;
    }

    @Override
    public org.springframework.validation.Validator getValidator() {
        return validator;
    }
}
```

This is an **illustrative configuration class**; it needs imports for `@Configuration`, `WebMvcConfigurer`, `LocalValidatorFactoryBean`, and ensures a validator bean is actually available to inject. Use it when you need explicit control over the active MVC validator; **do not add it to every Boot app** if auto-configuration already uses the right bean.

Controllers can attach local validators with `@InitBinder`/`WebDataBinder.addValidators(...)` for a specific model; those validators can also run alongside the global validator depending on configuration. Do not accidentally replace the global validator when the business logic still relies on Jakarta constraints.

## 7. Mechanism for Converting `ConstraintViolation` to Spring `Errors`

Suppose a model has:

```java
@NotBlank(message = "Name is required")
private String name;

@Size(min = 2, max = 16)
private String nickname;
```

With `name=""` and `nickname="X"`, the Jakarta API can produce two `ConstraintViolation`s carrying:

- `getPropertyPath()`: e.g., `name` or `nickname`.
- `getMessage()`: the interpolated error message.
- `getMessageTemplate()`: the original template, e.g., `{jakarta.validation.constraints.Size.message}`.
- `getInvalidValue()` and `getConstraintDescriptor()`: the invalid value and constraint metadata.

The Spring adapter reads the violations and registers them as `FieldError`/`ObjectError` instances in `Errors`; call `errors.getFieldErrors("name")` or `errors.getAllErrors()` as required by the UI/API. `FieldError` holds the field, rejected value, code, and interpolated message, enabling Spring MVC to display errors next to inputs.

**A critical distinction:**

- **Type conversion/binding error** occurs when data cannot be converted to the target type, e.g., assigning `"abc"` to an `Integer`. It is not a `ConstraintViolation` produced by `@Min`.
- **Bean Validation error** occurs once the object is populated and a constraint rule fails.
- Both categories of errors can coexist in `BindingResult` from the same binding pass. Controllers should not assume every `FieldError` originated from Jakarta Validation.

When using the Jakarta API directly (in services or tests), you receive `Set<ConstraintViolation<T>>` and decide how to return errors. When using Spring's binder, leverage `BindingResult`, `MessageCodesResolver`, and the application's exception handling mechanism.

## 8. Constraint Groups and Nested Validation

### Validation Groups

Jakarta Validation has the default group `jakarta.validation.groups.Default`. To separate creation and update rules:

```java
public interface OnCreate {}

public class AccountInput {
    @NotBlank(groups = OnCreate.class)
    private String password;
}
```

These are **illustrative declarations**, requiring the `@NotBlank` import and placing the class/interface in appropriate source files. In the controller:

```java
@PostMapping("/accounts")
public void create(@Validated(OnCreate.class)
                   @RequestBody AccountInput input) {
    // ...
}
```

With `SmartValidator`, validation hints are typically used as groups:

```java
BindingResult errors =
        new BeanPropertyBindingResult(input, "accountInput");
smartValidator.validate(input, errors, OnCreate.class);
```

This snippet assumes the variables are already initialized. **Note on selected groups:** if only `OnCreate` is requested, constraints belonging solely to `Default` do not automatically run unless the group/group schema is configured accordingly (e.g., group inheritance/sequence). Test actual behavior instead of assuming all annotations always run.

### `@Valid` Cascading

`@Valid` on a nested property triggers validation of the inner object:

```java
public class CheckoutRequest {
    @NotNull
    @Valid
    private Address deliveryAddress;
}

public class Address {
    @NotBlank
    private String city;
}
```

This is an illustrative class snippet. Without `@Valid`, the provider normally checks only constraints placed on the `deliveryAddress` property itself rather than traversing rules on `Address.city`. If `deliveryAddress == null`, `@Valid` does not make it required; `@NotNull` handles that part.

**Group sequences**, group conversions, and cascaded validation must be designed for complex data, though they are features of the **Bean Validation provider**, not custom logic implemented independently by `LocalValidatorFactoryBean`.

## 9. Error Messages and i18n: `ValidationMessages.properties` vs Spring `MessageSource`

Normally, the provider interpolates constraint messages from `ValidationMessages.properties` on the classpath and from the provider's default messages. For example:

```properties
# src/main/resources/ValidationMessages.properties
user.name.required=Name must not be blank
user.code.invalid=Code must start with VN-
```

Annotation:

```java
@NotBlank(message = "{user.name.required}")
private String name;
```

The provider resolves the `{user.name.required}` message template into the corresponding string.

To share **Spring's `MessageSource`** for validation messages, `LocalValidatorFactoryBean` provides a setter:

```java
@Bean
public LocalValidatorFactoryBean validator(MessageSource messageSource) {
    LocalValidatorFactoryBean factory =
            new LocalValidatorFactoryBean();
    factory.setValidationMessageSource(messageSource);
    return factory;
}
```

This is a **Spring bean declaration snippet**, requiring imports for `@Bean`, `MessageSource`, `LocalValidatorFactoryBean`, and a configured `messageSource` that actually contains the desired keys. Spring Javadoc notes that `setValidationMessageSource` integration relies on capabilities of Hibernate Validator/`ResourceBundleMessageInterpolator`; when switching providers, compatibility must be verified. **Do not call both `setMessageInterpolator(...)` and `setValidationMessageSource(...)`**: both govern message interpolation. A `MessageSource` used for the validator should allow sensible fallback, avoiding `useCodeAsDefaultMessage=true` which can suppress the provider's default messages.

There are two message layers:

1. The provider interpolates `ConstraintViolation.getMessage()` from constraint keys.
2. Spring generates error codes/messages for `BindingResult` so UIs or handlers can use `MessageSource` to render messages by field, object, and locale.

Do not confuse constraint key naming with Spring's `MessageCodesResolver` mechanism; they can work together, but they are not the same API.

## 10. Key Customization Points of `LocalValidatorFactoryBean`

| API/Configuration | Effect | When Needed |
| --- | --- | --- |
| `setProviderClass(...)` | Specifies a particular provider class | Multiple providers exist and an explicit choice is needed |
| `setValidationProviderResolver(...)` | Replaces provider discovery mechanism | Special classloader/plugin environments |
| `setConstraintValidatorFactory(...)` | Replaces how custom constraint validators are created | Custom factory; avoid breaking Spring DI |
| `setValidationMessageSource(...)` | Uses Spring messages for constraint interpolation | Unifying i18n with the application |
| `setMessageInterpolator(...)` | Provides a custom Jakarta interpolator | Custom message rules |
| `setMappingLocations(...)` | Loads constraint mappings from XML resources | Systems using XML constraint mapping |
| `setValidationProperties(...)` or `setValidationPropertyMap(...)` | Passes configuration properties to the provider | Provider-specific settings |
| `setTraversableResolver(...)` | Controls graph traversal/access during validation | Persistence integration or special contexts |
| `setParameterNameDiscoverer(...)` | Customizes how parameter names are resolved | Validating method/constructor constraints |
| `setConfigurationInitializer(...)` | Callback customizing `jakarta.validation.Configuration<?>` before build | Accessing special bootstrap options |

These setters must be configured **before Spring finishes initializing the validator bean**. Example:

```java
@Bean
LocalValidatorFactoryBean customValidator() {
    LocalValidatorFactoryBean factory =
            new LocalValidatorFactoryBean();
    factory.setValidationPropertyMap(
            Map.of("hibernate.validator.fail_fast", "true"));
    return factory;
}
```

This **illustrative bean snippet** requires importing `java.util.Map` and Spring annotations. `hibernate.validator.fail_fast` is a **Hibernate Validator**-specific property, not a universal property guaranteed by every Bean Validation provider. Fail-fast mode can stop early upon encountering a violation, so **do not rely on a fixed error count or order when this feature is enabled**.

**Considerations before switching providers:** Hibernate Validator is an implementation of Jakarta Validation, distinct from Hibernate ORM/JPA. Having Hibernate ORM does not guarantee a compatible Bean Validation provider is present; verify runtime dependencies. If multiple providers exist, default selection order should not be treated as a business rule; choose a provider explicitly when determinism is required.

## 11. Lifecycle, Performance, and Thread Safety

`LocalValidatorFactoryBean` is managed as a Spring bean and typically lives for the duration of the ApplicationContext:

1. Initialization: Spring receives configuration, ApplicationContext, and `ConstraintValidatorFactory`.
2. Provider bootstrap: creates `ValidatorFactory`, retrieves the default validator.
3. Usage: multiple services/binders/controllers can reuse the same `Validator` bean for independent validations.
4. Cleanup: when the Spring context closes, `LocalValidatorFactoryBean` releases the underlying factory.

**You should** reuse the configured `ValidatorFactory`/`Validator`; repeatedly creating a new factory per request is expensive and can break dependency/lifecycle behavior. The provider is responsible for caching metadata and constraint validator instances according to the API contract.

**You should not** store the target bean being validated or request data in mutable fields of a reusable custom `ConstraintValidator`. If a constraint needs annotation parameters, store stable configuration in `initialize(...)`; if an external service is needed, inject one with a clear thread-safety policy. For I/O operations, evaluate whether calling external services belongs in the validation flow; querying a database inside every constraint can cause repeated queries, increase latency, complicate testing, and introduce unintended transaction interactions.

**Do not manually instantiate a validator inside business methods** when a Spring-managed bean is already available:

```java
// Avoid repeating this on every request:
ValidatorFactory factory = Validation.buildDefaultValidatorFactory();
try {
    Validator validator = factory.getValidator();
    validator.validate(input);
} finally {
    factory.close();
}
```

This is an illustrative Java snippet; it bypasses the existing Spring bean, and creating an independent factory lacks `SpringConstraintValidatorFactory` for dependency injection. Replace it with dependency injection of the Spring-managed `jakarta.validation.Validator`.

## 12. Validation in Services: Distinguishing Object vs Method Validation

`Validator.validate(bean)` checks constraints on a **specific object** at the time of invocation; it does not automatically validate every argument of every method.

For method/constructor constraints (e.g., `@NotNull` on a service method parameter or `@Min` on a return value), distinguish two mechanisms:

- Jakarta Validation provides **`ExecutableValidator`** via `validator.forExecutables()`, enabling explicit parameter/return value validation.
- Spring supports **method validation** via `MethodValidationPostProcessor` and related integrations; `@Validated` on a Spring-managed service typically works with AOP proxies in an appropriate configuration. Do not assume annotations on an internal self-call (`this.someMethod()`) pass through the proxy. In modern Spring MVC, controller method validation also has its own built-in integration mechanism.

This is a **configuration- and version-specific integration area**. Having `LocalValidatorFactoryBean` does not mean every method is automatically validated just by adding constraints. Verify how method validation is enabled and write tests that actually invoke through the Spring bean/proxy when needed.

## 13. Testing the Right Integration Layers

Different layers require different tests:

**A. Provider + custom constraint:** use `@SpringBootTest` or a lightweight ApplicationContext to inject `jakarta.validation.Validator`; construct an invalid model and call `validate(...)`. Assert violation property paths and messages; when testing custom dependencies, mock/test external beans consistently.

**B. Bridge to Spring:** inject `org.springframework.validation.Validator`, create a `BeanPropertyBindingResult`, and call `validate(target, errors)`; check `hasFieldErrors("code")`/`getFieldErrorCount()`. This catches issues where the provider works but the Spring adapter is not being used.

**C. MVC request flow:** test endpoints with `MockMvc` to confirm `@Valid`/`@Validated` triggers and the error response is right. Specifically verify `BindingResult` placement and exception handler behavior.

**D. Groups/cascading:** test `@Valid` on nested beans, `@Validated(SomeGroup.class)`, null nested fields, and constraints belonging solely to `Default`.

**E. i18n:** supply a locale and verify message keys are actually interpolated, rather than asserting only that the provider returns a default string.

**F. Lifecycle/DI:** test custom `ConstraintValidator`s with Spring dependencies, and verify no second validator factory is created outside the context on the main path.

Short test example at the Jakarta layer (this is an **illustrative method** with beans already prepared):

```java
var violations = jakartaValidator.validate(invalidRegistration);
assertEquals(2, violations.size());
assertTrue(violations.stream()
        .anyMatch(v -> v.getPropertyPath().toString().equals("code")));
```

You need imports or static imports for JUnit 5 assertions, an `invalidRegistration` object, an injected `jakartaValidator`, and matching test dependencies. **The order of elements in `Set<ConstraintViolation>` is not guaranteed**; assert by path/message rather than by the first element.

## 14. Common Configuration Errors and Troubleshooting

| Symptom | Possible Cause | How to Check/Fix |
| --- | --- | --- |
| `NoProviderFoundException` when creating factory | Only API present, missing implementation | Add a compatible provider; with Boot use starter-validation |
| Constraints are ignored | Legacy `javax.validation.*` imports or missing `@Valid`/`@Validated` at trigger point | Align Jakarta/Spring versions; verify validation execution path |
| `@Autowired` in custom validator is null | Independent `ValidatorFactory` created or default factory replaced | Use Spring-managed `LocalValidatorFactoryBean`/`SpringConstraintValidatorFactory` |
| Provider runs but `BindingResult` has no errors | MVC uses a different validator or binding validation is not triggered | Check global/local validators, annotations, and exact bound target |
| Two `Validator` beans cause ambiguous injection | Boot auto-config and manual bean definition coexist | Remove duplicate configuration, set `@Primary` or `@Qualifier` if truly needed |
| `@Size` does not catch null | Size constraints treat null as valid by default | Combine with `@NotNull`/`@NotBlank` |
| Nested object is not validated | Forgot `@Valid` on the nested field | Add cascading `@Valid` and test nested paths |
| Validation groups return fewer errors than expected | Only a non-`Default` group was selected | Check group declarations and activation |
| Message keys are not interpolated | Missing resource bundle or misconfigured `MessageSource`/provider | Check base name, locale, interpolation, and fallback |
| Standalone custom validator test passes but MVC differs | MVC uses a different validator config, or test does not load context | Test with Spring ApplicationContext and `MockMvc` |
| Validation is unusually slow | Repeated factory creation, heavy DB/I/O inside constraints | Share validator bean, optimize lookup policies |
| Concurrent requests corrupt custom constraint logic | ConstraintValidator holds mutable request state | Keep `isValid` stateless and dependencies thread-safe |

**Diagnose in order:** (1) is a provider present? (2) does Spring have the right `LocalValidatorFactoryBean` bean? (3) does the entry point actually invoke validation? (4) do constraints have the right annotations/types/groups? (5) do the custom `ConstraintValidatorFactory` and injection work? (6) which validator is Spring MVC using? (7) are conversion errors being confused with validation errors?

## 15. Self-Check

**1. Is adding only `jakarta.validation-api` enough for `@NotBlank` to run?** No. The API describes constraints; you need a compatible provider and an entry point invoking validation.

**2. Why can both `jakarta.validation.Validator` and `org.springframework.validation.Validator` be injected from the same Spring bean?** Because `LocalValidatorFactoryBean` implements/provides both the Jakarta API and the Spring adapter; it converts Jakarta violations into `Errors` when called through the Spring interface.

**3. Where does `@Autowired` inside a custom `ConstraintValidator` come from?** From `SpringConstraintValidatorFactory`, configured by default by `LocalValidatorFactoryBean`, which uses the Spring bean factory.

**4. Should you create `Validation.buildDefaultValidatorFactory()` on every request instead of using the Spring bean?** No: it wastes resources and bypasses Spring's configuration/injection unless manually reconfigured.

**5. Does `@Valid` on an `Address` field make a null field an error?** No; `@Valid` only cascades when an object is present. Combine with `@NotNull` to enforce presence.

**6. Does `@Validated(OnCreate.class)` always run all constraints belonging to `Default`?** No. It depends on group selection and explicit group relationships.

**7. Why should you not assert on the first element of `Set<ConstraintViolation>`?** Because ordering is not guaranteed by the API; assert by path, constraint, or message.

**Remember:** `LocalValidatorFactoryBean` is **a Spring bean that initializes and connects the provider**, allowing **one unified Bean Validation foundation** across Jakarta, Spring Binding, MVC, and custom constraints with dependency injection.

## Official Documentation

- Spring Framework Reference — Java Bean Validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring Framework Reference — Spring Validation: https://docs.spring.io/spring-framework/reference/core/validation/validator.html
- Spring Framework Reference — MVC Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/validation.html
- Spring Framework Reference — MVC Validation & Method Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework API — LocalValidatorFactoryBean: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html
- Spring Framework API — SpringConstraintValidatorFactory: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/beanvalidation/SpringConstraintValidatorFactory.html
- Jakarta Validation specification: https://jakarta.ee/specifications/bean-validation/
- Hibernate Validator documentation: https://hibernate.org/validator/documentation/
