
# `@Digits`: Limiting Integer and Fractional Digits in Bean Validation

## 1. Problem and Meaning of `@Digits`

Suppose a system has an `amount` field for money with the rule **at most 4 integer digits** and **at most 2 fractional digits**. Values like `1234.56`, `0.5`, and `-12.34` satisfy the digit count, whereas `12345.67` has too many integer digits and `12.345` has too many fractional digits.

Jakarta Bean Validation provides the standard constraint:

```java
import jakarta.validation.constraints.Digits;

@Digits(integer = 4, fraction = 2)
private BigDecimal amount;
```

It requires the value to be a number with **no more than** `integer` digits in the integral part and **no more than** `fraction` digits in the fractional part. Both attributes are required when declaring the annotation and must be non-negative. This constraint resides in `jakarta.validation.constraints.Digits`; Spring Framework 6+/Spring Boot 3+ uses the `jakarta.validation.*` namespace.

Distinctions to make right away:

- `@Digits(integer = 4, fraction = 2)` defines **maximum digit limits**, not that the value must have exactly 4 integer digits or exactly 2 fractional digits.
- It **does not auto-round**, truncate decimals, convert strings to numbers, or require positive values.
- A `null` value is considered **valid under `@Digits` alone**. To require input, combine with `@NotNull`.
- It does not independently restrict business value ranges. To require "non-negative", "0 to 500", or "greater than 0", combine `@PositiveOrZero`, `@DecimalMin`, `@DecimalMax`, or corresponding rules.

`@Digits` is especially useful for prices, rates, weights, quantities with fractional parts, and decimal values stored in columns with fixed precision/scale.

## 2. Understanding `integer` and `fraction` Accurately

### 2.1. Both Counts Are Maximum Limits

```java
@Digits(integer = 4, fraction = 2)
BigDecimal amount;
```

The pattern above accepts at most 4 integer digits and 2 digits after the decimal point. The illustration table uses `BigDecimal` created from strings with the exact representation shown:

| Input Value | Integer Digits | Fractional Digits | Result |
| --- | ---: | ---: | --- |
| `1234.56` | 4 | 2 | Valid |
| `1234` | 4 | 0 | Valid |
| `0.5` | Within limit | 1 | Valid |
| `-9999.99` | 4 | 2 | Valid: minus sign is not counted as a digit |
| `12345.67` | 5 | 2 | **Invalid**: exceeds `integer` |
| `12.345` | 2 | 3 | **Invalid**: exceeds `fraction` |
| `10000.00` | 5 | 2 | **Invalid**: exceeds `integer` |
| `1.230` | 1 | 3 | **Invalid**: `BigDecimal` has `scale = 3` |
| `1.23` | 1 | 2 | Valid |
| `null` | Not applicable | Not applicable | Valid under `@Digits` alone |

The table uses a dot per Java decimal syntax; thousand separators do not appear. For `0.x` values, a provider may compute integer digit count via `BigDecimal.precision() - scale()`, which can yield a non-positive number for very small representations. The key rule for `integer = 4` is **at most 4 integer digits**; do not confuse displayed character count with the provider's algorithm.

### 2.2. Different from "Exactly Two Decimal Places"

`@Digits(integer = 4, fraction = 2)` still accepts `5`, `5.1`, and `5.12`. It **does not require** `5` to be written as `5.00`. If the UI should always display two decimal places, that is a formatter's job; if data must be stored with a fixed scale, that is a normalization decision in the business/persistence layer.

The case `@Digits(integer = 6, fraction = 0)` allows numbers **with no fractional digits** in their validated representation. It does not mean "positive integer", because negative values like `-123` are still accepted.

### 2.3. `null` and Required Input Conditions

```java
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotNull;

public class PaymentInput {

    @NotNull
    @Digits(integer = 4, fraction = 2)
    private BigDecimal amount;
}
```

This snippet illustrates a bean field, not a standalone Java application. If `amount == null`, `@Digits` skips it and `@NotNull` creates a violation. This is a common design principle across Jakarta constraints: checking *absence of value* is separated from checking *valid format/bounds when present*.

If `amount` must be positive and not exceed 5000, add range conditions. Even though `@Digits(integer = 4, fraction = 2)` blocks `10000.00`, it still accepts `9999.99` and `-9999.99`, so it is insufficient to express "0 ≤ amount ≤ 5000".

## 3. `BigDecimal`: Precision, Scale, and Trailing Zeros

For decimal numbers requiring accuracy, prefer `BigDecimal`. Avoid constructing with `new BigDecimal(0.1)` because `double` has an approximate binary representation; use strings or `BigDecimal.valueOf(...)` appropriately.

`BigDecimal` has two properties closely related to `@Digits`:

- `precision()`: number of digits in the **unscaled value** according to `BigDecimal` rules.
- `scale()`: number of digits to the right of the decimal point in ordinary representation if scale is positive; negative scale represents powers of 10.

In Hibernate Validator, when checking `BigDecimal`, determination is typically based on:

```text
integerPartLength  = precision - scale
fractionPartLength = max(scale, 0)
```

Understand that this is a **provider detail**, not a mandatory implementation dictated by Jakarta's annotation signature. For numbers with negative scale like `1E+4`, integer part length is computed from the full numeric value (`10000` has 5 integer digits). Do not replace this with counting characters in `toString()`.

Plain JDK Java 17 example:

```java
import java.math.BigDecimal;

public class BigDecimalMetadata {
    public static void main(String[] args) {
        for (String raw : new String[]{"1.23", "1.230", "1234.56"}) {
            BigDecimal value = new BigDecimal(raw);
            System.out.printf("%s: precision=%d, scale=%d%n",
                    raw, value.precision(), value.scale());
        }
    }
}
```

Run with:

```bash
javac BigDecimalMetadata.java
java BigDecimalMetadata
```

**Exact standard output:**

```text
1.23: precision=3, scale=2
1.230: precision=4, scale=3
1234.56: precision=6, scale=2
```

The following two objects have the same **numeric value** under `compareTo`, yet different scales:

```java
new BigDecimal("1.230").compareTo(new BigDecimal("1.23")) == 0
```

With `fraction = 2`, Hibernate Validator will reject `new BigDecimal("1.230")` because **scale equals 3**. This is an important difference between validating a decimal value represented as `BigDecimal` and asking how few digits the number could be reduced to.

If business rules permit stripping insignificant trailing zeros, you can **explicitly normalize** with:

```java
BigDecimal normalized =
        new BigDecimal("1.230").stripTrailingZeros();
// normalized has value 1.23 and scale = 2
```

Do not silently normalize if the data records intentional precision, e.g., measurements `1.230` and `1.23` may carry different meanings. Likewise, do not call `setScale(2, RoundingMode.HALF_UP)` merely to pass validation: that **rounds the data**. If business rules require rounding, define the policy and timing explicitly before validation/saving.

## 4. Supported Data Types

According to the Jakarta Validation API, `@Digits` supports these standard types:

- `BigDecimal`
- `BigInteger`
- `CharSequence` (commonly `String`)
- `byte`, `short`, `int`, `long` and their wrappers (`Byte`, `Short`, `Integer`, `Long`)

Hibernate Validator also supports certain other `Number` types as a **provider-specific extension**. Do not assume all Jakarta implementations support `float`/`double` the same way; binary floating-point numbers also suffer from conversion inaccuracies when mapped to decimal form.

### `BigInteger` and Integral Types

```java
@Digits(integer = 6, fraction = 0)
private Long accountSequence;
```

For integers, there is no fractional part. `fraction = 0` states the intent clearly; `integer = 6` blocks integer values with more than 6 digits. Using `@Digits` does not replace range checks like `@Min`/`@Max` or Java data type limits.

### With `String`, Do Not Confuse Numeric Checks with String Length

```java
@Digits(integer = 4, fraction = 2)
private String enteredAmount;
```

With a provider like Hibernate Validator, the string must first be parseable into a valid numeric value before checking integer/fractional parts. For instance, `"abc"` is invalid. However, `@Digits` **does not simply count character length**, is not a regex enforcing one exact writing style, and does not guarantee preserving leading zeros. `"000123.45"` may be interpreted as `123.45` depending on how the provider parses the string, rather than being evaluated as 6 integer characters.

If you need exact textual formatting such as "up to four digits before the dot, up to two after, no leading zeros, no exponent notation", consider `@Pattern` on the `String` field **alongside** numeric/business checks when appropriate. Do not use `@Size` instead of `@Digits`: `@Size(max = 6)` checks total string/collection length—including minus signs, separators, and other characters—not the two parts of a number.

### `Locale` and User Formatting

`@Digits` is not a `Locale`-aware formatter. In Spring MVC, if a user enters `"1.234,56"` in a UI using decimal commas, the input must be parsed properly via **data binding/formatting** before `@Digits` evaluates the `BigDecimal` object. A string-to-number conversion error may occur before validation. For JSON numeric payloads, clients should send numbers matching JSON syntax and a clear API contract; do not treat UI decimal commas as JSON numeric syntax.

## 5. Comparison with Commonly Used Constraints

| Constraint | Question It Answers | Example |
| --- | --- | --- |
| `@Digits(integer=4,fraction=2)` | At most how many integer/fractional digits? | `1234.56` passes, `12345.67` fails |
| `@NotNull` | Is a value required? | `null` is rejected |
| `@Positive`, `@PositiveOrZero` | Is the value positive/non-negative? | `-1.00` is rejected |
| `@DecimalMin("0.00")` | Is it >= a threshold? | Blocks negative numbers by value |
| `@DecimalMax("5000.00")` | Is it <= a threshold? | Blocks `5000.01` |
| `@Size(min=,max=)` | What is the string/collection/array length or size? | Does not replace decimal digit counts |
| `@Pattern(regexp=...)` | Does the string match a character pattern? | Enforces dot and exact formatting |
| `@Column(precision=6,scale=2)` | Decimal schema hint for JPA/DB | Persistence-related, does not replace Bean Validation |

A practical rule can combine them as follows:

```java
import java.math.BigDecimal;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotNull;

public class PriceInput {

    @NotNull(message = "amount.required")
    @Digits(integer = 4, fraction = 2, message = "amount.digits")
    @DecimalMin(value = "0.00", message = "amount.nonNegative")
    @DecimalMax(value = "5000.00", message = "amount.tooLarge")
    private BigDecimal amount;
}
```

This is an illustrative field; add constructors/getters/setters or appropriate binding when integrating into an MVC app. Each constraint carries a distinct responsibility. A value like `5000.001` can violate both `@Digits` and `@DecimalMax`; Bean Validation **does not guarantee returning only one error or a fixed error order**. The application needs a display strategy if you do not want multiple messages on the same field.

## 6. Runnable Java 17 Example: Testing Boundary Cases

The following example creates a Bean Validation provider and runs `@Digits` on an `AmountForm` object. It clearly prints **PASS** or the **violated** constraint names; constraint names are sorted so stdout does not depend on `Set<ConstraintViolation<?>>` iteration order.

Using a standalone Gradle project:

```text
digits-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/DigitsDemo.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'digits-demo'
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
    implementation 'org.hibernate.validator:hibernate-validator:8.0.6.Final'
    implementation 'org.glassfish.expressly:expressly:5.0.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'DigitsDemo'
}
```

Hibernate Validator 8 is the Jakarta Bean Validation provider using the `jakarta.validation.*` namespace. `expressly` supplies the Jakarta Expression Language implementation required for full provider message interpolation. In a Spring Boot project, typically add `spring-boot-starter-validation` and let Spring Boot's BOM manage versions instead of pinning two standalone dependencies as in this example.

**`src/main/java/DigitsDemo.java`:**

```java
import java.math.BigDecimal;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotNull;

public class DigitsDemo {

    public static final class AmountForm {

        @NotNull
        @Digits(integer = 4, fraction = 2)
        private final BigDecimal amount;

        public AmountForm(BigDecimal amount) {
            this.amount = amount;
        }

        public BigDecimal getAmount() {
            return amount;
        }
    }

    private static String describe(
            Set<ConstraintViolation<AmountForm>> violations) {

        if (violations.isEmpty()) {
            return "PASS";
        }

        return violations.stream()
                .map(v -> v.getPropertyPath() + ":"
                        + v.getConstraintDescriptor()
                            .getAnnotation()
                            .annotationType()
                            .getSimpleName())
                .sorted()
                .collect(Collectors.joining(","));
    }

    public static void main(String[] args) {
        String[] inputs = {
            "1234.56",
            "1234",
            "-9999.99",
            "12345.67",
            "12.345",
            "1.230",
            "1.23",
            null
        };

        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();

            for (String raw : inputs) {
                BigDecimal amount =
                        raw == null ? null : new BigDecimal(raw);

                AmountForm form = new AmountForm(amount);

                Set<ConstraintViolation<AmountForm>> violations =
                        validator.validate(form);

                String label = raw == null ? "<null>" : raw;
                System.out.println(label + " -> " + describe(violations));
            }
        }
    }
}
```

Using a locally installed Gradle:

```bash
gradle run --quiet
```

Or `./gradlew run --quiet` if using Gradle Wrapper on Linux/macOS; on Windows use `gradlew.bat run --quiet`.

**Expected standard output:**

```text
1234.56 -> PASS
1234 -> PASS
-9999.99 -> PASS
12345.67 -> amount:Digits
12.345 -> amount:Digits
1.230 -> amount:Digits
1.23 -> PASS
<null> -> amount:NotNull
```

Why are those lines right?

1. `1234.56` fits exactly within 4 integer digits and 2 fractional digits.
2. `1234` has no fractional part, and still passes because `fraction` is *at most* 2.
3. `-9999.99` passes: the minus sign does not count toward digit count; to disallow negatives, add `@DecimalMin("0")` or `@PositiveOrZero`.
4. `12345.67` has 5 integer digits, exceeding `integer = 4`.
5. `12.345` has 3 fractional digits, exceeding `fraction = 2`.
6. `1.230` is constructed via `new BigDecimal("1.230")`, has `scale = 3`, and is rejected even though the last digit is 0.
7. `null` **is accepted by `@Digits`** yet rejected by `@NotNull`, so only `amount:NotNull` appears.
8. The violation set does not guarantee order; the example sorts strings before printing for repeatable output.

The program validates objects constructed from valid numeric strings. It **does not** illustrate malformed inputs like `"12,34"` or `"abc"` when the target field is `BigDecimal`, because `new BigDecimal(raw)` throws `NumberFormatException` *before* Bean Validation runs. That is precisely why conversion/parsing must be separated from validation.

## 7. Applying in Spring MVC and Spring Boot

### 7.1. Defining the DTO

With Spring Boot 3+/Spring Framework 6+, an illustrative DTO for JSON requests:

```java
import java.math.BigDecimal;

import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotNull;

public record AmountRequest(
        @NotNull
        @Digits(integer = 4, fraction = 2)
        BigDecimal amount
) {}
```

`@Digits` is placed on the record component, allowing the provider to apply the constraint to the field/accessor per supported targets. This example uses JSON numbers with `BigDecimal`; there is no user Locale string-parsing step.

### 7.2. Controller Using `@Valid`

The following is an **integration illustration**, requiring a Spring MVC application and corresponding imports:

```java
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AmountController {

    @PostMapping("/amounts")
    public ResponseEntity<String> create(
            @Valid @RequestBody AmountRequest input,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest()
                    .body("invalid amount");
        }

        return ResponseEntity.ok("accepted");
    }
}
```

`BindingResult` immediately follows the validated parameter so the controller can handle Bean Validation errors per Spring MVC's mechanism. Without `BindingResult`, request object validation errors typically enter exception handling (`MethodArgumentNotValidException` in standard object validation), while method-level constraints or other validation setups may raise different exception types.

JSON body example:

```json
{"amount": 1234.56}
```

passes `@Digits(integer=4,fraction=2)` and receives `"accepted"` in the illustrative controller. Body:

```json
{"amount": 12345.67}
```

violates `@Digits` and the controller returns HTTP 400 with `"invalid amount"`. Malformed JSON or values unconvertible to `BigDecimal` may be rejected **before validation** via Jackson/`HttpMessageConverter` and do not necessarily enter `BindingResult` as a `@Digits` violation.

In production APIs, return a clear error structure containing field, error code, and properly interpolated message; do not expose sensitive values in logs/responses.

### 7.3. Form Input and `Locale`

With `@ModelAttribute`, Spring binds text strings from forms to numeric types; the formatter/conversion service decides how request separators are interpreted. If a form uses German locale and receives `"1.234,56"`, the parsing layer must interpret grouping dots and decimal commas correctly to produce `BigDecimal("1234.56")` before `@Digits` runs.

Do not rely on `@Digits` to understand `Locale` on its own; it does **not** replace `@NumberFormat`, `Formatter<BigDecimal>`, or locale resolver configuration. When input is treated as a **String** and validated directly with `@Digits`, the provider may require standard `BigDecimal` numeric syntax rather than accepting every localized notation.

## 8. Relationship with Databases: Precision and Scale

In SQL schemas, a `DECIMAL(p, s)` column typically has:

- `p` (*precision*): maximum total number of digits.
- `s` (*scale*): number of digits in the fractional part.

From the requirement **at most 4 integer digits + 2 fractional digits**, a common mapping is:

```java
@Digits(integer = 4, fraction = 2)
@Column(precision = 6, scale = 2)
private BigDecimal amount;
```

This is a JPA illustration (`jakarta.persistence.Column`), not a complete Entity. Normally, `DECIMAL(6,2)` holds up to 6 digits with 2 after the decimal point, corresponding to at most 4 integer digits. However:

1. `@Digits` is an **application check**; `@Column` is ORM schema mapping metadata. They do not replace one another.
2. Hibernate ORM can use `@Digits` when generating DDL/schema metadata in some modes, though results depend on provider/configuration; **do not assume the annotation alone is enough to create the right column**. Verify the actual SQL migrations.
3. Different database engines have different rules for rounding, rejecting, or converting numbers exceeding scale. The database must enforce consistency even if requests bypass the web tier.
4. For financial data, you must also decide currency units, sign limits, rounding modes, conversion policies, and transactions. `@Digits` only checks allowed digit counts.

Do not confuse the simple formula `p = integer + fraction` with `@Digits` persisting numbers or handling overflow on its own. The constraint serves as a pre-check; schema and business logic still need consistent design.

## 9. Common Mistakes

1. **Thinking `fraction=2` requires two digits.** It is an upper limit; `12` and `12.3` still pass.
2. **Thinking `@Digits` rounds numbers.** It only reports violations; rounding requires explicit business rules.
3. **Using `double` for money and expecting fractional digits to stay exact.** Use `BigDecimal` constructed from strings or reliable decimal sources.
4. **Overlooking `BigDecimal.scale()`.** `1.230` has scale 3 and can be rejected with `fraction = 2`; `1.23` has scale 2.
5. **Thinking `@Digits` forbids negative numbers.** The minus sign does not increase digit count; add `@DecimalMin` or `@PositiveOrZero` if needed.
6. **Thinking `null` is invalid.** `@Digits` alone allows `null`; add `@NotNull` for required fields.
7. **Using `@Size(max = 6)` for decimal numbers.** `@Size` measures data/string length, not separate integer and fractional digit counts.
8. **Counting raw input characters instead of significant digits.** Leading zeros, plus/minus signs, decimal points, and exponent notation make text length differ from numeric digits; controlling exact typing requires dedicated format validation.
9. **Failing to separate conversion and validation.** A string `"1,23"` can fail right when parsing `BigDecimal`; `@Digits` does not handle locales directly.
10. **Validating only at the API and ignoring the DB.** Other apps can write directly; the schema still needs matching precision/scale and constraints.
11. **Assuming providers have identical supported types.** Jakarta defines standard types; Hibernate Validator adds extra types per implementation. If relying on extensions, document and test your specific provider.
12. **Skipping tests for zero and negative numbers.** Values like `0.00`, `-0.01`, and `10000.00` must be covered according to business policy.
13. **Assuming validation errors always have a deterministic first element.** `Set<ConstraintViolation<?>>` is unordered; sort errors separately for display.
14. **Confusing `javax.validation.*` with `jakarta.validation.*`.** Spring Framework 6+/Boot 3+ uses the Jakarta namespace; migrating from older versions requires updating imports and providers.

## 10. Checklist and Practice Questions

### Minimum Test Matrix for `@Digits(integer = 4, fraction = 2)`

| Test | Expected |
| --- | --- |
| `new BigDecimal("0")` | Pass |
| `new BigDecimal("0.00")` | Pass |
| `new BigDecimal("1234.56")` | Pass |
| `new BigDecimal("12345.67")` | Violates `integer` |
| `new BigDecimal("1234.567")` | Violates `fraction` |
| `new BigDecimal("-9999.99")` | Passes `@Digits`; may violate separate non-negative rule |
| `new BigDecimal("1.230")` | Violates `fraction=2` in Hibernate Validator |
| `null` with `@Digits` only | Pass |
| `null` with `@NotNull` added | Violates `@NotNull` |

Test all three paths: **plain Java Bean Validation**, **Spring MVC form binding**, and **JSON deserialization** if the system uses them. JSON tests differ from form string tests because input conversion differs.

### Self-Test Answers

- What does `@Digits(integer=5, fraction=2)` mean? **At most 5 integer digits and 2 fractional digits; it does not require those exact counts.**
- Does `@Digits(integer=4, fraction=2)` block `-9999.99`? **No**; a separate range constraint is needed.
- Why can `BigDecimal("1.230")` fail while `BigDecimal("1.23")` passes? **Their scales are 3 and 2 respectively**.
- Why combine with `@NotNull`? **Because `@Digits` treats null as valid**.
- If you want 2 digits after the decimal point in the UI, what do you choose? **A formatter/`@NumberFormat` or display logic**, not `@Digits` to pad zeros.
- If the DB must store only two decimal places, is a schema definition needed? **Yes**: use an appropriate decimal column/type and migration, along with a scale-handling policy.
- If a user enters `1.234,56` in German locale, does `@Digits` automatically convert it to `1234.56`? **No**; Spring binding/conversion must parse it first.

## 11. References

- [Jakarta Validation 3.1 — `@Digits` Javadoc](https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/constraints/Digits.html): `integer`/`fraction` parameters, supported types, null validity.
- [Jakarta Bean Validation 3.0 specification — `@Digits`](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html): standard constraint definition.
- [Hibernate Validator 8 — Reference Guide](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/): extended types, `@Digits` description, and impact on schema metadata.
- [Java SE 17 — `BigDecimal` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): `precision`, `scale`, `stripTrailingZeros`, `compareTo`.
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): provider/adapter, Spring `DataBinder`, validation errors.
- [Spring Framework — MVC Controller Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): `@Valid`, `BindingResult`, and error-handling flows.

**Key takeaway:** `@Digits` checks upper limits on **integer digits** and **fractional digits** of a value based on Java type and provider; it does not round, constrain sign, or reject null. Combine it with `BigDecimal`, range constraints, and database schemas when building Spring applications.
