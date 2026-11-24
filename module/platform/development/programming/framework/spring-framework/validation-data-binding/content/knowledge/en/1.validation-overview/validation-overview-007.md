# Distinguishing Spring Validator, Jakarta Validation, and implementation libraries

## 1. Three concepts in three distinct roles

When an application receives a member registration object, we want to ensure `name` is non-empty and `age >= 18`. You may encounter `org.springframework.validation.Validator`, `jakarta.validation.Validator`, and Hibernate Validator in the same project. They are **not three synonymous APIs**:

- **Spring Validator**: an object validation contract provided by Spring Framework, centered around `supports(Class<?>)`, `validate(Object, Errors)`, and the `Errors`/`BindingResult` error model. Developers usually write validation rules themselves in Java.
- **Jakarta Validation** (also known as Jakarta Bean Validation): a **standard specification/API** defining constraint annotations such as `@NotBlank`, `@Min`, `@Valid`, as well as `jakarta.validation.Validator`, `ValidatorFactory`, and `ConstraintViolation`. The API defines how to request and receive validation results, without supplying the full execution engine itself.
- **Provider/implementation**: a library implementing Jakarta Validation, most commonly **Hibernate Validator**; another option is Apache BVal. The provider reads constraint metadata and actually evaluates objects. Hibernate Validator is **different from Hibernate ORM/JPA**.

The integration picture is typically:

```text
HTTP request -> deserialize / data binding -> Java object
                           |
                           +-> Spring WebDataBinder / Errors / BindingResult
                           |        ^ can invoke a custom Spring Validator
                           |        ^ or the LocalValidatorFactoryBean adapter
                           |
                           +-> Jakarta Validation API (Validator, constraints)
                                             |
                                             v
                                Provider (e.g., Hibernate Validator)
                                             |
                                             v
                                   ConstraintViolation
```

Spring Framework has a mechanism to **translate Jakarta Validation errors into Spring errors** when working with `BindingResult`. Thus an object annotated with Jakarta annotations is still handled naturally in Spring MVC.

## 2. Spring Validator: programmatic validation and Spring-style error recording

The `org.springframework.validation.Validator` interface has two core methods:

```java
public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);
}
```

- `supports` determines which target types this validator handles; it must match the type `DataBinder` will pass in.
- `validate` reads the object's state and records errors via `errors.reject(...)` for object-level errors or `errors.rejectValue("field", "error.code")` for field-level errors.
- `Errors` holds error codes, message arguments, and field details; `BindingResult` extends `Errors` to provide binding information and `FieldError`/`ObjectError`.
- `DataBinder` can register one or more validators and invoke `validate()`. In Spring MVC, `WebDataBinder` is used to bind request data and can be configured with `@InitBinder`.

Example of a rule not covered by built-in annotations:

```java
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public final class PasswordMatchValidator implements Validator {
    @Override
    public boolean supports(Class<?> type) {
        return SignupForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        SignupForm form = (SignupForm) target;
        if (form.getPassword() != null
                && !form.getPassword().equals(form.getConfirmPassword())) {
            errors.rejectValue(
                "confirmPassword", "password.mismatch",
                "Confirmation password does not match"
            );
        }
    }
}
```

*This snippet illustrates a validator and requires a `SignupForm` class with corresponding getters; a standalone runnable example is in Section 6.* Spring Validator suits complex rules, cross-field dependencies, or form/binding workflows, and cases where you want explicit control over error codes to resolve messages from `MessageSource`. A cross-field rule can also be implemented as a custom Jakarta constraint; the choice depends on how much reuse outside Spring is needed.

**Key takeaway:** the Spring `Validator` interface does not automatically scan `@NotBlank`/`@Min`. Processing those annotations is the job of a Jakarta Validation provider or an appropriate adapter.

## 3. Jakarta Validation: standard contract and declarative constraints

Key elements belong to the `jakarta.validation` and `jakarta.validation.constraints` namespaces:

| Element | Purpose |
| --- | --- |
| `@NotNull` | Value is not `null`; empty or whitespace-only strings are still valid. |
| `@NotBlank` | `CharSequence` must not be `null` and must contain at least one non-whitespace character. |
| `@NotEmpty` | String, collection, map, array… must not be `null` and must not be empty; whitespace-only strings can still pass. |
| `@Size(min, max)` | Valid length/size; does not replace `@NotNull`. |
| `@Min`, `@Max`, `@Positive`, `@Email`, `@Pattern` | Corresponding numeric, format, or regex rules; `@Email` does not replace checking whether an address actually exists. |
| `@Valid` | Requests cascading validation down into nested objects/elements at configured cascade points. |
| `@ConvertGroup`, `groups` | Selects/converts constraint groups across different scenarios. |
| `Validator#validate` | Executes validation through the provider and returns `Set<ConstraintViolation<T>>`. |

Example DTO:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record RegistrationRequest(
    @NotBlank String name,
    @Min(18) int age,
    @NotNull @Valid Address address
) {}

record Address(@NotBlank String city) {}
```

When the provider validates `RegistrationRequest`, `@Valid` enables checking `Address.city`. If `@Valid` is omitted on the `address` field, constraints inside `Address` will not automatically be traversed along that cascade path. `@Valid` **is not a null-check constraint**; therefore the example combines it with `@NotNull`. Constraints like `@NotBlank` and `@Min` do not take effect merely by appearing in code: an entry point must invoke validation, such as `jakarta.validation.Validator#validate`, Spring MVC triggering request validation, or a configured method validation mechanism.

The result of Jakarta Validation is a set of `ConstraintViolation` objects containing the property path (`getPropertyPath()`), message (`getMessage()`), invalid value (`getInvalidValue()`), constraint descriptor, etc. They are **not** Spring `FieldError` instances.

## 4. Provider: the library that actually evaluates constraints

`jakarta.validation-api` only defines the contract. **Hibernate Validator** is one provider of that contract: it reads annotation metadata, executes `ConstraintValidator` implementations, and returns results per the standard API. When running standalone, it can be bootstrapped via:

```java
try (jakarta.validation.ValidatorFactory factory =
         jakarta.validation.Validation.buildDefaultValidatorFactory()) {
    jakarta.validation.Validator validator = factory.getValidator();
    var violations = validator.validate(object);
}
```

The provider is discovered via Jakarta Validation's bootstrap mechanism. If only the API is present **without a valid provider on the runtime classpath**, `buildDefaultValidatorFactory()` will fail to build a factory (typically throwing `NoProviderFoundException`). In Spring Boot 3, `spring-boot-starter-validation` is the standard dependency that brings in the API along with a compatible provider, rather than adding just the API and expecting annotations to run by themselves.

A provider may offer extensions in its own namespace, such as `org.hibernate.validator.constraints`. Use standard `jakarta.validation.constraints` constraints whenever possible to avoid vendor lock-in. Do not assume the latest Hibernate Validator version is always compatible: pick the version managed by the Spring Boot BOM or check compatibility across Spring, Jakarta Validation, and the provider.

### Spring's adapter: LocalValidatorFactoryBean

`org.springframework.validation.beanvalidation.LocalValidatorFactoryBean` bridges the two worlds. It configures/initializes a Jakarta `ValidatorFactory` via the provider while also adapting to the `org.springframework.validation.Validator` contract, enabling Spring to convert `ConstraintViolation` instances into `Errors`/`BindingResult` when needed.

In a typical Spring MVC setup, when a Bean Validation provider is on the classpath, Spring can register `LocalValidatorFactoryBean` as the global validator. This explains why `@Valid @RequestBody` works in controllers and constraint errors can surface as `FieldError`s even though the DTO has no hand-written Spring Validator. **The adapter is not a provider**; it still requires an underlying implementation library.

## 5. Quick comparison

| Criterion | Spring Validator | Jakarta Validation | Provider (Hibernate Validator) |
| --- | --- | --- | --- |
| Nature | Spring API/contract | Jakarta standard specification and API | Library implementing the standard |
| Typical namespace | `org.springframework.validation.*` | `jakarta.validation.*` | `org.hibernate.validator.*` (plus Jakarta API) |
| Rule declaration | Java code in `validate` | Annotations or custom constraints | Reads and executes spec rules; has own extensions |
| Input | `Object` + `Errors` | Object + validation groups | Invoked via Jakarta API/adapter |
| Typical output | `FieldError`, `ObjectError` via `BindingResult` | `ConstraintViolation` | Produces violations per Jakarta contract |
| Depends on Spring? | Yes | No | Not required |
| Needs Jakarta provider? | No, if using only hand-written Spring rules | Yes, to execute the standard | Is itself the provider |
| When to choose | Form binding, custom business errors, needing Spring error codes | DTO/domain using declarative rules, cross-layer reuse | Choosing a compatible Jakarta Validation implementation |

Do not confuse the two identically named interfaces: `org.springframework.validation.Validator` **is different from** `jakarta.validation.Validator`. In a Java file using both, qualify the full package name where ambiguity arises; Java does not support import aliases.

## 6. Runnable Java 17 example: same data, two validation approaches

This example runs a **hand-written Spring Validator** and **Jakarta Validation via Hibernate Validator** on the same object. It uses Maven and JDK 17+, with no HTTP server startup required.

Structure:

```text
validation-comparison/
├── pom.xml
└── src/main/java/demo/ValidationComparisonDemo.java
```

File `pom.xml` (Spring Boot 3.3.5 manages the Java 17/Spring 6/Jakarta dependencies; versions are pinned here so the example is reproducible):

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
    <artifactId>validation-comparison</artifactId>
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

File `src/main/java/demo/ValidationComparisonDemo.java`:

```java
package demo;

import java.util.List;
import jakarta.validation.Validation;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.ValidationUtils;

public class ValidationComparisonDemo {

    public static final class Member {
        @NotBlank
        private final String name;

        @Min(18)
        private final int age;

        public Member(String name, int age) {
            this.name = name;
            this.age = age;
        }

        public String getName() {
            return name;
        }

        public int getAge() {
            return age;
        }
    }

    public static final class MemberSpringValidator
            implements org.springframework.validation.Validator {

        @Override
        public boolean supports(Class<?> type) {
            return Member.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            ValidationUtils.rejectIfEmptyOrWhitespace(
                errors, "name", "name.required"
            );
            Member member = (Member) target;
            if (member.getAge() < 18) {
                errors.rejectValue("age", "age.under18");
            }
        }
    }

    public static void main(String[] args) {
        Member member = new Member(" ", 16);

        // Flow 1: Spring validator -> BindingResult / FieldError.
        DataBinder binder = new DataBinder(member, "member");
        binder.addValidators(new MemberSpringValidator());
        binder.validate();
        List<String> springErrors = binder.getBindingResult()
            .getFieldErrors().stream()
            .map(error -> {
                String[] codes = error.getCodes();
                String baseCode = codes[codes.length - 1];
                return error.getField() + ":" + baseCode;
            })
            .sorted()
            .toList();
        System.out.println("Spring: " + springErrors);

        // Flow 2: Jakarta API -> provider -> ConstraintViolation.
        try (ValidatorFactory factory =
                 Validation.buildDefaultValidatorFactory()) {
            jakarta.validation.Validator validator = factory.getValidator();
            List<String> jakartaErrors = validator.validate(member).stream()
                .map(violation -> violation.getPropertyPath() + ":"
                    + violation.getConstraintDescriptor()
                        .getAnnotation().annotationType().getSimpleName())
                .sorted()
                .toList();
            System.out.println("Jakarta: " + jakartaErrors);
        }
    }
}
```

Run from the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ValidationComparisonDemo
```

The two lines printed by the program code (library logs, if any, may also appear):

```text
Spring: [age:age.under18, name:name.required]
Jakarta: [age:Min, name:NotBlank]
```

Explanation: both detect that `name` has only whitespace and `age` is less than 18. Spring returns errors with **developer-defined codes** (`age.under18`, `name.required`); Jakarta returns **violations tied to standard constraint types** (`Min`, `NotBlank`). In Spring, error codes after `MessageCodesResolver` may be expanded by object/field/type; the example intentionally takes the last element of `getCodes()` to display the stable base code.

## 7. In Spring MVC, where does each role participate?

With Spring Boot 3 + Spring MVC, `spring-boot-starter-web` is needed for controllers and `spring-boot-starter-validation` for the Bean Validation provider. This is an **illustrative controller snippet**, placed inside a configured Boot Web application; not the standalone program from Section 6:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

record CreateMemberRequest(@NotBlank String name, @Min(18) int age) {}

@RestController
class MemberController {
    @PostMapping("/members")
    ResponseEntity<Void> create(@Valid @RequestBody CreateMemberRequest request) {
        // Only processes when the request passes validation for this argument.
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
```

Typical flow:

1. Spring MVC reads JSON and converts it into `CreateMemberRequest` (deserialization/binding).
2. `@Valid` requests running Jakarta Bean Validation on the object; the `LocalValidatorFactoryBean` adapter delegates the work to the provider.
3. If there are violations and no `Errors`/`BindingResult` is placed right after that parameter, argument-level validation leads to `MethodArgumentNotValidException` (typically HTTP 400 under default MVC configuration).
4. To handle errors in the controller, place `BindingResult` **immediately after** the validated parameter, e.g., `create(@Valid @RequestBody CreateMemberRequest request, BindingResult errors)`, then check `errors.hasErrors()` and return an appropriate response.

**Further distinguishing method validation:** starting in Spring Framework 6.1, when a controller has constraints directly on method parameters/return values (such as `@RequestParam @Min(1) int page`), MVC's built-in method validation mechanism can apply and errors fall under `HandlerMethodValidationException`. It differs from validating a standard `@Valid @RequestBody` object. For controllers wanting this built-in MVC mechanism, avoid placing `@Validated` at the class level merely to enable validation because a class-level annotation switches to the AOP proxy path.

To add a custom Spring validator for a controller, you can register it via `@InitBinder`:

```java
@InitBinder("memberForm")
void initMemberBinder(WebDataBinder binder) {
    binder.addValidators(new MemberSpringValidator());
}
```

This snippet illustrates configuration inside a `@Controller` with a model attribute named `memberForm`, whose target type matches `supports`; import `org.springframework.web.bind.WebDataBinder` and `org.springframework.web.bind.annotation.InitBinder`. `addValidators` allows adding rules instead of replacing the global validator. Do not blindly apply a validator that only supports `Member` to a different DTO.

At the service layer, method validation uses Jakarta constraints, while evaluation can be triggered by Spring via `MethodValidationPostProcessor` and `@Validated` on beans invoked through an AOP proxy (Spring Boot can auto-configure this when conditions are met). Self-invocation from one method to another on `this` usually bypasses the proxy, so never assume method constraints are always checked. Outside Spring, you can use the Jakarta API to call `validator.validate(...)` explicitly.

## 8. Choosing the right solution per scenario

- **Request DTO with simple, reusable constraints:** use Jakarta constraints like `@NotBlank`, `@Size`, `@Min`; ensure a provider is present and validation is triggered.
- **Complex multi-field rules tied to Spring forms/binding:** consider writing a Spring `Validator` with `Errors` error codes; or a custom Jakarta class-level constraint if the rule should be Spring-independent.
- **Running validation outside Spring (batch jobs, Java SE, shared libraries):** depend on Jakarta API + compatible provider and call `Validator#validate`.
- **Spring Boot Web app wanting standard error handling:** use Jakarta annotations via `@Valid`/`@Validated`, handle `BindingResult` or appropriate exceptions; add Spring Validator only when genuinely needed.
- **Configuring error messages:** Jakarta has the `message` attribute/message interpolation; Spring has `MessageSource` and error-code resolution. Both mechanisms can be bridged through the adapter, though they are not identical.

## 9. Error-prone misconceptions

1. **Adding only `jakarta.validation-api` and expecting annotations to run.** The API does not replace a provider or a validation trigger. An implementation library and proper entry point are required.
2. **Confusing `@Valid` and `@Validated`.** `@Valid` is the Jakarta annotation for cascading/triggering validation where supported by the framework; `@Validated` is Spring's annotation supporting groups and method validation configuration. They are not two different providers.
3. **Confusing `javax.validation.*` with `jakarta.validation.*`.** Spring Framework 6 / Boot 3 uses Jakarta; Spring 5 / Boot 2 code typically uses the older namespace. Do not mix annotations, APIs, and providers across generations.
4. **Using `@NotNull` to forbid blank strings.** `@NotNull` only forbids null; to reject null/empty/whitespace strings, use `@NotBlank`.
5. **Thinking type conversion is validation.** Malformed JSON, unparseable numbers, or missing converters can fail before constraint validation runs and yield different error types. Distinguish binding/conversion errors from violations.
6. **Thinking `BindingResult` and `ConstraintViolation` are the same.** `BindingResult` is Spring's error model, which may contain both binding errors and constraint errors converted by the adapter.
7. **Unknowingly using provider-specific constraints.** `org.hibernate.validator.constraints.*` are not all part of the Jakarta standard; check portability and compatibility.
8. **Assuming every service call is automatically intercepted by method validation.** With AOP-based method validation, a proper bean/proxy and proxy-routed call are required; self-invocation can bypass it.
9. **Not placing `BindingResult` adjacent to the validated argument.** In flows supporting local error handling, parameter ordering affects how Spring MVC handles exceptions.
10. **Thinking Hibernate Validator is Hibernate ORM.** The two libraries serve different purposes; merely using Spring Data JPA/Hibernate ORM does not mean a Bean Validation provider is properly configured.

## 10. Self-check questions

- If a DTO only has `@NotBlank` but lacks a provider or nobody triggers validation, what happens?
- Why can `Spring Validator` run without depending on `Hibernate Validator`?
- Why does `LocalValidatorFactoryBean` still need a provider even though Spring registers it?
- Which scenarios yield `ConstraintViolation`, and which yield `BindingResult`?
- In Spring MVC 6.1+, when does the difference between `MethodArgumentNotValidException` and `HandlerMethodValidationException` appear?

**Conclusion:** Spring Validator is Spring's validation contract and error model; Jakarta Validation is the framework-independent standard for defining/checking constraints; Hibernate Validator is an implementation library for that standard. Spring uses an adapter to bridge them, so you can cleanly use both mechanisms within the same application when appropriate.

### References

- Spring Framework — Validation, Data Binding, and Type Conversion: https://docs.spring.io/spring-framework/reference/core/validation.html
- Spring Framework — Java Bean Validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring Framework — Spring MVC Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Hibernate Validator — Getting Started: https://hibernate.org/validator/documentation/getting-started/
