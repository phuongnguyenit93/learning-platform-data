# `@OverridesAttribute` for Customizing Composing Constraints

## 1. Purpose and context

In Spring Framework, annotation-driven data validation typically uses **Jakarta Validation (Bean Validation)** alongside a provider like Hibernate Validator. When several rules always travel together, we can define a **composed constraint**: a new annotation carrying built-in composing constraint annotations such as `@Size`, `@Pattern`, and `@NotNull`.

This lesson focuses on **`jakarta.validation.OverridesAttribute`**: how to forward attributes of a composed annotation down to attributes of individual composing constraints so callers can configure them right at the declaration site. After this lesson, you can:
- Create a composed annotation without writing a custom `ConstraintValidator` when existing constraints already express the rule completely.
- Map attributes such as `min`, `max`, `regexp`, and `message` using `@OverridesAttribute`.
- Target a specific constraint among multiple declarations of the same type using `constraintIndex`.
- Distinguish component configuration overrides from aggregate error messages and use the annotation in Spring MVC.
- Verify overridden values through validation results and metadata.

**Name distinction:** `@OverridesAttribute` belongs to Jakarta Validation and differs from Spring's `org.springframework.core.annotation.AliasFor`. `@AliasFor` handles attribute relationships across annotations in Spring's annotation-reading mechanism; it does not replace Bean Validation's override rules.

## 2. How does constraint composition work?

For example, the same user code must be 4–12 characters long and contain only uppercase letters, digits, and underscores:

```java
@Size(min = 4, max = 12)
@Pattern(regexp = "[A-Z0-9_]+")
private String userCode;
```

If this rule repeats across many DTOs, we place `@Size` and `@Pattern` on a `@UserCode` annotation, then put `@UserCode` on fields. Per Jakarta Validation, composing constraints combine with **AND**: a value must satisfy all rules to be valid. Each composing constraint still retains its own validation logic and message.

Problem: if the component always declares `@Size(min = 4, max = 12)`, how can one usage site require length 5–8 without creating another annotation? `@OverridesAttribute` solves this by linking an attribute method of `@UserCode` to an attribute of `@Size`. Values passed via `@UserCode(min = 5, max = 8)` are forwarded down to `@Size.min` and `@Size.max`.

**Mechanism scope:** This is a mapping of *attribute values*, not Java method overriding via `@Override`; nor does it alter the global definition of `@Size` or `@Pattern`.

## 3. Syntax and mapping rules

```java
@OverridesAttribute(constraint = Size.class, name = "min")
int min() default 4;
```

`@OverridesAttribute` must be placed on an **attribute declaration method inside a composed annotation** (e.g. `min()`), not on a DTO field or business method. Three parameters identify the mapping target:

| Parameter | Meaning |
| --- | --- |
| `constraint` | Annotation class of the direct composing constraint, e.g. `Size.class` or `Pattern.class`; required. |
| `name` | Target attribute name, e.g. `"min"`, `"max"`, `"regexp"`, `"message"`. If omitted, defaults to the outer method name. |
| `constraintIndex` | Zero-based index distinguishing multiple constraints of the same type; defaults to `-1` for a single declaration. |

Key conditions:
1. The outer attribute's return type must **match the target attribute's type exactly**; e.g. `@Size.min` is `int`, `@Pattern.regexp` is `String`. `long` cannot substitute for `int`.
2. The specified constraint must be a **direct composing constraint** of the annotation containing the override rule. With multiple nested composition layers, each layer applies forwarding at its direct level; you cannot jump across multiple levels with a single override annotation.
3. For each target attribute, the mapping must be clear, unambiguous, and non-conflicting. Broken composition setups can raise `ConstraintDefinitionException` when the provider reads metadata or executes validation.
4. The outer attribute's default value also takes effect: if the caller omits the argument, that `default` value is passed down to the composing constraint.

Example when attribute names match, allowing `name` to be omitted:

```java
@OverridesAttribute(constraint = Pattern.class)
String regexp() default "[A-Z0-9_]+";
```

Here `regexp()` on the composed annotation maps to `Pattern.regexp()`. Conversely, if you pick a friendlier name like `formatMessage()`, you must write `name = "message"` to map properly.

## 4. Runnable practice: customizing `@Size` and `@Pattern`

The standalone example below uses **Java 17**, **Jakarta Validation 3.0**, and **Hibernate Validator 8.0.6.Final**. It runs with Maven without starting Spring; a later section connects it back to Spring MVC. Structure:

```text
validation-demo/
├── pom.xml
└── src/main/java/demo/
    ├── UserCode.java
    └── Main.java
```

### 4.1. Declaring dependencies

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>validation-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.6.Final</version>
        </dependency>
        <dependency>
            <groupId>org.glassfish.expressly</groupId>
            <artifactId>expressly</artifactId>
            <version>5.0.0</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`hibernate-validator` brings in the provider and Jakarta Validation API transitively. `expressly` provides Jakarta Expression Language for message interpolation; Spring Boot applications usually manage dependencies via starters.

### 4.2. Creating the composed constraint

Create `src/main/java/demo/UserCode.java`:

```java
package demo;

import jakarta.validation.Constraint;
import jakarta.validation.OverridesAttribute;
import jakarta.validation.Payload;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Constraint(validatedBy = {})
@Size(min = 4, max = 12)
@Pattern(regexp = "[A-Z0-9_]+")
@Target({
        ElementType.FIELD,
        ElementType.METHOD,
        ElementType.PARAMETER,
        ElementType.ANNOTATION_TYPE
})
@Retention(RetentionPolicy.RUNTIME)
public @interface UserCode {

    String message() default "User code is invalid";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};

    @OverridesAttribute(constraint = Size.class, name = "min")
    int min() default 4;

    @OverridesAttribute(constraint = Size.class, name = "max")
    int max() default 12;

    @OverridesAttribute(constraint = Pattern.class)
    String regexp() default "[A-Z0-9_]+";

    @OverridesAttribute(constraint = Size.class, name = "message")
    String lengthMessage() default "length must be between {min} and {max}";

    @OverridesAttribute(constraint = Pattern.class, name = "message")
    String formatMessage() default "invalid characters";
}
```

Part-by-part explanation:
- `@Constraint(validatedBy = {})` states `@UserCode` is a valid constraint without its own validator: `@Size` and `@Pattern` handle validation.
- `@Retention(RUNTIME)` lets the provider read the annotation at runtime. `@Target(ANNOTATION_TYPE)` allows reusing `@UserCode` as a component of another composed annotation.
- `message()`, `groups()`, `payload()` are the required standard attributes of a normal constraint annotation.
- `min()` and `max()` forward to two distinct integer attributes of `@Size`.
- `regexp()` illustrates the default `name` rule: the outer and target method names are identical.
- `lengthMessage()` and `formatMessage()` customize **individual composing constraint messages**; `{min}` and `{max}` are interpolated from the actual overridden values.

Do not confuse `UserCode.message()` with `Size.message()` or `Pattern.message()`: they are three attributes on three different annotations. Declaring `UserCode.message()` alone **does not automatically** push the message down to components.

### 4.3. Placing the annotation on data and testing

Create `src/main/java/demo/Main.java`:

```java
package demo;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;

import java.util.TreeSet;

public class Main {

    static final class UserRequest {
        @UserCode(min = 5, max = 8, regexp = "[A-Z][A-Z0-9_]*")
        private final String code;

        UserRequest(String code) {
            this.code = code;
        }
    }

    private static void check(Validator validator, String value) {
        TreeSet<String> messages = new TreeSet<>();

        for (ConstraintViolation<UserRequest> violation
                : validator.validate(new UserRequest(value))) {
            messages.add(violation.getMessage());
        }

        System.out.println(String.valueOf(value) + " -> " + messages);
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            check(validator, "AB");
            check(validator, "Abc_12");
            check(validator, "ABC_12");
            check(validator, null);
        }
    }
}
```

Run from the `validation-demo` directory (requires JDK 17+ and Maven):

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.Main
```

Lines printed by `Main` on stdout (any Maven/provider logs are separate):

```text
AB -> [length must be between 5 and 8]
Abc_12 -> [invalid characters]
ABC_12 -> []
null -> []
```

- `AB` has valid format yet is only 2 characters long, so it violates `@Size(min=5,max=8)`.
- `Abc_12` is 6 characters long yet contains lowercase `b` and `c`; the `regexp` at the usage site replaced `@Pattern`'s configuration.
- `ABC_12` satisfies both components.
- `null` is treated as valid by `@Size` and `@Pattern`; if a value is required, add `@NotNull` or `@NotBlank` per your goal. Do not treat `@OverridesAttribute` as an automatic null-checking mechanism.

Note: this code is a **real, working annotation**. Writing `@Size(min=5,max=8)` and `@Pattern(regexp="...")` directly on every field has equivalent validation semantics, but does not provide a concise, reusable annotation API.

## 5. One outer attribute overriding multiple inner attributes

Sometimes an **exact** length is needed: minimum and maximum character counts must be equal. One method on a composed annotation can carry **multiple `@OverridesAttribute` annotations**, because it is repeatable.

The snippet below illustrates a **different** annotation (place it in its own file and add Jakarta Validation/Java annotation imports as in the earlier example):

```java
@Documented
@Constraint(validatedBy = {})
@Size(min = 6, max = 6)
@Target({ElementType.FIELD, ElementType.METHOD,
         ElementType.PARAMETER, ElementType.ANNOTATION_TYPE})
@Retention(RetentionPolicy.RUNTIME)
public @interface ExactLength {

    String message() default "Length is invalid";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};

    @OverridesAttribute(constraint = Size.class, name = "min")
    @OverridesAttribute(constraint = Size.class, name = "max")
    int length() default 6;
}
```

When using `@ExactLength(length = 8)`, the provider sees `@Size(min = 8, max = 8)`. With Jakarta Validation 3.0, two repeatable annotations placed directly on the same method are permitted; in older code you may encounter the wrapper syntax `@OverridesAttribute.List({...})`. This is a distinct technique, **unrelated** to `constraintIndex` because we only have **one** `@Size`.

## 6. Multiple composing constraints of the same type: `constraintIndex`

When a composed annotation contains two `@Pattern`s, `constraint = Pattern.class` and `name = "message"` alone are **insufficient** to select one instance. Use `constraintIndex = 0` for the first `@Pattern`, `1` for the second. The example below is an annotation declaration snippet (add imports as in section 4):

```java
@Documented
@Constraint(validatedBy = {})
@Pattern(regexp = "[A-Z].*", message = "Must start with uppercase")
@Pattern(regexp = ".*[0-9]", message = "Must end with digit")
@Target({ElementType.FIELD, ElementType.METHOD,
         ElementType.PARAMETER, ElementType.ANNOTATION_TYPE})
@Retention(RetentionPolicy.RUNTIME)
public @interface StartUpperEndDigit {

    String message() default "Invalid code";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};

    @OverridesAttribute(
            constraint = Pattern.class,
            name = "message",
            constraintIndex = 0
    )
    String firstMessage() default "First character must be uppercase";

    @OverridesAttribute(
            constraint = Pattern.class,
            name = "message",
            constraintIndex = 1
    )
    String secondMessage() default "Last character must be a digit";
}
```

Using `@StartUpperEndDigit(secondMessage = "Missing trailing digit")` replaces the message **only for the second `@Pattern`**. `"Abc"` passes the first condition but does not end with a digit, so it receives the new message. `"abc4"` violates the first condition.

Index counting rules:
- With two directly declared repeatable annotations, indices follow **left-to-right declaration order**, starting at `0`.
- With a `@Pattern.List({@Pattern(...), @Pattern(...)})` container, indices follow the elements of the `value` array.
- Do not declare constraints both directly and via `@Pattern.List` for the same type on one composed annotation; the specification states that doing so may cause a `ConstraintDeclarationException`.
- When there is only one `@Pattern`, omit `constraintIndex`; the default `-1` targets the single declaration.

`constraintIndex` is an index among **composing constraints of the same type**, not the ordinal position of every annotation on the class.

## 7. Error reporting: multiple violations or a single violation?

By default, composing constraints report errors individually. If a value fails both length and format, the `ConstraintViolation` set can contain **two violations** with `@Size` and `@Pattern` messages. Iteration order of violations is not guaranteed; `Main` uses `TreeSet` for deterministic print ordering.

If an API wants to return **one** representative error for the whole composed constraint, add `@ReportAsSingleViolation` to the **composed annotation declaration**:

```java
@ReportAsSingleViolation
@Constraint(validatedBy = {})
@Size(min = 4, max = 12)
@Pattern(regexp = "[A-Z0-9_]+")
// ... @Target, @Retention and attributes as in UserCode above
public @interface UserCode {
    String message() default "User code is invalid";
    // ...
}
```

This is an **annotation placement illustration**, not a full Java file replacing section 4. Now, when composition fails, the provider reports one error at the `@UserCode` level using `UserCode.message()`. `@OverridesAttribute` still forwards configuration down to components; `@ReportAsSingleViolation` changes how errors are aggregated. The two mechanisms serve two distinct purposes.

Choose a strategy according to your API contract:
- Need to pinpoint exact length vs format errors: keep component violations and customize `lengthMessage`/`formatMessage`.
- Need to hide rule details and return one simple message: use `@ReportAsSingleViolation` and configure `message` on the outer annotation.

## 8. Integrating into Spring Framework / Spring Boot

`@OverridesAttribute` is processed by the Jakarta Validation provider. Spring feeds the results into the validation/binding pipeline when the DTO is properly annotated and a provider is on the classpath. In Spring Boot 3.x applications, the following starters are typically declared (illustrative `build.gradle` snippet, assuming a Boot project with plugins and repositories configured):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
```

A DTO can use the defined `@UserCode`:

```java
public class CreateUserRequest {
    @UserCode(min = 5, max = 8, regexp = "[A-Z][A-Z0-9_]*")
    private String code;

    public String getCode() { return code; }
    public void setCode(String code) { this.code = code; }
}
```

An illustrative Spring MVC handler (code inside a Boot project, requiring Spring MVC and `jakarta.validation.Valid` imports):

```java
@RestController
@RequestMapping("/users")
class UserController {

    @PostMapping
    ResponseEntity<Void> create(@Valid @RequestBody CreateUserRequest request) {
        // Process data that has already passed input-layer validation.
        return ResponseEntity.noContent().build();
    }
}
```

For `@RequestBody` DTOs with `@Valid`, Spring MVC triggers Bean Validation, and when field constraints fail it typically throws `MethodArgumentNotValidException` (default HTTP 400). Simply placing `@UserCode` on a field without triggering validation on the object means JSON binding by itself does not always invoke the provider. With `@Validated`, the application can also select groups; with direct method validation, mechanisms/exceptions may differ depending on the handler signature.

**Set the boundary clearly:** attribute overriding does not customize `WebDataBinder` and does not change when Spring runs validation. It only adjusts the metadata used by the Bean Validation provider when invoked.

## 9. Verifying overridden metadata

If you suspect values are not being forwarded down, inspect `ConstraintDescriptor` from the provider instead of guessing from messages alone. The snippet below uses `validator` and `Main.UserRequest` from section 4, so it is not a standalone program:

```java
var property = validator.getConstraintsForClass(Main.UserRequest.class)
        .getConstraintsForProperty("code");

var outer = property.getConstraintDescriptors().iterator().next();

for (var component : outer.getComposingConstraints()) {
    System.out.println(component.getAnnotation().annotationType().getSimpleName()
            + " -> " + component.getAttributes());
}
```

You will find `Size` with `min=5`, `max=8` and `Pattern` with `regexp=[A-Z][A-Z0-9_]*` (along with the corresponding overridden messages). Descriptor ordering and attribute map key ordering **are not guaranteed**; verify by constraint/attribute name instead of matching fixed stdout strings.

`ConstraintDescriptor.getAttributes()` reflects the effective values after overriding; this is a very helpful verification tool when dealing with nested annotation composition or multiple `@Pattern`s.

## 10. Common errors and fixes

| Symptom | Common cause | How to fix |
| --- | --- | --- |
| Outer `min`/`max` values have no effect | Missing `@OverridesAttribute`, or declaring a same-named method without mapping | Put the annotation on the method itself, pointing to the right `Size.class` and `name`. |
| Provider reports constraint definition error | Wrong attribute name, wrong type, target is not a direct composing constraint, ambiguous mapping | Check the target constraint's API; inspect `ConstraintDefinitionException` and descriptors. |
| Two `@Pattern`s present, wrong one overridden | Missing or wrong `constraintIndex` | Specify index `0`/`1` per declaration order, or array order inside `@Pattern.List`. |
| Only one broad message appears | `@ReportAsSingleViolation` is present | Remove that annotation if you want to see individual component errors. |
| Entering `null` is still valid | `@Size`/`@Pattern` allow `null` | Combine with `@NotNull` or `@NotBlank` per business rules. |
| Spring misses request body errors | Missing provider or DTO validation not triggered | Add the validation starter, use `@Valid @RequestBody`, check handler and tests. |
| `jakarta.validation` imports not found | Mixing legacy `javax.validation` dependencies with Spring Boot 3 / Jakarta | Align dependencies and imports with the Spring/Jakarta generation in use. |
| Want to override a constraint two levels deep | `@OverridesAttribute` forwards only to direct composing constraints | Design forwarding at each required composition level. |

In addition, do not use `@OverridesAttribute` to change a value type unsupported by the constraint, such as converting `int` to `String`. For brand-new rules not expressible with built-in constraints, consider writing a dedicated `ConstraintValidator` instead of forcing composition.

## 11. Self-check exercises

1. Change `@UserCode(min = 5, max = 8)` to `@UserCode(min = 3, max = 6)`; predict the results for `"AB"` and `"ABC_12"`, then run to compare.
2. Add `@NotBlank` as a composing constraint of `@UserCode`. Re-test `null` and `""` inputs; analyze how the violation count changes.
3. Switch `@UserCode` to `@ReportAsSingleViolation`, then submit a value failing both length and format. Compare violation counts and message types.
4. For `@StartUpperEndDigit`, change `firstMessage` and `secondMessage` at usage sites; verify each change affects only one `@Pattern`.
5. Use `ConstraintDescriptor` to inspect the actual `min`, `max`, and `regexp`: when non-default values are passed on the outer annotation, component metadata must reflect the new values.

One way to remember it: **the outer annotation exposes the configuration API; `@OverridesAttribute` wires each attribute of that API to a composing constraint; the provider validates using the wired values; `@ReportAsSingleViolation` decides how messages are aggregated when composition fails.**

## Official reference material

- [Jakarta Bean Validation 3.0 — Constraint composition](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html#constraintcomposition)
- [Jakarta Validation API — `@OverridesAttribute`](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/overridesattribute)
- [Hibernate Validator 8 — Reference Guide, Constraint composition](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/#section-constraint-composition)
- [Spring Framework — Java Bean Validation integration](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring MVC — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)