# @Target, @Retention, and Repeatability of Custom Constraints

In Spring Framework, a custom Jakarta Validation constraint is typically declared with an **annotation** and a `ConstraintValidator` implementation class. Three Java meta-annotations determine **where** that annotation can be placed, **how long** it is retained, and whether it can be written **multiple times on the same element**:

- `@Target`: the locations where Java allows the annotation to be attached.
- `@Retention`: how long the annotation is retained; Bean Validation needs to read metadata at runtime.
- `@Repeatable`: allows repeating the same annotation type with different arguments on the same element; Jakarta Validation processes each declared constraint.

These three concepts serve different roles. They also **do not trigger validation on their own**: the annotation must be a valid constraint (`@Constraint`, `message`, `groups`, `payload`, and a matching validator), the application needs a Jakarta Validation provider, and there must be a validation trigger point (for example `Validator.validate(...)` or Spring's validation integration).

## 1. `@Target`: where can a constraint be placed?

`@Target` accepts one or more constants from `java.lang.annotation.ElementType`. The compiler checks annotation usage against these locations; they are not a list of data types supported by the validator.

| `ElementType` | Meaning for a custom constraint | Example |
|---|---|---|
| `FIELD` | Bean field, including `private` fields | `@Matches private String code;` |
| `METHOD` | Method, typically a getter/return value | Placed on `getCode()` |
| `PARAMETER` | Method or constructor parameter | `void save(@Matches String code)` |
| `CONSTRUCTOR` | The constructor itself, when a return-value constraint or execution rule is appropriate | Constraint on a constructor |
| `ANNOTATION_TYPE` | Used as a meta-annotation for constraint composition | Placing this constraint on another annotation |
| `TYPE_USE` | A type-use site, especially a collection's type argument | `List<@Matches String>` |
| `TYPE` | Class/interface/record declaration | Constraint checking the entire object |

Choose targets based on the **semantics of the validator**, rather than copying every possible target. For example, a `ConstraintValidator<Matches, String>` validator only understands strings, so the sample annotation below does not declare `TYPE` to apply to an entire class. `TYPE_USE` is useful for `List<@Matches String>`; it does not mean the provider automatically knows how to inspect arbitrary generic structures. Container element validation also depends on the value extractors supported by Jakarta Validation.

Example (abbreviated, illustrating placement only):

~~~java
// FIELD: validates the property when the bean is validated.
@Matches(regexp = "[A-Z]+")
private String code;

// PARAMETER: syntactically valid thanks to ElementType.PARAMETER.
// Checking on method invocation requires a method validation mechanism.
void submit(@Matches(regexp = "[A-Z]+") String code) { }

// TYPE_USE: applies to each String inside a supported container.
private java.util.List<@Matches(regexp = "[A-Z]+") String> codes;
~~~

If `@Target` only has `FIELD` and you place the annotation on a method, `javac` reports an invalid target location error. Conversely, allowing `PARAMETER` is not enough for every method call to be intercepted: Spring must be configured and routed through the appropriate method validation mechanism. `METHOD` on a getter and `FIELD` on a field can represent the same property; avoid accidentally declaring two equivalent constraints that produce duplicate errors with the same content.

## 2. `@Retention`: why does a custom constraint need `RUNTIME`?

`@Retention` takes a `RetentionPolicy` value:

| Policy | After compilation | Readable via reflection at runtime? | Suitable for Jakarta Validation? |
|---|---|---|---|
| `SOURCE` | Not retained in the `.class` file | No | No |
| `CLASS` | Present in `.class` but not retained for runtime reflection | No | No |
| `RUNTIME` | Retained in `.class` and present at runtime | Yes | **Yes** |

If `@Retention` is omitted, Java defaults to `CLASS`. For a Jakarta Validation constraint, use:

~~~java
@Retention(RetentionPolicy.RUNTIME)
~~~

A provider such as Hibernate Validator needs to find constraint metadata when validating an object. The `@Constraint` annotation cannot compensate for the custom annotation itself being retained only at `SOURCE` or `CLASS`. `RUNTIME` ensures metadata is observable, but **does not guarantee the constraint will execute** if a provider, validator, or validation invocation is missing.

`@Documented` is another meta-annotation that makes the annotation appear in Javadoc; it does not replace `@Retention(RUNTIME)` and does not trigger validation logic.

## 3. `@Repeatable`: multiple independent conditions on the same element

A code might have to satisfy two rules simultaneously: start with an uppercase letter **and** contain only 4–12 letters. To use `@Matches` twice on the same field, Java requires the `Matches` annotation to be declared repeatable.

The standard pattern consists of two parts:

1. On the main annotation: `@Repeatable(Matches.List.class)`.
2. A **container annotation** `Matches.List` with an element `Matches[] value()`; the container has `@Retention(RUNTIME)` and a target compatible with `Matches`.

Desired usage example:

~~~java
@Matches(regexp = "[A-Z].*", message = "Must start with an uppercase letter")
@Matches(regexp = "[A-Za-z]{4,12}", message = "Letters only, 4–12 characters long")
private String value;
~~~

Both constraints are evaluated when the object is validated; for the value `"a3"`, both are violated. `@Repeatable` allows **multiple declarations of the same type**, does not make the constraint "loop until satisfied", does not create a loop on its own, and does not replace `@Valid`.

At the Java level, the compiler may wrap repeated annotations into the `Matches.List` container. To properly read the declarations via reflection, use `getAnnotationsByType(Matches.class)` or `getDeclaredAnnotationsByType(Matches.class)`; `getAnnotation(Matches.class)` may return `null` when two annotations have been stored under the container. Jakarta Validation defines rules for recognizing multi-valued constraint annotations: the elements in the container's `value()` are processed as independent constraints.

The following explicit container syntax has an equivalent validation effect in this context:

~~~java
@Matches.List({
    @Matches(regexp = "[A-Z].*", message = "Must start with an uppercase letter"),
    @Matches(regexp = "[A-Za-z]{4,12}", message = "Letters only, 4–12 characters long")
})
private String value;
~~~

The name `List` is the convention recommended by Jakarta Validation, **not** `java.util.List`. If the container lacks `value()` of type `Matches[]`, or its retention/target is incompatible, Java will reject the repeatable design. The container itself is normally **not** marked with `@Constraint` separately: it is a shell holding child constraints, not a third validation rule.

## 4. Complete example: a repeatable custom constraint in Spring Boot

The example uses **Java 17+**, `jakarta.validation.*`, and a Spring Boot application configured with the `spring-boot-starter-validation` dependency (and the Spring Boot parent/BOM). All classes are in the same package `com.example.validation`. The provider in the starter executes the constraints; `CommandLineRunner` creates invalid data, invokes `Validator`, and prints the error count. This is a runnable program **when placed inside a valid Spring Boot project**, not a plain-JDK example needing only `javac`.

### 4.1. Annotation declaration — `Matches.java`

~~~java
package com.example.validation;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Constraint(validatedBy = MatchesValidator.class)
@Target({
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.PARAMETER,
    ElementType.ANNOTATION_TYPE,
    ElementType.TYPE_USE
})
@Retention(RetentionPolicy.RUNTIME)
@Repeatable(Matches.List.class)
public @interface Matches {
    String regexp();

    String message() default "Value does not match {regexp}";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};

    @Documented
    @Target({
        ElementType.FIELD,
        ElementType.METHOD,
        ElementType.PARAMETER,
        ElementType.ANNOTATION_TYPE,
        ElementType.TYPE_USE
    })
    @Retention(RetentionPolicy.RUNTIME)
    @interface List {
        Matches[] value();
    }
}
~~~

Points to read carefully:

- `@Constraint(validatedBy = MatchesValidator.class)` declares the validator for the constraint.
- `regexp()` is a constraint-specific configuration parameter; `message`, `groups`, and `payload` are the standard elements of a Jakarta Validation definition.
- `@Target` and `@Retention` appear on both the main annotation and the container; `@Repeatable` is attached only to the main annotation.
- `@Documented` makes Javadoc clearer; it does not affect validation results.

### 4.2. Validation logic — `MatchesValidator.java`

~~~java
package com.example.validation;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import java.util.regex.Pattern;

public final class MatchesValidator
        implements ConstraintValidator<Matches, String> {

    private Pattern pattern;

    @Override
    public void initialize(Matches annotation) {
        this.pattern = Pattern.compile(annotation.regexp());
    }

    @Override
    public boolean isValid(
            String value,
            ConstraintValidatorContext context) {
        return value == null || pattern.matcher(value).matches();
    }
}
~~~

`initialize` reads the `regexp` configuration of **each `@Matches` declaration**, compiles the regex, and then `isValid` checks the value. Returning `true` on `null` is the common design pattern for separating format validation from required-input checks; if `null` must be rejected, combine it with `@NotNull`. `Pattern.matcher(...).matches()` requires the **entire string** to match the regex. For complex regexes, consider validating or fixing the regex configuration at annotation construction time to catch misconfigurations early.

### 4.3. Target object carrying constraints — `AccountCode.java`

~~~java
package com.example.validation;

public final class AccountCode {

    @Matches(
        regexp = "[A-Z].*",
        message = "Must start with an uppercase letter")
    @Matches(
        regexp = "[A-Za-z]{4,12}",
        message = "Letters only, 4–12 characters long")
    private final String value;

    public AccountCode(String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }
}
~~~

These are **two constraint instances** of the same type, on the same field, with different configurations and messages. `"ABcd"` satisfies both; `"a3"` violates both; `"Abc"` satisfies the first condition but fails the minimum length. Each constraint is evaluated during a `validator.validate(...)` call under default semantics; the return order of `ConstraintViolation` items is not guaranteed.

### 4.4. Triggering validation and observing results — `DemoApplication.java`

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
    public void run(String... args) throws NoSuchFieldException {
        var violations = validator.validate(new AccountCode("a3"));

        System.out.println("Error count: " + violations.size());
        violations.stream()
            .map(v -> v.getMessage())
            .sorted()
            .forEach(System.out::println);

        var declared = AccountCode.class
            .getDeclaredField("value")
            .getAnnotationsByType(Matches.class);

        System.out.println(
            "@Matches count via reflection: " + declared.length);
    }
}
~~~

Required dependency in the `pom.xml` of a Spring Boot project managing dependency versions:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Run from the Maven project directory that has the Spring Boot parent/BOM and Spring Boot Maven plugin:

~~~bash
./mvnw spring-boot:run
~~~

On Windows, use `mvnw.cmd spring-boot:run`. Aside from Spring Boot startup log lines, the demo prints these exact four lines (messages are sorted for deterministic output):

~~~text
Error count: 2
Letters only, 4–12 characters long
Must start with an uppercase letter
@Matches count via reflection: 2
~~~

If `"a3"` is replaced with `"ABcd"`, the error count is `0` while the annotation count observed via reflection remains `2`: **constraint declaration** does not depend on input values, whereas **violations** depend on the validated value.

## 5. Relation to Spring MVC, binding, and container elements

**Binding and validation are two related but distinct phases.** Spring can bind HTTP data into an object; whether constraints are executed depends on the validation trigger point.

Example DTO:

~~~java
public class CreateAccountRequest {
    @Matches(regexp = "[A-Z].*")
    @Matches(regexp = "[A-Za-z]{4,12}")
    private String code;

    public String getCode() {
        return code;
    }

    public void setCode(String code) {
        this.code = code;
    }
}
~~~

With Spring MVC configured with Jakarta Validation, a controller parameter such as `@Valid @RequestBody CreateAccountRequest request` is one path that triggers object validation after binding. The annotation is allowed on the field thanks to `FIELD`, present at runtime thanks to `RUNTIME`, and applied twice thanks to `@Repeatable`. How HTTP errors are actually handled depends on configuration and controller exception handling.

For `List<@Matches(regexp = "[A-Z]+") String>`, `TYPE_USE` lets the constraint attach to the container's **string elements** when the provider supports value extraction. For `List<@Valid Address>`, `@Valid` is the **cascade** mechanism to traverse into the `Address` bean; it differs from `@Repeatable`. Applying an annotation to a method parameter also requires an appropriate method validation mechanism; merely having the method exist and be called is not enough for Jakarta Validation to run automatically.

## 6. Common errors and diagnostics

| Symptom | Common cause | How to check/fix |
|---|---|---|
| Compile error when placed on field, method, or type argument | `@Target` is missing `FIELD`, `METHOD`, `PARAMETER`, or `TYPE_USE` respectively | Compare actual usage sites against the `ElementType` list |
| Constraint is not discovered at runtime | Using `SOURCE`, `CLASS`, or omitting `@Retention` so it defaults to `CLASS` | Set `@Retention(RUNTIME)` on both the main annotation and the container |
| Compiler reports annotation is not repeatable | Writing two annotations of the same type without valid `@Repeatable`/container | Declare `@Repeatable(Matches.List.class)` and `Matches[] value()` |
| Compile error in `@Repeatable` definition | Container has shorter retention, incompatible target, or wrong `value()` type | Cross-check `@Target` and `@Retention` of both annotations |
| Reflection sees container but not individual annotations | Reading via `getAnnotation(Matches.class)` when multiple declarations exist | Use `getAnnotationsByType(Matches.class)` |
| No errors despite invalid data | Missing Jakarta Validation provider, validation not triggered, or validator returns `true` | Verify starter/provider, `@Constraint`, `Validator.validate`, or Spring trigger point |
| `UnexpectedTypeException` | Applying constraint to a type not supported by `ConstraintValidator<..., String>` | Adjust target/placement, data type, or add a validator for the right type |
| Duplicate errors or unexpected results | Attaching equivalent constraints to both field and getter, or repeating the same condition | Inspect metadata at each site and the intent of each constraint |
| `null` is still valid | Validator intentionally lets `null` pass | Add `@NotNull` if the field is required |
| Parameters are not checked automatically on method call | `PARAMETER` only allows placing the annotation syntactically | Enable method validation according to the Spring mechanism in use |

## 7. Checklist for designing repeatable constraints

Before adding a custom annotation to the codebase, answer these questions:

1. **Which locations are valid?** Declare only the `ElementType` values matching the semantics and supported data types; add `TYPE_USE` if container element constraints are needed.
2. **Is metadata retained at runtime?** Both the main annotation and the container have `@Retention(RUNTIME)`.
3. **Does the same constraint need to be applied multiple times?** If yes, declare `@Repeatable` and a `List` container with `value()` as an array of the main annotation.
4. **Is this genuinely a constraint?** Has `@Constraint`, `message`, `groups`, `payload`, and a valid `ConstraintValidator`/composition.
5. **What triggers validation?** `@Valid`/`@Validated` at the appropriate points or `Validator.validate(...)`; understand method validation vs bean validation in the application.
6. **Are results reliable?** Test valid samples, single-rule violations, multi-rule violations, `null`, unsupported types, and reading annotations back with `getAnnotationsByType`.

**Takeaway:** `@Target` = *where it can be placed*; `@Retention(RUNTIME)` = *discoverable at runtime*; `@Repeatable` + container = *declarable multiple times*. These three work together with `@Constraint`, `ConstraintValidator`, and a validation trigger point to make a custom constraint work properly in Spring.

## Original references

- [Jakarta Validation 3.1 Specification – Constraint definition & Applying multiple constraints](https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html#constraintdefinition)
- [Jakarta Validation API – `@Constraint`](https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/constraint)
- [Java SE 21 – `@Repeatable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/Repeatable.html)
- [Java SE 21 – `@Retention`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/Retention.html)
- [Java SE 21 – `AnnotatedElement.getAnnotationsByType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedElement.html)
- [Spring Framework – Java Bean Validation & custom constraints](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
