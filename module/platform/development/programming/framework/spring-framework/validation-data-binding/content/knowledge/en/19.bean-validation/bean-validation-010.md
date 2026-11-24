# Annotations Take Effect Only When Validation Is Invoked (Bean Validation in Spring)

## 1. Meaning of This Principle

When writing a DTO, entity, or Java bean like this:

```java
public class RegisterRequest {
    @NotBlank
    private String username;

    @Email
    private String email;
}
```

annotations like `@NotBlank` and `@Email` **describe data validation rules**. They do not run automatically when a constructor is called, do not passively watch every setter mutation, and do not by default prevent creating an invalid object.

For constraints to be **enforced**, a **validation invocation mechanism** must exist: a direct call such as `jakarta.validation.Validator.validate(object)`, a `DataBinder.validate()` call with a configured validator, a Spring MVC entry point with appropriate `@Valid`/`@Validated`, or Spring's method validation interceptor when actually passing through a Spring proxy.

Rule to remember:

> **Annotations are constraint-declaring metadata. A validation engine or integration mechanism must be invoked for constraints to be evaluated.**

In Bean Validation, having an annotation on a field does not mean the object is always in a valid state. Calling `new RegisterRequest()`, assigning fields via setters, or receiving JSON data are all object-creation/assignment operations; **validation is a separate step** when an entry point triggers it.

## 2. Four Components to Distinguish

| Component | Responsibility | Examples |
| --- | --- | --- |
| **Constraint annotation** | Declares data conditions | `@NotNull`, `@NotBlank`, `@Size`, `@Email`, `@Min` |
| **Cascade marker** | Requests validating nested objects *when a validation pass occurs* | `jakarta.validation.Valid` |
| **Validation engine** | Reads metadata, executes `ConstraintValidator`s, and returns violations | Hibernate Validator provider; `jakarta.validation.Validator` |
| **Trigger/integration** | Decides **when** to ask the engine to run | `validator.validate(...)`, Spring MVC `@Valid`, `DataBinder.validate()`, method validation proxy |

`@Validated` is a Spring annotation supporting **validation groups** and, when placed at the type level with appropriate configuration, marks a Spring bean eligible for **method validation** via interceptor/proxy. It does not turn a Java object created with `new` into a self-validating object.

### Core Processing Flow

```text
new DTO / setter / JSON deserialize / form bind
                  |
            Data present in bean
                  |
       Is there a validation trigger?
           /                 \
          NO                 YES
           |                   |
 Constraints do not run    Spring/API calls Validator
           |                   |
  Object may be invalid    Provider checks metadata
                               |
                    ConstraintViolation / Errors
                               |
                  Controller/service handles errors
```

**Having a validator on the classpath is a capability condition, not an execution condition.** You need a compatible provider (e.g., Hibernate Validator) *and* an actual validation invocation.

## 3. Which Situations Actually Run Validation?

| Situation | Automatically Runs Bean Validation? | Why |
| --- | --- | --- |
| `new User("", ...)`, setter, or builder setting fields | **No** | Only constructs/populates the object |
| Field has `@NotBlank`, no validation code | **No** | Annotation is just metadata |
| `validator.validate(user)` with active provider | **Yes** | Direct call to validation API |
| `validator.validateProperty(user, "name")` | **Yes**, for the selected property | Explicit caller command |
| `DataBinder.bind(values)` | **Does not guarantee Bean Validation** | Binding and validation are two steps |
| `binder.setValidator(v); binder.validate()` | **Yes** | Validator is set and invoked |
| Spring MVC `@Valid @RequestBody Dto dto` | **Yes** if MVC validation is configured and parameter is eligible | Argument resolver triggers check |
| Spring MVC `@Valid @ModelAttribute Form form` | **Yes** in supported processing flow | Binder/argument resolver checks |
| Spring MVC with only `@RequestBody Dto dto` | **Not via `@Valid`**, since it wasn't requested | Deserialization is not validation |
| Spring MVC `@RequestParam @Min(1) int page` | **Yes** in MVC supporting method validation | Constraint placed directly on parameter |
| Spring-managed service `@Validated` + `@NotBlank` param + call via proxy | **Yes** when method validation is enabled | Interceptor calls provider |
| Manually calling `new Service().method(...)` despite class `@Validated` | **Not automatically** | Bypasses Spring proxy |
| Internal method calling `this.otherMethod(...)` on a regular service proxy | **Normally bypasses interceptor** | Self-invocation bypasses proxy |
| `@Valid` on nested field, without validating parent object | **No** | Cascade runs only during a validation pass |
| JPA entity having `@NotNull` before calling `persist` | **Not from the annotation alone** | ORM callbacks are configurable integrations, not instant assignment checks |

Note: in certain integrations (Spring Boot configuration properties, JPA lifecycle, Spring MVC, method validation), the framework **can** invoke the validator automatically at configured entry points. That does not mean you must write `validate()` manually everywhere; rather, you must know which **specific entry point** is running.

## 4. Complete Java 17+ Example: Difference Between Annotations and Validation Calls

The example runs with Spring Boot 3.5, Java 17, and Maven. It demonstrates in sequence:

1. Constructing an invalid object while the constructor still completes.
2. Calling Jakarta `Validator.validate(...)` and getting **two violations**.
3. Omitting `@Valid` on a nested property so constraints in the child object **are not traversed**.
4. Using Spring `DataBinder.validate()` so errors land in `BindingResult`.
5. Calling a service through a `@Validated` Spring bean so method parameters are validated.

Structure:

```text
annotation-validation-demo/
├── pom.xml
└── src/main/java/demo/AnnotationValidationDemo.java
```

### `pom.xml`

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

    <groupId>demo</groupId>
    <artifactId>annotation-validation-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-validation` provides Jakarta Validation/provider integration; `spring-boot-starter-aop` ensures proxy/AOP support for the service example. Spring Boot enables method validation for Spring-managed beans when a compatible provider is present. You do not need to create a `ValidatorFactory` per request.

### `src/main/java/demo/AnnotationValidationDemo.java`

```java
package demo;

import jakarta.validation.ConstraintViolationException;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.validation.DataBinder;
import org.springframework.validation.annotation.Validated;

@SpringBootApplication
public class AnnotationValidationDemo {

    public static void main(String[] args) {
        SpringApplication.run(AnnotationValidationDemo.class, args);
    }

    @Bean
    BookingService bookingService() {
        return new BookingService();
    }

    @Bean
    ApplicationRunner demonstrate(
            jakarta.validation.Validator jakartaValidator,
            org.springframework.validation.Validator springValidator,
            BookingService service) {

        return args -> {
            Registration invalid =
                    new Registration("", new Contact(""));

            // new only creates the object. No validation call yet.
            System.out.println("Constructed: no automatic validation");

            long errors = jakartaValidator.validate(invalid).size();
            System.out.println("Jakarta violations: " + errors);

            // Missing @Valid on contact field => inner constraints not checked.
            WithoutCascade noCascade =
                    new WithoutCascade(new Contact(""));
            System.out.println("Without cascade: "
                    + jakartaValidator.validate(noCascade).size());

            DataBinder binder = new DataBinder(invalid);
            binder.setValidator(springValidator);
            binder.validate(); // Explicit validation invocation.
            System.out.println("Spring binder errors: "
                    + binder.getBindingResult().getErrorCount());

            System.out.println("Service valid: " + service.book("OK"));
            try {
                // Call via Spring proxy, not new BookingService().
                service.book("");
            } catch (ConstraintViolationException ex) {
                System.out.println("Service violations: "
                        + ex.getConstraintViolations().size());
            }
        };
    }

    public static class Registration {
        @NotBlank
        private final String username;

        @Valid
        private final Contact contact;

        Registration(String username, Contact contact) {
            this.username = username;
            this.contact = contact;
        }

        public String getUsername() {
            return username;
        }

        public Contact getContact() {
            return contact;
        }
    }

    public static class Contact {
        @NotBlank
        private final String email;

        Contact(String email) {
            this.email = email;
        }

        public String getEmail() {
            return email;
        }
    }

    public static class WithoutCascade {
        // Intentionally omitting @Valid here.
        private final Contact contact;

        WithoutCascade(Contact contact) {
            this.contact = contact;
        }

        public Contact getContact() {
            return contact;
        }
    }

    @Validated
    public static class BookingService {
        public String book(@NotBlank String code) {
            return "booked";
        }
    }
}
```

Run in the project directory:

```bash
mvn spring-boot:run
```

Alongside Spring Boot's startup logs, the lines printed by the program itself in order are:

```text
Constructed: no automatic validation
Jakarta violations: 2
Without cascade: 0
Spring binder errors: 2
Service valid: booked
Service violations: 1
```

**Why does it produce these results?**

- `new Registration("", new Contact(""))` does not throw an exception merely because of annotations. At this point there are **two blank values**, yet nothing has requested validation.
- `jakartaValidator.validate(invalid)` invokes the provider; `@NotBlank` on `username` fails, `@Valid` takes the provider to `Contact.email` and finds the second `@NotBlank` → **2** violations. The count is deterministic in this model because each field has exactly one constraint and both values are invalid.
- `WithoutCascade` holds an empty `Contact` without marking the field with `@Valid`, so validating the parent object does not descend into the child object → **0** violations.
- `DataBinder` only runs validation when we call `binder.validate()`. The Spring `Validator` translates the two violations into errors on `BindingResult` → **2**.
- `BookingService` is a Spring bean annotated with `@Validated`; calling `service.book("")` through the configured method-validation proxy violates `@NotBlank` on the parameter. By default the Spring interceptor throws `ConstraintViolationException` → **1**.
- Replacing `service` with `new BookingService()` bypasses the interceptor. The class and parameter still carry annotations, yet there is no proxy invoking validation.

**Example scope:** requires Spring Boot 3.x, Java 17, Maven, and the listed dependencies; the listed stdout covers only the application's `System.out.println` lines, excluding framework logs. In plain Spring Framework (without Boot), you must configure `LocalValidatorFactoryBean` and `MethodValidationPostProcessor` per project setup.

## 5. Manual Invocation via Jakarta `Validator`

Jakarta Validation provides `jakarta.validation.Validator`; common operations:

```java
Set<ConstraintViolation<Registration>> violations =
        validator.validate(registration);
```

This is an **illustrative snippet**, requiring a `validator` variable from the Spring context, the `Registration` class, and matching Jakarta imports. `validate` returns a `Set` of violations; **it does not automatically throw an exception when constraints fail**. The caller must check `isEmpty()` and decide whether to return errors, throw an exception, or reject processing.

Useful APIs:

- `validate(bean, groups...)`: validates bean constraints for the specified groups; if unspecified, uses `Default`.
- `validateProperty(bean, "name", groups...)`: validates constraints on one specific property; **does not cascade** into that property's object.
- `validateValue(SomeBean.class, "name", proposedValue, groups...)`: tests a proposed value without needing a bean instance; does not cascade.
- `getConstraintsForClass(...)`: inspects constraint metadata without running validation.
- `forExecutables()`: API for explicitly validating method/constructor parameters and return values.

Error-detection example:

```java
Set<ConstraintViolation<Registration>> violations =
        validator.validate(registration);

if (!violations.isEmpty()) {
    String paths = violations.stream()
            .map(v -> v.getPropertyPath().toString())
            .sorted()
            .collect(java.util.stream.Collectors.joining(", "));
    throw new IllegalArgumentException(
            "Invalid registration fields: " + paths);
}
```

The snippet above **is not a standalone program**: it needs imports for `java.util.Set` and `jakarta.validation.ConstraintViolation`, assuming `validator` and `registration` already exist. For the invalid registration above, the message lists paths in sorted order such as `contact.email, username`.

**Note on tests:** element iteration order in `Set<ConstraintViolation<?>>` is not guaranteed by the API. When asserting output, sort by property path or assert against a set of paths rather than relying on the "first violation".

## 6. Spring `DataBinder`: Binding Data Does Not Mean Validating

`DataBinder`/`WebDataBinder` is responsible for mapping input data onto Java properties according to conversion and binding configuration. Spring lets you register a Spring `Validator`, where `LocalValidatorFactoryBean` can act as an adapter to Jakarta Validation.

```java
DataBinder binder = new DataBinder(target);
binder.setValidator(springValidator);

binder.bind(new MutablePropertyValues(
        java.util.Map.of("username", "")));

// This is the point that actually triggers registered validation:
binder.validate();

BindingResult result = binder.getBindingResult();
System.out.println(result.hasErrors());
```

This is an **illustrative excerpt**, assuming `target` has a writable `username` property and `springValidator` supports target's class and is configured. Requires importing `org.springframework.validation.DataBinder`, `BindingResult`, and `org.springframework.beans.MutablePropertyValues`.

- `binder.bind(...)` can produce *binding/type-conversion errors* when values cannot be converted to target types.
- `binder.validate()` invokes registered validators, adding *validation errors*.
- `BindingResult` collects both binding and validation errors; do not assume every `FieldError` necessarily came from Jakarta `@NotBlank`.
- Calling `binder.setValidator(...)` without calling `binder.validate()` in direct API usage **has not** executed validation yet. Spring MVC performs this step on behalf of the application at supported entry points.

To check additional business rules using a custom Spring `Validator`, combine it with the global validator via `addValidators(...)` in the right context. Do not accidentally replace the Bean Validation validator and lose Jakarta constraint enforcement.

## 7. Spring MVC: When Do `@Valid` and `@Validated` Trigger?

### `@RequestBody`: JSON deserialization first, validation second

Example REST controller in Spring MVC (this is an **illustrative snippet**, requiring Spring MVC/Jakarta imports and an appropriate `RegistrationRequest` class):

```java
@PostMapping("/registrations")
public ResponseEntity<?> register(
        @Valid @RequestBody RegistrationRequest request,
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

When Spring MVC processes the request:

1. `HttpMessageConverter` (typically Jackson) reads JSON and constructs the DTO.
2. The argument resolver detects `@Valid` or `@Validated` on the supported parameter.
3. The MVC-configured validator evaluates constraints on the DTO.
4. Violations are placed into `BindingResult`, or lead to an exception when the controller does not accept errors at the permitted position.
5. The controller or a global exception handler determines the HTTP response.

**`BindingResult`/`Errors` must appear immediately after the validated parameter** so Spring can pass errors to the method in supported scenarios. Without a matching `BindingResult`, in MVC 6.1+ scenarios validating only an object argument normally throw `MethodArgumentNotValidException`; when constraints sit directly on method parameters, *method validation* can be used instead, throwing `HandlerMethodValidationException`. Exception types and applicability depend on method signature, parameter types, and configuration.

If you omit `@Valid` from `RegistrationRequest` on the `@RequestBody` parameter and have no other trigger, blank data can still be deserialized into the DTO without checking Bean Validation constraints.

**Do not confuse JSON errors with Bean Validation errors:** malformed JSON syntax, un-deserializable fields, or invalid enum values can fail **before** validation ever gets a chance to run. Catching only `MethodArgumentNotValidException` does not cover all request body errors.

### `@ModelAttribute`: form/query object

```java
@PostMapping("/profiles")
public String save(
        @Valid @ModelAttribute("profile") ProfileForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return "profile-form";
    }
    return "redirect:/profiles";
}
```

This is an **illustrative method snippet**, requiring form/controller classes and imports. Spring binds fields onto `ProfileForm` and then runs validation because of `@Valid`; errors go into `BindingResult` immediately after the parameter. A form with field annotations whose controller lacks `@Valid`/`@Validated` **is not guaranteed** to run Bean Validation merely from binding.

### Constraints placed directly on parameters

```java
@GetMapping("/products")
public List<Product> list(@RequestParam @Min(1) int page) {
    return productService.findPage(page);
}
```

This is an **illustrative snippet** using application `Product` and `productService`. In Spring MVC 6.1+ supporting built-in method validation, `@Min(1)` directly on the parameter is a constraint and can cause MVC to perform method validation. `@Valid` alone **is not a constraint annotation**, so by itself it does not trigger this style of method validation; it is a marker requesting object cascading when a validation pass runs.

Spring Framework notes: for new controllers using built-in MVC method validation, **do not put `@Validated` at the controller class level unless you need legacy AOP method validation**. Class-level `@Validated` can route method validation through a proxy, resulting in different handling from the built-in mechanism.

## 8. Spring Services: `@Validated` Requires a Proxy and Method Validation Infrastructure

Bean Validation of **service method arguments** is not enabled simply by writing:

```java
@Service
public class OrderService {
    public void create(@NotBlank String orderCode) {
        // logic
    }
}
```

This is an **illustrative class**; without a method-validation interceptor or manual check call, `@NotBlank` on the `orderCode` parameter remains mere metadata.

Configuration in plain Spring Framework:

```java
@Configuration
public class MethodValidationConfig {

    @Bean
    public static MethodValidationPostProcessor methodValidationPostProcessor() {
        return new MethodValidationPostProcessor();
    }
}
```

In Spring Boot, method validation is normally auto-enabled when a Bean Validation provider is present. Still, the target bean must be annotated with `@Validated` at the type level to be eligible for Spring-driven method validation:

```java
@Service
@Validated
public class OrderService {

    public void create(@NotBlank String orderCode) {
        // When invoked via a Spring proxy with the interceptor,
        // a blank orderCode will fail validation.
    }
}
```

Both snippets above are **illustrative classes for a Spring project**, requiring imports for `@Configuration`, `@Bean`, `@Service`, `@Validated`, `@NotBlank`, and `MethodValidationPostProcessor`.

Practical limits:

- Calling through a Spring bean/proxy, such as a service injected into a controller, gives the interceptor a chance to validate.
- Manually calling `new OrderService()`, using objects outside Spring, or calling methods via `this` inside the same bean normally **bypasses the proxy**.
- With standard AOP proxies, methods that cannot be proxied/advised (such as many `private`/`final` methods) should not be relied on for validation interception.
- If an application defines `@Bean MethodValidationPostProcessor` manually, check existing configuration so you do not create duplicate processing or unexpected proxies.
- By default, method validation violations from Spring's interceptor typically become `ConstraintViolationException`. You can configure adaptation to `MethodValidationException` in Spring versions/APIs that support it.
- Enabling method validation for **service classes** differs from automatic command-object validation in **MVC controllers**.

### Self-invocation: a hard-to-spot bug

```java
@Validated
@Service
public class AccountService {

    public void register() {
        updateEmail(""); // Internal call may bypass the AOP proxy.
    }

    public void updateEmail(@NotBlank String email) {
        // ...
    }
}
```

This snippet **is not a standalone program**. A call `accountService.updateEmail("")` from another bean through the proxy can be intercepted; a direct `updateEmail("")` call inside the same instance usually bypasses advice. Extract responsibility to another bean, invoke across a true public Spring-managed boundary, or place explicit validation where the invariant must hold. Do not rely on annotations as the sole safeguard for invariants on unproxied call paths.

## 9. `@Valid`, `@Validated`, and Groups: Similar Names, Different Effects

| Syntax | Role | Automatically Triggers a Validation Pass? |
| --- | --- | --- |
| `@NotNull`, `@NotBlank`, `@Size`, `@Email` | Declares constraints | No |
| `@Valid` on nested field | Cascades when parent object is validated | No |
| `@Valid` on supported Spring MVC parameter | Instructs MVC to validate DTO | Yes, because MVC integration calls the engine |
| `@Validated` on MVC DTO parameter | Requests validation, selects groups when needed | Yes in supported MVC flows |
| `@Validated` at Spring service class level | Marks bean for method validation proxy | Only when interceptor/proxy is configured and actually traversed |
| `@Validated(SomeGroup.class)` | Selects validation group | Only at the corresponding trigger point |

Groups example:

```java
public interface OnCreate {}

public class UserInput {
    @NotBlank(groups = OnCreate.class)
    private String password;

    @NotBlank
    private String displayName;
}
```

When `validator.validate(user)` omits groups, the engine uses `Default` and checks `displayName`; `password` belongs only to `OnCreate`, so it does not run. When calling `validator.validate(user, OnCreate.class)`, constraints in `OnCreate` run; `Default` is not added automatically unless an appropriate group relationship exists. Spring MVC can select `OnCreate` via `@Validated(OnCreate.class)` on the command object parameter.

**An annotation may show no errors** because its group was not selected, not necessarily because the provider is broken. Check **trigger**, **group selection**, and **cascade paths** together.

## 10. Nested Validation: Why `@Valid` Cannot Be Omitted

```java
public class Checkout {
    @NotNull
    @Valid
    private Address address;
}

public class Address {
    @NotBlank
    private String city;
}
```

This is an **illustrative model**. When validating `Checkout`:

- If `address == null`, `@NotNull` reports an error; `@Valid` does not turn null into an error.
- If `address != null` but `city == ""`, `@Valid` tells the provider to descend into `Address` and catch `@NotBlank` on `city`.
- If `@Valid` is missing on `Checkout.address`, calling `validate(checkout)` does not automatically check `Address.city`'s constraint merely because an object reference exists.
- If `Checkout` is only constructed without calling validation, **neither `@NotNull` nor the `@Valid` cascade has been evaluated**.

Cascaded validation also applies to container elements per Jakarta Validation capabilities (e.g., `List<@Valid Address>` and container element constraints), subject to provider value extractors and group propagation rules. Do not assume that writing `List<Address>` will cause the provider to check each element automatically when cascade metadata is missing.

## 11. Custom `ConstraintValidator`: `isValid(...)` Runs Only When the Provider Reaches the Constraint

Custom annotation example:

```java
@Target({ElementType.FIELD, ElementType.PARAMETER})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = PrefixValidator.class)
public @interface HasPrefix {
    String message() default "prefix invalid";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
```

And implementation:

```java
public final class PrefixValidator
        implements ConstraintValidator<HasPrefix, String> {

    @Override
    public boolean isValid(
            String value, ConstraintValidatorContext context) {
        return value == null || value.startsWith("VN-");
    }
}
```

Both snippets are **illustrative code**, requiring separate properly named files and imports for `java.lang.annotation.*` and `jakarta.validation.*`; the application must have a provider. Even though `@HasPrefix` is attached to a field, `isValid(...)` is invoked by the provider only if that field participates in **an actual validation pass**, according to the active group and cascade paths.

- In Spring, `LocalValidatorFactoryBean` normally bootstraps the provider and uses `SpringConstraintValidatorFactory` to support dependency injection into constraint validators.
- If the class/constraint is not part of the validation pass, `ConstraintValidator` does not run even if it can be Spring-managed or provider-instantiated.
- Having a custom validator call DBs/services is logic that must be controlled; avoid placing significant side effects inside `isValid(...)`, because the framework may validate multiple times or in an unspecified order.
- Some providers may reuse `ConstraintValidator` instances; avoid storing mutable per-request state in potentially shared instances.

## 12. Other Integrations That May Invoke Validation for You

### `@ConfigurationProperties` in Spring Boot

Spring Boot can validate configuration beans bound from properties/YAML when the bean is annotated with `@Validated` and a compatible provider is on the classpath, per Boot's binding/startup rules. This is a **dedicated entry point** in the application lifecycle, not an effect of `@NotNull` on arbitrary objects.

### JPA entity lifecycle

With JPA/Hibernate ORM and Bean Validation integration enabled, the provider may be invoked at lifecycle events such as `pre-persist`/`pre-update`. However:

- Do not assume entities are validated on `new Entity()`.
- Do not treat `repository.save(entity)` in every persistence technology as a guarantee that validation has already occurred.
- When JPA validates at flush/commit, the exception can happen **later** than the `save(...)` call.
- Group/lifecycle semantics and whether validation runs at all depend on provider, persistence configuration, and transactions.

### Testing, messaging, batch jobs, scheduled jobs

A DTO received from a queue, file import, unit test, or scheduled job **is not automatically** validated just because it has annotations. Pipeline authors must place explicit `Validator.validate(...)` calls or configure clear integration points. Spring MVC does not "cover" data created in other business flows by default.

## 13. Common Misconceptions

| Symptom | Wrong Assumption | Root Cause / Resolution |
| --- | --- | --- |
| `new User()` still accepts `name=""` | "`@NotBlank` is broken" | No validation pass has occurred; call validator or go through Spring MVC properly |
| REST accepts JSON missing a field | "Annotations mean Spring must block it" | Missing `@Valid`/`@Validated` on parameter or MVC validator is unconfigured |
| Calling `service.create("")` throws no error | "`@NotBlank` on method doesn't work" | Missing `@Validated`, missing post-processor/proxy, internal self-call, or manual `new` |
| Child object is invalid yet no error appears | "Bean Validation doesn't read child annotations" | Missing `@Valid` on the relation/cascade |
| Null argument is not flagged by `@Email` | "Constraint wasn't invoked" | Many format constraints allow null; pair with `@NotNull`/`@NotBlank` when required |
| Grouped constraint does not run | "Annotation wasn't recognized" | Active group differs from the group declared on the annotation |
| No `FieldError` created after binding | "Binder calls validator automatically" | After binding, you must call `binder.validate()` when using the API directly |
| Only `jakarta.validation-api` present and startup fails | "Annotations don't work" | Missing a compatible Bean Validation provider |
| Inconsistent switch from `javax.validation.*` to `jakarta.validation.*` | "Provider understands both automatically" | Must align Spring/Boot/API generation and dependencies |
| JSON parse error appears before constraint | "Validator was skipped" | Deserialization failed to build the DTO for validation |
| Expecting method validation to always throw HTTP 400 | "All validation errors share one handler" | MVC object, MVC method, service AOP, and manual APIs use different error mechanisms |
| Testing `@Valid` via unit test doing `new` on controller | "Test proves endpoint doesn't validate" | Test must invoke via MVC infrastructure or call Validator directly |

Do not rely on `@NotNull` or `@Validated` as the sole mechanism protecting data across all paths. Validation is an input barrier at **specific invocation points**; critical invariants still require checks at business boundaries, database constraints, or appropriate domain rules.

## 14. Distinguishing *Validation Not Invoked* vs *Validation Invoked With No Errors*

Before editing code, check in order:

1. **Is a provider present?** Do Maven/Gradle include both the Bean Validation API and a compatible provider? For Spring Boot 3+/Framework 6+, use `jakarta.validation.*`.
2. **Is there an entry point?** Which of `Validator.validate(...)`, `DataBinder.validate()`, Spring MVC `@Valid`/`@Validated`, method-validation proxy, JPA lifecycle, or Boot binder is actually running?
3. **Which object is validated?** Are field annotations on the DTO/bean received by the entry point, or on a different object constructed earlier?
4. **Right constraint type?** `@Email` normally accepts null; `@Size` likewise does not replace `@NotNull`. For numbers, use constraints compatible with the type.
5. **Cascading and groups?** Is `@Valid` present on nested paths? Are `Default`/`OnCreate` groups activated?
6. **Service proxy?** Is the bean Spring-managed or created via `new`? Is `@Validated` at type level? Can the method be advised by the interceptor? Is there self-invocation?
7. **Inspecting the right output?** Jakarta API returns `Set<ConstraintViolation>`; Spring binder writes `BindingResult`; MVC may throw exceptions; not all automatically throw the same error.
8. **Earlier failure?** JSON parsing, type conversion, or binding can fail before constraint validation.
9. **Testing the right entry point?** Use `MockMvc` for MVC, inject the real service from `ApplicationContext` for method-validation proxies, and call `Validator` directly for the validation engine.

### Testing Strategy

For services and DTOs, three separate tests can exist:

- **DTO/engine test:** inject `jakarta.validation.Validator`, call `validate(new UserInput(...))`, assert the set of violation property paths. This verifies constraint metadata + provider.
- **MVC test:** use `MockMvc` to send an invalid request to the real endpoint, asserting HTTP response/`BindingResult` per contract. This verifies annotations are in the right place *and* MVC has a trigger.
- **Service method test:** inject the `@Validated` bean from the Spring context and call the method with invalid arguments; assert exception or error result per configuration. Do not instantiate the service with `new` when testing the AOP trigger.

Having all three separate tests distinguishes "constraints work" from "the integration mechanism actually invoked the constraints".

## 15. Self-Check Questions

**Question 1.** A Java record has `@NotBlank` on `name`; does calling `new Person("")` automatically throw `ConstraintViolationException`?  
**Answer:** Not from the annotation alone. You need explicit constructor validation code or another validation call/entry point.

**Question 2.** A service uses `@Validated` and a method has `@NotBlank`, yet `this.method("")` is called from the same service—what happens?  
**Answer:** With standard Spring AOP proxies, internal calls bypass the proxy and may not be validated.

**Question 3.** A DTO in `@RequestBody` has `@NotBlank`; why put `@Valid` on the controller parameter?  
**Answer:** To instruct Spring MVC to invoke the validator after binding/deserialization succeeds, within supported mechanisms.

**Question 4.** Does `@Valid` on an `Address` field run when the parent object has not been validated?  
**Answer:** No. It only requests cascading when a validation pass occurs.

**Question 5.** Does `validator.validate(dto)` throw an exception automatically if violations exist?  
**Answer:** Not under the standard Jakarta API; it returns `Set<ConstraintViolation<T>>` and the caller handles it.

**Question 6.** Does `@NotNull` on an entity guarantee the object can never hold null?  
**Answer:** No. It is evaluated only when Bean Validation is invoked; database constraints are a separate layer.

**Question 7.** To verify a Spring service proxy actually works, should you test with `new` or a bean injected from the context?  
**Answer:** A bean injected from the context and invoked across a public boundary with the interceptor.

**Takeaway to remember:** **Writing constraints declares rules; invoking the right validation mechanism enforces rules.** Clearly identify *who calls, where, when, on which object, and with which groups*.

## Official References

- Spring Framework Reference — Bean Validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring Framework Reference — Spring Validation and DataBinder: https://docs.spring.io/spring-framework/reference/core/validation/validator.html
- Spring Framework Reference — Spring MVC Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework Reference — Global MVC Validator: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/validation.html
- Spring Boot Reference — Validation and method validation: https://docs.spring.io/spring-boot/reference/io/validation.html
- Spring API — `@Validated`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/annotation/Validated.html
- Jakarta Validation specification: https://jakarta.ee/specifications/bean-validation/
