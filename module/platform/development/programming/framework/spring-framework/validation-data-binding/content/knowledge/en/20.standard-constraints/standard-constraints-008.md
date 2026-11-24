# @AssertTrue and @AssertFalse

> **Context:** Two standard boolean constraints of Jakarta Bean Validation in Java and Spring Framework. This lesson focuses on the meaning of `true`/`false`/`null`, choosing `boolean` vs. `Boolean`, combining `@NotNull` when data must be sent, validating conditions derived from multiple fields, and how Spring MVC triggers validation. Executable standalone example uses Java 17+ and the Jakarta Validation provider from Spring Boot 3.3.x.

## 1. Definition and Purpose

`@AssertTrue` and `@AssertFalse` belong to `jakarta.validation.constraints`. They assert that **the boolean value of an element is in the desired state**.

- `@AssertTrue`: value is valid when `true`; `false` violates.
- `@AssertFalse`: value is valid when `false`; `true` violates.
- **Both treat `null` as valid**, per Jakarta Bean Validation. If a value must be provided, add `@NotNull` on `Boolean`.
- **Standard supported types:** primitive `boolean` and wrapper `java.lang.Boolean`. Do not apply these two annotations directly to `String`, `Integer`, `List`, or non-boolean objects.

They are *constraints on values*, not Java checks that run automatically when calling setters/constructors. Putting an annotation on a field is only a declaration; only when Bean Validation is triggered (e.g., `Validator.validate(bean)`, `@Valid` in Spring MVC) does the provider evaluate the constraint.

### Baseline Behavior Table

| Actual Value | `@AssertTrue` | `@AssertFalse` | `@NotNull` |
| --- | --- | --- | --- |
| `Boolean.TRUE` | Valid | Violation | Valid |
| `Boolean.FALSE` | Violation | Valid | Valid |
| `null` (`Boolean`) | **Valid** | **Valid** | Violation |
| `true` (primitive `boolean`) | Valid | Violation | Cannot be null |
| `false` (primitive `boolean`) | Violation | Valid | Cannot be null |

**Do not confuse `@AssertFalse` with "require the client to confirm no".** It allows `null`, meaning if business rules require an explicit `false` answer, use `@NotNull @AssertFalse Boolean field`. Similarly, `@AssertTrue` alone does not guarantee the user sent `true` if the field is `Boolean` and missing values become `null`.

## 2. Choosing `boolean` or `Boolean`

### 2.1. Primitive `boolean`: Only Two States

```java
import jakarta.validation.constraints.AssertTrue;

public class Settings {
    @AssertTrue
    private boolean enabled;
}
```

A primitive has two values, `true` or `false`; an unassigned `boolean` field is initialized to `false` by default. Therefore:

- `enabled = true` passes `@AssertTrue`.
- `enabled = false` fails `@AssertTrue`.
- "Not sent / not selected" cannot be represented as null.
- If a class is instantiated via a constructor without passing the field or a binder assigns defaults, a missing value and sending `false` **can become indistinguishable**. HTTP behavior also depends on mappers, setters, constructors, and binding configuration.

`@NotNull` on primitive `boolean` is useless: primitives cannot be null. Do not use `@NotNull` to distinguish "missing" from `false` when the type is already primitive.

### 2.2. Wrapper `Boolean`: Three States, Allowing Explicit User Answers

```java
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotNull;

public class TermsInput {
    @NotNull
    @AssertTrue
    private Boolean acceptedTerms;
}
```

This is an illustrative DTO without constructors/getters/setters. With `Boolean`, code can distinguish:

1. `null`: not provided or unspecified → `@NotNull` catches it.
2. `false`: answered, yet not agreed → `@AssertTrue` catches it.
3. `true`: answered and agreed → both pass.

If you only use `@AssertTrue Boolean acceptedTerms` without `@NotNull`, null **still passes**. The same applies to `@AssertFalse`:

```java
@NotNull
@AssertFalse
private Boolean disabledByPolicy;
```

This combination requires the value to be provided **and be `false`**. Use it for business flags where the API genuinely requires an explicit "no" answer, not merely for a field that defaults to false in the UI.

### 2.3. A Common Pitfall with JSON APIs

With a DTO containing `Boolean agreed` and standard Spring/Jackson configuration, the following requests have different meanings:

```json
{"agreed": true}
```

```json
{"agreed": false}
```

```json
{"agreed": null}
```

```json
{}
```

When the mapper creates the DTO and leaves `agreed = null` for a missing property, these three cases (false/null/missing) are not identical:

- `false`: `@AssertTrue` reports a violation; `@NotNull` passes.
- `null`: `@AssertTrue` passes; `@NotNull` reports a violation.
- Missing property: if the mapper leaves it null, behaves like null; however, strict constructors/records or Jackson settings may handle missing fields before validation.

**Do not assume every missing field always becomes null or every wrong-type value reaches Bean Validation.** Some JSON errors may be rejected by Jackson during deserialization, before Bean Validation runs. In API contracts, send JSON boolean literals `true`/`false`, rather than relying on whether a mapper allows coercion from `"true"` or `1`.

## 3. Runnable Java 17+ Example: Both Constraints and Null Handling

The example below uses a `ValidatorFactory`, checks `Boolean` values, compares required-answer cases, and then verifies a property computed from two numeric fields. For stable output, the program prints only sorted field paths and annotation names, without locale-dependent messages.

Structure:

```text
boolean-constraints/
├── pom.xml
└── src/main/java/demo/BooleanConstraintsDemo.java
```

**`pom.xml`**: uses Spring Boot's validation starter to supply the Jakarta Validation API and Hibernate Validator. The program runs as Java `main`, **without starting a Spring application**.

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
    <artifactId>boolean-constraints</artifactId>
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

**`src/main/java/demo/BooleanConstraintsDemo.java`**:

```java
package demo;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.AssertFalse;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotNull;

import java.util.List;

public class BooleanConstraintsDemo {

    static final class Flags {
        @AssertTrue
        private final Boolean active;

        @AssertFalse
        private final Boolean archived;

        Flags(Boolean active, Boolean archived) {
            this.active = active;
            this.archived = archived;
        }
    }

    static final class RequiredConsent {
        @NotNull
        @AssertTrue
        private final Boolean accepted;

        RequiredConsent(Boolean accepted) {
            this.accepted = accepted;
        }
    }

    static final class Range {
        private final int from;
        private final int to;

        Range(int from, int to) {
            this.from = from;
            this.to = to;
        }

        // A boolean getter can express a condition between two fields.
        @AssertTrue
        public boolean isOrdered() {
            return from <= to;
        }
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            inspect(validator, "flags.null",
                    new Flags(null, null));
            inspect(validator, "flags.wrong",
                    new Flags(false, true));
            inspect(validator, "flags.correct",
                    new Flags(true, false));

            inspect(validator, "consent.null",
                    new RequiredConsent(null));
            inspect(validator, "consent.false",
                    new RequiredConsent(false));
            inspect(validator, "consent.true",
                    new RequiredConsent(true));

            inspect(validator, "range.invalid",
                    new Range(10, 5));
            inspect(validator, "range.valid",
                    new Range(5, 10));
        }
    }

    private static void inspect(
            Validator validator, String name, Object input) {
        List<String> violations = validator
                .validate(input)
                .stream()
                .map(v -> v.getPropertyPath()
                        + ":"
                        + v.getConstraintDescriptor()
                                .getAnnotation()
                                .annotationType()
                                .getSimpleName())
                .sorted()
                .toList();

        System.out.println(name + " -> " + violations);
    }
}
```

Run from the directory containing `pom.xml` with Java 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.BooleanConstraintsDemo
```

**Lines printed by the program** (ignoring auxiliary Maven or provider logs if any):

```text
flags.null -> []
flags.wrong -> [active:AssertTrue, archived:AssertFalse]
flags.correct -> []
consent.null -> [accepted:NotNull]
consent.false -> [accepted:AssertTrue]
consent.true -> []
range.invalid -> [ordered:AssertTrue]
range.valid -> []
```

Analysis:

- `Flags(null, null)` is valid because both annotations allow null.
- `Flags(false, true)` has two violations: `active` must be true and `archived` must be false.
- `Flags(true, false)` satisfies both constraints.
- `RequiredConsent(null)` violates **`@NotNull`**, without violating `@AssertTrue`.
- `RequiredConsent(false)` violates **`@AssertTrue`**, without violating `@NotNull`.
- `RequiredConsent(true)` is valid.
- `Range(10, 5)` has getter `isOrdered()` returning false, violating `@AssertTrue` on property `ordered`.
- `Range(5, 10)` returns true, so it is valid.

In `Range`, `isOrdered()` is a parameterless **JavaBeans-style getter** returning primitive boolean. Bean Validation invokes the getter to check the property constraint. The example uses this approach to express a simple rule involving two fields; it does not turn `@AssertTrue` into an annotation placed directly on the class.

`ValidatorFactory` is created once and closed with `try-with-resources`. `Validator` can be reused across multiple `validate(...)` calls and has no separate `close()` method. Violations are sorted so output does not depend on `Set` iteration order.

## 4. Placing Annotations on Fields, Getters, and Derived Expressions

### 4.1. Field Validation: Checking Stored Data

```java
import jakarta.validation.constraints.AssertFalse;
import jakarta.validation.constraints.AssertTrue;

public class UserPreferences {
    @AssertTrue
    private Boolean visible;

    @AssertFalse
    private Boolean blocked;
}
```

This is an illustrative DTO snippet without constructors/getters/setters. The provider inspects the corresponding field values. You can annotate `private` fields; compliant Jakarta Validation providers still read field constraint metadata during validation.

### 4.2. Getter Validation: Checking a Derived Property

A condition involving multiple fields can sometimes be expressed concisely as a boolean getter:

```java
import jakarta.validation.constraints.AssertTrue;
import java.time.LocalDate;

public class TravelDates {
    private LocalDate departure;
    private LocalDate returnDate;

    @AssertTrue(message = "returnDate must not precede departure")
    public boolean isChronological() {
        return departure == null
                || returnDate == null
                || !returnDate.isBefore(departure);
    }
}
```

This illustrates the derived property `chronological`. The getter returns true when either date is absent or the return date is not before departure; to require both dates, place **`@NotNull` separately on each field**. Do not cram null checks and cross-field validity into one confusing expression when specific error reporting is desired.

When `isChronological()` returns false, the violation typically has `propertyPath` equal to `chronological`. If the API needs to attach the error directly to `returnDate`, consider writing a **custom class-level constraint** with `ConstraintValidatorContext` to produce a more meaningful path.

**Watch out for a side effect:** A public getter `isChronological()` may be treated by Jackson as a JSON property when serializing a JavaBean. In REST DTOs, if the getter is only for validation and should not appear in JSON output, use `@JsonIgnore` appropriately or separate DTO/validation logic. Check your actual Jackson configuration; `@AssertTrue` is not a JSON-control annotation.

### 4.3. Do Not Annotate Both Field and Getter for the Same Rule Unintentionally

```java
@AssertTrue
private Boolean accepted;

@AssertTrue
public Boolean getAccepted() {
    return accepted;
}
```

If both constraints are discovered, the same value can be **validated twice**, generating unwanted duplicate violations. Choose either field access or property access consistently for a given property. For property validation, place the annotation on the **getter**, not on the setter expecting Bean Validation to run automatically on every setter invocation.

An arbitrary method like `boolean checkBusinessRule()` is not automatically a JavaBeans getter. To use Bean Validation property constraints, define an appropriate `isXxx()`/`getXxx()` getter; for complex whole-object checks, consider a class-level constraint.

## 5. Using with Spring MVC and Spring Boot

### 5.1. Bean Validation Must Be Triggered

In Spring Boot 3.x, use `spring-boot-starter-validation` to include the Jakarta Validation API and provider. In Spring MVC, declare `@Valid` or `@Validated` at the appropriate binding point. Typical JSON request flow:

```text
HTTP JSON body (true / false / null / missing field)
        │
        ▼
Jackson deserialize
        │
        ▼
DTO with boolean or Boolean
        │
        ▼
@Valid @RequestBody → Jakarta Validation
        │
        ├── valid: controller handles request
        │
        └── invalid: validation errors / BindingResult / exception
```

Example **code snippets to add to a Spring Boot Web MVC project**, not a standalone Java file:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotNull;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

public record AcceptTermsRequest(
        @NotNull @AssertTrue Boolean acceptedTerms) {
}

@RestController
public class TermsController {
    @PostMapping("/terms/accept")
    public ResponseEntity<Void> accept(
            @Valid @RequestBody AcceptTermsRequest request) {
        // Runs only after standard validation succeeds.
        return ResponseEntity.noContent().build();
    }
}
```

In an application with Jakarta Validation configured:

| Request Body | Result per Record Constraints |
| --- | --- |
| `{"acceptedTerms": true}` | Valid |
| `{"acceptedTerms": false}` | `@AssertTrue` violates |
| `{"acceptedTerms": null}` | `@NotNull` violates |
| `{}` | If Jackson constructs the record with null for the missing component, `@NotNull` violates; strict constructor binding settings may reject the body earlier |
| Malformed JSON body | May be rejected by the JSON message converter **before** Bean Validation |

In standard Spring MVC configuration, `@Valid @RequestBody` failures are handled by the framework as HTTP 400 if no matching `BindingResult` is present. The JSON error payload format depends on `@ControllerAdvice`/application error handling. Do not assume a single exception or response schema covers all binding and constraint violation cases.

When switching to `@ModelAttribute`/HTML forms, an **unchecked HTML checkbox usually submits no parameter**. Spring data binding has special handling for checkboxes/field markers in certain setups, so the resulting value (`false` or `null`) must be tested with the actual form binding style. You cannot take HTML form behavior and apply it verbatim to JSON `@RequestBody`.

### 5.2. Validation Does Not Equal Business Verification and Security

`@AssertTrue Boolean acceptedTerms` only asserts that the DTO value at validation time is true (if non-null). It **does not prove** the user actually read the terms, does not record a consent audit trail, does not identify the terms version, and does not guarantee the confirmation came from an authenticated user.

A real terms-acceptance flow may require:

- `@NotNull @AssertTrue` to check request data.
- Identifying the logged-in user from the security context.
- Recording timestamp, terms version, consent action, and audit details per system policy.
- Avoiding trusting a client-supplied `acceptedTerms=true` flag alone in place of business proof.

Similarly, `@AssertFalse` on a `banned` flag in a request **does not** prove the account is not banned; that must be server-controlled state. Never use client-supplied values to make authorization decisions.

## 6. What These Annotations Do Not Do

### Do Not Replace `@NotNull`

Per the specification, null satisfies `@AssertTrue` and `@AssertFalse`. If the business question is "did the user explicitly answer?", you must use `Boolean` and `@NotNull` (or an equivalent mechanism) to distinguish unanswered states.

### Do Not Replace String Constraints

If you want `"YES"`, `"NO"`, or non-empty `"true"` strings, that is string data; use `@NotBlank`, `@Pattern`, enums, converters, or custom validators per the data contract. Do not annotate a `String` with `@AssertTrue`; that type is not supported by the standard and can throw `UnexpectedTypeException` on validation.

### Do Not Normalize Input

Neither annotation converts `"true"` to `true`, trims whitespace, fixes casing, or forces clients to send proper JSON literals. Any parsing/coercion happens before validation via configured converters/Jackson.

### Do Not Run Automatically on Every Object

Calling `new TermsInput()` does not run Bean Validation. You must invoke `jakarta.validation.Validator#validate()` or use an integration trigger (`@Valid` at boundaries, method validation, etc.). `@Valid` triggers validation at framework-supported points or marks cascading; it does not make plain Java constructors validate themselves.

### Do Not Return Results in a Fixed Order

`Validator#validate()` returns `Set<ConstraintViolation<T>>`; violation order must not be relied upon as a stable contract. Violation messages may be translated by locale. When writing tests, prefer comparing `propertyPath` and constraint type, or sorting before printing.

## 7. Common Mistakes and Resolutions

| Mistake | Consequence | Right Approach |
| --- | --- | --- |
| Using only `@AssertTrue Boolean agreed` to require user consent | `null` remains valid | Use `@NotNull @AssertTrue Boolean agreed` |
| Using only `@AssertFalse Boolean rejected` to require a "no" answer | `null` remains valid | Use `@NotNull @AssertFalse Boolean rejected` |
| Using primitive `boolean` to distinguish missing from `false` | Primitives cannot represent null | Use `Boolean` and define missing-field handling |
| Putting `@NotNull` on primitive `boolean` | Provides no extra presence guarantee | Use wrapper when null distinction is needed |
| Using `@AssertTrue` on `String` or `int` | No matching standard validator; may throw `UnexpectedTypeException` | Convert types intentionally or use type-appropriate constraints |
| Assuming `@AssertFalse` means "field not sent" | `false` and `null` are both valid yet mean different things | Document API contract clearly and add `@NotNull` if answer is required |
| Annotating a setter or arbitrary method expecting property validation | Constraint may not execute as expected | Annotate valid field/getter; use method validation for method params/returns |
| Annotating both field and getter with the same constraint | Can generate duplicate errors | Choose one consistent access strategy |
| Expecting a multi-field getter to target individual fields automatically | `propertyPath` is usually the derived getter name | Use a class-level custom constraint if detailed paths are needed |
| Using an `isValid()` getter only for validation without checking JSON output | Jackson may serialize the getter as an unintended property | Design DTOs cleanly or use `@JsonIgnore` appropriately |
| Omitting validation implementation dependency | Annotations exist yet validation does not run | Add a provider, such as `spring-boot-starter-validation` in Boot 3 |
| Using `javax.validation.*` imports in Spring Boot 3 | Different Jakarta namespace | Use `jakarta.validation.*` and compatible providers |
| Using `@AssertTrue` instead of server-side authorization checks | Clients can arbitrarily send `true` | Re-verify state, identity, and business rules on the server |
| Comparing verbatim message strings in tests | Easily broken by locale/provider changes | Assert constraint type/path or standardized error codes |

### Boundary with Database-Integrated Constraints

`@AssertTrue` and `@AssertFalse` are Bean Validation rules evaluated **at the point where validation is triggered**. They do not guarantee automatic database constraint generation across every ORM/DDL configuration; do not rely on them to protect boolean columns from other write paths that bypass validation. If data requires database-level invariants, define matching schema and business rules (e.g., `NOT NULL` or CHECK constraints where supported by the DB).

## 8. Self-Check Exercises

Before checking the answers, predict whether `validate(bean)` returns any error.

**Scenario A:** `@AssertTrue Boolean verified`, value null. **Answer:** no violation from `@AssertTrue` because null is valid.

**Scenario B:** `@NotNull @AssertTrue Boolean verified`, value null. **Answer:** `@NotNull` violates; `@AssertTrue` still considers null valid.

**Scenario C:** `@AssertFalse Boolean archived`, value true. **Answer:** violates `@AssertFalse`.

**Scenario D:** `@AssertFalse boolean archived`, unassigned field in a new object. **Answer:** primitive field defaults to false, so `@AssertFalse` alone reports no error.

**Scenario E:** `@AssertTrue boolean isEligible()` is a getter property returning false. **Answer:** violates when Bean Validation inspects the bean and recognizes the getter property. `propertyPath` is typically `eligible`.

**Scenario F:** `@AssertTrue String confirmation` holds `"true"`. **Answer:** `String` is unsupported in standard Jakarta Validation; a constraint configuration error/`UnexpectedTypeException` may occur during validation, not a successful boolean check.

## 9. Implementation Checklist

- [ ] Clearly determined whether business logic expects **true or false**?
- [ ] Chose `boolean` vs. `Boolean` depending on whether "unanswered" must be distinguished?
- [ ] If a `Boolean` field is required, paired `@NotNull` alongside `@AssertTrue`/`@AssertFalse`?
- [ ] Tested all three cases: `true`, `false`, and `null`?
- [ ] For HTTP requests, separately tested missing property, null, false, and wrong JSON types?
- [ ] If using methods/getters, followed JavaBeans conventions and avoided duplicate field + getter annotations?
- [ ] If a getter derives from multiple fields, planned error reporting and tested null cases?
- [ ] Included a Bean Validation provider and execution trigger (`@Valid`/`@Validated`/`Validator.validate`)?
- [ ] Avoided using client-submitted flags as proof of server-side authorization/consent?
- [ ] Verified tests check property path/constraint type, avoiding reliance on message text and `Set` order?

**Remember:** `@AssertTrue` requires **true**; `@AssertFalse` requires **false**; both accept **null** on `Boolean`. When a mandatory answer is required, pair `@NotNull`; when a rule depends on multiple fields, a boolean getter can express it, while weighing error paths, validation responsibilities, and JSON serialization side effects.

### References

- [Jakarta Bean Validation 3.0 — `@AssertTrue` Javadoc](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/AssertTrue.html)
- [Jakarta Bean Validation 3.0 — `@AssertFalse` Javadoc](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/AssertFalse.html)
- [Jakarta Bean Validation Specification 3.0, `8.3–8.4](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Hibernate Validator 8 Reference Guide — Constraint declarations](https://docs.jboss.org/hibernate/validator/8.0/reference/en-US/html_single/)
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring MVC — Method Argument Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
