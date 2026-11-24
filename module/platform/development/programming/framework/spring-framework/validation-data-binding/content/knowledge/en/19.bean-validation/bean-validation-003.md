# Distinguishing `jakarta.validation.Validator` and Spring `Validator`

## 1. Why Does One Application Have Two `Validator`s?

Spring Framework supports both **Jakarta Bean Validation** (the Jakarta standard) and **Spring Validation** (Spring's own API). Both interfaces are named `Validator`, yet they do not share the same return type, way of writing rules, or error data type:

- `jakarta.validation.Validator`: evaluates **constraints** such as `@NotBlank`, `@Min`, `@Size` on an object and **returns `Set<ConstraintViolation<T>>`**.
- `org.springframework.validation.Validator`: checks an object using Java logic inside an implementation class and **records errors into `Errors`/`BindingResult`** provided by the caller.

For example, if registration requires a non-blank name and age at least 18: Jakarta can use `@NotBlank`, `@Min` annotations; Spring Validator can check inside `validate(...)` and call `errors.rejectValue(...)`.

Spring's special feature is that **`LocalValidatorFactoryBean` connects the two APIs**: it creates and manages the Jakarta provider while also allowing Jakarta results to surface as Spring errors for binding/forms. This lesson clarifies each interface's responsibilities and how to use them properly in Spring MVC.

## 2. Side-by-Side API Comparison Table

| Aspect | `jakarta.validation.Validator` | `org.springframework.validation.Validator` |
| --- | --- | --- |
| Ecosystem | Jakarta Validation, Spring-independent | Spring Framework |
| Constraint definition | Typically annotations and `ConstraintValidator` | Typically written directly in Java |
| Primary methods | `validate(T object, Class<?>... groups)` | `supports(Class<?>)`, `validate(Object, Errors)` |
| Return type on check | `Set<ConstraintViolation<T>>` | `void`; errors are added to `Errors` |
| Error details | Constraint, property path, message, invalid value | `FieldError`, `ObjectError`, code, message arguments |
| Validation groups | Has `groups`/`Default` and group sequences | Basic interface takes no groups; `SmartValidator` takes hints |
| Property-level validation | `validateProperty`, `validateValue` | Explicitly check/record field errors |
| Spring MVC integration | Via provider and Spring adapter | Via `DataBinder`/`WebDataBinder`/`BindingResult` |
| Runtime library needed? | Needs an execution provider, e.g., Hibernate Validator | Custom validator only needs Spring Validation |

**Note:** constraint-violating data **does not cause** Jakarta `validate(...)` to throw an exception by default; it returns a set of errors. Spring `validate(Object, Errors)` also does not automatically throw an exception on an invalid object; HTTP 400 or exception handling depends on the caller layer and configuration.

### Do not import the wrong interface

```java
// Two different packages, same short name Validator:
jakarta.validation.Validator beanValidator;
org.springframework.validation.Validator springValidator;
```

These are variable declarations to compare types. In a file that needs both, write the fully qualified names as above, or import only one type. Doing `import jakarta.validation.Validator` and then calling `supports(...)` will not compile because the Jakarta interface does not define that method.

## 3. Jakarta Bean Validation: Constraints, Violations, Groups

### 3.1. Creating declarative rules

A form/DTO typically places annotations on properties:

```java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public class SignupForm {

    @NotBlank(message = "name.required")
    private String name;

    @Min(value = 18, message = "age.tooYoung")
    private int age;

    // Constructor, getters/setters according to the application's binding approach
}
```

This is an **illustrative declaration snippet**, not a self-contained runnable Java file. `@NotBlank` rejects `null`, empty strings, and whitespace-only strings. `@Min(18)` checks that the number is at least 18. A constraint is executed by a provider (e.g., Hibernate Validator), not by `jakarta.validation-api` alone.

Calling the Jakarta interface:

```java
Set<ConstraintViolation<SignupForm>> violations =
        jakartaValidator.validate(form);
```

Each `ConstraintViolation<T>` can provide:

- `getPropertyPath()`: field/path, such as `name` or `address.city`.
- `getMessage()`: the interpolated message.
- `getMessageTemplate()`: the original message template.
- `getInvalidValue()`: the rejected value, which should not be logged or returned when it contains sensitive data.
- `getConstraintDescriptor()`: constraint metadata (annotation, attributes, groups...).
- `getRootBean()`: the root object, when available.

**`Set` does not guarantee ordering.** Do not default to treating the "first element" as the priority error in an API. If deterministic results are needed, sort by field/code.

Jakarta also provides:

```java
jakartaValidator.validateProperty(form, "name");
jakartaValidator.validateValue(SignupForm.class, "name", "");
jakartaValidator.getConstraintsForClass(SignupForm.class);
```

`validateProperty` checks the constraints of one property on an existing object; `validateValue` checks a hypothetical value without needing an object; `getConstraintsForClass` inspects metadata. The two property/value checking methods are not equivalent to validating the entire object graph/cascade.

### 3.2. Validation groups

By default, `jakartaValidator.validate(form)` runs constraints belonging to `jakarta.validation.groups.Default`. For a custom group:

```java
interface PublishChecks {}

Set<ConstraintViolation<SignupForm>> violations =
        jakartaValidator.validate(form, PublishChecks.class);
```

This snippet assumes constraints are annotated with `groups = PublishChecks.class`; if all constraints belong only to `Default`, calling a custom group does not mean they will still run. Group sequences and group inheritance are advanced mechanisms to consider separately.

When a model has nested objects and you want to cascade into the child object, mark the association with `@jakarta.validation.Valid`:

```java
@jakarta.validation.Valid
private Address address;
```

Putting only `@NotNull` on the `address` property does not automatically evaluate annotations inside `Address`. Jakarta Bean Validation also provides executable validation for method parameters and return values via `forExecutables()`.

## 4. Spring Validator: `supports`, `validate`, `Errors`

The Spring interface defines two core methods:

```java
public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, org.springframework.validation.Errors errors);
}
```

This is a condensed signature for study; when writing code, implement the actual `org.springframework.validation.Validator`.

`supports(Class<?>)` reports the object type the validator understands. `validate(Object, Errors)` performs the checking logic and records errors:

- `errors.rejectValue("name", "name.required")`: error bound to a specific field.
- `errors.reject("date.range.invalid")`: object-level error.
- `errors.hasErrors()`, `errors.getFieldErrors()`, `errors.getGlobalErrors()`: read recorded errors.

`Errors` is usually used via `BindingResult`, which adds support for data binding info, type conversion errors, and rejected field values. `FieldError` has an **error code**, field, and default message; the code can be resolved using Spring's `MessageSource`. Jakarta's `ConstraintViolation.getMessage()` is a message already interpolated by the Jakarta provider. You should not treat those two values as the same kind of data.

Example custom Spring Validator:

```java
import org.springframework.validation.Errors;
import org.springframework.validation.ValidationUtils;

public final class SignupSpringValidator
        implements org.springframework.validation.Validator {

    @Override
    public boolean supports(Class<?> type) {
        return SignupForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        SignupForm form = (SignupForm) target;

        ValidationUtils.rejectIfEmptyOrWhitespace(
                errors, "name", "name.required");

        if (form.getAge() < 18) {
            errors.rejectValue("age", "age.tooYoung");
        }
    }
}
```

This is illustrative code based on a `SignupForm` with `getAge()`, not a complete standalone program. `supports` must match the right type; if `target` is another type, the cast can fail. You can use `SignupForm.class.equals(type)` to support only the exact class, or `isAssignableFrom` to support subclasses.

Spring Validator is well suited when rules need to evaluate multiple properties at once and choose which field receives the error. When validating nested objects, Spring supports `ValidationUtils.invokeValidator(...)` and `errors.pushNestedPath(...)`/`popNestedPath()` to maintain accurate field paths; avoid manually concatenating paths incorrectly.

Starting in Spring 6.1, the Spring Validator interface also has a default `validateObject(Object)` method to validate directly and obtain `Errors`; however, `validate(Object, Errors)` remains the primary contract in binding.

### `SmartValidator` and validation hints

`org.springframework.validation.SmartValidator` **extends Spring Validator**:

```java
void validate(Object target, Errors errors, Object... validationHints);
```

In the Bean Validation adapter, hints can be Jakarta groups. Spring's `@Validated` supports declaring validation groups/hints. Therefore it is inaccurate to say "Spring has no groups at all": the base Spring interface lacks them, but `SmartValidator` and the Jakarta integration layer support them.

A custom Spring Validator containing only Java logic **does not automatically understand** `@NotBlank`, `@Min`, or Jakarta groups without a suitable adapter/provider.

## 5. Bridging Both Worlds with `LocalValidatorFactoryBean`

`org.springframework.validation.beanvalidation.LocalValidatorFactoryBean` is Spring Framework 6.x's central adapter for Jakarta Bean Validation. It bootstraps the Jakarta `ValidatorFactory`, uses a provider such as Hibernate Validator, and allows the same instance to be viewed through:

- `jakarta.validation.Validator`: returns `Set<ConstraintViolation<T>>`.
- `org.springframework.validation.SmartValidator`: records into `Errors`/`BindingResult`, accepts hints.
- `jakarta.validation.ValidatorFactory`: accesses the factory when needed.

Processing flow when invoked via the Spring API:

```text
Bean with @NotBlank, @Min, custom Jakarta constraints
                       |
                       v
               Jakarta provider
                       |
                       v
              ConstraintViolation
                       |
                       v
           LocalValidatorFactoryBean
                       |
                       v
             Errors / BindingResult
            FieldError / ObjectError
```

The adapter translates Jakarta errors into Spring's error mechanism. It **does not automatically turn** your custom `org.springframework.validation.Validator` into Jakarta constraints: a rule written only inside Spring `validate(...)` will not appear if you only call Jakarta `validate(obj)`.

In Spring MVC, when a Bean Validation provider is present, Spring normally registers `LocalValidatorFactoryBean` as the global validator for `@Valid`/`@Validated`. Spring Boot provides `spring-boot-starter-validation` to supply the provider and related configuration. Do not create duplicate beans if auto-configuration already provides a suitable instance.

## 6. Standalone Java 17: Three Branches Validating the Same Object

The complete runnable example below does not start a web server. It validates `Signup("  ", 16)`, so both fields violate constraints. The three branches demonstrate the Jakarta API, a custom Spring API, and the Jakarta-to-Spring adapter.

Create the project:

```text
validator-apis/
├── settings.gradle
├── build.gradle
└── src/main/java/ValidatorApisDemo.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'validator-apis'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'application'
}
repositories {
    mavenCentral()
}
dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
    implementation 'org.hibernate.validator:hibernate-validator:8.0.6.Final'
    implementation 'org.glassfish.expressly:expressly:5.0.0'
}
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
application {
    mainClass = 'ValidatorApisDemo'
}
```

Versions are pinned for reproducibility. In a real Spring Boot project, let Boot's BOM manage compatible Spring/Hibernate versions. `hibernate-validator` provides the Jakarta Validation implementation; `expressly` provides Expression Language for message interpolation.

**`src/main/java/ValidatorApisDemo.java`:**

```java
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

public class ValidatorApisDemo {

    public static final class Signup {

        @NotBlank(message = "name.required")
        private final String name;

        @Min(value = 18, message = "age.tooYoung")
        private final int age;

        public Signup(String name, int age) {
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

    public static final class SignupSpringValidator
            implements org.springframework.validation.Validator {

        @Override
        public boolean supports(Class<?> type) {
            return Signup.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            Signup signup = (Signup) target;
            ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "name", "name.required");

            if (signup.getAge() < 18) {
                errors.rejectValue("age", "age.tooYoung");
            }
        }
    }

    static String jakartaFields(
            Set<? extends ConstraintViolation<?>> violations) {
        return violations.stream()
                .map(v -> v.getPropertyPath().toString())
                .sorted()
                .collect(Collectors.joining(","));
    }

    static String springFields(Errors errors) {
        return errors.getFieldErrors().stream()
                .map(FieldError::getField)
                .sorted()
                .collect(Collectors.joining(","));
    }

    public static void main(String[] args) {
        Signup input = new Signup("  ", 16);

        // Standalone Java demo: explicitly initialize and close the factory.
        LocalValidatorFactoryBean adapter = new LocalValidatorFactoryBean();
        adapter.afterPropertiesSet();

        try {
            // 1. Jakarta API returns violations.
            jakarta.validation.Validator jakarta = adapter;
            Set<ConstraintViolation<Signup>> violations =
                    jakarta.validate(input);
            System.out.printf("Jakarta: %d -> %s%n",
                    violations.size(), jakartaFields(violations));

            // 2. Custom Spring API records Errors.
            org.springframework.validation.Validator customSpring =
                    new SignupSpringValidator();
            Errors springErrors =
                    new BeanPropertyBindingResult(input, "signup");
            customSpring.validate(input, springErrors);
            System.out.printf("Spring: %d -> %s%n",
                    springErrors.getErrorCount(),
                    springFields(springErrors));

            // 3. The same adapter viewed as a Spring Validator.
            org.springframework.validation.Validator bridge = adapter;
            Errors adapterErrors =
                    new BeanPropertyBindingResult(input, "signup");
            bridge.validate(input, adapterErrors);
            System.out.printf("Adapter: %d -> %s%n",
                    adapterErrors.getErrorCount(),
                    springFields(adapterErrors));
        } finally {
            adapter.destroy();
        }
    }
}
```

Run in the project root directory with Java 17 and Gradle:

```bash
gradle run --quiet
```

If the project has a Gradle Wrapper, use `./gradlew run --quiet` on Linux/macOS or `gradlew.bat run --quiet` on Windows.

**Expected standard output:**

```text
Jakarta: 2 -> age,name
Spring: 2 -> age,name
Adapter: 2 -> age,name
```

Explanation:

1. `@NotBlank` rejects `"  "`, `@Min(18)` rejects 16, so Jakarta receives 2 violations.
2. The custom Spring Validator checks the corresponding two conditions and records 2 `FieldError`s into `Errors`.
3. The adapter translates the two Jakarta violations into a new `BeanPropertyBindingResult`, which also has 2 field errors.
4. Because `Set` does not guarantee ordering, the example **sorts field names** before printing for deterministic stdout.
5. Since there is no Spring container in the demo, `afterPropertiesSet()` and `destroy()` are called explicitly. In a Spring ApplicationContext, the container manages the lifecycle.

The demo uses an immutable object with getters to illustrate direct validation. When receiving HTML forms via `@ModelAttribute`, an appropriate model and data binding strategy are required; the example does not by itself demonstrate HTTP binding.

## 7. Spring MVC: `@Valid`, `@Validated`, `BindingResult`

In a Spring MVC application with a Bean Validation provider and appropriate validator configuration, place Jakarta `@Valid` or Spring `@Validated` on the model argument to request validation after the binding step.

Illustrative example of a **method inside `@Controller`**, assuming `SignupForm` is a model with appropriate getters/setters or binding mechanism and a matching view exists:

```java
import jakarta.validation.Valid;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;

@PostMapping("/signup")
public String submit(
        @Valid @ModelAttribute("signup") SignupForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return "signup-form";
    }
    return "signup-success";
}
```

`BindingResult` **must appear immediately after** the parameter whose errors it represents if the controller wants to handle those binding/validation errors directly.

To register a local custom Spring Validator for the `signup` model, place the following method **inside the controller**:

```java
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;

@InitBinder("signup")
public void initBinder(WebDataBinder binder) {
    binder.addValidators(new SignupSpringValidator());
}
```

`SignupSpringValidator.supports(...)` must support the model type. When a global Jakarta validator exists, `addValidators` can cause both the Jakarta validator and custom validator to run together. If the same rule is written twice, field errors can be duplicated; assign each rule to a single responsible place.

To select a Jakarta validation group, Spring's `@Validated` can be used:

```java
@Validated(PublishChecks.class)
@ModelAttribute("signup") SignupForm form
```

This is a **parameter declaration snippet**, not a complete controller method. `@Validated` allows specifying groups/hints; Jakarta's `@Valid` does not directly carry such a group list.

Note that Spring MVC 6.1+ also supports **method validation** when constraints are placed directly on parameters or return values. Error handling may go through `MethodArgumentNotValidException` or `HandlerMethodValidationException` depending on the signature and situation. Do not assume all `@Valid` errors produce the exact same exception type.

`@RequestBody` is decoded by Jackson/`HttpMessageConverter` before object constraint validation runs. Malformed JSON syntax or type mismatches are deserialization/binding issues, not `ConstraintViolation`s. Handle each error category properly and define an HTTP error DTO, avoiding exposing sensitive values from `getInvalidValue()` in responses.

## 8. Choosing an Implementation Approach

| Need | Suitable API | Explanation |
| --- | --- | --- |
| Required fields, length limits, numeric ranges, common patterns | Jakarta constraints | Concise, reusable across layers |
| Reusable custom constraints with groups | Jakarta `@Constraint` + `ConstraintValidator` | Leverages standard metadata/cascading/groups |
| Rules spanning multiple fields in a specific form | Spring Validator | Full control over field vs object errors and error codes |
| Using Jakarta constraints in Spring form binding | `LocalValidatorFactoryBean`/`SmartValidator` | Converts violations into `Errors` |
| Services/batches needing HTTP-independent validation | Jakarta Validator | Returns structured violation sets |
| Forms with Create/Update/Publish stages | Jakarta groups; Spring `@Validated` | Activates the exact constraint subset |
| Uniqueness under concurrent requests | Service + DB constraints/transactions | Pre-write validation does not eliminate race conditions |

You can combine both Jakarta and Spring validators. However, avoid duplicating the same rule in multiple places and avoid assuming the adapter will convert Spring rules to the Jakarta provider.

## 9. Common Mistakes to Avoid

1. **Package confusion:** Jakarta `Validator` has no `supports(Class<?>)`; Spring `Validator` does not return `Set<ConstraintViolation>`.
2. **Missing provider:** adding only `jakarta.validation-api` is insufficient to run annotation constraints.
3. **Ignoring results:** Jakarta `validate(...)` returns a `Set`; Spring `validate(...)` writes into `Errors`, neither throws an exception automatically on bad input.
4. **Wrong `supports`:** a validator attached to an unsupported model type can cause binder or cast failures.
5. **Duplicate errors:** checking age with both `@Min` and a custom Spring validator in the same flow.
6. **Group confusion:** running a custom group does not mean every constraint in the `Default` group also runs.
7. **Forgetting cascade:** `@NotNull` on a parent field does not validate constraints inside the child object.
8. **Confusing code vs message:** `FieldError.getCode()` works with Spring message resolution; `ConstraintViolation.getMessage()` is already interpolated by Jakarta.
9. **Wrong adapter assumption:** custom Spring rules do not automatically appear in `jakartaValidator.validate(...)`.
10. **Treating validation as a DB barrier:** uniqueness and data integrity must be enforced at the storage layer.
11. **Mixing `javax.validation` with `jakarta.validation`:** Spring Framework 6+/Spring Boot 3+ use the Jakarta namespace.
12. **Assuming all request errors come from Bean Validation:** distinguish JSON parsing, type conversion, form binding, object constraints, and method validation.
13. **Relying on `ConstraintViolation` Set order:** sort before testing or displaying.
14. **Exposing sensitive invalid values in logs/HTTP:** return only appropriate codes, paths, and messages.

## 10. Self-Check and Exercises

### Questions

- What does Jakarta `validate(form)` return? **`Set<ConstraintViolation<Form>>`, empty if there are no violations in the evaluated groups.**
- What does Spring `validate(form, errors)` return? **`void`; errors are added into `errors`.**
- Can `LocalValidatorFactoryBean` be used under both interfaces? **Yes, when configured with a provider.**
- Does a custom Spring Validator make the Jakarta API automatically recognize its Java rules? **No.**
- Why add `@Valid` on a nested field? **To request cascaded validation into the child object.**
- When is `@Validated` used? **When groups/hints are needed in a Spring-supported context.**

### Practice Exercises

1. Change `new Signup("  ", 16)` to `new Signup("Mai", 22)`: all three branches should produce **0 errors**.
2. Change it to `new Signup("Mai", 16)`: all three branches should report an error only on field **`age`**.
3. Add `confirmPassword` and validate it via Spring `Errors`; compare with writing a Jakarta class-level constraint.
4. Create a `PublishChecks` group; assign one constraint to that group and compare the result with `Default`.
5. Add an MVC endpoint accepting `@Valid @ModelAttribute`, then test both constraint failures and type conversion failures to distinguish the two error groups.

## 11. Official Documentation

- [Spring Framework — Validation Using Spring’s Validator Interface](https://docs.spring.io/spring-framework/reference/core/validation/validator.html): `supports`, `validate`, `Errors`, `ValidationUtils`.
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): Jakarta provider, `LocalValidatorFactoryBean`, both interfaces.
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): `@Valid`, `@Validated`, method validation.
- [Jakarta Bean Validation — Validator API](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/Validator.html): `validate`, `validateProperty`, `validateValue`, groups.
- [Spring Framework 6.2 — LocalValidatorFactoryBean](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html): adapter and lifecycle.
- [Hibernate Validator — 8.0 series](https://hibernate.org/validator/releases/8.0/): provider used in the examples.

**Knowledge takeaway:** the two `Validator`s address the same data-checking need through two different contracts. Jakarta describes constraints and returns `ConstraintViolation`; Spring Validator records errors into `Errors`. `LocalValidatorFactoryBean` enables Jakarta constraints to participate in Spring MVC's binding and validation flow.
