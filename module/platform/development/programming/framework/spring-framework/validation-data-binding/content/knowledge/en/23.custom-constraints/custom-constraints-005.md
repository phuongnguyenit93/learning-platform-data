# Defining Behavior When the Validated Value Is `null` in Custom Constraints

## 1. Context and principles

In Spring Framework, a common way to validate input data is using Jakarta Bean Validation with `@Valid`, `@Validated`, and annotations such as `@NotNull`, `@Pattern`, or user-defined constraints. For a custom constraint, the logic lives in `ConstraintValidator<A, T>#isValid(T value, ConstraintValidatorContext context)`.

**A custom constraint does not automatically skip `null`.** The `isValid` method itself decides whether to return `true` (valid) or `false` (invalid) when the value is `null`. Per Jakarta Bean Validation recommendations, constraints checking *content/format when a value is present* should usually accept `null`; the requirement *that a value must be present* should be declared separately with `@NotNull`.

For example: a product code must match the pattern `ABC-1234`, but only when the user supplies a code. There are two independent requirements:

- **Format:** `@Sku` verifies the entered code matches the pattern and returns `true` on `null`.
- **Presence:** `@NotNull` prevents the code from being `null`. Combine `@NotNull @Sku` when both presence and format are required.

This rule lets a single `@Sku` be reused for both optional and required fields; error messages also accurately reflect whether the problem is *missing data* or *invalid format*.

## 2. Distinguishing `null`, empty, and malformed

`null` means there is no reference to a value. It differs from an empty string `""` and a whitespace-only string `"   "`. Bean Validation does not treat these three states as identical by default.

| Constraint | `null` | `""` | `"   "` | Meaning |
| --- | --- | --- | --- | --- |
| `@NotNull` | Invalid | Valid | Valid | Only forbids `null` |
| `@NotEmpty` (string) | Invalid | Invalid | Valid | Forbids `null` and zero-length strings |
| `@NotBlank` (string) | Invalid | Invalid | Invalid | Requires at least one non-whitespace character |
| `@Size`, `@Pattern` | Valid | Depends on condition | Depends on condition | Checks a present value; does not require presence itself |
| `@Sku` in the example | Valid | Invalid | Invalid | Optional code, but if entered it must match the pattern |
| `@Null` | Valid | Invalid | Invalid | Accepts `null` only |

On the same field, `@NotNull @Sku` rejects `null` via `@NotNull`; `@Sku` can still return `true` for `null` without invalidating the other constraint. When multiple constraints fail together, the system may return multiple violations; do not rely on the iteration order of `Set<ConstraintViolation<?>>`.

## 3. Designing a `null` policy for a custom constraint

**Policy A — field may be absent, but if present must be valid (recommended for format constraints):**

```java
@Override
public boolean isValid(String value, ConstraintValidatorContext context) {
    if (value == null) {
        return true; // Requiredness is decided by @NotNull
    }
    return value.matches("[A-Z]{3}-[0-9]{4}");
}
```

**Policy B — required field:** keep the validator from Policy A and place `@NotNull @Sku` on the field. This expresses two distinct rules and keeps the validator reusable.

**Policy C — the constraint itself must forbid `null` by explicit contract:** you may return `false` on `null`, but document it clearly in the annotation docs and tests. Do not do this merely because you forgot to handle `null`; if the issue is "required input", `@NotNull` is usually clearer.

Do not call `value.length()`, `value.matches(...)`, or dereference child fields before handling `null`. A `NullPointerException` inside `isValid` is not a valid violation produced by returning `false`; it causes validation to fail with an exception. The validator must also never mutate the input value and must be safe for concurrent use.

## 4. Runnable Java 17 example with Jakarta Bean Validation

The following example has two fields: `requiredSku` (required) and `optionalSku` (optional). They use the same `@Sku` constraint.

Create a standard Maven project, Java 17+, with the structure:

```text
pom.xml
src/main/java/demo/validation/Sku.java
src/main/java/demo/validation/SkuValidator.java
src/main/java/demo/validation/ProductForm.java
src/main/java/demo/validation/NullPolicyDemo.java
```

**`pom.xml`** — uses Jakarta Bean Validation 3.x and Hibernate Validator 8.x as the provider (in a Spring Boot 3.x project that already includes `spring-boot-starter-validation`, you usually do not need to declare these sample dependencies directly).

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>null-validation-policy</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
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
      </plugin>
    </plugins>
  </build>
</project>
```

**`Sku.java`** — standard constraint declaration. `message`, `groups`, and `payload` are the mandatory parts of a constraint annotation.

```java
package demo.validation;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Target({
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.PARAMETER,
    ElementType.ANNOTATION_TYPE
})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = SkuValidator.class)
public @interface Sku {
    String message() default "must match AAA-1234";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
```

**`SkuValidator.java`** — validates the format while allowing `null`.

```java
package demo.validation;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public final class SkuValidator implements ConstraintValidator<Sku, String> {
    @Override
    public boolean isValid(String value, ConstraintValidatorContext context) {
        if (value == null) {
            return true;
        }
        return value.matches("[A-Z]{3}-[0-9]{4}");
    }
}
```

**`ProductForm.java`** — specifies requiredness at the constraint usage site.

```java
package demo.validation;

import jakarta.validation.constraints.NotNull;

public final class ProductForm {
    @NotNull
    @Sku
    private final String requiredSku;

    @Sku
    private final String optionalSku;

    public ProductForm(String requiredSku, String optionalSku) {
        this.requiredSku = requiredSku;
        this.optionalSku = optionalSku;
    }
}
```

**`NullPolicyDemo.java`** — runs an input matrix. To keep stdout deterministic, the program prints the failing annotation name instead of localized messages, then sorts the errors.

```java
package demo.validation;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import java.util.List;

public final class NullPolicyDemo {
    private static void check(Validator validator, String caseName, ProductForm form) {
        List<String> errors = validator.validate(form).stream()
            .map(v -> v.getPropertyPath() + ":" +
                v.getConstraintDescriptor().getAnnotation()
                    .annotationType().getSimpleName())
            .sorted()
            .toList();

        System.out.println(caseName + " => " +
            (errors.isEmpty() ? "OK" : String.join(", ", errors)));
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory = Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            check(validator, "null/null", new ProductForm(null, null));
            check(validator, "valid/null", new ProductForm("ABC-1234", null));
            check(validator, "bad/null", new ProductForm("abc-1234", null));
            check(validator, "valid/empty", new ProductForm("ABC-1234", ""));
        }
    }
}
```

Run from the directory containing `pom.xml`:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=demo.validation.NullPolicyDemo
```

Expected stdout (excluding Maven/provider logs if the environment has custom logging):

```text
null/null => requiredSku:NotNull
valid/null => OK
bad/null => requiredSku:Sku
valid/empty => optionalSku:Sku
```

**Why:** `requiredSku = null` violates only `@NotNull`; `@Sku` accepts `null`. `optionalSku = null` is valid. When `optionalSku = ""`, it is present but malformed, so `@Sku` rejects it. When `requiredSku = "abc-1234"`, the code fails because three uppercase letters and four digits are required.

## 5. Applying in Spring MVC and data binding

In a Spring MVC application with a Bean Validation provider (for example the `spring-boot-starter-validation` dependency), you can declare a DTO as follows. This is an **integration snippet** inside a configured controller, not a standalone Java program:

```java
public record CreateProductRequest(
    @NotNull @Sku String requiredSku,
    @Sku String optionalSku
) {}

@PostMapping("/products")
public ResponseEntity<Void> create(@Valid @RequestBody CreateProductRequest body) {
    // Only process when constraints applied to body are valid.
    return ResponseEntity.noContent().build();
}
```

Here `@Valid` instructs Spring to validate the DTO constraints after the object has been created/bound successfully. With JSON like `{"requiredSku":null,"optionalSku":null}`, `requiredSku` violates `@NotNull`. With `{"requiredSku":"ABC-1234","optionalSku":null}`, both fields are valid under these two constraints.

Distinguish the processing layers:

1. **Data reading and type conversion/binding:** malformed JSON, failure to instantiate the object, or failure to convert a string to a numeric type may be rejected **before** `ConstraintValidator` runs. A missing JSON field may map to `null` for a reference-type property, though the exact outcome depends on Jackson/constructor/default-value configuration.
2. **Bean Validation:** once the DTO exists, `@Valid` checks the fields; `@NotNull` checks presence, and `@Sku` checks format when a value is present.
3. **HTTP error handling:** Spring MVC typically turns `@Valid @RequestBody` validation errors into a client error response when no `BindingResult`/custom handler is present. The response structure depends on the application's exception handling configuration.

Do not confuse `@RequestBody(required = true)` with `@NotNull` on *a property*. `required = true` mainly concerns the presence of the entire request body, and does not replace requiredness constraints on individual fields.

### Relation to `@Valid` on nested objects

`@Valid` only requests deep validation when the referenced object exists. If the child object is `null`, cascading validation skips it. When a child object is required, place both:

```java
@NotNull
@Valid
private Address shippingAddress;
```

Similarly, `@Valid` **does not forbid `null` on its own**. Allowing `null` to pass in a custom constraint does not mean Spring skipped all checks on that field: other constraints are still evaluated according to their rules.

### If using `org.springframework.validation.Validator` manually

Spring also has its own `Validator` interface with `supports(Class<?>)` and `validate(Object target, Errors errors)`. This **is not** `jakarta.validation.ConstraintValidator` and does not share the `isValid(value, context)` contract above. When writing a Spring `Validator` manually, you must explicitly decide how to handle `null` properties and record errors using `errors.rejectValue(...)` or appropriate helpers; do not assume Bean Validation's `null` conventions automatically apply to custom-written logic. When a project already integrates Jakarta Bean Validation, prefer a dedicated constraint annotation for reusable format rules.

## 6. Cases requiring an explicit policy decision

| Business requirement | Representation | Behavior on `null` |
| --- | --- | --- |
| Optional promo code; if entered, must match format | `@Sku` | Valid |
| Required product code matching format | `@NotNull @Sku` | Invalid via `@NotNull` |
| Required name, whitespace-only not allowed | `@NotBlank` | Invalid |
| Field must always be absent at a processing step | `@Null` | Valid |
| Required nested object whose child fields must also be validated | `@NotNull @Valid` | Invalid via `@NotNull` |
| Optional value where empty string must mean "not provided" | Normalize input explicitly per API contract, or design a dedicated policy validator | Must not assume `""` equals `null` by default |

**Note on validation groups:** `@Validated(SomeGroup.class)` selects the constraint group to execute; it does not alter the `null` semantics of individual constraints. A `@NotNull` placed in an inactive group will not protect the value during that validation pass.

## 7. Testing and common pitfalls

When designing a new constraint, at minimum test `null`, empty string, whitespace-only, malformed data, valid data, and combinations with `@NotNull`. For class-level validators, also test a `null` root object if callers invoke `isValid` directly; for nested `@Valid`, distinguish that cascading is skipped when the child reference is `null`.

Pitfalls to avoid:

- **Dereferencing before checking `null`:** `value.trim()`, `value.length()`, or accessing child fields causes a `NullPointerException`. Put the `null` check at the top of `isValid`.
- **Letting all empty strings pass just because `null` passes:** `null`, `""`, and `" "` have different meanings; the policy for each state must be specified.
- **Baking requiredness into every format constraint:** reduces reusability and can produce confusing error messages. Use `@NotNull` or `@NotBlank` when they express the requirement accurately.
- **Assuming `@Valid` is equivalent to `@NotNull`:** this annotation triggers validation/cascading in the appropriate context, not a presence check.
- **Assuming Spring always invokes the validator:** there must be a provider, an appropriate validation trigger (`@Valid`, `@Validated`, `Validator#validate`, or corresponding config), and data must pass the binding step.
- **Skipping group/error-path tests:** the constraint might not belong to the active group; actual responses also depend on Spring configuration.

**Rule of thumb:** A constraint checking *what a value looks like* usually `return true` on `null`; a constraint checking *whether a value must exist* must be declared explicitly. Design both decisions independently and test both.

## References

- Jakarta Bean Validation Specification — `ConstraintValidator` implementation section and recommendation to separate `null` handling from content constraints: https://beanvalidation.org/2.0/spec/
- Hibernate Validator Reference Guide — creating custom constraints, `isValid`, and cascade validation: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Spring Framework Reference — Java Bean Validation, Spring `Validator`, and `DataBinder`: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring MVC Reference — validation on controller methods: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html