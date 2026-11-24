# Distinguishing @NotNull, @NotEmpty, and @NotBlank

> **Scope:** Three standard constraints from Jakarta Bean Validation in Java/Spring Framework applications. This lesson focuses on the meaning of `null`, empty strings, whitespace-only strings, collections/maps/arrays; how to choose the annotation matching the data type; and how to integrate validation in Spring MVC. Executable examples use Java 17 and Jakarta Validation via Hibernate Validator (Spring Boot 3.3.x).

## 1. Purpose of the Three Constraints

All three annotations belong to the `jakarta.validation.constraints` package in Jakarta Bean Validation (older projects use `javax.validation.constraints`). They express **three different levels of requirements** on a value:

- **`@NotNull`:** the referenced object must be **non-`null`**. It does not check content, element count, or whitespace.
- **`@NotEmpty`:** the value must be **non-`null` and have length/size greater than 0**. Supports `CharSequence`, `Collection`, `Map`, and arrays; does not treat whitespace-only strings as empty.
- **`@NotBlank`:** a **`CharSequence` value that is non-`null` and contains at least one non-whitespace character**. Used for text requiring meaningful content, such as a display name or required note.

All of them are **value-checking constraints**. They do not trim whitespace, convert `null` to an empty string, populate elements into a collection, or mutate the received object. Results only appear when the application/framework **actually triggers validation**.

| Annotation | Valid Condition | Supported Types per Spec | Is `null` valid? | Is `""` valid? | Is `"   "` valid? |
| --- | --- | --- | --- | --- | --- |
| `@NotNull` | Value is non-`null` | Any reference type; syntactically applicable to primitives, though not useful for null checking | No | Yes | Yes |
| `@NotEmpty` | Non-null and length/size ≥ 1 | `CharSequence`, `Collection`, `Map`, array | No | No | **Yes** |
| `@NotBlank` | Non-null and ≥ 1 non-whitespace character | `CharSequence`, e.g., `String`, `StringBuilder` | No | No | **No** |

In the table, `"   "` consists of three standard U+0020 spaces. For special Unicode characters that look like whitespace, results may depend on the provider/JDK definition of whitespace; you must test the exact character set accepted by the system. Do not assume every blank-looking character is recognized the same way as U+0020.

### 1.1. `@NotNull`: Only Checks Presence of a Reference

```java
import jakarta.validation.constraints.NotNull;

public class OrderInput {
    @NotNull
    private Long customerId;

    @NotNull
    private String comment;
}
```

The code above is a **DTO illustration**, without constructors/getters/setters and not self-executing. `customerId = null` is a violation; `customerId = 0L` still satisfies `@NotNull` because checking for positive numbers requires adding `@Positive` or `@Min(1)`. For `comment`, both `""` and `"   "` **satisfy** `@NotNull`.

Do not use primitive `int` if you want to distinguish "no number provided" from "number 0": primitives always have a default value when declared as fields, and a `@NotNull` constraint cannot detect missing data once it has become an `int`. Use `Integer`/`Long` and combine with range constraints.

### 1.2. `@NotEmpty`: Checks Size, Not Content Meaning

```java
import jakarta.validation.constraints.NotEmpty;
import java.util.List;
import java.util.Map;

public class BasketInput {
    @NotEmpty
    private String promotionCode;

    @NotEmpty
    private List<String> productIds;

    @NotEmpty
    private Map<String, String> attributes;

    @NotEmpty
    private byte[] attachment;
}
```

With `@NotEmpty`:

- `String`: based on `CharSequence.length()`. `""` is invalid; `" "` is valid because its length is 1.
- `List`, `Set`, and other `Collection` types: based on `size()`. `List.of()` is invalid; `List.of("")` is valid in terms of **size**.
- `Map`: based on entry count. A map with one empty key/value still has `size() = 1`.
- **Array**: based on `length`. `new String[0]` is invalid; `new String[]{null}` has one element, so it satisfies **the constraint placed on the array**, even though the element inside is null.

**`@NotEmpty` does not validate individual elements.** To ensure a list has at least one element and each element is text with content, add a constraint on the *type argument* (see Section 5). Do not use `@NotEmpty` on `Long`, `BigDecimal`, or a bean with no length/size concept: those types are unsupported and the provider may report `UnexpectedTypeException` when validation runs.

### 1.3. `@NotBlank`: Checks for Meaningful Text, Does Not Auto-Normalize Strings

```java
import jakarta.validation.constraints.NotBlank;

public class ProfileInput {
    @NotBlank
    private String displayName;
}
```

`@NotBlank` rejects `null`, `""`, and whitespace-only strings. It accepts `" A "` because it contains the non-whitespace character `A`, **but does not automatically turn** `" A "` into `"A"`. To store trimmed names, the application must perform normalization separately and decide consistently whether it occurs before or after validation.

`@NotBlank` is **not** a constraint for `List`/`Map`/arrays or numbers. Attaching it to a list can cause a runtime configuration error due to the lack of a matching validator rather than a normal `ConstraintViolation`.

## 2. Most Confused Behavior Matrix

### 2.1. Direct Comparison on the Same `String` Type

| `String` Value | `@NotNull` | `@NotEmpty` | `@NotBlank` | Why? |
| --- | --- | --- | --- | --- |
| `null` | ❌ | ❌ | ❌ | All three require non-null |
| `""` (length 0) | ✅ | ❌ | ❌ | Object exists, but has no characters |
| `"   "` (3 spaces) | ✅ | ✅ | ❌ | String has length 3, but no content characters |
| `"\t\n"` (tab and newline) | ✅ | ✅ | ❌ | Has characters, but all are ordinary whitespace |
| `"a"` | ✅ | ✅ | ✅ | Has one content character |
| `" a "` | ✅ | ✅ | ✅ | Contains `a`, even though surrounded by whitespace |
| `"0"` | ✅ | ✅ | ✅ | Digit `0` is valid content; does not check numeric semantics |

**Strictness levels on ordinary strings** can be understood as: `@NotBlank` → `@NotEmpty` → `@NotNull` (from stronger to weaker requirement). However, do not treat the three annotations as interchangeable because their **supported type domains differ**.

### 2.2. With Collections, Maps, and Arrays

| Value | `@NotNull` | `@NotEmpty` | `@NotBlank` |
| --- | --- | --- | --- |
| `List<String> = null` | ❌ | ❌ | Not supported on List |
| `List.of()` | ✅ | ❌ | Not supported |
| `List.of("")` | ✅ | ✅ | Not supported |
| `Map.of()` | ✅ | ❌ | Not supported |
| `Map.of("k", "")` | ✅ | ✅ | Not supported |
| `new int[0]` | ✅ | ❌ | Not supported |
| `new int[]{0}` | ✅ | ✅ | Not supported |

`@NotEmpty` guarantees **elements/entries exist**, not that elements are non-null, non-blank strings, positive numbers, or valid nested beans. That is the job of element-level constraints or nested validation.

## 3. Runnable Java 17 Example and Exact Output

The following example intentionally places the three constraints on **three fields holding the same `String` value** to observe the differences without depending on locale-specific error message text. It then validates a list using both `@NotEmpty` and an element-level constraint.

Project structure:

```text
constraint-comparison/
├── pom.xml
└── src/main/java/demo/StandardConstraintsDemo.java
```

**`pom.xml`** — uses `spring-boot-starter-validation` to provide the Jakarta Validation API and Hibernate Validator; the program only uses Jakarta Validation without starting Spring:

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
    <artifactId>constraint-comparison</artifactId>
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

**`src/main/java/demo/StandardConstraintsDemo.java`**:

```java
package demo;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import java.util.List;

public class StandardConstraintsDemo {

    static final class TextFields {
        @NotNull
        private final String presence;

        @NotEmpty
        private final String nonEmpty;

        @NotBlank
        private final String meaningful;

        TextFields(String value) {
            this.presence = value;
            this.nonEmpty = value;
            this.meaningful = value;
        }
    }

    static final class NameList {
        @NotEmpty
        private final List<@NotBlank String> names;

        NameList(List<String> names) {
            this.names = names;
        }
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            checkText(validator, "null", null);
            checkText(validator, "empty", "");
            checkText(validator, "spaces", "   ");
            checkText(validator, "value", "Hoa");

            checkList(validator, "null", null);
            checkList(validator, "empty", List.of());
            checkList(validator, "blankElement", List.of(" "));
            checkList(validator, "valid", List.of("Hoa"));
        }
    }

    private static void checkText(
            Validator validator, String label, String value) {
        List<String> invalidFields = validator
                .validate(new TextFields(value))
                .stream()
                .map(v -> v.getPropertyPath().toString())
                .sorted()
                .toList();

        System.out.println("text." + label + " -> " + invalidFields);
    }

    private static void checkList(
            Validator validator, String label, List<String> names) {
        int count = validator.validate(new NameList(names)).size();
        System.out.println("list." + label + " -> count=" + count);
    }
}
```

Run with JDK 17+ and Maven in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.StandardConstraintsDemo
```

**Lines printed by the program** (excluding extra logs if emitted by the Maven/provider environment):

```text
text.null -> [meaningful, nonEmpty, presence]
text.empty -> [meaningful, nonEmpty]
text.spaces -> [meaningful]
text.value -> []
list.null -> count=1
list.empty -> count=1
list.blankElement -> count=1
list.valid -> count=0
```

Output explanation:

1. For `null`, all three fields violate because all three constraints reject null.
2. For `""`, `presence` is valid under `@NotNull`; `nonEmpty` and `meaningful` violate.
3. For `"   "`, `@NotEmpty` considers the string to have length 3 so it is valid; `@NotBlank` still rejects it.
4. For `"Hoa"`, all three are valid.
5. For `List.of()`, the `@NotEmpty` constraint on the collection violates.
6. For `List.of(" ")`, the collection is non-empty, but the **element** violates `@NotBlank`.
7. For `List.of("Hoa")`, both the collection and the element are valid.

The example sorts field names to avoid depending on the iteration order of `Set<ConstraintViolation<?>>`; it also avoids printing `getMessage()` because message text can be internationalized. Violation counts in the example are controlled because each scenario only declares those specific constraints, without relying on provider evaluation order.

## 4. Choosing Annotations by Data Type and Business Requirement

Do not choose by which annotation name sounds "stricter"; answer **what is the data type, and what is the invalid condition?**

| Need | Suggested Declaration | Why |
| --- | --- | --- |
| Required `Long` ID | `@NotNull Long customerId` | Numbers have no "empty" concept; add `@Positive` if positive required |
| Username must have characters, not all spaces | `@NotBlank String username` | Rejects null, empty, and whitespace-only |
| Token must have at least one character; spaces may be valid per contract | `@NotEmpty String token` | Checks length without rejecting whitespace |
| Product list must have elements | `@NotEmpty List<Product> products` | Checks collection size |
| Label list must have elements and no blank labels | `@NotEmpty List<@NotBlank String> labels` | Combines container and element constraints |
| Map is optional, but if sent must have entries | Handle conditional rule separately; `@NotEmpty` rejects both null and empty maps | Only use `@NotEmpty` if **both map and entries are required** |
| Monetary amount must be provided and positive | `@NotNull @Positive BigDecimal amount` | Do not use `@NotEmpty` on `BigDecimal` |
| Non-empty string with max 50 characters | `@NotEmpty @Size(max=50) String code` | One constraint for presence/min length, one for max limit |

**Note on `null` and other constraints:** `@Size(min=1)` does not completely replace `@NotEmpty`: `@Size` generally treats `null` as valid per the specification. If `@Size` is used alone, a null value can pass validation. Combine with `@NotNull`/`@NotEmpty` when data is required.

## 5. Combining with Element Constraints and Nested Beans

### 5.1. Collection with Data and Elements with Data

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import java.util.List;

public class CampaignRequest {
    @NotEmpty
    private List<@NotBlank String> tags;

    // Constructor/getter/setter matching the binding style.
}
```

The levels have **different** meanings:

- `@NotEmpty` before `List` checks that the list reference is non-null and has at least one element.
- `@NotBlank` in `List<@NotBlank String>` checks each element string. A null, empty, or blank element causes an error even if the list is non-empty.
- Container element validation is supported in Jakarta Bean Validation 2.0+, suitable for collections/maps with constrained type arguments.
- `List.of("")` has one element so it passes the collection check, but fails on the element.
- `@NotBlank List<String>` placed on the whole list is the **wrong constraint type**.

If elements are nested DTOs, distinguish reference constraints from deep bean validation:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.util.List;

public class OrderRequest {
    @NotEmpty
    private List<@NotNull @Valid OrderLine> lines;

    // OrderLine contains constraints on its own fields.
}
```

Here `@NotEmpty` requires the list to have elements; `@NotNull` prevents null elements; `@Valid` requests validating the constraints inside each `OrderLine` object. `@Valid` **does not automatically** make the list non-empty. This code snippet is a structural example; `OrderLine` must be defined to compile in a real project.

### 5.2. `@NotBlank` Is Usually Enough; Adding `@NotNull` Is Not Strictly Necessary

```java
@NotNull
@NotBlank
private String title;
```

Placing both together like above is usually **logically redundant** because `@NotBlank` already rejects null. It can also produce **two violations for the same null value**, depending on validation groups and configuration. For a form that simply wants one "title is required" message, `@NotBlank` is the clearer choice.

Similarly, `@NotEmpty` already includes "not null", so `@NotNull @NotEmpty` is usually unnecessary if they share the same validation group and meaning. They can be separated intentionally to assign different messages or groups, provided you handle multiple-error display properly.

### 5.3. `@NotBlank` Does Not Replace Format Validation

Username `"a"` satisfies `@NotBlank` yet may be too short; email `"not-an-email"` also satisfies `@NotBlank`. Combine constraints to match requirements:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class AccountInput {
    @NotBlank
    @Size(min = 3, max = 32)
    private String username;

    @NotBlank
    @Email
    private String email;
}
```

- `@NotBlank` checks for content, including requiring not just spaces.
- `@Size` checks length/size, without guaranteeing meaningful text or trimmed spaces.
- `@Email` checks email format within the validator's contract; by itself it does not replace making the field required (especially when null).
- If business rules require stripping whitespace or normalizing Unicode, implement a dedicated processing step and write tests explicitly covering **before/after** normalization values.

## 6. Using with Spring MVC / Spring Boot

### 6.1. Validation Flow

Spring MVC can trigger Jakarta Validation via `@Valid` or `@Validated` on bound arguments. With Spring Boot 3.x, add the `spring-boot-starter-validation` dependency (a provider compatible with `jakarta.validation`) to have a validator. In a typical REST example:

```text
HTTP JSON body
     │
     ▼
Jackson deserialize → CreateUserRequest
     │
     ▼
@Valid / Spring MVC validation
     │
     ├── valid ───────► controller logic
     │
     └── invalid ─────► BindingResult / validation exception / HTTP 400
```

**`@NotNull`, `@NotEmpty`, and `@NotBlank` do not run automatically on constructor calls**, and merely adding annotations to fields does not mean every controller will validate. There must be an appropriate trigger: `@Valid`, `@Validated`, or calling `jakarta.validation.Validator#validate(...)`.

### 6.2. Illustrative DTO and Controller

This is a **snippet to add to a Spring Boot 3 application with Web MVC and starter-validation**, not a standalone Java file:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

public record CreateUserRequest(
    @NotNull Long departmentId,
    @NotBlank String displayName,
    @NotEmpty List<@NotBlank String> roles
) {}

@RestController
public class UserController {
    @PostMapping("/users")
    public ResponseEntity<Void> create(
            @Valid @RequestBody CreateUserRequest input) {
        // In a real application, run business logic after data is valid.
        return ResponseEntity.noContent().build();
    }
}
```

Under standard Spring MVC configuration, a request with body:

```json
{
  "departmentId": 3,
  "displayName": "   ",
  "roles": ["ADMIN"]
}
```

will trigger a `@NotBlank` violation for `displayName`. A body with `"roles": []` violates `@NotEmpty`; `"roles": [""]` violates the element-level `@NotBlank` constraint, even though the list is non-empty. Without a `BindingResult` handled in the controller, Spring MVC typically returns HTTP 400 for request body validation errors, though the **exact JSON error structure** depends on `@ControllerAdvice` and application configuration.

**Distinguish binding errors from validation errors:** If the JSON is malformed or a numeric field cannot be deserialized, Jackson/the message converter may fail *before* Bean Validation runs. You will not necessarily receive a `@NotNull`/`@NotBlank` violation for an unparseable field. When using `@ModelAttribute` instead of `@RequestBody`, form/query data goes through data binding and how errors are recorded into `BindingResult` can differ.

### 6.3. Missing Values, Null, and Empty Strings at the HTTP Boundary

Suppose a client sends syntactically valid bodies:

```json
{}
```

```json
{"displayName": null}
```

```json
{"displayName": ""}
```

```json
{"displayName": "   "}
```

When the DTO has a reference field `String displayName` and the mapper sets missing fields to null, all of these are **invalid** under Bean Validation with `@NotBlank`; however, these cases differ in origin and logging. Jackson configuration, constructor/record binding, default values, or custom deserializers can alter how missing properties are handled **before** validation. Do not assume missing HTTP fields always turn into null in every DTO.

With Spring data binding for forms, configurations such as `StringTrimmerEditor` may exist to convert whitespace-only strings to null before constraints run. Therefore, when debugging, determine the **actual value entering Bean Validation** before concluding which annotation passed or caught the error.

## 7. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Resolution |
| --- | --- | --- |
| Using `@NotNull` to require user text input | `""` and `"   "` remain valid | Choose `@NotBlank` for meaningful text |
| Using `@NotEmpty` for usernames | Space-only strings remain valid | Use `@NotBlank` |
| Using `@NotBlank` for `List`, `Map`, array, `Integer` | Unsupported type, may cause validator errors | Use `@NotEmpty` for containers, `@NotNull` for references/numbers |
| Using `@NotEmpty List<String>` and assuming elements are valid | List containing `""` or `null` may still pass | Add `List<@NotBlank String>` or appropriate element constraints |
| Using `@Size(min=1)` and assuming null is blocked | `@Size` ignores null per spec | Combine with `@NotNull` or use `@NotEmpty` |
| Attaching `@NotNull @NotBlank` "to be safe" | Duplicate meaning and possibly two errors for null | `@NotBlank` is usually enough |
| Using `@NotBlank` and assuming values are trimmed | Data still retains leading/trailing spaces | Normalize intentionally, test before/after |
| Using primitive `int` with `@NotNull` | Primitives cannot be null | Use `Integer` to distinguish missing values |
| Missing Bean Validation implementation dependency | Annotations exist but validation does not run as expected | Use a compatible provider, such as `spring-boot-starter-validation` |
| Using `javax.validation` with Spring Boot 3/Jakarta | Mismatched API generation | Switch to `jakarta.validation` and compatible dependencies |
| Missing `@Valid`/`@Validated` or validator call | No trigger to validate data | Enable validation at the boundary and test it |
| Asserting exact English message text | Easily breaks when locale/provider changes | Assert field/path/constraint type and stable error codes |
| Assuming all blank-looking Unicode characters act identically as whitespace | Unicode rules can differ across runtimes/providers | Test specific characters and define clear input normalization rules |

### 7.1. Unicode Whitespace and Special Characters

`@NotBlank` is specified for `CharSequence` as requiring at least one non-whitespace character. Do not conclude that *every character classified by Unicode as whitespace* will be treated identically by every provider; characters such as no-break space, zero-width space, or narrow space may behave differently from ordinary spaces. Do not silently modify input with `trim()` or `strip()` without testing the impact on the contract.

If the system handles multilingual data or usernames with complex rules, define validity policies (normalization, length limits by Unicode code point, allowed characters) separately beyond the three annotations. `@NotBlank` itself does not protect against all tricky string cases, ensure HTML-safe content, or block control characters.

### 7.2. Annotations Are Not Equivalent to Database Constraints

Bean Validation's `@NotNull` is a check rule **at the application layer when validation is triggered**. Even though Hibernate ORM can interpret validation metadata in certain integration modes, **do not rely** on this annotation to replace database `NOT NULL`, column lengths, or data integrity checks. For example, database `NOT NULL` blocks null but not `""` or `"   "`; a "must contain letters" rule must be checked at the appropriate layer. If there are multiple data write paths, enforce consistency measures according to system requirements.

## 8. Testing and Review Checklist

Before choosing an annotation or concluding that a form/API validates properly, verify these cases:

- [ ] For `String`, tested `null`, `""`, `"   "`, `"x"`, and strings with leading/trailing whitespace?
- [ ] For collections, tested `null`, empty collection, collection with an empty element, and valid collection?
- [ ] If elements must also be valid, added type-use constraints/`@Valid` in the right place?
- [ ] For numbers, used `@NotNull` plus appropriate numeric constraints instead of `@NotEmpty`?
- [ ] If using `@Size`/`@Email`/`@Pattern`, separately examined behavior when input is null?
- [ ] If applying `@NotBlank` to Unicode text, tested actual whitespace characters and normalization rules?
- [ ] In Spring Boot 3+, imported the right `jakarta.validation.*` package and included a provider?
- [ ] Added a validation trigger (`@Valid`/`@Validated`/`Validator.validate`), rather than just declaring annotations?
- [ ] Tested HTTP responses distinguishing malformed JSON, binding/type conversion failures, and constraint violations?
- [ ] When testing, avoided relying on `Set<ConstraintViolation>` order or locale-translated messages?

**Remember:** `@NotNull` asks "**is there a reference?**"; `@NotEmpty` asks "**is there at least one element/character?**"; `@NotBlank` asks "**does the string have at least one non-whitespace character?**". Choose according to **data type and business meaning**, then test at the exact Spring Bean Validation trigger boundary.

### Official References

- [Jakarta Validation 3.0 — @NotNull](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/NotNull.html)
- [Jakarta Validation 3.0 — @NotEmpty](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/NotEmpty.html)
- [Jakarta Validation 3.0 — @NotBlank](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/NotBlank.html)
- [Jakarta Bean Validation 3.0 — Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Hibernate Validator 8 — Reference Guide](https://docs.jboss.org/hibernate/validator/8.0/reference/en-US/html_single/)
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring MVC — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
