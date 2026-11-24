# @Size for Strings, Arrays, Collections, and Maps in Bean Validation

## 1. Goal and Core Rules

`@Size` is a standard constraint in **Jakarta Bean Validation** used to require **the size of a value to fall between `min` and `max` (inclusive of both endpoints)**. In Spring Framework applications, this constraint is commonly placed on request DTOs, configuration beans, domain objects, or method parameters enforced by Bean Validation.

Import used with Spring Framework 6 and Spring Boot 3:

~~~java
import jakarta.validation.constraints.Size;
~~~

Basic examples:

~~~java
@Size(min = 3, max = 20)
private String username;

@Size(min = 1, max = 5)
private List<String> roles;

@Size(max = 10)
private byte[] signature;

@Size(min = 1, max = 4)
private Map<String, String> metadata;
~~~

Key point to remember: **`@Size` measures the size of the annotated value itself; it does not automatically validate the content or individual elements inside that value.** To validate individual elements, write constraints on type arguments or use cascading `@Valid` on child beans.

| Declared Type | What Does `@Size` Count? | Example `@Size(min = 2, max = 4)` |
| --- | --- | --- |
| `String`, `StringBuilder`, `CharSequence` | `length()` of the character sequence, per Java semantics | `"AB"` passes, `"A"` fails. |
| `String[]`, `int[]`, `byte[]`, other arrays | `array.length`, number of elements in the array | `new int[]{1,2,3}` passes. |
| `List`, `Set`, or `Collection` implementations | `collection.size()` | A List with 3 elements passes, a Set with 5 elements fails. |
| `Map` | `map.size()`, number of **entries** (key–value pairs) | A Map with 2 entries passes. |
| `null` on any valid type above | Considered **valid by `@Size`** | Add `@NotNull` if a value is required. |

These rules are defined by the Jakarta Bean Validation specification. Providers such as Hibernate Validator enforce them when running `Validator.validate(bean)` or when Spring triggers validation appropriately.

### Boundary Values and Defaults

~~~java
@Size(min = 2, max = 4) // 2, 3, and 4 all pass
@Size(min = 2)          // Default upper limit: Integer.MAX_VALUE
@Size(max = 4)          // Default lower limit: 0
@Size                   // min=0, max=Integer.MAX_VALUE
~~~

The two parameters `min` and `max` are `int`:

- `min` defaults to **0**.
- `max` defaults to **`Integer.MAX_VALUE`**.
- Size is accepted when `min <= size <= max`.
- Valid configuration values must satisfy `min >= 0` and `max >= min`. Misdeclaring boundary constraints is a configuration issue, not an ordinary "invalid user input" error.
- `@Size(max = 0)` only accepts a value **of size 0** or `null`; it is not synonymous with `@Null`.
- `@Size(min = 1)` rejects a non-null empty value, yet **still allows null**.

## 2. How Bean Validation Evaluates @Size

An annotation is metadata attached to a field, getter, parameter, return value, or type-use. Writing the annotation alone does not mean checks run automatically.

~~~text
DTO / domain object with @Size
          |
          | Validator.validate(bean)
          v
 Bean Validation provider
          |
          | Determine type and matching validator
          | Value is null? -> valid for @Size
          | Non-null? -> compute length/size
          v
 Compare min <= size <= max
        /                  \
      true                 false
       |                     |
No @Size violation       Create a
emitted                  ConstraintViolation
       \                     /
        \                   /
         Set<ConstraintViolation<T>>
~~~

When validation succeeds for all constraints in the scope being evaluated, `Validator.validate(...)` returns an empty set. When it fails, the set contains details such as property path, message, invalid value, and descriptor.

If you only need a direct length check in Java, `String.length()` or `Collection.size()` is the normal approach; the benefit of `@Size` is **declaring the constraint once**, so the framework/provider enforces it consistently across processing paths and produces structured errors.

## 3. @Size on String and CharSequence

### 3.1. Counts Length, Not Meaningful Characters

~~~java
@Size(min = 3, max = 8, message = "Name must be between {min} and {max} units")
private String displayName;
~~~

When validated, the provider evaluates string length. For Java `String`, `length()` returns **the number of UTF-16 code units**, not necessarily the number of Unicode code points or user-perceived characters (grapheme clusters). This matters when data contains emojis or combining marks.

| String Value | `String.length()` | With `@Size(min=3,max=8)` |
| --- | ---: | --- |
| `"An"` | 2 | Fail |
| `"Anh"` | 3 | Pass |
| `"Nguyen"` | 6 | Pass |
| `"123456789"` | 9 | Fail |
| `""` | 0 | Fail |
| `"   "` | 3 | **Pass**: three spaces still have length 3 |
| `null` | `length()` not called | **Pass under `@Size`** |

For an emoji outside the Basic Multilingual Plane, such as `"🙂"`:

~~~java
System.out.println("🙂".length());              // 2
System.out.println("🙂".codePointCount(0, 2));  // 1
~~~

These are Java 17 statements that can be placed inside a method. The outputs are `2` and `1` respectively: a single emoji can occupy **two UTF-16 code units**. `@Size(max=1)` on a String containing only this emoji will fail when using standard Java length counting. Unicode strings with combining characters can also have a count different from the number of characters the user sees.

**When business rules require user-perceived character count**, such as at most 30 grapheme clusters in a name, `@Size` may not match the intended semantics. Define a counting standard and write a custom constraint or appropriate processing, considering Unicode normalization and grapheme segmentation rules. Do not treat `String.length()` as an absolute measure of "character count".

### 3.2. Whitespace Is Counted

`@Size` does not trim a String before counting. The string `"   "` has length 3; therefore `@Size(min=3)` can accept it. For a required name with content:

~~~java
@NotBlank
@Size(min = 3, max = 40)
private String fullName;
~~~

You need to import `jakarta.validation.constraints.NotBlank`. Then:

- `@NotBlank` rejects null, empty, or whitespace-only strings.
- `@Size` checks size according to the length rule.
- Neither **automatically transforms data**. If you want to strip leading/trailing whitespace, perform intentional normalization before validation or at a designed boundary.

A string `"  Nam  "` has length 7 under `@Size`, even though after `strip()` it becomes `"Nam"` (3). Agree on the contract: validate **raw data** or **normalized data**. Do not arbitrarily strip identifiers, passwords, or digital signatures.

### 3.3. @Size Does Not Check Format

`@Size(min=10, max=10)` cannot prove a string is a valid phone number; it only proves it has 10 UTF-16 code units. When format checks are needed:

~~~java
@Size(min = 6, max = 12)
@Pattern(regexp = "[A-Z0-9]+")
private String productCode;
~~~

For `@Pattern`, import `jakarta.validation.constraints.Pattern`. If null values must be rejected, add `@NotNull`/`@NotBlank` according to the contract. A code matching the length but violating the pattern will fail `@Pattern` without failing `@Size`.

## 4. @Size on Arrays: Element Count, Not Memory Size

Both `T[]` arrays and primitive arrays are supported:

~~~java
@Size(min = 2, max = 5)
private String[] answerChoices;

@Size(min = 16, max = 32)
private byte[] keyMaterial;

@Size(max = 100)
private int[] scores;
~~~

Explanation:

- For `String[]`, it counts **number of elements**, not the sum of individual String lengths.
- For `byte[]`, the element count equals the number of bytes in the array itself, though `@Size` does not check encoding semantics, signatures, or cryptographic strength.
- For `int[]`, it counts `int` elements; it does not constrain individual element values or measure memory bytes consumed by the array.
- The array `new String[3]` has size 3 **even if all three elements are null**. `@Size(min=3,max=3)` still passes.

Comparison examples:

~~~java
String[] a = {"long text", ""};    // a.length == 2
byte[] b = new byte[4];            // b.length == 4
int[] c = new int[0];              // c.length == 0
~~~

Only when you want to check element contents do you need additional constraints. For example with String:

~~~java
@Size(min = 2, max = 4)
private String @NotNull [] choices;
~~~

Type-use syntax on arrays is error-prone; a clearer approach in DTOs when validating individual elements is using `List<@NotBlank String>` with `@Size` on the List, as in the next section. If using arrays, verify whether the annotation targets the **array** or the **element type** and confirm the behavior with `Validator.validate(...)`. Do not assume `@Size` on an array validates every element.

## 5. @Size on Collections: List, Set, and Implementations

For Java `Collection`, the constraint measures `collection.size()`.

~~~java
@Size(min = 1, max = 3)
private List<String> roleNames;

@Size(min = 2, max = 10)
private Set<Long> selectedIds;
~~~

Distinctions to note:

| Value | Size Computed by `@Size` | With `@Size(min=1,max=3)` |
| --- | ---: | --- |
| `List.of()` | 0 | Fail |
| `List.of("admin")` | 1 | Pass |
| `List.of("A","B","C")` | 3 | Pass |
| `List.of("A","B","C","D")` | 4 | Fail |
| `Set.of("A","B")` | 2 | Pass |
| `null` | `size()` not called | Pass |
| List of three elements, one `null` | 3 | Pass under **`@Size` constraint** |

`Set` only stores distinct elements according to the `equals/hashCode` contract. Two duplicate values in a `Set` do not become two elements; `@Size` measures the size **after the Set has been constructed**. With `List`, duplicate values still occupy distinct positions and are counted separately.

### 5.1. Collection Size Differs from Element Constraints

~~~java
@Size(min = 1, max = 3)
private List<@NotBlank String> tags;
~~~

There are **two levels of checks** here:

1. `@Size(min=1,max=3)` attached to the **List**: limits the number of tags.
2. `@NotBlank` attached to **each String element**: disallows null, empty, or whitespace-only Strings.

For example, `List.of("", "java", "spring", "api")` has four elements; it violates `@Size(max=3)`, while the first element violates `@NotBlank`. A single request can receive **two violations** at different locations. Do not expect `@Size` to detect blank tags on its own.

Element types with their own constraints can use:

~~~java
private List<@Size(min = 2, max = 20) String> labels;
~~~

This applies `@Size` **to each String**, without limiting the number of elements in the List. To enforce both:

~~~java
@Size(min = 1, max = 10)
private List<@Size(min = 2, max = 20) String> labels;
~~~

Container element constraints in Bean Validation 2.0+/Jakarta Validation use type-use annotations. If the element is a **bean with its own annotations**, such as `OrderLine`, use `List<@Valid OrderLine>` to cascade into the child bean. Even so, `@Valid` does not replace `@Size`, and checking element count alone does not validate internal data.

### 5.2. Empty Collection, Null, and @NotEmpty

When requiring at least one element, two options have different nuances:

~~~java
@Size(min = 1)
private List<String> optionalList; // null is still accepted by @Size

@NotEmpty
private List<String> mandatoryList; // both null and empty list are rejected
~~~

If an upper limit and non-empty requirement are both needed:

~~~java
@NotEmpty
@Size(max = 5)
private List<@NotBlank String> categories;
~~~

`@NotEmpty` ensures the list has at least one element; `@Size(max=5)` limits it to at most five elements; `@NotBlank` validates each String. There is no need to repeat `@Size(min=1)` when `@NotEmpty` already states the minimum policy clearly, unless the project has a specific convention.

**Note on `Iterable`:** the standard contract of `@Size` lists `Collection`, and does not guarantee direct applicability to every class that only implements `Iterable` without implementing `Collection`. For a custom wrapper or stream, check whether the provider supports an extra validator or write a custom constraint. Do not put `@Size` on an unsupported type and assume it works by iterating.

## 6. @Size on Map: Entry Count, Not Key/Value Length

~~~java
@Size(min = 1, max = 4)
private Map<String, String> preferences;
~~~

`Map.size()` counts the number of key–value pairs:

| Map | `size()` | With `@Size(min=1,max=4)` |
| --- | ---: | --- |
| `Map.of()` | 0 | Fail |
| `Map.of("theme","dark")` | 1 | Pass |
| `Map.of("a","x", "b","y", "c","z", "d","w")` | 4 | Pass |
| Map with five entries | 5 | Fail |
| `null` | `size()` not called | Pass |

`@Size` **does not check** whether keys are empty, values are null, how long values are, or what characters keys contain. To constrain both the Map and its contents:

~~~java
@NotEmpty
@Size(max = 5)
private Map<@NotBlank String, @NotBlank String> labels;
~~~

Corresponding constraints:

- `@NotEmpty` on the Map: the Map must be non-null and have entries.
- `@Size(max=5)` on the Map: at most five entries.
- `@NotBlank` on the key and on the value: each String in those positions has non-whitespace content.

With `String` keys and bean values:

~~~java
@Size(max = 10)
private Map<@NotBlank String, @Valid Contact> contacts;
~~~

This illustrative declaration requires a `Contact` class with constraints, `jakarta.validation.Valid`, and imports. Bean Validation enforces key constraints and cascades into value beans when `Validator.validate(...)` runs, according to the active group configuration.

Do not forget: a Map can reject duplicate keys or overwrite an older key. Once the Map is constructed, `@Size` measures the **actual number of entries present**, not the number of pairs the user sent before parsing. If the API needs to limit the number of fields in a JSON payload *before parsing*, apply appropriate request parser/transport limits; `@Size` on a DTO only runs after the Java object exists.

## 7. @Size Compared with @NotNull, @NotEmpty, @NotBlank, and Other Constraints

This is the biggest source of confusion when using built-in constraints.

| Constraint | Is `null` valid? | `""` (empty String) | `"   "` | Empty List/Map |
| --- | --- | --- | --- | --- |
| `@Size(min=1)` | **Yes** | Invalid because size=0 | Valid because size=3 | Invalid because size=0 |
| `@NotNull` | **No** | Valid | Valid | Valid |
| `@NotEmpty` | **No** | Invalid | Valid | Invalid |
| `@NotBlank` | **No** | Invalid | Invalid | Not standardly applicable to List/Map |

Choose based on requirement:

- **Limit count or length**: `@Size(min=..., max=...)`.
- **Require an object** while accepting empty: `@NotNull`.
- **Require at least one character or element**: `@NotEmpty`, for CharSequence/Collection/Map/array.
- **Require a String with non-whitespace content**: `@NotBlank`, for CharSequence.
- **Check String pattern**: `@Pattern`.
- **Check numeric value**: `@Min`, `@Max`, `@DecimalMin`, `@DecimalMax`, `@Digits` depending on the case; `@Size` is not a standard constraint for `int` or `BigDecimal`.

Registration form example:

~~~java
@NotBlank
@Size(min = 3, max = 30)
private String username;

@NotNull
@Size(min = 2, max = 5)
private List<@NotBlank String> permissions;
~~~

The two fields have distinct policies: `username` must have real characters and sufficient length; `permissions` must have a non-null list with 2–5 elements, each permission being a non-blank String. If the design allows a null list while requiring 2–5 elements when present, use only `@Size(min=2,max=5)` on the list.

### Condensed Truth Table

Consider `@Size(min=2,max=4)`:

| Value | @Size | @NotNull | @NotEmpty (if applicable) |
| --- | --- | --- | --- |
| `null` | Pass | Fail | Fail |
| `""` or empty list | Fail | Pass | Fail |
| `"A"` or 1-element list | Fail | Pass | Pass |
| `"AB"` or 2-element list | Pass | Pass | Pass |
| `"ABCD"` or 4-element list | Pass | Pass | Pass |
| `"ABCDE"` or 5-element list | Fail | Pass | Pass |

**None of the annotations in the table above automatically truncate strings, remove elements, or turn null into an empty string.** Validation checks and reports violations; transforming data belongs to a different responsibility.

## 8. Standalone Java 17 Program: String, List, byte[], and Map

The example uses **Java 17**, **Jakarta Bean Validation 3.0**, and **Hibernate Validator 8.0.6.Final**. Hibernate Validator is the implementation executing the API. Running outside a Spring application requires both a provider and a Jakarta Expression Language implementation for message interpolation.

Maven project structure:

~~~text
size-constraint-demo/
├── pom.xml
└── src/
    ├── main/java/demo/SizeDemo.java
    └── test/java/demo/SizeDemoTest.java
~~~

Contents of `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>size-constraint-demo</artifactId>
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

File `src/main/java/demo/SizeDemo.java`:

~~~java
package demo;

import java.util.List;
import java.util.Map;
import java.util.Set;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class SizeDemo {

    static final class Form {
        @Size(min = 3, max = 5,
              message = "nickname length must be 3..5")
        private final String nickname;

        @Size(min = 1, max = 3,
              message = "tags count must be 1..3")
        private final List<
            @NotBlank(message = "tag cannot be blank") String> tags;

        @Size(min = 2, max = 4,
              message = "payload length must be 2..4")
        private final byte[] payload;

        @Size(min = 1, max = 2,
              message = "attributes must contain 1..2 entries")
        private final Map<String, String> attributes;

        Form(String nickname, List<String> tags,
             byte[] payload, Map<String, String> attributes) {
            this.nickname = nickname;
            this.tags = tags;
            this.payload = payload;
            this.attributes = attributes;
        }
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();

            Form invalid = new Form(
                "ab", List.of("", "ok", "news", "tools"),
                new byte[]{1}, Map.of());

            Set<ConstraintViolation<Form>> errors =
                validator.validate(invalid);

            System.out.println("invalid=" + errors.size());

            // Set does not guarantee order.
            // Print only selected messages so output does not depend on
            // how the provider represents container element paths.
            errors.stream()
                .map(ConstraintViolation::getMessage)
                .sorted()
                .forEach(System.out::println);

            Form valid = new Form(
                "Anna", List.of("java", "api"),
                new byte[]{1, 2}, Map.of("theme", "dark"));

            System.out.println(
                "valid=" + validator.validate(valid).size());

            // @Size allows null on all four fields by default.
            Form allNull = new Form(null, null, null, null);
            System.out.println(
                "allNull=" + validator.validate(allNull).size());

            System.out.println("emojiLength=" + "🙂".length());
        }
    }
}
~~~

Run with Maven and JDK 17+ from the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.SizeDemo
~~~

**Program stdout** (excluding extra logs from the provider/Maven):

~~~text
invalid=5
attributes must contain 1..2 entries
nickname length must be 3..5
payload length must be 2..4
tag cannot be blank
tags count must be 1..3
valid=0
allNull=0
emojiLength=2
~~~

### Explaining the Five Violations

1. `nickname="ab"` has length 2, less than `min=3` → violates `@Size` on String.
2. `tags` contains four elements, greater than `max=3` → violates `@Size` on List.
3. The first element of `tags` is `""` → violates `@NotBlank` on the String element. This is an **independent** violation from the tag count.
4. `payload` has only one byte, less than `min=2` → violates `@Size` on the primitive array.
5. `attributes=Map.of()` has zero entries, less than `min=1` → violates `@Size` on Map.

The `valid` object lies within the bounds of every constraint and all tags are non-blank, so there are no errors. `allNull` also has zero violations because the example **intentionally uses only `@Size` at the field level**, and `@NotBlank` on tag elements does not run when the entire List is null. If null is invalid by business rules, add `@NotNull` or `@NotEmpty` on the corresponding field.

This program does not use Spring MVC; it tests the Bean Validation contract directly. When Spring integrates a compatible provider and triggers validation, the semantics of `@Size` remain the same.

## 9. Testing with JUnit: Boundaries, Null, and Multiple Constraints Together

Add `src/test/java/demo/SizeDemoTest.java` to the project in Section 8:

~~~java
package demo;

import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.ValidatorFactory;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class SizeDemoTest {

    @Test
    void allFourKindsAreChecked() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {
            var validator = factory.getValidator();
            var form = new SizeDemo.Form(
                "ab",
                List.of("", "ok", "news", "tools"),
                new byte[]{1},
                Map.of());

            var violations = validator.validate(form);

            assertEquals(5, violations.size());

            Set<String> messages = violations.stream()
                .map(ConstraintViolation::getMessage)
                .collect(Collectors.toSet());

            assertEquals(Set.of(
                "nickname length must be 3..5",
                "tags count must be 1..3",
                "tag cannot be blank",
                "payload length must be 2..4",
                "attributes must contain 1..2 entries"
            ), messages);
        }
    }

    @Test
    void exactBoundarySizesAreInclusive() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {
            var validator = factory.getValidator();

            var minimum = new SizeDemo.Form(
                "Ann", List.of("ok"),
                new byte[]{1, 2}, Map.of("x", "1"));

            var maximum = new SizeDemo.Form(
                "Annie", List.of("a", "b", "c"),
                new byte[]{1, 2, 3, 4},
                Map.of("x", "1", "y", "2"));

            assertTrue(validator.validate(minimum).isEmpty());
            assertTrue(validator.validate(maximum).isEmpty());
        }
    }

    @Test
    void nullDoesNotViolateSizeAlone() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {
            var validator = factory.getValidator();
            var form = new SizeDemo.Form(null, null, null, null);

            assertTrue(validator.validate(form).isEmpty());
        }
    }

    @Test
    void elementConstraintIsSeparateFromListSize() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {
            var validator = factory.getValidator();

            var form = new SizeDemo.Form(
                "Anna", List.of("", "ok"),
                new byte[]{1, 2}, Map.of("a", "b"));

            var violations = validator.validate(form);
            assertEquals(1, violations.size());
            assertEquals(
                "tag cannot be blank",
                violations.iterator().next().getMessage());
        }
    }
}
~~~

Run:

~~~bash
mvn test
~~~

With Maven, dependencies, and JDK as above, the expected result is **4 tests passed, 0 failed**. The tests check not only "errors exist", but also all value kinds, both endpoints, `null`, and the distinction between List size and element constraints.

If tests run in a Boot project that already includes a provider, use Boot's dependency management and `spring-boot-starter-validation` instead of adding a redundant standalone provider version.

## 10. ConstraintViolation, Error Messages, and Error Fields

When `@Size` fails, the provider creates a `ConstraintViolation<T>`. Useful information:

~~~java
for (ConstraintViolation<SizeDemo.Form> v : errors) {
    String path = v.getPropertyPath().toString();
    String message = v.getMessage();
    Object min = v.getConstraintDescriptor()
                  .getAttributes().get("min");
    Object max = v.getConstraintDescriptor()
                  .getAttributes().get("max");

    System.out.println(path + ": " + message
        + " (min=" + min + ", max=" + max + ")");
}
~~~

This is an **illustrative snippet** using the `errors` variable obtained from `validator.validate(invalid)` in the previous example. `getPropertyPath()` identifies which field failed; `getMessage()` is the interpolated message; the descriptor holds constraint parameters such as `min/max`.

The default message can use a template:

~~~text
{jakarta.validation.constraints.Size.message}
~~~

Depending on the provider's `MessageInterpolator`/locale, it becomes a display message, typically including both length bounds. You can write a custom message with placeholders:

~~~java
@Size(min = 2, max = 5,
      message = "Number of elements must be between {min} and {max}")
private List<String> choices;
~~~

When invalid, the message interpolates to "Number of elements must be between 2 and 5". If building a public API, include a stable error code (e.g., `SIZE_OUT_OF_RANGE`), because message strings can change across locales. Keep in mind:

- `Set<ConstraintViolation<?>>` does not guarantee order: sort by property path/code when stable output is needed.
- A single field can have multiple violations (`@Size` + `@NotBlank`, or element constraints).
- `getInvalidValue()` may contain sensitive data; avoid returning it directly in responses.
- `@Size` on the List/Map itself produces a path to the property, while element errors can produce paths with an index/key and container element node.
- With field-level `@Size`, Strings/maps/arrays can also produce `@NotNull` errors when multiple annotations are combined.

When calling `validator.validate(bean)` directly, the result is a **Set**; it does not automatically throw `ConstraintViolationException` just because data is invalid. The application decides whether to block, return errors, or explicitly throw an exception per the caller contract.

## 11. Using @Size in Spring MVC and Spring Boot

Spring Framework integrates Jakarta Bean Validation via `LocalValidatorFactoryBean` and binding/validation mechanisms. In Spring Boot 3, the common dependency is:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

This is a **dependency snippet** added to a Spring Boot project managed by parent/BOM versioning. In a plain Spring Framework project, configure a Bean Validation provider and related integrations manually.

A request DTO:

~~~java
package demo.web;

import java.util.List;
import java.util.Map;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Size;

public class CreateGroupRequest {

    @NotBlank
    @Size(min = 3, max = 40)
    private String groupName;

    @NotEmpty
    @Size(max = 5)
    private List<@NotBlank String> members;

    @Size(max = 8)
    private Map<@NotBlank String, String> settings;

    // Requires getters/setters or appropriate binding mechanism.
}
~~~

This is an **illustrative web DTO**, not standalone because it lacks getters/setters and a controller. `@Size(max=5)` limits to 5 members, `@NotBlank` ensures each member is non-blank; `@Size(max=8)` limits the entry count of `settings`, without limiting character length in individual values.

Controller:

~~~java
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class GroupController {

    @PostMapping("/groups")
    ResponseEntity<Void> create(
            @Valid @RequestBody CreateGroupRequest request) {
        // Run business logic after request passes validation.
        return ResponseEntity.noContent().build();
    }
}
~~~

This snippet is **part of a Spring MVC application**. `@Valid` requests validating the bean after deserializing `@RequestBody`, provided an active Bean Validation provider is present. Typical request object errors surface as `MethodArgumentNotValidException` (when no `BindingResult` follows the argument and no method-level validation alters the flow). Applications can use `@RestControllerAdvice` to return a list of field errors.

For `@ModelAttribute` forms, `@Valid` can also trigger validation; errors can be read from `BindingResult`. Do not cast Spring's `FieldError` to `ConstraintViolation`. They are two distinct error representations.

### 11.1. @Size Placed Directly on Request Parameters

~~~java
@GetMapping("/search")
public String search(
        @RequestParam
        @Size(min = 2, max = 30) String q) {
    return "Search: " + q;
}
~~~

This is an illustrative controller snippet; import `GetMapping`, `RequestParam`, and `Size` in the controller class. With Spring MVC 6.1+'s built-in method validation integration, constraints placed directly on parameters can produce `HandlerMethodValidationException` when violated. The exact flow depends on method validation configuration, proxies, and Spring version.

Distinguish `@RequestParam String q` **with no value provided** from `q=""`: Spring applies parameter required/binding rules before Bean Validation runs; a "parameter missing" error can differ from a `@Size` error.

### 11.2. @Size on Collections in JSON vs. JSON Payload Size

With request:

~~~json
{
  "members": ["An", "Binh", "Chi", "Dung", "Hoa", "Lan"]
}
~~~

A DTO with `@Size(max=5) List<String> members` will fail because the deserialized List has **6 elements**. However, `@Size` does not limit HTTP body bytes before parsing. To guard against oversized requests, enforce request size limits and configure parsers at the HTTP/Jackson/gateway layer. Post-bind validation does not replace input resource controls.

JSON payloads with duplicate keys may be processed/overwritten by the parser depending on configuration; once the Map is built, `@Size` only sees the actual number of Map entries. If detecting duplicate JSON keys is required, configure the parser accordingly.

## 12. @Size on Nested Elements and Differences from @Valid

### 12.1. Collection Element Constraints

~~~java
@Size(min = 1, max = 5)
private List<@Size(min = 2, max = 20) String> labels;
~~~

- Outer `@Size`: 1–5 labels.
- Inner `@Size`: each label has 2 to 20 Java length units.
- If a label is `null`, the inner `@Size` still accepts null; add `@NotNull` or `@NotBlank` on the element if disallowed.
- A 6-element list containing a 1-character label can produce both a list size error and an element size error.

### 12.2. Validation Inside Child Beans

~~~java
record Item(
    @NotBlank @Size(max = 30) String sku,
    @Size(min = 1, max = 10) List<String> labels
) {}

record Basket(
    @Size(min = 1, max = 10)
    List<@Valid Item> items
) {}
~~~

This is an **illustrative snippet** requiring imports for `List`, `jakarta.validation.Valid`, `NotBlank`, and `Size`. `@Size` outside the List limits item count; `@Valid` requests validating each `Item`, including constraints on `sku` and `labels`.

If you only have `List<Item> items` and an outer `@Size` without `@Valid` where cascading is needed, do not expect Bean Validation to automatically check all fields of `Item`.

### 12.3. Map Keys and Values

~~~java
@Size(max = 3)
private Map<
    @NotBlank String,
    @Size(max = 40) String> translatedLabels;
~~~

`@Size(max=3)` limits the entry count, `@NotBlank` on the key checks key Strings, and `@Size(max=40)` on each value checks value length independently. If null values must be rejected, add `@NotNull` on the value; `@Size` alone allows null.

Do not lump entry-level errors together as "Map too long"; each constraint has its own scope and path. When reporting errors, preserve both path and error code.

## 13. Limits That @Size Does Not Cover

### 13.1. Does Not Constrain Integer or Decimal Magnitude

~~~java
@Min(1)
@Max(100)
private int quantity;
~~~

`@Size(min=1,max=100) int quantity` is not valid standard usage for numeric types. The provider may fail to find a matching validator and report `UnexpectedTypeException` / `ValidationException`. If the input is a **digit string** requiring exactly 6 characters, use `@Size(min=6,max=6)` (and digit character constraints if needed), while numeric magnitude should still be checked with numeric constraints.

### 13.2. Does Not Guarantee Uniqueness or Valid Content

`@Size(max=10) List<String> emails` does not guarantee 10 valid, non-duplicate, or authorized emails. Use element constraints like `@Email` and check duplicates/business relationships separately. `Set` eliminates duplicates per `equals/hashCode`, but that does not mean the raw input before building the Set had no duplicates.

`@Size(max=5) Map<String,Object> settings` also does not ensure keys are allowed, values match a schema, or dangerous keys are absent. Those requirements call for schema/domain validation and appropriate JSON handling.

### 13.3. Does Not Replace Byte Limits or Database Constraints

`@Size(max=255) String title` limits Java `String.length()`, not UTF-8 byte count directly. Some characters take multiple bytes. When storing into a byte-limited database column or sending to a byte-quota system, measure and enforce against the actual metric.

JPA/Hibernate `@Column(length = 255)` describes schema/column mapping, not a Bean Validation constraint automatically enforced across all paths. Some ORM integrations can infer DDL limits from `@Size` metadata depending on configuration/provider; do not rely on that behavior as a cross-database guarantee. Manage schema, request validation, and storage limits separately.

### 13.4. Does Not Define Error Ordering

If combining `@NotBlank` and `@Size(min=3)`, an empty String can trigger multiple violations. `Set<ConstraintViolation<T>>` does not guarantee return order. The UI may want to prioritize showing "required" before "too short", but ordering must be decided by the presentation layer/business rules rather than inferred from iterating the `Set`. Providers may also use fail-fast or group sequences that affect observed violation counts.

## 14. Messages, Groups, and Advanced Parameters

Full constraint declaration:

~~~java
@Size(
    min = 2,
    max = 12,
    message = "Must be between {min} and {max} characters",
    groups = RegistrationChecks.class
)
private String registrationCode;
~~~

This is an **illustrative snippet**; declare the `RegistrationChecks` interface and import `Size`. `groups` specifies which validation pass evaluates the constraint. Calling `validator.validate(bean)` by default generally evaluates only the `Default` group, not all custom groups automatically. When needed:

~~~java
Set<ConstraintViolation<Form>> errors =
    validator.validate(form, RegistrationChecks.class);
~~~

This illustrative snippet assumes `Form`, `RegistrationChecks`, and `validator` exist. When using `@Validated(RegistrationChecks.class)` in Spring, you can select the validation group applied at a boundary, though check Spring MVC/method validation context to avoid confusion.

Other attributes:

- `message`: error message template, which can contain `{min}` and `{max}`.
- `groups`: validation groups; defaults to `Default`.
- `payload`: extension metadata, not used to replace counting rules.
- `@Size.List` or repeatable `@Size` declarations: supports multiple `@Size` constraints on the same target (usually differentiated by group). Avoid setting contradictory bounds without a clear purpose.

If you need different rules across stages, define business groups and test the real call path; `@Size` does not automatically know "create screen" vs. "edit screen" unless groups/boundaries are configured.

## 15. Common Mistakes and Fixes

| Mistake | Why Is It Wrong? | Right Approach |
| --- | --- | --- |
| Assuming `@Size(min=1)` rejects null | Per spec, `@Size` allows null. | Add `@NotNull`, `@NotEmpty`, or `@NotBlank` if data is required. |
| Using `@Size(max=5)` on a List to limit element length | Only limits `List.size()`. | Add `List<@Size(max=5) String>` for elements. |
| Using `@Size(max=10)` on a Map to limit key length | Only counts entries. | Use `Map<@Size(max=10) String, ...>` for keys. |
| Using `@Size(min=2)` assuming whitespace-only strings fail | `length()` still counts whitespace. | Combine `@NotBlank` and a normalization policy if appropriate. |
| Assuming an emoji always counts as one character for `@Size` | Java String counts UTF-16 code units. | Choose code point/grapheme criteria separately if business rules require it. |
| Using `@Size` on `int`/`BigDecimal` | Not a standard supported type. | Use `@Min`/`@Max`/`@Digits` or other numeric constraints. |
| Counting JSON input keys before building a Map | The Map is already constructed by the parser and may overwrite duplicate keys. | Enforce parser limits and schema checks at the input boundary. |
| Putting `@Size` only on a List of beans without `@Valid` | Limits element count, does not cascade into child beans. | Add `List<@Valid Child>` where nested validation is needed. |
| Thinking `@Size(max=255)` guarantees <=255 UTF-8 bytes | Java length and byte length differ. | Define and enforce byte limits separately. |
| Importing only `jakarta.validation-api` and expecting validation to run | Requires a provider and a validation trigger. | Add provider/starter and `Validator.validate` or `@Valid` at the boundary. |
| Returning raw violations/`invalidValue` directly to clients | Can expose data or internal metadata. | Map safely to field/code/message, sorting if needed. |
| Applying `@Size` to a class implementing only `Iterable` | Spec only guarantees `Collection`, not every `Iterable`. | Use `Collection` or a custom constraint if needed. |
| Declaring `@Size` with negative `min` or `max < min` | Nonsensical constraint metadata. | Check boundary rules in code review and tests. |
| Assuming `@Size` always runs automatically on every request | Annotations require Bean Validation to be enabled and properly integrated. | Test the actual controller/binder/service with the provider. |

## 16. Design and Testing Checklist

1. Identify the **actual data type** of the property: `CharSequence`, array, `Collection`, or `Map`.
2. Explicitly state the size unit: Java UTF-16 length, element count, or entry count.
3. Choose business-accurate `min/max`; verify both boundary values **are valid**.
4. Decide whether `null` is allowed; add `@NotNull`/`@NotEmpty`/`@NotBlank` when required.
5. For Strings, decide on trim/normalization and whether grapheme/code point/byte limits are needed.
6. For collections, distinguish **element count** checks from **per-element constraints**.
7. For Maps, distinguish **entry count** from key/value checks.
8. For arrays, remember `@Size` does not validate individual element contents.
9. Enable a provider matching the `jakarta.validation` namespace; verify the execution point (`@Valid`, `@Validated`, or `Validator`).
10. Write tests for null, empty, min−1, min, max, max+1, Unicode data, Lists with invalid elements, and Maps with invalid keys/values.
11. Convert `ConstraintViolation`/`BindingResult` into clear errors with field, code, and message; do not expose sensitive values.
12. To protect system resources, add corresponding HTTP body size, JSON parser, database, and storage limits.

**Self-Check Questions**

1. Does `@Size(min=2,max=4)` accept a `null` String?
2. Does a List of three `null` elements pass `@Size(min=3,max=3)`?
3. Does `@Size(max=2) Map<String,String>` check key count, total value characters, or entry count?
4. Does `"   "` pass `@Size(min=3,max=3)`? Does it pass `@NotBlank`?
5. Does `List<@Size(min=2) String>` limit the number of elements in the List?
6. Does `@Size(max=1)` always pass on a String containing one emoji `"🙂"`?
7. If you want a non-null list with 1–5 elements and each element non-blank, where do you place the constraints?

**Answers:** (1) Yes, null is valid under `@Size`; (2) Yes, if the List actually contains three elements; (3) entry count; (4) passes `@Size`, fails `@NotBlank`; (5) no, it only checks the size of each String; (6) no, `"🙂"` has `String.length()==2`; (7) `@NotEmpty @Size(max=5) List<@NotBlank String>`.

## 17. References

- Jakarta Bean Validation 3.0 Specification, section *`@Size` constraint*: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Jakarta Bean Validation 3.0 API, `Size`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/Size.html
- Jakarta Bean Validation 3.0 API, `NotEmpty`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/NotEmpty.html
- Hibernate Validator 8, *Reference Guide*: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Hibernate Validator 8.0 series and example versions: https://hibernate.org/validator/releases/8.0/
- Spring Framework, *Java Bean Validation*: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring Framework, *Spring MVC Validation*: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
