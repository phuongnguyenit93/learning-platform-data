# Verifying Consistency Between `parse` and `print` for Number Formatting in Spring Framework

## 1. Goal and context

In input forms, the same number can be **printed for the user to read** and **parsed back from the string the user submits**. For example, `BigDecimal("1234.50")` may display as `1,234.50` in `en-US`, yet as `1.234,50` in `de-DE`. If the two directions disagree, a form may render correctly yet save the wrong number, drop decimal digits, or fail when resubmitting the exact value it just displayed.

After this article, you should be able to:
- Distinguish `print(value, locale)` from `parse(text, locale)` and identify where Spring invokes them in data binding.
- Construct two proper round-trip checks: **value → string → value** and **string → value → normalized string**.
- Verify locales, grouping separators, precision, rounding rules, invalid inputs, and binding errors.
- Write tests at both the `Formatter` level and Spring's actual conversion path, rather than relying solely on visual UI inspection.

The scope of this article is **parse/print consistency for numbers** in Spring Framework, especially in forms and data binding. Value-range checks, business rules, or JSON payloads belong to separate layers of responsibility.

## 2. What do `parse` and `print` actually do?

Spring defines `Formatter<T>` by combining two interfaces:

```java
public interface Printer<T> {
    String print(T value, Locale locale);
}

public interface Parser<T> {
    T parse(String text, Locale locale) throws ParseException;
}

public interface Formatter<T> extends Printer<T>, Parser<T> {
}
```

These are **abbreviated signatures for explanation**, not a standalone Java file. In Spring, these interfaces live in the `org.springframework.format` package.

- `print`: takes a typed value (`BigDecimal`, `Integer`, ...) and a `Locale`, returning a string for UI display.
- `parse`: takes a user-provided string and a `Locale`, returning a typed object or signaling an error.
- `Locale` is part of the contract: you must not use `Locale.US` when printing and accidentally use `Locale.GERMANY` when parsing back.
- `ConversionService` connects conversion steps. In a web environment, `DataBinder`/Spring MVC can use registered formatters to bind request strings to fields.

Simple flow:

```text
Model BigDecimal  --print(value, locale)-->  Form string
Model BigDecimal  <--parse(text, locale)---  User-submitted string
```

Spring includes number formatters such as `NumberStyleFormatter`, `CurrencyStyleFormatter`, `PercentStyleFormatter`, and the `@NumberFormat` annotation. They serve different display contracts. A plain `Converter<String, BigDecimal>` does not express bidirectional locale-aware behavior as explicitly as `Formatter<BigDecimal>`.

## 3. Two invariants to verify

Let `P_L(x) = print(x, L)` and `Q_L(s) = parse(s, L)` for the same locale `L`.

### 3.1. Value round-trip: `parse(print(value))`

For every value `x` in the domain supported by the formatter:

```text
Q_L(P_L(x)) == x           (under the defined equivalence relation)
```

The key lies in the word **equivalence**:
- For arithmetic equality, `BigDecimal.compareTo(...) == 0` checks numeric value equality. `BigDecimal.equals(...)` also compares `scale`: `1.0` and `1.00` are numerically equal yet `equals` returns `false`.
- If the requirement states **currency always has two decimal digits**, you must check `scale() == 2` or an equivalent normalization rule in addition to numeric equality.
- If original trailing decimals, negative zero `-0`, units, or original notation must be preserved, numeric value comparison alone is insufficient. Explicitly specify which information must survive.
- For `double`/`float`, error tolerances must be stated explicitly; do not blindly use `==` for floating-point values. For exact monetary amounts, `BigDecimal` is generally preferred.

Failure example: if `print` rounds `1.23456` to `"1.23"`, then `parse` only recovers `1.23`. The two directions cannot preserve the original value. This is a **lossy precision decision**, not a bug that a parser can magically fix.

### 3.2. String round-trip: `print(parse(text))`

Do not assume every valid string must print back character-for-character identically:

```text
P_L(Q_L(s)) = normalize_L(s)
```

`normalize_L` is the canonical representation defined by the formatter. For example, if the `en-US` standard requires thousands grouping and two fractional digits:

```text
"1234.5"  --parse-->  1234.50  --print-->  "1,234.50"
```

This is **consistent** behavior because the input string is normalized. Only require `P_L(Q_L(s)).equals(s)` when `s` is already defined to be a **canonical** string. For a well-behaved normalizing formatter, an additional property to verify is:

```text
normalize_L(normalize_L(s)) == normalize_L(s)
```

Meaning normalizing a second time does not change the result of the first normalization.

### 3.3. Invalid inputs must fail deliberately

If a string contains trailing characters, mixes locales, exceeds decimal digit limits, or is non-numeric, the parser must return an error matching the contract instead of silently accepting a prefix.

For example, `123.45abc` must never become `123.45` when the application requires the entire input field to be a number. When using `java.text.DecimalFormat`, you can check `ParsePosition.getIndex() == text.length()` to ensure no trailing suffix was ignored. **Verifying that the entire string was consumed is not the same as strictly validating every grouping-separator placement rule**; if strict canonical syntax is needed, add extra checks.

## 4. Scenarios that easily break consistency checks

| Scenario | Common Discrepancy | What to Verify |
| --- | --- | --- |
| Locale | `1,234` can mean different numbers by locale | Print and parse with the same `Locale`; test actual product locales |
| Decimal/grouping signs | Swapping `,` and `.` or accepting invalid grouping | Valid strings, invalid strings, full input consumption |
| Rounding | Fractional loss when `print` limits digits | Test values right before/after rounding thresholds |
| `BigDecimal` scale | Value matches yet `equals` fails | Use `compareTo` for arithmetic; check scale separately |
| Target type | Parsing large numbers then casting to `int` overflows or alters meaning | `Integer`/`Long` bounds, integers vs decimals |
| `%` and currency | Percent typically scales by 100; currency adds symbols and rounding rules | Test exact style, locale, symbol, and data type |
| Negative/zero values | Lost sign, negative zero, or tiny numbers printing as `0` | Test negatives, zero, near-zero, and domain bounds |
| Empty strings | Binding may convert to `null` depending on type/config | Explicit blank/null contract, separate binding-layer tests |
| Whitespace/Unicode | Space characters, non-breaking spaces, Unicode minus signs differ | Real copy/paste, leading/trailing spaces, grouping characters |
| Runtime config | Default locale, JDK locale data, registered formatter differ from expectations | Explicit locale, test on target JDK, test through Spring |

Do not assume a field with `@NumberFormat` always behaves identically to a manually instantiated `NumberStyleFormatter`: annotations, patterns, field types, and registered formatters may select different execution paths. Test the exact path your form uses.

## 5. Complete example: formatter for two-decimal monetary amounts

Business assumption: store `BigDecimal` with exactly two fractional digits; **never silently round** when a value has more than two digits. When displaying, use locale-specific thousands grouping and decimal separators. Input strings may omit grouping separators or a trailing fractional digit; after parsing, they are normalized to two fractional digits. This is a **concrete contract for testing**, not the default behavior of every Spring formatter.

Create a Java 17+ Maven project with the following `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>parse-print-consistency</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
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

Create `src/main/java/demo/ParsePrintDemo.java`:

```java
package demo;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParseException;
import java.text.ParsePosition;
import java.util.Locale;
import java.util.Map;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.format.Formatter;
import org.springframework.format.support.DefaultFormattingConversionService;
import org.springframework.validation.DataBinder;

public class ParsePrintDemo {

    static final class AmountFormatter implements Formatter<BigDecimal> {

        private DecimalFormat numberFormat(Locale locale) {
            DecimalFormat format = new DecimalFormat(
                    "#,##0.00",
                    DecimalFormatSymbols.getInstance(locale));
            format.setParseBigDecimal(true);
            format.setRoundingMode(RoundingMode.UNNECESSARY);
            return format;
        }

        @Override
        public String print(BigDecimal value, Locale locale) {
            // Do not silently truncate the third decimal place.
            BigDecimal fixedScale = value.setScale(2, RoundingMode.UNNECESSARY);
            return numberFormat(locale).format(fixedScale);
        }

        @Override
        public BigDecimal parse(String text, Locale locale) throws ParseException {
            if (text == null || text.isBlank()) {
                throw new ParseException("Amount must not be blank", 0);
            }

            DecimalFormat format = numberFormat(locale);
            ParsePosition position = new ParsePosition(0);
            Number number = format.parse(text, position);

            if (number == null || position.getIndex() != text.length()) {
                throw new ParseException(
                        "Invalid amount or trailing characters",
                        Math.max(0, position.getIndex()));
            }

            try {
                // Only accept values representable with two fractional digits.
                return ((BigDecimal) number).setScale(2, RoundingMode.UNNECESSARY);
            } catch (ArithmeticException ex) {
                throw new ParseException("More than 2 fractional digits",
                        position.getIndex());
            }
        }
    }

    public static final class PaymentForm {
        private BigDecimal amount;

        public BigDecimal getAmount() {
            return amount;
        }

        public void setAmount(BigDecimal amount) {
            this.amount = amount;
        }
    }

    private static void assertAmount(BigDecimal expected, BigDecimal actual) {
        if (actual == null || expected.compareTo(actual) != 0
                || actual.scale() != 2) {
            throw new AssertionError("Expected " + expected + ", got " + actual);
        }
    }

    public static void main(String[] args) throws ParseException {
        AmountFormatter formatter = new AmountFormatter();
        BigDecimal original = new BigDecimal("1234.50");

        for (Locale locale : new Locale[] {Locale.US, Locale.GERMANY}) {
            String printed = formatter.print(original, locale);
            BigDecimal parsed = formatter.parse(printed, locale);
            assertAmount(original, parsed);
            System.out.println(locale.toLanguageTag() + ": " + printed
                    + " -> " + parsed.toPlainString());
        }

        String canonical = formatter.print(
                formatter.parse("1234.5", Locale.US), Locale.US);
        if (!"1,234.50".equals(canonical)) {
            throw new AssertionError("Unexpected canonical output: " + canonical);
        }
        System.out.println("canonical: " + canonical);

        try {
            formatter.parse("1,234.50abc", Locale.US);
            throw new AssertionError("Trailing characters were accepted");
        } catch (ParseException expected) {
            // Pass: the parser does not ignore invalid trailing characters.
        }

        DefaultFormattingConversionService service =
                new DefaultFormattingConversionService();
        service.addFormatter(formatter);

        LocaleContextHolder.setLocale(Locale.GERMANY);
        try {
            String display = service.convert(original, String.class);
            BigDecimal restored = service.convert(display, BigDecimal.class);
            if (!"1.234,50".equals(display)) {
                throw new AssertionError("Unexpected Spring output: " + display);
            }
            assertAmount(original, restored);
            System.out.println("spring: " + display + " -> "
                    + restored.toPlainString());

            PaymentForm form = new PaymentForm();
            DataBinder binder = new DataBinder(form);
            binder.setConversionService(service);
            binder.bind(new MutablePropertyValues(
                    Map.of("amount", "1.234,50")));
            if (binder.getBindingResult().hasErrors()) {
                throw new AssertionError(binder.getBindingResult().toString());
            }
            assertAmount(original, form.getAmount());
            System.out.println("binding: " + form.getAmount().toPlainString());

            PaymentForm invalidForm = new PaymentForm();
            DataBinder invalidBinder = new DataBinder(invalidForm);
            invalidBinder.setConversionService(service);
            invalidBinder.bind(new MutablePropertyValues(
                    Map.of("amount", "1.234,50xyz")));
            if (!invalidBinder.getBindingResult().hasFieldErrors("amount")) {
                throw new AssertionError("Expected amount binding error");
            }
        } finally {
            LocaleContextHolder.resetLocaleContext();
        }

        System.out.println("checks: PASS");
    }
}
```

Run in the directory containing `pom.xml` (Maven 3.9+, JDK 17+):

```bash
mvn -q compile org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=demo.ParsePrintDemo
```

Expected output when run with the specified locales:

```text
en-US: 1,234.50 -> 1234.50
de-DE: 1.234,50 -> 1234.50
canonical: 1,234.50
spring: 1.234,50 -> 1234.50
binding: 1234.50
checks: PASS
```

### Why is the example designed this way?

1. `DecimalFormat` is **created fresh per invocation**: avoids sharing a mutable instance, which is not thread-safe, across requests.
2. `DecimalFormatSymbols.getInstance(locale)` makes grouping and decimal separators depend on the supplied locale rather than accidentally using the machine's default locale.
3. `setParseBigDecimal(true)` keeps numbers in exact decimal form instead of going through `double` and losing binary precision.
4. `ParsePosition` checks that the parser consumed the **entire** string; it does not strictly validate every grouping-separator placement rule by itself.
5. `RoundingMode.UNNECESSARY` turns out-of-contract rounding into an explicit error. A value like `1.234` is not silently pretended to be `1.23`.
6. `LocaleContextHolder` is set and reset with `finally` in the `ConversionService`/`DataBinder` check, preventing locale leakage across test runs.
7. The binding test proves both the Spring path that populates the field value and the one that reports `FieldError`, beyond direct `formatter.print`/`formatter.parse` calls.

**Intentional limitation of the example:** the formatter accepts some syntactic variations that `DecimalFormat` can parse completely, including strings missing grouping separators or having fewer decimal digits. If business rules mandate that input must match the display format *exclusively*, after a successful parse you can compare `print(parsed, locale)` to `text` and reject if they differ. In that case `"1234.5"` would be rejected instead of normalized. That choice must align with user experience. The example also does not model currency, unit codes, or maximum amount bounds.

## 6. Using in Spring MVC and `@NumberFormat`

For HTML forms, `WebMvcConfigurer.addFormatters(FormatterRegistry)` is an extension point for registering custom formatters. The following is a **configuration snippet** (assuming `AmountFormatter` is extracted to a shared class):

```java
@Configuration
class WebConfig implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(new AmountFormatter());
    }
}
```

Corresponding imports are `org.springframework.context.annotation.Configuration`, `org.springframework.format.FormatterRegistry`, and `org.springframework.web.servlet.config.annotation.WebMvcConfigurer`; web configuration requires the Spring MVC dependency. When a form receives a `BigDecimal` field string, Spring MVC uses the configured conversion/formatting system, and `BindingResult` records a type conversion error if parsing fails.

Another option for a specific field is an annotation (model snippet):

```java
@NumberFormat(pattern = "#,##0.00")
private BigDecimal amount;
```

Import `org.springframework.format.annotation.NumberFormat`. This annotation describes how to format the number by pattern. **Do not assume** it enforces the full `RoundingMode.UNNECESSARY`, `scale` check, or input-rejection policy of a hand-written `AmountFormatter`. If replacing a custom formatter with `@NumberFormat`, rerun the entire test matrix. When combining both annotations and registered formatters, test the field's actual conversion path because formatter precedence and selection may differ from expectations.

In an application, a user editing a form in one locale and submitting it under another can cause wrong values or `typeMismatch`. Maintain a consistent locale policy between render and submit; never rely on the server's default locale. For JSON APIs, JSON syntax uses a decimal period per the JSON standard; never apply HTML form locale number formatting to JSON numeric payloads.

## 7. Recommended project test matrix

Each case should specify: **input**, **locale**, **expected parse**, **expected print/canonical**, **data type**, and **error outcome**.

| Category | Data to Test | Expectations / What to Catch |
| --- | --- | --- |
| Basic | `0.00`, `1.00`, `1234.50`, `-1234.50` | Value round-trips accurately, sign/scale handled |
| Locale | `en-US`, `de-DE`, real locales such as `vi-VN` | Grouping and decimal separators match config/runtime |
| Normalization | `1234.5`, `1234.50`, `1,234.50` (`en-US`) | Same value; prints to defined canonical form |
| Precision | `0.01`, `999999999999.99`, boundary numbers | No overflow, no `double` pass-through, no lost digits |
| Reject rounding | `1.234` with 2-decimal formatter | Errors instead of silently saving `1.23` |
| Trailing junk | `123.45abc`, `12%`, unexpected separators | Never mistakes a prefix for the entire number |
| Null/blank | `null`, `""`, `"   "` | Clear rules at form/binding layer and required checks |
| Strict syntax | `12,34.50` (`en-US`) | If canonical syntax is required, add explicit checks; full parse alone is insufficient |
| Other numeric types | `Integer`, `Long`, `Double`, `BigDecimal` | Never assume identical precision/range policies |
| Spring integration | Valid/invalid strings via `DataBinder` or MVC tests | Field receives right value or `BindingResult` has `FieldError` |
| Operational boundaries | Concurrent requests/locales, deployment JDK and config | No locale leakage, no shared mutable `DecimalFormat` |

**Separate three testing layers:**

1. **Formatter unit tests:** invoke `print` and `parse` directly with an explicit `Locale` to verify the pure contract.
2. **ConversionService/binding integration tests:** verify the formatter is registered for the right field type, receives the right locale, and creates binding errors when needed.
3. **MVC form tests:** render the value in the UI, submit it back, and verify `BindingResult`/model values; include locale switches and copy-pasted user inputs. Do not substitute JSON serialization tests for these tests.

For multi-locale tests, pass `Locale` directly when testing formatters; in Spring integration tests, always restore `LocaleContextHolder` in `finally` or the equivalent teardown hook. Avoid making one test depend on another test's locale or execution order.

## 8. Diagnosing round-trip failures

If `parse(print(x))` returns a different number:
1. Record the **original value with its type and scale**, locale, pattern, printed string, parsed value, and the actual formatter class selected.
2. Check whether rounding occurred, `BigDecimal` passed through `double`, fractional digits were truncated, percent/currency scaling ran, or integer casting occurred.
3. Compare both directions under the exact same locale and configuration; reproduce in a standalone unit test.
4. Determine whether this is **contractually accepted information loss** or a bug to fix. If information loss is disallowed, fix the print strategy/data type first.

If `print(parse(s))` differs from `s`:
1. Determine whether `s` was already canonical or merely a valid input needing normalization.
2. Compare `parse(s)` with `parse(print(parse(s)))`; if the numeric value stays unchanged and the second string stabilizes, that may be valid normalization.
3. If the parser dropped a suffix, accepted wrong separators, flipped locale meaning, or allowed forbidden inputs, add syntax validation and failure tests.

If unit tests pass yet the form fails, inspect which formatter/annotation Spring selected, the actual field type, locale resolver, `BindingResult`, `@InitBinder`/`WebMvcConfigurer`, and differences between render and submit. `@NotNull` or `@DecimalMin` cannot substitute for proper parsing; Bean Validation evaluates values after conversion, whereas type-conversion errors must be caught at the binding layer.

## 9. Completion checklist

- [ ] Document valid value domain, locales, decimal digit counts, rounding rules, and canonical form.
- [ ] Verify `parse(print(x, L), L)` under the **proper equivalence relation of the numeric domain**.
- [ ] Verify `print(parse(s, L), L)` produces a normalized, idempotent form without wrongly enforcing character-for-character equality on free-form input.
- [ ] Cover locale cases, zero/negative/boundary values, precision/scale, invalid inputs, trailing characters, and blanks.
- [ ] Never share mutable `DecimalFormat` across threads; keep tests independent of server locale.
- [ ] Include integration tests for the formatter Spring actually uses and `BindingResult` on parse errors.
- [ ] Re-run bidirectional tests whenever changing patterns, annotations, JDK versions, or locale resolvers.

## Reference documentation

- Spring Framework — Spring Field Formatting: https://docs.spring.io/spring-framework/reference/core/validation/format.html
- Spring Framework — Spring MVC Type Conversion: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html
- Java SE — `DecimalFormat`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html
- Java SE — `BigDecimal`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html
