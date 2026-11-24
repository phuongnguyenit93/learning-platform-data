# Handling Empty Strings, Negative Signs, and Out-of-Range Numbers in Spring Number Conversion

Numeric data from forms or APIs typically arrives as strings. Users may send `"125"`, `"+125"`, `"-8"`, `""`, `"   "`, or a huge string such as `"999999999999999999999"`. These cases are distinct: valid numbers, omitted values, syntax errors, Java type overflows, or syntactically valid values that violate business rules.

When Spring binds a string to a numeric property, the **converter performs type conversion**, while validation checks constraints such as positivity or allowed ranges. You must separate blank/null handling, sign syntax, target type bounds, and business bounds.

## 1. Input classification

| Input | Classification | Handling Strategy |
| --- | --- | --- |
| `"125"` | Valid integer | `Integer 125` if within range |
| `"0"` | Zero | Allowed or forbidden per business rules |
| `"+125"` | Leading plus sign | Accepted by `Integer.parseInt` |
| `"-8"` | Syntactically valid negative | Representable by `int`; business rules decide |
| `""` | Empty string | `null` or error per contract |
| `"   "` | Whitespace only | Normalize then decide |
| `" 125 "` | Leading/trailing whitespace | Direct `parseInt` does not trim |
| `"12.5"` | Decimal number | Not an integer for `parseInt` |
| `"1,250"` | Grouping separator | Requires explicit locale/formatter |
| `"--5"` or `"+"` | Syntax error | Reject |
| `"2147483648"` | Exceeds `int` range | `NumberFormatException` |
| `"-2147483649"` | Below `Integer.MIN_VALUE` | `NumberFormatException` |

A negative number is not a parse error simply because it is negative. `Integer.parseInt("-8")` returns `-8`. If a quantity cannot be negative, that is a business rule, not a limitation of `int`.

## 2. Integer.parseInt syntax and type limits

`Integer.parseInt(String)` parses a decimal string into a signed integer. A single ASCII `+` or `-` sign is permitted at the first position.

| String | Result |
| --- | --- |
| `"42"` | `42` |
| `"+42"` | `42` |
| `"-42"` | `-42` |
| `"-0"` | `0` |
| `" 42"` / `"42 "` | `NumberFormatException` |
| `"+ 42"` / `"++42"` | `NumberFormatException` |
| `""` | `NumberFormatException` |
| `"42.0"` / `"4_200"` | `NumberFormatException` |

`parseInt` **does not automatically trim whitespace**. If the contract permits leading/trailing whitespace, code must normalize before parsing. Do not silently trim if whitespace carries meaning in the data.

Range of `int`:

```java
Integer.MIN_VALUE == -2_147_483_648
Integer.MAX_VALUE ==  2_147_483_647
```

Both bounds are valid. Values outside the range cause overflow:

```java
Integer.parseInt("2147483647");  // Valid
Integer.parseInt("-2147483648"); // Valid
Integer.parseInt("2147483648");  // NumberFormatException
Integer.parseInt("-2147483649"); // NumberFormatException
```

Do not use `(int)` casting to handle overflow. If you parse as `long` and cast, out-of-range values silently wrap to different numbers. Check bounds explicitly or use `Math.toIntExact(longValue)`.

## 3. Syntax errors, overflow, and business limits

| Category | Example | Meaning |
| --- | --- | --- |
| Syntax error | `"12x"`, `"--3"` | String does not represent an integer |
| Type overflow | `"2147483648"` for `Integer` | Cannot be represented in the target type |
| Business violation | `"-3"` when quantity must be non-negative; `"5001"` when max is 5000 | Parseable but not accepted |

`-3` is a valid integer in Java. However, a `quantity` property may disallow negatives. Enforce this with a custom converter, Bean Validation such as `@PositiveOrZero`, or an application service depending on the rule type.

The converter ensures a valid target representation/type. The validator enforces data constraints. The service enforces conditions depending on system state such as inventory, permissions, or quotas.

## 4. Policies for empty strings

With wrapper `Integer`, an application can represent an unprovided value as `null`. With primitive `int`, `null` cannot be assigned; the default value is `0`, yet empty input should not be assumed to mean 0.

| Policy | `""` / `"   "` | Field Omitted |
| --- | --- | --- |
| Optional → null | Trim then blank becomes `null` | Setter does not run; current value may stay intact |
| Required → error | Blank is rejected or validation fails | Checked under required contract |
| Default value | Replace blank with a defined default | Separate rule when key is absent |

**Do not equate an empty string with 0.** `""` has no digits; `"0"` is a valid integer. If blank input should become 0, define an explicit default policy.

Also distinguish **field not sent** from **field sent as blank**. When a key is absent, the binder may skip calling the setter. When a key is present and the converter returns `null`, the setter may receive `null`. In PATCH requests, "leave unchanged" differs from "clear value."

## 5. A Converter with blank, negative-sign, and range policies

The converter below turns blanks into `null` for optional fields; trims leading/trailing whitespace; allows `+` per Java's parser; rejects negatives when configured; parses within `int` range; and checks business range after parsing.

```java
public final class BoundedIntegerConverter
        implements Converter<String, Integer> {

    private final int minimum;
    private final int maximum;
    private final boolean allowNegative;

    public BoundedIntegerConverter(
            int minimum, int maximum, boolean allowNegative) {
        if (minimum > maximum) {
            throw new IllegalArgumentException("minimum > maximum");
        }
        this.minimum = minimum;
        this.maximum = maximum;
        this.allowNegative = allowNegative;
    }

    @Override
    public Integer convert(String source) {
        if (source == null) {
            return null;
        }

        String text = source.trim();
        if (text.isEmpty()) {
            return null;
        }

        final int value;
        try {
            value = Integer.parseInt(text);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    "Value is not a valid 32-bit decimal integer", ex);
        }

        if (!allowNegative && value < 0) {
            throw new IllegalArgumentException(
                    "Negative values are not allowed");
        }

        if (value < minimum || value > maximum) {
            throw new IllegalArgumentException(
                    "Value is outside the permitted range");
        }

        return value;
    }
}
```

This is a converter for a specific policy, not a universal rule for every `String → Integer`. Quantities may set min to 0; temperatures may allow negatives. If a field is required, do not rely on the converter returning `null`; add `@NotNull` or an appropriate requiredness contract.

Check business range after parsing to distinguish target-type overflow from business limits: `"5001"` may be a valid `int` that exceeds a 5000 quota; `"2147483648"` already overflows `int` so parsing fails before quota is even checked.

## 6. Runnable Java 17+ example with Spring DataBinder

This example uses Spring Framework Core with no Spring Boot or HTTP server. We register a custom `Converter<String, Integer>` on `DefaultFormattingConversionService`, then bind into a DTO with an `Integer` property.

### Project structure

```text
number-input-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/NumberInputDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'number-input-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
}

application {
    mainClass = 'example.NumberInputDemo'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

Requires JDK 17+ and a compatible Gradle version, with Maven Central access to download dependencies on the first run.

### Complete Java code

**`src/main/java/example/NumberInputDemo.java`**

```java
package example;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.core.convert.converter.Converter;
import org.springframework.core.convert.support.ConfigurableConversionService;
import org.springframework.format.support.DefaultFormattingConversionService;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;

public class NumberInputDemo {

    public static final class BoundedIntegerConverter
            implements Converter<String, Integer> {

        private final int minimum;
        private final int maximum;
        private final boolean allowNegative;

        public BoundedIntegerConverter(
                int minimum, int maximum, boolean allowNegative) {
            if (minimum > maximum) {
                throw new IllegalArgumentException("minimum > maximum");
            }
            this.minimum = minimum;
            this.maximum = maximum;
            this.allowNegative = allowNegative;
        }

        @Override
        public Integer convert(String source) {
            if (source == null) {
                return null;
            }
            String text = source.trim();
            if (text.isEmpty()) {
                return null;
            }

            final int value;
            try {
                value = Integer.parseInt(text);
            } catch (NumberFormatException ex) {
                throw new IllegalArgumentException(
                        "Value is not a valid 32-bit decimal integer", ex);
            }

            if (!allowNegative && value < 0) {
                throw new IllegalArgumentException(
                        "Negative values are not allowed");
            }
            if (value < minimum || value > maximum) {
                throw new IllegalArgumentException(
                        "Value is outside the permitted range");
            }
            return value;
        }
    }

    public static final class QuantityForm {
        private Integer quantity;

        public Integer getQuantity() {
            return quantity;
        }

        public void setQuantity(Integer quantity) {
            this.quantity = quantity;
        }
    }

    private static String label(String input) {
        return input == null ? "<null>" : "[" + input + "]";
    }

    private static void printDirect(
            BoundedIntegerConverter converter, String input) {
        try {
            System.out.println(label(input) + " -> " + converter.convert(input));
        } catch (IllegalArgumentException ex) {
            System.out.println(label(input) + " -> ERROR: " + ex.getMessage());
        }
    }

    private static void bindAndPrint(
            ConfigurableConversionService service, String input) {
        QuantityForm form = new QuantityForm();
        DataBinder binder = new DataBinder(form, "quantityForm");
        binder.setConversionService(service);

        MutablePropertyValues values = new MutablePropertyValues();
        values.add("quantity", input);
        binder.bind(values);

        FieldError error =
                binder.getBindingResult().getFieldError("quantity");
        System.out.println("binding " + label(input)
                + " -> value=" + form.getQuantity()
                + "; error=" + (error != null)
                + (error == null ? "" : "; code=" + error.getCode()));
    }

    public static void main(String[] args) {
        BoundedIntegerConverter converter =
                new BoundedIntegerConverter(0, 1000, false);

        printDirect(converter, " 42 ");
        printDirect(converter, "+42");
        printDirect(converter, "");
        printDirect(converter, "   ");
        printDirect(converter, "-5");
        printDirect(converter, "1001");
        printDirect(converter, "2147483648");
        printDirect(converter, "12x");

        ConfigurableConversionService service =
                new DefaultFormattingConversionService();
        service.addConverter(converter);

        bindAndPrint(service, "18");
        bindAndPrint(service, "-5");
    }
}
```

### Run and expected stdout

```bash
gradle -q run
```

If a Gradle wrapper is present, use `./gradlew -q run` on Linux/macOS or `gradlew.bat -q run` on Windows.

```text
[ 42 ] -> 42
[+42] -> 42
[] -> null
[   ] -> null
[-5] -> ERROR: Negative values are not allowed
[1001] -> ERROR: Value is outside the permitted range
[2147483648] -> ERROR: Value is not a valid 32-bit decimal integer
[12x] -> ERROR: Value is not a valid 32-bit decimal integer
binding [18] -> value=18; error=false
binding [-5] -> value=null; error=true; code=typeMismatch
```

Explanation: `" 42 "` is explicitly trimmed; `"+42"` is syntactically valid; blanks become `null`; `-5` is rejected by policy; `1001` exceeds business range; `2147483648` overflows `int`; `12x` is a syntax error. When routed through `DataBinder`, conversion errors for `quantity` are recorded in `BindingResult`/`FieldError` with the common code `typeMismatch`.

If the DTO requires the field, add `@NotNull` and enable Bean Validation. Do not log raw inputs or exceptions containing sensitive data in production.

## 7. Using Long, BigInteger, or BigDecimal when needed

| Type | Characteristics | When to Use |
| --- | --- | --- |
| `Integer` | 32-bit signed | Small counts with clear bounds |
| `Long` | 64-bit signed | Larger than `int` range yet still bounded |
| `BigInteger` | Arbitrary-precision integer | Very large integers |
| `BigDecimal` | Exact decimal representation | Money and decimals requiring scale control |

`Long.parseLong` widens the range while still having `Long.MIN_VALUE`/`Long.MAX_VALUE`. `BigInteger` represents large integers:

```java
BigInteger value = new BigInteger("999999999999999999999999");
```

Longer numbers consume more CPU and memory. Limit input length before constructing `BigInteger` to prevent resource abuse. Business range checks are still required after parsing.

Never cast `long` to `int` without checking bounds. Use `Math.toIntExact(longValue)` to detect values that cannot be represented exactly.

## 8. Negative numbers are a domain-specific policy

| Case | Can Negative Be Valid? |
| --- | --- |
| Order quantity | Usually no |
| Adjustment/refund entry | Possibly |
| Temperature/altitude | Yes |
| Account balance | Depends on rules |
| Delta/change amount | Can represent increase/decrease |

Do not register a global `String → Integer` converter that bans negatives across the entire application when fields have different semantics. Use converters per target domain type, field-level validation, or business services when rules depend on system state.

## 9. Locale, grouping, and decimal separators

`Integer.parseInt("1,000")` does not treat commas as grouping separators; `"1.000"` is not a valid integer either. For locale-formatted inputs, use `NumberFormat`/`DecimalFormat` or a Spring `Formatter` with an explicit locale.

`1,25` can be a decimal in one locale while commas act as grouping in another. Do not strip all commas before parsing because `"1,2"` could be misinterpreted as `12`. For money or exact decimals, prefer `BigDecimal` over `double`.

## 10. Primitives, wrappers, and missing fields

```java
public class QuantityForm {
    private Integer optionalQuantity;
    private int primitiveQuantity;
}
```

`Integer` can represent `null`, whereas `int` cannot. Choose `Integer` when you must distinguish unprovided input from 0. Choose `int` when a value must exist and a default of 0 is meaningful. Never use 0 as a sentinel when 0 is a valid business value.

When a field is omitted from a request, the binder may not invoke the setter; existing/default values may remain. When the key is present and blank converts to `null`, the setter may receive `null`. This is a critical distinction in updates/PATCH endpoints.

## 11. BindingResult and validation after conversion

With `@ModelAttribute` in Spring MVC, the typical flow is binding/conversion followed by validation when the parameter has `@Valid`/`@Validated` and an appropriate validator.

| Scenario | Error Phase | Typical Outcome |
| --- | --- | --- |
| `quantity=abc` | Conversion | `FieldError` with code `typeMismatch` |
| `quantity=2147483648` into `Integer` | Conversion/overflow | `FieldError` with code `typeMismatch` |
| `quantity=-5` forbidden by converter | Custom conversion policy | Binding error |
| `quantity=-5` parsed, `@PositiveOrZero` present | Validation | Constraint violation |
| Blank becomes `null`, `@NotNull` present | Validation | Constraint violation |
| Field omitted | No conversion run | Existing/default value may stay intact |

`BindingResult` must immediately follow the corresponding `@ModelAttribute` parameter:

```java
@PostMapping("/quantities")
String submit(
        @Valid @ModelAttribute("form") QuantityForm form,
        BindingResult result) {

    if (result.hasErrors()) {
        return "quantities/form";
    }
    quantityService.apply(form);
    return "quantities/success";
}
```

This is an MVC snippet requiring appropriate controller setup, DTO, validator, and views. Do not invoke the business service if binding/validation errors exist. `@RequestBody` JSON goes through an `HttpMessageConverter` (such as Jackson), which does not necessarily behave identically to `@ModelAttribute`.

## 12. Common mistakes

| Mistake | Cause | Fix |
| --- | --- | --- |
| `" 42 "` is rejected | `parseInt` does not trim | Normalize per contract |
| Blank turns into 0 | Unclear default policy | Distinguish `null`, empty, and `"0"` |
| Negatives rejected app-wide | Overly broad converter policy | Scope rules per domain/field |
| Large values wrap after cast | Unchecked `long` to `int` cast | Use `Math.toIntExact` or bounds check |
| `2147483648` yields generic error | Unclassified overflow | Surface appropriate type mismatch |
| `1,000` parses wrongly | Unspecified locale | Use `Formatter`/`NumberFormat` |
| Blank becomes `null` silently | Optional field/missing constraint | Add `@NotNull` as appropriate |
| Huge numbers consume resources | No input length limit | Cap string length before parsing |
| Conversion error mistaken for validation | Confusing `typeMismatch` with constraints | Handle binding before service |

## 13. Boundary value testing

For a converter bounded to `0..1000` with optional blanks:

| Case | Input | Expected |
| --- | --- | --- |
| Min/max | `"0"` / `"1000"` | Succeeds |
| Below min / above max | `"-1"` / `"1001"` | Rejected by policy |
| Plus sign | `"+1"` | `1` |
| Whitespace | `" 1 "` | `1` if trimmed |
| Blank | `""` / `"   "` | `null` |
| Invalid characters | `"1x"` | Parse rejected |
| Sign only | `"+"` / `"-"` | Parse rejected |
| `Integer` bounds | `"2147483647"` / `"-2147483648"` | Parseable; policy decides |
| Overflow | `"2147483648"` / `"-2147483649"` | Parse rejected |
| Very long string | Thousands of digits | Rejected by input length cap |

Illustrative JUnit tests:

```java
@Test
void acceptsTrimmedPositiveNumber() {
    var converter = new BoundedIntegerConverter(0, 1000, false);
    assertEquals(42, converter.convert(" 42 "));
}

@Test
void treatsBlankAsNull() {
    var converter = new BoundedIntegerConverter(0, 1000, false);
    assertNull(converter.convert("   "));
}

@Test
void rejectsNegativeValue() {
    var converter = new BoundedIntegerConverter(0, 1000, false);
    assertThrows(
            IllegalArgumentException.class,
            () -> converter.convert("-1"));
}

@Test
void rejectsIntegerOverflow() {
    var converter = new BoundedIntegerConverter(0, 1000, false);
    assertThrows(
            IllegalArgumentException.class,
            () -> converter.convert("2147483648"));
}
```

These tests require JUnit 5 and appropriate assertion imports. Converter unit tests verify policy; binder tests verify field-level errors; MVC integration tests verify actual binder registration.

## 14. Number converter design checklist

- Does blank mean `null`, error, or default?
- Is a leading plus sign accepted? Are negative numbers valid for this field?
- Should whitespace be trimmed, or does the contract require strict input?
- Is the target type `Integer`, `Long`, `BigInteger`, or `BigDecimal`?
- Do type min/max bounds differ from business min/max bounds?
- Is input length capped before parsing?
- Is `BindingResult` checked before calling the business service?
- Do missing keys and blank values behave differently?
- Are sensitive raw inputs kept out of logs, and are overflow tests included?

## 15. Takeaways and official references

- `Integer.parseInt` accepts an optional leading `+`/`-`; empty strings, invalid characters, and overflow throw `NumberFormatException`.
- `parseInt` does not automatically trim whitespace.
- `Integer.MIN_VALUE` and `Integer.MAX_VALUE` are valid bounds; values outside this range must be rejected.
- Negative numbers are valid signed integers; forbidding negatives is a separate business policy.
- `Integer` can represent `null`; primitive `int` cannot.
- Custom converters must define policies for blanks, signs, parsing, overflow, and ranges. Validators/services enforce corresponding constraints.
- Conversion errors in Spring binding are typically surfaced via `BindingResult`/`FieldError` with code `typeMismatch`.

References:

- [Oracle Java — Integer.parseInt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html): sign syntax, `int` range, and `NumberFormatException`.
- [Oracle Java — Long](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Long.html): 64-bit integer range.
- [Oracle Java — BigInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html): large integers.
- [Spring Framework — Core Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html): `Converter`, `ConversionService`, and registries.
- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html): `DataBinder`, conversion, and `BindingResult`.
- [Spring Framework — Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): combining conversion and validation.
