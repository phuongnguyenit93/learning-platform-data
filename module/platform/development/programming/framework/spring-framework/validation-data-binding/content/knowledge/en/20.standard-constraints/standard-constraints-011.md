# Null Semantics and Combining Multiple Constraints in Bean Validation

## 1. Why Is Understanding Null a Prerequisite?

When building registration forms, order-creation APIs, or business configurations, a data field often must satisfy **multiple independent conditions**. For instance, a username must be provided, not whitespace-only, and between 3 and 12 characters; age must be present and at least 18; a tag list must have 1–3 elements and each tag must be non-empty.

The most error-prone pitfall is that many Jakarta Bean Validation constraints **deliberately treat `null` as valid**, because they only inspect a property of an **existing value**. For example, `@Size(min = 3)` does not mean "at least three characters required": it rejects non-null strings of length 0, 1, or 2, yet **does not reject null**. To make a field required, combine it with an appropriate presence constraint such as `@NotNull`, `@NotEmpty`, or `@NotBlank`.

This lesson focuses on three skills:

1. Reading the exact semantics of `null`, empty strings, whitespace-only strings, empty collections, and null elements.
2. Stacking multiple independent constraints without assuming execution order or a single error message.
3. Choosing among **multiple annotations placed directly**, **reusable composed constraints**, and **class-level constraints** when rules span multiple properties.

This guide uses **Jakarta Bean Validation 3.0** (`jakarta.validation.*`), compatible with Spring Framework 6/Spring Boot 3. In older Spring 5/Boot 2 projects, the legacy namespace may be `javax.validation.*`; align with your provider and framework version.

## 2. Null, "Missing Data", Empty, and Blank Are Not the Same

Before choosing annotations, distinguish the state of the data:

| State | Java Example | Meaning |
| --- | --- | --- |
| Null reference | `String name = null;` | No String object exists to inspect content. |
| Empty string | `String name = "";` | A String object exists, with length 0. |
| Blank string | `String name = "   ";` | A String object exists; length 3, contains no meaningful characters per `@NotBlank`. |
| Formally valid string | `String name = "Minh";` | Data exists to apply length and content rules. |
| Null collection | `List<String> tags = null;` | The list is absent. |
| Empty collection | `List<String> tags = List.of();` | The list exists, yet contains zero elements. |
| Collection with a null element | `new ArrayList<>(Arrays.asList((String) null))` | The list has one element, whose value is null. |
| Null child object | `Address address = null;` | No child bean exists to cascade into, unless a separate presence constraint is declared. |

At the HTTP boundary there is also the concept of an **omitted field**. JSON without the property, JSON with `"name": null`, and JSON with `"name": ""` can pass through deserializers/binding differently. Bean Validation only operates on the object/value at the moment it is invoked. Therefore, understand binding rules before assuming one constraint can distinguish every "missing" vs. "explicit null" case.

For example, in a DTO storing into a plain `String`: an omitted JSON field may leave the property null; an explicit JSON null may also yield null. After binding, `@NotNull` on the property only knows **the Java value is null**, not whether the client sent the property. If business logic must distinguish "absent" from "sent null" (as in PATCH), use an input model or binding mechanism that tracks presence.

## 3. Rules of Standard Constraints When the Value Is Null

Do not rely on the rule of thumb "every constraint ignores null". **Read each annotation's contract.** Many content-focused constraints allow null, whereas presence constraints do not.

| Standard Constraint | Is `null` Valid? | Primary Check | Notes |
| --- | --- | --- | --- |
| `@Null` | Yes | Requires value to be null | Any non-null value violates. |
| `@NotNull` | **No** | Requires a value to exist | Does not check empty strings or empty Lists. |
| `@NotEmpty` | **No** | String/array/Collection/Map is non-null and non-empty | Whitespace-only strings can still pass. |
| `@NotBlank` | **No** | `CharSequence` has a non-whitespace character | For text; do not place directly on List/Map. |
| `@Size(min, max)` | Yes | String/array length, Collection element count, Map entry count | Both endpoints are inclusive. |
| `@Pattern(regexp)` | Yes | String matches regex | Null is valid; empty string depends on regex. |
| `@Email` | Yes | Email syntax | Details of "valid address" are decided by the provider. |
| `@Min` / `@Max` | Yes | Numeric threshold comparison | Does not turn missing data into 0. |
| `@Positive` / `@Negative` | Yes | Numeric sign | Null remains valid. |
| `@Past` / `@Future` | Yes | Relation to reference time | Null remains valid. |
| `@AssertTrue` / `@AssertFalse` | Yes | Matching boolean value | On `Boolean` wrapper, null is valid. |

This table is based on the **built-in constraints** contract of Jakarta Bean Validation 3.0. Application-defined or third-party annotations may handle null differently; read their `ConstraintValidator.isValid(...)`/Javadoc. Even when a standard annotation allows null, **binding, deserialization, method invocation, or type structure** may still reject missing data before validation starts.

**Important example:**

~~~java
@Size(min = 3, max = 12)
private String name;
~~~

A `null` value passes `@Size`, whereas `""` (length 0) and `"ab"` (length 2) fail. With:

~~~java
@Email
private String email;
~~~

Null passes per the `@Email` contract; to require an email to be present, pair a requiredness constraint. Never assume every email pattern validates all real-world email addresses identically, because the specification leaves detailed syntax criteria to the provider.

## 4. Direct Comparison of @NotNull, @NotEmpty, @NotBlank, and @Size

### 4.1. With String

| Value | `@NotNull` | `@NotEmpty` | `@NotBlank` | `@Size(min=2)` |
| --- | --- | --- | --- | --- |
| `null` | Fail | Fail | Fail | Pass |
| `""` | Pass | Fail | Fail | Fail |
| `" "` | Pass | Pass | Fail | Fail |
| `"  "` | Pass | Pass | Fail | Pass |
| `"ab"` | Pass | Pass | Pass | Pass |
| `"abcdef"` | Pass | Pass | Pass | Pass, if no max limit |

`@NotEmpty` checks that a string has non-zero length; it does not treat whitespace-only strings as empty. `@NotBlank` checks that a string is non-null and has at least one non-whitespace character. `@Size` checks length only and does not call `strip()`.

### 4.2. With List or Map

~~~java
@NotNull
@Size(min = 1, max = 5)
private List<String> members;
~~~

Interpretation:

- `null` is rejected by `@NotNull`, even though `@Size` alone considers null valid.
- `List.of()` is rejected by `@Size(min=1)`.
- A List with 1–5 elements satisfies the count check.
- A null element still **counts as one element**. The two annotations above do not inspect the content of each String.

If the intent is non-null and non-empty, you can write:

~~~java
@NotEmpty
@Size(max = 5)
private List<String> members;
~~~

Thanks to `@NotEmpty`, there is no need to add `@NotNull` solely to forbid null. Do not place `@NotBlank` directly on a `List` because it does not support `Collection` types per spec.

### 4.3. @Null Has Its Own Meaning

`@Null` does not mean "nullable"; it requires **the value to be null**. For example, a server-managed field that clients must not supply themselves:

~~~java
@Null(message = "id must not be supplied on create")
private Long id;
~~~

Requires importing `jakarta.validation.constraints.Null`. A null value is valid; `123` is invalid. For an update DTO, you may require `id` to be non-null via `@NotNull` in a different group. Never place `@Null` and `@NotNull` together in the **same group** on one field expecting any value to satisfy both: they are logically contradictory. To share a class across create/update, design distinct validation groups or use separate DTOs.

## 5. When Must Multiple Constraints Be Combined?

Each annotation answers one narrow question. A required field with data quality rules often needs more than one question:

| Business Requirement | Suggested Declaration | Why |
| --- | --- | --- |
| Name must have characters, 3 to 40 UTF-16 units | `@NotBlank @Size(min=3,max=40)` | Enforces content and checks length. |
| Required product code, length 4–8, uppercase letters/digits only | `@NotBlank @Size(min=4,max=8) @Pattern(regexp="[A-Z0-9]+")` | Presence, length, and format are three rules. |
| Required email, non-blank, max 254 characters | `@NotBlank @Email @Size(max=254)` | Needs presence, format, and length cap. The max number is a business/protocol decision. |
| Age must be present and at least 18 | `@NotNull @Min(18) Integer age` | `@Min` alone accepts null. |
| List must have 1–3 labels, each non-blank | `@NotEmpty @Size(max=3) List<@NotBlank String> labels` | Two levels: collection and element. |
| Address must be present and deeply validated | `@NotNull @Valid Address address` | `@Valid` only cascades when child bean exists. |
| Field filled only by the system on creation | `@Null Long id` | Client must not send a pre-populated ID. |

When requirements are **independent**, placing multiple constraints directly on the field is clearest. You do not need a custom annotation for every `@NotNull @Min` pair. Consider a composed constraint only when the same contract recurs in many places, needs a unified name, or needs centralized error message mapping.

### Step-by-Step String Example

1. `@Size(min=3,max=12)`: if present, must have right length; null is accepted.
2. `@NotNull @Size(min=3,max=12)`: must be non-null; yet `""` and `"  "` are still judged only by length, without guaranteeing characters.
3. `@NotBlank @Size(min=3,max=12)`: must have non-whitespace content and right length.
4. Add `@Pattern(regexp="[A-Za-z0-9_]+")` if restricting characters; note this rule intentionally allows ASCII only. Accented Vietnamese names will not match this regex.

Note: **Multiple constraints are not an ordered if/else chain.** Providers can evaluate constraints in the same group in an unspecified order; for a single value, multiple `ConstraintViolation`s may be produced simultaneously.

## 6. Validation Does Not Normalize, Fix, or Create Data

Annotations only describe conditions; by default they never mutate values.

~~~java
@NotBlank
@Size(min = 3, max = 12)
private String username;
~~~

If `username` is `"  An  "`, it has 6 UTF-16 units and is not whitespace-only; both constraints pass, even though after `strip()` it becomes `"An"` of length 2. If you want to evaluate after trimming, normalize at a well-defined boundary first and validate the result, or write a business-specific constraint. Never auto-trim passwords, signature tokens, or data where whitespace is significant.

Similarly:

- `@NotNull` does not instantiate a missing child object.
- `@NotEmpty` does not insert elements into a list.
- `@Size(max=5)` does not drop a sixth element.
- `@Email` does not fix domain names.
- `@Min(18)` does not bump 16 up to 18.
- `@Valid` does not construct child beans in order to cascade.

With HTTP data, **type converters or deserializers** can turn a String into an Integer, a date string into `LocalDate`, or an omitted value into another Java state before validation. Test the entire pipeline, not just annotations in isolation.

## 7. @Valid and Null in Nested Objects

`@Valid` instructs Bean Validation to traverse into constraints of the referenced object; per the specification, **null references are skipped when cascading**.

~~~java
class CustomerForm {
    @Valid
    Address address;
}

class Address {
    @NotBlank
    String city;
}
~~~

In this example, `address == null` does not produce a violation from `Address.city`. There is no `Address` object to validate. If the address is required:

~~~java
class CustomerForm {
    @NotNull(message = "address is required")
    @Valid
    Address address;
}
~~~

When `address == null`, `@NotNull` rejects it and `@Valid` skips cascading. When `address != null` but `address.city == ""`, Bean Validation cascades into `Address.city`, `@NotBlank` rejects it, and the violation path is typically `address.city`.

This is a critical rule in object-graph APIs: **requiring an object to exist** and **requiring an existing object to be valid** are two separate requirements. If the app allows an absent address, `@Valid` alone may be the right policy; do not blindly attach `@NotNull` without a business requirement.

### Lists and Maps Have Multiple Levels of Null

~~~java
@NotEmpty
@Size(max = 5)
private List<@NotBlank String> tags;
~~~

- Null list: `@NotEmpty` fails.
- Empty list: `@NotEmpty` fails.
- Four-element valid list: passes both List-level constraints.
- Four-element list with one null String: List level passes; `@NotBlank` on the null element fails.
- Six-element list with one blank String: `@Size(max=5)` fails and the element constraint may fail as well.

With child beans:

~~~java
@NotEmpty
private List<@NotNull @Valid Address> addresses;
~~~

The element constraint `@NotNull` forbids null elements, while `@Valid` validates properties of each **non-null** `Address`. Clearly distinguish null List, empty List, and null item as three separate scenarios.

With Map:

~~~java
@NotEmpty
private Map<@NotBlank String, @NotNull @Valid Address> contacts;
~~~

The Map must have entries, keys must be non-blank, values must be non-null, and non-null values are cascaded into. `@NotEmpty` only counts Map entries, without checking keys/values. Violation paths may include Map keys or container element nodes; when reading `getPropertyPath()`, do not assume it is always a simple field name.

## 8. Stacking Constraints: Independent, No Guarantee of "Which Runs First"

Example:

~~~java
@NotBlank(message = "name is required")
@Size(min = 3, max = 12,
      message = "name must have 3..12 characters")
private String name;
~~~

When `name = ""`:

- `@NotBlank` fails because the value is empty.
- `@Size(min=3)` also fails because length is 0.
- `Validator.validate(bean)` can return **two `ConstraintViolation`s** for the same `name` property.

When `name = null`:

- `@NotBlank` fails.
- `@Size` passes per its null-allowing contract.
- Only one violation is emitted from this constraint pair, assuming no other constraints exist on the property.

When `name = "ab"`:

- `@NotBlank` passes.
- `@Size(min=3)` fails.

The result is a `Set<ConstraintViolation<T>>` with no guaranteed order. Do not write logic like "take the first violation as the required error" or "if `@NotBlank` fails, `@Size` won't run" without configuring an explicit ordering mechanism.

### Are Multiple Errors on One Field Helpful or Harmful?

Each error carries distinct metadata, useful for testing and diagnostics. However, UIs often want only **one prioritized message** per field (e.g., "Please enter a name" when empty, rather than two messages back-to-back). You can:

1. Keep the full violation set on the backend and sort/prioritize during display.
2. Use group sequences when business logic requires staged validation.
3. Define a **composed constraint** with `@ReportAsSingleViolation` when a single unified contract should report one combined error.

These are three distinct mechanisms; do not pick a group sequence merely as a substitute for simple UI error prioritization.

## 9. Runnable Java 17 Example: Null, Multiple Constraints, and Nested Errors

This example runs on **Java 17 + Maven**, using **Jakarta Bean Validation 3.0** with **Hibernate Validator 8.0.6.Final**. We implement a composed constraint `@RequiredCode` in the next subsection, then test data with multiple errors, null data, and valid data.

Structure:

~~~text
null-constraint-demo/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── RequiredCode.java
    │   └── NullCompositionDemo.java
    └── test/java/demo/
        └── NullCompositionDemoTest.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>null-constraint-demo</artifactId>
    <version>1.0.0</version>

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
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`hibernate-validator` provides the execution provider; the Jakarta API comes transitively. `expressly` provides Jakarta Expression Language for message interpolation in a standalone Java SE app. With Spring Boot's dependency management and validation starter, dependencies are managed differently and usually do not require pinning versions as shown here.

### 9.1. File RequiredCode.java

~~~java
package demo;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import jakarta.validation.ReportAsSingleViolation;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

@NotBlank
@Size(min = 4, max = 8)
@Pattern(regexp = "[A-Z][A-Z0-9]*")
@Constraint(validatedBy = {})
@ReportAsSingleViolation
@Target({
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.PARAMETER,
    ElementType.ANNOTATION_TYPE,
    ElementType.TYPE_USE
})
@Retention(RetentionPolicy.RUNTIME)
@Documented
public @interface RequiredCode {
    String message() default
        "code must contain 4..8 uppercase letters/digits and start with a letter";

    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

The `@RequiredCode` contract:

- Value must be non-null, non-empty, and non-blank thanks to `@NotBlank`.
- Value must be 4–8 UTF-16 units long thanks to `@Size`.
- Value must start with uppercase `A–Z`, followed only by uppercase letters or digits thanks to `@Pattern`.
- `@ReportAsSingleViolation` requests reporting **one composite violation** instead of separate violations from the composing annotations if any component fails.
- `@Constraint(validatedBy = {})` indicates this annotation **has no separate validator of its own**, and is composed purely from the three constraints.

We intentionally kept the three rules separate even though a tight regex could include length: each constraint keeps a single responsibility while demonstrating how composition works. This is a policy for ASCII codes; do not impose this regex on Vietnamese usernames.

### 9.2. File NullCompositionDemo.java

~~~java
package demo;

import java.util.List;
import java.util.Set;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public class NullCompositionDemo {

    static final class Address {
        @NotBlank(message = "city is required")
        private final String city;

        Address(String city) {
            this.city = city;
        }
    }

    static final class Registration {
        @NotBlank(message = "name is required")
        @Size(min = 3, max = 12,
              message = "name must have 3..12 characters")
        private final String name;

        @NotNull(message = "age is required")
        @Min(value = 18,
             message = "age must be at least 18")
        private final Integer age;

        @NotNull(message = "labels are required")
        @Size(min = 1, max = 3,
              message = "labels count must be 1..3")
        private final List<
            @NotBlank(message = "label must not be blank")
            String> labels;

        @NotNull(message = "address is required")
        @Valid
        private final Address address;

        @RequiredCode
        private final String code;

        Registration(String name, Integer age,
                     List<String> labels, Address address,
                     String code) {
            this.name = name;
            this.age = age;
            this.labels = labels;
            this.address = address;
            this.code = code;
        }
    }

    static Registration validRegistration() {
        return new Registration(
            "Minh", 20, List.of("java"),
            new Address("Ha Noi"), "A123");
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();

            Registration invalid = new Registration(
                "", null,
                List.of("", "java", "spring", "api"),
                new Address(" "), "a9");

            Set<ConstraintViolation<Registration>> errors =
                validator.validate(invalid);

            System.out.println("invalid=" + errors.size());
            errors.stream()
                .map(ConstraintViolation::getMessage)
                .sorted()
                .forEach(System.out::println);

            Registration allNull =
                new Registration(null, null, null, null, null);
            System.out.println(
                "allNull=" + validator.validate(allNull).size());

            System.out.println(
                "valid=" +
                validator.validate(validRegistration()).size());
        }
    }
}
~~~

Run command from the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.NullCompositionDemo
~~~

Stdout produced by the Java code, excluding auxiliary Maven/provider logs:

~~~text
invalid=7
age is required
city is required
code must contain 4..8 uppercase letters/digits and start with a letter
label must not be blank
labels count must be 1..3
name is required
name must have 3..12 characters
allNull=5
valid=0
~~~

**Why `invalid=7`?**

1. `name=""` violates `@NotBlank` and `@Size(min=3)`: **2 independent errors**, same property `name`.
2. `age=null` violates `@NotNull`; `@Min(18)` **accepts null**: **1 error**.
3. `labels` has 4 elements so it violates `@Size(max=3)`; the first element is `""` so it violates `@NotBlank` on the element: **2 errors**.
4. `address` is non-null so `@Valid` cascades; `address.city=" "` violates `@NotBlank`: **1 error**.
5. `code="a9"` fails both length and pattern, yet `@RequiredCode` has `@ReportAsSingleViolation`, so it returns only **1 error** for `code`.

Total: `2 + 1 + 2 + 1 + 1 = 7`. Output sorts `getMessage()` because `Set` does not guarantee order. List element error paths are provider-defined, so the example avoids relying on the String representation of `Path` in stdout.

**Why `allNull=5`?**

- `name`: `@NotBlank` rejects null, `@Size` accepts → 1.
- `age`: `@NotNull` rejects null, `@Min` accepts → 1.
- `labels`: `@NotNull` rejects null, `@Size` accepts; no List exists to check elements → 1.
- `address`: `@NotNull` rejects null, `@Valid` does not cascade → 1.
- `code`: `@RequiredCode` rejects null via `@NotBlank`, reporting one combined error → 1.

Total **5**. `valid=0` confirms all applied conditions are satisfied. This outcome is not an implicit rule that "null is always invalid"; errors appear because we **explicitly declared** presence constraints.

## 10. Testing Null, Same-Field Duplicates, and Composed Constraints

File `src/test/java/demo/NullCompositionDemoTest.java`:

~~~java
package demo;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.ValidatorFactory;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class NullCompositionDemoTest {

    @Test
    void samePropertyCanHaveTwoIndependentViolations() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {
            var validator = factory.getValidator();
            var form = new NullCompositionDemo.Registration(
                "", 20, List.of("java"),
                new NullCompositionDemo.Address("Ha Noi"), "A123");

            var errors = validator.validate(form);

            assertEquals(2, errors.size());
            assertEquals(
                Set.of("name is required",
                       "name must have 3..12 characters"),
                errors.stream()
                    .map(ConstraintViolation::getMessage)
                    .collect(Collectors.toSet()));
        }
    }

    @Test
    void composedCodeConstraintReportsOneViolation() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {
            var validator = factory.getValidator();
            var form = new NullCompositionDemo.Registration(
                "Minh", 20, List.of("java"),
                new NullCompositionDemo.Address("Ha Noi"), "a9");

            var errors = validator.validate(form);

            assertEquals(1, errors.size());
            var error = errors.iterator().next();
            assertEquals("code", error.getPropertyPath().toString());
            assertEquals(
                "code must contain 4..8 uppercase letters/digits "
                    + "and start with a letter",
                error.getMessage());
        }
    }

    @Test
    void allNullFailsOnlyPresenceConditions() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {
            var validator = factory.getValidator();
            var form = new NullCompositionDemo.Registration(
                null, null, null, null, null);

            var errors = validator.validate(form);

            assertEquals(5, errors.size());
            assertEquals(
                Set.of("name", "age", "labels", "address", "code"),
                errors.stream()
                    .map(v -> v.getPropertyPath().toString())
                    .collect(Collectors.toSet()));
        }
    }

    @Test
    void nestedAndContainerViolationsBothAppear() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {
            var validator = factory.getValidator();
            var form = new NullCompositionDemo.Registration(
                "", null,
                List.of("", "java", "spring", "api"),
                new NullCompositionDemo.Address(" "), "a9");

            var errors = validator.validate(form);

            assertEquals(7, errors.size());
            assertTrue(errors.stream()
                .anyMatch(v ->
                    v.getPropertyPath().toString()
                        .equals("address.city")));
            assertTrue(errors.stream()
                .anyMatch(v -> v.getMessage()
                    .equals("label must not be blank")));
        }
    }

    @Test
    void validInputHasNoViolation() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {
            var validator = factory.getValidator();

            assertTrue(validator.validate(
                NullCompositionDemo.validRegistration()).isEmpty());
        }
    }
}
~~~

Run tests:

~~~bash
mvn test
~~~

With the sample project's dependencies, expect **5 tests passed**, 0 failed. The tests intentionally compare sets of messages/paths instead of the first element's position because `Set` has no deterministic order. Tests in this document are verified for syntax and logic; in another environment, still run `mvn test` to confirm classpath/provider behavior.

To test a hypothetical property value before instantiating an object, use `validator.validateValue(Registration.class, "name", null)`; results follow annotations on `name` without a root bean instance. `validateProperty(...)` and `validateValue(...)` do not execute `@Valid` cascades per spec; to evaluate the whole graph, use `validate(bean)`.

## 11. What Is a Composed Constraint and How Does It Differ from Stacking?

There are **two ways** to apply multiple rules to the same value:

**Approach A — declare each constraint directly at the usage site:**

~~~java
@NotBlank
@Size(min = 4, max = 8)
@Pattern(regexp = "[A-Z][A-Z0-9]*")
private String code;
~~~

Each constraint has its own metadata/message and can produce its own violation. Best when the rule set appears in only a few places or when showing each specific cause is desired.

**Approach B — define a composite annotation:**

~~~java
@RequiredCode
private String code;
~~~

`@RequiredCode` in the runnable example declares `@NotBlank`, `@Size`, and `@Pattern` **on the annotation definition**. The default combining operator for composed constraints in Jakarta is **AND**: all components must pass together. Add `@ReportAsSingleViolation` to return one combined error instead of multiple component errors.

**Precision notes:**

- A composed constraint **does not alter the null rules** of its component constraints. `@RequiredCode` rejects null because it **includes `@NotBlank`**. A composite consisting only of `@Size` and `@Pattern` will still accept null.
- `@ReportAsSingleViolation` only controls **how violations are reported** for the composed constraint (and may stop evaluating on the first failing component); it does not turn `null` into an error unless a component rejects null.
- Without `@ReportAsSingleViolation`, component constraints can emit individual violations; never assume only one message is always emitted.
- Composed constraints can have their own validator alongside components, though avoid confusing overlapping rules. For pure composition, `@Constraint(validatedBy = {})` is right.
- `groups` and `payload` of composing constraints follow the composite annotation's group/payload per spec. Do not treat them as unrelated free labels.

A composed constraint should carry a **meaningful business name** like `@RequiredCode`, `@ValidSku`, or `@StrongPassword`, rather than a generic name without a clear contract.

### When to Avoid @ReportAsSingleViolation?

If the UI needs to distinguish "missing code", "too short", and "invalid pattern", reporting one combined error reduces detail. In that case, declare multiple constraints directly or keep component violations in the composite. If the API needs a single stable message for "invalid code", `@ReportAsSingleViolation` can fit well.

Do not use composed constraints merely to hide configuration bugs or avoid reading `Set<ConstraintViolation<?>>`. Choose them when **a domain concept** genuinely combines multiple reusable conditions.

## 12. Group Validation: A Field Can Be Required at One Step and Optional at Another

Many forms have distinct **create**, **update**, and **draft** operations. In a draft, address may be null; when submitting an order, address becomes required. Validation groups address this.

Illustrative example:

~~~java
interface Create {}
interface Update {}

class Command {
    @Null(groups = Create.class)
    @NotNull(groups = Update.class)
    Long id;

    @NotBlank(groups = {Create.class, Update.class})
    String name;
}
~~~

This snippet requires importing `jakarta.validation.constraints.Null`, `NotNull`, and `NotBlank`. When `id=null`, validating the `Create` group allows id while the `Update` group rejects it. When `id=123L`, the reverse happens for the id constraint. You can invoke:

~~~java
validator.validate(command, Create.class);
validator.validate(command, Update.class);
~~~

This snippet uses `validator` and `command`. Understand:

- Without passing a group, `validate(bean)` uses the `Default` group.
- Passing `Create.class` alone **does not automatically** include constraints belonging to `Default`.
- To validate multiple groups together, pass multiple group classes, though evaluation order is not guaranteed without a sequence.
- `@GroupSequence` defines group ordering; if an earlier group fails, later groups in the sequence are not evaluated per spec. This is a mechanism for **validation scope and ordering**, not just UI display.
- In Spring, `@Validated(Group.class)` requests specific groups at supported integration points. `@Valid` alone does not select custom groups.

When create/update requirements diverge heavily, **two separate DTOs** are usually cleaner than one DTO packed with overlapping groups. Do not use groups to paper over an API needing two distinct data contracts.

## 13. Difference Between "Combined Constraints" and "Cross-Field Validation"

Stacking `@NotBlank @Size @Pattern` suffices for conditions **on a single value**. However, some business rules depend on two or more fields:

- `startDate <= endDate`.
- If `deliveryMethod = "SHIP"`, then `shippingAddress` is required.
- If `paymentType = "CARD"`, then `cardToken` is required.
- `minQuantity` must not exceed `maxQuantity`.

These relationships cannot be fully expressed by placing `@NotNull` or `@Size` on one field in isolation from the other. Consider a **class-level constraint** with `ConstraintValidator<CustomAnnotation, BeanType>`, or business-layer validation. Illustrative logic example:

~~~java
boolean isValidBooking(Booking booking) {
    if (booking == null) {
        return true; // Policy if this constraint accepts null.
    }
    if (booking.startDate() == null ||
        booking.endDate() == null) {
        return true; // Leave null to separate @NotNull if required.
    }
    return !booking.startDate().isAfter(booking.endDate());
}
~~~

This is **method-style pseudocode**, assuming a `Booking` class/record and accessors exist; it is not a standalone `ConstraintValidator` implementation. In a real class-level validator, decide how to construct violations and use `ConstraintValidatorContext`. To attach the error to `endDate` instead of an object-level error, add a property node via `buildConstraintViolationWithTemplate(...).addPropertyNode("endDate")...`.

**Why return true when null is present?** This is a common separation-of-concerns strategy: the relational constraint only runs when both values exist, while dedicated requiredness constraints handle null. It is **not a mandatory rule** for every custom validator. If business rules define missing either field as a primary violation of the class-level constraint, you can return false; state the contract clearly and test it.

## 14. Spring MVC and Spring Boot: When Do Multiple Annotations Run?

Annotations on a DTO only take effect when a Bean Validation provider is present and validation is **triggered** at the boundary.

In a dependency-managed Spring Boot 3 application, typically use:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

This XML snippet is the dependency to add to a Boot project; versions are managed by Boot's parent/BOM rather than the standalone version in Section 9.

Example DTO:

~~~java
public class SignupRequest {
    @NotBlank
    @Size(min = 3, max = 12)
    private String name;

    @NotNull
    @Min(18)
    private Integer age;

    @NotEmpty
    @Size(max = 3)
    private List<@NotBlank String> labels;

    // Getters/setters or appropriate binding mechanism.
}
~~~

This is an **illustrative DTO**, requiring matching imports. Controller:

~~~java
@PostMapping("/signup")
public ResponseEntity<Void> signup(
        @Valid @RequestBody SignupRequest request) {
    // Handle request after it passes validation.
    return ResponseEntity.noContent().build();
}
~~~

This is an **illustrative controller**, requiring Spring Web MVC and DTO imports in the same app. In standard Spring MVC, `@Valid @RequestBody` validates the object; argument validation failures can raise `MethodArgumentNotValidException` if no `Errors`/`BindingResult` follows the parameter and no method-level validation replaces it.

When constraints sit directly on method parameters (like `@Min` on `@RequestParam Integer page`), Spring MVC 6.1+ includes built-in method validation, which can throw `HandlerMethodValidationException`. On service methods via `@Validated` and AOP, you may by default receive `jakarta.validation.ConstraintViolationException` if method validation actually executes through the proxy. **Do not catch a single exception class assuming it covers all Bean Validation errors in Spring.**

### Special Nuances of Null in HTTP Binding

- `@RequestBody(required = true)` has Spring MVC body-presence enforcement; when the body is missing, failure can occur **before Bean Validation**.
- `@RequestParam(required = true)` likewise has its own presence rules.
- A JSON body with `"name": null` differs from an absent request body. After binding, `@NotBlank` rejects a null `name` field.
- If JSON omits `age` and the DTO leaves `Integer age = null`, `@NotNull` handles that state. By contrast, primitive `int` cannot represent null; deserialization/binding results must be checked. Prefer wrappers at boundaries when missing-value detection is needed.
- Type conversion failures, such as letters sent to a numeric field, can occur before `@Min` or `@NotNull`. Spring has its own error handling; do not expect every format error to become a `ConstraintViolation`.

### Multiple Errors on One Field in API Responses

If `name=""`, one request can violate both `@NotBlank` and `@Size`. Response design:

~~~json
{
  "errors": [
    {"field": "name", "code": "REQUIRED", "message": "Please enter a name"},
    {"field": "name", "code": "SIZE", "message": "Name must be 3-12 characters long"}
  ]
}
~~~

This is an example **data format**, not Spring's automatic HTTP output. If you want only one error per field, the API needs display-prioritization rules; the backend can still retain full `BindingResult`/`ConstraintViolation` details for testing and safe logging. `getMessage()` can be localized; error codes like `REQUIRED` should be explicitly defined by the API rather than coupled to provider message text.

## 15. When Does Combining Constraints Lose Information?

Using multiple constraints carries three risks to weigh:

1. **Duplicate messages:** `@NotBlank` and `@Size(min=3)` both fail on an empty string. Display one prioritized message; there is no need to drop constraints just because the UI wants one error.
2. **Contradictory conditions:** `@Null` and `@NotNull` in one group have no valid shared value; `@Size(min=10,max=5)` is invalid metadata; a `@Pattern` can conflict with length limits. Check logical consistency at design time.
3. **Overlooking null via wrong annotation choice:** `@Size(min=1)` rejects empty Lists yet accepts null Lists, `@Min(18)` only checks a present Integer, and `@Valid` does not require a child bean. Document "optional vs. required" explicitly per field.

Additionally, many constraints can impact performance (e.g., validating huge payloads, calling remote services inside custom validators). Validators should mainly inspect local data with no side effects; rules requiring I/O or race-sensitive business state typically must be re-verified in the business layer. Do not rely on execution order across annotations to avoid logic bugs.

## 16. How Do Exceptions, Fail-Fast, and Group Sequences Affect Results?

`Validator.validate(bean)` **returns a `Set<ConstraintViolation<T>>`**. It does not automatically throw `ConstraintViolationException` just because a field is invalid. That exception may be thrown by application code or generated by method validation/integration layers.

~~~java
Set<ConstraintViolation<MyForm>> errors =
    validator.validate(form);
if (!errors.isEmpty()) {
    throw new ConstraintViolationException(
        "Invalid form", errors);
}
~~~

This is an illustrative snippet requiring `MyForm`, `validator`, and `jakarta.validation.*` imports, not a standalone program. Do not treat all `ValidationException`s like invalid user input: bad provider configuration or invalid constraint declarations are programming bugs that should be classified separately.

Several situations cause results not to contain every possible violation:

- **Only requested groups are validated.** With `validate(bean, Create.class)`, the `Default` group is not automatically included unless appropriate relationships are defined.
- **Group sequences stop at the failing group.** If one group has violations, subsequent groups in the sequence are not evaluated per spec.
- **Hibernate Validator has a fail-fast option**, which is not a portable contract across all providers. When enabled, the provider may stop early after detecting a violation; never assume a deterministic order for picking the "first violation".
- **`@ReportAsSingleViolation`** replaces multiple component violation messages with one combined message and may short-circuit on the first failing component.
- **`@Valid` does not traverse null objects** or null collections, so deep errors in absent values cannot be detected.
- **`validateProperty(...)`/`validateValue(...)` do not cascade**, so their violation sets can differ from `validate(bean)`.

Therefore, never interpret `errors.isEmpty()` as "every business rule, every group, and every layer is valid" in all contexts. It means **no violations occurred within the validation scope that actually ran**.

## 17. Common Mistakes and Resolutions

| Mistake | Consequence | Right Approach |
| --- | --- | --- |
| Putting only `@Size(min=1)` and assuming the field is required | Null still passes. | Use `@NotNull`, `@NotEmpty`, or `@NotBlank` per type/meaning. |
| Putting only `@Email` and assuming email is required | Null is treated as valid. | Pair a presence constraint when email is required. |
| Using `@NotNull` to forbid empty strings | `""` is non-null so it passes. | Use `@NotBlank` for meaningful text. |
| Using `@NotEmpty` to forbid whitespace-only strings | `"   "` is non-empty so it can pass. | Use `@NotBlank`. |
| Using `@NotBlank` on `List` or `Map` | No standard validator for those types. | Use `@NotEmpty` or `@Size` for containers. |
| Attaching `@Valid` and assuming the child object is required | Cascading skips null. | Add `@NotNull` if truly required. |
| Using `@Size(max=3) List<...>` to forbid null elements | Only counts elements. | Use `List<@NotNull Element>` or appropriate element constraints. |
| Writing annotations in a specific order assuming execution order | Providers do not guarantee order within a group. | Use group sequences purposefully or prioritize errors in UI. |
| Taking only `violations.iterator().next()` | Set has no deterministic order. | Sort or process the whole set. |
| Using `@ReportAsSingleViolation` when specific causes must be displayed | Loses detailed component errors. | Consider separate reporting or keeping metadata in another layer. |
| Assuming a composite `@Pattern @Size` rejects null automatically | Both accept null. | Add `@NotNull`/`@NotBlank` when required. |
| Combining `@Null` and `@NotNull` in the same group | No value satisfies both. | Separate create/update groups or use separate DTOs. |
| Believing `@Min(18)` forbids null Integer | `@Min` allows null. | Add `@NotNull`. |
| Believing `@RequestBody @Valid` and binding errors throw one exception | Spring has multiple error paths and pre-validation conversion. | Test `MethodArgumentNotValidException`, method validation, and type conversion errors. |
| Using primitive `int` to distinguish omitted field from 0 | Primitives cannot represent null. | Use wrappers or an explicit presence model. |
| Logging or returning `getInvalidValue()` directly to clients | Can expose sensitive data. | Use only controlled field/code/message outputs. |
| Treating display messages as fixed error codes | Messages depend on locale/interpolator. | Define separate stable error codes. |
| Bounding strings with `@Size` thinking HTTP/DB byte limits are covered | Java String length differs from byte length. | Separate validation logic from request/storage limits. |

## 18. Design Checklist and Self-Check

Before shipping a request DTO or domain object, answer:

1. Can this field **be absent**? If not, use an appropriate presence constraint.
2. Do `null`, `""`, `"   "`, empty List, and empty Map have distinct meanings?
3. If it is a String, what level of **content**, **length**, **pattern**, and **normalization** checks is required?
4. If it is a number, use a wrapper to detect missing data or a primitive with intentional defaults?
5. If it is a Collection/Map, must the container be present and must individual elements/keys/values be checked separately?
6. If it is a child bean, does `@Valid` need to be paired with `@NotNull`?
7. Are constraints assigned to the right **group**, and is a group sequence truly needed?
8. Should multiple detailed violations or one combined violation be returned? If one, handle in UI or define a composed annotation?
9. Does the API separate binding/type-conversion errors from Bean Validation errors?
10. Do tests cover null, missing property, empty, blank, near min/max, null elements, null child objects, and multiple errors on one field?
11. Did you test `@Validated(Group.class)` in Spring to verify the right group runs?
12. When returning messages to clients, are stable error codes separated and sensitive values stripped?

**Review Questions**

1. Does `@Size(min=3) String name` reject `name=null`?
2. Does `@Email String email` make email required?
3. How do `@NotEmpty` and `@NotBlank` differ on `"   "`?
4. Does `@Valid Address address` validate `Address.city` if `address=null`?
5. What does `@NotEmpty List<@NotBlank String> labels` guarantee at both levels?
6. Why can `@NotBlank` and `@Size(min=3)` return two violations for `""`?
7. Does `@ReportAsSingleViolation` automatically turn a composite of only `@Pattern` and `@Size` into a required field?
8. How can a field be `@Null` on create and `@NotNull` on update?
9. Why cannot the iteration order of `Set<ConstraintViolation<T>>` serve as UI priority order?

**Answers:** (1) No; (2) No; (3) both reject null/empty, while `@NotBlank` also rejects whitespace-only; (4) No, cascading skips null; (5) List is present and non-empty, each String is non-blank; (6) two independent constraints both fail; (7) No, a null-rejecting component like `@NotBlank` is needed; (8) separate Create/Update groups or separate DTOs; (9) because Set does not guarantee order.

## 19. Official References

- Jakarta Bean Validation 3.0 — Specification (built-in constraint definitions, null, composition, and graph validation): https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Jakarta Bean Validation 3.0 API — `NotNull`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/NotNull.html
- Jakarta Bean Validation 3.0 API — `NotEmpty`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/NotEmpty.html
- Jakarta Bean Validation 3.0 API — `NotBlank`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/NotBlank.html
- Jakarta Bean Validation 3.0 API — `Size`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/Size.html
- Jakarta Bean Validation 3.0 API — `ReportAsSingleViolation`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/ReportAsSingleViolation.html
- Hibernate Validator 8.0 — Reference Guide (composition, container elements, fail-fast, groups): https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Spring Framework 6.2 — Spring MVC Validation: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — Bean Validation Integration: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
