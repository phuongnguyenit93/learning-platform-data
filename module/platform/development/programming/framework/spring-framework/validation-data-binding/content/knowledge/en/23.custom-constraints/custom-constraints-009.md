# Constraint Composition and `@ReportAsSingleViolation` in Jakarta Bean Validation

## 1. Purpose and context

In Spring Framework, a business rule often imposes multiple conditions on a single value. For instance, a username must be non-null/non-blank, 4 to 12 characters long, start with a lowercase letter, and contain only lowercase letters, digits, or underscores. You could attach `@NotBlank`, `@Size`, and `@Pattern` directly on each field; however, when the same rule appears across many DTOs, parameters, and models, repetition makes configuration and error messages inconsistent.

**Constraint composition** lets you define a high-level constraint annotation from built-in or custom constraints. `@ReportAsSingleViolation` controls **how errors are reported** for a composed constraint: if any component fails, the result can be reported as **a single violation of the high-level annotation**, rather than multiple violations from individual components.

Two purposes must be kept separate:

- **Composition:** reusing a set of conditions and grouping business meaning under one name, such as `@SafeUsername`.
- **Single-error reporting:** providing one broad, stable message to users or API consumers via `@ReportAsSingleViolation`.

This guide uses **Jakarta Validation** (package `jakarta.validation.*`), fitting Spring Framework 6 / Spring Boot 3. For Spring 5 / Boot 2 projects, the legacy API uses `javax.validation.*`; do not mix the two import families in the same example.

## 2. How constraint composition works

A custom annotation becomes a constraint when declared with `@Constraint`. To **only compose** other constraints without custom validation logic, use `@Constraint(validatedBy = {})`. Place the composing annotations, such as `@NotBlank`, `@Size`, and `@Pattern`, **on the new annotation declaration itself**.

By default, components combine with logical **AND**: a value is valid only if **all** components are valid. If the high-level annotation also has its own `ConstraintValidator`, that validator participates in checking too. Components are not replaced by the high-level annotation's validator.

With an ordinary composed constraint, failing components can emit **separate `ConstraintViolation`s**. For example, an empty string violates `@NotBlank`, `@Size(min = 4)`, and a `@Pattern` requiring a leading letter, potentially producing three errors on the same property.

With `@ReportAsSingleViolation` placed **on the composed annotation definition**:

1. The acceptance condition remains the logical **AND** of the components (in standard Jakarta Validation).
2. When a component is invalid, individual component error reports are suppressed; a single error representing the **high-level constraint** is returned with the high-level annotation's `message()`.
3. Per the specification, component evaluation stops on the first failure. **Do not rely on component evaluation order** to perform side effects or choose specific messages.
4. The "single violation" rule applies per **one composed constraint declaration at one site**. A bean with errors on other fields or other independent constraints on the same field can still return multiple errors.

`@ReportAsSingleViolation` does **not** make invalid data valid, does not automatically turn a set of conditions into OR, and is not an annotation placed directly on a field to bundle loose annotations.

## 3. Java 17+ example: from three errors to one error

The example below runs standalone using Maven, the Jakarta Validation API, and Hibernate Validator 8. Create the structure:

```text
constraint-composition-demo/
├── pom.xml
└── src/main/java/
    ├── SafeUsername.java
    └── Demo.java
```

**`pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>constraint-composition-demo</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.2.Final</version>
        </dependency>
        <dependency>
            <groupId>org.glassfish</groupId>
            <artifactId>jakarta.el</artifactId>
            <version>4.0.2</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>Demo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`hibernate-validator` provides the Jakarta Validation implementation; `jakarta.el` supports default message interpolation. The example selects versions compatible with Java 17.

**`src/main/java/SafeUsername.java`**

```java
import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import jakarta.validation.ReportAsSingleViolation;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@NotBlank
@Size(min = 4, max = 12)
@Pattern(regexp = "[a-z][a-z0-9_]*")
@ReportAsSingleViolation
@Constraint(validatedBy = {})
@Target({
    ElementType.FIELD,
    ElementType.PARAMETER,
    ElementType.ANNOTATION_TYPE,
    ElementType.TYPE_USE
})
@Retention(RetentionPolicy.RUNTIME)
@Documented
public @interface SafeUsername {
    String message() default
        "Invalid username: use 4-12 chars, start with a-z, then a-z/0-9/_";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
```

Meaning of each part:

- `@NotBlank` rejects `null`, empty strings, and whitespace-only strings.
- `@Size(min = 4, max = 12)` restricts length. For `CharSequence`, `@Size` accepts `null` by itself.
- `@Pattern(regexp = "[a-z][a-z0-9_]*")` requires the first character to be `a-z`; the rest are `a-z`, `0-9`, or `_`. `@Pattern` checks the whole string against the regex and accepts `null` by itself.
- `@Constraint(validatedBy = {})` means no redundant `ConstraintValidator` is written to duplicate the three conditions; the composing constraints perform the checks.
- `@Target` specifies usage sites; `ANNOTATION_TYPE` allows this constraint itself to be composed at another level. `@Retention(RUNTIME)` is needed so the provider can read the annotation at runtime.
- `message`, `groups`, and `payload` are the attributes required by the constraint declaration contract. `groups` enables validation group selection; `payload` carries application metadata.

**`src/main/java/Demo.java`**

```java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.util.Set;

public class Demo {
    static final class Direct {
        @NotBlank
        @Size(min = 4, max = 12)
        @Pattern(regexp = "[a-z][a-z0-9_]*")
        String username;

        Direct(String username) {
            this.username = username;
        }
    }

    static final class Composed {
        @SafeUsername
        String username;

        Composed(String username) {
            this.username = username;
        }
    }

    public static void main(String[] args) {
        ValidatorFactory factory = Validation.buildDefaultValidatorFactory();
        try {
            Validator validator = factory.getValidator();

            Set<ConstraintViolation<Direct>> direct =
                validator.validate(new Direct(""));
            Set<ConstraintViolation<Composed>> composed =
                validator.validate(new Composed(""));
            Set<ConstraintViolation<Composed>> valid =
                validator.validate(new Composed("alice_01"));

            System.out.println("Direct violations: " + direct.size());
            System.out.println("Composed violations: " + composed.size());
            System.out.println(
                "Message: " + composed.iterator().next().getMessage()
            );
            System.out.println("Valid violations: " + valid.size());
        } finally {
            factory.close();
        }
    }
}
```

Run from the directory containing `pom.xml`:

```bash
mvn -q compile exec:java
```

**Program stdout** (excluding Maven/provider logs written to other streams):

```text
Direct violations: 3
Composed violations: 1
Message: Invalid username: use 4-12 chars, start with a-z, then a-z/0-9/_
Valid violations: 0
```

`Direct` and `Composed` apply **the exact same three conditions** to an empty string; only **how errors are represented** differs. When valid (`alice_01`), all three conditions pass and the violation set is empty. In this example, the high-level annotation's message is a fixed string so the displayed output is deterministic; with messages loaded from a resource bundle, locale can alter the wording.

### Sample inputs to test

| `username` | Reason | `@SafeUsername` |
| --- | --- | --- |
| `""` | Blank, too short, fails pattern | 1 aggregate error |
| `"abc"` | Fewer than 4 characters | 1 aggregate error |
| `"Abcd"` | First letter uppercase | 1 aggregate error |
| `"alice-01"` | Contains `-` outside allowed set | 1 aggregate error |
| `"alice_01"` | Valid length and pattern | 0 errors |
| `null` | Violates `@NotBlank` | 1 aggregate error |

The error count in the example without `@ReportAsSingleViolation` depends on **how many components** fail; the error count with this annotation is **one per failing `@SafeUsername` application**.

## 4. Customizing component attributes with `@OverridesAttribute`

If everywhere requires length 4–12, you can keep the parameters fixed as in the example. If multiple places share the same naming structure yet need different lengths, let annotation users override `@Size` values via `@OverridesAttribute`.

In the **`@SafeUsername` definition above**, keep `@Size(min = 4, max = 12)` and add `import jakarta.validation.OverridesAttribute` plus the two elements below (this is an **add-on snippet**, not a standalone Java file):

```java
@OverridesAttribute(constraint = Size.class, name = "min")
int min() default 4;

@OverridesAttribute(constraint = Size.class, name = "max")
int max() default 12;
```

You can then use `@SafeUsername(min = 6, max = 20)`; the `min`/`max` values on the outer annotation override the corresponding attributes on `@Size`. If the message should reflect the actual numbers, update `message()`, e.g. `"Username must have {min}-{max} characters and match the allowed pattern"`: message interpolation replaces `{min}` and `{max}` with the outer constraint's attributes.

Keep in mind:

- Attribute names and types when overriding must be compatible; e.g. `int` for `Size.min`.
- With multiple components of the same type (e.g. multiple `@Pattern`s), use `constraintIndex` to target the right declaration when needed; do not assume one attribute automatically overrides all of them.
- `groups`, `payload`, and `validationAppliesTo` of composing constraints are not customizable in the ordinary way: values/context are inherited from the high-level constraint per the specification.
- If you change the length condition while keeping a hardcoded "4–12" message, results will be misleading; keep messages and logic synchronized.

## 5. Applying in Spring MVC

With Spring Boot 3, web projects usually include the `spring-boot-starter-validation` dependency. Spring uses the Jakarta Validation provider to validate DTOs when a `@RequestBody` parameter is marked with `@Valid`.

The example **only illustrates the integration part in a Spring Boot project with Spring Web and the Validation starter**; reuse `SafeUsername.java` defined above:

```java
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

class CreateUserRequest {
    @SafeUsername
    public String username;
}

@RestController
class UserController {
    @PostMapping("/users")
    ResponseEntity<String> create(@Valid @RequestBody CreateUserRequest request) {
        return ResponseEntity.ok(request.username);
    }
}
```

When a client sends `{"username": ""}`, validation of `CreateUserRequest.username` fails. With default MVC handling, an invalid `@Valid @RequestBody` typically produces an HTTP 400 response via `MethodArgumentNotValidException` (if the application defines a custom handler, the response structure may differ). `@SafeUsername`'s message can appear as **a single field error** for this constraint, helping the API return more consistent error codes and messages.

For controller or service method parameter validation, how method validation is triggered depends on the Spring version and configuration (such as `@Validated` in certain scenarios). Do not confuse `@ReportAsSingleViolation` with a validation trigger mechanism: it **only determines how a composed constraint reports errors after validation runs**.

For critical input rules, remember that Bean Validation is only one layer of data checking. The system must still check business conditions at the right processing boundaries and protect data integrity at the storage layer when needed.

## 6. Design choices and common pitfalls

### When to compose vs write a custom validator?

**Prefer composition** when the rule can be expressed completely using existing constraints and is reused: postal codes, product codes, usernames, format-plus-length combinations. **Write a dedicated `ConstraintValidator`** when the rule needs algorithms or state that components cannot express (such as cross-field dependencies or complex business rules). Both a custom validator and composing constraints can be used together on the same annotation if needed; by default they participate together via AND.

### Misconceptions to avoid

1. **Placing `@ReportAsSingleViolation` on a field:** wrong target; it is declared on the **composed constraint annotation** (a meta-annotation targeting `ANNOTATION_TYPE`).
2. **Assuming this annotation performs logical OR:** in standard Jakarta Validation, composition is **AND**. Hibernate Validator has a proprietary `@ConstraintComposition` extension for OR/NOT; relying on that extension makes code less portable to other providers.
3. **Forgetting `@Constraint(validatedBy = {})`:** an annotation composed from other annotations must still be declared as a constraint; an empty array indicates no additional validator.
4. **Forgetting `@Retention(RUNTIME)`, `@Target`, or the three mandatory attributes:** can cause definition errors, compile errors, or the provider failing to recognize it properly.
5. **Composing constraints that do not support the same data type:** `@Pattern` fits `CharSequence`, not arbitrarily on `Integer`; components and the outer constraint must have compatible target types.
6. **Thinking `@Size` or `@Pattern` forbids `null` on its own:** these constraints normally treat `null` as valid; add `@NotNull` or `@NotBlank` per the intended rule.
7. **Expecting strictly one error for the whole object:** it only aggregates errors belonging to **one composed constraint**. Other fields, other list elements, or other independent constraints can still produce errors.
8. **Relying on `ConstraintViolation` iteration order:** the return value is a `Set`; message order is not guaranteed. When using `@ReportAsSingleViolation`, present the high-level message rather than relying on "the first child error".
9. **Mixing `javax.validation` and `jakarta.validation`:** pick the API matching your Spring generation; avoid duplicate dependencies and wrong imports.
10. **Using a broad message when the API needs detailed remediation guidance:** reporting one error is concise, yet hides which component failed. For input forms needing condition-by-condition hints, consider **omitting** `@ReportAsSingleViolation`, or designing appropriate error codes/guidance at the API layer.

### Checklist when building a composed constraint

- Do all component conditions genuinely belong to the same business rule, and are supported data types consistent?
- Does the default AND satisfy the requirement?
- Do you want to return individual component errors to help fix input, or one aggregate business error?
- Is `message` accurate when attribute values are overridden via `@OverridesAttribute`?
- Have you tested valid inputs, `null`, empty, too short, too long, and invalid pattern characters?
- Have you tested on DTOs/parameters with your project's exact Spring/Jakarta Validation version?

## 7. Practical conclusion

For the need of "a meaningful, reused set of business conditions", define a composed constraint and attach it directly to fields/parameters. By default the system evaluates **all conditions with AND** and may emit multiple component errors. When you only want users/APIs to see **one high-level error per composed constraint**, place `@ReportAsSingleViolation` on the annotation definition, write a clear `message`, and test both error count and message text.

References:

- [Jakarta Bean Validation specification – Constraint composition](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Jakarta Validation API – ReportAsSingleViolation](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/ReportAsSingleViolation.html)
- [Hibernate Validator Reference Guide – Constraint composition](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/)
