# Supported Data Types and UnexpectedTypeException in Jakarta Bean Validation and Spring

## 1. The Core Problem: Constraints Do Not Apply to Every Java Type

Standard annotations such as `@NotBlank`, `@Size`, `@Min`, `@Positive`, `@Past`, or `@Email` each declare a rule, yet **each rule supports only specific data types**. Java generally allows attaching an annotation to a field even when the field's Java type is incompatible: an annotation having `@Target(FIELD)` does not mean it works on all field types.

Example:

```java
@NotBlank
private Integer quantity;
```

The snippet above can **compile successfully**, because Java checks annotation placement targets rather than knowing `@NotBlank` is only for `CharSequence`. When a Bean Validation pass processes this field, the provider finds no suitable `ConstraintValidator` for the `(@NotBlank, Integer)` pair and throws `jakarta.validation.UnexpectedTypeException`.

Distinguish:

- **Value violates a constraint on a supported type:** the provider creates a `ConstraintViolation`; e.g., `@Positive Integer quantity = 0`.
- **Constraint declared on an incompatible or ambiguous type:** the provider cannot resolve a matching implementation and throws `UnexpectedTypeException`; e.g., `@NotBlank Integer quantity = 1`.
- **Missing provider / validation not triggered:** a separate configuration or missing-trigger issue; cannot be diagnosed solely from whether a field carries annotations.

Key message: **choose the constraint according to the declared Java type first, then evaluate which values are valid**. Do not assume an annotation has a validator for your type simply because its name sounds plausible.

## 2. How Does Bean Validation Decide Type Support?

A constraint can be implemented by one or more implementations of the interface:

```java
ConstraintValidator<ConstraintAnnotation, SupportedType>
```

For instance, conceptually a validator for `@NotBlank` accepts `CharSequence`; because `String` implements `CharSequence`, it matches. `Integer` is not a subtype of `CharSequence`, so it does not match.

During a validation pass, the provider inspects:

1. The applied **constraint annotation**, such as `@Size`.
2. The **declared type** at the validated location, such as `String`, `List<String>`, `BigDecimal`, or `Integer`.
3. The list of `ConstraintValidator`s known to the provider for that constraint, including standard implementations and configured extensions.
4. Type-matching rules and selecting the **single most specific** validator among matching candidates.

Two situations lead to `UnexpectedTypeException`:

- **No matching validator:** e.g., `@NotBlank` on `Integer`.
- **Multiple matching validators with no single most specific one:** often seen with custom constraints when two validators accept unrelated interfaces and the field's type implements both.

Per Jakarta Validation, matching relies on subtype relationships between the validated type and validator-supported types; primitives are treated as equivalent to their wrapper types during validator resolution. Under normal setups, the error is detected when calling `validate(...)`, or earlier when the provider resolves metadata. It is not a Java syntax error.

```text
Constraint annotation + declared field type
                      |
                Provider lookup
                      |
       +--------------+---------------+
       |              |               |
  Exactly 1 most   No matching    Multiple equally
  specific type       type        specific types
       |              |               |
    isValid(...)    UnexpectedTypeException
       |
       +-- true  -> no violation
       +-- false -> ConstraintViolation
```

Because this is a type-based validator resolution error, having a current value of `null` **does not guarantee avoiding** `UnexpectedTypeException`. Do not rely on a few null-data tests to prove annotation declarations are valid.

## 3. Quick Lookup Table of Data Types by Standard Constraint

The table below follows **Jakarta Validation 3.1, section "Built-in Constraint definitions"**. Types or features added by a specific provider are noted separately; do not treat extensions as portable guarantees across providers.

| Constraint | Standard Supported Types | Main Condition | Common Misuse |
| --- | --- | --- | --- |
| `@Null`, `@NotNull` | Any type | Must be null / must not be null | Using `@NotNull` on primitive `int` cannot detect missing input |
| `@AssertTrue`, `@AssertFalse` | `boolean`, `Boolean` | True / false | Placing on `String` containing `"true"` |
| `@NotBlank` | `CharSequence` and subtypes like `String`, `StringBuilder` | Non-null, at least one non-whitespace char | Placing on `Integer`, `List`, enum |
| `@NotEmpty` | `CharSequence`, `Collection`, `Map`, arrays | Non-null, size greater than 0 | Placing on numbers or arbitrary JavaBeans |
| `@Size(min,max)` | `CharSequence`, `Collection`, `Map`, arrays | Length/element count within closed range | Placing on `Integer`/`BigDecimal` to check numeric bounds |
| `@Pattern(regexp=...)` | `CharSequence` | String matches regex | Placing on enum or number |
| `@Email` | `CharSequence` | Well-formed email per provider | Placing on `Integer`, `byte[]` |
| `@Min`, `@Max` | `BigDecimal`, `BigInteger`, `byte/short/int/long` and wrappers | Greater/less than or equal to `long` threshold | Placing on `String`, `LocalDate`, `List` |
| `@DecimalMin`, `@DecimalMax` | Integral types and `BigDecimal/BigInteger` above, plus `CharSequence` | Compares against string decimal threshold; has `inclusive` | Using to limit string length |
| `@Positive`, `@PositiveOrZero` | `BigDecimal`, `BigInteger`, numeric primitives/wrappers including `float/double` | `> 0` / `>= 0` | Placing on `String` containing digits |
| `@Negative`, `@NegativeOrZero` | Same numeric types as `@Positive` | `< 0` / `<= 0` | Placing on strings or enums |
| `@Digits(integer, fraction)` | `BigDecimal`, `BigInteger`, `CharSequence`, integral types and wrappers | Limits integer and fractional digit counts | Using to cap absolute magnitude or applying to `LocalDate` |
| `@Past`, `@PastOrPresent` | `Date`, `Calendar`, and standard supported `java.time` date/time types | Before present / before or equal to present | Placing on unparsed ISO `String` |
| `@Future`, `@FutureOrPresent` | Same temporal types as `@Past` | After present / after or equal to present | Placing on `Long` timestamp or `String` |

**Standard note for floating-point:** `float`/`double` **are not in the mandatory supported type set for `@Min`, `@Max`, `@DecimalMin`, and `@DecimalMax`** due to rounding risks; some providers add extensions. By contrast, `@Positive`/`@Negative` and their "or zero" variants **do** support `float`/`double` per spec. When monetary values or decimal precision matter, prefer `BigDecimal`.

**Choose by business meaning instead of memorizing tables:** an email string is checked with `@Email`, a collection of items uses `@NotEmpty`/`@Size`, a quantity uses `@Positive`/`@Min`, an end date uses `@Future`. The same phrase "greater than" can refer to **length**, **numeric value**, or **point in time**: they are different constraint families.

## 4. `@NotNull`, `@NotEmpty`, `@NotBlank`, and `@Size` Do Not Replace One Another

They can all appear on `String`, yet their semantics differ.

| `String` Value | `@NotNull` | `@NotEmpty` | `@NotBlank` | `@Size(min=1)` |
| --- | --- | --- | --- | --- |
| `null` | Error | Error | Error | Valid |
| `""` | Valid | Error | Error | Error |
| `"   "` | Valid | Valid | Error | Valid |
| `"abc"` | Valid | Valid | Valid | Valid |

`@Size` treats `null` as valid by default, so when requiring a name of 3–50 characters, `@NotBlank` is typically combined with `@Size(min=3, max=50)`.

```java
@NotBlank
@Size(min = 3, max = 50)
private String displayName;
```

For lists, `@NotBlank` **does not mean** "non-empty list":

```java
@NotEmpty
private List<String> tags;

@Size(min = 1, max = 10)
private List<String> categories;
```

Both snippets above are bean fields with `List` and constraint imports. They check the **element count** of the collection. To validate the **content of each string inside**, place the constraint on the type argument, e.g., `List<@NotBlank String>`.

`@NotNull` on `int` always passes null checks because primitives have no null value. For inputs that may be absent, use wrapper `Integer` with `@NotNull`; use `@Positive` to check positivity when present.

## 5. Numeric Types: Magnitude Differs from Length, Precision Differs from Range

Wrong example:

```java
@Size(min = 1, max = 10)
private Integer quantity; // Wrong: Integer has no "size" per @Size
```

Replace with:

```java
@NotNull
@Min(1)
@Max(10)
private Integer quantity;
```

Or if only > 0 is needed:

```java
@NotNull
@Positive
private Integer quantity;
```

For money:

```java
@NotNull
@DecimalMin(value = "0.00", inclusive = true)
@Digits(integer = 8, fraction = 2)
private BigDecimal price;
```

`@DecimalMin("0.00")` ensures non-negativity, while `@Digits(integer=8,fraction=2)` limits digit counts. `@Digits` is **not** a value-bound constraint; for example, `99999999.99` fits the digit structure yet may exceed an unexpressed business cap.

For `BigDecimal`, use integer and decimal thresholds per the specific contract; **`@Min` takes a `long` attribute**, whereas `@DecimalMin` takes a string to express bounds like `"0.01"`. Do not put `@Size(max=8)` on `BigDecimal` to cap magnitude.

Using `@Positive` with `double` is supported by the spec, yet IEEE 754 precision and NaN/infinity cases (provider-dependent) must be controlled with appropriate data types/rules; do not treat Bean Validation as a substitute for picking the right numeric type.

## 6. Dates, Times, and String Values: Must Parse to the Right Temporal Type

Wrong example:

```java
@Past
private String birthDate; // Wrong per spec: String is not a temporal type
```

Fix:

```java
@NotNull
@Past
private LocalDate birthDate;
```

In a Spring MVC API, an input string `"2000-01-01"` must be bound/parsed into `LocalDate` before the provider checks `@Past`. You can use `@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)` for query/form binding; JSON bodies use appropriate Jackson configuration. `@DateTimeFormat` **is a conversion mechanism**; it does not extend `@Past` to `String`.

Standard temporal types supported by `@Past`/`@Future` and their variants include `java.util.Date`, `Calendar`, `Instant`, `LocalDate`, `LocalDateTime`, `LocalTime`, `OffsetDateTime`, `OffsetTime`, `ZonedDateTime`, `MonthDay`, `Year`, `YearMonth`, and chronology types such as `HijrahDate`, `JapaneseDate`, `MinguoDate`, `ThaiBuddhistDate`.

"Present" in temporal constraints is supplied by Jakarta Validation's `ClockProvider`. Temporal tests should use a fixed `ClockProvider` when results must be invariant across run times; pay special attention to timezones when using `LocalDate`/`LocalTime`.

Placing `@Future` on a `Long` representing epoch milliseconds is **not** portable usage. If you must receive numeric epoch values, convert them to `Instant` at the application boundary or write a properly typed custom constraint.

## 7. How Does UnexpectedTypeException Differ from ConstraintViolation?

`jakarta.validation.UnexpectedTypeException` is a subclass of:

```text
RuntimeException
  └── ValidationException
       └── ConstraintDeclarationException
            └── UnexpectedTypeException
```

It indicates **no validator could be resolved for the constraint/type declaration**. It is neither a normal `ConstraintViolation` nor a `ConstraintViolationException` (a different class, often used by Spring in method validation integrations).

Compare two fields:

```java
@Positive
private Integer quantity = 0; // Right type; value fails constraint
```

Calling `validator.validate(bean)` returns a `Set<ConstraintViolation<?>>` with an error on `quantity`. Not `UnexpectedTypeException`.

```java
@NotBlank
private Integer quantity = 7; // Wrong type; constraint cannot run
```

Calling `validator.validate(bean)` throws `UnexpectedTypeException` instead of returning a field violation set. `Integer` does not implement `CharSequence`, regardless of whether the value is 7, 0, or null.

With Hibernate Validator, the message typically looks like:

```text
HV000030: No validator could be found for constraint
'jakarta.validation.constraints.NotBlank' validating type
'java.lang.Integer'. Check configuration for 'quantity'
```

This is a **sample message**, not a guarantee of identical wording across versions/providers. `HV000030` is a Hibernate Validator message code; the Jakarta API standardizes the **exception type**, not exact message text emitted by every provider.

Do not catch `UnexpectedTypeException` and turn every case into "invalid user input". Incompatible constraint/type pairs are almost always **server-side programming or configuration bugs**; fix the DTO/annotation/custom validator and add tests to catch them early.

## 8. Runnable Example with Java 17 and Spring Boot

The complete example below intentionally places a mistyped constraint in **a separate class**, after validating normal valid and invalid objects. That way we cleanly distinguish:

1. Bean satisfying all rules → 0 violations.
2. Bean with 5 invalid values on valid field types → 5 violations.
3. Bean placing `@NotBlank` on `Integer` → throws `UnexpectedTypeException`.

Structure:

```text
constraint-type-demo/
├── pom.xml
└── src/main/java/demo/ConstraintTypeDemo.java
```

### `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.8</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>constraint-type-demo</artifactId>
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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugins>
    </build>
</project>
```

### `src/main/java/demo/ConstraintTypeDemo.java`

```java
package demo;

import java.time.LocalDate;
import java.util.List;
import java.util.stream.Collectors;

import jakarta.validation.UnexpectedTypeException;
import jakarta.validation.constraints.Future;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ConstraintTypeDemo {

    public static void main(String[] args) {
        SpringApplication.run(ConstraintTypeDemo.class, args);
    }

    @Bean
    ApplicationRunner run(jakarta.validation.Validator validator) {
        return args -> {
            Order valid = new Order(
                    "Linh",
                    List.of("java"),
                    3,
                    "ABC",
                    LocalDate.of(2100, 1, 1));

            System.out.println("Valid violations: "
                    + validator.validate(valid).size());

            Order invalid = new Order(
                    "   ",
                    List.of(),
                    0,
                    "A",
                    LocalDate.of(2000, 1, 1));

            var violations = validator.validate(invalid);
            String paths = violations.stream()
                    .map(v -> v.getPropertyPath().toString())
                    .sorted()
                    .collect(Collectors.joining(", "));

            System.out.println("Invalid violations: "
                    + violations.size());
            System.out.println("Invalid fields: " + paths);

            try {
                validator.validate(new WrongType());
            } catch (UnexpectedTypeException ex) {
                System.out.println("Mismatched constraint: "
                        + ex.getClass().getSimpleName());
            }
        };
    }

    static final class Order {
        @NotBlank
        private final String name;

        @NotEmpty
        private final List<String> tags;

        @Positive
        private final Integer quantity;

        @Size(min = 3, max = 8)
        private final String code;

        @Future
        private final LocalDate deliveryDate;

        Order(String name, List<String> tags,
              Integer quantity, String code, LocalDate deliveryDate) {
            this.name = name;
            this.tags = tags;
            this.quantity = quantity;
            this.code = code;
            this.deliveryDate = deliveryDate;
        }
    }

    static final class WrongType {
        // Intentionally wrong to demonstrate UnexpectedTypeException.
        @NotBlank
        private final Integer quantity = 7;
    }
}
```

Run with Maven and JDK 17+ in `constraint-type-demo`:

```bash
mvn spring-boot:run
```

Aside from normal startup logs, the lines printed by the program are:

```text
Valid violations: 0
Invalid violations: 5
Invalid fields: code, deliveryDate, name, quantity, tags
Mismatched constraint: UnexpectedTypeException
```

**Why 5 errors?** `"   "` fails `@NotBlank`, `List.of()` fails `@NotEmpty`, 0 fails `@Positive`, `"A"` is too short for `@Size(min=3)`, and year 2000 is in the past so it fails `@Future`. Property paths are sorted before printing because `Set<ConstraintViolation<?>>` does not guarantee iteration order.

**Why is the third failure different?** `WrongType.quantity` has declared type `Integer`, whereas `@NotBlank` only supports `CharSequence`. The provider cannot pick a suitable validator, so no ordinary "valid/invalid value" check can happen.

The example uses `spring-boot-starter-validation` so Boot provides a provider and a Spring-managed `jakarta.validation.Validator`. The Java code and output above can be verified with Maven; when copying into another project, preserve matching packages, files, and dependencies. Do not treat a standalone demo running as proof that every API/controller in an app triggers validation automatically; check each entrypoint individually.

## 9. Common Mistyped Examples and Fixes

### A. Integer Using `@NotBlank`

Wrong:

```java
@NotBlank
private Integer age;
```

Right, if age is required to be 0 or above:

```java
@NotNull
@Min(0)
private Integer age;
```

If age must be strictly greater than 0, use `@Positive` instead of `@Min(0)`.

### B. Collection Using `@NotBlank`

Wrong:

```java
@NotBlank
private List<String> members;
```

Right:

```java
@NotEmpty
private List<@NotBlank String> members;
```

`@NotEmpty` checks that the list has at least one element, while `@NotBlank` on the type argument checks **each string**.

### C. Enum Stored in a SQL VARCHAR Column

Wrong:

```java
@Pattern(regexp = "NEW|DONE")
@Enumerated(EnumType.STRING)
private Status status;
```

Even though JPA persists the enum as a string in the database, **the Java field type is still `Status`**, so `@Pattern` (which only accepts `CharSequence`) is invalid. Use:

```java
@NotNull
@Enumerated(EnumType.STRING)
private Status status;
```

and define the enum constants cleanly. If business rules must restrict allowed states, use a custom constraint supporting `Status` or check at the business boundary. The JPA lines above are **illustrative fields**, requiring `jakarta.persistence.*` imports and a valid `Status` enum.

### D. Numeric Magnitude Using `@Size`

Wrong:

```java
@Size(max = 8)
private BigDecimal total;
```

Right when bounding numeric value:

```java
@DecimalMax("99999999.99")
@DecimalMin("0.00")
private BigDecimal total;
```

If you also want at most 8 integer digits and 2 fractional digits, add `@Digits(integer=8, fraction=2)`.

### E. Date Kept as `String` Using `@Past`

Wrong:

```java
@Past
private String birthday;
```

Right: parse to `LocalDate` and validate `@Past`, or if business requirements force keeping a string, write a custom constraint on `CharSequence` to parse/validate the date under a clear contract. Do not convert a date string into a number to apply `@Min`.

## 10. Validating Collection Elements and Container Element Constraints

Jakarta Validation supports constraints on **type arguments** and cascading via **value extractors**. This is where container types and element types are easily confused.

```java
@NotEmpty
private List<@NotBlank String> labels;

@Size(min = 1)
private Map<@NotBlank String, @Positive Integer> stockByCode;
```

The two illustrative fields above have:

- Constraint **placed on `List`**: `@NotEmpty` requires at least one element.
- Constraint **placed on `String` inside `List`**: `@NotBlank` validates each label.
- Constraint **placed on `Map`**: `@Size(min=1)` checks entry count.
- Constraints **placed on key/value**: keys must be non-blank strings; quantity values must be greater than 0.

If you write `List<@NotBlank Integer>`, the annotation sits on element type **`Integer`** and is still the wrong type; moving an annotation from the field into a type argument cannot turn an `Integer` into a `CharSequence`.

With nested beans:

```java
@NotEmpty
private List<@Valid Address> addresses;
```

`@Valid` triggers **cascading** into each `Address` when the parent object is validated; it is not a "non-empty" constraint. `@NotEmpty` ensures the collection has elements; to also ensure no element is null, add `@NotNull` on the type argument. Watch out for providers/extractors with custom containers such as wrapper classes. Not every custom container is automatically known to the provider for extracting elements: a `ValueExtractor` may be required.

**Distinguish errors:** a container element with an incompatible constraint type can throw `UnexpectedTypeException`, while a missing/unresolvable `ValueExtractor` can raise another `ValidationException`/`ConstraintDeclarationException` depending on the case. Read the **actual exception type**, and do not blame every nested/container issue on HV000030.

## 11. `null` Cases: Right Type Still Needs the Right Constraint

Most constraints checking **content/format** treat `null` as valid; they do not replace `@NotNull`.

| Constraint | Is `null` Valid? | Notes |
| --- | --- | --- |
| `@NotNull` | No | Requires presence; ignores inner content |
| `@Null` | Yes | Requires value to be null |
| `@NotBlank` | No | Also rejects empty/whitespace-only strings |
| `@NotEmpty` | No | Also rejects empty strings/collections/maps/arrays |
| `@Size`, `@Pattern`, `@Email` | Yes | Pair `@NotNull`/`@NotBlank` if required |
| `@Min`, `@Max`, `@Positive`, `@Digits` | Yes | Null values are skipped; add `@NotNull` if field is required |
| `@Past`, `@Future`, and variants | Yes | Missing dates must be handled separately |
| `@AssertTrue`/`@AssertFalse` on `Boolean` | Yes | Null is considered valid per spec |

Example of a required email:

```java
@NotBlank
@Email
private String email;
```

`@Email` handles formatting and `@NotBlank` requires content. Exact "valid email" criteria are partially left to the provider by Jakarta Validation; if the system has a specific contract, document and test it.

Understand **two independent dimensions**: "does the validator support the type?" and "does the value satisfy the rule?". Null being valid only answers the second dimension once constraint and type already match.

## 12. Provider Extensions and API Portability

Jakarta Validation defines standard constraints in `jakarta.validation.constraints`. Hibernate Validator also provides extra constraints in `org.hibernate.validator.constraints`, such as `@Length`, `@Range`, and `@URL`; those are **provider-specific features** that may have non-standard type sets and behaviors.

A provider may also extend supported types beyond the mandatory standard set for built-in constraints. For example, a version of Hibernate Validator might supply validators for certain numeric/string types outside the standard table. This creates two design considerations:

1. **Applications needing portability across providers:** rely only on types guaranteed by the Jakarta Validation specification; prefer standard annotations and proper models.
2. **Applications intentionally depending on Hibernate Validator:** verify the exact version's documentation and write integration tests. State the dependency explicitly; do not interpret a provider extension as a guarantee for all Jakarta providers.

Likewise, Spring Framework 6+ / Boot 3+ projects use `jakarta.validation.*`; older Spring 5/Boot 2 code typically uses `javax.validation.*`. Mixing annotations from both generations or incompatible provider/API versions can cause behaviors beyond `UnexpectedTypeException`. Diagnose dependencies and imports before changing types or constraints.

## 13. Custom Constraints: Specific Type Support and Ambiguous Matches

Suppose we have annotation `@ValidCode` and implementation:

```java
public final class ValidCodeValidator
        implements ConstraintValidator<ValidCode, CharSequence> {

    @Override
    public boolean isValid(
            CharSequence value,
            ConstraintValidatorContext context) {
        return value == null || value.toString().startsWith("VN-");
    }
}
```

This is an **illustrative class snippet**, requiring a `ValidCode` annotation with `@Constraint(validatedBy=ValidCodeValidator.class)`, `jakarta.validation.*` imports, and placement in a matching source file. Applying `@ValidCode` to `String` works because `String implements CharSequence`. Applying it to `Integer` finds no matching validator and can throw `UnexpectedTypeException`.

If a second type must be supported, define **a separate `ConstraintValidator<ValidCode, Integer>`** with clear semantics and list both implementations in `validatedBy`. Do not cast everything inside a validator not declared for that type; nor use `Object` as a catch-all if business rules distinguish data types.

A subtler failure:

- Validator A accepts `CharSequence`.
- Validator B accepts `Serializable`.
- The field is declared as `String`, which implements **both interfaces**.
- `CharSequence` and `Serializable` do not inherit from each other, so there is no single "more specific" validator.

Thus the provider can throw `UnexpectedTypeException` due to **ambiguous multiple matching validators**, even without a "missing validator". Inspect `validatedBy` lists, generic target types, and inheritance hierarchies. Use concrete target types and avoid registering multiple overloads with ambiguous relationships.

Jakarta Validation requires `ConstraintValidator.isValid(...)` implementations to be thread-safe; providers may cache instances. Thread-safety bugs in custom validator logic are a separate problem from `UnexpectedTypeException` itself.

## 14. When Errors Appear in Spring MVC

In Spring MVC, annotations like `@Valid`, `@Validated`, or constraints placed directly on method parameters can request Bean Validation at appropriate entrypoints.

Example request DTO:

```java
public class CreateOrderRequest {
    @NotBlank
    private String itemCode;

    @NotNull
    @Positive
    private Integer quantity;

    @NotEmpty
    private List<@NotBlank String> itemTags;

    // Constructor/getter/setter or record binding
    // defined as used by the application.
}
```

Above is an **illustrative class**, requiring `java.util.List` and Jakarta annotations. Controller:

```java
@PostMapping("/orders")
public ResponseEntity<Void> create(
        @Valid @RequestBody CreateOrderRequest request) {
    return ResponseEntity.accepted().build();
}
```

This is an **illustrative method** in a Spring MVC controller, requiring framework imports and a response policy. Once the framework deserializes the request into an object and triggers the validator:

- `quantity = 0` with `@Positive`: **invalid value**, produces a Bean Validation violation; MVC typically turns this into a client error like HTTP 400 per exception-handling configuration.
- `quantity = 5` while code declares `@NotBlank Integer quantity`: **mistyped constraint metadata**; the provider throws `UnexpectedTypeException`, typically surfacing as a server-side configuration bug. This is not "invalid form input" that can be fixed by changing user-facing validation messages.
- JSON sending `"quantity": "abc"` for `Integer`: Jackson can fail during type conversion before Bean Validation runs; that is a deserialization/HTTP message conversion error.
- If `@Valid`/supported entrypoint is missing, constraints may not run at all; seeing no exception **does not prove** types are declared properly.

In modern MVC, validating an object argument can raise `MethodArgumentNotValidException`; if method-level validation is triggered by constraints directly on method parameters, Spring may raise `HandlerMethodValidationException`. `UnexpectedTypeException` is an exception from **provider constraint resolution**, which must be treated as a technical bug and fixed in code. Do not treat it as an ordinary `BindingResult.hasErrors()` branch.

## 15. Diagnostic Workflow for HV000030/UnexpectedTypeException

When logs show a message like `HV000030` or class name `UnexpectedTypeException`, follow these steps in order:

1. **Read the exact annotation, type, and property path** in the message. For example, `NotBlank`, `Integer`, `quantity` is enough to pinpoint it.
2. **Open the Java declaration**, not just SQL schemas or JSON payloads. The field/getter/record component type dictates validator candidates. For an enum with `@Enumerated(EnumType.STRING)`, the Java type is still the enum.
3. **Cross-check the supported types table** in the Jakarta Validation spec or your exact provider/version Javadoc. Distinguish `@Size` vs. `@Min`, `@NotBlank` vs. `@NotEmpty`, `@Past` vs. String/epoch.
4. **Check whether the constraint is on the container or element**: `@NotBlank List<String>` is wrong; `List<@NotBlank String>` is right when validating each string.
5. **Check groups and cascade paths** if the error only triggers in one flow: the active validation group and `@Valid` on nested objects decide whether a field is inspected.
6. **Inspect custom `@Constraint(validatedBy=...)`**: does the validator have the right generic target type, or are multiple candidates equally specific?
7. **Check dependencies/integration**: `jakarta` vs. `javax`, provider version, Spring-managed services, XML mappings, or custom factory configurations overriding validators.
8. **Add a direct `validator.validate(bean)` test** for each DTO/group set so bugs are caught early and reproducibly rather than waiting for production requests.
9. **Fix the model or constraint** rather than catching and ignoring the exception. If a type truly requires special handling, write a custom constraint with a clear contract and test with the right provider.

In Hibernate Validator, `HV000031` typically relates to **multiple matching validators**, whereas `HV000030` relates to **no matching validator**; exact codes are implementation details, so also inspect the Java exception class and stack trace.

## 16. Testing to Prevent Regressions

### Testing Invalid Values with Valid Types

```java
var violations = validator.validate(
        new Order("   ", List.of(), 0,
                  "A", LocalDate.of(2000, 1, 1)));

assertEquals(5, violations.size());
```

This is an **illustrative JUnit 5 snippet**, based on the `Order` class from the earlier Java example and an injected `validator`. Import `org.junit.jupiter.api.Assertions.assertEquals` or use a static import. Assert specific property paths so message/locale changes do not make tests brittle.

### Testing That Wrong Types Expose Technical Errors

```java
assertThrows(UnexpectedTypeException.class,
        () -> validator.validate(new WrongType()));
```

Requires JUnit 5 and the `WrongType` class shown earlier. This test helps demonstrate the root cause in learning code. **For production code, fix `WrongType`'s declaration so real tests assert that `UnexpectedTypeException` no longer occurs**; do not keep a permanent test expecting a technical configuration failure.

### Spring Integration Tests

- Inject `jakarta.validation.Validator` from the Spring ApplicationContext to test the exact provider used by the app.
- For endpoints, use `MockMvc` with valid and invalid DTOs to distinguish binding errors, constraint violations, and configuration errors.
- For `@Validated` services, invoke through the Spring proxy when method validation is used.
- For collections/nested models, test at least one invalid element and verify `@Valid`/container element constraints are active.
- For custom constraints, purposefully test each supported type and an unsupported type; watch out for two validators colliding on shared interfaces.
- For temporal constraints, test alongside `ClockProvider`/timezone when cases depend on current time.

To catch errors before live traffic hits them, you can add an integration test scanning key DTOs/entrypoints and invoking validation on sample data. Do not assume starting the ApplicationContext validates every annotation: many providers resolve validators **lazily when a constraint type is first used**.

## 17. Quick Selection Rules

| What You Need to Validate | Appropriate Java Type | Annotations to Consider |
| --- | --- | --- |
| Required username, not spaces-only | `String` | `@NotBlank` + `@Size` |
| Email with content and valid structure | `String` | `@NotBlank` + `@Email` |
| List with at least one element | `List<T>` | `@NotEmpty` |
| List of names where each name is valid | `List<String>` | `@NotEmpty List<@NotBlank String>` |
| Positive integer item quantity | `Integer` | `@NotNull` + `@Positive` |
| Score from 0 to 100 | `Integer` or `BigDecimal` | `@Min(0)` + `@Max(100)` on supported types |
| Non-negative money, max 2 decimal places | `BigDecimal` | `@DecimalMin("0.00")` + `@Digits` |
| Delivery date after today | `LocalDate` | `@NotNull` + `@Future` |
| Ensure an enum status is provided | `Status` | `@NotNull` |
| String matching a regular expression | `String`/`CharSequence` | `@Pattern` |
| Child properties needing deeper validation | JavaBean or nested collection | `@Valid` + constraints on child fields |

**Ask yourself before code review:** "What is the declared type where the annotation is placed? Does Jakarta Validation have a validator for this annotation/type pair? Does the annotation check null or content? Is there an entrypoint actually running validation?"

## 18. Self-Check Questions

**1. Why does `@NotBlank Integer age` compile yet fail at runtime?**  
Java permits annotations on fields, but Bean Validation must resolve a `ConstraintValidator` with a matching supported type; `Integer` is not a `CharSequence`.

**2. Does `@Size(min=1) List<String> names` check that `names.get(0)` is non-empty?**  
No. It checks the list's element count. Use `List<@NotBlank String>` to check each string, paired with `@NotEmpty` if the list must have at least one element.

**3. Is `@Size(max=5) Integer code` equivalent to a numeric code of at most 5 digits?**  
No. `@Size` does not apply to `Integer` per the standard. Pick the right type, range, or string code format.

**4. Is `@Min(1) Double price` portable?**  
No, not under `@Min`'s mandatory supported types in Jakarta Validation; a provider may extend it. For decimals requiring business precision, use `BigDecimal` and `@DecimalMin`.

**5. Is `@Positive Double percent` portable?**  
Yes, `@Positive` explicitly supports `float`/`double` per spec, though you must understand floating-point representation.

**6. When `validator.validate(bean)` returns 3 `ConstraintViolation`s, is that an `UnexpectedTypeException`?**  
No. The provider resolved appropriate validators and detected failing values. `UnexpectedTypeException` means no unique validator could be resolved.

**7. Does `@Pattern` on an enum work because JPA stores enums as text?**  
No. Bean Validation inspects the Java type of the field, not how JPA encodes it into the database.

**8. Why can the same DTO work on one provider yet fail on another?**  
A provider may support extra types beyond the standard set. For portability, stick to Jakarta Validation's supported types.

**9. Can you fix the error by `catch (UnexpectedTypeException)` and returning a user error?**  
Do not treat that as a solution. This is typically a declaration/configuration bug that should be fixed in code and caught by tests.

**Remember:** *Invalid value → constraint violation; mistyped or ambiguous constraint declaration → UnexpectedTypeException*. Always choose **annotations according to the Java type** before validating real data.

## References

- Jakarta Validation 3.1 specification — Built-in Constraint definitions: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html#builtinconstraints
- Jakarta Validation 3.1 specification — ConstraintValidator resolution algorithm: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html
- Jakarta Validation API — UnexpectedTypeException: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/UnexpectedTypeException.html
- Jakarta Validation API — Built-in constraints package: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/constraints/package-summary.html
- Hibernate Validator — Reference Guide and documentation: https://hibernate.org/validator/documentation/
- Spring Framework Reference — Java Bean Validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring Framework Reference — Spring MVC Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
